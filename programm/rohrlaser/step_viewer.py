"""STEP-Viewer: Kern ohne Qt (Master-Auftrag Patrick 24.11.2026 „STEP Import Engine 2.0 – CAD-Kern erweitern,
Berechnungen beschleunigen und eigenen STEP-Viewer entwickeln“).

Der Viewer ist ein eigenes Fenster (step_viewer_fenster.py), das eine STEP-Datei ohne Angebot öffnet. Er rechnet
nichts selbst: die Geometrie misst dieselbe STEP-Messung wie der Import (STEP-Import.exe, OpenCascade, eigener
Prozess), mit denselben Messargumenten und demselben Zwischenspeicher. Darum zeigt der Viewer genau die Werte, die
eine Angebotsposition übernimmt, und ein „Übernehmen“ danach misst nicht noch einmal (Treffer im Zwischenspeicher).

Reihenfolge (Abschnitt 8 des Auftrags, Viewer und Kalkulation getrennt):

1. Kopf der Datei lesen (step_vorschau, nur Text, Sekundenbruchteile): Schema (AP203/AP214/AP242), Einheit,
   Baugruppen, Körper, vermutete Normteile. Das ist sofort sichtbar.
2. Messen (STEP-Messung im Hintergrund): Profil, Länge, Wand, Schneidweg, Konturen, Normteile, Netz je Körper.
3. Netze erst laden, wenn ein Körper gezeigt wird (lazy), die Gesamtansicht setzt alle zusammen.

Die Kontur je Linienzug kommt aus der Messung (netz['lk'] = Nummer in konturen_liste, ab 0.9.468); damit zeigt ein
Klick auf eine Linie die Werte genau dieser Kontur. Ältere Netze ohne 'lk' zeigen Konturen ohne Zuordnung.

Alle Zahlen hier kommen aus der Messung (CAD-Geometrie). Das 3D-Netz ist nur Anzeige; die Gegenprobe „Linie im 3D“
misst die Länge der Linienzüge des Netzes und vergleicht sie mit der Schnittlänge der Messung (unabhängige
Kontrolle, Abschnitt 13: „Schneidwege unabhängig gegenprüfen, Viewer und Kalkulation vergleichen“).
"""
import json
import math
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import konturrolle as kr

STANDARD, EXPERTE = "Standard", "Experte"
STUFEN = (STANDARD, EXPERTE)
STUFE_TEXT = {STANDARD: "Standard: vollständige Messung wie beim Import, 3D-Grunddarstellung",
              EXPERTE: "Experte: wie Standard, dazu feineres 3D-Netz (nur Anzeige, Messwerte gleich)"}
ZEITLIMIT_S = 1800           # Messung höchstens so lange (große Baugruppen)
KOERPER_ZEITLIMIT_S = 300    # je Körper (wie --zeitlimit beim Import mit Aufsicht)
KONTUR = "kontur:"           # Kennung einer Kontur im Netz (netz 'li' der Viewer-Kopie): kontur:<Nummer>
TEIL = "teil:"               # Kennung eines Körpers in der Gesamtansicht (netz 'ti'): teil:<Nummer der Messwerte>
GEGENPROBE_TOL = 0.02        # Linie im 3D darf so viel (relativ) von der Schnittlänge abweichen …
GEGENPROBE_MIN = 0.5         # … mindestens diese mm (Netz ist auf 0,01 mm gerundet, Kreise als Sehnen)

# Gruppen im Bauteilbaum
ROHR, BLECH, DREHFRAES, NORMTEIL, FEHLER = "Rohr/Profil", "Blech", "Dreh-/Frästeil", "Normteil/Zukaufteil", \
    "nicht messbar"
GRUPPEN = (ROHR, BLECH, DREHFRAES, NORMTEIL, FEHLER)

# Konturfarben (Ansicht „Konturen nach Art“): Art der Kontur -> (Legende, Farbe)
KONTURFARBEN = (
    ("Bohrung", "Bohrung", "#1F6FD1"),
    ("Langloch", "Langloch / Schlitz", "#00A3A3"),
    ("Rechteck", "Rechteck / Ausschnitt", "#8E44AD"),
    ("Sonder", "Sonderkontur", "#E91E63"),
    ("Ende", "Ende gerade", "#F28E2B"),
    ("Schräg", "Gehrung / Schrägschnitt", "#C62828"),
    ("Gravur", "Gravur", "#2E7D32"),
    ("Nicht", "nicht gelasert", "#7F8C8D"),
)
FARBE_JE = {k: f for k, _, f in KONTURFARBEN}
# Konturfarben nach Rolle (konturrolle.ROLLEN, Master-Auftrag 25.11.2026): Anfang und Ende verschieden
ROLLENFARBEN = (
    ("Anfangsschnitt", "Anfangsschnitt (Ende A)", "#F28E2B"),
    ("Endeschnitt", "Endeschnitt (Ende B)", "#C62828"),
    ("Anschlusskontur", "Anschlusskontur (Sattel)", "#6D4C41"),
    ("Innenkontur", "Innenkontur", "#1F6FD1"),
    ("Durchbruch", "Durchbruch (beide Wände)", "#00A3A3"),
    ("Ausschnitt", "Ausschnitt", "#8E44AD"),
    ("Freiformkontur", "Freiformkontur", "#E91E63"),
    ("nicht eindeutig", "nicht eindeutig", "#7F8C8D"),
    ("kein Schnitt", "Gravur / nicht gelasert", "#2E7D32"),
)
ROLLE_FARBE = {k: f for k, _, f in ROLLENFARBEN}
# Farben nach Schneidbarkeit (konturrolle.STUFEN)
STUFENFARBEN = ((1, "1 eindeutig", "#2E7D32"), (2, "2 wahrscheinlich", "#1F6FD1"), (3, "3 problematisch", "#E67E22"),
                (4, "4 nicht sicher", "#C62828"))
FARBEN_NACH = ("Art", "Rolle", "Schneidbarkeit")

_SCHEMA = (("AP242", "AP242 (ISO 10303-242)"), ("MANAGED_MODEL_BASED_3D_ENGINEERING", "AP242 (ISO 10303-242)"),
           ("AP203_CONFIGURATION_CONTROLLED_3D_DESIGN", "AP203 2. Ausgabe (ISO 10303-203)"),
           ("CONFIG_CONTROL_DESIGN", "AP203 (ISO 10303-203)"), ("AUTOMOTIVE_DESIGN", "AP214 (ISO 10303-214)"),
           ("AP214", "AP214 (ISO 10303-214)"))


