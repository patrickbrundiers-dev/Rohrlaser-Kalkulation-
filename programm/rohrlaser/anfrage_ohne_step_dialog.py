"""Anfrage ohne STEP (Patrick 17.11.2026, F2-F5 a; Logik in anfrage_ohne_step.py): Angebot ohne Positionen anlegen,
Fenster „Dateien der Anfrage“ und die gelbe Leiste im Angebot (Mixin für AngebotSeite)."""
from pathlib import Path

from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from . import anfrage_ohne_step as aos
from .klartext import fehler_text


# ------------------------------------------------------------------ Angebot ohne STEP anlegen (F2 a)
class OhneStepDialog(QDialog):
    """Kurzer Prüfdialog statt des STEP-Prüfdialogs: Kunde, Anfrage-Nr., was aus Mail und Formular erkannt ist und
    welche Dateien dabei sind. Positionen entstehen hier nicht."""

    def __init__(self, eltern, db, kundennr, kopf, hinweis, dateien):
        super().__init__(eltern)
        self.setWindowTitle("Neues Angebot aus Anfrage ohne STEP")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        text = QLabel("Die Anfrage hat keine STEP-Datei. Das Angebot wird mit den Angaben aus der Mail angelegt; die "
                      "Positionen legen Sie danach selbst an – von Hand oder im Angebot mit „Dateien der Anfrage …“ "
                      "aus einer PDF-Zeichnung bzw. DXF.")
        text.setWordWrap(True)
        lay.addWidget(text)
        form = QFormLayout()
        self.kunde = QComboBox()
        self.kunde.setEditable(True)
        self.kunde.setInsertPolicy(QComboBox.NoInsert)
        self.kunde.addItem("(ohne Kunde)", "")
        for k in db.zeilen("kunden"):
            if k.get("kundennr"):
                self.kunde.addItem(f"{k['kundennr']} – {k.get('name') or ''}", str(k["kundennr"]))
        i = self.kunde.findData(str(kundennr or ""))
        self.kunde.setCurrentIndex(max(i, 0))
        form.addRow("Kunde", self.kunde)
        self.referenz = QLineEdit(str((kopf or {}).get("kundenreferenz") or ""))
        self.referenz.setPlaceholderText("Anfrage-Nr. des Kunden")
        form.addRow("Ihre Anfrage", self.referenz)
        lay.addLayout(form)
        if hinweis:
            h = QLabel("<b>Aus E-Mail/Formular:</b><br>" + "<br>".join(_esc(z) for z in hinweis))
            h.setWordWrap(True)
            lay.addWidget(h)
        d = QLabel("<b>Dateien der Anfrage:</b> " + (", ".join(_esc(Path(p).name) for p in dateien)
                                                     if dateien else "keine (Mail ohne Anhang)"))
        d.setWordWrap(True)
        lay.addWidget(d)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Angebot anlegen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def werte(self):
        """(Kundennummer oder '', Anfrage-Nr.)"""
        nr = self.kunde.currentData()
        if self.kunde.currentText() != self.kunde.itemText(self.kunde.currentIndex()):
            nr = self.kunde.currentText().split("–")[0].strip()
        return str(nr or ""), self.referenz.text().strip()


def _esc(t):
    import html
    return html.escape(str(t))


