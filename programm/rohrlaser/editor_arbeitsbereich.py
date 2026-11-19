"""Arbeitsbereich des Teile-Editors wie in einem CAD-Programm (Plan 3D-Editor modernisieren 19.11.2026, Phase 3).

Ergänzt den Rahmen (teile_editor.EditorRahmen) um, ohne die Rechnung anzufassen:
- A8 Werkzeugleiste direkt über dem 3D: Auswahl, Verschieben, Messen, Winkel, Querschnitt, Eckpunkte, Bohrung,
  Ausschnitt, Einpassen, Auf Auswahl – mit Symbol, Tooltip und Taste. Die Knöpfe schalten dieselben Funktionen wie
  das Menüband (kein zweiter Weg mit eigener Logik).
- A6 Linke Seitenleiste mit Reitern: Merkmale (wie bisher) · Verlauf (alle Rückgängig-Schritte mit Namen, Klick springt
  dorthin) · Ebenen (Außenwand, Innenwand, Enden, Konturen … ein/aus, Legende ein/aus).
- A4 Seitenleisten ein-/ausblendbar (Knöpfe in der Statuszeile, Strg+1 links, Strg+2 rechts), Breiten je Benutzer
  gemerkt.
- A5 Statuszeile: Koordinaten unter der Maus, Auswahl, Modellabmessungen, Einheit, Prüfstatus.

Alles nur Anzeige und Bedienung: Ebenen blenden nur im Bild aus, die Statuszeile liest nur.
"""
from PySide6.QtCore import QObject, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QTabWidget, QToolBar,
                               QToolButton, QUndoView, QVBoxLayout, QWidget)

from . import stil, symbole

# Ebenen: (Name, Arten im Netz, Tooltip). Schnittkörper schalten über die Ansicht (koerper_setzen)
EBENEN = (
    ("Außenwand", ("A", "BL"), "Außenfläche des Rohrs bzw. das Blech"),
    ("Innenwand", ("I",), "Innenfläche des Rohrs"),
    ("Enden (Anfangs- und Endschnitt)", ("EA", "EB", "GB"), "Schnittflächen an Ende A und B"),
    ("Innenkonturen", ("K",), "Lochwände und Linien der Konturen"),
    ("Gravur", ("G", "GA"), "Gravurlinien"),
    ("Schweißnaht", ("NL", "SN", "SV", "SH", "SX"), "Längsnaht bzw. Schweißnähte"),
    ("Hilfskörper (Gegenrohr)", ("HK",), "Gegenrohr am Ende oder Durchbruch (gehört nicht zum Teil)"),
    ("Anbauteile", ("AN",), "aufgeschweißte Teile (nicht gelasert)"),
    ("Biegelinien", ("B",), "Biegelinien beim Blech"),
)
SCHNITTKOERPER = "Schnittkörper der Konturen"
EINHEIT = "mm"
NAMEN_ROHR = ("quer", "hoch", "längs")


def _z(w, stellen=1):
    t = f"{w:.{stellen}f}".replace(".", ",")
    return "0" + t[2:] if t.startswith("-0") and float(w) == 0 else t


# -------------------------------------------------------------- Verlauf: Namen der Schritte
def _kontur_name(k):
    art = (k or {}).get("art") or "Kontur"
    if k.get("d"):
        return f"{art} Ø {_wert(k['d'])}"
    if k.get("l") and k.get("b"):
        return f"{art} {_wert(k['l'])} × {_wert(k['b'])}"
    return str(art)


