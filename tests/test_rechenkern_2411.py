"""Rechenkern, Importlogik und Geometrieverarbeitung 2.0 (Master-Auftrag Patrick 24.11.2026): Beschleunigungen nur
bitgleich, Performance-Monitoring je Verarbeitungsschritt.

Geprüft wird ohne Bildschirm:
1. leistung.py: Median und Perzentile wie statistics.quantiles (inclusive), Schritt mit Dauer/CPU/Speicher/Zählwerten,
   Fehler zählt und wird weitergereicht, STEP-Teilschritte aus der ZEITEN-Zeile, Abschnitt im Diagnose-Bericht,
   diagnose.messen trägt jede Rechnung ein, Zurücksetzen.
2. Mengenläufe teilen Schnittzeiten: jeder Feldzugriff von _schneidzeit_teile_rechnen auf Position und Kopf wird über
   die Staffeln der Testangebote S/M/L und die Kontur-Angebote des Regressionstests (Dynamik, Gravur, Sattel)
   verfolgt – nie stueck/abruf_basis und keins der Kopffelder KOPF_OHNE_SCHNITTZEIT, nie die ganze Position (items,
   Schleife, repr). Damit ist die Schnittzeit von der Stückzahl unabhängig.
3. Staffeln mit und ohne Teilen (SCHNITTZEITEN_TEILEN): alle Zeilen Zahl für Zahl gleich (repr), und mit Teilen
   werden die Schnittzeiten seltener gerechnet (je Position und Kopf der Stufe einmal).
4. STEP: Boolesche Operationen im Parallelmodus (step_geometrie.BOOLESCH_PARALLEL) ergeben für ein offenes U-Profil
   (viele Boolesche Operationen) dieselben Messwerte wie nacheinander (RL_BOOLESCH_SEQ=1), jede Zahl.
Aufruf: python tests/test_rechenkern_2411.py [--ohne-step]
"""
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import testangebote_gross  # noqa: E402
from rohrlaser import diagnose, leistung, rechenmerker, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


# ---------------------------------------------------------------------------------------------- 1. leistung
werte = [0.31, 0.05, 1.7, 0.2, 0.9, 0.44, 2.5, 0.12, 0.6, 0.33, 0.07]
q = statistics.quantiles(werte, n=100, method="inclusive")
for p in (90, 95, 99):
    assert abs(leistung.perzentil(werte, p) - q[p - 1]) < 1e-12, (p, leistung.perzentil(werte, p), q[p - 1])
assert leistung.perzentil(werte, 50) == statistics.median(werte)
assert leistung.perzentil([], 50) is None and leistung.perzentil([3.0], 95) == 3.0
k = leistung.kennzahlen(werte)
assert k["n"] == 11 and k["max"] == 2.5 and k["min"] == 0.05 and k["median"] == statistics.median(werte)
ok("Median und Perzentile wie statistics.quantiles (inclusive)")

leistung.zuruecksetzen()
for i in range(5):
    with leistung.schritt("Test: Schritt", objekte=10) as s:
        sum(range(20000))
        s.zaehlen(konturen=3)
try:
    with leistung.schritt("Test: Schritt"):
        raise KeyError("absichtlich")
except KeyError:
    pass
else:
    raise AssertionError("Ausnahme verschluckt")
leistung.erfassen("Test: von außen", 2.0, koerper=4, warnung="langsam")
leistung.erfassen("Test: von außen", float("nan"))          # kein Messwert
st = leistung.stand()
e = st["Test: Schritt"]
assert e["anzahl"] == 6 and e["fehler"] == 1, e
assert e["zahlen"] == {"objekte": 50, "konturen": 15}, e["zahlen"]
assert e["median_s"] is not None and e["p95_s"] >= e["median_s"] and e["max_s"] >= e["p95_s"]
assert e["cpu_s"] is not None and 0 < e["cpu_auslastung"] <= 1.5, e
assert e["erster_start"] <= e["letztes_ende"]
a = st["Test: von außen"]
assert a["anzahl"] == 1 and a["cpu_s"] is None and a["warnungen"] == 1 and a["zahlen"] == {"koerper": 4}
ok("Schritt: Anzahl, Dauer, CPU, Zählwerte, Fehler, Warnung, Messwert von außen")