def neues_angebot(fenster, kundennr=None, kopf=None, vorschlag=None, neuer_kunde=None, hinweis=None,
                  werkstoff_text=None, dateien=(), dialog=None, **_):
    """Angebot ohne Positionen aus einer Anfrage ohne STEP (F2 a). Kunde: kundennr (Tests), sonst Vorschlag aus der
    Mail, sonst ein neu angelegter Kunde („Kunde prüfen“, bei Abbruch wieder entfernt). kopf: Kopffelder aus Mail und
    Formular (Anfrage-Nr., Wunschtermin, Bemerkung). dateien: Zeichnungen usw. für die Leiste. dialog(d) bedient den
    Prüfdialog statt exec (Tests); ohne Rückfragen (stumm) entfällt er. Ergebnis: Angebotsseite oder None."""
    from . import mail
    from .step_neu import kunde_anlegen
    db = fenster.db
    if db.nur_lesen:
        fenster.meldung("Lesemodus: es lassen sich keine Angebote anlegen.", fehler=True)
        return None
    hinweis = list(hinweis or [])
    if werkstoff_text:
        try:
            w = mail.werkstoff(werkstoff_text, db.zeilen("werkstoffe"))
        except Exception:       # noqa: BLE001
            w = (None, None, ())
        if w[1]:
            hinweis.append(f"Werkstoff laut Mail: {w[1]}" + ("" if w[0] else " (nicht eindeutig)")
                           + " – beim Anlegen der Positionen wählen")
    neu_angelegt = None
    if kundennr is None and not vorschlag and neuer_kunde:
        vorschlag, neu_angelegt = kunde_anlegen(db, neuer_kunde)
    kopf = dict(kopf or {})
    if kundennr is None:
        kundennr = vorschlag or ""
        if not fenster.stumm or dialog:
            d = OhneStepDialog(fenster, db, kundennr, kopf, hinweis, dateien)
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                if neu_angelegt and not db.con.execute("SELECT 1 FROM angebote WHERE kundennr=?",
                                                       (vorschlag,)).fetchone():
                    db.loeschen("kunden", [neu_angelegt])       # eben angelegt: mit dem Abbruch wieder weg
                return None
            kundennr, ref = d.werte()
            kopf["kundenreferenz"] = ref or None
    i = db.angebot_neu(dict(kopf, kundennr=kundennr or None))
    aos.merken(db, i, dateien, hinweis)
    fenster.angebote.neu_laden()
    seite = fenster.angebot_oeffnen(i)
    if neu_angelegt:
        fenster.meldung(f"Neuer Kunde {vorschlag} – {neuer_kunde.get('name')} angelegt (Bemerkung „Kunde prüfen“).")
    return seite


# ------------------------------------------------------------------ Dateien der Anfrage (F3 a)
class DateienDialog(QDialog):
    """Dateien der Anfrage im Angebotsordner: Ansehen, Als Position übernehmen (PDF/Scan: Rohr-Editor aus der
    Zeichnung, DXF: DXF-Import). Nichts geschieht von selbst."""

    def __init__(self, seite):
        super().__init__(seite)
        self.seite = seite
        self.setWindowTitle("Dateien der Anfrage")
        self.resize(720, 360)
        lay = QVBoxLayout(self)
        t = QLabel("Zeichnungen und Dateien aus der Anfrage. „Als Position übernehmen“ öffnet bei einer PDF-Zeichnung "
                   "bzw. einem Scan den Rohr-Editor mit Profil, Länge, Werkstoff und Stückzahl aus dem Schriftfeld "
                   "(bitte prüfen), bei einer DXF den DXF-Import (Bleche bzw. Rohr aus Ansichten).")
        t.setWordWrap(True)
        lay.addWidget(t)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        lay.addWidget(self.hinweis)
        self.tabelle = QTableWidget(0, 3)
        self.tabelle.setHorizontalHeaderLabels(["Datei", "Art", "Stand"])
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.itemSelectionChanged.connect(self._knoepfe)
        self.tabelle.itemDoubleClicked.connect(lambda _it: self.ansehen())
        lay.addWidget(self.tabelle, 1)
        zeile = QHBoxLayout()
        self.k_ansehen = QPushButton("Ansehen")
        self.k_ansehen.clicked.connect(lambda: self.ansehen())
        self.k_position = QPushButton("Als Position übernehmen")
        self.k_position.setObjectName("primaer")
        self.k_position.clicked.connect(lambda: self.uebernehmen())
        k_ordner = QPushButton("Ordner öffnen")
        k_ordner.clicked.connect(lambda: self.seite.f.angebot_ordner_oeffnen(self.seite.kopf))
        for b in (self.k_ansehen, self.k_position, k_ordner):
            zeile.addWidget(b)
        zeile.addStretch(1)
        schliessen = QPushButton("Schließen")
        schliessen.clicked.connect(self.accept)
        zeile.addWidget(schliessen)
        lay.addLayout(zeile)
        self.fuellen()

    def fuellen(self):
        st = aos.stand(self.seite.db, self.seite.id) or {}
        self.eintraege = list(st.get("dateien") or [])
        self.hinweis.setText("<br>".join(_esc(z) for z in st.get("hinweis") or ()))
        self.hinweis.setVisible(bool(st.get("hinweis")))
        self.tabelle.setRowCount(len(self.eintraege))
        for r, e in enumerate(self.eintraege):
            stand = "als Position übernommen" if e.get("uebernommen") else (
                "nur ansehen" if e["art"] not in aos.UEBERNEHMBAR else "")
            if self.seite.anfrage_datei(e["name"]) is None:
                stand = "fehlt im Angebotsordner"
            for c, w in enumerate((e["name"], aos.ART_TEXT.get(e["art"], e["art"]), stand)):
                self.tabelle.setItem(r, c, QTableWidgetItem(w))
        if self.eintraege:
            self.tabelle.selectRow(0)
        self._knoepfe()

    def gewaehlt(self):
        r = self.tabelle.currentRow()
        return self.eintraege[r] if 0 <= r < len(self.eintraege) else None

    def _knoepfe(self):
        e = self.gewaehlt()
        da = e is not None and self.seite.anfrage_datei(e["name"]) is not None
        self.k_ansehen.setEnabled(da)
        self.k_position.setEnabled(da and e["art"] in aos.UEBERNEHMBAR and not self.seite.fremd())

    def ansehen(self):
        e = self.gewaehlt()
        p = self.seite.anfrage_datei(e["name"]) if e else None
        if p is not None:
            self.seite.f.datei_oeffnen(str(p))
        return p

    def uebernehmen(self, **weitere):
        e = self.gewaehlt()
        if e is None:
            return 0
        n = self.seite.anfrage_datei_uebernehmen(e["name"], **weitere)
        self.fuellen()
        return n


