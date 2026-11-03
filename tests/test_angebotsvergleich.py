"""Prüft den Angebotsvergleich aus CSV (Plan 30.10.2026, Freigabe 1c 2c 3a 4a 5a 6a 7a 8a 9b):

- V1 eigener CSV-Export (CSV und ZIP) wird erkannt, ohne Zuordnung gelesen (Punkt als Dezimalzeichen, „93.2 %“)
- V2 fremde CSV aus Excel (Windows-1252, Titelzeile, Komma, €, Summenzeile): Vorschlag der Spaltenzuordnung,
     „Preis“ neben „Gesamt“ = Stückpreis, Summenzeile übersprungen, Zeile ohne Preis als Hinweis
- V3 Zuordnung: Artikelnummer (Schreibweise egal), dann Bezeichnung + Länge, dann Position; Rest nur in A/B;
     von Hand zuordnen und lösen
- V4 Vergleich: Differenz B − A je Stück und in %, verschiedene Mengen -> B auf Mengen von A, Hinweise zu Menge,
     Werkstoff, Länge, Zeit/HK/Marge; Markierung ab 5 % oder 50 €; Summen stimmen mit den Zeilen
- V5 Zahlen lesen: 1.234,50 / 1,234.50 / 1.500 / 12.5 / Zeiten HH:MM:SS
- V6 Fehler: leere Datei, .xlsx, ZIP ohne Positionen, Zuordnung ohne Preis
- V7 Angebot aus der Liste = dieselben Werte wie sein CSV-Export; nicht optimiert -> Hinweis
- V8 Dialog: Angebote aus der Liste, fremde CSV mit Vorlage, nur Abweichungen, Zuordnen, PDF und CSV; Datei-Menü
     und Kontextmenü der Angebotsliste (zwei markierte), Funktion ausschaltbar; nichts im Angebot gespeichert

Aufruf: python tests/test_angebotsvergleich.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import angebotsvergleich as av  # noqa: E402
from rohrlaser import export  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


def nah(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol


def fehler(aufruf):
    try:
        aufruf()
    except av.VergleichFehler as e:
        return str(e)
    raise AssertionError("kein Fehler")


EIGEN_CSV = (
    "﻿" + ";".join(export.POSITION_SPALTEN) + "\r\n"
    "2613000461;1;Vordach_Rohr-1;1;;0;;6000;;1;2;66.77;133.54;0;Stahl;S235 EN10219;3;1.065;24.242;904;T11;N₂;"
    "23.10.2026;2958;;Rechteckrohr 120 x 60 x 3, L = 2958 mm;00:00:10;00:12:16;0;69.11;93.2 %;;1.01;25.261;34.55;"
    "64.43;50.94;50.52;4%;Profile [Rechteckrohr 120x60x3]\r\n"
    "2613000461;2;Vordach_Rohr-2;2;;0;;6000;;1;4;47.51;190.04;0;Stahl;S235 EN10219;3;0.504;11.474;1155;T11;N₂;"
    "23.10.2026;1400;;Rechteckrohr 120 x 60 x 3, L = 1400 mm;00:00:09;00:19:26;0;98.71;92.5 %;;1.01;11.956;24.68;"
    "91.33;48.22;47.82;4%;Profile [Rechteckrohr 120x60x3], Gewinde [4xM6]\r\n"
    "2613000461;3;Lasche;3;;0;;6000;;1;10;5.00;50.00;0;Stahl;S235 EN10219;3;0.1;1;100;T11;N₂;"
    "23.10.2026;80;;Lasche 40x4;00:00:02;00:00:30;0;3;66.7 %;;1.01;1;3.00;20;5;1;4%;Profile [Flach 40x4]\r\n"
).encode("utf-8")

# ------------------------------------------------------------------ V1 eigener Export
q = av.datei_lesen(roh=EIGEN_CSV, name="2613000461 Angebotspositionen.csv")
assert q["eigen"] and q["titel"] == "Angebot 2613000461", q["titel"]
pa, h = av.positionen(q)
assert len(pa) == 3 and not h
p = pa[0]
assert p["artikel"] == "Vordach_Rohr-1" and p["pos"] == "1" and nah(p["menge"], 2) and nah(p["stueckpreis"], 66.77)
assert nah(p["preis"], 133.54) and nah(p["laenge"], 2958) and nah(p["hk"], 34.55) and nah(p["marge"], 93.2)
assert p["zeit"] == 10 and p["werkstoff"] == "S235 EN10219" and p["abmessung"] == "Rechteckrohr 120x60x3"
puffer = io.BytesIO()
with zipfile.ZipFile(puffer, "w") as z:
    z.writestr(export.POSITION_DATEI, EIGEN_CSV)
    z.writestr(export.KOPF_DATEI, export.csv_bytes(export.KOPF_SPALTEN, [[""] * 3 + ["AP Glas GmbH"] + [""] * 22]))
qz = av.datei_lesen(roh=puffer.getvalue(), name="Angebot_2613000461.zip")
assert qz["eigen"] and qz["titel"] == "Angebot 2613000461 – AP Glas GmbH", qz["titel"]
assert [x["stueckpreis"] for x in av.positionen(qz)[0]] == [x["stueckpreis"] for x in pa]
ok("V1 eigener CSV-Export (CSV und ZIP) ohne Zuordnung, Zahlen mit Punkt, Abmessung aus den Arbeitsgängen")

# ------------------------------------------------------------------ V2 fremde CSV
FREMD = ("Angebot Konkurrenz GmbH Nr. 4711\r\n"
         "Pos.;Art.-Nr.;Bezeichnung;Werkstoff;Länge;Menge;Preis;Gesamt\r\n"
         "10;VORDACH ROHR 1;Rohr 120x60x3;S355;2958;2;70,00 €;140,00 €\r\n"
         "20;vordach_rohr-2;Rohr 120x60x3 mit Gewinde;S235 EN10219;1400;5;45,50;227,50\r\n"
         "30;;Lasche 40x4;S235;80;10;5,10;51,00\r\n"
         "40;X-99;Neues Teil;S235;500;1;12,00;12,00\r\n"
         "50;Z-1;Zeichnung fehlt;;;1;;\r\n"
         ";;Summe netto;;;;;430,50\r\n").encode("cp1252")
qb = av.datei_lesen(roh=FREMD, name="Konkurrenz.csv")
assert not qb["eigen"] and qb["titel"] == "Konkurrenz" and qb["spalten"][0] == "Pos."
zu = av.vorschlag(qb["spalten"])
assert zu == dict(pos="Pos.", artikel="Art.-Nr.", bezeichnung="Bezeichnung", werkstoff="Werkstoff", laenge="Länge",
                  menge="Menge", stueckpreis="Preis", preis="Gesamt"), zu
assert av.zuordnung_pruefen(zu) is None
pb, hb = av.positionen(qb, zu)
assert len(pb) == 4 and nah(pb[0]["stueckpreis"], 70) and nah(pb[1]["preis"], 227.5) and pb[0]["pos"] == "10"
assert any("Zeile 5" in t and "ohne Preis" in t for t in hb) and any("Summenzeile" in t for t in hb), hb
ok("V2 fremde CSV: Windows-1252, Titelzeile, Komma und €, Vorschlag der Zuordnung, Summenzeile übersprungen")

# ------------------------------------------------------------------ V3 Zuordnung
alle_paare = av.zuordnen(pa, pb)        # Schreibweise der Artikelnummer egal; Lasche ohne Nummer: Bezeichnung
assert alle_paare == [(0, 0, "artikel"), (1, 1, "artikel"), (2, 2, "bezeichnung")], alle_paare
pb3 = [dict(x) for x in pb]
pb3[2]["laenge"] = 90.0                 # gleiche Bezeichnung, andere Länge: kein Paar
paare = av.zuordnen(pa, pb3)
assert paare == [(0, 0, "artikel"), (1, 1, "artikel")], paare
pa4 = [dict(x, artikel="", bezeichnung="") for x in pa]
pb4 = [dict(x, artikel="", bezeichnung="", pos=str(i + 1)) for i, x in enumerate(pb)]
assert av.zuordnen(pa4, pb4) == [(0, 0, "pos"), (1, 1, "pos"), (2, 2, "pos")]
p_hand = av.von_hand(paare, 2, 2)
assert (2, 2, "hand") in p_hand and len(p_hand) == 3
assert av.trennen(p_hand, 2) == paare
ok("V3 Zuordnung: Artikelnummer, Bezeichnung + Länge, Position; von Hand zuordnen und lösen")

# ------------------------------------------------------------------ V4 Vergleich
zeilen, s = av.vergleichen(pa, pb, paare, 0.05, 50)
arten = [z["art"] for z in zeilen]
assert arten == ["paar", "paar", "nur_a", "nur_b", "nur_b"], arten
z1, z2 = zeilen[0], zeilen[1]
assert nah(z1["diff_stk"], 3.23) and nah(z1["anteil"], 3.23 / 66.77) and not z1["markiert"]   # 4,8 % < 5 %
assert any(t.startswith("Werkstoff A S235 EN10219 / B S355") for t in z1["hinweise"]), z1["hinweise"]
# Menge B 5 statt 4: Stückpreis vergleichen, B auf Menge A
assert nah(z2["ges_b"], 45.5 * 4) and nah(z2["diff_ges"], 45.5 * 4 - 190.04) and "Menge A 4 / B 5" in z2["hinweise"]
assert zeilen[2]["markiert"] and zeilen[3]["markiert"]
assert s["paare"] == 2 and nah(s["paar_a"], 133.54 + 190.04) and nah(s["paar_b"], 140 + 182)
assert nah(s["diff"], s["paar_b"] - s["paar_a"]) and s["teurer"] == 1 and s["guenstiger"] == 1
assert s["nur_a"] == 1 and s["nur_b"] == 2 and nah(s["summe_a"], 373.58) and nah(s["summe_b_datei"], 430.5)
assert [z["diff_ges"] for z in s["groesste"]] == sorted((z1["diff_ges"], z2["diff_ges"]), key=lambda x: -abs(x))
z_m, _ = av.vergleichen(pa, pb, paare, 0.04, 0)
assert z_m[0]["markiert"]                                              # ab 4 %: markiert
z_e, _ = av.vergleichen(pa, pb, paare, 0, 6)
assert z_e[0]["markiert"] and z_e[1]["markiert"] is True               # 6,46 € bzw. 8,04 € ab 6 €
z_aus, _ = av.vergleichen(pa, pb, paare, 0, 0)
assert not z_aus[0]["markiert"] and not z_aus[1]["markiert"]
assert "B ist auf die zugeordneten Positionen 1,58 € (0,5 %) günstiger als A" in av.ergebnis_text(s), \
    av.ergebnis_text(s)
gleich = [dict(x) for x in pa]
gleich[0]["hk"], gleich[0]["zeit"] = 40.0, 70
zz, _ = av.vergleichen(pa, gleich, [(0, 0, "artikel")])
assert "HK/Stk A 34,55 € / B 40,00 €" in zz[0]["hinweise"] and "Zeit A 0:00:10 / B 0:01:10" in zz[0]["hinweise"]
text = av.csv_text(zeilen, s, "A", "B")
assert text.startswith("﻿Angebotsvergleich;A = A;B = B") and "66,77;70,00;3,23;+4,8 %" in text, text[:400]
ok("V4 Differenz B − A, Menge auf A hochgerechnet, Hinweise, Markierung 5 %/50 €, Summen, CSV")

# ------------------------------------------------------------------ V5 Zahlen
assert av.zahl("1.234,50 €") == 1234.5 and av.zahl("1,234.50", komma=False) == 1234.5
assert av.zahl("93.2 %", komma=False) == 93.2 and av.zahl("") is None and av.zahl("ca.") is None
assert av._dezimal_komma(["1.500", "2.000"]) and not av._dezimal_komma(["12.5", "3"]) and av._dezimal_komma(["3,5"])
assert av.sekunden("01:02:03") == 3723 and av.sekunden("2:30") == 150 and av.sekunden("1,5") == 90
ok("V5 Zahlen mit Komma/Punkt/€/%, Tausendertrennung, Zeiten")

# ------------------------------------------------------------------ V6 Fehler
assert "leer" in fehler(lambda: av.datei_lesen(roh=b"  \r\n", name="x.csv"))
assert "CSV" in fehler(lambda: av.datei_lesen(roh=b"\x00\x01", name="x.xlsx"))
leer_zip = io.BytesIO()
with zipfile.ZipFile(leer_zip, "w") as z:
    z.writestr("anderes.txt", "x")
assert export.POSITION_DATEI in fehler(lambda: av.datei_lesen(roh=leer_zip.getvalue(), name="x.zip"))
assert av.zuordnung_pruefen(dict(artikel="A")) and av.zuordnung_pruefen(dict(preis="P"))
ok("V6 Fehler: leere Datei, Excel-Datei, ZIP ohne Positionen, Zuordnung ohne Preis oder Kennung")

# ------------------------------------------------------------------ V7 Angebot aus der Liste
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)


def angebot_mit(kunde, laenge, stueck, optimieren=True):
    a = db.angebot_neu(dict(kunde=kunde, skonto=0, stange=6000))
    db.position_neu(a, dict(pos=10, artikel="Teil-1", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                            laenge=laenge, stueck=stueck, schneidweg=300, einstiche=2))
    db.position_neu(a, dict(pos=20, artikel="Teil-2", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                            laenge=400, stueck=5, schneidweg=200, einstiche=2))
    if optimieren:
        s = f.angebot_oeffnen(a)
        s.optimieren()
        s.neu_laden()
        pfad = s.csv_positionen(ordner=str(tmp))
        f.angebot_schliessen(a)
        return a, pfad
    return a, None


a1, csv1 = angebot_mit("Kunde Eins", 1000, 10)
a2, _ = angebot_mit("Kunde Zwei", 1000, 20)
a_leer, _ = angebot_mit("Ohne Plan", 1000, 10, optimieren=False)
vorher = (db.angebot(a1), db.positionen(a1))
qa = av.aus_angebot(db, a1)
qd = av.datei_lesen(csv1)
assert qa["eigen"] and qd["eigen"] and qa["titel"].startswith("Angebot ") and "Kunde Eins" in qa["titel"]
assert av.positionen(qa)[0] == av.positionen(qd)[0]
assert "nicht optimiert" in fehler(lambda: av.aus_angebot(db, a_leer))
ok("V7 Angebot aus der Liste = Werte seines CSV-Exports; nicht optimiert -> Hinweis")

# ------------------------------------------------------------------ V8 Dialog
d = f.angebote_vergleichen(a1, a2)
assert d.quellen["A"]["angebot_id"] == a1 and d.quellen["B"]["angebot_id"] == a2
assert [z["art"] for z in d.zeilen] == ["paar", "paar"] and d.summen["paare"] == 2
assert d.tabelle.rowCount() == 2 and "B ist" in d.ergebnis_text.text() or "gleich teuer" in d.ergebnis_text.text()
assert "5,0 %" in d.schwelle_text.text() and "50,00 €" in d.schwelle_text.text()
# fremde CSV als B, Vorlage greift beim zweiten Mal
fremd_pfad = tmp / "Konkurrenz.csv"
fremd_pfad.write_bytes(("Pos.;Art.-Nr.;Bezeichnung;Menge;Preis;Gesamt\r\n"
                        "1;teil-1;Rohr;10;1,00;10,00\r\n2;Teil-3;Anderes;5;2,00;10,00\r\n").encode("utf-8"))
assert d.datei_waehlen("B", str(fremd_pfad))
assert not d.quellen["B"]["eigen"] and d.zuordnungen["B"]["stueckpreis"] == "Preis"
assert [z["art"] for z in d.zeilen] == ["paar", "nur_a", "nur_b"] and d.spalten_knopf["B"].isEnabled()
db.einstellung_setzen(av.VORLAGEN, {"Konkurrenz": dict(spalten=["Pos.", "Art.-Nr.", "Bezeichnung", "Menge", "Preis",
                                                                 "Gesamt"],
                                                        zuordnung=dict(artikel="Art.-Nr.", menge="Menge",
                                                                       preis="Gesamt"))})
assert av.vorlage_finden(db.einstellung(av.VORLAGEN), d.quellen["B"]["spalten"]) == "Konkurrenz"
assert d.datei_waehlen("B", str(fremd_pfad))
assert d.zuordnungen["B"] == dict(artikel="Art.-Nr.", menge="Menge", preis="Gesamt")     # aus der Vorlage
assert nah(d.pos["B"][0]["stueckpreis"], 1.0)                                            # Preis ÷ Menge
# nur Abweichungen, Zuordnen von Hand
d.nur_abw.setChecked(True)
assert d.tabelle.rowCount() == sum(1 for z in d.zeilen if z["markiert"])
d.nur_abw.setChecked(False)
d.zuordnen(1, 1)
assert ("hand" in [p[2] for p in d.paare]) and [z["art"] for z in d.zeilen] == ["paar", "paar"]
d.tabelle.selectRow(1)
assert d.trennen_knopf.isEnabled()
d.trennen()
assert [z["art"] for z in d.zeilen] == ["paar", "nur_a", "nur_b"]
d.tabelle.clearSelection()
sel = d.tabelle.selectionModel()
for r in (1, 2):
    sel.select(d.tabelle.model().index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
assert d.zuordnen_knopf.isEnabled()
d.zuordnen()
assert len(d.paare) == 2
# Ausgabe
pdf_pfad = d.pdf(tmp / "vergleich.pdf")
assert pdf_pfad and pdf_pfad.read_bytes().startswith(b"%PDF") and pdf_pfad.stat().st_size > 2000
csv_pfad = d.csv(tmp / "vergleich.csv")
assert csv_pfad.read_bytes().startswith(b"\xef\xbb\xbfAngebotsvergleich")
# nichts gespeichert
assert (db.angebot(a1), db.positionen(a1)) == vorher
ok("V8 Dialog: Angebote aus der Liste, fremde CSV, Vorlage, nur Abweichungen, Zuordnen/Lösen, PDF und CSV")

# Datei-Menü, Kontextmenü der Angebotsliste, Funktion aus
assert "Angebote vergleichen …" in f.datei_aktionen
seite = f.angebote
seite.neu_laden()
seite.ansicht.clearSelection()
ids = []
for r in range(seite.filter.rowCount()):
    i = seite._id(seite.filter.index(r, 0))
    if i in (a1, a2):
        seite.ansicht.selectionModel().select(seite.filter.index(r, 0),
                                              QItemSelectionModel.Select | QItemSelectionModel.Rows)
        ids.append(i)
assert sorted(seite.markierte_ids()) == sorted((a1, a2))
menue = seite.kontextmenue(zeigen=False)
aktion = next(a for a in menue.actions() if a.text().startswith("Vergleichen"))
assert aktion.isEnabled() and aktion.text() == "Vergleichen …"
db.einstellung_setzen("funktion_vergleich", "nein")
f.funktionen_anwenden()
assert not f.datei_aktionen["Angebote vergleichen …"].isVisible()
assert not any(a.text().startswith("Vergleichen") for a in seite.kontextmenue(zeigen=False).actions())
db.einstellung_setzen("funktion_vergleich", "ja")
f.funktionen_anwenden()
ok("V8 Datei → Angebote vergleichen, Kontextmenü mit zwei markierten Angeboten, Funktion ausschaltbar")
print("Alle Prüfungen bestanden.")
