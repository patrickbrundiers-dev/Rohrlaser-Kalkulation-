"""Packmitteltausch je Dienstleister (Patrick 26.11.2026): was nicht zurückgegebene Packmittel kosten.

Grundsätze:
- Nur Tauschpackmittel (Abrechnung „Tausch“, z. B. Europalette, Gitterbox) werden getauscht. Gekaufte und gemietete
  Packmittel kosten wie bisher ihren Preis (paletten.packmittel_kosten), nie zusätzlich eine Wiederbeschaffung.
- Ohne passende Regel gilt KEIN Tausch: kein kostenloser Palettentausch unterstellen, jedes Stück kostet den
  Wiederbeschaffungswert.
- Je Stück genau eine Abrechnung: getauscht (0 €, ggf. Tauschzuschlag), Pfand, Rückführung oder Wiederbeschaffung.
  Pfand, Tauschzuschlag und Wiederbeschaffung werden so nie doppelt angesetzt.
- Die speziellere Regel gilt: Kunde vor Dienstleister vor einzelnem Packmittel vor Packmittelart vor allgemein.
Ohne Qt, ohne Datenbank.
"""
import math

from .zahlen import float_oder_0 as _n
from .zahlen import ist_zahl as _zahl

VOLL, TEIL, KEIN, ZUSCHLAG, PFAND, RUECK = ("vollständiger Tausch", "teilweiser Tausch", "kein Tausch",
                                            "Tausch gegen Zuschlag", "Tausch gegen Pfand",
                                            "Tausch nur bei Rücklieferung")
# Kostenarten der Packmittel (getrennt ausgewiesen, Summe = Packmittelkosten)
PACKMITTEL, VERPACKUNG, TAUSCHZUSCHLAG, WIEDERBESCHAFFUNG, PFAND_K, RUECKFUEHRUNG, KORREKTUR = (
    "Packmittel", "Verpackung und Sicherung", "Tauschzuschläge", "Nicht getauschte Packmittel (Wiederbeschaffung)",
    "Pfand", "Rückführung", "Korrektur von Hand")
KATEGORIEN = (PACKMITTEL, VERPACKUNG, TAUSCHZUSCHLAG, WIEDERBESCHAFFUNG, PFAND_K, RUECKFUEHRUNG, KORREKTUR)
EPS = 1e-9


def _euro(w):
    return f"{w:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def tauschbar(z):
    """Tauschpackmittel (Abrechnung Tausch)?"""
    return (z or {}).get("abrechnung") == "Tausch"


def wert(z):
    """Wiederbeschaffungswert je Stück: Wiederbeschaffungswert, sonst Tauschwert, sonst Preis; (€ oder None, Quelle)."""
    for feld, name in (("wiederbeschaffung", "Wiederbeschaffungswert"), ("tauschwert", "Tauschwert"),
                       ("preis", "Preis")):
        if _zahl(z.get(feld)):
            return float(z[feld]), name
    return None, ""


def _gilt(r, datum):
    if (r.get("aktiv") or "ja") == "nein":
        return False
    if datum and r.get("gueltig_ab") and datum < r["gueltig_ab"]:
        return False
    return not (datum and r.get("gueltig_bis") and datum > r["gueltig_bis"])


def regel(regeln, z, dienstleister=None, kundennr=None, datum=None):
    """Passende Tauschregel für Packmittel z beim Dienstleister (die speziellste) oder None."""
    beste, rang = None, None
    for r in regeln or ():
        if not r.get("regel") or not _gilt(r, datum):
            continue
        if r.get("dienstleister") and r["dienstleister"] != dienstleister:
            continue
        if r.get("kundennr") and r["kundennr"] != kundennr:
            continue
        pm = r.get("lht_id")
        if pm and pm not in (z.get("lht_id"), z.get("art")):
            continue
        k = (bool(r.get("kundennr")), bool(r.get("dienstleister")), pm == z.get("lht_id") and bool(pm), bool(pm),
             str(r.get("regel_id") or ""))
        if rang is None or k[:4] > rang[:4] or (k[:4] == rang[:4] and k[4] < rang[4]):
            beste, rang = r, k
    return beste


