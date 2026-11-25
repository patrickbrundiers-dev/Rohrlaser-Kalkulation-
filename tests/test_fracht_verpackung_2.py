"""Test: Fracht + Verpackung 2.0 (Patrick 25.11.2026, Master-Auftrag Versand- und Verpackungskalkulation).

- Tarifvorlagen: Listenpreise DHL/GLS/Hermes mit Quelle und Stand, Tariflücken (MBE, UPS, FedEx, DPD, Cargoboard,
  Speditionen) ohne Preise; zweimal laden legt nichts doppelt an; eigene Tarife bleiben.
- Tariflücke wird nie automatisch gewählt, bestehende Fracht (Richtwerte) rechnet gleich; Angebot per CSV macht aus der
  Tariflücke ein Geschäftskundenangebot mit Stand heute.
- Paketregeln: Karton, Mehrkarton (Preis je Paket nach Gewicht), Größenklassen (längste + kürzeste Seite), Gurtmaß und
  Längen-/Gewichtsgrenzen (Sperrgut mit Zuschlag bzw. nicht als Paket), Volumengewicht, Rundung.
- Paletten: Europalette, Palette mit Aufsetzrahmen (Anzahl Rahmen automatisch), Gitterbox, Langgut, Mischsendung,
  mehrere Paletten; Packmittelkosten (Kauf, Miete, Tausch mit Pfand, Sicherung, Packzeit, Rahmen).
- Anbietervergleich DE/EU/international: günstigster, schnellster, Preis-Leistung, Paletten; Richtwerte nie als
  Anbieterpreis, Tariflücken „Tarif fehlt – Angebot einholen“.
- Schnittstellen: ab Werk aus (kein Netz), Antworten von UPS/FedEx/DHL Express/Cargoboard offline gelesen.
- Angebot: Umlage nach Volumen, eigene Position (eigene Zeile im Angebot, Staffeln ohne Fracht), Verpackung aus der
  Packliste nur mit Haken; ohne die neuen Einstellungen bitgleich.
- Oberfläche: Frachtfenster mit Reitern Frachtkosten, Preisvergleich, Packliste und Packmittelkosten; Packmittel-Seite.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import (ausgabe, fracht, fracht_angebot, fracht_api, fracht_daten, fracht_tarife,  # noqa: E402
                       fracht_vergleich, paletten, rechnen, staffeln, zugang)
from rohrlaser.angebot import aktiv  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
db.einstellung_setzen("absender_plz", "33129")
db.fracht_richtwerte_laden("33129")
aid = beispiel_angebot.anlegen(db)
assert SCHEMA_VERSION >= 106


def setzen(tabelle, schluessel, wert, **felder):
    """Felder einer Stammdatenzeile ändern (Zeile nach ihrem Schlüssel)."""
    rid = next(z["id"] for z in db.zeilen(tabelle) if z.get(schluessel) == wert)
    for f, w in felder.items():
        db.aendern(tabelle, rid, f, w)


def rechnung(a_id):
    a = db.angebot(a_id)
    pos = db.positionen(a_id)
    k, tab = db.kontext(), db.tabellen()
    erg = rechnen.optimieren(a, pos, k)
    einst = rechnen.einstellungen_angebot(a, db.einstellungen())
    return a, pos, rechnen.kalkulation(a, pos, erg, k, tab, einst)


# ------------------------------------------------------------------ Bitgleich vor den Vorlagen
s_pal = dict(land="DE", plz="80331", absender_plz="33129", netto=300.0, lht=[dict(lht_id="EUR", anzahl=1)])
vorher = fracht.rechnen(db.fracht_daten(), s_pal)
_, _, (z_vor, sum_vor) = rechnung(aid)

# ------------------------------------------------------------------ Tarifvorlagen
n = db.fracht_vorlagen_laden()
assert n > 50 and db.fracht_vorlagen_laden() == 0, n
tarife = {t["tarif_id"]: t for t in db.zeilen("fracht_tarife")}
dhl = tarife["DHL-PAKET-2026"]
assert dhl["basis"] == "Listenpreis" and dhl["quelle"] and dhl["stand"] == fracht_tarife.STAND and dhl["gueltig_bis"]
assert tarife["DHL-PAKET-2027"]["gueltig_ab"] == "2027-01-01"
for t in ("MBE-PAKET", "MBE-SPERRGUT", "MBE-PALETTE", "MBE-INTERNATIONAL", "UPS-STANDARD", "FEDEX-PAKET",
          "DPD-CLASSIC", "CARGOBOARD-PALETTE", "CARGOBOARD-TEILLADUNG", "DACHSER-STUECKGUT", "SCHENKER-STUECKGUT",
          "RABEN-STUECKGUT", "SPED-TEILLADUNG", "SPED-KOMPLETT", "EXPRESS-KURIER"):
    assert tarife[t]["basis"] == fracht_daten.LUECKE, t
    assert not [p for p in db.zeilen("fracht_preise") if p["tarif_id"] == t], t       # keine erfundenen Preise
assert all((t.get("prioritaet") or 0) > 70 for i, t in tarife.items() if not i.startswith("RW-"))
ok(f"Tarifvorlagen: {n} Zeilen, Listenpreise mit Quelle und Stand, 15 Tariflücken ohne Preise, zweites Laden ändert "
   "nichts")

nachher = fracht.rechnen(db.fracht_daten(), s_pal)
assert nachher["gesamt"] == vorher["gesamt"] and nachher["tarif"]["tarif_id"] == vorher["tarif"]["tarif_id"]
_, _, (z_nach, sum_nach) = rechnung(aid)
assert sum_nach["verkauf"] == sum_vor["verkauf"] and sum_nach["fracht"] == sum_vor["fracht"]
assert [z and z["preis_teil"] for z in z_nach] == [z and z["preis_teil"] for z in z_vor]
ok(f"Bitgleich: Palette nach München weiter {vorher['gesamt']:.2f} € ({vorher['tarif']['tarif_id']}), Angebot "
   f"{sum_vor['verkauf']:.2f} € unverändert")

# ------------------------------------------------------------------ Paketregeln
n_pm = db.packmittel_vorlagen_laden()
assert n_pm == 5 and db.packmittel_vorlagen_laden() == 0
daten = db.fracht_daten()
paket = dict(land="DE", plz="80331", absender_plz="33129", versandart="Paket", tarif_id="DHL-PAKET-2026")


def k(lht_id, anzahl=1, brutto_je=None, masse=None, **extra):
    e = dict(lht_id=lht_id, anzahl=anzahl, **extra)
    if brutto_je:
        e["brutto_je"] = brutto_je
    if masse:
        e["masse"] = masse
    return e


e = fracht.rechnen(daten, dict(paket, netto=8.0, lht=[k("K-M")]))
assert e["gesamt"] == 10.49 and not e["fehler"], (e["gesamt"], e["fehler"])
e = fracht.rechnen(daten, dict(paket, netto=0.0, lht=[k("K-M", 3, brutto_je=[1.5, 4.8, 19.0])]))
assert e["gesamt"] == round(6.19 + 7.69 + 18.99, 2), e["zeilen"]
ok("Karton 8 kg = 10,49 €; Mehrkarton 1,5/4,8/19 kg = 6,19 + 7,69 + 18,99 € (Preis je Paket)")

e = fracht.rechnen(daten, dict(paket, netto=0.0, lht=[k("K-R1", 1, brutto_je=[12.0])]))
assert e["gesamt"] == round(18.99 + 28.99, 2) and any("Sperrgut" in z["text"] for z in e["zeilen"]), e["zeilen"]
e = fracht.rechnen(daten, dict(paket, netto=0.0, lht=[k("K-R2", 1, brutto_je=[12.0])]))    # außen 201 cm > 200 cm
assert e["gesamt"] is None and "zu groß" in e["fehler"][0], e["fehler"]
e = fracht.rechnen(daten, dict(paket, netto=0.0, lht=[k("K-M", 1, brutto_je=[35.0])]))
assert e["gesamt"] is None and e["fehler"], e
e = fracht.rechnen(daten, dict(paket, netto=0.0, lht=[k("K-M", 1, brutto_je=[5.0], masse=[2100, 300, 300])]))
assert e["gesamt"] is None and "zu groß" in e["fehler"][0], e["fehler"]
assert fracht.gurtmass((1200, 600, 600)) == 3600
ok("Rohrkarton 1,2 m (außen 121 cm) = Sperrgut (+28,99 €), 2 m (außen 201 cm) zu groß, 35 kg und 2,1 m nicht als DHL-Paket, Gurtmaß 1200+2×600+2×600 = 3600 mm")

gls = dict(paket, tarif_id="GLS-PAKET-2026")
e = fracht.rechnen(daten, dict(gls, netto=3.0, lht=[k("K-S")]))          # 400 × 300 × 200: 400 + 200 = 600 -> M
assert e["gesamt"] == 6.89, e["zeilen"]
e = fracht.rechnen(daten, dict(gls, netto=3.0, lht=[k("K-L")]))          # 1200 × 200 × 200 -> 1400 > 900 -> XL
assert e["gesamt"] == 22.00, e["zeilen"]
ok("GLS Größenklasse aus längster + kürzester Seite: 40 × 30 × 20 cm = M 6,89 €, 120 × 20 × 20 cm = XL 22,00 €")

# Volumengewicht und Rundung (eigener Pakettarif: Divisor 5.000 = 200 kg/m³, auf 1 kg runden)
db.neu("fracht_tarife", dict(tarif_id="T-VOL", bezeichnung="Test Volumen", modell="Pakettarif", versandart="Paket",
                             faktor_m3=200, rundung_kg=1, aktiv="ja", basis="Geschäftskundenangebot", stand="2026-11-25"))
for b, p in ((5, 8.0), (10, 11.0), (30, 20.0)):
    db.neu("fracht_preise", dict(tarif_id="T-VOL", bezug="Packstück", bis=b, preis=p, preisart="Festpreis"))
daten = db.fracht_daten()
e = fracht.rechnen(daten, dict(paket, tarif_id="T-VOL", netto=0.0, lht=[k("K-M", 1, brutto_je=[2.0])]))
# 600 × 400 × 400 mm = 0,096 m³ × 200 = 19,2 kg -> 20 kg (gerundet) -> Stufe bis 30 = 20 €
assert e["gesamt"] == 20.0, e["zeilen"]
ok("Volumengewicht 60 × 40 × 40 cm = 19,2 kg, auf 20 kg gerundet: Stufe bis 30 kg = 20 € statt 8 € nach Gewicht")

# ------------------------------------------------------------------ Paletten und Packmittel
lht = db.zeilen("fracht_lht")
eur_r = next(z for z in lht if z["lht_id"] == "EUR-R")
assert eur_r["art"] == paletten.RAHMEN and eur_r["rahmen_hoehe"] == 200 and eur_r["preis"] is None
v = {"hoehe_gesamt": 1200}
assert paletten.rahmen_anzahl(eur_r, 350) == 2 and paletten.rahmen_anzahl(eur_r, 1000) == 5
assert paletten.rahmen_anzahl(eur_r, 3000) == 5 and paletten.stapelhoehe(eur_r, v) == 1000
ok("Standard-Packmittel ohne Preise; Aufsetzrahmen automatisch: 350 mm Ware = 2 Rahmen, 1.000 mm = 5, höchstens 5")

pos = db.positionen(aid)
kopf = db.angebot(aid)
werte = [rechnen.position_werte(p, kopf, db.kontext(), db.tabellen()) if aktiv(p) else None for p in pos]
for std in ("EUR", "EUR-R", "GB-EP"):
    pl = paletten.packen(pos, werte, lht, std, "LG", None)
    assert pl["anzahl"] >= 1 and pl["netto"], (std, pl["hinweise"])
    if std == "EUR-R":
        rp = [p for p in pl["paletten"] if p["lht_id"] == "EUR-R"]
        assert rp and all(1 <= p["rahmen"] <= 5 for p in rp), rp
        assert all(p["hoehe"] == 144 + p["rahmen"] * 200 for p in rp), [(p["hoehe"], p["rahmen"]) for p in rp]
    if std == "GB-EP":
        assert any(p["lht_id"] == "GB-EP" for p in pl["paletten"])
    ids = {p["lht_id"] for p in pl["paletten"]}
    if "LG" in ids:
        assert ids - {"LG"}, ids                          # Mischsendung: Langgut und Standard
ok("Packen mit Europalette, Palette mit Aufsetzrahmen (Höhe = 144 + Rahmen × 200 mm) und Gitterbox; lange Teile "
   "auf Langgut (Mischsendung)")

# mehrere Paletten: Ware verdoppelt
pl1 = paletten.packen(pos, werte, lht, "EUR", "LG", None)
pos2 = [dict(p, stueck=(p.get("stueck") or 0) * 6) for p in pos]
pl6 = paletten.packen(pos2, werte, lht, "EUR", "LG", None)
assert pl6["anzahl"] > pl1["anzahl"], (pl1["anzahl"], pl6["anzahl"])
ok(f"Mehrere Paletten: 6-fache Menge = {pl6['anzahl']} statt {pl1['anzahl']} Ladungsträger")

setzen("fracht_lht", "lht_id", "EUR-R", preis=12.5, abrechnung="Kauf", sicherung=3.0, packzeit=15, rahmen_preis=4.0)
setzen("fracht_lht", "lht_id", "GB-EP", abrechnung="Tausch", pfand=80.0)
lht = db.zeilen("fracht_lht")
pm = paletten.packmittel_kosten([dict(lht_id="EUR-R", anzahl=2, rahmen=5), dict(lht_id="GB-EP", anzahl=1)], lht, 40.0)
assert pm["gesamt"] == round(2 * 12.5 + 2 * 3.0 + 2 * 15 / 60 * 40 + 5 * 4.0, 2), pm
assert any("Pfand 80,00" in h for h in pm["hinweise"])
ok(f"Packmittelkosten: 2 Paletten 25 € + Sicherung 6 € + Packzeit 20 € + 5 Rahmen 20 € = {pm['gesamt']:.2f} €; "
   "Gitterbox im Tausch 0 € mit Pfand-Hinweis")

# ------------------------------------------------------------------ Tariflücke: nie automatisch, CSV-Angebot
daten = db.fracht_daten()
s_auto = dict(land="DE", plz="80331", absender_plz="33129", netto=300.0, lht=[dict(lht_id="EUR", anzahl=1)],
              dienstleister="MBE")
e = fracht.rechnen(daten, s_auto)
assert e["gesamt"] is None, e                     # nur Tariflücken bei MBE: keine Fracht erfunden
csv = fracht_daten.preise_csv([dict(tarif_id="MBE-PALETTE", bezug="Ladungsträger", lht_art="Europalette", bis=1,
                                    preis=149.0, preisart="je Einheit"),
                               dict(tarif_id="MBE-PALETTE", bezug="Ladungsträger", lht_art="Europalette", bis=99,
                                    preis=129.0, preisart="je Einheit")])
zeilen, fehler = fracht_daten.preise_csv_lesen(csv, db.zeilen("fracht_tarife"), db.zeilen("fracht_zonen"))
assert len(zeilen) == 2 and not fehler, fehler
_, fehler2 = fracht_daten.preise_csv_lesen("tarif_id;bezug;bis;preis\nGIBTSNICHT;Sendung;1;5\n",
                                           db.zeilen("fracht_tarife"))
assert fehler2, fehler2
weg, neu, sich = db.fracht_preise_einlesen(zeilen)
assert (weg, neu) == (0, 2) and sich
t = next(t for t in db.zeilen("fracht_tarife") if t["tarif_id"] == "MBE-PALETTE")
assert t["basis"] == "Geschäftskundenangebot" and t["stand"] == fracht.heute()
daten = db.fracht_daten()
e = fracht.rechnen(daten, s_auto)
assert e["gesamt"] is not None and e["tarif"]["tarif_id"] == "MBE-PALETTE", (e["fehler"], e.get("tarif"))
ok(f"MBE: ohne Angebot keine Fracht (Tariflücke), CSV-Angebot übernommen (Sicherung vorher) -> Geschäftskundenangebot "
   f"mit Stand heute, Palette {e['gesamt']:.2f} €; unbekannter Tarif in der CSV = Fehler")

# ------------------------------------------------------------------ Vergleich DE / EU / international
sp = dict(land="DE", plz="80331", absender_plz="33129", netto=8.0, versandart="Paket", lht=[k("K-M")])
v = fracht_vergleich.vergleich(daten, {"Paket": sp, "Palette": dict(s_pal, versandart=None)})
z = {x["tarif_id"]: x for x in v["zeilen"]}
assert z["DHL-PAKET-2026"]["gesamt"] == 10.49 and z["DHL-PAKET-2026"]["preisart"] == "Anbieterpreis"
assert z["RW-PALETTE"]["preisart"] == "Richtwert" and z["RW-PALETTE"]["text"] == fracht_vergleich.RICHTWERT
assert z["UPS-STANDARD"]["status"] == "lücke" and z["UPS-STANDARD"]["text"] == fracht_vergleich.FEHLT
assert z["UPS-STANDARD"]["gesamt"] is None and "DHL-PAKET-2027" not in z       # 2027 erst ab 01.01.2027
emp = v["empfehlung"]
assert emp["guenstigster"]["preisart"] == "Anbieterpreis" and emp["guenstigster"]["gesamt"] == min(
    x["gesamt"] for x in v["zeilen"] if x["status"] == "ok" and x["preisart"] == "Anbieterpreis")
assert emp["paletten"]["tarif_id"] == "MBE-PALETTE" and emp["automatisch"]
ok(f"Vergleich DE: günstigster {emp['guenstigster']['bezeichnung']} {emp['guenstigster']['gesamt']:.2f} €, "
   "Palette MBE (Angebot), Richtwert gekennzeichnet, UPS „Tarif fehlt – Angebot einholen“")

for x in ("DHL-PAKET-2026", "GLS-PAKET-2026"):
    setzen("fracht_tarife", "tarif_id", x, laufzeit_tage=1 if x.startswith("DHL") else 3)
daten = db.fracht_daten()
sp3 = dict(sp, netto=3.0, lht=[k("K-S")])      # 40 × 30 × 20 cm, 3 kg: DHL 7,69 €, GLS M 6,89 €
v = fracht_vergleich.vergleich(daten, {"Paket": sp3})
emp = v["empfehlung"]
assert emp["schnellster"]["tarif_id"] == "DHL-PAKET-2026" and emp["guenstigster"]["tarif_id"] != "DHL-PAKET-2026"
assert emp["preis_leistung"]["tarif_id"] == "DHL-PAKET-2026"     # GLS 2 Tage langsamer: nicht Preis-Leistung
ok("Schnellster DHL (1 AT), günstigster GLS (3 AT); Preis-Leistung = DHL (GLS mehr als 1 AT langsamer)")

eu = dict(sp, land="AT", plz="1010")
v = fracht_vergleich.vergleich(daten, {"Paket": eu})
z = {x["tarif_id"]: x for x in v["zeilen"]}
assert z["DHL-PAKET-EU-2026"]["gesamt"] == 25.49, z["DHL-PAKET-EU-2026"]       # 8 kg -> bis 10 kg
assert "DHL-PAKET-2026" not in z and z["MBE-INTERNATIONAL"]["status"] == "lücke"
ch = dict(sp, land="CH", plz="8001")
v = fracht_vergleich.vergleich(daten, {"Paket": ch})
assert not [x for x in v["zeilen"] if x["status"] == "ok" and x["preisart"] == "Anbieterpreis"]
assert v["hinweise"] or not v["empfehlung"].get("automatisch") or v["empfehlung"]["automatisch"]["preisart"] != \
    "Anbieterpreis"
ok("EU (Wien): DHL Paket EU 25,49 €, MBE international Tariflücke; international (Schweiz): kein Listenpreis, keine "
   "erfundene Fracht")

# ------------------------------------------------------------------ Schnittstellen
assert fracht_api.eingerichtet(db.einstellungen()) == [] and db.einstellung("fracht_api_aktiv") == "nein"
r0 = fracht_api.abfragen(db.einstellungen(), sp, oeffnen=lambda *a, **kw: 1 / 0)
assert not r0["preise"] and "aus" in r0["fehler"][0]
ups = fracht_api.UPS().antwort({"RateResponse": {"RatedShipment": [
    {"Service": {"Code": "11"}, "TotalCharges": {"MonetaryValue": "19.80", "CurrencyCode": "EUR"},
     "NegotiatedRateCharges": {"TotalCharge": {"MonetaryValue": "14.10", "CurrencyCode": "EUR"}},
     "GuaranteedDelivery": {"BusinessDaysInTransit": "1"}}]}})
assert ups == [dict(dienst="UPS 11", preis=14.10, waehrung="EUR", laufzeit=1, vertragspreis=True)], ups
fx = fracht_api.FedEx().antwort({"output": {"rateReplyDetails": [
    {"serviceType": "FEDEX_REGIONAL_ECONOMY", "ratedShipmentDetails": [
        {"rateType": "ACCOUNT", "totalNetCharge": 17.5, "currency": "EUR"}]}]}})
assert fx[0]["preis"] == 17.5
dh = fracht_api.DHLExpress().antwort({"products": [{"productName": "EXPRESS DOMESTIC", "totalPrice": [
    {"currencyType": "BILLC", "priceCurrency": "EUR", "price": 31.2}], "deliveryCapabilities": {"totalTransitDays": "1"}}]})
assert dh[0]["preis"] == 31.2 and dh[0]["laufzeit"] == 1
cb = fracht_api.Cargoboard().antwort({"quotations": [{"product": "Standard", "price": {"net": 89.0, "currency": "EUR"},
                                                      "transitDays": 2}]})
assert cb[0]["preis"] == 89.0
url, kopf_h, body = fracht_api.UPS().anfrage(dict(sp, stuecke=[dict(kg=8.0, masse=(600, 400, 400))]), "A1")
assert body["RateRequest"]["Shipment"]["Package"][0]["Dimensions"]["Length"] == "60"
assert "@" not in json.dumps(body)                         # keine Kunden- oder Personendaten
zwei = dict(sp, stuecke=[dict(kg=8.0, masse=(600, 400, 400)), dict(kg=3.0, masse=(300, 200, 100))])
url, kopf_h, body = fracht_api.DHLExpress().anfrage(zwei, "A1")
assert body["packages"][1] == {"weight": 3.0, "dimensions": {"length": 30, "width": 20, "height": 10}}, body
assert len(body["packages"]) == 2 and "?" not in url          # Mehrstück per POST, jedes Stück mit Maß
tk, tb = fracht_api._token_anfrage(fracht_api.FedEx(), "id1", "geh")
assert b"client_id=id1" in tb and b"client_secret=geh" in tb and "Authorization" not in tk
tk, tb = fracht_api._token_anfrage(fracht_api.UPS(), "id1", "geh")
assert tk["Authorization"].startswith("Basic ") and tb == b"grant_type=client_credentials"
db.einstellung_setzen("fracht_api_aktiv", "ja")
zugang.speichern(fracht_api.zugang_name("UPS"), "A1|client", "geheim")


class Antwort:
    def __init__(self, j):
        self.j = j

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self.j).encode()


aufrufe = []


def oeffnen(req, timeout=None):
    aufrufe.append(req.full_url)
    if "oauth" in req.full_url:
        return Antwort({"access_token": "t"})
    return Antwort({"RateResponse": {"RatedShipment": [{"Service": {"Code": "11"}, "TotalCharges": {
        "MonetaryValue": "15.00", "CurrencyCode": "EUR"}}]}})


r1 = fracht_api.abfragen(db.einstellungen(), sp, oeffnen=oeffnen)
assert r1["preise"][0]["preis"] == 15.0 and r1["preise"][0]["basis"] == "Schnittstelle" and len(aufrufe) == 2
r2 = fracht_api.abfragen(db.einstellungen(), sp, oeffnen=lambda *a, **kw: (_ for _ in ()).throw(OSError("netz")))
assert not r2["preise"] and "gespeicherte Tarif" in r2["fehler"][0]
zugang.loeschen(fracht_api.zugang_name("UPS"))
db.einstellung_setzen("fracht_api_aktiv", "nein")
ok("Schnittstellen ab Werk aus (kein Aufruf); UPS/FedEx/DHL Express/Cargoboard-Antworten gelesen, nur Sendungsdaten "
   "in der Anfrage; Netzfehler -> gespeicherter Tarif gilt")

# ------------------------------------------------------------------ Angebot: Umlage nach Volumen, eigene Position
db.angebot_aendern(aid, "fracht", 220.0)
db.angebot_aendern(aid, "fracht_modus", None)
db.angebot_aendern(aid, "fracht_umlage", fracht_angebot.NACH_GEWICHT)
a, pos, (zg, sg) = rechnung(aid)
db.angebot_aendern(aid, "fracht_umlage", fracht_angebot.NACH_VOLUMEN)
a, pos, (zv, sv) = rechnung(aid)
assert abs(sum(z["fracht_teil"] * z["stueck"] for z in zv if z) - 220.0) < 1e-6
assert sv["fracht_umlage"] in (fracht_angebot.NACH_VOLUMEN, fracht_angebot.JE_STUECK)
assert abs(sv["verkauf"] - sg["verkauf"]) < 0.05
ok(f"Umlage {sv['fracht_umlage']}: Summe 220 €, Gesamtpreis gleich ({sv['verkauf']:.2f} €)")

db.angebot_aendern(aid, "fracht_umlage", fracht_angebot.EIGENE)
a, pos, (ze, se) = rechnung(aid)
assert all(z["fracht_teil"] == 0 for z in ze if z) and se["fracht_position"] == 220.0
assert abs(se["verkauf"] - (sg["verkauf"] - 220.0 / (1 - (se.get("skonto_satz") or 0) / 100) + 220.0)) < 0.5, (
    se["verkauf"], sg["verkauf"])
from rohrlaser import marge  # noqa: E402
assert abs(marge.werte(se)["warenwert"] - marge.werte(sg)["warenwert"]) < 0.5
ang = ausgabe.angebot(a, pos, ze, db.kontext(), rechnen.einstellungen_angebot(a, db.einstellungen()))
fz = [z for z in ang["zeilen"] if z.get("fracht_position")]
assert len(fz) == 1 and fz[0]["gesamt"] == 220.0 and fz[0]["text"].startswith("Fracht und Verpackung")
assert "eigene Position" in ang["fracht"] or ang["fracht"] == ""
ok("Eigene Position: Stückpreise ohne Fracht, eigene Zeile „Fracht und Verpackung“ 220 € im Angebot, Warenwert und "
   "Marge wie bei umgelegter Fracht (Fracht ohne Gewinn)")

stufen_kopf = dict(a, fracht_position_aus="ja")
_, s_st = rechnen.kalkulation(stufen_kopf, pos, rechnen.optimieren(a, pos, db.kontext()), db.kontext(),
                              db.tabellen(), rechnen.einstellungen_angebot(a, db.einstellungen()))
assert not s_st.get("fracht_position") and abs(s_st["verkauf"] - (se["verkauf"] - 220.0)) < 1e-6
assert staffeln is not None
ok("Staffelstufen bei eigener Position: Preise ohne Fracht")
db.angebot_aendern(aid, "fracht_umlage", fracht_angebot.NACH_GEWICHT)

# Verpackung aus der Packliste nur mit Haken (ältere Angebote wie bisher)
assert not fracht_angebot.packmittel_aktiv(db.angebot(aid))
d = dict(sendung=dict(s_pal, lht=[dict(lht_id="EUR-R", anzahl=2, rahmen=5)]),
         snapshot=dict(lht=db.zeilen("fracht_lht")), gesamt=220.0, text="", packmittel_aktiv=True)
db.angebot_aendern(aid, "fracht_sendung", json.dumps(d))
db.angebot_aendern(aid, "fracht_modus", fracht_angebot.BERECHNET)
a, pos, (zp, spm) = rechnung(aid)
assert fracht_angebot.packmittel_aktiv(a) and "Packliste" in (spm.get("verpackung_text") or ""), spm.get(
    "verpackung_text")
satz = rechnen.stundensaetze(db.tabellen()).get("Verpackung") or 0
erwartet = paletten.packmittel_kosten(d["sendung"]["lht"], d["snapshot"]["lht"], satz)["gesamt"]
assert abs(spm["verpackung"] - erwartet) < 0.01, (spm["verpackung"], erwartet)
ok(f"Verpackung aus der Packliste (Haken gesetzt): {spm['verpackung']:.2f} € ohne Gewinn, statt Tabelle Verpackung")

# ------------------------------------------------------------------ Oberfläche
db.angebot_aendern(aid, "fracht_sendung", None)
db.angebot_aendern(aid, "fracht_modus", None)
fenster = Hauptfenster(db, stumm=True)
fenster.resize(1300, 900)
r = fenster.fracht.rechner
fenster.fracht.zeigen(r)
assert [r.rechts_reiter.tabText(i) for i in range(3)] == ["Frachtkosten", "Preisvergleich",
                                                         "Packliste und Packmittelkosten"]
assert all(r.versandart.findText(x) >= 0 for x in fracht_daten.VERSANDARTEN)
r.plz.setText("80331")
r.versandart.setCurrentText("Paket")
r.netto.setValue(8.0)
r.lht_tabelle.setRowCount(0)
r.lht_neu("K-M", 1)
r.rechnen()
r.rechts_reiter.setCurrentIndex(1)
assert r.vergleich_tabelle.rowCount() >= 10 and r.empfehlung.text().startswith("<b>Empfehlung")
assert not r.live_knopf.isEnabled()
assert r.anbieter_uebernehmen("HERMES-PAKET-2026") and r.ergebnis["tarif"]["tarif_id"] == "HERMES-PAKET-2026"
assert not r.anbieter_uebernehmen("UPS-STANDARD")              # Tariflücke lässt sich nicht wählen
r.rechts_reiter.setCurrentIndex(2)
assert "Packmittelkosten" in r.packmittel_anzeige.toPlainText()
pm_seite = fenster.fracht.lht
assert pm_seite.titel == "Packmittel und Ladungsträger" and pm_seite.vorlagen_laden() == 0
ok("Frachtfenster: Reiter Frachtkosten/Preisvergleich/Packliste und Packmittelkosten, alle Versandarten, Anbieter "
   "übernehmen (Tariflücke nicht), Live-Knopf nur mit Schnittstellen; Seite Packmittel und Ladungsträger")

print("OK: Fracht + Verpackung 2.0")
