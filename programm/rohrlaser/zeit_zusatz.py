"""Laserzeit genauer (Plan ArTube-Unterlagen Paket 2 und 7, Patrick 12.11.2026 „Alles einbauen“).

Alles hängt an neuen Maschinenfeldern (leer = aus, alte Angebote bleiben bitgleich) bzw. an neuen Positionsfeldern
(leer = wie bisher):
- B1 Drehzeit je Seitenwechsel: Konturen auf n Seiten → (n − 1) × 'Drehzeit je Seitenwechsel [s]'.
- B3 Messzyklus: Messungen je Teil × Messzeit (schnell Vorgabe 4 s, sorgfältig 8 s; Maschinenfelder überschreiben).
- B5 Ausrichten: asymmetrische Profile (L, U, C, T, RP-, Sonderprofil, Halbflachoval) je Beladung 'Ausrichtzeit'.
- A4 Lademinimum: Werkstück kürzer als das Lademinimum wird von Hand geladen (Vorgabe 60 s je Werkstück).
- B6 Active Tilt: bei Wand bis 3 mm spart jedes weitere Loch eines Lochfelds bzw. Bohrungsmusters die Hälfte der
  Anfahrzeit (Kopf neigt sich zum nächsten Loch statt anzuheben).
- B7 Abfall zerteilen: großer Abfall wird mit Mikrostegen gesichert oder klein geschnitten (schneidfolge.abfall,
  Patrick 16.11.2026); Zerschneiden mit so wenigen Querschnitten wie nötig (Vorschub mittel, Einstich, Anfahren).
- G2 Anfahrweg: je Innenkontur Wandstärke + 1 mm (Einstellung), wenn er in die Kontur passt, sonst Punktanfahrt;
  Maschinenfeld 'anfahrweg' fest; Vorschub klein; ab 6 mm Wand zusätzlich 1 mm Überlappung.
- G3 dicke Wand mit N₂: ab 6 mm begrenzt die Maschine die Beschleunigung; kleine und mittlere Konturen und Ecken
  langsamer (Faktor nach Wand), bei O₂ nicht.
- D4/G7 Schnittqualität je Position: Standard, Qualität, Schnell, Kleines Rohr (Vorschub-Faktor wie die Adige-
  Tabellenarten); leer = Standard, bzw. Kleines Rohr automatisch bis 'Kleines Rohr bis Hüllkreis-Ø'.
- C4 Entladegrenze: Teil länger oder schwerer als die Entladegrenze wird von Hand entnommen (Vorgabe 30 s je Teil).
Ohne Qt."""
from . import rechenmerker

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


def _eingaben(p):
    """Eingaben des Schneidweg-Rechners der Position (technik) oder {}."""
    from . import schneidweg as sw
    return (sw.lesen(p.get("technik")) if p.get("technik") else None) or {}


def _lagen(p):
    """Konturen der Position mit Lage (skizze.lagen) oder []. Hängt nur am Text der Konturdaten (technik) und an
    der Länge: je Eingabe einmal gerechnet (Stabilitäts-Auftrag 18.11.2026, D3: bis 12.000 Mal je Vorgang neu
    gelesen). Die Aufrufer lesen die Lagen nur; jeder bekommt eine eigene Liste."""
    technik = p.get("technik")
    if not technik:
        return []
    laenge = _n(p.get("laenge"))
    if not isinstance(technik, str):
        return _lagen_rechnen(technik, laenge)
    return list(_LAGEN.holen((technik, laenge), lambda: tuple(_lagen_rechnen(technik, laenge))))


def _lagen_rechnen(technik, laenge):
    from . import schneidweg as sw, skizze as sk
    e = sw.lesen(technik)
    konturen = (e or {}).get("konturen") or []
    return sk.lagen(konturen, laenge) if konturen else []


_LAGEN = rechenmerker.Merker("Konturen mit Lage (zeit_zusatz._lagen)", 4000)


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


def vorschub_puffer(v, m, bahn=False):
    """Phase 5 (Patrick 16.11.2026 „es wird immer von 100 % Vorschub ausgegangen, was nicht der Realität entspricht“):
    Vorschübe groß, mittel, klein und Gravur × Vorschub-Ausnutzung der Maschine [%]; leer = 100 %. bahn (Phase 6 G2:
    Anfahren und Bremsen je Kontur sind berechnet): nur noch der Restpuffer für die Regelung."""
    a = _n((m or {}).get("vorschub_rest" if bahn else "vorschub_ausnutzung"))
    if a <= 0 or a >= 100 or not v[0]:
        return v
    f = a / 100.0
    h, i_, j, kv, l = v
    return (h * f, (i_ or 0) * f or i_, (j or 0) * f or j, (kv or 0) * f or kv, l)


