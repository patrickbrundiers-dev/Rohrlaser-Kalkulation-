"""Prüft die neuen Regeln der Fertigungsprüfung aus den ArTube-Unterlagen (Plan C1, C2, C5, Patrick 12.11.2026):
- P1 großer Ausschnitt (Abfall klemmt) mit Vorschlag Mikrostege / Nacharbeit „Ausbrechen“
- P2 Rundloch im Rundrohr (Abfall taumelt), kleine Bohrung nicht
- P3 Kontur auf dem Kantenradius, mittig nicht
- P4 Teil stark geschwächt (ausgeschnittene Fläche)
- P5 Kontur im Spannbereich nur bei Maschine mit „Teil am Stangenende“
- P6 Machbarkeit: kleinstes spannbares Profil, Stangengewicht für den Lader
- P7 Regeln abschaltbar (Tabelle pruefregeln)
- P8 Naht nicht suchbar (C3), Strahl trifft Gegenflansch (G4), Über der Entladegrenze (C4)

Aufruf: python tests/test_pruefung_artube.py
"""
import json
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import dfm, rechnen  # noqa: E402


def ok(text):
    print("OK    ", text)


QR = dict(form="Quadratrohr", a=60, b=60, wand=3, profil_id="QR 60x60x3")
RR = dict(form="Rundrohr", a=60, wand=3, profil_id="RR 60x3")


def pos(konturen, laenge=1000, **f):
    return dict(laenge=laenge, technik=json.dumps(dict(quelle="Schneidweg-Rechner", konturen=konturen)), **f)


def regeln(befunde):
    return {b.regel for b in befunde}


# ------------------------------------------------------------------ P1
gross = pos([dict(art="Rechteck", b=200, h=50, anzahl=1, x=500, seite="oben", quer=True)])     # quer 200 mm > 0,4 × 240
b = dfm.rohr(gross, QR)
t = next(x for x in b if x.regel == dfm.GROSSER_AUSSCHNITT)
assert "Mikrostege" in t.text and "Ausbrechen" in t.text, t.text
assert dfm.GROSSER_AUSSCHNITT not in regeln(dfm.rohr(pos([dict(art="Rechteck", b=40, h=20, anzahl=1, x=500,
                                                               seite="oben")]), QR))
ok("P1 großer Ausschnitt: " + t.text)

# ------------------------------------------------------------------ P2
b = dfm.rohr(pos([dict(art="Bohrung", d=25, anzahl=1, x=500, seite="oben")]), RR)
t = next(x for x in b if x.regel == dfm.RUNDLOCH)
assert t.stufe == dfm.HINWEIS and "taumelt" in t.text
assert dfm.RUNDLOCH not in regeln(dfm.rohr(pos([dict(art="Bohrung", d=12, anzahl=1, x=500, seite="oben")]), RR))
assert dfm.RUNDLOCH not in regeln(dfm.rohr(pos([dict(art="Bohrung", d=25, anzahl=1, x=500, seite="oben")]), QR))
ok("P2 Rundloch Ø 25 im Rundrohr 60: Hinweis, Ø 12 und Quadratrohr nicht")

# ------------------------------------------------------------------ P3 (Außenradius QR 60x3 nach EN 10219: 6 mm)
rand = pos([dict(art="Bohrung", d=10, anzahl=1, x=500, seite="oben", q=24)])   # Mitte 24 mm neben der Mitte
mitte = pos([dict(art="Bohrung", d=10, anzahl=1, x=500, seite="oben", q=0)])
assert dfm.KANTENRADIUS in regeln(dfm.rohr(rand, QR)) and dfm.KANTENRADIUS not in regeln(dfm.rohr(mitte, QR))
assert dfm.KANTENRADIUS not in regeln(dfm.rohr(rand, dict(QR, r_aussen=0)))     # scharfkantig: kein Radius
ok("P3 Bohrung 1 mm vor dem Kantenradius gemeldet, mittig und scharfkantig nicht")

# ------------------------------------------------------------------ P4
viele = pos([dict(art="Rechteck", b=40, h=40, anzahl=8, abstand=50, x=100 + 25 * 0, seite=s) for s in
             ("oben", "unten", "vorne", "hinten")], laenge=500)
