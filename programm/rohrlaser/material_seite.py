"""Seite „Material“ in der Seitenleiste (Materialplattform, Patrick 23.11.2026, Entwurf A „Arbeitsliste mit Detail“
mit umschaltbarer Preismatrix).

Links Filter mit Anzahl je Wert, in der Mitte eine Zeile je Material (Abmessung + Werkstoff) mit Spalten zum Ein- und
Ausblenden, rechts das Detail mit Reitern (Übersicht, Lieferanten, Alternativen, Verwendung, Verlauf). Oben die
intelligente Suche, Favoriten, Zuletzt, Häufig, Vergleich und die Prüfvorschläge. Alles liest und schreibt die
vorhandenen Stammdaten über materialplattform.py; die Tabellenseiten unter Einstellungen → Material bleiben.

Tempo: die Liste ist ein Modell, das in Blöcken von BLOCK Zeilen nachlädt (fetchMore); Suche und Filter laufen auf
der einmal gebauten Variantenliste (neu gebaut, wenn sich Stammdaten ändern).
"""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QFont
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QSplitter,
                               QTableView, QTableWidget, QTableWidgetItem, QTabWidget, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from . import material_ki, materialplattform as mp, stil
from .stammdaten import zahl_als_text

TITEL = "Material"
BLOCK = 500
SPALTEN_MERKER = "material_spalten"
# (Schlüssel, Titel, Nachkommastellen oder None für Text, sichtbar ab Werk)
SPALTEN = (("favorit", "★", None, True), ("profil_id", "Abmessung", None, True), ("werkstoff_id", "Werkstoff", None, True),
           ("kategorie", "Materialgruppe", None, True), ("form", "Profilart", None, False),
           ("wand", "Wand [mm]", 2, False), ("innen", "Innenmaß [mm]", None, False),
           ("kgm", "kg/m", 3, True), ("preis_kg", "€/kg", 2, True), ("preis_m", "€/m", 2, True),
           ("preis_stange", "€/Stange 6 m", 2, False), ("quelle", "Preisquelle", None, False),
           ("handelslaengen", "Handelslängen", None, True), ("lieferant", "Lieferant", None, True),
           ("n_lieferanten", "Lieferanten", 0, False), ("stand", "Preisstand", None, True),
           ("mindest", "Mindestabnahme", 0, False), ("nutzung", "Angebote", 0, True), ("zuletzt", "Zuletzt", None, False),
           ("bestand_stangen", "Bestand", 0, False), ("werkstoff_nr", "Werkstoff-Nr.", None, False),
           ("norm", "Norm", None, False), ("erp_schnitt", "ERP Ø €/m", 2, True),
           ("erp_letzter", "ERP letzter €/m", 2, False), ("erp_datum", "ERP letzter Kauf", None, False),
           ("erp_abw", "ERP Abw. %", 1, True), ("vorschlag_m", "Vorschlag €/m", 2, True),
           ("materialnr", "Materialnr.", None, False), ("material_bez", "Materialbezeichnung", None, False),
           ("handelsname", "Handelsbezeichnung", None, False))
LISTE, MATRIX = "Liste", "Matrix"


