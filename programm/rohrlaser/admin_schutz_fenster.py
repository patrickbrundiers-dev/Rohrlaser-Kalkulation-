"""Oberfläche des Admin-Schutzes (admin_schutz.py): Seiten sperren, Seite „Admin-Schutz“ mit den Häkchen je Bereich
(Frage 1c), Seite „Arbeitsplätze und Rechte“ (Hauptadmin vergibt Admin-Rechte), Wächter für die Sperre nach 15 Minuten
ohne Eingabe (Frage 4b).

Gesperrte Seiten bleiben sichtbar und lesbar (Frage 2a): Einstellungen grau, in Tabellen kein Bearbeiten, ändernde
Knöpfe aus. Ansehen, Suchen, Sortieren und Exportieren bleiben frei.
"""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QPushButton, QScrollArea, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import admin_schutz

SCHLOSS = "🔒"
NUR_ADMIN = "Nur Admin: diese Seite ändert nur der Admin (Hilfe → Lizenz bzw. „Als Admin freischalten …“)."
# Knöpfe, die auf gesperrten Seiten frei bleiben (nur ansehen oder exportieren)
FREI = {"CSV exportieren", "RP-Querschnitt …", "Als Admin freischalten …", "Admin sperren", "Mein Passwort ändern …"}


def sperren(seite, an):
    """Seite (Stammdaten, Zusatzarbeiten, Zeitvorgaben …) für Nicht-Admins sperren oder wieder freigeben. Merkt sich
    den vorherigen Zustand der Knöpfe und Tabellen, damit Freigeben ihn zurückholt."""
    an = bool(an)
    if getattr(seite, "admin_gesperrt", False) == an:
        return
    seite.admin_gesperrt = an
    modell = getattr(seite, "modell", None)
    if modell is not None:
        modell.admin_gesperrt = an
    for unter in getattr(seite, "teilseiten", ()):
        sperren(unter, an)
    for formular in seite.findChildren(QScrollArea):     # eingebettete Einstellungen (Fracht: Historie)
        if hasattr(formular, "schutz_setzen") and hasattr(formular, "felder"):
            formular.schutz_setzen(set(formular.felder) if an else ())
    if an:
        alt = seite.__dict__.setdefault("_admin_alt", {})
        for k in seite.findChildren(QPushButton):
            if k.text() not in FREI and id(k) not in alt:
                alt[id(k)] = (k, "knopf", k.isEnabled(), k.toolTip())
                k.setEnabled(False)
                k.setToolTip(NUR_ADMIN)
        for v in seite.findChildren(QAbstractItemView):
            if id(v) not in alt:
                alt[id(v)] = (v, "tabelle", v.editTriggers(), None)
                v.setEditTriggers(QAbstractItemView.NoEditTriggers)
    else:
        for w, art, wert, tipp in seite.__dict__.pop("_admin_alt", {}).values():
            if art == "knopf":
                w.setEnabled(wert)
                w.setToolTip(tipp)
            else:
                w.setEditTriggers(wert)


def gesperrt_melden(seite):
    """Für Aktionen (Tastenkürzel, Doppelklick): True und Meldung, wenn die Seite für Nicht-Admins gesperrt ist."""
    if not getattr(seite, "admin_gesperrt", False):
        return False
    meldung = getattr(seite, "meldung", None)
    if callable(meldung):
        meldung(NUR_ADMIN, fehler=True)
    return True


class EingabeWaechter(QObject):
    """Merkt sich jede Tasten- und Mauseingabe für die Sperre nach admin_schutz.MINUTEN ohne Eingabe."""
    ARTEN = (QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.Wheel)

    def __init__(self, sitzung):
        super().__init__()
        self.sitzung = sitzung

    def eventFilter(self, obj, ereignis):
        if ereignis.type() in self.ARTEN:
            self.sitzung.eingabe()
        return False