def schritt_text(vorher, nachher):
    """Kurzer Name eines Rückgängig-Schritts aus dem Vergleich zweier Editorstände (teile_editor.zustand), z. B.
    „Bohrung Ø 12 eingefügt“, „Zeile 2 geändert: d 10 → 12“, „Ende A geändert“."""
    try:
        ev, en = (vorher or {}).get("e") or {}, (nachher or {}).get("e") or {}
        kv, kn = list(ev.get("konturen") or []), list(en.get("konturen") or [])
        if len(kn) == len(kv) + 1:
            neu = next((k for i, k in enumerate(kn) if i >= len(kv) or k != kv[i]), kn[-1])
            return f"{_kontur_name(neu)} eingefügt"
        if len(kn) == len(kv) - 1:
            weg = next((k for i, k in enumerate(kv) if i >= len(kn) or k != kn[i]), kv[-1])
            return f"{_kontur_name(weg)} entfernt"
        if len(kn) != len(kv):
            return f"{abs(len(kn) - len(kv))} Konturen {'eingefügt' if len(kn) > len(kv) else 'entfernt'}"
        geaendert = [i for i, (a, b) in enumerate(zip(kv, kn)) if a != b]
        if len(geaendert) == 1:
            i = geaendert[0]
            a, b = kv[i], kn[i]
            schl = [s for s in sorted(set(a) | set(b)) if a.get(s) != b.get(s) and not str(s).startswith("_")]
            if len(schl) == 1:
                s = schl[0]
                return f"Zeile {i + 1} geändert: {s} {_wert(a.get(s))} → {_wert(b.get(s))}"
            return f"Zeile {i + 1} geändert ({_kontur_name(b)})"
        if len(geaendert) > 1:
            return f"{len(geaendert)} Konturen geändert"
        for seite, name in (("a", "Ende A"), ("b", "Ende B")):
            if (ev.get(seite) or {}) != (en.get(seite) or {}):
                return f"{name} geändert"
        if (vorher or {}).get("naht") != (nachher or {}).get("naht"):
            return "Schweißnaht geändert"
        andere = [s for s in sorted(set(ev) | set(en)) if ev.get(s) != en.get(s)]
        if andere:
            return f"{', '.join(map(str, andere[:3]))} geändert"
    except (TypeError, AttributeError, ValueError):
        pass
    return "Eingaben geändert"


def _wert(w):
    if isinstance(w, (int, float)) and not isinstance(w, bool):
        return _z(w, 2).rstrip("0").rstrip(",")
    if w in (None, ""):
        return "–"
    t = str(w)
    return t if len(t) <= 18 else t[:17] + "…"


