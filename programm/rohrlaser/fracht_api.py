"""Live-Frachtpreise über Schnittstellen (Fracht 2.0, Patrick 25.11.2026) – optional, ab Werk AUS.

Grundsätze:
- Einstellung „fracht_api_aktiv“ (Vorgabe nein). Ohne sie und ohne Zugang wird nie ins Internet gegangen; das
  Programm rechnet vollständig offline mit den gespeicherten Tarifen.
- Abfrage nur auf Knopfdruck („Live-Preise abfragen“ im Preisvergleich), nie beim Rechnen eines Angebots.
- Zugangsdaten (Client-ID/Secret bzw. API-Schlüssel) nur in der Windows-Anmeldeinformationsverwaltung (zugang.py,
  Ziel „Rohrlaser Onlinepreise: Fracht <Anbieter>“), nie in der Datenbank.
- Es gehen nur Sendungsdaten hinaus (PLZ, Land, Gewicht, Maße), keine Kunden- oder Personendaten.
- Ein Live-Preis gilt als Tarifbasis „Schnittstelle“ mit Abrufzeit; fällt die Abfrage aus, wird mit dem zuletzt
  gespeicherten Tarif gerechnet und das im Ergebnis vermerkt.

Anbieter: UPS (Rating API, OAuth), FedEx (Rate API, OAuth), DHL Express (MyDHL API, Basic Auth), Cargoboard
(Angebots-API mit Kundenkonto; Feldzuordnung beim Freischalten anhand der Kundendokumentation prüfen). DHL Paket
Deutschland hat keine Preis-Schnittstelle (Recherche 25.11.2026): dort gilt der eingetragene Tarif.
Ohne Qt. Die Tests rufen nur anfrage()/antwort() mit Beispieldaten auf (kein Netz).
"""
import base64
import datetime
import json
import urllib.parse
import urllib.request

from . import zugang

ZEITLIMIT = 15
EINSTELLUNG = "fracht_api_aktiv"


def zugang_name(anbieter):
    return "Fracht " + anbieter


def _cm(mm):
    return max(1, round((mm or 0) / 10))


def _stuecke(sendung):
    """[(kg, (l, b, h) mm)] der Packstücke; ohne Maße 1 × 1 × 1 cm (die Anbieter verlangen Werte)."""
    out = []
    for p in sendung.get("stuecke") or []:
        out.append((max(0.1, float(p.get("kg") or 0)), tuple(p.get("masse") or (10, 10, 10))))
    if not out:
        out.append((max(0.1, float(sendung.get("brutto") or sendung.get("netto") or 0)), (10, 10, 10)))
    return out


# ------------------------------------------------------------------ UPS
class UPS:
    name = "UPS"
    token_url = "https://onlinetools.ups.com/security/v1/oauth/token"
    url = "https://onlinetools.ups.com/api/rating/v2409/Shop"

    def anfrage(self, s, konto=""):
        pakete = [{"PackagingType": {"Code": "02"},
                   "Dimensions": {"UnitOfMeasurement": {"Code": "CM"}, "Length": str(_cm(m[0])),
                                  "Width": str(_cm(m[1])), "Height": str(_cm(m[2]))},
                   "PackageWeight": {"UnitOfMeasurement": {"Code": "KGS"}, "Weight": f"{kg:.1f}"}}
                  for kg, m in _stuecke(s)]
        adr = (lambda plz, land: {"Address": {"PostalCode": plz or "", "CountryCode": land or "DE"}})
        body = {"RateRequest": {"Shipment": {
            "Shipper": dict(adr(s.get("absender_plz"), s.get("absender_land")), ShipperNumber=konto),
            "ShipFrom": adr(s.get("absender_plz"), s.get("absender_land")),
            "ShipTo": adr(s.get("plz"), s.get("land")), "Package": pakete,
            "ShipmentRatingOptions": {"NegotiatedRatesIndicator": "Y"}}}}
        return self.url, {"Content-Type": "application/json"}, body

    def antwort(self, j):
        out = []
        for r in (j.get("RateResponse") or {}).get("RatedShipment") or []:
            neg = ((r.get("NegotiatedRateCharges") or {}).get("TotalCharge") or {})
            tot = neg or r.get("TotalCharges") or {}
            tage = (r.get("GuaranteedDelivery") or {}).get("BusinessDaysInTransit")
            out.append(dict(dienst="UPS " + str((r.get("Service") or {}).get("Code") or ""),
                            preis=float(tot.get("MonetaryValue") or 0), waehrung=tot.get("CurrencyCode") or "EUR",
                            laufzeit=int(tage) if str(tage or "").isdigit() else None,
                            vertragspreis=bool(neg)))
        return out


