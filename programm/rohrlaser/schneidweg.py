"""Schneidweg-Rechner für Positionen ohne STEP-Datei: Enden (gerade oder Gehrung), Bohrungen, Langlöcher,
Rechteckausschnitte, Schlitze und sonstige Konturen tabellarisch eingeben; das Programm rechnet Schnittlängen,
Einstiche und Hüllmaße und schreibt sie in die vorhandenen Felder der Position (Schneidweg, Einstiche,
Anfangs-/Endschnitt, Innenkonturen, Konturliste und Konturklassen). Die Schneidzeit rechnet danach wie immer
rechnen.schneidzeit mit den Schneiddaten der Maschine; einen eigenen Zeitansatz gibt es hier nicht.

Die Eingaben stehen als JSON in positionen.technik, damit der Dialog sie wieder anzeigt:
  {quelle: 'Schneidweg-Rechner', a: {winkel, achse, sattel, richtung}, b: {…}, gravur,
   konturen: [{art, anzahl, d | d, D | l, b | b, h, r | laenge, huelle | punkte, x, abstand, seite, q, text}]}
x = Lage der (ersten) Kontur ab Anfang [mm], abstand = Muster längs, seite = Fläche bzw. Winkel (Rundrohr),
q = Versatz quer zur Flächenmitte [mm]; alles nur für die Skizze (skizze.py), nicht für den Schneidweg.

Formeln (Maße in mm, Winkel = Abweichung von rechtwinklig in Grad, 0 = gerader Schnitt):
- gerades Ende: optimierung.schnittlaenge (Rohre Außenumfang, offene Profile halber Umfang)
- Gehrung Rundrohr: Ellipse mit Halbachsen r und r / cos α (Umfang nach Ramanujan)
- Gehrung aller anderen Profile: gerade Schnittlänge zerlegt in Anteil Höhe H und Anteil Breite W (zerlegung);
  die gekippte Richtung wird mit 1 / cos α gestreckt: über Höhe H / cos α + W, über Breite H + W / cos α.
  Unbekannte Profilform: gerade Schnittlänge / cos α (Schätzung, als solche gekennzeichnet)
- Ausklinkung (Sattelschnitt) Rundrohr Ø d rechtwinklig auf Rundrohr Ø D: Länge der Schnittkurve numerisch
- Bohrung π × d; Senkung π × d (der Laser schneidet die Bohrung, das Senken auf Ø D ist eine Zusatzarbeit);
  Langloch 2 × (l − b) + π × b; Rechteck 2 × (b + h) − 8 r + 2 π r; Schlitz (offen, vom Rand) 2 × l + b;
  Ausklinkung am Ende (Rechteck, offen zum Ende, Ecken innen mit r) 2 × (l − r) + (b − 2 r) + π r, der Endschnitt
  wird dafür nicht gekürzt (zur sicheren Seite); sonstige Kontur: Länge wie eingegeben. Jede Innenkontur 1 Einstich, jedes Ende
  rechnen.einstiche_ende(Profilform) Einstiche.
Hüllmaß (für die Konturklassen klein/mittel/groß): Bohrung und Senkung d, Ausklinkung max(l, b), Langloch l, Rechteck max(b, h), Schlitz max(l, b),
sonstige Kontur wie eingegeben (leer = groß), Polygon größte Ausdehnung in x oder y.
Vorschlag: Bohrungen mit dem Kernloch-Ø eines Gewindes ergeben einen Gewinde-Vorschlag (wie beim STEP-Import); er
gilt erst, wenn der Benutzer ihn in 'Gewinde geprüft' einträgt.
"""
import json
import math

from . import naht, optimierung as opt
from .stammdaten import flaeche_wirksam

QUELLE = "Schneidweg-Rechner"
QUELLE_STEP = "STEP-Import"         # Konturen aus der STEP-Messung (Lage, gemessene Schnittlängen)
BOHRUNG, LANGLOCH, RECHTECK, SCHLITZ, POLYGON, SONSTIGE = ("Bohrung", "Langloch", "Rechteck", "Schlitz", "Polygon",
                                                          "sonstige Kontur")
SENKUNG, AUSKLINKUNG = "Senkung", "Ausklinkung"
ARTEN = (BOHRUNG, SENKUNG, LANGLOCH, RECHTECK, SCHLITZ, AUSKLINKUNG, POLYGON, SONSTIGE)
# Maße je Art: (Schlüssel, Titel) in der Eingabetabelle
MASSE = {BOHRUNG: (("d", "Ø d"),), SENKUNG: (("d", "Bohrung Ø d (geschnitten)"), ("D", "Senk-Ø D (Zusatzarbeit)")),
         LANGLOCH: (("l", "Länge l"), ("b", "Breite b")),
         RECHTECK: (("b", "Breite b"), ("h", "Höhe h"), ("r", "Eckradius r")),
         SCHLITZ: (("l", "Tiefe l"), ("b", "Breite b")),
         AUSKLINKUNG: (("l", "Länge l ab Ende"), ("b", "Breite b"), ("r", "Eckradius r")),
         POLYGON: (("punkte", "Eckpunkte x,y; x,y; … [mm]"),),
         SONSTIGE: (("laenge", "Schnittlänge"), ("huelle", "Hüllmaß"))}
