"""Zentrale Art-Entscheidung beim STEP-Import (Patrick 04.11.2026: „Kantteile werden als Frästeile erkannt … eine
Auswahl, dass ich immer manuell noch umentscheiden kann, ob Blech, Rohr oder Dreh-/Frästeil“, Entscheidung „Zentrale
Art-Entscheidung“).

Jedes Teil wird in allen passenden Arten gemessen:
- Blech: ebenes oder gekantetes Blech (Blechprüfung _flach_pruefen, Abwicklung),
- Rohr/Profil: die Profilmessung (Rohr, Profil, Flachstahl, Vollmaterial),
- Dreh-/Frästeil: Zukaufteil mit Richtpreis (step_drehfraes; nicht erkannt: „von Hand gewählt“ nach dem Hüllquader).

Welche Art gilt, entscheidet nur noch die Regelliste REGELN in entscheiden() – in dieser Reihenfolge, die erste
zutreffende Regel gewinnt, ihr Grund steht im Teil (t.art_grund, Hinweisspalte im Prüfdialog). Die übrigen Arten
bleiben wählbar: die nächstliegende in t.alternative (wie bisher, z. B. Profil ↔ Kantteil), die anderen in t.arten
{Gruppe: Teil}; eine Art, die sich nicht messen lässt, steht mit Grund in t.arten_grund {Gruppe: Grund}.
"""
import step_geometrie as g

BLECH, PROFIL, DREHFRAES = "Blech", "Rohr/Profil", "Dreh-/Frästeil"
GRUPPEN = (BLECH, PROFIL, DREHFRAES)


def gruppe(t):
    """Gruppe eines Teils: Blech (eben/gekantet), Dreh-/Frästeil oder Rohr/Profil (alles andere)."""
    if t is None:
        return None
    if t.bauteiltyp in ("Blech", "Blech gekantet") or t.profilform in ("Blech", "Blech gekantet"):
        return BLECH
    if t.bauteiltyp in ("Drehteil", "Frästeil") or t.drehfraes:
        return DREHFRAES
    return PROFIL


def _kantteil(t):
    """Kantteil mit Biegeradien (außen = innen + Dicke) und gleicher Blechdicke: die Messung selbst ist ein gekantetes
    Blech oder sie hat eins als Auswahl und die Blechprüfung fand Biegungen (t._kantradien)."""
    if t is None:
        return False
    if t.bauteiltyp == "Blech gekantet":
        abw = ((t.blech or {}).get("abwicklung") or {}) if isinstance(t.blech, dict) else {}
        return not abw.get("scharf")
    alt = t.alternative
    return bool(getattr(t, "_kantradien", False) and alt is not None and alt.bauteiltyp == "Blech gekantet")


# Regelliste: (Name, Prüfung(t, d) -> Grund oder None, Wahl(t, d) -> Teil). t = Messung als Blech/Rohr/Profil nach den
# Kantteil-Regeln (_kantteil, _alternative_form), d = erkanntes Dreh-/Frästeil oder None.
REGELN = (
    ("Biegerohr/Knickrahmen", lambda t, d: "Biegerohr bzw. Knickrahmen (gebogenes Rohr)"
     if t is not None and (t.biegerohr or t.knick_schenkel) else None, lambda t, d: t),
    ("Kantteil", lambda t, d: "Kantteil mit Biegeradien (außen = innen + Dicke) – nie Dreh-/Frästeil"
     if d is not None and _kantteil(t) else None, lambda t, d: t),
    ("Dreh-/Frästeil", lambda t, d: (d.drehfraes or {}).get("text") or d.profilform
     if d is not None else None, lambda t, d: d),
    ("Messung", lambda t, d: "" if t is not None else None, lambda t, d: t),
)


