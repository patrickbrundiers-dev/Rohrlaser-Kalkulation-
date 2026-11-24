"""Rechenkerne und Systemstabilität (Master-Prompt Patrick 21.11.2026): schnellere Schnittoptimierung mit genau
denselben Ergebnissen, Ergebnisprüfung, Wiederherstellung, Diagnose mit Befunden, Überwachung der Hintergrundaufgaben.

Geprüft wird ohne Bildschirm:
1. Simplex der Spaltengenerierung: die Fortsetzung über die Schritte der Vorrunde (SimplexVerlauf) liefert für
   zufällige Folgen von Schnittmuster-Programmen Zahl für Zahl dasselbe wie die bisherige Rechnung von vorn
   (Referenz: der Code bis 0.9.447, unten unverändert eingefügt), auch mit kleinem Speicher für Zwischenstände.
2. Mustersuche (bestes_muster): gleiche Muster, gleiche Vollständigkeit wie der bisherige Code, bei jeder Suche
   während des Optimierens großer Testangebote.
3. Optimieren der Testangebote M und L: Schnittplan bitgleich mit und ohne Fortsetzung des Simplex.
4. Ergebnisprüfung: NaN/∞ in Zeilen oder Summen → summen["rechenfehler"], FEHLER im Angebots-Check, Diagnose zählt;
   ein gültiges Ergebnis bleibt ohne neuen Schlüssel.
5. Wiederherstellung: bricht die Kalkulation einmal ab (beschädigter Zwischenstand), rechnet sie ohne Merker neu und
   liefert dasselbe Ergebnis wie normal; ein bleibender Fehler wird weitergegeben.
6. Parallel: dieselbe Kalkulation in 4 Fäden gleichzeitig ergibt überall dasselbe.
7. Diagnose: Befunde mit Empfehlung (fehlgeschlagen, lange Rechnung, Doppelrechnung, Speicher, Datenbank, lange
   Hintergrundaufgabe), Antwortzeit-Stufen der Datenbank, Bericht.
8. Hintergrundaufgaben: melden, laufend, fertig gezählt, lange Laufzeit als Befund.
Aufruf: python tests/test_rechenkerne_2111.py
"""
import random
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import testangebote_gross  # noqa: E402
from rohrlaser import angebot_check, diagnose, hintergrund, optimierung, parallel, rechenmerker, rechenpruefung, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.optimierung import EPS, FREI, MUSTER_MAX_KNOTEN, anordnen, verbrauch  # noqa: E402,F401


def ok(text):
    print("OK    ", text)


# ---------------------------------------------------------------- Referenz: bisheriger Code (bis 0.9.447)
def simplex_max_alt(c, a, b):
    """Lineares Programm max c·y unter a·y <= b, y >= 0 mit b >= 0 (Simplex mit Tableau, Regel von Bland gegen
    Kreisen). Ergebnis: (y, Zielwert, Schattenpreise der Zeilen, gelöst)."""
    m, n = len(a), len(c)
    tab = [list(a[i]) + [1.0 if j == i else 0.0 for j in range(m)] + [b[i]] for i in range(m)]
    z = [-x for x in c] + [0.0] * (m + 1)
    basis = [n + i for i in range(m)]
    geloest = False
    for _ in range(20 * (m + n) + 100):
        e = next((j for j in range(n + m) if z[j] < -1e-9), None)
        if e is None:
            geloest = True
            break
        r, best = None, None
        for i in range(m):
            if tab[i][e] > 1e-9:
                q = tab[i][-1] / tab[i][e]
                if best is None or q < best - 1e-12 or (abs(q - best) <= 1e-12 and basis[i] < basis[r]):
                    r, best = i, q
        if r is None:       # unbeschränkt: kommt bei Schnittmustern nicht vor (jeder Typ hat ein Muster)
            break
        p = tab[r][e]
        zeile = [x / p for x in tab[r]]
        tab[r] = zeile
        # nur die Spalten, in denen die Pivotzeile nicht 0 ist, ändern sich (x − f·0 = x): gleiches Ergebnis, schneller
        nz = [j for j, y in enumerate(zeile) if y != 0.0]
        for i in range(m):
            ti = tab[i]
            if i != r and abs(ti[e]) > 1e-12:
                f = ti[e]
                for j in nz:
                    ti[j] = ti[j] - f * zeile[j]
        f = z[e]
        for j in nz:
            z[j] = z[j] - f * zeile[j]
        basis[r] = e
    y = [0.0] * n
    for i, bi in enumerate(basis):
        if bi < n:
            y[bi] = tab[i][-1]
    return y, z[-1], z[n:n + m], geloest


