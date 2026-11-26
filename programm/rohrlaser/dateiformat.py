"""Dateiformat am Inhalt erkennen (Importengine 2.0, Master-Auftrag Patrick 26.11.2026, Punkt 5: „Dateiendungen allein
reichen nicht zur sicheren Identifizierung des Formats. Hersteller, Softwareversion, Dateistruktur und tatsächlicher
Inhalt müssen berücksichtigt werden“). Ohne Qt und ohne OpenCascade; gemeinsam für Hauptprogramm (cad_import),
STEP-Messung (step_geometrie.lies_step_info) und Serverversion.

erkennen(pfad) -> Format mit
- art: STEP, IGES, TUBX, LST, LST_AUFTRAG (TRUMPF-Fertigungsauftrag ohne Schneidweg), BPF, ARTUBE, ZIP, sonst eines
  der Herstellerformate (MEGACAD, OLE = SolidWorks/Inventor/Solid Edge, CATIA, PARASOLID, ACIS, STL) oder UNBEKANNT
- hersteller, software, version: was die Datei selbst über sich sagt (leer, wenn nicht enthalten – nie geraten)
- endung_passt: Endung und Inhalt stimmen überein
- felder: weitere Angaben aus dem Kopf (Schema, CAD-System, Maschine, Profil …) als {Name: Wert}
- unbekannt: erkannte, aber nicht ausgewertete Bestandteile (z. B. Parasolid-Körper in der ARTUBE)

Geprüft wird nur der Anfang der Datei (KOPF Bytes) bzw. das Inhaltsverzeichnis eines Archivs: billig genug für jede
Datei beim Darüberziehen. Gelesen wird die Datei danach vom jeweiligen Leser (step_geometrie, step_tubx, step_lst,
step_blm) – Erkennen und Lesen sind getrennt, das Erkennen ändert kein Messergebnis.

Formatwissen (geprüft an Patricks Dateien aus den Supportpaketen, Kundendaten nicht im Repo):
- STEP: Textkopf „ISO-10303-21;“, FILE_NAME(… originating_system …), FILE_SCHEMA((…)).
- IGES: Zeilen zu 80 Zeichen, Spalte 73 Abschnittskennung S/G/D/P/T, Start mit S.
- TUBX (TRUMPF TubeCAM): ZIP (OPC) mit Task3D/…bson und tubeProps/app.xml (appVersion „TubeCAM (Version: 5.1.1…)“,
  profileType, machineId).
- LST (TRUMPF TruTops/Programming Tube): Text, Blöcke „BD“, „SET_METRIC“, BEGIN_EINRICHTEPLAN_INFO mit
  ProgrammingSystemSignature („Programming Tube 5.1.1…“), NC-Teil BEGIN_PROGRAMM. Ein Fertigungsauftrag
  (BEGIN_FERTIGUNG_AUFTRAG_TMP ohne BEGIN_PROGRAMM) enthält Programmnamen und Sollanzahl, aber keinen Schneidweg.
- BPF (BLM/Adige): Kopf „(c) Adige S.p.A. BLMGroup …“, danach zlib-gepackte Blöcke (step_blm).
- ARTUBE (BLM ArTube): tar-Archiv mit __ACF_FILE_SIGNATURE__ und _files/metadata, Teile als OBJ, Körper Parasolid.
"""
import re
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

KOPF = 64 * 1024

STEP, IGES, TUBX, LST, LST_AUFTRAG, BPF, ARTUBE, ZIP = ("STEP", "IGES", "TUBX", "LST", "LST_AUFTRAG", "BPF", "ARTUBE",
                                                       "ZIP")
MEGACAD, OLE, CATIA, PARASOLID, ACIS, STL, UNBEKANNT, LEER = ("MEGACAD", "OLE", "CATIA", "PARASOLID", "ACIS", "STL",
                                                              "UNBEKANNT", "LEER")
