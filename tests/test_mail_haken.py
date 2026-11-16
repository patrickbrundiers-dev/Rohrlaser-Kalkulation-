"""Mail-Werte nur mit Häkchen übernehmen (KI-001, Patrick 13.11.2026 „Weiter“ auf den offenen Punkt
„Übernahme nur mit Häkchen“).

- Prüfdialog: je vorbelegtem Mail-Wert (Anfrage-Nr., Wunschtermin, Werkstoff) ein Häkchen mit Fundstelle im Tooltip
- „sicher“ ist angehakt, „prüfen“ nicht; ohne Häkchen gilt der Wert ohne Mail (Anfrage-Nr. leer, Werkstoff =
  Vorgabe, Lieferzeit = Einstellung)
- nur was wirklich vorbelegt ist bekommt ein Häkchen

Aufruf: python tests/test_mail_haken.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import mail_fundstellen as mf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
k = db.kontext()
f = Hauptfenster(db, tmp, stumm=True)
ws_mail, ws_vorgabe = "1.4301", "S235-10219"
assert ws_mail in k.werkstoffe and ws_vorgabe in k.werkstoffe

# ------------------------------------------------------------------ Prüfdialog: Häkchen und ihre Wirkung
mw = [dict(datei="x.step", artikel="T1", bauteil="T1", profilform="Rundrohr", profil_id_vorschlag=next(iter(k.profile)),
           laenge=500, pruefstatus="plausibel", schneidweg=100)]
werte = [dict(feld="anfrage_nr", titel="Anfrage-Nr.", wert="AN-4711", fundstelle="Anfrage-Nr. AN-4711",
              sicherheit=mf.SICHER, an=True),
         dict(feld="werkstoff", titel="Werkstoff", wert=ws_mail, fundstelle="Werkstoff: V2A", sicherheit=mf.PRUEFEN,
              an=False, vorgabe=ws_vorgabe)]
dlg = StepPruefDialog(None, [dict(mw[0])], k, ws_mail, 1, vorpruefung=lambda: ([], 0), referenz="AN-4711",
                      mail_werte=werte)
assert set(dlg.mail_haken) == {"anfrage_nr", "werkstoff"}
assert dlg.mail_haken["anfrage_nr"].isChecked() and not dlg.mail_haken["werkstoff"].isChecked()
assert "Fundstelle" in dlg.mail_haken["werkstoff"].toolTip() and "V2A" in dlg.mail_haken["werkstoff"].toolTip()
assert dlg.werkstoff == ws_vorgabe and dlg.zeilen[0].ws.currentText() == ws_vorgabe, dlg.werkstoff
ok("Werkstoff nur „prüfen“: ohne Häkchen, die Teile stehen auf der Vorgabe")
dlg.mail_haken["werkstoff"].setChecked(True)
assert dlg.werkstoff == ws_mail and dlg.zeilen[0].ws.currentText() == ws_mail
dlg.mail_haken["werkstoff"].setChecked(False)
assert dlg.zeilen[0].ws.currentText() == ws_vorgabe
ok("Häkchen Werkstoff an/aus: Werkstoff aus der Mail bzw. Vorgabe in allen Teilen")
assert dlg.referenz_text() == "AN-4711"
dlg.mail_haken["anfrage_nr"].setChecked(False)
assert dlg.referenz_text() is None and dlg.mail_abgewaehlt() == {"anfrage_nr", "werkstoff"}
dlg.mail_haken["anfrage_nr"].setChecked(True)
assert dlg.referenz_text() == "AN-4711" and dlg.mail_abgewaehlt() == {"werkstoff"}
ok("Anfrage-Nr. „sicher“: angehakt; ohne Häkchen ist das Feld leer")
assert StepPruefDialog(None, [dict(mw[0])], k, ws_mail, 1, vorpruefung=lambda: ([], 0)).mail_haken == {}
ok("ohne Mail keine Häkchen")

# ------------------------------------------------------------------ welche Werte ein Häkchen bekommen
a = db.angebot_neu(dict(kundennr=None, kundenreferenz="AN-4711", lieferzeit_art="Kalenderwoche", lieferzeit_wert="48"))
s = f.angebot_oeffnen(a)
fs = [dict(feld="anfrage_nr", titel="Anfrage-Nr.", wert="AN-4711", fundstelle="Anfrage-Nr. AN-4711",
           sicherheit=mf.SICHER),
      dict(feld="termin", titel="Wunschtermin", wert="Kalenderwoche 48", fundstelle="Lieferung KW 48",
           sicherheit=mf.SICHER),
      dict(feld="werkstoff", titel="Werkstoff", wert=ws_mail, fundstelle="Werkstoff 1.4301", sicherheit=mf.SICHER),
      dict(feld="staffel", titel="Staffelmengen", wert="10 / 50", fundstelle="10 / 50 Stück", sicherheit=mf.PRUEFEN)]
mw_ = s._mail_werte(fs, ws_mail, ws_vorgabe, "1.4301")
assert [w["feld"] for w in mw_] == ["anfrage_nr", "termin", "werkstoff"] and all(w["an"] for w in mw_), mw_
assert mw_[2]["vorgabe"] == ws_vorgabe and "48" in mw_[1]["wert"]
assert [w["feld"] for w in s._mail_werte(fs, None, None, None)] == ["anfrage_nr", "termin"]       # Werkstoff nicht vorbelegt
anders = [dict(fs[0], wert="AN-9999")]
assert s._mail_werte(anders, None, None, None) == []          # Anfrage-Nr. im Kopf ist eine andere: kein Häkchen
ok("Häkchen nur für vorbelegte Werte (Anfrage-Nr. im Kopf, Lieferzeit, Werkstoff); Staffel bleibt Hinweis")

# ------------------------------------------------------------------ ohne Häkchen nach OK: Kopf zurück
db.einstellung_setzen("lieferzeit_art", None)
s._mail_abgewaehlt({"anfrage_nr", "termin"}, mw_)
kopf = db.angebot(a)
assert not kopf.get("kundenreferenz") and not kopf.get("lieferzeit_art") and not kopf.get("lieferzeit_wert"), kopf
ok("nach OK ohne Häkchen: Anfrage-Nr. leer, Lieferzeit wie in den Einstellungen")
print("alle Prüfungen bestanden")