def entscheiden(t, d):
    """Die Regelliste: das Teil der ersten zutreffenden Regel mit t.art_grund (Grund, leer = wie gemessen) und
    t.art_regel; die andere Messung (t bzw. d) kommt in den Pool der Arten (ergaenzen)."""
    for name, pruef, wahl in REGELN:
        grund = pruef(t, d)
        if grund is None:
            continue
        n = wahl(t, d)
        n.art_grund, n.art_regel = grund, name
        if n is d and t is not None:
            n._verworfen = [t]
        elif d is not None and n is not d:
            n._verworfen = [d]
        return n
    return t


def _blech_messen(solid, t):
    """Das Teil als Blech messen (ebenes oder gekantetes Blech) oder (None, Grund)."""
    fl = getattr(t, "_fl", None)
    if fl is None:
        try:
            fl = g._flach_pruefen(solid, g._volumen(solid))
        except Exception:  # nicht messbar
            fl = None
    if not fl:
        return None, "keine gleichbleibende Blechdicke"
    try:
        if fl["art"] == "gekantet" and "abwicklung" not in fl:
            from step_abwicklung import abwickeln
            try:
                fl["abwicklung"] = abwickeln(solid, fl["dicke"])
            except Exception as e:  # ohne Abwicklung bleibt es bei den Außenmaßen
                fl["abwicklung"] = dict(fehler=str(e))
        daten = g._blech_daten(solid, fl) if fl["art"] == "eben" else None
        if daten is not None and fl["dicke"] > g.BLECH_DICKE_BLECHMODUS * daten["breite"] + 1e-6:
            # „Dicke“ größer als ein Blech sein kann (Rohr der Länge nach als Platte): kein Blech
            return None, "keine Blechform (zu dick für die Breite, z. B. Rohr oder Vollkörper)"
        b = g._blech_teil(solid, t.datei, t.koerper, fl, g._volumen(solid), False, daten)
    except Exception as e:  # Blechmessung gescheitert
        return None, f"als Blech nicht messbar ({e})"
    return b, ""


def ergaenzen(solid, t):
    """Pool der Arten vervollständigen: je Gruppe, die weder t noch t.alternative ist, eine Messung in t.arten bzw. der
    Grund, warum es sie nicht gibt, in t.arten_grund. Nie eine Ausnahme (die Messung von t bleibt immer)."""
    t.arten, t.arten_grund = {}, {}
    haben = {gruppe(t)}
    if t.alternative is not None:
        haben.add(gruppe(t.alternative))
    verworfen = []
    for v in getattr(t, "_verworfen", None) or ():
        verworfen += [v] + ([v.alternative] if v.alternative is not None else [])
    for v in verworfen:
        gr = gruppe(v)
        if gr not in haben:
            if t.alternative is None:
                t.alternative = v
            else:
                t.arten[gr] = v
            haben.add(gr)
    for gr in GRUPPEN:
        if gr in haben:
            continue
        try:
            if gr == DREHFRAES:
                from step_drehfraes import pruefen
                n = pruefen(solid, t, t.datei, t.koerper, erzwingen=True)
                n, grund = (n, "") if n is not None and n is not t else (None, "als Dreh-/Frästeil nicht messbar")
            elif gr == BLECH:
                n, grund = _blech_messen(solid, t)
            else:       # die Profilmessung lief schon (zu teuer, sie zu wiederholen): von Hand nachtragen
                n, grund = None, "kein gleichbleibender Querschnitt – als Rohr/Profil von Hand nachtragen"
        except Exception as e:  # eine Zusatzmessung darf die Messung nie verhindern
            n, grund = None, f"nicht messbar ({e})"
        if n is not None:
            n.alternative = None
            t.arten[gr] = n
        else:
            t.arten_grund[gr] = grund
    t.__dict__.pop("_verworfen", None)
    for a in t.arten.values():
        a.__dict__.pop("_verworfen", None)
        a.alternative = None
    if t.alternative is not None:
        t.alternative.__dict__.pop("_verworfen", None)
        if t.alternative.alternative is t:
            t.alternative.alternative = None
    return t
