"""Teile-Editor (Plan S6): ein Rahmen für Rohr/Profil (Schneidweg-Rechner) und Blech/Kantteil (Blech-Editor).

Die Rechnung bleibt in den Fenstern (schneidweg.py, blech.py über SchneidwegDialog bzw. BlechDialog); der Rahmen legt
nur dazu:
- links den Merkmalsbaum (Teil, Enden, Innenkonturen, Biegungen, Anbauteile, Schweißnaht, Gravur) mit der Herkunft
  jedes Werts: STEP (wie gemessen), manuell (von Hand, bei geänderten STEP-Werten mit „auf STEP-Wert
  zurücksetzen“) oder Vorgabe (unverändert aus den Grundwerten);
- unten die Prüfmeldungen (Fertigungsprüfung dfm.py, Fehler und Hinweise der Rechnung); ein Klick wählt das
  Merkmal und hebt die Stelle in Tabelle, Skizze und 3D-Ansicht hervor;
- oben Rückgängig/Wiederholen (QUndoStack, Strg+Z/Strg+Y) und Messen im 3D (Punkt–Punkt);
- Auswahl in Baum, Tabelle, Skizze und 3D gleich: ein Klick auf eine Kontur in der 3D-Ansicht wählt die Zeile.
Baum und Prüfmeldungen werden 150 ms nach der letzten Eingabe neu aufgebaut (beim Tippen kein Hänger); jeder
Zwischenstand ist dann ein Schritt für Rückgängig.
"""
import copy
import math

