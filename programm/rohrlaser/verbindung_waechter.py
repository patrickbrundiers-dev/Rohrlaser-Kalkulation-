"""Verbindung zur Datenbank überwachen, neu aufbauen, Eingaben nicht verlieren (Datenbank-Auftrag 19.11.2026, Schritt 5).

PostgreSQL läuft auf jedem PC als eigener Server (pg_lokal). Bricht die Verbindung ab (Server beendet, PC aus dem
Ruhezustand, Virenscanner hält den Port), gilt:
- Lesen baut die Verbindung von selbst neu auf (db_verbindung), auch mit Neustart des Servers dieses PCs
  (PostgresVerbindung.wiederbeleben, gesetzt in datenspeicher);
- eine Eingabe, die gerade nicht gespeichert werden kann, geht nicht verloren: speichern() versucht einmal neu zu
  verbinden; klappt das nicht, merkt es die Eingabe (mit gelesener Version und angezeigtem Wert, Schritt 3) und
  meldet SpaeterGespeichert. Der Wächter im Hauptfenster prüft alle PRUEF_MS die Verbindung und trägt gemerkte
  Eingaben in ihrer Reihenfolge nach, sobald die Datenbank wieder da ist. Hat jemand dasselbe Feld inzwischen
  geändert, kommt die Rückfrage aus Schritt 3 (konflikt_dialog).
Ohne Qt bis auf Waechter (QTimer).
"""
import time

from . import db_verbindung

PRUEF_MS = 15_000


class SpaeterGespeichert(Exception):
    """Keine Verbindung: die Eingabe ist gemerkt und wird nachgetragen."""


def _v(db):
    return getattr(db.con, "v", None)


def neu_verbinden(db):
    """Verbindung neu aufbauen (mit Neustart des Servers dieses PCs). VerbindungWeg, wenn es nicht geht."""
    v = _v(db)
    if v is None or not hasattr(v, "neu_verbinden"):
        return
    v.neu_verbinden()
    db.con._offen = False           # eine offene Transaktion der Hülle ging mit der alten Verbindung verloren


def erreichbar(db):
    """True, wenn die Datenbank antwortet (baut eine abgebrochene Verbindung dabei neu auf)."""
    try:
        db.con.execute("SELECT 1").fetchone()
        return True
    except db_verbindung.VerbindungWeg:
        try:
            neu_verbinden(db)
            db.con.execute("SELECT 1").fetchone()
            return True
        except db_verbindung.DbFehler:
            return False


def ausstehend(db):
    """Gemerkte, noch nicht gespeicherte Eingaben dieser Datenbank: [dict(text, tun, zeit)]."""
    liste = getattr(db, "_ausstehend", None)
    if liste is None:
        liste = db._ausstehend = []
    return liste


def speichern(db, tun, text):
    """tun() ausführen (eine Eingabe speichern). Bricht die Verbindung ab: einmal neu verbinden und wiederholen;
    geht auch das nicht, Eingabe merken und SpaeterGespeichert auslösen. Andere Fehler (Konflikt, ValueError)
    gehen unverändert an den Aufrufer."""
    if ausstehend(db):                  # Reihenfolge wahren: erst die älteren Eingaben
        nachtragen(db)
        if ausstehend(db):
            ausstehend(db).append(dict(text=text, tun=tun, zeit=time.time()))
            raise SpaeterGespeichert(text)
    try:
        return tun()
    except db_verbindung.VerbindungWeg:
        try:
            neu_verbinden(db)
            return tun()
        except db_verbindung.VerbindungWeg:
            ausstehend(db).append(dict(text=text, tun=tun, zeit=time.time()))
            raise SpaeterGespeichert(text) from None


def nachtragen(db, konflikt=None):
    """Gemerkte Eingaben der Reihe nach speichern, solange die Verbindung steht. konflikt(k) bei einem
    AenderungsKonflikt: True = trotzdem speichern (tun(erzwingen=True)), sonst verwerfen. Ergebnis: (gespeichert,
    verworfen, offen)."""
    from .datenbank import AenderungsKonflikt
    liste = ausstehend(db)
    gespeichert = verworfen = 0
    if liste and not erreichbar(db):
        return 0, 0, len(liste)
    while liste:
        e = liste[0]
        try:
            e["tun"]()
        except db_verbindung.VerbindungWeg:
            break
        except AenderungsKonflikt as k:
            if konflikt is not None and konflikt(k):
                try:
                    e["tun"](erzwingen=True)
                    gespeichert += 1
                except db_verbindung.VerbindungWeg:
                    break
            else:
                verworfen += 1
            liste.pop(0)
            continue
        except Exception:               # noqa: BLE001 - eine fehlerhafte Eingabe hält die übrigen nicht auf
            from . import protokoll
            protokoll.warnung(f"Eingabe nicht nachgetragen: {e['text']}")
            verworfen += 1
            liste.pop(0)
            continue
        gespeichert += 1
        liste.pop(0)
    return gespeichert, verworfen, len(liste)


def zustand_text(db):
    """Kurzer Text: verbunden seit, Abbrüche, neu verbunden, ausstehende Eingaben."""
    v = _v(db)
    z = getattr(v, "zustand", None)
    if not z:
        return "Verbindung: Datei (SQLite)"
    seit = time.strftime("%H:%M", time.localtime(z["seit"])) if z.get("seit") else "–"
    t = (f"Verbindung: {'verbunden' if z['verbunden'] else 'UNTERBROCHEN'} (seit {seit}), Abbrüche "
         f"{z['abbrueche']}, neu verbunden {z['neu_verbunden']}")
    n = len(ausstehend(db))
    return t + (f", {n} Eingaben warten auf das Speichern" if n else "")


class Waechter:
    """Im Hauptfenster: alle PRUEF_MS prüfen, Statuszeile bei Abbruch und Wiederkehr, Eingaben nachtragen."""

    def __init__(self, fenster):
        from PySide6.QtCore import QTimer
        self.f = fenster
        self.weg = False
        self.uhr = QTimer(fenster)
        self.uhr.timeout.connect(self.pruefen)
        self.uhr.start(PRUEF_MS)

    def pruefen(self):
        db = self.f.db
        if db_verbindung.ist_sqlite(db.con):
            return
        da = erreichbar(db)
        if not da:
            if not self.weg:
                self.weg = True
                self.f.meldung("Datenbank nicht erreichbar – das Programm verbindet von selbst neu. Eingaben werden "
                               "gemerkt und danach gespeichert.", fehler=True)
            return
        if self.weg or ausstehend(db):
            from . import konflikt_dialog
            g, v, offen = nachtragen(db, konflikt=lambda k: konflikt_dialog.fragen(k) == konflikt_dialog.MEINE)
            self.weg = bool(offen)
            if not offen:
                zusatz = f" {g} gemerkte Eingaben gespeichert." if g else ""
                zusatz += f" {v} verworfen (inzwischen woanders geändert)." if v else ""
                self.f.meldung("Datenbank wieder verbunden." + zusatz)
