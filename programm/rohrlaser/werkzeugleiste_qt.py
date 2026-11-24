"""Oberfläche zu werkzeugleiste.py (Großes Design- und Layout-Update, Patrick 19.11.2026): „Meine Werkzeugleiste“
mit kontextabhängigen Knöpfen, eigene Tastenkürzel, Info-Panel rechts, Arbeitsbereiche im Menü Ansicht.

einrichten(f) hängt alles ans Hauptfenster:
- f.meine_leiste: QToolBar oben (verschiebbar, auch links/rechts/unten andockbar, z. B. als Schnellnavigation links).
  Links die eigenen Knöpfe in eigener Reihenfolge und Gruppen, nach einem Trenner die Knöpfe des Arbeitsbereichs
  (aktionen.kontext). Was gerade nicht geht, ist ausgegraut, der Tooltip nennt den Grund.
- f.info_dock: Info-Panel rechts (aktuelles Angebot, Kunde, Status, Kalkulationsstand, Hinweise, Aufgaben, letzte
  Änderungen), ein-/ausblendbar, gemerkt je Benutzer.
- Menü Ansicht → „Meine Werkzeugleiste“, „Werkzeugleiste konfigurieren …“, „Info-Panel“, „Dashboard anpassen …“ und
  „Arbeitsbereich“ (speichern, wählen, Standard wiederherstellen).
"""
from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (QDockWidget, QInputDialog, QLabel, QMenu, QMessageBox, QPushButton, QScrollArea,
                               QToolBar, QToolButton, QVBoxLayout, QWidget)

from . import aktionen, design, stil
from . import werkzeugleiste as wl

ZUSTAND = "leiste_fenster"          # {Kürzel: Base64 von QMainWindow.saveState}: Lage von Leiste und Info-Panel
_cache = {}


def pfade():
    """Alle Symbolnamen: Hauptaktionen (symbole.PFADE) und Editor (menueband.EDITOR_PFADE)."""
    from . import menueband, symbole
    return {**symbole.PFADE, **menueband.EDITOR_PFADE}


def icon(name, px=22, farbe=None):
    """Symbol in der Größe px (scharf, auch bei 200 % Skalierung); farbe = Hell-Farbe, wird ins Theme umgesetzt."""
    alle = pfade()
    if name not in alle:
        return QIcon()
    farbe = farbe or stil.umsetzen(stil.TEXT)
    schl = (name, px, farbe)
    if schl in _cache:
        return _cache[schl]
    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        return QIcon()
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
           f"stroke='{farbe}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{alle[name]}</svg>")
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for faktor in (1, 2):
        bild = QPixmap(px * faktor, px * faktor)
        bild.fill(Qt.transparent)
        p = QPainter(bild)
        renderer.render(p, QRectF(0, 0, bild.width(), bild.height()))
        p.end()
        bild.setDevicePixelRatio(faktor)
        ic.addPixmap(bild)
    _cache[schl] = ic
    return ic


# Knopffarben aus dem Designsystem: (Hintergrund, Text) in Hell-Farben, stil.umsetzen färbt fürs Theme um
# Text des Akzentknopfs als Wort „white“: stil färbt beim Theme-Wechsel nur Hex-Farben um
FARBE = {"akzent": (design.AKZENT, "white"), "gruen": (design.GRUEN_FLAECHE, design.GRUEN),
         "orange": (design.GELB_FLAECHE, design.ORANGE), "rot": (design.ROT_FLAECHE, design.ROT)}


def knopf_stil(farbe):
    if farbe not in FARBE:
        return ""
    grund, text = FARBE[farbe]
    if farbe == "akzent" and stil.thema() != "Hell":
        grund = design.HAUPTKNOPF_DUNKEL
    else:
        grund = stil.umsetzen(grund)
    text = text if farbe == "akzent" else stil.umsetzen(text)
    return (f"QToolButton {{ background: {grund}; color: {text}; border-radius: 4px; padding: 2px 6px; }}"
            f"QToolButton:disabled {{ background: transparent; color: {stil.umsetzen(design.TEXT_GRAU)}; }}")


STIL = {"neben": Qt.ToolButtonTextBesideIcon, "unter": Qt.ToolButtonTextUnderIcon, "aus": Qt.ToolButtonIconOnly}