def bestes_muster_alt(g, typen, bedarf, wert):
    """Schnittmuster (Anzahl je Typ, höchstens der Bedarf) mit dem größten Gesamtwert, das auf eine Stange passt.
    Tiefensuche, je Typ zuerst die größte mögliche Anzahl; abgeschnitten wird, wenn selbst die freie Länge mit dem
    besten Wert je mm nicht mehr reicht. Ergebnis: (Muster, Suche vollständig)."""
    n = len(typen)
    beste, zahl, knoten = [None, -1.0], [0] * n, [0]
    q_ab = [max([wert[j] / typen[j].laenge for j in range(i, n) if bedarf[j]] or [0.0]) for i in range(n + 1)]
    # Die Trennungen hängen ohne Gehrungen nur davon ab, wie viele Teile welche Enden haben (gerade-gerade,
    # schräg-gerade, gerade-schräg, schräg-schräg; anordnen ordnet danach, gewendet wird nie); der Verbrauch ist also
    # Länge der Teile + Zuschlag je Anzahl. Gehrungen zählen hier wie 2 Schnitte (sicher, nie zu kurz).
    arten = ((True, True), (False, True), (True, False), (False, False))
    art = [arten.index((t.a_gerade, t.b_gerade)) for t in typen]
    vertreter = {a: replace(typen[art.index(a)], laenge=0.0, a_gehrung=None, b_gehrung=None, drehung=FREI, naht=None)
                 for a in set(art)}
    zuschlag = {}

    def zuschlag_von(anz):
        null = [vertreter[a] for a in range(4) for _ in range(anz[a])]
        zuschlag[anz] = verbrauch(g, anordnen(null))
        return zuschlag[anz]

    grenze = g.nutzbar_bis + EPS

    frei = g.nutzbar_bis - g.endbeschnitt
    laengen = [t.laenge for t in typen]

    def suche(i, w, laenge, anz0):
        # anz0: Anzahl je Endenart der Typen vor i (wird mitgegeben statt je Knoten neu gezählt; gleiche Suche)
        knoten[0] += 1
        if w > beste[1] + 1e-9:
            beste[0], beste[1] = list(zahl), w
        if i == n or knoten[0] > MUSTER_MAX_KNOTEN:
            return
        if w + q_ab[i] * (frei - laenge) <= beste[1] + 1e-9:
            return
        a, li = art[i], laengen[i]
        anz = list(anz0)
        while zahl[i] < bedarf[i]:
            anz[a] += 1
            schl = tuple(anz)
            zs = zuschlag.get(schl)
            if zs is None:
                zs = zuschlag_von(schl)
            if not zs + (laenge + li * (zahl[i] + 1)) <= grenze:      # passt nicht mehr auf die Stange
                break
            zahl[i] += 1
        while True:
            k = zahl[i]
            weiter = list(anz0)
            weiter[a] += k
            suche(i + 1, w + wert[i] * k, laenge + li * k, weiter)
            if zahl[i] == 0:
                break
            zahl[i] -= 1

    suche(0, 0.0, 0.0, [0, 0, 0, 0])
    return beste[0], knoten[0] <= MUSTER_MAX_KNOTEN


