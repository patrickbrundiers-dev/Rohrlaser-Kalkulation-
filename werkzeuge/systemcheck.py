"""Systemcheck vor dem Sammel-Update (Patrick 19.11.2026, „Pre-Update Systemcheck“). Nur Entwicklung.

Misst mit dem echten Programmcode (Hauptfenster ohne Anzeige, PostgreSQL) die wichtigsten Arbeitsabläufe und je
Vorgang: Zeit (bester von n Läufen), CPU-Zeit des Prozesses, Arbeitsspeicher danach und Höchststand, Anzahl und Dauer
der Datenbank-Anweisungen, unnötige Mehrfachrechnungen („doppelt“, diagnose.py) und Fehler. Dazu ein Fingerabdruck der
Rechenergebnisse (gleiche Eingaben -> gleicher Fingerabdruck, Vergleich vorher/nachher) und ein Langzeitlauf
(Angebot n-mal schließen/öffnen und ändern; der Speicher darf nicht stetig wachsen).

Abläufe: Programmstart (Import der Module), Datendatei öffnen, Hauptfenster (Startseite/Dashboard), STEP-Import,
Angebot öffnen kalt/warm, Wechsel der Reiter, Zelle ändern mit Prüfung, Optimieren, Kalkulation (Materialpreise,
Maschinenzeiten, Gesamt), Speichern, Angebotsliste und Suche, Anfragen, 3D-Ansicht öffnen, Teil wechseln, Drehen und
Zoomen (je Bild), Messen (Körper/Flächen, Volumen), Rohr-Editor (Konturbearbeitung) öffnen, Angebots- und
Werkstatt-PDF, Langzeitlauf.

Aufruf (nicht als root; braucht die PostgreSQL-Programme):
  python werkzeuge/mit_pg.py -- python werkzeuge/systemcheck.py STEP-ORDNER AUSGABE [--langzeit 15] [--profil]
STEP-ORDNER: Ordner mit STEP-Dateien (Kundendaten nie ins Repository). Ergebnis: AUSGABE/ergebnis.json und
AUSGABE/fingerabdruck*.txt; Vergleich zweier Läufe: python werkzeuge/systemcheck.py --vergleich ALT.json NEU.json
"""
import argparse
import collections
import gc
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

HIER = Path(__file__).resolve().parent
R = HIER.parent


def _status(feld):
    try:
        for z in open("/proc/self/status", encoding="ascii"):
            if z.startswith(feld + ":"):
                return int(z.split()[1]) / 1024          # MB
    except OSError:
        pass
    return None


