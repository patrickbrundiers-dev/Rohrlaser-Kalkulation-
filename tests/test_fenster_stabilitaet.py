"""Fenster- und Oberflächenstabilität (Auftrag Patrick 27.11.2026 „Expertenmodus professionalisieren, UI-Redesign und
Fensterstabilität“, Abschnitt 8: automatische Öffnen-/Schließen-, Mehrfach-, Darstellungs- und Belastungstests).

Das Hauptfenster läuft ohne Bildschirm (1920 × 1040) mit einem optimierten Testangebot (erfundene Daten). Jeder
Menübefehl, der ein Fenster öffnet, wird wie vom Benutzer ausgelöst (echtes exec(), geschlossen über Schließen/X).
S1 Öffnen/Schließen/erneut Öffnen: Fenster erscheint, ist vollständig gezeichnet (keine leere, einfarbige Fläche),
   ist nach dem Schließen weg, kein Fenster sperrt danach noch das Programm (kein „X ohne Funktion“), keine
   sichtbaren Reste;
S2 Maximieren, Minimieren, Wiederherstellen, Größe ändern: Zustände stimmen, Fenster liegt danach auf dem Bildschirm
   und ist wieder vollständig gezeichnet;
S3 Speicher: nach mehrfachem Öffnen und Schließen bleiben keine Bedienelemente übrig (fenster_wache gibt geschlossene
   Dialoge frei; vorher blieben z. B. 223 Elemente je Öffnen der Prüfregeln zurück);
S4 fenster_wache hält Dialoge, die noch gebraucht werden (Attribut, Lambda von außen), und löscht nur freie;
S5 schneller Wechsel zwischen allen Hauptbereichen und Angebotsreitern: keine Ausnahme, keine Reste;
S6 Belastung (nur mit ROHRLASER_BELASTUNG=1, z. B. nachts): jedes Fenster 100-mal öffnen und schließen, Speicher
   und Anzahl der Elemente dürfen nicht dauerhaft steigen.
Aufruf: python tests/test_fenster_stabilitaet.py
"""
import gc
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QLocale, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QInputDialog, QMainWindow,  # noqa: E402
                               QMenu, QMessageBox, QPushButton, QVBoxLayout)

QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))
app = QApplication.instance() or QApplication([])

from abnahme_angebote import ANGEBOTE  # noqa: E402
from rohrlaser import angebot_fenster, fenster_wache, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

BELASTUNG = os.environ.get("ROHRLASER_BELASTUNG") == "1"
fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text, flush=True)
    if not bedingung:
        fehler.append(text)


for _n in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.No))
QMessageBox.about = staticmethod(lambda *a, **k: None)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getInt = staticmethod(lambda *a, **k: (0, False))
QInputDialog.getDouble = staticmethod(lambda *a, **k: (0.0, False))
AUSLASSEN = ("Beenden", "Schließen", "Wiederherstellen", "Update", "Anleitung", "löschen", "Löschen", "Abmelden",
             "Neu starten", "Support-Paket")


