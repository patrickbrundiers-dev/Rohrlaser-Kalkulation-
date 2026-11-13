"""Spiegelteile erkennen (GEO-013, Plan Phase 3 und 4, Patrick 13.11.2026 „Alles einbauen“): linkes und rechtes
Teil (z. B. Artikel -L/-R) sind dasselbe Programm, nur gespiegelt. Die Programmierzeit zählt dann einmal und wird wie
bei gleichen Teilen nach Stückzahl verteilt (rechnen.programmierung_gleich).

Spiegel heißt: gleiches Profil, gleicher Werkstoff, gleiche Länge (± 0,5 mm), gleicher Schneidweg (± 1 %) und gleiche
Einstiche, und die Konturen und Enden aus dem Schneidweg-Rechner (technik) sind nach einer Spiegelung gleich:
  längs   – an der Teilmitte (x → Länge − x, Ende A ↔ Ende B)
  quer    – an der senkrechten Ebene durch die Rohrachse (Seite vorne ↔ hinten, Winkel w → 360° − w)
  beides
Ein identisches Teil ist kein Spiegelteil (das regelt teil_gleich_schluessel). Ohne Konturen aus dem Rechner wird
nichts erkannt (lieber nicht zusammenfassen als falsch). Ohne Qt."""
import json

LAENGE_TOL, SCHNEIDWEG_TOL, X_TOL = 0.5, 0.01, 0.6
SEITE_GRAD = {"oben": 0, "vorne": 90, "unten": 180, "hinten": 270}


def _n(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else None


def _technik(p):
    t = p.get("technik")
    try:
        d = json.loads(t) if isinstance(t, str) and t else (t if isinstance(t, dict) else None)
    except ValueError:
        return None
    return d if isinstance(d, dict) and d.get("konturen") else None


def _seite(s):
    if s is None or s == "":
        return 0.0
    if isinstance(s, str):
        return float(SEITE_GRAD.get(s.strip().lower(), 0))
    return float(s) % 360


def _ende(e):
    e = e or {}
    return (round(_n(e.get("winkel")) or 0.0, 1), str(e.get("achse") or ""))


def _kontur(k, laenge, laengs, quer):
    """Vergleichbares Tupel einer Konturzeile nach der Spiegelung."""
    x = _n(k.get("x"))              # Mitte der ersten Kontur; ein Muster läuft mit abstand weiter
    if x is not None and laengs:
        n, ab = int(_n(k.get("anzahl")) or 1), _n(k.get("abstand")) or 0.0
        x = laenge - (x + (n - 1) * ab if ab > 0 else x)
    w = _seite(k.get("seite"))
    if quer:
        w = (360 - w) % 360
    werte = tuple(sorted((n, round(v, 1) if isinstance(v, float) else v) for n, v in k.items()
                         if n not in ("x", "seite", "gemessen", "quelle", "id") and not isinstance(v, (dict, list))))
    return (werte, round(w, 0), x)


def _konturen_gleich(ka, kb, laenge, laengs, quer):
    a = sorted((_kontur(k, laenge, False, False) for k in ka), key=lambda t: (repr(t[0]), t[1], t[2] or 0))
    b = sorted((_kontur(k, laenge, laengs, quer) for k in kb), key=lambda t: (repr(t[0]), t[1], t[2] or 0))
    if len(a) != len(b):
        return False
    for (wa, sa, xa), (wb, sb, xb) in zip(a, b):
        if wa != wb or abs(sa - sb) > 0.5 and abs(abs(sa - sb) - 360) > 0.5:
            return False
        if (xa is None) != (xb is None) or (xa is not None and abs(xa - xb) > X_TOL):
            return False
    return True


def _grund_gleich(p, q):
    if not p.get("profil_id") or p.get("profil_id") != q.get("profil_id"):
        return False
    if str(p.get("werkstoff_id") or "") != str(q.get("werkstoff_id") or ""):
        return False
    la, lb = _n(p.get("laenge")), _n(q.get("laenge"))
    if la is None or lb is None or abs(la - lb) > LAENGE_TOL:
        return False
    sa, sb = _n(p.get("schneidweg")), _n(q.get("schneidweg"))
    if (sa or sb) and (not sa or not sb or abs(sa - sb) > SCHNEIDWEG_TOL * max(sa, sb)):
        return False
    return (_n(p.get("einstiche")) or 0) == (_n(q.get("einstiche")) or 0)


def art(p, q):
    """'längs', 'quer', 'längs und quer' oder None (kein Spiegelteil bzw. identisch)."""
    if not _grund_gleich(p, q):
        return None
    ta, tb = _technik(p), _technik(q)
    if ta is None or tb is None:
        return None
    laenge = _n(p.get("laenge"))
    ka, kb = ta.get("konturen") or [], tb.get("konturen") or []
    enden_a, enden_b = (_ende(ta.get("a")), _ende(ta.get("b"))), (_ende(tb.get("a")), _ende(tb.get("b")))
    if enden_a == enden_b and _konturen_gleich(ka, kb, laenge, False, False):
        return None                 # identisch: kein Spiegelteil
    for laengs, quer, name in ((True, False, "längs"), (False, True, "quer"), (True, True, "längs und quer")):
        enden = (enden_b[1], enden_b[0]) if laengs else enden_b
        if enden == enden_a and _konturen_gleich(ka, kb, laenge, laengs, quer):
            return name
    return None


def paare(positionen, kandidaten=None):
    """[(i, j, Art)] der Spiegelpaare unter den Positionen (Nummern kandidaten, sonst alle), i < j."""
    idx = list(range(len(positionen))) if kandidaten is None else sorted(kandidaten)
    topf = {}                       # nur gleiche Abmessung und gleicher Werkstoff vergleichen (schnell)
    for i in idx:
        p = positionen[i]
        if p.get("profil_id") and _technik(p) is not None:
            topf.setdefault((p.get("profil_id"), str(p.get("werkstoff_id") or "")), []).append(i)
    out = []
    for liste in topf.values():
        for n, i in enumerate(liste):
            for j in liste[n + 1:]:
                a = art(positionen[i], positionen[j])
                if a:
                    out.append((i, j, a))
    return sorted(out)