# Endungen je Art (zum Abgleich „Endung passt“)
ENDUNGEN = {STEP: {".step", ".stp"}, IGES: {".igs", ".iges"}, TUBX: {".tubx"}, LST: {".lst"}, LST_AUFTRAG: {".lst"},
            BPF: {".bpf"}, ARTUBE: {".artube"}, ZIP: {".zip"}, MEGACAD: {".mac", ".prt"},
            OLE: {".sldprt", ".sldasm", ".ipt", ".iam", ".par", ".psm", ".asm"}, CATIA: {".catpart", ".catproduct"},
            PARASOLID: {".x_t", ".x_b"}, ACIS: {".sat", ".sab"}, STL: {".stl"}}
# Arten, die der STEP-Import messen kann (Rest: Meldung)
MESSBAR = {STEP, IGES, TUBX, LST, BPF, ARTUBE}
NAMEN = {STEP: "STEP", IGES: "IGES", TUBX: "TRUMPF TubeCAM (TUBX)", LST: "TRUMPF-LST", LST_AUFTRAG:
         "TRUMPF-Fertigungsauftrag (LST ohne Schneidweg)", BPF: "BLM-Teileprogramm (BPF)", ARTUBE:
         "BLM ArTube-Projekt", ZIP: "ZIP-Archiv", MEGACAD: "MegaCAD-Datei", OLE: "Herstellerformat (OLE: SolidWorks, "
         "Inventor oder Solid Edge)", CATIA: "CATIA-Datei", PARASOLID: "Parasolid-Datei", ACIS: "ACIS-Datei",
         STL: "STL-Netz", UNBEKANNT: "unbekanntes Format", LEER: "leere Datei"}


@dataclass
class Format:
    art: str
    endung: str = ""
    hersteller: str = ""
    software: str = ""
    version: str = ""
    felder: dict = field(default_factory=dict)
    unbekannt: list = field(default_factory=list)
    fehler: str = ""

    @property
    def endung_passt(self):
        return self.endung in ENDUNGEN.get(self.art, set())

    @property
    def messbar(self):
        return self.art in MESSBAR

    @property
    def name(self):
        return NAMEN.get(self.art, self.art)

    def text(self):
        """Eine Zeile für Importbericht und Prüfdialog."""
        t = self.name
        quelle = " ".join(x for x in (self.software, self.version) if x)
        if quelle:
            t += f" aus {quelle}"
        if self.felder.get("ap"):
            t += f", {self.felder['ap']}"
        if self.hersteller and self.hersteller not in t:
            t += f" ({self.hersteller})"
        return t

    def hinweis(self):
        """Text, wenn Endung und Inhalt nicht zusammenpassen, sonst ""."""
        if self.art in (UNBEKANNT, LEER) or self.endung_passt:
            return ""
        return f"Endung {self.endung or '(ohne)'} passt nicht zum Inhalt: {self.name}"


def _text(kopf):
    return kopf.decode("latin-1", "replace")


def _argumente(text):
    """Argumente einer STEP-Parameterliste auf oberster Ebene (Kommas in Klammern und Texten zählen nicht); Texte ohne
    Anführungszeichen, Listen als ein Text."""
    out, akt, tiefe, im_text = [], [], 0, False
    i = 0
    while i < len(text):
        c = text[i]
        if im_text:
            if c == "'" and text[i + 1:i + 2] == "'":
                akt.append("'")
                i += 1
            elif c == "'":
                im_text = False
            else:
                akt.append(c)
        elif c == "'":
            im_text = True
        elif c == "(":
            tiefe += 1
        elif c == ")":
            tiefe -= 1
        elif c == "," and tiefe == 0:
            out.append("".join(akt).strip())
            akt = []
        elif tiefe > 0 or not c.isspace():
            akt.append(c)
        i += 1
    out.append("".join(akt).strip())
    return out


def _step(kopf, f):
    t = _text(kopf)
    m = re.search(r"FILE_NAME\s*\((.*?)\)\s*;", t, re.S)
    if m:
        # FILE_NAME(name, time_stamp, (author), (organization), preprocessor_version, originating_system,
        # authorisation)
        arg = _argumente(m.group(1))
        if len(arg) >= 6:
            f.felder["zeitpunkt"] = arg[1]
            f.felder["praeprozessor"] = arg[4]
            f.software = arg[5].strip()
    m = re.search(r"FILE_SCHEMA\s*\(\s*\((.*?)\)\s*\)", t, re.S)
    if m:
        schema = " ".join(re.findall(r"'([^']*)'", m.group(1)))
        f.felder["schema"] = schema
        s = schema.upper()
        f.felder["ap"] = ("AP242" if "AP242" in s or "MANAGED_MODEL_BASED" in s else "AP214" if "AUTOMOTIVE_DESIGN" in s
                     else "AP203" if "CONFIG_CONTROL_DESIGN" in s else "")
    return f


