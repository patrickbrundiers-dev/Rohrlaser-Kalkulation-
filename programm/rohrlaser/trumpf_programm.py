"""TRUMPF-Rohrprogramme einlesen: LST (TruTops Tube / Programming Tube) und TUBX (TubeCAM-Projekt), Patrick
20.11.2026 („Tube und lst Daten ich möchte diese einlesen können“). Ohne Qt.

LST: Textdatei (Windows-1252) mit Abschnitten BEGIN_<Name> … ENDE_<Name>; MM-Zeilen nennen die Spalten, DA-Zeilen
(mit „*“-Folgezeilen) die Werte. Eine Job-Liste enthält mehrere Programme (je ein Block BD … ED) und vorneweg
FERTIGUNG_AUFTRAG_TMP mit Fertigungsauftrag und Sollanzahl je Programm. Gelesen werden je Programm: Maschine,
Werkstoff, Rohr (Querschnitt, Höhe, Breite, Durchmesser, Wand, Eckenradius, Stangenlänge, kg/m), je Teil die Länge,
die berechneten Zeiten (Anschnitt, Konturen, Abschnitt), dazu Schneidweg (Cutting length) und Einstiche
(TC_LASER_ON nach TC_LASER_OFF im NC-Teil).

TUBX: ZIP mit tubeProps/app.xml (Profil-ID, Profilart, Maschine, Werkstoffnummer, Wandstärke) und
Task3D/Workpiece*.bson (Teillänge, Gewicht, Kunde). Schneidweg, Einstiche und Zeiten stehen nur in der LST: liegt
eine LST mit demselben Programmnamen daneben, gelten ihre Werte.

Ergebnis je Teil: dict(quelle, programm, artikel, stueck, profilform, a, b, wand, radius, laenge, werkstoff,
werkstoff_nr, schneidweg, einstiche, zeit_s, maschine, stangenlaenge, kg_m, hinweise)."""
import csv
import io
import re
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ENDUNGEN = (".lst", ".tubx")
# TRUMPF-Werkstoffnamen → Suchwort für die Werkstoffe der Stammdaten
WERKSTOFF = {"st37": "S235", "st37-2": "S235", "s235": "S235", "1.0038": "S235", "1.0037": "S235",
             "st52": "S355", "st52-3": "S355", "s355": "S355", "1.0570": "S355", "1.0577": "S355",
             "1.4301": "1.4301", "v2a": "1.4301", "1.4571": "1.4571", "v4a": "1.4571", "1.4404": "1.4404",
             "almg3": "AlMg3", "alu": "Alu", "almgsi": "AlMgSi"}
PROFILART = {"rectangular": "Rechteckrohr", "square": "Quadratrohr", "round": "Rundrohr", "circular": "Rundrohr"}


class TrumpfFehler(ValueError):
    pass


def dateien(pfade):
    """Nur LST- und TUBX-Dateien aus einer Liste von Pfaden."""
    return [p for p in pfade if str(p).lower().endswith(ENDUNGEN)]


def lst_dateien(pfade):
    """Nur LST-Dateien; TUBX geht seit 20.11.2026 wie eine STEP durch den STEP-Import (step_messung/step_tubx.py)."""
    return [p for p in pfade if str(p).lower().endswith(".lst")]


def _zahl(text):
    try:
        return float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------------------ LST
def _werte(zeile):
    return [w.strip() for w in next(csv.reader(io.StringIO(zeile), quotechar="'", skipinitialspace=True))]


def _abschnitte(text):
    """[(Name, [dict je DA-Zeile])] in Dateireihenfolge."""
    out, name, spalten, daten = [], None, [], []
    for roh in text.splitlines():
        z = roh.rstrip()
        if z.startswith("BEGIN_"):
            name, spalten, daten = z[6:].strip(), [], []
        elif name and z.startswith("ENDE_"):
            out.append((name, [dict(zip(spalten, _werte(d))) for d in daten]))
            name = None
        elif name is None:
            continue
        elif z.startswith("MM,AT"):
            f = _werte(z)
            spalten.append(f[7] if len(f) > 7 else "")
        elif z.startswith("DA,"):
            daten.append(z[3:])
        elif z.startswith("*") and daten:
            daten[-1] += z[1:].strip()
    return out


def _einstiche(text):
    n, an = 0, False
    for m in re.finditer(r"TC_LASER_(ON|OFF)\(", text):
        if m.group(1) == "ON":
            n += not an
            an = True
        else:
            an = False
    return n


