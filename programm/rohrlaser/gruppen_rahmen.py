"""Gleicher Aufbau für alle Editoren (Vorschlag N1/E4, Patrick 07.11.2026): die Schweißbaugruppe und „Satz in 3D“
bekommen denselben Rahmen wie Rohr- und Blech-Editor (teile_editor.EditorRahmen):

    oben    Menüband mit den Reitern Konstruktion, Ansicht, Ausgabe
    links   Struktur (Strukturbaum der Baugruppe bzw. Teile des Satzes)
    Mitte   3D-Ansicht, darunter die Eingaben (Reiter, aufklappbar wie die Tabelle im Rohr-Editor)
    rechts  Ergebnis (Kosten, Zeiten, Hinweise)
    unten   Kennzahl-Kacheln, Messergebnis und Zähler der Prüfmeldungen (Klick klappt die Liste auf)
    Fuß     nur noch die Knöpfe zum Übernehmen bzw. Abbrechen (rechts), wie in allen Editoren

Die Fenster bauen ihre Widgets wie bisher; der Rahmen hängt sie nur um (Signale, Tests und Tastenkürzel bleiben).
Knöpfe der alten Fußleiste und der 3D-Leiste ziehen ins Menüband.
"""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (QAbstractButton, QCheckBox, QComboBox, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QSplitter, QToolButton, QVBoxLayout, QWidget)

from . import dfm, stil
from .editor_ergebnis import Ergebnisleiste
from .menueband import Menueband

# Knöpfe der 3D-Leiste (baugruppe_ansicht.BaugruppenAnsicht) -> Gruppe im Reiter Ansicht bzw. Konstruktion
ANSICHT_GRUPPEN = (
    ("Blickrichtung", ("Blick",)),
    ("3D-Darstellung", ("Nur Gewähltes", "Nähte")),
    ("Messen", ("Messen", "Winkel", "Maße löschen")),
    ("Montage", ("Montage",)),
)
WERKZEUG_GRUPPE = "Auswahl im 3D"        # übrige Knöpfe der 3D-Leiste (Längsnaht wählen …): Reiter Konstruktion
BAND_STIL = """
QFrame#bandgruppe QPushButton, QFrame#bandgruppe QToolButton#altknopf { border: none; padding: 2px 6px;
    text-align: left; background: transparent; }
QFrame#bandgruppe QPushButton:hover, QFrame#bandgruppe QToolButton#altknopf:hover { background: #EEF4FB;
    border-radius: 4px; }
QFrame#bandgruppe QPushButton:checked, QFrame#bandgruppe QToolButton#altknopf:checked { background: #DDEBF7;
    border-radius: 4px; }
QFrame#bandgruppe QPushButton:disabled { color: #9AA3AE; }
"""


def stufe(text):
    """Stufe einer Meldung aus ihrem Anfang (FEHLER/WARNUNG/HINWEIS); ohne Kennung: Warnung."""
    t = str(text or "").lstrip()
    for s in (dfm.FEHLER, dfm.WARNUNG, dfm.HINWEIS):
        if t.upper().startswith(s):
            return s
    return dfm.WARNUNG


