"""Richtpreis für Dreh- und Frästeile (Patrick 03.11.2026, Plan „Richtpreise für Dreh- und Frästeile“, Freigabe
alle a, Frage 2 b: Arbeitsgänge je Teil, „so genau wie möglich“).

Ein Dreh- oder Frästeil aus dem STEP-Import (drehfraes.py) ist ein Zukaufteil. Solange kein Lieferantenpreis da ist,
schätzt dieses Modul den Preis, den ein Lohnfertiger verlangen würde, aus der Geometrie der Messung (Spalte
'drehfraes', Kennwerte aus step_drehfraes): je Teil eine Liste von Arbeitsgängen mit Zeiten aus Schnittwerten,
dazu Rohmaterial, Rüsten/Programmieren verteilt auf die Stückzahl, Zusätze in €/Stück und der Aufschlag des
Lieferanten. Das Ergebnis ist ein EK-Vorschlag mit Hinweis „Richtpreis (Schätzung), Fremdangebot einholen“; ein
EK von Hand oder vom Lieferanten geht immer vor. Auf den EK kommt im Angebot wie bei allen Zukaufteilen nur der
Aufschlag der Zukaufregel, kein Gewinn.

Schnittwerte (Vorgaben, in den Einstellungen änderbar; Quellen siehe SCHNITTWERTE_QUELLEN): Hartmetall, Stand der
Technik, mit einem Nutzungsgrad (Anfahren, wechselnde Schnitttiefe), damit die Zeiten nicht zu knapp werden.

Rechenweg je Stück (Zeiten in Minuten):
- Drehen: Rohling Rundstahl (Lager-Ø ≥ Ø max + Aufmaß), bis 'df_stange_bis' von der Stange (Abstechen), sonst gesägt
  (Sägen, zweite Aufspannung). Schruppen = Spanvolumen ÷ (vc·f·ap·Nutzungsgrad); Schlichten = gedrehte Fläche ÷
  (vc·f·10); Bohren innen (bis 'df_bohr_max', Rest Ausdrehen); Einstechen je Einstich; Werkzeugwechsel je Werkzeug;
  Querbohrungen und Schlüsselflächen mit angetriebenen Werkzeugen bzw. als eigener Fräsgang; Handhabung.
- Fräsen: Rohling Flachstahl (Lagermaß ≥ Hüllmaß + Aufmaß je Seite), gesägt. Planfräsen = Aufmaß-Volumen ÷
  (Planleistung), Schruppen = Taschen/Kontur-Volumen ÷ (ae·ap·vf·Nutzungsgrad), Schlichten = Kontur-Fläche ÷
  (vf·ae), Bohren je Bohrung (Ø, Tiefe aus der Messung), Fasen/Senkungen, Aufspannungen, Werkzeugwechsel.
- Rüsten + Programmieren je Auftrag und Verfahren, geteilt durch die Stückzahl.
- Gewinde, Oberfläche, Härten u. ä. erkennt die Messung nicht sicher: als €/Stück (Regel Patrick: Gewinde, Senken,
  Bohren nur €/Stück), mit Hinweis, wenn die Messung „Gewinde/Freiform“ meldet.
Jede Zeit eines Arbeitsgangs lässt sich im Dialog von Hand überschreiben (eingaben['zeiten']).
"""
import json
import math
import re

from . import drehfraes

QUELLE = "Dreh-/Frästeil-Richtpreis"
HINWEIS = "Richtpreis (Schätzung), Fremdangebot einholen"
DREHEN, FRAESEN, SAEGEN = "Drehen", "Fräsen", "Sägen"
ROHLING_VOLL, ROHLING_ROHR = "Rundstahl", "Rohr (Hohlstahl)"
ROHLINGE = (ROHLING_VOLL, ROHLING_ROHR)

SCHNITTWERTE_QUELLEN = (
    "dswerk.de „Schnittwerte wählen“ (vc/f/ap Drehen, vc/fz Fräsen, Hartmetall, Schruppen)",
    "cncrechner.de „Schnittdaten Edelstahl“ (1.4301/1.4404/1.4571 Drehen, Schruppen/Schlichten)",
    "Horn „Bohren/Reiben Schnittdaten“ (VHM-Bohrer vc und f je Ø, Vorschubreihen A–E)",
    "Wolff Maschinen „Schnittdaten Bi-Metall-Bandsägen“ (Zerspanleistung cm²/min, Baustahl Ø50: 43–54)",
    "Sorotec „Schnittwerte“ (vc/fz Alu, Messing, Kunststoff)",
    "clean-invoice.com Preisleitfaden Feinwerkmechanik 2026 (Stundensätze Drehen 60–120 €/h, Fräsen 3-Achs "
    "70–120 €/h)",
)

# Schnittwerte je Werkstoffgruppe (Einstellung df_schnittwerte, eine Zeile je Gruppe, Spalten wie SPALTEN).
SPALTEN = ("gruppe", "dichte", "eur_kg", "dreh_vc", "dreh_f", "dreh_ap", "schlicht_vc", "schlicht_f", "fraes_vc",
           "fraes_fz", "fraes_schlicht_fz", "bohr_vc", "bohr_reihe", "saege", "erkennung")
SPALTEN_TITEL = ("Gruppe", "Dichte kg/dm³", "€/kg", "Drehen vc", "f mm/U", "ap mm", "Schlichten vc", "f mm/U",
                 "Fräsen vc", "fz mm", "Schlichten fz", "Bohren vc", "Vorschubreihe", "Sägen cm²/min",
                 "Erkennung (Teil des Werkstoffnamens)")
SCHNITTWERTE_VORGABE = """\
# Gruppe; Dichte; €/kg; Drehen vc; f; ap; Schlichten vc; f; Fräsen vc; fz; Schlichten fz; Bohren vc; Reihe; Sägen cm²/min; Erkennung
Edelstahl; 7,9; 5,00; 140; 0,20; 2,0; 180; 0,10; 90; 0,045; 0,03; 60; D; 20; 1.43,1.44,1.45,1.40,1.41,V2A,V4A,Edelstahl,Niro,X5Cr,X2Cr,X6Cr,AISI
Aluminium; 2,7; 5,50; 600; 0,30; 3,0; 700; 0,12; 450; 0,12; 0,08; 250; C; 150; Al,EN AW,3.3,3.4,Alu
Messing; 8,5; 9,50; 300; 0,25; 2,5; 350; 0,10; 300; 0,08; 0,05; 150; C; 100; CuZn,Messing,2.0,Ms58,Bronze,CuSn,Kupfer,CW0,CW1,CW4,CW5,CW6,CW7
Kunststoff; 1,4; 10,00; 400; 0,30; 3,0; 500; 0,15; 500; 0,10; 0,06; 150; C; 200; POM,PA6,PE,PVC,PTFE,PEEK,Kunststoff
Vergütungsstahl; 7,85; 2,20; 130; 0,20; 1,5; 160; 0,10; 110; 0,06; 0,04; 70; B; 35; C45,42Cr,34Cr,16Mn,20Mn,1.0503,1.7225,11SMn,Automat
Stahl; 7,85; 1,60; 220; 0,30; 2,5; 260; 0,12; 200; 0,09; 0,05; 90; A; 45; *
"""

