"""Prüft die Trennung von Einstellungen (Standard) und Werten je Angebot:
- Angebot A mit eigenen Werten, Angebot B mit Standardwerten; Einstellungen ändern -> A und B unverändert, neues
  Angebot C übernimmt den neuen Standard; erneut öffnen lädt alle Werte.
- Abweichungen vom Standard: Liste (Kalkulationswerte, Stundensätze, Zeitvorgaben), gelbe Markierung mit Tooltip,
  Kurzfassung, Preisänderung in der Statuszeile, 'Vorgaben aus Einstellungen' nennt die Änderungen und lässt von
  Hand eingetragene Werte an den Positionen stehen.

Aufruf: python tests/test_angebot_einstellungen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import copy
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.angebot import kalk_abweichungen  # noqa: E402
from rohrlaser.angebot_fenster import preis_aenderung  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")


def neues_angebot(kunde):
    a = db.angebot_neu(dict(kunde=kunde, skonto=0))
    db.position_neu(a, dict(pos=10, artikel="T1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800,
                            stueck=40, schneidweg=320, einstiche=2, zeit_manuell=12.5, preis_m=9.5))
    return a


a, b = neues_angebot("A"), neues_angebot("B")
db.angebot_aendern(a, "gewinn", 12.0)
zb = copy.deepcopy(db.angebot(a)["zeitbasis"])
zb["maschine"]["stundensatz"] = 160.0
db.zeitbasis_speichern(a, zb)

# ------------------------------------------------------------------ E1 Abweichungen
vorg = db.kalkulation_vorgaben()
abw = [(f.name, w, std) for f, w, std in kalk_abweichungen(db.angebot(a), vorg)]
assert abw == [("gewinn", 12.0, 10.0)], abw
assert kalk_abweichungen(db.angebot(b), vorg) == []
assert kalk_abweichungen(dict(gewinn=None), vorg) == []        # älteres Angebot ohne Wert: wie Einstellungen
zt = rechnen.zeitbasis_abweichungen(db.angebot(a)["zeitbasis"], db.zeitbasis_vorgabe(db.angebot(a)["maschine"]))
assert zt == ["Stundensatz Maschine 160 statt 150 €/h"], zt
assert rechnen.zeitbasis_abweichungen(db.angebot(b)["zeitbasis"], db.zeitbasis_vorgabe("T03")) == []
assert rechnen.zeitbasis_abweichungen(None, db.zeitbasis_vorgabe("T03")) == []
ok("E1 Abweichungen: Gewinn 12 statt 10 %, Stundensatz 160 statt 150 €/h; B ohne")

# ------------------------------------------------------------------ E2 Einstellungen ändern
kopf_a, kopf_b = db.angebot(a), db.angebot(b)
db.einstellung_setzen("gewinn", 0.20)
db.einstellung_setzen("mindestpreis", 300.0)
db.einstellung_setzen("zuschlag_fremdleistung", 0.05)
db.einstellung_setzen("zuschlag_material", 0.07)
satz = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T03")
db.aendern("maschinen", satz["id"], "stundensatz", 175.0)
for x, alt in ((a, kopf_a), (b, kopf_b)):
    neu = db.angebot(x)
    for n in ("gewinn", "zuschlag_fremdleistung", "angebotsaufschlag", "zeitbasis"):
        assert neu[n] == alt[n], (x, n, neu[n], alt[n])
c = db.angebot_neu(dict(kunde="C"))
kc = db.angebot(c)
assert kc["gewinn"] == 20.0 and kc["zuschlag_fremdleistung"] == 5.0
# Zuschlag Material und Fertigung: nicht je Angebot, immer aus den Einstellungen (auch für ältere Angebote)
assert "zuschlag_material" not in kc and "zuschlag_fertigung" not in kc
assert rechnen.einstellungen_angebot(dict(kopf_a, zuschlag_material=10.0), db.einstellungen())["zuschlag_material"] == 0.07
assert rechnen.einstellungen_angebot(kopf_a, db.einstellungen())["mindestpreis"] == 300.0   # gilt für alle Angebote
assert kc["zeitbasis"]["maschine"]["stundensatz"] == 175.0
# B weicht jetzt vom neuen Standard ab (es behält seine Werte), A weiterhin
assert {f.name for f, _, _ in kalk_abweichungen(db.angebot(b), db.kalkulation_vorgaben())} == \
    {"gewinn", "zuschlag_fremdleistung"}
ok("E2 Einstellungen geändert: A und B behalten ihre Werte und Stundensätze, neues Angebot C übernimmt den neuen Standard")

# ------------------------------------------------------------------ E3 Oberfläche
assert preis_aenderung(100.0, 112.5) == "Verkaufspreis netto 100,00 € → 112,50 €."
assert preis_aenderung(100.0, 100.001) == "Verkaufspreis netto unverändert 100,00 €." and preis_aenderung(None, 5) == ""
db.einstellung_setzen("mindestpreis", 0.0)      # sonst hebt der Mindestpreis (300 €) den Preis an: E3 prüft Gewinn
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
kb = s.kopf_bereich
assert kb.felder["gewinn"].value() == 12.0
assert "background" in kb.felder["gewinn"].styleSheet() and "Standard (Einstellungen) 20 %" in kb.felder["gewinn"].toolTip()
assert kb.felder["angebotsaufschlag"].styleSheet() == "" and "mindestpreis" not in kb.felder
assert "zuschlag_material" not in kb.felder and "zuschlag_fertigung" not in kb.felder
text = kb.abweichung_text.text()
assert text.startswith("3 Werte weichen von den Einstellungen ab") and "Gewinn 12 % statt 20 %" in text, text
assert "Stundensatz Maschine 160 statt 175 €/h" in text and "Mindestpreis" not in text
s.kopf_bereich.kalkulation_aufklappen(False)
assert "(3 abweichend von den Einstellungen)" in kb.kalk_kurz.text()
vorher = s._verkauf()
kb.felder["gewinn"].setValue(25.0)
kb.felder["gewinn"].editingFinished.emit()
assert s.kopf["gewinn"] == 25.0 and s._verkauf() > vorher
assert "Verkaufspreis netto" in fenster.statusBar().currentMessage() and "→" in fenster.statusBar().currentMessage()
kb.felder["gewinn"].setValue(20.0)                 # zurück auf den Standard: Markierung weg
kb.felder["gewinn"].editingFinished.emit()
assert kb.felder["gewinn"].styleSheet() == "" and "Gewinn" not in kb.abweichung_text.text()
ok("E3 Angebotsseite: abweichende Werte gelb mit Standard im Tooltip, Liste und Kurzfassung, Preisänderung in der Statuszeile")

# ------------------------------------------------------------------ E4 Vorgaben aus Einstellungen
p_alt = db.positionen(a)[0]
assert s.kalkulation_zuruecksetzen()
kopf = db.angebot(a)
assert kalk_abweichungen(kopf, db.kalkulation_vorgaben()) == []
assert rechnen.zeitbasis_abweichungen(kopf["zeitbasis"], db.zeitbasis_vorgabe(kopf["maschine"])) == []
p_neu = db.positionen(a)[0]
assert p_neu["zeit_manuell"] == p_alt["zeit_manuell"] == 12.5 and p_neu["preis_m"] == 9.5   # Positionen bleiben
assert not kb.abweichung_text.isVisible() and "Werte aus den Einstellungen übernommen" in fenster.statusBar().currentMessage()
assert s.kalkulation_zuruecksetzen() is False                # nichts mehr abweichend: nur Meldung
assert "entsprechen den Einstellungen" in fenster.statusBar().currentMessage()
ok("E4 'Vorgaben aus Einstellungen': alle Abweichungen übernommen, Meterpreis und Schneidzeit der Position bleiben")

# ------------------------------------------------------------------ E5 erneut öffnen
db.angebot_aendern(b, "angebotsaufschlag", 75.0)
db.angebot_aendern(b, "lieferzeit_art", "Wochen")
db.angebot_aendern(b, "lieferzeit_wert", "4")
db.schliessen()
db2 = Datenbank(tmp / "rohrlaser.db")
kb2 = db2.angebot(b)
assert kb2["angebotsaufschlag"] == 75.0 and kb2["gewinn"] == 10.0 and kb2["lieferzeit_wert"] == "4"
assert kb2["zeitbasis"]["maschine"]["stundensatz"] == 150.0
db2.schliessen()
ok("E5 Datei neu geöffnet: Werte je Angebot (Aufschlag, Gewinn, Lieferzeit, Stundensatz) unverändert geladen")

# ------------------------------------------------------------------ E6 Update auf 0.6.5: Zuschläge einmalig auf 0
db3 = Datenbank(tmp / "alt" / "rohrlaser.db")
db3.einstellung_setzen("zuschlag_material", 0.10)
db3.einstellung_setzen("zuschlag_fertigung", 0.15)
db3.con.execute("DELETE FROM einstellungen WHERE name='zuschlaege_stand'")    # Datei aus 0.6.4
db3.con.commit()
db3.schliessen()
db3 = Datenbank(tmp / "alt" / "rohrlaser.db")
assert db3.einstellung("zuschlag_material") == 0 and db3.einstellung("zuschlag_fertigung") == 0
db3.einstellung_setzen("zuschlag_material", 0.08)          # danach in den Einstellungen frei änderbar
db3.schliessen()
db3 = Datenbank(tmp / "alt" / "rohrlaser.db")
assert db3.einstellung("zuschlag_material") == 0.08 and db3.einstellung("zuschlag_fertigung") == 0
db3.schliessen()
ok("E6 Update: Zuschlag Material und Fertigung einmalig auf 0, danach in den Einstellungen änderbar")
print("OK: Einstellungen und Werte je Angebot getrennt")
