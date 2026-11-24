"""Materialpreise aus ERP-CSV (Plan 30.10.2026, Freigabe „Alle Empfehlungen“):
- E1 Lesen: Kodierung, Titelzeile, Spaltenköpfe, deutsche Zahlen und Datumsformate, Gutschrift/Summe übersprungen.
- E2 Zerlegen: Profil, Werkstoff, Oberfläche aus der EK-Bezeichnung mit Ampel.
- E3 Fenster: Prüfliste (Werkstoff wählen, Profil anlegen, überspringen, gemerkt), Übersicht (gewichteter Ø über
  12 Monate, Ausreißer, Verlauf mit Haken je Kauf), Aufpreis-Hinweis, zweiter Import ohne Doppelte; Stammdaten-Preise
  bleiben unverändert.
- E4 Angebot (Patrick 30.10.2026 17:39): Kauf zum Bedarf wählen (neuester mit 0,5- bis 2-facher Menge, sonst
  neuester, nur 12 Monate), nach dem Optimieren als Preis der Abmessung mit Bemerkung, Preis von Hand geht vor, ohne
  Kauf wie bisher, festgeschrieben und Funktion aus ohne neuen Vorschlag.
Alle Preise sind Testwerte; die Kaufdaten liegen relativ zu heute, damit der 12-Monats-Zeitraum immer passt.

Aufruf: python tests/test_erp_preise.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import einstellungen_nav, einstellungen_ordnung, funktionen, rechnen  # noqa: E402
from rohrlaser import erp_preise as E  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.erp_preise_dialog import SpaltenDialog  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
HEUTE = datetime.date.today()


def ok(text):
    print("OK    ", text)


def nah(a, b, text, eps=1e-6):
    assert a is not None and abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def tag(vor):
    return (HEUTE - datetime.timedelta(days=vor)).strftime("%d.%m.%Y")


# ------------------------------------------------------------------ E1 Lesen
assert E.zahl("3,10") == 3.1 and E.zahl("1.234,56") == 1234.56 and E.zahl("1,234.56") == 1234.56
assert E.zahl("12.5") == 12.5 and E.zahl("1.250") == 1250 and E.zahl("3,45 €") == 3.45 and E.zahl("120 m") == 120
assert E.zahl("abc") is None and E.zahl("") is None
assert E.datum("15.01.2026") == datetime.date(2026, 1, 15) and E.datum("15.01.26") == datetime.date(2026, 1, 15)
assert E.datum("2026-01-15 08:12") == datetime.date(2026, 1, 15) and E.datum("46037") == datetime.date(2026, 1, 15)
assert E.datum("Kaufdatum") is None
ok("Zahlen (Komma, Tausenderpunkt, €/m) und Datum (TT.MM.JJJJ, ISO, Excel-Tageszahl)")

ZEILEN = [
    ("Export Einkauf Rohre", "", "", "", ""),
    ("Kaufdatum", "Menge in Meter", "Meterpreis", "Artikelnummer", "EK Artikel"),
    (tag(420), "60", "2,70", "100421", "Rohr 42,4x2,0 S235JRH EN10219"),         # außerhalb 12 Monate
    (tag(290), "120,0", "3,10", "100421", "Rohr 42,4x2,0 S235JRH EN10219"),
    (tag(190), "60", "3,20", "100421", "Rohr 42,4x2,0 S235JRH EN10219"),
    (tag(80), "240", "3,05", "100421", "Rohr 42,4x2,0 S235JRH EN10219"),
    (tag(28), "6", "4,90", "100421", "Rohr 42,4x2,0 S235JRH EN10219"),           # Kleinmenge = Ausreißer
    (tag(240), "90", "5,40", "100430", "Quadratrohr 40 x 40 x 3 S235JRH EN 10219"),
    (tag(60), "120", "5,60", "100430", "Quadratrohr 40 x 40 x 3 S235JRH EN 10219"),
    (tag(60), "60", "7,10", "100431", "Quadratrohr 40x40x3 Stahl feuerverzinkt"),
    (tag(140), "48", "7,90", "100512", "Rechteckrohr 60x40x3 S355J2H EN10219"),
    (tag(170), "36", "7,20", "100440", "Rohr 50x50x4 S235JRH EN10219"),
    (tag(100), "30", "9,80", "200100", "Rundrohr 42,4 x 2,0 1.4301"),
    (tag(270), "10", "1,20", "900001", "Gewindestange M12 verzinkt"),
    (tag(230), "-12", "3,10", "100421", "Rohr 42,4x2,0 S235JRH EN10219"),        # Gutschrift
    ("", "", "", "", "Summe"),
]
csv_datei = tmp / "einkauf.csv"
csv_datei.write_bytes(("\r\n".join(";".join(z) for z in ZEILEN) + "\r\n").encode("cp1252"))
daten = E.lesen(csv_datei.read_bytes())
assert daten["kopf"] == list(ZEILEN[1]) and daten["erste"] == 3, daten["kopf"]
zu = E.spalten_vorschlag(daten["kopf"])
assert zu == dict(datum=0, menge=1, preis=2, artikelnr=3, bezeichnung=4), zu
liste, meldungen = E.kaeufe(daten, zu)
assert len(liste) == 12 and len(meldungen) == 1 and "Gutschrift" in meldungen[0] and meldungen[0].startswith("Zeile 15")
assert liste[0]["menge"] == 60 and liste[0]["preis"] == 2.7 and liste[0]["schluessel"] == "100421"
assert E.spalten_vorschlag(["Datum", "Meter", "Preis €/m", "Art.-Nr.", "Bezeichnung"]) == \
    dict(datum=0, menge=1, preis=2, artikelnr=3, bezeichnung=4)
assert E.fehlende(E.spalten_vorschlag(["Datum", "Wert", "Text"])) == ["menge", "preis"]
ok("CSV: Titelzeile übersprungen, Windows-1252, Spalten erkannt, Gutschrift gemeldet, Summenzeile still")

# ------------------------------------------------------------------ E2 Zerlegen
db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
e = E.zerlegen("Quadratrohr 40 x 40 x 3 S235JRH EN 10219", k)
assert (e["profil_id"], e["werkstoff_id"], e["oberflaeche"], e["ampel"]) == ("QR 40x40x3", "S235-10219", "", E.GRUEN)
e = E.zerlegen("Quadratrohr 40x40x3 S355J2H feuerverzinkt", k)
assert e["profil_id"] == "QR 40x40x3" and e["werkstoff_id"] is None and e["kandidaten"] == ["S355-10210", "S355-10219"]
assert "S235-10210" not in k.werkstoffe, "S235 EN 10210 gibt es nicht (Patrick 20.11.2026)"
assert E.zerlegen("Quadratrohr 40x40x3 S235JRH", k)["werkstoff_id"] == "S235-10219"
assert e["oberflaeche"] == "feuerverzinkt" and e["ober_unbekannt"] and e["ampel"] == E.GELB, e
e = E.zerlegen("Rohr 50x50x4 S235JRH EN10219", k)
assert e["profil_id"] is None and e["vorschlag"]["profil_id"] == "QR 50x50x4" and e["ampel"] == E.ROT
e = E.zerlegen("Rohr 60x40x3 1.4301 K240", k)
assert (e["profil_id"], e["werkstoff_id"], e["oberflaeche"]) == ("RE 60x40x3", "1.4301", "K240")
assert E.zerlegen("RO 48,3x2,6 S235 gebeizt", k)["profil_id"] == "RR 48,3x2,6"
assert E.zerlegen("Gewindestange M12 verzinkt", k)["hinweis"].startswith("Abmessung nicht erkannt")
ok("Bezeichnung: Profil (auch QR aus 40 x 40 x 3, RO = Rundrohr), Werkstoff mit EN-Norm, Oberfläche, Ampel")

# Patricks ERP-Export (EKexport_S235/S355.csv, 20.11.2026; Preise hier erfunden): Spalten Bestell-Nr., ArtNr,
# Bezeichnung, Zusatztext, Menge [m], Preis [€/m], Datum Erf., PE; Werkstoff aus Zusatztext bzw. „kaltgefertigt“,
# Form und Güte notfalls aus der Artikelnummer („30x30x3 S355“ ohne Rohrart)
ERP = ("Bestell-Nr.;ArtNr;Bezeichnung;Zusatztext;Bez4;Menge;Preis;L-Termin;Angebotsdatum;Datum Erf.;erfasst;PE;\r\n"
       "2026-1;EQRS235-40x40x3;Quadratrohr 40x40x3 kaltgefertigt;EN 10219- S235 HL 6m ******** Bitte auf Geradheit "
       "achten ********;;438;3,07;16.12.2026;;17.09.2026;Machnik;1;\r\n"
       "2026-2;EQRS355-40x40x3;40x40x3 S355;6050mm DIN EN 10219;;30;356;26.11.2026;;19.11.2026;Machnik;100;\r\n"
       "2026-3;ERRS235-60x40x3gs;Rechteckrohr 60x40x3;S235 Getrahlt HL 6m;;12,1;5,5;01.12.2026;;18.11.2026;Machnik;1;\r\n"
       "2026-4;EIPES235-100;IPE 100 mm HL 6m;S235 16x 4500mm;;72;9,1;01.12.2026;;18.11.2026;Machnik;1;\r\n")
d = E.lesen(ERP.encode("cp1252"))
z = E.spalten_vorschlag(d["kopf"])
assert [d["kopf"][z[f]] for f in ("datum", "menge", "preis", "artikelnr", "bezeichnung", "zusatz", "pe")] == \
    ["Datum Erf.", "Menge", "Preis", "ArtNr", "Bezeichnung", "Zusatztext", "PE"], z
ks, meld = E.kaeufe(d, z)
assert len(ks) == 4 and not meld and ks[0]["datum"] == datetime.date(2026, 9, 17), meld
assert ks[1]["preis"] == 3.56 and "Geradheit" in ks[0]["bezeichnung"] and "***" not in ks[0]["bezeichnung"]
arts = {a["artikelnr"]: a for a in E.artikel(ks, {}, k)}
assert (arts["EQRS235-40x40x3"]["profil_id"], arts["EQRS235-40x40x3"]["werkstoff_id"]) == ("QR 40x40x3", "S235-10219")
assert (arts["EQRS355-40x40x3"]["profil_id"], arts["EQRS355-40x40x3"]["werkstoff_id"]) == ("QR 40x40x3", "S355-10219")
assert arts["ERRS235-60x40x3gs"]["profil_id"] == "RE 60x40x3" and arts["ERRS235-60x40x3gs"]["oberflaeche"] == "gestrahlt"
assert "16x4500" not in arts["EIPES235-100"]["hinweis"].replace(" ", ""), arts["EIPES235-100"]["hinweis"]
assert E.artikelnr_hinweis("EQRS355-60x60x6,3gs") == " Quadratrohr S355 gestrahlt"
ok("ERP-Export (Patrick 20.11.2026): Datum Erf., Zusatztext, PE, Werkstoff aus Norm/kaltgefertigt, Form aus ArtNr")

# Patricks Export: 85 von 417 Artikeln „S235 mehrdeutig“ ohne EN 10219/10210 – entscheiden nahtlos/geschweißt,
# Rohrnormen, besondere Güten (P235GH, E235+C) und die Artikelnummer (…N = nahtlos, SNB/gn = geschweißt)
for text, artnr, soll in (("Ø-Rohr 76,1x2,6 S235 HL 6000 mm · DIN2458", "", "S235-10219"),
                          ("Ø-Rohr 38x3,6 S235 HL 6000 mm · geschweißt", "", "S235-10219"),
                          ("Ø-Rohr 42,4x4 S355 nahtlos HL 6000 mm", "", "S355-10210"),
                          ("Rundrohr 18x2 · S355", "ERS355D18x2N", "S355-10210"),
                          ("Rechteckrohr 50x20x2 S355", "ERRS355-50x20x2SNB", "S355-10219"),
                          ("Rechteckrohr 50x30x3 gestrahlt · EN 10219- S235/S275 HL 6m", "", "S235-10219"),
                          ("Ø-Rohr 26,9x2,6 S195T HL 6000 mm · EN10225", "ERS235D269x26", "S195T-10255"),
                          ("Ø-Rohr 133x4 P235TR2 HL 6000 mm · EN 10216-1 P235TR2", "ERS235D133x4", "P235TR2-10216"),
                          ("Ø-Rohr 57x3,2 P235GH HL 6000 mm · nahtlos", "ERS235D57x32N", "P235GH-10216"),
                          ("Ø-Rohr 42x2 S235 HL 6000 mm · E235+C nahtlos", "ERS235D42x2bkN", "E235-10305"),
                          ("Ø-Rohr 30x2 S355 HL 6000 mm", "ERS355D30x2", None)):
    e = E.zerlegen(text + E.artikelnr_hinweis(artnr), k)
    assert e["werkstoff_id"] == soll, (text, artnr, e["werkstoff_id"], e["kandidaten"])
assert E.artikelnr_hinweis("ERS235D70x7NBK") == " Rundrohr S235 blank nahtlos"
assert E.artikelnr_hinweis("ERRS355-120x60x8gn") == " Rechteckrohr S355 geschweißt"
ok("Werkstoff ohne Norm: nahtlos/geschweißt, DIN 2458, P235GH, E235+C und Artikelnummer entscheiden; sonst offen")

# ------------------------------------------------------------------ E3 Fenster
assert db.einstellung("funktion_erp_preise") == "nein", "11a: Vorgabe aus"
f = Hauptfenster(db, tmp, stumm=True)
seite = next(s for s in f.seiten if s.t.name == "preise")
f.funktionen_anwenden()
assert seite.erp_knopf.isHidden(), "Knopf nur mit eingeschalteter Funktion"
db.einstellung_setzen("funktion_erp_preise", "ja")
f.funktionen_anwenden()
assert not seite.erp_knopf.isHidden()
assert "e_erp_preise" in [s.schluessel for s in einstellungen_ordnung.SEITEN]
assert any("e_erp_preise" in seiten for _, seiten in einstellungen_nav.GRUPPEN)
assert funktionen.seite_an("e_erp_preise", db)
ok("Funktion „Materialpreise aus ERP-CSV“: Vorgabe aus, Knopf bei den Preisen, Seite ERP-Preisimport")

preise_vorher = db.zeilen("preise")
d = seite.erp_preise(str(csv_datei), zeigen=False)
assert d is not None and d.meldungen and "12 Käufe gelesen, davon 12 neu" in d.kopf.text(), d.kopf.text()
art = {a["artikelnr"]: a for a in d.artikel}
assert art["100421"]["ampel"] == art["100430"]["ampel"] == art["200100"]["ampel"] == E.GRUEN
assert art["100431"]["ampel"] == E.GELB and art["100440"]["ampel"] == E.ROT and art["900001"]["ampel"] == E.ROT
assert d.artikel[0]["ampel"] == E.ROT, "rote zuerst"
assert d.reiter.currentIndex() == 0 and "3 offen" in d.reiter.tabText(0)
ok("Prüfliste: 6 ERP-Artikel, grün/gelb/rot, offene zuerst")

r = next(i for i, a in enumerate(d.artikel) if a["artikelnr"] == "100431")
d.setzen(r, werkstoff="S235-10219")
art = {a["artikelnr"]: a for a in d.artikel}
assert art["100431"]["gemerkt"] and art["100431"]["oberflaeche"] == "feuerverzinkt" and art["100431"]["ampel"] == E.GRUEN
r = next(i for i, a in enumerate(d.artikel) if a["artikelnr"] == "100440")
assert d.profil_anlegen(r, werte=dict(profil_id="QR 50x50x4", form="Quadratrohr", a=50, wand=4,
                                      bemerkung="aus ERP-Preisimport angelegt")) == "QR 50x50x4"
art = {a["artikelnr"]: a for a in d.artikel}
assert art["100440"]["profil_id"] == "QR 50x50x4" and art["100440"]["ampel"] == E.GRUEN
r = next(i for i, a in enumerate(d.artikel) if a["artikelnr"] == "900001")
d.setzen(r, profil="– überspringen –")
art = {a["artikelnr"]: a for a in d.artikel}
assert art["900001"]["ignorieren"] and "offen" not in d.reiter.tabText(0)
ok("Werkstoff gewählt (gemerkt), Profil QR 50x50x4 angelegt, Gewindestange übersprungen")

g = {(x["profil_id"], x["werkstoff_id"], x["oberflaeche"]): x for x in d.gruppen}
rr = g[("RR 42,4x2,0", "S235-10219", "")]
nah(rr["durchschnitt"], round((120 * 3.10 + 60 * 3.20 + 240 * 3.05) / 420, 2), "Ø nach Menge ohne Ausreißer")
assert rr["anzahl"] == 3 and rr["ausreisser"] == 1 and rr["letzter"] == 4.9 and rr["meter"] == 420
assert [x["im_zeitraum"] for x in rr["kaeufe"]] == [False, True, True, True, True]
heute_rr = rechnen.kg_je_m("RR 42,4x2,0", "S235-10219", d.k) * 1.45
nah(rr["heute"], heute_rr, "heutiger Preis aus €/kg")
qr = g[("QR 40x40x3", "S235-10219", "")]
nah(qr["durchschnitt"], round((90 * 5.4 + 120 * 5.6) / 210, 2), "Ø QR")
es = g[("RR 42,4x2,0", "1.4301", "")]
nah(es["heute"], 62 / 6, "heute aus €/Stange")
assert ("QR 50x50x4", "S235-10219", "") in g and g[("QR 40x40x3", "S235-10219", "feuerverzinkt")]["abweichung"] is None
ok(f"Preise: RR 42,4x2,0 Ø {rr['durchschnitt']} €/m (heute {rr['heute']:.2f}), Ausreißer und alte Käufe zählen nicht")

auf = E.aufpreise(d.gruppen, d.k)
assert [a["oberflaeche"] for a in auf] == ["feuerverzinkt"]
nah(auf[0]["aufpreis_kg"], (7.10 - qr["durchschnitt"]) / qr["kg_m"], "Aufpreis €/kg")
assert "feuerverzinkt" in d.aufpreis.text()
ok(f"Aufpreis-Vorschlag feuerverzinkt {auf[0]['aufpreis_kg']:.2f} €/kg (nur Anzeige)")

zeile = d.gruppen.index(rr)
v = d.verlauf(zeile, zeigen=False)
assert v.tabelle.rowCount() == 5 and v.tabelle.item(4, 0).checkState() == Qt.Unchecked
v.tabelle.item(4, 0).setCheckState(Qt.Checked)        # Ausreißer von Hand mitrechnen
d.neu_rechnen()
rr2 = next(x for x in d.gruppen if (x["profil_id"], x["werkstoff_id"], x["oberflaeche"]) == ("RR 42,4x2,0", "S235-10219", ""))
nah(rr2["durchschnitt"], round((1296 + 6 * 4.9) / 426, 2), "Ø mit Ausreißer von Hand")
v = d.verlauf(d.gruppen.index(rr2), zeigen=False)
v.automatisch()
d.neu_rechnen()
rr3 = next(x for x in d.gruppen if (x["profil_id"], x["werkstoff_id"], x["oberflaeche"]) == ("RR 42,4x2,0", "S235-10219", ""))
assert rr3["durchschnitt"] == rr["durchschnitt"]
ok("Verlauf: Ausreißer per Haken mitrechnen und wieder automatisch")

assert db.zeilen("preise") == preise_vorher, "Stammdaten-Preise bleiben unverändert"
ok("Übersicht ohne Übernahme: Stammdaten-Preise unverändert")

d2 = seite.erp_preise(str(csv_datei), zeigen=False)
assert "davon 0 neu gespeichert (12 schon vorhanden)" in d2.kopf.text(), d2.kopf.text()
assert all(a["ampel"] == E.GRUEN for a in d2.artikel) and len(E.gespeicherte(db)) == 12
ok("Zweiter Import: keine doppelten Käufe, gewählte Zuordnungen gemerkt")

r = next(i for i, a in enumerate(d2.artikel) if a["artikelnr"] == "100431")
d2.vergessen(r)
assert next(a for a in d2.artikel if a["artikelnr"] == "100431")["ampel"] == E.GELB
ok("Zuordnung vergessen: wieder aus der Bezeichnung erkannt")

sd = SpaltenDialog(None, ["Datum", "Wert", "Text"], {"datum": 0})
sd._ok()
assert "Fehlt" in sd.fehler.text() and sd.result() == 0
for feld, i in (("menge", 1), ("preis", 1), ("bezeichnung", 2)):
    sd.wahl[feld].setCurrentIndex(i + 1)
sd._ok()
assert "mehrfach" in sd.fehler.text()
ok("Spalten zuordnen: Pflichtfelder und doppelte Spalten geprüft")

# ------------------------------------------------------------------ E4 Angebot
def k_(tage, menge, preis, rechnen=None, i=0):
    return dict(id=i, datum=HEUTE - datetime.timedelta(days=tage), menge=menge, preis=preis, rechnen=rechnen)


KS = [k_(420, 60, 2.7, i=1), k_(290, 120, 3.1, i=2), k_(190, 60, 3.2, i=3), k_(80, 240, 3.05, i=4), k_(28, 6, 4.9, i=5)]
assert E.kauf_waehlen(KS, 100, HEUTE)[0]["preis"] == 3.2, "neuester mit 50-200 m"
assert E.kauf_waehlen(KS, 200, HEUTE) == (KS[3], True)
assert E.kauf_waehlen(KS, 5000, HEUTE) == (KS[4], False), "keine ähnliche Menge: der neueste"
assert E.kauf_waehlen(KS[:1], 60, HEUTE) is None, "älter als 12 Monate"
assert E.kauf_waehlen(KS[:4] + [k_(10, 100, 3.0, rechnen=0, i=6)], 100, HEUTE)[0]["preis"] == 3.2, "von Hand aus"
ok("Kauf zum Bedarf: ähnliche Menge (0,5- bis 2-fach), sonst neuester, nur 12 Monate, von Hand ausgeschlossene nicht")
assert E.kauf_waehlen(KS, 5000, HEUTE, grenze=0.25) == (KS[3], False), "Ausreißer 4,90 €/m (Kleinmenge) nicht"
assert E.kauf_waehlen(KS[:4] + [k_(28, 6, 4.9, rechnen=1, i=5)], 5000, HEUTE, grenze=0.25)[0]["preis"] == 4.9, \
    "von Hand „immer mitrechnen“"
assert abs(E.schnitt(KS, HEUTE) - (120 * 3.1 + 60 * 3.2 + 240 * 3.05 + 6 * 4.9) / 426) < 1e-9
ok("Vorschlag ohne Ausreißer (außer von Hand mitrechnen), Durchschnitt nach Menge über 12 Monate")

db.einstellung_setzen("funktion_erp_preise", "ja")
an = beispiel_angebot.anlegen(db)
s = f.angebot_oeffnen(an)
assert s.optimieren()
erp = db.angebot(an)["erp_preise"]
schl = rechnen.erp_schluessel("RR 42,4x2,0", "S235-10219", "")
# Patrick 23.11.2026: direkt nur bei Kauf ≤ 4 Wochen mit passender Stangenzahl; der junge 6-m-Kauf ist ein Ausreißer
assert schl in erp and not erp[schl]["direkt"] and "nur Vorschlag, nicht eingesetzt" in erp[schl]["bemerkung"], erp
g0 = next(g for g in rechnen.material_abmessungen(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen)
          if (g["profil"], g["werkstoff"]) == ("RR 42,4x2,0", "S235-10219"))
assert g0["erp"] is None, "Vorschlag wird nicht eingerechnet"
ok("Kauf älter als 4 Wochen: nur Vorschlag, das Angebot rechnet mit dem Stammdatenpreis")
db.einstellung_setzen("erp_direkt_tage", 365)       # für die folgenden Prüfungen wie vorher: jeder Kauf im Jahr
db.einstellung_setzen("erp_direkt_stangen", 100)
s.optimieren()
erp = db.angebot(an)["erp_preise"]
assert erp[schl]["direkt"] and "direkt eingesetzt" in erp[schl]["bemerkung"], erp[schl]
schl = rechnen.erp_schluessel("RR 42,4x2,0", "S235-10219", "")
assert schl in erp and rechnen.erp_schluessel("RR 48,3x2,6", "S235-10219", "") not in erp, erp
assert erp[schl]["bemerkung"].startswith("ERP-Preis vom ") and "Stangen à 6 m" in erp[schl]["bemerkung"], erp[schl]
assert s.stand_optimierung() == "aktuell", "ERP-Preis ändert den Schnittplan nicht"
gr = {(g["profil"], g["werkstoff"]): g for g in rechnen.material_abmessungen(s.kopf, s.positionen, s.ergebnis, s.k,
                                                                             s.tabellen)}
g = gr[("RR 42,4x2,0", "S235-10219")]
assert g["erp"] and abs(g["berechnet"] - erp[schl]["preis"]) < 1e-9 and abs(g["wirksam"] - g["berechnet"]) < 1e-9
assert gr[("RR 48,3x2,6", "S235-10219")]["erp"] is None, "ohne Kauf wie bisher"
herkunft = rechnen.preis_herkunft(next(p for p in s.positionen if p["profil_id"] == "RR 42,4x2,0"), s.kopf, s.k,
                                  s.tabellen)
assert "ERP-Preis vom" in herkunft
ok(f"Nach dem Optimieren: RR 42,4x2,0 mit {erp[schl]['preis']} €/m ({erp[schl]['bemerkung']}), RR 48,3 wie bisher")

gesehen = {}


def schauen(dlg):
    gesehen["tipp"] = dlg.tabelle.item(0, 11).toolTip()
    gesehen["text"] = dlg.tabelle.item(0, 11).text()
    return 0


s.material_einstellen(schauen)
assert "ERP-Preis vom" in gesehen["tipp"] and "ⓔ" in gesehen["text"], gesehen
ok("Material-Fenster: ERP-Preis grau mit ⓔ, Bemerkung im Tooltip")

pos = next(p for p in s.positionen if p["profil_id"] == "RR 42,4x2,0")
hand = [dict(p, preis_m=9.99) if p["id"] == pos["id"] else p for p in s.positionen]
assert abs(rechnen.meterpreis(pos, s.kopf, hand, s.k, s.tabellen)[1] - 9.99) < 1e-9, "Preis von Hand geht vor"
s.kopf["preisbasis"] = {"x": 1}
assert s.erp_vorschlagen() == 0, "festgeschrieben: kein neuer Vorschlag"
s.kopf["preisbasis"] = None
db.einstellung_setzen("funktion_erp_preise", "nein")
assert s.erp_vorschlagen() == 0 and db.angebot(an)["erp_preise"] == erp, "Funktion aus: gewählte Preise bleiben"
ok("Preis von Hand geht vor; festgeschrieben bzw. Funktion aus: kein neuer Vorschlag, gewählte Preise bleiben")

# ------------------------------------------------------------------ E5 Preisverlauf
ev = E.verlauf_eintraege(db, db.kontext())
rr = [e for e in ev if e["profil_id"] == "RR 42,4x2,0" and e["art"] == E.ART_VERLAUF]
assert len(rr) >= 2 and all(e["basis"] == "€/m" and " m" in e["lieferant"] for e in rr), rr
assert [e["datum"] for e in rr] == sorted(e["datum"] for e in rr)
from rohrlaser.preisverlauf_dialog import PreisverlaufDialog  # noqa: E402
pd = PreisverlaufDialog(db, auswahl=(E.ART_VERLAUF, "RR 42,4x2,0", "S235-10219", None))
assert pd.wahl.currentText().startswith("RR 42,4x2,0 / S235-10219 (ERP-Einkauf"), pd.wahl.currentText()
assert pd.tabelle.rowCount() == len([e for e in rr if e["werkstoff_id"] == "S235-10219"]) and pd.kurve.punkte
ok(f"Preisverlauf: ERP-Einkäufe als eigene Kurve je Abmessung ({len(rr)} Tage RR 42,4x2,0), mit Ø 3/6/12 Monate")

# ------------------------------------------------------------------ E6 S235 EN 10210 entfernt (Patrick 20.11.2026)
db2 = Datenbank(tmp / "alt.db")
with db2.con:
    w = next(z for z in db2.zeilen("werkstoffe") if z["werkstoff_id"] == "S235-10219")
    sp = [c for c in w if c != "id"]
    db2.con.execute(f"INSERT INTO werkstoffe ({', '.join(sp)}) VALUES ({', '.join('?' * len(sp))})",
                    [("S235-10210" if c == "werkstoff_id" else w[c]) for c in sp])
    pr = db2.zeilen("preise")
    doppelt = next(z for z in pr if z["werkstoff_id"] == "S235-10219")
    nur = next(z for z in pr if z["werkstoff_id"] != "S235-10219" and z["profil_id"] not in
               {x["profil_id"] for x in pr if x["werkstoff_id"] == "S235-10219"})
    db2.con.execute("UPDATE preise SET werkstoff_id='S235-10210' WHERE id=?", (nur["id"],))
    sp = [c for c in doppelt if c != "id"]
    db2.con.execute(f"INSERT INTO preise ({', '.join(sp)}) VALUES ({', '.join('?' * len(sp))})",
                    [("S235-10210" if c == "werkstoff_id" else doppelt[c]) for c in sp])
    for t in ("S275-10219", "S195T-10255"):
        db2.con.execute("DELETE FROM werkstoffe WHERE werkstoff_id=?", (t,))
    db2.einstellung_setzen("erp_werkstoffe_stand", "")
db2.con.close()
db2 = Datenbank(tmp / "alt.db")
ids = {z["werkstoff_id"] for z in db2.zeilen("werkstoffe")}
assert "S235-10210" not in ids and {"S275-10219", "S195T-10255", "P235TR2-10216"} <= ids, ids
pr2 = db2.zeilen("preise")
assert not [z for z in pr2 if z["werkstoff_id"] == "S235-10210"]
assert len([z for z in pr2 if (z["profil_id"], z["werkstoff_id"]) == (doppelt["profil_id"], "S235-10219")]) == 1
assert any((z["profil_id"], z["werkstoff_id"]) == (nur["profil_id"], "S235-10219") for z in pr2)
ok("S235 EN 10210 entfernt: Preise auf S235 EN 10219 (doppelte fallen weg), S275/S195T/P235TR2 ergänzt")

print("Alle Tests ERP-Preise bestanden.")
