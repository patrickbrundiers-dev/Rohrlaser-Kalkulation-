"""Auftrag „3D-Ansicht – Kantenvisualisierung und technische Prüfbarkeit“ (Patrick 20.11.2026), Prüfung an den acht
Pflicht-Prüfmodellen (tests/pruefmodelle_3d.py).

K1 Kantenklassen: Körperkanten aus dem Knickwinkel, je Kante außen/innen (Innenwand), keine Netzdreiecke, keine
   Doppelten; große Baugruppe (über 100.000 Dreiecke) hat jetzt Kanten
K2 Kantenwinkel aus der Einstellung: kleiner Winkel = mehr Kanten (Rundrohr-Facetten), je Winkel neu gerechnet
K3 Verdeckung (Software): keine Innenkanten durch die Rohrwand; verdeckt gestrichelt nur auf Wunsch (Einstellung)
   bzw. in Verdeckt gestrichelt / Technisch / Prüfmodus; Raster-Verdeckung je Punkt richtig
K4 Darstellungen A–E und Prüfmodus: alle 13 Arten zeichnen alle Prüfmodelle ohne Fehler
K5 Durchsicht je Teil (Taste T, Knopf „Durchsichtig“): nur Anzeige, Netz und volles Modell unverändert, Alle deckend
K6 Einstellungen: sieben neue (an/aus, verdeckt, innen, Farbe, Stärke, Winkel, Deckkraft) nur je Arbeitsplatz, auf der
   Einstellungsseite, in den 3D-Profilen geprüft; Ungültiges fällt auf die Vorgabe
K7 OpenGL-Puffer: Außen-/Innenkanten getrennt, durchsichtige Dreiecke eigener Puffer, gleiche Dreieckszahl
K8 Tempo: Kanten der großen Baugruppe in vertretbarer Zeit

Aufruf: python tests/test_kanten_3d.py
"""
import copy
import os
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
import pruefmodelle_3d as pm  # noqa: E402
from rohrlaser import ansicht3d, ansicht3d_gl, ansicht3d_profile, einstellungen_ordnung, teilen  # noqa: E402
from rohrlaser import visualisierung as vis  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNGEN  # noqa: E402

ansicht3d.renderer_setzen("Software")
fehler = []


def ok(bedingung, text):
    print(("OK     " if bedingung else "FEHLER ") + text, flush=True)
    if not bedingung:
        fehler.append(text)


NETZE = {name.split()[0]: f() for name, f in pm.MODELLE}

# K1
m3 = ansicht3d.Modell(NETZE["3"])
kanten, klassen = m3.kanten(), m3.kanten_klassen()
ok(len(kanten) == len(klassen) and ansicht3d.KANTE_INNEN in klassen and ansicht3d.KANTE_AUSSEN in klassen,
   f"K1 Kanten mit Klasse je Kante: {klassen.count('a')} außen, {klassen.count('i')} innen")
schl = {tuple(sorted((tuple(round(c, 4) for c in a), tuple(round(c, 4) for c in b)))) for a, b, _ in kanten}
ok(len(schl) == len(kanten), "K1 keine doppelten Kanten")
# ebene Wand eines Rechteckrohrs: Diagonalen der Netzdreiecke sind keine Kanten (nur Knicke/Ränder)
n_dreiecke = len(m3.dreiecke)
ok(len(kanten) < n_dreiecke, f"K1 weniger Kanten ({len(kanten)}) als Dreiecke ({n_dreiecke}): keine Netzlinien")
m8 = ansicht3d.Modell(NETZE["8"])
t = time.perf_counter()
k8 = m8.kanten()
dt8 = time.perf_counter() - t
ok(len(m8.dreiecke) > 100000 and len(k8) > 1000, f"K1 große Baugruppe ({len(m8.dreiecke)} Dreiecke) hat Kanten "
                                                  f"({len(k8)})")

# K2
m5 = ansicht3d.Modell(NETZE["5"])
anzahl = {}
for winkel in (5.0, 25.0, 60.0):
    vis.setzen({"ansicht3d_kantenwinkel": winkel})
    anzahl[winkel] = len(m5.kanten())