# VHM-Bohrer: Vorschub f [mm/U] je Ø (Horn, Reihen A–E), dazwischen linear
BOHR_DM = (4, 6, 8, 10, 12, 16, 20)
BOHR_REIHEN = {"A": (0.10, 0.15, 0.20, 0.25, 0.30, 0.36, 0.40), "B": (0.09, 0.14, 0.18, 0.22, 0.26, 0.30, 0.35),
               "C": (0.12, 0.18, 0.24, 0.30, 0.35, 0.40, 0.50), "D": (0.08, 0.12, 0.16, 0.20, 0.24, 0.28, 0.30),
               "E": (0.08, 0.10, 0.12, 0.14, 0.16, 0.20, 0.28)}

# Lagermaße: Rundstahl Ø, Flachstahl Breite und Dicke [mm]; größer: auf 5 bzw. 10 mm aufgerundet (Zuschnitt)
RUND_LAGER = (6, 8, 10, 12, 14, 15, 16, 18, 20, 22, 25, 28, 30, 32, 35, 38, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85,
              90, 95, 100, 110, 120, 130, 140, 150, 160, 170, 180, 200, 220, 250, 280, 300)
FLACH_LAGER = (10, 12, 15, 16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 180, 200,
               220, 250, 300)

EINSTELLUNGEN = {
    "df_stundensatz_drehen": 85.0, "df_stundensatz_fraesen": 95.0,
    "df_ruesten_drehen": 45.0, "df_ruesten_fraesen": 60.0,
    "df_programm_drehen": 20.0, "df_programm_fraesen": 30.0, "df_programm_element": 2.0,
    "df_aufmass_d": 2.0, "df_aufmass_l": 2.0, "df_aufmass_fraes": 1.5,
    "df_stange_bis": 65.0, "df_abstich": 3.0, "df_bohr_max": 32.0, "df_nutzung": 0.6,
    "df_werkzeugwechsel": 0.15, "df_handhabung": 0.5, "df_entgraten": 0.3, "df_einstich": 0.25, "df_fase": 0.05,
    "df_aufspannen_fraesen": 1.0, "df_ruesten_aufspannung": 15.0, "df_fraeser": 16.0,
    "df_angetrieben": "ja", "df_verschnitt": 0.05, "df_aufschlag": 0.15, "df_mindestzeit": 0.5,
    "df_schnittwerte": SCHNITTWERTE_VORGABE,
    # Machbarkeit (Patrick 03.11.2026): Grenzen der Maschinen und Werkzeuge
    "df_max_d": 320.0, "df_max_l": 1000.0, "df_fraes_x": 1000.0, "df_fraes_y": 500.0, "df_fraes_z": 500.0,
    "df_bohr_gelb": 5.0, "df_bohr_rot": 10.0, "df_schlank_gelb": 4.0, "df_schlank_rot": 12.0,
    "df_tasche_gelb": 4.0, "df_tasche_rot": 8.0, "df_wand_min": 1.0, "df_radius_min": 0.5,
}
GRUEN, GELB, ROT = "grün", "gelb", "rot"
AMPEL_TEXT = {GRUEN: "machbar", GELB: "machbar mit Mehraufwand", ROT: "so nicht machbar bzw. Sonderverfahren"}


