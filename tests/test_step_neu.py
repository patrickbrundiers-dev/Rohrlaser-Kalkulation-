"""Prüft „Neues Angebot aus STEP“ (Plan „Arbeitsabläufe effizienter“ W11, Schritt AB3): Kunde aus dem Ordnernamen
bzw. aus dem letzten Angebot mit Importprofil, Angebot mit Kundenvorgaben anlegen, öffnen und den STEP-Import mit den
gefundenen Dateien starten; ohne STEP-Dateien und im Lesemodus wird nichts angelegt.

Aufruf: python tests/test_step_neu.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import step_neu  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Kunde aus dem Ordnernamen
kunden = [dict(kundennr="10001", name="Müller GmbH"), dict(kundennr="10002", name="Müller GmbH & Co. Stahlbau"),
          dict(kundennr="20001", name="AB")]
tmp = Path(tempfile.mkdtemp())
assert step_neu.kunde_aus_ordner(kunden, [tmp / "Anfragen" / "Müller GmbH" / "2026-10" / "teil.step"]) == "10001"
assert step_neu.kunde_aus_ordner(kunden, [tmp / "müller gmbh & co stahlbau anfrage 12" / "a.stp"]) == "10002"
assert step_neu.kunde_aus_ordner(kunden, [tmp / "K 20001 Rahmen" / "a.stp"]) == "20001"
assert step_neu.kunde_aus_ordner(kunden, [tmp / "AB" / "a.stp"]) is None          # Namen unter 3 Zeichen nicht
assert step_neu.kunde_aus_ordner(kunden, [tmp / "Sonstiges" / "a.stp"]) is None
ok("Kunde aus dem Ordnernamen: Name (längster zuerst) oder Kundennummer, bis drei Ordner darüber")

# ------------------------------------------------------------------ mit Datenbank und Oberfläche
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
k1, k2 = [k for k in db.zeilen("kunden")][:2]
importe = []
AngebotSeite.step_importieren = lambda self, dateien=None, *a, **kw: importe.append((self.id, dateien))

ordner = tmp / "Eingang" / k1["name"] / "Anfrage"
ordner.mkdir(parents=True)
for n in ("b.step", "a.STP", "zeichnung.pdf"):
    (ordner / n).write_text("x")
vorher = len(db.angebote())
s = fenster.angebote.neu_aus_step([str(ordner)])
assert s is not None and len(db.angebote()) == vorher + 1
assert s.kopf["kundennr"] == k1["kundennr"] and s.kopf["kunde"] == k1["name"]
assert fenster.reiter.currentWidget() is s
assert importe[-1] == (s.id, [str(ordner / "a.STP"), str(ordner / "b.step")]), importe
assert db.einstellung("step_letzter_ordner") == str(ordner)
ok("Ordner gezogen: Angebot für den Kunden aus dem Ordnernamen angelegt, geöffnet, Import mit den STEP-Dateien")

# Kein Kunde im Ordnernamen: Kunde des letzten eigenen Angebots mit Importprofil
db.neu("importprofile", dict(kundennr=k2["kundennr"]))
db.angebot_aendern(db.angebot_neu(dict(kundennr=k2["kundennr"])), "bemerkung", "zuletzt")
fremd = tmp / "Sonstiges"
fremd.mkdir()
(fremd / "c.step").write_text("x")
assert step_neu.kunde_vorschlag(db, [str(fremd / "c.step")]) == k2["kundennr"]
s2 = fenster.angebote.neu_aus_step([str(fremd / "c.step")])
assert s2.kopf["kundennr"] == k2["kundennr"] and importe[-1] == (s2.id, [str(fremd / "c.step")])
ok("Ohne Kunde im Ordnernamen: Kunde des zuletzt geänderten Angebots mit Importprofil")

# Kundenvorgaben (W2) gelten auch hier; kundennr '' = ohne Kunde
db.neu("kundenvorgaben", dict(kundennr=k1["kundennr"], stange=12000))
s3 = fenster.angebote.neu_aus_step([str(ordner)])
assert s3.kopf["stange"] == 12000
s4 = fenster.angebote.neu_aus_step([str(ordner)], kundennr="")
assert not s4.kopf.get("kundennr")
ok("Kundenvorgaben gelten beim Anlegen; ohne Kunde möglich")

# Keine STEP-Dateien, Lesemodus: nichts angelegt
leer = tmp / "leer"
leer.mkdir()
(leer / "x.pdf").write_text("x")
n = len(db.angebote())
assert fenster.angebote.neu_aus_step([str(leer)]) is None and len(db.angebote()) == n
db.nur_lesen = "Test"
assert fenster.angebote.neu_aus_step([str(ordner)]) is None and len(db.angebote()) == n
db.nur_lesen = None
ok("Ohne STEP-Dateien und im Lesemodus: kein Angebot")

# Ablageziele: Angebotsliste und Startseite nehmen gezogene Dateien an, Knöpfe vorhanden
from PySide6.QtWidgets import QPushButton  # noqa: E402
assert fenster.angebote.acceptDrops() and fenster.start.acceptDrops()
texte = {b.text() for b in fenster.angebote.findChildren(QPushButton)} | \
    {b.text() for b in fenster.start.findChildren(QPushButton)}
assert "Aus STEP …" in {b.text() for b in fenster.angebote.findChildren(QPushButton)}
assert "Aus STEP …" in {b.text() for b in fenster.start.findChildren(QPushButton)}
ok("Angebotsliste und Startseite: Ziehen und Knopf „Aus STEP …“")

print("Alle Prüfungen bestanden.")
