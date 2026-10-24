"""3D-Editor für Rohr und Blech ausbauen (Plan kalkulation/3d-editor, Schritte 3E-1 und 3E-2):
- E1 Durchdringung: Rundrohr rechtwinklig = schneidweg.sattel, Rechteck flach = Umfang, schräg = Gehrung, Versatz
  und zu kleines Gegenrohr, Durchbruch (zwei Wände).
- E2 Rechenfelder: Rechnungen mit Komma, ×, Größen (L/2), Muster „3x25“, nichts außer Rechnen (kein eval).
- E3 Ansichtswürfel: Blick auf jede Fläche dreht deren Normale zum Betrachter; Klick auf Fläche/Ecke trifft.
- E4 3D-Modell aus den Eingaben (rohr3d): Wände, Stirnflächen, Konturlinien mit Merkmal; Gehrung schräg.
- E5 Rahmen: Menüband (Reiter, Knöpfe), Ansichten 3D/Skizze/Beides, Tabelle ein/aus, Kacheln, Zähler der
  Prüfmeldungen, Modell aus den Eingaben bzw. STEP-Modell, Klick im 3D wählt die Kontur.
- E6 Eigenschaften: Felder der gewählten Kontur schreiben in die Tabelle (Rechnung L/2, Muster 3x25), Ende und
  Teil, Einfügen, Duplizieren (ohne Messwerte), Entfernen; Blech: Kontur und Biegung.
- E7 Maßbilder und Menüband zeichnen ohne Fehler (alle Konturarten).

Aufruf: python tests/test_editor_ausbau.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import durchdringung as dd, schneidweg as sw  # noqa: E402


def ok(t):
    print("OK    ", t)


Q = dd.Querschnitt
# ------------------------------------------------------------------ E1 Durchdringung
for d_, D_ in ((40, 60), (60, 60), (33.7, 48.3)):
    assert abs(dd.ende(Q("rund", d_), Q("rund", D_))["laenge"] - sw.sattel(d_, D_)) < 0.01
assert abs(dd.ende(Q("rechteck", 40, 40), Q("rechteck", 60, 60))["laenge"] - 160) < 1e-6
e = dd.ende(Q("rechteck", 40, 40), Q("rechteck", 500, 500), alpha=45)
assert abs(e["laenge"] - (2 * 40 / math.cos(math.radians(45)) + 80)) < 1e-6 and abs(e["tiefe"] - 40) < 1e-6
q = Q("rechteck", 40, 60, 4)
umfang = sum(math.dist(a, b) for a, b in zip(q.umriss(), q.umriss()[1:] + q.umriss()[:1]))
assert abs(umfang - (2 * (40 + 60) - 8 * 4 + 2 * math.pi * 4)) < 0.01
mit = dd.ende(Q("rund", 30), Q("rund", 60), versatz=10)["laenge"]
assert mit > sw.sattel(30, 60)                       # mit Versatz steiler: längere Kurve
for falsch in (dict(rohr=Q("rund", 60), gegen=Q("rund", 40)), dict(rohr=Q("rund", 40), gegen=Q("rund", 60), versatz=15)):
    try:
        dd.ende(**falsch)
        raise AssertionError(falsch)
    except ValueError as f:
        assert "Gegenrohr" in str(f)
b = dd.durchbruch(Q("rund", 60), Q("rund", 40), durchgehend=True)
assert b["einstiche"] == 2 and abs(b["laenge"] - 2 * sw.sattel(40, 60)) < 0.01 and abs(b["huelle"] - 40) < 0.01
ok("E1 Durchdringung: Sattel wie schneidweg.sattel, Rechteck, schräg, Versatz, Fehler, Durchbruch zwei Wände")

# ------------------------------------------------------------------ E2 Rechenfelder
from rohrlaser import rechenfeld as rf  # noqa: E402

assert rf.auswerten("L/2", {"L": 1960}) == 980 and rf.auswerten("12,5 × 2") == 25 and rf.auswerten("") is None
assert abs(rf.auswerten("(1960 − 2x25) / 3") - 1910 / 3) < 1e-9 and rf.auswerten("-5+2") == -3
for schlecht in ("__import__('os')", "2**10", "abs(3)", "L/0", "X+1", "1;2"):
    try:
        rf.auswerten(schlecht, {"L": 1})
        raise AssertionError(schlecht)
    except ValueError:
        pass
assert rf.muster("3x25") == (3, 25.0) and rf.muster("4 × 12,5") == (4, 12.5) and rf.muster("25") is None
assert rf.zahl_text(12.5) == "12,5" and rf.zahl_text(3.0) == "3"
ok("E2 Rechenfelder: Komma, ×, Klammern, Größen; Muster 3x25; alles andere abgelehnt")

# ------------------------------------------------------------------ E3 Ansichtswürfel
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansichtswuerfel as aw  # noqa: E402
from rohrlaser.ansicht3d import _drehung  # noqa: E402

for name, n in aw.FLAECHEN:
    g, k = aw.blick_auf(n)
    m = _drehung(g, k)
    z = sum(m[2][i] * n[i] for i in range(3))
    assert z > (0.99 if name not in ("oben", "unten") else 0.99 * math.cos(1.5708 - aw.NICK_MAX)), (name, z)
assert aw.blick_auf((-1, 0, 0)) == (0.0, 0.0)                 # vorne = Knopf „Vorn“
flaechen, bild = aw.flaechen_bild(*aw.blick_auf((-1, 0, 0)))
assert [f[0] for f in flaechen] == ["vorne"]
g, k = -0.45, 0.45
flaechen, bild = aw.flaechen_bild(g, k)
for name, n, ecken, _ in flaechen:
    mx, my = sum(e[0] for e in ecken) / 4, sum(e[1] for e in ecken) / 4
    assert aw.treffer(g, k, mx, my) == n, name
px, py, _ = bild((-1, 1, -1))
assert aw.treffer(g, k, px + 1, py) == (-1, 1, -1)              # Ecke vorne-oben an Ende A
ok("E3 Ansichtswürfel: jede Fläche zum Betrachter, Treffer Fläche und Ecke")

# ------------------------------------------------------------------ E4 3D-Modell aus den Eingaben
from rohrlaser import ansicht3d, rohr3d  # noqa: E402

QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")
eing = dict(a=dict(winkel=45, achse="über Höhe"), b={},
            konturen=[dict(art=sw.BOHRUNG, anzahl=2, d=10, x=100, abstand=50),
                      dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="vorne"),
                      dict(art=sw.GRAVUR, anzahl=1, laenge=20, x=400)])
n = rohr3d.netz(eing, QR, 500)
assert set(n["t"]) == {"A", "I", "EA", "EB"} and n["eingaben"] is True
assert n["li"]["K"] == ["kontur:0", "kontur:0", "kontur:1"] and n["li"]["G"] == ["kontur:2"]
assert n["li"]["EA"] == ["ende:a"] and n["li"]["EB"] == ["ende:b"]
mo = ansicht3d.Modell(n)
assert abs(mo.min[2]) < 1e-6 and abs(mo.max[2] - 500) < 1e-6 and abs(mo.max[1] - 20) < 1e-6
za = [n["l"]["EA"][0][i + 2] for i in range(0, len(n["l"]["EA"][0]), 3)]
assert abs(max(za) - min(za) - 40) < 0.01                   # Gehrung 45° über Höhe 40: 40 mm tief
lang = [n["l"]["K"][2][i:i + 3] for i in range(0, len(n["l"]["K"][2]), 3)]
assert all(abs(p[0] + 20.4) < 0.01 for p in lang)           # Langloch vorne: X = −u, 0,4 über der Wand
rr = rohr3d.netz(dict(a=dict(sattel=60), b={}, konturen=[]), dict(form="Rundrohr", a=40, wand=2), 300)
assert set(rr["t"]) == {"A", "I", "EA", "EB"}
u = rohr3d.netz(eing, dict(form="U-Profil", a=80, b=45, wand=6), 500)
assert "I" not in u["t"] and {"A", "EA", "EB"} <= set(u["t"])
assert rohr3d.netz(eing, QR, 0) is None
ok("E4 3D-Modell aus den Eingaben: Wände, Stirnflächen, Linien mit Merkmal, Gehrung, Rund- und U-Profil")

# ------------------------------------------------------------------ E5 Rahmen
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.editor_ansicht import BEIDES, D3, SKIZZE  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
kopf = dict(maschine="T11", stange=6000)
p = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10,
         technik=json.dumps(dict(eing, quelle=sw.QUELLE)))
d = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], kopf, k, db.tabellen(), db)
ed = d.editor
assert set(ed.band.seiten) == {"Konstruktion", "Ansicht", "Ausgabe"}
for text in ("Rückgängig", "Bohrung", "Langloch", "Rechteck", "Weitere", "Knickrahmen", "3D", "Beides", "Tabelle",
             "Messen", "Zeichnung als PDF", "STEP neu einlesen", "Duplizieren"):
    assert ed.band.knopf(text) is not None, text
assert not d.kontur_leiste.isVisible() and d.bilder is ed.ansichten
ed.modus_setzen(D3)
assert ed.ansichten.modus == D3 and ed.modus_knoepfe[D3].isChecked() and not ed.modus_knoepfe[BEIDES].isChecked()
assert db.einstellung("editor_ansicht") == D3
ed.modus_setzen(SKIZZE)
assert ed.ansichten.currentWidget() is d.skizze
ed.messen_knopf.setChecked(True)
assert ed.ansichten.modus == D3 and d.ansicht3d.ansicht.messen
ed.messen_knopf.setChecked(False)
ed.modus_setzen(BEIDES)
ed.tabelle_zeigen(False)
assert not ed.tabelle_knopf.isChecked() and db.einstellung("editor_tabelle") is False
ed.tabelle_zeigen(True)
ed.band.einklappen(True)
assert db.einstellung("editor_band_zu") is True and ed.band.eingeklappt
ed.band.einklappen(False)
ed.aktualisieren()
titel = [kc.titel.text() for kc in ed.leiste_unten.kacheln if not kc.isHidden()]
assert titel[:3] == ["Schneidweg", "Einstiche", "Schneidzeit"], titel
assert ed.leiste_unten.kacheln[0].wert.text() == f"{d.ergebnis['felder']['schneidweg']:.1f} mm".replace(".", ",")
from rohrlaser import dfm  # noqa: E402
from rohrlaser.editor_ergebnis import zaehler_text  # noqa: E402

assert zaehler_text([]) == "✓ keine Prüfmeldungen"
assert zaehler_text([dfm.FEHLER, dfm.WARNUNG, dfm.WARNUNG, dfm.HINWEIS]) == "✕ 1 Fehler · ! 2 Warnungen · i 1 Hinweis"
assert not ed.meldung_bereich.isVisibleTo(d)
ed.leiste_unten.zaehler.setChecked(True)
assert ed.meldung_bereich.isVisibleTo(d)
# Modell aus den Eingaben: Klick auf die Linie einer Kontur wählt sie
a = d.ansicht3d.ansicht
assert a.netz.get("eingaben") and not ed.step_knopf.isEnabled()
a.resize(900, 400)
nr = next(i for i, kn in enumerate(a.modell.linien_id) if kn == "kontur:1")
pa, pb = a.bildpunkt()(a.modell.linien[nr][0]), a.bildpunkt()(a.modell.linien[nr][1])
ed.waehlen("teil")
a.klicken((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
assert ed.gewaehlt == "kontur:1" and a.markiert == {"kontur:1"}
# STEP-Modell: umschaltbar, sobald ein Netz der Messung da ist
step_netz = dict(p=[20, 20, 0, -20, 20, 0, -20, 20, 500, 20, 20, 500], t={"A": [0, 1, 2, 0, 2, 3]}, l={})
ed.step_netz = step_netz
ed.modell_setzen(True)
assert a.netz is step_netz and ed.step_knopf.isChecked()
ed.modell_setzen(False)
assert a.netz.get("eingaben")
ok("E5 Rahmen: Menüband, Ansichten 3D/Skizze/Beides gemerkt, Tabelle ein/aus, Kacheln, Zähler, Modell + Klick im 3D")

# ------------------------------------------------------------------ E6 Eigenschaften
ei = ed.eigenschaften
ed.waehlen("kontur:1")
assert ei.mid == "kontur:1" and "Langloch" in ei.titel.text()
f = ei.felder["Länge l"]
f.setText("2 × 20")
f.uebernehmen()
assert d.tabelle.item(1, 2).text() == "40" and d.eingaben()["konturen"][1]["l"] == 40
f = ei.felder["Lage ab Ende A"]
f.setText("L/2")
f.uebernehmen()
assert d.eingaben()["konturen"][1]["x"] == 250
f.setText("abc")
f.uebernehmen()
assert f.fehler and d.eingaben()["konturen"][1]["x"] == 250
ed.waehlen("kontur:0")
f = ei.felder["Abstand Muster"]
f.setText("3x25")
f.editingFinished.emit()
assert d.eingaben()["konturen"][0]["anzahl"] == 3 and d.eingaben()["konturen"][0]["abstand"] == 25
ei.felder["Seite"].setCurrentText("90° vorne")
ei.felder["Seite"].activated.emit(0)
assert d.eingaben()["konturen"][0].get("seite") == "vorne"
# Ende und Teil
ed.waehlen("ende:b")
assert "Endschnitt" in ei.titel.text() and "Winkel über Breite" not in ei.felder
ei.felder["Gehrungswinkel"].setText("30")
ei.felder["Gehrungswinkel"].uebernehmen()
assert d.winkel["b"].value() == 30
ed.waehlen("teil")
ei.felder["Gravur je Teil"].setText("12,5")
ei.felder["Gravur je Teil"].uebernehmen()
assert d.gravur.value() == 12.5
# Einfügen, Duplizieren (ohne Messwerte), Entfernen
n0 = d.tabelle.rowCount()
ed.kontur_einfuegen(sw.RECHTECK)
assert d.tabelle.rowCount() == n0 + 1 and ed.gewaehlt == f"kontur:{n0}" and "Rechteck" in ei.titel.text()
d.eingaben_setzen(dict(d.eingaben(), konturen=d.eingaben()["konturen"] +
                       [dict(art=sw.BOHRUNG, anzahl=1, d=8, x=50, gemessen=25.1)]), mit_messung=True)
r = d.tabelle.rowCount() - 1
assert d.eingaben()["konturen"][r].get("gemessen") == 25.1
assert ed.duplizieren(r) and d.tabelle.rowCount() == r + 2
assert d.eingaben()["konturen"][r + 1].get("gemessen") is None and d.eingaben()["konturen"][r + 1]["d"] == 8
assert ed.entfernen(r + 1) and d.tabelle.rowCount() == r + 1 and ed.gewaehlt is None
ed.waehlen(f"kontur:{r}")
ed.aktualisieren()
assert ei.mid == f"kontur:{r}"
# Blech: Kontur und Biegung
bd = BlechDialog(None, db)
be = bd.editor
bd.art.setCurrentText("Kantteil")
bd._vorlage(bd.vorlage.findText("U-Profil"))
be.kontur_einfuegen(sw.BOHRUNG)
assert be.gewaehlt == "kontur:0"
be.eigenschaften.felder["Ø d"].setText("6,6")
be.eigenschaften.felder["Ø d"].uebernehmen()
be.eigenschaften.felder["Mitte x"].setText("40")
be.eigenschaften.felder["Mitte x"].uebernehmen()
assert bd.eingaben()["konturen"][0]["d"] == 6.6 and bd.eingaben()["konturen"][0]["x"] == 40
be.aktualisieren()
be.waehlen("biegung:1")
assert "Biegung B2" in be.eigenschaften.titel.text()
be.eigenschaften.felder["Biegewinkel danach"].setText("45")
be.eigenschaften.felder["Biegewinkel danach"].uebernehmen()
assert bd.eingaben()["schenkel"][1]["winkel"] == 45
be.waehlen("teil")
assert "Dicke" in be.eigenschaften.felder and "Kantlänge" in be.eigenschaften.felder
ok("E6 Eigenschaften: Kontur (Rechnung, Muster 3x25, Seite), Ende, Teil, Einfügen/Duplizieren/Entfernen, Blech")

# ------------------------------------------------------------------ E7 Zeichnen
from rohrlaser import massbild  # noqa: E402

for art in sw.ARTEN:
    pm = massbild.bild(art)
    assert not pm.isNull() and pm.width() == 2 * massbild.BREITE
d.resize(1366, 728)
d.show()
app.processEvents()
assert d.width() <= 1366 and d.height() <= 728, (d.width(), d.height())
d.grab()
bd.resize(1366, 728)
bd.show()
app.processEvents()
assert bd.width() <= 1366 and bd.height() <= 728, (bd.width(), bd.height())
bd.grab()
ok("E7 Maßbilder aller Konturarten; Rohr- und Blech-Editor passen auf 1366 × 728")
print("Alle Tests Editor-Ausbau bestanden.")
