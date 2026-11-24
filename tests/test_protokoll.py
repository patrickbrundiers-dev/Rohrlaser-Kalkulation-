"""Prüft das Fehlerprotokoll (protokoll.py): ein unerwarteter Fehler in einer Knopf-Aktion landet in
Daten/Protokoll/fehler.log, wird gemeldet (Text + Details) und das Programm läuft weiter.

Aufruf: python tests/test_protokoll.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from rohrlaser import protokoll  # noqa: E402

app = QApplication.instance() or QApplication([])
ordner = Path(tempfile.mkdtemp()) / "Protokoll"
gemeldet = []
pfad = protokoll.einrichten(ordner, zeigen=lambda text, details: gemeldet.append((text, details)))
assert pfad == ordner / "fehler.log"
protokoll.info("Start Test")


def kaputt():
    raise TypeError("can't multiply sequence by non-int of type 'float'")


knopf = QPushButton("Optimieren")
knopf.clicked.connect(kaputt)
sys.stderr = open(os.devnull, "w")          # wie im Programm ohne Konsole
knopf.click()                                # Fehler im Slot: Qt ruft sys.excepthook
app.processEvents()
sys.stderr = sys.__stderr__
assert len(gemeldet) == 1 and gemeldet[0][0].startswith("TypeError: can't multiply"), gemeldet
assert "def kaputt" in gemeldet[0][1] or "kaputt" in gemeldet[0][1]
inhalt = pfad.read_text(encoding="utf-8")
assert "Start Test" in inhalt and "Unerwarteter Fehler" in inhalt and "TypeError" in inhalt
t = threading.Thread(target=kaputt)
t.start()
t.join()
assert len(gemeldet) == 2 and pfad.read_text(encoding="utf-8").count("Unerwarteter Fehler") == 2
print("OK     Fehler in Knopf-Aktion und Hintergrund-Thread: gemeldet, in fehler.log protokolliert, Programm läuft weiter")
print("OK: Fehlerprotokoll")