# --- Zeiten je Teil ---------------------------------------------------------------------------------------------

def drehen_s(p, m):
    t = _n((m or {}).get("zeit_drehen"))
    if t <= 0:
        return 0.0
    return max(0, seiten(p) - 1) * t


# Messpunkte je Messung (Phase 3 E6): schnell 2, sorgfältig 4
MESS_PUNKTE = {"schnell": 2, "sorgfältig": 4}


def messung_s(m, art):
    """Zeit einer Messung [s] aus Antastweg und -geschwindigkeit (E6: Punkte × 2 × Weg ÷ Geschwindigkeit), sonst
    None."""
    weg, v = _n((m or {}).get("antast_weg")), _n((m or {}).get("antast_v"))
    if weg <= 0 or v <= 0:
        return None
    return MESS_PUNKTE.get(art, 2) * 2 * weg / (v / 60.0)


def messen_s(p, m):
    n = _n(p.get("messungen"))
    if n <= 0:
        return 0.0
    art = p.get("messart") if p.get("messart") in MESSEN else "schnell"
    feld = "zeit_messen_schnell" if art == "schnell" else "zeit_messen_sorgfaeltig"
    t = _n((m or {}).get(feld))
    b = messung_s(m, art)
    return n * (b if b is not None else t if t > 0 else MESSEN[art])


def hand_s(m, kg, laenge_mm):
    """Arbeit von Hand [s] (E6): Grundzeit + Zeit je kg × Gewicht + Zeit je m × Länge; None ohne Grundzeit."""
    m = m or {}
    if not isinstance(m.get("hand_grund"), (int, float)) or isinstance(m.get("hand_grund"), bool):
        return None
    return _n(m["hand_grund"]) + _n(m.get("hand_je_kg")) * _n(kg) + _n(m.get("hand_je_m")) * _n(laenge_mm) / 1000


def hub_s(m):
    """Kopf heben und senken je Kontur [s] (E4): 2 × Weg Z mit Eilgang und Beschleunigung Z + Einschwingen der
    Abstandsregelung; None, solange Hub, Eilgang Z oder Beschleunigung Z fehlen."""
    from .dynamik import bewegung
    m = m or {}
    h, v, a = _n(m.get("hub_z")), _n(m.get("eilgang_z")), _n(m.get("beschl_z"))
    if h <= 0 or v <= 0 or a <= 0:
        return None
    return 2 * bewegung(h / 1000, v / 60, a) + _n(m.get("zeit_regelung"))


def einziehen_s(m, laenge_mm):
    """Stange um ihre Länge einziehen bzw. ein Teil ausschieben [s] mit Eilgang und Beschleunigung X; None ohne."""
    from .dynamik import aktiv_verfahren, bewegung
    if not aktiv_verfahren(m):
        return None
    return bewegung(_n(laenge_mm) / 1000, _n(m["eilgang_x"]) / 60, _n(m["beschl_x"]))


STANGE_BEZUG = 6500.0       # [mm] Bezugslänge des berechneten Stangenwechsels (ohne max. Stangenlänge)


def stangenwechsel_berechnet(m):
    """(Stangenwechsel, Stangenwechsel SN) [s] für die Bezugslänge (max. Stangenlänge der Maschine, sonst 6.500 mm),
    E5: Laden (nicht parallel) + Spannen + Vermessen + Einziehen; SN + Schweißnaht suchen. None ohne 'Laden'."""
    m = m or {}
    if not isinstance(m.get("zeit_laden"), (int, float)) or isinstance(m.get("zeit_laden"), bool):
        return None
    ein = einziehen_s(m, _n(m.get("max_stange")) or STANGE_BEZUG)
    if ein is None:
        return None
    t = (0.0 if m.get("laden_parallel") == "ja" else _n(m["zeit_laden"])) + _n(m.get("zeit_spannen")) \
        + _n(m.get("zeit_vermessen")) + ein
    return t, t + _n(m.get("zeit_naht"))


