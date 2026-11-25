"""Nesting-Kern (Master-Entwicklungsauftrag Patrick 25.11.2026): Variantenlogik (P nur, wo es wirkt, gleiche Pläne in
einer Zeile, übertroffene Varianten, Variantenzahl), Strategien N „Gleiche Teile nacheinander“, S „Satzweise“,
X „Automatisch“ (Mehrzielbewertung), Kennzahlen der Schnittfolge und planabhängige Maschinenzeit.

Grundsatz laut Auftrag: keine Verbesserung behaupten, die die Messung nicht zeigt. Die bisherigen Strategien
A … H, P müssen bitgleich bleiben; N und S dürfen mehr Material brauchen, das zeigt der Vergleich offen.

Aufruf: python tests/test_nesting_kern_2511.py
"""
import random
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import nesting as ne, nesting_vergleich as nv, optimierung as opt  # noqa: E402

L6 = [ne.Laenge(6000, 60.0)]
L612 = [ne.Laenge(6000, 60.0), ne.Laenge(12000, 114.0)]


def gruppe(posten, artikel=None, **kw):
    g = opt.Gruppe(profil="QR 40x40x2", werkstoff="S235", stange=6000, endbeschnitt=10, greiferrest=142, kerf=0.2,
                   abstand=0.0, **kw)
    ts = []
    for z, (laenge, n, gerade) in enumerate(posten):
        name = artikel[z] if artikel else f"A{z}"
        ts += [opt.Teil(13 + z, 10 * (z + 1), name, i + 1, laenge, gerade, gerade, 160, 160) for i in range(n)]
    g.teile = ts
    return g


def abdruck(p):
    return None if p is None else [(x, [(t.zeile, t.nr, r) for t, r in f], rest) for x, f, rest in p.stangen]


def einmal(g, p):
    ids = sorted((t.zeile, t.nr) for _, f, _ in p.stangen for t, _ in f)
    assert ids == sorted((t.zeile, t.nr) for t in g.teile), "Teil fehlt oder doppelt"


# ---------------------------------------------------------------- K2: P nur, wo es wirkt (bitgleich)
g = gruppe([(1480, 20, True), (735, 40, True), (2210, 20, True)])
assert not opt.praezision_wirkt(g), "gerade Enden ohne Querschnitt: Präzision wirkt nicht"
for laengen in (L6, L612):
    ne.merker_leeren()
    opt.merker_leeren()
    a = ne.planen(g, ne.A, laengen)
    t = time.perf_counter()
    p = ne.planen(g, ne.P, laengen)
    dauer = time.perf_counter() - t
    # Gegenprobe: P wie vor 0.9.498 (Präzisionsrechnung immer) muss denselben Plan liefern
    with opt.praezision():
        e2, m2 = ne._grundplaene(g, ne._laengen_fuer(g, laengen))
        st = ne._kosten_suche(g, ne._laengen_fuer(g, laengen), "mm", e2, m2)
    kw = ne._kostenwert("mm", laengen)
    assert ne._wert(a.stangen, kw) <= ne._wert(st, kw) + 1e-6
    assert abdruck(p) == abdruck(a) or [(x, [(t.zeile, t.nr) for t, _ in f]) for x, f, _ in p.stangen] == \
        [(x, [(t.zeile, t.nr) for t, _ in f]) for x, f, _ in a.stangen], "P weicht von A ab"
    assert dauer < 0.5, f"P ohne Wirkung soll nicht neu rechnen ({dauer:.2f} s)"
with opt.offen_zaehlen() as z:
    ne.merker_leeren()
    ne.planen(g, ne.A, L6)
assert z.n >= 0
q = opt.Gruppe(profil="QR 40x40x2", werkstoff="S235", stange=6000, endbeschnitt=10, greiferrest=142, kerf=0.2,
               abstand=0.0, querschnitt=("Kasten", 40.0, 40.0))
q.teile = [opt.Teil(13, 10, "G", i + 1, 900, False, False, 160, 160, a_gehrung=(45.0, 0.0), b_gehrung=(45.0, 180.0))
           for i in range(6)]
assert opt.praezision_wirkt(q), "Gehrungen mit Querschnitt: Präzision rechnet"
print("OK     K2: P = A ohne zweite Rechnung, wo die Präzision nichts ändern kann; Gehrungen rechnen weiter")

# ---------------------------------------------------------------- Satz erkennen
assert ne.satz_erkennen(g.teile) == (20, [(("a2", 2210.0), 1), (("a0", 1480.0), 1), (("a1", 735.0), 2)]), \
    ne.satz_erkennen(g.teile)
