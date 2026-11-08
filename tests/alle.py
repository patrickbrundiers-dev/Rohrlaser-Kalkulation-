"""Gemeinsamer Testlauf (Plan „Intelligenteres Programm“ C4): alle Testskripte parallel in eigenen Prozessen, mit
Laufzeit je Test und Zusammenfassung. Ersetzt im Workflow die lange Einzelliste.

Die Liste TESTS legt Reihenfolge und Umgebung fest (reproduzierbar: gestartet wird immer in dieser Reihenfolge,
ausgegeben wird in dieser Reihenfolge, egal welcher Test zuerst fertig ist). Jede Datei tests/test_*.py muss in
TESTS, LANGSAM oder EIGEN stehen – eine neue Testdatei ohne Eintrag macht den Lauf rot, damit sie nicht vergessen wird.

Schneller Lauf (Optimierungsplan 04.11.2026, E2): mit --teil K/N läuft nur ein Teil der Tests; die Teile werden nach
den Laufzeiten aus tests/laufzeiten.json gleich lang verteilt (der Workflow startet drei Teile auf drei Rechnern
gleichzeitig). Innerhalb eines Laufs starten die langsamsten Tests zuerst. Ein roter Test wird am Ende einmal allein
wiederholt: grün beim zweiten Mal heißt „instabil“ (steht in der Zusammenfassung, der Lauf bleibt grün), rot bleibt rot.

Aufruf: python tests/alle.py [-j N] [--teil K/N] [--langsam] [--nur MUSTER …] [--markdown DATEI] [--coverage]
  -j N        so viele Tests gleichzeitig (Vorgabe: Anzahl Prozessorkerne)
  --teil K/N  nur Teil K von N (nach Laufzeit gleich verteilt)
  --laufzeiten DATEI  gemessene Laufzeiten als JSON schreiben (für tests/laufzeiten.json)
  --langsam   auch die langsamen Tests (LANGSAM; im Workflow nur beim Sammel-Release von Hand)
  --nur       nur Tests, deren Name eines der Muster enthält
  --markdown  Zusammenfassung als Markdown-Tabelle anhängen (z. B. "$GITHUB_STEP_SUMMARY")
  --coverage  jeden Test mit coverage (nur Entwicklung, requirements-dev.txt) laufen lassen; danach
              python -m coverage combine && python -m coverage report
"""
import argparse
import concurrent.futures
import json
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
    ("test_step_sammlung.py", {}),
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
    ("test_step_durchbruch.py", QT),
    ("test_rohr_aufgeschnitten.py", QT),
    ("test_flachstahl_enden.py", QT),
    ("test_fasen_ecken.py", QT),
    ("test_gewinde_modelliert.py", {}),
    ("test_a4_pruefsammlung.py", {}),
    ("test_editoren_gleich.py", {}),
    ("test_normteile_preis.py", {}),
    ("test_normteile_ohne_preis.py", {}),
    ("test_aufteilen.py", {}),
    ("test_aufteilen_bolzen.py", {}),
    ("test_pruefdialog_m1_m3.py", {}),
    ("test_paket9.py", {}),
    ("test_paket10.py", {}),
    ("test_paket11.py", {}),
    ("test_zeitlimit_vereinfacht.py", {}),
    ("test_langsam_hintergrund.py", {}),
    ("test_pruefsammlung_waechst.py", {}),
    ("test_rueckfragen_0711.py", {}),
    ("test_lage_tempo.py", {}),
    ("test_step_gedreht.py", {}),
    ("test_step_senden.py", {}),
    ("test_step_kritisch.py", QT),
    ("test_step_jede_kontur.py", QT),
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
    ("test_fehler_0111.py", QT),
    ("test_fehler_0511.py", QT),
    ("test_bedienung_0611.py", QT),
    ("test_langsam_0411.py", QT),
    ("test_parallel.py", {}),
    ("test_lieferlaengen.py", {}),
    ("test_teil_laenger_stange.py", {}),
    ("test_lieferlaengen_mischen.py", {}),
] + [(name, QT) for name in (
    "test_programm.py", "test_csv_export.py", "test_konturklassen.py", "test_zusatzarbeiten.py",
    "test_zusatz_verwaltung.py", "test_zukauf.py", "test_zukauf_verwaltung.py", "test_zukauf_angebot.py",
    "test_zukauf_preise.py", "test_aufschlag_angebot.py", "test_kunden_csv.py", "test_kunden_csv_robust.py", "test_zukauf_schnell.py", "test_zukauf_ek.py", "test_zukauf_blech.py",
    "test_vollmaterial.py", "test_drehfraes.py", "test_drehfraes_preis.py", "test_erkennung_vielfalt.py", "test_satz_kosten.py", "test_kantteile_vielfalt.py", "test_kantteil_bilder.py", "test_iges_import.py", "test_art_auswahl.py",
    "test_blech_position.py", "test_step_satz.py", "test_step_ablage.py", "test_importprofil.py", "test_artikel_step.py", "test_bohrbild.py",
    "test_bohrungsart.py",
    "test_rp_profile.py", "test_step_rp.py", "test_profilwechsel.py", "test_doppelklick.py", "test_mausrad.py",
    "test_step_bleche.py", "test_werkstoffe.py", "test_werkstoffe_rohrlaser.py", "test_meterpreis.py", "test_teuerung.py", "test_kalkulation_verbessern.py", "test_stundensatz.py", "test_gewinn_gestaffelt.py", "test_anfragenr_gewinn.py", "test_preis_simulator.py", "test_angebotsvergleich.py", "test_absage.py", "test_auftragsbestaetigung.py", "test_etiketten.py", "test_paket_module.py", "test_auslastung.py", "test_terminplan.py", "test_schnellpreis.py", "test_reklamation.py", "test_material_fenster.py", "test_stangen_vorgabe.py", "test_abmessung_fenster.py", "test_stangen_ansicht.py",
    "test_maschinen.py", "test_schneiddaten_standard.py", "test_lager.py", "test_nachkalk_auswertung.py", "test_laufzeit_teil.py", "test_arbeitsgaenge.py", "test_zusatz_erkennung.py", "test_satz_flaeche.py", "test_satz_zusatz.py", "test_einzelteile_vorschlaege.py", "test_rohrlaser_zusatz.py", "test_abrechnungsregeln.py", "test_varianten.py", "test_fertigung.py",
    "test_offene_profile.py", "test_wand_einstiche.py", "test_ansicht.py", "test_unterzeilen.py", "test_satz_optik.py", "test_gruppen_uebersicht.py", "test_naht_laenge.py", "test_satz_menge.py", "test_umwandeln.py", "test_kopf_kompakt.py", "test_layout_platz.py", "test_paket3.py", "test_paket4.py", "test_spaltenbreite.py",
    "test_angebot_leistung.py", "test_tempo.py", "test_zeiten.py",
    "test_staffelpreise.py", "test_gewinn_basis.py", "test_preisregeln.py", "test_quellcode_schutz.py", "test_update.py", "test_update_sperre.py", "test_update_haertung.py", "test_update_signatur.py", "test_echtheit.py", "test_update_testplan.py", "test_update_download.py", "test_daten_finden.py", "test_release_pruefen.py", "test_fracht.py", "test_fracht_angebot.py", "test_fracht_auto.py",
    "test_fracht_richtwerte.py", "test_pack_rechner.py", "test_sicherung.py", "test_preisbasis.py", "test_rundung.py",
    "test_angebot_vorgaben.py", "test_musterteile.py", "test_abruf_angebot.py", "test_vorschlaege_0211.py", "test_vorschlaege_0211b.py", "test_kalkulationsbasis.py", "test_angebot_einstellungen.py", "test_kundenmaterial.py", "test_schneidweg.py",
    "test_blech_editor.py", "test_blech_richtwerte.py", "test_blech_dxf.py", "test_blech_kfaktor.py", "test_blech_kantbarkeit.py", "test_blech_tafel.py",
    "test_dfm.py", "test_teile_editor.py", "test_editor_ursprung.py", "test_editor_ursprung_bg.py", "test_editor_ausbau.py", "test_editor_messen.py", "test_editor_abwicklung.py", "test_3d_ansicht.py", "test_drehpunkt.py", "test_blech_zeichnen.py",
    "test_konturvorlagen.py", "test_dxf_import.py", "test_dxf_ansichten.py", "test_dxf_rohr.py", "test_dxf_varianten.py", "test_dxf_robust.py", "test_schnittflaeche.py", "test_innenkante.py", "test_gegenrohr.py", "test_editor_griffe.py", "test_biegerohr.py", "test_knickrahmen.py",
    "test_knickverbindung.py", "test_knickrahmen_koerper.py", "test_steckverbindung.py", "test_naht.py",
    "test_naht_mehrfach.py", "test_stangenwechsel_sn.py", "test_3d.py", "test_3d_greifmass.py", "test_3d_editor.py", "test_programmierung.py",
    "test_schweissen.py", "test_baugruppe.py", "test_baugruppe_abnahme.py", "test_vorkalk.py", "test_bg_unterbaugruppe_naehte.py", "test_bg_mengen.py", "test_bg_werkstoff.py", "test_bg_serie.py", "test_bg_erreichbar.py", "test_bg_naht_rechnung.py", "test_baugruppe_baum.py", "test_baugruppe_ansicht.py", "test_satz3d.py", "test_satz_knick.py", "test_baugruppe_vorschlaege.py", "test_steck_montage.py", "test_montagefolge.py", "test_rahmen_assistent.py", "test_gravur.py", "test_tastatur.py", "test_enter_dialoge.py", "test_reihenfolge.py", "test_position_kopie.py", "test_materialanfrage.py", "test_angebot_mail.py", "test_plausibel.py",
    "test_protokoll.py", "test_festschreiben.py", "test_hintergrund.py", "test_vorgang.py", "test_zeitraum_liste.py", "test_teilen.py",
    "test_teilen_fenster.py", "test_teilen_zusammenarbeit.py", "test_teilen_zusammenarbeit_fenster.py", "test_teilen_ordner.py", "test_nummern.py", "test_angebotsordner.py", "test_lizenz.py", "test_lizenz_werkzeug.py", "test_lesemodus.py", "test_passwort.py", "test_themes.py", "test_dunkelmodus.py", "test_hell_dunkel.py",
    "test_arbeitsablaeufe.py", "test_auto_optimieren.py", "test_loeschschutz.py", "test_kundenvorgaben.py", "test_step_neu.py", "test_neue_fassung.py", "test_auftrag.py", "test_palettenschein.py", "test_tabellen_eingabe.py", "test_befehlspalette.py", "test_cockpit.py", "test_wasserfall.py", "test_spaltenbreite_merken.py", "test_symbole.py", "test_wiederholteile.py", "test_zwischenspeicher.py", "test_angebot_check.py", "test_design_pruefung.py", "test_pdf_layout.py", "test_kalkulation_pdf.py", "test_anfragen.py", "test_formular.py", "test_mail.py", "test_pdf_art.py", "test_zeichnung_hinweise.py", "test_mehrere_mails.py", "test_weiterleitung.py", "test_formular_tabelle.py", "test_pdf_zeichnung.py", "test_pdf_vektor.py", "test_nachfassen.py", "test_bedienung.py", "test_abmessung_neu.py", "test_u_profile_wand_rohrart.py", "test_eingabefelder.py", "test_angebotsablauf.py", "test_automationen.py", "test_angebot_automatik.py", "test_anleitung.py",
    "test_performance_update.py", "test_datenbank_indizes.py", "test_pruefung_optik.py", "test_archiv.py", "test_teilen_monate.py", "test_austausch.py", "test_ordner_pruefung.py", "test_kollegen_puls.py", "test_merker_namen.py", "test_ausgeschieden.py", "test_aenderungsverlauf.py", "test_sperre_meldung.py", "test_ordner_ausfall_umzug.py", "test_einstellungen_ordnung.py", "test_admin_schutz.py",
)]
# langsam: nur mit --langsam (im Workflow nicht bei jedem Pull Request)
LANGSAM = [("test_gehrung.py", QT), ("test_belastung.py", QT)]
# laufen mit eigenen Argumenten als eigener Schritt im Workflow (Testbericht) bzw. von Hand
EIGEN = {"test_step_referenz.py", "test_abnahme.py"}


