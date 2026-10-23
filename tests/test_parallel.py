"""Schnittpläne auf Hilfsprozessen (rohrlaser.parallel, Performance-Audit F2): gleiches Ergebnis wie nacheinander
gerechnet, auch mit dem Vergleich anderer Lieferlängen (Zuschnitt), sichere Rückfallebene, Abbruch.

Aufruf: python tests/test_parallel.py
"""
import json
import random
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import optimierung as opt, parallel, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

PROFILE = ["RR 42,4x2,0", "QR 40x40x3", "RE 60x40x3", "RE 120x60x4"]
WERKSTOFFE = ["S235-10219", "S355-10219"]


def ok(text):
    print("OK    ", text)


db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
a = db.angebot_neu(dict(kunde="Parallel", maschine="T11", stange=6000))
rnd = random.Random(7)
for i in range(80):
    db.position_neu(a, dict(pos=10 * (i + 1), artikel=f"P{i}", profil_id=PROFILE[i % 4],
                            werkstoff_id=WERKSTOFFE[(i // 4) % 2], laenge=float(rnd.randint(150, 2900)),
                            stueck=rnd.choice([2, 5, 10, 20]), schneidweg=300.0, einstiche=2,
                            **({"b_gerade": "nein"} if i % 6 == 5 else {})))
kopf, pos = db.angebot(a), db.positionen(a)
k, tab = db.kontext(), db.tabellen()
einst = dict(rechnen.einstellungen_angebot(kopf, db.einstellungen()), laenge_vergleich="ja")


def rechnen_mit(n_prozesse):
    parallel.anzahl_prozesse = lambda auftraege: n_prozesse if len(auftraege) >= 2 else 0
    meldungen = []
    erg = rechnen.optimieren(kopf, pos, k, tab, einst, fortschritt=lambda *x: meldungen.append(x))
    return json.dumps(erg, sort_keys=True, default=repr), meldungen


original = parallel.anzahl_prozesse
nacheinander, _ = rechnen_mit(0)
assert not parallel._helfer
verteilt, meldungen = rechnen_mit(2)
assert len(parallel._helfer) == 2, "zwei Hilfsprozesse"
assert verteilt == nacheinander, "gleiches Ergebnis wie nacheinander gerechnet"
assert any("Schnittpläne:" in m[2] for m in meldungen)
ok("2 Hilfsprozesse: Ergebnis (mit Lieferlängen-Vergleich und Zuschnitt) gleich wie nacheinander")
assert getattr(opt.vorgerechnet, "gruppen", None) is None, "Vorgerechnetes nach dem Lauf verworfen"
assert rechnen_mit(2)[0] == nacheinander
ok("zweiter Lauf mit denselben Hilfsprozessen gleich")

# Abbruch über die Fortschrittsanzeige: Ausnahme kommt an, Hilfsprozesse beendet
parallel.anzahl_prozesse = lambda auftraege: 2


class Abbruch(Exception):
    pass


def abbrechen(schritt, schritte, text):
    if "Schnittpläne:" in text:
        raise Abbruch()


try:
    rechnen.optimieren(kopf, pos, k, tab, einst, fortschritt=abbrechen)
    raise AssertionError("Abbruch nicht weitergegeben")
except Abbruch:
    pass
assert not parallel._helfer and getattr(opt.vorgerechnet, "gruppen", None) is None
ok("Abbruch: Ausnahme weitergegeben, Hilfsprozesse beendet")

# Hilfsprozess startet nicht: wie bisher selbst rechnen
alt_befehl, alt_warten = parallel._befehl, parallel.START_WARTEN
parallel._befehl = lambda adresse, schluessel: [sys.executable, "-c", "pass"]
parallel.START_WARTEN = 3
try:
    assert rechnen_mit(2)[0] == nacheinander and not parallel._helfer
finally:
    parallel._befehl, parallel.START_WARTEN = alt_befehl, alt_warten
ok("Hilfsprozess startet nicht: selbst gerechnet, gleiches Ergebnis")

parallel.anzahl_prozesse = original
klein = [opt.Gruppe("RR", "S", 6000, 5, 50, 2, 0, teile=[None] * 10)] * 3
assert original(klein) == 0, "kleine Angebote ohne Hilfsprozesse"
ok(f"unter {parallel.PARALLEL_AB_TEILE} Teilen ohne Hilfsprozesse")
parallel.beenden()
print("Alle Prüfungen bestanden.")
