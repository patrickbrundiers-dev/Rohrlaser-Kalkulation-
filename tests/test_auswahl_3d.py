"""3D-Auswahl in allen 3D-Fenstern gleich (CAD-Entwicklungsplan Paket 3, Patrick 12.11.2026). Die acht Testfälle
aus Abschnitt 7.3 des Plans und die Ergänzungen des Pakets.

A1 Körperauswahl: Teile einer Baugruppe (Kennung je Dreieck) und zusammenhängende Körper eines einzelnen Netzes
A2 Flächenauswahl: ebene und gewölbte Fläche mit Flächeninhalt
A3 Kantenauswahl (gerade Kante mit Länge, Kreis mit Durchmesser) und Punkt (Ecke)
A4 Mehrfachauswahl: Strg+Klick dazu/weg, Fenster nach rechts (ganz drin) und nach links (berührt), Filter
A5 Ausblenden und Isolieren, Alle einblenden; Rückgängig und Wiederholen der Sichtbarkeit
A6 Anzeige: Art des Elements unter der Maus und des Gewählten, Eigenschaften
B1 gleiche Bedienung in allen 3D-Fenstern: Leiste (Prüfdialog, Teilebaum, Schneidweg-Rechner), Schweißbaugruppe /
   Satz in 3D, Rohr- und Blech-Editor (Menüband und Rechtsklick-Menü)
B2 Auswahl über die Bauteilliste (Satz in 3D): Klick im 3D markiert die Zeile, Zeile markieren wählt den Körper;
   Bearbeitung mehrerer Körper: zwei im 3D gewählte Rohre -> Steckverbindung
B3 STEP-Prüfdialog: Körper der Baugruppe mit Name und Eigenschaften, Zeile der Liste folgt
B4 Rückgängig und Wiederholen einer Bearbeitung im Editor bei eingeschalteter Auswahl

Aufruf: python tests/test_auswahl_3d.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

import step_messen  # noqa: E402
from rohrlaser import auswahl3d as aw, step  # noqa: E402
from rohrlaser.ansicht3d import Ansicht3DMitKnoepfen, baugruppe, entpacken  # noqa: E402
from rohrlaser.ansicht3d_leiste import AUSWAHL, auswahl_menue  # noqa: E402
from rohrlaser.baugruppe_ansicht import BaugruppenAnsicht, teil_kennung  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.satz3d import TEIL  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-6):
    return abs(a - b) <= tol


def quader(dx, dy, dz, loch=None):
    """Netz eines Quaders (0…dx, 0…dy, 0…dz); loch = (x, y, Ø): Kreis-Kontur oben (netz 'l')."""
    p = [c for x in (0, dx) for y in (0, dy) for z in (0, dz) for c in (x, y, z)]
    t = [0, 1, 3, 0, 3, 2, 4, 6, 7, 4, 7, 5, 0, 4, 5, 0, 5, 1, 2, 3, 7, 2, 7, 6, 0, 2, 6, 0, 6, 4, 1, 5, 7, 1, 7, 3]
    netz = dict(p=[float(c) for c in p], t={"A": t}, l={})
    if loch:
        x, y, d = loch
        netz["l"]["K"] = [[c for s in range(49) for c in (x + d / 2 * math.cos(2 * math.pi * s / 48),
                                                          y + d / 2 * math.sin(2 * math.pi * s / 48), float(dz))]]
        netz["ln"] = {"K": [[0.0, 0.0, 1.0]]}
    return netz


def fenster(netz, titel="Test"):
    w = Ansicht3DMitKnoepfen()
    w.resize(900, 600)
    w.show()
    w.setzen(netz, titel)
    app.processEvents()
    return w


def pixel(a, punkt):
    x, y, _ = a.bildpunkt()(punkt)
    return x, y


def suchen(a, passt, schritt=6):
    """Erstes Pixel, an dem unter() ein Element liefert, für das passt(Element) gilt."""
    for x in range(10, a.width() - 10, schritt):
        for y in range(10, a.height() - 10, schritt):
            e = a.wahl.unter(x, y)
            if e is not None and passt(e):
                return x, y
    raise AssertionError("kein passendes Element im Bild")


# ------------------------------------------------------------------ A1 Körperauswahl
LAGE = [0, 0, 0, 0, 0, 1, 1, 0, 0]
teile = [dict(quader(100, 60, 40), lage=[x, 0, 0] + LAGE[3:]) for x in (0, 150, 300)]
bereiche = []
bg, _ = baugruppe(teile, bereiche=bereiche)
teil_kennung(bg, bereiche, [f"{TEIL}{i}" for i in range(3)])
bg["teile"] = True
w = fenster(bg, "Baugruppe")
a = w.ansicht
assert not a.wahl.an and w.leiste.auswahl.text() == AUSWAHL
w.leiste.auswahl.setChecked(True)                   # Knopf „Auswahl“ der gemeinsamen Leiste
assert a.wahl.an and a.hasMouseTracking()
namen = {f"{TEIL}0": "Pos. 10 Holm", f"{TEIL}1": "Pos. 20 Strebe", f"{TEIL}2": "Pos. 30 Fuß"}
a.wahl.koerper_name = namen.get
a.wahl.koerper_info = lambda k: ["Profil: QR 60x60x3"]
a.wahl.modell_neu()
el = a.wahl.elemente()
assert set(el.koerper) == set(namen) and all(len(v) == 12 for v in el.koerper.values()), el.koerper
x, y = suchen(a, lambda e: e["art"] == aw.KOERPER and e["id"] == f"{TEIL}1")
e = a.wahl.klick(x, y)
assert e["art"] == aw.KOERPER and aw.titel(e) == "Körper: Pos. 20 Strebe" and a.wahl.koerper_ids() == [f"{TEIL}1"]
# einzelnes Netz ohne Kennung: zusammenhängende Körper, Anbauteil für sich
einzel = quader(100, 60, 40)
anbau = quader(20, 20, 20)
basis = len(einzel["p"]) // 3
einzel["p"] += [c + (200 if i % 3 == 0 else 0) for i, c in enumerate(anbau["p"])]
einzel["t"]["AN"] = [basis + i for i in anbau["t"]["A"]]
w1 = fenster(einzel, "Teil mit Anbauteil")
a1 = w1.ansicht
a1.wahl.setzen(True, aw.KOERPER)
el1 = a1.wahl.elemente()
assert el1.namen == {"k0": "Teil", "a0": "Anbauteil"} and len(el1.koerper["k0"]) == 12, el1.namen
x, y = suchen(a1, lambda e: e["art"] == aw.KOERPER and e["id"] == "a0")
assert aw.titel(a1.wahl.klick(x, y)) == "Körper: Anbauteil"
ok("A1 Körperauswahl: Teil einer Baugruppe mit Name, im einzelnen Netz Teil und Anbauteil getrennt")

# ------------------------------------------------------------------ A2 Flächenauswahl
w2 = fenster(quader(100, 60, 40, loch=(50, 30, 20)), "Quader")
a2 = w2.ansicht
a2.wahl.setzen(True, aw.FLAECHE)
von, flaechen = a2.wahl.elemente().flaechen()
assert sorted(round(f["flaeche"]) for f in flaechen) == [2400, 2400, 4000, 4000, 6000, 6000]
assert all(f["typ"] == "eben" for f in flaechen)
x, y = suchen(a2, lambda e: e["art"] == aw.FLAECHE and nah(e["flaeche"], 6000, 1e-6))
e = a2.wahl.klick(x, y)
assert aw.titel(e) == "Fläche (eben): 6000,0 mm²" and nah(abs(e["n"][2]), 1) and "Normale" in a2.wahl.eigenschaften()[1]
assert a2.tafel.klartext().startswith("Fläche (eben): 6000,0 mm²")           # Eigenschaften in der Tafel im Bild
# gewölbte Fläche: Mantel eines Zylinders (Vieleck mit 48 Seiten), keine Körperkanten dazwischen
n = 48
zp = [c for s in range(n) for z in (0.0, 80.0) for c in (20 * math.cos(2 * math.pi * s / n),
                                                          20 * math.sin(2 * math.pi * s / n), z)]
zt = [i for s in range(n) for i in (2 * s, 2 * ((s + 1) % n), 2 * s + 1, 2 * s + 1, 2 * ((s + 1) % n),
                                    2 * ((s + 1) % n) + 1)]
w3 = fenster(dict(p=zp, t={"A": zt}, l={}), "Mantel")
a3 = w3.ansicht
a3.wahl.setzen(True, aw.FLAECHE)
_, fl3 = a3.wahl.elemente().flaechen()
assert len(fl3) == 1 and fl3[0]["typ"] == "gewölbt" and abs(fl3[0]["flaeche"] - math.pi * 40 * 80) < 15, fl3[0]
ok("A2 Flächenauswahl: sechs ebene Flächen mit Flächeninhalt und Normale, Zylindermantel als eine gewölbte Fläche")

# ------------------------------------------------------------------ A3 Kante und Punkt
a2.wahl.setzen(True, aw.KANTE)
x, y = pixel(a2, (50, 0, 40))                       # Mitte der oberen Längskante
e = a2.wahl.klick(x, y)
assert e["art"] == aw.KANTE and aw.titel(e) == "Kante (gerade): 100,00 mm", aw.titel(e)
assert any(z.startswith("Richtung") for z in a2.wahl.eigenschaften())
x, y = pixel(a2, (60, 30, 40))                      # auf dem Kreis der Bohrung (Ø 20 um 50/30)
e = a2.wahl.klick(x, y)
assert e["art"] == aw.KANTE and aw.titel(e) == "Kante (Kreis): Ø 20,00 mm", aw.titel(e)
assert any(z.startswith("Umfang: 62,83") for z in a2.wahl.eigenschaften()), a2.wahl.eigenschaften()
a2.wahl.setzen(True, aw.PUNKT)
x, y = pixel(a2, (100, 0, 40))
e = a2.wahl.klick(x, y)
assert e["art"] == aw.PUNKT and e["p"] == (100.0, 0.0, 40.0) and aw.titel(e) == "Punkt (Ecke)"
assert a2.wahl.klick(5, 5) is None and a2.wahl.gewaehlt == []               # Klick daneben hebt auf
ok("A3 Kantenauswahl: gerade Kante mit Länge, Kreis mit Durchmesser und Umfang; Punkt = Ecke")

# ------------------------------------------------------------------ A4 Mehrfachauswahl, Fenster, Filter
a2.wahl.setzen(True, aw.ALLES)
xf, yf = suchen(a2, lambda e: e["art"] == aw.FLAECHE)
a2.wahl.klick(xf, yf)
a2.wahl.filter = aw.KANTE
xk, yk = pixel(a2, (50, 0, 40))
a2.wahl.klick(xk, yk, dazu=True)
a2.wahl.filter = aw.PUNKT
xp, yp = pixel(a2, (100, 0, 40))
a2.wahl.klick(xp, yp, dazu=True)
assert a2.wahl.arten() == "1 Fläche, 1 Kante, 1 Punkt" and "gewählt: 1 Fläche, 1 Kante, 1 Punkt" in a2.wahl.status()
a2.wahl.klick(xp, yp, dazu=True)                    # Strg+Klick auf Gewähltes nimmt es wieder weg
assert a2.wahl.arten() == "1 Fläche, 1 Kante"
a2.wahl.klick(5, 5, dazu=True)                      # Strg+Klick daneben lässt die Auswahl stehen
assert len(a2.wahl.gewaehlt) == 2
# Fenster: nach rechts nur ganz Enthaltenes, nach links auch Berührtes
a.wahl.setzen(True, aw.KOERPER)
px = [pixel(a, q) for q in ((50, 30, 20), (200, 30, 20), (350, 30, 20))]      # Mitten der drei Körper
x0 = (px[0][0] + px[1][0]) / 2
a.wahl.fenster = (QPointF(0, 0), QPointF(a.width(), a.height()))
assert len(a.wahl.fenster_fertig()) == 3                                        # alles im Fenster
klein = (QPointF(px[1][0] - 3, px[1][1] - 3), QPointF(px[1][0] + 3, px[1][1] + 3))
a.wahl.fenster = klein
assert a.wahl.fenster_fertig() == []                                            # nach rechts: nichts ganz drin
a.wahl.fenster = (klein[1], klein[0])
assert [g["id"] for g in a.wahl.fenster_fertig()] == [f"{TEIL}1"]               # nach links: berührt
assert x0 and a.wahl.koerper_ids() == [f"{TEIL}1"]
# Filter: Kante trifft keine Fläche, Fläche keinen Punkt
a2.wahl.setzen(True, aw.KANTE)
assert a2.wahl.unter(xf, yf) is None or a2.wahl.unter(xf, yf)["art"] == aw.KANTE
a2.wahl.filter = aw.FLAECHE
assert a2.wahl.unter(xp, yp) is None or a2.wahl.unter(xp, yp)["art"] == aw.FLAECHE
a2.wahl.filter = aw.KANTE
assert len(a2.wahl.im_fenster(0, 0, a2.width(), a2.height())) == 13             # 12 Kanten + Kreis
a2.wahl.filter = aw.PUNKT
assert len(a2.wahl.im_fenster(0, 0, a2.width(), a2.height())) == 8
ok("A4 Mehrfachauswahl mit Strg (dazu/weg), Fenster nach rechts = ganz drin, nach links = berührt, Filter je Art")

# ------------------------------------------------------------------ A5 Ausblenden, Isolieren, Rückgängig
a.wahl.koerper_setzen([f"{TEIL}1"])
assert len(a.modell.dreiecke) == 36
assert a.wahl.ausblenden() == 1 and len(a.modell.dreiecke) == 24 and len(a.voll.dreiecke) == 36
assert a.wahl.versteckt == {f"{TEIL}1"} and a.wahl.gewaehlt == [] and "1 Körper ausgeblendet" in a.wahl.status()
assert all(a.wahl.unter(x, y) is None or a.wahl.unter(x, y)["id"] != f"{TEIL}1"
           for x in range(10, 890, 40) for y in range(10, 590, 40))             # Ausgeblendetes ist nicht wählbar
a.wahl.koerper_setzen([f"{TEIL}0"])
assert a.wahl.isolieren() == 2 and len(a.modell.dreiecke) == 12 and a.wahl.versteckt == {f"{TEIL}1", f"{TEIL}2"}
assert a.wahl.ausblenden() == 0 and len(a.modell.dreiecke) == 12                # das letzte Teil bleibt sichtbar
assert a.wahl.sicht_zurueck() and a.wahl.versteckt == {f"{TEIL}1"} and len(a.modell.dreiecke) == 24
assert a.wahl.sicht_zurueck() and a.wahl.versteckt == set() and len(a.modell.dreiecke) == 36
assert not a.wahl.sicht_zurueck()
assert a.wahl.sicht_vor() and a.wahl.sicht_vor() and not a.wahl.sicht_vor() and len(a.modell.dreiecke) == 12
assert a.wahl.alle_einblenden() == 2 and a.modell is a.voll
mitte, groesse = a.modell.mitte, a.modell.groesse
a.wahl.koerper_setzen([f"{TEIL}2"])
a.wahl.ausblenden()
assert a.modell.mitte == mitte and a.modell.groesse == groesse                  # das Bild springt nicht
w.setzen(bg, "Baugruppe")                                                       # neu gezeichnet: bleibt ausgeblendet
assert a.wahl.versteckt == {f"{TEIL}2"} and len(a.modell.dreiecke) == 24
a.wahl.alle_einblenden()
# Tasten H, I, Umschalt+H, Esc in der Ansicht
from PySide6.QtTest import QTest  # noqa: E402
a.wahl.koerper_setzen([f"{TEIL}0"])
QTest.keyClick(a, Qt.Key_H)
assert a.wahl.versteckt == {f"{TEIL}0"}
QTest.keyClick(a, Qt.Key_H, Qt.ShiftModifier)
assert a.wahl.versteckt == set()
a.wahl.koerper_setzen([f"{TEIL}0"])
QTest.keyClick(a, Qt.Key_I)
assert len(a.wahl.versteckt) == 2
QTest.keyClick(a, Qt.Key_H, Qt.ShiftModifier)
a.wahl.koerper_setzen([f"{TEIL}0"])
QTest.keyClick(a, Qt.Key_Escape)
assert a.wahl.gewaehlt == []
ok("A5 Ausblenden, Isolieren, Alle einblenden (Tasten H, I, Umschalt+H), Rückgängig/Wiederholen der Sichtbarkeit")

# ------------------------------------------------------------------ A6 Anzeige und Bedienung mit der Maus
a.wahl.setzen(True, aw.ALLES)
x, y = suchen(a, lambda e: e["art"] == aw.KOERPER and e["id"] == f"{TEIL}0")
QTest.mouseMove(a, QPointF(x, y).toPoint())
app.processEvents()
a.wahl.schweben(x, y)
assert a.wahl.status() == "Auswahl (Alles) · Körper: Pos. 10 Holm", a.wahl.status()       # Art unter der Maus
QTest.mouseClick(a, Qt.LeftButton, Qt.NoModifier, QPointF(x, y).toPoint())
assert a.wahl.koerper_ids() == [f"{TEIL}0"]
x1, y1 = suchen(a, lambda e: e["art"] == aw.KOERPER and e["id"] == f"{TEIL}2")
QTest.mouseClick(a, Qt.LeftButton, Qt.ControlModifier, QPointF(x1, y1).toPoint())
assert a.wahl.koerper_ids() == [f"{TEIL}0", f"{TEIL}2"] and a.wahl.arten() == "2 Körper"
zeilen = a.wahl.eigenschaften(a.wahl.gewaehlt[0])
assert zeilen[0] == "Körper: Pos. 10 Holm" and zeilen[1] == "Profil: QR 60x60x3" and \
    zeilen[2] == "Ausdehnung: 100,0 × 60,0 × 40,0 mm", zeilen
QTest.mousePress(a, Qt.LeftButton, Qt.ShiftModifier, QPointF(2, 2).toPoint())               # Umschalt+Ziehen
QTest.mouseMove(a, QPointF(a.width() - 2, a.height() - 2).toPoint())
QTest.mouseRelease(a, Qt.LeftButton, Qt.ShiftModifier, QPointF(a.width() - 2, a.height() - 2).toPoint())
assert a.wahl.arten() == "3 Körper" and a.wahl.fenster is None
w.grab()                                            # zeichnet Auswahl, Statuszeile und Tafel ohne Fehler
w.leiste.messen.setChecked(True)                    # Messen schaltet die Auswahl aus (und umgekehrt)
assert a.messen and not a.wahl.an and not w.leiste.auswahl.isChecked()
w.leiste.auswahl.setChecked(True)
assert a.wahl.an and not a.messen and not w.leiste.messen.isChecked()
ok("A6 Anzeige: Art unter der Maus, Gewähltes mit Eigenschaften; Klick, Strg+Klick, Umschalt+Ziehen; Messen aus")

# ------------------------------------------------------------------ B1 gleiche Bedienung in allen 3D-Fenstern
EINTRAEGE = ["Auswählen", "Filter: Alles", "Filter: Körper", "Filter: Fläche", "Filter: Kante", "Filter: Punkt",
             "Auf Auswahl zoomen", "Auswahl aufheben", "Ausblenden", "Isolieren", "Alle einblenden",
             "Sichtbarkeit: Rückgängig", "Sichtbarkeit: Wiederholen"]


def eintraege(menue):
    return [x.text().split("\t")[0] for x in menue.actions() if not x.isSeparator()]


assert eintraege(w.leiste.auswahl.menu()) == EINTRAEGE
bga = BaugruppenAnsicht()
assert bga.auswahl_knopf.text() == AUSWAHL and eintraege(bga.auswahl_knopf.menu()) == EINTRAEGE
m = auswahl_menue(QMenu(), a)
m.aboutToShow.emit()
ein = {x.text().split("\t")[0]: x for x in m.actions()}
assert ein["Auswählen"].isChecked() and ein["Filter: Alles"].isChecked() and ein["Isolieren"].isEnabled()
ein["Filter: Kante"].trigger()
assert a.wahl.filter == aw.KANTE
ok("B1 dasselbe Menü „Auswahl“ in der gemeinsamen Leiste und in Schweißbaugruppe / Satz in 3D")

# ------------------------------------------------------------------ B2 Satz in 3D: Liste <-> 3D, mehrere Körper
datei = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
tmp = Path(tempfile.mkdtemp())
step_messen.main(["--ausgabe", str(tmp / "m.txt"), "--json", str(tmp / "m.json"), "--netze", str(tmp / "netze"),
                  str(datei)])
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(tmp / "m.txt"), tmp / "netze"), tmp / "m.json")
for x in mw:
    x.update(_saetze=1, _stueck=1, _uebernehmen=True)
db = Datenbank(tmp / "satz.db")
k = db.kontext()
erg = step.uebernehmen([dict(x) for x in mw], [], k, db.zeilen("gewinde"), None, "S235-10219", None,
                       neue_profile=True, zukauf_liste=[])
satz = step.satzname(datei)
db.profile_anlegen(erg["profile"])
ang = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for q in erg["positionen"]:
    netz = q.pop("_netz", None)
    q.pop("_zukauf", None)
    pid = db.position_neu(ang, q)
    if netz:
        db.netz_speichern(pid, netz)
db.satz_daten_speichern(ang, satz, erg["satz_daten"][satz])
netze = db.netze(ang)
rolle = {kn: pid for pid in netze for kn in (entpacken(netze[pid]) or {}).get("koerper") or ()}
holm, strebe = rolle["1"], rolle["3"]
f = Hauptfenster(db, stumm=True)
seite = f.angebot_oeffnen(ang)
gesehen = {}


def bedienen(d):
    d.zeigen()
    a3 = d.ansicht3d.ansicht
    gesehen["knopf"] = eintraege(d.ansicht3d.auswahl_knopf.menu())
    d.ansicht3d.auswahl_knopf.setChecked(True)
    gesehen["an"] = a3.wahl.an and a3.wahl.vorgabe() == aw.KOERPER
    nr = {pid: i for i, (pid, _, _) in enumerate(d._koerper)}
    x, y = suchen(a3, lambda e: e["art"] == aw.KOERPER and e["id"] == f"{TEIL}{nr[strebe]}", 4)
    e = a3.wahl.klick(x, y)
    gesehen["name"] = aw.titel(e)
    gesehen["liste"] = d.auswahl()                              # Klick im 3D markiert die Zeile der Liste
    gesehen["info"] = a3.wahl.eigenschaften()
    x2, y2 = suchen(a3, lambda e: e["art"] == aw.KOERPER and d._koerper[int(e["id"][len(TEIL):])][0] == holm, 4)
    a3.wahl.klick(x2, y2, dazu=True)
    gesehen["zwei"] = d.auswahl()                               # Strg+Klick: zwei Teile, in Klickfolge
    gesehen["steck"] = d.steck_neu(*d.auswahl())                # Bearbeitung mehrerer Körper (wie im Rechtsklick-Menü)
    d.auswahl_setzen([holm])                                    # Auswahl über die Bauteilliste
    gesehen["aus_liste"] = sorted({d._koerper[int(k[len(TEIL):])][0] for k in a3.wahl.koerper_ids()})
    a3.wahl.isolieren()
    gesehen["isoliert"] = (len(a3.wahl.versteckt), len(d._koerper), d.auswahl())
    a3.wahl.alle_einblenden()
    d.reject()
    return d.result()


i = next(r for r, q in enumerate(seite.positionen) if q["id"] == holm)
seite.satz_3d(i, dialog=bedienen)
assert gesehen["knopf"] == EINTRAEGE and gesehen["an"], gesehen
assert gesehen["name"].startswith("Körper: Pos. ") and gesehen["liste"] == [strebe], gesehen
assert any(z.startswith("Profil: ") for z in gesehen["info"]) and any(z.startswith("Ausdehnung") for z in gesehen["info"])
assert gesehen["zwei"] == [strebe, holm] and gesehen["steck"], gesehen
assert gesehen["aus_liste"] == [holm], gesehen
versteckt, koerper, liste = gesehen["isoliert"]
assert 0 < versteckt < koerper and liste == [holm], gesehen
ok("B2 Satz in 3D: Klick im 3D markiert die Zeile, Zeile wählt den Körper, zwei gewählte Rohre -> Steckverbindung, "
   "Isolieren")

# ------------------------------------------------------------------ B3 STEP-Prüfdialog
from rohrlaser.step_dialog import KOERPER_3D, StepPruefDialog  # noqa: E402
pd = StepPruefDialog(None, [dict(x) for x in mw], k, "S235-10219", 1, zukauf_liste=db.zukauf_artikel_liste())
pd.resize(1500, 800)
pd.show()
app.processEvents()
pd.baugruppe_zeigen(datei.name)
ap = pd.ansicht.ansicht
assert ap.netz.get("teile") and eintraege(pd.ansicht.leiste.auswahl.menu()) == EINTRAEGE
pd.ansicht.leiste.auswahl.setChecked(True)
assert ap.wahl.aus_kennung() and len(ap.wahl.elemente().koerper) == len([x for x in mw if x.get("_netz")])
x, y = suchen(ap, lambda e: e["art"] == aw.KOERPER, 5)
e = ap.wahl.klick(x, y)
nummer = int(e["id"][len(KOERPER_3D):])
assert e["name"] == pd.messwerte[nummer]["artikel"]
gewaehlt = [z for z in pd.zeilen if z.it.isSelected()]
assert len(gewaehlt) == 1 and nummer in gewaehlt[0].liste                         # Zeile der Liste folgt
assert ap.netz.get("teile")                                                       # die Baugruppe bleibt im Bild
zeilen = ap.wahl.eigenschaften()
assert any(z.startswith("Importquelle: S03_") for z in zeilen) and any(z.startswith("Ausdehnung") for z in zeilen), zeilen
pd.close()
ok("B3 STEP-Prüfdialog: Körper der Baugruppe mit Name und Eigenschaften, die Zeile der Liste wird markiert")

# ------------------------------------------------------------------ B4 Rohr- und Blech-Editor, Rückgängig
from rohrlaser import blech  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser import schneidweg as sw  # noqa: E402
werkstoff = sorted(z["blech_werkstoff_id"] for z in db.zeilen("blech_werkstoffe"))[0]
dlg = BlechDialog(None, db, dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=300, breite=200,
                                 werkstoff=werkstoff, konturen=[]))
rahmen = dlg.editor
dlg.resize(1500, 900)
dlg.show()
app.processEvents()
knopf = rahmen.band.knopf(AUSWAHL)
assert knopf is not None and eintraege(knopf.menu()) == EINTRAEGE
knopf.setChecked(True)
ab = rahmen.ansicht()
assert ab.wahl.an
ab.wahl.filter = aw.FLAECHE
app.processEvents()
x, y = suchen(ab, lambda e: e["art"] == aw.FLAECHE and nah(e["flaeche"], 60000, 1.0), 5)
e = ab.wahl.klick(x, y)
assert aw.titel(e) == "Fläche (eben): 60000,0 mm²"
vorher = rahmen.zustand()
dlg.kontur_neu(dict(art=sw.BOHRUNG, anzahl=1, d=10, x=50, y=50))
rahmen.aktualisieren()
nachher = rahmen.zustand()
assert nachher != vorher and rahmen.verlauf.canUndo()
rahmen.verlauf.undo()
assert rahmen.zustand() == vorher and ab.wahl.an                         # die Auswahl bleibt eingeschaltet
rahmen.verlauf.redo()
assert rahmen.zustand() == nachher and ab.wahl.an
ab.wahl.setzen(False)
assert not knopf.isChecked()
dlg.close()
ok("B4 Blech-Editor: Knopf „Auswahl“ im Menüband, Fläche wählen; Rückgängig und Wiederholen einer Änderung")

print("Alle Prüfungen bestanden.")
