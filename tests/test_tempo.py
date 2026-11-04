"""Zeitwächter (Optimierungsplan 04.11.2026, A3): langsame Schritte landen mit Ort und Bedienung in tempo.log.

Geprüft wird ohne Bildschirm:
- eine Blockade der Oberfläche über der Grenze wird eingetragen (Dauer, Ort, letzte Bedienung), kurze nicht,
- ein Klick auf einen Knopf erscheint als „Klick „Text““, im Quelltext-Betrieb auch die Programmfunktion,
- tempo.log wird gelesen und zusammengefasst, das Support-Paket enthält tempo.log und tempo.txt,
- Hauptfenster.tempo_ort nennt Reiter, Angebot mit Positionen/Teilen und Unterreiter.
Aufruf: python tests/test_tempo.py
"""
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from rohrlaser import support, tempo  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
ordner = tmp / "Protokoll"


def warten(ms):
    QTest.qWait(ms)


# ------------------------------------------------------------------ Blockade erkennen
w = tempo.Waechter(ordner, kontext=lambda: "Angebote › Test", grenze_s=0.3, takt_ms=50)
assert w.starten()
warten(200)
assert not w.eintraege, w.eintraege
ok("ohne Blockade kein Eintrag")


def langsam_rechnen():
    t = time.perf_counter()
    while time.perf_counter() - t < 0.6:
        sum(range(2000))


knopf = QPushButton("&Optimieren")
knopf.clicked.connect(langsam_rechnen)
knopf.resize(120, 30)
knopf.show()
warten(100)
QTest.mouseClick(knopf, Qt.LeftButton)
warten(200)
assert len(w.eintraege) == 1, w.eintraege
e = w.eintraege[0]
assert "Ort: Angebote › Test" in e and "zuletzt: Klick „Optimieren“" in e, e
dauer = float(e.split(" s")[0])
assert 0.4 <= dauer <= 1.5, e
assert "in: " not in e, e                   # nur Programmfunktionen (rohrlaser/…) werden genannt, keine Testdatei
ok(f"Blockade nach Klick eingetragen: {e}")

kurz = QPushButton("Kurz")
kurz.clicked.connect(lambda: time.sleep(0.1))
kurz.show()
QTest.mouseClick(kurz, Qt.LeftButton)
warten(200)
assert len(w.eintraege) == 1, w.eintraege
ok("kurze Aktion (0,1 s) bleibt ohne Eintrag")

QTest.keyClick(kurz, Qt.Key_Return)
assert w.letzte_bedienung == "Taste Return in QPushButton", w.letzte_bedienung
ok(f"Tastendruck als Bedienung gemerkt: {w.letzte_bedienung}")

knopf2 = QPushButton("Rechnen")
knopf2.clicked.connect(langsam_rechnen)
knopf2.show()
QTest.mouseClick(knopf2, Qt.LeftButton)
warten(200)
assert len(w.eintraege) == 2 and "Klick „Rechnen“" in w.eintraege[-1], w.eintraege
ok("zweite Blockade mit eigener Bedienung")
w.stoppen()

# ------------------------------------------------------------------ Datei lesen, auswerten, Support-Paket
liste = tempo.lesen(ordner)
assert len(liste) == 2 and liste[0]["ort"] == "Angebote › Test" and liste[0]["bedienung"] == "Klick „Optimieren“", liste
text = tempo.auswerten(ordner)
assert text.startswith("2 langsame Schritte") and "Angebote › Test – Klick „Optimieren“" in text, text
ok("tempo.log gelesen und zusammengefasst")
assert tempo.auswerten(tmp / "leer").startswith("Keine langsamen Schritte")
ok("ohne Datei: Hinweis „keine langsamen Schritte“")

db = Datenbank(tmp / "rohrlaser.db")
e = support.erstellen(db, protokoll_ordner=ordner, system=[], lizenz_text="Test")
assert "tempo.log" in e["dateien"] and "tempo.txt" in e["dateien"], e["dateien"]
with zipfile.ZipFile(e["pfad"]) as z:
    assert z.read("tempo.txt").decode("utf-8").startswith("2 langsame Schritte")
ok("Support-Paket enthält tempo.log und tempo.txt")

# ------------------------------------------------------------------ Ort im Hauptfenster
f = Hauptfenster(db, tmp, stumm=True)
f.show()
a = db.angebot_neu(dict(kunde="Tempo", kundennr="K-1", maschine="T11", stange=6000))
db.position_neu(a, dict(pos=10, artikel="A1", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=500.0,
                        stueck=8))
db.position_neu(a, dict(pos=20, artikel="A2", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=700.0,
                        stueck=4))
s = f.angebot_oeffnen(a)
warten(50)
ort = f.tempo_ort()
assert s.titel() in ort and "(2 Pos., 12 Teile)" in ort and "Positionen" in ort, ort
ok(f"Ort im Angebot: {ort}")
f.reiter.setCurrentWidget(f.angebote)
assert f.tempo_ort().startswith("Angebote"), f.tempo_ort()
ok("Ort in der Angebotsliste")
assert getattr(f, "tempo", None) is None
ok("Tests (stumm): kein Zeitwächter im Hauptfenster")
print("Alle Prüfungen Zeitwächter bestanden.")
