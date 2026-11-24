"""Anfragen ohne STEP (Patrick 17.11.2026: Mails nur mit PDF oder ohne Anhang trotzdem als Anfrage bzw. Angebot,
Freigabe „Alle Empfehlungen“ = F1-F5 a): Kennzeichen und Akte (F1), Angebot ohne Positionen mit Kopfdaten (F2),
Dateien der Anfrage mit „Als Position übernehmen“ (F3), Rückfrage „STEP senden“ und nachgereichte STEP ins selbe
Angebot (F4), DXF zählt als Daten (F5). Nur erfundene Testmails.

Aufruf: python tests/test_anfragen_ohne_step.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import mail_testdateien  # noqa: E402
import pdf_testdateien as pt  # noqa: E402
from rohrlaser import anfrage_erkennung as ae  # noqa: E402
from rohrlaser import anfrage_ohne_step as aos  # noqa: E402
from rohrlaser import anfragen  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
eingang = tmp / "Eingang"
eingang.mkdir()
ALT = datetime.datetime.now() - datetime.timedelta(hours=2)
VON = ("Einkauf Krüger", "einkauf@krueger.example")
ZEICHNUNG = pt.pdf(tmp / "Halter-77.pdf", [("formular", ["Zeichnung Halter HA-77", "Werkstoff: 1.4301",
                                                         "Stückzahl: 12"])]).read_bytes()
DXF = (HIER / "dxf" / "rohr_bauteil1_patrick.dxf").read_bytes()
STEP = (HIER / "step" / "T01_RR42-4x2_L1250.step").read_bytes()


def schreiben(name, daten, wann=ALT):
    p = eingang / name
    p.write_bytes(daten)
    os.utime(p, (wann.timestamp(), wann.timestamp()))
    return p


def eml(betreff, text, anhaenge=(), wann=ALT):
    return mail_testdateien.eml(betreff, text, *VON, wann, list(anhaenge))


schreiben("1 nur pdf.eml", eml("Anfrage Halter HA-77", "Guten Tag,\nbitte um Angebot zu unserer Anfrage-Nr. "
                                "A-7701 gemäß Zeichnung.\nLiefertermin 18.12.2026\nGruß",
                                [("Halter-77.pdf", ZEICHNUNG)]), ALT - datetime.timedelta(minutes=50))
schreiben("2 ohne anhang.eml", eml("Preisanfrage Rohre", "Guten Tag,\nwas kosten 50 Stück QR 40x40x3, Länge 860 mm, "
                                   "S235?\nGruß"), ALT - datetime.timedelta(minutes=30))
schreiben("3 dxf.eml", eml("Anfrage Blech BL-5", "Bitte anbieten, 4 Stück.", [("BL-5.dxf", DXF)]),
          ALT - datetime.timedelta(minutes=15))
schreiben("4 mit step.eml", eml("Anfrage Gestell", "Bitte anbieten.", [("T01.step", STEP)]), ALT)

# ------------------------------------------------------------------ F1: Anfragen ohne STEP mit Kennzeichen
ohne, ohne_anf = [], []
gef = anfragen.suchen(eingang, ohne_step=ohne, ohne_anfragen=ohne_anf)
assert [a.name for a in gef] == ["4 mit step"], gef
assert {a.name: a.art() for a in ohne_anf} == {"1 nur pdf": "pdf", "2 ohne anhang": "leer", "3 dxf": "dxf"}, \
    [(a.name, a.art()) for a in ohne_anf]
assert "📄 nur PDF" in ohne_anf[0].text() and "✉ ohne Anhang" in ohne_anf[1].text() and "0 STEP" not in \
    ohne_anf[0].text()
assert gef[0].art() == "step" and gef[0].kennzeichen() == ""
ok("Anfrage-Ordner: Mails nur mit PDF, ohne Anhang und mit DXF sind Anfragen mit Kennzeichen (nur PDF, ohne Anhang, "
   "DXF ohne STEP)")

app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("benutzer_email", "patrick@laser.example")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.neu("kunden", dict(kundennr="K-7", name="Metallbau Krüger", ansprechpartner="Herr Probe",
                      email="einkauf@krueger.example"))
db.einstellung_setzen(anfragen.OHNE_STEP, "nein")
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
karte = fenster.start.anfragen
db.einstellung_setzen(anfragen.EINSTELLUNG, str(eingang))
karte.neu_laden(erzwingen=True)
assert karte.liste.count() == 1 and "Ohne STEP" in karte.hinweis.text(), karte.hinweis.text()
ok("Einstellung „anfragen_ohne_step“ = nein: wie bisher nur der Hinweis „Ohne STEP“")

db.einstellung_setzen(anfragen.OHNE_STEP, "ja")
karte.neu_laden(erzwingen=True)
texte = [karte.liste.item(i).text() for i in range(karte.liste.count())]
assert len(texte) == 4, texte
assert any("📄 nur PDF" in t for t in texte) and any("✉ ohne Anhang" in t for t in texte) \
    and any("DXF ohne STEP" in t for t in texte), texte
assert "Ohne STEP (nicht in der Liste" not in karte.hinweis.text(), karte.hinweis.text()
seite = fenster.anfragen_seite
seite.neu_laden()
akten = {a.betreff: a for a in seite.akten}
assert set(akten) == {"Anfrage Halter HA-77", "Preisanfrage Rohre", "Anfrage Blech BL-5", "Anfrage Gestell"}, akten
assert {b: a.daten_art() for b, a in akten.items()} == {"Anfrage Halter HA-77": "pdf", "Preisanfrage Rohre": "leer",
                                                       "Anfrage Blech BL-5": "dxf", "Anfrage Gestell": "step"}
seite.filter_daten.setCurrentIndex(seite.filter_daten.findData("ohne"))
assert seite.tabelle.rowCount() == 3
spalte = {seite.tabelle.item(r, 2).text(): seite.tabelle.item(r, 4).text() for r in range(3)}
assert spalte["Preisanfrage Rohre"] == "✉ ohne Anhang" and spalte["Anfrage Halter HA-77"].startswith("📄 nur PDF"), \
    spalte
seite.filter_daten.setCurrentIndex(seite.filter_daten.findData("step"))
assert seite.tabelle.rowCount() == 1 and seite.tabelle.item(0, 2).text() == "Anfrage Gestell"
seite.filter_daten.setCurrentIndex(0)
seite.waehlen(akten["Anfrage Halter HA-77"].nr)
assert "📄 nur PDF" in seite.kopf.text() and "ohne Positionen" in seite.kopf.text()
ok("Karte und Seite Anfragen: alle vier als Anfrage mit Akte, Kennzeichen in Liste und Kopf, Filter mit/ohne STEP")

# ------------------------------------------------------------------ F4: Rückfrage „STEP senden“ bei nur PDF
pdf_akte = akten["Anfrage Halter HA-77"]
fehlt = seite.erkennung(pdf_akte)["fehlt"]
assert "step" in fehlt and "zeichnung" not in fehlt, fehlt
assert "step" not in seite.erkennung(akten["Anfrage Blech BL-5"])["fehlt"]        # DXF zählt als Daten (F5)
assert "zeichnung" in seite.erkennung(akten["Preisanfrage Rohre"])["fehlt"]
assert "STEP-Dateien (3D-Modelle)" in ae.rueckfrage_text({}, pdf_akte, ["step"])
ok("Fehlt bei nur PDF: STEP-Datei (Rückfragetext „Bitte … STEP-Dateien“); DXF fehlt nichts, ohne Anhang: Zeichnung")

# ------------------------------------------------------------------ F2: Kalkulieren -> Angebot ohne Positionen
abgebrochen = []
karte.ohne_dialog = lambda d: abgebrochen.append(d.werte()) or QDialog.Rejected
seite.waehlen(pdf_akte.nr)
anzahl = len(db.angebote())
assert seite.kalkulieren() is None and len(db.angebote()) == anzahl
assert abgebrochen == [("K-7", "A-7701")], abgebrochen
ok("Prüfdialog „Anfrage ohne STEP“: Kunde und Anfrage-Nr. aus der Mail vorbelegt, Abbrechen legt nichts an")

karte.ohne_dialog = None
seite.neu_laden()
seite.waehlen(pdf_akte.nr)
a_seite = seite.kalkulieren(kundennr="K-7")
assert a_seite is not None and not db.positionen(a_seite.id)
kopf = db.angebot(a_seite.id)
assert kopf["kundennr"] == "K-7" and kopf["kundenreferenz"] == "A-7701", kopf
assert kopf["lieferzeit_art"] and "2026" in str(kopf["lieferzeit_wert"]), kopf
st = aos.stand(db, a_seite.id)
assert [d["name"] for d in st["dateien"]] == ["Halter-77.pdf"] and st["status"] == aos.OFFEN, st
ordner = Path(fenster.angebot_ordner(a_seite.kopf))
assert (ordner / "Anfrage" / "Halter-77.pdf").is_file() and any((ordner / "Anfrage").glob("*.eml"))
akte = seite.ablage().neu_lesen(pdf_akte)
assert akte.status == ak.BEARBEITUNG and kopf["nummer"] in akte.stand["angebote"]
assert ak.akten_zum_angebot(db, a_seite.id) == [akte.nr]
a_seite.anfrage_ohne_step_melden()
assert not a_seite.ohne_leiste.isHidden() and "Anfrage ohne STEP" in a_seite.ohne_text.text()
assert not a_seite.ohne_k_dateien.isHidden() and a_seite.ohne_k_einlesen.isHidden() \
    and not a_seite.ohne_k_step.isHidden()
ok("Kalkulieren ohne STEP: Angebot ohne Positionen mit Kunde, Anfrage-Nr. und Wunschtermin, PDF und Mail im "
   "Angebotsordner, Anfrage übernommen und verknüpft, gelbe Leiste")

# ------------------------------------------------------------------ F3: Dateien der Anfrage, Als Position übernehmen
aufrufe = []
orig_pdf = AngebotSeite.rohr_aus_pdf
AngebotSeite.rohr_aus_pdf = lambda self, pfade=None, **kw: aufrufe.append(("pdf", pfade)) or 1
d = a_seite.anfrage_dateien_zeigen(dialog=lambda d: None)
assert d.tabelle.rowCount() == 1 and d.k_position.isEnabled() and d.ansehen() is not None
assert d.uebernehmen() == 1 and aufrufe[-1][1][0].endswith("Halter-77.pdf")
AngebotSeite.rohr_aus_pdf = orig_pdf
assert aos.stand(db, a_seite.id)["dateien"][0]["uebernommen"]
assert d.tabelle.item(0, 2).text() == "als Position übernommen"
ok("Dateien der Anfrage: Ansehen, „Als Position übernehmen“ öffnet den Rohr-Editor aus der PDF-Zeichnung (erst auf "
   "Knopfdruck), Haken „übernommen“")

# ------------------------------------------------------------------ F4: STEP anfragen, nachgereicht, einlesen
mails = []


def outlook_ok(befehl):
    mails.append(json.loads(Path(befehl[-1]).read_text(encoding="utf-8")))
    return subprocess.CompletedProcess(befehl, 0, "", "")


seite.rueckfrage_ausfuehren = outlook_ok
fertig = a_seite.step_anfragen(ae.rueckfrage_text({}, akte, ["step"]))
assert fertig is not None and fertig.stand["rueckfrage"] and "STEP-Dateien" in mails[-1]["text"], mails
assert mails[-1]["an"] == "einkauf@krueger.example" and mails[-1]["betreff"] == "AW: Anfrage Halter HA-77"
antwort = tmp / "antwort.eml"
antwort.write_bytes(eml("AW: Anfrage Halter HA-77", "Anbei die STEP.", [("Halter-77.step", STEP)],
                        datetime.datetime.now()))
abl = seite.ablage()
abl.dateien_dazu(abl.neu_lesen(akte), [antwort], antwort=True)
nach = aos.nachgereicht(db, a_seite.id)
assert [p.name for p in nach] == ["Halter-77.step"], nach
assert "nachgereicht" in a_seite.anfrage_ohne_step_melden() and not a_seite.ohne_k_einlesen.isHidden()
eingelesen = []
orig_import = AngebotSeite.step_importieren
AngebotSeite.step_importieren = lambda self, dateien=None, *a, **kw: eingelesen.append((self.id, dateien)) or {}
seite.neu_laden()
seite.waehlen(akte.nr)
anzahl = len(db.angebote())
zurueck = seite.kalkulieren(kundennr="K-7")
AngebotSeite.step_importieren = orig_import
assert zurueck is a_seite and len(db.angebote()) == anzahl, (zurueck, a_seite)
assert eingelesen[-1][0] == a_seite.id and eingelesen[-1][1][0].endswith("Halter-77.step"), eingelesen
assert (ordner / "STEP" / "Halter-77.step").is_file()
assert aos.stand(db, a_seite.id)["status"] == aos.STEP and not aos.nachgereicht(db, a_seite.id)
assert a_seite.ohne_leiste.isHidden()
ok("STEP anfragen: Rückfrage als Outlook-Antwort; nachgereichte STEP (Antwort in der Akte): Leiste „STEP einlesen“, "
   "Kalkulieren liest sie in dasselbe Angebot und legt sie in den Angebotsordner")

# ------------------------------------------------------------------ Mail ohne Anhang, F5: DXF
leer = akten["Preisanfrage Rohre"]
seite.waehlen(leer.nr)
l_seite = seite.kalkulieren(kundennr="K-7")
assert l_seite is not None and aos.stand(db, l_seite.id)["dateien"] == []
assert "ohne Anhang" in l_seite.anfrage_ohne_step_melden() and l_seite.ohne_k_dateien.isHidden()
assert "Werkstoff laut Mail: S235" in " ".join(aos.stand(db, l_seite.id)["hinweis"]), aos.stand(db, l_seite.id)
assert l_seite.ohne_ausblenden() == "" and l_seite.ohne_leiste.isHidden()
ok("Mail ohne Anhang: Angebot ohne Positionen, Werkstoff der Mail als Hinweis, Leiste ausblendbar")

dxf_akte = akten["Anfrage Blech BL-5"]
seite.waehlen(dxf_akte.nr)
x_seite = seite.kalkulieren(kundennr="K-7")
assert x_seite is not None and [d["art"] for d in aos.stand(db, x_seite.id)["dateien"]] == ["dxf"]
assert not db.positionen(x_seite.id)            # ohne Rückfragen (stumm) öffnet der DXF-Import nicht von selbst
dxf_aufrufe = []
orig_dxf = AngebotSeite.blech_aus_dxf
AngebotSeite.blech_aus_dxf = lambda self, pfade=None, **kw: dxf_aufrufe.append(pfade) or 2
assert x_seite.anfrage_datei_uebernehmen("BL-5.dxf") == 2 and dxf_aufrufe[-1][0].endswith("BL-5.dxf")
AngebotSeite.blech_aus_dxf = orig_dxf
ok("DXF ohne STEP: Angebot mit der DXF in den Dateien der Anfrage, Übernahme über den DXF-Import")

# Anfrage mit STEP: wie bisher (STEP-Import), keine Leiste
step_akte = akten["Anfrage Gestell"]
seite.waehlen(step_akte.nr)
AngebotSeite.step_importieren = lambda self, dateien=None, *a, **kw: eingelesen.append((self.id, dateien)) or {}
s_seite = seite.kalkulieren(kundennr="K-7")
AngebotSeite.step_importieren = orig_import
assert s_seite is not None and aos.stand(db, s_seite.id) is None and s_seite.anfrage_ohne_step_melden() == ""
assert eingelesen[-1][0] == s_seite.id
ok("Anfrage mit STEP: unverändert über den STEP-Import, keine Leiste")
fenster.close()
db.schliessen()
print("Alle Tests bestanden.")
