"""Schneidweg-Rechner für Positionen ohne STEP-Datei: Enden (gerade oder Gehrung), Bohrungen, Langlöcher,
Rechteckausschnitte, Schlitze und sonstige Konturen tabellarisch eingeben; das Programm rechnet Schnittlängen,
Einstiche und Hüllmaße und schreibt sie in die vorhandenen Felder der Position (Schneidweg, Einstiche,
Anfangs-/Endschnitt, Innenkonturen, Konturliste und Konturklassen). Die Schneidzeit rechnet danach wie immer
rechnen.schneidzeit mit den Schneiddaten der Maschine; einen eigenen Zeitansatz gibt es hier nicht.

Die Eingaben stehen als JSON in positionen.technik, damit der Dialog sie wieder anzeigt:
  {quelle: 'Schneidweg-Rechner', a: {winkel, achse}, b: {winkel, achse}, gravur,
   konturen: [{art, anzahl, d | l, b | b, h, r | laenge, huelle, text}]}

Formeln (Maße in mm, Winkel = Abweichung von rechtwinklig in Grad, 0 = gerader Schnitt):
- gerades Ende: optimierung.schnittlaenge (Rohre Außenumfang, offene Profile halber Umfang)
- Gehrung Rundrohr: Ellipse mit Halbachsen r und r / cos α (Umfang nach Ramanujan)
- Gehrung Quadrat-/Rechteckrohr um eine Seite: 2 × gekippte Seite / cos α + 2 × andere Seite
- Gehrung anderer Profile: gerade Schnittlänge / cos α (Schätzung, als solche gekennzeichnet)
- Bohrung π × d; Langloch 2 × (l − b) + π × b; Rechteck 2 × (b + h) − 8 r + 2 π r; Schlitz (offen, vom Rand)
  2 × l + b; sonstige Kontur: Länge wie eingegeben. Jede Innenkontur 1 Einstich, jedes Ende
  rechnen.einstiche_ende(Profilform) Einstiche.
Hüllmaß (für die Konturklassen klein/mittel/groß): Bohrung d, Langloch l, Rechteck max(b, h), Schlitz max(l, b),
sonstige Kontur wie eingegeben (leer = groß).
"""
import json
import math

from . import optimierung as opt
from .stammdaten import flaeche_wirksam

QUELLE = "Schneidweg-Rechner"
BOHRUNG, LANGLOCH, RECHTECK, SCHLITZ, SONSTIGE = "Bohrung", "Langloch", "Rechteck", "Schlitz", "sonstige Kontur"
ARTEN = (BOHRUNG, LANGLOCH, RECHTECK, SCHLITZ, SONSTIGE)
# Maße je Art: (Schlüssel, Titel) in der Eingabetabelle
MASSE = {BOHRUNG: (("d", "Ø d"),), LANGLOCH: (("l", "Länge l"), ("b", "Breite b")),
         RECHTECK: (("b", "Breite b"), ("h", "Höhe h"), ("r", "Eckradius r")),
         SCHLITZ: (("l", "Tiefe l"), ("b", "Breite b")),
         SONSTIGE: (("laenge", "Schnittlänge"), ("huelle", "Hüllmaß"))}
ACHSEN = ("über Höhe", "über Breite")      # Gehrung an Quadrat-/Rechteckrohr: welche Seite gekippt wird
ROHRE_ECKIG = ("Quadratrohr", "Rechteckrohr")
OHNE_HUELLE = 9999.0        # sonstige Kontur ohne Hüllmaß: in der Konturliste als groß


