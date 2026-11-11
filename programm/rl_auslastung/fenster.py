"""Fenster des Programms Rohrlaser Auslastung: Reiter Aufträge, Auslastung, Soll und Ist, Kennzahlen, Einstellungen; dazu die
Werkstatt-Ansicht (große Schrift, große Knöpfe) für den Platz an der Maschine."""
import datetime
import html
from pathlib import Path

from PySide6.QtCore import QDate, QEvent, QMarginsF, QPointF, QRectF, Qt, QTime, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFontMetrics, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen,
                           QPolygonF)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QCompleter, QDateEdit, QDialog,
                               QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGraphicsScene, QGraphicsView, QGridLayout,
                               QGroupBox, QHBoxLayout,
                               QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget,
                               QTextBrowser, QTimeEdit, QToolTip, QVBoxLayout, QWidget)
from rohrlaser import einlastung, feiertage, stil
from rohrlaser.auslastung_grafik import RISIKO_TEXT, Plantafel, WochenBalken, spalten_daten

from . import NAME, VERSION, aktualisierung_fenster, austausch, hilfe, laufzeit, ort, rechnung
from . import daten as D

FILTER = ("offene Aufträge", "fertige Aufträge", "alle Aufträge")
EINSTELLUNGEN, HILFE = 4, 5                       # Reiter: 0 Aufträge, 1 Auslastung, 2 Soll und Ist, 3 Kennzahlen
ZEITRAUM = ("alle", "letzte 30 Tage", "letzte 90 Tage", "dieses Jahr", "letztes Jahr")
FORM_TEXT = {"hm": "1 h 30 min", "uhr": "1:30 h", "dez": "1,50 h (Dezimalstunden)", "min": "90 min (nur Minuten)"}
OHNE_TEXT = {"min": "Minuten (90 = 90 Minuten)", "h": "Stunden (2 = 2 Stunden)"}
RISIKO_FARBE = {einlastung.UEBER: stil.ROT_FLAECHE, einlastung.KNAPP: stil.GELB_FLAECHE}
# Plantafel (ab 1.6): Balkenfarben, in beiden Designs gleich, weiße Schrift darauf
TAFEL_FARBE = ("Terminrisiko", "Kunde", "Status")
TAFEL_ZOOM = (("Tag", 1), ("1 Woche", 7), ("2 Wochen", 14), ("4 Wochen", 28), ("Alles", None))
T_GRUEN, T_GELB, T_ROT, T_BLAU, T_GRAU = "#2E7D46", "#B26A00", "#B42318", "#3F6FA3", "#6B7684"
T_RISIKO = {einlastung.OK: T_GRUEN, einlastung.KNAPP: T_GELB, einlastung.UEBER: T_ROT, einlastung.OHNE: T_BLAU}
T_RISIKO_TEXT = ((T_GRUEN, "im Termin"), (T_GELB, "knapp"), (T_ROT, "zu spät"), (T_BLAU, "ohne Termin"))
T_STATUS = (("läuft", T_GRUEN), ("gestoppt", T_GELB), ("wartet auf Material", T_GRAU), ("offen", T_BLAU))
T_KUNDEN = ("#3F6FA3", "#B26A00", "#2E7D46", "#8E5A9B", "#2F8C8C", "#9C6B3F", "#B4456B", "#5F6B7A", "#6B8E23",
            "#C0504D")


def _tag(iso):
    try:
        return datetime.date.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return ""


def _arbeitstage(n):
    return f"{n} Arbeitstag" if int(n) == 1 else f"{n} Arbeitstage"


WOCHENTAG = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
WOCHENTAG_LANG = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def _folge_text(m):
    """Schichten einer Maschine für die Liste: „Früh + Spät“ oder im Wochenwechsel „Früh / Spät im Wechsel“."""
    folge = D.schichtfolge(m)
    text = " / ".join(" + ".join(woche) for woche in folge)
    sa = (m.get("schichten_sa") or "").replace(",", " + ")
    return text + (" im Wechsel" if len(folge) > 1 else "") + (f"; Sa {sa}" if sa else "")


def _wtag(d):
    """Datum mit Wochentag: Do 19.11.2026."""
    return f"{('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')[d.weekday()]} {d.strftime('%d.%m.%Y')}" if d else ""


def _zelle(text, rechts=False, daten=None, sortier=None):
    z = _Zelle("" if text is None else str(text))
    z.setFlags(z.flags() & ~Qt.ItemIsEditable)
    if rechts:
        z.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if daten is not None:
        z.setData(Qt.UserRole, daten)
    z.sortier = sortier
    return z


class _Zelle(QTableWidgetItem):
    """Zelle, die nach ihrem Wert sortiert (Laufzeit, Datum) statt nach dem angezeigten Text."""
    sortier = None

    def __lt__(self, other):
        a, b = self.sortier, getattr(other, "sortier", None)
        if a is not None and b is not None:
            return a < b
        return super().__lt__(other)


class LaufzeitFeld(QWidget):
    """Eingabe einer Laufzeit in freier Schreibweise mit Rückmeldung, wie sie verstanden wurde."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.eingabe = QLineEdit()
        self.eingabe.setPlaceholderText(laufzeit.BEISPIELE)
        self.eingabe.setToolTip("Schreibweisen: 1 Stunde 30 Minuten, 1 Std 30 Min, 1 h 30 min, 1h30, 1:30, 90 Minuten, "
                                "90 min, 1,5 h.\nEine ganze Zahl ohne Einheit gilt als "
                                + ("Stunden" if db.einstellung("ohne_einheit") == "h" else "Minuten")
                                + ", eine Kommazahl als Stunden (Einstellungen).")
        self.echo = QLabel("")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self.eingabe)
        lay.addWidget(self.echo)
        self.eingabe.textChanged.connect(self.pruefen)

    def setzen(self, minuten):
        self.eingabe.setText(laufzeit.text(minuten, self.db.einstellung("laufzeit_form")) if minuten else "")

    def minuten(self):
        """Ganze Minuten oder None (leer); laufzeit.Fehler bei unlesbarer Eingabe."""
        return laufzeit.lesen(self.eingabe.text(), self.db.einstellung("ohne_einheit"))

    def pruefen(self, *_):
        try:
            n = self.minuten()
        except laufzeit.Fehler as e:
            self.echo.setText(str(e))
            self.echo.setStyleSheet(f"color: {stil.umsetzen(stil.ROT)};")
            self.echo.setWordWrap(True)
            return False
        self.echo.setText("= " + laufzeit.lang(n) if n is not None else "")
        self.echo.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        return True


class GangTabelle(QWidget):
    """Zeilen eines mehrteiligen Auftrags: Arbeitsgänge nacheinander (Plan A) oder Teile, die gleichzeitig auf
    mehreren Maschinen laufen. art: "gaenge" (alles), "teile" (nur Maschine und Laufzeit, alle gleichzeitig),
    "vorlage" (wie gaenge, Laufzeit darf leer bleiben)."""
    KOPF = ("Arbeitsgang", "Arbeitsplatz", "Laufzeit / Arbeitstage", "gleichzeitig", "Status")

    def __init__(self, db, art="gaenge", parent=None):
        super().__init__(parent)
        self.db, self.art, self.zeilen, self.baut = db, art, [], False
        self.plaetze = [m["name"] for m in db.maschinen(nur_aktive=True)]
        self.tabelle = QTableWidget()
        self.tabelle.setColumnCount(len(self.KOPF))
        self.tabelle.setHorizontalHeaderLabels(self.KOPF if art != "teile" else
                                               ("Teil", "Maschine", "Kalkulierte Laufzeit", "", "Status"))
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setMinimumHeight(150)
        self.tabelle.setColumnHidden(0, art == "teile")
        self.tabelle.setColumnHidden(3, art == "teile")
        self.tabelle.horizontalHeaderItem(2).setToolTip("Laufzeit am Arbeitsplatz in jeder Schreibweise. Bei "
                                                        "Fremdarbeit die Dauer in Arbeitstagen.")
        self.tabelle.horizontalHeaderItem(3).setToolTip("Häkchen: Die Zeile läuft gleichzeitig mit der Zeile davor "
                                                        "statt danach.")
        self.k_neu = QPushButton("Maschine hinzufügen" if art == "teile" else "Arbeitsgang hinzufügen")
        self.k_weg = QPushButton("Entfernen")
        self.k_hoch = QPushButton("Nach oben")
        self.k_runter = QPushButton("Nach unten")
        self.k_neu.clicked.connect(lambda _=False: self.hinzu())
        self.k_weg.clicked.connect(lambda _=False: self.entfernen())
        self.k_hoch.clicked.connect(lambda _=False: self.schieben(-1))
        self.k_runter.clicked.connect(lambda _=False: self.schieben(1))
        self.vorlage = QComboBox()
        self.vorlage.addItem("Vorlage übernehmen …")
        for v in db.vorlagen():
            self.vorlage.addItem(v["name"], v["gaenge"])
        self.vorlage.activated.connect(self._vorlage)
        self.vorlage.setVisible(art == "gaenge" and self.vorlage.count() > 1)
        unten = QHBoxLayout()
        for k in (self.k_neu, self.k_weg, self.k_hoch, self.k_runter):
            unten.addWidget(k)
        unten.addStretch(1)
        unten.addWidget(self.vorlage)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.tabelle, 1)
        lay.addLayout(unten)

    def _zeit(self, g):
        if (g.get("platz") or "") == D.FREMD:
            return _arbeitstage(g["tage"]) if g.get("tage") else ""
        return laufzeit.text(g["kalk_min"], self.db.einstellung("laufzeit_form")) if g.get("kalk_min") else ""

    def setzen(self, gaenge):
        """Zeilen aus der Datenbank oder einer Vorlage zeigen."""
        self.zeilen = [dict(id=g.get("id"), name=g.get("name") or "", platz=g.get("platz") or "", zeit=self._zeit(g),
                            gleichzeitig=bool(g.get("gleichzeitig")), status=g.get("status") or "") for g in gaenge]
        self._zeigen()

    def _holen(self):
        """Was in den Zellen steht, in self.zeilen übernehmen."""
        for r, z in enumerate(self.zeilen):
            if r >= self.tabelle.rowCount() or self.tabelle.item(r, 0) is None:
                continue
            z["name"] = self.tabelle.item(r, 0).text().strip()
            wahl = self.tabelle.cellWidget(r, 1)
            z["platz"] = wahl.currentData() if wahl.currentData() is not None else wahl.currentText()
            z["zeit"] = self.tabelle.item(r, 2).text().strip()
            z["gleichzeitig"] = self.tabelle.item(r, 3).checkState() == Qt.Checked

    def _zeigen(self, zeile=None):
        self.baut = True
        for r in range(self.tabelle.rowCount()):  # alte Auswahlfelder sofort ausblenden, nicht erst beim Aufräumen
            if self.tabelle.cellWidget(r, 1) is not None:
                self.tabelle.cellWidget(r, 1).hide()
        self.tabelle.setRowCount(len(self.zeilen))
        self.tabelle.setColumnHidden(4, self.art == "vorlage" or not any(z["status"] for z in self.zeilen))
        for r, z in enumerate(self.zeilen):
            fertig = z["status"] == D.FERTIG
            name = QTableWidgetItem(z["name"])
            wahl = QComboBox()
            for platz in self.plaetze + ([z["platz"]] if z["platz"] and z["platz"] not in self.plaetze else []):
                wahl.addItem(platz, platz)
            if self.art != "teile":
                wahl.addItem("Fremdarbeit (außer Haus)", D.FREMD)
            wahl.setCurrentIndex(max(0, wahl.findData(z["platz"])))
            wahl.setEnabled(not fertig)
            zeit = QTableWidgetItem(z["zeit"])
            zeit.setToolTip("Laufzeit in jeder Schreibweise (1 h 30 min, 1:30, 90 min). Bei Fremdarbeit die Dauer in "
                            "Arbeitstagen, z. B. 5.")
            gleich = QTableWidgetItem("")
            gleich.setFlags((gleich.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            gleich.setCheckState(Qt.Checked if z["gleichzeitig"] and r else Qt.Unchecked)
            if r == 0:
                gleich.setFlags(gleich.flags() & ~Qt.ItemIsEnabled)
            for c, item in enumerate((name, None, zeit, gleich, _zelle(z["status"]))):
                if item is not None:
                    if fertig and c in (0, 2):
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.tabelle.setItem(r, c, item)
            self.tabelle.setCellWidget(r, 1, wahl)
        self.tabelle.resizeColumnsToContents()
        self.tabelle.setColumnWidth(0, max(150, self.tabelle.columnWidth(0)))
        self.tabelle.setColumnWidth(2, max(170, self.tabelle.columnWidth(2)))
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        if zeile is not None and 0 <= zeile < len(self.zeilen):
            self.tabelle.selectRow(zeile)
        self.baut = False

    def hinzu(self, name="", platz=None, zeit="", gleichzeitig=None):
        self._holen()
        teile = self.art == "teile"
        if platz is None:
            benutzt = {z["platz"] for z in self.zeilen}
            platz = next((p for p in self.plaetze if p not in benutzt), self.plaetze[0] if self.plaetze else "")
        self.zeilen.append(dict(id=None, name=name, platz=platz, zeit=zeit, status="",
                                gleichzeitig=(teile if gleichzeitig is None else gleichzeitig) and bool(self.zeilen)))
        self._zeigen(len(self.zeilen) - 1)

    def entfernen(self, zeile=None):
        self._holen()
        r = self.tabelle.currentRow() if zeile is None else zeile
        if 0 <= r < len(self.zeilen):
            if self.zeilen[r]["status"] == D.FERTIG:
                return False
            del self.zeilen[r]
            self._zeigen(min(r, len(self.zeilen) - 1))
            return True
        return False

    def schieben(self, richtung, zeile=None):
        self._holen()
        r = self.tabelle.currentRow() if zeile is None else zeile
        n = r + richtung
        if 0 <= r < len(self.zeilen) and 0 <= n < len(self.zeilen):
            self.zeilen[r], self.zeilen[n] = self.zeilen[n], self.zeilen[r]
            self._zeigen(n)

    def _vorlage(self, i):
        gaenge = self.vorlage.itemData(i)
        self.vorlage.setCurrentIndex(0)
        if gaenge:
            self._holen()
            if not any(z["status"] == D.FERTIG for z in self.zeilen):
                self.setzen(gaenge)

    def werte(self):
        """[dict(id, name, platz, kalk_min, tage, gleichzeitig)]; D.Fehler bei unlesbarer Zeile."""
        self._holen()
        out = []
        for nr, z in enumerate(self.zeilen, start=1):
            g = dict(id=z["id"], name=z["name"], platz=z["platz"], kalk_min=0, tage=0,
                     gleichzeitig=(z["gleichzeitig"] or self.art == "teile") and nr > 1)
            if self.art == "teile" and not g["name"]:
                g["name"] = f"Teil {nr} ({z['platz']})"
            if z["platz"] == D.FREMD:
                ziffern = "".join(c if c.isdigit() else " " for c in z["zeit"]).split()
                g["tage"] = int(ziffern[0]) if ziffern else 0
                if not g["tage"] and self.art != "vorlage":
                    raise D.Fehler(f"Zeile {nr}: Bei Fremdarbeit bitte die Dauer in Arbeitstagen eingeben, z. B. 5.")
            else:
                try:
                    g["kalk_min"] = laufzeit.lesen(z["zeit"], self.db.einstellung("ohne_einheit")) or 0
                except laufzeit.Fehler as e:
                    raise D.Fehler(f"Zeile {nr}: {e}") from None
            out.append(g)
        return out


class LieferTabelle(QWidget):
    """A5 Teillieferungen: Zeilen mit Termin und Menge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zeilen = []
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(4)
        self.k_hinzu = QPushButton("+ Teillieferung")
        self.k_hinzu.setToolTip("Noch einen Liefertermin mit Menge anlegen.")
        self.k_hinzu.clicked.connect(lambda: self.hinzu())
        unten = QHBoxLayout()
        unten.addWidget(self.k_hinzu)
        unten.addStretch(1)
        self.lay.addLayout(unten)

    def hinzu(self, termin=None, menge=""):
        tag = QDateEdit()
        tag.setCalendarPopup(True)
        tag.setDisplayFormat("dd.MM.yyyy")
        if termin is None:
            termin = (self.zeilen[-1][0].date().addDays(14) if self.zeilen else QDate.currentDate().addDays(14))
        elif not isinstance(termin, QDate):
            t = datetime.date.fromisoformat(str(termin))
            termin = QDate(t.year, t.month, t.day)
        tag.setDate(termin)
        feld = QLineEdit(D.mm_text(menge) if menge not in ("", None) else "")
        feld.setPlaceholderText("Menge")
        feld.setMaximumWidth(110)
        weg = QPushButton("✕")
        weg.setFixedWidth(34)
        weg.setToolTip("Diese Teillieferung entfernen")
        box = QWidget()
        z = QHBoxLayout(box)
        z.setContentsMargins(0, 0, 0, 0)
        z.addWidget(tag, 1)
        z.addWidget(feld)
        z.addWidget(QLabel("Stück"))
        z.addWidget(weg)
        eintrag = (tag, feld, box)
        weg.clicked.connect(lambda: self.entfernen(eintrag))
        self.zeilen.append(eintrag)
        self.lay.insertWidget(len(self.zeilen) - 1, box)
        return eintrag

    def entfernen(self, eintrag):
        if eintrag in self.zeilen:
            self.zeilen.remove(eintrag)
            eintrag[2].setParent(None)
            eintrag[2].deleteLater()

    def setzen(self, liste):
        for e in list(self.zeilen):
            self.entfernen(e)
        for x in liste or ():
            self.hinzu(x["termin"], x["menge"])

    def werte(self):
        return [dict(termin=datetime.date(t.date().year(), t.date().month(), t.date().day()), menge=f.text())
                for t, f, _b in self.zeilen]


class AuftragDialog(QDialog):
    """Auftrag anlegen oder ändern."""

    def __init__(self, db, auftrag=None, parent=None):
        super().__init__(parent)
        self.db, self.auftrag = db, dict(auftrag or {})
        self.setWindowTitle("Auftrag ändern" if self.auftrag.get("id") else "Neuer Auftrag")
        self.nummer = QLineEdit(self.auftrag.get("nummer") or "")
        self.kunde = QLineEdit(self.auftrag.get("kunde") or "")
        self.maschine = QComboBox()
        namen = [m["name"] for m in db.maschinen(nur_aktive=True)]
        if self.auftrag.get("maschine") and self.auftrag["maschine"] not in namen:
            namen.append(self.auftrag["maschine"])
        self.maschine.addItems(namen)
        if self.auftrag.get("maschine"):
            self.maschine.setCurrentText(self.auftrag["maschine"])
        self.kalk = LaufzeitFeld(db)
        self.kalk.setzen(self.auftrag.get("kalk_min"))
        self.mit_termin = QCheckBox("Liefertermin")
        self.termin = QDateEdit()
        self.termin.setCalendarPopup(True)
        self.termin.setDisplayFormat("dd.MM.yyyy")
        try:
            t = datetime.date.fromisoformat(self.auftrag.get("liefertermin") or "")
            self.termin.setDate(QDate(t.year, t.month, t.day))
            self.mit_termin.setChecked(True)
        except ValueError:
            self.termin.setDate(QDate.currentDate().addDays(14))
            self.mit_termin.setChecked(not self.auftrag.get("id"))
        self.mit_termin.toggled.connect(self.termin.setEnabled)
        self.termin.setEnabled(self.mit_termin.isChecked())
        zeile = QHBoxLayout()
        zeile.addWidget(self.mit_termin)
        zeile.addWidget(self.termin, 1)
        self.bemerkung = QLineEdit(self.auftrag.get("bemerkung") or "")
        # E8: Material da ab – vorher wird der Auftrag nicht eingelastet
        self.mit_material = QCheckBox("Material da ab")
        self.mit_material.setToolTip("Für Aufträge, deren Material noch nicht da ist: Vor diesem Tag plant das "
                                     "Programm den Auftrag nicht ein. Ohne Häkchen ist das Material da.")
        self.material = QDateEdit()
        self.material.setCalendarPopup(True)
        self.material.setDisplayFormat("dd.MM.yyyy")
        try:
            t = datetime.date.fromisoformat(self.auftrag.get("material_ab") or "")
            self.material.setDate(QDate(t.year, t.month, t.day))
            self.mit_material.setChecked(True)
        except ValueError:
            self.material.setDate(QDate.currentDate().addDays(7))
        self.mit_material.toggled.connect(self.material.setEnabled)
        self.material.setEnabled(self.mit_material.isChecked())
        zeile_m = QHBoxLayout()
        zeile_m.addWidget(self.mit_material)
        zeile_m.addWidget(self.material, 1)
        self.zusatz = {}
        # Mehrteilig: Arbeitsgänge nacheinander (Schalter in den Einstellungen) oder Teile auf mehreren Maschinen
        self.mit_gaengen = db.mit_gaengen() or any(
            not g["gleichzeitig"] and g["pos"] for g in self.auftrag.get("gaenge") or ())
        self.mehr = QCheckBox("Mehrere Arbeitsgänge (nacheinander, auch Fremdarbeit)" if self.mit_gaengen else
                              "Auftrag auf mehrere Maschinen aufteilen")
        self.mehr.setToolTip("Für Aufträge, die nicht auf einer Maschine in einem Stück laufen: jede Zeile hat ihren "
                             "eigenen Arbeitsplatz und ihre eigene Laufzeit und wird einzeln gestartet und fertig "
                             "gemeldet.")
        self.gaenge = GangTabelle(db, "gaenge" if self.mit_gaengen else "teile")
        self.gaenge.setzen(self.auftrag.get("gaenge") or ())
        self.mehr.setChecked(bool(self.auftrag.get("gaenge")))
        self.mehr.toggled.connect(self._mehr_geschaltet)
        # Paket A: Material und Rüstzeit (A1), Maße des Rohrs für die Eignung (A3), Teillieferungen (A5)
        self.werkstoff = QLineEdit(self.auftrag.get("material") or "")
        self.werkstoff.setPlaceholderText("z. B. 60x60x3 S235")
        self.werkstoff.setToolTip("Läuft auf der Maschine direkt davor das gleiche Material, rechnet das Programm "
                                  "keine Rüstzeit. Gleich heißt: gleich geschrieben (Groß und Klein egal).")
        vorschlag = QCompleter(db.materialien(), self)
        vorschlag.setCaseSensitivity(Qt.CaseInsensitive)
        vorschlag.setFilterMode(Qt.MatchContains)
        self.werkstoff.setCompleter(vorschlag)
        self.ruest = QLineEdit("" if self.auftrag.get("ruest_min") is None else str(self.auftrag["ruest_min"]))
        self.ruest.setMaximumWidth(90)
        self.ruest.setToolTip("Rüstzeit nur für diesen Auftrag in Minuten. Leer = die Rüstzeit der Maschine "
                              "(Einstellungen → Maschinen). 0 = dieser Auftrag braucht kein Rüsten.")
        self.ruest_text = QLabel("")
        zeile_r = QHBoxLayout()
        zeile_r.addWidget(self.ruest)
        zeile_r.addWidget(self.ruest_text, 1)
        self.durchmesser = QLineEdit(D.mm_text(self.auftrag["durchmesser"]) if self.auftrag.get("durchmesser") else "")
        self.laenge = QLineEdit(D.mm_text(self.auftrag["laenge"]) if self.auftrag.get("laenge") else "")
        for feld, tipp in ((self.durchmesser, "Durchmesser oder größtes Außenmaß des Rohrs in mm. Leer = unbekannt."),
                           (self.laenge, "Länge des Rohrs (der Stange) in mm. Leer = unbekannt.")):
            feld.setMaximumWidth(90)
            feld.setToolTip(tipp + " Das Programm legt den Auftrag nie auf eine Maschine, auf die das Rohr nicht "
                                   "passt (Einstellungen → Maschinen: größter Durchmesser, größte Rohrlänge).")
        zeile_d = QHBoxLayout()
        zeile_d.addWidget(self.durchmesser)
        zeile_d.addWidget(QLabel("mm Durchmesser"))
        zeile_d.addSpacing(12)
        zeile_d.addWidget(self.laenge)
        zeile_d.addWidget(QLabel("mm Länge"))
        zeile_d.addStretch(1)
        self.passt_text = QLabel("")
        self.passt_text.setWordWrap(True)
        self.passt_text.setStyleSheet(f"color: {stil.umsetzen(stil.ROT)};")
        self.passt_text.hide()
        self.mit_teilen = QCheckBox("Teillieferungen (mehrere Liefertermine mit Mengen)")
        self.mit_teilen.setToolTip("Für Abrufaufträge: Die Laufzeit teilt sich nach den Mengen, jede Lieferung wird "
                                   "mit ihrem eigenen Termin eingelastet. Der Liefertermin des Auftrags ist dann "
                                   "der letzte.")
        self.teile = LieferTabelle()
        self.teile.setzen(self.auftrag.get("lieferungen") or ())
        self.mit_teilen.setChecked(bool(self.auftrag.get("lieferungen")))
        self.mit_teilen.toggled.connect(self._teile_geschaltet)
        for feld in (self.durchmesser, self.laenge):
            feld.textChanged.connect(self._eignung_zeigen)
        self.maschine.currentTextChanged.connect(self._eignung_zeigen)
        form = QFormLayout()
        self.form = form
        form.addRow("Auftragsnummer", self.nummer)
        form.addRow("Kunde", self.kunde)
        form.addRow("Maschine", self.maschine)
        form.addRow("Kalkulierte Laufzeit", self.kalk)
        form.addRow("Rüstzeit", zeile_r)
        self.zeile_r = zeile_r
        form.addRow("", self.mehr)
        form.addRow("", self.gaenge)
        form.addRow("Material (für Rüsten)", self.werkstoff)
        form.addRow("Rohr", zeile_d)
        form.addRow("", self.passt_text)
        form.addRow("", zeile)
        form.addRow("", self.mit_teilen)
        form.addRow("", self.teile)
        form.addRow("", zeile_m)
        form.addRow("Bemerkung", self.bemerkung)
        for f in db.zusatzfelder():
            self.zusatz[f["name"]] = QLineEdit((self.auftrag.get("zusatz") or {}).get(f["name"], ""))
            form.addRow(f["name"], self.zusatz[f["name"]])
        self.fehler = QLabel("")
        self.fehler.setWordWrap(True)
        self.fehler.setStyleSheet(f"color: {stil.umsetzen(stil.ROT)};")
        knoepfe = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Save).setText("Speichern")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.speichern)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.fehler)
        lay.addWidget(knoepfe)
        self.setMinimumWidth(460)
        self._mehr_geschaltet(self.mehr.isChecked())
        self._teile_geschaltet(self.mit_teilen.isChecked())
        self._eignung_zeigen()

    def _teile_geschaltet(self, an):
        """Mit Teillieferungen ergibt sich der Liefertermin aus der letzten Lieferung."""
        self.form.setRowVisible(self.teile, an)
        self.mit_termin.setEnabled(not an)
        self.termin.setEnabled(not an and self.mit_termin.isChecked())
        if an and not self.teile.zeilen:
            self.teile.hinzu(self.termin.date() if self.mit_termin.isChecked() else None)
            self.teile.hinzu()
        self.adjustSize()

    def _eignung_zeigen(self, *_):
        """Rüstzeit der gewählten Maschine als Hinweis; rote Zeile, wenn das Rohr nicht auf die Maschine passt."""
        m = next((x for x in self.db.maschinen() if x["name"] == self.maschine.currentText()), None)
        self.ruest_text.setText(f"min (leer = wie Maschine: {int(m['ruest_min'] or 0)} min)" if m else "min")
        self.ruest.setPlaceholderText(str(int(m["ruest_min"] or 0)) if m else "")
        grund = ""
        if not self.mehr.isChecked():
            try:
                grund = D.passt_nicht(m, D._zahl(self.durchmesser.text(), "Durchmesser"),
                                      D._zahl(self.laenge.text(), "Rohrlänge"))
            except D.Fehler:
                grund = ""
        self.passt_text.setText(grund)
        self.form.setRowVisible(self.passt_text, bool(grund))

    def _mehr_geschaltet(self, an):
        """Einteilig: Maschine und Laufzeit als Felder. Mehrteilig: stattdessen die Tabelle der Zeilen."""
        for feld in (self.maschine, self.kalk, self.zeile_r, self.mit_teilen):
            self.form.setRowVisible(feld, not an)
        self.form.setRowVisible(self.gaenge, an)
        self.form.setRowVisible(self.teile, not an and self.mit_teilen.isChecked())
        if hasattr(self, "passt_text"):
            self._eignung_zeigen()
        if an and not self.gaenge.zeilen:         # die bisherige Maschine und Laufzeit als erste Zeile übernehmen
            self.gaenge.hinzu(platz=self.maschine.currentText(), zeit=self.kalk.eingabe.text(),
                              name="" if not self.mit_gaengen else self.maschine.currentText())
            if not self.mit_gaengen:
                self.gaenge.hinzu()
        self.setMinimumWidth(760 if an else 460)
        self.adjustSize()

    def werte(self):
        d, m = self.termin.date(), self.material.date()
        mehr = self.mehr.isChecked()
        return dict(material_ab=datetime.date(m.year(), m.month(), m.day()) if self.mit_material.isChecked() else None,
                    id=self.auftrag.get("id"), nummer=self.nummer.text(), kunde=self.kunde.text(),
                    maschine=self.maschine.currentText(), kalk_min=0 if mehr else self.kalk.minuten() or 0,
                    gaenge=self.gaenge.werte() if mehr else [],
                    liefertermin=datetime.date(d.year(), d.month(), d.day()) if self.mit_termin.isChecked() else None,
                    bemerkung=self.bemerkung.text(), zusatz={n: e.text() for n, e in self.zusatz.items()},
                    material=self.werkstoff.text(), ruest_min=None if mehr else self.ruest.text(),
                    durchmesser=self.durchmesser.text(), laenge=self.laenge.text(),
                    lieferungen=self.teile.werte() if self.mit_teilen.isChecked() and not mehr else [])

    def speichern(self):
        try:
            self.auftrag["id"] = self.db.auftrag_speichern(self.werte())
        except (D.Fehler, laufzeit.Fehler) as e:
            self.fehler.setText(str(e))
            return False
        self.accept()
        return True


