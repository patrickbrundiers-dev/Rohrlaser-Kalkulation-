"""Produktionsdaten-Intelligenz, Phase 1 und 2 (Master-Auftrag Patrick 24.11.2026 „Intelligente Maschinendaten-Analyse
– .LST & .BPF“): alle tatsächlich vorhandenen und deutbaren Werte einer Maschinendatei auslesen, je Wert mit Quelle,
Einheit und Deutung. Ohne Qt, ohne OpenCascade. Formatbeschreibung: docs/maschinendaten/FORMATE.md.

Grundsätze
- Nichts erfinden: ein Wert steht nur im Ergebnis, wenn er in der Datei steht oder eindeutig aus Werten der Datei folgt
  (dann Quelle „berechnet aus …“). Fehlt ein Wert, fehlt er (kein Ersatzwert); fehlende wichtige Werte nennt
  ``fehlend``.
- Deutungen, die aus den Beispielen geschlossen, aber nicht vom Hersteller belegt sind, tragen sicher=False.
- Felder der Datei, die wir (noch) nicht deuten, kommen in ``unbekannt`` (Abschnitt/Feld, Beispielwert), damit sie
  dokumentiert und später ausgewertet werden können.
- Eine beschädigte oder fremde Datei führt nie zu einem Absturz: ``analysieren`` liefert dann fehler (Text).
- Maschinenprogramme werden nur gelesen, nie geändert.

TRUMPF-LST (Programming Tube / TruTops Tube): Abschnitte BEGIN_x … ENDE_x mit MM-Zeilen (Spaltenname und Einheit) und
DA-Zeilen (Werte), danach der NC-Teil (BEGIN_PROGRAMM, Sinumerik). Aus dem NC-Teil werden nur Ereignisse gezählt
(Konturen, Einstiche, Positionierungen, Umspannen, Vollkreise); den Schneidweg als Geometrie liest
trumpf_programm/der LST-Schneidweg-Leser.

BLM-BPF (ArTube, LT7/LT8): gepacktes XML (step_messung/step_blm.bpf_dokumente) mit info_tubo (Querschnitt, Werkstoff),
info_pezzo (Länge, Volumen, Maschine, Gehrungswinkel, Toleranzen), geometrie (je Kontur Art, Länge, Anfahrweg,
Einschalten) und nesting. Die BPF enthält keine Zeiten."""
import csv
import io
import math
import re
from pathlib import Path

LST, BPF = "LST", "BPF"
ENDUNGEN = {".lst": LST, ".bpf": BPF}
# wichtige Werte: fehlen sie, steht es in ``fehlend`` (Datenqualität)
WICHTIG = ("werkstoff", "wand", "laenge", "schneidweg", "einstiche", "konturen", "zeit_gesamt_s")


class MaschinendatenFehler(ValueError):
    pass


def format_von(pfad):
    """'LST', 'BPF' oder None nach der Endung."""
    return ENDUNGEN.get(Path(str(pfad)).suffix.lower())


def _zahl(text):
    try:
        x = float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def wert(w, einheit="", quelle="", deutung="", sicher=True):
    """Ein ausgelesener Wert: [Wert, Einheit, Quelle, Deutung, sicher] (Liste: passt so in JSON)."""
    return [w, einheit, quelle, deutung, bool(sicher)]


def w(merkmale, schluessel, vorgabe=None):
    """Zahl/Text eines Merkmals (nur der Wert) oder vorgabe."""
    x = (merkmale or {}).get(schluessel)
    return x[0] if isinstance(x, (list, tuple)) and x and x[0] is not None else vorgabe