# ---------------------------------------------------------------- 1. Simplex
def folge_pruefen(rnd, n_typen, runden, staende_max=None):
    """Spaltengenerierung nachstellen: Startmuster je Typ, dann je Runde ein zufälliges neues Muster."""
    bedarf = [float(rnd.randint(1, 60)) for _ in range(n_typen)]
    muster = [[float(rnd.randint(1, 9)) if j == i else 0.0 for j in range(n_typen)] for i in range(n_typen)]
    v = optimierung.SimplexVerlauf()
    alt_max = optimierung.SIMPLEX_STAENDE_MAX
    if staende_max:
        optimierung.SIMPLEX_STAENDE_MAX = staende_max
    try:
        for _ in range(runden):
            a = [list(m) for m in muster]
            alt = simplex_max_alt(list(bedarf), a, [1.0] * len(a))
            neu = optimierung.simplex_max(list(bedarf), [list(m) for m in muster], [1.0] * len(a), v)
            assert repr(alt) == repr(neu), (n_typen, len(muster), alt, neu)
            muster.append([float(rnd.choice([0, 0, 0, 1, 2, 3, 5])) for _ in range(n_typen)])
            if not any(muster[-1]):
                muster[-1][rnd.randrange(n_typen)] = 1.0
    finally:
        optimierung.SIMPLEX_STAENDE_MAX = alt_max
    return v


rnd = random.Random(2111)
uebernommen = gerechnet = 0
for nr in range(60):
    v = folge_pruefen(rnd, rnd.randint(2, 18), rnd.randint(3, 40), staende_max=rnd.choice([None, 2, 3, 5]))
    uebernommen += v.uebernommen
    gerechnet += v.gerechnet
assert uebernommen > 0, "Fortsetzung wird nie genutzt"
ok(f"Simplex: 60 zufällige Spaltengenerierungen bitgleich zur Rechnung von vorn ({uebernommen} Schritte übernommen, "
   f"{gerechnet} gerechnet)")
# ohne passenden Verlauf (andere Matrix) rechnet er von vorn, ebenfalls gleich
v = optimierung.SimplexVerlauf()
for c, a in (([3.0, 4.0], [[2.0, 0.0], [0.0, 3.0]]), ([5.0, 1.0, 2.0], [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 4.0]])):
    assert repr(optimierung.simplex_max(c, a, [1.0] * len(a), v)) == repr(simplex_max_alt(c, a, [1.0] * len(a)))
ok("Simplex: andere Matrix → Rechnung von vorn, gleiches Ergebnis")

# ---------------------------------------------------------------- 2./3. Mustersuche und Optimieren
parallel.PARALLEL_AB_TEILE, ab = 10 ** 12, parallel.PARALLEL_AB_TEILE      # alles in diesem Prozess (vergleichbar)
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rk.db")
k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
suchen = [0]
neu_bm = optimierung.bestes_muster


def bm_beide(g, typen, bedarf, wert):
    r_neu = neu_bm(g, typen, bedarf, wert)
    r_alt = bestes_muster_alt(g, typen, list(bedarf), list(wert))
    assert repr(r_neu) == repr(r_alt), (r_neu, r_alt)
    suchen[0] += 1
    return r_neu


def leeren():
    rechenmerker.alle_leeren()
    optimierung.merker_leeren()


angebote = {g: testangebote_gross.anlegen(db, g) for g in ("M", "L")}
optimierung.bestes_muster = bm_beide
try:
    plaene = {}
    for g, aid in angebote.items():
        leeren()
        plaene[g] = repr(rechnen.optimieren(db.angebot(aid), db.positionen(aid), k, tab, einst))
finally:
    optimierung.bestes_muster = neu_bm
assert suchen[0] > 20, suchen
ok(f"Mustersuche: {suchen[0]} Suchen beim Optimieren der Testangebote M und L gleich wie bisher")