class FertigDialog(QDialog):
    """Fertigmeldung: tatsächliche Laufzeit, Fertig-Datum und Uhrzeit. Ohne Auftrag (oder mit suchen=True) steht oben
    die Suche nach der Auftragsnummer: tippen, Enter übernimmt den Treffer, Enter meldet fertig; „Fertig melden und
    nächster“ lässt den Dialog für den nächsten Auftrag offen. self.gemeldet = Nummern der gemeldeten Aufträge."""

    def __init__(self, db, auftrag=None, parent=None, jetzt=None, gang=None, suchen=None):
        super().__init__(parent)
        self.db, self.auftrag, self.gang, self.jetzt = db, None, None, jetzt
        self.mit_suche = auftrag is None if suchen is None else bool(suchen)
        self.gemeldet, self.fremd, self.treffer_liste = [], False, []
        self.form_ = db.einstellung("laufzeit_form")
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Auftragsnummer oder Kunde tippen, Enter übernimmt")
        self.suche.setClearButtonEnabled(True)
        self.treffer = QListWidget()
        self.treffer.setMaximumHeight(132)
        self.kopf = QLabel("")
        self.kopf.setTextFormat(Qt.RichText)
        self.zeile = QComboBox()                      # mehrteilig: welche Zeile, die an der Reihe ist
        self.platz, self.kalk, self.gestoppt = QLabel(""), QLabel(""), QLabel("")
        self.ist = LaufzeitFeld(db)
        self.am = QDateEdit(QDate.currentDate())
        self.am.setCalendarPopup(True)
        self.am.setDisplayFormat("dd.MM.yyyy")
        self.um = QTimeEdit(QTime.currentTime() if jetzt is None else QTime(jetzt.hour, jetzt.minute))
        self.um.setDisplayFormat("HH:mm")
        self.um.setToolTip("Uhrzeit, zu der der Auftrag fertig war. Vorbelegt mit jetzt.")
        wann = QHBoxLayout()
        wann.addWidget(self.am, 1)
        wann.addWidget(QLabel("um"))
        wann.addWidget(self.um)
        wann.addWidget(QLabel("Uhr"))
        form = QFormLayout()
        self.form = form
        form.addRow("Zeile", self.zeile)
        form.addRow("Arbeitsplatz", self.platz)
        form.addRow("Kalkulierte Laufzeit", self.kalk)
        form.addRow("Gestoppt mit Start/Stopp", self.gestoppt)
        form.addRow("Tatsächliche Laufzeit", self.ist)
        form.addRow("Fertig am", wann)
        self.fehler = QLabel("")
        self.fehler.setWordWrap(True)
        self.fehler.setStyleSheet(f"color: {stil.umsetzen(stil.ROT)};")
        self.erfolg = QLabel("")
        self.erfolg.setWordWrap(True)
        self.erfolg.setStyleSheet(f"color: {stil.umsetzen(stil.GRUEN)};")
        knoepfe = QDialogButtonBox()
        self.k_ok = knoepfe.addButton("Fertig melden", QDialogButtonBox.AcceptRole)
        self.k_weiter = knoepfe.addButton("Fertig melden und nächster", QDialogButtonBox.ActionRole)
        self.k_weiter.setToolTip("Meldet fertig und lässt das Fenster offen, um gleich den nächsten Auftrag zu suchen.")
        self.k_weiter.setAutoDefault(False)
        zu = knoepfe.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        zu.setAutoDefault(False)
        self.k_ok.clicked.connect(lambda _=False: self.speichern())
        self.k_weiter.clicked.connect(lambda _=False: self.speichern(weiter=True))
        knoepfe.rejected.connect(self.schliessen)
        lay = QVBoxLayout(self)
        lay.addWidget(self.suche)
        lay.addWidget(self.treffer)
        lay.addWidget(self.kopf)
        lay.addLayout(form)
        lay.addWidget(self.fehler)
        lay.addWidget(self.erfolg)
        lay.addWidget(knoepfe)
        self.setMinimumWidth(460)
        for w in (self.suche, self.treffer, self.k_weiter):
            w.setVisible(self.mit_suche)
        self.suche.textChanged.connect(self.suchen)
        self.suche.returnPressed.connect(self.uebernehmen)
        self.suche.installEventFilter(self)
        self.treffer.itemClicked.connect(lambda _i: self.uebernehmen())
        self.treffer.itemActivated.connect(lambda _i: self.uebernehmen())
        self.ist.eingabe.returnPressed.connect(lambda: self.speichern(weiter=False))
        self.zeile.currentIndexChanged.connect(self._zeile_gewaehlt)
        self.auftrag_setzen(auftrag, gang)
        if self.mit_suche:
            self.suche.setText(auftrag["nummer"] if auftrag else "")
            self.suchen()
            (self.ist.eingabe if auftrag else self.suche).setFocus()

    # ---- Suche
    def offene(self):
        return self.db.auftraege((D.OFFEN, D.LAEUFT))

    def suchen(self, *_):
        """Offene Aufträge, deren Nummer oder Kunde den Text enthält; die Nummer vorn zählt zuerst."""
        text = self.suche.text().strip().casefold()
        liste = []
        for a in self.offene():
            nummer, kunde = a["nummer"].casefold(), (a["kunde"] or "").casefold()
            if not text or text in nummer or text in kunde:
                rang = 0 if nummer == text else 1 if nummer.startswith(text) else 2 if text in nummer else 3
                liste.append((rang, a["nummer"], a))
        liste.sort(key=lambda x: x[:2])
        self.treffer_liste = [a for _r, _n, a in liste]
        self.treffer.clear()
        for a in self.treffer_liste[:50]:
            self.treffer.addItem(" · ".join(t for t in (
                a["nummer"], a["kunde"], a["maschine"], "läuft" if a["status"] == D.LAEUFT else "") if t))
        if self.treffer_liste:
            self.treffer.setCurrentRow(0)
        return self.treffer_liste

    def uebernehmen(self, nummer=None):
        """Den gewählten Treffer (oder die Auftragsnummer) in die Meldung übernehmen."""
        if nummer is not None:
            self.suche.setText(nummer)
        r = self.treffer.currentRow()
        if not self.treffer_liste or r < 0:
            self.fehler.setText(f"Kein offener Auftrag passt zu „{self.suche.text().strip()}“." if self.suche.text().strip()
                                else "Bitte eine Auftragsnummer eingeben.")
            return False
        self.auftrag_setzen(self.db.auftrag(self.treffer_liste[r]["id"]))
        self.ist.eingabe.setFocus()
        self.ist.eingabe.selectAll()
        return True

    def eventFilter(self, wer, e):
        if wer is self.suche and e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Down, Qt.Key_Up):
            r = self.treffer.currentRow() + (1 if e.key() == Qt.Key_Down else -1)
            if 0 <= r < self.treffer.count():
                self.treffer.setCurrentRow(r)
            return True
        return super().eventFilter(wer, e)

    # ---- Auftrag und Zeile
    def auftrag_setzen(self, auftrag, gang=None):
        self.auftrag = auftrag
        self.fehler.setText("")
        self.zeile.blockSignals(True)
        self.zeile.clear()
        bereit = self.db.bereit(auftrag["gaenge"]) if auftrag and auftrag["gaenge"] else []
        if gang is not None and not any(g["id"] == gang["id"] for g in bereit):
            bereit = [gang] + bereit
        for g in bereit:
            self.zeile.addItem(f"{g['name']} ({g['platz'] or 'Fremdarbeit'})", g["id"])
        if gang is not None:
            self.zeile.setCurrentIndex(max(0, self.zeile.findData(gang["id"])))
        self.zeile.blockSignals(False)
        self.bereit = bereit
        if auftrag is None:
            self.setWindowTitle("Auftrag fertig melden")
            self.kopf.setText("Noch kein Auftrag gewählt.")
        else:
            self.setWindowTitle(f"Auftrag {auftrag['nummer']} fertig melden")
            self.kopf.setText(f"<b>{auftrag['nummer']}</b>" + "".join(
                f" · {t}" for t in (auftrag["kunde"], auftrag["maschine"]) if t))
        self.kopf.setVisible(self.mit_suche)
        self._zeile_gewaehlt()

    def _zeile_gewaehlt(self, *_):
        a = self.auftrag
        self.gang = next((g for g in getattr(self, "bereit", ()) if g["id"] == self.zeile.currentData()), None)
        gang = self.gang
        self.fremd = gang is not None and gang["platz"] == D.FREMD
        teil = gang if gang is not None else a            # die Zeile, die gemeldet wird
        gelaufen = 0 if self.fremd or teil is None else self.db.gelaufen(teil, self.jetzt)
        if gang is not None:
            self.setWindowTitle(f"Auftrag {a['nummer']}: „{gang['name']}“ fertig melden")
            self.platz.setText(gang["platz"] or f"Fremdarbeit ({gang['tage']} Arbeitstage geplant)")
        self.kalk.setText(laufzeit.text(teil["kalk_min"], self.form_) if teil else "")
        self.gestoppt.setText(laufzeit.text(gelaufen, self.form_) if gelaufen else "")
        self.ist.setzen((teil.get("ist_min") or gelaufen or None) if teil else None)
        da = a is not None and not (a["gaenge"] and gang is None)
        self.form.setRowVisible(self.zeile, self.zeile.count() > 1)
        self.form.setRowVisible(self.platz, gang is not None)
        self.form.setRowVisible(self.kalk, da and not self.fremd)
        self.form.setRowVisible(self.gestoppt, da and bool(gelaufen))
        self.form.setRowVisible(self.ist, not self.fremd)
        for w in (self.ist, self.am, self.um, self.k_ok, self.k_weiter):
            w.setEnabled(da)
        if a is not None and a["gaenge"] and gang is None:
            self.fehler.setText("Bei diesem Auftrag ist gerade keine Zeile an der Reihe.")

    # ---- Melden
    def speichern(self, weiter=False):
        if self.auftrag is None or not self.k_ok.isEnabled():
            if self.mit_suche:
                self.uebernehmen()
            return False
        try:
            d, u = self.am.date(), self.um.time()
            minuten = 0 if self.fremd else self.ist.minuten() or 0
            if not self.fremd and minuten <= 0:
                raise D.Fehler("Bitte eine tatsächliche Laufzeit über 0 eingeben.")
            teil = self.gang if self.gang is not None else self.auftrag
            if teil["start_am"] and not self.fremd:   # die Uhr läuft noch: anhalten, der Auftrag ist ja fertig
                self.db.stoppen(self.auftrag["id"], gang_id=self.gang["id"] if self.gang else None, grund="")
            self.db.fertig_melden(self.auftrag["id"], minuten, datetime.date(d.year(), d.month(), d.day()),
                                  gang_id=self.gang["id"] if self.gang else None,
                                  fertig_um=f"{u.hour():02d}:{u.minute():02d}")
        except (D.Fehler, laufzeit.Fehler) as e:
            self.fehler.setText(str(e))
            return False
        self.gemeldet.append(self.auftrag["nummer"])
        if weiter and self.mit_suche:
            self.erfolg.setText(f"Fertig gemeldet: {', '.join(self.gemeldet)}")
            self.auftrag_setzen(None)
            self.suche.clear()
            self.suchen()
            self.um.setTime(QTime.currentTime() if self.jetzt is None else self.um.time())
            self.suche.setFocus()
            return True
        self.accept()
        return True

    def schliessen(self):
        """Abbrechen: was mit „und nächster“ schon gemeldet ist, bleibt gemeldet."""
        self.accept() if self.gemeldet else self.reject()


class MonatsBalken(QWidget):
    """Kennzahlen (E7): je Monat ein Balken Termintreue in Prozent, darunter die Abweichung der Kalkulation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.monate = []
        self.setMinimumHeight(190)

    def setzen(self, monate):
        self.monate = list(monate)[-12:]
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        text, grau, linie = stil.farbe(stil.TEXT), stil.farbe(stil.TEXT_GRAU), stil.farbe(stil.LINIE)
        links, oben, unten = 44, 22, 40
        h = self.height() - oben - unten
        p.setPen(grau)
        if not self.monate:
            p.drawText(self.rect(), Qt.AlignCenter, "Noch keine fertig gemeldeten Aufträge in diesem Zeitraum.")
            p.end()
            return
        for wert in (0, 50, 100):
            y = oben + h - h * wert / 100
            p.setPen(QPen(linie, 1))
            p.drawLine(QPointF(links, y), QPointF(self.width() - 6, y))
            p.setPen(grau)
            p.drawText(QRectF(0, y - 9, links - 6, 18), Qt.AlignRight | Qt.AlignVCenter, f"{wert} %")
        breite = (self.width() - links - 6) / len(self.monate)
        for i, m in enumerate(self.monate):
            x = links + i * breite
            b = min(64.0, breite * 0.6)
            if m["treue"] is not None:
                farbe = stil.GRUEN if m["treue"] >= 90 else stil.ORANGE if m["treue"] >= 75 else stil.ROT
                hoch = max(2.0, h * m["treue"] / 100)
                p.setPen(Qt.NoPen)
                p.setBrush(stil.farbe(farbe))
                p.drawRoundedRect(QRectF(x + (breite - b) / 2, oben + h - hoch, b, hoch), 3, 3)
                p.setPen(text)
                p.drawText(QRectF(x, oben + h - hoch - 18, breite, 16), Qt.AlignCenter, f"{m['treue']:.0f} %")
            p.setPen(text)
            p.drawText(QRectF(x, oben + h + 4, breite, 16), Qt.AlignCenter, f"{m['monat'][5:]}.{m['monat'][:4]}")
            p.setPen(grau)
            d = m["diff_prozent"]
            p.drawText(QRectF(x, oben + h + 20, breite, 16), Qt.AlignCenter,
                       "" if d is None else f"Kalk. {d:+.0f} %")
        p.end()


class StoppDialog(QDialog):
    """Grund bei Stopp (E6): je Grund ein Knopf, ein Klick genügt. grund: None = abgebrochen (die Uhr läuft weiter),
    "" = ohne Grund gestoppt."""

    def __init__(self, db, titel, parent=None, gross=False):
        super().__init__(parent)
        self.grund = None
        self.setWindowTitle(titel)
        hoch = 76 if gross else 40
        if gross:
            self.setStyleSheet("QLabel, QPushButton { font-size: 16pt; }")
        frage = QLabel("Warum wird gestoppt?")
        gitter = QGridLayout()
        self.knoepfe = []
        for i, g in enumerate(db.stoppgruende()):
            k = QPushButton(g)
            k.setMinimumHeight(hoch)
            k.setMinimumWidth(260 if gross else 190)
            k.clicked.connect(lambda _=False, g=g: self.waehlen(g))
            gitter.addWidget(k, i // 2, i % 2)
            self.knoepfe.append(k)
        self.k_ohne = QPushButton("Ohne Grund stoppen")
        self.k_weiter = QPushButton("Abbrechen (Uhr läuft weiter)")
        self.k_ohne.clicked.connect(lambda _=False: self.waehlen(""))
        self.k_weiter.clicked.connect(self.reject)
        unten = QHBoxLayout()
        for k in (self.k_ohne, self.k_weiter):
            k.setMinimumHeight(hoch)
            unten.addWidget(k)
        lay = QVBoxLayout(self)
        lay.addWidget(frage)
        lay.addLayout(gitter)
        lay.addSpacing(8)
        lay.addLayout(unten)

    def waehlen(self, grund):
        self.grund = grund
        self.accept()


class PapierkorbDialog(QDialog):
    """Gelöschte Aufträge ansehen und zurückholen (P3)."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f = fenster
        self.setWindowTitle("Papierkorb")
        self.info = QLabel(f"Gelöschte Aufträge bleiben {D.PAPIERKORB_TAGE} Tage hier und lassen sich zurückholen.")
        self.liste = QTableWidget()
        self.liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.liste.setSelectionMode(QAbstractItemView.SingleSelection)
        self.liste.verticalHeader().setVisible(False)
        self.k_zurueck = QPushButton("Zurückholen")
        self.k_zurueck.setObjectName("primaer")
        self.k_zurueck.clicked.connect(lambda _=False: self.zurueckholen())
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        unten = QHBoxLayout()
        unten.addWidget(self.k_zurueck)
        unten.addStretch(1)
        unten.addWidget(zu)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(self.liste, 1)
        lay.addLayout(unten)
        self.resize(760, 420)
        self.zeigen()

    def zeigen(self):
        kopf = ("Auftragsnummer", "Kunde", "Maschine", "Kalkulierte Laufzeit", "Liefertermin", "Status", "Gelöscht am")
        liste = self.f.db.papierkorb()
        self.liste.setColumnCount(len(kopf))
        self.liste.setHorizontalHeaderLabels(kopf)
        self.liste.setRowCount(len(liste))
        for r, a in enumerate(liste):
            for c, t in enumerate((a["nummer"], a["kunde"], a["maschine"], self.f.lz(a["kalk_min"]),
                                   _tag(a["liefertermin"]), a["status"], _tag(str(a["geloescht_am"])[:10]))):
                self.liste.setItem(r, c, _zelle(t, daten=a["id"] if c == 0 else None))
        self.liste.resizeColumnsToContents()
        self.liste.horizontalHeader().setStretchLastSection(True)
        if liste:
            self.liste.selectRow(0)
        self.k_zurueck.setEnabled(bool(liste))

    def zurueckholen(self):
        r = self.liste.currentRow()
        if r < 0:
            return None
        auftrag_id = self.liste.item(r, 0).data(Qt.UserRole)
        self.f.db.zurueckholen(auftrag_id)
        self.zeigen()
        self.f.laden()
        self.f.waehlen(auftrag_id)
        return auftrag_id