# -------------------------------------------------------------- Werkzeugleiste (A8)
class Werkzeugleiste(QToolBar):
    """Werkzeugleiste direkt über dem 3D (eine Zeile, Symbol und Text). werkzeuge: [(Name, Symbol, Taste, Tooltip, Funktion, umschalter, knopf)]."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOrientation(Qt.Horizontal)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(16, 16))
        self.setMovable(False)
        self.setObjectName("werkzeugleiste3d")
        self.setStyleSheet(stil.umsetzen("QToolBar#werkzeugleiste3d { background: #F3F6FA; border-bottom: 1px solid "
                                         "#D5DBE3; spacing: 2px; padding: 1px 4px; } QToolBar#werkzeugleiste3d "
                                         "QToolButton { padding: 2px 5px; } QToolBar#werkzeugleiste3d "
                                         "QToolButton:checked { background: #DCE9F8; border: 1px solid #8FA6C1; "
                                         "border-radius: 3px; }"))
        self.aktionen = {}

    def werkzeug(self, name, sym, ziel, taste=None, tipp="", umschalter=False):
        a = QAction(symbole.symbol(sym) if sym in symbole.PFADE else symbole.symbol("einpassen"), name, self)
        a.setCheckable(umschalter)
        a.setToolTip(f"<b>{name}</b>" + (f" ({taste})" if taste else "") + (f"<br>{tipp}" if tipp else ""))
        a.triggered.connect(ziel)
        self.addAction(a)
        self.aktionen[name] = a
        return a


# -------------------------------------------------------------- Ebenen (A6)
class Ebenenliste(QWidget):
    """Liste der Ebenen mit Haken; Haken weg blendet die Arten im 3D aus (nur Anzeige)."""

    def __init__(self, ansicht, merken=None, parent=None):
        super().__init__(parent)
        self.a, self.merken = ansicht, merken
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        hinweis = QLabel("Haken weg blendet die Ebene im 3D aus. Nur die Anzeige ändert sich, nicht das Teil.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        lay.addWidget(hinweis)
        self.liste = QListWidget()
        self.liste.setToolTip("Ebenen des 3D-Modells ein- und ausblenden")
        from .ansicht3d import FARBE
        for name, arten, tipp in EBENEN:
            it = QListWidgetItem(name)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            it.setToolTip(tipp)
            it.setData(Qt.UserRole, arten)
            farbe = FARBE.get(arten[0])
            if farbe is not None:
                from PySide6.QtGui import QPixmap
                bild = QPixmap(12, 12)
                bild.fill(farbe)
                it.setIcon(bild)
            self.liste.addItem(it)
        it = QListWidgetItem(SCHNITTKOERPER)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked if ansicht.koerper_an else Qt.Unchecked)
        it.setToolTip("Jede Kontur als halb durchsichtiger Körper, so tief wie sie schneidet")
        it.setData(Qt.UserRole, None)
        self.liste.addItem(it)
        self.liste.itemChanged.connect(self._geaendert)
        lay.addWidget(self.liste, 1)
        self.legende = QCheckBox("Legende im 3D zeigen")
        self.legende.setToolTip("Farblegende oben links im 3D; aus, wenn sie das Modell verdeckt")
        self.legende.setChecked(ansicht.legende_an)
        self.legende.toggled.connect(self._legende)
        lay.addWidget(self.legende)
        alle = QToolButton()
        alle.setText("Alle einblenden")
        alle.clicked.connect(self.alle_einblenden)
        lay.addWidget(alle)

    def _geaendert(self, it):
        if it.data(Qt.UserRole) is None:
            self.a.koerper_setzen(it.checkState() == Qt.Checked)
            return
        self.anwenden()

    def anwenden(self):
        aus = set()
        for i in range(self.liste.count()):
            it = self.liste.item(i)
            arten = it.data(Qt.UserRole)
            if arten and it.checkState() != Qt.Checked:
                aus.update(arten)
        self.a.ebenen_setzen(aus)

    def setzen(self, name, an):
        for i in range(self.liste.count()):
            if self.liste.item(i).text() == name:
                self.liste.item(i).setCheckState(Qt.Checked if an else Qt.Unchecked)

    def alle_einblenden(self):
        self.liste.blockSignals(True)
        for i in range(self.liste.count()):
            if self.liste.item(i).data(Qt.UserRole):
                self.liste.item(i).setCheckState(Qt.Checked)
        self.liste.blockSignals(False)
        self.anwenden()

    def _legende(self, an):
        self.a.legende_setzen(an)
        if self.merken is not None:
            self.merken("editor_legende", bool(an))


# -------------------------------------------------------------- Statuszeile (A5)
class Statuszeile(QWidget):
    """Koordinaten · Auswahl · Modell · Einheit · Prüfstatus, dazu die Knöpfe der Seitenleisten."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statuszeile3d")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(14)
        self.links = QToolButton()
        self.links.setCheckable(True)
        self.links.setChecked(True)
        self.links.setText("◧ Links")
        self.links.setToolTip("Linke Seitenleiste (Merkmale, Verlauf, Ebenen) ein-/ausblenden (Strg+1)")
        self.links.setAutoRaise(True)
        lay.addWidget(self.links)
        grau = f"color: {stil.umsetzen(stil.TEXT_GRAU)};"
        self.koordinaten = QLabel()
        self.koordinaten.setToolTip("Punkt auf dem Modell unter der Maus (Modellkoordinaten in mm)")
        self.koordinaten.setMinimumWidth(230)
        self.auswahl = QLabel()
        self.auswahl.setToolTip("Gewähltes Merkmal bzw. markierte Konturen")
        self.modell = QLabel()
        self.modell.setToolTip("Abmessungen des Modells (Hüllquader): Länge × Breite × Höhe")
        self.einheit = QLabel(f"Einheit: {EINHEIT}")
        self.pruefung = QLabel()
        self.pruefung.setToolTip("Prüfstatus des Teils (Fertigungsprüfung und 3D-Modell)")
        for w in (self.koordinaten, self.auswahl, self.modell, self.einheit):
            w.setStyleSheet(grau)
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(self.pruefung)
        self.rechts = QToolButton()
        self.rechts.setCheckable(True)
        self.rechts.setChecked(True)
        self.rechts.setText("Rechts ◨")
        self.rechts.setToolTip("Rechte Seitenleiste (Eigenschaften, Ergebnis) ein-/ausblenden (Strg+2)")
        self.rechts.setAutoRaise(True)
        lay.addWidget(self.rechts)
        self.koordinaten_setzen(None)

    def koordinaten_setzen(self, punkt, namen=("x", "y", "z")):
        if punkt is None:
            self.koordinaten.setText("Maus: –")
            return
        self.koordinaten.setText("Maus: " + " · ".join(f"{n} {_z(v)}" for n, v in zip(namen, punkt)) + f" {EINHEIT}")

    def modell_setzen(self, modell, rohr=True):
        if modell is None:
            self.modell.setText("Modell: –")
            return
        dx, dy, dz = (modell.max[i] - modell.min[i] for i in range(3))
        if rohr:        # Rohr: z = längs, x = quer, y = hoch
            self.modell.setText(f"Modell: L {_z(dz)} × B {_z(dx)} × H {_z(dy)} {EINHEIT}")
        else:
            self.modell.setText(f"Modell: {_z(dx)} × {_z(dy)} × {_z(dz)} {EINHEIT}")

    def pruefung_setzen(self, text, fehler=False, warnung=False):
        farbe = stil.ROT if fehler else stil.GELB_TEXT if warnung else stil.GRUEN
        self.pruefung.setText(text)
        self.pruefung.setStyleSheet(f"color: {stil.umsetzen(farbe)}; font-weight: bold;")


