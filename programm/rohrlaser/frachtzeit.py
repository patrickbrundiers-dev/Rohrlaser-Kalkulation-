"""Lieferdatum ab Werk und frei Haus (Patrick 10.11.2026, Freigabe „Alle Empfehlungen“ F1a–F5a).

- ab Werk = die Ware ist versandbereit (Termin nach Auslastung, terminplan); gespeichert in angebote.liefertermin
  und so verplant (Auslastung, Fertigung, Versand).
- frei Haus = ab Werk + Frachtlaufzeit in Arbeitstagen (Montag bis Freitag ohne die Feiertage des eigenen
  Bundeslands, Einstellung 'versand_bundesland'); gespeichert in angebote.liefertermin_frei_haus.
- Frachtlaufzeit (F1a): Feld 'laufzeit_tage' am Frachttarif (der Tarif der gespeicherten Frachtberechnung des
  Angebots); fehlt es, gilt die Vorgabe der Einstellungen 'frachtzeit_inland' (1) bzw. 'frachtzeit_ausland' (3).
  Laufzeit 0: Lieferbedingung ab Werk, Abholung, frei Frachtführer, Fracht „keine Fracht“ und Eigene Anlieferung.
- Kundentermin (F3a, F4a): Die Lieferzeit im Angebot und ein Wunschtermin des Kunden meinen bei frei Haus die
  Ankunft beim Kunden; ab Werk wird daraus rückwärts gerechnet (Kundentermin minus Laufzeit). Bei ab Werk/Abholung
  ist der Kundentermin das Datum ab Werk. Angebot und AB nennen das Datum passend zur Lieferbedingung.
"""
import datetime
from collections import namedtuple

from . import feiertage

AB_WERK, FREI_HAUS = "ab Werk", "frei Haus"
OHNE_LAUFZEIT = ("ab Werk", "Abholung", "frei Frachtführer")   # Lieferbedingungen: der Kunde holt bzw. übernimmt bei uns
EIGEN = "Eigene Anlieferung"                                  # fracht_richtwerte.EIGEN: am selben Tag beim Kunden
VORGABE_INLAND, VORGABE_AUSLAND = 1, 3

# tage = Arbeitstage Fracht; quelle = Text für Hinweise; frei_haus = Kundentermin ist die Ankunft beim Kunden
Laufzeit = namedtuple("Laufzeit", "tage quelle frei_haus")


def _ganz(v):
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def laufzeit(kopf, kunde=None, einst=None):
    """Frachtlaufzeit eines Angebots (Laufzeit). kopf = Angebotskopf, kunde = Kundenzeile (Lieferbedingung, Land),
    einst = Einstellungen (dict oder Funktion name -> Wert)."""
    from . import fracht_angebot
    kopf, kunde = kopf or {}, kunde or {}
    e = einst if callable(einst) else (einst or {}).get
    lb = (kunde.get("lieferbedingung") or "").strip()
    if fracht_angebot.modus(kopf) == fracht_angebot.KEINE:
        return Laufzeit(0, "keine Fracht (Abholung, ab Werk)", False)
    if lb in OHNE_LAUFZEIT:
        return Laufzeit(0, f"Lieferbedingung {lb}", False)
    d = fracht_angebot.daten(kopf) or {}
    tarif = (d.get("snapshot") or {}).get("tarif") or {}
    versandart = ((d.get("sendung") or {}).get("versandart") or tarif.get("versandart")
                  or e("fracht_versandart") or "")
    tage = _ganz(tarif.get("laufzeit_tage"))
    if tage is not None:
        return Laufzeit(max(0, tage), f"Tarif {tarif.get('tarif_id')}", True)
    if versandart == EIGEN:
        return Laufzeit(0, EIGEN, True)
    land = (kopf.get("fracht_land") or kunde.get("land") or "DE").strip().upper()
    if land == (e("absender_land") or "DE").strip().upper():
        tage = _ganz(e("frachtzeit_inland"))
        return Laufzeit(VORGABE_INLAND if tage is None else max(0, tage), "Vorgabe Inland", True)
    tage = _ganz(e("frachtzeit_ausland"))
    return Laufzeit(VORGABE_AUSLAND if tage is None else max(0, tage), f"Vorgabe Ausland ({land})", True)


def fuer_angebot(db, kopf):
    """Laufzeit mit Kunde und Einstellungen aus der Datenbank."""
    kopf = kopf or {}
    return laufzeit(kopf, db.kunde(kopf.get("kundennr")), db.einstellung)


def frei_haus(ab_werk, tage, land=None):
    """Ankunft beim Kunden: ab Werk + tage Arbeitstage (F5a: Feiertage des eigenen Bundeslands)."""
    return feiertage.arbeitstage_spaeter(ab_werk, int(tage), land) if ab_werk and tage else ab_werk


def ab_werk(frei_haus_datum, tage, land=None):
    """Rückwärts (F3a): spätestes Datum ab Werk für eine Ankunft am frei_haus_datum."""
    d, n = frei_haus_datum, int(tage or 0)
    while d and n > 0:
        d -= datetime.timedelta(days=1)
        if feiertage.ist_arbeitstag(d, land):
            n -= 1
    return d


def kundentermin(ab_werk_datum, lz, land=None):
    """Datum, das der Kunde genannt bekommt: frei Haus (Ankunft) oder ab Werk."""
    return frei_haus(ab_werk_datum, lz.tage, land) if lz.frei_haus else ab_werk_datum


def aus_kundentermin(datum, lz, land=None):
    """Datum ab Werk zu einem Kundentermin (Lieferzeit im Angebot, Wunschtermin)."""
    return ab_werk(datum, lz.tage, land) if lz.frei_haus else datum


def art(lz):
    return FREI_HAUS if lz.frei_haus else AB_WERK


def hinweis(lz):
    """Kurzer Text, z. B. 'frei Haus = ab Werk + 1 Arbeitstag Fracht (Vorgabe Inland)'."""
    if not lz.frei_haus:
        return f"Lieferung ab Werk ({lz.quelle})"
    return (f"frei Haus = ab Werk + {lz.tage} Arbeitstag{'' if lz.tage == 1 else 'e'} Fracht ({lz.quelle})")


def _iso(v):
    try:
        return datetime.date.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def termine(db, a, lz=None):
    """(ab Werk, frei Haus) eines Angebots als date oder None. frei Haus: gespeichert, sonst aus ab Werk gerechnet
    (ältere Aufträge ohne gespeichertes Datum)."""
    aw = _iso((a or {}).get("liefertermin"))
    fh = _iso((a or {}).get("liefertermin_frei_haus"))
    if aw and not fh:
        try:
            lz = lz or fuer_angebot(db, db.angebot(a["id"]) if a.get("id") and db else a)
            fh = frei_haus(aw, lz.tage, db.einstellung("versand_bundesland") if db else None)
        except Exception:           # Anzeige darf an der Fracht nie scheitern
            fh = None
    return aw, fh


def text_datum(d):
    return d.strftime("%d.%m.%Y") if d else ""