ACHSEN = ("über Höhe", "über Breite")      # Gehrung (außer Rundrohr): welche Richtung gekippt wird
# Gehrung bei Rund-, Quadrat- und Rechteckrohr: Seite, an der das Teil an diesem Ende am längsten ist (Blick von
# Ende A, 0° oben, 90° rechts; Rechteckrohr mit der Breitseite oben). Damit legt die Optimierung Gehrungen
# ineinander (positionen.a_ende/b_ende); ohne Angabe nicht.
RICHTUNGEN = {"nicht angegeben": None, "länger oben (0°)": 0, "länger rechts (90°)": 90,
              "länger unten (180°)": 180, "länger links (270°)": 270}
MIT_RICHTUNG = ("Rundrohr", "Quadratrohr", "Rechteckrohr")
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


def zerlegung(profil):
    """Gerade Schnittlänge eines Profils (außer Rundrohr) als (Anteil Höhe H, Anteil Breite W) [mm], passend zu
    optimierung.schnittlaenge; None für unbekannte Formen. Höhe = Maß a, Breite = Maß b."""
    form, a, b, wand = profil.get("form"), _z(profil.get("a")), _z(profil.get("b")), _z(profil.get("wand"))
    gerade = opt.schnittlaenge(form, a, profil.get("b"), profil.get("wand"), flaeche_wirksam(profil))
    if gerade <= 0:
        return None
    if form == "Quadratrohr":
        return 2 * a, 2 * a
    if form == "Rechteckrohr":
        return 2 * a, 2 * (b or a)
    if form in ("I-/H-Träger", "T-Profil", "U-Profil", "C-Profil", "L-Profil", "Flachstahl") and 0 < a <= gerade:
        return a, gerade - a           # Steg bzw. Schenkel a in der Höhe, der Rest (Flansche, Dicke) in der Breite
    return None


def sattel(d, D, schritte=720):
    """Länge der Schnittkurve, wenn ein Rundrohr Ø d rechtwinklig auf ein Rundrohr Ø D ≥ d gesetzt wird
    (Ausklinkung / Sattelschnitt), numerisch über den Umfang integriert."""
    r, R = d / 2, D / 2
    if r <= 0 or R < r:
        raise ValueError("Ausklinkung: Ø des Gegenrohrs muss mindestens so groß sein wie das Rohr.")
    lg = 0.0
    for i in range(schritte):
        t = 2 * math.pi * (i + 0.5) / schritte
        z = math.sqrt(max(R * R - (r * math.cos(t)) ** 2, 1e-12))
        dz = r * r * math.cos(t) * math.sin(t) / z
        lg += math.sqrt(r * r + dz * dz) * 2 * math.pi / schritte
    return lg


def ende(profil, winkel=0.0, achse=ACHSEN[0], gegenrohr=None):
    """Schnittlänge eines Endes: (mm, schaetzung). profil = Stammdaten-Zeile (form, a, b, wand, Fläche);
    gegenrohr = Ø des Rundrohrs, auf das das Ende ausgeklinkt wird (nur Rundrohr, rechtwinklig)."""
    form, a, b, wand = profil.get("form"), _z(profil.get("a")), profil.get("b"), profil.get("wand")
    gerade = opt.schnittlaenge(form, a, b, wand, flaeche_wirksam(profil))
    w = abs(_z(winkel))
    if _z(gegenrohr):
        if form != "Rundrohr":
            raise ValueError("Ausklinkung nur für Rundrohr.")
        if w:
            raise ValueError("Ausklinkung nur rechtwinklig (Gehrung 0°).")
        return sattel(a, _z(gegenrohr)), False
    if w < 1e-9:
        return gerade, False
    if w >= 80:
        raise ValueError("Gehrung: Winkel unter 80° eingeben (0° = gerader Schnitt).")
    c = math.cos(math.radians(w))
    if form == "Rundrohr":
        return ellipse(a / 2, a / 2 / c), False
    hw = zerlegung(profil)
    if hw:
        h_, w_ = hw
        return (h_ / c + w_ if achse != ACHSEN[1] else h_ + w_ / c), False
    return gerade / c, True