class MeineLeiste(QToolBar):
    """„Meine Werkzeugleiste“: Knöpfe aus aktionen.AKTIONEN nach werkzeugleiste.leiste(db)."""

    def __init__(self, f):
        super().__init__("Meine Werkzeugleiste")
        self.f = f
        self.setObjectName("meine_werkzeugleiste")
        self.setMovable(True)
        self.setFloatable(False)
        self.knoepfe = []           # [(QAction, Aktion, kontext?)]
        self._titel = []            # Gruppentitel (QLabel) des aktuellen Aufbaus
        self.kontext = None
        self.aufbau = None
        self._uhr = QTimer(self)    # Zustand der Knöpfe (Auswahl in Tabellen ändert sich ohne Signal ans Fenster)
        self._uhr.setInterval(700)
        self._uhr.timeout.connect(self.zustand)

    # -------------------------------------------------------------- Aufbau
    def neu_bauen(self):
        db = self.f.db
        self.aufbau = wl.leiste(db)
        self._alte_wegraeumen()
        self.clear()
        self.knoepfe = []
        px = wl.GROESSE_PX[self.aufbau["groesse"]]
        self.setIconSize(QSize(px, px))
        self.setToolButtonStyle(STIL[self.aufbau["beschriftung"]])
        for e in self.aufbau["knoepfe"]:
            if "gruppe" in e:
                self._gruppe(e["gruppe"])
            else:
                self._knopf(e, False)
        self.kontext = aktionen.kontext(self.f)
        ids = wl.kontext_knoepfe(self.aufbau, self.kontext)
        sichtbar = [a for a in ids if aktionen.sichtbar(aktionen.AKTION[a])]
        if sichtbar:
            self._gruppe(aktionen.KONTEXT_TITEL.get(self.kontext, ""), kontext=True)
            for aid in sichtbar:
                self._knopf({"id": aid}, True)
        self.setVisible(self.aufbau.get("sichtbar", True))
        self.zustand()
        if not self._uhr.isActive() and not self.f.stumm:
            self._uhr.start()

    def _alte_wegraeumen(self):
        """Aktionen, Menüs und Gruppentitel des vorigen Aufbaus wirklich löschen (Generalüberholung 24.11.2026).
        QToolBar.clear() nimmt sie nur aus der Leiste; da die Leiste ihr Elternteil ist, blieben sie bis zum
        Programmende stehen – bei jedem Wechsel des Reiters (Kontextknöpfe) kamen vier Menüs, Aktionen und zwei
        Beschriftungen samt Verbindungen dazu. deleteLater: neu_bauen kann aus einer Aktion der Leiste heraus laufen."""
        for act in self.actions():          # Knöpfe, Trenner und die Aktionen der Gruppentitel
            if act.parent() is not self:
                continue
            m = act.menu()
            if m is not None:
                m.deleteLater()
            act.deleteLater()
        for t in getattr(self, "_titel", ()):
            t.deleteLater()
        self._titel = []

    def _gruppe(self, titel, kontext=False):
        self.addSeparator()
        if titel:
            t = QLabel(titel)
            self._titel.append(t)
            t.setObjectName("leiste_gruppe")
            t.setStyleSheet(f"color: {stil.umsetzen(design.TEXT_GRAU)}; font-size: 8pt; padding: 0 4px;"
                            + ("font-style: italic;" if kontext else ""))
            t.setToolTip("Knöpfe für diesen Arbeitsbereich (wechseln mit der Seite)" if kontext else titel)
            self.addWidget(t)

    def _knopf(self, e, kontext):
        a = aktionen.AKTION[e["id"]]
        if not aktionen.sichtbar(a):
            return None
        px = self.iconSize().width()
        farbe = "#FFFFFF" if e.get("farbe") == "akzent" else None
        act = QAction(icon(e.get("symbol") or a.symbol, px, farbe), e.get("text") or a.titel, self)
        act.setData(a.id)
        if a.menue is not None:
            menue = QMenu(self)
            menue.aboutToShow.connect(lambda m=menue, a=a: self._menue_fuellen(m, a))
            act.setMenu(menue)
        else:
            act.triggered.connect(lambda _=False, a=a: aktionen.ausfuehren(self.f, a))
        self.addAction(act)
        w = self.widgetForAction(act)
        if isinstance(w, QToolButton):
            if a.menue is not None:
                w.setPopupMode(QToolButton.InstantPopup)
            w.setObjectName(f"leiste_{a.id}")
            if e.get("farbe"):
                w.setStyleSheet(knopf_stil(e["farbe"]))
        self.knoepfe.append((act, a, kontext))
        return act

    def _menue_fuellen(self, menue, a):
        menue.clear()
        eintraege = a.menue(self.f)
        if not eintraege:
            menue.addAction("(noch nichts)").setEnabled(False)
        for titel, aufruf in eintraege:
            menue.addAction(titel, aufruf)
        from . import werkzeugleiste as w
        w.benutzt(self.f.db, a.id)

    # -------------------------------------------------------------- Zustand
    def zustand(self):
        """Knöpfe frei/ausgegraut nach aktionen.grund; Arbeitsbereich gewechselt: Kontextknöpfe neu."""
        if aktionen.kontext(self.f) != self.kontext and self.aufbau is not None:
            return self.neu_bauen()
        tasten = (self.aufbau or {}).get("tasten") or {}
        for act, a, _ in self.knoepfe:
            warum = aktionen.grund(self.f, a)
            act.setEnabled(not warum)
            teile = [f"<b>{a.titel}</b>", a.tipp]
            if tasten.get(a.id):
                teile.append(f"Tastenkürzel: {QKeySequence(tasten[a.id]).toString(QKeySequence.NativeText)}")
            if warum:
                teile.append(f"<i>{warum}</i>")
            act.setToolTip("<br>".join(t for t in teile if t))
        return None

    def aktion(self, aid):
        """QAction eines Knopfs (für Tests und das Kontextmenü) oder None."""
        return next((act for act, a, _ in self.knoepfe if a.id == aid), None)

    def ids(self, kontext=None):
        return [a.id for _, a, k in self.knoepfe if kontext is None or k == kontext]

    def contextMenuEvent(self, ereignis):
        menue = self.kontext_menue(self.actionAt(ereignis.pos()))
        menue.exec(ereignis.globalPos())

    def kontext_menue(self, act=None):
        """Rechtsklick auf die Leiste: Knopf entfernen, Beschriftung, Größe, konfigurieren."""
        menue = QMenu(self)
        aid = act.data() if act is not None else None
        if aid and aid in self.ids(False):
            menue.addAction("Knopf entfernen", lambda: self.entfernen(aid))
        elif aid:
            menue.addAction("Fest in die Leiste übernehmen", lambda: self.uebernehmen(aid))
        unter = menue.addMenu("Beschriftung")
        for wert, text in wl.BESCHRIFTUNGEN:
            x = unter.addAction(text, lambda wert=wert: self.wert_setzen("beschriftung", wert))
            x.setCheckable(True)
            x.setChecked((self.aufbau or {}).get("beschriftung") == wert)
        unter = menue.addMenu("Größe")
        for wert, text, _ in wl.GROESSEN:
            x = unter.addAction(text, lambda wert=wert: self.wert_setzen("groesse", wert))
            x.setCheckable(True)
            x.setChecked((self.aufbau or {}).get("groesse") == wert)
        x = menue.addAction("Kontextabhängige Knöpfe", lambda: self.wert_setzen(
            "kontext_an", not (self.aufbau or {}).get("kontext_an", True)))
        x.setCheckable(True)
        x.setChecked((self.aufbau or {}).get("kontext_an", True))
        menue.addSeparator()
        menue.addAction("Werkzeugleiste konfigurieren …", lambda: konfigurieren(self.f))
        return menue

    def wert_setzen(self, name, wert):
        lst = wl.leiste(self.f.db)
        lst[name] = wert
        wl.leiste_setzen(self.f.db, lst)
        aendern(self.f)

    def entfernen(self, aid):
        lst = wl.leiste(self.f.db)
        lst["knoepfe"] = [e for e in lst["knoepfe"] if e.get("id") != aid]
        wl.leiste_setzen(self.f.db, lst)
        aendern(self.f)

    def uebernehmen(self, aid):
        lst = wl.leiste(self.f.db)
        lst["knoepfe"].append({"id": aid})
        wl.leiste_setzen(self.f.db, lst)
        aendern(self.f)


