"""Materialpreis-Gleitklausel für Abruf-/Rahmenangebote (Vorschlag K1, Patrick 02.11.2026 „K1a“).

Ein Abruf-Angebot mit „Material je Abruf“ (Materialklausel, abruf.py) bindet den Preis über die Laufzeit. Beim
Angebots-PDF sind die Materialpreise festgeschrieben (Preisbasis). Bei einem Abruf vergleicht „Gleitklausel prüfen …“
die festgeschriebenen Materialpreise (Preise je Profil + Werkstoff, Tonnenpreise, Lieferlängen, Teuerungszuschlag)
mit den aktuellen Stammdaten und rechnet das Angebot einmal mit den neuen Materialpreisen. Alles andere (Schneiddaten,
Stundensätze, Zuschläge, Gewinn) bleibt festgeschrieben, es ändert sich also nur der Materialanteil des Preises.

Ändern sich die Materialkosten des Angebots um mehr als die Schwelle (Einstellung abruf_klausel, Vorgabe ±5 %), ist
die Anpassung fällig; sonst bleibt der Preis. Übernommen wird nur nach Bestätigung: dann gelten die neuen
Materialpreise in der Preisbasis des Angebots, und der Versandverlauf merkt sich die Anpassung (art 'gleitklausel',
mit den alten Materialwerten, damit sie nachvollziehbar bleibt).

Ohne Qt, damit Rechnung und Tests es nutzen können."""
import copy
import datetime

from . import abruf, rechnen

MATERIAL_TEILE = ("preise", "tonnenpreise", "lieferlaengen", "teuerung")   # Teile der Preisbasis, die gleiten


