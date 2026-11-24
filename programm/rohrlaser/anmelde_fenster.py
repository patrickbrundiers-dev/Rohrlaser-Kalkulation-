"""Anmeldefenster der Hauptadmin-Lizenz (hauptadmin.py) und „Passwort ändern“ (Patrick 12.11.2026).

Beim Start erscheint das Fenster nur, wenn auf dem Rechner eine gültige Hauptadmin-Lizenz liegt (Kundenlizenzen,
Werkstatt-Rechner und die bisherige Admin-Lizenz starten wie bisher). Ohne richtiges Passwort (oder Notfallcode) öffnet
das Programm nicht: es gibt nur „Anmelden“ und „Beenden“. Nach mehreren Fehlversuchen zeigt das Fenster die Wartezeit
(Passwörter werden bis dahin abgelehnt, ein Notfallcode geht sofort).
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QToolButton, QVBoxLayout)

from . import NAME, stil
from . import hauptadmin as H

STIL = f"""
QFrame#anmeldeKopf {{ background: {stil.AKZENT}; border: none; }}
QLabel#anmeldeName {{ color: #FFFFFF; font-size: 15pt; font-weight: bold; }}
QLabel#anmeldeUnter {{ color: #DDEBF7; }}
QLabel#anmeldeInfo {{ color: {stil.TEXT_GRAU}; }}
QLabel#anmeldeFehler {{ color: {stil.ROT}; background: {stil.ROT_FLAECHE}; border: 1px solid {stil.ROT};
                        border-radius: 4px; }}
QLabel#anmeldeSperre {{ color: {stil.GELB_TEXT}; background: {stil.GELB_FLAECHE}; border: 1px solid #E8C66B;
                        border-radius: 4px; }}