# ------------------------------------------------------------------ FedEx
class FedEx:
    name = "FedEx"
    token_url = "https://apis.fedex.com/oauth/token"
    url = "https://apis.fedex.com/rate/v1/rates/quotes"

    def anfrage(self, s, konto=""):
        pakete = [{"weight": {"units": "KG", "value": round(kg, 1)},
                   "dimensions": {"length": _cm(m[0]), "width": _cm(m[1]), "height": _cm(m[2]), "units": "CM"}}
                  for kg, m in _stuecke(s)]
        body = {"accountNumber": {"value": konto}, "requestedShipment": {
            "shipper": {"address": {"postalCode": s.get("absender_plz") or "",
                                    "countryCode": s.get("absender_land") or "DE"}},
            "recipient": {"address": {"postalCode": s.get("plz") or "", "countryCode": s.get("land") or "DE"}},
            "pickupType": "DROPOFF_AT_FEDEX_LOCATION", "rateRequestType": ["ACCOUNT"],
            "requestedPackageLineItems": pakete}}
        return self.url, {"Content-Type": "application/json"}, body

    def antwort(self, j):
        out = []
        for r in (j.get("output") or {}).get("rateReplyDetails") or []:
            d = (r.get("ratedShipmentDetails") or [{}])[0]
            out.append(dict(dienst="FedEx " + str(r.get("serviceName") or r.get("serviceType") or ""),
                            preis=float(d.get("totalNetCharge") or 0), waehrung=d.get("currency") or "EUR",
                            laufzeit=None, vertragspreis=d.get("rateType") == "ACCOUNT"))
        return out


# ------------------------------------------------------------------ DHL Express
class DHLExpress:
    name = "DHL Express"
    token_url = None
    url = "https://express.api.dhl.com/mydhlapi/rates"

    def anfrage(self, s, konto=""):
        kg, m = max(_stuecke(s), key=lambda x: x[0])
        gesamt = sum(x[0] for x in _stuecke(s))
        datum = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        q = dict(accountNumber=konto, originCountryCode=s.get("absender_land") or "DE",
                 originPostalCode=s.get("absender_plz") or "", destinationCountryCode=s.get("land") or "DE",
                 destinationPostalCode=s.get("plz") or "", weight=f"{gesamt:.1f}", length=_cm(m[0]),
                 width=_cm(m[1]), height=_cm(m[2]), plannedShippingDate=datum, isCustomsDeclarable="false",
                 unitOfMeasurement="metric")
        return self.url + "?" + urllib.parse.urlencode(q), {}, None

    def antwort(self, j):
        out = []
        for p in j.get("products") or []:
            preis = next((x for x in p.get("totalPrice") or [] if x.get("currencyType") == "BILLC"),
                         (p.get("totalPrice") or [{}])[0])
            tage = (p.get("deliveryCapabilities") or {}).get("totalTransitDays")
            out.append(dict(dienst="DHL Express " + str(p.get("productName") or ""),
                            preis=float(preis.get("price") or 0), waehrung=preis.get("priceCurrency") or "EUR",
                            laufzeit=int(tage) if str(tage or "").isdigit() else None, vertragspreis=True))
        return out