vis.setzen({})
ok(anzahl[5.0] > anzahl[25.0] >= anzahl[60.0], f"K2 Kantenwinkel 5°/25°/60°: {anzahl}")
ok(len(m5.kanten()) == anzahl[25.0], "K2 zurück auf die Vorgabe: wieder dieselben Kanten")

# K3 Raster-Verdeckung je Punkt
ver = ansicht3d._Verdeckung(1.0, 0.01)
ver.dazu((0.0, 0.0, 10.0), (10.0, 0.0, 10.0), (0.0, 10.0, 10.0))
ok(ver.verdeckt((2.0, 2.0, 0.0)) and not ver.verdeckt((2.0, 2.0, 20.0)) and not ver.verdeckt((9.0, 9.0, 0.0)),
   "K3 Punkt hinter dem Dreieck verdeckt, davor bzw. daneben sichtbar")
st = ver.stuecke((-5.0, 2.0, 0.0), (5.0, 2.0, 0.0), 1.0)
ok(len(st) == 2 and st[0][2] and not st[1][2], f"K3 Strecke in sichtbares und verdecktes Stück geteilt ({len(st)})")


def bild(netz, darstellung, blick="Vorn", w=360, h=220):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    m = ansicht3d.Modell(netz)
    g, n = ansicht3d.blick_auf({"Vorn": (0, 0, -1), "Iso": (-0.5, 0.6, -0.6)}[blick]) if blick != "Vorn" else (0, 0)
    ansicht3d.zeichnen(p, m, w, h, g, n, darstellung=darstellung)
    p.end()
    return img


def blaue(img):
    """Bildpunkte in der Farbe der Innenkanten (auch gestrichelt/halb deckend auf hellem Grund)."""
    n = 0
    for x in range(0, img.width()):
        for y in range(0, img.height()):
            c = QColor(img.pixel(x, y))
            if c.blue() > c.red() + 40 and c.blue() > c.green() + 15:
                n += 1
    return n


# Rohr mit Gehrung von der Seite: die Innenwand liegt ganz hinter der Außenwand
netz6 = copy.deepcopy(NETZE["6"])
for k in ("l",):
    netz6[k] = {}
vis.setzen({"ansicht3d_innenkanten": "ja", "ansicht3d_verdeckt": "nein"})
ohne = blaue(bild(netz6, ansicht3d.MIT_KANTEN))
vis.setzen({"ansicht3d_innenkanten": "ja", "ansicht3d_verdeckt": "ja"})
mit = blaue(bild(netz6, ansicht3d.MIT_KANTEN))
technisch = blaue(bild(netz6, ansicht3d.TECHNISCH))
vis.setzen({})
ok(ohne < 15 and mit > 3 * max(ohne, 10), f"K3 Innenkanten hinter der Wand nicht durchgezogen ({ohne} blaue "
                                           f"Bildpunkte), mit „verdeckt gestrichelt“ sichtbar ({mit})")
ok(technisch > 3 * max(ohne, 10), f"K3 Technisch zeigt verdeckte Innenkanten gestrichelt ({technisch})")

# K4
modi = {"A": ansicht3d.REALISTISCH, "B": ansicht3d.MIT_KANTEN, "C": ansicht3d.TECHNISCH,
        "D": ansicht3d.DURCHSICHTIG_KANTEN, "E": ansicht3d.DRAHTGITTER}
ok(dict(ansicht3d.MODI_AE) == modi and len(ansicht3d.DARSTELLUNGEN) == 13 and ansicht3d.PRUEFMODUS in ansicht3d.DARSTELLUNGEN,
   "K4 Modi A–E und Prüfmodus Rohrlaser in der Darstellungsliste")
gezeichnet = 0
for name, netz in NETZE.items():
    if name == "8":
        continue
    for dar in ansicht3d.DARSTELLUNGEN:
        img = bild(netz, dar, "Iso", 200, 130)
        gezeichnet += not img.isNull()
