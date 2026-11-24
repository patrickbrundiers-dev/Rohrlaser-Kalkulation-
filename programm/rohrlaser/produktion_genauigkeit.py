"""Produktionsdaten-Intelligenz, Phase 5: Genauigkeitsbewertung einer Kalkulation und Genauigkeit über die Zeit
(Patrick 24.11.2026, Abschnitt 12 „Automatische Genauigkeitskontrolle“). Ohne Qt.

bewertung(…) je Position: wie viele vergleichbare Maschinendaten es gibt (gleiche Profilform, Maße ± MASS_REL, Wand
± WAND_TOL, passender Werkstoff), davon mit an der Maschine gemessener Zeit, und wie genau die Kalkulation bei
diesen Teilen lag. Daraus je Bereich (Material, Geometrie, Bearbeitungszeit) eine Stufe. Grundsatz: keine künstlich
hohe Genauigkeit – „sehr gut“ nur mit gemessenen Zeiten (nicht mit der Rechnung des CAM), genug Teilen und kleiner
Abweichung; ohne Daten steht „keine Produktionsdaten“. Zusätzlich: welche Werte gemessen und welche geschätzt sind und
wo Daten fehlen.

genauigkeit_nach(…) für das Dashboard: mittlere Abweichung Zeit und Material je Werkstoff, Wandbereich, Profilart und
Monat (Entwicklung über die Zeit)."""
import statistics

from . import lst_vergleich as lv
from . import maschinendaten as md

MASS_REL = 0.2          # Profilmaße ± 20 % gelten als vergleichbar
WAND_TOL = 0.5          # mm
SEHR_GUT_N, GUT_N = 10, 3
SEHR_GUT_PCT, GUT_PCT = 10.0, 20.0
SEHR_GUT, GUT, GERING, KEINE = "sehr gut", "gut", "gering", "keine Produktionsdaten"
STUFEN = (SEHR_GUT, GUT, GERING, KEINE)


def _profil(prof):
    if not prof:
        return None
    return dict(profilform=prof.get("form"), a=max(prof.get("a") or 0, prof.get("b") or 0),
                b=min(prof.get("a") or 0, prof.get("b") or prof.get("a") or 0), wand=prof.get("wand") or 0)


def vergleichbar(t, prof, werkstoff_id, werkstoffe):
    """Maschinendaten-Teil t vergleichbar mit Profil (Stammdaten) und Werkstoff der Position?"""
    pr = _profil(prof)
    if not pr or not t.get("profilform") or t["profilform"] != pr["profilform"] or not t.get("a"):
        return False
    if abs((t.get("wand") or 0) - pr["wand"]) > WAND_TOL:
        return False
    ta, tb = t["a"], t.get("b") or t["a"]
    if pr["a"] and abs(ta - pr["a"]) > MASS_REL * pr["a"]:
        return False
    if pr["b"] and abs(tb - pr["b"]) > MASS_REL * pr["b"]:
        return False
    return lv.werkstoff_passt(t, werkstoff_id, werkstoffe)


def _stufe(n_gemessen, n_cam, abw):
    if n_gemessen >= SEHR_GUT_N and abw is not None and abw <= SEHR_GUT_PCT:
        return SEHR_GUT
    if n_gemessen >= GUT_N and abw is not None and abw <= GUT_PCT:
        return GUT
    if n_gemessen or n_cam:
        return GERING
    return KEINE


