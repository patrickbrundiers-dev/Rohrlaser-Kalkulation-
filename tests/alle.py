"""Gemeinsamer Testlauf (Plan „Intelligenteres Programm“ C4): alle Testskripte parallel in eigenen Prozessen, mit
Laufzeit je Test und Zusammenfassung. Ersetzt im Workflow die lange Einzelliste.

Die Liste TESTS legt Reihenfolge und Umgebung fest (reproduzierbar: gestartet wird immer in dieser Reihenfolge,
ausgegeben wird in dieser Reihenfolge, egal welcher Test zuerst fertig ist). Jede Datei tests/test_*.py muss in
TESTS, LANGSAM oder EIGEN stehen – eine neue Testdatei ohne Eintrag macht den Lauf rot, damit sie nicht vergessen wird.

Aufruf: python tests/alle.py [-j N] [--langsam] [--nur MUSTER …] [--markdown DATEI] [--coverage]
  -j N        so viele Tests gleichzeitig (Vorgabe: Anzahl Prozessorkerne)
  --langsam   auch die langsamen Tests (LANGSAM; im Workflow nur auf main bzw. von Hand)
  --nur       nur Tests, deren Name eines der Muster enthält
  --markdown  Zusammenfassung als Markdown-Tabelle anhängen (z. B. "$GITHUB_STEP_SUMMARY")
  --coverage  jeden Test mit coverage (nur Entwicklung, requirements-dev.txt) laufen lassen; danach
              python -m coverage combine && python -m coverage report
"""
import argparse
import concurrent.futures
import os
import subprocess
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
QT = {"QT_QPA_PLATFORM": "offscreen"}

# (Datei, Umgebung) – erst STEP-Messung und Optimierung, dann die Programm-Tests (Reihenfolge wie bisher im Workflow)
TESTS = [
    ("test_step_import.py", {}),
    ("test_step_regression.py", {}),
    ("test_step_einlesen.py", {}),
    ("test_step_profile.py", QT),
    ("test_step_konturen.py", {}),
    ("test_step_anbau.py", {}),
    ("test_anbau_pruefen.py", {}),
    ("test_step_rahmengestell.py", QT),
    ("test_step_ergebnis.py", QT),
    ("test_3d_step.py", QT),
    ("test_step_fase.py", {}),
    ("test_step_kantteile.py", {}),
    ("test_step_messung_robust.py", QT),
    ("test_step_struktur.py", {}),
    ("test_step_leistung.py", {}),
    ("test_ansicht_gl.py", {}),
    ("test_optimierung.py", {}),
    ("test_lieferlaengen.py", {}),
] + [(name, QT) for name in (
    "test_programm.py", "test_csv_export.py", "test_konturklassen.py", "test_zusatzarbeiten.py",
    "test_zusatz_verwaltung.py", "test_zukauf.py", "test_zukauf_verwaltung.py", "test_zukauf_angebot.py",
    "test_zukauf_preise.py", "test_kunden_csv.py", "test_zukauf_schnell.py", "test_zukauf_ek.py", "test_zukauf_blech.py",
    "test_blech_position.py", "test_step_satz.py", "test_step_ablage.py", "test_importprofil.py", "test_bohrbild.py",
    "test_rp_profile.py", "test_step_rp.py", "test_profilwechsel.py", "test_doppelklick.py", "test_mausrad.py",
    "test_step_bleche.py", "test_werkstoffe.py", "test_meterpreis.py", "test_material_fenster.py", "test_maschinen.py",
    "test_offene_profile.py", "test_wand_einstiche.py", "test_ansicht.py", "test_spaltenbreite.py", "test_zeiten.py",
    "test_staffelpreise.py", "test_gewinn_basis.py", "test_update.py", "test_fracht.py", "test_fracht_angebot.py", "test_fracht_auto.py",
    "test_fracht_richtwerte.py", "test_sicherung.py", "test_preisbasis.py", "test_rundung.py",
    "test_angebot_vorgaben.py", "test_angebot_einstellungen.py", "test_kundenmaterial.py", "test_schneidweg.py",
    "test_blech_editor.py", "test_blech_dxf.py", "test_blech_kfaktor.py", "test_blech_kantbarkeit.py", "test_blech_tafel.py",
    "test_dfm.py", "test_teile_editor.py", "test_naht.py",
    "test_stangenwechsel_sn.py", "test_3d.py", "test_3d_greifmass.py", "test_3d_editor.py", "test_programmierung.py",
    "test_schweissen.py", "test_baugruppe.py", "test_baugruppe_abnahme.py", "test_tastatur.py", "test_materialanfrage.py", "test_plausibel.py",
    "test_protokoll.py", "test_festschreiben.py", "test_hintergrund.py", "test_vorgang.py", "test_teilen.py",
    "test_teilen_fenster.py", "test_lizenz.py", "test_lesemodus.py", "test_passwort.py", "test_themes.py",
    "test_arbeitsablaeufe.py", "test_befehlspalette.py", "test_cockpit.py", "test_wasserfall.py", "test_spaltenbreite_merken.py", "test_symbole.py", "test_anleitung.py",
)]
# langsam: nur mit --langsam (im Workflow nicht bei jedem Pull Request)
LANGSAM = [("test_gehrung.py", QT)]
# laufen mit eigenen Argumenten als eigener Schritt im Workflow (Testbericht) bzw. von Hand
EIGEN = {"test_step_referenz.py", "test_abnahme.py"}


