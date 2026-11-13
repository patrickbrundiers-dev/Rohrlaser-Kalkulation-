"""Benutzer und Rollen (Plan Auftragsworkflow, Paket 6) als Teil der Seite „Arbeitsplätze und Rechte“ (nur
Hauptadmin), Anmeldefenster „Benutzer anmelden“. Regeln in rollen.py.

Oben die Benutzer (Kürzel, Name, Rollen, Anmeldung, Aktiv) mit Benutzer anlegen, Rollen, Passwort / PIN, Sperren und
Entfernen; darunter die Rechtetabelle je Rolle und Bereich (–, sehen, bearbeiten) und der Schalter „Beim Start
anmelden“.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import rollen

SPALTEN = ("Kürzel", "Name", "Rollen", "Anmeldung", "Aktiv")


def _tabelle(spalten, dehnen):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    if dehnen is not None:
        t.horizontalHeader().setSectionResizeMode(dehnen, QHeaderView.Stretch)
    return t


class BenutzerDialog(QDialog):
    """Kürzel, Name und Rollen (Häkchen) eines Benutzers, dazu optional Passwort und PIN."""

    def __init__(self, eltern, z=None):
        super().__init__(eltern)
        self.setWindowTitle("Benutzer" if z else "Benutzer anlegen")
        form = QFormLayout(self)
        self.kuerzel = QLineEdit((z or {}).get("kuerzel") or "")
        self.kuerzel.setEnabled(not z)
        self.name = QLineEdit((z or {}).get("name") or "")
        form.addRow("Kürzel", self.kuerzel)
        form.addRow("Name", self.name)
        self.rollen = {}
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        for r, titel in rollen.ROLLEN:
            c = QCheckBox(titel)
            c.setChecked(r in ((z or {}).get("rollen") or ()))
            self.rollen[r] = c
            bl.addWidget(c)
        form.addRow("Rollen", box)
        self.passwort = QLineEdit()
        self.passwort.setEchoMode(QLineEdit.Password)
        self.passwort.setPlaceholderText(f"leer = unverändert, mindestens {rollen.PASSWORT_MIN} Zeichen")
        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.Password)
        self.pin.setPlaceholderText(f"leer = unverändert, {rollen.PIN_MIN}–{rollen.PIN_MAX} Ziffern (Werkstatt)")
        form.addRow("Passwort", self.passwort)
        form.addRow("PIN", self.pin)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Ok).setText("Speichern")
        k.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        form.addRow(k)

    def werte(self):
        return dict(kuerzel=self.kuerzel.text(), name=self.name.text(),
                    rollen=[r for r, c in self.rollen.items() if c.isChecked()],
                    passwort=self.passwort.text() or None, pin=self.pin.text() or None)


class RollenTeil(QWidget):
    def __init__(self, db, meldung, geaendert=None):
        super().__init__()
        self.db, self.meldung, self.geaendert = db, meldung, geaendert
        self.gesperrt = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        text = QLabel("<b>Benutzer und Rollen</b>: Jeder Benutzer (Kürzel) bekommt eine oder mehrere Rollen und ein "
                      "Passwort oder eine PIN (Werkstatt). Solange niemand eine Rolle hat, darf jeder alles wie "
                      "bisher. Danach gilt die Rechtetabelle; wer keine Rolle hat, darf nur sehen. Ein freigeschalteter "
                      "Admin darf immer alles.")
        text.setWordWrap(True)
        lay.addWidget(text)
        self.tabelle = _tabelle(SPALTEN, 2)
        self.tabelle.setMinimumHeight(180)
        self.tabelle.doubleClicked.connect(lambda _: self.bearbeiten())
        lay.addWidget(self.tabelle)
        zeile = QHBoxLayout()
        self.knopf = {}
        for name, titel, ziel, tip in (
                ("neu", "Benutzer anlegen …", self.anlegen, "Neuen Benutzer mit Kürzel, Name, Rollen und Passwort/PIN"),
                ("bearbeiten", "Rollen und Zugang …", self.bearbeiten,
                 "Name, Rollen, Passwort oder PIN des gewählten Benutzers ändern"),
                ("sperren", "Sperren / Entsperren", self.sperren_umschalten,
                 "Gesperrte Benutzer können sich nicht anmelden und dürfen nur sehen"),
                ("entfernen", "Entfernen", self.entfernen, "Benutzer mit Rollen und Zugang entfernen")):
            b = QPushButton(titel)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            self.knopf[name] = b
            zeile.addWidget(b)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.pflicht = QCheckBox("Beim Start anmelden (Kürzel und Passwort oder PIN)")
        self.pflicht.setToolTip("Gilt, sobald Benutzer mit Rollen und Passwort/PIN angelegt sind. Aus: es gilt das "
                                "Kürzel des Arbeitsplatzes; „Datei → Benutzer anmelden …“ wechselt den Benutzer.")
        self.pflicht.toggled.connect(self._pflicht_gesetzt)
        lay.addWidget(self.pflicht)
        lay.addWidget(QLabel("<b>Rechtetabelle</b>: je Rolle und Bereich – (kein Zugriff), sehen oder bearbeiten"))
        self.rechte = QTableWidget(len(rollen.ROLLEN), len(rollen.BEREICHE))
        self.rechte.setHorizontalHeaderLabels([t for _, t in rollen.BEREICHE])
        self.rechte.setVerticalHeaderLabels([t for _, t in rollen.ROLLEN])
        self.rechte.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.rechte.setMinimumHeight(300)
        lay.addWidget(self.rechte)
        z2 = QHBoxLayout()
        self.vorgabe_knopf = QPushButton("Vorgabe wiederherstellen")
        self.vorgabe_knopf.setToolTip("Rechtetabelle auf die Vorgabe des Programms zurücksetzen")
        self.vorgabe_knopf.clicked.connect(self.vorgabe)
        z2.addWidget(self.vorgabe_knopf)
        z2.addStretch(1)
        lay.addLayout(z2)
        self.stumm = False
        self.neu_laden()

    def neu_laden(self):
        self.liste = rollen.uebersicht(self.db)
        t = self.tabelle
        t.setRowCount(len(self.liste))
        for r, z in enumerate(self.liste):
            zugang = " und ".join(x for x, ja in (("Passwort", z["passwort"]), ("PIN", z["pin"])) if ja) or "–"
            for c, w in enumerate((z["kuerzel"], z["name"] or "–",
                                   ", ".join(rollen.ROLLE_TITEL[x] for x in z["rollen"]) or "keine (nur sehen)"
                                   if rollen.aktiv(self.db) else ", ".join(rollen.ROLLE_TITEL[x] for x in z["rollen"])
                                   or "–", zugang, "ja" if z["aktiv"] else "gesperrt")):
                it = QTableWidgetItem(w)
                it.setData(Qt.UserRole, z["kuerzel"])
                t.setItem(r, c, it)
        self.pflicht.blockSignals(True)
        self.pflicht.setChecked(self.db.einstellung(rollen.PFLICHT) != "nein")
        self.pflicht.blockSignals(False)
        werte = rollen.rechte(self.db)
        for r, (rolle, _) in enumerate(rollen.ROLLEN):
            for c, (bereich, _) in enumerate(rollen.BEREICHE):
                box = QComboBox()
                for k, titel in rollen.STUFEN:
                    box.addItem(titel, k)
                box.setCurrentIndex([k for k, _ in rollen.STUFEN].index(werte[rolle][bereich]))
                box.setEnabled(not self.gesperrt and rolle != rollen.ADMIN)
                box.currentIndexChanged.connect(lambda _i, b=box, ro=rolle, be=bereich: self.recht(ro, be,
                                                                                                    b.currentData()))
                self.rechte.setCellWidget(r, c, box)
        self.schutz_setzen(self.gesperrt)

    def _fertig(self, fehler, text):
        if fehler:
            self.meldung(fehler, fehler=True)
            self.neu_laden()
            return False
        self.meldung(text + " Gilt an allen Plätzen nach dem nächsten Abgleich.")
        self.neu_laden()
        if self.geaendert:
            self.geaendert()
        w = self.window()
        if hasattr(w, "rechte_anwenden"):
            w.rechte_anwenden()
        return True

    def gewaehlt(self):
        r = self.tabelle.currentRow()
        return self.liste[r] if 0 <= r < len(self.liste) else None

    def waehlen(self, kuerzel):
        for r, z in enumerate(self.liste):
            if z["kuerzel"] == kuerzel:
                self.tabelle.selectRow(r)
                return True
        return False

    def _speichern(self, w, alt=None):
        fehler = rollen.benutzer_setzen(self.db, w["kuerzel"], w["name"], w["rollen"],
                                        (alt or {}).get("aktiv", True))
        if not fehler and (w.get("passwort") or w.get("pin")):
            fehler = rollen.zugang_setzen(self.db, self._kuerzel(w["kuerzel"]), w.get("passwort"), w.get("pin"))
        return self._fertig(fehler, f"Benutzer {w['name'] or w['kuerzel']} gespeichert.")

    @staticmethod
    def _kuerzel(k):
        from .teilen import kuerzel_sauber
        return kuerzel_sauber(k)

    def anlegen(self, werte=None):
        if self.gesperrt:
            return False
        if werte is None:
            d = BenutzerDialog(self)
            if d.exec() != QDialog.Accepted:
                return False
            werte = d.werte()
        return self._speichern(werte)

    def bearbeiten(self, werte=None):
        z = self.gewaehlt()
        if self.gesperrt or z is None:
            if z is None:
                self.meldung("Bitte zuerst einen Benutzer wählen.", fehler=True)
            return False
        if werte is None:
            d = BenutzerDialog(self, z)
            if d.exec() != QDialog.Accepted:
                return False
            werte = d.werte()
        return self._speichern(dict(werte, kuerzel=z["kuerzel"]), z)

    def sperren_umschalten(self):
        z = self.gewaehlt()
        if self.gesperrt or z is None or not z["angelegt"]:
            self.meldung("Bitte einen angelegten Benutzer wählen.", fehler=True)
            return False
        fehler = rollen.benutzer_setzen(self.db, z["kuerzel"], z["name"], z["rollen"], not z["aktiv"])
        return self._fertig(fehler, f"{z['name'] or z['kuerzel']} {'gesperrt' if z['aktiv'] else 'entsperrt'}.")

    def entfernen(self):
        z = self.gewaehlt()
        if self.gesperrt or z is None or not z["angelegt"]:
            self.meldung("Bitte einen angelegten Benutzer wählen.", fehler=True)
            return False
        return self._fertig(rollen.entfernen(self.db, z["kuerzel"]), f"{z['name'] or z['kuerzel']} entfernt.")

    def recht(self, rolle, bereich, stufe):
        if self.gesperrt:
            return False
        return self._fertig(rollen.recht_setzen(self.db, rolle, bereich, stufe),
                            f"{rollen.ROLLE_TITEL[rolle]}: {rollen.BEREICH_TITEL[bereich]} "
                            f"{dict(rollen.STUFEN)[stufe] if stufe else 'kein Zugriff'}.")

    def vorgabe(self):
        if self.gesperrt:
            return False
        rollen.vorgabe_wiederherstellen(self.db)
        return self._fertig("", "Rechtetabelle auf die Vorgabe zurückgesetzt.")

    def _pflicht_gesetzt(self, an):
        if self.gesperrt:
            return
        self.db.einstellung_setzen(rollen.PFLICHT, "ja" if an else "nein")
        if self.geaendert:
            self.geaendert()

    def schutz_setzen(self, gesperrt):
        self.gesperrt = bool(gesperrt)
        for b in self.knopf.values():
            b.setEnabled(not gesperrt)
        self.vorgabe_knopf.setEnabled(not gesperrt)
        self.pflicht.setEnabled(not gesperrt)
        for r in range(self.rechte.rowCount()):
            for c in range(self.rechte.columnCount()):
                w = self.rechte.cellWidget(r, c)
                if w is not None:
                    w.setEnabled(not gesperrt and rollen.ROLLEN[r][0] != rollen.ADMIN)


class AnmeldenDialog(QDialog):
    """Benutzer anmelden (beim Start, wenn eingeschaltet, oder Datei → Benutzer anmelden …)."""

    def __init__(self, eltern, db, beim_start=False):
        super().__init__(eltern)
        self.db = db
        self.setWindowTitle("Benutzer anmelden")
        form = QFormLayout(self)
        form.addRow(QLabel("Mit Kürzel und Passwort oder PIN anmelden. Die Rechte kommen aus den Rollen des "
                           "Benutzers."))
        self.kuerzel = QLineEdit(rollen.angemeldet(db))
        self.geheim = QLineEdit()
        self.geheim.setEchoMode(QLineEdit.Password)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #B42318;")
        form.addRow("Kürzel", self.kuerzel)
        form.addRow("Passwort / PIN", self.geheim)
        form.addRow(self.fehler)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Ok).setText("Anmelden")
        k.button(QDialogButtonBox.Cancel).setText("Beenden" if beim_start else "Abbrechen")
        k.accepted.connect(self.pruefen)
        k.rejected.connect(self.reject)
        form.addRow(k)
        (self.geheim if self.kuerzel.text() else self.kuerzel).setFocus()

    def pruefen(self):
        f = rollen.anmelden(self.db, self.kuerzel.text(), self.geheim.text())
        if f:
            self.fehler.setText(f)
            self.geheim.clear()
            return
        self.accept()
