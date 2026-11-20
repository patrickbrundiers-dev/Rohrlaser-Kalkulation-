"""Explosionsansicht erweitern (Auftrag Patrick 20.11.2026).

E1 Stand: speichern/lesen (Ungültiges fällt auf die Vorgabe), aktiv nur mit Stärke oder eigenem Versatz
E2 Richtungen: frei, waagrecht (ohne Hochachse), nur X; fixierte Teile bleiben stehen, eigener Versatz kommt dazu
E3 Rückgängig/Wiederholen der Änderungen von Hand
E4 Ebenen: Teile einer Unterbaugruppe gehen zusammen (enger beieinander als ohne Ebenen)
E5 Überlappung vermeiden: sich schneidende Hüllen werden auseinandergeschoben
E6 Ansicht: nur Anzeige (Netz und volles Modell unverändert, gleich viele Dreiecke), Verbindungslinien/Nummern
E7 Teile mit der Maus ziehen (frei und nur X), fixierte nicht
E8 Animation auseinander/zusammen/Montagereihenfolge, Pause
E9 Explosionsfenster: Ansicht mit Namen und Kamera speichern/zeigen/löschen (in den Daten der Baugruppe),
   Explosionszeichnung PDF/PNG mit Stückliste, in die Angebotsakte
E10 TeileKopplung: Positionsnummern wie in der Stückliste, Beschriftung, Ebenen aus der Unterbaugruppe
E11 Baugruppe und Satz speichern die Ansichten, Menü „Explosion einstellen …“ in allen Editoren

Aufruf: python tests/test_explosion.py
"""
import copy
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, ansicht3d_leiste, explosion as ex, explosion_dialog as ed, rohr3d  # noqa: E402
from rohrlaser import schneidweg as sw  # noqa: E402
from rohrlaser.auswahl3d import TeileKopplung  # noqa: E402

ansicht3d.renderer_setzen("Software")
fehler = []


def ok(bedingung, text):
    print(("OK     " if bedingung else "FEHLER ") + text, flush=True)
    if not bedingung:
        fehler.append(text)


# E1
s = ex.Stand()
ok(not s.aktiv() and s.als_dict()["faktor"] == 0.0, "E1 neuer Stand: keine Explosion")
s.faktor, s.richtung, s.versatz, s.fix = 1.25, "h", {"teil:1": [10.0, 0.0, -5.0]}, {"teil:0"}
s2 = ex.Stand().aus_dict(s.als_dict())
ok(s2.als_dict() == s.als_dict() and s2.aktiv(), "E1 Stand speichern und wieder lesen: gleich")
s3 = ex.Stand().aus_dict(dict(faktor="x", richtung="quer", versatz={"a": [1, "b"], "b": [float("nan"), 0, 0]},
                              beschriftung="?", fix=[None, "teil:2"]))
ok(s3.faktor == 0.0 and s3.richtung == "frei" and not s3.versatz and s3.beschriftung == "Positionsnummer"
   and s3.fix == {"teil:2"}, "E1 Ungültiges fällt auf die Vorgabe zurück")
ok(ex.Stand().aus_dict(dict(faktor=99)).faktor == ex.FAKTOR_MAX, "E1 Stärke höchstens FAKTOR_MAX")
ok(ex.Stand().aus_dict(dict(versatz={"teil:0": [1, 0, 0]})).aktiv(), "E1 nur eigener Versatz: Explosion aktiv")

# E2
mitten = {"a": (-100.0, 50.0, 0.0), "b": (100.0, -50.0, 0.0), "c": (0.0, 0.0, 300.0)}
huellen = {k: (tuple(c - 5 for c in m), tuple(c + 5 for c in m)) for k, m in mitten.items()}
g = (0.0, 0.0, 100.0)
s = ex.Stand()
s.faktor, s.ueberlappung = 1.0, False
w = ex.wege(mitten, huellen, g, s)
ok(w["a"] == (-100.0, 50.0, -100.0) and w["c"] == (0.0, 0.0, 200.0), f"E2 frei: Weg aus der Mitte {w['a']}")
s.richtung = "h"
w = ex.wege(mitten, huellen, g, s)
ok(all(abs(v[ex.SENKRECHT]) < 1e-9 for v in w.values()) and abs(w["a"][0] + 100) < 1e-9,
   f"E2 waagrecht: nichts entlang der Hochachse {w['a']}")