# ------------------------------------------------------------------ Info-Panel
class InfoPanel(QScrollArea):
    """Rechter Informationsbereich: aktuelles Angebot mit Kunde, Nummer, Status, Kalkulationsstand, Hinweisen,
    offenen Aufgaben und letzten Änderungen; ohne geöffnetes Angebot die zuletzt bearbeiteten."""

    def __init__(self, f):
        super().__init__()
        self.f = f
        self.setWidgetResizable(True)
        self.setObjectName("info_panel")
        innen = QWidget()
        self.lay = QVBoxLayout(innen)
        self.lay.setContentsMargins(10, 8, 10, 8)
        self.text = QLabel()
        self.text.setTextFormat(Qt.RichText)
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.text.linkActivated.connect(self._link)
        self.lay.addWidget(self.text)
        self.problem_knopf = QPushButton("Nächster offener Punkt (F7)")
        self.problem_knopf.clicked.connect(lambda: self._mit_angebot("naechstes_problem"))
        self.lay.addWidget(self.problem_knopf)
        self.check_knopf = QPushButton("Angebots-Check …")
        self.check_knopf.clicked.connect(lambda: self._mit_angebot("check_zeigen"))
        self.lay.addWidget(self.check_knopf)
        self.lay.addStretch(1)
        self.setWidget(innen)
        self.setMinimumWidth(170)         # neben einem Angebot auch auf 1280 Pixel Breite (20.11.2026)
        self._uhr = QTimer(self)
        self._uhr.setSingleShot(True)
        self._uhr.setInterval(400)
        self._uhr.timeout.connect(self.fuellen)
        self._seite = None

    def _mit_angebot(self, methode):
        seite = aktionen.angebot(self.f)
        if seite is not None:
            getattr(seite, methode)()

    def _link(self, ziel):
        art, _, wert = ziel.partition(":")
        if art == "angebot":
            self.f.angebot_oeffnen(int(wert))
        elif art == "kunde":
            seite = aktionen.angebot(self.f)
            if seite is not None:
                seite.kunde_zeigen()

    def spaeter(self, *_):
        if self.isVisible():
            self._uhr.start()

    def showEvent(self, e):
        super().showEvent(e)
        self.fuellen()

    def fuellen(self):
        seite = aktionen.angebot(self.f)
        if seite is not None and getattr(seite, "pos_modell", None) is None:
            # Angebot wird gerade erst aufgebaut (Supportpaket 23.11.2026: AttributeError pos_modell beim Zeigen):
            # gleich noch einmal versuchen, wenn die Seite fertig ist
            self.spaeter()
            return
        if seite is not self._seite:
            if self._seite is not None:
                try:
                    self._seite.pos_modell.modelReset.disconnect(self.spaeter)
                except (RuntimeError, TypeError):
                    pass
            self._seite = seite
            if seite is not None:
                seite.pos_modell.modelReset.connect(self.spaeter)
        self.text.setText(self.inhalt())
        self.problem_knopf.setVisible(seite is not None)
        self.check_knopf.setVisible(seite is not None)

    def inhalt(self):
        """HTML des Panels (ohne Fenster testbar über das Hauptfenster)."""
        seite = aktionen.angebot(self.f)
        grau = stil.umsetzen(design.TEXT_GRAU)
        if seite is None:
            zeilen = [f"<p style='color:{grau}'>Kein Angebot geöffnet. Bereich: "
                      f"{aktionen.KONTEXT_TITEL.get(aktionen.kontext(self.f), '')}</p>", "<b>Zuletzt bearbeitet</b><br>"]
            try:
                letzte = sorted(self.f.db.angebote(), key=lambda z: str(z.get("geaendert") or ""), reverse=True)[:8]
            except Exception:       # noqa: BLE001
                letzte = []
            for z in letzte:
                zeilen.append(f"<a href='angebot:{z['id']}'>{_h(z.get('nummer'))}</a> {_h(z.get('kunde'))}<br>")
            return "".join(zeilen)
        k = seite.kopf
        punkte = len(seite.offene_punkte()) if hasattr(seite, "offene_punkte") else 0
        stand = seite.stand_optimierung() if hasattr(seite, "stand_optimierung") else ""
        farbe = design.GRUEN if stand == "aktuell" else design.ORANGE
        teile = [f"<h3 style='margin:0'>{_h(k.get('nummer') or 'Angebot')}</h3>",
                 _zeile("Kunde", f"<a href='kunde:'>{_h(k.get('kunde') or '–')}</a>"
                        + (f" ({_h(k.get('kundennr'))})" if k.get("kundennr") else "")),
                 _zeile("Referenz", _h(k.get("kundenreferenz"))),
                 _zeile("Bearbeiter", _h(k.get("bearbeiter"))),
                 _zeile("Bearbeitungsstatus", _h(k.get("vorgang") or "Entwurf")),
                 _zeile("Kalkulationsstatus", f"<span style='color:{stil.umsetzen(farbe)}'>"
                        f"{'✓' if stand == 'aktuell' else '!'} {_h(stand)}</span>"),
                 _zeile("Positionen", str(len(seite.positionen))),
                 _zeile("Hinweise", f"{punkte} offene Punkte" if punkte else "✓ alle Positionen OK")]
        aufgaben = []
        from . import funktionen
        if k.get("wiedervorlage") and funktionen.an(funktionen.WIEDERVORLAGE):      # Wiedervorlage abschaltbar
            aufgaben.append(f"Wiedervorlage {_h(k.get('wiedervorlage'))}")
        if k.get("gueltig_bis"):
            aufgaben.append(f"gültig bis {_h(k.get('gueltig_bis'))}")
        if k.get("liefertermin"):
            aufgaben.append(f"Liefertermin {_h(k.get('liefertermin'))}")
        if aufgaben:
            teile.append("<p><b>Offene Aufgaben</b><br>" + "<br>".join(aufgaben) + "</p>")
        aenderungen = self._aenderungen(k)
        if aenderungen:
            teile.append("<p><b>Letzte Änderungen</b><br>" + "<br>".join(aenderungen) + "</p>")
        return "".join(t for t in teile if t)

    def _aenderungen(self, k, anzahl=5):
        if not k.get("uid"):
            return []
        try:
            from . import aenderungsverlauf as av
            eintraege = av.eintraege(self.f.db.con, tabelle=av.ANGEBOT, uid=k["uid"], grenze=anzahl)
        except Exception:           # noqa: BLE001 – Verlauf ist Zusatz (ohne gemeinsamen Ordner leer)
            return []
        aus = []
        for e in eintraege:
            try:
                feld = av.feld_titel(e)
            except Exception:       # noqa: BLE001
                feld = e.get("feld") or ""
            aus.append(f"{_h(str(e.get('zeit') or '')[:16].replace('T', ' '))} {_h(e.get('wer'))}: {_h(feld)}")
        return aus


