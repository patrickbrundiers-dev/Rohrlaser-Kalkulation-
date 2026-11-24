"""STEP neu einlesen im Editor mit Vorschau (Plan „Neuerungen und Editor-Import“ Teil C, Patrick 10.11.2026,
Freigabe „Alle Empfehlungen“): vor dem Überschreiben zeigen, was sich ändert, und von Hand gesetzte Werte behalten.

- vergleich(alt, neu, …): Zeilen der Vorschau (Länge, Profil, Enden, Konturen gleich/neu/entfällt)
- handwerte(alt, neu): von Hand gesetzte Werte der alten Konturen (Gewinde, Senkung, Flowdrill, Gravurtext) auf die
  passenden neuen Konturen übertragen (gleiche Seite, Lage und Größe), dazu die Gravurlänge ohne eigene Zeile
- neuere_revision(pfad): neuere Datei desselben Teils im selben Ordner (…_Rev B, …-Index C, … v3)

Ohne Qt, damit die Regeln einzeln prüfbar sind; den Dialog baut schneidweg_dialog.step_einlesen.
"""
import re
from pathlib import Path

from . import schneidweg as sw

LAGE_TOL = 0.5          # mm: gleiche Lage längs und quer
MASS_TOL = 0.05         # mm: gleiche Maße
RUND = (sw.BOHRUNG, sw.SENKUNG, sw.FLOWDRILL)       # dieselbe geschnittene Bohrung, Art von Hand wählbar
MAX_ZEILEN = 6          # so viele neue bzw. entfallende Konturen nennt die Vorschau einzeln


def _z(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else None


def _nah(a, b, tol):
    a, b = _z(a), _z(b)
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tol)


def _gleiche_kontur(a, n):
    """Dieselbe Kontur am Teil: gleiche Seite, Lage längs/quer, Anzahl und Größe (Bohrung, Senkung und Flowdrill
    gelten als dieselbe Bohrung, wenn Ø d passt)."""
    rund = a.get("art") in RUND and n.get("art") in RUND
    if not rund and a.get("art") != n.get("art"):
        return False
    if str(a.get("seite") or "") != str(n.get("seite") or "") or int(_z(a.get("anzahl")) or 1) != int(
            _z(n.get("anzahl")) or 1):
        return False
    if not _nah(a.get("x"), n.get("x"), LAGE_TOL) or not _nah(a.get("q") or 0, n.get("q") or 0, LAGE_TOL):
        return False
    if rund:
        return _nah(a.get("d"), n.get("d"), MASS_TOL)
    for k, _ in sw.MASSE.get(a.get("art"), ()):
        if k == "punkte":
            if str(a.get(k) or "").strip() != str(n.get(k) or "").strip():
                return False
        elif not _nah(a.get(k) or 0, n.get(k) or 0, MASS_TOL if k not in ("laenge", "huelle") else LAGE_TOL):
            return False
    return True


def zuordnen(alt, neu):
    """Konturen alt/neu paaren: [(Index alt, Index neu)], dazu die Indizes ohne Partner (entfällt, neu)."""
    frei = list(range(len(alt)))
    paare, neue = [], []
    for j, n in enumerate(neu):
        i = next((i for i in frei if _gleiche_kontur(alt[i], n)), None)
        if i is None:
            neue.append(j)
        else:
            frei.remove(i)
            paare.append((i, j))
    return paare, frei, neue


def _kontur_text(z):
    from .stammdaten import zahl_als_text as zahl
    masse = " × ".join(zahl(_z(z.get(k)), 1) for k, _ in sw.MASSE.get(z.get("art"), ()) if _z(z.get(k)))
    n = int(_z(z.get("anzahl")) or 1)
    return (f"{n}× " if n > 1 else "") + str(z.get("art") or "Kontur") + (f" {masse}" if masse else "") + (
        f" bei x = {zahl(z['x'], 1)}" if _z(z.get("x")) is not None else "")


def _ende_text(e):
    from .stammdaten import zahl_als_text as zahl
    e = e or {}
    if e.get("form") == sw.FORM_3D:
        return "3D-Ende aus der Datei"
    w = _z(e.get("winkel")) or 0
    teile = ["gerade" if abs(w) < 0.05 else f"{zahl(w, 1)}° {e.get('achse') or ''}".strip()]
    if _z(e.get("sattel")):
        teile.append(f"Sattel Ø {zahl(e['sattel'], 1)}")
    return ", ".join(teile)