s.richtung = "x"
w = ex.wege(mitten, huellen, g, s)
ok(all(abs(v[1]) < 1e-9 and abs(v[2]) < 1e-9 for v in w.values()), "E2 nur X")
s.richtung, s.fix, s.versatz = "frei", {"a"}, {"b": [0.0, 0.0, 7.0]}
w = ex.wege(mitten, huellen, g, s)
ok(w["a"] == (0.0, 0.0, 0.0) and abs(w["b"][2] - (-100.0 + 7.0)) < 1e-9, "E2 fixiert bleibt, eigener Versatz dazu")
w = ex.wege(mitten, huellen, g, s, t=0.5)
ok(abs(w["c"][2] - 100.0) < 1e-9, "E2 Animation t = 0,5: halber Weg")

# E3
s = ex.Stand()
s.versatz_setzen(["a"], [5, 0, 0])
s.verschieben(["a"], [1, 2, 3])
ok(s.versatz["a"] == [6, 2, 3], "E3 setzen und verschieben")
s.rueckgaengig()
ok(s.versatz["a"] == [5.0, 0.0, 0.0] and s.kann_vor(), "E3 Rückgängig")
s.wiederholen()
ok(s.versatz["a"] == [6.0, 2.0, 3.0], "E3 Wiederholen")
s.fixieren(["a"])
ok(s.verschieben(["a"], [1, 0, 0]) == 0 and s.versatz["a"] == [6.0, 2.0, 3.0], "E3 fixiertes Teil lässt sich nicht verschieben")
s.zuruecksetzen()
ok(not s.versatz and not s.fix and s.rueckgaengig() and s.fix == {"a"}, "E3 Alles zurücksetzen, rückgängig machbar")

# E4
mitten4 = {"a": (200.0, 0.0, 0.0), "b": (220.0, 0.0, 0.0), "c": (-200.0, 0.0, 0.0)}
h4 = {k: (tuple(c - 1 for c in m), tuple(c + 1 for c in m)) for k, m in mitten4.items()}
s = ex.Stand()
s.faktor, s.ueberlappung = 1.0, False
gr = {"a": "U1", "b": "U1"}.get
mit = ex.wege(mitten4, h4, (0.0, 0.0, 0.0), s, gr)
s.ebenen = False
ohne = ex.wege(mitten4, h4, (0.0, 0.0, 0.0), s, gr)
abst = (mitten4["b"][0] + mit["b"][0]) - (mitten4["a"][0] + mit["a"][0])
abst_ohne = (mitten4["b"][0] + ohne["b"][0]) - (mitten4["a"][0] + ohne["a"][0])
ok(abst < abst_ohne and abs(mit["a"][0] - mit["b"][0]) < abs(ohne["a"][0] - ohne["b"][0]),
   f"E4 Unterbaugruppe geht zusammen auseinander (Abstand {abst:.0f} statt {abst_ohne:.0f} mm)")

# E5
mitten5 = {"a": (0.0, 0.0, 0.0), "b": (1.0, 0.0, 0.0)}
h5 = {"a": ((-50.0, -50.0, -50.0), (50.0, 50.0, 50.0)), "b": ((-49.0, -50.0, -50.0), (51.0, 50.0, 50.0))}
s = ex.Stand()
s.faktor = 1.0
w5 = ex.wege(mitten5, h5, (0.5, 0.0, 0.0), s)
lk = h5["a"][1][0] + w5["a"][0]
rk = h5["b"][0][0] + w5["b"][0]
ok(rk >= lk - 1e-6, f"E5 Überlappung vermeiden: Hüllen getrennt ({lk:.1f} ≤ {rk:.1f})")
s.ueberlappung = False
w5o = ex.wege(mitten5, h5, (0.5, 0.0, 0.0), s)
ok(h5["b"][0][0] + w5o["b"][0] < h5["a"][1][0] + w5o["a"][0], "E5 ohne: Teile schneiden sich noch")

