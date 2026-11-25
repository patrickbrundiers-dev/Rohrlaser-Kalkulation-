"""Tests der Gesamtprüfung 25.11.2026 (Codeanalyse, Fehlersuche, Performance; Bericht
docs/system-audit/GESAMTPRUEFUNG_2511.md).

1. Stangenoptimierung mit Zufallsgruppen aller Merkmale (Gehrungen Kasten/Quadrat/Rund, feste und unbekannte Naht,
   3D-Greifmaß, Teil am Stangenende): unabhängige Kontrolle (pruefe) und für kleine Gruppen Vergleich mit einer
   vollständigen Suche über alle Aufteilungen, Reihenfolgen und Drehungen. Eine als „nachweislich minimal“
   gemeldete Stangenzahl muss stimmen, die Schranke darf nie über dem wahren Minimum liegen.
2. aufloesen merkt sich Ablehnungen (Befund G-01: 10.000 gleiche Teile mit schrägem Ende rechneten 152 s): gleiches
   Ergebnis wie ohne Merken (bitgleich, Zufallsgruppen und große Serien), deutlich weniger passt-Prüfungen.
3. Schneidweg-Rechner (Befund G-02): eine vertippte Anzahl bzw. Reihenzahl meldet einen Fehler statt den
   Arbeitsspeicher zu füllen.
4. RP-Profile (Befund G-03): alle 141 Profile der Bibliothek haben einen Umriss mit der Fläche der Bibliothek; Profile,
   die schon vorher stimmten, bekommen genau denselben Umriss.

Aufruf: python tests/test_gesamtpruefung_2511.py
"""
import itertools
import random
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import optimierung as opt  # noqa: E402
from rohrlaser.optimierung import Gruppe, Teil  # noqa: E402


# ------------------------------------------------------------------ 1. Zufallsgruppen gegen vollständige Suche
def min_belegt(g, teile):
    """Kleinste Belegung über alle Reihenfolgen, Drehungen und Nahtlagen (unabhängig von anordnen)."""
    lagen = opt.naht_lagen(g, teile)
    if not lagen:
        return None
    beste = None
    for folge in itertools.permutations(teile):
        for s in lagen:
            je = [opt.drehungen(g, t, s) if opt._nestbar(g) else (0,) for t in folge]
            for dreh in itertools.product(*je):
                b = opt.belegt(g, list(zip(folge, dreh)))
                if beste is None or b < beste:
                    beste = b
    return beste


def minimum_stangen(g):
    """Wahres Minimum der Stangen (vollständige Suche über alle Aufteilungen)."""
    merk = {}

    def ok(teile):
        k = frozenset(id(t) for t in teile)
        if k not in merk:
            b = min_belegt(g, teile)
            merk[k] = b is not None and b <= g.nutzbar_bis + opt.EPS
        return merk[k]
    beste = [len(g.teile) + 1]

    def suche(rest, n):
        if n >= beste[0]:
            return
        if not rest:
            beste[0] = n
            return
        erstes, andere = rest[0], rest[1:]
        for k in range(len(andere), -1, -1):
            for mit in itertools.combinations(andere, k):
                if ok([erstes, *mit]):
                    suche([t for t in andere if t not in mit], n + 1)
    suche(list(g.teile), 0)
    return beste[0]


def zufalls_gruppe(rnd, klein):
    form = rnd.choice(["kasten", "quadrat", "rund", "keiner"])
    q = {"kasten": ("Kasten", 60, 40), "quadrat": ("Kasten", 50, 50), "rund": ("Rund", 30), "keiner": ()}[form]
    stange = rnd.choice([1000, 1500, 2500, 6000]) if klein else rnd.choice([6000, 12000])
    g = Gruppe("P", "S", stange, rnd.choice([0, 5, 20]), rnd.choice([0, 50, 80, 150]), rnd.choice([0, 0.3, 2]),
               rnd.choice([0, 2, 5]), querschnitt=q)
    if rnd.random() < 0.3:
        g.ende_bonus = max(0.0, g.greiferrest - rnd.choice([0, 10, 30]))
    n = (rnd.randint(1, 4) if q else rnd.randint(1, 7)) if klein else rnd.randint(20, 200)
    typen = []
    for _ in range(rnd.randint(1, 4)):
        def gehrung():
            return None if rnd.random() < 0.5 or not q else (rnd.choice([15, 30, 45, 60]),
                                                             rnd.choice([0, 90, 180, 270]))
        a, b = gehrung(), gehrung()
        dr = rnd.choice([opt.FREI, opt.FREI, opt.FEST, opt.UNBEKANNT])
        typen.append(dict(laenge=round(rnd.uniform(30, stange * (0.7 if klein else 0.5)), 1), a=a, b=b,
                          ag=a is None and rnd.random() < 0.8, bg=b is None and rnd.random() < 0.8, dr=dr,
                          naht=rnd.choice([0, 90, 180, 270]) if dr == opt.FEST else None,
                          rest=rnd.choice([0, 0, 0, 120, 300]), ende_frei=rnd.random() < 0.4))
    g.teile = []
    while len(g.teile) < n:
        ty = rnd.choice(typen)
        z = len(g.teile) + 13
        g.teile.append(Teil(z, z, "A", len(g.teile) + 1, ty["laenge"], ty["ag"], ty["bg"], 60, 60, ty["a"], ty["b"],
                            drehung=ty["dr"], naht=ty["naht"], rest=ty["rest"], ende_frei=ty["ende_frei"]))
    return g


