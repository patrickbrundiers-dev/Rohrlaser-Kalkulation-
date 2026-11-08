"""Prüfdialog (Vorschläge M1–M3, Patrick 07.11.2026 abends):
M1 kein Querscrollen: Hinweis-Spalte zeigt nur ein Stichwort (ganzer Text im Infofeld), Länge/Schneidweg/Konturen
   ausgeblendet (Rechtsklick auf die Kopfzeile blendet sie ein), Anbauteile nur mit Anbauteilen, Spalten passen sich an.
M2 fehlendes Profil direkt im Prüfdialog anlegen (Zeile „Profil anlegen“ über der Liste).
M3 gelbe Teile der Reihe nach: „Nächstes prüfen“ (F8) springt, „Passt“ (Leertaste) hakt an und macht grün.

Aufruf: python tests/test_pruefdialog_m1_m3.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import step_messen  # noqa: E402
from formen_baukasten import ohne, quader, schreibe  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog, stichwort  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ M1 Stichwort
assert stichwort("Profil fehlt in den Stammdaten") == "Profil fehlt"
assert stichwort("Drehteil Ø41,6 × 20 mm (Normteil: Mutter); PRÜFEN – nur nach den Maßen") == "Drehteil +1"
assert stichwort("UNSICHER: anbauteile") == "UNSICHER"
assert stichwort("") == "" and stichwort(None) == ""
ok("Stichwort: erster Hinweis bis zum Doppelpunkt, ganze Wörter bis 12 Zeichen, „+N“ für weitere")

# ------------------------------------------------------------------ Teile: Flachstahl (Profil fehlt), Quadratrohr
schreibe({"Lasche": quader(146, 40, 9.5),
          "Rohr": ohne(quader(500, 40, 40), quader(500, 34, 34, 0, 3, 3))}, TMP)
aus = TMP / "m.txt"
step_messen.main(["--ausgabe", str(aus), str(TMP / "Lasche.step"), str(TMP / "Rohr.step")])
MW = step.lies_messwerte(aus)
app = QApplication.instance() or QApplication([])
db = Datenbank(TMP / "p.db")
k = db.kontext()
angelegt = []


def anlegen(text):
    """Wie AngebotFenster.abmessung_neu: Profil in die Stammdaten, Ergebnis die Profil-ID."""
    k.profile[text] = dict(next(iter(k.profile.values())), profil_id=text)
    angelegt.append(text)
    return text


werte = [dict(m) for m in MW]
d = StepPruefDialog(None, werte, k, "S235-10219", 1, zukauf_liste=[], profil_anlegen=anlegen)
d.resize(1350, 720)
d.show()
app.processEvents()

# ------------------------------------------------------------------ M1 Spalten
for c in (d.SP_LAENGE, d.SP_SCHNEIDWEG, d.SP_KONTUREN, d.SP_ANBAU):
    assert d.baum.isColumnHidden(c), d.SPALTEN[c]
z = next(z for z in d.zeilen if "Profil fehlt" in z.it.text(d.SP_HINWEIS))
anzeige = d.baum.itemDelegateForColumn(d.SP_HINWEIS).displayText(z.it.text(d.SP_HINWEIS), None)
assert anzeige == stichwort(z.it.text(d.SP_HINWEIS)) and len(anzeige) < len(z.it.text(d.SP_HINWEIS))
d.spalten_einpassen()
app.processEvents()
breite = sum(d.baum.columnWidth(c) for c in range(len(d.SPALTEN)) if not d.baum.isColumnHidden(c))
assert breite <= d.baum.viewport().width(), (breite, d.baum.viewport().width())
assert d.baum.horizontalScrollBar().maximum() == 0, d.baum.horizontalScrollBar().maximum()
assert d.baum.columnWidth(0) >= d.SPALTE_MIN[0]
d.spalte_zeigen(d.SP_LAENGE)
assert not d.baum.isColumnHidden(d.SP_LAENGE)
d.spalte_zeigen(d.SP_LAENGE, False)
ok("M1: Nebenspalten aus, Hinweis als Stichwort, alle sichtbaren Spalten passen in die Liste (keine Querleiste), "
   "Spalten über die Kopfzeile ein- und ausblendbar")

# ------------------------------------------------------------------ M2 Profil anlegen
fehlt = d.profile_fehlend()
assert len(fehlt) == 1 and fehlt[0].startswith("FL 40"), fehlt
assert not d.profil_zeile.isHidden() and not d.profil_knopf.isHidden() and fehlt[0] in d.profil_info.text()
assert d.profil_anlegen() == fehlt and angelegt == fehlt
assert d.profile_fehlend() == [] and d.profil_knopf.isHidden() and "Angelegt: " + fehlt[0] in d.profil_info.text()
z = next(z for z in d.zeilen if z.vorschlag == fehlt[0])
assert "Profil fehlt" not in z.it.text(d.SP_HINWEIS) and "Profil fehlt in den Stammdaten" not in z.ampel_gruende
d2 = StepPruefDialog(None, [dict(m) for m in MW if "Lasche" in m["datei"]], db.kontext(), "S235-10219", 1,
                     zukauf_liste=[])
assert d2.profil_zeile.isHidden(), "ohne Anlege-Funktion (nur lesen, fremdes Angebot) keine Zeile"
ok(f"M2: Zeile „Profil anlegen“ über der Liste, {fehlt[0]} angelegt, das Teil ist danach nicht mehr „Profil fehlt“")

# ------------------------------------------------------------------ M3 der Reihe nach prüfen
for m in werte:
    m["pruefstatus"] = "prüfen"            # beide Teile gelb („nur nach den Maßen erkannt“)
d3 = StepPruefDialog(None, werte, k, "S235-10219", 1, zukauf_liste=[])
d3.show()
app.processEvents()
gruen, gelb, _ = d3.ampel_zahlen()
assert gelb == 2 and not d3.naechst_knopf.isHidden(), (gruen, gelb)
erste = d3.naechstes_pruefen()
assert erste is not None and erste.ampel == "gelb" and d3.baum.currentItem() is erste.it
zweite = d3.passt()
assert erste.ampel == "gruen" and erste.it.checkState(0) == Qt.Checked
assert all(werte[i].get("_geprueft") for i in erste.liste)
assert zweite is not erste and zweite.ampel == "gelb" and d3.baum.currentItem() is zweite.it
assert d3.ampel_zahlen()[1] == 1
d3._leertaste()                             # Leertaste = „Passt“
assert d3.ampel_zahlen()[1] == 0 and d3.naechst_knopf.isHidden() and d3.naechstes_pruefen() is None
assert step.ampel(dict(werte[0]))[0] == "gruen" and "von Hand geprüft" in step.ampel(dict(werte[0]))[1][0]
assert step.ampel(dict(werte[0]), profil_fehlt=True)[0] == "gelb", "Profil fehlt bleibt gelb trotz „Passt“"
ok("M3: „Nächstes prüfen“ springt zum gelben Teil, „Passt“/Leertaste hakt an, macht grün und geht weiter")

print("Prüfdialog M1–M3: alle Tests bestanden.")