def _z(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def lesen(text):
    """Eingaben aus positionen.technik (JSON) oder leere Eingaben."""
    try:
        d = json.loads(text) if text else {}
    except (TypeError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    d.setdefault("a", {})
    d.setdefault("b", {})
    d.setdefault("konturen", [])
    return d


def ellipse(a, b):
    """Umfang einer Ellipse mit den Halbachsen a, b (Ramanujan II, Fehler < 0,01 % für übliche Gehrungen)."""
    h = ((a - b) / (a + b)) ** 2 if a + b else 0
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def ende(profil, winkel=0.0, achse=ACHSEN[0]):
    """Schnittlänge eines Endes: (mm, schaetzung). profil = Stammdaten-Zeile (form, a, b, wand, Fläche)."""
    form, a, b, wand = profil.get("form"), _z(profil.get("a")), profil.get("b"), profil.get("wand")
    gerade = opt.schnittlaenge(form, a, b, wand, flaeche_wirksam(profil))
    w = abs(_z(winkel))
    if w < 1e-9:
        return gerade, False
    if w >= 80:
        raise ValueError("Gehrung: Winkel unter 80° eingeben (0° = gerader Schnitt).")
    c = math.cos(math.radians(w))
    if form == "Rundrohr":
        return ellipse(a / 2, a / 2 / c), False
    if form in ROHRE_ECKIG:
        h_, b_ = a, _z(b) or a                         # a = Höhe, b = Breite
        kipp, fest = (h_, b_) if achse != ACHSEN[1] else (b_, h_)
        return 2 * kipp / c + 2 * fest, False
    return gerade / c, True


def kontur(e):
    """Eine Zeile der Konturtabelle: (Schnittlänge je Stück, Hüllmaß oder None = groß, Anzahl). ValueError bei
    fehlenden oder unmöglichen Maßen."""
    art, n = e.get("art"), int(_z(e.get("anzahl")) or 0)
    if n < 1:
        raise ValueError(f"{art}: Anzahl fehlt.")
    if art == BOHRUNG:
        d = _z(e.get("d"))
        if d <= 0:
            raise ValueError("Bohrung: Ø fehlt.")
        return math.pi * d, d, n
    if art == LANGLOCH:
        l_, b_ = _z(e.get("l")), _z(e.get("b"))
        if b_ <= 0 or l_ < b_:
            raise ValueError("Langloch: Länge ≥ Breite > 0 eingeben.")
        return 2 * (l_ - b_) + math.pi * b_, l_, n
    if art == RECHTECK:
        b_, h_, r = _z(e.get("b")), _z(e.get("h")), _z(e.get("r"))
        if b_ <= 0 or h_ <= 0 or 2 * r > min(b_, h_):
            raise ValueError("Rechteck: Breite und Höhe > 0, Eckradius höchstens halbe Seite.")
        return 2 * (b_ + h_) - 8 * r + 2 * math.pi * r, max(b_, h_), n
    if art == SCHLITZ:
        l_, b_ = _z(e.get("l")), _z(e.get("b"))
        if l_ <= 0 or b_ <= 0:
            raise ValueError("Schlitz: Tiefe und Breite > 0 eingeben.")
        return 2 * l_ + b_, max(l_, b_), n
    if art == SONSTIGE:
        lg = _z(e.get("laenge"))
        if lg <= 0:
            raise ValueError("Sonstige Kontur: Schnittlänge fehlt.")
        return lg, (_z(e.get("huelle")) or None), n
    raise ValueError(f"Unbekannte Konturart '{art}'.")


def rechnen(eingaben, profil, grenzen):
    """Schneidweg je Teil aus den Eingaben. profil = Stammdaten-Zeile, grenzen = (klein bis, mittel bis) der Maschine.
    Ergebnis dict(schritte=[{text, anzahl, laenge_stueck, laenge, einstiche, huelle, klasse, schaetzung}],
    felder={Feldname der Position: Wert}, schneidweg, einstiche, schaetzung, fehler=[Texte])."""
    from .rechnen import einstiche_ende, grenzen_text, konturen_text, konturklassen, zahl
    schritte, fehler, liste, enden = [], [], [], []
    form = profil.get("form")
    hk_ende = max(_z(profil.get("a")), _z(profil.get("b")))
    n_ende = einstiche_ende(form)
    for seite, titel in (("a", "Anfangsschnitt"), ("b", "Endschnitt")):
        e = eingaben.get(seite) or {}
        try:
            lg, sch = ende(profil, e.get("winkel"), e.get("achse") or ACHSEN[0])
        except ValueError as f:
            fehler.append(f"{titel}: {f}")
            lg, sch = ende(profil)
        w = abs(_z(e.get("winkel")))
        text = titel + (f" Gehrung {zahl(w, 1)}°" + (f" {e.get('achse') or ACHSEN[0]}" if form in ROHRE_ECKIG else "")
                        if w else " gerade")
        schritte.append(dict(text=text, anzahl=1, laenge_stueck=lg, laenge=lg, einstiche=n_ende, huelle=hk_ende,
                             klasse="Ende", schaetzung=sch, gerade=not w))
        enden.append(("A" if seite == "a" else "E", hk_ende, lg))
    for e in eingaben.get("konturen") or ():
        try:
            lg, hk, n = kontur(e)
        except ValueError as f:
            fehler.append(str(f))
            continue
        masse = " × ".join(zahl(_z(e.get(k_)), 2) for k_, _ in MASSE.get(e.get("art"), ()) if _z(e.get(k_)))
        klasse = ("groß" if hk is None else "klein" if round(hk, 2) <= grenzen[0] else
                  "mittel" if round(hk, 2) <= grenzen[1] else "groß")
        schritte.append(dict(text=f"{n} × {e.get('art')} {masse}".strip() + (f" ({e['text']})" if e.get("text") else ""),
                             anzahl=n, laenge_stueck=lg, laenge=n * lg, einstiche=n, huelle=hk, klasse=klasse,
                             schaetzung=False, gerade=None))
        liste += [(hk if hk is not None else OHNE_HUELLE, lg)] * n
    gravur = _z(eingaben.get("gravur"))
    a_s, b_s = schritte[0]["laenge"], schritte[1]["laenge"]
    innen = sum(lg for _, lg in liste)
    kl = konturklassen([(hk, lg) for hk, lg in liste], grenzen)
    einstiche = 2 * n_ende + sum(s["einstiche"] for s in schritte[2:])
    felder = dict(schneidweg=round(a_s + b_s + innen, 1), einstiche=einstiche, a_schnitt=round(a_s, 1),
                  b_schnitt=round(b_s, 1), a_gerade="ja" if schritte[0]["gerade"] else "nein",
                  b_gerade="ja" if schritte[1]["gerade"] else "nein", innen=round(innen, 1),
                  gravur=round(gravur, 1) if gravur else None,
                  konturen=konturen_text(liste, enden),
                  kontur_grenzen=grenzen_text(grenzen), **kl)
    return dict(schritte=schritte, felder=felder, schneidweg=felder["schneidweg"], einstiche=einstiche,
                schaetzung=any(s["schaetzung"] for s in schritte), fehler=fehler)


def speichern(eingaben):
    """Eingaben als JSON für positionen.technik (mit Quelle)."""
    return json.dumps(dict(eingaben, quelle=QUELLE), ensure_ascii=False)