def machbarkeit(d, w, roh=None):
    """Machbarkeitsprüfung aus den Kennwerten der Messung: Liste dict(stufe gelb|rot, text, gang, faktor) – gelb mit
    Zeitzuschlag (faktor auf die Arbeitsgänge, deren Name mit gang beginnt), rot = so nicht machbar bzw.
    Sonderverfahren (Tieflochbohren, Erodieren, größere Maschine). Leer = grün."""
    w = einstellungen(w) if not isinstance(w, dict) or "df_max_d" not in w else w
    k = _kennwerte(d)
    out = []

    def neu(stufe, text, gang=None, faktor=1.0):
        out.append(dict(stufe=stufe, text=text, gang=gang, faktor=faktor))
    art = d.get("art")
    bohr = list(k.get("bohrungen") or ()) + list(k.get("querbohrungen") or ())
    if art == drehfraes.DREHTEIL:
        bohr += [dict(a, innen=True) for a in k.get("innen") or ()][:1]
    for b in bohr:
        dm, tiefe = _z(b.get("d")), _z(b.get("l"))
        if dm <= 0 or tiefe <= 0 or (b.get("innen") and dm > w["df_bohr_max"]):
            continue
        v = tiefe / dm
        if v > w["df_bohr_rot"]:
            neu(ROT, f"Bohrung Ø{_fmm(dm)} × {_fmm(tiefe)} mm ist {_fmm(v)} × Ø tief (über {_fmm(w['df_bohr_rot'])} × Ø:"
                f" Tieflochbohren)", "Bohren", 2.0)
        elif v > w["df_bohr_gelb"]:
            neu(GELB, f"Bohrung Ø{_fmm(dm)} × {_fmm(tiefe)} mm ist {_fmm(v)} × Ø tief (Entspanen, +50 % Bohrzeit)",
                "Bohren", 1.5)
    if art == drehfraes.DREHTEIL:
        da, lg = _z(d.get("durchmesser")), _z(d.get("laenge"))
        v = lg / da if da > 0 else 0            # Schlankheit wie beim Spannen: Länge zum größten Ø
        if v > w["df_schlank_rot"]:
            neu(ROT, f"sehr schlank: Länge {_fmm(lg)} mm = {_fmm(v)} × Ø {_fmm(da)} (Lünette bzw. "
                "Langdrehautomat)", "Drehen", 1.6)
        elif v > w["df_schlank_gelb"]:
            neu(GELB, f"schlank: Länge = {_fmm(v)} × Ø {_fmm(da)} (Reitstock, kleinere Schnittwerte, "
                "+30 % Drehzeit)", "Drehen", 1.3)
        wand = k.get("wand_min")
        if wand is not None and wand < w["df_wand_min"]:
            neu(ROT, f"Wand nur {_fmm(wand)} mm (unter {_fmm(w['df_wand_min'])} mm: verzieht sich beim Spannen)")
        elif wand is not None and wand < 2 * w["df_wand_min"]:
            neu(GELB, f"dünne Wand {_fmm(wand)} mm (vorsichtig spannen, +20 % Schlichtzeit)", "Drehen schlichten",
                1.2)
        if da > w["df_max_d"] or lg > w["df_max_l"]:
            neu(ROT, f"größer als die Drehmaschine (Ø {_fmm(da)} / Länge {_fmm(lg)} mm, Grenze Ø "
                f"{_fmm(w['df_max_d'])} / {_fmm(w['df_max_l'])} mm)")
    else:
        fr = w["df_fraeser"]
        rmin = k.get("innenradius_min")
        if rmin is not None and rmin < w["df_radius_min"]:
            neu(ROT, f"Innenradius {_fmm(rmin)} mm (unter {_fmm(w['df_radius_min'])} mm: scharfe Innenecke nur durch "
                "Erodieren)")
        elif rmin is not None and rmin < fr / 2 - 0.01:
            neu(GELB, f"Innenradius {_fmm(rmin)} mm kleiner als der Fräser Ø{_fmm(fr)} (kleiner Fräser, +30 % "
                "Schlichtzeit)", "Fräsen schlichten", 1.3)
        tt = _z(k.get("taschentiefe"))
        dm_wz = max(2 * rmin, 1.0) if rmin is not None and rmin < fr / 2 else fr
        if tt > w["df_tasche_rot"] * dm_wz:
            neu(ROT, f"Tasche/Absatz {_fmm(tt)} mm tief = über {_fmm(w['df_tasche_rot'])} × Fräser-Ø {_fmm(dm_wz)}"
                " (Sonderwerkzeug bzw. Erodieren)", "Fräsen schruppen", 1.8)
        elif tt > w["df_tasche_gelb"] * dm_wz:
            neu(GELB, f"tiefe Tasche {_fmm(tt)} mm = über {_fmm(w['df_tasche_gelb'])} × Fräser-Ø {_fmm(dm_wz)} "
                "(langer Fräser, +30 % Schruppzeit)", "Fräsen schruppen", 1.3)
        masse = sorted((_z(d.get("laenge")), _z(d.get("breite")), _z(d.get("hoehe"))), reverse=True)
        grenze = sorted((w["df_fraes_x"], w["df_fraes_y"], w["df_fraes_z"]), reverse=True)
        if any(m > g for m, g in zip(masse, grenze)):
            neu(ROT, "größer als der Verfahrweg der Fräsmaschine ("
                + " × ".join(_fmm(x) for x in grenze) + " mm)")
    return out


def ampel(liste):
    """Gesamtstufe der Machbarkeit: rot vor gelb vor grün."""
    stufen = {x["stufe"] for x in liste}
    return ROT if ROT in stufen else GELB if GELB in stufen else GRUEN


def _z(x, vorgabe=0.0):
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).strip().replace(",", "."))
    except (TypeError, ValueError, AttributeError):
        return vorgabe


def schnittwerte(text=None):
    """Zeilen der Schnittwert-Tabelle (Einstellung df_schnittwerte) als Liste von dicts; ungültige Zeilen fehlen.
    Ohne Zeile 'Stahl' kommt die Vorgabe dazu (Rückfall für unbekannte Werkstoffe)."""
    out = []
    for zeile in str(text if text is not None else SCHNITTWERTE_VORGABE).splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue
        teile = [t.strip() for t in zeile.split(";")]
        if len(teile) < len(SPALTEN) - 1:
            continue
        teile += [""] * (len(SPALTEN) - len(teile))
        z = dict(zip(SPALTEN, teile))
        for n in SPALTEN:
            if n not in ("gruppe", "bohr_reihe", "erkennung"):
                z[n] = _z(z[n])
        z["bohr_reihe"] = (z["bohr_reihe"] or "A").upper()[:1]
        if z["bohr_reihe"] not in BOHR_REIHEN:
            z["bohr_reihe"] = "A"
        z["erkennung"] = [b.strip() for b in z["erkennung"].split(",") if b.strip()]
        if z["gruppe"] and z["dichte"] > 0 and z["dreh_vc"] > 0 and z["fraes_vc"] > 0:
            out.append(z)
    if not any(z["gruppe"] == "Stahl" for z in out) and text is not None:
        out += [z for z in schnittwerte(None) if z["gruppe"] == "Stahl"]
    return out


def gruppe(werkstoff, tabelle):
    """Werkstoffgruppe zum Werkstoffnamen: erste Zeile, deren Erkennungsbegriff im Namen vorkommt (Groß-/Klein egal;
    kurze Begriffe wie 'Al' nur als eigenes Wort bzw. am Anfang); '*' bzw. 'Stahl' ist der Rückfall."""
    name = str(werkstoff or "")
    low = name.lower()
    rueck = None
    for z in tabelle:
        for b in z["erkennung"]:
            if b == "*":
                rueck = rueck or z
                continue
            bl = b.lower()
            if len(bl) <= 3 and not bl[0].isdigit():
                # kurz (Al, PE …): als eigenes Wort bzw. vor einem Großbuchstaben (AlMgSi1), nicht mitten im Wort
                if re.search(r"(^|[^A-Za-z])" + re.escape(b) + r"(?![a-z])", name) or \
                        re.search(r"(^|[^a-z])" + re.escape(bl) + r"([^a-z]|$)", low):
                    return z
            elif bl in low:
                return z
    return rueck or next((z for z in tabelle if z["gruppe"] == "Stahl"), tabelle[-1] if tabelle else None)


def lagermass(x, liste, schritt):
    """Kleinstes Lagermaß ≥ x, darüber auf schritt aufgerundet."""
    for m in liste:
        if m >= x - 1e-6:
            return float(m)
    return float(math.ceil(x / schritt) * schritt)