def bewertung(p, k, teile, abweichungen=None):
    """Bewertung einer Position p (dict) mit dem Kontext k (Profile, Werkstoffe) und den Produktionsdaten-Teilen
    (produktion_lst.teile). abweichungen: {(programm, teil_nr): |Zeitabweichung| %} aus dem Vergleich (optional).
    Ergebnis dict(vergleichbar, gemessen, cam, bpf, abweichung_pct, bereiche [dict(bereich, stufe, text)],
    gemessen_werte [Text], geschaetzt_werte [Text], fehlt [Text], text)."""
    prof = k.profile.get(p.get("profil_id")) if p.get("profil_id") else None
    vgl = [t for t in teile if vergleichbar(t, prof, p.get("werkstoff_id"), k.werkstoffe)]
    gem = [t for t in vgl if t.get("zeiten_gemessen")]
    cam = [t for t in vgl if t.get("zeiten_berechnet") and not t.get("zeiten_gemessen")]
    bpf = [t for t in vgl if (t.get("format") or "LST") == md.BPF]
    ab = abweichungen or {}
    werte = [ab[(t["programm"], t["teil_nr"])] for t in gem if (t["programm"], t["teil_nr"]) in ab]
    abw = round(statistics.median(werte), 1) if werte else None
    st_zeit = _stufe(len(gem), len(cam), abw)
    bereiche, gemessen, geschaetzt, fehlt = [], [], [], []
    # Material
    w = k.werkstoffe.get(p.get("werkstoff_id")) or {}
    if prof and w.get("dichte"):
        bereiche.append(dict(bereich="Materialdaten", stufe=SEHR_GUT, text="Profil und Werkstoff (mit Dichte) aus "
                                                                              "den Stammdaten"))
        gemessen.append("Material: Profil und Werkstoff aus den Stammdaten")
    elif prof:
        bereiche.append(dict(bereich="Materialdaten", stufe=GUT, text="Profil aus den Stammdaten, Werkstoff ohne "
                                                                         "Dichte"))
        fehlt.append("Dichte des Werkstoffs")
    else:
        bereiche.append(dict(bereich="Materialdaten", stufe=GERING, text="Profil oder Werkstoff unvollständig"))
        fehlt.append("Profil und Werkstoff der Position")
    # Geometrie
    if p.get("step_merkmale") and p.get("schneidweg"):
        bereiche.append(dict(bereich="Geometrieerkennung", stufe=SEHR_GUT, text="aus der STEP-Messung"))
        gemessen.append("Schnittlänge und Einstiche aus der STEP-Messung")
    elif p.get("schneidweg"):
        bereiche.append(dict(bereich="Geometrieerkennung", stufe=GUT, text="Schnittlänge eingegeben (ohne STEP)"))
        geschaetzt.append("Schnittlänge von Hand eingegeben")
    else:
        bereiche.append(dict(bereich="Geometrieerkennung", stufe=GERING, text="keine Schnittlänge"))
        fehlt.append("Schnittlänge (STEP-Datei oder Eingabe)")
    # Zeit
    if gem:
        t_zeit = f"{len(gem)} vergleichbare Teile mit gemessener Zeit" + (f", Kalkulation lag im Mittel {abw:.1f} % "
                                                                          f"daneben" if abw is not None else "")
    elif cam:
        t_zeit = f"nur {len(cam)} vergleichbare Teile mit CAM-Zeit (noch keine Messung der Maschine)"
    else:
        t_zeit = "keine vergleichbaren Maschinendaten: Zeit nur aus der Rechnung"
    bereiche.append(dict(bereich="Bearbeitungszeit", stufe=st_zeit, text=t_zeit.replace(".", ",")))
    if p.get("zeit_manuell") == "ja":
        gemessen.append("Bearbeitungszeit von Hand / aus dem Maschinenprogramm")
    else:
        geschaetzt.append("Bearbeitungszeit aus Schneiddaten und Zeitbausteinen berechnet")
    if not gem:
        fehlt.append("gemessene Zeiten vergleichbarer Teile (LST nach dem Lauf an der Maschine speichern)")
    if len(gem) < SEHR_GUT_N:
        fehlt.append(f"für „{SEHR_GUT}“ mindestens {SEHR_GUT_N} gemessene vergleichbare Teile (jetzt {len(gem)})")
    text = (f"Bearbeitungszeit: {st_zeit} ({t_zeit})").replace(".", ",")
    return dict(vergleichbar=len(vgl), gemessen=len(gem), cam=len(cam), bpf=len(bpf), abweichung_pct=abw,
                bereiche=bereiche, gemessen_werte=gemessen, geschaetzt_werte=geschaetzt, fehlt=fehlt, text=text)


