"""Absturz beim Öffnen der Schweißbaugruppe (Patrick 16.11.2026: „Schweißbaugruppen lassen sich nicht öffnen,
Programm stürzt ab“ – kein Fenster, das Programm schloss sich).

Ursache: fluss.FlussLayout.expandingDirections gab Qt.Orientations() zurück. Nur im übersetzten Programm (Cython,
programm/kompilieren.py) führte das zu einem Speicherzugriffsfehler beim Aufbau des Fensters; im Python-Lauf der
Tests fiel es nicht auf. Nachgestellt mit allen Modulen übersetzt: tests/test_baugruppe.py stürzte bei B11 ab, mit
Qt.Orientation(0) laufen alle Baugruppen-Tests durch. Dieser Test prüft die Schreibweise im ganzen eigenen Code
(leere Qt-Flags nie über den Plural-Namen bauen) und dass die Knopfzeilen der Schweißbaugruppe richtig umbrechen.

Aufruf: python tests/test_bg_absturz_1611.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import ast
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
sys.path.insert(0, str(PROGRAMM))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402

from rohrlaser import fluss  # noqa: E402
from rohrlaser.ansicht3d_leiste import FlussLayout as Leiste3DFluss  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ A1 keine leeren Plural-Flags im eigenen Code
treffer = []
for ordner in ("rohrlaser", "step_messung", "rl_auslastung"):
    for datei in sorted((PROGRAMM / ordner).glob("*.py")):
        for k in ast.walk(ast.parse(datei.read_text(encoding="utf-8"))):
            f = getattr(k, "func", None)
            if (isinstance(k, ast.Call) and not k.args and not k.keywords and isinstance(f, ast.Attribute)
                    and f.attr[:1].isupper() and f.attr.endswith("s") and isinstance(f.value, ast.Name)
                    and f.value.id == "Qt"):
                treffer.append(f"{datei.relative_to(PROGRAMM)}:{k.lineno}: Qt.{f.attr}()")
assert not treffer, "Leeres Qt-Flag über den Plural-Namen (stürzt übersetzt ab), Qt.X(0) nehmen:\n" + "\n".join(treffer)
ok("A1 kein Qt.Orientations() & Co. im eigenen Code (übersetzt: Speicherzugriffsfehler beim Öffnen des Fensters)")

# ------------------------------------------------------------------ A2 Knopfzeile bricht weiter um
app = QApplication.instance() or QApplication([])
for art in (fluss.FlussLayout, Leiste3DFluss):
    w = QWidget()
    lay = art(w)
    for i in range(6):
        lay.addWidget(QPushButton(f"Knopf {i}"))
    assert lay.expandingDirections() == Qt.Orientation(0)
    breit, schmal = lay.heightForWidth(2000), lay.heightForWidth(150)
    assert schmal > breit > 0, (art, breit, schmal)
    lay.setGeometry(QRect(0, 0, 150, schmal))
    assert len({b.geometry().y() for b in w.findChildren(QPushButton)}) > 1
ok("A2 umbrechende Knopfzeilen: eine Zeile bei voller Breite, mehrere bei schmalem Fenster")
print("Alle Tests bestanden.")