# ======================================================================================================== LST
# (Abschnitt, Feld) -> (Schlüssel, Deutung, sicher, Einheit wenn die Datei keine nennt oder sie falsch ist)
LST_PROGRAMM = {
    ("EINRICHTEPLAN_INFO", "viewer name machine"): ("maschine", "Maschine (Anzeigename)", True, ""),
    ("EINRICHTEPLAN_INFO", "Maschine"): ("maschine_kurz", "Maschinenkürzel", True, ""),
    ("EINRICHTEPLAN_INFO", "EquipmentNumber"): ("anlage_nr", "Anlagennummer der Maschine", True, ""),
    ("EINRICHTEPLAN_INFO", "Steuerung"): ("steuerung", "Steuerung", True, ""),
    ("EINRICHTEPLAN_INFO", "ProgrammingSystemSignature"): ("cam_version", "Programmiersystem und Version", True, ""),
    ("EINRICHTEPLAN_INFO", "SoftwareVersion"): ("software_version", "Softwarestand", True, ""),
    ("EINRICHTEPLAN_INFO", "Bearbeiter"): ("bearbeiter", "Programmierer", True, ""),
    ("EINRICHTEPLAN_INFO", "Datum"): ("datum", "Programmdatum", True, ""),
    ("EINRICHTEPLAN_INFO", "Programmnummer"): ("programm", "Programmname", True, ""),
    ("EINRICHTEPLAN_INFO", "Auftragsname"): ("auftragsname", "Auftragsname im CAM", True, ""),
    ("EINRICHTEPLAN_INFO", "Material-ID"): ("werkstoff_id", "Werkstoff-ID der Maschine", True, ""),
    ("EINRICHTEPLAN_INFO", "Tafelgewicht"): ("gewicht_programm", "Gewicht der Fertigteile des Programms (aus den "
                                             "Beispielen: Rohgewicht minus Ausschnitte)", False, "kg"),
    ("EINRICHTEPLAN_INFO", "Maschinenzeit"): ("maschinenzeit_min", "Maschinenzeit des Programms laut CAM", True, "min"),
    ("EINRICHTEPLAN_INFO", "Processing time PierceLine"): ("zeit_pierceline_min", "Bearbeitungszeit PierceLine "
                                                           "(gleich der Maschinenzeit, keine Einstichzeit)", True, "min"),
    ("EINRICHTEPLAN_INFO", "Cutting length"): ("schneidweg_maschine", "Schneidweg der Maschinenachsen inkl. Anfahrten "
                                               "(nicht die reine Schnittlänge am Material)", True, "mm"),
    ("EINRICHTEPLAN_INFO", "Bemerkung"): ("bemerkung", "Bemerkung des CAM", True, ""),
    ("TUBE_TECH", "Rohr-ID"): ("rohr_id", "Rohr-ID der Profildatenbank", True, ""),
    ("TUBE_TECH", "Material"): ("werkstoff", "Werkstoff", True, ""),
    ("TUBE_TECH", "Rohrlaenge"): ("stangenlaenge", "Rohmaterial-Länge (Stange)", True, "mm"),
    ("TUBE_TECH", "Wandstaerke"): ("wand", "Wandstärke", True, "mm"),
    ("TUBE_TECH", "Hoehe (Rechteckrohr)"): ("hoehe", "Höhe (Rechteckrohr)", True, "mm"),
    ("TUBE_TECH", "Breite (Rechteckrohr)"): ("breite", "Breite (Rechteckrohr)", True, "mm"),
    ("TUBE_TECH", "Eckenradius (Rechteckrohr)"): ("eckenradius", "Eckenradius außen", True, "mm"),
    ("TUBE_TECH", "(Huellkreis-)Durchmesser (Rechteck-/Rundrohr)"): ("durchmesser", "Durchmesser bzw. Hüllkreis",
                                                                     True, "mm"),
    ("TUBE_TECH", "Mass Per Meter"): ("kg_m", "Metergewicht (die Datei nennt „kg“, gemeint ist kg/m)", True, "kg/m"),
    ("TUBE_TECH", "Unfold Length"): ("umfang", "Abwicklungslänge (Umfang)", True, "mm"),
    ("TUBE_TECH", "max. Vorschub X-Achse"): ("max_vorschub_x", "größter Vorschub Längsachse X", True, "mm/min"),
    ("TUBE_TECH", "max. Vorschub A-Achse"): ("max_vorschub_a", "größte Drehgeschwindigkeit A", True, "°/min"),
    ("TUBE_TECH", "max. Beschleunigung X-Achse"): ("max_beschl_x", "größte Beschleunigung X", True, "m/s²"),
    ("TUBE_TECH", "max. Beschleunigung A-Achse"): ("max_beschl_a", "größte Beschleunigung A", True, "1/s²"),
    ("TUBE_TECH", "LaserTechnologieTabelle"): ("technologie", "Laser-Technologietabelle (Schneiddaten)", True, ""),
    ("TUBE_TECH", "Clamping Force Feed Station"): ("spannkraft_vorschub", "Spannkraft Vorschubstation", True, ""),
    ("TUBE_TECH", "Clamping Force Feed Through Chuck"): ("spannkraft_durchschub", "Spannkraft Durchschubfutter",
                                                         True, ""),
    ("TUBE_CORNER", "Schneidvorschub 1"): ("ecken_vorschub_1", "Schneidvorschub an Ecken, Stufe 1", True, "m/min"),
    ("TUBE_CORNER", "Schneidvorschub 2"): ("ecken_vorschub_2", "Schneidvorschub an Ecken, Stufe 2", True, "m/min"),
    ("TUBE_CORNER", "Schneidabstand 1"): ("ecken_abstand_1", "Düsenabstand an Ecken, Stufe 1", True, "mm"),
    ("TUBE_CORNER", "Schneidabstand 2"): ("ecken_abstand_2", "Düsenabstand an Ecken, Stufe 2", True, "mm"),
    ("TUBE_LOAD", "Anschnitt"): ("anschnitt_beladen", "Anschnitt am Stangenanfang", True, "mm"),
    ("TUBE_LOAD", "Spanntechnik"): ("spanntechnik", "Spanntechnik (Code)", False, ""),
    ("MICROJOINT", "programmierte Microjoints aktiv"): ("microjoints_programmiert", "programmierte Microjoints", True,
                                                         ""),
    ("MICROJOINT", "automatische Microjoints aktiv"): ("microjoints_auto", "automatische Microjoints", True, ""),
    ("PROGRAM_PROPERTIES", "Bevel Cutting Version"): ("fase_version", "Fasenschnitt (0 = keiner)", False, ""),
    ("PROGRAMM", "Bearbeitungszeit"): ("bearbeitungszeit_min", "Bearbeitungszeit des NC-Programms", True, "min"),
}
LST_TEIL = {
    ("TUBE_PART_TECH", "Work Part Length"): ("laenge", "Fertigteil-Länge", True, "mm"),
    ("TUBE_PART_TECH", "Bearbeitungslaenge (Soll)"): ("bearbeitungslaenge", "Bearbeitungslänge je Teil (mit "
                                                      "Anschnitt und Abschnitt)", True, "mm"),
    ("TUBE_PART_TECH", "Rohrlaenge (Soll)"): ("rohlaenge_soll", "programmierte Rohrlänge des Teils", True, "mm"),
    ("TUBE_PART_TECH", "X Min Gap To Next Part"): ("teileabstand", "kleinster Abstand zum nächsten Teil", True, "mm"),
    ("TUBE_PART_TECH", "Machining Length First Cut"): ("zugabe_anschnitt", "Bearbeitungszugabe Anschnitt", True, "mm"),
    ("TUBE_PART_TECH", "Machining Length Cut Off"): ("zugabe_abschnitt", "Bearbeitungszugabe Abschnitt", True, "mm"),
    ("TUBE_PART_TECH", "Gemeinsamer Trennschnitt"): ("gemeinsamer_trennschnitt", "gemeinsamer Trennschnitt erlaubt",
                                                     True, ""),
    ("TUBE_PART_TECH", "kleinste Kontur"): ("kleinste_kontur", "kleinste Kontur", True, "mm"),
    ("TUBE_PART_TECH", "Wirkkontur"): ("wirkkontur", "Wirkkontur", False, "mm"),
    ("TUBE_PART_TECH", "Contour Free Length Before Cut Off"): ("freilaenge_abschnitt", "konturfreie Länge vor dem "
                                                               "Abschnitt", True, "mm"),
    ("TUBE_PART_TECH", "Chuck Position Program Start End"): ("spannlaenge", "Futterposition am Programmanfang/-ende "
                                                             "(vermutlich Restlänge im Futter)", False, "mm"),
    ("TUBE_PART_TECH", "RapidCut Allowed"): ("rapidcut", "RapidCut erlaubt", True, ""),
    ("TUBE_PART_TECH", "Seam Position Is Defined"): ("naht_vorgegeben", "Lage der Schweißnaht vorgegeben", True, ""),
    ("TUBE_PART_TECH", "Unload Type"): ("entladeart", "Entladeart (Code)", False, ""),
    ("TUBE_PART_TECH", "Werkstoffkennung"): ("werkstoff_teil", "Werkstoff des Teils", True, ""),
}
# TUBE_PART_TIMES: berechnet und gemessen (die Maschine schreibt die Messung nach dem Lauf in die LST)
ZEIT_TEXT = (("anschnitt", "First Cut"), ("konturen", "Contour"), ("abschnitt", "Cut Off"))
LST_BEKANNT_ABSCHNITTE = {"EINRICHTEPLAN_INFO", "TUBE_TECH", "TUBE_CORNER", "TUBE_LOAD", "MICROJOINT",
                          "PROGRAM_PROPERTIES", "PROGRAMM", "TUBE_PART_TECH", "TUBE_PART_TIMES", "CONSUMPTION_TIMES",
                          "FERTIGUNG_AUFTRAG_TMP", "TOPS_DATA", "TUBE_PART_UNLOAD", "TUBE_UNLOAD", "TUBE_END_LEFT",
                          "TUBE_END_RIGHT", "GLOBAL_DATASET", "LTT_CALLS", "ANALYTICS_DATA", "TUBE_PART_VARIANTS"}


