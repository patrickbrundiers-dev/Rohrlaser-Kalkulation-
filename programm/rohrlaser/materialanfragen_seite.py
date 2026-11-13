"""Reiter „Materialanfragen“: Historie aller Materialanfragen an Lieferanten (Patrick 13.11.2026, Konzept
„Materialanfragen über Outlook“, Schritt 3).

Oben Zähler je Status (ein Klick filtert) und Suche/Lieferant, links die Liste (neueste zuerst), rechts die gewählte
Anfrage: Material, E-Mail-Text, Anhänge, interne Bemerkung und Verlauf mit Datum, Uhrzeit und wer. Knöpfe: Kalkulation
öffnen, Status setzen (Versendet, Angebot erhalten, Abgeschlossen), Erneut senden (Erinnerung mit Bezug, F5a),
„Gesendete in Outlook prüfen“ (Versendet aus den Gesendeten Elementen, nur lesen, F4a). Anfragen in Angeboten der
Kollegen sind nur zu sehen; ändern kann sie der Bearbeiter des Angebots. Gesendet wird nur in Outlook."""
import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QWidget)

from . import materialanfragen as mv
from .klartext import fehler_text

SPALTEN = ("Kennung", "Erstellt", "Angebot", "Kunde", "Lieferant", "Material", "Status", "Versendet", "Wer")
FARBE = {mv.ENTWURF: "#8A94A6", mv.VERSENDET: "#2F6FB3", mv.ERHALTEN: "#A66A00", mv.ABGESCHLOSSEN: "#2F7D4F"}
ALLE = "Alle"


