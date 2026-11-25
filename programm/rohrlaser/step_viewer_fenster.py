"""Fenster „STEP-Viewer“ (Master-Auftrag Patrick 24.11.2026, Abschnitte 5–8): eine STEP-Datei ohne Angebot öffnen,
ansehen, messen und prüfen; bei Bedarf ins Angebot übernehmen.

Aufbau: links der Bauteilbaum (Rohre/Profile, Bleche, Dreh-/Frästeile, Normteile, nicht messbar), in der Mitte die
3D-Ansicht aller 3D-Fenster des Programms (ansicht3d mit Leiste: Blick, Darstellung, Perspektive/Orthografisch,
Auswahl von Körper/Fläche/Kante, Messen von Länge, Abstand, Winkel, Durchmesser, Radius, Wandstärke, Schnitt,
Explosion), rechts die Reiter Erkennung, Konturen, Datei und Leistung. Die Werte kommen aus der STEP-Messung
(step_viewer.py), nie aus dem Anzeigenetz; das Netz ist nur Bild.

Bedienung: Datei öffnen (Strg+O, auch Ziehen ins Fenster), Schließen (Strg+W), Analysestufe Standard/Experte,
Gesamtansicht/Einzelteil, Konturen färben nach Art, Rolle (Anfang und Ende verschieden) oder Schneidbarkeit, Konturen je
Rolle ein-/ausblenden, nur rohrlaser-relevante Teile, Hell/Dunkel, Kontur in der Liste, im 3D oder in der Abwicklung
unter dem 3D anklicken = Berechnungsinformationen (Auswahl in allen dreien gleich), Rolle einer Kontur von Hand ändern
(Rechtsklick in der Konturliste), Art von Hand ändern (Rechtsklick im Baum), Übernehmen ins Angebot.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QMainWindow, QMenu, QProgressBar, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import konturrolle as kr
from . import step_viewer as sv
from . import stil
from .ansicht3d import Ansicht3DMitKnoepfen

GESAMT, EINZEL = "Gesamtansicht", "Einzelteil"
DUNKEL = "Dunkel (CAD)"
KONTUR_SPALTEN = ("Nr.", "Art", "Maß [mm]", "Lage", "Schnitt [mm]", "Einstich", "Linie 3D [mm]", "Gegenprobe", "Rolle",
                  "Schneidbarkeit")
SP_ROLLE, SP_STUFE = 8, 9
STUFE_FARBE = {k: f for k, _, f in sv.STUFENFARBEN}


class Abwicklung2D(QWidget):
    """Abwicklung des Mantels neben dem 3D (Master-Auftrag 25.11.2026, Abschnitt 6): Umfang senkrecht, Länge waagrecht,
    jede Kontur in der Farbe des 3D. Klick auf eine Linie wählt die Kontur (Signal gewaehlt mit der Kennung), die
    gewählte Kontur ist dick gezeichnet; nur Anzeige, die Werte kommen aus der Messung (sv.abwicklung_2d)."""
    gewaehlt = Signal(str)

    def __init__(self):
        super().__init__()
        self.abw, self.farben, self.markiert = None, {}, None
        self.setMinimumHeight(150)
        self.setToolTip("Abwicklung: Linie anklicken wählt die Kontur (auch im 3D und in der Liste)")

    def setzen(self, abw, farben=None):
        self.abw, self.farben = abw, dict(farben or {})
        self.setVisible(abw is not None)
        self.update()

    def markieren(self, kennung):
        self.markiert = kennung
        self.update()

    def _rahmen(self):
        r = 8.0
        return r, r, max(self.width() - 2 * r, 1.0), max(self.height() - 2 * r - 14, 1.0)

    def _punkt(self, s, z):
        x0, y0, w, h = self._rahmen()
        return QPointF(x0 + z / self.abw["laenge"] * w, y0 + s / self.abw["umfang"] * h)

    def paintEvent(self, _):
        if not self.abw:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x0, y0, w, h = self._rahmen()
        p.setPen(QPen(QColor(stil.farbe("#7F8C8D")), 1, Qt.DashLine))
        p.drawRect(int(x0), int(y0), int(w), int(h))
        for li in self.abw["linien"]:
            dick = li["kennung"] == self.markiert
            p.setPen(QPen(QColor(self.farben.get(li["kennung"], "#444444")), 3.5 if dick else 1.6))
            pts = li["punkte"]
            paare = zip(pts, pts[1:] + ([] if li["gerade"] else pts[:1]))
            for a, b in paare:
                if not li["gerade"] and abs(a[0] - b[0]) > self.abw["umfang"] / 2:
                    continue
                p.drawLine(self._punkt(*a), self._punkt(*b))
        p.setPen(QColor(stil.farbe("#555555")))
        p.drawText(int(x0), int(y0 + h + 12), f"Abwicklung: Länge {sv._dez(self.abw['laenge'], 1)} mm × Umfang "
                   f"{sv._dez(self.abw['umfang'], 1)} mm (Ende A links)")
        p.end()

    def mousePressEvent(self, e):
        if not self.abw:
            return
        x0, y0, w, h = self._rahmen()
        z = (e.position().x() - x0) / w * self.abw["laenge"]
        s = (e.position().y() - y0) / h * self.abw["umfang"]
        tol = 6.0 / max(w / self.abw["laenge"], h / self.abw["umfang"], 1e-9)       # 6 Pixel
        k = sv.treffer_2d(self.abw, s, z, tol)
        if k:
            self.gewaehlt.emit(k)


def _tabelle_zeilen(baum, zeilen):
    baum.clear()
    for t, w in zeilen:
        it = QTreeWidgetItem([t, str(w)])
        it.setToolTip(1, str(w))
        baum.addTopLevelItem(it)
    baum.resizeColumnToContents(0)


def _zwei_spalten():
    b = QTreeWidget()
    b.setColumnCount(2)
    b.setHeaderLabels(["Merkmal", "Wert"])
    b.setRootIsDecorated(False)
    b.setWordWrap(True)
    b.setAlternatingRowColors(True)
    b.header().setSectionResizeMode(1, QHeaderView.Stretch)
    return b


class StepViewer(QMainWindow):
    """Eigenständiger STEP-Viewer. f = Hauptfenster (Datenbank, Programmordner, Angebote) oder None (nur ansehen,
    Messung über step.messprogramm des Programmordners)."""

    def __init__(self, f=None, pfad=None, parent=None, programmordner=None):
        super().__init__(parent)
        self.f = f
        self.db = getattr(f, "db", None)
        self.programmordner = programmordner or getattr(f, "programmordner", None) or Path(__file__).resolve().parents[1]
        self.setWindowTitle("STEP-Viewer")
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.resize(1500, 900)
        self.setAcceptDrops(True)
        self.mes, self.kopf, self.pfad = None, None, None
        self.ansicht_art, self.gezeigt = GESAMT, None
        self.zeilen = []                   # Konturzeilen des gezeigten Einzelteils
        self.anzeige = {}                  # Leistung der Anzeige (modell_s, bild_s, erstes_bild_s, dreiecke)
        self._pool, self._lauf, self._stand, self._start = None, None, {}, 0.0
        self._abbruch = False
        self._hintergrund_vorher = None
        self._bauen()
        self._warten = QTimer(self)
        self._warten.setInterval(120)
        self._warten.timeout.connect(self._pruefen)
        if pfad:
            self.oeffnen(pfad)
        else:
            self._leer()

    # -------------------------------------------------------------- Aufbau
    def _bauen(self):
        leiste = QToolBar("STEP-Viewer")
        leiste.setMovable(False)
        self.addToolBar(leiste)
        self.aktionen = {}

        def aktion(name, text, fn, taste=None, tipp="", check=False):
            a = QAction(text, self)
            a.setToolTip(tipp or text)
            a.setCheckable(check)
            if taste:
                a.setShortcut(QKeySequence(taste))
            a.triggered.connect(fn)
            leiste.addAction(a)
            self.aktionen[name] = a
            return a
        aktion("oeffnen", "Öffnen …", lambda: self.oeffnen(), QKeySequence.Open, "STEP-, IGES-, TUBX- oder BLM-Datei "
               "öffnen (auch per Ziehen ins Fenster)")
        aktion("schliessen", "Schließen", self.schliessen_datei, "Ctrl+W", "Datei schließen")
        aktion("neu", "Neu messen", lambda: self.oeffnen(self.pfad, neu=True), "F5", "Datei mit der gewählten "
               "Analysestufe neu messen")
        leiste.addSeparator()
        leiste.addWidget(QLabel(" Analysestufe "))
        self.stufe = QComboBox()
        self.stufe.addItems(sv.STUFEN)
        self.stufe.setToolTip("\n".join(sv.STUFE_TEXT[s] for s in sv.STUFEN) + "\nSchnellmodus: beim Import wählen "
                              "(nur Schneidweg und Kalkulationsdaten).")
        self.stufe.currentTextChanged.connect(lambda _: self.oeffnen(self.pfad, neu=True) if self.pfad else None)
        leiste.addWidget(self.stufe)
        leiste.addSeparator()
        aktion("gesamt", GESAMT, lambda: self.zeigen(None), "Ctrl+G", "Alle Körper in Einbaulage", check=True)
        aktion("einzel", EINZEL, lambda: self.zeigen(self._gewaehlt_nr()), "Ctrl+E",
               "Gewählten Körper allein mit Schnitten und Konturen", check=True)
        aktion("farben", "Konturen nach Art", self._farben_anwenden, None, "Bohrungen, Langlöcher, Ausschnitte, "
               "Sonderkonturen, Enden, Gehrungen/Schrägschnitte und Gravuren farbig", check=True)
        self.aktionen["farben"].setChecked(True)
        self.farbe_nach = QComboBox()
        self.farbe_nach.addItems(sv.FARBEN_NACH)
        self.farbe_nach.setCurrentText("Rolle")
        self.farbe_nach.setToolTip("Konturen färben nach Art (Bohrung, Langloch …), nach Rolle (Anfangsschnitt, "
                                   "Innenkontur, Durchbruch, Endeschnitt …; Anfang und Ende verschieden) oder nach "
                                   "Schneidbarkeit (1 eindeutig … 4 nicht sicher)")
        self.farbe_nach.currentTextChanged.connect(lambda _: self._farben_anwenden())
        leiste.addWidget(self.farbe_nach)
        self.rollen_aus = set()
        self.rollen_knopf = QToolButton()
        self.rollen_knopf.setText("Konturen ein/aus")
        self.rollen_knopf.setPopupMode(QToolButton.InstantPopup)
        self.rollen_knopf.setToolTip("Konturen je Rolle im 3D und in der Abwicklung ein- und ausblenden")
        menue = QMenu(self.rollen_knopf)
        self.rollen_aktionen = {}
        for rolle, text, _ in sv.ROLLENFARBEN:
            a = menue.addAction(text)
            a.setCheckable(True)
            a.setChecked(True)
            a.toggled.connect(lambda an, r=rolle: self.rolle_zeigen(r, an))
            self.rollen_aktionen[rolle] = a
        self.rollen_knopf.setMenu(menue)
        leiste.addWidget(self.rollen_knopf)
        aktion("relevant", "Nur Rohrlaser-Teile", lambda: self.zeigen(self.gezeigt), None, "Gesamtansicht: Normteile, "
               "Bleche und Dreh-/Frästeile ausblenden; Einzelteil: Anbauteile und Innenwand ausblenden", check=True)
        aktion("pruefung", "Farben nach Prüfung", lambda: self.zeigen(None), None, "Gesamtansicht nach der "
               "Geometrieprüfung färben: grün korrekt, gelb unsicher, blau reparierbar, rot fehlerhaft, dunkelgrau "
               "ausgeschlossene Normteile (Prüfprotokoll: Körper anklicken)", check=True)
        aktion("dunkel", "Dunkel", self._dunkel, None, "Dunkler Hintergrund der 3D-Ansicht (CAD)", check=True)
        leiste.addSeparator()
        aktion("uebernehmen", "Ins Angebot übernehmen …", self.uebernehmen, None, "Die Datei wie mit „STEP "
               "importieren“ ins geöffnete Angebot übernehmen (ohne geöffnetes Angebot: neues Angebot); die Messung "
               "kommt aus dem Zwischenspeicher")
        aktion("kopieren", "Werte kopieren", self.kopieren, None, "Erkennung und Konturen des gezeigten Körpers in "
               "die Zwischenablage")

        haupt = QSplitter(Qt.Horizontal)
        self.baum = QTreeWidget()
        self.baum.setHeaderLabels(["Bauteil", "Art / Profil", "Länge [mm]"])
        self.baum.setContextMenuPolicy(Qt.CustomContextMenu)
        self.baum.customContextMenuRequested.connect(self._baum_menue)
        self.baum.currentItemChanged.connect(lambda it, _: self._baum_gewaehlt(it))
        self.baum.itemDoubleClicked.connect(lambda it, _: self.zeigen(it.data(0, Qt.UserRole))
                                            if isinstance(it.data(0, Qt.UserRole), int) else None)
        haupt.addWidget(self.baum)
        self.ansicht = Ansicht3DMitKnoepfen()
        self.ansicht.ansicht.angeklickt.connect(self._geklickt)
        wahl = self.ansicht.ansicht.wahl
        wahl.koerper_name = lambda k: sv.name(self.mes.messwerte[sv.teil_nr(k)]) \
            if self.mes and sv.teil_nr(k) is not None and sv.teil_nr(k) < len(self.mes.messwerte) else None
        wahl.koerper_info = lambda k: [f"{t}: {w}" for t, w in sv.erkennung(self.mes.messwerte[sv.teil_nr(k)])[1:6]] \
            if self.mes and sv.teil_nr(k) is not None and sv.teil_nr(k) < len(self.mes.messwerte) else []
        self.ansicht.ansicht.doppelklick_ziel = None
        mitte = QWidget()
        ml = QVBoxLayout(mitte)
        ml.setContentsMargins(0, 0, 0, 0)
        self.titel = QLabel()
        self.titel.setStyleSheet("font-weight: 600; padding: 2px 4px;")
        ml.addWidget(self.titel)
        mitte_teil = QSplitter(Qt.Vertical)
        mitte_teil.addWidget(self.ansicht)
        self.abwicklung = Abwicklung2D()
        self.abwicklung.gewaehlt.connect(self._2d_gewaehlt)
        self.abwicklung.setVisible(False)
        mitte_teil.addWidget(self.abwicklung)
        mitte_teil.setSizes([600, 170])
        ml.addWidget(mitte_teil, 1)
        haupt.addWidget(mitte)
        self.reiter = QTabWidget()
        self.erkennung = _zwei_spalten()
        er = QWidget()
        el = QVBoxLayout(er)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(self.erkennung, 1)
        zl = QHBoxLayout()
        self.art_knopf = QComboBox()
        self.art_knopf.setToolTip("Art des Körpers von Hand korrigieren (wie im Prüfdialog)")
        self.art_knopf.activated.connect(lambda _: self._art_aus_knopf())
        zl.addWidget(QLabel("Art:"))
        zl.addWidget(self.art_knopf, 1)
        el.addLayout(zl)
        self.merken = QCheckBox("Korrekturen für künftige Importe merken")
        self.merken.setChecked(True)
        self.merken.setToolTip("Wie im Prüfdialog: dasselbe Teil (Name und Geometrie) bekommt beim nächsten Import "
                               "diese Art bzw. Normteil-Entscheidung")
        el.addWidget(self.merken)
        self.reiter.addTab(er, "Erkennung")
        ko = QWidget()
        kl = QVBoxLayout(ko)
        kl.setContentsMargins(0, 0, 0, 0)
        self.konturen = QTableWidget(0, len(KONTUR_SPALTEN))
        self.konturen.setHorizontalHeaderLabels(KONTUR_SPALTEN)
        self.konturen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.konturen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.konturen.verticalHeader().setVisible(False)
        self.konturen.itemSelectionChanged.connect(self._kontur_gewaehlt)
        self.konturen.setContextMenuPolicy(Qt.CustomContextMenu)
        self.konturen.customContextMenuRequested.connect(self._kontur_menue)
        kl.addWidget(self.konturen, 2)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        kl.addWidget(self.summe)
        self.kontur_feld = _zwei_spalten()
        kl.addWidget(self.kontur_feld, 1)
        self.reiter.addTab(ko, "Konturen")
        self.datei_feld = _zwei_spalten()
        self.reiter.addTab(self.datei_feld, "Datei")
        self.leistung = _zwei_spalten()
        self.reiter.addTab(self.leistung, "Leistung")
        haupt.addWidget(self.reiter)
        haupt.setSizes([320, 760, 470])
        haupt.setStretchFactor(1, 1)
        self.setCentralWidget(haupt)
        self.balken = QProgressBar()
        self.balken.setMaximumWidth(260)
        self.balken.setVisible(False)
        self.status_text = QLabel()
        self.statusBar().addWidget(self.status_text, 1)
        self.statusBar().addPermanentWidget(self.balken)
        self._knoepfe()

    def _knoepfe(self):
        da = self.mes is not None and bool(self.mes.messwerte)
        for n in ("schliessen", "neu", "gesamt", "einzel", "farben", "relevant", "uebernehmen", "kopieren"):
            self.aktionen[n].setEnabled(da or (n == "schliessen" and self.pfad is not None))
        self.aktionen["uebernehmen"].setEnabled(da and self.f is not None and hasattr(self.f, "angebote"))
        self.aktionen["gesamt"].setChecked(self.ansicht_art == GESAMT)
        self.aktionen["einzel"].setChecked(self.ansicht_art == EINZEL)

    def _leer(self):
        self.titel.setText("Keine Datei geöffnet")
        self.ansicht.setzen(None, "", "STEP-Datei öffnen (Strg+O) oder hierher ziehen. Der Viewer misst sie wie der "
                                     "STEP-Import und zeigt Profil, Konturen, Schneidweg und Normteile.")
        self.status_text.setText("Bereit")
        self._knoepfe()

    # -------------------------------------------------------------- Öffnen und Messen
    def _mess_args(self):
        if self.db is None:
            return None
        try:
            from . import anfrage_vorab
            return anfrage_vorab.vorschau_argumente(self.db)
        except Exception:       # noqa: BLE001 – ohne Einstellungen: Vorgaben der Messung
            return None

    def oeffnen(self, pfad=None, neu=False):
        """Datei öffnen (ohne pfad: Dateidialog) und im Hintergrund messen. True, wenn die Messung startet."""
        from . import step
        if pfad is None:
            start = ""
            if self.db is not None:
                try:
                    from . import step_ablage
                    start = str(step_ablage.start_ordner(self.db))
                except Exception:       # noqa: BLE001
                    start = ""
            pfad, _ = QFileDialog.getOpenFileName(self, "STEP-Datei öffnen", start, step.CAD_FILTER)
            if not pfad:
                return False
        pfad = Path(pfad)
        if not sv.dateiname_ok(pfad) or not pfad.is_file():
            self.status_text.setText(f"{pfad.name}: keine lesbare CAD-Datei (STEP, IGES, TUBX, BLM)")
            return False
        if self._lauf is not None:
            self._abbruch = True
        self._aufraeumen()
        self.pfad = pfad
        self._start = time.perf_counter()
        uhr = time.perf_counter()
        self.kopf = sv.kopf(pfad)
        kopf_s = time.perf_counter() - uhr
        self.setWindowTitle(f"STEP-Viewer – {pfad.name}")
        self.titel.setText(f"{pfad.name} – wird gemessen …")
        _tabelle_zeilen(self.datei_feld, sv.kopf_zeilen(self.kopf))
        self.reiter.setCurrentWidget(self.datei_feld)
        self.baum.clear()
        self.erkennung.clear()
        self.konturen.setRowCount(0)
        self.ansicht.setzen(None, "", "Die Datei wird gemessen (Profil, Konturen, Schneidweg, Netz). Der Kopf der "
                                     "Datei steht schon im Reiter „Datei“.")
        self._stand = dict(kopf_s=kopf_s)
        self._abbruch = False
        befehl = step.messprogramm(self.programmordner)
        stufe = self.stufe.currentText()
        self._pool = self._pool or ThreadPoolExecutor(max_workers=1)
        stand = self._stand
        self._lauf = self._pool.submit(sv.messen, befehl, pfad, self._mess_args(), stufe,
                                       lambda d: stand.update(fortschritt=d), lambda: self._abbruch)
        self.balken.setRange(0, 0)
        self.balken.setVisible(True)
        self._warten.start()
        self._knoepfe()
        return True

    def _pruefen(self):
        if self._lauf is None:
            self._warten.stop()
            return
        if not self._lauf.done():
            d = self._stand.get("fortschritt") or {}
            s = time.perf_counter() - self._start
            if d.get("koerper_n"):
                self.balken.setRange(0, int(d["koerper_n"]))
                self.balken.setValue(int(d.get("koerper") or 0))
            self.status_text.setText(f"Messung läuft … {s:.0f} s" + (f" – {d.get('phase')}" if d.get("phase") else "")
                                     + (f", Körper {d.get('koerper')}/{d.get('koerper_n')}" if d.get("koerper_n")
                                        else ""))
            return
        self._warten.stop()
        lauf, self._lauf = self._lauf, None
        try:
            mes = lauf.result()
        except Exception as x:          # noqa: BLE001
            mes = None
            self.status_text.setText(f"Messung fehlgeschlagen: {x}")
        self.balken.setVisible(False)
        if mes is None:
            return
        if self._abbruch or mes.pfad != self.pfad:
            mes.aufraeumen()
            return
        mes.zeiten["kopf_s"] = self._stand.get("kopf_s")
        self.mes = mes
        self.fertig()

    def warten(self, s=600.0):
        """Tests: bis die Messung fertig ist."""
        if self._lauf is not None:
            self._lauf.result(timeout=s)
            self._pruefen()

    def fertig(self):
        """Messung fertig: Baum füllen, Ansicht zeigen."""
        mes = self.mes
        if mes.fehler:
            self.titel.setText(f"{mes.pfad.name}: {mes.fehler}")
            self.ansicht.setzen(None, "", mes.fehler)
            self.status_text.setText(mes.fehler)
            self._knoepfe()
            return
        self._baum_fuellen()
        n = len(mes.messwerte)
        self.ansicht_art = GESAMT if n > 1 else EINZEL
        self.zeigen(None if n > 1 else 0, erstes=True)
        self.reiter.setCurrentIndex(0)
        self.status_text.setText(f"{n} Körper gemessen in {mes.zeiten.get('messung_s') or 0:.1f} s"
                                 + (" (aus dem Zwischenspeicher)" if mes.zeiten.get("aus_speicher") else "")
                                 + f", Analysestufe {mes.stufe}")
        self._knoepfe()

    def _baum_fuellen(self):
        self.baum.clear()
        gruppen = {}
        for i, m in enumerate(self.mes.messwerte):
            g = sv.gruppe(m)
            if g not in gruppen:
                it = QTreeWidgetItem([g, "", ""])
                it.setFirstColumnSpanned(False)
                gruppen[g] = it
            form = m.get("profil_id_vorschlag") or m.get("profilform") or m.get("bauteiltyp") or ""
            nt = sv.normteil(m) if g == sv.NORMTEIL else None
            if nt:
                form = f"{nt.get('kategorie') or ''} {nt.get('groesse') or ''}".strip()
            kind = QTreeWidgetItem([sv.name(m), form, sv._dez(sv._f(m, "laenge"), 1) if sv._f(m, "laenge") else ""])
            kind.setData(0, Qt.UserRole, i)
            kind.setToolTip(0, m.get("pfad") or sv.name(m))
            st = sv.pruef_status(m)
            if st and st != "korrekt" and g != sv.NORMTEIL:     # Geometrieprüfung: auffällige Körper farbig
                from .importanalyse_dialog import STATUS_FARBE
                kind.setForeground(0, QBrush(stil.farbe(STATUS_FARBE[st])))
                kind.setToolTip(0, f"{m.get('pfad') or sv.name(m)}\nGeometrie {st}")
            gruppen[g].addChild(kind)
        for g in sv.GRUPPEN:
            if g in gruppen:
                it = gruppen[g]
                it.setText(0, f"{g} ({it.childCount()})")
                self.baum.addTopLevelItem(it)
                it.setExpanded(g != sv.NORMTEIL or it.childCount() <= 20)
        for c in range(3):
            self.baum.resizeColumnToContents(c)

    def _gewaehlt_nr(self):
        it = self.baum.currentItem()
        n = it.data(0, Qt.UserRole) if it is not None else None
        if isinstance(n, int):
            return n
        return self.gezeigt if self.gezeigt is not None else (0 if self.mes and self.mes.messwerte else None)

    def _item(self, i):
        for g in range(self.baum.topLevelItemCount()):
            top = self.baum.topLevelItem(g)
            for k in range(top.childCount()):
                if top.child(k).data(0, Qt.UserRole) == i:
                    return top.child(k)
        return None

    # -------------------------------------------------------------- Anzeigen
    def _anzeigen(self, netz, titel, info, erstes=False):
        a = self.ansicht.ansicht
        uhr = time.perf_counter()
        self.ansicht.setzen(netz, titel, info)
        self.anzeige["modell_s"] = time.perf_counter() - uhr
        if a.isVisible():           # nur ein gezeigtes Fenster zeichnet wirklich (sonst kein Messwert)
            uhr = time.perf_counter()
            a.repaint()
            self.anzeige["bild_s"] = time.perf_counter() - uhr
        else:
            self.anzeige.pop("bild_s", None)
        mo = a.modell
        self.anzeige["dreiecke"] = len(mo.dreiecke) if mo is not None and hasattr(mo, "dreiecke") else 0
        if erstes:
            self.anzeige["erstes_bild_s"] = time.perf_counter() - self._start
        _tabelle_zeilen(self.leistung, sv.leistung_zeilen(self.mes, self.anzeige))

    def zeigen(self, i=None, erstes=False):
        """Körper i allein (Einzelteil) bzw. alle (i None, Gesamtansicht) zeigen."""
        mes = self.mes
        if mes is None or not mes.messwerte:
            return
        self.ansicht.ansicht.markieren(())
        self.ansicht.ansicht.kosten_setzen()
        if i is None:
            self.ansicht_art, self.gezeigt = GESAMT, None
            self.abwicklung.setzen(None)
            alle = range(len(mes.messwerte))
            if self.aktionen["relevant"].isChecked():
                alle = [k for k in alle if sv.gruppe(mes.messwerte[k]) == sv.ROHR]
            nach = self.aktionen["pruefung"].isChecked()
            netz, ohne = sv.gesamt_netz(mes, list(alle), nach_pruefung=nach)
            n = len(list(alle))
            info = (f"{n} Körper in Einbaulage, "
                    + ("Farbe nach Geometrieprüfung (grün korrekt, gelb unsicher, blau reparierbar, rot fehlerhaft)"
                       if nach else "gleiche Teile in gleicher Farbe") + ", Normteile dunkelgrau. Körper anklicken "
                    "= Eigenschaften, Doppelklick im Baum = Einzelteil mit Konturen."
                    + (f" {ohne} Körper ohne Einbaulage fehlen." if ohne else ""))
            self._anzeigen(netz, "", info, erstes)
            self.titel.setText(f"{mes.pfad.name} – {GESAMT} ({n} Körper)")
            if len(mes.messwerte) == 1:
                self._erkennung_zeigen(0)
            else:
                _tabelle_zeilen(self.erkennung, sv.uebersicht(mes))
                self.art_knopf.clear()
                self.art_knopf.setEnabled(False)
            self._knoepfe()
            return
        from . import step
        self.ansicht_art, self.gezeigt = EINZEL, i
        m = mes.messwerte[i]
        roh = mes.netz(i)
        netz = sv.mit_konturkennung(roh)
        if netz:
            netz = step.netz_der_art(dict(m, _netz=netz)) or netz
            if self.aktionen["relevant"].isChecked():
                from .ansicht3d import ohne_arten
                netz = ohne_arten(netz, {"AN", "GA", "I"})
        self.zeilen = sv.konturen(m, roh)
        if netz and self.rollen_aus:
            netz = sv.ohne_konturen(netz, sv.ausgeblendet(self.zeilen, self.rollen_aus))
        info = "" if netz else "Für diesen Körper gibt es kein 3D-Netz (nicht messbar oder ältere Messung)."
        self._anzeigen(netz, "", info, erstes)
        self.titel.setText(f"{mes.pfad.name} – {sv.name(m)}")
        self._erkennung_zeigen(i)
        self._konturen_fuellen(m)
        self._farben_anwenden()
        it = self._item(i)
        if it is not None and self.baum.currentItem() is not it:
            self.baum.blockSignals(True)
            self.baum.setCurrentItem(it)
            self.baum.blockSignals(False)
        self._knoepfe()

    def _erkennung_zeigen(self, i):
        m = self.mes.messwerte[i]
        _tabelle_zeilen(self.erkennung, sv.erkennung(m, self.mes.koerper_json(i)))
        self.art_knopf.blockSignals(True)
        self.art_knopf.clear()
        moeglich = sv.arten_moeglich(m)
        self.art_knopf.addItems(moeglich)
        jetzt = sv.gruppe(m)
        if jetzt in moeglich:
            self.art_knopf.setCurrentText(jetzt)
        self.art_knopf.setEnabled(jetzt != sv.FEHLER)
        self.art_knopf.setProperty("nr", i)
        self.art_knopf.blockSignals(False)

    def _konturen_fuellen(self, m):
        t = self.konturen
        t.blockSignals(True)
        t.setRowCount(len(self.zeilen))
        for r, z in enumerate(self.zeilen):
            werte = (str(z["nr"]), z["art"], z["mass"], z["lage"], sv._dez(z["schnitt"], 2) if z["schnitt"] else "",
                     "1" if z["einstich"] else "", sv._dez(z["netz_mm"], 2) if z["netz_mm"] is not None else "",
                     z["gegenprobe"], (z.get("rolle") or "") + (" (Hand)" if z.get("hand") else ""),
                     f"{z['stufe']} {z['stufe_text']}" if z.get("stufe") and z.get("rolle") != "kein Schnitt" else "")
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if c in (0, 4, 5, 6):
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if z["hinweis"]:
                    it.setToolTip(z["hinweis"])
                if c in (SP_ROLLE, SP_STUFE) and z.get("grund"):
                    it.setToolTip(z["grund"])
                if c == SP_STUFE and w:
                    it.setForeground(QBrush(stil.farbe(STUFE_FARBE.get(z["stufe"], stil.TEXT))))
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        t.blockSignals(False)
        s = sv.summen(m, self.zeilen)
        if self.zeilen:
            self.summe.setText(
                f"<b>Gesamtschneidweg {sv._dez(s['schneidweg'], 1)} mm</b> (Messung, wie die Position übernimmt), "
                f"Summe der Konturen {sv._dez(s['summe'], 1)} mm {'✓' if s['gleich'] else '– weicht ab!'}; "
                f"<b>Einstiche {s['einstiche']}</b>; Gegenprobe 3D-Linien {s['gegenprobe_ok']}/{s['gegenprobe_n']} ✓"
                + (f"; Gravur {sv._dez(s['gravur'], 1)} mm" if s["gravur"] else ""))
        else:
            self.summe.setText("Keine Konturen (kein Rohr/Profil oder nicht gemessen).")
        self.kontur_feld.clear()

    def _farben_anwenden(self):
        a = self.ansicht.ansicht
        einzel = self.ansicht_art == EINZEL and bool(self.zeilen) and self.gezeigt is not None
        linien, legende = sv.konturfarben(self.zeilen or [], self.farbe_nach.currentText(), self.rollen_aus) \
            if einzel else ({}, [])
        if einzel:
            m = self.mes.messwerte[self.gezeigt]
            farben2d = linien or sv.konturfarben(self.zeilen, "Rolle", self.rollen_aus)[0]
            self.abwicklung.setzen(sv.abwicklung_2d(m, self.zeilen, self.rollen_aus), farben2d)
        else:
            self.abwicklung.setzen(None)
        if not einzel or not self.aktionen["farben"].isChecked():
            a.kosten_setzen()
            return
        a.kosten_setzen(linien=linien, legende=legende)

    def rolle_zeigen(self, rolle, an):
        """Konturen der Rolle im 3D und in der Abwicklung ein-/ausblenden (Menü „Konturen ein/aus“)."""
        (self.rollen_aus.discard if an else self.rollen_aus.add)(rolle)
        if self.rollen_aktionen[rolle].isChecked() != an:
            self.rollen_aktionen[rolle].blockSignals(True)
            self.rollen_aktionen[rolle].setChecked(an)
            self.rollen_aktionen[rolle].blockSignals(False)
        if self.ansicht_art == EINZEL and self.gezeigt is not None:
            self.zeigen(self.gezeigt)

    def _2d_gewaehlt(self, kennung):
        nr = sv.kontur_nr(kennung)
        if nr is not None:
            self.reiter.setCurrentIndex(1)
            self.kontur_waehlen(nr)

    def _kontur_menue(self, pos):
        r = self.konturen.rowAt(pos.y())
        if not 0 <= r < len(self.zeilen) or self.gezeigt is None:
            return
        z = self.zeilen[r]
        menue = QMenu(self)
        unter = menue.addMenu("Rolle ändern")
        for rolle in kr.ROLLEN:
            a = unter.addAction(rolle)
            a.setCheckable(True)
            a.setChecked(rolle == z.get("rolle"))
            a.triggered.connect(lambda _=False, nr=z["nr"], ro=rolle: self.rolle_aendern(nr, ro))
        if z.get("hand"):
            menue.addAction("Gemessene Rolle wiederherstellen", lambda nr=z["nr"]: self.rolle_aendern(nr, None))
        menue.exec(self.konturen.viewport().mapToGlobal(pos))

    def rolle_aendern(self, nr, rolle):
        """Handkorrektur der Rolle (Rechtsklick in der Konturliste); None = wieder die gemessene. Die Korrektur steht
        in den Messwerten und geht mit „Ins Angebot übernehmen“ in die Position."""
        if self.gezeigt is None or not sv.rolle_setzen(self.mes.messwerte[self.gezeigt], nr, rolle):
            return False
        self.zeigen(self.gezeigt)
        self.kontur_waehlen(nr)
        return True

    def _dunkel(self):
        from . import visualisierung
        jetzt = visualisierung.aktuell()
        if self.aktionen["dunkel"].isChecked():
            if self._hintergrund_vorher is None:
                self._hintergrund_vorher = jetzt.get("ansicht3d_hintergrund")
            visualisierung.setzen(dict(jetzt, ansicht3d_hintergrund=DUNKEL))
        else:
            visualisierung.setzen(dict(jetzt, ansicht3d_hintergrund=self._hintergrund_vorher or visualisierung.VERLAUF))
            self._hintergrund_vorher = None
        self.ansicht.ansicht.update()

    # -------------------------------------------------------------- Auswahl
    def _baum_gewaehlt(self, it):
        n = it.data(0, Qt.UserRole) if it is not None else None
        if not isinstance(n, int) or self.mes is None:
            return
        if self.ansicht_art == EINZEL:
            self.zeigen(n)
        else:
            self._erkennung_zeigen(n)
            wahl = self.ansicht.ansicht.wahl
            if wahl.aus_kennung():          # Körper im 3D hervorheben (Auswahl der 3D-Fenster)
                try:
                    wahl.waehlen([wahl._koerper_el(f"{sv.TEIL}{n}")])
                except (AttributeError, KeyError, TypeError):
                    pass

    def _geklickt(self, treffer):
        kennung = (treffer or {}).get("id")
        nr = sv.kontur_nr(kennung)
        if nr is not None and self.ansicht_art == EINZEL:
            for r, z in enumerate(self.zeilen):
                if z["nr"] == nr:
                    self.reiter.setCurrentIndex(1)
                    self.konturen.selectRow(r)
                    return nr
            return None
        teil = sv.teil_nr(kennung)
        if teil is not None:
            it = self._item(teil)
            if it is not None:
                self.baum.blockSignals(True)
                self.baum.setCurrentItem(it)
                self.baum.blockSignals(False)
            self._erkennung_zeigen(teil)
            self.reiter.setCurrentIndex(0)
            return teil
        return None

    def _kontur_gewaehlt(self):
        r = self.konturen.currentRow()
        a = self.ansicht.ansicht
        if not 0 <= r < len(self.zeilen) or self.gezeigt is None:
            a.markieren(())
            self.kontur_feld.clear()
            return
        z = self.zeilen[r]
        a.markieren([z["kennung"]])
        self.abwicklung.markieren(z["kennung"])
        _tabelle_zeilen(self.kontur_feld, sv.kontur_info(z, self.mes.messwerte[self.gezeigt]))

    def kontur_waehlen(self, nr):
        """Tests/Bedienung: Kontur nr wählen wie ein Klick in der Liste."""
        for r, z in enumerate(self.zeilen):
            if z["nr"] == nr:
                self.konturen.selectRow(r)
                return z
        return None

    # -------------------------------------------------------------- Korrektur von Hand
    def _baum_menue(self, pos):
        it = self.baum.itemAt(pos)
        n = it.data(0, Qt.UserRole) if it is not None else None
        if not isinstance(n, int):
            return
        menue = QMenu(self)
        menue.addAction("Einzelteil zeigen", lambda: self.zeigen(n))
        arten = menue.addMenu("Art ändern")
        for g in sv.arten_moeglich(self.mes.messwerte[n]):
            arten.addAction(g, lambda g=g: self.art_aendern(n, g))
        menue.exec(self.baum.viewport().mapToGlobal(pos))

    def _art_aus_knopf(self):
        n = self.art_knopf.property("nr")
        if isinstance(n, int):
            self.art_aendern(n, self.art_knopf.currentText())

    def art_aendern(self, i, ziel):
        """Art des Körpers i von Hand ändern; mit „merken“ für künftige Importe gemerkt. True, wenn geändert."""
        m = self.mes.messwerte[i]
        if not sv.art_setzen(m, ziel):
            return False
        gemerkt = 0
        if self.merken.isChecked() and self.db is not None and not getattr(self.db, "nur_lesen", False):
            gemerkt = sv.korrekturen_merken(self.db, [m])
        self._baum_fuellen()
        self.zeigen(i if self.ansicht_art == EINZEL else None)
        self._erkennung_zeigen(i)
        self.status_text.setText(f"{sv.name(m)}: Art {sv.gruppe(m)}" + (" (für künftige Importe gemerkt)"
                                                                         if gemerkt else ""))
        return True

    # -------------------------------------------------------------- Übernehmen, Kopieren
    def uebernehmen(self):
        """Ins geöffnete Angebot (wie „STEP importieren“) bzw. als neues Angebot; Korrekturen sind gemerkt."""
        if self.f is None or self.pfad is None:
            return None
        from . import aktionen
        seite = aktionen.angebot(self.f)
        if seite is not None and hasattr(seite, "step_importieren"):
            return seite.step_importieren(dateien=[str(self.pfad)])
        return self.f.angebote.neu_aus_step([str(self.pfad)])

    def kopieren(self):
        if self.mes is None:
            return ""
        i = self.gezeigt if self.gezeigt is not None else 0
        m = self.mes.messwerte[i]
        text = sv.text_kopieren(sv.erkennung(m, self.mes.koerper_json(i)))
        if self.zeilen and self.gezeigt is not None:
            text += "\n\n" + "\t".join(KONTUR_SPALTEN) + "\n" + "\n".join(
                "\t".join((str(z["nr"]), z["art"], z["mass"], z["lage"], sv._dez(z["schnitt"], 2),
                           str(z["einstich"]), "" if z["netz_mm"] is None else sv._dez(z["netz_mm"], 2),
                           z["gegenprobe"])) for z in self.zeilen)
        QApplication.clipboard().setText(text)
        return text

    # -------------------------------------------------------------- Schließen, Ziehen
    def schliessen_datei(self):
        if self._lauf is not None:
            self._abbruch = True
        self._aufraeumen()
        self.pfad, self.kopf = None, None
        self.setWindowTitle("STEP-Viewer")
        self.baum.clear()
        self.erkennung.clear()
        self.konturen.setRowCount(0)
        self.abwicklung.setzen(None)
        self.datei_feld.clear()
        self.leistung.clear()
        self.summe.clear()
        self.balken.setVisible(False)
        self._leer()

    def _aufraeumen(self):
        if self.mes is not None:
            self.mes.aufraeumen()
        self.mes, self.zeilen, self.gezeigt, self.anzeige = None, [], None, {}

    def closeEvent(self, e):
        self._abbruch = True
        self._warten.stop()
        self._aufraeumen()
        if self._hintergrund_vorher is not None:
            self.aktionen["dunkel"].setChecked(False)
            self._dunkel()
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(sv.dateiname_ok(u.toLocalFile()) for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if sv.dateiname_ok(u.toLocalFile()):
                self.oeffnen(u.toLocalFile())
                break


def oeffnen(f=None, pfad=None, parent=None):
    """STEP-Viewer zeigen (nicht modal); bleibt am Hauptfenster hängen (f._step_viewer), damit er offen bleibt."""
    v = StepViewer(f, pfad, parent)
    if f is not None:
        liste = getattr(f, "_step_viewer", None)
        if not isinstance(liste, list):
            liste = []
            try:
                f._step_viewer = liste
            except AttributeError:
                pass
        liste.append(v)
    if not getattr(f, "stumm", False):
        v.show()
    return v
