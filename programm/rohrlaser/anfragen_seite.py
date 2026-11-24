"""Seite „Anfragen“ (Patrick 12.11.2026, Konzept „Outlook-Anbindung und Anfragenverwaltung“, Paket 1).

Oben eine Zählerleiste Neu · In Bearbeitung · Erledigt · Meine (ein Klick filtert), dazu Suche und Filter. Links die
Liste der Anfragen, rechts die gewählte Anfrage: Mailtext, Anhänge, verknüpfte Angebote, Notizen und Verlauf, darunter
die Knöpfe je Status (Übernehmen, Kalkulieren, Als erledigt markieren …). Die Daten kommen aus den Akten
(anfragen_akten.py); neue Anfragen erfasst die Karte „Neue Anfragen“ der Startseite aus dem Anfrage-Ordner. Alle
AKTUALISIEREN_S Sekunden sieht die Seite in die Akten (Übernahmen anderer Arbeitsplätze); neue Anfragen melden sich
unten rechts in Windows. Paket 2 (13.11.2026): „Outlook …“ holt die Anfragen aus dem klassischen Outlook dieses
Rechners (outlook_anfragen.py), im Hintergrund alle outlook_anfragen.TAKT_S Sekunden.

Paket 5 (Freigabe 13.11.2026 „Alle fünf“): Ampel mit Antwortfrist in Arbeitstagen wie auf der Startseite (statt der
festen 24 Stunden), Vormessung der STEP-Dateien mit Richtpreis (einmal für alle Plätze, im Verlauf), fester Bearbeiter
je Kunde (Kundenstamm „Zuständig“), „Keine Anfrage“ aussortieren (mit Grund, nie gelöscht; ab dem zweiten Mal vom
selben Absender als Vorschlag), Auswertung (je Woche, Zeit bis zum Angebot, je Mitarbeiter, Trefferquote). Angebot per
E-Mail legt die Anfrage nach Erledigt (angebot_ausgabe.angebot_mail).

Paket 6 (Freigabe 14.11.2026 „Alle vier“): rechts „Erkannt“ mit Anfrage-Nr., Wunschtermin, Werkstoff und Staffel samt
Fundstelle und was noch fehlt (anfrage_erkennung.py, übernommen wird erst beim Kalkulieren), „Rückfrage …“ öffnet in
Outlook eine Antwort an den Kunden mit den fehlenden Angaben (nie automatisch gesendet; die Anfrage wartet auf den
Kunden, die Ampel ruht), Wiederholteile (gleiche STEP-Datei, bekannte Artikelnummer) mit „Aus letztem Angebot“, und
der Filter aus den Kacheln der Startseite (überfällig, heute fällig, meine)."""
import datetime
import html
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QToolButton, QVBoxLayout,
                               QWidget)

from . import anfrage_art as aa
from . import anfrage_ki_lokal as ki
from . import anfrage_lernen as al
from . import anfrage_nachfassen as anf
from . import anfrage_reihenfolge as ar
from . import anhang_analyse as an
from . import protokoll
from . import anfragen_akten as ak
from . import anfragen_dokumente as adok
from . import anfragen_sammeln as sa
from . import kunden_daten as kd
from . import mail_zuordnung as mz
from . import anfrage_phase as ph
from . import outlook_anfragen as ol
from . import stil
from . import virenpruefung as vp
from .klartext import fehler_text

AKTUALISIEREN_S = 30
SPALTEN = ("Nr.", "Kunde / Absender", "Betreff", "Eingang", "Anhänge", "Priorität", "Bearbeiter", "Status")
FARBE = {ak.NEU: "#8A94A6", ak.BEARBEITUNG: "#2F6FB3", ak.ERLEDIGT: "#2F7D4F"}     # dezent: Rand/Schrift
PRIO_FARBE = {"eilt": "#B42318", "hoch": "#A66A00"}
ERINNERN_AB = 7             # Erinnerung an wartende Anfragen: einmal am Tag ab 7 Uhr
ERINNERT = "anfragen_erinnert"      # Einstellung je Arbeitsplatz: Tag der letzten Erinnerung
ORDNER = (("neu", "Neu"), ("in_bearbeitung", "In Bearbeitung"), ("erledigt", "Erledigt"), ("meine", "Meine"),
          (ak.AUSSORTIERT, "Keine Anfrage"), (ak.GELOESCHT, "Gelöscht"))
AMPEL_FARBE = {"grün": "#2F7D4F", "gelb": "#A66A00", "rot": "#B42318"}
ERLEDIGT_TAGE = 90          # Erledigt zeigt standardmäßig die letzten 90 Tage


def _zeit(d):
    return d.strftime("%d.%m.%Y %H:%M") if d else ""


def _datum_text(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso or "")