# ------------------------------------------------------------------ Cargoboard
class Cargoboard:
    """Cargoboard-Angebots-API (Kundenkonto mit E-Mail und API-Schlüssel, kostenlos laut docs.cargoboard.com).
    Die Feldnamen folgen der öffentlichen Übersicht; beim Freischalten mit der Kundendokumentation abgleichen."""
    name = "Cargoboard"
    token_url = None
    url = "https://api.cargoboard.com/v1/quotations"

    def anfrage(self, s, konto=""):
        pos = [{"quantity": 1, "packagingType": "EUR" if (m[0], m[1]) == (1200, 800) else "OTHER",
                "length": _cm(m[0]), "width": _cm(m[1]), "height": _cm(m[2]), "weight": round(kg, 1)}
               for kg, m in _stuecke(s)]
        body = {"pickup": {"countryCode": s.get("absender_land") or "DE", "postalCode": s.get("absender_plz") or ""},
                "delivery": {"countryCode": s.get("land") or "DE", "postalCode": s.get("plz") or ""},
                "items": pos}
        return self.url, {"Content-Type": "application/json"}, body

    def antwort(self, j):
        out = []
        for a in j.get("quotations") or j.get("offers") or ([j] if "price" in j else []):
            p = a.get("price")
            preis = p.get("net") if isinstance(p, dict) else p
            out.append(dict(dienst="Cargoboard " + str(a.get("product") or a.get("serviceLevel") or ""),
                            preis=float(preis or 0), waehrung=(p.get("currency") if isinstance(p, dict) else None)
                            or "EUR", laufzeit=a.get("transitDays"), vertragspreis=True))
        return out


ANBIETER = {a.name: a for a in (UPS(), FedEx(), DHLExpress(), Cargoboard())}


def eingerichtet(einst):
    """Anbieter mit Zugang, wenn die Schnittstellen eingeschaltet sind (sonst leer)."""
    if (einst or {}).get(EINSTELLUNG) != "ja":
        return []
    return [n for n in ANBIETER if zugang.vorhanden(zugang_name(n))]


def _http(url, headers, body=None, methode=None, oeffnen=None):
    daten = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, data=daten, headers=dict(headers, **{"User-Agent": "Rohrlaser-Kalkulation"}),
                                 method=methode or ("POST" if daten is not None else "GET"))
    with (oeffnen or urllib.request.urlopen)(req, timeout=ZEITLIMIT) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def abfragen(einst, sendung, anbieter=None, oeffnen=None):
    """Live-Preise der eingerichteten Anbieter (nur auf Knopfdruck). Ergebnis: dict(preise=[…], fehler=[…]) –
    preise mit anbieter, dienst, preis, waehrung, laufzeit, basis 'Schnittstelle', abruf (Zeit)."""
    namen = [n for n in (anbieter or eingerichtet(einst)) if n in ANBIETER]
    out = dict(preise=[], fehler=[])
    if (einst or {}).get(EINSTELLUNG) != "ja":
        out["fehler"].append("Schnittstellen sind aus (Einstellungen › Frachtkosten): es gilt der gespeicherte Tarif")
        return out
    jetzt = datetime.datetime.now().isoformat(timespec="minutes")
    for n in namen:
        a = ANBIETER[n]
        z = zugang.lesen(zugang_name(n))
        if not z:
            out["fehler"].append(f"{n}: kein Zugang eingetragen")
            continue
        benutzer, geheim = z
        konto, _, kennung = benutzer.partition("|")      # „Kontonummer|Client-ID“ bzw. nur Kontonummer
        try:
            url, kopf, body = a.anfrage(sendung, konto)
            if a.token_url:
                t = _http(a.token_url, {"Content-Type": "application/x-www-form-urlencoded", "Authorization":
                          "Basic " + base64.b64encode(f"{kennung or konto}:{geheim}".encode()).decode()},
                          b"grant_type=client_credentials", oeffnen=oeffnen)
                kopf = dict(kopf, Authorization="Bearer " + str(t.get("access_token") or ""))
            else:
                kopf = dict(kopf, Authorization="Basic " + base64.b64encode(
                    f"{kennung or konto}:{geheim}".encode()).decode())
            for p in a.antwort(_http(url, kopf, body, oeffnen=oeffnen)):
                out["preise"].append(dict(p, anbieter=n, basis="Schnittstelle", abruf=jetzt))
        except Exception as e:          # Netz, Zugang, Antwort: gespeicherter Tarif gilt weiter
            out["fehler"].append(f"{n}: Abfrage fehlgeschlagen ({type(e).__name__}) – es gilt der gespeicherte Tarif")
    return out
