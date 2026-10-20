"""Versioniertes Ergebnisformat der STEP-Messung (JSON).

Je STEP-Datei: Dateiname, Importstatus, Einheit, Meldungen des STEP-Lesers und je Körper Profiltyp, Außen- und
Innenmaße, Wandstärke mit Einzelmessungen, Länge, Längsachse, Konturen mit Lage, Schnittwinkel der Enden, Prüfstatus,
Warnungen und Erkennungssicherheit je Merkmal. Alle Längen in mm, Winkel in Grad.

Regeln: Was nicht gemessen wurde, ist null (nie 0 oder ein Ersatzwert); der Grund steht in "warnungen".
"pruefstatus" = "plausibel" heißt nur, dass die Messung in sich stimmig ist. Es ist keine Fertigungsfreigabe.

Versionen von SCHEMA_VERSION:
- 1.0 (19.10.2026): erste Fassung.
- 1.1 (20.10.2026): "bauteiltyp" (Profil, Blech, Blech gekantet) und je Blech der Block "blech" (Länge, Breite, Dicke,
  Flächen, Volumen, Kontur, Innenkonturen, Bohrungen, Fingerabdruck). Bei Blechen sind Profilwerte (Querschnitt,
  Wandstärke, Innenmaße) null. Felder aus 1.0 unverändert.
"""
from datetime import datetime

SCHEMA = "rohrlaser-step-messung"
SCHEMA_VERSION = "1.1"
HOHL = ("Rundrohr", "Quadratrohr", "Rechteckrohr", "Sonderprofil")
VOLL = ("Flachstahl", "Vierkantstahl", "Rundstahl")
BLECH = ("Blech", "Blech gekantet")


def _blech(b):
    """Blechblock fürs JSON (nur Bleche)."""
    if not b:
        return None
    out = {k: _r(b.get(k), 2) for k in ("laenge", "breite", "hoehe", "dicke", "flaeche_aussen", "flaeche_netto",
                                         "abwicklung_flaeche", "volumen", "umfang_aussen", "umfang_innen")
           if b.get(k) is not None}
    out.update(kontur=b.get("kontur"), innenkonturen=b.get("innen", 0),
               bohrungen=[dict(durchmesser=_r(d), anzahl=n) for d, n in (b.get("bohrungen") or {}).items()],
               fingerabdruck=b.get("fingerabdruck"))
    return out


def _r(x, n=3):
    return None if x is None else round(float(x), n) + 0.0     # + 0.0: keine -0.0