def bohr_f(d, reihe):
    """Vorschub [mm/U] eines VHM-Bohrers mit Ø d aus der Vorschubreihe (linear, außerhalb gekappt)."""
    werte = BOHR_REIHEN.get(reihe) or BOHR_REIHEN["A"]
    if d <= BOHR_DM[0]:
        return werte[0] * max(d, 1) / BOHR_DM[0]
    for i in range(1, len(BOHR_DM)):
        if d <= BOHR_DM[i]:
            t = (d - BOHR_DM[i - 1]) / (BOHR_DM[i] - BOHR_DM[i - 1])
            return werte[i - 1] + t * (werte[i] - werte[i - 1])
    return werte[-1]


def bohrzeit(d, tiefe, sw):
    """Bohrzeit [min] für eine Bohrung Ø d, Tiefe [mm]: (Tiefe + Spitze 0,3·d + 2 mm Anlauf) ÷ (f·n)."""
    if d <= 0 or tiefe <= 0:
        return 0.0
    n = sw["bohr_vc"] * 1000 / (math.pi * d)
    vf = bohr_f(d, sw["bohr_reihe"]) * n
    return (tiefe + 0.3 * d + 2) / vf if vf > 0 else 0.0


def _gang(liste, name, verfahren, minuten, info=""):
    liste.append(dict(name=name, verfahren=verfahren, minuten=max(0.0, minuten), info=info))


def _fmm(x):
    return f"{x:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def _fmin(x):
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _stab(sw, rund):
    """Name des Stangenmaterials: Rund-/Flachstahl bei Stahl, sonst Rund-/Flachmaterial (Alu, Messing, Kunststoff)."""
    stahl = "stahl" in str(sw.get("gruppe") or "Stahl").lower()
    return ("Rund" if rund else "Flach") + ("stahl" if stahl else "material")


def _bohrliste(liste):
    """Bohrungen als Text, gleiche zusammengefasst: „6× Ø9 × 15, Ø6 × 24“."""
    anz = {}
    for a in liste:
        k = f"Ø{_fmm(_z(a['d']))} × {_fmm(_z(a['l']))}"
        anz[k] = anz.get(k, 0) + 1
    return ", ".join((f"{n}× " if n > 1 else "") + k for k, n in anz.items())


def _kennwerte(d):
    k = d.get("kennwerte")
    return k if isinstance(k, dict) else {}


