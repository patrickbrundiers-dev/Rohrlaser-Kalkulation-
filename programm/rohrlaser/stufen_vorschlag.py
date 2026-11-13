"""Sinnvolle Staffelstufen vorschlagen (Roadmap Kalkulation Phase 2, OFFER-004; Freigabe Patrick 13.11.2026 „Ganze
Phase 2 nach Empfehlung“).

Staffeln werden nie automatisch angelegt (Regel Patrick). Der Knopf „Sinnvolle Stufen …“ im Reiter Staffeln rechnet
das Angebot probeweise mit mehreren Mengen (Mengen des Angebots × Faktor, wie die Standard-Staffeln) und zeigt je
Faktor: Stangen, Stückpreis gegenüber dem Angebot, Anteil von Rüsten und Programmierung am Preis. Bleibt auf den
Stangen Platz, wird die Menge einer Position ohne Satz bis zur vollen Stange erhöht (wie CAM-010, mehrmenge.py) und
mit einer zweiten Probe geprüft: mehr Teile ohne weitere Stange („Stangensprung“).

Empfohlen (vorangehakt) sind Stufen, an denen der Stückpreis spürbar sinkt (PREIS_SPRUNG gegenüber der vorigen
Zeile) und die erste Stufe, ab der Rüsten und Programmierung unter RUEST_GRENZE des Preises liegen. Übernommen wird
nur per Klick. Ohne Qt."""
from .stammdaten import zahl_als_text as zahl

FAKTOREN = (2, 3, 5, 10, 20, 50)
PREIS_SPRUNG = 0.05         # 5 % günstiger je Teil als die vorige Zeile
RUEST_GRENZE = 0.05         # Rüsten und Programmierung unter 5 % des Preises
HOECHSTENS_EMPFOHLEN = 3


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _mengen_positionen(positionen, mengen):
    """Positionen mit den Stückzahlen der Stufe (Schlüssel = Satz oder Pos.-Nr.)."""
    from .angebot import aktiv
    from .staffeln import je_satz, txt
    out = []
    for p in positionen:
        s = txt(p.get("satz"))
        schl = s or txt(p.get("pos"))
        if aktiv(p) and schl in mengen:
            out.append(dict(p, stueck=mengen[schl] * (je_satz(p) if s else 1)))
        else:
            out.append(dict(p))
    return out


def _lauf(kopf, positionen, k, tabellen, einst):
    """Optimieren und kalkulieren: (Ergebnis, Zeilen, Summen) oder None bei Fehlern."""
    from .rechnen import kalkulation, optimieren
    erg = optimieren(kopf, positionen, k, tabellen, einst)
    if erg.get("fehler"):
        return None
    zeilen, summen = kalkulation(kopf, positionen, erg, k, tabellen, einst)
    return erg, zeilen, summen


def _werte(positionen, zeilen, einst):
    """(Warenwert, Teile, Einmalanteil) aus den Kalkulationszeilen."""
    from .angebot import aktiv
    from .ausgabe import einmal_anteil
    wert = teile = einmal = 0.0
    for p, z in zip(positionen, zeilen):
        if not aktiv(p) or not z:
            continue
        c = _n(z.get("stueck", p.get("stueck")))
        wert += _n(z.get("preis_teil")) * c
        teile += c
        einmal += einmal_anteil(z, einst) * c
    return wert, teile, einmal


