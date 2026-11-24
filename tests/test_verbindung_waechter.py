"""Verbindungsabbruch, Neustart, keine verlorenen Eingaben, Statusanzeige (Datenbank-Auftrag 19.11.2026, Schritt 5).

Mit echtem Server je Datenordner (wie test_pg_rollen; als root oder ohne PostgreSQL-Programme übersprungen):
- Server dieses PCs beendet: Lesen und Speichern starten ihn von selbst neu (wiederbeleben), Zustand zählt mit;
- Server bleibt weg: die Eingabe wird gemerkt (SpaeterGespeichert), weitere in Reihenfolge dahinter; sobald er wieder
  da ist, trägt nachtragen() alle nach; hat jemand dasselbe Feld inzwischen geändert, entscheidet die Rückfrage;
- Stammdaten-Tabelle: Eingabe bleibt sichtbar und wird nachgetragen; der Wächter meldet Abbruch und Wiederkehr;
- Statusanzeige: Version, Größe, Verbindungen, Sperren, langsame Abfragen, letzte Sicherung, Verbindungszustand.

Aufruf: python tests/test_verbindung_waechter.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import datenspeicher, pg_lokal, verbindung_waechter  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK     " + text)


if hasattr(os, "getuid") and os.getuid() == 0:
    print("übersprungen: initdb läuft nicht als root")
    sys.exit(0)
try:
    pg_lokal.programme()
except pg_lokal.PgFehlt:
    print("übersprungen: keine PostgreSQL-Programme")
    sys.exit(0)

tmp = Path(tempfile.mkdtemp())
try:
    pfad = tmp / "Daten" / "rohrlaser.db"
    db = Datenbank(pfad)
    v = db.con.v
    aid = db.angebot_neu(dict(kunde="Wächter GmbH"))
    kid = db.neu("kunden", dict(kundennr="W-1", name="Alt"))
    s = datenspeicher.server(pfad)
    assert v.wiederbeleben is not None and v.zustand["verbunden"]

    # ------------------------------------------------------------------ Server weg: von selbst neu gestartet
    s.stoppen()
    assert not s.laeuft()
    assert db.angebot(aid)["kunde"] == "Wächter GmbH", "Lesen startet den Server neu"
    assert s.laeuft() and v.zustand["neu_verbunden"] >= 1 and v.zustand["abbrueche"] >= 1, v.zustand
    s.stoppen()
    verbindung_waechter.speichern(db, lambda: db.angebot_aendern(aid, "kunde", "Neu GmbH"), "Kunde")
    assert db.angebot(aid)["kunde"] == "Neu GmbH"
    ok("Server dieses PCs beendet: Lesen und Speichern starten ihn neu, Abbrüche und Neuverbindungen gezählt")

    # ------------------------------------------------------------------ Server bleibt weg: Eingaben gemerkt
    echt = v.wiederbeleben

    def kaputt():
        raise RuntimeError("Server startet nicht (Test)")

    v.wiederbeleben = kaputt
    s.stoppen()
    for wert in ("Erst GmbH", "Dann GmbH"):
        try:
            verbindung_waechter.speichern(db, lambda w=wert: db.angebot_aendern(aid, "kunde", w), f"Kunde {wert}")
            raise AssertionError("ohne Server gespeichert?")
        except verbindung_waechter.SpaeterGespeichert:
            pass
    assert [e["text"] for e in verbindung_waechter.ausstehend(db)] == ["Kunde Erst GmbH", "Kunde Dann GmbH"]
    assert "UNTERBROCHEN" in verbindung_waechter.zustand_text(db) and "2 Eingaben warten" in \
        verbindung_waechter.zustand_text(db)
    assert verbindung_waechter.nachtragen(db) == (0, 0, 2), "ohne Server bleibt alles gemerkt"
    v.wiederbeleben = echt
    assert verbindung_waechter.nachtragen(db) == (2, 0, 0)
    assert db.angebot(aid)["kunde"] == "Dann GmbH", "in Reihenfolge nachgetragen"
    ok("Server bleibt weg: Eingaben gemerkt (Reihenfolge), danach alle nachgetragen")

    # Konflikt beim Nachtragen: jemand hat dasselbe Feld inzwischen geändert
    va = db.version("angebote", aid)
    v.wiederbeleben = kaputt
    s.stoppen()
    try:
        verbindung_waechter.speichern(db, lambda erzwingen=False: db.angebot_aendern(
            aid, "kunde", "Meins GmbH", **({} if erzwingen else dict(version=va, erwartet="Dann GmbH"))), "Kunde")
    except verbindung_waechter.SpaeterGespeichert:
        pass
    v.wiederbeleben = echt
    s.starten()
    andere = Datenbank(pfad)
    andere.angebot_aendern(aid, "kunde", "Kollege GmbH")
    andere.schliessen()
    assert verbindung_waechter.nachtragen(db, konflikt=lambda k: False) == (0, 1, 0)
    assert db.angebot(aid)["kunde"] == "Kollege GmbH", "Konflikt: fremder Wert bleibt"
    ok("Nachtragen mit Konflikt: Rückfrage entscheidet, nichts still überschrieben")

    # ------------------------------------------------------------------ Oberfläche: Stammdaten und Wächter
    from PySide6.QtCore import Qt  # noqa: E402
    from PySide6.QtWidgets import QApplication  # noqa: E402

    from rohrlaser import fenster  # noqa: E402
    from rohrlaser.datenbank import TABELLE  # noqa: E402

    app = QApplication.instance() or QApplication([])
    meldungen = []
    m = fenster.StammdatenModell(db, TABELLE["kunden"], lambda t, fehler=False: meldungen.append(t))
    zeile = next(i for i, z in enumerate(m.daten) if z["id"] == kid)
    spalte = next(i for i, (a, f) in enumerate(m.spalten) if a == "feld" and f.name == "name")
    v.wiederbeleben = kaputt
    s.stoppen()
    assert m.setData(m.index(zeile, spalte), "Gemerkt GmbH", Qt.ItemDataRole.EditRole) is True
    assert m.daten[zeile]["name"] == "Gemerkt GmbH" and "gemerkt" in meldungen[-1]

    class F:
        def __init__(self):
            self.db, self.texte = db, []

        def meldung(self, t, fehler=False):
            self.texte.append(t)

    f = F()
    w = verbindung_waechter.Waechter.__new__(verbindung_waechter.Waechter)
    w.f, w.weg = f, False
    w.pruefen()
    assert w.weg and "nicht erreichbar" in f.texte[-1]
    v.wiederbeleben = echt
    w.pruefen()
    assert not w.weg and "wieder verbunden" in f.texte[-1] and "1 gemerkte Eingaben gespeichert" in f.texte[-1]
    assert db.con.execute("SELECT name FROM kunden WHERE id=?", (kid,)).fetchone()[0] == "Gemerkt GmbH"
    ok("Stammdaten-Tabelle: Eingabe bleibt sichtbar, Wächter meldet Abbruch und Wiederkehr und trägt nach")

    # ------------------------------------------------------------------ Statusanzeige
    db.sicherung()
    v.langsam.append((0, 1.5, "SELECT langsam"))
    text = datenspeicher.status(db)
    for teil in ("Verbindung: verbunden", "PostgreSQL ", "Verbindungen", "wartende Sperren", "SELECT langsam",
                 "Letzte Sicherung:", "PostgreSQL-Abbild"):
        assert teil in text, (teil, text)
    ok("Statusanzeige: Verbindung, Version, Größe, Verbindungen, Sperren, langsame Abfragen, letzte Sicherung")
    db.schliessen()
finally:
    datenspeicher.alle_stoppen()
print("OK: Verbindung überwacht, Eingaben bleiben erhalten")
