"""OFFER-015 (Roadmap Kalkulation Phase 2, Paket 2e, 13.11.2026): Angebot und Auftragsbestätigung auf Englisch.

Haken „Angebot auf Englisch“ im Angebotskopf (Kundenvorgabe „Angebote auf Englisch“ setzt ihn bei neuen Angeboten).
Das PDF übersetzt dann die festen Bezeichnungen (Kopf, Tabelle, Summen, Konditionen), die Standardsätze (Lieferzeit,
Zahlung, Fracht, Mindestauftragswert, Staffeln, Kundenmaterial) und die üblichen Wörter der Positionstexte (Profile,
Oberflächen, Zusatzarbeiten). Zahlen stehen englisch (1,234.56). Eigene Wörter: Einstellung „englisch_woerter“
(„Deutsch = English; …“, gehen den eingebauten vor). Bedingungen: Einstellung „bedingungen_en“; leer = deutscher Text
(der Angebots-Check nennt das). Ohne Haken bleibt alles wie bisher. Ohne Qt.
"""
import re

FELD = "englisch"

# feste Bezeichnungen im PDF (genau so, wie pdf.py sie schreibt)
BEZEICHNUNGEN = {
    "Angebot": "Quotation", "Auftragsbestätigung": "Order confirmation", "Angebots-Nr.": "Quotation no.",
    "Datum": "Date", "Gültig bis": "Valid until", "Kunden-Nr.": "Customer no.", "Ihre Anfrage": "Your inquiry",
    "AB-Nr.": "Confirmation no.", "Unser Angebot": "Our quotation", "vom": "dated", "Ihre Bestellung": "Your order",
    "Liefertermin": "Delivery date", "Ansprechpartner": "Contact", "Telefon": "Phone",
    "Pos.": "Item", "Art.-Nr.": "Part no.", "Bezeichnung": "Description", "Menge": "Qty", "Einh.": "Unit",
    "Preis/Einh. €": "Unit price €", "Gesamt €": "Total €", "Summe netto": "Subtotal (net)",
    "zzgl. MwSt.": "plus VAT", "Gesamtbetrag": "Total amount", "Konditionen": "Terms",
    "Rahmenbedingungen": "Framework conditions", "Stk.": "pcs.", "Satz": "set", "Sätze": "sets",
    "pausch.": "lump sum", "St": "pcs.",
}