def vorschlaege(kopf, positionen, k, tabellen, einst, faktoren=FAKTOREN):
    """[dict(faktor, mengen {Schlüssel: Menge}, stangen, preis_index, einmal_anteil, voll (Schlüssel mit aufgefüllter
    Stange), empfohlen, grund)]; preis_index = Ø Preis je Teil ÷ Ø Preis je Teil im Angebot. Leer ohne Mengen."""
    from . import mehrmenge
    from .staffeln import auswahl, standard_menge, txt
    basis_mengen = {schl: menge for schl, _, menge in auswahl(positionen) if menge}
    if not basis_mengen:
        return []
    basis = _lauf(kopf, positionen, k, tabellen, einst)
    if basis is None:
        return []
    w0, t0, e0 = _werte(positionen, basis[1], einst)
    preis0 = w0 / t0 if t0 else 0.0
    if preis0 <= 0:
        return []
    zeilen = [dict(faktor=1, mengen=basis_mengen, stangen=len(basis[0].get("stangen") or ()), preis_index=1.0,
                   einmal_anteil=e0 / w0 if w0 else 0.0, voll=[], empfohlen=False, grund="Mengen des Angebots")]
    for f in faktoren:
        mengen = {s: standard_menge(m, f) for s, m in basis_mengen.items()}
        pos = _mengen_positionen(positionen, mengen)
        r = _lauf(kopf, pos, k, tabellen, einst)
        if r is None:
            continue
        voll = []
        mehr = mehrmenge.kandidaten(kopf, pos, r[0], k)     # Platz auf den Stangen: bis zur vollen Stange
        if mehr:
            mengen2 = dict(mengen)
            for i, n in mehr.items():
                schl = txt(pos[i].get("pos"))
                if schl in mengen2:
                    mengen2[schl] += n
            pos2 = _mengen_positionen(positionen, mengen2)
            r2 = _lauf(kopf, pos2, k, tabellen, einst)
            if r2 is not None and len(r2[0].get("stangen") or ()) <= len(r[0].get("stangen") or ()):
                voll = sorted(s for s in mengen2 if mengen2[s] != mengen[s])
                mengen, pos, r = mengen2, pos2, r2
        w, t, e = _werte(pos, r[1], einst)
        if not t or not w:
            continue
        zeilen.append(dict(faktor=f, mengen=mengen, stangen=len(r[0].get("stangen") or ()), preis_index=w / t / preis0,
                           einmal_anteil=e / w, voll=voll, empfohlen=False, grund=""))
    _empfehlen(zeilen)
    return zeilen[1:]


def _empfehlen(zeilen):
    """Empfehlung und Grund setzen (zeilen[0] = Angebot)."""
    n = 0
    ruest_da = zeilen[0]["einmal_anteil"] < RUEST_GRENZE
    for vor, z in zip(zeilen, zeilen[1:]):
        gruende = []
        if vor["preis_index"] > 0 and z["preis_index"] <= vor["preis_index"] * (1 - PREIS_SPRUNG):
            gruende.append(f"{zahl(100 * (1 - z['preis_index'] / vor['preis_index']), 0)} % günstiger je Teil als "
                           "die vorige Zeile")
        if not ruest_da and z["einmal_anteil"] < RUEST_GRENZE:
            ruest_da = True
            gruende.append(f"Rüsten und Programmierung erstmals unter {zahl(100 * RUEST_GRENZE, 0)} % des Preises")
        if z["voll"]:
            gruende.append("Stangen aufgefüllt (" + ", ".join(f"Pos. {s}" for s in z["voll"]) + ")")
        z["grund"] = "; ".join(gruende)
        if gruende[:1] and not gruende[0].startswith("Stangen") and n < HOECHSTENS_EMPFOHLEN:
            z["empfohlen"] = True
            n += 1


def mengen_text(mengen, positionen=None):
    """„Pos. 1: 50 · Satz A: 20“."""
    from .staffeln import txt
    saetze = {txt(p.get("satz")) for p in positionen or () if txt(p.get("satz"))}
    return " · ".join(f"{'Satz' if s in saetze else 'Pos.'} {s}: {zahl(m, 0)}" for s, m in mengen.items())


def anlegen(db, angebot_id, zeilen):
    """Je gewählte Zeile eine Stufe mit ihren Mengen anlegen (nur per Klick). Ergebnis: IDs der neuen Stufen."""
    ids = []
    for z in zeilen:
        sid = db.staffel_stufe_neu(angebot_id)
        for schl, menge in z["mengen"].items():
            db.staffel_neu(angebot_id, dict(schluessel=schl, menge=menge, stufe_id=sid))
        ids.append(sid)
    return ids
