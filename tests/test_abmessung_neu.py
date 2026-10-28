"""Neue Abmessung aus der Eingabe anlegen (Patrick 28.10.2026): eine getippte Abmessung, die in den Stammdaten
(Profile) fehlt, bietet in der Schnellzeile, in der Profilspalte und in der Kopfzeile des Rohr-Editors (Neue
Position) ein Menü „Abmessung … neu anlegen …“; das Fenster ist aus der Eingabe vorbelegt, danach steht die
Abmessung in den Stammdaten und die Eingabe läuft mit ihr weiter. Kein Materialpreis wird geraten.

Aufruf: python tests/test_abmessung_neu.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import neue_position as np_, profil_neu  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Vorschlag aus dem Text
for text, soll in (("RE 70x30x3", ("Rechteckrohr", 70, 30, 3, "RE 70x30x3")),
                   ("rr 60,3 x 2,9", ("Rundrohr", 60.3, None, 2.9, "RR 60,3x2,9")),
                   ("QR 50x4", ("Quadratrohr", 50, None, 4, "QR 50x50x4")),
                   ("L 50x5", ("L-Profil", 50, 50, 5, "L 50x50x5")),
                   ("FL 40x5", ("Flachstahl", 40, None, 5, "FL 40x5")),
                   ("70x30x3", ("Rechteckrohr", 70, 30, 3, "RE 70x30x3")),
                   ("50x50x4", ("Quadratrohr", 50, None, 4, "QR 50x50x4")),
                   ("Ø 33,7x2", ("Rundrohr", 33.7, None, 2, "RR 33,7x2"))):
    v = profil_neu.vorschlag(text)
    assert v and (v["form"], v["a"], v["b"], v["wand"], v["profil_id"]) == soll, (text, v)
assert profil_neu.vorschlag("IPE 200")["form"] == "I-/H-Träger"
for text in ("unbekannt", "", "QR 50x40x3", "XY 10x2"):
    assert profil_neu.vorschlag(text) is None, text
ok("Vorschlag: Form, Maße und Profil-ID aus der getippten Abmessung")

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
f.show()
k = db.kontext()
assert "RE 70x30x3" not in k.profile and "RR 60,3x2,9" not in k.profile and "QR 55x55x4" not in k.profile
werkstoff = next(iter(k.werkstoffe))

# ------------------------------------------------------------------ Fenster vorbelegt, Fläche abfragen
d = profil_neu.ProfilNeuDialog(None, k.profile, None, k.profilformen, eingabe="re 70 x 30 x 3")
assert (d.form.currentText(), d.a.value(), d.b.value(), d.wand.value(), d.pid.text()) == \
    ("Rechteckrohr", 70, 30, 3, "RE 70x30x3") and d.fehler() == "", d.fehler()
assert d.windowTitle() == "Neue Abmessung anlegen" and "kg/m" in d.info.text()
d.form.setCurrentText("C-Profil")
assert "Fläche" in d.fehler(), d.fehler()      # Querschnitt nicht rechenbar: Fläche abfragen
d.flaeche.setValue(420)
assert d.fehler() == "" and d.werte()["flaeche_manuell"] == 420
ok("Fenster aus der Eingabe vorbelegt; Fläche wird abgefragt, wenn sie sich nicht rechnen lässt")

# ------------------------------------------------------------------ Schnellzeile
aid = db.angebot_neu(dict(kunde="Test"))
s = f.angebot_oeffnen(aid)
s.schnell.setText(f"RE 70x30x3 {werkstoff} 1250 4")
assert s.schnellzeile() == 0 and s.schnell.text().startswith("RE 70x30x3")
m = s.abm_menue
assert m is not None and m.isVisible(), "Menü unter der Schnellzeile"
texte = [a.text() for a in m.actions()]
assert texte[1] == "Abmessung RE 70x30x3 neu anlegen …" and "Nicht anlegen" in texte, texte
gesehen = {}


def bestaetigen(d):
    gesehen["vorbelegt"] = (d.form.currentText(), d.a.value(), d.b.value(), d.wand.value(), d.pid.text())
    return QDialog.Accepted


m.close()
assert s.abmessung_neu("RE 70x30x3", lambda pid: s.schnellzeile(), dialog=bestaetigen) == "RE 70x30x3"
assert gesehen["vorbelegt"] == ("Rechteckrohr", 70, 30, 3, "RE 70x30x3"), gesehen
zeile = next(z for z in db.zeilen("profile") if z["profil_id"] == "RE 70x30x3")
assert (zeile["form"], zeile["a"], zeile["b"], zeile["wand"]) == ("Rechteckrohr", 70, 30, 3)
pos = db.positionen(aid)
assert len(pos) == 1 and (pos[0]["profil_id"], pos[0]["laenge"], pos[0]["stueck"]) == ("RE 70x30x3", 1250, 4), pos
assert s.schnell.text() == "" and "Materialpreis fehlt" in f.verlauf.eintraege[0][1], f.verlauf.eintraege[0]
assert not pos[0].get("preis_m"), "kein geratener Meterpreis"
ok("Schnellzeile: Menü bietet die Abmessung an, angelegt in den Stammdaten, Position mit ihr angelegt")

# andere Profil-ID im Fenster: die Zeile läuft trotzdem mit ihr weiter; Abbrechen legt nichts an
s.schnell.setText("RR 60,3x2,9 800 2")
assert s.schnellzeile() == 0
assert s.abmessung_neu("RR 60,3x2,9", dialog=lambda d: QDialog.Rejected) is None
assert "RR 60,3x2,9" not in {z["profil_id"] for z in db.zeilen("profile")}


def andere_id(d):
    d.pid.setText("RR 60,3x2,9 EN10219")
    return QDialog.Accepted


assert s.abmessung_neu("RR 60,3x2,9", lambda pid: s.schnellzeile(), dialog=andere_id) == "RR 60,3x2,9 EN10219"
assert db.positionen(aid)[-1]["profil_id"] == "RR 60,3x2,9 EN10219" and s.schnell.text() == ""
s.schnell.setText("unbekannt 800 2")
s.abm_menue = None
s.schnellzeile()
assert s.abm_menue is None, "ohne Zahl im Profiltext kein Menü"
s.schnell.clear()
ok("Schnellzeile: eigene Profil-ID, Abbrechen legt nichts an, ohne Abmessung kein Menü")

# ------------------------------------------------------------------ Profilspalte im Angebot
modell = s.pos_modell
spalte = next(i for i, (art, x) in enumerate(modell.spalten) if art == "feld" and x.name == "profil_id")
s.abm_menue = None
assert modell.setData(modell.index(0, spalte), "QR 55x4")
app.processEvents()
assert s.abm_menue is not None and s.abm_menue.actions()[1].text() == "Abmessung QR 55x55x4 neu anlegen …"
s.abm_menue.close()
pid0 = db.positionen(aid)[0]["id"]
s.abmessung_neu("QR 55x4", lambda pid: (db.position_aendern(pid0, "profil_id", pid), s.neu_laden()),
                dialog=lambda d: QDialog.Accepted)
assert db.positionen(aid)[0]["profil_id"] == "QR 55x55x4" and "QR 55x55x4" in s.k.profile
ok("Profilspalte: unbekannte Abmessung bietet das Menü an der Zelle, Position bekommt die neue Profil-ID")

# ------------------------------------------------------------------ Kopfzeile im Rohr-Editor (Neue Position)
gesehen = {}


def rohr(d):
    d.k_profil.setCurrentText("RE 80x40x4")
    d._profil_fehlt()
    gesehen["menue"] = d.abm_menue is not None and d.abm_menue.actions()[1].text()
    d.abm_menue.close()
    gesehen["pid"] = d.profil_neu(eingabe="RE 80x40x4", dialog=lambda nd: (
        gesehen.setdefault("vorbelegt", (nd.form.currentText(), nd.pid.text())), QDialog.Accepted)[1])
    gesehen["gewaehlt"] = (d.k_profil.currentText(), d.profil.get("profil_id"))
    d.k_laenge.setValue(500)
    return QDialog.Accepted


assert s.position_neu(np_.ROHR, dialog=rohr) == np_.ROHR
assert gesehen["menue"] == "Abmessung RE 80x40x4 neu anlegen …", gesehen
assert gesehen["vorbelegt"] == ("Rechteckrohr", "RE 80x40x4") and gesehen["pid"] == "RE 80x40x4"
assert gesehen["gewaehlt"] == ("RE 80x40x4", "RE 80x40x4"), gesehen
assert db.positionen(aid)[-1]["profil_id"] == "RE 80x40x4"
ok("Rohr-Editor (Neue Position): getippte Abmessung bietet das Menü, Fenster vorbelegt, Profil gewählt")

# nur ansehen: kein Menü
s.kopf = dict(s.kopf, fremd="XY")
assert s.abmessung_neu_anbieten("RE 90x50x4", s.schnell) is None
print("Alle Tests bestanden.")
