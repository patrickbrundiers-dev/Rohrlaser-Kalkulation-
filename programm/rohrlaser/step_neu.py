"""Neues Angebot direkt aus STEP-Dateien (Plan Arbeitsabläufe W11).

STEP-Dateien oder ein Ordner auf die Angebotsliste bzw. die Startseite ziehen oder „Neues Angebot aus STEP …“:
Das Programm schlägt den Kunden vor (kunde_vorschlag), legt das Angebot an (mit den Kundenvorgaben, W2), öffnet es
und startet den STEP-Import wie in der Positionsliste.
"""
import datetime
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


# „Anfrage 4711“, „Anfrage-Nr. 4711“, „Anfr. 4711“, „RFQ 4711“ im Ordnernamen (Plan Angebotsablauf V5)
REFERENZ = re.compile(r"(?:anfrage|anfr\.|rfq)\s*(?:-?\s*nr\.?|nummer)?\s*[:#-]?\s*([0-9][\w/.-]*|[a-z]+-?[0-9][\w/.-]*)",
                      re.IGNORECASE)


def referenz_aus_ordner(dateien):
    """Anfrage-Nr. des Kunden aus dem nächsten Ordnernamen der Dateien (z. B. „Müller Anfrage 4711“ → 4711), sonst
    None."""
    for d in map(Path, dateien or ()):
        ordner = d if d.is_dir() else d.parent
        for name in [ordner.name] + [p.name for p in ordner.parents][:ORDNER_TIEFE - 1]:
            m = REFERENZ.search(name or "")
            if m:
                return m.group(1).rstrip(".-")
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


def _mails_lesen(fenster, dateien):
    """E-Mails unter den gezogenen Dateien/Ordnern (Patrick 28.10.2026): STEP-Anhänge neben die Mail legen und Kunde,
    Anfrage-Nr., Lieferzeit, Bemerkung, Werkstoff und Stückzahlen wie im Anfrage-Ordner (anfragen.werte) vorbelegen.
    Ergebnis (Dateien samt ausgepackter STEP-Dateien, weitere Werte)."""
    from . import anfragen, mail
    pfade = anfragen.mails_neben(dateien)
    if not pfade:
        return dateien, {}
    dateien, mails = list(dateien), []
    for p in sorted(pfade, key=anfragen.quell_zeit):     # älteste zuerst; gleicher Name: die neueste Version gilt
        try:
            dateien += [str(d) for d in anfragen.neben_auspacken(p)]
        except OSError as e:
            fenster.meldung(f"Anhänge von {p.name} lassen sich nicht auspacken: {e}", fehler=True)
        m = mail.lesen(p) if p.suffix.lower() in anfragen.MAIL else None      # ZIP: nur auspacken
        if m:
            mails.append(m)
    return list(dict.fromkeys(dateien)), anfragen.werte(fenster.db, [], mails)[2]


def _alte_version(p):
    """'Teil1 (alt).step' neben 'Teil1.step': ältere Version aus einer früheren Mail, nicht importieren."""
    from . import anfragen
    p = Path(p)
    return anfragen.ist_alt(p) and p.with_name(anfragen.ALT.sub("", p.stem) + p.suffix).exists()


