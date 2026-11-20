"""Bauteilanalyse der Importengine (Laserhub-Vergleich, Patrick 20.11.2026 „CAD-Import, Bauteilerkennung und
automatische Geometrieanalyse“, Konzept docs/system-audit/IMPORTENGINE_LASERHUB_2011.md).

Kein zweites Erkennungssystem: alles hier wird aus den Messwerten der STEP-Messung (STEP-Import.exe, step_geometrie,
Art-Entscheidung step_arten) und der Erkennungs-Ampel des Programms (step.ampel) abgeleitet, ohne neue Geometrie-
Rechnung. Die Analyse läuft je Teil EINMAL (analysieren() merkt sie sich in den Messwerten unter "_analyse") und wird
mit der Position in positionen.step_merkmale gespeichert (step_pruefung.speicherwert, Schlüssel "analyse"); alle Module
lesen sie von dort (aus_position), statt neu zu messen.

Je Teil:
- kategorie: eine der KATEGORIEN (Rundrohr … Sonstiges Bauteil), dazu unterart (z. B. "gebogen", "Normteil")
- konfidenz: 0 … 100 %, erklärt die Ampel: grün ≥ 90, gelb 50 … 89, rot < 50. Die Stufe bestimmt allein die Ampel
  (step.ampel) – die Zahl macht nur sichtbar, wie viel fehlt. Abzüge stehen in "unsicherheiten".
- merkmale: jede erkannte Bearbeitung mit Merkmal (Bohrung, Langloch, Schlitz, Gehrungsschnitt …), Lage (x ab Ende A,
  Winkel bzw. Seite am Umfang), Abmessung, Orientierung, Schnittlänge, zugeordneter Bearbeitung und eigener Konfidenz
- kennzahlen: Profil, Wand, Länge, Volumen, Gewicht (Stahl 7,85 kg/dm³, nur Richtwert – die Kalkulation rechnet mit dem
  Werkstoff der Position), Schneidweg, Anzahl Bohrungen/Ausschnitte/Gravuren/Einstiche, Komplexitätsgrad

Ohne Qt.
"""
import json
import re
import math

VERSION = 1

RUNDROHR, VIERKANT, RECHTECK, OVAL, SONDER, OFFEN, BAUGRUPPE, BLECH, FRAES, DREH, SONSTIGE = (
    "Rundrohr", "Vierkantrohr", "Rechteckrohr", "Ovalrohr", "Sonderprofil", "Offenes Profil", "Rohrlaser-Baugruppe",
    "Blechteil", "Frästeil", "Drehteil", "Sonstiges Bauteil")
KATEGORIEN = (RUNDROHR, VIERKANT, RECHTECK, OVAL, SONDER, OFFEN, BAUGRUPPE, BLECH, FRAES, DREH, SONSTIGE)
ROHRLASER = (RUNDROHR, VIERKANT, RECHTECK, OVAL, SONDER, OFFEN)        # Kategorien, die der Rohrlaser schneidet

_FORM_KATEGORIE = {
    "Rundrohr": RUNDROHR, "Quadratrohr": VIERKANT, "Rechteckrohr": RECHTECK,
    "Flachoval": OVAL, "Halbflachoval": OVAL, "Elliptisch": OVAL,
    "Sonderprofil": SONDER, "RP-Profil": SONDER, "Mehrkammer": SONDER,
    "U-Profil": OFFEN, "C-Profil": OFFEN, "L-Profil": OFFEN, "T-Profil": OFFEN, "I-/H-Träger": OFFEN,
    "Flachstahl": OFFEN, "offenes Sonderprofil": OFFEN, "U-Stahl": OFFEN,
    "Blech": BLECH, "Blech gekantet": BLECH, "Frästeil": FRAES, "Drehteil": DREH,
}
DICHTE_STAHL = 7.85e-6          # kg/mm³ (Richtwert für das Gewicht in den Kennzahlen)
GRUEN_AB, GELB_AB = 90, 50      # Konfidenz-Bänder der Ampel
SCHLITZ_BREITE, SCHLITZ_VERHAELTNIS = 3.0, 8.0      # mm bzw. Länge/Breite: ab hier heißt ein Langloch „Schlitz“