QLabel#anmeldeTipp {{ color: {stil.TEXT_GRAU}; font-size: 8.5pt; }}
QLineEdit#anmeldePasswort {{ padding: 4px 6px; }}
"""


def _stil():
    try:
        return stil.umsetzen(STIL)
    except Exception:       # noqa: BLE001 – ohne Theme (Tests): helle Farben
        return STIL


def _passwortfeld(platzhalter=""):
    """Passwortfeld mit Knopf „Anzeigen“ (Zeile, Feld)."""
    feld = QLineEdit()
    feld.setEchoMode(QLineEdit.Password)
    feld.setObjectName("anmeldePasswort")
    feld.setPlaceholderText(platzhalter)
    feld.setMinimumHeight(30)
    zeigen = QToolButton()
    zeigen.setText("Anzeigen")
    zeigen.setCheckable(True)
    zeigen.setToolTip("Passwort beim Tippen lesbar anzeigen")
    zeigen.toggled.connect(lambda an: feld.setEchoMode(QLineEdit.Normal if an else QLineEdit.Password))
    zeile = QHBoxLayout()
    zeile.setSpacing(6)
    zeile.addWidget(feld, 1)
    zeile.addWidget(zeigen)
    return zeile, feld


class AnmeldeDialog(QDialog):
    """Hauptadmin-Anmeldung: Passwort oder Notfallcode. accept() erst nach erfolgreicher Anmeldung."""

    def __init__(self, stelle, eltern=None, titel="Hauptadmin-Anmeldung", name=NAME):
        super().__init__(eltern)
        self.stelle = stelle
        self.ergebnis = None
        self.setWindowTitle(f"{name} – Anmeldung")
        self.setModal(True)
        self.setFixedWidth(480)             # feste Breite: umbrochene Texte bekommen die richtige Höhe
        self.setStyleSheet(_stil())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        kopf = QFrame()
        kopf.setObjectName("anmeldeKopf")
        kl = QVBoxLayout(kopf)
        kl.setContentsMargins(22, 18, 22, 16)
        name = QLabel(name)
        name.setObjectName("anmeldeName")
        unter = QLabel(f"\N{LOCK}  {titel}")
        unter.setObjectName("anmeldeUnter")
        kl.addWidget(name)
        kl.addWidget(unter)
        lay.addWidget(kopf)
        innen = QVBoxLayout()
        innen.setContentsMargins(22, 16, 22, 18)
        innen.setSpacing(8)
        _, inhalt, _ = stelle.hauptadmin_lesen()
        inhalt = inhalt or {}
        self.info = QLabel(f"Lizenz {inhalt.get('lizenz_id', '–')} · {inhalt.get('inhaber') or 'Hauptadmin'} · "
                           "gilt auf allen eigenen Rechnern (ohne Rechner-ID)")
        self.info.setObjectName("anmeldeInfo")
        self.info.setWordWrap(True)
        innen.addWidget(self.info)
        innen.addSpacing(4)
        innen.addWidget(QLabel("<b>Passwort</b>"))
        zeile, self.passwort = _passwortfeld("Hauptadmin-Passwort oder Notfallcode")
        innen.addLayout(zeile)
        self.fehler = QLabel()
        self.fehler.setObjectName("anmeldeFehler")
        self.fehler.setWordWrap(True)
        self.fehler.setMargin(6)                    # Abstand innen (Polsterung im Stil verfälscht die Höhe beim Umbruch)
        self.fehler.hide()
        innen.addWidget(self.fehler)
        self.sperre = QLabel()
        self.sperre.setObjectName("anmeldeSperre")
        self.sperre.setWordWrap(True)
        self.sperre.setMargin(6)                    # Abstand innen (Polsterung im Stil verfälscht die Höhe beim Umbruch)
        self.sperre.hide()
        innen.addWidget(self.sperre)
        tipp = QLabel("Passwort vergessen? Im Lizenz-Werkzeug einen Notfallcode für die Rechner-ID "
                      f"<b>{stelle.rechner or '?'}</b> erzeugen und hier eingeben.")
        tipp.setObjectName("anmeldeTipp")
        tipp.setWordWrap(True)
        tipp.setTextInteractionFlags(Qt.TextSelectableByMouse)
        innen.addWidget(tipp)
        knoepfe = QHBoxLayout()
        knoepfe.addStretch(1)
        self.beenden = QPushButton("Beenden")
        self.beenden.clicked.connect(self.reject)
        self.anmelden = QPushButton("Anmelden")
        self.anmelden.setObjectName("primaer")
        self.anmelden.setDefault(True)
        self.anmelden.clicked.connect(lambda: self.versuchen())
        knoepfe.addWidget(self.beenden)
        knoepfe.addWidget(self.anmelden)
        innen.addSpacing(6)
        innen.addLayout(knoepfe)
        lay.addLayout(innen)
        self.passwort.returnPressed.connect(lambda: self.versuchen())
        self.uhr = QTimer(self)
        self.uhr.setInterval(1000)
        self.uhr.timeout.connect(self.sperre_anzeigen)
        self.sperre_anzeigen()
        self.passwort.setFocus()

    def sperre_anzeigen(self):
        """Wartezeit nach Fehlversuchen: Hinweis mit Restzeit (die Anmeldung lehnt Passwörter bis dahin ab, ein
        Notfallcode geht sofort)."""
        warten = self.stelle.sperre().wartezeit()
        if warten:
            self.sperre.setText(f"Zu viele Fehlversuche – nächster Versuch in {H.warte_text(warten)}. Ein "
                                "Notfallcode geht sofort.")
            self.sperre.show()
            if not self.uhr.isActive():
                self.uhr.start()
        else:
            self.sperre.hide()
            self.uhr.stop()
        return warten

    def versuchen(self, text=None):
        """Anmelden mit dem eingegebenen (oder übergebenen) Passwort. Ergebnis: True = angemeldet."""
        text = self.passwort.text() if text is None else text
        self.passwort.clear()
        e = self.stelle.hauptadmin_anmelden(text)
        self.ergebnis = e
        if e.ok:
            self.fehler.hide()
            self.accept()
            return True
        self.fehler.setText(e.text)
        self.fehler.setVisible(not e.warten)        # bei Sperre sagt der gelbe Hinweis alles
        self.sperre_anzeigen()
        self.adjustSize()
        self.passwort.setFocus()
        return False


def anmelden(stelle, eltern=None, ausfuehren=None, name=NAME):
    """Anmeldefenster zeigen. ausfuehren(dialog) ersetzt exec() (Tests). Ergebnis: True = angemeldet."""
    d = AnmeldeDialog(stelle, eltern, name=name)
    ok = (ausfuehren(d) if ausfuehren else d.exec())
    return bool(ok) and stelle.hauptadmin_ok


def hauptadmin_beim_start(stelle, ausfuehren=None, protokoll=None, name=NAME):
    """Beim Start: Liegt eine gültige Hauptadmin-Lizenz auf dem Rechner, muss man sich anmelden, sonst startet das
    Programm nicht. Ohne Hauptadmin-Lizenz (Kunden, Werkstatt): sofort True, wie bisher. Ein Fehler in der Anmeldung
    lässt das Programm zu (nie offen ohne Passwort). Ergebnis: True = weiter starten, False = beenden."""
    if stelle is None:
        return True
    try:
        if not stelle.hauptadmin_noetig():
            return True
        return anmelden(stelle, None, ausfuehren, name)
    except Exception:       # noqa: BLE001
        import traceback
        if protokoll:
            protokoll("Hauptadmin-Anmeldung fehlgeschlagen:\n" + traceback.format_exc())
        if ausfuehren is None:
            QMessageBox.critical(None, name, "Die Hauptadmin-Anmeldung ist fehlgeschlagen (Protokoll). Das Programm "
                                             "wird beendet.")
        return False


class PasswortAendernDialog(QDialog):
    """Hauptadmin: Passwort ändern (bisheriges, neues, Wiederholung). Die Datei bekommt einen neuen Tresor."""

    def __init__(self, stelle, eltern=None):
        super().__init__(eltern)
        self.stelle = stelle
        self.setWindowTitle("Hauptadmin – Passwort ändern")
        self.setFixedWidth(460)
        self.setStyleSheet(_stil())
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        text = QLabel(f"Mindestens {H.PASSWORT_MIN} Zeichen. Danach gilt auf diesem Rechner nur noch das neue "
                      "Passwort. Für deine anderen Rechner die Datei über <i>Hauptadmin → Hauptadmin-Datei für weitere "
                      "Rechner speichern …</i> mitnehmen.")
        text.setWordWrap(True)
        text.setObjectName("anmeldeInfo")
        lay.addWidget(text)
        self.felder = []
        for titel in ("Bisheriges Passwort", "Neues Passwort", "Neues Passwort wiederholen"):
            lay.addWidget(QLabel(f"<b>{titel}</b>"))
            zeile, feld = _passwortfeld()
            lay.addLayout(zeile)
            self.felder.append(feld)
        self.alt, self.neu, self.wieder = self.felder
        self.fehler = QLabel()
        self.fehler.setObjectName("anmeldeFehler")
        self.fehler.setWordWrap(True)
        self.fehler.setMargin(6)                    # Abstand innen (Polsterung im Stil verfälscht die Höhe beim Umbruch)
        self.fehler.hide()
        lay.addWidget(self.fehler)
        knoepfe = QHBoxLayout()
        knoepfe.addStretch(1)
        ab = QPushButton("Abbrechen")
        ab.clicked.connect(self.reject)
        self.ok = QPushButton("Passwort ändern")
        self.ok.setObjectName("primaer")
        self.ok.setDefault(True)
        self.ok.clicked.connect(lambda: self.aendern())
        knoepfe.addWidget(ab)
        knoepfe.addWidget(self.ok)
        lay.addLayout(knoepfe)

    def aendern(self, alt=None, neu=None, wieder=None):
        alt = self.alt.text() if alt is None else alt
        neu = self.neu.text() if neu is None else neu
        wieder = self.wieder.text() if wieder is None else wieder
        if neu != wieder:
            return self._fehler("Die beiden neuen Passwörter sind nicht gleich.")
        fehler = H.passwort_regeln(neu, alt)
        if fehler:
            return self._fehler(fehler)
        try:
            self.stelle.hauptadmin_passwort_aendern(alt, neu)
        except H.HauptadminFehler as e:
            for f in self.felder:
                f.clear()
            return self._fehler(str(e))
        self.accept()
        return True

    def _fehler(self, text):
        self.fehler.setText(text)
        self.fehler.show()
        return False
