"""Reiter „Qualität“ und „Auslieferung“ der Seite Aufträge (Plan Auftragsworkflow, Paket 5). Regeln in auftrag_qs.py.

Qualität: oben die Bedingungen für „Fertiggestellt“ (Produktion, Qualitätskontrolle) und die Knöpfe Prüfung erfassen,
Sonderfreigabe, Messprotokoll, Foto/Dokument, Storno und Fertig melden; darunter je Position der Prüfstand und der
Verlauf der Prüfungen der gewählten Position.
Auslieferung: je Position i.O. geprüft, geliefert, offen und lieferbar; Lieferung erfassen (Versand, Abholung,
eigene Lieferung, mit Lieferschein des Angebots), Storno, Dokumente und Abschluss des Auftrags.
"""
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import stil
from . import auftraege as au, auftrag_qs as qs

QS_SPALTEN = ("Pos.", "Artikel", "Menge", "Produktion", "Geprüft", "Gut", "Ausschuss", "Nacharbeit", "QS-Stand",
              "Prüfer", "Datum")
VERLAUF_SPALTEN = ("Datum", "Prüfer", "Geprüft", "Gut", "Ausschuss", "Nacharbeit", "Ergebnis", "Dokumente",
                   "Bemerkung")
LIEF_SPALTEN = ("Pos.", "Artikel", "Menge", "i.O. freigegeben", "Geliefert", "Offen", "Lieferbar")
LIEFERUNG_SPALTEN = ("Datum", "Art", "Mengen", "Lieferscheine", "Verpackung", "Paletten", "Erfasst", "Bemerkung")
DOK_SPALTEN = ("Bereich", "Datei", "Abgelegt", "Von")


def _zahl(x):
    try:
        return f"{float(x):g}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def _datum(iso):
    s = str(iso or "")[:10]
    return f"{s[8:10]}.{s[5:7]}.{s[:4]}" if len(s) == 10 else s


def _tabelle(spalten, dehnen=1):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    kopf = t.horizontalHeader()
    kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
    kopf.setSectionResizeMode(dehnen, QHeaderView.Stretch)
    return t


def _zelle(t, r, c, text, rechts=False, farbe=None, daten=None, durch=False):
    it = QTableWidgetItem(str(text))
    if rechts:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if farbe:
        it.setForeground(stil.farbe(farbe))
    if daten is not None:
        it.setData(Qt.UserRole, daten)
    if durch:
        f = it.font()
        f.setStrikeOut(True)
        it.setFont(f)
        it.setForeground(stil.farbe("#8A8A8A"))
    t.setItem(r, c, it)


def _knoepfe(eltern, liste):
    lay, knopf = QHBoxLayout(), {}
    for name, text, ziel, tip in liste:
        b = QPushButton(text)
        b.setToolTip(tip)
        b.clicked.connect(lambda _=False, ziel=ziel: ziel())
        if name in ("pruefen", "liefern"):
            b.setObjectName("primaer")
        knopf[name] = b
        lay.addWidget(b)
    lay.addStretch(1)
    return lay, knopf


class _Dateien(QWidget):
    """Knopf „Dateien …“ mit der Liste der gewählten Dateien (Fotos, Berichte)."""

    def __init__(self, titel):
        super().__init__()
        self.dateien = []
        self.titel = titel
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        b = QPushButton("Dateien …")
        b.clicked.connect(self.waehlen)
        self.text = QLabel("keine")
        self.text.setWordWrap(True)
        lay.addWidget(b)
        lay.addWidget(self.text, 1)

    def waehlen(self):
        d, _ = QFileDialog.getOpenFileNames(self, self.titel, "", "Fotos und Dokumente (*.jpg *.jpeg *.png *.heic "
                                            "*.pdf *.xlsx *.docx *.msg *.txt);;Alle Dateien (*)")
        if d:
            self.dateien = d
            self.text.setText(", ".join(Path(x).name for x in d))


def _knopfleiste(dialog, ok_text):
    k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    k.button(QDialogButtonBox.Ok).setText(ok_text)
    k.button(QDialogButtonBox.Cancel).setText("Abbrechen")
    k.accepted.connect(dialog.accept)
    k.rejected.connect(dialog.reject)
    return k


