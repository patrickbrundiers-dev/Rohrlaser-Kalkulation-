"""Zeitlimit passend zum Hintergrund-Messen (Vorschlag M4, Patrick 07.11.2026): Vorgabe 600 s statt 120 s (alte Vorgabe
wird einmalig angehoben, von Hand geänderte Werte bleiben), und ein Körper über dem Zeitlimit wird vereinfacht gemessen
(Hüllmaß, Volumen, als Frästeil/Zukauf, gelb) statt gar nicht. Langsam macht ihn die Testhilfe
STEP_MESSEN_TEST_LANGSAM="Datei:Körper:Sekunden".

Aufruf: python tests/test_zeitlimit_vereinfacht.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
MESSEN = HIER.parent / "programm" / "step_messung" / "step_messen.py"
RAHMEN = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
TMP = Path(tempfile.mkdtemp())

from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG  # noqa: E402
from rohrlaser.step_einstellungen import mess_argumente  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Vorgabe und einmalige Anhebung
assert EINSTELLUNG["step_zeitlimit"].vorgabe == 600
db = Datenbank(TMP / "neu.db")
assert db.einstellung("step_zeitlimit") == 600
assert "600" in " ".join(mess_argumente(db)), mess_argumente(db)
for alt, erwartet in ((120, 600), (90, 90), (1800, 1800)):
    pfad = TMP / f"alt_{alt}.db"
    d = Datenbank(pfad)
    d.einstellung_setzen("step_zeitlimit", alt)
    d.einstellung_setzen("zeitlimit_stand", "")          # Datei von vor 0.9.274
    d.con.close()
    assert Datenbank(pfad).einstellung("step_zeitlimit") == erwartet, (alt, Datenbank(pfad).einstellung("step_zeitlimit"))
ok("Zeitlimit-Vorgabe 600 s; alte Vorgabe 120 s wird einmalig 600 s, eigene Werte (90 s, 1800 s) bleiben")

# ------------------------------------------------------------------ Körper über dem Zeitlimit: vereinfacht gemessen
aus = TMP / "r.txt"
umgebung = dict(os.environ, STEP_MESSEN_TEILEN_AB="99", STEP_MESSEN_TEST_LANGSAM=f"{RAHMEN.name}:3:30")
r = subprocess.run([sys.executable, str(MESSEN), "--ausgabe", str(aus), "--prozesse", "1", "--zeitlimit", "4",
                    str(RAHMEN)], env=umgebung, capture_output=True, text=True, timeout=600)
assert r.returncode in (0, 1), r.stderr[-2000:]
mw = {str(m["koerper"]): m for m in step.lies_messwerte(aus)}
k3 = mw["3"]
assert k3.get("profilform") == "Frästeil" and not k3.get("fehler"), k3
assert "vereinfacht gemessen (Zeitlimit 4 s überschritten)" in str(k3.get("hinweise")), k3.get("hinweise")
masse = sorted(float(x) for x in str(k3["huelle"]).split("|"))
assert abs(masse[-1] - 500) < 1 and abs(masse[0] - 40) < 1, masse
assert step.ampel(k3)[0] == "gelb", step.ampel(k3)
assert mw["4"].get("profilform") == "Frästeil", "K4 ist eine Kopie von K3 (gleiche Form)"
assert all(m.get("profilform") == "Quadratrohr" for n, m in mw.items() if n in ("1", "2", "6")), \
    [(n, m.get("profilform")) for n, m in mw.items()]
ok("Körper über dem Zeitlimit: vereinfacht als Frästeil (Hüllmaß 500 × 40 × 40, Volumen), gelb mit Hinweis; "
   "die übrigen Körper normal gemessen")
print("Zeitlimit vereinfacht: alle Tests bestanden.")