def _drehen(d, sw, w, rohling_art, gaenge, hinweise):
    """Arbeitsgänge und Rohling eines Drehteils. Ergebnis: Rohling-dict."""
    k = _kennwerte(d)
    da, di, lg = _z(d.get("durchmesser")), _z(d.get("innen")), _z(d.get("laenge"))
    v_fertig = _z(d.get("volumen")) or (math.pi / 4 * (da ** 2 - di ** 2) * lg)
    # Lasche/Anbau außerhalb des Drehdurchmessers: Rohling über den Anbau, der Rest wird gefräst (Dreh-Fräs-Teil)
    d_roh = lagermass(max(da, _z(k.get("anbau_d"))) + w["df_aufmass_d"], RUND_LAGER, 10)
    stange = d_roh <= w["df_stange_bis"]
    l_bearb = lg + w["df_aufmass_l"] * (1 if stange else 2)         # gesägt: an beiden Enden plandrehen
    l_roh = l_bearb + (w["df_abstich"] if stange else 2.0)          # Abstich bzw. Sägeschnitt
    di_roh = 0.0
    if rohling_art == ROHLING_ROHR and di >= 30:
        di_roh = max(0.0, math.floor((di - w["df_aufmass_d"]) / 5) * 5)
    elif rohling_art == ROHLING_ROHR:
        hinweise.append("Rohr als Rohling erst ab Innen-Ø 30 mm: Rundstahl gerechnet")
    v_roh = math.pi / 4 * (d_roh ** 2 - di_roh ** 2) * l_bearb
    gew = math.pi / 4 * (d_roh ** 2 - di_roh ** 2) * l_roh * sw["dichte"] / 1e6
    werkzeuge = 2                                   # Schruppen außen, Schlichten außen
    # Sägen (ab Stange: Abstechen am Ende)
    if not stange:
        flaeche = math.pi / 4 * (d_roh ** 2 - di_roh ** 2) / 100
        _gang(gaenge, "Sägen Rohling", SAEGEN, flaeche / sw["saege"] + 0.3 if sw["saege"] > 0 else 0.3,
              f"Ø{_fmm(d_roh)}, {_fmm(flaeche)} cm² bei {_fmm(sw['saege'])} cm²/min + 0,3 min Handhabung")
    # Bohren innen
    v_bohr = 0.0
    innen = [a for a in k.get("innen") or () if _z(a.get("d")) > 0] or (
        [dict(d=di, l=lg)] if di > 0 else [])
    if innen and di_roh <= 0:
        db = min(min(_z(a["d"]) for a in innen), w["df_bohr_max"])
        tiefe = max(_z(a["l"]) for a in innen)
        if not any("Sackbohrung" in m for m in d.get("merkmale") or ()):
            tiefe = max(tiefe, lg)              # Durchgangsbohrung
        t = bohrzeit(db, tiefe + w["df_aufmass_l"], sw)
        v_bohr = math.pi / 4 * db ** 2 * tiefe
        werkzeuge += 1
        _gang(gaenge, f"Bohren innen Ø{_fmm(db)}", DREHEN, t,
              f"Tiefe {_fmm(tiefe)} mm, vc {_fmm(sw['bohr_vc'])} m/min, f {bohr_f(db, sw['bohr_reihe']):.2f} mm/U"
              .replace(".", ","))
        if max(_z(a["d"]) for a in innen) > db + 0.5 or len(innen) > 1:
            werkzeuge += 1                          # Innen-Ausdrehen (Volumen im Schruppen)
    # Schruppen (außen und innen)
    v_span = max(0.0, v_roh - v_fertig - v_bohr)
    q = sw["dreh_vc"] * sw["dreh_f"] * sw["dreh_ap"] * w["df_nutzung"]          # cm³/min
    _gang(gaenge, "Drehen schruppen", DREHEN, (v_span / 1000) / q if q > 0 else 0.0,
          f"Spanvolumen {_fmm(v_span / 1000)} cm³ bei {_fmm(q)} cm³/min (vc {_fmm(sw['dreh_vc'])}, "
          f"f {_fmm(sw['dreh_f'])}, ap {_fmm(sw['dreh_ap'])}, Nutzung {_fmm(w['df_nutzung'] * 100)} %)")
    # Schlichten: gedrehte Fläche (Mantel, Stirn, Fasen, Radien) – ohne Messung: Mantel + Stirnflächen geschätzt
    a_dreh = _z(k.get("dreh_flaeche")) + _z(k.get("stirn_flaeche"))
    if a_dreh <= 0:
        a_dreh = (math.pi * da * lg + math.pi / 2 * da ** 2 + (math.pi * di * lg if di else 0)) / 100
    rate = sw["schlicht_vc"] * sw["schlicht_f"] * 10                           # cm²/min
    _gang(gaenge, "Drehen schlichten", DREHEN, a_dreh / rate if rate > 0 else 0.0,
          f"Fläche {_fmm(a_dreh)} cm² bei {_fmm(rate)} cm²/min (vc {_fmm(sw['schlicht_vc'])}, "
          f"f {_fmm(sw['schlicht_f'])})")
    # Einstiche, Fasen/Radien/Konturen
    n_einst = int(_z(k.get("einstiche")))
    if n_einst:
        werkzeuge += 1
        _gang(gaenge, f"Einstechen ({n_einst}×)", DREHEN, n_einst * w["df_einstich"],
              f"{_fmin(w['df_einstich'])} min je Einstich")
    n_kont = int(_z(k.get("fasen")) + _z(k.get("radien")) + _z(k.get("konturen")))
    n_abs = max(0, len(k.get("aussen") or ()) - 1) + max(0, len(k.get("innen") or ()) - 1)
    if n_kont or n_abs:
        _gang(gaenge, f"Absätze/Fasen/Radien ({n_abs + n_kont}×)", DREHEN, (n_abs + n_kont) * w["df_fase"],
              f"{_fmin(w['df_fase'])} min je Konturelement (Anfahren)")
    # Abstechen bzw. zweite Aufspannung
    if stange:
        n = sw["dreh_vc"] * 1000 / (math.pi * d_roh)
        t = (d_roh / 2) / (0.08 * n) + 0.1 if n > 0 else 0.1
        werkzeuge += 1
        _gang(gaenge, "Abstechen", DREHEN, t, f"Ø{_fmm(d_roh)}, f 0,08 mm/U")
    else:
        _gang(gaenge, "Umspannen 2. Seite", DREHEN, w["df_handhabung"], "gesägter Rohling: beide Seiten plandrehen")
    # Querbohrungen, Schlüsselflächen
    quer = [a for a in k.get("querbohrungen") or () if _z(a.get("d")) > 0]
    zus = d.get("zusatz") or ()
    if not quer and "Querbohrung" in zus:
        quer = [dict(d=min(10.0, da / 3), l=da)]
        hinweise.append("Querbohrung ohne Maße: Ø10 × Ø max angenommen")
    schl_a = _z(k.get("schluessel_flaeche"))
    if not schl_a and "Schlüsselfläche/Abflachung" in zus:
        schl_a = da * da * 0.5 / 100
    angetrieben = str(w.get("df_angetrieben") or "ja").lower().startswith("j")
    verf_zus = DREHEN if angetrieben else FRAESEN
    if quer:
        t = sum(bohrzeit(_z(a["d"]), _z(a["l"]), sw) + 0.1 for a in quer)
        werkzeuge += len({round(_z(a["d"]), 1) for a in quer})
        n_ax = sum(1 for a in quer if a.get("axial"))
        name = ("Bohrungen axial/Lochkreis" if n_ax == len(quer) else "Querbohrungen" if not n_ax
                else "Quer- und Lochkreisbohrungen")
        _gang(gaenge, f"{name} ({len(quer)}×)", verf_zus, t,
              _bohrliste(quer) + ("" if angetrieben else "; eigener Fräsgang (keine angetriebenen Werkzeuge)"))
    if schl_a:
        fr = w["df_fraeser"]
        n = sw["fraes_vc"] * 1000 / (math.pi * fr)
        vf = sw["fraes_fz"] * 4 * n
        rate_f = vf * fr * 0.6 / 100                                           # cm²/min (Schlichtbahn)
        v = schl_a * 0.2                                                        # 2 mm tief angenommen
        qf = 0.4 * fr * fr * vf * w["df_nutzung"] / 1000
        t = (v / qf if qf > 0 else 0) + (schl_a / rate_f if rate_f > 0 else 0) + 0.2
        werkzeuge += 1
        _gang(gaenge, "Schlüsselfläche/Abflachung fräsen", verf_zus, t,
              f"Fläche {_fmm(schl_a)} cm², 2 mm tief angenommen")
    if quer or schl_a:
        if not angetrieben:
            _gang(gaenge, "Aufspannen Fräsen", FRAESEN, w["df_aufspannen_fraesen"], "")
    _gang(gaenge, f"Werkzeugwechsel ({werkzeuge}×)", DREHEN, werkzeuge * w["df_werkzeugwechsel"], "")
    _gang(gaenge, "Handhabung, Messen", DREHEN, w["df_handhabung"] * (0.5 if stange else 1.0),
          "Stangenlader" if stange else "Ein-/Ausspannen")
    _gang(gaenge, "Entgraten", DREHEN, w["df_entgraten"], "")
    elemente = 2 + n_einst + n_kont + n_abs + len(quer) + bool(schl_a)
    return dict(art=ROHLING_ROHR if di_roh else ROHLING_VOLL, d=d_roh, innen=di_roh, laenge=l_roh,
                gewicht=gew, text=f"{'Rohr' if di_roh else _stab(sw, True)} Ø{_fmm(d_roh)}"
                + (f"/Ø{_fmm(di_roh)}" if di_roh else "") + f" × {_fmm(l_roh)} mm"
                + (" (von der Stange)" if stange else " (gesägt)"), elemente=elemente,
                zweiter=FRAESEN if (quer or schl_a) and not angetrieben else None)