def neues_angebot(fenster, dateien=None, kundennr=None, kopf=None, formulare=None, vorschlag=None, hinweis=None,
                  werkstoff_text=None, neuer_kunde=None):
    """Angebot anlegen und die STEP-Dateien importieren. dateien: Dateien/Ordner (ohne: Dateiauswahl); kundennr:
    ohne Dialog (Tests, '' = ohne Kunde); kopf: weitere Kopffelder (z. B. kundenreferenz aus dem Anfrageformular);
    formulare: gelesene Anfrageformulare (Stückzahlen je Artikelnummer, W6b/W6c); aus einer E-Mail der Anfrage:
    vorschlag = Kunde (Absenderadresse), hinweis = Zeilen „Aus E-Mail/Formular“ für den Prüfdialog, werkstoff_text = Text,
    in dem der Import nach dem Werkstoff sucht; neuer_kunde = Stammdaten eines unbekannten Absenders (mail.kunde_daten):
    der Kunde wird angelegt (Bemerkung „Kunde prüfen“, Patrick 28.10.2026) und bei Abbruch wieder entfernt.
    Ergebnis: Angebotsseite oder None (abgebrochen, nichts angelegt)."""
    db = fenster.db
    if db.nur_lesen:
        fenster.meldung("Lesemodus: es lassen sich keine Angebote anlegen.", fehler=True)
        return None
    if not dateien:
        dateien, _ = QFileDialog.getOpenFileNames(fenster, "Neues Angebot aus STEP", str(step_ablage.start_ordner(db)),
                                                  "STEP-Dateien, E-Mails und ZIP (*.step *.stp *.STEP *.STP *.msg *.eml *.zip)")
        if not dateien:
            return None
    if formulare is None:           # Kundenordner oder Mail gezogen: E-Mail auslesen wie im Anfrage-Ordner
        dateien, w = _mails_lesen(fenster, dateien)
        kopf = dict(w.get("kopf") or {}, **(kopf or {}))
        formulare, hinweis = w.get("formulare"), hinweis or w.get("hinweis")
        vorschlag, werkstoff_text = vorschlag or w.get("vorschlag"), werkstoff_text or w.get("werkstoff_text")
        neuer_kunde = neuer_kunde or w.get("neuer_kunde")
    gefunden = [str(d) for d in step.step_dateien(dateien) if not _alte_version(d)]
    if not gefunden:
        if not fenster.stumm:
            QMessageBox.information(fenster, "Neues Angebot aus STEP", "Keine STEP-Dateien (*.step, *.stp) gefunden.")
        fenster.meldung("Keine STEP-Dateien gefunden.", fehler=True)
        return None
    step_ablage.ordner_merken(db, gefunden)
    waehlen = kundennr is None and not fenster.stumm     # Plan Bedienung B1: Kunde oben im Prüfdialog
    neu_angelegt = None
    if kundennr is None and not vorschlag and neuer_kunde:
        vorschlag, neu_angelegt = kunde_anlegen(db, neuer_kunde)
    if kundennr is None:
        kundennr = vorschlag or kunde_vorschlag(db, dateien) or ""
    i = db.angebot_neu(dict(kopf or {}, kundennr=kundennr or None))
    fenster.angebote.neu_laden()
    seite = fenster.angebot_oeffnen(i)
    extra = {n: w for n, w in (("formulare", formulare), ("hinweis", hinweis), ("werkstoff_text", werkstoff_text))
             if w}
    referenz = (kopf or {}).get("kundenreferenz") or referenz_aus_ordner(dateien)
    if seite.step_importieren(gefunden, kunde_waehlen=waehlen, referenz=referenz, **extra) is None \
            and not seite.positionen:
        # abgebrochen: das eben angelegte leere Angebot wieder entfernen (wie vorher beim Abbruch der Kundenwahl)
        fenster.angebot_schliessen(i)
        db.angebot_loeschen(i, trotz_schutz=True)     # eben angelegt, nie optimiert
        if neu_angelegt and not db.con.execute("SELECT 1 FROM angebote WHERE kundennr=?", (vorschlag,)).fetchone():
            db.loeschen("kunden", [neu_angelegt])       # mit dem Angebot auch den eben angelegten Kunden
        fenster.angebote.neu_laden()
        return None
    if neu_angelegt:
        fenster.meldung(f"Neuer Kunde {vorschlag} – {neuer_kunde.get('name')} angelegt (Bemerkung „Kunde prüfen“).")
    return seite


PRUEFEN = "Kunde prüfen"


def kunde_anlegen(db, daten):
    """Kunden aus mail.kunde_daten anlegen: nächste freie Kundennummer, Bemerkung „Kunde prüfen – aus E-Mail vom
    …“. Ergebnis (Kundennummer, Zeilen-ID) bzw. (None, None) wenn nicht möglich."""
    from . import mail, stammdaten
    try:
        nr = mail.neue_kundennr([k.get("kundennr") for k in db.zeilen("kunden")])
        felder = {f.name for f in stammdaten.KUNDEN.felder}
        werte = {k: v for k, v in daten.items() if k in felder and v}
        if not re.fullmatch(r"[A-Z]{2}", werte.get("land") or "DE"):
            werte.pop("land")
        werte.update(kundennr=nr, bemerkung=f"{PRUEFEN} – automatisch aus der Anfrage angelegt am "
                                            f"{datetime.date.today().strftime('%d.%m.%Y')}")
        return nr, db.neu("kunden", werte)
    except Exception:       # z. B. Lesemodus: dann ohne Kunden weiter
        return None, None