def _iges_felder(g, n=8):
    """Erste n Felder des IGES-Global-Abschnitts; Texte als Hollerith (5Hhallo), Trenner Komma (Feld 1 darf ihn
    selbst als 1H, angeben)."""
    out, i = [], 0
    while i < len(g) and len(out) < n:
        m = re.match(r"\s*(\d+)H", g[i:])
        if m:
            lg = int(m.group(1))
            start = i + m.end()
            out.append(g[start:start + lg])
            i = start + lg
        else:
            j = i
            while j < len(g) and g[j] not in ",;":
                j += 1
            out.append(g[i:j].strip())
            i = j
        if i < len(g) and g[i] in ",;":
            i += 1
    return out


def _iges(kopf, f):
    zeilen = _text(kopf).splitlines()
    g = "".join(z[:72] for z in zeilen[:80] if len(z) >= 73 and z[72] == "G")
    teile = _iges_felder(g)
    # 1 Parametertrenner, 2 Satztrenner, 3 Sender-Produkt, 4 Dateiname, 5 System des Senders, 6 Präprozessor
    if len(teile) >= 5:
        f.felder["sender"] = teile[2]
        f.software = teile[4].strip()
    if len(teile) >= 6:
        f.felder["praeprozessor"] = teile[5].strip()
    return f


def _zip(pfad, f):
    try:
        with zipfile.ZipFile(pfad) as z:
            namen = z.namelist()
            if any(n.startswith("Task3D/") for n in namen) and "tubeProps/app.xml" in namen:
                f.art, f.hersteller = TUBX, "TRUMPF"
                try:
                    xml = z.read("tubeProps/app.xml")[:20000].decode("utf-8", "replace")
                except (KeyError, OSError, zipfile.BadZipFile):
                    xml = ""
                for name, schl in (("appVersion", "app"), ("profileType", "profil"), ("profileId", "profil_id"),
                                   ("machineId", "maschine"), ("material", "werkstoff"), ("thickness", "wand")):
                    m = re.search(rf"<{name}>(.*?)</{name}>", xml, re.S)
                    if m:
                        f.felder[schl] = m.group(1).strip()
                app = f.felder.pop("app", "")
                m = re.match(r"\s*(\w[\w ]*?)\s*\(Version:\s*([^;)]+)", app)
                if m:
                    f.software, f.version = m.group(1), m.group(2).strip()
                elif app:
                    f.software = app
                bekannt = ("Task3D/", "tubeProps/", "_rels/", "[Content_Types].xml", "package/", "Preview/", "LTT/",
                           "Settings/")
                f.unbekannt = sorted({n.split("/")[0] for n in namen if not n.startswith(bekannt)})
            else:
                f.art = ZIP
                f.felder["eintraege"] = len(namen)
    except (zipfile.BadZipFile, OSError) as e:
        f.art, f.fehler = ZIP, f"ZIP defekt ({e})"
    return f


LST_MAX = 16 * 2 ** 20     # LST ganz lesen bis zu dieser Größe (Schneidweg steht hinter dem Kopf)