def _fraesen(d, sw, w, gaenge, hinweise):
    """Arbeitsgänge und Rohling eines Frästeils. Ergebnis: Rohling-dict."""
    k = _kennwerte(d)
    la, lb, lc = _z(d.get("laenge")), _z(d.get("breite")), _z(d.get("hoehe"))
    v_fertig = _z(d.get("volumen")) or la * lb * lc * 0.8
    a = w["df_aufmass_fraes"]
    b_roh = lagermass(lb + 2 * a, FLACH_LAGER, 10)
    h_roh = lagermass(lc + 2 * a, FLACH_LAGER, 5)
    l_roh = la + 2 * a
    v_huell = la * lb * lc
    v_roh = b_roh * h_roh * l_roh
    gew = v_roh * sw["dichte"] / 1e6
    fr = w["df_fraeser"]
    n = sw["fraes_vc"] * 1000 / (math.pi * fr)
    vf = sw["fraes_fz"] * 4 * n                                     # mm/min, 4 Schneiden
    vf_s = sw["fraes_schlicht_fz"] * 4 * n * 1.2
    werkzeuge = 3                                                   # Planfräser, Schruppen, Schlichten
    flaeche = b_roh * h_roh / 100
    _gang(gaenge, "Sägen Rohling", SAEGEN, flaeche / sw["saege"] + 0.3 if sw["saege"] > 0 else 0.3,
          f"Flach {_fmm(b_roh)} × {_fmm(h_roh)}, {_fmm(flaeche)} cm² bei {_fmm(sw['saege'])} cm²/min")
    # Planfräsen (Aufmaß aller Seiten): Planfräser Ø 3 × Fräser, ae 0,7·D, ap 1,5 mm
    v_plan = max(0.0, v_roh - v_huell)
    d_plan = 3 * fr
    n_p = sw["fraes_vc"] * 1000 / (math.pi * d_plan)
    q_plan = 0.7 * d_plan * min(3.0, a + 0.5) * sw["fraes_fz"] * 6 * n_p * w["df_nutzung"] / 1000
    _gang(gaenge, "Planfräsen (Aufmaß)", FRAESEN, (v_plan / 1000) / q_plan if q_plan > 0 else 0.0,
          f"{_fmm(v_plan / 1000)} cm³ bei {_fmm(q_plan)} cm³/min (Planfräser Ø{_fmm(d_plan)})")
    # Schruppen Taschen/Kontur
    bohr = [x for x in k.get("bohrungen") or () if _z(x.get("d")) > 0]
    v_bohr = sum(math.pi / 4 * _z(x["d"]) ** 2 * _z(x["l"]) for x in bohr)
    v_kontur = max(0.0, v_huell - v_fertig - v_bohr)
    q = 0.4 * fr * fr * vf * w["df_nutzung"] / 1000                # ae 0,4·D, ap 1·D
    _gang(gaenge, "Fräsen schruppen (Taschen/Kontur)", FRAESEN, (v_kontur / 1000) / q if q > 0 else 0.0,
          f"{_fmm(v_kontur / 1000)} cm³ bei {_fmm(q)} cm³/min (Fräser Ø{_fmm(fr)}, vc {_fmm(sw['fraes_vc'])}, "
          f"fz {_fmm(sw['fraes_fz'])})")
    # Schlichten: Konturfläche ohne Bohrungen
    a_k = _z(k.get("kontur_flaeche")) or 2 * (la * lb + la * lc + lb * lc) / 100
    rate = vf_s * 0.6 * fr / 100                                    # cm²/min
    _gang(gaenge, "Fräsen schlichten", FRAESEN, a_k / rate if rate > 0 else 0.0,
          f"Fläche {_fmm(a_k)} cm² bei {_fmm(rate)} cm²/min")
    # Bohrungen
    if not bohr and "Bohrungen" in (d.get("zusatz") or ()):
        hinweise.append("Bohrungen ohne Maße: bitte im Dialog prüfen")
    if bohr:
        t = sum(bohrzeit(_z(x["d"]), _z(x["l"]), sw) + 0.15 for x in bohr)     # + Zentrieren/Positionieren
        werkzeuge += 1 + len({round(_z(x["d"]), 1) for x in bohr})
        _gang(gaenge, f"Bohren ({len(bohr)}×)", FRAESEN, t,
              _bohrliste(bohr) + "; mit Zentrieren")
    n_fase = int(_z(k.get("fasen")))
    n_rad = int(_z(k.get("radien")) + _z(k.get("innenradien")))
    if n_fase:
        werkzeuge += 1
        _gang(gaenge, f"Fasen/Senkungen ({n_fase}×)", FRAESEN, n_fase * 2 * w["df_fase"], "")
    if n_rad:
        _gang(gaenge, f"Radien/Ecken ({n_rad}×)", FRAESEN, n_rad * w["df_fase"], "")
    aufsp = 2 + (1 if _z(k.get("richtungen")) > 3 else 0)
    _gang(gaenge, f"Aufspannen ({aufsp}×)", FRAESEN, aufsp * w["df_aufspannen_fraesen"], "Ein-/Ausspannen, Ausrichten")
    _gang(gaenge, f"Werkzeugwechsel ({werkzeuge}×)", FRAESEN, werkzeuge * w["df_werkzeugwechsel"] * aufsp / 2, "")
    _gang(gaenge, "Entgraten, Messen", FRAESEN, w["df_entgraten"] + w["df_handhabung"], "")
    elemente = 3 + len(bohr) + n_fase + int(_z(k.get("stufen")))
    return dict(art="Flachstahl", breite=b_roh, hoehe=h_roh, laenge=l_roh, gewicht=gew,
                text=f"{_stab(sw, False)} {_fmm(b_roh)} × {_fmm(h_roh)} × {_fmm(l_roh)} mm (gesägt)", elemente=elemente,
                aufspannungen=aufsp, zweiter=None)


def _norm(x):
    return re.sub(r"[^0-9a-z]", "", str(x or "").lower())


def werkstoff_zeile(name, werkstoffe):
    """Zeile der Tabelle Dreh-/Fräs-Werkstoffe zum Werkstoffnamen oder None: gleicher Name, sonst gleiche
    Bezeichnung, sonst der längste gemeinsame Anfang ab 4 Zeichen (S235-10219 → S235JR, 1.4301 2B → 1.4301)."""
    n = _norm(name)
    if not n or not werkstoffe:
        return None
    zeilen = list(werkstoffe.values()) if isinstance(werkstoffe, dict) else list(werkstoffe)
    for z in zeilen:
        if _norm(z.get("drehfraes_werkstoff_id")) == n or _norm(z.get("bezeichnung")) == n:
            return z
    best, laenge = None, 0
    for z in zeilen:
        for k in (_norm(z.get("drehfraes_werkstoff_id")), _norm(z.get("bezeichnung"))):
            i = 0
            while i < min(len(k), len(n)) and k[i] == n[i]:
                i += 1
            ganz = i == len(k) and i >= 3                   # ganze ID am Anfang (C45 in C45E, 1.4301 in 1.4301 2B)
            zahl_offen = k[i:i + 1].isdigit() and n[i:i + 1].isdigit()     # 1.4301 ≠ 1.4305
            if i > laenge and (ganz or (i >= 4 and not zahl_offen)):
                best, laenge = z, i
    return best


