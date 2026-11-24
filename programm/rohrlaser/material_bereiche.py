"""Bereiche der Seite Material (Master-Auftrag Materialdatenbank, Patrick 23.11.2026): Dashboard,
Materialübersicht (material_seite), Werkstoffe, Abmessungen, Materialkombinationen (Materialstamm),
Einkaufspreise, Lieferanten (mit Lieferantenvergleich), ERP-Import (Einkäufe und Stammdaten mit Vorschau),
Preisverlauf (mit Herkunft), Importhistorie (Rückgängig) und Einstellungen.

Die Tabellenbereiche sind die vorhandenen Stammdaten-Tabellenseiten (keine zweite Verwaltung); der Admin-Schutz
gilt dort wie unter Einstellungen.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import material_import as mi
from . import material_stamm as ms
from . import materialplattform as mp
from .stammdaten import zahl_als_text

BEREICHE = ("Dashboard", "Materialübersicht", "Werkstoffe", "Abmessungen", "Materialkombinationen", "Einkaufspreise",
            "Lieferanten", "ERP-Import", "Preisverlauf", "Importhistorie", "Einstellungen")
TABELLEN_BEREICH = {"Werkstoffe": "werkstoffe", "Abmessungen": "profile", "Materialkombinationen": "materialstamm",
                    "Einkaufspreise": "preise", "Lieferanten": "material_lieferanten"}


def _zelle(t, rechts=False):
    it = QTableWidgetItem("" if t is None else str(t))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if len(it.text()) > 30:
        it.setToolTip(it.text())
    if rechts:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return it


def _tabelle(koepfe):
    t = QTableWidget(0, len(koepfe))
    t.setHorizontalHeaderLabels(koepfe)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.setSortingEnabled(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def _fuellen(t, zeilen):
    t.setSortingEnabled(False)
    t.setRowCount(len(zeilen))
    for r, z in enumerate(zeilen):
        for c, v in enumerate(z):
            t.setItem(r, c, _zelle(v, isinstance(v, (int, float)) or (isinstance(v, str) and v[:1] in "+-0123456789"
                                                                      and v.replace(",", "").replace(".", "")
                                                                      .replace("%", "").replace(" ", "")
                                                                      .lstrip("+-").isdigit())))
    t.setSortingEnabled(True)
    t.resizeColumnsToContents()


def _z(x, st=2):
    return "" if x is None else zahl_als_text(x, st)


def _pct(p):
    return "" if p is None else ("+" if p >= 0 else "−") + zahl_als_text(abs(p), 1)


def einrichten(seite, uebersicht):
    """Reiter der Bereiche an seite (MaterialBereich) anlegen; uebersicht = die bisherige Arbeitsliste."""
    seite.bereiche = QTabWidget()
    seite.bereiche.setDocumentMode(True)
    seite.bereich_seiten = {}
    seite.dashboard = DashboardSeite(seite)
    for name in BEREICHE:
        if name == "Dashboard":
            w = seite.dashboard
        elif name == "Materialübersicht":
            w = uebersicht
        elif name == "ERP-Import":
            w = ImportSeite(seite)
        elif name == "Preisverlauf":
            w = PreisverlaufSeite(seite)
        elif name == "Importhistorie":
            w = HistorieSeite(seite)
        elif name == "Einstellungen":
            w = EinstellungenSeite(seite)
        else:
            w = QWidget()           # Tabellenseite wird beim ersten Zeigen gebaut (Tempo)
            QVBoxLayout(w).setContentsMargins(0, 0, 0, 0)
        seite.bereich_seiten[name] = w
        seite.bereiche.addTab(w, name)
    seite.bereiche.setCurrentWidget(uebersicht)
    seite.bereiche.currentChanged.connect(lambda i: bereich_gezeigt(seite, seite.bereiche.tabText(i)))
    from PySide6.QtGui import QKeySequence, QShortcut
    for taste, fn in TASTEN(seite):     # nur auf der Seite Material (keine Überschneidung mit dem Hauptfenster)
        sc = QShortcut(QKeySequence(taste), seite)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(fn)


def TASTEN(seite):  # noqa: N802
    """Tastenkürzel der Seite Material."""
    def suche():
        bereich_zeigen(seite, "Materialübersicht")
        seite.suche.setFocus()
        seite.suche.selectAll()
    return (("Ctrl+F", suche),
            ("Ctrl+Shift+I", lambda: bereich_zeigen(seite, "ERP-Import")),
            ("Ctrl+Shift+E", lambda: seite.exportieren()),
            ("Ctrl+Shift+D", lambda: bereich_zeigen(seite, "Dashboard")),
            ("F5", lambda: bereich_gezeigt(seite, seite.bereiche.tabText(seite.bereiche.currentIndex()))))


def bereich_zeigen(seite, name):
    seite.bereiche.setCurrentWidget(seite.bereich_seiten[name])
    bereich_gezeigt(seite, name)
    return seite.bereich_seiten[name]


def tabellenseite(seite, name):
    """Die eingebettete Stammdaten-Tabellenseite eines Bereichs (gebaut beim ersten Aufruf)."""
    w = seite.bereich_seiten[name]
    if getattr(w, "tabelle_seite", None) is None:
        from .fenster import StammdatenSeite
        from .stammdaten import TABELLE
        ts = StammdatenSeite(seite.db, TABELLE[TABELLEN_BEREICH[name]], seite.f.meldung)
        w.layout().addWidget(ts)
        w.tabelle_seite = ts
        if name == "Lieferanten":
            k = QHBoxLayout()
            b = QPushButton("Lieferantenvergleich …")
            b.setToolTip("Alle gültigen Lieferantenpreise des markierten Materials für einen Bedarf rechnen "
                         "(Staffel, Mindestabnahme, Verpackungseinheit, Lieferzeit) und den günstigsten vorschlagen")
            b.clicked.connect(lambda: lieferantenvergleich(seite))
            k.addWidget(b)
            k.addStretch(1)
            w.layout().addLayout(k)
    return w.tabelle_seite


def bereich_gezeigt(seite, name):
    from . import admin_schutz
    from .admin_schutz_fenster import sperren
    if name in TABELLEN_BEREICH:
        ts = tabellenseite(seite, name)
        ts.neu_laden()
        gesch = TABELLEN_BEREICH[name] in admin_schutz.tabellen_geschuetzt(seite.db)
        sperren(ts, gesch and not admin_schutz.ist_admin(seite.db))
    elif name == "Materialübersicht":
        seite.neu_laden()
    elif hasattr(seite.bereich_seiten.get(name), "neu_laden"):
        seite.bereich_seiten[name].neu_laden()


# ------------------------------------------------------------------ Dashboard
class Kachel(QFrame):
    def __init__(self, titel, ziel=None, seite=None):
        super().__init__()
        self.setObjectName("karte")
        self.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(self)
        self.wert = QLabel("–")
        f = self.wert.font()
        f.setPointSizeF(f.pointSizeF() * 1.8)
        f.setBold(True)
        self.wert.setFont(f)
        t = QLabel(titel)
        t.setObjectName("grau")
        lay.addWidget(self.wert)
        lay.addWidget(t)
        self.ziel, self.seite = ziel, seite
        if ziel:
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip(f"Öffnet {ziel[0]}")

    def mousePressEvent(self, e):
        if self.ziel and self.seite:
            bereich, zustand = self.ziel
            bereich_zeigen(self.seite, bereich)
            if zustand:
                self.seite.filter_setzen("zustand", [zustand])
        super().mousePressEvent(e)


class DashboardSeite(QWidget):
    """Kennzahlen der Materialdatenbank; ein Klick auf eine Kachel öffnet den Bereich (gefiltert)."""
    KACHELN = (("werkstoffe", "Werkstoffe", ("Werkstoffe", None)),
               ("abmessungen", "Abmessungen", ("Abmessungen", None)),
               ("varianten", "Materialvarianten", ("Materialübersicht", None)),
               ("stamm", "im Materialstamm", ("Materialkombinationen", None)),
               ("lieferanten", "Lieferanten", ("Lieferanten", None)),
               ("preis_alt", "Preise älter als 30 Tage", ("Materialübersicht", mp.ZUSTAND_ALT)),
               ("ohne_preis", "Materialien ohne Preis", ("Materialübersicht", mp.ZUSTAND_OHNE)),
               ("nur_tonne", "nur Tonnenpreis", ("Materialübersicht", mp.ZUSTAND_TONNE)),
               ("aenderungen_seit_import", "Preisänderungen im letzten Import", ("Preisverlauf", None)),
               ("inaktiv", "inaktive Materialien", ("Materialkombinationen", None)))

    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        lay = QVBoxLayout(self)
        kopf = QHBoxLayout()
        t = QLabel("Materialdatenbank")
        f = t.font()
        f.setPointSizeF(f.pointSizeF() * 1.4)
        f.setBold(True)
        t.setFont(f)
        kopf.addWidget(t)
        kopf.addStretch(1)
        for text, fn in (("ERP-Import …", lambda: bereich_zeigen(seite, "ERP-Import")),
                         ("Prüfvorschläge", lambda: seite.pruefen()),
                         ("Zur Materialübersicht", lambda: bereich_zeigen(seite, "Materialübersicht"))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            kopf.addWidget(b)
        lay.addLayout(kopf)
        gitter = QGridLayout()
        self.kacheln = {}
        for i, (key, titel, ziel) in enumerate(self.KACHELN):
            k = Kachel(titel, ziel, seite)
            self.kacheln[key] = k
            gitter.addWidget(k, i // 5, i % 5)
        lay.addLayout(gitter)
        self.letzter = QLabel()
        self.letzter.setWordWrap(True)
        lay.addWidget(self.letzter)
        lay.addWidget(QLabel("<b>Preiswarnungen</b> (Prüfvorschläge, lokal; Doppelklick öffnet das Material)"))
        self.warnungen = _tabelle(["Art", "Material", "Befund", "Begründung"])
        self.warnungen.cellDoubleClicked.connect(self._oeffnen)
        lay.addWidget(self.warnungen, 1)
        self.werte = {}

    def neu_laden(self):
        zeilen = self.seite.alle_zeilen if self.seite.alle_zeilen else None
        self.werte = ms.kennzahlen(self.seite.db, zeilen)
        for key, k in self.kacheln.items():
            k.wert.setText(str(self.werte.get(key, 0)))
        li = self.werte.get("letzter_import")
        self.letzter.setText(
            f"Letzter ERP-Import: {str(li['zeit'])[:16].replace('T', ' ')}, {Path(str(li['datei'])).name}, "
            f"{li['neu']} neu, {li['preise']} Preise geändert" if li else
            "Letzter ERP-Import: noch keiner (Bereich ERP-Import)")
        from . import material_ki
        befunde = []
        try:
            befunde = material_ki.alle(self.seite.db, self.seite.alle_zeilen or None)[:300]
        except Exception:       # noqa: BLE001  (Dashboard nie leer wegen eines Befunds)
            from . import protokoll
            protokoll.warnung("Material-Dashboard: Prüfvorschläge nicht verfügbar")
        self._befunde = befunde
        _fuellen(self.warnungen, [(b.get("art"), b.get("material") or "", b.get("text") or "",
                                   b.get("begruendung") or "") for b in befunde])

    def _oeffnen(self, r, _c):
        it = self.warnungen.item(r, 1)
        if it and " · " in it.text():
            pid, wid = it.text().split(" · ", 1)
            bereich_zeigen(self.seite, "Materialübersicht")
            self.seite.auswaehlen(pid, wid)


# ------------------------------------------------------------------ Lieferantenvergleich
def lieferzeit_erp(db, profil_id, werkstoff_id):
    """Text der zugesagten Lieferzeit eines Materials aus dem ERP-Einkauf („Ø 12 Tage (5 bis 21, 8 Käufe)“), sonst ""."""
    from . import erp_preise
    g = mp.erp_gruppen(db).get((profil_id, werkstoff_id))
    return erp_preise.lieferzeit_text((g or {}).get("lieferzeit"))


def lieferantenvergleich(seite, profil_id=None, werkstoff_id=None, bedarf=None, frage=True, eltern=None):
    """Lieferantenvergleich für das markierte Material (Materialübersicht oder Tabelle Lieferanten). Ergebnis:
    (Liste aus material_stamm.angebote_fuer, Vorschlag) oder None."""
    if profil_id is None:
        z = seite.aktuelle() if seite.bereiche.currentWidget() is seite.bereich_seiten["Materialübersicht"] else None
        if z is None and "Lieferanten" in seite.bereich_seiten and getattr(
                seite.bereich_seiten["Lieferanten"], "tabelle_seite", None):
            z = seite.bereich_seiten["Lieferanten"].tabelle_seite.ausgewaehlt()
        z = z or seite.aktuelle()
        if not z:
            seite.f.meldung("Bitte zuerst ein Material markieren.")
            return None
        profil_id, werkstoff_id = z["profil_id"], z["werkstoff_id"]
    if bedarf is None:
        if getattr(seite.f, "stumm", False) or not frage:
            bedarf = 30.0
        else:
            bedarf, ok = QInputDialog.getDouble(eltern or seite, "Lieferantenvergleich", f"Bedarf für {profil_id} · "
                                                f"{werkstoff_id} [m]:", 30.0, 0.1, 100000, 1)
            if not ok:
                return None
    k = seite.db.kontext()
    kgm = mp.kg_je_m(k.profile.get(profil_id) or {}, k.werkstoffe.get(werkstoff_id) or {})
    zeilen = seite.db.zeilen(mp.LIEFERANTEN_TABELLE)
    alle = ms.angebote_fuer(zeilen, profil_id, werkstoff_id, kgm, bedarf)
    v = ms.lieferant_vorschlag(zeilen, profil_id, werkstoff_id, kgm, bedarf)
    if not getattr(seite.f, "stumm", False) and frage:
        d = QDialog(eltern or seite)
        d.setWindowTitle(f"Lieferantenvergleich {profil_id} · {werkstoff_id}, Bedarf {bedarf:g} m")
        lay = QVBoxLayout(d)
        t = _tabelle(["Lieferant", "Länge [mm]", "€/m", "Stangen", "Meter", "Kosten [€]", "Lieferzeit [Tage]",
                      "Bevorzugt", "Staffel ab [m]", "Hinweis"])
        _fuellen(t, [(a["lieferant"], int(a["laenge"]), _z(a["preis_m"]), a["stangen"], _z(a["meter"], 1),
                      _z(a["kosten"]), "" if a["lieferzeit"] is None else int(a["lieferzeit"]),
                      "ja" if a["bevorzugt"] else "", _z(a["staffel_ab"], 0), a["grund"]) for a in alle])
        lay.addWidget(t)
        lay.addWidget(QLabel(f"<b>Vorschlag:</b> {v['lieferant']} – {v['begruendung']}" if v else
                             "Kein gültiger Lieferantenpreis für dieses Material (Tabelle Lieferanten)."))
        lz = lieferzeit_erp(seite.db, profil_id, werkstoff_id)
        if lz:
            lay.addWidget(QLabel(f"<b>Lieferzeit laut ERP-Einkauf:</b> {lz} (Liefertermin minus Erfassungsdatum, "
                                 "über alle Lieferanten)"))
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Schließen")
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        d.resize(980, 380)
        d.exec()
    return alle, v


# ------------------------------------------------------------------ ERP-Import
class ImportSeite(QWidget):
    """ERP-Import: Einkäufe (Kaufdatum, Menge, Preis) oder Materialstamm/Preisliste (Artikelnr., Werkstoff,
    Abmessung, EK-Preis); Datei wählen oder hierher ziehen (Drag & Drop)."""

    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        kopf = QLabel(
            "<b>ERP-Import</b><br>Datei hierher ziehen oder wählen. CSV (UTF-8, ANSI, ; , Tab |, Dezimalkomma oder "
            "-punkt) oder Excel (.xlsx). Vor jeder Übernahme gibt es eine Vorschau; erst „Übernehmen“ ändert "
            "etwas, und jeder Lauf lässt sich unter Importhistorie zurücknehmen.")
        kopf.setWordWrap(True)          # sonst erzwingt der lange Text eine Mindestbreite des Hauptfensters
        lay.addWidget(kopf)
        k = QHBoxLayout()
        b1 = QPushButton("Materialstamm und EK-Preise einlesen …")
        b1.setObjectName("primaer")
        b1.setToolTip("Artikel-/Preisliste aus dem ERP: Materialnummer, Bezeichnung, Werkstoff, Abmessung, EK-Preis, "
                      "Einheit, Lieferant, Gewicht")
        b1.clicked.connect(lambda: self.stamm_einlesen())
        b2 = QPushButton("Einkäufe (EK-CSV) einlesen …")
        b2.setToolTip("Einkaufshistorie: Kaufdatum, Menge, Meterpreis, Artikelnummer, EK-Artikel")
        b2.clicked.connect(lambda: seite.erp_einlesen())
        b3 = QPushButton("Preisliste eines Lieferanten …")
        b3.clicked.connect(lambda: seite.preisliste_importieren())
        for b in (b1, b2, b3):
            k.addWidget(b)
        k.addStretch(1)
        lay.addLayout(k)
        lay.addWidget(QLabel("<b>Importprofile</b> (gespeicherte Spaltenzuordnungen dieses Arbeitsplatzes)"))
        self.profile = _tabelle(["Name", "Spalten", "Preiseinheit", "Lieferant"])
        lay.addWidget(self.profile, 1)
        pk = QHBoxLayout()
        weg = QPushButton("Importprofil löschen")
        weg.clicked.connect(self.profil_loeschen)
        pk.addWidget(weg)
        pk.addStretch(1)
        lay.addLayout(pk)

    def neu_laden(self):
        _fuellen(self.profile, [(n, ", ".join(mi.FELD_TITEL.get(f, f) for f in p.get("spalten", {})),
                                 p.get("einheit") or "", p.get("lieferant") or "")
                                for n, p in sorted(mi.profile(self.seite.db).items())])

    def profil_loeschen(self):
        r = self.profile.currentRow()
        if r >= 0:
            mi.profil_loeschen(self.seite.db, self.profile.item(r, 0).text())
            self.neu_laden()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.stamm_einlesen(urls[0])

    def stamm_einlesen(self, pfad=None, **kw):
        return stamm_import(self.seite, pfad, **kw)


def stamm_import(seite, pfad=None, uebernehmen=None, spalten=None, einheit=None, lieferant=None, profil_name=None,
                 hand=None, vorschau=None):
    """Materialstamm/EK-Preise aus dem ERP: Datei lesen, Spalten zuordnen (Importprofil), Vorschau, übernehmen.
    uebernehmen/spalten/... für Tests ohne Dialog; hand = von Hand zugeordnete Zeilen (mi.analysieren), vorschau(v)
    bedient das Vorschau-Fenster statt exec (True = Übernehmen). Ergebnis: dict(posten, erg) oder None."""
    if pfad is None:
        if getattr(seite.f, "stumm", False):
            return None
        pfad, _ = QFileDialog.getOpenFileName(seite, "ERP-Materialstamm / Preisliste", "",
                                              "CSV oder Excel (*.csv *.txt *.xlsx);;Alle Dateien (*)")
        if not pfad:
            return None
    try:
        daten = mi.lesen(Path(pfad).read_bytes(), str(pfad))
    except (OSError, mi.ImportFehler) as e:
        seite.f.meldung(f"ERP-Import: {e}", fehler=True)
        return None
    name, prof = mi.profil_fuer(seite.db, daten["kopf"])
    sp = spalten or (prof or {}).get("spalten") or mi.spalten_vorschlag(daten["kopf"])
    einheit = einheit or (prof or {}).get("einheit") or "€/m"
    lieferant = lieferant if lieferant is not None else (prof or {}).get("lieferant") or None
    stumm = getattr(seite.f, "stumm", False) or uebernehmen is not None or vorschau is not None
    if not stumm:
        d = SpaltenDialog(seite, daten, sp, einheit, lieferant, name)
        if d.exec() != QDialog.Accepted:
            return None
        sp, einheit, lieferant, profil_name = d.ergebnis()
    if mi.fehlende(sp):
        seite.f.meldung("ERP-Import: es fehlt " + ", ".join(mi.fehlende(sp)), fehler=True)
        return None
    if profil_name:
        mi.profil_speichern(seite.db, profil_name, daten["kopf"], sp, einheit, lieferant)
    def rechnen_neu(h=None):
        return mi.analysieren(seite.db, daten, sp, einheit, lieferant, hand=h or hand)
    posten = rechnen_neu()
    if stumm and vorschau is None:
        gruppen = uebernehmen if uebernehmen is not None else mi.AUSFUEHRBAR
    else:
        v = VorschauDialog(seite, posten, rechnen_neu)
        if not (vorschau(v) if vorschau else v.exec() == QDialog.Accepted):
            return dict(posten=posten, erg=None)
        gruppen = v.gruppen()
    if not any(e["gruppe"] in gruppen for e in posten):
        seite.f.meldung("ERP-Import: nichts zu übernehmen")
        return dict(posten=posten, erg=None)
    if not seite.darf("preise", "materialstamm", "profile") or (
            any(e.get("werkstoff_neu") and e["gruppe"] in gruppen for e in posten) and not seite.darf("werkstoffe")):
        return dict(posten=posten, erg=None)
    try:
        erg = mi.ausfuehren(seite.db, posten, gruppen, datei=pfad, importprofil=profil_name or name or "")
    except mi.ImportFehler as e:
        seite.f.meldung(str(e), fehler=True)
        return dict(posten=posten, erg=None)
    gemerkt = mi.hand_merken(seite.db, posten, gruppen)     # von Hand zugeordnete Artikel beim nächsten Mal erkennen
    erg["gemerkt"] = gemerkt
    f = seite.window()
    f.alles_neu_laden() if hasattr(f, "alles_neu_laden") else None
    seite.neu_laden(erzwingen=True)
    seite.f.meldung(f"ERP-Import übernommen: {erg['neu']} Materialien neu, {erg['preise']} Preise, "
                    f"{erg['profile']} Profile, {erg['werkstoffe']} Werkstoffe (rückgängig unter Importhistorie)")
    return dict(posten=posten, erg=erg)


class SpaltenDialog(QDialog):
    """Spalten der Datei den Feldern zuordnen (Vorschlag nach Spaltennamen), Preiseinheit/Lieferant vorgeben,
    als Importprofil speichern."""

    def __init__(self, seite, daten, spalten, einheit, lieferant, profil_name):
        super().__init__(seite)
        self.setWindowTitle("ERP-Import: Spalten zuordnen")
        self.daten = daten
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.wahl = {}
        for feld, titel in mi.FELDER:
            c = QComboBox()
            c.addItem("–")
            c.addItems([f"{i + 1}: {k}" for i, k in enumerate(daten["kopf"])])
            if feld in spalten:
                c.setCurrentIndex(spalten[feld] + 1)
            self.wahl[feld] = c
            form.addRow(titel + (" *" if feld in mi.PFLICHT else ""), c)
        self.einheit = QComboBox()
        self.einheit.addItems(["€/m", "€/kg", "€/t", "€/100 m", "€/Stange"])
        self.einheit.setCurrentText(einheit)
        form.addRow("Preiseinheit, wenn die Spalte fehlt", self.einheit)
        self.lieferant = QComboBox()
        self.lieferant.addItem("")
        self.lieferant.addItems(sorted(seite.db.kontext().zukauf_lieferanten))
        self.lieferant.setCurrentText(lieferant or "")
        form.addRow("Lieferant, wenn die Spalte fehlt", self.lieferant)
        self.profil = QComboBox()
        self.profil.setEditable(True)
        self.profil.addItems([""] + sorted(mi.profile(seite.db)))
        self.profil.setCurrentText(profil_name or "")
        self.profil.setToolTip("Name eingeben, um die Zuordnung als Importprofil zu speichern")
        form.addRow("Als Importprofil speichern", self.profil)
        lay.addLayout(form)
        self.fehler = QLabel()
        self.fehler.setObjectName("fehler")
        lay.addWidget(self.fehler)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Weiter zur Vorschau")
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def spalten(self):
        return {f: c.currentIndex() - 1 for f, c in self.wahl.items() if c.currentIndex() > 0}

    def _ok(self):
        sp = self.spalten()
        fehlt = mi.fehlende(sp)
        doppelt = len(set(sp.values())) < len(sp)
        if fehlt or doppelt:
            self.fehler.setText(("Fehlt: " + ", ".join(fehlt) + ". ") * bool(fehlt)
                                + "Eine Spalte ist mehrfach zugeordnet." * doppelt)
            return
        self.accept()

    def ergebnis(self):
        e = self.einheit.currentText().replace("€/100 m", "€/100m")
        return self.spalten(), e, self.lieferant.currentText() or None, self.profil.currentText().strip() or None


class VorschauDialog(QDialog):
    """Vorschau vor dem Import: je Gruppe Anzahl und Zeilen; Haken, welche Gruppen übernommen werden. Zeilen, die
    das Programm nicht zuordnen konnte, lassen sich hier von Hand einem Profil und Werkstoff zuordnen (neu(hand)
    rechnet die Vorschau neu); unten steht, welche offenen Angebote nach der Übernahme anders rechnen."""
    KOPF = ["Zeile", "Materialnr.", "Bezeichnung", "Profil", "Werkstoff", "Oberfläche", "Basis", "Preis", "€/m neu",
            "€/m bisher", "Änderung %", "Lieferant", "Gültig ab", "Hinweis"]

    def __init__(self, seite, posten, neu=None):
        super().__init__(seite)
        self.setWindowTitle("ERP-Import: Vorschau")
        self.seite, self.posten, self.neu, self.hand = seite, posten, neu, {}
        lay = QVBoxLayout(self)
        k = QHBoxLayout()
        self.haken = {}
        for g in mi.GRUPPEN:
            cb = QCheckBox(g)
            cb.toggled.connect(lambda *_: self._zaehlen())
            self.haken[g] = cb
            k.addWidget(cb)
        k.addStretch(1)
        lay.addLayout(k)
        self.reiter = QTabWidget()
        self.tabellen = {}
        for g in mi.GRUPPEN:
            t = _tabelle(self.KOPF)
            t.itemSelectionChanged.connect(lambda: self._knoepfe())
            self.tabellen[g] = t
            self.reiter.addTab(t, g)
        self.reiter.currentChanged.connect(lambda *_: self._knoepfe())
        lay.addWidget(self.reiter, 1)
        self.auswirkung_text = QLabel()
        self.auswirkung_text.setWordWrap(True)
        lay.addWidget(self.auswirkung_text)
        u = QHBoxLayout()
        self.zuordnen_knopf = QPushButton("Zuordnen …")
        self.zuordnen_knopf.setToolTip("Markierte Zeile aus „nicht zuordenbar“ oder „fehlerhaft“ von Hand einem Profil "
                                       "und Werkstoff zuordnen; die Vorschau rechnet neu, und die Artikelnummer wird "
                                       "beim Übernehmen gemerkt")
        self.zuordnen_knopf.clicked.connect(lambda: self.zuordnen())
        u.addWidget(self.zuordnen_knopf)
        self.exp = QPushButton("Fehlerhafte Zeilen exportieren …")
        self.exp.clicked.connect(lambda: self.fehler_exportieren())
        u.addWidget(self.exp)
        self.auswirkung_knopf = QPushButton("Betroffene Angebote …")
        self.auswirkung_knopf.setToolTip("Offene Angebote, die nach der Übernahme mit dem neuen Preis rechnen")
        self.auswirkung_knopf.clicked.connect(lambda: self.auswirkung_zeigen())
        u.addWidget(self.auswirkung_knopf)
        self.text = QLabel()
        u.addWidget(self.text, 1)
        lay.addLayout(u)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = bb.button(QDialogButtonBox.Ok)
        self.ok.setText("Übernehmen")
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.resize(1250, 680)
        self._fuellen(erst=True)

    def _fuellen(self, erst=False):
        """Gruppen, Tabellen und Zähler aus self.posten; beim ersten Mal sind alle übernehmbaren Gruppen angehakt,
        danach bleiben die Haken (eine neu gefüllte Gruppe wird angehakt)."""
        z = mi.zaehlen(self.posten)
        for i, g in enumerate(mi.GRUPPEN):
            cb = self.haken[g]
            geht = g in mi.AUSFUEHRBAR and z[g] > 0
            war = cb.isEnabled()
            cb.blockSignals(True)
            cb.setText(f"{g} ({z[g]})")
            cb.setChecked(geht and (erst or cb.isChecked() or not war))
            cb.setEnabled(geht)
            cb.setToolTip("übernehmen" if g in mi.AUSFUEHRBAR else "wird nicht übernommen (nur angezeigt)")
            cb.blockSignals(False)
            zeilen = [e for e in self.posten if e["gruppe"] == g]
            _fuellen(self.tabellen[g], [(e["zeile"], e["materialnr"], e["bezeichnung"], e.get("profil_id") or "",
                                         e.get("werkstoff_id") or "", e.get("oberflaeche") or "", e.get("basis") or "",
                                         _z(e.get("preis"), 4), _z(e.get("preis_m")), _z(e.get("alt_m")),
                                         _pct(e.get("pct")), e.get("lieferant") or "",
                                         e.get("gueltig_ab") or "", "; ".join(e["hinweis"])) for e in zeilen])
            self.reiter.setTabText(i, f"{g} ({z[g]})")
        self.exp.setEnabled(z[mi.FEHLER] + z[mi.OFFEN] + z[mi.DOPPELT] > 0)
        self._zaehlen()
        self._knoepfe()

    def _markiert(self):
        """Markierter Posten des offenen Reiters oder None."""
        g = mi.GRUPPEN[self.reiter.currentIndex()]
        r = self.tabellen[g].currentRow()
        zeilen = [e for e in self.posten if e["gruppe"] == g]
        return zeilen[r] if 0 <= r < len(zeilen) else None

    def _knoepfe(self):
        e = self._markiert()
        self.zuordnen_knopf.setEnabled(self.neu is not None and e is not None and e.get("preis") is not None
                                       and (e["gruppe"] == mi.OFFEN or e.get("hand")))

    def zuordnen(self, zeile=None, profil_id=None, werkstoff_id=None, oberflaeche=""):
        """Zeile von Hand zuordnen: ohne Angaben fragt ein Fenster nach Profil und Werkstoff (Werkstoffe, die der
        Materialstamm für das Profil kennt, stehen oben). Danach rechnet die Vorschau neu. Ergebnis: True/False."""
        e = self._markiert() if zeile is None else next((x for x in self.posten if x["zeile"] == zeile), None)
        if e is None or self.neu is None:
            return False
        if profil_id is None:
            wahl = self._zuordnung_fragen(e)
            if wahl is None:
                return False
            profil_id, werkstoff_id, oberflaeche = wahl
        self.hand[e["zeile"]] = dict(profil_id=profil_id, werkstoff_id=werkstoff_id, oberflaeche=oberflaeche or "")
        self.posten[:] = self.neu(self.hand)
        self._fuellen()
        return True

    def _zuordnung_fragen(self, e):
        k = self.seite.db.kontext()
        d = QDialog(self)
        d.setWindowTitle("ERP-Import: Zeile zuordnen")
        lay = QVBoxLayout(d)
        info = QLabel(f"<b>Zeile {e['zeile']}</b>: {e.get('materialnr') or ''} {e.get('bezeichnung') or ''}<br>"
                      + "; ".join(e["hinweis"]))
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        pr = QComboBox()
        pr.setEditable(True)
        pr.addItems(sorted(k.profile))
        pr.setCurrentText(e.get("profil_id") if e.get("profil_id") in k.profile else "")
        ws = QComboBox()
        ob = QComboBox()
        ob.addItems([""] + sorted(k.oberflaechen))
        ob.setCurrentText(e.get("oberflaeche") or "")

        def werkstoffe(*_):
            jetzt = ws.currentText() or e.get("werkstoff_id") or ""
            oben = [w["werkstoff_id"] for w in ms.werkstoffe_fuer(pr.currentText(), self.seite.db.zeilen(ms.STAMM), k)]
            ws.clear()
            ws.addItems(oben + [w for w in sorted(k.werkstoffe) if w not in oben])
            ws.setCurrentIndex(ws.findText(jetzt) if jetzt in k.werkstoffe else -1)     # Werkstoff nie raten
        pr.currentTextChanged.connect(werkstoffe)
        werkstoffe()
        form.addRow("Profil", pr)
        form.addRow("Werkstoff", ws)
        form.addRow("Oberfläche", ob)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Zuordnen")
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        d.resize(520, 220)
        while d.exec() == QDialog.Accepted:
            if pr.currentText() in k.profile and ws.currentText() in k.werkstoffe:
                return pr.currentText(), ws.currentText(), ob.currentText()
            self.seite.f.meldung("Bitte ein vorhandenes Profil und einen Werkstoff wählen.", fehler=True)
        return None

    def auswirkung(self):
        return mi.auswirkung(self.seite.db, self.posten, self.gruppen())

    def auswirkung_zeigen(self):
        """Liste der offenen Angebote, die nach der Übernahme anders rechnen (nur Anzeige)."""
        d = QDialog(self)
        d.setWindowTitle("ERP-Import: betroffene offene Angebote")
        lay = QVBoxLayout(d)
        t = _tabelle(["Angebot", "Kunde", "Positionen", "Material", "€/m bisher", "€/m neu", "Änderung %"])
        _fuellen(t, [(a["nummer"], a["kunde"], a["positionen"], f"{pid} · {wid}", _z(alt), _z(neu_), _pct(pct))
                     for a in self.auswirkung() for pid, wid, alt, neu_, pct in a["materialien"]])
        lay.addWidget(t)
        lay.addWidget(QLabel("Festgeschriebene Angebote und Positionen mit eigenem Meterpreis ändern sich nicht."))
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Schließen")
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        d.resize(900, 420)
        d.exec()

    def gruppen(self):
        return tuple(g for g, cb in self.haken.items() if cb.isChecked())

    def _zaehlen(self):
        n = sum(1 for e in self.posten if e["gruppe"] in self.gruppen())
        self.text.setText(f"{n} Zeilen werden übernommen. Vorher wird gesichert; der Lauf lässt sich zurücknehmen.")
        self.ok.setEnabled(n > 0)
        aw = self.auswirkung()
        self.auswirkung_knopf.setEnabled(bool(aw))
        self.auswirkung_text.setVisible(bool(aw))
        if aw:
            nummern = ", ".join(str(a["nummer"]) for a in aw[:6]) + (" …" if len(aw) > 6 else "")
            self.auswirkung_text.setText(
                f"<b>Auswirkung:</b> {len(aw)} offene" + ("s Angebot rechnet" if len(aw) == 1 else " Angebote rechnen")
                + f" nach der Übernahme mit neuen Materialpreisen ({nummern}). Festgeschriebene Angebote bleiben "
                "unverändert.")

    def fehler_exportieren(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Fehlerhafte Zeilen", "import_fehler.csv", "CSV (*.csv)")
            if not pfad:
                return None
        Path(pfad).write_text(mi.fehler_csv(self.posten), encoding="utf-8-sig")
        return pfad


# ------------------------------------------------------------------ Preisverlauf
class PreisverlaufSeite(QWidget):
    """Jede Preisänderung mit altem und neuem Preis, Änderung in %, Datum, Herkunft, Lieferant und Importquelle:
    aus dem ERP-Import (Importhistorie) und aus den Stammdaten (Preisstände, preisverlauf)."""

    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        lay = QVBoxLayout(self)
        k = QHBoxLayout()
        self.nur_gross = QCheckBox("nur Änderungen ab 10 %")
        self.nur_gross.toggled.connect(lambda *_: self.neu_laden())
        k.addWidget(self.nur_gross)
        kurve = QPushButton("Preisentwicklung des Materials …")
        kurve.setToolTip("Grafik im Reiter Preishistorie der Materialübersicht")
        kurve.clicked.connect(self._kurve)
        k.addWidget(kurve)
        k.addStretch(1)
        lay.addLayout(k)
        self.tabelle = _tabelle(["Datum", "Profil", "Werkstoff", "Lieferant", "Basis", "alter EK", "neuer EK",
                                 "Änderung %", "Herkunft", "Importquelle"])
        lay.addWidget(self.tabelle, 1)
        self.zeilen = []

    def neu_laden(self):
        self.zeilen = verlauf_zeilen(self.seite.db)
        if self.nur_gross.isChecked():
            self.zeilen = [z for z in self.zeilen if z["pct"] is not None and abs(z["pct"]) >= 10]
        _fuellen(self.tabelle, [(str(z["datum"])[:10], z["profil_id"] or "", z["werkstoff_id"] or "",
                                 z["lieferant"] or "", z["basis"] or "", _z(z["alt"], 4), _z(z["neu"], 4),
                                 _pct(z["pct"]), z["herkunft"], z["quelle"])
                                for z in self.zeilen])

    def _kurve(self):
        r = self.tabelle.currentRow()
        if r < 0:
            return
        pid, wid = self.tabelle.item(r, 1).text(), self.tabelle.item(r, 2).text()
        bereich_zeigen(self.seite, "Materialübersicht")
        self.seite.auswaehlen(pid, wid)
        self.seite.detail.setCurrentIndex(self.seite.detail.count() - 1)


def verlauf_zeilen(db):
    """Preisänderungen neueste zuerst: [dict(datum, profil_id, werkstoff_id, lieferant, basis, alt, neu, pct, herkunft,
    quelle)] aus Importhistorie und Preisständen der Stammdaten (preisverlauf)."""
    out = []
    for p in mi.preis_aenderungen(db):
        out.append(dict(datum=p["zeit"], profil_id=p["profil_id"], werkstoff_id=p["werkstoff_id"],
                        lieferant=p["lieferant"], basis=p["basis"], alt=p["alt"], neu=p["neu"], pct=p["pct"],
                        herkunft="ERP-Import" + (" (zurückgenommen)" if "rück" in str(p["status"]) else ""),
                        quelle=Path(str(p["datei"] or "")).name))
    try:
        from . import preisverlauf
        je, k = {}, db.kontext()
        for e in sorted(preisverlauf.eintraege(db.con), key=lambda e: (str(e.get("zeit") or ""), e.get("id") or 0)):
            s = (e.get("art"), e.get("profil_id"), e.get("werkstoff_id"), e.get("laenge"))
            alt = je.get(s)
            je[s] = e
            if alt is None or mp._n(alt.get("preis")) == mp._n(e.get("preis")):
                continue
            a, b = mp._n(alt.get("preis")), mp._n(e.get("preis"))
            basis = e.get("basis")
            if a and b and alt.get("basis") != basis and e.get("profil_id"):
                kgm = mp.kg_je_m(k.profile.get(e.get("profil_id")) or {}, k.werkstoffe.get(e.get("werkstoff_id")) or {})
                a, b = mp.je_meter(alt.get("basis"), a, kgm, 6000), mp.je_meter(basis, b, kgm, 6000)
                basis = "€/m (umgerechnet)"
            out.append(dict(datum=e.get("zeit") or e.get("datum"), profil_id=e.get("profil_id"),
                            werkstoff_id=e.get("werkstoff_id"), lieferant=e.get("lieferant"), basis=basis,
                            alt=a, neu=b, pct=(b / a - 1) * 100 if a and b else None,
                            herkunft="Stammdaten (" + str(e.get("art") or "Preise") + ")", quelle=""))
    except Exception:           # noqa: BLE001  (ohne Preisverlauf: nur Importe)
        from . import protokoll
        protokoll.warnung("Material-Preisverlauf: Preisstände nicht lesbar")
    out.sort(key=lambda z: str(z["datum"] or ""), reverse=True)
    gesehen, rein = set(), []
    for z in sorted(out, key=lambda z: (z["alt"] is None, not str(z["herkunft"]).startswith("ERP"))):
        # mit altem Preis vor ohne, ERP-Import vor Stammdaten
        s = (str(z["datum"] or "")[:10], z["profil_id"], z["werkstoff_id"], round(z["neu"] or 0, 4))
        if s not in gesehen:
            gesehen.add(s)
            rein.append(z)
    rein.sort(key=lambda z: str(z["datum"] or ""), reverse=True)
    return rein


# ------------------------------------------------------------------ Importhistorie
class HistorieSeite(QWidget):
    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        lay = QVBoxLayout(self)
        self.tabelle = _tabelle(["Nr.", "Zeit", "Datei", "Importprofil", "Benutzer", "Zeilen", "neu", "Preise",
                                 "unverändert", "doppelt", "fehlerhaft", "nicht zuordenbar", "Status"])
        self.tabelle.itemSelectionChanged.connect(self._posten)
        lay.addWidget(self.tabelle, 1)
        k = QHBoxLayout()
        self.zurueck = QPushButton("Import rückgängig machen …")
        self.zurueck.clicked.connect(lambda: self.rueckgaengig())
        k.addWidget(self.zurueck)
        k.addStretch(1)
        lay.addLayout(k)
        lay.addWidget(QLabel("<b>Änderungen des markierten Laufs</b>"))
        self.posten = _tabelle(["Tabelle", "Zeile", "Aktion", "alt", "neu"])
        lay.addWidget(self.posten, 1)
        self.laeufe = []

    def neu_laden(self):
        self.laeufe = mi.laeufe(self.seite.db)
        _fuellen(self.tabelle, [(z["id"], str(z["zeit"])[:16].replace("T", " "), Path(str(z["datei"] or "")).name,
                                 z["importprofil"] or "", z["benutzer"] or "", z["zeilen"], z["neu"], z["preise"],
                                 z["unveraendert"], z["doppelt"], z["fehler"], z["offen"], z["status"])
                                for z in self.laeufe])

    def _gewaehlt(self):
        r = self.tabelle.currentRow()
        return int(self.tabelle.item(r, 0).text()) if r >= 0 and self.tabelle.item(r, 0) else None

    def _posten(self):
        i = self._gewaehlt()
        if i is None:
            return
        from .stammdaten import TABELLE
        _fuellen(self.posten, [(TABELLE[p["tabelle"]].titel if p["tabelle"] in TABELLE else p["tabelle"],
                                p["zeilen_id"], {"geaendert": "geändert"}.get(p["aktion"], p["aktion"]),
                                ", ".join(f"{k}={v}" for k, v in (p["alt"] or {}).items()),
                                ", ".join(f"{k}={v}" for k, v in (p["neu"] or {}).items() if k != "_kontext"))
                               for p in mi.posten_des_laufs(self.seite.db, i)])

    def rueckgaengig(self, import_id=None, frage=True):
        import_id = import_id or self._gewaehlt()
        if import_id is None or not self.seite.darf("preise", "materialstamm", "profile"):
            return None
        if frage and not getattr(self.seite.f, "stumm", False):
            if QMessageBox.question(self, "Import rückgängig", f"Importlauf {import_id} vollständig zurücknehmen? "
                                    "Neu angelegte Materialien, Profile und Preise werden gelöscht, geänderte Preise "
                                    "bekommen den alten Wert.") != QMessageBox.Yes:
                return None
        n, meldungen = mi.rueckgaengig(self.seite.db, import_id)
        f = self.seite.window()
        f.alles_neu_laden() if hasattr(f, "alles_neu_laden") else None
        self.seite.neu_laden(erzwingen=True)
        self.neu_laden()
        self.seite.f.meldung(f"Import {import_id} zurückgenommen: {n} Änderungen"
                             + (f", {len(meldungen)} Felder inzwischen von Hand geändert (bleiben)" if meldungen
                                else ""))
        return n, meldungen


# ------------------------------------------------------------------ Einstellungen
class EinstellungenSeite(QWidget):
    """Wichtige Einstellungen der Materialdatenbank mit Sprung in die Einstellungen."""
    NAMEN = ("erp_monate", "erp_ausreisser", "erp_direkt_tage", "erp_direkt_stangen", "erp_werkstoff_vorwahl",
             "funktion_erp_preise", "step_werkstoff", "rest_min_laenge")

    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Einstellungen der Materialdatenbank</b> (ändern unter Einstellungen; Admin-Schutz "
                             "gilt dort)"))
        self.tabelle = _tabelle(["Einstellung", "Wert"])
        lay.addWidget(self.tabelle, 1)
        k = QHBoxLayout()
        for text, ziel in (("Einstellungen ERP-Preisimport öffnen", "e_erp_preise"),
                           ("Tabelle Materialindex öffnen", "material_index")):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, z=ziel: self._oeffnen(z))
            k.addWidget(b)
        k.addStretch(1)
        lay.addLayout(k)

    def neu_laden(self):
        from .stammdaten import EINSTELLUNG
        def wert(v):
            return zahl_als_text(v) if isinstance(v, float) else str(v)
        _fuellen(self.tabelle, [(EINSTELLUNG[n].titel, wert(self.seite.db.einstellung(n)))
                                for n in self.NAMEN if n in EINSTELLUNG])

    def _oeffnen(self, ziel):
        f = self.seite.f
        if ziel == "e_erp_preise" and hasattr(f, "einstellung_zeigen"):
            f.einstellung_zeigen("erp_direkt_tage")
            return
        self.seite.stammdaten_zeigen(ziel)
