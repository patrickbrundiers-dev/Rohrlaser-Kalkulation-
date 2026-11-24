"""CAD-Import vorbereiten (Importengine, Laserhub-Vergleich, Patrick 20.11.2026): aus gezogenen bzw. gewählten Dateien,
Ordnern und ZIP-Archiven die Liste der STEP-/IGES-Dateien für die Messung und eine Liste von Befunden.

Laserhub nimmt STEP, SLDPRT und CATPART, entpackt ZIP-Archive und lädt mehrere Dateien per Drag & Drop. Das Programm
misst STEP und IGES (OpenCascade); SolidWorks-, CATIA-, Inventor-, Creo/NX- und Parasolid-Dateien sind
Herstellerformate, deren Geometrie sich ohne den Kern des Herstellers nicht lesen lässt. Statt sie still zu übergehen,
steht jede solche Datei mit klarer Meldung im Prüfdialog (rote Zeile „nicht lesbar“) und im Importbericht.

vorbereiten(pfade) -> Vorbereitung:
- dateien: STEP/IGES zum Messen (Ordner samt Unterordnern, ZIP-Archive entpackt, auch ZIP in ZIP bis ZIP_TIEFE)
- befunde: [dict(datei, stufe, text)] stufe FEHLER (nicht messbar) oder HINWEIS (gemessen, aber beachten)
  · Herstellerformat (SLDPRT …), leere Datei, keine STEP-Datei (Kopf fehlt), ZIP defekt/zu groß/verschlüsselt
  · unvollständige STEP-Datei (Ende fehlt; die Messung versucht es trotzdem)
  · doppelte Datei (gleicher Inhalt, auch unter anderem Namen): nur einmal gemessen
  · andere Dateien (PDF, Bilder, Text) übersprungen
- herkunft: {entpackte Datei: "Archiv.zip"} (für Bericht und Ablage)

Entpackt wird in einen Ordner je Archiv-Inhalt (SHA-256) unter dem Temp-Ordner (ENTPACKT), damit die Dateien für die
Kopie in den Angebotsordner und „Neu einlesen“ erhalten bleiben; ältere als AUFHEBEN_TAGE werden aufgeräumt.
Schutz: keine Pfade außerhalb des Zielordners (Zip Slip), höchstens ZIP_MAX_MB entpackt und ZIP_MAX_DATEIEN Einträge.
Ohne Qt.
"""
import hashlib
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

STEP_ENDUNGEN = (".step", ".stp")
IGES_ENDUNGEN = (".igs", ".iges")
BLM_ENDUNGEN = (".artube", ".bpf")      # BLM/Adige ArTube-Projekt und Teileprogramm (step_messung/step_blm.py)
CAD_ENDUNGEN = STEP_ENDUNGEN + IGES_ENDUNGEN + (".tubx",) + BLM_ENDUNGEN    # TUBX (#593) und BLM messen wie STEP
ZIP_ENDUNGEN = (".zip",)
# Herstellerformate: Name für die Meldung
NATIV = {
    ".sldprt": "SolidWorks-Teil", ".sldasm": "SolidWorks-Baugruppe",
    ".catpart": "CATIA-Teil", ".catproduct": "CATIA-Baugruppe",
    ".ipt": "Inventor-Teil", ".iam": "Inventor-Baugruppe",
    ".prt": "Creo-/NX-Teil", ".asm": "Creo-Baugruppe", ".par": "Solid-Edge-Teil", ".psm": "Solid-Edge-Blechteil",
    ".x_t": "Parasolid-Datei", ".x_b": "Parasolid-Datei", ".sat": "ACIS-Datei", ".jt": "JT-Datei",
    ".3dm": "Rhino-Datei", ".f3d": "Fusion-360-Datei", ".ifc": "IFC-Datei",
    ".stl": "STL-Netz", ".obj": "OBJ-Netz",
}
NATIV_TEXT = ("{art} ({endung}) kann nicht gelesen werden – Herstellerformat ohne frei lesbare Geometrie. "
              "Bitte im CAD als STEP (AP214 oder AP242) speichern und neu importieren.")
NETZ_TEXT = ("{art} ({endung}) enthält nur Dreiecke, keine Volumengeometrie (Bohrungen, Wand, Konturen nicht "
             "messbar). Bitte als STEP speichern.")
FEHLER, HINWEIS = "Fehler", "Hinweis"
ZIP_TIEFE = 3
ZIP_MAX_MB = 500
ZIP_MAX_DATEIEN = 5000
AUFHEBEN_TAGE = 14
ENTPACKT = "Rohrlaser-CAD-Import"
KOPF_BYTES = 4096


@dataclass
class Vorbereitung:
    dateien: list = field(default_factory=list)
    befunde: list = field(default_factory=list)
    herkunft: dict = field(default_factory=dict)

    def fehler(self):
        return [b for b in self.befunde if b["stufe"] == FEHLER]

    def hinweise(self):
        return [b for b in self.befunde if b["stufe"] == HINWEIS]

    def zeilen(self):
        """Textzeilen für Bericht und Meldung."""
        return [f"{b['datei']}: {b['text']}" for b in self.befunde]


