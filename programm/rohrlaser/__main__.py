"""Programmstart: python -m rohrlaser (Entwicklung) bzw. Rohrlaser-Angebotskalkulation.exe.

Wo die Datendatei liegt, entscheidet orte.py: portabel (Portabel.ini im ZIP) im Ordner 'Daten' neben dem Programm,
installiert im Benutzerprofil (%LOCALAPPDATA%\\Rohrlaser Angebotskalkulation\\Daten).
--daten ORDNER     anderer Datenordner
--info             Datenort, Art (portabel/installiert) und Inhalt der Datendatei als JSON schreiben (--ergebnis DATEI)
                   und beenden; legt die Datendatei an, wenn es sie noch nicht gibt (Build-Test des Installers)
--selbsttest       Fenster aufbauen, alle Reiter einmal anzeigen, einen Beispielangebot anlegen, optimieren,
                   Staffelpreise, PDFs und CSV-Export erzeugen, beenden (Rückgabewert 0 = in Ordnung);
                   mit --step DATEI … zusätzlich STEP-Dateien messen und übernehmen, mit --ergebnis DATEI
                   das Protokoll in eine Textdatei schreiben (die .exe hat keine Konsole).
--update-test QUELLE  Online-Update aus QUELLE (Dateiliste Update.json, Adresse oder Pfad) bei offenem
                   Hauptfenster einspielen und beenden; --alle tauscht jede Programmdatei aus (prüft im Build,
                   dass sich die laufende .exe und alle geladenen Bibliotheken austauschen lassen).
"""
import argparse
import json
import sys
import tempfile
import traceback
from pathlib import Path

from . import NAME, VERSION