ok(gezeichnet == 7 * 13, f"K4 sieben Prüfmodelle × 13 Darstellungen gezeichnet ({gezeichnet})")
ok(all(d in ansicht3d.DARSTELLUNG_TIPP for d in ansicht3d.DARSTELLUNGEN), "K4 jede Darstellung mit Tipp")

# K5 Durchsicht je Teil
netz2 = copy.deepcopy(NETZE["2"])
vorher = copy.deepcopy(netz2)
a = ansicht3d.Ansicht3D()
a.resize(400, 260)
a.setzen(netz2)
a.wahl.setzen(True)
voll_dreiecke = list(a.voll.dreiecke)
a.wahl.gewaehlt = [a.wahl._koerper_el("teil:1")]
n = a.wahl.durchsichtig_schalten()
durch = getattr(a.modell, "durch", None)
teil1 = {nr for nr, k in enumerate(a.wahl.elemente().koerper_von) if k == "teil:1"}
ok(n == 1 and durch and set(durch) == teil1, f"K5 Teil durchsichtig: {len(durch or ())} Dreiecke markiert")
ok(a.modell is not a.voll and getattr(a.voll, "durch", None) is None and a.voll.dreiecke == voll_dreiecke,
   "K5 nur Anzeige: volles Modell unverändert, eigene Kopie für die Ansicht")
for dar in (ansicht3d.MIT_KANTEN, ansicht3d.PRUEFMODUS, ansicht3d.TECHNISCH):
    a.darstellung_setzen(dar)
    a._bild = None
    ok(not a.grab().isNull(), f"K5 Bild mit durchsichtigem Teil: {dar}")
ok(any("Durchsichtig" in x[0] for x in a.wahl.aktionen_liste()), "K5 Knopf „Durchsichtig“ zur Auswahl")
ok(a.wahl.alle_deckend() == 1 and not getattr(a.modell, "durch", None), "K5 Alle deckend")
ok(netz2 == vorher, "K5 Netz unverändert")
a.wahl.gewaehlt = [a.wahl._koerper_el("teil:0")]
a.wahl.durchsichtig_schalten()
a.wahl.durchsichtig_schalten()
ok(not a.wahl.durchsichtig, "K5 zweimal schalten: wieder deckend")

# K6 Einstellungen
neu = ("ansicht3d_kanten", "ansicht3d_verdeckt", "ansicht3d_innenkanten", "ansicht3d_kantenfarbe",
       "ansicht3d_kantenstaerke", "ansicht3d_kantenwinkel", "ansicht3d_deckkraft")
namen = {e.name for e in EINSTELLUNGEN}
ok(all(x in namen and x in vis.NAMEN and x in teilen.LOKAL for x in neu),
   "K6 sieben Einstellungen, Aussehen, nur dieser Arbeitsplatz")
seite = {n for ab in einstellungen_ordnung.SEITE["e_kanten3d"].abschnitte for n in ab.namen}
ok(set(neu) <= seite, "K6 auf der Einstellungsseite „3D-Kanten und Durchsicht“")
w = vis.setzen({"ansicht3d_kanten": "vielleicht", "ansicht3d_kantenfarbe": "Pink", "ansicht3d_kantenwinkel": 500,
                "ansicht3d_deckkraft": "x", "ansicht3d_kantenstaerke": "kräftig"})
ok(w["ansicht3d_kanten"] == "ja" and w["ansicht3d_kantenfarbe"] == vis.VORGABEN["ansicht3d_kantenfarbe"]
   and float(w["ansicht3d_kantenwinkel"]) <= 80 and float(w["ansicht3d_deckkraft"]) == vis.DECKKRAFT_VORGABE
   and w["ansicht3d_kantenstaerke"] == "kräftig", f"K6 Ungültiges → Vorgabe bzw. Grenze ({w})")