def handwerte(alt, neu):
    """Von Hand gesetzte Werte der alten Konturen auf die neuen übertragen. alt, neu: Eingaben des Rechners (neu wird
    nicht verändert). Ergebnis: (neue Eingaben, [Texte, was behalten wurde])."""
    ak, nk = list((alt or {}).get("konturen") or ()), [dict(z) for z in (neu or {}).get("konturen") or ()]
    paare, _, _ = zuordnen(ak, nk)
    zaehler = {}
    for i, j in paare:
        a, n = ak[i], nk[j]
        if a.get("art") in (sw.SENKUNG, sw.FLOWDRILL) and n.get("art") == sw.BOHRUNG:
            n["art"] = a["art"]         # Bohrung von Hand zur Senkung bzw. zum Flowdrill gemacht
            if a["art"] == sw.SENKUNG and _z(a.get("D")):
                n["D"] = a["D"]
            zaehler[a["art"]] = zaehler.get(a["art"], 0) + 1
        if "gewinde" in a and n.get("art") in sw.MIT_GEWINDE and n.get("gewinde") != a["gewinde"]:
            n["gewinde"] = a["gewinde"]
            titel = f"Gewinde {a['gewinde']}" if a["gewinde"] else "ohne Gewinde"
            zaehler[titel] = zaehler.get(titel, 0) + 1
        if a.get("text") and a.get("art") == n.get("art") and not n.get("text"):
            n["text"] = a["text"]
            zaehler["Text"] = zaehler.get("Text", 0) + 1
    texte = [f"{t} an {n} Kontur{'en' if n > 1 else ''}" for t, n in zaehler.items()]
    aus = dict(neu or {}, konturen=nk)
    ga = _z((alt or {}).get("gravur")) or 0
    if ga > MASS_TOL and not _z((neu or {}).get("gravur")):
        # Gravurlänge ohne eigene Zeile (Beschriftung, Positionsgravur): die Datei kennt sie nicht
        from .stammdaten import zahl_als_text
        aus["gravur"] = ga
        texte.append(f"Gravurlänge {zahl_als_text(ga, 1)} mm")
    return aus, texte


def vergleich(alt, neu, laenge_alt=None, laenge_neu=None, profil_alt=None, profil_neu=None):
    """Zeilen der Vorschau [(Art, Text)], Art 'gleich', 'geaendert', 'neu', 'weg' oder 'hinweis'. alt, neu: Eingaben
    des Rechners (neu schon für das Profil der Position umgestellt); profil_*: Texte wie „QR 40x40x3“."""
    from .stammdaten import zahl_als_text as zahl
    out = []
    if profil_alt and profil_neu and str(profil_alt).strip() != str(profil_neu).strip():
        out.append(("hinweis", f"Die Datei misst Profil {profil_neu}, die Position hat {profil_alt}: gerechnet wird "
                               "mit dem Profil der Position, solange es nicht umgestellt wird"))
    la, ln = _z(laenge_alt), _z(laenge_neu)
    if la is not None and ln is not None and abs(ln - la) > LAGE_TOL:
        out.append(("hinweis", f"Länge: die Datei misst {zahl(ln, 1)} mm, die Position hat {zahl(la, 1)} mm "
                               f"({zahl(abs(ln - la), 1)} mm {'länger' if ln > la else 'kürzer'})"))
    for s, name in (("a", "Ende A"), ("b", "Ende B")):
        ta, tn = _ende_text((alt or {}).get(s)), _ende_text((neu or {}).get(s))
        if ta != tn:
            out.append(("geaendert", f"{name}: {ta} → {tn}"))
    ak, nk = list((alt or {}).get("konturen") or ()), list((neu or {}).get("konturen") or ())
    paare, weg, neue = zuordnen(ak, nk)
    if paare:
        out.append(("gleich", f"{len(paare)} Kontur{'en' if len(paare) > 1 else ''} unverändert"))
    for art, idx, liste, wort in (("neu", neue, nk, "neu"), ("weg", weg, ak, "entfällt")):
        for i in idx[:MAX_ZEILEN]:
            out.append((art, f"{wort}: {_kontur_text(liste[i])}"))
        if len(idx) > MAX_ZEILEN:
            out.append((art, f"{wort}: {len(idx) - MAX_ZEILEN} weitere Konturen"))
    ga, gn = _z((alt or {}).get("gravur")) or 0, _z((neu or {}).get("gravur")) or 0
    if gn and abs(ga - gn) > LAGE_TOL:         # entfällt sie ganz, bietet handwerte() an, sie zu behalten
        out.append(("geaendert", f"Gravur: {zahl(ga, 1)} mm → {zahl(gn, 1)} mm"))
    return out


def unveraendert(zeilen):
    """True, wenn die Vorschau nichts Geändertes enthält (nur „unverändert“ bzw. leer)."""
    return all(art == "gleich" for art, _ in zeilen)


_REV = re.compile(r"[\s._-]*(?:rev(?:ision)?|index|idx|stand|v)[\s._-]*[0-9a-z]{1,3}$", re.IGNORECASE)


def stamm(name):
    """Dateiname ohne Endung und ohne Revisionsanhang („Halter_Rev B“ -> „halter“)."""
    s = Path(str(name)).stem.strip()
    return (_REV.sub("", s) or s).strip().casefold()


def neuere_revision(pfad, endungen=None):
    """Neueste Datei desselben Teils im selben Ordner, die jünger ist als pfad (gleicher Name ohne Revisionsanhang),
    sonst None."""
    from .step import CAD_ENDUNGEN
    pfad = Path(pfad)
    endungen = tuple(e.lower() for e in (endungen or CAD_ENDUNGEN))
    try:
        basis, zeit = stamm(pfad.name), pfad.stat().st_mtime
        kandidaten = [(d.stat().st_mtime, d) for d in pfad.parent.iterdir()
                      if d.is_file() and d != pfad and d.suffix.lower() in endungen and stamm(d.name) == basis]
    except OSError:
        return None
    neuer = [(t, d) for t, d in kandidaten if t > zeit]
    return max(neuer)[1] if neuer else None