def kandidat(pfad):
    """Schnelle Prüfung beim Darüberziehen: CAD-Datei, ZIP, Herstellerformat oder Ordner."""
    p = Path(pfad)
    e = p.suffix.lower()
    return e in CAD_ENDUNGEN or e in ZIP_ENDUNGEN or e in NATIV or p.is_dir()


def _sha(pfad, block=1 << 20):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for teil in iter(lambda: f.read(block), b""):
            h.update(teil)
    return h.hexdigest()


def step_pruefen(pfad):
    """(Stufe, Text) für eine STEP-Datei mit Problem oder None. Liest nur Anfang und Ende der Datei."""
    try:
        gr = Path(pfad).stat().st_size
    except OSError as e:
        return FEHLER, f"Datei nicht lesbar ({e.strerror or e})"
    if gr == 0:
        return FEHLER, "leere Datei (0 Byte)"
    try:
        with open(pfad, "rb") as f:
            kopf = f.read(KOPF_BYTES)
            f.seek(max(0, gr - KOPF_BYTES))
            ende = f.read()
    except OSError as e:
        return FEHLER, f"Datei nicht lesbar ({e.strerror or e})"
    if b"ISO-10303-21" not in kopf.upper():
        if kopf[:4] == b"PK\x03\x04":
            return FEHLER, "ZIP-Archiv mit Endung .step – bitte als .zip importieren"
        return FEHLER, "keine STEP-Datei (Kopfzeile ISO-10303-21 fehlt)"
    if b"END-ISO-10303-21" not in ende.upper():
        return HINWEIS, "STEP-Datei unvollständig (Ende fehlt, abgebrochene Übertragung?) – Messung versucht es " \
                        "trotzdem, bitte Ergebnis prüfen"
    return None


def standard_ordner():
    """Ordner für entpackte Archive: je Benutzer im Temp-Ordner (mehrere Benutzer auf einem PC stören sich nicht)."""
    try:
        import getpass
        wer = "".join(c for c in getpass.getuser() if c.isalnum())[:30]
    except Exception:       # noqa: BLE001 – ohne Benutzernamen ein gemeinsamer Ordner
        wer = ""
    return Path(tempfile.gettempdir()) / (f"{ENTPACKT}-{wer}" if wer else ENTPACKT)


def _aufraeumen(basis):
    grenze = time.time() - AUFHEBEN_TAGE * 86400
    try:
        for d in basis.iterdir():
            if d.is_dir() and d.stat().st_mtime < grenze:
                shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass


def _sicherer_name(name):
    """Pfad im Archiv als relative Teile ohne Laufwerk, '..' und leere Teile (Schutz vor Zip Slip)."""
    teile = [t for t in str(name).replace("\\", "/").split("/") if t not in ("", ".", "..") and ":" not in t]
    return teile


def entpacken(zip_pfad, basis=None, tiefe=0, befunde=None, name=None):
    """ZIP entpacken (verschachtelt bis ZIP_TIEFE). Ergebnis: [Pfad entpackter Dateien] (ohne ZIP-Dateien selbst)."""
    befunde = befunde if befunde is not None else []
    name = name or Path(zip_pfad).name
    basis = Path(basis) if basis else standard_ordner()
    try:
        basis.mkdir(parents=True, exist_ok=True)
        if tiefe == 0:
            _aufraeumen(basis)
        ziel = basis / f"{Path(zip_pfad).stem[:40]}-{_sha(zip_pfad)[:12]}"
    except OSError as e:
        befunde.append(dict(datei=name, stufe=FEHLER, text=f"ZIP nicht lesbar ({e})"))
        return []
    out = []
    try:
        with zipfile.ZipFile(zip_pfad) as z:
            eintraege = [i for i in z.infolist() if not i.is_dir()]
            if len(eintraege) > ZIP_MAX_DATEIEN:
                befunde.append(dict(datei=name, stufe=FEHLER, text=f"ZIP mit {len(eintraege)} Dateien – mehr als "
                                    f"{ZIP_MAX_DATEIEN}, nicht entpackt"))
                return []
            if sum(i.file_size for i in eintraege) > ZIP_MAX_MB * 2 ** 20:
                befunde.append(dict(datei=name, stufe=FEHLER, text=f"ZIP entpackt größer als {ZIP_MAX_MB} MB – "
                                    "nicht entpackt (bitte Dateien einzeln importieren)"))
                return []
            for i in eintraege:
                teile = _sicherer_name(i.filename)
                if not teile:
                    continue
                if i.flag_bits & 0x1:
                    befunde.append(dict(datei=f"{name}/{'/'.join(teile)}", stufe=FEHLER,
                                        text="verschlüsselt (Kennwort) – nicht entpackt"))
                    continue
                datei = ziel.joinpath(*teile)
                if not datei.resolve().is_relative_to(ziel.resolve()):
                    continue
                if not datei.is_file() or datei.stat().st_size != i.file_size:
                    datei.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(i) as quelle, open(datei, "wb") as senke:
                        shutil.copyfileobj(quelle, senke)
                if datei.suffix.lower() in ZIP_ENDUNGEN:
                    if tiefe + 1 >= ZIP_TIEFE:
                        befunde.append(dict(datei=f"{name}/{'/'.join(teile)}", stufe=HINWEIS,
                                            text=f"ZIP in ZIP tiefer als {ZIP_TIEFE} Ebenen – übersprungen"))
                        continue
                    out.extend(entpacken(datei, ziel / "_zip", tiefe + 1, befunde, f"{name}/{'/'.join(teile)}"))
                else:
                    out.append(datei)
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError) as e:
        befunde.append(dict(datei=name, stufe=FEHLER, text=f"ZIP defekt oder nicht lesbar ({e})"))
    return out