# Merkmalnamen (Spalte „Merkmal“)
M_BOHRUNG, M_SACK, M_LANGLOCH, M_SCHLITZ, M_DURCHBRUCH, M_KONTUR, M_FREIFORM, M_GRAVUR, M_FRAES = (
    "Runde Bohrung", "Sackbohrung", "Langloch", "Schlitz", "Durchbruch", "Konturausschnitt", "Freiformkontur",
    "Gravur", "Fräsung")
M_GERADE, M_GEHRUNG, M_SCHRAEG, M_STIRN = "Gerader Schnitt", "Gehrungsschnitt", "Schrägschnitt", "Stirnausschnitt"
M_GEWINDE, M_SENKUNG, M_FLIESS, M_FASE = "Gewinde (Vorschlag)", "Senkung", "Fließloch", "Fase"
M_FERTIG = "Fertigbarkeit"      # Verstoß gegen eine Konstruktionsregel der Maschine (fertigbarkeit.py)

LASER, GRAVUR_LASER, GEWINDE, SENKEN, FRAESEN, FLOWDRILL = (
    "Laserschnitt", "Lasergravur", "Gewinde schneiden", "Senken", "Fräsen/Bohren (nicht lasern)", "Fließlochbohren")


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) else 0.0


def _json(v, leer=None):
    if isinstance(v, (dict, list)):
        return v
    try:
        x = json.loads(v) if v else leer
    except (TypeError, ValueError):
        return leer
    return x if x is not None else leer


def _r(x, st=1):
    return round(_f(x), st)


def _sicherheit(m):
    """Erkennungssicherheit je Merkmal der Messung (Spalte 'sicherheit' „achse=sicher;profil=unsicher …“)."""
    out = {}
    for teil in str(m.get("sicherheit") or "").split(";"):
        if "=" in teil:
            k, v = teil.split("=", 1)
            out[k.strip()] = v.strip()
    return out


# ---------------------------------------------------------------------------------------------------------- Kategorie
def kategorie(m):
    """(Kategorie, Unterart) eines gemessenen Körpers."""
    form = m.get("profilform") or ""
    if m.get("fehler") or not form:
        return SONSTIGE, "nicht lesbar" if m.get("fehler") else "nicht erkannt"
    if m.get("_normteil"):
        return SONSTIGE, "Normteil/Zukaufteil"
    if form in ("Gravurkörper", "Schweißnaht (Körper)", "Verbundkern"):
        return SONSTIGE, f"{form} (kein eigenes Fertigungsteil)"
    if form in ("Rundstahl", "Vierkantstahl"):
        return SONSTIGE, f"Vollmaterial ({form})"
    kat = _FORM_KATEGORIE.get(form)
    if kat is None:
        kat = SONDER if (m.get("bauteiltyp") or "") == "Profil" else SONSTIGE
    unter = form if kat in (OVAL, OFFEN, SONDER, BLECH) else ""
    if m.get("biegerohr") not in (None, "", "{}", "null"):
        unter = "gebogen"
    elif m.get("knick_schenkel") not in (None, "", "[]", "null"):
        unter = "Knickrahmen"
    elif kat == BLECH and form == "Blech gekantet":
        unter = "gekantet"
    return kat, unter


# ---------------------------------------------------------------------------------------------------------- Merkmale
def _orientierung(d):
    r = d.get("richtung")
    if r is None:
        return ""
    r = _f(r) % 180
    return "längs" if abs(r - 90) < 1 else "quer" if r < 1 or r > 179 else f"schräg {r:.0f}°"


def _lage(d):
    out = {}
    if d.get("z") is not None:
        out["x"] = _r(d.get("z"))
    if d.get("winkel") is not None:
        out["winkel"] = _r(d.get("winkel"))
    if d.get("seite"):
        out["seite"] = str(d.get("seite"))
    return out