ZERSPAN_SPALTEN = ("dreh_vc", "schlicht_vc", "fraes_vc", "bohr_vc")


def werkstoff_schnittwerte(werkstoff, w):
    """Schnittwerte zum Werkstoff (dict wie eine Zeile der Schnittwerte) und die Zeile der Tabelle Dreh-/Fräs-
    Werkstoffe (oder None): aus der Tabelle Gruppe, Dichte, €/kg und Zerspanbarkeit (vc × %/100), sonst die
    Gruppe nach Erkennungsbegriff. w = einstellungen(…)."""
    tab = schnittwerte(w.get("df_schnittwerte"))
    zeile = werkstoff_zeile(werkstoff, w.get("werkstoffe"))
    sw = gruppe(werkstoff, tab)
    if zeile is None or sw is None:
        return sw, None
    sw = dict(next((z for z in tab if z["gruppe"] == zeile.get("gruppe")), sw))
    if _z(zeile.get("dichte")) > 0:
        sw["dichte"] = _z(zeile.get("dichte"))
    if _z(zeile.get("preis_kg")) > 0:
        sw["eur_kg"] = _z(zeile.get("preis_kg"))
    f = _z(zeile.get("zerspanbarkeit"), 100.0) / 100 or 1.0
    for n in ZERSPAN_SPALTEN:
        sw[n] = sw[n] * f
    return sw, zeile


def einstellungen(werte=None):
    """Einstellungen mit Vorgaben ergänzt (Zahlen als float); 'werkstoffe' = Tabelle Dreh-/Fräs-Werkstoffe
    {ID: Zeile} (datenbank.drehfraes_einstellungen) bleibt erhalten."""
    w = dict(EINSTELLUNGEN)
    for n, v in (werte or {}).items():
        if n in EINSTELLUNGEN and v is not None and v != "":
            w[n] = v
    if isinstance((werte or {}).get("werkstoffe"), (dict, list)):
        w["werkstoffe"] = werte["werkstoffe"]
    for n, v in EINSTELLUNGEN.items():
        if isinstance(v, float):
            w[n] = _z(w[n], v)
    return w


def rechnen(e, einst=None):
    """Richtpreis eines Dreh-/Frästeils. e = Eingaben (daten: Messung 'drehfraes', werkstoff, stueck, rohling,
    zeiten {Arbeitsgang: Minuten von Hand}, zusatz_eur, zusatz_text, eur_kg von Hand). Ergebnis: dict(arbeitsgaenge,
    rohling, gruppe, material, zeit_drehen, zeit_fraesen, maschine, ruesten, zusatz, aufschlag, richtpreis,
    hinweise, fehler)."""
    w = einstellungen(einst)
    d = e.get("daten") or {}
    erg = dict(arbeitsgaenge=[], rohling=None, gruppe=None, material=0.0, maschine=0.0, ruesten=0.0, zusatz=0.0,
               aufschlag=0.0, richtpreis=None, hinweise=[], fehler=[], zeit_drehen=0.0, zeit_fraesen=0.0,
               zeit_saegen=0.0, stueck=max(1.0, _z(e.get("stueck"), 1.0)), machbarkeit=[], ampel=None)
    art = d.get("art")
    if art not in drehfraes.ARTEN:
        erg["fehler"].append("kein Dreh- oder Frästeil")
        return erg
    sw, zeile = werkstoff_schnittwerte(e.get("werkstoff"), w)
    if sw is None:
        erg["fehler"].append("Schnittwerte fehlen (Einstellungen → Dreh-/Frästeil-Richtpreis)")
        return erg
    erg["gruppe"] = sw["gruppe"]
    erg["werkstoff_tabelle"] = zeile.get("drehfraes_werkstoff_id") if zeile else None
    if zeile and abs(_z(zeile.get("zerspanbarkeit"), 100.0) - 100) > 0.5:
        erg["hinweise"].append(f"Zerspanbarkeit {_fmm(_z(zeile.get('zerspanbarkeit')))} % "
                               f"({zeile.get('drehfraes_werkstoff_id')})")
    elif e.get("werkstoff") and w.get("werkstoffe") and not zeile:
        erg["hinweise"].append(f"{e.get('werkstoff')} nicht in den Dreh-/Fräs-Werkstoffen: Vorgabe der Gruppe "
                               f"{sw['gruppe']}")
    if not e.get("werkstoff"):
        erg["hinweise"].append(f"Werkstoff offen: als {sw['gruppe']} gerechnet")
    if art == drehfraes.DREHTEIL and (_z(d.get("durchmesser")) <= 0 or _z(d.get("laenge")) <= 0):
        erg["fehler"].append("Maße fehlen")
        return erg
    if art == drehfraes.FRAESTEIL and min(_z(d.get("laenge")), _z(d.get("breite")), _z(d.get("hoehe"))) <= 0:
        erg["fehler"].append("Maße fehlen")
        return erg
    if not d.get("kennwerte"):
        erg["hinweise"].append("ohne Kennwerte der Messung (älteres Messergebnis): Flächen geschätzt")
    gaenge = []
    if art == drehfraes.DREHTEIL:
        roh = _drehen(d, sw, w, e.get("rohling") or ROHLING_VOLL, gaenge, erg["hinweise"])
        haupt = DREHEN
    else:
        roh = _fraesen(d, sw, w, gaenge, erg["hinweise"])
        haupt = FRAESEN
    mb = machbarkeit(d, w)
    for x in mb:                    # Zeitzuschlag je Befund auf die betroffenen Arbeitsgänge
        if x["gang"] and x["faktor"] != 1.0:
            for g in gaenge:
                if g["name"].startswith(x["gang"]) or (x["gang"] == "Bohren" and "bohrung" in g["name"].lower()):
                    g["minuten"] *= x["faktor"]
                    g["info"] = (g["info"] + "; " if g["info"] else "") + f"Machbarkeit × {_fmm(x['faktor'])}"
    erg["machbarkeit"], erg["ampel"] = mb, ampel(mb)
    hand = e.get("zeiten") or {}
    for g in gaenge:
        g["berechnet"] = g["minuten"]
        if g["name"] in hand and _z(hand[g["name"]], -1) >= 0:
            g["minuten"] = _z(hand[g["name"]])
            g["hand"] = True
    satz = {DREHEN: w["df_stundensatz_drehen"], FRAESEN: w["df_stundensatz_fraesen"],
            SAEGEN: w["df_stundensatz_drehen"] * 0.6}
    for g in gaenge:
        g["kosten"] = g["minuten"] / 60 * satz[g["verfahren"]]
    zeit = {v: sum(g["minuten"] for g in gaenge if g["verfahren"] == v) for v in (DREHEN, FRAESEN, SAEGEN)}
    if zeit[haupt] < w["df_mindestzeit"]:
        _gang(gaenge, "Mindestzeit", haupt, w["df_mindestzeit"] - zeit[haupt], "")
        gaenge[-1].update(berechnet=gaenge[-1]["minuten"], kosten=gaenge[-1]["minuten"] / 60 * satz[haupt])
        zeit[haupt] = w["df_mindestzeit"]
    erg.update(arbeitsgaenge=gaenge, rohling=roh, zeit_drehen=zeit[DREHEN], zeit_fraesen=zeit[FRAESEN],
               zeit_saegen=zeit[SAEGEN], maschine=sum(g["kosten"] for g in gaenge))
    # Material
    eur_kg = _z(e.get("eur_kg")) or sw["eur_kg"]
    erg["eur_kg"] = eur_kg
    erg["material"] = roh["gewicht"] * (1 + w["df_verschnitt"]) * eur_kg
    # Rüsten und Programmieren je Auftrag, auf die Stückzahl verteilt
    progr = (w["df_programm_drehen"] if haupt == DREHEN else w["df_programm_fraesen"]) + \
        w["df_programm_element"] * roh.get("elemente", 0)
    ruest = w["df_ruesten_drehen"] if haupt == DREHEN else w["df_ruesten_fraesen"]
    if haupt == FRAESEN:
        ruest += w["df_ruesten_aufspannung"] * max(0, roh.get("aufspannungen", 2) - 1)
    r_eur = (ruest + progr) / 60 * satz[haupt]
    if roh.get("zweiter") == FRAESEN:
        r_eur += (w["df_ruesten_fraesen"] * 0.5 + w["df_programm_element"] * 2) / 60 * satz[FRAESEN]
    erg["ruesten_auftrag"] = r_eur
    erg["ruesten_min"] = ruest + progr
    erg["ruesten"] = r_eur / erg["stueck"]
    # Zusätze €/Stück (Gewinde, Oberfläche, Härten …)
    erg["zusatz"] = max(0.0, _z(e.get("zusatz_eur")))
    if "Gewinde/Freiform" in (d.get("zusatz") or ()) and not erg["zusatz"]:
        erg["hinweise"].append("Gewinde/Freiform erkannt: Gewinde bitte als Zusatz €/Stück eintragen")
    netto = erg["material"] + erg["maschine"] + erg["ruesten"] + erg["zusatz"]
    erg["aufschlag"] = netto * w["df_aufschlag"]
    erg["richtpreis"] = round(netto + erg["aufschlag"], 2)
    erg["zeit_stueck"] = sum(zeit.values())
    return erg