def stange_laenge_s(m, laenge_mm):
    """Mehr- bzw. Minderzeit [s] einer Stange gegenüber der Bezugslänge beim berechneten Stangenwechsel (E5)."""
    if stangenwechsel_berechnet(m) is None:
        return 0.0
    return einziehen_s(m, laenge_mm) - einziehen_s(m, _n((m or {}).get("max_stange")) or STANGE_BEZUG)


def _zahl(w):
    return isinstance(w, (int, float)) and not isinstance(w, bool)


def entladen_s(m, p, k=None):
    """Entladen je Teil [s]: berechnet (Patrick 16.11.2026) = Grundzeit Klappe/Auflage + Zeit je m × Teillänge + Zeit
    je kg × Teilgewicht; ohne Grundzeit der feste Wert 'Entladen je Teil'; None ohne beides."""
    m = m or {}
    if _zahl(m.get("entladen_grund")):
        return (_n(m["entladen_grund"]) + _n(m.get("entladen_je_m")) * _n(p.get("laenge")) / 1000
                + _n(m.get("entladen_je_kg")) * _n(teil_kg(p, k)))
    return _n(m["zeit_entladen"]) if _zahl(m.get("zeit_entladen")) else None


def nebenzeit_s(m, p, k=None, laenge_verfahren=False):
    """Nebenzeit je Teil [s] (E5): Ausschieben um Teillänge + Schnittverlust mit Eilgang X + Entladen (entladen_s);
    None ohne Entladen oder Dynamik X. laenge_verfahren: der Weg über die Teillänge steht schon in den Leerwegen
    (Zeitart Bewegung, dynamik.verfahrzeit vom Anfangs- zum Endschnitt), hier nur noch der Schnittverlust."""
    m = m or {}
    ent = entladen_s(m, p, k)
    if ent is None:
        return None
    aus = einziehen_s(m, (0.0 if laenge_verfahren else _n(p.get("laenge"))) + _n(m.get("schnittverlust")))
    return None if aus is None else aus + ent


def tilt_s(p, m, wand, anfahr):
    """Ersparnis Active Tilt [s] (positiv) je Teil."""
    if (m or {}).get("active_tilt") != "ja" or _n(anfahr) <= 0 or _n(wand) > TILT_WAND + EPS:
        return 0.0
    gruppen = {}
    for d in _lagen(p):
        if d.get("art") in ("Lochfeld", "Bohrung"):
            gruppen[d["zeile"]] = gruppen.get(d["zeile"], 0) + 1
    return sum(n - 1 for n in gruppen.values() if n > 1) * _n(anfahr) * TILT_ANTEIL


def abfall_zerteilen(p, m, einst=None):
    """Zusatzschnitte (B7, Patrick 16.11.2026 „klein schneiden“): (Anzahl, mm) für Innenkonturen, deren Abfall
    zerschnitten wird (schneidfolge.abfall: Eigenschaft der Kontur bzw. Einstellung 'Abfall großer Ausschnitte' ab
    'abfall_max' der Maschine bzw. der Einstellung): so wenige Querschnitte wie nötig, kein Stück länger als die
    Grenze. Mit Mikrostegen gesicherter Abfall braucht keinen Zusatzschnitt (aber je Steg einen Einstich, mikrostege)."""
    from . import schneidfolge as sf
    rg = sf.mit_teil(sf.regel(einst, m), _eingaben(p))
    n, mm = 0, 0.0
    for d in _lagen(p):
        if d.get("art") in OHNE_ABFALL:
            continue
        k, lg = sf.zerschneiden_mm(d.get("eingabe") or {}, rg)
        n += k
        mm += lg
    return n, mm


def mikrostege(p, m, einst=None):
    """(Anzahl Mikrostege, Anteil der Einstichzeit je Steg) aller Innenkonturen eines Teils: jeder Steg ist ein
    neuer Einstich (Einstellung 'Mikrosteg: Anteil Einstichzeit', vorbelegt 100 %)."""
    from . import schneidfolge as sf
    rg = sf.mit_teil(sf.regel(einst, m), _eingaben(p))
    n = sum(sf.mikrostege_n(d.get("eingabe") or {}, rg) for d in _lagen(p) if d.get("art") not in OHNE_ABFALL)
    return n, rg["mikrosteg_anteil"]