class TerminauskunftDialog(QDialog):
    """Wann wäre ein neuer Auftrag fertig? Rechnet nur, speichert nichts (P6)."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f = fenster
        self.setWindowTitle("Terminauskunft")
        self.dauer = LaufzeitFeld(fenster.db)
        self.dauer.eingabe.textChanged.connect(lambda _t: self.rechnen())
        self.antwort = QLabel("")
        self.antwort.setWordWrap(True)
        self.tabelle = QTableWidget()
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        form = QFormLayout()
        form.addRow("Laufzeit des neuen Auftrags", self.dauer)
        hinweis = QLabel("Der Auftrag wird probeweise hinter alle offenen Aufträge der Maschine gestellt. Gespeichert "
                         "wird nichts.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        zu = QDialogButtonBox(QDialogButtonBox.Close)
        zu.button(QDialogButtonBox.Close).setText("Schließen")
        zu.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.antwort)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(hinweis)
        lay.addWidget(zu)
        self.resize(560, 360)
        self.rechnen()

    def rechnen(self):
        try:
            minuten = self.dauer.minuten()
        except laufzeit.Fehler:
            minuten = None
        kopf = ("Maschine", "Start", "Laser fertig", "Lieferbar ab")
        liste = rechnung.auskunft(self.f.db, minuten, self.f.heute()) if minuten else []
        self.tabelle.setColumnCount(len(kopf))
        self.tabelle.setHorizontalHeaderLabels(kopf)
        self.tabelle.setRowCount(len(liste))
        for r, x in enumerate(liste):
            for c, t in enumerate((x["maschine"], _wtag(x["start"]), _wtag(x["fertig"]) or "später als 400 Tage",
                                   _wtag(x["lieferbar"]))):
                self.tabelle.setItem(r, c, _zelle(t))
        self.tabelle.resizeColumnsToContents()
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        if liste and liste[0]["fertig"]:
            x = liste[0]
            self.antwort.setText(f"<b>Am frühesten auf {x['maschine']}: fertig am {_wtag(x['fertig'])}</b>"
                                 + (f", lieferbar ab {_wtag(x['lieferbar'])}." if x["lieferbar"] != x["fertig"] else "."))
        else:
            self.antwort.setText("Bitte die Laufzeit eingeben." if not minuten else "Keine aktive Maschine.")
        return liste


class ZiehTafel(Plantafel):
    """Plantafel des Programms (ab 1.6 eigene Zeichnung, die Plantafel der Kalkulation bleibt unverändert): große
    Balken mit Auftragsnummer und Kunde, Tageskopf, Farbe nach Terminrisiko, Kunde oder Status, Zustand im Balken
    (läuft, gestoppt, wartet auf Material, fester Platz), Liefertermin mit Verspätungslinie, Auslastung je Tag,
    zusammengehörige Teile eines Auftrags hervorgehoben und verbunden. Ein Auftrag lässt sich mit der Maus auf einen
    anderen Tag oder eine andere Maschine ziehen (E1)."""
    verschoben = Signal(object, object, str, object)      # Auftrag-ID, Arbeitsgang-ID oder None, Maschine, Tag
    SCHWELLE = 6                                          # ab so vielen Pixeln ist es Ziehen, kein Klick
    LINKS, KOPF, ZEILE = 76, 58, 86
    B_OBEN, B_HOCH = 16, 46                               # Balken innerhalb der Zeile

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zug, self.ziel, self.ziehbar = None, None, True
        self.farbe_nach = TAFEL_FARBE[0]
        self.zustand = {}                         # {(Auftrag-ID, Gang-ID): dict(laeuft, gestoppt, grund, anteil, material)}
        self.versatz = 0                          # waagerecht gerollt: die Spalte der Maschinen bleibt stehen
        self.kunden = {}
        self.tag_an = False                       # Tagesansicht: ein Tag füllt die Breite, Uhrzeiten, mehr Text
        self.spannen = None                       # Schichtkalender (rechnung.spannen): Arbeitszeit als Uhrzeiten
        self.sicht_breite = None                  # sichtbare Breite im Rollbereich (setzt TafelRahmen.anpassen)

    def tag_ansicht(self, an):
        """Tagesansicht ein/aus: höhere Zeilen für drei Zeilen Text je Auftrag und das Stundenraster."""
        self.tag_an = bool(an)
        self.ZEILE, self.B_OBEN, self.B_HOCH = (118, 30, 62) if an else (86, 16, 46)
        self._groesse()
        self.update()

    def teile_am(self, m, tag):
        """Arbeitszeit der Maschine an diesem Tag als [(Beginn in Minuten, Dauer in Stunden, Schicht)]."""
        if not self.ein or not self.ein["kapazitaet"].get((m, tag)):
            return []
        return (self.spannen.teile(m, tag) if self.spannen else []) or [(360, 8.0, "")]

    def uhr(self, m, tag, stunden):
        """Uhrzeit als Text an der Stelle stunden (der nutzbaren Stunden) dieses Tages, '' ohne Arbeitszeit."""
        kap = self.ein["kapazitaet"].get((m, tag)) if self.ein else None
        minuten = rechnung.uhr_am(self.teile_am(m, tag), stunden / kap) if kap else None
        return "" if minuten is None else D.uhr_text(minuten)

    def setzen(self, aus, ein, wochen, auswahl=None, zustand=None):
        self.zustand = zustand or {}
        namen = sorted({a.get("kunde") or "" for a in ein["auftraege"]})
        self.kunden = {k: T_KUNDEN[i % len(T_KUNDEN)] for i, k in enumerate(namen)}
        super().setzen(aus, ein, wochen, auswahl)

    def farbe_setzen(self, art):
        self.farbe_nach = art if art in TAFEL_FARBE else TAFEL_FARBE[0]
        self.update()

    def versatz_setzen(self, x):
        self.versatz = int(x)
        self.update()

    def _status(self, a):
        z = self.zustand.get((a["id"], a.get("gang")), {})
        return ("läuft" if z.get("laeuft") else "gestoppt" if z.get("gestoppt") else
                "wartet auf Material" if z.get("material") else "offen")

    def balkenfarbe(self, a):
        if self.farbe_nach == "Kunde":
            return QColor(self.kunden.get(a.get("kunde") or "", T_BLAU))
        if self.farbe_nach == "Status":
            return QColor(dict(T_STATUS)[self._status(a)])
        return QColor(T_RISIKO.get(a["risiko"], T_BLAU))

    def legende(self):
        """[(Farbe, Text)] zur gewählten Farbgebung."""
        if self.farbe_nach == "Kunde":
            liste = [(f, k or "ohne Kunde") for k, f in self.kunden.items()]
            return liste[:8] + ([(T_GRAU, f"… {len(liste) - 8} weitere")] if len(liste) > 8 else [])
        if self.farbe_nach == "Status":
            return [(f, t) for t, f in T_STATUS]
        return list(T_RISIKO_TEXT)

    def tipp(self, a):
        """Infokarte (V4): alles Wichtige zum Auftrag unter dem Mauszeiger."""
        z = self.zustand.get((a["id"], a.get("gang")), {})
        zeilen = [f"<b>{a.get('nummer') or ''}</b>" + (f" · {a['kunde']}" if a.get("kunde") else ""),
                  f"{a['maschine'] or D.FREMD_TEXT} · Restlaufzeit {laufzeit.text(int(a['h'] * 60 + 0.5), 'hm')}"]
        if a.get("start"):
            zeilen.append(f"Start {_wtag(a['start'])} · fertig {_wtag(a['fertig']) or 'später'}")
        if a.get("termin_datum"):
            zeilen.append(f"Liefertermin {_wtag(a['termin_datum'])}" + (
                f" · Puffer {_arbeitstage(a['puffer'])}" if a.get("puffer") is not None else ""))
        zeilen.append(f"Terminrisiko: {RISIKO_TEXT.get(a['risiko'], '')}")
        if z.get("laeuft"):
            zeilen.append(f"Läuft seit {z['laeuft']} Uhr" + (f" · {z['anteil']:.0%} erledigt" if z.get("anteil") else ""))
        elif z.get("gestoppt"):
            zeilen.append("Gestoppt" + (f": {z['grund']}" if z.get("grund") else "")
                          + (f" · {z['anteil']:.0%} erledigt" if z.get("anteil") else ""))
        if z.get("material"):
            zeilen.append(f"Wartet auf Material, da ab {_wtag(z['material'])}")
        if a.get("fest"):
            zeilen.append(f"Fester Platz ab {_wtag(a['fest'])}")
        if a.get("material"):
            zeilen.append(f"Material: {a['material']}")
        if a.get("ruest_h"):
            zeilen.append(f"Davon Rüsten {laufzeit.text(int(a['ruest_h'] * 60 + 0.5), 'hm')} (dunkler Anfang)")
        elif a.get("ruest_gespart_h"):
            zeilen.append(f"Rüsten gespart ({laufzeit.text(int(a['ruest_gespart_h'] * 60 + 0.5), 'hm')}): "
                          "gleiches Material direkt davor")
        if "teil" in a:
            zeilen.append(f"Teillieferung {a['teil']} von {a['teil_von']}: {D.mm_text(a.get('menge'))} Stück")
        return "<br>".join(zeilen)

    def _treffer(self, pos):
        if pos.x() < self.versatz + self.LINKS:
            return None
        return super()._treffer(pos)

    def ziel_bei(self, pos):
        """(Maschine, Tag) unter dem Mauszeiger; Tage vor heute werden heute. None außerhalb der Tafel."""
        if not self.ein or not self.tage:
            return None
        zeile = int((pos.y() - self.KOPF) // self.ZEILE)
        spalte = int((pos.x() - self.LINKS) // self._tb())
        if not (0 <= zeile < len(self.ein["maschinen"]) and 0 <= spalte < len(self.tage)) or pos.y() < self.KOPF:
            return None
        if pos.x() < self.versatz + self.LINKS:
            return None
        return self.ein["maschinen"][zeile], max(self.tage[spalte], self.ein["heute"])

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        a = self._treffer(e.position())
        self.zug = (a, e.position()) if a and self.ziehbar and e.button() == Qt.LeftButton else None
        self.ziel = None

    def mouseMoveEvent(self, e):
        if self.zug is None:
            super().mouseMoveEvent(e)
            return
        weg = e.position() - self.zug[1]
        if self.ziel is None and abs(weg.x()) + abs(weg.y()) < self.SCHWELLE:
            return
        self.ziel = self.ziel_bei(e.position())
        if self.ziel:
            QToolTip.showText(e.globalPosition().toPoint(), f"{self.zug[0].get('nummer') or ''}: fest ab "
                              f"{_wtag(self.ziel[1])} auf {self.ziel[0]}", self)
        self.update()

    def mouseReleaseEvent(self, e):
        zug, ziel = self.zug, self.ziel
        self.zug = self.ziel = None
        self.update()
        if zug and ziel:
            self.verschoben.emit(zug[0]["id"], zug[0].get("gang"), ziel[0], ziel[1])

    def paintEvent(self, _ereignis):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self.flaechen = []
        if not self.ein or not self.tage:
            p.end()
            return
        tb = self._tb()
        text, grau = stil.farbe(stil.TEXT), stil.farbe(stil.TEXT_GRAU)
        linie, fein = stil.farbe(stil.RAHMEN), stil.farbe(stil.LINIE)
        zu, hell, weiss = stil.farbe("#EEF1F5"), stil.farbe("#FFFFFF"), QColor("#FFFFFF")
        normal = self.font()
        klein, fett = self.font(), self.font()
        klein.setPointSizeF(max(6.5, normal.pointSizeF() * 0.85))
        fett.setBold(True)
        fm, fmf = QFontMetrics(normal), QFontMetrics(fett)
        maschinen = self.ein["maschinen"]
        unten = self.KOPF + len(maschinen) * self.ZEILE
        heute = self.ein["heute"]
        # ---- Kopf: Kalenderwoche, Wochentag, Datum
        for i, tag in enumerate(self.tage):
            x = self.LINKS + i * tb
            if tag.weekday() == 0:
                p.setPen(QPen(linie, 1))
                p.drawLine(QPointF(x, 2), QPointF(x, unten))
                p.setFont(klein)
                p.setPen(grau)
                p.drawText(QRectF(x + 4, 1, tb * 7 - 6, 14), Qt.AlignLeft | Qt.AlignVCenter,
                           f"KW {tag.isocalendar()[1]}" + ("" if tb >= 40 else f"  {tag.strftime('%d.%m.')}"))
            elif tb >= 40:
                p.setPen(QPen(fein, 1))
                p.drawLine(QPointF(x, 18), QPointF(x, unten))
            frei = not any(self.ein["kapazitaet"].get((m, tag)) for m in maschinen)
            p.setPen(grau if frei else text)
            if self.tag_an and tb >= 300:
                p.setFont(fett)
                p.drawText(QRectF(x + 8, 18, tb - 12, 34), Qt.AlignLeft | Qt.AlignVCenter,
                           f"{WOCHENTAG_LANG[tag.weekday()]}, {tag.strftime('%d.%m.%Y')}"
                           + ("  (arbeitsfrei)" if frei else ""))
            elif tb >= 40:
                p.setFont(fett if tag == heute else normal)
                p.drawText(QRectF(x, 18, tb, 17), Qt.AlignCenter, WOCHENTAG[tag.weekday()])
                p.drawText(QRectF(x, 35, tb, 17), Qt.AlignCenter, tag.strftime("%d.%m."))
            elif tb >= 15:
                p.setFont(klein)
                p.drawText(QRectF(x, 22, tb, 14), Qt.AlignCenter, WOCHENTAG[tag.weekday()][:1])
                p.drawText(QRectF(x, 37, tb, 14), Qt.AlignCenter, f"{tag.day}")
        teile = {}                                # {Auftrag-ID: [(Stufe, erster Balken, letzter Balken)]} für V7
        sicht_von = self.versatz + self.LINKS
        sicht_bis = self.versatz + (self.sicht_breite if self.tagbreite_fest and self.sicht_breite
                                    else self.width())
        for r, m in enumerate(maschinen):
            y = self.KOPF + r * self.ZEILE
            p.setPen(QPen(fein, 1))
            p.drawLine(QPointF(0, y), QPointF(self.width(), y))
            p.setPen(Qt.NoPen)
            for i, tag in enumerate(self.tage):   # Tage ohne Schicht und Vergangenheit grau; Auslastung des Tages (V8)
                kap = self.ein["kapazitaet"].get((m, tag))
                x = self.LINKS + i * tb
                p.setBrush(zu if tag < heute or not kap else hell)
                p.drawRect(QRectF(x, y + 1, tb + 0.5, self.ZEILE - 1))
                if kap and tag >= heute and tb >= 6:
                    voll = min(1.0, sum(self.ein["belegt"].get((m, tag), {}).values()) / kap)
                    p.setBrush(stil.farbe(stil.LINIE))
                    p.drawRect(QRectF(x + 2, y + 5, tb - 4, 5))
                    if voll > 0.004:
                        p.setBrush(QColor(T_ROT if voll >= 0.995 else T_GELB if voll >= 0.8 else T_GRUEN))
                        p.drawRect(QRectF(x + 2, y + 5, (tb - 4) * voll, 5))
                if self.tag_an and tb >= 300 and kap:                         # Stundenraster mit Uhrzeiten
                    self._raster(p, m, tag, x, y, tb, klein, grau, fein, linie)
                    p.setPen(Qt.NoPen)
            for a in (x for x in self.ein["auftraege"] if x["maschine"] == m):
                farbe = self.balkenfarbe(a)
                gewaehlt = a["id"] == self.auswahl
                blass = self.auswahl is not None and not gewaehlt and any(
                    x["id"] == self.auswahl for x in self.ein["auftraege"])
                if blass:
                    farbe.setAlpha(70)
                z = self.zustand.get((a["id"], a.get("gang")), {})
                laeufe = self.laeufe(a, m)
                gross = None
                for n, (x0, x1) in enumerate(laeufe):
                    rect = QRectF(x0, y + self.B_OBEN, max(3.0, x1 - x0 - 1), self.B_HOCH)
                    p.setPen(QPen(text, 2.2) if gewaehlt else QPen(farbe.darker(135), 1))
                    p.setBrush(farbe)
                    p.drawRoundedRect(rect, 5, 5)
                    if n == 0 and z.get("material") and rect.width() > 8:      # wartet auf Material: schraffiert
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(QColor(255, 255, 255, 150), Qt.BDiagPattern))
                        p.drawRoundedRect(rect, 5, 5)
                    self.flaechen.append((rect.adjusted(-1, -6, 1, 6), a))
                    # Text ins größte Stück, das gerade zu sehen ist (beim Rollen und im Vollbild)
                    zu_sehen = QRectF(max(rect.left(), sicht_von), rect.top(),
                                      min(rect.right(), sicht_bis) - max(rect.left(), sicht_von), rect.height())
                    if zu_sehen.width() > 0 and (gross is None or zu_sehen.width() > gross.width()):
                        gross = zu_sehen
                if laeufe:
                    erster = QRectF(laeufe[0][0], y + self.B_OBEN, max(3.0, laeufe[0][1] - laeufe[0][0] - 1), self.B_HOCH)
                    letzter = QRectF(laeufe[-1][0], y + self.B_OBEN, max(3.0, laeufe[-1][1] - laeufe[-1][0] - 1),
                                     self.B_HOCH)
                    teile.setdefault(a["id"], []).append((a.get("stufe", 0), erster, letzter))
                    if z.get("anteil") and erster.width() > 10:               # Fortschritt: Leiste unten im Balken
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor(255, 255, 255, 90 if not blass else 40))
                        leiste = QRectF(erster.left() + 3, erster.bottom() - 7, erster.width() - 6, 4)
                        p.drawRect(leiste)
                        p.setBrush(QColor(255, 255, 255, 235 if not blass else 90))
                        p.drawRect(QRectF(leiste.left(), leiste.top(), leiste.width() * min(1.0, z["anteil"]), 4))
                    if a.get("ruest_h") and a.get("stuecke"):                 # A1 Rüsten: dunkler Anfang des Balkens
                        tag0, von0, bis0 = a["stuecke"][0]
                        if self.tage[0] <= tag0 <= self.tage[-1]:
                            kap0 = self.ein["kapazitaet"].get((m, tag0)) or 1.0
                            xa = self._x(tag0, von0 / kap0)
                            xb = min(self._x(tag0, min(1.0, min(bis0, von0 + a["ruest_h"]) / kap0)), erster.right())
                            if xb - xa >= 3:
                                p.setPen(Qt.NoPen)
                                p.setBrush(QColor(0, 0, 0, 40 if blass else 95))
                                p.drawRoundedRect(QRectF(xa, erster.top(), xb - xa, erster.height()), 5, 5)
                    if a.get("fest"):                                         # fester Platz: weißer Punkt links oben
                        p.setPen(QPen(QColor("#1F2937"), 1.2))
                        p.setBrush(weiss)
                        p.drawEllipse(QPointF(erster.left() + 1, erster.top() + 1), 4, 4)
                if self.tag_an and tb >= 300:                                 # Tagesansicht: Text je Tag mit Uhrzeit
                    self._tagestext(p, a, m, y, z, blass, fett, normal, fmf, fm)
                elif gross is not None and gross.width() > 34:                # zwei Zeilen Text im größten Stück (V1)
                    schrift = QColor(255, 255, 255, 110) if blass else weiss
                    marke = "▶ " if z.get("laeuft") else "❚❚ " if z.get("gestoppt") else ""
                    breite = int(gross.width() - 12)
                    p.setPen(schrift)
                    p.setFont(fett)
                    p.drawText(QRectF(gross.left() + 7, gross.top() + 4, breite, 18), Qt.AlignLeft | Qt.AlignVCenter,
                               fmf.elidedText(marke + str(a.get("nummer") or ""), Qt.ElideRight, breite))
                    zweite = (f"Material ab {z['material'].strftime('%d.%m.')}" if z.get("material") else
                              f"gestoppt: {z['grund']}" if z.get("gestoppt") and z.get("grund") else
                              " · ".join(x for x in (a.get("kunde") or "",
                                                     laufzeit.text(int(a["h"] * 60 + 0.5), "hm")) if x))
                    p.setFont(normal)
                    p.drawText(QRectF(gross.left() + 7, gross.top() + 21, breite, 18), Qt.AlignLeft | Qt.AlignVCenter,
                               fm.elidedText(zweite, Qt.ElideRight, breite))
                t = a.get("termin_datum")
                if t and self.tage[0] <= t <= self.tage[-1]:                  # Liefertermin: Dreieck am Zeilenfuß (V6)
                    x = self._x(t, 1.0)
                    yb = y + self.ZEILE - 2
                    spaet = bool(a.get("fertig")) and a["risiko"] == einlastung.UEBER
                    marke_farbe = QColor(T_RISIKO.get(a["risiko"], T_GRAU)) if self.farbe_nach != "Terminrisiko" \
                        else QColor(farbe)
                    if blass:
                        marke_farbe.setAlpha(70)
                    p.setPen(Qt.NoPen)
                    p.setBrush(marke_farbe)
                    p.drawPolygon(QPolygonF([QPointF(x - 6, yb), QPointF(x + 6, yb), QPointF(x, yb - 10)]))
                    if (spaet or gewaehlt) and a.get("fertig") and laeufe:   # gestrichelt bis zum Ende des Balkens
                        p.setPen(QPen(marke_farbe, 1.4, Qt.DashLine))
                        ende = min(laeufe[-1][1], self.width())
                        p.drawLine(QPointF(min(ende, x), yb - 5), QPointF(max(ende, x), yb - 5))
                        if ende > x:
                            p.drawLine(QPointF(ende, yb - 5), QPointF(ende, y + self.B_OBEN + self.B_HOCH))
        for auftrag_id, liste in teile.items():   # Arbeitsgänge eines Auftrags verbinden (V7)
            stufen = sorted({s for s, _e, _l in liste})
            if len(stufen) < 2:
                continue
            stift = QColor(text)
            stift.setAlpha(230 if auftrag_id == self.auswahl else 110)
            p.setPen(QPen(stift, 1.6 if auftrag_id == self.auswahl else 1.0, Qt.DotLine))
            for vor, nach in zip(stufen, stufen[1:]):
                for _s, _e, ende in (x for x in liste if x[0] == vor):
                    for _s2, anfang, _l in (x for x in liste if x[0] == nach):
                        p.drawLine(QPointF(ende.right(), ende.center().y()), QPointF(anfang.left(), anfang.center().y()))
        p.setPen(QPen(fein, 1))
        p.drawLine(QPointF(0, unten), QPointF(self.width(), unten))
        if self.tage[0] <= heute <= self.tage[-1]:                            # heute: Linie mit Schild
            x = self._x(heute)
            p.setPen(QPen(QColor(T_ROT), 1.6))
            p.drawLine(QPointF(x, 14), QPointF(x, unten))
            p.setFont(klein)
            if x >= self.versatz + self.LINKS - 1:                            # nicht, wenn heute weggerollt ist
                schild = QRectF(max(x - 20, self.versatz + self.LINKS + 2), 1 if tb >= 40 else 18, 40, 14)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(T_ROT))
                p.drawRoundedRect(schild, 3, 3)
                p.setPen(weiss)
                p.drawText(schild, Qt.AlignCenter, "heute")
        if self.zug and self.ziel:                # Ziel beim Ziehen: Strich am Tagesanfang in der Zeile der Maschine
            m, tag = self.ziel
            y = self.KOPF + maschinen.index(m) * self.ZEILE
            x = self._x(tag)
            p.setPen(QPen(text, 2, Qt.DashLine))
            p.drawLine(QPointF(x, y + 2), QPointF(x, y + self.ZEILE - 2))
            p.setPen(QPen(text, 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(self.LINKS, y + 1, self.width() - self.LINKS - 4, self.ZEILE - 2))
        # ---- Spalte der Maschinen: bleibt beim Rollen stehen
        p.setPen(Qt.NoPen)
        p.setBrush(self.palette().window())
        p.drawRect(QRectF(self.versatz, 0, self.LINKS, unten + 1))
        p.setFont(fett)
        for r, m in enumerate(maschinen):
            y = self.KOPF + r * self.ZEILE
            p.setPen(QPen(fein, 1))
            p.drawLine(QPointF(self.versatz, y), QPointF(self.versatz + self.LINKS, y))
            p.setPen(text)
            p.drawText(QRectF(self.versatz + 6, y, self.LINKS - 10, self.ZEILE), Qt.AlignLeft | Qt.AlignVCenter,
                       fmf.elidedText(m, Qt.ElideRight, self.LINKS - 10))
        p.setPen(QPen(linie, 1))
        p.drawLine(QPointF(self.versatz + self.LINKS, self.KOPF), QPointF(self.versatz + self.LINKS, unten))
        p.end()


def _tafel_zusatz():
    """Zeichnen der Tagesansicht (Methoden der ZiehTafel, hier nur wegen der Länge von paintEvent getrennt)."""

    def raster(self, p, m, tag, x, y, tb, klein, grau, fein, linie):
        teile = self.teile_am(m, tag)
        gesamt = sum(d for _b, d, _n in teile)
        if gesamt <= 0:
            return
        schritt = 1 if tb / gesamt >= 46 else 2 if tb / gesamt >= 23 else 4
        p.setFont(klein)
        aus = self.spannen.ausnahme(m, tag) if self.spannen else None
        grund = f" · {aus['grund'] or 'Ausnahme'}" if aus else ""          # Ausnahme im Schichtkalender nennen
        vor = 0.0
        frei_ab = x                                # links davon steht schon Text (Grund der Ausnahme)
        fmk = QFontMetrics(klein)
        for i, (beginn, dauer, name) in enumerate(teile):
            x0 = x + tb * vor / gesamt
            if i:
                p.setPen(QPen(linie, 1.4))
                p.drawLine(QPointF(x0, y + 12), QPointF(x0, y + self.ZEILE - 1))
            erste = -(-beginn // 60) * 60                 # erste volle Stunde in der Schicht
            t = erste
            while t < beginn + dauer * 60 - 1:
                xs = x0 + tb * ((t - beginn) / 60) / gesamt
                if t > beginn:
                    p.setPen(QPen(fein, 1))
                    p.drawLine(QPointF(xs, y + 26), QPointF(xs, y + self.ZEILE - 1))
                if ((t - erste) // 60) % schritt == 0 and xs + 34 < x + tb and xs + 3 >= frei_ab:
                    p.setPen(grau)
                    marke = D.uhr_text(t) + (f" {name}" if name and t == erste and tb * schritt / gesamt >= 90 else "")
                    breit = 110
                    if grund and i == 0 and t == erste:
                        marke = D.uhr_text(t) + (f" {name}" if name else "") + grund
                        breit = min(fmk.horizontalAdvance(marke) + 4, int(x + tb - xs - 6))
                        marke = fmk.elidedText(marke, Qt.ElideRight, breit)
                        frei_ab = xs + 3 + breit + 8
                    p.drawText(QRectF(xs + 3, y + 12, breit, 14), Qt.AlignLeft | Qt.AlignVCenter, marke)
                t += 60
            vor += dauer

    def tagestext(self, p, a, m, y, z, blass, fett, normal, fmf, fm):
        weiss = QColor(255, 255, 255, 110) if blass else QColor("#FFFFFF")
        marke = "▶ " if z.get("laeuft") else "❚❚ " if z.get("gestoppt") else ""
        for tag, von, bis in a["stuecke"]:
            if tag < self.tage[0] or tag > self.tage[-1] or bis - von <= 0:
                continue
            kap = self.ein["kapazitaet"].get((m, tag)) or 1.0
            x0, x1 = self._x(tag, von / kap), self._x(tag, min(1.0, bis / kap))
            breite = int(x1 - x0 - 14)
            if breite < 40:
                continue
            p.setPen(weiss)
            p.setFont(fett)
            kopf = marke + " · ".join(t for t in (str(a.get("nummer") or ""), a.get("kunde") or "") if t)
            p.drawText(QRectF(x0 + 7, y + self.B_OBEN + 3, breite, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       fmf.elidedText(kopf, Qt.ElideRight, breite))
            p.setFont(normal)
            zeit = f"{self.uhr(m, tag, von)} bis {self.uhr(m, tag, bis)} Uhr · {laufzeit.text(int((bis - von) * 60 + 0.5), 'hm')}"
            p.drawText(QRectF(x0 + 7, y + self.B_OBEN + 21, breite, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(zeit, Qt.ElideRight, breite))
            heute = tag == self.ein["heute"]
            dritte = (f"wartet auf Material, da ab {z['material'].strftime('%d.%m.')}" if z.get("material") else
                      f"läuft seit {z['laeuft']} · gelaufen {laufzeit.text(z.get('gelaufen', 0), 'hm')} von "
                      f"{laufzeit.text(z.get('kalk', 0), 'hm')}" if heute and z.get("laeuft") else
                      f"gestoppt: {z['grund']}" if z.get("gestoppt") and z.get("grund") else
                      " · ".join(t for t in (
                          f"Rest gesamt {laufzeit.text(int(a['h'] * 60 + 0.5), 'hm')}" if a["h"] - (bis - von) > 0.01
                          else "", f"fertig {_wtag(a['fertig'])[:-4]}" if a.get("fertig") and a["fertig"] != tag else
                          "wird heute fertig" if a.get("fertig") == tag == self.ein["heute"] else
                          "wird an diesem Tag fertig" if a.get("fertig") == tag else "",
                          f"Termin {_wtag(a['termin_datum'])[:-4]}" if a.get("termin_datum") else "") if t))
            p.drawText(QRectF(x0 + 7, y + self.B_OBEN + 39, breite, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(dritte, Qt.ElideRight, breite))

    return raster, tagestext


ZiehTafel._raster, ZiehTafel._tagestext = _tafel_zusatz()


HALLE_SCHRIFT = (("normal", 1.0), ("groß", 1.5), ("sehr groß", 2.0))
HALLE_TAKT = (("aus", 0), ("alle 15 s", 15), ("alle 30 s", 30), ("jede Minute", 60))
HALLE_SEITEN = {"Tag": 5, "1 Woche": 4, "2 Wochen": 2}      # so viele Seiten zeigt das automatische Blättern


class TafelVollbild(QWidget):
    """Plantafel allein in einem Fenster (V2, A4), für den Bildschirm in der Halle: nur ansehen, Ansicht wählbar,
    große Schrift (die ganze Tafel wird vergrößert), Uhr, automatisches Blättern. Esc oder „Schließen“ beendet."""

    def __init__(self, parent=None, platz=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Plantafel")
        self.platz = platz
        self.tafel = ZiehTafel()
        self.tafel.ziehbar = False
        self.rahmen = TafelRahmen(self.tafel)
        self.faktor, self.name, self.seite, self.jetzt = 1.0, "1 Woche", 0, None
        self.szene = QGraphicsScene(self)
        self.huelle = self.szene.addWidget(self.rahmen)
        self.sicht = QGraphicsView(self.szene)
        self.sicht.setFrameShape(QFrame.NoFrame)
        self.sicht.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.sicht.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sicht.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.sicht.setBackgroundBrush(self.palette().window())
        self.sicht.viewport().installEventFilter(self)
        self.titel = QLabel("")
        self.titel.setTextFormat(Qt.RichText)
        self.uhr = QLabel("")
        self.uhr.setToolTip("Datum und Uhrzeit dieses Rechners")
        self.knoepfe = {}
        oben = QHBoxLayout()
        oben.addWidget(self.titel)
        oben.addStretch(1)
        oben.addWidget(self.uhr)
        oben.addStretch(1)
        for name, tage in TAFEL_ZOOM:
            k = QPushButton(name)
            k.setCheckable(True)
            k.clicked.connect(lambda _=False, name=name: self.ansicht(name))
            oben.addWidget(k)
            self.knoepfe[name] = k
        for zeichen, tun in (("◀", lambda: self.rahmen.blaettern(-1)), ("Heute", lambda: self.rahmen.zu_heute()),
                             ("▶", lambda: self.rahmen.blaettern(1))):
            k = QPushButton(zeichen)
            k.clicked.connect(lambda _=False, tun=tun: tun())
            oben.addWidget(k)
        self.schrift = QComboBox()
        for name, f in HALLE_SCHRIFT:
            self.schrift.addItem(f"Schrift {name}", f)
        self.schrift.setToolTip("Vergrößert die ganze Plantafel, damit sie aus der Entfernung lesbar ist.")
        self.blaettert = QComboBox()
        for name, sek in HALLE_TAKT:
            self.blaettert.addItem(f"Blättern {name}", sek)
        self.blaettert.setToolTip("Automatisch weiterblättern: in der Tagesansicht durch die nächsten Arbeitstage, "
                                  "in der Wochenansicht durch die nächsten Wochen, danach wieder von vorn. Passen "
                                  "nicht alle Maschinen auf den Bildschirm, kommen erst die unteren dran.")
        oben.addSpacing(12)
        oben.addWidget(self.schrift)
        oben.addWidget(self.blaettert)
        zu = QPushButton("Schließen (Esc)")
        zu.clicked.connect(self.close)
        oben.addSpacing(12)
        oben.addWidget(zu)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.sicht, 1)
        self.sekunde = QTimer(self)
        self.sekunde.timeout.connect(self.uhr_zeigen)
        self.sekunde.start(1000)
        self.takt = QTimer(self)
        self.takt.timeout.connect(self.weiter)
        ini = ort.ini_lesen(platz) if platz is not None else {}
        try:
            faktor, sek = float(ini.get("halle_schrift") or 1.5), int(ini.get("halle_takt") or 0)
        except ValueError:
            faktor, sek = 1.5, 0
        self.schrift.setCurrentIndex(max(0, self.schrift.findData(faktor)))
        self.blaettert.setCurrentIndex(max(0, self.blaettert.findData(sek)))
        self.schrift.currentIndexChanged.connect(lambda _i: self.schrift_setzen(self.schrift.currentData()))
        self.blaettert.currentIndexChanged.connect(lambda _i: self.takt_setzen(self.blaettert.currentData()))
        self.schrift_setzen(self.schrift.currentData(), merken=False)
        self.takt_setzen(self.blaettert.currentData(), merken=False)
        self.ansicht("1 Woche")
        self.uhr_zeigen()

    def _merken(self, schluessel, wert):
        if self.platz is not None:
            try:
                ort.merken(schluessel, wert, self.platz)
            except OSError:
                pass

    def schrift_setzen(self, faktor, merken=True):
        """Größe der Tafel: 1 = wie im Hauptfenster; Titel und Uhr wachsen mit."""
        self.faktor = float(faktor or 1.0)
        self.sicht.resetTransform()
        self.sicht.scale(self.faktor, self.faktor)
        punkt = self.font().pointSizeF() if self.font().pointSizeF() > 0 else 10.0
        self.titel.setStyleSheet(f"font-size: {punkt * self.faktor:.1f}pt;")
        self.uhr.setStyleSheet(f"font-size: {punkt * self.faktor * 1.25:.1f}pt; font-weight: bold;")
        if merken:
            self._merken("halle_schrift", f"{self.faktor:g}")
        self.anpassen()

    def takt_setzen(self, sekunden, merken=True):
        """Automatisches Blättern alle sekunden (0 = aus)."""
        self.takt.stop()
        if sekunden:
            self.takt.start(int(sekunden) * 1000)
        if merken:
            self._merken("halle_takt", str(int(sekunden or 0)))

    def uhr_zeigen(self):
        jetzt = self.jetzt or datetime.datetime.now()
        self.uhr.setText(f"{WOCHENTAG_LANG[jetzt.weekday()]}, {jetzt:%d.%m.%Y}   {jetzt:%H:%M} Uhr")

    def anpassen(self):
        """Die Tafel füllt die Breite des Fensters, auch vergrößert."""
        breite = max(200, int(self.sicht.viewport().width() / self.faktor))
        if self.rahmen.width() != breite:
            self.rahmen.setFixedWidth(breite)
        self.rahmen.anpassen()
        self.szene.setSceneRect(0, 0, breite, self.rahmen.height())

    def ansicht(self, name):
        self.name, self.seite = name, 0
        for n, k in self.knoepfe.items():
            k.setChecked(n == name)
        self.rahmen.sichtbar(dict(TAFEL_ZOOM)[name])
        self.anpassen()

    def weiter(self):
        """Ein Schritt des automatischen Blätterns: erst nach unten, wenn Maschinen fehlen, dann in der Zeit weiter;
        nach der letzten Seite wieder von vorn. Tage ohne Arbeitszeit überspringt die Tagesansicht."""
        senkrecht = self.sicht.verticalScrollBar()
        if senkrecht.value() < senkrecht.maximum():
            senkrecht.setValue(min(senkrecht.maximum(), senkrecht.value() + max(1, self.sicht.viewport().height() - 40)))
            return
        senkrecht.setValue(0)
        seiten = HALLE_SEITEN.get(self.name, 1)
        waagerecht = self.rahmen.horizontalScrollBar()
        self.seite += 1
        if self.seite >= seiten or waagerecht.value() >= waagerecht.maximum():
            self.seite = 0
            self.rahmen.zu_heute()
            return
        self.rahmen.blaettern(1)
        t = self.tafel
        for _n in range(7):                       # Tagesansicht: arbeitsfreie Tage auslassen
            tag = self.rahmen.tag_zeigen()
            if tag is None or not t.ein or any(t.ein["kapazitaet"].get((m, tag)) for m in t.ein["maschinen"]):
                break
            if waagerecht.value() >= waagerecht.maximum():
                break
            self.rahmen.blaettern(1)

    def eventFilter(self, wer, e):
        if e.type() == QEvent.Resize:
            QTimer.singleShot(0, self.anpassen)
        return False

    def closeEvent(self, e):
        self.takt.stop()
        super().closeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self.takt_setzen(self.blaettert.currentData(), merken=False)
        QTimer.singleShot(0, self.anpassen)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_F11):
            self.close()
        else:
            super().keyPressEvent(e)


class TafelRahmen(QScrollArea):
    """Rollbarer Rahmen um die Plantafel (V2): tage = so viele Tage sind sichtbar (None = alles passend); die Spalte
    der Maschinen bleibt beim Rollen stehen."""

    def __init__(self, tafel, parent=None):
        super().__init__(parent)
        self.tafel, self.tage = tafel, None
        self.aussen = None                        # äußerer Rollbereich der Seite: begrenzt die sichtbare Breite
        self.setWidget(tafel)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.horizontalScrollBar().valueChanged.connect(tafel.versatz_setzen)

    def sichtbar(self, tage):
        self.tage = tage
        self.tafel.tag_ansicht(tage == 1)
        self.anpassen()
        self.zu_heute() if tage == 1 else self.horizontalScrollBar().setValue(0)

    def schritt(self):
        """So weit rollt ein Schritt: ein Tag in der Tagesansicht, sonst eine Woche."""
        return int((self.tafel.tagbreite_fest or 0) * (1 if self.tage == 1 else 7))

    def zu_heute(self):
        """Tagesansicht: heute zeigen; sonst an den Anfang (die laufende Woche)."""
        t = self.tafel
        if self.tage == 1 and t.ein and t.ein["heute"] in t.tage and t.tagbreite_fest:
            self.horizontalScrollBar().setValue(int(t.tage.index(t.ein["heute"]) * t.tagbreite_fest))
        else:
            self.horizontalScrollBar().setValue(0)

    def blaettern(self, richtung):
        b, s = self.horizontalScrollBar(), self.schritt()
        if s and self.tage == 1:                  # Tagesansicht: immer auf einem ganzen Tag landen
            b.setValue(int(round(b.value() / s) + richtung) * s)
        elif s:
            b.setValue(b.value() + richtung * s)

    def tag_zeigen(self):
        """Der Tag, der in der Tagesansicht gerade links steht (sonst None)."""
        t = self.tafel
        if self.tage != 1 or not t.tagbreite_fest or not t.tage:
            return None
        return t.tage[min(len(t.tage) - 1, int(round(self.horizontalScrollBar().value() / t.tagbreite_fest)))]

    def anpassen(self):
        breite = self.viewport().width()
        if self.aussen is not None:               # die Seite ist breiter als ihr Fenster: nur das Sichtbare zählt
            breite = min(breite, self.aussen.viewport().width() - 4)
        self.tafel.sicht_breite = breite
        breite -= self.tafel.LINKS + 4
        fest = max(8.0, breite / self.tage) if self.tage and self.tage < len(self.tafel.tage) else None
        if fest != self.tafel.tagbreite_fest:
            tag = self.tag_zeigen()               # Tagesansicht: beim Ändern der Fensterbreite auf dem Tag bleiben
            self.tafel.zoom(fest)
            if tag is not None and fest:
                self.horizontalScrollBar().setValue(int(self.tafel.tage.index(tag) * fest))
        self.horizontalScrollBar().setSingleStep(max(20, int(fest or 20)) if self.tage == 1 else 40)
        hoch = self.tafel.sizeHint().height() + (self.horizontalScrollBar().sizeHint().height() + 2 if fest else 0)
        if hoch != self.height():
            self.setFixedHeight(hoch)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.anpassen()

    def eventFilter(self, wer, e):
        if e.type() == QEvent.Resize:
            QTimer.singleShot(0, self.anpassen)
        return False


OPT_TEXT = {rechnung.OPT_MASCHINE: "auf {nach} statt {von}", rechnung.OPT_VOR: "vorziehen (läuft als Nächstes)",
            rechnung.OPT_TERMIN: "wieder nach Liefertermin einordnen",
            rechnung.OPT_FOLGE: "direkt hinter gleiches Material stellen ({material})"}
ZIEL_TEXT = dict(rechnung.ZIELE)
ZIEL_HINWEIS = {
    rechnung.ZIEL_TERMIN: "Ziel: möglichst wenige Aufträge zu spät. Dafür kann ein Auftrag, der ohnehin nicht zu "
                          "halten ist, weiter nach hinten rücken (rot).",
    rechnung.ZIEL_RUESTEN: "Ziel: möglichst wenig Rüstzeit. Aufträge mit gleichem Material rücken auf ihrer Maschine "
                           "direkt hintereinander, solange dadurch kein Termin mehr reißt oder knapp wird. Die "
                           "Aufträge bis dorthin bekommen eine feste Reihenfolge; neue Aufträge stehen dahinter.",
    rechnung.ZIEL_GLEICH: "Ziel: Arbeitsvorrat der Ausweichmaschinen möglichst gleich. Aufträge wechseln die "
                          "Maschine, solange dadurch kein Termin mehr reißt oder knapp wird und das Rohr dort passt."}


def _stunden_text(h):
    return laufzeit.text(int(h * 60 + 0.5), "hm")


def _guete_text(g):
    return (f"{g[0]} nicht zu halten, {g[1]} knapp" + (f", zusammen {g[2]} Arbeitstage zu spät" if g[2] else ""))


class OptimierenDialog(QDialog):
    """Vorschlag der automatischen Optimierung (V5): oben die Änderungen, unten ihre Wirkung je Auftrag.
    Gespeichert wird erst mit „Übernehmen“."""

    def __init__(self, fenster, vorschlag):
        super().__init__(fenster)
        ziel = vorschlag.get("ziel", rechnung.ZIEL_TERMIN)
        self.setWindowTitle(f"Optimieren: Vorschlag ({ZIEL_TEXT[ziel]})")
        self.resize(820, 560)
        mehr = ("", "")
        if ziel == rechnung.ZIEL_RUESTEN:
            mehr = tuple(f", Rüsten {_stunden_text(h)}" for h in vorschlag["ruest"])
        elif ziel == rechnung.ZIEL_GLEICH:
            mehr = tuple(", Unterschied im Arbeitsvorrat " + f"{t:.1f}".replace(".", ",") + " Arbeitstage"
                         for t in vorschlag["ungleich"])
        kopf = QLabel(f"<b>Jetzt:</b> {_guete_text(vorschlag['vorher'])}{mehr[0]}<br>"
                      f"<b>Mit dem Vorschlag:</b> {_guete_text(vorschlag['nachher'])}{mehr[1]}")
        kopf.setTextFormat(Qt.RichText)
        self.schritte = QTableWidget(len(vorschlag["schritte"]), 3)
        self.schritte.setHorizontalHeaderLabels(("Auftragsnummer", "Kunde", "Änderung"))
        for r, s in enumerate(vorschlag["schritte"]):
            for c, t in enumerate((s["nummer"], s["kunde"], OPT_TEXT[s["art"]].format(**s))):
                self.schritte.setItem(r, c, _zelle(t))
        liste = vorschlag["aenderungen"]
        self.wirkung = QTableWidget(len(liste), 5)
        self.wirkung.setHorizontalHeaderLabels(("Auftragsnummer", "Kunde", "Laser fertig bisher", "Laser fertig neu",
                                                "Terminrisiko"))
        for r, x in enumerate(liste):
            risiko = (RISIKO_TEXT.get(x["risiko_neu"], "") if x["risiko_alt"] == x["risiko_neu"] else
                      f"{RISIKO_TEXT.get(x['risiko_alt'], '')} → {RISIKO_TEXT.get(x['risiko_neu'], '')}")
            for c, t in enumerate((x["nummer"], x["kunde"], _wtag(x["fertig_alt"]) or "später",
                                   _wtag(x["fertig_neu"]) or "später", risiko)):
                z = _zelle(t)
                if c == 4 and x["schlechter"] < 0:
                    z.setForeground(QColor(stil.umsetzen(stil.GRUEN)))
                elif c == 4 and (x["schlechter"] > 0 or (x["risiko_neu"] == einlastung.UEBER and (x["tage"] or 0) > 0)):
                    z.setForeground(QColor(stil.umsetzen(stil.ROT)))
                    if x["schlechter"] <= 0:
                        z.setText(f"{t}, {x['tage']} Tage später")
                self.wirkung.setItem(r, c, z)
        for t in (self.schritte, self.wirkung):
            t.verticalHeader().setVisible(False)
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.horizontalHeader().setStretchLastSection(True)
            t.resizeColumnsToContents()
        hinweis = QLabel(ZIEL_HINWEIS[ziel] + " Laufende Aufträge, Aufträge mit festem Platz, mit mehreren "
                         "Arbeitsgängen oder mit Teillieferungen bleiben unberührt. Nach dem Übernehmen stellt "
                         "„Optimierung rückgängig“ den Stand von jetzt wieder her.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        kn = QDialogButtonBox()
        self.k_ok = kn.addButton("Übernehmen", QDialogButtonBox.AcceptRole)
        kn.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        self.k_ok.setEnabled(fenster.db.darf("auftraege"))
        kn.accepted.connect(self.accept)
        kn.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(kopf)
        lay.addWidget(QLabel(f"<b>{len(vorschlag['schritte'])} Änderungen</b>"))
        lay.addWidget(self.schritte, 1)
        lay.addWidget(QLabel("<b>Wirkung</b> (Aufträge, deren Fertig-Tag oder Terminrisiko sich ändert)"))
        lay.addWidget(self.wirkung, 2)
        lay.addWidget(hinweis)
        lay.addWidget(kn)


class WasWaereWennDialog(QDialog):
    """Was-wäre-wenn (E2): Samstagsarbeit, Zusatzstunden in einer Woche, ein Auftrag auf einer anderen Maschine.
    Rechnet nur; gespeichert wird erst mit „Übernehmen“."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f = f = fenster
        self.setWindowTitle("Was wäre, wenn …")
        self.samstag = QDoubleSpinBox()
        self.samstag.setRange(0, 24)
        self.samstag.setDecimals(1)
        self.samstag.setSuffix(" h")
        self.samstag.setValue(f.db.zahl("samstag_stunden"))
        self.zusatz = dict(f.aus.get("zusatz") or {})     # {(Maschine, Montag): Stunden}
        self.wechsel = {}                                 # {Auftrag-ID: Maschine}
        maschinen = list(f.aus["maschinen"])
        montage = [s[0] for s in f.aus["spalten"] if isinstance(s[0], datetime.date)]
        self.z_maschine = QComboBox()
        self.z_maschine.addItems(maschinen)
        self.z_woche = QComboBox()
        for mo in montage:
            self.z_woche.addItem(f"KW {mo.isocalendar()[1]} (ab {mo.strftime('%d.%m.')})", mo)
        self.z_stunden = QDoubleSpinBox()
        self.z_stunden.setRange(0.5, 100)
        self.z_stunden.setDecimals(1)
        self.z_stunden.setValue(8)
        self.z_stunden.setSuffix(" h")
        k_z = QPushButton("Zusatzstunden eintragen")
        k_z.clicked.connect(lambda _=False: self.zusatz_setzen(
            self.z_maschine.currentText(), self.z_woche.currentData(), self.z_stunden.value()))
        self.a_auftrag = QComboBox()
        self.einteilig = {a["id"]: a for a in f.ein["auftraege"]
                          if "gang" not in a and "teil" not in a and a.get("vorrang") != rechnung.LAEUFT_ZUERST}
        for a in sorted(self.einteilig.values(), key=lambda a: str(a["nummer"])):
            self.a_auftrag.addItem(f"{a['nummer']} {a.get('kunde') or ''} ({a['maschine']})".strip(), a["id"])
        self.a_maschine = QComboBox()
        self.a_maschine.addItems(maschinen)
        k_a = QPushButton("Auf diese Maschine legen")
        k_a.clicked.connect(lambda _=False: self.wechsel_setzen(self.a_auftrag.currentData(),
                                                                self.a_maschine.currentText()))
        self.annahmen = QTableWidget()
        self.annahmen.setColumnCount(2)
        self.annahmen.setHorizontalHeaderLabels(("Annahme", "Wert"))
        self.annahmen.verticalHeader().setVisible(False)
        self.annahmen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.annahmen.setMaximumHeight(130)
        self.annahmen.horizontalHeader().setStretchLastSection(True)
        k_weg = QPushButton("Annahme entfernen")
        k_weg.clicked.connect(lambda _=False: self.entfernen())
        self.ergebnis = QLabel("")
        self.ergebnis.setWordWrap(True)
        self.tabelle = QTableWidget()
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.fehler = QLabel("")
        self.fehler.setStyleSheet(f"color: {stil.umsetzen(stil.ROT)};")
        self.fehler.setWordWrap(True)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        self.knoepfe.button(QDialogButtonBox.Apply).setText("Übernehmen")
        self.knoepfe.button(QDialogButtonBox.Close).setText("Schließen")
        self.knoepfe.button(QDialogButtonBox.Apply).clicked.connect(lambda _=False: self.uebernehmen())
        self.knoepfe.rejected.connect(self.reject)
        form = QFormLayout()
        form.addRow("Samstag", self.samstag)
        z1 = QHBoxLayout()
        for w in (self.z_maschine, self.z_woche, self.z_stunden, k_z):
            z1.addWidget(w)
        z1.addStretch(1)
        form.addRow("Zusatzstunden", z1)
        z2 = QHBoxLayout()
        z2.addWidget(self.a_auftrag, 1)
        z2.addWidget(QLabel("auf"))
        z2.addWidget(self.a_maschine)
        z2.addWidget(k_a)
        form.addRow("Andere Maschine", z2)
        z3 = QHBoxLayout()
        z3.addWidget(k_weg)
        z3.addStretch(1)
        hinweis = QLabel("Hier wird nur gerechnet. Erst „Übernehmen“ speichert die Annahmen. Ein Auftrag auf einer "
                         "anderen Maschine rechnet mit derselben Laufzeit.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.annahmen)
        lay.addLayout(z3)
        lay.addWidget(self.ergebnis)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(hinweis)
        lay.addWidget(self.fehler)
        lay.addWidget(self.knoepfe)
        self.samstag.valueChanged.connect(lambda _w: self.rechnen())
        self.resize(860, 640)
        self.rechnen()

    def zusatz_setzen(self, maschine, montag, stunden):
        if maschine and montag is not None:
            self.zusatz[(maschine, montag)] = float(stunden)
            self.rechnen()

    def wechsel_setzen(self, auftrag_id, maschine):
        a = self.einteilig.get(auftrag_id)
        if a is None:
            return
        if maschine == a["maschine"]:
            self.wechsel.pop(auftrag_id, None)
        elif not rechnung.passt(self.f.aus, a, maschine):
            QMessageBox.information(self, "Was wäre, wenn …", D.passt_nicht(
                self.f.aus["eignung"].get(maschine), a.get("durchmesser"), a.get("laenge")))
            return
        else:
            self.wechsel[auftrag_id] = maschine
        self.rechnen()

    def entfernen(self, zeile=None):
        r = self.annahmen.currentRow() if zeile is None else zeile
        z = self.annahmen.item(r, 0) if r >= 0 else None
        art, key = z.data(Qt.UserRole) if z is not None else (None, None)
        if art == "zusatz":
            self.zusatz.pop(key, None)
        elif art == "wechsel":
            self.wechsel.pop(key, None)
        self.rechnen()

    def probe(self):
        return rechnung.Probe(samstag=self.samstag.value(), zusatz=self.zusatz, maschine=self.wechsel)

    def rechnen(self):
        f = self.f
        zeilen = [(("zusatz", k), f"Zusatzstunden {k[0]}, KW {k[1].isocalendar()[1]}", f"+{h:g} h".replace(".", ","))
                  for k, h in sorted(self.zusatz.items())]
        zeilen += [(("wechsel", i), f"Auftrag {self.einteilig[i]['nummer']}", f"{self.einteilig[i]['maschine']} → {m}")
                   for i, m in self.wechsel.items()]
        self.annahmen.setRowCount(len(zeilen))
        for r, (key, name, wert) in enumerate(zeilen):
            self.annahmen.setItem(r, 0, _zelle(name, daten=key))
            self.annahmen.setItem(r, 1, _zelle(wert))
        self.annahmen.resizeColumnsToContents()
        self.annahmen.horizontalHeader().setStretchLastSection(True)
        self.neu = rechnung.rechnen(f.aus, int(f.db.zahl("schwelle_tage", 2)), probe=self.probe())
        self.diff = rechnung.vergleich(f.ein, self.neu)
        alt, neu = f.ein["risiko"], self.neu["risiko"]
        besser = sum(1 for x in self.diff if (x["tage"] or 0) < 0)
        schlechter = sum(1 for x in self.diff if (x["tage"] or 0) > 0)
        self.ergebnis.setText(
            f"<b>Terminrisiko: nicht zu halten {alt[einlastung.UEBER]} → {neu[einlastung.UEBER]}, knapp "
            f"{alt[einlastung.KNAPP]} → {neu[einlastung.KNAPP]}.</b> {besser} Aufträge werden früher fertig, "
            f"{schlechter} später." if self.diff else "Mit diesen Annahmen ändert sich kein Fertig-Tag.")
        kopf = ("Auftragsnummer", "Kunde", "Maschine", "Fertig jetzt", "Fertig dann", "Unterschied", "Terminrisiko")
        self.tabelle.setColumnCount(len(kopf))
        self.tabelle.setHorizontalHeaderLabels(kopf)
        self.tabelle.setRowCount(len(self.diff))
        for r, x in enumerate(self.diff):
            n = abs(x["tage"] or 0)
            tage = "" if x["tage"] is None else "gleich" if not n else (
                f"{n} {'Tag' if n == 1 else 'Tage'} {'früher' if x['tage'] < 0 else 'später'}")
            risiko = (RISIKO_TEXT.get(x["risiko_neu"], "") if x["risiko_alt"] == x["risiko_neu"] else
                      f"{RISIKO_TEXT.get(x['risiko_alt'], '')} → {RISIKO_TEXT.get(x['risiko_neu'], '')}")
            werte = [_zelle(x["nummer"]), _zelle(x["kunde"]), _zelle(x["maschine"] or D.FREMD_TEXT),
                     _zelle(_wtag(x["fertig_alt"]) or "später"), _zelle(_wtag(x["fertig_neu"]) or "später"),
                     _zelle(tage), _zelle(risiko)]
            for c, z in enumerate(werte):
                self.tabelle.setItem(r, c, z)
            if x["risiko_alt"] != x["risiko_neu"]:
                farbe = stil.ROT_FLAECHE if x["schlechter"] > 0 else stil.GRUEN_FLAECHE
                werte[6].setBackground(stil.farbe(farbe))
                werte[6].setForeground(stil.farbe(stil.TEXT))
        self.tabelle.resizeColumnsToContents()
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        return self.diff

    def uebernehmen(self):
        """Annahmen speichern: Samstag und Zusatzstunden als Einstellung, Aufträge auf ihre neue Maschine."""
        db = self.f.db
        if not self.f.darf("auftraege"):
            self.fehler.setText("Übernehmen darf nur Planung oder Verwaltung.")
            return False
        samstag_neu = abs(self.samstag.value() - db.zahl("samstag_stunden")) > 1e-9
        if samstag_neu and not db.darf("einstellungen"):
            self.fehler.setText("Die Samstagsstunden ändert nur die Rolle Verwaltung.")
            return False
        try:
            for auftrag_id, maschine in self.wechsel.items():
                db.maschine_wechseln(auftrag_id, maschine)
        except D.Fehler as e:
            self.fehler.setText(str(e))
            return False
        if samstag_neu:
            db.einstellung_setzen("samstag_stunden", self.samstag.value())
        if self.zusatz != (self.f.aus.get("zusatz") or {}):
            db.zusatzstunden_setzen(self.zusatz)
        self.f.laden()
        self.accept()
        return True


class Hauptfenster(QMainWindow):
    def __init__(self, db, heute=None, platz=None, werkstatt=None, programmordner=None):
        """platz: Ordner der Auslastung.ini dieses Platzes (Vorgabe neben dem Programm); werkstatt: True startet in
        der Werkstatt-Ansicht (Vorgabe: wie an diesem Platz gemerkt); programmordner: Ordner des fertigen Programms
        für das Online-Update (None beim Start aus dem Quelltext: kein Update)."""
        super().__init__()
        self.db, self.heute_fest, self.platz = db, heute, platz
        self.updater = aktualisierung_fenster.Updater(self, programmordner)
        self.aus = self.ein = self.gem = None
        self.rueck, self.vorschlag = None, {}     # letztes Verschieben (für Rückgängig), Ausweichmaschinen
        self.woche = None                         # im Wochenbalken gewählte (Maschine, Montag)
        self.setWindowTitle(f"{NAME} {VERSION}")
        self.resize(1320, 820)
        self.reiter = QTabWidget()
        self.stapel = QStackedWidget()            # Planung (Reiter) oder Werkstatt-Ansicht (E4)
        self.setCentralWidget(self.stapel)
        self.stapel.addWidget(self.reiter)
        self.stapel.addWidget(self._seite_werkstatt())
        self.k_werkstatt = QPushButton("Werkstatt-Ansicht")
        self.k_werkstatt.setToolTip("Große Ansicht für den Platz an der Maschine: Maschine wählen, die nächsten "
                                    "Aufträge in großer Schrift, große Knöpfe Start, Stopp und Fertig.")
        self.k_werkstatt.clicked.connect(lambda _=False: self.werkstatt_an(True))
        self.reiter.setCornerWidget(self.k_werkstatt, Qt.TopRightCorner)
        self.reiter.addTab(self._seite_auftraege(), "Aufträge")
        self.reiter.addTab(self._seite_auslastung(), "Auslastung")
        self.reiter.addTab(self._seite_soll_ist(), "Soll und Ist")
        self.reiter.addTab(self._seite_kennzahlen(), "Kennzahlen")
        self.reiter.addTab(self._seite_einstellungen(), "Einstellungen")
        self.reiter.addTab(self._seite_hilfe(), "Hilfe")
        self.reiter.currentChanged.connect(lambda _i: self.laden())
        self.statusBar().showMessage(f"Datenbank: {db.pfad}")
        self.wer_zeile = QLabel("")               # Benutzer und Rolle, steht dauerhaft rechts unten
        self.statusBar().addPermanentWidget(self.wer_zeile)
        self.stand = db.stand()
        self.uhr = QTimer(self)                   # anderer Platz hat gespeichert, oder eine Start/Stopp-Uhr läuft
        self.uhr.timeout.connect(self.takt)
        self.uhr.start(5000)
        self.laden()
        self.uebergabe_pruefen()
        if werkstatt or (werkstatt is None and ort.ini_lesen(self.platz).get("werkstatt") == "1"):
            self.werkstatt_an(True)

    def heute(self):
        return self.heute_fest or datetime.date.today()

    def form(self):
        return self.db.einstellung("laufzeit_form")

    def lz(self, minuten):
        return laufzeit.text(minuten, self.form())

    def meldung(self, text):
        QMessageBox.warning(self, NAME, text)

    def hinweis(self, text):
        """Kurze Nachricht unten im Fenster (ohne Dialog)."""
        self.statusBar().showMessage(text, 10000)

    def darf(self, recht):
        """Benutzerrechte (Plan B): True, wenn die Rolle dieses Platzes das Recht hat; sonst Hinweis unten."""
        if self.db.darf(recht):
            return True
        self.statusBar().showMessage(f"Dafür reicht die Rolle „{D.ROLLE_TEXT[self.db.rolle()]}“ nicht.", 6000)
        return False

    def rechte_setzen(self):
        """Knöpfe und Reiter sperren, die die Rolle nicht darf; Name und Rolle unten im Fenster."""
        rolle = self.db.rolle()
        planen, verwalten = self.db.darf("auftraege"), self.db.darf("einstellungen")
        self.k_neu.setEnabled(planen)
        self.a_csv_ein.setEnabled(planen)
        self.a_papierkorb.setEnabled(planen)
        self.reiter.setTabEnabled(EINSTELLUNGEN, verwalten)
        self.reiter.setTabToolTip(EINSTELLUNGEN, "" if verwalten else "Einstellungen ändert nur die Rolle Verwaltung.")
        if not verwalten and self.reiter.currentIndex() == EINSTELLUNGEN:
            self.reiter.setCurrentIndex(0)
        if self.db.rechte_an():
            self.wer_zeile.setText(f"Benutzer: {self.db.wer or 'unbekannt'} ({D.ROLLE_TEXT[rolle]})")
        else:
            self.wer_zeile.setText("")

    def takt(self):
        neu = self.db.stand()
        if neu != self.stand or self.db.uhr_laeuft():
            self.stand = neu
            if not QApplicationModal():
                self.laden()
        self.takte = getattr(self, "takte", 0) + 1
        if self.takte % 12 == 0 and not QApplicationModal():       # etwa jede Minute: neue Übergabe im Ordner?
            self.uebergabe_pruefen()

    # ------------------------------------------------------------------ Übergabe-Ordner (E9)
    def uebergabe_pruefen(self):
        """Schaut in den Übergabe-Ordner. Eine neue Datei, die nichts Neues bringt, gilt gleich als erledigt; sonst
        erscheint über der Auftragsliste eine Zeile mit „Einlesen …“. Ergebnis: die anstehende Datei oder None."""
        self.ueb_datei, self.ueb_ergebnis = None, None
        if self.db.darf("auftraege"):
            for pfad in austausch.neue_dateien(self.db):
                try:
                    ergebnis = austausch.lesen(self.db, pfad)
                except (OSError, IndexError, ValueError):
                    continue                      # wird vielleicht gerade geschrieben: beim nächsten Mal wieder
                if ergebnis["neu"] or ergebnis["geaendert"] or ergebnis["fehler"]:
                    self.ueb_datei, self.ueb_ergebnis = pfad, ergebnis
                    break
                austausch.gelesen_merken(self.db, pfad)
        if self.ueb_datei is None:
            self.ueb_zeile.setVisible(False)
            return None
        e = self.ueb_ergebnis
        teile = [f"{len(e['neu'])} neue Aufträge" if len(e["neu"]) != 1 else "1 neuer Auftrag",
                 f"{len(e['geaendert'])} geänderte" if len(e["geaendert"]) != 1 else "1 geänderter"]
        if e["fehler"]:
            teile.append(f"{len(e['fehler'])} Zeilen mit Fehler" if len(e["fehler"]) != 1 else "1 Zeile mit Fehler")
        self.ueb_text.setText(f"<b>Neue Übergabe aus der Kalkulation:</b> {self.ueb_datei.name} · " + ", ".join(teile))
        self.ueb_zeile.setVisible(True)
        return self.ueb_datei

    def uebergabe_einlesen(self, fragen=True):
        """Knopf „Einlesen …“: die übliche Rückfrage mit der Zusammenfassung, dann übernehmen."""
        pfad = self.ueb_datei
        if pfad is None:
            return None
        ergebnis = self.csv_einlesen(pfad, fragen=fragen)
        if ergebnis is not None:                  # None = bei der Rückfrage abgelehnt: die Zeile bleibt stehen
            austausch.gelesen_merken(self.db, pfad)
            self.uebergabe_pruefen()
        return ergebnis

    def uebergabe_ablehnen(self):
        """Knopf „Nicht einlesen“: die Datei gilt als erledigt, bis die Kalkulation sie neu schreibt."""
        if self.ueb_datei is not None:
            austausch.gelesen_merken(self.db, self.ueb_datei)
            self.uebergabe_pruefen()

    # ------------------------------------------------------------------ Aufträge
    def _seite_auftraege(self):
        w = QWidget()
        self.filter = QComboBox()
        self.filter.addItems(FILTER)
        self.filter.currentIndexChanged.connect(lambda _i: self.auftraege_zeigen())
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Auftragsnummer, Kunde, Maschine, Bemerkung")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(lambda _t: self.auftraege_zeigen())
        self.k_neu = QPushButton("Neuer Auftrag …")
        self.k_neu.setObjectName("primaer")
        self.k_aendern = QPushButton("Ändern …")
        self.k_uhr = QPushButton("Start")
        self.k_fertig = QPushButton("Fertig melden …")
        self.k_fertig.setToolTip("Auftrag fertig melden (F8). Ohne Auswahl in der Liste: Auftragsnummer tippen, Enter, "
                                 "Laufzeit prüfen, Enter. Mit Auswahl ist der Auftrag schon eingetragen.")
        self.k_fertig.setShortcut("F8")
        self.k_oeffnen = QPushButton("Wieder öffnen")
        self.k_reihe = QPushButton("Reihenfolge")
        self.k_loeschen = QPushButton("Löschen")
        self.k_mehr = QPushButton("Mehr")
        self.k_uhr.setToolTip("Startet die Uhr für den gewählten Auftrag, ein zweiter Klick hält sie an. Die gestoppte "
                              "Zeit steht in der Spalte Status und wird bei der Fertigmeldung als tatsächliche "
                              "Laufzeit vorgeschlagen.")
        self.k_reihe.setToolTip("Normal laufen die Aufträge einer Maschine nach Liefertermin. Vorziehen stellt den "
                                "gewählten Auftrag an den Anfang, Zurückstellen ans Ende.")
        self.k_loeschen.setToolTip(f"Legt den Auftrag in den Papierkorb (Mehr → Papierkorb); dort bleibt er "
                                   f"{D.PAPIERKORB_TAGE} Tage und lässt sich zurückholen.")
        menue = QMenu(self.k_reihe)
        self.a_vor = menue.addAction("Vorziehen (läuft als Nächstes)", lambda: self.reihenfolge(1))
        self.a_zurueck = menue.addAction("Zurückstellen (läuft zuletzt)", lambda: self.reihenfolge(-1))
        self.a_termin = menue.addAction("Wieder nach Liefertermin", lambda: self.reihenfolge(0))
        self.a_loesen = menue.addAction("Festen Platz lösen", lambda: self.platz_loesen())
        self.k_reihe.setMenu(menue)
        mehr = QMenu(self.k_mehr)
        self.a_csv_ein = mehr.addAction("CSV einlesen …", lambda: self.csv_einlesen())
        mehr.addAction("CSV speichern …", lambda: self.csv_speichern())
        mehr.addSeparator()
        self.a_verlauf = mehr.addAction("Änderungsverlauf …", lambda: self.verlauf())
        self.a_papierkorb = mehr.addAction("Papierkorb …", lambda: self.papierkorb())
        self.k_mehr.setMenu(mehr)
        for k, f in ((self.k_neu, self.neu), (self.k_aendern, self.aendern), (self.k_uhr, self.uhr_schalten),
                     (self.k_fertig, self.fertig_melden), (self.k_oeffnen, self.wieder_oeffnen),
                     (self.k_loeschen, self.loeschen)):
            k.clicked.connect(lambda _=False, f=f: f())
        oben = QHBoxLayout()
        oben.addWidget(self.filter)
        oben.addWidget(self.suche, 1)
        knoepfe = QHBoxLayout()
        for k in (self.k_neu, self.k_aendern, self.k_uhr, self.k_fertig, self.k_oeffnen, self.k_reihe, self.k_loeschen):
            knoepfe.addWidget(k)
        knoepfe.addStretch(1)
        knoepfe.addWidget(self.k_mehr)
        self.liste = QTableWidget()
        self.liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.liste.setSelectionMode(QAbstractItemView.SingleSelection)
        self.liste.setAlternatingRowColors(True)
        self.liste.verticalHeader().setVisible(False)
        self.liste.setSortingEnabled(True)
        self.liste.itemSelectionChanged.connect(self.knoepfe_setzen)
        self.liste.itemDoubleClicked.connect(lambda _i: self.aendern())
        self.summe = QLabel("")
        # E9: neue Übergabe aus der Kalkulation im Ordner gefunden
        self.ueb_datei, self.ueb_ergebnis = None, None
        self.ueb_zeile = QFrame()
        self.ueb_zeile.setStyleSheet(f"QFrame {{ background: {stil.umsetzen(stil.BLAU_FLAECHE)}; border-radius: 4px; }}"
                                     f" QLabel {{ color: {stil.umsetzen(stil.TEXT)}; }}")
        self.ueb_text = QLabel("")
        self.k_ueb_ein = QPushButton("Einlesen …")
        self.k_ueb_nein = QPushButton("Nicht einlesen")
        self.k_ueb_ein.clicked.connect(lambda _=False: self.uebergabe_einlesen())
        self.k_ueb_nein.clicked.connect(lambda _=False: self.uebergabe_ablehnen())
        ul = QHBoxLayout(self.ueb_zeile)
        ul.setContentsMargins(10, 6, 10, 6)
        ul.addWidget(self.ueb_text, 1)
        ul.addWidget(self.k_ueb_ein)
        ul.addWidget(self.k_ueb_nein)
        self.ueb_zeile.setVisible(False)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addLayout(knoepfe)
        lay.addWidget(self.ueb_zeile)
        lay.addWidget(self.liste, 1)
        lay.addWidget(self.summe)
        return w

    def gewaehlt(self):
        """Der in der Liste gewählte Auftrag (frisch aus der Datenbank) oder None."""
        r = self.liste.currentRow()
        z = self.liste.item(r, 0) if r >= 0 else None
        return self.db.auftrag(z.data(Qt.UserRole)) if z is not None else None

    def waehlen(self, auftrag_id):
        for r in range(self.liste.rowCount()):
            if self.liste.item(r, 0).data(Qt.UserRole) == auftrag_id:
                self.liste.selectRow(r)
                return True
        return False

    def auftraege_zeigen(self):
        alt = self.gewaehlt()
        status = {0: (D.OFFEN, D.LAEUFT), 1: (D.FERTIG,), 2: None}[self.filter.currentIndex()]
        such = self.suche.text().strip().lower()
        plan = (self.ein or {}).get("plan", {})
        felder = [f["name"] for f in self.db.zusatzfelder()]
        gaenge_an = self.db.mit_gaengen()
        kopf = ["Auftragsnummer", "Kunde", "Maschine", "Kalkulierte Laufzeit", "Liefertermin", "Status",
                "Fertig (Plan)" if gaenge_an else "Laser fertig (Plan)", "Terminrisiko", "Tatsächliche Laufzeit",
                "Abweichung", "Fertig am", "Bemerkung", "Durchlaufzeit (Plan)", "Material (Rüsten)"] + felder
        self.liste.setSortingEnabled(False)
        self.liste.setColumnCount(len(kopf))
        self.liste.setHorizontalHeaderLabels(kopf)
        zeilen = []
        for a in self.db.auftraege(status):
            if such and such not in " ".join([a["nummer"], a["kunde"], a["maschine"], a["bemerkung"],
                                              a.get("material") or ""]
                                             + list(a["zusatz"].values())).lower():
                continue
            zeilen.append(a)
        self.liste.setRowCount(len(zeilen))
        offen_min = 0
        for r, a in enumerate(zeilen):
            p = plan.get(a["id"], {})
            diff, prozent = rechnung.abweichung(a["kalk_min"], a["ist_min"])
            status_text = a["status"]
            if a["status"] != D.FERTIG and a["gaenge"]:
                offene = [g for g in a["gaenge"] if g["status"] != D.FERTIG]
                offen_min += sum(max(0, g["kalk_min"] - self.db.gelaufen(g)) for g in offene if g["platz"])
                jetzt = self.db.bereit(a["gaenge"])
                status_text += (f": {len(a['gaenge']) - len(offene)} von {len(a['gaenge'])} fertig, jetzt "
                                + " + ".join(g["name"] for g in jetzt))
                gelaufen = sum(self.db.gelaufen(g) for g in jetzt if g["platz"])
                laeuft = any(g["start_am"] for g in jetzt)
                if gelaufen or laeuft:
                    status_text += f" ({self.lz(gelaufen)}" + (", Uhr läuft)" if laeuft else ")")
                if a["vorrang"]:
                    status_text += ", vorgezogen" if a["vorrang"] > 0 else ", zurückgestellt"
                if a["fest_ab"]:
                    status_text += f", fest ab {_tag(a['fest_ab'])}"
            elif a["status"] != D.FERTIG:
                gelaufen = self.db.gelaufen(a)
                offen_min += max(0, a["kalk_min"] - gelaufen)
                if gelaufen or a["start_am"]:
                    grund = "" if a["start_am"] else self.db.offener_stopp(a["id"])
                    status_text += f" ({self.lz(gelaufen)}" + (", Uhr läuft)" if a["start_am"] else
                                                                 f", gestoppt: {grund})" if grund else ")")
                if a["vorrang"]:
                    status_text += ", vorgezogen" if a["vorrang"] > 0 else ", zurückgestellt"
                if a["fest_ab"]:
                    status_text += f", fest ab {_tag(a['fest_ab'])}"
            material = self.db.wartet_auf_material(a, self.heute())
            if material:
                status_text += f", wartet auf Material (da ab {material.strftime('%d.%m.%Y')})"
            abw = "" if diff is None else f"{'+' if diff > 0 else ''}{self.lz(diff)}" + (
                f" ({prozent:+.0f} %)".replace(".", ",") if prozent is not None else "")
            risiko = RISIKO_TEXT.get(p.get("risiko"), "") if a["status"] != D.FERTIG else ""
            termin_text, termin_tipp = _tag(a["liefertermin"]), ""
            if a.get("lieferungen"):              # A5: nächste offene Teillieferung, alle im Hinweis
                offene = {t["teil"]: t for t in p.get("teile") or ()}
                zeilen_t = []
                for n, x in enumerate(a["lieferungen"], start=1):
                    t = offene.get(n)
                    zeilen_t.append(f"{n}. {_tag(x['termin'])}: {D.mm_text(x['menge'])} Stück" + (
                        " (fertig)" if a["status"] == D.FERTIG or (t is None and p.get("teile")) else
                        f", Laser fertig {_tag(t['fertig']) or 'später'}, {RISIKO_TEXT.get(t['risiko'], '')}"
                        if t else ""))
                termin_tipp = "Teillieferungen:\n" + "\n".join(zeilen_t)
                naechste = min(offene) if offene and a["status"] != D.FERTIG else len(a["lieferungen"])
                termin_text = (f"{_tag(a['lieferungen'][naechste - 1]['termin'])} "
                               f"(Lieferung {naechste} von {len(a['lieferungen'])})")
            werte = [
                _zelle(a["nummer"], daten=a["id"]), _zelle(a["kunde"]), _zelle(a["maschine"]),
                _zelle(self.lz(a["kalk_min"]), True, sortier=a["kalk_min"]),
                _zelle(termin_text, sortier=a["liefertermin"] or "9999"), _zelle(status_text),
                _zelle(_tag(p.get("fertig")), sortier=str(p.get("fertig") or "9999")), _zelle(risiko),
                _zelle(self.lz(a["ist_min"]), True, sortier=a["ist_min"] or 0),
                _zelle(abw, True, sortier=diff if diff is not None else 0),
                _zelle(" ".join(t for t in (_tag(a["fertig_am"]), a.get("fertig_um") or "") if t),
                       sortier=(a["fertig_am"] or "") + (a.get("fertig_um") or "")), _zelle(a["bemerkung"]),
                _zelle(_arbeitstage(p["durchlauf"]) if p.get("durchlauf") and a["status"] != D.FERTIG else "",
                       True, sortier=p.get("durchlauf") or 0),
                _zelle(a.get("material") or ""),
            ] + [_zelle(a["zusatz"].get(n, "")) for n in felder]
            if termin_tipp:
                werte[4].setToolTip(termin_tipp)
            for c, z in enumerate(werte):
                self.liste.setItem(r, c, z)
            farbe = RISIKO_FARBE.get(p.get("risiko")) if a["status"] != D.FERTIG else None
            if farbe:
                werte[7].setBackground(stil.farbe(farbe))
                werte[7].setForeground(stil.farbe(stil.TEXT))
        for c in (6, 7):                          # Plan nur bei offenen, Ist nur bei fertigen Aufträgen
            self.liste.setColumnHidden(c, self.filter.currentIndex() == 1)
        for c in (8, 9, 10):
            self.liste.setColumnHidden(c, self.filter.currentIndex() == 0)
        self.liste.setColumnHidden(12, not gaenge_an or self.filter.currentIndex() == 1)
        self.liste.setColumnHidden(13, not any(a.get("material") for a in zeilen))
        self.liste.setSortingEnabled(True)
        self.liste.resizeColumnsToContents()
        self.liste.horizontalHeader().setSectionResizeMode(11, QHeaderView.Stretch)
        self.summe.setText(f"{len(zeilen)} Aufträge" + (f", noch {self.lz(offen_min)} offene Laufzeit"
                                                        if offen_min else ""))
        if alt is None or not self.waehlen(alt["id"]):
            self.liste.clearSelection()
            self.liste.setCurrentCell(-1, -1)
        self.knoepfe_setzen()

    def knoepfe_setzen(self):
        a = self.gewaehlt()
        offen = a is not None and a["status"] != D.FERTIG
        fertig = a is not None and a["status"] == D.FERTIG
        planen, melden = self.db.darf("auftraege"), self.db.darf("melden")
        self.k_aendern.setEnabled(a is not None and planen)
        bereit = self.db.bereit(a["gaenge"]) if offen and a["gaenge"] else []
        if len(bereit) > 1:                       # mehrere Zeilen gleichzeitig an der Reihe: der Knopf fragt nach
            self.k_uhr.setText("Start / Stopp …")
        else:
            self.k_uhr.setText("Stopp" if offen and (bereit[0]["start_am"] if bereit else a["start_am"]) else "Start")
        for k, recht in ((self.k_uhr, melden), (self.k_reihe, planen)):
            k.setEnabled(offen and recht)
            k.setVisible(not fertig)                                # bei einem fertigen Auftrag: nur Wieder öffnen
        self.k_fertig.setEnabled(melden)          # ohne Auswahl: erst die Auftragsnummer suchen
        self.k_fertig.setVisible(not fertig)
        teilweise = offen and any(g["status"] == D.FERTIG for g in a["gaenge"])
        self.k_oeffnen.setVisible(fertig or teilweise)
        self.k_oeffnen.setText("Letzten Arbeitsgang wieder öffnen" if a is not None and a["gaenge"] else
                               "Wieder öffnen")
        self.k_oeffnen.setEnabled(melden)
        self.a_termin.setEnabled(offen and bool(a["vorrang"]))
        self.a_loesen.setEnabled(offen and bool(a["fest_ab"]))
        self.k_loeschen.setEnabled(a is not None and planen)
        self.a_verlauf.setEnabled(a is not None)

    def neu(self, zeigen=True):
        if not self.darf("auftraege"):
            return None
        d = AuftragDialog(self.db, parent=self)
        if zeigen and d.exec() == QDialog.Accepted:
            self.laden()
            self.waehlen(d.auftrag["id"])
        return d

    def aendern(self, auftrag_id=None, zeigen=True):
        a = self.db.auftrag(auftrag_id) if auftrag_id is not None else self.gewaehlt()
        if a is None or not self.darf("auftraege"):
            return None
        d = AuftragDialog(self.db, a, self)
        if zeigen and d.exec() == QDialog.Accepted:
            self.laden()
        return d

    def gang_waehlen(self, a, titel, gang_id=None):
        """Arbeitsgang eines mehrteiligen Auftrags, der jetzt an der Reihe ist. Sind es mehrere (gleichzeitig), fragt
        ein kleiner Dialog; gang_id überspringt ihn (Tests)."""
        bereit = self.db.bereit(a["gaenge"])
        if gang_id is not None:
            return next((g for g in bereit if g["id"] == gang_id), None)
        if len(bereit) <= 1:
            return bereit[0] if bereit else None
        namen = [f"{g['name']} ({g['platz'] or 'Fremdarbeit'})" + (", Uhr läuft" if g["start_am"] and g["platz"] else
                                                                  ", gestartet" if g["start_am"] else "")
                 for g in bereit]
        wahl, ok = QInputDialog.getItem(self, f"Auftrag {a['nummer']}", titel, namen, 0, False)
        return bereit[namen.index(wahl)] if ok else None

    def stopp_grund(self, titel, grund=None, gross=False):
        """Grund bei Stopp (E6): fragt mit einem Klick-Dialog, wenn es in den Einstellungen eingeschaltet ist.
        Ergebnis: Grund, "" = ohne Grund, None = abgebrochen. grund vorgegeben (auch ""): keine Frage (Tests)."""
        if grund is not None:
            return grund
        if self.db.einstellung("stopp_fragen") != "1" or not self.db.stoppgruende():
            return ""
        d = StoppDialog(self.db, titel, self, gross)
        return d.grund if d.exec() == QDialog.Accepted else None

    def _uhr(self, a, g=None, grund=None, gross=False):
        """Start oder Stopp für den Auftrag a bzw. seinen Arbeitsgang g; beim Stopp mit Grund."""
        teil = g if g is not None else a
        gang_id = g["id"] if g is not None else None
        try:
            if teil["start_am"]:
                fragen = g is None or g["platz"] != D.FREMD           # Fremdarbeit hat keine Uhr, also keinen Grund
                grund = self.stopp_grund(f"Auftrag {a['nummer']} stoppen", grund, gross) if fragen else ""
                if grund is None:
                    return False
                self.db.stoppen(a["id"], gang_id=gang_id, grund=grund or None)
            else:
                self.db.starten(a["id"], gang_id=gang_id)
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        return True

    def uhr_schalten(self, gang_id=None, grund=None):
        """Ein Knopf für Start und Stopp (P1)."""
        a = self.gewaehlt()
        if a is None or a["status"] == D.FERTIG or not self.darf("melden"):
            return
        g = None
        if a["gaenge"]:
            g = self.gang_waehlen(a, "Welche Zeile starten oder stoppen?", gang_id)
            if g is None:
                return
        self._uhr(a, g, grund)
        self.laden()

    # ------------------------------------------------------------------ Werkstatt-Ansicht (E4)
    def _seite_werkstatt(self):
        """Ansicht für das Tablet oder den Hallen-PC: Maschine wählen, die nächsten Aufträge in großer Schrift,
        große Knöpfe Start, Stopp und Fertig. Ein Gerät genügt für alle Maschinen (F2a)."""
        w = self.werkstatt = QWidget()
        w.setObjectName("werkstatt")
        f = stil.umsetzen
        w.setStyleSheet(
            "#werkstatt QLabel, #werkstatt QTableWidget, #werkstatt QCheckBox { font-size: 15pt; }"
            "#werkstatt QHeaderView::section { font-size: 12pt; padding: 6px; }"
            "#werkstatt QPushButton { font-size: 15pt; min-height: 46px; padding: 4px 18px; }"
            f"#werkstatt QPushButton:checked {{ background: {f(stil.AKZENT)}; color: white; font-weight: 600; }}"
            "#werkstatt QLabel#w_nummer { font-size: 30pt; font-weight: 700; }"
            "#werkstatt QLabel#w_zustand { font-size: 18pt; font-weight: 600; }"
            "#werkstatt QPushButton#w_start, #werkstatt QPushButton#w_stopp, #werkstatt QPushButton#w_fertig "
            "{ font-size: 24pt; font-weight: 700; min-height: 96px; color: white; border-radius: 8px; }"
            f"#werkstatt QPushButton#w_start {{ background: {f(stil.GRUEN)}; }}"
            f"#werkstatt QPushButton#w_stopp {{ background: {f(stil.ROT)}; }}"
            f"#werkstatt QPushButton#w_fertig {{ background: {f(stil.AKZENT)}; }}"
            f"#werkstatt QPushButton#w_start:disabled, #werkstatt QPushButton#w_stopp:disabled, "
            f"#werkstatt QPushButton#w_fertig:disabled {{ background: {f(stil.RAHMEN)}; color: {f(stil.TEXT_GRAU)}; }}"
            f"#werkstatt QFrame#w_karte {{ border: 1px solid {f(stil.RAHMEN)}; border-radius: 8px; }}")
        self.w_maschine, self.w_wahl, self.w_zeilen, self.w_knoepfe = None, None, [], {}
        self.w_plaetze = QHBoxLayout()
        self.k_w_zurueck = QPushButton("Zur Planung")
        self.k_w_voll = QPushButton("Vollbild")
        self.k_w_voll.setCheckable(True)
        self.w_immer = QCheckBox("An diesem Platz immer so starten")
        self.k_w_zurueck.clicked.connect(lambda _=False: self.werkstatt_an(False))
        self.k_w_voll.toggled.connect(lambda an: self.showFullScreen() if an else self.showNormal())
        self.w_immer.toggled.connect(lambda an: self._platz_merken("werkstatt", "1" if an else None))
        oben = QHBoxLayout()
        oben.addLayout(self.w_plaetze)
        oben.addStretch(1)
        oben.addWidget(self.w_immer)
        oben.addWidget(self.k_w_voll)
        oben.addWidget(self.k_w_zurueck)
        self.w_nummer, self.w_text, self.w_zustand = QLabel(""), QLabel(""), QLabel("")
        self.w_nummer.setObjectName("w_nummer")
        self.w_zustand.setObjectName("w_zustand")
        self.w_text.setWordWrap(True)
        karte = QFrame()
        karte.setObjectName("w_karte")
        kl = QVBoxLayout(karte)
        for x in (self.w_nummer, self.w_text, self.w_zustand):
            kl.addWidget(x)
        self.k_w_start, self.k_w_stopp, self.k_w_fertig = QPushButton("Start"), QPushButton("Stopp"), QPushButton(
            "Fertig")
        knoepfe = QHBoxLayout()
        for k, name, f_ in ((self.k_w_start, "w_start", self.werkstatt_start),
                            (self.k_w_stopp, "w_stopp", self.werkstatt_stopp),
                            (self.k_w_fertig, "w_fertig", self.werkstatt_fertig)):
            k.setObjectName(name)
            k.clicked.connect(lambda _=False, f_=f_: f_())
            knoepfe.addWidget(k, 1)
        self.w_liste = QTableWidget()
        self.w_liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.w_liste.setSelectionMode(QAbstractItemView.SingleSelection)
        self.w_liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.w_liste.setAlternatingRowColors(True)
        self.w_liste.verticalHeader().setVisible(False)
        self.w_liste.verticalHeader().setDefaultSectionSize(52)
        self.w_liste.itemSelectionChanged.connect(self._werkstatt_gewaehlt)
        self.w_summe = QLabel("")
        lay = QVBoxLayout(w)
        lay.setSpacing(12)
        lay.addLayout(oben)
        lay.addWidget(karte)
        lay.addLayout(knoepfe)
        lay.addWidget(self.w_liste, 1)
        lay.addWidget(self.w_summe)
        return w

    def _platz_merken(self, schluessel, wert):
        if getattr(self, "w_fuellt", False):
            return
        try:
            ort.merken(schluessel, wert, self.platz)
        except OSError:                           # Programmordner schreibgeschützt: gilt dann nur bis zum Schließen
            pass

    def werkstatt_ist_an(self):
        return self.stapel.currentWidget() is self.werkstatt

    def werkstatt_an(self, an=True):
        """Zwischen Planung (Reiter) und Werkstatt-Ansicht wechseln."""
        if not an and self.k_w_voll.isChecked():
            self.k_w_voll.setChecked(False)
        self.stapel.setCurrentWidget(self.werkstatt if an else self.reiter)
        self.laden()

    def werkstatt_maschine(self, name):
        """Maschine der Werkstatt-Ansicht wählen; dieser Platz merkt sie sich."""
        self.w_maschine, self.w_wahl = name, None
        self._platz_merken("maschine", name)
        self.werkstatt_zeigen()

    def werkstatt_daten(self, maschine):
        """Die offenen Aufträge bzw. Arbeitsgänge einer Maschine in der geplanten Reihenfolge, mit dem Zustand für
        die Werkstatt: [dict(id, gang, auftrag, teil, nummer, kunde, name, rest_min, termin, risiko, laeuft, bereit,
        zustand)]."""
        zeilen, teile = [], {}
        for e in rechnung.arbeitsliste(self.ein, maschine):
            if "teil" in e and e["id"] in teile:  # A5: weitere Teillieferungen zählen zur Zeile des Auftrags
                teile[e["id"]]["rest_min"] += int(e["h"] * 60 + 0.5)
                continue
            a = self.db.auftrag(e["id"])
            if a is None:
                continue
            g = next((x for x in a["gaenge"] if x["id"] == e.get("gang")), None)
            teil = g if g is not None else a
            dran = self.db.bereit(a["gaenge"]) if a["gaenge"] else []
            bereit = g is None or any(x["id"] == g["id"] for x in dran)
            gelaufen = self.db.gelaufen(teil)
            if teil["start_am"]:
                zustand = f"läuft seit {str(teil['start_am'])[11:16]} Uhr, bisher {self.lz(gelaufen)}"
            elif self.db.wartet_auf_material(a, self.heute()):
                zustand = f"wartet auf Material (da ab {_wtag(self.db.wartet_auf_material(a, self.heute()))})"
            elif not bereit:
                zustand = "wartet auf " + ", ".join(x["name"] for x in dran)
            else:
                grund = self.db.offener_stopp(a["id"], g["id"] if g is not None else None)
                zustand = (f"gestoppt nach {self.lz(gelaufen)}" + (f": {grund}" if grund else "")
                           if gelaufen or grund else "bereit")
            if "teil" in e:
                zustand += f" · Lieferung {e['teil']} von {e['teil_von']}: {D.mm_text(e.get('menge'))} Stück"
            zeilen.append(dict(id=a["id"], gang=g["id"] if g is not None else None, auftrag=a, teil=teil,
                               nummer=a["nummer"], kunde=a["kunde"], name=g["name"] if g is not None else "",
                               rest_min=int(e["h"] * 60 + 0.5), termin=e.get("termin_datum"), risiko=e.get("risiko"),
                               laeuft=bool(teil["start_am"]), bereit=bereit, zustand=zustand))
            if "teil" in e:
                teile[e["id"]] = zeilen[-1]
        return zeilen

    def werkstatt_zeigen(self):
        maschinen = list(self.ein["maschinen"])
        self.w_fuellt = True
        try:
            ini = ort.ini_lesen(self.platz)
            self.w_immer.setChecked(ini.get("werkstatt") == "1")
            if self.w_maschine not in maschinen:
                self.w_maschine = ini.get("maschine") if ini.get("maschine") in maschinen else (
                    maschinen[0] if maschinen else None)
            if list(self.w_knoepfe) != maschinen:                    # Knöpfe der Maschinen neu aufbauen
                for k in self.w_knoepfe.values():
                    k.setParent(None)
                self.w_knoepfe = {}
                for m in maschinen:
                    k = QPushButton(m)
                    k.setCheckable(True)
                    k.clicked.connect(lambda _=False, m=m: self.werkstatt_maschine(m))
                    self.w_plaetze.addWidget(k)
                    self.w_knoepfe[m] = k
            for m, k in self.w_knoepfe.items():
                k.setChecked(m == self.w_maschine)
            self.w_zeilen = self.werkstatt_daten(self.w_maschine) if self.w_maschine else []
            mit_gang = any(z["name"] for z in self.w_zeilen)
            kopf = ["Auftrag", "Kunde", "Arbeitsgang", "Restlaufzeit", "Liefertermin", "Zustand"]
            t = self.w_liste
            t.blockSignals(True)
            t.setColumnCount(len(kopf))
            t.setHorizontalHeaderLabels(kopf)
            t.setRowCount(len(self.w_zeilen))
            for r, z in enumerate(self.w_zeilen):
                for c, text in enumerate((z["nummer"], z["kunde"], z["name"], self.lz(z["rest_min"]),
                                          _wtag(z["termin"]), z["zustand"])):
                    zelle = _zelle(text, c == 3)
                    if c == 4 and z["risiko"] in RISIKO_FARBE:
                        zelle.setBackground(stil.farbe(RISIKO_FARBE[z["risiko"]]))
                        zelle.setForeground(stil.farbe(stil.TEXT))
                        zelle.setToolTip(RISIKO_TEXT.get(z["risiko"], ""))
                    if c == 5 and z["laeuft"]:
                        zelle.setBackground(stil.farbe(stil.GRUEN_FLAECHE))
                        zelle.setForeground(stil.farbe(stil.TEXT))
                    t.setItem(r, c, zelle)
            t.setColumnHidden(2, not mit_gang)
            t.horizontalHeader().setStretchLastSection(False)
            t.resizeColumnsToContents()
            t.horizontalHeader().setStretchLastSection(True)
            wahl = next((r for r, z in enumerate(self.w_zeilen) if (z["id"], z["gang"]) == self.w_wahl), None)
            if wahl is None and self.w_zeilen:    # Vorgabe: was läuft, sonst der nächste Auftrag der Reihenfolge
                wahl = next((r for r, z in enumerate(self.w_zeilen) if z["laeuft"]), 0)
            if wahl is not None:
                t.selectRow(wahl)
            t.blockSignals(False)
            gesamt = sum(z["rest_min"] for z in self.w_zeilen)
            self.w_summe.setText(f"{self.w_maschine}: {len(self.w_zeilen)} offene Aufträge, {self.lz(gesamt)}"
                                 if self.w_maschine else "Keine aktive Maschine.")
        finally:
            self.w_fuellt = False
        self._werkstatt_gewaehlt()

    def werkstatt_zeile(self):
        r = self.w_liste.currentRow()
        return self.w_zeilen[r] if 0 <= r < len(self.w_zeilen) else None

    def werkstatt_waehlen(self, auftrag_id, gang_id=None):
        for r, z in enumerate(self.w_zeilen):
            if (z["id"], z["gang"]) == (auftrag_id, gang_id):
                self.w_liste.selectRow(r)
                return True
        return False

    def _werkstatt_gewaehlt(self):
        z = self.werkstatt_zeile()
        melden = self.db.darf("melden")
        if z is None:
            self.w_wahl = None
            self.w_nummer.setText("Kein offener Auftrag" if self.w_maschine else "Keine aktive Maschine")
            self.w_text.setText("Auf dieser Maschine ist nichts eingeplant." if self.w_maschine else "")
            self.w_zustand.setText("")
        else:
            self.w_wahl = (z["id"], z["gang"])
            a = z["auftrag"]
            self.w_nummer.setText(" · ".join(x for x in (z["nummer"], z["kunde"]) if x))
            teile = ([z["name"]] if z["name"] else []) + [
                f"kalkuliert {self.lz(z['teil']['kalk_min'])}", f"Rest {self.lz(z['rest_min'])}"] + (
                [f"Liefertermin {_wtag(z['termin'])}"] if z["termin"] else [])
            self.w_text.setText(" · ".join(teile) + (f"\n{a['bemerkung']}" if a.get("bemerkung") else ""))
            self.w_zustand.setText(z["zustand"][:1].upper() + z["zustand"][1:])
            self.w_zustand.setStyleSheet(f"color: {stil.umsetzen(stil.GRUEN if z['laeuft'] else stil.TEXT_GRAU)};")
        self.k_w_start.setEnabled(bool(z) and melden and z["bereit"] and not z["laeuft"])
        self.k_w_stopp.setEnabled(bool(z) and melden and z["laeuft"])
        self.k_w_fertig.setEnabled(bool(z) and melden and z["bereit"])

    def _werkstatt_teil(self):
        """(Auftrag, Arbeitsgang oder None) der gewählten Zeile, frisch aus der Datenbank."""
        z = self.werkstatt_zeile()
        if z is None or not self.darf("melden"):
            return None, None
        a = self.db.auftrag(z["id"])
        if a is None or a["status"] == D.FERTIG:
            return None, None
        return a, next((g for g in a["gaenge"] if g["id"] == z["gang"]), None)

    def werkstatt_start(self):
        a, g = self._werkstatt_teil()
        if a is not None and not (g if g is not None else a)["start_am"]:
            self._uhr(a, g, gross=True)
            self.laden()

    def werkstatt_stopp(self, grund=None):
        a, g = self._werkstatt_teil()
        if a is not None and (g if g is not None else a)["start_am"]:
            self._uhr(a, g, grund, gross=True)
            self.laden()

    def werkstatt_fertig(self, zeigen=True):
        """Fertig: hält die Uhr an (ohne Grund, der Auftrag ist ja fertig) und fragt die tatsächliche Laufzeit."""
        a, g = self._werkstatt_teil()
        if a is None:
            return None
        if g is not None and not any(x["id"] == g["id"] for x in self.db.bereit(a["gaenge"])):
            self.meldung(f"„{g['name']}“ ist noch nicht an der Reihe.")
            return None
        if (g if g is not None else a)["start_am"] and (g is None or g["platz"]):
            self.db.stoppen(a["id"], gang_id=g["id"] if g is not None else None)
            a = self.db.auftrag(a["id"])
            g = next((x for x in a["gaenge"] if g is not None and x["id"] == g["id"]), None)
        d = FertigDialog(self.db, a, self, gang=g)
        d.setStyleSheet("QLabel, QPushButton, QLineEdit, QDateEdit { font-size: 15pt; }")
        if zeigen and d.exec() == QDialog.Accepted:
            self.laden()
        return d

    def reihenfolge(self, richtung):
        """Vorziehen (+1), zurückstellen (-1) oder wieder nach Liefertermin (0) (P4)."""
        a = self.gewaehlt()
        if a is None or a["status"] == D.FERTIG or not self.darf("auftraege"):
            return
        self.db.vorrang_setzen(a["id"], richtung)
        self.laden()

    def platz_loesen(self, auftrag_id=None):
        """Festen Platz aus der Plantafel lösen: Der Auftrag ordnet sich wieder nach Liefertermin ein."""
        a = self.db.auftrag(auftrag_id) if auftrag_id is not None else self.gewaehlt()
        if a is None or not a["fest_ab"] or not self.darf("auftraege"):
            return
        self.db.loesen(a["id"])
        self.laden()

    def papierkorb(self, zeigen=True):
        if not self.darf("auftraege"):
            return None
        d = PapierkorbDialog(self)
        if zeigen:
            d.exec()
        return d

    def verlauf(self, zeigen=True):
        """Änderungsverlauf des gewählten Auftrags (Plan B3): wer hat wann was geändert, gestartet, gemeldet."""
        a = self.gewaehlt()
        if a is None:
            return None
        d = QDialog(self)
        d.setWindowTitle(f"Änderungsverlauf Auftrag {a['nummer']}")
        d.liste = QTableWidget()
        d.liste.verticalHeader().setVisible(False)
        d.liste.setSelectionMode(QAbstractItemView.NoSelection)
        d.liste.setWordWrap(True)
        zeilen = self.db.verlauf(a["id"])
        d.liste.setColumnCount(3)
        d.liste.setHorizontalHeaderLabels(("Wann", "Wer", "Was"))
        d.liste.setRowCount(len(zeilen))
        for r, z in enumerate(zeilen):
            wann = datetime.datetime.fromisoformat(z["wann"]).strftime("%d.%m.%Y %H:%M")
            for c, t in enumerate((wann, z["wer"] or "unbekannt", z["was"])):
                d.liste.setItem(r, c, _zelle(t))
        d.liste.resizeColumnsToContents()
        d.liste.horizontalHeader().setStretchLastSection(True)
        d.liste.resizeRowsToContents()
        zu = QDialogButtonBox(QDialogButtonBox.Close)
        zu.button(QDialogButtonBox.Close).setText("Schließen")
        zu.rejected.connect(d.reject)
        lay = QVBoxLayout(d)
        if not zeilen:
            lay.addWidget(QLabel("Zu diesem Auftrag ist noch nichts aufgezeichnet (angelegt vor Version 1.2)."))
        lay.addWidget(d.liste, 1)
        lay.addWidget(zu)
        d.resize(760, 380)
        if zeigen:
            d.exec()
        return d

    def fertig_melden(self, zeigen=True, gang_id=None, suchen=False):
        """Fertig melden. Mit einem offenen Auftrag in der Liste: dessen Meldung, oben steht die Suche für einen
        anderen. Ohne Auswahl (oder suchen=True): erst die Auftragsnummer suchen."""
        if not self.darf("melden"):
            return None
        a = self.gewaehlt()
        if suchen or a is None or a["status"] == D.FERTIG:
            d = FertigDialog(self.db, None, self)
            if zeigen:
                d.exec()
                if d.gemeldet:
                    self.laden()
                    self.statusBar().showMessage("Fertig gemeldet: " + ", ".join(d.gemeldet), 10000)
            return d
        gang = None
        if a["gaenge"]:                           # Fertigmeldung je Arbeitsgang (Plan A4a)
            gang = self.gang_waehlen(a, "Welche Zeile fertig melden?", gang_id)
            if gang is None:
                return None
            if gang["start_am"] and gang["platz"]:
                self.db.stoppen(a["id"], gang_id=gang["id"])
                a = self.db.auftrag(a["id"])
                gang = next(g for g in a["gaenge"] if g["id"] == gang["id"])
        elif a["start_am"]:
            self.db.stoppen(a["id"])
            a = self.db.auftrag(a["id"])
        d = FertigDialog(self.db, a, self, gang=gang, suchen=True)
        if zeigen and d.exec() == QDialog.Accepted:
            self.laden()
        return d

    def wieder_oeffnen(self):
        a = self.gewaehlt()
        if a and self.darf("melden"):
            self.db.wieder_oeffnen(a["id"])
            self.laden()

    def loeschen(self):
        """Ohne Rückfrage in den Papierkorb (P3); dort lässt sich der Auftrag zurückholen."""
        a = self.gewaehlt()
        if a is None or not self.darf("auftraege"):
            return
        self.db.auftrag_loeschen(a["id"])
        self.laden()
        self.statusBar().showMessage(f"Auftrag {a['nummer']} liegt im Papierkorb (Mehr → Papierkorb, "
                                     f"{D.PAPIERKORB_TAGE} Tage).", 10000)

    def csv_einlesen(self, pfad=None, fragen=True):
        if not self.darf("auftraege"):
            return None
        if pfad is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "Aufträge aus CSV einlesen", "", "CSV (*.csv *.txt);;Alle (*)")
            if not pfad:
                return None
        try:
            ergebnis = austausch.lesen(self.db, pfad)
        except OSError as e:
            self.meldung(f"Die Datei lässt sich nicht lesen: {e}")
            return None
        text = austausch.zusammenfassung(ergebnis)
        if not ergebnis["neu"] and not ergebnis["geaendert"]:
            if fragen:
                QMessageBox.information(self, NAME, "Nichts zu übernehmen.\n\n" + text)
            return ergebnis
        if fragen and QMessageBox.question(self, NAME, text + "\n\nJetzt übernehmen?", QMessageBox.Yes | QMessageBox.No,
                                           QMessageBox.Yes) != QMessageBox.Yes:
            return None
        self.db.sichern("vor-CSV")
        austausch.uebernehmen(self.db, ergebnis)
        self.laden()
        return ergebnis

    def csv_speichern(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Auftragsliste als CSV", "Auftraege.csv", "CSV (*.csv)")
            if not pfad:
                return None
        ids = [self.liste.item(r, 0).data(Qt.UserRole) for r in range(self.liste.rowCount())]
        return austausch.schreiben(self.db, pfad, [self.db.auftrag(i) for i in ids])

    # ------------------------------------------------------------------ Auslastung
    def _seite_auslastung(self):
        w = QWidget()
        self.wochen = QSpinBox()
        self.wochen.setRange(2, 26)
        self.wochen.setValue(int(self.db.zahl("wochen", 8)))
        self.wochen.setSuffix(" Wochen")
        self.wochen.valueChanged.connect(self._wochen_geaendert)
        self.k_pdf = QPushButton("PDF …")
        pdf_menue = QMenu(self.k_pdf)
        pdf_menue.addAction("Auslastung A4 quer …", lambda: self.pdf())
        pdf_menue.addAction("Auslastung A3 quer (zum Aushängen) …", lambda: self.pdf(gross=True))
        pdf_menue.addAction("Tagesansicht des gezeigten Tages …", lambda: self.tag_pdf())
        self.k_pdf.setMenu(pdf_menue)
        self.k_auskunft = QPushButton("Terminauskunft …")
        self.k_auskunft.setToolTip("Wann wäre ein neuer Auftrag mit einer bestimmten Laufzeit fertig? Rechnet nur, "
                                   "speichert nichts.")
        self.k_auskunft.clicked.connect(lambda _=False: self.terminauskunft())
        self.k_arbeitsliste = QPushButton("Arbeitsliste PDF …")
        self.k_arbeitsliste.setToolTip("Je Maschine eine Seite für die Werkstatt: die Aufträge in der geplanten "
                                       "Reihenfolge mit Laufzeit, Start, Fertig-Datum und Liefertermin.")
        self.k_arbeitsliste.clicked.connect(lambda _=False: self.arbeitsliste_pdf())
        self.k_risiko = QPushButton("Terminrisiko zeigen")
        self.k_risiko.clicked.connect(lambda _=False: self.woche_waehlen(None, None))
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.balken = WochenBalken()
        self.balken.gewaehlt.connect(self.woche_waehlen)
        self.k_wenn = QPushButton("Was wäre, wenn …")
        self.k_wenn.setToolTip("Probeweise rechnen: Samstagsarbeit, Zusatzstunden in einer Woche, ein Auftrag auf "
                               "einer anderen Maschine. Gespeichert wird erst mit „Übernehmen“.")
        self.k_wenn.clicked.connect(lambda _=False: self.was_waere_wenn())
        self.k_optimieren = QPushButton("Optimieren …")
        self.k_optimieren.setToolTip("Sucht eine Reihenfolge und Maschinenverteilung, bei der möglichst kein Auftrag "
                                     "zu spät fertig wird, und zeigt sie als Vorschlag. Geändert wird erst mit "
                                     "„Übernehmen“.")
        opt_menue = QMenu(self.k_optimieren)
        for z, name in rechnung.ZIELE:
            opt_menue.addAction(name, lambda z=z: self.optimieren(ziel=z))
        self.k_optimieren.setMenu(opt_menue)
        self.rueck_opt = None                     # Stand vor der übernommenen Optimierung (für Rückgängig)
        self.k_rueck = QPushButton("Verschieben rückgängig")
        self.k_rueck.clicked.connect(lambda _=False: self.verschieben_rueckgaengig())
        self.k_rueck.setVisible(False)
        self.k_vorschlag = QPushButton("Vorschlag übernehmen")
        self.k_vorschlag.setToolTip("Legt den gewählten Auftrag auf die vorgeschlagene Ausweichmaschine.")
        self.k_vorschlag.clicked.connect(lambda _=False: self.vorschlag_uebernehmen())
        self.zug_zeile = QLabel("")
        self.zug_zeile.setWordWrap(True)
        self.zug_zeile.setVisible(False)
        self.tafel = ZiehTafel()
        self.tafel.verschoben.connect(self.tafel_verschoben)
        self.tafel.gewaehlt.connect(self.tafel_gewaehlt)
        self.tafel.oeffnen.connect(lambda i: self.aendern(i))
        legende = QLabel("Wochenbalken: Rahmen = Kapazität, gefüllt = eingelastete Aufträge (ab 80 % gelb, über 100 % "
                         "rot), grau links = tatsächliche Stunden aus den Fertigmeldungen.")
        legende.setWordWrap(True)
        legende.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        # Plantafel: Ansicht (V2), Farbe (V3), Legende
        self.tafel_rahmen = TafelRahmen(self.tafel)
        self.t_zoom = {}
        tz = QHBoxLayout()
        tz.setSpacing(4)
        tz.addWidget(QLabel("<b>Plantafel</b>"))
        tz.addSpacing(8)
        for name, tage in TAFEL_ZOOM:
            k = QPushButton(name)
            k.setCheckable(True)
            k.clicked.connect(lambda _=False, name=name: self.tafel_zoom(name))
            tz.addWidget(k)
            self.t_zoom[name] = k
        self.t_blaettern = []
        for zeichen, tipp, tun in (("◀", "zurück (Tagesansicht: ein Tag, sonst eine Woche)",
                                    lambda: self.tafel_rahmen.blaettern(-1)),
                                   ("Heute", "zeigt heute", lambda: self.tafel_rahmen.zu_heute()),
                                   ("▶", "weiter (Tagesansicht: ein Tag, sonst eine Woche)",
                                    lambda: self.tafel_rahmen.blaettern(1))):
            k = QPushButton(zeichen)
            k.setToolTip(tipp)
            k.clicked.connect(lambda _=False, tun=tun: tun())
            tz.addWidget(k)
            self.t_blaettern.append(k)
        self.t_suche = QLineEdit()
        self.t_suche.setPlaceholderText("Suchen: Auftrag oder Kunde")
        self.t_suche.setClearButtonEnabled(True)
        self.t_suche.setMinimumWidth(170)
        self.t_suche.setMaximumWidth(220)
        self.t_suche.setToolTip("Zeigt den Auftrag in der Plantafel und springt zu seinem Beginn. Eingabetaste: "
                                "nächster Treffer.")
        self.t_suche.textChanged.connect(lambda _t: self.tafel_suchen())
        self.t_suche.returnPressed.connect(lambda: self.tafel_suchen(weiter=True))
        tz.addSpacing(8)
        tz.addWidget(self.t_suche)
        self.k_vollbild = QPushButton("Vollbild")
        self.k_vollbild.setToolTip("Plantafel über den ganzen Bildschirm, z. B. für den Bildschirm in der Halle. "
                                   "Esc schließt.")
        self.k_vollbild.clicked.connect(lambda _=False: self.tafel_vollbild())
        tz.addWidget(self.k_vollbild)
        tz.addSpacing(12)
        tz.addWidget(QLabel("Farbe nach"))
        self.t_farbe = QComboBox()
        self.t_farbe.addItems(TAFEL_FARBE)
        self.t_farbe.currentTextChanged.connect(self.tafel_farbe)
        tz.addWidget(self.t_farbe)
        tz.addSpacing(12)
        self.t_legende = QLabel("")
        self.t_legende.setTextFormat(Qt.RichText)
        tz.addWidget(self.t_legende, 1)
        self.t_hinweis = QLabel("▶ läuft · ❚❚ gestoppt · schraffiert = wartet auf Material · weißer Punkt = fester Platz "
                                "· Dreieck = Liefertermin, gestrichelt = Verspätung · Streifen oben = Auslastung des "
                                "Tages. Ziehen mit der Maus legt einen Auftrag fest, Doppelklick öffnet ihn.")
        self.t_hinweis.setWordWrap(True)
        self.t_hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.balken)
        ll.addWidget(legende)
        ll.addSpacing(6)
        ll.addLayout(tz)
        ll.addWidget(self.tafel_rahmen)
        self.t_ist = QLabel("")                   # V3: Tatsächliches von heute, nur in der Tagesansicht
        self.t_ist.setWordWrap(True)
        self.t_ist.setTextFormat(Qt.RichText)
        self.t_ist.hide()
        self.vollbild = None
        ll.addWidget(self.t_ist)
        ll.addWidget(self.t_hinweis)
        ll.addStretch(1)
        ini = ort.ini_lesen(self.platz)
        self.t_farbe.setCurrentText(ini.get("tafel_farbe") if ini.get("tafel_farbe") in TAFEL_FARBE else TAFEL_FARBE[0])
        self.tafel_zoom(ini.get("tafel_zoom") if ini.get("tafel_zoom") in self.t_zoom else "2 Wochen", merken=False)
        self.tafel_farbe(self.t_farbe.currentText(), merken=False)
        rollen = QScrollArea()
        rollen.setWidgetResizable(True)
        rollen.setFrameShape(QFrame.NoFrame)
        rollen.setWidget(links)
        self.tafel_rahmen.aussen = rollen
        rollen.viewport().installEventFilter(self.tafel_rahmen)
        self.details_titel = QLabel("")
        self.details_titel.setWordWrap(True)
        self.details = QTableWidget()
        self.details.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.details.setSelectionMode(QAbstractItemView.SingleSelection)
        self.details.verticalHeader().setVisible(False)
        self.details.itemDoubleClicked.connect(
            lambda z: self.aendern(self.details.item(z.row(), 0).data(Qt.UserRole)))
        self.details.itemSelectionChanged.connect(self._vorschlag_knopf)
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        kopf = QHBoxLayout()
        kopf.addWidget(self.details_titel, 1)
        kopf.addWidget(self.k_vorschlag)
        kopf.addWidget(self.k_risiko)
        self.vorschlag_zeile = QLabel("")
        self.vorschlag_zeile.setWordWrap(True)
        self.vorschlag_zeile.setVisible(False)
        rl.addLayout(kopf)
        rl.addWidget(self.vorschlag_zeile)
        rl.addWidget(self.details, 1)
        teiler = QSplitter(Qt.Horizontal)
        teiler.addWidget(rollen)
        teiler.addWidget(rechts)
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 2)
        teiler.setSizes([800, 560])
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Zeitraum"))
        oben.addWidget(self.wochen)
        oben.addWidget(self.k_auskunft)
        oben.addWidget(self.k_wenn)
        oben.addWidget(self.k_optimieren)
        oben.addWidget(self.k_rueck)
        oben.addStretch(1)
        oben.addWidget(self.k_arbeitsliste)
        oben.addWidget(self.k_pdf)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addWidget(self.info)
        lay.addWidget(self.zug_zeile)
        lay.addWidget(teiler, 1)
        return w

    def tafel_zoom(self, name, merken=True):
        """Ansicht der Plantafel (V2): so viele Tage sind sichtbar, der Rest wird gerollt; der Platz merkt es sich."""
        for n, k in self.t_zoom.items():
            k.setChecked(n == name)
        self.tafel_rahmen.sichtbar(dict(TAFEL_ZOOM)[name])
        for k in self.t_blaettern:
            k.setEnabled(name != "Alles")
        self.tag_ist_zeigen()
        if merken:
            self._platz_merken("tafel_zoom", name)

    def tag_ist_zeigen(self):
        """Unter der Tagesansicht: was heute tatsächlich läuft und fertig wurde (V3). Ergebnis: der Text."""
        text = ""
        if self.tafel.tag_an and getattr(self, "ein", None):
            ist = rechnung.tag_ist_text(rechnung.tag_ist(self.db, self.heute()))
            if ist:
                rot = stil.umsetzen(stil.ROT)
                text = "<b>Heute tatsächlich:</b> " + " &nbsp;·&nbsp; ".join(
                    f"<b>{html.escape(m)}</b> " + "; ".join(
                        f"<span style='color:{rot}'>{html.escape(t)}</span>" if "überzieht" in t else html.escape(t)
                        for t in texte) for m, texte in sorted(ist.items()))
        if hasattr(self, "t_ist"):
            self.t_ist.setText(text)
            self.t_ist.setVisible(bool(text))
        return text

    def tafel_suchen(self, text=None, weiter=False):
        """Auftrag in der Plantafel suchen (Auftragsnummer oder Kunde enthält den Text): hebt ihn hervor und rollt
        zu seinem Beginn. weiter: der nächste Treffer. Ergebnis: Auftrag-ID oder None."""
        text = (self.t_suche.text() if text is None else text).strip().lower()
        t = self.tafel
        if not text or not t.ein:
            if t.auswahl is not None:
                t.auswahl = None
                t.update()
            return None
        treffer = {}
        for a in t.ein["auftraege"]:
            if text in str(a.get("nummer") or "").lower() or text in str(a.get("kunde") or "").lower():
                tag = min((s[0] for s in a.get("stuecke") or ()), default=None)
                if a["id"] not in treffer or (tag and (treffer[a["id"]] is None or tag < treffer[a["id"]])):
                    treffer[a["id"]] = tag
        if not treffer:
            self.hinweis(f"„{text}“ nicht gefunden (gesucht wird in den offenen Aufträgen).")
            t.auswahl = None
            t.update()
            return None
        ids = sorted(treffer, key=lambda i: (treffer[i] is None, treffer[i] or datetime.date.max, i))
        i = ids[(ids.index(t.auswahl) + 1) % len(ids)] if weiter and t.auswahl in ids else ids[0]
        t.auswahl = i
        t.update()
        self.tafel_gewaehlt(i)
        tag = treffer[i]
        if tag in t.tage and t.tagbreite_fest:
            if self.tafel_rahmen.tage != 1:
                tag -= datetime.timedelta(days=tag.weekday())
            self.tafel_rahmen.horizontalScrollBar().setValue(int(t.tage.index(tag) * t.tagbreite_fest))
        nummer = next(a["nummer"] for a in t.ein["auftraege"] if a["id"] == i)
        self.hinweis(f"{ids.index(i) + 1} von {len(ids)} Treffern: {nummer}"
                     + (f", beginnt {_wtag(treffer[i])}" if treffer[i] else ", noch nicht eingeplant"))
        return i

    def tafel_vollbild(self, zeigen=True):
        """Plantafel in einem eigenen Fenster über den ganzen Bildschirm (nur ansehen); folgt jedem Neuladen."""
        if self.vollbild is None:
            self.vollbild = TafelVollbild(self, self.platz)
        self._vollbild_fuellen()
        if zeigen:
            self.vollbild.showFullScreen()
        return self.vollbild

    def _vollbild_fuellen(self):
        v = self.vollbild
        if v is None or not getattr(self, "ein", None):
            return
        v.tafel.spannen = self.tafel.spannen
        v.tafel.setzen(self.aus, self.ein, self.wochen.value(), None, self.tafel_zustand())
        v.tafel.farbe_setzen(self.t_farbe.currentText())
        v.titel.setText(f"<b>Plantafel</b> &nbsp; Stand {_wtag(self.heute())}, "
                        f"{datetime.datetime.now():%H:%M} Uhr")
        v.anpassen()

    def tafel_farbe(self, art, merken=True):
        """Farbe der Balken (V3): nach Terminrisiko, Kunde oder Status; die Legende steht daneben."""
        self.tafel.farbe_setzen(art)
        self.t_legende.setText("&nbsp;&nbsp; ".join(
            f"<span style='color:{f}'>■</span> {t}" for f, t in self.tafel.legende()))
        if merken:
            self._platz_merken("tafel_farbe", art)

    def tafel_zustand(self):
        """Zustand je Auftrag bzw. Arbeitsgang für die Plantafel (V5): läuft, gestoppt mit Grund, Anteil erledigt,
        wartet auf Material."""
        out = {}
        for a in self.db.auftraege((D.OFFEN, D.LAEUFT)):
            material = self.db.wartet_auf_material(a, self.heute())
            for g in (a["gaenge"] or [None]):
                teil = g if g is not None else a
                if teil["status"] == D.FERTIG:
                    continue
                gang_id = g["id"] if g is not None else None
                gelaufen = 0 if g is not None and g["platz"] == D.FREMD else self.db.gelaufen(teil)
                laeuft = str(teil["start_am"])[11:16] if teil["start_am"] else ""
                grund = "" if laeuft else self.db.offener_stopp(a["id"], gang_id)
                out[(a["id"], gang_id)] = dict(
                    laeuft=laeuft, gestoppt=bool(not laeuft and (gelaufen or grund)), grund=grund,
                    anteil=min(1.0, gelaufen / teil["kalk_min"]) if teil["kalk_min"] else 0.0, material=material,
                    gelaufen=gelaufen, kalk=int(teil["kalk_min"] or 0),
                    ueber=max(0, gelaufen - int(teil["kalk_min"] or 0)) if laeuft and teil["kalk_min"] else 0)
        return out

    def tafel_verschoben(self, auftrag_id, gang_id, maschine, tag):
        """Auftrag in der Plantafel verschoben (E1): Er liegt fest ab diesem Tag auf dieser Maschine. Danach steht
        über der Tafel, welche Termine dadurch kippen; „Verschieben rückgängig“ stellt den Stand davor wieder her."""
        if not self.darf("auftraege"):
            return False
        vorher = self.ein
        try:
            self.rueck = self.db.festlegen(auftrag_id, tag, maschine, gang_id)
            self.rueck_opt = None
            self.k_rueck.setText("Verschieben rückgängig")
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        a = self.db.auftrag(auftrag_id)
        schlechter = [x for x in rechnung.vergleich(vorher, self.ein) if x["schlechter"] > 0]
        text = f"Auftrag {a['nummer']} liegt jetzt fest ab {_wtag(tag)} auf {maschine}."
        if schlechter:
            text += (f" <b style='color:{stil.umsetzen(stil.ROT)}'>Dadurch kippt der Termin bei: "
                     + ", ".join(f"{x['nummer']} ({RISIKO_TEXT.get(x['risiko_neu'], '')})" for x in schlechter[:8])
                     + ("…" if len(schlechter) > 8 else "") + ".</b>")
        else:
            text += " Kein anderer Termin kippt dadurch."
        self.zug_zeile.setText(text)
        self.zug_zeile.setVisible(True)
        self.k_rueck.setVisible(True)
        self.tafel.auswahl = auftrag_id
        self.tafel.update()
        return True

    def optimieren(self, zeigen=True, uebernehmen=None, ziel=rechnung.ZIEL_TERMIN):
        """Automatische Optimierung (V5, A2) mit Ziel (rechnung.ZIELE): Vorschlag rechnen, im Dialog zeigen und auf
        „Übernehmen“ speichern; „Optimierung rückgängig“ stellt den Stand davor wieder her. uebernehmen True/False
        überspringt den Dialog (Tests). Ergebnis: der Vorschlag (rechnung.optimieren) oder None, wenn nichts zu
        verbessern ist."""
        if not getattr(self, "ein", None):
            return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            vorschlag = rechnung.optimieren(self.aus, self.ein, int(self.db.zahl("schwelle_tage", 2)), ziel=ziel)
        finally:
            QApplication.restoreOverrideCursor()
        if vorschlag is None:
            r = self.ein["risiko"]
            text = ("Das Programm findet keine Reihenfolge mit weniger Rüstzeit, bei der alle Termine so gut bleiben "
                    "wie jetzt. Rüsten spart nur, wo Aufträge das gleiche Material eingetragen haben und die "
                    "Maschine eine Rüstzeit hat (Einstellungen → Maschinen)." if ziel == rechnung.ZIEL_RUESTEN else
                    "Das Programm findet keine gleichmäßigere Verteilung auf die Ausweichmaschinen, bei der alle "
                    "Termine so gut bleiben wie jetzt." if ziel == rechnung.ZIEL_GLEICH else
                    "Alle Termine sind zu halten, es gibt nichts zu optimieren." if not (
                        r[einlastung.UEBER] or r[einlastung.KNAPP]) else
                    "Das Programm findet keine bessere Reihenfolge oder Maschinenverteilung. Helfen können "
                    "Zusatzstunden oder Samstagsarbeit (Was wäre, wenn …) oder ein späterer Liefertermin.")
            if zeigen and uebernehmen is None:
                QMessageBox.information(self, "Optimieren", text)
            else:
                self.hinweis(text)
            return None
        if uebernehmen is None and zeigen:
            uebernehmen = OptimierenDialog(self, vorschlag).exec() == QDialog.Accepted
        if uebernehmen and self.darf("auftraege"):
            self.rueck_opt = self.db.optimierung_uebernehmen(vorschlag["schritte"])
            self.rueck = None
            self.laden()
            v, n = vorschlag["vorher"], vorschlag["nachher"]
            mehr = (f", Rüsten {_stunden_text(vorschlag['ruest'][0])} → {_stunden_text(vorschlag['ruest'][1])}"
                    if ziel == rechnung.ZIEL_RUESTEN else "")
            self.zug_zeile.setText(f"Optimierung übernommen ({len(vorschlag['schritte'])} Änderungen): nicht zu halten "
                                   f"{v[0]} → {n[0]}, knapp {v[1]} → {n[1]}{mehr}.")
            self.zug_zeile.setVisible(True)
            self.k_rueck.setText("Optimierung rückgängig")
            self.k_rueck.setVisible(True)
        return vorschlag

    def verschieben_rueckgaengig(self):
        if self.rueck_opt is not None and self.darf("auftraege"):
            try:
                self.db.optimierung_zurueck(self.rueck_opt)
            except D.Fehler as e:
                self.meldung(str(e))
                return False
            self.rueck_opt = None
            self.k_rueck.setText("Verschieben rückgängig")
            self.zug_zeile.setVisible(False)
            self.k_rueck.setVisible(False)
            self.laden()
            return True
        if self.rueck is None or not self.darf("auftraege"):
            return False
        try:
            self.db.zuruecksetzen(self.rueck)
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.rueck = None
        self.zug_zeile.setVisible(False)
        self.k_rueck.setVisible(False)
        self.laden()
        return True

    def was_waere_wenn(self, zeigen=True):
        d = WasWaereWennDialog(self)
        if zeigen:
            d.exec()
        return d

    def _vorschlag_knopf(self):
        r = self.details.currentRow()
        z = self.details.item(r, 0) if r >= 0 else None
        self.k_vorschlag.setEnabled(z is not None and z.data(Qt.UserRole) in self.vorschlag
                                    and self.db.darf("auftraege"))

    def vorschlag_uebernehmen(self, auftrag_id=None):
        """Ausweichmaschine (E3): den gewählten Auftrag auf die vorgeschlagene Maschine legen."""
        if auftrag_id is None:
            r = self.details.currentRow()
            auftrag_id = self.details.item(r, 0).data(Qt.UserRole) if r >= 0 else None
        v = self.vorschlag.get(auftrag_id)
        if v is None or not self.darf("auftraege"):
            return False
        self.db.maschine_wechseln(auftrag_id, v["maschine"])
        self.laden()
        return True

    def _wochen_geaendert(self, n):
        self.db.einstellung_setzen("wochen", n)
        self.stand = self.db.stand()
        self.laden()

    def woche_waehlen(self, maschine, key):
        self.woche = (maschine, key) if maschine is not None and isinstance(key, datetime.date) else None
        if self.woche is None:
            self.balken.auswahl = None
            self.balken.update()
        else:
            self.tafel_zu_woche(key)
        self.details_zeigen()

    def tafel_zu_woche(self, montag):
        """Klick auf einen Wochenbalken: die Plantafel rollt zu dieser Woche (in der Tagesansicht zu ihrem ersten
        Tag ab heute). In der Ansicht „Alles“ ist die Woche schon zu sehen. Ergebnis: der Tag, der links steht."""
        t, r = self.tafel, self.tafel_rahmen
        if not t.tage or not t.tagbreite_fest:
            return None
        tag = min(max(montag, t.tage[0]), t.tage[-1])
        r.horizontalScrollBar().setValue(int(t.tage.index(tag) * t.tagbreite_fest))
        return tag

    def tafel_gewaehlt(self, auftrag_id):
        for r in range(self.details.rowCount()):
            if self.details.item(r, 0).data(Qt.UserRole) == auftrag_id:
                self.details.selectRow(r)
                return

    def auftraege_der_auswahl(self):
        """(Titel, Aufträge) für die Tabelle rechts: gewählte Woche oder die Aufträge mit Terminrisiko."""
        if self.woche:
            m, mo = self.woche
            ende = mo + datetime.timedelta(days=6)
            liste = [a for a in self.ein["auftraege"] if a["maschine"] == m
                     and any(mo <= tag <= ende for tag, _v, _b in a["stuecke"])]
            return f"{m}, KW {mo.isocalendar()[1]}: {len(liste)} Aufträge auf dem Laser", liste
        liste = rechnung.kritische(self.ein)
        return (f"Terminrisiko: {len(liste)} Aufträge knapp oder nicht zu halten" if liste
                else "Kein Auftrag mit Terminrisiko"), liste

    def details_zeigen(self):
        if self.ein is None:
            return
        titel, liste = self.auftraege_der_auswahl()
        self.details_titel.setText(titel)
        kopf = ("Auftragsnummer", "Kunde", "Maschine", "Liefertermin", "Restlaufzeit", "Laser fertig", "Puffer [AT]",
                "Terminrisiko", "Vorschlag")
        self.details.setColumnCount(len(kopf))
        self.details.setHorizontalHeaderLabels(kopf)
        self.details.setRowCount(len(liste))
        for r, a in enumerate(liste):
            werte = [_zelle(a["nummer"], daten=a["id"]), _zelle(a["kunde"]), _zelle(a["maschine"] or D.FREMD_TEXT),
                     _zelle(_tag(a.get("termin"))), _zelle(self.lz(int(a["h"] * 60 + 0.5)), True),
                     _zelle(_tag(a.get("fertig")) or "später"), _zelle(a["puffer"], True),
                     _zelle(RISIKO_TEXT.get(a["risiko"], "")), _zelle(self._vorschlag_text(a["id"]))]
            for c, z in enumerate(werte):
                self.details.setItem(r, c, z)
            if a["risiko"] in RISIKO_FARBE:
                werte[7].setBackground(stil.farbe(RISIKO_FARBE[a["risiko"]]))
                werte[7].setForeground(stil.farbe(stil.TEXT))
        self.details.resizeColumnsToContents()
        self.details.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.details.setColumnHidden(8, not self.vorschlag)
        self.k_vorschlag.setVisible(bool(self.vorschlag))
        namen = {a["id"]: a["nummer"] for a in self.ein["auftraege"]}
        self.vorschlag_zeile.setText("<b>Ausweichmaschine:</b> " + "; ".join(
            f"{namen.get(i, '')} {self._vorschlag_text(i)}" for i in list(self.vorschlag)[:4])
            + (" …" if len(self.vorschlag) > 4 else ""))
        self.vorschlag_zeile.setVisible(bool(self.vorschlag))
        self._vorschlag_knopf()

    def _vorschlag_text(self, auftrag_id):
        v = self.vorschlag.get(auftrag_id)
        if v is None:
            return ""
        return (f"auf {v['maschine']} fertig {_wtag(v['fertig'])}"
                + (f", {_arbeitstage(v['tage'])} früher" if v["tage"] else "")
                + (", Termin dann ok" if v["risiko"] == einlastung.OK else
                   ", dann knapp" if v["risiko"] == einlastung.KNAPP else ""))

    def auslastung_zeigen(self):
        self.vorschlag = rechnung.ausweichen(self.aus, self.ein, int(self.db.zahl("schwelle_tage", 2)))
        self.tafel.ziehbar = self.db.darf("auftraege")
        self.balken.setzen(spalten_daten(self.aus, self.ein, self.gem, True), self.woche)
        self.tafel.spannen = rechnung.spannen(self.db)
        self.tafel.setzen(self.aus, self.ein, self.wochen.value(), self.tafel.auswahl, self.tafel_zustand())
        self.tafel_rahmen.anpassen()
        self.tafel_farbe(self.t_farbe.currentText(), merken=False)
        self.tag_ist_zeigen()
        if self.vollbild is not None and self.vollbild.isVisible():
            self._vollbild_fuellen()
        r = self.ein["risiko"]
        text = ("Die offenen Aufträge laufen ab heute nacheinander, sortiert nach Liefertermin, durch die freien "
                "Stunden jeder Maschine. Was nicht in eine Woche passt, rutscht in die nächste.")
        if r[einlastung.UEBER] or r[einlastung.KNAPP]:
            text += (f" <b style='color:{stil.umsetzen(stil.ROT)}'>Terminrisiko: {r[einlastung.UEBER]} nicht zu "
                     f"halten, {r[einlastung.KNAPP]} knapp.</b>")
        self.info.setText(text)
        self.details_zeigen()

    def tag_pdf(self, pfad=None, tag=None):
        """Tagesansicht als PDF (A4 quer): ein Tag mit Stundenraster, darunter die Aufträge des Tages mit Uhrzeit
        und das Tatsächliche. tag: Vorgabe der Tag, der in der Tagesansicht gerade zu sehen ist, sonst heute."""
        tag = tag or self.tafel_rahmen.tag_zeigen() or self.heute()
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Tagesansicht als PDF", f"Tagesplan-{tag:%Y-%m-%d}.pdf",
                                                  "PDF (*.pdf)")
            if not pfad:
                return None
        w, seite, p = _pdf_beginnen(pfad, "Tagesplan")
        t = self.tafel
        with stil.druckfarben():
            f = self.font()
            y = _pdf_titel(p, f, seite, f"Tagesplan {_wtag(tag)}, Stand {self.heute().strftime('%d.%m.%Y')}")
            merk = (t.tage, t.tagbreite_fest, t.versatz, t.tag_an, t.size(), t.minimumWidth(), t.auswahl)
            t.tage, t.tagbreite_fest, t.versatz, t.auswahl = [tag], None, 0, None
            t.tag_ansicht(True)
            t.setMinimumWidth(0)
            t.resize(seite.width(), t.sizeHint().height())
            t.render(p, QPointF(0, y).toPoint())
            y += t.height() + 14
            zeilen = []
            for a in sorted(self.ein["auftraege"], key=lambda a: (a.get("maschine") or "", a["nummer"])):
                for d, von, bis in a.get("stuecke") or ():
                    if d == tag and bis - von > 0:
                        m = a.get("maschine") or ""
                        zeilen.append([m, t.uhr(m, d, von), t.uhr(m, d, bis), a["nummer"], a.get("kunde") or "",
                                       laufzeit.text(int((bis - von) * 60 + 0.5), "hm"), _tag(a.get("termin"))])
            zeilen.sort(key=lambda z: (z[0], z[1]))
            t.tage, t.tagbreite_fest, t.versatz, t.auswahl = merk[0], merk[1], merk[2], merk[6]
            t.tag_ansicht(merk[3])
            t.setMinimumWidth(merk[5])
            t.resize(merk[4])
            t._groesse()
            y = _pdf_tabelle(p, f, seite, y, ("Maschine", "von", "bis", "Auftragsnummer", "Kunde", "Laufzeit",
                                              "Liefertermin"), zeilen, (110, 60, 60, 190, 260, 90, 100))
            ist = rechnung.tag_ist_text(rechnung.tag_ist(self.db, tag))
            if ist:
                y += 12
                p.drawText(QRectF(0, y, seite.width(), 16), Qt.AlignLeft | Qt.AlignVCenter, "Tatsächlich an diesem Tag")
                _pdf_tabelle(p, f, seite, y + 18, ("Maschine", "Auftrag"),
                             [[m, text] for m, texte in sorted(ist.items()) for text in texte], (110, 760))
            p.end()
        del w
        return pfad

    def pdf(self, pfad=None, gross=False):
        """Auslastung als PDF (A4 quer, gross = A3 quer): Wochenbalken, Plantafel und die Aufträge mit
        Terminrisiko."""
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Auslastung als PDF", "Maschinenauslastung-A3.pdf" if gross
                                                  else "Maschinenauslastung.pdf", "PDF (*.pdf)")
            if not pfad:
                return None
        w, seite, p = _pdf_beginnen(pfad, "Maschinenauslastung", gross)
        with stil.druckfarben():
            f = self.font()
            y = _pdf_titel(p, f, seite, f"Maschinenauslastung, Stand {self.heute().strftime('%d.%m.%Y')}")
            tb, versatz = self.tafel.tagbreite_fest, self.tafel.versatz     # im PDF: alles passend auf die Seite
            tag_an = self.tafel.tag_an
            self.tafel.tag_ansicht(False)
            self.tafel.tagbreite_fest, self.tafel.versatz = None, 0
            for widget in (self.balken, self.tafel):
                alt, fest = widget.size(), widget.minimumWidth()
                widget.setMinimumWidth(0)
                widget.resize(seite.width(), widget.sizeHint().height())
                widget.render(p, QPointF(0, y).toPoint())
                y += widget.height() + 14
                widget.setMinimumWidth(fest)
                widget.resize(alt)
            self.tafel.tagbreite_fest, self.tafel.versatz = tb, versatz
            self.tafel.tag_ansicht(tag_an)
            liste = rechnung.kritische(self.ein)
            zeilen = [[a["nummer"], a["kunde"], a["maschine"] or D.FREMD_TEXT, _tag(a.get("termin")),
                       _tag(a.get("fertig")) or "später",
                       "" if a["puffer"] is None else str(a["puffer"]), RISIKO_TEXT.get(a["risiko"], "")] for a in liste]
            p.drawText(QRectF(0, y, seite.width(), 16), Qt.AlignLeft | Qt.AlignVCenter,
                       f"Aufträge mit Terminrisiko: {len(liste)}")
            _pdf_tabelle(p, f, seite, y + 18, ("Auftragsnummer", "Kunde", "Maschine", "Liefertermin", "Laser fertig",
                                               "Puffer [AT]", "Terminrisiko"), zeilen, (110, 250, 80, 90, 90, 80, 120))
            p.end()
        del w
        return pfad

    def terminauskunft(self, zeigen=True):
        d = TerminauskunftDialog(self)
        if zeigen:
            d.exec()
        return d

    def arbeitsliste_pdf(self, pfad=None):
        """Arbeitsliste für die Werkstatt (P7): je Maschine eine Seite A4 quer, Aufträge in der geplanten Reihenfolge."""
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Arbeitsliste als PDF", "Arbeitsliste.pdf", "PDF (*.pdf)")
            if not pfad:
                return None
        felder = [f["name"] for f in self.db.zusatzfelder()][:2]
        kopf = ["Nr.", "Auftragsnummer", "Kunde", "Restlaufzeit", "Start", "Laser fertig", "Liefertermin",
                "Terminrisiko"] + felder + ["Bemerkung", "erledigt"]
        breiten = [30, 110, 170, 90, 90, 90, 90, 95] + [95] * len(felder) + [150, 60]
        w, seite, p = _pdf_beginnen(pfad, "Arbeitsliste")
        breiten = [b * seite.width() / sum(breiten) for b in breiten]        # auf die Seitenbreite verteilen
        f = self.font()
        for i, m in enumerate(self.ein["maschinen"]):
            if i:
                w.newPage()
            liste = rechnung.arbeitsliste(self.ein, m)
            gesamt = sum(int(a["h"] * 60 + 0.5) for a in liste)
            y = _pdf_titel(p, f, seite, f"Arbeitsliste {m}, Stand {_wtag(self.heute())}: {len(liste)} Aufträge, "
                                        f"{self.lz(gesamt)}")
            zeilen = []
            for n, a in enumerate(liste, start=1):
                voll = self.db.auftrag(a["id"]) or {}
                zeilen.append([n, a["nummer"], a["kunde"], self.lz(int(a["h"] * 60 + 0.5)), _wtag(a["start"]),
                               _wtag(a["fertig"]) or "später", _wtag(a["termin_datum"]),
                               "" if a["risiko"] == einlastung.OK else RISIKO_TEXT.get(a["risiko"], "")]
                              + [(voll.get("zusatz") or {}).get(x, "") for x in felder]
                              + [voll.get("bemerkung", ""), "☐"])
            _pdf_tabelle(p, f, seite, y, kopf, zeilen, breiten, w, hoehe=20)
        p.end()
        return pfad

    # ------------------------------------------------------------------ Soll und Ist
    def _seite_soll_ist(self):
        w = QWidget()
        self.zeitraum = QComboBox()
        self.zeitraum.addItems(ZEITRAUM)
        self.zeitraum.currentIndexChanged.connect(lambda _i: self.soll_ist_zeigen())
        self.k_si_csv = QPushButton("Liste als CSV …")
        self.k_si_pdf = QPushButton("Liste als PDF …")
        self.k_si_csv.clicked.connect(lambda _=False: self.soll_ist_csv())
        self.k_si_pdf.clicked.connect(lambda _=False: self.soll_ist_pdf())
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Fertig gemeldet"))
        oben.addWidget(self.zeitraum)
        oben.addStretch(1)
        oben.addWidget(self.k_si_csv)
        oben.addWidget(self.k_si_pdf)
        self.si_info = QLabel("")
        self.si_info.setWordWrap(True)
        self.si_maschinen = QTableWidget()
        self.si_liste = QTableWidget()
        self.si_stopps = QTableWidget()           # Unterbrechungen nach Grund (E6)
        self.si_stopps.setMaximumHeight(250)
        self.si_stopps_info = QLabel("")
        self.si_stopps_info.setWordWrap(True)
        self.si_stopps_info.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        for t in (self.si_maschinen, self.si_liste, self.si_stopps):
            t.verticalHeader().setVisible(False)
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.setAlternatingRowColors(True)
        self.si_liste.setSortingEnabled(True)
        self.si_maschinen.setMaximumHeight(250)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addWidget(self.si_info)
        links, rechts = QVBoxLayout(), QVBoxLayout()
        links.addWidget(QLabel("<b>Je Maschine</b>"))
        links.addWidget(self.si_maschinen)
        rechts.addWidget(QLabel("<b>Unterbrechungen nach Grund</b>"))
        rechts.addWidget(self.si_stopps)
        beide = QHBoxLayout()
        beide.addLayout(links, 1)
        beide.addLayout(rechts, 1)
        lay.addLayout(beide)
        lay.addWidget(self.si_stopps_info)
        lay.addWidget(QLabel("<b>Je Auftrag</b>"))
        lay.addWidget(self.si_liste, 1)
        return w

    def _seite_kennzahlen(self):
        """Kennzahlen (E7): Termintreue, verspätete Aufträge, Auslastung je Maschine, Kalkulation über die Zeit."""
        w = QWidget()
        self.kz_zeitraum = QComboBox()
        self.kz_zeitraum.addItems(ZEITRAUM)
        self.kz_zeitraum.setCurrentIndex(3)
        self.kz_zeitraum.currentIndexChanged.connect(lambda _i: self.kennzahlen_zeigen())
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Fertig gemeldet"))
        oben.addWidget(self.kz_zeitraum)
        oben.addStretch(1)
        self.kz_kacheln = {}
        kacheln = QHBoxLayout()
        for key, titel in (("treue", "Termintreue"), ("spaet", "Verspätete Aufträge"),
                           ("kalk", "Kalkulation"), ("last", "Auslastung nächste 4 Wochen")):
            rahmen = QFrame()
            rahmen.setObjectName("kz_kachel")
            rahmen.setStyleSheet(f"QFrame#kz_kachel {{ border: 1px solid {stil.umsetzen(stil.RAHMEN)}; "
                                 "border-radius: 6px; }")
            kopf, zahl, unter = QLabel(titel), QLabel(""), QLabel("")
            kopf.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
            zahl.setStyleSheet("font-size: 22pt; font-weight: 700;")
            unter.setWordWrap(True)
            unter.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
            kl = QVBoxLayout(rahmen)
            for x in (kopf, zahl, unter):
                kl.addWidget(x)
            kacheln.addWidget(rahmen, 1)
            self.kz_kacheln[key] = (zahl, unter)
        self.kz_balken = MonatsBalken()
        self.kz_maschinen, self.kz_spaet = QTableWidget(), QTableWidget()
        for t in (self.kz_maschinen, self.kz_spaet):
            t.verticalHeader().setVisible(False)
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
            t.setAlternatingRowColors(True)
        self.kz_spaet.itemDoubleClicked.connect(lambda _z: self._kennzahl_auftrag())
        links, rechts = QVBoxLayout(), QVBoxLayout()
        links.addWidget(QLabel("<b>Auslastung je Maschine</b>"))
        links.addWidget(self.kz_maschinen, 1)
        rechts.addWidget(QLabel("<b>Verspätete Aufträge</b> (Doppelklick zeigt den Auftrag)"))
        rechts.addWidget(self.kz_spaet, 1)
        unten = QHBoxLayout()
        unten.addLayout(links, 2)
        unten.addLayout(rechts, 3)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addLayout(kacheln)
        lay.addWidget(QLabel("<b>Termintreue je Monat</b> (Balken), darunter die Abweichung der Kalkulation"))
        lay.addWidget(self.kz_balken)
        lay.addLayout(unten, 1)
        return w

    def kennzahlen_daten(self):
        return rechnung.kennzahlen(self.db, self.ein, self.gem, self.heute(),
                                   *self.zeitraum_grenzen(self.kz_zeitraum.currentIndex()))

    def kennzahlen_zeigen(self):
        k = self.kz = self.kennzahlen_daten()

        def kachel(key, zahl, unter, farbe=None):
            z, u = self.kz_kacheln[key]
            z.setText(zahl)
            z.setStyleSheet("font-size: 22pt; font-weight: 700;"
                            + (f" color: {stil.umsetzen(farbe)};" if farbe else ""))
            u.setText(unter)
        t = k["treue"]
        kachel("treue", "–" if t is None else f"{t:.0f} %",
               f"{k['puenktlich']} von {k['mit_termin']} Aufträgen am Liefertermin oder früher fertig" if k["mit_termin"]
               else "noch kein fertiger Auftrag mit Liefertermin",
               None if t is None else stil.GRUEN if t >= 90 else stil.ORANGE if t >= 75 else stil.ROT)
        ueber = sum(1 for v in k["verspaetet"] if v["art"] == "überfällig")
        kachel("spaet", str(len(k["verspaetet"])),
               f"{ueber} überfällig, {len(k['verspaetet']) - ueber} werden laut Plan zu spät" if k["verspaetet"]
               else "alle offenen Aufträge liegen im Termin", stil.ROT if k["verspaetet"] else stil.GRUEN)
        d = k["diff_prozent"]
        kachel("kalk", "–" if d is None else f"{d:+.0f} %",
               "noch keine Fertigmeldung im Zeitraum" if d is None else
               f"{k['fertig']} Aufträge liefen im Schnitt {'länger' if d > 0 else 'kürzer'} als kalkuliert"
               if abs(d) >= 0.5 else f"{k['fertig']} Aufträge, Kalkulation und Laufzeit stimmen überein",
               None if d is None or abs(d) < 10 else stil.ORANGE)
        plan_h = sum(m["plan_h"] for m in k["maschinen"])
        plan_kap = sum(m["plan_kap_h"] for m in k["maschinen"])
        last = 100 * plan_h / plan_kap if plan_kap else None
        kachel("last", "–" if last is None else f"{last:.0f} %",
               f"{plan_h:.0f} von {plan_kap:.0f} Stunden auf allen Maschinen verplant".replace(".", ","),
               None if last is None or last <= 100 else stil.ROT)
        self.kz_balken.setzen(k["monate"])

        def prozent(wert):
            return "" if wert is None else f"{wert:.0f} %"
        kopf = ("Maschine", "Letzte 4 Wochen", "Stunden", "Nächste 4 Wochen", "Stunden")
        t = self.kz_maschinen
        t.setColumnCount(len(kopf))
        t.setHorizontalHeaderLabels(kopf)
        t.setRowCount(len(k["maschinen"]))
        for r, m in enumerate(k["maschinen"]):
            texte = (m["maschine"], prozent(m["ist_prozent"]), f"{m['ist_h']:.0f} / {m['kap_h']:.0f}",
                     prozent(m["plan_prozent"]), f"{m['plan_h']:.0f} / {m['plan_kap_h']:.0f}")
            for c, text in enumerate(texte):
                z = _zelle(text, c > 0)
                if c == 3 and m["plan_prozent"] is not None and m["plan_prozent"] > 100:
                    z.setBackground(stil.farbe(stil.ROT_FLAECHE))
                    z.setForeground(stil.farbe(stil.TEXT))
                t.setItem(r, c, z)
        t.resizeColumnsToContents()
        t.setToolTip("Letzte 4 Wochen: tatsächliche Stunden aus den Fertigmeldungen gegen die Kapazität. Nächste 4 "
                     "Wochen: eingeplante Stunden gegen die Kapazität.")
        kopf = ("Auftragsnummer", "Kunde", "Maschine", "Liefertermin", "Fertig (Plan)", "Verspätung")
        t = self.kz_spaet
        t.setColumnCount(len(kopf))
        t.setHorizontalHeaderLabels(kopf)
        t.setRowCount(len(k["verspaetet"]))
        for r, v in enumerate(k["verspaetet"]):
            tage = "" if v["tage"] is None else f"{v['tage']} Tag{'e' if v['tage'] != 1 else ''}"
            texte = (v["nummer"], v["kunde"], v["maschine"], _wtag(v["termin"]), _wtag(v["fertig_plan"]) or "später",
                     f"{v['art']}" + (f", {tage}" if tage else ""))
            for c, text in enumerate(texte):
                z = _zelle(text, daten=v["id"] if c == 0 else None)
                if c == 5:
                    z.setBackground(stil.farbe(stil.ROT_FLAECHE if v["art"] == "überfällig" else stil.GELB_FLAECHE))
                    z.setForeground(stil.farbe(stil.TEXT))
                t.setItem(r, c, z)
        t.resizeColumnsToContents()
        t.horizontalHeader().setStretchLastSection(True)

    def _kennzahl_auftrag(self):
        """Doppelklick auf einen verspäteten Auftrag: im Reiter Aufträge zeigen."""
        r = self.kz_spaet.currentRow()
        if 0 <= r < len(self.kz["verspaetet"]):
            self.filter.setCurrentIndex(0)
            self.suche.clear()
            self.reiter.setCurrentIndex(0)
            self.waehlen(self.kz["verspaetet"][r]["id"])

    def zeitraum_grenzen(self, i=None):
        h, i = self.heute(), self.zeitraum.currentIndex() if i is None else i
        if i == 1:
            return h - datetime.timedelta(days=30), h
        if i == 2:
            return h - datetime.timedelta(days=90), h
        if i == 3:
            return datetime.date(h.year, 1, 1), h
        if i == 4:
            return datetime.date(h.year - 1, 1, 1), datetime.date(h.year - 1, 12, 31)
        return None, None

    def _abw(self, diff, prozent):
        if diff is None:
            return ""
        return f"{'+' if diff > 0 else ''}{self.lz(diff)}" + (
            f" ({prozent:+.0f} %)".replace(".", ",") if prozent is not None else "")

    def soll_ist_daten(self):
        """(Kopf und Zeilen je Maschine, Kopf und Zeilen je Auftrag) als Texte, für Anzeige, CSV und PDF."""
        si = rechnung.soll_ist(self.db, *self.zeitraum_grenzen())
        k1 = ("Maschine", "Aufträge", "Kalkuliert", "Tatsächlich", "Abweichung")
        z1 = [[s["maschine"], str(s["anzahl"]), self.lz(s["kalk_min"]), self.lz(s["ist_min"]),
               self._abw(s["diff_min"], s["diff_prozent"])] for s in si["maschinen"] + [si["gesamt"]]]
        k2 = ("Auftragsnummer", "Kunde", "Maschine", "Liefertermin", "Fertig am", "Kalkulierte Laufzeit",
              "Tatsächliche Laufzeit", "Abweichung")
        z2 = [[a["nummer"], a["kunde"], a["maschine"], _tag(a["liefertermin"]),
               " ".join(t for t in (_tag(a["fertig_am"]), a.get("fertig_um") or "") if t),
               self.lz(a["kalk_min"]), self.lz(a["ist_min"]), self._abw(a["diff_min"], a["diff_prozent"])]
              for a in si["zeilen"]]
        return si, (k1, z1), (k2, z2)

    def stopps_daten(self):
        """(Kopf, Zeilen) der Unterbrechungen nach Grund im gewählten Zeitraum (E6)."""
        liste = rechnung.unterbrechungen(self.db, *self.zeitraum_grenzen())
        gesamt = liste[-1]["minuten"] if liste else 0
        kopf = ("Grund", "Anzahl", "Stillstand", "Anteil")
        return kopf, [[u["grund"], str(u["anzahl"]), self.lz(u["minuten"]) if u["gemessen"] else "",
                       f"{100 * u['minuten'] / gesamt:.0f} %" if gesamt and u["gemessen"] else ""] for u in liste]

    def soll_ist_zeigen(self):
        si, (k1, z1), (k2, z2) = self.soll_ist_daten()
        k3, z3 = self.stopps_daten()
        self.si_stopps_info.setText(
            "Stillstand = Zeit vom Stopp bis zum Weiterlaufen am selben Tag. Stopps über Nacht oder bis zur "
            "Fertigmeldung zählen nur in der Anzahl." if z3 else
            "In diesem Zeitraum ist kein Stopp mit Grund aufgezeichnet. Der Grund wird beim Knopf Stopp abgefragt.")
        g = si["gesamt"]
        if g["anzahl"]:
            p = g["diff_prozent"]
            self.si_info.setText(
                f"{g['anzahl']} fertige Aufträge: kalkuliert {self.lz(g['kalk_min'])}, tatsächlich "
                f"{self.lz(g['ist_min'])}. " + ("" if p is None else (
                    f"Die Aufträge liefen im Schnitt {abs(p):.0f} % {'länger' if p > 0 else 'kürzer'} als kalkuliert."
                    if abs(p) >= 0.5 else "Kalkulation und tatsächliche Laufzeit stimmen überein.")))
        else:
            self.si_info.setText("In diesem Zeitraum ist noch kein Auftrag fertig gemeldet. Die tatsächliche Laufzeit "
                                 "wird bei „Fertig melden“ im Reiter Aufträge eingetragen.")
        self.si_liste.setSortingEnabled(False)
        for tabelle, kopf, zeilen, rechts in ((self.si_maschinen, k1, z1, (1, 2, 3, 4)),
                                             (self.si_stopps, k3, z3, (1, 2, 3)),
                                             (self.si_liste, k2, z2, (5, 6, 7))):
            tabelle.setColumnCount(len(kopf))
            tabelle.setHorizontalHeaderLabels(kopf)
            tabelle.setRowCount(len(zeilen))
            for r, z in enumerate(zeilen):
                for c, t in enumerate(z):
                    tabelle.setItem(r, c, _zelle(t, c in rechts))
            tabelle.resizeColumnsToContents()
        for r, a in enumerate(si["zeilen"]):           # sortieren nach Wert, Abweichung ab 10 % farbig
            for c, wert in ((3, a["liefertermin"] or ""), (4, a["fertig_am"] or ""), (5, a["kalk_min"]),
                            (6, a["ist_min"] or 0), (7, a["diff_min"] or 0)):
                self.si_liste.item(r, c).sortier = wert
            p = a["diff_prozent"]
            if p is not None and abs(p) >= 10:
                z = self.si_liste.item(r, 7)
                z.setBackground(stil.farbe(stil.GELB_FLAECHE if p > 0 else stil.GRUEN_FLAECHE))
                z.setForeground(stil.farbe(stil.TEXT))
        self.si_liste.setSortingEnabled(True)

    def soll_ist_csv(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Soll und Ist als CSV", "Soll-Ist.csv", "CSV (*.csv)")
            if not pfad:
                return None
        import csv
        _si, (k1, z1), (k2, z2) = self.soll_ist_daten()
        with open(pfad, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(k2)
            w.writerows(z2)
            w.writerow([])
            w.writerow(k1)
            w.writerows(z1)
            k3, z3 = self.stopps_daten()
            if z3:
                w.writerow([])
                w.writerow(k3)
                w.writerows(z3)
        return pfad

    def soll_ist_pdf(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Soll und Ist als PDF", "Soll-Ist.pdf", "PDF (*.pdf)")
            if not pfad:
                return None
        _si, (k1, z1), (k2, z2) = self.soll_ist_daten()
        w, seite, p = _pdf_beginnen(pfad, "Soll und Ist")
        f = self.font()
        y = _pdf_titel(p, f, seite, f"Kalkulierte und tatsächliche Laufzeit, {self.zeitraum.currentText()}, Stand "
                                    f"{self.heute().strftime('%d.%m.%Y')}")
        y = _pdf_tabelle(p, f, seite, y, k1, z1, (140, 80, 130, 130, 200)) + 16
        k3, z3 = self.stopps_daten()
        if z3:
            y = _pdf_tabelle(p, f, seite, y, k3, z3, (240, 80, 130, 80)) + 16
        _pdf_tabelle(p, f, seite, y, k2, z2, (120, 220, 80, 90, 90, 130, 130, 170), w)
        p.end()
        return pfad

    # ------------------------------------------------------------------ Einstellungen
    def _seite_einstellungen(self):
        w = QWidget()
        self.e_maschinen = QTableWidget()
        self.e_maschinen.setColumnCount(8)
        self.e_maschinen.setHorizontalHeaderLabels(("Maschine", "Stunden je Tag", "aktiv", "Sperrtage",
                                                    "Übergangszeit davor", "Ausweichmaschine", "Rüstzeit",
                                                    "Größtes Rohr"))
        self.e_maschinen.horizontalHeader().setStretchLastSection(True)
        self.e_maschinen.itemDoubleClicked.connect(lambda _z: self.maschine_bearbeiten())
        self.e_maschinen.verticalHeader().setVisible(False)
        self.e_maschinen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.e_maschinen.setMaximumHeight(200)
        self.k_m_neu = QPushButton("Maschine hinzufügen …")
        self.k_m_aendern = QPushButton("Maschine ändern …")
        self.k_m_weg = QPushButton("Maschine entfernen")
        self.k_m_neu.clicked.connect(lambda _=False: self.maschine_bearbeiten(neu=True))
        self.k_m_aendern.clicked.connect(lambda _=False: self.maschine_bearbeiten())
        self.k_m_weg.clicked.connect(lambda _=False: self.maschine_entfernen())
        g1 = QGroupBox("Maschinen")
        self.g_maschinen = g1
        l1 = QVBoxLayout(g1)
        l1.addWidget(self.e_maschinen)
        z = QHBoxLayout()
        for k in (self.k_m_neu, self.k_m_aendern, self.k_m_weg):
            z.addWidget(k)
        z.addStretch(1)
        l1.addLayout(z)

        self.e_schichten = QTableWidget()
        self.e_schichten.setColumnCount(5)
        self.e_schichten.setHorizontalHeaderLabels(("Schicht", "Beginn", "Ende", "Pause", "Arbeitszeit"))
        self.e_schichten.horizontalHeader().setStretchLastSection(True)
        self.e_schichten.verticalHeader().setVisible(False)
        self.e_schichten.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.e_schichten.setMaximumHeight(150)
        self.e_schichten.itemDoubleClicked.connect(lambda _z: self.schicht_bearbeiten())
        self.k_s_neu = QPushButton("Schicht hinzufügen …")
        self.k_s_aendern = QPushButton("Schicht ändern …")
        self.k_s_weg = QPushButton("Schicht entfernen")
        self.k_s_neu.clicked.connect(lambda _=False: self.schicht_bearbeiten(neu=True))
        self.k_s_aendern.clicked.connect(lambda _=False: self.schicht_bearbeiten())
        self.k_s_weg.clicked.connect(lambda _=False: self.schicht_entfernen())
        g_s = QGroupBox("Schichten")
        l_s = QVBoxLayout(g_s)
        h_s = QLabel("Welche Schichten eine Maschine von Montag bis Freitag fährt, steht bei der Maschine "
                     "(<i>Maschine ändern …</i>), dort auch der Wochenwechsel. Ihre Stunden je Tag ergeben sich dann "
                     "aus den Schichten ohne Pause. Maschinen ohne Schicht behalten ihre Stunden je Tag von Hand.")
        h_s.setWordWrap(True)
        l_s.addWidget(h_s)
        l_s.addWidget(self.e_schichten)
        z = QHBoxLayout()
        self.k_s_hoch, self.k_s_runter = QPushButton("▲"), QPushButton("▼")
        self.k_s_hoch.setToolTip("Schicht in der Liste nach oben")
        self.k_s_runter.setToolTip("Schicht in der Liste nach unten")
        self.k_s_hoch.clicked.connect(lambda _=False: self.schicht_schieben(-1))
        self.k_s_runter.clicked.connect(lambda _=False: self.schicht_schieben(1))
        for k in (self.k_s_neu, self.k_s_aendern, self.k_s_weg, self.k_s_hoch, self.k_s_runter):
            z.addWidget(k)
        z.addStretch(1)
        l_s.addLayout(z)
        h_a = QLabel("<b>Ausnahmen</b> für einzelne Tage oder Zeiträume: Sonderschicht, Kurzarbeit, Brückentag. Ein "
                     "einzelner Tag gilt auch am Samstag und am Feiertag, ein Zeitraum für Montag bis Freitag ohne "
                     "Feiertage.")
        h_a.setWordWrap(True)
        self.e_ausnahmen = QTableWidget()
        self.e_ausnahmen.setColumnCount(4)
        self.e_ausnahmen.setHorizontalHeaderLabels(("Tage", "Maschine", "Schichten", "Grund"))
        self.e_ausnahmen.horizontalHeader().setStretchLastSection(True)
        self.e_ausnahmen.verticalHeader().setVisible(False)
        self.e_ausnahmen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.e_ausnahmen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.e_ausnahmen.setMaximumHeight(150)
        self.e_ausnahmen.itemDoubleClicked.connect(lambda _z: self.ausnahme_bearbeiten())
        self.k_a_neu = QPushButton("Ausnahme hinzufügen …")
        self.k_a_aendern = QPushButton("Ausnahme ändern …")
        self.k_a_weg = QPushButton("Ausnahme entfernen")
        self.k_a_neu.clicked.connect(lambda _=False: self.ausnahme_bearbeiten(neu=True))
        self.k_a_aendern.clicked.connect(lambda _=False: self.ausnahme_bearbeiten())
        self.k_a_weg.clicked.connect(lambda _=False: self.ausnahme_entfernen())
        l_s.addWidget(h_a)
        l_s.addWidget(self.e_ausnahmen)
        z = QHBoxLayout()
        for k in (self.k_a_neu, self.k_a_aendern, self.k_a_weg):
            z.addWidget(k)
        z.addStretch(1)
        l_s.addLayout(z)

        self.e_samstag = QDoubleSpinBox()
        self.e_samstag.setRange(0, 24)
        self.e_samstag.setDecimals(1)
        self.e_samstag.setSuffix(" h")
        self.e_nutzung = QSpinBox()
        self.e_nutzung.setRange(10, 100)
        self.e_nutzung.setSuffix(" %")
        self.e_nutzung.setToolTip("Anteil der Arbeitszeit, der wirklich für Aufträge nutzbar ist (Rüsten, Störungen).")
        self.e_vorlauf = QSpinBox()
        self.e_vorlauf.setRange(0, 30)
        self.e_vorlauf.setSuffix(" Arbeitstage")
        self.e_vorlauf.setToolTip("So viele Arbeitstage liegen zwischen „Laser fertig“ und dem Liefertermin "
                                  "(Nacharbeit, Verpacken, Versand).")
        self.e_schwelle = QSpinBox()
        self.e_schwelle.setRange(0, 20)
        self.e_schwelle.setSuffix(" Arbeitstage")
        self.e_land = QComboBox()
        self.e_land.addItems(feiertage.AUSWAHL)
        self.e_ruhe = QLineEdit()
        self.e_ruhe.setPlaceholderText("z. B. 24.12.2026-31.12.2026; 02.10.2026")
        g2 = QGroupBox("Arbeitszeit und Termine")
        f2 = QFormLayout(g2)
        f2.addRow("Samstag", self.e_samstag)
        f2.addRow("Nutzungsgrad", self.e_nutzung)
        f2.addRow("Feiertage", self.e_land)
        f2.addRow("Betriebsruhe", self.e_ruhe)
        f2.addRow("Vorlauf bis zum Liefertermin", self.e_vorlauf)
        f2.addRow("Termin „knapp“ unter", self.e_schwelle)

        self.e_form = QComboBox()
        for k, t in FORM_TEXT.items():
            self.e_form.addItem(t, k)
        self.e_ohne = QComboBox()
        for k, t in OHNE_TEXT.items():
            self.e_ohne.addItem(t, k)
        self.e_design = QComboBox()
        self.e_design.addItems(stil.THEMES)
        g3 = QGroupBox("Laufzeit und Ansicht")
        f3 = QFormLayout(g3)
        f3.addRow("Laufzeit anzeigen als", self.e_form)
        f3.addRow("Ganze Zahl ohne Einheit bedeutet", self.e_ohne)
        hinweis = QLabel("Bei der Eingabe gehen immer alle Schreibweisen: " + laufzeit.BEISPIELE.replace("z. B. ", "")
                         + ".")
        hinweis.setWordWrap(True)
        f3.addRow("", hinweis)
        f3.addRow("Design", self.e_design)

        self.e_felder = QTableWidget()
        self.e_felder.setColumnCount(1)
        self.e_felder.setHorizontalHeaderLabels(("Zusatzfeld",))
        self.e_felder.horizontalHeader().setStretchLastSection(True)
        self.e_felder.verticalHeader().setVisible(False)
        self.e_felder.setMaximumHeight(160)
        self.k_f_neu = QPushButton("Feld hinzufügen …")
        self.k_f_um = QPushButton("Feld umbenennen …")
        self.k_f_weg = QPushButton("Feld entfernen")
        self.k_f_neu.clicked.connect(lambda _=False: self.feld_bearbeiten(neu=True))
        self.k_f_um.clicked.connect(lambda _=False: self.feld_bearbeiten())
        self.k_f_weg.clicked.connect(lambda _=False: self.feld_entfernen())
        g4 = QGroupBox("Zusatzfelder je Auftrag (für eigene Angaben, z. B. Material, Stückzahl, Bearbeiter)")
        l4 = QVBoxLayout(g4)
        l4.addWidget(self.e_felder)
        z = QHBoxLayout()
        for k in (self.k_f_neu, self.k_f_um, self.k_f_weg):
            z.addWidget(k)
        z.addStretch(1)
        l4.addLayout(z)

        self.e_pfad = QLabel("")
        self.e_pfad.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.e_pfad.setWordWrap(True)
        self.k_db = QPushButton("Datenbank an anderem Ort …")
        self.k_db.setToolTip("Für mehrere Plätze: Datenbank in einen gemeinsamen Ordner legen und an jedem Platz hier "
                             "auswählen. Gibt es am gewählten Ort noch keine, wird die jetzige dorthin kopiert.")
        self.k_sichern = QPushButton("Jetzt sichern")
        self.k_db.clicked.connect(lambda _=False: self.datenbank_waehlen())
        self.k_sichern.clicked.connect(lambda _=False: self.jetzt_sichern())
        g5 = QGroupBox("Datenbank")
        l5 = QVBoxLayout(g5)
        l5.addWidget(self.e_pfad)
        z = QHBoxLayout()
        z.addWidget(self.k_db)
        z.addWidget(self.k_sichern)
        z.addStretch(1)
        l5.addLayout(z)

        # Benutzer und Rechte (Plan B): Anmeldename des Platzes -> Rolle; alle anderen bekommen die Vorgabe-Rolle
        self.e_benutzer = QTableWidget()
        self.e_benutzer.setColumnCount(2)
        self.e_benutzer.setHorizontalHeaderLabels(("Anmeldename (Windows)", "Rolle"))
        self.e_benutzer.horizontalHeader().setStretchLastSection(True)
        self.e_benutzer.verticalHeader().setVisible(False)
        self.e_benutzer.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.e_benutzer.setMaximumHeight(170)
        self.e_benutzer.itemDoubleClicked.connect(lambda _z: self.benutzer_bearbeiten())
        self.k_b_neu = QPushButton("Benutzer hinzufügen …")
        self.k_b_aendern = QPushButton("Benutzer ändern …")
        self.k_b_weg = QPushButton("Benutzer entfernen")
        self.k_b_neu.clicked.connect(lambda _=False: self.benutzer_bearbeiten(neu=True))
        self.k_b_aendern.clicked.connect(lambda _=False: self.benutzer_bearbeiten())
        self.k_b_weg.clicked.connect(lambda _=False: self.benutzer_entfernen())
        self.e_rolle_vorgabe = QComboBox()
        for schluessel, text in D.ROLLEN[1:]:
            self.e_rolle_vorgabe.addItem(text, schluessel)
        self.e_rechte_info = QLabel("")
        self.e_rechte_info.setWordWrap(True)
        rollen_text = QLabel(
            "<b>Verwaltung</b>: alles, auch Einstellungen und Benutzer. <b>Planung</b>: Aufträge anlegen, ändern, "
            "löschen, Reihenfolge, CSV, Papierkorb. <b>Werkstatt</b>: Start, Stopp, fertig melden. <b>Nur lesen</b>: "
            "ansehen und drucken. Ansehen, Terminauskunft und Drucken darf jeder.")
        rollen_text.setWordWrap(True)
        rollen_text.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        g6 = QGroupBox("Benutzer und Rechte")
        l6 = QVBoxLayout(g6)
        l6.addWidget(self.e_rechte_info)
        l6.addWidget(self.e_benutzer)
        z6 = QHBoxLayout()
        for k in (self.k_b_neu, self.k_b_aendern, self.k_b_weg):
            z6.addWidget(k)
        z6.addStretch(1)
        z6.addWidget(QLabel("Alle anderen:"))
        z6.addWidget(self.e_rolle_vorgabe)
        l6.addLayout(z6)
        l6.addWidget(rollen_text)
        # Arbeitsgänge (Plan A): zuschaltbar, Vorgabe aus; Vorlagen für wiederkehrende Abläufe
        self.e_gaenge = QCheckBox("Mehrere Arbeitsgänge je Auftrag verwenden (z. B. Laser, Entgraten, Verzinken)")
        self.e_gaenge.toggled.connect(lambda _an: self.gaenge_schalten())
        gaenge_text = QLabel(
            "Eingeschaltet lässt sich ein Auftrag in Arbeitsgänge teilen, die nacheinander laufen. Jeder Arbeitsgang "
            "hat seinen Arbeitsplatz und seine Laufzeit und wird einzeln gestartet und fertig gemeldet. Weitere "
            "Arbeitsplätze (Entgraten, Schweißen …) werden oben bei den Maschinen angelegt. Fremdarbeit belegt keinen "
            "Arbeitsplatz, sie dauert nur ihre Arbeitstage. Aufträge ohne Arbeitsgänge bleiben, wie sie sind.")
        gaenge_text.setWordWrap(True)
        gaenge_text.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        self.e_vorlagen = QTableWidget()
        self.e_vorlagen.setColumnCount(2)
        self.e_vorlagen.setHorizontalHeaderLabels(("Vorlage", "Arbeitsgänge"))
        self.e_vorlagen.horizontalHeader().setStretchLastSection(True)
        self.e_vorlagen.verticalHeader().setVisible(False)
        self.e_vorlagen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.e_vorlagen.setMaximumHeight(150)
        self.e_vorlagen.itemDoubleClicked.connect(lambda _z: self.vorlage_bearbeiten())
        self.k_v_neu = QPushButton("Vorlage hinzufügen …")
        self.k_v_aendern = QPushButton("Vorlage ändern …")
        self.k_v_weg = QPushButton("Vorlage entfernen")
        self.k_v_neu.clicked.connect(lambda _=False: self.vorlage_bearbeiten(neu=True))
        self.k_v_aendern.clicked.connect(lambda _=False: self.vorlage_bearbeiten())
        self.k_v_weg.clicked.connect(lambda _=False: self.vorlage_entfernen())
        g7 = QGroupBox("Arbeitsgänge")
        l7 = QVBoxLayout(g7)
        l7.addWidget(self.e_gaenge)
        l7.addWidget(gaenge_text)
        l7.addWidget(self.e_vorlagen)
        z7 = QHBoxLayout()
        for k in (self.k_v_neu, self.k_v_aendern, self.k_v_weg):
            z7.addWidget(k)
        z7.addStretch(1)
        l7.addLayout(z7)
        # Grund bei Stopp (E6)
        self.e_stopp = QCheckBox("Beim Stopp nach dem Grund fragen")
        self.e_gruende = QLineEdit()
        self.e_gruende.setPlaceholderText("Störung; Material fehlt; Rüsten; Pause; anderer Auftrag")
        self.e_gruende.setToolTip("Die Gründe zur Auswahl, mit Strichpunkt getrennt. Je Grund erscheint beim Stopp "
                                  "ein Knopf; die Auswertung steht im Reiter Soll und Ist.")
        self.e_stopp.toggled.connect(lambda _an: self.einstellungen_speichern())
        self.e_gruende.editingFinished.connect(self.einstellungen_speichern)
        g8 = QGroupBox("Grund bei Stopp")
        l8 = QFormLayout(g8)
        l8.addRow(self.e_stopp)
        l8.addRow("Gründe", self.e_gruende)
        # Übergabe aus der Kalkulation automatisch erkennen (E9)
        self.e_ordner = QLineEdit()
        self.e_ordner.setPlaceholderText("kein Ordner: Übergabedateien werden nur von Hand eingelesen")
        self.e_ordner.setClearButtonEnabled(True)
        self.k_ordner = QPushButton("Ordner wählen …")
        self.e_ordner.editingFinished.connect(self.einstellungen_speichern)
        self.k_ordner.clicked.connect(lambda _=False: self.uebergabe_ordner_waehlen())
        ordner_text = QLabel(
            "Das Programm schaut etwa jede Minute in diesen Ordner. Liegt dort eine neue Übergabedatei aus der "
            "Kalkulation (Knopf „Übergabe …“ auf der Seite Auslastung), erscheint über der Auftragsliste eine Zeile "
            "mit „Einlesen …“. Übernommen wird erst nach der Rückfrage.")
        ordner_text.setWordWrap(True)
        ordner_text.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        g9 = QGroupBox("Übergabe aus der Kalkulation")
        l9 = QVBoxLayout(g9)
        z9 = QHBoxLayout()
        z9.addWidget(self.e_ordner, 1)
        z9.addWidget(self.k_ordner)
        l9.addLayout(z9)
        l9.addWidget(ordner_text)
        # P2: jede Änderung gilt sofort, ohne Speichern-Knopf
        self.e_fuellt = False
        self.e_rolle_vorgabe.currentIndexChanged.connect(lambda _i: self.rolle_vorgabe_speichern())
        for feld in (self.e_samstag, self.e_nutzung, self.e_vorlauf, self.e_schwelle):
            feld.valueChanged.connect(lambda _w: self.einstellungen_speichern())
        for feld in (self.e_land, self.e_form, self.e_ohne, self.e_design):
            feld.currentIndexChanged.connect(lambda _i: self.einstellungen_speichern())
        self.e_ruhe.editingFinished.connect(self.einstellungen_speichern)
        hinweis = QLabel("Jede Änderung gilt sofort.")
        hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        innen = QWidget()
        lay = QVBoxLayout(innen)
        lay.addWidget(hinweis)
        for g in (g1, g_s, g2, g7, g8, g9, g3, g4, g6, g5):
            lay.addWidget(g)
        lay.addStretch(1)
        rollen = QScrollArea()
        rollen.setWidgetResizable(True)
        rollen.setFrameShape(QFrame.NoFrame)
        rollen.setWidget(innen)
        aussen = QVBoxLayout(w)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(rollen)
        return w

    def einstellungen_zeigen(self):
        self.e_fuellt = True
        try:
            self._einstellungen_fuellen()
        finally:
            self.e_fuellt = False

    def _einstellungen_fuellen(self):
        sch = self.db.schichten()
        self.e_schichten.setRowCount(len(sch))
        for r, x in enumerate(sch):
            for c, t in enumerate((x["name"], x["beginn"], x["ende"], f"{x['pause']} min",
                                   laufzeit.text(int(x["stunden"] * 60 + 0.5), "hm"))):
                self.e_schichten.setItem(r, c, _zelle(t, c > 0))
        self.e_ausnahmen_liste = self.db.ausnahmen()
        self.e_ausnahmen.setRowCount(len(self.e_ausnahmen_liste))
        for r, a in enumerate(self.e_ausnahmen_liste):
            tage = _wtag(a["von"]) + (f" bis {_wtag(a['bis'])}" if a["bis"] != a["von"] else "")
            for c, t in enumerate((tage, a["maschine"] or "alle", " + ".join(a["namen"]) or "frei", a["grund"])):
                self.e_ausnahmen.setItem(r, c, _zelle(t))
        self.e_ausnahmen.resizeColumnsToContents()
        ms = self.db.maschinen()
        self.e_maschinen.setRowCount(len(ms))
        for r, m in enumerate(ms):
            self.e_maschinen.setItem(r, 0, _zelle(m["name"]))
            self.e_maschinen.setItem(r, 1, _zelle(f"{m['stunden_tag']:g}".replace(".", ",") + (
                f"  ({_folge_text(m).lstrip('; ')})" if m["schichten"] or m.get("schichten_sa") else ""), True))
            self.e_maschinen.setItem(r, 2, _zelle("ja" if m["aktiv"] else "nein"))
            self.e_maschinen.setItem(r, 3, _zelle(m["sperrtage"]))
            self.e_maschinen.setItem(r, 4, _zelle(_arbeitstage(m["uebergang_tage"]) if m["uebergang_tage"] else ""))
            self.e_maschinen.setItem(r, 5, _zelle("ja" if m["ausweich"] else "nein"))
            self.e_maschinen.setItem(r, 6, _zelle(f"{int(m['ruest_min'])} min" if m.get("ruest_min") else ""))
            self.e_maschinen.setItem(r, 7, _zelle(", ".join(x for x in (
                f"Ø bis {D.mm_text(m['max_durchmesser'])} mm" if m.get("max_durchmesser") else "",
                f"Länge bis {D.mm_text(m['max_laenge'])} mm" if m.get("max_laenge") else "") if x)))
        gaenge_an = self.db.mit_gaengen()
        self.e_maschinen.setColumnHidden(4, not gaenge_an)
        self.e_maschinen.setHorizontalHeaderItem(0, QTableWidgetItem("Maschine / Arbeitsplatz" if gaenge_an
                                                                     else "Maschine"))
        self.g_maschinen.setTitle("Maschinen und Arbeitsplätze" if gaenge_an else "Maschinen")
        self.e_gaenge.setChecked(gaenge_an)
        vorlagen = self.db.vorlagen()
        self.e_vorlagen.setRowCount(len(vorlagen))
        for r, v in enumerate(vorlagen):
            self.e_vorlagen.setItem(r, 0, _zelle(v["name"]))
            self.e_vorlagen.setItem(r, 1, _zelle(D._plaetze_text(v["gaenge"]) + "  (" + ", ".join(
                g["name"] for g in v["gaenge"]) + ")"))
        self.e_vorlagen.resizeColumnsToContents()
        self.e_vorlagen.horizontalHeader().setStretchLastSection(True)
        for w in (self.e_vorlagen, self.k_v_neu, self.k_v_aendern, self.k_v_weg):
            w.setVisible(gaenge_an)
        self.e_maschinen.resizeColumnsToContents()
        self.e_ordner.setText(self.db.einstellung("uebergabe_ordner") or "")
        self.e_stopp.setChecked(self.db.einstellung("stopp_fragen") == "1")
        self.e_gruende.setText("; ".join(self.db.stoppgruende()))
        self.e_samstag.setValue(self.db.zahl("samstag_stunden"))
        self.e_nutzung.setValue(int(self.db.zahl("nutzungsgrad", 100)))
        self.e_vorlauf.setValue(int(self.db.zahl("vorlauf_tage")))
        self.e_schwelle.setValue(int(self.db.zahl("schwelle_tage", 2)))
        self.e_land.setCurrentText(self.db.einstellung("bundesland"))
        self.e_ruhe.setText(self.db.einstellung("betriebsruhe"))
        self.e_form.setCurrentIndex(max(0, self.e_form.findData(self.db.einstellung("laufzeit_form"))))
        self.e_ohne.setCurrentIndex(max(0, self.e_ohne.findData(self.db.einstellung("ohne_einheit"))))
        self.e_design.setCurrentText(self.db.einstellung("design"))
        felder = self.db.zusatzfelder()
        self.e_felder.setRowCount(len(felder))
        for r, f in enumerate(felder):
            self.e_felder.setItem(r, 0, _zelle(f["name"]))
        self.e_pfad.setText(str(self.db.pfad))
        benutzer = self.db.benutzer()
        self.e_benutzer.setRowCount(len(benutzer))
        for r, b in enumerate(benutzer):
            self.e_benutzer.setItem(r, 0, _zelle(b["name"]))
            self.e_benutzer.setItem(r, 1, _zelle(D.ROLLE_TEXT.get(b["rolle"], b["rolle"])))
        self.e_benutzer.resizeColumnsToContents()
        self.e_benutzer.horizontalHeader().setStretchLastSection(True)
        self.e_rolle_vorgabe.setCurrentIndex(max(0, self.e_rolle_vorgabe.findData(self.db.einstellung("rolle_vorgabe"))))
        self.e_rolle_vorgabe.setEnabled(bool(benutzer))
        self.e_rechte_info.setText(
            f"Die Rechte sind an. Du bist als „{self.db.wer}“ angemeldet." if benutzer else
            "Die Rechte sind aus: Solange kein Benutzer eingetragen ist, darf jeder Platz alles. Mit dem ersten "
            f"Benutzer (Rolle Verwaltung, am besten du selbst: „{self.db.wer}“) gelten sie für alle Plätze.")

    def gaenge_schalten(self):
        """Schalter Arbeitsgänge: gilt sofort. Ausschalten ändert vorhandene Aufträge nicht."""
        if self.e_fuellt:
            return
        self.db.einstellung_setzen("arbeitsgaenge", "1" if self.e_gaenge.isChecked() else "0")
        self.laden()

    def _vorlage_gewaehlt(self):
        r = self.e_vorlagen.currentRow()
        liste = self.db.vorlagen()
        return liste[r] if 0 <= r < len(liste) else None

    def vorlage_bearbeiten(self, neu=False, werte=None):
        """Dialog Vorlage; werte=(Name, [Arbeitsgang …]) überspringt den Dialog (Tests)."""
        v = None if neu else self._vorlage_gewaehlt()
        if not neu and v is None:
            return False
        if werte is None:
            d = QDialog(self)
            d.setWindowTitle("Vorlage für Arbeitsgänge")
            name = QLineEdit(v["name"] if v else "")
            name.setPlaceholderText("z. B. Lasern und verzinken")
            tabelle = GangTabelle(self.db, "vorlage")
            tabelle.setzen(v["gaenge"] if v else ())
            if not v:
                tabelle.hinzu(name="Laser")
            hinweis = QLabel("Die Laufzeit darf hier leer bleiben, sie wird im Auftrag eingetragen. Bei Fremdarbeit "
                             "steht die übliche Dauer in Arbeitstagen.")
            hinweis.setWordWrap(True)
            fehler = QLabel("")
            fehler.setStyleSheet(f"color: {stil.umsetzen(stil.ROT)};")
            kn = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            kn.button(QDialogButtonBox.Save).setText("Speichern")
            kn.button(QDialogButtonBox.Cancel).setText("Abbrechen")

            def speichern():
                try:
                    self.db.vorlage_speichern(name.text(), tabelle.werte(), alt=v["name"] if v else None)
                except D.Fehler as e:
                    fehler.setText(str(e))
                    return
                d.accept()
            kn.accepted.connect(speichern)
            kn.rejected.connect(d.reject)
            form = QFormLayout()
            form.addRow("Name", name)
            lay = QVBoxLayout(d)
            lay.addLayout(form)
            lay.addWidget(tabelle, 1)
            lay.addWidget(hinweis)
            lay.addWidget(fehler)
            lay.addWidget(kn)
            d.resize(820, 380)
            if d.exec() != QDialog.Accepted:
                return False
        else:
            try:
                self.db.vorlage_speichern(werte[0], werte[1], alt=v["name"] if v else None)
            except D.Fehler as e:
                self.meldung(str(e))
                return False
        self.laden()
        return True

    def vorlage_entfernen(self):
        v = self._vorlage_gewaehlt()
        if v is None:
            return False
        self.db.vorlage_loeschen(v["name"])
        self.laden()
        return True

    def _benutzer_gewaehlt(self):
        r = self.e_benutzer.currentRow()
        liste = self.db.benutzer()
        return liste[r] if 0 <= r < len(liste) else None

    def benutzer_bearbeiten(self, neu=False, werte=None):
        """Dialog Benutzer; werte=(Anmeldename, Rolle) überspringt den Dialog (Tests)."""
        b = None if neu else self._benutzer_gewaehlt()
        if not neu and b is None:
            return False
        if werte is None:
            d = QDialog(self)
            d.setWindowTitle("Benutzer")
            form = QFormLayout(d)
            name = QLineEdit(b["name"] if b else ("" if self.db.rechte_an() else self.db.wer))
            name.setPlaceholderText("so wie bei der Windows-Anmeldung, z. B. mueller")
            name.setMinimumWidth(260)
            rolle = QComboBox()
            for schluessel, text in D.ROLLEN:
                rolle.addItem(text, schluessel)
            rolle.setCurrentIndex(max(0, rolle.findData(b["rolle"] if b else
                                                        D.WERKSTATT if self.db.rechte_an() else D.VERWALTUNG)))
            form.addRow("Anmeldename", name)
            form.addRow("Rolle", rolle)
            kn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            kn.button(QDialogButtonBox.Cancel).setText("Abbrechen")
            kn.accepted.connect(d.accept)
            kn.rejected.connect(d.reject)
            form.addRow(kn)
            if d.exec() != QDialog.Accepted:
                return False
            werte = (name.text(), rolle.currentData())
        try:
            self.db.benutzer_speichern(werte[0], werte[1], alt=b["name"] if b else None)
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

    def benutzer_entfernen(self):
        b = self._benutzer_gewaehlt()
        if b is None:
            return False
        try:
            self.db.benutzer_loeschen(b["name"])
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

    def rolle_vorgabe_speichern(self):
        if not self.e_fuellt:
            self.db.einstellung_setzen("rolle_vorgabe", self.e_rolle_vorgabe.currentData())
            self.stand = self.db.stand()

    def einstellungen_speichern(self):
        if self.e_fuellt:
            return
        design_alt = self.db.einstellung("design")
        for k, v in (("samstag_stunden", self.e_samstag.value()), ("nutzungsgrad", self.e_nutzung.value()),
                     ("vorlauf_tage", self.e_vorlauf.value()), ("schwelle_tage", self.e_schwelle.value()),
                     ("bundesland", self.e_land.currentText()), ("betriebsruhe", self.e_ruhe.text().strip()),
                     ("laufzeit_form", self.e_form.currentData()), ("ohne_einheit", self.e_ohne.currentData()),
                     ("design", self.e_design.currentText()),
                     ("uebergabe_ordner", self.e_ordner.text().strip()),
                     ("stopp_fragen", "1" if self.e_stopp.isChecked() else "0"),
                     ("stoppgruende", "; ".join(g.strip() for g in self.e_gruende.text().split(";") if g.strip()))):
            self.db.einstellung_setzen(k, v)
        if self.e_design.currentText() != design_alt:
            from PySide6.QtWidgets import QApplication
            stil.ansicht_wechseln(QApplication.instance(), self, self.e_design.currentText())
        self.statusBar().showMessage("Einstellung gespeichert.", 3000)
        self.aus, self.ein = rechnung.einlasten(self.db, self.heute(), self.wochen.value())
        self.gem = rechnung.gemessen(self.db, self.aus, self.heute())
        self.stand = self.db.stand()

    def uebergabe_ordner_waehlen(self, pfad=None):
        if pfad is None:
            pfad = QFileDialog.getExistingDirectory(self, "Ordner für die Übergabe aus der Kalkulation",
                                                    self.e_ordner.text())
            if not pfad:
                return
        self.e_ordner.setText(str(pfad))
        self.einstellungen_speichern()
        self.uebergabe_pruefen()

    def _maschine_gewaehlt(self):
        r = self.e_maschinen.currentRow()
        return self.db.maschinen()[r] if 0 <= r < self.e_maschinen.rowCount() else None

    def maschine_bearbeiten(self, neu=False, werte=None):
        """Dialog Maschine; werte=(Name, Stunden, aktiv[, Sperrtage[, Übergangszeit[, Ausweichmaschine[, Schichten[,
        Beginn des Wechsels[, Samstagsschichten[, Rüstzeit in Minuten[, größter Durchmesser[, größte Rohrlänge]]]]]]]]])
        überspringt den Dialog (Tests)."""
        m = None if neu else self._maschine_gewaehlt()
        if not neu and m is None:
            return False
        if werte is None:
            d = QDialog(self)
            d.setWindowTitle("Maschine hinzufügen" if neu else "Maschine ändern")
            name = QLineEdit(m["name"] if m else "")
            stunden = QDoubleSpinBox()
            stunden.setRange(0, 24)
            stunden.setDecimals(1)
            stunden.setSuffix(" h")
            stunden.setValue(m["stunden_tag"] if m else 8.0)
            aktiv = QCheckBox("aktiv (wird eingelastet und angezeigt)")
            aktiv.setChecked(bool(m["aktiv"]) if m else True)
            form = QFormLayout(d)
            form.addRow("Name", name)
            form.addRow("Stunden je Tag (Montag bis Freitag)", stunden)
            wochen_k, wechsel, beginn, sa_k = [], QSpinBox(), QDateEdit(), []
            if self.db.schichten():
                alle = self.db.schichten()
                folge = D.schichtfolge(m) if m else []
                wechsel.setRange(1, D.FOLGE_MAX)
                wechsel.setValue(max(1, len(folge)))
                wechsel.setSuffix(" Wochen")
                wechsel.setSpecialValueText("jede Woche gleich")
                wechsel.setToolTip("Wochenwechsel: Die Schichten wechseln von Woche zu Woche und beginnen danach "
                                   "wieder von vorn, z. B. eine Woche Früh, die nächste Spät.")
                start = D._tag_iso(m.get("schicht_start")) if m else None
                montag = self.heute() - datetime.timedelta(days=self.heute().weekday())
                beginn.setCalendarPopup(True)
                beginn.setDisplayFormat("dd.MM.yyyy")
                beginn.setDate(QDate(*(start or montag).timetuple()[:3]))
                beginn.setToolTip("In dieser Woche gilt Woche 1 des Wechsels (es zählt der Montag der Woche).")
                gitter = QGridLayout()
                marken = []
                for w in range(D.FOLGE_MAX):
                    marke = QLabel(f"Woche {w + 1}")
                    gitter.addWidget(marke, w, 0)
                    marken.append(marke)
                    zeile = []
                    for c, x in enumerate(alle):
                        k = QCheckBox(f"{x['name']} ({x['beginn']} bis {x['ende']})")
                        k.setChecked(w < len(folge) and x["name"] in folge[w])
                        gitter.addWidget(k, w, c + 1)
                        zeile.append((k, x))
                    wochen_k.append(zeile)
                gitter.setColumnStretch(len(alle) + 1, 1)
                b_marke = QLabel("Woche 1 beginnt in der Woche vom")

                def rechnen():
                    n = wechsel.value()
                    mo = beginn.date().toPython()
                    jetzt = ((montag - (mo - datetime.timedelta(days=mo.weekday()))).days // 7) % n
                    for w, zeile in enumerate(wochen_k):
                        marken[w].setText(f"Woche {w + 1}" + (" (diese Woche)" if w == jetzt else ""))
                        marken[w].setVisible(n > 1 and w < n)
                        for k, _x in zeile:
                            k.setVisible(w < n)
                    b_marke.setVisible(n > 1)
                    beginn.setVisible(n > 1)
                    summen = [sum(x["stunden"] for k, x in zeile if k.isChecked()) for zeile in wochen_k[:n]]
                    summen = [h for h in summen if h > 0]
                    stunden.setEnabled(not summen)
                    if summen:
                        stunden.setValue(min(24.0, min(summen)))

                for zeile in wochen_k:
                    for k, _x in zeile:
                        k.toggled.connect(lambda _an: rechnen())
                wechsel.valueChanged.connect(lambda _n: rechnen())
                beginn.dateChanged.connect(lambda _d: rechnen())
                form.addRow("Schichten (Montag bis Freitag)", gitter)
                form.addRow("Wochenwechsel über", wechsel)
                form.addRow(b_marke, beginn)
                rechnen()
                hat_sa = [n for n in (m.get("schichten_sa") or "").split(",") if n] if m else []
                z_sa = QHBoxLayout()
                for x in alle:
                    k = QCheckBox(x["name"])
                    k.setChecked(x["name"] in hat_sa)
                    k.setToolTip("Ohne Haken gelten am Samstag die Stunden für alle Maschinen (Arbeitszeit und "
                                 "Termine → Samstag).")
                    z_sa.addWidget(k)
                    sa_k.append((k, x))
                z_sa.addStretch(1)
                form.addRow("Schichten am Samstag", z_sa)
            form.addRow("", aktiv)
            sperre = QLineEdit(m["sperrtage"] if m else "")
            sperre.setPlaceholderText("z. B. 24.11.2026-25.11.2026; 02.12.2026")
            sperre.setToolTip("Tage, an denen nur diese Maschine steht (Wartung, Ausfall). Einzelne Tage oder "
                              "von-bis, mit Semikolon getrennt.")
            sperre.setMinimumWidth(300)
            form.addRow("Sperrtage (Wartung, Ausfall)", sperre)
            ueber = QSpinBox()
            ueber.setRange(0, 60)
            ueber.setSuffix(" Arbeitstage")
            ueber.setValue(int(m["uebergang_tage"] or 0) if m else 0)
            ueber.setToolTip("Nur für Aufträge mit mehreren Arbeitsgängen: So viele Arbeitstage liegen zwischen dem "
                             "Ende des Arbeitsgangs davor und dem Beginn an diesem Arbeitsplatz (Transport, Abkühlen, "
                             "Liegezeit). 0 = es geht am selben Tag weiter.")
            if self.db.mit_gaengen():
                form.addRow("Übergangszeit davor", ueber)
            ausweich = QCheckBox("Ausweichmaschine (kann Aufträge anderer Maschinen übernehmen)")
            ausweich.setChecked(bool(m["ausweich"]) if m else False)
            ausweich.setToolTip("Nur Maschinen mit Häkchen schlägt das Programm bei Terminrisiko als Ausweichmaschine "
                                "vor. Für Arbeitsplätze wie Entgraten oder Schweißen das Häkchen entfernen.")
            form.addRow("", ausweich)
            ruest = QSpinBox()
            ruest.setRange(0, 600)
            ruest.setSuffix(" min")
            ruest.setValue(int(m.get("ruest_min") or 0) if m else 0)
            ruest.setToolTip("So lange dauert das Rüsten vor jedem Auftrag auf dieser Maschine. Das Programm rechnet "
                             "die Zeit zu jedem Auftrag dazu, außer direkt davor läuft das gleiche Material. Im "
                             "Auftrag lässt sich die Zeit einzeln ändern. 0 = ohne Rüstzeit rechnen.")
            form.addRow("Rüstzeit je Auftrag", ruest)
            max_d, max_l = QDoubleSpinBox(), QDoubleSpinBox()
            for feld, wert, tipp in ((max_d, m.get("max_durchmesser") if m else 0, "Durchmesser oder Außenmaß"),
                                     (max_l, m.get("max_laenge") if m else 0, "Rohrlänge")):
                feld.setRange(0, 99999)
                feld.setDecimals(1)
                feld.setSuffix(" mm")
                feld.setSpecialValueText("keine Grenze")
                feld.setValue(float(wert or 0))
                feld.setToolTip(f"Größte {tipp}, die diese Maschine kann. Aufträge mit größerem Rohr legt das "
                                "Programm nie auf diese Maschine, auch nicht als Ausweichmaschine oder in der "
                                "automatischen Optimierung. 0 = keine Grenze.")
            z_rohr = QHBoxLayout()
            z_rohr.addWidget(QLabel("Durchmesser bis"))
            z_rohr.addWidget(max_d)
            z_rohr.addSpacing(12)
            z_rohr.addWidget(QLabel("Länge bis"))
            z_rohr.addWidget(max_l)
            z_rohr.addStretch(1)
            form.addRow("Größtes Rohr", z_rohr)
            kn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            kn.button(QDialogButtonBox.Cancel).setText("Abbrechen")
            kn.accepted.connect(d.accept)
            kn.rejected.connect(d.reject)
            form.addRow(kn)
            if d.exec() != QDialog.Accepted:
                return False
            werte = (name.text(), stunden.value(), aktiv.isChecked(), sperre.text(), ueber.value(),
                     ausweich.isChecked(),
                     [[x["name"] for k, x in zeile if k.isChecked()] for zeile in wochen_k[:wechsel.value()]]
                     if len(wochen_k) and wechsel.value() > 1 else
                     [x["name"] for k, x in (wochen_k[0] if wochen_k else []) if k.isChecked()],
                     beginn.date().toPython(), [x["name"] for k, x in sa_k if k.isChecked()],
                     ruest.value(), max_d.value(), max_l.value())
        try:
            self.db.maschine_speichern(werte[0], werte[1], werte[2], alt=m["name"] if m else None,
                                       sperrtage=werte[3] if len(werte) > 3 else None,
                                       uebergang=werte[4] if len(werte) > 4 else None,
                                       ausweich=werte[5] if len(werte) > 5 else None,
                                       schichten=werte[6] if len(werte) > 6 else None,
                                       schicht_start=werte[7] if len(werte) > 7 else None,
                                       samstag=werte[8] if len(werte) > 8 else None,
                                       ruest=werte[9] if len(werte) > 9 else None,
                                       max_durchmesser=werte[10] if len(werte) > 10 else None,
                                       max_laenge=werte[11] if len(werte) > 11 else None)
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

    def schicht_bearbeiten(self, neu=False, werte=None):
        """Dialog Schicht; werte=(Name, Beginn, Ende, Pause in Minuten) überspringt den Dialog (Tests)."""
        liste = self.db.schichten()
        r = self.e_schichten.currentRow()
        if not neu and not 0 <= r < len(liste):
            return False
        alt = None if neu else liste[r]
        if werte is None:
            d = QDialog(self)
            d.setWindowTitle("Schicht hinzufügen" if neu else "Schicht ändern")
            name = QLineEdit(alt["name"] if alt else "")
            beginn = QLineEdit(alt["beginn"] if alt else "06:00")
            ende = QLineEdit(alt["ende"] if alt else "14:00")
            pause = QSpinBox()
            pause.setRange(0, 240)
            pause.setSuffix(" min")
            pause.setValue(alt["pause"] if alt else 30)
            form = QFormLayout(d)
            form.addRow("Name", name)
            form.addRow("Beginn (Uhrzeit)", beginn)
            form.addRow("Ende (Uhrzeit, auch nach Mitternacht)", ende)
            form.addRow("Pause", pause)
            kn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            kn.button(QDialogButtonBox.Cancel).setText("Abbrechen")
            kn.accepted.connect(d.accept)
            kn.rejected.connect(d.reject)
            form.addRow(kn)
            if d.exec() != QDialog.Accepted:
                return False
            werte = (name.text(), beginn.text(), ende.text(), pause.value())
        eintrag = dict(name=werte[0], beginn=werte[1], ende=werte[2], pause=werte[3])
        try:
            if alt and alt["name"] != str(werte[0]).strip():      # umbenannt: die Maschinen ziehen mit
                D._schicht(*werte)
                self.db.schicht_umbenennen(alt["name"], str(werte[0]).strip())
            self.db.schichten_setzen(liste + [eintrag] if neu else [eintrag if i == r else x
                                                                    for i, x in enumerate(liste)])
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

    def schicht_schieben(self, richtung):
        """Gewählte Schicht in der Liste nach oben (-1) oder unten (1)."""
        liste = self.db.schichten()
        r = self.e_schichten.currentRow()
        if not 0 <= r < len(liste) or not 0 <= r + richtung < len(liste):
            return False
        liste[r], liste[r + richtung] = liste[r + richtung], liste[r]
        self.db.schichten_setzen(liste)
        self.laden()
        self.e_schichten.selectRow(r + richtung)
        return True

    def ausnahme_bearbeiten(self, neu=False, werte=None):
        """Dialog Ausnahme im Schichtkalender; werte=(Maschine oder '', von, bis, [Schichten], Grund) überspringt
        den Dialog (Tests)."""
        r = self.e_ausnahmen.currentRow()
        liste = self.db.ausnahmen()
        if not neu and not 0 <= r < len(liste):
            return False
        alt = None if neu else liste[r]
        if werte is None:
            d = QDialog(self)
            d.setWindowTitle("Ausnahme hinzufügen" if neu else "Ausnahme ändern")
            wahl = QComboBox()
            wahl.addItem("alle Maschinen", "")
            for m in self.db.maschinen():
                wahl.addItem(m["name"], m["name"])
            wahl.setCurrentIndex(max(0, wahl.findData(alt["maschine"] if alt else "")))
            von, bis = QDateEdit(), QDateEdit()
            for feld, tag in ((von, alt["von"] if alt else self.heute()), (bis, alt["bis"] if alt else self.heute())):
                feld.setCalendarPopup(True)
                feld.setDisplayFormat("dd.MM.yyyy")
                feld.setDate(QDate(*tag.timetuple()[:3]))
            von.dateChanged.connect(lambda tag: bis.setDate(tag) if bis.date() < tag else None)
            kaesten = []
            z = QHBoxLayout()
            for x in self.db.schichten():
                k = QCheckBox(f"{x['name']} ({x['beginn']} bis {x['ende']})")
                k.setChecked(bool(alt) and x["name"] in alt["namen"])
                z.addWidget(k)
                kaesten.append((k, x))
            z.addStretch(1)
            grund = QLineEdit(alt["grund"] if alt else "")
            grund.setPlaceholderText("z. B. Sonderschicht, Kurzarbeit, Brückentag")
            hinweis = QLabel("Ohne Haken wird an diesen Tagen nicht gearbeitet.")
            hinweis.setEnabled(False)
            form = QFormLayout(d)
            form.addRow("Maschine", wahl)
            form.addRow("Von", von)
            form.addRow("Bis", bis)
            form.addRow("Schichten an diesen Tagen", z)
            form.addRow("", hinweis)
            form.addRow("Grund", grund)
            kn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            kn.button(QDialogButtonBox.Cancel).setText("Abbrechen")
            kn.accepted.connect(d.accept)
            kn.rejected.connect(d.reject)
            form.addRow(kn)
            if d.exec() != QDialog.Accepted:
                return False
            werte = (wahl.currentData(), von.date().toPython(), bis.date().toPython(),
                     [x["name"] for k, x in kaesten if k.isChecked()], grund.text())
        try:
            self.db.ausnahme_speichern(werte[0], werte[1], werte[2], werte[3], werte[4] if len(werte) > 4 else "",
                                       id=alt["id"] if alt else None)
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

    def ausnahme_entfernen(self):
        r = self.e_ausnahmen.currentRow()
        liste = self.db.ausnahmen()
        if not 0 <= r < len(liste):
            return False
        self.db.ausnahme_entfernen(liste[r]["id"])
        self.laden()
        return True

    def schicht_entfernen(self):
        liste = self.db.schichten()
        r = self.e_schichten.currentRow()
        if not 0 <= r < len(liste):
            return False
        self.db.schichten_setzen([x for i, x in enumerate(liste) if i != r])
        self.laden()
        return True

    def maschine_entfernen(self):
        m = self._maschine_gewaehlt()
        if m is None:
            return False
        try:
            self.db.maschine_loeschen(m["name"])
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

    def _feld_gewaehlt(self):
        r = self.e_felder.currentRow()
        return self.e_felder.item(r, 0).text() if r >= 0 and self.e_felder.item(r, 0) else None

    def feld_bearbeiten(self, neu=False, name=None):
        alt = None if neu else self._feld_gewaehlt()
        if not neu and alt is None:
            return False
        if name is None:
            name, ok = QInputDialog.getText(self, "Zusatzfeld", "Name des Feldes", text=alt or "")
            if not ok:
                return False
        try:
            self.db.zusatzfeld_speichern(name, alt=alt)
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

    def feld_entfernen(self, fragen=True):
        name = self._feld_gewaehlt()
        if name is None:
            return False
        n = self.db.zusatz_gefuellt(name)
        if n and fragen and QMessageBox.question(
                self, NAME, f"Das Feld „{name}“ ist bei {n} Aufträgen ausgefüllt. Feld und Inhalte löschen?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        self.db.zusatzfeld_loeschen(name)
        self.laden()
        return True

    def jetzt_sichern(self):
        ziel = self.db.sichern(datetime.datetime.now().strftime("%H%M%S"))
        self.statusBar().showMessage(f"Gesichert: {ziel}", 8000)
        return ziel

    def datenbank_waehlen(self, pfad=None):
        """Datenbank an einem anderen Ort öffnen (gemeinsamer Ordner). Gibt es dort keine, wird die jetzige kopiert."""
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Ort der Datenbank", str(self.db.pfad), "Datenbank (*.db)",
                                                  options=QFileDialog.DontConfirmOverwrite)
            if not pfad:
                return False
        pfad = Path(pfad)
        if pfad.resolve() == self.db.pfad.resolve():
            return False
        if not pfad.exists():
            import shutil
            pfad.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.db.pfad, pfad)
        try:
            neu = D.Daten(pfad)
        except (D.Fehler, OSError, Exception) as e:      # noqa: BLE001 – auch keine SQLite-Datei
            self.meldung(f"Die Datenbank lässt sich nicht öffnen: {e}")
            return False
        self.db.schliessen()
        self.db = neu
        ort.datenbank_merken(pfad)
        self.stand = self.db.stand()
        self.statusBar().showMessage(f"Datenbank: {pfad}")
        self.laden()
        return True

    # ------------------------------------------------------------------ Hilfe
    def _seite_hilfe(self):
        self.hilfe = QTextBrowser()
        self.hilfe.setOpenExternalLinks(False)
        self.hilfe.setHtml(hilfe.html())
        seite = QWidget()
        lay = QVBoxLayout(seite)
        zeile = QHBoxLayout()
        self.update_stand = QLabel(f"Installiert: {self.updater.stand()}")
        self.k_update = QPushButton("Nach Updates suchen")
        self.k_update.setToolTip("Sieht online nach einer neueren Version. Geladen werden nur die geänderten Dateien; "
                                 "eingespielt wird erst nach einem Klick auf „Jetzt aktualisieren“.")
        self.k_update.clicked.connect(lambda _=False: self.updater.suchen())
        zeile.addWidget(self.update_stand)
        zeile.addStretch(1)
        zeile.addWidget(self.k_update)
        lay.addLayout(zeile)
        lay.addWidget(self.hilfe, 1)
        return seite

    # ------------------------------------------------------------------ alles
    def laden(self):
        """Neu rechnen und den sichtbaren Reiter füllen."""
        self.aus, self.ein = rechnung.einlasten(self.db, self.heute(), self.wochen.value())
        self.gem = rechnung.gemessen(self.db, self.aus, self.heute())
        if self.woche and self.woche[0] not in self.ein["maschinen"]:
            self.woche = None
        self.rechte_setzen()
        i = self.reiter.currentIndex()
        if self.werkstatt_ist_an():
            self.werkstatt_zeigen()
        elif i == 0:
            self.auftraege_zeigen()
        elif i == 1:
            self.auslastung_zeigen()
        elif i == 2:
            self.soll_ist_zeigen()
        elif i == 3:
            self.kennzahlen_zeigen()
        elif i == EINSTELLUNGEN:
            self.einstellungen_zeigen()
        self.stand = self.db.stand()


def QApplicationModal():
    """Ist gerade ein Dialog offen? Dann nicht unter ihm neu laden."""
    from PySide6.QtWidgets import QApplication
    return QApplication.activeModalWidget() is not None


def _pdf_beginnen(pfad, titel, gross=False):
    w = QPdfWriter(str(pfad))
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.A3 if gross else QPageSize.A4), QPageLayout.Landscape,
                                QMarginsF(12, 12, 12, 12)))
    w.setResolution(96)
    w.setTitle(titel)
    return w, w.pageLayout().paintRectPixels(96), QPainter(w)