class MaterialanfragenSeite(QWidget):
    titel = "Materialanfragen"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.eintraege, self.status = [], ALLE
        self.ausfuehren = None          # Tests: ersetzt den Outlook-Aufruf
        self.rueckfrage = None          # Tests: rueckfrage(titel, text) -> bool
        lay = QVBoxLayout(self)
        oben = QHBoxLayout()
        self.gruppe = QButtonGroup(self)
        self.zaehler = {}
        for st in (ALLE,) + mv.STATUS:
            b = QPushButton(st)
            b.setCheckable(True)
            b.setObjectName("anfragen_zaehler")
            b.setMinimumHeight(36)
            b.clicked.connect(lambda _=False, s=st: self.status_waehlen(s))
            self.gruppe.addButton(b)
            self.zaehler[st] = b
            oben.addWidget(b)
        self.zaehler[ALLE].setChecked(True)
        oben.addStretch(1)
        lay.addLayout(oben)
        filter_ = QHBoxLayout()
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Kennung, Angebot, Kunde, Lieferant, Betreff, Bemerkung …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(lambda _: self._fuellen())
        self.lieferant = QComboBox()
        self.lieferant.currentTextChanged.connect(lambda _: self._fuellen())
        self.pruefen_knopf = QPushButton("Gesendete in Outlook prüfen")
        self.pruefen_knopf.setToolTip("Liest die Gesendeten Elemente des klassischen Outlook (nur lesen): Anfragen, "
                                      "deren Kennung dort im Betreff steht, werden „Versendet“.")
        self.pruefen_knopf.clicked.connect(lambda: self.gesendet_pruefen())
        filter_.addWidget(self.suche, 2)
        filter_.addWidget(QLabel("Lieferant:"))
        filter_.addWidget(self.lieferant, 1)
        filter_.addWidget(self.pruefen_knopf)
        lay.addLayout(filter_)

        teiler = QSplitter(Qt.Horizontal)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        for i, b in enumerate((150, 112, 95, 130, 130, 0, 115, 112, 45)):
            if b:
                self.tabelle.setColumnWidth(i, b)
        self.tabelle.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.tabelle.itemSelectionChanged.connect(self._detail)
        self.tabelle.cellDoubleClicked.connect(lambda *_: self.kalkulation_oeffnen())
        teiler.addWidget(self.tabelle)
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        self.detail = QTextBrowser()
        rl.addWidget(self.detail, 1)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet("color: #7A5A00;")
        rl.addWidget(self.hinweis)
        k1, k2 = QHBoxLayout(), QHBoxLayout()
        self.oeffnen_knopf = QPushButton("Kalkulation öffnen")
        self.oeffnen_knopf.clicked.connect(lambda: self.kalkulation_oeffnen())
        self.erneut_knopf = QPushButton("Erneut senden (Erinnerung)")
        self.erneut_knopf.clicked.connect(lambda: self.erneut_senden())
        self.status_knoepfe = {}
        for st, text in ((mv.VERSENDET, "Ist gesendet"), (mv.ERHALTEN, "Angebot erhalten"),
                         (mv.ABGESCHLOSSEN, "Abschließen")):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, s=st: self.status_setzen(s))
            self.status_knoepfe[st] = b
            k2.addWidget(b)
        k1.addWidget(self.oeffnen_knopf)
        k1.addWidget(self.erneut_knopf)
        k1.addStretch(1)
        k2.addStretch(1)
        rl.addLayout(k1)
        rl.addLayout(k2)
        teiler.addWidget(rechts)
        teiler.setSizes([800, 480])
        lay.addWidget(teiler, 1)
        self.leer = QLabel("Noch keine Materialanfragen. Im Angebot: Ausgaben → Materialanfrage (E-Mail).")
        self.leer.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.leer)

    # ------------------------------------------------------------------ Daten
    def neu_laden(self):
        self.eintraege = mv.alle(self.db)
        alt = self.lieferant.currentText()
        self.lieferant.blockSignals(True)
        self.lieferant.clear()
        self.lieferant.addItems([ALLE] + sorted({e.get("lieferant") or "" for e in self.eintraege} - {""}))
        self.lieferant.setCurrentText(alt or ALLE)
        self.lieferant.blockSignals(False)
        for st, b in self.zaehler.items():
            n = len(self.eintraege) if st == ALLE else sum(1 for e in self.eintraege if e.get("status") == st)
            b.setText(f"{st}  {n}")
        self._fuellen()

    def status_waehlen(self, st):
        self.status = st
        self.zaehler[st].setChecked(True)
        self._fuellen()

    def zeigen_fuer(self, nummer):
        """Nur die Anfragen eines Angebots (Menü im Angebot)."""
        self.neu_laden()
        self.status_waehlen(ALLE)
        self.suche.setText(nummer or "")

    def sichtbar(self):
        lief = self.lieferant.currentText()
        return mv.filtern(self.eintraege, None if self.status == ALLE else self.status,
                          None if lief in ("", ALLE) else lief, self.suche.text())

    def _fuellen(self):
        zeilen = self.sichtbar()
        self.tabelle.setRowCount(len(zeilen))
        for r, e in enumerate(zeilen):
            werte = (e.get("kennung"), mv._zeit_text(e.get("erstellt")), e.get("nummer"), e.get("kunde"),
                     e.get("lieferant") or "–", "; ".join(e.get("zeilen") or ()), e.get("status")
                     + (f" ({e['erneut']}× erinnert)" if e.get("erneut") else ""),
                     mv._zeit_text(e.get("versendet")) if e.get("versendet") else "", e.get("wer"))
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w or ""))
                if c == 6:
                    it.setForeground(QColor(FARBE.get(e.get("status"), "#000000")))
                if c == 0:
                    it.setData(Qt.UserRole, r)
                self.tabelle.setItem(r, c, it)
        self._zeilen = zeilen
        self.leer.setVisible(not self.eintraege)
        if zeilen:
            self.tabelle.selectRow(0)
        self._detail()

    def gewaehlt(self):
        r = self.tabelle.currentRow()
        z = getattr(self, "_zeilen", [])
        return z[r] if 0 <= r < len(z) else None

    def _detail(self):
        e = self.gewaehlt()
        eigen = bool(e) and not e.get("fremd")
        for b in list(self.status_knoepfe.values()) + [self.erneut_knopf]:
            b.setEnabled(eigen and not getattr(self.db, "nur_lesen", False))
        self.oeffnen_knopf.setEnabled(bool(e))
        if e:
            self.status_knoepfe[e.get("status")].setEnabled(False) if e.get("status") in self.status_knoepfe else None
        self.hinweis.setText(f"Angebot von {e['fremd']}: nur ansehen, ändern kann es der Bearbeiter."
                             if e and e.get("fremd") else "")
        if not e:
            self.detail.setHtml("")
            return
        h = html.escape
        teile = [f"<h3>{h(e.get('kennung') or '')} · {h(e.get('status') or '')}</h3>",
                 f"<p><b>An:</b> {h(e.get('lieferant') or '–')} {h(e.get('an') or '')}<br>"
                 f"<b>Betreff:</b> {h(e.get('betreff') or '')}<br>"
                 f"<b>Angebot:</b> {h(e.get('nummer') or '')} – {h(e.get('kunde') or '')}<br>"
                 f"<b>Vorlage:</b> {h(e.get('vorlage') or '')}</p>"]
        if e.get("liefertermin") or e.get("gueltig"):
            teile.append(f"<p><b>Liefertermin:</b> {h(e.get('liefertermin') or '–')} · <b>Gültig bis:</b> "
                         f"{h(e.get('gueltig') or '–')}</p>")
        if e.get("intern"):
            teile.append(f"<p style='color:#7A5A00'><b>Interne Bemerkung:</b> {h(e['intern'])}</p>")
        teile.append("<p><b>Material:</b><br>" + "<br>".join(h(z) for z in e.get("zeilen") or ()) + "</p>")
        if e.get("anhaenge"):
            teile.append("<p><b>Anhänge:</b> " + ", ".join(h(a) for a in e["anhaenge"]) + "</p>")
        teile.append("<p><b>Verlauf:</b><br>" + "<br>".join(
            f"{h(mv._zeit_text(v.get('zeit')))} · {h(v.get('status') or '')}"
            + (f" · {h(v['wer'])}" if v.get("wer") else "") + (f" · {h(v['text'])}" if v.get("text") else "")
            for v in e.get("verlauf") or ()) + "</p>")
        teile.append("<p><b>E-Mail-Text:</b></p><pre style='white-space:pre-wrap'>" + h(e.get("text") or "")
                     + "</pre>")
        self.detail.setHtml("".join(teile))

    # ------------------------------------------------------------------ Aktionen
    def _wer(self):
        return self.db.einstellung("benutzer_kuerzel") or ""

    def _waehle(self, kennung):
        for r, e in enumerate(getattr(self, "_zeilen", [])):
            if e.get("kennung") == kennung:
                self.tabelle.selectRow(r)
                return

    def status_setzen(self, st):
        e = self.gewaehlt()
        if not e or e.get("fremd"):
            return False
        ok = mv.status_setzen(self.db, e["angebot_id"], e["kennung"], st, self._wer(), "von Hand")
        self.neu_laden()
        self._waehle(e["kennung"])
        self.f.meldung(f"{e['kennung']}: {st}.")
        return ok

    def kalkulation_oeffnen(self):
        e = self.gewaehlt()
        if e:
            return self.f.angebot_oeffnen(e["angebot_id"])
        return None

    def _frage(self, titel, text):
        if self.rueckfrage is not None:
            return bool(self.rueckfrage(titel, text))
        return QMessageBox.question(self, titel, text) == QMessageBox.Yes

    def erneut_senden(self):
        """Erinnerung an den Lieferanten in Outlook öffnen (mit Bezug auf die erste Anfrage, gleiche Kennung)."""
        from . import materialanfrage as ma
        e = self.gewaehlt()
        if not e or e.get("fremd"):
            return False
        wann = mv._zeit_text(e.get("versendet") or e.get("erstellt"))
        if not self._frage("Erneut senden", f"Erinnerung zu {e['kennung']} an {e.get('lieferant') or e.get('an')} "
                                            f"öffnen? Die Anfrage ist vom {wann} ({e.get('status')})."):
            return False
        einst = self.db.einstellungen()
        text = mv.erinnerung_text(e)
        ok, fehler = mv.VERSANDWEGE["outlook"](e.get("an") or "", mv.erinnerung_betreff(e), text,
                                               ausfuehren=self.ausfuehren, signatur_=ma.outlook_signatur(einst))
        if not ok:
            self.f.meldung(f"Outlook ließ sich nicht ansteuern ({fehler_text(fehler)}).", fehler=True)
            return False
        mv.erneut_vermerken(self.db, e["angebot_id"], e["kennung"], self._wer())
        self.neu_laden()
        self._waehle(e["kennung"])
        self.f.meldung(f"Erinnerung zu {e['kennung']} in Outlook geöffnet – bitte dort prüfen und senden.")
        return True

    def gesendet_pruefen(self):
        """Gesendete Elemente lesen und Entwürfe mit ihrer Kennung auf „Versendet“ setzen. Ergebnis: Anzahl oder
        None (Outlook nicht erreichbar)."""
        ok, daten = mv.gesendete(self.ausfuehren)
        if not ok:
            self.f.meldung(f"Gesendete Elemente nicht lesbar ({fehler_text(daten)}). Status bitte mit „Ist gesendet“ "
                           "setzen.", fehler=True)
            return None
        n = mv.gesendet_abgleichen(self.db, daten, self._wer())
        self.neu_laden()
        self.f.meldung(f"{n} Anfrage(n) als versendet erkannt." if n else "Keine neuen versendeten Anfragen gefunden.")
        return n
