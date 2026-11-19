"""Klick bearbeitet (Patrick 19.11.2026): In der Kundenliste und bei Artikelnummer/Bezeichnung der Positionen ging
Bearbeiten erst nach dem Lostippen. Jetzt öffnet ein Klick in die gewählte Zelle sie (SelectedClicked), Doppelklick
auf die Bezeichnung bearbeitet direkt."""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtWidgets import QAbstractItemView, QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
KLICK = QAbstractItemView.SelectedClicked

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
f.resize(1400, 860)
f.show()
assert f.kunden.ansicht.editTriggers() & KLICK, "Kundenliste: Klick in die gewählte Zeile bearbeitet"
assert all(s.ansicht.editTriggers() & KLICK or getattr(s, "admin_gesperrt", False) for s in f.seiten), \
    "alle Stammdaten-Tabellen (außer vom Admin gesperrte)"
print("OK     Kundenliste und alle Stammdaten: Klick in die gewählte Zelle bearbeitet")

aid = beispiel_angebot.anlegen(db)
f.angebot_oeffnen(aid)
seite = f.offen[aid]
app.processEvents()
v = seite.pos_ansicht
assert v.editTriggers() & KLICK
spalte = next(c for c in range(seite.pos_modell.columnCount()) if seite.pos_modell.name(c) == "bezeichnung")
i = seite.pos_modell.index(0, spalte)
v.setCurrentIndex(i)
seite._doppelklick(i)
assert v.state() == QAbstractItemView.EditingState, "Doppelklick auf die Bezeichnung bearbeitet direkt"
print("OK     Positionen: Klick in die gewählte Zelle und Doppelklick auf die Bezeichnung bearbeiten")
print("OK: Klick bearbeitet")

# Einstellungen (Patrick 19.11.2026: Experten-Einstellungen beim Öffnen nicht richtig sichtbar)
from PySide6.QtWidgets import QGroupBox  # noqa: E402
from rohrlaser.einstellungen_ordnung import SEITEN  # noqa: E402
s = next(x for x in SEITEN if x.schluessel == "e_kosten")
f.einstellung_zeigen(next(a.namen[0] for a in s.abschnitte if a.experte))
app.processEvents()
es = f.bereich.unter.currentWidget()
experte = [b for b in es.findChildren(QGroupBox) if b.isCheckable()]
assert experte and all(not b.isChecked() and b.height() <= b.fontMetrics().height() + 10 for b in experte), \
    "zugeklappter Expertenabschnitt: nur die Überschrift, keine leere Karte"
experte[0].setChecked(True)
app.processEvents()
assert experte[0].height() > 50
name = next(e.name for e, _, _, b in es.zeilen if b is experte[0])
stern, feld = es.sterne[name], es.felder[name]
abstand = stern.mapTo(es, stern.rect().topLeft()).x() - feld.mapTo(es, feld.rect().topRight()).x()
assert 0 <= abstand < 40, f"Stern direkt neben dem Wert, nicht weit rechts ({abstand} px)"
print("OK     Einstellungen: Expertenabschnitt zu nur Überschrift, auf mit Werten; Stern direkt neben dem Wert")
print("OK: Einstellungen")
