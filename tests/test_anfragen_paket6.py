"""Anfragenverwaltung, Paket 6 (Patrick 14.11.2026, „Alle vier“): erkannte Werte mit Fundstelle und was fehlt,
Rückfrage an den Kunden (Outlook-Antwort, nie gesendet; Ampel ruht bis zur Antwort), Wiederholteile (gleiche STEP,
bekannte Artikelnummer) mit „Aus letztem Angebot“, Kacheln der Startseite mit Filter. Nur erfundene Testmails.

Aufruf: python tests/test_anfragen_paket6.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien  # noqa: E402
from rohrlaser import anfrage_erkennung as ae  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
TEXT_VOLL = ("Guten Tag,\nbitte um Angebot zu unserer Anfrage-Nr. A-4711.\nWerkstoff: 1.4301\n"
             "Liefertermin 05.12.2026\nStaffel 10 / 50 / 100 Stück\nGruß")
TEXT_LEER = "Guten Tag,\nbitte anbieten.\nGruß"


def mail(name, betreff, adresse, wann, text, anhaenge=()):
    p = tmp / name
    p.write_bytes(mail_testdateien.eml(betreff, text, "Test Kunde", adresse, wann, list(anhaenge)))
    return p


# ------------------------------------------------------------------ Erkennung ohne Oberfläche
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.neu("kunden", dict(kundennr="K-6", name="Gestellbau Sechs", ansprechpartner="Frau Probe",
                      email="einkauf@sechs.example"))
werte = ae.erkannt(db, None, TEXT_VOLL)
felder = {w["feld"]: w for w in werte}
assert set(felder) == {"anfrage_nr", "termin", "werkstoff", "staffel"}, felder
assert felder["anfrage_nr"]["wert"] == "A-4711" and felder["werkstoff"]["sicherheit"] == "sicher"
assert all(w["fundstelle"] for w in werte)
assert ae.fehlt(werte, None, TEXT_VOLL) == []
leer = ae.erkannt(db, None, TEXT_LEER)
assert ae.fehlt(leer, None, TEXT_LEER) == ["werkstoff", "termin", "menge"]
assert ae.fehlt_text(["werkstoff"]) == ["Werkstoff nicht genannt"]
unsicher = ae.erkannt(db, None, "Werkstoff: S235JR, 20 Stück")
assert ae.fehlt(unsicher, None, "Werkstoff: S235JR, 20 Stück")[0] == "werkstoff_unsicher"
t = ae.rueckfrage_text(dict(ansprechpartner="Frau Probe"), None, ["werkstoff", "termin"], "Laser GmbH")
assert t.startswith("Sehr geehrte Frau Probe,") and "Welcher Werkstoff" in t and "Wunschtermin" in t
ok("Erkennung: Anfrage-Nr., Wunschtermin, Werkstoff, Staffel mit Fundstelle; fehlende Angaben und Rückfragetext")

# ------------------------------------------------------------------ Rückfrage in der Ablage: Ampel ruht
abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")
ein = datetime.datetime(2026, 11, 9, 9, 0)              # Montag
m = mail("r.eml", "Anfrage Halter", "einkauf@sechs.example", ein, TEXT_LEER, [("halter.step", b"ISO-10303-21; H")])
r, _ = abl.anlegen(dict(quelle="ordner", betreff="Anfrage Halter", absender="einkauf@sechs.example", eingang=ein,
                        kundennr="K-6"), [m], "r1")
jetzt = datetime.datetime(2026, 11, 13, 10, 0)
assert ak.ampel(r, 2, jetzt=jetzt)[0] == "rot"
r = abl.rueckfrage(r, "Welcher Werkstoff?", jetzt=ein + datetime.timedelta(hours=2))
assert r.stand["rueckfrage"] and ak.ampel(r, 2, jetzt=jetzt) == (None, None, "wartet auf Kunde")
assert any("Rückfrage an den Kunden: Welcher Werkstoff?" in ak.verlauf_text(e) for e in r.verlauf)
antwort = mail("antwort.eml", "AW: Anfrage Halter", "einkauf@sechs.example", jetzt, "Werkstoff 1.4301")
abl.dateien_dazu(r, [antwort], jetzt=datetime.datetime(2026, 11, 12, 8, 0), antwort=True)
r = abl.neu_lesen(r)
assert not r.stand["rueckfrage"] and r.stand["antwort_am"]
stufe, faellig, _t = ak.ampel(r, 2, jetzt=jetzt)
assert stufe == "grün" and faellig == datetime.date(2026, 11, 16), (stufe, faellig)    # Frist ab der Antwort
r = abl.rueckfrage(r, "Und die Stückzahl?", jetzt=datetime.datetime(2026, 11, 12, 9, 0))
r = abl.antwort_erhalten(r, jetzt=datetime.datetime(2026, 11, 12, 10, 0))
assert not r.stand["rueckfrage"] and ak.ampel(r, 2, jetzt=jetzt)[0] == "grün"
try:
    abl.antwort_erhalten(r)
    raise AssertionError("Antwort ohne Rückfrage")
except ak.AblageFehler:
    pass
assert r.pfad.exists() and all(d["pfad"].exists() for d in r.dateien())
ok("Rückfrage: wartet auf Kunde (keine Ampel), nach der Antwort per Mail oder von Hand läuft die Frist neu; nichts "
   "gelöscht")

# ------------------------------------------------------------------ Seite
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
seite.vormess_auftrag = dict(messen=lambda job, anf: [dict(fehler="nicht lesbar")])
abl2 = seite.ablage()
heute = datetime.datetime.now().replace(microsecond=0)
STEP = ("rahmen.step", b"ISO-10303-21; Rahmen Sechs")
m1 = mail("alt.eml", "Anfrage Rahmen", "einkauf@sechs.example", heute - datetime.timedelta(days=30), TEXT_VOLL, [STEP])
alt, _ = abl2.anlegen(dict(quelle="outlook", betreff="Anfrage Rahmen", absender="einkauf@sechs.example",
                           kundennr="K-6", eingang=heute - datetime.timedelta(days=30)), [m1], "alt")
frueher = db.angebot_neu(dict(kundennr="K-6"))
db.position_neu(frueher, dict(pos=10, artikel="RS-100", bezeichnung="Rahmen", profil_id="QR 40x40x3",
                              werkstoff_id="1.4301", laenge=1200, stueck=10, schneidweg=200, einstiche=2))
nummer_alt = db.angebot(frueher)["nummer"]
abl2.angebot_verknuepfen(abl2.uebernehmen(alt), nummer_alt)
abl2.erledigen(abl2.neu_lesen(alt))
m2 = mail("neu.eml", "Anfrage Rahmen nochmal", "einkauf@sechs.example", heute - datetime.timedelta(days=9),
          TEXT_LEER, [STEP])
neu, _ = abl2.anlegen(dict(quelle="outlook", betreff="Anfrage Rahmen nochmal", absender="einkauf@sechs.example",
                           kundennr="K-6", eingang=heute - datetime.timedelta(days=9)), [m2], "neu")
m3 = mail("art.eml", "Bestellung RS-100", "einkauf@sechs.example", heute, "Bitte 25 Stück RS-100 anbieten. "
          "Werkstoff 1.4301, Liefertermin 05.12.2026")
art, _ = abl2.anlegen(dict(quelle="outlook", betreff="Bestellung RS-100", absender="einkauf@sechs.example",
                           kundennr="K-6", eingang=heute), [m3], "art")
seite.neu_laden()
seite._vormessung_pruefen(warten=True)
seite.waehlen(neu.nr)
text = seite.inhalt.toPlainText()
assert "Erkannt" in text and "Fehlt: Werkstoff nicht genannt, Wunschtermin nicht genannt, Stückzahl" in text, text
assert "Wiederholteile" in text and nummer_alt in text and f"wie Anfrage {alt.nr}" in text, text
assert not seite.k_rueckfrage.isHidden() and not seite.k_letztes.isHidden()
ok("Seite: Erkannt mit Fundstelle, Fehlt, Wiederholteil über dieselbe STEP-Datei")

# Kacheln der Startseite
start = fenster.start
assert not start.anfragen_kacheln.isHidden()
assert start.anfragen_kacheln.kacheln["ueberfaellig"].wert.text() == "1"
assert seite.kachel_zahlen() == dict(ueberfaellig=1, heute=0, meine=0), seite.kachel_zahlen()
start._anfragen_kachel("ueberfaellig")
assert fenster.reiter.currentWidget() is seite and seite.ampel_filter == "ueberfaellig"
assert seite.tabelle.rowCount() == 1 and seite.tabelle.item(0, 0).text() == neu.nr
assert not seite.filter_zeile.isHidden() and "überfällige" in seite.filter_hinweis.text()
seite.filter_setzen("")
assert seite.filter_zeile.isHidden() and seite.ordner == "neu" and seite.tabelle.rowCount() == 2
ok("Kacheln: überfällig/heute fällig/meine auf der Startseite, Klick öffnet Anfragen mit Filter, Filter aufheben")

# Rückfrage: Outlook-Antwort (nie gesendet), wartet auf Kunde
aufrufe = []


def outlook_ok(befehl):
    aufrufe.append(json.loads(Path(befehl[-1]).read_text(encoding="utf-8")))
    return subprocess.CompletedProcess(befehl, 0, "", "")


seite.rueckfrage_ausfuehren = outlook_ok
seite.waehlen(neu.nr)
fertig = seite.rueckfrage(ae.rueckfrage_text(dict(ansprechpartner="Frau Probe"), seite.akte(),
                                             seite.erkennung(seite.akte())["fehlt"]))
assert fertig is not None and fertig.stand["rueckfrage"]
d = aufrufe[-1]
assert d["an"] == "einkauf@sechs.example" and d["betreff"] == "AW: Anfrage Rahmen nochmal", d
assert "Sehr geehrte Frau Probe" in d["text"] and "Welcher Werkstoff" in d["text"]
assert seite.ampeln[neu.nr] == (None, None, "wartet auf Kunde")
assert "wartet auf Kunde" in seite.kopf.text() and "Antwort erhalten" in seite.kopf.text()
assert seite.kachel_zahlen()["ueberfaellig"] == 0
assert seite.antwort_erhalten() is not None and not abl2.neu_lesen(neu).stand["rueckfrage"]
ok("Rückfrage …: Antwort in Outlook mit den fehlenden Angaben, Anfrage wartet auf den Kunden, Antwort erhalten")

# Wiederholteil über die Artikelnummer: Aus letztem Angebot
seite.waehlen(art.nr)
erk = seite.erkennung(seite.akte())
assert [w["art"] for w in erk["wiederholt"]] == ["artikel"] and erk["wiederholt"][0]["menge"] == 25, erk
assert "Artikel RS-100" in seite.inhalt.toPlainText()
i = seite.aus_letztem_angebot()
assert i is not None
pos = db.positionen(i)
assert len(pos) == 1 and pos[0]["artikel"] == "RS-100" and pos[0]["stueck"] == 25, pos
a2 = abl2.neu_lesen(art)
assert a2.status == ak.BEARBEITUNG and db.angebot(i)["nummer"] in a2.stand["angebote"]
assert ak.akten_zum_angebot(db, i) == [art.nr]
ok("Aus letztem Angebot: Positionen kopiert, Stückzahl aus der Anfrage, Anfrage übernommen und verknüpft")

# Gleiche STEP: ganzes letztes Angebot
seite.waehlen(neu.nr)
j = seite.aus_letztem_angebot()
assert j is not None and len(db.positionen(j)) == 1 and ak.akten_zum_angebot(db, j) == [neu.nr]
ok("Aus letztem Angebot bei gleicher STEP-Datei: alle Positionen des früheren Angebots")
fenster.close()
db.schliessen()
print("Alle Tests bestanden.")
