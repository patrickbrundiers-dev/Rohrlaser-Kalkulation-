"""Tooltips und Hilfe „nur Tooltip“ wie unter Windows (Supportpaket 27.11.2026).

Unter Windows erzeugt Qt Tooltips ohne Elternfenster: das Stylesheet des Hauptfensters galt dort nicht (dunkler Kasten
ohne Rand, oft nur die erste Zeile, Text über der Tabelle). Hier wird der Tooltip wie unter Windows ohne Eltern gezeigt.
W1 die Tooltip-Regeln des Themes stehen an der Anwendung, Schrift = Schrift der Anwendung (90 %);
W2 Tooltip ohne Eltern: Fläche und Rand des Themes (Dunkel #2A3240, Rand #56657A), Hell weiß;
W3 zu klein gesetzter Tooltip (nur eine Zeile) wird wieder auf volle Höhe gebracht;
W4 langer Hilfetext bricht um (höchstens etwa 80 Zeichen breit) statt einer bildschirmbreiten Zeile;
W5 Hilfe im Modus „nur Tooltip“: Klick auf „Hilfe“ zeigt den ganzen Text;
W6 Themewechsel setzt die Tooltip-Regeln neu (Hell ↔ Dunkel);
W7 losgelöstes Bedienelement (setVisible(True) vor dem Einsetzen): kein Fenster für die Fensterverwaltung, steht im
   Protokoll, bleibt es ohne Fenster, wird es ausgeblendet; eingesetzt erscheint es normal im Dialog;
W8 nach dem Schließen eines Tooltips wird die Fläche darunter im Fenster neu gezeichnet (Reste unter Windows);
W9 im Programm wird kein Bedienelement mehr vor dem Einsetzen eingeblendet (Quelltext-Prüfung, Foto 27.11.2026:
   „＋ Neue Zusatzarbeit …“, „STEP-Dateien in den Ordner des Angebots kopieren“, „(Zusatzarbeit)“).
Aufruf: python tests/test_tooltip_windows.py
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolTip, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
from rohrlaser import hilfe, stil  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


def warten(ms=150):
    ende = time.time() + ms / 1000
    while time.time() < ende:
        app.processEvents()
        time.sleep(0.005)


def tipp():
    return next((t for t in QApplication.topLevelWidgets()
                 if t.isVisible() and t.metaObject().className() == "QTipLabel"), None)


def zeigen(text, w):
    QToolTip.hideText()
    warten(50)
    QToolTip.showText(w.mapToGlobal(QPoint(40, 40)), text, None, QRect(), 20000)   # wie Windows: ohne Eltern
    warten()
    return tipp()


def farbe(t, x, y):
    return t.grab().toImage().pixelColor(x, y).name().upper()


stil.anwenden(app, "Dunkel", 90)
fenster = QWidget()
fenster.resize(900, 500)
stil.fenster_stil(fenster)
fenster.show()
warten()

# W1
pruefe("QToolTip" in app.styleSheet() and "#2A3240" in app.styleSheet() and "QTableView" not in app.styleSheet(),
       "W1 nur die Tooltip-Regeln des Themes an der Anwendung")
pruefe(QApplication.font("QTipLabel").pointSizeF() == app.font().pointSizeF(),
       f"W1 Tooltip-Schrift = Programmschrift ({app.font().pointSizeF():.1f} pt)")

# W2
TEXT = "Auch anfragen bei (je Lieferant eine eigene E-Mail):\nMüller Stahl GmbH\nKlöckner Metals"
t = zeigen(TEXT, fenster)
pruefe(t is not None and t.parentWidget() is None, "W2 Tooltip ohne Elternfenster sichtbar")
if t is not None:
    pruefe(farbe(t, t.width() // 2, t.height() - 3) == "#2A3240", f"W2 Dunkel: Fläche #2A3240 ({farbe(t, t.width() // 2, t.height() - 3)})")
    pruefe(farbe(t, 0, t.height() // 2) == "#56657A", f"W2 Dunkel: Rand #56657A ({farbe(t, 0, t.height() // 2)})")
    zeilen = t.fontMetrics().lineSpacing() * 3
    pruefe(t.height() >= zeilen, f"W2 alle drei Zeilen Platz ({t.height()} px ≥ {zeilen} px)")

    # W3
    t.resize(t.width(), t.fontMetrics().height() + 2)
    warten()
    pruefe(t.height() >= zeilen, f"W3 nur eine Zeile hoch gesetzt → wieder volle Höhe ({t.height()} px)")

# W4
LANG = ("Kategorien der Zukaufartikel mit Standardaufschlag. Neue Artikel übernehmen den Aufschlag ihrer Kategorie; "
        "Artikel mit individuellem Aufschlag ändern sich nicht, wenn hier ein Wert geändert wird. Leer = es gilt der "
        "Standardaufschlag der Einstellungen. Methoden: % auf Einstand, € je Einheit, € je Bestellung, Zielmarge %.")
t = zeigen(LANG, fenster)
pruefe(t is not None and t.wordWrap() and t.width() <= stil.TIPP_BREITE + 40,
       f"W4 langer Text bricht um ({t.width() if t else '-'} px breit)")
if t is not None:
    pruefe(t.height() >= t.heightForWidth(t.width()) - 1, "W4 Höhe für alle umbrochenen Zeilen")

# W5
QToolTip.hideText()
warten(50)
h = hilfe.Hinweis(LANG, parent=fenster)
h.tooltip = True
h._zeigen()
h.show()
warten(50)
pruefe(h.knopf.text() == "Hilfe", "W5 Modus nur Tooltip: Knopf „Hilfe“")
h.knopf.click()
warten()
pruefe(QToolTip.isVisible() and QToolTip.text() == h.text, "W5 Klick auf „Hilfe“ zeigt den ganzen Text")
QToolTip.hideText()
warten(50)

# W6
stil.anwenden(app, "Hell", 100)
pruefe("#2A3240" not in app.styleSheet() and "#FFFFFF" in app.styleSheet(), "W6 Hell: Tooltip-Regeln hell")
t = zeigen(TEXT, fenster)
pruefe(t is not None and farbe(t, t.width() // 2, t.height() - 3) == "#FFFFFF", "W6 Hell: Fläche weiß")
QToolTip.hideText()

# W7
from PySide6.QtWidgets import QCheckBox, QDialog, QPushButton, QVBoxLayout  # noqa: E402

from rohrlaser import fenster_merken, fenster_platz, geister  # noqa: E402

haken = QCheckBox("STEP-Dateien in den Ordner des Angebots kopieren")
haken.setVisible(True)                      # alter Fehler: ohne Eltern = eigenes Fenster
pruefe(geister.losgeloest(haken), "W7 Haken ohne Fenster erkannt")
pruefe(not fenster_merken.FensterMerker._passt(haken) and not fenster_platz.FensterPlatz._fenster(haken),
       "W7 kein Fenster für Fensterverwaltung und Fensterlage")
pruefe(any(f[1].startswith("STEP-Dateien") for f in geister.funde), "W7 Stelle gemerkt (Protokoll)")
warten(80)
pruefe(not haken.isVisible(), "W7 losgelöster Haken nach dem Aufbau ausgeblendet")
d = QDialog()
lay = QVBoxLayout(d)
knopf = QPushButton("＋ Neue Zusatzarbeit …")
lay.addWidget(knopf)
d.show()
warten(50)
pruefe(knopf.isVisible() and not knopf.isWindow(), "W7 eingesetzt: Knopf normal im Dialog")
d.close()

# W8
fenster.raise_()
t = zeigen(TEXT, fenster)
rahmen = t.frameGeometry() if t is not None else None
pruefe(rahmen is not None and geister.neu_zeichnen_unter(rahmen) >= 1, "W8 Fläche unter dem Tooltip wird neu gezeichnet")
QToolTip.hideText()
warten(50)

# W9
import ast  # noqa: E402

WIDGETS = {"QPushButton", "QToolButton", "QCheckBox", "QRadioButton", "QLabel", "QComboBox", "QLineEdit", "QSpinBox",
           "QDoubleSpinBox", "QProgressBar", "QSlider", "QWidget", "QFrame", "QGroupBox", "QTableWidget", "QListWidget",
           "QTextEdit", "QPlainTextEdit", "QTreeWidget", "QTextBrowser", "QDateEdit"}
EINSETZEN = {"addWidget", "addRow", "setCellWidget", "addTab", "insertWidget", "setWidget", "addPermanentWidget",
             "setCornerWidget", "setIndexWidget", "setItemWidget", "setParent"}


def frueh_gezeigt(datei):
    """Stellen: Bedienelement ohne Eltern erzeugt, eingeblendet (setVisible/show, nicht False) vor dem Einsetzen."""
    funde_ = []
    for fn in ast.walk(ast.parse(datei.read_text(encoding="utf-8"))):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        erzeugt, gezeigt, eingesetzt = {}, {}, {}
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
                c = n.value.func
                name = c.id if isinstance(c, ast.Name) else getattr(c, "attr", "")
                if name in WIDGETS and not n.value.keywords and not any(
                        isinstance(a, ast.Name) and a.id in ("self", "parent") for a in n.value.args):
                    for z in n.targets:
                        erzeugt.setdefault(ast.unparse(z), n.lineno)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                k = ast.unparse(n.func.value)
                if n.func.attr in ("setVisible", "show") and not (
                        n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value is False):
                    gezeigt.setdefault(k, []).append(n.lineno)
                if n.func.attr in EINSETZEN:
                    for a in n.args:
                        eingesetzt.setdefault(ast.unparse(a), []).append(n.lineno)
        for k, z in erzeugt.items():
            s_ = [x for x in gezeigt.get(k, []) if x >= z]
            e_ = [x for x in eingesetzt.get(k, []) if x >= z]
            if s_ and e_ and min(s_) < min(e_):
                funde_.append(f"{datei.name}:{min(s_)} {k}")
    return funde_


quelle = Path(__file__).resolve().parent.parent / "programm" / "rohrlaser"
frueh = [f for d in sorted(quelle.glob("*.py")) for f in frueh_gezeigt(d)]
pruefe(not frueh, f"W9 kein Bedienelement vor dem Einsetzen eingeblendet {frueh[:8] or ''}")

print("\n" + (f"{len(fehler)} FEHLER" if fehler else "Alle Prüfungen bestanden."))
sys.exit(1 if fehler else 0)