def ende_abfall(p, m, k, wand, einst=None):
    """Abfallschnitte an kritischen Enden (Sonderanschnitt tiefer als 'ende_abfall_ab', schneidfolge.ende_abfall):
    (Anzahl Schnitte, Schnittlänge [mm], Anzahl Mikrostege), aus dem 3D-Netz des Teils (gemerkt)."""
    from . import rohr3d, schneidfolge as sf, schneidweg as sw
    e = sw.lesen(p.get("technik")) if p.get("technik") else None
    if not e or not any(sf.ende_sonder(e.get(s)) for s in ("a", "b")):
        return 0, 0.0, 0
    pr = k.profile.get(p.get("profil_id")) if k and getattr(k, "profile", None) else None
    if not pr:
        return 0, 0.0, 0
    rg = sf.mit_teil(sf.regel(einst, m), e)
    try:
        netz = rohr3d.netz(e, pr, _n(p.get("laenge")) or _n(e.get("laenge")) or 1000.0)
    except Exception:       # Netz nicht baubar: keine Abfallschnitte rechnen
        return 0, 0.0, 0
    zz = sf.zuege(netz)
    n, mm, st = 0, 0.0, 0
    for mid, s in ((sf.ENDE_A, "a"), (sf.ENDE_B, "b")):
        if sf.ende_sonder(e.get(s)) and zz.get(mid):
            ea = sf.ende_abfall(zz[mid][0], mid, rg, wand)
            if ea:
                n, mm, st = n + len(ea["schnitte"]), mm + ea["mm"], st + len(ea["stege"])
    return n, mm, st


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


OFFENE_PROFILE = ("U-Profil", "C-Profil", "L-Profil", "T-Profil", "Flachstahl", "I-/H-Träger")


def offen_ohne_einstich(p, form):
    """G4: Ausklinkungen am Rand eines offenen Profils beginnen an der freien Kante, ohne Einstich (Anzahl)."""
    if form not in OFFENE_PROFILE or _n(p.get("einstiche")) <= 0:
        return 0
    n = sum(1 for d in _lagen(p) if d.get("art") == "Ausklinkung")
    return int(min(n, _n(p.get("einstiche"))))


def anfahrweg_mm(p, m, wand, innen):
    """Anfahrweg aller Innenkonturen [mm]: mit 'Anfahrweg berechnen: Zugabe' je Kontur Materialstärke + Zugabe
    (Patrick 16.11.2026: „immer Materialstärke + 1 mm, wenn das möglich ist, sonst Punktanfahrt“): passt der Weg
    nicht in die Kontur (halbes Hüllmaß kleiner als der Weg), sticht der Laser auf der Kontur ein (Weg 0). Ohne
    Zugabe der feste Anfahrweg (+ Überlappung ab 6 mm)."""
    zugabe = (m or {}).get("anfahrweg_zugabe")
    if isinstance(zugabe, (int, float)) and not isinstance(zugabe, bool):
        if innen <= 0:
            return 0.0
        weg = _n(wand) + zugabe
        lagen = [d for d in _lagen(p) if d.get("art") != "Gravur"] if p else []
        if not lagen:
            return innen * weg
        passt = sum(1 for d in lagen if not _n(d.get("huelle")) or _n(d["huelle"]) / 2 >= weg - EPS)
        return min(innen, passt) * weg
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


def handling_s(p, m, k):
    """CALC-015 (Roadmap Phase 2): Zuschlag [s] je Teil ab Teillänge bzw. Teilgewicht der Maschine (Kran, zweite
    Person beim Entladen und Sortieren); 0, solange 'Handling-Zuschlag je Teil' oder beide Grenzen leer sind."""
    m = m or {}
    t, lg, kg = _n(m.get("zeit_handling")), _n(m.get("handling_laenge")), _n(m.get("handling_kg"))
    if t <= 0 or (lg <= 0 and kg <= 0):
        return 0.0
    if lg > 0 and _n(p.get("laenge")) >= lg - EPS:
        return t
    if kg > 0:
        g = teil_kg(p, k)
        if g is not None and g >= kg - EPS:
            return t
    return 0.0


def entnahme_s(p, m, k):
    h = handling_s(p, m, k)
    if not entnahme_grund(p, m, k):
        return h
    b = hand_s(m, teil_kg(p, k), _n(p.get("laenge")))
    t = _n((m or {}).get("zeit_entnahme"))
    return (b if b is not None else t if t > 0 else ENTNAHME_HAND) + h