leistung.zuruecksetzen()
leistung.step_zeiten({"koerper_n": 48, "koerper_s": 30.5, "prozesse": 3, "dateien": {
    "a.step": {"lesen": 1.0, "abschluss": 2.0, "schritte": {"lesen_s": 0.4, "uebertragen_s": 0.3, "naehen_s": 0.1,
                                                           "struktur_s": 0.05, "kopien_s": 0.02, "verschoben": 3}},
    "b.step": {"ganz": 5.0, "schritte": {"lesen_s": 0.2, "messen_s": 4.1, "gemessen": 2, "abschluss_s": 0.3}}}},
    dauer_s=40.0, dateien=2, mb=3.5)
st = leistung.stand()
assert st["STEP-Import gesamt"]["summe_s"] == 40.0 and st["STEP-Import gesamt"]["zahlen"]["koerper"] == 48
assert st["STEP: Datei lesen"]["anzahl"] == 2 and abs(st["STEP: Datei lesen"]["summe_s"] - 0.6) < 1e-12
assert st["STEP: Körper messen"]["zahlen"] == {"koerper": 2}
assert st["STEP: Baugruppe auswerten"]["anzahl"] == 2           # a: abschluss (verteilt), b: abschluss_s
assert st["STEP: Körper verteilt gemessen"]["zahlen"] == {"koerper": 48}
leistung.step_zeiten({}, dauer_s=1.0)                            # ohne ZEITEN-Zeile: nur die Gesamtdauer
leistung.step_zeiten(None)
ok("STEP-Teilschritte aus der ZEITEN-Zeile der Messung")

diagnose.zuruecksetzen()
assert leistung.stand() == {}
with diagnose.messen("Kalkulation"):
    sum(range(1000))
bericht = diagnose.bericht()
assert "Leistung je Verarbeitungsschritt" in bericht and "Kalkulation" in bericht.split("Leistung je")[1]
assert leistung.stand()["Kalkulation"]["anzahl"] == 1
ok("diagnose.messen trägt ein, Abschnitt im Diagnose-Bericht, Zurücksetzen gemeinsam")

# --------------------------------------------------------------------------- 2. Feldzugriffe der Schnittzeit
gelesen_p, gelesen_k, ganz = set(), set(), []


class Spur(dict):
    """Position bzw. Kopf, die jeden Feldzugriff aufschreibt."""
    def __init__(self, d, ziel):
        super().__init__(d)
        self._ziel = ziel

    def __getitem__(self, k):
        self._ziel.add(k)
        return dict.__getitem__(self, k)

    def get(self, k, d=None):
        self._ziel.add(k)
        return dict.get(self, k, d)

    def __contains__(self, k):
        self._ziel.add(k)
        return dict.__contains__(self, k)

    def _ganz(self, art):
        ganz.append(art)

    def items(self):
        self._ganz("items")
        return dict.items(self)

    def keys(self):
        self._ganz("keys")
        return dict.keys(self)

    def values(self):
        self._ganz("values")
        return dict.values(self)

    def __iter__(self):
        self._ganz("iter")
        return dict.__iter__(self)

    def __repr__(self):
        self._ganz("repr")
        return dict.__repr__(self)

    def copy(self):
        self._ganz("copy")
        return dict.copy(self)


orig = rechnen._schneidzeit_teile_rechnen
anzahl_gerechnet = [0]


def verfolgt(p, kopf, *a):
    anzahl_gerechnet[0] += 1
    return orig(Spur(p, gelesen_p) if type(p) is dict else p, Spur(kopf, gelesen_k) if type(kopf) is dict else kopf,
                *a)


def leeren():
    rechenmerker.alle_leeren()
    m = getattr(rechnen, "_KALK_MERK", None)
    if m is not None:
        m.leeren()


tmp = Path(tempfile.mkdtemp(prefix="rk2411_"))
db = Datenbank(tmp / "rk.db")
kx, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
angebote = []
for g in ("S", "M", "L"):
    aid = testangebote_gross.anlegen(db, g)
    kopf, pos = db.angebot(aid), db.positionen(aid)
    db.ergebnis_speichern(aid, rechnen.optimieren(kopf, pos, kx, tab, einst))
    kopf = db.angebot(aid)
    angebote.append((g, kopf, pos, db.staffeln(aid), rechnen.einstellungen_angebot(kopf, einst)))

rechnen._schneidzeit_teile_rechnen = verfolgt
try:
    for g, kopf, pos, stufen, e in angebote:
        leeren()
        staffeln.rechnen_alle(kopf, pos, stufen, kx, tab, e)
    # Kontur-Angebote des Regressionstests: Dynamik-Maschinen, Gravur, Sattel, Gehrungen
    import test_regression_ergebnisse as reg
    for ang in reg.KONTUR_ANGEBOTE:
        for menge in (None, 7):
            leeren()
            reg.kontur_rechnen(ang, db, staffel=menge)       # legt an, optimiert und kalkuliert