def _lst(pfad, kopf, f):
    try:
        with open(pfad, "rb") as d:
            kopf = d.read(LST_MAX)
    except OSError:
        pass
    t = _text(kopf)
    f.hersteller = "TRUMPF"
    # Fertigungsauftrag: Liste der Programme mit Sollanzahl; enthält er die Programme selbst, ist er messbar
    f.art = LST if "BEGIN_PROGRAMM" in t else LST_AUFTRAG
    if "BEGIN_FERTIGUNG_AUFTRAG" in t:
        f.felder["fertigungsauftrag"] = True
        f.felder["programme"] = sorted(set(re.findall(r"(?m)^DA,'[^']*','[^']*','([^']+)'", t)))
    f.felder["programme_n"] = len(re.findall(r"(?m)^BEGIN_PROGRAMM", t))
    m = re.search(r"'ProgrammingSystemSignature'.*", t)
    sig = re.search(r"'(Programming Tube[^']*|TruTops[^']*)'", t)
    if sig:
        teile = sig.group(1).rsplit(" ", 1)
        f.software, f.version = (teile[0], teile[1]) if len(teile) == 2 and re.match(r"\d", teile[1]) else (
            sig.group(1), "")
    elif m:
        f.software = "TRUMPF-Programmiersystem"
    m = re.search(r"DA,'(T\d+)',\d+,'([^']*)'", t)
    if m:
        f.felder["maschine"], f.felder["steuerung"] = m.group(1), m.group(2)
    return f


def _artube(pfad, f):
    f.hersteller, f.software = "BLM Group (Adige)", "ArTube"
    try:
        with tarfile.open(pfad) as t:
            namen = t.getnames()
    except (tarfile.TarError, OSError) as e:
        f.fehler = f"ARTUBE-Archiv defekt ({e})"
        return f
    f.felder["teile_obj"] = sum(1 for n in namen if n.startswith("_files/obj/parts/"))
    if any(n.endswith((".x_t", ".x_b", ".xmt_txt", ".xmt_bin")) or "parasolid" in n.lower() for n in namen):
        f.unbekannt.append("Parasolid-Körper (nicht lesbar, gemessen wird aus BPF bzw. OBJ-Netz)")
    return f


def erkennen(pfad):
    """Format der Datei am Inhalt (siehe Modultext). Liest höchstens KOPF Bytes bzw. das Archiv-Verzeichnis."""
    p = Path(pfad)
    f = Format(UNBEKANNT, endung=p.suffix.lower())
    try:
        with open(p, "rb") as d:
            kopf = d.read(KOPF)
    except OSError as e:
        f.fehler = f"Datei nicht lesbar ({e.strerror or e})"
        return f
    if not kopf:
        f.art = LEER
        return f
    k = kopf.lstrip(b"\xef\xbb\xbf \t\r\n")
    if k[:12].upper() == b"ISO-10303-21":
        f.art = STEP
        return _step(kopf, f)
    if kopf[:4] == b"PK\x03\x04":
        return _zip(p, f)
    if b"Adige S.p.A." in kopf[:200] and b"BLM" in kopf[:200]:
        f.art, f.hersteller, f.software = BPF, "BLM Group (Adige)", "ArTube/BLMelements"
        m = re.search(rb"BLMGroup\s+(\d{4})", kopf[:200])
        if m:
            f.felder["kopf_jahr"] = m.group(1).decode()
        return f
    if kopf[:22] == b"__ACF_FILE_SIGNATURE__":      # tar ohne ustar-Kennung, erster Eintrag ist die Signatur
        f.art = ARTUBE
        return _artube(p, f)
    if kopf[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        f.art = OLE
        return f
    if kopf[:7] == b"MegaCad":
        f.art, f.software = MEGACAD, "MegaCAD"
        m = re.match(rb"MegaCad(\d+)", kopf)
        f.version = m.group(1).decode() if m else ""
        return f
    if kopf[:8] == b"V5_CFV2\x00" or b"CATIA" in kopf[:64]:
        f.art = CATIA
        return f
    if k[:20].startswith(b"**ABCDEFGHIJKLMNOPQR") or k[:8] == b"PS\x00\x00\x00":
        f.art = PARASOLID
        return f
    if kopf[:5].lower() == b"solid" or (p.suffix.lower() == ".stl" and len(kopf) > 84):
        f.art = STL
        return f
    zeilen = k.split(b"\n", 2)
    if zeilen and len(zeilen[0].rstrip(b"\r")) == 80 and zeilen[0][72:73] == b"S":
        f.art = IGES
        return _iges(kopf, f)
    if k[:2] == b"BD" and (b"SET_METRIC" in kopf[:200] or b"BEGIN_" in kopf[:400]):
        return _lst(p, kopf, f)
    if re.match(rb"\d+ \d+ \d+", k[:20]) and p.suffix.lower() in (".sat", ".sab"):
        f.art = ACIS
    return f
