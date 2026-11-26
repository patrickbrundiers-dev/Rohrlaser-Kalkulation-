"""Ablage der Angebotsakte (Patrick 18.11.2026): Unterordner „Angebotsakte“ im vorhandenen Angebotsordner.

    <Angebotsordner>/Angebotsakte/
        PDF/                 Angebot_<Nr>_Gesamt.pdf, _Kunde.pdf, _Intern.pdf, _Technik.pdf (immer die neueste Fassung)
        PDF/Versionen/       ältere Fassungen: Angebot_<Nr>_Gesamt_V1_2026-11-18_1903.pdf
        Technische_Daten/    3D-Bilder je Position (PNG)
        Schnittschemata/     Angebot_<Nr>_Schnittschema.pdf (Seite 3 allein)
        Kalkulationsdaten/   kalkulation_V<n>.json (alle Werte der Akte), akte.json (Verzeichnis der Versionen)

Neu erzeugen überschreibt nie: die bisherige Datei wandert mit ihrer Versionsnummer und Zeit nach Versionen/.
akte.json hält je Version Datum, Bearbeiter, Fingerabdruck der Kalkulation, Netto, erzeugte Dokumente und Seiten;
damit zeigt die Angebotsübersicht „Akte aktuell“ oder „Akte veraltet“. Fassungen eines Angebots (Fassung 2 …) haben
ihren eigenen Angebotsordner und damit ihre eigene Akte. Ohne Qt."""
import datetime
import json
import shutil
from pathlib import Path

from .angebotsordner import sauber

ORDNER = "Angebotsakte"
PDF, VERSIONEN, TECHNIK, SCHNITT, DATEN = "PDF", "Versionen", "Technische_Daten", "Schnittschemata", "Kalkulationsdaten"
VERZEICHNIS = "akte.json"
AKTUELL, VERALTET = "aktuell", "veraltet"


def _angebotsordner(o):
    """Angebotsordner aus dem Angebotsordner oder dem Ordner der Akte selbst."""
    o = Path(o)
    return o.parent if o.name == ORDNER else o


def _akte(o):
    return _angebotsordner(o) / ORDNER


def ordner(angebotsordner, anlegen=True):
    o = Path(angebotsordner) / ORDNER
    if anlegen:
        for u in (PDF, Path(PDF) / VERSIONEN, TECHNIK, SCHNITT, DATEN):
            (o / u).mkdir(parents=True, exist_ok=True)
    return o


def dateiname(nummer, zusatz, endung=".pdf"):
    return f"Angebot_{sauber(nummer).replace(' ', '_') or 'ohne_Nummer'}_{zusatz}{endung}"


def verzeichnis(akte_ordner):
    """akte.json lesen: dict(versionen=[...]); fehlt oder beschädigt: leer."""
    try:
        d = json.loads((_akte(akte_ordner) / DATEN / VERZEICHNIS).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and isinstance(d.get("versionen"), list) else dict(versionen=[])
    except (OSError, ValueError):
        return dict(versionen=[])


def letzte(akte_ordner):
    v = verzeichnis(akte_ordner)["versionen"]
    return v[-1] if v else None


def stand(akte_ordner, fingerabdruck):
    """AKTUELL, VERALTET oder None (noch keine Akte)."""
    e = letzte(akte_ordner)
    if not e:
        return None
    return AKTUELL if e.get("fingerabdruck") == fingerabdruck else VERALTET


def _wegsichern(datei, version, versionen_ordner):
    """Vorhandene Datei mit Versionsnummer und Zeit nach Versionen/ verschieben (nie überschreiben)."""
    datei = Path(datei)
    if not datei.exists():
        return None
    zeit = datetime.datetime.fromtimestamp(datei.stat().st_mtime).strftime("%Y-%m-%d_%H%M")
    ziel = Path(versionen_ordner) / f"{datei.stem}_V{version or 0}_{zeit}{datei.suffix}"
    i = 1
    while ziel.exists():
        i += 1
        ziel = Path(versionen_ordner) / f"{datei.stem}_V{version or 0}_{zeit}_{i}{datei.suffix}"
    shutil.move(str(datei), str(ziel))
    return ziel


def naechste_version(akte_ordner):
    v = verzeichnis(akte_ordner)["versionen"]
    return (max((int(e.get("version") or 0) for e in v), default=0) + 1) if v else 1


def ablegen(akte_ordner, nummer, dokumente, akte_json=None, bilder=None, schnitt=None, eintrag=None):
    """Erzeugte Dateien in die Akte legen. dokumente = {art: fertige PDF-Datei (Zwischendatei)}, bilder =
    {Dateiname: PNG-Bytes}, schnitt = PDF nur mit dem Schnittschema, akte_json = Text der Akte, eintrag = Angaben für
    akte.json (erstellt, bearbeiter, fingerabdruck, netto, seiten). Ergebnis: dict(version, dateien {art: Pfad},
    gesichert [ältere Fassungen])."""
    from .angebotsakte import DATEI_ZUSATZ
    o = ordner(_angebotsordner(akte_ordner))
    alt = letzte(o)
    alt_version = int((alt or {}).get("version") or 0)
    version = naechste_version(o)
    dateien, gesichert = {}, []
    for art, quelle in (dokumente or {}).items():
        ziel = o / PDF / dateiname(nummer, DATEI_ZUSATZ.get(art, art))
        g = _wegsichern(ziel, alt_version, o / PDF / VERSIONEN)
        if g:
            gesichert.append(g)
        shutil.copyfile(quelle, ziel)
        dateien[art] = ziel
    if schnitt:
        ziel = o / SCHNITT / dateiname(nummer, "Schnittschema")
        g = _wegsichern(ziel, alt_version, o / SCHNITT)
        if g:
            gesichert.append(g)
        shutil.copyfile(schnitt, ziel)
        dateien["schnittschema"] = ziel
    for name, png in (bilder or {}).items():
        (o / TECHNIK / sauber(name)).write_bytes(png)
    if akte_json is not None:
        ziel = o / DATEN / f"kalkulation_V{version}.json"
        ziel.write_text(akte_json, encoding="utf-8")
        dateien["kalkulationsdaten"] = ziel
    v = verzeichnis(o)
    e = dict(eintrag or {}, version=version, dateien={a: Path(p).name for a, p in dateien.items()},
             gespeichert=datetime.datetime.now().isoformat(timespec="seconds"))
    v["versionen"].append(e)
    v["nummer"] = nummer
    tmp = o / DATEN / (VERZEICHNIS + ".neu")
    tmp.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(o / DATEN / VERZEICHNIS)
    return dict(version=version, dateien=dateien, gesichert=gesichert, ordner=o)


def datei(akte_ordner, nummer, art, finden=None):
    """Pfad des neuesten Dokuments der Art (kunde/intern/gesamt) oder None. finden(pfad) -> neuer Pfad oder None:
    sucht ein in den PPEASE-Angebotsordner verschobenes Dokument (ppease_ablage.wo, 26.11.2026)."""
    from .angebotsakte import DATEI_ZUSATZ
    o = _akte(akte_ordner)
    p = o / PDF / dateiname(nummer, DATEI_ZUSATZ.get(art, art))
    if p.exists():
        return p
    try:
        return finden(p) if finden else None
    except OSError:
        return None


def versionen(akte_ordner):
    """Ältere Fassungen (neueste zuerst)."""
    o = _akte(akte_ordner)
    try:
        return sorted((p for p in (o / PDF / VERSIONEN).iterdir() if p.suffix.lower() == ".pdf"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