class AnfragenSeite(QWidget):
    def __init__(self, fenster):
        super().__init__()
        self.f = fenster
        self.db = fenster.db
        self.titel = "Anfragen"
        self.akten, self._gewaehlt, self._mailtexte = [], None, {}
        self.ordner = "neu"
        self.ampel_filter = ""          # Paket 6: Filter aus der Startseiten-Kachel (ueberfaellig, heute, meine)
        self._erkannt = {}
        self._anhang_cache = {}      # 20.11.2026: Nr -> (Dateistand, anhang_analyse)
        self._ang_phase = {}         # 20.11.2026 (anfrage_phase): Angebotsnummern -> Phase aus Angebot/Auftrag
        self._kw = None              # 23.11.2026 (Wichtig zuerst): Kundenwerte aus den Angeboten, je Laden einmal
        lay = QVBoxLayout(self)
        # Zählerleiste
        oben = QHBoxLayout()
        self.gruppe = QButtonGroup(self)
        self.gruppe.setExclusive(True)
        self.zaehler = {}
        for key, text in ORDNER:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setObjectName("anfragen_zaehler")
            b.setMinimumHeight(40)
            b.clicked.connect(lambda _=False, k=key: self.ordner_waehlen(k))
            self.gruppe.addButton(b)
            self.zaehler[key] = b
            oben.addWidget(b)
        self.zaehler["neu"].setChecked(True)
        oben.addStretch(1)
        filter_ = QHBoxLayout()         # zweite Zeile: Suche und Filter (passt auch in schmale Fenster)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Kunde, Betreff, Text, Projekt-/Bestell-Nr., Datei, Mail, Angebot …")
        self.suche.setClearButtonEnabled(True)
        self.suche.setMinimumWidth(270)       # 20.11.2026: Platz für den Filter Mail-Art (Fenster bleibt maximiert)
        self.suche.textChanged.connect(lambda _t: self.liste_fuellen())
        filter_.addWidget(self.suche, 2)
        self.filter_bearbeiter = QComboBox()
        self.filter_bearbeiter.setToolTip("Nur Anfragen dieses Bearbeiters")
        self.filter_bearbeiter.currentIndexChanged.connect(lambda _i: self.liste_fuellen())
        filter_.addWidget(self.filter_bearbeiter)
        self.filter_prio = QComboBox()
        self.filter_prio.addItem("Alle Prioritäten", "")
        for p in reversed(ak.PRIORITAETEN):
            self.filter_prio.addItem(ak.PRIORITAET_TEXT[p], p)
        self.filter_prio.currentIndexChanged.connect(lambda _i: self.liste_fuellen())
        filter_.addWidget(self.filter_prio)
        self.filter_daten = QComboBox()     # Patrick 17.11.2026: Anfragen ohne STEP (nur PDF, ohne Anhang) finden
        for text, wert in (("Alle Anfragen", ""), ("Mit STEP", "step"), ("Ohne STEP", "ohne"),
                           ("Kunde prüfen", "pruefen")):
            self.filter_daten.addItem(text, wert)
        self.filter_daten.setToolTip("Ohne STEP: nur PDF-Zeichnung, nur DXF oder Mail ohne Anhang")
        self.filter_daten.currentIndexChanged.connect(lambda _i: self.liste_fuellen())
        filter_.addWidget(self.filter_daten)
        self.filter_art = QComboBox()       # 20.11.2026 (anfrage_art): nach Mail-Art filtern
        self.filter_art.addItem("Alle Mail-Arten", "")
        self.filter_art.addItem("Unklare Erkennung", "unklar")
        self.filter_art.addItem("Keine neue Anfrage", "andere")
        for art, titel in aa.ARTEN.items():
            self.filter_art.addItem(titel, art)
        self.filter_art.setToolTip("Was für eine Mail: Anfrage, Bestellung, Reklamation, Werbung … (erkannt beim "
                                   "Eingang, von Hand änderbar)")
        self.filter_art.currentIndexChanged.connect(lambda _i: self.liste_fuellen())
        self.filter_art.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.filter_art.setMinimumContentsLength(9)     # lange Arten gekürzt, das Fenster bleibt so breit wie bisher
        filter_.addWidget(self.filter_art)
        self.filter_kunde = QComboBox()     # 20.11.2026: Filter nach Kunde (Projekt-/Bestell-Nr. über die Suche)
        self.filter_kunde.setToolTip("Nur Anfragen dieses Kunden")
        self.filter_kunde.currentIndexChanged.connect(lambda _i: self.liste_fuellen())
        filter_.addWidget(self.filter_kunde)
        self.filter_zeit = QComboBox()
        for text, tage in (("Letzte 90 Tage", ERLEDIGT_TAGE), ("Letztes Jahr", 365), ("Alle", 0)):
            self.filter_zeit.addItem(text, tage)
        self.filter_zeit.setToolTip("Zeitraum für Erledigt")
        self.filter_zeit.currentIndexChanged.connect(lambda _i: self.liste_fuellen())
        filter_.addWidget(self.filter_zeit)
        knopf = QPushButton("Auswertung")
        knopf.setToolTip("Anfragen je Woche, Zeit bis zum Angebot, je Mitarbeiter, Trefferquote")
        knopf.clicked.connect(self.mitarbeiter_zeigen)
        oben.addWidget(knopf)
        knopf = QPushButton("Aktualisieren")
        knopf.clicked.connect(lambda: self.neu_laden(eingang=True))
        oben.addWidget(knopf)
        knopf = QPushButton("Outlook …")
        knopf.setToolTip("Anfragen aus dem klassischen Outlook dieses Rechners holen")
        knopf.clicked.connect(self.outlook_zeigen)
        oben.addWidget(knopf)
        lay.addLayout(oben)
        lay.addLayout(filter_)
        schnell = QHBoxLayout()         # 20.11.2026 (Plan K10): Schnellfilter, mehrere zugleich = alle müssen passen
        schnell.setSpacing(4)
        schnell.addWidget(QLabel("Schnellfilter:"))
        self.schnell = {}
        for k, (text, tipp) in SCHNELL.items():
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tipp)
            b.setCheckable(True)
            b.setStyleSheet(SCHNELL_STIL)   # 23.11.2026: eingeschaltet deutlich blau (vorher kaum zu sehen)
            b.toggled.connect(lambda _an: self.liste_fuellen())
            schnell.addWidget(b)
            self.schnell[k] = b
        self.k_filter_zurueck = QToolButton()   # 23.11.2026: alle Filter auf Vorgabe
        self.k_filter_zurueck.setText("✕ Filter zurücksetzen")
        self.k_filter_zurueck.setToolTip("Schnellfilter, Suche und alle Auswahlfelder auf Vorgabe (alle Anfragen)")
        self.k_filter_zurueck.clicked.connect(lambda: self.filter_zuruecksetzen())
        self.k_filter_zurueck.setVisible(False)
        schnell.addWidget(self.k_filter_zurueck)
        schnell.addStretch(1)
        self.wichtig_zuerst = QToolButton()     # 23.11.2026: Reihenfolge mit Gründen (anfrage_reihenfolge)
        self.wichtig_zuerst.setText("Wichtig zuerst")
        self.wichtig_zuerst.setToolTip("Sortiert nach Frist, Priorität, Mail-Art (Bestellung, Reklamation …), "
                                       "Kunde und Menge; die Gründe stehen rechts im Kopf der Anfrage")
        self.wichtig_zuerst.setCheckable(True)
        self.wichtig_zuerst.setStyleSheet(SCHNELL_STIL)
        self.wichtig_zuerst.toggled.connect(lambda _an: self.liste_fuellen())
        schnell.addWidget(self.wichtig_zuerst)
        lay.addLayout(schnell)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setVisible(False)
        lay.addWidget(self.hinweis)
        self.ol_status = QLabel()           # 20.11.2026 (Plan K8): letzter Outlook-Abruf, wartende Mails
        self.ol_status.setWordWrap(True)
        self.ol_status.setVisible(False)
        self.ol_status.linkActivated.connect(lambda _u: self.erneut_verarbeiten())
        lay.addWidget(self.ol_status)
        zeile = QHBoxLayout()           # Paket 6: Filter aus der Startseite, mit „Filter aufheben“
        self.filter_hinweis = QLabel()
        zeile.addWidget(self.filter_hinweis)
        self.k_filter_weg = QPushButton("Filter aufheben")
        self.k_filter_weg.clicked.connect(lambda: self.filter_setzen(""))
        zeile.addWidget(self.k_filter_weg)
        zeile.addStretch(1)
        self.filter_zeile = QWidget()
        self.filter_zeile.setLayout(zeile)
        zeile.setContentsMargins(0, 0, 0, 0)
        self.filter_zeile.setVisible(False)
        lay.addWidget(self.filter_zeile)

        teiler = QSplitter(Qt.Horizontal)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setAlternatingRowColors(True)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabelle.itemSelectionChanged.connect(self._gewaehlt_neu)
        self.tabelle.itemActivated.connect(lambda _it: self.hauptaktion())
        self.tabelle.setAcceptDrops(True)          # Dateien/Mails auf eine Zeile ziehen = zu dieser Anfrage
        self.tabelle.viewport().setAcceptDrops(True)
        self.tabelle.viewport().installEventFilter(self)
        teiler.addWidget(self.tabelle)

        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(8, 0, 0, 0)
        self.kopf = QLabel()
        self.kopf.setWordWrap(True)
        self.kopf.setTextFormat(Qt.RichText)
        rl.addWidget(self.kopf)
        self.inhalt = QTextBrowser()
        self.inhalt.setOpenLinks(False)
        self.inhalt.anchorClicked.connect(self._link)
        self.reiter = QTabWidget()      # 20.11.2026: Übersicht · Dokumente & Mails · Chronik
        self.reiter.addTab(self.inhalt, "Übersicht")
        self.dokumente = adok.DokumentePanel(self)
        self.reiter.addTab(self.dokumente, "Dokumente && Mails")
        self.chronik = QTextBrowser()
        self.reiter.addTab(self.chronik, "Chronik")
        rl.addWidget(self.reiter, 1)
        zeile = QHBoxLayout()
        self.wahl_bearbeiter = QComboBox()
        self.wahl_bearbeiter.setToolTip("Bearbeiter für Übernehmen bzw. Bearbeiter ändern")
        zeile.addWidget(self.wahl_bearbeiter)
        self.k_uebernehmen = QPushButton("Übernehmen")
        self.k_uebernehmen.setObjectName("primaer")
        self.k_uebernehmen.setToolTip("Anfrage für den gewählten Bearbeiter übernehmen (Enter)")
        self.k_uebernehmen.clicked.connect(lambda: self.uebernehmen())
        self.k_zuweisen = QPushButton("Zuweisen")
        self.k_zuweisen.setToolTip("Neue Anfrage dem gewählten Mitarbeiter vorschlagen (er übernimmt sie selbst)")
        self.k_zuweisen.clicked.connect(lambda: self.zuweisen())
        self.k_bearbeiter = QPushButton("Bearbeiter ändern")
        self.k_bearbeiter.clicked.connect(lambda: self.bearbeiter_aendern())
        self.k_kalkulieren = QPushButton("Kalkulieren")
        self.k_kalkulieren.setObjectName("primaer")
        self.k_kalkulieren.setToolTip("Neues Angebot aus den Dateien der Anfrage, mit der Anfrage verknüpft")
        self.k_kalkulieren.clicked.connect(lambda: self.kalkulieren())
        self.k_letztes = QPushButton("Aus letztem Angebot")
        self.k_letztes.setToolTip("Neues Angebot mit den Positionen des letzten Angebots dieser Teile, mit der Anfrage "
                                  "verknüpft")
        self.k_letztes.clicked.connect(lambda: self.aus_letztem_angebot())
        for b in (self.k_uebernehmen, self.k_zuweisen, self.k_bearbeiter, self.k_kalkulieren, self.k_letztes):
            zeile.addWidget(b)
        zeile.addStretch(1)
        rl.addLayout(zeile)
        zeile = QHBoxLayout()
        self.wahl_prio = QComboBox()
        for p in ak.PRIORITAETEN:
            self.wahl_prio.addItem(ak.PRIORITAET_TEXT[p], p)
        self.wahl_prio.setToolTip("Priorität")
        self.wahl_prio.activated.connect(lambda _i: self.prioritaet(self.wahl_prio.currentData()))
        zeile.addWidget(self.wahl_prio)
        self.k_notiz = QPushButton("Notiz …")
        self.k_notiz.clicked.connect(lambda: self.notiz())
        self.k_stand = QPushButton("Bearbeitungsstand …")
        self.k_stand.clicked.connect(lambda: self.bearbeitungsstand())
        self.k_zurueck = QPushButton("Zurückgeben")
        self.k_zurueck.setToolTip("Zurück nach Neu, ein anderer kann sie übernehmen")
        self.k_zurueck.clicked.connect(lambda: self.zurueckgeben())
        self.k_erledigt = QPushButton("Als erledigt markieren")
        self.k_erledigt.clicked.connect(lambda: self.erledigen())
        self.k_wieder = QPushButton("Wieder öffnen")
        self.k_wieder.clicked.connect(lambda: self.wieder_oeffnen())
        self.k_keine = QPushButton("Keine Anfrage …")
        self.k_keine.setToolTip("Werbung, Rechnung o. Ä.: mit Grund aussortieren (wird nicht gelöscht)")
        self.k_keine.clicked.connect(lambda: self.aussortieren())
        self.k_loeschen = QPushButton("Löschen …")      # Patrick 24.11.2026: Anfrage löschen (Ordner „Gelöscht“)
        self.k_loeschen.setToolTip("Anfrage in den Ordner „Gelöscht“ legen: aus allen Listen heraus, kommt nicht als "
                                   "neue Anfrage zurück, „Wiederherstellen“ holt sie zurück")
        self.k_loeschen.clicked.connect(lambda: self.loeschen())
        self.k_herstellen = QPushButton("Wiederherstellen")
        self.k_herstellen.setToolTip("Gelöschte Anfrage zurück in ihren alten Ordner")
        self.k_herstellen.clicked.connect(lambda: self.wiederherstellen())
        self.k_rueckfrage = QPushButton("Rückfrage …")
        self.k_rueckfrage.setToolTip("Antwort an den Kunden in Outlook öffnen, mit den fehlenden Angaben (wird nicht "
                                     "automatisch gesendet); die Anfrage wartet dann auf den Kunden")
        self.k_rueckfrage.clicked.connect(lambda: self.rueckfrage())
        for b in (self.k_notiz, self.k_stand, self.k_rueckfrage, self.k_keine, self.k_zurueck, self.k_erledigt,
                  self.k_wieder, self.k_loeschen, self.k_herstellen):
            zeile.addWidget(b)
        zeile.addStretch(1)
        rl.addLayout(zeile)
        teiler.addWidget(rechts)
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 2)
        teiler.setSizes([780, 620])
        lay.addWidget(teiler, 1)
        self.teiler, self._geteilt = teiler, False

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.neu_laden(takt=True))
        self.timer.start(AKTUALISIEREN_S * 1000)
        self._takt_stand = None         # Stand beim letzten Takt: unverändert -> Liste nicht neu aufbauen
        self._bekannt = None            # Nummern der neuen Anfragen beim letzten Lesen (Windows-Meldung)
        self._antworten = {}            # Antworten des Kunden je Anfrage beim letzten Lesen
        self.neu_laden()
        # Outlook: Abruf im Hintergrund (nur wenn an diesem Rechner eingeschaltet)
        self._ol_pool, self._ol_lauf, self.outlook_letzt = None, None, None
        self.outlook_timer = QTimer(self)
        self.outlook_timer.timeout.connect(self.outlook_abrufen)
        self.outlook_timer.start(ol.TAKT_S * 1000)
        self._ol_warten = QTimer(self)
        self._ol_warten.setInterval(500)
        self._ol_warten.timeout.connect(self._outlook_pruefen)
        QTimer.singleShot(3000, self.outlook_abrufen)

    def eventFilter(self, obj, e):
        """Ziehen auf eine Zeile der Liste: Dateien bzw. Outlook-Mails zu dieser Anfrage."""
        if obj is self.tabelle.viewport() and e.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            m = e.mimeData()
            if not (m.hasUrls() or adok.ist_outlook_zug(m)):
                return False
            if e.type() != QEvent.Drop:
                e.acceptProposedAction()
                return True
            it = self.tabelle.itemAt(e.position().toPoint())
            if it is not None:
                self.waehlen(it.data(Qt.ItemDataRole.UserRole))
                if m.hasUrls():
                    self.dokumente_hinzufuegen([ak.Path(u.toLocalFile()) for u in m.urls() if u.isLocalFile()],
                                               quelle="drag")
                else:
                    self.outlook_auswahl_hinzufuegen(quelle="drag")
            e.acceptProposedAction()
            return True
        return super().eventFilter(obj, e)

    def showEvent(self, ereignis):
        """Beim ersten Zeigen: Liste links etwas breiter als die Anfrage rechts (Betreff und Status lesbar)."""
        super().showEvent(ereignis)
        if not self._geteilt and self.teiler.width() > 0:
            self._geteilt = True
            b = self.teiler.width()
            self.teiler.setSizes([int(b * 0.58), b - int(b * 0.58)])

    # ------------------------------------------------------------------ Daten
    def ablage(self):
        return ak.ablage(self.db)

    def ich(self):
        return ak.kuerzel(self.db)

    def mitarbeiter_liste(self):
        from . import teilen
        namen = {self.ich(): f"{self.ich()} (ich)"}
        try:
            for k, n in teilen.kollegen(self.db).items():
                namen[k] = f"{k} – {n}" if n else k
        except Exception:
            pass
        for a in self.akten:
            for k in (a.bearbeiter, a.stand["zugewiesen"]):
                if k and k not in namen:
                    namen[k] = k
        return namen

    def mitarbeiter_namen(self):
        """{Kürzel: Name} aller Mitarbeiter (für die Zuordnung der Outlook-Kategorien)."""
        from . import teilen
        out = {}
        try:
            out[self.ich()] = str(self.db.einstellung("benutzer_name") or "").strip()
            out.update(teilen.kollegen(self.db))
        except Exception:               # noqa: BLE001
            pass
        for k in self.mitarbeiter_liste():
            out.setdefault(k, "")
        return out

    def neu_laden(self, eingang=False, takt=False):
        """Akten neu lesen; eingang: vorher den Anfrage-Ordner ansehen (Karte der Startseite). takt: Aufruf der Uhr
        alle AKTUALISIEREN_S Sekunden – ist keine Akte geändert (Ablage liefert dann dieselben Objekte aus ihrem
        Zwischenspeicher), bleibt die Liste stehen. Vorher baute jeder Takt alles neu auf: alle 30 s stand das
        Programm 0,5–0,7 s, auch auf der Startseite (Supportpaket 20.11.2026)."""
        if eingang:
            karte = getattr(getattr(self.f, "start", None), "anfragen", None)
            if karte is not None:
                karte.neu_laden(erzwingen=True)
        from . import tempo           # Abschnitte für den Zeitwächter (29-s-Hänger beim ersten Öffnen, 23.11.2026)
        if not getattr(self, "_wiederhergestellt", False) and not getattr(self.db, "nur_lesen", False):
            self._wiederhergestellt = True
            try:                        # abgebrochene Zusammenführungen (Absturz, Netz) zu Ende führen
                with tempo.abschnitt("Anfragen: Zusammenführungen prüfen"):
                    meldungen = sa.wiederherstellen(self.ablage())
                for t in meldungen:
                    self.f.meldung(t)
            except Exception as fehler:           # noqa: BLE001
                protokoll.warnung(f"Anfragen: Meldung nicht angezeigt ({type(fehler).__name__}: {fehler})")
        try:
            with tempo.abschnitt("Anfragen: Akten lesen"):
                akten = self.ablage().alle()
            stand = (tuple(map(id, akten)), datetime.datetime.now().strftime("%Y%m%d%H"))  # Ampel/Fristen stündlich
            if takt and stand == self._takt_stand and akten:
                return
            self._takt_stand = stand
            self.akten = akten
            self.hinweis.setVisible(False)
            self.fehlalarme_aufheben()
        except OSError as e:
            self.akten = []
            self._takt_stand = None
            self.hinweis.setText(f"Anfragen nicht lesbar: {fehler_text(e)}")
            self.hinweis.setVisible(True)
        self._erkannt = {}
        self._ang_phase = {}
        self._kw = None
        self._modell_cache = None
        if not takt:
            with tempo.abschnitt("Anfragen: Outlook-Status"):
                self.ol_status_zeigen()
        for name, schritt in (("Zuständige", self._zustaendige), ("Ampeln", self._ampeln_setzen),
                              ("Zähler", self._zaehler_setzen), ("Auswahl", self._auswahl_fuellen),
                              ("Liste füllen", self.liste_fuellen), ("Neue melden", self._neue_melden),
                              ("Virenprüfung starten", self.viren_starten), ("Vormessen", self.vormessen),
                              ("Kacheln", self._kacheln_melden)):
            with tempo.abschnitt(f"Anfragen: {name}"):
                schritt()

    # ------------------------------------------------------------------ Paket 5: Zuständig, Ampel, Vormessung
    def _zustaendige(self):
        """Fester Bearbeiter je Kunde (Kundenstamm „Zuständig“): neue Anfragen gleich zuweisen (Einstellung
        anfrage_zuweisen)."""
        try:
            if self.db.nur_lesen or (self.db.einstellung("anfrage_zuweisen") or "ja") != "ja":
                return []
            neu = [a for a in self.akten if a.status == ak.NEU and a.kunde]
            if not neu:
                return []
            erg = self.ablage().zustaendig_zuweisen(neu, self.db.zeilen("kunden"))
        except Exception:               # noqa: BLE001 – Zuweisung ist Komfort, nie ein Grund für einen Fehler
            return []
        try:                            # 20.11.2026 (Plan K7): sichere Vorschläge nur mit Einstellung, Vorgabe aus
            if (self.db.einstellung(ph.AUTO) or "nein") == "ja":
                erg = list(erg or []) + ph.vorschlaege_zuweisen(self.ablage(), self.akten, self.db.zeilen("kunden"),
                                                                list(self.mitarbeiter_liste()))
        except Exception as fehler:     # noqa: BLE001 – Komfort, nie ein Fehler
            protokoll.warnung(f"Anfragen: Bearbeiter-Vorschläge nicht zugewiesen ({type(fehler).__name__}: {fehler})")
        if erg:
            abl = self.ablage()
            self.akten = [abl.neu_lesen(a) if a.nr in dict(erg) else a for a in self.akten]
        return erg

    def _modell(self, ziel="art"):
        """Freigegebenes Modell (anfrage_lernen; Mail-Art, Sachgebiet oder Bearbeiter) oder {} (je Laden einmal
        gelesen)."""
        if getattr(self, "_modell_cache", None) is None:
            self._modell_cache = {}
        if ziel not in self._modell_cache:
            try:
                self._modell_cache[ziel] = al.aktiv_lesen(self.ablage().wurzel, ziel)
            except OSError:
                self._modell_cache[ziel] = {}
        return self._modell_cache[ziel]

    def ki_fragen(self, senden=None):
        """Optionale lokale KI (Einstellung anfragen_ki_lokal, Vorgabe aus): Vorschläge zu technischen Angaben, nur
        Werte, die im Text stehen; nur Anzeige zum Prüfen."""
        a = self.akte()
        if a is None:
            return None
        if not ki.an(self.db):
            self.f.meldung("Die lokale KI ist ausgeschaltet (Einstellung anfragen_ki_lokal).", fehler=True)
            return None
        url, modell = ki.einstellungen(self.db)
        try:
            werte = ki.vorschlaege(f"{a.betreff}\n{self._mailtext(a)}", url, modell,
                                   senden=senden or getattr(self, "ki_senden", None))
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.erkennung(a)["ki"] = werte
        self._zeigen(a)
        self.f.meldung(f"Lokale KI: {len(werte)} Vorschlag/Vorschläge, bitte prüfen.")
        return werte

    def phase(self, a):
        """Phase der Akte (anfrage_phase) mit den verknüpften Angeboten und Aufträgen (je Laden zwischengespeichert)."""
        n = tuple(a.stand.get("angebote") or ())
        if n and n not in self._ang_phase:
            try:
                self._ang_phase[n] = ph.angebots_phase(self.db, n)
            except Exception as fehler:     # noqa: BLE001
                protokoll.warnung(f"Anfragen: Phase aus Angebot nicht bestimmt ({type(fehler).__name__}: {fehler})")
                self._ang_phase[n] = ph.ANGEBOT
        return ph.phase(a, self._ang_phase.get(n, ""))

    def vorschlag(self, a):
        """Bearbeiter-Vorschlag für eine neue Anfrage (anfrage_phase.vorschlag) oder None."""
        if a is None or a.status != ak.NEU:
            return None
        try:
            ein = a.einordnung or {}
            gelernt = al.bearbeiter_tipp(self._modell("bearbeiter"), a.betreff, a.kunde or "",
                                         ein.get("sachgebiete") or ())
            return ph.vorschlag(a, self.akten, self.db.zeilen("kunden"), list(self.mitarbeiter_liste()),
                                gelernt=gelernt)
        except Exception as fehler:     # noqa: BLE001 – Hilfe, nie ein Fehler
            protokoll.warnung(f"Anfragen: kein Bearbeiter-Vorschlag ({type(fehler).__name__}: {fehler})")
            return None

    def _ampeln_setzen(self, jetzt=None):
        """Ampel je Akte (Frist in Arbeitstagen nach Kundenvorgabe bzw. Einstellung anfrage_frist)."""
        from . import anfrage_vorab
        self.ampeln, tage = {}, {}
        try:
            land = self.db.einstellung("versand_bundesland")
        except Exception:               # noqa: BLE001
            land = None
        for a in self.akten:
            if a.status == ak.ERLEDIGT:
                continue
            try:
                if a.kunde not in tage:
                    tage[a.kunde] = anfrage_vorab.frist_tage(self.db, a.kunde or None)
                self.ampeln[a.nr] = ak.ampel(a, tage[a.kunde], jetzt=jetzt, land=land)
            except Exception:           # noqa: BLE001
                self.ampeln[a.nr] = (None, None, "")
        return self.ampeln

    def dringend(self, a):
        """Ampel rot oder gelb (heute fällig bzw. überfällig)."""
        return (self.ampeln.get(a.nr) or (None,))[0] in ("rot", "gelb")

    vormess_auftrag = None              # Tests: ersetzt anfrage_vorab.auftrag/messen (dict(messen=callable))

    def vormessen(self):
        """Offene Akten mit STEP-Dateien im Hintergrund vormessen (eine nach der anderen, nur ein Platz je Akte)."""
        from . import anfrage_vorab, anfragen
        if getattr(self, "_vm_lauf", None) is not None:
            return False
        try:
            if self.db.nur_lesen or (self.db.einstellung("anfrage_vormessen") or "ja") != "ja":
                return False
        except Exception:               # noqa: BLE001
            return False
        abl = self.ablage()
        for a in self.akten:
            if a.status == ak.ERLEDIGT or a.virus() or a.stand.get("versendet"):
                continue
            dateien = [d["pfad"] for d in a.dateien() if not d.get("gesperrt") and not d.get("aus_mail")
                       and d["pfad"].is_file() and ak.Path(d["name"]).suffix.lower() not in ak.GEFAEHRLICH]
            anf = anfragen.Anfrage(a.betreff, None, dateien, a.kunde or None)
            if not anf.step_anzahl():
                continue
            st = ak.pruefsumme_text("|".join(f"{p.name}:{p.stat().st_size}" for p in anf.dateien))
            if a.stand.get("vormessung_stempel") == st:
                continue
            try:
                job = self.vormess_auftrag or anfrage_vorab.auftrag(self.db, self.f.programmordner, anf)
            except Exception:           # noqa: BLE001
                job = None
            if not job:                 # ausgeschaltet oder kein Messprogramm
                return False
            if not abl.vormessung_nehmen(a, st):
                continue
            if isinstance(job, dict) and not job.get("messen"):
                job = dict(job, ablage=str(a.pfad / anfrage_vorab.MESSUNG))    # für alle Plätze in die Akte
            messen = job.get("messen") if isinstance(job, dict) and job.get("messen") else anfrage_vorab.messen
            self._vm_pool = getattr(self, "_vm_pool", None) or ThreadPoolExecutor(max_workers=1)
            self._vm_lauf = (a.nr, st, anf, self._vm_pool.submit(messen, job, anf))
            if not hasattr(self, "_vm_warten"):
                self._vm_warten = QTimer(self)
                self._vm_warten.setInterval(1000)
                self._vm_warten.timeout.connect(self._vormessung_pruefen)
            self._vm_warten.start()
            return True
        return False

    def _vormessung_pruefen(self, warten=False):
        """Fertige Vormessung auswerten (Hauptthread: Profile und Richtpreis aus der Datenbank) und in den Verlauf."""
        from . import anfrage_vorab
        lauf = getattr(self, "_vm_lauf", None)
        if lauf is None:
            return False
        nr, st, anf, fu = lauf
        if not warten and not fu.done():
            return False
        self._vm_lauf = None
        self._vm_warten.stop()
        try:
            werte = fu.result()
        except Exception:               # noqa: BLE001
            werte = None
        t = "keine Teile erkannt"
        if werte:
            try:
                z = anfrage_vorab.zusammenfassung(werte, self.db.kontext().profile)
                preis = anfrage_vorab.richtpreis(self.db, anf.kunde, werte)
                t = anfrage_vorab.text(z, preis, anfrage_vorab.wiederholt(self.db, anf.kunde, z["artikel"])) or t
            except Exception:           # noqa: BLE001
                pass
        a = self.akte(nr)
        if a is not None:
            try:
                self.ablage().vormessung_merken(a, t, st)
            except OSError:
                pass
        self.neu_laden()
        return True

    # ------------------------------------------------------------------ Virenprüfung (Paket 3)
    viren_exe = None                    # Tests: Pfad des Prüfprogramms
    viren_ausfuehren = None             # Tests: ersetzt subprocess.run

    def _viren_exe(self):
        """Prüfprogramm, nur wenn die eigene Virenprüfung eingeschaltet ist (seit 16.11.2026 Vorgabe aus)."""
        if not vp.an(self.db):
            return None
        return self.viren_exe or vp.programm()

    def fehlalarme_aufheben(self):
        """Sperren der alten Prüfung (Fund nur aus dem Rückgabewert, Fehlalarm) einmal aufheben. Ergebnis: Anzahl."""
        if self.db.nur_lesen:
            return 0
        n = 0
        for a in [a for a in self.akten if a.fehlalarme()]:
            try:
                n += len(self.ablage().sperre_aufheben(a, a.fehlalarme(), grund="Fehlalarm der alten Virenprüfung"))
            except OSError:
                continue
        if n:
            self.akten = self.ablage().alle()
            self.f.meldung(f"{n} Anhang/Anhänge wieder freigegeben: die alte Virenprüfung hatte sie fälschlich als "
                           "Virus gesperrt.")
        return n

    def sperre_aufheben(self, name, fragen=True):
        """Eine gesperrte Datei der gewählten Anfrage wieder freigeben (Fehlalarm), mit Rückfrage. Ergebnis: True."""
        a = self.akte()
        if a is None or self.db.nur_lesen:
            return False
        if fragen and not self.f.stumm:
            if QMessageBox.question(self, "Sperre aufheben", f"{name} wieder freigeben?\n\nNur wenn sicher ist, dass "
                                    "die Datei harmlos ist (Fehlalarm). Der Windows-Virenschutz prüft sie beim "
                                    "Öffnen trotzdem.") != QMessageBox.Yes:
                return False
        ok = bool(self.ablage().sperre_aufheben(a, [name], grund=f"von {self.ich()} als Fehlalarm freigegeben"))
        self.neu_laden()
        self.waehlen(a.nr)
        return ok

    def viren_starten(self, warten=False):
        """Ungeprüfte Dateien der offenen Anfragen im Hintergrund prüfen (je Lauf höchstens 5 Anfragen)."""
        if getattr(self, "_vp_lauf", None) is not None or self.db.nur_lesen or not self._viren_exe():
            return False
        versucht = self.__dict__.setdefault("_vp_versucht", set())
        offen = [a for a in self.akten if a.status != ak.ERLEDIGT and a.nr not in versucht and a.ungeprueft()][:5]
        if not offen:
            return False
        versucht.update(a.nr for a in offen)
        abl, exe, aus = self.ablage(), self._viren_exe(), self.viren_ausfuehren

        def lauf():
            erg = {}
            for a in offen:
                try:
                    w = abl.viren_pruefen(a, exe=exe, ausfuehren=aus)
                except OSError:
                    continue
                if w:
                    erg[a.nr] = w
            return erg
        self._vp_pool = getattr(self, "_vp_pool", None) or ThreadPoolExecutor(max_workers=1)
        self._vp_lauf = self._vp_pool.submit(lauf)
        if warten:
            self._vp_lauf.result()
            self._viren_pruefen()
        else:
            QTimer.singleShot(500, self._viren_pruefen)
        return True

    def _viren_pruefen(self):
        f = getattr(self, "_vp_lauf", None)
        if f is None:
            return
        if not f.done():
            QTimer.singleShot(500, self._viren_pruefen)
            return
        self._vp_lauf = None
        try:
            erg = f.result()
        except Exception:               # noqa: BLE001 – Prüfung darf das Programm nie stören
            erg = {}
        funde = [f"{nr}: {name}" for nr, w in erg.items() for name, r in w.items() if r == vp.FUND]
        if funde:
            self.f.meldung("Virus gefunden und gesperrt: " + ", ".join(funde), fehler=True)
            try:
                from .teilen_fenster import windows_meldung
                windows_meldung(self.f, "Virus in einer Anfrage gefunden", funde)
            except Exception:
                pass
        if erg:
            self.neu_laden()

    def _neue_melden(self):
        """Neue Anfragen seit dem letzten Lesen unten rechts in Windows melden (nicht beim ersten Lesen)."""
        neu = {a.nr: a for a in self.akten if a.status == ak.NEU}
        antw = {a.nr: a.stand.get("antworten", 0) for a in self.akten}
        erst = self._bekannt is None
        dazu = [] if erst else [a for nr, a in neu.items() if nr not in self._bekannt]
        antworten = [] if erst else [a for a in self.akten if antw[a.nr] > self._antworten.get(a.nr, 0)]
        self._bekannt, self._antworten = set(neu), antw
        try:
            from .teilen_fenster import windows_meldung
            if dazu:
                windows_meldung(self.f, "Neue Anfrage" if len(dazu) == 1 else f"{len(dazu)} neue Anfragen",
                                [f"{a.kunde or a.absender or a.nr}: {a.betreff}" for a in dazu])
            if antworten:
                windows_meldung(self.f, "Antwort des Kunden" if len(antworten) == 1
                                else f"{len(antworten)} Antworten von Kunden",
                                [f"{a.nr} ({a.bearbeiter or 'neu'}): {a.betreff}" for a in antworten])
        except Exception:
            pass
        self._erinnern()

    def _erinnern(self, jetzt=None):
        """Einmal am Tag (ab ERINNERN_AB Uhr): Anfragen, deren Antwortfrist heute endet oder abgelaufen ist (Ampel
        gelb oder rot; ohne Frist: länger als 24 Stunden neu), melden. Ergebnis: Text."""
        jetzt = jetzt or datetime.datetime.now()
        heute = jetzt.date().isoformat()
        if jetzt.hour < ERINNERN_AB or self.db.nur_lesen or (self.db.einstellung(ERINNERT) or "") == heute:
            return ""
        amp = self._ampeln_setzen(jetzt)
        warten = [a for a in self.akten if (amp.get(a.nr) or (None,))[0] in ("rot", "gelb")]
        nach = [a for a in self.akten if (self.nachfassen_stand(a, jetzt) or {}).get("faellig_ist")]
        if not warten and not nach:
            return ""
        if not warten:                  # 23.11.2026: nur Rückfragen nachzufassen
            self.db.einstellung_setzen(ERINNERT, heute)
            titel = ("1 Rückfrage" if len(nach) == 1 else f"{len(nach)} Rückfragen") + " ohne Antwort: nachfassen"
            self.f.meldung(f"{titel}: " + ", ".join(a.nr for a in nach[:5]) + (" …" if len(nach) > 5 else ""))
            return titel
        self.db.einstellung_setzen(ERINNERT, heute)
        if all(amp[a.nr][1] is None for a in warten):          # ohne Frist: alte Regel
            titel = ("1 Anfrage wartet" if len(warten) == 1 else f"{len(warten)} Anfragen warten") + \
                f" seit über {ak.ERINNERN_STUNDEN} Stunden"
        else:
            titel = ("1 Anfrage ist" if len(warten) == 1 else f"{len(warten)} Anfragen sind") + \
                " heute fällig oder überfällig"
        if nach:
            titel += f", {len(nach)} Rückfrage{'n' if len(nach) != 1 else ''} nachfassen"
        self.f.meldung(f"{titel}: " + ", ".join(a.nr for a in warten[:5]) + (" …" if len(warten) > 5 else ""))
        try:
            from .teilen_fenster import windows_meldung
            windows_meldung(self.f, titel, [f"{a.nr}: {a.betreff}" for a in warten])
        except Exception:
            pass
        return titel

    def _zaehler_setzen(self):
        z = ak.zaehlen(self.akten, self.ich())
        for key, text in ORDNER:
            self.zaehler[key].setText(f"{text}  {z[key]}")
        warten = sum(self.dringend(a) for a in self.akten if a.status == ak.NEU)
        self.zaehler["neu"].setToolTip(f"{warten} Anfrage(n) heute fällig oder überfällig"
                                       if warten else "Neue Anfragen, noch nicht übernommen")
        self.zaehler[ak.AUSSORTIERT].setToolTip("Aussortiert: Werbung, Rechnungen u. Ä. (nichts wird gelöscht)")
        self.zaehler[ak.GELOESCHT].setToolTip("Gelöschte Anfragen (für alle ausgeblendet, wiederherstellbar)")
        try:
            i = self.f.reiter.indexOf(self)
            if i >= 0:
                self.f.reiter.setTabText(i, f"Anfragen ({z['neu']})" if z["neu"] else "Anfragen")
        except Exception:
            pass

    def _auswahl_fuellen(self):
        namen = self.mitarbeiter_liste()
        for box, alle in ((self.filter_bearbeiter, "Alle Bearbeiter"), (self.wahl_bearbeiter, None)):
            alt = box.currentData()
            box.blockSignals(True)
            box.clear()
            if alle:
                box.addItem(alle, "")
            for k, t in namen.items():
                box.addItem(t, k)
            i = box.findData(alt if alt is not None else (self.ich() if not alle else ""))
            box.setCurrentIndex(max(0, i))
            box.blockSignals(False)
        alt = self.filter_kunde.currentData()
        namen_k = self._kunden_namen()
        self.filter_kunde.blockSignals(True)
        self.filter_kunde.clear()
        self.filter_kunde.addItem("Alle Kunden", "")
        for nr in sorted({a.kunde for a in self.akten if a.kunde}, key=lambda n: (namen_k.get(n) or n).lower()):
            self.filter_kunde.addItem(f"{namen_k.get(nr) or nr} ({nr})", nr)
        self.filter_kunde.setCurrentIndex(max(0, self.filter_kunde.findData(alt or "")))
        self.filter_kunde.blockSignals(False)

    def sichtbare(self):
        tage = self.filter_zeit.currentData() if self.ordner in (ak.ERLEDIGT, ak.AUSSORTIERT) else 0
        seit = datetime.datetime.now() - datetime.timedelta(days=tage) if tage else None
        liste = ak.filtern(self.akten, self.ordner, self.ich(), self.suche.text(),
                           self.filter_bearbeiter.currentData() or "", self.filter_prio.currentData() or "", seit)
        if self.ampel_filter:
            liste = [a for a in liste if self.passt_filter(a, self.ampel_filter)]
        daten = self.filter_daten.currentData() or ""
        if daten == "pruefen":
            liste = [a for a in liste if a.kunde_pruefen()]
        elif daten:
            liste = [a for a in liste if (a.daten_art() == "step") == (daten == "step")]
        kunde = self.filter_kunde.currentData() if hasattr(self, "filter_kunde") else ""
        if kunde:
            liste = [a for a in liste if a.kunde == kunde]
        art = self.filter_art.currentData() if hasattr(self, "filter_art") else ""
        if art:
            liste = [a for a in liste if _art_passt(a.einordnung, art)]
        for k, b in getattr(self, "schnell", {}).items():
            if b.isChecked():
                liste = [a for a in liste if self.schnell_passt(a, k)]
        if getattr(self, "wichtig_zuerst", None) is not None and self.wichtig_zuerst.isChecked():
            liste = ar.sortieren(liste, {a.nr: self.reihenfolge(a) for a in liste})
        return liste

    def nachfassen_stand(self, a, jetzt=None):
        """anfrage_nachfassen.stand der Akte (Einstellung TAGE, Bundesland wie die Ampel)."""
        try:
            land = self.db.einstellung("versand_bundesland")
        except Exception:               # noqa: BLE001
            land = None
        return anf.stand(a, anf.tage(self.db), jetzt=jetzt, land=land)

    def reihenfolge(self, a, voll=False):
        """(Punkte, Teile) für „Wichtig zuerst“. Technische Werte (Menge) nur, wenn die Akte schon erkannt ist oder
        voll=True (Kopf der Akte), damit die Liste ohne Mail-Texte auskommt."""
        if self._kw is None:
            from . import vertrieb
            try:
                self._kw = vertrieb.kunden_werte(self.db.angebote())
            except Exception:           # noqa: BLE001 – ohne Angebote: kein Kundenwert
                self._kw = {}
        from . import vertrieb
        erk = self.erkennung(a) if voll else self._erkannt.get(a.nr) or {}
        ein = erk.get("einordnung") or a.einordnung
        return ar.punkte(a, (self.ampeln.get(a.nr) or (None,))[0], ein, erk.get("technik") or (),
                         vertrieb.wichtigkeit(self._kw, a.kunde), self.nachfassen_stand(a))

    def schnell_passt(self, a, k):
        """Schnellfilter k (SCHNELL) für die Akte a."""
        if k == "ohne":
            return a.status == ak.NEU and not a.stand.get("zugewiesen")
        if k == "kunde":
            return a.kunde_pruefen()
        if k == "dringend":
            return a.prioritaet in ("hoch", "eilt") or self.dringend(a)
        if k == "ueberfaellig":
            return (self.ampeln.get(a.nr) or (None,))[0] == "rot"
        if k == "unklar":
            ein = self.erkennung(a).get("einordnung") if a.status != ak.ERLEDIGT else a.einordnung
            return bool(ein) and ein.get("sicherheit") == aa.UNKLAR
        if k == "fehlt":
            return a.status != ak.ERLEDIGT and bool(self.erkennung(a)["fehlt"])
        if k == "doppelt":
            return any(e.get("zweiter_weg") for e in a.verlauf)
        if k == "anhaenge":
            return _neue_anhaenge(a)
        if k == "nachfassen":
            return bool((self.nachfassen_stand(a) or {}).get("faellig_ist"))
        return True

    def filter_aktiv(self):
        """Namen der Filter, die nicht auf Vorgabe stehen (Schnellfilter, Suche, Auswahlfelder)."""
        out = [b.text() for b in getattr(self, "schnell", {}).values() if b.isChecked()]
        if self.suche.text().strip():
            out.append("Suche")
        for box in (self.filter_bearbeiter, self.filter_prio, self.filter_daten, getattr(self, "filter_art", None),
                    getattr(self, "filter_kunde", None)):
            if box is not None and box.currentIndex() > 0:
                out.append(box.currentText())
        return out

    def filter_zuruecksetzen(self):
        """Alle Filter auf Vorgabe (23.11.2026); Ordner und Zeitraum bleiben. Ergebnis: Anzahl sichtbarer Anfragen."""
        boxen = [self.filter_bearbeiter, self.filter_prio, self.filter_daten, getattr(self, "filter_art", None),
                 getattr(self, "filter_kunde", None)]
        knoepfe = list(getattr(self, "schnell", {}).values())
        for w in boxen + knoepfe + [self.suche]:
            if w is not None:
                w.blockSignals(True)
        try:
            for b in knoepfe:
                b.setChecked(False)
            for box in boxen:
                if box is not None:
                    box.setCurrentIndex(0)
            self.suche.clear()
        finally:
            for w in boxen + knoepfe + [self.suche]:
                if w is not None:
                    w.blockSignals(False)
        if self.ampel_filter:
            self.filter_setzen("")
        else:
            self.liste_fuellen()
        return self.tabelle.rowCount()

    def liste_fuellen(self):
        alt = self._gewaehlt
        liste = self.sichtbare()
        if hasattr(self, "k_filter_zurueck"):
            aktiv = self.filter_aktiv()
            self.k_filter_zurueck.setVisible(bool(aktiv))
            self.k_filter_zurueck.setToolTip("Aktiv: " + ", ".join(aktiv) + " – alles auf Vorgabe" if aktiv else "")
        self.tabelle.setSortingEnabled(False)
        self.tabelle.setRowCount(len(liste))
        kunden = {}
        try:
            kunden = {str(k.get("kundennr")): k.get("name") or "" for k in self.db.zeilen("kunden")}
        except Exception:
            pass
        ich = self.ich()                # je Liste einmal (19.11.2026: vorher je Zelle eine Abfrage)
        for r, a in enumerate(liste):
            arten = {}
            dateien = a.dateien()
            for d in dateien:
                if d["art"] != "mail":
                    arten[d["art"]] = arten.get(d["art"], 0) + 1
            mails = sum(1 for d in dateien if d["art"] == "mail")
            if not arten and mails:
                arten = {"mail": mails}
            anh = ", ".join(f"{n} {ak.ART_TEXT[x]}" for x, n in arten.items())
            if a.kennzeichen():         # ohne STEP (17.11.2026): Kennzeichen vorn
                anh = a.kennzeichen() + (f" · {anh}" if arten and "mail" not in arten else "")
            kunde = kunden.get(a.kunde) or a.stand.get("kunde_name") or a.kopf.get("kunde_name") or a.absender \
                or a.kopf.get("absender", "")
            if a.kunde_pruefen():       # Kunde nicht sicher erkannt (19.11.2026): auffällig, nie still falsch
                v = (a.zuordnung.get("vorschlaege") or [None])[0]
                kunde = "⚠ Kunde prüfen" + (f": {v['name']}?" if v else (f" ({kunde})" if kunde else ""))
            stufe, faellig, frist = self.ampeln.get(a.nr) or (None, None, "")
            status = ak.STATUS_TEXT[a.status]
            p = self.phase(a)
            if p not in (ph.NEU, ph.BEARBEITUNG, ph.ERLEDIGT, ph.NICHT_RELEVANT):
                status = ph.text(p)     # 20.11.2026: Phase statt nur „In Bearbeitung“
            if a.geloescht:
                status = "Gelöscht" + (f": {a.stand['geloescht_grund']}" if a.stand.get("geloescht_grund") else "")
            elif a.stand.get("zusammengefuehrt_in"):
                status = f"Zusammengeführt in {a.stand['zusammengefuehrt_in']}"
            elif a.aussortiert:
                status = f"Keine Anfrage: {a.aussortiert}"
            elif frist:                 # kurz in der Liste, ganz im Tooltip und rechts im Kopf
                status += " · " + ("überfällig" if stufe == "rot" and faellig else "heute" if stufe == "gelb"
                                   else f"bis {faellig:%d.%m.}" if faellig else frist)
            betreff = a.betreff
            ein = a.einordnung
            if ein and (ein.get("art") != aa.ANFRAGE or ein.get("sicherheit") == aa.UNKLAR):
                betreff = f"[{aa.KURZ.get(ein.get('art'), '?')}{'?' if ein.get('sicherheit') == aa.UNKLAR else ''}] " \
                    + betreff
            werte = (a.nr, kunde, betreff, _zeit(a.eingang), anh, ak.PRIORITAET_TEXT.get(a.prioritaet, ""),
                     a.bearbeiter or (f"für {a.stand['zugewiesen']}" if a.stand["zugewiesen"] else ""), status)
            meine = ak.ist_meine(a, ich)
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                it.setData(Qt.ItemDataRole.UserRole, a.nr)
                if c == 7:
                    it.setToolTip(f"Antwort {frist}" if frist else "")
                    it.setForeground(stil.farbe(AMPEL_FARBE[stufe] if stufe in ("rot", "gelb") else FARBE[a.status]))
                if c == 2 and (a.stand.get("vormessung") or ein):
                    it.setToolTip("\n".join(x for x in (
                        aa.kurztext(dict(ein, titel=aa.titel(ein.get("art"), ein.get("sachgebiete") or ())))
                        if ein else "", f"Vormessung: {a.stand['vormessung']}" if a.stand.get("vormessung") else "")
                        if x))
                if c == 5 and a.prioritaet in PRIO_FARBE:
                    it.setForeground(QColor(PRIO_FARBE[a.prioritaet]))
                if c == 0:
                    it.setToolTip(a.kopf.get("kurz", ""))
                if meine and c in (0, 2):
                    s = it.font()
                    s.setBold(True)
                    it.setFont(s)
                self.tabelle.setItem(r, c, it)
        zeile = next((r for r, a in enumerate(liste) if a.nr == alt), 0 if liste else -1)
        if zeile >= 0:
            self.tabelle.selectRow(zeile)
            self._gewaehlt = liste[zeile].nr
            self._zeigen(liste[zeile])        # gleiche Zeile wie vorher: kein Signal, Inhalt trotzdem neu
        else:
            self._gewaehlt = None
            self._zeigen(None)

    def _gewaehlt_neu(self):
        it = self.tabelle.selectedItems()
        nr = it[0].data(Qt.ItemDataRole.UserRole) if it else None
        self._gewaehlt = nr
        self._zeigen(self.akte())

    def akte(self, nr=None):
        nr = nr or self._gewaehlt
        return next((a for a in self.akten if a.nr == nr), None)

    def waehlen(self, nr):
        """Anfrage wählen (Tests, Links): Ordner passend umschalten."""
        a = self.akte(nr)
        if a is None:
            return None
        ziel = ak.GELOESCHT if a.geloescht else a.status
        if self.ordner not in (ziel, None) and not (self.ordner == "meine" and ak.ist_meine(a, self.ich())):
            self.ordner_waehlen(ziel)
        self._gewaehlt = nr
        self.liste_fuellen()
        return a

    def ordner_waehlen(self, key):
        self.ordner = key
        self.ampel_filter = ""
        self.filter_zeile.setVisible(False)
        self.zaehler[key].setChecked(True)
        self.liste_fuellen()

    # ------------------------------------------------------------------ Anzeige
    def _mailtext(self, a):
        """Ganzer Text der ersten Mail der Akte (gelesen mit mail.py), sonst der Kurztext."""
        from . import mail
        if a.nr in self._mailtexte:
            return self._mailtexte[a.nr]
        text = ""
        for d in a.dateien():
            if d["art"] == "mail" and d["pfad"].exists():
                m = mail.lesen(d["pfad"])
                if m is not None:
                    text = m.text
                    break
        self._mailtexte[a.nr] = text or a.kopf.get("kurz", "")
        return self._mailtexte[a.nr]

    def _zeigen(self, a):
        self._knoepfe(a)
        if a is None:
            self.kopf.setText("<i>Keine Anfrage gewählt</i>")
            self.inhalt.clear()
            self.dokumente.fuellen(None, None)
            self.chronik.clear()
            return
        e = html.escape
        s = a.stand
        absender = a.absender if a.stand.get("absender_korr") else a.kopf.get("absender_name") or ""
        adresse = a.absender_adresse
        zeilen = [f"<b style='font-size:14px'>{e(a.betreff)}</b>",
                  f"{e(a.nr)} · <span style='color:{FARBE[a.status]}'>{ak.STATUS_TEXT[a.status]}</span>"
                  + (f" · {e(ak.PRIORITAET_TEXT[a.prioritaet])}" if a.prioritaet != "normal" else ""),
                  (f"Von {e(absender)} &lt;{e(adresse)}&gt;" if adresse else (f"Von {e(absender)}" if absender else
                   (f"Interne Anfrage von {e(a.zuordnung['anfragender_intern'].get('name') or '')}"
                    if a.zuordnung.get("anfragender_intern") else
                    "Kunde nicht erkennbar, bitte selbst wählen" if a.kopf.get("weitergeleitet") else "")))
                  + (f" · intern {e(a.kopf['weitergeleitet'])}" if a.kopf.get("weitergeleitet") else ""),
                  f"Eingang {_zeit(a.eingang)}"
                  + (f" · übernommen {ak._zeit_text(s['uebernommen_am'])} von {e(a.bearbeiter)}" if a.bearbeiter
                     else (f" · vorgeschlagen für {e(s['zugewiesen'])}" if s["zugewiesen"] else ""))
                  + (f" · erledigt {ak._zeit_text(s['erledigt_am'])}" if s["erledigt_am"] else "")]
        stufe, _f, frist = self.ampeln.get(a.nr) or (None, None, "")
        if frist and not s.get("rueckfrage"):
            zeilen.append(f"<span style='color:{AMPEL_FARBE.get(stufe, '#666')}'>● Antwort {e(frist)}</span>")
        if a.geloescht:
            zeilen.append(f"<b style='color:#B42318'>Gelöscht</b> {ak._zeit_text(s['geloescht'])} von "
                          f"{e(s.get('geloescht_von') or '?')}" + (f": {e(s['geloescht_grund'])}"
                                                                   if s.get("geloescht_grund") else "")
                          + " · „Wiederherstellen“ holt sie zurück")
        if a.aussortiert:
            zeilen.append(f"<b>Keine Anfrage:</b> {e(a.aussortiert)}")
        if a.kennzeichen() and not a.aussortiert:
            zeilen.append(f"<span style='color:#A66A00'>{e(a.kennzeichen())}</span> · „Kalkulieren“ legt ein Angebot "
                          "ohne Positionen an (Kunde, Anfrage-Nr. und Termin aus der Mail)")
        if s.get("rueckfrage"):
            nf = self.nachfassen_stand(a)
            if nf and nf["faellig_ist"]:      # 23.11.2026: nachfassen
                zeilen.append(f"<span style='color:{AMPEL_FARBE['rot']}'>● {e(nf['text'])}</span> · "
                              "<a href='nachfassen:'>Erinnerung …</a> · <a href='antwort:'>Antwort erhalten</a>")
            else:
                zeilen.append(f"<span style='color:{AMPEL_FARBE['gelb']}'>● Rückfrage am "
                              f"{ak._zeit_text(s['rueckfrage'])} · wartet auf Kunde</span>"
                              + (f" ({e(nf['text'])})" if nf else "") + " · <a href='antwort:'>Antwort erhalten</a>")
        elif a.status != ak.ERLEDIGT:
            try:
                gl = anf.geliefert_text(anf.geliefert(a, self.erkennung(a)["fehlt"]))
            except Exception:           # noqa: BLE001 – Hilfe, nie ein Fehler
                gl = ""
            if gl:
                zeilen.append(f"<span style='color:#2F6FB3'>● {e(gl)}</span>")
        if a.status != ak.ERLEDIGT and not a.aussortiert:
            try:
                p, teile = self.reihenfolge(a, voll=True)
            except Exception:           # noqa: BLE001
                p, teile = None, []
            if p is not None and teile:
                zeilen.append(f"<span style='color:#666'>Wichtig: {p} Punkte – {e(ar.text(teile))}</span>")
        self.kopf.setText("<br>".join(z for z in zeilen if z))
        teile = []
        n, grund = ak.aussortier_vorschlag(self.akten, a)
        if n:
            teile.append(f"<p style='color:#A66A00'>Vom selben Absender wurden schon {n} Mails als „Keine Anfrage“ "
                         f"aussortiert ({e(grund)}). <a href='aussortieren:{e(grund)}'>Auch diese aussortieren</a></p>")
        if a.stand.get("zusammengefuehrt_in"):
            z = a.stand["zusammengefuehrt_in"]
            teile.append(f"<p style='color:#2F6FB3'><b>Zusammengeführt in <a href='anfrage:{e(z)}'>{e(z)}</a></b>"
                         " – Mails und Dokumente stehen dort.</p>")
        try:
            teile.append(adok.herkunft_html(a, self._kunden_namen()))
            vs = sa.vorschlaege(self.akten, a, self._mailtext(a)) if a.status != ak.ERLEDIGT else []
        except Exception:               # noqa: BLE001 – Anzeige, nie ein Fehler
            vs = []
        if vs:
            teile.append("<p style='color:#A66A00'><b>Gehört vielleicht zu:</b> " + "; ".join(
                f"<a href='anfrage:{e(b.nr)}'>{e(b.nr)}</a> {e(b.betreff)} ({e(g)}) · "
                f"<a href='zusammen:{e(b.nr)}'>Zusammenführen …</a>" for b, g in vs) + "</p>")
        if a.status != ak.ERLEDIGT:
            teile += self._erkannt_html(a)
        if s.get("vormessung"):
            teile.append(f"<p><b>Vormessung:</b> {e(s['vormessung'])}</p>")
        for v in s.get("versendet") or ():
            teile.append(f"<p><b>Angebot per E-Mail:</b> {e(v['angebot'])} am {ak._zeit_text(v['zeit'])}"
                         + (f" an {e(v['an'])}" if v.get("an") else "") + "</p>")
        if s["stand"]:
            teile.append(f"<p><b>Bearbeitungsstand:</b> {e(s['stand'])}</p>")
        if s["angebote"]:
            teile.append("<p><b>Angebote:</b> " + ", ".join(
                f"<a href='angebot:{e(n)}'>{e(n)}</a>{e(self._angebot_text(n))}" for n in s["angebote"]) + "</p>")
        dateien = a.dateien()
        if dateien:
            li = []
            rollen = {x["datei"]: x for x in self.anhaenge(a)}
            for d in dateien:
                gr = f"{(d.get('groesse') or 0) / 1024:.0f} KB"
                x = rollen.get(d.get("datei", d["name"]))
                w = f" <span style='color:#B42318'>{e(d['warnung'])}</span>" if d["warnung"] else ""
                if d.get("aus_mail"):
                    w += " <span style='color:#666'>(Anhang der Mail)</span>"
                if d["viren"] == vp.SAUBER:
                    w += " <span style='color:#2F7D4F'>✓ geprüft</span>"
                elif d["viren"] == vp.FREIGEGEBEN:
                    w += " <span style='color:#666'>(Sperre aufgehoben)</span>"
                elif d["viren"] is None and not d.get("gesperrt") and self._viren_exe():
                    w += " <span style='color:#666'>(wird auf Viren geprüft …)</span>"
                if d["viren"] == vp.FUND:
                    w += f" <a href='freigeben:{e(d.get('datei', d['name']))}'>Sperre aufheben …</a>"
                if d.get("gesperrt"):
                    li.append(f"<li>{e(d['name'])}{w}</li>")
                    continue
                rolle = ""
                if x is not None:       # 20.11.2026 (anhang_analyse): Rolle, Revision, neuer Stand, Hinweise
                    rolle = f"{x['rolle']}" + (f", Rev. {x['revision']}" if x["revision"] else "")
                    if x["neuer_stand_von"]:
                        w += f" <span style='color:#A66A00'>neuer Stand von {e(x['neuer_stand_von'])}</span>"
                    if x["gruppe"]:
                        w += " <span style='color:#666'>(STEP und Zeichnung zum selben Teil)</span>"
                    for h in x["hinweise"]:
                        w += f" <span style='color:#B42318'>{e(h)}</span>"
                li.append(f"<li><a href='datei:{e(d.get('datei', d['name']))}'>{e(d['name'])}</a> "
                          f"<span style='color:#666'>{e(rolle) + ', ' if rolle else ''}{ak.ART_TEXT[d['art']]}, "
                          f"{gr}</span>{w}</li>")
            teile.append(f"<p><b>Anhänge ({len(dateien)}):</b></p><ul>{''.join(li)}</ul>"
                         "<p><a href='ordner:'>Ordner der Anfrage öffnen</a></p>")
        text = self._mailtext(a)
        if text:
            teile.append("<p><b>Nachricht:</b></p><p>" + e(text).replace("\n", "<br>") + "</p>")
        if s["notizen"]:
            teile.append("<p><b>Interne Notizen:</b></p><ul>" + "".join(
                f"<li>{ak._zeit_text(n['zeit'])} {e(n['kuerzel'])}: {e(n['text'])}</li>" for n in s["notizen"])
                + "</ul>")
        verlauf = sorted(a.verlauf, key=lambda x: (x.get("zeit", ""), x.get("kuerzel", ""), x.get("nr", 0)))
        teile.append("<p><b>Verlauf:</b></p><p style='color:#555'>"
                     + "<br>".join(e(ak.verlauf_text(x)) for x in verlauf) + "</p>")
        self.inhalt.setHtml("".join(teile))
        try:
            self.dokumente.fuellen(a, self.ablage().wurzel)
            self.chronik.setHtml(adok.chronik_html(a))
        except Exception as fehler:               # noqa: BLE001
            protokoll.warnung(f"Anfragen: Chronik nicht angezeigt ({type(fehler).__name__}: {fehler})")

    def _kunden_namen(self):
        try:
            return {str(k.get("kundennr")): k.get("name") or "" for k in self.db.zeilen("kunden")}
        except Exception:               # noqa: BLE001
            return {}

    def _angebot_text(self, nummer):
        """Summe netto und Stand des Angebots, z. B. „ (1.234,50 € netto, versendet)“."""
        try:
            z = self.db.con.execute("SELECT vk_netto, stand FROM angebote WHERE nummer=? ORDER BY id DESC LIMIT 1",
                                    (nummer,)).fetchone()
        except Exception:
            return ""
        if not z:
            return ""
        teile = []
        if z[0]:
            teile.append(f"{z[0]:,.2f} € netto".replace(",", "X").replace(".", ",").replace("X", "."))
        if z[1]:
            teile.append(str(z[1]))
        return f" ({', '.join(teile)})" if teile else ""

    def _knoepfe(self, a):
        from . import admin_schutz
        lesen = bool(getattr(self.db, "nur_lesen", False))
        st = a.status if a else None
        ich = self.ich()
        admin = admin_schutz.ist_admin(self.db)
        eigen = bool(a and (a.bearbeiter == ich or admin or (a.aussortiert and not a.bearbeiter)))
        self.k_uebernehmen.setVisible(st == ak.NEU)
        self.k_zuweisen.setVisible(st == ak.NEU)
        self.k_bearbeiter.setVisible(st == ak.BEARBEITUNG)
        self.k_kalkulieren.setVisible(st in (ak.NEU, ak.BEARBEITUNG))
        self.k_zurueck.setVisible(st == ak.BEARBEITUNG)
        self.k_erledigt.setVisible(st == ak.BEARBEITUNG)
        weg = bool(a and a.geloescht)
        self.k_wieder.setVisible(st == ak.ERLEDIGT and not weg)
        self.k_keine.setVisible(st == ak.NEU)
        self.k_loeschen.setVisible(bool(a) and not weg)
        self.k_herstellen.setVisible(weg)
        # Löschen: eine neue Anfrage jeder, sonst der Bearbeiter oder ein Admin; Wiederherstellen jeder
        self.k_loeschen.setEnabled(bool(a) and not lesen and (st == ak.NEU or eigen or not a.bearbeiter))
        self.k_herstellen.setEnabled(bool(a) and not lesen)
        self.k_rueckfrage.setVisible(st in (ak.NEU, ak.BEARBEITUNG))
        self.k_letztes.setVisible(st in (ak.NEU, ak.BEARBEITUNG) and bool(self.erkennung(a)["wiederholt"]))
        for b in (self.k_uebernehmen, self.k_zuweisen, self.k_kalkulieren, self.k_notiz, self.k_stand,
                  self.wahl_prio, self.wahl_bearbeiter, self.k_keine, self.k_rueckfrage, self.k_letztes):
            b.setEnabled(bool(a) and not lesen)
        for b in (self.k_bearbeiter, self.k_zurueck, self.k_erledigt, self.k_wieder):
            b.setEnabled(bool(a) and not lesen and eigen)
        virus = bool(a) and a.virus()
        if virus:                       # Paket 3: Virus gefunden, erst klären
            self.k_kalkulieren.setEnabled(False)
            self.k_letztes.setEnabled(False)
        self.k_kalkulieren.setToolTip("Gesperrt: der Virenschutz hat in dieser Anfrage einen Virus gefunden" if virus
                                      else "Neues Angebot aus den Dateien der Anfrage, mit der Anfrage verknüpft")
        if a:
            self.wahl_prio.setCurrentIndex(max(0, self.wahl_prio.findData(a.prioritaet)))
            vorschlag = a.stand["zugewiesen"] or a.bearbeiter or ich
            i = self.wahl_bearbeiter.findData(vorschlag)
            if i >= 0:
                self.wahl_bearbeiter.setCurrentIndex(i)

    def _link(self, url):
        a = self.akte()
        t = url.toString()
        art, _, wert = t.partition(":")
        art = art.replace("-", "_")     # 23.11.2026: Links mit „_“ sind keine gültige QUrl (Kunde ändern ging nicht)
        if art == "angebot":
            self.angebot_oeffnen(wert)
        elif art == "anfrage":
            self.waehlen(wert)
        elif art == "zusammen" and a:
            self.zusammenfuehren([wert] if wert else None)
        elif art == "kunde_ok" and a:
            self.kunde_zuordnen(wert, bestaetigen=True)
        elif art == "angebot_hand" and a:
            self.angebot_hand()
        elif art == "kunde_profil" and wert:        # 23.11.2026: Kundenprofil der Kundenverwaltung
            kb = getattr(self.f, "kunden", None)
            if kb is not None and hasattr(kb, "oeffnen"):
                self.f.reiter.setCurrentWidget(kb)
                kb.oeffnen(wert)
        elif art == "kunde_wahl" and a:
            self.kunde_zuordnen()
        elif art == "kunde_neu" and a:
            self.kunde_neu_anlegen()
        elif art == "ansprechpartner" and a:
            self.ansprechpartner_setzen()
        elif art == "absender" and a:
            self.absender_korrigieren()
        elif art == "ohne_kunde" and a:
            self._ausfuehren(lambda abl, x: abl.zuordnung_aendern(x, "ohne_kunde"),
                             "Anfrage {nr}: intern, ohne Kunde.")
        elif art == "zuruecksetzen" and a:
            self._ausfuehren(lambda abl, x: abl.zuordnung_aendern(x, "zuruecksetzen"),
                             "Anfrage {nr}: Zuordnung zurückgesetzt (wie beim Eingang erkannt).")
        elif art == "aussortieren" and a:
            self.aussortieren(wert)
        elif art == "rueckfrage" and a:
            self.rueckfrage()
        elif art == "nachfassen" and a:
            self.nachfassen()
        elif art == "art" and a:
            self.art_aendern()
        elif art == "phase" and a:
            self.phase_setzen()
        elif art == "ki" and a:
            self.ki_fragen()
        elif art == "vorschlag" and a:
            self.zuweisen(wert)
        elif art == "nachtrag_gesehen" and a:
            self.nachtrag_gesehen()
        elif art == "antwort" and a:
            self.antwort_erhalten()
        elif art == "letztes" and a:
            self.aus_letztem_angebot()
        elif art == "freigeben" and a:
            self.sperre_aufheben(wert)
        elif art == "datei" and a:
            d = next((d for d in a.dateien() if d.get("datei", d["name"]) == wert), None)
            if d is None:
                return
            if d["viren"] is None and not d.get("gesperrt") and self._viren_exe():
                try:                    # noch nicht geprüft: vor dem Öffnen jetzt prüfen
                    self.ablage().viren_pruefen(a, exe=self._viren_exe(), ausfuehren=self.viren_ausfuehren)
                except OSError:
                    pass
                a = self.ablage().neu_lesen(a)
                d = next((x for x in a.dateien() if x.get("datei", x["name"]) == wert), d)
                if d.get("gesperrt"):
                    self._zeigen(a)
            if d["viren"] == vp.FUND:
                self.f.meldung(f"{d['name']}: Virus gefunden, die Datei ist gesperrt.", fehler=True)
                return
            if d.get("gesperrt") or ak.Path(d["name"]).suffix.lower() in ak.GEFAEHRLICH:
                self.f.meldung(f"{d['name']}: ausführbare Datei, wird aus Sicherheitsgründen nicht geöffnet.",
                               fehler=True)
                return
            self.vorschau(a, d)         # Vorschau im Programm (17.11.2026), extern nur über den Knopf
        elif art == "ordner" and a:
            self.f.datei_oeffnen(a.pfad / ak.DATEIEN)

    def vorschau(self, a, d):
        """Anhänge der Anfrage in der Vorschau im Programm zeigen, d zuerst; ◀ ▶ blättern durch die übrigen
        (gesperrte, mit Virus und ausführbare Dateien nie). Ergebnis: das Fenster."""
        from . import anhang_vorschau, step
        liste = []
        for x in a.dateien():
            if x.get("gesperrt") or x["viren"] == vp.FUND or ak.Path(x["name"]).suffix.lower() in ak.GEFAEHRLICH \
                    or not x["pfad"].is_file():
                continue
            liste.append(dict(name=x["name"], pfad=x["pfad"], hinweis=x.get("warnung") or ""))
        i = next((k for k, x in enumerate(liste) if x["pfad"] == d["pfad"]), 0)
        try:
            befehl = step.messprogramm(self.f.programmordner)
        except Exception:               # noqa: BLE001
            befehl = None
        args = self.messung_uebernehmen(a) if befehl else None
        alt = getattr(self, "_vorschau", None)
        if alt is not None:
            alt.close()
        self._vorschau = anhang_vorschau.fenster(self, liste, i, self._extern, befehl, args)
        if not self.f.stumm:
            self._vorschau.show()
            self._vorschau.raise_()
        return self._vorschau

    def _extern(self, pfad):
        """Knopf „Extern öffnen“ in der Vorschau: mit dem Programm, das Windows dafür vorsieht."""
        if not self.f.stumm and QMessageBox.question(
                self, "Extern öffnen", f"{ak.Path(pfad).name}\nmit dem zugehörigen Programm öffnen?\n\n"
                "Makros in Office-Dateien können dort laufen.") != QMessageBox.Yes:
            return
        self.f.datei_oeffnen(pfad)

    def angebot_oeffnen(self, nummer):
        z = self.db.con.execute("SELECT id FROM angebote WHERE nummer=? ORDER BY id DESC LIMIT 1",
                                (nummer,)).fetchone()
        if not z:
            self.f.meldung(f"Angebot {nummer} gibt es hier nicht (noch nicht abgeglichen?).", fehler=True)
            return None
        return self.f.angebot_oeffnen(z[0])

    # ------------------------------------------------------------------ Aktionen
    def _ausfuehren(self, tun, text=None):
        a = self.akte()
        if a is None:
            return None
        try:
            neu = tun(self.ablage(), a)
        except ak.SchonUebernommen as e:
            self.f.meldung(str(e), fehler=True)
            if not self.f.stumm:
                QMessageBox.information(self, "Anfrage übernehmen", str(e))
            self.neu_laden()
            return None
        except (ak.AblageFehler, OSError) as e:
            self.f.meldung(f"{a.nr}: {fehler_text(e) if isinstance(e, OSError) else e}", fehler=True)
            self.neu_laden()
            return None
        if text:
            self.f.meldung(text.format(nr=a.nr))
        self.neu_laden()
        if ol.an(self.db):
            QTimer.singleShot(1000, self.outlook_abrufen)        # Mail in Outlook gleich mitziehen
        return neu

    def hauptaktion(self):
        a = self.akte()
        if a and a.status == ak.NEU:
            return self.uebernehmen()
        if a and a.status == ak.BEARBEITUNG:
            return self.kalkulieren()
        return None

    def uebernehmen(self, bearbeiter=None):
        """Anfrage übernehmen (ein Klick): Bearbeiter, Zeit, Status In Bearbeitung; die Originale im Anfrage-Ordner
        kommen in dessen Unterordner .uebernommen."""
        bearbeiter = bearbeiter or self.wahl_bearbeiter.currentData() or self.ich()
        neu = self._ausfuehren(lambda abl, a: abl.uebernehmen(a, bearbeiter),
                               "Anfrage {nr} übernommen" + (f" für {bearbeiter}." if bearbeiter != self.ich() else "."))
        if neu is not None:
            self._eingang_ablegen(neu)
            self.ordner_waehlen(ak.BEARBEITUNG)
            self.waehlen(neu.nr)
        return neu

    def _eingang_ablegen(self, akte):
        karte = getattr(getattr(self.f, "start", None), "anfragen", None)
        if karte is None or not karte.ordner():
            return 0
        abl = self.ablage()
        n = 0
        for a in list(karte.anfragen):
            z = ak.akte_zu(abl, a)
            if z is not None and z.nr == akte.nr:
                n += ak.eingang_ablegen(a, karte.ordner(), akte.nr)
        if n:
            karte.neu_laden(erzwingen=True)
        return n

    def zuweisen(self, an=None):
        an = an if an is not None else (self.wahl_bearbeiter.currentData() or "")
        a = self.akte()
        v = self.vorschlag(a) if an and a is not None and not a.stand.get("zugewiesen") else None
        akte = self._ausfuehren(lambda abl, x: abl.zuweisen(x, an),
                                "Anfrage {nr} " + (f"für {an} vorgeschlagen." if an else "nicht mehr zugewiesen."))
        if akte is not None and v:      # 20.11.2026: Vorschlag angenommen oder anders entschieden (Auswertung)
            self._rueckmelden(a, "bearbeiter", v["kuerzel"], an, betreff=a.betreff, kunde=a.kunde or "",
                              sachgebiete=list((a.einordnung or {}).get("sachgebiete") or []))
        return akte

    def _rueckmelden(self, a, feld, auto, neu, **weitere):
        from . import anfrage_lernen
        try:
            anfrage_lernen.rueckmelden(self.ablage().wurzel, feld, auto or "", neu or "", a.nr, self.ich(),
                                       **weitere)
        except OSError as fehler:
            protokoll.warnung(f"Anfragen: Rückmeldung nicht gespeichert ({fehler})")

    def phase_setzen(self, phase=None):
        """Phase der gewählten Anfrage von Hand setzen ("" = wieder automatisch). Mit Phasen-Ordner wandert die Mail
        beim nächsten Abruf dorthin."""
        a = self.akte()
        if a is None:
            return None
        if phase is None:
            from PySide6.QtWidgets import QInputDialog
            wahl = ["Automatisch (aus Status, Rückfrage, Angebot, Auftrag)"] + [ph.text(x) for x in ph.VON_HAND]
            jetzt_ = a.stand.get("phase") or ""
            t, ok = QInputDialog.getItem(self, "Phase ändern", f"Phase von {a.nr}:", wahl,
                                         1 + ph.VON_HAND.index(jetzt_) if jetzt_ in ph.VON_HAND else 0, False)
            if not ok:
                return None
            phase = next((x for x in ph.VON_HAND if ph.text(x) == t), "")
        auto = ph.phase(a, self._ang_phase.get(tuple(a.stand.get("angebote") or ()), ""))
        akte = self._ausfuehren(lambda abl, x: abl.phase_setzen(x, phase),
                                "Anfrage {nr}: Phase " + (ph.text(phase) if phase else "automatisch") + ".")
        if akte is not None and phase:
            self._rueckmelden(a, "phase", auto, phase)
        return akte

    def erneut_verarbeiten(self):
        """Mails, deren Übernahme fehlschlug, beim nächsten Abruf sofort wieder versuchen (und gleich abrufen)."""
        try:
            n = ol.erneut_verarbeiten(self.ablage())
        except OSError as e:
            self.f.meldung(f"Outlook: {fehler_text(e)}", fehler=True)
            return 0
        self.f.meldung(f"{n} Mail(s) werden erneut verarbeitet.")
        if ol.an(self.db):
            self.outlook_abrufen(immer=True, warten=self.f.stumm)
        return n

    def ol_status_zeigen(self):
        try:
            s = ol.abruf_status(self.ablage())
        except OSError:
            s = {}
        if not s and not ol.an(self.db):
            self.ol_status.setVisible(False)
            return ""
        t = html.escape(ol.status_text(s))
        if s.get("wartet") or not s.get("outlook_erreicht", True):
            t += " · <a href='erneut:'>Erneut verarbeiten</a>"
        farbe = "#B42318" if not s.get("outlook_erreicht", True) else ("#A66A00" if s.get("fehler") else "#666")
        self.ol_status.setText(f"<span style='color:{stil.farbe(farbe).name()}'>{t}</span>")
        self.ol_status.setVisible(True)
        return t

    def bearbeiter_aendern(self, an=None):
        an = an or self.wahl_bearbeiter.currentData()
        return self._ausfuehren(lambda abl, a: abl.bearbeiter_aendern(a, an), f"Anfrage {{nr}}: Bearbeiter {an}.")

    def prioritaet(self, wert):
        return self._ausfuehren(lambda abl, a: abl.prioritaet(a, wert))

    def notiz(self, text=None):
        if text is None:
            if self.f.stumm:
                return None
            text, gut = QInputDialog.getMultiLineText(self, "Interne Notiz", "Notiz (sehen alle Kollegen):")
            if not gut or not text.strip():
                return None
        return self._ausfuehren(lambda abl, a: abl.notiz(a, text), "Notiz zu {nr} gespeichert.")

    def bearbeitungsstand(self, text=None):
        a = self.akte()
        if text is None:
            if self.f.stumm or a is None:
                return None
            text, gut = QInputDialog.getText(self, "Bearbeitungsstand", "Stand (z. B. „Rückfrage Werkstoff offen“):",
                                             text=a.stand["stand"])
            if not gut:
                return None
        return self._ausfuehren(lambda abl, a: abl.bearbeitungsstand(a, text))

    def erledigen(self):
        return self._ausfuehren(lambda abl, a: abl.erledigen(a), "Anfrage {nr} erledigt.")

    def wieder_oeffnen(self):
        return self._ausfuehren(lambda abl, a: abl.wieder_oeffnen(a), "Anfrage {nr} wieder in Bearbeitung.")

    def zurueckgeben(self):
        return self._ausfuehren(lambda abl, a: abl.zurueckgeben(a), "Anfrage {nr} zurück nach Neu.")

    def aussortieren(self, grund=None):
        """Keine Anfrage (Paket 5): mit Grund nach „Keine Anfrage“ (Status Erledigt, in Outlook nach Erledigt)."""
        a = self.akte()
        if a is None:
            return None
        if grund is None:
            if self.f.stumm:
                return None
            vorschlag = ak.aussortier_vorschlag(self.akten, a)[1]
            gruende = list(ak.AUSSORTIER_GRUENDE)
            grund, gut = QInputDialog.getItem(self, "Keine Anfrage", f"{a.betreff}\n\nGrund (sehen alle Kollegen; "
                                              "die Mail bleibt erhalten):", gruende,
                                              gruende.index(vorschlag) if vorschlag in gruende else 0, True)
            if not gut or not grund.strip():
                return None
        neu = self._ausfuehren(lambda abl, a: abl.aussortieren(a, grund),
                               "Anfrage {nr} als „Keine Anfrage“ aussortiert (" + grund + ").")
        if neu is not None:
            self._eingang_ablegen(neu)      # 24.11.2026: Originale aus dem Anfrage-Ordner weglegen
        return neu

    def loeschen(self, grund=None):
        """Anfrage löschen (Patrick 24.11.2026): nach Rückfrage in den Ordner „Gelöscht“; die Originale im
        Anfrage-Ordner kommen weg (nach .uebernommen/<Nr>), damit sie nicht wieder als neu erscheinen."""
        a = self.akte()
        if a is None:
            return None
        if grund is None:
            if self.f.stumm:
                return None
            extra = (f"\n\nVerknüpfte Angebote bleiben erhalten: {', '.join(a.stand['angebote'])}"
                     if a.stand.get("angebote") else "")
            grund, gut = QInputDialog.getText(
                self, "Anfrage löschen", f"{a.nr}: {a.betreff}\n\nDie Anfrage kommt in den Ordner „Gelöscht“ (für "
                "alle Kollegen), dort kann sie wiederhergestellt werden." + extra + "\n\nGrund (freiwillig):")
            if not gut:
                return None
        neu = self._ausfuehren(lambda abl, x: abl.loeschen(x, grund or ""), "Anfrage {nr} gelöscht (Ordner „Gelöscht“).")
        if neu is not None:
            self._eingang_ablegen(neu)
        return neu

    def wiederherstellen(self):
        neu = self._ausfuehren(lambda abl, a: abl.wiederherstellen(a), "Anfrage {nr} wiederhergestellt.")
        if neu is not None:
            self.ordner_waehlen(neu.status)
            self.waehlen(neu.nr)
        return neu

    def messung_uebernehmen(self, a):
        """Vormessung der Akte (auch von einem anderen Platz, Akte/_messung) in den eigenen STEP-Zwischenspeicher
        übernehmen, damit Kalkulieren und 3D-Vorschau nicht neu messen (Patrick 18.11.2026). Ergebnis: Messargumente
        für die 3D-Vorschau oder None."""
        from . import anfrage_vorab
        try:
            args = anfrage_vorab.vorschau_argumente(self.db, a.kunde or None)
            anfrage_vorab.messung_uebernehmen(a.pfad / anfrage_vorab.MESSUNG, anfrage_vorab.cache_aus(args))
            return args
        except Exception:               # noqa: BLE001 – ohne Übernahme wird eben gemessen
            return None

    def kalkulieren(self, kundennr=None):
        """Neues Angebot aus den Dateien der Anfrage (Arbeitskopie, die Akte bleibt vollständig): derselbe Weg wie
        „Öffnen“ in der Karte (auspacken, Formular und Mail lesen, Prüfdialog, Angebotsordner). Eine neue Anfrage wird
        dabei übernommen. Danach sind Anfrage und Angebot verknüpft. kundennr: ohne Kundenwahl (Tests).
        Ohne STEP (Patrick 17.11.2026, F2 a) entsteht ein Angebot ohne Positionen; hat der Kunde zu einem solchen
        Angebot die STEP nachgereicht (F4 a), liest „Kalkulieren“ sie in dieses Angebot statt in ein neues.
        Ergebnis: Angebotsseite oder None."""
        import shutil
        from . import anfrage_ohne_step as aos
        a = self.akte()
        if a is None:
            return None
        if a.virus():
            self.f.meldung(f"{a.nr}: Virus gefunden, Kalkulieren gesperrt. Bitte erst klären.", fehler=True)
            return None
        if a.status == ak.NEU:
            a = self.uebernehmen(self.ich())
            if a is None:
                return None
        for angebot_id in aos.offene_angebote(self.db, a):       # nachgereichte STEP: ins vorhandene Angebot
            if aos.nachgereicht(self.db, angebot_id):
                self.f.angebot_oeffnen(angebot_id)
                seite = getattr(self.f, "offen", {}).get(angebot_id)
                if seite is not None and hasattr(seite, "nachgereichte_step_einlesen"):
                    seite.nachgereichte_step_einlesen()
                    self.neu_laden()
                    return seite
        karte = getattr(getattr(self.f, "start", None), "anfragen", None)
        if karte is None:
            return None
        self.messung_uebernehmen(a)
        try:
            arbeit = ak.arbeitskopie(a)
        except ak.AblageFehler as e:
            self.f.meldung(f"{a.nr}: {e}", fehler=True)
            return None
        except OSError as e:
            self.f.meldung(f"Dateien der Anfrage nicht kopierbar: {fehler_text(e)}", fehler=True)
            return None
        try:
            seite = karte.oeffnen([arbeit], kundennr=kundennr)
        finally:
            shutil.rmtree(arbeit.ordner, ignore_errors=True)
        if seite is not None:           # auch Anfragen aus Outlook (Schlüssel = Nachrichten-ID) sicher verknüpfen
            try:
                nummer = seite.kopf.get("nummer") or ""
                if nummer:
                    self.ablage().angebot_verknuepfen(self.ablage().neu_lesen(a), nummer)
                if a.nr not in ak.akten_zum_angebot(self.db, seite.id):
                    alt = ak.akten_zum_angebot(self.db, seite.id)
                    self.db.zusatz_setzen(seite.id, "anfrage_akte", alt + [a.nr] if alt else a.nr)
            except Exception:           # noqa: BLE001
                pass
        self.neu_laden()
        if seite is not None:
            self.waehlen(a.nr)
        return seite

    # ------------------------------------------------------------------ Paket 6: Erkannt, Rückfrage, Wiederholteile
    def erkennung(self, a):
        """{werte, fehlt, wiederholt} der Akte (zwischengespeichert bis zum nächsten Neu-Laden)."""
        from . import anfrage_erkennung as ae
        if a is None:
            return dict(werte=[], fehlt=[], wiederholt=[], einordnung=None, technik=[])
        if a.nr not in self._erkannt:
            text = self._mailtext(a)
            try:
                werte = ae.erkannt(self.db, a, text)
                fehlt = ae.fehlt(werte, a, text)
                wieder = ae.wiederholt(self.db, self.akten, a, text) if a.status != ak.ERLEDIGT else []
            except Exception:           # noqa: BLE001 – Hilfe, nie ein Fehler
                werte, fehlt, wieder = [], [], []
            ein, technik = a.einordnung, []
            try:                        # 20.11.2026: Mail-Art (ältere Akten: jetzt erkennen) und technische Werte
                if not ein:
                    namen = [d["name"] for d in a.dateien()]
                    ein = aa.kompakt(aa.einordnen(text, a.betreff, namen))
                if not a.stand.get("art_korr"):     # freigegebenes gelerntes Modell (nur unsichere Fälle)
                    ein = al.anwenden(self._modell(), ein, text, a.betreff)
                    ein = al.sachgebiete_anwenden(self._modell("sachgebiet"), ein, text, a.betreff)
                technik = aa.technik(text)
            except Exception as fehler:     # noqa: BLE001 – Hilfe, nie ein Fehler
                protokoll.warnung(f"Anfragen: Mail-Art/Werte nicht erkannt ({type(fehler).__name__}: {fehler})")
            nach = []
            try:                        # 20.11.2026: was Nachträge anders sagen (nur Anzeige)
                mails = self._mails(a)
                if len(mails) > 1:
                    nach = an.nachtraege(mails)
            except Exception as fehler:     # noqa: BLE001 – Hilfe, nie ein Fehler
                protokoll.warnung(f"Anfragen: Nachträge nicht verglichen ({type(fehler).__name__}: {fehler})")
            self._erkannt[a.nr] = dict(werte=werte, fehlt=fehlt, wiederholt=wieder, einordnung=ein, technik=technik,
                                       nachtraege=nach)
        return self._erkannt[a.nr]

    def _erkannt_html(self, a):
        from . import anfrage_erkennung as ae
        e = html.escape
        erk = self.erkennung(a)
        teile = []
        p = self.phase(a)               # 20.11.2026 (Plan K6): Phase bis zum Auftrag, von Hand änderbar
        hand = a.stand.get("phase") or ""
        teile.append(f"<p><b>Phase:</b> {e(ph.text(p))}"
                     + (f" <span style='color:#666'>(von Hand, {e(a.stand.get('phase_von') or '?')})</span>"
                        if hand and hand == p else " <span style='color:#666'>(automatisch)</span>")
                     + ("" if p in (ph.ERLEDIGT, ph.NICHT_RELEVANT) else " · <a href='phase:'>ändern …</a>")
                     + "</p>")
        v = self.vorschlag(a) if not a.stand.get("zugewiesen") else None
        if v:                           # 20.11.2026 (Plan K7): Vorschlag mit Gründen, zugewiesen wird nur auf Klick
            teile.append(f"<p><b>Vorschlag Bearbeiter:</b> {e(v['kuerzel'])}"
                         + (" (sicher)" if v["sicher"] else "")
                         + f" · <a href='vorschlag:{e(v['kuerzel'])}'>zuweisen</a>"
                         + f"<br><span style='color:#666'>{e('; '.join(v['gruende'][:4]))}</span></p>")
        nach = erk.get("nachtraege") or []
        if nach:                        # 20.11.2026: neue Angaben aus Nachträgen nie still übernehmen
            neu = len(nach) > a.stand.get("nachtrag_gesehen", 0)
            zeilen = "".join(
                f"<tr><td><b>{e(x['titel'])}</b>&nbsp;</td><td>{e(str(x['alt']) or '–')} → <b>{e(str(x['neu']))}</b>"
                f"&nbsp;</td><td style='color:#666'>{e(x['mail'])} {e(x['datum'])}: „{e(x['fundstelle'])}“</td></tr>"
                for x in nach)
            farbe_n = stil.farbe("#A66A00" if neu else "#666").name()
            teile.append(f"<p style='color:{farbe_n}'><b>Geänderte Angaben aus Nachträgen</b> (nichts wurde "
                         "automatisch übernommen" + ("; Angebot bitte prüfen" if a.stand.get("angebote") else "")
                         + ")" + (" · <a href='nachtrag-gesehen:'>Gesehen</a>" if neu else " · gesehen")
                         + f"</p><table>{zeilen}</table>")
        ein = erk.get("einordnung")
        if ein:                         # 20.11.2026: was für eine Mail, mit Gründen und Ändern
            farbe_s = {aa.SICHER_ART: "#2F7D4F", aa.WAHRSCHEINLICH: "#A66A00", aa.UNKLAR: "#B42318",
                       "bestätigt": "#2F7D4F"}.get(ein.get("sicherheit"), "#666")
            sg = ", ".join(aa.SACHGEBIETE.get(x, x) for x in ein.get("sachgebiete") or ())
            gruende = "; ".join(f"{g}" + (f" („{z}“)" if z else "") for g, z in ein.get("gruende") or ())
            if ein.get("sicherheit") == "bestätigt":
                gruende = f"von Hand gesetzt ({ein.get('von') or '?'})"
            teile.append(
                f"<p><b>Mail-Art:</b> {e(aa.titel(ein.get('art'), ein.get('sachgebiete') or ()))} "
                f"<span style='color:{stil.farbe(farbe_s).name()}'>({e(ein.get('sicherheit') or '?')})</span>"
                + (f" · <b>Sachgebiet:</b> {e(sg)}" if sg else "")
                + " · <a href='art:'>ändern …</a>"
                + (f"<br><span style='color:#666'>{e(gruende)}</span>" if gruende else "") + "</p>")
            if ein.get("art") == aa.WERBUNG and not a.aussortiert and a.status != ak.ERLEDIGT:
                teile.append("<p style='color:#A66A00'>Sieht nach Werbung aus. "
                             "<a href='aussortieren:Werbung'>Als „Keine Anfrage“ aussortieren</a></p>")
        if ki.an(self.db) or erk.get("ki"):     # 20.11.2026 (Plan K10): lokale KI, Vorgabe aus
            zeilen = "".join(
                f"<tr><td><b>{e(w['titel'])}</b>&nbsp;</td><td>{e(str(w['wert']))}&nbsp;</td>"
                f"<td style='color:{stil.farbe('#A66A00').name()}'>KI lokal · prüfen&nbsp;</td>"
                f"<td style='color:#666'>„{e(w['fundstelle'])}“</td></tr>" for w in erk.get("ki") or ())
            teile.append("<p><b>Lokale KI</b> <span style='color:#666'>(eigener Rechner, nur Werte aus dem Text)</span>"
                         + (" · <a href='ki:'>fragen …</a>" if ki.an(self.db) else "") + "</p>"
                         + (f"<table>{zeilen}</table>" if zeilen else ""))
        if erk.get("technik"):
            farbe_t = {"sicher": stil.farbe("#2F7D4F").name(), "prüfen": stil.farbe("#A66A00").name()}
            zeilen = "".join(
                f"<tr><td><b>{e(w['titel'])}</b>&nbsp;</td><td>{e(str(w['wert']))}&nbsp;</td>"
                f"<td style='color:{farbe_t.get(w['sicherheit'], '#666')}'>{e(w['sicherheit'])}&nbsp;</td>"
                f"<td style='color:#666'>„{e(w['fundstelle'])}“</td></tr>" for w in erk["technik"])
            teile.append("<p><b>Technische Angaben</b> <span style='color:#666'>(nur gelesen, nichts erfunden; "
                         "jede mit Fundstelle)</span></p>" + f"<table>{zeilen}</table>")
        if erk["werte"] or erk["fehlt"]:
            farbe = {"sicher": stil.farbe("#2F7D4F").name(), "prüfen": stil.farbe("#A66A00").name(),
                     "unsicher": stil.farbe("#B42318").name()}
            zeilen = "".join(
                f"<tr><td><b>{e(w['titel'])}</b>&nbsp;</td><td>{e(str(w['wert']))}&nbsp;</td>"
                f"<td style='color:{farbe.get(w['sicherheit'], '#666')}'>{e(w['sicherheit'])}&nbsp;</td>"
                f"<td style='color:#666'>„{e(w['fundstelle'])}“</td></tr>" for w in erk["werte"])
            teile.append("<p><b>Erkannt</b> <span style='color:#666'>(wird erst beim Kalkulieren im Prüfdialog "
                         "übernommen)</span></p>" + (f"<table>{zeilen}</table>" if zeilen else ""))
            if erk["fehlt"]:
                teile.append(f"<p style='color:{stil.farbe('#B42318').name()}'><b>Fehlt:</b> "
                             + e(", ".join(ae.fehlt_text(erk["fehlt"])))
                             + ("" if a.stand.get("rueckfrage") else " · <a href='rueckfrage:'>Rückfrage …</a>")
                             + "</p>")
        if erk["wiederholt"]:
            li = []
            for w in erk["wiederholt"]:
                preis = ae.euro(w["preis"])
                preis = (f", {preis}/Stück" if w["art"] == "artikel" else f", {preis} netto") if preis else ""
                li.append(f"<li>{e(w['was'])}: Angebot <a href='angebot:{e(w['nummer'])}'>{e(w['nummer'])}</a> vom "
                          f"{e(_datum_text(w['datum']))}{e(preis)}"
                          + (f" ({e(w['vorgang'])})" if w.get("vorgang") else "") + "</li>")
            teile.append("<p><b>Wiederholteile:</b> <a href='letztes:'>Aus letztem Angebot</a></p><ul>"
                         + "".join(li) + "</ul>")
        return teile

    def _mails(self, a):
        """[(Name, Datum, Text)] aller Mails der Akte in Eingangsreihenfolge (Kopf zuerst, dann Nachträge)."""
        from . import mail
        out = []
        for d in a.dateien():
            if d["art"] != "mail" or d.get("gesperrt") or not d["pfad"].is_file():
                continue
            m = mail.lesen(d["pfad"])
            if m is None:
                continue
            datum = m.datum.strftime("%d.%m. %H:%M") if m.datum else ""
            out.append((d["name"], datum, m.text or ""))
        return out

    def anhaenge(self, a):
        """Rolle, Revision und Hinweise je Datei (anhang_analyse), zwischengespeichert je Akte und Dateistand (liest
        nur die ersten Bytes jeder Datei, nur wenn sich die Dateien geändert haben)."""
        if a is None:
            return []
        dateien = a.dateien()
        schl = (a.nr, tuple((d.get("datei", d["name"]), d.get("groesse")) for d in dateien))
        if self._anhang_cache.get(a.nr, (None,))[0] != schl:
            try:
                liste = an.analyse(dateien)
            except Exception as fehler:     # noqa: BLE001 – Hilfe, nie ein Fehler
                protokoll.warnung(f"Anfragen: Anhänge nicht ausgewertet ({type(fehler).__name__}: {fehler})")
                liste = []
            self._anhang_cache[a.nr] = (schl, liste)
        return self._anhang_cache[a.nr][1]

    def nachtrag_gesehen(self):
        a = self.akte()
        if a is None:
            return None
        nach = self.erkennung(a).get("nachtraege") or []
        return self._ausfuehren(lambda abl, x: abl.nachtrag_gesehen(x, nach),
                                "Anfrage {nr}: Änderungen aus Nachträgen gesehen.")

    def art_aendern(self, art=None, sachgebiete=None):
        """Mail-Art und Sachgebiet der gewählten Anfrage von Hand setzen (Verlauf + Rückmeldung zum Lernen)."""
        from . import anfrage_lernen
        a = self.akte()
        if a is None:
            return None
        ein = self.erkennung(a).get("einordnung") or {}
        if art is None:
            from .anfragen_dokumente import ArtDialog
            d = ArtDialog(self, ein.get("art") or aa.ANFRAGE, ein.get("sachgebiete") or [])
            if not d.exec():
                return None
            art, sachgebiete = d.werte()
        auto = (a.kopf.get("einordnung") or ein or {})
        akte = self._ausfuehren(lambda abl, x: abl.art_aendern(x, art, sachgebiete or []),
                                "Anfrage {nr}: Mail-Art " + aa.ARTEN.get(art, art) + ".")
        if akte is None:
            return None
        try:
            anfrage_lernen.rueckmelden(self.ablage().wurzel, "art", auto.get("art", ""), art, a.nr, self.ich(),
                                       f"{a.betreff}\n{self._mailtext(a)}", sachgebiete_auto=auto.get("sachgebiete"),
                                       sachgebiete=list(sachgebiete or []))
        except OSError as fehler:
            protokoll.warnung(f"Anfragen: Rückmeldung nicht gespeichert ({fehler})")
        self._erkannt.pop(a.nr, None)
        return akte

    def _kunde(self, a):
        try:
            return next((k for k in self.db.zeilen("kunden") if str(k.get("kundennr")) == str(a.kunde)), {}) \
                if a.kunde else {}
        except Exception:               # noqa: BLE001
            return {}

    def _mail_pfad(self, a):
        mails = [d["pfad"] for d in a.dateien() if d["art"] == "mail" and not d.get("aus_mail")
                 and not d.get("gesperrt") and d["pfad"].is_file()]
        mails.sort(key=lambda p: p.suffix.lower() != ".msg")
        return mails[0] if mails else None

    # ------------------------------------------------------------------ Herkunft und Kunde (19.11.2026)
    def kunde_zuordnen(self, nr=None, bestaetigen=False, regel=False, domain=False, grund="", im_fenster=None):
        """Kunde von Hand zuordnen bzw. Vorschlag übernehmen (bestaetigen). Ohne nr: Fenster „Kunde aus der Anfrage“
        (erkannte Kunden, Suche, Gegenüberstellung Datenbank | Neue E-Mail, neuer Kunde, „Als Regel merken“; im_fenster(d): Tests bedienen es statt exec). regel/domain: Lernregel Adresse bzw. Domain → Kunde anlegen. Ergebnis: Akte oder None."""
        a = self.akte()
        if a is None:
            return None
        if nr is None:
            if self.f.stumm and im_fenster is None:
                return None
            # 23.11.2026 (MSG-Auftrag): erkannte Kunden mit Gründen, Gegenüberstellung Datenbank | Neue E-Mail,
            # nur angehakte Werte übernehmen, Ansprechpartner wählen/neu, neuer Kunde mit Dublettenprüfung
            from .anfrage_kunde_dialog import KundeAusMailDialog
            vorschlag = a.kunde or next((v["kundennr"] for v in a.zuordnung.get("vorschlaege") or []), None)
            d = KundeAusMailDialog(self, self.db, self._mail_daten(a) or {}, getattr(self.f, "kunden", None),
                                   vorschlag=vorschlag, adresse=a.absender_adresse or "", stumm=im_fenster is not None)
            self.kunde_fenster = d          # Tests: das offene Fenster
            if im_fenster is not None:      # Tests: Bedienung statt exec (Haken, Knöpfe)
                im_fenster(d)
            elif d.exec() != QDialog.Accepted:
                return None
            if not d.ergebnis:
                return None
            erg = d.ergebnis
            nr, regel, domain = erg["kundennr"], d.regel.isChecked(), d.domain.isChecked()
            grund = d.grund_text.text().strip() or ("neu angelegt" if erg.get("angelegt") else "")
            if erg.get("kunde") or erg.get("neu_person"):
                self.f.meldung(f"Kunde {nr}: " + ", ".join(erg.get("kunde") or [])
                               + (" · neuer Ansprechpartner" if erg.get("neu_person") else "") + " übernommen.")
            if erg.get("person"):
                p = next((x for x in kd.ansprechpartner(self.db, nr) if x["id"] == erg["person"]), None)
                if p:
                    self._ansprech_merken = kd.name_voll(p)
        name = self._kunden_namen().get(str(nr), "")
        r = None
        adresse = a.absender_adresse
        if (regel or domain) and adresse:
            try:
                r = mz.regel_anlegen(self.ablage().wurzel, "domain" if domain else "adresse",
                                     mz.mail._domain(adresse) if domain else adresse, nr, name, von=self.ich(),
                                     akte=a.nr)
            except (OSError, ValueError) as e:
                self.f.meldung(f"Regel nicht gespeichert: {e}", fehler=True)
        feld = "bestaetigt" if bestaetigen and not grund else "kunde"
        auto = str((a.kopf.get("zuordnung") or {}).get("kundennr") or a.kopf.get("kundennr") or "")
        akte = self._ausfuehren(lambda abl, x: abl.zuordnung_aendern(x, feld, nr, name, grund=grund,
                                                                      regel=r and mz.regel_text(r)),
                                f"Anfrage {{nr}}: Kunde {nr} {name}".rstrip() + (" (als Regel gemerkt)." if r else "."))
        if akte is not None:            # 20.11.2026: Rückmeldung zur Kunden-Erkennung (Auswertung)
            self._rueckmelden(a, "kunde", auto, str(nr))
            ap = getattr(self, "_ansprech_merken", None)
            self._ansprech_merken = None
            if ap:                      # gewählter Ansprechpartner aus dem Kundenstamm
                self.ansprechpartner_setzen(ap)
        return akte

    def _mail_daten(self, a):
        """Kundendaten aus der Mail der Anfrage (bei interner Weiterleitung aus der Mail des Kunden darin): Firma,
        Anschrift, Telefon, USt-ID, Website, Person (anfrage_kunde.kontakt_aus_mail); korrigierter Absender zählt.
        None, wenn keine Mail lesbar ist."""
        from . import anfrage_kunde, mail
        m = None
        p = self._mail_pfad(a)
        if p is not None:
            try:
                m = mail.lesen(p)
            except Exception as fehler:     # noqa: BLE001 – beschädigte .msg: melden, ohne Mail weiter
                self.f.meldung(f"Mail nicht lesbar ({type(fehler).__name__}): {p.name}", fehler=True)
                m = None
            w = mail.weiterleitung(m, self._eigene_domains(), self.db.einstellung("briefkopf_1") or "") \
                if m is not None else None
            if w is not None and w.original is not None:
                m = w.original
        daten = (anfrage_kunde.kontakt_aus_mail(m, self._eigene_domains()) if m is not None else None) or {}
        k = a.stand.get("absender_korr")
        if k and k.get("adresse"):
            daten["email"] = k["adresse"]
            if daten.get("person"):
                daten["person"]["email"] = k["adresse"]
        return daten

    def kunde_neu_anlegen(self, daten=None, trotzdem=False):
        """Neuen Kunden aus Absender und Signatur anlegen und zuordnen (23.11.2026: Kundenverwaltung mit
        Ansprechpartner, Kundennummer reserviert, Dublettenprüfung ohne Rechtsform/USt-ID/Domain/Telefon). Mit
        Bildschirm öffnet sich die Eingabemaske vorbelegt mit den Daten der Mail; stumm (Tests) mit Dubletten nur
        mit trotzdem. Ergebnis: Kundennummer oder None."""
        from . import anfrage_kunde
        a = self.akte()
        if a is None:
            return None
        if daten is None:
            daten = self._mail_daten(a) or {}
        daten = dict(daten)
        if not daten.get("person") and daten.get("ansprechpartner"):     # alte Form (mail.kunde_daten)
            an, vor, nach = kd.name_teilen(daten.pop("ansprechpartner"))
            daten["person"] = dict(anrede=an, vorname=vor, nachname=nach, email=daten.get("email"))
        kb = getattr(self.f, "kunden", None)
        if not self.f.stumm and kb is not None and hasattr(kb, "neuer_kunde"):
            nr = kb.neuer_kunde(vorschlag=anfrage_kunde.vorschlag_neu(daten), oeffnen=False)
        else:
            if not daten.get("name"):
                self.f.meldung("Kein Firmenname in der Mail – bitte den Kunden von Hand anlegen.", fehler=True)
                return None
            dub = kd.dubletten(self.db, dict(daten, ansprechpartner=[daten["person"]] if daten.get("person") else []))
            if dub and not trotzdem:
                text = "; ".join(f"{k['kundennr']} {k.get('name') or ''} ({', '.join(g)})" for k, g, _ in dub[:6])
                self.f.meldung(f"Möglicherweise schon im Kundenstamm: {text}", fehler=True)
                return None
            try:
                nr = anfrage_kunde.neu_anlegen(self.db, daten, dubletten_ok=True, kundennr=daten.get("kundennr"))
            except Exception as fehler:     # noqa: BLE001 – Lesemodus, Eingabe: Meldung statt stiller Fehler
                self.f.meldung(f"Kunde nicht angelegt: {fehler}", fehler=True)
                return None
        if not nr:
            return None
        name = (kd.kunde(self.db, nr) or {}).get("name") or daten.get("name") or ""
        self._ausfuehren(lambda abl, x: abl.zuordnung_aendern(x, "kunde", nr, name, grund="neu angelegt"),
                         f"Neuer Kunde {nr} {name} angelegt und zugeordnet.")
        return nr

    def angebot_hand(self, nummer=None):
        """Anfrage von Hand mit einem vorhandenen Angebot verknüpfen (Angebotsnummer)."""
        a = self.akte()
        if a is None:
            return None
        if nummer is None:
            if self.f.stumm:
                return None
            nummer, gut = QInputDialog.getText(self, "Angebot verknüpfen", "Angebotsnummer:")
            if not gut:
                return None
        nummer = nummer.strip()
        try:
            z = self.db.con.execute("SELECT id FROM angebote WHERE nummer=? ORDER BY id DESC LIMIT 1",
                                    (nummer,)).fetchone()
        except Exception:               # noqa: BLE001
            z = None
        if not nummer or not z:
            self.f.meldung(f"Angebot {nummer or '?'} nicht gefunden.", fehler=True)
            return None
        erg = self._ausfuehren(lambda abl, x: abl.angebot_verknuepfen(x, nummer, von_hand=True),
                               f"Anfrage {{nr}} mit Angebot {nummer} verknüpft.")
        try:
            alt = ak.akten_zum_angebot(self.db, z[0])
            if a.nr not in alt:
                self.db.zusatz_setzen(z[0], "anfrage_akte", alt + [a.nr] if alt else a.nr)
        except Exception as fehler:               # noqa: BLE001
            protokoll.warnung(f"Anfragen: Verweis im Angebot nicht gesetzt ({type(fehler).__name__}: {fehler})")
        return erg

    def ansprechpartner_setzen(self, text=None):
        a = self.akte()
        if a is None:
            return None
        if text is None:
            if self.f.stumm:
                return None
            text, gut = QInputDialog.getText(self, "Ansprechpartner", "Ansprechpartner beim Kunden:",
                                             text=a.zuordnung.get("ansprechpartner") or "")
            if not gut:
                return None
        return self._ausfuehren(lambda abl, x: abl.zuordnung_aendern(x, "ansprechpartner", text.strip()),
                                "Anfrage {nr}: Ansprechpartner geändert.")

    def absender_korrigieren(self, adresse=None, name=""):
        a = self.akte()
        if a is None:
            return None
        if adresse is None:
            if self.f.stumm:
                return None
            adresse, gut = QInputDialog.getText(self, "Absender korrigieren",
                                                "E-Mail-Adresse des Kunden (für Antwort und Angebot):",
                                                text=a.absender_adresse)
            if not gut:
                return None
        adresse = adresse.strip().lower()
        if adresse and "@" not in adresse:
            self.f.meldung("Bitte eine E-Mail-Adresse eingeben.", fehler=True)
            return None
        if mz.mail.ist_intern(adresse, self._eigene_domains()):
            self.f.meldung("Das ist eine eigene Adresse, nicht die des Kunden.", fehler=True)
            return None
        return self._ausfuehren(lambda abl, x: abl.zuordnung_aendern(x, "absender", adresse, name),
                                "Anfrage {nr}: Absender korrigiert.")

    # ------------------------------------------------------------------ Dokumente, Zusammenführen (20.11.2026)
    def dokumente_hinzufuegen(self, pfade=None, quelle="hand"):
        """Mails und Dokumente zur gewählten Anfrage (ohne pfade: Dateiauswahl). Ergebnis: dict wie
        anfragen_sammeln.hinzufuegen oder None."""
        a = self.akte()
        if a is None or getattr(self.db, "nur_lesen", False):
            return None
        if pfade is None:
            if self.f.stumm:
                return None
            pfade = adok.dateien_waehlen(self)
        pfade = [p for p in pfade if p.is_file()] + [x for p in pfade if p.is_dir() for x in sorted(p.rglob("*"))
                                                     if x.is_file() and not x.name.startswith(".")]
        if not pfade:
            return None
        try:
            r = sa.hinzufuegen(self.ablage(), a, pfade, quelle=quelle)
        except (ak.AblageFehler, OSError) as e:
            self.f.meldung(f"{a.nr}: {fehler_text(e) if isinstance(e, OSError) else e}", fehler=True)
            return None
        teile = [f"{len(r['neu'])} hinzugefügt"] if r["neu"] else []
        if r["doppelt"]:
            teile.append(f"{len(r['doppelt'])} schon vorhanden ({', '.join(r['doppelt'][:3])})")
        if r["fehler"]:
            teile.append("nicht übernommen: " + "; ".join(r["fehler"][:3]))
        self.f.meldung(f"Anfrage {a.nr}: " + ", ".join(teile or ["nichts Neues"]), fehler=bool(r["fehler"]))
        self._mailtexte.pop(a.nr, None)
        self.neu_laden()
        self.waehlen(a.nr)
        return r

    def outlook_auswahl_hinzufuegen(self, quelle="outlook"):
        """Die im Outlook-Fenster markierten Mails als .msg sichern und hinzufügen (auch beim Ziehen aus Outlook)."""
        import shutil
        if self.akte() is None:
            return None
        ziel = adok.zwischenordner()
        try:
            dateien, fehler = ol.auswahl_sichern(ziel, getattr(self, "outlook_ausfuehren", None))
            if fehler and not dateien:
                self.f.meldung("Outlook: " + "; ".join(fehler[:2]), fehler=True)
                return None
            return self.dokumente_hinzufuegen(dateien, quelle=quelle)
        finally:
            shutil.rmtree(ziel, ignore_errors=True)

    def dokumente_verschieben(self, dateien=None, ziel=None):
        a = self.akte()
        if a is None:
            return None
        dateien = dateien if dateien is not None else self.dokumente.gewaehlt()
        if not dateien:
            self.f.meldung("Bitte im Reiter „Dokumente & Mails“ die Mails bzw. Dateien markieren.", fehler=True)
            return None
        if ziel is None:
            if self.f.stumm:
                return None
            d = adok.AnfrageWahlDialog(self, self.akten, a.nr, f"{len(dateien)} Datei(en) aus {a.nr} zuweisen an:")
            if d.exec() != QDialog.Accepted or not d.wahl():
                return None
            ziel = d.wahl()
        nach = self.akte(ziel) or self.ablage().lesen(ziel)
        if nach is None:
            return None
        return self._ausfuehren(lambda abl, x: sa.verschieben(abl, x, nach, dateien),
                                f"{len(dateien)} Datei(en) aus {{nr}} an {ziel} zugewiesen.")

    def zusammenfuehren(self, weitere=None, bestaetigt=None):
        """Weitere Anfragen in die gewählte zusammenführen: Fenster mit Vorschlägen und Übersicht, erst nach
        Bestätigung (bestaetigt=True: ohne Fenster, Tests). Ergebnis: Journal-ID oder None."""
        from . import admin_schutz
        a = self.akte()
        if a is None:
            return None
        vs = sa.vorschlaege(self.akten, a, self._mailtext(a))
        if not self.f.stumm and not bestaetigt:
            d = adok.ZusammenDialog(self, a, self.akten, vs if weitere is None else
                                    [(self.akte(n), "gewählt") for n in weitere if self.akte(n)])
            if weitere:
                for i in range(d.liste.count()):
                    if d.liste.item(i).data(Qt.ItemDataRole.UserRole) in weitere:
                        d.liste.item(i).setCheckState(Qt.Checked)
            if d.exec() != QDialog.Accepted or not d.gewaehlt():
                return None
            weitere = d.gewaehlt()
        elif not bestaetigt:
            return None
        akten = [x for x in (self.akte(n) for n in weitere or ()) if x is not None]
        try:
            jid = sa.zusammenfuehren(self.ablage(), a, akten, ich=self.ich(), admin=admin_schutz.ist_admin(self.db))
        except (ak.AblageFehler, OSError) as e:
            self.f.meldung(f"Zusammenführen: {fehler_text(e) if isinstance(e, OSError) else e}", fehler=True)
            self.neu_laden()
            return None
        self.f.meldung(f"{', '.join(x.nr for x in akten)} in {a.nr} zusammengeführt (rückgängig über "
                       "„Zusammenführung rückgängig“).")
        for x in akten:                 # 24.11.2026: Originale der weiteren aus dem Anfrage-Ordner weglegen
            self._eingang_ablegen(x)
        self.neu_laden()
        self.waehlen(a.nr)
        return jid

    def trennen(self, jid=None):
        from . import admin_schutz
        a = self.akte()
        if a is None:
            return None
        if not self.f.stumm and QMessageBox.question(
                self, "Zusammenführung rückgängig", "Die zuletzt zusammengeführten Anfragen wieder trennen? Ihre Mails "
                "und Dokumente werden hier ausgeblendet, die Anfragen sind wieder eigenständig.") != QMessageBox.Yes:
            return None
        try:
            wieder = sa.rueckgaengig(self.ablage(), a, jid, ich=self.ich(), admin=admin_schutz.ist_admin(self.db))
        except (ak.AblageFehler, OSError) as e:
            self.f.meldung(f"Trennen: {fehler_text(e) if isinstance(e, OSError) else e}", fehler=True)
            return None
        self.f.meldung(f"{', '.join(x.nr for x in wieder)} wieder eigenständig.")
        self.neu_laden()
        self.waehlen(a.nr)
        return wieder

    def kategorie_setzen(self, kategorie, dateien=None):
        a = self.akte()
        if a is None or not kategorie:
            return None
        if kategorie == "__neu__":
            if self.f.stumm:
                return None
            name, gut = QInputDialog.getText(self, "Neue Kategorie", "Name der Kategorie:")
            if not gut or not name.strip():
                return None
            try:
                sa.kategorie_anlegen(self.ablage().wurzel, name)
            except (ak.AblageFehler, OSError) as e:
                self.f.meldung(str(e), fehler=True)
                return None
            kategorie = " ".join(name.split())[:40]
        dateien = dateien if dateien is not None else self.dokumente.gewaehlt()
        if not dateien:
            self.f.meldung("Bitte die Dokumente markieren.", fehler=True)
            return None

        def tun(abl, x):
            for d in dateien:
                x = sa.kategorie_setzen(abl, x, d, kategorie)
            return x
        return self._ausfuehren(tun, f"{len(dateien)} Dokument(e) unter „{kategorie}“.")

    def rueckfrage(self, text=None):
        """Rückfrage an den Kunden: Antwort auf seine Mail in Outlook öffnen (Text mit den fehlenden Angaben, nie
        automatisch gesendet), dann wartet die Anfrage auf den Kunden (Ampel ruht, bis er antwortet). Ohne Outlook:
        als E-Mail-Datei zum Öffnen. text: ohne Dialog (Tests). Ergebnis: neue Akte oder None."""
        from . import anfrage_erkennung as ae
        from . import materialanfrage as ma
        a = self.akte()
        if a is None:
            return None
        if text is None:
            try:
                absender = self.db.einstellung("versand_absender") or ""
            except Exception:           # noqa: BLE001
                absender = ""
            text = ae.rueckfrage_text(self._kunde(a), a, self.erkennung(a)["fehlt"], absender)
            if self.f.stumm:
                return None
            text, gut = QInputDialog.getMultiLineText(self, "Rückfrage an den Kunden",
                                                      "Text der Rückfrage (öffnet sich in Outlook als Antwort, "
                                                      "gesendet wird erst von Ihnen):", text)
            if not gut or not text.strip():
                return None
        an, betreff = a.absender_adresse, ae.rueckfrage_betreff(a)
        msg = self._mail_pfad(a)
        if (a.kopf.get("zuordnung") or {}).get("art") in ("weitergeleitet", "intern") or a.kopf.get("weitergeleitet"):
            msg = None                  # nie auf die interne Mail antworten: Notizen der Kollegen bleiben intern
        gut, fehler = ma.outlook_oeffnen(an, betreff, text, ausfuehren=getattr(self, "rueckfrage_ausfuehren", None),
                                         signatur_=True, antwort=msg if msg and msg.suffix.lower() == ".msg" else None)
        if not gut:
            try:                        # ohne Outlook: E-Mail-Datei (wie beim Angebot per E-Mail)
                import tempfile
                ziel = ak.Path(tempfile.gettempdir()) / "rohrlaser_rueckfrage"
                ziel.mkdir(parents=True, exist_ok=True)
                pfad = ma.eml(ziel / f"Rueckfrage_{a.nr}.eml", an, betreff, text)
                if not self.f.stumm:
                    self.f.datei_oeffnen(pfad)
            except OSError as e:
                self.f.meldung(f"Rückfrage nicht zu öffnen: {fehler} {fehler_text(e)}", fehler=True)
                return None
        try:
            fehlt = list(self.erkennung(a)["fehlt"])
        except Exception:               # noqa: BLE001
            fehlt = []
        return self._ausfuehren(lambda abl, a: abl.rueckfrage(a, text, fehlt=fehlt),
                                "Rückfrage zu Anfrage {nr} geöffnet – sie wartet jetzt auf den Kunden.")

    def nachfassen(self, text=None):
        """Erinnerung an eine offene Rückfrage (23.11.2026): Antwort in Outlook mit den Fragen der Rückfrage (nie
        automatisch gesendet), dann läuft die Wartezeit neu. text: ohne Dialog (Tests)."""
        from . import anfrage_erkennung as ae
        from . import materialanfrage as ma
        a = self.akte()
        if a is None or not a.stand.get("rueckfrage"):
            return None
        if text is None:
            try:
                absender = self.db.einstellung("versand_absender") or ""
            except Exception:           # noqa: BLE001
                absender = ""
            text = anf.erinnerung_text(self._kunde(a), a, absender)
            if self.f.stumm:
                return None
            text, gut = QInputDialog.getMultiLineText(self, "Erinnerung an die Rückfrage",
                                                      "Text der Erinnerung (öffnet sich in Outlook, gesendet wird "
                                                      "erst von Ihnen):", text)
            if not gut or not text.strip():
                return None
        an, betreff = a.absender_adresse, ae.rueckfrage_betreff(a)
        msg = self._mail_pfad(a)
        if (a.kopf.get("zuordnung") or {}).get("art") in ("weitergeleitet", "intern") or a.kopf.get("weitergeleitet"):
            msg = None
        gut, fehler = ma.outlook_oeffnen(an, betreff, text, ausfuehren=getattr(self, "rueckfrage_ausfuehren", None),
                                         signatur_=True, antwort=msg if msg and msg.suffix.lower() == ".msg" else None)
        if not gut:
            try:
                import tempfile
                ziel = ak.Path(tempfile.gettempdir()) / "rohrlaser_rueckfrage"
                ziel.mkdir(parents=True, exist_ok=True)
                pfad = ma.eml(ziel / f"Erinnerung_{a.nr}.eml", an, betreff, text)
                if not self.f.stumm:
                    self.f.datei_oeffnen(pfad)
            except OSError as e:
                self.f.meldung(f"Erinnerung nicht zu öffnen: {fehler} {fehler_text(e)}", fehler=True)
                return None
        return self._ausfuehren(lambda abl, a: abl.rueckfrage(a, text, nachfassen=True),
                                "Erinnerung zu Anfrage {nr} geöffnet – sie wartet weiter auf den Kunden.")

    def antwort_erhalten(self):
        """Antwort von Hand vermerkt (z. B. am Telefon): die Frist läuft ab jetzt neu."""
        return self._ausfuehren(lambda abl, a: abl.antwort_erhalten(a),
                                "Anfrage {nr}: Antwort erhalten, die Frist läuft neu.")

    def aus_letztem_angebot(self):
        """Wiederholteile: neues Angebot mit den Positionen des letzten Angebots (gleiche STEP: alle Positionen; bekannte
        Artikel: deren Positionen, Stückzahl aus der Anfrage), mit der Anfrage verknüpft. Ergebnis: Angebots-ID."""
        from . import position_kopie, teilekatalog, wiederholanfrage
        a = self.akte()
        if a is None:
            return None
        if self.db.nur_lesen:
            self.f.meldung("Die Datendatei ist nur zum Lesen geöffnet.", fehler=True)
            return None
        if a.virus():
            self.f.meldung(f"{a.nr}: Virus gefunden, bitte erst klären.", fehler=True)
            return None
        wieder = self.erkennung(a)["wiederholt"]
        if not wieder:
            self.f.meldung(f"Anfrage {a.nr}: keine Wiederholteile gefunden.", fehler=True)
            return None
        quellen = {}
        for w in wieder:
            if w["art"] == "step":
                quellen.setdefault(w["angebot_id"], None)
        artikel = [w["quelle"] for w in wieder if w["art"] == "artikel"]
        for q, ids in teilekatalog.nach_angebot(artikel).items():
            if q in quellen and quellen[q] is None:
                continue
            quellen.setdefault(q, [])
            quellen[q] += ids
        kunde = a.kunde or (self._erste_kunde(quellen) or "")
        if a.status == ak.NEU:
            a = self.uebernehmen(self.ich())
            if a is None:
                return None
        i = self.db.angebot_neu(dict(kundennr=kunde))
        seite = self.f.angebot_oeffnen(i)
        for q, ids in quellen.items():
            pos = self.db.positionen(q)
            zeilen = [n for n, p in enumerate(pos) if ids is None or p["id"] in ids]
            if zeilen and position_kopie.einheiten(pos, zeilen) and seite is not None:
                seite.positionen_uebernehmen(q, zeilen, staffeln=False)
        try:
            wiederholanfrage.stueck_setzen(self.db, i, artikel)
        except Exception:               # noqa: BLE001
            pass
        try:
            nummer = (self.db.angebot(i) or {}).get("nummer") or ""
            if nummer:
                self.ablage().angebot_verknuepfen(self.ablage().neu_lesen(a), nummer)
            self.db.zusatz_setzen(i, "anfrage_akte", a.nr)
        except Exception:               # noqa: BLE001
            pass
        if hasattr(self.f, "angebote"):
            self.f.angebote.neu_laden()
        if seite is not None and hasattr(seite, "neu_laden"):
            seite.neu_laden()
        self.f.meldung(f"Neues Angebot aus dem letzten Angebot angelegt, mit Anfrage {a.nr} verknüpft.")
        self.neu_laden()
        return i

    def _erste_kunde(self, quellen):
        for q in quellen:
            z = self.db.con.execute("SELECT kundennr FROM angebote WHERE id=?", (q,)).fetchone()
            if z and z[0]:
                return z[0]
        return None

    # ------------------------------------------------------------------ Paket 6: Kacheln der Startseite
    FILTER_TEXT = {"ueberfaellig": "überfällige Anfragen", "heute": "heute fällige Anfragen",
                   "meine": "meine Anfragen"}

    def passt_filter(self, a, art):
        stufe, faellig, _t = self.ampeln.get(a.nr) or (None, None, "")
        if art == "ueberfaellig":
            return stufe == "rot"
        if art == "heute":
            return stufe == "gelb"
        if art == "meine":
            return ak.ist_meine(a, self.ich())
        return True

    def kachel_zahlen(self):
        """{ueberfaellig, heute, meine} für die Kacheln der Startseite."""
        return {k: sum(1 for a in self.akten if a.status != ak.ERLEDIGT and self.passt_filter(a, k))
                for k in self.FILTER_TEXT}

    def filter_setzen(self, art):
        """Filter aus der Kachel (alle offenen Anfragen mit dieser Ampel) oder "" = aufheben."""
        self.ampel_filter = art if art in self.FILTER_TEXT else ""
        if self.ampel_filter:
            self.gruppe.setExclusive(False)
            for b in self.zaehler.values():
                b.setChecked(False)
            self.gruppe.setExclusive(True)
            self.ordner = "meine" if art == "meine" else None
            if art == "meine":
                self.zaehler["meine"].setChecked(True)
            self.filter_hinweis.setText(f"Gefiltert: {self.FILTER_TEXT[art]}")
        else:
            if self.ordner is None:
                self.ordner = "neu"
            self.zaehler[self.ordner].setChecked(True)
        self.filter_zeile.setVisible(bool(self.ampel_filter))
        self.liste_fuellen()

    def _kacheln_melden(self):
        start = getattr(self.f, "start", None)
        if start is not None and hasattr(start, "anfragen_kacheln_setzen"):
            try:
                start.anfragen_kacheln_setzen(self.kachel_zahlen())
            except Exception:           # noqa: BLE001
                pass

    # ------------------------------------------------------------------ Outlook (Paket 2)
    def outlook_abrufen(self, immer=False, warten=False):
        """Abruf im Hintergrund starten (eingeschaltet oder immer). warten: bis fertig (Tests, „Jetzt abrufen“)."""
        try:                            # Zeitgeber kann nach dem Schließen der Datendatei noch feuern
            if self._ol_lauf is not None or self.db.nur_lesen or not (immer or ol.an(self.db)):
                return False
            kunden = kd.mit_kontakten(self.db)     # 23.11.2026: auch E-Mail/Telefon der Ansprechpartner
            phasen = ph.ordner_einstellungen(self.db)
            # Phase mit Angeboten/Aufträgen hier rechnen (Datenbank nur im Hauptfaden), der Abruf liest nur die Liste
            phasen_je = {a.nr: self.phase(a) for a in self.akten if a.stand.get("angebote")} if phasen else {}
        except Exception:               # noqa: BLE001
            return False
        self._ol_pool = self._ol_pool or ThreadPoolExecutor(max_workers=1)
        self._ol_lauf = self._ol_pool.submit(ol.abrufen, self.ablage(), ol.ordner(self.db), kunden,
                                             getattr(self, "outlook_ausfuehren", None), None,
                                             ol.unter_pfade(self.db), ol.zuordnung(self.db),
                                             self.mitarbeiter_namen(), ol.ordner_ids(self.db),
                                             self._eigene_domains(), self.db.einstellung("briefkopf_1") or "",
                                             phasen, lambda a: phasen_je.get(a.nr) or ph.phase(a))
        if warten:
            self._ol_lauf.result()
            self._outlook_pruefen()
        else:
            self._ol_warten.start()
        return True

    def _eigene_domains(self):
        """Domains der eigenen Firma: zählen beim Abruf nie als Kunde (weitergeleitete Mails)."""
        try:
            from . import anfragen
            return anfragen.eigene_domains(self.db)
        except Exception:               # noqa: BLE001
            return set()

    def _outlook_pruefen(self):
        f = self._ol_lauf
        if f is None or not f.done():
            return
        self._ol_lauf = None
        self._ol_warten.stop()
        try:
            erg = f.result()
        except Exception as e:          # noqa: BLE001 – Abruf darf das Programm nie stören
            erg = dict(neu=[], gefolgt=[], verschoben=0, fehler=[str(e)], anderer=None)
        self.outlook_letzt = (datetime.datetime.now(), erg)
        if erg["neu"] or erg["gefolgt"] or erg["verschoben"] or erg.get("antworten") or erg.get("kategorien"):
            self.neu_laden()
        if erg["fehler"]:
            self.hinweis.setText("Outlook: " + "; ".join(erg["fehler"][:3]))
            self.hinweis.setVisible(True)
        self.ol_status_zeigen()
        d = getattr(self, "_ol_dialog", None)
        if d is not None:
            d.anzeigen()

    def outlook_zeigen(self):
        d = OutlookDialog(self)
        self._ol_dialog = d
        if not self.f.stumm:
            d.exec()
            self._ol_dialog = None
        return d

    def auswertung(self):
        """Daten der Auswertung (Paket 5) mit den Vorgängen der verknüpften Angebote."""
        vorgaenge = {}
        nummern = {n for a in self.akten for n in a.stand["angebote"]}
        if nummern:
            try:
                for nr, vg in self.db.con.execute("SELECT nummer, vorgang FROM angebote WHERE nummer IN (%s)"
                                                  % ",".join("?" * len(nummern)), tuple(nummern)):
                    vorgaenge[nr] = vg or "Entwurf"
            except Exception:           # noqa: BLE001
                pass
        return ak.auswertung(self.akten, vorgaenge)

    def auswertung_zeigen(self):
        return self.mitarbeiter_zeigen()

    def mitarbeiter_zeigen(self):
        d = AuswertungDialog(self, self.auswertung(), self.mitarbeiter_liste(), seite=self)
        if not self.f.stumm:
            d.exec()
        return d