class AdminSchutzSeite(QScrollArea):
    """Seite „Admin-Schutz“: welche Bereiche nur der Admin ändert (Häkchen, Vorgabe = Vorschlag nach Risiko), dazu der
    Stand der Admin-Vorgaben für alle Arbeitsplätze. Die Seite selbst ist immer geschützt."""
    titel = "Admin-Schutz"
    schluessel = admin_schutz.SEITE_ADMIN

    def __init__(self, db, meldung, geaendert=None):
        super().__init__()
        self.db, self.meldung, self.geaendert = db, meldung, geaendert
        self.setWidgetResizable(True)
        innen = QWidget()
        lay = QVBoxLayout(innen)
        text = QLabel("Häkchen = nur der Admin ändert diesen Bereich. Andere sehen die Werte, können sie aber nicht "
                      "ändern. Die Werte der geschützten Bereiche gelten an jedem Arbeitsplatz: sie gehen als "
                      "Admin-Vorgaben über den gemeinsamen Ordner an alle Plätze, abweichende Werte werden dort "
                      "wiederhergestellt. Ohne Admin-Passwort (Seite Firma) ist nichts gesperrt.")
        text.setWordWrap(True)
        text.setStyleSheet("color: #5F6B7A;")
        lay.addWidget(text)
        self.stand = QLabel()
        self.stand.setWordWrap(True)
        lay.addWidget(self.stand)
        self.haken = {}
        for art, titel in (("einstellungen", "Einstellungen"), ("stammdaten", "Stammdaten")):
            box = QGroupBox(titel)
            gitter = QGridLayout(box)
            liste = [b for b in admin_schutz.bereiche() if b[2] == art]
            halb = (len(liste) + 1) // 2
            for i, (k, t, _) in enumerate(liste):
                h = QCheckBox(t)
                h.toggled.connect(lambda _an, k=k: self._speichern())
                self.haken[k] = h
                gitter.addWidget(h, i % halb, i // halb)
            lay.addWidget(box)
        zeile = QHBoxLayout()
        self.vorschlag = QPushButton("Vorschlag wiederherstellen")
        self.vorschlag.setToolTip("Häkchen wie im Vorschlag nach Risiko: Preise, Gewinn, Kosten, Maschinen, "
                                  "Schneiddaten, Firma, Funktionen …")
        self.vorschlag.clicked.connect(self.vorschlag_setzen)
        zeile.addWidget(self.vorschlag)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        lay.addStretch(1)
        self.setWidget(innen)
        self.neu_laden()

    def neu_laden(self):
        self._laden = True
        schutz = admin_schutz.geschuetzt_liste(self.db)
        for k, h in self.haken.items():
            h.setChecked(k in schutz)
        self._laden = False
        st = self.db.einstellung(admin_schutz.STAND) or {}
        if not admin_schutz.aktiv(self.db):
            self.stand.setText("<b>Kein Admin-Passwort gesetzt</b>: alle Seiten sind frei.")
        elif st.get("stand"):
            von = f" von {st['von']}" if st.get("von") else ""
            self.stand.setText(f"Admin-Vorgaben zuletzt verteilt bzw. übernommen: {st['stand'].replace('T', ' ')}"
                               f"{von}.")
        else:
            self.stand.setText("Admin-Vorgaben noch nicht verteilt (beim nächsten Abgleich als Admin).")

    def _speichern(self):
        if getattr(self, "_laden", False) or getattr(self, "admin_gesperrt", False):
            return
        neu = sorted(k for k, h in self.haken.items() if h.isChecked())
        self.db.einstellung_setzen(admin_schutz.ADMIN_SEITEN, neu)
        self.meldung("Admin-Schutz gespeichert.")
        if self.geaendert:
            self.geaendert()

    def vorschlag_setzen(self):
        if getattr(self, "admin_gesperrt", False):
            return
        self.db.einstellung_setzen(admin_schutz.ADMIN_SEITEN, sorted(admin_schutz.VORGABE))
        self.neu_laden()
        self.meldung("Admin-Schutz: Vorschlag wiederhergestellt.")
        if self.geaendert:
            self.geaendert()

    def schutz_setzen(self, gesperrt):
        self.admin_gesperrt = bool(gesperrt)
        for h in self.haken.values():
            h.setEnabled(not gesperrt)
        self.vorschlag.setEnabled(not gesperrt)


AMPEL = {"gruen": "#2E7D32", "gelb": "#7A5B00", "rot": "#B42318"}


def zeit_text(iso):
    """2026-10-30T08:15:00 -> 30.10.2026 08:15"""
    if not iso or len(iso) < 16:
        return iso or ""
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]} {iso[11:16]}"