def _kontur_merkmal(d, sicher):
    art = d.get("art") or ""
    konf = 95 if sicher else 75
    lg, br = _f(d.get("laenge")), _f(d.get("breite"))
    e = dict(art=art, schnittlaenge=_r(d.get("schnittlaenge")), durchgehend=bool(d.get("durchgehend", True)),
             orientierung=_orientierung(d), bearbeitung=LASER, **_lage(d))
    if art in ("Ende A", "Ende B"):
        form, geh = d.get("form") or "", _f(d.get("gehrung"))
        ux, uy = abs(_f(d.get("um_x"))), abs(_f(d.get("um_y")))
        if form == "komplex":
            e.update(merkmal=M_STIRN, abmessung=f"Hüllmaß {_r(d.get('huellmass'))} mm")
        elif form == "Gehrung" or abs(geh) > 0.05:
            # Gehrung = um eine Querachse geneigt; um beide Querachsen geneigt = Schrägschnitt (Doppelgehrung)
            schraeg = ux > 0.05 and uy > 0.05
            e.update(merkmal=M_SCHRAEG if schraeg else M_GEHRUNG, gehrung=_r(geh),
                     abmessung=f"{_r(geh)}°" + (f" (um X {_r(ux)}°, um Y {_r(uy)}°)" if schraeg else ""))
        else:
            e.update(merkmal=M_GERADE, abmessung="")
        e["ende"] = art[-1]
        return dict(e, konfidenz=konf if form != "komplex" else min(konf, 85))
    if art == "Bohrung":
        dm = _f(d.get("durchmesser")) or _f(d.get("huellmass"))
        e.update(merkmal=M_BOHRUNG, d=round(dm, 2), abmessung=f"Ø {dm:g} mm")
        if _f(d.get("schraeg")) > 0.5:
            e["orientierung"] = f"schräg {_r(d.get('schraeg'))}°"
        return dict(e, konfidenz=konf)
    if art == "Sackbohrung":
        dm = _f(d.get("durchmesser")) or _f(d.get("huellmass"))
        return dict(e, merkmal=M_SACK, d=round(dm, 2), abmessung=f"Ø {dm:g} mm", bearbeitung=FRAESEN,
                    durchgehend=False, konfidenz=konf)
    if art == "Gravur":
        return dict(e, merkmal=M_GRAVUR, laenge=round(lg, 1), breite=round(br, 1), tiefe=_r(d.get("tiefe"), 2),
                    abmessung=f"{lg:g} × {br:g} mm" + (f", Tiefe {_f(d.get('tiefe')):g} mm" if d.get("tiefe") else ""),
                    bearbeitung=GRAVUR_LASER, durchgehend=False, konfidenz=konf)
    if art == "Innenmerkmal":
        return dict(e, merkmal=M_FRAES, abmessung=str(d.get("hinweis") or ""), bearbeitung=FRAESEN,
                    durchgehend=False, konfidenz=min(konf, 80))
    if art in ("Langloch", "Rechteckausschnitt", "Ausschnitt"):
        schlitz = br > 0 and (br <= SCHLITZ_BREITE or lg / br >= SCHLITZ_VERHAELTNIS)
        name = M_SCHLITZ if schlitz else M_LANGLOCH if art == "Langloch" else M_DURCHBRUCH \
            if art == "Rechteckausschnitt" else M_KONTUR
        return dict(e, merkmal=name, laenge=round(lg, 2), breite=round(br, 2), abmessung=f"{lg:g} × {br:g} mm",
                    konfidenz=konf)
    if art == "Sonderkontur" or d.get("form") == "Ellipse":
        return dict(e, merkmal=M_KONTUR, laenge=round(lg, 2), breite=round(br, 2),
                    abmessung=f"{lg:g} × {br:g} mm" if lg else f"Hüllmaß {_r(d.get('huellmass'))} mm",
                    konfidenz=min(konf, 90))
    # Kontur ohne erkannte Form (nur Schnittlänge): Freiform, bitte prüfen
    return dict(e, merkmal=M_FREIFORM, abmessung=f"Hüllmaß {_r(d.get('huellmass'))} mm",
                hinweis=str(d.get("hinweis") or ""), konfidenz=min(konf, 70))


def _paare(text, felder=2):
    """'8.4/16.5:2|10/20:1' bzw. '8.0:2' -> [(Werte…, Anzahl)]."""
    out = []
    for teil in str(text or "").split("|"):
        if ":" not in teil:
            continue
        wert, n = teil.rsplit(":", 1)
        try:
            out.append((tuple(float(x) for x in wert.split("/")[:felder]), int(float(n))))
        except ValueError:
            continue
    return out