class OhneVerlauf(optimierung.SimplexVerlauf):
    """Verlauf, der nie passt: jede Runde rechnet von vorn (wie bisher)."""
    __slots__ = ()

    def __setattr__(self, name, wert):
        object.__setattr__(self, name, None if name == "a" else wert)


orig = optimierung.SimplexVerlauf
optimierung.SimplexVerlauf = OhneVerlauf
try:
    for g, aid in angebote.items():
        leeren()
        assert repr(rechnen.optimieren(db.angebot(aid), db.positionen(aid), k, tab, einst)) == plaene[g], g
finally:
    optimierung.SimplexVerlauf = orig
ok("Optimieren M und L: Schnittplan bitgleich mit und ohne Fortsetzung des Simplex")
parallel.PARALLEL_AB_TEILE = ab

# ---------------------------------------------------------------- 4. Ergebnisprüfung
aid = angebote["M"]
erg = rechnen.optimieren(db.angebot(aid), db.positionen(aid), k, tab, einst)
db.ergebnis_speichern(aid, erg)
kopf, pos = db.angebot(aid), db.positionen(aid)
e = rechnen.einstellungen_angebot(kopf, einst)
zeilen, summen = rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e)
assert "rechenfehler" not in summen and rechenpruefung.befunde(zeilen, summen) == []
assert not any(p[0] == "FEHLER" and "Rechenfehler" in p[1] for p in angebot_check.punkte(kopf, pos, [""] * len(pos), "aktuell", summen))
diagnose.zuruecksetzen()
z2 = [dict(z) if z else z for z in zeilen]
s2 = dict(summen)
i = next(i for i, z in enumerate(z2) if z)
z2[i]["verkauf"] = float("nan")
s2["material"] = float("inf")
t = rechenpruefung.pruefen(z2, s2)
assert len(t) == 2 and s2["rechenfehler"] == t and "nan" in t[0] and "Summe: material" in t[1], t
fehler = [p for p in angebot_check.punkte(kopf, pos, [""] * len(pos), "aktuell", s2) if p[0] == "FEHLER"]
assert any("Rechenfehler" in p[1] for p in fehler), fehler
assert diagnose.stand()["fehlgeschlagen"]["Kalkulation"]["anzahl"] == 1
assert any(b[0] == diagnose.ROT for b in diagnose.befunde())
# Text mit „inf“ (z. B. „informiert“) ist kein Befund
assert rechenpruefung.befunde([dict(pos=1, text="informiert, nanometer")], dict(x=1.0)) == []
ok("Ergebnisprüfung: gültiges Ergebnis unverändert; NaN/∞ → rechenfehler, FEHLER im Angebots-Check, Diagnose ROT")

# ---------------------------------------------------------------- 5. Wiederherstellung
normal = repr(rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e))
gemerkt = rechnen._kalkulation_gemerkt
aufrufe = [0]


def einmal_kaputt(*a):
    aufrufe[0] += 1
    raise ValueError("beschädigter Zwischenstand (Test)")


rechnen._kalkulation_gemerkt = einmal_kaputt
try:
    diagnose.zuruecksetzen()
    wieder = repr(rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e))
finally:
    rechnen._kalkulation_gemerkt = gemerkt
assert wieder == normal and aufrufe[0] == 1
assert diagnose.stand()["fehlgeschlagen"]["Kalkulation (abgebrochen)"]["anzahl"] == 1
messen = rechnen._kalkulation_messen
rechnen._kalkulation_gemerkt = einmal_kaputt
rechnen._kalkulation_messen = lambda *a: (_ for _ in ()).throw(KeyError("bleibt"))
try:
    try:
        rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e)
        raise AssertionError("Fehler verschluckt")
    except ValueError as ex:
        assert "beschädigter" in str(ex)
finally:
    rechnen._kalkulation_gemerkt, rechnen._kalkulation_messen = gemerkt, messen
