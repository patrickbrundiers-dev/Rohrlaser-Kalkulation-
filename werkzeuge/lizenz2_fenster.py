"""Lizenz 2.0 im Fenster des Lizenz-Werkzeugs (Paket L2-2): Übersicht aller Lizenzen mit Lizenzschlüssel und Plätzen.

Oben die Lizenzen (Lizenznehmer, Art, belegt/max, Ablauf, Status, Schlüssel), unten die Plätze der markierten
Lizenz. Aktionen: neue Lizenz, Anfrage beantworten, Freigabebeleg verbuchen, Platz deaktivieren, verlängern, Plätze/
Benutzer ändern, übertragen, sperren. Die Logik steht in lizenz2_werkzeug.py; Fehler kommen dort als SystemExit.
Jede Aktion nimmt ihre Werte optional als Parameter (Tests ohne Rückfragen).
"""
import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import lizenz2_werkzeug as L2
import lizenz_werkzeug as wz
from rohrlaser import aktivierung as A
from rohrlaser import lizenz

SPALTEN = (("lizenz_nr", "Lizenznummer"), ("lizenznehmer", "Lizenznehmer"), ("firma", "Firma"), ("typ", "Art"),
           ("plaetze_text", "Plätze belegt"), ("benutzer", "Benutzer"), ("gueltig_bis", "Gültig bis"),
           ("status_text", "Status"), ("lizenzschluessel", "Lizenzschlüssel"))
PLATZ_SPALTEN = (("aktivierung_id", "Platz"), ("name", "Rechnername"), ("rechner_id", "Rechner-ID"),
                 ("aktiviert_am", "Aktiviert am"), ("status_text", "Status"))
FARBE = dict(abgelaufen="#FDE2E1", laeuft_ab="#FEF3C7", gesperrt="#E5E7EB", ersetzt="#F3F4F6")


def _datum(q):
    return datetime.date(q.year(), q.month(), q.day())


def _qdate(d):
    return QDate(d.year, d.month, d.day)


class LizenzDialog2(QDialog):
    """Eingabe für eine neue oder geänderte Lizenz."""

    def __init__(self, eltern, titel, werte=None):
        super().__init__(eltern)
        self.setWindowTitle(titel)
        w = werte or {}
        form = QFormLayout(self)
        self.lizenznehmer = QLineEdit(w.get("lizenznehmer", ""))
        self.firma = QLineEdit(w.get("firma", ""))
        self.kundennr = QLineEdit(w.get("kundennr", ""))
        self.typ = QComboBox()
        for t in A.TYPEN:
            self.typ.addItem(A.TYP_TEXT[t], t)
        self.typ.setCurrentIndex(A.TYPEN.index(w.get("typ", "einzelplatz")))
        self.plaetze = QSpinBox()
        self.plaetze.setRange(1, 500)
        self.plaetze.setValue(int(w.get("plaetze", 1)))
        self.benutzer = QSpinBox()
        self.benutzer.setRange(0, 1000)
        self.benutzer.setSpecialValueText("ohne Grenze")
        self.benutzer.setValue(int(w.get("benutzer", 0)))
        self.reserve = QSpinBox()
        self.reserve.setRange(0, 20)
        self.reserve.setValue(int(w.get("reserve", 1)))
        self.unbefristet = QCheckBox("unbefristet (Kauflizenz)")
        self.bis = QDateEdit()
        self.bis.setCalendarPopup(True)
        self.bis.setDisplayFormat("dd.MM.yyyy")
        bis = w.get("bis", wz.monate_spaeter(datetime.date.today(), 12))
        self.unbefristet.setChecked(bis is None)
        self.bis.setDate(_qdate(bis or wz.monate_spaeter(datetime.date.today(), 12)))
        self.unbefristet.toggled.connect(lambda an: self.bis.setEnabled(not an))
        self.bis.setEnabled(bis is not None)
        self.module = QLineEdit(", ".join(w.get("module") or ["alle"]))
        self.admins = QLineEdit(", ".join(w.get("admins") or []))
        self.admins.setPlaceholderText("Namen der Kunden-Admins, durch Komma getrennt")
        self.hinweis = QLineEdit(w.get("hinweis", ""))
        self.typ.currentIndexChanged.connect(self._typ)
        for titel_, feld in (("Lizenznehmer:", self.lizenznehmer), ("Firma:", self.firma),
                             ("Kundennummer:", self.kundennr), ("Art:", self.typ), ("Plätze:", self.plaetze),
                             ("Benutzer (Server):", self.benutzer), ("Reserve für Hardwaretausch:", self.reserve),
                             ("Gültig bis:", self.bis), ("", self.unbefristet), ("Module:", self.module),
                             ("Kunden-Admins:", self.admins), ("Hinweis:", self.hinweis)):
            form.addRow(titel_, feld)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        form.addRow(k)
        self._typ()

    def _typ(self):
        einzel = self.typ.currentData() == "einzelplatz"
        if einzel:
            self.plaetze.setValue(1)
        self.plaetze.setEnabled(not einzel)
        self.benutzer.setEnabled(self.typ.currentData() == "server")

    def werte(self):
        return dict(lizenznehmer=self.lizenznehmer.text().strip(), firma=self.firma.text().strip(),
                    kundennr=self.kundennr.text().strip(), typ=self.typ.currentData(), plaetze=self.plaetze.value(),
                    benutzer=self.benutzer.value(), reserve=self.reserve.value(),
                    bis=None if self.unbefristet.isChecked() else _datum(self.bis.date()),
                    module=[m.strip() for m in self.module.text().split(",") if m.strip()] or ["alle"],
                    admins=[a.strip() for a in self.admins.text().split(",") if a.strip()],
                    hinweis=self.hinweis.text().strip())


