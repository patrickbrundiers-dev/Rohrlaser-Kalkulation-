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


# ---------------------------------------------------------------- Nachregeln (A4 Prüfsammlung, Patrick 07.11.2026)
# Nach dem Pool der Arten: Fälle, in denen die Messung ein Profil findet, das keins ist, und eine andere Art im Pool
# passt. Je Regel (Name, Prüfung(t) -> (Gruppe, Grund) oder None); die erste zutreffende tauscht.

def _kandidat(t, gr):
    """Die Messung der Gruppe gr aus dem Pool (t.alternative oder t.arten) oder None."""
    if t.alternative is not None and gruppe(t.alternative) == gr:
        return t.alternative
    return (t.arten or {}).get(gr)


def _blech_gekantet_rund(b):
    """Gekantetes Blech mit Biegeradien (nicht scharfkantig, Abwicklung ohne Fehler)."""
    if b is None or b.bauteiltyp != "Blech gekantet" or not isinstance(b.blech, dict):
        return False
    abw = b.blech.get("abwicklung") or {}
    return not abw.get("scharf") and not abw.get("fehler")


def _flachstahl_blech(t):
    if t.bauteiltyp != "Profil" or t.profilform != "Flachstahl" or _kandidat(t, BLECH) is None:
        return None
    if t.innen_konturen:
        return BLECH, "Flachstahl mit Ausschnitten/Bohrungen in der Fläche: Laserteil aus Blech"
    if t.laenge < g.FLACHSTAHL_LAENGE * t.abm_a - 1e-6:
        return BLECH, f"Flachstahl kürzer als {g.FLACHSTAHL_LAENGE:g} × Breite (Lasche): Laserteil aus Blech"
    return None


def _sonderprofil_kantteil(t):
    if t.bauteiltyp != "Profil" or t.profilform != "Sonderprofil" or t.normprofil:
        return None
    b = _kandidat(t, BLECH)
    if _blech_gekantet_rund(b):
        return BLECH, "Profil nicht erkannt, aber gekantetes Blech mit Biegeradien: Kantteil"
    if b is not None and b.bauteiltyp == "Blech gekantet" and t.sicherheit.get("wandstaerke") == "unsicher" \
            and not ((b.blech or {}).get("abwicklung") or {}).get("fehler"):
        # Mehrkammer-„Profil“ mit ungleicher Wand, das sich als Blech abwickeln lässt (Wanne mit Rand, 0003)
        return BLECH, "Profil nicht erkannt (Wand ungleich), aber als Blech abwickelbar: Kantteil"
    return None


def _winkel_kein_normmass(t):
    b = _kandidat(t, BLECH)
    if t.bauteiltyp == "Profil" and t.profilform == "L-Profil" and not t.normprofil and b is not None \
            and b.bauteiltyp == "Blech gekantet" and not ((b.blech or {}).get("abwicklung") or {}).get("fehler"):
        return BLECH, f"Winkel {t.profil_id_vorschlag or ''} ist kein Normmaß: Kantteil".replace("  ", " ")
    return None


def _klotz(t):
    if t.bauteiltyp == "Profil" and t.profilform in ("Quadratrohr", "Rechteckrohr") \
            and t.laenge < max(t.abm_a, t.abm_b) - 1e-6 and t.sicherheit.get("wandstaerke") == "unsicher":
        return DREHFRAES, "kürzer als breit und Wand nicht einheitlich: Klotz mit Bohrung, kein Rohrstück"
    return None


NACHREGELN = (
    ("Flachstahl → Blech", _flachstahl_blech),
    ("Sonderprofil → Kantteil", _sonderprofil_kantteil),
    ("Winkel ohne Normmaß → Kantteil", _winkel_kein_normmass),
    ("Klotz → Frästeil", _klotz),
)


