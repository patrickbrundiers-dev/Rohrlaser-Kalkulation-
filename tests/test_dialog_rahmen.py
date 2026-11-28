"""Einheitlicher Dialog-Rahmen Variante B (Freigabe Patrick 28.11.2026).

R1 vorgemerkter Dialog: Kopf mit Titel und Erklärung, Aktionen über der Tabelle (höchstens 3 sichtbar), Rest und
   Gefährliches unter „Weitere Aktionen“, unten Schließen; Dialog ohne Vormerkung bleibt unverändert;
R2 Einträge im Menü lösen den Knopf aus und übernehmen seine Aktivierung;
R3 ohne Tabelle: Aktionen links in der Fußleiste, Hauptaktion (OK) rechts und Standard;
R4 Farben im Theme: Dunkel setzt Kopf und Fuß um;
R5 jede freigegebene Ansicht ist im Programm vorgemerkt (und keine andere).
Aufruf: python tests/test_dialog_rahmen.py
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFrame, QLabel, QLineEdit,  # noqa: E402
                               QPushButton, QVBoxLayout)

app = QApplication.instance() or QApplication([])
from rohrlaser import dialog_rahmen, stil  # noqa: E402
from rohrlaser.fenster_merken import FensterMerker  # noqa: E402
from rohrlaser.tabelle_dialog import TabellenDialog  # noqa: E402

stil.anwenden(app, "Hell")
fehler = []


def pruefe(bedingung, text):
    print(("OK      " if bedingung else "FEHLER  ") + text)
    if not bedingung:
        fehler.append(text)


class FakeDB:
    def __init__(self):
        self.d = {}

    def einstellung(self, k, vorgabe=None):
        return self.d.get(k, vorgabe)

    def einstellung_setzen(self, k, v):
        self.d[k] = v


merker = FensterMerker(FakeDB(), benutzer="T")
app.installEventFilter(merker)
gerufen = []


def knopf(name):
    return lambda m, n=name: gerufen.append(n)


def tabellendialog(vormerken=True):
    d = TabellenDialog(None, "Lernzentrale", "Was das Programm gelernt hat. Eine Zeile markieren und eine Aktion "
                       "wählen.", ("A", "B"), [["1", "2"], ["3", "4"]],
                       [(n, knopf(n)) for n in ("Vergessen", "Übernehmen", "Nicht mehr lernen", "Kennwerte prüfen …",
                                                "LST-Ordner einlesen", "Produktionsdaten-Intelligenz …")])
    if vormerken:
        dialog_rahmen.vormerken(d)
    return d


def sichtbare_knoepfe(w):
    return [b.text() for b in w.findChildren(QPushButton) if b.isVisible()]


# R1
d = tabellendialog()
d.show()
app.processEvents()
kopf = d.findChild(QFrame, "dialogkopf")
fuss = d.findChild(QFrame, "dialogfuss")
titel = d.findChild(QLabel, "dialogtitel")
pruefe(kopf is not None and fuss is not None and titel is not None and titel.text() == "Lernzentrale",
       "R1 Kopf mit Titel und Fußleiste")
erkl = [lb for lb in kopf.findChildren(QLabel) if lb.objectName() == "nebentext"] if kopf else []
pruefe(erkl and erkl[0].text().startswith("Was das Programm"), "R1 Erklärung steht im Kopf")
oben = [b.text() for b in d.findChildren(QPushButton) if b.isVisible() and b.parentWidget().objectName() == "dialogaktionen"]
pruefe(oben == ["Übernehmen", "Kennwerte prüfen …", "LST-Ordner einlesen", "Weitere Aktionen"],
       f"R1 über der Tabelle drei Aktionen und „Weitere Aktionen“: {oben}")
y_knopf = max(b.mapTo(d, b.rect().bottomLeft()).y() for b in d.findChildren(QPushButton)
              if b.isVisible() and b.parentWidget().objectName() == "dialogaktionen")
pruefe(d.tabelle.mapTo(d, d.tabelle.rect().topLeft()).y() > y_knopf, "R1 Aktionen stehen über der Tabelle")
unten = [b.text() for b in fuss.findChildren(QPushButton) if b.isVisible()]
pruefe(unten in (["Schließen"], ["Close"]), f"R1 unten nur Schließen: {unten}")
weitere = next(b for b in d.findChildren(QPushButton) if b.objectName() == "weitere")
menue = [a.text() for a in weitere.menu().actions()]
pruefe(menue == ["Produktionsdaten-Intelligenz …", "", "Vergessen", "Nicht mehr lernen"],
       f"R1 Menü: Rest, Trennstrich, dann Gefährliches: {menue}")
pruefe(not d.findChild(QDialogButtonBox).isVisible(), "R1 alte Knopfleiste ausgeblendet")
d2 = tabellendialog(vormerken=False)
d2.show()
app.processEvents()
pruefe(d2.findChild(QFrame, "dialogkopf") is None and len(sichtbare_knoepfe(d2)) == 7,
       "R1 Dialog ohne Vormerkung bleibt wie er ist")
d2.close()

# R2
d.knoepfe["Vergessen"].setEnabled(False)
weitere.menu().aboutToShow.emit()
akt = {a.text(): a for a in weitere.menu().actions()}
pruefe(not akt["Vergessen"].isEnabled() and akt["Nicht mehr lernen"].isEnabled(), "R2 Aktivierung übernommen")
akt["Nicht mehr lernen"].trigger()
d.knoepfe["Übernehmen"].click()
pruefe(gerufen == ["Nicht mehr lernen", "Übernehmen"], f"R2 Rückrufe laufen: {gerufen}")
d.close()

# R3 ohne Tabelle
e = QDialog()
e.setWindowTitle("Kostentreiber")
lay = QVBoxLayout(e)
lay.addWidget(QLabel("Kurz"))
lay.addWidget(QLineEdit())
box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
box.addButton(QPushButton("Kopieren"), QDialogButtonBox.ActionRole)
box.addButton(QPushButton("Alles löschen"), QDialogButtonBox.ActionRole)
lay.addWidget(box)
ok = box.button(QDialogButtonBox.Ok)
dialog_rahmen.vormerken(e)
e.show()
app.processEvents()
fz = e.findChild(QFrame, "dialogfuss")
reihe = [b.text().replace("&", "") for b in sorted((b for b in fz.findChildren(QPushButton) if b.isVisible()),
                                                   key=lambda b: b.mapTo(fz, b.rect().topLeft()).x())]
pruefe(reihe[:2] == ["Kopieren", "Weitere Aktionen"] and reihe[2] == "OK" and reihe[3] in ("Abbrechen", "Cancel"),
       f"R3 Fußleiste: links Aktion und Weitere, rechts OK und Abbrechen: {reihe}")
pruefe(ok.objectName() == "primaer" and ok.isDefault(), "R3 OK ist Hauptaktion und Standard")
pruefe(e.findChild(QLabel, "nebentext") is None, "R3 kurzes Label bleibt im Inhalt")
e.close()

# R4 Dunkel
css = stil.stylesheet("Dunkel")
m = re.search(r"QFrame#dialogkopf \{ background: (#[0-9A-Fa-f]{6})", css)
mf = re.search(r"QFrame#dialogfuss \{ background: (#[0-9A-Fa-f]{6})", css)
pruefe(m and m.group(1).upper() != "#FFFFFF" and mf and mf.group(1).upper() != "#F7F9FB",
       f"R4 Dunkel: Kopf {m and m.group(1)}, Fuß {mf and mf.group(1)}")

# R5 freigegebene Ansichten vorgemerkt
quelle = Path(__file__).resolve().parent.parent / "programm" / "rohrlaser"
stellen = {}
for q in quelle.glob("*.py"):
    zeilen = q.read_text(encoding="utf-8").splitlines()
    for i, z in enumerate(zeilen):
        if 'setProperty("dialog_rahmen", True)' in z:
            umfeld = "\n".join(zeilen[max(0, i - 25):i + 6])
            titel_ = next((t for t in dialog_rahmen.FREIGEGEBEN if f'"{t}"' in umfeld), None)
            stellen[f"{q.name}:{i + 1}"] = titel_
pruefe(sorted(t for t in stellen.values() if t) == sorted(dialog_rahmen.FREIGEGEBEN),
       f"R5 alle freigegebenen Ansichten vorgemerkt: {sorted(stellen.values(), key=str)}")
pruefe(all(stellen.values()), f"R5 keine andere Ansicht vorgemerkt: {[k for k, v in stellen.items() if not v]}")

print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles in Ordnung.")
sys.exit(1 if fehler else 0)
