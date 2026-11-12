"""Teil wenden (Plan ArTube-Unterlagen G6/G8, Patrick 12.11.2026 „Auch einbauen aber so daß das Teil als Duplikat
gedreht angelegt wird, Stückzahl wird dann automatisch aufgeteilt was am sinnvollsten ist“).

Ausnahme zur Regel „Rohre mit Konturen, Gehrung oder Nahtvorgabe nie drehen“: das Original bleibt ungedreht, ein
Duplikat der Position mit 'Gewendet (Ende B zuerst)' = ja läuft um die senkrechte Achse gewendet durch die Maschine
(Ende B vorn). Das Teil selbst ist dasselbe (gleiche Konturen, gleiche STEP, nichts verschoben); nur der
Schnittplan sieht seine Enden getauscht: gerade/schräg, Schnittlänge, Gehrung (Richtung von Ende A gesehen
gespiegelt: rechts <-> links) und die feste Naht. So legen sich z. B. Gehrungen besser ineinander oder ein Teil mit
geradem Ende A darf als letztes in den Greiferrest. Die Stückzahl teilt aufteilen() so auf, dass die wenigsten
Stangen nötig sind (bei Gleichstand mit dem wenigsten Verschnitt, sonst möglichst wenig gewendet).
Ohne Qt."""
import json

from . import naht

JA = "ja"
FELDER_TAUSCH = (("a_gerade", "b_gerade"), ("a_schnitt", "b_schnitt"), ("a_ende", "b_ende"))
MAX_VERSUCHE = 25           # so viele Aufteilungen werden höchstens gerechnet (große Stückzahl: in Stufen)


def gewendet(p):
    return (p or {}).get("gewendet") == JA


def spiegeln(richtung):
    """Richtung [°] von Ende A gesehen nach dem Wenden um die senkrechte Achse: rechts <-> links."""
    return None if richtung is None else (360.0 - float(richtung)) % 360.0


def _ende_gespiegelt(text):
    try:
        d = json.loads(text) if text else None
    except (TypeError, ValueError):
        return text
    if not isinstance(d, dict) or d.get("richtung") is None:
        return text
    try:
        return json.dumps(dict(d, richtung=spiegeln(d["richtung"])))
    except (TypeError, ValueError):
        return text


def ansicht(p):
    """Position, wie der Schnittplan sie gewendet sieht (Enden getauscht, Richtungen gespiegelt); ungewendet p."""
    if not gewendet(p):
        return p
    q = dict(p, _gewendet=True)
    for a, b in FELDER_TAUSCH:
        q[a], q[b] = p.get(b), p.get(a)
    q["a_ende"], q["b_ende"] = _ende_gespiegelt(q.get("a_ende")), _ende_gespiegelt(q.get("b_ende"))
    return q


def erlaubt(p):
    """'' = darf gewendet werden, sonst der Grund."""
    from . import baugruppe, satzgruppen
    from .angebot import kein_laserteil
    p = p or {}
    if gewendet(p):
        return "ist schon das gewendete Duplikat"
    if p.get("wenden") == "nein":
        return "Wenden nicht erlaubt (Sichtseite, Folie oder Schliff)"
    if kein_laserteil(p):
        return "kein Rohrlaserteil"
    if baugruppe.zuordnung(p)[0] or satzgruppen.name(p):
        return "Teil eines Satzes oder einer Schweißbaugruppe (dort Stückzahl je Satz)"
    stk = p.get("stueck")
    if not isinstance(stk, (int, float)) or stk < 2:
        return "Stückzahl unter 2"
    gleich = all((p.get(a) or None) == (p.get(b) or None) for a, b in FELDER_TAUSCH) and \
        naht.ende_lesen(p.get("a_ende")) is None
    if gleich:
        return "beide Enden gleich, Wenden ändert nichts"
    return ""


def _kandidaten(n):
    if n - 1 <= MAX_VERSUCHE:
        return list(range(0, n))
    schritt = n / MAX_VERSUCHE
    return sorted({0} | {int(round(i * schritt)) for i in range(1, MAX_VERSUCHE)} | {n // 2}) or [0]


def _bewertung(erg, profil, werkstoff):
    st = [s for s in erg.get("stangen") or () if s.get("profil") == profil and s.get("werkstoff") == werkstoff]
    return len(st), sum(float(s.get("verlust") or 0) for s in st)


def aufteilen(kopf, positionen, i, k, tabellen=None, einst=None):
    """Beste Aufteilung der Stückzahl von Position i auf Original und gewendetes Duplikat:
    dict(gewendet = Stück im Duplikat (0 = Wenden spart nichts), stangen, stangen_ohne, verlust, verlust_ohne).
    Gerechnet werden nur die Positionen derselben Stangengruppe (Profil und Werkstoff)."""
    from . import rechnen
    p = positionen[i]
    n = int(p["stueck"])
    gruppe = [q for q in positionen if q.get("profil_id") == p.get("profil_id")
              and q.get("werkstoff_id") == p.get("werkstoff_id") and q is not p]
    beste = None
    for w in _kandidaten(n):
        liste = gruppe + [dict(p, stueck=n - w)] + ([dict(p, stueck=w, gewendet=JA, id=None)] if w else [])
        erg = rechnen.optimieren(kopf, liste, k, tabellen, einst)
        st, verlust = _bewertung(erg, p.get("profil_id"), p.get("werkstoff_id"))
        wert = (st, round(verlust, 1), w)
        if w == 0:
            ohne = (st, verlust)
        if beste is None or wert < beste[0]:
            beste = (wert, w)
    (st, verlust, _), w = beste
    return dict(gewendet=w, stangen=st, verlust=verlust, stangen_ohne=ohne[0], verlust_ohne=ohne[1])


def klemmt(p):
    """Hinweistext, wenn Ende B einen komplexen Anschnitt hat (3D-Ende aus der STEP, Sattel/Durchdringung) und Ende A
    gerade ist: das Teil kann beim Abtrennen klemmen und sich nicht lösen; gewendet wird Ende B vorn geschnitten.
    Sonst None."""
    from . import schneidweg as sw
    if gewendet(p) or (p or {}).get("a_gerade") == "nein" or (p or {}).get("wenden") == "nein":
        return None
    e = sw.lesen((p or {}).get("technik")) or {}
    b = e.get("b") or {}
    gegen = isinstance(b.get("gegen"), dict) and sw._z(b["gegen"].get("d")) > 0
    if b.get("form") == sw.FORM_3D or sw._z(b.get("sattel")) > 0 or gegen:
        return ("Komplexer Anschnitt an Ende B: das Teil kann beim Abtrennen klemmen – Vorschlag „Teil wenden“ "
                "(gewendetes Duplikat, Ende B vorn)")
    return None
