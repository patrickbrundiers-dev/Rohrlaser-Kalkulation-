"""Füllteile (Plan PROfirst-/LogiTRACE-Handbücher 12.11.2026, H3; nur Vorschlag).

Wiederholteile, die ausdrücklich auf Lager gefertigt werden dürfen (Einstellung 'fuellteile', je Zeile „Artikel;
Profil-ID; Werkstoff-ID; Länge [mm]; höchstens Stück“), können freie Stangenenden eines Auftrags füllen. Das Programm
schlägt je Stange vor, wie viele davon noch hinter das letzte Teil passen (vor dem Greiferrest, mit einem
Schnittverlust je Teil). Es plant sie nie selbst ein und ändert weder Schnittplan noch Preis: Füllteile sind
Fertigteile, keine Reste (Regel „kein Restelager, Verschnitt nur melden“ bleibt)."""
import re

EINSTELLUNG = "fuellteile"


def liste_lesen(text):
    """[dict(artikel, profil, werkstoff, laenge, max)] aus dem Text der Einstellung; unlesbare Zeilen entfallen."""
    out = []
    for zeile in str(text or "").splitlines():
        teile = [t.strip() for t in zeile.split(";")]
        if len(teile) < 4 or not teile[0] or not teile[1] or not teile[2]:
            continue
        try:
            laenge = float(teile[3].replace(",", "."))
        except ValueError:
            continue
        m = re.match(r"\d+", teile[4]) if len(teile) > 4 else None
        if laenge > 0:
            out.append(dict(artikel=teile[0], profil=teile[1], werkstoff=teile[2], laenge=laenge,
                            max=int(m.group()) if m else None))
    return out


def vorschlaege(ergebnis, liste, kerf=0.0):
    """Je Stange mit Platz: [dict(nr, profil, werkstoff, frei, artikel, laenge, stueck)]; je Füllteil höchstens
    'max' Stück über alle Stangen. Längste Füllteile zuerst, je Stange so viele wie passen."""
    out, rest_max = [], {i: f["max"] for i, f in enumerate(liste)}
    for s in (ergebnis or {}).get("stangen") or ():
        if s.get("beistellung") or s.get("werkstuecke"):
            continue
        belegt = s["end"] + sum(t["laenge"] for t in s["teile"]) + s["verlust"]
        frei = s["stange"] - s["greif"] - belegt
        for i, f in sorted(enumerate(liste), key=lambda x: -x[1]["laenge"]):
            if f["profil"] != s["profil"] or f["werkstoff"] != s["werkstoff"]:
                continue
            n = int((frei + 1e-6) // (f["laenge"] + kerf)) if frei > 0 else 0
            if rest_max[i] is not None:
                n = min(n, rest_max[i])
            if n <= 0:
                continue
            out.append(dict(nr=s["nr"], profil=s["profil"], werkstoff=s["werkstoff"], frei=round(frei, 1),
                            artikel=f["artikel"], laenge=f["laenge"], stueck=n))
            frei -= n * (f["laenge"] + kerf)
            if rest_max[i] is not None:
                rest_max[i] -= n
    return out


def text(v):
    if not v:
        return "Füllteile: auf keiner Stange ist Platz für ein eingetragenes Füllteil."
    summe = {}
    for x in v:
        summe[x["artikel"]] = summe.get(x["artikel"], 0) + x["stueck"]
    return ("Füllteile (nur Vorschlag, nicht eingeplant): " + ", ".join(f"{a} {n} Stk" for a, n in summe.items())
            + " auf Stange " + ", ".join(str(x["nr"]) for x in v) + ".")
