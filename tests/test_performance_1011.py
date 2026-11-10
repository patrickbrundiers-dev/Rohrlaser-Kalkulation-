"""Performance-Update 10.11.2026 (Patrick „Programm schneller, zuverlässiger“): schneller bei gleichen Ergebnissen.

Geprüft wird ohne Bildschirm:
- rechnen.kopie liefert dasselbe wie copy.deepcopy (auch Mehrfach-Verweise) und ist schneller,
- rechnen.merker: Positionswerte, Schneiddaten, Stangenpreise und Stangenwerte je Eingabe einmal, jeder Aufrufer
  bekommt eigene Werte, ohne Merker und in anderen Threads rechnet alles wie bisher,
- satz_abweichung (jetzt über _satz_anzahlen) meldet dasselbe wie die alte quadratische Suche,
- Angebot mit gestaffeltem Gewinn (wie Patricks Einstellungen): eine Kalkulation je Änderung, der Angebots-Check
  nach der Pause rechnet keine zweite Kalkulation für die Auslastung, Ergebnisse gleich wie ohne Merker,
- Zeitgrenze Zelle ändern + Check (200 Positionen, gestaffelter Gewinn),
- Zeitwächter: Abschnitte mit eigener Grenze, Dekorator gemessen, Abschnitte im Hintergrund zählen nicht,
  Hänger-Schutz schreibt sofort eine Zeile mit den laufenden Abschnitten, die Auswertung nennt sie,
- Neuladen eines Angebots markiert seine Schritte (Daten lesen, Positionstabelle, Kalkulation …),
- Schnellprüfung der Datendatei (PruefLauf): gesunde Datei ohne Befund, beschädigte mit Befund.
Aufruf: python tests/test_performance_1011.py
"""
import copy
import json
import os
import random
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen, tempo  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank, PruefLauf  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

GRENZE_ZELLE_CHECK = 1.5     # s, 200 Positionen mit gestaffeltem Gewinn: Zelle ändern + Check (gemessen 0,4 s)
PROFILE = ["RR 42,4x2,0", "RR 48,3x2,6", "QR 40x40x3", "RE 60x40x3", "RE 120x60x4"]
WERKSTOFFE = ["S235-10219", "S355-10219", "1.4301"]
GESTAFFELT = (("gewinn_bis_1", 1000.0), ("gewinn_satz_1", 0.25), ("gewinn_bis_2", 2499.0), ("gewinn_satz_2", 0.2),
              ("gewinn_bis_3", 3000.0), ("gewinn_satz_3", 0.15))


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])

# ------------------------------------------------------------------ kopie wie deepcopy
innen = {"a": [1, 2.5, None], "b": "x"}
probe = ([{"z": innen, "w": innen, "t": (1, [2, 3]), "m": {1, 2}}, None], {"summe": 1.25, "liste": [innen]})
k1, k2 = copy.deepcopy(probe), rechnen.kopie(probe)
assert repr(k1) == repr(k2) and k2 == probe and k2 is not probe
assert k2[0][0]["z"] is k2[0][0]["w"] is k2[1]["liste"][0] and k2[0][0]["z"] is not innen
k2[0][0]["z"]["a"].append(9)
assert innen["a"] == [1, 2.5, None]
gross = [{"pos": i, "werte": [float(i)] * 20, "text": f"T{i}", "d": {"x": i, "y": [i, i]}} for i in range(3000)]
t = time.perf_counter()
copy.deepcopy(gross)
t_deep = time.perf_counter() - t
t = time.perf_counter()
assert rechnen.kopie(gross) == gross
t_kopie = time.perf_counter() - t
assert t_kopie < t_deep, (t_kopie, t_deep)
ok(f"kopie = deepcopy (Mehrfach-Verweise bleiben), {t_deep / t_kopie:.1f}× schneller")

