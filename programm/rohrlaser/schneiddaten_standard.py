"""Schneiddaten auf Standard zurücksetzen (Patrick 29.10.2026): Vergleich der Tabelle mit den mitgelieferten
Richtwerten (stammdaten.beispiel_schneiddaten) und der Dialog mit Vorschau.

Umfang: alle Maschinen mit Richtwerten (stammdaten.LASER), eine Maschine oder nur die markierten Zeilen. Eine Zeile
gehört zum Standard, wenn Maschine, Kategorie, Gas und 'Wandstärke bis' einer Richtwertzeile gleichen und die
Werkstoff-ID leer ist; ihre Werte werden auf den Standard gesetzt. Eigene Zeilen (werkstoffgenau oder ohne passende
Richtwertzeile) werden beim Zurücksetzen einer Maschine entfernt, außer 'eigene Zeilen behalten'; fehlende
Standardzeilen kommen dazu. Bei 'nur markierte Zeilen' wird nichts entfernt und nichts ergänzt."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QLabel, QMessageBox, QRadioButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from . import stil
from .stammdaten import LASER, SCHNEIDDATEN, beispieldaten, zahl_als_text

# Werte, die das Zurücksetzen auf den Standard setzt (die Schlüsselfelder bleiben)
WERTE = ("vorschub_gross", "vorschub_mittel", "vorschub_klein", "einstechzeit", "vorschub_gravur", "zeit_ecke",
         "bemerkung")
TITEL = {f.name: f.titel for f in SCHNEIDDATEN.felder}


def _leer(v):
    return v is None or v == ""


def schluessel(z):
    """(Maschine, Werkstoff-ID, Kategorie, Gas, Wandstärke bis) einer Zeile; leere Felder als None."""
    w = z.get("wand_bis")
    return (z.get("maschinen_id"), None if _leer(z.get("werkstoff_id")) else z["werkstoff_id"],
            None if _leer(z.get("kategorie")) else z["kategorie"], None if _leer(z.get("gas")) else z["gas"],
            round(float(w), 3) if isinstance(w, (int, float)) else w)


def standard_zeilen(maschinen=None):
    """Mitgelieferte Schneiddaten-Zeilen (dicts) der Maschinen (None = alle mit Richtwerten)."""
    return [z for z in beispieldaten()["schneiddaten"] if maschinen is None or z["maschinen_id"] in maschinen]


def standard_je_schluessel():
    """{schluessel: Standardzeile} aller Richtwerte (Markierung der abweichenden Zellen in der Tabelle)."""
    return {schluessel(z): z for z in standard_zeilen()}


def gleich(a, b):
    if _leer(a) and _leer(b):
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-9
    return a == b


def abweichungen(z, std):
    """{Feld: (jetzt, Standard)} der Werte, die von der Standardzeile abweichen."""
    return {f: (z.get(f), std.get(f)) for f in WERTE if not gleich(z.get(f), std.get(f))}


def vergleich(aktuell, maschinen=None, ids=None, eigene_behalten=False):
    """Was das Zurücksetzen ändern würde. aktuell = Zeilen der Tabelle (mit id). Umfang: ids (markierte Zeilen) oder
    maschinen (None = alle mit Richtwerten). Ergebnis dict(aendern=[(Zeile, {Feld: (jetzt, Standard)}, Standard)],
    gleich=Anzahl schon wie Standard, entfernen=[Zeile], ergaenzen=[Standardzeile], ohne_standard=[Zeile] (markierte
    oder behaltene eigene Zeilen ohne Richtwert, bleiben unverändert), maschinen=[betroffene Maschinen])."""
    if ids is not None:
        ids = set(ids)
        zeilen = [z for z in aktuell if z.get("id") in ids]
        maschinen = sorted({z.get("maschinen_id") for z in zeilen if z.get("maschinen_id") in LASER})
        std = {schluessel(s): s for s in standard_zeilen(maschinen)}
    else:
        maschinen = sorted(m for m in (maschinen if maschinen is not None else LASER) if m in LASER)
        std = {schluessel(s): s for s in standard_zeilen(maschinen)}
        zeilen = [z for z in aktuell if z.get("maschinen_id") in maschinen]
    out = dict(aendern=[], gleich=0, entfernen=[], ergaenzen=[], ohne_standard=[], maschinen=maschinen)
    gefunden = set()
    for z in zeilen:
        s = std.get(schluessel(z))
        if s is None:
            (out["ohne_standard"] if ids is not None or eigene_behalten else out["entfernen"]).append(z)
            continue
        gefunden.add(schluessel(z))
        ab = abweichungen(z, s)
        if ab:
            out["aendern"].append((z, ab, s))
        else:
            out["gleich"] += 1
    if ids is None:
        out["ergaenzen"] = [s for k, s in std.items() if k not in gefunden]
    return out


def zeile_text(z):
    """'T11 · Stahl · N₂ · bis 3 mm' bzw. mit Werkstoff-ID."""
    teile = [z.get("maschinen_id"), z.get("werkstoff_id") or z.get("kategorie"), z.get("gas")]
    w = z.get("wand_bis")
    teile.append(f"bis {zahl_als_text(w)} mm" if isinstance(w, (int, float)) else "")
    return " · ".join(str(t) for t in teile if t)


def wert_text(v):
    if _leer(v):
        return "leer"
    return zahl_als_text(v) if isinstance(v, (int, float)) else str(v)


def zusammenfassung(v):
    """Kurztext der Vorschau: Anzahl geänderte, entfernte, ergänzte, unveränderte Zeilen."""
    teile = [f"{len(v['aendern'])} Zeile(n) bekommen Standardwerte"]
    if v["entfernen"]:
        teile.append(f"{len(v['entfernen'])} eigene Zeile(n) werden entfernt")
    if v["ergaenzen"]:
        teile.append(f"{len(v['ergaenzen'])} fehlende Standardzeile(n) werden ergänzt")
    if v["ohne_standard"]:
        teile.append(f"{len(v['ohne_standard'])} Zeile(n) ohne Richtwert bleiben unverändert")
    teile.append(f"{v['gleich']} Zeile(n) sind schon Standard")
    return ", ".join(teile) + "."


def vorschau_zeilen(v):
    """[(Zeile, Was, Jetzt, Standard)] für die Vorschautabelle."""
    out = []
    for z, ab, _ in v["aendern"]:
        for f, (jetzt, std) in ab.items():
            out.append((zeile_text(z), TITEL.get(f, f), wert_text(jetzt), wert_text(std)))
    for z in v["entfernen"]:
        out.append((zeile_text(z), "eigene Zeile", "vorhanden", "wird entfernt"))
    for s in v["ergaenzen"]:
        out.append((zeile_text(s), "Standardzeile", "fehlt", "wird ergänzt"))
    for z in v["ohne_standard"]:
        out.append((zeile_text(z), "kein Richtwert", "bleibt", "unverändert"))
    return out


class StandardDialog(QDialog):
    """Umfang wählen, Vorschau prüfen, dann 'Zurücksetzen …' (mit letzter Rückfrage, Vorwahl Nein). Ergebnis in
    self.wahl = dict(maschinen, ids, eigene_behalten) oder None."""
    SPALTEN = ("Zeile", "Was", "Jetzt", "Standard")

    def __init__(self, eltern, aktuell, markiert=(), stumm=False):
        super().__init__(eltern)
        self.aktuell, self.markiert, self.stumm = aktuell, list(markiert), stumm
        self.wahl = None
        self.setWindowTitle("Schneiddaten auf Standard zurücksetzen")
        self.resize(760, 520)
        oben = QLabel("Die mitgelieferten Richtwerte (Rohr-Schnitttabellen, keine Herstellerwerte) gibt es für "
                      f"{', '.join(f'{m} ({laser})' for m, laser in LASER.items())}. Vorher wird automatisch eine "
                      "Datensicherung angelegt (zurückholen mit „Sicherung wiederherstellen …“).")
        oben.setWordWrap(True)
        self.alle = QRadioButton(f"Alle Maschinen ({', '.join(LASER)})")
        self.eine = QRadioButton("Eine Maschine")
        self.maschine = QComboBox()
        self.maschine.addItems([f"{m} ({laser}-Laser)" for m, laser in LASER.items()])
        self.nur_markiert = QRadioButton(f"Nur die markierten Zeilen ({len(self.markiert)})")
        self.nur_markiert.setEnabled(bool(self.markiert))
        self.gruppe = QButtonGroup(self)
        for b in (self.alle, self.eine, self.nur_markiert):
            self.gruppe.addButton(b)
        (self.nur_markiert if self.markiert else self.alle).setChecked(True)
        self.behalten = QCheckBox("Eigene Zeilen behalten")
        self.behalten.setToolTip("Zeilen je Werkstoff und andere eigene Zeilen bleiben, nur die Standardzeilen werden "
                                 "zurückgesetzt")
        eine = QHBoxLayout()
        eine.addWidget(self.eine)
        eine.addWidget(self.maschine)
        eine.addStretch(1)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.tabelle = QTableWidget(0, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabelle.verticalHeader().hide()
        self.tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        knoepfe = QDialogButtonBox()
        self.ok = knoepfe.addButton("Zurücksetzen …", QDialogButtonBox.AcceptRole)
        knoepfe.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        self.ok.clicked.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(oben)
        lay.addWidget(self.alle)
        lay.addLayout(eine)
        lay.addWidget(self.nur_markiert)
        lay.addWidget(self.behalten)
        lay.addWidget(self.text)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(knoepfe)
        for b in (self.alle, self.eine, self.nur_markiert):
            b.toggled.connect(self._zeigen)
        self.maschine.currentIndexChanged.connect(lambda *_: (self.eine.setChecked(True), self._zeigen()))
        self.behalten.toggled.connect(self._zeigen)
        self._zeigen()

    def umfang(self):
        """dict(maschinen, ids, eigene_behalten) der aktuellen Wahl."""
        if self.nur_markiert.isChecked():
            return dict(maschinen=None, ids=self.markiert, eigene_behalten=True)
        maschinen = list(LASER) if self.alle.isChecked() else [list(LASER)[self.maschine.currentIndex()]]
        return dict(maschinen=maschinen, ids=None, eigene_behalten=self.behalten.isChecked())

    def _zeigen(self, *_):
        u = self.umfang()
        self.behalten.setEnabled(u["ids"] is None)
        self.v = vergleich(self.aktuell, **u)
        self.text.setText(zusammenfassung(self.v))
        zeilen = vorschau_zeilen(self.v)
        self.tabelle.setRowCount(len(zeilen))
        for i, werte in enumerate(zeilen):
            for j, w in enumerate(werte):
                item = QTableWidgetItem(w)
                if j == 3:
                    item.setBackground(stil.farbe_fest("#FCE4D6" if w == "wird entfernt" else "#E2F0D9"))
                self.tabelle.setItem(i, j, item)
        self.tabelle.resizeColumnsToContents()
        self.tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ok.setEnabled(bool(self.v["aendern"] or self.v["entfernen"] or self.v["ergaenzen"]))

    def bestaetigung_text(self):
        v = self.v
        return (f"Schneiddaten von {', '.join(v['maschinen']) or '–'} auf Standard zurücksetzen?\n\n"
                + zusammenfassung(v) + "\n\nVorher wird eine Datensicherung angelegt. Angebote mit "
                "festgeschriebenen Preisen rechnen mit ihren gespeicherten Schneiddaten weiter.")

    def _ok(self):
        if not self.stumm and QMessageBox.question(
                self, "Schneiddaten zurücksetzen", self.bestaetigung_text(),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.wahl = self.umfang()
        self.accept()


def dialog_zeigen(eltern, aktuell, markiert=()):
    """Dialog öffnen; Ergebnis die Wahl (dict) oder None."""
    d = StandardDialog(eltern, aktuell, markiert)
    d.setAttribute(Qt.WA_DeleteOnClose, False)
    return d.wahl if d.exec() == QDialog.Accepted else None
