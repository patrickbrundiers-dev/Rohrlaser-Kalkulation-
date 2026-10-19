"""Programmstart: python -m rohrlaser (Entwicklung) bzw. Rohrlaser-Angebotskalkulation.exe.

Die Datendatei liegt im Ordner 'Daten' neben dem Programm (portabel, keine Installation).
--daten ORDNER     anderer Datenordner
--selbsttest       Fenster aufbauen, alle Reiter einmal anzeigen, einen Beispielangebot anlegen, optimieren,
                   Staffelpreise, PDFs und CSV-Export erzeugen, beenden (Rückgabewert 0 = in Ordnung);
                   mit --step DATEI … zusätzlich STEP-Dateien messen und übernehmen, mit --ergebnis DATEI
                   das Protokoll in eine Textdatei schreiben (die .exe hat keine Konsole).
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
                if not datei or Path(datei).stat().st_size < 1000:
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


def main(argv=None):
    ap = argparse.ArgumentParser(prog=NAME)
    ap.add_argument("--daten", help="Datenordner (Vorgabe: Ordner 'Daten' neben dem Programm)")
    ap.add_argument("--selbsttest", action="store_true")
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
        return selbsttest(app, a.ergebnis, a.step)

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
