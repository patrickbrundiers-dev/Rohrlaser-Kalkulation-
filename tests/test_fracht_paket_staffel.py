"""Test: Staffelpreise und automatische Fracht mit Paketversand (Patrick 17.11.2026).

Fehler vorher: War die Fracht des Angebots als Paket berechnet, packte jede Staffelmenge auf die Standard-Palette
(Europalette). Der Paket-Tarif hat dafür keinen Preis, keine Stufe bekam einen Preis ('Tarif RW-PAKET ohne Preis
für Europalette'). Jetzt: je Menge die günstigste Kartongröße; passt nichts in einen Karton, ein klarer Grund.
F1/F2: jede Menge vergleicht Paket und Palette (Tarifkopie der anderen Versandart) und alle Ladungsträger.
F3: Spalte Fracht im Reiter Staffeln.
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

assert d["alternative"] and not d["alternative"]["paket"] and d["alternative"]["snapshot"]
ok("Mit der Fracht wird die Tarifkopie der anderen Versandart (Palette) gemerkt")

db.angebot_aendern(aid, "fracht_sendung", json.dumps(d, ensure_ascii=False, default=str))
db.angebot_aendern(aid, "fracht", d["gesamt"])
a, pos, werte = lesen()
ein = rechnen.einstellungen_angebot(a, db.einstellungen())
mengen = (10, 50, 200, 1000)
stufen = [dict(id=i, schluessel="50", menge=m) for i, m in enumerate(mengen, 1)]
zs = staffeln.rechnen_alle(a, pos, stufen, k, tab, ein)
fr = [z["preis"]["fracht"] if z.get("preis") else None for z in zs]
assert all(f for f in fr), [z.get("hinweis") for z in zs]
assert abs(fr[0] - d["gesamt"]) < 0.005, fr
info = [z["fracht_info"] for z in zs]
assert info[0]["versand"] == "Paket" and info[-1]["versand"] == "Palette", info
assert "Palette günstiger als Paket" in zs[-1]["hinweis"] and "Paket günstiger als Palette" in zs[0]["hinweis"]
assert all(abs(i["betrag"] - f) < 0.005 for i, f in zip(info, fr))
ok("F1/F2 Staffeln: je Menge die günstigste Ladung (" +
   " / ".join(f"{m}: {f:.2f} € {i['ladung']} ({i['versand']})" for m, f, i in zip(mengen, fr, info)) + ")")

# nur Paket (ältere Berechnung ohne zweite Tarifkopie): 1.000 Stück in Kartons, viel teurer
d_alt = json.loads(json.dumps(d, default=str))
d_alt.pop("alternative")
zs_alt = staffeln.rechnen_alle(dict(a, fracht_sendung=json.dumps(d_alt)), pos, stufen, k, tab, ein)
nur_paket = zs_alt[-1]["preis"]["fracht"]
assert zs_alt[-1]["fracht_info"]["versand"] == "Paket" and nur_paket > 3 * fr[-1], (nur_paket, fr[-1])
ok(f"Vorher (nur Paket): 1.000 Stück {nur_paket:.2f} € in Kartons, jetzt {fr[-1]:.2f} € als Palette")

# Spalte Fracht im Reiter Staffeln (F3)
from rohrlaser.staffel_seite import fracht_text  # noqa: E402
t3 = fracht_text([zs[-1]])
assert t3.startswith(f"{fr[-1]:.2f}".replace(".", ",") + " €") and "(Palette)" in t3 and "€/Stk." in t3, t3
assert "je Abruf" in fracht_text([zs[-1]], je_abruf=True)
ok(f"F3 Spalte Fracht: '{t3}'")

# Paket erkannt an der Versandart oder an Kartons
d_v = json.loads(json.dumps(d, default=str))
d_v["sendung"]["versandart"] = None
assert fracht_angebot.ist_paket(d_v["sendung"], d_v["snapshot"])
assert not fracht_angebot.ist_paket(dict(lht=[dict(lht_id="EUR", anzahl=1)]), d_v["snapshot"])
ok("Paket erkannt an der Versandart oder daran, dass alle Ladungsträger Kartons sind")

# Teile zu lang für jeden Karton: Palette statt Fehler
p50 = pos[0]
db.position_aendern(p50["id"], "laenge", 1500.0)
a, pos, werte = lesen()
x = fracht_angebot.stufe_details(a, pos, werte)
assert x["betrag"] and x["versand"] == "Palette", x
d2 = fracht_angebot.auto_rechnen(db.fracht_daten(), a, pos, werte, None, einst)
assert d2["gesamt"] and "keinen Karton" in d2["hinweise"][0], (d2.get("fehler"), d2.get("hinweise"))
x = fracht_angebot.stufe_details(dict(a, fracht_sendung=json.dumps(d_alt)), pos, werte)
assert x["betrag"] is None and "keinen Karton" in x["fehler"], x
db.position_aendern(p50["id"], "laenge", 345.0)
ok("1.500 mm passt in keinen Karton: als Palette gerechnet; nur mit Paket-Tarif ein klarer Grund")

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
