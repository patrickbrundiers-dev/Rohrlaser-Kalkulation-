"""Designsystem „Klar“ Phase 5 (UI/UX Next Level, Freigabe Patrick 26.11.2026): übrige Bereiche und Einfacher Modus.

S1 jeder Bereich der Liste seitenkoepfe.KOEPFE hat oben einen einzeiligen Seitenkopf, Titel = Text des Reiters;
S2 der Kopf steht über dem bisherigen Inhalt derselben Seite (gleiches Objekt, Tabelle darunter), kein Doppel bei
   erneutem Aufruf; Bereiche mit eigenem Kopf (Start, Kunden, Einstellungen) bekommen keinen zweiten;
S3 Auswertung: Titel im Stil der Seitentitel;
E1 Einfacher Modus: erledigte Schritte mit ✓ und Kennzeichen „erledigt“, offene mit Nummer.
Aufruf: python tests/test_klar_phase5.py (mit PostgreSQL wie die übrigen Fenster-Tests)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QTableView  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
for _n in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.No))
from rohrlaser import einfach_seite, seitenkoepfe  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


db = Datenbank(Path(tempfile.mkdtemp()) / "x.db")
f = Hauptfenster(db, stumm=True)
f.resize(1366, 728)
f.show()
QTest.qWait(100)

# ---------------------------------------------------------------- S1
koepfe = seitenkoepfe.anwenden(f)
for attr, _ in seitenkoepfe.KOEPFE:
    w = getattr(f, attr, None)
    if w is None:
        continue
    k = koepfe.get(attr)
    titel = f.reiter.tabText(f.reiter.indexOf(w)).replace("&&", "&")
    pruefe(k is not None and k.titel.text() == titel and k.titel.objectName() == "seitentitel"
           and w.layout().itemAt(0).widget() is k, f"S1 {attr}: Kopf „{k.titel.text() if k else '-'}“ oben")

# ---------------------------------------------------------------- S2
f.reiter.setCurrentWidget(f.angebote)
QTest.qWait(50)
k = f.angebote.seitenkopf
tab = f.angebote.findChildren(QTableView)[0]
pruefe(k.isVisible() and k.height() <= 45 and tab.mapTo(f.angebote, tab.rect().topLeft()).y() > k.geometry().bottom(),
       f"S2 Angebote: Kopf {k.height()} px hoch, Tabelle darunter")
anzahl = sum(1 for i in range(f.angebote.layout().count())
             if f.angebote.layout().itemAt(i).widget() is k)
seitenkoepfe.anwenden(f)
pruefe(anzahl == 1 and f.angebote.layout().itemAt(1).widget() is not k, "S2 erneuter Aufruf setzt keinen zweiten Kopf")
pruefe(all(getattr(getattr(f, a), "seitenkopf", None) is None for a in ("start", "kunden", "bereich")),
       "S2 Start, Kunden und Einstellungen behalten ihren eigenen Kopf")

# ---------------------------------------------------------------- S3
pruefe(any(lb.text() == "Auswertung der Aufträge" and lb.objectName() == "seitentitel"
           for lb in f.auswertung.findChildren(QLabel)), "S3 Auswertung mit Seitentitel")

# ---------------------------------------------------------------- E1
b = QPushButton()
einfach_seite.EinfachBereich._schritt_kennzeichnen(b, 1, erledigt=True)
pruefe(b.text().startswith("✓") and b.property("erledigt") is True, f"E1 erledigter Schritt „{b.text()}“")
einfach_seite.EinfachBereich._schritt_kennzeichnen(b, 1, erledigt=False)
pruefe(b.text().startswith("2") and b.property("erledigt") is False, f"E1 offener Schritt „{b.text()}“")

f.close()
print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles in Ordnung.")
sys.exit(1 if fehler else 0)