def _profil(tt, hinweise):
    """Profilform und Maße aus TUBE_TECH."""
    h, b = _zahl(tt.get("Hoehe (Rechteckrohr)")) or 0.0, _zahl(tt.get("Breite (Rechteckrohr)")) or 0.0
    d = _zahl(tt.get("(Huellkreis-)Durchmesser (Rechteck-/Rundrohr)")) or 0.0
    wand = _zahl(tt.get("Wandstaerke")) or 0.0
    radius = _zahl(tt.get("Eckenradius (Rechteckrohr)")) or 0.0
    q = str(tt.get("Querschnitt") or "").strip()
    if h > 0 and b > 0:
        if abs(h - b) < 0.05:
            return "Quadratrohr", b, b, wand, radius
        return "Rechteckrohr", max(h, b), min(h, b), wand, radius
    if d > 0:
        return "Rundrohr", d, None, wand, None
    hinweise.append(f"Querschnitt {q or '?'} nicht erkannt (Rohr-ID {tt.get('Rohr-ID') or '?'})")
    return None, None, None, wand, None


# TUBE_PART_TIMES: berechnet (TruTops) und gemessen (füllt die Maschine nach dem Lauf, Patrick 20.11.2026)
ANTEILE = (("anschnitt", "First Cut"), ("konturen", "Contour"), ("abschnitt", "Cut Off"))


def _zeitanteile(z):
    """({anschnitt, konturen, abschnitt} berechnet, dasselbe gemessen oder None, Anzahl Messungen)."""
    ber = {k: _zahl(z.get(f"Calculated {t} Machine Time")) for k, t in ANTEILE}
    n = int(_zahl(z.get("Number Of Recorded Part Times")) or 0)
    mittel = {k: _zahl(z.get(f"Average Measured {t} Machine Time")) for k, t in ANTEILE}
    letzt = {k: _zahl(z.get(f"Last Program Run Measured {t} Machine Time")) for k, t in ANTEILE}
    gem = mittel if n and any(mittel.values()) else letzt if any(letzt.values()) else None
    return ({k: v for k, v in ber.items() if v is not None} or None), gem, n


def _laser_an(zeilen, teile):
    """(Laser an, Verfahren) [s] je Teil aus CONSUMPTION_TIMES Gruppe 2 (Zeit je Laserleistung; 0 W = Verfahren ohne
    Strahl). Beide zusammen sind die berechnete Maschinenzeit (P20: 12,7 + 9,8 = 22,5 s); sonst (None, None)."""
    an = aus = 0.0
    gefunden = False
    for z in zeilen:
        if str(z.get("ConsumptionGroup")).strip() != "2":
            continue
        t, w = _zahl(z.get("OnTime")) or 0.0, _zahl(z.get("LaserPower")) or 0.0
        gefunden = True
        if w > 0:
            an += t
        else:
            aus += t
    if not gefunden or an <= 0:
        return None, None
    return round(an / max(teile, 1), 2), round(aus / max(teile, 1), 2)


def _strahl(zeilen, teile):
    """Strahl-Ein-Zeit [s] je Teil aus CONSUMPTION_TIMES (Verbrauchsgruppe 1 = Schneidgas, OnTime) oder None."""
    s = sum(_zahl(z.get("OnTime")) or 0.0 for z in zeilen if str(z.get("ConsumptionGroup")).strip() == "1")
    return round(s / max(teile, 1), 2) if s else None


def qualitaet(t):
    """Datenqualität eines gelesenen Teils fürs Lernen: (Stufe, [Gründe]); Stufe VOLL, TEIL oder UNPLAUSIBEL."""
    gruende, unpl = [], []
    for f, titel in (("profilform", "Profil"), ("laenge", "Länge"), ("schneidweg", "Schneidweg"),
                     ("einstiche", "Einstiche"), ("zeiten_berechnet", "Zeiten")):
        if not t.get(f):
            gruende.append(f"{titel} fehlt")
    if t.get("teile_im_programm", 1) > 1:
        gruende.append("mehrere Teile in einem Programm (Schneidweg/Einstiche geteilt)")
    if t.get("laenge") and t.get("a") and t.get("schneidweg"):
        umfang = (3.14159 * t["a"]) if t.get("profilform") == "Rundrohr" else 2 * (t["a"] + (t.get("b") or t["a"]))
        if t["schneidweg"] < 0.9 * umfang:
            unpl.append(f"Schneidweg {t['schneidweg']:.0f} mm kleiner als ein Trennschnitt ({umfang:.0f} mm)")
    zb = t.get("zeiten_berechnet") or {}
    if zb and not zb.get("konturen") and not zb.get("abschnitt"):
        unpl.append("Zeit 0")
    if unpl:
        return UNPLAUSIBEL, unpl + gruende
    return (TEIL if gruende else VOLL), gruende