class AuswertungDialog(QDialog):
    """Auswertung der Anfragen (Paket 5): Kennzahlen oben, Anfragen je Woche (Eingänge, mit Angebot, keine Anfrage)
    und je Mitarbeiter (offen, erledigt, vorgeschlagen, Ø bis Übernahme, Ø bis Angebot, Ø Bearbeitung, Angebote,
    beauftragt). self.tabelle = Mitarbeiter, self.wochen = Wochen."""

    def __init__(self, parent, werte, namen, seite=None):
        super().__init__(parent)
        self.seite = seite
        self.setWindowTitle("Auswertung der Anfragen")
        lay = QVBoxLayout(self)
        mit, auftrag = werte["treffer"]
        self.kennzahlen = QLabel(
            f"Ø vom Eingang bis zum Angebot: <b>{ak.dauer_text(werte['std_bis_angebot'])}</b> · "
            f"Trefferquote: <b>{ak.quote_text(auftrag, mit)}</b> ({auftrag} von {mit} Anfragen mit Angebot "
            f"beauftragt) · Keine Anfrage: <b>{werte['aussortiert']}</b>")
        self.kennzahlen.setWordWrap(True)
        lay.addWidget(self.kennzahlen)
        w = QTableWidget(len(werte["wochen"]), 4)
        w.setHorizontalHeaderLabels(("Woche", "Eingänge", "mit Angebot", "keine Anfrage"))
        for r, (woche, n, ang, aus) in enumerate(reversed(werte["wochen"])):
            j, kw = woche.split("-W")
            for c, v in enumerate((f"KW {int(kw)}/{j}", n, ang, aus)):
                w.setItem(r, c, QTableWidgetItem(str(v)))
        self.wochen = w
        ma = werte["mitarbeiter"]
        t = QTableWidget(len(ma), 9)
        t.setHorizontalHeaderLabels(("Mitarbeiter", "Offen", "Erledigt", "Vorgeschlagen", "Ø bis Übernahme",
                                     "Ø bis Angebot", "Ø Bearbeitung", "Angebote", "Beauftragt"))
        for r, (k, x) in enumerate(ma.items()):
            for c, v in enumerate((namen.get(k, k), x["offen"], x["erledigt"], x["zugewiesen"],
                                   ak.dauer_text(x["std_bis_uebernahme"]), ak.dauer_text(x["std_bis_angebot"]),
                                   ak.dauer_text(x["std_bearbeitung"]), x["angebote"],
                                   f"{x['beauftragt']} ({ak.quote_text(x['beauftragt'], x['angebote'])})")):
                t.setItem(r, c, QTableWidgetItem(str(v)))
        self.tabelle = t
        for tab, titel, breiten in ((w, "<b>Je Woche</b> (letzte 12 Wochen)", (110, 80, 100, 110)),
                                    (t, "<b>Je Mitarbeiter</b>", (140, 60, 70, 100, 120, 110, 110, 80, 100))):
            lay.addWidget(QLabel(titel))
            tab.verticalHeader().setVisible(False)
            tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
            for c, b in enumerate(breiten):
                tab.setColumnWidth(c, b)
            lay.addWidget(tab, 1)
        # 23.11.2026 (Stufe 2 Punkt 4): Erkennung je Woche (aus den Akten gerechnet, nichts gespeichert)
        from . import anfrage_messung
        try:
            vl = anfrage_messung.verlauf(seite.akten, self._wurzel()) if seite is not None else []
        except OSError:
            vl = []
        v = QTableWidget(len(vl), 8)
        v.setHorizontalHeaderLabels(("Woche", "Eingänge", "Mail-Art unklar", "von Hand korrigiert",
                                     "Kunde eindeutig", "Ø bis Übernahme", "Rückfragen", "nachgefasst"))
        for r, x in enumerate(reversed(vl)):
            j, kw = x["woche"].split("-W")
            for c, wert in enumerate((f"KW {int(kw)}/{j}", x["eingaenge"], _prozent(x["unklar"]), _prozent(x["korrigiert"]),
                                      _prozent(x["kunde_sicher"]), ak.dauer_text(x["std_bis_uebernahme"]),
                                      x["rueckfragen"], x["nachgefasst"])):
                v.setItem(r, c, QTableWidgetItem(str(wert)))
        v.verticalHeader().setVisible(False)
        v.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v.setMaximumHeight(190)
        for c, b in enumerate((100, 75, 120, 150, 120, 125, 90, 95)):
            v.setColumnWidth(c, b)
        self.verlauf = v
        lay.addWidget(QLabel("<b>Erkennung je Woche</b> (nach Eingang; weniger „unklar“ und „korrigiert“ ist besser)"))
        lay.addWidget(v)
        # 20.11.2026 (Plan K9/K11): Erkennung – Trefferquote je Feld, gelerntes Modell im Schatten, Freigabe
        lay.addWidget(QLabel("<b>Erkennung</b> (aus den Korrekturen von Hand)"))
        self.erkennung = QTextBrowser()
        self.erkennung.setMaximumHeight(170)
        lay.addWidget(self.erkennung)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Gelernt für:"))
        self.ziel = QComboBox()             # 23.11.2026: Mail-Art, Sachgebiet, Bearbeiter, je eigene Freigabe
        for k, t_ in al.ZIELE.items():
            self.ziel.addItem(t_, k)
        self.ziel.currentIndexChanged.connect(lambda _i: self.erkennung_zeigen())
        zeile.addWidget(self.ziel)
        self.k_trainieren = QPushButton("Modell prüfen")
        self.k_trainieren.setToolTip("Aus allen Korrekturen ein Wortmodell rechnen und gegen die Regeln testen (nur "
                                     "Schatten, ändert nichts)")
        self.k_trainieren.clicked.connect(self.trainieren)
        self.k_freigeben = QPushButton("Freigeben")
        self.k_freigeben.setToolTip("Nur Admin: das geprüfte Modell wirkt ab jetzt bei unsicheren Mails")
        self.k_freigeben.clicked.connect(self.freigeben)
        self.k_zurueck = QPushButton("Freigabe zurücknehmen")
        self.k_zurueck.clicked.connect(self.zuruecknehmen)
        for k in (self.k_trainieren, self.k_freigeben, self.k_zurueck):
            zeile.addWidget(k)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.erkennung_zeigen()
        knopf = QDialogButtonBox(QDialogButtonBox.Close)
        knopf.rejected.connect(self.reject)
        lay.addWidget(knopf)
        self.resize(980, 860)

    def _wurzel(self):
        return self.seite.ablage().wurzel if self.seite is not None else None

    def erkennung_zeigen(self):
        w = self._wurzel()
        if w is None:
            self.erkennung.setHtml("<i>keine Daten</i>")
            return ""
        try:
            aus = al.auswertung(w, self.seite.akten)
            ziel = self.ziel.currentData() or "art"
            schatten, aktiv = al.modell_lesen(w, ziel), al.aktiv_lesen(w, ziel)
        except OSError as e:
            self.erkennung.setHtml(f"<i>nicht lesbar: {html.escape(str(e))}</i>")
            return ""
        z = []
        for f, x in aus["felder"].items():
            v = "; ".join(f"{html.escape(a)} ({n}×)" for a, n in x["verwechselt"])
            z.append(f"<tr><td>{html.escape(al.FELDER.get(f, f))}&nbsp;</td><td>{x['anzahl']}&nbsp;</td>"
                     f"<td>{x['quote']} % bestätigt&nbsp;</td><td style='color:#666'>{v}</td></tr>")
        t = ("<table><tr><th align=left>Feld</th><th align=left>Rückmeldungen</th><th align=left>Quote</th>"
             "<th align=left>häufig korrigiert</th></tr>" + "".join(z) + "</table>") if z else \
            "<p>Noch keine Korrekturen.</p>"
        sich = ", ".join(f"{html.escape(k)} {n}" for k, n in sorted(aus["sicherheit"].items()))
        p = (schatten or {}).get("pruefung") or {}
        ok, grund = al.freigabe_moeglich(schatten)
        m = f"<b>{html.escape(al.ZIELE.get(ziel, ziel))}:</b> "
        m += (f"Schatten-Modell {schatten.get('version')}: {p.get('n')} Beispiele, im Test {p.get('modell')} % "
             f"richtig, Regeln {p.get('regeln')} %. " if schatten else "Noch kein Modell geprüft. ")
        m += (f"Freigegeben: Modell {aktiv.get('version')} ({html.escape(str(aktiv.get('freigegeben_von') or ''))})."
              if aktiv else "Kein Modell freigegeben, es gelten nur die Regeln.")
        self.erkennung.setHtml(t + (f"<p>Mail-Art-Sicherheit: {sich}</p>" if sich else "")
                               + f"<p>{m}<br><span style='color:#666'>Freigabe: {html.escape(grund)}</span></p>")
        self.k_freigeben.setEnabled(ok)
        self.k_zurueck.setEnabled(bool(aktiv))
        return self.erkennung.toPlainText()

    def trainieren(self):
        m = al.trainieren(self._wurzel(), ziel=self.ziel.currentData() or "art")
        self.erkennung_zeigen()
        return m

    def freigeben(self):
        from . import admin_schutz
        if not admin_schutz.ist_admin(self.seite.db):
            self.seite.f.meldung("Nur ein Admin kann ein gelerntes Modell freigeben.", fehler=True)
            return False
        ok, text = al.freigeben(self._wurzel(), self.seite.ich(), ziel=self.ziel.currentData() or "art")
        self.seite.f.meldung(text, fehler=not ok)
        self.seite._modell_cache = None
        self.seite._erkannt = {}
        self.erkennung_zeigen()
        return ok

    def zuruecknehmen(self):
        from . import admin_schutz
        if not admin_schutz.ist_admin(self.seite.db):
            self.seite.f.meldung("Nur ein Admin kann die Freigabe zurücknehmen.", fehler=True)
            return ""
        t = al.zuruecknehmen(self._wurzel(), ziel=self.ziel.currentData() or "art")
        self.seite.f.meldung(t)
        self.seite._modell_cache = None
        self.seite._erkannt = {}
        self.erkennung_zeigen()
        return t


