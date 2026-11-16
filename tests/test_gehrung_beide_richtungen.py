"""Gehrung im 3D-Editor in beide Richtungen (Patrick 16.11.2026: „Gerungen gehen nur in 1 Richtung“).

Vorher stellte der Griff an der Schnittebene (und Pfeil hoch/runter) nur 0 … 79,9° auf der Seite, die „automatisch“
als längste annimmt; über 0° hinaus blieb das Ende gerade. Jetzt:
R1 Griff über die Spitze hinaus ziehen kippt die Gehrung auf die Gegenseite (längste Seite +180°), zurückziehen
   stellt die ursprüngliche Richtung (auch „automatisch“) wieder her; ein Rückgängig-Schritt für den ganzen Zug
R2 Pfeil runter unter 0° kippt ebenso
R3 Rechtsklick: „Gehrung umdrehen“ und „Längste Seite“ oben/rechts/unten/links; „gekippt über“ passt dazu
R4 3D-Modell: die längste Seite liegt wirklich auf der gewählten Seite (Rechteckrohr, beide Achsen, beide Enden)
R5 Rundrohr kippt in jede Richtung; Sattel/Gegenrohr und zweiachsig bleiben ohne Umdrehen
K1 Konturen (Patrick 16.11.2026: „Konturen werden komisch dargestellt“): im Software-Zeichnen schien die Lochwand
   einer Kontur auf der Rückseite als roter Strich durch die vordere Wand (Sortierung nach der Dreiecksmitte); jetzt
   liegt sie unter den Flächen und ist nur durchs Loch zu sehen

Aufruf: python tests/test_gehrung_beide_richtungen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import editor_griffe as eg, rohr3d, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()


def ok(t):
    print("OK    ", t)


def dialog(pid, eing, L=500):
    p = dict(profil_id=pid, werkstoff_id="S235-10219", laenge=L, stueck=1,
             technik=json.dumps(dict(eing, quelle=sw.QUELLE)))
    d = SchneidwegDialog(None, p, k.profile[pid], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
    d.resize(1600, 1000)
    d.show()
    app.processEvents()
    d.editor.modus_setzen("3D")
    app.processEvents()
    return d


def laengste_seite(d, s, L=500):
    """Aus dem 3D-Netz: Richtung (0 oben, 90 rechts, 180 unten, 270 links von Ende A) der Außenecke, an der das Teil
    an Ende s am weitesten hinausragt."""
    e = d.eingaben()
    netz = rohr3d.netz(sw.mit_angenommener_richtung(e, d.profil), d.profil, L)
    f = netz["p"]                                    # flach, je Punkt rohr3d._xyz: (−u, v, x)
    pk = [f[i:i + 3] for i in range(0, len(f), 3)]
    xs = [p[2] for p in pk]
    ziel = min(xs) if s == "a" else max(xs)
    spitze = [p for p in pk if abs(p[2] - ziel) < 1e-3]
    u = sum(-p[0] for p in spitze) / len(spitze)
    v = sum(p[1] for p in spitze) / len(spitze)
    return round(math.degrees(math.atan2(u, v))) % 360


def ende_griff(d, s):
    w, a = d.editor.werkzeug, d.ansicht3d.ansicht
    d.editor.waehlen(f"ende:{s}")
    a.grab()
    return w, next(x for x in w._griffe if x["art"] == "ende" and x["seite"] == s)


# ------------------------------------------------------------------ R1 Griff über die Spitze hinaus
d = dialog("QR 40x40x3", dict(a=dict(winkel=30, achse="über Höhe"), b={}, konturen=[]))
assert d._richtung_wert("a") is None
r0 = eg.richtung_jetzt(d, "a")
w, g = ende_griff(d, "a")
schritte = d.editor.verlauf.count()
w.druck(g["punkt"], Qt.LeftButton)
w.ziehen(g["punkt"] - g["richtung"] * 60)          # Abstand 40·tan30 = 23 mm, 60 mm zurück → −37 mm: andersherum
assert "andersherum" in w.live, w.live
assert d.winkel["a"].value() == 43 and d._richtung_wert("a") == (r0 + 180) % 360, (d.winkel["a"].value(),
                                                                                   d._richtung_wert("a"))
w.ziehen(g["punkt"] - g["richtung"] * 5)           # wieder auf der alten Seite: Richtung wieder „automatisch“
assert d._richtung_wert("a") is None and d.winkel["a"].value() == 24, (d._richtung_wert("a"), d.winkel["a"].value())
w.ziehen(g["punkt"] - g["richtung"] * 60)
w.loslassen()
assert d.editor.verlauf.count() == schritte + 1 and d._richtung_wert("a") == (r0 + 180) % 360
d.editor.verlauf.undo()
assert d._richtung_wert("a") is None and d.winkel["a"].value() == 30
d.editor.verlauf.redo()
assert d._richtung_wert("a") == (r0 + 180) % 360 and d.winkel["a"].value() == 43
ok("R1 Griff über die Spitze hinaus kippt die Gehrung auf die Gegenseite, zurück wieder automatisch, ein Schritt")

# ------------------------------------------------------------------ R2 Pfeil runter unter 0°
d = dialog("QR 40x40x3", dict(a={}, b=dict(winkel=1, achse="über Höhe"), konturen=[]))
d.editor.waehlen("ende:b")
w = d.editor.werkzeug
r0 = eg.richtung_jetzt(d, "b")
assert w.taste(QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier)) and d.winkel["b"].value() == 0
assert w.taste(QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.ShiftModifier))
assert d.winkel["b"].value() == 10 and eg.richtung_jetzt(d, "b") == (r0 + 180) % 360
ok("R2 Pfeil runter: 1° → gerade → 10° auf der Gegenseite")

# ------------------------------------------------------------------ R3 Kontextmenü, R4 längste Seite im 3D
d = dialog("RE 60x40x3" if "RE 60x40x3" in k.profile else next(p for p, v in k.profile.items()
                                                                 if v.get("form") == "Rechteckrohr"),
           dict(a=dict(winkel=30, achse="über Höhe"), b=dict(winkel=20, achse="über Breite"), konturen=[]))
texte = [x.text() for x in d.editor.kontextmenue("ende:a").actions()]
assert "Gehrung umdrehen (andere Seite länger)" in texte and "Längste Seite (Gehrungsrichtung)" in texte, texte
for s in ("a", "b"):
    vorher = laengste_seite(d, s)
    assert vorher == round(eg.richtung_jetzt(d, s)) % 360, (s, vorher, eg.richtung_jetzt(d, s))
    m = d.editor.kontextmenue(f"ende:{s}")
    next(x for x in m.actions() if x.text().startswith("Gehrung umdrehen")).trigger()
    assert laengste_seite(d, s) == (vorher + 180) % 360, (s, laengste_seite(d, s), vorher)
    for text, grad in sw.RICHTUNGEN.items():
        if grad is None:
            continue
        m = d.editor.kontextmenue(f"ende:{s}")
        sm = next(x.menu() for x in m.actions() if x.text().startswith("Längste Seite"))
        next(x for x in sm.actions() if x.text() == text).trigger()
        assert d._richtung_wert(s) == grad and laengste_seite(d, s) == grad, (s, grad, laengste_seite(d, s))
        ueber_a = (grad % 180 == 90) == bool(d.qs.a_waagrecht)
        assert d.achse[s].currentText() == sw.ACHSEN[0 if ueber_a else 1], (s, grad, d.achse[s].currentText())
ok("R3/R4 Kontextmenü: umdrehen und längste Seite oben/rechts/unten/links, das 3D folgt, „gekippt über“ passt")

# ------------------------------------------------------------------ R5 Rundrohr, Sonderfälle
rr = next(p for p, v in k.profile.items() if v.get("form") == "Rundrohr")
d = dialog(rr, dict(a=dict(winkel=30), b={}, konturen=[]))
eg.gehrung_umdrehen(d, "a")
assert d._richtung_wert("a") == 180 and laengste_seite(d, "a") == 180
d.editor.waehlen("ende:a")
assert d.editor.werkzeug.taste(QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier)) and d.winkel["a"].value() == 31
d = dialog("QR 40x40x3", dict(a=dict(winkel=20, achse=sw.ACHSE_ZWEI, winkel_h=20, winkel_b=10), b={}, konturen=[]))
assert not eg.umkehrbar(d, "a")
assert "Gehrung umdrehen (andere Seite länger)" not in [x.text() for x in d.editor.kontextmenue("ende:a").actions()]
ok("R5 Rundrohr dreht frei, zweiachsig ohne Umdrehen")

# ------------------------------------------------------------------ K1 Lochwand nicht durch die Wand
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from rohrlaser import ansicht3d  # noqa: E402

RE = dict(form="Rechteckrohr", a=60, b=40, wand=3, profil_id="RE 60x40x3", r_aussen=6)


def rote_punkte(seite):
    e = dict(a={}, b={}, konturen=[dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=400, seite=seite)])
    mo = ansicht3d.Modell(rohr3d.netz(e, RE, 900))
    bild = QImage(1700, 600, QImage.Format_RGB32)
    bild.fill(0xFFFFFF)
    p = QPainter(bild)
    ansicht3d.zeichnen(p, mo, 1700, 600, -0.45, 0.45)       # Ausgangsansicht: von oben vorn
    p.end()
    n = 0
    for y in range(0, 600, 2):
        for x in range(300, 1400, 2):          # ohne die Enden (Anfangsschnitt orange)
            c = bild.pixelColor(x, y)
            n += c.red() > 170 and c.green() < 130 and c.blue() < 130
    return n


assert rote_punkte("oben") > 20                                 # sichtbare Kontur: rot
assert rote_punkte("unten") == 0, rote_punkte("unten")         # Rückseite: nichts scheint durch
ok("K1 Kontur auf der Rückseite scheint nicht mehr durch die Wand (Software-Zeichnen)")
print("OK: Gehrung im 3D-Editor in beide Richtungen, Konturen ohne Durchscheinen")