def _text(z, feld, stellen):
    v = z.get(feld)
    if feld == "favorit":
        return "★" if v else ""
    if feld == "handelslaengen":
        return " · ".join(f"{x / 1000:g} m".replace(".", ",") for x in v or [])
    if feld == "stand":
        return _datum(v)
    if feld in ("zuletzt", "erp_datum"):
        return _datum(v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return zahl_als_text(v, stellen)
    return "" if v is None else str(v)


def _datum(iso):
    t = str(iso or "")
    return f"{t[8:10]}.{t[5:7]}.{t[:4]}" if len(t) >= 10 else t


class MaterialModell(QAbstractTableModel):
    """Varianten als Tabelle; lädt in Blöcken (canFetchMore/fetchMore), damit 30.000 Zeilen flüssig bleiben."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zeilen, self.geladen = [], 0

    def setzen(self, zeilen):
        self.beginResetModel()
        self.zeilen, self.geladen = list(zeilen), min(BLOCK, len(zeilen))
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.geladen

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(SPALTEN)

    def canFetchMore(self, parent=QModelIndex()):
        return not parent.isValid() and self.geladen < len(self.zeilen)

    def fetchMore(self, parent=QModelIndex()):
        n = min(BLOCK, len(self.zeilen) - self.geladen)
        if n <= 0:
            return
        self.beginInsertRows(QModelIndex(), self.geladen, self.geladen + n - 1)
        self.geladen += n
        self.endInsertRows()

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            return SPALTEN[s][1]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= self.geladen:
            return None
        z = self.zeilen[index.row()]
        feld, _, stellen, _ = SPALTEN[index.column()]
        if role == Qt.DisplayRole:
            return _text(z, feld, stellen)
        if role == Qt.TextAlignmentRole and stellen is not None:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            if feld == "favorit":
                return QBrush(stil.farbe(stil.ORANGE))
            if feld == "stand" and z.get("alter_tage") is not None and z["alter_tage"] > mp.STAND_ALT_TAGE:
                return QBrush(stil.farbe(stil.ORANGE))
            if feld == "vorschlag_m" and z.get("vorschlag_m") is not None:
                return QBrush(stil.farbe(stil.AKZENT))
            if feld == "erp_abw" and z.get("erp_abw") is not None and abs(z["erp_abw"]) > mp.ERP_ABW_PCT:
                return QBrush(stil.farbe(stil.ORANGE))
            if feld in ("preis_m", "preis_kg") and z.get("quelle") == mp.QUELLE_TONNE:
                return QBrush(stil.farbe(stil.TEXT_GRAU))
            if z.get("archiviert") or z.get("inaktiv"):
                return QBrush(stil.farbe(stil.TEXT_GRAU))
        if role == Qt.ToolTipRole:
            if feld in ("preis_m", "preis_kg"):
                return f"Preisquelle: {z.get('quelle')}" + (" (grau: aus dem Tonnenpreis des Werkstoffs)"
                                                            if z.get("quelle") == mp.QUELLE_TONNE else "")
            if feld == "stand" and z.get("alter_tage") is not None:
                return f"{z['alter_tage']} Tage alt"
            if feld == "vorschlag_m" and z.get("vorschlag_m") is not None:
                return (f"Preisvorschlag aus der Historie, Sicherheit {z.get('vorschlag_sicher')}; Begründung und "
                        "Übernehmen im Reiter Preishistorie")
            if feld.startswith("erp_") and z.get("erp_anzahl"):
                return (f"ERP-Einkauf: {z['erp_anzahl']} Käufe, {zahl_als_text(z['erp_meter'], 0)} m, Ø "
                        f"{zahl_als_text(z['erp_schnitt'], 2)} €/m" + (f" (mit {z['erp_ober']})" if z["erp_ober"] else "")
                        + ". Nur Anzeige: ändert die Stammdaten-Preise nicht.")
        if role == Qt.UserRole:
            return z
        return None

    def zeile(self, r):
        return self.zeilen[r] if 0 <= r < len(self.zeilen) else None


class MaterialBereich(QWidget):
    """Hauptseite Material. f = Hauptfenster (db, meldung, offene Angebote)."""
    titel = TITEL
    geaendert = Signal()

    def __init__(self, f):
        super().__init__()
        self.f, self.db = f, f.db
        self.alle_zeilen, self.sichtbar, self.auswahl = [], [], {}
        self._stand = None
        self.ansicht = LISTE
        self.modus = None           # None | "fav" | "zuletzt" | "haeufig"

        # ---- Kopfzeile
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: 40x40x2, 60x40x3 Edelstahl, Rundrohr 42,4x2, S235, 1.4301 …")
        self.suche.setClearButtonEnabled(True)
        self.suche.setToolTip("Live-Suche über Abmessung, Werkstoff, Werkstoff-Nr., Gleichnamen (V2A, AISI 304), "
                              "Materialgruppe und Lieferant; „42x2“ findet auch 42,4 × 2")
        self._takt = QTimer(self)
        self._takt.setSingleShot(True)
        self._takt.setInterval(150)
        self._takt.timeout.connect(self.anwenden)
        self.suche.textChanged.connect(lambda *_: self._takt.start())
        self.schnell = QButtonGroup(self)
        self.schnell.setExclusive(False)
        self.knoepfe = {}
        kopf = QHBoxLayout()
        kopf.addWidget(self.suche, 1)
        for key, text, tipp in (("fav", "★ Favoriten", "Nur Favoriten dieses Arbeitsplatzes"),
                                ("zuletzt", "Zuletzt", "Zuletzt in Angeboten verwendet, neueste zuerst"),
                                ("haeufig", "Häufig", "Am häufigsten in Angeboten verwendet")):
            b = QToolButton()
            b.setText(text)
            b.setCheckable(True)
            b.setToolTip(tipp)
            b.toggled.connect(lambda an, k=key: self.modus_setzen(k if an else None))
            self.knoepfe[key] = b
            kopf.addWidget(b)
        self.umschalter = QComboBox()
        self.umschalter.addItems([LISTE, MATRIX])
        self.umschalter.setToolTip("Liste: eine Zeile je Material · Matrix: Abmessungen × Werkstoffe einer Profilart "
                                   "mit €/m (Lücken und alte Preise auf einen Blick)")
        self.umschalter.currentTextChanged.connect(self.ansicht_setzen)
        kopf.addWidget(self.umschalter)
        self.vergleich_knopf = QPushButton("Vergleichen")
        self.vergleich_knopf.setToolTip("Markierte Materialien nebeneinander (Preis, Gewicht, Güte, Längen, Lieferant, "
                                        "Verschnitt bei den Teilen des offenen Angebots)")
        self.vergleich_knopf.clicked.connect(lambda: self.vergleichen())
        kopf.addWidget(self.vergleich_knopf)
        self.pruef_knopf = QPushButton("Prüfvorschläge")
        self.pruef_knopf.setToolTip("Lokale Prüfung ohne Internet: fehlende Stammdaten, ungewöhnliche Preise, Dubletten, "
                                    "günstigere Lieferanten. Übernommen wird nur per Klick.")
        self.pruef_knopf.clicked.connect(lambda: self.pruefen())
        kopf.addWidget(self.pruef_knopf)
        neu = QPushButton("Neues Material")
        neu.setObjectName("primaer")
        nm = QMenu(neu)
        nm.addAction("Neue Abmessung …", lambda: self.profil_neu())
        nm.addAction("Neuer Werkstoff … (Einstellungen)", lambda: self.stammdaten_zeigen("werkstoffe"))
        nm.addAction("Neuer Lieferantenpreis …", lambda: self.lieferant_neu())
        neu.setMenu(nm)
        kopf.addWidget(neu)
        mehr = QPushButton("Mehr")
        mm = QMenu(mehr)
        mm.addAction("Liste als CSV exportieren …", lambda: self.exportieren())
        mm.addAction("Preisliste eines Lieferanten importieren (CSV/Excel) …", lambda: self.preisliste_importieren())
        mm.addAction("ERP-Einkauf (EK-CSV) einlesen …", lambda: self.erp_einlesen())
        mm.addAction("Profile und Werkstoffe aus dem EK anlegen …", lambda: self.erp_anlegen())
        mm.addSeparator()
        self.alle_box = mm.addAction("Alle Kombinationen Abmessung × Werkstoff zeigen")
        self.alle_box.setCheckable(True)
        self.alle_box.toggled.connect(lambda *_: self.neu_laden(erzwingen=True))
        self.archiv_box = mm.addAction("Archivierte zeigen")
        self.archiv_box.setCheckable(True)
        self.archiv_box.toggled.connect(lambda *_: self.neu_laden(erzwingen=True))
        mm.addAction("Spalten …", lambda: self.spalten_menue().exec(self.mapToGlobal(self.rect().center())))
        mm.addSeparator()
        for name, titel in (("profile", "Profile"), ("werkstoffe", "Werkstoffe"), ("preise", "Preise"),
                            ("lieferlaengen", "Lieferlängen"), ("material_lieferanten", "Material-Lieferanten")):
            mm.addAction(f"Tabelle {titel} öffnen", lambda n=name: self.stammdaten_zeigen(n))
        mehr.setMenu(mm)
        kopf.addWidget(mehr)

        # ---- Filter links
        self.filter_baum = QTreeWidget()
        self.filter_baum.setHeaderHidden(True)
        self.filter_baum.setMinimumWidth(170)
        self.filter_baum.setMaximumWidth(260)
        self.filter_baum.itemChanged.connect(self._filter_geaendert)
        self._filter_bau = False

        # ---- Liste
        self.modell = MaterialModell(self)
        self.tabelle = QTableView()
        self.tabelle.setModel(self.modell)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabelle.setAlternatingRowColors(True)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.verticalHeader().setDefaultSectionSize(24)
        self.tabelle.setSortingEnabled(False)
        kopfz = self.tabelle.horizontalHeader()
        kopfz.setSectionsClickable(True)
        kopfz.sectionClicked.connect(self.sortieren)
        kopfz.setContextMenuPolicy(Qt.CustomContextMenu)
        kopfz.customContextMenuRequested.connect(lambda p: self.spalten_menue().exec(kopfz.mapToGlobal(p)))
        kopfz.setSectionResizeMode(QHeaderView.Interactive)
        self.tabelle.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabelle.customContextMenuRequested.connect(lambda p: self.kontextmenue(p))
        self.tabelle.selectionModel().currentRowChanged.connect(lambda *_: self.detail_zeigen())
        self.tabelle.doubleClicked.connect(lambda *_: self.detail.setCurrentIndex(0))
        self._sort = (None, False)

        # ---- Matrix
        self.matrix_form = QComboBox()
        self.matrix_form.currentTextChanged.connect(lambda *_: self.matrix_fuellen())
        self.matrix = QTableWidget()
        self.matrix.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.matrix.cellDoubleClicked.connect(self._matrix_doppelklick)
        self.matrix_seite = QWidget()
        ml = QVBoxLayout(self.matrix_seite)
        ml.setContentsMargins(0, 0, 0, 0)
        mk = QHBoxLayout()
        mk.addWidget(QLabel("Profilart"))
        mk.addWidget(self.matrix_form)
        self.matrix_legende = QLabel("Zelle = €/m · grün: Preis aktuell · gelb: älter als 30 Tage · grau: aus "
                                     "Tonnenpreis · rot: kein Preis · Doppelklick: Material in der Liste zeigen")
        self.matrix_legende.setWordWrap(True)
        mk.addWidget(self.matrix_legende, 1)
        ml.addLayout(mk)
        ml.addWidget(self.matrix, 1)

        # ---- Detail rechts
        self.detail = QTabWidget()
        self.detail.setMinimumWidth(390)
        self.ueber = QLabel()
        self.ueber.setTextFormat(Qt.RichText)
        self.ueber.setWordWrap(True)
        self.ueber.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.ueber.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.bild = QLabel()
        uw = QWidget()
        ul = QVBoxLayout(uw)
        ul.addWidget(self.bild)
        ul.addWidget(self.ueber, 1)
        self.detail.addTab(uw, "Übersicht")
        self.lief_tabelle = QTableWidget(0, 7)
        self.lief_tabelle.setHorizontalHeaderLabels(["Lieferant", "Preis", "€/m", "Länge", "Gültig bis", "Lieferzeit",
                                                     "Artikelnr."])
        self.lief_tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.lief_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lief_tabelle.verticalHeader().setVisible(False)
        lw = QWidget()
        ll = QVBoxLayout(lw)
        ll.addWidget(self.lief_tabelle, 1)
        lk = QHBoxLayout()
        b1 = QPushButton("Neu …")
        b1.clicked.connect(lambda: self.lieferant_neu())
        b2 = QPushButton("Als Preis übernehmen")
        b2.setToolTip("Schreibt Preis, Basis, Lieferant und Gültig ab nach 'Preise' (mit Lieferlänge nach "
                      "'Lieferlängen'); der Preiswächter meldet betroffene offene Angebote, festgeschriebene bleiben")
        b2.clicked.connect(lambda: self.lieferant_uebernehmen())
        b3 = QPushButton("Löschen")
        b3.clicked.connect(lambda: self.lieferant_loeschen())
        for b in (b1, b2, b3):
            lk.addWidget(b)
        ll.addLayout(lk)
        self.detail.addTab(lw, "Lieferanten")
        self.alt_liste = QListWidget()
        self.alt_liste.setWordWrap(True)
        self.detail.addTab(self.alt_liste, "Alternativen")
        self.verwendung = QListWidget()
        self.verwendung.itemDoubleClicked.connect(lambda it: self._angebot_oeffnen(it.data(Qt.UserRole)))
        self.detail.addTab(self.verwendung, "Verwendung")
        hw = QWidget()
        hl = QVBoxLayout(hw)
        self.kurve = PreisKurve()
        hl.addWidget(self.kurve)
        self.kurve_text = QLabel()
        self.kurve_text.setWordWrap(True)
        self.kurve_text.setTextFormat(Qt.RichText)
        hl.addWidget(self.kurve_text)
        self.vorschlag_box = QLabel()
        self.vorschlag_box.setWordWrap(True)
        self.vorschlag_box.setTextFormat(Qt.RichText)
        self.vorschlag_knopf = QPushButton("Vorschlag übernehmen")
        self.vorschlag_knopf.setToolTip("Schreibt den vorgeschlagenen Preis nach 'Preise' (Gültig ab heute, in der "
                                        "Preisbasis der Zeile); nur mit Admin-Freischaltung, Eintrag im KI-Protokoll")
        self.vorschlag_knopf.clicked.connect(lambda: self.vorschlag_uebernehmen())
        vk = QHBoxLayout()
        vk.addWidget(self.vorschlag_box, 1)
        vk.addWidget(self.vorschlag_knopf, 0, Qt.AlignTop)
        hl.addLayout(vk)
        self.monate_tab = QTableWidget(0, 7)
        self.monate_tab.setHorizontalHeaderLabels(["Monat", "Käufe", "Meter", "Ø €/m", "Min–Max €/m",
                                                   "Stammdaten €/m", "Abw. %"])
        self.monate_tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.monate_tab.verticalHeader().setVisible(False)
        self.monate_tab.setToolTip("Historie je Monat: ERP-Käufe (nur die, die zählen, im Ø), Stammdatenpreis am "
                                   "Monatsende und Ereignisse (Preisänderungen, Lieferantenpreise)")
        self.historie_reiter = QTabWidget()
        self.historie_reiter.addTab(self.monate_tab, "Je Monat")
        self.verlauf = QListWidget()
        self.historie_reiter.addTab(self.verlauf, "Alle Einträge")
        hl.addWidget(self.historie_reiter, 1)
        self.erp_knopf = QPushButton("ERP-Käufe …")
        self.erp_knopf.setToolTip("Alle Käufe dieses Materials aus der ERP-CSV; Ausreißer von Hand mitrechnen oder "
                                  "weglassen")
        self.erp_knopf.clicked.connect(lambda: self.erp_kaeufe())
        hl.addWidget(self.erp_knopf, 0, Qt.AlignLeft)
        self.detail.addTab(hw, "Preishistorie")

        self.stapel = QSplitter(Qt.Horizontal)
        self.stapel.addWidget(self.filter_baum)
        mitte = QWidget()
        ml2 = QVBoxLayout(mitte)
        ml2.setContentsMargins(0, 0, 0, 0)
        ml2.addWidget(self.tabelle, 1)
        ml2.addWidget(self.matrix_seite, 1)
        self.matrix_seite.setVisible(False)
        self.fuss = QLabel()
        self.fuss.setObjectName("grau")
        ml2.addWidget(self.fuss)
        self.stapel.addWidget(mitte)
        self.stapel.addWidget(self.detail)
        self.stapel.setStretchFactor(1, 1)
        self.stapel.setSizes([200, 760, 420])

        self.uebersicht = QWidget()
        ul = QVBoxLayout(self.uebersicht)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addLayout(kopf)
        ul.addWidget(self.stapel, 1)
        from . import material_bereiche
        material_bereiche.einrichten(self, self.uebersicht)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.bereiche, 1)
        self._spalten_lesen()

    # ------------------------------------------------------------------ Daten
    def neu_laden(self, erzwingen=False):
        """Varianten neu bauen, wenn sich die Stammdaten geändert haben (oder erzwingen)."""
        try:
            stand = self.db.stammdaten_stand()
        except Exception:           # noqa: BLE001
            stand = None
        schluessel = (stand, self.alle_box.isChecked(), self.archiv_box.isChecked(), len(mp.favoriten(self.db)),
                      self._erp_stand())
        if not erzwingen and schluessel == self._stand and self.alle_zeilen:
            self.anwenden()
            return
        self._stand = schluessel
        self._erp = mp.erp_gruppen(self.db)
        self.alle_zeilen = mp.varianten(self.db.kontext(), self.db.tabellen(), self.db.zeilen(mp.LIEFERANTEN_TABELLE),
                                        mp.nutzung(self.db), mp.lager_bestand(self.db), mp.favoriten(self.db),
                                        alle=self.alle_box.isChecked(), mit_archiv=self.archiv_box.isChecked(),
                                        erp=self._erp, stamm=self.db.zeilen(mp.STAMM_TABELLE))
        from . import material_historie as mh
        for schl, v in mh.alle_vorschlaege(self.db, self.alle_zeilen, self._erp).items():
            for z in self.alle_zeilen:
                if (z["profil_id"], z["werkstoff_id"]) == schl:
                    z.update(vorschlag_m=v["preis_m"], vorschlag_sicher=v["sicherheit"])
        self.filter_fuellen()
        self.anwenden()

    def _erp_stand(self):
        try:
            return tuple(self.db.con.execute("SELECT COUNT(*), MAX(importiert) FROM erp_kaeufe").fetchone())
        except Exception:           # noqa: BLE001
            return None

    def showEvent(self, e):
        super().showEvent(e)
        self.neu_laden()

    def anwenden(self):
        zeilen = self.alle_zeilen
        if self.modus == "fav":
            zeilen = [z for z in zeilen if z.get("favorit")]
        elif self.modus == "zuletzt":
            zeilen = mp.zuletzt(zeilen, 50)
        elif self.modus == "haeufig":
            zeilen = mp.haeufig(zeilen, 50)
        zeilen = mp.filtern(zeilen, self.auswahl)
        zeilen = mp.suchen(zeilen, self.suche.text())
        feld, ab = self._sort
        if feld:
            zeilen = sorted(zeilen, key=lambda z: (z.get(feld) is None, z.get(feld) if not isinstance(z.get(feld), list)
                                                   else len(z.get(feld))), reverse=ab)
        self.sichtbar = zeilen
        self.modell.setzen(zeilen)
        arch = sum(1 for z in self.alle_zeilen if z.get("archiviert"))
        self.fuss.setText(f"{len(zeilen)} von {len(self.alle_zeilen)} Materialien"
                          + (f" · {arch} archiviert" if arch else "")
                          + ("" if self.alle_box.isChecked() else " · nur Materialien mit Preis, Lieferant oder "
                             "Verwendung (Mehr → Alle Kombinationen)"))
        if zeilen:
            self.tabelle.selectRow(0)
        self.detail_zeigen()
        if self.ansicht == MATRIX:
            self.matrix_fuellen()

    def modus_setzen(self, modus):
        for k, b in self.knoepfe.items():
            b.blockSignals(True)
            b.setChecked(k == modus)
            b.blockSignals(False)
        self.modus = modus
        self.anwenden()

    def sortieren(self, spalte):
        feld = SPALTEN[spalte][0]
        alt, ab = self._sort
        self._sort = (feld, not ab if alt == feld else False)
        self.anwenden()

    # ------------------------------------------------------------------ Filter
    def filter_fuellen(self):
        self._filter_bau = True
        self.filter_baum.clear()
        fac = mp.facetten(self.alle_zeilen)
        for feld, titel in mp.FILTER:
            werte = fac.get(feld) or []
            if not werte:
                continue
            g = QTreeWidgetItem([titel])
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            self.filter_baum.addTopLevelItem(g)
            for w, n in werte[:40]:
                it = QTreeWidgetItem([f"{w}  ({n})"])
                it.setData(0, Qt.UserRole, (feld, w))
                it.setCheckState(0, Qt.Checked if w in self.auswahl.get(feld, ()) else Qt.Unchecked)
                g.addChild(it)
            g.setExpanded(feld in ("kategorie", "form", "zustand") or bool(self.auswahl.get(feld)))
        self._filter_bau = False

    def _filter_geaendert(self, it, _spalte):
        if self._filter_bau:
            return
        d = it.data(0, Qt.UserRole)
        if not d:
            return
        feld, w = d
        s = set(self.auswahl.get(feld, ()))
        (s.add if it.checkState(0) == Qt.Checked else s.discard)(w)
        self.auswahl[feld] = s
        self.anwenden()

    def filter_setzen(self, feld, werte):
        """Filter von außen (Tests, Sprung aus dem Angebot): {Werte} für ein Feld."""
        self.auswahl[feld] = set(werte)
        self.filter_fuellen()
        self.anwenden()

    # ------------------------------------------------------------------ Spalten
    def _spalten_lesen(self):
        w = self.db.einstellung(SPALTEN_MERKER)
        an = set(w) if isinstance(w, list) else {s[0] for s in SPALTEN if s[3]}
        for i, s in enumerate(SPALTEN):
            self.tabelle.setColumnHidden(i, s[0] not in an)

    def spalten_menue(self):
        m = QMenu(self)
        for i, s in enumerate(SPALTEN):
            a = m.addAction(s[1])
            a.setCheckable(True)
            a.setChecked(not self.tabelle.isColumnHidden(i))
            a.toggled.connect(lambda an, i=i: self.spalte_setzen(i, an))
        m.addSeparator()
        m.addAction("Spalten wie ab Werk", lambda: self.spalten_zuruecksetzen())
        return m

    def spalte_setzen(self, i, an):
        self.tabelle.setColumnHidden(i, not an)
        self.db.einstellung_setzen(SPALTEN_MERKER, [s[0] for j, s in enumerate(SPALTEN)
                                                    if not self.tabelle.isColumnHidden(j)])

    def spalten_zuruecksetzen(self):
        self.db.einstellung_setzen(SPALTEN_MERKER, None)
        self._spalten_lesen()

    # ------------------------------------------------------------------ Auswahl
    def markierte(self):
        rows = sorted({i.row() for i in self.tabelle.selectionModel().selectedRows()})
        return [self.modell.zeile(r) for r in rows if self.modell.zeile(r) is not None]

    def aktuelle(self):
        i = self.tabelle.currentIndex()
        z = self.modell.zeile(i.row()) if i.isValid() else None
        return z or (self.markierte() or [None])[0]

    def auswaehlen(self, profil_id, werkstoff_id):
        """Material in der Liste markieren (lädt nach, bis es sichtbar ist). True, wenn gefunden."""
        for r, z in enumerate(self.modell.zeilen):
            if mp.schluessel(z) == (profil_id, werkstoff_id):
                while self.modell.geladen <= r:
                    self.modell.fetchMore()
                self.tabelle.selectRow(r)
                self.tabelle.scrollTo(self.modell.index(r, 1))
                self.detail_zeigen()
                return True
        return False

    # ------------------------------------------------------------------ Detail
    def detail_zeigen(self):
        z = self.aktuelle()
        self.lief_tabelle.setRowCount(0)
        self.alt_liste.clear()
        self.verwendung.clear()
        self.verlauf.clear()
        if not z:
            self.ueber.setText("Kein Material gewählt.")
            self.bild.clear()
            return
        k = self.db.kontext()
        pr = k.profile.get(z["profil_id"]) or {}
        try:
            from .meterpreis_dialog import querschnitt_pixmap
            self.bild.setPixmap(querschnitt_pixmap(pr, 96, stil.umsetzen(stil.AKZENT)))
        except Exception:           # noqa: BLE001
            self.bild.clear()
        exakt = self._preis_exakt(z)
        zeilen = [("Materialgruppe", z["kategorie"] or "–"), ("Werkstoff", " · ".join(
                  x for x in (z["werkstoff"], z["werkstoff_nr"], z["norm"]) if x) or z["werkstoff_id"]),
                  ("Profilart", z["form"]), ("Innenmaß", z["innen"] or "–"),
                  ("Gewicht", f"{zahl_als_text(z['kgm'], 3)} kg/m" if z["kgm"] is not None else "fehlt (Dichte?)"),
                  ("Dichte", f"{zahl_als_text(z['dichte'], 2)} kg/dm³" if z["dichte"] is not None else "fehlt"),
                  ("Preis", f"{zahl_als_text(z['preis_kg'], 2)} €/kg · {zahl_als_text(z['preis_m'], 2)} €/m"
                   if z["preis_m"] is not None else "fehlt"),
                  ("Preisquelle", z["quelle"] + (f", Stand {_datum(z['stand'])}" if z["stand"] else "")),
                  ("Im Angebot (6 m, mit Teuerung)", f"{zahl_als_text(exakt, 2)} €/m" if exakt is not None else "–"),
                  ("Stange 6 m", f"{zahl_als_text(z['preis_stange'], 2)} €" if z["preis_stange"] is not None else "–"),
                  ("Handelslängen", _text(z, "handelslaengen", None) or "Stangenlänge des Angebots"),
                  ("Lieferanten", ", ".join(z["lieferanten"]) or "–"),
                  ("Mindestabnahme", f"{int(z['mindest'])} Stangen" if z["mindest"] else "–"),
                  ("In Angeboten", f"{z['nutzung']}" + (f", zuletzt {_datum(z['zuletzt'])}" if z["zuletzt"] else "")),
                  ]
        if z.get("erp_anzahl"):
            zeilen.append(("ERP-Einkauf", f"Ø {zahl_als_text(z['erp_schnitt'], 2)} €/m ({z['erp_anzahl']} Käufe, "
                           f"{zahl_als_text(z['erp_meter'], 0)} m)" + (
                               f", {zahl_als_text(z['erp_abw'], 1)} % zum Stammdatenpreis"
                               if z.get("erp_abw") is not None else "")))
        if z.get("bestand_stangen") is not None:
            zeilen.append(("Lager (verfügbar)", f"{z['bestand_stangen']} Stangen, {z['bestand_reste']} Reststücke"))
        if z.get("archiviert"):
            zeilen.append(("Archiviert", "ja: nicht in neuen Auswahllisten"))
        grau = stil.umsetzen(stil.TEXT_GRAU)
        html = (f"<b style='font-size:14px'>{z['profil_id']} · {z['werkstoff_id']}</b>"
                + ("  <span style='color:#B35C00'>★</span>" if z["favorit"] else "")
                + "<table cellspacing='0' cellpadding='2'>"
                + "".join(f"<tr><td style='color:{grau}; padding-right:10px'>{a}</td><td>{b}</td></tr>"
                          for a, b in zeilen) + "</table>")
        self.ueber.setText(html)
        lief = [lz for lz in self.db.zeilen(mp.LIEFERANTEN_TABELLE) if mp.schluessel(lz) == mp.schluessel(z)]
        self._lief = lief
        self.lief_tabelle.setRowCount(len(lief))
        for r, lz in enumerate(lief):
            pm = mp.je_meter(lz.get("basis"), lz.get("preis"), z["kgm"], lz.get("laenge") or 6000)
            werte = [lz.get("lieferant") or "", f"{zahl_als_text(lz.get('preis'), 2)} {lz.get('basis') or ''}",
                     zahl_als_text(pm, 2) if pm is not None else "–", str(lz.get("laenge") or ""),
                     _datum(lz.get("gueltig_bis")), f"{lz['lieferzeit']} T" if lz.get("lieferzeit") else "",
                     lz.get("artikelnr") or ""]
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if not mp.gueltig(lz):
                    it.setForeground(QBrush(stil.farbe(stil.TEXT_GRAU)))
                    it.setToolTip("Preis nicht (mehr) gültig")
                self.lief_tabelle.setItem(r, c, it)
        self.lief_tabelle.resizeColumnsToContents()
        alt = mp.alternativen(z, lief, k, self.db.tabellen())
        for a in alt:
            t = f"{a['art']}: {a['text']}"
            if a["preis_m"] is not None:
                t += f" · {zahl_als_text(a['preis_m'], 2)} €/m"
            if a["ersparnis_pct"] is not None:
                t += f" ({zahl_als_text(a['ersparnis_pct'], 1)} % {'günstiger' if a['ersparnis_pct'] > 0 else 'teurer'})"
            self.alt_liste.addItem(t)
        if not alt:
            self.alt_liste.addItem("Keine Alternative mit demselben Werkstoff (andere Lieferanten, Handelslängen).")
        for a in self._verwendung(z):
            it = QListWidgetItem(f"{a['nummer']} · {a.get('kunde') or ''} · {_datum(a.get('geaendert'))}")
            it.setData(Qt.UserRole, a["id"])
            self.verwendung.addItem(it)
        g = self._erp.get((z["profil_id"], z["werkstoff_id"])) if hasattr(self, "_erp") else None
        pp = mp.preis_punkte(self.db, z["profil_id"], z["werkstoff_id"], gruppe=g or {})
        self.kurve.setzen(pp, z.get("preis_m"))
        teile = []
        if pp["stamm"]:
            erster = pp["stamm"][0][1]
            teile.append(f"Stammdaten {zahl_als_text(pp['stamm'][-1][1], 2)} €/m"
                         + (f" ({zahl_als_text((pp['stamm'][-1][1] / erster - 1) * 100, 1)} % seit "
                            f"{pp['stamm'][0][0].strftime('%d.%m.%Y')})" if erster and len(pp["stamm"]) > 1 else ""))
        if z.get("erp_anzahl"):
            teile.append(f"ERP-Einkauf Ø {zahl_als_text(z['erp_schnitt'], 2)} €/m aus {z['erp_anzahl']} Käufen, "
                         f"zuletzt {zahl_als_text(z['erp_letzter'], 2)} €/m am {_datum(z['erp_datum'])}"
                         + (f" (mit {z['erp_ober']})" if z["erp_ober"] else ""))
        self.kurve_text.setText(" · ".join(teile) or "Noch keine Preisstände, Käufe oder Lieferantenpreise.")
        self.erp_knopf.setEnabled(bool(g))
        from . import material_historie as mh
        tr = mh.trend(pp)
        if tr:
            teile = [f"Ø {m} Mon. {zahl_als_text(tr[f'mittel_{m}'], 2)}" for m in (3, 6, 12) if tr.get(f"mittel_{m}")]
            if tr.get("pct_jahr") is not None:
                teile.append(f"Trend {zahl_als_text(tr['pct_jahr'], 1)} % je Jahr")
            self.kurve_text.setText(self.kurve_text.text() + "<br>" + " · ".join(teile))
        self._vorschlag = mh.vorschlag(z, pp, kg_ref=mh.kg_referenz(self.alle_zeilen, self._erp)
                                       if getattr(self, "_erp", None) else None)
        v = self._vorschlag
        if v:
            farbe = stil.umsetzen({mh.HOCH: stil.GRUEN, mh.MITTEL: stil.ORANGE}.get(v["sicherheit"], stil.TEXT_GRAU))
            self.vorschlag_box.setText(
                f"<b>Preisvorschlag {zahl_als_text(v['preis_m'], 2)} €/m</b>"
                + (f" ({'+' if v['abw'] > 0 else ''}{zahl_als_text(v['abw'], 1)} %)" if v["abw"] is not None else "")
                + f" · Sicherheit <span style='color:{farbe}'><b>{v['sicherheit']}</b></span><br>"
                + f"<span style='color:{stil.umsetzen(stil.TEXT_GRAU)}'>{v['begruendung']}</span>")
        else:
            self.vorschlag_box.setText("Kein Preisvorschlag: der heutige Preis passt zur Historie oder es fehlen "
                                       "Käufe und Lieferantenpreise.")
        self.vorschlag_knopf.setEnabled(bool(v))
        ms = mh.monate(pp)
        self.monate_tab.setRowCount(len(ms))
        for r, m in enumerate(ms):
            werte = [f"{m['monat'][5:]}.{m['monat'][:4]}", str(m["kaeufe"] or ""),
                     zahl_als_text(m["meter"], 0) if m["meter"] else "",
                     zahl_als_text(m["schnitt"], 2) if m["schnitt"] is not None else "",
                     f"{zahl_als_text(m['min'], 2)}–{zahl_als_text(m['max'], 2)}" if m["min"] is not None else "",
                     zahl_als_text(m["stamm"], 2) if m["stamm"] is not None else "",
                     zahl_als_text(m["abw"], 1) if m["abw"] is not None else ""]
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if c:
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if m["ereignisse"]:
                    it.setToolTip("\n".join(m["ereignisse"]))
                if c == 6 and m["abw"] is not None and abs(m["abw"]) > mp.ERP_ABW_PCT:
                    it.setForeground(QBrush(stil.farbe(stil.ORANGE)))
                self.monate_tab.setItem(r, c, it)
        self.monate_tab.resizeColumnsToContents()
        for h in mp.historie(self.db, z["profil_id"], z["werkstoff_id"])[:300]:
            self.verlauf.addItem(f"{_datum(h['zeit']) if len(h['zeit']) == 10 else h['zeit']} · {h['art']} · {h['text']}")

    def _preis_exakt(self, z):
        """€/m wie im Angebot (rechnen.meterpreis mit Teuerung, Lieferlängen, Mindestabnahme-Regeln)."""
        from . import rechnen
        try:
            p = dict(profil_id=z["profil_id"], werkstoff_id=z["werkstoff_id"], laenge=1000, stueck=1)
            kopf = dict(stange=6000)
            return rechnen.meterpreis(p, kopf, [p], self.db.kontext(), self.db.tabellen())[0]
        except Exception:           # noqa: BLE001
            return None

    def _verwendung(self, z, anzahl=100):
        try:
            rows = self.db.con.execute(
                "SELECT DISTINCT a.id, a.nummer, a.kunde, a.geaendert FROM positionen p JOIN angebote a ON "
                "a.id = p.angebot_id WHERE p.profil_id=? AND p.werkstoff_id=? ORDER BY a.geaendert DESC LIMIT ?",
                (z["profil_id"], z["werkstoff_id"], anzahl)).fetchall()
            return [dict(id=r[0], nummer=r[1], kunde=r[2], geaendert=r[3]) for r in rows]
        except Exception:           # noqa: BLE001
            return []

    def _angebot_oeffnen(self, angebot_id):
        if angebot_id and hasattr(self.f, "angebot_oeffnen"):
            self.f.angebot_oeffnen(angebot_id)

    # ------------------------------------------------------------------ Matrix
    def ansicht_setzen(self, name):
        self.ansicht = name
        self.tabelle.setVisible(name == LISTE)
        self.matrix_seite.setVisible(name == MATRIX)
        if name == MATRIX:
            formen = sorted({z["form"] for z in self.alle_zeilen if z["form"]})
            alt = self.matrix_form.currentText()
            self.matrix_form.blockSignals(True)
            self.matrix_form.clear()
            self.matrix_form.addItems(formen)
            if alt in formen:
                self.matrix_form.setCurrentText(alt)
            self.matrix_form.blockSignals(False)
            self.matrix_fuellen()

    def matrix_fuellen(self):
        form = self.matrix_form.currentText()
        zeilen = [z for z in self.sichtbar if z["form"] == form]
        profile = sorted({z["profil_id"] for z in zeilen}, key=lambda p: next(
            ((x["a"] or 0, x["b"] or 0, x["wand"] or 0) for x in zeilen if x["profil_id"] == p), (0, 0, 0)))
        werkstoffe = sorted({z["werkstoff_id"] for z in zeilen}, key=lambda w: (
            next((x["kategorie"] for x in zeilen if x["werkstoff_id"] == w), ""), w))
        if len(profile) > 400:
            profile = profile[:400]
        idx = {mp.schluessel(z): z for z in zeilen}
        self.matrix.clear()
        self.matrix.setRowCount(len(profile))
        self.matrix.setColumnCount(len(werkstoffe))
        self.matrix.setHorizontalHeaderLabels(werkstoffe)
        self.matrix.setVerticalHeaderLabels(profile)
        farben = dict(ok=stil.GRUEN_FLAECHE, alt=stil.GELB_FLAECHE, ton=stil.FLAECHE, fehlt=stil.ROT_FLAECHE)
        for r, p in enumerate(profile):
            for c, w in enumerate(werkstoffe):
                z = idx.get((p, w))
                if z is None:
                    continue
                art = ("fehlt" if z["quelle"] == mp.QUELLE_FEHLT else "ton" if z["quelle"] == mp.QUELLE_TONNE
                       else "alt" if (z["alter_tage"] or 0) > mp.STAND_ALT_TAGE else "ok")
                it = QTableWidgetItem(zahl_als_text(z["preis_m"], 2) if z["preis_m"] is not None else "–")
                it.setTextAlignment(Qt.AlignCenter)
                it.setBackground(QBrush(stil.farbe(farben[art])))
                it.setToolTip(f"{p} · {w}: {z['quelle']}" + (f", Stand {_datum(z['stand'])}" if z["stand"] else ""))
                it.setData(Qt.UserRole, (p, w))
                self.matrix.setItem(r, c, it)
        self.matrix.resizeColumnsToContents()

    def _matrix_doppelklick(self, r, c):
        it = self.matrix.item(r, c)
        if it is None:
            return
        p, w = it.data(Qt.UserRole)
        self.umschalter.setCurrentText(LISTE)
        self.auswaehlen(p, w)

    # ------------------------------------------------------------------ Schreibrechte
    def darf(self, *tabellen):
        """Schreiben in diese Stammdaten erlaubt? Geschützte Tabellen (Admin-Schutz, z. B. Preise, Werkstoffe) nur mit
        Admin-Freischaltung, wie auf den Tabellenseiten der Einstellungen; im Lesemodus nie. Sonst Meldung."""
        if getattr(self.db, "nur_lesen", False):
            self.f.meldung("Lesemodus: Änderungen sind gerade nicht möglich.", fehler=True)
            return False
        from . import admin_schutz
        gesperrt = sorted(set(tabellen) & admin_schutz.tabellen_geschuetzt(self.db))
        if gesperrt and not admin_schutz.ist_admin(self.db):
            from .stammdaten import TABELLE
            namen = ", ".join(TABELLE[t].titel if t in TABELLE else t for t in gesperrt)
            self.f.meldung(f"Nur Admin: {namen} ändert nur der Admin. Unter Einstellungen „Als Admin "
                           "freischalten …“, dann hier erneut.", fehler=True)
            return False
        return True

    # ------------------------------------------------------------------ Kontextmenü und Aktionen
    def kontextmenue(self, punkt=None, zeigen=True):
        m = QMenu(self.tabelle)
        zs = self.markierte()
        z = self.aktuelle()
        if z:
            m.addAction("Favorit entfernen" if z["favorit"] else "Als Favorit markieren", lambda: self.favorit(z))
        m.addAction(f"Vergleichen ({len(zs)})", lambda: self.vergleichen()).setEnabled(len(zs) >= 2)
        seite = self.offenes_angebot()
        a = m.addAction("Den markierten Positionen des offenen Angebots zuweisen",
                        lambda: self.zuweisen())
        a.setEnabled(bool(z and seite is not None))
        a.setToolTip("Setzt Abmessung und Werkstoff an den markierten Rohrlaser-Positionen des zuletzt gezeigten "
                     "Angebots; danach neu optimieren")
        m.addSeparator()
        m.addAction("Abmessung duplizieren …", lambda: self.duplizieren()).setEnabled(bool(z))
        m.addAction("Werkstoff duplizieren …", lambda: self.werkstoff_duplizieren()).setEnabled(bool(z))
        m.addAction(f"Mehrere ändern ({len(zs)}) …", lambda: self.mehrfach()).setEnabled(bool(zs))
        if z:
            m.addAction("Abmessung zurückholen" if z["archiviert"] else "Abmessung archivieren",
                        lambda: self.archivieren("profile", z["profil_id"], not z["archiviert"]))
            m.addAction("Werkstoff archivieren", lambda: self.archivieren("werkstoffe", z["werkstoff_id"], True))
        m.addSeparator()
        m.addAction("Neuer Lieferantenpreis …", lambda: self.lieferant_neu()).setEnabled(bool(z))
        m.addAction("In Tabelle Preise zeigen", lambda: self.stammdaten_zeigen("preise"))
        m.addAction("Als CSV exportieren (markierte) …", lambda: self.exportieren(zs)).setEnabled(bool(zs))
        if zeigen:
            m.exec(self.tabelle.viewport().mapToGlobal(punkt) if punkt is not None else self.tabelle.mapToGlobal(
                self.tabelle.rect().center()))
        return m

    def favorit(self, z):
        mp.favorit_setzen(self.db, z["profil_id"], z["werkstoff_id"], not z["favorit"])
        z["favorit"] = not z["favorit"]
        self.modell.layoutChanged.emit()
        self.detail_zeigen()

    def archivieren(self, tabelle, wert, an, frage=True):
        if not self.darf(tabelle):
            return False
        if an and frage and not getattr(self.f, "stumm", False):
            if QMessageBox.question(self, "Archivieren", f"„{wert}“ archivieren?\n\nEs erscheint nicht mehr in neuen "
                                    "Auswahllisten. Bestehende Angebote rechnen unverändert weiter; nichts wird "
                                    "gelöscht. Zurückholen geht über Mehr → Archivierte zeigen.") != QMessageBox.Yes:
                return False
        mp.archivieren(self.db, tabelle, wert, an)
        self.f.meldung(f"{wert} {'archiviert' if an else 'zurückgeholt'}.")
        self.neu_laden(erzwingen=True)
        return True

    def duplizieren(self, neue_id=None, wand=None):
        z = self.aktuelle()
        if not z:
            return None
        if not self.darf("profile"):
            return None
        if neue_id is None:
            neue_id, ok = QInputDialog.getText(self, "Abmessung duplizieren", "Neue Profil-ID:", text=z["profil_id"])
            if not ok:
                return None
        werte = {} if wand is None else dict(wand=wand)
        try:
            mp.duplizieren(self.db, z["profil_id"], neue_id.strip(), **werte)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.f.meldung(f"Abmessung {neue_id} angelegt (Maße unter Einstellungen → Profile anpassen).")
        self.neu_laden(erzwingen=True)
        return neue_id

    def werkstoff_duplizieren(self, neue_id=None):
        z = self.aktuelle()
        if not z:
            return None
        if not self.darf("werkstoffe"):
            return None
        if neue_id is None:
            neue_id, ok = QInputDialog.getText(self, "Werkstoff duplizieren", "Neue Werkstoff-ID:",
                                               text=z["werkstoff_id"] + " Kopie")
            if not ok:
                return None
        try:
            mp.werkstoff_duplizieren(self.db, z["werkstoff_id"], neue_id.strip())
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.f.meldung(f"Werkstoff {neue_id} angelegt.")
        self.neu_laden(erzwingen=True)
        return neue_id

    def mehrfach(self, dialog=None):
        zs = self.markierte()
        if not zs:
            return None
        d = MehrfachDialog(self, len(zs))
        if not (dialog(d) if dialog else d.exec() == QDialog.Accepted):
            return None
        tabelle, feld, wert, faktor = d.ergebnis()
        if not self.darf(tabelle):
            return None
        try:
            n = mp.mehrfach_aendern(self.db, zs, tabelle, feld, wert, preis_faktor=faktor)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.f.meldung(f"{n} Zeile(n) geändert.")
        self.neu_laden(erzwingen=True)
        return n

    def offenes_angebot(self):
        """Ziel für „Zuweisen“: das Angebot, aus dem gesprungen wurde, sonst das zuletzt geöffnete; None ohne."""
        offen = list(getattr(self.f, "offen", {}).values())
        if getattr(self, "ziel_seite", None) in offen:
            return self.ziel_seite
        return offen[-1] if offen else None

    def zuweisen(self, seite=None, zeilen=None):
        """Abmessung und Werkstoff an markierte Rohrlaser-Positionen eines offenen Angebots. Ergebnis: Anzahl."""
        z = self.aktuelle()
        seite = seite or self.offenes_angebot()
        if not z or seite is None:
            return 0
        if getattr(self.db, "nur_lesen", False) or (hasattr(seite, "fremd") and seite.fremd()):
            self.f.meldung("Dieses Angebot lässt sich hier nicht ändern (Lesemodus oder Angebot eines Kollegen).",
                           fehler=True)
            return 0
        from . import rechnen
        zeilen = zeilen if zeilen is not None else seite._markierte_zeilen()
        ids = [seite.positionen[r]["id"] for r in zeilen if r < len(seite.positionen)
               and not rechnen.kein_laserteil(seite.positionen[r])]
        if not ids:
            self.f.meldung("Im Angebot ist keine Rohrlaser-Position markiert.", fehler=True)
            return 0
        for i in ids:
            self.db.position_aendern(i, "profil_id", z["profil_id"])
            self.db.position_aendern(i, "werkstoff_id", z["werkstoff_id"])
        seite.neu_laden()
        self.f.meldung(f"{z['profil_id']} · {z['werkstoff_id']} an {len(ids)} Position(en) von {seite.titel()} "
                       "gesetzt; bitte neu optimieren.")
        return len(ids)

    # ------------------------------------------------------------------ Lieferanten
    def lieferant_neu(self, werte=None, dialog=None):
        z = self.aktuelle()
        if not z or not self.darf(mp.LIEFERANTEN_TABELLE, "zukauf_lieferanten"):
            return None
        d = LieferantDialog(self, z, self.db.kontext().zukauf_lieferanten)
        if werte is not None:
            d.setzen(werte)
        if not (dialog(d) if dialog else d.exec() == QDialog.Accepted):
            return None
        w = d.werte()
        if not w.get("lieferant") or w.get("preis") is None:
            self.f.meldung("Lieferant und Preis angeben.", fehler=True)
            return None
        if w["lieferant"] not in self.db.kontext().zukauf_lieferanten:
            self.db.neu("zukauf_lieferanten", dict(name=w["lieferant"]))
        try:
            i = self.db.neu(mp.LIEFERANTEN_TABELLE, dict(w, profil_id=z["profil_id"], werkstoff_id=z["werkstoff_id"]))
        except Exception as e:      # noqa: BLE001  (doppelter Schlüssel)
            self.f.meldung(f"Nicht gespeichert: {e}", fehler=True)
            return None
        self.neu_laden(erzwingen=True)
        self.auswaehlen(z["profil_id"], z["werkstoff_id"])
        self.detail.setCurrentIndex(1)
        return i

    def _lief_markiert(self):
        r = self.lief_tabelle.currentRow()
        lief = getattr(self, "_lief", [])
        return lief[r] if 0 <= r < len(lief) else None

    def lieferant_uebernehmen(self, lz=None):
        lz = lz or self._lief_markiert()
        if not lz:
            self.f.meldung("Erst einen Lieferanten in der Liste markieren.", fehler=True)
            return None
        if not self.darf("preise", "lieferlaengen"):
            return None
        z = self.aktuelle()
        try:
            ziel = mp.lieferant_uebernehmen(self.db, lz)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.f.meldung(f"Preis von {lz.get('lieferant')} als aktiver Preis in '{ziel}' übernommen. Offene Angebote "
                       "meldet der Preiswächter; festgeschriebene bleiben.")
        self.neu_laden(erzwingen=True)
        if z:
            self.auswaehlen(z["profil_id"], z["werkstoff_id"])
        return ziel

    def lieferant_loeschen(self):
        lz = self._lief_markiert()
        if not lz or not self.darf(mp.LIEFERANTEN_TABELLE):
            return
        self.db.loeschen(mp.LIEFERANTEN_TABELLE, [lz["id"]])
        self.neu_laden(erzwingen=True)

    # ------------------------------------------------------------------ Vergleich, Prüfung
    def vergleichen(self, zeilen=None, dialog=None):
        zs = zeilen or self.markierte()
        if len(zs) < 2:
            self.f.meldung("Für den Vergleich mindestens zwei Materialien markieren (Strg + Klick).", fehler=True)
            return None
        teile, masch = self._teile_des_angebots(zs)
        v = mp.vergleich(zs[:8], teile, masch)
        d = VergleichDialog(self, v, bool(teile))
        if dialog:
            dialog(d)
        else:
            d.exec()
        return v

    def _teile_des_angebots(self, zs):
        """Teilelängen [mm] des offenen Angebots für die Profile der Auswahl und die Maschinenwerte."""
        seite = self.offenes_angebot()
        if seite is None:
            return None, None
        pids = {z["profil_id"] for z in zs}
        alle = []
        je = {}
        for p in seite.positionen:
            if p.get("profil_id") in pids and isinstance(p.get("laenge"), (int, float)):
                n = int(p["stueck"]) if isinstance(p.get("stueck"), (int, float)) and p["stueck"] > 0 else 1
                je.setdefault(p["profil_id"], []).extend([p["laenge"]] * n)
                alle += [p["laenge"]] * n
        # eine Abmessung: ihre Teile für alle Spalten; mehrere Abmessungen: jede mit ihren eigenen Teilen
        teile = {k: v[:3000] for k, v in je.items()} if len(je) > 1 else alle[:3000]
        m = (seite.k.maschinen.get(seite.kopf.get("maschine")) or {}) if hasattr(seite, "k") else {}
        masch = dict(endbeschnitt=m.get("endbeschnitt") or 10.0, greiferrest=m.get("greiferrest") or 140.0,
                     kerf=m.get("schnittbreite") or m.get("kerf") or 0.2)
        return teile or None, masch

    def pruefen(self, dialog=None):
        befunde = material_ki.alle(self.db, self.alle_zeilen)
        self.pruef_knopf.setText(f"Prüfvorschläge {len(befunde)}" if befunde else "Prüfvorschläge")
        d = PruefDialog(self, befunde)
        if dialog:
            dialog(d)
        else:
            d.exec()
        if d.geaendert:
            self.neu_laden(erzwingen=True)
        return befunde

    # ------------------------------------------------------------------ Neu, Import, Export
    def profil_neu(self, eingabe=None, dialog=None):
        if not self.darf("profile"):
            return None
        from .profil_neu import ProfilNeuDialog
        d = ProfilNeuDialog(self, self.db.kontext().profile, eingabe=eingabe or self.suche.text() or None,
                            bemerkung="auf der Seite Material angelegt")
        if not (dialog(d) if dialog else d.exec() == QDialog.Accepted):
            return None
        w = d.werte()
        try:
            self.db.neu("profile", w)
        except Exception as e:      # noqa: BLE001
            self.f.meldung(f"Nicht angelegt: {e}", fehler=True)
            return None
        self.f.meldung(f"Abmessung {w['profil_id']} angelegt; Preis über Lieferantenpreis oder Tabelle Preise.")
        self.alle_box.setChecked(True)
        self.neu_laden(erzwingen=True)
        return w["profil_id"]

    def exportieren(self, zeilen=None, pfad=None):
        zeilen = zeilen if zeilen is not None else self.sichtbar
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Materialliste exportieren", "Material.csv", "CSV (*.csv)")
            if not pfad:
                return None
        with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
            f.write(mp.csv_export(zeilen))
        self.f.meldung(f"{len(zeilen)} Materialien exportiert: {pfad}")
        return pfad

    def preisliste_importieren(self, pfad=None, lieferant=None, frage=True):
        if not self.darf(mp.LIEFERANTEN_TABELLE, "zukauf_lieferanten"):
            return None
        if pfad is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "Preisliste importieren", "",
                                                  "Preislisten (*.csv *.txt *.xlsx);;Alle Dateien (*)")
            if not pfad:
                return None
        if str(pfad).lower().endswith(".xlsx"):
            text = mp.xlsx_als_csv(pfad)
            if text is None:
                self.f.meldung("Excel-Dateien braucht openpyxl; bitte als CSV speichern.", fehler=True)
                return None
        else:
            raw = open(pfad, "rb").read()
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("cp1252")
        if lieferant is None:
            lieferant, ok = QInputDialog.getItem(self, "Preisliste", "Lieferant (wenn die Datei keine Spalte "
                                                 "Lieferant hat):", [""] + list(self.db.kontext().zukauf_lieferanten),
                                                 0, True)
            if not ok:
                return None
        erg = mp.preisliste_lesen(text, lieferant or None, self.db.kontext())
        if frage and not getattr(self.f, "stumm", False):
            fehler = "\n".join(f"Zeile {n}: {g}" for n, g in erg["fehler"][:15])
            if QMessageBox.question(self, "Preisliste importieren",
                                    f"{len(erg['zeilen'])} Zeilen lesbar, {len(erg['fehler'])} mit Fehler."
                                    + (f"\n\n{fehler}" if fehler else "")
                                    + "\n\nImportieren? Vorher wird gesichert. Aktive Preise bleiben, übernehmen geht "
                                    "danach je Material.") != QMessageBox.Yes:
                return None
        for n in {z["lieferant"] for z in erg["zeilen"]} - set(self.db.kontext().zukauf_lieferanten):
            self.db.neu("zukauf_lieferanten", dict(name=n))
        r = mp.preisliste_importieren(self.db, erg["zeilen"])
        self.f.meldung(f"Preisliste: {r['neu']} neu, {r['geaendert']} geändert, {len(erg['fehler'])} übersprungen.")
        self.neu_laden(erzwingen=True)
        return dict(r, fehler=erg["fehler"])

    def erp_einlesen(self, pfad=None, **kw):
        """ERP-Einkaufs-CSV einlesen (vorhandener Import mit Spaltenzuordnung und Prüfliste); danach zeigt die Liste
        Ø, letzten Kauf und Abweichung je Material. Die Stammdaten-Preise bleiben unverändert."""
        from .erp_preise import ErpFehler
        from .erp_preise_dialog import importieren
        try:
            d = importieren(self, self.db, pfad, **kw)
        except (OSError, ErpFehler) as e:
            self.f.meldung(f"ERP-Preise: {e}", fehler=True)
            return None
        if d is None:
            return None
        self.erp_anlegen(still_wenn_leer=True)     # Patrick 23.11.2026: Profile/Werkstoffe aus dem EK anlegen
        if self.darf("materialstamm"):      # Artikelnummer je Abmessung × Werkstoff in den Materialstamm
            from . import material_stamm
            st = material_stamm.ergaenzen(self.db, quelle="ERP-EK")
            if st["neu"] or st["nummern"]:
                self.f.meldung(f"Materialstamm: {st['neu']} Materialien neu, {st['nummern']} Artikelnummern "
                               "übernommen")
        self.neu_laden(erzwingen=True)
        return d

    def erp_anlegen(self, frage=True, still_wenn_leer=False):
        """Profile und Werkstoffe aus dem ERP-Einkauf anlegen (erp_anlegen.plan/ausfuehren): erkannte Abmessungen
        als Profil, Güte mit Norm und Naht als Werkstoff (EN 10219 geschweißt, EN 10210 warmgefertigt/nahtlos,
        EN 10305), Zuordnung der EK-Artikel gemerkt. Admin-Schutz: ohne Freigabe für Werkstoffe nur Profile.
        Ergebnis: dict wie erp_anlegen.ausfuehren oder None."""
        from . import erp_anlegen
        p = erp_anlegen.plan(self.db)
        if not (p["profile"] or p["werkstoffe"] or p["zuordnungen"]):
            if not still_wenn_leer:
                self.f.meldung("Aus dem EK ist nichts anzulegen: alle erkannten Profile und Werkstoffe gibt es schon"
                               + (f" ({len(p['offen'])} EK-Artikel unklar, siehe Prüfliste des ERP-Imports)"
                                  if p["offen"] else ""))
            return None
        if not self.darf("profile"):
            return None
        from . import admin_schutz
        mit_w = bool(p["werkstoffe"]) and ("werkstoffe" not in admin_schutz.tabellen_geschuetzt(self.db)
                                           or admin_schutz.ist_admin(self.db))
        text = (f"{len(p['profile'])} Profile, {len(p['werkstoffe']) if mit_w else 0} Werkstoffe und "
                f"{len(p['zuordnungen'])} EK-Zuordnungen anlegen?\n\n"
                + "\n".join(f"Profil {x['profil_id']}" for x in p["profile"][:12])
                + ("\n" if p["profile"] else "")
                + "\n".join(f"Werkstoff {w['werkstoff_id']}: {w['norm']}, {w['rohrart']}" for w in
                            (p["werkstoffe"] if mit_w else [])[:8])
                + (f"\n\nUnklar (bleibt in der Prüfliste): {len(p['offen'])}" if p["offen"] else "")
                + ("" if mit_w or not p["werkstoffe"] else
                   "\n\nWerkstoffe sind admin-geschützt: nur Profile werden angelegt."))
        if frage and not getattr(self.f, "stumm", False):
            if QMessageBox.question(self, "Aus dem EK anlegen", text) != QMessageBox.Yes:
                return None
        erg = erp_anlegen.ausfuehren(self.db, p, mit_werkstoffen=mit_w)
        f = self.window()
        f.alles_neu_laden() if hasattr(f, "alles_neu_laden") else None
        self.neu_laden(erzwingen=True)
        self.f.meldung(f"Aus dem EK angelegt: {erg['profile']} Profile, {erg['werkstoffe']} Werkstoffe, "
                       f"{erg['zuordnungen']} Zuordnungen")
        return erg

    def vorschlag_uebernehmen(self, frage=True):
        """Preisvorschlag des markierten Materials übernehmen (Admin-Schutz, Protokoll wie die Prüfvorschläge)."""
        z, v = self.aktuelle(), getattr(self, "_vorschlag", None)
        if not z or not v or not self.darf("preise"):
            return None
        if frage and not getattr(self.f, "stumm", False):
            if QMessageBox.question(self, "Preisvorschlag", f"{z['profil_id']} · {z['werkstoff_id']}: "
                                    f"{zahl_als_text(v['preis_m'], 2)} €/m als aktiven Preis übernehmen?\n\n"
                                    f"{v['begruendung']}") != QMessageBox.Yes:
                return None
        b = material_ki.befund(material_ki.VORSCHLAG, "historie", f"{z['profil_id']} · {z['werkstoff_id']}",
                               f"Preisvorschlag {zahl_als_text(v['preis_m'], 2)} €/m", v["begruendung"],
                               aktion="preis_aus_historie",
                               daten=dict(profil_id=z["profil_id"], werkstoff_id=z["werkstoff_id"],
                                          preis_m=v["preis_m"], quelle=v["quelle"]))
        text = material_ki.anwenden(self.db, b)
        self.f.meldung(text + ". Offene Angebote meldet der Preiswächter; festgeschriebene bleiben.")
        self.neu_laden(erzwingen=True)
        self.auswaehlen(z["profil_id"], z["werkstoff_id"])
        return text

    def erp_kaeufe(self, dialog=None):
        """Käufe des markierten Materials (Fenster aus dem ERP-Import, Haken „zählt“ je Kauf)."""
        z = self.aktuelle()
        g = self._erp.get((z["profil_id"], z["werkstoff_id"])) if z and hasattr(self, "_erp") else None
        if not g:
            return None
        from .erp_preise_dialog import VerlaufDialog
        d = VerlaufDialog(self, self.db, g)
        if dialog:
            dialog(d)
        else:
            d.exec()
        self.neu_laden(erzwingen=True)
        return d

    def stammdaten_zeigen(self, name):
        """Tabellenseite unter Einstellungen → Material zeigen (z. B. 'preise')."""
        for s in getattr(self.f, "seiten", []):
            if getattr(getattr(s, "t", None), "name", None) == name:
                if hasattr(self.f, "zeigen"):
                    self.f.zeigen(s)
                return s
        return None

    def sizeHint(self):
        return QSize(1200, 700)


# ---------------------------------------------------------------------- Preishistorie
class PreisKurve(QWidget):
    """Preishistorie €/m: Stufenlinie der Stammdaten-Preisstände (blau), ERP-Käufe als Punkte (grün, rot = zählt
    nicht), ERP-Ø gestrichelt, Lieferantenpreise als Rauten (orange)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pp, self.aktuell = dict(stamm=[], erp=[], lieferanten=[], schnitt=None), None
        self.setMinimumHeight(170)

    def setzen(self, pp, aktuell=None):
        self.pp, self.aktuell = pp, aktuell
        self.update()

    def werte(self):
        pp = self.pp
        return ([(d, p) for d, p in pp["stamm"]] + [(x["datum"], x["preis"]) for x in pp["erp"]]
                + [(x["datum"], x["preis"]) for x in pp["lieferanten"]])

    def paintEvent(self, _):
        import datetime

        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QPainter, QPen, QPolygonF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        text = self.palette().color(self.palette().ColorRole.WindowText)
        punkte = self.werte()
        if not punkte:
            p.setPen(text)
            p.drawText(self.rect(), Qt.AlignCenter, "Noch keine Preishistorie")
            p.end()
            return
        r = QRectF(self.rect()).adjusted(52, 8, -10, -22)
        heute = datetime.date.today()
        t0 = min(d for d, _ in punkte)
        t1 = max(max(d for d, _ in punkte), heute)
        t1 = t1 if t1 > t0 else t0 + datetime.timedelta(days=1)
        ws = [w for _, w in punkte] + ([self.pp["schnitt"]] if self.pp.get("schnitt") else [])
        lo, hi = min(ws), max(ws)
        if hi - lo < 0.01:
            lo, hi = lo * 0.95, hi * 1.05
        lo, hi = lo - (hi - lo) * 0.08, hi + (hi - lo) * 0.08

        def pt(d, w):
            return QPointF(r.left() + (d - t0).days / (t1 - t0).days * r.width(),
                           r.bottom() - (w - lo) / (hi - lo) * r.height())
        grau = stil.farbe(stil.TEXT_GRAU)
        p.setPen(QPen(grau, 1))
        p.drawLine(r.bottomLeft(), r.bottomRight())
        p.drawLine(r.bottomLeft(), r.topLeft())
        for w in (lo + (hi - lo) * 0.08, hi - (hi - lo) * 0.08):
            p.drawText(QPointF(2, pt(t0, w).y() + 4), zahl_als_text(w, 2))
        p.drawText(QPointF(r.left(), r.bottom() + 15), t0.strftime("%d.%m.%Y"))
        p.drawText(QPointF(r.right() - 64, r.bottom() + 15), t1.strftime("%d.%m.%Y"))
        st = self.pp["stamm"]
        if st:
            p.setPen(QPen(stil.farbe(stil.AKZENT), 2))
            for i, (d, w) in enumerate(st):
                bis = st[i + 1][0] if i + 1 < len(st) else t1
                p.drawLine(pt(d, w), pt(bis, w))
                if i + 1 < len(st):
                    p.drawLine(pt(bis, w), pt(bis, st[i + 1][1]))
        if self.pp.get("schnitt"):
            p.setPen(QPen(stil.farbe(stil.GRUEN), 1, Qt.DashLine))
            y = pt(t0, self.pp["schnitt"]).y()
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        p.setPen(Qt.NoPen)
        for x in self.pp["erp"]:
            p.setBrush(QBrush(stil.farbe(stil.GRUEN if x["zaehlt"] else stil.ROT)))
            p.drawEllipse(pt(x["datum"], x["preis"]), 3.5, 3.5)
        p.setBrush(QBrush(stil.farbe(stil.ORANGE)))
        for x in self.pp["lieferanten"]:
            c = pt(x["datum"], x["preis"])
            p.drawPolygon(QPolygonF([QPointF(c.x(), c.y() - 5), QPointF(c.x() + 5, c.y()), QPointF(c.x(), c.y() + 5),
                                     QPointF(c.x() - 5, c.y())]))
        p.end()


# ---------------------------------------------------------------------- Dialoge
class LieferantDialog(QDialog):
    def __init__(self, parent, z, lieferanten):
        super().__init__(parent)
        self.setWindowTitle(f"Lieferantenpreis · {z['profil_id']} · {z['werkstoff_id']}")
        form = QFormLayout(self)
        self.lieferant = QComboBox()
        self.lieferant.setEditable(True)
        self.lieferant.addItems(sorted(lieferanten))
        self.basis = QComboBox()
        self.basis.addItems(["€/kg", "€/m", "€/Stange"])
        self.preis = QLineEdit()
        self.laenge = QLineEdit()
        self.laenge.setPlaceholderText("leer = Stangenlänge der Preise-Zeile")
        self.ab, self.bis = QLineEdit(), QLineEdit()
        self.ab.setPlaceholderText("TT.MM.JJJJ")
        self.bis.setPlaceholderText("TT.MM.JJJJ")
        self.zeit, self.mindest, self.artnr, self.bem = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        for t, w in (("Lieferant", self.lieferant), ("Preisbasis", self.basis), ("Preis [€]", self.preis),
                     ("Lieferlänge [mm]", self.laenge), ("Gültig ab", self.ab), ("Gültig bis", self.bis),
                     ("Lieferzeit [Tage]", self.zeit), ("Mindestabnahme [Stangen]", self.mindest),
                     ("Artikelnr. des Lieferanten", self.artnr), ("Bemerkung", self.bem)):
            form.addRow(t, w)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def setzen(self, w):
        self.lieferant.setCurrentText(w.get("lieferant") or "")
        self.basis.setCurrentText(w.get("basis") or "€/kg")
        for feld, ed in (("preis", self.preis), ("laenge", self.laenge), ("gueltig_ab", self.ab),
                         ("gueltig_bis", self.bis), ("lieferzeit", self.zeit), ("mindest_stangen", self.mindest),
                         ("artikelnr", self.artnr), ("bemerkung", self.bem)):
            if w.get(feld) is not None:
                ed.setText(str(w[feld]))

    def werte(self):
        def ganz(t):
            v = mp._zahl_text(t)
            return int(v) if v is not None else None
        return {k: v for k, v in dict(
            lieferant=self.lieferant.currentText().strip(), basis=self.basis.currentText(),
            preis=mp._zahl_text(self.preis.text()), laenge=ganz(self.laenge.text()),
            gueltig_ab=mp._datum_text(self.ab.text()), gueltig_bis=mp._datum_text(self.bis.text()),
            lieferzeit=ganz(self.zeit.text()), mindest_stangen=ganz(self.mindest.text()),
            artikelnr=self.artnr.text().strip() or None, bemerkung=self.bem.text().strip() or None).items()
            if v not in (None, "")}


MEHRFACH_AUSWAHL = (("Preis um Prozent ändern", ("preise", None)), ("Lieferant", ("preise", "lieferant")),
                    ("Gültig ab", ("preise", "gueltig_ab")), ("Mindestabnahme [Stangen]", ("preise", "mindest_stangen")),
                    ("Liefer-Stangenlänge [mm]", ("preise", "lieferlaenge")),
                    ("Bemerkung der Preise-Zeile", ("preise", "bemerkung")),
                    ("Endbeschnitt abweichend [mm]", ("profile", "endbeschnitt")),
                    ("Greiferrest abweichend [mm]", ("profile", "greiferrest")),
                    ("Bemerkung der Abmessung", ("profile", "bemerkung")))


class MehrfachDialog(QDialog):
    """Feld und Wert für mehrere Materialien. Güte, Dichte und Maße sind nicht dabei (technische Werte)."""

    def __init__(self, parent, anzahl):
        super().__init__(parent)
        self.setWindowTitle(f"{anzahl} Materialien ändern")
        form = QFormLayout(self)
        self.feld = QComboBox()
        self.feld.addItems([t for t, _ in MEHRFACH_AUSWAHL])
        self.wert = QLineEdit()
        self.prozent = QDoubleSpinBox()
        self.prozent.setRange(-90, 500)
        self.prozent.setSuffix(" %")
        self.prozent.setDecimals(1)
        form.addRow("Feld", self.feld)
        form.addRow("Neuer Wert", self.wert)
        form.addRow("Preisänderung", self.prozent)
        hinweis = QLabel("Nur vorhandene Zeilen in 'Preise' werden geändert. Werkstoff, Güte, Dichte und Maße lassen "
                         "sich hier bewusst nicht für viele Materialien zugleich ändern.")
        hinweis.setWordWrap(True)
        form.addRow(hinweis)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)
        self.feld.currentIndexChanged.connect(self._umschalten)
        self._umschalten()

    def _umschalten(self, *_):
        prozent = MEHRFACH_AUSWAHL[self.feld.currentIndex()][1][1] is None
        self.prozent.setEnabled(prozent)
        self.wert.setEnabled(not prozent)

    def ergebnis(self):
        tabelle, feld = MEHRFACH_AUSWAHL[self.feld.currentIndex()][1]
        if feld is None:
            return tabelle, None, None, 1 + self.prozent.value() / 100
        t = self.wert.text().strip()
        if feld in ("mindest_stangen", "lieferlaenge", "endbeschnitt", "greiferrest"):
            v = mp._zahl_text(t)
            wert = int(v) if v is not None else None
        elif feld == "gueltig_ab":
            wert = mp._datum_text(t)
        else:
            wert = t or None
        return tabelle, feld, wert, None


