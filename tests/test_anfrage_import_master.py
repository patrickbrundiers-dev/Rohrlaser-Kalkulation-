"""Outlook-E-Mail-Import intelligent erweitern (Patrick 25.11.2026, Master-Auftrag): Kundenbindung bis zum Auftrag,
Stückzahlen je Position aus Mail/PDF/Scan, Artikelnummer + Revision und STEP-Zuordnung (artikelnr.py).

Abnahmeliste des Auftrags:
  M1  Kunde automatisch erkannt -> bleibt für alle Schritte (Prüfdialog nimmt keinen anderen aus der Mail)
  M2  Kunde manuell gewählt -> bleibt verbindlich
  M3  Kunde mit mehreren Mailadressen -> richtiger Kunde erkannt
  M4  MSG mit Stückzahl -> Menge extrahiert (Menge:, 50x benötigt, pcs, Stückzahl, „Artikel 12345 – 20 Stück“)
  M5  PDF-Positionsliste -> Mengen je Position (Tabelle und Textzeilen), Fundstelle, Widerspruch Mail/PDF
  M6  Scan (OCR-Text) -> Mengen gefunden
  M7  STEP mit Grundnummer -> automatisch zugeordnet
  M8  STEP „_002“ / „-02“ / „_REV02“ -> Revision bleibt erhalten (getrennt, an der Position gespeichert)
  M9  mehrere STEP-Versionen -> Mehrdeutigkeit angezeigt, keine Menge geraten
  M10 mehrere Artikel -> Positionen bleiben getrennt; fehlende Menge = „nicht erkannt“
  M11 Kunde geändert -> Anfrage und Angebote bleiben konsistent, beauftragte nie automatisch
  M12 Prüfdialog: Spalten Revision und Erkennung Stückzahl (sicher/unsicher/Widerspruch/nicht erkannt) farbig

Aufruf: python tests/test_anfrage_import_master.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien as t  # noqa: E402
from rohrlaser import anfragen, artikelnr, formular, importprofil, mail, pdf_art, step_pruefung  # noqa: E402
from rohrlaser import anfragen_akten as akt  # noqa: E402
from rohrlaser import kunden_daten as kd  # noqa: E402
from rohrlaser import kundenbindung as kb  # noqa: E402
from rohrlaser import mail_zuordnung as mz  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
D = datetime.datetime(2026, 11, 25, 9, 0)
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
db.einstellung_setzen("briefkopf_1", "Laser Brundiers GmbH")
db.einstellung_setzen("eigene_domains", "laser.example")

WEISS = kd.anlegen(db, dict(kundennr="K-10001", name="Weiss und Soehne Stahlbau GmbH", ort="Hagen",
                            email="info@weiss-stahlbau.de"),
                   [dict(vorname="Jürgen", nachname="Weiß", email="j.weiss@weiss-stahlbau.de", haupt="ja"),
                    dict(vorname="Anna", nachname="Berg", email="a.berg@weiss-gruppe.de")])
KRUEGER = kd.anlegen(db, dict(kundennr="K-10002", name="Metallbau Krüger GmbH", email="h.krueger@krueger-metall.de",
                              ort="Lünen"))
EIGEN = {"laser.example"}
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
abl = seite.ablage()
ein = tmp / "ein"
ein.mkdir()


def akte_aus_mail(name, daten, schluessel):
    p = ein / name
    p.write_bytes(daten)
    k = akt.mail_kopf(dict(quelle="ordner", eingang=D), mail.lesen(p), kd.mit_kontakten(db), EIGEN,
                      "Laser Brundiers GmbH", wurzel=abl.wurzel)
    a, _ = abl.anlegen(k, [p], schluessel, jetzt=D)
    abl.zuordnung_protokollieren(a)
    seite.neu_laden()
    seite.waehlen(a.nr)
    return abl.neu_lesen(a)


# ------------------------------------------------------------------ M1 Kunde automatisch erkannt bleibt
a1 = akte_aus_mail("weiss.msg", t.msg("Anfrage Rohrteile", "Bitte 20 Stück anbieten.\n\nJürgen Weiß",
                                      "Jürgen Weiß", "j.weiss@weiss-stahlbau.de", D,
                                      anhaenge=[("123456_REV02.stp", b"ISO-10303-21;")]), "m1")
assert a1.kunde == WEISS, (a1.kunde, a1.zuordnung)
assert kb.gebunden(a1) and kb.quelle(a1) == "automatisch"
arbeit = akt.arbeitskopie(a1)
assert arbeit.kunde == WEISS and arbeit.kunde_fest, "automatisch erkannter Kunde nicht gebunden"
# die Mail/das Formular nennt einen anderen Kunden: der Kunde der Anfrage gilt, die Abweichung ist nur ein Hinweis
gelesen = [dict(text="Metallbau Krüger GmbH\nAnfrage-Nr. 4711\n123456 20 Stk", ocr=False, unsicher=set(),
                datei="anfrage.pdf")]
kunde, _, weitere = anfragen.werte(db, gelesen, [], WEISS, kunde_fest=True)
assert kunde == WEISS, kunde
frei, _, _ = anfragen.werte(db, gelesen, [], WEISS, kunde_fest=False)
assert frei == KRUEGER, "Gegenprobe: ohne Bindung erkennt das Formular Krüger"
ok("M1 automatisch erkannter Kunde ist gebunden: Prüfdialog übernimmt keinen anderen aus Mail/Formular")

# ------------------------------------------------------------------ M2 Kunde manuell bleibt verbindlich
a2 = akte_aus_mail("unbekannt.msg", t.msg("Rohre", "Hallo, 5 Stück bitte.", "Max", "max@irgendwo.example", D), "m2")
assert not a2.kunde and not kb.gebunden(a2)
a2 = seite.kunde_zuordnen(KRUEGER)
assert a2.kunde == KRUEGER and kb.gebunden(a2) and kb.quelle(a2) == "von Hand", (a2.kunde, kb.quelle(a2))
assert akt.arbeitskopie(a2).kunde_fest
k2, _, _ = anfragen.werte(db, [dict(text="Weiss und Soehne Stahlbau GmbH", ocr=False, unsicher=set())], [],
                          KRUEGER, kunde_fest=True)
assert k2 == KRUEGER
ok("M2 von Hand gewählter Kunde bleibt verbindlich (Quelle „von Hand“)")

# ------------------------------------------------------------------ M3 mehrere Mailadressen
for adresse in ("info@weiss-stahlbau.de", "j.weiss@weiss-stahlbau.de", "a.berg@weiss-gruppe.de"):
    p = ein / f"x_{adresse.split('@')[0].replace('.', '_')}.msg"
    p.write_bytes(t.msg("Anfrage", "Bitte anbieten.", "Kunde", adresse, D))
    z = mz.zuordnen(mail.lesen(p), kd.mit_kontakten(db), EIGEN, "Laser Brundiers GmbH")
    assert z["kundennr"] == WEISS or WEISS in [v["kundennr"] for v in z["vorschlaege"][:1]], (adresse, z)
ok("M3 Kunde mit mehreren Mailadressen (Firma, Ansprechpartner, andere Domain des Ansprechpartners) erkannt")

# ------------------------------------------------------------------ M4 Stückzahl aus der Mail
TEXT = """Guten Tag,
bitte bieten Sie an:
Artikel 12345 – 20 Stück
4711-020: Menge: 15
Teil 556677 50x benötigt
88990011 qty 12 pcs
Stückzahl 7 für 334455
"""
p = ein / "mengen.msg"
p.write_bytes(t.msg("Anfrage", TEXT, "Kunde", "info@weiss-stahlbau.de", D))
volltext = mail.lesen(p).volltext()
st = formular.stueckzahlen(volltext, ["12345.step", "4711-020.stp", "556677.step", "88990011.step", "334455.step"])
assert st == {"12345.step": (20, True), "4711-020.stp": (15, True), "556677.step": (50, True),
              "88990011.step": (12, True), "334455.step": (7, True)}, st
ok("M4 MSG: „– 20 Stück“, „Menge: 15“, „50x benötigt“, „12 pcs“, „Stückzahl 7“ sicher erkannt")

# ------------------------------------------------------------------ M5 PDF-Positionsliste, Fundstelle, Widerspruch
POS = ("Pos  Artikel-Nr.   Bezeichnung   Menge\n"
       "10   123456        Halter        20 Stk\n"
       "20   777777-02     Strebe        8 Stk\n"
       "30   999000        Blech         40 Stk\n")
messwerte = [dict(datei="123456_REV02.step", artikel="123456"), dict(datei="777777-02.step", artikel="777777"),
             dict(datei="999000_final.step", artikel="999000_final")]
fund = {}
gesamt = formular.stueck_aus([dict(text=POS, datei="Positionsliste.pdf"),
                              dict(text="Bitte 123456 25 Stk", mail=True, quelle="der Mail vom 25.11.")],
                             {n for m in messwerte for n in (m["datei"], m["artikel"])}, fund)
formular.stueck_setzen(messwerte, gesamt, fund)
assert [m["_stueck"] for m in messwerte] == [20, 8, 40], [m.get("_stueck") for m in messwerte]
assert messwerte[0]["_stueck_fundstelle"].startswith("Positionsliste.pdf: „10   123456"), messwerte[0]
assert "Mail vom 25.11.: 25" in messwerte[0]["_stueck_widerspruch"] and messwerte[0]["_stueck_formular"] is False
assert messwerte[2]["_stueck_formular"] is True and "_stueck_widerspruch" not in messwerte[2]
ok("M5 PDF-Positionsliste: Menge je Position, Fundstelle „Datei: Zeile“, Widerspruch Mail ↔ PDF gelb")

# ------------------------------------------------------------------ M6 Scan (OCR-Text)
OCR = "Pos Artikel Menge\n1 123456 20 Stk\n2 654321 5 Stk\n"
st = formular.stueckzahlen(OCR, ["123456_002.step", "654321-01.step"], ocr=True, unsicher={"5"})
assert st == {"123456_002.step": (20, True), "654321-01.step": (5, False)}, st
ok("M6 Scan: Mengen aus dem OCR-Text über die Grundnummer, unsicher gelesene Ziffer bleibt unsicher")

# ------------------------------------------------------------------ M7 STEP mit Grundnummer
z = artikelnr.zuordnen(["123456", "777777", "888888"],
                       ["123456_REV02.step", "777777_final.step", "Halter.step"])
assert z["123456"]["status"] == artikelnr.EINDEUTIG and z["123456"]["datei"] == "123456_REV02.step"
assert z["777777"]["status"] == artikelnr.EINDEUTIG and z["888888"]["status"] == artikelnr.KEINE
for n in ("123456_A", "123456_final", "123456_neu", "123456_Bearbeitet", "123456-02", "123456_002", "123456_REV02",
          "123456 Rev_A", "123456_V02"):
    assert artikelnr.grund(n + ".step") == "123456", n
assert artikelnr.grund("4711-020.step") == "4711-020", "kurze Nummer mit Bindestrich ist selbst die Artikelnummer"
assert artikelnr.grund("4711-02.step", ["4711"]) == "4711", "bekannte Nummer aus dem PDF: Rest ist Revision"
assert artikelnr.grund("MG-01 Stiel.stp") == "MG-01 Stiel"
ok("M7 Grundnummer: _A/_final/_neu/_Bearbeitet/-02/_002/_REV02/Rev_A/_V02 erkannt; 4711-020 bleibt; "
   "eindeutig/nicht zugeordnet")

# ------------------------------------------------------------------ M8 Revision bleibt erhalten
for n, rev in (("123456_002", "002"), ("123456-02", "02"), ("123456_REV02", "REV02"), ("123456 Rev_A", "Rev_A")):
    assert artikelnr.zerlegen(n).revision == rev, (n, artikelnr.zerlegen(n))
m = dict(datei="123456_002.step", artikel="123456_002", bauteil="")
b = importprofil.bestimmen(m, "Bauteilname")
assert b["artikel"] == "123456" and b["revision"] == "002", b
mw = [dict(datei="123456_002.step", artikel="123456_002", bauteil="", laenge=100, profilform="RR")]
importprofil.anwenden(mw)
assert mw[0]["artikel"] == "123456" and mw[0]["_revision"] == "002", mw[0]
mw[0].update(_stueck=20, _stueck_formular=True, _stueck_vorschlag=20, _stueck_fundstelle="a.pdf: „123456 20 Stk“")
e = json.loads(step_pruefung.speicherwert(mw[0]))["erkennung"]
assert e["revision"] == "002" and e["stueck_status"] == "sicher" and e["stueck_quelle"].startswith("a.pdf"), e
mw[0]["_stueck"] = 25
assert json.loads(step_pruefung.speicherwert(mw[0]))["erkennung"]["stueck_status"] == "von Hand"
ok("M8 Revision getrennt (002, 02, REV02, Rev_A), Artikel = Grundnummer, an der Position gespeichert (step_merkmale)")

# ------------------------------------------------------------------ M9 mehrere STEP-Versionen
z = artikelnr.zuordnen(["555555"], ["555555_REV01.step", "555555_REV02.step"])
assert z["555555"]["status"] == artikelnr.MEHRDEUTIG and z["555555"]["datei"] == "555555_REV02.step", z
mw = [dict(datei="555555_REV01.step", artikel="555555"), dict(datei="555555_REV02.step", artikel="555555-2")]
pdf_art.anwenden(mw, [dict(text="Pos Artikel Menge\n10 555555 30 Stk", datei="liste.pdf")])
# die Artikel-Nr. 555555 trifft genau den einen Messwert; der andere bleibt offen, beide zeigen die Revisionsfrage
assert mw[0]["_stueck"] == 30 and mw[0]["_stueck_formular"] is False, mw[0]
assert "bitte Revision prüfen" in mw[0]["_stueck_hinweis"], mw[0]
assert mw[1].get("_stueck_fehlt") and "bitte Revision prüfen" in mw[1]["_stueck_hinweis"], mw[1]
mw = [dict(datei="555555_REV01.step"), dict(datei="555555_REV02.step")]
fund = {}
formular.stueck_setzen(mw, formular.stueck_aus([dict(text="555555 30 Stk", datei="mail")],
                                               {m["datei"] for m in mw}, fund), fund)
assert all(m["_stueck_formular"] is False and "bitte Revision prüfen" in m["_stueck_hinweis"] for m in mw), mw
st = formular.stueckzahlen("123456-01 10 Stk\n123456-02 20 Stk", ["123456_REV02.step"])
assert st == {"123456_REV02.step": (20, True)}, st
assert formular.stueckzahlen("123456-01 10 Stk\n123456-03 20 Stk", ["123456_REV02.step"]) == {}
ok("M9 mehrere Versionen: mehrdeutig (neueste als Vorschlag), Menge nur unsicher mit „bitte Revision prüfen“; "
   "im Text passende Revision gewählt, sonst nichts geraten")

# ------------------------------------------------------------------ M10 mehrere Artikel getrennt, „nicht erkannt“
mw = [dict(datei="111111.step"), dict(datei="222222.step"), dict(datei="333333.step")]
pdf_art.anwenden(mw, [dict(text="111111 4 Stk\n222222 9 Stk\nAnlage: Zeichnung 333333", datei="anfrage.pdf")])
assert mw[0]["_stueck"] == 4 and mw[1]["_stueck"] == 9, mw
assert "_stueck" not in mw[2] and mw[2]["_stueck_fehlt"], mw[2]
assert json.loads(step_pruefung.speicherwert(mw[2]))["erkennung"]["stueck_status"] == "nicht erkannt"
ok("M10 mehrere Artikel bleiben getrennt; ohne Menge „nicht erkannt“ statt erfundener Zahl")

# ------------------------------------------------------------------ M11 Kundenwechsel konsistent
i_offen = db.angebot_neu(dict(kundennr=WEISS))
i_auftrag = db.angebot_neu(dict(kundennr=WEISS))
db.vorgang_setzen(i_auftrag, "Beauftragt")
db.auftrag_setzen(i_auftrag, "AB-77", None)
n_offen, n_auftrag = db.angebot(i_offen)["nummer"], db.angebot(i_auftrag)["nummer"]
a1 = abl.neu_lesen(a1)
a1 = abl.angebot_verknuepfen(a1, n_offen)
a1 = abl.angebot_verknuepfen(a1, n_auftrag)
db.zusatz_setzen(i_offen, "anfrage_akte", a1.nr)
db.zusatz_setzen(i_auftrag, "anfrage_akte", a1.nr)
w = kb.wechsel(db, a1, KRUEGER)
assert [x["nummer"] for x in w["offen"]] == [n_offen] and [x["nummer"] for x in w["beauftragt"]] == [n_auftrag], w
assert "Beauftragt" in kb.wechsel_text(w, KRUEGER)
seite.neu_laden()
seite.waehlen(a1.nr)
# ohne Bestätigung (ohne Bildschirm, nichts angegeben): Angebote bleiben
seite.kunde_zuordnen(KRUEGER)
assert db.angebot(i_offen)["kundennr"] == WEISS and db.angebot(i_auftrag)["kundennr"] == WEISS
# mit Bestätigung: offene folgen, beauftragte nicht
seite.kunde_zuordnen(WEISS)
seite.kunde_zuordnen(KRUEGER, angebote_mit=True, auftraege_mit=False)
assert db.angebot(i_offen)["kundennr"] == KRUEGER, db.angebot(i_offen)["kundennr"]
assert db.angebot(i_auftrag)["kundennr"] == WEISS, "beauftragtes Angebot automatisch umgestellt"
assert abl.neu_lesen(a1).kunde == KRUEGER
# Kundenwechsel im Angebot: die Anfrage folgt
s = fenster.angebot_oeffnen(i_offen)
s.kunde_waehlen(WEISS)
assert db.angebot(i_offen)["kundennr"] == WEISS and abl.neu_lesen(a1).kunde == WEISS, abl.neu_lesen(a1).kunde
v = [e for e in abl.neu_lesen(a1).verlauf if e.get("aktion") == akt.ZUORDNUNG]
assert v[-1].get("grund") == "im Angebot gewählt", v[-1]
ok("M11 Kundenwechsel: ohne Bestätigung bleiben Angebote; bestätigt folgen offene, beauftragte nie; "
   "Wechsel im Angebot schreibt die Anfrage nach")

# ------------------------------------------------------------------ M12 Prüfdialog-Spalten
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
import step_messen  # noqa: E402
from formen_baukasten import ohne, quader, schreibe  # noqa: E402

from rohrlaser import step, stil  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

STEP = tmp / "step"
STEP.mkdir()
rohr = ohne(quader(500, 40, 40), quader(500, 34, 34, 0, 3, 3))
schreibe({"123456_REV02": rohr, "777777": rohr, "888888": rohr}, STEP)
aus = STEP / "m.txt"
step_messen.main(["--ausgabe", str(aus)] + [str(STEP / f"{n}.step") for n in ("123456_REV02", "777777", "888888")])
mw = step.lies_messwerte(aus)
importprofil.anwenden(mw)
pdf_art.anwenden(mw, [dict(text="123456 20 Stk\n777777 8", datei="liste.pdf"),
                      dict(text="777777 10 Stk", mail=True, quelle="der Mail")])
d = StepPruefDialog(None, mw, db.kontext(), None, 1, zukauf_liste=[])
d.show()
app.processEvents()
assert not d.baum.isColumnHidden(d.SP_REVISION) and not d.baum.isColumnHidden(d.SP_ERKENNUNG)
zeilen = {Path(str(d.messwerte[z.liste[0]].get("datei"))).stem: z for z in d.zeilen}
r = zeilen["123456_REV02"].it
assert r.text(d.SP_REVISION) == "REV02" and r.text(d.SP_ERKENNUNG) == "sicher · liste.pdf", r.text(d.SP_ERKENNUNG)
assert r.background(d.SP_ERKENNUNG).color().name().upper() == stil.farbe(stil.GRUEN_FLAECHE).name().upper()
assert zeilen["777777"].it.text(d.SP_ERKENNUNG).startswith("Widerspruch"), zeilen["777777"].it.text(d.SP_ERKENNUNG)
assert "der Mail" in zeilen["777777"].it.toolTip(d.SP_ERKENNUNG) or "Mail" in zeilen["777777"].it.toolTip(d.SP_ERKENNUNG)
n = zeilen["888888"]
assert n.it.text(d.SP_ERKENNUNG) == "nicht erkannt" and n.it.text(d.SP_REVISION) == ""
n.sp.setValue(12)               # von Hand eingetragen: nicht mehr rot
assert n.it.text(d.SP_ERKENNUNG) == ""
d.close()
ok("M12 Prüfdialog: Spalte Revision (REV02), Erkennung „sicher · liste.pdf“ grün, Widerspruch gelb, "
   "„nicht erkannt“ rot bis zur Eingabe von Hand")

print("Alle Tests bestanden.")
