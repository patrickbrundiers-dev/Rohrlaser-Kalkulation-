"""Fehler-Durchgang 01.11.2026 (Patrick „Ausführlichen Bugfix durchführen“, Freigabe „So umsetzen“):
- F1 Stangenoptimierung bei großen Stückzahlen: First-Fit, Best-Fit und Auflösen überspringen volle Stangen und
  schon geprüfte gleiche Teile. Ergebnis Stange für Stange gleich wie vorher (Vergleich mit dem bisherigen Verfahren,
  hier als Referenz kopiert), aber schnell: 20.000 gleiche Teile vorher über 10 Minuten, 6.000 gemischte vorher
  rund 80 s.
- F2 Rechtsklick ohne Markierung → „Baugruppe bearbeiten …“: Hinweis statt Absturz (IndexError).
- F3 „inf“, „nan“, „1e999“ in Zahlen- und Rechenfeldern: abgelehnt wie jede andere ungültige Eingabe (vorher Preis
  „nan“ bzw. Absturz bei Ganzzahlfeldern).

Aufruf: python tests/test_fehler_0111.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import random
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import optimierung as opt  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ F1 Referenz: Verfahren bis 0.9.227 (unverändert)
def ref_first_fit(g, teile):
    stangen = []
    for t in opt.sortiert(teile):
        for s in stangen:
            if opt.passt(g, s + [t]):
                s.append(t)
                break
        else:
            stangen.append([t])
    return stangen


def ref_best_fit(g, teile):
    stangen = []
    for t in opt.sortiert(teile):
        beste, rest_min = None, None
        for s in stangen:
            if not opt.vertraeglich(g, s + [t]):
                continue
            v = opt.belegt(g, opt.anordnen(s + [t], g))
            if v <= g.nutzbar_bis + opt.EPS and (rest_min is None or g.nutzbar_bis - v < rest_min):
                beste, rest_min = s, g.nutzbar_bis - v
        if beste is None:
            stangen.append([t])
        else:
            beste.append(t)
    return stangen


def ref_aufloesen(g, stangen):
    """Schwach belegte Stangen auflösen, wenn alle ihre Teile in andere Stangen passen."""
    stangen = [list(s) for s in stangen]
    belegt_ = {}        # Belegung je Zusammenstellung (wird sonst je Teil für jede Stange neu gerechnet)

    def vb(x):
        k = tuple(id(t) for t in x)
        if k not in belegt_:
            belegt_[k] = opt.belegt(g, opt.anordnen(x, g))
        return belegt_[k]
    geaendert = True
    while geaendert and len(stangen) > 1:
        geaendert = False
        for s in sorted(stangen, key=lambda s: sum(t.laenge for t in s)):
            andere = [list(x) for x in stangen if x is not s]
            ok = True
            for t in opt.sortiert(s):
                ziel = None
                for x in sorted(andere, key=lambda x: -vb(x)):
                    if opt.passt(g, x + [t]):
                        ziel = x
                        break
                if ziel is None:
                    ok = False
                    break
                ziel.append(t)
            if ok:
                stangen = andere
                geaendert = True
                break
    return stangen



def zufallsgruppe(seed, n_von=1, n_bis=120):
    r = random.Random(seed)
    qs = r.choice([(), ("Kasten", 40, 40), ("Kasten", 60, 40), ("Rund", 25)])
    g = opt.Gruppe("P", "S235", r.choice([6000, 3000, 2000]), r.choice([0, 5, 10]), r.choice([0, 50, 100]),
                   r.choice([0, 0.2, 2]), r.choice([0, 1, 5]), querschnitt=qs)
    arten = []
    for _ in range(r.randint(1, 6)):
        laenge = r.choice([r.uniform(50, 1500), r.uniform(100, 3000), r.uniform(10, 200)])
        ag, bg = r.random() < .7, r.random() < .7
        ageh = None if ag or not qs else (r.choice([15, 30, 45]), r.choice([0, 90, 180, 270]))
        bgeh = None if bg or not qs else (r.choice([15, 30, 45]), r.choice([0, 90, 180, 270]))
        dreh = r.choice([opt.FREI, opt.FREI, opt.FEST, opt.UNBEKANNT])
        naht = r.choice([0, 90, 180, 270]) if dreh == opt.FEST else None
        arten.append((laenge, ag, bg, ageh, bgeh, dreh, naht, r.choice([0, 0, 200])))
    teile = []
    for i in range(r.randint(n_von, n_bis)):
        laenge, ag, bg, ageh, bgeh, dreh, naht, rest = r.choice(arten)
        teile.append(opt.Teil(i % 5, i % 5, f"A{i % 5}", i, round(laenge, 1), ag, bg, 10, 10, ageh, bgeh, dreh, naht,
                              rest))
    g.teile = [t for t in teile if t.laenge + g.endbeschnitt + g.kerf + max(g.greiferrest, t.rest) <= g.stange]
    return g


def nummern(stangen):
    return [[t.nr for t in s] for s in stangen]


geprueft = 0
for seed in range(120):
    g = zufallsgruppe(seed)
    if not g.teile:
        continue
    for neu, alt in ((opt.first_fit, ref_first_fit), (opt.best_fit, ref_best_fit)):
        a, b = neu(g, g.teile), alt(g, g.teile)
        assert nummern(a) == nummern(b), (seed, neu.__name__)
        assert nummern(opt.aufloesen(g, a)) == nummern(ref_aufloesen(g, b)), (seed, "aufloesen")
    geprueft += 1
ok(f"F1 First-Fit, Best-Fit und Auflösen Stange für Stange wie bisher ({geprueft} Zufallsgruppen)")


def pruefen(g, stangen):
    assert sorted(t.nr for f in stangen for t, _ in f) == sorted(t.nr for t in g.teile), "Teile fehlen oder doppelt"
    assert all(opt.belegt(g, f) <= g.nutzbar_bis + opt.EPS for f in stangen), "Stange überlastet"


g = opt.Gruppe("RR 42,4x2,0", "S235", 6000, 5, 100, 0.2, 1, querschnitt=("Rund", 21.2))
g.teile = [opt.Teil(0, 10, "A", i, 1250.0, True, True, 133, 133) for i in range(20000)]
t0 = time.time()
st = opt.optimiere(g)
dauer = time.time() - t0
pruefen(g, st)
assert len(st) == 5000 and g.bewiesen and dauer < 30, (len(st), dauer)
ok(f"F1 20.000 gleiche Teile: 5.000 Stangen, optimal, {dauer:.1f} s (vorher über 10 Minuten)")

ARTEN = [(485.0, True, True, None, None), (210.0, True, False, None, (45, 0)),
         (1250.0, False, False, (45, 0), (45, 180)), (860.0, True, True, None, None), (95.5, True, True, None, None)]
g = opt.Gruppe("QR 40x40x3", "S235", 6000, 5, 100, 0.2, 1, querschnitt=("Kasten", 40, 40))
g.teile = [opt.Teil(z, z * 10, f"A{z}", i, laenge, a, b, 160, 160, ga, gb)
           for z, (laenge, a, b, ga, gb) in enumerate(ARTEN) for i in range(1200)]
t0 = time.time()
st = opt.optimiere(g)
dauer = time.time() - t0
pruefen(g, st)
assert len(st) <= 591 and dauer < 60, (len(st), dauer)
ok(f"F1 6.000 gemischte Teile mit Gehrungen (Abruf-Größe): {len(st)} Stangen in {dauer:.1f} s (vorher rund 80 s)")

# ------------------------------------------------------------------ F3 unendlich ablehnen
from rohrlaser import rechenfeld, stammdaten  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

for text in ("inf", "nan", "1e999", "-Infinity", "9" * 400):
    for art in ("zahl", "ganz"):
        try:
            stammdaten.wert_aus_text(stammdaten.Feld("x", "Wert", art), text)
        except ValueError as e:
            assert "Wert" in str(e)
        else:
            raise AssertionError((text, art))
for text in ("1e999", "1e308*10", "1e308*10-1e308*10"):
    try:
        rechenfeld.auswerten(text)
    except ValueError:
        pass
    else:
        raise AssertionError(text)
assert stammdaten.wert_aus_text(stammdaten.Feld("x", "Wert", "zahl"), "1.250,5") == 1250.5
assert rechenfeld.auswerten("(1000 - 2x25)/2") == 475.0
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
a = db.angebot_neu(dict(kunde="Testkunde (erfunden)"))
try:
    db.position_neu(a, dict(pos=10, profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=float("inf"),
                            stueck=3))
except ValueError as e:
    assert "endliche" in str(e)
else:
    raise AssertionError("inf gespeichert")
ok("F3 „inf“, „nan“, „1e999“ in Zahlenfeldern, Rechenfeldern und Datenbank abgelehnt, normale Eingaben unverändert")

# ------------------------------------------------------------------ F2 Rechtsklick ohne Markierung
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
aid = beispiel_angebot.anlegen(db)
f.angebot_oeffnen(aid)
s = f.offen[aid]
s.pos_ansicht.clearSelection()
meldungen = []
alt_meldung = f.meldung
f.meldung = lambda text, *x, **k: meldungen.append(text)
s.pos_aktionen["Baugruppe bearbeiten …"].trigger()
assert s.baugruppe_bearbeiten([]) is False
assert meldungen and "markieren" in meldungen[0], meldungen
f.meldung = alt_meldung
ok("F2 „Baugruppe bearbeiten …“ ohne Markierung: Hinweis statt Absturz")