VOLL, TEIL, UNPLAUSIBEL = "vollständig", "Teilwerte fehlen", "unplausibel"


def lst_lesen(pfad=None, text=None, name=None):
    """Teile aus einer LST-Datei (ein Programm oder eine Job-Liste)."""
    if text is None:
        try:
            roh = Path(pfad).read_bytes()
        except OSError as e:
            raise TrumpfFehler(f"Die Datei lässt sich nicht öffnen:\n{pfad}\n\n{e}") from e
        try:
            text = roh.decode("utf-8")
        except UnicodeDecodeError:
            text = roh.decode("cp1252", errors="replace")
    name = name or (Path(pfad).name if pfad else "LST")
    if "BEGIN_EINRICHTEPLAN_INFO" not in text:
        raise TrumpfFehler(f"{name}: keine TRUMPF-LST (Abschnitt EINRICHTEPLAN_INFO fehlt).")
    blöcke = re.split(r"(?m)^BD\s*$", text)
    auftrag = {}
    for b in blöcke:
        for abschnitt, zeilen in _abschnitte(b):
            if abschnitt == "FERTIGUNG_AUFTRAG_TMP":
                for z in zeilen:
                    if z.get("Programmname"):
                        auftrag[z["Programmname"]] = z
    teile = []
    for b in blöcke:
        if "BEGIN_EINRICHTEPLAN_INFO" not in b:
            continue
        ab = {}
        for abschnitt, zeilen in _abschnitte(b):
            ab.setdefault(abschnitt, []).extend(zeilen)
        info = (ab.get("EINRICHTEPLAN_INFO") or [{}])[0]
        tt = (ab.get("TUBE_TECH") or [{}])[0]
        prog = info.get("Programmnummer") or Path(name).stem
        hinweise = []
        form, a, b_, wand, radius = _profil(tt, hinweise)
        pt = ab.get("TUBE_PART_TECH") or [{}]
        zeiten = {z.get("Data Set Name"): z for z in ab.get("TUBE_PART_TIMES") or []}
        nc = b[b.find("BEGIN_PROGRAMM"):] if "BEGIN_PROGRAMM" in b else ""
        weg, stiche = _zahl(info.get("Cutting length")), _einstiche(nc) if nc else None
        bahn = _bahn(b, prog)
        laser_an, verfahren = _laser_an(ab.get("CONSUMPTION_TIMES") or [], len(pt))
        if len(pt) > 1:
            hinweise.append(f"{len(pt)} Teile in einem Programm: Schneidweg und Einstiche gleichmäßig geteilt")
        fa = auftrag.get(prog) or {}
        werkstoff = tt.get("Material") or info.get("Material-ID") or ""
        for t in pt:
            laenge = _zahl(t.get("Work Part Length")) or _zahl(t.get("OriginalProgrammedTubeLength")) \
                or _zahl(t.get("Rohrlaenge (Soll)"))
            z = zeiten.get(t.get("Tabellenidentifikator")) or (list(zeiten.values())[0] if len(zeiten) == 1 else {})
            zeit = sum(_zahl(z.get(k)) or 0.0 for k in ("Calculated First Cut Machine Time",
                                                       "Calculated Contour Machine Time",
                                                       "Calculated Cut Off Machine Time")) or None
            berechnet, gemessen, messungen = _zeitanteile(z)
            if zeit is None and _zahl(info.get("Maschinenzeit")):
                zeit = _zahl(info.get("Maschinenzeit")) * 60.0 / len(pt)
            teile.append(dict(
                quelle=name, programm=prog, artikel=fa.get("FertAuftrBez") or prog,
                auftrag=fa.get("Jobname") or "", stueck=int(_zahl(fa.get("SollAnzahl")) or 0) or None,
                profilform=form, a=a, b=b_, wand=wand, radius=radius,
                laenge=round(laenge, 1) if laenge else None, werkstoff=werkstoff,
                werkstoff_nr="", schneidweg=round(weg / len(pt), 1) if weg else None,
                einstiche=round(stiche / len(pt)) if stiche else None, zeit_s=round(zeit, 1) if zeit else None,
                maschine=info.get("viewer name machine") or info.get("Maschine") or "",
                stangenlaenge=_zahl(tt.get("Rohrlaenge")), kg_m=_zahl(tt.get("Mass Per Meter")),
                datum=info.get("Datum") or "", hinweise=list(hinweise),
                # Lernsystem (produktion_lst.py): Zeitanteile berechnet/gemessen, Strahl-Ein, Maschinenzeit
                teil_nr=pt.index(t) + 1, teile_im_programm=len(pt), zeiten_berechnet=berechnet,
                zeiten_gemessen=gemessen, messungen=messungen,
                maschinenzeit_s=round(_zahl(info.get("Maschinenzeit")) * 60.0, 1)
                if _zahl(info.get("Maschinenzeit")) else None,
                strahl_s=_strahl(ab.get("CONSUMPTION_TIMES") or [], len(pt)),
                laser_an_s=laser_an, verfahren_s=verfahren))
            _bahn_werte(teile[-1], bahn, len(pt), weg)
    if not teile:
        raise TrumpfFehler(f"{name}: kein Teil im Programm gefunden.")
    return teile


