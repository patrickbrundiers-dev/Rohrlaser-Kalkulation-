"""Gemeinsamer Testlauf (Plan „Intelligenteres Programm“ C4): alle Testskripte parallel in eigenen Prozessen, mit
Laufzeit je Test und Zusammenfassung. Ersetzt im Workflow die lange Einzelliste.

Die Liste TESTS legt Reihenfolge und Umgebung fest (reproduzierbar: gestartet wird immer in dieser Reihenfolge,
ausgegeben wird in dieser Reihenfolge, egal welcher Test zuerst fertig ist). Jede Datei tests/test_*.py muss in
TESTS, LANGSAM oder EIGEN stehen – eine neue Testdatei ohne Eintrag macht den Lauf rot, damit sie nicht vergessen wird.

Aufruf: python tests/alle.py [-j N] [--langsam] [--nur MUSTER …] [--markdown DATEI] [--coverage]
  -j N        so viele Tests gleichzeitig (Vorgabe: Anzahl Prozessorkerne)
  --langsam   auch die langsamen Tests (LANGSAM; im Workflow nur beim Sammel-Release von Hand)
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
    ("test_step_drop.py", QT),
    ("test_step_regression.py", {}),
    ("test_step_wie_modell.py", {}),
    ("test_step_einlesen.py", {}),
    ("test_step_profile.py", QT),
    ("test_step_konturen.py", {}),
    ("test_step_anbau.py", {}),
    ("test_anbau_pruefen.py", {}),
    ("test_step_rahmengestell.py", QT),
    ("test_step_ergebnis.py", QT),
    ("test_3d_step.py", QT),
    ("test_step_fase.py", {}),
    ("test_step_export.py", QT),
    ("test_baugruppe_step.py", QT),
    ("test_step_mutter.py", QT),
    ("test_anbau_gravur.py", QT),
    ("test_naht_spalt.py", QT),
    ("test_zeichnung_baugruppe.py", QT),
    ("test_step_kantteile.py", {}),
    ("test_offenes_rohr.py", QT),
    ("test_rohr_ausschnitt.py", {}),
    ("test_winkel_virtuell.py", QT),
    ("test_virtuell_nutzen.py", QT),
    ("test_nasen_geometrie.py", QT),
    ("test_step_importfehler.py", QT),
    ("test_step_pruefung.py", QT),
    ("test_step_editor_wie_step.py", QT),
    ("test_step_rohranschluss.py", QT),
    ("test_rohr_aufgeschnitten.py", QT),
    ("test_gehrung_2d.py", QT),
    ("test_gehrung_2d_umstellen.py", QT),
    ("test_step_robust.py", QT),
    ("test_step_laserteile.py", QT),
    ("test_step_messung_robust.py", QT),
    ("test_step_gravur.py", QT),
    ("test_step_struktur.py", {}),
    ("test_step_leistung.py", {}),
    ("test_ansicht_gl.py", {}),
    ("test_schnittkoerper.py", {}),
    ("test_optimierung.py", {}),
    ("test_parallel.py", {}),
    ("test_lieferlaengen.py", {}),
    ("test_teil_laenger_stange.py", {}),
    ("test_lieferlaengen_mischen.py", {}),
] + [(name, QT) for name in (
    "test_programm.py", "test_csv_export.py", "test_konturklassen.py", "test_zusatzarbeiten.py",
    "test_zusatz_verwaltung.py", "test_zukauf.py", "test_zukauf_verwaltung.py", "test_zukauf_angebot.py",
    "test_zukauf_preise.py", "test_aufschlag_angebot.py", "test_kunden_csv.py", "test_kunden_csv_robust.py", "test_zukauf_schnell.py", "test_zukauf_ek.py", "test_zukauf_blech.py",
    "test_vollmaterial.py",
    "test_blech_position.py", "test_step_satz.py", "test_step_ablage.py", "test_importprofil.py", "test_artikel_step.py", "test_bohrbild.py",
    "test_rp_profile.py", "test_step_rp.py", "test_profilwechsel.py", "test_doppelklick.py", "test_mausrad.py",
    "test_step_bleche.py", "test_werkstoffe.py", "test_werkstoffe_rohrlaser.py", "test_meterpreis.py", "test_teuerung.py", "test_kalkulation_verbessern.py", "test_stundensatz.py", "test_gewinn_gestaffelt.py", "test_preis_simulator.py", "test_absage.py", "test_auftragsbestaetigung.py", "test_etiketten.py", "test_auslastung.py", "test_reklamation.py", "test_material_fenster.py", "test_stangen_vorgabe.py", "test_abmessung_fenster.py", "test_stangen_ansicht.py",
    "test_maschinen.py", "test_schneiddaten_standard.py", "test_lager.py", "test_nachkalk_auswertung.py", "test_arbeitsgaenge.py", "test_abrechnungsregeln.py", "test_varianten.py", "test_fertigung.py",
    "test_offene_profile.py", "test_wand_einstiche.py", "test_ansicht.py", "test_unterzeilen.py", "test_satz_optik.py", "test_kopf_kompakt.py", "test_spaltenbreite.py",
    "test_angebot_leistung.py", "test_zeiten.py",
    "test_staffelpreise.py", "test_gewinn_basis.py", "test_preisregeln.py", "test_quellcode_schutz.py", "test_update.py", "test_update_sperre.py", "test_update_haertung.py", "test_update_signatur.py", "test_echtheit.py", "test_update_testplan.py", "test_update_download.py", "test_daten_finden.py", "test_release_pruefen.py", "test_fracht.py", "test_fracht_angebot.py", "test_fracht_auto.py",
    "test_fracht_richtwerte.py", "test_pack_rechner.py", "test_sicherung.py", "test_preisbasis.py", "test_rundung.py",
    "test_angebot_vorgaben.py", "test_musterteile.py", "test_abruf_angebot.py", "test_angebot_einstellungen.py", "test_kundenmaterial.py", "test_schneidweg.py",
    "test_blech_editor.py", "test_blech_dxf.py", "test_blech_kfaktor.py", "test_blech_kantbarkeit.py", "test_blech_tafel.py",
    "test_dfm.py", "test_teile_editor.py", "test_editor_ausbau.py", "test_editor_messen.py", "test_editor_abwicklung.py", "test_3d_ansicht.py", "test_drehpunkt.py", "test_blech_zeichnen.py",
    "test_konturvorlagen.py", "test_dxf_import.py", "test_dxf_ansichten.py", "test_dxf_rohr.py", "test_dxf_varianten.py", "test_dxf_robust.py", "test_schnittflaeche.py", "test_innenkante.py", "test_gegenrohr.py", "test_editor_griffe.py", "test_biegerohr.py", "test_knickrahmen.py",
    "test_knickverbindung.py", "test_knickrahmen_koerper.py", "test_steckverbindung.py", "test_naht.py",
    "test_naht_mehrfach.py", "test_stangenwechsel_sn.py", "test_3d.py", "test_3d_greifmass.py", "test_3d_editor.py", "test_programmierung.py",
    "test_schweissen.py", "test_baugruppe.py", "test_baugruppe_abnahme.py", "test_vorkalk.py", "test_bg_mengen.py", "test_bg_werkstoff.py", "test_bg_serie.py", "test_bg_erreichbar.py", "test_bg_naht_rechnung.py", "test_baugruppe_baum.py", "test_baugruppe_ansicht.py", "test_satz3d.py", "test_satz_knick.py", "test_baugruppe_vorschlaege.py", "test_steck_montage.py", "test_montagefolge.py", "test_rahmen_assistent.py", "test_gravur.py", "test_tastatur.py", "test_enter_dialoge.py", "test_reihenfolge.py", "test_position_kopie.py", "test_materialanfrage.py", "test_plausibel.py",
    "test_protokoll.py", "test_festschreiben.py", "test_hintergrund.py", "test_vorgang.py", "test_zeitraum_liste.py", "test_teilen.py",
    "test_teilen_fenster.py", "test_teilen_zusammenarbeit.py", "test_teilen_zusammenarbeit_fenster.py", "test_teilen_ordner.py", "test_nummern.py", "test_angebotsordner.py", "test_lizenz.py", "test_lizenz_werkzeug.py", "test_lesemodus.py", "test_passwort.py", "test_themes.py", "test_dunkelmodus.py", "test_hell_dunkel.py",
    "test_arbeitsablaeufe.py", "test_auto_optimieren.py", "test_loeschschutz.py", "test_kundenvorgaben.py", "test_step_neu.py", "test_neue_fassung.py", "test_auftrag.py", "test_palettenschein.py", "test_tabellen_eingabe.py", "test_befehlspalette.py", "test_cockpit.py", "test_wasserfall.py", "test_spaltenbreite_merken.py", "test_symbole.py", "test_wiederholteile.py", "test_zwischenspeicher.py", "test_angebot_check.py", "test_design_pruefung.py", "test_pdf_layout.py", "test_kalkulation_pdf.py", "test_anfragen.py", "test_formular.py", "test_mail.py", "test_pdf_art.py", "test_mehrere_mails.py", "test_pdf_zeichnung.py", "test_pdf_vektor.py", "test_nachfassen.py", "test_bedienung.py", "test_abmessung_neu.py", "test_eingabefelder.py", "test_angebotsablauf.py", "test_anleitung.py",
    "test_performance_update.py", "test_datenbank_indizes.py", "test_pruefung_optik.py", "test_archiv.py", "test_teilen_monate.py", "test_austausch.py", "test_einstellungen_ordnung.py", "test_admin_schutz.py",
)]
# langsam: nur mit --langsam (im Workflow nicht bei jedem Pull Request)
LANGSAM = [("test_gehrung.py", QT), ("test_belastung.py", QT)]
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