def passwort_fragen(eltern, titel, text):
    """Passwort zweimal abfragen. Ergebnis: Passwort oder None (abgebrochen, ungleich)."""
    a, ok = QInputDialog.getText(eltern, titel, text, QLineEdit.Password)
    if not ok or not a:
        return None
    b, ok = QInputDialog.getText(eltern, titel, "Bitte noch einmal eingeben:", QLineEdit.Password)
    if not ok:
        return None
    if a != b:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(eltern, titel, "Die beiden Eingaben sind nicht gleich.")
        return None
    return a


class PlaetzeSeite(QScrollArea):
    """Seite „Arbeitsplätze und Rechte“ (nur Hauptadmin): alle Mitarbeiter aus dem gemeinsamen Ordner mit Name und
    Kürzel vom ersten Start, Rechner, Lizenz (Ampel), Version und zuletzt gesehen; je Zeile das Recht Mitarbeiter, Admin
    oder Admin gesperrt. Darunter der Verlauf: welcher Admin wann was geändert hat."""
    titel = "Arbeitsplätze und Rechte"
    schluessel = admin_schutz.SEITE_PLAETZE
    SPALTEN = ("Name", "Kürzel", "Rechner", "Lizenz", "Version", "Zuletzt da", "Recht")

    def __init__(self, db, meldung, geaendert=None):
        super().__init__()
        self.db, self.meldung, self.geaendert = db, meldung, geaendert
        self.stumm = False              # Tests: Startpasswort ohne Dialog (recht_waehlen(…, startpasswort=…))
        self.admin_gesperrt = False
        self.setWidgetResizable(True)
        innen = QWidget()
        lay = QVBoxLayout(innen)
        text = QLabel("Jeder Arbeitsplatz meldet sich hier über den gemeinsamen Ordner mit Name und Kürzel (vom ersten "
                      "Start). <b>Admin</b>: ändert alle Seiten mit 🔒 an jedem Arbeitsplatz mit gültiger Lizenz, mit "
                      "eigenem Passwort (Startpasswort vergibt der Hauptadmin, beim ersten Freischalten ändern). Admin-"
                      "Schutz und Rechte ändert nur der Hauptadmin (Passwort der Admin-Lizenz). <b>Admin gesperrt</b>: "
                      "kann sich nicht mehr freischalten. Lizenzen selbst sperrt weiter das Lizenz-Werkzeug.")
        text.setWordWrap(True)
        text.setStyleSheet("color: #5F6B7A;")
        lay.addWidget(text)
        self.tabelle = QTableWidget(0, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabelle.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tabelle.setMinimumHeight(220)
        lay.addWidget(self.tabelle)
        zeile = QHBoxLayout()
        self.start_knopf = QPushButton("Neues Startpasswort …")
        self.start_knopf.setToolTip("Für den gewählten Admin ein neues Startpasswort vergeben (Passwort vergessen).")
        self.start_knopf.clicked.connect(lambda: self.startpasswort())
        zeile.addWidget(self.start_knopf)
        self.leer = QLabel()
        self.leer.setStyleSheet("color: #5F6B7A;")
        zeile.addWidget(self.leer, 1)
        lay.addLayout(zeile)
        lay.addWidget(QLabel("<b>Verlauf</b>: wer hat welche Admin-Vorgaben geändert"))
        self.verlauf = QTableWidget(0, 3)
        self.verlauf.setHorizontalHeaderLabels(("Zeit", "Wer", "Was"))
        self.verlauf.verticalHeader().setVisible(False)
        self.verlauf.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verlauf.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.verlauf.setMinimumHeight(160)
        lay.addWidget(self.verlauf, 1)
        self.setWidget(innen)
        self.neu_laden()

    def neu_laden(self):
        self.liste = admin_schutz.plaetze(self.db)
        self.wahl = {}
        t = self.tabelle
        t.setRowCount(len(self.liste))
        for r, p in enumerate(self.liste):
            lt, ampel = admin_schutz.lizenz_text(p["lizenz"])
            haupt = p["lizenz"].get("stufe") == "admin"
            zuletzt = "dieser Platz" if p["ich"] else zeit_text(p["stand"])
            for c, w in enumerate((p["name"] or "–", p["kuerzel"], p["rechner"], lt, p["version"], zuletzt)):
                it = QTableWidgetItem(w)
                if c == 3 and ampel:
                    from PySide6.QtGui import QColor
                    it.setForeground(QColor(AMPEL[ampel]))
                t.setItem(r, c, it)
            if haupt:
                t.setCellWidget(r, 6, None)
                t.setItem(r, 6, QTableWidgetItem(admin_schutz.HAUPTADMIN))
                continue
            box = QComboBox()
            for k, titel in admin_schutz.RECHTE:
                box.addItem(titel, k)
            box.setCurrentIndex([k for k, _ in admin_schutz.RECHTE].index(p["recht"]))
            box.setEnabled(not self.admin_gesperrt)
            box.currentIndexChanged.connect(lambda _i, b=box, k=p["kuerzel"]: self._gewaehlt(k, b))
            self.wahl[p["kuerzel"]] = box
            t.setCellWidget(r, 6, box)
        t.resizeColumnsToContents()
        self.leer.setText("" if self.liste else "Noch kein Arbeitsplatz im gemeinsamen Ordner (Datei → Benutzer und "
                                                "gemeinsamer Ordner …).")
        v = list(reversed(admin_schutz.verlauf(self.db)))
        self.verlauf.setRowCount(len(v))
        for r, e in enumerate(v):
            for c, w in enumerate((zeit_text(e.get("zeit")), e.get("wer") or "", e.get("was") or "")):
                self.verlauf.setItem(r, c, QTableWidgetItem(w))
        self.verlauf.resizeColumnToContents(0)
        self.verlauf.resizeColumnToContents(1)
        self.start_knopf.setEnabled(not self.admin_gesperrt)

    def _name(self, kuerzel):
        return next((p["name"] for p in self.liste if p["kuerzel"] == kuerzel), "")

    def _gewaehlt(self, kuerzel, box):
        if not self.recht_waehlen(kuerzel, box.currentData()):
            self.neu_laden()                # abgebrochen: alte Auswahl zurück

    def recht_waehlen(self, kuerzel, neu, startpasswort=None):
        """Recht vergeben; für einen neuen Admin fragt die Seite das Startpasswort. Ergebnis: übernommen ja/nein."""
        if self.admin_gesperrt:
            return False
        if neu == admin_schutz.ADMIN and not (admin_schutz.admins(self.db).get(kuerzel) or {}).get("hash") \
                and startpasswort is None and not self.stumm:
            startpasswort = passwort_fragen(self, "Startpasswort", f"Startpasswort für {self._name(kuerzel) or kuerzel} "
                                                                   "(mindestens 6 Zeichen; der Admin ändert es beim "
                                                                   "ersten Freischalten):")
            if startpasswort is None:
                return False
        fehler = admin_schutz.recht_setzen(self.db, kuerzel, neu, self._name(kuerzel), startpasswort)
        if fehler:
            self.meldung(fehler, fehler=True)
            return False
        self.meldung(f"{self._name(kuerzel) or kuerzel}: {dict(admin_schutz.RECHTE)[neu]}. Gilt an allen Plätzen nach "
                     "dem nächsten Abgleich.")
        self.neu_laden()
        if self.geaendert:
            self.geaendert()
        return True

    def startpasswort(self, kuerzel=None, startpasswort=None):
        """Neues Startpasswort für einen Admin (Frage 4a: Passwort vergessen)."""
        if self.admin_gesperrt:
            return False
        if kuerzel is None:
            r = self.tabelle.currentRow()
            kuerzel = self.liste[r]["kuerzel"] if 0 <= r < len(self.liste) else None
        e = admin_schutz.admins(self.db).get(kuerzel) if kuerzel else None
        if not e:
            self.meldung("Bitte zuerst einen Admin in der Liste wählen.", fehler=True)
            return False
        if startpasswort is None:
            startpasswort = passwort_fragen(self, "Neues Startpasswort",
                                            f"Neues Startpasswort für {e.get('name') or kuerzel}:")
            if startpasswort is None:
                return False
        fehler = admin_schutz.recht_setzen(self.db, kuerzel, e.get("recht"), e.get("name"), startpasswort)
        if fehler:
            self.meldung(fehler, fehler=True)
            return False
        self.meldung(f"Neues Startpasswort für {e.get('name') or kuerzel} vergeben.")
        if self.geaendert:
            self.geaendert()
        return True

    def schutz_setzen(self, gesperrt):
        self.admin_gesperrt = bool(gesperrt)
        for b in self.wahl.values():
            b.setEnabled(not gesperrt)
        self.start_knopf.setEnabled(not gesperrt)


class SchlossLeiste(QWidget):
    """Leiste über den Einstellungen: Schloss mit Admin-Passwort und „Als Admin freischalten …“ oder, freigeschaltet,
    der Hinweis und „Admin sperren“."""

    def __init__(self, bereich):
        super().__init__()
        self.bereich = bereich
        self.setObjectName("schlossleiste")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.passwort = QLineEdit()
        self.passwort.setEchoMode(QLineEdit.Password)
        self.passwort.setPlaceholderText("Admin-Passwort")
        self.passwort.setMaximumWidth(200)
        self.passwort.returnPressed.connect(lambda: bereich.oeffnen())
        self.freischalten = QPushButton("Als Admin freischalten …")
        self.freischalten.clicked.connect(lambda: bereich.oeffnen())
        self.sperren = QPushButton("Admin sperren")
        self.sperren.clicked.connect(lambda: bereich.sperren())
        self.mein = QPushButton("Mein Passwort ändern …")
        self.mein.clicked.connect(lambda: bereich.mein_passwort())
        self.fehler = QLabel()
        self.fehler.setObjectName("fehler")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.fehler)
        lay.addWidget(self.passwort)
        lay.addWidget(self.freischalten)
        lay.addWidget(self.mein)
        lay.addWidget(self.sperren)

    def anzeigen(self, aktiv, admin, seite_gesperrt, wer=""):
        """wer: '' (nicht freigeschaltet), admin_schutz.HAUPTADMIN oder der Name des Admins."""
        self.setVisible(aktiv)
        self.passwort.setVisible(not admin)
        self.freischalten.setVisible(not admin)
        self.sperren.setVisible(admin)
        self.mein.setVisible(admin and bool(wer) and wer != admin_schutz.HAUPTADMIN)
        if admin and seite_gesperrt:            # weiterer Admin auf einer Seite des Hauptadmins
            self.fehler.clear()
            self.text.setText(f"Als Admin {wer} freigeschaltet. {SCHLOSS} <b>Nur Hauptadmin</b>: Admin-Schutz und "
                              "Rechte ändert nur der Hauptadmin.")
            self.setStyleSheet("#schlossleiste { background: #FFF4D6; } #schlossleiste QLabel { color: #7A5B00; }")
        elif admin:
            self.fehler.clear()
            als = "Als Hauptadmin" if wer == admin_schutz.HAUPTADMIN else f"Als Admin {wer}" if wer else "Als Admin"
            self.text.setText(f"{als} freigeschaltet: auch die Seiten mit {SCHLOSS} sind änderbar. Sperrt nach "
                              f"{admin_schutz.MINUTEN} Minuten ohne Eingabe.")
            self.setStyleSheet("#schlossleiste { background: #E8F5E9; } #schlossleiste QLabel { color: #2E7D32; }")
        elif seite_gesperrt:
            self.text.setText(f"{SCHLOSS} <b>Nur Admin</b>: diese Seite ändert nur der Admin. Ansehen geht. Admins "
                              "schalten sich mit ihrem eigenen Passwort frei.")
            self.setStyleSheet("#schlossleiste { background: #FFF4D6; } #schlossleiste QLabel { color: #7A5B00; } "
                               "#schlossleiste #fehler { color: #B42318; }")
        else:
            self.text.setText(f"Seiten mit {SCHLOSS} ändert nur der Admin.")
            self.setStyleSheet("#schlossleiste #fehler { color: #B42318; }")
