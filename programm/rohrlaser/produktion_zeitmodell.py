"""Produktionsdaten-Intelligenz, Phase 4: Zeitmodell je Konturklasse aus den Maschinendaten (Patrick 24.11.2026: „Wenn
verschiedene Konturarten groß, mittel, klein angegeben sind, dann auch anzeigen und daraus lernen“). Ohne Qt.

Je Gruppe (Maschine × Werkstoff × Wandbereich) über viele Programme:
    reine Laserzeit (Laser an) ≈ mm_groß × a_groß + mm_mittel × a_mittel + mm_klein × a_klein + Einstiche × e
mit a = Sekunden je mm (Vorschub = 60 ÷ (1000 × a) m/min) und e = Sekunden je Einstich, gelöst als kleinste Quadrate
mit nicht negativen Werten. Gebraucht werden die Schnittlängen je Klasse aus dem NC-Schneidweg der LST und die
Laser-an-Zeit (LST-Verbrauchsgruppe 2); die BPF hat keine Zeiten und zählt hier nicht.

Ein Modell gilt erst ab MINDEST_PROGRAMME Programmen und mindestens zwei Teilen mehr als Unbekannte; seine Güte zeigt
die Gegenprobe (je Programm aus den übrigen gelernt). Das Modell ist ein Hinweis: es ändert keine Schneiddaten. Zum
Vergleich steht daneben der Vorschub je Klasse, mit dem die Kalkulation gerechnet hat (Zeit je Klasse ÷ Schnittlänge
der zugeordneten Positionen)."""
import statistics

from . import maschinendaten as md

KLASSEN = ("gross", "mittel", "klein")
KLASSE_TEXT = {"gross": "groß", "mittel": "mittel", "klein": "klein"}
MINDEST_PROGRAMME = 3
GEW_ITER = 400


def _bereich(wand):
    from . import kalibrierung
    try:
        return kalibrierung.bereich(wand)
    except (TypeError, ValueError):
        return "?"


def daten(teile):
    """Lernbare Teile: [dict(programm, gruppe, x {klasse: mm, einstiche: n}, y (Laser an s))]."""
    out = []
    for t in teile:
        m = t.get("merkmale") or {}
        y = md.w(m, "laser_an_s")
        mm = {c: md.w(m, f"mm_{c}") for c in KLASSEN}
        if not isinstance(y, (int, float)) or y <= 0 or all(not isinstance(v, (int, float)) for v in mm.values()):
            continue
        x = {c: float(v or 0.0) for c, v in mm.items()}
        x["einstiche"] = float(t.get("einstiche") or md.w(m, "einstiche") or 0.0)
        gruppe = (t.get("maschine") or "?", str(t.get("werkstoff") or "?"), _bereich(t.get("wand")))
        out.append(dict(programm=t.get("programm"), gruppe=gruppe, x=x, y=float(y)))
    return out


def nnls(zeilen, namen):
    """Kleinste Quadrate mit Werten ≥ 0 (Koordinatenabstieg, wenige Unbekannte): {Name: Wert}."""
    a = {n: 0.0 for n in namen}
    nn = {n: sum(z["x"][n] ** 2 for z in zeilen) for n in namen}
    for _ in range(GEW_ITER):
        groesste = 0.0
        for n in namen:
            if nn[n] <= 0:
                continue
            r = sum(z["x"][n] * (z["y"] - sum(a[k] * z["x"][k] for k in namen)) for z in zeilen)
            neu = max(0.0, a[n] + r / nn[n])
            groesste = max(groesste, abs(neu - a[n]))
            a[n] = neu
        if groesste < 1e-12:
            break
    return a


def _vorhersage(a, z):
    return sum(a[k] * z["x"][k] for k in a)


def modell(zeilen):
    """Modell einer Gruppe: dict(n, programme, vorschub {klasse: m/min}, einstich_s, fehler_pct (Gegenprobe), status)."""
    namen = [n for n in KLASSEN + ("einstiche",) if any(z["x"][n] > 0 for z in zeilen)]
    progs = sorted({z["programm"] for z in zeilen})
    out = dict(n=len(zeilen), programme=len(progs), vorschub={}, einstich_s=None, fehler_pct=None,
               status="zu wenig Daten")
    if not namen or len(progs) < MINDEST_PROGRAMME or len(zeilen) < len(namen) + 2:
        return out
    a = nnls(zeilen, namen)
    fehler = []
    for p in progs:     # Gegenprobe: ohne dieses Programm gelernt
        lern = [z for z in zeilen if z["programm"] != p]
        ap = nnls(lern, namen)
        fehler += [abs(_vorhersage(ap, z) / z["y"] - 1.0) for z in zeilen if z["programm"] == p and z["y"]]
    out.update(vorschub={c: round(60.0 / (1000.0 * a[c]), 2) for c in KLASSEN if c in a and a[c] > 0},
               einstich_s=round(a["einstiche"], 3) if "einstiche" in a else None,
               fehler_pct=round(100 * statistics.median(fehler), 1) if fehler else None, status="ok")
    return out


def kalkulation_vorschub(vergleich_zeilen):
    """Vorschub je Klasse, mit dem die Kalkulation gerechnet hat, je Gruppe: {gruppe: {klasse: m/min}} (Median über
    die zugeordneten Teile; Zeit je Klasse der Kalkulationszeile ÷ Schnittlänge der Position)."""
    je = {}
    for z in vergleich_zeilen:
        kz, p = z.get("kalk") or {}, z.get("position") or {}
        t = z["teil"]
        g = (t.get("maschine") or "?", str(t.get("werkstoff") or "?"), _bereich(t.get("wand")))
        for c in KLASSEN:
            s, mm = kz.get(f"zeit_{c}"), p.get(f"{c}_mm")
            if isinstance(s, (int, float)) and s > 0 and isinstance(mm, (int, float)) and mm > 0:
                je.setdefault(g, {}).setdefault(c, []).append(mm / 1000.0 / (s / 60.0))
    return {g: {c: round(statistics.median(v), 2) for c, v in d.items()} for g, d in je.items()}


def modelle(teile, vergleich_zeilen=()):
    """Alle Gruppen: [dict(gruppe, text, …modell, kalk {klasse: m/min})], größte Gruppe zuerst."""
    gr = {}
    for z in daten(teile):
        gr.setdefault(z["gruppe"], []).append(z)
    kalk = kalkulation_vorschub(vergleich_zeilen)
    out = []
    for g, zeilen in gr.items():
        out.append(dict(gruppe=g, text=" · ".join(str(x) for x in g), kalk=kalk.get(g) or {}, **modell(zeilen)))
    out.sort(key=lambda m: (m["status"] != "ok", -m["n"]))
    return out


def text(m):
    """Kurztext eines Modells für Dashboard und KI."""
    if m["status"] != "ok":
        return f"{m['text']}: {m['n']} Teile aus {m['programme']} Programmen – zu wenig Daten"
    teile = [f"{KLASSE_TEXT[c]} {v:.1f} m/min".replace(".", ",") +
             (f" (Kalkulation {m['kalk'][c]:.1f})".replace(".", ",") if c in m["kalk"] else "")
             for c, v in m["vorschub"].items()]
    if m["einstich_s"] is not None:
        teile.append(f"Einstich {m['einstich_s']:.2f} s".replace(".", ","))
    return (f"{m['text']}: " + ", ".join(teile) + f"; Gegenprobe ±{m['fehler_pct']:.1f} %".replace(".", ",")
            if m["fehler_pct"] is not None else f"{m['text']}: " + ", ".join(teile))
