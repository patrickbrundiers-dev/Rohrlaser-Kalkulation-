"""Virtuelles Bauteil: so wird das Teil gelasert (Patrick 26.10.2026, „Können wir mit dem virtuellen Bauteil noch mehr
machen?“ – Freigabe 1, 2, 4). Winkel/U aus größerem Profil (step_schenkel: Teil ∪ Stege 2 mm) und offen gezeichnete
Rohre (step_offenes_rohr: Teil ∪ Ringe 2 mm, Fenster ausgeschnitten) misst die STEP-Messung als eigenen Körper.

- STEP-Export: STEP-Import.exe --virtuell ORDNER schreibt den Körper je Teil als k<Nr>.step (in Dateilage, die
  Kundendatei bleibt unverändert); das Programm speichert ihn über den Rechtsklick bzw. den Schneidweg-Rechner.
- Zeichnung und Werkstattpapiere zeigen die Stege rot mit Hinweis.
- Stege bleiben dran (Vorgabe) oder werden abgetrennt (je Position, Schneidweg-Rechner bzw. Rechtsklick; Freigabe
  „Je nach Kunde wählbar“): abgetrennt kommt die Zusatzarbeit ZUSATZ_STEGE (€/Stück) dazu und das Gewicht ist das
  des gezeichneten Teils, sonst das des Teils mit Stegen.
- Gewicht je Teil aus dem Volumen (positionen.technik volumen_teil bzw. volumen_gezeichnet, mm³) statt aus Metergewicht
  × Länge; der Rest des Querschnitts ist Abfall (abfall_kg).

Schlüssel in positionen.technik (schneidweg.lesen): stege_virtuell (Winkel/U) bzw. offen_virtuell (Rohr), volumen_teil,
volumen_gezeichnet, l_step, step_datei, step_koerper, stege_abtrennen."""
import json

STEG = 2.0                                       # mm, wie step_offenes_rohr.STEG
ZUSATZ_STEGE, STEGE_PREIS = "Stege abtrennen", 1.50     # € je Teil (Beispielpreis, Stammdaten Zusatzarbeiten)
FARBE = "#E00000"                                # wie die 3D-Ansicht (Arten ES, EW)
ARTEN_ROT = ("ES", "EW", "EO")                   # Netz-Arten der Stege bzw. Ringe