def _bahn(block, prog):
    """Schneidweg aus dem NC-Teil (lst_bahn) für ein Programm-Block oder None."""
    try:
        from . import lst_bahn
        progs = lst_bahn.programme(block, prog)
    except Exception:       # noqa: BLE001 – Zusatz (Patrick 24.11.2026); ohne ihn bleiben die LST-Werte wie bisher
        from . import protokoll
        protokoll.warnung("Schneidweg der LST nicht lesbar")
        return None
    return progs[0] if progs else None


def _bahn_werte(t, bahn, teile, weg):
    """Teil um die Werte aus dem NC-Schneidweg ergänzen: Schnittlänge am Material (wird Schneidweg), Maschinenweg
    laut LST, Anfahrt, Restzerteilung, Konturen je Klasse (Hüllmaß, Länge) für die Konturklassen der Kalkulation."""
    t["maschinenweg"] = round(weg / teile, 1) if weg else None
    if bahn is None:
        return
    if weg and not 0.3 * weg <= bahn["schnittlaenge"] <= 1.05 * weg:
        return      # Schneidweg passt nicht zum Maschinenweg (NC-Teil unvollständig): Werte der LST bleiben wie bisher
    from . import lst_bahn
    t["schnittlaenge_material"] = round(bahn["schnittlaenge"] / teile, 1)
    t["schneidweg"] = t["schnittlaenge_material"] or t["schneidweg"]
    t["anfahrt"], t["restzerteilung"] = round(bahn["anfahrt"] / teile, 1), round(bahn["restzerteilung"] / teile, 1)
    t["konturen"] = bahn["einstiche"]
    t["halbspalt"] = bahn.get("halbspalt")
    if teile == 1:
        t["enden"], t["innen"] = lst_bahn.konturliste(bahn)
    if t.get("schnittlaenge_material") and weg:
        t["hinweise"].append(f"Schneidweg am Material {t['schnittlaenge_material']:.0f} mm (Maschinenweg laut LST "
                             f"{weg / teile:.0f} mm mit Anfahrten und Ecken)")


# Programmdaten je Datei (Name ohne Endung, klein): beim Übernehmen aus der Messung in positionen.step_merkmale
# ['programm'] (Laser-an-Zeit, TRUMPF-Zeit, Schneidweg); step.step_dateien trägt LST-Dateien (auch neben einer TUBX) ein
PROGRAMMDATEN = {}
_PROGRAMM_FELDER = ("quelle", "programm", "laser_an_s", "verfahren_s", "zeit_s", "maschinenweg", "schnittlaenge_material",
                    "einstiche", "stueck", "maschine")


def programm_merken(pfad, auch=()):
    """LST-Datei lesen und ihre Programmdaten unter ihrem Namen (und den Namen in auch, z. B. der TUBX daneben)
    merken, wenn sie genau ein Teil enthält. Ergebnis: die Daten oder None."""
    try:
        teile = lst_lesen(pfad)
    except TrumpfFehler:
        return None
    if len(teile) != 1:
        return None
    d = {k: teile[0].get(k) for k in _PROGRAMM_FELDER if teile[0].get(k) not in (None, "")}
    for name in (Path(pfad).stem, *auch):
        PROGRAMMDATEN[str(name).lower()] = d
    return d


