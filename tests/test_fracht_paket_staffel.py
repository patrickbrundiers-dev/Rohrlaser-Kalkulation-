"""Test: Staffelpreise und automatische Fracht mit Paketversand (Patrick 17.11.2026).

Fehler vorher: War die Fracht des Angebots als Paket berechnet, packte jede Staffelmenge auf die Standard-Palette
(Europalette). Der Paket-Tarif hat dafür keinen Preis, keine Stufe bekam einen Preis ('Tarif RW-PAKET ohne Preis
für Europalette'). Jetzt: je Menge die günstigste Kartongröße; passt nichts in einen Karton, ein klarer Grund.
Dazu: paletten.packen sucht bei 'nie mischen'/'Reste' nur noch die letzte Palette der Position (vorher alle,
quadratisch bei vielen Kartons) – gleiche Ergebnisse, viel schneller.
"""
import json
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

import beispiel_angebot  # noqa: E402
from rohrlaser import fracht, fracht_angebot, paletten, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
db.einstellung_setzen("absender_plz", "33129")
db.fracht_richtwerte_laden("33129")
db.einstellung_setzen("fracht_versandart", fracht.PAKET)
aid = beispiel_angebot.anlegen(db)
for p in db.positionen(aid):              # nur Pos. 50 (RR 48,3 × 2,6, 345 mm) bleibt: passt in Kartons
    if p["pos"] != 50:
        db.positionen_loeschen([p["id"]])
    else:
        db.position_aendern(p["id"], "stueck", 10)
db.angebot_aendern(aid, "fracht_auto", "ja")
db.angebot_aendern(aid, "fracht_plz", "20095")
db.angebot_aendern(aid, "fracht_modus", fracht_angebot.BERECHNET)
k, tab = db.kontext(), db.tabellen()


def lesen():
    a = db.angebot(aid)
    pos = db.positionen(aid)
    return a, pos, [rechnen.position_werte(p, a, k, tab) if rechnen.position_aktiv(p) else None for p in pos]


EINST = ("absender_plz", "absender_land", "fracht_versandart", "fracht_lht_standard", "fracht_lht_langgut",
         "fracht_umwegfaktor") + fracht_angebot.PALETTEN_EINST
einst = {n: db.einstellung(n) for n in EINST}
a, pos, werte = lesen()
d = fracht_angebot.auto_rechnen(db.fracht_daten(), a, pos, werte, None, einst)
assert not d.get("fehler") and d["gesamt"], d.get("fehler")
assert all(x["lht_id"].startswith("K-") for x in d["sendung"]["lht"]), d["sendung"]["lht"]
assert einst["fracht_lht_standard"] == "EUR"
ok(f"Automatische Fracht mit Versandart Paket: {d['sendung']['lht']} {fracht.euro(d['gesamt'])} "
   "(vorher Europalette -> 'Tarif RW-PAKET ohne Preis für Europalette')")

db.angebot_aendern(aid, "fracht_sendung", json.dumps(d, ensure_ascii=False, default=str))
db.angebot_aendern(aid, "fracht", d["gesamt"])
a, pos, werte = lesen()
ein = rechnen.einstellungen_angebot(a, db.einstellungen())
mengen = (10, 50, 200, 1000)
stufen = [dict(id=i, schluessel="50", menge=m) for i, m in enumerate(mengen, 1)]
zs = staffeln.rechnen_alle(a, pos, stufen, k, tab, ein)
fr = [z["preis"]["fracht"] if z.get("preis") else None for z in zs]
assert all(f for f in fr), [z.get("hinweis") for z in zs]
assert fr == sorted(fr) and abs(fr[0] - d["gesamt"]) < 0.005, fr
assert all("× K-" in (z.get("hinweis") or "") for z in zs), [z.get("hinweis") for z in zs]
ok("Staffeln mit Paket: jede Menge mit eigener Fracht in Kartons (" +
   " / ".join(f"{m}: {f:.2f}" for m, f in zip(mengen, fr)) + " €)")

# ältere Frachtberechnung ohne Versandart in der Sendung, aber nur mit Kartons: auch Paket
d_alt = json.loads(json.dumps(d))
d_alt["sendung"]["versandart"] = None
assert fracht_angebot.ist_paket(d_alt["sendung"], d_alt["snapshot"])
assert not fracht_angebot.ist_paket(dict(lht=[dict(lht_id="EUR", anzahl=1)]), d_alt["snapshot"])
ok("Paket erkannt an der Versandart oder daran, dass alle Ladungsträger Kartons sind")

# Teile zu lang für jeden Karton: klarer Grund statt Palette mit Paket-Tarif
p50 = pos[0]
db.position_aendern(p50["id"], "laenge", 1500.0)
a, pos, werte = lesen()
b, _, fehler = fracht_angebot.stufe(a, pos, werte)
assert b is None and "passen in keinen Karton" in fehler, fehler
zs = staffeln.rechnen_alle(a, pos, stufen[:1], k, tab, ein)
assert zs[0]["preis_einheit"] is None and "keinen Karton" in zs[0]["hinweis"], zs[0]["hinweis"]
d2 = fracht_angebot.auto_rechnen(db.fracht_daten(), a, pos, werte, None, einst)
assert d2["fehler"] == fracht_angebot.KEIN_KARTON, d2.get("fehler")
db.position_aendern(p50["id"], "laenge", 345.0)
ok("1.500 mm passt in keinen Karton: Stufe und automatische Fracht nennen den Grund (kein stiller Palettenpreis)")

# paletten.packen: gleiche Anzahl wie vorher, viele Kartons schnell
lht = db.fracht_daten()["lht"]
werte_k = [dict(gewicht=0.8, profil_abm=("Quadratrohr", 40.0, 40.0, 2.0))]
for n, soll in ((20, 1), (1000, 42), (10000, 417)):
    for mischen in paletten.MISCHEN:
        e = paletten.packen([dict(id=1, pos=10, stueck=n, laenge=300.0)], werte_k, lht, "K-M", None,
                            {"palette_mischen": mischen})
        assert e["anzahl"] == soll and sum(x for p in e["paletten"] for _, x in p["inhalt"]) == n, (n, mischen, e["anzahl"])
t = time.time()
e = paletten.packen([dict(id=1, pos=10, stueck=40000, laenge=300.0), dict(id=2, pos=20, stueck=40000, laenge=200.0)],
                    werte_k * 2, lht, "K-M", None, {})
dauer = time.time() - t
assert e["gesamt_stueck"] == 80000 and dauer < 10, dauer
ok(f"Packen: gleiche Kartonzahl wie vorher, 80.000 Teile in {e['anzahl']} Kartons in {dauer:.1f} s")

db.schliessen()
print("OK: Staffeln mit Paketversand")