def vergleich(alt, neu):
    a, b = json.loads(Path(alt).read_text()), json.loads(Path(neu).read_text())
    print(f"{'Vorgang':44s} {'vorher s':>9s} {'nachher s':>9s} {'Faktor':>7s}  SQL vorher/nachher  doppelt")
    for name, w in b.items():
        if not isinstance(w, dict) or "s" not in w:
            continue
        v = a.get(name)
        if not isinstance(v, dict):
            print(f"{name:44s} {'–':>9s} {w['s']:9.3f}")
            continue
        f = v["s"] / w["s"] if w["s"] else float("inf")
        print(f"{name:44s} {v['s']:9.3f} {w['s']:9.3f} {f:6.1f}x  {v['sql']:6d}/{w['sql']:<6d}  "
              f"{v.get('doppelt', 0)}/{w.get('doppelt', 0)}")
    for k in ("fingerabdruck", "fingerabdruck_ende"):
        print(k, "gleich" if a.get(k) == b.get(k) else f"VERSCHIEDEN {a.get(k)} / {b.get(k)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="?")
    ap.add_argument("aus", nargs="?")
    ap.add_argument("--langzeit", type=int, default=15)
    ap.add_argument("--profil", action="store_true")
    ap.add_argument("--vergleich", nargs=2)
    a = ap.parse_args()
    if a.vergleich:
        return vergleich(*a.vergleich)
    aus = Path(a.aus)
    aus.mkdir(parents=True, exist_ok=True)

    # Programmstart: Import aller Module in einem frischen Prozess; der erste Lauf übersetzt die .pyc (das
    # ausgelieferte Programm ist übersetzt), gezählt wird der zweite
    def _start():
        t = time.perf_counter()
        subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                        "from PySide6.QtWidgets import QApplication; QApplication([]); import rohrlaser.fenster",
                        str(R / "programm")], check=True, env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        return time.perf_counter() - t
    _start()
    start_import = _start()

    sys.path[:0] = [str(R / "programm")]
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QDialog, QTabWidget
    app = QApplication.instance() or QApplication([])
    from rohrlaser import db_verbindung, diagnose

    sql = collections.Counter()
    zahl = [0, 0.0]
    orig = db_verbindung.KompatVerbindung._gezaehlt

    def _norm(s):
        s = re.sub(r"\s+", " ", s.strip())
        s = re.sub(r"'[^']*'", "'?'", s)
        return re.sub(r"\b\d+\b", "N", s)[:110]

    def gezaehlt(self, s, tun):
        t0 = time.perf_counter()
        try:
            return orig(self, s, tun)
        finally:
            zahl[0] += 1
            zahl[1] += time.perf_counter() - t0
            sql[_norm(s)] += 1
    db_verbindung.KompatVerbindung._gezaehlt = gezaehlt

    from rohrlaser.angebot_fenster import AngebotSeite
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.fenster import Hauptfenster
    AngebotSeite.CHECK_SOFORT = False
    erg = {"Programmstart (Module laden, eigener Prozess)": dict(s=round(start_import, 3), sql=0, cpu_s=None)}
    print(f"{'Programmstart (Module laden, eigener Prozess)':46s} {start_import:7.3f} s", flush=True)

    def doppelt():
        return sum(e["doppelt"] for e in diagnose.stand()["rechnungen"].values())

    def vorgang(name, f, n=1):
        import cProfile
        zeiten, fehler = [], None
        sql.clear()
        zahl[0], zahl[1] = 0, 0.0
        d0, c0 = doppelt(), time.process_time()
        pr = cProfile.Profile() if a.profil else None
        wert = None
        for _ in range(n):
            app.processEvents()
            t0 = time.perf_counter()
            if pr:
                pr.enable()
            try:
                wert = f()
            except Exception as e:      # noqa: BLE001 – Fehler gehört ins Ergebnis
                fehler = repr(e)
                traceback.print_exc()
            if pr:
                pr.disable()
            zeiten.append(time.perf_counter() - t0)
        if pr:
            pr.dump_stats(str(aus / (re.sub(r"\W+", "_", name) + ".prof")))
        erg[name] = dict(s=round(min(zeiten), 3), s_max=round(max(zeiten), 3), cpu_s=round((time.process_time() - c0) / n, 3),
                         ram_mb=round(_status("VmRSS") or 0), spitze_mb=round(_status("VmHWM") or 0),
                         sql=zahl[0] // n, sql_s=round(zahl[1] / n, 3), doppelt=doppelt() - d0, fehler=fehler,
                         top=sql.most_common(6))
        print(f"{name:46s} {min(zeiten):7.3f} s  CPU {erg[name]['cpu_s']:6.2f} s  RAM {erg[name]['ram_mb']:5d} MB  "
              f"SQL {zahl[0] // n:5d} ({zahl[1] / n:.3f} s)  doppelt {erg[name]['doppelt']}"
              + (f"  FEHLER {fehler}" if fehler else ""), flush=True)
        return wert

    def fingerabdruck(s):
        m = s.pos_modell
        teile = [repr(getattr(m, n, None)) for n in ("werte", "status", "meterpreise")]
        try:
            teile.append(repr(s._rechnung()))
        except Exception as e:          # noqa: BLE001
            teile.append("FEHLER " + repr(e))
        text = re.sub(r"'uid': '[^']*'", "'uid': ''", "\n".join(teile))
        text = re.sub(r"0x[0-9a-f]+", "0x", text)
        return hashlib.sha256(text.encode()).hexdigest()[:16], text

    import tempfile
    datei = Path(tempfile.mkdtemp()) / "systemcheck.db"
    db = vorgang("Datendatei öffnen", lambda: Datenbank(datei))
    f = vorgang("Hauptfenster mit Startseite aufbauen", lambda: Hauptfenster(db, R / "programm", stumm=True))
    f.automatik_testen = True
    aid = db.angebot_neu(dict(kunde="Systemcheck", kundennr="4711"))
    s = f.angebot_oeffnen(aid)
    dateien = sorted(str(p) for p in Path(a.steps).iterdir() if p.suffix.lower() in (".stp", ".step"))
    vorgang(f"STEP-Import {len(dateien)} Dateien", lambda: s.step_importieren(dateien, "S235-10219", 1, als_satz=False))
    app.processEvents()
    f.angebot_schliessen(aid)
    db.con.commit()
    s = vorgang("Angebot öffnen (kalt)", lambda: f.angebot_oeffnen(aid))
    app.processEvents()
    fp, text = fingerabdruck(s)
    (aus / "fingerabdruck.txt").write_text(text, encoding="utf-8")
    erg["fingerabdruck"] = fp
    print("FINGERABDRUCK", fp, len(s.positionen), "Positionen", flush=True)
    vorgang("Angebot neu laden (warm)", s.neu_laden, 3)

    def wechsel():
        f.reiter.setCurrentWidget(f.angebote)
        app.processEvents()
        f.reiter.setCurrentWidget(s)
        app.processEvents()
    vorgang("Wechsel Angebotsliste <-> Angebot", wechsel, 3)
    spalte = next(i for i, (_, fd) in enumerate(s.pos_modell.spalten)
                  if fd is not None and getattr(fd, "name", None) == "stueck")

    def zelle(d=1):
        alt = s.pos_modell.data(s.pos_modell.index(0, spalte))
        s.pos_modell.setData(s.pos_modell.index(0, spalte), str(int(float(str(alt).replace(",", ".") or 1)) + d))
        app.processEvents()
        uhr = s.__dict__.get("_check_uhr")
        if uhr is not None:
            uhr.stop()
        s._check_jetzt()
    vorgang("Zelle ändern (Stückzahl) mit Prüfung", zelle, 2)
    zelle(-2)
    vorgang("Optimieren (Stangen, Verschnitt)", s.optimieren, 1)
    from rohrlaser import rechnen

    def kalkulation():
        kopf, pos = db.angebot(aid), db.positionen(aid)
        e = rechnen.einstellungen_angebot(kopf, db.einstellungen())
        return rechnen.kalkulation(kopf, pos, kopf["ergebnis"], db.kontext(), db.tabellen(), e)
    vorgang("Gesamtkalkulation (Material, Maschinenzeit, Kosten)", kalkulation, 3)

    def unter_reiter():
        for w in s.findChildren(QTabWidget):
            if w.count() > 2:
                for i in range(w.count()):
                    w.setCurrentIndex(i)
                    app.processEvents()
                w.setCurrentIndex(0)
                break
    vorgang("Unterreiter im Angebot durchklicken", unter_reiter)
    vorgang("Speichern (Commit)", lambda: db.con.commit(), 3)
    vorgang("Angebotsliste neu laden", f.angebote.neu_laden, 3)
    suche = getattr(f.angebote, "suche", None)
    if suche is not None and hasattr(suche, "setText"):
        vorgang("Angebotsliste suchen", lambda: (suche.setText("Systemcheck"), app.processEvents(), suche.setText(""),
                                                 app.processEvents()), 3)
    anfragen = getattr(f, "anfragen", None)
    if anfragen is not None:
        vorgang("Reiter Anfragen öffnen", lambda: (f.reiter.setCurrentWidget(anfragen), app.processEvents(),
                                                   f.reiter.setCurrentWidget(s), app.processEvents()), 2)
    # 3D: Ansicht öffnen, Teil wechseln, Drehen/Zoomen je Bild, Messen
    from rohrlaser.ansicht3d import Ansicht3D
    d3 = vorgang("3D-Ansicht öffnen", lambda: s.ansicht_3d(0))
    ansicht = None
    if d3 is not None:
        ansichten = d3.findChildren(Ansicht3D)
        ansicht = max(ansichten, key=lambda w: w.width() * w.height()) if ansichten else None
    if ansicht is not None:
        ansicht.resize(1200, 800)
        liste = getattr(d3, "liste", None)
        n_pos = len(s.positionen)

        def teil_wechseln():
            for r in range(min(n_pos, 10)):
                if liste is not None and hasattr(liste, "selectRow"):
                    liste.selectRow(r)
                app.processEvents()
                ansicht.grab()
        vorgang("3D: zehn Teile nacheinander zeigen", teil_wechseln)
        # größtes Teil für Drehen/Zoomen/Messen
        netze = db.netze(aid)
        groesstes = max(netze.values(), key=len) if netze else None
        if groesstes is not None:
            ansicht.setzen(groesstes)
            ansicht.grab()
            dreiecke = len(getattr(getattr(ansicht, "modell", None), "dreiecke", []) or [])
            erg["3D größtes Teil Dreiecke"] = dreiecke

            def drehen():
                for _ in range(36):
                    ansicht.drehen_um("y", 10)
                    ansicht.grab()
            w = vorgang("3D: 360° drehen (36 Bilder)", drehen)
            erg["3D: 360° drehen (36 Bilder)"]["ms_je_bild"] = round(1000 * erg["3D: 360° drehen (36 Bilder)"]["s"] / 36, 1)

            def zoomen():
                for i in range(20):
                    ansicht.zoomen(1.1 if i < 10 else 1 / 1.1)
                    ansicht.grab()
            vorgang("3D: zoomen (20 Bilder)", zoomen)
            erg["3D: zoomen (20 Bilder)"]["ms_je_bild"] = round(1000 * erg["3D: zoomen (20 Bilder)"]["s"] / 20, 1)
            del w
            from rohrlaser import auswahl3d

            def messen():
                el = auswahl3d.Elemente(ansicht.modell)
                el.flaechen()
                return [el.masse(k) for k in list(el.koerper)[:3]]
            vorgang("Messen: Körper und Flächen erkennen, Volumen", messen)
    if d3 is not None:
        d3.close()
        d3.deleteLater()
    # Rohr-Editor (Konturbearbeitung) öffnen und abbrechen
    from rohrlaser.angebot import kein_laserteil
    r = next((i for i, p in enumerate(s.positionen) if not kein_laserteil(p) and p.get("profil_id") in s.k.profile), None)
    if r is not None:
        vorgang("Rohr-Editor (Konturbearbeitung) öffnen", lambda: s.schneidweg_berechnen(
            zeile=r, dialog=lambda d: (app.processEvents(), QDialog.Rejected)[1]))
    vorgang("Angebots-PDF", lambda: s.angebot_pdf(oeffnen=False))
    vorgang("Werkstatt-PDF", s.werkstatt_pdf)
    fp2, text2 = fingerabdruck(s)
    (aus / "fingerabdruck_ende.txt").write_text(text2, encoding="utf-8")
    erg["fingerabdruck_ende"] = fp2
    print("FINGERABDRUCK ENDE", fp2, flush=True)
    # Langzeit: schließen, öffnen, ändern; Speicher je Runde
    ram = []
    gc.collect()
    t0 = time.perf_counter()
    from PySide6.QtCore import QCoreApplication, QEvent

    def loeschen_abarbeiten():          # wie die Ereignisschleife des Programms: deleteLater wirklich ausführen
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    for i in range(a.langzeit):
        f.angebot_schliessen(aid)
        loeschen_abarbeiten()
        s = f.angebot_oeffnen(aid)
        app.processEvents()
        zelle(1 if i % 2 == 0 else -1)
        gc.collect()
        ram.append(round(_status("VmRSS") or 0))
    erg["Langzeit"] = dict(runden=a.langzeit, s_je_runde=round((time.perf_counter() - t0) / max(1, a.langzeit), 3),
                           ram_mb=ram, zuwachs_mb_je_runde=round((ram[-1] - ram[len(ram) // 3]) /
                                                                 max(1, len(ram) - len(ram) // 3 - 1), 2) if ram else None,
                           objekte=len(gc.get_objects()))
    print("LANGZEIT", erg["Langzeit"], flush=True)
    erg["diagnose"] = diagnose.bericht()
    (aus / "ergebnis.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