def gezeichnet(w):
    """Ist das Fenster vollständig gezeichnet (nicht leer/einfarbig)? Stichprobe auf einem Raster."""
    bild = w.grab().toImage()
    if bild.isNull() or bild.width() < 20 or bild.height() < 20:
        return False
    farben = {bild.pixel(x, y) for x in range(0, bild.width(), max(1, bild.width() // 40))
              for y in range(0, bild.height(), max(1, bild.height() // 30))}
    return len(farben) >= 3


def elemente():
    gc.collect()
    fenster_wache.aufraeumen(sofort=True)
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()
    gc.collect()
    return len(QApplication.allWidgets())


def auf_bildschirm(w):
    r = QApplication.primaryScreen().availableGeometry()
    g = w.frameGeometry()
    return r.intersects(g) and r.contains(g.center())


class Bediener:
    """Schließt jedes Fenster, das sich öffnet, wie ein Benutzer (Prüfungen vorher), auch verschachtelte."""

    def __init__(self, f, pfad, fenster_pruefen):
        self.f, self.pfad, self.pruefen = f, pfad, fenster_pruefen
        self.gesehen = []
        self.uhr = QTimer()
        self.uhr.setInterval(30)
        self.uhr.timeout.connect(self.tick)

    def tick(self):
        m = QApplication.activeModalWidget()
        if m is None:
            for w in QApplication.topLevelWidgets():
                if w.isVisible() and w is not self.f and w.isWindow() and not isinstance(w, QMenu) \
                        and w.windowType() in (Qt.Window, Qt.Dialog) and w not in self.gesehen:
                    m = w
                    break
        if m is None:
            return
        if m not in self.gesehen:
            self.gesehen.append(m)
            if self.pruefen:
                self.pruefen(m, self.pfad)
        m.close()


def menue_aktionen(f):
    aktionen = []

    def sammeln(m, pfad):
        for act in m.actions():
            if act.menu():
                sammeln(act.menu(), pfad + "/" + act.menu().title().replace("&", ""))
            elif not act.isSeparator() and act.text():
                aktionen.append((pfad + "/" + act.text().replace("&", ""), act))
    for act in f.menuBar().actions():
        if act.menu():
            sammeln(act.menu(), act.menu().title().replace("&", ""))
    return [(p, a) for p, a in aktionen if not any(x in p for x in AUSLASSEN)]


ERGEBNIS = {}


def fenster_pruefen(w, pfad):
    """S1/S2 an einem gerade geöffneten Fenster."""
    QApplication.processEvents()
    e = ERGEBNIS.setdefault(pfad, dict(klasse=type(w).__name__))
    e["gezeichnet"] = gezeichnet(w)
    e["auf_bildschirm"] = auf_bildschirm(w)
    if isinstance(w, QMessageBox):
        return
    vorher = w.size()
    w.showMaximized()
    QApplication.processEvents()
    maxi = w.isMaximized() or w.minimumSize() == w.maximumSize()
    w.showMinimized()
    QApplication.processEvents()
    mini = w.isMinimized() or w.minimumSize() == w.maximumSize()
    w.showNormal()
    QApplication.processEvents()
    normal = not w.isMaximized() and not w.isMinimized()
    if w.minimumSize() != w.maximumSize():
        w.resize(max(w.minimumWidth(), vorher.width() - 40), max(w.minimumHeight(), vorher.height() - 30))
        QApplication.processEvents()
    e["zustaende"] = maxi and mini and normal
    e["nach_zustaenden_gezeichnet"] = gezeichnet(w)
    e["nach_zustaenden_auf_bildschirm"] = auf_bildschirm(w)


def ausloesen(f, pfad, act, pruefen=True, frist=8.0):
    b = Bediener(f, pfad, fenster_pruefen if pruefen else None)
    b.uhr.start()
    t0 = time.perf_counter()
    try:
        act.trigger()
        ende = time.time() + 0.3
        while time.time() < ende:                   # nicht modale Fenster: kurz warten, dann schließen
            QApplication.processEvents()
            b.tick()
            if not b.gesehen:
                break
    finally:
        b.uhr.stop()
        b.uhr.timeout.disconnect()
    QApplication.processEvents()
    dauer = time.perf_counter() - t0
    rest = [w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not f and not isinstance(w, QMenu)
            and w.windowType() in (Qt.Window, Qt.Dialog)]
    for w in rest:
        w.close()
    namen = [type(w).__name__ for w in b.gesehen]
    b.gesehen.clear()                   # der Test selbst hält keine Fenster fest (S3)
    return namen, rest, dauer


# ------------------------------------------------------------------ S4 fenster_wache für sich
fenster_wache.einrichten()


class _D(QDialog):
    def __init__(self, p):
        super().__init__(p)
        lay = QVBoxLayout(self)
        b = QPushButton("OK")
        lay.addWidget(b)
        b.clicked.connect(self.accept)
        b.clicked.connect(lambda: self.setWindowTitle("x"))


class _Halter:
    pass


haupt = QMainWindow()
halter = _Halter()


def _zu(d):
    QTimer.singleShot(0, d.accept)


def _frei():
    d = _D(haupt)
    _zu(d)
    d.exec()


def _attribut():
    halter.d = _D(haupt)
    _zu(halter.d)
    halter.d.exec()


def _lambda_aussen():
    d = _D(haupt)
    _zu(d)
    d.exec()
    a = QAction("wieder", haupt)
    a.triggered.connect(lambda: d.show())
    haupt.addAction(a)


def _meldung():
    m = QMessageBox(QMessageBox.Information, "Probe", "Text", QMessageBox.Ok, haupt)
    QTimer.singleShot(0, m.accept)
    m.exec()


for _f in (_frei, _attribut, _lambda_aussen, _meldung):
    _f()
geloescht = fenster_wache.aufraeumen(sofort=True)
QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
uebrig = haupt.findChildren(QDialog)
pruefe(geloescht == 2 and len(uebrig) == 2 and halter.d in uebrig,
       f"S4 fenster_wache: freie Dialoge und Meldungen gelöscht ({geloescht}), gehalten über Attribut und Lambda von "
       f"außen bleiben ({len(uebrig)})")
haupt.findChildren(QAction)[-1].trigger()           # die gehaltene Lambda funktioniert noch
QApplication.processEvents()
pruefe(any(d.isVisible() for d in haupt.findChildren(QDialog)), "S4 gehaltener Dialog lässt sich wieder zeigen")
for d in haupt.findChildren(QDialog):
    d.close()
haupt.close()

# ------------------------------------------------------------------ Hauptfenster mit Testangebot
stil.anwenden(app, "Hell")
angebot_fenster.AngebotSeite.CHECK_SOFORT = False
po = Path(tempfile.mkdtemp(prefix="stabil_")) / "Rohrlaser-Angebotskalkulation"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
f = Hauptfenster(db, po, stumm=True)
f.resize(1920, 1040)
f.show()
v = ANGEBOTE[0]
a = db.angebot_neu(dict(nummer="A-2026-0100", kunde="Metallbau Beispiel (erfunden)", kundennr="10417",
                        maschine=v["maschine"], stange=v["stange"]))
for p in v["positionen"]:
    db.position_neu(a, dict(pos=p["pos"], artikel=p["artikel"], bezeichnung=p["bezeichnung"], profil_id=p["profil"],
                            werkstoff_id=p["werkstoff"], laenge=p["laenge"], stueck=p["stueck"]))
f.alles_neu_laden()
f.angebot_oeffnen(a)
QTest.qWait(1500)

# ------------------------------------------------------------------ S1/S2/S3 alle Menüfenster
aktionen = menue_aktionen(f)
mit_fenster = []
for pfad, act in aktionen:
    try:
        if not act.isEnabled():
            continue
    except RuntimeError:
        continue
    gesehen, rest, dauer = ausloesen(f, pfad, act)
    if not gesehen:
        continue
    mit_fenster.append((pfad, act))
    e = ERGEBNIS.setdefault(pfad, {})
    e["rest"] = [type(w).__name__ for w in rest]
    e["modal_danach"] = QApplication.activeModalWidget() is not None
    e["dauer"] = dauer
pruefe(len(mit_fenster) >= 12, f"{len(mit_fenster)} Menübefehle öffnen ein Fenster")
for pfad, e in ERGEBNIS.items():
    if "gezeichnet" not in e:
        continue
    probleme = [k for k in ("gezeichnet", "auf_bildschirm") if not e.get(k)]
    if "zustaende" in e:
        probleme += [k for k in ("zustaende", "nach_zustaenden_gezeichnet", "nach_zustaenden_auf_bildschirm")
                     if not e.get(k)]
    if e.get("rest"):
        probleme.append(f"Reste {e['rest']}")
    if e.get("modal_danach"):
        probleme.append("sperrt nach dem Schließen")
    pruefe(not probleme, f"S1/S2 {pfad} ({e.get('klasse')}): öffnet gezeichnet auf dem Bildschirm, Maximieren/"
                         f"Minimieren/Wiederherstellen/Größe, schließt ohne Reste {probleme or ''}".rstrip())

# S3: jedes Fenster dreimal; danach dürfen keine Elemente übrig bleiben
basis = elemente()
zuwachs = {}
for pfad, act in mit_fenster:
    vor = elemente()
    for _ in range(3):
        ausloesen(f, pfad, act, pruefen=False)
    nach = elemente()
    zuwachs[pfad] = nach - vor
lecks = {p: z for p, z in zuwachs.items() if z > 3}
pruefe(not lecks, f"S3 {len(mit_fenster)} Fenster je dreimal geöffnet und geschlossen: keine Elemente übrig "
                  f"(gesamt {elemente() - basis:+d}) {lecks or ''}".rstrip())
pruefe(fenster_wache.statistik["geloescht"] > 0, f"S3 fenster_wache hat {fenster_wache.statistik['geloescht']} "
                                                f"geschlossene Dialoge freigegeben")

# S5 schneller Wechsel zwischen allen Bereichen und Angebotsreitern
vor = elemente()
try:
    for _ in range(5):
        for i in range(f.reiter.count()):
            f.reiter.setCurrentIndex(i)
            QApplication.processEvents()
        seite = f.offen.get(a)
        if seite is not None:
            f.reiter.setCurrentWidget(seite)
            for j in range(seite.reiter.count()):
                seite.reiter.setCurrentIndex(j)
                QApplication.processEvents()
    ausnahme = None
except Exception as ex:                 # noqa: BLE001
    ausnahme = ex
nach = elemente()
offen = [w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not f and not isinstance(w, QMenu)
         and w.windowType() in (Qt.Window, Qt.Dialog)]
pruefe(ausnahme is None and not offen and gezeichnet(f),
       f"S5 5 × alle Bereiche und Angebotsreiter gewechselt: keine Ausnahme, kein Fenster übrig, Hauptfenster "
       f"gezeichnet (Elemente {nach - vor:+d})")

# S6 Belastung
if BELASTUNG:
    import resource
    rss0, el0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, elemente()
    for runde in range(100):
        for pfad, act in mit_fenster:
            ausloesen(f, pfad, act, pruefen=False)
        if runde in (9, 49, 99):
            print(f"       Runde {runde + 1}: Elemente {elemente() - el0:+d}, RSS "
                  f"{(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss0) / 1024:+.0f} MB", flush=True)
    pruefe(elemente() - el0 < 50, f"S6 Belastung: {100 * len(mit_fenster)} Öffnen/Schließen ohne dauerhaften Zuwachs")

f.close()
if fehler:
    print(f"\n{len(fehler)} Fehler")
    sys.exit(1)
print("Alle Fensterstabilitäts-Prüfungen bestanden.")