def programmdaten(datei):
    """Gemerkte Programmdaten zur Datei (Name oder Pfad einer gemessenen Datei) oder None."""
    if not datei:
        return None
    return PROGRAMMDATEN.get(Path(str(datei)).stem.lower())


# ----------------------------------------------------------------------------------------------------------- TUBX
_UEBERSPRINGEN = {"VerticesOfTriangleMesh", "MeshIndices", "ProfileEdgeSections", "ProfileSections",
                  "LaserTechnologySections", "InnerAreas", "AlternateAreas"}


def _bson(b, i=0, ende=None):
    """Kleiner BSON-Leser (nur was TUBX braucht); große Netz-Daten werden übersprungen."""
    n = struct.unpack_from("<i", b, i)[0]
    ende, i, out = i + n - 1, i + 4, {}
    while i < ende:
        art = b[i]
        j = b.index(b"\x00", i + 1)
        key = b[i + 1:j].decode("utf-8", "replace")
        i = j + 1
        if art == 0x01:
            out[key] = struct.unpack_from("<d", b, i)[0]
            i += 8
        elif art in (0x02, 0x0D, 0x0E):
            ln = struct.unpack_from("<i", b, i)[0]
            out[key] = b[i + 4:i + 3 + ln].decode("utf-8", "replace")
            i += 4 + ln
        elif art in (0x03, 0x04):
            ln = struct.unpack_from("<i", b, i)[0]
            if key not in _UEBERSPRINGEN:
                out[key] = _bson(b, i)
            i += ln
        elif art == 0x05:
            ln = struct.unpack_from("<i", b, i)[0]
            i += 5 + ln
        elif art == 0x07:
            i += 12
        elif art == 0x08:
            out[key] = bool(b[i])
            i += 1
        elif art in (0x09, 0x11, 0x12):
            out[key] = struct.unpack_from("<q", b, i)[0]
            i += 8
        elif art == 0x10:
            out[key] = struct.unpack_from("<i", b, i)[0]
            i += 4
        elif art in (0x0A, 0x06, 0xFF, 0x7F):
            out[key] = None
        elif art == 0x13:
            i += 16
        else:
            break
    return out


def _suchen(d, schluessel):
    if isinstance(d, dict):
        if schluessel in d and not isinstance(d[schluessel], dict):
            return d[schluessel]
        for v in d.values():
            w = _suchen(v, schluessel)
            if w is not None:
                return w
    return None


def _zahl_einheit(text):
    m = re.match(r"\s*([\d.,]+)", str(text or ""))
    return _zahl(m.group(1)) if m else None


def tubx_lesen(pfad=None, roh=None, name=None):
    """Teil aus einer TUBX-Datei (TubeCAM). Schneidweg, Einstiche und Zeit nur aus einer LST daneben."""
    name = name or (Path(pfad).name if pfad else "TUBX")
    try:
        z = zipfile.ZipFile(io.BytesIO(roh) if roh is not None else pfad)
    except (OSError, zipfile.BadZipFile) as e:
        raise TrumpfFehler(f"{name}: keine TUBX-Datei (ZIP) oder beschädigt.\n\n{e}") from e
    with z:
        namen = z.namelist()
        app = next((n for n in namen if n.lower().endswith("tubeprops/app.xml")), None)
        if not app:
            raise TrumpfFehler(f"{name}: keine TUBX-Datei (tubeProps/app.xml fehlt).")
        wurzel = ElementTree.fromstring(z.read(app))
        def feld(tag):
            el = next((e for e in wurzel.iter() if e.tag.rsplit("}", 1)[-1] == tag), None)
            return (el.text or "").strip() if el is not None else ""
        wp = {}
        for n in namen:
            if re.search(r"Task3D/Workpiece[^/]*\.bson$", n):
                try:
                    wp = _bson(z.read(n))
                except (struct.error, ValueError, IndexError):
                    wp = {}
                break
    hinweise = []
    pid, art = feld("profileId"), feld("profileType")
    wand = _zahl_einheit(feld("thickness")) or 0.0
    form = PROFILART.get(art.lower())
    # Profil-ID wie 1_600X400X40_1_20: Maße in 1/10 mm (Breite X Höhe X Eckenradius)
    m = re.match(r"\d+_(\d+)X(\d+)(?:X(\d+))?", pid or "")
    a = b = radius = None
    if m:
        x, y = int(m.group(1)) / 10.0, int(m.group(2)) / 10.0
        radius = int(m.group(3)) / 10.0 if m.group(3) else None
        a, b = max(x, y), min(x, y)
        if form == "Rechteckrohr" and abs(a - b) < 0.05:
            form = "Quadratrohr"
        if form == "Rundrohr":
            b = radius = None
    if form is None or a is None:
        hinweise.append(f"Profil {pid or '?'} ({art or '?'}) nicht erkannt")
    laenge = _suchen(wp, "WorkpieceLength")
    prog = Path(name).stem
    nr = feld("material")
    return [dict(quelle=name, programm=prog, artikel=prog, auftrag="", stueck=None, profilform=form, a=a, b=b,
                 wand=wand, radius=radius, laenge=round(laenge, 1) if isinstance(laenge, (int, float)) else None,
                 werkstoff=nr, werkstoff_nr=nr, schneidweg=None, einstiche=None, zeit_s=None,
                 maschine=feld("machineId"), stangenlaenge=None, kg_m=None,
                 gewicht=_suchen(wp, "Weight"), kunde=_suchen(wp, "CustomerName") or "", datum="",
                 hinweise=hinweise)]


