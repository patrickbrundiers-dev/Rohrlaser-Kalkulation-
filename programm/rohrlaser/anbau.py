"""Anbauteile eines Rohrteils aus dem STEP-Import (aufgeschweißte Bolzen, Muttern, Laschen, Bleche, Kopfplatten):
je Anbauteil im Dialog 'Anbauteile prüfen' Art, Bearbeitung und Gravurlänge prüfen, bestätigen oder ausschließen.

Anbauteil (JSON-Liste der STEP-Messung, Spalte 'anbauteile'): {nr, art, quelle, z, winkel, u, seite, aufstand
{form, umfang, flaeche, durchmesser bzw. laenge/breite}, hoehe, volumen, bearbeitung, gravur_laenge, vertrauen,
hinweis} und hier dazu status offen / bestätigt / ausgeschlossen. Der Laser schneidet Anbauteile nie; er graviert nur
ihre Lage aufs Rohr (Bearbeitung, Patrick 22.10.2026, F1 a): Umriss der Aufstandsfläche, Positionsmarke (Kreuz
2 × 10 mm), Punktmarke (Kreuz 2 × 2 mm) oder keine. Ausgeschlossen = keine Gravur, bleibt aber in der Liste.

Die Gravur der Anbauteile steckt schon in der Gravur des Teils (Messung); geändert wird nur um den Unterschied
zwischen alter und neuer Wahl (anwenden), wie beim Bohrbild.
"""
import json

ARTEN = ("Bolzen", "Mutter", "Lasche", "Blech", "Kopfplatte", "Sonstiges")
BEARBEITUNGEN = ("Umriss", "Positionsmarke", "Punktmarke", "keine")
# Vorgabe je Art (wie step_geometrie.ANBAU_BEARBEITUNG)
VORGABE = {"Bolzen": "Positionsmarke", "Mutter": "Umriss", "Lasche": "Umriss", "Blech": "Umriss",
           "Kopfplatte": "keine", "Sonstiges": "Umriss"}
MARKE = 2 * 10.0        # mm Gravur der Positionsmarke (Kreuz aus zwei Strichen je 10 mm)
PUNKT = 2 * 2.0         # mm Gravur der Punktmarke (Kreuz aus zwei Strichen je 2 mm)
OFFEN, BESTAETIGT, AUSGESCHLOSSEN = "offen", "bestätigt", "ausgeschlossen"


def lesen(wert):
    """JSON-Text oder Liste -> Liste der Anbauteile (Kopien, status ergänzt)."""
    if isinstance(wert, str):
        try:
            wert = json.loads(wert or "[]")
        except ValueError:
            wert = []
    out = []
    for a in wert or []:
        if isinstance(a, dict):
            a = dict(a)
            a.setdefault("status", OFFEN)
            out.append(a)
    return out


def schreiben(liste):
    return json.dumps(liste, ensure_ascii=False) if liste else None


def umriss(a):
    """Länge des Umrisses der Aufstandsfläche [mm] oder 0 (keine Aufstandsfläche, z. B. Kopfplatte)."""
    try:
        return float((a.get("aufstand") or {}).get("umfang") or 0)
    except (TypeError, ValueError):
        return 0.0


def bearbeitungen(a):
    """Wählbare Bearbeitungen: Umriss nur mit Aufstandsfläche."""
    return [b for b in BEARBEITUNGEN if b != "Umriss" or umriss(a) > 0]


def laenge(a, bearbeitung):
    """Gravurlänge [mm] einer Bearbeitung."""
    return {"Umriss": round(umriss(a), 2), "Positionsmarke": MARKE, "Punktmarke": PUNKT}.get(bearbeitung, 0.0)


def vorgabe(a, art):
    """Vorgabe-Bearbeitung für die Art (ohne Aufstandsfläche statt Umriss die Positionsmarke)."""
    b = VORGABE.get(art, "Umriss")
    return "Positionsmarke" if b == "Umriss" and umriss(a) <= 0 else b


def wirksam(a):
    """Gravur [mm], die das Anbauteil verursacht (ausgeschlossen = 0)."""
    if a.get("status") == AUSGESCHLOSSEN:
        return 0.0
    try:
        return float(a.get("gravur_laenge") or 0)
    except (TypeError, ValueError):
        return 0.0


def gravur(liste):
    return round(sum(wirksam(a) for a in liste), 2)


def konturen(liste):
    return sum(1 for a in liste if wirksam(a) > 0)