def _h(text):
    from html import escape
    return escape(str(text or ""))


def _zeile(titel, wert):
    if not wert:
        return ""
    return f"<p style='margin:2px 0'><span style='color:{stil.umsetzen(design.TEXT_GRAU)}'>{titel}</span><br>{wert}</p>"


# ------------------------------------------------------------------ Einrichten
def einrichten(f):
    """Werkzeugleiste, Tastenkürzel, Info-Panel und Menüpunkte ans Hauptfenster hängen."""
    try:
        wl.vorgaben_lesen(f.db)             # Standardlayouts des Admins aus dem gemeinsamen Ordner
    except Exception:                       # noqa: BLE001 – ohne Ordner gelten die gemerkten
        from . import protokoll
        protokoll.warnung("Oberflächen-Vorgaben aus dem gemeinsamen Ordner nicht gelesen")
    f.meine_leiste = MeineLeiste(f)
    f.addToolBar(Qt.TopToolBarArea, f.meine_leiste)
    f.info_panel = InfoPanel(f)
    f.info_dock = QDockWidget("Info", f)
    f.info_dock.setObjectName("info_dock")
    f.info_dock.setWidget(f.info_panel)
    f.info_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
    f.addDockWidget(Qt.RightDockWidgetArea, f.info_dock)
    f.info_dock.visibilityChanged.connect(lambda an: f.info_panel.spaeter() if an else None)
    f.leiste_tasten = []
    f.reiter.currentChanged.connect(lambda _: _gewechselt(f))
    _menue(f)
    aendern(f, fenster=True)


