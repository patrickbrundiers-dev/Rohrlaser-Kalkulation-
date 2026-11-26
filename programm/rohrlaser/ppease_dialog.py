"""Fenster „Dokumentenablage / PPEASE-Verknüpfung“ (Patrick 19.11.2026, ppease_ablage.py).

Vier Bereiche: 1 Angebotszuordnung (PPEASE-Nummer, Kunde, Bezeichnung, Speicherpfad, Ordnerstatus), 2 Dokumente
(Liste mit Haken, Typ, Größe, Quelle, Zielordner, Status; Vorschau; Ziehen & Ablegen), 3 Speicherübersicht (schon im
Ordner, neu, geändert, Fortschritt), 4 Aktionen (Ordner öffnen, Dokumente speichern, weitere hinzufügen, Speicherpfad
ändern, Ablage prüfen). Der Benutzer gibt nur die Nummer ein, hakt an und klickt „Dokumente speichern“."""
import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox, QProgressBar, QPushButton,
                               QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import ppease_ablage as pa
from . import protokoll, stil
from .klartext import fehler_text

SP_DOK, SP_TYP, SP_GROESSE, SP_QUELLE, SP_ZIEL, SP_STATUS, SP_AKTION = range(7)
VERSCHIEBEN = "leiste_ppease_verschieben"     # je Arbeitsplatz, nie abgeglichen (leiste_*); Vorgabe an
STATUS_FARBE = {pa.NEU: stil.AKZENT, pa.GLEICH: stil.GRUEN, pa.SCHON: stil.GRUEN, pa.GEAENDERT: stil.ORANGE}


