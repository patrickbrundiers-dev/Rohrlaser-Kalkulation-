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


def update_test(quelle, alle=False):
    """Prüft im fertigen Programm das Online-Update ohne Bildschirm (Workflow Auslastung): bei offenem Fenster und
    offener Datenbank die Dateiliste aus quelle holen (mit Signaturprüfung), laden, beenden, alle geänderten Dateien
    austauschen. 0 = in Ordnung."""
    import os
    import tempfile
    import traceback
    from pathlib import Path
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from . import aktualisierung as A
    from . import aktualisierung_fenster, daten
    from .fenster import Hauptfenster
    zeilen, code = [], 1
    try:
        ordner = A.programmordner()
        if ordner is None:
            raise RuntimeError("--update-test nur im fertigen Programm (sonst würde der Quellordner ausgetauscht)")
        app = QApplication.instance() or QApplication([])
        db = daten.Daten(Path(tempfile.mkdtemp()) / "Auslastung.db")
        f = Hauptfenster(db, programmordner=ordner)
        f.show()
        app.processEvents()
        zeilen.append(f"Installiert: {f.updater.stand()}")
        online = A.online_liste(quelle)
        zeilen.append(f"Online: {A.stand_text(online)}")
        aus = A.laden(ordner, online, f.updater.lokal, quelle, alle=alle)
        f.close()
        db.schliessen()
        ergebnis = aktualisierung_fenster.nach_beenden(ordner, aus, starten=lambda *_: None, fragen=lambda _g: False)
        zeilen.append(f"Ausgetauscht: {len(aus['plan']['neu'])} Dateien, entfernt: {len(aus['plan']['weg'])}, "
                      f"Ergebnis: {ergebnis}")
        zeilen.append(f"Jetzt: {A.stand_text(A.lokale_liste(ordner))}")
        code = 0 if ergebnis == "ok" else 1
    except Exception:       # noqa: BLE001 – jeder Fehler gehört in die Ausgabe des Laufs
        zeilen.append(traceback.format_exc())
    zeilen.append("UPDATE OK" if code == 0 else "UPDATE FEHLER")
    text = "\n".join(zeilen)
    print(text)
    if os.environ.get("RLA_ERGEBNIS"):
        Path(os.environ["RLA_ERGEBNIS"]).write_text(text, encoding="utf-8")
    return code


def main(argv=None):
    from . import aktualisierung
    programm = aktualisierung.programmordner()
    aktualisierung.beim_start(programm)           # unterbrochenes Update zurückstellen, Reste löschen (jeder Start)
    if "--selbsttest" in (sys.argv if argv is None else argv):
        return selbsttest()
    if "--update-test" in (sys.argv if argv is None else argv):
        a = sys.argv if argv is None else argv
        return update_test(a[a.index("--update-test") + 1], alle="--alle" in a)
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication, QMessageBox
    from rohrlaser import mausrad, stil

    from . import NAME, aktualisierung_fenster, daten, ort
    from .fenster import Hauptfenster
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(NAME)
    mausrad.einrichten(app)        # das Mausrad rollt die Seite und ändert nie einen Wert (Patrick 11.11.2026)
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
    from . import lizenzen
    try:                                          # Plan 2.4: Lizenz dieses Rechners (die der Kalkulation gilt mit)
        stelle = lizenzen.Stelle(ort.basis())
    except Exception:                             # noqa: BLE001 – ohne prüfbare Lizenz: nur ansehen
        stelle = lizenzen.Stelle(ort.basis(), schluessel={})
    f = Hauptfenster(db, werkstatt=True if "--werkstatt" in argv else None, programmordner=programm, lizenz=stelle)
    stil.fenster_stil(f)
    f.show()
    if "--nach-update" in argv:                   # Neustart durch das Online-Update: sagen, wie es ausging
        art = (argv[argv.index("--nach-update") + 1:] + ["ok"])[0]
        f.hinweis(aktualisierung_fenster.NACH_UPDATE_TEXT.get(art, "{stand}").format(stand=f.updater.stand()))
    f.updater.beim_start()
    ende = app.exec()
    ausstehend = f.updater.ausstehend
    f.deleteLater()                               # Fenster geordnet löschen, solange die Anwendung noch lebt
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    if ausstehend:                                # Update geladen: Datenbank zu, Dateien austauschen, neu starten
        db.schliessen()
        aktualisierung_fenster.nach_beenden(programm, ausstehend)
    return ende


if __name__ == "__main__":
    sys.exit(main())