def _gewechselt(f):
    f.meine_leiste.zustand()
    f.info_panel.spaeter()


def aendern(f, fenster=False):
    """Nach einer Änderung der Einstellungen: Leiste, Tastenkürzel, Info-Panel und Startseite neu."""
    f.meine_leiste.neu_bauen()
    tasten_anwenden(f)
    f.info_dock.setVisible(wl.info_an(f.db))
    if fenster:
        zustand_laden(f)
    start = getattr(f, "start", None)
    if start is not None and hasattr(start, "karten_anordnen"):
        start.karten_anordnen()


def tasten_anwenden(f):
    """Eigene Tastenkürzel (werkzeugleiste.tasten) als Aktionen des Hauptfensters, auch für Knöpfe außerhalb der
    Leiste."""
    for act in f.leiste_tasten:
        f.removeAction(act)
        act.deleteLater()
    f.leiste_tasten = []
    for aid, taste in wl.tasten(f.db).items():
        a = aktionen.AKTION.get(aid)
        if a is None or a.ausfuehren is None or a.menue is not None:
            continue
        act = QAction(a.titel, f)
        act.setShortcut(QKeySequence(taste))
        act.setShortcutContext(Qt.WindowShortcut)
        act.triggered.connect(lambda _=False, a=a: aktionen.ausfuehren(f, a))
        f.addAction(act)
        f.leiste_tasten.append(act)


