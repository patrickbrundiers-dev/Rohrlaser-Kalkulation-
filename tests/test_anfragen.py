"""Anfrage-Ordner (Plan W6a): Anfragen erkennen (Unterordner = eine Anfrage, lose Dateien mit weniger als 10 Minuten
Abstand = eine Anfrage, Dateien im Schreiben noch nicht), Kunde aus dem Ordnernamen, Hinweis bei mehreren Anfragen
eines Kunden, Sperre „in Bearbeitung“, nach dem Übernehmen in den Angebotsordner verschieben, bei Abbruch liegen
lassen; Karte auf der Startseite nur mit Einstellung.

Aufruf: python tests/test_anfragen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import anfragen  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


JETZT = datetime.datetime(2026, 10, 25, 20, 0)


def datei(pfad, minuten_vorher, inhalt="x"):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(inhalt)
    t = (JETZT - datetime.timedelta(minutes=minuten_vorher)).timestamp()
    os.utime(pfad, (t, t))
    return pfad


tmp = Path(tempfile.mkdtemp())
kunden = [dict(kundennr="10233", name="Anlagenbau Hessler"), dict(kundennr="10417", name="Metallbau Krüger")]

# ------------------------------------------------------------------ Erkennen
o = tmp / "Anfragen"
datei(o / "Anlagenbau Hessler Gestell" / "a.step", 60)
datei(o / "Anlagenbau Hessler Gestell" / "Bestellung.pdf", 60)
datei(o / "Anlagenbau Hessler Konsole" / "unter" / "k.stp", 50)
datei(o / "Nur Formular" / "x.pdf", 40)                       # ohne STEP: keine Anfrage
datei(o / "Im Schreiben" / "neu.step", 0.1)                   # zu jung: kommt beim nächsten Blick
datei(o / "lose1.step", 30)
datei(o / "lose2.stp", 24)                                    # 6 min nach lose1: dieselbe Anfrage
datei(o / "lose3.step", 5)                                    # 19 min später: neue Anfrage
datei(o / "notiz.txt", 5)                                     # fremde Endung zählt nicht
liste = anfragen.suchen(o, kunden, jetzt=JETZT)
namen = [a.name for a in liste]
assert namen == ["Anlagenbau Hessler Gestell", "Anlagenbau Hessler Konsole", "2 Dateien vom 25.10. 19:30",
                 "lose3"], namen
gestell, konsole, lose, einzeln = liste
assert [d.name for d in gestell.step] == ["a.step"] and [d.name for d in gestell.formulare] == ["Bestellung.pdf"]
assert [d.name for d in konsole.step] == ["k.stp"]
assert gestell.kunde == "10233" and konsole.kunde == "10233" and lose.kunde is None
assert [d.name for d in lose.dateien] == ["lose1.step", "lose2.stp"]
assert set(anfragen.gleicher_kunde(liste)) == {"10233"}
ok("Unterordner = Anfrage, lose Dateien unter 10 min Abstand zusammen, ohne STEP/zu jung nicht, Kunde aus dem Ordner")

# ------------------------------------------------------------------ Sperren, Freigeben, Verschieben
lose = anfragen.sperren(lose, o, "PB", jetzt=JETZT)
assert lose.ordner == o / "Anfrage 2026-10-25 19-36" and lose.ordner.is_dir(), lose.ordner
assert not (o / "lose1.step").exists() and (lose.ordner / "lose1.step").exists()
neu = anfragen.suchen(o, kunden, jetzt=JETZT)
assert [a.gesperrt for a in neu if a.ordner == lose.ordner] == ["PB"]
assert set(anfragen.gleicher_kunde(neu)) == {"10233"}
anfragen.freigeben(lose)
assert [a.gesperrt for a in anfragen.suchen(o, kunden, jetzt=JETZT) if a.ordner == lose.ordner] == [None]
ziel = tmp / "Ablage" / "2026-00042 Hessler"
datei(ziel / "STEP" / "a.step", 1)                            # schon kopiert (Häkchen im Prüfdialog): nicht doppelt
anfragen.sperren(gestell, o, "PB", jetzt=JETZT)
n, fehler = anfragen.verschieben(gestell, ziel)
assert (n, fehler) == (2, []), (n, fehler)
assert sorted(p.name for p in (ziel / "STEP").iterdir()) == ["a.step"]
assert (ziel / anfragen.ZIEL_FORMULAR / "Bestellung.pdf").exists()
assert not (o / "Anlagenbau Hessler Gestell").exists()
ok("Sperre mit Kürzel (lose Dateien in eigenen Unterordner), Freigeben, Verschieben ohne Doppel, leerer Ordner weg")

# ------------------------------------------------------------------ Startseite
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
karte = fenster.start.anfragen
assert not karte.karte.isVisibleTo(karte.karte.parentWidget())
db.einstellung_setzen("ablageordner", str(tmp / "Ablage2"))
db.einstellung_setzen("benutzer_kuerzel", "PB")
o2 = tmp / "Eingang"
datei(o2 / "Metallbau Krüger 4711" / "t.step", 20, "STEP")
db.einstellung_setzen(anfragen.EINSTELLUNG, str(o2))
karte.neu_laden()
assert karte.karte.isVisibleTo(karte.karte.parentWidget()) and karte.liste.count() == 1
assert "Metallbau Krüger" in karte.liste.item(0).text()

importe = []
abbrechen = [True]


def step_importieren(self, dateien=None, *a, **kw):
    importe.append((self.id, dateien))
    return None if abbrechen[0] else {}


AngebotSeite.step_importieren = step_importieren
vorher = len(db.angebote())
assert karte.oeffnen([karte.anfragen[0]], kundennr="10417") is None
assert len(db.angebote()) == vorher and (o2 / "Metallbau Krüger 4711" / "t.step").exists()
assert anfragen.sperre_lesen(o2 / "Metallbau Krüger 4711") is None
abbrechen[0] = False
seite = karte.oeffnen([karte.anfragen[0]], kundennr="10417")
assert seite is not None and len(db.angebote()) == vorher + 1
assert importe[-1][1] == [str(o2 / "Metallbau Krüger 4711" / "t.step")], importe
ziel = fenster.angebot_ordner(seite.kopf)
assert (ziel / "STEP" / "t.step").read_text() == "STEP" and not (o2 / "Metallbau Krüger 4711").exists()
assert karte.liste.count() == 0 and "Keine neuen Anfragen" in karte.titel.text()
ok("Startseite: Karte nur mit Einstellung, Abbruch lässt Dateien liegen und hebt die Sperre auf, Übernahme "
   "verschiebt in den Angebotsordner")
print("Alle Tests bestanden.")