def abweichungen(zeilen):
    """{(programm, teil_nr): |Abweichung %|} der verglichenen Teile mit gemessener Zeit (lst_vergleich.vergleich)."""
    return {(z["teil"]["programm"], z["teil"]["teil_nr"]): abs(z["diff_pct"]) for z in zeilen
            if z.get("diff_pct") is not None and z.get("ist_s") is not None and not z.get("geometrie")}


def angebot(db, positionen, teile=None, zeilen=None):
    """Bewertung je Laserposition eines Angebots: [(Position, Bewertung)]."""
    from . import produktion_lst as pl
    teile = teile if teile is not None else pl.teile(db)
    if zeilen is None:
        zeilen = lv.vergleich(db, teile) if any(t.get("zeiten_gemessen") for t in teile) else []
    ab = abweichungen(zeilen)
    k = db.kontext()
    return [(p, bewertung(p, k, teile, ab)) for p in positionen if p.get("profil_id")]


def genauigkeit_nach(ergebnisse, merkmal):
    """Mittlere |Abweichung| % von Zeit und Material je Gruppe; merkmal: 'werkstoff', 'wand', 'profil', 'monat'.
    ergebnisse aus produktion_abgleich.auswerten. Ergebnis [dict(gruppe, n, zeit_pct, material_pct)]."""
    from . import kalibrierung
    gr = {}
    for e in ergebnisse:
        t = e["zeile"]["teil"]
        if merkmal == "werkstoff":
            g = str(t.get("werkstoff") or "?")
        elif merkmal == "wand":
            try:
                g = kalibrierung.bereich(t.get("wand"))
            except (TypeError, ValueError):
                g = "?"
        elif merkmal == "profil":
            g = t.get("profilform") or "?"
        else:
            g = str(t.get("gelesen") or "")[:7] or "?"
        w = {x["schluessel"]: x for x in e["werte"]}
        d = gr.setdefault(g, dict(zeit=[], material=[]))
        if (w.get("zeit") or {}).get("diff_pct") is not None:
            d["zeit"].append(abs(w["zeit"]["diff_pct"]))
        if (w.get("material") or {}).get("diff_pct") is not None:
            d["material"].append(abs(w["material"]["diff_pct"]))
    out = []
    for g, d in sorted(gr.items()):
        out.append(dict(gruppe=g, n=max(len(d["zeit"]), len(d["material"])),
                        zeit_pct=round(statistics.mean(d["zeit"]), 1) if d["zeit"] else None,
                        material_pct=round(statistics.mean(d["material"]), 2) if d["material"] else None))
    return out


def qualitaet(teile):
    """Datenqualität aller Produktionsdaten: dict(vollstaendig_pct, gemessen_pct, bpf, unsicher (Teile mit unsicher
    gedeuteten Kernwerten))."""
    from . import trumpf_programm as tp
    if not teile:
        return dict(vollstaendig_pct=None, gemessen_pct=None, bpf=0, unsicher=0)
    n = len(teile)
    unsicher = sum(1 for t in teile if any(not (x[4] if len(x) > 4 else True)
                                         for s, x in (t.get("merkmale") or {}).items()
                                         if s in ("schneidweg", "einstiche", "konturen")))
    return dict(vollstaendig_pct=round(100 * sum(1 for t in teile if t.get("qualitaet") == tp.VOLL) / n, 1),
                gemessen_pct=round(100 * sum(1 for t in teile if t.get("zeiten_gemessen")) / n, 1),
                bpf=sum(1 for t in teile if (t.get("format") or "LST") == md.BPF), unsicher=unsicher)