def fehlende():
    """Testdateien, die weder in TESTS, LANGSAM noch EIGEN stehen."""
    bekannt = {n for n, _ in TESTS + LANGSAM} | EIGEN
    return sorted(p.name for p in HIER.glob("test_*.py") if p.name not in bekannt)


LAUFZEITEN = HIER / "laufzeiten.json"
UNBEKANNT_S = 30        # Laufzeit eines Tests, der noch nicht in laufzeiten.json steht


def laufzeiten():
    try:
        return json.loads(LAUFZEITEN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def teil(liste, k, n, dauer=None):
    """Teil k (1 … n) der Tests: die längsten zuerst jeweils dem bisher kürzesten Teil zugeteilt (gleich lange Teile).
    Ergebnis in der Reihenfolge von liste."""
    dauer = laufzeiten() if dauer is None else dauer
    summe, zu = [0.0] * n, {}
    for name, _ in sorted(liste, key=lambda e: -dauer.get(e[0], UNBEKANNT_S)):
        i = min(range(n), key=lambda j: summe[j])
        summe[i] += dauer.get(name, UNBEKANNT_S)
        zu[name] = i
    return [(name, u) for name, u in liste if zu[name] == k - 1]


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
    a.add_argument("--teil", default=None)
    a.add_argument("--laufzeiten", default=None)
    args = a.parse_args(argv)

    liste = TESTS + (LANGSAM if args.langsam else [])
    if args.nur:
        liste = [(n, u) for n, u in liste if any(m in n for m in args.nur)]
    ohne = fehlende() if not args.nur else []
    if args.teil:
        k, n = (int(x) for x in args.teil.split("/"))
        liste = teil(liste, k, n)
        ohne = ohne if k == 1 else []        # fehlende Einträge meldet nur Teil 1
        print(f"Teil {k} von {n}: {len(liste)} Tests", flush=True)

    dauer_alt = laufzeiten()
    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.j)) as pool:
        # langsamste zuerst starten (sonst wartet am Ende alles auf einen spät gestarteten langen Test)
        reihe = sorted(liste, key=lambda e: -dauer_alt.get(e[0], UNBEKANNT_S))
        laeufe = {n: pool.submit(ausfuehren, n, u, args.coverage) for n, u in reihe}
        ergebnisse = []
        for n, _ in liste:                   # Ausgabe in fester Reihenfolge
            name, code, dauer, ausgabe = laeufe[n].result()
            ergebnisse.append((name, code, dauer))
            print(f"{'OK    ' if code == 0 else 'FEHLER'}  {dauer:7.1f} s  {name}", flush=True)
            if code != 0:
                print("\n".join("        | " + z for z in ausgabe.rstrip().splitlines()[-60:]), flush=True)
    # rote Tests einmal allein wiederholen (ohne Last der anderen): grün = instabil, nicht rot
    instabil = []
    umgebung = dict(liste)
    for i, (name, code, dauer) in enumerate(ergebnisse):
        if code == 0:
            continue
        _, code2, dauer2, ausgabe2 = ausfuehren(name, umgebung[name], args.coverage)
        print(f"{'OK    ' if code2 == 0 else 'FEHLER'}  {dauer2:7.1f} s  {name} (Wiederholung allein)", flush=True)
        if code2 == 0:
            instabil.append(name)
            ergebnisse[i] = (name, 0, dauer)
        else:
            print("\n".join("        | " + z for z in ausgabe2.rstrip().splitlines()[-30:]), flush=True)
    gesamt = time.monotonic() - start
    if args.laufzeiten:
        with open(args.laufzeiten, "w", encoding="utf-8") as f:
            json.dump({n: round(d) for n, _, d in ergebnisse}, f, indent=0, sort_keys=True)

    rot = [n for n, c, _ in ergebnisse if c != 0]
    print()
    print(f"{len(ergebnisse)} Tests in {gesamt:.0f} s (Summe der Laufzeiten {sum(d for _, _, d in ergebnisse):.0f} s, "
          f"{args.j} gleichzeitig)")
    if instabil:
        print("Instabil (erst rot, allein wiederholt grün): " + ", ".join(instabil))
    for n, _, d in sorted(ergebnisse, key=lambda e: -e[2])[:5]:
        print(f"  langsamste: {d:6.1f} s  {n}")
    if ohne:
        print("Testdateien ohne Eintrag in tests/alle.py (TESTS, LANGSAM oder EIGEN): " + ", ".join(ohne))
    print("Alles in Ordnung." if not rot and not ohne else f"{len(rot)} Test(s) rot: {', '.join(rot)}")

    if args.markdown:
        with open(args.markdown, "a", encoding="utf-8") as f:
            titel = f" (Teil {args.teil})" if args.teil else ""
            f.write(f"### Tests{titel}: {len(ergebnisse) - len(rot)} von {len(ergebnisse)} grün ({gesamt:.0f} s)\n\n"
                    "| Test | Ergebnis | Laufzeit |\n|---|---|---:|\n")
            for n, c, d in ergebnisse:
                f.write(f"| {n} | {'✅' if c == 0 else '❌'} | {d:.1f} s |\n")
            if instabil:
                f.write("\nInstabil (erst rot, allein wiederholt grün): " + ", ".join(instabil) + "\n")
            if ohne:
                f.write("\nOhne Eintrag in tests/alle.py: " + ", ".join(ohne) + "\n")
    return 1 if rot or ohne else 0


if __name__ == "__main__":
    sys.exit(main())
