"""Fenster Angebots-Check (Plan A2/W7): die eine Sammelrückfrage vor dem Angebots-PDF bzw. dem Vorgang „Verschickt“,
auch jederzeit zum Ansehen (Menü Ausgaben, Strg+K). Jede Zeile mit „Hinspringen“; bei FEHLER geht es nur mit
Begründung weiter, sie steht danach im Versandverlauf des Angebots."""
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from . import stil
from .angebot_check import FEHLER, HINWEIS, WARNUNG, blockiert, erledigbar, offen

FARBE = {FEHLER: stil.ROT, WARNUNG: stil.GELB_TEXT, HINWEIS: stil.TEXT_GRAU}


class CheckDialog(QDialog):
    """weiter = Text des Weiter-Knopfs (None = nur ansehen, ein Knopf Schließen). Nach „Hinspringen“ ist der Dialog
    abgelehnt und ziel gesetzt; der Aufrufer springt dann hin. K1 (Patrick 08.11.2026): Punkte mit aktion bekommen
    „Erledigen“, oben „Alles Automatische erledigen“; danach ist der Dialog abgelehnt und aktionen gesetzt, der Aufrufer
    führt sie aus und zeigt den Check neu (nur mit erledigen=True)."""

    def __init__(self, parent, punkte, weiter=None, titel="Angebots-Check", erledigen=False):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.punkte, self.ziel, self.aktionen = punkte, None, []
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        n_offen, gesperrt = len(offen(punkte)), blockiert(punkte)
        if not punkte:
            kopf = "Alles erledigt: Kunde, Schnittplan, Positionen, Bohrungen, Fracht und Staffeln sind in Ordnung."
        elif not n_offen:
            kopf = "Keine offenen Punkte, nur Hinweise:"
        else:
            kopf = (f"<b>{n_offen} offene{'r' if n_offen == 1 else ''} Punkt{'e' if n_offen > 1 else ''}</b>"
                    + (" – mit FEHLER geht es nur mit Begründung weiter." if gesperrt and weiter else
                       " – bitte prüfen oder trotzdem weiter." if weiter else ""))
        k = QLabel(kopf)
        k.setWordWrap(True)
        lay.addWidget(k)
        auto = erledigbar(punkte) if erledigen else []
        self.alle_knopf = None
        if len(auto) > 1:
            self.alle_knopf = QPushButton(f"Alles Automatische erledigen ({len(auto)})")
            self.alle_knopf.setToolTip("Alle Punkte mit „Erledigen“ nacheinander vom Programm lösen lassen, danach "
                                       "prüft der Check neu")
            self.alle_knopf.clicked.connect(lambda: self._erledigen([p.aktion for p in auto]))
            lay.addWidget(self.alle_knopf, 0, Qt.AlignLeft)
        liste = QWidget()
        raster = QGridLayout(liste)
        raster.setContentsMargins(0, 0, 0, 0)
        raster.setColumnStretch(1, 1)
        self.hin_knoepfe, self.erledigen_knoepfe = [], []
        for r, p in enumerate(punkte):
            art = QLabel(f"<b style='color:{stil.umsetzen(FARBE[p.art])}'>{p.art}</b>")
            raster.addWidget(art, r, 0, Qt.AlignTop)
            text = escape(p.text) + (f"<br><span style='color:{stil.umsetzen(stil.TEXT_GRAU)}'>{escape(p.details)}"
                                     "</span>" if p.details else "")
            t = QLabel(text)
            t.setWordWrap(True)
            t.setTextInteractionFlags(Qt.TextSelectableByMouse)
            raster.addWidget(t, r, 1)
            if erledigen and getattr(p, "aktion", None):
                e = QPushButton("Erledigen")
                e.setToolTip({"optimieren": "Schnittplan jetzt neu optimieren",
                              "staffeln_rechnen": "Staffelpreise jetzt neu rechnen",
                              "preise": "Aktuelle Preise übernehmen (mit Rückgängig)",
                              "preisluecke": "Ähnlichen Profilpreis in Stammdaten → Preise anlegen (mit Rückgängig)",
                              "gravur": "Artikelnummer nach der Kundenvorgabe auf diese Teile gravieren",
                              "teilbestell": "Haken „Vorbehalt bei Teilbestellung“ setzen: das Angebot nennt den Text "
                                             "unter den Bedingungen"
                              }.get(p.aktion, ""))
                e.clicked.connect(lambda _=False, a=p.aktion: self._erledigen([a]))
                raster.addWidget(e, r, 3, Qt.AlignTop)
                self.erledigen_knoepfe.append(e)
            if p.ziel:
                b = QPushButton("Hinspringen")
                b.setToolTip("Fenster schließen und zur Stelle springen")
                b.clicked.connect(lambda _=False, z=p.ziel: self._hin(z))
                raster.addWidget(b, r, 2, Qt.AlignTop)
                self.hin_knoepfe.append(b)
        rahmen = QScrollArea()
        rahmen.setWidgetResizable(True)
        rahmen.setFrameShape(QScrollArea.NoFrame)
        rahmen.setWidget(liste)
        rahmen.setMaximumHeight(420)
        lay.addWidget(rahmen)
        self.begruendung = QLineEdit()
        self.begruendung.setPlaceholderText("Begründung (Pflicht bei FEHLER, steht im Versandverlauf)")
        self.begruendung.setVisible(bool(weiter) and gesperrt)
        lay.addWidget(self.begruendung)
        knoepfe = QDialogButtonBox()
        if weiter:
            self.weiter = knoepfe.addButton("Trotzdem weiter" if gesperrt else weiter, QDialogButtonBox.AcceptRole)
            knoepfe.addButton(QDialogButtonBox.Cancel)
            self.weiter.setEnabled(not gesperrt)
            self.begruendung.textChanged.connect(lambda t: self.weiter.setEnabled(bool(t.strip())))
            (self.begruendung if gesperrt else knoepfe.button(QDialogButtonBox.Cancel)).setFocus()
        else:
            self.weiter = None
            knoepfe.addButton(QDialogButtonBox.Close)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def _erledigen(self, aktionen):
        self.aktionen = list(dict.fromkeys(aktionen))
        self.reject()

    def _hin(self, ziel):
        self.ziel = ziel
        self.reject()

    def text_begruendung(self):
        return self.begruendung.text().strip()