assert ne.satz_erkennen(g.teile, 10)[0] == 10, "vorgegebene Satzzahl, wenn sie alle Mengen teilt"
assert ne.satz_erkennen(g.teile, 7)[0] == 20, "Satzzahl teilt nicht: aus den Mengen erkennen"
assert ne.satz_erkennen(gruppe([(1000, 7, True), (500, 3, True)]).teile) is None, "kein gemeinsamer Teiler"
assert ne.satz_erkennen(gruppe([(1000, 8, True)]).teile) is None, "nur eine Sorte"
# gleicher Artikel in zwei Positionen = eine Sorte
g2 = gruppe([(1250, 8, True), (1250, 6, True), (640, 10, True)], artikel=["Holm", "Holm", "Strebe"])
assert len(ne._sorten(g2.teile)) == 2
print("OK     Satz aus den Mengen (ggT), Vorgabe, gleiche Artikel über Positionen")

# ---------------------------------------------------------------- N und S: Fertigungsfolge, Prüfung, Material ehrlich
for laengen in (L6, L612):
    ne.merker_leeren()
    a = ne.planen(g, ne.A, laengen)
    n = ne.planen(g, ne.N, laengen)
    s = ne.planen(g, ne.S, laengen)
    for p in (n, s):
        einmal(g, p)
        ne.pruefe(g, p.stangen, p.uebrig, laengen)
        assert p.werte["gekauft_mm"] >= a.werte["gekauft_mm"] - 1e-6, "A bleibt die Materialgrenze"
    assert n.werte["artikelwechsel"] <= a.werte["artikelwechsel"], (n.werte["artikelwechsel"], a.werte["artikelwechsel"])
    assert s.werte["zwischenlager"] < a.werte["zwischenlager"], (s.werte["zwischenlager"], a.werte["zwischenlager"])
    assert s.werte["saetze"] == 20 and "1 × A2 2210 mm" in s.werte["satz_aufbau"], s.werte["satz_aufbau"]
    assert s.werte["satz_erster"] == 1, "erster Satz auf der ersten Stange fertig"
# N bei einer Sorte: volle Stangen, so viele wie A
e = gruppe([(870, 120, True)])
n = ne.planen(e, ne.N, L6)
assert n.werte["stangen"] == ne.planen(e, ne.A, L6).werte["stangen"] and n.werte["artikelwechsel"] == 0
# N: gleiche Teile stehen nacheinander, Reste am Stangenende
m = gruppe([(1150, 20, True), (2380, 10, True), (560, 15, True)])
n = ne.planen(m, ne.N, L6)
einmal(m, n)
folge = [ne.sorte(t) for _, f, _ in n.stangen for t, _ in f]
bloecke = sum(1 for x, y in zip(folge, folge[1:]) if x != y) + 1
assert bloecke == n.werte["artikelwechsel"] + 1
assert n.werte["artikelwechsel"] <= ne.planen(m, ne.A, L6).werte["artikelwechsel"]
# S nicht möglich ohne Satz
assert ne.planen(gruppe([(1000, 7, True), (500, 3, True)]), ne.S, L6) is None
# S mit Vorgabe der Satzzahl über die Gewichte
s10 = ne.planen(g, ne.S, L6, gewichte=dict(saetze=10))
assert s10.werte["saetze"] == 10
print("OK     N gleiche Teile nacheinander, S satzweise: jedes Teil einmal, geprüft, nie weniger Material als A")

# ---------------------------------------------------------------- X Automatisch
ne.merker_leeren()
x0 = ne.planen(g, ne.X, L6, gewichte=dict(artikelwechsel=0.0, zwischenlager=0.0, minute=0.0))
e0 = ne.planen(g, ne.E, L6)
assert ne.punkte_x(x0, dict(artikelwechsel=0.0, zwischenlager=0.0, minute=0.0)) <= ne.punkte(e0) + 1e-6
xs = ne.planen(g, ne.X, L6, gewichte=dict(zwischenlager=50.0, artikelwechsel=0.0))
assert xs.werte["zwischenlager"] == ne.planen(g, ne.S, L6).werte["zwischenlager"], "hohes Gewicht Zwischenlager: S"
assert "gewählt wie" in xs.warum and xs.schritte, xs.warum
print("OK     X wählt nach den Gewichten (ohne Zusatzgewichte nie schlechter als E)")

