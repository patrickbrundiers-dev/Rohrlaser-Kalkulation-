"""Fenster des Programms Rohrlaser Auslastung: Reiter Aufträge, Auslastung, Soll und Ist, Kennzahlen, Einstellungen; dazu die
Werkstatt-Ansicht (große Schrift, große Knöpfe) für den Platz an der Maschine."""
import datetime
import html
import re
from pathlib import Path

from PySide6.QtCore import QDate, QEvent, QMarginsF, QPointF, QRectF, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QKeySequence, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen,
                           QPolygonF)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QCompleter, QDateEdit, QDialog,
                               QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGraphicsScene, QGraphicsView, QGridLayout,
                               QGroupBox, QHBoxLayout,
                               QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget,
                               QTextBrowser, QTimeEdit, QToolTip, QVBoxLayout, QWidget)
from rohrlaser import einlastung, feiertage, stil
from rohrlaser.auslastung_grafik import RISIKO_TEXT, Plantafel, WochenBalken, spalten_daten

from . import NAME, VERSION, aktualisierung_fenster, austausch, hilfe, laufzeit, ort, rechnung, schnittstelle, warnungen
from . import daten as D

FILTER = ("offene Aufträge", "fertige Aufträge", "alle Aufträge")
EINSTELLUNGEN, HILFE = 4, 5                       # Reiter: 0 Aufträge, 1 Auslastung, 2 Soll und Ist, 3 Kennzahlen
ZEITRAUM = ("alle", "letzte 30 Tage", "letzte 90 Tage", "dieses Jahr", "letztes Jahr")
FORM_TEXT = {"hm": "1 h 30 min", "uhr": "1:30 h", "dez": "1,50 h (Dezimalstunden)", "min": "90 min (nur Minuten)"}
OHNE_TEXT = {"min": "Minuten (90 = 90 Minuten)", "h": "Stunden (2 = 2 Stunden)"}
RISIKO_FARBE = {einlastung.UEBER: stil.ROT_FLAECHE, einlastung.KNAPP: stil.GELB_FLAECHE}
# Plantafel (ab 1.6): Balkenfarben, in beiden Designs gleich, weiße Schrift darauf
TAFEL_FARBE = ("Terminrisiko", "Kunde", "Status")
# N4: was in der zweiten Zeile eines Balkens steht (je Platz wählbar); Vorgabe wie bisher Kunde und Restlaufzeit
BALKEN_FELDER = {"kunde": "Kunde", "rest": "Restlaufzeit", "termin": "Liefertermin", "stueck": "Stückzahl",
                 "material": "Material", "bemerkung": "Bemerkung"}
BALKEN_VORGABE = ("kunde", "rest")
MONAT_ZOOM = "Monat"
MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember")
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
        self.stueck, self.mit_zusatz, self.R = 1, False, None   # Plan 2.6: Zusatzschritte mit Zeit aus Anzahl
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
        self.k_zusatz = QPushButton("Zusatzschritt ändern …")
        self.k_zusatz.setToolTip("Anzahl Gewinde, Nieten, Nähte … des gewählten Zusatzschritts ändern. Auch mit "
                                 "Doppelklick auf seine Laufzeit.")
        self.k_zusatz.clicked.connect(lambda _=False: self.zusatz_bearbeiten())
        self.k_zusatz.hide()
        self.tabelle.cellDoubleClicked.connect(self._doppelklick)
        self.vorlage = QComboBox()
        self.vorlage.addItem("Vorlage übernehmen …")
        for v in db.vorlagen():
            self.vorlage.addItem(v["name"], v["gaenge"])
        self.vorlage.activated.connect(self._vorlage)
        self.vorlage.setVisible(art == "gaenge" and self.vorlage.count() > 1)
        unten = QHBoxLayout()
        for k in (self.k_neu, self.k_weg, self.k_hoch, self.k_runter, self.k_zusatz):
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
                            gleichzeitig=bool(g.get("gleichzeitig")), status=g.get("status") or "",
                            zusatz=D.Z.positionen(g.get("zusatz"))) for g in gaenge]
        self._zeigen()

    # ---------------------------------------------------------------- Plan 2.6: Zusatzschritte
    def zusatz_erlauben(self, an, stueck=1):
        self.mit_zusatz, self.stueck = bool(an) and self.art == "gaenge", max(1, int(stueck or 1))
        self.k_zusatz.setVisible(self.mit_zusatz)

    def richtzeiten(self):
        if self.R is None:
            self.R = self.db.richtzeiten()
        return self.R

    def rechenweg(self, z):
        """(Laufzeit als Text, Rechenweg) einer Zeile mit Zusatzschritt; None ohne Zusatzschritt."""
        if not z.get("zusatz"):
            return None
        try:
            minuten, tage, text = D.Z.zeit(z["zusatz"], self.stueck, self.richtzeiten())
        except ValueError as e:
            return z["zeit"], str(e)
        if tage:
            return _arbeitstage(tage), text + f"; abholen und anliefern {D.Z.tage_text(self.db.fremd_tage())}"
        return laufzeit.text(minuten, self.db.einstellung("laufzeit_form")), text

    def stueck_setzen(self, n):
        """Stückzahl geändert: die Zeit der Zusatzschritte neu rechnen (fertig gemeldete bleiben)."""
        self._holen()
        self.stueck = max(1, int(n or 1))
        for z in self.zeilen:
            if z.get("zusatz") and z["status"] != D.FERTIG:
                z["zeit"] = self.rechenweg(z)[0]
        self._zeigen(self.tabelle.currentRow())

    def _doppelklick(self, r, c):
        if c == 2 and 0 <= r < len(self.zeilen) and self.zeilen[r].get("zusatz"):
            self.zusatz_bearbeiten(r)

    def zusatz_bearbeiten(self, zeile=None, neu=False, oeffnen=True):
        """Dialog für einen Zusatzschritt: neu (hinten anhängen) oder die gewählte Zeile ändern. oeffnen=False gibt
        den Dialog zurück, ohne ihn zu zeigen (Tests). Ergebnis: True, wenn eine Zeile dazukam oder sich änderte."""
        self._holen()
        r = self.tabelle.currentRow() if zeile is None else zeile
        alt = None if neu or not (0 <= r < len(self.zeilen)) else self.zeilen[r]
        if alt is not None and (not alt.get("zusatz") or alt["status"] == D.FERTIG):
            alt = None
            neu = True
        if alt is None and not neu:
            return False
        dlg = ZusatzDialog(self.db, self.richtzeiten(), self.stueck, self.plaetze, alt, self)
        if not oeffnen:
            return dlg
        if dlg.exec() != QDialog.Accepted:
            return False
        return self.zusatz_uebernehmen(dlg.werte(), None if alt is None else r)

    def zusatz_uebernehmen(self, w, zeile=None):
        """Ergebnis des Zusatzschritt-Dialogs eintragen (zeile None: neue Zeile hinten)."""
        self._holen()
        namen = {z["name"] for i, z in enumerate(self.zeilen) if i != zeile}
        name, n = w["name"], 2
        while name in namen:
            name, n = f"{w['name']} {n}", n + 1
        if zeile is None:
            self.zeilen.append(dict(id=None, name=name, platz=w["platz"], zeit="", status="", gleichzeitig=False,
                                    zusatz=w["zusatz"]))
            zeile = len(self.zeilen) - 1
        else:
            self.zeilen[zeile].update(name=name, platz=w["platz"], zusatz=w["zusatz"])
        self.zeilen[zeile]["zeit"] = self.rechenweg(self.zeilen[zeile])[0]
        self._zeigen(zeile)
        return True

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
            weg = self.rechenweg(z)
            if weg is not None:                   # Plan 2.6: Zeit kommt aus der Anzahl, Rechenweg als Hinweis
                zeit.setFlags(zeit.flags() & ~Qt.ItemIsEditable)
                zeit.setToolTip(f"{weg[1]}\nÄndern: Doppelklick oder „Zusatzschritt ändern …“.")
                name.setToolTip(weg[1])
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
        self.zeilen.append(dict(id=None, name=name, platz=platz, zeit=zeit, status="", zusatz=[],
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
            g = dict(id=z["id"], name=z["name"], platz=z["platz"], kalk_min=0, tage=0, zusatz=z.get("zusatz") or [],
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


class ZusatzDialog(QDialog):
    """Plan 2.6 (Z4): ein Zusatzschritt (Gewinde schneiden, Senken, Bohren, Nieten, Schweißen, Verzinken …) mit der
    Anzahl je Teil; die Laufzeit rechnet das Programm aus den Richtzeiten und zeigt den Rechenweg."""

    def __init__(self, db, richtzeiten, stueck, plaetze, zeile=None, parent=None):
        super().__init__(parent)
        self.db, self.R, self.stueck = db, richtzeiten, max(1, int(stueck or 1))
        self.setWindowTitle("Zusatzschritt ändern" if zeile else "Zusatzschritt hinzufügen")
        self.schritt = QComboBox()
        for schritt, _arten in D.Z.schritte(richtzeiten):
            self.schritt.addItem(schritt)
        alt = {(p["schritt"], p["art"]): p["anzahl"] for p in (zeile or {}).get("zusatz") or ()}
        if zeile and zeile.get("zusatz"):
            self.schritt.setCurrentText(zeile["zusatz"][0]["schritt"])
        self.alt = alt
        self.platz = QComboBox()
        for p in plaetze:
            self.platz.addItem(p, p)
        self.platz.addItem("Fremdarbeit (außer Haus)", D.FREMD)
        self.wunsch_platz = (zeile or {}).get("platz")
        self.arten = QWidget()
        self.arten_lay = QGridLayout(self.arten)
        self.arten_lay.setContentsMargins(0, 0, 0, 0)
        self.felder = []
        self.ergebnis = QLabel("")
        self.ergebnis.setWordWrap(True)
        self.ergebnis.setTextFormat(Qt.RichText)
        self.ergebnis.setMinimumWidth(420)
        form = QFormLayout()
        form.addRow("Zusatzschritt", self.schritt)
        form.addRow("Anzahl je Teil", self.arten)
        form.addRow("Arbeitsplatz", self.platz)
        form.addRow("Stückzahl", QLabel(f"{self.stueck} Stück (im Auftrag)"))
        form.addRow("Laufzeit", self.ergebnis)
        self.form = form
        hinweis = QLabel("Die Zeiten je Stück stehen in Einstellungen → Termine und Abläufe → Zusatzschritte. "
                         "„Schätzwert“ heißt: noch nicht an euren Fertigmeldungen geprüft.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen")
        self.knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        self.knoepfe.accepted.connect(self.accept)
        self.knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(hinweis)
        lay.addWidget(self.knoepfe)
        self.schritt.currentIndexChanged.connect(lambda _i: self._arten_bauen())
        self.platz.currentIndexChanged.connect(lambda _i: self.rechnen())
        self._arten_bauen()

    def _arten(self):
        return dict(D.Z.schritte(self.R)).get(self.schritt.currentText(), [])

    def _arten_bauen(self):
        while self.arten_lay.count():
            w = self.arten_lay.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self.felder = []
        arten = self._arten()
        fremd = bool(arten) and all(D.Z.fremd(r) for r in arten)
        for i, r in enumerate(arten):
            if fremd:
                break
            feld = QSpinBox()
            feld.setRange(0, 9999)
            feld.setValue(int(self.alt.get((r["schritt"], r["art"] or ""), 0)))
            feld.valueChanged.connect(lambda _w: self.rechnen())
            self.arten_lay.addWidget(QLabel(r["art"] or r["schritt"]), i, 0)
            self.arten_lay.addWidget(feld, i, 1)
            info = QLabel(f"je {D.Z._sek(float(r['je_s'] or 0))}" + (" (Schätzwert)" if r.get("geschaetzt") else ""))
            info.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
            self.arten_lay.addWidget(info, i, 2)
            self.felder.append((r, feld))
        if fremd:
            self.arten_lay.addWidget(QLabel("keine Anzahl nötig (Fremdarbeit)"), 0, 0)
        platz = self.wunsch_platz if self.wunsch_platz is not None and self.alt else (arten[0]["platz"] if arten
                                                                                         else None)
        if fremd:
            platz = D.FREMD
        i = self.platz.findData(platz) if platz is not None else -1
        if i < 0 and platz:                       # Arbeitsplatz fehlt noch in den Maschinen: trotzdem anbieten
            self.platz.insertItem(self.platz.count() - 1, platz, platz)
            i = self.platz.findData(platz)
        self.platz.setCurrentIndex(max(0, i))
        self.platz.setEnabled(not fremd)
        self.rechnen()

    def positionen(self):
        arten = self._arten()
        if arten and all(D.Z.fremd(r) for r in arten):
            return [dict(schritt=arten[0]["schritt"], art=arten[0]["art"] or "", anzahl=1.0)]
        return [dict(schritt=r["schritt"], art=r["art"] or "", anzahl=float(f.value())) for r, f in self.felder
                if f.value() > 0]

    def rechnen(self):
        """Laufzeit und Rechenweg zeigen; Übernehmen erst, wenn eine Anzahl da ist."""
        ok = self.knoepfe.button(QDialogButtonBox.Ok)
        try:
            minuten, tage, text = D.Z.zeit(self.positionen(), self.stueck, self.R)
        except ValueError as e:
            self.ergebnis.setText(f"<span style='color:{stil.umsetzen(stil.TEXT_GRAU)}'>{html.escape(str(e))}</span>")
            ok.setEnabled(False)
            return None
        ok.setEnabled(True)
        if tage:
            haupt = (f"<b>{tage} Arbeitstage außer Haus</b><br>Abholung und Anlieferung "
                     f"{html.escape(D.Z.tage_text(self.db.fremd_tage()))}")
        else:
            haupt = (f"<b>{html.escape(laufzeit.lang(minuten))}</b><br>"
                     f"<span style='color:{stil.umsetzen(stil.TEXT_GRAU)}'>{html.escape(text)}</span>")
        self.ergebnis.setText(haupt)
        return minuten, tage, text

    def werte(self):
        return dict(name=self.schritt.currentText(), platz=self.platz.currentData(), zusatz=self.positionen())


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
        self.stand = db.auftrag_stand(self.auftrag["id"]) if self.auftrag.get("id") else None   # Plan 3.4
        self.setWindowTitle("Auftrag ändern" if self.auftrag.get("id") else
                            "Wiederholauftrag" if self.auftrag.get("wiederholung") else "Neuer Auftrag")
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
        # N4 (Plan 2.2): bei neuen Aufträgen gleich sehen, wann sie frühestens fertig wären
        self.frueh = QLabel("")
        self.frueh.setWordWrap(True)
        self.frueh.setTextFormat(Qt.RichText)
        self.k_frueh = QPushButton("Als Liefertermin")
        self.k_frueh.setToolTip("Setzt den Liefertermin auf „lieferbar ab“ der gewählten Maschine.")
        self.k_frueh.clicked.connect(lambda _=False: self.frueh_uebernehmen())
        self.k_frueh.hide()
        self.frueh_liste = []
        zeile_f = QHBoxLayout()
        zeile_f.addWidget(self.frueh, 1)
        zeile_f.addWidget(self.k_frueh)
        self.frueh_uhr = QTimer(self)
        self.frueh_uhr.setSingleShot(True)
        self.frueh_uhr.setInterval(400)
        self.frueh_uhr.timeout.connect(self.frueh_zeigen)
        self.finished.connect(lambda _r: self.frueh_uhr.stop())
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
        # Plan 2.6: Stückzahl und Zusatzschritte (Gewinde, Nieten, Schweißen …) mit Zeit aus der Anzahl
        self.mit_zusatz = self.mit_gaengen and (austausch.zusatz_an(db) or any(
            g.get("zusatz") for g in self.auftrag.get("gaenge") or ()))
        self.stueck = QSpinBox()
        self.stueck.setRange(1, 10 ** 7)
        self.stueck.setValue(int(self.auftrag.get("stueckzahl") or 1))
        self.stueck.setSuffix(" Stück")
        self.stueck.setToolTip("Stückzahl des Auftrags. Die Zeit der Zusatzschritte rechnet sich daraus.")
        self.k_zusatz = QPushButton("+ Zusatzschritt …")
        self.k_zusatz.setToolTip("Gewinde schneiden, Senken, Bohren, Nieten, Schweißen, Verzinken, Pulvern: Anzahl je "
                                 "Teil eingeben, das Programm rechnet die Laufzeit.")
        self.k_zusatz.clicked.connect(lambda _=False: self.zusatz_neu())
        self.gaenge.zusatz_erlauben(self.mit_zusatz, self.stueck.value())
        self.stueck.valueChanged.connect(self.gaenge.stueck_setzen)
        zeile_s = QHBoxLayout()
        zeile_s.addWidget(self.stueck)
        zeile_s.addStretch(1)
        zeile_s.addWidget(self.k_zusatz)
        # Paket A: Material und Rüstzeit (A1), Maße des Rohrs für die Eignung (A3), Teillieferungen (A5)
        self.werkstoff = QLineEdit(self.auftrag.get("material") or "")
        self.werkstoff.setPlaceholderText("z. B. 60x60x3 S235")
        self.werkstoff.setToolTip("Läuft auf der Maschine direkt davor das gleiche Material, rechnet das Programm "
                                  "keine Rüstzeit. Gleich heißt: gleich geschrieben (Groß und Klein egal).")
        vorschlag = QCompleter(db.materialien(), self)
        vorschlag.setCaseSensitivity(Qt.CaseInsensitive)
        vorschlag.setFilterMode(Qt.MatchContains)
        self.werkstoff.setCompleter(vorschlag)
        # Plan 3.2: Abmessung einzeln (Profilform, Maß a/b, Wand, Werkstoff); daraus entsteht das Material
        self.ab_profil = QComboBox()
        self.ab_profil.setEditable(True)
        self.ab_profil.addItems(("",) + D.PROFILE)
        self.ab_profil.setCurrentText(self.auftrag.get("profil") or "")
        self.ab_profil.setToolTip("Profilform, z. B. Rechteckrohr. Mit Maßen, Wand und Werkstoff ergibt sich das "
                                  "Material von selbst; gleiche Abmessung hintereinander spart das Rüsten (Bündeln).")
        self.ab_felder = {}
        for k, platz, breite in (("mass_a", "Maß a", 70), ("mass_b", "Maß b", 70), ("wand", "Wand", 60),
                                 ("werkstoff", "Werkstoff", 90)):
            w = self.auftrag.get(k)
            e = QLineEdit((w or "") if k == "werkstoff" else (D.mm_text(w) if w else ""))
            e.setPlaceholderText(platz)
            e.setMaximumWidth(breite)
            e.setToolTip(f"{platz}{' in mm' if k != 'werkstoff' else ', z. B. S235 oder 1.4301'}.")
            self.ab_felder[k] = e
        self._ab_text = D.material_text(*(self.auftrag.get(k) for k in D.ABMESSUNG))
        zeile_ab = QHBoxLayout()
        zeile_ab.addWidget(self.ab_profil, 1)
        for k in ("mass_a", "mass_b", "wand"):
            zeile_ab.addWidget(self.ab_felder[k])
            if k != "wand":
                zeile_ab.addWidget(QLabel("×"))
        zeile_ab.addWidget(QLabel("mm"))
        zeile_ab.addWidget(self.ab_felder["werkstoff"])
        self.zeile_ab = zeile_ab
        self.ab_profil.currentTextChanged.connect(lambda _t: self._abmessung_geaendert())
        for e in self.ab_felder.values():
            e.textChanged.connect(lambda _t: self._abmessung_geaendert())
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
        # N7: Wiederholauftrag – woher die Werte kommen
        self.wdh_text = QLabel(self.auftrag.get("wiederholung") or "")
        self.wdh_text.setWordWrap(True)
        self.wdh_text.setStyleSheet(f"color: {stil.umsetzen(stil.GRUEN)};")
        if self.auftrag.get("wiederholung"):
            form.addRow("", self.wdh_text)
        form.addRow("Rüstzeit", zeile_r)
        self.zeile_r = zeile_r
        form.addRow("Stückzahl", zeile_s)
        form.setRowVisible(zeile_s, self.mit_zusatz)
        form.addRow("", self.mehr)
        form.addRow("", self.gaenge)
        form.addRow("Abmessung", zeile_ab)
        form.addRow("Material (für Rüsten)", self.werkstoff)
        form.addRow("Rohr", zeile_d)
        form.addRow("", self.passt_text)
        form.addRow("", zeile)
        if not self.auftrag.get("id"):
            form.addRow("Frühestens fertig", zeile_f)
            self.kalk.eingabe.textChanged.connect(lambda _t: self.frueh_uhr.start() if self.isVisible() else None)
            self.maschine.currentTextChanged.connect(lambda _t: self.frueh_zeigen(neu_rechnen=False))
        form.addRow("", self.mit_teilen)
        form.addRow("", self.teile)
        form.addRow("", zeile_m)
        # V8: erst nach anderen Aufträgen (z. B. Teile, die erst auf einer anderen Maschine entstehen)
        self.nach = QLineEdit(db.nach_text(self.auftrag))
        self.nach.setPlaceholderText("Auftragsnummern, z. B. A-2701 (leer = sofort)")
        self.nach.setToolTip("Dieser Auftrag beginnt erst, wenn diese Aufträge fertig sind. Mehrere mit Komma.")
        vorschlag = QCompleter(sorted(str(x["nummer"]) for x in db.auftraege((D.OFFEN, D.LAEUFT))
                                      if x["id"] != self.auftrag.get("id")), self.nach)
        vorschlag.setCaseSensitivity(Qt.CaseInsensitive)
        self.nach.setCompleter(vorschlag)
        form.addRow("Erst nach", self.nach)
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
        # M1/M2/E5 (Plan 2.3): ausgeschaltete Funktionen verschwinden, eingetragene Werte bleiben
        self.f_mat, self.f_teil = db.funktion("material"), db.funktion("teillieferungen")
        form.setRowVisible(self.werkstoff, self.f_mat)
        form.setRowVisible(zeile_ab, self.f_mat)
        form.setRowVisible(zeile_d, self.f_mat)
        form.setRowVisible(zeile_m, db.funktion("material_ab"))
        self._mehr_geschaltet(self.mehr.isChecked())
        self._teile_geschaltet(self.mit_teilen.isChecked())
        self._eignung_zeigen()
        self.frueh_zeigen(neu_rechnen=False)

    def frueh_zeigen(self, neu_rechnen=True):
        """N4: frühester Termin je Maschine hinter allen offenen Aufträgen (wie die Terminauskunft, speichert nichts).
        Die gewählte Maschine steht vorn und fett, die früheste andere dahinter."""
        if self.auftrag.get("id"):
            return
        try:
            minuten = self.kalk.minuten()
        except laufzeit.Fehler:
            minuten = None
        if neu_rechnen:
            self.frueh_liste = rechnung.auskunft(self.db, minuten) if minuten else []
        gewaehlt = next((x for x in self.frueh_liste if x["maschine"] == self.maschine.currentText()), None)
        if not self.frueh_liste or gewaehlt is None:
            self.frueh.setText("<span style='color:%s'>erscheint, sobald die Laufzeit eingetragen ist</span>"
                               % stil.umsetzen(stil.TEXT_GRAU))
            self.k_frueh.hide()
            return
        def text(x):
            if x["fertig"] is None:
                return f"{x['maschine']}: später als 400 Tage"
            return (f"{x['maschine']}: fertig {_wtag(x['fertig'])}"
                    + (f", lieferbar {_wtag(x['lieferbar'])}" if x["lieferbar"] != x["fertig"] else ""))
        teile = [f"<b>{text(gewaehlt)}</b>"]
        besser = self.frueh_liste[0]
        if besser is not gewaehlt and besser["fertig"] and (gewaehlt["fertig"] is None
                                                             or besser["fertig"] < gewaehlt["fertig"]):
            teile.append("früher: " + text(besser))
        self.frueh.setText(" · ".join(teile))
        self.k_frueh.setVisible(gewaehlt["lieferbar"] is not None and not self.mit_teilen.isChecked())

    def zusatz_neu(self, oeffnen=True):
        """Plan 2.6: „+ Zusatzschritt …“. Ein einteiliger Auftrag wird dafür mehrteilig (Maschine als erste Zeile)."""
        if not self.mehr.isChecked():
            self.mehr.setChecked(True)
        return self.gaenge.zusatz_bearbeiten(neu=True, oeffnen=oeffnen)

    def frueh_uebernehmen(self):
        x = next((x for x in self.frueh_liste if x["maschine"] == self.maschine.currentText()), None)
        if x and x["lieferbar"]:
            t = x["lieferbar"]
            self.mit_termin.setChecked(True)
            self.termin.setDate(QDate(t.year, t.month, t.day))

    def _teile_geschaltet(self, an):
        """Mit Teillieferungen ergibt sich der Liefertermin aus der letzten Lieferung."""
        an = an and getattr(self, "f_teil", True)  # Funktion aus: Lieferungen bleiben gespeichert, nur unsichtbar
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
        self.form.setRowVisible(self.passt_text, bool(grund) and getattr(self, "f_mat", True))

    def _mehr_geschaltet(self, an):
        """Einteilig: Maschine und Laufzeit als Felder. Mehrteilig: stattdessen die Tabelle der Zeilen."""
        for feld in (self.maschine, self.kalk):
            self.form.setRowVisible(feld, not an)
        self.form.setRowVisible(self.zeile_r, not an and getattr(self, "f_mat", True))
        self.form.setRowVisible(self.mit_teilen, not an and getattr(self, "f_teil", True))
        self.form.setRowVisible(self.gaenge, an)
        self.form.setRowVisible(self.teile, not an and self.mit_teilen.isChecked() and getattr(self, "f_teil", True))
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
                    **self.abmessung(), stand=self.stand, nach=self.nach.text(),
                    lieferungen=self.teile.werte() if self.mit_teilen.isChecked() and not mehr else [],
                    **(dict(stueckzahl=self.stueck.value()) if self.mit_zusatz else {}))

    def abmessung(self):
        """Plan 3.2: Profilform, Maß a/b, Wand, Werkstoff aus den Feldern (Maße als Text, Daten prüft sie)."""
        return dict(profil=self.ab_profil.currentText(), **{k: e.text() for k, e in self.ab_felder.items()})

    def _abmessung_geaendert(self):
        """Material folgt der Abmessung, solange niemand es von Hand anders geschrieben hat."""
        try:
            neu = D.material_text(*(D._zahl(v, k) if k in ("mass_a", "mass_b", "wand") else v
                                    for k, v in self.abmessung().items()))
        except D.Fehler:
            return
        if not self.werkstoff.text().strip() or " ".join(self.werkstoff.text().split()) == self._ab_text:
            self.werkstoff.setText(neu)
        self._ab_text = neu
        gross = max((D._zahl(self.ab_felder[k].text() or 0, k) for k in ("mass_a", "mass_b")), default=0)
        if gross and not self.durchmesser.text().strip() or (gross and self.durchmesser.property("auto")):
            self.durchmesser.setText(D.mm_text(gross))
            self.durchmesser.setProperty("auto", True)

    def speichern(self, ueberschreiben=None):
        """Speichern. Plan 3.4: Hat ein anderer Platz den Auftrag inzwischen geändert, fragt das Programm, statt still
        zu überschreiben (ueberschreiben True/False beantwortet die Frage ohne Fenster, Tests)."""
        try:
            werte = self.werte()
            try:
                self.auftrag["id"] = self.db.auftrag_speichern(werte)
            except D.Konflikt as k:
                if ueberschreiben is None:
                    box = QMessageBox(QMessageBox.Warning, "Inzwischen geändert",
                                      f"{k}\n\nJetzt gespeichert: {self._stand_text(k.jetzt)}\n"
                                      f"Deine Eingabe: {self._stand_text(werte)}\n\nMit deiner Eingabe "
                                      "überschreiben oder abbrechen und den neuen Stand ansehen?", parent=self)
                    ja = box.addButton("Meine Eingabe speichern", QMessageBox.AcceptRole)
                    box.addButton("Abbrechen", QMessageBox.RejectRole)
                    box.exec()
                    ueberschreiben = box.clickedButton() is ja
                if not ueberschreiben:
                    self.fehler.setText(f"{k} Nicht gespeichert; bitte das Fenster schließen und neu öffnen.")
                    return False
                self.auftrag["id"] = self.db.auftrag_speichern(dict(werte, ueberschreiben=True))
        except (D.Fehler, laufzeit.Fehler) as e:
            self.fehler.setText(str(e))
            return False
        self.accept()
        return True

    @staticmethod
    def _stand_text(a):
        if not a:
            return "–"
        termin = a.get("liefertermin")
        termin = termin.strftime("%d.%m.%Y") if isinstance(termin, datetime.date) else D._zeigen("Liefertermin", termin)
        return (f"{a.get('maschine') or ''}, {laufzeit.text(int(a.get('kalk_min') or 0), 'hm')}, "
                f"Liefertermin {termin or 'keiner'}")


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
        # Plan 3.3: davon Rüsten (freiwillig) für die Auswertung Rüsten je Maschine
        self.ruest = QLineEdit()
        self.ruest.setMaximumWidth(90)
        self.ruest.setPlaceholderText("freiwillig")
        self.ruest.setToolTip("Wie viele Minuten der tatsächlichen Laufzeit waren Rüsten? Leer lassen, wenn "
                              "unbekannt. Die Kennzahlen zeigen daraus die Rüstzeit je Maschine.")
        zeile_r = QHBoxLayout()
        zeile_r.addWidget(self.ruest)
        zeile_r.addWidget(QLabel("min"))
        zeile_r.addStretch(1)
        self.zeile_ruest = zeile_r
        form.addRow("davon Rüsten", zeile_r)
        form.setRowVisible(zeile_r, db.funktion("material"))
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
        self.ruest.clear()
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
                                  fertig_um=f"{u.hour():02d}:{u.minute():02d}",
                                  ruest_ist=None if self.fremd else self.ruest.text().strip() or None)
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
        breite = (self.width() - links - 6) / max(len(self.monate), 12)   # L6: feste Breite wie bei 12 Monaten
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


class Chip(QLabel):
    """Plan 3.0: kleines Feld mit Text und Hintergrundfarbe für die Kennzahlen-Zeile; ein Klick löst clicked aus."""
    clicked = Signal()

    def __init__(self, text=""):
        super().__init__(text)
        self.setTextFormat(Qt.PlainText)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def click(self):
        self.clicked.emit()


class KnappKnopf(QPushButton):
    """Knopf so breit wie sein Text (ohne die Mindestbreite des Stils), damit eine Knopfzeile auch bei 1366 Pixeln
    passt (E2: Zeile der Plantafel mit „Monat“)."""

    def sizeHint(self):
        s = super().sizeHint()
        return QSize(min(s.width(), self.fontMetrics().horizontalAdvance(self.text()) + 26), s.height())

    def minimumSizeHint(self):
        return self.sizeHint()


class MonatsTafel(QWidget):
    """Monatsplan wie in der Excel-Plantafel (E2, Plan 2.3): Zeilen = Tage des Monats, Spalten = Maschinen, in jeder
    Zelle die Aufträge des Tages mit ihrer Zeit an diesem Tag, unten die Tagesauslastung (grün, gelb, rot).
    Vergangene Tage zeigen, was tatsächlich lief. Klick wählt einen Auftrag, Doppelklick öffnet ihn."""
    gewaehlt = Signal(object)
    oeffnen = Signal(object)
    LINKS, KOPF = 96, 26

    def __init__(self, parent=None):
        super().__init__(parent)
        self.daten, self.heute_tag, self.ist, self.auswahl = None, None, {}, None
        self.lz = lambda minuten: laufzeit.text(minuten, "hm")
        self.termine = {}                         # {Auftrag-ID: Liefertermin-Text} für den Tooltip
        self.flaechen = []                        # [(QRectF, Auftrag-ID, Tooltip)]
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, daten, heute, ist=None, auswahl=None, termine=None):
        self.daten, self.heute_tag, self.ist, self.auswahl = daten, heute, ist or {}, auswahl
        self.termine = termine or {}
        self.updateGeometry()
        self.setMinimumHeight(self.hoehe())
        self.update()

    def _zeilenhoehe(self):
        return QFontMetrics(self._klein()).height() + 2

    def _klein(self):
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() * 0.9))
        return f

    def _zeilen(self, d):
        """So viele Textzeilen braucht der Tag d (mindestens eine)."""
        if not self.daten:
            return 1
        mindest = 2 if d.weekday() == 0 or d == self.daten["tage"][0] else 1      # Platz für „KW 46“
        if d < self.heute_tag:
            return max([mindest] + [len(t) for t in (self.ist.get(d) or {}).values()])
        return max([mindest] + [len(self.daten["zellen"].get((m, d), ())) for m in self.daten["maschinen"]])

    def _tageshoehe(self, d):
        return 6 + self._zeilen(d) * self._zeilenhoehe() + (14 if d >= self.heute_tag else 0)

    def hoehe(self):
        if not self.daten:
            return 80
        return self.KOPF + sum(self._tageshoehe(d) for d in self.daten["tage"]) + 30

    def sizeHint(self):
        return QSize(800, self.hoehe())

    def zeichnen(self, p, breite):
        """Zeichnet den Monat in der Breite breite (Bildschirm und PDF). Ergebnis: Höhe."""
        self.flaechen = []
        if not self.daten:
            return 0
        text, grau = stil.farbe(stil.TEXT), stil.farbe(stil.TEXT_GRAU)
        linie, fein = stil.farbe(stil.RAHMEN), stil.farbe(stil.LINIE)
        zu, hell = stil.farbe("#EEF1F5"), stil.farbe("#FFFFFF")
        normal, klein, fett = QFont(self.font()), self._klein(), QFont(self.font())
        fett.setBold(True)
        kfett = QFont(klein)
        kfett.setBold(True)
        fmk = QFontMetrics(klein)
        zh = self._zeilenhoehe()
        maschinen = self.daten["maschinen"]
        sb = max(60.0, (breite - self.LINKS) / max(1, len(maschinen)))
        p.setFont(fett)
        p.setPen(text)
        for j, m in enumerate(maschinen):
            p.drawText(QRectF(self.LINKS + j * sb + 4, 0, sb - 8, self.KOPF), Qt.AlignLeft | Qt.AlignVCenter, m)
        y = self.KOPF
        for d in self.daten["tage"]:
            h = self._tageshoehe(d)
            vergangen = d < self.heute_tag
            p.setPen(Qt.NoPen)
            for j, m in enumerate(maschinen):
                kap = self.daten["kap"].get((m, d)) or 0.0
                p.setBrush(zu if vergangen or kap <= 1e-9 else hell)
                p.drawRect(QRectF(self.LINKS + j * sb, y, sb, h))
            if d == self.heute_tag:
                p.setBrush(stil.farbe(stil.BLAU_FLAECHE))
                p.drawRect(QRectF(0, y, self.LINKS, h))
            p.setPen(QPen(linie if d.weekday() == 0 else fein, 1))
            p.drawLine(QPointF(0, y), QPointF(self.LINKS + sb * len(maschinen), y))
            p.setFont(fett if d == self.heute_tag else normal)
            p.setPen(grau if vergangen or d.weekday() >= 5 else text)
            p.drawText(QRectF(4, y + 2, self.LINKS - 6, zh + 2), Qt.AlignLeft | Qt.AlignVCenter,
                       f"{WOCHENTAG[d.weekday()]} {d.strftime('%d.%m.')}")
            if d.weekday() == 0 or d == self.daten["tage"][0]:
                p.setFont(klein)
                p.setPen(grau)
                p.drawText(QRectF(4, y + 2 + zh, self.LINKS - 6, zh), Qt.AlignLeft | Qt.AlignVCenter,
                           f"KW {d.isocalendar()[1]}")
            for j, m in enumerate(maschinen):
                x = self.LINKS + j * sb
                kap = self.daten["kap"].get((m, d)) or 0.0
                p.setFont(klein)
                if vergangen:
                    p.setPen(grau)
                    for i, t in enumerate((self.ist.get(d) or {}).get(m, ())):
                        p.drawText(QRectF(x + 4, y + 3 + i * zh, sb - 8, zh), Qt.AlignLeft | Qt.AlignVCenter,
                                   fmk.elidedText(t, Qt.ElideRight, int(sb - 8)))
                    continue
                if kap <= 1e-9:
                    p.setPen(grau)
                    p.drawText(QRectF(x + 4, y + 3, sb - 8, zh), Qt.AlignLeft | Qt.AlignVCenter, "frei")
                    continue
                for i, z in enumerate(self.daten["zellen"].get((m, d), ())):
                    r = QRectF(x + 3, y + 3 + i * zh, sb - 6, zh)
                    if z["id"] == self.auswahl:
                        p.setPen(Qt.NoPen)
                        p.setBrush(stil.farbe(stil.BLAU_FLAECHE))
                        p.drawRect(r)
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(T_RISIKO.get(z["risiko"], T_BLAU)))
                    p.drawEllipse(QRectF(r.x() + 1, r.y() + zh / 2 - 3, 6, 6))
                    zeit = self.lz(z["minuten"])
                    zb = fmk.horizontalAdvance(zeit) + 4
                    p.setPen(text)
                    p.setFont(kfett)
                    nb = QFontMetrics(kfett).horizontalAdvance(z["nummer"]) + 6
                    platz = r.width() - 10 - zb
                    p.drawText(QRectF(r.x() + 10, r.y(), platz, zh), Qt.AlignLeft | Qt.AlignVCenter,
                               QFontMetrics(kfett).elidedText(z["nummer"], Qt.ElideRight, int(platz)))
                    p.setFont(klein)
                    if platz - nb > 20 and z["kunde"]:
                        p.setPen(grau)
                        p.drawText(QRectF(r.x() + 10 + nb, r.y(), platz - nb, zh), Qt.AlignLeft | Qt.AlignVCenter,
                                   fmk.elidedText(z["kunde"], Qt.ElideRight, int(platz - nb)))
                    p.setPen(text)
                    p.drawText(QRectF(r.right() - zb, r.y(), zb, zh), Qt.AlignRight | Qt.AlignVCenter, zeit)
                    tipp = (f"{z['nummer']}" + (f", {z['kunde']}" if z["kunde"] else "") +
                            f"\nan diesem Tag: {zeit}" +
                            (f"\nLiefertermin {self.termine[z['id']]}" if self.termine.get(z["id"]) else ""))
                    self.flaechen.append((r, z["id"], tipp))
                voll = (self.daten["last"].get((m, d)) or 0.0) / kap
                by = y + h - 12
                p.setPen(Qt.NoPen)
                p.setBrush(fein)
                p.drawRect(QRectF(x + 4, by + 2, sb - 48, 6))
                farbe = T_ROT if voll >= 0.995 else T_GELB if voll >= 0.8 else T_GRUEN
                if voll > 0.004:
                    p.setBrush(QColor(farbe))
                    p.drawRect(QRectF(x + 4, by + 2, (sb - 48) * min(1.0, voll), 6))
                p.setPen(QColor(farbe) if voll > 0.004 else grau)
                p.drawText(QRectF(x + sb - 42, by - 2, 38, 13), Qt.AlignRight | Qt.AlignVCenter,
                           f"{voll * 100:.0f} %")
            y += h
        p.setPen(QPen(linie, 1))
        p.drawLine(QPointF(0, y), QPointF(self.LINKS + sb * len(maschinen), y))
        for j in range(len(maschinen) + 1):
            x = self.LINKS + j * sb
            p.drawLine(QPointF(x, 0 if j else self.KOPF), QPointF(x, y))
        p.setFont(fett)
        p.setPen(text)
        p.drawText(QRectF(4, y + 2, self.LINKS, 24), Qt.AlignLeft | Qt.AlignVCenter, "Monat")
        for j, m in enumerate(maschinen):
            plan, verf = self.daten["summe"][m]
            anteil = f" ({plan / verf * 100:.0f} %)" if verf > 1e-9 else ""
            p.setFont(klein)
            p.drawText(QRectF(self.LINKS + j * sb + 4, y + 2, sb - 8, 24), Qt.AlignLeft | Qt.AlignVCenter,
                       f"{self.lz(int(plan * 60 + 0.5))} von {self.lz(int(verf * 60 + 0.5))}{anteil}")
        return y + 28

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.daten:
            p.setPen(stil.farbe(stil.TEXT_GRAU))
            p.drawText(self.rect(), Qt.AlignCenter, "Keine Maschinen angelegt.")
        else:
            self.zeichnen(p, self.width())
        p.end()

    def _treffer(self, pos):
        for r, i, tipp in self.flaechen:
            if r.contains(QPointF(pos)):
                return i, tipp
        return None, ""

    def mousePressEvent(self, e):
        i, _ = self._treffer(e.position())
        if i is not None:
            self.auswahl = i
            self.update()
            self.gewaehlt.emit(i)

    def mouseDoubleClickEvent(self, e):
        i, _ = self._treffer(e.position())
        if i is not None:
            self.oeffnen.emit(i)

    def mouseMoveEvent(self, e):
        i, tipp = self._treffer(e.position())
        self.setToolTip(tipp if i is not None else "")
        self.setCursor(Qt.PointingHandCursor if i is not None else Qt.ArrowCursor)


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
        self.wirkung = None                       # Plan 3.1: f(Auftrag-ID, Gang-ID, Maschine, Tag) -> Text beim Ziehen
        self.wirkung_text = ""
        self.farbe_nach = TAFEL_FARBE[0]
        self.balken_felder = list(BALKEN_VORGABE)  # N4: Inhalt der zweiten Zeile im Balken
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

    def felder_setzen(self, felder):
        """N4: Felder der zweiten Balkenzeile (Schlüssel aus BALKEN_FELDER, in dieser Reihenfolge)."""
        self.balken_felder = [k for k in BALKEN_FELDER if k in set(felder or ())]
        self.update()

    def balken_text(self, a, z):
        """N4: zweite Zeile im Balken aus den gewählten Feldern."""
        werte = {"kunde": a.get("kunde") or "", "rest": laufzeit.text(int(a["h"] * 60 + 0.5), "hm"),
                 "termin": f"Termin {a['termin_datum']:%d.%m.}" if a.get("termin_datum") else "",
                 "stueck": z.get("stueck") or "", "material": a.get("material") or "",
                 "bemerkung": z.get("bemerkung") or ""}
        return " · ".join(werte[k] for k in self.balken_felder if werte.get(k))

    def versatz_setzen(self, x):
        self.versatz = int(x)
        self.update()

    def _status(self, a):
        z = self.zustand.get((a["id"], a.get("gang")), {})
        return ("läuft" if z.get("laeuft") else "gestoppt" if z.get("gestoppt") else
                "wartet auf Material" if z.get("material") else "offen")

    def _tag_hinweis(self, m, tag):
        """Plan 2.9: (Farbe, kurz, lang) für Wartung oder fehlende Bediener an diesem Tag, sonst None."""
        w = (self.ein.get("wartung") or {}).get((m, tag))
        if w:
            h = sum(x["h"] for x in w)
            namen = ", ".join(x["name"] for x in w)
            return (QColor(T_ROT) if any(x["ueber"] for x in w) else QColor("#6B7280"), "Wartung",
                    f"{namen} {laufzeit.text(int(h * 60 + 0.5))}")
        b = (self.ein.get("besetzt") or {}).get((m, tag))
        if b:
            fehlt = f" ({', '.join(b['fehlt'])})" if b["fehlt"] else ""
            return (QColor("#D97706"), "Bediener", f"Bediener {b['ist']} von {b['soll']}{fehlt}")
        return None

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
        alt = self.ziel
        self.ziel = self.ziel_bei(e.position())
        if self.ziel:
            if self.ziel != alt and self.wirkung is not None:    # nur, wenn Tag oder Maschine wechselt
                try:
                    self.wirkung_text = self.wirkung(self.zug[0]["id"], self.zug[0].get("gang"), *self.ziel) or ""
                except Exception:                 # die Vorschau darf das Ziehen nie aufhalten
                    self.wirkung_text = ""
            QToolTip.showText(e.globalPosition().toPoint(), f"{self.zug[0].get('nummer') or ''}: fest ab "
                              f"{_wtag(self.ziel[1])} auf {self.ziel[0]}"
                              + (f"\n{self.wirkung_text}" if self.wirkung_text else ""), self)
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
                hinweis = self._tag_hinweis(m, tag) if tag >= heute else None
                if hinweis is not None:                                       # Plan 2.9: Wartung, Bediener fehlt
                    farbe_h, kurz, lang = hinweis
                    leiste = QRectF(x + 1, y + self.ZEILE - 15, tb - 1, 13)
                    p.setBrush(QBrush(farbe_h, Qt.BDiagPattern))
                    p.drawRect(QRectF(x + 1, y + 12, tb - 1, self.ZEILE - 13))
                    p.setBrush(farbe_h)
                    p.drawRect(leiste)
                    if tb >= 34:
                        p.setFont(klein)
                        p.setPen(QColor("#FFFFFF"))
                        p.drawText(leiste.adjusted(3, 0, -2, 0), Qt.AlignLeft | Qt.AlignVCenter,
                                   QFontMetrics(klein).elidedText(lang if tb >= 120 else kurz, Qt.ElideRight,
                                                                  int(tb - 6)))
                        p.setPen(Qt.NoPen)
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
                              self.balken_text(a, z))
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
            QTimer.singleShot(0, self, self.anpassen)      # mit self: entfällt, wenn gelöscht
        return False