# ------------------------------------------------------------------ Merker
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
k, tab = db.kontext(), db.tabellen()
kopf = dict(maschine="T11", stange=6000)
p = dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=500.0, stueck=4, schneidweg=300.0)
aufrufe = []
alt_pw = rechnen._position_werte
rechnen._position_werte = lambda *a: aufrufe.append(1) or alt_pw(*a)
try:
    w0 = rechnen.position_werte(p, kopf, k, tab)
    rechnen.position_werte(p, kopf, k, tab)
    assert len(aufrufe) == 2
    with rechnen.merker():
        w1 = rechnen.position_werte(p, kopf, k, tab)
        w1["eingeplant"] = 99            # eigenes dict: der nächste Aufrufer sieht das nicht
        w2 = rechnen.position_werte(p, kopf, k, tab)
        with rechnen.merker():           # verschachtelt: der äußere gilt
            rechnen.position_werte(p, kopf, k, tab)
        anderer = []
        th = threading.Thread(target=lambda: anderer.append(rechnen.position_werte(p, kopf, k, tab)))
        th.start()
        th.join()
    assert len(aufrufe) == 4, aufrufe     # 2 ohne Merker, 1 im Merker, 1 im anderen Thread
    assert "eingeplant" not in w2 and w2 == w0 and repr(anderer[0]) == repr(w0)
    rechnen.position_werte(p, kopf, k, tab)
    assert len(aufrufe) == 5               # nach dem Merker wieder neu gerechnet
finally:
    rechnen._position_werte = alt_pw
with rechnen.merker():
    a = rechnen.schneiddaten("T11", "S235-10219", 2.0, tab)
    assert rechnen.schneiddaten("T11", "S235-10219", 2.0, tab) is a
assert rechnen.schneiddaten("T11", "S235-10219", 2.0, tab) == a
ok("Merker: je Eingabe einmal, eigene Werte je Aufrufer, verschachtelt, je Thread, danach wie bisher")

# ------------------------------------------------------------------ Satz-Abweichung wie bisher


def satz_alt(p, positionen):
    if not positionen or rechnen.saetze_von(p) is None:
        return None
    satz = str(p.get("satz")).strip()
    n = sorted({rechnen.saetze_von(q) for q in positionen if rechnen.position_aktiv(q)
                and rechnen.saetze_von(q) is not None and str(q.get("satz")).strip() == satz})
    if len(n) < 2:
        return None
    return f"Satz {satz}: unterschiedliche Anzahl Sätze ({' / '.join(rechnen.zahl(x, 2) for x in n)})"


rnd = random.Random(3)
for runde in range(30):
    pos = [dict(satz=rnd.choice([None, "A", " A", "B", 7]), stueck=rnd.choice([0, 2, 4, 6, 8]),
                je_satz=rnd.choice([None, 1, 2, 0.5]), aktiv=rnd.choice([None, "nein"])) for _ in range(25)]
    for q in pos:
        assert rechnen.satz_abweichung(q, pos) == satz_alt(q, pos)
        with rechnen.merker():
            assert rechnen.satz_abweichung(q, pos) == satz_alt(q, pos)
ok("Satz-Abweichung: gleiche Meldungen wie die alte Suche (750 Positionen)")


