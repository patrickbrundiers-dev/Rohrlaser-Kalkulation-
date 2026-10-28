"""Untergrenze der Testabdeckung (Verbesserungsplan P0-4): der Rechenkern darf nicht unbemerkt ungetestet werden.

Liest den coverage-Bericht (python -m coverage json) des Laufs tests/alle.py --coverage und prüft je Kernmodul und
gesamt die Untergrenze aus MINDEST. Die Grenzen liegen 2 Prozentpunkte unter der Messung vom 28.10.2026 (0.9.165),
damit kleine Umbauten nicht gleich rot werden; steigt die Abdeckung, die Grenze per Pull Request nachziehen.
Nicht gemessen werden Programmteile in eigenen Prozessen (STEP-Import.exe, Hilfsprozesse beim Optimieren).

Aufruf: python tests/abdeckung_pruefen.py abdeckung.json [--markdown DATEI]
"""
import argparse
import json
import sys

GESAMT = 87
MINDEST = {         # Modul in programm/rohrlaser -> Mindestabdeckung in %
    "abmessung": 97, "arbeitsgaenge": 94, "datenbank": 94, "export": 91, "fertigung": 94, "fracht": 90,
    "fracht_angebot": 92, "kennwerte": 95, "lager": 91, "lizenz": 90, "nachkalkulation": 98, "optimierung": 92,
    "paletten": 83, "pdf": 89, "rechnen": 94, "schneidweg": 92, "staffeln": 87, "step": 89, "teilen": 89,
    "varianten": 94, "zukauf": 89,
}


def pruefen(bericht):
    """[(Name, gemessen %, Grenze %, ok)] für alle Kernmodule und gesamt."""
    dateien = bericht["files"]
    zeilen = []
    for name, grenze in MINDEST.items():
        f = dateien.get(f"programm/rohrlaser/{name}.py")
        wert = f["summary"]["percent_covered"] if f else 0.0     # fehlt das Modul im Bericht: nie gelaufen
        zeilen.append((name, wert, grenze, wert >= grenze))
    wert = bericht["totals"]["percent_covered"]
    zeilen.append(("gesamt", wert, GESAMT, wert >= GESAMT))
    return zeilen


def main():
    a = argparse.ArgumentParser()
    a.add_argument("bericht")
    a.add_argument("--markdown")
    args = a.parse_args()
    with open(args.bericht, encoding="utf-8") as f:
        zeilen = pruefen(json.load(f))
    for name, wert, grenze, ok in zeilen:
        print(f"{'OK    ' if ok else 'ZU WENIG'} {name:16} {wert:5.1f} % (mindestens {grenze} %)")
    if args.markdown:
        with open(args.markdown, "a", encoding="utf-8") as f:
            f.write("\n### Testabdeckung\n\n| Modul | Abdeckung | Mindestens |\n|---|---:|---:|\n")
            f.writelines(f"| {'' if ok else '❌ '}{n} | {w:.1f} % | {g} % |\n" for n, w, g, ok in zeilen)
    rot = [n for n, _, _, ok in zeilen if not ok]
    if rot:
        print("Abdeckung unter der Untergrenze: " + ", ".join(rot))
        return 1
    print("OK: Testabdeckung")
    return 0


if __name__ == "__main__":
    sys.exit(main())