# E5 (Plan 2.3): zuschaltbare Funktionen (Name für Daten.funktion, Häkchen, Erklärung)
FUNKTIONEN = (
    ("material", "Material und Rüsten",
     "Material, Rüstzeit und Rohrmaße im Auftrag und bei der Maschine; gleiches Material hintereinander spart das "
     "Rüsten, Optimieren mit Ziel „Wenig Rüsten“. Aus: geplant wird nur mit der eingetragenen Zeit."),
    ("material_ab", "Material da ab",
     "Datum im Auftrag, vor dem er nicht eingeplant wird (Status „wartet auf Material“, schraffiert in der "
     "Plantafel)."),
    ("teillieferungen", "Teillieferungen", "Mehrere Liefertermine mit Mengen in einem Auftrag."),
    ("arbeitsgaenge", "Mehrere Arbeitsgänge",
     "Ein Auftrag in Arbeitsgängen nacheinander, z. B. Laser, Entgraten, Verzinken (Einstellungen → Termine und "
     "Abläufe → Arbeitsgänge)."),
    ("werkstatt", "Werkstatt-Ansicht", "Knopf oben rechts für die große Ansicht an der Maschine."),
    ("zusatzschritte", "Zusatzschritte (Gewinde, Senken, Bohren, Nieten, Schweißen, Verzinken, Pulvern)",
     "Im Auftrag Stückzahl und „+ Zusatzschritt …“: Anzahl je Teil eingeben, das Programm rechnet die Laufzeit aus "
     "Richtzeiten (Einstellungen → Termine und Abläufe). Schaltet die Arbeitsgänge mit ein und legt die "
     "Arbeitsplätze Bearbeitung und Schweißen an."),
    ("warnungen", "Warnungen (Glocke)",
     "Glocke oben rechts und Zeile im Reiter Aufträge: Liefertermin überschritten oder nicht zu halten, Material "
     "fehlt kurz vor dem Start, Maschine steht, Fremdarbeit nicht zurück (Grenzen: Einstellungen → Termine und "
     "Abläufe → Warnungen)."),
    ("wartung", "Wartung im Kalender",
     "Wartungen je Maschine (einmalig, alle X Wochen, alle X Laufstunden) nehmen an ihrem Tag Stunden weg und stehen "
     "grau in der Plantafel (Einstellungen → Wartung und Bediener)."),
    ("bediener", "Bediener und Einrichter",
     "Wer bedient welche Maschine, wer ist im Urlaub oder krank: fehlt der Bediener, plant das Programm weniger ein "
     "und warnt vorher (Einstellungen → Wartung und Bediener)."),
    ("engpass", "Engpässe mit Empfehlung",
     "Die Glocke meldet, wenn eine Maschine in einer der nächsten 4 Wochen über 100 % ausgelastet ist oder ab 95 %, "
     "während eine Ausweichmaschine unter 60 % liegt, und rechnet aus, welche Aufträge verlegt werden könnten."),
    ("rueckmeldung", "Rückmeldung an die Kalkulation",
     "Schreibt Rueckmeldung.csv in den Übergabe-Ordner: Ist-Zeiten, freie Stunden je Maschine und Woche, frühester "
     "Fertig-Tag für 1, 4, 8 und 16 Stunden. Einmal am Tag und nach jeder Fertigmeldung."),
)
RICHT_KOPF = ("Zusatzschritt", "Art", "je Stück (s)", "Rüsten (min)", "Handling je Teil (s)", "Arbeitsplatz",
              "Arbeitstage", "Stichwörter", "Schätzwert")