class Lizenzen2(QDialog):
    """Lizenz-Übersicht 2.0 (Dashboard)."""

    def __init__(self, eltern, ordner, pw=None, stumm=False):
        super().__init__(eltern)
        self.ordner, self.pw, self.stumm = Path(ordner), pw, stumm
        self.setWindowTitle("Lizenzen mit Lizenzschlüssel (Lizenz 2.0)")
        self.resize(1100, 680)
        lay = QVBoxLayout(self)
        self.kopf = QLabel()
        self.kopf.setWordWrap(True)
        lay.addWidget(self.kopf)
        zeile = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Suchen: Lizenznehmer, Firma, Lizenznummer, Schlüssel, Rechnername")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self.filtern)
        self.alte = QCheckBox("ersetzte Lizenzen zeigen")
        self.alte.toggled.connect(self.filtern)
        zeile.addWidget(self.filter, 1)
        zeile.addWidget(self.alte)
        lay.addLayout(zeile)
        teiler = QSplitter(Qt.Vertical)
        self.tabelle = self._tabelle(SPALTEN)
        self.tabelle.itemSelectionChanged.connect(self.plaetze_zeigen)
        self.plaetze_tabelle = self._tabelle(PLATZ_SPALTEN)
        oben, unten = QWidget(), QWidget()
        QVBoxLayout(oben).addWidget(self.tabelle)
        ul = QVBoxLayout(unten)
        self.plaetze_titel = QLabel("<b>Plätze</b> der markierten Lizenz")
        ul.addWidget(self.plaetze_titel)
        ul.addWidget(self.plaetze_tabelle)
        teiler.addWidget(oben)
        teiler.addWidget(unten)
        lay.addWidget(teiler, 1)
        knoepfe = QHBoxLayout()
        for text, ziel, tipp in (
                ("Neue Lizenz …", self.neu, "Lizenzzertifikat mit Lizenzschlüssel für einen Kunden"),
                ("Anfrage beantworten …", self.anfrage, "Aktivierungsanfrage (Datei oder Code) eines Rechners"),
                ("Freigabe verbuchen …", self.freigabe, "Freigabebeleg eines Rechners: Platz wird frei"),
                ("Platz deaktivieren …", self.deaktivieren, "Rechner defekt oder verloren: Platz frei + Sperrliste"),
                ("Verlängern …", self.verlaengern, "neues Zertifikat mit gleichem Schlüssel, Plätze ziehen mit"),
                ("Ändern / übertragen …", self.aendern, "Plätze, Benutzer, Module oder Lizenznehmer ändern"),
                ("Sperren …", self.sperren, "ganze Lizenz sperren (Sperrliste)"),
                ("Schlüssel kopieren", self.schluessel_kopieren, "Lizenzschlüssel in die Zwischenablage")):
            b = QPushButton(text)
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, f=ziel: f())
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        lay.addLayout(knoepfe)
        self.neu_laden()

    # ---------------------------------------------------------------- Anzeige
    @staticmethod
    def _tabelle(spalten):
        t = QTableWidget(0, len(spalten))
        t.setHorizontalHeaderLabels([s for _, s in spalten])
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setSelectionMode(QTableWidget.SingleSelection)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)
        return t

    def neu_laden(self, markieren=None):
        markieren = markieren or self.markierte()
        self.zeilen = L2.uebersicht(self.ordner)
        aktiv = [z for z in self.zeilen if not z["ersetzt_durch"]]
        belegt = sum(z["belegt"] for z in aktiv)
        faellig = [z for z in aktiv if z["status"] in ("laeuft_ab", "abgelaufen")]
        self.kopf.setText(f"<b>{len(aktiv)}</b> Lizenzen, <b>{belegt}</b> Plätze belegt"
                          + (f" · <span style='color:#B45309'><b>{len(faellig)}</b> laufen bald ab oder sind "
                             "abgelaufen</span>" if faellig else ""))
        self.tabelle.setRowCount(len(self.zeilen))
        for i, z in enumerate(self.zeilen):
            z = dict(z, typ=A.TYP_TEXT.get(z["typ"], z["typ"]), plaetze_text=f"{z['belegt']} / {z['max']}",
                     benutzer=z["benutzer"] or "")
            farbe = FARBE.get(z["status"])
            for j, (s, _) in enumerate(SPALTEN):
                item = QTableWidgetItem(str(z.get(s, "")))
                if farbe:
                    item.setBackground(QColor(farbe))
                self.tabelle.setItem(i, j, item)
        self.filtern()
        if markieren:
            for i in range(self.tabelle.rowCount()):
                if self.tabelle.item(i, 0).text() == markieren:
                    self.tabelle.selectRow(i)
        self.plaetze_zeigen()

    def filtern(self, *_):
        text = self.filter.text().strip().casefold()
        for i, z in enumerate(self.zeilen):
            zeile = " ".join(self.tabelle.item(i, j).text() for j in range(self.tabelle.columnCount())).casefold()
            if text and text not in zeile:     # auch Rechnernamen der Plätze durchsuchen
                zeile += " " + " ".join(f"{a.get('name', '')} {a.get('rechner_id', '')}"
                                        for a in L2.aktivierungen_von(self.ordner, z["lizenz_nr"])).casefold()
            versteckt = (bool(text) and text not in zeile) or (bool(z["ersetzt_durch"]) and not self.alte.isChecked())
            self.tabelle.setRowHidden(i, versteckt)

    def markierte(self):
        zeilen = {i.row() for i in self.tabelle.selectedIndexes()} if hasattr(self, "tabelle") else set()
        return self.tabelle.item(min(zeilen), 0).text() if zeilen else None

    def markieren(self, nr):
        self.neu_laden(nr)

    def plaetze_zeigen(self):
        nr = self.markierte()
        liste = L2.aktivierungen_von(self.ordner, nr) if nr else []
        self.plaetze_titel.setText(f"<b>Plätze</b> von {nr}" if nr else "<b>Plätze</b> der markierten Lizenz")
        self.plaetze_tabelle.setRowCount(len(liste))
        for i, a in enumerate(liste):
            a = dict(a, status_text="aktiv" if a["status"] == "aktiv" else
                     f"frei seit {a.get('frei_am', '')} ({a.get('frei_grund', '')})")
            for j, (s, _) in enumerate(PLATZ_SPALTEN):
                item = QTableWidgetItem(str(a.get(s, "")))
                if a["status"] != "aktiv":
                    item.setForeground(QColor("#6B7280"))
                self.plaetze_tabelle.setItem(i, j, item)

    def markierter_platz(self):
        zeilen = {i.row() for i in self.plaetze_tabelle.selectedIndexes()}
        return self.plaetze_tabelle.item(min(zeilen), 0).text() if zeilen else None

    # ---------------------------------------------------------------- Hilfen
    def fehler(self, e):
        if not self.stumm:
            QMessageBox.warning(self, "Lizenz 2.0", str(e))
        self.letzter_fehler = str(e)
        return None

    def passwort(self):
        if self.pw:
            return self.pw
        pw, ok = QInputDialog.getText(self, "Passwort", "Passwort des privaten Schlüssels:", QLineEdit.Password)
        return pw.encode("utf-8") if ok and pw else None

    def quelle_abfragen(self, titel):
        """Datei oder eingefügter Code (Text). Ergebnis: Path, Text oder None."""
        d = QDialog(self)
        d.setWindowTitle(titel)
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel("Code einfügen (ANFRAGE-… bzw. FREIGABE-…) oder eine Datei wählen:"))
        feld = QPlainTextEdit()
        lay.addWidget(feld)
        datei = QPushButton("Datei wählen …")
        ergebnis = {}

        def waehlen():
            p, _ = QFileDialog.getOpenFileName(d, titel, str(Path.home()), "Datei (*.json *.lizenz);;Alle Dateien (*)")
            if p:
                ergebnis["pfad"] = Path(p)
                d.accept()
        datei.clicked.connect(waehlen)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.addButton(datei, QDialogButtonBox.ActionRole)
        k.accepted.connect(d.accept)
        k.rejected.connect(d.reject)
        lay.addWidget(k)
        if not d.exec():
            return None
        return ergebnis.get("pfad") or (feld.toPlainText().strip() or None)

    def ergebnis_zeigen(self, titel, text, code="", datei=None):
        QGuiApplication.clipboard().setText(code or text)
        if self.stumm:
            return
        d = QDialog(self)
        d.setWindowTitle(titel)
        lay = QVBoxLayout(d)
        info = QLabel(text + (f"<br><br>Datei: {datei}" if datei else "")
                      + ("<br><br>Code für den Kunden (schon in der Zwischenablage):" if code else ""))
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(info)
        if code:
            feld = QPlainTextEdit(code)
            feld.setReadOnly(True)
            lay.addWidget(feld)
        k = QDialogButtonBox(QDialogButtonBox.Ok)
        k.accepted.connect(d.accept)
        lay.addWidget(k)
        d.exec()

    # ---------------------------------------------------------------- Aktionen
    def neu(self, werte=None):
        if werte is None:
            d = LizenzDialog2(self, "Neue Lizenz")
            if not d.exec():
                return None
            werte = d.werte()
        if not werte.get("lizenznehmer"):
            return self.fehler("Bitte den Lizenznehmer eintragen.")
        pw = self.passwort()
        if not pw:
            return None
        w = dict(werte)
        try:
            schl, datei = L2.zertifikat_ausstellen(self.ordner, w.pop("lizenznehmer"), w.pop("typ"),
                                                   w.pop("plaetze", 1), pw=pw, **w)
        except (SystemExit, lizenz.LizenzFehler, ValueError) as e:
            return self.fehler(e)
        nr = datei.name.split("_")[0]
        self.markieren(nr)
        self.ergebnis_zeigen("Lizenz erstellt", f"Lizenz <b>{nr}</b> erstellt. Diesen Lizenzschlüssel an den Kunden "
                             f"schicken (er gibt ihn unter Hilfe → Lizenz … → Mit Lizenzschlüssel aktivieren ein):"
                             f"<br><br><b style='font-size:14pt'>{schl}</b>", schl, datei)
        return schl, nr

    def anfrage(self, quelle=None):
        quelle = quelle if quelle is not None else self.quelle_abfragen("Anfrage beantworten")
        if quelle is None:
            return None
        pw = self.passwort()
        if not pw:
            return None
        try:
            antwort, datei, text = L2.aktivieren(self.ordner, quelle, pw=pw)
        except (SystemExit, lizenz.LizenzFehler) as e:
            return self.fehler(e)
        self.markieren(antwort["inhalt"]["lizenz_nr"])
        self.ergebnis_zeigen("Anfrage beantwortet", f"{text}<br><br>Die Antwortdatei oder den Code an den Kunden "
                             "schicken (Hilfe → Lizenz … → Aktivierung einfügen bzw. Lizenzdatei laden).",
                             A.als_code(antwort), datei)
        return antwort

    def freigabe(self, quelle=None):
        quelle = quelle if quelle is not None else self.quelle_abfragen("Freigabe verbuchen")
        if quelle is None:
            return None
        try:
            aid = L2.freigeben(self.ordner, quelle)
        except (SystemExit, lizenz.LizenzFehler) as e:
            return self.fehler(e)
        self.neu_laden()
        self.ergebnis_zeigen("Freigabe verbucht", f"Platz {aid} ist wieder frei.")
        return aid

    def deaktivieren(self, aid=None, bestaetigt=None):
        aid = aid or self.markierter_platz()
        if not aid:
            return self.fehler("Bitte unten einen Platz markieren.")
        if bestaetigt is None:
            bestaetigt = QMessageBox.question(
                self, "Platz deaktivieren", f"Platz {aid} deaktivieren?\n\nDer Platz wird frei und kommt auf die "
                "Sperrliste (danach „Sperrliste hochladen …“ im Hauptfenster), damit der Rechner nicht weiterläuft.") \
                == QMessageBox.Yes
        if not bestaetigt:
            return None
        pw = self.passwort()
        if not pw:
            return None
        try:
            L2.deaktivieren(self.ordner, aid, pw=pw)
        except SystemExit as e:
            return self.fehler(e)
        self.neu_laden()
        return aid

    def _werte(self, nr):
        d = L2.register_lesen(self.ordner)
        z = d["zertifikate"][nr]["zertifikat"]["inhalt"]
        return dict(lizenznehmer=z["lizenznehmer"], firma=z.get("firma", ""), kundennr=z.get("kundennr", ""),
                    typ=z["typ"], plaetze=z["plaetze"], benutzer=z.get("benutzer", 0),
                    reserve=z["aktivierungen_max"] - z["plaetze"], module=z.get("module"), admins=z.get("admins"),
                    hinweis=z.get("hinweis", ""),
                    bis=datetime.date.fromisoformat(z["gueltig_bis"]) if z.get("gueltig_bis") else None)

    def _ersetzen(self, nr, werte, titel):
        pw = self.passwort()
        if not pw:
            return None
        try:
            neu_nr, datei = L2.aendern(self.ordner, nr, pw=pw, **werte)
        except (SystemExit, lizenz.LizenzFehler, ValueError) as e:
            return self.fehler(e)
        self.markieren(neu_nr)
        self.ergebnis_zeigen(titel, f"Neue Lizenz <b>{neu_nr}</b> ersetzt {nr}. Der Lizenzschlüssel bleibt gleich. "
                             "Die Rechner holen sich die neue Lizenz mit <i>Mit Lizenzschlüssel aktivieren …</i> "
                             "(gleicher Schlüssel); die Anfrage hier beantworten, es wird kein neuer Platz belegt.",
                             datei=datei)
        return neu_nr

    def verlaengern(self, bis=None):
        nr = self.markierte()
        if not nr:
            return self.fehler("Bitte oben eine Lizenz markieren.")
        if bis is None:
            alt = self._werte(nr)["bis"] or datetime.date.today()
            start = max(alt, datetime.date.today())
            vorschlag = wz.monate_spaeter(start + datetime.timedelta(days=1), 12)
            text, ok = QInputDialog.getText(self, "Verlängern", f"{nr} gültig bis (TT.MM.JJJJ):",
                                            text=vorschlag.strftime("%d.%m.%Y"))
            if not ok:
                return None
            try:
                bis = datetime.datetime.strptime(text.strip(), "%d.%m.%Y").date()
            except ValueError:
                return self.fehler("Bitte ein Datum wie 31.12.2027 eingeben.")
        return self._ersetzen(nr, dict(bis=bis), "Lizenz verlängert")

    def aendern(self, werte=None):
        nr = self.markierte()
        if not nr:
            return self.fehler("Bitte oben eine Lizenz markieren.")
        if werte is None:
            d = LizenzDialog2(self, f"{nr} ändern oder übertragen", self._werte(nr))
            if not d.exec():
                return None
            werte = d.werte()
        return self._ersetzen(nr, werte, "Lizenz geändert")

    def sperren(self, bestaetigt=None):
        nr = self.markierte()
        if not nr:
            return self.fehler("Bitte oben eine Lizenz markieren.")
        if bestaetigt is None:
            bestaetigt = QMessageBox.question(self, "Lizenz sperren", f"Lizenz {nr} mit allen Plätzen sperren?\n\n"
                                              "Danach „Sperrliste hochladen …“ im Hauptfenster.") == QMessageBox.Yes
        if not bestaetigt:
            return None
        pw = self.passwort()
        if not pw:
            return None
        try:
            L2.lizenz_sperren(self.ordner, nr, pw=pw)
        except SystemExit as e:
            return self.fehler(e)
        self.neu_laden(nr)
        return nr

    def schluessel_kopieren(self):
        nr = self.markierte()
        if not nr:
            return self.fehler("Bitte oben eine Lizenz markieren.")
        schl = L2.register_lesen(self.ordner)["zertifikate"][nr]["lizenzschluessel"]
        QGuiApplication.clipboard().setText(schl)
        return schl

