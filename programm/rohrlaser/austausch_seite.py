"""Seite „Austausch“: Austauschordner 2.0 als Projekt- und Dateimanager im Programm (Patrick 24.11.2026).

Links Schnellzugriffe (Übersicht, Neu für mich, Meine Aufgaben, Favoriten, Zuletzt verwendet, Wer arbeitet woran),
die Bereiche (Gemeinsame Dateien, Mein Ordner, Anfragen, Angebotsablage, PPEASE-Ablage), Archiv, Papierkorb und
gespeicherte Suchen. Oben Pfad, Suche (über alle Bereiche, auch Kommentare und Dateiinhalt) und Filter (Typ,
Mitarbeiter, Kunde, Status, Zeitraum), Liste oder Kacheln, Sortierung. Rechts der Infobereich der gewählten Datei:
Vorschau, Bauteilinfo, Zuordnung mit Vorschlägen zum Bestätigen, Verantwortlich/Status/Priorität/Fällig/Aufgabe/Notiz,
Kommentare, Verlauf und Versionen. Hochladen per Knopf oder Ziehen (mit Fortschritt und Rückfrage bei gleichem
Namen), Herausziehen in den Explorer, Mehrfachauswahl und Kontextmenü. Die Logik steht in austausch_dateien.py.
"""
import hashlib
import time
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QDate, QMimeData, QModelIndex, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog,
                               QDialogButtonBox, QFileDialog, QFileIconProvider, QFormLayout, QGridLayout,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QProgressDialog, QPushButton, QScrollArea,
                               QSplitter, QStackedWidget, QTableView, QTextBrowser, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from . import austausch_dateien as ad
from .klartext import fehler_text

MIME = "application/x-rohrlaser-austausch"
SPALTEN = (("name", "Name"), ("art", "Typ"), ("groesse", "Größe"), ("zeit", "Geändert"), ("kundennr", "Kunde"),
           ("angebot", "Angebot"), ("bearbeiter", "Verantwortlich"), ("status", "Status"), ("ort", "Ort"))
STATUS_FARBE = {ad.NEU: "#2F6FB3", ad.UNGESEHEN: "#2F6FB3", ad.BEARBEITUNG: "#A66A00",
                ad.RUECKFRAGE: "#C0392B", ad.FERTIG: "#2F7D4F", ad.ARCHIVIERT: "#8A94A6"}
ZEITRAUM = (("", "Jederzeit"), (1, "Heute"), (7, "Letzte 7 Tage"), (30, "Letzte 30 Tage"), (365, "Letztes Jahr"))
UEBERSICHT, NEU_FUER_MICH, MEINE, FAVORITEN, ZULETZT, WER, ARCHIV, PAPIERKORB, SUCHE = (
    "uebersicht", "neu", "meine", "favoriten", "zuletzt", "wer", "archiv", "papierkorb", "suche")
SCHNELL = ((UEBERSICHT, "Übersicht"), (NEU_FUER_MICH, "Neu für mich"), (MEINE, "Meine Aufgaben"),
           (FAVORITEN, "Favoriten"), (ZULETZT, "Zuletzt verwendet"), (WER, "Wer arbeitet woran"))
DASHBOARD_KACHELN = (("neu", "Neue Dateien", NEU_FUER_MICH), ("meine", "Meine Aufgaben", MEINE),
                     ("faellig", "Fällig", MEINE), ("rueckfrage", "Offene Rückfragen", ad.RUECKFRAGE),
                     ("bearbeitung", "In Bearbeitung", ad.BEARBEITUNG), ("fertig", "Fertig (7 Tage)", ad.FERTIG),
                     ("vorschlag", "Zuordnung bestätigen", "vorschlag"))
VORSCHAU_PX = 96


def _zeit_text(t):
    if not t:
        return ""
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(t))


def _iso_text(iso):
    if not iso:
        return ""
    s = str(iso)
    return f"{s[8:10]}.{s[5:7]}.{s[:4]} {s[11:16]}".strip()


class DateiModell(QAbstractTableModel):
    """Einträge der aktuellen Ansicht; Spalte 0 trägt Symbol bzw. Vorschaubild (Kacheln)."""

    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        self.eintraege, self.metas, self.neu = [], {}, set()
        self.kacheln = False
        self._symbole = {}
        self._anbieter = QFileIconProvider()

    def setzen(self, eintraege, metas, neu):
        self.beginResetModel()
        self.eintraege, self.metas, self.neu = list(eintraege), metas, set(neu)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.eintraege)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(SPALTEN)

    def headerData(self, i, ausrichtung, rolle=Qt.DisplayRole):
        if ausrichtung == Qt.Horizontal and rolle == Qt.DisplayRole:
            return SPALTEN[i][1]
        return None

    def eintrag(self, zeile):
        return self.eintraege[zeile] if 0 <= zeile < len(self.eintraege) else None

    def _symbol(self, e):
        k = "ordner" if e.ordner else e.endung
        if k not in self._symbole:
            from PySide6.QtCore import QFileInfo
            if e.ordner:
                self._symbole[k] = self._anbieter.icon(QFileIconProvider.Folder)
            else:
                self._symbole[k] = self._anbieter.icon(QFileInfo(f"x{e.endung}"))
        return self._symbole[k]

    def data(self, index, rolle=Qt.DisplayRole):
        e = self.eintrag(index.row())
        if e is None:
            return None
        s = SPALTEN[index.column()][0]
        m = self.metas.get(e.datei) or {}
        if rolle == Qt.DisplayRole:
            if s == "name":
                return e.name
            if s == "art":
                return ad.ART_TEXT.get(e.art, e.endung.lstrip(".").upper())
            if s == "groesse":
                return "" if e.ordner else ad.groesse_text(e.groesse)
            if s == "zeit":
                return _zeit_text(e.zeit)
            if s == "ort":
                return ad.BEREICH_TITEL.get(e.bereich, e.bereich) + ("/" + e.ordner_rel if e.ordner_rel else "")
            return m.get(s) or ""
        if rolle == Qt.DecorationRole and index.column() == 0:
            if self.kacheln:
                bild = self.seite.vorschaubild(e)
                if bild is not None:
                    return bild
            return self._symbol(e)
        if rolle == Qt.FontRole and e.datei in self.neu:
            f = QFont()
            f.setBold(True)
            return f
        if rolle == Qt.ForegroundRole and s == "status" and m.get("status"):
            return QColor(STATUS_FARBE.get(m["status"], "#555555"))
        if rolle == Qt.ToolTipRole:
            t = [e.rel]
            if e.office:
                t.append(f"Gerade in Office geöffnet von {e.office}")
            if ad.vorschlaege(m):
                t.append("Zuordnung vorgeschlagen, bitte bestätigen")
            return "\n".join(t)
        if rolle == Qt.UserRole:
            return e.datei
        return None

    def flags(self, index):
        f = super().flags(index)
        if index.isValid():
            f |= Qt.ItemIsDragEnabled
            e = self.eintrag(index.row())
            if e is not None and e.ordner:
                f |= Qt.ItemIsDropEnabled
        return f

    def supportedDragActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def mimeTypes(self):
        return [MIME, "text/uri-list"]

    def mimeData(self, indexe):
        zeilen = sorted({i.row() for i in indexe})
        md = QMimeData()
        dateien = [self.eintraege[z].datei for z in zeilen if self.eintrag(z) is not None]
        md.setData(MIME, "\n".join(dateien).encode("utf-8"))
        w = self.seite.w
        md.setUrls([QUrl.fromLocalFile(str(ad.pfad(self.seite.db, d, w))) for d in dateien
                    if ad.pfad(self.seite.db, d, w) is not None])
        return md

    def canDropMimeData(self, daten, aktion, zeile, spalte, eltern):
        return daten.hasFormat(MIME) or daten.hasUrls()

    def dropMimeData(self, daten, aktion, zeile, spalte, eltern):
        ziel = self.eintrag(eltern.row()) if eltern.isValid() else None
        self.seite.abgelegt(daten, ziel if ziel is not None and ziel.ordner else None)
        return True


