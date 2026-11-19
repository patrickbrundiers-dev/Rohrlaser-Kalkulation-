"""Dialoge „Meine Werkzeugleiste konfigurieren“ und „Dashboard anpassen“ (Großes Design- und Layout-Update, Patrick
19.11.2026, Punkte 3.1 und 4).

Konfigurator: links die Aktionsbibliothek nach Bereichen (Suche), rechts drei Listen – Meine Leiste, Kontextknöpfe je
Arbeitsbereich, Schnellzugriffe der Startseite. Ziehen mit der Maus (Drag & Drop) aus der Bibliothek in eine Liste
fügt hinzu, Ziehen in der Liste sortiert; dazu Knöpfe Hinzufügen, Entfernen, ▲/▼ und „Gruppe einfügen“. Für den
gewählten Knopf: eigener Text (umbenennen), Symbol, Farbe, Tastenkürzel. Für die Leiste: Größe, Beschriftung,
sichtbar, Kontextknöpfe an. Admin: als Standard für eine Rolle speichern.

Dashboard: Kachelzeilen oben, Karten links und rechts, ausgeblendete; Ziehen zwischen den Listen ordnet an.
"""
from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGridLayout, QGroupBox, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QTabWidget, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import aktionen
from . import werkzeugleiste as wl
from .werkzeugleiste_qt import icon, pfade

MIME = "application/x-rohrlaser-aktion"
ROLLE = Qt.UserRole             # Eintrag als dict {"id": …} oder {"gruppe": …}


def _text(e):
    if "gruppe" in e:
        return f"──  Gruppe: {e['gruppe']}  ──" if e["gruppe"] else "──────  Trenner  ──────"
    a = aktionen.AKTION.get(e.get("id"))
    titel = e.get("text") or (a.titel if a else e.get("id"))
    zusatz = [x for x in (e.get("farbe") and dict(wl.FARBEN).get(e["farbe"]),) if x]
    return titel + (f"   ({', '.join(zusatz)})" if zusatz else "")


class Bibliothek(QTreeWidget):
    """Aktionsbibliothek nach Bereichen; Einträge lassen sich in die Listen ziehen."""

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.gruppen = {}
        for g in aktionen.GRUPPEN:
            k = QTreeWidgetItem([g])
            k.setFlags(Qt.ItemIsEnabled)
            self.addTopLevelItem(k)
            self.gruppen[g] = k
        for a in aktionen.AKTIONEN:
            if not aktionen.sichtbar(a):
                continue
            it = QTreeWidgetItem([a.titel])
            it.setData(0, ROLLE, a.id)
            it.setIcon(0, icon(a.symbol, 16))
            it.setToolTip(0, a.tipp)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            self.gruppen[a.gruppe].addChild(it)
        for titel, wo in aktionen.NUR_EDITOR:          # nur zur Übersicht: im Menüband des 3D-Editors
            it = QTreeWidgetItem([f"{titel}  (im Menüband des 3D-Editors)"])
            it.setToolTip(0, f"Gilt nur im 3D-Editor: {wo}. Dort im Menüband, nicht in der Hauptleiste.")
            it.setFlags(Qt.NoItemFlags)
            self.gruppen["3D-Editor"].addChild(it)
        self.expandAll()

    def filtern(self, text):
        worte = text.lower().split()
        for k in self.gruppen.values():
            sichtbar = 0
            for i in range(k.childCount()):
                it = k.child(i)
                a = aktionen.AKTION.get(it.data(0, ROLLE))
                such = f"{it.text(0)} {a.tipp if a else ''} {' '.join(a.stichworte) if a else ''} {k.text(0)}".lower()
                zeigen = all(w in such for w in worte)
                it.setHidden(not zeigen)
                sichtbar += zeigen
            k.setHidden(sichtbar == 0)

    def gewaehlt(self):
        it = self.currentItem()
        return it.data(0, ROLLE) if it is not None else None

    def mimeData(self, items):
        m = QMimeData()
        ids = [it.data(0, ROLLE) for it in items if it.data(0, ROLLE)]
        m.setData(MIME, "\n".join(ids).encode())
        return m

    def mimeTypes(self):
        return [MIME]