# E6
QR = dict(form="Quadratrohr", a=40, b=40, wand=3)
netz = rohr3d.netz(sw.v_ergaenzen(dict(a={}, b={}, laenge=300, konturen=[]), QR), QR, 300)
LAGE = [0, 0, 0, 0, 0, 1, 1, 0, 0]
teile = [dict(netz, lage=[x, 0, 0] + LAGE[3:]) for x in (0, 100, 200)]
bg, _ = ansicht3d.baugruppe(teile)
bg_vorher = copy.deepcopy(bg)
d = ansicht3d.Ansicht3D()
d.resize(800, 500)
d.setzen(bg, "BG Test")
voll = d.voll
el = d.wahl.elemente()
ids = []
for k in el.koerper_von:
    if k not in ids:
        ids.append(k)
ok(len(ids) == 3, f"E6 drei Körper erkannt {ids}")
d.explo.versatz = {ids[0]: [0.0, 0.0, 250.0]}
d.explosion_anwenden()
ok(d.modell is not voll and len(d.modell.dreiecke) == len(voll.dreiecke) and d.voll is voll
   and d.modell.max[2] > voll.max[2] + 200, "E6 nur eigener Versatz: Teil verschoben, gleich viele Dreiecke")
ok(len(d.explo_pfeile) == 3 and "eigenem Versatz" in (d.anzeige_hinweis() or ""),
   f"E6 Verbindungslinien je Teil, Hinweis „{d.anzeige_hinweis()}“")
d.explo.versatz = {}
d.explosion_setzen(1.0)
bild_mit = d.grab().toImage()
d.explo.beschriftung, d.explo.linien = "Aus", False
d.update()
bild_ohne = d.grab().toImage()
ok(bild_mit != bild_ohne, "E6 Linien und Positionsnummern werden gezeichnet")
d.explo.beschriftung, d.explo.linien = "Positionsnummer", True
d.messen_setzen(True)
ok(not d.messen, "E6 Messen in der Explosion gesperrt")
ok(bg == bg_vorher, "E6 Netz unverändert (Lage = STEP)")

# E7
d.explosion_setzen(0)
d.explo.zuruecksetzen()
d.explosion_anwenden()
d.explo_ziehen, d.explo_achse = True, "frei"
bild = d.bildpunkt()
el = d.wahl.elemente()
nr = next(i for i, k in enumerate(el.koerper_von) if k == ids[2])
i, j, k, _, _ = d.voll.dreiecke[nr]
mitte = [sum(d.voll.punkte[x][c] for x in (i, j, k)) / 3 for c in range(3)]
px = bild(mitte)


def maus(art, x, y, knopf=Qt.LeftButton):
    e = QMouseEvent(art, QPointF(x, y), QPointF(x, y), knopf, knopf if art != QEvent.MouseButtonRelease else
                    Qt.NoButton, Qt.NoModifier)
    {QEvent.MouseButtonPress: d.mousePressEvent, QEvent.MouseMove: d.mouseMoveEvent,
     QEvent.MouseButtonRelease: d.mouseReleaseEvent}[art](e)