stil_k = vis.kanten_stil()
ok(stil_k["breite"] == vis.KANTENSTAERKEN["kräftig"] and 0 < stil_k["alpha"] < 1, "K6 Kantenstil aus den Einstellungen")
vis.setzen({})
gut, weg = ansicht3d_profile.pruefen({"ansicht3d_kantenfarbe": "Schwarz", "ansicht3d_kantenwinkel": 100,
                                      "ansicht3d_verdeckt": "ja"})
ok("ansicht3d_kantenfarbe" in gut and "ansicht3d_verdeckt" in gut and "ansicht3d_kantenwinkel" not in gut and weg,
   f"K6 3D-Profile prüfen die neuen Werte ({weg})")
for name, werte in ansicht3d_profile.PROFILE.items():
    ok(ansicht3d_profile.pruefen(werte)[1] == [], f"K6 Profil gültig: {name}")

# K7 OpenGL-Puffer
farben = {x: ansicht3d_gl._farbe(c) for x, c in ansicht3d.FARBE.items()}
mo = ansicht3d.Modell(NETZE["3"])
d, li, ka, ki, dd = ansicht3d_gl.puffer_daten(mo, farben, farben, kanten=True)
ok(len(ka) // 18 == mo.kanten_klassen().count("a") and len(ki) // 18 == mo.kanten_klassen().count("i") and not dd,
   "K7 Kantenpuffer außen/innen getrennt")
d2, _, _, _, dd2 = ansicht3d_gl.puffer_daten(mo, farben, farben, klar=lambda nr, art: art in ansicht3d.PRUEF_DURCH)
ok(len(dd2) > 0 and len(d2) + len(dd2) == len(d), "K7 durchsichtige Dreiecke im eigenen Puffer, keins verloren")

# K9 Keine Längslinien mitten im Rundrohr (Patrick 20.11.2026, Prüfdialog I10_RR40x2_L300_Loch25): lange Facetten
# neben den kleinen Dreiecken um ein Loch sind keine Tangentenkante; mit Flächenkatalog der STEP-Messung zählt nur
# der Übergang zwischen zwei STEP-Flächen
from rohrlaser import rohr3d, schneidweg as sw9  # noqa: E402


def laengs(netz):
    m_ = ansicht3d.Modell(netz)
    return len([1 for a, b, _ in m_.kanten() if abs(a[2] - b[2]) > 5])


loch = dict(a={}, b={}, konturen=[dict(art=sw9.BOHRUNG, anzahl=1, d=25, x=150, seite="oben"),
                                  dict(art=sw9.BOHRUNG, anzahl=1, d=8, x=250, seite="vorne")])
rr9 = rohr3d.netz(loch, dict(form="Rundrohr", a=40, wand=2), 300)
ok(laengs(rr9) == 0, f"K9 Rundrohr Ø 40 mit Loch Ø 25: keine Längslinie auf dem Mantel ({laengs(rr9)})")
ok(laengs(rohr3d.netz(loch, dict(form="Rundrohr", a=168.3, wand=4), 300)) == 0, "K9 Rundrohr Ø 168,3: keine Längslinie")
qr9 = laengs(rohr3d.netz(loch, dict(form="Quadratrohr", a=40, b=40, wand=3), 300))
ok(qr9 >= 16, f"K9 Quadratrohr: Tangentenkanten am Eckradius bleiben ({qr9})")
kat = copy.deepcopy(rr9)                      # alle Dreiecke einer STEP-Fläche: nur Ränder, keine Kante dazwischen
kat["fk"], kat["tf"] = [dict(a="Zylinder", f=1.0, r=20.0)], {k: [0] * (len(v) // 3) for k, v in kat["t"].items()}
mk = ansicht3d.Modell(kat)
ok(len(mk.dreiecke_f) == len(mk.dreiecke) and laengs(kat) == 0, "K9 Flächenkatalog: innerhalb einer STEP-Fläche keine Kante")

# K8
ok(dt8 < 60.0, f"K8 Kanten der großen Baugruppe in {dt8:.1f} s")

print()
if fehler:
    print(f"{len(fehler)} FEHLER")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