class KnopfListe(QListWidget):
    """Liste von Einträgen (dict); Drag & Drop: aus der Bibliothek hinzufügen, in der Liste verschieben."""

    def __init__(self, nur_aktionen=False):
        super().__init__()
        self.nur_aktionen = nur_aktionen        # Kontext und Schnellzugriffe: keine Gruppen
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAcceptDrops(True)

    def setzen(self, eintraege):
        self.clear()
        for e in eintraege:
            self.anhaengen(e)

    def anhaengen(self, e, zeile=None):
        if isinstance(e, str):
            e = {"id": e}
        if self.nur_aktionen and "gruppe" in e:
            return None
        if "id" in e and any(x.get("id") == e["id"] for x in self.eintraege()):
            return None                        # jede Aktion nur einmal je Liste
        it = QListWidgetItem(_text(e))
        it.setData(ROLLE, dict(e))
        a = aktionen.AKTION.get(e.get("id"))
        if a is not None:
            it.setIcon(icon(e.get("symbol") or a.symbol, 16))
            it.setToolTip(a.tipp)
        if zeile is None or zeile < 0 or zeile > self.count():
            self.addItem(it)
        else:
            self.insertItem(zeile, it)
        self.setCurrentItem(it)
        return it

    def eintraege(self):
        return [self.item(i).data(ROLLE) for i in range(self.count())]

    def ids(self):
        return [e["id"] for e in self.eintraege() if "id" in e]

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            self.abgelegt(bytes(e.mimeData().data(MIME)).decode(), self.indexAt(e.position().toPoint()).row())
            e.setDropAction(Qt.CopyAction)
            e.accept()
            return
        super().dropEvent(e)

    def abgelegt(self, text, zeile=-1):
        """Aus der Bibliothek abgelegte Aktionen einfügen (zeile < 0: ans Ende)."""
        for n, aid in enumerate(a for a in text.split("\n") if a in aktionen.AKTION):
            self.anhaengen({"id": aid}, zeile + n if zeile >= 0 else None)

    def verschieben(self, schritt):
        r = self.currentRow()
        ziel = r + schritt
        if r < 0 or not 0 <= ziel < self.count():
            return False
        it = self.takeItem(r)
        self.insertItem(ziel, it)
        self.setCurrentRow(ziel)
        return True


