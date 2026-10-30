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
    (tag(60), "60", "7,10", "100431", "Quadratrohr 40x40x3 S235JRH feuerverzinkt"),
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
e = E.zerlegen("Quadratrohr 40x40x3 S235JRH feuerverzinkt", k)
assert e["profil_id"] == "QR 40x40x3" and e["werkstoff_id"] is None and e["kandidaten"] == ["S235-10210", "S235-10219"]
assert e["oberflaeche"] == "feuerverzinkt" and e["ober_unbekannt"] and e["ampel"] == E.GELB, e
e = E.zerlegen("Rohr 50x50x4 S235JRH EN10219", k)
assert e["profil_id"] is None and e["vorschlag"]["profil_id"] == "QR 50x50x4" and e["ampel"] == E.ROT
e = E.zerlegen("Rohr 60x40x3 1.4301 K240", k)
assert (e["profil_id"], e["werkstoff_id"], e["oberflaeche"]) == ("RE 60x40x3", "1.4301", "K240")
assert E.zerlegen("RO 48,3x2,6 S235 gebeizt", k)["profil_id"] == "RR 48,3x2,6"
assert E.zerlegen("Gewindestange M12 verzinkt", k)["hinweis"].startswith("Abmessung nicht erkannt")
ok("Bezeichnung: Profil (auch QR aus 40 x 40 x 3, RO = Rundrohr), Werkstoff mit EN-Norm, Oberfläche, Ampel")

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

db.einstellung_setzen("funktion_erp_preise", "ja")
an = beispiel_angebot.anlegen(db)
s = f.angebot_oeffnen(an)
assert s.optimieren()
erp = db.angebot(an)["erp_preise"]
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

print("Alle Tests ERP-Preise bestanden.")
