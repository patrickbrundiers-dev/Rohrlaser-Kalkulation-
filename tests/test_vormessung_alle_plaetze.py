"""Vormessung für alle Plätze und 3D-Vorschau ohne Warten (Patrick 18.11.2026: „Ist es von Vorteil, die Anfragen im
Hintergrund zu importieren oder zu rechnen? … wenn ich die STEP in der Vorschau ansehe, dass diese nicht erst geladen
werden muss“). Mit nachgebauter Messung (tests/vormessung_nachbau.py), nur erfundene Dateien.

  V1 Einträge des Zwischenspeichers, die eine Vormessung benutzt hat, kommen in die Akte (_messung); ein anderer Platz
     übernimmt nur fehlende Einträge in seinen eigenen Zwischenspeicher.
  V2 Die Vormessung legt ihre Einträge in der Akte ab (anfrage_vorab.messen mit job["ablage"]).
  V3 Anderer Platz: 3D-Vorschau einer vorgemessenen STEP kommt aus dem Zwischenspeicher (gleiche Argumente wie
     Kalkulieren), es wird nicht neu gemessen; Kalkulieren übernimmt die Vormessung ebenfalls.

Aufruf: python tests/test_vormessung_alle_plaetze.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import inspect
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import anfrage_vorab as av  # noqa: E402
from rohrlaser import anfragen  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import anfragen_seite as aseite  # noqa: E402
from rohrlaser import step, step_einstellungen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
MESS = [sys.executable, str(HIER / "vormessung_nachbau.py")]


def eintrag(ordner, name, alter_s=0):
    e = Path(ordner) / name
    e.mkdir(parents=True)
    (e / "ergebnis.json").write_text("{}", encoding="utf-8")
    if alter_s:
        t = time.time() - alter_s
        os.utime(e, (t, t))
    return e


# ------------------------------------------------------------------ V1 ablegen und übernehmen
c1, akte1, c2 = tmp / "v1" / "cache_a", tmp / "v1" / "akte" / av.MESSUNG, tmp / "v1" / "cache_b"
seit = time.time()
eintrag(c1, "alt", alter_s=3600)                     # von einer anderen Anfrage, nicht benutzt
eintrag(c1, "neu1")
eintrag(c1, "neu2")
(c1 / "halb.neu").mkdir()                             # unfertiger Eintrag: nie kopieren
assert av.messung_ablegen(c1, akte1, seit) == 2 and sorted(p.name for p in akte1.iterdir()) == ["neu1", "neu2"]
assert av.messung_ablegen(c1, akte1, seit) == 0       # schon da
eintrag(c2, "neu1")
(c2 / "neu1" / "eigen.txt").write_text("bleibt", encoding="utf-8")
assert av.messung_uebernehmen(akte1, c2) == 1 and sorted(p.name for p in c2.iterdir()) == ["neu1", "neu2"]
assert (c2 / "neu1" / "eigen.txt").exists() and (c2 / "neu2" / "ergebnis.json").exists()
assert av.messung_uebernehmen(tmp / "fehlt", c2) == 0 and av.messung_uebernehmen(akte1, None) == 0
assert av.cache_aus(["--prozesse", "1", "--cache", "X"]) == Path("X") and av.cache_aus(["--cache"]) is None
ok("V1 benutzte Einträge kommen in die Akte, ein anderer Platz übernimmt nur fehlende")

# ------------------------------------------------------------------ V2 Vormessung legt in der Akte ab
quelle = tmp / "v2"
quelle.mkdir()
(quelle / "rahmen.step").write_text("ISO-10303-21; Rahmen", encoding="utf-8")
anf = anfragen.Anfrage("Anfrage Rahmen", quelle, [quelle / "rahmen.step"], None)
cache_a, ablage = tmp / "v2" / "cache", tmp / "v2" / "akte" / av.MESSUNG
job = dict(befehl=MESS, args=["--prozesse", "1", "--cache", str(cache_a), "--flachstahl-bis", "0"], ablage=str(ablage))
assert av.messen(job, anf) == []
assert len(list(cache_a.iterdir())) == 1 and [p.name for p in ablage.iterdir()] == [p.name for p in cache_a.iterdir()
                                                                                     if p.is_dir()]
ok("V2 die Vormessung legt ihre Einträge zusätzlich in der Akte ab")

# ------------------------------------------------------------------ V3 anderer Platz: Vorschau sofort
db = Datenbank(tmp / "platz_b" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO2")
a, _ = abl.anlegen(dict(quelle="ordner", betreff="Anfrage Rahmen"), [quelle / "rahmen.step"], "r1")
fenster = Hauptfenster(db, tmp / "platz_b", stumm=True)
seite = fenster.anfragen_seite
seite.ablage = lambda: abl
seite.neu_laden()
step.messprogramm = lambda ordner=None: list(MESS)
# Platz A hat vorgemessen (gleiche Argumente wie die Vorschau, eigener Zwischenspeicher), Ergebnis liegt in der Akte
args_a = av.vorschau_argumente(db, None)
i = args_a.index("--cache")
args_a[i + 1] = str(tmp / "platz_a_cache")
av.messen(dict(befehl=MESS, args=args_a, ablage=str(a.pfad / av.MESSUNG)), anf)
assert (a.pfad / av.MESSUNG).is_dir() and not step_einstellungen.cache_ordner(db).exists()
d = next(x for x in abl.neu_lesen(a).dateien() if x["name"] == "rahmen.step")
v = seite.vorschau(abl.neu_lesen(a), d)
v.step_warten(60)
log = step_einstellungen.cache_ordner(db).parent / "aufrufe.txt"
aufruf = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
assert aufruf["treffer"] == 1 and "--cache" in aufruf["args"] and "--flachstahl-bis" in aufruf["args"], aufruf
assert type(v.flaeche.currentWidget()).__name__ == "Ansicht3D", v.flaeche.currentWidget()
assert "self.messung_uebernehmen(a)" in inspect.getsource(aseite.AnfragenSeite.kalkulieren)
ok("V3 anderer Platz: die 3D-Vorschau einer vorgemessenen STEP kommt aus dem Zwischenspeicher, Kalkulieren übernimmt "
   "die Vormessung auch")
print("Alle Tests bestanden.")