def _werte(zeile):
    return [x.strip() for x in next(csv.reader(io.StringIO(zeile), quotechar="'", skipinitialspace=True))]


def lst_abschnitte(text):
    """[(Abschnitt, [(Feld, Einheit)], [dict je Datenzeile])] in Dateireihenfolge (ohne NC-Text)."""
    out, name, spalten, daten = [], None, [], []
    for roh in text.splitlines():
        z = roh.rstrip()
        if z.startswith("BEGIN_"):
            name, spalten, daten = z[6:].strip(), [], []
        elif name and z.startswith("ENDE_"):
            try:
                zeilen = [dict(zip([s for s, _ in spalten], _werte(d))) for d in daten]
            except (csv.Error, StopIteration):
                zeilen = []
            out.append((name, spalten, zeilen))
            name = None
        elif name is None or z.startswith("START_TEXT"):
            continue
        elif z.startswith("MM,AT"):
            try:
                f = _werte(z)
            except (csv.Error, StopIteration):
                continue
            spalten.append((f[7] if len(f) > 7 else "", f[9] if len(f) > 9 else ""))
        elif z.startswith("DA,"):
            daten.append(z[3:])
        elif z.startswith("*") and daten:
            daten[-1] += z[1:].strip()
    return out


def nc_ereignisse(nc):
    """Ereignisse im NC-Teil zählen (keine Geometrie): dict(konturen, einstiche, positionierungen, umspannen,
    vollkreise, abschnitte [Namen der Programmabschnitte], saetze, anfahrten)."""
    n = dict(konturen=0, einstiche=0, positionierungen=0, umspannen=0, vollkreise=0, abschnitte=[], saetze=0,
             anfahrten=0)
    an = False
    for z in nc.splitlines():
        s = z.strip()
        if not s or s.startswith(("BEGIN_", "ENDE_", "START_TEXT", "C")) and not s.startswith("CALL"):
            continue
        n["saetze"] += 1
        teil = s.split(" ", 1)[1] if re.match(r"N\d+\s", s) else s       # Satznummer N10 … ist freiwillig
        if ";(Contour:" in teil:
            n["konturen"] += 1
        if "TC_LASER_ON(" in teil:
            n["einstiche"] += not an
            an = True
        elif "TC_LASER_OFF(" in teil:
            an = False
        if teil.startswith("TC_POS("):
            n["positionierungen"] += 1
        if "TC_TUBE_CHUCKMOVE" in teil:
            n["umspannen"] += 1
        if ";LeadIn" in teil and "Rounding" not in teil:
            n["anfahrten"] += 1
        m = re.match(r"TC_PROG_SECTION\((\w+)", teil)
        if m:
            n["abschnitte"].append(m.group(1))
        # Vollkreis: G02/G03 nur mit I/J (ohne Zielpunkt X/Y), Kommentar ;Processing
        if re.match(r"G0?[23]\s+I", teil) and " X" not in teil and " Y" not in teil:
            n["vollkreise"] += 1
    return n