ok("Wiederherstellung: Abbruch → einmal ohne Merker neu, gleiches Ergebnis; bleibender Fehler wird gemeldet")

# ---------------------------------------------------------------- 6. Parallel
leeren()
rechnen._KALK_MERK.leeren()
ergebnisse, fehler_t = [], []


def lauf():
    try:
        for _ in range(3):
            ergebnisse.append(repr(rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e)))
    except Exception as ex:     # noqa: BLE001 – im Test sammeln
        fehler_t.append(ex)


faeden = [threading.Thread(target=lauf) for _ in range(4)]
for f in faeden:
    f.start()
for f in faeden:
    f.join()
assert not fehler_t and len(ergebnisse) == 12 and set(ergebnisse) == {normal}, fehler_t
ok("Parallel: 4 Fäden × 3 Kalkulationen gleichzeitig, alle gleich dem normalen Ergebnis")

# ---------------------------------------------------------------- 7. Diagnose
diagnose.zuruecksetzen()
for d in (0.0005, 0.005, 0.05, 0.5, 2.0):
    diagnose.db_zugriff(d)
st = diagnose.stand()
assert st["db"]["stufen"] == [1, 1, 1, 1, 1] and abs(st["db"]["max_s"] - 2.0) < 1e-12
roh = dict(st, rechnungen=dict(Optimieren=dict(anzahl=12, summe_s=40.0, max_s=20.0, langsam=6, doppelt=0),
                               Kalkulation=dict(anzahl=20, summe_s=2.0, max_s=0.2, langsam=0, doppelt=5)),
           speicher_mb=3500, db=dict(anweisungen=1000, summe_s=30.0, stufen=[900, 50, 20, 20, 10], max_s=3.0),
           hintergrund_lang=[("Staffelpreise", 900.0)], haenger=2, fehler=3, cache_aus=True, fehlgeschlagen={})
bf = diagnose.befunde(roh)
texte = " | ".join(b[1] for b in bf)
for teil in ("Optimieren: längster Lauf", "Kalkulation: 5 von 20", "Arbeitsspeicher", "Datenbank langsam",
             "Staffelpreise", "hing 2×", "3 unerwartete", "Merker über den Neustart"):
    assert teil in texte, (teil, texte)
assert bf[0][0] == diagnose.ROT and all(b[2] for b in bf), bf
assert diagnose.befunde(dict(st, rechnungen={}, speicher_mb=300, fehler=0, hintergrund_lang=[], haenger=0,
                             cache_aus=False, fehlgeschlagen={}, db=dict(anweisungen=0, summe_s=0.0))) == []
b = diagnose.bericht()
assert "Befunde und Empfehlungen" in b and "Antwortzeiten" in b and "Hintergrundaufgaben" in b
ok(f"Diagnose: {len(bf)} Befunde mit Empfehlung erkannt, unauffälliger Stand ohne Befund, Bericht vollständig")

# ---------------------------------------------------------------- 8. Hintergrundaufgaben
halt = threading.Event()
f = hintergrund.melden(threading.Thread(target=halt.wait, name="Testaufgabe", daemon=True))
f.start()
assert any(n == "Testaufgabe" and s is not None for n, s in hintergrund.laufend())
assert not any(n == "Testaufgabe" for n, _ in hintergrund.befunde())
assert any(n == "Testaufgabe" for n, _ in hintergrund.befunde(time.monotonic() + hintergrund.LANG_S + 1))
halt.set()
f.join()
assert hintergrund.beendet()["Testaufgabe"]["anzahl"] == 1
assert not any(n == "Testaufgabe" for n, _ in hintergrund.laufend())
ok("Hintergrundaufgaben: gemeldet, laufend mit Dauer, lange Laufzeit als Befund, fertig gezählt")
db.schliessen()
print("Alle Prüfungen bestanden.")