def koerper(t):
    """Ergebnis eines Körpers (step_geometrie.Teil) als dict."""
    gemessen = bool(t.profilform) and t.laenge > 0
    hohl = t.profilform in HOHL and t.innen_a > 0
    konturen = [k for k in t.konturen_liste if not k["art"].startswith("Ende ")]
    enden = {k["art"]: k for k in t.konturen_liste if k["art"].startswith("Ende ")}
    blech = t.profilform in BLECH
    if blech:
        aussen = dict(laenge=_r(t.blech.get("laenge")), breite=_r(t.blech.get("breite")),
                      dicke=_r(t.blech.get("dicke")))
    elif t.profilform in ("Rundrohr", "Rundstahl"):
        aussen = dict(durchmesser=_r(t.abm_a))
    elif t.profilform in ("Quadratrohr", "Vierkantstahl"):
        aussen = dict(a=_r(t.abm_a), b=_r(t.abm_a))
    else:
        aussen = dict(a=_r(t.abm_a), b=_r(t.abm_b))
    if gemessen and hohl:
        innen = dict(durchmesser=_r(t.innen_a)) if t.profilform == "Rundrohr" else dict(a=_r(t.innen_a),
                                                                                         b=_r(t.innen_b))
    else:
        innen = None
    if gemessen and t.profilform not in VOLL and not blech:
        wand = dict(wert=_r(t.wandstaerke), minimum=_r(min([m[3] for m in t.wand_messungen] + [t.wandstaerke])),
                    maximum=_r(max([m[3] for m in t.wand_messungen] + [t.wandstaerke])),
                    einzelmessungen=[dict(z=_r(z), x=_r(x), y=_r(y), wert=_r(w), seite=s)
                                     for z, x, y, w, s in t.wand_messungen])
    else:
        wand = None
    konturen_ausgewertet = gemessen and t.sicherheit.get("konturen") not in (None, "nicht ausgewertet")
    return {
        "nr": t.koerper,
        "artikel_vorschlag": t.datei,
        "koerperart": t.koerperart or None,
        "geometrie_gueltig": t.gueltig,
        "volumen_mm3": _r(t.volumen, 1) if t.koerperart != "Flächenmodell offen" else None,
        "oberflaeche_mm2": _r(t.oberflaeche, 1),
        "anzahl_flaechen": t.n_flaechen,
        "anzahl_kanten": t.n_kanten,
        "huellquader_datei": list(map(_r, t.huelle)) if t.huelle else None,
        "bauteiltyp": t.bauteiltyp or None,
        "profiltyp": t.profilform or None,
        "profil_id_vorschlag": t.profil_id_vorschlag or None,
        "aussenmasse": aussen if gemessen else None,
        "innenmasse": innen,
        "querschnittsflaeche_mm2": _r(t.flaeche, 2) if gemessen and not blech else None,
        "wandstaerke": wand,
        "laenge": _r(t.laenge) if gemessen else None,
        "laengsachse": dict(richtung=list(map(lambda x: _r(x, 6), t.achse_global)),
                            ende_a=list(map(_r, t.ende_a_global))) if gemessen and t.achse_global else None,
        "schnittwinkel": {name: dict(form=e.get("form"), gesamt=e.get("gehrung"), um_x=e.get("um_x"),
                                     um_y=e.get("um_y")) for name, e in enden.items()} if konturen_ausgewertet else None,
        "schneidweg": dict(gesamt=_r(t.schneidweg, 2), ende_a=_r(t.ende_a, 2), ende_b=_r(t.ende_b, 2),
                           innen=_r(t.innen, 2), gravur=_r(t.gravur, 2), einstiche=t.konturen)
        if konturen_ausgewertet else None,
        "konturen": [dict(d) for d in konturen] if konturen_ausgewertet else None,
        "enden": list(enden.values()) if konturen_ausgewertet else None,
        "blech": _blech(t.blech) if blech else None,
        "pruefstatus": t.pruefstatus,
        "warnungen": list(t.hinweise),
        "erkennungssicherheit": dict(t.sicherheit),
    }


def datei(name, teile=None, fehler=None):
    """Ergebnis einer STEP-Datei. teile: Liste step_geometrie.Teil; fehler: Text, wenn die Datei nicht lesbar war."""
    if fehler is not None or not teile:
        return {"datei": name, "importstatus": "nicht lesbar", "fehler": fehler, "einheit_datei": None,
                "einheit_ausgabe": "mm", "meldungen": [], "warnungen": [], "baugruppe": None, "anzahl_koerper": 0,
                "koerper": []}
    meldungen = teile[0].meldungen
    leer = [h for t in teile if not t.koerper for h in t.hinweise]     # z. B. "Kein Körper … in der Datei"
    return {
        "datei": name,
        "importstatus": "gelesen mit Meldungen" if meldungen else "gelesen",
        "fehler": None,
        "einheit_datei": teile[0].einheit or None,
        "einheit_ausgabe": "mm",
        "meldungen": list(meldungen),
        "warnungen": leer,
        "baugruppe": len(teile) > 1,
        "anzahl_koerper": len([t for t in teile if t.koerper]),
        "koerper": [koerper(t) for t in teile if t.koerper],
    }


def gesamt(dateien):
    """Gesamtergebnis einer Messung mehrerer Dateien."""
    return {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "erzeugt": datetime.now().isoformat(timespec="seconds"),
            "hinweis": "Messergebnis aus der Geometrie, keine Fertigungsfreigabe.", "dateien": dateien}