def zu_lang(g):
    return any(t.laenge + g.endbeschnitt + g.kerf + max(g.greiferrest, t.rest)
               - (g.ende_bonus if t.ende_frei else 0) > g.stange for t in g.teile)


def leeren():
    opt._ANORDNUNG.clear()
    opt._TRENNSUMME.clear()
    opt.merker_leeren()


def plan(g):
    leeren()
    r = opt.optimiere(g)
    return [[(t.zeile, t.nr, d) for t, d in f] for f in r], g.bewiesen, g.schranke


geprueft = 0
for s in range(400):
    g = zufalls_gruppe(random.Random(s), True)
    if zu_lang(g):
        continue
    leeren()
    r = opt.optimiere(g)
    opt.pruefe([g], [r])
    wahr = minimum_stangen(g)
    assert len(r) >= wahr, (s, len(r), wahr)
    assert not g.bewiesen or len(r) == wahr, f"Gruppe {s}: {len(r)} Stangen als minimal gemeldet, möglich {wahr}"
    assert g.schranke <= wahr, f"Gruppe {s}: Schranke {g.schranke} über dem Minimum {wahr}"
    geprueft += 1
assert geprueft > 350, geprueft
print(f"OK    {geprueft} kleine Zufallsgruppen: Kontrolle ok, Minimum und Schranke wie die vollständige Suche")

for s in range(40):
    g = zufalls_gruppe(random.Random(1000 + s), False)
    if zu_lang(g):
        continue
    leeren()
    opt.pruefe([g], [opt.optimiere(g)])
print("OK    40 große Zufallsgruppen: keine Stange überbelegt, jedes Teil genau einmal")


# ------------------------------------------------------------------ 2. aufloesen mit Merken: bitgleich, schneller
def vergleich(g):
    opt.AUFLOESEN_MERKEN = False
    try:
        ohne = plan(g)
    finally:
        opt.AUFLOESEN_MERKEN = True
    return ohne, plan(g)


gleich = 0
for s in range(300):
    g = zufalls_gruppe(random.Random(5000 + s), s % 3 == 0)
    if zu_lang(g):
        continue
    ohne, mit = vergleich(g)
    assert ohne == mit, f"Gruppe {s}: aufloesen mit Merken rechnet anders"
    gleich += 1


def serie(n, laenge, a_gerade, b_gerade, quer=(), geh=None):
    g = Gruppe("P", "S", 6000, 10, 142, 0.2, 2, querschnitt=quer)
    g.teile = [Teil(13, 10, "A", i + 1, laenge, a_gerade, b_gerade, 100, 100, None, geh) for i in range(n)]
    return g


rnd = random.Random(2511)
gemischt = Gruppe("P", "S", 6000, 10, 142, 0.2, 2)
for z in range(8):
    L, a, b = round(rnd.uniform(30, 900), 1), rnd.random() < 0.5, rnd.random() < 0.5
    gemischt.teile += [Teil(13 + z, 13 + z, "A", i + 1, L, a, b, 60, 60) for i in range(120)]
for g in (serie(1200, 50, True, False), serie(600, 230.5, False, False), gemischt,
          serie(400, 615, True, False, ("Kasten", 60, 40), (45, 0))):
    ohne, mit = vergleich(g)
    assert ohne == mit, "große Serie: aufloesen mit Merken rechnet anders"
    gleich += 1
print(f"OK    aufloesen mit Merken: {gleich} Gruppen bitgleich wie ohne")