def gravur_zuege(liste):
    """Gravur der Anbauteile als Linienzüge fürs 3D aus den Eingaben und den STEP-Export (Rille 0,1 mm):
    [[(Punkt, Normale nach außen)]] im Rohrsystem der STEP-Messung (z = Rohrachse ab Ende A). Je Anbauteil nach seiner
    Bearbeitung: Umriss der Aufstandsfläche, Kreuz 2 × 10 mm (Positionsmarke) bzw. 2 × 2 mm (Punktmarke); keine bzw.
    ausgeschlossen: nichts. Braucht die Lage aus der STEP-Messung (ab Version 0.9.118: marke, umriss_linien)."""
    import math
    out = []
    for a in liste:
        m = a.get("marke")
        if a.get("status") == AUSGESCHLOSSEN or not m or wirksam(a) <= 0:
            continue
        (mx, my, mz), (tx, ty), (nx, ny), (cx, cy) = m["m"], m["t"], m["n"], m.get("c") or (0.0, 0.0)
        r = math.hypot(mx - cx, my - cy)

        def auf_wand(x, y, z):
            if m.get("rund") and r > 0:         # Rundrohr: auf den Mantel, Normale radial
                dx, dy = x - cx, y - cy
                d = math.hypot(dx, dy) or 1.0
                return (cx + dx * r / d, cy + dy * r / d, z), (dx / d, dy / d, 0.0)
            return (x, y, z), (nx, ny, 0.0)
        b = a.get("bearbeitung")
        if b == "Umriss" and a.get("umriss_linien"):
            zuege = [[(z[i], z[i + 1], z[i + 2]) for i in range(0, len(z) - 2, 3)] for z in a["umriss_linien"]]
        elif b in ("Positionsmarke", "Punktmarke"):
            h = (MARKE if b == "Positionsmarke" else PUNKT) / 4
            zuege = [[(mx, my, mz - h), (mx, my, mz + h)],
                     [(mx + tx * h * k / 8, my + ty * h * k / 8, mz) for k in range(-8, 9)]]
        else:
            continue
        out += [[auf_wand(*q) for q in zug] for zug in zuege if len(zug) >= 2]
    return out


def eingaben_mit_gravur(e, p):
    """Eingaben e des Rohr-Editors mit der Gravur der Anbauteile der Position p (Schlüssel anbau_gravur, nur fürs 3D
    und den STEP-Export, nicht gespeichert)."""
    zuege = gravur_zuege(lesen((p or {}).get("anbauteile")))
    return dict(e or {}, anbau_gravur=zuege) if zuege else e


def unsicher(a):
    return a.get("vertrauen") == "prüfen"


def offen(liste):
    """Anzahl unsicher erkannter Anbauteile, die noch nicht bestätigt oder ausgeschlossen sind."""
    return sum(1 for a in liste if unsicher(a) and a.get("status", OFFEN) == OFFEN)


def pruefteil(liste):
    """True, wenn ein Anbauteil unsicher erkannt und nicht ausgeschlossen ist (Prüfzeit je Teil, Einstellung
    pruefzeit_anbau)."""
    return any(unsicher(a) and a.get("status") != AUSGESCHLOSSEN for a in liste)


def position_anwenden(p, neu):
    """Feldänderungen einer Angebotsposition für die neue Liste: Gravur um den Unterschied, Spalte anbauteile."""
    try:
        gravur_alt = float(p.get("gravur") or 0)
    except (TypeError, ValueError):
        gravur_alt = 0.0
    g = anwenden({"gravur": gravur_alt}, lesen(p.get("anbauteile")), neu)["gravur"]
    return {"gravur": round(g, 1) or None, "anbauteile": schreiben(neu)}


def anwenden(werte, alt, neu):
    """Neue Werte für gravur, gravur_anbau und gravur_konturen (nur die Felder, die werte hat): um den Unterschied
    zwischen der alten und der neuen Liste geändert."""
    out = {}
    for name, f in (("gravur", gravur), ("gravur_anbau", gravur), ("gravur_konturen", konturen)):
        if name not in werte:
            continue
        try:
            wert = float(werte.get(name) or 0)
        except (TypeError, ValueError):
            wert = 0.0
        wert = max(0.0, wert - f(alt) + f(neu))
        out[name] = int(round(wert)) if name == "gravur_konturen" else round(wert, 2)
    return out


def dez(x, stellen=1):
    try:
        return f"{round(float(x), stellen):g}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def lage_text(a):
    """z. B. 'z 300 mm, 0°' bzw. 'Ende A'."""
    if a.get("art") == "Kopfplatte" or str(a.get("seite") or "").startswith("Ende"):
        return a.get("seite") or "Ende"
    seite = a.get("seite") or (f"{dez(a['winkel'])}°" if a.get("winkel") is not None else "")
    return ", ".join(x for x in (f"z {dez(a['z'], 0)} mm" if a.get("z") is not None else "", seite) if x)


def aufstand_text(a):
    """z. B. 'Kreis Ø 20' oder 'Rechteck 40 × 10' (mm)."""
    s = a.get("aufstand") or {}
    if not s:
        return "keine"
    if s.get("durchmesser") is not None:
        return f"{s.get('form') or 'Kreis'} Ø {dez(s['durchmesser'])}"
    return f"{s.get('form') or ''} {dez(s.get('laenge'))} × {dez(s.get('breite'))}".strip()


def kurz(liste):
    """Kurztext für Listen, z. B. '2 Bolzen, 1 Lasche' (+ ' – 1 prüfen')."""
    if not liste:
        return ""
    zahl = {}
    for a in liste:
        if a.get("status") != AUSGESCHLOSSEN:
            zahl[a.get("art") or "Sonstiges"] = zahl.get(a.get("art") or "Sonstiges", 0) + 1
    teile = [f"{n} {art}" for art, n in zahl.items()]
    aus = sum(1 for a in liste if a.get("status") == AUSGESCHLOSSEN)
    if aus:
        teile.append(f"{aus} ausgeschlossen")
    n = offen(liste)
    return ", ".join(teile) + (f" – {n} prüfen" if n else "")
