"""Karte „Neue Anfragen“ auf der Startseite (Plan W6a): Anfragen aus dem Anfrage-Ordner (anfragen.py), Öffnen als
neues Angebot aus STEP, mehrere Anfragen eines Kunden auf Wunsch zusammen. Sichtbar nur mit Einstellung
„anfrage_ordner“; alle ANFRAGEN_S Sekunden wird nachgesehen. Anfrageformulare werden schon vorher im Hintergrund
gelesen (Scans mit Tesseract dauern einige Sekunden je Seite, Plan W6c); die Liste zeigt solange „liest Formular …“."""
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHBoxLayout, QInputDialog, QLabel, QListWidget, \
    QListWidgetItem, QMessageBox, QPushButton

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
        # Gemeinsamer Ordner (Patrick 28.10.2026): Anfrage einem Kollegen zuweisen, für alle sichtbar
        self.knopf_zuweisen = QPushButton("Zuweisen …")
        self.knopf_zuweisen.setToolTip("Markierte Anfrage einem Kollegen zuweisen (alle sehen „für MK“)")
        self.knopf_zuweisen.clicked.connect(lambda: self.zuweisen(self.markierte()[:1]))
        for b in (self.knopf_oeffnen, self.knopf_zusammen, self.knopf_zuweisen, ordner):
            zeile.addWidget(b)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.anfragen, self._stand = [], None
        self._gelesen, self._laeuft, self._pool = {}, {}, None     # Formulare: Schlüssel -> Ergebnis bzw. Future
        self._warten = QTimer(self.karte)
        self._warten.setInterval(1000)
        self._warten.timeout.connect(self._lesen_pruefen)
        self.timer = QTimer(self.karte)
        self.timer.timeout.connect(self.neu_laden)
        self.timer.start(ANFRAGEN_S * 1000)
        self.neu_laden()

    def ordner(self):
        o = anfragen.ordner(self.f.db)
        return str(o) if o else ""

    def neu_laden(self, erzwingen=False):
        o = self.ordner()
        self.karte.setVisible(bool(o))
        if not o:
            self.anfragen = []
            return
        kunden = self.f.db.zeilen("kunden")
        ich = self.f.db.einstellung("benutzer_kuerzel") or ""
        ohne = []
        try:            # Nachtrag zu einer schon übernommenen Anfrage erkennen (Anfrage-Nr. = Kundenreferenz)
            angebote = {r: (n, k) for r, n, k in self.f.db.con.execute(
                "SELECT kundenreferenz, nummer, kundennr FROM angebote WHERE COALESCE(kundenreferenz, '') <> '' "
                "ORDER BY id")}
        except Exception:
            angebote = {}
        try:            # intern weitergeleitete Mails: Absender des Kunden zum Zusammenfassen (31.10.2026)
            anfragen.EIGENE = anfragen.eigene_domains(self.f.db)
        except Exception:
            anfragen.EIGENE = set()
        neu = anfragen.suchen(o, kunden, ohne_step=ohne, angebote=angebote)
        st = (anfragen.stand(neu), tuple(ohne))
        if st == self._stand and not erzwingen:
            return
        markiert = {a.schluessel for a in self.markierte()}
        self.anfragen, self._stand, self._kunden = neu, st, kunden
        self.liste.clear()
        self._vorlesen(neu)
        for a in neu:
            kunde = anfragen.kunde_text(kunden, a.kunde) if a.kunde else ""
            liest = " · liest Formular …" if any(_schluessel(d) in self._laeuft for d in a.formulare) else ""
            it = QListWidgetItem((f"{kunde}  –  {a.text()}" if kunde else a.text()) + liest)
            it.setData(Qt.ItemDataRole.UserRole, a.schluessel)
            if a.gesperrt or (a.zugewiesen.get("an") and a.zugewiesen.get("an") != ich):
                it.setForeground(self.liste.palette().placeholderText())
            if a.zugewiesen.get("an") == ich and not a.gesperrt:
                schrift = it.font()
                schrift.setBold(True)       # mir zugewiesen
                it.setFont(schrift)
            self.liste.addItem(it)
            it.setSelected(a.schluessel in markiert)
        offen = [a for a in neu if not a.gesperrt]
        meine = [a for a in offen if ich and a.zugewiesen.get("an") == ich]
        self.titel.setText(f"<b>{len(offen)} offene Anfrage{'n' if len(offen) != 1 else ''}</b>"
                           + (f", davon <b>{len(meine)} für Sie</b>," if meine else "") + f" im Ordner {o}"
                           if neu else f"Keine neuen Anfragen im Ordner {o}")
        self.liste.setVisible(bool(neu))
        mehrere = anfragen.gleicher_kunde(neu)
        zeilen = [f"{len(v)} offene Anfragen von <b>{anfragen.kunde_text(kunden, k)}</b>: getrennt öffnen oder "
                  f"<a href='{k}'>beide markieren</a> und „Zusammen öffnen“" for k, v in mehrere.items()]
        nachtrag = [t for t in ohne if "(Nachtrag zu Angebot " in t]
        ohne = [t for t in ohne if t not in nachtrag]
        for t in nachtrag:  # Mail ohne STEP zu einer schon übernommenen Anfrage (Patrick 28.10.2026, F2 a)
            name, _, nr = t[:-1].partition(" (Nachtrag zu Angebot ")
            zeilen.append(f"Nachtrag zu Angebot <b>{nr}</b>: {name} – bitte im Angebot prüfen und die Mail von Hand "
                          "dazulegen")
        if ohne:        # nur Zeichnungen/Formulare: nichts automatisch daraus anlegen (Patrick 28.10.2026)
            zeilen.append(f"Ohne STEP (nicht in der Liste, z. B. nur Zeichnung als PDF): {', '.join(ohne[:4])}"
                          + (f" und {len(ohne) - 4} weitere" if len(ohne) > 4 else "")
                          + " – Teile von Hand anlegen oder die STEP dazulegen")
        self.hinweis.setText("<br>".join(zeilen))
        self.hinweis.setVisible(bool(zeilen))
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
        from . import teilen
        self.knopf_zuweisen.setVisible(teilen.aktiv(self.f.db))
        self.knopf_zuweisen.setEnabled(n == 1)

    def zuweisen(self, auswahl, an=None, notiz=""):
        """Anfrage einem Kollegen zuweisen (ohne an: Auswahl); „(niemand)“ hebt die Zuweisung auf. Ergebnis: True."""
        from . import teilen
        if not auswahl:
            return False
        a = auswahl[0]
        ich = teilen.kuerzel(self.f.db)
        if an is None:
            if self.f.stumm:
                return False
            namen = {k: f"{k} – {n}" if n else k for k, n in teilen.kollegen(self.f.db).items()}
            namen[ich] = f"{ich} (ich)"
            eintraege = list(namen.values()) + ["(niemand)"]
            wahl, gut = QInputDialog.getItem(self.f, "Anfrage zuweisen", f"„{a.name}“ zuweisen an:", eintraege, 0, False)
            if not gut:
                return False
            an = next((k for k, t in namen.items() if t == wahl), "")
            if an:
                notiz, gut = QInputDialog.getText(self.f, "Anfrage zuweisen", "Notiz (darf leer sein):")
                if not gut:
                    return False
        try:
            anfragen.zuweisen(a, self.ordner(), an, ich, notiz)
        except OSError as e:
            self.f.meldung(f"Anfrage lässt sich nicht zuweisen: {e}", fehler=True)
            return False
        self.f.meldung(f"Anfrage „{a.name}“ " + (f"an {an} zugewiesen." if an else "nicht mehr zugewiesen."))
        self.neu_laden(erzwingen=True)
        return True

    def _kunde_markieren(self, kundennr):
        self.liste.clearSelection()
        for i in range(self.liste.count()):
            a = self._anfrage(self.liste.item(i))
            if a and str(a.kunde) == kundennr and not a.gesperrt:
                self.liste.item(i).setSelected(True)

    def ordner_oeffnen(self):
        if self.ordner():
            self.f.datei_oeffnen(self.ordner())

    def _vorlesen(self, liste):
        """Formulare offener Anfragen im Hintergrund lesen (ein Formular nach dem anderen)."""
        from . import formular
        for a in liste:
            if a.gesperrt:
                continue
            for d in a.formulare:
                k = _schluessel(d)
                if k not in self._gelesen and k not in self._laeuft:
                    self._pool = self._pool or ThreadPoolExecutor(max_workers=1)
                    self._laeuft[k] = self._pool.submit(formular.datei_lesen, d, self.f.programmordner)
        if self._laeuft and not self._warten.isActive():
            self._warten.start()

    def _lesen_pruefen(self):
        fertig = [k for k, f in self._laeuft.items() if f.done()]
        for k in fertig:
            self._gelesen[k] = self._ergebnis(self._laeuft.pop(k))
        if not self._laeuft:
            self._warten.stop()
        if fertig:
            self.neu_laden(erzwingen=True)

    @staticmethod
    def _ergebnis(future):
        try:
            return future.result()
        except Exception:
            return None

    def formular_lesen(self, d):
        """Gelesenes Formular (dict text/ocr/unsicher) oder None; wartet auf das Lesen im Hintergrund bzw. liest jetzt
        (Sanduhr)."""
        from . import formular
        k = _schluessel(d)
        if self._gelesen.get(k):
            return self._gelesen[k]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if k in self._laeuft:
                self._gelesen[k] = self._ergebnis(self._laeuft.pop(k))
            if not self._gelesen.get(k):         # vorher verschoben (Sperre) oder noch nie gelesen
                self._gelesen[k] = formular.datei_lesen(d, self.f.programmordner)
        finally:
            QApplication.restoreOverrideCursor()
        return self._gelesen[k]

    def _formulare(self, gesperrt):
        """Anfrageformulare und E-Mails lesen (Plan W6b/W6c, Mail 28.10.2026, anfragen.werte): Anfragenummer ins Feld
        „Ihre Anfrage“ und in den Ordnernamen 'Kunde – Nummer', dazu Stückzahlen, Kunde, Lieferzeit, Bemerkung und
        Werkstoff aus der Mail. Ändert gesperrt (neue Pfade). Ergebnis: weitere Werte für neu_aus_step."""
        from . import mail
        gelesen = [g for g in (self.formular_lesen(d) for a in gesperrt for d in a.formulare) if g]
        mails = [m for m in (mail.lesen(d) for a in gesperrt for d in a.mails) if m]
        kunde, nummer, weitere = anfragen.werte(self.f.db, gelesen, mails,
                                                next((a.kunde for a in gesperrt if a.kunde), None))
        if nummer and len(gesperrt) == 1:
            try:
                gesperrt[0] = anfragen.umbenennen(gesperrt[0], anfragen.ordner_name(
                    anfragen.kunde_text(self.f.db.zeilen("kunden"), kunde) if kunde else "", nummer))
            except OSError:
                pass            # Ordner offen (Explorer): Name bleibt
        if kunde:
            for a in gesperrt:
                a.kunde = a.kunde or kunde
        return weitere

    def oeffnen(self, auswahl, zusammen=False, kundennr=None):
        """Anfragen als ein neues Angebot aus STEP öffnen (ohne Auswahl: die älteste offene). Sperren, Anhänge der
        Mails auspacken, importieren,
        danach die Dateien in den Angebotsordner verschieben; bei Abbruch Sperre aufheben. kundennr: ohne Kundenwahl
        (Tests). Ergebnis: Angebotsseite oder None."""
        ich = self.f.db.einstellung("benutzer_kuerzel") or ""
        frei = [a for a in self.anfragen if not a.gesperrt and a.zugewiesen.get("an") in (None, "", ich)]
        frei.sort(key=lambda a: a.zugewiesen.get("an") != ich)       # mir zugewiesene zuerst (sonst älteste)
        auswahl = [a for a in auswahl if a] or frei[:1]
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
        andere = [a for a in auswahl if a.zugewiesen.get("an") not in (None, "", kuerzel)]
        if andere and not fremd and not self.f.stumm and QMessageBox.question(
                self.f, "Anfrage öffnen", f"„{andere[0].name}“ ist {andere[0].zugewiesen['an']} zugewiesen. "
                "Trotzdem öffnen?") != QMessageBox.Yes:
            return None
        gesperrt = []
        try:
            for a in auswahl:
                gesperrt.append(anfragen.sperren(a, self.ordner(), kuerzel))
                gesperrt[-1] = anfragen.auspacken(gesperrt[-1])      # Fehler: Sperre wird unten aufgehoben
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


def _schluessel(d):
    """Formular wiedererkennen, auch nach dem Verschieben in einen Unterordner: Name, Größe, Änderungszeit."""
    try:
        st = d.stat()
        return d.name, st.st_size, st.st_mtime_ns
    except OSError:
        return d.name, None, None
