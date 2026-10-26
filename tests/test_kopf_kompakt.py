"""Prüft Angebotskopf und Kalkulation kompakter (Patrick 25.10.2026):
- K1 Rüstzeit je Maschine (Angebot) nur sichtbar, wenn sie nicht 0 ist (Wert aus dem Snapshot des Angebots)
- K2 Stangenwechsel je Stange je Angebot änderbar (Snapshot), SN bleibt, Preis ändert sich, gelb bei Abweichung,
     „Vorgaben aus Einstellungen“ setzt zurück; Snapshot vor 0.8.10 (ohne SN) behält den alten SN-Wert
- K3 Fracht rechts neben der Kalkulation ab FRACHT_RECHTS_AB, darunter bei 1366 px; Fenster passt auf 1366 px
- K4 Bearbeiter neben der Bemerkung, Lieferzeit-Vorschau nur ohne Lieferzeit als eigene Zeile

Aufruf: python tests/test_kopf_kompakt.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.angebot_oben import FRACHT_RECHTS_AB  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
fenster.resize(1920, 1080)
fenster.show()
db.einstellung_setzen("mindestpreis", 0)           # kleines Angebot: Stangenwechsel soll den Preis ändern
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for i in range(3):
    db.position_neu(a, dict(pos=10 * (i + 1), artikel=f"T{i}", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                            laenge=800 + 100 * i, stueck=4, schneidweg=320, einstiche=2))
s = fenster.angebot_oeffnen(a)
s.optimieren()
kb = s.kopf_bereich
kb.kalkulation_aufklappen(True)
app.processEvents()

# ------------------------------------------------------------------ K1 Rüstzeit je Maschine
zb = db.angebot(a)["zeitbasis"]
assert zb["maschine"]["ruestzeit"], zb
b, w, _ = kb.maschine_kalk["ruestzeit"]
assert w.isVisibleTo(kb) and b.isVisibleTo(kb)
zb["maschine"]["ruestzeit"] = 0
db.zeitbasis_speichern(a, zb)
s.neu_laden()
b, w, _ = kb.maschine_kalk["ruestzeit"]
assert not w.isVisibleTo(kb) and not b.isVisibleTo(kb)
for n in ("stangenwechsel", "stangenwechsel_sn", "stundensatz"):
    assert kb.maschine_kalk[n][1].isVisibleTo(kb), n
ok("K1 Rüstzeit je Maschine (Angebot) mit 0 min ausgeblendet, mit Wert sichtbar; übrige Maschinenwerte bleiben")

# ------------------------------------------------------------------ K2 Stangenwechsel je Angebot
sw = kb.stangenwechsel
assert sw.value() == 24 and "background" not in sw.styleSheet(), (sw.value(), sw.styleSheet())
assert kb.maschine_kalk["stangenwechsel_sn"][1].text() == "29 s"
vorher = s._verkauf()
sw.setValue(40)
sw.editingFinished.emit()
m = db.angebot(a)["zeitbasis"]["maschine"]
assert m["stangenwechsel"] == 40 and m["stangenwechsel_sn"] == 29, m
_, su = s._rechnung()
assert su["stangenwechsel"] == 40 and su["stangenwechsel_sn"] == 29 and s._verkauf() > vorher, su["stangenwechsel"]
assert kb.stangenwechsel.value() == 40 and "background" in kb.stangenwechsel.styleSheet()
assert kb.maschine_kalk["stangenwechsel_sn"][1].text() == "29 s"
kalk, zeiten = kb.abweichungen()
assert any(t.startswith("Stangenwechsel 40 statt 24") for t in zeiten), zeiten
assert s.stangenwechsel_setzen(40) is False          # gleicher Wert: nichts gespeichert
# Stammdaten bleiben unverändert
assert db.kontext().maschinen["T11"]["stangenwechsel"] == 24
s.kalkulation_zuruecksetzen()
assert db.angebot(a)["zeitbasis"]["maschine"]["stangenwechsel"] == 24 and kb.stangenwechsel.value() == 24
# Snapshot vor 0.8.10 (ohne SN): SN behält den bisherigen Stangenwechsel
zb = db.angebot(a)["zeitbasis"]
zb["maschine"].pop("stangenwechsel_sn")
db.zeitbasis_speichern(a, zb)
s.neu_laden()
assert kb.maschine_kalk["stangenwechsel_sn"][1].text() == "24 s"
assert s.stangenwechsel_setzen(30)
m = db.angebot(a)["zeitbasis"]["maschine"]
assert m["stangenwechsel"] == 30 and m["stangenwechsel_sn"] == 24, m
assert rechnen.stangenwechsel_zeiten(m) == (30, 24)
ok("K2 Stangenwechsel je Stange je Angebot änderbar (Snapshot), SN bleibt, Preis folgt, gelb, Vorgaben setzen zurück")

# ------------------------------------------------------------------ K3 Fracht neben der Kalkulation
kb.breite_anpassen(1920)
app.processEvents()
assert kb.fracht_rechts
idx = kb.karten.indexOf(kb.fracht_karte)
assert kb.karten.getItemPosition(idx)[:2] == (0, 1)
kb.breite_anpassen(FRACHT_RECHTS_AB - 1)
assert not kb.fracht_rechts and kb.karten.getItemPosition(kb.karten.indexOf(kb.fracht_karte))[:2] == (1, 0)
fenster.resize(1366, 728)
app.processEvents()
assert fenster.minimumSizeHint().width() <= 1366, fenster.minimumSizeHint()
assert not kb.fracht_rechts
fenster.resize(1920, 1080)
app.processEvents()
assert kb.fracht_rechts
ok("K3 Fracht rechts neben der Kalkulation ab %d px, darunter bei 1366 px; Fenster passt auf 1366 px" % FRACHT_RECHTS_AB)

# ------------------------------------------------------------------ K4 Angebotskopf
g = kb.kopf_inhalt.layout().itemAt(0).layout()
zeile_bem = g.getItemPosition(g.indexOf(kb.felder["bemerkung"]))[0]
assert g.getItemPosition(g.indexOf(kb.bearbeiter))[0] == zeile_bem
kb.kopf_aufklappen(True)
db.angebot_aendern(a, "lieferzeit_art", None)
db.angebot_aendern(a, "lieferzeit_zusatz", None)
s.neu_laden()
assert kb.lz_vorschau.isVisibleTo(kb) and "Keine Lieferzeit" in kb.lz_vorschau.text()
db.angebot_aendern(a, "lieferzeit_art", "Wochen")
db.angebot_aendern(a, "lieferzeit_wert", "2")
s.neu_laden()
assert not kb.lz_vorschau.isVisibleTo(kb) and "2 Wochen" in kb.lz_art.toolTip() and "2 Wochen" in kb.lz_vorschau.text()
ok("K4 Bearbeiter neben der Bemerkung; Lieferzeit-Vorschau nur ohne Lieferzeit, sonst als Tooltip")