class PruefDialog(QDialog):
    """Prüfung einer Position: geprüft, gut, Ausschuss, Nacharbeit, Ergebnis, Prüfer, Datum, Dateien, Bemerkung."""

    def __init__(self, eltern, p, st, pruefer=""):
        super().__init__(eltern)
        self.setWindowTitle("Prüfung erfassen")
        form = QFormLayout(self)
        form.addRow(QLabel(f"<b>Pos. {p['nr']} {p.get('artikel') or ''}</b> · Menge {_zahl(st['menge'])} · i.O. "
                           f"bisher {_zahl(st['gut'])} · offen {_zahl(st['offen'])}"))
        self.geprueft, self.gut, self.ausschuss, self.nacharbeit = (QLineEdit() for _ in range(4))
        self.geprueft.setText(_zahl(st["offen"]))
        self.gut.setText(_zahl(st["offen"]))
        for w in (self.ausschuss, self.nacharbeit):
            w.setPlaceholderText("0")
        self.ergebnis = QComboBox()
        self.ergebnis.addItem("automatisch aus den Mengen", "")
        for e in (qs.IO, qs.TEIL_IO, qs.NIO):
            self.ergebnis.addItem(e, e)
        self.pruefer = QLineEdit(pruefer)
        self.datum = QDateEdit(QDate.currentDate())
        self.datum.setCalendarPopup(True)
        self.datum.setDisplayFormat("dd.MM.yyyy")
        self.dateien = _Dateien("Fotos / Prüfberichte")
        self.bemerkung = QLineEdit()
        self.bemerkung.setPlaceholderText("z. B. Grat an Ende B, Maß 1250 +0,8")
        form.addRow("Geprüft [Stück]", self.geprueft)
        form.addRow("Gut (i.O.)", self.gut)
        form.addRow("Ausschuss", self.ausschuss)
        form.addRow("Nacharbeit", self.nacharbeit)
        form.addRow("Ergebnis", self.ergebnis)
        form.addRow("Prüfer", self.pruefer)
        form.addRow("Datum", self.datum)
        form.addRow("Fotos / Dokumente", self.dateien)
        form.addRow("Bemerkung", self.bemerkung)
        form.addRow(_knopfleiste(self, "Speichern"))

    def werte(self):
        z = lambda w: w.text().replace(",", ".") or 0      # noqa: E731
        return dict(geprueft=z(self.geprueft), gut=z(self.gut), ausschuss=z(self.ausschuss),
                    nacharbeit=z(self.nacharbeit), ergebnis=self.ergebnis.currentData() or None,
                    pruefer=self.pruefer.text(), datum=self.datum.date().toString("yyyy-MM-dd"),
                    dokumente_=list(self.dateien.dateien), bemerkung=self.bemerkung.text())


