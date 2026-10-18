"""Programmstart: python -m rohrlaser (Entwicklung) bzw. Rohrlaser-Kalkulation.exe.

Die Datendatei liegt im Ordner 'Daten' neben dem Programm (portabel, keine Installation).
--daten ORDNER     anderer Datenordner
--selbsttest       Fenster aufbauen, alle Reiter einmal anzeigen, beenden (Rückgabewert 0 = in Ordnung);
                   mit --mappe DATEI zusätzlich die Stammdaten aus der Mappe übernehmen,
                   mit --ergebnis DATEI das Protokoll in eine Textdatei schreiben (die .exe hat keine Konsole).
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


def selbsttest(app, mappe, ergebnis):
    from .datenbank import Datenbank
    from .fenster import Hauptfenster
    protokoll = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db = Datenbank(Path(tmp) / "rohrlaser.db")
            f = Hauptfenster(db)
            f.show()
            for i in range(f.reiter.count()):
                f.reiter.setCurrentIndex(i)
                app.processEvents()
                protokoll.append(f"Reiter {f.reiter.tabText(i)}: ok")
            if mappe:
                if not f.mappe_uebernehmen(mappe, nachfragen=False):
                    raise RuntimeError(f"Übernahme aus {mappe} fehlgeschlagen")
                protokoll.append("Übernahme: " + ", ".join(f"{s.t.titel} {len(s.modell.daten)}" for s in f.seiten))
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
    a = ap.parse_args(argv)

    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QApplication, QMessageBox
    QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))   # Komma als Dezimalzeichen
    app = QApplication(sys.argv[:1])
    app.setApplicationName(NAME)
    app.setStyle("Fusion")
    if a.selbsttest:
        return selbsttest(app, a.mappe, a.ergebnis)

    from .datenbank import Datenbank
    from .fenster import Hauptfenster
    ordner = Path(a.daten) if a.daten else programmordner() / "Daten"
    try:
        db = Datenbank(ordner / "rohrlaser.db")
        db.sicherung_heute()
    except Exception as e:
        QMessageBox.critical(None, NAME, f"Die Datendatei in {ordner} lässt sich nicht öffnen:\n\n{e}")
        return 1
    f = Hauptfenster(db)
    f.show()
    code = app.exec()
    db.schliessen()
    return code


if __name__ == "__main__":
    sys.exit(main())
