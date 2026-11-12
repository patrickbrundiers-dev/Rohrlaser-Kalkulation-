"""Laserzeit genauer (Plan ArTube-Unterlagen Paket 2 und 7, Patrick 12.11.2026 „Alles einbauen“).

Alles hängt an neuen Maschinenfeldern (leer = aus, alte Angebote bleiben bitgleich) bzw. an neuen Positionsfeldern
(leer = wie bisher):
- B1 Drehzeit je Seitenwechsel: Konturen auf n Seiten → (n − 1) × 'Drehzeit je Seitenwechsel [s]'.
- B3 Messzyklus: Messungen je Teil × Messzeit (schnell Vorgabe 4 s, sorgfältig 8 s; Maschinenfelder überschreiben).
- B5 Ausrichten: asymmetrische Profile (L, U, C, T, RP-, Sonderprofil, Halbflachoval) je Beladung 'Ausrichtzeit'.
- A4 Lademinimum: Werkstück kürzer als das Lademinimum wird von Hand geladen (Vorgabe 60 s je Werkstück).
- B6 Active Tilt: bei Wand bis 3 mm spart jedes weitere Loch eines Lochfelds bzw. Bohrungsmusters die Hälfte der
  Anfahrzeit (Kopf neigt sich zum nächsten Loch statt anzuheben).
- B7 Abfall zerteilen: Innenkontur mit Hüllmaß über 'größter Abfall' bekommt einen Zusatzschnitt quer durch den
  Abfall (Hüllmaß, Vorschub mittel) mit Einstich und Anfahren.
- G2 Anfahrweg: je Innenkontur der Anfahrweg (Lochung auf dem Abfall, Ansatz) mit Vorschub klein; ab 6 mm Wand
  zusätzlich 1 mm Überlappung, damit der Abfall sicher fällt.
- G3 dicke Wand mit N₂: ab 6 mm begrenzt die Maschine die Beschleunigung; kleine und mittlere Konturen und Ecken
  langsamer (Faktor nach Wand), bei O₂ nicht.
- D4/G7 Schnittqualität je Position: Standard, Qualität, Schnell, Kleines Rohr (Vorschub-Faktor wie die Adige-
  Tabellenarten); leer = Standard, bzw. Kleines Rohr automatisch bis 'Kleines Rohr bis Hüllkreis-Ø'.
- C4 Entladegrenze: Teil länger oder schwerer als die Entladegrenze wird von Hand entnommen (Vorgabe 30 s je Teil).
Ohne Qt."""
EPS = 1e-6
MESSEN = {"schnell": 4.0, "sorgfältig": 8.0}          # [s] je Messung (Vorgabe, Patrick 12.11.2026)
MESSARTEN = tuple(MESSEN)
HAND_LADEN = 60.0           # [s] je Werkstück unter dem Lademinimum (Vorgabe)
ENTNAHME_HAND = 30.0        # [s] je Teil über der Entladegrenze (Vorgabe)
TILT_ANTEIL = 0.5           # Anteil der Anfahrzeit, den Active Tilt je weiterem Loch spart
TILT_WAND = 3.0             # [mm] Active Tilt bis zu dieser Wand
UEBERLAPP_AB = 6.0          # [mm] Wand, ab der die Überlappung dazukommt
UEBERLAPPUNG = 1.0          # [mm] je Innenkontur
# Zeitfaktor kleine/mittlere Konturen und Ecken mit N₂ nach Wand (LT8.20 Tabelle 6-1: Beschleunigung begrenzt)
BESCHLEUNIGUNG = ((6.0, 1.1), (8.0, 1.2), (10.0, 1.3), (12.0, 1.5))
# Schnittqualität: Faktor auf den Vorschub (Zeit ÷ Faktor)
QUALITAET = {"Standard": 1.0, "Qualität": 0.8, "Schnell": 1.2, "Kleines Rohr": 0.7}
QUALITAETEN = tuple(QUALITAET)
# 3D-Schnittparameter (H1): Adige ab Werk je Geometrie mit dem Parameter ihres größten Kopfwinkels
JE_GEOMETRIE, JE_FLAECHE = "je Geometrie (größter Winkel)", "je Fläche"
PARAM_3D = (JE_GEOMETRIE, JE_FLAECHE)
# Beschleunigungsgrenze der Anschlusswerkzeuge mit N₂ [m/s²] ab Wand [mm] (LT8.20 Tabelle 6-1, H2)
ANSCHLUSS_BESCHL = ((3.0, 3.0), (4.0, 2.0), (5.0, 1.0), (6.0, 0.5), (8.0, 0.1), (10.0, 0.05), (12.0, 0.001))
KASTEN_KANTEN = ("Quadratrohr", "Rechteckrohr", "RP-Profil")
ASYMMETRISCH = ("L-Profil", "U-Profil", "C-Profil", "T-Profil", "Sonderprofil", "Halbflachoval", "RP-Profil")
OHNE_ABFALL = ("Gravur", "Text-Gravur", "Schlitz", "Ausklinkung", "Senkung", "Flowdrill")   # kein loser Abfall


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _form(p, k):
    pr = (k.profile.get(p.get("profil_id")) if k else None) or {}
    return pr, pr.get("form") or ""