# Sätze und Wörter der Texte, in dieser Reihenfolge (längere zuerst); Regex, Groß/klein wie geschrieben
SAETZE = (
    (r"Lieferzeit: ", "Delivery time: "),
    (r"ca\. (\S+) Arbeitstag(e)? nach Auftragseingang",
     lambda m: f"approx. {m[1]} working day{'s' if m[2] else ''} after receipt of order"),
    (r"ca\. (\S+) Woche(n)? nach Auftragseingang",
     lambda m: f"approx. {m[1]} week{'s' if m[2] else ''} after receipt of order"),
    (r"\bKW (\d)", r"CW \1"), (r"\bbis (\d\d\.\d\d\.\d{4})", r"by \1"), (r"nach Absprache", "by arrangement"),
    (r"\(frei Haus\)", "(delivered free)"), (r"\(ab Werk\)", "(ex works)"),
    (r"Liefertermine zur Wahl \(netto\): ", "Delivery options (net): "),
    (r"Express in ca\. (\d+) Arbeitstagen", r"express in approx. \1 working days"),
    (r"flexibel in ca\. (\d+) Arbeitstagen", r"flexible in approx. \1 working days"),
    (r"\bStandard (?=[\d.,]+ €)", "standard "),
    (r"Zahlung innerhalb (\d+) Tagen mit ([\d,]+) % Skonto oder innerhalb (\d+) Tagen netto\.",
     r"Payment within \1 days less \2 % cash discount or within \3 days net."),
    (r"Zahlung innerhalb (\d+) Tagen mit ([\d,]+) % Skonto oder sofort netto\.",
     r"Payment within \1 days less \2 % cash discount or immediately net."),
    (r"Zahlung innerhalb (\d+) Tagen netto\.", r"Payment within \1 days net."),
    (r"Lieferung ab Werk; Frachtkosten sind nicht enthalten\.", "Delivery ex works; freight costs are not included."),
    (r"Die Frachtkosten sind in den Preisen enthalten\.", "Freight costs are included in the prices."),
    (r"Die Preise enthalten die Fracht frei Haus nach ", "Prices include freight, delivered free to "),
    (r"Die Preise enthalten die Fracht frei Haus\.", "Prices include freight, delivered free."),
    (r"Mindestauftragswert ([\d.,]+) € netto \(Warenwert ohne Fracht\)\.",
     r"Minimum order value \1 € net (value of goods excluding freight)."),
    (r"Mindestauftragswert ([\d.,]+) € netto\.", r"Minimum order value \1 € net."),
    (r"Material wird vom Kunden beigestellt: ", "Material supplied by the customer: "),
    (r"Das Material der Pos\. (.+?) wird vom Kunden beigestellt\.", r"The material for item \1 is supplied by the customer."),
    (r"\b(\d+) Stangen? ", lambda m: f"{m[1]} bar{'' if m[1] == '1' else 's'} "), (r", à ", ", each "),
    (r"Staffelpreise je Stufe bei gemeinsamer Bestellung aller Positionen dieser Stufe",
     "Scaled prices per level when all items of this level are ordered together"),
    (r"Staffelpreise bei Einzelbestellung dieser Position", "Scaled prices when this item is ordered separately"),
    (r"Staffelpreise bei Einzelbestellung dieses Satzes", "Scaled prices when this set is ordered separately"),
    (r"Zeilen mit Stufe: bei gemeinsamer Bestellung aller Positionen dieser Stufe",
     "lines with level: when all items of this level are ordered together"),
    (r"\bStufe (\d+): ", r"Level \1: "), (r"\bAb (\d[\d.,]*) ", r"From \1 "), (r"zzgl\. einmalig", "plus one-off"),
    (r"Muster – im Serienpreis enthalten", "Sample – included in the series price"),
    (r"Muster – siehe Musterkosten einmalig", "Sample – see one-off sample costs"),
    (r"vom Kunden beigestellt", "supplied by the customer"), (r"inkl\. Material ", "incl. material "),
    (r"Naht innen geschabt", "inside weld seam removed"), (r"\bRohr (?=\S)", "tube "),
    (r"Bearbeitung: ", "Machining: "), (r"\binkl\. ", "incl. "), (r"\bGewinde\b", "thread"),
    (r"\bGravur\b", "engraving"), (r"\bGehrung\b", "mitre"), (r"\bBohrungen\b", "holes"), (r"\bBohrung\b", "hole"),
    (r"\bLanglöcher\b", "slots"), (r"\bLangloch\b", "slot"), (r"\bAusklinkung\b", "notch"),
    (r"\bRundrohr\b", "Round tube"), (r"\bQuadratrohr\b", "Square tube"), (r"\bRechteckrohr\b", "Rectangular tube"),
    (r"\bU-Profil\b", "U-channel"), (r"\bC-Profil\b", "C-channel"), (r"\bL-Profil\b", "Angle"),
    (r"\bFlachstahl\b", "Flat bar"), (r"\bI-Träger\b", "I-beam"), (r"\bT-Profil\b", "T-section"),
    (r"\bfeuerverzinkt\b", "hot-dip galvanised"), (r"\bpulverbeschichtet\b", "powder coated"),
    (r"\bverzinkt\b", "galvanised"), (r"\bgebeizt\b", "pickled"), (r"\bgeschliffen\b", "ground"),
    (r"\bgestrahlt\b", "blasted"), (r"\blackiert\b", "painted"), (r"\beloxiert\b", "anodised"),
    (r"\bgeölt\b", "oiled"), (r"\bEntgraten\b", "deburring"), (r"\bentgratet\b", "deburred"),
    (r"\bSchweißen\b", "welding"), (r"\bgeschweißt\b", "welded"), (r"\bBiegen\b", "bending"),
    (r"\bgebogen\b", "bent"), (r"\bSenkung\b", "countersink"), (r"\bSenken\b", "countersinking"),
    (r"\bFließlochformen\b", "flow drilling"), (r"\bReinigen\b", "cleaning"), (r"\bVerpackung\b", "packaging"),
    (r"\bSchweißbaugruppe\b", "welded assembly"), (r"\bSatz\b", "Set"), (r"\bStück\b", "pcs."),
    (r"\bStk\.", "pcs."), (r"\bZukaufteil\b", "purchased part"), (r"\bBlech\b", "sheet"),
)
_SAETZE = [(re.compile(m), n) for m, n in SAETZE]