from PySide6.QtCore import QItemSelectionModel, QObject, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (QHeaderView, QLabel, QListWidget, QListWidgetItem, QMenu, QScrollArea, QSplitter,
                               QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from . import biegerohr, dfm, rechnen, rohr3d, schneidweg as sw, stil, symbole
from .ansicht3d import Ansicht3D
from .editor_ansicht import BEIDES, D3, SKIZZE, Ansichtsbereich
from .editor_eigenschaften import Eigenschaften
from .editor_ergebnis import Ergebnisleiste
from .menueband import Menueband

STEP, MANUELL, VORGABE = "STEP", "manuell", "Vorgabe"
GEAENDERT = "manuell (STEP geändert)"
GRUPPEN = ("Teil", "Enden", "Innenkonturen", "Biegungen", "Anbauteile", "Schweißnaht", "Gravur")
FARBE_HERKUNFT = {STEP: stil.GRUEN, GEAENDERT: stil.ORANGE, MANUELL: stil.TEXT, VORGABE: stil.TEXT_GRAU}
FARBE_STUFE = {dfm.FEHLER: stil.ROT, dfm.WARNUNG: stil.GELB_TEXT, dfm.HINWEIS: stil.TEXT_GRAU}
VERZOEGERUNG = 150          # ms nach der letzten Eingabe: Baum, Prüfmeldungen, Rückgängig-Schritt
BAND_SYMBOL = {sw.BOHRUNG: "bohrung", sw.SENKUNG: "bohrung", sw.FLOWDRILL: "bohrung", sw.LANGLOCH: "langloch",
               sw.RECHTECK: "rechteck", sw.SCHLITZ: "ausklinkung", sw.AUSKLINKUNG: "ausklinkung",
               sw.POLYGON: "polygon", sw.SONDERKONTUR: "sonderkontur", sw.SONSTIGE: "sonderkontur",
               sw.GRAVUR: "gravur", sw.V_AUSSCHNITT: "v_ausschnitt"}


class Merkmal:
    """Eintrag im Merkmalsbaum. id: 'teil', 'ende:a', 'kontur:3', 'biegung:0', 'naht', 'gravur', 'anbau';
    zurueck: STEP-Wert zum Zurücksetzen vorhanden (Herkunft GEAENDERT)."""
    __slots__ = ("id", "gruppe", "text", "herkunft")

    def __init__(self, id_, gruppe, text, herkunft):
        self.id, self.gruppe, self.text, self.herkunft = id_, gruppe, text, herkunft

    def __repr__(self):
        return f"{self.id}: {self.text} [{self.herkunft}]"


def _z(v, stellen=1):
    """Zahl mit Komma, ohne Nullen am Ende (8 statt 8,0)."""
    t = f"{sw._z(v):.{stellen}f}"
    return (t.rstrip("0").rstrip(".") if "." in t else t).replace(".", ",")


def kontur_text(i, z):
    """'3. Bohrung Ø d 8 × 2 bei x = 120' (Zeile ab 0)."""
    art = z.get("art") or "?"
    masse = []
    for k, titel in sw.MASSE.get(art, ()):
        v = z.get(k)
        if v in (None, ""):
            continue
        masse.append(f"{titel.split(' (')[0]} {v if isinstance(v, str) else _z(v)}")
    n = int(sw._z(z.get("anzahl")) or 1)
    lage = ""
    if z.get("x") is not None:
        lage = f" bei x = {_z(z['x'], 0)}" + (f", y = {_z(z['y'], 0)}" if z.get("y") is not None else "")
    return f"{i + 1}. {art}" + (f" {', '.join(masse)}" if masse else "") + (f" × {n}" if n > 1 else "") + lage


def ende_text(x):
    x = x or {}
    if sw._z(x.get("sattel")):
        return f"Sattel auf Ø {_z(x['sattel'])}"
    if x.get("achse") == sw.ACHSE_ZWEI:
        return f"Schrägschnitt {_z(x.get('winkel_h'))}° / {_z(x.get('winkel_b'))}°"
    w = sw._z(x.get("winkel"))
    if not w:
        return "gerade"
    return f"Gehrung {_z(w)}°" + (f" {x['achse']}" if x.get("achse") else "") + (" 3D" if x.get("d3") else "")


def merkmale_rohr(e, laenge=None, step_enden=None, step_zeilen=None, naht_text=None, anbau_text=None):
    """Merkmale eines Rohrteils aus den Eingaben des Schneidweg-Rechners. step_enden / step_zeilen: je Ende
    ('a', 'b') bzw. Konturzeile True = wie gemessen, False = gemessen und von Hand geändert (fehlt = kein STEP)."""
    step_enden, step_zeilen = step_enden or {}, step_zeilen or {}

    def herkunft(stand, vorgabe=False):
        return STEP if stand is True else GEAENDERT if stand is False else VORGABE if vorgabe else MANUELL
    out = [Merkmal("teil", "Teil", f"Länge {_z(laenge)} mm" if laenge else "Länge –", MANUELL)]
    for s, titel in (("a", "Ende A"), ("b", "Ende B")):
        x = e.get(s) or {}
        gerade = not sw._z(x.get("winkel")) and not sw._z(x.get("sattel"))
        out.append(Merkmal(f"ende:{s}", "Enden", f"{titel}: {ende_text(x)}", herkunft(step_enden.get(s), gerade)))
    for i, z in enumerate(e.get("konturen") or ()):
        out.append(Merkmal(f"kontur:{i}", "Gravur" if z.get("art") == sw.GRAVUR else "Innenkonturen",
                           kontur_text(i, z), herkunft(step_zeilen.get(i))))
    br = biegerohr.lesen(e)
    if br:      # Biegerohr aus dem STEP-Import: Biegedaten fest aus der Messung
        out[0] = Merkmal("teil", "Teil", f"Länge {_z(laenge)} mm gestreckt, Biegerohr" if laenge else
                         "Länge –", STEP)
        for b in biegerohr.biegungen(br):
            out.append(Merkmal(f"biegung:{b['nr'] - 1}", "Biegungen",
                               f"B{b['nr']}: L {_z(b['gerade'])} · R {_z(b['drehung'])}° · A {_z(b['winkel'])}° · "
                               f"Radius {_z(b['radius'])} (x {_z(b['x0'])}–{_z(b['x1'])} mm)", STEP))
        out.append(Merkmal("biegedaten", "Biegungen", "Biegedaten: " + biegerohr.kurz(br), STEP))
        if br.get("xyz"):
            out.append(Merkmal("xyz", "Biegungen", "XYZ: " + "; ".join(biegerohr.xyz_zeilen(br)), STEP))
    if anbau_text:
        out.append(Merkmal("anbau", "Anbauteile", anbau_text, STEP))
    if naht_text is not None:
        out.append(Merkmal("naht", "Schweißnaht", naht_text[0], naht_text[1]))
    if sw._z(e.get("gravur")):
        out.append(Merkmal("gravur", "Gravur", f"weitere Gravur {_z(e['gravur'])} mm je Teil", MANUELL))
    return out


def _zuschnitt_werte(e):
    return tuple(e.get(k) for k in ("art", "form", "punkte", "laenge", "breite", "eckradius", "kantlaenge"))


def merkmale_blech(e, step=None, start=None):
    """Merkmale eines Blechteils aus den Eingaben des Blech-Editors. step: Werte wie im STEP-Import gemessen
    (e['step'], blech.aus_step) oder None; start: Eingaben beim Öffnen eines neuen Teils (unverändert = Vorgabe)."""
    from . import blech

    def herkunft(jetzt, gemessen, vorgabe):
        if step is not None:
            return STEP if jetzt == gemessen else GEAENDERT if gemessen is not None else MANUELL
        return VORGABE if start is not None and jetzt == vorgabe else MANUELL
    s = step or {}
    st = start or {}
    kant = e.get("art") == blech.KANTTEIL
    if e.get("form") == blech.POLYGON:
        umriss = f"Polygon ({len([x for x in (e.get('punkte') or '').split(';') if x.strip()])} Punkte)"
    elif kant:
        umriss = f"Kantteil, Kantlänge {_z(e.get('kantlaenge'))} mm"
    else:
        umriss = f"Rechteck {_z(e.get('laenge'))} × {_z(e.get('breite'))} mm"
    out = [Merkmal("teil", "Teil", f"{e.get('werkstoff') or '–'} {_z(e.get('dicke'))} mm, {umriss}",
                   herkunft(_zuschnitt_werte(e) + (e.get("dicke"),),
                            _zuschnitt_werte(s) + (s.get("dicke"),) if step is not None else None,
                            _zuschnitt_werte(st) + (st.get("dicke"),)))]
    if kant:
        schenkel = e.get("schenkel") or []
        for i, x in enumerate(schenkel[:-1]):
            gem = (s.get("schenkel") or [])[i] if i < len(s.get("schenkel") or []) else None
            vor = (st.get("schenkel") or [])[i] if i < len(st.get("schenkel") or []) else None
            out.append(Merkmal(f"biegung:{i}", "Biegungen",
                               f"B{i + 1}: {_z(x.get('winkel'))}° nach Schenkel {_z(x.get('laenge'))} mm"
                               + (f", r {_z(x['radius'])}" if x.get("radius") is not None else ""),
                               herkunft(x, gem, vor)))
    else:
        for i, x in enumerate(e.get("biegelinien") or ()):
            out.append(Merkmal(f"biegung:{i}", "Biegungen", f"B{i + 1}: {_z(x.get('winkel'))}° (aus dem STEP-Import)",
                               STEP if step is not None else MANUELL))
    gem_k, vor_k = s.get("konturen") or [], st.get("konturen") or []
    for i, z in enumerate(e.get("konturen") or ()):
        out.append(Merkmal(f"kontur:{i}", "Gravur" if z.get("art") == sw.GRAVUR else "Innenkonturen",
                           kontur_text(i, z), herkunft(_kontur_kern(z), _kontur_kern(gem_k[i]) if i < len(gem_k)
                                                       else None, _kontur_kern(vor_k[i]) if i < len(vor_k) else None)))
    return out


def _kontur_kern(z):
    """Kontur ohne leere Felder (die Tabelle schreibt fehlende Maße als None)."""
    return {k: v for k, v in (z or {}).items() if v not in (None, "")} if z is not None else None


def ziele(befund):
    """Merkmale, die ein Befund betrifft: Konturzeilen, sonst Teil bzw. Biegungen."""
    if befund.zeilen:
        return [f"kontur:{i}" for i in befund.zeilen]
    if befund.regel == dfm.KANTBARKEIT:
        return ["biegung:0"]
    return ["teil"]


class _Schritt(QUndoCommand):
    """Ein Rückgängig-Schritt: Zustand vorher und nachher (das erste redo beim Ablegen ist schon geschehen)."""

    def __init__(self, rahmen, vorher, nachher):
        super().__init__("")
        self.rahmen, self.vorher, self.nachher, self._erst = rahmen, vorher, nachher, True

    def redo(self):
        if self._erst:
            self._erst = False
            return
        self.rahmen.zustand_setzen(self.nachher)

    def undo(self):
        self.rahmen.zustand_setzen(self.vorher)


class EditorRahmen(QObject):
    """Rahmen um ein Fenster (dialog.teiler wird eingebettet); art 'rohr' (SchneidwegDialog) oder 'blech'
    (BlechDialog). Danach dialog.editor = self: die Fenster melden jede Rechnung mit geaendert()."""

    def __init__(self, dialog, art):
        super().__init__(dialog)
        self.d, self.art = dialog, art
        self.merkmale, self.befunde, self.gewaehlt = [], [], None
        self._still = False
        self.verlauf = QUndoStack(self)
        self.zeitgeber = QTimer(self)
        self.zeitgeber.setSingleShot(True)
        self.zeitgeber.setInterval(VERZOEGERUNG)
        self.zeitgeber.timeout.connect(self.aktualisieren)
        self._bauen()
        self.start = self.d.eingaben() if art == "blech" and getattr(dialog, "neu", False) else None
        self._letzter = self.zustand()
        dialog.editor = self
        self.aktualisieren()
        self.eigenschaften.zeigen("teil")

    # -------------------------------------------------------------- Oberfläche
    def _bauen(self):
        """Menüband oben, links Merkmale, in der Mitte die Ansichten (3D und Skizze bzw. Abwicklung), rechts das
        Ergebnis, unten Kennzahlen und Prüfmeldungen (Plan 3D-Editor 3E-1). Die Eingaben der Fenster bleiben: beim
        Rohr unter den Ansichten (aufklappbar), beim Blech links unter den Merkmalen."""
        d = self.d
        rohr = self.art == "rohr"
        self._band_bauen()
        # links Merkmalsbaum, unten Prüfmeldungen
        self.baum = QTreeWidget()
        self.baum.setHeaderLabels(["Merkmal", "Herkunft"])
        kopf = self.baum.header()
        kopf.setStretchLastSection(False)
        kopf.setSectionResizeMode(0, QHeaderView.Stretch)
        kopf.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.baum.setToolTip("Merkmale des Teils. Herkunft: STEP = wie gemessen, manuell = von Hand, Vorgabe = "
                             "Grundwert. Klick wählt das Merkmal in Tabelle, Skizze und 3D-Ansicht.")
        self.baum.currentItemChanged.connect(lambda neu, _: self._baum_gewaehlt(neu))
        self.meldungen = QListWidget()
        self.meldungen.setWordWrap(True)
        self.meldungen.setToolTip("Prüfmeldungen der Fertigungsprüfung und der Rechnung; Klick zeigt die Stelle")
        self.meldungen.currentItemChanged.connect(lambda neu, _: self._meldung_gewaehlt(neu))
        self.meldungen.itemClicked.connect(self._meldung_gewaehlt)
        haupt = d.layout()
        teiler = d.teiler
        stelle = haupt.indexOf(teiler)
        haupt.removeWidget(teiler)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("<b>Merkmale</b>"))
        ll.addWidget(self.baum, 1)
        links.setMinimumWidth(200)
        d.ergebnis_bereich.setMinimumWidth(260)
        # Ansichten aus den Fenstern holen (Rohr: früher Reiter, Blech: früher untereinander rechts)
        self.ansichten = Ansichtsbereich(d.skizze, d.ansicht3d, self._einstellung("editor_ansicht", BEIDES))
        d.kontur_leiste.hide()
        self.waagerecht = QSplitter(Qt.Horizontal)
        self.waagerecht.setChildrenCollapsible(False)
        self.eigenschaften = Eigenschaften(d, self.art)
        self.eigenschaften.setMinimumWidth(260)
        self.eigenschaften.duplizieren.connect(self.duplizieren)
        self.eigenschaften.entfernen.connect(self.entfernen)
        rechts = QSplitter(Qt.Vertical)
        rechts.setChildrenCollapsible(False)
        rechts.addWidget(self.eigenschaften)
        erg_rollen = QScrollArea()          # Ergebnis-Text rollt, statt die Fensterhöhe zu erzwingen
        erg_rollen.setWidgetResizable(True)
        erg_rollen.setFrameShape(QScrollArea.NoFrame)
        erg_rollen.setWidget(d.ergebnis_bereich)
        rechts.addWidget(erg_rollen)
        rechts.setStretchFactor(0, 3)
        rechts.setStretchFactor(1, 2)
        rechts.setSizes([420, 280])
        self.rechts = rechts
        if rohr:
            d.skizze_kopf.hide()
            d.bilder.hide()
            d.bilder = self.ansichten
            self.mitte = QSplitter(Qt.Vertical)
            self.mitte.setChildrenCollapsible(True)
            self.mitte.addWidget(self.ansichten)
            rollen = QScrollArea()          # schmaler Bildschirm: die Eingaben rollen statt das Fenster zu verbreitern
            rollen.setWidgetResizable(True)
            rollen.setFrameShape(QScrollArea.NoFrame)
            rollen.setWidget(d.eingabe_bereich)
            self.mitte.addWidget(rollen)
            self.tabelle_bereich = rollen
            self.mitte.setStretchFactor(0, 3)
            self.mitte.setStretchFactor(1, 2)
            self.waagerecht.addWidget(links)
            self.waagerecht.addWidget(self.mitte)
            self.waagerecht.addWidget(rechts)
            teiler.hide()
        else:
            d.bilder_teiler.hide()
            spalte = QSplitter(Qt.Vertical)
            spalte.addWidget(links)
            rollen = QScrollArea()
            rollen.setWidgetResizable(True)
            rollen.setFrameShape(QScrollArea.NoFrame)
            rollen.setWidget(d.eingabe_bereich)
            spalte.addWidget(rollen)
            spalte.setStretchFactor(0, 1)
            spalte.setStretchFactor(1, 4)
            spalte.setSizes([170, max(500, d.height() - 400)])
            d.ergebnis_bereich.layout().addStretch(1)
            self.mitte = self.ansichten
            self.tabelle_bereich = rollen
            self.waagerecht.addWidget(spalte)
            self.waagerecht.addWidget(self.ansichten)
            self.waagerecht.addWidget(rechts)
            teiler.hide()
        self.waagerecht.setStretchFactor(0, 0)
        self.waagerecht.setStretchFactor(1, 1)
        self.waagerecht.setStretchFactor(2, 0)
        breite = max(900, d.width())
        links_b, rechts_b = (240, 340) if rohr else (500, 320)
        self.waagerecht.setSizes([links_b, breite - links_b - rechts_b, rechts_b])
        if rohr:
            hoehe = max(500, d.height() - 260)
            self.mitte.setSizes([int(hoehe * 0.55), hoehe - int(hoehe * 0.55)])
        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        self.meldung_titel = QLabel()
        ul.addWidget(self.meldung_titel)
        ul.addWidget(self.meldungen, 1)
        self.meldung_bereich = unten
        self.senkrecht = QSplitter(Qt.Vertical)
        self.senkrecht.addWidget(self.waagerecht)
        self.senkrecht.addWidget(unten)
        self.senkrecht.setStretchFactor(0, 1)
        self.senkrecht.setStretchFactor(1, 0)
        self.senkrecht.setSizes([max(400, d.height() - 140), 110])
        self.leiste_unten = Ergebnisleiste()
        self.mass = self.leiste_unten.mass
        self.leiste_unten.aufgeklappt.connect(unten.setVisible)
        unten.setVisible(False)
        haupt.insertWidget(stelle, self.leiste_unten)
        haupt.insertWidget(stelle, self.senkrecht, 1)
        haupt.insertWidget(stelle, self.band)
        a3 = self.ansicht()
        if a3 is not None:
            a3.angeklickt.connect(self._3d_geklickt)
            a3.gemessen.connect(lambda w: self.mass.setText(f"Abstand {rechnen.zahl(w, 1)} mm"))
        self.step_netz = a3.netz if rohr and a3 is not None else None      # Rohr: Netz des STEP-Imports
        self.modell_step = bool(self.step_netz) and bool(getattr(d, "biegerohr", None))
        if rohr:
            d.tabelle.itemSelectionChanged.connect(self._tabelle_gewaehlt)
        else:
            d.tabelle.itemSelectionChanged.connect(lambda: self._tabelle_gewaehlt())
            d.schenkel.itemSelectionChanged.connect(self._schenkel_gewaehlt)
        self._modus_knoepfe(self.ansichten.modus)
        self.tabelle_zeigen(self._einstellung("editor_tabelle", True) is not False)
        # Tastatur: Entf in Baum, Tabelle und 3D entfernt die gewählte Kontur, Strg+D dupliziert sie
        for w in (self.baum, d.tabelle, d.ansicht3d.ansicht):
            k = QShortcut(QKeySequence.Delete, w, context=Qt.WidgetWithChildrenShortcut)
            k.activated.connect(lambda: self._gewaehlte_zeile() is not None and self.entfernen(self._gewaehlte_zeile()))
        k = QShortcut(QKeySequence("Ctrl+D"), d, context=Qt.WindowShortcut)
        k.activated.connect(lambda: self._gewaehlte_zeile() is not None and self.duplizieren(self._gewaehlte_zeile()))

    def _einstellung(self, name, vorgabe):
        db = getattr(self.d, "db", None)
        try:
            v = db.einstellung(name) if db is not None else None
        except Exception:           # z. B. Lesemodus fremder Daten
            v = None
        return v if v not in (None, "") else vorgabe

    def _band_bauen(self):
        d = self.d
        rohr = self.art == "rohr"
        self.band = Menueband()
        kon, ans, aus = (self.band.reiter(n) for n in ("Konstruktion", "Ansicht", "Ausgabe"))
        g = kon.gruppe("Bearbeiten")
        for attr, aktion, text, taste, sym in (
                ("rueck", self.verlauf.createUndoAction(self, "Rückgängig"), "Rückgängig", QKeySequence.Undo,
                 "rueckgaengig"),
                ("vor", self.verlauf.createRedoAction(self, "Wiederholen"), "Wiederholen", QKeySequence.Redo,
                 "wiederholen")):
            aktion.setShortcut(taste)
            aktion.setShortcutContext(Qt.WindowShortcut)
            aktion.setToolTip(f"{text} ({QKeySequence(taste).toString(QKeySequence.NativeText)})")
            aktion.setIcon(symbole.symbol(sym))
            d.addAction(aktion)
            knopf = g.knopf(text, sym)
            knopf.setDefaultAction(aktion)
            knopf.setText(text)
            setattr(self, attr, knopf)
        self.zurueck_knopf = g.knopf("Auf STEP-Wert", "wiederherstellen", lambda: self.zuruecksetzen(), gross=False,
                                     tipp="Das gewählte Merkmal wieder so setzen, wie es im STEP-Import gemessen wurde")
        g.knopf("Duplizieren", "duplizieren", lambda: self._gewaehlte_zeile() is not None and
                self.duplizieren(self._gewaehlte_zeile()), gross=False, tipp="Gewählte Kontur kopieren",
                taste="Strg+D")
        g.knopf("Entfernen", "loeschen", lambda: (d._entfernen if rohr else d._kontur_weg)(), gross=False,
                tipp="Markierte Konturzeilen entfernen", taste="Entf")
        # Konturen: die häufigsten groß, alle weiteren im Menü
        g = kon.gruppe("Konturen")
        arten = sw.ARTEN if rohr else (sw.BOHRUNG, sw.LANGLOCH, sw.RECHTECK, sw.POLYGON, sw.SONSTIGE)
        haupt = (sw.BOHRUNG, sw.LANGLOCH, sw.RECHTECK)
        for art in haupt:
            g.knopf(art, BAND_SYMBOL.get(art), lambda _=False, art=art: self.kontur_einfuegen(art),
                    tipp=f"{art} einfügen: neue Zeile, Lage und Maße im Eingabebereich")
        mehr = QMenu(self.band)
        for art in arten:
            if art not in haupt:
                a = mehr.addAction(symbole.symbol(BAND_SYMBOL.get(art, "mehr")), art)
                a.triggered.connect(lambda _=False, art=art: self.kontur_einfuegen(art))
        g.knopf("Weitere", "mehr", menue=mehr, tipp="Weitere Konturarten")
        if rohr:
            g = kon.gruppe("Rohr")
            k = g.knopf("Knickrahmen", "v_ausschnitt", lambda: d.knickrahmen(),
                        tipp=d.knick_knopf.toolTip())
            k.setEnabled(d.knick_knopf.isEnabled())
            g = kon.gruppe("Übernehmen")
            k = g.knopf("Aus Position", "kopieren", lambda: d._kopieren_waehlen(), gross=False,
                        tipp="Konturen einer anderen Position dieses Angebots anhängen")
            k.setEnabled(bool(d.positionen))
            k = g.knopf("Vorlagen", "vorlage", menue=d.vorlagen_knopf.menu(), gross=False,
                        tipp=d.vorlagen_knopf.toolTip())
            k.setEnabled(d.vorlagen_knopf.isEnabled())
        else:
            g = kon.gruppe("Kantteil")
            for b, sym in zip(d.schenkel_knoepfe, ("neu", "loeschen")):
                g.knopf(b.text().replace("+ ", ""), sym, lambda _=False, b=b: b.click(), gross=False,
                        tipp="Schenkel anhängen" if sym == "neu" else "Markierte Schenkel entfernen")
        # Ansicht
        g = ans.gruppe("Darstellung")
        self.modus_knoepfe = {}
        for modus, text, sym in ((D3, "3D", "wuerfel"), (SKIZZE, "Skizze" if rohr else "Abwicklung", "abwicklung"),
                                 (BEIDES, "Beides", "beides")):
            self.modus_knoepfe[modus] = g.knopf(text, sym, lambda an, m=modus: an and self.modus_setzen(m),
                                                umschalter=True, tipp=f"Mitte: {text}")
        self.tabelle_knopf = g.knopf("Tabelle", "liste", self.tabelle_zeigen, umschalter=True,
                                     tipp="Eingaben als Tabelle zeigen (zum schnellen Durchtippen vieler Zeilen)")
        g = ans.gruppe("Blickrichtung")
        for text, (gi, ni) in (("Schräg", Ansicht3D.GRUND), ("Vorn", (0.0, 0.0)), ("Oben", (0.0, 1.5)),
                               ("Stirnseite", (-1.5708, 0.0))):
            g.knopf(text, None, lambda _=False, gi=gi, ni=ni: self._blick(gi, ni), gross=False)
        if rohr:
            g = ans.gruppe("Modell")
            self.step_knopf = g.knopf("STEP-Modell", "step", lambda an: self.modell_setzen(an), umschalter=True,
                                      tipp="3D: gemessenes Modell aus dem STEP-Import statt des Modells aus den "
                                           "Eingaben (das zeigt jede Änderung sofort)")
            g = ans.gruppe("Skizze")
            g.widget(d.ansicht_wahl)
            g.knopf("Einpassen", None, lambda: d.skizze.einpassen(), gross=False)
        g = ans.gruppe("Messen")
        self.messen_knopf = g.knopf("Messen", "messen", self._messen, umschalter=True,
                                    tipp="In der 3D-Ansicht zwei Punkte anklicken (die nächste Ecke wird gefangen): "
                                         "Abstand in mm")
        # Ausgabe
        g = aus.gruppe("Ausgabe")
        if rohr:
            g.knopf("Zeichnung als PDF", "pdf", lambda: d.zeichnung_pdf(), tipp=d.zeichnung_knopf.toolTip())
            k = g.knopf("STEP neu einlesen", "step", lambda: d.step_einlesen(), tipp=d.step_knopf.toolTip())
            k.setEnabled(d.step_knopf.isEnabled())
        else:
            g.knopf("DXF speichern", "dxf", lambda: d.dxf_speichern(), tipp=d.dxf_knopf.toolTip())
        self.band.eingeklappt_geaendert.connect(lambda an: self._merken("editor_band_zu", an))
        if self._einstellung("editor_band_zu", False) is True:
            self.band.einklappen(True)

    def _merken(self, name, wert):
        db = getattr(self.d, "db", None)
        try:
            if db is not None:
                db.einstellung_setzen(name, wert)
        except Exception:           # Lesemodus: dann eben nicht merken
            pass

    def _modus_knoepfe(self, modus):
        for m, b in self.modus_knoepfe.items():
            b.blockSignals(True)
            b.setChecked(m == modus)
            b.blockSignals(False)

    def modus_setzen(self, modus):
        """Mitte: 3D, Skizze/Abwicklung oder beides (wird je Benutzer gemerkt)."""
        self.ansichten.modus_setzen(modus)
        self._modus_knoepfe(modus)
        self._merken("editor_ansicht", modus)

    def tabelle_zeigen(self, an):
        """Eingabetabelle(n) zeigen oder nur Ansichten + Eigenschaften (wird je Benutzer gemerkt)."""
        an = bool(an)
        self.tabelle_bereich.setVisible(an)
        self.tabelle_knopf.blockSignals(True)
        self.tabelle_knopf.setChecked(an)
        self.tabelle_knopf.blockSignals(False)
        self._merken("editor_tabelle", an)

    def _gewaehlte_zeile(self):
        art, _, nr = (self.gewaehlt or "").partition(":")
        if art == "kontur" and nr.isdigit() and int(nr) < self.d.tabelle.rowCount():
            return int(nr)
        return None

    def duplizieren(self, r):
        """Konturzeile r kopieren (ohne Messwerte des STEP-Imports) und die Kopie wählen."""
        d = self.d
        konturen = d.eingaben().get("konturen") or []
        if not 0 <= r < len(konturen):
            return False
        z = {k: v for k, v in copy.deepcopy(konturen[r]).items() if k not in ("gemessen", "huelle_gemessen")}
        (d.zeile_neu if self.art == "rohr" else d.kontur_neu)(z)
        neu = d.tabelle.rowCount() - 1
        d.tabelle.selectRow(neu)
        self.aktualisieren()
        self.waehlen(f"kontur:{neu}")
        return True

    def entfernen(self, r):
        """Konturzeile r entfernen."""
        d = self.d
        if not 0 <= r < d.tabelle.rowCount():
            return False
        d.tabelle.removeRow(r)
        self.gewaehlt = None
        d.rechnen()
        self.aktualisieren()
        self.eigenschaften.zeigen(None)
        return True

    def _blick(self, gier, nick):
        a = self.ansicht()
        if a is None:
            return
        if self.ansichten.modus == SKIZZE:
            self.modus_setzen(BEIDES)
        a.ansicht(gier, nick)

    def kontur_einfuegen(self, art):
        """Neue Konturzeile der Art anhängen und wählen."""
        d = self.d
        if self.art == "rohr":
            d.zeile_neu(dict(art=art, anzahl=1))
        else:
            d.kontur_neu(dict(art=art, anzahl=1))
        r = d.tabelle.rowCount() - 1
        if r >= 0:
            d.tabelle.selectRow(r)
            d.tabelle.setFocus()
            self.aktualisieren()
            self.waehlen(f"kontur:{r}")

    def modell_setzen(self, step):
        """Rohr: 3D-Modell aus dem STEP-Import (step=True) oder aus den Eingaben."""
        self.modell_step = bool(step) and bool(self.step_netz)
        self._modell_zeigen(self.d.eingaben())

    def _modell_zeigen(self, e):
        """Rohr: Netz der 3D-Ansicht setzen, Blickrichtung behalten."""
        d = self.d
        a = self.ansicht()
        if a is None or self.art != "rohr":
            return
        if hasattr(self, "step_knopf"):
            self.step_knopf.setEnabled(bool(self.step_netz))
            self.step_knopf.blockSignals(True)
            self.step_knopf.setChecked(self.modell_step)
            self.step_knopf.blockSignals(False)
        if self.modell_step or getattr(d, "biegerohr", None):
            netz, titel = self.step_netz, "3D-Ansicht (STEP-Import)"
        else:
            laenge = d.k_laenge.value() if getattr(d, "neu", False) and hasattr(d, "k_laenge") else d.p.get("laenge")
            try:
                netz = rohr3d.netz(e, d.profil, laenge)
            except (ValueError, TypeError, ZeroDivisionError):
                netz = None
            netz, titel = netz or self.step_netz, "3D-Modell (aus den Eingaben)"
        if netz is a.netz:
            return
        alt = a.netz is not None
        blick = (a.gier, a.nick, a.zoom, a.versatz)
        d.ansicht3d.setzen(netz, titel)
        if alt and netz:            # beim Tippen die Blickrichtung behalten
            a.gier, a.nick, a.zoom, a.versatz = blick
            a.update()
        if self.gewaehlt:
            self._3d_markieren([self.gewaehlt])

    def _modell_aus_eingaben(self):
        a = self.ansicht()
        return a is not None and bool((a.netz or {}).get("eingaben"))

    def _kacheln(self):
        d, erg = self.d, self.d.ergebnis or {}
        if self.art == "rohr":
            f = erg.get("felder") or {}
            if not f:
                self.leiste_unten.kacheln_setzen([])
                return
            try:
                zeit = d.schneidzeit()
            except Exception:       # ohne Schneiddaten bzw. unvollständige Eingaben
                zeit = None
            self.leiste_unten.kacheln_setzen([
                ("Schneidweg", f"{rechnen.zahl(f.get('schneidweg'), 1)} mm",
                 f"Enden {rechnen.zahl(f.get('a_schnitt'), 1)} + {rechnen.zahl(f.get('b_schnitt'), 1)} mm, "
                 f"Innenkonturen {rechnen.zahl(f.get('innen'), 1)} mm"),
                ("Einstiche", str(f.get("einstiche") or 0), ""),
                ("Schneidzeit", f"{rechnen.zahl(zeit, 1)} s" if zeit is not None else "–",
                 "je Teil mit den Schneiddaten der Maschine" if zeit is not None else "keine Schneiddaten"),
                ("Konturen klein/mittel/groß", f"{f.get('klein_n', 0)} / {f.get('mittel_n', 0)} / {f.get('gross_n', 0)}",
                 "Konturklassen nach Hüllmaß")])
            return
        if not erg.get("richtpreis"):
            self.leiste_unten.kacheln_setzen([])
            return
        zs = erg.get("zuschnitt") or {}
        self.leiste_unten.kacheln_setzen([
            ("Richtpreis je Stück", f"{erg['richtpreis']:.2f} €".replace(".", ","), "EK-Vorschlag"),
            ("Zuschnitt", f"{rechnen.zahl(zs.get('laenge'), 1)} × {rechnen.zahl(zs.get('breite'), 1)} mm", ""),
            ("Gewicht", f"{rechnen.zahl(erg.get('gewicht'), 2)} kg", "je Teil"),
            ("Laserzeit", f"{rechnen.zahl(erg.get('zeit'), 1)} s",
             f"Schneidweg {rechnen.zahl(erg.get('schneidweg'), 0)} mm, {erg.get('einstiche')} Einstiche")])

    def ansicht(self):
        a = getattr(self.d, "ansicht3d", None)
        return a.ansicht if a is not None else None

    def _messen(self, an):
        a = self.ansicht()
        if a is None:
            return
        if an:
            self.ansichten.setCurrentWidget(self.d.ansicht3d)
        a.messen_setzen(an)
        self.mass.setText("Zwei Punkte in der 3D-Ansicht anklicken" if an else "")

    # -------------------------------------------------------------- Zustand und Rückgängig
    def zustand(self):
        """Alles, was Rückgängig wiederherstellt (Eingaben samt STEP-Merkern der Zeilen und Enden)."""
        d = self.d
        if self.art == "blech":
            return dict(e=d.eingaben())
        zeilen = [copy.deepcopy(getattr(d.tabelle.cellWidget(r, 0), "step", None))
                  for r in range(d.tabelle.rowCount())]
        return dict(e=d.eingaben(), naht=d.naht_werte(), zeilen=zeilen, enden=copy.deepcopy(d._ende_step))

    def zustand_setzen(self, z):
        d = self.d
        self._still = True
        try:
            if self.art == "blech":
                d.eingaben_setzen(copy.deepcopy(z["e"]))
            else:
                self._rohr_setzen(z)
        finally:
            self._still = False
        self.zeitgeber.stop()
        self._letzter = self.zustand()
        self.aktualisieren()

    def _rohr_setzen(self, z):
        from . import naht
        from .schneidweg_dialog import NAHT_WAHL, ohne_messung
        d = self.d
        e = copy.deepcopy(z["e"])
        d.eingaben_setzen(ohne_messung(e))
        d.d3.setChecked(e.get("d3") is True)
        for s in ("a", "b"):
            d.ende_3d[s].setChecked(bool((e.get(s) or {}).get("d3")))
        n = z.get("naht") or {}
        if d.naht_form is not None and n:
            d.naht_vorgabe.setCurrentText(n.get("naht_vorgabe") or naht.KEINE)
            w = n.get("naht_winkel")
            if isinstance(w, (int, float)):
                if hasattr(d.naht_winkel, "setValue"):
                    d.naht_winkel.setValue(w)
                else:
                    d.naht_winkel.setCurrentText(next((t for t, v in NAHT_WAHL.items() if v == w),
                                                      d.naht_winkel.currentText()))
            if n.get("naht_quelle"):
                d.naht_quelle.setCurrentText(n["naht_quelle"])
        d._ende_step = copy.deepcopy(z.get("enden") or {})
        for r, step in enumerate(z.get("zeilen") or ()):
            if r < d.tabelle.rowCount():
                d.tabelle.cellWidget(r, 0).step = copy.deepcopy(step)
        self._rohr_farben()
        d._step_hinweis()
        d.rechnen()

    def _rohr_farben(self):
        """Grün = wie gemessen (Enden: Winkel, Konturen: Anzahl), wie beim Einlesen im Schneidweg-Rechner."""
        d = self.d
        for s in ("a", "b"):
            gleich = s in d._ende_step and d._ende_werte(s) == d._ende_step[s][0]
            d.winkel[s].setStyleSheet(f"background: {stil.GRUEN_FLAECHE};" if gleich else "")
        d.tabelle.blockSignals(True)
        for r in range(d.tabelle.rowCount()):
            it = d.tabelle.item(r, 1)
            if it is not None:
                it.setBackground(QColor(stil.GRUEN_FLAECHE) if self._zeile_step(r) is True else QColor(0, 0, 0, 0))
        d.tabelle.blockSignals(False)

    def _zeile_step(self, r):
        """True = Zeile wie gemessen, False = gemessen und geändert, None = ohne STEP."""
        combo = self.d.tabelle.cellWidget(r, 0)
        step = getattr(combo, "step", None)
        if not step:
            return None
        return step[0] == combo.currentText() and tuple(step[1]) == self.d._mass_texte(r)

    def geaendert(self):
        """Das Fenster hat neu gerechnet: Baum, Prüfmeldungen und Rückgängig nach kurzer Ruhe."""
        if not self._still:
            self.zeitgeber.start()

    def aktualisieren(self):
        z = self.zustand()
        if not self._still and z != self._letzter:
            self.verlauf.push(_Schritt(self, self._letzter, z))
            self._letzter = z
        self.merkmale = self._merkmale(z)
        self._baum_fuellen()
        self._meldungen_fuellen()
        self._zurueck_pruefen()
        self._modell_zeigen(z["e"])
        self._kacheln()
        self.eigenschaften.auffrischen()

    # -------------------------------------------------------------- Merkmale
    def _merkmale(self, z):
        d = self.d
        e = z["e"]
        if self.art == "blech":
            return merkmale_blech(e, getattr(d, "step_werte", None), self.start)
        from . import anbau, naht
        enden = {s: d._ende_werte(s) == werte for s, (werte, _) in d._ende_step.items()}
        zeilen = {r: self._zeile_step(r) for r in range(d.tabelle.rowCount())}
        laenge = d.k_laenge.value() if hasattr(d, "k_laenge") else d.p.get("laenge")
        naht_text = None
        if d.naht_form is not None:
            v = d.naht_vorgabe.currentText()
            if v == naht.FEST:
                w = z["naht"].get("naht_winkel")
                naht_text = (f"feste Position {rechnen.zahl(w, 0)}° ({z['naht'].get('naht_quelle')})",
                             STEP if z["naht"].get("naht_quelle") == "STEP" else MANUELL)
            else:
                naht_text = (v, VORGABE if v == naht.KEINE else MANUELL)
        anbauteile = anbau.lesen(d.p.get("anbauteile"))
        return merkmale_rohr(e, laenge, enden, {r: s for r, s in zeilen.items() if s is not None}, naht_text,
                             anbau.kurz(anbauteile) if anbauteile else None)

    def _baum_fuellen(self):
        b = self.baum
        b.blockSignals(True)
        b.clear()
        gruppen = {}
        wahl = None
        for m in self.merkmale:
            if m.gruppe not in gruppen:
                g = QTreeWidgetItem([m.gruppe, ""])
                g.setFlags(g.flags() & ~Qt.ItemIsSelectable)
                f = g.font(0)
                f.setBold(True)
                g.setFont(0, f)
                gruppen[m.gruppe] = g
            it = QTreeWidgetItem([m.text, m.herkunft])
            it.setData(0, Qt.UserRole, m.id)
            it.setToolTip(0, m.text)
            it.setForeground(1, QColor(FARBE_HERKUNFT.get(m.herkunft, stil.TEXT)))
            gruppen[m.gruppe].addChild(it)
            if m.id == self.gewaehlt:
                wahl = it
        for name in GRUPPEN:
            if name in gruppen:
                b.addTopLevelItem(gruppen[name])
                gruppen[name].setExpanded(True)
        if wahl is not None:
            b.setCurrentItem(wahl)
        b.blockSignals(False)

    def _meldungen_fuellen(self):
        d = self.d
        liste = self.meldungen
        liste.blockSignals(True)
        liste.clear()
        self.befunde = list(d.pruefung())
        erg = d.ergebnis or {}
        eintraege = [(b.stufe, b.zeile(), ziele(b)) for b in self.befunde]
        eintraege += [(dfm.FEHLER, f, []) for f in erg.get("fehler") or ()]
        eintraege += [(dfm.HINWEIS, h, []) for h in erg.get("hinweise") or ()]
        for stufe, text, z in sorted(eintraege, key=lambda t: -dfm.RANG[t[0]]):
            it = QListWidgetItem(f"{stufe}: {text}")
            it.setForeground(QColor(FARBE_STUFE[stufe]))
            it.setData(Qt.UserRole, z)
            it.setToolTip(text + ("\nKlick zeigt die Stelle" if z else ""))
            liste.addItem(it)
        if not eintraege:
            it = QListWidgetItem("Keine Prüfmeldungen")
            it.setForeground(QColor(stil.GRUEN))
            liste.addItem(it)
        liste.blockSignals(False)
        n = len(eintraege)
        self.meldung_titel.setText(f"<b>Prüfmeldungen</b> ({n})" if n else "<b>Prüfmeldungen</b>")
        self.leiste_unten.zaehler_setzen([e[0] for e in eintraege])

    def _zurueck_pruefen(self):
        m = next((x for x in self.merkmale if x.id == self.gewaehlt), None)
        self.zurueck_knopf.setEnabled(m is not None and m.herkunft == GEAENDERT)

    # -------------------------------------------------------------- Auswahl
    def waehlen(self, merkmal_id):
        """Merkmal wählen: im Baum markieren und in Tabelle, Skizze und 3D zeigen."""
        self.gewaehlt = merkmal_id
        b = self.baum
        b.blockSignals(True)
        for i in range(b.topLevelItemCount()):
            g = b.topLevelItem(i)
            for k in range(g.childCount()):
                if g.child(k).data(0, Qt.UserRole) == merkmal_id:
                    b.setCurrentItem(g.child(k))
        b.blockSignals(False)
        self._zeigen(merkmal_id)
        self._zurueck_pruefen()

    def _baum_gewaehlt(self, it):
        if it is not None and it.data(0, Qt.UserRole):
            self.waehlen(it.data(0, Qt.UserRole))

    def _meldung_gewaehlt(self, it):
        z = it.data(Qt.UserRole) if it is not None else None
        if not z:
            return
        self.waehlen(z[0])
        if len(z) > 1:
            self._zeilen_markieren([int(x.split(":")[1]) for x in z if x.startswith("kontur:")])

    def _zeilen_markieren(self, zeilen):
        """Mehrere Konturzeilen markieren (z. B. beide Konturen eines zu schmalen Stegs)."""
        t = self.d.tabelle
        if not zeilen:
            return
        t.blockSignals(True)
        t.clearSelection()
        for r in zeilen:
            if 0 <= r < t.rowCount():
                t.selectionModel().select(t.model().index(r, 0),
                                          QItemSelectionModel.Select | QItemSelectionModel.Rows)
        t.blockSignals(False)
        if self.art == "rohr":
            self.d._auswahl_tabelle()
        self._3d_markieren([f"kontur:{r}" for r in zeilen])

    def _tabelle_gewaehlt(self):
        zeilen = sorted({i.row() for i in self.d.tabelle.selectedIndexes()})
        if zeilen and self.gewaehlt != f"kontur:{zeilen[0]}":
            self.gewaehlt = f"kontur:{zeilen[0]}"
            self.waehlen(self.gewaehlt)

    def _schenkel_gewaehlt(self):
        r = self.d.schenkel.currentRow()
        if r >= 0 and self.gewaehlt != f"biegung:{r}":
            self.waehlen(f"biegung:{r}")

    def _zeigen(self, mid):
        d = self.d
        art, _, nr = mid.partition(":")
        if art == "kontur":
            r = int(nr)
            if 0 <= r < d.tabelle.rowCount() and r not in {i.row() for i in d.tabelle.selectedIndexes()}:
                d.tabelle.selectRow(r)
                d.tabelle.scrollToItem(d.tabelle.item(r, 1))
        elif art == "biegung" and self.art == "blech" and d.schenkel.rowCount() > int(nr):
            d.schenkel.blockSignals(True)
            d.schenkel.selectRow(int(nr))
            d.schenkel.blockSignals(False)
        elif art == "ende":
            d.winkel[nr].setFocus()
        elif art == "naht":
            d.naht_vorgabe.setFocus()
        elif art == "gravur":
            d.gravur.setFocus()
        if self.art == "blech":
            d.skizze.markieren(mid)
        self._3d_markieren([mid])
        if self.eigenschaften.mid != mid:
            self.eigenschaften.zeigen(mid)

    def _3d_markieren(self, ids):
        a = self.ansicht()
        if a is None:
            return
        if self.art == "blech" or self._modell_aus_eingaben():
            a.markieren(ids)
            return
        a.markieren((), self._z_bereich(ids))

    def _z_bereich(self, ids):
        """Rohr (STEP-Netz, Achse Z ab Ende A): Bereich längs der Achse um die Konturen bzw. das Ende."""
        from . import skizze as sk
        a = self.ansicht()
        if a is None or a.modell is None or getattr(self.d, "biegerohr", None):
            return None             # Biegerohr: das Netz ist gebogen, Lagen gelten am gestreckten Rohr
        d = self.d
        z0, z1 = a.modell.min[2], a.modell.max[2]
        bereiche = []
        e = d.eingaben()
        lagen = {x["zeile"]: x for x in sk.lagen(e.get("konturen") or [], z1 - z0) if x.get("nr") == 0}
        hoehe = max(sw._z(d.profil.get("a")), sw._z(d.profil.get("b")), 10.0)
        for mid in ids:
            art, _, nr = mid.partition(":")
            if art == "kontur" and int(nr) in lagen:
                x = lagen[int(nr)]
                h = max(sw._z(x.get("huelle")), 6.0) / 2 + 2
                bereiche.append((z0 + x["x"] - h, z0 + x["x"] + h))
            elif art == "ende":
                w = math.radians(min(sw._z((e.get(nr) or {}).get("winkel")), 80))
                tief = hoehe * math.tan(w) + 3
                bereiche.append((z0 - 1, z0 + tief) if nr == "a" else (z1 - tief, z1 + 1))
        if not bereiche:
            return None
        return min(b[0] for b in bereiche), max(b[1] for b in bereiche)

    def _3d_geklickt(self, treffer):
        """Klick auf eine Linie in der 3D-Ansicht: Merkmal wählen (Blech: Kennung der Linie, Rohr: nächste Kontur
        bzw. Ende längs der Achse)."""
        if self.art == "blech" or (self._modell_aus_eingaben() and treffer.get("id")):
            if treffer.get("id"):
                self.waehlen(treffer["id"])
            return
        from . import skizze as sk
        if getattr(self.d, "biegerohr", None):
            return
        a = self.ansicht()
        z0, z1 = a.modell.min[2], a.modell.max[2]
        x = treffer["punkt"][2] - z0
        e = self.d.eingaben()
        beste = None
        for lage in sk.lagen(e.get("konturen") or [], z1 - z0):
            dist = abs(lage["x"] - x) - max(sw._z(lage.get("huelle")), 6.0) / 2
            if beste is None or dist < beste[0]:
                beste = (dist, f"kontur:{lage['zeile']}")
        enden = [(x, "ende:a"), (z1 - z0 - x, "ende:b")]
        ende = min(enden)
        if beste is None or (ende[0] < 5 and ende[0] < beste[0]):
            beste = ende
        self.waehlen(beste[1])

    # -------------------------------------------------------------- Zurücksetzen
    def zuruecksetzen(self, mid=None):
        """Gewähltes Merkmal auf den STEP-Wert zurücksetzen (ein Schritt für Rückgängig)."""
        mid = mid or self.gewaehlt
        d = self.d
        if not mid:
            return False
        art, _, nr = mid.partition(":")
        if self.art == "rohr":
            if art == "ende" and nr in d._ende_step:
                w, achse, sattel, richtung, wb = d._ende_step[nr][0]
                d.achse[nr].setCurrentText(achse)
                d.winkel[nr].setValue(w)
                d.winkel_b[nr].setValue(wb)
                d.sattel[nr].setValue(sattel)
                d.richtung[nr].setCurrentText(richtung)
            elif art == "kontur":
                r = int(nr)
                combo = d.tabelle.cellWidget(r, 0)
                step = getattr(combo, "step", None)
                if not step:
                    return False
                combo.setCurrentText(step[0])
                d.tabelle.blockSignals(True)
                for i, text in enumerate(step[1]):
                    d.tabelle.item(r, 2 + i).setText(text)
                d.tabelle.blockSignals(False)
            else:
                return False
            self._rohr_farben()
            d.rechnen()
            return True
        step = getattr(d, "step_werte", None)
        if not step:
            return False
        e = d.eingaben()
        if art == "kontur" and int(nr) < len(step.get("konturen") or []) and int(nr) < len(e["konturen"]):
            e["konturen"][int(nr)] = copy.deepcopy(step["konturen"][int(nr)])
        elif art == "biegung" and int(nr) < min(len(step.get("schenkel") or []), len(e["schenkel"])):
            e["schenkel"][int(nr)] = copy.deepcopy(step["schenkel"][int(nr)])      # nur diese Biegung
        elif art == "teil":
            for k in ("art", "form", "punkte", "laenge", "breite", "eckradius", "kantlaenge", "dicke"):
                e[k] = step.get(k)
        else:
            return False
        d.eingaben_setzen(e)
        return True