def vorhandene_tasten(f):
    """{Taste: Menüpunkt} aller Menüpunkte des Hauptfensters (für die Prüfung eigener Kürzel)."""
    aus = {}
    for a in f.menuBar().actions():
        m = a.menu()
        if m is None:
            continue
        for b in m.actions():
            for s in b.shortcuts():
                if not s.isEmpty() and b not in f.leiste_tasten:
                    aus[s.toString()] = b.text().replace("&", "")
    return aus


def konfigurieren(f):
    return f.werkzeugleiste_konfigurieren()


def startseite_anpassen(f):
    from .werkzeugleiste_dialog import StartseiteDialog
    d = StartseiteDialog(f)
    if f.stumm:
        return d
    if d.exec():
        d.uebernehmen()
    return d


def info_umschalten(f, an=None):
    an = not f.info_dock.isVisible() if an is None else an
    wl.info_setzen(f.db, an)
    f.info_dock.setVisible(an)
    return an


# ------------------------------------------------------------------ Fensterlage und Arbeitsbereiche
def zustand_text(f):
    return bytes(f.saveState().toBase64()).decode("ascii")


def zustand_merken(f):
    """Lage von Leiste und Info-Panel je Benutzer merken (beim Beenden)."""
    try:
        alle = dict(f.db.einstellung(ZUSTAND) or {})
        alle[wl.benutzer(f.db)] = zustand_text(f)
        if not f.db.nur_lesen:
            f.db.einstellung_setzen(ZUSTAND, alle)
    except Exception:           # noqa: BLE001 – Merken ist Zusatz, das Beenden geht vor
        from . import protokoll
        protokoll.warnung("Lage von Werkzeugleiste und Info-Panel nicht gemerkt")


def zustand_laden(f, text=None):
    if text is None:
        text = (f.db.einstellung(ZUSTAND) or {}).get(wl.benutzer(f.db)) if isinstance(
            f.db.einstellung(ZUSTAND), dict) else None
    if text:
        f.restoreState(QByteArray.fromBase64(text.encode("ascii")))
        f.info_dock.setVisible(wl.info_an(f.db))
        f.meine_leiste.setVisible(f.meine_leiste.aufbau.get("sichtbar", True))


def arbeitsbereich_speichern(f, name=None):
    if name is None:
        name, ok = QInputDialog.getText(f, "Arbeitsbereich speichern", "Name des Arbeitsbereichs (z. B. Kalkulation):")
        if not ok:
            return None
    fehler = wl.profil_speichern(f.db, name, wl.schnappschuss(f.db, zustand_text(f), f.reiter.oben.modus))
    if fehler:
        f.meldung(fehler, fehler=True)
        return None
    f.meldung(f"Arbeitsbereich „{name.strip()}“ gespeichert.")
    return name