def _n(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0


def moeglich(kopf):
    """Text, warum die Gleitklausel nicht geht, oder None: nur Abruf-Angebote mit Material je Abruf und mit
    festgeschriebenen Preisen (nach dem Angebots-PDF)."""
    ab = abruf.daten(kopf)
    if not ab:
        return "Gleitklausel: nur bei Abruf-/Rahmenangeboten mit Jahres- und Abrufmenge."
    if ab["bevorraten"]:
        return "Gleitklausel: das Material ist für die Jahresmenge bevorratet, der Preis gleitet nicht."
    if not isinstance((kopf or {}).get("preisbasis"), dict):
        return "Gleitklausel: erst nach dem Angebots-PDF (dann sind die Materialpreise festgeschrieben)."
    return None


def preisbasis_neu(kopf, positionen, k_akt, tab_akt):
    """Preisbasis des Angebots mit den aktuellen Materialpreisen (MATERIAL_TEILE), sonst unverändert."""
    pb = copy.deepcopy(kopf["preisbasis"])
    aktuell = rechnen.preisbasis_aus(dict(kopf, maschine=pb.get("maschine") or kopf.get("maschine")), positionen,
                                     k_akt, tab_akt)
    for n in MATERIAL_TEILE:
        if n in aktuell:
            pb[n] = aktuell[n]
    return pb


def _material_je_werkstoff(positionen, zeilen):
    out = {}
    for p, z in zip(positionen, zeilen or ()):
        if z and p.get("werkstoff_id"):
            out[p["werkstoff_id"]] = out.get(p["werkstoff_id"], 0.0) + _n(z.get("material_position"))
    return out


def pruefen(kopf, positionen, ergebnis, k_akt, tab_akt, einst, schwelle=None):
    """Vergleich festgeschrieben gegen aktuell: dict(fehlt) oder dict(schwelle [%], material_alt, material_neu,
    prozent, faellig, werkstoffe=[dict(werkstoff, alt, neu, prozent)], positionen=[dict(pos, bezeichnung, stueck,
    alt, neu)] (Preis je Teil), verkauf_alt, verkauf_neu, preisbasis=neue Preisbasis). einst = Einstellungen des
    Angebots (wie im Angebotsfenster); schwelle in % (None = Einstellung abruf_klausel, Vorgabe 5)."""
    grund = moeglich(kopf)
    if grund:
        return dict(fehlt=grund)
    if not ergebnis:
        return dict(fehlt="Gleitklausel: bitte zuerst optimieren.")
    schwelle = _n(schwelle if schwelle is not None else (tab_akt.get("einstellungen") or {}).get("abruf_klausel", 5.0))
    k_alt, t_alt = rechnen.preisbasis_anwenden(kopf, k_akt, tab_akt)
    z_alt, s_alt = rechnen.kalkulation(kopf, positionen, ergebnis, k_alt, t_alt, einst)
    pb = preisbasis_neu(kopf, positionen, k_akt, tab_akt)
    kopf_neu = dict(kopf, preisbasis=pb)
    k_neu, t_neu = rechnen.preisbasis_anwenden(kopf_neu, k_akt, tab_akt)
    z_neu, s_neu = rechnen.kalkulation(kopf_neu, positionen, ergebnis, k_neu, t_neu, einst)
    m_alt, m_neu = _n(s_alt.get("material")), _n(s_neu.get("material"))
    prozent = 100 * (m_neu - m_alt) / m_alt if m_alt > 0 else 0.0
    wa, wn = _material_je_werkstoff(positionen, z_alt), _material_je_werkstoff(positionen, z_neu)
    werkstoffe = [dict(werkstoff=w, alt=wa[w], neu=wn.get(w, 0.0),
                       prozent=100 * (wn.get(w, 0.0) - wa[w]) / wa[w] if wa[w] > 0 else 0.0)
                  for w in sorted(wa, key=str)]
    pos = [dict(pos=p.get("pos"), bezeichnung=p.get("bezeichnung") or p.get("artikel") or "", stueck=p.get("stueck"),
                alt=_n(a.get("preis_teil")), neu=_n(b.get("preis_teil")))
           for p, a, b in zip(positionen, z_alt, z_neu) if a and b]
    return dict(schwelle=schwelle, material_alt=m_alt, material_neu=m_neu, prozent=prozent,
                faellig=abs(prozent) > schwelle + 1e-9, werkstoffe=werkstoffe, positionen=pos,
                verkauf_alt=_n(s_alt.get("verkauf")), verkauf_neu=_n(s_neu.get("verkauf")), preisbasis=pb)


def eintrag(v, heute=None):
    """Eintrag für den Versandverlauf nach dem Übernehmen (art 'gleitklausel')."""
    return dict(art="gleitklausel", datum=(heute or datetime.date.today()).isoformat(),
                prozent=round(v["prozent"], 2), netto_alt=round(v["verkauf_alt"], 2),
                netto_neu=round(v["verkauf_neu"], 2))


def verlauf_text(e):
    """Zeile im Versandverlauf."""
    from .ausgabe import datum_text
    from .stammdaten import zahl_als_text as zahl
    return (f"{datum_text(e.get('datum'))}: Gleitklausel Material {'+' if _n(e.get('prozent')) >= 0 else '−'}"
            f"{zahl(abs(_n(e.get('prozent'))), 1)} % – {zahl(_n(e.get('netto_alt')), 2)} € → "
            f"{zahl(_n(e.get('netto_neu')), 2)} € netto")


def text(v):
    """Mehrzeiliger Text für die Rückfrage."""
    from .stammdaten import zahl_als_text as zahl
    if v.get("fehlt"):
        return v["fehlt"]
    zeilen = [f"Materialkosten des Angebots: {zahl(v['material_alt'], 2)} € → {zahl(v['material_neu'], 2)} € "
              f"({'+' if v['prozent'] >= 0 else '−'}{zahl(abs(v['prozent']), 1)} %), Schwelle ±{zahl(v['schwelle'], 1)} %."]
    for w in v["werkstoffe"]:
        zeilen.append(f"  {w['werkstoff']}: {'+' if w['prozent'] >= 0 else '−'}{zahl(abs(w['prozent']), 1)} %")
    zeilen.append("")
    for p in v["positionen"][:12]:
        zeilen.append(f"  Pos. {p['pos']} {p['bezeichnung']}: {zahl(p['alt'], 2)} € → {zahl(p['neu'], 2)} € je Teil")
    if len(v["positionen"]) > 12:
        zeilen.append(f"  … und {len(v['positionen']) - 12} weitere")
    zeilen.append("")
    zeilen.append(f"Angebot netto: {zahl(v['verkauf_alt'], 2)} € → {zahl(v['verkauf_neu'], 2)} €.")
    zeilen.append("Die Anpassung ist fällig (über der Schwelle)." if v["faellig"] else
                  "Unter der Schwelle: der Preis bleibt laut Klausel unverändert.")
    return "\n".join(zeilen)
