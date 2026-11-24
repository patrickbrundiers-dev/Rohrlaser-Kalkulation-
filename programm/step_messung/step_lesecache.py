"""Lese-Zwischenspeicher der STEP-Messung (CAD-Kern 3.0, Master-Auftrag Patrick 24.11.2026).

Befund aus dem Profiling (docs/performance/cad_kern_3_2411.md): Beim Einlesen großer Baugruppen geht fast die ganze
Zeit in die Formheilung von OpenCascade, genauer in das Ergänzen fehlender Flächenkurven (ShapeFix_Edge::FixAddPCurve
→ ShapeConstruct_ProjectCurveOnSurface → Extrema_GenExtPS auf Freiformflächen). Bei U_29MB.step (870 Körper) sind
das rund 290 s von 292 s. Diese Rechnung steckt in OpenCascade (C++) und lässt sich von außen weder abschalten (die
Kurven sind für gültige Körper nötig) noch bitgleich verkürzen.

Was sich vermeiden lässt, ist sie zu wiederholen: Dieselbe Datei wird oft mehrmals gemessen (nach einem Programm-
Update ist der Ergebnis-Zwischenspeicher leer, nach geänderten Einstellungen, beim Nachladen der 3D-Daten, bei einem
Neu-Messen nach Zeitlimit). Das Einlesen hängt aber nur vom Inhalt der Datei, ihrem Namen und dem Lesecode ab, nicht
von den Einstellungen der Messung. Deshalb merkt sich dieser Speicher die gelesenen und geheilten Körper als
OpenCascade-Binärdatei (BinTools, Zahlen bitgenau) mit Info, Kopien und gedrehten Kopien.

Schlüssel: SHA-256 des Dateiinhalts, Dateiname ohne Endung (Name der Baugruppenwurzel), LESER_STAND, OpenCascade-
Version. LESER_STAND bei jeder Änderung am Lesen hochzählen (lies_step_info, _caf_uebertragen, _struktur, _naehen,
_instanzen, _gedrehte, _grosse_datei_einstellen, _einheit, IGES-Lesen); tests/test_cad_kern_3_2411.py prüft das über
eine Prüfsumme des Quelltexts.

Bitgleichheit: BinTools schreibt Richtungen (gp_Dir, gp_Dir2d, auch in den Flächenkurven) als Zahlen und normiert sie
beim Lesen neu; dabei kann die letzte Binärstelle kippen (gemessen: Flächenkurven um 1e-16 anders). Die Messung ist an
einigen Stellen so empfindlich, dass daraus andere Stützstellen werden (126 Prüf-STEPs: 3 Dateien mit anderen
z-Lagen der Wandstärken-Einzelmessungen, K08 mit bis 0,23 mm anderem Umriss einer Kontur der Auswahl „geschlossen“).
Deshalb misst das Programm bei eingeschaltetem Speicher schon beim ersten Lesen die gemerkte (einmal geschriebene und
wieder gelesene) Form: erstes Lesen, jedes Wiedereinlesen und alle Messprozesse rechnen dann bitgleich. Dieselbe
Umwandlung macht der Schnappschuss für die Messprozesse einer verteilten Datei (step_messen._schnappschuss_*) schon
seit 06.11.2026 – ohne diesen Speicher hängen dort die letzten Stellen davon ab, welcher Prozess einen Körper misst.

Ab AB_S Sekunden Lesedauer wird gemerkt (Vorgabe 0: jede STEP/IGES-Datei, damit alle Messungen dieselbe Form sehen).
Der Speicher liegt im Zwischenspeicher-Ordner der Messung (--cache, Einträge lesen_<Schlüssel>) und wird
mit ihm auf --cache-mb begrenzt (älteste zuerst weg).
"""
import hashlib
import json
import os
import pickle
import time
from pathlib import Path

LESER_STAND = 2
AB_S = 0.0                  # s: erst ab dieser Lesedauer merken (0 = immer, siehe Bitgleichheit)
UMGEBUNG = "STEP_LESECACHE"     # Ordner (vom Messprogramm gesetzt, gilt so auch in den Messprozessen)
ENDUNGEN = (".step", ".stp", ".igs", ".iges")
VORSILBE = "lesen_"