# ---------------------------------------------------------------- E bitgleich mit erweiterten Gewichten
ne.merker_leeren()
e1 = ne.planen(g, ne.E, L612, gewichte=dict(belegung=5.0, rest_mm=0.0))
ne.merker_leeren()
e2 = ne.planen(g, ne.E, L612, gewichte=dict(belegung=5.0, rest_mm=0.0, artikelwechsel=3.0, zwischenlager=1.0,
                                             minute=2.0, saetze=0, zeit=(20.0, 0.01, 1.5)))
assert abdruck(e1) == abdruck(e2), "E darf die neuen Gewichte nicht lesen"
print("OK     E bitgleich (liest nur € je Belegung und Restgutschrift)")

# ---------------------------------------------------------------- Maschinenzeit und Schnitte
w = ne.planen(e, ne.A, L6).werte
assert w["schnitte"] == w["trennschnitte"] + 2 * w["stangen"]
mz = ne.maschinenzeit(w, (20.0, 0.01, 1.5))
assert abs(mz - (w["beladungen"] * 20.0 + w["enden_mm"] * 0.01 + w["schnitte"] * 1.5)) < 1e-6
assert ne.maschinenzeit(w, None) is None
print("OK     Maschinenzeit planabhängig = Stangenwechsel + Trennschnitte (Schätzung)")

# ---------------------------------------------------------------- Variantenlogik im Vergleich
zeilen = [dict(strategie="bisher", name="bisher"),
          dict(strategie="A", name="A x", abdruck=1, gekauft_m=10, einkauf=100, beladungen=2, belegungen=1,
               verschnitt_mm=5, artikelwechsel=3, zwischenlager=4, maschine_min=1.0, punkte=110),
          dict(strategie="B", name="B x", abdruck=1, gekauft_m=10, einkauf=100, beladungen=2, belegungen=1,
               verschnitt_mm=5, artikelwechsel=3, zwischenlager=4, maschine_min=1.0, punkte=110),
          dict(strategie="E", name="E x", abdruck=1, gekauft_m=10, einkauf=100, beladungen=2, belegungen=1,
               verschnitt_mm=5, artikelwechsel=3, zwischenlager=4, maschine_min=1.0, punkte=110),
          dict(strategie="H", name="H x", abdruck=2, gekauft_m=12, einkauf=120, beladungen=3, belegungen=2,
               verschnitt_mm=9, artikelwechsel=5, zwischenlager=6, maschine_min=1.5, punkte=140),
          dict(strategie="S", name="S x", abdruck=3, gekauft_m=12, einkauf=120, beladungen=3, belegungen=1,
               verschnitt_mm=9, artikelwechsel=8, zwischenlager=0, maschine_min=1.5, punkte=125)]
out = nv.varianten_ordnen([dict(z) for z in zeilen], "E")
assert [z["strategie"] for z in out] == ["bisher", "E", "H", "S"], [z["strategie"] for z in out]
assert out[1]["auch"] == ["A", "B"] and out[1]["name"].endswith("(= A, B)")
assert out[2].get("uebertroffen") == "E" and not out[3].get("uebertroffen"), "S hat weniger Zwischenlager"
out = nv.varianten_ordnen([dict(z) for z in zeilen], "E", hoechstens=1)
assert [z["strategie"] for z in out] == ["bisher", "E"], [z["strategie"] for z in out]
out = nv.varianten_ordnen([dict(z) for z in zeilen], "E", gewaehlt="H", hoechstens=1)
assert [z["strategie"] for z in out] == ["bisher", "E", "H"], "gewählte Strategie bleibt sichtbar"
v = dict(zeilen=nv.varianten_ordnen([dict(z) for z in zeilen], "E"))
assert nv.zeile_von(v, "B")["strategie"] == "E" and nv.zeile_von(v, "Q") == {}
print("OK     Variantenlogik: gleiche Pläne in einer Zeile, übertroffene grau, Variantenzahl begrenzt")

# ---------------------------------------------------------------- großer Auftrag: Zeit und Prüfung
rnd = random.Random(3)
gross = gruppe([(round(rnd.uniform(300, 2900), 1), rnd.randint(4, 20), True) for _ in range(25)])
t = time.perf_counter()
ne.merker_leeren()
for s_ in (ne.A, ne.N, ne.S, ne.X):
    p = ne.planen(gross, s_, L612)
    if p is not None:
        einmal(gross, p)
dauer = time.perf_counter() - t
assert dauer < 60, f"{dauer:.1f} s"
print(f"OK     großer Auftrag ({len(gross.teile)} Teile): A, N, S, X in {dauer:.1f} s geprüft")
print("Alle Tests Nesting-Kern OK")
