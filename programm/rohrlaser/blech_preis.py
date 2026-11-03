"""EK eines Blechteils im Angebot: berechneter Richtpreis oder eingeholtes Angebot des Lieferanten (Patrick
03.11.2026: „Der Preis soll später durch eingeholte Angebote änderbar sein … einfach per Klick im Angebot
überschreibbar“).

Der Richtpreis wird immer im Blech-Editor berechnet (blech.rechnen) und als Staffelzeile „ab Stückzahl“ im
Zukaufartikel eingetragen; die Position merkt sich diese Zeilen in technik 'richtpreise'. Jede andere Staffelzeile
des Preisstands ist ein Angebotspreis (aus „EK eintragen …“, der Spalte „EK Blech“ oder der Übersicht Bleche). Solange
ein Angebotspreis gilt, ersetzt ein neu berechneter Richtpreis ihn nicht; leeren setzt auf den Richtpreis zurück.
Ohne Qt."""
from . import blech, rechnen, zukauf


def _rund(x):
    return round(float(x), 2)


def stand(p, daten=None):
    """EK-Stand eines Blechteils der Position p oder None (kein Blech aus dem Blech-Editor bzw. STEP):
    dict(ek [€/St oder None], richtpreis [€/St oder None], angebot (True = Angebotspreis gilt), lieferant, menge,
    artikel_id). daten = Blech-Daten (werkstoffe, laser, einst) für den Richtpreis, sonst der gemerkte."""
    e = blech.lesen(p.get("technik"))
    liste = zukauf.json_liste(p.get("zukauf"))
    if e is None or not liste or not rechnen.ist_zukaufteil(p) or liste[0].get("artikel_id") is None:
        return None
    st = liste[0].get("stand") or {}
    bezug = st.get("bezug") or {}
    menge = float(zukauf.dez(liste[0].get("menge")) or 1) * float(zukauf.bezugsmenge(liste[0], p) or 0)
    ek, zeile = zukauf.ek_je_einheit(bezug, menge or 1)
    ek = float(ek) if ek is not None and ek > 0 else None
    merk = {(float(r["ab"]), _rund(r["preis"])) for r in e.get("richtpreise") or ()
            if isinstance(r, dict) and isinstance(r.get("ab"), (int, float)) and isinstance(r.get("preis"), (int, float))}
    angebot = bool(zeile is not None and ek is not None and merk
                   and (float(zeile["ab"]), _rund(zeile["preis"])) not in merk)
    rp = None
    if daten:
        erg = blech.rechnen(dict(e, stueck=p.get("stueck") or e.get("stueck")), daten.get("werkstoffe") or {},
                            daten.get("laser") or daten.get("laserdaten") or [], daten.get("einst"))
        rp = erg.get("richtpreis")
    if rp is None and merk:
        ab = max(1.0, float(p.get("stueck") or 1))
        passend = sorted((x for x in merk if x[0] <= ab), key=lambda x: x[0]) or sorted(merk)
        rp = passend[-1][1]
    return dict(ek=ek, richtpreis=rp, angebot=angebot, lieferant=bezug.get("lieferant"), menge=menge,
                artikel_id=liste[0]["artikel_id"], angebotspreis=e.get("angebotspreis"))


def text(s):
    """Kurztext für die Spalte „EK Blech“, z. B. '12,40' oder '' ohne EK."""
    return rechnen.zahl(s["ek"], 2) if s and s.get("ek") is not None else ""


def tooltip(s):
    if not s:
        return ""
    rp = f"{rechnen.zahl(s['richtpreis'], 2)} €" if s.get("richtpreis") is not None else "–"
    if s.get("angebot"):
        a = s.get("angebotspreis") or {}
        von = a.get("lieferant") or s.get("lieferant") or ""
        return (f"Angebotspreis {text(s)} € je Stück" + (f" von {von}" if von else "")
                + (f" ({a['datum']})" if a.get("datum") else "")
                + f". Berechneter Richtpreis zum Vergleich: {rp}.\nKlicken und neuen Preis eintragen; leeren = "
                "wieder Richtpreis.")
    return (f"Richtpreis {rp} je Stück (berechnet im Blech-Editor, EK-Vorschlag).\nKlicken und eingeholten "
            "Angebotspreis des Lieferanten eintragen; er gilt dann statt des Richtpreises.")