class GruppenRahmen(QObject):
    """d: Dialog mit layout(); alt: Widget im Layout, an dessen Stelle der Rahmen tritt (wird ausgeblendet);
    links: Struktur; reiter: Eingaben (QTabWidget) unter der 3D-Ansicht; rechts: Widgets der Ergebnisspalte;
    ansicht3d: 3D-Ansicht oder None (kommt später mit ansicht_einhaengen); fuss: Layout der Fußleiste, deren Knöpfe
    (außer OK/Abbrechen) ins Band ziehen. kacheln() -> [(Titel, Wert, Tipp)], meldungen() -> [Text]; Klick auf
    eine Meldung ruft springen(text); nachher() läuft nach jedem Auffrischen (Baum nachziehen). Danach
    d.rahmen = self."""

    def __init__(self, d, alt, links, reiter, rechts, ansicht3d=None, kacheln=None, meldungen=None, springen=None,
                 nachher=None):
        super().__init__(d)
        self.d, self.reiter, self._nachher = d, reiter, nachher
        self._kacheln, self._meldungen, self._springen = kacheln, meldungen, springen
        self.ansicht3d = None
        self.gruppen = {}
        self.band = Menueband()
        self.band.setStyleSheet(self.band.styleSheet() + stil.umsetzen(BAND_STIL))
        for n in ("Konstruktion", "Ansicht", "Ausgabe"):
            self.band.reiter(n)
        self.gruppe("Konstruktion", "Bearbeiten")       # wie im Rohr-/Blech-Editor zuerst (Zurücksetzen)
        haupt = d.layout()
        stelle = haupt.indexOf(alt)
        haupt.removeWidget(alt)
        if alt is not reiter and alt is not links:
            alt.hide()
        # Mitte: 3D oben, Eingaben darunter
        self.mitte_oben = QWidget()
        self._mitte_lay = QVBoxLayout(self.mitte_oben)
        self._mitte_lay.setContentsMargins(0, 0, 0, 0)
        self.platzhalter = QLabel("Keine 3D-Daten: die Teile kommen nicht aus einem STEP-Import.")
        self.platzhalter.setAlignment(Qt.AlignCenter)
        self.platzhalter.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        self._mitte_lay.addWidget(self.platzhalter, 1)
        self.mitte = QSplitter(Qt.Vertical)
        self.mitte.setChildrenCollapsible(True)
        self.mitte.addWidget(self.mitte_oben)
        unten_rollen = QScrollArea()        # Reiter mit hohen Tabellen: rollen statt das Fenster zu strecken
        unten_rollen.setWidgetResizable(True)
        unten_rollen.setFrameShape(QScrollArea.NoFrame)
        unten_rollen.setWidget(reiter)
        reiter.show()
        self.tabelle_bereich = unten_rollen
        self.mitte.addWidget(unten_rollen)
        self.mitte.setStretchFactor(0, 3)
        self.mitte.setStretchFactor(1, 2)
        # links Struktur, rechts Ergebnis (rollt)
        links.setMinimumWidth(220)
        rechts_w = QWidget()
        rl = QVBoxLayout(rechts_w)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("<b>Ergebnis</b>"))
        for w in rechts:
            if isinstance(w, QLabel):
                w.setWordWrap(True)
            for x in w.findChildren(QLabel):
                x.setWordWrap(True)
            rl.addWidget(w)
        rl.addStretch(1)
        rollen = QScrollArea()
        rollen.setWidgetResizable(True)
        rollen.setFrameShape(QScrollArea.NoFrame)
        rollen.setWidget(rechts_w)
        rollen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rollen.setMinimumWidth(240)
        self.rechts = rollen
        self.waagerecht = QSplitter(Qt.Horizontal)
        self.waagerecht.setChildrenCollapsible(False)
        for w in (links, self.mitte, rollen):
            self.waagerecht.addWidget(w)
        self.waagerecht.setStretchFactor(0, 0)
        self.waagerecht.setStretchFactor(1, 1)
        self.waagerecht.setStretchFactor(2, 0)
        breite = max(1000, d.width())
        self.waagerecht.setSizes([250, breite - 250 - 290, 290])
        hoehe = max(500, d.height() - 260)
        self.mitte.setSizes([int(hoehe * 0.5), hoehe - int(hoehe * 0.5)])
        # unten: Prüfmeldungen (aufklappbar) und Ergebnisleiste
        self.meldungen_liste = QListWidget()
        self.meldungen_liste.setWordWrap(True)
        self.meldungen_liste.setToolTip("Prüfmeldungen der Rechnung; Klick springt zur Zeile")
        self.meldungen_liste.itemClicked.connect(self._meldung_geklickt)
        self.meldung_titel = QLabel()
        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addWidget(self.meldung_titel)
        ul.addWidget(self.meldungen_liste, 1)
        unten.setVisible(False)
        self.meldung_bereich = unten
        self.senkrecht = QSplitter(Qt.Vertical)
        self.senkrecht.addWidget(self.waagerecht)
        self.senkrecht.addWidget(unten)
        self.senkrecht.setStretchFactor(0, 1)
        self.senkrecht.setStretchFactor(1, 0)
        self.senkrecht.setSizes([max(400, d.height() - 140), 110])
        self.leiste_unten = Ergebnisleiste()
        self.leiste_unten.aufgeklappt.connect(unten.setVisible)
        haupt.insertWidget(stelle, self.leiste_unten)
        haupt.insertWidget(stelle, self.senkrecht, 1)
        haupt.insertWidget(0, self.band)
        self._uhr = QTimer(self)
        self._uhr.setSingleShot(True)
        self._uhr.setInterval(150)
        self._uhr.timeout.connect(self.auffrischen)
        d.rahmen = self
        if ansicht3d is not None:
            self.ansicht_einhaengen(ansicht3d)
        self.platz_3d()
        d.installEventFilter(self)          # nach dem Zeigen (gemerkte Teiler sind dann gesetzt) noch einmal

    PLATZHALTER_HOEHE = 30      # ohne 3D-Daten bleibt oben nur die Hinweiszeile, die Eingaben bekommen die Höhe

    def eventFilter(self, obj, e):
        if obj is self.d and e.type() == QEvent.Show:
            QTimer.singleShot(0, self.platz_3d)
        return False

    def platz_3d(self):
        """Plan Schweißbaugruppe 10.11.2026, L2: ohne 3D-Daten klappt die leere 3D-Fläche bis auf die Hinweiszeile
        zu und die Eingaben (Tabellen) bekommen die Höhe; mit 3D-Daten ist sie nie zugeklappt (z. B. nach gemerkten
        Teilern aus einer Baugruppe ohne STEP)."""
        try:
            oben, unten = self.mitte.sizes()
        except (RuntimeError, ValueError):      # Fenster schon zerstört
            return
        gesamt = max(oben + unten, 200)
        if self.ansicht3d is None:
            if oben != self.PLATZHALTER_HOEHE:
                self.mitte.setSizes([self.PLATZHALTER_HOEHE, gesamt - self.PLATZHALTER_HOEHE])
        elif oben < 80:
            self.mitte.setSizes([gesamt // 2, gesamt - gesamt // 2])

    # -------------------------------------------------------------- Band
    def gruppe(self, reiter, titel):
        g = self.band.reiter(reiter).gruppen.get(titel) or self.band.reiter(reiter).gruppe(titel)
        self.gruppen[titel] = g
        return g

    def einsetzen(self, reiter, titel, *widgets):
        """Vorhandene Knöpfe/Felder (z. B. der alten Fußleiste) in eine Gruppe des Bands umhängen: kleine Knöpfe
        zu dritt übereinander, Auswahlfelder als eigene Spalte."""
        g = self.gruppe(reiter, titel)
        for w in widgets:
            if w is None:
                continue
            if isinstance(w, (QAbstractButton, QCheckBox)) and not isinstance(w, QComboBox):
                if isinstance(w, QToolButton):
                    w.setObjectName("altknopf")
                    w.setAutoRaise(True)
                if isinstance(w, QPushButton):
                    w.setFlat(True)
                g._raster.addWidget(w, g._zeile, g._spalte, Qt.AlignLeft)
                g.knoepfe[w.text()] = w
                g._zeile += 1
                if g._zeile == 3:
                    g._spalte, g._zeile = g._spalte + 1, 0
            else:
                g.widget(w)
        return g

    def fuss_leeren(self, fuss, ziele):
        """Knöpfe der Fußleiste (QHBoxLayout) nach ziele {Widget: (Reiter, Gruppe)} ins Band; der Rest bleibt."""
        for w, (reiter, titel) in ziele.items():
            if w is not None:
                fuss.removeWidget(w)
                self.einsetzen(reiter, titel, w)

    def ansicht_einhaengen(self, a3):
        """3D-Ansicht (BaugruppenAnsicht) in die Mitte; ihre Leiste wandert ins Band (Reiter Ansicht), das
        Messergebnis in die Ergebnisleiste."""
        if self.ansicht3d is a3:
            return
        self.ansicht3d = a3
        self.platzhalter.hide()
        self._mitte_lay.insertWidget(0, a3, 1)
        self.platz_3d()
        leiste = getattr(a3, "_leiste", None)
        if leiste is None:
            return
        knoepfe = {}
        for i in range(leiste.count()):
            w = leiste.itemAt(i).widget()
            if w is not None and w is not getattr(a3, "mass", None):
                knoepfe[w] = w.text() if hasattr(w, "text") else ""
        vergeben = set()
        if getattr(a3, "darstellung", None) is not None:
            self.einsetzen("Ansicht", "3D-Darstellung", a3.darstellung)
            vergeben.add(a3.darstellung)
        for titel, texte in ANSICHT_GRUPPEN:
            ws = [w for w, t in knoepfe.items() if t in texte and w not in vergeben]
            if ws:
                self.einsetzen("Ansicht", titel, *ws)
                vergeben.update(ws)
        rest = [w for w in knoepfe if w not in vergeben]
        if rest:
            self.einsetzen("Konstruktion", WERKZEUG_GRUPPE, *rest)
        mass = getattr(a3, "mass", None)
        if mass is not None:
            self.leiste_unten.mass.hide()
            self.leiste_unten._lay.insertWidget(1, mass, 1)
        leiste.parentWidget().hide()

    # -------------------------------------------------------------- Ergebnis und Prüfmeldungen
    def spaeter(self):
        """Nach einer Eingabe: Kacheln und Meldungen kurz danach neu (mehrere Eingaben = ein Durchlauf)."""
        self._uhr.start()

    def auffrischen(self):
        if self._kacheln is not None:
            self.leiste_unten.kacheln_setzen(self._kacheln())
        texte = [t for t in (self._meldungen() if self._meldungen is not None else ()) if t]
        self.meldungen_liste.clear()
        farben = {dfm.FEHLER: stil.ROT, dfm.WARNUNG: stil.GELB_TEXT, dfm.HINWEIS: stil.TEXT_GRAU}
        stufen = []
        for t in texte:
            s = stufe(t)
            stufen.append(s)
            it = QListWidgetItem(t)
            it.setForeground(stil.farbe(farben[s]))
            it.setData(Qt.UserRole, t)
            self.meldungen_liste.addItem(it)
        self.meldung_titel.setText(f"<b>Prüfmeldungen</b> ({len(texte)})" if texte else "<b>Prüfmeldungen</b>")
        self.leiste_unten.zaehler_setzen(stufen)
        if self._nachher is not None:
            self._nachher()

    def _meldung_geklickt(self, it):
        if self._springen is not None and it is not None:
            self._springen(it.data(Qt.UserRole))