getroffen = d.explosion_koerper_bei(px[0], px[1])
maus(QEvent.MouseButtonPress, px[0], px[1])
maus(QEvent.MouseMove, px[0] + 40, px[1] - 30)
maus(QEvent.MouseButtonRelease, px[0] + 40, px[1] - 30)
v = d.explo.versatz.get(getroffen)
ok(getroffen is not None and v and any(abs(c) > 1 for c in v), f"E7 Teil {getroffen} gezogen: Versatz {v}")
p2 = d.bildpunkt()([mitte[c] + v[c] for c in range(3)])
ok(abs(p2[0] - px[0] - 40) < 3 and abs(p2[1] - px[1] + 30) < 3, f"E7 Teil folgt der Maus im Bild {px[:2]} -> {p2[:2]}")
ok(d.explo.kann_zurueck(), "E7 Ziehen ist rückgängig machbar")
d.explo.zuruecksetzen()
d.explo_achse = "x"
d.explosion_anwenden()
maus(QEvent.MouseButtonPress, px[0], px[1])
maus(QEvent.MouseMove, px[0] + 50, px[1] + 50)
maus(QEvent.MouseButtonRelease, px[0] + 50, px[1] + 50)
v = d.explo.versatz.get(getroffen) or [0, 0, 0]
ok(abs(v[0]) > 1 and abs(v[1]) < 1e-9 and abs(v[2]) < 1e-9, f"E7 nur entlang X: {v}")
d.explo.zuruecksetzen()
d.explo.fixieren([getroffen])
d.explosion_anwenden()
maus(QEvent.MouseButtonPress, px[0], px[1])
maus(QEvent.MouseMove, px[0] + 50, px[1])
maus(QEvent.MouseButtonRelease, px[0] + 50, px[1])
ok(not d.explo.versatz, "E7 fixiertes Teil bleibt stehen")
d.explo.zuruecksetzen()
d.explo_ziehen = False
d.explosion_anwenden()

# E8
d.explo.faktor = 1.0
ok(d.explosion_animieren("auseinander", 0.2) and d.explosion_laeuft() and d.explo_t == 0.0,
   "E8 Animation auseinander startet bei 0")
ok(not d.explosion_pause() and d.explosion_pause(), "E8 Pause und Weiter")
for _ in range(200):
    if not d.explosion_laeuft():
        break
    d._explo_schritt()
ok(not d.explosion_laeuft() and d.explo_t == 1.0 and d.explo.faktor == 1.0, "E8 auseinander fertig")
d.explosion_animieren("montage", 0.2)
zwischen = None
for n in range(500):
    if not d.explosion_laeuft():
        break
    d._explo_schritt()
    if n == 3:
        zwischen = d.explo.schritt
ok(not d.explosion_laeuft() and d.explo.faktor == 0.0 and d.modell is d.voll and zwischen is not None,
   "E8 Montagereihenfolge: Teil für Teil zusammen, am Ende Einbaulage")
ok(ex.reihenfolge({"a": (0, 0, 0), "b": (500, 0, 0), "c": (100, 0, 0)}, (0, 0, 0)) == ["b", "c", "a"],
   "E8 Reihenfolge von außen nach innen")

# E9
daten = {}
ed.ablage_einhaengen(d, daten)
dlg = ed.zeigen(d)
d.explo.faktor = 1.5
d.gier = 33.0
d.explosion_anwenden()
dlg.merken("Seite links")
ok(daten.get("explosionen") and daten["explosionen"][0]["name"] == "Seite links"
   and daten["explosionen"][0]["stand"]["faktor"] == 1.5 and daten["explosionen"][0]["kamera"]["gier"] == 33.0,
   "E9 Ansicht mit Namen und Kamera in den Daten gespeichert")