RICHT_FELD = ("schritt", "art", "je_s", "ruest_min", "handling_s", "platz", "tage", "stichwort")
EINSTELLUNG_REITER = (("Maschinen und Schichten", lambda g: (g[1], g["s"])),
                      ("Wartung und Bediener", lambda g: (g[14], g[15])),
                      ("Termine und Abläufe", lambda g: (g[10], g[2], g[13], g[7], g[12], g[8], g[9])),
                      ("Ansicht und Felder", lambda g: (g[11], g[3], g[4])),
                      ("Benutzer und Datenbank", lambda g: (g[6], g[5])))
PRIO_TEXT = {"A": "A (wichtig)", "B": "B (normal)", "C": "C (kann warten)"}
BALKEN_ZEILE = 84                         # L1: Höhe einer Maschine in den Wochenbalken (vorher 122)
BALKEN_LEGENDE = ("Wochenbalken: Rahmen = Kapazität, gefüllt = eingelastete Aufträge (ab 80 % gelb, über 100 % rot), "
                  "grau links = tatsächliche Stunden aus den Fertigmeldungen. Klick auf eine Woche zeigt rechts ihre "
                  "Aufträge und rollt die Plantafel dorthin.")
TAFEL_HINWEIS = ("▶ läuft · ❚❚ gestoppt · schraffiert = wartet auf Material · weißer Punkt = fester Platz · Dreieck = "
                 "Liefertermin, gestrichelt = Verspätung · Streifen oben = Auslastung des Tages. Ziehen mit der Maus "
                 "legt einen Auftrag fest, Doppelklick öffnet ihn.")
RECHENWEG = ("Die offenen Aufträge laufen ab heute nacheinander, sortiert nach Liefertermin, durch die freien Stunden "
             "jeder Maschine. Was nicht in eine Woche passt, rutscht in die nächste.")


OPT_TEXT = {rechnung.OPT_MASCHINE: "auf {nach} statt {von}", rechnung.OPT_VOR: "vorziehen (läuft als Nächstes)",
            rechnung.OPT_TERMIN: "wieder nach Liefertermin einordnen",
            rechnung.OPT_FOLGE: "direkt hinter gleiches Material stellen ({material})"}
ZIEL_TEXT = dict(rechnung.ZIELE, engpass="Engpass entlasten", buendel="Bündeln")
ZIEL_HINWEIS = {
    rechnung.ZIEL_TERMIN: "Ziel: möglichst wenige Aufträge zu spät. Dafür kann ein Auftrag, der ohnehin nicht zu "
                          "halten ist, weiter nach hinten rücken (rot).",
    rechnung.ZIEL_RUESTEN: "Ziel: möglichst wenig Rüstzeit. Aufträge mit gleichem Material rücken auf ihrer Maschine "
                           "direkt hintereinander, solange dadurch kein Termin mehr reißt oder knapp wird. Die "
                           "Aufträge bis dorthin bekommen eine feste Reihenfolge; neue Aufträge stehen dahinter.",
    rechnung.ZIEL_GLEICH: "Ziel: Arbeitsvorrat der Ausweichmaschinen möglichst gleich. Aufträge wechseln die "
                          "Maschine, solange dadurch kein Termin mehr reißt oder knapp wird und das Rohr dort passt.",
    "engpass": "Ziel: die überlastete Maschine in dieser Woche entlasten. Bis zu drei Aufträge wechseln auf eine "
               "Ausweichmaschine, solange kein Termin schlechter wird und die Ausweichmaschine höchstens 100 % "
               "erreicht.",
    "buendel": "Ziel: weniger Rüsten. Aufträge mit gleichem Material (Profilform, Maße, Wand, Werkstoff) laufen direkt "
               "hintereinander, solange dadurch kein Termin knapp wird oder reißt. Die Aufträge bis dorthin bekommen "
               "eine feste Reihenfolge."}


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
        if ziel in (rechnung.ZIEL_RUESTEN, "buendel"):
            mehr = tuple(f", Rüsten {_stunden_text(h)}" for h in vorschlag["ruest"])
        elif ziel == rechnung.ZIEL_GLEICH:
            mehr = tuple(", Unterschied im Arbeitsvorrat " + f"{t:.1f}".replace(".", ",") + " Arbeitstage"
                         for t in vorschlag["ungleich"])
        if ziel == "engpass":
            mehr = tuple(f", {vorschlag['maschine']} in KW {vorschlag['montag'].isocalendar()[1]}: {p:.0f} %"
                         for p in vorschlag["prozent"])
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


class BuendelDialog(QDialog):
    """Plan 3.2 (Paket C): Liste „Bündeln“. Je Zeile ein Bündel gleichen Materials mit gesparter Rüstzeit und
    Termin-Prüfung; „Ansehen …“ zeigt Vorher/Nachher, „Übernehmen“ speichert. Nach dem Übernehmen rechnet die Liste
    neu (ein Bündel ändert die Reihenfolge der anderen)."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.setWindowTitle("Bündeln")
        self.resize(900, 460)
        self.tage = QSpinBox()
        self.tage.setRange(1, 60)
        self.tage.setValue(int(fenster.db.zahl("buendel_tage", rechnung.BUENDEL_TAGE)))
        self.tage.setSuffix(" Arbeitstage")
        self.tage.setToolTip("Nur Aufträge, die in so vielen Arbeitstagen beginnen, kommen in ein Bündel.")
        self.tage.valueChanged.connect(lambda _v: self.rechnen())
        self.kopf = QLabel("")
        self.kopf.setWordWrap(True)
        self.tabelle = QTableWidget(0, 5)
        self.tabelle.setHorizontalHeaderLabels(("Maschine", "Material", "Aufträge", "Rüsten gespart", "Termine"))
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.itemSelectionChanged.connect(self._knoepfe)
        self.tabelle.doubleClicked.connect(lambda _i: self.ansehen())
        hinweis = QLabel(ZIEL_HINWEIS["buendel"] + " Ein Bündel steht nur hier, wenn es Rüstzeit spart und kein "
                         "Auftrag ein schlechteres Terminrisiko bekommt. Gleich heißt: gleiche Profilform, gleiche "
                         "Maße und Wand, gleicher Werkstoff (Feld Material im Auftrag).")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        self.k_ansehen = QPushButton("Ansehen …")
        self.k_ansehen.clicked.connect(lambda _=False: self.ansehen())
        self.k_ueber = QPushButton("Übernehmen")
        self.k_ueber.clicked.connect(lambda _=False: self.uebernehmen())
        k_zu = QPushButton("Schließen")
        k_zu.clicked.connect(self.reject)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Aufträge der nächsten"))
        oben.addWidget(self.tage)
        oben.addStretch(1)
        unten = QHBoxLayout()
        unten.addWidget(self.k_ansehen)
        unten.addWidget(self.k_ueber)
        unten.addStretch(1)
        unten.addWidget(k_zu)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.kopf)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(hinweis)
        lay.addLayout(unten)
        self.liste = []
        self.rechnen()

    def rechnen(self):
        f = self.f
        if f.db.darf("einstellungen"):
            f.db.einstellung_setzen("buendel_tage", str(self.tage.value()))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.liste = rechnung.buendel(f.aus, f.ein, f.heute(), int(f.db.zahl("schwelle_tage", 2)),
                                          self.tage.value())
        finally:
            QApplication.restoreOverrideCursor()
        self.tabelle.setRowCount(len(self.liste))
        for r, v in enumerate(self.liste):
            werte = (v["maschine"], v["material"], ", ".join(v["nummern"]), f"{v['gespart_min']} min",
                     "kein Termin schlechter" + (f", {sum(1 for x in v['aenderungen'] if x['schlechter'] < 0)} besser"
                                                 if any(x["schlechter"] < 0 for x in v["aenderungen"]) else ""))
            for c, t in enumerate(werte):
                z = _zelle(t, rechts=c == 3)
                if c == 4:
                    z.setForeground(QColor(stil.umsetzen(stil.GRUEN)))
                self.tabelle.setItem(r, c, z)
        self.tabelle.resizeColumnsToContents()
        summe = sum(v["gespart_min"] for v in self.liste)
        self.kopf.setText(f"<b>{len(self.liste)} Bündel</b>, zusammen etwa {summe} min Rüsten weniger (jedes für sich "
                          "gerechnet)." if self.liste else
                          "Kein Bündel gefunden: Es gibt keine Aufträge mit gleichem Material, die heute getrennt "
                          "laufen und ohne Nachteil für einen Termin zusammenrücken können. Bündeln braucht das Feld "
                          "Material (oder Profil und Maße) im Auftrag und eine Rüstzeit der Maschine.")
        if self.liste:
            self.tabelle.selectRow(0)
        self._knoepfe()

    def _knoepfe(self):
        da = bool(self.liste) and self.tabelle.currentRow() >= 0
        self.k_ansehen.setEnabled(da)
        self.k_ueber.setEnabled(da and self.f.db.darf("auftraege"))

    def gewaehlt(self):
        r = self.tabelle.currentRow()
        return self.liste[r] if 0 <= r < len(self.liste) else None

    def ansehen(self):
        v = self.gewaehlt()
        if v is not None and OptimierenDialog(self, v).exec() == QDialog.Accepted:
            return self.uebernehmen()
        return False

    def uebernehmen(self):
        v = self.gewaehlt()
        if v is None or not self.f._vorschlag_speichern(v):
            return False
        self.rechnen()
        return True


# Plan 3.4: lesbare Namen im Protokoll (unbekannte Namen bleiben, wie sie sind)
PROTOKOLL_NAMEN = {
    "name": "Name", "stunden_tag": "Stunden je Tag", "aktiv": "aktiv", "sperrtage": "gesperrte Tage",
    "uebergang_tage": "Übergang (Tage)", "ausweich": "Ausweichmaschine", "schichten": "Schichten",
    "schicht_start": "Schichtbeginn", "schichten_sa": "Schichten Samstag", "ruest_min": "Rüstzeit (min)",
    "max_durchmesser": "größter Durchmesser", "max_laenge": "größte Länge", "erfahrung": "Erfahrungswert",
    "bezeichnung": "Bezeichnung", "typ": "Typ", "leistung": "Leistung (%)", "arbeitstage": "Arbeitstage",
    "rolle": "Rolle", "schwelle_tage": "Warnung Termin (Tage)", "buendel_tage": "Bündeln (Tage)",
    "fremd_tage": "Fremdarbeit (Tage)", "samstag_stunden": "Stunden Samstag", "wochen": "Wochen in der Ansicht",
    "arbeitsgaenge": "Arbeitsgänge", "rolle_vorgabe": "Rolle aller anderen", "land": "Bundesland",
    "ohne_einheit": "Zahl ohne Einheit", "design": "Design", "ruhe": "Ruhezeit",
}


def _protokoll_lesbar(text):
    return re.sub(r"\b([a-z_]+)(?=: |$)", lambda m: PROTOKOLL_NAMEN.get(m.group(1), m.group(1)), str(text or ""))


class ProtokollDialog(QDialog):
    """Plan 3.4: Protokoll der Änderungen an Maschinen, Wartungen, Bedienern, Ausnahmen, Richtzeiten, Benutzern,
    Zusatzfeldern und Einstellungen. Zum Nachlesen, nichts lässt sich ändern."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.db = fenster.db
        self.setWindowTitle("Protokoll")
        self.resize(1000, 560)
        self.bereich = QComboBox()
        self.bereich.addItem("alle Bereiche", None)
        for b in sorted({v[0] for v in D.PROTOKOLL.values()} | {"Einstellung"}):
            self.bereich.addItem(b, b)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Maschine, Benutzer, Wert …")
        self.suche.setClearButtonEnabled(True)
        self.tabelle = QTableWidget(0, 6)
        self.tabelle.setHorizontalHeaderLabels(("Wann", "Wer", "Bereich", "Was", "Vorher", "Nachher"))
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setWordWrap(True)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.bereich.currentIndexChanged.connect(lambda _i: self.laden())
        self.suche.textChanged.connect(lambda _t: self.laden())
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Bereich"))
        oben.addWidget(self.bereich)
        oben.addWidget(self.suche, 1)
        kn = QDialogButtonBox(QDialogButtonBox.Close)
        kn.button(QDialogButtonBox.Close).setText("Schließen")
        kn.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(kn)
        self.laden()

    def laden(self):
        liste = self.db.protokoll(self.bereich.currentData(), self.suche.text().strip())
        self.tabelle.setRowCount(len(liste))
        for r, z in enumerate(liste):
            wann = z["wann"].replace("T", " ")[:16]
            try:
                wann = datetime.datetime.fromisoformat(z["wann"]).strftime("%d.%m.%Y %H:%M")
            except ValueError:
                pass
            werte = (wann, z["wer"], z["bereich"], _protokoll_lesbar(z["was"]), _protokoll_lesbar(z["alt"]),
                     _protokoll_lesbar(z["neu"]))
            for c, t in enumerate(werte):
                self.tabelle.setItem(r, c, _zelle(t))
        self.tabelle.resizeColumnsToContents()
        for c in (4, 5):
            self.tabelle.setColumnWidth(c, min(self.tabelle.columnWidth(c), 320))
        return liste