# ------------------------------------------------------------------ Kopf der Datei (ohne Messung)
def schema_name(schema):
    """Anwendungsprotokoll aus FILE_SCHEMA ('AUTOMOTIVE_DESIGN { 1 0 10303 214 … }' -> 'AP214 …'); unbekannt: der
    Text selbst, leer: ''."""
    s = str(schema or "").upper()
    for schl, name in _SCHEMA:
        if schl in s:
            return name
    return str(schema or "").split("{")[0].strip()


def kopf(pfad):
    """Übersicht der Datei vor dem Messen (step_vorschau, nur Text): dict mit datei, mb, schema, ap, einheit,
    baugruppen, bauteile, einbauten, gleiche, koerper, flaechen, zukauf, messzeit; IGES/TUBX/BLM nur Name und Größe."""
    from . import step_vorschau
    pfad = Path(pfad)
    if pfad.suffix.lower() not in (".step", ".stp"):
        try:
            mb = round(pfad.stat().st_size / 1e6, 1)
        except OSError as f:
            return dict(datei=pfad.name, fehler=str(f))
        return dict(datei=pfad.name, mb=mb, schema="", ap=pfad.suffix.upper().lstrip("."), einheit="")
    u = step_vorschau.datei(pfad)
    u["ap"] = schema_name(u.get("schema"))
    return u


def kopf_zeilen(u):
    """Zeilen (Titel, Wert) für das Feld „Datei“."""
    if not u:
        return []
    if u.get("fehler"):
        return [("Datei", u.get("datei") or ""), ("Fehler", u["fehler"])]
    from . import step_vorschau
    out = [("Datei", u.get("datei") or ""), ("Größe", f"{_dez(u.get('mb') or 0, 1)} MB")]
    if u.get("ap"):
        out.append(("Format", u["ap"]))
    if u.get("einheit"):
        out.append(("Einheit der Datei", u["einheit"] + ("" if u["einheit"] == "mm" else " (wird in mm umgerechnet)")))
    if "koerper" in u:
        out += [("Baugruppen", str(u.get("baugruppen") or 0)), ("Bauteile", str(u.get("bauteile") or 0)),
                ("Einbauten", str(u.get("einbauten") or 0)), ("Körper", str(u.get("koerper") or 0)),
                ("Flächen", str(u.get("flaechen") or 0))]
        if u.get("zukauf"):
            out.append(("Normteile laut Name", ", ".join(f"{n}× {k}" for k, n in sorted(u["zukauf"].items()))))
        if u.get("messzeit"):
            out.append(("Messzeit geschätzt", step_vorschau.dauer_text(u["messzeit"])))
    return out


