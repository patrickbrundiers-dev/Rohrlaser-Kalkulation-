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
  RP-Profil: Kontur aus der RP-Bibliothek in der gekippten Richtung gestreckt (rp_profile.schnitt_gehrung)
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

from . import dreid, naht, optimierung as opt, rp_profile
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
# Schrägschnitt zweiachsig: die Schnittebene kippt über Höhe und Breite zugleich (winkel_h, winkel_b); winkel ist dann
# der Gesamtwinkel der Ebene (Kopf in 3D, Skizze), gesamtwinkel
ACHSE_ZWEI = "über Höhe und Breite"
ACHSEN_WAHL = ACHSEN + (ACHSE_ZWEI,)
# 3D-Ende aus dem STEP-Import (mehrere Ebenen, Zylinder): Flächen der Messung (flaechen, huelle), ende_3d
FORM_3D = "komplex"
# Gehrung bei Rund-, Quadrat- und Rechteckrohr: Seite, an der das Teil an diesem Ende am längsten ist (Blick von
# Ende A, 0° oben, 90° rechts; Rechteckrohr mit der Breitseite oben). Damit legt die Optimierung Gehrungen
# ineinander (positionen.a_ende/b_ende). "automatisch" (gespeichert None): die Richtung folgt aus "gekippt über"
# (angenommene_richtung), die Optimierung darf das Teil frei drehen.
AUTOMATISCH = "automatisch"
RICHTUNGEN = {AUTOMATISCH: None, "länger oben (0°)": 0, "länger rechts (90°)": 90,
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
    gerade = opt.schnittlaenge(form, a, profil.get("b"), profil.get("wand"), flaeche_wirksam(profil),
                               profil.get("profil_id"))
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


def gesamtwinkel(w_h, w_b):
    """Neigung der Schnittebene gegen den geraden Schnitt [Grad] aus den Winkeln über Höhe und über Breite."""
    th, tb = math.tan(math.radians(abs(_z(w_h)))), math.tan(math.radians(abs(_z(w_b))))
    return math.degrees(math.atan(math.hypot(th, tb)))


def schraeg(profil, th, tb):
    """Schnittlänge eines ebenen Endes, dessen Ebene mit der Steigung th über Höhe (Maß a) und tb über Breite (Maß b)
    kippt: (mm, schaetzung). Rundrohr: Ellipse mit der Gesamtneigung; RP-Profil: Kontur der Bibliothek je Richtung
    gestreckt; Rohre und offene Profile: Anteil Höhe × √(1 + th²) + Anteil Breite × √(1 + tb²) (zerlegung, exakt für
    achsparallele Kanten); unbekannte Form: gerade Schnittlänge × √(1 + th² + tb²) (Schätzung)."""
    form, a = profil.get("form"), _z(profil.get("a"))
    gerade = opt.schnittlaenge(form, a, profil.get("b"), profil.get("wand"), flaeche_wirksam(profil),
                               profil.get("profil_id"))
    if not th and not tb:
        return gerade, False
    if form == "Rundrohr":
        return ellipse(a / 2, a / 2 * math.sqrt(1 + th * th + tb * tb)), False
    rp = rp_profile.daten(profil.get("profil_id")) if form == rp_profile.FORM else None
    if rp:          # über Höhe = Maß A = Breite x des Querschnitts
        return rp_profile.schnitt_schraeg(rp, th, tb), False
    hw = zerlegung(profil)
    if hw:
        return hw[0] * math.sqrt(1 + th * th) + hw[1] * math.sqrt(1 + tb * tb), False
    return gerade * math.sqrt(1 + th * th + tb * tb), True


def ende(profil, winkel=0.0, achse=ACHSEN[0], gegenrohr=None, kipp=None):
    """Schnittlänge eines Endes: (mm, schaetzung). profil = Stammdaten-Zeile (form, a, b, wand, Fläche);
    gegenrohr = Ø des Rundrohrs, auf das das Ende ausgeklinkt wird (nur Rundrohr, rechtwinklig); kipp = (Winkel über
    Höhe, Winkel über Breite) beim zweiachsigen Schrägschnitt (achse ACHSE_ZWEI), winkel ist dann ohne Bedeutung."""
    form, a = profil.get("form"), _z(profil.get("a"))
    if achse == ACHSE_ZWEI and kipp is not None:
        w_h, w_b = abs(_z(kipp[0])), abs(_z(kipp[1]))
        if max(w_h, w_b) >= 80:
            raise ValueError("Schrägschnitt: Winkel unter 80° eingeben.")
        if _z(gegenrohr):
            raise ValueError("Ausklinkung nur rechtwinklig (Gehrung 0°).")
        return schraeg(profil, math.tan(math.radians(w_h)), math.tan(math.radians(w_b)))
    w = abs(_z(winkel))
    if _z(gegenrohr):
        if form != "Rundrohr":
            raise ValueError("Ausklinkung nur für Rundrohr.")
        if w:
            raise ValueError("Ausklinkung nur rechtwinklig (Gehrung 0°).")
        return sattel(a, _z(gegenrohr)), False
    if w >= 80:
        raise ValueError("Gehrung: Winkel unter 80° eingeben (0° = gerader Schnitt).")
    t = math.tan(math.radians(w))
    return schraeg(profil, t, 0.0) if achse != ACHSEN[1] else schraeg(profil, 0.0, t)


GESCHLOSSEN_3D = ("Rundrohr", "Quadratrohr", "Rechteckrohr", rp_profile.FORM)   # 3D-Ende neu rechenbar


def _hoehe(f, x, y):
    """Höhe z einer Fläche der Messung über dem Punkt (x, y) des Querschnitts oder None (außerhalb des Zylinders).
    Ebene ['E', gx, gy, c]: z = c + gx·x + gy·y; Zylinder quer zur Rohrachse ['Z', ux, uy, ax, ay, az, r, vz]:
    z = az + vz·√(r² − s²), s = Abstand von der Zylinderachse in der Querschnittsebene."""
    if f[0] == "E":
        return f[3] + f[1] * x + f[2] * y
    _, ux, uy, ax, ay, az, r, vz = f
    s = -(x - ax) * uy + (y - ay) * ux
    if abs(s) > r:
        return None
    return az + vz * math.sqrt(r * r - s * s)


def ende_3d(profil, flaechen, huelle, schritt=0.5):
    """Schnittlänge eines 3D-Endes (mehrere Ebenen, Zylinder; aus der STEP-Messung, Felder flaechen und huelle) am
    Profil profil: die Außenkontur des Querschnitts (skizze.Querschnitt, Blick von Ende A: u = −x, v = y der Messung)
    wird fein unterteilt, jeder Punkt bekommt die Höhe der Schnittfläche (Hülle 'min' bzw. 'max' über alle Flächen),
    und die gerade Schnittlänge des Profils wird im Verhältnis Länge der Raumkurve / Länge der Kontur gestreckt.
    Nur geschlossene Profile (GESCHLOSSEN_3D); None, wenn das nicht geht (Fläche über einem Punkt nicht definiert)."""
    from . import skizze as sk
    if profil.get("form") not in GESCHLOSSEN_3D or not flaechen or huelle not in ("min", "max"):
        return None
    try:
        um = sk.Querschnitt(profil).umriss[0]
    except (ValueError, TypeError, ZeroDivisionError, IndexError):
        return None
    wahl = min if huelle == "min" else max
    pts = []
    for (u0, v0), (u1, v1) in zip(um, um[1:] + um[:1]):
        n = max(1, int(math.hypot(u1 - u0, v1 - v0) / schritt))
        pts += [(u0 + (u1 - u0) * i / n, v0 + (v1 - v0) * i / n) for i in range(n)]
    hoehen = []
    for u, v in pts:
        z = [h for h in (_hoehe(f, -u, v) for f in flaechen) if h is not None]
        if not z:
            return None
        hoehen.append(wahl(z))
    eben = raum = 0.0
    for i, (u, v) in enumerate(pts):
        u1, v1 = pts[(i + 1) % len(pts)]
        d = math.hypot(u1 - u, v1 - v)
        eben += d
        raum += math.sqrt(d * d + (hoehen[(i + 1) % len(pts)] - hoehen[i]) ** 2)
    gerade = ende(profil)[0]
    return gerade * raum / eben if eben > 0 and gerade > 0 else None


def messprofil_text(form, a, b, wand):
    """Kennung des gemessenen Querschnitts (Form, Maße, Wand) für ein Ende aus dem STEP-Import: daran erkennt der
    Rechner, dass das Profil der Position ein anderes ist als gemessen (anderes_profil)."""
    def f(x):
        try:
            return float(x or 0)
        except (TypeError, ValueError):
            return 0.0
    return f"{form}|{f(a):.2f}|{f(b):.2f}|{f(wand):.2f}"


def _masse(form, a, b):
    a, b = _z(a), _z(b)
    return (a,) if form == "Flachstahl" else (max(a, b or a), min(a, b or a))


def anderes_profil(e, profil):
    """Gilt die gemessene Länge des Endes e für das Profil profil nicht (mehr)? Ja, wenn das Ende auf einem anderen
    Querschnitt gemessen wurde (messprofil: Form, Maße ±0,3 mm, Wand ±0,15 mm) und beim RP-Profil immer (die Messung
    zählt den Anschlag doppelt)."""
    if profil.get("form") == rp_profile.FORM and rp_profile.daten(profil.get("profil_id")):
        return True
    try:
        form, a, b, wand = str(e.get("messprofil") or "").split("|")
        a, b, wand = float(a), float(b), float(wand)
    except ValueError:
        return False
    if form != profil.get("form") or abs(wand - _z(profil.get("wand"))) > 0.15:
        return True
    return any(abs(x - y) > 0.3 for x, y in zip(_masse(form, a, b), _masse(form, profil.get("a"), profil.get("b"))))


def ende_neu(profil, e):
    """Schnittlänge eines gemessenen Endes e (Eingaben des Rechners aus dem STEP-Import) für das Profil profil neu
    gerechnet (Patrick 22.10.2026: Profil im Import geändert): gerade = Schnittlänge des Profils, Gehrung und
    Schrägschnitt zweiachsig exakt mit Winkel und Achse, 3D-Ende aus den Flächen der Messung (ende_3d).
    Ergebnis (mm, Art) oder None, wenn es nicht geht (komplexes Ende ohne Flächen, offenes Profil)."""
    form = e.get("form")
    if form == "gerade":
        return ende(profil)[0], "gerade"
    if e.get("flaechen"):
        lg = ende_3d(profil, e["flaechen"], e.get("huelle"))
        return (lg, "3D") if lg else None
    if form in ("Gehrung", "Schrägschnitt zweiachsig") and _z(e.get("winkel")):
        try:
            return ende(profil, e.get("winkel"), e.get("achse") or ACHSEN[0], None,
                        (e.get("winkel_h"), e.get("winkel_b")))[0], form
        except ValueError:
            return None
    return None


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


def rechnen(eingaben, profil, grenzen, gewinde=None, maschine=None):
    """Schneidweg je Teil aus den Eingaben. profil = Stammdaten-Zeile, grenzen = Regel der Konturklassen
    (rechnen.kontur_regel: Grenzen der Maschine, mit Wandstärke auch die Faktoren × Wand). maschine = Stammdaten-
    Zeile der Maschine für die Grenzen des Schwenkwinkels (3D, dreid; None = Vorgabe ±45°): mit Häkchen
    'd3' der Eingaben wird eine Bohrung in 3D als Ellipse auf der Wand gerechnet (Länge und Hüllmaß mit dem
    begrenzten Winkel), eine Gehrung in 3D behält ihre Länge (nur der Kopf ist geschwenkt).
    Ergebnis dict(schritte=[{text, anzahl, laenge_stueck, laenge, einstiche, huelle, klasse, schaetzung}],
    felder={Feldname der Position: Wert}, schneidweg, einstiche, schaetzung, fehler=[Texte]).
    gewinde = [(Gewinde, Kernloch-Ø)] aus den Stammdaten für den Gewinde-Vorschlag (leer: übliche Kernlöcher)."""
    from .rechnen import einstiche_ende, grenzen_text, kontur_klasse, konturen_text, konturklassen, zahl
    schritte, fehler, liste, enden, gehrung, richtung_fehlt = [], [], [], [], {}, []
    richtung_fehlt_text = []
    hinweise_3d, hinweise_ende = [], []
    mit_3d = eingaben.get("d3") is True
    form = profil.get("form")
    hk_ende = max(_z(profil.get("a")), _z(profil.get("b")))
    n_ende = einstiche_ende(form)
    for seite, titel in (("a", "Anfangsschnitt"), ("b", "Endschnitt")):
        e = eingaben.get(seite) or {}
        zwei = e.get("achse") == ACHSE_ZWEI
        kipp = (e.get("winkel_h"), e.get("winkel_b")) if zwei else None
        try:
            lg, sch = ende(profil, e.get("winkel"), e.get("achse") or ACHSEN[0], e.get("sattel"), kipp)
            sat = _z(e.get("sattel"))
        except ValueError as f:
            fehler.append(f"{titel}: {f}")
            lg, sch = ende(profil)
            sat = 0
        w = gesamtwinkel(*kipp) if zwei else abs(_z(e.get("winkel")))
        if zwei:
            text = (f"{titel} Schrägschnitt {zahl(abs(_z(kipp[0])), 1)}° über Höhe und {zahl(abs(_z(kipp[1])), 1)}° "
                    f"über Breite (gesamt {zahl(w, 1)}°)" if w else f"{titel} gerade")
        else:
            text = titel + (f" Ausklinkung auf Rundrohr Ø {zahl(sat, 1)}" if sat else
                            f" Gehrung {zahl(w, 1)}°" + (f" {e.get('achse') or ACHSEN[0]}" if form != "Rundrohr"
                                                          else "") if w else " gerade")
        gerade = not w and not sat
        if _z(e.get("gemessen")) > 0:       # aus der STEP-Messung: gemessene Länge und Form
            neu = ende_neu(profil, e) if anderes_profil(e, profil) else None
            text = f"{titel} {e.get('form') or ''}".rstrip() + (f" {zahl(w, 1)}°" if w else "")
            if neu:             # anderes Profil als gemessen (oder RP): mit der gemessenen Form neu gerechnet
                lg, sch, gerade = neu[0], False, e.get("form") == "gerade"
                text += f" (STEP-Form, für {profil.get('profil_id') or 'das Profil'} gerechnet)"
            else:
                lg, sch, gerade = _z(e["gemessen"]), False, e.get("form") == "gerade"
                text += " (STEP gemessen)"
                if anderes_profil(e, profil):
                    hinweise_ende.append(f"{titel}: gemessen an einem anderen Querschnitt "
                                         f"({str(e.get('messprofil')).split('|')[0]}), Form {e.get('form') or '?'} "
                                         "nicht neu rechenbar: gemessene Länge gilt, bitte prüfen")
        if mit_3d and e.get("d3") and w and not sat:
            v, h_ = dreid.gehrung_begrenzen(w, maschine)
            text += f", in 3D (Kopf {zahl(v, 1)}°)"
            if h_:
                hinweise_3d.append(f"{titel}: {h_} Die Gehrungsfläche ist dann nicht maßhaltig.")
        schritte.append(dict(text=text, anzahl=1, laenge_stueck=lg, laenge=lg, einstiche=n_ende,
                             huelle=_z(e.get("huelle_gemessen")) or hk_ende, klasse="Ende", schaetzung=sch,
                             gerade=gerade))
        gehrung[seite] = None
        if w and not sat and e.get("richtung") is None and form in MIT_RICHTUNG and not _z(e.get("gemessen")) \
                and not zwei:
            richtung_fehlt.append(titel)
            r_ = angenommene_richtung(profil, e.get("achse"))
            richtung_fehlt_text.append(next(t for t, v in RICHTUNGEN.items() if v == r_))
        if w and not sat and e.get("richtung") is not None and form in MIT_RICHTUNG:
            f_ = None if zwei else richtung_pruefen(profil, e.get("richtung"), e.get("achse") or ACHSEN[0])
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
        if mit_3d and e.get("d3") and e.get("art") == BOHRUNG:
            try:
                nl, nq, ges, h_ = dreid.neigung_begrenzen(e.get("neigung_l"), e.get("neigung_q"), maschine)
            except ValueError as f:
                fehler.append(f"Bohrung 3D: {f}")
                continue
            if not (_z(e.get("gemessen")) > 0 and not h_):
                lg = dreid.bohrung_laenge(_z(e.get("d")), ges)
            hk = dreid.bohrung_huelle(_z(e.get("d")), ges)
            masse += f" 3D längs {zahl(nl, 1)}° quer {zahl(nq, 1)}°".replace("-", "−")
            if h_:
                hinweise_3d.append(f"Bohrung Ø {zahl(_z(e.get('d')), 2)}: {h_} Die Bohrung ist dann nicht maßhaltig.")
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
    if richtung_fehlt:
        hinweise.append(f"{' und '.join(richtung_fehlt)}: längste Seite automatisch aus „gekippt über“ "
                        f"({', '.join(richtung_fehlt_text)}). Bei frei drehbaren Teilen (Schweißnaht ohne Vorgabe) "
                        "dreht die Optimierung das Teil passend und legt die Gehrungen ineinander. Nur wenn die Lage "
                        "fest ist (Werkstattpapiere, Bohrbild), die längste Seite von Hand wählen.")
    hinweise += hinweise_ende + hinweise_3d
    return dict(schritte=schritte, felder=felder, schneidweg=felder["schneidweg"], einstiche=einstiche,
                schaetzung=any(s["schaetzung"] for s in schritte), fehler=fehler, hinweise=hinweise,
                hinweise_3d=hinweise_3d)


def aus_position(e, p, profil):
    """Eingaben e (positionen.technik) um die gespeicherten Werte der Position ergänzen, wenn der Rechner sie noch
    nicht kennt (STEP-Import vor 0.6.29 oder ohne Konturliste, Gravur aus dem Import): Enden mit der gemessenen Länge
    (a_schnitt/b_schnitt) und der Gehrung aus a_ende/b_ende, Gravur, Innenkonturen aus der Konturliste (Hüllmaß ×
    Schnittlänge): Bohrung, wenn die Länge π × Hüllmaß ist, sonst sonstige Kontur; gleiche Konturen als eine Zeile mit
    Anzahl, Lage unbekannt (in der Skizze verteilt). Eingaben des Rechners selbst (Quelle Schneidweg-Rechner) bleiben,
    wie sie sind. Ergebnis: neue Eingaben (Kopie) und ob etwas aus der Position kam."""
    from .rechnen import konturen_lesen
    e = json.loads(json.dumps(e))
    if e.get("quelle") == QUELLE:
        return e, False
    liste = konturen_lesen(p.get("konturen"), True)
    huelle_ende = {a: hk for a, hk, _ in liste if a}
    neu = False
    for s, schnitt, gerade, feld, kenn in (("a", "a_schnitt", "a_gerade", "a_ende", "A"),
                                           ("b", "b_schnitt", "b_gerade", "b_ende", "E")):
        if _z(e[s].get("gemessen")) or e[s].get("winkel") or _z(p.get(schnitt)) <= 0:
            continue
        x = dict(gemessen=round(_z(p[schnitt]), 2), form="gerade" if p.get(gerade) == "ja" else "nicht gerade")
        if huelle_ende.get(kenn):
            x["huelle_gemessen"] = huelle_ende[kenn]
        g = naht.ende_lesen(p.get(feld))
        if g:
            x.update(winkel=g[0], richtung=g[1], form="Gehrung", achse=achse_zu_richtung(profil, g[1]))
        e[s], neu = x, True
    if not e.get("gravur") and _z(p.get("gravur")) > 0:
        e["gravur"], neu = round(_z(p["gravur"]), 1), True
    if not e["konturen"] and e.get("quelle") != QUELLE_STEP:
        zeilen = {}
        for art, hk, lg in liste:
            if not art and lg > 0:
                zeilen[(hk, lg)] = zeilen.get((hk, lg), 0) + 1
        for (hk, lg), n in zeilen.items():
            k = dict(anzahl=n, gemessen=round(lg, 2), text="aus STEP, Lage unbekannt")
            if hk < OHNE_HUELLE:
                k["huelle_gemessen"] = hk
            if hk > 0 and abs(lg - math.pi * hk) <= max(0.15, 0.01 * lg):
                k.update(art=BOHRUNG, d=hk)
            else:
                k.update(art=SONSTIGE, laenge=round(lg, 2), huelle=hk if hk < OHNE_HUELLE else None)
            e["konturen"].append(k)
            neu = True
    return e, neu


def achse_zu_richtung(profil, richtung):
    """Gehrungsachse passend zur Richtung (Rechteckrohr Breitseite oben: 0°/180° kippt über die kürzere Seite)."""
    a, b = _z(profil.get("a")), _z(profil.get("b")) or _z(profil.get("a"))
    quer = min(a, b) if float(richtung) % 180 == 0 else max(a, b)
    return ACHSEN[0] if abs(quer - a) < 1e-6 else ACHSEN[1]


def speichern(eingaben):
    """Eingaben als JSON für positionen.technik (mit Quelle)."""
    return json.dumps(dict(eingaben, quelle=QUELLE), ensure_ascii=False)


def angenommene_richtung(profil, achse):
    """Richtung (am längsten …) für eine Gehrung ohne Angabe: die erste, die zur Gehrungsachse passt (Rechteckrohr:
    0° kippt über die kürzere Seite, 90° über die längere). Nur für frei drehbare Teile (rechnen.gruppen_bilden):
    dort legt die Optimierung mit Drehung um 180° bzw. 90° jede Lage gleich gut ineinander."""
    for r in (0, 90):
        if achse_zu_richtung(profil, r) == (achse or ACHSEN[0]):
            return r
    return 0


def mit_angenommener_richtung(eingaben, profil):
    """Eingaben für Skizze und Zeichnung: Enden mit Gehrung und Richtung "automatisch" bekommen die angenommene
    Richtung (wie die Optimierung, angenommene_richtung); gespeichert bleibt None."""
    if (profil or {}).get("form") not in MIT_RICHTUNG:
        return eingaben
    neu = dict(eingaben)
    for s in ("a", "b"):
        e = neu.get(s)
        if isinstance(e, dict) and e.get("richtung") is None and not _z(e.get("sattel")) \
                and 0 < abs(_z(e.get("winkel"))) < 80:
            neu[s] = dict(e, richtung=angenommene_richtung(profil, e.get("achse")), richtung_auto=True)
    return neu


def gehrung_ohne_richtung(technik, seite, profil):
    """(Winkel, angenommene Richtung) für ein Ende, das im Schneidweg-Rechner eine Gehrung ohne Richtung hat
    (Rund-, Quadrat-, Rechteckrohr, keine Ausklinkung), sonst None."""
    if (profil or {}).get("form") not in MIT_RICHTUNG:
        return None
    e = lesen(technik).get(seite) or {}
    if not isinstance(e, dict) or e.get("richtung") is not None or _z(e.get("sattel")) or _z(e.get("gemessen")):
        return None
    w = abs(_z(e.get("winkel")))
    return (w, angenommene_richtung(profil, e.get("achse"))) if 0 < w < 80 else None
