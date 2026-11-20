"""Versionsnummern gegen Überschreiben (Datenbank-Auftrag 19.11.2026, Schritt 3 „optimistische Sperre“).

Prüft:
- jede Änderung einer Zeile (Angebot, Position, Stammdaten) erhöht ihre Versionsnummer, über jeden Weg (auch
  db.con direkt wie Abgleich und Import); gelöschte Zeilen verlieren ihren Eintrag; Stammdaten-Zähler unberührt;
- aendern/angebot_aendern/position_aendern mit version= und erwartet=: gleiche Version oder nur andere Felder
  geändert -> gespeichert, neue Version zurück; dasselbe Feld inzwischen anders -> AenderungsKonflikt mit
  gespeichertem Wert und Eingabe, nichts geschrieben; Zeile gelöscht -> Konflikt „gelöscht“;
- zwei Verbindungen (zwei Programmfenster/Starts auf demselben Datenbestand): die spätere Eingabe überschreibt
  die frühere nicht still;
- ohne version/erwartet wie bisher (alte Aufrufer unverändert);
- Oberfläche: Stammdaten-Tabelle, Positionen und Angebotskopf fragen bei einem Konflikt (Meine Eingabe / Neu laden);
- Versionen gehören nicht in Sicherungen und Kopien (db_kopie.EIGENE).

Aufruf: python tests/test_zeilen_version.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import db_kopie, konflikt_dialog  # noqa: E402
from rohrlaser.datenbank import VERSIONEN, AenderungsKonflikt, Datenbank  # noqa: E402


def ok(text):
    print("OK     " + text)


def pos(pid, d=None):
    d = d or db
    return dict(d.con.execute("SELECT * FROM positionen WHERE id=?", (pid,)).fetchone())


tmp = Path(tempfile.mkdtemp())
pfad = tmp / "Daten" / "rohrlaser.db"
db = Datenbank(pfad)
aid = db.angebot_neu(dict(kunde="Version GmbH"))
pid = db.position_neu(aid, dict(stueck=10, bezeichnung="Rohr A"))
kid = db.neu("kunden", dict(kundennr="K-1", name="Alt GmbH"))

a0, p0, k0 = db.version("angebote", aid), db.version("positionen", pid), db.version("kunden", kid)
v = db.angebot_aendern(aid, "kunde", "Neu GmbH")
assert v == db.version("angebote", aid) > a0
vp = db.position_aendern(pid, "stueck", 20)
assert vp == db.version("positionen", pid) == p0 + 1
assert db.version("angebote", aid) > v, "Position geändert -> Angebot (geaendert) hat neue Version"
vk = db.aendern("kunden", kid, "name", "Neu GmbH")
assert vk == k0 + 1
with db.con:                                                # auch direkt (Abgleich, Import, Neuberechnung)
    db.con.execute("UPDATE kunden SET name='Direkt GmbH' WHERE id=?", (kid,))
assert db.version("kunden", kid) == k0 + 2
assert db.versionen("kunden", [kid, 999999]) == {kid: k0 + 2, 999999: 0}
stand = db.stammdaten_stand()
db.position_aendern(pid, "stueck", 21)
assert db.stammdaten_stand() == stand, "Versionen sind keine Stammdaten (Zwischenspeicher bleibt gültig)"
ok("jede Änderung erhöht die Versionsnummer der Zeile, auch direkt über db.con; Stammdaten-Zähler unberührt")

# ------------------------------------------------------------------ optimistische Sperre
v0 = db.version("positionen", pid)
v1 = db.position_aendern(pid, "stueck", 30, version=v0, erwartet=21)
assert v1 == v0 + 1 and pos(pid)["stueck"] == 30
# jemand anders ändert ein ANDERES Feld: alte Version, aber erwarteter Wert stimmt -> gespeichert
with db.con:
    db.con.execute("UPDATE positionen SET bezeichnung='Rohr B' WHERE id=?", (pid,))
v2 = db.position_aendern(pid, "stueck", 31, version=v1, erwartet=30)
assert pos(pid)["stueck"] == 31 and pos(pid)["bezeichnung"] == "Rohr B" and v2 > v1
# jemand anders ändert DASSELBE Feld -> Konflikt, nichts geschrieben
with db.con:
    db.con.execute("UPDATE positionen SET stueck=40 WHERE id=?", (pid,))
try:
    db.position_aendern(pid, "stueck", 50, version=v2, erwartet=31)
    raise AssertionError("Konflikt erwartet")
except AenderungsKonflikt as k:
    assert (k.tabelle, k.zeilen_id, k.feld, k.jetzt, k.eingabe, k.geloescht) == ("positionen", pid, "stueck", 40, 50,
                                                                                 False), vars(k)
    assert "inzwischen geändert" in str(k)
assert pos(pid)["stueck"] == 40, "bei Konflikt nichts überschrieben"
# andere Seite hat schon dasselbe eingetragen: kein Konflikt
db.position_aendern(pid, "stueck", 40, version=v2, erwartet=31)
# nur Version, ohne erwarteten Wert: jede fremde Änderung zählt
vk = db.version("kunden", kid)
with db.con:
    db.con.execute("UPDATE kunden SET plz_ort='Hagen' WHERE id=?", (kid,))
try:
    db.aendern("kunden", kid, "name", "Später GmbH", version=vk)
    raise AssertionError("Konflikt erwartet")
except AenderungsKonflikt as k:
    assert k.jetzt == "Direkt GmbH"
assert db.aendern("kunden", kid, "name", "Später GmbH", version=db.version("kunden", kid)) > vk
# Kopf
va = db.version("angebote", aid)
with db.con:
    db.con.execute("UPDATE angebote SET kunde='Fremd GmbH' WHERE id=?", (aid,))
try:
    db.angebot_aendern(aid, "kunde", "Meine GmbH", version=va, erwartet="Neu GmbH")
    raise AssertionError("Konflikt erwartet")
except AenderungsKonflikt as k:
    assert k.jetzt == "Fremd GmbH" and k.eingabe == "Meine GmbH"
assert db.angebot(aid)["kunde"] == "Fremd GmbH"
db.angebot_aendern(aid, "kunde", "Meine GmbH")          # ohne Prüfung wie bisher („Meine Eingabe übernehmen“)
assert db.angebot(aid)["kunde"] == "Meine GmbH"
# Zahlen mit Rundungsrauschen und leer/None gelten gleich
db.position_aendern(pid, "preis_m", 0.1 + 0.2)
db.position_aendern(pid, "preis_m", 5.0, version=0, erwartet=0.3)
db.position_aendern(pid, "bezeichnung", None)
db.position_aendern(pid, "bezeichnung", "x", version=0, erwartet="")
# gelöscht
p2 = db.position_neu(aid, dict(stueck=1))
v = db.version("positionen", p2)
db.positionen_loeschen([p2])
assert db.con.execute(f"SELECT COUNT(*) FROM {db._stand_schema}{VERSIONEN} WHERE tabelle='positionen' AND "
                      "zeilen_id=?", (p2,)).fetchone()[0] == 0, "gelöschte Zeile: Eintrag weg"
try:
    db.position_aendern(p2, "stueck", 2, version=v, erwartet=1)
    raise AssertionError("Konflikt erwartet")
except AenderungsKonflikt as k:
    assert k.geloescht and "gelöscht" in str(k)
ok("gleiche Version oder nur andere Felder geändert: gespeichert; dasselbe Feld anders: Konflikt mit beiden Werten, "
   "nichts geschrieben; gelöscht: Konflikt; ohne Angaben wie bisher")

# ------------------------------------------------------------------ zwei Verbindungen auf denselben Datenbestand
db2 = Datenbank(pfad)
p = pos(pid)
v_a = db.version("positionen", pid)
v_b = db2.version("positionen", pid)
assert v_a == v_b
db.position_aendern(pid, "stueck", 70, version=v_a, erwartet=p["stueck"])
try:
    db2.position_aendern(pid, "stueck", 80, version=v_b, erwartet=p["stueck"])
    raise AssertionError("zweites Fenster hätte still überschrieben")
except AenderungsKonflikt as k:
    assert k.jetzt == 70
assert pos(pid, db2)["stueck"] == 70
db2.schliessen()
ok("zwei Verbindungen: die spätere Eingabe überschreibt die frühere nicht still")

assert VERSIONEN in db_kopie.EIGENE
ok("Versionen gehören nicht in Sicherungen und Kopien")

# ------------------------------------------------------------------ Oberfläche
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import fenster  # noqa: E402
from rohrlaser.datenbank import TABELLE  # noqa: E402

app = QApplication.instance() or QApplication([])
meldungen = []
m = fenster.StammdatenModell(db, TABELLE["kunden"], lambda t, fehler=False: meldungen.append((t, fehler)))
zeile = next(i for i, z in enumerate(m.daten) if z["id"] == kid)
spalte = next(i for i, (a, f) in enumerate(m.spalten) if a == "feld" and f.name == "name")
idx = m.index(zeile, spalte)
with db.con:
    db.con.execute("UPDATE kunden SET name='Kollege GmbH' WHERE id=?", (kid,))
konflikt_dialog.ANTWORT = konflikt_dialog.NEU_LADEN
assert m.setData(idx, "Ich GmbH", Qt.ItemDataRole.EditRole) is False
assert db.con.execute("SELECT name FROM kunden WHERE id=?", (kid,)).fetchone()[0] == "Kollege GmbH" and m.daten[zeile]["name"] == "Kollege GmbH"
assert any("nicht gespeichert" in t for t, _ in meldungen), meldungen
with db.con:
    db.con.execute("UPDATE kunden SET name='Kollege 2 GmbH' WHERE id=?", (kid,))
konflikt_dialog.ANTWORT = konflikt_dialog.MEINE
assert m.setData(idx, "Ich GmbH", Qt.ItemDataRole.EditRole) is True
assert db.con.execute("SELECT name FROM kunden WHERE id=?", (kid,)).fetchone()[0] == "Ich GmbH"
ok("Stammdaten-Tabelle: Konflikt -> Neu laden (fremder Wert bleibt) oder Meine Eingabe (überschreibt bewusst)")
# Positionstabelle und Angebotskopf (AngebotSeite.position_speichern / _kopf_speichern) ohne ganzes Fenster
from PySide6.QtCore import QObject  # noqa: E402

from rohrlaser.angebot import POSITIONEN  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402


class Seite(QObject):
    def __init__(self):
        super().__init__()
        self.db, self.id, self.geladen, self.texte = db, aid, 0, []
        self.f = type("F", (), {"meldung": lambda _s, t, fehler=False: self.texte.append(t)})()
        self.pos_versionen = db.positions_versionen(aid)

    def neu_laden(self, *_):
        self.geladen += 1


seite = Seite()
feld = POSITIONEN.feld("stueck")
p = pos(pid)
assert AngebotSeite.position_speichern(seite, p, feld, p["stueck"] + 1) is True
assert seite.pos_versionen[pid] == db.version("positionen", pid)
with db.con:
    db.con.execute("UPDATE positionen SET stueck=999 WHERE id=?", (pid,))
konflikt_dialog.ANTWORT = konflikt_dialog.NEU_LADEN
assert AngebotSeite.position_speichern(seite, dict(p, stueck=p["stueck"] + 1), feld, 5) is False
app.processEvents()
assert pos(pid)["stueck"] == 999 and seite.geladen == 1 and "nicht gespeichert" in seite.texte[-1]
konflikt_dialog.ANTWORT = konflikt_dialog.MEINE
assert AngebotSeite.position_speichern(seite, dict(p, stueck=p["stueck"] + 1), feld, 5) is True
assert pos(pid)["stueck"] == 5
ok("Positionstabelle: Konflikt -> Neu laden (fremder Wert bleibt) oder Meine Eingabe")
konflikt_dialog.ANTWORT = None
db.schliessen()
print("OK: Versionsnummern gegen Überschreiben")
