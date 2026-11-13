"""Prüft Materialanfragen über Outlook (Patrick 13.11.2026, Konzept „Materialanfragen über Outlook“, alle a):
- V Vorlagen: „Standard“ aus den Einstellungen ohne Datensatz, eigene Vorlagen anlegen/kopieren/ändern/löschen auf
  der Seite E-Mail-Vorlagen, Anrede/Gruß/Signatur, Platzhalter, Kennung im Betreff, Liefertermin/Gültigkeit/Info.
- G Materialgruppen (vorbelegt, Schema 86), Lieferanten mit Materialgruppen (Mehrfachauswahl), Anrede und
  Standardvorlage; Vorschlag passender Lieferanten; Umbenennen einer Gruppe ändert die Lieferanten mit.
- D Dialog: Blech-/Zukaufteile mit Artikel-Nr. und Zeichnung, mehrere Lieferanten (je eine eigene Outlook-E-Mail,
  nur Display), PDF der Materialliste und Zeichnungen als Anhang, interne Bemerkung nicht in der E-Mail.
- H Verlauf je Angebot mit Kennung, Status, Datum/Uhrzeit, wer; Doppelversand-Schutz; ohne Outlook E-Mail-Dateien.
- S Reiter Materialanfragen: Filter, Status von Hand, Gesendete in Outlook prüfen (nur lesen), Erinnerung, Antwort
  eingelesen = Angebot erhalten, Bestellung = Abgeschlossen, Angebote der Kollegen nur ansehen.
- M Ältere Datei (Schema 85) bekommt Materialgruppen und die neuen Spalten.
Outlook wird nie wirklich aufgerufen (ausfuehren ersetzt PowerShell); das Programm sendet nie.

Aufruf: python tests/test_materialanfragen_outlook.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import email
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from email import policy
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import materialanfrage as ma, materialanfragen as mv, zukauf  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.mehrfach_auswahl import MehrfachDialog, mehrfach_waehlen  # noqa: E402


def ok(t):
    print("OK    ", t)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.einstellung_setzen("briefkopf_1", "Muster Laser GmbH")
db.einstellung_setzen("benutzer_kuerzel", "PB")

# ------------------------------------------------------------------ G Materialgruppen, Lieferanten
assert SCHEMA_VERSION >= 86
assert [z["name"] for z in db.zeilen("materialgruppen")] == list(zukauf.MATERIALGRUPPEN_VORGABE)
spalten = {r[1] for r in db.con.execute("PRAGMA table_info(zukauf_lieferanten)")}
assert {"materialgruppen", "anrede", "vorlage"} <= spalten
db.neu("zukauf_lieferanten", dict(name="Stahlhandel Nord", email="anfrage@stahl-nord.example",
                                  ansprechpartner="Herr Maier", anrede="Sehr geehrter Herr Maier",
                                  materialgruppen="Stahl"))
db.neu("zukauf_lieferanten", dict(name="Rohr Süd", email="vertrieb@rohr-sued.example", materialgruppen="Stahl; Edelstahl"))
db.neu("zukauf_lieferanten", dict(name="Blech Ost", email="info@blech-ost.example", materialgruppen="Blechteile"))
db.neu("zukauf_lieferanten", dict(name="Alu West", email="alu@west.example", materialgruppen="Aluminium"))
preis = next(z for z in db.zeilen("preise") if (z["profil_id"], z["werkstoff_id"]) == ("QR 40x40x3", "S235-10219"))
db.aendern("preise", preis["id"], "lieferant", "Stahlhandel Nord")
assert mv.gruppen_liste("Stahl; Edelstahl, Aluminium") == ["Stahl", "Edelstahl", "Aluminium"]
assert mv.gruppen_text(["Stahl", " Stahl", "", "Edelstahl"]) == "Stahl; Edelstahl"
k = db.kontext()
assert "Blechteile" in k.auswahl("materialgruppe") and k.auswahl("vorlagenart") == ["Materialanfrage", "Materialbestellung"]
rohr = dict(art="rohr", profil="QR 40x40x3", werkstoff="S235-10219", lieferant="Stahlhandel Nord")
blech = dict(art="zukauf", artikeltyp="Blech", lieferant=None)
assert mv.materialgruppe(rohr, k) == (k.werkstoffe["S235-10219"].get("kategorie") or "Stahl")
assert mv.materialgruppe(blech) == "Blechteile" and mv.materialgruppe(dict(art="zukauf", artikeltyp="Drehteil")) == \
    "Dreh-/Frästeile" and mv.materialgruppe(dict(art="zukauf")) == "Zukaufteile"
vorschlag = mv.passende_lieferanten([rohr, blech], db.zeilen("zukauf_lieferanten"), k)
assert vorschlag[0] == ("Stahlhandel Nord", "Lieferant des Materials"), vorschlag
assert [n for n, _ in vorschlag[1:]] == ["Blech Ost", "Rohr Süd"] or [n for n, _ in vorschlag[1:]] == ["Rohr Süd", "Blech Ost"]
assert "Alu West" not in [n for n, _ in vorschlag]
app = QApplication.instance() or QApplication([])
md = MehrfachDialog(None, "Materialgruppen", k.auswahl("materialgruppe"), "Stahl; Alt")
assert [md.liste.item(i).text() for i in range(md.liste.count())][-1] == "Alt"        # unbekannt bleibt stehen
md.liste.item(1).setCheckState(Qt.Checked)
assert md.wert() == "Stahl; Edelstahl; Alt"
assert mehrfach_waehlen(None, "x", ["A", "B"], "A", dialog=lambda d: 0) is None
gid = next(z["id"] for z in db.zeilen("materialgruppen") if z["name"] == "Edelstahl")
db.aendern("materialgruppen", gid, "name", "Edelstahl rostfrei")
assert next(z for z in db.zeilen("zukauf_lieferanten") if z["name"] == "Rohr Süd")["materialgruppen"] == \
    "Stahl; Edelstahl rostfrei"
db.aendern("materialgruppen", gid, "name", "Edelstahl")
ok("G Materialgruppen vorbelegt, Lieferanten mit Gruppen/Anrede, Vorschlag nach Material und Gruppe, Mehrfachauswahl, "
   "Umbenennen ändert Lieferanten mit")

# ------------------------------------------------------------------ V Vorlagen
fenster = Hauptfenster(db, stumm=True)
fenster.resize(1600, 1000)
einst = db.einstellungen()
std = mv.vorlagen([], einst)
assert len(std) == 1 and std[0]["name"] == "Standard" and std[0]["standard"] and not db.zeilen("mail_vorlagen")
kopf = dict(nummer="A-2026-0200", kunde="Kunde X", auftragsnr="AU-77")
b, t = mv.mail_bauen(std[0], kopf, [], einst, k, kennung_="MA A-2026-0200/1", liefertermin="KW 49", gueltig="31.12.2026",
                     info="Bitte mit Zeugnis")
assert b == "Materialanfrage zu Angebot A-2026-0200 (MA A-2026-0200/1)", b
assert "Gewünschter Liefertermin: KW 49\nBitte Angebot gültig bis: 31.12.2026\nBitte mit Zeugnis" in t, t
assert t == ma.anschreiben(kopf, [], einst, k).replace("\n\nBitte mit Preis", "\n\nGewünschter Liefertermin: KW 49\n"
                                                         "Bitte Angebot gültig bis: 31.12.2026\nBitte mit Zeugnis\n\n"
                                                         "Bitte mit Preis"), t
lz0 = dict(name="X", anrede="Sehr geehrter Herr Maier")       # Standard beginnt mit Anrede: ersetzen, nicht doppelt
_, t = mv.mail_bauen(std[0], kopf, [], einst, k, lieferant=lz0)
assert t.startswith("Sehr geehrter Herr Maier,\n\nbitte senden") and "Damen und Herren" not in t, t
seite = fenster.mail_vorlagen
assert seite.schluessel == "e_mail_vorlagen" and fenster.bereich.unter.indexOf(seite) >= 0
assert seite.vorlagen_liste.count() == 2 and "aus den Einstellungen" in seite.vorlagen_liste.item(0).text()
seite.neu()
seite.name.setText("Stahl Rohr")
seite.gruppe.setCurrentText("Stahl")
seite.betreff.setText("Materialanfrage – {projekt}")
assert seite.speichern()
v = next(z for z in db.zeilen("mail_vorlagen") if z["name"] == "Stahl Rohr")
assert v["materialgruppe"] == "Stahl" and v["anrede"] == "Sehr geehrte Damen und Herren" and v["pdf"] == "ja"
assert "{materialdaten}" in v["text"] and v["gruss"] == "Mit freundlichen Grüßen"
assert "Materialanfrage – P-4711 (MA A-2026-0100/1)" in seite.vorschau.toPlainText()
seite.kopieren()
assert seite.name.text() == "Stahl Rohr Kopie" and seite.speichern()
seite.signatur.setPlainText("Peter Beispiel\nEinkauf")
assert seite.speichern()
assert seite.loeschen(fragen=False) and "Stahl Rohr Kopie" not in [z["name"] for z in db.zeilen("mail_vorlagen")]
seite.neu()
seite.name.setText("Stahl Rohr")
assert not seite.speichern() and "gibt es schon" in fenster.statusBar().currentMessage()
seite.neu()
seite.text.setPlainText("")
assert not seite.speichern()
vl = mv.vorlage_waehlen(mv.vorlagen(db.zeilen("mail_vorlagen"), einst), None, ["Stahl"])
assert vl["name"] == "Stahl Rohr"
lz = next(z for z in db.zeilen("zukauf_lieferanten") if z["name"] == "Stahlhandel Nord")
b, t = mv.mail_bauen(vl, kopf, [], einst, k, lieferant=lz, kennung_="MA A-2026-0200/1")
assert b == "Materialanfrage – AU-77 (MA A-2026-0200/1)" and t.startswith("Sehr geehrter Herr Maier,\n\nbitte erstellen")
assert t.rstrip().endswith("Mit freundlichen Grüßen") and "{" not in t
ok("V Vorlagen: Standard aus Einstellungen, anlegen/kopieren/löschen, Name doppelt abgewiesen, Anrede des Lieferanten, "
   "Gruß, Projektnummer und Kennung im Betreff, Liefertermin/Gültigkeit/Info")

# ------------------------------------------------------------------ D Dialog mit Rohr, Blech, mehreren Lieferanten
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
a = db.angebot_neu(dict(kunde="Test", nummer="A-2026-0300"))
db.con.execute("UPDATE angebote SET auftragsnr='AU-300' WHERE id=?", (a,))      # wie beim Beauftragen
db.con.commit()
db.position_neu(a, dict(pos=10, artikel="T-100", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1450,
                        stueck=8, schneidweg=200, einstiche=2))
lasche = zukauf.frei_eintrag("Lasche", 2, artikelnr="L-17", lieferant="Blech Ost", kategorie="Blechteile")
db.position_neu(a, dict(pos=20, artikel="BG-1", art="Zukaufteil", stueck=5, zukauf=json.dumps([lasche])))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
ordner = fenster.angebot_ordner(s.kopf)
(ordner / "T-100 Zeichnung.pdf").write_bytes(b"%PDF-1.4 Zeichnung")
(ordner / "L-17.step").write_text("ISO-10303-21;")
(ordner / "A-2026-0300 Angebot.pdf").write_bytes(b"%PDF eigene Ausgabe")
aufrufe = []


def outlook_ok(befehl):
    daten = json.loads(Path(befehl[-1]).read_text(encoding="utf-8"))
    skript = Path(befehl[befehl.index("-File") + 1]).read_text(encoding="utf-8-sig")
    assert "Display" in skript and ".Send" not in skript and "Send(" not in skript
    for anh in daten["anhaenge"]:
        assert Path(anh).is_file(), anh
    aufrufe.append(daten)
    return subprocess.CompletedProcess(befehl, 0, "", "")


gesehen = {}


def bedienen(d):
    gesehen["zeilen"] = [z.get("art") for z in d.zeilen]
    gesehen["text_rohr"] = d.text.toPlainText()
    gesehen["vorlage"] = d.vorlage.currentText()
    gesehen["weitere"] = [d.weitere.item(i).text() for i in range(d.weitere.count())]
    gesehen["anhaenge"] = {d.anhaenge.item(i).text(): d.anhaenge.item(i).checkState() == Qt.Checked
                           for i in range(d.anhaenge.count())}
    gesehen["betreff"] = d.betreff.text()
    for r in range(len(d.zeilen)):            # Rohr und Lasche in einer Anfrage
        d.tabelle.item(r, 0).setCheckState(Qt.Checked)
    d.liefertermin.setText("KW 49")
    d.gueltig.setText("30.11.2026")
    d.info.setText("Bitte Zeugnis 3.1 beilegen.")
    d.intern.setText("Preis vom letzten Mal: 1,10 €/kg")
    for i in range(d.weitere.count()):
        if d.weitere.item(i).data(Qt.UserRole) == "Rohr Süd":
            d.weitere.item(i).setCheckState(Qt.Checked)
    gesehen["text"] = d.text.toPlainText()
    d.in_outlook()
    return d.result()


d = s.material_anfragen(dialog=bedienen, ausfuehren=outlook_ok)
assert gesehen["zeilen"] == ["rohr", "zukauf"], gesehen["zeilen"]
assert gesehen["vorlage"] == "Stahl Rohr", gesehen["vorlage"]         # Materialgruppe Stahl
assert gesehen["weitere"] == ["Blech Ost  – Lieferant des Materials", "Rohr Süd  – Materialgruppe Stahl", "Alu West"], \
    gesehen["weitere"]
assert gesehen["anhaenge"] == {"Materialliste als PDF": True, "T-100 Zeichnung.pdf": True, "L-17.step": False}, \
    gesehen["anhaenge"]
assert gesehen["betreff"] == "Materialanfrage – AU-300 (MA A-2026-0300/1)", gesehen["betreff"]
t = gesehen["text"]
assert t.startswith("Sehr geehrter Herr Maier,") and "Quadratrohr 40 x 40 x 3" in t and "für Artikel T-100" in t, t
assert "- 10 Stück Lasche (Art.-Nr. L-17)" in t and "für Artikel BG-1" in t, t
assert "Gewünschter Liefertermin: KW 49" in t and "Bitte Angebot gültig bis: 30.11.2026" in t and \
    "Bitte Zeugnis 3.1 beilegen." in t
assert "1,10" not in t                                               # interne Bemerkung nicht in der E-Mail
assert len(aufrufe) == 2 and [x["an"] for x in aufrufe] == ["anfrage@stahl-nord.example", "vertrieb@rohr-sued.example"]
assert aufrufe[0]["betreff"].endswith("(MA A-2026-0300/1)") and aufrufe[1]["betreff"].endswith("(MA A-2026-0300/2)")
assert aufrufe[1]["text"].startswith("Sehr geehrte Damen und Herren,"), aufrufe[1]["text"][:60]   # Anrede der Vorlage
for x in aufrufe:
    namen = [Path(p).name for p in x["anhaenge"]]
    assert "T-100 Zeichnung.pdf" in namen and "L-17.step" not in namen and any(n.endswith(".pdf") and "Materialanfrage"
                                                                                in n for n in namen), namen
pdf = next(Path(p) for p in aufrufe[0]["anhaenge"] if "Materialanfrage" in Path(p).name)
assert pdf.read_bytes().startswith(b"%PDF") and pdf.stat().st_size > 1500
assert d.ergebnis == "outlook" and "2 E-Mails in Outlook geöffnet" in fenster.statusBar().currentMessage()
ok("D Dialog: Rohr + Blechteil mit Artikel-Nr., Vorlage nach Materialgruppe, weitere Lieferanten je eigene E-Mail mit "
   "eigener Kennung und Anrede, PDF + vorbelegte Zeichnung angehängt, interne Bemerkung nicht in der E-Mail")

# ------------------------------------------------------------------ H Verlauf und Doppelversand
liste = mv.liste(db, a)
assert [e["kennung"] for e in liste] == ["MA A-2026-0300/1", "MA A-2026-0300/2"]
e1 = liste[0]
assert e1["status"] == mv.ENTWURF and e1["lieferant"] == "Stahlhandel Nord" and e1["wer"] == "PB"
assert e1["intern"] == "Preis vom letzten Mal: 1,10 €/kg" and e1["liefertermin"] == "KW 49" and e1["weg"] == "outlook"
assert len(e1["erstellt"]) == 19 and e1["verlauf"][0]["text"] == "in Outlook geöffnet"
assert len(e1["zeilen"]) == 2 and "Lasche" in e1["zeilen"][1] and len(e1["schluessel"]) == 2
assert any(n.endswith(".pdf") for n in e1["anhaenge"])
fragen = []


def nochmal(d):
    d.tabelle.item(0, 0).setCheckState(Qt.Checked)
    d.in_outlook()
    return d.result()


aufrufe.clear()
s.anfrage_rueckfrage = lambda titel, text: fragen.append(text) or False      # nein: nicht noch einmal
d = s.material_anfragen(dialog=nochmal, ausfuehren=outlook_ok)
assert fragen and "MA A-2026-0300/1" in fragen[0] and "PB" in fragen[0] and not aufrufe
assert "schon angefragt" in d.meldung and len(mv.liste(db, a)) == 2
s.anfrage_rueckfrage = lambda titel, text: True                              # ja: bewusst neu
d = s.material_anfragen(dialog=nochmal, ausfuehren=outlook_ok)
assert len(aufrufe) == 1 and mv.liste(db, a)[-1]["kennung"] == "MA A-2026-0300/3"
del s.anfrage_rueckfrage
mv.status_setzen(db, a, "MA A-2026-0300/3", mv.ABGESCHLOSSEN, "PB")


def fehlt(befehl):
    return subprocess.CompletedProcess(befehl, 1, "", "Die COM-Klasse Outlook.Application ist nicht registriert.")


geoeffnet = []
s.f.datei_oeffnen = geoeffnet.append


def ohne_outlook(d):
    d.lieferant.setCurrentText("Blech Ost")
    for i in range(d.weitere.count()):
        if d.weitere.item(i).data(Qt.UserRole) == "Alu West":
            d.weitere.item(i).setCheckState(Qt.Checked)
    d.in_outlook()
    return d.result()


d = s.material_anfragen(dialog=ohne_outlook, ausfuehren=fehlt)
assert d.ergebnis == "eml" and len(geoeffnet) == 2 and all(p.suffix == ".eml" for p in geoeffnet), geoeffnet
assert "Blech Ost" in geoeffnet[0].name and "Alu West" in geoeffnet[1].name
m = email.message_from_bytes(geoeffnet[0].read_bytes(), policy=policy.default)
assert m["To"] == "info@blech-ost.example" and m["X-Unsent"] == "1" and "Lasche" in m.get_body().get_content()
assert "MA A-2026-0300/4" in m["Subject"] and [e["weg"] for e in mv.liste(db, a)][-2:] == ["eml", "eml"]
ok("H Verlauf mit Kennung, Status Entwurf, Datum/Uhrzeit, wer, interne Bemerkung; Doppelversand: Rückfrage, nein = "
   "nichts geöffnet; ohne Outlook je Lieferant eine E-Mail-Datei")

# ------------------------------------------------------------------ S Reiter Materialanfragen
ms = fenster.materialanfragen
assert fenster.reiter.indexOf(ms) >= 0
ms.neu_laden()
assert ms.tabelle.rowCount() == 5 and ms.zaehler[mv.ENTWURF].text() == "Entwurf  4"
ms.status_waehlen(mv.ABGESCHLOSSEN)
assert ms.tabelle.rowCount() == 1
ms.status_waehlen("Alle")
ms.lieferant.setCurrentText("Rohr Süd")
assert ms.tabelle.rowCount() == 1 and ms.gewaehlt()["kennung"] == "MA A-2026-0300/2"
assert "Interne Bemerkung" in ms.detail.toPlainText() and "Verlauf" in ms.detail.toPlainText()
ms.lieferant.setCurrentText("Alle")
ms.suche.setText("gibt es nicht")              # nichts gefunden -> leer
assert ms.tabelle.rowCount() == 0
ms.suche.setText("")
lese = []


def gesendet(befehl):
    lese.append(Path(befehl[befehl.index("-File") + 1]).read_text(encoding="utf-8-sig"))
    Path(befehl[-2]).write_text(json.dumps([{"betreff": "Materialanfrage – AU-300 (MA A-2026-0300/1)",
                                             "zeit": "2026-11-13T12:00:05"},
                                            {"betreff": "AW: etwas anderes", "zeit": "2026-11-13T12:01:00"}]),
                                encoding="utf-8")
    return subprocess.CompletedProcess(befehl, 0, "", "")


ms.ausfuehren = gesendet
assert ms.gesendet_pruefen() == 1 and "GetDefaultFolder(5)" in lese[0] and "Send(" not in lese[0] and \
    ".Move" not in lese[0] and ".Delete" not in lese[0]
e1 = mv.liste(db, a)[0]
assert e1["status"] == mv.VERSENDET and e1["versendet"] == "2026-11-13T12:00:05"
assert ms.gesendet_pruefen() == 0                                      # nur einmal
ms.ausfuehren = fehlt
assert ms.gesendet_pruefen() is None and "Ist gesendet" in fenster.statusBar().currentMessage()
ms.suche.setText("MA A-2026-0300/2")
assert ms.gewaehlt()["kennung"] == "MA A-2026-0300/2"
assert ms.status_setzen(mv.VERSENDET) and mv.liste(db, a)[1]["verlauf"][-1]["text"] == "von Hand"
aufrufe.clear()
ms.ausfuehren, ms.rueckfrage = outlook_ok, (lambda *_: True)
assert ms.erneut_senden()
assert aufrufe[0]["betreff"].startswith("Erinnerung: ") and "MA A-2026-0300/2" in aufrufe[0]["betreff"]
assert "--- Unsere Anfrage ---" in aufrufe[0]["text"] and aufrufe[0]["an"] == "vertrieb@rohr-sued.example"
e2 = mv.liste(db, a)[1]
assert e2["erneut"] == 1 and e2["status"] == mv.ENTWURF
ms.rueckfrage = lambda *_: False
assert not ms.erneut_senden()
# Antwort des Lieferanten eingelesen -> Angebot erhalten (Kennung im Text)
from rohrlaser import lieferantenantwort  # noqa: E402
lieferantenantwort.einlesen(db, a, "Zu Ihrer Anfrage MA A-2026-0300/1: QR 40x40x3 S235 1,25 €/kg, Lieferzeit 5 Tage",
                            "anfrage@stahl-nord.example", [("QR 40x40x3", "S235-10219")], k.profile, 6000)
assert mv.liste(db, a)[0]["status"] == mv.ERHALTEN
assert mv.antwort_erhalten(db, a, "Unbekannt", "") is None
# Bestellung schließt die offenen Anfragen an diesen Lieferanten
assert mv.abschliessen(db, a, "Stahlhandel Nord", "PB") == 1 and mv.liste(db, a)[0]["status"] == mv.ABGESCHLOSSEN
# Angebot eines Kollegen: nur ansehen
db.con.execute("UPDATE angebote SET fremd='MK' WHERE id=?", (a,))
db.con.commit()
ms.suche.setText("")
ms.neu_laden()
assert ms.gewaehlt()["fremd"] == "MK" and not ms.erneut_knopf.isEnabled() and "nur ansehen" in ms.hinweis.text()
assert not ms.status_setzen(mv.VERSENDET)
assert mv.gesendet_abgleichen(db, [("x (MA A-2026-0300/4)", "2026-11-13T13:00:00")]) == 0
db.con.execute("UPDATE angebote SET fremd=NULL WHERE id=?", (a,))
db.con.commit()
assert fenster.materialanfragen_zeigen("A-2026-0300") is ms and ms.suche.text() == "A-2026-0300"
ok("S Reiter: Zähler, Filter Status/Lieferant/Suche, Gesendete prüfen (nur lesen) = Versendet, von Hand, Erinnerung "
   "mit Rückfrage, Antwort = Angebot erhalten, Bestellung = Abgeschlossen, Kollegen-Angebot nur ansehen")

# ------------------------------------------------------------------ K Kennung, Mehrbenutzer
assert mv.kennung("2026-012", 1) == "MA 2026-012/1"
assert [m.group(0) for m in mv.KENNUNG.finditer("AW: Anfrage (MA 2026-012/1) und MA A-2026-0300/12")] == \
    ["MA 2026-012/1", "MA A-2026-0300/12"]
b2 = db.angebot_neu(dict(kunde="Andere", nummer="A-2026-0301"))
assert mv.naechste_kennung(db, b2, "A-2026-0301") == "MA A-2026-0301/1"   # je Angebot, ohne gemeinsamen Zähler
ok("K Kennung je Angebot eindeutig (Angebotsnummer + laufende Nr.), im Betreff und in Antworten erkennbar")

# ------------------------------------------------------------------ M ältere Datei
db.schliessen()
alt = tmp / "alt.db"
con = sqlite3.connect(tmp / "rohrlaser.db")
con.execute("VACUUM INTO ?", (str(alt),))
con.close()
con = sqlite3.connect(alt)
con.execute("DROP TABLE materialgruppen")
con.execute("DROP TABLE mail_vorlagen")
for sp in ("materialgruppen", "anrede", "vorlage"):
    con.execute(f"ALTER TABLE zukauf_lieferanten DROP COLUMN {sp}")
con.execute("PRAGMA user_version=85")
con.commit()
con.close()
db2 = Datenbank(alt)
assert db2.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert len(db2.zeilen("materialgruppen")) == 7 and db2.zeilen("mail_vorlagen") == []
assert {"materialgruppen", "anrede", "vorlage"} <= {r[1] for r in db2.con.execute("PRAGMA table_info(zukauf_lieferanten)")}
assert len(mv.liste(db2, a)) == 5                       # Verlauf steht im Angebot
db2.schliessen()
ok("M Datei mit Schema 85: Materialgruppen vorbelegt, Vorlagen leer, neue Lieferanten-Spalten, Verlauf bleibt")
print("OK: Materialanfragen über Outlook")