class VergleichDialog(QDialog):
    def __init__(self, parent, v, mit_teilen):
        super().__init__(parent)
        self.setWindowTitle("Materialvergleich")
        self.resize(900, 460)
        lay = QVBoxLayout(self)
        t = QTableWidget(len(v["zeilen"]), len(v["spalten"]))
        t.setHorizontalHeaderLabels(v["spalten"])
        t.setVerticalHeaderLabels([z[0] for z in v["zeilen"]])
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, (titel, werte, bestes) in enumerate(v["zeilen"]):
            stellen = next((s for f, ti, s in mp.VERGLEICH if ti == titel), None)
            for c, w in enumerate(werte):
                if isinstance(w, list):
                    txt = ", ".join(str(x) for x in w)
                elif isinstance(w, (int, float)) and not isinstance(w, bool):
                    txt = zahl_als_text(w, stellen)
                elif titel.startswith("Preisstand"):
                    txt = _datum(w)
                else:
                    txt = "" if w is None else str(w)
                it = QTableWidgetItem(txt)
                if bestes == c:
                    it.setBackground(QBrush(stil.farbe(stil.GRUEN_FLAECHE)))
                    f = QFont(it.font())
                    f.setBold(True)
                    it.setFont(f)
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        self.tabelle = t
        lay.addWidget(t, 1)
        for h in v.get("hinweise") or ():
            lab = QLabel(h)
            lab.setWordWrap(True)
            lay.addWidget(lab)
        if not mit_teilen:
            lay.addWidget(QLabel("Verschnitt: ein Angebot öffnen, dann rechnet der Vergleich mit dessen Teilelängen."))
        b = QDialogButtonBox(QDialogButtonBox.Close)
        b.button(QDialogButtonBox.Close).setText("Schließen")
        b.rejected.connect(self.reject)
        b.accepted.connect(self.accept)
        lay.addWidget(b)