def _lagen(p):
    """Konturen der Position mit Lage (skizze.lagen) oder []."""
    from . import schneidweg as sw, skizze as sk
    e = sw.lesen(p.get("technik")) if p.get("technik") else None
    konturen = (e or {}).get("konturen") or []
    return sk.lagen(konturen, _n(p.get("laenge"))) if konturen else []


def seiten(p):
    """Anzahl Seiten mit Innenkonturen (Gravur zählt mit, Konturen ohne Seite zählen als eine Seite)."""
    return len({str((d.get("eingabe") or {}).get("seite") or "") for d in _lagen(p)})


# --- Vorschub ---------------------------------------------------------------------------------------------------

def qualitaet(p, m, profil):
    """Schnittqualität der Position: Feld 'schnittqualitaet', leer = Kleines Rohr bis zum Hüllkreis der Maschine
    ('kleines_rohr_bis'), sonst Standard."""
    q = p.get("schnittqualitaet")
    if q in QUALITAET:
        return q
    bis = _n((m or {}).get("kleines_rohr_bis"))
    if bis > 0 and profil:
        from .stammdaten import huellkreis
        hk = huellkreis(profil)
        if hk is not None and hk <= bis + EPS:
            return "Kleines Rohr"
    return "Standard"


def beschleunigung(m, wand, gas):
    """Zeitfaktor für kleine/mittlere Konturen und Ecken (G3): nur mit Maschinenfeld 'beschleunigung_dick' = ja,
    N₂ und Wand ab 6 mm; sonst 1."""
    if (m or {}).get("beschleunigung_dick") != "ja" or gas != "N₂":
        return 1.0
    f = 1.0
    for ab, faktor in BESCHLEUNIGUNG:
        if _n(wand) >= ab - EPS:
            f = faktor
    return f


def vorschuebe(v, p, m, profil, wand, gas):
    """Wirksame Vorschübe (groß, mittel, klein, Gravur, Einstechzeit) mit Schnittqualität und dicker Wand; v wie
    rechnen.schneidzeit. Ergebnis (Vorschübe, Faktor Ecken)."""
    h, i_, j, kv, l = v
    if not h:
        return v, 1.0
    fq = QUALITAET[qualitaet(p, m, profil)]
    fb = beschleunigung(m, wand, gas)
    return (h * fq, i_ * fq / fb, j * fq / fb, kv, l), fb


# --- Zeiten je Teil ---------------------------------------------------------------------------------------------

def drehen_s(p, m):
    t = _n((m or {}).get("zeit_drehen"))
    if t <= 0:
        return 0.0
    return max(0, seiten(p) - 1) * t


