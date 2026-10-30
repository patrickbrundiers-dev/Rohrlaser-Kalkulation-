"""Oberfläche des Admin-Schutzes (admin_schutz.py): Seiten sperren, Seite „Admin-Schutz“ mit den Häkchen je Bereich
(Frage 1c), Wächter für die Sperre nach 15 Minuten ohne Eingabe (Frage 4b).

Gesperrte Seiten bleiben sichtbar und lesbar (Frage 2a): Einstellungen grau, in Tabellen kein Bearbeiten, ändernde
Knöpfe aus. Ansehen, Suchen, Sortieren und Exportieren bleiben frei.
"""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import admin_schutz

SCHLOSS = "🔒"
NUR_ADMIN = "Nur Admin: diese Seite ändert nur der Admin (Hilfe → Lizenz bzw. „Als Admin freischalten …“)."
# Knöpfe, die auf gesperrten Seiten frei bleiben (nur ansehen oder exportieren)
FREI = {"CSV exportieren", "RP-Querschnitt …", "Als Admin freischalten …", "Admin sperren"}


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


class SchlossLeiste(QWidget):
    """Leiste über den Einstellungen: Schloss mit Admin-Passwort und „Als Admin freischalten …“ oder, freigeschaltet,
    der Hinweis und „Admin sperren“."""

    def __init__(self, bereich):
        from PySide6.QtWidgets import QLineEdit
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
        self.fehler = QLabel()
        self.fehler.setObjectName("fehler")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.fehler)
        lay.addWidget(self.passwort)
        lay.addWidget(self.freischalten)
        lay.addWidget(self.sperren)

    def anzeigen(self, aktiv, admin, seite_gesperrt):
        self.setVisible(aktiv)
        self.passwort.setVisible(not admin)
        self.freischalten.setVisible(not admin)
        self.sperren.setVisible(admin)
        if admin:
            self.fehler.clear()
            self.text.setText(f"Als Admin freigeschaltet: auch die Seiten mit {SCHLOSS} sind änderbar. Sperrt nach "
                              f"{admin_schutz.MINUTEN} Minuten ohne Eingabe.")
            self.setStyleSheet("#schlossleiste { background: #E8F5E9; } #schlossleiste QLabel { color: #1B5E20; }")
        elif seite_gesperrt:
            self.text.setText(f"{SCHLOSS} <b>Nur Admin</b>: diese Seite ändert nur der Admin. Ansehen geht.")
            self.setStyleSheet("#schlossleiste { background: #FFF4D6; } #schlossleiste QLabel { color: #7A5B00; } "
                               "#schlossleiste #fehler { color: #B42318; }")
        else:
            self.text.setText(f"Seiten mit {SCHLOSS} ändert nur der Admin.")
            self.setStyleSheet("#schlossleiste #fehler { color: #B42318; }")