class Liste(QTableView):
    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setSortingEnabled(False)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.setWordWrap(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionsClickable(True)


class Kacheln(QListView):
    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setIconSize(QSize(VORSCHAU_PX, VORSCHAU_PX))
        self.setGridSize(QSize(VORSCHAU_PX + 44, VORSCHAU_PX + 46))
        self.setWordWrap(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setContextMenuPolicy(Qt.CustomContextMenu)


class Uebersicht(QWidget):
    """Dashboard des Austauschordners: Kacheln mit Zahlen (Klick öffnet die Liste) und Listen."""
    gewaehlt = Signal(str)          # Schnellzugriff oder Status
    datei_gewaehlt = Signal(str)

    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        lay = QVBoxLayout(self)
        kopf = QHBoxLayout()
        t = QLabel("Übersicht Austauschordner")
        t.setObjectName("titel")
        kopf.addWidget(t)
        kopf.addStretch(1)
        self.anpassen = QPushButton("Anpassen …")
        self.anpassen.setToolTip("Welche Kacheln und Listen die Übersicht zeigt (nur für diesen Arbeitsplatz)")
        self.anpassen.clicked.connect(self.anpassen_dialog)
        kopf.addWidget(self.anpassen)
        lay.addLayout(kopf)
        self.raster = QGridLayout()
        lay.addLayout(self.raster)
        self.kacheln = {}
        for i, (k, titel, ziel) in enumerate(DASHBOARD_KACHELN):
            b = QPushButton(f"0\n{titel}")
            b.setObjectName("anfragen_zaehler")
            b.setMinimumHeight(64)
            b.clicked.connect(lambda _=False, z=ziel: self.gewaehlt.emit(z))
            self.kacheln[k] = b
            self.raster.addWidget(b, i // 4, i % 4)
        unten = QHBoxLayout()
        self.listen = {}
        for k, titel in (("zuletzt", "Kürzlich geändert"), ("wer", "Wer arbeitet woran"),
                         ("aktivitaet", "Gemeinsame Aktivitäten")):
            box = QVBoxLayout()
            box.addWidget(QLabel(f"<b>{titel}</b>"))
            li = QListWidget()
            li.itemDoubleClicked.connect(lambda it: self.datei_gewaehlt.emit(it.data(Qt.UserRole) or ""))
            box.addWidget(li)
            self.listen[k] = li
            rahmen = QWidget()
            rahmen.setLayout(box)
            unten.addWidget(rahmen, 1)
        lay.addLayout(unten, 1)

    def sichtbar(self):
        v = (self.seite.db.einstellung(ad.L_ANSICHT) or {})
        v = v if isinstance(v, dict) else {}
        return set(v.get("dashboard") or ([k for k, _, _ in DASHBOARD_KACHELN] + ["zuletzt", "wer", "aktivitaet"]))

    def fuellen(self, u):
        an = self.sichtbar()
        for k, titel, _ in DASHBOARD_KACHELN:
            self.kacheln[k].setText(f"{len(u.get(k) or [])}\n{titel}")
            self.kacheln[k].setVisible(k in an)
        for k, li in self.listen.items():
            li.parentWidget().setVisible(k in an)
            li.clear()
        for d in u["zuletzt"]:
            it = QListWidgetItem(d.partition(":")[2])
            it.setData(Qt.UserRole, d)
            self.listen["zuletzt"].addItem(it)
        for x in u["wer"]:
            it = QListWidgetItem(f"{x['wer']}: {(x['datei'] or '').partition(':')[2]} ({x['art']})")
            it.setData(Qt.UserRole, x["datei"])
            self.listen["wer"].addItem(it)
        if not u["wer"]:
            self.listen["wer"].addItem("Gerade bearbeitet niemand eine Datei.")
        for e in u["aktivitaet"]:
            it = QListWidgetItem(f"{_iso_text(e['zeit'])} {e['wer']}: {e['datei'].partition(':')[2]} – "
                                 f"{ad.verlauf_text(e)}")
            it.setData(Qt.UserRole, e["datei"])
            self.listen["aktivitaet"].addItem(it)

    def anpassen_dialog(self, werte=None):
        d = QDialog(self)
        d.setWindowTitle("Übersicht anpassen")
        lay = QVBoxLayout(d)
        an = self.sichtbar()
        haken = {}
        for k, titel in [(k, t) for k, t, _ in DASHBOARD_KACHELN] + [("zuletzt", "Kürzlich geändert"),
                                                                    ("wer", "Wer arbeitet woran"),
                                                                    ("aktivitaet", "Gemeinsame Aktivitäten")]:
            c = QCheckBox(titel)
            c.setChecked(k in an)
            haken[k] = c
            lay.addWidget(c)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        if werte is not None:           # Tests
            for k, c in haken.items():
                c.setChecked(k in werte)
            ergebnis = QDialog.Accepted
        else:
            ergebnis = d.exec()
        if ergebnis == QDialog.Accepted:
            v = self.seite.db.einstellung(ad.L_ANSICHT) or {}
            v = dict(v) if isinstance(v, dict) else {}
            v["dashboard"] = [k for k, c in haken.items() if c.isChecked()]
            self.seite.db.einstellung_setzen(ad.L_ANSICHT, v)
            self.seite.neu_laden()


class Info(QScrollArea):
    """Infobereich rechts: Vorschau, Zuordnung, Arbeit, Kommentare, Verlauf, Versionen der gewählten Datei."""

    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        self.datei = None
        self.setWidgetResizable(True)
        self.setMinimumWidth(320)
        innen = QWidget()
        lay = QVBoxLayout(innen)
        self.titel = QLabel("Keine Datei gewählt")
        self.titel.setObjectName("titel")
        self.titel.setWordWrap(True)
        lay.addWidget(self.titel)
        self.sperre = QLabel("")
        self.sperre.setWordWrap(True)
        self.sperre.setStyleSheet("color: #A66A00; font-weight: 600;")
        lay.addWidget(self.sperre)
        self.bild = QLabel()
        self.bild.setAlignment(Qt.AlignCenter)
        self.bild.setMinimumHeight(10)
        lay.addWidget(self.bild)
        self.daten = QLabel()
        self.daten.setWordWrap(True)
        self.daten.setTextFormat(Qt.RichText)
        lay.addWidget(self.daten)
        knoepfe = QHBoxLayout()
        self.k_vorschau = QPushButton("Vorschau")
        self.k_vorschau.clicked.connect(lambda: self.seite.vorschau())
        self.k_oeffnen = QPushButton("Bearbeiten")
        self.k_oeffnen.setToolTip("Mit dem zugehörigen Programm öffnen; die anderen sehen „in Bearbeitung“, die "
                                  "vorige Fassung wird gesichert")
        self.k_oeffnen.clicked.connect(lambda: self.seite.bearbeiten())
        self.k_kalk = QPushButton("In Kalkulation")
        self.k_kalk.setToolTip("STEP-Dateien als neues Angebot kalkulieren (oder ins geöffnete Angebot)")
        self.k_kalk.clicked.connect(lambda: self.seite.in_kalkulation())
        for k in (self.k_vorschau, self.k_oeffnen, self.k_kalk):
            knoepfe.addWidget(k)
        lay.addLayout(knoepfe)
        # Zuordnung
        lay.addWidget(QLabel("<b>Zuordnung</b>"))
        self.vorschlag = QLabel()
        self.vorschlag.setWordWrap(True)
        self.vorschlag.setStyleSheet("background: #FFF4D6; padding: 4px; border-radius: 3px;")
        lay.addWidget(self.vorschlag)
        vk = QHBoxLayout()
        self.k_bestaetigen = QPushButton("Vorschlag bestätigen")
        self.k_bestaetigen.clicked.connect(lambda: self.seite.vorschlag(True))
        self.k_verwerfen = QPushButton("Verwerfen")
        self.k_verwerfen.clicked.connect(lambda: self.seite.vorschlag(False))
        vk.addWidget(self.k_bestaetigen)
        vk.addWidget(self.k_verwerfen)
        lay.addLayout(vk)
        form = QFormLayout()
        self.felder = {}
        for k, t in ad.ZUORDNUNG:
            e = QLineEdit()
            e.setObjectName(f"austausch_{k}")
            self.felder[k] = e
            form.addRow(t, e)
        lay.addLayout(form)
        lay.addWidget(QLabel("<b>Bearbeitung</b>"))
        form2 = QFormLayout()
        self.bearbeiter = QComboBox()
        self.bearbeiter.setEditable(True)
        self.status = QComboBox()
        self.status.addItems([""] + list(ad.STATUS))
        self.prioritaet = QComboBox()
        self.prioritaet.addItems([""] + list(ad.PRIORITAETEN))
        self.faellig_an = QCheckBox("fällig am")
        self.faellig = QDateEdit()
        self.faellig.setCalendarPopup(True)
        self.faellig.setDisplayFormat("dd.MM.yyyy")
        self.faellig.setDate(QDate.currentDate())
        f_zeile = QHBoxLayout()
        f_zeile.addWidget(self.faellig_an)
        f_zeile.addWidget(self.faellig, 1)
        self.aufgabe = QLineEdit()
        self.aufgabe.setPlaceholderText("z. B. Kalkulieren bis Freitag")
        self.notiz = QLineEdit()
        self.notiz.setPlaceholderText("nur intern")
        form2.addRow("Verantwortlich", self.bearbeiter)
        form2.addRow("Status", self.status)
        form2.addRow("Priorität", self.prioritaet)
        form2.addRow("Fällig", f_zeile)
        form2.addRow("Aufgabe", self.aufgabe)
        form2.addRow("Interne Notiz", self.notiz)
        lay.addLayout(form2)
        self.k_speichern = QPushButton("Speichern")
        self.k_speichern.setObjectName("primaer")
        self.k_speichern.clicked.connect(lambda: self.seite.info_speichern())
        lay.addWidget(self.k_speichern)
        lay.addWidget(QLabel("<b>Kommentare und Verlauf</b>"))
        self.verlauf = QTextBrowser()
        self.verlauf.setMinimumHeight(140)
        lay.addWidget(self.verlauf)
        kz = QHBoxLayout()
        self.kommentar = QLineEdit()
        self.kommentar.setPlaceholderText("Kommentar schreiben …")
        self.kommentar.returnPressed.connect(lambda: self.seite.kommentieren())
        self.k_kommentar = QPushButton("Senden")
        self.k_kommentar.clicked.connect(lambda: self.seite.kommentieren())
        kz.addWidget(self.kommentar, 1)
        kz.addWidget(self.k_kommentar)
        lay.addLayout(kz)
        lay.addWidget(QLabel("<b>Versionen</b>"))
        self.versionen = QListWidget()
        self.versionen.setMaximumHeight(110)
        lay.addWidget(self.versionen)
        self.k_version = QPushButton("Fassung wiederherstellen")
        self.k_version.setToolTip("Die gewählte Fassung wird wieder aktuell; die jetzige wird vorher gesichert")
        self.k_version.clicked.connect(lambda: self.seite.version_zurueck())
        lay.addWidget(self.k_version)
        lay.addStretch(1)
        self.setWidget(innen)
        self.zeigen(None)

    def zeigen(self, e, m=None):
        self.datei = e.datei if e is not None else None
        aktiv = e is not None
        for w in [self.k_vorschau, self.k_oeffnen, self.k_kalk, self.k_speichern, self.k_kommentar, self.k_version,
                  self.kommentar, self.bearbeiter, self.status, self.prioritaet, self.faellig, self.faellig_an,
                  self.aufgabe, self.notiz] + list(self.felder.values()):
            w.setEnabled(aktiv)
        self.bild.clear()
        self.sperre.setText("")
        self.vorschlag.hide()
        self.k_bestaetigen.hide()
        self.k_verwerfen.hide()
        if e is None:
            self.titel.setText("Keine Datei gewählt")
            self.daten.setText("Datei anklicken: hier stehen Vorschau, Zuordnung, Kommentare und Versionen.")
            self.verlauf.clear()
            self.versionen.clear()
            for f in self.felder.values():
                f.clear()
            return
        m = m or {}
        s = self.seite
        self.titel.setText(e.name)
        zeilen = [f"{ad.ART_TEXT.get(e.art, e.endung)} · {ad.groesse_text(e.groesse) if not e.ordner else 'Ordner'}",
                  f"Geändert {_zeit_text(e.zeit)}",
                  f"Ort: {ad.BEREICH_TITEL.get(e.bereich, e.bereich)}/{e.ordner_rel}"]
        if m.get("hochgeladen_von"):
            zeilen.append(f"Hochgeladen von {m['hochgeladen_von']} am {_iso_text(m.get('hochgeladen_am'))}")
        info = s.datei_info(e)
        if info:
            zeilen.append(info)
        self.daten.setText("<br>".join(zeilen))
        bild = s.vorschaubild(e, 260)
        if bild is not None:
            self.bild.setPixmap(bild.pixmap(260, 260))
        sp = s.sperre_von(e)
        if sp:
            self.sperre.setText(f"In Bearbeitung von {sp['wer']}" + (" (Office)" if sp.get("office") else "")
                                + (f" seit {_iso_text(sp.get('seit'))}" if sp.get("seit") else ""))
        vs = ad.vorschlaege(m)
        if vs:
            self.vorschlag.setText("Vorschlag: " + "; ".join(
                f"{ad.FELD_TEXT.get(v['feld'], v['feld'])} {v['wert']} ({v['grund']})" for v in vs))
            self.vorschlag.show()
            self.k_bestaetigen.show()
            self.k_verwerfen.show()
        for k, f in self.felder.items():
            f.setText(m.get(k) or "")
        self.bearbeiter.clear()
        self.bearbeiter.addItems([""] + s.kollegen())
        self.bearbeiter.setCurrentText(m.get("bearbeiter") or "")
        self.status.setCurrentText(m.get("status") or "")
        self.prioritaet.setCurrentText(m.get("prioritaet") or "")
        self.faellig_an.setChecked(bool(m.get("faellig")))
        if m.get("faellig"):
            self.faellig.setDate(QDate.fromString(str(m["faellig"])[:10], "yyyy-MM-dd"))
        self.aufgabe.setText(m.get("aufgabe") or "")
        self.notiz.setText(m.get("notiz") or "")
        self.verlauf.setHtml("".join(
            f"<p><b>{_iso_text(v['zeit'])} {v['wer']}</b>: {ad.verlauf_text(v)}</p>"
            for v in ad.verlauf(s.db, e.datei, grenze=100)) or "<i>Noch nichts.</i>")
        self.versionen.clear()
        p = ad.pfad(s.db, e.datei, s.w)
        if p is not None and not e.ordner:
            for v in ad.versionen(p):
                it = QListWidgetItem(f"V{v['nummer']} · {v['zeit'].replace('_', ' ')} · {v['wer']} · "
                                     f"{ad.groesse_text(v['groesse'])}")
                it.setData(Qt.UserRole, str(v["pfad"]))
                self.versionen.addItem(it)
        self.k_version.setEnabled(self.versionen.count() > 0)
        self.k_kalk.setVisible(e.art == "step")
        self.k_oeffnen.setEnabled(not e.ordner)

    def werte(self):
        w = {k: f.text().strip() for k, f in self.felder.items()}
        w.update(bearbeiter=self.bearbeiter.currentText().strip().upper(), status=self.status.currentText(),
                 prioritaet=self.prioritaet.currentText(),
                 faellig=self.faellig.date().toString("yyyy-MM-dd") if self.faellig_an.isChecked() else "",
                 aufgabe=self.aufgabe.text().strip(), notiz=self.notiz.text().strip())
        return w


class AustauschSeite(QWidget):
    """Reiter „Austausch“ im Hauptfenster."""
    titel = "Austausch"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.stumm = getattr(fenster, "stumm", False)
        self.w = {}
        self.index = {}                 # Bereich -> [Eintrag]
        self.index_zeit = 0.0
        self.metas = {}
        self.ansicht = (UEBERSICHT, None, "")       # (Art, Bereich, Ordner)
        self.filter_ = ad.Filter()
        self.sortierung = ("name", False)
        self.inhalt = None
        self._bilder = {}
        self._lauf = None
        self.antworten = []             # Tests: vorbereitete Antworten auf Rückfragen
        self.meldungen = []             # Tests: gezeigte Benachrichtigungen
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        # Kopfzeile
        kopf = QHBoxLayout()
        self.pfad_zeile = QHBoxLayout()
        kopf.addLayout(self.pfad_zeile)
        kopf.addStretch(1)
        self.k_hoch = QPushButton("Hochladen …")
        self.k_hoch.setObjectName("primaer")
        self.k_hoch.setToolTip("Dateien in den gewählten Ordner legen (oder einfach in die Liste ziehen)")
        self.k_hoch.clicked.connect(lambda: self.hochladen_dialog())
        self.k_ordner = QPushButton("Neuer Ordner")
        self.k_ordner.clicked.connect(lambda: self.ordner_neu())
        self.k_neu = QPushButton("Aktualisieren")
        self.k_neu.setToolTip("Ordner neu einlesen (F5)")
        self.k_neu.clicked.connect(lambda: self.neu_laden(einlesen=True))
        self.k_meldung = QPushButton("Benachrichtigungen …")
        self.k_meldung.clicked.connect(lambda: self.meldungen_dialog())
        for k in (self.k_hoch, self.k_ordner, self.k_neu, self.k_meldung):
            kopf.addWidget(k)
        lay.addLayout(kopf)
        # Suche und Filter
        fz = QHBoxLayout()
        self.suche = QLineEdit()
        self.suche.setObjectName("austausch_suche")
        self.suche.setClearButtonEnabled(True)
        self.suche.setPlaceholderText("Suchen in allen Bereichen: Name, Kunde, Nummer, Mitarbeiter, Kommentar, Inhalt …")
        self.suche.textChanged.connect(lambda _: self._suche_timer.start(250))
        self._suche_timer = QTimer(self)
        self._suche_timer.setSingleShot(True)
        self._suche_timer.timeout.connect(lambda: self.filter_anwenden())
        self.typ = QComboBox()
        self.typ.addItem("Alle Typen", "")
        for a, t, _ in ad._ARTEN:
            self.typ.addItem(t, a)
        self.typ.addItem("Ordner", "ordner")
        self.mitarbeiter = QComboBox()
        self.status = QComboBox()
        self.status.addItem("Jeder Status", "")
        for s in ad.STATUS:
            self.status.addItem(s, s)
        self.kunde = QLineEdit()
        self.kunde.setPlaceholderText("Kundennr.")
        self.kunde.setMaximumWidth(90)
        self.zeitraum = QComboBox()
        for v, t in ZEITRAUM:
            self.zeitraum.addItem(t, v)
        self.sortieren = QComboBox()
        for k, t in ad.SORTIERUNG:
            self.sortieren.addItem(f"Sortiert: {t}", k)
        self.absteigend = QToolButton()
        self.absteigend.setText("↑")
        self.absteigend.setCheckable(True)
        self.absteigend.setToolTip("Reihenfolge umkehren")
        self.k_kacheln = QToolButton()
        self.k_kacheln.setText("Kacheln")
        self.k_kacheln.setCheckable(True)
        self.k_kacheln.setToolTip("Zwischen Liste und Kacheln (mit Vorschaubildern) wechseln")
        self.k_speichern = QToolButton()
        self.k_speichern.setText("Suche merken")
        self.k_speichern.clicked.connect(lambda: self.suche_merken())
        for c in (self.typ, self.mitarbeiter, self.status, self.zeitraum, self.sortieren):
            c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            c.setMinimumContentsLength(9)
            c.currentIndexChanged.connect(lambda _: self.filter_anwenden())
        self.kunde.textChanged.connect(lambda _: self._suche_timer.start(250))
        self.absteigend.toggled.connect(lambda _: self.filter_anwenden())
        self.k_kacheln.toggled.connect(self.kacheln_umschalten)
        fz.addWidget(self.suche, 3)
        for c in (self.typ, self.mitarbeiter, self.status, self.kunde, self.zeitraum, self.sortieren, self.absteigend,
                  self.k_kacheln, self.k_speichern):
            fz.addWidget(c)
        lay.addLayout(fz)
        # Mitte: Navigation | Inhalt | Info
        self.teiler = QSplitter(Qt.Horizontal)
        self.nav = QTreeWidget()
        self.nav.setHeaderHidden(True)
        self.nav.setMinimumWidth(170)
        self.nav.itemClicked.connect(self._nav_geklickt)
        self.nav.setContextMenuPolicy(Qt.CustomContextMenu)
        self.nav.customContextMenuRequested.connect(self._nav_menue)
        self.teiler.addWidget(self.nav)
        self.stapel = QStackedWidget()
        self.modell = DateiModell(self)
        self.liste = Liste(self)
        self.liste.setModel(self.modell)
        self.kachel = Kacheln(self)
        self.kachel.setModel(self.modell)
        self.kachel.setSelectionModel(self.liste.selectionModel())
        self.uebersicht = Uebersicht(self)
        self.uebersicht.gewaehlt.connect(self._uebersicht_gewaehlt)
        self.uebersicht.datei_gewaehlt.connect(self.zeige_datei)
        self.leer = QLabel("")
        self.leer.setAlignment(Qt.AlignCenter)
        for w in (self.uebersicht, self.liste, self.kachel):
            self.stapel.addWidget(w)
        for v in (self.liste, self.kachel):
            v.doubleClicked.connect(lambda i: self.oeffnen_doppelt(i.row()))
            v.customContextMenuRequested.connect(self._menue)
        self.liste.selectionModel().selectionChanged.connect(lambda *_: self._auswahl())
        self.liste.horizontalHeader().sectionClicked.connect(self._spalte_sortieren)
        self.teiler.addWidget(self.stapel)
        self.info = Info(self)
        self.teiler.addWidget(self.info)
        self.teiler.setStretchFactor(1, 1)
        self.teiler.setSizes([200, 760, 340])
        lay.addWidget(self.teiler, 1)
        self.statuszeile = QLabel("")
        self.statuszeile.setObjectName("hinweis")
        lay.addWidget(self.statuszeile)
        self.setAcceptDrops(True)
        self._takt = QTimer(self)
        self._takt.timeout.connect(self.takt)
        if not self.stumm:
            self._takt.start(60_000)
        self._nav_fuellen()

    # -------------------------------------------------------------- Daten
    def kollegen(self):
        from . import teilen
        k = set(teilen.mitarbeiter(self.db)) | {ad.kuerzel(self.db)}
        for m in self.metas.values():           # auch Kürzel, die nur in Zuweisungen vorkommen
            k |= {m.get("bearbeiter"), m.get("hochgeladen_von")}
        return sorted(x for x in k if x)

    def erststart(self):
        t = self.db.einstellung("austausch_erststart")
        if not t:
            t = time.time()
            self.db.einstellung_setzen("austausch_erststart", t)
        return float(t)

    def einlesen(self, sofort=None):
        """Bereiche einlesen. Im Hauptfenster im Hintergrund (Dateisystem, keine Datenbank); stumm sofort."""
        self.w = ad.wurzeln(self.db, anlegen=True)
        sofort = self.stumm if sofort is None else sofort
        if sofort:
            self.index = ad.alle(self.db, w=self.w)
            self.index_zeit = time.monotonic()
            self._inhalt_lesen()
            return
        if self._lauf is not None and self._lauf.is_alive():
            return
        import threading
        w = dict(self.w)
        ergebnis = {}

        def arbeit():
            ergebnis["index"] = ad.alle(self.db, w=w)
        self._lauf = threading.Thread(target=arbeit, name="Austausch einlesen", daemon=True)
        from . import hintergrund
        self._lauf.start()
        hintergrund.melden(self._lauf)
        self.statuszeile.setText("Ordner werden eingelesen …")

        def fertig():
            if self._lauf is not None and self._lauf.is_alive():
                QTimer.singleShot(150, fertig)
                return
            if "index" in ergebnis:
                self.index = ergebnis["index"]
                self.index_zeit = time.monotonic()
                self._inhalt_lesen()
                self._zeigen()
        QTimer.singleShot(150, fertig)

    def _inhalt_lesen(self):
        if self.inhalt is None:
            self.inhalt = ad.Inhalt(Path(getattr(self.db, "pfad", ".")).parent / "Austausch_Cache")
        self.inhalt.lesen(self.alle_eintraege(), self.w, hoechstens=200 if not self.stumm else 2000)
        self.inhalt.speichern()

    def alle_eintraege(self):
        return [e for liste in self.index.values() for e in liste]

    def neu_laden(self, einlesen=None):
        if einlesen or not self.index or time.monotonic() - self.index_zeit > 30:
            self.einlesen()
        self.metas = ad.meta(self.db)
        self._nav_fuellen()
        self._zeigen()
        if hasattr(self.f, "anzeige_merken"):
            pass

    # -------------------------------------------------------------- Navigation
    def _nav_fuellen(self):
        aktuell = self.ansicht
        self.nav.blockSignals(True)
        self.nav.clear()
        alle = self.alle_eintraege()
        g = ad.gesehen(self.db)
        zahl = {NEU_FUER_MICH: sum(1 for e in alle if not e.ordner and not e.archiv
                                   and ad.ist_neu(g, e, self.erststart(), self.metas.get(e.datei))),
                MEINE: sum(1 for m in self.metas.values() if m.get("bearbeiter") == ad.kuerzel(self.db)
                           and m.get("status") not in (ad.FERTIG, ad.ARCHIVIERT) and not m.get("weg"))}
        oben = QTreeWidgetItem(["Schnellzugriff"])
        oben.setFlags(Qt.ItemIsEnabled)
        self.nav.addTopLevelItem(oben)
        for k, t in SCHNELL:
            it = QTreeWidgetItem([f"{t} ({zahl[k]})" if zahl.get(k) else t])
            it.setData(0, Qt.UserRole, (k, None, ""))
            oben.addChild(it)
        bo = QTreeWidgetItem(["Bereiche"])
        bo.setFlags(Qt.ItemIsEnabled)
        self.nav.addTopLevelItem(bo)
        for b, t in ad.BEREICHE:
            if self.w.get(b) is None and self.w:
                continue
            it = QTreeWidgetItem([t])
            it.setData(0, Qt.UserRole, ("bereich", b, ""))
            it.setToolTip(0, str(self.w.get(b) or ""))
            bo.addChild(it)
        for k, t in ((ARCHIV, "Archiv"), (PAPIERKORB, "Papierkorb")):
            it = QTreeWidgetItem([t])
            it.setData(0, Qt.UserRole, (k, None, ""))
            bo.addChild(it)
        suchen = ad.gespeicherte_suchen(self.db)
        if suchen:
            so = QTreeWidgetItem(["Gespeicherte Suchen"])
            so.setFlags(Qt.ItemIsEnabled)
            self.nav.addTopLevelItem(so)
            for s in suchen:
                it = QTreeWidgetItem([s["name"]])
                it.setData(0, Qt.UserRole, (SUCHE, s["name"], ""))
                so.addChild(it)
        self.nav.expandAll()
        self.nav.blockSignals(False)
        self.ansicht = aktuell
        self._mitarbeiter_fuellen()

    def _mitarbeiter_fuellen(self):
        alt = self.mitarbeiter.currentData()
        self.mitarbeiter.blockSignals(True)
        self.mitarbeiter.clear()
        self.mitarbeiter.addItem("Alle Mitarbeiter", "")
        for k in self.kollegen():
            self.mitarbeiter.addItem(k, k)
        i = self.mitarbeiter.findData(alt)
        self.mitarbeiter.setCurrentIndex(max(i, 0))
        self.mitarbeiter.blockSignals(False)

    def _nav_geklickt(self, it, _spalte=0):
        d = it.data(0, Qt.UserRole)
        if d:
            self.gehe(*d)

    def gehe(self, art, bereich=None, ordner=""):
        """Ansicht wechseln: Schnellzugriff, Bereich (mit Unterordner), Archiv, Papierkorb, gespeicherte Suche."""
        if art == SUCHE:
            s = next((x for x in ad.gespeicherte_suchen(self.db) if x["name"] == bereich), None)
            if s:
                self.filter_setzen(ad.Filter.aus(s["filter"]))
            art, bereich, ordner = "alle", None, ""
        self.ansicht = (art, bereich, ordner or "")
        self._zeigen()

    def _uebersicht_gewaehlt(self, ziel):
        if ziel in (NEU_FUER_MICH, MEINE):
            return self.gehe(ziel)
        if ziel == "vorschlag":
            self.ansicht = ("vorschlag", None, "")
            return self._zeigen()
        self.status.setCurrentIndex(max(self.status.findData(ziel), 0))
        self.gehe("alle")

    def _pfad_zeile(self):
        while self.pfad_zeile.count():
            w = self.pfad_zeile.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        art, b, o = self.ansicht
        if art != "bereich":
            t = dict(SCHNELL).get(art) or {ARCHIV: "Archiv", PAPIERKORB: "Papierkorb", "alle": "Suche in allen "
                                           "Bereichen", "vorschlag": "Zuordnung bestätigen"}.get(art, art)
            lab = QLabel(f"<b>{t}</b>")
            self.pfad_zeile.addWidget(lab)
            return
        teile = [("", ad.BEREICH_TITEL.get(b, b))] + [("/".join(o.split("/")[:i + 1]), x)
                                                      for i, x in enumerate(o.split("/")) if x]
        for i, (rel, t) in enumerate(teile):
            k = QToolButton()
            k.setText(t)
            k.setAutoRaise(True)
            k.clicked.connect(lambda _=False, r=rel: self.gehe("bereich", b, r))
            self.pfad_zeile.addWidget(k)
            if i < len(teile) - 1:
                self.pfad_zeile.addWidget(QLabel("›"))

    # -------------------------------------------------------------- Anzeige
    def filter_aus_feldern(self):
        return ad.Filter(text=self.suche.text(), art=self.typ.currentData() if self.typ.currentData() != "ordner"
                         else "", mitarbeiter=self.mitarbeiter.currentData() or "", kunde=self.kunde.text().strip(),
                         status=self.status.currentData() or "", seit_tage=int(self.zeitraum.currentData() or 0))

    def filter_setzen(self, f):
        for c, v in ((self.typ, f.art), (self.mitarbeiter, f.mitarbeiter), (self.status, f.status),
                     (self.zeitraum, f.seit_tage or "")):
            c.blockSignals(True)
            c.setCurrentIndex(max(c.findData(v), 0))
            c.blockSignals(False)
        self.kunde.blockSignals(True)
        self.kunde.setText(f.kunde)
        self.kunde.blockSignals(False)
        self.suche.blockSignals(True)
        self.suche.setText(f.text)
        self.suche.blockSignals(False)

    def filter_anwenden(self):
        art = self.ansicht[0]
        f = self.filter_aus_feldern()
        if art in (UEBERSICHT,) and (f.text or f.art or f.mitarbeiter or f.kunde or f.status or f.seit_tage):
            self.ansicht = ("alle", None, "")
        elif art == "bereich" and f.text:
            self.ansicht = ("alle", None, "")       # Suche läuft über alle Bereiche
        self._zeigen()

    def sichtbare(self):
        """Einträge der aktuellen Ansicht (gefiltert und sortiert)."""
        art, b, o = self.ansicht
        f = self.filter_aus_feldern()
        alle = self.alle_eintraege()
        ich = ad.kuerzel(self.db)
        g = ad.gesehen(self.db)
        if art == "bereich":
            basis = [e for e in self.index.get(b, []) if e.ordner_rel == o and not e.archiv]
        elif art == ARCHIV:
            basis = [e for e in alle if e.archiv]
            f.archiv = True
        elif art == NEU_FUER_MICH:
            basis = alle
            f.nur_neu, f.ordner = True, False
        elif art == MEINE:
            basis = alle
            f.nur_meine, f.ordner = True, False
            basis = [e for e in basis if (self.metas.get(e.datei) or {}).get("status") not in (ad.FERTIG,
                                                                                            ad.ARCHIVIERT)]
        elif art == FAVORITEN:
            fav = ad.favoriten(self.db)
            basis = [e for e in alle if e.datei in fav]
        elif art == ZULETZT:
            z = ad.zuletzt(self.db)
            basis = sorted((e for e in alle if e.datei in z), key=lambda e: z.index(e.datei))
        elif art == WER:
            dateien = {x["datei"] for x in ad.wer_arbeitet(self.db, self.w, self.metas)}
            basis = [e for e in alle if e.datei in dateien]
        elif art == "vorschlag":
            basis = [e for e in alle if ad.vorschlaege(self.metas.get(e.datei) or {})]
            f.ordner = False
        else:                       # alle (Suche)
            basis = alle
            f.ordner = bool(f.text)
        if self.typ.currentData() == "ordner":
            basis = [e for e in basis if e.ordner]
        kunden = {}
        if f.text:
            kunden = {str(k): n for k, n in self.db.con.execute("SELECT kundennr, name FROM kunden") if k}
        liste = ad.filtern(basis, self.metas, f, ich=ich, gesehen_=g,
                           inhalt=self.inhalt.text() if self.inhalt and f.text else None,
                           kommentare=ad.kommentare_text(self.db) if f.text else None, erststart=self.erststart(),
                           kunden_namen=kunden)
        if art == ZULETZT and not self.absteigend.isChecked() and self.sortieren.currentData() == "name":
            return liste
        return ad.sortieren(liste, self.metas, self.sortieren.currentData() or "name", self.absteigend.isChecked())

    def _zeigen(self):
        self._pfad_zeile()
        art = self.ansicht[0]
        b = self.ansicht[1]
        schreiben = art == "bereich" and b not in ad.NUR_LESEN
        self.k_hoch.setEnabled(schreiben)
        self.k_ordner.setEnabled(schreiben and not (b in ad.OHNE_ORDNER_OBEN and not self.ansicht[2]))
        if art == UEBERSICHT:
            self.stapel.setCurrentWidget(self.uebersicht)
            u = ad.uebersicht(self.db, self.alle_eintraege(), self.metas, ad.gesehen(self.db),
                              erststart=self.erststart())
            self.uebersicht.fuellen(u)
            self.statuszeile.setText(self._stand_text())
            self.info.zeigen(None)
            return
        if art == PAPIERKORB:
            self._papierkorb_zeigen()
            return
        liste = self.sichtbare()
        g = ad.gesehen(self.db)
        neu = {e.datei for e in liste if not e.ordner
               and ad.ist_neu(g, e, self.erststart(), self.metas.get(e.datei))}
        self.modell.setzen(liste, self.metas, neu)
        self.stapel.setCurrentWidget(self.kachel if self.k_kacheln.isChecked() else self.liste)
        self.liste.setColumnHidden(len(SPALTEN) - 1, art == "bereich")
        self.statuszeile.setText(f"{sum(1 for e in liste if not e.ordner)} Datei(en)"
                                 + (f", {sum(1 for e in liste if e.ordner)} Ordner" if any(e.ordner for e in liste)
                                    else "") + " · " + self._stand_text())
        if not liste:
            self.statuszeile.setText("Keine Einträge. " + ("Dateien hierher ziehen oder „Hochladen …“."
                                                           if schreiben else ""))
        self._auswahl()

    def _stand_text(self):
        uploads = ad.laufende_uploads(self.db, self.w) if self.w.get(ad.DATEIEN) else []
        t = f"Ordner: {self.w.get(ad.DATEIEN) or '–'}"
        if uploads:
            t += " · gerade hochgeladen: " + ", ".join(f"{u.get('wer')}: {u.get('datei', '').partition(':')[2]}"
                                                         for u in uploads[:3])
        return t

    def _papierkorb_zeigen(self):
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
        korb = ad.papierkorb(self.db, self.w)
        t = getattr(self, "_korb_tabelle", None)
        if t is None:
            box = QWidget()
            lay = QVBoxLayout(box)
            t = QTableWidget(0, 4)
            t.setHorizontalHeaderLabels(["Name", "Ursprünglich", "Gelöscht von", "Gelöscht am"])
            t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.verticalHeader().hide()
            lay.addWidget(t)
            zeile = QHBoxLayout()
            k1 = QPushButton("Wiederherstellen")
            k1.clicked.connect(lambda: self.korb_zurueck())
            k2 = QPushButton("Endgültig löschen …")
            k2.setToolTip("Nur der Administrator")
            k2.clicked.connect(lambda: self.korb_endgueltig())
            k3 = QPushButton(f"Älter als {ad.PAPIERKORB_TAGE} Tage leeren …")
            k3.clicked.connect(lambda: self.korb_leeren())
            for k in (k1, k2, k3):
                zeile.addWidget(k)
            zeile.addStretch(1)
            lay.addLayout(zeile)
            self._korb_tabelle, self._korb_box = t, box
            self._korb_knopf_endgueltig = k2
            self._korb_knopf_leeren = k3
            self.stapel.addWidget(box)
        self._korb = korb
        t.setRowCount(len(korb))
        for i, e in enumerate(korb):
            for j, v in enumerate((e.get("name"), e.get("datei", "").partition(":")[2], e.get("wer"),
                                   _iso_text(e.get("zeit")))):
                t.setItem(i, j, QTableWidgetItem(v or ""))
        darf = ad.darf_endgueltig(self.db)
        self._korb_knopf_endgueltig.setEnabled(darf)
        self._korb_knopf_leeren.setEnabled(darf)
        self.stapel.setCurrentWidget(self._korb_box)
        self.statuszeile.setText(f"{len(korb)} Einträge im Papierkorb. Gelöschte Dateien bleiben hier, bis der "
                                 "Administrator sie endgültig löscht.")
        self.info.zeigen(None)

    def kacheln_umschalten(self, an):
        self.modell.kacheln = bool(an)
        self.k_kacheln.setText("Liste" if an else "Kacheln")
        v = self.db.einstellung(ad.L_ANSICHT) or {}
        v = dict(v) if isinstance(v, dict) else {}
        v["kacheln"] = bool(an)
        self.db.einstellung_setzen(ad.L_ANSICHT, v)
        if self.ansicht[0] not in (UEBERSICHT, PAPIERKORB):
            self.stapel.setCurrentWidget(self.kachel if an else self.liste)
            self.modell.layoutChanged.emit()

    def _spalte_sortieren(self, i):
        k = {"zeit": "zeit", "groesse": "groesse", "art": "art", "kundennr": "kunde", "bearbeiter": "mitarbeiter"
             }.get(SPALTEN[i][0], "name")
        j = self.sortieren.findData(k)
        if j == self.sortieren.currentIndex():
            self.absteigend.setChecked(not self.absteigend.isChecked())
        else:
            self.sortieren.setCurrentIndex(j)

    # -------------------------------------------------------------- Vorschau
    def vorschaubild(self, e, px=VORSCHAU_PX):
        """QIcon mit Vorschaubild (Bilder, PDF erste Seite) oder None; zwischengespeichert je Datei und Stand."""
        if e.ordner or e.art not in ("bild", "pdf"):
            return None
        schl = (e.datei, e.zeit, px)
        if schl in self._bilder:
            return self._bilder[schl]
        p = ad.pfad(self.db, e.datei, self.w)
        bild = None
        cache = Path(getattr(self.db, "pfad", ".")).parent / "Austausch_Cache" / "Vorschau"
        name = hashlib.sha1(f"{e.datei}|{e.zeit}|{px}".encode()).hexdigest()[:24] + ".png"
        try:
            if (cache / name).exists():
                bild = QImage(str(cache / name))
            elif e.art == "bild" and e.groesse < 40 << 20:
                bild = QImage(str(p))
            elif e.art == "pdf" and e.groesse < 60 << 20:
                import pypdfium2 as pdfium
                d = pdfium.PdfDocument(str(p))
                try:
                    s = d[0]
                    b, h = s.get_size()
                    pil = s.render(scale=px / max(b, h, 1)).to_pil().convert("RGB")
                    bild = QImage(pil.tobytes("raw", "RGB"), pil.width, pil.height, 3 * pil.width,
                                  QImage.Format_RGB888).copy()
                finally:
                    d.close()
            if bild is not None and not bild.isNull():
                bild = bild.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                if not (cache / name).exists():
                    cache.mkdir(parents=True, exist_ok=True)
                    bild.save(str(cache / name))
        except Exception:           # noqa: BLE001 – ohne Vorschau weiter
            bild = None
        icon = QIcon(QPixmap.fromImage(bild)) if bild is not None and not bild.isNull() else None
        if len(self._bilder) > 2000:
            self._bilder.clear()
        self._bilder[schl] = icon
        return icon

    def datei_info(self, e):
        """Kurzinfo je Typ: STEP (Bauteile, Baugruppen, Einheit), Mail (Absender, Betreff), Text (Anfang)."""
        p = ad.pfad(self.db, e.datei, self.w)
        if p is None or e.ordner or not p.exists():
            return ""
        try:
            if e.art == "step" and e.endung in (".step", ".stp") and e.groesse < 80 << 20:
                from . import step_vorschau
                u = step_vorschau.zusammen([p])
                return "<br>".join(step_vorschau.zeilen(u)[:3])
            if e.art == "mail":
                from . import mail
                m = mail.lesen(p)
                if m is not None:
                    return (f"Von {m.absender_name or m.absender}<br>Betreff: {m.betreff}"
                            + (f"<br>{len(m.anhaenge)} Anhang/Anhänge" if m.anhaenge else ""))
            if e.art in ("text", "csv", "laser") and e.groesse < 2 << 20:
                t = ad.inhalt_lesen(p, e.art)[:300]
                return "<tt>" + t.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>") + "</tt>"
        except Exception:           # noqa: BLE001
            return ""
        return ""

    def sperre_von(self, e):
        if e.office:
            return dict(wer=e.office, office=True)
        try:
            s = ad.sperre(self.db, e.datei, self.w)
        except OSError:
            return None
        return s if s and not s.get("eigene") else None

    def vorschau(self, e=None):
        e = e or self.gewaehlt_eins()
        if e is None or e.ordner:
            return None
        from . import anhang_vorschau, step
        liste = [x for x in self.modell.eintraege if not x.ordner and x.endung not in ad.GEFAEHRLICH]
        eintraege = [dict(name=x.name, pfad=ad.pfad(self.db, x.datei, self.w), hinweis="") for x in liste]
        i = next((k for k, x in enumerate(liste) if x.datei == e.datei), 0)
        try:
            befehl = step.messprogramm(self.f.programmordner)
        except Exception:           # noqa: BLE001
            befehl = None
        alt = getattr(self, "_vorschau", None)
        if alt is not None:
            alt.close()
        self._vorschau = anhang_vorschau.fenster(self, eintraege, i, self.f.datei_oeffnen, befehl)
        ad.benutzt(self.db, e.datei)
        self.gesehen([e])
        if not self.stumm:
            self._vorschau.show()
            self._vorschau.raise_()
        return self._vorschau

    # -------------------------------------------------------------- Auswahl und Info
    def gewaehlte(self):
        zeilen = sorted({i.row() for i in self.liste.selectionModel().selectedRows()})
        return [self.modell.eintrag(z) for z in zeilen if self.modell.eintrag(z) is not None]

    def gewaehlt_eins(self):
        g = self.gewaehlte()
        return g[0] if g else None

    def _auswahl(self):
        e = self.gewaehlt_eins()
        if e is None:
            self.info.zeigen(None)
            return
        self.info.zeigen(e, self.metas.get(e.datei))

    def waehlen(self, datei):
        """Datei in der aktuellen Liste wählen (Tests, Sprung aus der Übersicht)."""
        for i, e in enumerate(self.modell.eintraege):
            if e.datei == datei:
                self.liste.selectRow(i)
                return e
        return None

    def zeige_datei(self, datei):
        """Zum Ordner der Datei gehen und sie wählen."""
        if not datei:
            return None
        b, rel = ad.zerlegen(datei)
        if rel.startswith(ad.ARCHIV + "/"):
            self.gehe(ARCHIV)
        else:
            self.gehe("bereich", b, rel.rpartition("/")[0])
        return self.waehlen(datei)

    def gesehen(self, eintraege):
        ad.gesehen_setzen(self.db, {e.datei: ad.stand_zeit(e, self.metas.get(e.datei)) for e in eintraege if not e.ordner})

    def oeffnen_doppelt(self, zeile):
        e = self.modell.eintrag(zeile)
        if e is None:
            return
        if e.ordner:
            if e.archiv:
                return
            self.gehe("bereich", e.bereich, e.rel)
            return
        self.vorschau(e)

    def _frage(self, titel, text, knoepfe, vorgabe=0):
        """Rückfrage mit eigenen Knöpfen; Tests: Antwort aus self.antworten. Ergebnis: Index oder None."""
        if self.antworten:
            return self.antworten.pop(0)
        if self.stumm:
            return vorgabe
        box = QMessageBox(self)
        box.setWindowTitle(titel)
        box.setText(text)
        ks = [box.addButton(k, QMessageBox.AcceptRole) for k in knoepfe]
        box.addButton("Abbrechen", QMessageBox.RejectRole)
        box.setDefaultButton(ks[vorgabe])
        box.exec()
        k = box.clickedButton()
        return ks.index(k) if k in ks else None

    def _fehler(self, e):
        text = str(e) if isinstance(e, ad.AustauschFehler) else fehler_text(e)
        self.f.meldung(text, fehler=True)
        if not self.stumm:
            QMessageBox.warning(self, "Austausch", text)

    def info_speichern(self):
        e = self.gewaehlt_eins()
        if e is None:
            return 0
        try:
            n = ad.setzen(self.db, [x.datei for x in self.gewaehlte()], **self.info.werte())
        except ad.AustauschFehler as f:
            self._fehler(f)
            return 0
        self.metas = ad.meta(self.db)
        self.f.meldung(f"{n} Angabe(n) gespeichert." if n else "Nichts geändert.")
        self._puls()
        self._zeigen()
        self.waehlen(e.datei)
        return n

    def vorschlag(self, bestaetigen):
        e = self.gewaehlt_eins()
        if e is None:
            return
        try:
            if bestaetigen:
                ad.vorschlag_bestaetigen(self.db, e.datei)
            else:
                ad.vorschlag_verwerfen(self.db, e.datei)
        except ad.AustauschFehler as f:
            self._fehler(f)
            return
        self.metas = ad.meta(self.db)
        self._zeigen()
        self.waehlen(e.datei)

    def kommentieren(self):
        e = self.gewaehlt_eins()
        t = self.info.kommentar.text().strip()
        if e is None or not t:
            return
        an = ""
        if t.startswith("@"):
            an, _, rest = t[1:].partition(" ")
            an, t = an.upper(), rest.strip() or t
        try:
            ad.kommentar(self.db, e.datei, t, an=an)
        except ad.AustauschFehler as f:
            self._fehler(f)
            return
        self.info.kommentar.clear()
        self.metas = ad.meta(self.db)
        self._puls()
        self.info.zeigen(e, self.metas.get(e.datei))

    def version_zurueck(self):
        e = self.gewaehlt_eins()
        it = self.info.versionen.currentItem() or self.info.versionen.item(0)
        if e is None or it is None:
            return
        if self._frage("Fassung wiederherstellen", f"{e.name}: Fassung „{it.text()}“ wieder aktuell machen?\n\n"
                       "Die jetzige Fassung wird vorher als Version gesichert.", ["Wiederherstellen"]) != 0:
            return
        try:
            ad.version_wiederherstellen(self.db, e.datei, it.data(Qt.UserRole), self.w)
        except (ad.AustauschFehler, OSError) as f:
            self._fehler(f)
            return
        self.f.meldung(f"{e.name}: ältere Fassung wiederhergestellt.")
        self.neu_laden(einlesen=True)

    # -------------------------------------------------------------- Dateioperationen
    def _ziel(self):
        art, b, o = self.ansicht
        return (b, o) if art == "bereich" else (ad.DATEIEN, "")

    def _konflikt_frage(self):
        merk = {}

        def frage(name):
            if "alle" in merk:
                return merk["alle"]
            i = self._frage("Name schon vorhanden", f"„{name}“ gibt es hier schon.\n\nAls neue Version ablegen "
                            "(die alte Fassung wird gesichert), beide behalten (neuer Name) oder überspringen?",
                            ["Neue Version", "Beide behalten", "Überspringen", "Neue Version für alle"], 1)
            modus = {0: ad.VERSION, 1: ad.BEIDE, 2: ad.UEBERSPRINGEN, 3: ad.VERSION}.get(i, ad.UEBERSPRINGEN)
            if i == 3:
                merk["alle"] = ad.VERSION
            return modus
        return frage

    def hochladen(self, pfade, bereich=None, ordner=None):
        """Dateien/Ordner hochladen (mit Fortschritt und Abbrechen). Ergebnis: Bericht."""
        b, o = self._ziel()
        b = bereich or b
        o = o if ordner is None else ordner
        if not pfade:
            return None
        fortschritt = None
        abbrechen = None
        if not self.stumm:
            dlg = QProgressDialog("Dateien werden abgelegt …", "Abbrechen", 0, 1000, self)
            dlg.setWindowModality(Qt.WindowModal)
            dlg.setMinimumDuration(400)

            def fortschritt(n, g, name):
                dlg.setLabelText(f"{name}\n{ad.groesse_text(n)} von {ad.groesse_text(g)}")
                dlg.setValue(int(1000 * n / max(g, 1)))
                QApplication.processEvents()

            def abbrechen():
                return dlg.wasCanceled()
        try:
            bericht = ad.hochladen(self.db, pfade, b, o, konflikt=self._konflikt_frage(), fortschritt=fortschritt,
                                   abbrechen=abbrechen, w=self.w or None)
        except ad.AustauschFehler as f:
            self._fehler(f)
            return None
        finally:
            if not self.stumm:
                dlg.close()
        self.f.meldung(bericht.text(), fehler=not bericht.ok)
        self._puls()
        self.neu_laden(einlesen=True)
        self.gesehen([x for x in self.alle_eintraege() if x.datei in bericht.neu])
        return bericht

    def hochladen_dialog(self, pfade=None):
        if pfade is None:
            pfade, _ = QFileDialog.getOpenFileNames(self, "Dateien hochladen")
        return self.hochladen([Path(p) for p in pfade])

    def ordner_neu(self, name=None):
        b, o = self._ziel()
        if name is None:
            name, ok = QInputDialog.getText(self, "Neuer Ordner", "Name des Ordners:")
            if not ok:
                return None
        try:
            d = ad.ordner_anlegen(self.db, b, o, name, self.w or None)
        except ad.AustauschFehler as f:
            self._fehler(f)
            return None
        self.neu_laden(einlesen=True)
        return d

    def abgelegt(self, daten, ziel=None):
        """Drop auf die Liste: interne Einträge verschieben, Dateien von außen hochladen."""
        b, o = self._ziel()
        if ziel is not None:
            b, o = ziel.bereich, ziel.rel
        if daten.hasFormat(MIME):
            dateien = [d for d in bytes(daten.data(MIME)).decode("utf-8").split("\n") if d]
            dateien = [d for d in dateien if not (ziel is not None and d == ziel.datei)]
            if not dateien:
                return
            if self.ansicht[0] != "bereich" and ziel is None:
                return
            try:
                ad.verschieben(self.db, dateien, b, o, self.w)
            except (ad.AustauschFehler, OSError) as f:
                self._fehler(f)
            self._puls()
            self.neu_laden(einlesen=True)
            return
        pfade = [Path(u.toLocalFile()) for u in daten.urls() if u.isLocalFile()]
        if self.ansicht[0] != "bereich" and ziel is None:
            self.f.meldung("Zum Ablegen bitte einen Bereich oder Ordner links wählen (z. B. Gemeinsame Dateien).")
            return
        self.hochladen(pfade, b, o)

    def dragEnterEvent(self, ereignis):
        if ereignis.mimeData().hasUrls() or ereignis.mimeData().hasFormat(MIME):
            ereignis.acceptProposedAction()

    def dropEvent(self, ereignis):
        self.abgelegt(ereignis.mimeData())
        ereignis.acceptProposedAction()

    def herunterladen(self, ziel=None):
        g = self.gewaehlte()
        if not g:
            return []
        if ziel is None:
            ziel = QFileDialog.getExistingDirectory(self, "Herunterladen nach")
            if not ziel:
                return []
        try:
            out = ad.herunterladen(self.db, [e.datei for e in g], ziel, w=self.w)
        except (ad.AustauschFehler, OSError) as f:
            self._fehler(f)
            return []
        self.f.meldung(f"{len(out)} Datei(en) nach {ziel} kopiert.")
        return out

    def _ziel_waehlen(self, titel, antwort=None):
        """Zielordner wählen: [(Text, Bereich, Ordner)] aus allen beschreibbaren Bereichen."""
        ziele = []
        for b, t in ad.BEREICHE:
            if self.w.get(b) is None or b in ad.NUR_LESEN:
                continue
            if b not in ad.OHNE_ORDNER_OBEN:
                ziele.append((t, b, ""))
            for e in self.index.get(b, []):
                if e.ordner and not e.archiv:
                    ziele.append((f"{t}/{e.rel}", b, e.rel))
        if antwort is not None:
            return next(((b, o) for t, b, o in ziele if t == antwort), None)
        if self.antworten:
            return self.antworten.pop(0)
        text, ok = QInputDialog.getItem(self, titel, "Zielordner:", [t for t, _, _ in ziele], 0, False)
        if not ok:
            return None
        return next(((b, o) for t, b, o in ziele if t == text), None)

    def kopieren_nach(self, ziel=None, verschieben=False):
        g = self.gewaehlte()
        if not g:
            return []
        ziel = ziel or self._ziel_waehlen("Verschieben nach" if verschieben else "Kopieren nach")
        if not ziel:
            return []
        try:
            fn = ad.verschieben if verschieben else ad.kopieren
            out = fn(self.db, [e.datei for e in g], ziel[0], ziel[1], self.w)
        except (ad.AustauschFehler, OSError) as f:
            self._fehler(f)
            return []
        self._puls()
        self.neu_laden(einlesen=True)
        return out

    def umbenennen(self, name=None):
        e = self.gewaehlt_eins()
        if e is None:
            return None
        if name is None:
            name, ok = QInputDialog.getText(self, "Umbenennen", "Neuer Name:", text=e.name)
            if not ok:
                return None
        try:
            neu = ad.umbenennen(self.db, e.datei, name, self.w)
        except (ad.AustauschFehler, OSError) as f:
            self._fehler(f)
            return None
        self._puls()
        self.neu_laden(einlesen=True)
        self.waehlen(neu)
        return neu

    def loeschen(self):
        g = self.gewaehlte()
        if not g:
            return 0
        if self._frage("In den Papierkorb", f"{len(g)} Eintrag/Einträge in den Papierkorb verschieben?\n\n"
                       "Im Papierkorb lassen sie sich wiederherstellen.", ["In den Papierkorb"]) != 0:
            return 0
        try:
            n = ad.loeschen(self.db, [e.datei for e in g], self.w)
        except (ad.AustauschFehler, OSError) as f:
            self._fehler(f)
            return 0
        self.f.meldung(f"{n} Eintrag/Einträge im Papierkorb.")
        self._puls()
        self.neu_laden(einlesen=True)
        return n

    def archivieren(self):
        g = self.gewaehlte()
        if not g:
            return []
        try:
            if all(e.archiv for e in g):
                out = [ad.aus_archiv(self.db, e.datei, self.w) for e in g]
            else:
                out = ad.archivieren(self.db, [e.datei for e in g if not e.archiv], self.w)
        except (ad.AustauschFehler, OSError) as f:
            self._fehler(f)
            return []
        self._puls()
        self.neu_laden(einlesen=True)
        return out

    def bearbeiten(self, e=None):
        """Mit dem zugehörigen Programm öffnen: weiche Sperre und Sicherung der vorigen Fassung."""
        e = e or self.gewaehlt_eins()
        if e is None or e.ordner:
            return None
        try:
            p, fremd = ad.bearbeiten(self.db, e.datei, w=self.w)
            if fremd:
                i = self._frage("Wird gerade bearbeitet", f"{e.name} wird gerade von {fremd['wer']} bearbeitet"
                                + (f" (seit {_iso_text(fremd.get('seit'))})" if fremd.get("seit") else "")
                                + ".\n\nGleichzeitig bearbeiten kann Änderungen überschreiben. Die jetzige Fassung "
                                "wird gesichert und lässt sich wiederherstellen.",
                                ["Nur ansehen", "Trotzdem bearbeiten"], 0)
                if i == 0:
                    return self.vorschau(e)
                if i != 1:
                    return None
                p, _ = ad.bearbeiten(self.db, e.datei, trotzdem=True, w=self.w)
        except (ad.AustauschFehler, OSError) as f:
            self._fehler(f)
            return None
        ad.benutzt(self.db, e.datei)
        self.__dict__.setdefault("eigene_sperren", set()).add(e.datei)
        self.f.datei_oeffnen(p)
        self.f.meldung(f"{e.name} geöffnet. Die Kollegen sehen „in Bearbeitung“; die vorige Fassung ist gesichert.")
        return p

    def bearbeitung_beenden(self):
        e = self.gewaehlt_eins()
        if e is None:
            return
        ad.entsperren(self.db, e.datei, self.w)
        self.__dict__.setdefault("eigene_sperren", set()).discard(e.datei)
        self._auswahl()

    def in_kalkulation(self, ins_offene=None):
        """STEP-Dateien als neues Angebot kalkulieren (Kunde aus der Zuordnung) oder ins geöffnete Angebot."""
        g = [e for e in self.gewaehlte() if e.art == "step"]
        if not g:
            self.f.meldung("Bitte STEP-Dateien wählen.")
            return None
        pfade = [ad.pfad(self.db, e.datei, self.w) for e in g]
        kd = next(((self.metas.get(e.datei) or {}).get("kundennr") for e in g
                   if (self.metas.get(e.datei) or {}).get("kundennr")), None)
        seite = self.f.reiter.currentWidget() if hasattr(self.f, "reiter") else None
        offene = [s for s in getattr(self.f, "offen", {}).values()]
        if ins_offene is None and offene:
            i = self._frage("In Kalkulation", f"{len(g)} STEP-Datei(en) kalkulieren:", [
                "Neues Angebot", f"In {getattr(offene[-1], 'kopf', {}).get('nummer') or 'geöffnetes Angebot'}"], 0)
            if i is None:
                return None
            ins_offene = i == 1
        for e in g:
            ad.benutzt(self.db, e.datei)
        if ins_offene and offene:
            seite = offene[-1]
            return seite.step_importieren(dateien=[str(p) for p in pfade])
        return self.f.angebote.neu_aus_step([str(p) for p in pfade], kundennr=kd)

    def als_anfrage(self):
        """MSG/EML in den Anfrage-Ordner legen: dort übernimmt die Anfragenverwaltung sie wie aus Outlook."""
        g = [e for e in self.gewaehlte() if e.art == "mail"]
        if not g:
            return []
        from . import anfragen
        ziel = anfragen.ordner(self.db)
        if ziel is None:
            self._fehler(ad.AustauschFehler("Kein Anfrage-Ordner eingerichtet (Einstellungen → Anfragen)."))
            return []
        out = []
        for e in g:
            p = ad.pfad(self.db, e.datei, self.w)
            z = ad._frei(Path(ziel) / p.name)
            ad._kopieren(p, z)
            out.append(z)
            with self.db.con:
                ad.ereignis(self.db, e.datei, ad.E_KOPIERT, "als Kundenanfrage übernommen")
        self.f.meldung(f"{len(out)} Mail(s) an die Anfragenverwaltung übergeben. Sie erscheinen unter Anfragen.")
        if hasattr(self.f, "anfragen_seite"):
            try:
                self.f.anfragen_seite.neu_laden()
            except Exception:       # noqa: BLE001
                pass
        return out

    def zuordnung_erkennen(self):
        from . import austausch_zuordnung as az
        g = [e for e in self.gewaehlte() if not e.ordner] or [e for e in self.modell.eintraege if not e.ordner]
        n = 0
        ktx = az.Kontext(self.db)
        for e in g:
            gesetzt, vs = az.anwenden(self.db, e.datei, ktx=ktx)
            n += bool(gesetzt or vs)
        self.metas = ad.meta(self.db)
        self.f.meldung(f"Zuordnung erkannt: {n} von {len(g)} Datei(en) mit Treffern.")
        self._zeigen()
        return n

    def zuweisen(self, an):
        g = self.gewaehlte()
        if not g:
            return 0
        try:
            n = ad.setzen(self.db, [e.datei for e in g], bearbeiter=an)
        except ad.AustauschFehler as f:
            self._fehler(f)
            return 0
        self.metas = ad.meta(self.db)
        self._puls()
        self._zeigen()
        return n

    def status_setzen(self, status):
        g = self.gewaehlte()
        if not g:
            return 0
        try:
            n = ad.setzen(self.db, [e.datei for e in g], status=status)
        except ad.AustauschFehler as f:
            self._fehler(f)
            return 0
        self.metas = ad.meta(self.db)
        self._puls()
        self._zeigen()
        return n

    def im_explorer(self):
        e = self.gewaehlt_eins()
        if e is None:
            art, b, o = self.ansicht
            p = ad.pfad(self.db, ad.schluessel(b, o), self.w) if art == "bereich" else self.w.get(ad.DATEIEN)
        else:
            p = ad.pfad(self.db, e.datei, self.w)
            p = p if e.ordner else p.parent
        if p is not None:
            self.f.datei_oeffnen(p)

    # -------------------------------------------------------------- Papierkorb
    def _korb_gewaehlt(self):
        t = self._korb_tabelle
        return [self._korb[i.row()] for i in t.selectionModel().selectedRows() if i.row() < len(self._korb)]

    def korb_zurueck(self, eintraege=None):
        n = 0
        for e in (eintraege if eintraege is not None else self._korb_gewaehlt()):
            try:
                ad.wiederherstellen(self.db, e, self.w)
                n += 1
            except (ad.AustauschFehler, OSError) as f:
                self._fehler(f)
        self.f.meldung(f"{n} Eintrag/Einträge wiederhergestellt.")
        self.neu_laden(einlesen=True)
        return n

    def korb_endgueltig(self, eintraege=None):
        liste = eintraege if eintraege is not None else self._korb_gewaehlt()
        if not liste or self._frage("Endgültig löschen", f"{len(liste)} Eintrag/Einträge endgültig löschen?\n\n"
                                    "Das lässt sich nicht rückgängig machen.", ["Endgültig löschen"]) != 0:
            return 0
        try:
            n = ad.endgueltig_loeschen(self.db, liste)
        except (ad.AustauschFehler, OSError) as f:
            self._fehler(f)
            return 0
        self.neu_laden(einlesen=True)
        return n

    def korb_leeren(self):
        if self._frage("Papierkorb leeren", f"Alles endgültig löschen, was länger als {ad.PAPIERKORB_TAGE} Tage im "
                       "Papierkorb liegt?", ["Leeren"]) != 0:
            return 0
        try:
            n = ad.papierkorb_leeren(self.db, w=self.w)
        except (ad.AustauschFehler, OSError) as f:
            self._fehler(f)
            return 0
        self.neu_laden(einlesen=True)
        return n

    # -------------------------------------------------------------- Menüs
    def menue_aktionen(self, g):
        """[(Text, Funktion) oder None (Trenner) oder (Text, [Untermenü])] für die Auswahl g."""
        if not g:
            art, b, _ = self.ansicht
            if art == "bereich" and b not in ad.NUR_LESEN:
                return [("Hochladen …", lambda: self.hochladen_dialog()), ("Neuer Ordner …", lambda: self.ordner_neu()),
                        ("Im Explorer zeigen", self.im_explorer)]
            return []
        e = g[0]
        nur = e.bereich in ad.NUR_LESEN
        a = []
        if len(g) == 1 and e.ordner:
            a.append(("Öffnen", lambda: self.gehe("bereich", e.bereich, e.rel)))
        if not e.ordner:
            a += [("Vorschau", lambda: self.vorschau(e))]
            if not nur:
                a.append(("Bearbeiten (öffnen)", lambda: self.bearbeiten(e)))
                if ad.sperre(self.db, e.datei, self.w) and ad.sperre(self.db, e.datei, self.w).get("eigene"):
                    a.append(("Bearbeitung beenden", self.bearbeitung_beenden))
        if any(x.art == "step" for x in g):
            a.append(("In Kalkulation übernehmen …", lambda: self.in_kalkulation()))
        if any(x.art == "mail" for x in g):
            a.append(("Als Kundenanfrage übernehmen", self.als_anfrage))
        a.append(None)
        a += [("Herunterladen …", lambda: self.herunterladen()), ("Kopieren nach …", lambda: self.kopieren_nach())]
        if not nur:
            a += [("Verschieben nach …", lambda: self.kopieren_nach(verschieben=True))]
            if len(g) == 1:
                a.append(("Umbenennen …", lambda: self.umbenennen()))
            a += [("Aus dem Archiv holen" if all(x.archiv for x in g) else "Archivieren", self.archivieren),
                  ("In den Papierkorb …", self.loeschen)]
        a.append(None)
        fav = ad.favoriten(self.db)
        if len(g) == 1:
            a.append(("Favorit entfernen" if e.datei in fav else "Zu Favoriten", lambda: self._favorit(e)))
        a.append(("Zuweisen an", [(k, lambda _=False, k=k: self.zuweisen(k)) for k in self.kollegen()]
                  + [("Niemand", lambda: self.zuweisen(""))]))
        a.append(("Status", [(s, lambda _=False, s=s: self.status_setzen(s)) for s in ad.STATUS]))
        a.append(("Zuordnung erkennen", self.zuordnung_erkennen))
        a.append(("Im Explorer zeigen", self.im_explorer))
        return a

    def _favorit(self, e):
        ad.favorit_umschalten(self.db, e.datei)
        self._zeigen()

    def _menue(self, pos):
        sender = self.sender()
        idx = sender.indexAt(pos) if hasattr(sender, "indexAt") else QModelIndex()
        if idx.isValid() and not self.liste.selectionModel().isRowSelected(idx.row(), QModelIndex()):
            self.liste.selectRow(idx.row())
        m = QMenu(self)
        self._menue_bauen(m, self.menue_aktionen(self.gewaehlte()))
        if not m.isEmpty():
            m.exec(sender.viewport().mapToGlobal(pos))

    def _menue_bauen(self, m, aktionen):
        for x in aktionen:
            if x is None:
                m.addSeparator()
            elif isinstance(x[1], list):
                self._menue_bauen(m.addMenu(x[0]), x[1])
            else:
                act = QAction(x[0], m)
                act.triggered.connect(lambda _=False, fn=x[1]: fn())
                m.addAction(act)

    def _nav_menue(self, pos):
        it = self.nav.itemAt(pos)
        d = it.data(0, Qt.UserRole) if it else None
        if not d or d[0] != SUCHE:
            return
        m = QMenu(self)
        act = m.addAction("Gespeicherte Suche löschen")
        act.triggered.connect(lambda: (ad.suche_loeschen(self.db, d[1]), self._nav_fuellen()))
        m.exec(self.nav.viewport().mapToGlobal(pos))

    def suche_merken(self, name=None):
        if name is None:
            name, ok = QInputDialog.getText(self, "Suche merken", "Name der Suche (z. B. „Offene STEP von Müller“):")
            if not ok:
                return
        try:
            ad.suche_speichern(self.db, name, self.filter_aus_feldern().als_dict())
        except ad.AustauschFehler as f:
            self._fehler(f)
            return
        self._nav_fuellen()

    # -------------------------------------------------------------- Benachrichtigungen
    def meldungen_dialog(self, werte=None):
        d = QDialog(self)
        d.setWindowTitle("Benachrichtigungen im Austauschordner")
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel("Benachrichtigen bei (nur dieser Arbeitsplatz; gesammelt je Prüfung, eigene Änderungen "
                             "nie):"))
        an = ad.meldungen_an(self.db)
        haken = {}
        for k, t in ad.MELDUNGEN:
            c = QCheckBox(t)
            c.setChecked(an.get(k, False))
            haken[k] = c
            lay.addWidget(c)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        if werte is not None:
            for k, c in haken.items():
                c.setChecked(werte.get(k, c.isChecked()))
            ok = True
        else:
            ok = d.exec() == QDialog.Accepted
        if ok:
            ad.meldungen_setzen(self.db, {k: c.isChecked() for k, c in haken.items()})
        return ok

    def benachrichtigen(self):
        """Neue Ereignisse für mich: Statusleiste/Meldung im Programm und Windows-Infobereich (gesammelt)."""
        try:
            liste = ad.benachrichtigungen(self.db)
        except Exception as e:      # noqa: BLE001 – Meldungen sind Zugabe
            from . import protokoll
            protokoll.warnung(f"Austausch: Benachrichtigungen {e!r}")
            return []
        if not liste:
            return []
        self.meldungen.extend(liste)
        texte = [x["text"] for x in liste]
        self.f.meldung("Austausch: " + texte[0] + (f" (und {len(texte) - 1} weitere)" if len(texte) > 1 else ""))
        try:
            from . import teilen_fenster
            teilen_fenster.windows_meldung(self.f, "Austauschordner", texte)
        except Exception:           # noqa: BLE001
            pass
        self._nav_fuellen()
        return liste

    def takt(self):
        """Alle 60 s: eigene Sperren erneuern, neu einlesen, wenn die Seite sichtbar ist, Benachrichtigungen."""
        ad.eigene_sperren_erneuern(self.db, getattr(self, "eigene_sperren", ()), self.w)
        if self.isVisible():
            self.neu_laden(einlesen=True)
        else:
            self.metas = ad.meta(self.db)
        self.benachrichtigen()

    def _puls(self):
        """Nach einer Änderung bald abgleichen, damit die Kollegen sie sehen (teilen_fenster.puls)."""
        try:
            from . import teilen_fenster
            teilen_fenster.puls(self.f)
        except Exception:           # noqa: BLE001
            pass

    def keyPressEvent(self, ereignis):
        if ereignis.key() == Qt.Key_F5:
            self.neu_laden(einlesen=True)
            return
        if ereignis.key() == Qt.Key_Delete:
            self.loeschen()
            return
        if ereignis.key() == Qt.Key_F2:
            self.umbenennen()
            return
        super().keyPressEvent(ereignis)

    def showEvent(self, ereignis):
        v = self.db.einstellung(ad.L_ANSICHT) or {}
        if isinstance(v, dict) and bool(v.get("kacheln")) != self.k_kacheln.isChecked():
            self.k_kacheln.setChecked(bool(v.get("kacheln")))
        super().showEvent(ereignis)


