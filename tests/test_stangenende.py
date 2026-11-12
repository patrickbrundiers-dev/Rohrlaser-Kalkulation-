"""Prüft „Teil am Stangenende“ (Plan ArTube-Unterlagen A1, Patrick 12.11.2026; Adige-Abfallvorstellung):
- S1 Optimierung: letztes Teil mit freiem Ende B nutzt den Greiferrest bis auf den Mindestabfall, ohne Freigabe nicht
- S2 Reihenfolge: das freie Teil kommt ans Stangenende; zwei freie Teile auf einer Stange nur eines im Greiferrest
- S3 Zufallsgruppen: nie überbelegt (unabhängige Prüfung), nie mehr Stangen als ohne Teil am Stangenende
- S4 Regeln (stangenende.py): Maschinenfeld, höchster Abfall, Ende B schräg, 3D-Greifmaß, Kontur im Spannbereich
- S5 Angebot: Maschine mit „Teil am Stangenende“ = ja -> eine Stange weniger, Stangentext; Maschine ohne = wie bisher

Aufruf: python tests/test_stangenende.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import random
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import optimierung as opt  # noqa: E402
from rohrlaser import stangenende as se  # noqa: E402
from rohrlaser.optimierung import Gruppe, Teil, am_stangenende, anordnen, hinten, optimiere, passt, pruefe  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


def gruppe(teile, greif=142.0, bonus=137.0, stange=6000):
    g = Gruppe("QR 40x40x3", "S235", stange, 10, greif, 0.2, 5)
    g.ende_bonus = bonus
    g.teile = teile
    return g


def teil(nr, laenge, frei=True, zeile=13, rest=0.0):
    return Teil(zeile, 10, "A", nr, laenge, True, True, 160, 160, rest=rest, ende_frei=frei)


# ------------------------------------------------------------------ S1
# ohne: nutzbar bis 6000 − 142 = 5858 -> Teil bis 5847,8; mit: Abfall 5 -> nutzbar bis 5995 -> Teil bis 5984,8
g = gruppe([teil(1, 5984.8)])
assert passt(g, g.teile) and not passt(gruppe([teil(1, 5985)]), [teil(1, 5985)])
f = anordnen(g.teile, g)
assert am_stangenende(g, f) and abs(hinten(g, f) - 5) < EPS
assert not passt(gruppe([teil(1, 5900, frei=False)]), [teil(1, 5900, frei=False)])
assert not passt(gruppe([teil(1, 5900)], bonus=0), [teil(1, 5900)])
ok("S1 letztes Teil am Stangenende: nutzbar bis 5.995 statt 5.858 mm; ohne Freigabe bzw. Maschine wie bisher")

# ------------------------------------------------------------------ S2
a, b = teil(1, 3000, frei=False, zeile=13), teil(1, 2900, zeile=14)       # 10 + 3000,2 + 2900,2 = 5910,4 > 5858
g2 = gruppe([a, b])
st = optimiere(g2)
assert len(st) == 1 and st[0][-1][0] is b and am_stangenende(g2, st[0]), st
pruefe([g2], [st])
g2b = gruppe([replace(a, ende_frei=False), replace(b, ende_frei=False)])
assert len(optimiere(g2b)) == 2
ok("S2 freies Teil ans Stangenende: 3.000 + 2.900 auf einer Stange (ohne Teil am Stangenende zwei)")
c, d = teil(1, 3000, zeile=13), teil(1, 3000, zeile=14)                   # 6010,4 > 5995 -> nie eine Stange
g3 = gruppe([c, d])
assert len(optimiere(g3)) == 2
ok("S2 zwei freie Teile 2 × 3.000: zwei Stangen (nur das letzte darf in den Greiferrest)")

# ------------------------------------------------------------------ S3
rnd = random.Random(1211)
for runde in range(60):
    teile = []
    for z in range(rnd.randint(1, 4)):
        laenge = rnd.choice((450, 800, 1250, 1999.5, 2400, 2950, 2990, 3800, 5900))
        frei = rnd.random() < 0.6 or laenge > 5800          # länger als die Nutzlänge: nur am Stangenende
        rest = 0 if laenge > 5800 else rnd.choice((0, 0, 0, 300))
        teile += [teil(n, laenge, frei, zeile=13 + z, rest=rest) for n in range(1, rnd.randint(2, 9))]
    g = gruppe(teile)
    st = optimiere(g)
    pruefe([g], [st])
    for f in st:
        last = f[-1][0]
        if am_stangenende(g, f):
            assert last.ende_frei and last.rest <= g.greiferrest + EPS
        assert opt.verbrauch(g, f) + hinten(g, f) <= g.stange + EPS
    ohne = gruppe([replace(t, ende_frei=False) for t in teile])
    assert len(st) <= len(optimiere(ohne)), runde
ok("S3 60 Zufallsgruppen: keine Stange überbelegt, Teil am Stangenende nur mit Freigabe, nie mehr Stangen als ohne")

# ------------------------------------------------------------------ S4 Regeln
m = dict(stangenende="ja")
assert se.bonus(m, 142) == 137 and se.bonus({}, 142) == 0 and se.bonus(m, 350) == 0
assert se.bonus(dict(m, stangenende_min=20), 142) == 122 and se.bonus(dict(m, stangenende_max=500), 350) == 345
p = dict(laenge=3000)
assert se.frei(p, m, 142, True) == "" and se.abstand_b(p) == math.inf
assert se.frei(p, {}, 142, True) == "Maschine ohne Teil am Stangenende"
assert se.frei(p, m, 142, False) == "Ende B nicht gerade"
assert se.frei(p, m, 142, True, rest=300) == "3D-Bearbeitung nahe Ende B"
assert se.frei(dict(laenge=3000, innen=2), m, 142, True) == "Lage der Konturen unbekannt"
kont = lambda x: json.dumps(dict(quelle="Schneidweg-Rechner", konturen=[dict(art="Bohrung", d=20, anzahl=1, x=x,  # noqa: E731
                                                                           seite="oben")]))
nah, weit = dict(laenge=3000, technik=kont(2900)), dict(laenge=3000, technik=kont(500))
an, aw = se.abstand_b(nah), se.abstand_b(weit)
assert an is not None and aw is not None and an < 142 < aw, (an, aw)
assert se.frei(nah, m, 142, True).startswith("Kontur ") and se.frei(weit, m, 142, True) == ""
ok(f"S4 Regeln: Maschine, höchster Abfall, Ende B schräg, 3D, Kontur {an:.0f} mm vor Ende B gesperrt, {aw:.0f} frei")

# ------------------------------------------------------------------ S5 Angebot
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
ma = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
greif = ma["greiferrest"]
assert 5 + 60 < greif <= 300, greif
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
# 10 + 3000,2 + L + 0,2 liegt 60 mm über der Nutzlänge 6000 − Greiferrest, aber unter 6000 − Mindestabfall 5
for nr, laenge in ((10, 3000), (20, round(2989.6 - greif + 60, 1))):
    db.position_neu(a, dict(pos=nr, artikel=f"S{nr}", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                            laenge=laenge, stueck=1, schneidweg=320, einstiche=2, a_schnitt=160, b_schnitt=160))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
n_ohne = len(s.ergebnis["stangen"])
db.aendern("maschinen", ma["id"], "stangenende", "ja")
s.neu_laden()
assert s.optimieren()
st = s.ergebnis["stangen"]
assert len(st) == n_ohne - 1 and st[0].get("stangenende"), (n_ohne, [(x["stange"], x.get("stangenende")) for x in st])
_, _, text = rechnen.stange_zeichen(st[0])
assert "Teil am Stangenende" in text, text
ok(f"S5 Angebot: mit Teil am Stangenende {len(st)} statt {n_ohne} Stangen, Stangentext „{text}“")
print("Alle Stangenende-Tests bestanden.")