def ordner():
    o = os.environ.get(UMGEBUNG)
    return Path(o) if o else None


def _ocp_version():
    try:
        import OCP
        return getattr(OCP, "__version__", "") or ""
    except ImportError:
        return ""


def schluessel(pfad):
    """Schlüssel des Eintrags oder None (andere Dateiart, nicht lesbar)."""
    p = Path(pfad)
    if p.suffix.lower() not in ENDUNGEN:
        return None
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError:
        return None
    h.update(json.dumps([LESER_STAND, _ocp_version(), p.stem]).encode("utf-8"))
    return h.hexdigest()


def formen_schreiben(pfad, koerper, daten):
    """Körper [(Art, Form)] als BinTools-Datei pfad und daten (picklebar) daneben als .pkl; True bei Erfolg.
    Erst in Zeitdateien, dann umbenennen (ein gleichzeitiger Leser sieht nie eine halbe Datei)."""
    from OCP.BinTools import BinTools
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    pfad = Path(pfad)
    tmp = pfad.with_suffix(f".{os.getpid()}.tmp")
    try:
        c = TopoDS_Compound()
        b = BRep_Builder()
        b.MakeCompound(c)
        for _, k in koerper:
            b.Add(c, k)
        BinTools.Write_s(c, str(tmp))
        tmp.with_suffix(".pkl").write_bytes(pickle.dumps((daten, [a for a, _ in koerper])))
        os.replace(tmp.with_suffix(".pkl"), pfad.with_suffix(".pkl"))
        os.replace(tmp, pfad)
        return True
    except Exception:       # nur Beschleunigung
        for x in (tmp, tmp.with_suffix(".pkl")):
            try:
                x.unlink()
            except OSError:
                pass
        return False


def formen_laden(pfad):
    """Gegenstück zu formen_schreiben: (Körper [(Art, Form)], daten) oder None."""
    from OCP.BinTools import BinTools
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopoDS import TopoDS, TopoDS_Iterator, TopoDS_Shape
    try:
        pfad = Path(pfad)
        if not pfad.is_file():
            return None
        daten, arten = pickle.loads(pfad.with_suffix(".pkl").read_bytes())
        s = TopoDS_Shape()
        BinTools.Read_s(s, str(pfad))
        it, formen = TopoDS_Iterator(s), []
        while it.More():
            formen.append(it.Value())
            it.Next()
        if len(formen) != len(arten):
            return None
        art = {TopAbs_SOLID: TopoDS.Solid, TopAbs_SHELL: TopoDS.Shell, TopAbs_FACE: TopoDS.Face,
               TopAbs_COMPOUND: TopoDS.Compound}
        return [(a, art.get(k.ShapeType(), lambda x: x)(k)) for a, k in zip(arten, formen)], daten
    except Exception:
        return None


def _eintrag(o, s):
    return Path(o) / f"{VORSILBE}{s}" / "formen.bin"


def laden(pfad):
    """(Körper, Info, gleich, gedreht) aus dem Speicher oder None. Info["phasen"] nennt die Ladezeit."""
    o = ordner()
    if o is None:
        return None
    uhr = time.monotonic()
    s = schluessel(pfad)
    if s is None:
        return None
    erg = formen_laden(_eintrag(o, s))
    if erg is None:
        return None
    koerper, (info, gleich, gedreht) = erg
    try:
        os.utime(_eintrag(o, s).parent)     # zuletzt benutzt (Begrenzen nach Alter)
    except OSError:
        pass
    info = dict(info)
    info["phasen"] = dict(lesecache_s=time.monotonic() - uhr, lesecache=1, verschoben=len(gleich),
                          gedreht=len(gedreht))
    return koerper, info, gleich, gedreht


def merken(pfad, koerper, info, gleich, gedreht):
    """Gelesene Datei merken, wenn das Lesen mindestens AB_S Sekunden gedauert hat."""
    o = ordner()
    if o is None:
        return False
    ph = info.get("phasen") or {}
    if sum(v for k, v in ph.items() if k.endswith("_s")) < float(os.environ.get("STEP_LESECACHE_AB", AB_S)):
        return False
    s = schluessel(pfad)
    if s is None:
        return False
    ziel = _eintrag(o, s)
    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return formen_schreiben(ziel, koerper, (info, gleich, gedreht))