def aktiv(kopf):
    return (kopf or {}).get(FELD) == "ja"


def woerter(text):
    """Einstellung „englisch_woerter“: 'Deutsch = English; …' bzw. je Zeile -> [(Deutsch, English)], längere zuerst."""
    out = []
    for teil in re.split(r"[;\n]", str(text or "")):
        de, sep, en = teil.partition("=")
        if sep and de.strip() and en.strip():
            out.append((de.strip(), en.strip()))
    return sorted(out, key=lambda x: -len(x[0]))


def zahlen(text):
    """Zahlen englisch schreiben: '1.234,56' -> '1,234.56', '42,4' -> '42.4'; Datum 15.11.2026 bleibt."""
    t = re.sub(r"(?<=\d),(?=\d)", "\x00", text)
    t = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d)(?!\.\d))", ",", t)
    return t.replace("\x00", ".")


def text(t, eigene=()):
    """Ein Text des Angebots auf Englisch (Wörter, die keiner kennt, bleiben deutsch)."""
    if not t:
        return t
    s = str(t)
    for de, en in eigene:
        s = re.sub(r"(?<!\w)" + re.escape(de) + r"(?!\w)", en.replace("\\", r"\\"), s)
    for m, n in _SAETZE:
        s = m.sub(n, s)
    return zahlen(s)


def bezeichnung(t):
    """Feste Bezeichnung im PDF (BEZEICHNUNGEN) auf Englisch; Unbekanntes wie es ist."""
    return BEZEICHNUNGEN.get(t, t)


def angebot(ang, einst):
    """ang = ausgabe.angebot(...) (angebot_daten) übersetzt, als neue dict; ang['englisch'] = True für pdf.py."""
    einst = einst or {}
    eigene = woerter(einst.get("englisch_woerter"))
    out = dict(ang, englisch=True)
    for n in ("lieferzeit", "zahlung", "fracht", "mindestpreis", "muster", "beistellung", "rahmen"):
        if out.get(n):
            out[n] = text(out[n], eigene)
    bed = str(einst.get("bedingungen_en") or "").strip()
    if bed:
        out["bedingungen"] = bed
    zeilen = []
    for z in ang.get("zeilen") or ():
        z = dict(z)
        for n in ("text", "bezeichnung", "einheit"):
            if z.get(n):
                z[n] = text(z[n], eigene)
        zeilen.append(z)
    out["zeilen"] = zeilen
    out["staffeln"] = [dict(st, text=text(st.get("text"), eigene)) for st in ang.get("staffeln") or ()]
    return out


def check_punkt(kopf, einst):
    """Hinweis im Angebots-Check: englisches Angebot, aber keine englischen Bedingungen eingetragen."""
    if not aktiv(kopf) or str((einst or {}).get("bedingungen_en") or "").strip():
        return None
    if not str((einst or {}).get("bedingungen") or "").strip():
        return None
    return ("Angebot auf Englisch: die Bedingungen stehen noch deutsch im PDF – englischen Text unter Einstellungen "
            "→ Texte im PDF → Bedingungen auf Englisch eintragen")
