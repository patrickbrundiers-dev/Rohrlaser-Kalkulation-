"""Maximiertes Fenster bleibt maximiert (Patrick 20.11.2026: „Maximierter Bildschirm prüfen darf sich nicht
verändern“).

Seit dem Design-Update (0.9.414) verlangte die Startseite mit der Karte Schnellzugriffe eine Mindesthöhe von rund
870 Pixeln. Auf einem Laptop (z. B. 1366 × 768 oder 1920 × 1080 bei 150 %) wuchs das maximierte Fenster beim Wechsel
auf die Startseite über den Bildschirmrand. Geprüft wird auf einem Bildschirm von 1280 × 680 (kleinste Größe aus dem
Layout-Rundgang): maximiert starten, alle Hauptreiter, ein Angebot mit allen Reitern, Info-Panel, die Arbeitsbereiche,
Hell/Dunkel und ein Dialog. Das Fenster bleibt dabei maximiert und genau so groß wie der Bildschirm. Der Arbeitsbereich
„Tablet“ (große Knöpfe, komfortable Abstände) läuft in einem zweiten Lauf auf 1280 × 800, der üblichen Tablet-Größe.

Aufruf: python tests/test_fenster_maximiert.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER)]
TABLET = sys.argv[1:] == ["tablet"]
BREITE, HOEHE = (1280, 800) if TABLET else (1280, 680)
_konf = Path(tempfile.mkdtemp()) / "bildschirm.json"
_konf.write_text(json.dumps({"screens": [{"name": "laptop", "x": 0, "y": 0, "width": BREITE, "height": HOEHE,
                                          "logicalDpi": 96, "dpr": 1}]}))
os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={_konf}"
from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox  # noqa: E402

QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))
app = QApplication.instance() or QApplication([])

from abnahme_angebote import ANGEBOTE  # noqa: E402
from rohrlaser import aktionen, werkzeugleiste, werkzeugleiste_qt  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

for _n in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.No))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))


def main():
    bildschirm = app.primaryScreen().availableGeometry()
    assert (bildschirm.width(), bildschirm.height()) == (BREITE, HOEHE), bildschirm
    po = Path(tempfile.mkdtemp())
    (po / "Daten").mkdir()
    db = Datenbank(po / "Daten" / "rohrlaser.db")
    f = Hauptfenster(db, po, stumm=True)
    v = ANGEBOTE[0]
    a = db.angebot_neu(dict(nummer="A-2026-0100", kunde="Metallbau Beispiel (erfunden)", kundennr="10417",
                            maschine=v["maschine"], stange=v["stange"]))
    for p in v["positionen"]:
        db.position_neu(a, dict(pos=p["pos"], artikel=p["artikel"], bezeichnung=p["bezeichnung"],
                                profil_id=p["profil"], werkstoff_id=p["werkstoff"], laenge=p["laenge"],
                                stueck=p["stueck"]))
    f.alles_neu_laden()
    f.starten()
    QTest.qWait(100)
    soll = f.geometry()
    assert f.isMaximized(), "Start nicht maximiert"
    assert soll.width() <= BREITE and soll.height() <= HOEHE, soll
    funde = []

    def pruefen(schritt):
        app.processEvents()
        QTest.qWait(20)
        m = f.minimumSizeHint()
        if not f.isMaximized() or f.geometry() != soll or m.width() > BREITE or m.height() > HOEHE:
            funde.append(f"{schritt}: maximiert={f.isMaximized()} Größe {f.width()}×{f.height()} "
                         f"(soll {soll.width()}×{soll.height()}), Mindestgröße {m.width()}×{m.height()}")

    pruefen("Start")
    for i in range(f.reiter.count()):
        f.reiter.setCurrentIndex(i)
        pruefen(f"Reiter {f.reiter.tabText(i)}")
    f.angebot_oeffnen(a)
    QTest.qWait(1500)               # automatisch optimieren
    seite = f.reiter.currentWidget()
    pruefen("Angebot geöffnet")
    for i in range(seite.reiter.count()):
        seite.reiter.setCurrentIndex(i)
        pruefen(f"Angebot, Reiter {seite.reiter.tabText(i)}")
    werkzeugleiste_qt.info_umschalten(f, True)
    pruefen("Info-Panel an")
    bereiche = ["Tablet"] if TABLET else [n for n in werkzeugleiste.EINGEBAUT if n != "Tablet"]
    for name in bereiche:
        werkzeugleiste_qt.arbeitsbereich_anwenden(f, name)
        for i in range(min(f.reiter.count(), 3)):
            f.reiter.setCurrentIndex(i)
            pruefen(f"Arbeitsbereich {name}, Reiter {f.reiter.tabText(i)}")
    werkzeugleiste_qt.arbeitsbereich_anwenden(f, "Standard")
    f.reiter.setCurrentWidget(f.start)
    for schritt in ("Dunkel", "Hell"):
        aktionen.ausfuehren(f, aktionen.AKTION["thema"])
        pruefen(schritt)
    d = QDialog(f)
    d.resize(900, 640)
    d.show()
    pruefen("Dialog offen")
    d.close()
    pruefen("Dialog zu")
    assert not funde, "Fenster verändert sich:\n" + "\n".join(funde)
    print(f"OK: Fenster bleibt maximiert ({soll.width()}×{soll.height()}) bei allen Reitern, Angebot, Info-Panel, "
          f"Arbeitsbereichen {', '.join(bereiche)}, Hell/Dunkel und Dialog")
    if not TABLET:
        p = subprocess.run([sys.executable, __file__, "tablet"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors="replace")
        print(p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "(keine Ausgabe)")
        assert p.returncode == 0, p.stdout[-3000:]


if __name__ == "__main__":
    main()
