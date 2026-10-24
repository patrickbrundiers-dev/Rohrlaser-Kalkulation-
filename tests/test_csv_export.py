"""Prüft den CSV-Export Angebotskopf.csv / Angebotspositionen.csv (Format von Patrick, 23.10.2026):
- C1 Kopfzeilen und Spaltenzahl exakt wie vorgegeben, eine Kopfzeile je Angebot
- C2 alle Positionen des Angebots (Beispiel 2613000461 mit Vordach_Rohr-1 und Vordach_Rohr-2), Angebotsnummer je Zeile
- C3 Werte aus der Kalkulation: Stückpreis/Preis wie im Angebots-PDF, HK, Marge, Einkauf, Gewicht, Zeiten HH:MM:SS
- C4 Umlaute, €, °, Semikolon, Anführungszeichen und Zeilenumbruch bleiben erhalten bzw. werden maskiert
- C5 leere Werte verschieben keine Spalten; Dezimalpunkt ohne Tausendertrennzeichen; UTF-8 mit BOM, CRLF
- C6 ZIP mit beiden Dateien, Export ändert die Datenbank nicht, wieder einlesbar
- C7 Formatfunktionen (Zeit, Datum, Zahlen als Text) und großes Angebot (Laufzeit)

Aufruf: python tests/test_csv_export.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import csv
import hashlib
import io
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import export  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

KOPF = ("Erstellungsdatum;Datum Kunde:;Kunden Nr.;Kunde:;Nachname;Versandzone:;Kundenanfrage:;Kommentar;"
        "Versandkosten;Feste Versandkosten;Versand inkl.;Lieferzeit;%Kunde Mat;%Kunde Arb.;%Fremdarb.;"
        "Bearbeitungszeit;Gesamtzeit;Restblech min.€;Preis;Kundenkurzbez.;Position;Anrede;%Aufschlag;"
        "Rabatt(Euros);Aufrunden;Angebot erstellt von")
POS = ("Angebot;Art;ArtikelNr.;Pos.;Pos.Nr.;Bestellt;Anzahl Tafeln;Format;Arb.;Anz. Baugruppe;Menge;Stückpr.;"
       "Preis;Preis geändert;Werkstoff;Werkstofftyp;Dicke;Fläche;Gew.;Umfang;Maschine;Schneiden;Date;L.;B.;"
       "Artikeltext;Bearbeitungszeit;Gesamtzeit;zum Schneiden;Gesamt HK(€);Marge Netto%;Kommentar;Preis/Kg;"
       "Einsatzgewicht;HK();Marge Netto();Gesamt Einkauf();Gesamt Einkauf(Kg);Verschnitt;Liste der Arbeitsgänge")


def ok(text):
    print("OK    ", text)


def lesen(daten):
    """CSV-Bytes -> Liste von Zeilen (prüft BOM und CRLF)."""
    assert daten[:3] == b"\xef\xbb\xbf", daten[:10]
    text = daten.decode("utf-8-sig")
    assert text.split("\n", 1)[0].endswith("\r"), text[:200]       # Zeilenende CRLF
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=";"))


def euro(t):
    return float(t) if t else None


def db_stand(pfad):
    return hashlib.sha256(Path(pfad).read_bytes()).hexdigest()


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db_pfad = tmp / "rohrlaser.db"
db = Datenbank(db_pfad)
fenster = Hauptfenster(db, tmp, stumm=True)
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))

# Testdaten wie im Beispiel von Patrick: Rechteckrohr 120x60x3, Angebot 2613000461
vorlage = next(z for z in db.zeilen("profile") if z["profil_id"] == "RE 120x60x4")
db.neu("profile", {**{n: v for n, v in vorlage.items() if n not in ("id", "uid")}, "profil_id": "RE 120x60x3",
                   "wand": 3.0})
for z in db.zeilen("preise"):
    if z["profil_id"] == "RE 120x60x4":
        db.neu("preise", {**{n: v for n, v in z.items() if n not in ("id", "uid")}, "profil_id": "RE 120x60x3"})
db.neu("kunden", dict(kundennr="10916", name="AP Glas GmbH", ansprechpartner="Jürgen Weiß",
                      lieferbedingung="Ab Werk", plz_ort="33129 Delbrück"))
a = db.angebot_neu(dict(nummer="2613000461", kunde="AP Glas GmbH", kundennr="10916", maschine="T11",
                        kundenreferenz="Bestellung Rohrlaserteile", bemerkung='Text mit ; und "Zitat"\nzweite Zeile',
                        lieferzeit_art="Wochen", lieferzeit_wert="2", fracht=50.0, datum="2026-10-23"))
db.position_neu(a, dict(pos=1, artikel="Vordach_Rohr-1", profil_id="RE 120x60x3", werkstoff_id="S235-10219",
                        laenge=2958, stueck=2, schneidweg=904, einstiche=2))
db.position_neu(a, dict(pos=2, artikel="Vordach_Rohr-2", bezeichnung="Träger 90° geschweißt", profil_id="RE 120x60x3",
                        werkstoff_id="S235-10219", laenge=1400, stueck=4, schneidweg=1155, einstiche=2,
                        gewinde="4xM6"))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()

# ------------------------------------------------------------------ C1/C2 Kopf, Spalten, Positionen
vorher = db_stand(db_pfad)
pfad = s.csv_export()
assert pfad and pfad.name == "Angebot_2613000461.zip" and pfad.parent == tmp / "Ablage" / "2613000461 AP Glas GmbH", pfad   # Ordner je Angebot
with zipfile.ZipFile(pfad) as z:
    assert sorted(z.namelist()) == ["Angebotskopf.csv", "Angebotspositionen.csv"], z.namelist()
    kopf = lesen(z.read("Angebotskopf.csv"))
    pos = lesen(z.read("Angebotspositionen.csv"))
assert ";".join(kopf[0]) == KOPF and len(kopf[0]) == 26 and ";".join(export.KOPF_SPALTEN) == KOPF
assert ";".join(pos[0]) == POS and len(pos[0]) == 40 and ";".join(export.POSITION_SPALTEN) == POS
assert len(kopf) == 2, kopf                         # genau eine Zeile je Angebot
assert all(len(z) == 26 for z in kopf) and all(len(z) == 40 for z in pos)
ok("C1 Kopfzeilen exakt, 26 bzw. 40 Spalten, eine Kopfzeile je Angebot")
K = dict(zip(kopf[0], kopf[1]))
P = [dict(zip(pos[0], z)) for z in pos[1:]]
assert [p["ArtikelNr."] for p in P] == ["Vordach_Rohr-1", "Vordach_Rohr-2"]
assert all(p["Angebot"] == "2613000461" for p in P) and [p["Pos."] for p in P] == ["1", "2"]
assert [p["Art"] for p in P] == ["1", "2"]
ok("C2 alle Positionen des Angebots, jede mit der Angebotsnummer verknüpft")

# ------------------------------------------------------------------ C3 Werte aus der Kalkulation
zeilen, summen = s._rechnung()
ang = s.angebot_daten()
assert K["Kunden Nr."] == "10916" and K["Kunde:"] == "AP Glas GmbH" and K["Nachname"] == "Jürgen Weiß"
assert K["Versandzone:"] == "Ab Werk" and K["Kundenanfrage:"] == "Bestellung Rohrlaserteile"
assert K["Datum Kunde:"] == "23.10.2026" and len(K["Erstellungsdatum"]) == 10 and K["Erstellungsdatum"][2] == "."
assert K["Versandkosten"] == "50.00" and K["Feste Versandkosten"] == "True" and K["Versand inkl."] == "False"
assert K["Lieferzeit"].startswith("ca. 2 Wochen nach Auftragseingang") and "Lieferzeit" not in K["Lieferzeit"], K
assert euro(K["Preis"]) == ang["netto"], (K["Preis"], ang["netto"])
assert K["Restblech min.€"] == "" or euro(K["Restblech min.€"]) > 0
assert K["Aufrunden"] == "+0.01" and K["Kundenkurzbez."] == K["Anrede"] == K["Rabatt(Euros)"] == ""
for p, z, az in zip(P, [x for x in zeilen if x], [x for x in ang["zeilen"] if x["art"] == "teil"]):
    assert euro(p["Stückpr."]) == az["preis"] and euro(p["Preis"]) == az["gesamt"], (p, az)   # wie Angebots-PDF
    assert abs(euro(p["Gesamt HK(€)"]) - z["herstell_position"]) < 0.005
    assert abs(euro(p["HK()"]) - z["herstell_teil"]) < 0.005
    hk = euro(p["Gesamt HK(€)"])
    assert abs(euro(p["Marge Netto()"]) - (euro(p["Preis"]) - z["herstell_position"])) < 0.006
    assert p["Marge Netto%"].endswith(" %") and abs(euro(p["Marge Netto%"][:-2])
                                                    - 100 * (az["gesamt"] - z["herstell_position"]) / z["herstell_position"]) < 0.06
    assert abs(euro(p["Gesamt Einkauf()"]) - z["material_position"]) < 0.005 and euro(p["Gesamt Einkauf()"]) > 0
    assert p["Werkstoff"] == "Stahl" and p["Werkstofftyp"] == "S235 EN10219" and p["Dicke"] == "3"
    assert p["Maschine"] == "T11" and p["Date"] == "23.10.2026" and p["Menge"] in ("2", "4")
    assert p["Bearbeitungszeit"].count(":") == 2 and len(p["Bearbeitungszeit"]) == 8
    assert p["Gesamtzeit"] > p["Bearbeitungszeit"]
    assert euro(p["Einsatzgewicht"]) >= euro(p["Gew."]) > 0 and p["Verschnitt"].endswith("%")
    assert abs(euro(p["Gesamt Einkauf(Kg)"]) - euro(p["Einsatzgewicht"]) * int(p["Menge"])) < 0.01
    assert p["Liste der Arbeitsgänge"].startswith("Profile [Rechteckrohr 120x60x3]")
p1, p2 = P
assert p1["L."] == "2958" and p1["Umfang"] == "904" and p1["Fläche"] == "1.034", p1      # (360 − (8 − 2π) × 6) mm × 2,958 m
# (Umfang mit Außenradius 6 mm nach Norm)
assert "Gewinde [4xM6]" in p2["Liste der Arbeitsgänge"] and "Gewinde 4xM6" in p2["Artikeltext"]
# Zeiten im Kopf = Summe der Positionen
sek = [sum(int(x) * f for x, f in zip(t.split(":"), (3600, 60, 1))) for t in (p1["Bearbeitungszeit"], p2["Bearbeitungszeit"])]
ges = [sum(int(x) * f for x, f in zip(t.split(":"), (3600, 60, 1))) for t in (p1["Gesamtzeit"], p2["Gesamtzeit"])]
kz = lambda t: sum(int(x) * f for x, f in zip(t.split(":"), (3600, 60, 1)))  # noqa: E731
assert abs(kz(K["Bearbeitungszeit"]) - sum(sek)) <= 1 and abs(kz(K["Gesamtzeit"]) - sum(ges)) <= 1, K
ok("C3 Werte aus Kunde, Kopf und Kalkulation; Stückpreis/Preis wie Angebots-PDF, Zeiten HH:MM:SS, Kopfzeiten = Summe")

# ------------------------------------------------------------------ C4 Sonderzeichen und Maskierung
roh = zipfile.ZipFile(pfad).read("Angebotskopf.csv").decode("utf-8-sig")
assert '"Text mit ; und ""Zitat""\nzweite Zeile"' in roh, roh
assert K["Kommentar"] == 'Text mit ; und "Zitat"\nzweite Zeile'
assert "Restblech min.€" in roh and "Jürgen Weiß" in roh
ok("C4 Semikolon, Anführungszeichen, Zeilenumbruch maskiert; Umlaute, ß, € erhalten")

# ------------------------------------------------------------------ C5 leere Werte, Zahlenformat
assert p1["Pos.Nr."] == "" and p1["Anzahl Tafeln"] == "" and p1["B."] == ""
assert all("," not in p[n] for p in P for n in ("Stückpr.", "Preis", "Gesamt HK(€)", "Gew.", "Einsatzgewicht"))
assert all("." in p["Preis"] and len(p["Preis"].split(".")[1]) == 2 for p in P)
assert export.zahl(12345.5, 2) == "12345.50"          # kein Tausendertrennzeichen
ok("C5 leere Felder ohne Verschiebung, Dezimalpunkt ohne Tausendertrennzeichen, Beträge mit 2 Stellen")

# ------------------------------------------------------------------ C6 einzelne Dateien, Datenbank unverändert
pk = s.csv_kopf()
pp = s.csv_positionen()
assert pk.name == "2613000461 Angebotskopf.csv" and pp.name == "2613000461 Angebotspositionen.csv"
assert lesen(pk.read_bytes()) == kopf and lesen(pp.read_bytes()) == pos
assert db_stand(db_pfad) == vorher, "Export hat die Datenbank verändert"
assert not list((tmp / "Ablage").rglob(".export_*"))
ok("C6 ZIP mit beiden Dateien, einzelne CSV gleich, Datenbank unverändert, wieder einlesbar")

# ------------------------------------------------------------------ C7 Formate, leeres Angebot, großes Angebot
assert export.zeit(83) == "00:01:23" and export.zeit(2697) == "00:44:57" and export.zeit(90000) == "25:00:00"
assert export.zeit(None) == "" and export.zeit("x") == "" and export.zeit(-1) == ""
assert export.datum("2026-10-23T14:05:00") == "23.10.2026" and export.datum("##########") == "" and export.datum(None) == ""
assert export.zahl("12,5") == "12.5" and export.zahl("1234.5", 2) == "1234.50" and export.zahl(2958.0) == "2958"
assert export.zahl(None) == "" and export.zahl("abc") == "" and export.geld(0.005) == "0.01"
leer = db.angebot_neu(dict(kunde="Ohne Positionen", maschine="T11"))
s_leer = fenster.angebot_oeffnen(leer)
assert s_leer.csv_export() is None
try:
    export.csv_bytes(export.KOPF_SPALTEN, [["zu kurz"]])
    raise AssertionError("falsche Spaltenzahl nicht erkannt")
except ValueError:
    pass
gross = db.angebot_neu(dict(nummer="G-1", kunde="Groß", maschine="T11"))
for i in range(200):
    db.position_neu(gross, dict(pos=i + 1, artikel=f"T{i}", profil_id="RE 60x40x3", werkstoff_id="S235-10219",
                                laenge=300 + 50 * (i % 8), stueck=1 + i % 3, schneidweg=400, einstiche=2))
sg = fenster.angebot_oeffnen(gross)
assert sg.optimieren()
t0 = time.time()
pg = sg.csv_export()
dauer = time.time() - t0
with zipfile.ZipFile(pg) as z:
    assert len(lesen(z.read("Angebotspositionen.csv"))) == 201
assert dauer < 30, dauer
ok(f"C7 Formate HH:MM:SS/TT.MM.JJJJ, Text-Zahlen, leeres Angebot abgewiesen, 200 Positionen in {dauer:.1f} s")

print("OK: CSV-Export Angebotskopf/Angebotspositionen")
