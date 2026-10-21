"""Zeichnungen und Dokumente je Position: Die Datei wird in den Ordner des Angebots kopiert
(Ablageordner/<Angebotsnummer>/), in der Position steht nur der Dateiname (positionen.dokumente, JSON-Liste).
So bleibt das Angebot vollständig, auch wenn die Originaldatei verschoben oder gelöscht wird.

Gleicher Name mit gleichem Inhalt wird wiederverwendet, gleicher Name mit anderem Inhalt bekommt ' (2)', ' (3)' …
"""
import filecmp
import json
import shutil
from pathlib import Path

from .ausgabe import dateiname

ENDUNGEN = (".pdf", ".step", ".stp", ".dxf", ".dwg", ".png", ".jpg", ".jpeg", ".tif", ".tiff")


def ordner(ablage, kopf):
    """Ordner der Dokumente eines Angebots: <Ablage>/<Angebotsnummer> (wird bei Bedarf angelegt)."""
    return Path(ablage) / dateiname(kopf)


def liste(text):
    """Dateinamen aus positionen.dokumente."""
    try:
        d = json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
    return [str(x) for x in d if x] if isinstance(d, list) else []


def text(namen):
    """Dateinamen für positionen.dokumente (None = keine)."""
    namen = list(dict.fromkeys(n for n in namen if n))
    return json.dumps(namen, ensure_ascii=False) if namen else None


def kurz(text_):
    """Anzeige in der Positionsliste: 'Z-100.pdf' bzw. '3 Dateien'."""
    n = liste(text_)
    return "" if not n else n[0] if len(n) == 1 else f"{len(n)} Dateien"


def passend(pfade):
    """Nur Dateien mit bekannter Endung (Zeichnung, Modell, Bild)."""
    return [Path(p) for p in pfade if Path(p).suffix.lower() in ENDUNGEN and Path(p).is_file()]


def kopieren(ziel_ordner, quelle):
    """Datei in den Ordner des Angebots kopieren. Ergebnis: Dateiname im Ordner."""
    quelle, ziel_ordner = Path(quelle), Path(ziel_ordner)
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    ziel = ziel_ordner / quelle.name
    n = 2
    while ziel.exists():
        if ziel.resolve() == quelle.resolve() or filecmp.cmp(ziel, quelle, shallow=False):
            return ziel.name
        ziel = ziel_ordner / f"{quelle.stem} ({n}){quelle.suffix}"
        n += 1
    shutil.copy2(quelle, ziel)
    return ziel.name


def anhaengen(ziel_ordner, vorhanden, quellen):
    """Dateien kopieren und an die vorhandene Liste (Text aus positionen.dokumente) anhängen. Ergebnis: neuer Text."""
    return text(liste(vorhanden) + [kopieren(ziel_ordner, q) for q in quellen])


def pfade(ziel_ordner, text_):
    """[(Dateiname, Pfad, vorhanden)] einer Position."""
    return [(n, Path(ziel_ordner) / n, (Path(ziel_ordner) / n).is_file()) for n in liste(text_)]