class PruefDialog(QDialog):
    """Befunde der lokalen Prüfung; Übernehmen/Ablehnen je Befund."""

    def __init__(self, parent, befunde):
        super().__init__(parent)
        self.setWindowTitle(f"Prüfvorschläge Material ({len(befunde)})")
        self.resize(820, 520)
        self.db, self.f, self.seite = parent.db, parent.f, parent
        self.befunde, self.geaendert = list(befunde), False
        lay = QVBoxLayout(self)
        info = QLabel("Lokale Prüfung auf diesem PC, ohne Internet. Das Programm ändert nichts von selbst; Werkstoff, "
                      "Güte und technische Werte ändert keine Aktion.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.liste = QListWidget()
        self.liste.setWordWrap(True)
        lay.addWidget(self.liste, 1)
        self.grund = QLabel()
        self.grund.setWordWrap(True)
        lay.addWidget(self.grund)
        k = QHBoxLayout()
        self.ueber = QPushButton("Übernehmen")
        self.ueber.clicked.connect(lambda: self.uebernehmen())
        self.ab = QPushButton("Ablehnen (nicht mehr zeigen)")
        self.ab.clicked.connect(lambda: self.ablehnen())
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        for b in (self.ueber, self.ab):
            k.addWidget(b)
        k.addStretch(1)
        k.addWidget(zu)
        lay.addLayout(k)
        self.liste.currentRowChanged.connect(self._zeigen)
        self._fuellen()

    def _fuellen(self):
        self.liste.clear()
        for b in self.befunde:
            it = QListWidgetItem(f"{b['art']} · {b['material']} · {b['text']}")
            sym = stil.status_symbol("HINWEIS" if b["art"] == material_ki.VORSCHLAG else b["art"])
            if sym is not None:
                it.setIcon(sym)
            self.liste.addItem(it)
        if self.befunde:
            self.liste.setCurrentRow(0)
        else:
            self.grund.setText("Keine Auffälligkeiten.")
        self._zeigen(self.liste.currentRow())

    def _zeigen(self, r):
        b = self.befunde[r] if 0 <= r < len(self.befunde) else None
        self.grund.setText(f"Begründung: {b['begruendung']}" if b else "")
        self.ueber.setEnabled(bool(b and b.get("aktion")))
        self.ab.setEnabled(bool(b))

    def uebernehmen(self, r=None):
        r = self.liste.currentRow() if r is None else r
        b = self.befunde[r] if 0 <= r < len(self.befunde) else None
        if not b or not b.get("aktion"):
            return None
        if not self.seite.darf(*{"preis_uebernehmen": ("preise", "lieferlaengen"),
                                  "preis_aus_historie": ("preise",)}.get(b["aktion"], ("profile",))):
            return None
        try:
            text = material_ki.anwenden(self.db, b)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.f.meldung(text + ".")
        self.befunde.pop(r)
        self.geaendert = True
        self._fuellen()
        return text

    def ablehnen(self, r=None):
        r = self.liste.currentRow() if r is None else r
        b = self.befunde[r] if 0 <= r < len(self.befunde) else None
        if not b:
            return
        material_ki.ablehnen(self.db, b)
        self.befunde.pop(r)
        self._fuellen()


__all__ = ["MaterialBereich", "TITEL"]