def kosten(eintraege, lht_zeilen, regeln, dienstleister=None, kundennr=None, datum=None):
    """Tauschkosten der Tauschpackmittel einer Sendung.
    eintraege = [{lht_id, anzahl}]. Ergebnis: dict(zeilen=[(Text, €, Kostenart)], posten={Kostenart: €},
    stuecke=[{lht_id, anzahl, getauscht, pfand, rueck, wieder, regel}], hinweise, fehlt (Wert fehlt))."""
    lht = {z["lht_id"]: z for z in lht_zeilen or () if z.get("lht_id")}
    zeilen, hinweise, stuecke, fehlt = [], [], [], False
    lieferung = {}                      # Zuschlag je Lieferung: einmal je Regel
    name_dl = dienstleister or "ohne Dienstleister"
    for e in eintraege or ():
        z, n = lht.get(e.get("lht_id")), int(_n(e.get("anzahl")))
        if not z or n <= 0 or not tauschbar(z):
            continue
        name = z.get("bezeichnung") or z["lht_id"]
        r = regel(regeln, z, dienstleister, kundennr, datum)
        art = (r or {}).get("regel") or KEIN
        grund = f"Regel {r['regel_id']}" if r else f"keine Tauschregel für {name_dl}: kein Tausch angenommen"
        if r and _zahl(r.get("mindest")) and n < r["mindest"] and art != KEIN:
            grund = f"Regel {r['regel_id']}: Tausch erst ab {int(r['mindest'])} Stück, hier {n}"
            art = KEIN
        getauscht = pfand = rueck = 0
        if art in (VOLL, ZUSCHLAG):
            getauscht = n
        elif art == TEIL:
            q = [math.floor(n * _n(r["quote"]) / 100 + EPS)] if _zahl(r.get("quote")) else []
            if _zahl(r.get("tausch_max")):
                q.append(int(r["tausch_max"]))
            getauscht = min([n] + q)
        elif art == PFAND:
            pfand = n
        elif art == RUECK:
            rueck = n
        wieder = n - getauscht - pfand - rueck
        stuecke.append(dict(lht_id=z["lht_id"], anzahl=n, getauscht=getauscht, pfand=pfand, rueck=rueck,
                            wieder=wieder, regel=(r or {}).get("regel_id"), art=art))
        if getauscht:
            satz = _n((r or {}).get("zuschlag_stueck")) if _zahl((r or {}).get("zuschlag_stueck")) else (
                _n(z.get("tauschzuschlag")) if art == ZUSCHLAG else 0.0)
            frei = int(_n((r or {}).get("frei")))
            m = max(0, getauscht - frei)
            if satz and m:
                zeilen.append((f"Tauschzuschlag {m} × {name} × {_euro(satz)}"
                               + (f" ({frei} frei)" if frei else "") + f" – {grund}", m * satz, TAUSCHZUSCHLAG))
            elif art == ZUSCHLAG and not satz:
                hinweise.append(f"{name}: Tausch gegen Zuschlag ohne Betrag (Regel oder Packmittel → Tauschzuschlag)")
            if not satz or not m:
                hinweise.append(f"{name}: {getauscht} Stück getauscht ({grund}), keine Kosten")
        if pfand:
            satz = _n(r.get("pfand")) if _zahl(r.get("pfand")) else _n(z.get("pfand"))
            if satz:
                zeilen.append((f"Pfand {pfand} × {name} × {_euro(satz)} – {grund}", pfand * satz, PFAND_K))
            else:
                hinweise.append(f"{name}: Tausch gegen Pfand ohne Pfandbetrag (Regel oder Packmittel → Pfand)")
        if rueck:
            if _zahl(r.get("rueckfuehrung")):
                zeilen.append((f"Rückführung {rueck} × {name} × {_euro(_n(r['rueckfuehrung']))} – {grund}",
                               rueck * _n(r["rueckfuehrung"]), RUECKFUEHRUNG))
            else:                       # ohne Rückführungskosten: Stücke gelten als nicht getauscht
                wieder += rueck
                stuecke[-1].update(rueck=0, wieder=wieder)
                rueck = 0
        if wieder:
            w, quelle = wert(z)
            if w is None:
                fehlt = True
                hinweise.append(f"{name}: {wieder} Stück nicht getauscht ({grund}), Wiederbeschaffungswert fehlt "
                                "(Packmittel → Wiederbeschaffungswert)")
            else:
                zeilen.append((f"Nicht getauscht {wieder} × {name} × {_euro(w)}"
                               + (f" ({quelle})" if quelle != "Wiederbeschaffungswert" else "") + f" – {grund}",
                               wieder * w, WIEDERBESCHAFFUNG))
        if r and _n(r.get("zuschlag_lieferung")) and (getauscht or pfand or rueck) and r["regel_id"] not in lieferung:
            lieferung[r["regel_id"]] = _n(r["zuschlag_lieferung"])
            zeilen.append((f"Tauschzuschlag je Lieferung ({r['regel_id']})", _n(r["zuschlag_lieferung"]),
                           TAUSCHZUSCHLAG))
    posten = {}
    for _, b, k in zeilen:
        posten[k] = posten.get(k, 0.0) + b
    return dict(zeilen=zeilen, posten=posten, stuecke=stuecke, hinweise=hinweise, fehlt=fehlt)