# vergebliche Prüfungen: 2.000 gleiche Teile mit schrägem Ende Ende B (vorher 35.658 passt je aufloesen)
zaehler = [0]
passt_orig = opt.passt


def passt_zaehlend(*a):
    zaehler[0] += 1
    return passt_orig(*a)


opt.passt = passt_zaehlend
try:
    g = serie(2000, 50, True, False)
    leeren()
    t0 = time.perf_counter()
    r = opt.optimiere(g)
    dauer = time.perf_counter() - t0
finally:
    opt.passt = passt_orig
opt.pruefe([g], [r])
assert len(r) == 19 and g.bewiesen, (len(r), g.bewiesen)
assert zaehler[0] < 20000, f"aufloesen prüft wieder jedes Teil gegen jede volle Stange ({zaehler[0]} passt)"
print(f"OK    2.000 Teile mit schrägem Ende: 19 Stangen (minimal), {zaehler[0]} passt-Prüfungen "
      f"(vorher über 100.000), {dauer:.1f} s")


# ------------------------------------------------------------------ 3. Schneidweg: Tippfehler in der Anzahl
from rohrlaser import rp_profile, schneidweg as sw  # noqa: E402

PROFIL = dict(profil_id="RR 42,4x2,0", form="Rundrohr", a=42.4, b=None, wand=2.0, flaeche=None)
REGEL = (10.0, 30.0)          # Konturklassen klein bis / mittel bis [mm] (rechnen.kontur_regel ohne Wand)
for zeile in (dict(art=sw.BOHRUNG, anzahl=10 ** 7, d=8.5),
              dict(art=sw.LOCHFELD, anzahl=10, d=5, reihen=10 ** 6, teilung_q=3, abstand=10, x=20),
              dict(art=sw.LANGLOCH, anzahl=60000, l=20, b=8, kopien=[{"seite": "unten"}])):
    try:
        sw.kontur(zeile)
    except ValueError as f:
        assert "Anzahl bzw. Reihen prüfen" in str(f), f
    else:
        raise AssertionError(f"{zeile['art']}: keine Meldung bei {zeile} ")
assert sw.kontur(dict(art=sw.BOHRUNG, anzahl=sw.KONTUREN_MAX, d=8.5))[2] == sw.KONTUREN_MAX
t0 = time.perf_counter()
r = sw.rechnen(dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=10 ** 9, d=8.5, x=100),
                                          dict(art=sw.BOHRUNG, anzahl=2, d=8.5, x=200)]), PROFIL, REGEL)
assert any("Anzahl bzw. Reihen prüfen" in f for f in r["fehler"]), r["fehler"]
assert sum(s_["anzahl"] for s_ in r["schritte"] if s_.get("art") == sw.BOHRUNG) == 2      # übrige Zeilen gerechnet
assert time.perf_counter() - t0 < 5
print("OK    Konturzeile mit vertippter Anzahl/Reihen (10.000.000): Fehlermeldung statt vollem Arbeitsspeicher")


# ------------------------------------------------------------------ 4. RP-Profile: Umriss für alle
def flaeche(pts):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2


def umriss_ohne_ausweg(e, tol=0.1):
    q = rp_profile.querschnitt(e["elemente"], mit_konturen=True)
    mx, my = q["x0"] + q["breite"] / 2, q["y0"] + q["hoehe"] / 2
    return q, [[(round(x - mx, 4), round(y - my, 4)) for x, y in rp_profile.ausduennen(z, tol)]
               for z in q["konturen"]["aussen"][:1] + q["konturen"]["kammern"]]


bib = rp_profile.bibliothek()
vorher_gut = 0
for pid, e in sorted(bib.items()):
    u = rp_profile.umriss(e)
    netto = flaeche(u[0]) - sum(flaeche(k) for k in u[1:])
    assert abs(netto - e["flaeche"]) <= 0.03 * e["flaeche"], (pid, netto, e["flaeche"])
    try:
        q, alt = umriss_ohne_ausweg(e)
    except ValueError:
        continue
    if abs(q["flaeche"] - e["flaeche"]) <= 0.01 * e["flaeche"]:
        assert u == alt, f"{pid}: Umriss geändert, obwohl er vorher stimmte"
        vorher_gut += 1
assert len(bib) == 141 and vorher_gut == 103, (len(bib), vorher_gut)
print(f"OK    RP-Profile: alle {len(bib)} mit Umriss (vorher 38 ohne bzw. falsch), {vorher_gut} wie bisher")

print("OK: Gesamtprüfung 25.11.2026")
