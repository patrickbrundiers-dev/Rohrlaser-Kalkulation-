"""Preislücke beim Tonnenpreis (Plan Kalkulation 11.11.2026, A1, Freigabe „Alle Empfehlungen“).

Hat ein Profil im Angebot keinen eigenen Preis (kein €/m im Angebot, keine Zeile in 'Lieferlängen' mit Preis, keine
gültige Zeile in 'Preise'), rechnet das Material still mit dem Tonnenpreis des Werkstoffs. Liegt der deutlich unter
den Profilpreisen ähnlicher Rohre, rechnet das Angebot zu billig (Probe 11.11.: RR 42,4x2,0 S355 ohne Profilpreis
213,56 € gegen 246,04 € in S235 mit Profilpreis 1,45 €/kg).

Ähnlich = gleiche Profilform und gleiche Werkstoff-Kategorie, mit gültiger Zeile in 'Preise'; gewählt wird die
nächste Abmessung (A, B und Wand relativ), bei Gleichstand derselbe Werkstoff. Ihr Preis wird in €/kg umgerechnet
und bei anderem Werkstoff mit dem Verhältnis der Tonnenpreise angepasst (S355 teurer als S235). Ist der Tonnenpreis
um mehr als die Schwelle (Einstellung preisluecke_schwelle, Vorgabe 10 %, 0 = aus) billiger, meldet der
Angebots-Check eine WARNUNG; „Erledigen“ legt den Vorschlag als Zeile in 'Preise' an (Rückgängig löscht sie wieder).
Nur Hinweis und Vorschlag: ohne „Erledigen“ ändert sich kein Preis. Ohne Qt."""
import datetime

SCHWELLE_VORGABE = 10.0         # %
AKTION = "preisluecke"


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _kg_m(profil_id, werkstoff_id, k):
    from .rechnen import kg_je_m
    return kg_je_m(profil_id, werkstoff_id, k)


def eur_kg(zeile, k):
    """Preis einer Zeile aus 'Preise' in €/kg (None, wenn das Gewicht fehlt)."""
    basis, preis = zeile.get("basis"), _n(zeile.get("preis"))
    if basis == "€/kg":
        return preis
    kgm = _kg_m(zeile.get("profil_id"), zeile.get("werkstoff_id"), k)
    if not kgm:
        return None
    if basis == "€/m":
        return preis / kgm
    if basis == "€/Stange" and _n(zeile.get("lieferlaenge")) > 0:
        return preis / (kgm * zeile["lieferlaenge"] / 1000)
    return None


def _abstand(p, q):
    """Relativer Abstand zweier Profilzeilen (A, B, Wand)."""
    d = 0.0
    for f in ("a", "b", "wand"):
        x, y = _n(p.get(f)), _n(q.get(f))
        if x or y:
            d += abs(x - y) / max(x, y)
    return d


def aehnlich(profil_id, werkstoff_id, k, tabellen):
    """Nächster ähnlicher Profilpreis: dict(profil_id, werkstoff_id, eur_kg (angepasst), roh (€/kg der Zeile),
    zeile, faktor) oder None."""
    from .rechnen import kategorie
    from .stammdaten import PREISE, pruefen
    pr = k.profile.get(profil_id)
    if not pr:
        return None
    kat = kategorie(werkstoff_id, k)
    tonne = _n((k.werkstoffe.get(werkstoff_id) or {}).get("tonnenpreis"))
    beste = None
    for z in tabellen.get("preise") or ():
        q = k.profile.get(z.get("profil_id"))
        if not q or q.get("form") != pr.get("form") or kategorie(z.get("werkstoff_id"), k) != kat:
            continue
        if (z.get("profil_id"), z.get("werkstoff_id")) == (profil_id, werkstoff_id) or pruefen(PREISE, z, k) != "OK":
            continue
        roh = eur_kg(z, k)
        if not roh:
            continue
        schl = (_abstand(pr, q), z.get("werkstoff_id") != werkstoff_id)
        if beste is None or schl < beste[0]:
            beste = (schl, z, roh)
    if beste is None:
        return None
    _, z, roh = beste
    faktor = 1.0
    if z["werkstoff_id"] != werkstoff_id:
        t2 = _n((k.werkstoffe.get(z["werkstoff_id"]) or {}).get("tonnenpreis"))
        if tonne > 0 and t2 > 0:
            faktor = tonne / t2
    return dict(profil_id=z["profil_id"], werkstoff_id=z["werkstoff_id"], eur_kg=roh * faktor, roh=roh, zeile=z,
                faktor=faktor)