def _tauschen(t, n, grund, regel):
    """n (aus dem Pool von t) wird die Messung; t und die übrigen Arten bleiben wählbar."""
    pool = [x for x in [t.alternative, *(t.arten or {}).values()] if x is not None and x is not n]
    n.alternative = t
    t.alternative = None
    n.arten = {gruppe(x): x for x in pool if gruppe(x) not in (gruppe(n), gruppe(t))}
    n.arten_grund = {k: v for k, v in (t.arten_grund or {}).items() if k not in n.arten and k != gruppe(t)}
    t.arten, t.arten_grund = {}, {}
    for x in pool:
        x.alternative = None
    n.art_grund, n.art_regel = grund, regel
    if n.drehfraes:     # von der Regel gewählt, nicht von Hand
        from step_drehfraes import VON_HAND
        info = n.drehfraes
        if VON_HAND in info.get("merkmale", ()):
            info["merkmale"] = [m for m in info["merkmale"] if m != VON_HAND]
            info["text"] = f"{info['art']} ({', '.join(info['merkmale'] + info.get('zusatz', []))})" \
                if info["merkmale"] or info.get("zusatz") else info["art"]
    for name in ("einheit", "meldungen", "bauteil", "pfad", "knoten", "koerperart", "gueltig", "struktur", "naehte",
                 "ohne_naht"):
        if hasattr(t, name) and not getattr(n, name, None):
            setattr(n, name, getattr(t, name))
    return n


MEHRTEILIG_FUELLGRAD = 0.05     # Frästeil: Volumen unter so viel des Hüllquaders = dünne Bleche, nicht aus dem Vollen


def _mehrteilig(solid, t):
    """Grund, warum der Körper wohl mehrere Teile in einem ist (verschmolzene Schweißbaugruppe), sonst None."""
    import re
    if t.bauteiltyp == "Frästeil" and t.drehfraes and t.abm_a and t.abm_b and t.laenge:
        fuell = (t.volumen or 0) / (t.abm_a * t.abm_b * t.laenge)
        if 0 < fuell < MEHRTEILIG_FUELLGRAD:
            return f"Frästeil aus dünnen Wänden (nur {100 * fuell:.1f} % des Hüllquaders gefüllt)"
    if t.bauteiltyp == "Blech gekantet":
        f = getattr(t, "abwicklung_fehler", "") or ""
        m = re.match(r"Biegezone mit (\d+) Schenkeln", f) or re.match(r"(\d+) statt 2 Blechhäute", f)
        if m and int(m.group(1)) >= 3:
            return f"Bleche stoßen aneinander ({f})"
    if t.bauteiltyp in ("Profil", "Blech") and t.profilform in ("Sonderprofil", "offenes Sonderprofil", "Blech"):
        import step_drehfraes as df
        fl = df.flaechen(solid)
        if len(fl) <= df.NORMTEIL_FLAECHEN_MAX:
            for z in (e for e in fl if e["typ"] == "zylinder"):
                kante, rest = df.sechskante(fl, *z["achse"])
                if kante and rest:
                    return f"Sechskant (Mutter SW {kante[0]['schluessel']:g}) mit weiteren Teilen verschmolzen"
    return None


def _mehrteilig_markieren(t, grund):
    """Gelb, nicht übernommen (Patrick 07.11.2026: markieren und Hinweis, nicht automatisch zerlegen)."""
    t.sicherheit["profil"] = "unsicher"
    t.hinweise.insert(0, f"Mehrere Teile in einem Körper? {grund} – nicht übernommen: STEP in Einzelteile aufteilen "
                         "oder nach Prüfung von Hand anhaken")
    t.art_grund = f"mehrere Teile in einem Körper: {grund}"
    return t


def nachregeln(t, solid=None):
    """Die erste zutreffende Nachregel tauscht die Messung gegen die passende Art aus dem Pool; sonst t. Danach:
    ein Körper, der wohl aus mehreren verschmolzenen Teilen besteht, wird gelb markiert."""
    t = _nachregeln(t)
    if solid is not None:
        try:
            grund = _mehrteilig(solid, t)
        except Exception:  # die Prüfung darf die Messung nie verhindern
            grund = None
        if grund:
            _mehrteilig_markieren(t, grund)
    return t


def _nachregeln(t):
    for name, pruef in NACHREGELN:
        try:
            r = pruef(t)
        except Exception:  # eine Regel darf die Messung nie verhindern
            r = None
        if r is None:
            continue
        gr, grund = r
        n = _kandidat(t, gr)
        if n is not None:
            return _tauschen(t, n, grund, name)
    return t
