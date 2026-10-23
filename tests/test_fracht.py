"""Prüft das Frachtkosten-Modul (F1–F16): PLZ-Zonen, Tarifmodelle, Ladehilfsmittel, Zuschläge, Diesel, Mindestfracht,
Tarifwahl und -gültigkeit, Währung, Rundung, Historie nach Tarifänderung, fehlende Daten, CSV und Oberfläche.
Alle Tarifwerte hier sind erfundene Testwerte.

Aufruf: python tests/test_fracht.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from rohrlaser import fracht  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.fracht_daten import FRACHT_TABELLE, plz_csv, plz_csv_lesen  # noqa: E402
from rohrlaser.stammdaten import Kontext, pruefen  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


def gleich(a, b, text=""):
    assert a is not None and abs(a - b) < 0.005, f"{text}: {a} statt {b}"


def daten(**extra):
    """Kleiner Testdatensatz: Zonen A (Bereich), B (Präfix), S (Standard), I (Insel), Tarife G (Gewicht), P (Palette)."""
    d = dict(
        laender=[dict(land="DE", plz_laenge=5), dict(land="CH", plz_laenge=4, waehrung="CHF")],
        zonen=[dict(zone_id="A", bezeichnung="Nah", land="DE", km=40), dict(zone_id="B", bezeichnung="Fern", land="DE"),
               dict(zone_id="S", bezeichnung="Standard", land="DE", standard="ja"),
               dict(zone_id="I", bezeichnung="Insel", land="DE", art="Insel"),
               dict(zone_id="X", bezeichnung="alt", land="DE", aktiv="nein"),
               dict(zone_id="CH", bezeichnung="Schweiz", land="CH", standard="ja")],
        plz=[dict(land="DE", plz_von="01000", plz_bis="09999", zone_id="A"),
             dict(land="DE", plz_von="8*", zone_id="B"),
             dict(land="DE", plz_von="80331", zone_id="A"),                      # einzelne PLZ vor Präfix
             dict(land="DE", plz_von="25980", plz_bis="25999", zone_id="I"),
             dict(land="DE", plz_von="70000", plz_bis="70999", zone_id="X")],
        dienstleister=[dict(dienstleister_id="D1"), dict(dienstleister_id="D2")],
        tarife=[dict(tarif_id="G", modell="Gewichtstarif", dienstleister="D1", versandart="Stückgut", mindestfracht=30,
                     rundung_kg=1, laender="DE"),
                dict(tarif_id="P", modell="Palettentarif", dienstleister="D1", versandart="Palette", laender="DE")],
        preise=[dict(tarif_id="G", bezug="kg", bis=100, preis=40), dict(tarif_id="G", bezug="kg", bis=250, preis=60),
                dict(tarif_id="G", bezug="kg", bis=500, preis=90), dict(tarif_id="G", bezug="kg", bis=1000, preis=150),
                dict(tarif_id="G", bezug="100 kg", preis=16, preisart="je Einheit"),
                dict(tarif_id="G", zone_id="B", bezug="kg", bis=500, preis=120),
                dict(tarif_id="G", zone_id="B", bezug="kg", bis=1000, preis=200),
                dict(tarif_id="P", bezug="Stellplatz", bis=1, preis=50, preisart="je Einheit"),
                dict(tarif_id="P", bezug="Stellplatz", bis=3, preis=45, preisart="je Einheit"),
                dict(tarif_id="P", bezug="Stellplatz", bis=6, preis=40, preisart="je Einheit"),
                dict(tarif_id="P", bezug="Stellplatz", bis=None, preis=None, preisart="je Einheit"),
                dict(tarif_id="P", bezug="Ladungsträger", lht_art="Gitterbox", bis=3, preis=60, preisart="je Einheit")],
        lht=[dict(lht_id="EUR", art="Europalette", laenge=1200, breite=800, hoehe=1000, eigengewicht=25, nutzlast=1000,
                  max_laenge=1400, stellplaetze=1),
             dict(lht_id="GB", art="Gitterbox", laenge=1240, breite=835, hoehe=970, eigengewicht=85, nutzlast=1500,
                  stapelbar="ja", stapelfaktor=3, max_laenge=1200),
             dict(lht_id="LG", art="Langgut", laenge=6500, breite=800, hoehe=300, eigengewicht=30, nutzlast=2000,
                  max_laenge=6500, stellplaetze=3)],
        zuschlaege=[], dieselpreise=[], dieselstaffel=[], waehrungen=[])
    for k, v in extra.items():
        d[k] = v
    return d


def s(**w):
    return dict(dict(land="DE", plz="05000", versandart="Stückgut", netto=0, datum="2026-10-20"), **w)


# ------------------------------------------------------------------ F1 PLZ -> Zone
d = daten()
assert fracht.zone_finden(d, "DE", "05000")["zone"]["zone_id"] == "A"
assert fracht.zone_finden(d, "DE", "01000")["zone"]["zone_id"] == "A", "Grenze unten, führende Null"
assert fracht.zone_finden(d, "DE", "09999")["zone"]["zone_id"] == "A", "Grenze oben"
assert fracht.zone_finden(d, "DE", "81234")["zone"]["zone_id"] == "B", "Präfix 8*"
assert fracht.zone_finden(d, "DE", "80331")["zone"]["zone_id"] == "A", "einzelne PLZ vor Präfix"
assert fracht.zone_finden(d, "DE", " 25 990 ")["zone"]["zone_id"] == "I", "Leerzeichen"
k = dict(d, plz=d["plz"] + [dict(land="DE", plz_von="81000", plz_bis="81999", zone_id="S", kundennr="K1")])
assert fracht.zone_finden(k, "DE", "81234", kundennr="K1")["zone"]["zone_id"] == "S", "Kundenregel vor allgemein"
assert fracht.zone_finden(k, "DE", "81234", kundennr="K2")["zone"]["zone_id"] == "B"
v = dict(d, plz=d["plz"] + [dict(land="DE", plz_von="05000", plz_bis="05999", zone_id="B", richtung="Versand")])
assert fracht.zone_finden(v, "DE", "05500", "Versand")["zone"]["zone_id"] == "B", "Versandregel, engerer Bereich"
assert fracht.zone_finden(v, "DE", "05500", "Empfang")["zone"]["zone_id"] == "A", "Versandregel gilt nicht für Empfang"
ok("F1 PLZ-Zuordnung: Bereich mit Grenzen und führender Null, Präfix, einzelne PLZ vor Präfix, Kunde vor allgemein, "
   "Versand/Empfang getrennt")

# ------------------------------------------------------------------ F2 nicht zugeordnete PLZ
z = fracht.zone_finden(d, "DE", "30000")
assert z["status"] == "standard" and z["zone"]["zone_id"] == "S" and "keiner Zone zugeordnet" in z["text"]
z = fracht.zone_finden(d, "DE", "70500")
assert z["status"] == "standard" and z["hinweise"], "inaktive Zone wird nicht verwendet, Hinweis"
ohne_std = dict(d, zonen=[x for x in d["zonen"] if x["zone_id"] != "S"])
z = fracht.zone_finden(ohne_std, "DE", "30000")
assert z["status"] == "fehler" and z["zone"] is None and "keine Standardzone" in z["text"]
e = fracht.rechnen(ohne_std, s(plz="30000", netto=50))
assert e["status"] == "fehler" and e["gesamt"] is None and "keiner Zone" in e["fehler"][0]
e = fracht.rechnen(d, s(plz="30000", netto=50))
assert e["gesamt"] is not None and any("keiner Zone zugeordnet" in w for w in e["warnungen"]), "Warnung sichtbar"
mehr = dict(d, plz=d["plz"] + [dict(land="DE", plz_von="03000", plz_bis="03999", zone_id="B"),
                               dict(land="DE", plz_von="03000", plz_bis="03999", zone_id="S", richtung="Empfang")])
z = fracht.zone_finden(mehr, "DE", "03500")
assert z["status"] == "mehrdeutig" and "Zone B" in z["text"] and "Zone S" in z["text"], z
assert fracht.rechnen(mehr, s(plz="03500", netto=50))["gesamt"] is None, "mehrdeutig: keine stille Wahl"
mehr["plz"][-1]["prioritaet"] = 1
assert fracht.zone_finden(mehr, "DE", "03500")["zone"]["zone_id"] == "S", "Priorität löst den Gleichstand"
assert fracht.zone_finden(d, "DE", "")["status"] == "fehler"
ok("F2 Nicht zugeordnete PLZ: Standardzone mit Warnung, ohne Standardzone Fehler, inaktive Zone übergangen, "
   "mehrdeutige Regeln gemeldet bis Priorität vergeben")

# ------------------------------------------------------------------ F3 Gewichtstarif und Grenzen
for kg, soll in ((100, 40), (100.4, 60), (250, 60), (500, 90), (1000, 150), (1000.2, 1001 * 16 / 100)):
    e = fracht.rechnen(d, s(netto=kg))
    gleich(e["gesamt"], soll, f"{kg} kg")
e = fracht.rechnen(d, s(netto=1000.2))
assert e["gewicht"]["frachtpflichtig"] == 1001 and "aufgerundet" in e["gewicht"]["erklaerung"]
e = fracht.rechnen(d, s(plz="81234", netto=400))
gleich(e["gesamt"], 120, "Zonenpreis vor 'alle Zonen'")
e = fracht.rechnen(d, s(plz="81234", netto=1200))
assert e["gesamt"] is None and any("über der letzten Stufe" in f for f in e["fehler"]), e["fehler"]
ok("F3 Gewichtstarif: Stufen genau auf der Grenze und knapp darüber, über 1.000 kg je 100 kg, Aufrunden, "
   "Zonenpreise vor allgemeinen, über der letzten Zonenstufe = individuelle Berechnung")

# ------------------------------------------------------------------ F4 Paletten und Gitterboxen
sp = s(versandart="Palette", netto=600)
for n, soll in ((1, 50), (2, 90), (3, 135), (6, 240)):
    e = fracht.rechnen(d, dict(sp, lht=[dict(lht_id="EUR", anzahl=n)]))
    gleich(e["gesamt"], soll, f"{n} Paletten")
e = fracht.rechnen(d, dict(sp, lht=[dict(lht_id="EUR", anzahl=7)]))
assert e["gesamt"] is None and any("individuelle Berechnung" in f for f in e["fehler"]), "mehr als 6: individuell"
e = fracht.rechnen(d, dict(sp, lht=[dict(lht_id="GB", anzahl=2)]))
gleich(e["gesamt"], 120, "Gitterbox eigener Preis")
assert e["lht"]["stellplaetze"] == 1, "3 Gitterboxen stapelbar je Stellplatz"
e = fracht.rechnen(d, dict(sp, lht=[]))
assert e["gesamt"] is None and any("keine Ladehilfsmittel" in f for f in e["fehler"])
ok("F4 Palettentarif je Stellplatz (1 / 2–3 / 4–6 / mehr = individuell), Gitterbox mit eigenem Preis, Stapelung, "
   "Palettentarif ohne Ladungsträger = Fehler")

# ------------------------------------------------------------------ F5 gemischte Ladehilfsmittel
e = fracht.rechnen(d, dict(sp, lht=[dict(lht_id="EUR", anzahl=2), dict(lht_id="GB", anzahl=1)]))
gleich(e["gesamt"], 2 * 45 + 60, "Paletten und Gitterbox getrennt")
assert [z["text"] for z in e["zeilen"]] == ["Grundfracht Stellplatz", "Grundfracht Gitterbox"]
lw = e["lht"]
assert lw["anzahl"] == 3 and lw["stellplaetze"] == 3 and abs(lw["eigengewicht"] - 135) < EPS
assert abs(lw["volumen"] - (2 * 1.2 * 0.8 * 1.0 + 1.24 * 0.835 * 0.97)) < 1e-9
gleich(e["gewicht"]["brutto"], 600 + 135, "Brutto = Netto + Eigengewicht")
e = fracht.rechnen(d, dict(sp, lht=[dict(lht_id="EUR", anzahl=1), dict(lht_id="LG", anzahl=1)]))
gleich(e["gesamt"], 4 * 40, "Langgut zählt 3 Stellplätze")
ohne_gb = dict(d, preise=[p for p in d["preise"] if p.get("lht_art") != "Gitterbox"])
ohne_allg = dict(ohne_gb, preise=[dict(p, lht_art="Europalette") if p["tarif_id"] == "P" else p for p in ohne_gb["preise"]])
e = fracht.rechnen(ohne_allg, dict(sp, lht=[dict(lht_id="EUR", anzahl=1), dict(lht_id="GB", anzahl=1)]))
assert e["gesamt"] is None and any("ohne Preis für Gitterbox" in f for f in e["fehler"]), e["fehler"]
e = fracht.rechnen(d, dict(sp, lht=[dict(lht_id="EUR", anzahl=1, gewicht=400), dict(lht_id="GB", anzahl=1, gewicht=300)]))
assert e["gewicht"]["brutto"] == 700 and "je Ladungsträger" in e["gewicht"]["quelle"]
v, h = fracht.packvorschlag([(1500, 1000), (300, 6000)], d["lht"], "EUR", "LG")
assert v == [dict(lht_id="EUR", anzahl=2), dict(lht_id="LG", anzahl=1)] and not h, v
v, h = fracht.packvorschlag([(100, 7000)], d["lht"], "EUR", "LG")
assert v == [dict(lht_id="LG", anzahl=1)] and h, "zu lang auch für Langgut: Hinweis"
assert fracht.packvorschlag([(100, 500)], d["lht"], "FEHLT", "LG")[0] == []
ok("F5 Kombination: Paletten + Gitterbox + Langgut mit Anzahl, Stellplätzen, Volumen, Eigengewicht; fehlender "
   "Preis für eine Art = Fehler statt 0 €; Bruttogewicht je Ladungsträger; Packvorschlag nach Gewicht und Länge")

# ------------------------------------------------------------------ F6 Dieselzuschlag
leist = dict(zuschlag_id="AV", typ="Avisierung", berechnung="€ je Sendung", wert=10, bedingung="nur wenn gewählt")
for basis, ids, soll in (("Grundfracht", None, 0.1 * 90), ("Grundfracht + Leistungszuschläge", None, 0.1 * 100),
                         ("gewählte Zuschläge", "AV", 0.1 * 10), ("gewählte Zuschläge", "Grundfracht, AV", 0.1 * 100)):
    dz = daten(zuschlaege=[leist, dict(zuschlag_id="DI", typ="Diesel", berechnung="%", basis=basis, basis_liste=ids,
                                       wert=10)])
    e = fracht.rechnen(dz, s(netto=400, leistungen={"AV": 1}))
    diesel = next(z for z in e["zuschlaege"] if z["zuschlag_id"] == "DI")
    gleich(diesel["betrag"], soll, basis)
    assert "auf" in diesel["erklaerung"]
dz = daten(zuschlaege=[dict(zuschlag_id="DF", typ="Diesel", berechnung="€ je Sendung", wert=7.5)])
gleich(fracht.rechnen(dz, s(netto=400))["gesamt"], 97.5, "Diesel als Festbetrag")
staffel = [dict(zuschlag_id="DS", preis_ab=1.40, wert=5), dict(zuschlag_id="DS", preis_ab=1.60, wert=8),
           dict(zuschlag_id="DS", preis_ab=1.80, wert=11)]
ds = [dict(zuschlag_id="DS", typ="Diesel", berechnung="Dieselstaffel", basis="Grundfracht")]
for preis, soll in ((1.59, 5), (1.60, 8), (1.95, 11)):
    dz = daten(zuschlaege=ds, dieselstaffel=staffel, dieselpreise=[dict(datum="2026-10-01", preis=preis),
                                                                   dict(datum="2026-11-01", preis=9.99)])
    e = fracht.rechnen(dz, s(netto=400))
    gleich(e["zuschlaege"][0]["betrag"], 90 * soll / 100, f"Dieselpreis {preis}")
dz = daten(zuschlaege=ds, dieselstaffel=staffel)
e = fracht.rechnen(dz, s(netto=400))
assert not e["zuschlaege"] and any("kein Dieselpreis" in w for w in e["warnungen"]), "kein erfundener Dieselpreis"
dz = daten(zuschlaege=ds, dieselstaffel=staffel, dieselpreise=[dict(datum="2026-10-01", preis=1.2)])
assert any("unter der ersten Schwelle" in t for t in fracht.rechnen(dz, s(netto=400))["nicht_angewendet"])
ok("F6 Diesel: % auf Grundfracht, auf Grundfracht + Leistungen, auf gewählte Zuschläge, Festbetrag, Dieselstaffel "
   "mit Schwellen und Preis am Datum; ohne Dieselpreis Warnung statt erfundenem Wert")

# ------------------------------------------------------------------ F7 Mindestfracht und Mindermenge
e = fracht.rechnen(daten(tarife=[dict(d["tarife"][0], mindestfracht=55)] + d["tarife"][1:]), s(netto=50))
gleich(e["gesamt"], 55)
assert e["zeilen"][-1]["text"] == "Anhebung auf Mindestfracht" and abs(e["zeilen"][-1]["betrag"] - 15) < EPS
e = fracht.rechnen(daten(tarife=[dict(d["tarife"][0], mindestfracht=55, rabatt=10)] + d["tarife"][1:]), s(netto=400))
gleich(e["gesamt"], 81, "Rabatt 10 % auf 90")
e = fracht.rechnen(daten(tarife=[dict(d["tarife"][0], mindestfracht=85, rabatt=10)] + d["tarife"][1:]), s(netto=400))
gleich(e["gesamt"], 85, "Rabatt unterschreitet Mindestfracht nicht")
mm = daten(zuschlaege=[dict(zuschlag_id="MM", typ="Mindermenge", berechnung="€ je Sendung", wert=12,
                            bedingung="Gewicht unter", grenze=30)])
gleich(fracht.rechnen(mm, s(netto=20))["gesamt"], 52)
e = fracht.rechnen(mm, s(netto=30))
gleich(e["gesamt"], 40)
assert any("nicht unter" in t for t in e["nicht_angewendet"])
ok("F7 Mindestfracht als eigene Zeile, Rabatt vor Mindestfracht, Mindermengenzuschlag nur unter der Gewichtsgrenze")

# ------------------------------------------------------------------ F8 mehrere Zuschläge
zus = [dict(zuschlag_id="DI", typ="Diesel", berechnung="%", basis="Grundfracht", wert=12),
       dict(zuschlag_id="DI-D1", typ="Diesel", berechnung="%", basis="Grundfracht", wert=9, dienstleister="D1"),
       dict(zuschlag_id="MA", typ="Maut", berechnung="€ je 100 kg", wert=1.5, mindest=5),
       dict(zuschlag_id="LG", typ="Langgut / Überlänge", berechnung="€ je Sendung", wert=20, bedingung="Teillänge über",
            grenze=3000),
       dict(zuschlag_id="IN", typ="Insel- und Randgebiet", berechnung="€ je Sendung", wert=30,
            bedingung="Zonenart Insel/Randgebiet/Sondergebiet"),
       dict(zuschlag_id="HB", typ="Hebebühne", berechnung="€ je Sendung", wert=25, bedingung="nur wenn gewählt"),
       dict(zuschlag_id="WZ", typ="Wartezeit", berechnung="€ je Stunde", wert=40, bedingung="nur wenn gewählt"),
       dict(zuschlag_id="EN", typ="Energie", berechnung="%", basis="Grundfracht + Leistungszuschläge", wert=50,
            hoechst=20),
       dict(zuschlag_id="AB", typ="Express", berechnung="€ je Sendung", wert=99, gueltig_bis="2026-01-31"),
       dict(zuschlag_id="AUS", typ="Gefahrgut", berechnung="€ je Sendung", wert=99, aktiv="nein")]
dz = daten(zuschlaege=zus)
e = fracht.rechnen(dz, s(plz="25990", netto=400, max_laenge=6000, leistungen={"HB": 1, "WZ": 1.5}))
b = {z["zuschlag_id"]: z["betrag"] for z in e["zuschlaege"]}
assert set(b) == {"DI-D1", "MA", "LG", "IN", "HB", "WZ", "EN"}, b
gleich(b["DI-D1"], 90 * 0.09, "Diesel des Dienstleisters überdeckt den allgemeinen")
gleich(b["MA"], 6.0, "Maut 4 × 1,50")
gleich(b["WZ"], 60, "1,5 h × 40")
gleich(b["EN"], 20, "Höchstbetrag")
assert any("überdeckt" in t for t in e["nicht_angewendet"])
gleich(e["gesamt"], sum(z["betrag"] for z in e["zeilen"]))
e = fracht.rechnen(dz, s(netto=10))
assert {z["zuschlag_id"] for z in e["zuschlaege"]} == {"DI-D1", "MA", "EN"}
gleich(next(z["betrag"] for z in e["zuschlaege"] if z["zuschlag_id"] == "MA"), 5, "Mindestbetrag")
ok("F8 Mehrere Zuschläge: speziellerer Diesel überdeckt den allgemeinen, Maut mit Mindestbetrag, Überlänge, Insel, "
   "gewählte Leistungen, Stunden, Höchstbetrag; abgelaufene und inaktive Zuschläge wirken nicht")

# ------------------------------------------------------------------ F9 Tarifgültigkeit, -wechsel und -wahl
alt = dict(d["tarife"][0], gueltig_bis="2026-06-30")
neu = dict(d["tarife"][0], tarif_id="G2", gueltig_ab="2026-07-01")
dt = daten(tarife=[alt, neu, d["tarife"][1]], preise=d["preise"] + [dict(p, tarif_id="G2", preis=p["preis"] * 2)
                                                                     for p in d["preise"] if p["tarif_id"] == "G"])
assert fracht.rechnen(dt, s(netto=400, datum="2026-06-30"))["tarif"]["tarif_id"] == "G"
e = fracht.rechnen(dt, s(netto=400, datum="2026-07-01"))
assert e["tarif"]["tarif_id"] == "G2" and abs(e["gesamt"] - 180) < EPS
gleich(fracht.rechnen(dt, s(netto=400, datum="2026-07-01", tarif_id="G2"))["gesamt"], 180)
e = fracht.rechnen(dt, s(netto=400, datum="2026-07-01", tarif_id="G"))
assert e["gesamt"] is None and "nicht gültig" in e["fehler"][0], "von Hand gewählter Tarif außerhalb der Gültigkeit"
zwei = daten(tarife=[d["tarife"][0], dict(d["tarife"][0], tarif_id="G3")],
             preise=d["preise"] + [dict(p, tarif_id="G3") for p in d["preise"] if p["tarif_id"] == "G"])
e = fracht.rechnen(zwei, s(netto=400))
assert e["status"] == "auswahl" and e["gesamt"] is None and len(e["weitere_tarife"]) == 2, "keine stille Wahl"
zwei["tarife"][1]["prioritaet"] = 1
assert fracht.rechnen(zwei, s(netto=400))["tarif"]["tarif_id"] == "G3"
kt = daten(tarife=d["tarife"] + [dict(d["tarife"][0], tarif_id="GK", kundennr="K1", tarifart="Kundentarif")],
           preise=d["preise"] + [dict(p, tarif_id="GK", preis=p["preis"] - 10) for p in d["preise"] if p["tarif_id"] == "G"])
e = fracht.rechnen(kt, s(netto=400, kundennr="K1"))
assert e["tarif"]["tarif_id"] == "GK" and "Kundentarif" in e["tarif_grund"] and e["weitere_tarife"][0]["tarif_id"] == "G"
assert fracht.rechnen(kt, s(netto=400, kundennr="K2"))["tarif"]["tarif_id"] == "G"
rv = daten(tarife=d["tarife"] + [dict(d["tarife"][0], tarif_id="GR", tarifart="Rahmenvertrag", dienstleister="D2")],
           preise=d["preise"] + [dict(p, tarif_id="GR") for p in d["preise"] if p["tarif_id"] == "G"])
assert fracht.rechnen(rv, s(netto=400))["tarif"]["tarif_id"] == "GR", "Rahmenvertrag vor Standardtarif"
assert fracht.rechnen(rv, s(netto=400, dienstleister="D1"))["tarif"]["tarif_id"] == "G", "Frachtführer gewählt"
it = daten(tarife=d["tarife"] + [dict(d["tarife"][0], tarif_id="INT", tarifart="interner Verrechnungstarif",
                                      prioritaet=1)])
assert fracht.rechnen(it, s(netto=400))["tarif"]["tarif_id"] == "G", "interner Tarif nur ausdrücklich"
ok("F9 Tarifgültigkeit am Stichtag, Wechsel zum Folgetarif, gewählter ungültiger Tarif = Fehler, Gleichstand ohne "
   "stille Wahl, Priorität, Kundentarif vor Rahmenvertrag vor Standard, interne Tarife nur ausdrücklich")

# ------------------------------------------------------------------ F10 Land und Währung
ch = daten(tarife=d["tarife"] + [dict(tarif_id="CHT", modell="Gewichtstarif", laender="CH", waehrung="CHF")],
           preise=d["preise"] + [dict(tarif_id="CHT", bezug="kg", bis=1000, preis=100)])
e = fracht.rechnen(ch, s(land="CH", plz="8000", netto=200))
assert e["gesamt"] is None and any("Umrechnungskurs" in f for f in e["fehler"]), "fehlender Kurs"
ch["waehrungen"] = [dict(waehrung="CHF", kurs=1.05, stand="2026-10-01")]
e = fracht.rechnen(ch, s(land="CH", plz="8000", netto=200))
gleich(e["gesamt"], 105, "100 CHF × 1,05")
assert e["tarif"]["tarif_id"] == "CHT" and "CHF" in e["zeilen"][0]["erklaerung"]
assert fracht.rechnen(ch, s(land="CH", plz="8000", netto=200, versandart=None))["tarif"]["tarif_id"] == "CHT", \
    "Tarife für DE gelten nicht in CH"
ok("F10 Auslandstarif für CH mit eigener Standardzone, Umrechnung CHF → EUR mit Kurs, fehlender Kurs = Fehler")

# ------------------------------------------------------------------ F12 Rundung
dr = daten(preise=[dict(tarif_id="G", bezug="kg", preis=0.3333, preisart="je Einheit")],
           tarife=[dict(d["tarife"][0], rundung_kg=None, mindestfracht=None)],
           zuschlaege=[dict(zuschlag_id="D", typ="Diesel", berechnung="%", basis="Grundfracht", wert=7.25),
                       dict(zuschlag_id="M", typ="Maut", berechnung="€ je kg", wert=0.0125)])
e = fracht.rechnen(dr, s(netto=123.4))
for zl in e["zeilen"]:
    assert zl["betrag"] == round(zl["betrag"], 2)
assert e["gesamt"] == round(sum(zl["betrag"] for zl in e["zeilen"]), 2), "Summe = Summe der ausgewiesenen Zeilen"
gleich(e["zeilen"][0]["betrag"], 41.13, "123,4 × 0,3333 = 41,12922")
gleich(e["zeilen"][1]["betrag"], 1.54, "123,4 × 0,0125 = 1,5425 kaufmännisch")
gleich(fracht.kaufm_runden(2.675, 2), 2.68, "halbe Cent kaufmännisch aufrunden")
ok(f"F12 Rundung: jede Zeile auf Cent, Gesamt = Summe der Zeilen ({fracht.euro(e['gesamt'])}), kaufmännisch")

# ------------------------------------------------------------------ F14 fehlende und widersprüchliche Daten
e = fracht.rechnen(daten(tarife=[]), s(netto=100))
assert e["gesamt"] is None and "Kein Tarif passt" in e["fehler"][0]
e = fracht.rechnen(daten(preise=[]), s(netto=100))
assert e["gesamt"] is None and any("keine Preise" in f for f in e["fehler"])
e = fracht.rechnen(d, s(netto=0))
assert e["gesamt"] is None and any("Kein Gewicht" in f for f in e["fehler"])
e = fracht.rechnen(daten(preise=[dict(tarif_id="G", bezug="Stellplatz", preis=10)]), s(netto=100))
assert e["gesamt"] is None and any("passt nicht zum Gewichtstarif" in w for w in e["warnungen"]) and e["fehler"]
e = fracht.rechnen(daten(preise=[dict(tarif_id="G", bezug="kg", bis=500, preis=None)]), s(netto=100))
assert e["gesamt"] is None and any("ohne Preis" in f for f in e["fehler"])
e = fracht.rechnen(daten(tarife=[dict(tarif_id="K", modell="Kombinationstarif")],
                         preise=[dict(tarif_id="K", bezug="km", preis=1, preisart="je Einheit")]), s(plz="81234", netto=1))
assert e["gesamt"] is None and any("Entfernung fehlt" in f for f in e["fehler"])
gleich(fracht.rechnen(daten(tarife=[dict(tarif_id="K", modell="Kombinationstarif")],
                            preise=[dict(tarif_id="K", bezug="Sendung", preis=20),
                                    dict(tarif_id="K", bezug="km", preis=1, preisart="je Einheit"),
                                    dict(tarif_id="K", bezug="kg", preis=0.1, preisart="je Einheit"),
                                    dict(tarif_id="K", bezug="Ladungsträger", preis=5, preisart="je Einheit")]),
                     s(netto=100, lht=[dict(lht_id="EUR", anzahl=2)]))["gesamt"], 20 + 40 + 0.1 * 150 + 10,
       "Kombinationstarif: Grundpreis + km + kg + Ladungsträger")
e = fracht.rechnen(d, s(netto=1500, lht=[dict(lht_id="EUR", anzahl=1)]))
assert any("Nutzlast" in w for w in e["warnungen"])
e = fracht.rechnen(d, s(netto=100, lht=[dict(lht_id="UNBEKANNT", anzahl=1)]))
assert any("unbekannt" in h for h in e["hinweise"])
k = Kontext(listen=dict(land=["DE"], zone=["A"], tarif=[]))
assert pruefen(FRACHT_TABELLE["fracht_plz"], dict(land="DE", plz_von="09999", plz_bis="01000", zone_id="A"),
               k).startswith("FEHLER: PLZ bis liegt vor")
assert pruefen(FRACHT_TABELLE["fracht_tarife"], dict(tarif_id="T", modell="Gewichtstarif", gueltig_ab="2026-05-01",
                                                     gueltig_bis="2026-04-01"), k).startswith("FEHLER")
assert pruefen(FRACHT_TABELLE["fracht_zuschlaege"], dict(zuschlag_id="Z", typ="Diesel", berechnung="%"),
               k).startswith("FEHLER: Prozentzuschlag braucht")
assert pruefen(FRACHT_TABELLE["fracht_zuschlaege"], dict(zuschlag_id="Z", typ="Diesel", berechnung="%",
                                                         basis="gewählte Zuschläge", basis_liste="Z"), k).startswith(
    "FEHLER: Zuschlag kann nicht auf sich selbst")
assert pruefen(FRACHT_TABELLE["fracht_preise"], dict(tarif_id="T", bezug="kg"), k).startswith("FEHLER: Tarif unbekannt")
e = fracht.rechnen(d, s(netto=400, lieferbedingung="ab Werk"))
assert e["gesamt"] == 0 and "trägt der Kunde" in e["hinweise"][-1]
ok("F14 Fehlende/widersprüchliche Daten: kein Tarif, keine Preise, kein Gewicht, falsches Modell, Preis leer, km "
   "fehlt, Nutzlast überschritten, unbekannter Ladungsträger, Prüfregeln der Tabellen; Lieferbedingung ab Werk = 0 €")

# ------------------------------------------------------------------ F15 CSV-Import und -Export
zeilen = [dict(land="DE", plz_von="01067", plz_bis="01099", zone_id="A", richtung=None, dienstleister=None,
               kundennr=None, prioritaet=2, bemerkung="Dresden; Test"),
          dict(land="DE", plz_von="8*", plz_bis=None, zone_id="B", richtung="Empfang", dienstleister="D1",
               kundennr="K1", prioritaet=None, bemerkung=None)]
text = plz_csv(zeilen)
assert text.startswith("﻿Land;PLZ von;PLZ bis;Zone")
gelesen, fehler = plz_csv_lesen(text, {"A", "B"}, {"DE"})
assert not fehler and gelesen == zeilen, (gelesen, fehler)
schlecht = text + "DE;12345;;Q;;;;;\r\nDE;;;A;;;;;\r\nDE;20000;10000;A;;;;;\r\nFR;75000;;A;;;;;\r\nDE;abc$;;A;;;;;\r\n"
gelesen, fehler = plz_csv_lesen(schlecht, {"A", "B"}, {"DE"})
assert len(gelesen) == 2 and len(fehler) == 5 and fehler[0].startswith("Zeile 4: Zone 'Q'"), fehler
gelesen, fehler = plz_csv_lesen("PLZ von,Zone\n10115,A\n", {"A"}, set())
assert gelesen[0]["plz_von"] == "10115" and gelesen[0]["land"] == "DE", "Komma als Trenner, Land Vorgabe DE"
ok("F15 CSV: Export → Import ergibt dieselben Zuordnungen (führende Nullen, Präfix, Semikolon im Text); fehlerhafte "
   "Zeilen werden mit Zeilennummer gemeldet und nicht übernommen")

# ------------------------------------------------------------------ Datenbank, Historie, Oberfläche
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert db.anzahl("fracht_tarife") == 2 and all("BEISPIEL" in t["tarif_id"] for t in db.zeilen("fracht_tarife"))
assert db.fracht_beispiele_laden() == 0, "Beispieldaten nicht doppelt"
fenster = Hauptfenster(db, tmp, stumm=True)
fenster.show()
fb = fenster.fracht
r = fb.rechner
r.plz.setText("80331")
r.versandart.setCurrentText("Stückgut")
r.netto.setValue(380)
e = r.rechnen()
assert e["gesamt"] is not None and "Beispieltarif" in e["warnungen"][0]
assert "Gesamtfrachtkosten" in r.anzeige.toPlainText() and "BEISPIEL-STUECKGUT" in r.anzeige.toPlainText()
nr = r.speichern()
gespeichert = e["gesamt"]

# ------------------------------------------------------------------ F13 Historie nach Tarifänderung
for p in db.zeilen("fracht_preise"):
    db.aendern("fracht_preise", p["id"], "preis", (p["preis"] or 0) * 3 if p["preis"] is not None else None)
r.neu_laden()
neu_e = r.rechnen()
assert neu_e["gesamt"] > gespeichert + 1, "aktuelle Rechnung mit geänderten Preisen"
h = db.fracht_kalkulationen()[0]
assert h["id"] == nr and abs(h["gesamt"] - gespeichert) < EPS and abs(h["ergebnis"]["gesamt"] - gespeichert) < EPS
snap = h["ergebnis"]["snapshot"]
nach = fracht.nachrechnen(snap, h["eingaben"])
gleich(nach["gesamt"], gespeichert, "mit gespeichertem Snapshot unverändert")
db.loeschen("fracht_tarife", [t["id"] for t in db.zeilen("fracht_tarife")])
gleich(fracht.nachrechnen(snap, h["eingaben"])["gesamt"], gespeichert, "auch nach Löschen des Tarifs")
assert fenster.bereich.oeffnen("av")
fb.zeigen(fb.historie)
assert fb.historie.tabelle.rowCount() == 1 and "Gesamtfrachtkosten" in fb.historie.anzeigen(0)
ok(f"F13 Historie: gespeicherte Kalkulation ({fracht.euro(gespeichert)}) bleibt nach Preisänderung und Löschen des "
   f"Tarifs gleich (aktuell {fracht.euro(neu_e['gesamt'])}); Anzeige aus dem Snapshot")

# Tarif als neue Version, CSV über die Oberfläche
db.fracht_beispiele_laden()
fb.zeigen(fb.tarife)
t = fb.tarife.tarife
t.ansicht.setCurrentIndex(t.filter.index(0, 0))
alt_id = t.ausgewaehlt()["tarif_id"]
assert fb.tarife.preise.filter.rowCount() > 0 and alt_id in fb.tarife.preis_titel.text()
neu_id = fb.tarife.neue_version("2027-01-01")
tarife = {x["tarif_id"]: x for x in db.zeilen("fracht_tarife")}
assert tarife[alt_id]["gueltig_bis"] == "2026-12-31" and tarife[neu_id]["gueltig_ab"] == "2027-01-01"
assert len([p for p in db.zeilen("fracht_preise") if p["tarif_id"] == neu_id]) == \
    len([p for p in db.zeilen("fracht_preise") if p["tarif_id"] == alt_id])
fb.zeigen(fb.zonen)
pfad = fb.zonen.csv_exportieren(str(tmp / "plz.csv"))
vorher = db.anzahl("fracht_plz")
assert fb.zonen.csv_importieren(pfad) == (0, vorher, [])
Path(tmp / "neu.csv").write_text("Land;PLZ von;Zone\nDE;33602;Z2\nDE;33-6;Z2\n", encoding="utf-8")
neu, ersetzt, fehler = fb.zonen.csv_importieren(str(tmp / "neu.csv"))
assert (neu, ersetzt, len(fehler)) == (1, 0, 1) and db.anzahl("fracht_plz") == vorher + 1
fb.zonen.test_plz.setText("33602")
assert "Zone Z2" in fb.zonen.test_ergebnis.text()
ok("Tarif als neue Version (alter gilt bis Vortag, Preise kopiert), CSV über die Oberfläche, PLZ testen")

# ------------------------------------------------------------------ F16 Oberfläche Desktop und schmales Fenster
fenster.bereich.sperren()
fb.zeigen(fb.zonen)
assert fb.gesperrt[fb.zonen].stapel.currentIndex() == 0, "Pflege gesperrt"
assert fb.unter.currentIndex() == 1
fb.unter.setCurrentIndex(0)
assert fb.rechner.isVisible(), "Rechner frei"
fenster.bereich.oeffnen("av")
for breite, hoehe in ((1024, 700), (1920, 1080)):
    fenster.resize(breite, hoehe)
    app.processEvents()
    tb = fb.unter.tabBar()
    assert sum(tb.tabRect(i).width() for i in range(tb.count())) <= tb.width() + 1, "alle Unterreiter sichtbar"
    for i in range(fb.unter.count()):
        fb.unter.setCurrentIndex(i)
        app.processEvents()
        for sa in fb.unter.currentWidget().findChildren(QScrollArea):
            if sa.isVisible() and sa.widgetResizable():
                assert not sa.horizontalScrollBar().isVisible(), (breite, fb.unter.tabText(i))
    fb.unter.setCurrentIndex(0)
    app.processEvents()
    soll = r.teiler.orientation().name == "Vertical"
    assert soll == (r.width() < 1100), (breite, r.width(), r.teiler.orientation())
ok("F16 Oberfläche bei 1024 × 700 und 1920 × 1080: alle sieben Unterreiter sichtbar, kein waagrechtes Scrollen, "
   "im schmalen Fenster Ergebnis unter der Eingabe; Pflege gesperrt, Rechner frei")

# ------------------------------------------------------------------ alte Datei (Schema 14) öffnen
fenster.close()
db.schliessen()
alt = tmp / "alt.db"
db2 = Datenbank(alt)
for t in [r[0] for r in db2.con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fracht_%'")]:
    db2.con.execute(f'DROP TABLE "{t}"')
db2.con.execute("PRAGMA user_version=14")
db2.con.commit()
db2.schliessen()
db3 = Datenbank(alt)
assert db3.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION >= 16
assert db3.anzahl("fracht_tarife") == 0 and db3.anzahl("fracht_kalkulationen") == 0, "alte Datei: leere Tabellen"
assert any(f"vor_Schema_{SCHEMA_VERSION}" in p.name for p in (alt.parent / "Sicherung").glob("*.db")), "Sicherung vor Umstellung"
assert {"plz", "land", "lieferbedingung"} <= {r[1] for r in db3.con.execute("PRAGMA table_info(kunden)")}
e = fracht.rechnen(db3.fracht_daten(), s(netto=10))
assert e["gesamt"] is None and e["fehler"]
db3.schliessen()
ok("Alte Datei (Schema 14): Sicherung, leere Frachttabellen, neue Kundenfelder, Rechner meldet fehlende Daten")
print("OK: Frachtkosten")