finally:
    rechnen._schneidzeit_teile_rechnen = orig
assert anzahl_gerechnet[0] > 100, anzahl_gerechnet
verboten_p = gelesen_p & set(rechnen.SCHNITTZEIT_OHNE_MENGE)
verboten_k = gelesen_k & set(rechnen.KOPF_OHNE_SCHNITTZEIT)
assert not verboten_p, f"Schnittzeit liest die Stückzahl: {verboten_p}"
assert not verboten_k, f"Schnittzeit liest Kopffelder außerhalb des Schlüssels: {verboten_k}"
assert not ganz, f"Schnittzeit liest Position/Kopf als Ganzes: {sorted(set(ganz))}"
assert {"laenge", "profil_id", "werkstoff_id"} <= gelesen_p and "maschine" in gelesen_k
ok(f"Schnittzeit: {anzahl_gerechnet[0]} Rechnungen verfolgt, {len(gelesen_p)} Positionsfelder und "
   f"{len(gelesen_k)} Kopffelder gelesen, nie Stückzahl oder ausgenommene Kopffelder")

# ------------------------------------------------------------------- 3. Staffeln mit und ohne Teilen bitgleich
for g, kopf, pos, stufen, e in angebote:
    ergebnisse = {}
    for teilen in (False, True):
        rechnen.SCHNITTZEITEN_TEILEN = teilen
        anzahl_gerechnet[0] = 0
        rechnen._schneidzeit_teile_rechnen = lambda *a: (anzahl_gerechnet.__setitem__(0, anzahl_gerechnet[0] + 1),
                                                         orig(*a))[1]
        try:
            leeren()
            ergebnisse[teilen] = (repr(staffeln.rechnen_alle(kopf, pos, stufen, kx, tab, e)), anzahl_gerechnet[0])
        finally:
            rechnen._schneidzeit_teile_rechnen = orig
            rechnen.SCHNITTZEITEN_TEILEN = True
    assert ergebnisse[True][0] == ergebnisse[False][0], f"Staffeln {g} mit Teilen anders"
    n_aus, n_an = ergebnisse[False][1], ergebnisse[True][1]
    aktiv = sum(1 for p in pos if staffeln.position_aktiv(p))
    # je Position mindestens einmal; mehr, wenn sich der Kopf einer Stufe ändert (z. B. Fracht je Menge)
    assert aktiv <= n_an < n_aus or len(stufen) < 2, (g, n_aus, n_an, aktiv)
    ok(f"Staffeln {g} ({len(stufen)} Stufen): bitgleich, Schnittzeiten {n_aus} → {n_an} gerechnet")

# --------------------------------------------------------------------- 4. STEP: Boolesche Operationen parallel
if "--ohne-step" not in sys.argv:
    messen = HIER.parent / "programm" / "step_messung" / "step_messen.py"
    datei = HIER / "step_offen" / "OR1_U_offen_RE60x40x3.step"
    out = {}
    for name, seq in (("parallel", ""), ("nacheinander", "1")):
        js, txt = tmp / f"{name}.json", tmp / f"{name}.txt"
        netze = tmp / f"{name}_netze"
        netze.mkdir()
        env = dict(os.environ, PYTHONHASHSEED="0", RL_BOOLESCH_SEQ=seq)
        r = subprocess.run([sys.executable, str(messen), "--ausgabe", str(txt), "--json", str(js), "--netze",
                            str(netze), "--prozesse", "1", str(datei)], env=env, capture_output=True, text=True,
                           timeout=900)
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
        d = json.loads(js.read_text(encoding="utf-8"))
        d.pop("erzeugt", None)
        out[name] = (d, txt.read_text(encoding="utf-8"),
                     sorted((p.name, p.read_bytes()) for p in netze.iterdir()))
    assert out["parallel"][0] == out["nacheinander"][0], "Messwerte (JSON) verschieden"
    assert out["parallel"][1] == out["nacheinander"][1], "Messtabelle verschieden"
    assert out["parallel"][2] == out["nacheinander"][2], "3D-Netze verschieden"
    ok("STEP offenes U-Profil: Boolesche Operationen parallel = nacheinander (JSON, Tabelle, Netze)")

print("Alle Prüfungen bestanden.")