# ------------------------------------------------------------------ Leiste im Angebot (F3-F5 a)
class OhneStepMixin:
    """Für AngebotSeite: gelbe Leiste „Angebot aus einer Anfrage ohne STEP“ mit Dateien, STEP anfragen,
    STEP einlesen (nachgereicht) und Ausblenden."""

    def _ohne_leiste_bauen(self, stil_text):
        self.ohne_leiste = QFrame()
        self.ohne_leiste.setStyleSheet(stil_text)
        ol = QHBoxLayout(self.ohne_leiste)
        ol.setContentsMargins(10, 6, 10, 6)
        self.ohne_text = QLabel()
        self.ohne_text.setWordWrap(True)
        ol.addWidget(self.ohne_text, 1)
        self.ohne_k_einlesen = QPushButton("STEP einlesen")
        self.ohne_k_einlesen.setObjectName("primaer")
        self.ohne_k_einlesen.clicked.connect(lambda: self.nachgereichte_step_einlesen())
        self.ohne_k_dateien = QPushButton("Dateien der Anfrage …")
        self.ohne_k_dateien.clicked.connect(lambda: self.anfrage_dateien_zeigen())
        self.ohne_k_step = QPushButton("STEP anfragen …")
        self.ohne_k_step.setToolTip("Rückfrage an den Kunden als Antwort auf seine Mail (Outlook, nie automatisch "
                                    "gesendet); die Anfrage wartet dann auf ihn")
        self.ohne_k_step.clicked.connect(lambda: self.step_anfragen())
        self.ohne_k_weg = QPushButton("Ausblenden")
        self.ohne_k_weg.clicked.connect(lambda: self.ohne_ausblenden())
        for b in (self.ohne_k_einlesen, self.ohne_k_dateien, self.ohne_k_step, self.ohne_k_weg):
            ol.addWidget(b)
        self.ohne_leiste.hide()
        return self.ohne_leiste

    def anfrage_ohne_step_melden(self):
        """Leiste zeigen oder verbergen. Ergebnis: Text der Leiste ('' = keine)."""
        try:
            st = aos.stand(self.db, self.id)
            nach = aos.nachgereicht(self.db, self.id) if st is not None and not self.fremd() else []
        except Exception:       # noqa: BLE001 – Hilfe, nie ein Fehler beim Öffnen
            st, nach = None, []
        text = aos.leiste_text(st, nach)
        self._ohne_nach = nach
        if not hasattr(self, "ohne_leiste"):
            return text
        self.ohne_text.setText(text)
        self.ohne_k_einlesen.setVisible(bool(nach))
        self.ohne_k_dateien.setVisible(bool(st and st.get("dateien")))
        from . import anfragen_akten as ak
        self.ohne_k_step.setVisible(not nach and bool(ak.akten_zum_angebot(self.db, self.id)))
        self.ohne_leiste.setVisible(bool(text))
        return text

    def anfrage_datei(self, name):
        """Pfad einer Datei der Anfrage im Angebotsordner oder None."""
        try:
            ordner = self.f.angebot_ordner(self.kopf)
        except OSError:
            return None
        return aos.pfad(ordner, name)

    def anfrage_dateien_zeigen(self, dialog=None):
        d = DateienDialog(self)
        if dialog:
            dialog(d)
        else:
            d.exec()
        self.anfrage_ohne_step_melden()
        return d

    def anfrage_datei_uebernehmen(self, name, **weitere):
        """Eine Datei der Anfrage als Position: PDF/Scan -> rohr_aus_pdf, DXF -> blech_aus_dxf; weitere gehen an diese
        (Tests). Ergebnis: Anzahl angelegter Positionen."""
        p = self.anfrage_datei(name)
        if p is None or self.fremd():
            return 0
        if p.suffix.lower() == ".dxf":
            n = self.blech_aus_dxf([str(p)], **weitere)
        else:
            n = self.rohr_aus_pdf([str(p)], **weitere)
        if n:
            aos.uebernommen(self.db, self.id, name)
        self.anfrage_ohne_step_melden()
        return n

    def step_anfragen(self, text=None):
        """F4 a: Rückfrage „Bitte STEP senden“ zur verknüpften Anfrage (Seite Anfragen). Ergebnis: Akte oder None."""
        from . import anfragen_akten as ak
        nummern = ak.akten_zum_angebot(self.db, self.id)
        s = getattr(self.f, "anfragen_seite", None)
        if not nummern or s is None:
            self.f.meldung("Zu diesem Angebot gibt es keine Anfrage in der Anfragenverwaltung: die STEP bitte per "
                           "E-Mail anfragen.", fehler=True)
            return None
        s.neu_laden()
        s.waehlen(nummern[0])
        erg = s.rueckfrage(text)
        self.anfrage_ohne_step_melden()
        return erg

    def nachgereichte_step_einlesen(self, dateien=None, **weitere):
        """F4 a: nachgereichte STEP-Dateien aus der Akte in dieses Angebot (STEP-Import mit Prüfdialog) und in den
        Angebotsordner (STEP). Ergebnis: Ergebnis des Imports oder None."""
        import shutil
        from . import angebotsordner
        dateien = [Path(p) for p in (dateien or aos.nachgereicht(self.db, self.id))]
        if not dateien or self.fremd():
            return None
        try:
            ziel = Path(self.f.angebot_ordner(self.kopf)) / angebotsordner.STEP_ORDNER
            ziel.mkdir(parents=True, exist_ok=True)
            kopien = []
            for p in dateien:
                z = ziel / p.name
                if not z.exists():
                    shutil.copy2(p, z)
                kopien.append(z)
        except OSError as e:
            self.f.meldung(f"STEP-Dateien nicht in den Angebotsordner kopierbar: {fehler_text(e)}", fehler=True)
            kopien = dateien
        erg = self.step_importieren([str(p) for p in kopien], **weitere)
        if erg is not None:
            aos.eingelesen(self.db, self.id, dateien)
        self.anfrage_ohne_step_melden()
        return erg

    def ohne_ausblenden(self):
        aos.ausblenden(self.db, self.id)
        return self.anfrage_ohne_step_melden()