class OutlookDialog(QDialog):
    """Einstellung je Rechner: Anfragen aus Outlook holen, Ordnername, wer abruft, letzter Abruf, Jetzt abrufen."""

    def __init__(self, seite):
        super().__init__(seite)
        self.seite, db = seite, seite.db
        self.setWindowTitle("Anfragen aus Outlook")
        lay = QVBoxLayout(self)
        t = QLabel("Das Programm liest den Eingangsordner aus dem klassischen Outlook dieses Rechners. Jede Mail "
                   "dort wird eine Anfrage und bleibt im Eingang (= Neu); Übernehmen und Erledigen verschieben sie nach „In "
                   "Bearbeitung“ bzw. „Erledigt“, Verschieben in Outlook ändert die Anfrage. Eine Outlook-Kategorie "
                   "kann für einen Mitarbeiter stehen: gesetzt = zugewiesen, und das Programm setzt sie selbst. Nur "
                   "ein Rechner holt ab. Gesendet oder gelöscht wird nichts.")
        t.setWordWrap(True)
        lay.addWidget(t)
        self.ein = QCheckBox("Dieser Rechner holt die Anfragen aus Outlook")
        self.ein.setChecked(ol.an(db))
        self.ein.toggled.connect(self._ein)
        lay.addWidget(self.ein)
        self.viren = QCheckBox("Anhänge zusätzlich selbst mit dem Windows-Virenschutz prüfen (MpCmdRun)")
        self.viren.setToolTip("Aus (Vorgabe): der Echtzeitschutz von Windows prüft die Dateien ohnehin beim Auspacken "
                              "und Öffnen. An: das Programm ruft den Defender zusätzlich selbst auf und sperrt Funde.")
        self.viren.setChecked(vp.an(db))
        self.viren.toggled.connect(lambda an_: db.einstellung_setzen(vp.EIN, "ja" if an_ else "nein"))
        lay.addWidget(self.viren)
        raster = QGridLayout()
        self.ordner = QLineEdit(ol.ordner(db))
        self.ordner.setToolTip("Name des Ordners, z. B. Anfragen; mit \\ als Pfad, z. B. Postfach\\Anfragen; "
                               "„Wählen …“ nimmt den Ordner aus der Ordnerauswahl von Outlook")
        self.ordner.editingFinished.connect(
            lambda: db.einstellung_setzen(ol.ORDNER_EINSTELLUNG, self.ordner.text().strip() or ol.ORDNER_VORGABE))
        self.pfade = {}
        zeilen = [("eingang", "Eingang", self.ordner)]
        for schl, (name, status) in zip(("neu", "bearbeitung", "erledigt"),
                                        (("Neu", ak.NEU), ("In Bearbeitung", ak.BEARBEITUNG),
                                         ("Erledigt", ak.ERLEDIGT))):
            e = QLineEdit(db.einstellung(ol.PFAD_EINSTELLUNG[schl]) or "")
            e.setPlaceholderText("leer: neue Mails bleiben im Eingang, kein eigener Ordner (Vorgabe)" if schl == "neu"
                                 else f"Unterordner „{ol.UNTER[status]}“ im Eingang (Vorgabe)")
            e.editingFinished.connect(lambda s_=schl, e_=e: self._pfad_setzen(s_, e_.text()))
            self.pfade[schl] = e
            zeilen.append((schl, name, e))
        for p in ph.ORDNER_PHASEN:      # 20.11.2026 (Plan K6): weitere Ordner je Phase, leer = nicht benutzt
            schl = "phase_" + p
            e = QLineEdit(db.einstellung(ph.ORDNER_EINSTELLUNG + p) or "")
            e.setPlaceholderText("leer: kein eigener Ordner (Mail bleibt in „"
                                 + ol.UNTER[ph.ORDNER_PHASEN[p]] + "“)")
            e.editingFinished.connect(lambda s_=schl, e_=e: self._pfad_setzen(s_, e_.text()))
            self.pfade[schl] = e
            zeilen.append((schl, ph.text(p), e))
        for r, (schl, name, feld) in enumerate(zeilen):
            if r == 4:
                raster.addWidget(QLabel("<i>Optional: eigener Ordner je Phase. Verschieben in Outlook setzt die "
                                        "Phase, das Programm verschiebt beim Wechsel der Phase.</i>"), 50, 0, 1, 3)
            z = r if r < 4 else 50 + r
            raster.addWidget(QLabel(name), z, 0)
            raster.addWidget(feld, z, 1)
            w = QPushButton("Wählen …")
            w.setToolTip("Ordner in Outlook auswählen (auch in einem anderen Postfach)")
            w.clicked.connect(lambda _=False, s_=schl: self.waehlen(s_))
            raster.addWidget(w, z, 2)
        lay.addLayout(raster)
        kopf = QHBoxLayout()
        kopf.addWidget(QLabel("<b>Outlook-Kategorie → Mitarbeiter</b>"), 1)
        holen = QPushButton("Kategorien aus Outlook lesen")
        holen.clicked.connect(lambda: self.kategorien_holen())
        kopf.addWidget(holen)
        lay.addLayout(kopf)
        self.kat_tab = QTableWidget(0, 2)
        self.kat_tab.setHorizontalHeaderLabels(["Kategorie", "Mitarbeiter"])
        self.kat_tab.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.kat_tab.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.kat_tab.verticalHeader().setVisible(False)
        self.kat_tab.setToolTip("Gesetzt in Outlook = Anfrage dem Mitarbeiter zugewiesen; im Programm zugewiesen "
                                "oder übernommen = Kategorie an der Mail. Vorbelegt, wenn die Kategorie wie Kürzel "
                                "oder Name heißt.")
        lay.addWidget(self.kat_tab, 1)
        self.kategorien_zeigen()
        lay.addWidget(QLabel("<b>Zuordnungsregeln</b> (gelernt aus Korrekturen, gelten für neue Mails)"))
        self.regeln = QTextBrowser()     # 19.11.2026: kontrolliertes Lernen, sichtbar und löschbar
        self.regeln.setOpenLinks(False)
        self.regeln.setMaximumHeight(110)
        self.regeln.anchorClicked.connect(self._regel_link)
        lay.addWidget(self.regeln)
        self.regeln_zeigen()
        self.stand = QLabel()
        self.stand.setWordWrap(True)
        lay.addWidget(self.stand)
        unten = QDialogButtonBox(QDialogButtonBox.Close)
        self.jetzt = unten.addButton("Jetzt abrufen", QDialogButtonBox.ActionRole)
        self.jetzt.clicked.connect(self.abrufen)
        unten.rejected.connect(self.reject)
        lay.addWidget(unten)
        self.anzeigen()
        self.resize(640, 520)

    def regeln_zeigen(self):
        try:
            self.regeln.setHtml(adok.regeln_html(mz.regeln_lesen(self.seite.ablage().wurzel)))
        except Exception:               # noqa: BLE001
            self.regeln.setHtml("<i>Regeln nicht lesbar</i>")

    def _regel_link(self, url):
        art, _, rid = url.toString().partition(":")
        if art.replace("-", "_") == "regel_weg" and rid:
            mz.regel_loeschen(self.seite.ablage().wurzel, rid)
            self.regeln_zeigen()

    def _pfad_setzen(self, schl, pfad):
        """Outlook-Pfad eines Ordners speichern ("" = Vorgabe). Ergebnis: Fehlertext oder ""."""
        db = self.seite.db
        pfad = (pfad or "").strip()
        if schl == "neu" and pfad == ol.ordner(db):
            pfad = ""                   # Neu = der Eingang selbst: Mails bleiben dort (kein eigener Ordner)
        andere = {ol.ordner(db)} | {self.pfade[k].text().strip() for k in self.pfade if k != schl}
        if pfad and schl != "eingang" and pfad in andere:
            self.pfade[schl].setText(db.einstellung(_einstellung(schl)) or "")
            self.seite.f.meldung("Dieser Ordner ist schon für einen anderen Zweck gewählt.", fehler=True)
            return "doppelt"
        if schl == "eingang":
            self.ordner.setText(pfad or ol.ORDNER_VORGABE)
            db.einstellung_setzen(ol.ORDNER_EINSTELLUNG, pfad or ol.ORDNER_VORGABE)
        else:
            self.pfade[schl].setText(pfad)
            db.einstellung_setzen(_einstellung(schl), pfad)
        return ""

    def waehlen(self, schl):
        """Ordnerauswahl von Outlook öffnen und den gewählten Ordner übernehmen. Ergebnis: Pfad oder ""."""
        pfad, kats, fehler, kennung = ol.ordner_waehlen(getattr(self.seite, "outlook_ausfuehren", None))
        if fehler:
            self.seite.f.meldung(f"Outlook: {fehler}", fehler=True)
            return ""
        if kats:
            self._kats_merken(kats)
        db = self.seite.db
        if schl == "neu" and kennung.get("e") and \
                (ol.ordner_ids(db).get(ol.ordner(db)) or {}).get("e") == kennung.get("e"):
            pfad = ol.ordner(db)        # den Eingang selbst gewählt: Neu bleibt im Eingang
        if not pfad or self._pfad_setzen(schl, pfad):
            return ""
        if schl == "neu" and not self.pfade["neu"].text():
            return pfad
        ol.ordner_id_merken(self.seite.db, pfad, kennung.get("e"), kennung.get("s"))   # auch fremde Postfächer
        return pfad

    def _kats_merken(self, kats):
        try:
            ol.kategorien_schreiben(self.seite.ablage(), set(ol.kategorien_lesen(self.seite.ablage())) | set(kats))
        except OSError:
            pass
        self.kategorien_zeigen()

    def kategorien_holen(self):
        kats, fehler = ol.kategorien_holen(getattr(self.seite, "outlook_ausfuehren", None))
        if fehler:
            self.seite.f.meldung(f"Outlook: {fehler}", fehler=True)
            return []
        self._kats_merken(kats)
        return kats

    def kategorien_zeigen(self):
        """Tabelle Kategorie → Mitarbeiter: Kategorien vom letzten Abruf und von Hand zugeordnete."""
        db = self.seite.db
        try:
            bekannt = ol.kategorien_lesen(self.seite.ablage())
        except OSError:
            bekannt = []
        zu, namen = ol.zuordnung(db), self.seite.mitarbeiter_namen()
        kats = sorted(set(bekannt) | set(zu), key=str.casefold)
        self.kat_tab.clearSpans()
        self.kat_tab.setRowCount(len(kats))
        for r, kat in enumerate(kats):
            it = QTableWidgetItem(kat)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.kat_tab.setItem(r, 0, it)
            wahl = QComboBox()
            wahl.addItem("– kein Mitarbeiter –", "")
            for k, n in sorted(namen.items()):
                wahl.addItem(f"{k} – {n}" if n else k, k)
            jetzt = ol.kat_kuerzel(kat, zu, namen)
            if jetzt and wahl.findData(jetzt) < 0:
                wahl.addItem(jetzt, jetzt)
            wahl.setCurrentIndex(max(0, wahl.findData(jetzt)))
            wahl.currentIndexChanged.connect(lambda _i, k_=kat, w_=wahl: ol.zuordnung_setzen(db, k_, w_.currentData()))
            self.kat_tab.setCellWidget(r, 1, wahl)
        if not kats:
            self.kat_tab.setRowCount(1)
            leer = QTableWidgetItem("Noch keine Kategorien: „Kategorien aus Outlook lesen“ oder einmal abrufen.")
            leer.setFlags(Qt.ItemIsEnabled)
            self.kat_tab.setItem(0, 0, leer)
            self.kat_tab.setSpan(0, 0, 1, 2)

    def _ein(self, an_):
        db = self.seite.db
        db.einstellung_setzen(ol.EIN, "ja" if an_ else "nein")
        if not an_:
            try:
                ol.marke_abgeben(self.seite.ablage())
            except OSError:
                pass
        else:
            self.seite.outlook_abrufen()
        self.anzeigen()

    def abrufen(self):
        self.seite.db.einstellung_setzen(ol.ORDNER_EINSTELLUNG, self.ordner.text().strip() or ol.ORDNER_VORGABE)
        self.seite.outlook_abrufen(immer=True, warten=self.seite.f.stumm)
        self.anzeigen()

    def anzeigen(self):
        zeilen = []
        try:
            m = ol.marke_lesen(self.seite.ablage())
        except OSError:
            m = None
        if m:
            try:
                zuletzt = f"{datetime.datetime.fromisoformat(m.get('zeit', '')):%d.%m.%Y %H:%M}"
            except ValueError:
                zuletzt = "?"
            zeilen.append(f"Abruf durch {m.get('kuerzel', '')} am Rechner {m.get('platz', '')}, zuletzt {zuletzt}")
        else:
            zeilen.append("Zurzeit holt kein Rechner die Anfragen aus Outlook.")
        if self.seite._ol_lauf is not None:
            zeilen.append("Abruf läuft …")
        elif self.seite.outlook_letzt:
            z, e = self.seite.outlook_letzt
            if e.get("anderer"):
                a = e["anderer"]
                t = f"nicht abgerufen: Rechner {a.get('platz', '')} ({a.get('kuerzel', '')}) holt ab"
            else:
                n = len(e["neu"])
                t = (f"{n} neue Anfrage{'' if n == 1 else 'n'}, {e['verschoben']} in Outlook verschoben, "
                     f"{e.get('kategorien', 0)} Kategorien in Outlook gesetzt, "
                     f"{len(e['gefolgt'])} nach Änderung in Outlook geändert")
                if e.get("andere"):
                    t += (f"; {e['andere']} Eintr{'ag' if e['andere'] == 1 else 'äge'} im Eingang sind keine Mail "
                          "(z. B. Termin, Lesebestätigung) und bleiben dort")
            zeilen.append(f"Letzter Abruf {z:%H:%M}: {t}")
            zeilen += [f"Fehler: {f}" for f in e["fehler"][:3]]
        self.stand.setText("\n".join(zeilen))