def programmordner():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def deutsch(app):
    """Deutsche Texte für Qt-Standarddialoge (Ja/Nein, Abbrechen, Dateiauswahl), falls die Übersetzung dabei ist."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    uebersetzung = QTranslator(app)
    if uebersetzung.load(QLocale(QLocale.German, QLocale.Germany), "qtbase", "_",
                         QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(uebersetzung)


# Beispielangebot für den Selbsttest (Profile und Werkstoffe aus den Beispieldaten)
BEISPIEL = [dict(pos=10, artikel="BSP-001", bezeichnung="Holm", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                 laenge=1250, stueck=12, schneidweg=266.4, einstiche=2),
            dict(pos=20, artikel="BSP-002", bezeichnung="Strebe", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                 laenge=860, stueck=20, schneidweg=330, einstiche=4, gewinde="2xM6"),
            dict(pos=30, artikel="BSP-003", bezeichnung="Rahmen", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                 laenge=2150, stueck=6, schneidweg=345, einstiche=3)]


def selbsttest(app, ergebnis, step_dateien=()):
    from .datenbank import Datenbank
    from .fenster import Hauptfenster
    protokoll = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db = Datenbank(Path(tmp) / "rohrlaser.db")
            f = Hauptfenster(db, programmordner(), stumm=True)
            f.show()
            for i in range(f.reiter.count()):
                f.reiter.setCurrentIndex(i)
                app.processEvents()
                protokoll.append(f"Reiter {f.reiter.tabText(i)}: ok")
            protokoll.append("Stammdaten: " + ", ".join(f"{s.t.titel} {len(s.modell.daten)}" for s in f.seiten))
            aid = db.angebot_neu(dict(kunde="Selbsttest"))
            for p in BEISPIEL:
                db.position_neu(aid, p)
            seite = f.angebot_oeffnen(aid)
            if not seite.optimieren():
                raise RuntimeError("Optimierung fehlgeschlagen")
            for i in range(seite.reiter.count()):
                seite.reiter.setCurrentIndex(i)
                app.processEvents()
            e = seite.ergebnis
            db.einstellung_setzen("ablageordner", str(Path(tmp) / "Ablage"))
            if not seite.stufen:
                db.staffel_neu(aid, dict(schluessel=str(seite.positionen[0]["pos"]), menge=10))
                seite.neu_laden()
            sp = seite.staffelpreise_rechnen()
            if not sp or any(str(z.get("hinweis") or "").startswith("FEHLER") for z in sp):
                raise RuntimeError(f"Staffelpreise fehlerhaft: {sp}")
            protokoll.append(f"Staffelpreise: {len(sp)} Stufen, " + ", ".join(
                f"{z['menge']} {z['einheit']} {z['preis_einheit']:.2f} €" for z in sp))
            for art, aufruf in (("Angebot", seite.angebot_pdf), ("Werkstattpapiere", seite.werkstatt_pdf),
                                ("Kalkulation", seite.kalkulation_pdf), ("CSV-Export", seite.csv_export)):
                datei = aufruf()
                if not datei or Path(datei).stat().st_size < (300 if art == "CSV-Export" else 1000):    # ZIP ist klein
                    raise RuntimeError(f"{art} nicht geschrieben")
                protokoll.append(f"{art}: {Path(datei).name} ({Path(datei).stat().st_size // 1024} KB)")
            protokoll.append(f"Angebot {seite.kopf['nummer']}: {len(seite.positionen)} Positionen, "
                             f"{len(e['stangen'])} Stangen, Stand {seite.stand_optimierung()}, "
                             f"Verkaufspreis {seite.kalk.zeilen and sum(z['preis_position'] or 0 for z in seite.kalk.zeilen):.2f}")
            if step_dateien:
                erg = seite.step_importieren(list(step_dateien), werkstoff=None, stueck=10)
                if not erg or len(erg["positionen"]) == 0:
                    raise RuntimeError("STEP-Import ohne Ergebnis")
                protokoll.append(f"STEP-Import: {len(erg['positionen'])} Positionen, "
                                 f"Protokoll {len(seite.prot.zeilen)} Zeilen")
                seite.optimieren()
                protokoll.append(f"Neu optimiert: {len(seite.ergebnis['stangen'])} Stangen")
            f.angebot_schliessen(aid)
            f.sicherung_erstellen()
            protokoll.append("Sicherung: ok")
            f.close()
            db.schliessen()
        protokoll.append("SELBSTTEST OK")
        code = 0
    except Exception:
        protokoll.append(traceback.format_exc())
        protokoll.append("SELBSTTEST FEHLER")
        code = 1
    text = "\n".join(protokoll)
    if ergebnis:
        Path(ergebnis).write_text(text, encoding="utf-8")
    else:
        print(text)
    return code


def update_test(app, quelle, ergebnis, alle):
    from .datenbank import Datenbank
    from .fenster import Hauptfenster
    from . import update
    protokoll = []
    try:
        if not getattr(sys, "frozen", False):
            raise RuntimeError("--update-test nur im fertigen Programm (sonst würde der Quellordner ausgetauscht)")
        with tempfile.TemporaryDirectory() as tmp:
            db = Datenbank(Path(tmp) / "rohrlaser.db")
            f = Hauptfenster(db, programmordner(), stumm=True)
            f.show()
            f.angebot_oeffnen(db.angebot_neu(dict(kunde="Update-Test")))
            app.processEvents()
            protokoll.append(f"Installiert: {update.stand_text(update.lokale_liste(programmordner()))}")
            online, plan = update.aktualisieren(programmordner(), quelle, alle=alle)
            protokoll.append(f"Online: {update.stand_text(online)}")
            if plan:
                protokoll.append(f"Ausgetauscht: {len(plan['neu'])} Dateien aus {len(plan['pakete'])} Paketen "
                                 f"({plan['groesse'] / 1e6:.1f} MB), entfernt: {len(plan['weg'])}")
            protokoll.append(f"Jetzt: {update.stand_text(update.lokale_liste(programmordner()))}")
            f.close()
            db.schliessen()
        protokoll.append("UPDATE OK")
        code = 0
    except Exception:
        protokoll.append(traceback.format_exc())
        protokoll.append("UPDATE FEHLER")
        code = 1
    text = "\n".join(protokoll)
    if ergebnis:
        Path(ergebnis).write_text(text, encoding="utf-8")
    else:
        print(text)
    return code


def info(orte_, ergebnis):
    """--info: Orte und Inhalt der Datendatei (öffnet sie mit Sperre wie beim normalen Start)."""
    from . import orte
    from .datenbank import Datenbank, SCHEMA_VERSION, datei_info
    werte = dict(programm=str(orte_.programm), daten=str(orte_.daten), datei=str(orte_.datei),
                 ablage=str(orte_.ablage), portabel=orte_.portabel, grund=orte_.grund, schema_programm=SCHEMA_VERSION)
    try:
        sperre = orte.Sperre(orte_.daten)
        try:
            db = Datenbank(orte_.datei)
            db.schliessen()
            werte.update(datei_info(orte_.datei))
        finally:
            sperre.freigeben()
        code = 0
    except Exception:
        werte["fehler"] = traceback.format_exc()
        code = 1
    text = json.dumps(werte, indent=1, ensure_ascii=False)
    if ergebnis:
        Path(ergebnis).write_text(text, encoding="utf-8")
    else:
        print(text)
    return code


def erster_start(orte_):
    """Noch keine Datendatei: vorhandene Daten (Datendatei, Sicherung oder Export) übernehmen oder mit
    Beispieldaten beginnen. Ergebnis: False, wenn das Programm beendet werden soll."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from .datenbank import datei_uebernehmen
    m = QMessageBox(QMessageBox.Question, NAME,
                    f"Hier gibt es noch keine Daten ({orte_.art}, Datenordner {orte_.daten}).\n\n"
                    "Vorhandene Daten aus einer anderen Programmversion übernehmen (Datendatei rohrlaser.db, eine "
                    "Sicherung oder eine Export-Datei)? Die Quelle bleibt dabei unverändert.")
    uebernehmen = m.addButton("Daten übernehmen …", QMessageBox.AcceptRole)
    m.addButton("Mit Beispieldaten beginnen", QMessageBox.RejectRole)
    m.exec()
    while m.clickedButton() is uebernehmen:
        datei, _ = QFileDialog.getOpenFileName(None, "Daten übernehmen", str(Path.home()),
                                               "Datendatei, Sicherung oder Export (*.db *.zip)")
        if not datei:
            return True
        try:
            i = datei_uebernehmen(datei, orte_.datei)
            QMessageBox.information(None, NAME, f"Daten übernommen: {i['anzahl'].get('angebote', 0)} Angebote "
                                                f"aus {datei}.")
            return True
        except OSError as e:
            QMessageBox.warning(None, NAME, f"Die Daten lassen sich nicht übernehmen:\n\n{e}")
    return True