def _hms(text):
    m = re.match(r"\s*(\d+)\s*:\s*(\d+)\s*:\s*(\d+)", str(text or ""))
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None


def _feld_wert(roh, einheit):
    z = _zahl(roh)
    if z is not None and re.fullmatch(r"\s*-?[\d.,]+\s*", str(roh)):
        return z
    return str(roh).strip()


def _programm_bloecke(text):
    return [b for b in re.split(r"(?m)^BD\s*$", text) if "BEGIN_EINRICHTEPLAN_INFO" in b]


def lst_auswerten(text, name="LST"):
    """Alle deutbaren Werte einer LST: [dict(format, programm, teil_nr, version, merkmale {Schlüssel: wert(..)},
    unbekannt [(Abschnitt, Feld, Beispiel)], fehlend [Schlüssel])] je Teil in der Reihenfolge von
    trumpf_programm.lst_lesen."""
    if "BEGIN_EINRICHTEPLAN_INFO" not in text:
        raise MaschinendatenFehler(f"{name}: keine TRUMPF-LST (Abschnitt EINRICHTEPLAN_INFO fehlt).")
    auftrag = {}
    for ab, _sp, zeilen in lst_abschnitte(text.split("\nBD")[0] if "\nBD" in text else ""):
        if ab == "FERTIGUNG_AUFTRAG_TMP":
            for z in zeilen:
                auftrag[z.get("Programmname")] = z
    for ab, _sp, zeilen in lst_abschnitte(text):
        if ab == "FERTIGUNG_AUFTRAG_TMP":
            for z in zeilen:
                auftrag.setdefault(z.get("Programmname"), z)
    out = []
    for block in _programm_bloecke(text):
        abschnitte = lst_abschnitte(block)
        einheiten, daten = {}, {}
        for ab, spalten, zeilen in abschnitte:
            for f, e in spalten:
                einheiten[(ab, f)] = e
            daten.setdefault(ab, []).extend(zeilen)
        info = (daten.get("EINRICHTEPLAN_INFO") or [{}])[0]
        prog = info.get("Programmnummer") or Path(name).stem
        gemeinsam, unbekannt = {}, []
        for (ab, feld), (schl, deutung, sicher, einheit) in LST_PROGRAMM.items():
            z = (daten.get(ab) or [{}])[0]
            roh = z.get(feld)
            if roh in (None, "", "none"):
                continue
            gemeinsam[schl] = wert(_feld_wert(roh, einheit), einheit or einheiten.get((ab, feld), ""),
                                   f"LST {ab} / {feld}", deutung, sicher)
        tops = {str(z.get("Datensatzname")): z.get("Wert") for z in daten.get("TOPS_DATA") or ()}
        if _hms(tops.get("103")) is not None:
            gemeinsam["zeit_tops_s"] = wert(_hms(tops["103"]), "s", "LST TOPS_DATA / 103",
                                            "Programmlaufzeit laut TruTops (h:min:s)", False)
        # Gas und Strahl: Verbrauchsgruppe 1 = Schneidgas (in den Beispielen mit Düse und Druck)
        for z in daten.get("CONSUMPTION_TIMES") or ():
            if str(z.get("ConsumptionGroup")).strip() == "1":
                for schl, feld, einheit, deutung in (
                        ("strahl_s", "OnTime", "s", "Strahl ein (Schneidgas-Gruppe 1)"),
                        ("gas_l", "GasVolumeInLiters", "l", "Gasmenge (Schneidgas-Gruppe 1)"),
                        ("gasdruck", "GasPressure", "bar", "Gasdruck"), ("duese", "NozzleDiameter", "mm", "Düse"),
                        ("gasart", "GasType", "", "Gasart (Code)")):
                    x = _zahl(z.get(feld))
                    if x is not None:
                        gemeinsam[schl] = wert(x, einheit, f"LST CONSUMPTION_TIMES / {feld}", deutung,
                                               schl not in ("gasart", "duese"))
                break
        # Verbrauchsgruppe 2 (aus den Beispielen: Summe = berechnete Maschinenzeit): bei 0 W Verfahren/Positionieren
        # mit Laser aus, sonst Laser an je Leistungsstufe (Patrick 24.11.2026: Laserzeit getrennt nutzen)
        an, aus, stufen = 0.0, 0.0, {}
        for z in daten.get("CONSUMPTION_TIMES") or ():
            if str(z.get("ConsumptionGroup")).strip() != "2":
                continue
            t, lw = _zahl(z.get("OnTime")) or 0.0, _zahl(z.get("LaserPower")) or 0.0
            if lw > 0:
                an += t
                stufen[int(lw)] = stufen.get(int(lw), 0.0) + t
            else:
                aus += t
        teile_n = max(1, len(daten.get("TUBE_PART_TECH") or [{}]))
        if an:          # ohne Zeile mit Laserleistung ist die Aufteilung nicht belegt
            q = "LST CONSUMPTION_TIMES Gruppe 2 / OnTime" + (f" ÷ {teile_n} Teile" if teile_n > 1 else "")
            gemeinsam["laser_an_s"] = wert(round(an / teile_n, 2), "s", q + ", LaserPower > 0",
                                           "reine Laserzeit je Teil (Laser an, alle Leistungsstufen)", teile_n == 1)
            gemeinsam["verfahren_s"] = wert(round(aus / teile_n, 2), "s", q + ", LaserPower = 0",
                                            "Verfahren und Positionieren je Teil (Laser aus)", teile_n == 1)
            for lw, t in sorted(stufen.items()):
                gemeinsam[f"laser_an_{lw}w_s"] = wert(round(t / teile_n, 2), "s", q + f", LaserPower = {lw} W",
                                                      f"Laser an mit {lw} W je Teil", teile_n == 1)
        nc = block[block.find("BEGIN_PROGRAMM"):] if "BEGIN_PROGRAMM" in block else ""
        ne = nc_ereignisse(nc) if nc else None
        for ab, spalten, zeilen in abschnitte:      # nicht gedeutete Felder dokumentieren
            for f, _e in spalten:
                if (ab, f) in LST_PROGRAMM or (ab, f) in LST_TEIL or ab in ("TUBE_PART_TIMES", "CONSUMPTION_TIMES",
                                                                             "FERTIGUNG_AUFTRAG_TMP", "TOPS_DATA"):
                    continue
                beisp = next((z.get(f) for z in zeilen if z.get(f) not in (None, "")), "")
                if beisp != "":
                    unbekannt.append((ab, f, str(beisp)[:40]))
            if ab not in LST_BEKANNT_ABSCHNITTE:
                unbekannt.append((ab, "(ganzer Abschnitt)", ""))
        teile = daten.get("TUBE_PART_TECH") or [{}]
        zeiten = {z.get("Data Set Name"): z for z in daten.get("TUBE_PART_TIMES") or ()}
        fa = auftrag.get(prog) or {}
        for i, pt in enumerate(teile):
            m = dict(gemeinsam)
            if fa.get("Jobname"):
                m["job"] = wert(fa["Jobname"], "", "LST FERTIGUNG_AUFTRAG_TMP / Jobname", "Jobname", True)
            if fa.get("FertAuftrBez"):
                m["fertigungsauftrag"] = wert(fa["FertAuftrBez"], "", "LST FERTIGUNG_AUFTRAG_TMP / FertAuftrBez",
                                              "Fertigungsauftrag", True)
            if _zahl(fa.get("SollAnzahl")):
                m["sollanzahl"] = wert(int(_zahl(fa["SollAnzahl"])), "Stück", "LST FERTIGUNG_AUFTRAG_TMP / SollAnzahl",
                                       "Sollanzahl des Programms", True)
            for (ab, feld), (schl, deutung, sicher, einheit) in LST_TEIL.items():
                roh = pt.get(feld)
                if roh in (None, ""):
                    continue
                m[schl] = wert(_feld_wert(roh, einheit), einheit or einheiten.get((ab, feld), ""),
                               f"LST {ab} / {feld}", deutung, sicher)
            z = zeiten.get(pt.get("Tabellenidentifikator")) or (list(zeiten.values())[0] if len(zeiten) == 1 else {})
            ber = {k: _zahl(z.get(f"Calculated {t} Machine Time")) for k, t in ZEIT_TEXT}
            for k, t in ZEIT_TEXT:
                if ber[k] is not None:
                    m[f"zeit_{k}_s"] = wert(ber[k], "s", f"LST TUBE_PART_TIMES / Calculated {t} Machine Time",
                                            f"Maschinenzeit {k} je Teil (berechnet vom CAM)", True)
            if any(v is not None for v in ber.values()):
                m["zeit_gesamt_s"] = wert(round(sum(v or 0.0 for v in ber.values()), 2), "s",
                                          "berechnet aus TUBE_PART_TIMES (Anschnitt + Konturen + Abschnitt)",
                                          "Maschinenzeit je Teil (berechnet vom CAM)", True)
            n_mess = int(_zahl(z.get("Number Of Recorded Part Times")) or 0)
            mittel = {k: _zahl(z.get(f"Average Measured {t} Machine Time")) for k, t in ZEIT_TEXT}
            letzt = {k: _zahl(z.get(f"Last Program Run Measured {t} Machine Time")) for k, t in ZEIT_TEXT}
            gem = mittel if n_mess and any(mittel.values()) else letzt if any(letzt.values()) else None
            if gem:
                m["zeit_gemessen_s"] = wert(round(sum(v or 0.0 for v in gem.values()), 2), "s",
                                            "LST TUBE_PART_TIMES / " + ("Average Measured …" if gem is mittel
                                                                        else "Last Program Run Measured …"),
                                            "an der Maschine gemessene Zeit je Teil", True)
                m["messungen"] = wert(n_mess, "", "LST TUBE_PART_TIMES / Number Of Recorded Part Times",
                                      "Zahl der gemessenen Läufe", True)
            if ne is not None:
                n = len(teile)
                quelle = "gezählt im NC-Teil (BEGIN_PROGRAMM)" + (f", ÷ {n} Teile" if n > 1 else "")
                if not ne["konturen"] and ne["einstiche"]:     # ohne Kontur-Kommentare: Anzahl unbekannt
                    ne = dict(ne, konturen=None)
                for schl, deutung in (("konturen", "Konturen (Kommentar „Contour“)"),
                                      ("einstiche", "Einstiche (Laser ein nach Laser aus)"),
                                      ("positionierungen", "Positionierbewegungen (TC_POS)"),
                                      ("umspannen", "Umspannvorgänge (Futterbewegung TC_TUBE_CHUCKMOVE)"),
                                      ("vollkreise", "Vollkreise (Bohrungen)"), ("anfahrten", "Anfahrten (LeadIn)")):
                    if ne[schl] is not None:
                        m[schl] = wert(round(ne[schl] / n) if n > 1 else ne[schl], "", quelle, deutung, n == 1)
                m["nc_saetze"] = wert(ne["saetze"], "", "gezählt im NC-Teil", "NC-Sätze des Programms", True)
                if ne["abschnitte"]:
                    m["programmabschnitte"] = wert(", ".join(ne["abschnitte"]), "", "NC TC_PROG_SECTION",
                                                   "Programmabschnitte", True)
            weg = w(m, "schneidweg_maschine")
            if weg is not None:     # Schnittlänge am Material liefert der NC-Schneidweg (produktion_lst.lesen_teile)
                m["maschinenweg"] = wert(round(weg / len(teile), 1), "mm", "LST EINRICHTEPLAN_INFO / Cutting length"
                                         + (f" ÷ {len(teile)} Teile" if len(teile) > 1 else ""),
                                         "Weg der Maschinenachsen je Teil (mit Anfahrten)", len(teile) == 1)
            _abgeleitet(m)
            out.append(dict(format=LST, programm=prog, teil_nr=i + 1,
                            version=w(m, "cam_version") or w(m, "software_version") or "",
                            merkmale=m, unbekannt=unbekannt if i == 0 else [], fehlend=_fehlend(m)))
    if not out:
        raise MaschinendatenFehler(f"{name}: kein Programm gefunden.")
    return out