def messen_s(p, m):
    n = _n(p.get("messungen"))
    if n <= 0:
        return 0.0
    art = p.get("messart") if p.get("messart") in MESSEN else "schnell"
    feld = "zeit_messen_schnell" if art == "schnell" else "zeit_messen_sorgfaeltig"
    t = _n((m or {}).get(feld))
    return n * (t if t > 0 else MESSEN[art])


def tilt_s(p, m, wand, anfahr):
    """Ersparnis Active Tilt [s] (positiv) je Teil."""
    if (m or {}).get("active_tilt") != "ja" or _n(anfahr) <= 0 or _n(wand) > TILT_WAND + EPS:
        return 0.0
    gruppen = {}
    for d in _lagen(p):
        if d.get("art") in ("Lochfeld", "Bohrung"):
            gruppen[d["zeile"]] = gruppen.get(d["zeile"], 0) + 1
    return sum(n - 1 for n in gruppen.values() if n > 1) * _n(anfahr) * TILT_ANTEIL


def abfall_zerteilen(p, m):
    """Zusatzschnitte (B7): (Anzahl, mm) für Innenkonturen mit Hüllmaß über 'abfall_max'."""
    grenze = _n((m or {}).get("abfall_max"))
    if grenze <= 0:
        return 0, 0.0
    n, mm = 0, 0.0
    for d in _lagen(p):
        hk = _n(d.get("huelle"))
        if d.get("art") not in OHNE_ABFALL and hk > grenze + EPS:
            n += 1
            mm += hk
    return n, mm


def innenkonturen(p, ersatz=0):
    """Gestochene Innenkonturen je Teil: jede Kontur der Konturliste mit Lage einzeln (ohne Gravur), ohne Liste
    ersatz (rechnen.konturen_anzahl)."""
    lagen = _lagen(p)
    if not lagen:
        return ersatz
    return sum(1 for d in lagen if d.get("art") not in ("Gravur", "Text-Gravur"))


def anschluss_beschleunigung(m, wand, gas):
    """Beschleunigungsgrenze des Ansatzes [m/s²] (H2) mit 'Langsamer ab 6 mm Wand mit N₂' = ja, N₂, ab 3 mm; sonst
    None (keine Grenze)."""
    if (m or {}).get("beschleunigung_dick") != "ja" or gas != "N₂":
        return None
    a = None
    for ab, wert in ANSCHLUSS_BESCHL:
        if _n(wand) >= ab - EPS:
            a = wert
    return a


def anfahrweg_s(weg_mm, n, v_klein, a):
    """Zeit für n Ansätze von je weg_mm: mit Vorschub klein, mit Beschleunigungsgrenze a [m/s²] mindestens
    Beschleunigen und Bremsen über den Weg (2 × √(s / a))."""
    if n <= 0 or weg_mm <= 0 or not v_klein:
        return 0.0
    t = 60 * weg_mm / v_klein
    if a:
        t = max(t, 2 * (weg_mm / 1000 / a) ** 0.5)
    return n * t


def kanten_ueber(p, m, form):
    """Kanten, über die Innenkonturen eines Kastenprofils laufen (H3): geschlossene Kontur über n Wände 2 × (n − 1),
    Schlitz/Ausklinkung n − 1; nur mit 'Eckzeit für Innenkonturen über die Kante' = ja."""
    if (m or {}).get("kanten_innen") != "ja" or form not in KASTEN_KANTEN:
        return 0
    n = 0
    for d in _lagen(p):
        w = len((d.get("eingabe") or {}).get("waende") or ())
        if w > 1 and d.get("art") not in ("Gravur", "Text-Gravur"):
            n += (w - 1) * (1 if d.get("art") in ("Schlitz", "Ausklinkung") else 2)
    return n


def anfahrweg_mm(p, m, wand, innen):
    weg = _n((m or {}).get("anfahrweg"))
    if weg <= 0 or innen <= 0:
        return 0.0
    return innen * (weg + (UEBERLAPPUNG if _n(wand) >= UEBERLAPP_AB - EPS else 0.0))


