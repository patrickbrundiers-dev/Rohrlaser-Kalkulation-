"""Prüft das Packmaß je Position (paletten.packmass, Verbesserungsplan P0-4: bisher nur gerade Rohre getestet).
Das Packmaß bestimmt Packvorschlag und Fracht. Erwartete Werte sind von Hand aus der Geometrie nachgerechnet
(Hüllquader, längste Seite zuerst).

Aufruf: python tests/test_packmass.py
"""
import json
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import blech, paletten  # noqa: E402


def ok(text):
    print("OK    ", text)


def gleich(ist, soll):
    assert ist is not None and len(ist) == len(soll) and all(abs(a - b) < 1e-6 for a, b in zip(ist, soll, strict=True)), \
        (ist, soll)


# gerades Rohr: Länge × Querschnitt
RR = dict(profil_abm=("Rechteckrohr", 60, 40, 3))
gleich(paletten.packmass(dict(laenge=2000), RR), (2000, 60, 40))
gleich(paletten.packmass(dict(laenge=500), dict(profil_abm=("Rundrohr", 48.3, None, 2.6))), (500, 48.3, 48.3))
gleich(paletten.packmass(dict(laenge=1500), dict(profil_abm=("Flachstahl", 50, None, 8))), (1500, 50, 8))
assert paletten.packmass(dict(laenge=None), RR) is None
assert paletten.packmass(dict(laenge=2000), dict()) is None
ok("Rohr: Länge × Querschnitt (Rechteck, Rund, Flachstahl), ohne Länge oder Profil kein Packmaß")

# ebener Zuschnitt: Länge × Breite × Dicke
zuschnitt = blech.speichern(dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=400, breite=200, dicke=3))
gleich(paletten.packmass(dict(technik=zuschnitt), {}), (400, 200, 3))
kaputt = blech.speichern(dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=400, dicke=3))     # Breite fehlt
assert paletten.packmass(dict(technik=kaputt), {}) is None
ok("Blech-Zuschnitt: 400 × 200 × 3; unvollständige Eingabe: kein Packmaß statt Absturz")

# Kantteil U 50/100/50, Dicke 2, Kantlänge 1000: Seitenansicht 50 × 100 (Außenmaße) + Dicke
kant = blech.speichern(dict(art=blech.KANTTEIL, kantlaenge=1000, dicke=2, schenkel=[
    dict(laenge=50, winkel=90), dict(laenge=100, winkel=90), dict(laenge=50)]))
gleich(paletten.packmass(dict(technik=kant), {}), (1000, 102, 52))
ok("Kantteil U 50/100/50 × 1000, s = 2: 1000 × 102 × 52")

# Knickrahmen L 600/400 aus QR 40: Schenkelzug + Profilmaß
knick = json.dumps(dict(knickrahmen=dict(schenkel=[600, 400], beta=90)))
gleich(paletten.packmass(dict(technik=knick, laenge=1000), dict(profil_abm=("Quadratrohr", 40, 40, 3))), (640, 440, 40))
knick_u = json.dumps(dict(knickrahmen=dict(schenkel=[300, 500, 300], beta=[90, 90])))
gleich(paletten.packmass(dict(technik=knick_u, laenge=1100), dict(profil_abm=("Rechteckrohr", 60, 40, 3))),
       (540, 340, 60))
ok("Knickrahmen: L 600/400 aus QR 40 → 640 × 440 × 40, U 300/500/300 aus RR 60×40 → 540 × 340 × 60")

# Biegerohr: Hüllquader der Mittellinie + Durchmesser
bieg = json.dumps(dict(biegerohr=dict(elemente=[dict(art="gerade")], xyz=[[0, 0, 0], [500, 0, 0], [500, 300, 100]])))
gleich(paletten.packmass(dict(technik=bieg, laenge=900), dict(profil_abm=("Rundrohr", 30, None, 2))),
       (530, 330, 130))
ok("Biegerohr: Mittellinie 500 × 300 × 100 + Ø 30 → 530 × 330 × 130")

# Schweißbaugruppe: Abmessungen aus den Stammdaten der Baugruppe (Text), längste zuerst
bg = dict(art="Schweißbaugruppe", baugruppe=json.dumps(dict(id="bg1", stamm=dict(abmessungen="800 x 1200 x 600 mm"))))
gleich(paletten.packmass(bg, {}), (1200, 800, 600))
assert paletten.packmass(dict(art="Schweißbaugruppe", baugruppe=json.dumps(dict(id="bg1", stamm={}))), {}) is None
ok("Schweißbaugruppe: '800 x 1200 x 600 mm' → 1200 × 800 × 600, ohne Abmessungen kein Packmaß")
print("OK: Packmaß")
