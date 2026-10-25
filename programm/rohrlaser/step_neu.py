"""Neues Angebot direkt aus STEP-Dateien (Plan Arbeitsabläufe W11).

STEP-Dateien oder ein Ordner auf die Angebotsliste bzw. die Startseite ziehen oder „Neues Angebot aus STEP …“:
Das Programm schlägt den Kunden vor (kunde_vorschlag), legt das Angebot an (mit den Kundenvorgaben, W2), öffnet es
und startet den STEP-Import wie in der Positionsliste.
"""
import re
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from . import step, step_ablage

OHNE_KUNDE = "(ohne Kunde)"
ORDNER_TIEFE = 4            # so viele Ordner oberhalb der Dateien werden nach einem Kunden durchsucht


def _wort(text):
    return re.sub(r"[^0-9a-zäöüß]+", " ", str(text or "").lower()).strip()


def kunde_aus_ordner(kunden, dateien):
    """Kundennummer, deren Nummer oder Name in einem Ordnernamen der Dateien steht (nächster Ordner zuerst),
    sonst None. Namen zählen ab 3 Zeichen; ein Ordner „Müller GmbH Anfrage 12“ passt zu „Müller GmbH“."""
    ordner = []
    for d in map(Path, dateien):
        teile = [p.name for p in (d if d.is_dir() else d.parent).parents][:ORDNER_TIEFE - 1]
        for name in [(d if d.is_dir() else d.parent).name] + teile:
            if name and name not in ordner:
                ordner.append(name)
    for name in ordner:
        w = f" {_wort(name)} "
        for k in kunden:
            nr = _wort(k.get("kundennr"))
            if nr and f" {nr} " in w:
                return k["kundennr"]
        for k in sorted(kunden, key=lambda k: -len(_wort(k.get("name")))):     # längster Name zuerst
            n = _wort(k.get("name"))
            if len(n) >= 3 and f" {n} " in w:
                return k["kundennr"]
    return None


def kunde_vorschlag(db, dateien):
    """Vorschlag für den Kunden: aus dem Ordnernamen, sonst der Kunde des zuletzt geänderten eigenen Angebots mit
    Importprofil, sonst None."""
    kunden = db.zeilen("kunden")
    nr = kunde_aus_ordner(kunden, dateien)
    if nr:
        return nr
    mit_profil = {str(z.get("kundennr")) for z in db.zeilen("importprofile") if z.get("kundennr")}
    bekannt = {str(k["kundennr"]) for k in kunden}
    for a in sorted(db.angebote(), key=lambda a: a.get("geaendert") or "", reverse=True):
        if not a.get("fremd") and str(a.get("kundennr")) in mit_profil & bekannt:
            return a["kundennr"]
    return None


def neues_angebot(fenster, dateien=None, kundennr=None):
    """Angebot anlegen und die STEP-Dateien importieren. dateien: Dateien/Ordner (ohne: Dateiauswahl); kundennr:
    ohne Dialog (Tests, '' = ohne Kunde). Ergebnis: Angebotsseite oder None (abgebrochen, nichts angelegt)."""
    db = fenster.db
    if db.nur_lesen:
        fenster.meldung("Lesemodus: es lassen sich keine Angebote anlegen.", fehler=True)
        return None
    if not dateien:
        dateien, _ = QFileDialog.getOpenFileNames(fenster, "Neues Angebot aus STEP", str(step_ablage.start_ordner(db)),
                                                  "STEP-Dateien (*.step *.stp *.STEP *.STP)")
        if not dateien:
            return None
    gefunden = [str(d) for d in step.step_dateien(dateien)]
    if not gefunden:
        if not fenster.stumm:
            QMessageBox.information(fenster, "Neues Angebot aus STEP", "Keine STEP-Dateien (*.step, *.stp) gefunden.")
        fenster.meldung("Keine STEP-Dateien gefunden.", fehler=True)
        return None
    step_ablage.ordner_merken(db, gefunden)
    waehlen = kundennr is None and not fenster.stumm     # Plan Bedienung B1: Kunde oben im Prüfdialog
    if kundennr is None:
        kundennr = kunde_vorschlag(db, dateien) or ""
    i = db.angebot_neu(dict(kundennr=kundennr or None))
    fenster.angebote.neu_laden()
    seite = fenster.angebot_oeffnen(i)
    if seite.step_importieren(gefunden, kunde_waehlen=waehlen) is None and not seite.positionen:
        # abgebrochen: das eben angelegte leere Angebot wieder entfernen (wie vorher beim Abbruch der Kundenwahl)
        fenster.angebot_schliessen(i)
        db.angebot_loeschen(i)
        fenster.angebote.neu_laden()
        return None
    return seite