def fehlende():
    """Testdateien, die weder in TESTS, LANGSAM noch EIGEN stehen."""
    bekannt = {n for n, _ in TESTS + LANGSAM} | EIGEN
    return sorted(p.name for p in HIER.glob("test_*.py") if p.name not in bekannt)


def ausfuehren(name, umgebung, coverage):
    env = dict(os.environ, **umgebung)
    befehl = [sys.executable]
    if coverage:
        befehl += ["-m", "coverage", "run", "--parallel-mode", "--source", str(HIER.parent / "programm")]
    start = time.monotonic()
    p = subprocess.run(befehl + [str(HIER / name)], cwd=HIER.parent, env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, errors="replace")
    return name, p.returncode, time.monotonic() - start, p.stdout


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("-j", type=int, default=os.cpu_count() or 2)
    a.add_argument("--langsam", action="store_true")
    a.add_argument("--nur", nargs="+", default=None)
    a.add_argument("--markdown")
    a.add_argument("--coverage", action="store_true")
    args = a.parse_args(argv)

    liste = TESTS + (LANGSAM if args.langsam else [])
    if args.nur:
        liste = [(n, u) for n, u in liste if any(m in n for m in args.nur)]
    ohne = fehlende() if not args.nur else []

    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.j)) as pool:
        laeufe = [pool.submit(ausfuehren, n, u, args.coverage) for n, u in liste]
        ergebnisse = []
        for f in laeufe:                     # Ausgabe in fester Reihenfolge
            name, code, dauer, ausgabe = f.result()
            ergebnisse.append((name, code, dauer))
            print(f"{'OK    ' if code == 0 else 'FEHLER'}  {dauer:7.1f} s  {name}", flush=True)
            if code != 0:
                print("\n".join("        | " + z for z in ausgabe.rstrip().splitlines()[-60:]), flush=True)
    gesamt = time.monotonic() - start

    rot = [n for n, c, _ in ergebnisse if c != 0]
    print()
    print(f"{len(ergebnisse)} Tests in {gesamt:.0f} s (Summe der Laufzeiten {sum(d for _, _, d in ergebnisse):.0f} s, "
          f"{args.j} gleichzeitig)")
    for n, _, d in sorted(ergebnisse, key=lambda e: -e[2])[:5]:
        print(f"  langsamste: {d:6.1f} s  {n}")
    if ohne:
        print("Testdateien ohne Eintrag in tests/alle.py (TESTS, LANGSAM oder EIGEN): " + ", ".join(ohne))
    print("Alles in Ordnung." if not rot and not ohne else f"{len(rot)} Test(s) rot: {', '.join(rot)}")

    if args.markdown:
        with open(args.markdown, "a", encoding="utf-8") as f:
            f.write(f"### Tests: {len(ergebnisse) - len(rot)} von {len(ergebnisse)} grün ({gesamt:.0f} s)\n\n"
                    "| Test | Ergebnis | Laufzeit |\n|---|---|---:|\n")
            for n, c, d in ergebnisse:
                f.write(f"| {n} | {'✅' if c == 0 else '❌'} | {d:.1f} s |\n")
            if ohne:
                f.write("\nOhne Eintrag in tests/alle.py: " + ", ".join(ohne) + "\n")
    return 1 if rot or ohne else 0


if __name__ == "__main__":
    sys.exit(main())