def _z(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _sicherheit(m, name):
    for teil in str(m.get("sicherheit") or "").split(";"):
        k, _, v = teil.partition("=")
        if k == name:
            return v
    return None


def volumen(m):
    """(Volumen mit Stegen bzw. Ringen, Volumen wie gezeichnet) in mm³ aus den Messwerten oder None (kein virtuelles
    Bauteil mit Stegen)."""
    if _sicherheit(m, "stege") == "virtuell":
        virt, gez = _z(_sicherheit(m, "volumen_virtuell")), _z(m.get("volumen"))
    elif _sicherheit(m, "offene_seite") == "stege":
        try:
            offen = json.loads(m.get("geschlossen") or "null") or {}
        except ValueError:
            offen = {}
        virt, gez = _z(m.get("volumen")), _z(offen.get("volumen"))
    else:
        return None
    return (virt, gez) if virt > 0 else None


def ist_virtuell(e):
    """True, wenn die Eingaben des Schneidweg-Rechners (technik) ein virtuelles Bauteil mit Stegen sind."""
    return bool(e) and bool(e.get("stege_virtuell") or e.get("offen_virtuell"))


def technik_lesen(p):
    """technik einer Position als dict (nur wenn sie ein virtuelles Bauteil ist), sonst {} – schnell: ohne den
    Schlüssel volumen_teil wird nichts gelesen."""
    t = p.get("technik")
    if not isinstance(t, str) or '"volumen_teil"' not in t:
        return {}
    try:
        e = json.loads(t)
    except ValueError:
        return {}
    return e if isinstance(e, dict) and ist_virtuell(e) else {}


def gewicht(p, dichte):
    """Gewicht je Teil [kg] aus dem Volumen (mit Stegen, abgetrennt wie gezeichnet), auf die Teilelänge umgerechnet,
    oder None. dichte in kg/dm³."""
    e = technik_lesen(p)
    if not e or not dichte:
        return None
    vol = _z(e.get("volumen_gezeichnet")) if e.get("stege_abtrennen") else _z(e.get("volumen_teil"))
    if vol <= 0:
        return None
    lg, l_step = _z(p.get("laenge")), _z(e.get("l_step"))
    faktor = lg / l_step if lg > 0 and l_step > 0 else 1.0
    return vol * faktor * float(dichte) / 1e6


def hinweis(e, profil_id=None):
    """Satz für Zeichnung und Werkstattpapiere oder ''."""
    if not ist_virtuell(e):
        return ""
    was = "Ring" if e.get("offen_virtuell") else "Steg"
    aus = f" aus {profil_id}" if profil_id else ""
    if e.get("stege_abtrennen"):
        return (f"Virtuelles Bauteil{aus}: je ein {was} {STEG:g} mm an Ende A und B (rot) hält das Teil beim Lasern – "
                "danach abtrennen und entgraten.")
    return f"Virtuelles Bauteil{aus}: je ein {was} {STEG:g} mm an Ende A und B (rot) bleibt am Teil stehen."


def zusatz_eintragen(zusatz_json, an, katalog, quelle):
    """Spalte Zusatzarbeiten (JSON) mit ZUSATZ_STEGE × 1 (an) bzw. ohne den Eintrag dieser Quelle. Ergebnis (JSON oder
    None, fehlt = Zusatzarbeit nicht in den Stammdaten)."""
    from . import rechnen
    liste = rechnen.zusatz_liste(dict(zusatz=zusatz_json))
    kat = {z.get("name"): z for z in katalog or ()}
    out, da = [], False
    for e in liste:
        if e.get("name") == ZUSATZ_STEGE:
            if an:
                out.append(e)
                da = True
            elif e.get("quelle") != quelle:
                out.append(e)
        else:
            out.append(e)
    fehlt = False
    if an and not da:
        if ZUSATZ_STEGE in kat:
            out.append(dict(name=ZUSATZ_STEGE, menge=1, preis=None, text=None, quelle=quelle,
                            stand=rechnen.zusatz_stand(kat[ZUSATZ_STEGE])))
        else:
            fehlt = True
    return (json.dumps(out, ensure_ascii=False) if out else None), fehlt


def netz_ausschnitt(netz, ende, laenge=80.0):
    """Ende A ("a") bzw. B ("b") des 3D-Netzes (dict p/t/l, Rohrachse z): Dreiecke und Kantenzüge, die höchstens
    laenge mm vom Ende entfernt liegen – für die vergrößerten Enden in der Zeichnung."""
    p = netz.get("p") or []
    if len(p) < 9:
        return netz
    zs = p[2::3]
    lo, hi = min(zs), max(zs)
    von, bis = (lo - 0.5, lo + laenge) if ende == "a" else (hi - laenge, hi + 0.5)
    t_neu, neu_nr, p_neu = {}, {}, []

    def nummer(j):              # nur die benutzten Punkte: das Bild passt sich dem Ausschnitt an
        if j not in neu_nr:
            neu_nr[j] = len(p_neu) // 3
            p_neu.extend(p[3 * j:3 * j + 3])
        return neu_nr[j]
    for art, idx in (netz.get("t") or {}).items():
        behalten = [nummer(j) for i in range(0, len(idx) - 2, 3)
                    if all(von <= p[3 * j + 2] <= bis for j in idx[i:i + 3]) for j in idx[i:i + 3]]
        if behalten:
            t_neu[art] = behalten
    l_neu = {}
    for art, zuege in (netz.get("l") or {}).items():
        for zug in zuege:
            lauf = []
            for i in range(0, len(zug) - 2, 3):
                if von <= zug[i + 2] <= bis:
                    lauf.extend(zug[i:i + 3])
                    continue
                if len(lauf) >= 6:
                    l_neu.setdefault(art, []).append(lauf)
                lauf = []
            if len(lauf) >= 6:
                l_neu.setdefault(art, []).append(lauf)
    if not p_neu:
        return netz
    return {k: v for k, v in dict(netz, p=p_neu, t=t_neu, l=l_neu).items() if k not in ("ti", "li", "ln")}