def oeffnen_fehlgeschlagen(orte_, fehler):
    """Datendatei lässt sich nicht öffnen: Sicherung wählen und an ihre Stelle legen (die defekte Datei wird
    verschoben, nicht gelöscht). Ergebnis: True, wenn es noch einmal versucht werden soll."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from .datenbank import datei_uebernehmen
    m = QMessageBox(QMessageBox.Critical, NAME, f"Die Datendatei in {orte_.daten} lässt sich nicht öffnen:\n\n"
                                                f"{fehler}\n\nEine Sicherung wiederherstellen? Die jetzige Datei "
                                                "bleibt im Ordner Sicherung erhalten.")
    zurueck = m.addButton("Sicherung wiederherstellen …", QMessageBox.AcceptRole)
    m.addButton("Beenden", QMessageBox.RejectRole)
    m.exec()
    if m.clickedButton() is not zurueck:
        return False
    datei, _ = QFileDialog.getOpenFileName(None, "Sicherung wiederherstellen", str(orte_.daten / "Sicherung"),
                                           "Sicherung oder Export (*.db *.zip)")
    if not datei:
        return False
    try:
        datei_uebernehmen(datei, orte_.datei)
        return True
    except OSError as e:
        QMessageBox.critical(None, NAME, f"Die Sicherung lässt sich nicht wiederherstellen:\n\n{e}")
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(prog=NAME)
    ap.add_argument("--daten", help="Datenordner (Vorgabe: siehe orte.py)")
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--ergebnis")
    ap.add_argument("--step", nargs="*", default=[])
    ap.add_argument("--update-test")
    ap.add_argument("--alle", action="store_true")
    a = ap.parse_args(argv)

    from . import orte, update
    update.aufraeumen(programmordner())        # Reste eines Updates (alte Dateien sind jetzt frei)

    from PySide6.QtCore import QLocale, QStandardPaths
    from PySide6.QtWidgets import QApplication, QMessageBox
    QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))   # Komma als Dezimalzeichen
    app = QApplication(sys.argv[:1])
    app.setApplicationName(NAME)
    app.setStyle("Fusion")
    from .stil import ziffern_tabellarisch
    ziffern_tabellarisch(app)
    from . import mausrad
    mausrad.einrichten(app)
    deutsch(app)
    if a.selbsttest:
        return selbsttest(app, a.ergebnis, a.step)
    if a.update_test:
        return update_test(app, a.update_test, a.ergebnis, a.alle)

    dokumente = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or None
    o = orte.ermitteln(programmordner(), a.daten, dokumente=dokumente)
    if a.info:
        return info(o, a.ergebnis)

    from . import protokoll
    from .datenbank import Datenbank
    from .fenster import Hauptfenster
    protokoll.einrichten(o.daten / "Protokoll")
    protokoll.info(f"Start {NAME} {VERSION} ({o.art}, Daten {o.daten})")
    try:
        sperre = orte.Sperre(o.daten)
    except orte.Gesperrt as e:
        QMessageBox.warning(None, NAME, f"{e}\n\nBitte dort zuerst beenden. Zwei Programme dürfen nicht "
                                        "gleichzeitig mit derselben Datendatei arbeiten.")
        return 1
    except OSError as e:
        QMessageBox.critical(None, NAME, f"Im Datenordner {o.daten} darf das Programm nicht schreiben:\n\n{e}")
        return 1
    try:
        if not o.datei.exists():
            erster_start(o)
        while True:
            try:
                db = Datenbank(o.datei)
                db.sicherung_heute()
                break
            except Exception as e:
                if not oeffnen_fehlgeschlagen(o, e):
                    return 1
        f = Hauptfenster(db, programmordner(), orte=o)
        f.starten()
        code = app.exec()
        db.schliessen()
        return code
    finally:
        sperre.freigeben()


if __name__ == "__main__":
    sys.exit(main())