def teil_kg(p, k):
    from .rechnen import kg_je_m
    kgm = kg_je_m(p.get("profil_id"), p.get("werkstoff_id"), k) if k else None
    return None if kgm is None else kgm * _n(p.get("laenge")) / 1000


def entnahme_grund(p, m, k):
    """Teil über der Entladegrenze (C4): Text oder ''."""
    m = m or {}
    lg, kg = _n(m.get("entlade_laenge")), _n(m.get("entlade_kg"))
    if lg > 0 and _n(p.get("laenge")) > lg + EPS:
        return f"Teil länger als die Entladegrenze ({lg:.0f} mm): von Hand entnehmen, Stütze vorsehen"
    if kg > 0:
        g = teil_kg(p, k)
        if g is not None and g > kg + EPS:
            return (f"Teil schwerer als die Entladegrenze ({g:.1f} kg > {kg:.0f} kg): von Hand entnehmen, Stütze "
                    "vorsehen").replace(".", ",")
    return ""


def entnahme_s(p, m, k):
    if not entnahme_grund(p, m, k):
        return 0.0
    t = _n((m or {}).get("zeit_entnahme"))
    return t if t > 0 else ENTNAHME_HAND


def anteile(p, m, k, wand, vorschub, anfahr, innen, gas=None, zeit_ecke=0.0, f_ecke=1.0):
    """Zusätzliche Zeitanteile je Teil [s]: dict(drehen, messen, anfahrweg, abfall, entnahme, tilt (Ersparnis beim
    Anfahren), ecken_innen (Eckzeit der Innenkonturen über die Kante, H3)); vorschub = wirksame Vorschübe."""
    h, i_, j, _, l = vorschub
    _, form = _form(p, k)
    out = dict(drehen=drehen_s(p, m), messen=messen_s(p, m), anfahrweg=0.0, abfall=0.0, entnahme=entnahme_s(p, m, k),
               tilt=tilt_s(p, m, wand, anfahr), ecken_innen=kanten_ueber(p, m, form) * _n(zeit_ecke) * _n(f_ecke))
    if h:
        n = innenkonturen(p, innen)
        weg = anfahrweg_mm(p, m, wand, n)
        out["anfahrweg"] = anfahrweg_s(weg / n if n else 0.0, n, j or h, anschluss_beschleunigung(m, wand, gas))
        n, mm = abfall_zerteilen(p, m)
        out["abfall"] = 60 * mm / (i_ or h) + n * (_n(l) + _n(anfahr)) if n else 0.0
    return out


# --- je Beladung ------------------------------------------------------------------------------------------------

def beladung_s(s, m, k):
    """Zusatzzeit [s] einer Stange (bzw. zugeschnittenen Lieferstange je Werkstück): Ausrichten asymmetrischer
    Profile (B5) und Laden von Hand unter dem Lademinimum (A4)."""
    m = m or {}
    aus, lade = _n(m.get("zeit_ausrichten")), _n(m.get("lademinimum"))
    if aus <= 0 and lade <= 0:
        return 0.0
    hand = _n(m.get("zeit_hand_laden")) or HAND_LADEN
    form = ((k.profile.get(s.get("profil")) if k else None) or {}).get("form") or ""
    laengen = [_n(w.get("laenge")) for w in s.get("werkstuecke") or ()] or [_n(s.get("stange"))]
    t = 0.0
    for lg in laengen:
        if aus > 0 and form in ASYMMETRISCH:
            t += aus
        if lade > 0 and 0 < lg < lade - EPS:
            t += hand
    return t


def beladungen_s(stangen, m, k):
    return sum(beladung_s(s, m, k) for s in stangen or ())


def kurz_geladen(stangen, m):
    """Anzahl Werkstücke unter dem Lademinimum (für den Hinweis)."""
    lade = _n((m or {}).get("lademinimum"))
    if lade <= 0:
        return 0
    n = 0
    for s in stangen or ():
        for lg in [_n(w.get("laenge")) for w in s.get("werkstuecke") or ()] or [_n(s.get("stange"))]:
            n += 0 < lg < lade - EPS
    return n

