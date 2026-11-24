"""UI-Modernisierung U6 (Patrick 12.11.2026): Einstellungen mit weniger Rollen.

Prüft: lange Karten (Funktionen) stehen auf breiten Seiten in zwei Zeilenspalten, ohne waagrechten Bildlauf; die
Suche filtert in beiden Hälften und klappt Expertenkarten auf; schmal wieder eine Spalte; Werte speichern wie vorher.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def warten():
    for _ in range(3):
        QApplication.processEvents()


po = Path(tempfile.mkdtemp(prefix="einst_teilen_")) / "Rohrlaser-Angebotskalkulation"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
f = Hauptfenster(db, po, stumm=True)
f.resize(1366, 728)
f.show()
f.reiter.setCurrentWidget(f.bereich)
s = next(x for x in f.einstellungen.seiten if x.schluessel == "e_funktionen")
f.bereich.zeigen(s)
warten()
box = next(b for b in s.boxen if b.title() == "Funktionen")
form, form2, liste = s._formulare[id(box)]
assert s.geteilt and form.rowCount() and form2.rowCount() and form.rowCount() + form2.rowCount() == len(liste)
assert s.horizontalScrollBar().maximum() == 0, "kein waagrechter Bildlauf"
assert {e.name for e, fo, _, _ in s.zeilen if fo is form2}, "Suche kennt die rechte Hälfte"
ok("1366 px: lange Karte Funktionen in zwei Zeilenspalten, ohne waagrechten Bildlauf")

rechts = next(e for e, fo, _, b in s.zeilen if fo is form2)
s.filtern(rechts.titel.split()[0])
warten()
assert any(fo is form2 and fo.isRowVisible(z) for e, fo, z, b in s.zeilen if e is rechts)
s.filtern("")
warten()
ok("Suche findet Einstellungen in der rechten Hälfte")

f.resize(1024, 700)
warten()
assert not any(s._formulare[id(b)][1].rowCount() for b in s.boxen), "schmal: eine Spalte"
f.resize(1920, 1040)
warten()
hoehe = s.widget().sizeHint().height()
for teilen, zwei in ((True, False), (False, True)):       # die gewählte Anordnung ist die niedrigste
    s.teilen(teilen)
    s._anordnen(zwei)
    s.widget().layout().activate()
    assert hoehe <= s.widget().sizeHint().height() + 1, (teilen, zwei, hoehe, s.widget().sizeHint().height())
s._stufe = None
s.resize(s.size())
f.resize(1921, 1040)
warten()
assert s.horizontalScrollBar().maximum() == 0
ok("1024 px eine Spalte; 1920 px die Anordnung mit dem wenigsten Rollen")

w = s.felder[rechts.name]
if hasattr(w, "setChecked"):
    alt = w.isChecked()
    w.setChecked(not alt)
    warten()
    assert db.einstellung(rechts.name) == ("ja" if not alt else "nein"), db.einstellung(rechts.name)
    w.setChecked(alt)
    ok("Schalter in der rechten Hälfte speichert wie vorher")
print("Alle Tests OK")