d.explo.faktor, d.gier = 0.3, 0.0
d.explosion_anwenden()
ok(dlg.laden("Seite links") and d.explo.faktor == 1.5 and d.gier == 33.0, "E9 gespeicherte Ansicht zeigen")
ok(d.explo.rueckgaengig() and d.explo.faktor == 0.3, "E9 Zeigen ist rückgängig machbar")
d.explo.faktor = 1.0
d.explosion_anwenden()
with tempfile.TemporaryDirectory() as tmp:
    pdf = ed.zeichnung_speichern(d, Path(tmp) / "z.pdf")
    png = ed.zeichnung_speichern(d, Path(tmp) / "z.png")
    ok(open(pdf, "rb").read(4) == b"%PDF" and os.path.getsize(png) > 5000, "E9 Explosionszeichnung PDF und PNG")
    ok(ed.in_akte_legen(d) is None, "E9 ohne Angebot: nichts in die Akte")
    d.explosion_akte = lambda: (tmp, "2026-00001")
    out = ed.in_akte_legen(d, "Seite links")
    ok(out and all(Path(p).exists() and "Angebotsakte" in p and "Technische_Daten" in p for p in out),
       f"E9 in die Angebotsakte gelegt: {[Path(p).name for p in out or []]}")
dlg.loeschen("Seite links")
ok(not daten["explosionen"], "E9 Ansicht gelöscht")

# E10
positionen = {"p1": dict(id="p1", pos="10", artikel="R-40", bezeichnung="Holm", werkstoff_id="S235",
                         profil_id="QR40x3", wand=3, stueck=2),
              "p2": dict(id="p2", pos="20", artikel="R-41", werkstoff_id="S235")}
koerper = [("p1", None, None), ("p2", None, None), ("p1", None, None)]
gewaehlt = []
kp = TeileKopplung(d, lambda: koerper, positionen.get, lambda: gewaehlt, lambda x: gewaehlt.__init__(x), "k",
                   gruppe=lambda pid: "U1" if pid == "p1" else None)
ok(d.explosion_nummer("k0") == "10" and d.explosion_nummer("k1") == "20", "E10 Positionsnummern aus der Stückliste")
ok(d.explosion_text("k0")[:2] == ["R-40", "Holm"] and "Wand: 3 mm" in d.explosion_text("k0"),
   f"E10 Beschriftung {d.explosion_text('k0')}")
ok(d.explosion_gruppe("k2") == "U1" and d.explosion_gruppe("k1") is None, "E10 Ebenen aus der Unterbaugruppe")
sl = ed.stueckliste(d)
ok([z["nr"] for z in sl] == ["10", "20"] and sl[0]["menge"] == 2 and sl[0]["profil"] == "QR40x3",
   f"E10 Stückliste der Zeichnung fasst gleiche Positionen zusammen {[(z['nr'], z['menge']) for z in sl]}")

# E11
q = (Path(ansicht3d.__file__).parent / "baugruppe_dialog.py").read_text(encoding="utf-8")
ok("ablage_einhaengen(self.ansicht3d.ansicht, lambda: self.bg" in q and "gruppe=self._explosion_gruppe" in q,
   "E11 Schweißbaugruppe: Ansichten in bg['explosionen'], Ebenen aus den Unterbaugruppen")
q = (Path(ansicht3d.__file__).parent / "satz3d.py").read_text(encoding="utf-8")
ok("ablage_einhaengen(" in q and '"explosionen": self.bg["explosionen"]' in q, "E11 Satz: Ansichten in den Satzdaten")
from PySide6.QtWidgets import QMenu  # noqa: E402
m = ansicht3d_leiste.explosion_menue(QMenu(), d)
texte = [a.text() for a in m.actions()]
ok(any(t.startswith("Explosion einstellen") for t in texte) and any("Explosionszeichnung" in t for t in texte),
   "E11 Menü Explosion: Einstellen und Explosionszeichnung (alle Editoren über ansicht_knoepfe)")
from rohrlaser import baugruppe  # noqa: E402
b = baugruppe.leer()
b["explosionen"] = [dict(name="A", stand=ex.Stand().als_dict(), kamera={})]
ok(baugruppe.lesen(baugruppe.speichern(b))["explosionen"][0]["name"] == "A", "E11 Baugruppe speichert die Ansichten")

print("\n" + (f"{len(fehler)} Fehler." if fehler else "Alle Prüfungen bestanden."))
sys.exit(1 if fehler else 0)