class PpeaseDialog(QDialog):
    """db: Datenbank; kopf: Angebot (oder None: nur hinzugefügte Dateien); angebotsordner: Ordner des Angebots in
    der eigenen Ablage; anfrage_dateien: Dateien der Kundenanfrage; oeffnen(pfad): Datei/Ordner öffnen;
    kuerzel: Mitarbeiter fürs Protokoll. fragen(titel, text) -> bool und melden(titel, text) lassen sich in Tests
    ersetzen."""

    def __init__(self, parent, db, kopf=None, angebotsordner=None, anfrage_dateien=(), oeffnen=None, kuerzel="ICH",
                 stumm=False, akte_erstellen=None, nach_verschieben=None):
        super().__init__(parent)
        self.nach_verschieben = nach_verschieben    # Rückruf [(alt, neu)] nach dem Verschieben (Anfrage-Akten)
        self.db, self.kopf, self.kuerzel, self.stumm = db, dict(kopf or {}), kuerzel, stumm
        self.oeffnen_fn, self.akte_erstellen = oeffnen, akte_erstellen
        self.angebotsordner = Path(angebotsordner) if angebotsordner else None
        self.anfrage_dateien = list(anfrage_dateien or ())
        self.v = pa.vorgaben(db)
        self.dokumente, self.status, self.aktionen = [], {}, {}
        self.ordner, self.vorhanden = None, False
        self.pfad_ok = None
        self.letzter_bericht = None
        self.fragen = self._fragen
        self.melden = self._melden
        nr = self.kopf.get("nummer") or ""
        self.setWindowTitle("Dokumentenablage / PPEASE-Verknüpfung" + (f" – Angebot {nr}" if nr else ""))
        self.setAcceptDrops(True)
        self._bauen()
        g = pa.gemerkt(db, self.kopf.get("id"))
        self.nummer.setText(g.get("nummer") or "")
        self.kunde.setText(g.get("kunde") or self.kopf.get("kunde") or "")
        self.bezeichnung.setText(g.get("bezeichnung") or self.kopf.get("kundenreferenz") or "")
        self.dokumente = pa.dokumente_sammeln(self.angebotsordner, self.anfrage_dateien)
        self._liste_fuellen()
        self.pfad_pruefen(still=True)
        self.aktualisieren()
        self.resize(1180, 820)

    # ------------------------------------------------------------------ Aufbau
    def _bauen(self):
        lay = QVBoxLayout(self)
        # Bereich 1
        b1 = QGroupBox("1  Angebotszuordnung")
        f = QFormLayout(b1)
        zeile = QHBoxLayout()
        self.nummer = QLineEdit()
        self.nummer.setPlaceholderText("z. B. 2026-44327")
        self.nummer.setToolTip("Angebotsnummer aus PPEASE. Der Ordner wird danach benannt bzw. wiedergefunden.")
        self.nummer.setMaximumWidth(220)
        self.nummer_info = QLabel()
        self.nummer_info.setWordWrap(True)
        zeile.addWidget(self.nummer)
        zeile.addWidget(self.nummer_info, 1)
        f.addRow("Angebotsnummer PPEASE", zeile)
        self.kunde = QLineEdit()
        self.kunde.setPlaceholderText("optional, für den Ordnernamen (Einstellungen → Ablage und Teilen)")
        f.addRow("Kundenname", self.kunde)
        self.bezeichnung = QLineEdit()
        self.bezeichnung.setPlaceholderText("optional")
        f.addRow("Angebotsbezeichnung", self.bezeichnung)
        zeile = QHBoxLayout()
        self.pfad = QLabel()
        self.pfad.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.pfad.setWordWrap(True)
        self.pfad_knopf = QPushButton("Ändern …")
        self.pfad_knopf.clicked.connect(lambda: self.pfad_aendern())
        zeile.addWidget(self.pfad, 1)
        zeile.addWidget(self.pfad_knopf)
        f.addRow("Speicherpfad", zeile)
        self.ordner_info = QLabel()
        self.ordner_info.setWordWrap(True)
        self.ordner_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addRow("Ordnerstatus", self.ordner_info)
        lay.addWidget(b1)
        self._takt = QTimer(self)
        self._takt.setSingleShot(True)
        self._takt.setInterval(350)
        self._takt.timeout.connect(self.aktualisieren)
        for w in (self.nummer, self.kunde, self.bezeichnung):
            w.textChanged.connect(lambda *_: self._takt.start())
        # Bereich 2 und 3 nebeneinander/untereinander
        teiler = QSplitter(Qt.Vertical)
        b2 = QGroupBox("2  Dokumentenauswahl")
        l2 = QVBoxLayout(b2)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        l2.addWidget(self.hinweis)
        innen = QSplitter(Qt.Horizontal)
        self.liste = QTreeWidget()
        self.liste.setRootIsDecorated(False)
        self.liste.setHeaderLabels(["Dokument", "Typ", "Größe", "Quelle", "Zielordner", "Status",
                                    "Bei vorhandener Datei"])
        self.liste.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.liste.header().setSectionResizeMode(SP_DOK, QHeaderView.Stretch)
        for s in (SP_TYP, SP_GROESSE, SP_QUELLE, SP_STATUS):
            self.liste.header().setSectionResizeMode(s, QHeaderView.ResizeToContents)
        self.liste.setColumnWidth(SP_ZIEL, 190)
        self.liste.setColumnWidth(SP_AKTION, 210)
        self.liste.itemChanged.connect(self._haken_geaendert)
        self.liste.currentItemChanged.connect(lambda *_: self._vorschau())
        self.liste.itemDoubleClicked.connect(lambda *_: self.vorschau_gross())
        innen.addWidget(self.liste)
        rechts = QWidget()
        lr = QVBoxLayout(rechts)
        lr.setContentsMargins(0, 0, 0, 0)
        self.vorschau = QLabel("Keine Datei gewählt")
        self.vorschau.setAlignment(Qt.AlignCenter)
        self.vorschau.setMinimumSize(220, 220)
        self.vorschau.setWordWrap(True)
        self.vorschau.setStyleSheet(f"border: 1px solid {stil.LINIE}; color: {stil.TEXT_GRAU};")
        lr.addWidget(self.vorschau, 1)
        self.gross_knopf = QPushButton("Vorschau öffnen")
        self.gross_knopf.setToolTip("Datei in der Vorschau des Programms zeigen (PDF, Bilder, STEP, DXF, Excel …)")
        self.gross_knopf.clicked.connect(lambda: self.vorschau_gross())
        lr.addWidget(self.gross_knopf)
        innen.addWidget(rechts)
        innen.setStretchFactor(0, 4)
        innen.setStretchFactor(1, 1)
        l2.addWidget(innen, 1)
        zeile = QHBoxLayout()
        for text, ziel in (("Alle auswählen", lambda: self.alle(True)), ("Keine", lambda: self.alle(False)),
                           ("Nur neue und geänderte", self.nur_neue)):
            k = QPushButton(text)
            k.clicked.connect(lambda _=False, z=ziel: z())
            zeile.addWidget(k)
        zeile.addStretch(1)
        self.zahl = QLabel()
        zeile.addWidget(self.zahl)
        l2.addLayout(zeile)
        teiler.addWidget(b2)
        b3 = QGroupBox("3  Speicherübersicht")
        l3 = QVBoxLayout(b3)
        self.uebersicht = QLabel()
        self.uebersicht.setWordWrap(True)
        l3.addWidget(self.uebersicht)
        self.vorhanden_liste = QListWidget()
        self.vorhanden_liste.setMinimumHeight(70)
        l3.addWidget(self.vorhanden_liste, 1)
        self.fortschritt = QProgressBar()
        self.fortschritt.setTextVisible(True)
        self.fortschritt.setValue(0)
        self.fortschritt.setFormat("bereit")
        l3.addWidget(self.fortschritt)
        self.ergebnis = QLabel()
        self.ergebnis.setWordWrap(True)
        l3.addWidget(self.ergebnis)
        teiler.addWidget(b3)
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 1)
        lay.addWidget(teiler, 1)
        # Bereich 4
        b4 = QGroupBox("4  Aktionen")
        l4 = QHBoxLayout(b4)
        self.knopf_ordner = QPushButton("Ordner öffnen")
        self.knopf_dazu = QPushButton("Weitere Dokumente hinzufügen …")
        self.knopf_pfad = QPushButton("Speicherpfad ändern …")
        self.knopf_pruefen = QPushButton("Ablage prüfen")
        self.knopf_speichern = QPushButton("Dokumente speichern")
        self.knopf_speichern.setObjectName("primaer")
        self.knopf_schliessen = QPushButton("Schließen")
        self.knopf_ordner.clicked.connect(lambda: self.ordner_oeffnen())
        self.knopf_dazu.clicked.connect(lambda: self.hinzufuegen())
        self.knopf_pfad.clicked.connect(lambda: self.pfad_aendern())
        self.knopf_pruefen.clicked.connect(lambda: self.ablage_pruefen())
        self.knopf_speichern.clicked.connect(lambda: self.speichern())
        self.knopf_schliessen.clicked.connect(self.reject)
        self.knopf_dazu.setToolTip("Dateien aus anderen Ordnern wählen; Dateien lassen sich auch in dieses Fenster "
                                   "ziehen.")
        self.knopf_pruefen.setToolTip("Speicherort erreichbar und beschreibbar? Reste eines abgebrochenen "
                                      "Speichervorgangs entfernen.")
        for k in (self.knopf_ordner, self.knopf_dazu, self.knopf_pfad, self.knopf_pruefen):
            l4.addWidget(k)
        # Verschieben statt kopieren (Patrick 26.11.2026 „keine doppelten Daten“), gemerkt je Arbeitsplatz
        self.verschieben = QCheckBox("Verschieben (keine doppelten Daten)")
        self.verschieben.setToolTip(
            "An: Mail mit Anhängen, Kundendateien und Dokumente der Angebotsakte kommen in den PPEASE-Angebotsordner; "
            "das Original wird erst nach geprüfter Kopie entfernt. Programmdateien (JSON, Zwischenspeicher) bleiben "
            "immer, wo sie sind. Das Programm findet die Dateien über die PPEASE-Nummer wieder.\nAus: nur kopieren.")
        try:
            self.verschieben.setChecked(self.db.einstellung(VERSCHIEBEN) is not False)
        except Exception:       # noqa: BLE001
            self.verschieben.setChecked(True)
        if getattr(self.db, "nur_lesen", False):
            # Lesemodus: der neue Ort ließe sich nicht am Angebot bzw. in der Anfrage merken -> nur kopieren
            self.verschieben.setChecked(False)
            self.verschieben.setEnabled(False)
            self.verschieben.setToolTip("Im Lesemodus wird nur kopiert: der neue Ort ließe sich nicht merken.")
        self.verschieben.toggled.connect(self._verschieben_umgeschaltet)
        l4.addWidget(self.verschieben)
        if self.akte_erstellen:
            self.knopf_akte = QPushButton("Angebotsdokument erstellen …")
            self.knopf_akte.setToolTip("Angebotsakte (Kundenangebot, interne Kalkulation, Schnittschema) erzeugen; "
                                       "sie erscheint danach in der Liste.")
            self.knopf_akte.clicked.connect(lambda: self._akte())
            l4.addWidget(self.knopf_akte)
        l4.addStretch(1)
        l4.addWidget(self.knopf_schliessen)
        l4.addWidget(self.knopf_speichern)
        lay.addWidget(b4)
        self._knopf_text()

    def _knopf_text(self):
        self.knopf_speichern.setText("Dokumente verschieben" if self.verschieben.isChecked() else "Dokumente speichern")

    def _verschieben_umgeschaltet(self, an):
        self._knopf_text()
        try:
            if not getattr(self.db, "nur_lesen", False):
                self.db.einstellung_setzen(VERSCHIEBEN, bool(an))
        except Exception as e:  # noqa: BLE001 – nur Merker
            protokoll.warnung(f"PPEASE-Ablage: Merker Verschieben nicht gespeichert ({type(e).__name__}: {e})")

    # ------------------------------------------------------------------ Liste
    def _ziel_auswahl(self, d):
        c = QComboBox()
        for art, name in pa.alle_kategorien(self.v):
            c.addItem(name, art)
        i = c.findData(d.kategorie)
        c.setCurrentIndex(i if i >= 0 else c.count() - 1)
        c.currentIndexChanged.connect(lambda _=0, d=d, c=c: self._ziel_geaendert(d, c))
        return c

    def _liste_fuellen(self):
        self.liste.blockSignals(True)
        self.liste.clear()
        for d in self.dokumente:
            e = QTreeWidgetItem([d.name, d.typ, pa.groesse_text(d.groesse),
                                 d.quelle + (" · Programmdatei, bleibt" if d.intern else ""), "", "", ""])
            e.setFlags(e.flags() | Qt.ItemIsUserCheckable)
            e.setCheckState(SP_DOK, Qt.Checked if d.gewaehlt else Qt.Unchecked)
            e.setToolTip(SP_DOK, str(d.pfad))
            e.setTextAlignment(SP_GROESSE, Qt.AlignRight | Qt.AlignVCenter)
            e.setData(SP_DOK, Qt.UserRole, id(d))
            self.liste.addTopLevelItem(e)
            self.liste.setItemWidget(e, SP_ZIEL, self._ziel_auswahl(d))
        self.liste.blockSignals(False)
        if self.liste.topLevelItemCount():
            self.liste.setCurrentItem(self.liste.topLevelItem(0))
        self._hinweis_stellen()

    def _hinweis_stellen(self):
        t = []
        if self.angebotsordner is None:
            t.append("Kein Angebot geöffnet: nur hinzugefügte Dateien (Knopf unten oder in das Fenster ziehen).")
        elif not any(d.quelle == pa.Q_AKTE for d in self.dokumente):
            t.append("Für dieses Angebot gibt es noch keine Angebotsakte (Angebots-PDF, Kalkulation, Schnittschema)."
                     + (" „Angebotsdokument erstellen …“ erzeugt sie." if self.akte_erstellen else ""))
        if not self.dokumente:
            t.append("Noch keine Dokumente.")
        self.hinweis.setText(" ".join(t))
        self.hinweis.setVisible(bool(t))

    def _dok(self, e):
        k = e.data(SP_DOK, Qt.UserRole)
        return next((d for d in self.dokumente if id(d) == k), None)

    def _zeilen(self):
        for i in range(self.liste.topLevelItemCount()):
            e = self.liste.topLevelItem(i)
            d = self._dok(e)
            if d is not None:
                yield e, d

    def _haken_geaendert(self, e, spalte):
        d = self._dok(e)
        if d is not None and spalte == SP_DOK:
            d.gewaehlt = e.checkState(SP_DOK) == Qt.Checked
            self._zaehlen()

    def _ziel_geaendert(self, d, c):
        d.kategorie = c.currentData()
        self.aktualisieren()

    def alle(self, an):
        self.liste.blockSignals(True)
        for e, d in self._zeilen():
            d.gewaehlt = an and not d.intern        # Programmdateien nur einzeln von Hand (26.11.2026)
            e.setCheckState(SP_DOK, Qt.Checked if d.gewaehlt else Qt.Unchecked)
        self.liste.blockSignals(False)
        self._zaehlen()

    def nur_neue(self):
        self.liste.blockSignals(True)
        for e, d in self._zeilen():
            d.gewaehlt = self.status.get(id(d), (pa.NEU,))[0] in (pa.NEU, pa.GEAENDERT) and not d.intern
            e.setCheckState(SP_DOK, Qt.Checked if d.gewaehlt else Qt.Unchecked)
        self.liste.blockSignals(False)
        self._zaehlen()

    def _zaehlen(self):
        n = sum(d.gewaehlt for d in self.dokumente)
        self.zahl.setText(f"{n} von {len(self.dokumente)} ausgewählt")
        self.knopf_speichern.setEnabled(n > 0)

    def hinzufuegen(self, pfade=None):
        """Weitere Dateien (ohne pfade: Dateidialog). Ergebnis: Anzahl neu aufgenommen."""
        if pfade is None:
            if self.stumm:
                return 0
            pfade, _ = QFileDialog.getOpenFileNames(self, "Weitere Dokumente hinzufügen", str(Path.home()))
        neu = pa.extern(pfade or (), self.dokumente)
        if neu:
            self.dokumente.extend(neu)
            self._liste_fuellen()
            self.liste.setCurrentItem(self.liste.topLevelItem(self.liste.topLevelItemCount() - 1))
            self.aktualisieren()
        return len(neu)

    def dragEnterEvent(self, ereignis):
        if ereignis.mimeData().hasUrls():
            ereignis.acceptProposedAction()

    def dropEvent(self, ereignis):
        pfade = [u.toLocalFile() for u in ereignis.mimeData().urls() if u.isLocalFile()]
        if pfade:
            self.hinzufuegen(pfade)
            ereignis.acceptProposedAction()

    # ------------------------------------------------------------------ Vorschau
    def _gewaehltes(self):
        e = self.liste.currentItem()
        return self._dok(e) if e is not None else None

    def _vorschau(self):
        d = self._gewaehltes()
        if d is None:
            self.vorschau.setPixmap(QPixmap())
            self.vorschau.setText("Keine Datei gewählt")
            return
        bild = vorschaubild(d.pfad, 260)
        if bild is not None and not bild.isNull():
            self.vorschau.setPixmap(bild)
        else:
            self.vorschau.setPixmap(QPixmap())
            self.vorschau.setText(f"{d.typ}\n{d.name}\n{pa.groesse_text(d.groesse)}\n\nVorschau mit „Vorschau öffnen“")

    def vorschau_gross(self):
        d = self._gewaehltes()
        if d is None or self.stumm:
            return None
        from . import anhang_vorschau
        eintraege = [dict(name=x.name, pfad=x.pfad) for x in self.dokumente]
        w = anhang_vorschau.fenster(self, eintraege, self.dokumente.index(d), extern=self.oeffnen_fn)
        w.show()
        return w

    # ------------------------------------------------------------------ Zuordnung und Status
    def pfad_pruefen(self, still=False):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            p = pa.pfad_pruefen(self.v.ordner)
        finally:
            QApplication.restoreOverrideCursor()
        self.pfad_ok = p
        self.pfad.setText(self.v.ordner or "– noch nicht festgelegt –")
        if not still and not p.ok:
            self.melden("Speicherort", p.text)
        return p

    def aktualisieren(self):
        nr, fehler, hinweis = pa.nummer_pruefen(self.nummer.text(), self.v.muster)
        farbe = stil.ROT if fehler else (stil.ORANGE if hinweis else stil.GRUEN)
        self.nummer_info.setText(fehler or hinweis or "Nummer in Ordnung.")
        self.nummer_info.setStyleSheet(f"color: {farbe};")
        p = self.pfad_ok
        self.ordner, self.vorhanden = None, False
        if p is None or not p.ok:
            self.ordner_info.setText((p.text if p else "") + ("  Bitte „Speicherpfad ändern …“." if p and p.art
                                                               in ("leer", "fehlt", "kein_ordner") else ""))
            self.ordner_info.setStyleSheet(f"color: {stil.ROT};")
        elif fehler:
            self.ordner_info.setText("Erst eine gültige Angebotsnummer eingeben.")
            self.ordner_info.setStyleSheet(f"color: {stil.TEXT_GRAU};")
        else:
            self.ordner, self.vorhanden = pa.ordner_status(self.v, nr, self.kunde.text(), self.bezeichnung.text())
            if self.vorhanden:
                self.ordner_info.setText(f"Vorhandener Ordner wird verwendet: {self.ordner}")
                self.ordner_info.setStyleSheet(f"color: {stil.GRUEN};")
            else:
                self.ordner_info.setText(f"Kein Ordner „{nr}“ im Hauptordner gefunden. Bitte den Angebotsordner "
                                         "zuerst in PPEASE anlegen; das Programm legt keine Angebotsordner an.")
                self.ordner_info.setStyleSheet(f"color: {stil.ROT};")
        self.status = pa.vergleichen(self.v, self.ordner if self.vorhanden else None, self.dokumente)
        for e, d in self._zeilen():
            st, h = self.status.get(id(d), (pa.NEU, ""))
            e.setText(SP_STATUS, pa.STATUS_TEXT[st])
            e.setToolTip(SP_STATUS, h or "")
            e.setForeground(SP_STATUS, _farbe(STATUS_FARBE[st]))
            w = self.liste.itemWidget(e, SP_AKTION)
            if st == pa.GEAENDERT:
                if w is None:
                    c = QComboBox()
                    for a in (pa.ERSETZEN, pa.NEUE_VERSION, pa.UEBERSPRINGEN):
                        c.addItem(pa.AKTION_TEXT[a], a)
                    c.setCurrentIndex(c.findData(self.aktionen.get(id(d), pa.ERSETZEN)))
                    c.currentIndexChanged.connect(lambda _=0, d=d, c=c: self.aktionen.__setitem__(id(d),
                                                                                                 c.currentData()))
                    self.aktionen.setdefault(id(d), pa.ERSETZEN)
                    self.liste.setItemWidget(e, SP_AKTION, c)
            elif w is not None:
                self.liste.removeItemWidget(e, SP_AKTION)
                self.aktionen.pop(id(d), None)
        self._uebersicht()
        self._zaehlen()
        self.knopf_ordner.setEnabled(bool(self.vorhanden) or bool(p and p.ok))
        return bool(p and p.ok and not fehler)

    def _uebersicht(self):
        zahl = {s: 0 for s in pa.STATUS_TEXT}
        for st, _ in self.status.values():
            zahl[st] += 1
        da = pa.vorhandene(self.ordner) if self.vorhanden else []
        self.vorhanden_liste.clear()
        for rel, groesse, zeit in da:
            self.vorhanden_liste.addItem(f"{rel}   ·   {pa.groesse_text(groesse)}   ·   "
                                         f"{datetime.datetime.fromtimestamp(zeit):%d.%m.%Y %H:%M}")
        if not da:
            self.vorhanden_liste.addItem("Im Angebotsordner liegen noch keine Dateien." if self.vorhanden else
                                         "Kein Angebotsordner gefunden.")
        self.uebersicht.setText(f"Vorhandene Dateien im Ordner: {len(da)}  ·  Neu: {zahl[pa.NEU]}  ·  Geändert: "
                                f"{zahl[pa.GEAENDERT]}  ·  Schon abgelegt: {zahl[pa.GLEICH] + zahl[pa.SCHON]}")

    # ------------------------------------------------------------------ Aktionen
    def pfad_aendern(self, pfad=None):
        """Hauptordner wählen (ohne pfad: Ordnerdialog), prüfen und für alle Plätze speichern."""
        if pfad is None:
            if self.stumm:
                return None
            pfad = QFileDialog.getExistingDirectory(self, "Hauptordner der PPEASE-Ablage wählen",
                                                    self.v.ordner or str(Path.home()))
            if not pfad:
                return None
        p = pa.pfad_pruefen(pfad)
        if not p.ok and not self.fragen("Speicherpfad", p.text + "\n\nTrotzdem als Speicherpfad festlegen?"):
            return None
        try:
            self.db.einstellung_setzen(pa.E_ORDNER, str(Path(pfad)))
        except Exception as e:       # noqa: BLE001 – Lesemodus, Admin-Vorgabe
            self.melden("Speicherpfad", f"Der Speicherpfad lässt sich nicht speichern:\n{fehler_text(e)}")
            return None
        self.v = pa.vorgaben(self.db)
        self.pfad_ok = p
        self.pfad.setText(self.v.ordner)
        self.aktualisieren()
        return p

    def ablage_pruefen(self):
        """Speicherort prüfen, Reste eines abgebrochenen Speichervorgangs entfernen. Ergebnis: Text."""
        p = self.pfad_pruefen(still=True)
        t = [p.text]
        self.aktualisieren()
        if p.ok and self.vorhanden:
            r = pa.aufraeumen(self.ordner)
            if r["entfernt"]:
                t.append(f"{len(r['entfernt'])} unvollständige Zwischendatei(en) entfernt.")
            if r["unterbrochen"]:
                u = r["unterbrochen"]
                t.append(f"Ein Speichervorgang von {u.get('von')} am {pa._kurz(u.get('zeit'))} wurde nicht "
                         "abgeschlossen; fehlende Dateien stehen als „Neu“ in der Liste und lassen sich erneut "
                         "speichern.")
                pa.unterbrochen_vermerken(self.ordner, self.kuerzel, u)
            s = pa.sperre_lesen(self.ordner)
            if s:
                t.append(f"Gerade gesperrt von {s.get('von')} ({s.get('platz')}) seit {str(s.get('zeit'))[11:16]}.")
            if not r["entfernt"] and not r["unterbrochen"] and not s:
                t.append("Angebotsordner in Ordnung.")
            self.aktualisieren()
        text = "\n".join(t)
        self.ergebnis.setText(text)
        self.melden("Ablage prüfen", text)
        return text

    def ordner_oeffnen(self):
        o = self.ordner if self.vorhanden else (Path(self.v.ordner) if self.v.ordner else None)
        if o and self.oeffnen_fn:
            self.oeffnen_fn(o)
        return o

    def _akte(self):
        if self.akte_erstellen and self.akte_erstellen():
            neu = pa.dokumente_sammeln(self.angebotsordner, self.anfrage_dateien)
            alt = {str(d.pfad) for d in self.dokumente}
            self.dokumente.extend(d for d in neu if str(d.pfad) not in alt)
            self._liste_fuellen()
            self.aktualisieren()

    def speichern(self):
        """„Dokumente speichern“. Ergebnis: Bericht oder None (abgebrochen/nicht möglich)."""
        self._takt.stop()
        nr, fehler, hinweis = pa.nummer_pruefen(self.nummer.text(), self.v.muster)
        if fehler:
            self.melden("Dokumente speichern", fehler)
            return None
        if hinweis and not self.fragen("Angebotsnummer", hinweis + "\n\nTrotzdem mit dieser Nummer speichern?"):
            return None
        p = self.pfad_pruefen(still=True)
        if not p.ok:
            self.aktualisieren()
            self.melden("Dokumente speichern", p.text + "\n\nEs wurde nichts gespeichert.")
            return None
        self.aktualisieren()
        gewaehlt = [d for d in self.dokumente if d.gewaehlt]
        if not gewaehlt:
            self.melden("Dokumente speichern", "Bitte mindestens ein Dokument auswählen.")
            return None
        if not self.vorhanden:      # Patrick 19.11.: nur vorhandene Ordner (legt PPEASE an), nie neu anlegen
            self.melden("Dokumente speichern", self.ordner_info.text() + "\n\nEs wurde nichts gespeichert.")
            return None
        if self.vorhanden:
            r = pa.aufraeumen(self.ordner)
            if r["unterbrochen"]:
                pa.unterbrochen_vermerken(self.ordner, self.kuerzel, r["unterbrochen"])
            self.aktualisieren()
        ersetzen = [d.name for d in gewaehlt if self.status.get(id(d), (pa.NEU,))[0] == pa.GEAENDERT
                    and self.aktionen.get(id(d)) == pa.ERSETZEN]
        if ersetzen and not self.fragen(
                "Vorhandene Dateien ersetzen",
                f"{len(ersetzen)} Datei(en) liegen schon mit anderem Inhalt im Ordner:\n\n"
                + "\n".join("• " + n for n in ersetzen[:12]) + ("\n…" if len(ersetzen) > 12 else "")
                + f"\n\nErsetzen? Die bisherige Fassung bleibt im Unterordner {pa.VERSIONEN}."):
            return None
        verschieben = self.verschieben.isChecked() and self.verschieben.isEnabled()
        if verschieben:
            # erst den Ordner am Angebot merken: ohne diesen Vermerk fände das Programm verschobene Dateien nicht
            try:
                pa.merken(self.db, self.kopf.get("id"), nr, self.kunde.text().strip(),
                          self.bezeichnung.text().strip(), self.ordner)
            except Exception as e:      # noqa: BLE001 – dann lieber nichts verschieben
                protokoll.warnung(f"PPEASE-Ablage: Nummer nicht gemerkt, Verschieben abgelehnt ({type(e).__name__}: {e})")
                self.melden("Dokumente verschieben",
                            "Die PPEASE-Nummer lässt sich am Angebot nicht speichern, deshalb fände das Programm "
                            "verschobene Dateien nicht wieder.\n\nEs wurde nichts verschoben. Mit „Verschieben“ aus "
                            f"lässt sich kopieren.\n\n{fehler_text(e) if isinstance(e, OSError) else e}")
                return None
        bewegt = [d for d in gewaehlt if not d.intern]
        if verschieben and bewegt and not self.fragen(
                "Dokumente verschieben",
                f"{len(bewegt)} Datei(en) werden in den PPEASE-Angebotsordner verschoben:\n{self.ordner}\n\n"
                "Jede Datei wird erst kopiert und geprüft, erst danach wird das Original entfernt. Programmdateien "
                "(JSON, Zwischenspeicher, Messungen) bleiben, wo sie sind; die Kalkulation findet die Dateien über "
                "die PPEASE-Nummer wieder.\n\nVerschieben?"):
            return None
        self.fortschritt.setRange(0, len(gewaehlt))
        self.fortschritt.setValue(0)

        def weiter(i, n, name):
            self.fortschritt.setValue(i)
            self.fortschritt.setFormat(f"{i} von {n}" + (f" – {name}" if name else ""))
            QApplication.processEvents()
            return True
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            b = pa.ablegen(self.v, self.ordner, self.dokumente, self.kuerzel, self.aktionen,
                           angebot=self.kopf.get("nummer") or "", nummer=nr, fortschritt=weiter,
                           verschieben=verschieben)
        except pa.Gesperrt as e:
            QApplication.restoreOverrideCursor()
            self.melden("Dokumente speichern", str(e))
            return None
        except OSError as e:
            QApplication.restoreOverrideCursor()
            self.melden("Dokumente speichern", f"Im Angebotsordner lässt sich nicht speichern:\n{fehler_text(e)}")
            return None
        QApplication.restoreOverrideCursor()
        self.letzter_bericht = b
        try:
            pa.merken(self.db, self.kopf.get("id"), nr, self.kunde.text().strip(), self.bezeichnung.text().strip(),
                      self.ordner)
        except Exception:       # noqa: BLE001 – Lesemodus: Ablage ist trotzdem geschehen
            protokoll.warnung("PPEASE-Ablage: Nummer am Angebot nicht gemerkt")
        protokoll.info(f"PPEASE-Ablage {nr}: {b.text()} ({self.ordner})")
        if b.verschoben:
            if self.nach_verschieben:
                try:
                    self.nach_verschieben(b.verschoben)
                except Exception as e:      # noqa: BLE001 – die Dateien liegen sicher im Ordner
                    protokoll.warnung(f"PPEASE-Ablage: neuer Ort nicht vermerkt ({type(e).__name__}: {e})")
            weg = {a for a, _ in b.verschoben}
            self.dokumente = [d for d in self.dokumente if str(d.pfad) not in weg]
            self._liste_fuellen()
        self.fortschritt.setFormat("fertig" if b.ok else "mit Fehlern beendet")
        teile = [b.text()]
        teile += [f"✕ {n}: {t}" for n, t in b.fehler[:6]]
        teile += [f"– {n}: {t}" for n, t in b.uebersprungen[:6]]
        teile += [f"⚠ {n}: {t}" for n, t in b.nicht_entfernt[:6]]
        self.ergebnis.setText("\n".join(teile))
        self.ergebnis.setStyleSheet(f"color: {stil.GRUEN if b.ok else stil.ROT};")
        self.aktualisieren()
        if not b.ok:
            self.melden("Dokumente speichern", "\n".join(meldung_text(b)))
        return b

    # ------------------------------------------------------------------ Rückfragen
    def _fragen(self, titel, text):
        if self.stumm:
            return True
        return QMessageBox.question(self, titel, text) == QMessageBox.Yes

    def _melden(self, titel, text):
        if not self.stumm:
            QMessageBox.information(self, titel, text)