def schwelle(einst):
    w = (einst or {}).get("preisluecke_schwelle")
    return SCHWELLE_VORGABE if w is None or w == "" else _n(w)


def luecken(kopf, positionen, k, tabellen, einst=None):
    """Je Profil + Werkstoff des Angebots mit Tonnenpreis deutlich unter dem ähnlichen Profilpreis ein dict(profil_id,
    werkstoff_id, tonne_kg, vorschlag (aehnlich), prozent, zeilen [Positionsindex])."""
    from .rechnen import beigestellt, kein_laserteil, lieferlaengen, preis_zeile
    grenze = schwelle(einst)
    if grenze <= 0:
        return []
    out, gesehen = [], {}
    for i, p in enumerate(positionen):
        pid, wid = p.get("profil_id"), p.get("werkstoff_id")
        if not pid or not wid or kein_laserteil(p) or _n(p.get("preis_m")) > 0 or beigestellt(p):
            continue
        if (pid, wid) in gesehen:
            if gesehen[(pid, wid)] is not None:
                gesehen[(pid, wid)]["zeilen"].append(i)
            continue
        gesehen[(pid, wid)] = None
        if preis_zeile(pid, wid, k, tabellen) is not None:
            continue
        if any(z.get("basis") and _n(z.get("preis")) > 0 for z in lieferlaengen(pid, wid, k, tabellen, einst,
                                                                                    auto=False)):
            continue
        tonne = _n((k.werkstoffe.get(wid) or {}).get("tonnenpreis")) / 1000
        v = aehnlich(pid, wid, k, tabellen)
        if not v or tonne <= 0 or tonne >= v["eur_kg"] * (1 - grenze / 100):
            continue
        e = dict(profil_id=pid, werkstoff_id=wid, tonne_kg=tonne, vorschlag=v,
                 prozent=(v["eur_kg"] - tonne) / v["eur_kg"] * 100, zeilen=[i])
        gesehen[(pid, wid)] = e
        out.append(e)
    return out


def _z(w, stellen=2):
    return f"{w:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def text(e):
    v = e["vorschlag"]
    quelle = v["profil_id"] + ("" if v["werkstoff_id"] == e["werkstoff_id"] else f" {v['werkstoff_id']}")
    anpass = (f", umgerechnet mit dem Tonnenpreis-Verhältnis {_z(v['faktor'], 3)}" if abs(v["faktor"] - 1) > 1e-9
              else "")
    return (f"{e['profil_id']} {e['werkstoff_id']}: kein eigener Preis – gerechnet mit Tonnenpreis "
            f"{_z(e['tonne_kg'])} €/kg, ähnliches Profil {quelle} kostet {_z(v['roh'])} €/kg{anpass} "
            f"(Tonnenpreis {_z(e['prozent'], 0)} % billiger)")


def punkte(kopf, positionen, k, tabellen, einst=None):
    """Punkte für den Angebots-Check (WARNUNG mit „Erledigen“)."""
    from . import angebot_check
    out = []
    for e in luecken(kopf, positionen, k, tabellen, einst):
        nr = [str(positionen[i].get("pos") or i + 1) for i in e["zeilen"]]
        out.append(angebot_check.Punkt(
            angebot_check.WARNUNG, text(e), f"pos:{e['zeilen'][0]}",
            "Pos. " + ", ".join(nr[:6]) + (" …" if len(nr) > 6 else "")
            + f" – „Erledigen“ legt {_z(e['vorschlag']['eur_kg'])} €/kg als Profilpreis an", aktion=AKTION))
    return out


def uebernehmen(db, liste, heute=None):
    """Vorschläge als Zeilen in 'Preise' anlegen (nur, wo es noch keine Zeile gibt). Ergebnis: neue Zeilen-IDs."""
    heute = (heute or datetime.date.today()).isoformat()
    da = {(z.get("profil_id"), z.get("werkstoff_id")) for z in db.zeilen("preise")}
    ids = []
    for e in liste:
        if (e["profil_id"], e["werkstoff_id"]) in da:
            continue
        v = e["vorschlag"]
        quelle = v["profil_id"] + ("" if v["werkstoff_id"] == e["werkstoff_id"] else f" {v['werkstoff_id']}")
        ids.append(db.neu("preise", dict(
            profil_id=e["profil_id"], werkstoff_id=e["werkstoff_id"], basis="€/kg", preis=round(v["eur_kg"], 2),
            gueltig_ab=heute, lieferant=v["zeile"].get("lieferant"),
            bemerkung=f"übernommen von {quelle} (Preislücke Tonnenpreis), bitte beim Lieferanten bestätigen")))
    return ids