def aus_step(d, werkstoff=None, stueck=1):
    """Eingaben für rechnen aus der Messung eines Dreh-/Frästeils (drehfraes.daten)."""
    return dict(daten=d, werkstoff=werkstoff or None, stueck=stueck or 1, rohling=ROHLING_VOLL, zeiten={},
                zusatz_eur=0.0, zusatz_text="")


def richtpreis(d, werkstoff, einst, stueck=1):
    """Richtpreis je Stück [€] oder None (Fehler)."""
    erg = rechnen(aus_step(d, werkstoff, stueck), einst)
    return erg["richtpreis"] if not erg["fehler"] else None


def lesen(text):
    """Gespeicherte Eingaben (positionen.technik) oder None, wenn sie nicht von hier stammen."""
    try:
        x = json.loads(text) if text else None
    except (TypeError, ValueError):
        return None
    return x if isinstance(x, dict) and x.get("quelle") == QUELLE else None


def ek_ist_richtpreis(p):
    """Position eines Dreh-/Frästeils, deren EK nur aus Richtpreisen besteht (kein Preis vom Lieferanten): dann
    erinnert der Angebots-Check an das Fremdangebot."""
    e = lesen(p.get("technik"))
    if e is None:
        return False
    richt = {round(_z(r.get("preis")), 2) for r in e.get("richtpreise") or () if isinstance(r, dict)}
    try:
        liste = json.loads(p.get("zukauf") or "[]")
    except (TypeError, ValueError):
        return False
    preise = [round(_z(z.get("preis")), 2) for x in liste if isinstance(x, dict)
              for z in ((x.get("stand") or {}).get("bezug") or {}).get("preise") or () if _z(z.get("preis")) > 0]
    return bool(richt and preise) and set(preise) <= richt


def speichern(e):
    return json.dumps(dict(e, quelle=QUELLE), ensure_ascii=False)


def _gruppe_text(erg):
    t = erg.get("werkstoff_tabelle")
    return f"{t}, {erg['gruppe']}" if t else str(erg.get("gruppe"))


def bericht(erg):
    """Aufschlüsselung als Textzeilen (Preis-Aufbau, Kalkulations-PDF, Tests)."""
    if erg.get("fehler"):
        return ["Kein Richtpreis: " + "; ".join(erg["fehler"])]
    z = [f"Rohling: {erg['rohling']['text']}, {_fmm(erg['rohling']['gewicht'])} kg × {erg['eur_kg']:.2f} €/kg "
         f"({_gruppe_text(erg)})".replace(".", ",", 1)]
    for g in erg["arbeitsgaenge"]:
        z.append(f"{g['name']}: {g['minuten']:.2f} min {g['verfahren']}".replace(".", ",")
                 + (" (von Hand)" if g.get("hand") else ""))
    z.append(f"Material {erg['material']:.2f} € + Bearbeitung {erg['maschine']:.2f} € + Rüsten/Programm "
             f"{erg['ruesten']:.2f} € + Zusätze {erg['zusatz']:.2f} € + Aufschlag {erg['aufschlag']:.2f} € = "
             f"{erg['richtpreis']:.2f} € je Stück ({_fmm(erg['stueck'])} St)".replace(".", ","))
    return z
