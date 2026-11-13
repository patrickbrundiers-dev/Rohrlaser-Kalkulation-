"""Roadmap Kalkulation, Phase 2 Paket 2b Material (Freigabe Patrick 13.11.2026 „Ganze Phase 2 nach Empfehlung“).

MAT-021   Schwere Stangen: Mehrzeit je Stange ab einem Stangengewicht (Maschine), leer = aus.
MAT-012   Materialindex je Monat: Tonnenpreis = Basis + Zuschlag des Monats (Werkstoff vor Kategorie vor alle).
MAT-008   Materialpreise als Zeitreihe: jeder Stand mit Datum, Durchschnitt 3/6/12 Monate, Fenster Preisverlauf.
PART-013  EK-Verlauf je Zukaufartikel aus dem Protokoll, Hinweis bei Preissprung über der Schwelle.
MAT-013   Mindestabnahme des Lieferanten: Hinweis, mit Einstellung ja als Kosten (kein Lagerbestand).
MAT-014   Vormaterial schon veredelt gegen Veredeln nach dem Laser: Vergleich als Hinweis.
MAT-019   Gewicht aus STEP-Volumen gegen Profil × Länge: Hinweis über der Schwelle.

Aufruf: python tests/test_phase2b_1311.py
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

import beispiel_angebot as B  # noqa: E402
from rohrlaser import materialindex, material_pruefung as mp, preisverlauf as pv, rechnen, zeit_zusatz, zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster, StammdatenSeite  # noqa: E402
from rohrlaser.stammdaten import TABELLE  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k not in ("nummer", "kundennr", "kunde")}
ROHR = dict(B.POSITIONEN[0])          # RR 42,4x2,0 S235, 1250 mm
K1 = db.zeilen("kunden")[0]["kundennr"]
HEUTE = datetime.date.today()


def ok(text):
    print("OK  ", text)


def angebot(*positionen, kopf=None):
    i = db.angebot_neu(dict(KOPF, kundennr=K1, **(kopf or {})))
    for p in positionen:
        db.position_neu(i, p)
    s = fenster.angebot_oeffnen(i)
    s.optimieren()
    return s


def texte(punkte):
    return [p.text for p in punkte]


# ------------------------------------------------------------------ Schema und Vorgaben
for t, felder in (("maschinen", {"schwer_ab_kg", "zeit_schwer"}), ("preise", {"mindest_stangen"}),
                  ("lieferlaengen", {"mindest_stangen"}), ("oberflaechen", {"vormaterial", "veredeln_tage"}),
                  ("material_index", {"monat", "kategorie", "werkstoff_id", "zuschlag"}),
                  ("preis_verlauf", {"datum", "art", "preis"})):
    spalten = {r[1] for r in db.con.execute(f'PRAGMA table_info("{t}")')}
    assert felder <= spalten, (t, felder - spalten)
assert db.einstellung("mindestabnahme_kosten") == "nein"
assert db.einstellung("step_gewicht_abweichung") == 0 and db.einstellung("zukauf_preissprung") == 0
assert not db.zeilen("material_index")
assert all(not m.get("schwer_ab_kg") and not m.get("zeit_schwer") for m in db.zeilen("maschinen"))
ok("Schema 87: neue Felder und Tabellen leer, neue Einstellungen aus")

# ------------------------------------------------------------------ MAT-021 schwere Stangen
k = db.kontext()
s_rohr = dict(profil="RR 42,4x2,0", werkstoff="S235-10219", stange=6000)
kg = zeit_zusatz.stange_kg(s_rohr, k)
assert kg and 5 < kg < 20, kg                 # 42,4 x 2: ~1,99 kg/m x 6 m
m = dict(schwer_ab_kg=None, zeit_schwer=60)
assert zeit_zusatz.beladung_s(s_rohr, m, k) == 0
assert zeit_zusatz.beladung_s(s_rohr, dict(m, schwer_ab_kg=kg - 1), k) == 60
assert zeit_zusatz.beladung_s(s_rohr, dict(m, schwer_ab_kg=kg + 1), k) == 0
s = angebot(dict(ROHR, stueck=20))
vorher = s._rechnung()[1]["stangenwechsel_s"] if "stangenwechsel_s" in s._rechnung()[1] else None
n_stangen = len(s.ergebnis["stangen"])
masch = next(x for x in db.zeilen("maschinen") if x["maschinen_id"] == s.kopf["maschine"])
db.aendern("maschinen", masch["id"], "schwer_ab_kg", 5.0)
db.aendern("maschinen", masch["id"], "zeit_schwer", 90.0)
s.neu_laden()
s.optimieren()
k = s.k
assert sum(zeit_zusatz.schwer_s(st, k.maschinen[s.kopf["maschine"]], k) for st in s.ergebnis["stangen"]) \
    == 90 * n_stangen
nachher = s._rechnung()[1].get("stangenwechsel_s")
if vorher is not None and nachher is not None:
    assert abs(nachher - vorher - 90 * n_stangen) < 1e-6, (vorher, nachher)
db.aendern("maschinen", masch["id"], "schwer_ab_kg", None)
ok(f"MAT-021: Stange {kg:.1f} kg ab Grenze +90 s je Stange ({n_stangen} Stangen), ohne Grenze 0")

# ------------------------------------------------------------------ MAT-012 Materialindex
ws = next(w for w in db.zeilen("werkstoffe") if w["werkstoff_id"] == "S235-10219")
basis = ws["tonnenpreis"]
monat = HEUTE.strftime("%Y-%m")
frueher = (HEUTE.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
zeilen = [dict(monat=frueher, kategorie=ws["kategorie"], werkstoff_id=None, zuschlag=50),
          dict(monat="2999-01", kategorie=None, werkstoff_id=None, zuschlag=999)]
assert materialindex.zuschlag("S235-10219", ws["kategorie"], zeilen)[0] == 50       # letzter früherer Monat
zeilen.append(dict(monat=monat, kategorie=None, werkstoff_id=None, zuschlag=20))
assert materialindex.zuschlag("S235-10219", ws["kategorie"], zeilen)[0] == 50       # Kategorie vor „alle“
zeilen.append(dict(monat=frueher, kategorie=None, werkstoff_id="S235-10219", zuschlag=70))
assert materialindex.zuschlag("S235-10219", ws["kategorie"], zeilen)[0] == 70       # Werkstoff vor Kategorie
assert materialindex.anwenden({"X": dict(tonnenpreis=100)}, []) == {"X": dict(tonnenpreis=100)}
assert materialindex.pruefung([dict(monat="11/2026")]) and not materialindex.pruefung([dict(monat=monat)])
db.neu("material_index", dict(monat=monat, kategorie=ws["kategorie"], zuschlag=150.0, quelle="Lieferant"))
w = db.kontext().werkstoffe["S235-10219"]
assert w["tonnenpreis"] == basis + 150 and w["tonnenpreis_basis"] == basis and w["index_monat"] == monat
assert db.zeilen("werkstoffe")[0]["tonnenpreis"] == ws["tonnenpreis"]               # Stammdaten unverändert
assert "Materialindex" in materialindex.text(w)
db.loeschen("material_index", [z["id"] for z in db.zeilen("material_index")])
ok(f"MAT-012: Tonnenpreis {basis:.0f} + Index 150 €/t im Kontext, Vorrang Werkstoff > Kategorie > alle")

# ------------------------------------------------------------------ MAT-008 Preisverlauf
pr = next(z for z in db.zeilen("preise") if z["profil_id"] == "RR 42,4x2,0" and z["werkstoff_id"] == "S235-10219")
start = db.preisverlauf("RR 42,4x2,0", "S235-10219", pv.ART_PREIS)
assert len(start) == 1 and abs(start[0]["preis"] - pr["preis"]) < 1e-9
db.aendern("preise", pr["id"], "preis", round(pr["preis"] * 1.2, 2))
db.aendern("preise", pr["id"], "bemerkung", "nur Text")          # keine Preisänderung: kein neuer Stand
e = db.preisverlauf("RR 42,4x2,0", "S235-10219", pv.ART_PREIS)
assert len(e) == 2 and abs(e[-1]["preis"] - round(pr["preis"] * 1.2, 2)) < 1e-9, e
assert any(x["art"] == pv.ART_TONNE for x in db.preisverlauf(werkstoff_id="S235-10219"))
punkte = [(HEUTE - datetime.timedelta(days=200), 1.0), (HEUTE - datetime.timedelta(days=50), 2.0)]
kz = {x["monate"]: x for x in pv.kennzahlen(punkte, HEUTE)}
assert abs(kz[3]["mittel"] - (1.0 * 41 + 2.0 * 51) / 92) < 0.02, kz[3]
assert kz[6]["damals"] == 1.0 and abs(kz[6]["aenderung_pct"] - 100) < 1e-9
assert kz[12]["damals"] is None
seite = StammdatenSeite(db, TABELLE["preise"], lambda *a, **k: None)
assert any(b.text() == "Preisverlauf …" for b in seite.findChildren(QPushButton))
seite.ansicht.selectRow(0)
d = seite.preisverlauf(zeigen=False)
assert d.wahl.count() > 1 and d.kurve.punkte, d.wahl.count()
ok("MAT-008: jeder Preisstand mit Datum, Durchschnitt zeitgewichtet, Fenster Preisverlauf mit Kurve")

# ------------------------------------------------------------------ PART-013 EK-Verlauf
aid = db.zukauf_speichern(None, dict(artikelnr="Z-EK", bezeichnung="Stopfen", einheit="Stück",
                                     aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT,
                                     aufschlag_wert=0),
                          [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=1.00)])])
db.zukauf_ek_eintragen(aid, 1.05, lieferant="L")
db.zukauf_ek_eintragen(aid, 1.30, lieferant="L")
v = pv.ek_verlauf(db.zukauf_historie())
reihe = v[(aid, "L")]
assert [x["preis"] for x in reihe] == [1.00, 1.05, 1.30], reihe
assert pv.spruenge(v, 0) == []
sp = pv.spruenge(v, 10)
assert len(sp) == 1 and abs(sp[0]["pct"] - (1.30 / 1.05 - 1) * 100) < 1e-6 and "Stopfen" in pv.sprung_text(sp[0])
from rohrlaser.zukauf_preise import PreisaenderungenSeite  # noqa: E402
zs = PreisaenderungenSeite(db, lambda *a, **k: None)
dlg = zs.ek_verlauf(zeigen=False)
assert dlg.kurve.punkte and dlg.tabelle.rowCount() == 3
# im Angebots-Check nur mit Schwelle und nur für Artikel des Angebots
s = angebot(dict(ROHR, stueck=10, zukauf=json.dumps([dict(artikel_id=aid, menge=1)])))
assert not [t for t in texte(s._material_punkte()) if "EK-Preissprung" in t]
db.einstellung_setzen("zukauf_preissprung", 10.0)
s.einst = dict(s.einst, zukauf_preissprung=10.0)
assert [t for t in texte(s._material_punkte()) if "EK-Preissprung Z-EK" in t or "EK-Preissprung Stopfen" in t]
db.einstellung_setzen("zukauf_preissprung", 0.0)
ok("PART-013: EK-Verlauf je Lieferant aus dem Protokoll, Sprung über 10 % im Check und markiert")

# ------------------------------------------------------------------ MAT-013 Mindestabnahme
s = angebot(dict(ROHR, stueck=10))
n = len(s.ergebnis["stangen"])
pr = next(z for z in db.zeilen("preise") if z["profil_id"] == "RR 42,4x2,0" and z["werkstoff_id"] == "S235-10219")
assert mp.bedarf(s.ergebnis["stangen"], s.tabellen) == []
db.aendern("preise", pr["id"], "mindest_stangen", n + 3)
s.neu_laden()
s.optimieren()
g = mp.bedarf(s.ergebnis["stangen"], s.tabellen)
assert len(g) == 1 and g[0]["mehr"] == 3 and g[0]["n"] == n, g
sw0 = rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)
mat0 = sum(x["kosten"] for x in sw0)
t = [x for x in texte(s._material_punkte()) if x.startswith("Mindestabnahme")]
assert t and "nicht im Preis" in t[0] and f"mindestens {n + 3} Stangen, gebraucht {n}" in t[0], t
db.einstellung_setzen("mindestabnahme_kosten", "ja")
s.neu_laden()
s.optimieren()
sw1 = rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)
mat1 = sum(x["kosten"] for x in sw1)
assert abs(mat1 - mat0 * (n + 3) / n) < 0.01, (mat0, mat1)
assert "(im Preis enthalten)" in [x for x in texte(s._material_punkte()) if x.startswith("Mindestabnahme")][0]
db.einstellung_setzen("mindestabnahme_kosten", "nein")
db.aendern("preise", pr["id"], "mindest_stangen", None)
ok(f"MAT-013: {n} Stangen gebraucht, Mindestabnahme {n + 3}: Hinweis, mit „ja“ Material × {n + 3}/{n}")

# ------------------------------------------------------------------ MAT-014 Vormaterial veredelt
db.neu("werkstoffe", dict(ws, werkstoff_id="S235-SZ", werkstoff="S235 sendzimirverzinkt", tonnenpreis=basis * 1.15))
ob = next(o for o in db.zeilen("oberflaechen") if (o.get("aufpreis_m") or 0) > 0)
db.aendern("oberflaechen", ob["id"], "vormaterial", "S235-SZ")
db.aendern("oberflaechen", ob["id"], "veredeln_tage", 5)
s = angebot(dict(ROHR, stueck=10, oberflaeche=ob["oberflaeche"]))
vg = mp.veredeln_vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)
assert len(vg) == 1 and vg[0]["vormaterial"] == "S235-SZ" and vg[0]["tage"] == 5, vg
t = [x for x in texte(s._material_punkte()) if "Vormaterial S235-SZ" in x]
assert t and "spart 5 Arbeitstage Veredeln" in t[0] and "der Kunde entscheidet" in t[0], t
db.aendern("oberflaechen", ob["id"], "vormaterial", None)
s.neu_laden()
assert mp.veredeln_vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst) == []
ok(f"MAT-014: {ob['oberflaeche']} nach dem Laser gegen Vormaterial: {t[0][:90]} …")

# ------------------------------------------------------------------ MAT-019 STEP-Gewicht
kgm = rechnen.kg_je_m("RR 42,4x2,0", "S235-10219", s.k)
vol = kgm * 1.25 / ws["dichte"] * 1e6            # mm³ passend zu 1250 mm
gut = dict(ROHR, stueck=5, technik=json.dumps(dict(volumen_step=round(vol * 0.97, 1))))
falsch = dict(ROHR, pos=20, stueck=5, technik=json.dumps(dict(volumen_step=round(vol * 1.6, 1))))
s = angebot(gut, falsch)
assert mp.gewicht_punkte(s.positionen, s.k, s.einst) == []          # Einstellung 0 = aus
s.einst = dict(s.einst, step_gewicht_abweichung=15.0)
pk = mp.gewicht_punkte(s.positionen, s.k, s.einst)
assert len(pk) == 1 and "Pos. 20" in pk[0].text and "+60 %" in pk[0].text and pk[0].ziel == "pos:1", texte(pk)
x = mp.step_gewicht(s.positionen[0], s.k)
assert abs(x[2] + 3) < 0.5, x
ok("MAT-019: STEP-Gewicht −3 % ohne Hinweis, +60 % mit Hinweis und Sprung zur Position")

# ------------------------------------------------------------------ Angebots-Check im Fenster
s.freigabe_punkte()
fenster.close()
db.schliessen()
print("Alle Prüfungen Paket 2b bestanden.")