def anteile(p, m, k, wand, vorschub, anfahr, innen, gas=None, zeit_ecke=0.0, f_ecke=1.0, einst=None):
    """Zusätzliche Zeitanteile je Teil [s]: dict(drehen, messen, anfahrweg, abfall, entnahme, tilt (Ersparnis beim
    Anfahren), ecken_innen (Eckzeit der Innenkonturen über die Kante, H3)); vorschub = wirksame Vorschübe."""
    h, i_, j, _, l = vorschub
    _, form = _form(p, k)
    out = dict(drehen=drehen_s(p, m), messen=messen_s(p, m), anfahrweg=0.0, abfall=0.0, entnahme=entnahme_s(p, m, k),
               tilt=tilt_s(p, m, wand, anfahr), ecken_innen=kanten_ueber(p, m, form) * _n(zeit_ecke) * _n(f_ecke),
               einstich_frei=offen_ohne_einstich(p, form) * _n(l) if (m or {}).get("rand_ohne_einstich") == "ja"
               else 0.0)
    if h:
        n = innenkonturen(p, innen)
        weg = anfahrweg_mm(p, m, wand, n)
        out["anfahrweg"] = anfahrweg_s(weg / n if n else 0.0, n, j or h, anschluss_beschleunigung(m, wand, gas))
        n, mm = abfall_zerteilen(p, m, einst)
        out["abfall"] = 60 * mm / (i_ or h) + n * (_n(l) + _n(anfahr)) if n else 0.0
        n, anteil = mikrostege(p, m, einst)
        n_e, mm_e, st_e = ende_abfall(p, m, k, wand, einst)
        out["abfall"] += (n + st_e) * anteil * _n(l) + (60 * mm_e / (i_ or h) + n_e * (_n(l) + _n(anfahr)) if n_e
                                                         else 0.0)
    return out


# --- je Beladung ------------------------------------------------------------------------------------------------

def beladung_s(s, m, k):
    """Zusatzzeit [s] einer Stange (bzw. zugeschnittenen Lieferstange je Werkstück): Ausrichten asymmetrischer
    Profile (B5) und Laden von Hand unter dem Lademinimum (A4)."""
    m = m or {}
    aus, lade = _n(m.get("zeit_ausrichten")), _n(m.get("lademinimum"))
    t = schwer_s(s, m, k)
    laengen = [_n(w.get("laenge")) for w in s.get("werkstuecke") or ()] or [_n(s.get("stange"))]
    t += sum(stange_laenge_s(m, lg) for lg in laengen)     # E5: Einziehen nach der echten Stangenlänge
    if aus <= 0 and lade <= 0:
        return t
    form = ((k.profile.get(s.get("profil")) if k else None) or {}).get("form") or ""
    kg_s = stange_kg(s, k) if hand_s(m, 0.0, 0.0) is not None else None      # Gewicht nur für E6 nötig
    lg_s = _n(s.get("stange"))
    for lg in laengen:
        if aus > 0 and form in ASYMMETRISCH:
            t += aus
        if lade > 0 and 0 < lg < lade - EPS:
            b = hand_s(m, kg_s * lg / lg_s if kg_s and lg_s else 0.0, lg)
            t += b if b is not None else (_n(m.get("zeit_hand_laden")) or HAND_LADEN)
    return t


def stange_kg(s, k):
    """Gewicht einer Stange [kg] aus kg/m × Stangenlänge, None ohne Profil/Werkstoff-Daten."""
    from .rechnen import kg_je_m
    if not k or not s.get("profil"):
        return None
    kgm = kg_je_m(s.get("profil"), s.get("werkstoff"), k)
    return kgm * _n(s.get("stange")) / 1000 if kgm else None


def schwer_s(s, m, k):
    """MAT-021 (Roadmap Phase 2): Mehrzeit [s] für eine Stange ab dem Gewicht „Schwere Stange ab [kg]“ der
    Maschine (Kran, zweite Person); 0, solange eins der beiden Felder leer ist."""
    ab, mehr = _n((m or {}).get("schwer_ab_kg")), _n((m or {}).get("zeit_schwer"))
    if ab <= 0 or mehr <= 0:
        return 0.0
    kg = stange_kg(s, k)
    return mehr if kg is not None and kg >= ab - EPS else 0.0


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