def meldung_text(b):
    t = [b.text()]
    if b.abgebrochen:
        t.append("Der Vorgang wurde abgebrochen (Speicherort nicht mehr erreichbar?). Schon kopierte Dateien sind "
                 "vollständig; der Rest steht als „Neu“ in der Liste.")
    t += [f"{n}: {e}" for n, e in b.fehler[:8]]
    return t


def _farbe(hexwert):
    from PySide6.QtGui import QBrush, QColor
    return QBrush(QColor(hexwert))


def vorschaubild(pfad, kante):
    """Kleines Vorschaubild: Bilder direkt, PDF erste Seite (pypdfium2); sonst None."""
    p = Path(pfad)
    s = p.suffix.lower()
    try:
        if s in pa.BILDER:
            pix = QPixmap(str(p))
        elif s == ".pdf":
            import pypdfium2 as pdfium
            d = pdfium.PdfDocument(str(p))
            try:
                bild = d[0].render(scale=kante / max(d[0].get_size())).to_pil()
            finally:
                d.close()
            from PySide6.QtGui import QImage
            bild = bild.convert("RGB")
            q = QImage(bild.tobytes(), bild.width, bild.height, bild.width * 3, QImage.Format_RGB888).copy()
            pix = QPixmap.fromImage(q)
        else:
            return None
    except Exception:       # noqa: BLE001 – Vorschau ist nie Pflicht
        return None
    if pix.isNull():
        return None
    return pix.scaled(kante, kante, Qt.KeepAspectRatio, Qt.SmoothTransformation)