# ------------------------------------------------------------------ Angebot mit gestaffeltem Gewinn
def positionen(n, seed=1):
    r = random.Random(seed)
    for i in range(n):
        q = dict(pos=10 * (i + 1), artikel=f"ART-{i:04d}", bezeichnung=f"Teil {i}",
                 profil_id=PROFILE[i % len(PROFILE)], werkstoff_id=WERKSTOFFE[(i // 5) % len(WERKSTOFFE)],
                 laenge=float(r.choice([r.randint(80, 600), r.randint(600, 2500), r.randint(2500, 5800)])),
                 stueck=r.choice([1, 2, 4, 6, 8, 10, 12, 20, 40]),
                 schneidweg=round(r.uniform(250, 1200), 1), einstiche=r.randint(2, 10))
        if i % 10 == 3:
            q["zusatz"] = json.dumps([dict(name="Entgraten")])
        if i % 15 == 7:
            q["satz"], q["je_satz"] = f"Satz {i // 15}", 2
        yield q


for n, w in GESTAFFELT:
    db.einstellung_setzen(n, w)
AngebotSeite.CHECK_SOFORT = False
f = Hauptfenster(db, tmp, stumm=True)
aid = db.angebot_neu(dict(kunde="Leistung", kundennr="K-10045", maschine="T11", stange=6000))
for q in positionen(200):
    db.position_neu(aid, q)
s = f.angebot_oeffnen(aid)
s.optimieren()
app.processEvents()
spalte = next(i for i, (_, fd) in enumerate(s.pos_modell.spalten) if fd is not None and getattr(fd, "name", None) == "stueck")
zaehler = {"kalk": 0, "_kalk": 0}
alt_k, alt__k = rechnen.kalkulation, rechnen._kalkulation


def kalk(*a, **kw):
    zaehler["kalk"] += 1
    return alt_k(*a, **kw)


def _kalk(*a, **kw):
    zaehler["_kalk"] += 1
    return alt__k(*a, **kw)


def check():
    uhr = s.__dict__.get("_check_uhr")
    if uhr is not None:
        uhr.stop()
    s._check_jetzt()


rechnen.kalkulation, rechnen._kalkulation = kalk, _kalk
try:
    t = time.perf_counter()
    s.pos_modell.setData(s.pos_modell.index(0, spalte), "7")
    app.processEvents()
    nach_zelle = dict(zaehler)
    check()
    dauer = time.perf_counter() - t
finally:
    rechnen.kalkulation, rechnen._kalkulation = alt_k, alt__k
assert nach_zelle == {"kalk": 1, "_kalk": 2}, nach_zelle        # gestaffelt: Basis + Lauf, einmal
assert zaehler["kalk"] - nach_zelle["kalk"] <= 1, zaehler        # Check: nur noch die Grundwerte-Wirkung
ok(f"gestaffelter Gewinn: 1 Kalkulation je Änderung, Check ohne zweite für die Auslastung ({zaehler})")
assert dauer < GRENZE_ZELLE_CHECK, dauer
ok(f"Zelle ändern + Check, 200 Positionen gestaffelt: {dauer:.2f} s (Grenze {GRENZE_ZELLE_CHECK} s)")
mit = repr((s.pos_modell.werte, s.pos_modell.status, s.pos_modell.meterpreise, s._rechnung()))
alt_merker = rechnen.merker
rechnen.merker = lambda: __import__("contextlib").nullcontext()
try:
    s.neu_laden()
    ohne = repr((s.pos_modell.werte, s.pos_modell.status, s.pos_modell.meterpreise, s._rechnung()))
finally:
    rechnen.merker = alt_merker
assert mit == ohne
ok("Positionstabelle und Kalkulation mit Merker bitgleich wie ohne")
erst, dann = s.freigabe_punkte(), s.freigabe_punkte()
assert erst == dann and len(erst) == len(set(map(str, erst))), (erst, dann)
ok("Angebots-Check zweimal hintereinander: gleiche Punkte, keine doppelt")

# ------------------------------------------------------------------ Zeitwächter
tempo._abschnitte.clear()
with tempo.abschnitt("kurz"):
    pass
with tempo.abschnitt("fein", 0.0):
    pass


@tempo.gemessen("Dekoriert", 0.0)
def dekoriert(x):
    return x * 2


assert dekoriert(4) == 8
th = threading.Thread(target=lambda: tempo.abschnitt("Hintergrund", 0.0).__enter__())
th.start()
th.join()
namen = [n for n, _ in tempo._abschnitte]
assert namen == ["fein", "Dekoriert"], namen
ok("Abschnitte: eigene Grenze, Dekorator, Hintergrund zählt nicht")
tempo._abschnitte.clear()
FEIN_ALT = tempo.ABSCHNITT_MIN_S
s.neu_laden()
namen = {n for n, _ in tempo._abschnitte}
# kurze Schritte (unter 50 ms) stehen nicht drin; mindestens das Neuladen selbst dauert bei 200 Positionen länger
assert "Angebot neu laden" in namen, namen
import rohrlaser.angebot_fenster as af  # noqa: E402
af.FEIN, alt_fein = 0.0, af.FEIN
try:
    tempo._abschnitte.clear()
    s.neu_laden()
    namen = {n for n, _ in tempo._abschnitte}
finally:
    af.FEIN = alt_fein
for n in ("Angebot: Daten lesen", "Angebot: Positionstabelle rechnen", "Angebot: Kalkulation", "Angebot: Check",
          "Angebot: Ergebnisse anzeigen"):
    assert n in namen, (n, namen)
ok("Neuladen markiert seine Schritte für das Tempo-Protokoll")

zeilen = []
w = tempo.Waechter(tmp / "Protokoll", schreiben=zeilen.append)
w.letzte_bedienung = "Klick „OK“"
w._ort_zuletzt = "Angebot 2026-00058 › Positionen"
jetzt = time.perf_counter()
w._zuletzt = jetzt - 12
tempo._offen[:] = ["Angebot neu laden", "Angebot: Kalkulation"]
try:
    text = w.haenger_pruefen(jetzt)
    assert w.haenger_pruefen(jetzt + 1) is None          # je Hänger einmal
finally:
    tempo._offen.clear()
assert text and text.startswith("Hänger seit 12 s") and "läuft: Angebot neu laden › Angebot: Kalkulation" in text \
    and "Ort: Angebot 2026-00058" in text and "zuletzt: Klick „OK“" in text, text
w._zuletzt = jetzt
assert w.haenger_pruefen(jetzt + 2) is None
proto = tmp / "Protokoll2"
proto.mkdir()
(proto / tempo.DATEI).write_text(f"2026-11-10 10:00:00,000 {text}\n2026-11-10 10:00:05,000 15.2 s | Ort: X\n",
                                 encoding="utf-8")
auswertung = tempo.auswerten(proto)
assert "Hänger über 10 s: 1" in auswertung and "läuft: Angebot neu laden" in auswertung, auswertung
assert len(tempo.lesen(proto)) == 1
ok("Hänger-Schutz: sofort eine Zeile mit Ort und laufenden Abschnitten, Auswertung nennt sie")

# ------------------------------------------------------------------ Datendatei prüfen
lauf = PruefLauf(db.pfad)
assert lauf.warten(30) and lauf.fehler is None and lauf.dauer is not None, lauf.fehler
kaputt = tmp / "kaputt.db"
con = sqlite3.connect(kaputt)
con.execute("CREATE TABLE t (a INTEGER PRIMARY KEY, b TEXT)")
con.execute("CREATE INDEX ib ON t(b)")
con.executemany("INSERT INTO t VALUES (?, ?)", [(i, f"wert {i}" * 20) for i in range(3000)])
con.commit()
con.close()
daten = bytearray(kaputt.read_bytes())
seite = 4096
for n in range(3, min(len(daten) // seite, 40), 3):        # Seiten mitten in der Datei überschreiben
    daten[n * seite + 100:n * seite + 400] = b"\xff" * 300
kaputt.write_bytes(bytes(daten))
lauf = PruefLauf(kaputt)
assert lauf.warten(30) and lauf.fehler, "Beschädigung nicht erkannt"
ok(f"Datendatei-Prüfung: gesund ohne Befund, beschädigt erkannt ({lauf.fehler[:60]} …)")

f.close()
print("Alle Prüfungen Performance-Update 10.11. bestanden.")