# -------------------------------------------------------------- Einbau in den Rahmen
class Arbeitsbereich(QObject):
    """Baut Werkzeugleiste, Reiter links, Statuszeile und Tasten in einen fertigen EditorRahmen ein."""

    def __init__(self, rahmen):
        super().__init__(rahmen)
        self.r = rahmen
        r, d = rahmen, rahmen.d
        a3 = r.ansicht()
        self.a3 = a3
        # ---- linke Leiste: Reiter
        links = r.waagerecht.widget(0)
        self.reiter = QTabWidget()
        self.reiter.setDocumentMode(True)
        stelle = r.waagerecht.indexOf(links)
        titel = links.findChild(QLabel)
        if titel is not None and titel.text() == "<b>Merkmale</b>":
            titel.hide()                    # steht jetzt auf dem Reiter
        if r.art == "rohr":
            r.waagerecht.insertWidget(stelle, self.reiter)
            self.reiter.addTab(links, "Merkmale")
        else:                               # Blech: links steht eine Spalte (Merkmale über den Eingaben)
            spalte = links
            merk = spalte.widget(0)
            spalte.insertWidget(0, self.reiter)
            self.reiter.addTab(merk, "Merkmale")
        self.verlauf = QUndoView(r.verlauf)
        self.verlauf.setEmptyLabel("Stand beim Öffnen")
        self.verlauf.setToolTip("Alle Schritte seit dem Öffnen. Klick auf einen Schritt setzt den Editor auf diesen "
                                "Stand (wie mehrmals Rückgängig); danach geht Wiederholen wieder vorwärts.")
        self.reiter.addTab(self.verlauf, "Verlauf")
        self.ebenen = None
        if a3 is not None:
            # A9: die Legende verdeckte das Modell; im Editor zeigt der Reiter Ebenen die Farben, Legende im 3D nach Wahl
            a3.legende_setzen(r._einstellung("editor_legende", False) is True)
            self.ebenen = Ebenenliste(a3, r._merken)
            self.reiter.addTab(self.ebenen, "Ebenen")
        self.reiter.setTabToolTip(0, "Merkmale des Teils mit Herkunft und Sicherheit")
        self.reiter.setTabToolTip(1, "Bearbeitungshistorie: jeder Schritt mit Namen")
        if self.ebenen is not None:
            self.reiter.setTabToolTip(2, "Ebenen ein-/ausblenden, Legende")
        # ---- Seitenleisten einklappbar, Breiten gemerkt (A4)
        r.waagerecht.setChildrenCollapsible(True)
        r.waagerecht.setCollapsible(1, False)
        self.status = Statuszeile()
        self.status.links.toggled.connect(lambda an: self.seite_zeigen(0, an))
        self.status.rechts.toggled.connect(lambda an: self.seite_zeigen(2, an))
        r.waagerecht.splitterMoved.connect(lambda *_: self._breiten_merken())
        self._breiten_laden()
        for taste, seite in (("Ctrl+1", self.status.links), ("Ctrl+2", self.status.rechts)):
            k = QShortcut(QKeySequence(taste), d, context=Qt.WindowShortcut)
            k.activated.connect(seite.toggle)
        haupt = d.layout()
        haupt.insertWidget(haupt.indexOf(r.leiste_unten) + 1, self.status)
        # ---- Werkzeugleiste am 3D (A8)
        self.leiste = None
        if a3 is not None:
            self._leiste_bauen()
        # ---- Statuszeile füttern
        if a3 is not None:
            a3.maus_koordinaten = True
            a3.setMouseTracking(True)
            a3.maus_punkt.connect(lambda p: self.status.koordinaten_setzen(
                p, NAMEN_ROHR if r.art == "rohr" and not (a3.netz or {}).get("global") else ("x", "y", "z")))
        # ---- Mehrfachbearbeitung (A10, A11): rechts statt der Eigenschaften, wenn ≥ 2 Konturen markiert sind
        from .editor_mehrfach import MehrfachTafel
        self.mehrfach = MehrfachTafel(r)
        self.mehrfach.hide()
        r.rechts.insertWidget(0, self.mehrfach)
        self._mehrfach_uhr = QTimer(self)
        self._mehrfach_uhr.setSingleShot(True)
        self._mehrfach_uhr.setInterval(0)
        self._mehrfach_uhr.timeout.connect(self.mehrfach_pruefen)
        d.tabelle.itemSelectionChanged.connect(self._mehrfach_uhr.start)
        r.baum.setSelectionMode(QAbstractItemView.ExtendedSelection)
        r.baum.itemSelectionChanged.connect(self._baum_mehrfach)
        self._uhr = QTimer(self)
        self._uhr.setSingleShot(True)
        self._uhr.setInterval(0)
        self._uhr.timeout.connect(self.auffrischen)
        r.verlauf.indexChanged.connect(lambda *_: self._uhr.start())
        self.auffrischen()

    # ---- Mehrfachbearbeitung
    def markiert(self):
        return sorted({i.row() for i in self.r.d.tabelle.selectedIndexes()})

    def mehrfach_pruefen(self):
        zeilen = self.markiert()
        if len(zeilen) > 1:
            self.mehrfach.zeigen(zeilen)
            self.mehrfach.show()
            self.r.eigenschaften.hide()
        elif self.mehrfach.isVisible() or self.r.eigenschaften.isHidden():
            self.mehrfach.hide()
            self.r.eigenschaften.show()
        self.auffrischen()

    def _baum_mehrfach(self):
        """Strg/Umschalt+Klick im Merkmalsbaum: mehrere Konturen markieren (dieselben Zeilen in der Tabelle)."""
        ids = [it.data(0, Qt.UserRole) for it in self.r.baum.selectedItems()]
        zeilen = sorted({int(i.split(":")[1]) for i in ids if isinstance(i, str) and i.startswith("kontur:")})
        if len(zeilen) < 2:
            return
        t = self.r.d.tabelle
        t.blockSignals(True)
        self.mehrfach._markieren([z for z in zeilen if z < t.rowCount()])
        t.blockSignals(False)
        self.mehrfach_pruefen()

    def mehrfach_aktiv(self):
        return self.mehrfach.isVisible() and len(self.mehrfach.zeilen) > 1

    # ---- Seitenleisten
    def seite_zeigen(self, nr, an):
        w = self.r.waagerecht
        groessen = w.sizes()
        if an and groessen[nr] == 0:
            gemerkt = getattr(self, "_breite", {}).get(nr) or (300 if nr == 0 else 340)
            groessen[nr] = gemerkt
            groessen[1] = max(200, groessen[1] - gemerkt)
        elif not an and groessen[nr] > 0:
            self._breite = dict(getattr(self, "_breite", {}))
            self._breite[nr] = groessen[nr]
            groessen[1] += groessen[nr]
            groessen[nr] = 0
        w.setSizes(groessen)
        knopf = self.status.links if nr == 0 else self.status.rechts
        if knopf.isChecked() != bool(an):
            knopf.blockSignals(True)
            knopf.setChecked(bool(an))
            knopf.blockSignals(False)
        self._breiten_merken()

    def _breiten_merken(self):
        g = self.r.waagerecht.sizes()
        self.status.links.blockSignals(True)
        self.status.rechts.blockSignals(True)
        self.status.links.setChecked(g[0] > 0)
        self.status.rechts.setChecked(g[2] > 0)
        self.status.links.blockSignals(False)
        self.status.rechts.blockSignals(False)
        self.r._merken(f"editor_seiten_{self.r.art}", [g[0], g[2]])

    def _breiten_laden(self):
        wert = self.r._einstellung(f"editor_seiten_{self.r.art}", None)
        if not (isinstance(wert, list) and len(wert) == 2 and all(isinstance(x, int) and 0 <= x <= 2000
                                                                   for x in wert)):
            return
        g = self.r.waagerecht.sizes()
        gesamt = sum(g)
        links, rechts = wert
        g = [links, max(300, gesamt - links - rechts), rechts]
        self.r.waagerecht.setSizes(g)

    # ---- Werkzeugleiste
    def _leiste_bauen(self):
        r, d = self.r, self.r.d
        rohr = r.art == "rohr"
        L = self.leiste = Werkzeugleiste()
        self.taste = {}

        def knopf_klick(k, an=None):
            def tun(*_):
                if k is None:
                    return
                if an is None:
                    k.click()
                elif k.isChecked() != an:
                    k.setChecked(an)
            return tun

        def verschieben(*_):
            for k in (r.auswahl_knopf, r.messen_knopf, r.winkel_knopf):
                if k.isChecked():
                    k.setChecked(False)
            self._werkzeuge_stellen()

        L.werkzeug("Verschieben", "verschieben", verschieben, "V", "Kontur am Griff ziehen, Pfeiltasten verschieben "
                   "(Umschalt = ×10); Enden am Griff kippen. Das ist das normale Werkzeug.", True)
        L.werkzeug("Auswahl", "auswahl", lambda an: r.auswahl_knopf.setChecked(an), "S",
                   "Körper, Fläche, Kante oder Punkt wählen; Strg+Klick mehrere, Umschalt+Ziehen Fenster", True)
        L.addSeparator()
        L.werkzeug("Messen", "lineal", lambda an: r.messen_knopf.setChecked(an), "M",
                   "Zwei Punkte anklicken: Abstand mit exakten Werten (Kreismitte, Kante, Ecke)", True)
        L.werkzeug("Winkel", "winkel", lambda an: r.winkel_knopf.setChecked(an), "W",
                   "Drei Punkte anklicken, der mittlere ist der Scheitel", True)
        L.werkzeug("Maße weg", "masse_weg", lambda *_: r._masse_loeschen(), None, "Alle stehenden Maße entfernen")
        if rohr:
            L.addSeparator()
            L.werkzeug("Schnitt", "schnitt", lambda an: r.schnitt_knopf.setChecked(an), "Q",
                       "Querschnitt an einer Stelle längs des Rohrs", True)
            L.werkzeug("Eckpunkte", "kontur", lambda *_: self._eckpunkte(), "E",
                       "Eckpunkte der gewählten Kontur (Polygon, Sonderkontur) bearbeiten")
            from . import schneidweg as sw
            L.werkzeug("Bohrung", "bohrung", lambda *_: r.kontur_einfuegen(sw.BOHRUNG), "B",
                       "Neue Bohrung einfügen (danach in den Eigenschaften Ø und Lage)")
            L.werkzeug("Ausschnitt", "ausschnitt", lambda *_: r.kontur_einfuegen(sw.RECHTECK), "R",
                       "Neues Rechteck (Ausschnitt) einfügen")
        L.addSeparator()
        a3 = self.a3
        L.werkzeug("Einpassen", "einpassen", lambda *_: a3.einpassen(), "F", "Ganzes Modell bzw. Auswahl einpassen")
        L.werkzeug("Auf Auswahl", "blick", lambda *_: a3.auf_auswahl(), "Z", "Auf das gewählte Element zoomen")
        raster = L.werkzeug("Raster", "raster", lambda an: a3.raster_setzen(an), "G",
                            "Raster unter dem Modell ein/aus (Weite passt sich an, jede 5. Linie kräftiger)", True)
        raster.setChecked(a3.raster_an)
        # Tasten nur im 3D (in Eingabefeldern tippt man weiter normal)
        for name, a in L.aktionen.items():
            tipp = a.toolTip()
            taste = tipp[tipp.find("(") + 1:tipp.find(")")] if "(" in tipp else None
            if taste and len(taste) == 1:
                k = QShortcut(QKeySequence(taste), a3, context=Qt.WidgetShortcut)
                k.activated.connect(a.trigger)
                self.taste[taste] = a
        for k in (r.auswahl_knopf, r.messen_knopf, r.winkel_knopf) + ((r.schnitt_knopf,) if rohr else ()):
            k.toggled.connect(lambda *_: self._werkzeuge_stellen())
        self._werkzeuge_stellen()
        # direkt über die 3D-Ansicht (die Ansicht ist breit, aber im Editor nicht hoch)
        d.ansicht3d.layout().insertWidget(0, L)

    def _eckpunkte(self):
        r = self.r
        z = r._gewaehlte_zeile()
        if z is None or not r.eckpunkte(z):
            from . import einblendung
            einblendung.melden(r.d, "Erst eine Kontur mit Eckpunkten wählen (Polygon oder Sonderkontur).")

    def _werkzeuge_stellen(self):
        r, L = self.r, self.leiste
        if L is None:
            return
        an = dict(Auswahl=r.auswahl_knopf.isChecked(), Messen=r.messen_knopf.isChecked(),
                  Winkel=r.winkel_knopf.isChecked())
        if r.art == "rohr":
            an["Schnitt"] = r.schnitt_knopf.isChecked()
        an["Verschieben"] = not (an["Auswahl"] or an["Messen"] or an["Winkel"])
        for name, wert in an.items():
            a = L.aktionen.get(name)
            if a is not None and a.isChecked() != wert:
                a.blockSignals(True)
                a.setChecked(wert)
                a.blockSignals(False)

    # ---- Statuszeile
    def auffrischen(self):
        r, a3 = self.r, self.a3
        if a3 is not None:
            self.status.modell_setzen(a3.modell, r.art == "rohr" and not (a3.netz or {}).get("global"))
        self.status.auswahl.setText("Auswahl: " + self.auswahl_text())
        stufen = list(getattr(r.leiste_unten, "_stufen", []))
        from . import dfm
        fehler, warn = dfm.FEHLER in stufen, dfm.WARNUNG in stufen
        modell_fehler = bool(a3 is not None and getattr(a3, "pruef_meldung", ""))
        if fehler or modell_fehler:
            text = "✕ Prüfung: Fehler" if fehler else "! 3D-Modell mit ausgelassenen Stellen"
        elif warn:
            text = "! Prüfung: Warnungen"
        else:
            text = "✓ Prüfung in Ordnung"
        self.status.pruefung_setzen(text, fehler or modell_fehler, warn)

    def auswahl_text(self):
        r = self.r
        zeilen = r.markierte_zeilen() if r.art == "rohr" else []
        if len(zeilen) > 1:
            return f"{len(zeilen)} Konturen"
        mid = r.gewaehlt
        if not mid:
            return "keine"
        m = next((m for m in r.merkmale if m.id == mid), None)
        text = m.text if m is not None else mid
        return text if len(text) <= 40 else text[:39] + "…"