def richtung_pruefen(profil, richtung, achse):
    """Passt die Richtung (am längsten …) zur Gehrungsachse? Beim Rechteckrohr liegt die Breitseite oben: 0°/180°
    kippt über die kürzere Seite, 90°/270° über die längere. Ergebnis: Fehlertext oder None."""
    from .rechnen import zahl
    form, a, b = profil.get("form"), _z(profil.get("a")), _z(profil.get("b")) or _z(profil.get("a"))
    if form != "Rechteckrohr" or abs(a - b) < 1e-9 or richtung % 90:
        return None
    quer = a if achse != ACHSEN[1] else b            # Maß, über das die Gehrung läuft
    soll = min(a, b) if richtung % 180 == 0 else max(a, b)
    if abs(quer - soll) > 1e-9:
        return (f"Richtung {int(richtung)}° passt nicht zur Gehrung {achse} (Breitseite oben: 0°/180° über "
                f"{zahl(min(a, b), 1)} mm, 90°/270° über {zahl(max(a, b), 1)} mm)")
    return None


def punkte(text):
    """'0,0; 40,0; 40,20' -> [(0, 0), (40, 0), (40, 20)] (Komma oder Leerzeichen zwischen x und y)."""
    out = []
    for teil in str(text or "").split(";"):
        z = teil.replace(",", " ").split()
        if not z:
            continue
        if len(z) != 2:
            raise ValueError(f"Polygon: Punkt '{teil.strip()}' als x,y eingeben.")
        try:
            out.append((float(z[0]), float(z[1])))
        except ValueError:
            raise ValueError(f"Polygon: Punkt '{teil.strip()}' ist keine Zahl.")
    return out


def kontur(e):
    """Eine Zeile der Konturtabelle: (Schnittlänge je Stück, Hüllmaß oder None = groß, Anzahl). ValueError bei
    fehlenden oder unmöglichen Maßen."""
    art, n = e.get("art"), int(_z(e.get("anzahl")) or 0)
    if n < 1:
        raise ValueError(f"{art}: Anzahl fehlt.")
    if _z(e.get("gemessen")) > 0:       # aus der STEP-Messung, Maße unverändert: gemessene Länge
        lg, hk, _ = kontur(dict(e, gemessen=None, laenge=e.get("laenge") or e["gemessen"]))
        return _z(e["gemessen"]), (_z(e.get("huelle_gemessen")) or hk), n
    if art == BOHRUNG:
        d = _z(e.get("d"))
        if d <= 0:
            raise ValueError("Bohrung: Ø fehlt.")
        return math.pi * d, d, n
    if art == SENKUNG:
        d, D = _z(e.get("d")), _z(e.get("D"))
        if d <= 0:
            raise ValueError("Senkung: Bohrung Ø fehlt.")
        if D and D <= d:
            raise ValueError("Senkung: Senk-Ø muss größer als die Bohrung sein.")
        return math.pi * d, d, n
    if art == AUSKLINKUNG:
        l_, b_, r = _z(e.get("l")), _z(e.get("b")), _z(e.get("r"))
        if l_ <= 0 or b_ <= 0 or 2 * r > b_ or r > l_:
            raise ValueError("Ausklinkung: Länge und Breite > 0, Eckradius höchstens halbe Breite.")
        return 2 * (l_ - r) + (b_ - 2 * r) + math.pi * r, max(l_, b_), n
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
    if art == POLYGON:
        pk = punkte(e.get("punkte"))
        if len(pk) < 3:
            raise ValueError("Polygon: mindestens 3 Eckpunkte x,y eingeben.")
        lg = sum(math.dist(pk[i], pk[(i + 1) % len(pk)]) for i in range(len(pk)))
        return lg, max(max(x for x, _ in pk) - min(x for x, _ in pk), max(y for _, y in pk) - min(y for _, y in pk)), n
    if art == SONSTIGE:
        lg = _z(e.get("laenge"))
        if lg <= 0:
            raise ValueError("Sonstige Kontur: Schnittlänge fehlt.")
        return lg, (_z(e.get("huelle")) or None), n
    raise ValueError(f"Unbekannte Konturart '{art}'.")


