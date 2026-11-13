"""Seite „Produktion“ (Plan Auftragsworkflow 13.11.2026, Paket 4). Regeln in auftrag_produktion.py.

Alle aktiven Arbeitsgänge der Aufträge ab „Produktionsbereit“: oben Reiter je Status mit Anzahl und die Auswahl des
Arbeitsplatzes (Maschine oder Arbeitsgang), das Such-/Scanfeld (Auftragsnummer, Artikel, Kunde), darunter große
Knöpfe für die Rückmeldung am gewählten Arbeitsgang: Beginnen, Unterbrechen, Fortsetzen, Teilmenge …, Abschließen …,
Problem melden …, Problem gelöst, Ausschuss / Nacharbeit …. Unten die Rückmeldungen des Arbeitsgangs (mit Storno).
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QPushButton, QSplitter, QStyledItemDelegate,
                               QTabBar, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import auftraege as au, auftrag_produktion as pr, leerhinweis

SPALTEN = ("Auftrag", "Pos.", "Artikel", "Arbeitsgang", "Arbeitsplatz", "Mitarbeiter", "Status", "Fortschritt",
           "Gut / Soll", "Ausschuss", "Soll [min]", "Ist [min]", "Start geplant", "Liefertermin", "Kunde")
VERLAUF_SPALTEN = ("Zeit", "Benutzer", "Rückmeldung", "Menge", "Ausschuss", "Minuten", "Bemerkung")
FILTER = (pr.NICHT_FERTIG,) + pr.AG_STATUS + ("Alle",)
FARBE = {pr.LAEUFT: "#E8F0FB", pr.GESTOERT: "#FDECEA", pr.PAUSE: "#FFF6DB", pr.FERTIG: "#E3F4E8"}


def _zahl(x):
    try:
        return f"{float(x):g}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def _datum(iso):
    t = str(iso or "")
    return f"{t[8:10]}.{t[5:7]}.{t[:4]}{t[10:16].replace('T', ' ')}" if len(t) >= 10 else t


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


ANTEIL = Qt.UserRole + 7


class BalkenDelegate(QStyledItemDelegate):
    """Fortschrittsbalken in einer Tabellenzelle (Anteil 0–1 in ANTEIL), gemalt statt eigenem Widget."""

    def paint(self, maler, option, index):
        super().paint(maler, option, index)
        wert = index.data(ANTEIL)
        if wert is None:
            return
        r = QRectF(option.rect).adjusted(4, 5, -4, -5)
        maler.save()
        maler.setRenderHint(maler.RenderHint.Antialiasing)
        maler.setPen(Qt.NoPen)
        maler.setBrush(QColor("#E3E8EF"))
        maler.drawRoundedRect(r, 3, 3)
        if wert > 0:
            maler.setBrush(QColor("#9FD8B0" if wert >= 1 else "#A9C8EC"))
            maler.drawRoundedRect(QRectF(r.x(), r.y(), max(4.0, r.width() * min(1.0, wert)), r.height()), 3, 3)
        maler.setPen(QColor("#1B2633"))
        maler.drawText(r, Qt.AlignCenter, f"{wert * 100:.0f} %")
        maler.restore()


def balken(t, r, c, wert):
    """Zelle (r, c) als Fortschrittsbalken; Spalte bekommt einmal den Delegate."""
    if not isinstance(t.itemDelegateForColumn(c), BalkenDelegate):
        t.setItemDelegateForColumn(c, BalkenDelegate(t))
        t.horizontalHeader().setSectionResizeMode(c, QHeaderView.Fixed)
        t.setColumnWidth(c, 120)
    it = QTableWidgetItem("")
    it.setData(ANTEIL, float(wert or 0))
    it.setToolTip(f"{(wert or 0) * 100:.0f} %")
    t.setItem(r, c, it)
    return it


class MengeDialog(QDialog):
    """Menge, Ausschuss, Minuten und Bemerkung für Teilmenge, Abschluss, Ausschuss/Nacharbeit."""

    def __init__(self, eltern, titel, z, mit_art=False):
        super().__init__(eltern)
        self.setWindowTitle(titel)
        form = QFormLayout(self)
        form.addRow(QLabel(f"<b>{z['nummer']} Pos. {z['pos']} {z['artikel']}</b> · {z['name']} · gut "
                           f"{_zahl(z['gut'])} von {_zahl(z['soll'])}"))
        self.art = QComboBox()
        self.art.addItems(["Ausschuss", "Nacharbeit erforderlich"])
        if mit_art:
            form.addRow("Art", self.art)
        self.menge = QLineEdit()
        self.menge.setPlaceholderText("Stück")
        rest = max(0.0, z["soll"] - z["gut"])
        if not mit_art and rest:
            self.menge.setText(_zahl(rest))
        self.ausschuss = QLineEdit()
        self.ausschuss.setPlaceholderText("Stück")
        self.minuten = QLineEdit()
        self.minuten.setPlaceholderText("leer = aus Beginnen/Unterbrechen")
        self.bemerkung = QLineEdit()
        form.addRow("Menge" if mit_art else "Gute Menge", self.menge)
        if not mit_art:
            form.addRow("Ausschuss", self.ausschuss)
            form.addRow("Minuten", self.minuten)
        form.addRow("Bemerkung", self.bemerkung)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Melden")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def werte(self):
        return dict(menge=self.menge.text().replace(",", ".") or 0,
                    ausschuss=self.ausschuss.text().replace(",", ".") or 0,
                    minuten=self.minuten.text().replace(",", ".") or None, bemerkung=self.bemerkung.text(),
                    art=pr.NACHARBEIT if self.art.currentIndex() == 1 else pr.AUSSCHUSS)


class ProduktionSeite(QWidget):
    titel = "Produktion"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.alle, self.zeilen = [], []
        self.leiste = QTabBar()
        self.leiste.setExpanding(False)
        self.leiste.setDrawBase(False)
        self.leiste.setUsesScrollButtons(True)
        for x in FILTER:
            self.leiste.addTab(x)
        self.leiste.currentChanged.connect(self.neu_laden)
        self.platz = QComboBox()
        self.platz.setToolTip("Arbeitsplatz: Maschine, sonst der Arbeitsgang")
        self.platz.addItem("Alle Arbeitsplätze", "")
        self.platz.currentIndexChanged.connect(self.neu_laden)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen oder scannen: Auftrag, Artikel, Kunde, Arbeitsgang, Mitarbeiter …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.neu_laden)
        oben = QHBoxLayout()
        oben.addWidget(self.suche, 1)
        oben.addWidget(self.platz)
        knoepfe = QHBoxLayout()
        self.knopf = {}
        for name, text, ziel, tip in (
                ("beginnen", "▶ Beginnen", lambda: self.melden(pr.BEGONNEN), "Arbeitsgang beginnen (Ist-Start)"),
                ("unterbrechen", "⏸ Unterbrechen", lambda: self.melden(pr.UNTERBROCHEN), "Pause, Schichtende"),
                ("fortsetzen", "⏵ Fortsetzen", lambda: self.melden(pr.FORTGESETZT), "Weiterarbeiten"),
                ("teilmenge", "Teilmenge …", lambda: self.mit_menge(pr.TEILMENGE), "Fertige Teilmenge melden"),
                ("abschliessen", "✓ Abschließen …", lambda: self.mit_menge(pr.ABGESCHLOSSEN),
                 "Arbeitsgang fertig (Restmenge, Ausschuss, Minuten)"),
                ("problem", "⚠ Problem melden …", self.problem,
                 "Maschinenstillstand, Material fehlt, Zeichnungsproblem …"),
                ("geloest", "Problem gelöst", lambda: self.melden(pr.GELOEST), "Problem erledigt, weiter wie vorher"),
                ("ausschuss", "Ausschuss / Nacharbeit …", lambda: self.mit_menge(pr.AUSSCHUSS),
                 "Ausschuss oder Nacharbeit melden")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setMinimumHeight(40)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            if name in ("beginnen", "abschliessen"):
                b.setObjectName("primaer")
            self.knopf[name] = b
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        self.tabelle = _tabelle(SPALTEN)
        self.tabelle.itemSelectionChanged.connect(self.detail_zeigen)
        self.tabelle.doubleClicked.connect(lambda _: self.auftrag_zeigen())
        leerhinweis.setzen(self.tabelle, "Keine Arbeitsgänge für diese Auswahl. Hier erscheinen Aufträge, sobald sie "
                                         "in der Arbeitsvorbereitung produktionsbereit gemeldet sind.")
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.RichText)
        self.verlauf = _tabelle(VERLAUF_SPALTEN)
        self.storno_knopf = QPushButton("Rückmeldung stornieren …")
        self.storno_knopf.setToolTip("Eine falsche Rückmeldung unwirksam machen (mit Grund, bleibt in der Historie)")
        self.storno_knopf.clicked.connect(lambda: self.stornieren())
        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addWidget(self.detail)
        ul.addWidget(self.verlauf, 1)
        sl = QHBoxLayout()
        sl.addWidget(self.storno_knopf)
        sl.addStretch(1)
        ul.addLayout(sl)
        teiler = QSplitter(Qt.Vertical)
        teiler.addWidget(self.tabelle)
        teiler.addWidget(unten)
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 1)
        self.info = QLabel()
        lay = QVBoxLayout(self)
        lay.addWidget(self.leiste)
        lay.addLayout(oben)
        lay.addLayout(knoepfe)
        lay.addWidget(teiler, 1)
        lay.addWidget(self.info)
        self.neu_laden()

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_veraltet", False):
            self.neu_laden()

    # ------------------------------------------------ Liste
    def status_filter(self):
        i = self.leiste.currentIndex()
        return FILTER[i] if 0 <= i < len(FILTER) else pr.NICHT_FERTIG

    def filter_setzen(self, status=pr.NICHT_FERTIG, platz=None, suche=None):
        if platz is not None:
            self.platz.blockSignals(True)
            self.platz.setCurrentIndex(max(0, self.platz.findData(platz)))
            self.platz.blockSignals(False)
        if suche is not None:
            self.suche.blockSignals(True)
            self.suche.setText(suche)
            self.suche.blockSignals(False)
        self.leiste.blockSignals(True)
        self.leiste.setCurrentIndex(FILTER.index(status) if status in FILTER else 0)
        self.leiste.blockSignals(False)
        self.neu_laden()

    def neu_laden(self, *_):
        if not self.f.stumm and not self.isVisible():
            self._veraltet = True
            return
        self._veraltet = False
        gewaehlt = self.gewaehlt()
        self.alle = pr.zeilen(self.db)
        plaetze = sorted({pr.arbeitsplatz(z) for z in self.alle})
        if plaetze != [self.platz.itemData(i) for i in range(1, self.platz.count())]:
            alt = self.platz.currentData()
            self.platz.blockSignals(True)
            while self.platz.count() > 1:
                self.platz.removeItem(1)
            for x in plaetze:
                self.platz.addItem(x, x)
            self.platz.setCurrentIndex(max(0, self.platz.findData(alt)))
            self.platz.blockSignals(False)
        basis = pr.filtern(self.alle, self.platz.currentData() or "", "Alle", self.suche.text())
        for i, f in enumerate(FILTER):
            self.leiste.setTabText(i, f"{f} ({len(pr.filtern(basis, '', f))})")
        self.zeilen = pr.filtern(basis, "", self.status_filter())
        self.tabelle.blockSignals(True)
        self.tabelle.setRowCount(len(self.zeilen))
        for r, z in enumerate(self.zeilen):
            werte = (z["nummer"], z["pos"], z["artikel"], z["name"], pr.arbeitsplatz(z), z["mitarbeiter"],
                     z["status"] + (f": {z['problem']}" if z["problem"] else ""), None,
                     f"{_zahl(z['gut'])} / {_zahl(z['soll'])}", _zahl(z["ausschuss"]) if z["ausschuss"] else "",
                     _zahl(round(z["sollzeit"], 1)), _zahl(z["istzeit"]) if z["istzeit"] else "", _datum(z["start"]),
                     _datum(z["liefertermin"]), z["kunde"])
            for c, w in enumerate(werte):
                if c == 7:
                    balken(self.tabelle, r, c, z["fortschritt"])
                    continue
                it = QTableWidgetItem("" if w is None else str(w))
                if c in (1, 8, 9, 10, 11):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if z["status"] in FARBE:
                    it.setBackground(QColor(FARBE[z["status"]]))
                self.tabelle.setItem(r, c, it)
        self.tabelle.blockSignals(False)
        r = next((r for r, z in enumerate(self.zeilen) if (z["auftrag"], z["ag"]) == gewaehlt),
                 0 if self.zeilen else -1)
        if r >= 0:
            self.tabelle.selectRow(r)
        self.detail_zeigen()
        laeuft = sum(1 for z in self.alle if z["status"] == pr.LAEUFT)
        stoer = sum(1 for z in self.alle if z["status"] == pr.GESTOERT)
        self.info.setText(f"{len(self.zeilen)} Arbeitsgänge gezeigt · {laeuft} in Bearbeitung"
                          + (f" · {stoer} mit Problem" if stoer else ""))

    def gewaehlt(self):
        z = self.zeile()
        return (z["auftrag"], z["ag"]) if z else None

    def zeile(self):
        r = self.tabelle.currentRow() if hasattr(self, "tabelle") else -1
        return self.zeilen[r] if 0 <= r < len(self.zeilen) else None

    def waehlen(self, nummer, name=None, pos=None):
        for r, z in enumerate(self.zeilen):
            if z["nummer"] == nummer and (name is None or z["name"] == name) and (pos is None or z["pos"] == pos):
                self.tabelle.selectRow(r)
                return True
        return False

    def detail_zeigen(self):
        z = self.zeile()
        for b in self.knopf.values():
            b.setEnabled(z is not None)
        self.storno_knopf.setEnabled(z is not None)
        if z is None:
            self.detail.setText("")
            self.verlauf.setRowCount(0)
            return
        st = z["status"]
        self.knopf["beginnen"].setEnabled(st in (pr.OFFEN, pr.EINGEPLANT, pr.FERTIG))
        self.knopf["unterbrechen"].setEnabled(st == pr.LAEUFT)
        self.knopf["fortsetzen"].setEnabled(st in (pr.PAUSE, pr.GESTOERT))
        self.knopf["geloest"].setEnabled(st == pr.GESTOERT)
        self.detail.setText(
            f"<b>{z['nummer']} · Pos. {z['pos']} {z['artikel']} {z['bezeichnung']}</b> · {z['name']} · {st}<br>"
            f"Gut {_zahl(z['gut'])} von {_zahl(z['soll'])}"
            + (f" · Ausschuss {_zahl(z['ausschuss'])}" if z["ausschuss"] else "")
            + (f" · Nacharbeit {_zahl(z['nacharbeit'])}" if z["nacharbeit"] else "")
            + f" · Soll {_zahl(round(z['sollzeit'], 1))} min · Ist {_zahl(z['istzeit'])} min"
            + (f" · begonnen {_datum(z['ist_start'])}" if z["ist_start"] else "")
            + (f" · fertig {_datum(z['ist_ende'])}" if z["ist_ende"] else ""))
        a = au.auftrag(self.db, z["auftrag"])
        p = next(x for x in a["positionen"] if x["uid"] == z["position"])
        rm = pr.verlauf(p, z["ag"])
        self._rm = rm
        self.verlauf.setRowCount(len(rm))
        for r, x in enumerate(rm):
            d = x.get("daten") or {}
            werte = (_datum(x["am"]), " ".join(v for v in (x.get("wer"), f"({x['name']})" if x.get("name") else "")
                                               if v),
                     pr.TYP_TEXT.get(x["typ"], x["typ"]) + (f": {d['grund']}" if d.get("grund") else "")
                     + (" (storniert)" if x["storniert"] else ""),
                     _zahl(d.get("menge")), _zahl(d.get("ausschuss")), _zahl(d.get("minuten")), x.get("bemerkung"))
            for c, w in enumerate(werte):
                it = QTableWidgetItem("" if w is None else str(w))
                if x["storniert"] or x["typ"] == pr.STORNO:
                    it.setForeground(QColor("#8A94A3"))
                self.verlauf.setItem(r, c, it)

    # ------------------------------------------------ Rückmelden
    def melden(self, typ, **werte):
        z = self.zeile()
        if z is None:
            return False
        try:
            r = pr.rueckmelden(self.db, z["auftrag"], z["position"], z["ag"], typ, **werte)
        except au.AuftragFehler as e:
            self.f.meldung(str(e), fehler=True)
            return False
        if r:
            self.f.meldung(f"{z['nummer']} Pos. {z['pos']} {z['name']}: {pr.TYP_TEXT[typ]}.")
        self.neu_laden()
        if hasattr(self.f, "auftraege"):
            self.f.auftraege.neu_laden()
        return r

    def mit_menge(self, typ, werte=None):
        z = self.zeile()
        if z is None:
            return False
        if werte is None:
            titel = {pr.TEILMENGE: "Teilmenge melden", pr.ABGESCHLOSSEN: "Arbeitsgang abschließen",
                     pr.AUSSCHUSS: "Ausschuss / Nacharbeit"}[typ]
            d = MengeDialog(self, titel, z, mit_art=typ == pr.AUSSCHUSS)
            if d.exec() != QDialog.Accepted:
                return False
            werte = d.werte()
        werte = dict(werte)
        art = werte.pop("art", None)
        if typ == pr.AUSSCHUSS and art:
            typ = art
        return self.melden(typ, **werte)

    def problem(self, grund=None, bemerkung=None):
        if self.zeile() is None:
            return False
        if grund is None:
            grund, ok = QInputDialog.getItem(self, "Problem melden", "Was ist los?", list(pr.GRUENDE), 0, False)
            if not ok:
                return False
            bemerkung, ok = QInputDialog.getText(self, "Problem melden", "Beschreibung:")
            if not ok:
                return False
        return self.melden(pr.PROBLEM, grund=grund, bemerkung=bemerkung or "")

    def stornieren(self, zeile=None, grund=None):
        z = self.zeile()
        rm = [x for x in getattr(self, "_rm", []) if not x["storniert"] and x["typ"] != pr.STORNO]
        if z is None or not rm:
            return False
        if zeile is None:
            namen = [f"{_datum(x['am'])} {pr.TYP_TEXT.get(x['typ'])} {_zahl((x.get('daten') or {}).get('menge'))}"
                     for x in rm]
            wahl, ok = QInputDialog.getItem(self, "Rückmeldung stornieren", "Welche Rückmeldung?", namen, 0, False)
            if not ok:
                return False
            zeile = namen.index(wahl)
            grund, ok = QInputDialog.getText(self, "Rückmeldung stornieren", "Grund (steht in der Historie):")
            if not ok:
                return False
        return self.melden(pr.STORNO, bezug=rm[zeile]["uid"], bemerkung=grund or "")

    def auftrag_zeigen(self):
        z = self.zeile()
        if z is not None and hasattr(self.f, "auftrag_zeigen"):
            self.f.auftrag_zeigen(z["auftrag"])