class KonfiguratorDialog(QDialog):
    """„Meine Werkzeugleiste konfigurieren“."""

    def __init__(self, f):
        super().__init__(f)
        self.f = f
        self.setWindowTitle("Meine Werkzeugleiste konfigurieren")
        self.resize(980, 640)
        self.aufbau = wl.leiste(f.db)
        lay = QVBoxLayout(self)
        hinweis = QLabel("Aktionen aus der Bibliothek in eine Liste <b>ziehen</b> (oder doppelklicken), in der Liste "
                         "durch Ziehen sortieren. Ausgegraute Knöpfe in der Leiste nennen im Tooltip, wann sie gehen.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        mitte = QHBoxLayout()
        lay.addLayout(mitte, 1)
        links = QVBoxLayout()
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Aktion suchen …")
        self.suche.setClearButtonEnabled(True)
        links.addWidget(self.suche)
        self.bibliothek = Bibliothek()
        self.suche.textChanged.connect(self.bibliothek.filtern)
        self.bibliothek.itemDoubleClicked.connect(lambda *_: self.hinzufuegen())
        links.addWidget(self.bibliothek, 1)
        mitte.addLayout(links, 2)
        knoepfe = QVBoxLayout()
        knoepfe.addStretch(1)
        for text, ziel in (("Hinzufügen ›", self.hinzufuegen), ("‹ Entfernen", self.entfernen),
                           ("▲ Nach oben", lambda: self.liste().verschieben(-1)),
                           ("▼ Nach unten", lambda: self.liste().verschieben(1)),
                           ("Gruppe einfügen …", self.gruppe_einfuegen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            knoepfe.addWidget(b)
            if text.startswith("Gruppe"):
                self.gruppe_knopf = b
        knoepfe.addStretch(1)
        mitte.addLayout(knoepfe)
        rechts = QVBoxLayout()
        self.reiter = QTabWidget()
        self.meine = KnopfListe()
        self.meine.setzen(self.aufbau["knoepfe"])
        self.reiter.addTab(self.meine, "Meine Leiste")
        kontext_seite = QWidget()
        kl = QVBoxLayout(kontext_seite)
        kl.setContentsMargins(0, 4, 0, 0)
        self.kontext_wahl = QComboBox()
        for k, titel in aktionen.KONTEXTE:
            self.kontext_wahl.addItem(titel, k)
        kl.addWidget(self.kontext_wahl)
        self.kontext_liste = KnopfListe(nur_aktionen=True)
        kl.addWidget(self.kontext_liste, 1)
        self.kontext_an = QCheckBox("Kontextabhängige Knöpfe zeigen (rechts in der Leiste, je nach Seite)")
        self.kontext_an.setChecked(self.aufbau.get("kontext_an", True))
        kl.addWidget(self.kontext_an)
        self.kontexte = {k: list(wl.kontext_knoepfe(dict(self.aufbau, knoepfe=[], kontext_an=True), k))
                         for k, _ in aktionen.KONTEXTE}
        self._kontext = None
        self.kontext_wahl.currentIndexChanged.connect(self._kontext_gewechselt)
        self.kontext_wahl.setCurrentIndex(max(0, self.kontext_wahl.findData(aktionen.kontext(f))))
        self._kontext_gewechselt()
        self.reiter.addTab(kontext_seite, "Kontextknöpfe")
        self.schnell = KnopfListe(nur_aktionen=True)
        self.schnell.setzen(wl.schnellzugriffe(f.db))
        self.reiter.addTab(self.schnell, "Schnellzugriffe (Startseite)")
        self.reiter.currentChanged.connect(lambda _: self._auswahl())
        rechts.addWidget(self.reiter, 1)
        # Eigenschaften des gewählten Knopfs
        box = QGroupBox("Gewählter Knopf")
        form = QFormLayout(box)
        self.text_feld = QLineEdit()
        self.text_feld.setPlaceholderText("Standardtext")
        form.addRow("Beschriftung (umbenennen)", self.text_feld)
        self.symbol_wahl = QComboBox()
        self.symbol_wahl.addItem("(Standard)", "")
        for name in sorted(pfade()):
            self.symbol_wahl.addItem(icon(name, 16), name, name)
        form.addRow("Symbol", self.symbol_wahl)
        self.farbe_wahl = QComboBox()
        for wert, titel in wl.FARBEN:
            self.farbe_wahl.addItem(titel, wert)
        form.addRow("Farbe", self.farbe_wahl)
        self.taste = QKeySequenceEdit()
        self.taste.setMaximumSequenceLength(1)
        self.tasten = dict(self.aufbau.get("tasten") or {})
        tz = QHBoxLayout()
        tz.addWidget(self.taste, 1)
        weg = QPushButton("Löschen")
        weg.clicked.connect(self.taste.clear)
        tz.addWidget(weg)
        form.addRow("Tastenkürzel", tz)
        self.box = box
        rechts.addWidget(box)
        self.text_feld.textEdited.connect(lambda _: self._eigenschaft())
        self.symbol_wahl.activated.connect(lambda _: self._eigenschaft())
        self.farbe_wahl.activated.connect(lambda _: self._eigenschaft())
        self.taste.editingFinished.connect(self._eigenschaft)
        for liste in (self.meine, self.kontext_liste, self.schnell):
            liste.currentItemChanged.connect(lambda *_: self._auswahl())
        # Leiste als Ganzes
        ganz = QGroupBox("Leiste")
        g = QGridLayout(ganz)
        self.groesse = QComboBox()
        for wert, titel, _ in wl.GROESSEN:
            self.groesse.addItem(titel, wert)
        self.groesse.setCurrentIndex(self.groesse.findData(self.aufbau["groesse"]))
        self.beschriftung = QComboBox()
        for wert, titel in wl.BESCHRIFTUNGEN:
            self.beschriftung.addItem(titel, wert)
        self.beschriftung.setCurrentIndex(self.beschriftung.findData(self.aufbau["beschriftung"]))
        self.sichtbar = QCheckBox("Leiste anzeigen")
        self.sichtbar.setChecked(self.aufbau.get("sichtbar", True))
        g.addWidget(QLabel("Größe"), 0, 0)
        g.addWidget(self.groesse, 0, 1)
        g.addWidget(QLabel("Beschriftung"), 1, 0)
        g.addWidget(self.beschriftung, 1, 1)
        g.addWidget(self.sichtbar, 2, 0, 1, 2)
        rechts.addWidget(ganz)
        mitte.addLayout(rechts, 3)
        unten = QHBoxLayout()
        b = QPushButton("Standard wiederherstellen")
        b.setToolTip("Eigene Leiste verwerfen: es gilt die Vorgabe für die eigene Rolle bzw. das Standardlayout")
        b.clicked.connect(self.standard)
        unten.addWidget(b)
        self.rolle_wahl = QComboBox()
        self.rolle_knopf = QPushButton("Als Standard für Rolle speichern")
        self.rolle_knopf.setToolTip("Admin: diese Leiste, das Dashboard und die Schnellzugriffe gelten für alle "
                                    "Benutzer der Rolle, die keine eigene Oberfläche eingerichtet haben (über den "
                                    "gemeinsamen Ordner an allen Plätzen)")
        self.rolle_knopf.clicked.connect(self.als_rollenvorgabe)
        from . import rollen
        for r, titel in rollen.ROLLEN:
            self.rolle_wahl.addItem(titel, r)
        admin = self._admin()
        self.rolle_wahl.setVisible(admin)
        self.rolle_knopf.setVisible(admin)
        unten.addWidget(self.rolle_wahl)
        unten.addWidget(self.rolle_knopf)
        unten.addStretch(1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        unten.addWidget(knoepfe)
        lay.addLayout(unten)
        self._auswahl()

    def _admin(self):
        try:
            from . import admin_schutz
            return not admin_schutz.aktiv(self.f.db) or admin_schutz.ist_admin(self.f.db)
        except Exception:           # noqa: BLE001
            return False

    # -------------------------------------------------------------- Listen
    def liste(self):
        return {0: self.meine, 1: self.kontext_liste, 2: self.schnell}[self.reiter.currentIndex()]

    def _kontext_gewechselt(self, *_):
        if self._kontext is not None:
            self.kontexte[self._kontext] = self.kontext_liste.ids()
        self._kontext = self.kontext_wahl.currentData()
        self.kontext_liste.setzen(self.kontexte.get(self._kontext, []))

    def hinzufuegen(self, aid=None):
        aid = aid or self.bibliothek.gewaehlt()
        if aid not in aktionen.AKTION:
            return None
        return self.liste().anhaengen({"id": aid})

    def entfernen(self):
        liste = self.liste()
        r = liste.currentRow()
        if r >= 0:
            liste.takeItem(r)

    def gruppe_einfuegen(self, titel=None):
        if self.liste() is not self.meine:
            self.reiter.setCurrentWidget(self.meine)
        if titel is None and not self.f.stumm:
            from PySide6.QtWidgets import QInputDialog
            titel, ok = QInputDialog.getText(self, "Gruppe einfügen", "Titel der Gruppe (leer = nur Trennstrich):")
            if not ok:
                return None
        r = self.meine.currentRow()
        return self.meine.anhaengen({"gruppe": titel or ""}, r + 1 if r >= 0 else None)

    def _auswahl(self):
        it = self.liste().currentItem()
        e = it.data(ROLLE) if it is not None else None
        knopf = e is not None and "id" in e
        self.box.setEnabled(knopf)
        eigene = self.liste() is self.meine
        self.gruppe_knopf.setEnabled(True)
        for w in (self.text_feld, self.symbol_wahl, self.farbe_wahl):
            w.setEnabled(knopf and eigene)
        self.text_feld.setText((e or {}).get("text", "") if knopf else "")
        self.text_feld.setPlaceholderText(aktionen.AKTION[e["id"]].titel if knopf else "")
        self.symbol_wahl.setCurrentIndex(max(0, self.symbol_wahl.findData((e or {}).get("symbol", ""))))
        self.farbe_wahl.setCurrentIndex(max(0, self.farbe_wahl.findData((e or {}).get("farbe", ""))))
        self.taste.setKeySequence(QKeySequence(self.tasten.get(e["id"], "")) if knopf else QKeySequence())

    def _eigenschaft(self):
        it = self.liste().currentItem()
        if it is None or "id" not in (it.data(ROLLE) or {}):
            return
        e = dict(it.data(ROLLE))
        if self.liste() is self.meine:
            for name, wert in (("text", self.text_feld.text().strip()), ("symbol", self.symbol_wahl.currentData()),
                               ("farbe", self.farbe_wahl.currentData())):
                if wert:
                    e[name] = wert
                else:
                    e.pop(name, None)
            it.setData(ROLLE, e)
            it.setText(_text(e))
            a = aktionen.AKTION[e["id"]]
            it.setIcon(icon(e.get("symbol") or a.symbol, 16))
        taste = self.taste.keySequence().toString(QKeySequence.PortableText)
        if taste:
            self.tasten[e["id"]] = taste
        else:
            self.tasten.pop(e["id"], None)

    # -------------------------------------------------------------- Ergebnis
    def ergebnis(self):
        self._kontext_gewechselt()
        kontext = {k: v for k, v in self.kontexte.items() if v != wl.KONTEXT_VORGABE.get(k, [])}
        return {"knoepfe": self.meine.eintraege(), "kontext": kontext, "kontext_an": self.kontext_an.isChecked(),
                "groesse": self.groesse.currentData(), "beschriftung": self.beschriftung.currentData(),
                "tasten": self.tasten, "sichtbar": self.sichtbar.isChecked()}

    def konflikte(self):
        from .werkzeugleiste_qt import vorhandene_tasten
        return wl.tasten_konflikte(self.tasten, vorhandene_tasten(self.f))

    def accept(self):
        konflikte = self.konflikte()
        if konflikte and not self.f.stumm:
            text = "\n".join(f"{QKeySequence(t).toString(QKeySequence.NativeText)}: "
                             f"{aktionen.AKTION[a].titel} – schon belegt durch „{m}“" for a, t, m in konflikte)
            if QMessageBox.warning(self, "Tastenkürzel", f"Diese Tastenkürzel sind doppelt belegt:\n\n{text}\n\n"
                                   "Trotzdem übernehmen? (Dann gilt keines der doppelten.)",
                                   QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
        super().accept()

    def uebernehmen(self):
        from . import werkzeugleiste_qt
        wl.leiste_setzen(self.f.db, self.ergebnis())
        wl.schnellzugriffe_setzen(self.f.db, self.schnell.ids())
        werkzeugleiste_qt.aendern(self.f)

    def standard(self):
        lst = wl.vorgabe(self.f.db)
        self.meine.setzen(lst["knoepfe"])
        self.kontexte = {k: list(wl.KONTEXT_VORGABE.get(k, [])) for k, _ in aktionen.KONTEXTE}
        self._kontext = None
        self._kontext_gewechselt()
        self.schnell.setzen(wl.SCHNELL_VORGABE)
        self.tasten = {}
        self.groesse.setCurrentIndex(self.groesse.findData(lst["groesse"]))
        self.beschriftung.setCurrentIndex(self.beschriftung.findData(lst["beschriftung"]))
        self.sichtbar.setChecked(True)
        self.kontext_an.setChecked(True)

    def als_rollenvorgabe(self, rolle=None):
        rolle = rolle or self.rolle_wahl.currentData()
        wl.vorgabe_setzen(self.f.db, rolle, {"leiste": self.ergebnis(), "startseite": wl.startseite(self.f.db),
                                             "schnell": self.schnell.ids()})
        from . import rollen
        self.f.meldung(f"Standardlayout für die Rolle „{rollen.ROLLE_TITEL.get(rolle, rolle)}“ gespeichert.")
        return rolle


# ------------------------------------------------------------------ Dashboard anpassen
class StartseiteDialog(QDialog):
    """Karten der Startseite: oben (Kachelzeilen), links, rechts, ausgeblendet; per Drag & Drop anordnen."""

    def __init__(self, f):
        super().__init__(f)
        self.f = f
        self.setWindowTitle("Dashboard anpassen")
        self.resize(820, 460)
        lay = QVBoxLayout(self)
        hinweis = QLabel("Karten mit der Maus zwischen den Spalten <b>ziehen</b>: oben die Kennzahl-Zeilen, darunter "
                         "zwei Spalten. Was unter „Ausgeblendet“ liegt, erscheint nicht auf der Startseite.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        raster = QGridLayout()
        lay.addLayout(raster, 1)
        anordnung = wl.startseite(f.db)
        self.listen = {}
        for n, (bereich, titel) in enumerate((("oben", "Oben (Kennzahlen)"), ("links", "Linke Spalte"),
                                              ("rechts", "Rechte Spalte"), ("aus", "Ausgeblendet"))):
            raster.addWidget(QLabel(f"<b>{titel}</b>"), 0, n)
            liste = QListWidget()
            liste.setDragDropMode(QAbstractItemView.DragDrop)
            liste.setDefaultDropAction(Qt.MoveAction)
            liste.setWordWrap(True)
            karten = anordnung.get(bereich) if bereich != "aus" else wl.ausgeblendet(anordnung)
            for karte in karten:
                self._eintrag(liste, karte)
            raster.addWidget(liste, 1, n)
            self.listen[bereich] = liste
        zeile = QHBoxLayout()
        for text, schritt in (("▲", -1), ("▼", 1)):
            b = QPushButton(text)
            b.setToolTip("Gewählte Karte in ihrer Spalte verschieben")
            b.clicked.connect(lambda _=False, schritt=schritt: self.verschieben(schritt))
            zeile.addWidget(b)
        b = QPushButton("Standard")
        b.clicked.connect(self.standard)
        zeile.addWidget(b)
        zeile.addStretch(1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        zeile.addWidget(knoepfe)
        lay.addLayout(zeile)

    @staticmethod
    def _eintrag(liste, karte):
        it = QListWidgetItem(wl.KARTE_TITEL[karte])
        it.setData(ROLLE, karte)
        liste.addItem(it)
        return it

    def setzen(self, anordnung):
        for liste in self.listen.values():
            liste.clear()
        for bereich in ("oben", "links", "rechts"):
            for karte in anordnung.get(bereich, ()):
                self._eintrag(self.listen[bereich], karte)
        for karte in wl.ausgeblendet(wl.start_sauber(anordnung)):
            self._eintrag(self.listen["aus"], karte)

    def standard(self):
        self.setzen(wl.START_VORGABE)

    def verschieben(self, schritt):
        for liste in self.listen.values():
            r = liste.currentRow()
            if liste.hasFocus() or (r >= 0 and liste.currentItem().isSelected()):
                ziel = r + schritt
                if 0 <= ziel < liste.count():
                    liste.insertItem(ziel, liste.takeItem(r))
                    liste.setCurrentRow(ziel)
                return

    def ergebnis(self):
        """Anordnung; falsch abgelegte Karten rücken in ihren Bereich (Kachelzeilen nur oben, Karten nicht oben)."""
        aus = {b: [self.listen[b].item(i).data(ROLLE) for i in range(self.listen[b].count())]
               for b in ("oben", "links", "rechts")}
        for karte in [k for k in aus["oben"] if k not in wl.OBEN_KARTEN]:
            aus["oben"].remove(karte)
            aus["rechts"].append(karte)
        for b in ("links", "rechts"):
            for karte in [k for k in aus[b] if k in wl.OBEN_KARTEN]:
                aus[b].remove(karte)
                aus["oben"].append(karte)
        return wl.start_sauber(aus)

    def uebernehmen(self):
        wl.startseite_setzen(self.f.db, self.ergebnis())
        if hasattr(self.f.start, "karten_anordnen"):
            self.f.start.karten_anordnen()