def _gewinde(bohrungen, gewinde_tabelle=None):
    """Gewinde-Vorschläge aus Kernloch-Ø: [(Gewinde, Kernloch-Ø, Anzahl)] (Tabelle step.KERNLOCH)."""
    from .step import KERNLOCH
    tab = gewinde_tabelle or KERNLOCH
    out = []
    for (d, *_), n in _paare(bohrungen, 1):
        for g, kern in tab:
            if abs(d - kern) <= 0.05:
                out.append((g, d, n))
    return out


def _blech_merkmale(b):
    out = []
    for d, n in sorted((b.get("bohrungen") or {}).items(), key=lambda x: _f(x[0])):
        out.append(dict(merkmal=M_BOHRUNG, art="Bohrung", d=_f(d), abmessung=f"Ø {_f(d):g} mm", anzahl=int(n),
                        bearbeitung=LASER, konfidenz=95))
    for k in b.get("konturen_lage") or ():
        if k.get("form") in (None, "Kreis"):
            continue
        out.append(dict(merkmal=M_KONTUR, art=str(k.get("form")), abmessung=str(k.get("achsen") or ""),
                        bearbeitung=LASER, konfidenz=90))
    kant = ((b.get("abwicklung") or {}).get("kantungen")) if isinstance(b.get("abwicklung"), dict) else None
    if kant:
        out.append(dict(merkmal="Biegung", art="Kantung", anzahl=int(kant), abmessung=f"{kant} Kantung(en)",
                        bearbeitung="Kanten", konfidenz=90))
    return out


def merkmale(m, gewinde_tabelle=None):
    """Alle erkannten Bearbeitungen eines Teils (Liste von dicts, siehe Modultext)."""
    sicher = _sicherheit(m).get("konturen", "sicher") == "sicher"
    out = [_kontur_merkmal(d, sicher) for d in _json(m.get("konturen_liste"), []) or () if isinstance(d, dict)]
    for (dm, sd), n in _paare(m.get("senkungen")):
        out.append(dict(merkmal=M_SENKUNG, art="Senkung", d=dm, abmessung=f"Ø {dm:g} / Senk-Ø {sd:g} mm", anzahl=n,
                        bearbeitung=SENKEN, konfidenz=90))
    for (dm, *_), n in _paare(m.get("fliessloecher"), 1):
        out.append(dict(merkmal=M_FLIESS, art="Fließloch", d=dm, abmessung=f"Kernloch Ø {dm:g} mm", anzahl=n,
                        bearbeitung=FLOWDRILL, konfidenz=90))
    for g, dm, n in _gewinde(m.get("bohrungen"), gewinde_tabelle):
        out.append(dict(merkmal=M_GEWINDE, art="Gewinde", d=dm, abmessung=f"{g} (Kernloch Ø {dm:g} mm)", anzahl=n,
                        bearbeitung=GEWINDE, konfidenz=70, hinweis="Annahme aus dem Kernloch – bitte bestätigen"))
    if "Fase" in str(m.get("hinweise") or ""):
        out.append(dict(merkmal=M_FASE, art="Fase", abmessung="laut Hinweis der Messung", bearbeitung="Fasen",
                        konfidenz=75))
    b = _json(m.get("blech"), None)
    if isinstance(b, dict) and (m.get("profilform") or "") in ("Blech", "Blech gekantet"):
        out.extend(_blech_merkmale(b))
    for f in m.get("_fertigbarkeit") or ():      # geprüft beim Import mit der Maschine des Angebots
        e = dict(merkmal=M_FERTIG, art=f.get("regel") or "", abmessung=f.get("text") or "", bearbeitung="prüfen",
                 konfidenz=70, hinweis="Konstruktionsregel der Maschine – Teil bleibt wie in der STEP")
        if f.get("x") is not None:
            e["x"] = f["x"]
        if f.get("seite"):
            e["seite"] = f["seite"]
        out.append(e)
    for e in out:   # Maße wie im übrigen Programm mit Dezimalkomma
        if isinstance(e.get("abmessung"), str):
            e["abmessung"] = re.sub(r"(\d)\.(\d)", r"\1,\2", e["abmessung"])
    return out


