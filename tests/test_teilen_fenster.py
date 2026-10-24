"""Prüft die Oberfläche für mehrere Arbeitsplätze (teilen_fenster.py): Benutzer-Dialog, Knopf Abgleichen, Liste mit
Bearbeiter und Auswahl Meine/Alle, Angebote der Kollegen nur zum Ansehen (Hinweis, gesperrte Eingaben, kein Löschen,
kein Vorgang), Als Kopie übernehmen, Bearbeiter im Kopf und als Ansprechpartner im Angebots-PDF, Schreiben beim
Beenden.

Aufruf: python tests/test_teilen_fenster.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import nummern, pdf, teilen, teilen_fenster  # noqa: E402
from rohrlaser.angebot_fenster import ALLE, MEINE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()
POS = dict(pos=10, artikel="T-1", bezeichnung="Holm", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
           stueck=5, schneidweg=320, einstiche=2)

# ---------------------------------------------------------------- Benutzer-Dialog
pb = Datenbank(tmp / "pb" / "rohrlaser.db")
alt = pb.angebot_neu(dict(kunde="Altkunde"))           # vor dem Kürzel angelegt
f_pb = Hauptfenster(pb, tmp, stumm=True)
assert not f_pb.angebote.wer_filter.isVisibleTo(f_pb.angebote) and not f_pb.angebote.abgleich_knopf.isVisibleTo(f_pb.angebote)
d = teilen_fenster.BenutzerDialog(f_pb)
d.kuerzel.setText("")
assert "Kürzel" in d.pruefen()
d.name.setText("Patrick Brundiers")
d.kuerzel.setText("pb")
d.kuerzel.textEdited.emit("pb")
assert d.kuerzel.text() == "PB"
d.email.setText("pb@example.com")
d.telefon.setText("05250 123")
d.ordner.setText(str(tmp / "gibt-es-nicht"))
assert "nicht erreichbar" in d.pruefen()
d.ordner.setText(str(gemeinsam))
assert d.pruefen() is None
d._ok()
assert d.geaendert and teilen.aktiv(pb) and pb.einstellung("benutzer_kuerzel") == "PB"
assert pb.angebot(alt)["nummer"].endswith("-00001") and pb.angebot(alt)["bearbeiter"] == "PB"
ok("Benutzer-Dialog: Kürzel groß und Pflicht, Ordner muss erreichbar sein, speichert Name, E-Mail, Telefon, Ordner; "
   "ältere eigene Angebote bekommen den Bearbeiter")

a1 = pb.angebot_neu(dict(kunde="Kunde A"))
pb.position_neu(a1, POS)
f_pb.angebote.neu_laden()
assert f_pb.angebote.abgleich_knopf.isVisibleTo(f_pb.angebote)
seite = f_pb.angebot_oeffnen(a1)
assert seite.kopf_bereich.bearbeiter.text() == "PB – Patrick Brundiers"
assert not seite.fremd_leiste.isVisibleTo(seite)
ang = seite.angebot_daten()
assert ang["ansprechpartner"]["name"] == "Patrick Brundiers" and ang["ansprechpartner"]["telefon"] == "05250 123"
pdf.angebot_pdf(tmp / "a.pdf", seite.kopf, ang, seite.einst)
assert (tmp / "a.pdf").stat().st_size > 0
if shutil.which("pdftotext"):                         # Text prüfen, wo pdftotext installiert ist (nicht in der CI)
    text = subprocess.run(["pdftotext", "-layout", str(tmp / "a.pdf"), "-"], capture_output=True, text=True).stdout
    assert "Ansprechpartner" in text and "Patrick Brundiers" in text and "pb@example.com" in text, text[:800]
ok("eigenes Angebot: Bearbeiter im Kopf (PB – Name), Ansprechpartner mit Telefon und E-Mail für das Angebots-PDF")
assert teilen_fenster.abgleichen(f_pb) is not None
assert (gemeinsam / "Rohrlaser_PB.sqlite").exists()
ok("Knopf Abgleichen legt die eigene Datei in den gemeinsamen Ordner")

# ---------------------------------------------------------------- Kollege sieht das Angebot
mk = Datenbank(tmp / "mk" / "rohrlaser.db")
for n, w in (("benutzer_name", "Martin K"), ("benutzer_kuerzel", "MK"), ("teilen_ordner", str(gemeinsam))):
    mk.einstellung_setzen(n, w)
f_mk = Hauptfenster(mk, tmp, stumm=True)
assert teilen_fenster.abgleichen(f_mk) is None, "erster Abgleich braucht die Rückfrage (stumm: abgebrochen)"
assert not (gemeinsam / "Rohrlaser_MK.sqlite").exists()
teilen.lesen(mk, teilen.UEBERNEHMEN)
b = teilen_fenster.abgleichen(f_mk)
assert b is not None and (gemeinsam / "Rohrlaser_MK.sqlite").exists()
au = f_mk.angebote
eintraege = [au.wer_filter.itemText(i) for i in range(au.wer_filter.count())]
assert eintraege == [MEINE, ALLE, "PB"] and au.wer_filter.currentText() == ALLE, eintraege
spalte = [s[0] for s in au.SPALTEN].index("Bearbeiter")
zeile = next(r for r in range(au.modell.rowCount()) if au.modell.zeilen[r]["nummer"] == pb.angebot(a1)["nummer"])
fid = au.modell.zeilen[zeile]["id"]
idx = au.modell.index(zeile, spalte)
assert au.modell.data(idx) == "PB" and au.modell.data(idx, Qt.FontRole).italic()
au.wer_filter.setCurrentText(MEINE)
assert au.modell.rowCount() == 0
au.wer_filter.setCurrentText("PB")
assert au.modell.rowCount() == 2, "auch das ältere Angebot"
ok("Liste: Spalte Bearbeiter, Auswahl Meine Angebote / Alle Mitarbeiter / PB, Angebote der Kollegen kursiv und grau")

au.ansicht.setCurrentIndex(au.filter.mapFromSource(au.modell.index(
    next(r for r in range(au.modell.rowCount()) if au.modell.zeilen[r]["id"] == fid), 0)))
assert au.vorgang_setzen("Beauftragt") is False and mk.angebot(fid).get("vorgang") is None
au.loeschen()
assert mk.angebot(fid) is not None
ok("Angebot eines Kollegen: Vorgang setzen und Löschen gesperrt (Hinweis in der Statuszeile)")

fs = f_mk.angebot_oeffnen(fid)
assert fs.fremd() == "PB" and fs.fremd_leiste.isVisibleTo(fs) and "Patrick Brundiers" in fs.fremd_text.text()
assert not fs.kopf_bereich.isEnabled() and not fs.leiste.links.isEnabled() and not fs.acceptDrops()
assert fs.titel().endswith("(PB)")
spalte_feld = next(i for i, (art, _) in enumerate(fs.pos_modell.spalten) if art == "feld")
assert not fs.pos_modell.flags(fs.pos_modell.index(0, spalte_feld)) & Qt.ItemIsEditable
assert fs.kopf_bereich.bearbeiter.text() == "PB – Patrick Brundiers"
assert fs.angebot_daten()["ansprechpartner"]["name"] == "Patrick Brundiers"
ok("geöffnetes Angebot des Kollegen: gelber Hinweis, Kopf, Knöpfe und Positionen gesperrt, Titel mit Kürzel")
neu = fs.als_kopie()
k = mk.angebot(neu)
assert nummern.zaehler(k["nummer"]) > nummern.zaehler(pb.angebot(a1)["nummer"]) and k["bearbeiter"] == "MK" and not k.get("fremd")
ks = f_mk.offen[neu]
assert not ks.fremd() and ks.kopf_bereich.isEnabled()
ok("Als Kopie übernehmen: eigenes Angebot mit neuer Nummer aus dem gemeinsamen Nummernkreis, bearbeitbar")

# ---------------------------------------------------------------- Änderung beim Bearbeiter, offenes Fenster lädt neu
pb.angebot_aendern(a1, "kunde", "Kunde A geändert")
teilen.schreiben(pb)
teilen_fenster.abgleichen(f_mk)
assert fs.kopf["kunde"] == "Kunde A geändert"
pb.angebot_loeschen(a1)
teilen.schreiben(pb)
teilen_fenster.abgleichen(f_mk)
assert fid not in f_mk.offen and mk.angebot(fid) is None
ok("Abgleich: offenes Angebot des Kollegen zeigt den neuen Stand, gelöschtes wird geschlossen")

# ---------------------------------------------------------------- Beenden schreibt die eigene Datei
f_mk.stumm = False
vorher = teilen.info_lesen(gemeinsam / "Rohrlaser_MK.sqlite")["angebote"]
mk.angebot_neu(dict(kunde="noch eins"))
from rohrlaser import fenster as fenster_modul  # noqa: E402
fenster_modul.QMessageBox.warning = staticmethod(lambda *a, **k: fenster_modul.QMessageBox.Yes)
f_mk.db.sicherungen = lambda zusatz=None: ([], None)
f_mk.close()
assert teilen.info_lesen(gemeinsam / "Rohrlaser_MK.sqlite")["angebote"] == vorher + 1
ok("Beenden: eigene Angebote in den gemeinsamen Ordner gelegt")
print("OK: Oberfläche mehrere Arbeitsplätze")