# ---------------------------------------------------------------------------------------------------- zusammen
def lesen(pfade):
    """Teile aus LST- und TUBX-Dateien; TUBX mit gleichnamigem Programm in einer LST (gewählt oder im selben
    Ordner) bekommt deren Schneidweg, Einstiche, Zeit und Sollanzahl. Ergebnis: (teile, fehler)."""
    teile, fehler, lst_progs = [], [], {}
    pfade = [Path(p) for p in pfade]
    for p in pfade:
        if p.suffix.lower() == ".lst":
            try:
                for t in lst_lesen(p):
                    teile.append(t)
                    lst_progs.setdefault(t["programm"].lower(), t)
            except TrumpfFehler as e:
                fehler.append(str(e))
    for p in pfade:
        if p.suffix.lower() != ".tubx":
            continue
        try:
            tx = tubx_lesen(p)[0]
        except TrumpfFehler as e:
            fehler.append(str(e))
            continue
        lst = lst_progs.get(tx["programm"].lower())
        if lst is None:
            nachbar = p.with_suffix(".lst")
            if not nachbar.exists():
                nachbar = next((q for q in p.parent.glob("*") if q.suffix.lower() == ".lst"
                                and q.stem.lower() == p.stem.lower()), None)
            if nachbar is not None and nachbar.exists():
                try:
                    lst = next((t for t in lst_lesen(nachbar) if t["programm"].lower() == tx["programm"].lower()),
                               None)
                except TrumpfFehler:
                    lst = None
                if lst is not None:
                    teile.append(dict(lst, quelle=f"{p.name} + {nachbar.name}", gewicht=tx.get("gewicht"),
                                      kunde=tx.get("kunde") or ""))
                    lst_progs[lst["programm"].lower()] = teile[-1]
                    continue
            tx["hinweise"].append("ohne LST: Schneidweg, Einstiche und TRUMPF-Zeit fehlen (LST mit gleichem Namen "
                                  "dazulegen)")
            teile.append(tx)
        else:       # schon aus der LST: nur Gewicht/Kunde ergänzen
            lst["gewicht"], lst["kunde"] = tx.get("gewicht"), tx.get("kunde") or ""
            lst["quelle"] = f"{lst['quelle']} + {p.name}"
    return teile, fehler


def werkstoff_wort(t):
    """Suchwort für den Werkstoff der Stammdaten (St37 → S235)."""
    w = str(t.get("werkstoff") or "").strip()
    return WERKSTOFF.get(w.lower(), w)


def text(t, zahl=lambda x, n=1: f"{x:.{n}f}".replace(".", ",")):
    """Kurzbeschreibung eines Teils für Vorschau und Bemerkung."""
    if t.get("profilform") == "Rundrohr":
        prof = f"Ø{zahl(t['a'])}×{zahl(t['wand'])}"
    elif t.get("a"):
        prof = f"{zahl(t['a'])}×{zahl(t['b'])}×{zahl(t['wand'])}"
    else:
        prof = "?"
    teile = [f"{t.get('profilform') or 'Profil'} {prof}", f"L {zahl(t['laenge'])} mm" if t.get("laenge") else "",
             f"Schneidweg {zahl(t['schneidweg'], 0)} mm" if t.get("schneidweg") else "",
             f"{t['einstiche']} Einstiche" if t.get("einstiche") else "",
             f"TRUMPF {zahl(t['zeit_s'])} s/Teil" if t.get("zeit_s") else ""]
    return ", ".join(x for x in teile if x)
