"""Materialindex bzw. Legierungszuschlag je Monat (Roadmap Kalkulation Phase 2, MAT-012; Freigabe Patrick 13.11.2026
„Ganze Phase 2 nach Empfehlung“).

Tabelle 'Materialindex' (stammdaten.MATERIAL_INDEX): je Monat (JJJJ-MM) ein Zuschlag in €/t für einen Werkstoff, eine
Werkstoff-Kategorie oder alle Werkstoffe. Die Werte trägt der Anwender von Hand oder per CSV ein (Lieferanten-Info,
Stahlindex); das Programm erfindet nichts und holt nichts aus dem Netz.

Wirkung: Der Tonnenpreis des Werkstoffs gilt als Basis. Der Stammdaten-Kontext der Rechnung (Datenbank.kontext) rechnet
Basis + Zuschlag des laufenden Monats; gibt es für den Monat keine Zeile, gilt die letzte frühere. Vorrang: Zeile mit
Werkstoff-ID, dann Kategorie, dann „alle“ (beide leer). Zeilen in 'Preise' und 'Lieferlängen' bleiben unverändert (dort
stehen echte Lieferantenpreise). Festgeschriebene Angebote (preisbasis) behalten ihren Tonnenpreis; der Preiswächter
und „Aktuelle Preise übernehmen …“ melden den Unterschied wie bei jeder Preisänderung. Leere Tabelle = wie bisher.
Ohne Qt."""
import datetime


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def monat(datum=None):
    """'JJJJ-MM' des Datums (date oder ISO-Text), ohne Datum der laufende Monat."""
    if datum is None:
        return datetime.date.today().strftime("%Y-%m")
    return str(datum)[:7]


def monat_gueltig(text):
    """True für 'JJJJ-MM' mit Monat 01..12."""
    t = str(text or "").strip()
    return len(t) == 7 and t[4] == "-" and t[:4].isdigit() and t[5:].isdigit() and 1 <= int(t[5:]) <= 12


def zuschlag(werkstoff_id, kategorie, zeilen, stichtag=None):
    """(Zuschlag €/t, Zeile) für den Werkstoff zum Monat des Stichtags oder (None, None)."""
    m = monat(stichtag)
    passend = []
    for z in zeilen or ():
        zm = str(z.get("monat") or "").strip()
        w = _n(z.get("zuschlag"))
        if not monat_gueltig(zm) or zm > m or w is None:
            continue
        wid, kat = z.get("werkstoff_id") or None, z.get("kategorie") or None
        if wid is not None and wid != werkstoff_id:
            continue
        if wid is None and kat is not None and kat != kategorie:
            continue
        rang = 2 if wid is not None else 1 if kat is not None else 0
        passend.append((rang, zm, z))
    if not passend:
        return None, None
    # spezifischste Zeile, darin der jüngste Monat bis zum Stichtag
    rang = max(r for r, _, _ in passend)
    z = max((x for x in passend if x[0] == rang), key=lambda x: x[1])[2]
    return _n(z.get("zuschlag")), z


def anwenden(werkstoffe, zeilen, stichtag=None):
    """Werkstoff-Zeilen {ID: Zeile} mit Tonnenpreis = Basis + Zuschlag (neue dicts, Eingabe bleibt unverändert);
    dazu tonnenpreis_basis, index_zuschlag und index_monat in den betroffenen Zeilen. Ohne Zeilen: Eingabe selbst."""
    if not zeilen:
        return werkstoffe
    out = {}
    for wid, w in werkstoffe.items():
        basis = _n((w or {}).get("tonnenpreis"))
        zs, z = zuschlag(wid, (w or {}).get("kategorie"), zeilen, stichtag)
        if basis is None or not zs:
            out[wid] = w
            continue
        out[wid] = dict(w, tonnenpreis=max(0.0, basis + zs), tonnenpreis_basis=basis, index_zuschlag=zs,
                        index_monat=z.get("monat"))
    return out


def text(w):
    """'Tonnenpreis 1.850 €/t = Basis 1.700 + Materialindex 2026-11 150 €/t' oder ''."""
    from .stammdaten import zahl_als_text as zahl
    if not w or w.get("index_zuschlag") is None:
        return ""
    return (f"Tonnenpreis {zahl(w['tonnenpreis'], 0)} €/t = Basis {zahl(w['tonnenpreis_basis'], 0)} + Materialindex "
            f"{w.get('index_monat')} {zahl(w['index_zuschlag'], 0)} €/t")


def pruefung(zeilen):
    """Fehlertexte der Tabelle (Monat falsch geschrieben)."""
    return [f"Materialindex: Monat „{z.get('monat')}“ bitte als JJJJ-MM schreiben (z. B. 2026-11)"
            for z in zeilen or () if z.get("monat") and not monat_gueltig(z.get("monat"))]
