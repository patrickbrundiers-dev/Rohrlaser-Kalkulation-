"""Karte „Neue Anfragen“ auf der Startseite (Plan W6a): Anfragen aus dem Anfrage-Ordner (anfragen.py), Öffnen als
neues Angebot aus STEP, mehrere Anfragen eines Kunden auf Wunsch zusammen. Sichtbar nur mit Einstellung
„anfrage_ordner“; alle ANFRAGEN_S Sekunden wird nachgesehen."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, \
    QPushButton

from . import anfragen, angebotsordner

ANFRAGEN_S = 30             # Sekunden zwischen zwei Blicken in den Ordner


class AnfragenKarte:
    """Baut die Karte (self.karte) und hält die Anfragen (self.anfragen)."""

    def __init__(self, fenster):
        from .angebot_oben import karte
        self.f = fenster
        self.karte, lay = karte("Neue Anfragen")
        self.titel = QLabel()
        self.titel.setWordWrap(True)
        lay.addWidget(self.titel)
        self.liste = QListWidget()
        self.liste.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.liste.setToolTip("Doppelklick öffnet die Anfrage als neues Angebot. Mehrere markieren (Strg) und "
                              "„Zusammen öffnen“ rechnet sie in einem Angebot.")
        self.liste.itemActivated.connect(lambda it: self.oeffnen([self._anfrage(it)]))
        self.liste.itemSelectionChanged.connect(self._knoepfe_setzen)
        self.liste.setMaximumHeight(140)
        lay.addWidget(self.liste)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setTextFormat(Qt.RichText)
        self.hinweis.linkActivated.connect(self._kunde_markieren)
        lay.addWidget(self.hinweis)
        zeile = QHBoxLayout()
        self.knopf_oeffnen = QPushButton("Öffnen")
        self.knopf_oeffnen.setObjectName("primaer")
        self.knopf_oeffnen.clicked.connect(lambda: self.oeffnen(self.markierte()))
        self.knopf_zusammen = QPushButton("Zusammen öffnen")
        self.knopf_zusammen.setToolTip("Markierte Anfragen in einem Angebot (Stangen gemeinsam optimiert)")
        self.knopf_zusammen.clicked.connect(lambda: self.oeffnen(self.markierte(), zusammen=True))
        ordner = QPushButton("Ordner öffnen")
        ordner.clicked.connect(self.ordner_oeffnen)
        for b in (self.knopf_oeffnen, self.knopf_zusammen, ordner):
            zeile.addWidget(b)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.anfragen, self._stand = [], None
        self.timer = QTimer(self.karte)
        self.timer.timeout.connect(self.neu_laden)
        self.timer.start(ANFRAGEN_S * 1000)
        self.neu_laden()

    def ordner(self):
        return (self.f.db.einstellung(anfragen.EINSTELLUNG) or "").strip()

    def neu_laden(self, erzwingen=False):
        o = self.ordner()
        self.karte.setVisible(bool(o))
        if not o:
            self.anfragen = []
            return
        kunden = self.f.db.zeilen("kunden")
        neu = anfragen.suchen(o, kunden)
        st = anfragen.stand(neu)
        if st == self._stand and not erzwingen:
            return
        markiert = {a.schluessel for a in self.markierte()}
        self.anfragen, self._stand, self._kunden = neu, st, kunden
        self.liste.clear()
        for a in neu:
            kunde = anfragen.kunde_text(kunden, a.kunde) if a.kunde else ""
            it = QListWidgetItem(f"{kunde}  –  {a.text()}" if kunde else a.text())
            it.setData(Qt.ItemDataRole.UserRole, a.schluessel)
            if a.gesperrt:
                it.setForeground(self.liste.palette().placeholderText())
            self.liste.addItem(it)
            it.setSelected(a.schluessel in markiert)
        offen = [a for a in neu if not a.gesperrt]
        self.titel.setText(f"<b>{len(offen)} offene Anfrage{'n' if len(offen) != 1 else ''}</b> im Ordner {o}"
                           if neu else f"Keine neuen Anfragen im Ordner {o}")
        self.liste.setVisible(bool(neu))
        mehrere = anfragen.gleicher_kunde(neu)
        self.hinweis.setText("<br>".join(
            f"{len(v)} offene Anfragen von <b>{anfragen.kunde_text(kunden, k)}</b>: getrennt öffnen oder "
            f"<a href='{k}'>beide markieren</a> und „Zusammen öffnen“" for k, v in mehrere.items()))
        self.hinweis.setVisible(bool(mehrere))
        self._knoepfe_setzen()

    def _anfrage(self, it):
        schl = it.data(Qt.ItemDataRole.UserRole)
        return next((a for a in self.anfragen if a.schluessel == schl), None)

    def markierte(self):
        return [a for a in map(self._anfrage, self.liste.selectedItems()) if a is not None]

    def _knoepfe_setzen(self):
        n = len(self.markierte())
        self.knopf_oeffnen.setEnabled(n == 1 or (n == 0 and bool(self.anfragen)))
        self.knopf_zusammen.setEnabled(n > 1)

    def _kunde_markieren(self, kundennr):
        self.liste.clearSelection()
        for i in range(self.liste.count()):
            a = self._anfrage(self.liste.item(i))
            if a and str(a.kunde) == kundennr and not a.gesperrt:
                self.liste.item(i).setSelected(True)

    def ordner_oeffnen(self):
        if self.ordner():
            self.f.datei_oeffnen(self.ordner())

    def _formulare(self, gesperrt):
        """Anfrageformulare (PDF mit Text) lesen (Plan W6b): Anfragenummer ins Feld „Ihre Anfrage“ und in den
        Ordnernamen 'Kunde – Nummer' (daraus schlägt der Import den Kunden vor), Text für die Stückzahlen. Ändert
        gesperrt (neue Pfade). Ergebnis: weitere Werte für neu_aus_step (kopf, formular_text)."""
        from . import formular
        alle = [d for a in gesperrt for d in a.formulare]
        if not alle:
            return {}
        kunden = self.f.db.zeilen("kunden")
        eigene = [self.f.db.einstellung("briefkopf_1") or ""]
        texte = [formular.pdf_text(d) for d in alle if d.suffix.lower() == ".pdf"]
        text = "\n".join(t for t in texte if t.strip())
        if not text:
            return {}
        e = formular.auswerten(text, kunden, eigene=eigene)
        kunde = e["kunde"] or next((a.kunde for a in gesperrt if a.kunde), None)
        if e["nummer"] and len(gesperrt) == 1:
            try:
                gesperrt[0] = anfragen.umbenennen(gesperrt[0], anfragen.ordner_name(
                    anfragen.kunde_text(kunden, kunde) if kunde else "", e["nummer"]))
            except OSError:
                pass            # Ordner offen (Explorer): Name bleibt
        if kunde:
            for a in gesperrt:
                a.kunde = a.kunde or kunde
        weitere = dict(formular_text=text)
        if e["nummer"]:
            weitere["kopf"] = dict(kundenreferenz=e["nummer"])
        return weitere

    def oeffnen(self, auswahl, zusammen=False, kundennr=None):
        """Anfragen als ein neues Angebot aus STEP öffnen (ohne Auswahl: die älteste offene). Sperren, importieren,
        danach die Dateien in den Angebotsordner verschieben; bei Abbruch Sperre aufheben. kundennr: ohne Kundenwahl
        (Tests). Ergebnis: Angebotsseite oder None."""
        auswahl = [a for a in auswahl if a] or [a for a in self.anfragen if not a.gesperrt][:1]
        if not auswahl:
            return None
        if len(auswahl) > 1 and not zusammen:
            auswahl = auswahl[:1]
        kuerzel = self.f.db.einstellung("benutzer_kuerzel") or ""
        fremd = [a for a in auswahl if a.gesperrt and a.gesperrt != kuerzel]
        if fremd and not self.f.stumm and QMessageBox.question(
                self.f, "Anfrage öffnen", f"„{fremd[0].name}“ ist in Bearbeitung von {fremd[0].gesperrt}. "
                "Trotzdem öffnen?") != QMessageBox.Yes:
            return None
        gesperrt = []
        try:
            for a in auswahl:
                gesperrt.append(anfragen.sperren(a, self.ordner(), kuerzel))
        except OSError as e:
            for a in gesperrt:
                anfragen.freigeben(a)
            self.f.meldung(f"Anfrage lässt sich nicht öffnen: {e}", fehler=True)
            return None
        weitere = self._formulare(gesperrt)                         # kann den Ordner umbenennen
        dateien = [str(d) for a in gesperrt for d in a.step]
        seite = self.f.angebote.neu_aus_step(dateien, kundennr, **weitere)
        if seite is None:
            for a in gesperrt:
                anfragen.freigeben(a)
            self.neu_laden(erzwingen=True)
            return None
        try:
            ziel = self.f.angebot_ordner(seite.kopf)
        except OSError as e:
            self.f.meldung(f"Anfrage übernommen, Dateien nicht verschoben: {e}", fehler=True)
            self.neu_laden(erzwingen=True)
            return seite
        n, fehler = 0, []
        for a in gesperrt:
            k, f = anfragen.verschieben(a, ziel, angebotsordner.STEP_ORDNER)
            n, fehler = n + k, fehler + f
        self.f.meldung(f"Anfrage übernommen: {n} Datei(en) nach {ziel} verschoben"
                       + (f" (nicht verschoben: {'; '.join(fehler)})" if fehler else "."), fehler=bool(fehler))
        self.neu_laden(erzwingen=True)
        return seite