def _abgeleitet(m):
    """Werte, die eindeutig aus Werten der Datei folgen (Quelle „berechnet aus …“)."""
    bl, ab = w(m, "bearbeitungslaenge"), w(m, "teileabstand")
    if isinstance(bl, (int, float)):
        m["verbrauch_mm"] = wert(round(bl + (ab or 0.0), 2), "mm", "berechnet aus Bearbeitungslänge + Teileabstand",
                                 "Materialverbrauch je Teil auf der Stange", ab is not None)
    st, v = w(m, "stangenlaenge"), w(m, "verbrauch_mm")
    if isinstance(st, (int, float)) and isinstance(v, (int, float)) and v > 0:
        rest = (w(m, "anschnitt_beladen", 0.0) or 0.0) + (w(m, "spannlaenge", 0.0) or 0.0)
        n = int((st - rest) // v)
        if n > 0:
            m["teile_je_stange"] = wert(n, "Stück", "berechnet aus Stangenlänge − Anschnitt − Futterposition, ÷ "
                                        "Verbrauch je Teil", "Teile je Stange bei nur diesem Teil", False)
            lg = w(m, "laenge")
            if isinstance(lg, (int, float)):
                m["ausnutzung_pct"] = wert(round(100.0 * n * lg / st, 1), "%", "berechnet aus Teile je Stange × "
                                           "Länge ÷ Stangenlänge", "Materialausnutzung bei nur diesem Teil", False)
    weg, zk = w(m, "maschinenweg"), w(m, "zeit_konturen_s")
    if isinstance(weg, (int, float)) and isinstance(zk, (int, float)) and zk > 0:
        m["vorschub_mittel"] = wert(round(weg / 1000.0 / (zk / 60.0), 2), "m/min", "berechnet aus Maschinenweg ÷ "
                                    "Konturzeit", "mittlerer Bahnvorschub inkl. Ecken, Einstichen und Anfahrten", True)
    kg, lg = w(m, "kg_m"), w(m, "laenge")
    if isinstance(kg, (int, float)) and isinstance(lg, (int, float)):
        m["gewicht_roh"] = wert(round(kg * lg / 1000.0, 3), "kg", "berechnet aus Metergewicht × Länge",
                                "Rohgewicht je Teil (ohne Ausschnitte)", True)
    if w(m, "zeit_tops_s") is None and isinstance(w(m, "maschinenzeit_min"), (int, float)):
        pass        # Programmzeit steht in maschinenzeit_min; keine weitere Ableitung


def _fehlend(m):
    return [s for s in WICHTIG if w(m, s) in (None, "") and not (s == "schneidweg" and w(m, "maschinenweg"))]


# ======================================================================================================== BPF
GEO_ART = {"1": "geschlossen", "2": "Trennschnitt", "3": "offen"}      # info_geo/tipogeo (aus den Beispielen)
BPF_BENUTZT = {"versione_output_xml", "sw", "versione_sw", "data_partprogram", "ora_partprogram", "lunghezza",
               "volume", "materiale", "nome_sezione", "tipo", "dim_x", "dim_y", "spessore", "raggiatura",
               "superficie", "famiglia", "matricola", "versione", "microgiunzioni", "ang_conico_max", "ang_xz_max",
               "ang_xz_min", "ang_yz_max", "ang_yz_min", "toll_lin", "toll_ang", "toll_prec", "tipogeo", "l",
               "tipo_faccia", "accensione", "AngIn", "AngOut", "DrawLen", "Length", "XCutMin", "XCutMax",
               "x_min_geo", "x_max_geo", "nome", "info_rapido", "tipo_intestatura_dx", "tipo_intestatura_sx",
               "velo", "velocita", "pt_3d", "versore", "punto", "punti", "info_geo", "info_faccia", "facce",
               "geometrie", "Progetto", "bpf", "info_tubo", "sezione", "info_pezzo", "nesting", "macchine",
               "macchina_valida", "rapidi", "tipot", "p_ini", "p_fin", "normale", "centro", "raggio", "angolo",
               "top", "topologie", "profili", "profilo_esterno", "profilo_interno"}


def _t(e, pfad):
    x = e.find(pfad) if e is not None else None
    return (x.text or "").strip() if x is not None and x.text is not None else ""


def _f(e, pfad):
    return _zahl(_t(e, pfad))


def _profilform(name, a, b, aussen_boegen_nur):
    n = (name or "").lower()
    if "rund" in n or "round" in n or "circ" in n or aussen_boegen_nur:
        return "Rundrohr"
    if a and b and abs(a - b) < 0.05:
        return "Quadratrohr"
    return "Rechteckrohr" if a and b else None


def bpf_auswerten(daten, name="BPF"):
    """Alle deutbaren Werte einer BPF (ein Teil): [dict(format, programm, teil_nr, version, merkmale, unbekannt,
    fehlend, kopf (Profilform, a, b, wand, radius für die Tabelle der Produktionsdaten))]."""
    from step_messung import step_blm
    try:
        docs = step_blm.bpf_dokumente(daten)
    except (ValueError, IndexError, KeyError, UnicodeDecodeError) as e:
        raise MaschinendatenFehler(f"{name}: {e}") from e
    proj = next((d.find("Progetto") for d in docs if d.find("Progetto") is not None), None)
    if proj is None:
        raise MaschinendatenFehler(f"{name}: BPF ohne Projekt (Progetto).")
    sez, pez = proj.find("info_tubo/sezione"), proj.find("info_pezzo")
    if sez is None or pez is None:
        raise MaschinendatenFehler(f"{name}: BPF ohne Rohrangaben (info_tubo/info_pezzo).")
    m = {}

    def setz(schl, x, einheit, quelle, deutung, sicher=True):
        if x not in (None, ""):
            m[schl] = wert(x, einheit, f"BPF {quelle}", deutung, sicher)

    setz("cam_version", f"{_t(proj, 'sw')} {_t(proj, 'versione_sw')}".strip(), "", "sw / versione_sw",
         "Programmiersystem und Version")
    setz("format_version", _t(proj, "versione_output_xml"), "", "versione_output_xml", "Version des Dateiformats")
    mv = proj.find("info_pezzo/macchine/macchina_valida")
    setz("maschine", _t(mv, "famiglia"), "", "macchina_valida / famiglia", "Maschine (Baureihe)")
    setz("anlage_nr", _t(mv, "matricola"), "", "macchina_valida / matricola", "Maschinennummer")
    setz("datum", _t(pez, "data_partprogram").replace("/", "-"), "", "info_pezzo / data_partprogram",
         "Programmdatum")
    setz("werkstoff", _t(proj, "info_tubo/materiale"), "", "info_tubo / materiale", "Werkstoff (Kurzname im CAM)")
    a, b = _f(sez, "dim_x"), _f(sez, "dim_y")
    aussen = sez.find("profili/profilo_esterno")
    boegen_nur = aussen is not None and all((t.findtext("tipot") or "").strip() != "1" for t in aussen.iter("top")) \
        and any(True for _ in aussen.iter("top"))
    form = _profilform(_t(sez, "nome_sezione"), a, b, boegen_nur)
    setz("profil_name", _t(sez, "nome_sezione"), "", "sezione / nome_sezione", "Querschnitt (Name)")
    setz("breite", a, "mm", "sezione / dim_x", "Breite bzw. Durchmesser")
    setz("hoehe", b, "mm", "sezione / dim_y", "Höhe")
    setz("wand", _f(sez, "spessore"), "mm", "sezione / spessore", "Wandstärke")
    setz("eckenradius", _f(sez, "raggiatura"), "mm", "sezione / raggiatura", "Eckenradius")
    setz("querschnittsflaeche", _f(sez, "superficie"), "mm²", "sezione / superficie", "Querschnittsfläche")
    setz("laenge", _f(pez, "lunghezza"), "mm", "info_pezzo / lunghezza", "Fertigteil-Länge")
    setz("volumen", _f(pez, "volume"), "mm³", "info_pezzo / volume", "Volumen des Fertigteils")
    setz("microjoints", _f(pez, "microgiunzioni"), "", "info_pezzo / microgiunzioni", "Microjoints")
    setz("schraeg_max", _f(pez, "angoli/ang_conico_max"), "°", "info_pezzo / angoli / ang_conico_max",
         "größter Schrägschnittwinkel (Fase)", False)
    setz("toleranz_linear", _f(pez, "tolleranze/toll_lin"), "", "tolleranze / toll_lin", "CAM-Toleranz linear",
         False)
    ns = next((d.find(".//nesting") for d in docs if d.find(".//nesting") is not None), None)
    if ns is not None:
        setz("gehrung_anfang", _f(ns, "AngIn"), "°", "nesting / AngIn", "Winkel am Teilanfang (0 = gerade)", False)
        setz("gehrung_ende", _f(ns, "AngOut"), "°", "nesting / AngOut", "Winkel am Teilende (90 = gerade?)", False)
        setz("bearbeitung_bis", _f(ns, "XCutMax"), "mm", "nesting / XCutMax", "Bearbeitungsbereich bis X", False)
    # Konturen
    arten, laenge, anfahr, stiche, kreise = {}, 0.0, 0.0, 0, 0
    for g in proj.findall("geometrie/info_geo"):
        art = GEO_ART.get(_t(g, "tipogeo"), f"Art {_t(g, 'tipogeo') or '?'}")
        arten[art] = arten.get(art, 0) + 1
        laenge += _f(g, "dimensioni/l") or 0.0
        punkte = []
        for fa in g.findall("facce/info_faccia"):
            pk = [step_blm._p(pu.find("pt_3d")) for pu in fa.findall("punti/punto")]
            pk = [p for p in pk if p is not None]
            if _t(fa, "tipo_faccia") == "2":
                anfahr += sum(math.dist(p, q) for p, q in zip(pk, pk[1:]))
            else:
                punkte += pk
        stiche += any((e.text or "").strip() == "1" for e in g.iter("accensione"))     # je Kontur einmal ein
        if art == "geschlossen" and len(punkte) >= step_blm.KREIS_MIN_PUNKTE:
            try:
                kreise += step_blm.kreis_aus_punkten(punkte) is not None
            except (ValueError, ZeroDivisionError, IndexError):
                pass
    n_geo = sum(arten.values())
    if n_geo:
        setz("konturen", n_geo, "", "geometrie / info_geo (Anzahl)", "Konturen (Schneidwege)")
        for art, n in sorted(arten.items()):
            setz(f"konturen_{art.lower()}", n, "", "geometrie / info_geo / tipogeo", f"Konturen: {art}", False)
        setz("schneidweg", round(laenge, 1), "mm", "Summe geometrie / info_geo / dimensioni / l",
             "Schnittlänge am Teil (Summe der Konturlängen)")
        setz("anfahrweg", round(anfahr, 1), "mm", "Summe der Flächen tipo_faccia 2", "Anfahrwege", False)
        setz("vollkreise", kreise, "", "geschlossene Konturen, deren Punkte einen Kreis bilden", "Vollkreise (Bohrungen)")
    if stiche:
        setz("einstiche", stiche, "", "geometrie / info_geo mit accensione = 1", "Einstiche (je Kontur einmal Laser "
             "ein)", False)
    rap = proj.find("rapidi")
    if rap is not None:
        setz("positionierungen", len(rap.findall("info_rapido")), "", "rapidi / info_rapido (Anzahl)",
             "Eilgänge zwischen den Konturen")
    _abgeleitet(m)
    used = BPF_BENUTZT
    unbekannt, gesehen = [], set()
    for d in docs:
        for e in d.iter():
            if e.tag in used or e.tag in gesehen or len(e):
                continue
            gesehen.add(e.tag)
            unbekannt.append(("XML", e.tag, (e.text or "").strip()[:40] or
                              ", ".join(f"{k}={v}" for k, v in list(e.attrib.items())[:2])))
    prog = _t(pez, "nome") or Path(name).stem
    kopf = dict(profilform=form, a=max(a or 0, b or 0) or None, b=(min(a or 0, b or 0) or None)
                if form != "Rundrohr" else None, wand=w(m, "wand"),
                radius=w(m, "eckenradius") if form != "Rundrohr" else None)
    return [dict(format=BPF, programm=prog, teil_nr=1, version=w(m, "format_version") or "", merkmale=m,
                 unbekannt=unbekannt, fehlend=_fehlend(m) + ["Zeiten (die BPF enthält keine Zeiten)"], kopf=kopf)]


# ================================================================================================== zusammen
def _text(roh):
    try:
        return roh.decode("utf-8")
    except UnicodeDecodeError:
        return roh.decode("cp1252", errors="replace")


def auswerten(roh, name):
    """Datei-Inhalt (Bytes) auswerten; Format nach der Endung. Fehler: MaschinendatenFehler."""
    fmt = format_von(name)
    if fmt == LST:
        return lst_auswerten(_text(roh), name)
    if fmt == BPF:
        return bpf_auswerten(roh, name)
    raise MaschinendatenFehler(f"{name}: unbekanntes Format (nur .lst und .bpf).")


def analysieren(pfad):
    """Eine Datei lesen und auswerten, ohne Ausnahme: dict(pfad, format, teile [..], fehler)."""
    p = Path(str(pfad))
    try:
        return dict(pfad=str(p), format=format_von(p), teile=auswerten(p.read_bytes(), p.name), fehler="")
    except MaschinendatenFehler as e:
        return dict(pfad=str(p), format=format_von(p), teile=[], fehler=str(e))
    except OSError as e:
        return dict(pfad=str(p), format=format_von(p), teile=[], fehler=f"{p.name}: nicht lesbar ({e})")
    except Exception as e:  # noqa: BLE001 – beschädigte Datei darf das Programm nie anhalten
        return dict(pfad=str(p), format=format_von(p), teile=[], fehler=f"{p.name}: beschädigt ({type(e).__name__}: "
                                                                        f"{e})")


def bpf_teil_zeile(e):
    """BPF-Auswertung → Teil im Aufbau von trumpf_programm.lst_lesen (für die Produktionsdaten)."""
    m, k = e["merkmale"], e.get("kopf") or {}
    return dict(quelle="", programm=e["programm"], teil_nr=1, artikel=e["programm"], auftrag="", stueck=None,
                profilform=k.get("profilform"), a=k.get("a"), b=k.get("b"), wand=k.get("wand"),
                radius=k.get("radius"), laenge=w(m, "laenge"), werkstoff=w(m, "werkstoff") or "", werkstoff_nr="",
                schneidweg=w(m, "schneidweg"), einstiche=w(m, "einstiche"), zeit_s=None,
                maschine=w(m, "maschine") or "", stangenlaenge=None, kg_m=None, datum=w(m, "datum") or "",
                hinweise=["BPF: keine Zeiten in der Datei"], teile_im_programm=1, zeiten_berechnet=None,
                zeiten_gemessen=None, messungen=0, maschinenzeit_s=None, strahl_s=None)


def merkmal_text(schl, x):
    """'Deutung: Wert Einheit' für Anzeigen."""
    v, einheit, _q, deutung, sicher = (list(x) + [None] * 5)[:5]
    if isinstance(v, float):
        v = f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{deutung or schl}: {v}{(' ' + einheit) if einheit else ''}{'' if sicher else ' (Deutung unsicher)'}"