def _art_passt(ein, wahl):
    """Filter „Mail-Art“: unklar, andere (keine neue Anfrage) oder genau eine Art."""
    if not ein:
        return wahl == "unklar"
    if wahl == "unklar":
        return ein.get("sicherheit") == aa.UNKLAR
    if wahl == "andere":
        return ein.get("art") != aa.ANFRAGE
    return ein.get("art") == wahl


def _einstellung(schl):
    """Einstellung eines Ordners im Fenster „Outlook …“ (Grundordner oder Phasen-Ordner „phase_…“)."""
    if schl.startswith("phase_"):
        return ph.ORDNER_EINSTELLUNG + schl[len("phase_"):]
    return ol.PFAD_EINSTELLUNG[schl]


SCHNELL_STIL = ("QToolButton:checked { background: #2F6FB3; color: white; "
               "border: 1px solid #1F4E79; border-radius: 3px; font-weight: bold; }")
SCHNELL = {"ohne": ("Nicht zugeordnet", "Neue Anfragen ohne Bearbeiter"),
           "kunde": ("Kunde prüfen", "Kunde nicht sicher erkannt"),
           "dringend": ("Dringend", "Priorität hoch/eilt oder heute fällig bzw. überfällig"),
           "fehlt": ("Angaben fehlen", "Es fehlen Angaben für die Kalkulation (Werkstoff, Stückzahl …)"),
           "unklar": ("Unklar", "Mail-Art nicht sicher erkannt"),
           "anhaenge": ("Neue Anhänge", "Seit der letzten eigenen Bearbeitung sind Dateien dazugekommen"),
           "doppelt": ("Doppelt", "Dieselbe Mail kam auf zwei Wegen (z. B. direkt und weitergeleitet)"),
           "ueberfaellig": ("Überfällig", "Antwortfrist überschritten"),
           "nachfassen": ("Nachfassen", "Rückfrage an den Kunden ohne Antwort (Einstellung „Rückfrage nachfassen "
                                        "nach … Arbeitstagen“)")}


def _prozent(x):
    return "–" if x is None else f"{x} %"


def _neue_anhaenge(a):
    """Dateien (keine Mail) kamen nach der letzten Aktion des Bearbeiters dazu (bei Neu: nach dem Eingang)."""
    wer = a.bearbeiter or ""
    seit = max((e.get("zeit", "") for e in a.verlauf if wer and e.get("kuerzel") == wer
                and e.get("aktion") != ak.DATEI_DAZU), default="")
    for e in a.verlauf:
        if e.get("aktion") == ak.DATEI_DAZU and e.get("zeit", "") > seit and any(
                ak.art(d.get("name", "")) != "mail" for d in e.get("dateien") or ()):
            return True
    return False
