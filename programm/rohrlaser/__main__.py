"""Programmstart: python -m rohrlaser (Entwicklung) bzw. Rohrlaser-Kalkulation.exe.

Die Datendatei liegt im Ordner 'Daten' neben dem Programm (portabel, keine Installation).
--daten ORDNER     anderer Datenordner
--selbsttest       Fenster aufbauen, alle Reiter einmal anzeigen, beenden (Rückgabewert 0 = in Ordnung);
                   mit --mappe DATEI zusätzlich die Stammdaten aus der Mappe übernehmen,
                   und den Auftrag der Mappe übernehmen, optimieren, Staffelpreise, PDFs und Excel-Export
                   erzeugen, mit --step DATEI … zusätzlich STEP-Dateien
                   messen und übernehmen, mit --ergebnis DATEI das Protokoll in eine Textdatei schreiben
                   (die .exe hat keine Konsole).
"""
import argparse
import sys
import tempfile
import traceback
from pathlib import Path

from . import NAME


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


def selbsttest(app, mappe, ergebnis, step_dateien=()):
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
            if mappe:
                if not f.mappe_uebernehmen(mappe, nachfragen=False):
                    raise RuntimeError(f"Übernahme aus {mappe} fehlgeschlagen")
                protokoll.append("Übernahme: " + ", ".join(f"{s.t.titel} {len(s.modell.daten)}" for s in f.seiten))
                aid = f.auftraege.aus_mappe(mappe)
                if not aid:
                    raise RuntimeError("Auftrag aus der Mappe nicht übernommen")
                seite = f.offen[aid]
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
                                    ("Kalkulation", seite.kalkulation_pdf), ("Excel-Export", seite.excel_export)):
                    datei = aufruf()
                    if not datei or Path(datei).stat().st_size < 1000:
                        raise RuntimeError(f"{art} nicht geschrieben")
                    protokoll.append(f"{art}: {Path(datei).name} ({Path(datei).stat().st_size // 1024} KB)")
                protokoll.append(f"Auftrag {seite.kopf['nummer']}: {len(seite.positionen)} Positionen, "
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
                f.auftrag_schliessen(aid)
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


def main(argv=None):
    ap = argparse.ArgumentParser(prog=NAME)
    ap.add_argument("--daten", help="Datenordner (Vorgabe: Ordner 'Daten' neben dem Programm)")
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--mappe")
    ap.add_argument("--ergebnis")
    ap.add_argument("--step", nargs="*", default=[])
    a = ap.parse_args(argv)

    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QApplication, QMessageBox
    QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))   # Komma als Dezimalzeichen
    app = QApplication(sys.argv[:1])
    app.setApplicationName(NAME)
    app.setStyle("Fusion")
    deutsch(app)
    if a.selbsttest:
        return selbsttest(app, a.mappe, a.ergebnis, a.step)

    from .datenbank import Datenbank
    from .fenster import Hauptfenster
    ordner = Path(a.daten) if a.daten else programmordner() / "Daten"
    try:
        db = Datenbank(ordner / "rohrlaser.db")
        db.sicherung_heute()
    except Exception as e:
        QMessageBox.critical(None, NAME, f"Die Datendatei in {ordner} lässt sich nicht öffnen:\n\n{e}")
        return 1
    f = Hauptfenster(db, programmordner())
    f.show()
    code = app.exec()
    db.schliessen()
    return code


if __name__ == "__main__":
    sys.exit(main())