def _pdf_titel(p, f, seite, text):
    f = type(f)(f)
    f.setPointSizeF(13)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#1F2937"))                   # fest: PDF, immer dunkle Schrift auf Weiß
    p.drawText(QRectF(0, 0, seite.width(), 24), Qt.AlignLeft | Qt.AlignVCenter, text)
    f.setPointSizeF(8.5)
    f.setBold(False)
    p.setFont(f)
    return 30


def _pdf_tabelle(p, f, seite, y, kopf, zeilen, breiten, writer=None, hoehe=14):
    """Einfache Tabelle; mit writer läuft sie über mehrere Seiten. Ergebnis: y nach der letzten Zeile."""
    fm = QFontMetrics(p.font())

    def zeile(texte, y, fett=False):
        x = 0
        schrift = p.font()
        schrift.setBold(fett)
        p.setFont(schrift)
        for t, b in zip(texte, breiten):
            p.drawText(QRectF(x, y, b - 6, hoehe), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(str(t), Qt.ElideRight, b - 6))
            x += b
        if hoehe > 14:                            # Arbeitsliste: Linie unter jeder Zeile zum Abhaken
            p.drawLine(QPointF(0, y + hoehe), QPointF(sum(breiten), y + hoehe))
    zeile(kopf, y, True)
    y += hoehe + 2
    for z in zeilen:
        if y > seite.height() - 16:
            if writer is None:
                break
            writer.newPage()
            y = 0
            zeile(kopf, y, True)
            y += hoehe + 2
        zeile(z, y)
        y += hoehe
    return y