def vorbereiten(pfade, basis=None):
    """Dateien, Ordner und ZIPs zu Vorbereitung (siehe Modultext). Reihenfolge wie gewählt, Ordner sortiert."""
    erg = Vorbereitung()
    gesehen, inhalte, andere = set(), {}, {}

    def nimm(p, anzeige, aus_zip=None):
        e = p.suffix.lower()
        if e in ZIP_ENDUNGEN:
            for x in entpacken(p, basis, 0, erg.befunde, anzeige):
                erg.herkunft[x] = aus_zip or anzeige
                nimm(x, f"{anzeige}/{x.name}", aus_zip or anzeige)
            return
        if e in NATIV:
            text = NETZ_TEXT if e in (".stl", ".obj") else NATIV_TEXT
            erg.befunde.append(dict(datei=anzeige, stufe=FEHLER, text=text.format(art=NATIV[e], endung=p.suffix)))
            return
        if e not in CAD_ENDUNGEN:
            andere[e or "(ohne Endung)"] = andere.get(e or "(ohne Endung)", 0) + 1
            return
        try:
            schluessel = p.resolve()
        except OSError:
            schluessel = p
        if schluessel in gesehen:
            return
        gesehen.add(schluessel)
        befund = step_pruefen(p) if e in STEP_ENDUNGEN else None
        if befund and befund[0] == FEHLER:
            erg.befunde.append(dict(datei=anzeige, stufe=FEHLER, text=befund[1]))
            return
        try:
            sha = _sha(p)
        except OSError as ex:
            erg.befunde.append(dict(datei=anzeige, stufe=FEHLER, text=f"Datei nicht lesbar ({ex})"))
            return
        if sha in inhalte:
            erg.befunde.append(dict(datei=anzeige, stufe=HINWEIS,
                                    text=f"gleicher Inhalt wie {inhalte[sha]} – nur einmal gemessen"))
            return
        inhalte[sha] = anzeige
        if befund:
            erg.befunde.append(dict(datei=anzeige, stufe=befund[0], text=befund[1]))
        erg.dateien.append(p)

    for roh in pfade or ():
        p = Path(roh)
        if p.is_dir():
            for x in sorted(y for y in p.rglob("*") if y.is_file()):
                nimm(x, str(x.relative_to(p.parent)))
        elif p.exists():
            nimm(p, p.name)
        else:
            erg.befunde.append(dict(datei=p.name, stufe=FEHLER, text="Datei nicht gefunden"))
    for p in blm_doppelte(erg.dateien):
        erg.dateien.remove(p)
        erg.befunde.append(dict(datei=p.name, stufe=HINWEIS, text=f"gehört zu {p.stem}.artube daneben – nur einmal "
                                "gemessen (die ARTUBE nimmt das BPF für den exakten Querschnitt)"))
    if andere:
        erg.befunde.append(dict(datei="andere Dateien", stufe=HINWEIS, text="übersprungen: " + ", ".join(
            f"{n}× {e}" for e, n in sorted(andere.items(), key=lambda x: -x[1]))))
    return erg


def blm_doppelte(dateien):
    """BPF-Dateien, deren ArTube-Projekt (gleicher Name, gleicher Ordner) auch in der Liste steht: die ARTUBE liest das
    BPF daneben selbst (Teil nur einmal messen)."""
    artube = {(Path(p).parent, Path(p).stem.lower()) for p in dateien if Path(p).suffix.lower() == ".artube"}
    return [p for p in dateien if Path(p).suffix.lower() == ".bpf" and (Path(p).parent, Path(p).stem.lower()) in artube]


def fehler_zeilen(vorbereitung, vorlage=None):
    """Messwert-Zeilen für nicht messbare Dateien (Fehler-Befunde): rot im Prüfdialog, „nicht messbar“ im
    Importbericht. vorlage = eine Messwert-Zeile, deren Schlüssel leer übernommen werden."""
    out = []
    for b in vorbereitung.fehler():
        if b["datei"] == "andere Dateien":
            continue
        z = {k: "" for k in (vorlage or {}) if not str(k).startswith("_")}
        z.update(datei=Path(b["datei"]).name, artikel=Path(b["datei"]).stem, koerper="1", fehler=b["text"],
                 pruefstatus="nicht messbar", _import_befund=True)
        out.append(z)
    return out