class LieferDialog(QDialog):
    """Lieferung: Art, Datum, Menge je Position (Vorgabe: lieferbar), Verpackung, Paletten, Lieferschein, Dateien."""

    def __init__(self, eltern, stand):
        super().__init__(eltern)
        self.setWindowTitle("Lieferung erfassen")
        self.stand = [z for z in stand if z["offen"] > 0 or z["menge"] <= 0]
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.art = QComboBox()
        self.art.addItems(list(qs.LIEFERARTEN))
        self.datum = QDateEdit(QDate.currentDate())
        self.datum.setCalendarPopup(True)
        self.datum.setDisplayFormat("dd.MM.yyyy")
        form.addRow("Art", self.art)
        form.addRow("Datum (Versand / Abholung / Lieferung)", self.datum)
        lay.addLayout(form)
        self.tabelle = QTableWidget(len(self.stand), 5)
        self.tabelle.setHorizontalHeaderLabels(("Pos.", "Artikel", "Offen", "Lieferbar (i.O.)", "Menge jetzt"))
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for r, z in enumerate(self.stand):
            for c, (t, rechts) in enumerate(((z["nr"], False), (z["artikel"], False), (_zahl(z["offen"]), True),
                                             (_zahl(z["lieferbar"]), True))):
                it = QTableWidgetItem(str(t))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if rechts:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(r, c, it)
            it = QTableWidgetItem(_zahl(z["lieferbar"]) if z["lieferbar"] else "")
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabelle.setItem(r, 4, it)
        lay.addWidget(self.tabelle, 1)
        form2 = QFormLayout()
        self.verpackung = QLineEdit()
        self.verpackung.setPlaceholderText("z. B. Gitterbox, Europalette, Karton")
        self.paletten = QLineEdit()
        self.paletten.setPlaceholderText("0")
        self.lieferschein = QCheckBox("Lieferschein zum Angebot anlegen")
        self.lieferschein.setChecked(True)
        self.grund = QLineEdit()
        self.grund.setPlaceholderText("nur nötig, wenn mehr als i.O. geprüft geliefert wird")
        self.dateien = _Dateien("Lieferpapiere / Fotos")
        self.bemerkung = QLineEdit()
        form2.addRow("Verpackung", self.verpackung)
        form2.addRow("Paletten", self.paletten)
        form2.addRow("", self.lieferschein)
        form2.addRow("Grund (mehr als geprüft)", self.grund)
        form2.addRow("Dokumente", self.dateien)
        form2.addRow("Bemerkung", self.bemerkung)
        lay.addLayout(form2)
        lay.addWidget(_knopfleiste(self, "Lieferung speichern"))
        self.resize(640, 480)

    def werte(self):
        mengen = {}
        for r, z in enumerate(self.stand):
            t = (self.tabelle.item(r, 4).text() if self.tabelle.item(r, 4) else "").replace(",", ".").strip()
            if t:
                mengen[z["uid"]] = t
        return dict(mengen=mengen, art=self.art.currentText(), datum=self.datum.date().toString("yyyy-MM-dd"),
                    verpackung=self.verpackung.text(), paletten=self.paletten.text() or 0,
                    lieferschein=self.lieferschein.isChecked(), grund=self.grund.text(),
                    dokumente_=list(self.dateien.dateien), bemerkung=self.bemerkung.text())


class _Basis(QWidget):
    def __init__(self, seite):
        super().__init__()
        self.seite, self.db = seite, seite.db
        self.a = None

    def _ordner(self):
        """Ordner des Auftrags in der Ablage des ersten Angebots (oder None)."""
        if not self.a or not self.a["angebote"]:
            return None
        aid = au.angebot_id(self.db, self.a["angebote"][0]["uid"])
        return qs.auftragsordner(self.seite._ordner_von(aid) if aid else None, self.a["nummer"])

    def _fehler(self, e):
        self.seite.f.meldung(str(e), fehler=True)
        return False

    def _text(self, titel, frage, vorgabe=None):
        if vorgabe is not None:
            return vorgabe
        t, ok = QInputDialog.getText(self, titel, frage)
        return t.strip() if ok and t.strip() else None

    def dokument(self, dateien=None, bereich=None):
        if self.a is None:
            return False
        if dateien is None:
            dateien, _ = QFileDialog.getOpenFileNames(self, "Dokument zum Auftrag ablegen")
            if not dateien:
                return False
        try:
            liste = qs.dokumente_ablegen(self.db, self.a["uid"], dateien, bereich or self.BEREICH, self._ordner())
        except (au.AuftragFehler, OSError) as e:
            return self._fehler(e)
        self.seite.f.meldung(f"{len(liste)} Datei(en) im Auftrag {self.a['nummer']} abgelegt.")
        self.seite.neu_laden()
        return True


