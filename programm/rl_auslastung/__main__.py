"""Start: python -m rl_auslastung (oder Rohrlaser-Auslastung.exe)."""
import sys


def selbsttest():
    """Prüft das gebaute Programm ohne Bildschirm: Datenbank anlegen, Auftrag in Worten eingeben, einlasten, fertig
    melden, Fenster füllen, PDF schreiben. 0 = in Ordnung."""
    import datetime
    import os
    import tempfile
    from pathlib import Path
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from . import daten, laufzeit
    from .fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])
    ordner = Path(tempfile.mkdtemp())
    db = daten.Daten(ordner / "Auslastung.db")
    heute = datetime.date(2026, 11, 11)
    a = db.auftrag_speichern(dict(nummer="T-1", maschine="LT7", kalk_min=laufzeit.lesen("1 Stunde 30 Minuten"),
                                  liefertermin=datetime.date(2026, 11, 20)))
    b = db.auftrag_speichern(dict(nummer="T-2", maschine="T03", kalk_min=laufzeit.lesen("90 Minuten")))
    db.fertig_melden(b, laufzeit.lesen("1:40"), datetime.date(2026, 11, 10))
    f = Hauptfenster(db, heute=heute)
    f.show()
    for i in range(f.reiter.count()):
        f.reiter.setCurrentIndex(i)
        app.processEvents()
    plan = {x["id"]: x for x in f.ein["auftraege"]}
    gut = (plan[a]["fertig"] == heute and f.si_liste.rowCount() == 1
           and Path(f.pdf(ordner / "test.pdf")).read_bytes().startswith(b"%PDF"))
    f.close()
    db.schliessen()
    print("Selbsttest Rohrlaser Auslastung:", "in Ordnung" if gut else "FEHLER")
    return 0 if gut else 1


def main(argv=None):
    if "--selbsttest" in (sys.argv if argv is None else argv):
        return selbsttest()
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication, QMessageBox
    from rohrlaser import stil

    from . import NAME, daten, ort
    from .fenster import Hauptfenster
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    app.setApplicationName(NAME)
    try:
        db = daten.Daten(ort.datenbank())
    except Exception as e:      # noqa: BLE001 – Ordner nicht erreichbar, Datei beschädigt, neuere Version
        QMessageBox.critical(None, NAME, f"Die Datenbank {ort.datenbank()} lässt sich nicht öffnen:\n{e}\n\n"
                             "Liegt sie in einem gemeinsamen Ordner, ist dieser gerade erreichbar? Der Ort steht in "
                             f"der Datei {ort.INI} neben dem Programm.")
        return 1
    try:
        db.sichern()
    except OSError:
        pass
    stil.anwenden(app, db.einstellung("design"))
    # --werkstatt: gleich in der Werkstatt-Ansicht starten (sonst so, wie es an diesem Platz gemerkt ist)
    f = Hauptfenster(db, werkstatt=True if "--werkstatt" in (sys.argv if argv is None else argv) else None)
    stil.fenster_stil(f)
    f.show()
    ende = app.exec()
    f.deleteLater()                               # Fenster geordnet löschen, solange die Anwendung noch lebt
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    return ende


if __name__ == "__main__":
    sys.exit(main())
