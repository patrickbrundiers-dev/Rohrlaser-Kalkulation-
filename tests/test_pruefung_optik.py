"""Prüfung Performance, System, Daten, Optik (Patrick 29.10.2026), Schritte 1–3; Berechnung und Import unverändert:
- S1 Breite der Übersicht nach dem Schließen eines Angebots: kein „already deleted“-Fehler mehr
- O3 Zeiten in der Übersicht: Zeit und Betrag nie ohne Abstand
- O5 Kurzzeilen (Kopf, Kalkulation, Fracht) enden mit „…“, Tooltip zeigt den ganzen Text, text() bleibt ganz
- O6 leere Tabellen (Fertigung, Versand, Lager) zeigen einen Hinweis
- O1 niedrige Angebotsseite (Laptop 1366 × 768): Karten flacher, Kalkulation + Fracht zugeklappt nebeneinander
- O2 Einblendungen stehen links neben der Übersicht des offenen Angebots

Aufruf: python tests/test_pruefung_optik.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import leerhinweis  # noqa: E402
from rohrlaser.angebot_oben import KOMPAKT_UNTER, KurzZeile  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
fehler = []


def _haken(art, wert, tb):
    fehler.append(f"{art.__name__}: {wert}")
    sys.__excepthook__(art, wert, tb)


sys.excepthook = _haken
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
f.resize(1600, 900)
f.show()
a = beispiel_angebot.anlegen(db)


def ruhe():
    for _ in range(5):
        app.processEvents()


# ------------------------------------------------------------------ S1 Schließen direkt nach einer Layout-Änderung
for _ in range(5):
    s = f.angebot_oeffnen(a)
    ruhe()
    # Layout-Anfrage der Übersicht (z. B. nach einer Änderung): die Breite wird gleich danach angepasst
    QCoreApplication.sendEvent(s.uebersicht_rahmen.widget(), QEvent(QEvent.LayoutRequest))
    f.angebot_schliessen(a)
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    ruhe()
assert not fehler, fehler
ok("S1 Angebot direkt nach einer Änderung der Übersicht schließen: keine Fehlermeldung")

# ------------------------------------------------------------------ O3 Abstand Zeit / Betrag
s = f.angebot_oeffnen(a)
s.optimieren()
ruhe()
html = s.uebersicht_bereich.zeiten.text()
assert "Arbeitszeit gesamt" in html and "&nbsp;&nbsp;&nbsp;" in html, html[:300]
ok("O3 Zeiten: Abstand zwischen Zeit und Betrag")

# ------------------------------------------------------------------ O5 Kurzzeile mit …
z = KurzZeile()
voll = "Zuschlag Fremdleistung 10,0 % · Rüstzeit je Abmessung 15,0 min · Programmierzeit je Position 5,0 min"
z.setText("   " + voll + "   <b style='color:#B35C00'>(2 abweichend)</b>")
z.setToolTip("Hilfe")
z.resize(2000, 20)
z.show()
ruhe()
assert z.toolTip() == "Hilfe" and "…" not in QLabel.text(z), "passt: ganz und ohne …"
z.resize(260, 20)
ruhe()
angezeigt = QLabel.text(z)
assert "…" in angezeigt, angezeigt[-200:]
assert "(2 abweichend)" in z.text() and voll in z.text(), "text() liefert den ganzen Text"
assert voll.split(" · ")[0] in z.toolTip() and "Hilfe" in z.toolTip(), z.toolTip()
z.resize(2000, 20)
ruhe()
assert "…" not in QLabel.text(z) and z.toolTip() == "Hilfe"
kb = s.kopf_bereich
assert isinstance(kb.kalk_kurz, KurzZeile) and isinstance(kb.fracht_kurz, KurzZeile) and isinstance(kb.kopf_kurz,
                                                                                                    KurzZeile)
ok("O5 Kurzzeilen enden mit „…“, Tooltip mit ganzem Text, text() unverändert")

# ------------------------------------------------------------------ O6 Hinweis in leeren Tabellen
for tabelle in (f.fertigung.liste, f.fertigung.verlauf, f.versand.tabelle, f.lager.tabelle, f.lager.buchungen):
    assert leerhinweis.text(tabelle), tabelle
f.fertigung.liste.setRowCount(0)
f.fertigung.liste.viewport().repaint()
ok("O6 leere Tabellen in Fertigung, Versand und Lager mit Hinweis")

# ------------------------------------------------------------------ O1 niedrige Seite
kb.kalkulation_aufklappen(False)
kb.fracht_aufklappen(False)
kb.breite_anpassen(1000, KOMPAKT_UNTER + 100)
assert not kb.kompakt and kb.fracht_rechts is False
kb.breite_anpassen(1000, KOMPAKT_UNTER - 60)
assert kb.kompakt and kb.fracht_rechts is True, "zugeklappt: Kalkulation und Fracht nebeneinander"
assert kb.kalk_karte.layout().contentsMargins().top() == 3
kb.kalkulation_aufklappen(True)
assert kb.fracht_rechts is False, "aufgeklappt wieder untereinander"
kb.kalkulation_aufklappen(False)
assert kb.fracht_rechts is True
kb.breite_anpassen(1000, KOMPAKT_UNTER + 100)
assert not kb.kompakt and kb.fracht_rechts is False and kb.kalk_karte.layout().contentsMargins().top() == 8
f.resize(1366, 768)
ruhe()
assert kb.kompakt, s.height()
f.resize(1600, 900)
ruhe()
assert not kb.kompakt, s.height()
ok("O1 niedrige Angebotsseite: Karten flacher, Kalkulation + Fracht zugeklappt nebeneinander, sonst wie bisher")

# ------------------------------------------------------------------ O2 Einblendung links neben der Übersicht
f.reiter.setCurrentWidget(s)
ruhe()
grenze = f.einblendung_grenze()
assert grenze and grenze == s.uebersicht_rahmen.mapTo(f, s.uebersicht_rahmen.rect().topLeft()).x()
f.einblendung.zeigen("344 Stangen, 678 Teile eingeplant.")
assert f.einblendung.geometry().right() < grenze, (f.einblendung.geometry(), grenze)
f.einblendung.hide()
f.reiter.setCurrentWidget(f.start)
ruhe()
assert f.einblendung_grenze() is None
f.einblendung.zeigen("Gespeichert.")
assert f.einblendung.geometry().right() > f.width() - 40
ok("O2 Einblendung links neben der Übersicht des offenen Angebots, sonst unten rechts")

assert not fehler, fehler
print("Alle Tests Prüfung Optik bestanden.")