class QsReiter(_Basis):
    BEREICH = "Qualität"

    def __init__(self, seite):
        super().__init__(seite)
        self.bedingung = QLabel()
        self.bedingung.setTextFormat(Qt.RichText)
        self.bedingung.setWordWrap(True)
        knoepfe, self.knopf = _knoepfe(self, (
            ("pruefen", "Prüfung erfassen …", self.pruefen,
             "Prüfung der gewählten Position: geprüfte Menge, gut, Ausschuss, Nacharbeit, Prüfer, Fotos"),
            ("sonder", "Sonderfreigabe …", self.sonderfreigabe,
             "Position ohne vollständige Prüfung freigeben (z. B. Kunde nimmt so ab), nur mit Grund"),
            ("protokoll", "Messprotokoll (PDF)", self.messprotokoll,
             "Prüfplan mit Sollmaßen aus der STEP und leerer Ist-Spalte für das Angebot der Position"),
            ("dokument", "Foto / Dokument …", self.dokument, "Fotos oder Prüfberichte im Auftragsordner ablegen"),
            ("storno", "Prüfung stornieren …", self.stornieren, "Falsch erfasste Prüfung unwirksam machen (mit Grund)"),
            ("fertig", "Fertig melden …", self.fertigmelden,
             "Auftrag „Fertiggestellt“; nicht alles erfüllt = Sonderfreigabe mit Grund")))
        self.tabelle = _tabelle(QS_SPALTEN, 1)
        self.tabelle.itemSelectionChanged.connect(self._verlauf_zeigen)
        self.tabelle.doubleClicked.connect(lambda _: self.pruefen())
        self.tabelle.setToolTip("Doppelklick: Prüfung der Position erfassen")
        self.verlauf = _tabelle(VERLAUF_SPALTEN, 8)
        self.verlauf.doubleClicked.connect(self._datei_oeffnen)
        self.verlauf.setToolTip("Prüfungen der gewählten Position (neueste oben); Doppelklick öffnet die Dokumente")
        teiler = QSplitter(Qt.Vertical)
        teiler.addWidget(self.tabelle)
        teiler.addWidget(self.verlauf)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.bedingung)
        lay.addLayout(knoepfe)
        lay.addWidget(teiler, 1)
        self._qs = []

    def zeigen(self, a):
        alt = self.position()
        self.a = a
        for b in self.knopf.values():
            b.setEnabled(a is not None)
        if a is None:
            self.bedingung.setText("")
            self.tabelle.setRowCount(0)
            self.verlauf.setRowCount(0)
            return
        self.knopf["fertig"].setEnabled(a["status"] in qs.FERTIGMELDEN_ERLAUBT)
        for n in ("pruefen", "sonder", "storno"):
            self.knopf[n].setEnabled(a["status"] in qs.QS_ERLAUBT)
        teile = []
        for punkt, erfuellt, text in qs.bedingungen(a):
            farbe = "#1E8E3E" if erfuellt else "#B7791F"
            teile.append(f"<span style='color:{farbe}'>{'✔' if erfuellt else '○'}</span> <b>{punkt}</b>: {text}")
        if a["status"] in (au.FERTIG, au.AUSGELIEFERT, au.ABGESCHLOSSEN):
            teile.append(f"<b>{a['status']}</b>")
        self.bedingung.setText("<br>".join(teile))
        self.tabelle.setRowCount(len(a["positionen"]))
        for r, p in enumerate(a["positionen"]):
            st = qs.qs_stand(p)
            offen = qs.produktion_offen(p)
            farbe = {qs.QS_FERTIG: "#1E8E3E", qs.QS_SONDER: "#1E8E3E", qs.QS_NACHARBEIT: "#B42318",
                     qs.QS_TEIL: "#B7791F"}.get(st["status"])
            _zelle(self.tabelle, r, 0, p["nr"], daten=p["uid"])
            _zelle(self.tabelle, r, 1, " ".join(x for x in (p.get("artikel") or "", p.get("bezeichnung") or "") if x))
            _zelle(self.tabelle, r, 2, _zahl(st["menge"]), rechts=True)
            _zelle(self.tabelle, r, 3, "fertig" if not offen else "offen: " + ", ".join(offen),
                   farbe="#1E8E3E" if not offen else None)
            for c, f in ((4, "geprueft"), (5, "gut"), (6, "ausschuss"), (7, "nacharbeit")):
                _zelle(self.tabelle, r, c, _zahl(st[f]) if st[f] else "", rechts=True)
            _zelle(self.tabelle, r, 8, st["status"], farbe=farbe)
            _zelle(self.tabelle, r, 9, st["pruefer"])
            _zelle(self.tabelle, r, 10, _datum(st["datum"]))
        r = next((i for i, p in enumerate(a["positionen"]) if p["uid"] == alt), 0)
        if a["positionen"]:
            self.tabelle.selectRow(r)
        self._verlauf_zeigen()

    def position(self):
        r = self.tabelle.currentRow()
        it = self.tabelle.item(r, 0) if r >= 0 else None
        return it.data(Qt.UserRole) if it else None

    def _p(self):
        u = self.position()
        return next((p for p in (self.a or {}).get("positionen", ()) if p["uid"] == u), None)

    def waehlen(self, nr):
        for r, p in enumerate((self.a or {}).get("positionen", ())):
            if p["nr"] == nr:
                self.tabelle.selectRow(r)
                return True
        return False

    def _verlauf_zeigen(self):
        p = self._p()
        self._qs = qs.qs_verlauf(p) if p else []
        self.verlauf.setRowCount(len(self._qs))
        for r, x in enumerate(self._qs):
            d = x.get("storniert")
            werte = (_datum(x.get("datum")), x.get("pruefer") or "", _zahl(x.get("geprueft")), _zahl(x.get("gut")),
                     _zahl(x.get("ausschuss")) if x.get("ausschuss") else "",
                     _zahl(x.get("nacharbeit")) if x.get("nacharbeit") else "",
                     x.get("ergebnis") + (" (storniert)" if d else ""),
                     ", ".join(f["name"] for f in x.get("dokumente") or ()), x.get("bemerkung") or "")
            for c, t in enumerate(werte):
                _zelle(self.verlauf, r, c, t, rechts=c in (2, 3, 4, 5), durch=d, daten=x["uid"] if c == 0 else None)

    def _datei_oeffnen(self, *_):
        r = self.verlauf.currentRow()
        if 0 <= r < len(self._qs):
            for f in self._qs[r].get("dokumente") or ():
                QDesktopServices.openUrl(QUrl.fromLocalFile(f["pfad"]))

    def pruefen(self, werte=None):
        p = self._p()
        if self.a is None or p is None:
            return self._fehler("Bitte zuerst eine Position wählen.")
        if werte is None:
            d = PruefDialog(self, p, qs.qs_stand(p), au.benutzer(self.db)[1] or au.benutzer(self.db)[0])
            if d.exec() != QDialog.Accepted:
                return False
            werte = d.werte()
        try:
            qs.pruefung_erfassen(self.db, self.a["uid"], p["uid"], ordner=self._ordner(), **werte)
        except (au.AuftragFehler, OSError) as e:
            return self._fehler(e)
        self.seite.f.meldung(f"Prüfung Pos. {p['nr']} gespeichert.")
        self.seite.neu_laden()
        return True

    def sonderfreigabe(self, grund=None):
        p = self._p()
        if self.a is None or p is None:
            return self._fehler("Bitte zuerst eine Position wählen.")
        grund = self._text("Sonderfreigabe", f"Pos. {p['nr']} ohne vollständige Prüfung freigeben. Grund (steht in "
                                             "der Historie):", grund)
        if not grund:
            return False
        try:
            qs.pruefung_erfassen(self.db, self.a["uid"], p["uid"], 0, 0, ergebnis=qs.SONDER, bemerkung=grund)
        except au.AuftragFehler as e:
            return self._fehler(e)
        self.seite.neu_laden()
        return True

    def stornieren(self, zeile=None, grund=None):
        p = self._p()
        r = self.verlauf.currentRow() if zeile is None else zeile
        if self.a is None or p is None or not 0 <= r < len(self._qs) or self._qs[r].get("storniert"):
            return self._fehler("Bitte unten eine (nicht stornierte) Prüfung wählen.")
        grund = self._text("Prüfung stornieren", "Grund (steht in der Historie):", grund)
        if not grund:
            return False
        try:
            qs.pruefung_stornieren(self.db, self.a["uid"], p["uid"], self._qs[r]["uid"], grund)
        except au.AuftragFehler as e:
            return self._fehler(e)
        self.seite.neu_laden()
        return True

    def fertigmelden(self, grund=None):
        if self.a is None:
            return False
        if grund is None:
            if qs.fertig_moeglich(self.a):
                grund = ""
            else:
                offen = "\n".join(f"• {p}: {t}" for p, ok, t in qs.bedingungen(self.a) if not ok)
                grund = self._text("Sonderfreigabe", f"Noch nicht alles erfüllt:\n{offen}\n\nTrotzdem fertig melden? "
                                                     "Grund (steht in der Historie):")
                if grund is None:
                    return False
        try:
            qs.fertigmelden(self.db, self.a["uid"], grund)
        except au.AuftragFehler as e:
            return self._fehler(e)
        self.seite.f.meldung(f"Auftrag {self.a['nummer']} ist fertiggestellt.")
        self.seite.neu_laden()
        return True

    def messprotokoll(self):
        """Prüfplan/Messprotokoll (PDF) des Angebots der gewählten Position (wie im Angebot)."""
        p = self._p()
        aid = au.angebot_id(self.db, p.get("angebot")) if p and p.get("angebot") else None
        if not aid or not self.db.angebot(aid):
            return self._fehler("Messprotokoll gibt es nur für Positionen aus einem Angebot.")
        seite = self.seite.f.angebot_oeffnen(aid)
        return seite.pruefplan_pdf(erstmuster=False)