def arbeitsbereich_anwenden(f, name):
    daten = wl.profil_daten(f.db, name)
    if daten is None:
        return False
    wl.profil_anwenden(f.db, daten)
    # zuerst Leiste und Info-Panel (aendern), dann Navigation und Dichte: sonst brauchen Panel, breite Navigation und
    # komfortable Abstände kurz zusammen mehr Breite als der Bildschirm und das maximierte Fenster wächst (20.11.2026)
    aendern(f)
    if daten.get("navigation") in ("automatisch", "breit", "schmal"):
        f.leiste_modus(daten["navigation"])
    if "dichte" in daten:
        f.ansicht_anwenden()
    if daten.get("fenster"):
        zustand_laden(f, daten["fenster"])
    f.meldung(f"Arbeitsbereich „{name}“ übernommen.")
    return True


def arbeitsbereich_loeschen(f, name):
    if not f.stumm and QMessageBox.question(f, "Arbeitsbereich löschen", f"Arbeitsbereich „{name}“ löschen?") \
            != QMessageBox.Yes:
        return False
    return wl.profil_loeschen(f.db, name)


def standard_wiederherstellen(f):
    """Eigene Leiste, Startseite, Schnellzugriffe und Info-Panel verwerfen; Leiste wieder oben."""
    if not f.stumm and QMessageBox.question(
            f, "Standardlayout", "Eigene Werkzeugleiste, Dashboard und Schnellzugriffe verwerfen und das Standardlayout "
            "(bzw. die Vorgabe des Admins für die eigene Rolle) wiederherstellen?") != QMessageBox.Yes:
        return False
    wl.zuruecksetzen(f.db)
    f.removeToolBar(f.meine_leiste)
    f.addToolBar(Qt.TopToolBarArea, f.meine_leiste)
    f.addDockWidget(Qt.RightDockWidgetArea, f.info_dock)
    aendern(f)
    f.meine_leiste.show()
    return True


def _menue(f):
    ansicht = next((a.menu() for a in f.menuBar().actions() if a.text().replace("&", "") == "Ansicht"), None)
    if ansicht is None:
        return
    ansicht.addSeparator()
    f.leiste_sichtbar_aktion = QAction("Meine Werkzeugleiste", f, checkable=True)
    f.leiste_sichtbar_aktion.toggled.connect(lambda an: _leiste_zeigen(f, an))
    ansicht.addAction(f.leiste_sichtbar_aktion)
    ansicht.addAction("Werkzeugleiste konfigurieren …", lambda: konfigurieren(f))
    f.info_aktion = QAction("Info-Panel rechts", f, checkable=True)
    f.info_aktion.setShortcut(QKeySequence("Ctrl+Shift+I"))
    f.info_aktion.triggered.connect(lambda an: info_umschalten(f, an))
    ansicht.addAction(f.info_aktion)
    ansicht.addAction("Dashboard anpassen …", lambda: startseite_anpassen(f))
    f.arbeitsbereich_menue = ansicht.addMenu("Arbeitsbereich")
    f.arbeitsbereich_menue.aboutToShow.connect(lambda: _arbeitsbereiche_fuellen(f))
    ansicht.aboutToShow.connect(lambda: (f.leiste_sichtbar_aktion.setChecked(f.meine_leiste.isVisible()),
                                         f.info_aktion.setChecked(f.info_dock.isVisible())))


def _leiste_zeigen(f, an):
    if an == f.meine_leiste.isVisible():
        return
    f.meine_leiste.wert_setzen("sichtbar", bool(an))


def _arbeitsbereiche_fuellen(f):
    m = f.arbeitsbereich_menue
    m.clear()
    for name in wl.EINGEBAUT:
        m.addAction(name, lambda name=name: arbeitsbereich_anwenden(f, name))
    eigene = wl.profile(f.db)
    if eigene:
        m.addSeparator()
        for name in sorted(eigene):
            m.addAction(name, lambda name=name: arbeitsbereich_anwenden(f, name))
    m.addSeparator()
    m.addAction("Aktuellen Arbeitsbereich speichern …", lambda: arbeitsbereich_speichern(f))
    if eigene:
        loeschen = m.addMenu("Arbeitsbereich löschen")
        for name in sorted(eigene):
            loeschen.addAction(name, lambda name=name: arbeitsbereich_loeschen(f, name))
    m.addAction("Standardlayout wiederherstellen …", lambda: standard_wiederherstellen(f))
