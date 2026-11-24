"""Nesting-Arbeitsplatz 2.0 (Patrick 24.11.2026): Strategien F/G/H, Zwischenspeicher bitgleich, Machbarkeit,
aktueller Plan im Vergleich, Live-Status, Teile frei ziehen (feste Reihenfolge, gespeichert und so neu gerechnet),
Stange auflösen und von Hand verschachteln, Abmessung/Alles zurücksetzen, CSV-Export, Protokoll, 3D und
Stangenbild aus denselben Daten, Bereiche ein-/ausblenden.

Aufruf: python tests/test_nesting_arbeitsplatz2.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import csv
import io
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import nesting as ne, nesting_machbarkeit as nm, nesting_vergleich as nv, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser import nesting_dialog  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
QR, ST = "QR 40x40x3", "S235-10219"
for laenge in (6000, 6500, 7000):
    db.neu("lieferlaengen", dict(profil_id=QR, werkstoff_id=ST, laenge=laenge))
fenster = Hauptfenster(db, tmp, stumm=True)
aid = db.angebot_neu(dict(kunde="Test", maschine="T03", stange=6000))
for i, (lg, n) in enumerate([(850, 12), (1250, 8), (430, 6), (1800, 4)]):
    db.position_neu(aid, dict(pos=10 * (i + 1), artikel=f"A{i}", profil_id=QR, werkstoff_id=ST, laenge=lg,
                              stueck=n, schneidweg=160, einstiche=1))
s = fenster.angebot_oeffnen(aid)
assert s.optimieren()

# ---- Engine: neue Strategien, Zwischenspeicher bitgleich
status = []
v = s.nesting_vergleich(status=lambda d: status.append(dict(d)))
assert status and status[-1]["plaene"] == len(status) and status[-1]["beste"]["stangen"] > 0
assert "geprüfte Pläne" in nesting_dialog.status_text(status[-1])
g = v[0]["gruppe"]
p = v[0]["plaene"]
for x in (ne.F, ne.G, ne.H):
    assert x in p, list(p)
    ne.pruefe(g, p[x].stangen, list(p[x].uebrig), None)
assert p[ne.F].werte["stangen"] <= min(p[y].werte["stangen"] for y in (ne.A, ne.B, ne.D))
assert p[ne.G].werte["verschnitt_mm"] <= min(p[y].werte["verschnitt_mm"] for y in (ne.A, ne.B, ne.D)) + 1e-6
ne.merker_leeren()
v2 = s.nesting_vergleich()
for x in p:
    assert [(laenge, [(t.laenge, r) for t, r in f], k) for laenge, f, k in p[x].stangen] == \
        [(laenge, [(t.laenge, r) for t, r in f], k) for laenge, f, k in v2[0]["plaene"][x].stangen], x
print("OK     Strategien F/G/H geprüft, Zwischenspeicher bitgleich")

# ---- Machbarkeit: zu lange Stange ist unzulässig, normale Pläne zulässig
assert all(z.get("zulaessig", True) for z in v[0]["zeilen"]), [z.get("machbar") for z in v[0]["zeilen"]]
b = nm.pruefen(g, p[ne.A].stangen, {"max_stange": 6200})
assert any(x.stufe == nm.FEHLER for x in b) == any(laenge > 6200 for laenge, _, _ in p[ne.A].stangen)
b = nm.pruefen(g, p[ne.A].stangen, {"max_stange": 5000})
assert not nm.zulaessig(b) and "unzulässig" in nm.text(b)
print("OK     Machbarkeit: max. Stangenlänge schließt Plan aus")

# ---- Aktueller (gespeicherter) Plan als Zeile, nicht veraltet
assert any(z["strategie"] == nv.AKTUELL for z in v[0]["zeilen"]), [z["strategie"] for z in v[0]["zeilen"]]
assert not v[0].get("veraltet")
assert v[0]["plaene"][nv.AKTUELL].werte["stangen"] == len(s.ergebnis["stangen"])
print("OK     Gespeicherter Plan im Vergleich (nicht veraltet)")

# ---- Protokoll und CSV
zeilen = nv.protokoll(v[0])
assert zeilen and any("Untergrenze" in z for z in zeilen), zeilen[:5]
txt = nv.export_csv(v[0], p[ne.A], s.positionen)
rows = list(csv.reader(io.StringIO(txt), delimiter=";"))
assert len(rows) - 1 == sum(len(f) for _, f, _ in p[ne.A].stangen), len(rows)
print("OK     Protokoll und CSV-Export (je Teil eine Zeile)")

# ---- Dialog: Bereiche, Ansichten, Ziehen, Auflösen, Zurücksetzen
d = nesting_dialog.NestingDialog(v, s.positionen, s)
d.resize(1400, 900)
d.show()
app.processEvents()
for n in ("Links", "Rechts", "Unten"):
    d.bereich_knoepfe[n].setChecked(False)
    app.processEvents()
    d.bereich_knoepfe[n].setChecked(True)
assert d.links.isVisible() and d.rechts.isVisible() and d.unten.isVisible()
r = next(i for i, z in enumerate(d.vergleich[0]["zeilen"]) if z["strategie"] == ne.A)
d.tabelle.selectRow(r)
app.processEvents()
st = d.bild.stangen
assert d.bild.anzeige and len(d.bild.anzeige) == len([x for x in st if x[1]])
assert d.karten["ausnutzung"].text().endswith("%") and d.karten["machbar"].text()
d.ansicht_setzen(nesting_dialog.STANGENBILD)
app.processEvents()
d.ansicht_setzen(nesting_dialog.DREI_D)
d.stange_gewaehlt(0)
app.processEvents()
assert d.drei_d.stange is not None and d.drei_d.segmente
d.drei_d.grab().save(str(tmp / "nesting_3d.png"))
d.ansicht_setzen(nesting_dialog.BEARBEITEN)
app.processEvents()
d.grab().save(str(tmp / "nesting_arbeitsplatz2.png"))

# Teil auf der Stange nach hinten ziehen (feste Reihenfolge)
i0 = next(i for i, x in enumerate(st) if len(x[1]) >= 2)
erstes = st[i0][1][0][0]
d.gezogen(i0, 0, i0, len(st[i0][1]))
assert d.hand_stangen is not None and d.fest, d.hinweis.text()
assert d.bild.stangen[i0][1][-1][0] is erstes
ne.pruefe(g, d.hand_stangen, [], None)
# auf eine neue Stange ziehen
n_vor = len(d.bild.stangen)
d.gezogen(i0, 0, -1, 0)
assert len(d.bild.stangen) == n_vor + 1, d.hinweis.text()
# rückgängig / wiederholen
d.rueckgaengig()
assert len(d.bild.stangen) == n_vor
d.wiederholen()
assert len(d.bild.stangen) == n_vor + 1
d.rueckgaengig()
d.rueckgaengig()
assert d.bild.stangen == st and d.hand_stangen is None
# zu voll: Meldung, nichts geändert
voll = max(range(len(st)), key=lambda i: sum(t.laenge for t, _ in st[i][1]))
lang = max(((i, n) for i, x in enumerate(st) for n in range(len(x[1])) if i != voll),
           key=lambda x: st[x[0]][1][x[1]][0].laenge)
d.gezogen(lang[0], lang[1], voll, 0)
if d.hand_stangen is None:
    assert "Passt nicht" in d.hinweis.text() and d.bild.stangen == st, d.hinweis.text()
# Stange auflösen und Teil von Hand wieder einsetzen
d.stange_gewaehlt(i0)
n_teile = len(st[i0][1])
d.stange_aufloesen()
assert len(d.uebrig) == n_teile and len(d.bild.stangen) == len(st) - 1
assert "nicht eingeplant" in d.kennzahlen.text()
d.uebrig_liste.setCurrentRow(0)
assert d.bild.einsetz_modus
d.eingesetzt(-1, 0)
assert len(d.uebrig) == n_teile - 1 and len(d.bild.stangen) == len(st)
# Klick-Einsetzen in das Bild (Punkt auf der neuen Stange)
d.uebrig_liste.setCurrentRow(0)
y = d.bild.OBEN + (len(d.bild.stangen) - 1) * d.bild.ZEILE + d.bild.KOPF + 5
d.bild.mousePressEvent(type("E", (), {"position": lambda self: QPointF(d.bild.width() - 200, y),
                                      "button": lambda self: 1})())
assert len(d.uebrig) == n_teile - 2, (len(d.uebrig), d.hinweis.text())
# CSV der gezeigten Stangen
pfad = d.csv_speichern(str(tmp / "plan.csv"))
assert pfad and Path(pfad).read_text(encoding="utf-8-sig").count("\n") > 3
# Belegung übernehmen: fest gespeichert, danach so gerechnet
hand = d.hand_uebernehmen()
assert hand and all(x.get("fest") for x in hand)
assert all(len(t) == 3 for x in hand for t in x["teile"])
d.abmessung_zuruecksetzen()
assert d.hand[v[0]["schluessel"]] is None
assert d.alles_zuruecksetzen() >= 0
print("OK     Dialog: Bereiche, 2D/Stangenbild/3D, ziehen, neue Stange, rückgängig, auflösen, einsetzen, CSV, "
      "zurücksetzen")


# Belegung mit fester Reihenfolge speichern und neu optimieren: genau diese Reihenfolge
def fest_ziehen(d):
    r = next(i for i, z in enumerate(d.vergleich[0]["zeilen"]) if z["strategie"] == ne.A)
    d.tabelle.selectRow(r)
    st = d.bild.stangen
    i0 = next(i for i, x in enumerate(st) if len(x[1]) >= 2)
    d.gezogen(i0, 0, i0, len(st[i0][1]))
    d.erwartet = [[round(t.laenge, 3) for t, _ in f] for _, f, _ in d.bild.stangen]
    d.hand_uebernehmen()
    fest_ziehen.d = d
    return True


assert s.nesting_arbeitsplatz(dialog=fest_ziehen)
gespeichert = db.angebot(aid)["stangen_hand"]
assert gespeichert and all(x.get("fest") for x in next(iter(gespeichert.values())))
ist = [[round(t["laenge"], 3) for t in x["teile"]] for x in s.ergebnis["stangen"]]
assert sorted(map(tuple, ist)) == sorted(map(tuple, fest_ziehen.d.erwartet)), (ist, fest_ziehen.d.erwartet)
assert all(x.get("nesting") == rechnen.NESTING_HAND for x in s.ergebnis["stangen"])
print("OK     Feste Reihenfolge gespeichert und beim Optimieren genau so gerechnet")

# Sprung aus dem Stangenbild: Abmessung und Stange gewählt
start = s.nesting_start(2)
assert start and start[0] == v[0]["schluessel"]
geoeffnet = {}
assert s.nesting_von_stange(2, dialog=lambda d: (geoeffnet.update(st=d.bild.stange_nr,
                                                                  s=d.strategie_der_zeile()), False)[-1]) is False
assert geoeffnet == {"st": 1, "s": nv.AKTUELL}, geoeffnet
print("OK     Sprung aus dem Stangenbild: Abmessung, gespeicherter Plan, Stange gewählt")

# Alles zurücksetzen im Angebot: wieder Strategie/bisher
assert s.nesting_arbeitsplatz(dialog=lambda d: (d.alles_zuruecksetzen(), True)[-1])
assert not db.angebot(aid)["stangen_hand"]
print("OK     Alles zurücksetzen entfernt die Belegung von Hand")
# Reiter Optimierung: Verschachtelungs-Vorschlag mit gerechnetem Vorteil, Übernehmen als neue Fassung
from rohrlaser import optimierungsvorschlaege as ov  # noqa: E402
vs = ov.verschachtelung(s.nesting_vergleich())
assert vs and all(x["art"] == ov.VERSCHACHTELUNG and x["aktion"]["typ"] == "nesting" for x in vs), vs
assert all(x["kosten"] is None or x["kosten"] >= ov.NESTING_MIN_EUR - 1e-9 for x in vs)
alle_v = s.optimierung_vorschlaege(maschinen=True)
assert any(x["art"] == ov.VERSCHACHTELUNG for x in alle_v), [x["art"] for x in alle_v]
neu = s.vorschlag_uebernehmen(vs[0])
assert db.angebot(neu)["nesting"] == {vs[0]["aktion"]["schluessel"]: vs[0]["aktion"]["strategie"]}
assert not db.angebot(aid)["nesting"] or db.angebot(aid)["nesting"] != db.angebot(neu)["nesting"]
print("OK     Optimierung: Verschachtelungs-Vorschlag, als neue Fassung übernommen")
fenster.close()
db.schliessen()
print("Alle Tests OK")