class LieferReiter(_Basis):
    BEREICH = "Auslieferung"

    def __init__(self, seite):
        super().__init__(seite)
        self.stand_text = QLabel()
        self.stand_text.setTextFormat(Qt.RichText)
        self.stand_text.setWordWrap(True)
        knoepfe, self.knopf = _knoepfe(self, (
            ("liefern", "Lieferung erfassen …", self.liefern,
             "Versand, Abholung oder eigene Lieferung mit Mengen je Position; legt den Lieferschein des Angebots an"),
            ("storno", "Lieferung stornieren …", self.stornieren, "Falsch erfasste Lieferung unwirksam machen"),
            ("dokument", "Dokument …", self.dokument, "Lieferpapiere, Fotos der Verpackung u. a. ablegen"),
            ("abschluss", "Auftrag abschließen …", self.abschliessen,
             "Nach der Auslieferung abschließen; übernimmt die Ist-Werte in die Nachkalkulation")))
        self.tabelle = _tabelle(LIEF_SPALTEN, 1)
        self.lieferungen = _tabelle(LIEFERUNG_SPALTEN, 2)
        self.dokumente = _tabelle(DOK_SPALTEN, 1)
        self.dokumente.doubleClicked.connect(self._datei_oeffnen)
        self.dokumente.setToolTip("Alle Dokumente des Auftrags; Doppelklick öffnet die Datei")
        unten = QTabWidget()
        unten.addTab(self.lieferungen, "Lieferungen")
        unten.addTab(self.dokumente, "Dokumente")
        teiler = QSplitter(Qt.Vertical)
        teiler.addWidget(self.tabelle)
        teiler.addWidget(unten)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.stand_text)
        lay.addLayout(knoepfe)
        lay.addWidget(teiler, 1)
        self._lief, self._dok = [], []

    def zeigen(self, a):
        self.a = a
        for b in self.knopf.values():
            b.setEnabled(a is not None)
        if a is None:
            self.stand_text.setText("")
            for t in (self.tabelle, self.lieferungen, self.dokumente):
                t.setRowCount(0)
            return
        self.knopf["liefern"].setEnabled(a["status"] in qs.LIEFERN_ERLAUBT)
        self.knopf["abschluss"].setEnabled(a["status"] != au.ABGESCHLOSSEN)
        st = qs.liefer_stand(a)
        menge = sum(z["menge"] for z in st)
        gel = sum(z["geliefert"] for z in st)
        frei = sum(z["lieferbar"] for z in st)
        self.stand_text.setText(f"<b>{a['status']}</b> · geliefert {_zahl(gel)} von {_zahl(menge)} Stück"
                                + (f" · jetzt lieferbar (i.O. geprüft) {_zahl(frei)}" if frei else "")
                                + (" · <span style='color:#1E8E3E'>alles geliefert</span>" if qs.alles_geliefert(a)
                                   else ""))
        self.tabelle.setRowCount(len(st))
        for r, z in enumerate(st):
            _zelle(self.tabelle, r, 0, z["nr"], daten=z["uid"])
            _zelle(self.tabelle, r, 1, " ".join(x for x in (z["artikel"], z["bezeichnung"]) if x))
            for c, f in ((2, "menge"), (3, "freigegeben"), (4, "geliefert"), (5, "offen"), (6, "lieferbar")):
                _zelle(self.tabelle, r, c, _zahl(z[f]), rechts=True,
                       farbe="#1E8E3E" if f == "offen" and z["offen"] <= 0 else None)
        nr = {p["uid"]: p["nr"] for p in a["positionen"]}
        alle = list(a["kopf"].get("_lieferungen") or ())
        weg = {x.get("storno") for x in alle if x.get("storno")}
        self._lief = [dict(x, storniert=x["uid"] in weg) for x in sorted(
            (x for x in reversed(alle) if not x.get("storno")), key=lambda x: x.get("am") or "", reverse=True)]
        self.lieferungen.setRowCount(len(self._lief))
        for r, x in enumerate(self._lief):
            werte = (_datum(x.get("datum")), x.get("art") or "",
                     ", ".join(f"Pos. {nr.get(k, '?')}: {_zahl(m)}" for k, m in (x.get("mengen") or {}).items()),
                     ", ".join(x.get("lieferscheine") or ()), x.get("verpackung") or "",
                     _zahl(x.get("paletten")) if x.get("paletten") else "",
                     " ".join(t for t in (x.get("wer") or "", _datum(x.get("am"))) if t),
                     " · ".join(t for t in (x.get("bemerkung") or "", x.get("grund") or "",
                                            "storniert" if x["storniert"] else "") if t))
            for c, t in enumerate(werte):
                _zelle(self.lieferungen, r, c, t, durch=x["storniert"])
        self._dok = list(reversed(qs.dokumente(a)))
        self.dokumente.setRowCount(len(self._dok))
        for r, d in enumerate(self._dok):
            for c, t in enumerate((d.get("bereich") or "", d.get("name") or "", _datum(d.get("am")),
                                   d.get("wer") or "")):
                _zelle(self.dokumente, r, c, t)

    def _datei_oeffnen(self, *_):
        r = self.dokumente.currentRow()
        if 0 <= r < len(self._dok):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._dok[r]["pfad"]))

    def liefern(self, werte=None):
        if self.a is None:
            return False
        if werte is None:
            d = LieferDialog(self, qs.liefer_stand(self.a))
            if d.exec() != QDialog.Accepted:
                return False
            werte = d.werte()
        try:
            r = qs.liefern(self.db, self.a["uid"], ordner=self._ordner(), **werte)
        except (au.AuftragFehler, OSError) as e:
            return self._fehler(e)
        text = f"Lieferung zum Auftrag {self.a['nummer']} gespeichert"
        if r["lieferscheine"]:
            text += f", Lieferschein {', '.join(r['lieferscheine'])} (Druck im Angebot)"
        self.seite.f.meldung(text + "." + (" " + " ".join(r["hinweise"]) if r["hinweise"] else ""),
                             fehler=bool(r["hinweise"]))
        self.seite.neu_laden()
        return True

    def stornieren(self, zeile=None, grund=None):
        r = self.lieferungen.currentRow() if zeile is None else zeile
        if self.a is None or not 0 <= r < len(self._lief) or self._lief[r]["storniert"]:
            return self._fehler("Bitte unten eine (nicht stornierte) Lieferung wählen.")
        grund = self._text("Lieferung stornieren", "Grund (steht in der Historie; der Lieferschein bleibt):", grund)
        if not grund:
            return False
        try:
            qs.lieferung_stornieren(self.db, self.a["uid"], self._lief[r]["uid"], grund)
        except au.AuftragFehler as e:
            return self._fehler(e)
        self.seite.neu_laden()
        return True

    def abschliessen(self, grund=None):
        if self.a is None:
            return False
        if grund is None:
            grund = "" if self.a["status"] == au.AUSGELIEFERT else self._text(
                "Auftrag abschließen", f"Der Auftrag steht auf „{self.a['status']}“ (noch nicht ausgeliefert).\n"
                                      "Trotzdem abschließen? Grund (steht in der Historie):")
            if grund is None:
                return False
        try:
            n = qs.abschliessen(self.db, self.a["uid"], grund)
        except au.AuftragFehler as e:
            return self._fehler(e)
        self.seite.f.meldung(f"Auftrag {self.a['nummer']} abgeschlossen."
                             + (f" {n} Ist-Werte in die Nachkalkulation übernommen." if n else ""))
        self.seite.neu_laden()
        return True