# ---------------------------------------------------------------------------------------------------- Kennzahlen
def kennzahlen(m, liste=None):
    """Kennzahlen für die Kalkulation (eine Quelle für alle Module)."""
    liste = merkmale(m) if liste is None else liste
    vol = _f(m.get("volumen"))
    zaehl = {}
    for x in liste:
        zaehl[x["merkmal"]] = zaehl.get(x["merkmal"], 0) + int(x.get("anzahl") or 1)
    bohr = zaehl.get(M_BOHRUNG, 0)
    aussch = sum(zaehl.get(k, 0) for k in (M_LANGLOCH, M_SCHLITZ, M_DURCHBRUCH, M_KONTUR, M_FREIFORM))
    gravur = zaehl.get(M_GRAVUR, 0)
    punkte = (0.2 * bohr + 0.5 * aussch + 1.5 * zaehl.get(M_FREIFORM, 0) + 0.5 * gravur
              + 1.0 * zaehl.get(M_GEHRUNG, 0) + 2.0 * (zaehl.get(M_SCHRAEG, 0) + zaehl.get(M_STIRN, 0))
              + 0.5 * (zaehl.get(M_SENKUNG, 0) + zaehl.get(M_GEWINDE, 0) + zaehl.get(M_FRAES, 0)))
    return dict(
        profilform=m.get("profilform") or "", abm_a=_r(m.get("abm_a"), 2), abm_b=_r(m.get("abm_b"), 2),
        wand=_r(m.get("wandstaerke"), 2), laenge=_r(m.get("laenge")), querschnitt=_r(m.get("flaeche"), 1),
        volumen_cm3=round(vol / 1000, 2), gewicht_stahl_kg=round(vol * DICHTE_STAHL, 3),
        schneidweg=_r(m.get("schneidweg")), einstiche=int(_f(m.get("konturen"))), bohrungen=bohr,
        ausschnitte=aussch, gravuren=gravur, merkmale=zaehl, fertigbar=not zaehl.get(M_FERTIG),
        komplexitaet="einfach" if punkte < 2 else "mittel" if punkte < 6 else "komplex",
        komplexitaet_punkte=round(punkte, 1))


# ---------------------------------------------------------------------------------------------------- Konfidenz
_ABZUG = {"wahrscheinlich": 8, "unsicher": 25}
_SICHERHEIT_NAME = {"achse": "Rohrachse", "laenge": "Länge", "profil": "Profil", "wandstaerke": "Wandstärke",
                    "konturen": "Konturen"}


def konfidenz(m, liste=None, farbe=None, gruende=None):
    """(Konfidenz 0 … 100, Stufe sicher/prüfen/unsicher, Unsicherheiten [Text]). Stufe = Erkennungs-Ampel."""
    if farbe is None:
        from .step import ampel
        try:
            farbe, gruende = ampel(m)
        except Exception:       # noqa: BLE001 – Analyse ist Zusatz, darf den Import nie stören
            farbe, gruende = ("rot" if m.get("fehler") else "gelb"), []
    wert, uns = 100, []
    if m.get("fehler"):
        return 0, "unsicher", [str(m.get("fehler"))]
    for k, v in _sicherheit(m).items():
        if v in _ABZUG:
            wert -= _ABZUG[v]
            uns.append(f"{_SICHERHEIT_NAME.get(k, k)} {v}")
    if m.get("gueltig") in ("0", "False", "nein", False):
        wert -= 20
        uns.append("Körper geometrisch ungültig")
    if (m.get("profilform") or "") in ("Sonderprofil", "offenes Sonderprofil"):
        wert -= 15
        uns.append("Profil nicht als Standardprofil erkannt")
    if "von Hand" in str(m.get("art_grund") or ""):
        wert -= 20
        uns.append("Art nur nach Hüllmaß gewählt")
    g = m.get("_rohr_gegenprobe") or m.get("_kant_gegenprobe")
    if g and not g[0]:
        wert -= 15
        uns.append("3D-Gegenprobe mit Abweichung")
    for x in liste or ():
        if x.get("konfidenz", 100) < 75:
            wert -= 5
            uns.append(f"{x['merkmal']} {x.get('abmessung') or ''}".strip() + " prüfen")
    for gr in (gruende or ()) if farbe != "gruen" else ():
        if gr and gr not in uns and len(uns) < 12:
            uns.append(str(gr))
    wert = max(0, min(100, wert))
    if farbe == "gruen":
        wert = max(wert, GRUEN_AB)
    elif farbe == "gelb":
        wert = max(GELB_AB, min(wert, GRUEN_AB - 1))
    else:
        wert = min(wert, GELB_AB - 1)
    stufe = {"gruen": "sicher", "gelb": "prüfen"}.get(farbe, "unsicher")
    return wert, stufe, list(dict.fromkeys(uns))