class MaterialbedarfDialog(QDialog):
    """V7: Stangen je Profil und Woche (Woche = Beginn des Auftrags laut Planung). Nur Anzeige und Excel."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f = fenster
        self.setWindowTitle("Materialbedarf je Woche")
        self.wochen = QSpinBox()
        self.wochen.setRange(1, 26)
        self.wochen.setSuffix(" Wochen")
        self.wochen.setValue(int(fenster.db.zahl("material_wochen", 6)))
        self.wochen.valueChanged.connect(lambda _w: self.laden())
        k_excel = QPushButton("Excel …")
        k_excel.clicked.connect(lambda _=False: self.excel())
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Zeitraum"))
        oben.addWidget(self.wochen)
        oben.addStretch(1)
        oben.addWidget(k_excel)
        self.tabelle = QTableWidget()
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        kn = QDialogButtonBox(QDialogButtonBox.Close)
        kn.button(QDialogButtonBox.Close).setText("Schließen")
        kn.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(self.info)
        lay.addWidget(kn)
        self.resize(1100, 520)
        self.laden()

    def kopf(self):
        return (["Material", "Stangenlänge"] + [f"KW {mo.isocalendar()[1]}" for mo in self.daten["wochen"]]
                + ["später", "Summe", "Nutzlänge [m]", "Material da ab", "Aufträge"])

    def zeilen(self):
        """[(Werte für die Excel-Datei, Warnung)] je Profil, zuletzt die Aufträge ohne Stangenangabe."""
        d = self.daten
        aus = []
        for z in d["zeilen"]:
            werte = [z["material"], z["laenge"] or None] + [z["je"].get(mo) for mo in d["wochen"]] + [
                z["je"].get("später"), z["summe"], round(z["nutz_m"], 1) or None,
                z["material_ab"].strftime("%d.%m.%Y") if z["material_ab"] else "", ", ".join(z["nummern"])]
            warnung = "; ".join(f"{n} beginnt {s:%d.%m.}, Material erst ab {ab:%d.%m.}" for n, s, ab in z["zu_spaet"])
            aus.append((werte, warnung))
        o = d["ohne"]
        if o["nummern"]:
            werte = ["Aufträge ohne Stangenangabe (Anzahl)", None] + [o["je"].get(mo) for mo in d["wochen"]] + [
                o["je"].get("später"), len(o["nummern"]), None, "", ", ".join(o["nummern"])]
            aus.append((werte, ""))
        return aus

    def laden(self):
        if int(self.f.db.zahl("material_wochen", 6)) != self.wochen.value():
            self.f.db.einstellung_setzen("material_wochen", self.wochen.value())
        self.daten = rechnung.materialbedarf(self.f.db, self.f.ein, self.wochen.value())
        kopf = self.kopf()
        zeilen = self.zeilen()
        self.tabelle.clear()
        self.tabelle.setColumnCount(len(kopf))
        self.tabelle.setHorizontalHeaderLabels(kopf)
        self.tabelle.setRowCount(len(zeilen))
        ohne = bool(self.daten["ohne"]["nummern"])
        for r, (werte, warnung) in enumerate(zeilen):
            letzte = ohne and r == len(zeilen) - 1
            for c, w in enumerate(werte):
                if w is None or w == "":
                    t = ""
                elif c == 1:
                    t = f"{D.mm_text(w)} mm"
                elif isinstance(w, float):
                    t = f"{w:g}".replace(".", ",")
                else:
                    t = str(w)
                zelle = _zelle(t, rechts=0 < c < len(werte) - 2)
                if letzte:
                    zelle.setForeground(stil.farbe(stil.TEXT_GRAU))
                if warnung and c == len(werte) - 2:
                    zelle.setBackground(stil.farbe(stil.ROT_FLAECHE))
                    zelle.setForeground(stil.farbe(stil.TEXT))
                    zelle.setToolTip(warnung)
                self.tabelle.setItem(r, c, zelle)
        self.tabelle.resizeColumnsToContents()
        self.tabelle.setColumnWidth(len(kopf) - 1, min(self.tabelle.columnWidth(len(kopf) - 1), 260))
        warnungen = [w for _z, w in zeilen if w]
        text = ("Woche = Beginn des Auftrags laut Planung. Die Stangen kommen aus der Kalkulation (Schnittplan). "
                "Nur zum Ansehen, bestellt wird nichts.")
        if warnungen:
            text = "<b>Material kommt zu spät:</b> " + html.escape("; ".join(warnungen)) + "<br>" + text
        if not zeilen:
            text = "Keine geplanten Aufträge im Zeitraum. " + text
        self.info.setText(text)
        return self.daten

    def excel(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Materialbedarf als Excel",
                                                  f"Materialbedarf-{self.f.heute():%Y-%m-%d}.xlsx", "Excel (*.xlsx)")
            if not pfad:
                return None
        from . import xlsx
        xlsx.schreiben(pfad, [("Materialbedarf", self.kopf() + ["Hinweis"],
                               [list(w) + [h] for w, h in self.zeilen()])])
        return pfad


class KapazitaetDialog(QDialog):
    """N8: freie Kapazität je Maschine und Woche für den Vertrieb, dazu der früheste Termin für eine Laufzeit.
    Rechnet nur, speichert nichts; Excel zum Weitergeben."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f = fenster
        self.setWindowTitle("Freie Kapazität")
        self.wochen = QSpinBox()
        self.wochen.setRange(1, 26)
        self.wochen.setSuffix(" Wochen")
        self.wochen.setValue(int(fenster.db.zahl("kapazitaet_wochen", 8)))
        self.wochen.valueChanged.connect(lambda _w: self.laden())
        k_excel = QPushButton("Excel …")
        k_excel.clicked.connect(lambda _=False: self.excel())
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Zeitraum"))
        oben.addWidget(self.wochen)
        oben.addStretch(1)
        oben.addWidget(k_excel)
        self.tabelle = QTableWidget()
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.dauer = LaufzeitFeld(fenster.db)
        self.dauer.eingabe.textChanged.connect(lambda _t: self.termin())
        self.antwort = QLabel("")
        self.antwort.setWordWrap(True)
        self.antwort.setTextFormat(Qt.RichText)
        form = QFormLayout()
        form.addRow("Frühester Termin für", self.dauer)
        hinweis = QLabel("Freie Stunden = Arbeitszeit laut Schichten, Feiertagen, Wartung und Bedienern minus geplante "
                         "Aufträge. Aufträge, die heute schon nicht mehr passen, sind abgezogen. Gespeichert wird "
                         "nichts.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        kn = QDialogButtonBox(QDialogButtonBox.Close)
        kn.button(QDialogButtonBox.Close).setText("Schließen")
        kn.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.tabelle, 1)
        lay.addLayout(form)
        lay.addWidget(self.antwort)
        lay.addWidget(hinweis)
        lay.addWidget(kn)
        self.resize(980, 460)
        self.laden()
        self.termin()

    def kopf(self):
        return ["Maschine"] + [f"KW {mo.isocalendar()[1]} ({mo:%d.%m.})" for mo in self.daten["wochen"]] + ["Summe"]

    def zeilen(self):
        """[[Maschine, Stunden je Woche …, Summe]], zuletzt die Summe aller Maschinen."""
        d = self.daten
        aus = [[z["maschine"]] + [round(z["frei"][mo], 1) for mo in d["wochen"]] + [round(z["summe"], 1)]
               for z in d["zeilen"]]
        aus.append(["Alle Maschinen"] + [round(d["gesamt"][mo], 1) for mo in d["wochen"]] + [round(d["summe"], 1)])
        return aus

    def laden(self):
        if int(self.f.db.zahl("kapazitaet_wochen", 8)) != self.wochen.value():
            self.f.db.einstellung_setzen("kapazitaet_wochen", self.wochen.value())
        self.daten = rechnung.freie_kapazitaet(self.f.db, self.f.aus, self.f.ein, self.f.heute(), self.wochen.value())
        kopf, zeilen = self.kopf(), self.zeilen()
        self.tabelle.clear()
        self.tabelle.setColumnCount(len(kopf))
        self.tabelle.setHorizontalHeaderLabels(kopf)
        self.tabelle.setRowCount(len(zeilen))
        verf = {z["maschine"]: z["verfuegbar"] for z in self.daten["zeilen"]}
        for r, werte in enumerate(zeilen):
            for c, w in enumerate(werte):
                zelle = _zelle(w if c == 0 else f"{w:g} h".replace(".", ","), rechts=c > 0)
                if r == len(zeilen) - 1:
                    f = zelle.font()
                    f.setBold(True)
                    zelle.setFont(f)
                elif 0 < c <= len(self.daten["wochen"]):
                    v = verf[werte[0]].get(self.daten["wochen"][c - 1]) or 0
                    if v > 1e-9:
                        anteil = w / v
                        zelle.setBackground(stil.farbe(stil.GRUEN_FLAECHE if anteil >= 0.25 else
                                                       stil.GELB_FLAECHE if w > 0 else stil.ROT_FLAECHE))
                        zelle.setForeground(stil.farbe(stil.TEXT))
                        zelle.setToolTip(f"{w:g} von {v:g} h frei".replace(".", ","))
                self.tabelle.setItem(r, c, zelle)
        self.tabelle.resizeColumnsToContents()
        return self.daten

    def termin(self):
        """Frühester Termin je Maschine für die eingegebene Laufzeit (wie die Terminauskunft)."""
        try:
            minuten = self.dauer.minuten()
        except laufzeit.Fehler:
            minuten = None
        if not minuten:
            self.antwort.setText("Laufzeit eingeben, z. B. 12 h: dann steht hier, wann ein neuer Auftrag frühestens "
                                 "fertig wäre.")
            return []
        liste = rechnung.auskunft(self.f.db, minuten, self.f.heute())
        teile = [f"{html.escape(x['maschine'])} {('fertig ' + _wtag(x['fertig'])) if x['fertig'] else 'später als 400 Tage'}"
                 + (f", lieferbar ab {_wtag(x['lieferbar'])}" if x["fertig"] and x["lieferbar"] != x["fertig"] else "")
                 for x in liste]
        self.antwort.setText((f"<b>Am frühesten: {teile[0]}</b>" + ("<br>" + "; ".join(teile[1:]) if teile[1:] else ""))
                             if teile else "Keine aktive Maschine.")
        return liste

    def excel(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Freie Kapazität als Excel",
                                                  f"Freie-Kapazitaet-{self.f.heute():%Y-%m-%d}.xlsx", "Excel (*.xlsx)")
            if not pfad:
                return None
        from . import xlsx
        xlsx.schreiben(pfad, [("Freie Kapazität [h]", self.kopf(), self.zeilen())])
        return pfad


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
        # V6: Varianten speichern, laden und vergleichen (ändert nichts an der Planung)
        self.v_name = QLineEdit()
        self.v_name.setPlaceholderText("Name, z. B. Samstag LT7")
        self.v_name.setMinimumWidth(200)
        k_vs = QPushButton("Als Variante speichern")
        k_vs.clicked.connect(lambda _=False: self.variante_speichern())
        self.v_liste = QComboBox()
        self.v_liste.setMinimumWidth(180)
        k_vl = QPushButton("Laden")
        k_vl.clicked.connect(lambda _=False: self.variante_laden(self.v_liste.currentText()))
        k_vd = QPushButton("Löschen")
        k_vd.clicked.connect(lambda _=False: self.variante_loeschen(self.v_liste.currentText()))
        self.k_vergleich = QPushButton("Varianten vergleichen …")
        self.k_vergleich.clicked.connect(lambda _=False: self.varianten_zeigen())
        z4 = QHBoxLayout()
        for w in (self.v_name, k_vs, QLabel("Gespeichert:"), self.v_liste, k_vl, k_vd, self.k_vergleich):
            z4.addWidget(w)
        z4.addStretch(1)
        self.v_knoepfe = (k_vl, k_vd, self.k_vergleich)
        hinweis = QLabel("Hier wird nur gerechnet. Erst „Übernehmen“ speichert die Annahmen. Ein Auftrag auf einer "
                         "anderen Maschine rechnet mit derselben Laufzeit.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.annahmen)
        lay.addLayout(z3)
        lay.addLayout(z4)
        lay.addWidget(self.ergebnis)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(hinweis)
        lay.addWidget(self.fehler)
        lay.addWidget(self.knoepfe)
        self.samstag.valueChanged.connect(lambda _w: self.rechnen())
        self.resize(960, 680)
        self.varianten_laden()
        self.rechnen()

    # ---------------------------------------------------------------- V6: Varianten
    def varianten_laden(self, waehlen=None):
        self.v_liste.clear()
        for v in self.f.db.varianten():
            self.v_liste.addItem(v["name"])
        if waehlen:
            self.v_liste.setCurrentText(waehlen)
        for k in self.v_knoepfe:
            k.setEnabled(self.v_liste.count() > 0)

    def variante_speichern(self, name=None):
        try:
            v = self.f.db.variante_speichern(self.v_name.text() if name is None else name, self.samstag.value(),
                                             self.zusatz, self.wechsel)
        except D.Fehler as e:
            self.fehler.setText(str(e))
            return None
        self.fehler.setText("")
        self.varianten_laden(v["name"])
        return v

    def variante_laden(self, name):
        v = next((x for x in self.f.db.varianten() if x["name"] == name), None)
        if v is None:
            return False
        samstag, zusatz, wechsel = D.Daten.variante_annahmen(v)
        self.zusatz = zusatz
        self.wechsel = {i: m for i, m in wechsel.items() if i in self.einteilig}
        self.v_name.setText(v["name"])
        self.samstag.blockSignals(True)
        self.samstag.setValue(samstag)
        self.samstag.blockSignals(False)
        self.rechnen()
        return True

    def variante_loeschen(self, name):
        if name:
            self.f.db.variante_loeschen(name)
            self.varianten_laden()

    VERGLEICH_KOPF = ("Variante", "Annahmen", "Nicht zu halten", "Knapp", "Früher fertig", "Später fertig",
                      "Mehrstunden", "Gespeichert")

    def varianten_vergleich(self):
        """Je gespeicherter Variante (und dem Plan ohne Annahmen) Terminrisiko und Mehrstunden: [Zeilen-Tupel]."""
        f = self.f
        schwelle = int(f.db.zahl("schwelle_tage", 2))
        risiko = f.ein["risiko"]
        zeilen = [("Plan jetzt", "keine", risiko[einlastung.UEBER], risiko[einlastung.KNAPP], 0, 0, "–", "")]
        for v in f.db.varianten():
            samstag, zusatz, wechsel = D.Daten.variante_annahmen(v)
            wechsel = {i: m for i, m in wechsel.items()
                       if i in self.einteilig and rechnung.passt(f.aus, self.einteilig[i], m)}
            neu = rechnung.rechnen(f.aus, schwelle, probe=rechnung.Probe(samstag=samstag, zusatz=zusatz,
                                                                         maschine=wechsel))
            diff = rechnung.vergleich(f.ein, neu)
            teile = []
            if samstag:
                teile.append(f"Samstag {samstag:g} h")
            teile += [f"{m} KW {mo.isocalendar()[1]} +{h:g} h" for (m, mo), h in sorted(zusatz.items())]
            teile += [f"{self.einteilig[i]['nummer']} → {m}" for i, m in wechsel.items()]
            mehr = sum(zusatz.values())
            try:
                wann = datetime.datetime.fromisoformat(v["wann"]).strftime("%d.%m.%Y %H:%M")
            except (KeyError, TypeError, ValueError):
                wann = ""
            zeilen.append((v["name"], "; ".join(teile).replace(".", ",") or "keine",
                           neu["risiko"][einlastung.UEBER], neu["risiko"][einlastung.KNAPP],
                           sum(1 for x in diff if (x["tage"] or 0) < 0), sum(1 for x in diff if (x["tage"] or 0) > 0),
                           " + ".join(([f"{mehr:g} h".replace(".", ",")] if mehr else [])
                                      + ([f"Samstage je {samstag:g} h".replace(".", ",")] if samstag else [])) or "–",
                           f"{wann} {v.get('wer') or ''}".strip()))
        return zeilen

    def varianten_zeigen(self, zeigen=True):
        d = QDialog(self)
        d.setWindowTitle("Varianten vergleichen")
        t = QTableWidget(0, len(self.VERGLEICH_KOPF))
        t.setHorizontalHeaderLabels(self.VERGLEICH_KOPF)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setWordWrap(True)
        zeilen = self.varianten_vergleich()
        t.setRowCount(len(zeilen))
        beste = min((z[2], z[3], -z[4]) for z in zeilen)
        for r, z in enumerate(zeilen):
            for c, w in enumerate(z):
                zelle = _zelle(str(w), rechts=c in (2, 3, 4, 5))
                if r and (z[2], z[3], -z[4]) == beste and c == 0:
                    zelle.setBackground(stil.farbe(stil.GRUEN_FLAECHE))
                    zelle.setForeground(stil.farbe(stil.TEXT))
                t.setItem(r, c, zelle)
        t.resizeColumnsToContents()
        t.setColumnWidth(1, min(t.columnWidth(1), 360))
        t.resizeRowsToContents()
        t.horizontalHeader().setStretchLastSection(True)
        hinweis = QLabel("Jede Variante ist gegen den Plan von jetzt gerechnet. Grün: am wenigsten Aufträge, die nicht "
                         "zu halten sind (dann knapp, dann früher fertig). Laden holt eine Variante in das Fenster, "
                         "erst „Übernehmen“ ändert die Planung.")
        hinweis.setWordWrap(True)
        kn = QDialogButtonBox(QDialogButtonBox.Close)
        kn.button(QDialogButtonBox.Close).setText("Schließen")
        kn.rejected.connect(d.reject)
        lay = QVBoxLayout(d)
        lay.addWidget(t, 1)
        lay.addWidget(hinweis)
        lay.addWidget(kn)
        d.tabelle = t
        d.resize(1000, 380)
        if zeigen:
            d.exec()
        return d

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
    def __init__(self, db, heute=None, platz=None, werkstatt=None, programmordner=None, lizenz=None):
        """platz: Ordner der Auslastung.ini dieses Platzes (Vorgabe neben dem Programm); werkstatt: True startet in
        der Werkstatt-Ansicht (Vorgabe: wie an diesem Platz gemerkt); programmordner: Ordner des fertigen Programms
        für das Online-Update (None beim Start aus dem Quelltext: kein Update); lizenz: lizenzen.Stelle (Plan 2.4,
        None = voller Zugriff ohne Hinweise, z. B. in Tests)."""
        super().__init__()
        self.db, self.heute_fest, self.platz = db, heute, platz
        self.lizenz = lizenz
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
        # V3 (Plan 2.7): Glocke mit den Warnungen neben der Werkstatt-Ansicht
        self.warn, self.warn_gezeigt = [], None   # aktuelle Warnungen; Schlüssel, die schon gemeldet wurden
        self.k_glocke = QPushButton("🔔")
        self.k_glocke.setToolTip("Warnungen: Liefertermin in Gefahr, Material fehlt, Maschine steht, Fremdarbeit "
                                 "nicht zurück. Klick zeigt die Liste.")
        self.glocke_menue = QMenu(self)
        self.k_glocke.setMenu(self.glocke_menue)
        ecke = QWidget()
        el = QHBoxLayout(ecke)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(6)
        el.addWidget(self.k_glocke)
        el.addWidget(self.k_werkstatt)
        self.reiter.setCornerWidget(ecke, Qt.TopRightCorner)
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
        self.abgleich_zeile = QLabel("")          # N2: letzter Abgleich mit der Excel-Liste
        self.statusBar().addPermanentWidget(self.abgleich_zeile)
        self.lizenz_zeile = QLabel("")            # Plan 2.4: Hinweis zur Lizenz (läuft ab, nur ansehen)
        self.lizenz_zeile.setTextFormat(Qt.PlainText)
        self.lizenz_zeile.hide()
        self.statusBar().addPermanentWidget(self.lizenz_zeile)
        self.lizenz_anwenden(laden=False)
        self.stand = db.stand()
        self.uhr = QTimer(self)                   # anderer Platz hat gespeichert, oder eine Start/Stopp-Uhr läuft
        self.uhr.timeout.connect(self.takt)
        self.uhr.start(5000)
        self.laden()
        self.uebergabe_pruefen()
        self.abgleichen()
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
        self.a_einfuegen.setEnabled(planen)
        self.a_papierkorb.setEnabled(planen)
        self.reiter.setTabEnabled(EINSTELLUNGEN, verwalten)
        self.reiter.setTabToolTip(EINSTELLUNGEN, "" if verwalten else "Einstellungen ändert nur die Rolle Verwaltung.")
        if not verwalten and self.reiter.currentIndex() == EINSTELLUNGEN:
            self.reiter.setCurrentIndex(0)
        if self.db.rechte_an():
            self.wer_zeile.setText(f"Benutzer: {self.db.wer or 'unbekannt'} ({D.ROLLE_TEXT[rolle]})")
        else:
            self.wer_zeile.setText("")

    # ------------------------------------------------------------------ Lizenz (Plan 2.4)
    def lizenz_anwenden(self, laden=True):
        """Zustand der Lizenz neu prüfen: ohne gültige Lizenz nur ansehen (Rolle Nur lesen), Hinweis unten rechts."""
        if self.lizenz is None:
            return None
        try:
            z = self.lizenz.zustand if self.lizenz.zustand is not None and not laden else self.lizenz.pruefen()
        except Exception as e:  # noqa: BLE001 – eine kaputte Prüfung darf das Programm nicht öffnen lassen
            self.db.nur_ansehen = f"Lizenz nicht prüfbar ({e})"
            self.lizenz_zeile.setText(f"Nur ansehen: {self.db.nur_ansehen}")
            self.lizenz_zeile.show()
            return None
        self.db.nur_ansehen = z.nur_lesen
        farbe = {"gelb": stil.GELB_TEXT, "rot": stil.ROT}.get(z.farbe)
        self.lizenz_zeile.setText(z.hinweis)
        self.lizenz_zeile.setStyleSheet(f"color: {stil.umsetzen(farbe)}; font-weight: bold;" if farbe else "")
        self.lizenz_zeile.setVisible(bool(z.hinweis))
        if laden:
            self.laden()
        return z

    def lizenz_zeigen(self, zeigen=True):
        from rohrlaser.lizenz_dialog import LizenzDialog
        d = LizenzDialog(self, self.lizenz, stumm=not zeigen)
        if zeigen:
            d.exec()
        return d

    def takt(self):
        neu = self.db.stand()
        if neu != self.stand or self.db.uhr_laeuft():
            self.stand = neu
            if not QApplicationModal():
                self.laden()
        self.takte = getattr(self, "takte", 0) + 1
        if self.takte % 720 == 0 and self.lizenz is not None:     # etwa jede Stunde: Lizenz (Ablauf über Nacht)
            self.lizenz_anwenden()
        if self.takte % 12 == 0 and not QApplicationModal():       # etwa jede Minute: neue Übergabe im Ordner?
            self.warnungen_zeigen()                                 # V3: eine Maschine steht schon länger
            self.uebergabe_pruefen()
            self.abgleichen()

    # ------------------------------------------------------------------ Abgleich mit der Excel-Liste (N2)
    def abgleichen(self, immer=False):
        """N2 (Plan 2.2): liest die eingestellte Excel-Liste, wenn sie seit dem letzten Mal gespeichert wurde, und
        übernimmt neue und geänderte Aufträge ohne Rückfrage (vorher Sicherung). Ergebnis: Text für die Statuszeile
        oder None (kein Abgleich eingestellt, Datei unverändert, keine Rechte)."""
        pfad = (self.db.einstellung("abgleich_datei") or "").strip()
        if not pfad or not self.db.darf("auftraege"):
            self.abgleich_zeile.setText("")
            return None
        try:
            stempel = Path(pfad).stat().st_mtime
        except OSError:
            self.abgleich_zeile.setText("Excel-Abgleich: Datei nicht gefunden")
            return self.abgleich_zeile.text()
        if not immer and getattr(self, "abgleich_stempel", None) == (pfad, stempel):
            return None
        try:
            ergebnis = austausch.lesen(self.db, pfad)
        except (OSError, IndexError, ValueError) as e:  # wird vielleicht gerade gespeichert: beim nächsten Mal
            self.abgleich_zeile.setText(f"Excel-Abgleich: Datei nicht lesbar ({e})")
            return self.abgleich_zeile.text()
        self.abgleich_stempel = (pfad, stempel)
        if ergebnis["neu"] or ergebnis["geaendert"]:
            self.db.sichern("vor-Abgleich")
            austausch.uebernehmen(self.db, ergebnis)
            self.laden()
        uhr = datetime.datetime.now().strftime("%H:%M")
        teile = [f"{len(ergebnis['neu'])} neu", f"{len(ergebnis['geaendert'])} geändert"]
        if ergebnis["fehler"]:
            teile.append(f"{len(ergebnis['fehler'])} Zeilen mit Fehler")
        text = f"Excel-Abgleich {uhr}: " + ", ".join(teile)
        self.abgleich_zeile.setText(text)
        self.abgleich_zeile.setToolTip(austausch.zusammenfassung(ergebnis))
        return text

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
                if ergebnis["neu"] or ergebnis["geaendert"] or ergebnis["fehler"] or ergebnis.get("storno"):
                    self.ueb_datei, self.ueb_ergebnis = pfad, ergebnis
                    break
                austausch.gelesen_merken(self.db, pfad)
        if self.ueb_datei is None:
            self.ueb_zeile.setVisible(False)
            return None
        e = self.ueb_ergebnis
        teile = [f"{len(e['neu'])} neue Aufträge" if len(e["neu"]) != 1 else "1 neuer Auftrag",
                 f"{len(e['geaendert'])} geänderte" if len(e["geaendert"]) != 1 else "1 geänderter"]
        if e.get("storno"):
            teile.append(f"{len(e['storno'])} storniert")
        if e["fehler"]:
            teile.append(f"{len(e['fehler'])} Zeilen mit Fehler" if len(e["fehler"]) != 1 else "1 Zeile mit Fehler")
        self.ueb_text.setText(f"<b>Neue Übergabe aus der Kalkulation:</b> {self.ueb_datei.name} · " + ", ".join(teile))
        self.ueb_zeile.setVisible(True)
        return self.ueb_datei

    def rueckmeldung_pruefen(self):
        """Plan 2.8: Rückmeldung an die Kalkulation schreiben, wenn sie fällig ist (schnittstelle.faellig)."""
        try:
            if schnittstelle.faellig(self.db, self.heute()):
                return schnittstelle.rueckmeldung_schreiben(self.db, heute=self.heute())
        except (OSError, ValueError, KeyError) as e:   # Ordner im Netz nicht erreichbar o. Ä.: beim nächsten Mal
            self.statusBar().showMessage(f"Rückmeldung an die Kalkulation nicht geschrieben: {e}", 8000)
        return None

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
        self.a_csv_ein = mehr.addAction("Aus Excel oder CSV einlesen …", lambda: self.csv_einlesen())
        self.a_einfuegen = mehr.addAction("Aus Excel einfügen (Strg+V)", lambda: self.einfuegen())
        self.a_einfuegen.setShortcut(QKeySequence.Paste)
        self.a_einfuegen.setShortcutContext(Qt.WindowShortcut)
        self.addAction(self.a_einfuegen)            # N1: Strg+V gilt im ganzen Fenster, nicht nur im offenen Menü
        mehr.addAction("CSV speichern …", lambda: self.csv_speichern())
        mehr.addSeparator()
        self.a_stueck = mehr.addAction("Stück fertig melden …", lambda: self.stueck_melden())
        self.a_stueck.setToolTip("Fortschritt nach Stückzahl: z. B. 35 von 50 Stück fertig. Die Restlaufzeit rechnet "
                                 "sich dann aus den offenen Stück.")
        self.a_wiederholen = mehr.addAction("Wiederholauftrag aus diesem Auftrag …", lambda: self.wiederholen())
        self.a_wiederholen.setToolTip("Neuer Auftrag nach dem Muster des gewählten: Kunde, Maschine, Abmessung, "
                                      "Arbeitsgänge und Zusatzschritte; bei einem fertigen Auftrag die tatsächliche "
                                      "Laufzeit vom letzten Mal.")
        self.a_verlauf = mehr.addAction("Änderungsverlauf …", lambda: self.verlauf())
        self.a_papierkorb = mehr.addAction("Papierkorb …", lambda: self.papierkorb())
        self.k_mehr.setMenu(mehr)
        for k, f in ((self.k_neu, self.neu), (self.k_aendern, self.aendern), (self.k_uhr, self.uhr_schalten),
                     (self.k_fertig, self.fertig_melden), (self.k_oeffnen, self.wieder_oeffnen),
                     (self.k_loeschen, self.loeschen)):
            k.clicked.connect(lambda _=False, f=f: f())
        # E4 (Plan 2.3): Schnelleingabe – eine Zeile tippen, Enter, Auftrag ist angelegt
        self.schnell = QLineEdit()
        self.schnell.setPlaceholderText("Schnell anlegen: A-2701 LT7 3:30 25.11. Kunde, dann Enter")
        self.schnell.setToolTip("Auftragsnummer, Maschine, Laufzeit (3:30, 3 h 30 min, 90 min) und nach Wunsch "
                                "Liefertermin (TT.MM.) und Kunde, in beliebiger Reihenfolge. Enter legt den Auftrag an.")
        self.schnell.setClearButtonEnabled(True)
        self.schnell.returnPressed.connect(lambda: self.schnell_anlegen())
        oben = QHBoxLayout()
        oben.addWidget(self.filter)
        oben.addWidget(self.suche, 1)
        oben.addWidget(self.schnell, 1)
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
        # V3: Zeile mit den Warnungen (wie eine Kachel auf der Startseite)
        self.warn_zeile = QLabel("")
        self.warn_zeile.setWordWrap(True)
        self.warn_zeile.setTextFormat(Qt.RichText)
        self.warn_zeile.setStyleSheet(f"QLabel {{ background: {stil.umsetzen(stil.ROT_FLAECHE)}; color: "
                                      f"{stil.umsetzen(stil.TEXT)}; border-radius: 4px; padding: 6px 10px; }}")
        self.warn_zeile.linkActivated.connect(lambda _l: self.glocke_zeigen())
        self.warn_zeile.setVisible(False)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addLayout(knoepfe)
        lay.addWidget(self.warn_zeile)
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
                "Abweichung", "Fertig am", "Bemerkung", "Durchlaufzeit (Plan)", "Material (Rüsten)",
                "Puffer [AT]", "Spätester Start", "Priorität"] + felder
        prio = self.db.prioritaeten()
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
            ] + self._v4_zellen(a, p, prio) + [_zelle(a["zusatz"].get(n, "")) for n in felder]
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
        self.liste.setColumnHidden(13, not self.db.funktion("material") or not any(a.get("material") for a in zeilen))
        for c in (14, 15):                        # V4: Puffer und spätester Start nur bei offenen Aufträgen
            self.liste.setColumnHidden(c, self.filter.currentIndex() == 1)
        self.liste.setColumnHidden(16, not prio)  # V10: erst sichtbar, wenn ein Kunde A oder C ist
        kopfzeile = self.liste.horizontalHeader()
        for c, ziel in ((16, 2), (14, 9), (15, 10)):   # neben Kunde bzw. hinter Terminrisiko
            if kopfzeile.visualIndex(c) != ziel:
                kopfzeile.moveSection(kopfzeile.visualIndex(c), ziel)
        self.liste.setSortingEnabled(True)
        self.liste.resizeColumnsToContents()
        self.liste.horizontalHeader().setSectionResizeMode(11, QHeaderView.Stretch)
        self.summe.setText(f"{len(zeilen)} Aufträge" + (f", noch {self.lz(offen_min)} offene Laufzeit"
                                                        if offen_min else ""))
        if alt is None or not self.waehlen(alt["id"]):
            self.liste.clearSelection()
            self.liste.setCurrentCell(-1, -1)
        self.knoepfe_setzen()

    def _v4_zellen(self, a, p, prio):
        """V4/V10: Zellen Puffer [AT], Spätester Start und Priorität einer Zeile der Auftragsliste."""
        offen = a["status"] != D.FERTIG
        puffer = p.get("puffer") if offen else None
        spaet = p.get("spaetester_start") if offen else None
        z_puffer = _zelle("" if puffer is None else str(puffer), True, sortier=puffer if puffer is not None else 9999)
        z_spaet = _zelle(_tag(spaet), sortier=str(spaet or "9999"))
        if spaet is not None:
            z_spaet.setToolTip("Spätester Start = geplanter Start plus Puffer in Arbeitstagen: so spät kann der "
                               "Auftrag noch anfangen und hält den Liefertermin, wenn alles andere bleibt.")
            if spaet <= self.heute():
                z_spaet.setBackground(stil.farbe(stil.ROT_FLAECHE if spaet < self.heute() else stil.GELB_FLAECHE))
                z_spaet.setForeground(stil.farbe(stil.TEXT))
        stufe = prio.get(str(a["kunde"] or "").strip().casefold(), "B")
        return [z_puffer, z_spaet, _zelle(stufe if prio else "", sortier=stufe)]

    # ---------------------------------------------------------------- V3 (Plan 2.7): Warnungen
    def warnungen_zeigen(self):
        """Warnungen neu bestimmen: Glocke, Zeile im Reiter Aufträge, auf Wunsch Windows-Hinweis bei neuen."""
        if self.ein is None:
            return []
        try:
            self.warn = warnungen.liste(self.db, self.aus, self.ein, self.heute())
        except Exception:                         # eine Warnung darf das Programm nie aufhalten
            self.warn = []
        an = self.db.funktion("warnungen")
        n, rot = len(self.warn), any(w["stufe"] == warnungen.ROT for w in self.warn)
        self.k_glocke.setVisible(an)
        self.k_glocke.setText(f"🔔 {n}" if n else "🔔")
        self.k_glocke.setStyleSheet(
            f"QPushButton {{ background: {stil.umsetzen(stil.ROT if rot else stil.ORANGE)}; color: white; "
            "font-weight: bold; padding: 2px 10px; }" if n else "")
        self.glocke_menue.clear()
        for w in self.warn:
            aktion = self.glocke_menue.addAction(("● " if w["stufe"] == warnungen.ROT else "○ ") + w["text"])
            aktion.triggered.connect(lambda _=False, w=w: self.engpass_oeffnen(w) if w["art"] == "engpass"
                                     else self.warnung_oeffnen(w["auftrag_id"]))
        if not self.warn:
            self.glocke_menue.addAction("Keine Warnungen").setEnabled(False)
        self.glocke_menue.addSeparator()
        a_win = self.glocke_menue.addAction("Windows-Hinweis bei neuer Warnung (dieser Platz)")
        a_win.setCheckable(True)
        a_win.setChecked(ort.ini_lesen(self.platz).get("windows_hinweis") == "1")
        a_win.toggled.connect(lambda an_: self._platz_merken("windows_hinweis", "1" if an_ else "0"))
        if n and an:
            erste = "; ".join(html.escape(w["text"]) for w in self.warn[:2])
            self.warn_zeile.setText(f"<b>⚠ {n} Warnung{'en' if n != 1 else ''}:</b> {erste}"
                                    + (" …" if n > 2 else "") + " &nbsp;<a href='#'>alle anzeigen</a>")
        self.warn_zeile.setVisible(bool(n and an))
        neu = [w for w in self.warn if self.warn_gezeigt is not None and w["schluessel"] not in self.warn_gezeigt]
        self.warn_gezeigt = {w["schluessel"] for w in self.warn}
        if neu:
            self._windows_hinweis(neu)
        return self.warn

    def glocke_zeigen(self):
        self.k_glocke.showMenu()

    def warnung_oeffnen(self, auftrag_id):
        """Klick auf eine Warnung: den Auftrag im Reiter Aufträge zeigen."""
        if self.werkstatt_ist_an():
            self.werkstatt_an(False)
        if auftrag_id is None:                    # Plan 2.9: Wartung oder Bediener -> Einstellungen
            self.reiter.setCurrentIndex(EINSTELLUNGEN)
            self.laden()
            for i in range(self.e_reiter.count()):
                if self.e_reiter.tabText(i) == "Wartung und Bediener":
                    self.e_reiter.setCurrentIndex(i)
            return None
        self.filter.setCurrentIndex(0)
        self.suche.clear()
        self.reiter.setCurrentIndex(0)
        return self.waehlen(auftrag_id)

    def _windows_hinweis(self, neu):
        """Optional (Einstellung je Platz): Hinweis unten rechts in Windows, nur für neu hinzugekommene Warnungen."""
        if ort.ini_lesen(self.platz).get("windows_hinweis") != "1":
            return False
        from PySide6.QtWidgets import QSystemTrayIcon
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        if getattr(self, "tray", None) is None:
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.messageClicked.connect(lambda: (self.showNormal(), self.activateWindow(), self.glocke_zeigen()))
            self.tray.show()
        self.tray.showMessage(f"{NAME}: {len(neu)} neue Warnung{'en' if len(neu) != 1 else ''}",
                              "\n".join(w["text"] for w in neu[:4]), QSystemTrayIcon.Warning, 15000)
        return True

    # ------------------------------------------------------------------ Plan 2.9: Wartung und Bediener
    def _wartung_gruppe(self):
        g = QGroupBox("Wartung im Kalender")
        self.g_wartung = g
        lay = QVBoxLayout(g)
        info = QLabel("Wartungen nehmen der Maschine an ihrem Tag die Dauer weg; die Plantafel zeigt sie grau, die "
                      "Glocke meldet sie 3 Arbeitstage vorher. Wiederkehrend alle X Wochen oder alle X Laufstunden "
                      "(aus den Fertigmeldungen).")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.e_wartungen = QTableWidget(0, 6)
        self.e_wartungen.setHorizontalHeaderLabels(("Maschine", "Wartung", "Wann", "Dauer", "Nächste", "Zuletzt erledigt"))
        self.e_wartungen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.e_wartungen.setSelectionMode(QAbstractItemView.SingleSelection)
        self.e_wartungen.verticalHeader().setVisible(False)
        self.e_wartungen.horizontalHeader().setStretchLastSection(True)
        self.e_wartungen.setMinimumHeight(150)
        self.e_wartungen.doubleClicked.connect(lambda _i: self.wartung_bearbeiten(self._wartung_gewaehlt()))
        lay.addWidget(self.e_wartungen)
        knoepfe = QHBoxLayout()
        for text, tun in (("Neue Wartung …", lambda: self.wartung_bearbeiten()),
                          ("Ändern …", lambda: self.wartung_bearbeiten(self._wartung_gewaehlt())),
                          ("Erledigt", lambda: self.wartung_erledigt(self._wartung_gewaehlt())),
                          ("Löschen", lambda: self.wartung_loeschen(self._wartung_gewaehlt()))):
            k = QPushButton(text)
            k.clicked.connect(lambda _=False, t=tun: t())
            knoepfe.addWidget(k)
        knoepfe.addStretch(1)
        lay.addLayout(knoepfe)
        return g

    def _personen_gruppe(self):
        g = QGroupBox("Bediener und Einrichter")
        self.g_personen = g
        lay = QVBoxLayout(g)
        info = QLabel("Wer bedient welche Maschine? Ist niemand da, der eine Maschine bedienen darf (Urlaub, krank), "
                      "plant das Programm an dem Tag weniger Stunden auf ihr ein und warnt 5 Arbeitstage vorher. "
                      "Maschinen, die hier niemand bedient, rechnen wie bisher.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.e_personen = QTableWidget(0, 5)
        self.e_personen.setHorizontalHeaderLabels(("Name", "Maschinen", "Einrichter", "Abwesend", "Aktiv"))
        self.e_personen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.e_personen.setSelectionMode(QAbstractItemView.SingleSelection)
        self.e_personen.verticalHeader().setVisible(False)
        self.e_personen.horizontalHeader().setStretchLastSection(True)
        self.e_personen.setMinimumHeight(150)
        self.e_personen.doubleClicked.connect(lambda _i: self.person_bearbeiten(self._person_gewaehlt()))
        lay.addWidget(self.e_personen)
        knoepfe = QHBoxLayout()
        for text, tun in (("Neue Person …", lambda: self.person_bearbeiten()),
                          ("Ändern …", lambda: self.person_bearbeiten(self._person_gewaehlt())),
                          ("Löschen", lambda: self.person_loeschen(self._person_gewaehlt()))):
            k = QPushButton(text)
            k.clicked.connect(lambda _=False, t=tun: t())
            knoepfe.addWidget(k)
        knoepfe.addStretch(1)
        lay.addLayout(knoepfe)
        return g

    @staticmethod
    def _wartung_wann(w):
        if w["art"] == "wochen":
            return f"alle {w['wochen']} Wochen ab {w['datum'].strftime('%d.%m.%Y')}"
        if w["art"] == "stunden":
            return f"alle {w['stunden']:g} Laufstunden ab {w['datum'].strftime('%d.%m.%Y')}"
        return f"am {w['datum'].strftime('%d.%m.%Y')}"

    def _wartung_naechste(self, wid):
        tage = sorted(d for (_m, d), liste in ((self.aus or {}).get("wartung") or {}).items()
                      if any(x["id"] == wid for x in liste))
        return tage[0] if tage else None

    def _wartung_bediener_fuellen(self):
        if not hasattr(self, "e_wartungen"):
            return
        liste = self.db.wartungen()
        self.e_wartungen.setRowCount(0)
        self.e_wartungen.setRowCount(len(liste))
        for r, w in enumerate(liste):
            naechste = self._wartung_naechste(w["id"])
            werte = (w["maschine"], w["name"], self._wartung_wann(w), laufzeit.text(int(w["dauer_h"] * 60 + 0.5)),
                     naechste.strftime("%d.%m.%Y") if naechste else "–",
                     w["erledigt"].strftime("%d.%m.%Y") if w["erledigt"] else "")
            for c, t in enumerate(werte):
                self.e_wartungen.setItem(r, c, _zelle(t, daten=w["id"] if c == 0 else None))
        self.e_wartungen.resizeColumnsToContents()
        personen = self.db.personen()
        self.e_personen.setRowCount(0)
        self.e_personen.setRowCount(len(personen))
        for r, p in enumerate(personen):
            werte = (p["name"], ", ".join(p["maschinen"]) or "–", "ja" if p["einrichter"] else "", p["abwesend"],
                     "ja" if p["aktiv"] else "nein")
            for c, t in enumerate(werte):
                self.e_personen.setItem(r, c, _zelle(t, daten=p["id"] if c == 0 else None))
        self.e_personen.resizeColumnsToContents()

    def _wartung_gewaehlt(self):
        r = self.e_wartungen.currentRow()
        return self.e_wartungen.item(r, 0).data(Qt.UserRole) if r >= 0 and self.e_wartungen.item(r, 0) else None

    def _person_gewaehlt(self):
        r = self.e_personen.currentRow()
        return self.e_personen.item(r, 0).data(Qt.UserRole) if r >= 0 and self.e_personen.item(r, 0) else None

    def _nach_aenderung(self):
        self.aus, self.ein = rechnung.einlasten(self.db, self.heute(), self.wochen.value())
        self._wartung_bediener_fuellen()

    def wartung_bearbeiten(self, wid=None, werte=None):
        """Dialog Wartung; werte=dict(maschine, name, art, datum, wochen, stunden, dauer_h) speichert ohne Dialog."""
        if not self.darf("einstellungen"):
            return None
        alt = next((w for w in self.db.wartungen() if w["id"] == wid), None) if wid else None
        if werte is None:
            d = QDialog(self)
            d.setWindowTitle("Wartung")
            form = QFormLayout(d)
            maschine = QComboBox()
            maschine.addItems([m["name"] for m in self.db.maschinen()])
            name = QLineEdit(alt["name"] if alt else "Wartung")
            art = QComboBox()
            for k, t in D.WARTUNG_ARTEN.items():
                art.addItem(t, k)
            datum = QDateEdit()
            datum.setCalendarPopup(True)
            datum.setDisplayFormat("dd.MM.yyyy")
            tag = alt["datum"] if alt else self.heute()
            datum.setDate(QDate(tag.year, tag.month, tag.day))
            wochen_n = QSpinBox()
            wochen_n.setRange(1, 104)
            wochen_n.setSuffix(" Wochen")
            stunden_n = QSpinBox()
            stunden_n.setRange(1, 100000)
            stunden_n.setSuffix(" Laufstunden")
            dauer = QDoubleSpinBox()
            dauer.setRange(0.25, 24)
            dauer.setSingleStep(0.5)
            dauer.setSuffix(" h")
            if alt:
                maschine.setCurrentText(alt["maschine"])
                art.setCurrentIndex(max(0, art.findData(alt["art"])))
                wochen_n.setValue(max(1, alt["wochen"]))
                stunden_n.setValue(max(1, int(alt["stunden"])))
                dauer.setValue(alt["dauer_h"])
            else:
                wochen_n.setValue(4)
                stunden_n.setValue(500)
                dauer.setValue(2)
            form.addRow("Maschine", maschine)
            form.addRow("Was", name)
            form.addRow("Wiederholung", art)
            form.addRow("Am / ab", datum)
            form.addRow("Alle", wochen_n)
            form.addRow("Alle", stunden_n)
            form.addRow("Dauer", dauer)

            def sichtbar(_i=0):
                form.setRowVisible(wochen_n, art.currentData() == "wochen")
                form.setRowVisible(stunden_n, art.currentData() == "stunden")
            art.currentIndexChanged.connect(sichtbar)
            sichtbar()
            kn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            kn.accepted.connect(d.accept)
            kn.rejected.connect(d.reject)
            form.addRow(kn)
            if d.exec() != QDialog.Accepted:
                return None
            q = datum.date()
            werte = dict(maschine=maschine.currentText(), name=name.text(), art=art.currentData(),
                         datum=datetime.date(q.year(), q.month(), q.day()), wochen=wochen_n.value(),
                         stunden=stunden_n.value(), dauer_h=dauer.value())
        try:
            neu = self.db.wartung_speichern(werte, wid)
        except D.Fehler as e:
            self.meldung(str(e))
            return None
        self._nach_aenderung()
        return neu

    def wartung_erledigt(self, wid, tag=None):
        if wid is None or not self.darf("einstellungen"):
            return
        self.db.wartung_erledigt(wid, tag or self.heute())
        self._nach_aenderung()

    def wartung_loeschen(self, wid):
        if wid is None or not self.darf("einstellungen"):
            return
        self.db.wartung_loeschen(wid)
        self._nach_aenderung()

    def person_bearbeiten(self, pid=None, werte=None):
        """Dialog Person; werte=dict(name, maschinen, einrichter, abwesend, aktiv) speichert ohne Dialog."""
        if not self.darf("einstellungen"):
            return None
        alt = next((p for p in self.db.personen() if p["id"] == pid), None) if pid else None
        if werte is None:
            d = QDialog(self)
            d.setWindowTitle("Bediener")
            form = QFormLayout(d)
            name = QLineEdit(alt["name"] if alt else "")
            haken = []
            box = QVBoxLayout()
            for m in self.db.maschinen():
                c = QCheckBox(m["name"])
                c.setChecked(bool(alt and m["name"] in alt["maschinen"]))
                haken.append(c)
                box.addWidget(c)
            einrichter = QCheckBox("darf rüsten und einrichten")
            einrichter.setChecked(bool(alt and alt["einrichter"]))
            abwesend = QLineEdit(alt["abwesend"] if alt else "")
            abwesend.setPlaceholderText("z. B. 24.11.2026-28.11.2026; 02.12.2026")
            abwesend.setToolTip("Urlaub, krank, Schule: einzelne Tage oder Zeiträume, durch Semikolon getrennt.")
            abwesend.setMinimumWidth(300)
            aktiv = QCheckBox("arbeitet hier")
            aktiv.setChecked(alt["aktiv"] if alt else True)
            form.addRow("Name", name)
            form.addRow("Bedient", box)
            form.addRow("Einrichter", einrichter)
            form.addRow("Abwesend (Urlaub, krank)", abwesend)
            form.addRow("", aktiv)
            kn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            kn.accepted.connect(d.accept)
            kn.rejected.connect(d.reject)
            form.addRow(kn)
            if d.exec() != QDialog.Accepted:
                return None
            werte = dict(name=name.text(), maschinen=[c.text() for c in haken if c.isChecked()],
                         einrichter=einrichter.isChecked(), abwesend=abwesend.text(), aktiv=aktiv.isChecked())
        try:
            neu = self.db.person_speichern(werte, pid)
        except D.Fehler as e:
            self.meldung(str(e))
            return None
        self._nach_aenderung()
        return neu

    def person_loeschen(self, pid):
        if pid is None or not self.darf("einstellungen"):
            return
        self.db.person_loeschen(pid)
        self._nach_aenderung()

    def _warn_gruppe(self):
        g = QGroupBox("Warnungen, Kundenpriorität und Planungsregeln")
        self.g_warn = g
        form = QFormLayout(g)
        self.e_warn_stopp = QSpinBox()
        self.e_warn_stopp.setRange(1, 600)
        self.e_warn_stopp.setSuffix(" min")
        self.e_warn_stopp.setToolTip("Warnung, wenn eine Unterbrechung mit Grund länger dauert.")
        self.e_warn_material = QSpinBox()
        self.e_warn_material.setRange(0, 20)
        self.e_warn_material.setSuffix(" Arbeitstage")
        self.e_warn_material.setToolTip("Warnung, wenn das Material noch nicht da ist und der Auftrag in so vielen "
                                        "Arbeitstagen starten soll.")
        self.e_prio_tage = QSpinBox()
        self.e_prio_tage.setRange(0, 30)
        self.e_prio_tage.setSuffix(" Tage")
        self.e_prio_tage.setToolTip("A-Kunden werden so eingeplant, als läge ihr Liefertermin so viele Tage früher, "
                                    "C-Kunden so viele Tage später. Der Liefertermin selbst bleibt.")
        self.e_rest_prozent = QSpinBox()
        self.e_rest_prozent.setRange(0, 100)
        self.e_rest_prozent.setSuffix(" % der Kalkulation")
        self.e_rest_min = QSpinBox()
        self.e_rest_min.setRange(0, 600)
        self.e_rest_min.setSuffix(" min")
        for feld in (self.e_rest_prozent, self.e_rest_min):
            feld.setToolTip("Läuft ein Auftrag länger als kalkuliert, plant das Programm bis zur Fertigmeldung "
                            "noch so viel Restzeit ein (der größere Wert, höchstens die Kalkulation).")
        self.e_einfrieren = QSpinBox()
        self.e_einfrieren.setRange(0, 20)
        self.e_einfrieren.setSuffix(" Arbeitstage")
        self.e_einfrieren.setToolTip("Optimieren und Ausweichmaschine ändern nichts an Aufträgen, die in so vielen "
                                     "Arbeitstagen ab heute beginnen (0 = aus). Von Hand verschieben geht weiter.")
        for feld, schluessel in ((self.e_warn_stopp, "warn_stopp_min"), (self.e_warn_material, "warn_material_tage"),
                                 (self.e_prio_tage, "prio_tage"), (self.e_rest_prozent, "rest_prozent"),
                                 (self.e_rest_min, "rest_min"), (self.e_einfrieren, "einfrieren_tage")):
            feld.valueChanged.connect(lambda w, s=schluessel: self._warn_speichern(s, w))
            feld.setMaximumWidth(180)
        form.addRow("Maschine steht länger als", self.e_warn_stopp)
        form.addRow("Material fehlt, Start in höchstens", self.e_warn_material)
        form.addRow("Kundenpriorität verschiebt um", self.e_prio_tage)
        rest = QHBoxLayout()
        rest.addWidget(self.e_rest_prozent)
        rest.addWidget(QLabel("mindestens"))
        rest.addWidget(self.e_rest_min)
        rest.addStretch(1)
        form.addRow("Länger als kalkuliert: Restzeit", rest)
        form.addRow("Nicht umplanen: die nächsten", self.e_einfrieren)
        self.e_kunden = QTableWidget()
        self.e_kunden.setColumnCount(2)
        self.e_kunden.setHorizontalHeaderLabels(("Kunde", "Priorität"))
        self.e_kunden.verticalHeader().setVisible(False)
        self.e_kunden.setMinimumHeight(160)
        self.e_kunden.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        form.addRow("Kunden", self.e_kunden)
        text = QLabel("A = wichtig, wird vorgezogen; B = normal; C = kann warten. Von Hand vorgezogene Aufträge und "
                      "feste Plätze gehen weiter vor.")
        text.setWordWrap(True)
        text.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        form.addRow(text)
        return g

    def _warn_fuellen(self):
        for feld, schluessel, vorgabe in ((self.e_warn_stopp, "warn_stopp_min", 30),
                                          (self.e_warn_material, "warn_material_tage", 2),
                                          (self.e_prio_tage, "prio_tage", 3), (self.e_rest_prozent, "rest_prozent", 15),
                                          (self.e_rest_min, "rest_min", 30), (self.e_einfrieren, "einfrieren_tage", 2)):
            feld.setValue(int(self.db.zahl(schluessel, vorgabe)))
        kunden = self.db.kunden()
        self.e_kunden.setRowCount(0)              # alte Auswahlfelder ganz entfernen, sonst bleiben sie stehen
        self.e_kunden.setRowCount(len(kunden))
        self.e_kunden_wahl = {}
        for r, k in enumerate(kunden):
            self.e_kunden.setItem(r, 0, _zelle(k))
            wahl = QComboBox()
            for stufe, t in PRIO_TEXT.items():
                wahl.addItem(t, stufe)
            wahl.setCurrentIndex(list(PRIO_TEXT).index(self.db.prioritaet(k)))
            wahl.currentIndexChanged.connect(lambda _i, k=k, w=wahl: self.prioritaet_setzen(k, w.currentData()))
            self.e_kunden.setCellWidget(r, 1, wahl)
            self.e_kunden_wahl[k] = wahl

    def _warn_speichern(self, schluessel, wert):
        if self.e_fuellt:
            return
        self.db.einstellung_setzen(schluessel, int(wert))
        self.laden()

    def prioritaet_setzen(self, kunde, stufe):
        """V10: Kundenpriorität ändern; gilt sofort für die Reihenfolge der Einplanung."""
        if self.e_fuellt:
            return
        self.db.prioritaet_setzen(kunde, stufe)
        self.laden()
        self.hinweis(f"{kunde}: Priorität {PRIO_TEXT.get(stufe, stufe)}.")

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
        self.a_wiederholen.setEnabled(a is not None and planen)
        self.a_stueck.setEnabled(offen and melden)

    def neu(self, zeigen=True):
        if not self.darf("auftraege"):
            return None
        d = AuftragDialog(self.db, parent=self)
        if zeigen and d.exec() == QDialog.Accepted:
            self.laden()
            self.waehlen(d.auftrag["id"])
        return d

    def wiederholen(self, auftrag_id=None, zeigen=True):
        """N7: neuen Auftrag nach dem Muster eines alten anlegen (Vorschlag, gespeichert wird erst mit Speichern)."""
        a = self.db.auftrag(auftrag_id) if auftrag_id is not None else self.gewaehlt()
        if a is None or not self.darf("auftraege"):
            return None
        d = AuftragDialog(self.db, self.db.wiederholung(a["id"]), self)
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
        # N2: Fortschritt nach Stückzahl melden (beim Stopp oder zum Schichtende)
        self.k_w_stueck = QPushButton("Stück fertig …")
        self.k_w_stueck.setToolTip("Wie viele Stück sind schon fertig? Die Restlaufzeit rechnet sich dann aus den "
                                   "offenen Stück.")
        self.k_w_stueck.clicked.connect(lambda _=False: self.werkstatt_stueck())
        zeile_st = QHBoxLayout()
        zeile_st.addStretch(1)
        zeile_st.addWidget(self.k_w_stueck)
        kl.addLayout(zeile_st)
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
            if teil.get("stueck_fertig") is not None and a.get("stueckzahl"):
                zustand += f" · {int(teil['stueck_fertig'])} von {int(a['stueckzahl'])} Stück fertig"
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
        self.k_w_stueck.setEnabled(bool(z) and melden and z["bereit"])

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

    def werkstatt_stueck(self, fertig=None, gesamt=None):
        a, g = self._werkstatt_teil()
        if a is None:
            return None
        return self.stueck_melden(a["id"], g["id"] if g is not None else None, fertig, gesamt, gross=True)

    def stueck_melden(self, auftrag_id=None, gang_id=None, fertig=None, gesamt=None, gross=False):
        """N2: „35 von 50 Stück fertig“ melden. Ohne fertig fragt ein kleines Fenster (fertig und gesamt vorgegeben:
        ohne Fenster, Tests). Ergebnis True, wenn gespeichert."""
        a = self.db.auftrag(auftrag_id) if auftrag_id is not None else self.gewaehlt()
        if a is None or a["status"] == D.FERTIG or not self.darf("melden"):
            return None
        g = None
        if a["gaenge"]:
            g = (next((x for x in a["gaenge"] if x["id"] == gang_id), None) if gang_id is not None else
                 self.gang_waehlen(a, "Für welchen Arbeitsgang Stück melden?"))
            if g is None or g["platz"] == D.FREMD:
                return None
        teil = g if g is not None else a
        if fertig is None:
            d = QDialog(self)
            d.setWindowTitle(f"Stück fertig: {a['nummer']}" + (f" · {g['name']}" if g is not None else ""))
            if gross:
                d.setStyleSheet("QLabel, QPushButton, QSpinBox { font-size: 15pt; }")
            s_fertig, s_gesamt = QSpinBox(), QSpinBox()
            for s in (s_fertig, s_gesamt):
                s.setRange(0, 10 ** 7)
                s.setSuffix(" Stück")
            s_gesamt.setMinimum(1)
            s_gesamt.setValue(int(a.get("stueckzahl") or 1))
            s_fertig.setValue(int(teil.get("stueck_fertig") or 0))
            form = QFormLayout()
            form.addRow("Fertig", s_fertig)
            form.addRow("von", s_gesamt)
            kn = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            kn.button(QDialogButtonBox.Save).setText("Speichern")
            kn.button(QDialogButtonBox.Cancel).setText("Abbrechen")
            kn.accepted.connect(d.accept)
            kn.rejected.connect(d.reject)
            lay = QVBoxLayout(d)
            lay.addLayout(form)
            lay.addWidget(kn)
            s_fertig.setFocus()
            s_fertig.selectAll()
            if d.exec() != QDialog.Accepted:
                return None
            fertig, gesamt = s_fertig.value(), s_gesamt.value()
        try:
            self.db.stueck_melden(a["id"], fertig, gesamt if gesamt is not None else a.get("stueckzahl") or 1,
                                  gang_id=g["id"] if g is not None else None)
        except D.Fehler as e:
            self.meldung(str(e))
            return False
        self.laden()
        return True

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

    def einfuegen(self, text=None, fragen=True):
        """N1 (Plan 2.2): Zeilen aus Excel kopiert (mit der Überschriftenzeile) und mit Strg+V eingefügt."""
        from PySide6.QtWidgets import QApplication
        if self.reiter.currentIndex() != 0 and text is None:
            return None
        if isinstance(QApplication.focusWidget(), QLineEdit) and text is None:
            QApplication.focusWidget().paste()    # in einem Eingabefeld bleibt Strg+V normales Einfügen
            return None
        text = QApplication.clipboard().text() if text is None else text
        if not text.strip():
            self.meldung("In der Zwischenablage ist nichts. In Excel die Zeilen mit der Überschriftenzeile markieren, "
                         "Strg+C, dann hier Strg+V.")
            return None
        return self.csv_einlesen(zeilen=austausch.text_zeilen(text), fragen=fragen)

    def schnell_anlegen(self, text=None):
        """E4: Zeile der Schnelleingabe lesen und den Auftrag anlegen. Ergebnis: Auftrag-ID oder None."""
        if not self.darf("auftraege"):
            return None
        text = self.schnell.text() if text is None else text
        try:
            werte = austausch.schnell_lesen(self.db, text, self.heute())
            if self.db.auftrag(nummer=werte["nummer"]):
                raise D.Fehler(f"Den Auftrag {werte['nummer']} gibt es schon (Ändern … oder Doppelklick).")
            neu = self.db.auftrag_speichern(werte)
        except (D.Fehler, laufzeit.Fehler) as e:
            self.statusBar().showMessage(str(e), 10000)
            return None
        self.schnell.clear()
        self.laden()
        self.waehlen(neu)
        termin = f", Liefertermin {werte['liefertermin'].strftime('%d.%m.%Y')}" if werte["liefertermin"] else ""
        extra = ""
        if werte.get("gaenge"):                   # Plan 2.6: erkannte Zusatzschritte nennen
            extra = f", {werte.get('stueckzahl') or 1} Stück, dann " + ", ".join(
                g["name"] + (f" {_arbeitstage(g['tage'])}" if g["tage"] else f" {laufzeit.text(g['kalk_min'])}")
                for g in werte["gaenge"][1:])
        self.hinweis(f"Auftrag {werte['nummer']} angelegt: {werte['maschine']}, "
                     f"{laufzeit.text(werte['kalk_min'])}{termin}{extra}.")
        return neu

    def csv_einlesen(self, pfad=None, fragen=True, zeilen=None):
        if not self.darf("auftraege"):
            return None
        if pfad is None and zeilen is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "Aufträge aus Excel oder CSV einlesen", "",
                                                  "Excel oder CSV (*.xlsx *.xlsm *.csv *.txt);;Alle (*)")
            if not pfad:
                return None
        try:
            ergebnis = austausch.lesen(self.db, pfad, zeilen=zeilen)
        except OSError as e:
            self.meldung(f"Die Datei lässt sich nicht lesen: {e}")
            return None
        text = austausch.zusammenfassung(ergebnis)
        if not ergebnis["neu"] and not ergebnis["geaendert"] and not ergebnis.get("storno"):
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
        pdf_menue.addAction("Monatsplan A3 quer (zum Aushängen) …", lambda: self.monat_pdf(gross=True))
        pdf_menue.addAction("Monatsplan A4 quer …", lambda: self.monat_pdf())
        self.k_pdf.setMenu(pdf_menue)
        self.k_auskunft = QPushButton("Terminauskunft …")
        self.k_auskunft.setToolTip("Wann wäre ein neuer Auftrag mit einer bestimmten Laufzeit fertig? Rechnet nur, "
                                   "speichert nichts.")
        self.k_auskunft.clicked.connect(lambda _=False: self.terminauskunft())
        # N8: freie Stunden je Maschine und Woche für den Vertrieb
        self.k_kapazitaet = QPushButton("Freie Kapazität …")
        self.k_kapazitaet.setToolTip("Freie Stunden je Maschine und Woche und der früheste Termin für eine Laufzeit, "
                                     "z. B. für Zusagen im Vertrieb. Rechnet nur, speichert nichts.")
        self.k_kapazitaet.clicked.connect(lambda _=False: self.kapazitaet_zeigen())
        self.k_arbeitsliste = QPushButton("Arbeitsliste PDF …")
        self.k_arbeitsliste.setToolTip("Je Maschine eine Seite für die Werkstatt: die Aufträge in der geplanten "
                                       "Reihenfolge mit Laufzeit, Start, Fertig-Datum und Liefertermin.")
        self.k_arbeitsliste.clicked.connect(lambda _=False: self.arbeitsliste_pdf())
        self.k_risiko = QPushButton("Terminrisiko zeigen")
        self.k_risiko.clicked.connect(lambda _=False: self.woche_waehlen(None, None))
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.balken = WochenBalken()
        # L1 (Plan 2.1): kompakt, damit die Plantafel auch bei 1366 x 768 alle Maschinen zeigt
        self.balken.ZEILE, self.balken.OBEN, self.balken.UNTEN = BALKEN_ZEILE, 28, 30
        self.balken.setToolTip(BALKEN_LEGENDE)
        self.balken.gewaehlt.connect(self.woche_waehlen)
        self.k_wenn = QPushButton("Was wäre, wenn …")
        self.k_wenn.setToolTip("Probeweise rechnen: Samstagsarbeit, Zusatzstunden in einer Woche, ein Auftrag auf "
                               "einer anderen Maschine. Gespeichert wird erst mit „Übernehmen“.")
        self.k_wenn.clicked.connect(lambda _=False: self.was_waere_wenn())
        self.k_material = QPushButton("Materialbedarf …")
        self.k_material.setToolTip("Stangen je Profil und Woche für die geplanten Aufträge (aus der Kalkulation), mit "
                                   "Material-Termin; nur zum Ansehen und als Excel.")
        self.k_material.clicked.connect(lambda _=False: self.materialbedarf_zeigen())
        self.k_optimieren = QPushButton("Optimieren …")
        self.k_optimieren.setToolTip("Sucht eine Reihenfolge und Maschinenverteilung, bei der möglichst kein Auftrag "
                                     "zu spät fertig wird, und zeigt sie als Vorschlag. Geändert wird erst mit "
                                     "„Übernehmen“.")
        opt_menue = QMenu(self.k_optimieren)
        self.a_ziele = {z: opt_menue.addAction(name, lambda z=z: self.optimieren(ziel=z)) for z, name in rechnung.ZIELE}
        opt_menue.addSeparator()
        self.a_buendeln = opt_menue.addAction("Bündeln …", lambda: self.buendeln())
        self.a_buendeln.setToolTip("Aufträge mit gleichem Material zusammenlegen: Liste mit gesparter Rüstzeit.")
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
        self.tafel.wirkung = self.zieh_wirkung
        self.tafel.gewaehlt.connect(self.tafel_gewaehlt)
        self.tafel.oeffnen.connect(lambda i: self.aendern(i))
        # Plantafel: Ansicht (V2), Farbe (V3), Legende
        self.tafel_rahmen = TafelRahmen(self.tafel)
        self.t_zoom = {}
        tz = QHBoxLayout()
        tz.setSpacing(4)
        t_titel = QLabel("<b>Plantafel</b> ⓘ")
        t_titel.setToolTip(TAFEL_HINWEIS)
        self.t_titel = t_titel
        tz.addWidget(t_titel)
        tz.addSpacing(8)
        for name, tage in TAFEL_ZOOM:
            k = KnappKnopf(name)
            k.setCheckable(True)
            k.clicked.connect(lambda _=False, name=name: self.tafel_zoom(name))
            tz.addWidget(k)
            self.t_zoom[name] = k
        k = KnappKnopf(MONAT_ZOOM)               # E2 (Plan 2.3): Monatsplan wie in der Excel-Plantafel
        k.setCheckable(True)
        k.setToolTip("Monatsplan wie in eurer Excel: Zeilen = Tage, Spalten = Maschinen, in jeder Zelle die Aufträge "
                     "des Tages mit Zeit, unten die Tagesauslastung. ◀ ▶ blättern nach Monat.")
        k.clicked.connect(lambda _=False: self.tafel_zoom(MONAT_ZOOM))
        tz.addWidget(k)
        self.t_zoom[MONAT_ZOOM] = k
        self.t_blaettern = []
        for zeichen, tipp, richtung in (("◀", "zurück (Tagesansicht: ein Tag, Monatsplan: ein Monat, sonst eine "
                                              "Woche)", -1),
                                        ("Heute", "zeigt heute", 0),
                                        ("▶", "weiter (Tagesansicht: ein Tag, Monatsplan: ein Monat, sonst eine "
                                              "Woche)", 1)):
            k = KnappKnopf(zeichen)
            k.setToolTip(tipp)
            k.clicked.connect(lambda _=False, r=richtung: self.tafel_blaettern(r))
            tz.addWidget(k)
            self.t_blaettern.append(k)
        self.monat_titel = QLabel("")
        self.monat_titel.setVisible(False)
        tz.addSpacing(6)
        tz.addWidget(self.monat_titel)
        self.t_suche = QLineEdit()
        self.t_suche.setPlaceholderText("Suchen: Auftrag oder Kunde")
        self.t_suche.setClearButtonEnabled(True)
        self.t_suche.setMinimumWidth(140)
        self.t_suche.setMaximumWidth(220)
        self.t_suche.setToolTip("Zeigt den Auftrag in der Plantafel und springt zu seinem Beginn. Eingabetaste: "
                                "nächster Treffer.")
        self.t_suche.textChanged.connect(lambda _t: self.tafel_suchen())
        self.t_suche.returnPressed.connect(lambda: self.tafel_suchen(weiter=True))
        self.k_vollbild = QPushButton("Vollbild")
        self.k_vollbild.setToolTip("Plantafel über den ganzen Bildschirm, z. B. für den Bildschirm in der Halle. "
                                   "Esc schließt.")
        self.k_vollbild.clicked.connect(lambda _=False: self.tafel_vollbild())
        tz.addStretch(1)
        tz2 = QHBoxLayout()                       # L3: zweite Zeile, damit bei 1366 Pixel nichts abgeschnitten ist
        tz2.setSpacing(4)
        tz2.addWidget(self.k_vollbild)
        tz2.addSpacing(8)
        tz2.addWidget(self.t_suche)               # E2: in die zweite Zeile, damit die erste für „Monat“ reicht
        tz2.addSpacing(12)
        tz2.addWidget(QLabel("Farbe nach"))
        self.t_farbe = QComboBox()
        self.t_farbe.addItems(TAFEL_FARBE)
        self.t_farbe.currentTextChanged.connect(self.tafel_farbe)
        tz2.addWidget(self.t_farbe)
        # N4: Text im Balken frei wählen (je Platz gemerkt)
        self.k_t_text = QPushButton("Text im Balken")
        self.k_t_text.setToolTip("Was in der zweiten Zeile der Balken steht. Gilt für diesen Platz.")
        text_menue = QMenu(self.k_t_text)
        self.a_t_text = {}
        for k, name in BALKEN_FELDER.items():
            act = text_menue.addAction(name)
            act.setCheckable(True)
            act.toggled.connect(lambda _an: self.tafel_text())
            self.a_t_text[k] = act
        self.k_t_text.setMenu(text_menue)
        tz2.addWidget(self.k_t_text)
        tz2.addSpacing(12)
        self.t_legende = QLabel("")
        self.t_legende.setTextFormat(Qt.RichText)
        self.t_legende.setWordWrap(True)
        tz2.addWidget(self.t_legende, 1)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.balken)
        ll.addSpacing(4)
        ll.addLayout(tz)
        ll.addLayout(tz2)
        ll.addWidget(self.tafel_rahmen)
        self.monat_erster = self.heute().replace(day=1)
        self.monat_tafel = MonatsTafel()
        self.monat_tafel.gewaehlt.connect(self.tafel_gewaehlt)
        self.monat_tafel.oeffnen.connect(lambda i: self.aendern(i))
        self.monat_tafel.setVisible(False)
        ll.addWidget(self.monat_tafel)
        self.t_ist = QLabel("")                   # V3: Tatsächliches von heute, nur in der Tagesansicht
        self.t_ist.setWordWrap(True)
        self.t_ist.setTextFormat(Qt.RichText)
        self.t_ist.hide()
        self.vollbild = None
        ll.addWidget(self.t_ist)
        ll.addStretch(1)
        ini = ort.ini_lesen(self.platz)
        self.t_farbe.setCurrentText(ini.get("tafel_farbe") if ini.get("tafel_farbe") in TAFEL_FARBE else TAFEL_FARBE[0])
        self.tafel_zoom(ini.get("tafel_zoom") if ini.get("tafel_zoom") in self.t_zoom else "2 Wochen", merken=False,
                        zeigen=False)
        self.tafel_farbe(self.t_farbe.currentText(), merken=False)
        felder = [k for k in str(ini.get("balken_text") or "").split(",") if k in BALKEN_FELDER]
        self.w_fuellt_text = True
        for k, act in self.a_t_text.items():
            act.setChecked(k in (felder if ini.get("balken_text") is not None else BALKEN_VORGABE))
        self.w_fuellt_text = False
        self.tafel_text(merken=False)
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
        self.rechts = rechts
        self.k_liste = QPushButton("Liste rechts")
        self.k_liste.setCheckable(True)
        self.k_liste.setToolTip("Blendet die Liste rechts (Terminrisiko, Aufträge der gewählten Woche) ein oder aus. "
                                "Ausgeblendet hat die Plantafel die volle Breite. Der Platz merkt sich die Wahl.")
        self.k_liste.toggled.connect(lambda an: self.liste_rechts(an))
        self.k_balken = QPushButton("Wochenbalken")
        self.k_balken.setCheckable(True)
        self.k_balken.setToolTip("Blendet die Wochenbalken ein oder aus. Ausgeblendet hat die Plantafel die ganze "
                                 "Höhe. Der Platz merkt sich die Wahl.")
        self.k_balken.toggled.connect(lambda an: self.balken_zeigen(an))
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 2)
        teiler.setSizes([800, 560])
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Zeitraum"))
        oben.addWidget(self.wochen)
        oben.addWidget(self.k_auskunft)
        oben.addWidget(self.k_kapazitaet)
        oben.addWidget(self.k_wenn)
        oben.addWidget(self.k_material)
        oben.addWidget(self.k_optimieren)
        oben.addWidget(self.k_rueck)
        oben.addStretch(1)
        oben.addWidget(self.k_balken)
        oben.addWidget(self.k_liste)
        oben.addWidget(self.k_arbeitsliste)
        oben.addWidget(self.k_pdf)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addWidget(self._kennzahl_zeile())
        lay.addWidget(self.info)
        lay.addWidget(self.zug_zeile)
        lay.addWidget(teiler, 1)
        ini = ort.ini_lesen(self.platz)
        for k, an in ((self.k_liste, ini.get("liste_rechts") != "0"), (self.k_balken, ini.get("wochenbalken") != "0")):
            k.blockSignals(True)                  # beim Start nur lesen, nicht in die Auslastung.ini schreiben
            k.setChecked(an)
            k.blockSignals(False)
        self.liste_rechts(self.k_liste.isChecked(), merken=False)
        self.balken_zeigen(self.k_balken.isChecked(), merken=False)
        self.info.setToolTip(RECHENWEG)
        return w

    # ------------------------------------------------------------------ Plan 3.0: Kennzahlen-Zeile
    def _kennzahl_zeile(self):
        """Plan 3.0 (Paket A): eine Zeile über der Plantafel mit Zeitraum, Gesamtauslastung, freien und geplanten
        Stunden, Aufträgen in Arbeit, offen, überfällig, mit kritischem Termin, Produktivität und je Maschine die
        Auslastung im Zeitraum (grün frei, gelb hoch, rot Überlast)."""
        zeile = QWidget()
        z = QHBoxLayout(zeile)
        z.setContentsMargins(0, 0, 0, 0)
        z.setSpacing(4)
        self.kzl_zeitraum = QComboBox()
        self.kzl_zeitraum.addItems(rechnung.ZEITRAEUME)
        self.kzl_zeitraum.setToolTip("Zeitraum für die Zahlen in dieser Zeile.")
        self.kzl_von, self.kzl_bis = QDateEdit(), QDateEdit()
        for feld in (self.kzl_von, self.kzl_bis):
            feld.setCalendarPopup(True)
            feld.setDisplayFormat("dd.MM.yy")
            feld.setDate(QDate(*self.heute().timetuple()[:3]))
            feld.setVisible(False)
            feld.dateChanged.connect(lambda _d: self.kennzahl_zeile_zeigen())
        ini = ort.ini_lesen(self.platz)
        if ini.get("kz_zeitraum") in rechnung.ZEITRAEUME[:-1]:
            self.kzl_zeitraum.setCurrentText(ini["kz_zeitraum"])
        else:
            self.kzl_zeitraum.setCurrentText(rechnung.ZEITRAEUME[1])
        self.kzl_zeitraum.currentTextChanged.connect(lambda t: self._kzl_zeitraum(t))
        z.addWidget(self.kzl_zeitraum)
        z.addWidget(self.kzl_von)
        z.addWidget(self.kzl_bis)
        z.addSpacing(4)
        self.kzl = {}
        for key, tipp, aktion in (
                ("auslastung", "Belegte Zeit (tatsächlich + geplant + Überlast) durch die verfügbare Zeit aller "
                               "Maschinen im Zeitraum.", None),
                ("frei", "Freie Maschinenstunden ab heute im Zeitraum.", None),
                ("geplant", "Eingelastete Stunden ab heute im Zeitraum.", None),
                ("arbeit", "Aufträge, die gerade laufen. Klick zeigt die offenen Aufträge.", "auftraege"),
                ("offen", "Offene Aufträge (noch nicht begonnen). Klick zeigt die offenen Aufträge.", "auftraege"),
                ("ueberfaellig", "Liefertermin vorbei, noch nicht fertig. Klick zeigt das Terminrisiko.", "risiko"),
                ("kritisch", "Nicht zu halten oder knapp. Klick zeigt das Terminrisiko.", "risiko"),
                ("produktiv", "Kalkulierte durch tatsächliche Laufzeit der letzten 90 Tage (100 % = wie kalkuliert, "
                              "darunter = länger gebraucht).", None)):
            k = Chip()
            k.setToolTip(tipp)
            k.setProperty("tipp", tipp)
            if aktion is not None:
                k.setCursor(Qt.PointingHandCursor)
            if aktion == "auftraege":
                k.clicked.connect(lambda _=False: self._kzl_auftraege())
            elif aktion == "risiko":
                k.clicked.connect(lambda _=False: self._kzl_risiko())
            z.addWidget(k)
            self.kzl[key] = k
        z.addSpacing(6)
        self.kzl_mzeile = QHBoxLayout()
        self.kzl_mzeile.setSpacing(3)
        z.addLayout(self.kzl_mzeile)
        z.addStretch(1)
        self.kzl_m_knoepfe = []
        self._kzl_zeitraum(self.kzl_zeitraum.currentText(), merken=False, zeigen=False)
        return zeile

    def _kzl_zeitraum(self, text, merken=True, zeigen=True):
        frei = text == rechnung.ZEITRAEUME[-1]
        self.kzl_von.setVisible(frei)
        self.kzl_bis.setVisible(frei)
        if merken and not frei:
            self._platz_merken("kz_zeitraum", text)
        if zeigen:
            self.kennzahl_zeile_zeigen()

    def _kzl_auftraege(self):
        self.reiter.setCurrentIndex(0)
        self.filter.setCurrentIndex(0)

    def _kzl_risiko(self):
        self.liste_rechts(True)
        self.woche_waehlen(None, None)

    def kennzahl_zahlen(self):
        """(Zahlen des Zeitraums, Zähler) für die Kennzahlen-Zeile."""
        heute = self.heute()
        von, bis = rechnung.zeitraum(self.kzl_zeitraum.currentText(), heute, self.kzl_von.date().toPython(),
                                     self.kzl_bis.date().toPython())
        zahl = rechnung.zahlen(self.db, self.aus, self.ein, von, bis, heute)
        offen = self.db.auftraege((D.OFFEN, D.LAEUFT))
        r = self.ein["risiko"]
        zaehler = dict(arbeit=sum(1 for a in offen if a["status"] == D.LAEUFT),
                       offen=sum(1 for a in offen if a["status"] == D.OFFEN),
                       ueberfaellig=sum(1 for a in offen if a["liefertermin"] and a["liefertermin"] < heute.isoformat()),
                       kritisch=r[einlastung.UEBER] + r[einlastung.KNAPP],
                       produktiv=rechnung.produktivitaet(self.db, heute))
        return zahl, zaehler

    def kennzahl_zeile_zeigen(self):
        if getattr(self, "ein", None) is None or not hasattr(self, "kzl"):
            return
        zahl, n = self.kennzahl_zahlen()
        g = zahl["gesamt"]
        farbe = {"ueber": stil.ROT_FLAECHE, "hoch": stil.GELB_FLAECHE, "frei": stil.GRUEN_FLAECHE, "aus": stil.FLAECHE}

        def chip(k, text, stufe=None, tipp=None):
            k.setText(text)
            k.setToolTip(tipp or k.property("tipp") or "")
            k.setStyleSheet(f"background: {stil.umsetzen(farbe[stufe])}; color: {stil.umsetzen(stil.TEXT)}; "
                            "border-radius: 3px; padding: 2px 6px;" if stufe else "padding: 2px 4px;")

        def proz(p):
            return "–" if p is None else f"{p:.0f} %"

        def h(x):
            return f"{x:.0f} h" if x >= 9.5 else f"{x:.1f} h".replace(".", ",")

        zeitraum = (f"{zahl['von']:%d.%m.}" if zahl["von"] == zahl["bis"]
                    else f"{zahl['von']:%d.%m.} bis {zahl['bis']:%d.%m.}")
        tipp = (f"{self.kzl['auslastung'].property('tipp')}\n{zeitraum}: verfügbar {h(g['verfuegbar'])}, tatsächlich "
                f"{h(g['ist'])}, geplant {h(g['geplant'])}, frei {h(g['frei'])}, Überlast {h(g['ueber'])}")
        chip(self.kzl["auslastung"], f"Auslastung {proz(g['prozent'])}", g["stufe"], tipp)
        chip(self.kzl["frei"], f"Frei {h(g['frei'])}")
        chip(self.kzl["geplant"], f"Geplant {h(g['geplant'])}")
        chip(self.kzl["arbeit"], f"In Arbeit {n['arbeit']}")
        chip(self.kzl["offen"], f"Offen {n['offen']}")
        chip(self.kzl["ueberfaellig"], f"Überfällig {n['ueberfaellig']}", "ueber" if n["ueberfaellig"] else None)
        chip(self.kzl["kritisch"], f"Kritisch {n['kritisch']}", "hoch" if n["kritisch"] else None)
        chip(self.kzl["produktiv"], f"Produktivität {proz(n['produktiv'])}")
        for k in self.kzl_m_knoepfe:
            self.kzl_mzeile.removeWidget(k)
            k.hide()                              # sonst bleibt es bis zum Löschen sichtbar über der Zeile
            k.setParent(None)
            k.deleteLater()
        self.kzl_m_knoepfe = []
        for z in zahl["maschinen"]:
            if z["verfuegbar"] <= 1e-9 and z["stufe"] == "aus":
                continue
            k = Chip()
            chip(k, f"{z['maschine']} {proz(z['prozent'])}", z["stufe"],
                 f"{z['maschine']}, {zeitraum}: verfügbar {h(z['verfuegbar'])}, tatsächlich {h(z['ist'])}, geplant "
                 f"{h(z['geplant'])}, frei {h(z['frei'])}, Überlast {h(z['ueber'])}")
            self.kzl_mzeile.addWidget(k)
            self.kzl_m_knoepfe.append(k)
        self.kzl_letzt = zahl

    def balken_zeigen(self, an, merken=True):
        """L1 (Plan 2.1): Wochenbalken ein- oder ausblenden; der Platz merkt es sich."""
        self.balken.setVisible(an)
        self.k_balken.setText("Wochenbalken ausblenden" if an else "Wochenbalken zeigen")
        if self.k_balken.isChecked() != an:
            self.k_balken.setChecked(an)
        if merken:
            self._platz_merken("wochenbalken", None if an else "0")

    def liste_rechts(self, an, merken=True):
        """L2 (Plan 2.1): Liste rechts ein- oder ausblenden; der Platz merkt es sich."""
        self.rechts.setVisible(an)
        self.k_liste.setText("Liste rechts ausblenden" if an else "Liste rechts zeigen")
        if self.k_liste.isChecked() != an:
            self.k_liste.setChecked(an)
        if merken:
            self._platz_merken("liste_rechts", None if an else "0")

    def tafel_zoom(self, name, merken=True, zeigen=True):
        """Ansicht der Plantafel (V2): so viele Tage sind sichtbar, der Rest wird gerollt; der Platz merkt es sich.
        „Monat“ (E2) zeigt statt der Plantafel den Monatsplan."""
        for n, k in self.t_zoom.items():
            k.setChecked(n == name)
        self.monat_an = name == MONAT_ZOOM
        self.tafel_rahmen.setVisible(not self.monat_an)
        self.monat_tafel.setVisible(self.monat_an)
        self.monat_titel.setVisible(self.monat_an)
        if self.monat_an:
            if zeigen and getattr(self, "ein", None):
                self.monat_zeigen()
                self.monat_zu_heute()
        else:
            self.tafel_rahmen.sichtbar(dict(TAFEL_ZOOM)[name])
        for k in self.t_blaettern:
            k.setEnabled(name != "Alles")
        self.tag_ist_zeigen()
        if merken:
            self._platz_merken("tafel_zoom", name)

    def tafel_blaettern(self, richtung):
        """◀ Heute ▶ über der Plantafel: richtung -1/1 blättert (Monatsplan: ein Monat), 0 zeigt heute."""
        if getattr(self, "monat_an", False):
            if richtung == 0:
                self.monat_erster = self.heute().replace(day=1)
            else:
                d = self.monat_erster + datetime.timedelta(days=32 if richtung > 0 else -1)
                self.monat_erster = d.replace(day=1)
            self.monat_zeigen()
            self.monat_zu_heute()
        elif richtung == 0:
            self.tafel_rahmen.zu_heute()
        else:
            self.tafel_rahmen.blaettern(richtung)

    def monat_daten(self, erster=None):
        """Monatsplan des Monats ab erster (Vorgabe: der gezeigte) als dict für MonatsTafel.setzen()."""
        erster = erster or self.monat_erster
        daten = rechnung.monat(self.ein, erster.year, erster.month)
        heute = self.heute()
        ist = {d: rechnung.tag_ist_text(rechnung.tag_ist(self.db, d)) for d in daten["tage"] if d < heute}
        termine = {a["id"]: _tag(a.get("termin")) for a in self.ein["auftraege"]}
        return daten, ist, termine

    def monat_zeigen(self):
        """E2: den Monatsplan des gezeigten Monats füllen. Ergebnis: die Daten (rechnung.monat)."""
        daten, ist, termine = self.monat_daten()
        self.monat_tafel.lz = self.lz
        self.monat_tafel.setzen(daten, self.heute(), ist, self.tafel.auswahl, termine)
        e = self.monat_erster
        self.monat_titel.setText(f"<b>{MONATE[e.month - 1]} {e.year}</b>")
        return daten

    def monat_zu_heute(self):
        """Im laufenden Monat bis zur Zeile von heute rollen (die vergangenen Tage stehen darüber), sonst nach oben.
        Ergebnis: die Höhe der Zeile von heute im Monatsplan (0 in anderen Monaten)."""
        t, heute = self.monat_tafel, self.heute()
        oben = 0
        if t.daten and heute in t.daten["tage"]:
            oben = t.KOPF + sum(t._tageshoehe(d) for d in t.daten["tage"] if d < heute)
        rollen = self.tafel_rahmen.aussen
        if rollen is not None:                    # erst nach dem Layout steht die Lage des Monatsplans fest
            QTimer.singleShot(0, t, lambda: rollen.verticalScrollBar().setValue(
                max(0, t.y() + oben - t.KOPF - 8) if oben else 0))
        return oben

    def monat_pdf(self, pfad=None, gross=False, erster=None):
        """Monatsplan als PDF (A4 quer, gross = A3 quer zum Aushängen), passend auf eine Seite verkleinert."""
        erster = erster or self.monat_erster
        name = f"{MONATE[erster.month - 1]} {erster.year}"
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Monatsplan als PDF",
                                                  f"Monatsplan-{erster:%Y-%m}{'-A3' if gross else ''}.pdf",
                                                  "PDF (*.pdf)")
            if not pfad:
                return None
        w, seite, p = _pdf_beginnen(pfad, f"Monatsplan {name}", gross)
        t = MonatsTafel()
        t.setFont(self.font())
        t.lz = self.lz
        daten, ist, termine = self.monat_daten(erster)
        t.setzen(daten, self.heute(), ist, None, termine)
        with stil.druckfarben():
            f = self.font()
            y = _pdf_titel(p, f, seite, f"Monatsplan {name}, Stand {self.heute().strftime('%d.%m.%Y')}")
            faktor = min(1.0, (seite.height() - y) / max(1, t.hoehe()))
            p.save()
            p.translate(0, y)
            p.scale(faktor, faktor)
            t.zeichnen(p, seite.width() / faktor)
            p.restore()
            p.end()
        del w
        return pfad

    def tag_ist_zeigen(self):
        """Unter der Tagesansicht: was heute tatsächlich läuft und fertig wurde (V3). Ergebnis: der Text."""
        text = ""
        if self.tafel.tag_an and not getattr(self, "monat_an", False) and getattr(self, "ein", None):
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
        v.tafel.felder_setzen(self.tafel.balken_felder)
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

    def tafel_text(self, felder=None, merken=True):
        """N4: Felder der zweiten Balkenzeile setzen (felder=None: aus dem Menü) und für diesen Platz merken."""
        if getattr(self, "w_fuellt_text", False):
            return
        if felder is not None:
            self.w_fuellt_text = True
            for k, act in self.a_t_text.items():
                act.setChecked(k in felder)
            self.w_fuellt_text = False
        gewaehlt = [k for k, act in self.a_t_text.items() if act.isChecked()]
        self.tafel.felder_setzen(gewaehlt)
        if self.vollbild is not None:
            self.vollbild.tafel.felder_setzen(gewaehlt)
        if merken:
            self._platz_merken("balken_text", ",".join(gewaehlt))

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
                stueck = D.Daten.fortschritt(teil, a)          # N2: Fortschritt nach Stück, sonst nach Zeit
                out[(a["id"], gang_id)] = dict(
                    laeuft=laeuft, gestoppt=bool(not laeuft and (gelaufen or grund)), grund=grund,
                    anteil=stueck if stueck is not None else
                    min(1.0, gelaufen / teil["kalk_min"]) if teil["kalk_min"] else 0.0, material=material,
                    gelaufen=gelaufen, kalk=int(teil["kalk_min"] or 0), bemerkung=a.get("bemerkung") or "",
                    stueck=(f"{int(teil['stueck_fertig'])}/{int(a['stueckzahl'])} Stück"
                            if teil.get("stueck_fertig") is not None and a.get("stueckzahl") else
                            f"{int(a['stueckzahl'])} Stück" if int(a.get("stueckzahl") or 0) > 1 else ""),
                    ueber=max(0, gelaufen - int(teil["kalk_min"] or 0)) if laeuft and teil["kalk_min"] else 0)
        return out

    def zieh_wirkung(self, auftrag_id, gang_id, maschine, tag):
        """Plan 3.1: Wirkung beim Ziehen in der Plantafel, ohne zu speichern: welche Termine kippen oder besser werden
        und wie sich die Auslastung der betroffenen Maschinen in der Woche ändert."""
        if not getattr(self, "ein", None):
            return ""
        probe = rechnung.probe_festlegen(self.aus, auftrag_id, gang_id, maschine, tag,
                                         int(self.db.zahl("schwelle_tage", 2)))
        if probe is None:
            return ""
        return self.wirkung_text(self.ein, probe, tag, {maschine} | {a["maschine"] for a in self.ein["auftraege"]
                                                                    if a["id"] == auftrag_id})

    def wirkung_text(self, vorher, nachher, tag, maschinen):
        diff = rechnung.vergleich(vorher, nachher)
        schlechter = [x["nummer"] for x in diff if x["schlechter"] > 0]
        besser = [x["nummer"] for x in diff if x["schlechter"] < 0]
        teile = []
        if schlechter:
            teile.append("Termin kippt: " + ", ".join(schlechter[:5]) + (" …" if len(schlechter) > 5 else ""))
        if besser:
            teile.append("besser: " + ", ".join(besser[:5]) + (" …" if len(besser) > 5 else ""))
        if not teile:
            teile.append("kein Termin ändert sich")
        mo = tag - datetime.timedelta(days=tag.weekday())
        heute = self.heute()
        vo = rechnung.zahlen(self.db, self.aus, vorher, max(mo, heute), mo + datetime.timedelta(days=6), heute)
        na = rechnung.zahlen(self.db, self.aus, nachher, max(mo, heute), mo + datetime.timedelta(days=6), heute)
        p_v = {x["maschine"]: x["prozent"] for x in vo["maschinen"]}
        p_n = {x["maschine"]: x["prozent"] for x in na["maschinen"]}
        for m in sorted(maschinen):
            if p_v.get(m) is not None and p_n.get(m) is not None and abs(p_v[m] - p_n[m]) >= 0.5:
                teile.append(f"{m} KW {mo.isocalendar()[1]}: {p_v[m]:.0f} % → {p_n[m]:.0f} %")
        return "; ".join(teile)

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
        try:                                      # Plan 3.1: Auslastung der Woche vorher → nachher
            last = [t for t in self.wirkung_text(vorher, self.ein, tag, {maschine} | {
                a["maschine"] for a in vorher["auftraege"] if a["id"] == auftrag_id}).split("; ") if " KW " in t]
        except Exception:
            last = []
        if last:
            text += " Auslastung: " + ", ".join(last) + "."
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
        if uebernehmen:
            self._vorschlag_speichern(vorschlag)
        return vorschlag

    def protokoll_zeigen(self, zeigen=True):
        """Plan 3.4: Protokoll (nur mit dem Recht Einstellungen)."""
        if not self.darf("einstellungen"):
            return None
        d = ProtokollDialog(self)
        if zeigen:
            d.exec()
        return d

    def buendeln(self, zeigen=True):
        """Plan 3.2: Liste „Bündeln“ öffnen. zeigen=False gibt den Dialog ungeöffnet zurück (Tests)."""
        if not getattr(self, "ein", None):
            return None
        d = BuendelDialog(self)
        if zeigen:
            d.exec()
        return d

    def _vorschlag_speichern(self, vorschlag):
        """Vorschlag (Optimieren oder Engpass-Empfehlung) speichern; „Optimierung rückgängig“ holt den Stand zurück."""
        ziel = vorschlag.get("ziel")
        if self.darf("auftraege"):
            self.rueck_opt = self.db.optimierung_uebernehmen(vorschlag["schritte"])
            self.rueck = None
            self.laden()
            v, n = vorschlag["vorher"], vorschlag["nachher"]
            mehr = (f", Rüsten {_stunden_text(vorschlag['ruest'][0])} → {_stunden_text(vorschlag['ruest'][1])}"
                    if ziel in (rechnung.ZIEL_RUESTEN, "buendel") else
                    f", {vorschlag['maschine']} in KW {vorschlag['montag'].isocalendar()[1]}: "
                    f"{vorschlag['prozent'][0]:.0f} % → {vorschlag['prozent'][1]:.0f} %" if ziel == "engpass" else "")
            self.zug_zeile.setText(f"{dict(engpass='Empfehlung', buendel='Bündel').get(ziel, 'Optimierung')} übernommen ({len(vorschlag['schritte'])} Änderungen): nicht zu halten "
                                   f"{v[0]} → {n[0]}, knapp {v[1]} → {n[1]}{mehr}.")
            self.zug_zeile.setVisible(True)
            self.k_rueck.setText("Optimierung rückgängig")
            self.k_rueck.setVisible(True)
            return True
        return False

    def engpass_oeffnen(self, w, uebernehmen=None):
        """Plan 3.1: Klick auf eine Engpass-Warnung. Mit Empfehlung: Vorschlag mit Vorher/Nachher zeigen, gespeichert
        wird erst mit „Übernehmen“ (uebernehmen True/False überspringt den Dialog, Tests). Ohne Empfehlung: die Woche
        in der Plantafel zeigen. Ergebnis: übernommen ja/nein."""
        if self.werkstatt_ist_an():
            self.werkstatt_an(False)
        self.reiter.setCurrentIndex(1)
        e, vorschlag = w["engpass"], w.get("vorschlag")
        self.tafel_zu_woche(e["montag"])
        if not e.get("gerechnet"):                # noch nicht ausgerechnet (Tempo): jetzt
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                vorschlag = rechnung.empfehlung(self.db, self.aus, self.ein, e, self.heute(),
                                                int(self.db.zahl("schwelle_tage", 2)))
            finally:
                QApplication.restoreOverrideCursor()
            e["gerechnet"], w["vorschlag"] = True, vorschlag
            w["text"] = rechnung.engpass_text(e, vorschlag)
        if vorschlag is None:
            self.zug_zeile.setText(html.escape(w["text"]))
            self.zug_zeile.setVisible(True)
            return False
        if uebernehmen is None:
            uebernehmen = OptimierenDialog(self, vorschlag).exec() == QDialog.Accepted
        return bool(uebernehmen) and self._vorschlag_speichern(vorschlag)

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
        if self.monat_an:
            self.monat_zeigen()
        if self.vollbild is not None and self.vollbild.isVisible():
            self._vollbild_fuellen()
        r = self.ein["risiko"]
        text = ""                                 # L4: der Rechenweg steht im Tooltip und in der Hilfe
        if r[einlastung.UEBER] or r[einlastung.KNAPP]:
            text = (f"<b style='color:{stil.umsetzen(stil.ROT)}'>Terminrisiko: {r[einlastung.UEBER]} nicht zu "
                    f"halten, {r[einlastung.KNAPP]} knapp.</b>")
        self.info.setText(text)
        self.info.setVisible(bool(text))
        self.kennzahl_zeile_zeigen()
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

    def kapazitaet_zeigen(self, zeigen=True):
        """N8: freie Kapazität für den Vertrieb."""
        d = KapazitaetDialog(self)
        if zeigen:
            d.exec()
        return d

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
        self.si_stopps_info = QLabel("")
        self.si_stopps_info.setWordWrap(True)
        self.si_stopps_info.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        for t in (self.si_maschinen, self.si_liste, self.si_stopps):
            t.verticalHeader().setVisible(False)
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.setAlternatingRowColors(True)
        self.si_liste.setSortingEnabled(True)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addWidget(self.si_info)
        links, self.si_rechts = QVBoxLayout(), QWidget()     # L5: Unterbrechungen nur, wenn es welche gibt
        rechts = QVBoxLayout(self.si_rechts)
        rechts.setContentsMargins(0, 0, 0, 0)
        links.addWidget(QLabel("<b>Je Maschine</b>"))
        links.addWidget(self.si_maschinen)
        links.addStretch(1)
        rechts.addWidget(QLabel("<b>Unterbrechungen nach Grund</b>"))
        rechts.addWidget(self.si_stopps)
        beide = QHBoxLayout()
        beide.addLayout(links, 1)
        beide.addWidget(self.si_rechts, 1)
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
        self.kz_excel = QPushButton("Excel …")
        self.kz_excel.setToolTip("Kennzahlen, Auswertung je Tag/Woche/Monat, Maschinenvergleich, Soll und Ist und die "
                                 "zu späten Aufträge als Excel-Datei (.xlsx) speichern.")
        self.kz_excel.clicked.connect(lambda _=False: self.kennzahlen_excel())
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Fertig gemeldet"))
        oben.addWidget(self.kz_zeitraum)
        oben.addStretch(1)
        oben.addWidget(self.kz_excel)
        self.kz_kacheln = {}
        kacheln = QHBoxLayout()
        for key, titel in (("treue", "Termintreue der fertigen Aufträge"), ("spaet", "Zu spät: überfällig oder laut Plan"),
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
        rechts.addWidget(QLabel("<b>Zu späte Aufträge</b> (überfällig oder laut Plan; Doppelklick zeigt den Auftrag)"))
        rechts.addWidget(self.kz_spaet, 1)
        unten = QHBoxLayout()
        unten.addLayout(links, 2)
        unten.addLayout(rechts, 3)
        # Plan 3.3: Auswertung je Tag/Woche/Monat und Maschinenvergleich
        self.kz_raster = QComboBox()
        for key, name in rechnung.RASTER:
            self.kz_raster.addItem(name, key)
        self.kz_raster.setCurrentIndex(1)
        self.kz_raster.currentIndexChanged.connect(lambda _i: self.auswertung_zeigen())
        self.kz_vergleich, self.kz_perioden = QTableWidget(), QTableWidget()
        for t in (self.kz_vergleich, self.kz_perioden):
            t.verticalHeader().setVisible(False)
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
            t.setAlternatingRowColors(True)
        self.kz_aw_info = QLabel("")
        self.kz_aw_info.setWordWrap(True)
        self.kz_aw_info.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        aw = QWidget()
        aw_lay = QVBoxLayout(aw)
        aw_oben = QHBoxLayout()
        aw_oben.addWidget(QLabel("<b>Maschinenvergleich</b> im gewählten Zeitraum"))
        aw_oben.addStretch(1)
        aw_oben.addWidget(QLabel("Einteilung"))
        aw_oben.addWidget(self.kz_raster)
        aw_lay.addLayout(aw_oben)
        aw_lay.addWidget(self.kz_vergleich, 2)
        aw_lay.addWidget(QLabel("<b>Je Tag, Woche oder Monat</b>"))
        aw_lay.addWidget(self.kz_perioden, 3)
        aw_lay.addWidget(self.kz_aw_info)
        ueber = QWidget()
        ueber.setLayout(unten)
        self.kz_unten = QTabWidget()
        self.kz_unten.addTab(ueber, "Übersicht")
        self.kz_unten.addTab(aw, "Auswertung und Maschinenvergleich")
        self.kz_unten.currentChanged.connect(lambda i: self.auswertung_zeigen() if i == 1 else None)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addLayout(kacheln)
        self.kz_balken_text = QLabel("<b>Termintreue je Monat</b> (Balken), darunter die Abweichung der Kalkulation")
        lay.addWidget(self.kz_balken_text)
        lay.addWidget(self.kz_balken)
        lay.addWidget(self.kz_unten, 1)
        self.kz_unten.currentChanged.connect(lambda i: [x.setVisible(i == 0) for x in (self.kz_balken,
                                                                                      self.kz_balken_text)])
        return w

    AW_KOPF = ("Maschine", "Kapazität [h]", "Produktion [h]", "Auslastung", "Rüsten [h]", "Stillstand [h]",
               "Stopps", "Produktivität", "Fertig", "Termintreue", "Durchlauf [Tage]")

    def auswertung_grenzen(self):
        """Zeitraum der Auswertung: der Zeitraum oben; bei „alle“ ab der ersten Fertigmeldung (höchstens ein Jahr)."""
        von, bis = self.zeitraum_grenzen(self.kz_zeitraum.currentIndex())
        h = self.heute()
        if von is None:
            erste = [rechnung._datum(x["fertig_am"]) for x in rechnung._meldungen(self.db)]
            erste = [t for t in erste if t]
            von = max(min(erste), h - datetime.timedelta(days=365)) if erste else h - datetime.timedelta(days=30)
        return von, min(bis or h, h)

    def auswertung_daten(self):
        von, bis = self.auswertung_grenzen()
        return rechnung.auswertung(self.db, self.aus, von, bis, self.kz_raster.currentData())

    @staticmethod
    def _aw_werte(z):
        def p(w):
            return None if w is None else round(w)

        def h(w):
            return round(w, 1)
        return (z["maschine"], h(z["kap_h"]), h(z["produktion_h"]), p(z["auslastung"]),
                h(z["ruest_h"]) if z["ruest_n"] else None, h(z["stillstand_h"]), z["stopps"], p(z["produktivitaet"]),
                z["fertig"], p(z["treue"]), None if z["durchlauf"] is None else round(z["durchlauf"], 1))

    def auswertung_zeigen(self):
        if not getattr(self, "aus", None):
            return None
        a = self.aw = self.auswertung_daten()

        def text(w, c):
            if w is None:
                return ""
            if c in (3, 7, 9):
                return f"{w} %"
            return f"{w}".replace(".", ",") if isinstance(w, float) else str(w)

        def fuellen(t, kopf, zeilen):
            t.setColumnCount(len(kopf))
            t.setHorizontalHeaderLabels(kopf)
            t.setRowCount(len(zeilen))
            for r, werte in enumerate(zeilen):
                for c, w in enumerate(werte):
                    z = _zelle(text(w, c - (len(kopf) - len(self.AW_KOPF))), c >= len(kopf) - len(self.AW_KOPF) + 1)
                    t.setItem(r, c, z)
            t.resizeColumnsToContents()
        fuellen(self.kz_vergleich, self.AW_KOPF, [self._aw_werte(z) for z in a["maschinen"] + [a["gesamt"]]])
        if a["maschinen"]:
            r = self.kz_vergleich.rowCount() - 1
            for c in range(self.kz_vergleich.columnCount()):
                z = self.kz_vergleich.item(r, c)
                f = z.font()
                f.setBold(True)
                z.setFont(f)
        name = dict(rechnung.RASTER)[a["raster"]]
        fuellen(self.kz_perioden, (name,) + self.AW_KOPF,
                [(z["periode"],) + self._aw_werte(z) for z in a["zeilen"]
                 if z["produktion_h"] or z["stopps"] or z["fertig"]])
        self.kz_aw_info.setText(
            f"{_wtag(a['von'])} bis {_wtag(a['bis'])}. Produktion = tatsächliche Laufzeit der Fertigmeldungen, "
            "Auslastung = Produktion durch Kapazität, Rüsten = bei der Fertigmeldung angegebene Rüstzeit (leer = nicht "
            "gemeldet), Stillstand = Stopps mit Weiterlaufen am selben Tag, Produktivität = kalkuliert durch "
            "tatsächlich, Durchlauf = Kalendertage von angelegt bis fertig.")
        return a

    def materialbedarf_zeigen(self, zeigen=True):
        """V7: Materialbedarf je Woche."""
        d = MaterialbedarfDialog(self)
        if zeigen:
            d.exec()
        return d

    def kennzahlen_excel(self, pfad=None):
        """Plan 3.3: Kennzahlen als .xlsx (Auswertung, Maschinenvergleich, Soll und Ist, zu spät)."""
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Kennzahlen als Excel", f"Kennzahlen-{self.heute():%Y-%m-%d}.xlsx",
                                                  "Excel (*.xlsx)")
            if not pfad:
                return None
        from . import xlsx
        a = self.auswertung_daten()
        name = dict(rechnung.RASTER)[a["raster"]]
        von, bis = self.zeitraum_grenzen(self.kz_zeitraum.currentIndex())
        si = rechnung.soll_ist(self.db, von, bis)
        k = self.kennzahlen_daten()
        blaetter = [
            ("Maschinenvergleich", self.AW_KOPF, [self._aw_werte(z) for z in a["maschinen"] + [a["gesamt"]]]),
            (f"Je {name}", ("Beginn", name) + self.AW_KOPF,
             [(z["beginn"], z["periode"]) + self._aw_werte(z) for z in a["zeilen"]]),
            ("Soll und Ist", ("Auftragsnummer", "Kunde", "Maschine", "Fertig am", "Liefertermin", "Kalkuliert [min]",
                              "Tatsächlich [min]", "davon Rüsten [min]", "Abweichung [min]", "Abweichung [%]"),
             [(x["nummer"], x["kunde"], x["maschine"], rechnung._datum(x["fertig_am"]),
               rechnung._datum(x["liefertermin"]), x["kalk_min"], x["ist_min"], x.get("ruest_ist"), x["diff_min"],
               None if x["diff_prozent"] is None else round(x["diff_prozent"], 1)) for x in si["zeilen"]]),
            ("Zu spät", ("Auftragsnummer", "Kunde", "Maschine", "Liefertermin", "Fertig (Plan)", "Art", "Tage"),
             [(v["nummer"], v["kunde"], v["maschine"], v["termin"], v["fertig_plan"], v["art"], v["tage"])
              for v in k["verspaetet"]]),
            ("Unterbrechungen", ("Grund", "Anzahl", "Minuten", "davon gemessen"),
             [(z["grund"] or "ohne Grund", z["anzahl"], z["minuten"], z["gemessen"])
              for z in rechnung.unterbrechungen(self.db, von, bis)]),
        ]
        try:
            xlsx.schreiben(pfad, blaetter)
        except OSError as e:
            QMessageBox.warning(self, "Excel", f"Die Datei ließ sich nicht schreiben:\n{e}")
            return None
        self.statusBar().showMessage(f"Kennzahlen gespeichert: {pfad}", 8000)
        return pfad

    def kennzahlen_daten(self):
        return rechnung.kennzahlen(self.db, self.ein, self.gem, self.heute(),
                                   *self.zeitraum_grenzen(self.kz_zeitraum.currentIndex()))

    def kennzahlen_zeigen(self):
        k = self.kz = self.kennzahlen_daten()
        if self.kz_unten.currentIndex() == 1:
            self.auswertung_zeigen()

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
        self.si_rechts.setVisible(bool(z3))
        for t in (self.si_maschinen, self.si_stopps):     # L5: Tabellen nur so hoch wie ihr Inhalt
            t.setFixedHeight(min(250, t.horizontalHeader().sizeHint().height() + 4
                                 + sum(t.rowHeight(r) for r in range(t.rowCount()))))
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
        self.e_maschinen.setColumnCount(11)
        self.e_maschinen.setHorizontalHeaderLabels(("Maschine", "Stunden je Tag", "aktiv", "Sperrtage",
                                                    "Übergangszeit davor", "Ausweichmaschine", "Rüstzeit",
                                                    "Größtes Rohr", "Typ, Bezeichnung", "Leistung",
                                                    "Arbeitstage"))
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
        self.k_protokoll = QPushButton("Protokoll …")
        self.k_protokoll.setToolTip("Wer hat wann Maschinen, Wartungen, Bediener, Schichten, Benutzer oder "
                                    "Einstellungen geändert (alt → neu). Nur für Admins.")
        self.k_protokoll.clicked.connect(lambda _=False: self.protokoll_zeigen())
        self.k_db.clicked.connect(lambda _=False: self.datenbank_waehlen())
        self.k_sichern.clicked.connect(lambda _=False: self.jetzt_sichern())
        g5 = QGroupBox("Datenbank")
        l5 = QVBoxLayout(g5)
        l5.addWidget(self.e_pfad)
        z = QHBoxLayout()
        z.addWidget(self.k_db)
        z.addWidget(self.k_sichern)
        z.addWidget(self.k_protokoll)
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
        # N2 (Plan 2.2): eine feste Excel-Liste wird automatisch abgeglichen
        self.e_abgleich = QLineEdit()
        self.e_abgleich.setPlaceholderText("keine Datei: kein automatischer Abgleich")
        self.e_abgleich.setClearButtonEnabled(True)
        self.e_abgleich.editingFinished.connect(self.einstellungen_speichern)
        self.k_abgleich = QPushButton("Datei wählen …")
        self.k_abgleich.clicked.connect(lambda _=False: self.abgleich_datei_waehlen())
        abgleich_text = QLabel(
            "Eure Auftragsliste in Excel (oder CSV), z. B. im gemeinsamen Ordner. Sobald sie gespeichert ist, "
            "übernimmt das Programm neue und geänderte Aufträge ohne Rückfrage (Prüfung jede Minute, Sicherung "
            "der Datenbank vorher). Was in der Datei fehlt, bleibt im Programm. Die Statuszeile unten zeigt den "
            "letzten Abgleich.")
        abgleich_text.setWordWrap(True)
        abgleich_text.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        g10 = QGroupBox("Abgleich mit eurer Excel-Liste")
        l10 = QVBoxLayout(g10)
        z10 = QHBoxLayout()
        z10.addWidget(self.e_abgleich, 1)
        z10.addWidget(self.k_abgleich)
        l10.addLayout(z10)
        l10.addWidget(abgleich_text)
        # E5 (Plan 2.3): Seite Funktionen – Zusatzfunktionen ein- und ausschalten, Daten bleiben
        g11 = QGroupBox("Funktionen")
        l11 = QVBoxLayout(g11)
        self.e_funktionen = {}
        for name, titel, text in FUNKTIONEN:
            k = QCheckBox(titel)
            k.setToolTip(text)
            k.toggled.connect(lambda an, name=name: self.funktion_schalten(name, an))
            self.e_funktionen[name] = k
            l11.addWidget(k)
            erkl = QLabel(text)
            erkl.setWordWrap(True)
            erkl.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)}; margin-left: 22px;")
            l11.addWidget(erkl)
        f_text = QLabel("Ausgeschaltet verschwinden Felder und Knöpfe; schon eingetragene Werte bleiben gespeichert "
                        "und sind beim Einschalten wieder da. Gilt für alle Plätze.")
        f_text.setWordWrap(True)
        f_text.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        l11.addWidget(f_text)
        g12 = self._zusatz_gruppe()
        g13 = self._warn_gruppe()
        g14, g15 = self._wartung_gruppe(), self._personen_gruppe()
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
        # L7 (Plan 2.1): Unterreiter statt einer langen Seite
        self.e_reiter = QTabWidget()
        for titel, gruppen in EINSTELLUNG_REITER:
            innen = QWidget()
            lay = QVBoxLayout(innen)
            for g in gruppen({1: g1, "s": g_s, 2: g2, 3: g3, 4: g4, 5: g5, 6: g6, 7: g7, 8: g8, 9: g9, 10: g10,
                              11: g11, 12: g12, 13: g13, 14: g14, 15: g15}):
                lay.addWidget(g)
            lay.addStretch(1)
            rollen = QScrollArea()
            rollen.setWidgetResizable(True)
            rollen.setFrameShape(QFrame.NoFrame)
            rollen.setWidget(innen)
            self.e_reiter.addTab(rollen, titel)
        aussen = QVBoxLayout(w)
        aussen.addWidget(hinweis)
        aussen.addWidget(self.e_reiter, 1)
        return w

    def funktion_schalten(self, name, an):
        """E5 (Plan 2.3): Häkchen auf der Seite Funktionen; gilt sofort für alle Plätze."""
        if self.e_fuellt:
            return
        if name == "arbeitsgaenge":
            self.e_gaenge.setChecked(an)          # derselbe Schalter wie bei den Arbeitsgängen
            return
        if name == "zusatzschritte":              # Plan 2.6: Arbeitsgänge mit an, Arbeitsplätze anlegen
            neu = self.db.zusatz_einschalten(an)
            self.laden()
            self.einstellungen_zeigen()
            self.hinweis("Zusatzschritte " + ("eingeschaltet" if an else "ausgeschaltet") + "." + (
                f" Neu angelegt (8 Stunden je Tag, bitte prüfen): {', '.join(neu)}." if neu else "")
                + (" Richtzeiten: Einstellungen → Termine und Abläufe → Zusatzschritte." if an else ""))
            return
        self.db.funktion_setzen(name, an)
        self.laden()
        self.einstellungen_zeigen()
        self.hinweis(f"„{dict((n, t) for n, t, _x in FUNKTIONEN)[name]}“ {'eingeschaltet' if an else 'ausgeschaltet'}.")

    # ---------------------------------------------------------------- Plan 2.6: Richtzeiten der Zusatzschritte
    def _zusatz_gruppe(self):
        g = QGroupBox("Zusatzschritte: Richtzeiten")
        self.g_zusatz = g
        lay = QVBoxLayout(g)
        text = QLabel(
            "Laufzeit eines Zusatzschritts = Rüsten + Stückzahl × (Handling je Teil + Anzahl × Zeit je Stück). "
            "Mehrere Arten in einem Schritt (z. B. 4 × M8 und 2 × M12) werden addiert, Rüsten und Handling zählen "
            "einmal. Die Startwerte sind Schätzwerte; ändert ihr eine Zeit, gilt sie als eure. Arbeitsplatz "
            "„Fremdarbeit“ zählt nur die Arbeitstage. Stichwörter gelten für die Schnelleingabe und Excel "
            "(„4xM8“, „2xNiete“, „verzinken“).")
        text.setWordWrap(True)
        text.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        lay.addWidget(text)
        self.e_richt = QTableWidget()
        self.e_richt.setColumnCount(len(RICHT_KOPF))
        self.e_richt.setHorizontalHeaderLabels(RICHT_KOPF)
        self.e_richt.verticalHeader().setVisible(False)
        self.e_richt.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.e_richt.setSelectionMode(QAbstractItemView.SingleSelection)
        self.e_richt.setMinimumHeight(260)
        self.e_richt.itemChanged.connect(self._richtzeit_geaendert)
        self.e_richt_liste = []
        lay.addWidget(self.e_richt)
        z = QHBoxLayout()
        self.k_r_neu = QPushButton("Zeile hinzufügen")
        self.k_r_weg = QPushButton("Zeile entfernen")
        self.k_r_neu.clicked.connect(lambda _=False: self.richtzeit_neu())
        self.k_r_weg.clicked.connect(lambda _=False: self.richtzeit_entfernen())
        z.addWidget(self.k_r_neu)
        z.addWidget(self.k_r_weg)
        z.addStretch(1)
        lay.addLayout(z)
        zt = QHBoxLayout()
        zt.addWidget(QLabel("Fremdarbeit abholen und anliefern am:"))
        self.e_fremd_tage = []
        for i, t in enumerate(D.Z.WOCHENTAGE):
            k = QCheckBox(t)
            k.toggled.connect(lambda _an: self.fremd_tage_speichern())
            self.e_fremd_tage.append(k)
            zt.addWidget(k)
        zt.addStretch(1)
        lay.addLayout(zt)
        ft = QLabel("Ohne Häkchen: an jedem Arbeitstag. Der Arbeitsgang davor muss am Tag vorher fertig sein; "
                    "zurück kommt die Ware am nächsten solchen Tag nach den Arbeitstagen.")
        ft.setWordWrap(True)
        ft.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        lay.addWidget(ft)
        self.e_vorschlaege = QWidget()
        self.e_vorschlaege_lay = QVBoxLayout(self.e_vorschlaege)
        self.e_vorschlaege_lay.setContentsMargins(0, 6, 0, 0)
        lay.addWidget(self.e_vorschlaege)
        return g

    def _zusatz_fuellen(self):
        an = self.db.funktion("zusatzschritte")
        self.g_zusatz.setVisible(an)
        if not an:
            return
        self.e_richt_liste = self.db.richtzeiten()
        self.e_richt.blockSignals(True)
        self.e_richt.setRowCount(len(self.e_richt_liste))
        for r, x in enumerate(self.e_richt_liste):
            werte = (x["schritt"], x["art"], f"{x['je_s']:g}".replace(".", ","),
                     f"{x['ruest_min']:g}".replace(".", ","), f"{x['handling_s']:g}".replace(".", ","),
                     x["platz"] or D.FREMD_TEXT, str(x["tage"] or "") if not x["platz"] else "", x["stichwort"],
                     "ja" if x["geschaetzt"] else "")
            for c, t in enumerate(werte):
                item = QTableWidgetItem(t)
                if c == 8:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setToolTip("ja = Startwert des Programms, noch nicht an euren Zeiten geprüft")
                if 2 <= c <= 4 or c == 6:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.e_richt.setItem(r, c, item)
        self.e_richt.resizeColumnsToContents()
        self.e_richt.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)   # Stichwörter
        self.e_richt.blockSignals(False)
        erlaubt = self.db.fremd_tage()
        for i, k in enumerate(self.e_fremd_tage):
            k.setChecked(i in erlaubt)
        while self.e_vorschlaege_lay.count():
            w = self.e_vorschlaege_lay.takeAt(0)
            if w.widget():
                w.widget().hide()
                w.widget().deleteLater()
            elif w.layout():
                while w.layout().count():
                    x = w.layout().takeAt(0).widget()
                    if x is not None:
                        x.hide()
                        x.deleteLater()
        self.e_vorschlag_knoepfe = []
        vorschlaege = self.db.zusatz_vorschlaege()
        if vorschlaege:
            kopf = QLabel("<b>Aus euren Fertigmeldungen gelernt</b> (Vorschlag, wird erst mit ✓ übernommen):")
            self.e_vorschlaege_lay.addWidget(kopf)
        for v in vorschlaege:
            z = QHBoxLayout()
            z.addWidget(QLabel(D.Z.vorschlag_text(v)), 1)
            k = QPushButton("✓ Übernehmen")
            k.clicked.connect(lambda _=False, v=v: self.richtzeit_vorschlag_uebernehmen(v))
            self.e_vorschlag_knoepfe.append(k)
            z.addWidget(k)
            self.e_vorschlaege_lay.addLayout(z)

    def _richtzeit_geaendert(self, item):
        """Jede Änderung in der Tabelle gilt sofort; bei Fehler steht wieder der alte Wert da."""
        if self.e_fuellt or not (0 <= item.row() < len(self.e_richt_liste)):
            return
        alt = self.e_richt_liste[item.row()]
        neu = {f: self.e_richt.item(item.row(), c).text() for c, f in enumerate(RICHT_FELD)}
        for f in ("je_s", "ruest_min", "handling_s", "tage"):
            neu[f] = neu[f].strip() or "0"
        try:
            self.db.richtzeit_speichern(neu, alt["id"])
        except D.Fehler as e:
            self.hinweis(str(e))
        QTimer.singleShot(0, self, self.einstellungen_zeigen)

    def richtzeit_neu(self):
        namen = {(x["schritt"], x["art"]) for x in self.db.richtzeiten()}
        art, n = "neu", 2
        while ("Bearbeitung", art) in namen:
            art, n = f"neu {n}", n + 1
        self.db.richtzeit_speichern(dict(schritt="Bearbeitung", art=art, je_s=30, ruest_min=10, handling_s=20,
                                         platz=D.Z.BEARBEITUNG), None)
        self.einstellungen_zeigen()
        self.e_richt.selectRow(self.e_richt.rowCount() - 1)
        self.hinweis("Neue Zeile angelegt: bitte Namen, Art und Zeiten eintragen.")

    def richtzeit_entfernen(self, zeile=None, fragen=True):
        r = self.e_richt.currentRow() if zeile is None else zeile
        if not (0 <= r < len(self.e_richt_liste)):
            return False
        x = self.e_richt_liste[r]
        name = f"{x['schritt']} {x['art']}".strip()
        if fragen and QMessageBox.question(self, NAME, f"„{name}“ aus den Richtzeiten entfernen? Schon eingeplante "
                                           "Aufträge behalten ihre Zeit.") != QMessageBox.Yes:
            return False
        self.db.richtzeit_loeschen(x["id"])
        self.einstellungen_zeigen()
        return True

    def fremd_tage_speichern(self):
        if self.e_fuellt:
            return
        self.db.einstellung_setzen("fremd_tage", ",".join(str(i) for i, k in enumerate(self.e_fremd_tage)
                                                          if k.isChecked()))
        self.laden()

    def richtzeit_vorschlag_uebernehmen(self, v):
        """Z3/F4a: ein gelernter Wert wird erst mit ✓ zur Richtzeit (dann kein Schätzwert mehr)."""
        x = next((r for r in self.db.richtzeiten() if r["id"] == v["id"]), None)
        if x is None:
            return False
        self.db.richtzeit_speichern(dict(x, je_s=v["gemessen_s"], geschaetzt=0), x["id"])
        self.einstellungen_zeigen()
        self.hinweis(f"Übernommen: {D.Z.vorschlag_text(v)}. Neue Aufträge rechnen damit.")
        return True

    def einstellungen_zeigen(self):
        self.e_fuellt = True
        try:
            self._einstellungen_fuellen()
        finally:
            self.e_fuellt = False

    def _einstellungen_fuellen(self):
        for name, k in self.e_funktionen.items():
            k.setChecked(self.db.mit_gaengen() if name == "arbeitsgaenge" else self.db.funktion(name))
        self._zusatz_fuellen()
        self._warn_fuellen()
        self._wartung_bediener_fuellen()
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
            self.e_maschinen.setItem(r, 8, _zelle(", ".join(x for x in (m.get("typ"), m.get("bezeichnung")) if x)))
            leistung = float(m.get("leistung") or 100)
            self.e_maschinen.setItem(r, 9, _zelle("Erfahrungswert" if m.get("erfahrung") else
                                                  "" if abs(leistung - 100) < 1e-9 else f"{leistung:.0f} %"))
            self.e_maschinen.setItem(r, 10, _zelle(" ".join(("Mo", "Di", "Mi", "Do", "Fr", "Sa")[int(t)]
                                                            for t in m["arbeitstage"].split(","))
                                                   if m.get("arbeitstage") else ""))
        gaenge_an = self.db.mit_gaengen()
        self.e_maschinen.setColumnHidden(4, not gaenge_an)
        mat = self.db.funktion("material")
        for c in (6, 7):                          # L7: Rüstzeit und größtes Rohr nur, wenn eine Maschine sie hat
            self.e_maschinen.setColumnHidden(c, not mat or not any(self.e_maschinen.item(r, c).text()
                                                                   for r in range(len(ms))))
        for c in (8, 9, 10):                      # Plan 3.0: nur, wenn eine Maschine etwas eingetragen hat
            self.e_maschinen.setColumnHidden(c, not any(self.e_maschinen.item(r, c).text() for r in range(len(ms))))
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
        self.e_abgleich.setText(self.db.einstellung("abgleich_datei") or "")
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
                     ("abgleich_datei", self.e_abgleich.text().strip()),
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

    def abgleich_datei_waehlen(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "Excel-Liste für den automatischen Abgleich",
                                                  self.e_abgleich.text(),
                                                  "Excel oder CSV (*.xlsx *.xlsm *.csv *.txt);;Alle (*)")
            if not pfad:
                return
        self.e_abgleich.setText(str(pfad))
        self.einstellungen_speichern()
        self.abgleichen()

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
        Beginn des Wechsels[, Samstagsschichten[, Rüstzeit in Minuten[, größter Durchmesser[, größte Rohrlänge[,
        Erfahrungswert[, Bezeichnung[, Typ[, Leistung in Prozent[, Arbeitstage (0 = Montag bis 5 = Samstag)]]]]]]]]]]]]]])
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
            bez = QLineEdit(m.get("bezeichnung") or "" if m else "")    # Plan 3.0: Maschinenverwaltung
            bez.setPlaceholderText("z. B. Rohrlaser 2, Halle 3")
            typ = QLineEdit(m.get("typ") or "" if m else "")
            typ.setPlaceholderText("z. B. LT7, LT8.20, Fiber 3 kW")
            form.addRow("Bezeichnung", bez)
            form.addRow("Maschinentyp", typ)
            form.addRow("Stunden je Tag (Montag bis Freitag)", stunden)
            hat_tage = ({int(t) for t in (m.get("arbeitstage") or "").split(",") if t.strip()} if m else set()) \
                or set(range(6))
            z_tage, tag_k = QHBoxLayout(), []
            for i, t in enumerate(("Mo", "Di", "Mi", "Do", "Fr", "Sa")):
                k = QCheckBox(t)
                k.setChecked(i in hat_tage)
                z_tage.addWidget(k)
                tag_k.append(k)
            z_tage.addStretch(1)
            tag_k[5].setToolTip("Samstag zählt mit den Samstagsstunden (Arbeitszeit und Termine → Samstag) oder den "
                                "Samstagsschichten der Maschine.")
            form.addRow("Arbeitstage", z_tage)
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
            if not self.db.funktion("material"):  # M1 (Plan 2.3): Werte bleiben, nur unsichtbar
                form.setRowVisible(ruest, False)
                form.setRowVisible(z_rohr, False)
            # N3 (Plan 2.2): Erfahrungswert aus Soll und Ist
            erf = QCheckBox("Mit Erfahrungswert planen")
            erf.setChecked(bool(m.get("erfahrung")) if m else False)
            wert = rechnung.erfahrung(self.db, self.heute(), alle=True).get(m["name"]) if m else None
            erf_text = QLabel(
                f"Aufträge liefen hier zuletzt {abs(wert[0] - 1) * 100:.0f} % {'länger' if wert[0] >= 1 else 'kürzer'} "
                f"als kalkuliert ({wert[1]} fertige Aufträge im letzten Jahr). Eingeschaltet plant das Programm "
                "die kalkulierte Zeit um so viel länger bzw. kürzer." if wert else
                f"Braucht mindestens {rechnung.ERFAHRUNG_MIN} fertige Aufträge auf dieser Maschine im letzten Jahr; "
                "bis dahin plant das Programm mit der kalkulierten Zeit.")
            erf_text.setWordWrap(True)
            erf_text.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
            form.addRow("Erfahrungswert", erf)
            form.addRow("", erf_text)
            leist = QSpinBox()                    # Plan 3.0: Produktivitätsfaktor von Hand
            leist.setRange(10, 300)
            leist.setSuffix(" %")
            leist.setValue(int(round(float(m.get("leistung") or 100))) if m else 100)
            leist.setToolTip("Wie schnell diese Maschine gegenüber der Kalkulation arbeitet: 100 % = wie kalkuliert, "
                             "80 % = braucht ein Viertel länger, 120 % = schneller. Gilt, solange „Mit "
                             "Erfahrungswert planen“ aus ist.")
            z_leist = QHBoxLayout()
            z_leist.addWidget(leist)
            vorschlag = rechnung.leistung_vorschlag(self.db, self.heute()).get(m["name"]) if m else None
            if vorschlag:
                k_vor = QPushButton(f"Erfahrungswert {vorschlag[0]} % übernehmen")
                k_vor.setToolTip(f"Aus {vorschlag[1]} fertigen Aufträgen des letzten Jahres.")
                k_vor.clicked.connect(lambda _=False, v=vorschlag[0]: leist.setValue(v))
                z_leist.addWidget(k_vor)
            z_leist.addStretch(1)
            form.addRow("Leistung", z_leist)
            erf.toggled.connect(lambda an: leist.setEnabled(not an))
            leist.setEnabled(not erf.isChecked())
            if m and self.db.funktion("wartung"):
                ws = [w for w in self.db.wartungen() if w["maschine"] == m["name"]]
                w_text = QLabel(("Wartungen: " + "; ".join(w["name"] for w in ws[:4]) + (" …" if len(ws) > 4 else "")
                                 if ws else "Keine Wartung eingetragen.")
                                + " Ändern unter Einstellungen → Wartung und Bediener.")
                w_text.setWordWrap(True)
                w_text.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
                form.addRow("Wartung", w_text)
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
                     ruest.value(), max_d.value(), max_l.value(), erf.isChecked(), bez.text(), typ.text(),
                     leist.value(), [i for i, k in enumerate(tag_k) if k.isChecked()])
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
                                       max_laenge=werte[11] if len(werte) > 11 else None,
                                       erfahrung=werte[12] if len(werte) > 12 else None,
                                       bezeichnung=werte[13] if len(werte) > 13 else None,
                                       typ=werte[14] if len(werte) > 14 else None,
                                       leistung=werte[15] if len(werte) > 15 else None,
                                       arbeitstage=werte[16] if len(werte) > 16 else None)
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
        self.k_lizenz = QPushButton("Lizenz …")
        self.k_lizenz.setToolTip("Zustand der Lizenz, Rechner-ID kopieren, Lizenzdatei laden. Die Lizenz der "
                                 "Kalkulation gilt hier mit.")
        self.k_lizenz.clicked.connect(lambda _=False: self.lizenz_zeigen())
        self.k_lizenz.setVisible(self.lizenz is not None)
        zeile.addWidget(self.update_stand)
        zeile.addStretch(1)
        zeile.addWidget(self.k_lizenz)
        zeile.addWidget(self.k_update)
        lay.addLayout(zeile)
        lay.addWidget(self.hilfe, 1)
        return seite

    # ------------------------------------------------------------------ alles
    def funktionen_anwenden(self):
        """E5 (Plan 2.3): ausgeschaltete Funktionen aus Knöpfen, Menüs und Legende nehmen."""
        self.k_werkstatt.setVisible(self.db.funktion("werkstatt"))
        self.a_ziele[rechnung.ZIEL_RUESTEN].setVisible(self.db.funktion("material"))
        self.a_buendeln.setVisible(self.db.funktion("material"))
        self.k_material.setVisible(self.db.funktion("material"))
        hinweis = TAFEL_HINWEIS
        if not self.db.funktion("material_ab"):
            hinweis = hinweis.replace(" · schraffiert = wartet auf Material", "")
        self.t_titel.setToolTip(hinweis)
        self.schnell.setPlaceholderText("Schnell anlegen: A-2701 LT7 3:30 25.11. Kunde" + (
            " 50 Stk 4xM8 verzinken" if austausch.zusatz_an(self.db) else "") + ", dann Enter")

    def laden(self):
        """Neu rechnen und den sichtbaren Reiter füllen."""
        self.funktionen_anwenden()
        self.aus, self.ein = rechnung.einlasten(self.db, self.heute(), self.wochen.value())
        self.gem = rechnung.gemessen(self.db, self.aus, self.heute())
        if self.woche and self.woche[0] not in self.ein["maschinen"]:
            self.woche = None
        self.rechte_setzen()
        self.warnungen_zeigen()
        self.rueckmeldung_pruefen()
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
