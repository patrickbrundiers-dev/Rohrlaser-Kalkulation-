"""Kopfleiste „Klar“ (UI/UX Next Level Phase 2, Freigabe Patrick 26.11.2026, F2/F3).

K1 Menüleiste zeigt nur den Knopf „Menü“; alle bisherigen Menüs stehen darin, Datei nach Themen geteilt, dieselben
   QAction-Objekte (kein Punkt fehlt, keiner doppelt);
K2 Tastenkürzel der Menüpunkte lösen im kompakten Modus aus; Alt+Buchstabe ist für jedes Menü belegt;
K3 Ansicht → Klassische Menüleiste zeigt die alten Menüs (gemerkt in leiste_menue), zurück auf kompakt;
K4 Hauptadmin-Menü bleibt bis zur Anmeldung verborgen, auch im Knopf;
K5 Zähler in der Seitenleiste (setzen, ausblenden, 99+); Werkzeugleiste ist ab Werk aus;
K6 Startseite: Begrüßung nach Tageszeit, Hinweisband bei Beispiel-Stammdaten; Befehlssuche nennt das Thema.
Aufruf: python tests/test_kopfleiste.py (mit PostgreSQL wie die übrigen Fenster-Tests)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
for _n in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.No))
from rohrlaser import befehlspalette, kopfleiste, werkzeugleiste  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


po = Path(tempfile.mkdtemp(prefix="kl_")) / "Rohrlaser"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
f = Hauptfenster(db, po, stumm=True)
f.resize(1600, 900)
f.show()
QTest.qWait(50)
k = f.kopfleiste

# K1
sichtbar = [a for a in f.menuBar().actions() if a.isVisible()]
pruefe(sichtbar == [k.knopf], f"K1 nur der Knopf Menü sichtbar {[a.text() for a in sichtbar]}")
m = k.aufbauen()
namen = [a.text() for a in m.actions() if not a.isSeparator() and a.isVisible()]
pruefe(namen == ["Datei", "Bearbeiten", "Kunden", "Daten und Abgleich", "Auswertung und Prüfung", "KI", "Ansicht",
                 "Hilfe"], f"K1 Reihenfolge {namen}")
datei = next(a.menu() for n, a in k.originale() if n == "Datei")
alt = [a for a in datei.actions() if not a.isSeparator()]
neu = [x for a in m.actions() if a.menu() is not None and a.text() in kopfleiste.REIHENFOLGE[:1] + kopfleiste.REIHENFOLGE[3:6]
       for x in a.menu().actions() if not x.isSeparator()]
pruefe(len(alt) == len(neu) and set(map(id, alt)) == set(map(id, neu)),
       f"K1 Datei-Punkte vollständig und dieselben Objekte ({len(alt)} / {len(neu)})")
pruefe(kopfleiste.thema("Mit den Kollegen abgleichen") == "Daten und Abgleich"
       and kopfleiste.thema("KI-Zentrale …") == "KI" and kopfleiste.thema("Kostentreiber …") == "Auswertung und Prüfung"
       and kopfleiste.thema("STEP-Viewer (Datei ansehen und prüfen) …") == "Datei"
       and kopfleiste.thema("Beenden") == "Datei", "K1 Themen")
bearbeiten = next(a for a in m.actions() if a.text() == "Bearbeiten")
original = next(a.menu() for n, a in k.originale() if n == "Bearbeiten")
pruefe(bearbeiten.menu().actions() == original.actions() and original.menuAction().parent() is original,
       "K1 Bearbeiten zeigt dieselben Punkte, das bisherige Menü bleibt unangetastet")

# K2
f.activateWindow()
ziel = next(a for n, o in k.originale() for a in o.menu().actions() if a.text() == "Nächster Reiter")
gezaehlt = []
ziel.triggered.connect(lambda *_: gezaehlt.append(1))
QTest.keySequence(f, ziel.shortcut())
QTest.qWait(20)
pruefe(gezaehlt, "K2 Tastenkürzel Strg+Tab löst im kompakten Modus aus")
tasten = sorted(t.key().toString() for t in k._tasten)
pruefe({"Alt+D", "Alt+B", "Alt+K", "Alt+A", "Alt+H"} <= set(tasten) and all(t.isEnabled() for t in k._tasten),
       f"K2 Alt-Tasten {tasten}")

# K3
k.umschalter.setChecked(True)
klassisch = [a.text().replace("&", "") for a in f.menuBar().actions() if a.isVisible()]
pruefe(klassisch == ["Datei", "Bearbeiten", "Kunden", "Ansicht", "Hilfe"]
       and db.einstellung(kopfleiste.EINSTELLUNG) == kopfleiste.KLASSISCH
       and not any(t.isEnabled() for t in k._tasten), f"K3 klassisch {klassisch}")
k.umschalter.setChecked(False)
pruefe([a for a in f.menuBar().actions() if a.isVisible()] == [k.knopf]
       and db.einstellung(kopfleiste.EINSTELLUNG) == kopfleiste.KOMPAKT, "K3 zurück auf kompakt")

# K4
from rohrlaser import hauptadmin_menue  # noqa: E402

pruefe("Hauptadmin" not in [a.text() for a in k.aufbauen().actions() if a.isVisible()], "K4 Hauptadmin verborgen")


class Z:
    hauptadmin = True


hauptadmin_menue.anwenden(f, Z())
pruefe("Hauptadmin" in [a.text() for a in k.aufbauen().actions() if a.isVisible()]
       and [a for a in f.menuBar().actions() if a.isVisible()] == [k.knopf], "K4 nach Anmeldung im Knopf, nicht in der Leiste")
k.umschalter.setChecked(True)
pruefe("Hauptadmin" in [a.text().replace("&", "") for a in f.menuBar().actions() if a.isVisible()],
       "K4 klassisch: Hauptadmin in der Leiste")
hauptadmin_menue.anwenden(f, None)
pruefe("Hauptadmin" not in [a.text().replace("&", "") for a in f.menuBar().actions() if a.isVisible()],
       "K4 abgemeldet: wieder verborgen")
k.umschalter.setChecked(False)

# K5
leiste = f.reiter.oben
z = leiste.zahl_setzen("Anfragen", 3, hervor=True)
pruefe(z is not None and z.text() == "3" and z.objectName() == "navzahl_hervor" and leiste.zahl("Anfragen") == 3,
       "K5 Zähler gesetzt")
leiste.zahl_setzen("Anfragen", 150)
pruefe(leiste.zahl("Anfragen") == 99 and z.objectName() == "navzahl", "K5 99+")
leiste.zahl_setzen("Anfragen", 0)
pruefe(leiste.zahl("Anfragen") == 0 and z.isHidden(), "K5 0 blendet aus")
pruefe(leiste.zahl_setzen("Gibt es nicht", 2) is None, "K5 unbekannter Bereich")
pruefe(werkzeugleiste.LEISTE_VORGABE["sichtbar"] is False, "K5 Werkzeugleiste ab Werk aus")

# K6
s = f.start
pruefe(s.begruessung(datetime.datetime(2026, 11, 26, 8)).startswith("Guten Morgen")
       and s.begruessung(datetime.datetime(2026, 11, 26, 14)).startswith("Guten Tag")
       and s.begruessung(datetime.datetime(2026, 11, 26, 20)).startswith("Guten Abend"), "K6 Begrüßung")
pruefe(s._untertitel(datetime.date(2026, 11, 26)).startswith("Donnerstag, 26. November 2026"), "K6 Datum")
s._neu_laden()
beispiel = (db.einstellung("stammdaten_herkunft") or "") == "Beispieldaten"
pruefe(s.beispiel_band.isVisibleTo(s) == beispiel, f"K6 Hinweisband bei Beispieldaten ({beispiel})")
eintraege = befehlspalette._menue_befehle(f)
pruefe(any(n == "Daten und Abgleich" and b.text() == "Mit den Kollegen abgleichen" for n, b in eintraege)
       and not any(n == "Datei" and b.text().startswith("KI-") for n, b in eintraege), "K6 Befehlssuche nennt das Thema")

f.close()
print("\n" + ("ALLE PRÜFUNGEN OK" if not fehler else f"{len(fehler)} FEHLER"))
sys.exit(1 if fehler else 0)