def rechnen(eingaben, profil, grenzen, gewinde=None):
    """Schneidweg je Teil aus den Eingaben. profil = Stammdaten-Zeile, grenzen = Regel der Konturklassen
    (rechnen.kontur_regel: Grenzen der Maschine, mit Wandstärke auch die Faktoren × Wand).
    Ergebnis dict(schritte=[{text, anzahl, laenge_stueck, laenge, einstiche, huelle, klasse, schaetzung}],
    felder={Feldname der Position: Wert}, schneidweg, einstiche, schaetzung, fehler=[Texte]).
    gewinde = [(Gewinde, Kernloch-Ø)] aus den Stammdaten für den Gewinde-Vorschlag (leer: übliche Kernlöcher)."""
    from .rechnen import einstiche_ende, grenzen_text, kontur_klasse, konturen_text, konturklassen, zahl
    schritte, fehler, liste, enden, gehrung = [], [], [], [], {}
    form = profil.get("form")
    hk_ende = max(_z(profil.get("a")), _z(profil.get("b")))
    n_ende = einstiche_ende(form)
    for seite, titel in (("a", "Anfangsschnitt"), ("b", "Endschnitt")):
        e = eingaben.get(seite) or {}
        try:
            lg, sch = ende(profil, e.get("winkel"), e.get("achse") or ACHSEN[0], e.get("sattel"))
            sat = _z(e.get("sattel"))
        except ValueError as f:
            fehler.append(f"{titel}: {f}")
            lg, sch = ende(profil)
            sat = 0
        w = abs(_z(e.get("winkel")))
        text = titel + (f" Ausklinkung auf Rundrohr Ø {zahl(sat, 1)}" if sat else
                        f" Gehrung {zahl(w, 1)}°" + (f" {e.get('achse') or ACHSEN[0]}" if form != "Rundrohr" else "")
                        if w else " gerade")
        gerade = not w and not sat
        if _z(e.get("gemessen")) > 0:       # aus der STEP-Messung: gemessene Länge und Form
            lg, sch, gerade = _z(e["gemessen"]), False, e.get("form") == "gerade"
            text = f"{titel} {e.get('form') or ''}".rstrip() + (f" {zahl(w, 1)}°" if w else "") + " (STEP gemessen)"
        schritte.append(dict(text=text, anzahl=1, laenge_stueck=lg, laenge=lg, einstiche=n_ende,
                             huelle=_z(e.get("huelle_gemessen")) or hk_ende, klasse="Ende", schaetzung=sch,
                             gerade=gerade))
        gehrung[seite] = None
        if w and not sat and e.get("richtung") is not None and form in MIT_RICHTUNG:
            f_ = richtung_pruefen(profil, e.get("richtung"), e.get("achse") or ACHSEN[0])
            if f_:
                fehler.append(f"{titel}: {f_}")
            else:
                gehrung[seite] = naht.ende_text(w, e["richtung"])
        enden.append(("A" if seite == "a" else "E", schritte[-1]["huelle"], lg))
    for e in eingaben.get("konturen") or ():
        try:
            lg, hk, n = kontur(e)
        except ValueError as f:
            fehler.append(str(f))
            continue
        masse = (f"{len(punkte(e.get('punkte')))} Eckpunkte" if e.get("art") == POLYGON else
                 " × ".join(zahl(_z(e.get(k_)), 2) for k_, _ in MASSE.get(e.get("art"), ()) if _z(e.get(k_))))
        klasse = "groß" if hk is None else ("klein", "mittel", "groß")[kontur_klasse(hk, grenzen)]
        if _z(e.get("gemessen")) > 0:
            masse = (masse + " (STEP gemessen)").strip()
        schritte.append(dict(text=f"{n} × {e.get('art')} {masse}".strip() + (f" ({e['text']})" if e.get("text") else ""),
                             anzahl=n, laenge_stueck=lg, laenge=n * lg, einstiche=n, huelle=hk, klasse=klasse,
                             schaetzung=False, gerade=None, art=e.get("art"), eingabe=e))
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
                  kontur_grenzen=grenzen_text(grenzen), a_ende=gehrung["a"], b_ende=gehrung["b"], **kl)
    # Bohrungen und Gewinde-Vorschlag wie beim STEP-Import ('4xØ8,5', '4xM10')
    from .step import KERNLOCH, gewinde_vorschlag
    bohr = {}
    for s_ in schritte[2:]:
        if s_.get("art") == BOHRUNG:
            d = round(_z(s_["eingabe"].get("d")), 2)
            bohr[d] = bohr.get(d, 0) + s_["anzahl"]
    paare = "|".join(f"{d}:{n}" for d, n in sorted(bohr.items()))
    felder["bohrungen"] = "; ".join(f"{n}xØ{zahl(d, 2)}" for d, n in sorted(bohr.items())) or None
    felder["gewinde_vorschlag"] = gewinde_vorschlag(paare, gewinde or KERNLOCH) or None
    senk = sum(s_["anzahl"] for s_ in schritte[2:] if s_.get("art") == SENKUNG)
    hinweise = [f"{senk} Senkung(en): der Laser schneidet nur die Bohrung; das Senken als Zusatzarbeit erfassen "
                "(Zusatzarbeiten …)."] if senk else []
    return dict(schritte=schritte, felder=felder, schneidweg=felder["schneidweg"], einstiche=einstiche,
                schaetzung=any(s["schaetzung"] for s in schritte), fehler=fehler, hinweise=hinweise)


def speichern(eingaben):
    """Eingaben als JSON für positionen.technik (mit Quelle)."""
    return json.dumps(dict(eingaben, quelle=QUELLE), ensure_ascii=False)