b = dfm.rohr(viele, QR)
assert dfm.GESCHWAECHT in regeln(b), b
assert dfm.GESCHWAECHT not in regeln(dfm.rohr(mitte, QR))
ok("P4 32 Ausschnitte 40 × 40 auf 500 mm: " + next(x.text for x in b if x.regel == dfm.GESCHWAECHT))

# ------------------------------------------------------------------ P5
m = dict(stangenende="ja", greiferrest=142)
nah = pos([dict(art="Bohrung", d=10, anzahl=1, x=950, seite="oben")])
assert dfm.SPANNBEREICH in regeln(dfm.rohr(nah, QR, m))
assert dfm.SPANNBEREICH not in regeln(dfm.rohr(nah, QR, dict(m, stangenende=None)))
assert dfm.SPANNBEREICH not in regeln(dfm.rohr(mitte, QR, m))
ok("P5 Kontur 45 mm vor Ende B bei Greiferrest 142: Hinweis nur mit „Teil am Stangenende“")

# ------------------------------------------------------------------ P6
assert rechnen.grenze_ueberschritten(dict(min_huellkreis=20), dict(form="Rundrohr", a=12), 1.0) == \
    "Profil kleiner als die Maschine spannen kann"
assert rechnen.grenze_ueberschritten(dict(min_huellkreis=20), dict(form="Rundrohr", a=25), 1.0) is None
assert rechnen.grenze_ueberschritten(dict(max_stange_kg=100), QR, 20.0, 6000) == "Stange schwerer als der Lader zulässt"
assert rechnen.grenze_ueberschritten(dict(max_stange_kg=100), QR, 5.0, 6000) is None
assert rechnen.grenze_ueberschritten(dict(max_stange_kg=100), QR, 20.0) is None
ok("P6 Machbarkeit: kleinstes spannbares Profil und Stangengewicht für den Lader")

# ------------------------------------------------------------------ P7
aus = [dict(regel=r, aktiv="nein") for r in (dfm.GROSSER_AUSSCHNITT, dfm.RUNDLOCH, dfm.KANTENRADIUS, dfm.GESCHWAECHT,
                                             dfm.SPANNBEREICH)]
for p_, pr in ((gross, QR), (rand, QR), (viele, QR), (nah, QR)):
    assert not regeln(dfm.rohr(p_, pr, m, aus)) & {dfm.GROSSER_AUSSCHNITT, dfm.KANTENRADIUS, dfm.GESCHWAECHT,
                                                   dfm.SPANNBEREICH}
assert {r for r, *_ in dfm.beispiel_regeln()} >= {dfm.GROSSER_AUSSCHNITT, dfm.RUNDLOCH, dfm.KANTENRADIUS}
ok("P7 alle neuen Regeln einzeln abschaltbar, Beispielzeilen der Tabelle vorhanden")

# ------------------------------------------------------------------ P8
SP = dict(form="Sonderprofil", a=60, b=30, wand=3, profil_id="SP 1")
UP = dict(form="U-Profil", a=60, b=30, wand=5, profil_id="UPN 60")
fest = pos([], naht_vorgabe="feste Position", naht_winkel=0)
assert dfm.NAHT_SUCHE in regeln(dfm.rohr(fest, SP)) and dfm.NAHT_SUCHE not in regeln(dfm.rohr(fest, QR))
assert dfm.NAHT_SUCHE not in regeln(dfm.rohr(pos([]), SP))
fl = pos([dict(art="Bohrung", d=10, anzahl=1, x=500, seite="Flansch oben")])
st = pos([dict(art="Bohrung", d=10, anzahl=1, x=500, seite="Steg")])
assert dfm.FLANSCH_GEGENUEBER in regeln(dfm.rohr(fl, UP)) and dfm.FLANSCH_GEGENUEBER not in regeln(dfm.rohr(st, UP))
lang = pos([], laenge=4000)
assert dfm.ENTLADEN in regeln(dfm.rohr(lang, QR, dict(entlade_laenge=3000)))
assert dfm.ENTLADEN not in regeln(dfm.rohr(lang, QR, {}))
ok("P8 Naht nicht suchbar am Sonderprofil, Bohrung im U-Flansch trifft Gegenflansch, 4 m über Entladegrenze 3 m")
print("Alle Prüfregeln aus den ArTube-Unterlagen bestanden.")