# ------------------------------------------------------------------ Messung
class Messung:
    """Ergebnis einer Messung im Viewer: messwerte (Liste von dicts wie beim Import), json (STEP-JSON), ordner
    (temporär, mit den Netzen; aufraeumen() löscht ihn), zeiten (Sekunden je Schritt), fehler (Text oder '')."""

    def __init__(self, pfad, ordner, stufe=STANDARD):
        self.pfad, self.ordner, self.stufe = Path(pfad), Path(ordner), stufe
        self.messwerte, self.json, self.zeiten, self.fehler, self.rc = [], {}, {}, "", None
        self._netze = {}

    def netz(self, i):
        """Netz des Körpers i (dict) oder None; wird beim ersten Zugriff aus der Datei gelesen (lazy)."""
        if i in self._netze:
            return self._netze[i]
        m = self.messwerte[i] if 0 <= i < len(self.messwerte) else {}
        netz = None
        if m.get("netz"):
            uhr = time.perf_counter()
            try:
                netz = json.loads((self.ordner / "netze" / m["netz"]).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                netz = None
            self.zeiten["netz_laden_s"] = self.zeiten.get("netz_laden_s", 0.0) + time.perf_counter() - uhr
        self._netze[i] = netz
        return netz

    def koerper_json(self, i):
        """Eintrag des Körpers im STEP-JSON (Volumen, Hülle, Sicherheit …) oder {}."""
        m = self.messwerte[i] if 0 <= i < len(self.messwerte) else {}
        for d in (self.json or {}).get("dateien") or ():
            if d.get("datei") == m.get("datei"):
                for k in d.get("koerper") or ():
                    if str(k.get("nr")) == str(m.get("koerper")):
                        return k
        return {}

    def aufraeumen(self):
        shutil.rmtree(self.ordner, ignore_errors=True)


def mess_aufruf(befehl, pfad, ordner, args=None, stufe=STANDARD):
    """Aufruf der STEP-Messung für den Viewer (Liste für subprocess): Messwerte, JSON und Netze in ordner; args wie
    beim Import (anfrage_vorab.vorschau_argumente: Zwischenspeicher, Grenzwerte, Flachstahl); Experte: feines Netz."""
    ordner = Path(ordner)
    (ordner / "liste.txt").write_text(str(pfad), encoding="utf-8")
    args = list(args or ["--prozesse", "0"])
    if "--zeitlimit" not in args:
        args += ["--zeitlimit", str(KOERPER_ZEITLIMIT_S)]       # Fortschritt je Körper, hängende Körper melden
    return (list(befehl) + ["--liste", str(ordner / "liste.txt"), "--ausgabe", str(ordner / "messwerte.txt"),
                            "--json", str(ordner / "ergebnis.json"), "--netze", str(ordner / "netze")] + args
            + (["--netze-fein"] if stufe == EXPERTE else []))


def fortschritt(zeile):
    """Fortschrittszeile der Messung als dict (koerper, koerper_n, phase) oder None."""
    zeile = zeile.strip()
    if not zeile.startswith("{"):
        return None
    try:
        d = json.loads(zeile)
    except ValueError:
        return None
    return d if isinstance(d, dict) and "koerper_n" in d else None


def messen(befehl, pfad, args=None, stufe=STANDARD, melden=None, abbrechen=None, zeitlimit=ZEITLIMIT_S):
    """STEP-Datei messen (läuft im Hintergrund-Thread des Viewers). melden(dict) bekommt den Fortschritt,
    abbrechen() -> True beendet die Messung. Ergebnis: Messung (fehler gesetzt, wenn nichts gemessen wurde)."""
    from . import step
    ordner = Path(tempfile.mkdtemp(prefix="step_viewer_"))
    mes = Messung(pfad, ordner, stufe)
    if not befehl:
        mes.fehler = "Die STEP-Messung (STEP-Import.exe) fehlt im Programmordner."
        return mes
    uhr = time.perf_counter()
    aufruf = mess_aufruf(befehl, pfad, ordner, args, stufe)
    try:
        proz = subprocess.Popen(aufruf, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as f:
        mes.fehler = f"STEP-Messung nicht startbar: {f}"
        return mes
    zeiten = {}
    try:
        for zeile in proz.stdout:
            if zeile.startswith("ZEITEN "):
                try:
                    zeiten = json.loads(zeile[7:])
                except ValueError:
                    zeiten = {}
                continue
            d = fortschritt(zeile)
            if d is not None and melden is not None:
                melden(d)
            if (abbrechen is not None and abbrechen()) or time.perf_counter() - uhr > zeitlimit:
                proz.kill()
                mes.fehler = "Messung abgebrochen." if abbrechen is not None and abbrechen() else \
                    f"Messung nach {zeitlimit // 60} min abgebrochen (Zeitlimit)."
                break
    finally:
        proz.stdout.close()
        mes.rc = proz.wait()
    gesamt = time.perf_counter() - uhr
    teil = ((zeiten.get("dateien") or {}).get(Path(pfad).name) or {})
    schritte = teil.get("schritte") or {}
    mes.zeiten = dict(messung_s=round(gesamt, 3), lesen_s=schritte.get("lesen_s"), messen_s=schritte.get("messen_s"),
                      abschluss_s=schritte.get("abschluss_s"), aus_speicher=not teil and mes.rc == 0)
    if mes.fehler:
        return mes
    try:
        mes.messwerte = step.lies_messwerte(ordner / "messwerte.txt")
    except OSError:
        mes.messwerte = []
    try:
        mes.json = json.loads((ordner / "ergebnis.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mes.json = {}
    if mes.messwerte:
        step.struktur_anhaengen(mes.messwerte, ordner / "ergebnis.json")
    if not mes.messwerte:
        mes.fehler = "Die Datei enthält keine messbaren Körper." if mes.rc in (0, 1) else \
            f"Die STEP-Messung ist mit Code {mes.rc} beendet worden."
    return mes


# ------------------------------------------------------------------ Einordnung je Körper
def _f(m, n):
    try:
        return float(str(m.get(n) or 0).replace(",", "."))
    except ValueError:
        return 0.0


def _dez(x, stellen=1):
    return f"{x:.{stellen}f}".replace(".", ",")


def _mm(x):
    return f"{_dez(x, 1 if abs(x - round(x)) > 1e-6 else 0)} mm" if x else ""


def normteil(m):
    """Einordnung als Norm-/Zukaufteil (zukaufteile.einordnen: Norm im Namen, an der Form erkannt, Begriff) oder
    None. Von Hand im Viewer entschieden: _zukauf_hand bzw. _fertigung_hand."""
    from . import zukaufteile
    if m.get("_fertigung_hand"):
        return None
    if m.get("_zukauf_hand"):
        return m.get("_zukaufteil") or dict(kategorie=m["_zukauf_hand"], vertrauen=zukaufteile.SICHER,
                                            grund="von Hand")
    return zukaufteile.einordnen(m)


def gruppe(m):
    """Gruppe im Bauteilbaum: Rohr/Profil, Blech, Dreh-/Frästeil, Normteil/Zukaufteil oder nicht messbar. Sicher
    erkannte Normteile (Name/Form) sind Normteile; ein bloßer Vorschlag bleibt in seiner gemessenen Art."""
    from . import step, zukaufteile
    if m.get("fehler") or not m.get("profilform") and not m.get("bauteiltyp"):
        return FEHLER
    nt = normteil(m)
    if nt and nt.get("vertrauen") == zukaufteile.SICHER:
        return NORMTEIL
    g = step.art_gruppe(m)
    return {step.ART_BLECH: BLECH, step.ART_DREHFRAES: DREHFRAES}.get(g, ROHR)


def name(m):
    return str(m.get("bauteil") or m.get("artikel") or f"Körper {m.get('koerper') or ''}").strip()


def _sicherheit(m):
    out = {}
    for teil in str(m.get("sicherheit") or "").split(";"):
        k, _, v = teil.partition("=")
        if k.strip():
            out[k.strip()] = v.strip()
    return out


def einstiche(m):
    """Einstiche wie in der Position (step.uebernehmen): Konturen der Messung, an den Enden je nach Profil mehr."""
    from . import rechnen
    form = m.get("profilform") or ""
    enden = sum(1 for n in ("ende_a", "ende_b") if _f(m, n) > 0)
    return int(_f(m, "konturen")) + (rechnen.einstiche_ende(form) - 1) * enden


def erkennung(m, k_json=None):
    """Erkannte Werte des Körpers als [(Titel, Wert)] für das Feld „Erkennung“ (alles aus der Messung)."""
    from . import step
    k_json = k_json or {}
    g = gruppe(m)
    out = [("Bauteil", name(m)), ("Art", g)]
    form = m.get("profilform") or m.get("bauteiltyp") or ""
    if form:
        out.append(("Profiltyp", form))
    if m.get("profil_id_vorschlag"):
        out.append(("Profil-ID (Vorschlag)", m["profil_id_vorschlag"]))
    a, b, w = _f(m, "abm_a"), _f(m, "abm_b"), _f(m, "wandstaerke")
    if a:
        out.append(("Abmessungen", f"{_dez(a, 2)}x{_dez(b, 2)} mm" if b and abs(b - a) > 1e-9 else f"{_dez(a, 2)} mm"))
    if w:
        out.append(("Wandstärke", f"{_dez(w, 2)} mm"))
    if _f(m, "laenge"):
        out.append(("Länge", f"{_dez(_f(m, 'laenge'), 2)} mm"))
    if g in (ROHR,):
        out.append(("Schneidweg", f"{_dez(_f(m, 'schneidweg'), 1)} mm (ohne Gravur)"))
        out.append(("Einstiche", str(einstiche(m))))
        if _f(m, "innen"):
            out.append(("Innenkonturen", f"{int(_f(m, 'innen_konturen'))} Stück, {_dez(_f(m, 'innen'), 1)} mm"))
        if _f(m, "gravur"):
            out.append(("Gravur", f"{int(_f(m, 'gravur_konturen'))} Stück, {_dez(_f(m, 'gravur'), 1)} mm"))
        if m.get("bohrungen"):
            out.append(("Bohrungen", step.bohrungen_text(m["bohrungen"])))
        g_ = step.gehrungen(m)
        schraeg = [f"{t} {_dez(_f(g_, k), 1)}°" for k, t in (("a_gehrung", "Ende A"), ("b_gehrung", "Ende B"))
                   if _f(g_, k)]
        if schraeg:
            out.append(("Gehrung / Schrägschnitt", ", ".join(schraeg)))
    nt = normteil(m)
    if nt:
        out.append(("Normteil/Zukauf", f"{nt.get('kategorie') or ''} {nt.get('norm') or ''} {nt.get('groesse') or ''}"
                    .strip() + f" – {nt.get('vertrauen') or ''}: {nt.get('grund') or ''}"))
    if _f(m, "volumen"):
        out.append(("Volumen", f"{_dez(_f(m, 'volumen') / 1000, 1)} cm³"))
    if _f(m, "oberflaeche"):
        out.append(("Oberfläche", f"{_dez(_f(m, 'oberflaeche') / 100, 1)} cm²"))
    huelle = [float(x) for x in str(m.get("huelle") or "").split("|") if _zahl(x)]
    if len(huelle) == 3:
        out.append(("Hüllquader (Datei)", " × ".join(_dez(x, 1) for x in huelle) + " mm"))
    if m.get("n_flaechen"):
        out.append(("Flächen / Kanten", f"{m.get('n_flaechen')} / {m.get('n_kanten') or '?'}"))
    if m.get("koerperart"):
        out.append(("Körperart", m["koerperart"] + ("" if m.get("gueltig") != "0" else " (Geometrie fehlerhaft)")))
    sich = _sicherheit(m)
    if sich:
        out.append(("Erkennung", ", ".join(f"{k} {v}" for k, v in sich.items())))
    if m.get("pruefstatus"):
        out.append(("Prüfstatus", m["pruefstatus"]))
    if m.get("art_grund"):
        out.append(("Grund der Art", m["art_grund"]))
    if k_json.get("warnungen"):
        out.append(("Warnungen", "; ".join(k_json["warnungen"])))
    if m.get("hinweise"):
        out.append(("Hinweise", m["hinweise"]))
    if m.get("fehler"):
        out.append(("Fehler", m["fehler"]))
    return out + pruef_zeilen(m)


def _zahl(x):
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def uebersicht(mes):
    """Zusammenfassung der ganzen Datei als [(Titel, Wert)] (Gesamtansicht ohne gewählten Körper)."""
    if mes is None or not mes.messwerte:
        return []
    je = {}
    for m in mes.messwerte:
        je.setdefault(gruppe(m), []).append(m)
    out = [("Datei", mes.pfad.name), ("Körper", str(len(mes.messwerte)))]
    for g in GRUPPEN:
        if g in je:
            out.append((g, str(len(je[g]))))
    rohre = je.get(ROHR) or []
    if rohre:
        out.append(("Schneidweg aller Rohre/Profile", f"{_dez(sum(_f(m, 'schneidweg') for m in rohre), 1)} mm"))
        out.append(("Einstiche aller Rohre/Profile", str(sum(einstiche(m) for m in rohre))))
        profile = {}
        for m in rohre:
            pid = m.get("profil_id_vorschlag") or m.get("profilform") or "?"
            profile[pid] = profile.get(pid, 0) + 1
        out.append(("Profile", ", ".join(f"{n}× {p}" for p, n in sorted(profile.items()))))
    normteile = je.get(NORMTEIL) or []
    if normteile:
        arten = {}
        for m in normteile:
            k = (normteil(m) or {}).get("kategorie") or "Zukaufteil"
            arten[k] = arten.get(k, 0) + 1
        out.append(("Normteile (nicht im Schneidweg)", ", ".join(f"{n}× {k}" for k, n in sorted(arten.items()))))
    out += pruef_uebersicht(mes)
    out.append(("Analysestufe", mes.stufe))
    return out


# ------------------------------------------------------------------ Konturen
def konturen_liste(m):
    try:
        d = json.loads(m.get("konturen_liste") or "[]")
    except ValueError:
        return []
    return d if isinstance(d, list) else []


def blech_liste(m):
    """Blech (und andere Körper ohne Konturliste): Konturen aus der Blechmessung – Außenkontur = Schneidweg minus
    Innenkonturen, Innenkonturen aus innen_liste (Ø:Länge, Ø 0 = keine Bohrung). Summe = Schneidweg der Messung."""
    from . import step
    innen = step._paare(m.get("innen_liste"))
    sw = _f(m, "schneidweg")
    if sw <= 0:
        return []
    aussen = sw - sum(lg for _, lg in innen)
    out = [dict(art="Außenkontur", durchgehend=True, schnittlaenge=aussen)] if aussen > 1e-6 else []
    for dm, lg in innen:
        out.append(dict(art="Bohrung", durchgehend=True, durchmesser=dm, schnittlaenge=lg) if dm > 0 else
                   dict(art="Innenkontur", durchgehend=True, schnittlaenge=lg))
    return out


def kontur_klasse(d):
    """Farbklasse der Kontur (KONTURFARBEN)."""
    art = str(d.get("art") or "")
    if art.startswith("Ende"):
        g = d.get("gehrung")
        return "Ende" if (d.get("form") == "gerade" or (g is not None and abs(float(g or 0)) < 1e-6)) else "Schräg"
    if art in ("Gravur",) or (not d.get("durchgehend") and art not in ("Sackbohrung",)):
        return "Gravur" if art == "Gravur" else "Nicht"
    if art == "Sackbohrung" or not d.get("schnittlaenge"):
        return "Nicht"
    if art in ("Bohrung", "Senkung"):
        return "Schräg" if float(d.get("schraeg") or 0) >= 1.0 else "Bohrung"
    if art in ("Langloch", "Schlitz"):
        return "Langloch"
    if art in ("Rechteckausschnitt", "Ausschnitt", "Rechteck"):
        return "Rechteck"
    return "Sonder"


def kontur_mass(d):
    """Maß der Kontur als Text (Ø, L × B, Gehrungswinkel)."""
    if d.get("durchmesser"):
        return f"Ø{_dez(float(d['durchmesser']), 2)}"
    if d.get("laenge") and d.get("breite"):
        return f"{_dez(float(d['laenge']), 2)} × {_dez(float(d['breite']), 2)}"
    if str(d.get("art") or "").startswith("Ende"):
        g = d.get("gehrung")
        return f"{d.get('form') or ''}" + (f" {_dez(float(g), 1)}°" if g not in (None, 0, 0.0) else "")
    return ""


def kontur_lage(d):
    teile = []
    if d.get("z") is not None:
        teile.append(f"z {_dez(float(d['z']), 1)}")
    if d.get("seite"):
        teile.append(str(d["seite"]))
    elif d.get("winkel") is not None:
        teile.append(f"{_dez(float(d['winkel']), 0)}°")
    return ", ".join(teile)


def _zug_laenge(zug):
    s = 0.0
    for i in range(3, len(zug) - 2, 3):
        s += math.dist(zug[i - 3:i], zug[i:i + 3])
    return s


def linien_laengen(netz):
    """Länge der Linienzüge im Netz je Kontur {Nummer: mm} aus netz['lk'] (Gegenprobe zur Schnittlänge)."""
    out = {}
    lk = (netz or {}).get("lk") or {}
    for art, zuege in ((netz or {}).get("l") or {}).items():
        nummern = lk.get(art) or []
        for i, zug in enumerate(zuege):
            nr = nummern[i] if i < len(nummern) else -1
            if isinstance(nr, int) and nr >= 0:
                out[nr] = out.get(nr, 0.0) + _zug_laenge(zug)
    return out


def konturen(m, netz=None):
    """Konturen des Körpers als Zeilen dict(nr, art, klasse, mass, lage, schnitt, einstich, durch, netz_mm,
    gegenprobe, hinweis, kennung). einstich = 1 für jede gelaserte Kontur (Enden: siehe einstiche()); netz_mm = Länge
    der Linien im 3D (None ohne Zuordnung), gegenprobe = '✓' / 'Abweichung' / ''."""
    laengen = linien_laengen(netz) if netz else {}
    mit_lk = bool((netz or {}).get("lk"))
    liste = konturen_liste(m)
    if not liste:
        liste, mit_lk = blech_liste(m), False          # Blech: keine Zuordnung zu den 3D-Linien
    # offene Profile (U, C, L, T, Flachstahl): die Messung zeichnet die Kanten auf beiden Seiten der Wand, gerechnet
    # wird eine (Schnittlänge = halbe Kantenlänge, step_geometrie._offen_konturen)
    offen = any(isinstance(d, dict) and ("querschnitt" in d or "querlage" in d) for d in liste)
    rundrohr = m.get("profilform") == "Rundrohr"
    wand = _f(m, "wandstaerke") or None
    sicher = _sicherheit(m).get("konturen") != "unsicher"     # „wahrscheinlich“ kommt von einzelnen Konturen
    out = []
    for nr, d in enumerate(liste):
        if not isinstance(d, dict):
            continue
        kl = kontur_klasse(d)
        schnitt = float(d.get("schnittlaenge") or 0.0)
        aussen = schnitt                # Länge der Außenlinie (Gegenprobe)
        hinweis = str(d.get("hinweis") or "")
        ende = {"Ende A": "ende_a", "Ende B": "ende_b"}.get(str(d.get("art") or ""))
        if ende and m.get(ende) not in (None, "") and _f(m, ende) > schnitt + 0.05:   # Rundung (2 Stellen) ist kein Steg
            # Ende mit Innensteg/Innenwand: die Messung rechnet den Schnitt durch den Steg mit (ende_a/ende_b)
            hinweis = (hinweis + "; " if hinweis else "") + f"inkl. Innensteg {_dez(_f(m, ende) - schnitt)} mm"
            schnitt = _f(m, ende)
        gelasert = kl not in ("Gravur", "Nicht")
        lg = laengen.get(nr) if mit_lk else None
        if lg is not None and offen and d.get("durchgehend"):
            lg /= 2
        probe = ""

        def passt(a, b):
            return abs(a - b) <= max(GEGENPROBE_MIN, GEGENPROBE_TOL * b)
        if d.get("art") in ("Senkung", "Fließloch") or d.get("gewinde"):
            lg = None           # Linie = Senk-/Kragen-/Gewinderand, geschnitten wird das Kernloch: nicht vergleichbar
        if lg is not None and aussen > 0:
            probe = "✓" if passt(lg, aussen) else "Abweichung"
            dm = float(d.get("durchmesser") or 0)
            if probe != "✓" and rundrohr and d.get("art") == "Bohrung" and dm \
                    and math.pi * dm - GEGENPROBE_MIN <= lg <= aussen + GEGENPROBE_MIN:
                # Bohrung im Rundrohr als 2D-Schnitt (dreid.bohrung_2d_rundrohr): die 3D-Linie (Sattelkurve) liegt
                # zwischen π·Ø und dem längeren 2D-Schnitt, der gerechnet wird
                probe = "✓ 2D-Schnitt"
        r = kr.rolle(d, wand, sicher)
        out.append(dict(nr=nr, art=str(d.get("art") or ""), klasse=kl, mass=kontur_mass(d), lage=kontur_lage(d),
                        schnitt=schnitt, einstich=1 if gelasert and schnitt > 0 else 0, durch=bool(d.get("durchgehend")),
                        netz_mm=lg, gegenprobe=probe, hinweis=hinweis, kennung=f"{KONTUR}{nr}",
                        schwenk=d.get("schwenk"), daten=d, rolle=r["rolle"] if r["schnitt"] else "kein Schnitt",
                        stufe=r["stufe"], stufe_text=r["stufe_text"], grund=r["grund"], hand=bool(r.get("hand"))))
    return out


def summen(m, zeilen):
    """Summe der Konturzeilen gegen die Werte der Messung (die die Position übernimmt): dict(schneidweg, summe,
    gleich, einstiche, gravur, gegenprobe_ok, gegenprobe_n)."""
    laser = sum(z["schnitt"] for z in zeilen if z["klasse"] not in ("Gravur", "Nicht"))
    sw = _f(m, "schneidweg")
    gepr = [z for z in zeilen if z["gegenprobe"]]
    return dict(schneidweg=sw, summe=round(laser, 2), gleich=abs(laser - sw) <= max(0.5, 0.001 * sw),
                einstiche=einstiche(m), gravur=sum(z["schnitt"] for z in zeilen if z["klasse"] == "Gravur"),
                gegenprobe_ok=sum(1 for z in gepr if z["gegenprobe"].startswith("✓")), gegenprobe_n=len(gepr))


def kontur_info(z, m):
    """Berechnungsinformationen einer angeklickten Kontur als [(Titel, Wert)]."""
    out = [("Kontur", f"Nr. {z['nr']}: {z['art']}"), ("Maß", z["mass"] or "–"), ("Lage", z["lage"] or "–"),
           ("Schnittlänge", f"{_dez(z['schnitt'], 2)} mm" if z["schnitt"] else "–"),
           ("Einstich", "ja" if z["einstich"] else "nein"),
           ("Durchgehend", "ja" if z["durch"] else "nein"),
           ("Im Schneidweg", "ja" if z["klasse"] not in ("Gravur", "Nicht") else
            "nein (Gravur, eigene Zeit)" if z["klasse"] == "Gravur" else "nein")]
    if z.get("schwenk") not in (None, ""):
        out.append(("Schwenkwinkel Kopf", f"{_dez(float(z['schwenk']), 1)}°"))
    if z["netz_mm"] is not None:
        out.append(("Linie im 3D (Gegenprobe)", f"{_dez(z['netz_mm'], 2)} mm {z['gegenprobe']}".strip()))
        if z["gegenprobe"] == "✓ 2D-Schnitt":
            out.append(("Erklärung", "Bohrung im Rundrohr: der Laser schneidet 2D (Strahl zur Rohrmitte), außen "
                        "länger als die konstruierte Bohrung; gerechnet wird der 2D-Schnitt"))
    if z.get("rolle"):
        out.append(("Rolle", z["rolle"] + (" (von Hand)" if z.get("hand") else "")))
        out.append(("Schneidbarkeit", f"{z['stufe']} {z['stufe_text']}: {z['grund']}"))
    if z["hinweis"]:
        out.append(("Hinweis", z["hinweis"]))
    out.append(("Anteil am Schneidweg", f"{_dez(100 * z['schnitt'] / _f(m, 'schneidweg'), 1)} %"
                if _f(m, "schneidweg") and z["klasse"] not in ("Gravur", "Nicht") else "–"))
    return out


# ------------------------------------------------------------------ Netze für die Anzeige
def mit_konturkennung(netz):
    """Kopie des Netzes, in der jeder Linienzug die Kennung seiner Kontur trägt (netz 'li' = 'kontur:<Nr>'), damit
    Anklicken und Hervorheben in der Ansicht gehen. Nur für den Viewer: das gespeicherte Netz behält 'lk'."""
    if not netz or not netz.get("lk"):
        return netz
    out = dict(netz)
    out["li"] = {art: [f"{KONTUR}{n}" if isinstance(n, int) and n >= 0 else None for n in nummern]
                 for art, nummern in netz["lk"].items()}
    return out


def konturfarben(zeilen, nach="Art", aus=()):
    """Farben je Linienkennung für ansicht3d.kosten_setzen und die Legende (nur vorhandene Arten/Rollen/Stufen).
    nach: "Art" (KONTURFARBEN), "Rolle" (ROLLENFARBEN, Anfang und Ende verschieden) oder "Schneidbarkeit"
    (STUFENFARBEN); aus: Rollen, die ausgeblendet sind (ohne Farbe, nicht in der Legende)."""
    zeilen = [z for z in zeilen if z.get("rolle") not in aus]
    if nach == "Rolle":
        linien = {z["kennung"]: ROLLE_FARBE.get(z.get("rolle"), "#7F8C8D") for z in zeilen}
        da = {z.get("rolle") for z in zeilen}
        return linien, [(t, f) for k, t, f in ROLLENFARBEN if k in da]
    if nach == "Schneidbarkeit":
        farbe = {k: f for k, _, f in STUFENFARBEN}
        zeilen = [z for z in zeilen if z.get("rolle") != "kein Schnitt"]
        linien = {z["kennung"]: farbe.get(z.get("stufe"), "#7F8C8D") for z in zeilen}
        da = {z.get("stufe") for z in zeilen}
        return linien, [(t, f) for k, t, f in STUFENFARBEN if k in da]
    linien = {z["kennung"]: FARBE_JE[z["klasse"]] for z in zeilen}
    da = {z["klasse"] for z in zeilen}
    return linien, [(t, f) for k, t, f in KONTURFARBEN if k in da]


def ohne_konturen(netz, kennungen):
    """Netz ohne die Linienzüge der Konturen kennungen (netz 'li' der Viewer-Kopie, mit_konturkennung): Konturen
    einer Rolle ausblenden. Dreiecke bleiben; ohne kennungen kommt das Netz unverändert zurück."""
    if not netz or not kennungen or not isinstance(netz.get("li"), dict):
        return netz
    kennungen = set(kennungen)
    out = dict(netz)
    neu_l, neu_li = {}, {}
    for art, zuege in (netz.get("l") or {}).items():
        kn = netz["li"].get(art) or []
        behalten = [i for i in range(len(zuege)) if not (i < len(kn) and kn[i] in kennungen)]
        neu_l[art] = [zuege[i] for i in behalten]
        if art in netz["li"]:
            neu_li[art] = [kn[i] for i in behalten if i < len(kn)]
    out["l"], out["li"] = neu_l, neu_li
    out.pop("ln", None)
    out.pop("lk", None)
    return out


def ausgeblendet(zeilen, aus):
    """Kennungen der Konturen, deren Rolle in aus liegt."""
    return {z["kennung"] for z in zeilen if z.get("rolle") in aus}


def rolle_setzen(m, nr, rolle):
    """Handkorrektur: Rolle der Kontur nr in den Messwerten m setzen (konturen_liste[nr]["rolle_hand"]; None = wieder
    die gemessene). Die Position übernimmt die Messwerte mit der Korrektur. True = geändert."""
    liste = konturen_liste(m)
    if not (0 <= nr < len(liste)) or not isinstance(liste[nr], dict):
        return False
    if rolle is not None and rolle not in kr.ROLLEN:
        return False
    if rolle is None:
        if "rolle_hand" not in liste[nr]:
            return False
        liste[nr].pop("rolle_hand")
    else:
        liste[nr]["rolle_hand"] = rolle
    m["konturen_liste"] = json.dumps(liste, ensure_ascii=False, separators=(",", ":"))
    return True


# ------------------------------------------------------------------ Abwicklung 2D (neben dem 3D)
def umfang(m):
    """Außenumfang des Profils für die 2D-Abwicklung [mm] (Rundrohr π·Ø, Quadrat-/Rechteckrohr mit Außenradius),
    sonst die längste gerade Endkontur; None = keine Abwicklung (offene Profile, Bleche)."""
    form = m.get("profilform") or ""
    a, b, r = _f(m, "abm_a"), _f(m, "abm_b"), _f(m, "radius")
    if form == "Rundrohr" and a > 0:
        return math.pi * a
    if form in ("Quadratrohr", "Rechteckrohr") and a > 0:
        b = b or a
        return 2 * (a + b) - (8 - 2 * math.pi) * r
    enden = [d for d in konturen_liste(m) if isinstance(d, dict) and d.get("form") == "gerade"]
    return max((float(d.get("schnittlaenge") or 0) for d in enden), default=0.0) or None


def abwicklung_2d(m, zeilen, aus=()):
    """Abwicklung des Mantels für die Ansicht neben dem 3D: dict(umfang, laenge, linien=[dict(nr, kennung, rolle,
    stufe, punkte [(s, z)], gerade)]). Konturen mit Umriss (Abwicklung der Messung, s = Umfang ab 0°) als Linienzug,
    gerade Enden ohne Umriss als Linie über den ganzen Umfang bei z. Nur Anzeige; None ohne Umfang oder Länge."""
    u, lg = umfang(m), _f(m, "laenge")
    if not u or lg <= 0:
        return None
    linien = []
    for z in zeilen:
        if z.get("rolle") in aus:
            continue
        d = z.get("daten") or {}
        pts = []
        for p in d.get("umriss") or ():
            try:
                pts.append((float(p[0]) % u, float(p[1])))
            except (TypeError, ValueError, IndexError):
                continue
        gerade = False
        if not pts and str(d.get("art") or "").startswith("Ende") and d.get("z") is not None:
            zz = float(d["z"])
            pts, gerade = [(0.0, zz), (u, zz)], True
        if pts:
            linien.append(dict(nr=z["nr"], kennung=z["kennung"], rolle=z.get("rolle"), stufe=z.get("stufe"),
                               punkte=pts, gerade=gerade))
    return dict(umfang=u, laenge=lg, linien=linien)


def treffer_2d(abw, s, z, tol=3.0):
    """Kontur der 2D-Abwicklung, die am Punkt (s, z) liegt (Abstand höchstens tol mm), als Kennung; sonst None."""
    beste, best_d = None, tol
    for li in (abw or {}).get("linien") or ():
        p = li["punkte"]
        for a, b in zip(p, p[1:] + ([] if li["gerade"] else p[:1])):
            if not li["gerade"] and abs(a[0] - b[0]) > abw["umfang"] / 2:      # Sprung über die Naht der Abwicklung
                continue
            d_ = _abstand_strecke((s, z), a, b)
            if d_ < best_d:
                beste, best_d = li["kennung"], d_
    return beste


def _abstand_strecke(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def gesamt_netz(mes, sichtbar, hervor=(), nach_pruefung=False):
    """Alle sichtbaren Körper in Einbaulage (ansicht3d.baugruppe), jedes Teil anklickbar (netz 'ti' = teil:<Nr>);
    Normteile dunkelgrau; nach_pruefung: Farbe nach der Geometrieprüfung (PRUEF_ART). Ergebnis: (Netz oder None,
    Teile ohne Einbaulage)."""
    from .ansicht3d import baugruppe
    from .baugruppe_ansicht import teil_kennung
    teile = [i for i in sichtbar if mes.netz(i)]
    bereiche = []
    netz, ohne = baugruppe([mes.netz(i) for i in teile], {n for n, i in enumerate(teile) if i in set(hervor)},
                           list(range(len(teile))), bereiche=bereiche,
                           normteile={n for n, i in enumerate(teile) if gruppe(mes.messwerte[i]) == NORMTEIL},
                           pruefung={n: PRUEF_ART.get(pruef_status(mes.messwerte[i]), "QU") for n, i in enumerate(teile)}
                           if nach_pruefung else None)
    if netz:
        teil_kennung(netz, bereiche, [f"{TEIL}{i}" for i in teile])
        netz["teile"] = True
    return netz, ohne


# ------------------------------------------------------------------ Geometrieprüfung (step_qualitaet, 24.11.2026)
PRUEF_ART = {"korrekt": "QK", "unsicher": "QU", "reparierbar": "QR", "fehlerhaft": "QF"}


def pruefung(m):
    """Geometrieprüfung des Körpers (Spalte 'pruefung' der Messung) als dict oder None (ältere Messung)."""
    q = m.get("pruefung")
    if isinstance(q, dict) or not q:
        return q or None
    try:
        return json.loads(q)
    except (TypeError, ValueError):
        return None


def pruef_status(m):
    """korrekt / unsicher / reparierbar / fehlerhaft; '' ohne Prüfung."""
    return (pruefung(m) or {}).get("status") or ""


def pruef_zeilen(m):
    """Zeilen für das Feld „Erkennung“: Status, Toleranz, Fehler, Reparatur, CAD-Prüfwerte, Doppelt."""
    q = pruefung(m)
    if not q:
        return []
    out = [("Geometrieprüfung", q.get("status") or "")]
    tol = q.get("toleranz") or {}
    if tol.get("max") is not None:
        t = tol["max"]
        out.append(("Toleranz nach dem Einlesen", ("< 0,0001" if t < 1e-4 else _dez(t, 4)) + f" mm ({tol.get('stufe')})"))
    if q.get("fehler"):
        from .importanalyse_dialog import FEHLER_TEXT
        out.append(("Geometriefehler", ", ".join(f"{n}× {FEHLER_TEXT.get(c, c)}" for c, n in q["fehler"].items())))
    r = q.get("reparatur")
    if r:
        out.append(("Reparatur-Probe", f"Klasse {r.get('klasse')}: {r.get('text')}"
                    + (" – gemessen mit der reparierten Kopie" if q.get("gemessen_mit_reparatur") else "")))
    c = q.get("cad_referenz")
    if c:
        out.append(("CAD-Prüfwerte", f"{c.get('status')} (Volumen {_dez((c.get('volumen_rel') or 0) * 100, 3)} %)"))
    if q.get("doppelt_zu"):
        out.append(("Doppelt", f"liegt deckungsgleich auf Körper {q['doppelt_zu']}"))
    return out


def pruef_uebersicht(mes):
    """Zeilen der Gesamtübersicht: Körper je Prüfstatus und die Genauigkeit der Datei."""
    st = {}
    for m in mes.messwerte:
        s_ = pruef_status(m)
        if s_:
            st[s_] = st.get(s_, 0) + 1
    if not st:
        return []
    out = [("Geometrieprüfung", ", ".join(f"{st[k]} {k}" for k in PRUEF_ART if st.get(k)))]
    d = next((x for x in (m.get("pruefung_datei") for m in mes.messwerte) if x), None)
    try:
        d = json.loads(d) if isinstance(d, str) else d
    except (TypeError, ValueError):
        d = None
    if d:
        if d.get("system"):
            out.append(("CAD-System", d["system"]))
        if d.get("unsicherheit_mm"):
            u = d["unsicherheit_mm"]
            out.append(("Genauigkeit der Datei", ("< 0,0001" if u < 1e-4 else _dez(u, 4)) + " mm"))
        out.append(("CAD-Prüfwerte", ", ".join(f"{n} {k}" for k, n in (d.get("cad_abgleich") or {}).items())
                    or ("in der Datei, keinem Körper zuzuordnen" if d.get("cad_pruefwerte") else "keine in der Datei")))
    return out


def teil_nr(kennung):
    k = str(kennung or "")
    return int(k[len(TEIL):]) if k.startswith(TEIL) and k[len(TEIL):].isdigit() else None


def kontur_nr(kennung):
    k = str(kennung or "")
    return int(k[len(KONTUR):]) if k.startswith(KONTUR) and k[len(KONTUR):].isdigit() else None


# ------------------------------------------------------------------ Korrektur von Hand
def art_setzen(m, ziel):
    """Art von Hand ändern (Blech, Rohr/Profil, Dreh-/Frästeil wie im Prüfdialog, step.art_setzen; Normteil =
    Zukaufteil annehmen; Fertigungsteil = Normteil-Vorschlag ablehnen). True, wenn geändert."""
    from . import step, zukaufteile
    if ziel == NORMTEIL:
        if m.get("_zukauf_hand"):
            return False
        zukaufteile.annehmen(m)
        return True
    if m.get("_zukauf_hand") or m.get("_normteil"):
        for k in ("_zukauf_hand", "_normteil", "_normteil_bezeichnung", "_zukaufteil"):
            m.pop(k, None)
        m["_fertigung_hand"] = True
        if ziel in (None, gruppe(m)):
            return True
    if ziel in (None, ROHR, BLECH, DREHFRAES) and gruppe(m) == NORMTEIL:
        m["_fertigung_hand"] = True
    gr = {ROHR: step.ART_PROFIL, BLECH: step.ART_BLECH, DREHFRAES: step.ART_DREHFRAES}.get(ziel)
    if gr is None:
        return bool(m.get("_fertigung_hand"))
    if step.art_gruppe(m) == gr:
        return bool(m.get("_fertigung_hand"))
    return step.art_setzen(m, gr)


def arten_moeglich(m):
    """Arten, auf die der Körper umgestellt werden kann (gemessen in der Messung) plus Normteil."""
    from . import step
    out = []
    for gr, d in step.arten(m).items():
        if d.get("messung") is not None:
            out.append({step.ART_PROFIL: ROHR, step.ART_BLECH: BLECH, step.ART_DREHFRAES: DREHFRAES}[gr])
    return [g for g in (ROHR, BLECH, DREHFRAES) if g in out] + [NORMTEIL]


def korrekturen_merken(db, messwerte):
    """Von Hand geänderte Arten und Normteil-Entscheidungen für künftige Importe merken (dieselben Einstellungen wie
    der Prüfdialog: step.ART_GELERNT, zukaufteile.GELERNT). Ergebnis: Anzahl gemerkter Teile."""
    from . import step, zukaufteile
    arten_neu = {}
    for m in messwerte:
        if m.get("_art_gemessen") and step.art_schluessel(m):
            arten_neu[step.art_schluessel(m)] = step.art_gruppe(m)
    if arten_neu:
        db.einstellung_setzen(step.ART_GELERNT, step.arten_gelernt_merken(db.einstellung(step.ART_GELERNT) or {},
                                                                         arten_neu))
    zk_alt = db.einstellung(zukaufteile.GELERNT) or {}
    zk_neu = zukaufteile.entscheidungen(messwerte, zk_alt)
    if zk_neu:
        db.einstellung_setzen(zukaufteile.GELERNT, zukaufteile.merken(zk_alt, zk_neu))
    return len(arten_neu) + len(zk_neu)


# ------------------------------------------------------------------ Leistung
def leistung_zeilen(mes, anzeige=None):
    """Messwerte der Leistung als [(Titel, Wert)]: Messung (Einlesen, Analyse, Abschluss), Netz laden, Modell
    aufbauen, erstes Bild; anzeige = dict(modell_s, bild_s, dreiecke) der Ansicht."""
    z = (mes.zeiten if mes else {}) or {}
    out = []

    def s(x):
        return f"{_dez(x, 2)} s" if isinstance(x, (int, float)) else "–"
    if "kopf_s" in z:
        out.append(("Kopf der Datei lesen", s(z["kopf_s"])))
    out.append(("Messung gesamt", s(z.get("messung_s")) + (" (aus dem Zwischenspeicher)" if z.get("aus_speicher")
                                                            else "")))
    for k, t in (("lesen_s", "  STEP einlesen"), ("messen_s", "  Geometrie analysieren"),
                 ("abschluss_s", "  Abschluss (Baugruppe, Nähte)")):
        if z.get(k) is not None:
            out.append((t, s(z[k])))
    if z.get("netz_laden_s") is not None:
        out.append(("Netze laden", s(z["netz_laden_s"])))
    for k, t in (("modell_s", "Netz an die Ansicht geben"), ("bild_s", "Modell aufbauen und zeichnen"),
                 ("erstes_bild_s", "Zeit bis zum ersten 3D-Bild (ab Öffnen)")):
        if (anzeige or {}).get(k) is not None:
            out.append((t, s(anzeige[k])))
    if (anzeige or {}).get("dreiecke"):
        out.append(("Dreiecke gezeigt", f"{anzeige['dreiecke']:,}".replace(",", ".")))
    return out


def text_kopieren(zeilen):
    return "\n".join(f"{t}\t{w}" for t, w in zeilen)


def dateiname_ok(pfad):
    """Lesbare CAD-Datei für den Viewer (STEP, IGES, TUBX, BLM)?"""
    from . import step
    return Path(pfad).suffix.lower() in step.CAD_ENDUNGEN