# ---------------------------------------------------------------------------------------------------- Gesamt
def analyse(m, gewinde_tabelle=None):
    """Bauteilanalyse eines gemessenen Körpers (dict, JSON-fähig)."""
    kat, unter = kategorie(m)
    liste = merkmale(m, gewinde_tabelle)
    wert, stufe, uns = konfidenz(m, liste)
    bearbeitungen = sorted({x["bearbeitung"] for x in liste if x.get("merkmal") not in (M_GERADE, M_FERTIG)})
    return dict(version=VERSION, kategorie=kat, unterart=unter, rohrlaser=kat in ROHRLASER, konfidenz=wert,
                stufe=stufe, unsicherheiten=uns, merkmale=liste, bearbeitungen=bearbeitungen,
                kennzahlen=kennzahlen(m, liste))


def analysieren(messwerte, neu=False):
    """Analyse je Teil einmal rechnen und in m["_analyse"] merken (neu=True rechnet nach einer Korrektur neu)."""
    for m in messwerte or ():
        if neu or "_analyse" not in m:
            try:
                m["_analyse"] = analyse(m)
            except Exception as e:     # noqa: BLE001 – Analyse ist Zusatz, darf den Import nie stören
                m["_analyse"] = dict(version=VERSION, kategorie=SONSTIGE, unterart="Analyse fehlgeschlagen",
                                     rohrlaser=False, konfidenz=0, stufe="unsicher",
                                     unsicherheiten=[f"Analyse fehlgeschlagen: {e}"], merkmale=[], bearbeitungen=[],
                                     kennzahlen={})
    return messwerte


def von(m):
    """Analyse eines Teils (gemerkt oder neu gerechnet und gemerkt)."""
    if "_analyse" not in m:
        analysieren([m])
    return m["_analyse"]


MERKMALE_MAX = 300      # so viele Merkmale je Position werden mit der Position gespeichert


def speicherform(m):
    """Analyse für positionen.step_merkmale (Merkmalliste gekürzt auf MERKMALE_MAX). Beim Übernehmen einmal neu
    gerechnet, damit Korrekturen aus dem Prüfdialog (Art, Profil) drin sind; danach lesen alle Module die
    gespeicherte Fassung (aus_position)."""
    analysieren([m], neu=True)
    a = dict(m["_analyse"])
    if len(a.get("merkmale") or ()) > MERKMALE_MAX:
        a["merkmale"] = a["merkmale"][:MERKMALE_MAX]
        a["merkmale_gekuerzt"] = True
    return a


def aus_position(p):
    """Gespeicherte Analyse einer Position (aus dem STEP-Import) oder None."""
    from .step_pruefung import lesen
    d = lesen((p or {}).get("step_merkmale"))
    return (d or {}).get("analyse")


def kurztext(a):
    """„Vierkantrohr · 96 % sicher · 3 Bohrungen, 1 Gehrungsschnitt“."""
    if not a:
        return ""
    zaehl = (a.get("kennzahlen") or {}).get("merkmale") or {}
    teile = [f"{n} {k}" for k, n in sorted(zaehl.items(), key=lambda x: -x[1]) if k != M_GERADE][:4]
    kat = a.get("kategorie") or ""
    if a.get("unterart"):
        kat += f" ({a['unterart']})"
    return f"{kat} · {a.get('konfidenz', 0)} % {a.get('stufe', '')}" + (f" · {', '.join(teile)}" if teile else "")
