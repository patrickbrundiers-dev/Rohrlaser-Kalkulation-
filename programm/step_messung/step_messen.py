"""STEP-Messung für den STEP-Import des Programms (wird als STEP-Import.exe ausgeliefert).

Misst je Körper Profil, Länge, Schneidweg und Konturen (step_geometrie.py), dazu Importdaten (Einheit der Datei,
Körperart, Geometrieprüfung, Volumen, Oberfläche, Flächen-/Kantenzahl, Hüllquader, Meldungen des STEP-Lesers).
Flächenmodelle werden zu Volumen genäht; was nicht messbar ist, steht mit Hinweis als eigene Zeile drin.
und schreibt die Messwerte als Textdatei (UTF-8, Tabulator-getrennt, Dezimalpunkt).
"STEP importieren" im Programm startet diese Messung und übernimmt die Werte ins Angebot.

Aufruf:
    STEP-Import.exe --ausgabe MESSWERTE.txt [--netze ORDNER] (--liste DATEILISTE.txt | DATEI_ODER_ORDNER ...)

--netze ORDNER: je Teil zusätzlich ein Dreiecksnetz für die 3D-Ansicht als JSON-Datei (Spalte "netz" = Dateiname).

DATEILISTE.txt: ein Pfad je Zeile (UTF-8). Rückgabewert 0 = alle Dateien gelesen,
1 = mindestens eine Datei mit Fehler (steht in der Spalte "fehler"), 2 = Aufruf falsch.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from step_geometrie import analysiere_datei  # noqa: E402

PROZESSE_MAX = 4      # gleichzeitige Messprozesse bei vielen Dateien (jeder lädt OpenCascade einmal)
SPALTEN = ["datei", "artikel", "koerper", "profilform", "abm_a", "abm_b", "wandstaerke", "flaeche", "laenge",
           "schneidweg", "konturen", "ende_a", "ende_a_gerade", "ende_b", "ende_b_gerade", "innen",
           "innen_konturen", "gravur", "gravur_konturen", "bohrungen", "innen_liste", "profil_id_vorschlag",
           "hinweise", "einheit", "koerperart", "gueltig", "volumen", "oberflaeche", "n_flaechen", "n_kanten",
           "huelle", "meldungen", "innen_a", "innen_b", "wand_messungen", "sicherheit", "konturen_liste", "netz",
           "fehler"]


def _z(x):
    return repr(float(x))


def _text(s):
    return str(s).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _analysiere(datei, netz=False):
    """Wie analysiere_datei; Pfade mit Umlauten o. ä. über eine Kopie mit einfachem Namen lesen,
    weil OpenCascade solche Pfade unter Windows nicht in jeder Version öffnet."""
    if str(datei).isascii() or not datei.is_file():
        return analysiere_datei(datei, netz)
    ordner = None   # auch der Temp-Ordner kann Umlaute enthalten (Benutzername)
    if not tempfile.gettempdir().isascii():
        ordner = next((p for p in (os.environ.get("PUBLIC"), os.environ.get("SystemDrive", "C:") + "\\")
                       if p and p.isascii() and os.access(p, os.W_OK)), None)
    with tempfile.TemporaryDirectory(dir=ordner) as tmp:
        kopie = Path(tmp) / "teil.step"
        shutil.copyfile(datei, kopie)
        teile = analysiere_datei(kopie, netz)
    for t in teile:
        t.datei = datei.stem
    return teile


def zeilen(datei, netze=None, nr=1):
    """Messwerte einer Datei als Zeilen (Liste von Feldern in der Reihenfolge SPALTEN). netze: Ordner für die
    Dreiecksnetze (None = keine), nr: laufende Nummer der Datei (Name der Netzdateien)."""
    try:
        teile = _analysiere(datei, netze is not None)
    except Exception as e:  # Datei defekt o. ä.: als Fehlerzeile melden
        return [[datei.name, datei.stem] + [""] * (len(SPALTEN) - 3) + [_text(e) or type(e).__name__]]
    out = []
    for t in teile:
        artikel = t.datei if len(teile) == 1 else f"{t.datei}-K{t.koerper}"
        netz = ""
        if netze is not None and t.netz:
            netz = f"{nr:05d}_{t.koerper}.json"
            (Path(netze) / netz).write_text(json.dumps(t.netz, separators=(",", ":")), encoding="utf-8")
        out.append([datei.name, artikel, str(t.koerper), t.profilform, _z(t.abm_a), _z(t.abm_b), _z(t.wandstaerke),
                    _z(t.flaeche), _z(t.laenge), _z(t.schneidweg), str(t.konturen), _z(t.ende_a),
                    "1" if t.ende_a_gerade else "0", _z(t.ende_b), "1" if t.ende_b_gerade else "0", _z(t.innen),
                    str(t.innen_konturen), _z(t.gravur), str(t.gravur_konturen),
                    "|".join(f"{_z(d)}:{n}" for d, n in t.bohrungen.items()),
                    "|".join(f"{_z(g)}:{_z(l)}" for g, l in t.innen_liste),
                    t.profil_id_vorschlag, _text("; ".join(t.hinweise)), t.einheit, t.koerperart,
                    "" if t.gueltig is None else "1" if t.gueltig else "0", _z(t.volumen), _z(t.oberflaeche),
                    str(t.n_flaechen), str(t.n_kanten), "|".join(_z(x) for x in t.huelle),
                    _text("; ".join(t.meldungen)), _z(t.innen_a), _z(t.innen_b),
                    "|".join(":".join([_z(z), _z(x), _z(y), _z(w), s]) for z, x, y, w, s in t.wand_messungen),
                    ";".join(f"{k}={v}" for k, v in t.sicherheit.items()),
                    json.dumps(t.konturen_liste, ensure_ascii=False, separators=(",", ":")), netz, ""])
    return out


def step_dateien(pfade):
    out = []
    for p in map(Path, pfade):
        if p.is_dir():
            out += sorted(x for x in p.iterdir() if x.suffix.lower() in (".step", ".stp"))
        else:
            out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="STEP-Dateien messen (für den STEP-Import der Angebotskalkulation)")
    ap.add_argument("--ausgabe", required=True, help="Textdatei für die Messwerte")
    ap.add_argument("--liste", help="Textdatei mit einem STEP-Pfad je Zeile")
    ap.add_argument("--netze", help="Ordner für die Dreiecksnetze der 3D-Ansicht (JSON je Teil)")
    ap.add_argument("pfade", nargs="*", help="STEP-Dateien oder Ordner")
    a = ap.parse_args(argv)
    pfade = list(a.pfade)
    if a.liste:
        pfade += [z.strip() for z in Path(a.liste).read_text(encoding="utf-8-sig").splitlines() if z.strip()]
    if not pfade:
        ap.error("keine STEP-Dateien angegeben")
    dateien = step_dateien(pfade)
    if a.netze:
        Path(a.netze).mkdir(parents=True, exist_ok=True)
    ergebnis = [None] * len(dateien)
    prozesse = min(PROZESSE_MAX, (os.cpu_count() or 1) - 1, len(dateien) // 3)
    if prozesse >= 2:       # viele Dateien: auf mehrere Prozesse verteilen, Reihenfolge der Ausgabe bleibt
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(prozesse) as pool:
            auftraege = {pool.submit(zeilen, d, a.netze, i): i for i, d in enumerate(dateien, start=1)}
            for n, fertig in enumerate(as_completed(auftraege), start=1):
                i = auftraege[fertig]
                ergebnis[i - 1] = fertig.result()
                print(f"[{n}/{len(dateien)}] {dateien[i - 1].name}", flush=True)
    else:
        for i, datei in enumerate(dateien, start=1):
            print(f"[{i}/{len(dateien)}] {datei.name}", flush=True)
            ergebnis[i - 1] = zeilen(datei, a.netze, i)
    fehler = False
    with open(a.ausgabe, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(SPALTEN) + "\n")
        for zs in ergebnis:
            for z in zs:
                fehler = fehler or bool(z[-1])
                f.write("\t".join(z) + "\n")
    return 1 if fehler else 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()     # STEP-Import.exe: Unterprozesse der Messung
    sys.exit(main())
