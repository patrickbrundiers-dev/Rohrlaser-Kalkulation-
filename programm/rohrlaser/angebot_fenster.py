"""Angebote: Übersicht, Angebotsbearbeitung (Kopf, Positionen), STEP-Import, Optimierung, Ergebnisse."""
import copy
import datetime
import functools
import json
import shutil
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QSize, QEvent, QEventLoop, QItemSelectionModel, QModelIndex, QPointF, QProcess, QRectF, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QKeySequence, QPainter, QPen, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QFormLayout, QInputDialog, QMenu, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressDialog, QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableView,
    QTabWidget, QTextBrowser, QToolTip,
    QVBoxLayout, QWidget)

from . import abmessung, anbau, profil_neu, blech, dreid, fracht_angebot, ausgabe, export, materialanfrage, naht, pdf, rechnen, schneidweg, step, tastatur, \
    teilen, virtuell, vorschau, zukauf, zukauf_ek, baugruppe, bg_mengen
from .nachkalk_seite import NachkalkulationSeite
from .staffel_seite import StaffelSeite
from . import plausibel, zusatz_dialog
from .zusatz_dialog import ZusatzDialog
from .schneidweg_dialog import SchneidwegDialog, gewinde_liste
from .naht_dialog import NahtDialog
from .baugruppe_dialog import BaugruppeDialog
from .zukauf_dialog import ZukaufDialog, datum_text
from .zukauf_schnell import SchnellDialog, artikel_werte
from .zeiten_seite import ZeitenSeite
from .datenbank import VORGAENGE
from .angebot import BAUGRUPPE, EIGENMATERIAL, POSITIONEN, STEP_FELDER, ZUKAUFTEIL, aktiv as position_aktiv, ist_baugruppe, \
    ist_muster, ist_zukaufteil, kein_laserteil
from .angebot_oben import KALK_NAMEN, KALK_OFFEN_EINSTELLUNG, KopfBereich, UebersichtBereich, UebersichtRahmen, _kundennr
from .sichtbarkeit import sichtbar, spalte_sichtbar
from .angebot_spalten import AUSW_SPALTEN, FEHLER_SPALTEN, KALK_SPALTEN, KOMPAKT_SPALTEN, STANGEN_SPALTEN, TEIL_SPALTEN, \
    kompakt_zeilen
from .leiste import UmbruchLeiste
from . import angebot_check, angebotsordner, nummern as angebotsnummern, optimierung as opt, reihenfolge, schritte, step_ablage, \
    step_einstellungen, stil, tabellen_eingabe, teile_editor, vorkalk
from .schritte import Schrittanzeige
from .stangen_ansicht import UEBERSICHT as STANGEN_UEBERSICHT, StangenSeite
from .teile_baum import TeileBaum
from . import funktionen, muster_haken, stangen_abwicklung, vollmaterial
from .step_ablage import AblageFeld
from .fenster import FARBE_BERECHNET, FARBE_EINGABE, FARBE_STATUS, Auswahl, Sortierung
from .spaltenbreite import AutoGroesse
from . import position_kopie, satzgruppen, unterzeilen
from .unterzeilen import Unterzeilen, UnterzeilenDelegat, UnterzeilenMixin
from .verlauf import Verlauf
from .stammdaten import ZEITRAUM, ZEITRAUM_ALLE, wert_aus_text, wert_als_text, zahl_als_text


def preis_aenderung(vorher, nachher):
    """Kurztext zur Preisänderung, z. B. 'Verkaufspreis netto 1.234,00 € → 1.290,50 €.'"""
    if vorher is None or nachher is None:
        return ""
    if abs(vorher - nachher) < 0.005:
        return f"Verkaufspreis netto unverändert {zahl_als_text(vorher, 2)} €."
    return f"Verkaufspreis netto {zahl_als_text(vorher, 2)} € → {zahl_als_text(nachher, 2)} €."


def _z(w, stellen=2):
    return zahl_als_text(w, stellen) if isinstance(w, (int, float)) and not isinstance(w, bool) else ("" if w is None else str(w))


def _farbe_status(text):
    return FARBE_STATUS.get(str(text).split(":")[0])


def _tabelle(modell, sortieren=True):
    v = QTableView()
    if sortieren and not isinstance(modell, Sortierung):
        proxy = Sortierung(v)
        proxy.setSourceModel(modell)
        modell = proxy
    v.setModel(modell)
    v.setSelectionBehavior(QAbstractItemView.SelectRows)
    v.setSortingEnabled(sortieren)
    v.sortByColumn(-1, Qt.AscendingOrder)   # zuerst in der gelieferten Reihenfolge (Pos. aufsteigend)
    kopf = v.horizontalHeader()
    kopf.setDefaultAlignment(Qt.AlignCenter | Qt.TextWordWrap)
    kopf.setMinimumHeight(48)
    v.verticalHeader().setDefaultSectionSize(22)
    AutoGroesse(v)                  # Breite und Höhe passend zum Inhalt (spaltenbreite.py)
    return v


LISTE_ROLLEN = frozenset((Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.UserRole, Qt.ItemDataRole.TextAlignmentRole, Qt.ItemDataRole.BackgroundRole,
                          Qt.ItemDataRole.ForegroundRole, Qt.ItemDataRole.FontRole))


class Liste(QAbstractTableModel):
    """Nur-Lese-Tabelle aus dicts. spalten: [(Titel, Schlüssel oder Funktion(zeile), Nachkommastellen, Breite)]."""

    def __init__(self, spalten, zeilen=(), max_stellen=None):
        super().__init__()
        self.spalten, self.zeilen = spalten, list(zeilen)
        self.max_stellen = max_stellen      # Anzeige höchstens so viele Nachkommastellen, Tooltip genau

    def setzen(self, zeilen):
        self.beginResetModel()
        self.zeilen = list(zeilen)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.zeilen)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.spalten)

    def headerData(self, abschnitt, richtung, rolle=Qt.ItemDataRole.DisplayRole):
        if rolle == Qt.ItemDataRole.DisplayRole:
            return self.spalten[abschnitt][0] if richtung == Qt.Horizontal else str(abschnitt + 1)
        return None

    def wert(self, r, c):
        schl = self.spalten[c][1]
        z = self.zeilen[r]
        return schl(z) if callable(schl) else z.get(schl)

    def data(self, index, rolle=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or rolle not in LISTE_ROLLEN:     # andere Rollen fragt Qt oft ab, Antwort immer None
            return None
        w = self.wert(index.row(), index.column())
        stellen = self.spalten[index.column()][2]
        if rolle in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if isinstance(w, datetime.datetime):
                return w.strftime("%d.%m.%Y %H:%M")
            if stellen is not None and self.max_stellen is not None and rolle == Qt.ItemDataRole.DisplayRole:
                stellen = min(stellen, self.max_stellen)
            return _z(w, stellen) if stellen is not None else ("" if w is None else str(w))
        if rolle == Qt.ItemDataRole.UserRole:
            return w
        if rolle == Qt.ItemDataRole.TextAlignmentRole and isinstance(w, (int, float)) and not isinstance(w, bool):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.ItemDataRole.BackgroundRole and isinstance(w, str):
            f = _farbe_status(w) or ({"ÜBERBELEGT": FARBE_STATUS["FEHLER"]}.get(w))
            if f is not None:
                return QBrush(f)
        # Zeilen eines Satzes getönt, Satzname fett in der Farbe des Satzes (satzgruppen.zeilen_markieren)
        z = self.zeilen[index.row()] if index.row() < len(self.zeilen) else None
        ton = z.get("satz_ton") if isinstance(z, dict) else None
        if ton is None:
            return None
        if rolle == Qt.ItemDataRole.BackgroundRole:
            return QBrush(satzgruppen.mischen(stil.farbe("#FFFFFF"), stil.farbe(satzgruppen.FLAECHEN[ton])))
        if self.spalten[index.column()][1] == "satz":
            if rolle == Qt.ItemDataRole.ForegroundRole:
                return QBrush(stil.farbe(satzgruppen.TEXTE[ton]))
            if rolle == Qt.ItemDataRole.FontRole:
                f = QFont()
                f.setBold(True)
                return f
        return None


def leere_ausblenden(ansicht, liste, immer=()):
    """Spalten ohne Wert in allen Zeilen (0, leer) ausblenden wie in der Positionsliste (sichtbarkeit.py); Spalten
    mit Schlüssel in immer bleiben. Ergebnis: Anzahl ausgeblendeter Spalten."""
    n = 0
    for c, sp in enumerate(liste.spalten):
        zeigen = (not liste.zeilen or sp[1] in immer
                  or spalte_sichtbar([liste.wert(r, c) for r in range(len(liste.zeilen))]))
        ansicht.setColumnHidden(c, not zeigen)
        n += not zeigen
    return n


def gleiche_ausblenden(ansicht, liste, schluessel):
    """Spalten (Schlüssel aus schluessel), die in allen Zeilen denselben Wert haben, ausblenden; Ergebnis: Text
    'Titel Wert' je ausgeblendeter Spalte für eine Zeile über der Tabelle (Gleiches steht nur einmal da)."""
    teile = []
    for c, sp in enumerate(liste.spalten):
        if sp[1] not in schluessel:
            continue
        werte = {liste.data(liste.index(r, c)) for r in range(len(liste.zeilen))}
        gleich = len(liste.zeilen) > 1 and len(werte) == 1
        ansicht.setColumnHidden(c, gleich)
        if gleich:
            titel, einheit = sp[0], ""
            if "[" in titel:
                titel, einheit = titel.split("[", 1)
                einheit = " " + einheit.rstrip("]")
            teile.append(f"{titel.strip()} <b>{werte.pop()}{einheit}</b>")
    return teile


def _breiten(ansicht, spalten):
    for i, s in enumerate(spalten):
        ansicht.setColumnWidth(i, s[3] if len(s) > 3 else 90)


# ------------------------------------------------------------------ Übersicht der Angebote
# Stand eines Angebots in der Liste: Text und Farbe (wie die Etiketten in der Übersicht des Angebots)
STATUS_FARBE = {"Nachkalkuliert": "#DDEBF7", "Optimiert": "#E3F4E8", "Veraltet": "#FDECEA",
                "Nicht optimiert": "#FFF6DB"}
VORGANG_FARBE = {"Verschickt": "#DDEBF7", "Beauftragt": "#E3F4E8", "Abgelehnt": "#ECEEF1", "Abgelaufen": "#FDECEA",
                 "Ersetzt": "#ECEEF1"}
# Filter der Angebotsliste: Titel -> Prüfung je Zeile (Vorgang, abgelaufen)
# Filter der Angebotsliste: (Vorgang, abgelaufen, Zeile der Liste) -> zeigen
VORGANG_FILTER = {"Alle Angebote": lambda v, ab, z: True,
                  "Offen (Entwurf, Verschickt)": lambda v, ab, z: v in ("Entwurf", "Verschickt"),
                  "Entwurf": lambda v, ab, z: v == "Entwurf", "Verschickt": lambda v, ab, z: v == "Verschickt",
                  "Verschickt und abgelaufen": lambda v, ab, z: v == "Verschickt" and ab,
                  # Plan A9: wie die Wiedervorlage der Startseite (nachfassen, Gültigkeit endet, Datum von Hand)
                  "Wiedervorlage fällig": lambda v, ab, z: bool(z.get("_wv")),
                  "Beauftragt": lambda v, ab, z: v == "Beauftragt",
                  # Plan Arbeitsabläufe W9: beauftragt, aber noch ohne Ist-Werte (eine Bemerkung allein zählt nicht)
                  "Nachkalkulation offen": lambda v, ab, z: v == "Beauftragt" and not z.get("ist_erfasst"),
                  "Abgelehnt": lambda v, ab, z: v == "Abgelehnt",
                  "Ersetzt (alte Fassungen)": lambda v, ab, z: v == "Ersetzt"}


ERSETZT = "Ersetzt"      # alte Fassung (Plan Arbeitsabläufe W10, angebote.ersetzt_durch), kein eigener Vorgang


def vorgang(z):
    if z.get("ersetzt_durch"):
        return ERSETZT
    return z.get("vorgang") or VORGAENGE[0]


def gueltig_bis(z, tage):
    """Datum, bis zu dem das Angebot gilt (Angebotsdatum + Gültigkeit in Tagen), None ohne Datum."""
    try:
        return datetime.date.fromisoformat(z.get("datum") or "") + datetime.timedelta(days=int(tage or 0))
    except (ValueError, TypeError):
        return None


def abgelaufen(z, tage, heute=None):
    """Verschicktes Angebot, dessen Gültigkeit vorbei ist (Entwurf, Beauftragt, Abgelehnt laufen nicht ab)."""
    g = gueltig_bis(z, tage)
    return vorgang(z) == "Verschickt" and g is not None and g < (heute or datetime.date.today())


def offener_auftrag(z, heute=None):
    """Beauftragt und noch nicht versendet (wie Versand → Aktuell: nicht archiviert, auch nicht automatisch);
    bleibt in der Angebotsliste trotz Zeitraum sichtbar."""
    from . import palettenschein
    if vorgang(z) != "Beauftragt":
        return False
    d = palettenschein.lesen(z.get("_schein"))
    return not palettenschein.ist_versendet(d) and not palettenschein.archiviert(z, d, heute)


def angebot_status(z):
    """'Nachkalkuliert', 'Optimiert', 'Veraltet' oder 'Nicht optimiert'; ohne gemerkten Stand (Angebot seit dem
    Update nicht geöffnet) zählt, ob es ein Optimierungsergebnis gibt."""
    if z.get("nachkalkuliert"):
        return "Nachkalkuliert"
    if not z.get("optimiert_am") or z.get("stand") == "offen":
        return "Nicht optimiert"
    return "Veraltet" if z.get("stand") == "veraltet" else "Optimiert"


class AngeboteListe(Liste):
    EIGENE_ROLLEN = frozenset((Qt.ItemDataRole.ForegroundRole, Qt.ItemDataRole.FontRole, Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ToolTipRole))

    def data(self, index, rolle=Qt.ItemDataRole.DisplayRole):
        if rolle not in self.EIGENE_ROLLEN:        # schneller Weg für die übrigen Rollen (Liste.data)
            return super().data(index, rolle)
        if rolle == Qt.ItemDataRole.ForegroundRole and index.isValid() and self.zeilen[index.row()].get("fremd"):
            return QBrush(stil.farbe(FREMD_FARBE))          # Angebote anderer Mitarbeiter: grau, nur zum Ansehen
        if rolle == Qt.ItemDataRole.FontRole and index.isValid() and self.zeilen[index.row()].get("fremd"):
            f = QFont()
            f.setItalic(True)
            return f
        if rolle == Qt.ItemDataRole.BackgroundRole and index.isValid() and self.spalten[index.column()][0] in ("Status", "Vorgang"):
            w = self.wert(index.row(), index.column())
            farbe = STATUS_FARBE.get(w) or VORGANG_FARBE.get(str(w).split(" ")[0])
            return QBrush(stil.farbe(farbe)) if farbe else None
        if rolle == Qt.ItemDataRole.ToolTipRole and index.isValid() and self.spalten[index.column()][0] == "Vorgang":
            from .absage import letzte
            a = letzte(self.zeilen[index.row()]) if str(self.wert(index.row(), index.column())).startswith(
                "Abgelehnt") else None
            if a:
                return f"Absagegrund: {a.get('grund')}" + (f" – {a['bemerkung']}" if a.get("bemerkung") else "")
        if rolle == Qt.ItemDataRole.ToolTipRole and index.isValid() and self.spalten[index.column()][1] == "vk_netto":
            am = self.zeilen[index.row()].get("vk_am")
            return (f"Stand vom {_zeit(am)} (zuletzt beim Öffnen des Angebots gerechnet)" if am else
                    "Wird beim Öffnen des Angebots gerechnet")
        return super().data(index, rolle)


FREMD_FARBE = "#6B7280"


def bearbeiter(z):
    """Kürzel des Bearbeiters; Angebote eines Kollegen ohne Kürzel (vor 0.8.30 angelegt): das Kürzel seiner Datei."""
    return z.get("bearbeiter") or z.get("fremd") or ""
MEINE, ALLE = "Meine Angebote", "Alle Mitarbeiter"
SUCHE_PAUSE_MS = 250


FASSUNG = object()        # Ergebnis des Kopieren-Dialogs: neue Fassung statt Kopie


def step_neu_pfade(ereignis):
    """Gezogene Dateien/Ordner, wenn STEP-Dateien oder Ordner darunter sind (Angebotsliste, Startseite), sonst [].
    Ordner werden hier nicht durchsucht (das stockt beim Ziehen), sondern erst nach dem Ablegen."""
    urls = ereignis.mimeData().urls() if ereignis.mimeData().hasUrls() else []
    pfade = [u.toLocalFile() for u in urls if u.isLocalFile()]
    mail = any(Path(p).suffix.lower() in (".msg", ".eml", ".zip") for p in pfade)  # E-Mail/ZIP mit STEP (28.10.2026)
    return pfade if step.step_kandidaten(pfade) or mail else []


def step_drop(fenster, ereignis, ziel, aufruf):
    """Abgelegte STEP-Dateien: Drop sofort annehmen und den Import erst danach starten. Windows hält den Explorer
    fest, bis dropEvent zurückkehrt – liefe der Import (Messung, Prüfdialog) darin, hinge der Explorer so lange.
    Während ein Import läuft, wird ein weiterer Drop mit Hinweis abgelehnt. ziel: Widget, dessen Fenster nach vorne
    kommt; aufruf: startet den Import. Ergebnis: True = angenommen."""
    if fenster.step_drop_laeuft:
        ereignis.ignore()
        fenster.meldung("Es läuft schon ein STEP-Import. Bitte erst diesen abschließen.", fehler=True)
        return False
    ereignis.acceptProposedAction()
    fenster.step_drop_laeuft = True

    def starten():
        try:
            if not fenster.stumm:       # Explorer liegt meist vorne: Programm nach vorne holen (Prüfdialog)
                ziel.window().raise_()
                ziel.window().activateWindow()
            aufruf()
        finally:
            fenster.step_drop_laeuft = False
    QTimer.singleShot(0, starten)
    return True


class AngeboteSeite(QWidget):
    oeffnen = Signal(int)
    KUERZEL = {"neu": "neu", "loeschen": ("loeschen", "ansicht")}     # Tastenkürzel, siehe tastatur.py

    SPALTEN = [("Angebotsnummer", "nummer", None, 120),
               ("Bearbeiter", lambda z: bearbeiter(z) + (" ● geöffnet" if z.get("_offen") else ""), None, 70),
               ("Kunde", "kunde", None, 200), ("Kundennr.", "kundennr", None, 90),
               ("Datum", lambda z: _datum(z.get("datum")), None, 85),
               ("Vorgang", lambda z: (f"Ersetzt durch {z['ersetzt_durch']}" if z.get("ersetzt_durch") else
                                      vorgang(z) + (" (abgelaufen)" if z.get("_abgelaufen") else "")), None, 140),
               ("Gültig bis", lambda z: _datum(z["_gueltig"].isoformat()) if z.get("_gueltig") else "", None, 85),
               ("Auftragsnr.", "auftragsnr", None, 100),
               ("Liefertermin", lambda z: _datum(z.get("liefertermin")), None, 85),
               ("Status", lambda z: angebot_status(z), None, 120),
               ("Verkaufspreis netto [€]", "vk_netto", 2, 110), ("Maschine", "maschine", None, 70),
               ("Positionen", "positionen", 0, 70), ("Teile", "teile", 0, 70),
               ("Optimiert am", lambda z: _zeit(z.get("optimiert_am")), None, 120),
               ("Geändert am", lambda z: _zeit(z.get("geaendert")), None, 120),
               ("Nachkalkuliert", lambda z: "ja" if z.get("nachkalkuliert") else "", None, 85)]

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.modell = AngeboteListe(self.SPALTEN)
        self.filter = Sortierung()
        self.filter.setSourceModel(self.modell)
        self.ansicht = _tabelle(self.filter)
        self.ansicht.setEditTriggers(QAbstractItemView.NoEditTriggers)
        _breiten(self.ansicht, self.SPALTEN)
        self.ansicht.doubleClicked.connect(lambda i: self.oeffnen.emit(self._id(i)))
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen nach Angebot, Kunde, Artikel, Auftragsnummer …")
        self.suche.setClearButtonEnabled(True)
        # Suche erst nach einer kurzen Tipp-Pause (Performance-Audit F1): nicht bei jeder Taste die ganze Liste
        self._such_timer = QTimer(self)
        self._such_timer.setSingleShot(True)
        self._such_timer.setInterval(SUCHE_PAUSE_MS)
        self._such_timer.timeout.connect(self.neu_laden)
        self.suche.textChanged.connect(self._such_timer.start)
        tastatur.suche_esc(self.suche)
        self.vorgang_filter = QComboBox()
        self.vorgang_filter.addItems(list(VORGANG_FILTER))
        self.vorgang_filter.setToolTip("Angebote nach Vorgang zeigen; abgelaufen = verschickt und Gültigkeit vorbei")
        self.vorgang_filter.currentTextChanged.connect(self.neu_laden)
        # Zeitraum (Patrick 29.10.2026): ältere Angebote ausblenden, Vorgabe in den Einstellungen → Angebot
        self.zeitraum_filter = QComboBox()
        self.zeitraum_filter.addItems(list(ZEITRAUM))
        self.zeitraum_filter.setToolTip("Nur Angebote mit Datum oder Änderung in diesem Zeitraum zeigen. Fällige "
                                        "Wiedervorlagen, nicht versendete Aufträge und geöffnete Angebote bleiben "
                                        "immer sichtbar, die Suche findet alle.")
        self._zeitraum_vorgabe = None
        self.zeitraum_filter.currentTextChanged.connect(self.neu_laden)
        self.zeitraum_hinweis = QLabel()
        self.zeitraum_hinweis.setObjectName("kennzahltitel")
        self.zeitraum_hinweis.setTextFormat(Qt.RichText)
        self.zeitraum_hinweis.linkActivated.connect(lambda _: self.zeitraum_filter.setCurrentText(ZEITRAUM_ALLE))
        self.zeitraum_hinweis.hide()
        # Mehrere Arbeitsplätze (teilen.py): eigene Angebote, alle oder die eines Kollegen
        self.wer_filter = QComboBox()
        self.wer_filter.setToolTip("Eigene Angebote, alle oder die eines Kollegen zeigen. Angebote der Kollegen "
                                   "(grau) lassen sich ansehen und als Kopie übernehmen.")
        self.wer_filter.currentTextChanged.connect(self.neu_laden)
        self.abgleich_knopf = QPushButton("Abgleichen")
        self.abgleich_knopf.setToolTip("Eigene Angebote in den gemeinsamen Ordner legen und Angebote und Stammdaten "
                                       "der Kollegen holen (auch beim Start und Beenden)")
        self.abgleich_knopf.clicked.connect(lambda: self.f.abgleichen())
        self.vorgang_knopf = QPushButton("Vorgang ▾")
        self.vorgang_knopf.setToolTip("Vorgang des gewählten Angebots setzen: Entwurf, Verschickt (setzt das "
                                      "Angebots-PDF selbst), Beauftragt (mit Auftragsnummer und Liefertermin), Abgelehnt; Nachfassen vermerken "
                                      "und Wiedervorlage")
        menue = QMenu(self.vorgang_knopf)
        for v in VORGAENGE:
            menue.addAction(v, lambda v=v: self.vorgang_setzen(v))
        menue.addSeparator()            # Plan A9
        self.nachfassen_aktionen = (menue.addAction("Nachfassen vermerken …", lambda: self.nachfassen()),
                                    menue.addAction("Wiedervorlage …", lambda: self.wiedervorlage_setzen()))
        menue.aboutToShow.connect(lambda: [a.setVisible(funktionen.an("funktion_nachfassen"))
                                           for a in self.nachfassen_aktionen])
        # Zusammenarbeit (Patrick 28.10.2026): eigenes Angebot an einen Kollegen abgeben
        self.uebergeben_aktion = menue.addAction("An Kollegen übergeben …", lambda: self.uebergeben())
        self.notiz_aktion = menue.addAction("Notiz an Kollegen …", lambda: self.notiz())
        trenner = menue.addSeparator()  # Plan Palettenbegleitschein (ausgeblendet, wenn Versand aus)
        ps = menue.addAction("Palettenbegleitschein …", lambda: self._gewaehlt() and self.f.palettenschein(self._gewaehlt()))
        self.palettenschein_aktionen = (trenner, ps)
        menue.aboutToShow.connect(lambda: [a.setVisible(self.f.versand_an()) for a in self.palettenschein_aktionen])
        menue.aboutToShow.connect(lambda: [a.setVisible(teilen.aktiv(self.db))
                                           for a in (self.uebergeben_aktion, self.notiz_aktion)])
        self.vorgang_knopf.setMenu(menue)
        for taste in (Qt.Key_Return, Qt.Key_Enter):         # Eingabe öffnet das markierte Angebot
            k = QShortcut(QKeySequence(taste), self.ansicht, self.oeffnen_gewaehlt)
            k.setContext(Qt.WidgetShortcut)
        leiste = QHBoxLayout()
        for text, ziel in (("Neues Angebot", self.neu), ("Öffnen", self.oeffnen_gewaehlt), ("Kopieren", self.kopieren),
                           ("Löschen", self.loeschen), ("Ordner öffnen", self.ordner_oeffnen)):
            b = QPushButton(text)
            if text == "Neues Angebot":
                b.setObjectName("primaer")
            if text == "Neues Angebot":
                b.setToolTip("Neues Angebot anlegen. Aus STEP-Dateien: Dateien oder einen Ordner auf die Liste "
                             "ziehen oder Datei → Neues Angebot aus STEP …")
            if text == "Löschen":
                b.setToolTip("Markiertes Angebot mit allen Positionen löschen. Mit Löschschutz (Einstellungen → "
                             "Angebot) lassen sich einmal optimierte Angebote nur mit Admin-Rechten löschen.")
            if text == "Ordner öffnen":
                b.setToolTip("Ordner des markierten Angebots in der Ablage öffnen (PDFs, CSV, Materialanfrage, "
                             "STEP); ohne Markierung die ganze Ablage")
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            leiste.addWidget(b)
        leiste.addWidget(self.vorgang_knopf)
        leiste.addWidget(self.abgleich_knopf)
        leiste.addSpacing(20)
        leiste.addWidget(self.wer_filter)
        # schmale Fenster (1024 px): die Auswahlen dürfen schmaler werden als ihr längster Eintrag, damit der
        # Zeitraum die Mindestbreite des Hauptfensters nicht erhöht
        self.vorgang_filter.setMinimumWidth(120)
        self.zeitraum_filter.setMinimumWidth(70)
        leiste.addWidget(self.vorgang_filter)
        leiste.addWidget(self.zeitraum_filter)
        leiste.addWidget(self.suche, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(leiste)
        lay.addWidget(self.ansicht, 1)
        lay.addWidget(self.zeitraum_hinweis)
        self.setAcceptDrops(True)
        self.neu_laden()

    def suchen(self, text):
        """Suchtext setzen und die Liste sofort filtern (ohne Tipp-Pause), z. B. Angebote eines Kunden zeigen."""
        self.suche.setText(text)
        self.neu_laden()

    def neu_laden(self, *_):
        self._such_timer.stop()
        tage = self.db.einstellung("gueltigkeit")
        passt = VORGANG_FILTER.get(self.vorgang_filter.currentText(), VORGANG_FILTER["Alle Angebote"])
        such = self.suche.text().strip()
        seit = self._zeitraum_seit()
        offen = sorted(i for i in (getattr(self.f, "offen", None) or ()) if isinstance(i, int))
        alle = self.db.angebote(such, seit=seit, dazu=offen)
        wer = self._wer_fuellen(alle)
        from . import cockpit
        faellig = {id(w.z): w for w in cockpit.wiedervorlagen(alle, tage,
                                                             nachfassen=self.db.einstellung("nachfassen_tage"))}
        for z in alle:
            z["_wv"] = faellig.get(id(z))
        if seit and not such:
            heute = datetime.date.today()
            alle = [z for z in alle if z.get("_im_zeitraum") or z["_wv"] or z["id"] in offen
                    or offener_auftrag(z, heute)]
        self._zeitraum_hinweis_setzen(self.db.angebote_anzahl() - len(alle) if seit and not such else 0)
        zeilen = []
        geteilt = teilen.aktiv(self.db)
        for z in alle:
            z["_offen"] = teilen.offen_bei(self.db, z.get("nummer")) if geteilt and z.get("fremd") else None
            z["_gueltig"], z["_abgelaufen"] = gueltig_bis(z, tage), abgelaufen(z, tage)
            if not passt(vorgang(z), z["_abgelaufen"], z):
                continue
            if wer == MEINE and z.get("fremd") or wer not in (MEINE, ALLE) and bearbeiter(z) != wer:
                continue
            zeilen.append(z)
        self.modell.setzen(zeilen)
        self._leere_spalten()

    def _zeitraum_seit(self):
        """ISO-Datum, ab dem die Liste Angebote zeigt (Auswahl Zeitraum), None = alle. Folgt der Einstellung
        'angebote_zeitraum', sobald sie sich ändert."""
        vorgabe = self.db.einstellung("angebote_zeitraum")
        if vorgabe != self._zeitraum_vorgabe:
            self._zeitraum_vorgabe = vorgabe
            if vorgabe in ZEITRAUM:
                self.zeitraum_filter.blockSignals(True)
                self.zeitraum_filter.setCurrentText(vorgabe)
                self.zeitraum_filter.blockSignals(False)
        tage = ZEITRAUM.get(self.zeitraum_filter.currentText())
        return (datetime.date.today() - datetime.timedelta(days=tage)).isoformat() if tage else None

    def _zeitraum_hinweis_setzen(self, anzahl):
        if anzahl > 0:
            self.zeitraum_hinweis.setText(
                f"{anzahl:,} ältere Angebote ausgeblendet (Zeitraum {self.zeitraum_filter.currentText()}).".replace(",", ".")
                + " <a href='alle'>Alle zeigen</a> · Die Suche findet alle.")
        self.zeitraum_hinweis.setVisible(anzahl > 0)

    AUSBLENDBAR = ("Bearbeiter", "Nachkalkuliert", "Auftragsnr.", "Liefertermin")    # leer: ausgeblendet (L6, W8)

    def _leere_spalten(self):
        for c, (titel, quelle, _, _) in enumerate(self.SPALTEN):
            if titel in self.AUSBLENDBAR:
                leer = all(not (quelle(z) if callable(quelle) else z.get(quelle)) for z in self.modell.zeilen)
                self.ansicht.setColumnHidden(c, leer)

    def _wer_fuellen(self, alle):
        """Auswahl Meine/Alle/Kürzel nur, wenn geteilt wird oder Angebote anderer da sind. Ergebnis: Auswahl."""
        kuerzel = sorted({bearbeiter(z) for z in alle if z.get("fremd")} - {None, ""})
        eintraege = [MEINE, ALLE] + kuerzel if (kuerzel or teilen.aktiv(self.db)) else []
        sichtbar_jetzt = bool(eintraege)
        self.wer_filter.setVisible(sichtbar_jetzt)
        self.abgleich_knopf.setVisible(teilen.aktiv(self.db))
        if [self.wer_filter.itemText(i) for i in range(self.wer_filter.count())] != eintraege:
            alt = self.wer_filter.currentText()
            self.wer_filter.blockSignals(True)
            self.wer_filter.clear()
            self.wer_filter.addItems(eintraege)
            self.wer_filter.setCurrentText(alt if alt in eintraege else ALLE if eintraege else "")
            self.wer_filter.blockSignals(False)
        return self.wer_filter.currentText() if sichtbar_jetzt else ALLE

    def uebergeben(self, angebot_id=None, an=None, notiz=""):
        """Vorgang → An Kollegen übergeben: das gewählte eigene Angebot gehört danach dem Kollegen."""
        from . import teilen_fenster
        i = angebot_id or self._gewaehlt()
        if i is None or self._fremd(i, "Übergeben"):
            return False
        return teilen_fenster.uebergeben(self.f, i, an, notiz)

    def notiz(self, angebot_id=None, an=None, text="", faellig=None):
        """Vorgang → Notiz an Kollegen: zum gewählten Angebot (auch eines Kollegen), wahlweise mit Wiedervorlage."""
        from . import teilen_fenster
        i = angebot_id or self._gewaehlt()
        if i is None:
            return False
        return teilen_fenster.notiz_senden(self.f, i, an, text, faellig)

    def _fremd(self, i, was):
        """Angebot eines Kollegen: Hinweis statt Ändern. Ergebnis: True = fremd (nichts tun)."""
        a = self.db.angebot(i) or {}
        if not a.get("fremd"):
            return False
        self.f.meldung(f"Angebot {a['nummer']} gehört {a['fremd']}: {was} kann nur {a['fremd']}. "
                       "Zum Weiterarbeiten „Kopieren“ (eigene Kopie mit eigener Nummer).", fehler=True)
        return True

    def _termin_frueh(self, angebot_id):
        """Frühester Liefertermin nach Auslastung (Vorschlag V2) für das Fenster „Beauftragt“, None ohne
        Schnittplan oder ohne Funktion Maschinenauslastung."""
        from . import funktionen, terminplan
        if not funktionen.an("funktion_auslastung", self.db):
            return None
        try:
            return terminplan.fruehester(self.db, angebot_id)
        except Exception:           # Vorschlag darf das Beauftragen nie verhindern
            return None

    def vorgang_setzen(self, v, angebot_id=None, auftrag=None, absage=None):
        """Vorgang des gewählten Angebots setzen (Beauftragt, Abgelehnt …). Beauftragt: Fenster für Auftragsnummer
        und Liefertermin (W8); auftrag = (Auftragsnummer, ISO-Termin) setzt beides ohne Fenster. Abgelehnt: Fenster
        für den Absagegrund (Plan 29.10.2026 1b); absage = (Grund, Bemerkung, Preis Wettbewerb) ohne Fenster."""
        i = angebot_id or self._gewaehlt()
        if not i or self._fremd(i, "den Vorgang setzen"):
            return False
        a = self.db.angebot(i) or {}
        if v == "Verschickt" and (a.get("vorgang") or "Entwurf") == "Entwurf" and not self.f.stumm:
            # Angebots-Check auch vor „Verschickt“ von Hand (Plan A2): das Angebot öffnet sich dafür
            seite = self.f.angebot_oeffnen(i)
            if seite is None or not seite.vor_verschickt():
                return False
        if v == "Beauftragt" and auftrag is None and not self.f.stumm and not self.db.nur_lesen:
            from . import auftrag as auftrag_fenster
            auftrag = auftrag_fenster.abfragen(self, a, self.db.einstellung("versand_bundesland"),
                                               frueh=self._termin_frueh(i))
            if auftrag is None:
                return False
        if v == "Abgelehnt" and absage is None and not self.f.stumm and not self.db.nur_lesen:
            from . import absage_dialog
            absage = absage_dialog.abfragen(self, a)
            if absage is None:
                return False
        self.db.vorgang_setzen(i, v)
        text = ""
        if v == "Abgelehnt" and absage is not None:
            self.db.absage_merken(i, *absage)
            text = f", Grund: {absage[0]}"
        if v == "Beauftragt" and auftrag is not None:
            self.db.auftrag_setzen(i, *auftrag)
            text = "".join((f", Auftrag {auftrag[0]}" if auftrag[0] else "",
                            f", Liefertermin {_datum(auftrag[1])}" if auftrag[1] else ""))
        self.neu_laden()
        if v == "Beauftragt" and self.f.versand_an():
            text += " – Palettenschein und Versand im Reiter Versand"
            self.f.versand.neu_laden()
        self.f.meldung(f"Angebot {self.db.angebot(i)['nummer']}: Vorgang {v}{text}.")
        return True

    def nachfassen(self, angebot_id=None, dialog=None):
        """Nachfassen beim Kunden vermerken (Plan A9, nachfassen_dialog)."""
        from .nachfassen_dialog import nachfassen_dialog
        i = angebot_id or self._gewaehlt()
        return nachfassen_dialog(self.f, i, self, dialog) if i else None

    def wiedervorlage_setzen(self, angebot_id=None, dialog=None):
        from .nachfassen_dialog import wiedervorlage_dialog
        i = angebot_id or self._gewaehlt()
        return wiedervorlage_dialog(self.f, i, self, dialog) if i else None

    def _id(self, index):
        return self.modell.zeilen[self.filter.mapToSource(index).row()]["id"]

    def _gewaehlt(self):
        i = self.ansicht.currentIndex()
        if not i.isValid():
            self.f.meldung("Bitte zuerst ein Angebot wählen.", fehler=True)
            return None
        return self._id(i)

    def neu(self):
        i = self.db.angebot_neu()
        self.neu_laden()
        self.oeffnen.emit(i)

    def neu_aus_step(self, dateien=None, kundennr=None, **weitere):
        """Neues Angebot aus STEP-Dateien (Plan Arbeitsabläufe W11, step_neu.py); weitere: kopf, formulare,
        vorschlag, hinweis, werkstoff_text, neuer_kunde (Anfrage-Ordner, E-Mail)."""
        from . import step_neu
        return step_neu.neues_angebot(self.f, dateien, kundennr, **weitere)

    # STEP-Dateien oder Ordner auf die Liste ziehen: neues Angebot (W11)
    def dragEnterEvent(self, ereignis):
        if step_neu_pfade(ereignis):
            ereignis.acceptProposedAction()

    def dropEvent(self, ereignis):
        pfade = step_neu_pfade(ereignis)
        if pfade:
            step_drop(self.f, ereignis, self, lambda: self.neu_aus_step(pfade))

    def oeffnen_gewaehlt(self):
        i = self._gewaehlt()
        if i:
            self.oeffnen.emit(i)

    def ordner_oeffnen(self):
        """Ordner des markierten Angebots öffnen, ohne Markierung die Ablage. Ergebnis: Ordner oder None."""
        i = self._gewaehlt()
        return self.f.angebot_ordner_oeffnen(self.db.angebot(i) if i else None)

    def kopieren(self, kundennr=None):
        """Angebot kopieren; im Dialog lässt sich ein anderer Kunde wählen (kundennr setzt ihn ohne Dialog)."""
        i = self._gewaehlt()
        if not i:
            return None
        if kundennr is None and not self.f.stumm:
            kundennr = self._kunde_fuer_kopie(self.db.angebot(i))
            if kundennr is False:
                return None
            if kundennr is FASSUNG:
                return self.neue_fassung(i)
        neu = self.db.angebot_kopieren(i, kundennr)
        self.neu_laden()
        self.oeffnen.emit(neu)
        return neu

    def _kunde_fuer_kopie(self, a):
        """Dialog: Kunde der Kopie. Ergebnis: Kundennummer ('' = ohne Kunde) oder False (abgebrochen)."""
        d = QDialog(self)
        d.setWindowTitle(f"Angebot {a['nummer']} kopieren")
        form = QFormLayout(d)
        kunde = QComboBox()
        kunde.setEditable(True)
        kunde.setInsertPolicy(QComboBox.NoInsert)
        for kd in self.db.zeilen("kunden"):
            if kd.get("kundennr"):
                kunde.addItem(f"{kd['kundennr']} – {kd.get('name') or ''}", kd["kundennr"])
        i = kunde.findData(a.get("kundennr"))
        kunde.setCurrentIndex(i)
        if i < 0:
            kunde.setEditText(a.get("kundennr") or "")
        text = QLabel(("Angebot von " + a["fremd"] + ": " if a.get("fremd") else "") +
                      "Die Kopie bekommt eine neue, eigene Nummer und das heutige Datum. Für einen anderen Kunden "
                      "kommen Name und Zahlungsbedingungen aus dem Kundenstamm.")
        text.setWordWrap(True)
        d.setMinimumWidth(460)
        form.addRow(text)
        form.addRow("Kunde", kunde)
        fassung = None
        if not a.get("fremd"):          # W10: neue Fassung statt Kopie (nur eigene Angebote)
            fassung = QCheckBox(f"Neue Fassung {self.db.fassung_nummer(a['id'])} statt Kopie (gleicher Kunde, "
                                f"aktuelle Preise; {a['nummer']} wird „ersetzt“)")
            fassung.toggled.connect(kunde.setDisabled)
            form.addRow(fassung)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(d.accept)
        knoepfe.rejected.connect(d.reject)
        form.addRow(knoepfe)
        if d.exec() != QDialog.Accepted:
            return False
        if fassung is not None and fassung.isChecked():
            return FASSUNG
        return _kundennr(kunde.currentText())

    def neue_fassung(self, angebot_id=None):
        """Neue Fassung des gewählten Angebots (Plan Arbeitsabläufe W10): gleiche Nummer mit Zusatz -2, -3 …,
        gleicher Kunde, aktuelle Preise; die bisherige Fassung steht danach auf „Ersetzt“. Ergebnis: neue ID."""
        i = angebot_id or self._gewaehlt()
        if not i or self._fremd(i, "eine neue Fassung anlegen"):
            return None
        if self.db.nur_lesen:
            self.f.meldung("Lesemodus: es lassen sich keine Angebote anlegen.", fehler=True)
            return None
        alt = self.db.angebot(i)["nummer"]
        neu = self.db.angebot_fassung(i)
        self.f.angebot_schliessen(i)            # offene alte Fassung: Reiter zu, sie ist jetzt ersetzt
        self.neu_laden()
        self.oeffnen.emit(neu)
        self.f.meldung(f"Neue Fassung {self.db.angebot(neu)['nummer']} angelegt; {alt} ist ersetzt.")
        return neu

    def loeschen(self):
        i = self._gewaehlt()
        if not i or self._fremd(i, "löschen"):
            return
        a = self.db.angebot(i)
        grund = self.db.loeschschutz(i)         # Löschschutz (Patrick 28.10.2026): einmal optimiert = bleibt
        admin = bool(getattr(self.f, "bereich", None) and self.f.bereich.admin)
        if grund and not admin:
            QMessageBox.information(self, "Angebot löschen", grund)
            self.f.meldung(f"Angebot {a['nummer']} ist gegen Löschen geschützt.", fehler=True)
            return
        frage = f"Angebot {a['nummer']} mit allen Positionen löschen?\n\nDie tägliche Datensicherung enthält es weiterhin."
        if grund:
            frage = (f"{grund}\n\nMit Admin-Rechten trotzdem löschen?\n\nDie tägliche Datensicherung enthält es "
                     "weiterhin.")
        if QMessageBox.question(self, "Angebot löschen", frage) == QMessageBox.Yes:
            self.f.angebot_schliessen(i)
            self.db.angebot_loeschen(i, trotz_schutz=bool(grund))
            self.neu_laden()


def _datum(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y") if iso else ""
    except ValueError:
        return iso


def _zeit(iso):
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M") if iso else ""
    except ValueError:
        return iso


# ------------------------------------------------------------------ Positionen
BERECHNET = [("Profilform", "profilform", None), ("Querschnitt [mm²]", "querschnitt", 1), ("Wandstärke [mm]", "wand", 2),
             ("Metergewicht [kg/m]", "kg_m", 3), ("Gewicht je Teil [kg]", "gewicht", 3),
             ("Länge gesamt [mm]", "laenge_gesamt", 0), ("Stangenlänge wirksam [mm]", "stange", 0),
             ("Endbeschnitt wirksam [mm]", "end", 0), ("Greiferrest wirksam [mm]", "greif", 0),
             ("Nutzlänge Stange [mm]", "nutz", 0), ("Preis hinterlegt", "preis_hinterlegt", None),
             ("Vorschub groß [mm/min]", "vorschub", 0), ("Schneidgas", "gas", None), ("Gewicht Position [kg]", "gewicht_position", 2),
             ("Eingeplant [Stk]", "eingeplant", 0), ("Nicht eingeplant [Stk]", "nicht_eingeplant", 0)]
# Zusatzarbeiten gleich hinter der Artikelnummer, mit den Gewinden davor (Plan Angebotsablauf V6: auch bei 1366 px
# sichtbar, was an jedem Teil gemacht wird); Satz und Stück je Satz gleich hinter Pos. (Sätze abheben, 27.10.2026)
SICHTBAR = ["pos", "satz", "je_satz", "art", "artikel", "zusatz", "bezeichnung", "profil_id", "werkstoff_id", "oberflaeche",
            "laenge", "stueck", "muster",
            "schneidweg", "einstiche", "zeit_manuell", "prog_zeit", "stange", "preis_m", "material_herkunft",
            "gewinde", "zukauf",
            "naht_vorgabe", "anbauteile", "gewicht_teil", "je_umfang"]
# Optionale Spalten: erscheinen, sobald eine Position einen Wert hat, oder über 'Weitere Spalten'
OPTIONALE_SPALTEN = ("art", "oberflaeche", "stange", "satz", "je_satz", "material_herkunft", "gewinde", "zusatz",
                     "zukauf", "naht_vorgabe", "anbauteile", "gewicht_teil", "je_umfang", "muster")
EIGENE = ("zusatz", "zukauf", "naht", "bohrbild", "anbau")        # Spalten mit eigenem Dialog (Doppelklick)
# Profilwechsel einer STEP-Position in der Tabelle: diese Felder rechnet der Schneidweg-Rechner neu (profil_gewechselt)
PROFILWECHSEL_FELDER = ("schneidweg", "einstiche", "a_schnitt", "b_schnitt", "a_gerade", "b_gerade", "innen",
                        "konturen", "kontur_grenzen", "klein_n", "klein_mm", "mittel_n", "mittel_mm", "gross_n",
                        "gross_mm")
RECHNER_SPALTEN = {"schneidweg", "einstiche"} | set(STEP_FELDER)     # Doppelklick: Schneidweg-Rechner
# Ändert sich eines davon, wird das Vorschaubild der Artikelnummer neu gezeichnet
VORSCHAU_FELDER = ("technik", "laenge", "profil_id", "art", "konturen", "a_ende", "b_ende", "a_schnitt", "b_schnitt")
BOHRBILD_SPALTEN = ("gewinde", "bohrungen", "gewinde_vorschlag")     # Doppelklick: Bohrungen prüfen
# Doppelklick auf den Status: (Stichwort im Status, Ziel, Tooltip); erstes passendes gilt. Ziel = Methode der
# Angebotsseite (bekommt die Zeile) oder "feld:" + Spalte (Zelle zum Eintragen öffnen, Spalte notfalls einblenden).
STATUS_ZIELE = (
    # Schweißbaugruppe (Status der Baugruppe und ihrer Teile): Editor; vor 'Naht', 'Zusatzarbeit' und 'Stückzahl'
    ("Baugruppe", "baugruppe_bearbeiten", "Schweißbaugruppe bearbeiten"),
    ("Nahtgruppe", "baugruppe_bearbeiten", "Schweißbaugruppe bearbeiten"),
    ("Stundensatz fehlt", "baugruppe_bearbeiten", "Schweißbaugruppe bearbeiten"),
    ("doppelt?", "baugruppe_bearbeiten", "Schweißbaugruppe bearbeiten"),
    ("Richtwerten", "baugruppe_bearbeiten", "Schweißbaugruppe bearbeiten"),
    ("Vorrichtung", "baugruppe_bearbeiten", "Schweißbaugruppe bearbeiten"),
    ("keine Nahtgruppen", "baugruppe_bearbeiten", "Schweißbaugruppe bearbeiten"),
    ("Bohrungen prüfen", "bohrungen_pruefen", "Bohrungen prüfen"),
    ("Anbauteile prüfen", "anbauteile_pruefen", "Anbauteile prüfen"),
    ("Zukaufartikel fehlt", "zukaufteile", "Zukaufteile wählen"),
    ("EK fehlt", "zukauf_ek", "Einkaufspreis eintragen"),
    ("Zusatzarbeit", "zusatzarbeiten", "Zusatzarbeiten wählen"),
    ("Schweißnaht", "schweissnaht", "Schweißnaht wählen"),
    ("Naht", "schweissnaht", "Schweißnaht wählen"),
    ("Schneidweg fehlt", "schneidweg_berechnen", "Schneidweg-Rechner öffnen"),
    ("Kontur", "schneidweg_berechnen", "Schneidweg-Rechner öffnen"),
    ("Profil unbekannt", "feld:profil_id", "Profil wählen"),
    ("Querschnitt fehlt", "feld:profil_id", "Profil wählen"),
    ("Hüllkreis", "feld:profil_id", "Profil wählen"),
    ("Metergewicht", "feld:profil_id", "Profil wählen"),
    ("Werkstoff unbekannt", "feld:werkstoff_id", "Werkstoff wählen"),
    ("Oberfläche", "feld:oberflaeche", "Oberfläche wählen"),
    ("Teilelänge fehlt", "feld:laenge", "Teilelänge eintragen"),
    ("Teil länger als Nutzlänge", "feld:laenge", "Teilelänge prüfen"),
    ("Stückzahl", "feld:stueck", "Stückzahl eintragen"),
    ("Stange länger", "feld:stange", "Stangenlänge eintragen"),
    ("kein gültiger Materialpreis", "feld:preis_m", "Meterpreis eintragen"),
    ("keine Schneiddaten", "feld:zeit_manuell", "Schneidzeit von Hand eintragen"),
    ("Schneidzeit manuell", "feld:zeit_manuell", "Schneidzeit ändern"),
    ("beigestellt", "feld:material_herkunft", "Material ändern"),
    ("nicht vollständig eingeplant", "optimieren", "Optimieren"),
)


def status_ziel(status):
    """(Ziel, Tooltip) für den Doppelklick auf einen Status, sonst None."""
    return next(((z, t) for wort, z, t in STATUS_ZIELE if wort in str(status or "")), None)


SPALTEN_EINSTELLUNG = "ansicht_positionsspalten"     # gemerkte Wahl {Spalte: True/False}; fehlt = automatisch
ABWEICHUNG_MM = 0.25    # STEP-Teilwerte sind auf 0,1 mm gerundet: kleinere Unterschiede sind keine Änderung


def schneidweg_abweichung(p):
    """Eingetragener Schneidweg − (Anfangs- + Endschnitt + Innenkonturen aus STEP) [mm]; None ohne STEP-Werte
    oder wenn beide gleich sind (der Schneidweg wurde nicht von Hand geändert)."""
    teile = [p.get(n) for n in ("a_schnitt", "b_schnitt", "innen")]
    if any(not isinstance(t, (int, float)) for t in teile) or not isinstance(p.get("schneidweg"), (int, float)):
        return None
    d = p["schneidweg"] - sum(teile)
    return d if abs(d) > ABWEICHUNG_MM else None


# Vorschaubilder aus dem 3D-Netz, solange das Programm läuft (Performance-Plan P3, Frage 3a): gleiches Netz = gleiches
# Bild, auch nach Schließen und erneutem Öffnen des Angebots. Ein großes Netz (Rohr mit 1.000 Bohrungen) braucht sonst
# bei jedem Öffnen Sekunden.
VORSCHAU_MERKEN = 2000
_vorschau_merker = {}


def netz_vorschau(daten):
    """Vorschaubild (64 × 18) aus gepackten Netz-Bytes (Datenbank) oder None; gemerkt nach dem Inhalt."""
    if not daten:
        return None
    import hashlib
    schl = hashlib.blake2b(daten, digest_size=16).digest()
    if schl in _vorschau_merker:
        _vorschau_merker[schl] = _vorschau_merker.pop(schl)       # zuletzt benutzt nach hinten
        return _vorschau_merker[schl]
    from .ansicht3d import entpacken, vorschaubild
    bild = vorschaubild(entpacken(daten), 64, 18)
    _vorschau_merker[schl] = bild
    while len(_vorschau_merker) > VORSCHAU_MERKEN:
        _vorschau_merker.pop(next(iter(_vorschau_merker)))
    return bild

class PositionenModell(QAbstractTableModel):
    geaendert = Signal()

    def __init__(self, seite):
        super().__init__()
        self.s = seite
        felder = {f.name: f for f in POSITIONEN.felder}
        art = lambda f: "bohrbild" if f.name in BOHRBILD_SPALTEN else f.art if f.art in EIGENE else "feld"
        # Status gleich nach der Positionsnummer: Fehler und Warnungen auch bei schmalem Fenster sichtbar
        self.spalten = ([(art(felder[n]), felder[n]) for n in SICHTBAR[:1]] + [("status", None)]
                        + [(art(felder[n]), felder[n]) for n in SICHTBAR[1:]]
                        + [("berechnet", b) for b in BERECHNET]
                        + [(art(f), f) for f in POSITIONEN.felder if f.name in STEP_FELDER]
                        + [("abweichung", None)])
        self.daten, self.werte, self.status = [], [], []
        self.mit_netz, self.bilder = set(), {}
        self.kopf_text = {}         # Zeilenkopf gruppierter Baugruppen (D3): ▾/▸ an der Baugruppe, └ an den Teilen
        self.satz, self.satz_zu = {}, set()     # Sätze (satzgruppen.info) und zugeklappte Sätze, von _gruppieren

    def vorschau(self, r):
        """Kleines Bild der Position: 3D aus dem STEP-Import, sonst selbst angelegt die Draufsicht des Rohrs
        (Schneidweg-Rechner) bzw. der Zuschnitt (Blech-Editor). Neu gezeichnet, sobald sich Technik, Länge, Profil
        oder Enden ändern."""
        p = self.daten[r]
        pid = p.get("id")
        schluessel = (pid in self.mit_netz,) + tuple(p.get(n) for n in VORSCHAU_FELDER)
        alt = self.bilder.get(pid)
        if alt is None or alt[0] != schluessel:
            try:
                if pid in self.mit_netz:
                    neu = netz_vorschau(self.s.db.netz(pid))
                elif blech.lesen(p.get("technik")):
                    neu = vorschau.bild(p, None)
                elif not kein_laserteil(p):
                    neu = vorschau.rohr(p, self.k.profile.get(p.get("profil_id")))
                else:
                    neu = None
            except Exception:       # beschädigte Daten: ohne Bild weiter
                neu = None
            self.bilder[pid] = alt = (schluessel, neu)
        return alt[1]

    def rechnen(self):
        s = self.s
        self.beginResetModel()
        self.daten = s.positionen
        self.mit_netz = s.db.netz_ids(s.id)
        ids = {p.get("id") for p in self.daten}
        self.bilder = {pid: b for pid, b in self.bilder.items() if pid in ids}
        erg = s.ergebnis
        eingeplant = rechnen.eingeplant_je_position(erg) if erg and erg["stangen"] else None
        self.werte, self.status, self.zeiten, self.meterpreise, self.prog_zeiten = [], [], [], [], []
        for i, p in enumerate(self.daten):
            w = rechnen.position_werte(p, s.kopf, s.k, s.tabellen)
            self.meterpreise.append(rechnen.meterpreis(p, s.kopf, self.daten, s.k, s.tabellen))  # (berechnet, wirksam, fehlt)
            self.zeiten.append(rechnen.schneidzeit(p, s.kopf, w.get("wand_schneiden"), s.tabellen, s.k)[2])   # berechnet [s]
            # Programmierzeit ohne Eintrag von Hand: Grundzeit + Zeit je Innenkontur [min] (Zukaufteile: keine)
            self.prog_zeiten.append(None if kein_laserteil(p) else
                                    rechnen.programmier_zeit(dict(p, prog_zeit=None), s.einst)[0])
            ein = eingeplant.get(rechnen.schluessel(p, i), 0) if eingeplant is not None else None
            w["eingeplant"] = ein if p.get("profil_id") and not kein_laserteil(p) else None
            if kein_laserteil(p):
                ein = None              # Zukaufteile werden nicht eingeplant
            w["nicht_eingeplant"] = (rechnen.rohrstuecke(p) - ein) if ein is not None and p.get("stueck") is not None \
                else None
            self.werte.append(w)
            self.status.append(rechnen.status(p, w, s.kopf, s.k, ein, self.daten))
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.daten)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.spalten)

    @property
    def k(self):
        return self.s.k

    def headerData(self, abschnitt, richtung, rolle=Qt.ItemDataRole.DisplayRole):
        if rolle != Qt.ItemDataRole.DisplayRole:
            return None
        if richtung == Qt.Vertical:
            return self.kopf_text.get(abschnitt) or str(abschnitt + 1)
        art, x = self.spalten[abschnitt]
        if art == "zusatz":
            return "Gewinde · Zusatzarbeiten"
        return x.titel if art in ("feld",) + EIGENE else {"status": "Status",
                                                          "abweichung": "Abweichung Schneidweg zu STEP [mm]"}.get(art) or x[0]

    def _zusatz_auto(self, p):
        """Automatische Zusatzarbeiten der Position aus den Arbeitsgang-Regeln, z. B. „Strahlen (automatisch)“."""
        tab = getattr(self.s, "tabellen", None) or {}
        if not tab.get("arbeitsgang_regeln") or getattr(self.s, "k", None) is None:
            return ""
        from . import zusatz_regeln
        vorhanden = {e["name"] for e in rechnen.zusatz_liste(p)}
        return "; ".join(f"{a['name']} (automatisch)" for a in
                         zusatz_regeln.automatische(p, getattr(self.s, "kopf", None), self.s.k, tab, vorhanden))

    def name(self, c):
        """Name einer Spalte (Feldname, 'status', 'abweichung' oder 'berechnet:' + Schlüssel)."""
        art, x = self.spalten[c]
        return x.name if art in ("feld",) + EIGENE else ("berechnet:" + x[1] if art == "berechnet" else art)

    def roh(self, r, c):
        art, x = self.spalten[c]
        if art in ("feld", "bohrbild"):
            return self.daten[r].get(x.name)
        if art == "status":
            return self.status[r]
        if art == "zusatz":         # V6: Gewinde und Zusatzarbeiten zusammen, z. B. „4xM6 · Senken; feuerverzinkt“
            p = self.daten[r]
            return " · ".join(t for t in ((p.get("gewinde") or "").strip(), rechnen.zusatz_text(p),
                                          self._zusatz_auto(p)) if t)
        if art == "zukauf":
            return zukauf.zukauf_text(self.daten[r])
        if art == "naht":
            return naht.text(self.daten[r], self.k.profile.get(self.daten[r].get("profil_id")))
        if art == "anbau":
            return anbau.kurz(anbau.lesen(self.daten[r].get("anbauteile")))
        if art == "abweichung":
            return schneidweg_abweichung(self.daten[r])
        w = self.werte[r].get(x[1])
        return {True: "ja", False: "nein"}.get(w, w) if isinstance(w, bool) else w

    # Während die Tabelle ihre Spalten und Zeilen einpasst (spaltenbreite.AutoGroesse), fragt Qt jede Zelle mehrfach
    # und mit vielen Rollen ab; das Modell ändert sich dabei nicht. Dann einmal je Zelle und Rolle rechnen
    # (Performance-Plan P6, Frage 6a: Breiten exakt wie bisher).
    _merk = None

    def merken_an(self, an):
        self._merk = {} if an else None

    def data(self, index, rolle=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if self._merk is None:
            return self._data(index, rolle)
        schl = (index.row(), index.column(), int(rolle))
        if schl not in self._merk:
            self._merk[schl] = self._data(index, rolle)
        return self._merk[schl]

    def _data(self, index, rolle):
        s = self.satz.get(index.row())
        if s is None:
            return self._data_zelle(index, rolle)
        # Positionen eines Satzes (Patrick 27.10.2026): getönt, an der ersten fett Name und Anzahl Sätze
        art, x = self.spalten[index.column()]
        if art == "feld" and x.name == "satz":
            if rolle == Qt.ItemDataRole.DisplayRole:
                return satzgruppen.zelltext(s, s["name"] in self.satz_zu)
            if rolle == Qt.ItemDataRole.ForegroundRole:
                return QBrush(stil.farbe(satzgruppen.TEXTE[s["ton"]] if s["erste"] else "#5F6B7A"))
            if rolle == Qt.ItemDataRole.FontRole and s["erste"]:
                f = QFont()
                f.setBold(True)
                return f
            if rolle == Qt.ItemDataRole.ToolTipRole:
                return (f"Satz {s['name']}: {s['teile']} Position(en)"
                        + (f", {s['saetze']} {'Satz' if s['saetze'] == 1 else 'Sätze'}" if s["saetze"] else "")
                        + (".\nKlick auf ▾/▸ im Zeilenkopf: Positionen des Satzes zu- bzw. aufklappen."
                           if s["teile"] > 1 else "."))
        w = self._data_zelle(index, rolle)
        if rolle == Qt.ItemDataRole.BackgroundRole and isinstance(w, QBrush) and art != "status" \
                and w.color() in (FARBE_EINGABE, FARBE_BERECHNET):
            return QBrush(satzgruppen.mischen(w.color(), stil.farbe(satzgruppen.FLAECHEN[s["ton"]])))
        return w

    def _data_zelle(self, index, rolle):
        art, x = self.spalten[index.column()]
        w = self.roh(index.row(), index.column())
        if art == "feld" and x.name == "zeit_manuell":      # Schneidzeit: berechnet, von Hand überschreibbar
            berechnet = self.zeiten[index.row()]
            if rolle == Qt.ItemDataRole.DisplayRole and w is None:
                return _z(berechnet, 1) if berechnet is not None else ""
            if rolle == Qt.ItemDataRole.ToolTipRole:
                return (f"Berechnet: {_z(berechnet, 1)} s je Teil (ohne Einsparung gemeinsamer Schnitte). "
                        if berechnet is not None else "Keine Schneiddaten: Zeit von Hand eintragen. ") + \
                    ("Von Hand eingetragen; leeren = wieder berechnet." if w is not None
                     else "Doppelklick zum Anpassen.")
            if rolle == Qt.ItemDataRole.EditRole and w is None:
                return _z(berechnet, 1) if berechnet is not None else ""
            if rolle == Qt.ItemDataRole.ForegroundRole:
                return QBrush(stil.farbe("#000000" if w is not None else "#5F6B7A"))
            if rolle == Qt.ItemDataRole.FontRole and w is not None:
                f = QFont()
                f.setBold(True)
                return f
        if art == "feld" and x.name == "prog_zeit":         # Programmierzeit: berechnet, von Hand überschreibbar
            berechnet = self.prog_zeiten[index.row()] if index.row() < len(self.prog_zeiten) else None
            if rolle in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole) and w is None:
                return _z(berechnet, 1) if berechnet is not None else ""
            if rolle == Qt.ItemDataRole.ToolTipRole:
                n = rechnen.konturen_anzahl(self.daten[index.row()])
                return ((f"Berechnet: {_z(berechnet, 1)} min = Grundzeit je Position + Zeit je Innenkontur × {n} "
                         "Innenkontur(en) (Kalkulation des Angebots). " if berechnet is not None
                         else "Verschicktes Angebot: Betrag je Position festgeschrieben. ")
                        + ("Von Hand eingetragen; leeren = wieder berechnet." if w is not None
                           else "Doppelklick zum Anpassen."))
            if rolle == Qt.ItemDataRole.ForegroundRole:
                return QBrush(stil.farbe("#000000" if w is not None else "#5F6B7A"))
            if rolle == Qt.ItemDataRole.FontRole and w is not None:
                f = QFont()
                f.setBold(True)
                return f
        if art == "feld" and x.name == "preis_m":           # Meterpreis: berechnet, von Hand überschreibbar
            berechnet, wirksam, fehlt = self.meterpreise[index.row()]
            eigen = rechnen._n(w) > 0
            # Preis von Hand einer anderen Position derselben Stangengruppe gilt für alle Stangen der Gruppe
            fremd = not eigen and wirksam is not None and berechnet is not None and abs(wirksam - berechnet) > 0.005
            anzeige = wirksam if fremd else berechnet
            if rolle in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole) and not eigen:
                return _z(anzeige, 2) if anzeige is not None else ""
            if rolle == Qt.ItemDataRole.ToolTipRole:
                if kein_laserteil(self.daten[index.row()]):
                    return "Zukaufteil bzw. Schweißbaugruppe: kein Materialpreis je m."
                t = (f"Berechnet: {_z(berechnet, 2)} €/m (Lieferlänge, Preise bzw. Tonnenpreis, mit Aufpreis der "
                     "Oberfläche). " if berechnet is not None else "Kein berechneter Meterpreis: Preis von Hand "
                                                                    "eintragen. ")
                if fehlt and berechnet is not None:
                    t += f"Achtung: {fehlt}. "
                h = rechnen.preis_herkunft(self.daten[index.row()], self.s.kopf, self.s.k, self.s.tabellen)
                if h:
                    t += h + ". "
                if eigen:
                    return t + ("Von Hand eingetragen, gilt für alle Positionen mit gleichem Profil, Werkstoff, "
                                "Oberfläche und Stangenlänge; leeren = wieder berechnet.")
                if fremd:
                    return t + (f"Es gilt {_z(wirksam, 2)} €/m, von Hand bei einer anderen Position mit gleichem "
                                "Profil, Werkstoff, Oberfläche und Stangenlänge eingetragen.")
                return t + "Doppelklick zum Anpassen (günstiger oder teurer)."
            if rolle == Qt.ItemDataRole.ForegroundRole:
                return QBrush(stil.farbe("#000000" if eigen else "#5F6B7A"))
            if rolle == Qt.ItemDataRole.FontRole and (eigen or fremd):
                f = QFont()
                f.setBold(eigen)
                f.setItalic(fremd)
                return f
        if rolle == Qt.ItemDataRole.ToolTipRole and art == "status" and status_ziel(w):
            return f"{w}\nDoppelklick: {status_ziel(w)[1]}"
        if rolle == Qt.ItemDataRole.ToolTipRole and art == "feld" and (x.name in RECHNER_SPALTEN or x.name == "artikel"):
            p = self.daten[index.row()]
            text = wert_als_text(x, w)
            if x.name == "artikel" and p.get("id") in self.mit_netz:
                return (text + "\n" if text else "") + "Doppelklick aufs Bild: " + \
                    ("Blech-Editor" if blech.lesen(p.get("technik")) else "Schneidweg-Rechner") + \
                    " · Doppelklick auf die Nummer: 3D-Ansicht · Tippen oder F2: Artikelnummer ändern"
            if x.name == "artikel" and self.vorschau(index.row()):
                return (text + "\n" if text else "") + "Doppelklick aufs Bild: " + \
                    ("Blech-Editor" if blech.lesen(p.get("technik")) else "Schneidweg-Rechner") + \
                    " · Tippen oder F2: Artikelnummer ändern"
            if x.name in RECHNER_SPALTEN and not kein_laserteil(p) and p.get("profil_id") in self.k.profile:
                return (text + "\n" if text else "") + "Doppelklick: Schneidweg-Rechner · Tippen oder F2: Wert eintragen"
        if rolle in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if art == "bohrbild" and rolle == Qt.ItemDataRole.ToolTipRole:
                return (wert_als_text(x, w) + "\n" if w not in (None, "") else "") + \
                    "Doppelklick: Bohrungen prüfen (Gewinde, Senkungen, Flowdrill bestätigen oder ablehnen)"
            if art in ("feld", "bohrbild"):
                return wert_als_text(x, w)
            if art == "berechnet":
                return _z(w, x[2]) if x[2] is not None else ("" if w is None else str(w))
            if art == "abweichung":
                if rolle == Qt.ItemDataRole.ToolTipRole:
                    return ("Schneidweg von Hand geändert: eingetragen minus Summe aus Anfangsschnitt, Endschnitt und "
                            "Innenkonturen laut STEP." if w is not None else "Schneidweg wie aus STEP gemessen.")
                return _z(w, 1) if w is not None else ""
            if art == "zusatz" and rolle == Qt.ItemDataRole.ToolTipRole:
                return (w + "\n" if w else "") + "Doppelklick: Gewinde und Zusatzarbeiten wählen"
            if art == "zukauf" and rolle == Qt.ItemDataRole.ToolTipRole:
                return (w + "\n" if w else "") + "Doppelklick: Zukaufteile wählen"
            if art == "anbau" and rolle == Qt.ItemDataRole.ToolTipRole:
                return (w + "\n" if w else "") + "Doppelklick: Anbauteile prüfen (aufgeschweißte Teile, nur Gravur)"
            if art == "naht" and rolle == Qt.ItemDataRole.ToolTipRole:
                return (w + "\n" if w else "Keine Vorgabe: frei drehbar\n") + \
                    "Doppelklick: Schweißnaht am Querschnitt wählen (Blick von Ende A, 0° oben, 90° rechts)"
            return w
        if rolle == Qt.ItemDataRole.EditRole and art == "feld":
            return wert_als_text(x, w, bearbeiten=True)
        if rolle == Qt.ItemDataRole.DecorationRole and art == "status":
            return stil.status_symbol(w)
        if rolle == Qt.ItemDataRole.DecorationRole and art == "feld" and x.name == "artikel":
            return self.vorschau(index.row())
        if rolle == Qt.ItemDataRole.UserRole:
            return w
        if rolle == Qt.ItemDataRole.TextAlignmentRole and (art == "berechnet" and x[2] is not None or art == "abweichung"
                                              or art == "feld" and x.art in ("zahl", "ganz")):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.ItemDataRole.BackgroundRole:
            if art == "status":
                return QBrush(_farbe_status(w) or (stil.farbe("#FFF2CC") if str(w).startswith("HINWEIS") else FARBE_BERECHNET))
            if art == "abweichung" and w is not None:
                return QBrush(stil.farbe("#FFF2CC"))
            return QBrush(FARBE_EINGABE if art in ("feld",) + EIGENE else FARBE_BERECHNET)
        if rolle == Qt.ItemDataRole.ForegroundRole and art == "status":
            return QBrush(stil.farbe({"FEHLER": "#8C1D18", "WARNUNG": "#6B4A00"}.get(str(w).split(":")[0], "#1F2937")))
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.spalten[index.column()][0] == "feld" and not (self.s.kopf or {}).get("fremd"):
            f |= Qt.ItemIsEditable
        return f

    def setData(self, index, text, rolle=Qt.ItemDataRole.EditRole):
        if rolle != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        art, f = self.spalten[index.column()]
        if art != "feld":
            return False
        p = self.daten[index.row()]
        try:
            wert = wert_aus_text(f, text)
        except ValueError as e:
            self.s.f.meldung(str(e), fehler=True)
            return False
        if wert == p.get(f.name):
            return False
        if f.name == "zeit_manuell" and p.get(f.name) is None and wert is not None \
                and self.zeiten[index.row()] is not None and abs(wert - round(self.zeiten[index.row()], 1)) < 0.05:
            return False                # berechnete Zeit unverändert bestätigt: bleibt berechnet
        if f.name == "prog_zeit" and p.get(f.name) is None and wert is not None \
                and self.prog_zeiten[index.row()] is not None \
                and abs(wert - round(self.prog_zeiten[index.row()], 1)) < 0.05:
            return False                # berechnete Programmierzeit unverändert bestätigt: bleibt berechnet
        if f.name == "preis_m":
            if wert is not None and wert <= 0:
                wert = None             # 0 = kein Preis von Hand
            berechnet = self.meterpreise[index.row()][0]
            if wert is not None and rechnen._n(p.get(f.name)) <= 0 and berechnet is not None \
                    and abs(wert - round(berechnet, 2)) < 0.005:
                return False            # berechneter Meterpreis unverändert bestätigt: bleibt berechnet
            if wert == p.get(f.name):
                return False
        self.s.db.position_aendern(p["id"], f.name, wert)
        if f.name in ("konturen", "kontur_grenzen"):     # Konturliste geändert: beim Neuladen neu einteilen
            self.s.db.position_aendern(p["id"], "kontur_grenzen", None)
        neu = self.s.profil_gewechselt(dict(p, profil_id=wert)) if f.name == "profil_id" else None
        if f.name in ("stueck", "je_satz"):     # Satz (Patrick 31.10.2026): Stückzahl und Stück je Satz passen zusammen
            neu = self.s.satz_nachziehen(p, f.name, wert)
        self.s.f.meldung(f"{f.titel} gespeichert." + (f" {neu}" if neu else ""))
        self.geaendert.emit()
        if f.name == "profil_id" and wert and wert not in self.k.profile:     # Abmessung fehlt: anlegen anbieten
            QTimer.singleShot(0, self, lambda: self._abmessung_anbieten(p["id"], wert, index.column()))
        return True

    def _abmessung_anbieten(self, pos_id, text, spalte):
        """Profilspalte: getippte Abmessung fehlt in den Stammdaten -> Menü an der Zelle; angelegt mit anderer
        Profil-ID (z. B. 'QR 50x4' -> 'QR 50x50x4') bekommt die Position die neue ID."""
        ansicht = self.s.pos_ansicht
        zeile = next((i for i, x in enumerate(self.daten) if x.get("id") == pos_id), None)
        index = self.index(zeile, spalte) if zeile is not None else QModelIndex()
        vi = ansicht.model().mapFromSource(index) if hasattr(ansicht.model(), "mapFromSource") else index
        r = ansicht.visualRect(vi)

        def weiter(pid):
            if pid != text:
                self.s.db.position_aendern(pos_id, "profil_id", pid)
            self.s.neu_laden()
        m = self.s.abmessung_neu_anbieten(text, None, weiter)
        if m is not None and r.isValid():
            m.move(ansicht.viewport().mapToGlobal(r.bottomLeft()))


# ------------------------------------------------------------------ Stangenbild
class Stangenbild(QWidget):
    """Je Stangenmuster ein maßstäblicher Balken: Endbeschnitt grau, Teile farbig mit Pos. und Länge,
    dicke Linie = Schnitt, Rest hellgrau, Greiferrest rot. Schweißnaht als roter Strich auf jedem Teil, im Kopf je
    Stange Querschnitt mit Nahtlage (roter Punkt) und gedrehte Teile; Gehrungen ineinander: grüne Schnittkanten,
    Ersparnis einmal je Stange."""
    ZEILE = 74
    LEGENDE = 20
    GRUEN = "#1E7B34"
    doppelklick = Signal(str)       # Bezug (ref) des Teils unter der Maus
    klick = Signal(str)             # Bezug (ref) des angeklickten Teils (Abmessungs-Fenster: Zeile der Teileliste)

    def __init__(self):
        super().__init__()
        self.muster, self.farben, self.flaechen = [], {}, []
        self.markiert = None        # Bezug (ref) der hervorgehobenen Teile
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip("Doppelklick auf ein Teil: zur Position")

    def teil_bei(self, punkt):
        """Bezug (ref) des Teils an der Stelle punkt, sonst None."""
        t = self._teil_bei(punkt)
        return t["ref"] if t else None

    def _teil_bei(self, punkt):
        return next((t for r, t in self.flaechen if r.contains(QPointF(punkt))), None)

    def mouseDoubleClickEvent(self, ereignis):
        ref = self.teil_bei(ereignis.position() if hasattr(ereignis, "position") else ereignis.pos())
        if ref:
            self.doppelklick.emit(ref)

    def mousePressEvent(self, ereignis):
        ref = self.teil_bei(ereignis.position() if hasattr(ereignis, "position") else ereignis.pos())
        if ref:
            self.klick.emit(ref)
        super().mousePressEvent(ereignis)

    def markieren(self, ref):
        """Teile mit dem Bezug ref hervorheben (None = keins)."""
        self.markiert = ref
        self.update()

    def muster_y(self, i):
        """Obere Kante des i-ten Stangenmusters [px] (zum Hinscrollen)."""
        return 10 + (self.LEGENDE if self._legende() else 0) + self.ZEILE * i

    def event(self, ereignis):
        if ereignis.type() == QEvent.ToolTip:
            t = self._teil_bei(ereignis.pos())
            QToolTip.showText(ereignis.globalPos(), self.tipp(t) if t else self.toolTip(), self)
            return True
        return super().event(ereignis)

    @staticmethod
    def tipp(t):
        """Tooltip eines Teils: Pos., Länge, Naht, Drehung, Trennung zum Vorgänger, Ersparnis."""
        zeilen = [f"Pos. {t['pos'] if t['pos'] is not None else t['artikel']} · {_z(t['laenge'], 1)} mm"]
        _, text = rechnen.teil_zeichen(t)
        zeilen.append(text or "Keine Nahtvorgabe, nicht gedreht")
        if t.get("trennung"):
            zeilen.append(f"Zum Vorgänger: {t['trennung']}")
        if t.get("eingespart_mm"):
            zeilen.append(f"Gemeinsamer Schnitt: {_z(t['eingespart_mm'], 1)} mm Schneidweg gespart")
        zeilen.append("Doppelklick: zur Position")
        return "\n".join(zeilen)

    def _legende(self):
        return any(rechnen.gehrung_gespart(s) > 0 or rechnen.stange_zeichen(s)[2] for s, _ in self.muster)

    def setzen(self, ergebnis, farben=None):
        """farben = {ref: Farbe} von außen (Stangen-Detail: dieselben Farben wie in der Übersicht), sonst je Position
        in der Reihenfolge des ersten Auftretens."""
        self.muster = rechnen.stangenmuster(ergebnis)
        if farben is None:
            from .stangen_ansicht import teil_farben
            farben = teil_farben([s for s, _ in self.muster])
        self.farben = {r: QColor(f) for r, f in farben.items()}
        hoehe = 20 + self.ZEILE * len(self.muster) + (self.LEGENDE if self._legende() else 0)
        self.setMinimumHeight(max(60, hoehe))
        self.update()

    def _symbol(self, p, q, lage, x, y):
        """Querschnitt (Blick von Ende A) mit rotem Punkt an der Naht, Kantenlänge 12 px ab (x, y) oben links."""
        b, h = rechnen.symbol_masse(q)
        g = 12
        mx, my = x + g / 2, y + g / 2
        r = QRectF(mx - b * g / 2, my - h * g / 2, b * g, h * g)
        p.setPen(QPen(stil.farbe("#404040"), 1.2))
        p.setBrush(Qt.NoBrush)
        p.setRenderHint(QPainter.Antialiasing, True)
        if q and q[0] == "Kasten":
            p.drawRect(r)
        else:
            p.drawEllipse(r)
        if lage is not None:
            nx, ny = rechnen.naht_punkt(q, lage)
            p.setPen(Qt.NoPen)
            p.setBrush(stil.farbe("#D0021B"))
            p.drawEllipse(QPointF(mx + nx * g, my - ny * g), 2.6, 2.6)
            p.setBrush(Qt.NoBrush)
        p.setRenderHint(QPainter.Antialiasing, False)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        if not self.muster:
            p.drawText(self.rect(), Qt.AlignCenter, "Noch nicht optimiert.")
            return
        x0, breite = 10, max(200, self.width() - 20)
        self.flaechen = []
        klein = QFont(self.font())
        klein.setPointSizeF(max(7.0, klein.pointSizeF() - 1.5))
        fett = QFont(self.font())
        fett.setBold(True)
        y = 10
        if self._legende():
            p.setFont(klein)
            p.setPen(stil.farbe("#404040"))
            p.drawText(x0, y, breite, 16, Qt.AlignLeft | Qt.AlignVCenter,
                       "Roter Strich = Schweißnaht (gestrichelt: hinten liegend); hinter dem Stangentitel der "
                       "Querschnitt von Ende A mit rotem Punkt an der Naht.  Grün = Gehrungen ineinandergelegt; die "
                       "Ersparnis ist in Rest und Ausnutzung schon enthalten.")
            y += self.LEGENDE
        for s, nummern in self.muster:
            p.setPen(stil.farbe("#202020"))
            p.setFont(fett)
            anz = len(nummern)
            nr_text = ", ".join(map(str, nummern)) if anz <= 6 else f"{nummern[0]}–{nummern[-1]}"
            kopf = (f"{anz} × Stange {nr_text}: {s['profil']}  {rechnen.material_text(s['werkstoff'], s.get('oberflaeche'))}  {_z(s['stange'], 0)} mm")
            if any(t.get("ansicht") == "von oben" for t in s["teile"]):
                kopf += "  (Ansicht von oben)"
            p.drawText(x0, y + 12, kopf)
            lage, q, zeichen = rechnen.stange_zeichen(s)
            if zeichen:                     # Naht und Drehung einmal je Stange
                xs = x0 + p.fontMetrics().horizontalAdvance(kopf) + 12
                self._symbol(p, q, lage, xs, y + 2)
                p.setFont(klein)
                p.setPen(stil.farbe("#202020"))
                p.drawText(QRectF(xs + 17, y, 400, 16), Qt.AlignLeft | Qt.AlignVCenter, zeichen)
            summe = sum(t["laenge"] for t in s["teile"])
            rest = s["stange"] - s["end"] - summe - s["verlust"]
            gespart = rechnen.gehrung_gespart(s)
            p.setFont(klein)
            p.setPen(stil.farbe("#202020"))
            werte = f"{len(s['teile'])} Teile · Rest {_z(rest, 1)} mm · Ausnutzung {_z(100 * summe / s['stange'], 1)} %"
            p.drawText(x0 + breite - 330, y, 330, 16, Qt.AlignRight | Qt.AlignVCenter, werte)
            if gespart > 0:                 # Ersparnis einmal je Stange, links neben Rest und Ausnutzung
                p.setPen(QColor(self.GRUEN))
                rechts = x0 + breite - p.fontMetrics().horizontalAdvance(werte) - 12
                p.drawText(QRectF(rechts - 300, y, 300, 16), Qt.AlignRight | Qt.AlignVCenter,
                           f"Gehrungen ineinander: {_z(gespart, 1)} mm gespart ·")
            m = breite / s["stange"]
            yb, hb = y + 20, 34
            oben = 270 if any(t.get("ansicht") == "von oben" for t in s["teile"]) else 0

            def rechteck(von, bis, farbe, rand=stil.farbe("#5F6B7A")):
                r = QRectF(x0 + von * m, yb, max(1.0, (bis - von) * m), hb)
                p.fillRect(r, farbe)
                p.setPen(QPen(rand, 1))
                p.drawRect(r)
                return r
            rechteck(0, s["stange"], stil.farbe("#EDEDED"))                         # Rest
            rechteck(0, s["end"], stil.farbe("#A6A6A6"))                             # Endbeschnitt
            rechteck(s["stange"] - s["greif"], s["stange"], stil.farbe("#E06666"))   # Greiferrest
            if s.get("greif_3d"):           # 3D-Bearbeitung am letzten Teil: 3D-Greifmaß statt Greiferrest
                p.setPen(stil.farbe("#FFFFFF"))
                p.drawText(QRectF(x0 + (s["stange"] - s["greif"]) * m, yb, s["greif"] * m, hb), Qt.AlignCenter, "3D")
            vorher = None
            for t in s["teile"]:
                ineinander = bool(t.get("material_gespart")) and vorher is not None
                if t.get("kante_a") or t.get("kante_b"):        # schräge Enden: Umriss mit Schnittkanten
                    ol, or_, ur, ul = rechnen.umriss(t)
                    form = QPolygonF([QPointF(x0 + ol * m, yb), QPointF(x0 + or_ * m, yb),
                                      QPointF(x0 + ur * m, yb + hb), QPointF(x0 + ul * m, yb + hb)])
                    p.setPen(QPen(stil.farbe("#202020"), 2))
                    p.setBrush(self.farben.get(t["ref"], stil.farbe("#4E79A7")))
                    p.drawPolygon(form)
                    p.setBrush(Qt.NoBrush)
                    r = QRectF(x0 + max(ol, ul) * m, yb, max(1.0, (min(or_, ur) - max(ol, ul)) * m), hb)
                else:
                    r = rechteck(t["von"], t["bis"], self.farben.get(t["ref"], stil.farbe("#4E79A7")))
                    p.setPen(QPen(stil.farbe("#202020"), 2))
                    p.drawLine(r.topLeft(), r.bottomLeft())
                    p.drawLine(r.topRight(), r.bottomRight())
                if ineinander:      # Stoß der ineinandergelegten Gehrungen: beide Schnittkanten grün
                    p.setRenderHint(QPainter.Antialiasing, True)
                    p.setPen(QPen(QColor(self.GRUEN), 3))
                    for u, a, b in ((vorher, 1, 2), (t, 0, 3)):
                        x = rechnen.umriss(u)
                        p.drawLine(QPointF(x0 + x[a] * m, yb), QPointF(x0 + x[b] * m, yb + hb))
                    p.setRenderHint(QPainter.Antialiasing, False)
                strich = rechnen.naht_strich(t, oben)
                if strich and r.width() > 6:       # Schweißnaht als roter Strich über die Länge des Teils
                    hy = yb + hb / 2 - strich[0] * (hb / 2 - 3)
                    stift = QPen(stil.farbe("#D0021B"), 3)
                    if not strich[1]:
                        stift.setStyle(Qt.DashLine)
                    p.setPen(stift)
                    p.drawLine(QPointF(r.left() + 3, hy), QPointF(r.right() - 3, hy))
                if self.markiert is not None and t["ref"] == self.markiert:
                    p.setPen(QPen(stil.farbe(stil.ORANGE), 3))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(r.adjusted(-1, -1, 1, 1))
                self.flaechen.append((QRectF(r), t))
                text = f"{t['pos'] if t['pos'] is not None else t['artikel']}\n{_z(t['laenge'], 1)}"
                if r.width() > 28:
                    p.setPen(stil.schrift_auf(self.farben.get(t["ref"], stil.farbe("#4E79A7"))))   # lesbar auf der Teilfarbe
                    p.setFont(klein)
                    p.drawText(r, Qt.AlignCenter, text if r.width() > 46 else str(t["pos"] or ""))
                vorher = t
            y += self.ZEILE
        p.end()


def laengen_html(erg, kopf, positionen, k, tabellen, einst, nur=None):
    """Vergleich der Lieferlängen je Gruppe als HTML: Kennzahlen je Variante, Empfehlung mit Begründung und Links
    zum Übernehmen (laenge:<Gruppe>:<Länge>, 0 = Stangenlänge des Angebots). nur = Indizes der Gruppen, die
    gezeigt werden (Abmessungs-Fenster), None = alle."""
    if not erg:
        return "<i>Noch nicht optimiert.</i>"
    if not erg.get("laengen") and not rechnen.laengen_vergleichen(einst):
        return ("Der Vergleich mit anderen Lieferlängen (z. B. 12 m) ist ausgeschaltet: Einstellungen → Vorgaben → "
                "Lieferlängen, „beim Optimieren andere Lieferlängen vergleichen“ = ja. Ist die Stangenlänge des "
                "Angebots für ein Profil nicht lieferbar, wird trotzdem mit einer lieferbaren Länge geplant.")
    if not erg.get("laengen"):
        return ("Für die Profile dieses Angebots gibt es keine weitere Lieferlänge: verglichen wird, was unter "
                "Einstellungen → Lieferlängen steht, und ohne Eintrag Profile über dem Hüllkreis-Ø aus den "
                "Einstellungen (Vorgabe 70 mm) mit 12 m. Kleinere Profile ohne Eintrag werden nie mit 12 m geplant.")
    zeilen = [("Benötigte Stangen", lambda v: _z(v["lieferstangen"], 0)),
              ("Beladungen der Maschine (Stangen)", lambda v: _z(v["werkstuecke"], 0)),
              ("Zuschnitte beim Lieferanten", lambda v: _z(v["zuschnitte"], 0) if v["zuschnitt"] else "–"),
              ("Stangenlängen nach Zuschnitt [mm]", lambda v: ", ".join(_z(l, 0) for l in v["werkstueck_laengen"]) or "–"),
              ("Materiallänge [m]", lambda v: _z(v["material_mm"] / 1000, 1)),
              ("Materialkosten [€]", lambda v: _z(v["material"])),
              ("Stangenwechsel / je Beladung [€]", lambda v: _z(v["werkstueck_kosten"])),
              ("Zuschnittkosten [€]", lambda v: _z(v["zuschnitt_kosten"]) if v["zuschnitt"] else "–"),
              ("Reststückwert [€]", lambda v: "nicht angerechnet"),
              ("<b>Gesamtkosten [€]</b>", lambda v: f"<b>{_z(v['gesamt'])}</b>"),
              ("Verschnitt [mm]", lambda v: _z(v["verschnitt_mm"], 0)),
              ("Verschnitt [%]", lambda v: _z(100 * v["verschnitt_anteil"], 1)),
              ("Angaben fehlen", lambda v: ", ".join(v["fehlt"]) or "–")]
    farbe = {rechnen.LAENGE_ALTERNATIVE: "#1E7B34", rechnen.LAENGE_NUR_ALTERNATIVE: "#1E7B34",
             rechnen.LAENGE_ANGABEN_FEHLEN: "#B45F06"}
    teile = []
    for i, vg in enumerate(erg["laengen"]):
        if nur is not None and i not in nur:
            continue
        b = rechnen.laengen_bewerten(vg, kopf, positionen, k, tabellen, einst)
        geplant = vg.get("gewaehlt") or vg["stange"]
        kopfz = "".join(f"<th align='right'>{rechnen.m_text(v['laenge'])}-m-Variante"
                        + (" (geplant)" if v["laenge"] == geplant else "") + "</th>" for v in b["varianten"])
        if not vg["basis_lieferbar"]:
            kopfz = f"<th align='right'>{rechnen.m_text(vg['stange'])} m: nicht lieferbar</th>" + kopfz
        html = [f"<p><b>{vg['profil']} · {rechnen.material_text(vg['werkstoff'], vg.get('oberflaeche'))}</b> "
                f"(Stangenlänge des Angebots {_z(vg['stange'], 0)} mm, max. Beladelänge "
                f"{_z(vg.get('max_werkstueck'), 0) if vg.get('max_werkstueck') else '–'} mm)"
                + ("<br><i>12 m ohne Eintrag in Lieferlängen angenommen (Hüllkreis-Ø über der Grenze in den "
                   "Einstellungen), Preis wie unter Preise.</i>" if vg.get("automatisch") else "") + "</p>",
                "<table border='1' cellspacing='0' cellpadding='3'><tr><th align='left'>Kennzahl</th>" + kopfz + "</tr>"]
        for n, (titel, f) in enumerate(zeilen):
            # nicht ausführbare Variante: Grund in der ersten Zeile, sonst leer
            wert = lambda v: f(v) if not v["fehler"] else ("nicht ausführbar: " + v["fehler"] if n == 0 else "")
            zellen = "".join(f"<td align='right'>{wert(v)}</td>" for v in b["varianten"])
            if not vg["basis_lieferbar"]:
                zellen = "<td></td>" + zellen
            html.append(f"<tr><td>{titel}</td>{zellen}</tr>")
        html.append("</table>")
        html.append(f"<p><span style='color:{farbe.get(b['empfehlung'], '#202020')}'><b>{b['titel']}</b></span><br>"
                    f"{b['begruendung']}</p>")
        mi = b.get("mischung")
        if mi:      # Vorschlag Mischen: nur zum Ansehen, der Schnittplan bleibt (Patrick 28.10.2026)
            statt = " bzw. ".join(f"{_z(x)} € mit nur {rechnen.m_text(l)} m" for x, l in
                                  ((mi["statt_basis"], vg["stange"]), (mi["statt_lang"], mi["laenge"])) if x is not None)
            html.append(f"<p><span style='color:#1E5BA8'><b>Vorschlag Mischen: {mi['text']}</b></span><br>"
                        f"Die am schlechtesten belegten {rechnen.m_text(mi['laenge'])}-m-Stangen werden durch "
                        f"{rechnen.m_text(vg['stange'])}-m-Stangen ersetzt: {_z(mi['gesamt'])} € statt {statt} "
                        f"(spart {_z(mi['ersparnis'])} €, Materiallänge {_z(mi['mischung']['material_mm'] / 1000, 1)} m, "
                        f"{_z(mi['mischung']['werkstuecke'], 0)} Beladungen"
                        + (f", Angaben fehlen: {', '.join(mi['fehlt'])}" if mi["fehlt"] else "")
                        + f"). <a href='mischung:{i}:{mi['laenge']}'>Stangenbelegung ansehen …</a> <i>Nur ein "
                        "Vorschlag zum Ansehen – der Schnittplan wird dadurch nicht geändert.</i></p>")
        links = [f"<a href='laenge:{i}:{v['laenge']}'>{rechnen.m_text(v['laenge'])}-m-Stangen übernehmen</a>"
                 for v in b["varianten"] if v["laenge"] != geplant and v["laenge"] != vg["stange"] and not v["fehler"]]
        if geplant != vg["stange"] and vg["basis_lieferbar"]:
            links.append(f"<a href='laenge:{i}:0'>wieder {rechnen.m_text(vg['stange'])}-m-Stangen verwenden</a>")
        if links:
            html.append("<p>Geplant: " + f"{rechnen.m_text(geplant)} m. " + " · ".join(links) + "</p>")
        teile.append("".join(html))
    return "<hr>".join(teile)


def laengen_sinnvoll(erg, kopf, positionen, k, tabellen, einst):
    """Kurztext, wenn der Vergleich der Lieferlängen eine sinnvolle Lösung zeigt (eine andere Länge ist empfohlen
    oder nur sie ist lieferbar) oder schon eine andere Länge geplant ist; sonst None (Knopf ausgeblendet)."""
    texte = []
    for vg in (erg or {}).get("laengen") or []:
        b = rechnen.laengen_bewerten(vg, kopf, positionen, k, tabellen, einst)
        if vg.get("gewaehlt") and vg["gewaehlt"] != vg["stange"]:
            texte.append(f"{vg['profil']}: {rechnen.m_text(vg['gewaehlt'])} m geplant")
        elif b["empfehlung"] in (rechnen.LAENGE_ALTERNATIVE, rechnen.LAENGE_NUR_ALTERNATIVE):
            texte.append(f"{vg['profil']}: {b['titel']}")
        if b.get("mischung") and not b["mischung"]["fehlt"]:
            texte.append(f"{vg['profil']}: Vorschlag Mischen {b['mischung']['text']} spart {_z(b['mischung']['ersparnis'])} €")
    return " · ".join(texte) or None


class WerteUebernehmenDialog(QDialog):
    """Wiederholteil (Plan A1): übernehmbare Werte der alten Position einzeln an- oder abwählen; nie den Preis."""

    def __init__(self, parent, position, treffer, felder):
        from .wiederholteile import text
        super().__init__(parent)
        self.setWindowTitle("Werte übernehmen")
        lay = QVBoxLayout(self)
        kopf = QLabel(f"<b>Pos. {position.get('pos')} · {position.get('artikel') or position.get('bezeichnung') or ''}"
                      f"</b><br>{text([treffer])}<br>Aus Pos. {treffer.position.get('pos')} in "
                      f"{treffer.angebot['nummer']} ({treffer.angebot.get('kunde') or ''}):")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        self.haken = {}
        for f, titel in felder:
            if f not in treffer.werte:
                continue
            alt, neu = position.get(f), treffer.werte[f]
            c = QCheckBox(f"{titel}: {_wert_kurz(neu)}" + (f"   (bisher {_wert_kurz(alt)})" if alt not in (None, "") else ""))
            c.setChecked(True)
            lay.addWidget(c)
            self.haken[f] = c
        hinweis = QLabel("Der Preis wird nicht übernommen, er entsteht neu aus der Kalkulation.")
        hinweis.setStyleSheet(f"color: {stil.TEXT_GRAU};")
        lay.addWidget(hinweis)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def gewaehlt(self):
        return [f for f, c in self.haken.items() if c.isChecked()]


def _wert_kurz(w, laenge=60):
    if isinstance(w, float):
        return zahl_als_text(w, 2 if w % 1 else 0)
    t = str(w)
    if t.startswith(("[", "{")):        # Zusatzarbeiten, Naht: JSON
        try:
            daten = json.loads(t)
            if isinstance(daten, list):
                t = ", ".join(str(x.get("name") or x.get("bezeichnung") or x) if isinstance(x, dict) else str(x)
                              for x in daten)
            elif isinstance(daten, dict):
                t = ", ".join(f"{k}: {v}" for k, v in daten.items() if v not in (None, ""))
        except ValueError:
            pass
    return t if len(t) <= laenge else t[:laenge - 1] + "…"


class LaengenDialog(QDialog):
    """Vergleich der Lieferlängen (6 m gegen 12 m) groß in einem eigenen Fenster; Links übernehmen eine Länge."""

    def __init__(self, seite):
        super().__init__(seite)
        self.setWindowTitle("Lieferlängen: 6 m gegen 12 m")
        self.resize(1250, 820)
        lay = QVBoxLayout(self)
        self.ansicht = QTextBrowser()
        self.ansicht.setOpenLinks(False)
        self.ansicht.zoomIn(4)          # groß: bessere Übersicht als im Reiter
        self.ansicht.anchorClicked.connect(lambda url: seite.laenge_waehlen(url.toString()))
        lay.addWidget(self.ansicht, 1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)


# ------------------------------------------------------------------ Angebot
def _d(w):
    return float(w) if w is not None else None


def zukauf_zeilen(gruppen):
    """Zeilen der Tabelle Zukaufteile aus summen['zukauf'] (zukauf.rechnen): eine Zeile je Artikel und Preisstand."""
    out = []
    for g in gruppen:
        st, b = g["stand"], g["bestellung"]
        out.append(dict(artikel=st.get("artikelnr"), bezeichnung=st.get("bezeichnung"),
                        einheit=zukauf.EINHEIT_KURZ.get(st.get("einheit"), st.get("einheit")),
                        lieferant=b.get("lieferant"), positionen=g["positionen"], verbrauch=_d(b["verbrauch"]),
                        bestellt=_d(b["bestellt"]), mehrmenge=_d(b["mehrmenge"]) or None,
                        staffel=f"ab {zahl_als_text(float(b['staffel']['ab']), 0)}" if b.get("staffel") else None,
                        ek=_d(b["ek"]), einkauf=_d(b["einkauf"]), bezug=_d(b["bezug"]), einstand=_d(g["einstand"]),
                        regel=g["regel"], aufschlag=_d(g["aufschlag"]), vk=_d(g["vk"]),
                        db_pct=_d(g["aufschlag"] / g["vk"] * 100) if g["vk"] else None,
                        stand=datum_text(st.get("datum")),
                        hinweis=("FEHLER: " + g["fehler"]) if g["fehler"]
                        else ("WARNUNG: " + g["warnung"]) if g["warnung"] else ""))
    return out


def zukauf_info(summen):
    n = len(summen["zukauf"])
    if not n:
        return ("Keine Zukaufteile. Zukaufteile einer Position: Position markieren, dann 'Zukaufteile …' "
                "(oder Doppelklick in die Spalte Zukaufteile).")
    e, a = summen["zukauf_einstand"], summen["zukauf_aufschlag"]
    return (f"{n} Artikel · Einstand {_z(e)} € · Aufschlag {_z(a)} € · Verkauf {_z(e + a)} € (netto, ohne Skonto). "
            "Gleiche Artikel aller Positionen werden zusammen bestellt; gerechnet wird mit dem Preisstand, der in "
            "den Positionen gespeichert ist.")


ZUKAUF_SPALTEN = [("Artikelnr.", "artikel", None, 90), ("Bezeichnung", "bezeichnung", None, 180),
                  ("Einheit", "einheit", None, 50), ("Lieferant", "lieferant", None, 120),
                  ("Positionen", "positionen", 0, 70), ("Verbrauch", "verbrauch", 2, 75),
                  ("Bestellmenge", "bestellt", 2, 95), ("Mehrmenge", "mehrmenge", 2, 75),
                  ("Preisstaffel", "staffel", None, 75), ("EK je Einheit [€]", "ek", 4, 85),
                  ("Einkauf [€]", "einkauf", 2, 80), ("Bezugskosten [€]", "bezug", 2, 95),
                  ("Einstand [€]", "einstand", 2, 80), ("Aufschlagsregel", "regel", None, 170),
                  ("Aufschlag [€]", "aufschlag", 2, 80), ("Verkauf netto [€]", "vk", 2, 85),
                  ("Deckungsbeitrag [% vom VK]", "db_pct", 1, 110), ("Preisstand", "stand", None, 80),
                  ("Hinweis", "hinweis", None, 220)]
PROT_SPALTEN = [(t, (lambda i: lambda z: z[i] if i < len(z) else None)(i), None, 90) for i, t in enumerate(step.PROTOKOLL)]


KALK_IMMER = {"pos", "artikel", "stueck", "material_teil", "herstell_teil", "preis_teil", "preis_position"}
KOMPAKT_IMMER = {"pos", "artikel", "profil", "stueck", "laenge", "material", "oberflaeche", "laser_brutto", "laser_netto",
                 "preis_teil", "preis_position"}
# Reiter Stangenbild: Stangenmuster, Übersicht oder Detail; seit 0.9.146 neuer Name, damit für alle zuerst die Übersicht
# gilt (Patrick 26.10.2026: „Übersicht als Standardansicht“), danach wird die Wahl wieder gemerkt
STANGENBILD_EINSTELLUNG = "ansicht_stangenbild_2"
KOMPAKT_EINSTELLUNG = "ansicht_kalk_kompakt"    # Reiter Kalkulation: kompakte Übersicht (Vorgabe) oder alle Spalten
PLAN_GLEICH = {"profil", "werkstoff", "oberflaeche", "stange", "end", "greif"}   # einmal über dem Schnittplan
UEBERSICHT_MIN, UEBERSICHT_BREIT = 320, 400      # Breite der Übersicht rechts (1366 px bzw. ab 1700 px)


class _AuswahlUnter(UnterzeilenMixin, Auswahl):
    """Auswahl der Positionsliste, Zelle oben, darunter die Zusatzarbeiten (unterzeilen.py)."""


class AngebotReiter(QTabWidget):
    """Reiter eines Angebots. Zusammengehörige Seiten liegen als Unterreiter in einem Reiter (Kalkulation mit
    Zeiten, Schnittplan mit Stangenbild und Auswertung). setCurrentWidget, indexOf und waehlen finden auch
    Seiten in den Unterreitern."""

    def __init__(self):
        super().__init__()
        self.gruppen = []

    def gruppe(self, text, seiten):
        g = QTabWidget()
        g.setDocumentMode(True)
        g.gruppe_von = self              # Strg+Bild↓/↑ blättert in den Reitern des Angebots, nicht hier
        for w, t in seiten:
            g.addTab(w, t)
        self.gruppen.append(g)
        self.addTab(g, text)
        return g

    @staticmethod
    def _in(seite, w):
        return seite is w or seite.isAncestorOf(w)

    def indexOf(self, w):
        for i in range(self.count()):
            if self._in(self.widget(i), w):
                return i
        return -1

    def setCurrentWidget(self, w):
        i = self.indexOf(w)
        if i < 0:
            return
        self.setCurrentIndex(i)
        g = self.widget(i)
        if g in self.gruppen and g is not w:
            j = next((j for j in range(g.count()) if self._in(g.widget(j), w)), -1)
            if j >= 0:
                g.setCurrentIndex(j)

    def ort(self, text):
        """(Reiterleiste, Index) des Reiters oder Unterreiters mit diesem Text."""
        for i in range(self.count()):
            if self.tabText(i) == text:
                return self, i
        for g in self.gruppen:
            for j in range(g.count()):
                if g.tabText(j) == text:
                    return g, j
        raise KeyError(text)

    def waehlen(self, text):
        leiste, i = self.ort(text)
        if leiste is self:
            self.setCurrentIndex(i)
            if self.widget(i) in self.gruppen:
                self.widget(i).setCurrentIndex(0)
        else:
            self.setCurrentWidget(leiste.widget(i))

    def texte(self):
        """Alle Reiter- und Unterreitertexte (für den Abgleich mit der Anleitung)."""
        return [self.tabText(i) for i in range(self.count())] + [g.tabText(j) for g in self.gruppen
                                                               for j in range(g.count())]


class SchnellFeld(QLineEdit):
    """Eingabefeld der Schnellzeile: Einfügen mehrerer Zeilen meldet sie (mehrzeilig) statt sie zu verbinden."""
    mehrzeilig = Signal(str)

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Paste):
            text = QApplication.clipboard().text()
            if "\n" in text.strip():
                self.mehrzeilig.emit(text)
                return
        super().keyPressEvent(e)


def blaetterbar(liste=False):
    """Editor-Methode der Angebotsseite mit Blättern (Plan Bedienung B3): ◀ ▶ im Editor schließt ihn (Änderungen
    übernommen, Freigabe F3a) und öffnet gleich die vorige bzw. nächste Position derselben Art. liste: die Methode
    erwartet eine Liste von Zeilen (Baugruppe)."""
    def deko(methode):
        @functools.wraps(methode)
        def huelle(self, *a, **kw):
            if getattr(self, "_blaettern_laeuft", False):
                return methode(self, *a, **kw)
            self._blaettern_laeuft = True
            try:
                self._blaettern_ziel = None
                erg = methode(self, *a, **kw)
                while self._blaettern_ziel is not None:
                    ziel, self._blaettern_ziel = self._blaettern_ziel, None
                    if not 0 <= ziel < len(self.positionen):
                        break
                    self.pos_ansicht.selectRow(ziel)
                    weiter = {n: v for n, v in kw.items() if n == "dialog"}
                    erg = methode(self, [ziel] if liste else ziel, **weiter)
            finally:
                self._blaettern_laeuft = False
            return erg
        return huelle
    return deko


def _ids_ersetzen(x, karte):
    """Vorläufige Positions-IDs (karte {'<ID>~<n>': neue ID}) in einer verschachtelten Struktur ersetzen, auch in
    Schlüsseln und in eingebetteten JSON-Texten."""
    if isinstance(x, dict):
        return {(karte.get(k, k) if isinstance(k, str) else k): _ids_ersetzen(w, karte) for k, w in x.items()}
    if isinstance(x, (list, tuple)):
        return type(x)(_ids_ersetzen(w, karte) for w in x)
    if isinstance(x, str):
        if x in karte:
            return karte[x]
        if x[:1] in "{[" and any(k in x for k in karte):
            try:
                return json.dumps(_ids_ersetzen(json.loads(x), karte), ensure_ascii=False)
            except ValueError:
                return x
    return x


class AngebotSeite(QWidget):
    # Tastenkürzel (siehe tastatur.py); Entf nur in der Positionsliste
    KUERZEL = {"neu": "position_neu", "loeschen": ("positionen_loeschen", "pos_ansicht"),
               "rueckgaengig": "rueckgaengig", "wiederholen": "wiederholen", "einfuegen": "_einfuegen",
               "ausschneiden": "_ausschneiden", "optimieren": "optimieren", "drucken": "angebot_pdf",
               "importieren": "step_importieren", "staffeln": "staffelpreise_rechnen", "werkstatt": "werkstatt_pdf",
               "kalkulation": "kalkulation_pdf", "material": "material_anfragen", "stueck": "stueck_aendern",
               "duplizieren": "position_duplizieren", "hoch": ("positionen_hoch", "pos_ansicht"), "runter": ("positionen_runter", "pos_ansicht")}

    def __init__(self, fenster, angebot_id):
        super().__init__()
        self.setAcceptDrops(True)       # STEP-Dateien und Ordner per Drag & Drop importieren
        self.f, self.db, self.id = fenster, fenster.db, angebot_id
        self.verlauf = Verlauf(self.db, angebot_id)     # Rückgängig/Wiederholen
        self._laden = False
        self.kopf, self.positionen, self.ergebnis = {}, [], None

        # Kopf und Kalkulationseinstellungen (links), Übersicht (rechts): siehe angebot_oben.py
        self.kopf_bereich = KopfBereich(self)
        self.felder = self.kopf_bereich.felder
        self.maschinenwerte = self.kopf_bereich.maschinenwerte
        self.uebersicht_bereich = UebersichtBereich()
        self.stand = self.uebersicht_bereich.stand
        self.uebersicht = self.uebersicht_bereich.uebersicht
        self.uebersicht_bereich.preise_knopf.clicked.connect(lambda _=False: self.preise_aktualisieren())
        self.uebersicht_bereich.wiederholteile.linkActivated.connect(self.wiederholteil_link)
        self.uebersicht_bereich.freigabe.linkActivated.connect(self.check_link)
        oben_rahmen = QScrollArea()          # kleine Fenster: Kopf und Kalkulation scrollen
        oben_rahmen.setWidgetResizable(True)
        oben_rahmen.setFrameShape(QFrame.NoFrame)
        oben_rahmen.setWidget(self.kopf_bereich)
        # Übersicht als rechte Spalte über die ganze Höhe: Preise immer im Blick, die Reiter bekommen mehr Höhe
        self.uebersicht_rahmen = UebersichtRahmen(self.uebersicht_bereich, UEBERSICHT_MIN)

        # Aktionen in drei Gruppen (Layout-Plan L9): Erfassen · Rechnen · Ausgeben. Rechts nur Angebot (PDF) als
        # Knopf, alle weiteren Ausgaben im Menü „Ausgaben“; Positionen löschen über Rechtsklick oder Entf
        # (Bearbeiten → Löschen …).
        self.leiste = UmbruchLeiste()     # bei schmalem Fenster rückt die Ausgabe in eine zweite Zeile
        leiste = self.leiste.links_layout
        # „STEP importieren …“ steht nur noch im Menü (Strg+I): das Ablagefeld lädt STEP und DXF per Ziehen oder Klick
        b = QPushButton("Neue Position")
        b.clicked.connect(lambda: self.position_neu())
        leiste.addWidget(b)
        self.ablage_klein = AblageFeld()       # sichtbares Ziel für Drag & Drop direkt neben „Neue Position“
        self.ablage_klein.geklickt.connect(lambda: self.dateien_waehlen())
        leiste.addWidget(self.ablage_klein)
        leiste.addSpacing(16)
        optimieren = QPushButton("Optimieren")
        optimieren.setObjectName("primaer")     # Hauptknöpfe (dunkelblau): Optimieren und Angebot (PDF)
        optimieren.clicked.connect(lambda: self.optimieren())
        leiste.addWidget(optimieren)
        zusatz = QPushButton("Zusatzarbeiten …")
        zusatz.clicked.connect(lambda: self.zusatzarbeiten())
        leiste.addWidget(zusatz)
        self.zukauf_knopf = QPushButton("Zukaufteile …")      # Auswahlmenü statt weiterer Knöpfe
        menue = QMenu(self.zukauf_knopf)
        menue.addAction("Zukaufteile bearbeiten …", lambda: self.zukaufteile())
        menue.addAction("Neuer Zukaufartikel …", lambda: self.zukauf_schnell())
        menue.addAction("EK eintragen …", lambda: self.zukauf_ek())
        self.zukauf_knopf.setMenu(menue)
        self.zukauf_knopf.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0px; }")
        leiste.addWidget(self.zukauf_knopf)
        # Material je Abmessung (Patrick 22.10.2026)
        self.material_knopf = QPushButton("Material …")
        self.material_knopf.setToolTip("Materialeinsatz je Abmessung; Werkstoff, Oberfläche, Lieferlänge, Material und "
                                       "Meterpreis ändern")
        self.material_knopf.clicked.connect(lambda: self.material_einstellen())
        leiste.addWidget(self.material_knopf)
        ansicht = QPushButton("3D-Ansicht …")
        ansicht.clicked.connect(lambda: self.ansicht_3d())
        leiste.addWidget(ansicht)
        leiste = self.leiste.rechts_layout
        pdf = QPushButton("Angebot (PDF)")
        pdf.setObjectName("primaer")
        pdf.clicked.connect(lambda: self.angebot_pdf())
        leiste.addWidget(pdf)
        self.weitere = QPushButton("Ausgaben")
        self.weitere.setToolTip("Werkstattpapiere, Kalkulation, Materialanfrage, CSV-Export und weitere Aktionen")
        menue = QMenu(self.weitere)
        menue.addAction("Angebots-Check …", lambda: self.check_zeigen())
        fa = self.funktion_aktionen = []          # (Aktion, Funktion): ausgeblendet, wenn die Funktion aus ist
        # Angebot per E-Mail (Vorschlag V1, 31.10.2026): PDF + Outlook, als Antwort auf die Anfrage-Mail
        fa.append((menue.addAction("Angebot per E-Mail …", lambda: self.angebot_mail()), "funktion_angebot_mail"))
        menue.addSeparator()
        # Auftragsbestätigung (Plan 29.10.2026 1c): im Layout des Angebots, mit Bestellnummer und Liefertermin
        fa.append((menue.addAction("Auftragsbestätigung (PDF)", lambda: self.auftragsbestaetigung_pdf()), "funktion_ab"))
        menue.addAction("Werkstattpapiere (PDF)", lambda: self.werkstatt_pdf())
        # Etiketten mit QR-Code für die Rückmeldung per Scan (Plan 29.10.2026 2a, etiketten.py)
        fa.append((menue.addAction("Etiketten mit QR-Code (PDF) …", lambda: self.etiketten_pdf()), "funktion_etiketten"))
        self.palettenschein_aktion = menue.addAction("Palettenbegleitschein …", lambda: self.f.palettenschein(self.id))
        menue.aboutToShow.connect(lambda: self.palettenschein_aktion.setVisible(self.f.versand_an()))
        menue.addAction("Kalkulation (PDF)", lambda: self.kalkulation_pdf())
        # Materialanfrage (Patrick 22.10.2026): Stangenbedarf beim Lieferanten anfragen, gesendet wird nur im Mailprogramm
        self.anfrage_aktion = menue.addAction("Materialanfrage (E-Mail)", lambda: self.material_anfragen())
        fa.append((self.anfrage_aktion, "funktion_materialanfrage"))
        # Materialbestand und Reststücke (lager.py): nur mit Einstellung 'lager_aktiv'
        self.lager_aktion = menue.addAction("Material aus Lager …", lambda: self.material_aus_lager())
        menue.aboutToShow.connect(lambda: self.lager_aktion.setVisible(self.f.lager_an()))
        # Freigabe und Fertigungsstatus (fertigung.py): Reiter Fertigung mit diesem Auftrag
        self.fertigung_aktion = menue.addAction("Fertigungsstatus …", lambda: self.f.fertigung_zeigen(self.id))
        menue.aboutToShow.connect(lambda: self.fertigung_aktion.setVisible(self.f.fertigung_an()))
        # Material-/Fertigungsvarianten mit Zielgröße (varianten.py)
        fa.append((menue.addAction("Varianten vergleichen …", lambda: self.varianten_vergleichen()), "funktion_simulator"))
        # Arbeitsgänge je Position mit Vorschlägen der Arbeitsgang-Regeln (arbeitsgaenge.py)
        menue.addAction("Arbeitsgänge vorschlagen …", lambda: self.arbeitsgaenge_vorschlagen())
        # Reklamationen je Auftrag/Position mit Kosten in der Nachkalkulation (Plan 29.10.2026 2c)
        self.reklamation_aktion = menue.addAction("Reklamation erfassen …", lambda: self.reklamation_erfassen())
        fa.append((self.reklamation_aktion, "funktion_reklamation"))
        menue.aboutToShow.connect(lambda: self.reklamation_aktion.setEnabled(
            (self.db.angebot(self.id) or {}).get("vorgang") == "Beauftragt" and not self.fremd()))
        fa.append((menue.addAction("Nachfassen vermerken …", lambda: self.f.angebote.nachfassen(self.id)),  # Plan A9
                   "funktion_nachfassen"))
        fa.append((menue.addAction("Wiedervorlage …", lambda: self.f.angebote.wiedervorlage_setzen(self.id)),
                   "funktion_nachfassen"))
        # CSV-Export (export.py): Angebotskopf und Angebotspositionen als einzelne Dateien, Ordner wählbar
        csv = menue.addMenu("CSV-Export")
        csv.setToolTipsVisible(True)
        for text, ziel in (("Kopf + Positionen …", self.csv_export), ("Nur Angebotskopf …", self.csv_kopf),
                           ("Nur Angebotspositionen …", self.csv_positionen)):
            csv.addAction(text, lambda ziel=ziel: ziel())
        menue.addSeparator()
        for text, ziel in (("Schneidweg berechnen …", lambda: self.schneidweg_berechnen()),
                           ("Schweißnaht …", lambda: self.schweissnaht()),
                           ("Ordner öffnen", lambda: self.f.angebot_ordner_oeffnen(self.kopf))):
            a = menue.addAction(text, lambda ziel=ziel: ziel())
            if text == "Schweißnaht …":
                fa.append((a, "funktion_schweissen"))
        menue.aboutToShow.connect(lambda: [a.setVisible(funktionen.an(n)) for a, n in self.funktion_aktionen])
        self.weitere.setMenu(menue)
        leiste.addWidget(self.weitere)

        # Positionen und Ergebnisse
        self.pos_modell = PositionenModell(self)
        self.pos_modell.geaendert.connect(self.neu_laden)
        self.pos_ansicht = _tabelle(self.pos_modell, sortieren=False)
        self.pos_ansicht.setItemDelegate(_AuswahlUnter(self.pos_modell, self.pos_ansicht))
        # Doppelklick entscheidet _doppelklick (Dialog oder Zelle bearbeiten); Tippen und F2 bearbeiten immer
        self.pos_ansicht.setEditTriggers(QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)
        self.pos_ansicht.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.pos_ansicht.setIconSize(QSize(64, 18))     # 3D-Vorschau in der Spalte Artikelnummer
        # Eingabe springt weiter, ↓ in der letzten Zeile = neue Position, Strg+D = Wert von oben (Plan W5)
        self.excel = tabellen_eingabe.ExcelEingabe(
            self.pos_ansicht, lambda: self.db.einstellung("eingabe_richtung"), self.zeile_anhaengen,
            lambda: self._gesammelt(tabellen_eingabe.von_oben))
        self.pos_ansicht.horizontalHeader().setStretchLastSection(True)
        for i, (art, x) in enumerate(self.pos_modell.spalten):
            self.pos_ansicht.setColumnWidth(i, x.breite if art in ("feld",) + EIGENE else (240 if art == "status" else 85))
        # Rechtsklick auf eine Position: Bearbeiten-Aktionen ohne weitere Knöpfe in der Leiste. Plan Bedienung B5: nur
        # die Einträge, die zur Art der markierten Positionen passen (MENUE_ARTEN), mit Tastenkürzel; bei mehreren
        # markierten Zeilen zusätzlich „Für markierte setzen …“ (Werkstoff, Oberfläche).
        self.pos_ansicht.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pos_menue = QMenu(self.pos_ansicht)
        self.pos_aktionen = {}
        for text, ziel, tasten in (
                ("Schneidweg berechnen …", lambda: self.schneidweg_berechnen(), ""),
                ("Blech-Editor …", lambda: self.blech_bearbeiten(), ""),
                ("Baugruppe bearbeiten …", lambda: self.baugruppe_bearbeiten(self._markierte_zeilen()), ""),
                ("Schweißnaht …", lambda: self.schweissnaht(), ""),
                ("Zusatzarbeiten …", lambda: self.zusatzarbeiten(), ""),
                ("Material …", lambda: self.material_einstellen(), ""),
                ("Bohrungen prüfen …", lambda: self.bohrungen_pruefen(), ""),
                ("Anbauteile prüfen …", lambda: self.anbauteile_pruefen(), ""),
                ("STEP-Merkmale prüfen …", lambda: self.step_merkmale_pruefen(), ""),
                ("Arbeitsgänge vorschlagen …", lambda: self.arbeitsgaenge_vorschlagen(), ""),
                ("Zukaufteile bearbeiten …", lambda: self.zukaufteile(), ""),
                ("Satz in 3D …", lambda: self.satz_3d(), ""),
                ("Satz bearbeiten (Anzahl Sätze) …", lambda: self.satz_bearbeiten(), ""),
                ("Virtuelles Bauteil als STEP …", lambda: self.virtuell_step_speichern(), ""),
                ("Stege abtrennen an/aus", lambda: self.stege_abtrennen(), ""),
                ("Muster an/aus", lambda: self.muster_umschalten(), ""),
                ("Position duplizieren", lambda: self.position_duplizieren(), "Strg+Umschalt+D"),
                ("Positionen aus anderem Angebot übernehmen …", lambda: self.positionen_uebernehmen(), ""),
                ("Baugruppe in anderes Angebot kopieren …", lambda: self.baugruppe_kopieren(), ""),
                ("Für markierte setzen …", lambda: self.fuer_markierte_setzen(), ""),
                ("Stückzahl ändern …", lambda: self.stueck_aendern(), "Strg+Umschalt+S"),
                ("Nach oben", lambda: self.positionen_verschieben(reihenfolge.OBEN), "Alt+↑"),
                ("Nach unten", lambda: self.positionen_verschieben(reihenfolge.UNTEN), "Alt+↓"),
                ("An den Anfang", lambda: self.positionen_verschieben(reihenfolge.ANFANG), ""),
                ("Ans Ende", lambda: self.positionen_verschieben(reihenfolge.ENDE), ""),
                ("Positionsnummern neu vergeben (10, 20, 30 …)", lambda: self.positionsnummern_vergeben(), ""),
                ("Positionen löschen", self.positionen_loeschen, "Entf")):
            # Kürzel nur als Text rechts (Tabulator), die Kürzel selbst hängen am Menü Bearbeiten
            a = self.pos_menue.addAction(text + (f"\t{tasten}" if tasten else ""), lambda ziel=ziel: ziel())
            self.pos_aktionen[text] = a
        self.pos_menue.insertSeparator(self.pos_aktionen["Position duplizieren"])
        self.pos_menue.insertSeparator(self.pos_aktionen["Für markierte setzen …"])
        self.pos_menue.insertSeparator(self.pos_aktionen["Nach oben"])
        self.pos_menue.insertSeparator(self.pos_aktionen["Positionen löschen"])
        self.pos_menue.aboutToShow.connect(self._pos_menue_anpassen)
        self.pos_ansicht.customContextMenuRequested.connect(
            lambda punkt: self.fremd() or self._menue_zeile(punkt) or
            self.pos_menue.exec(self.pos_ansicht.viewport().mapToGlobal(punkt)))
        self.pos_ansicht.doubleClicked.connect(self._doppelklick)
        self.bg_zu, self.bg_zeilen = set(), {}
        self.satz_zu, self.satz_zeilen = set(), {}
        # Zusatzarbeiten unter der Position (Patrick 26.10.2026): je Arbeitsschritt eine eingerückte Zeile
        self.unter_texte = {}            # Index der Position -> [(Text, Warnung)] (unterzeilen.schritte)
        unter_an = self.db.einstellung(unterzeilen.EINSTELLUNG) is not False
        artikel = next(c for c in range(len(self.pos_modell.spalten)) if self.pos_modell.name(c) == "artikel")
        self.pos_unter = Unterzeilen(self.pos_ansicht, lambda r: self.unter_texte.get(r, ()), artikel,
                                     lambda r: r < len(self.positionen) and self.zusatzarbeiten([r]), unter_an)
        self.pos_ansicht.verticalHeader().sectionClicked.connect(self._kopf_klick)
        self.pos_ansicht.verticalHeader().setToolTip("Klick auf ▾/▸ einer Schweißbaugruppe bzw. eines Satzes: "
                                                     "Einzelteile bzw. Positionen des Satzes zu- bzw. aufklappen. "
                                                     "Zeilenkopf ziehen: Position an eine andere Stelle "
                                                     "verschieben (auch Alt+↑/↓, Rechtsklick → Nach oben/unten)")
        # Reihenfolge per Drag & Drop am Zeilenkopf (Patrick 29.10.2026, reihenfolge.py)
        self.pos_ansicht.verticalHeader().setSectionsMovable(True)
        self.pos_ansicht.verticalHeader().sectionMoved.connect(self._kopf_gezogen)

        self.kalk = Liste(KALK_SPALTEN, max_stellen=2)
        self.stangen = Liste(STANGEN_SPALTEN)
        self.teile = Liste(TEIL_SPALTEN)
        self.ausw = Liste(AUSW_SPALTEN)
        self.fehler = Liste(FEHLER_SPALTEN)
        self.prot = Liste(PROT_SPALTEN)
        self.zukauf = Liste(ZUKAUF_SPALTEN)
        kalk_ansicht = self.kalk_ansicht = _tabelle(self.kalk)
        _breiten(kalk_ansicht, KALK_SPALTEN)
        self.summen = QLabel()
        self.summen.setWordWrap(True)
        self.summen.setObjectName("summenzeile")
        self.kalk_info = QLabel()
        self.kalk_info.setStyleSheet("color: #5F6B7A;")
        # Kompakte Übersicht (Vorgabe): das Wichtigste je Bauteil; 'Alle Spalten' zeigt die ganze Kalkulation
        self.kompakt = Liste(KOMPAKT_SPALTEN, max_stellen=2)
        self.kompakt_ansicht = _tabelle(self.kompakt)
        _breiten(self.kompakt_ansicht, KOMPAKT_SPALTEN)
        self.kompakt_ansicht.setItemDelegate(UnterzeilenDelegat(self.kompakt_ansicht))
        self.kompakt_unter = Unterzeilen(self.kompakt_ansicht, self._kompakt_unter_texte, 1, an=unter_an)
        self.kompakt_ansicht.setToolTip("Doppelklick: zur Position")
        self.kompakt_ansicht.doubleClicked.connect(self._kompakt_doppelklick)
        self.kalk_kompakt = QCheckBox("Kompakt")
        self.kalk_kompakt.setToolTip("Kompakt: Profil, Stückzahl, Länge, Material, Oberfläche, Laserzeit berechnet und "
                                     "genutzt, Verkaufspreis je Bauteil.\nOhne Häkchen: alle Spalten der Kalkulation.")
        self.kalk_kompakt.setChecked(self.db.einstellung(KOMPAKT_EINSTELLUNG) is not False)
        self.kalk_kompakt.toggled.connect(self._kompakt_umschalten)
        kalk_seite = QWidget()
        kl = QVBoxLayout(kalk_seite)
        kl.addWidget(self.summen)
        kz = QHBoxLayout()
        kz.addWidget(self.kalk_info, 1)
        self.unter_haken_kalk = self._unter_haken(unter_an)
        kz.addWidget(self.unter_haken_kalk)
        kz.addWidget(self.kalk_kompakt)
        kl.addLayout(kz)
        kl.addWidget(self.kompakt_ansicht, 1)
        kl.addWidget(kalk_ansicht, 1)
        self._kompakt_umschalten(self.kalk_kompakt.isChecked(), merken=False)
        self.stangen_ansicht = _tabelle(self.stangen, sortieren=False)
        _breiten(self.stangen_ansicht, STANGEN_SPALTEN)
        self.stangen_ansicht.selectionModel().currentRowChanged.connect(self._stange_gewaehlt)
        teile_ansicht = self.teile_ansicht = _tabelle(self.teile, sortieren=False)
        _breiten(teile_ansicht, TEIL_SPALTEN)
        plan = QSplitter(Qt.Vertical)
        plan_oben = QWidget()
        po = QVBoxLayout(plan_oben)
        po.setContentsMargins(0, 4, 0, 0)
        self.plan_info = QLabel()           # was für alle Stangen gleich ist, steht nur hier einmal
        self.plan_info.setWordWrap(True)
        po.addWidget(self.plan_info)
        po.addWidget(self.stangen_ansicht, 1)
        plan_unten = QWidget()
        pu = QVBoxLayout(plan_unten)
        pu.setContentsMargins(0, 4, 0, 0)
        self.teile_titel = QLabel()
        pu.addWidget(self.teile_titel)
        pu.addWidget(teile_ansicht, 1)
        plan.addWidget(plan_oben)
        plan.addWidget(plan_unten)
        # Stangenbild: Umschalter Stangenmuster / Übersicht / Detail (Lantek-Ideen L1, L2, L4)
        self.stangen_seite = StangenSeite(self.db.einstellung(STANGENBILD_EINSTELLUNG) or STANGEN_UEBERSICHT,
                                          lambda a: self.db.einstellung_setzen(STANGENBILD_EINSTELLUNG, a),
                                          lambda: self.db.einstellung("stangenbild_popup"))
        self.stangen_seite.doppelklick.connect(self.zur_position)
        self.bild = self.stangen_seite.bild
        teile_ansicht.setToolTip("Doppelklick auf ein Teil: zur Position")
        teile_ansicht.doubleClicked.connect(
            lambda i: self.zur_position(self.teile.zeilen[i.row()].get("ref")) if i.row() < len(self.teile.zeilen) else None)
        ausw_seite = QWidget()
        al = QVBoxLayout(ausw_seite)
        ausw_ansicht = _tabelle(self.ausw)
        _breiten(ausw_ansicht, AUSW_SPALTEN)
        fehler_ansicht = _tabelle(self.fehler)
        _breiten(fehler_ansicht, FEHLER_SPALTEN)
        al.addWidget(ausw_ansicht, 2)
        self.fehler_titel = QLabel()
        self.fehler_titel.setWordWrap(True)
        al.addWidget(self.fehler_titel)
        self.fehler_ansicht = fehler_ansicht
        al.addWidget(fehler_ansicht, 1)
        # Lieferlängen: Knopf nur bei einer sinnvollen Lösung, der Vergleich selbst groß im eigenen Fenster
        self.laengen_dialog = LaengenDialog(self)
        self.laengen_ansicht = self.laengen_dialog.ansicht
        lz = QHBoxLayout()
        self.laengen_knopf = QPushButton("12-m-Lösung ansehen …")
        self.laengen_knopf.setToolTip("Lieferlängen: 6 m gegen 12 m – Vergleich je Gruppe in einem großen Fenster")
        self.laengen_knopf.clicked.connect(lambda: self.laengen_zeigen())
        self.laengen_hinweis = QLabel()
        self.laengen_hinweis.setWordWrap(True)
        lz.addWidget(self.laengen_knopf)
        lz.addWidget(self.laengen_hinweis, 1)
        al.addLayout(lz)
        self.laengen_knopf.setVisible(False)
        self.laengen_hinweis.setVisible(False)
        zk_seite = QWidget()            # Zukaufteile: Bestellung je Artikel und Preisstand (ganzes Angebot)
        zl = QVBoxLayout(zk_seite)
        self.zukauf_info = QLabel()
        self.zukauf_info.setWordWrap(True)
        zl.addWidget(self.zukauf_info)
        self.zukauf_ansicht = _tabelle(self.zukauf)
        _breiten(self.zukauf_ansicht, ZUKAUF_SPALTEN)
        zl.addWidget(self.zukauf_ansicht, 1)
        prot_ansicht = _tabelle(self.prot)
        _breiten(prot_ansicht, PROT_SPALTEN)
        prot_ansicht.setToolTip("Doppelklick auf eine Zeile: zur Position")
        prot_ansicht.doubleClicked.connect(lambda i: self.protokoll_zur_position(prot_ansicht.model().mapToSource(i).row()))
        # Staffeln: Mengenstufen mit Werten je Stufe (Eingabe) und Kosten je Stufe (Ergebnis), siehe staffel_seite.py
        st_seite = StaffelSeite(self)
        self.staffel_modell, self.staffel_ansicht, self.staffel_info = st_seite.modell, st_seite.ansicht, st_seite.info

        self.reiter = AngebotReiter()
        self.schritte = Schrittanzeige()         # ① erfasst → ② optimiert → ③ geprüft → ④ verschickt (L10)
        self.reiter.setCornerWidget(self.schritte, Qt.TopRightCorner)
        self.pos_seite = QWidget()            # Positionsliste mit Spaltenauswahl darüber
        self.pos_leiste = QHBoxLayout()
        self.pos_leiste.setContentsMargins(0, 0, 0, 0)
        pl = QVBoxLayout(self.pos_seite)
        pl.setContentsMargins(0, 4, 0, 0)
        pl.setSpacing(4)
        pl.addLayout(self.pos_leiste)
        # Schnellzeile (Plan Bedienung B6): „QR 40x3 S235 1250 20“ + Eingabe legt die Position an
        self.schnell = SchnellFeld()
        self.schnell.setPlaceholderText("Schnellzeile: z. B. QR 40x3 S235 1250 20 (Profil, Werkstoff, Länge, Stück) – "
                                        "Eingabe legt die Position an, mehrere Zeilen einfügen geht auch")
        self.schnell.setToolTip("Profil, Werkstoff, Länge [mm] und Stückzahl in einer Zeile. Eindeutig mit L=1250, "
                                "1250mm, 20 Stk, x20; Artikelnummer mit #. Mehrere Zeilen (z. B. aus einer E-Mail "
                                "oder Excel) mit Strg+V einfügen: je Zeile eine Position.")
        self.schnell_vorschau = QLabel()
        self.schnell_vorschau.setStyleSheet("color: #5F6B7A;")
        self.schnell.textChanged.connect(self._schnell_vorschau)
        self.schnell.returnPressed.connect(lambda: self.schnellzeile())
        self.schnell.mehrzeilig.connect(lambda text: self.schnellzeile(text))
        sz = QHBoxLayout()
        sz.setContentsMargins(0, 0, 0, 0)
        sz.addWidget(self.schnell, 3)
        sz.addWidget(self.schnell_vorschau, 2)
        pl.addLayout(sz)
        pl.addWidget(self.pos_ansicht, 1)
        # leeres Angebot: großes Ablagefeld statt der leeren Positionsliste
        self.ablage_gross = AblageFeld(gross=True)
        self.ablage_gross.geklickt.connect(lambda: self.dateien_waehlen())
        pl.addWidget(self.ablage_gross, 1)
        self.reiter.addTab(self.pos_seite, "Positionen")
        self.kalk_seite = kalk_seite
        self.zeiten_seite = ZeitenSeite(self)
        self.reiter.gruppe("Kalkulation", [(kalk_seite, "Kalkulation"), (self.zeiten_seite, "Zeiten && Arbeitskosten")])
        self.reiter.addTab(zk_seite, "Zukaufteile")
        # Teilebaum mit Offen-Spalte und 3D-Vorschau links neben dem Schnittplan (Lantek-Idee L3)
        self.teile_baum = TeileBaum(self._vorschau_netz)
        self.teile_baum.gewaehlt.connect(self._baum_gewaehlt)
        self.teile_baum.doppelklick.connect(self.zur_position)
        plan_seite = QSplitter(Qt.Horizontal)
        plan_seite.addWidget(self.teile_baum)
        plan_seite.addWidget(plan)
        plan_seite.setStretchFactor(1, 1)
        plan_seite.setSizes([440, 860])
        self.reiter.gruppe("Schnittplan", [(plan_seite, "Schnittplan"), (self.stangen_seite, "Stangenbild"),
                                           (ausw_seite, "Auswertung")])
        self.reiter.addTab(st_seite, "Staffeln")
        self._nachkalk = NachkalkulationSeite(self)
        self.reiter.addTab(self._nachkalk, "Nachkalkulation")
        self.reiter.addTab(prot_ansicht, "STEP-Protokoll")
        self._st_seite = st_seite
        self.reiter.currentChanged.connect(lambda _: self._verdeckte_fuellen(self.reiter.currentWidget()))

        # Spaltenauswahl der Positionsliste (Zeile über der Liste, Reiter behalten die volle Breite)
        el = self.pos_leiste
        self.pos_info = QLabel()
        self.pos_info.setStyleSheet("color: #5F6B7A;")
        self.pos_info.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)     # schmales Fenster: Text gekürzt
        self.spalten_knopf = QPushButton("Weitere Spalten")
        self.spalten_knopf.setToolTip("Optionale Spalten der Positionsliste ein- oder ausblenden. Spalten mit Werten "
                                      "erscheinen automatisch.")
        self.spalten_menue = QMenu(self.spalten_knopf)
        self.spalten_menue.aboutToShow.connect(self._spalten_menue_fuellen)
        self.spalten_knopf.setMenu(self.spalten_menue)
        self.zeige_step = QCheckBox("STEP-Werte (aus CAD)")
        self.zeige_step.setToolTip("Aus dem importierten CAD-Modell (STEP) gemessene Werte: Anfangs- und Endschnitt, "
                                   "Innenkonturen, Gravur, Bohrungen, Konturgrößen.")
        self.zeige_berechnet = QCheckBox("Berechnete Werte (Programm)")
        self.zeige_berechnet.setToolTip("Vom Programm ermittelte Werte: Profilform, Gewicht, wirksame Stangenlänge, "
                                        "Vorschub, eingeplante Teile usw.")
        el.addWidget(self.pos_info, 1)
        self.unter_haken_pos = self._unter_haken(self.pos_unter.an)
        for w in (self.unter_haken_pos, self.spalten_knopf, self.zeige_step, self.zeige_berechnet):
            el.addWidget(w)
        for c in (self.zeige_berechnet, self.zeige_step):
            c.toggled.connect(self._spalten_zeigen)

        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addWidget(self.leiste)
        ul.addWidget(self.reiter, 1)
        self.teiler = QSplitter(Qt.Vertical)
        self.teiler.addWidget(oben_rahmen)
        self.teiler.addWidget(unten)
        self.teiler.setStretchFactor(0, 0)
        self.teiler.setStretchFactor(1, 1)
        self.teiler.setChildrenCollapsible(False)
        self.spalten = QSplitter(Qt.Horizontal)       # links Kopf und Reiter, rechts die Übersicht
        self.spalten.addWidget(self.teiler)
        self.spalten.addWidget(self.uebersicht_rahmen)
        self.spalten.setStretchFactor(0, 1)
        self.spalten.setStretchFactor(1, 0)
        self.spalten.setChildrenCollapsible(False)
        # Angebot eines Kollegen (teilen.py): Hinweis mit Kopieren, Eingaben gesperrt
        self.fremd_leiste = QFrame()
        self.fremd_leiste.setStyleSheet("QFrame { background: #FFF4D6; border: 1px solid #E8C66B; border-radius: 4px; }"
                                        "QLabel { border: none; }")
        fl = QHBoxLayout(self.fremd_leiste)
        fl.setContentsMargins(10, 6, 10, 6)
        self.fremd_text = QLabel()
        self.fremd_text.setWordWrap(True)
        fl.addWidget(self.fremd_text, 1)
        kopie = QPushButton("Als Kopie übernehmen")
        kopie.setToolTip("Eigene Kopie mit eigener Nummer und heutigem Datum anlegen und öffnen")
        kopie.clicked.connect(lambda: self.als_kopie())
        fl.addWidget(kopie)
        # Zusammenarbeit (Patrick 28.10.2026): Übernahme beim Bearbeiter anfragen, eigene Übergabe zurücknehmen
        self.anfrage_knopf = QPushButton("Übernahme anfragen …")
        self.anfrage_knopf.setToolTip("Den Bearbeiter fragen, ob er Ihnen das Angebot übergibt (er wird beim nächsten "
                                      "Abgleich gefragt)")
        self.anfrage_knopf.clicked.connect(lambda: self._anfragen())
        fl.addWidget(self.anfrage_knopf)
        self.zurueck_knopf = QPushButton("Übergabe zurücknehmen")
        self.zurueck_knopf.setToolTip("Das Angebot wieder selbst bearbeiten (nur solange der Kollege es noch nicht "
                                      "übernommen hat)")
        self.zurueck_knopf.clicked.connect(lambda: self._zuruecknehmen())
        fl.addWidget(self.zurueck_knopf)
        self.fremd_leiste.hide()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 4)
        lay.addWidget(self.fremd_leiste)
        lay.addWidget(self.spalten, 1)
        self.spalten_wahl = self.db.einstellung(SPALTEN_EINSTELLUNG) or {}
        self.neu_laden()
        self.funktionen_anwenden()

    def funktionen_anwenden(self):
        """Funktionen ein/aus (funktionen.py): Knöpfe Zukaufteile und Fracht berechnen, Reiter Nachkalkulation.
        Menüeinträge prüfen beim Öffnen selbst. Hat das Angebot schon Zukaufteile, bleibt der Knopf."""
        zukauf = funktionen.an("funktion_zukauf") or any(ist_zukaufteil(p) for p in getattr(self, "positionen", ()))
        self.zukauf_knopf.setVisible(zukauf)
        self.kopf_bereich.fracht_knopf.setVisible(funktionen.an("funktion_fracht"))
        self.reiter.setTabVisible(self.reiter.indexOf(self._nachkalk), funktionen.an("funktion_nachkalkulation"))

    # -------------------------------------------------------------- Laden und Rechnen
    def titel(self):
        nr = self.kopf.get("nummer") or ""
        return (f"Angebot {nr}" + (" (vorläufige Nummer)" if angebotsnummern.vorlaeufig(nr) else "")
                + (f" ({self.kopf['fremd']})" if self.kopf.get("fremd") else ""))

    def nummer_endgueltig(self, wofuer):
        """Vor Angebots-PDF und Materialanfrage: eine vorläufige Nummer (Ordner war beim Anlegen nicht erreichbar) jetzt
        im gemeinsamen Ordner endgültig vergeben. False = Ordner weiter nicht erreichbar (Meldung)."""
        if self.fremd() or not angebotsnummern.vorlaeufig(self.kopf.get("nummer")):
            return True
        try:
            umn = angebotsnummern.endgueltig(self.db, self.id)
        except OSError:
            text = (f"{wofuer} erst mit endgültiger Angebotsnummer: der gemeinsame Ordner ist nicht erreichbar. "
                    "Die Nummer kommt beim nächsten Abgleich.")
            if self.f.stumm:
                self.f.meldung(text, fehler=True)
            else:
                QMessageBox.warning(self, wofuer, text)
            return False
        self.neu_laden()
        self.f.angebote.neu_laden()
        if umn:
            self.f.meldung(f"Angebotsnummer {umn[0][0]} → {umn[0][1]} (endgültig).")
        return True

    def fremd(self):
        """Kürzel des Kollegen, wenn das Angebot einem anderen Mitarbeiter gehört (nur ansehen), sonst None."""
        return (self.kopf or {}).get("fremd") or None

    def _fremd_anzeigen(self):
        k = self.fremd()
        lesen = bool(self.db.nur_lesen)            # Lizenz: Lesemodus wie ein fremdes Angebot, nur ansehen
        self.fremd_leiste.setVisible(bool(k) or lesen)
        self.kopf_bereich.setEnabled(not k and not lesen)
        self.schnell.setEnabled(not k and not lesen)
        self.leiste.links.setEnabled(not k)          # Lesemodus: Knöpfe einzeln (3D-Ansicht bleibt)
        self.setAcceptDrops(not k and not lesen)
        if lesen and not k:
            self.fremd_text.setText(f"<b>Lesemodus</b> – {self.db.nur_lesen}. Das Angebot lässt sich ansehen, aber "
                                    "nicht ändern (Hilfe → Lizenz …).")
        nr = (self.kopf or {}).get("nummer")
        uebergabe = teilen.vorgang_offen(self.db, nr, teilen.UEBERGABE) if k else None
        anfrage = teilen.vorgang_offen(self.db, nr, teilen.ANFRAGE) if k else None
        self.zurueck_knopf.setVisible(bool(uebergabe) and not lesen)
        self.anfrage_knopf.setVisible(bool(k) and not uebergabe and not lesen and teilen.aktiv(self.db))
        self.anfrage_knopf.setEnabled(not anfrage)
        self.anfrage_knopf.setText("Übernahme angefragt" if anfrage else "Übernahme anfragen …")
        if k:
            m = teilen.mitarbeiter(self.db, k)
            wer = f"{m.get('name')} ({k})" if m.get("name") else k
            if uebergabe:
                self.fremd_text.setText(f"<b>An {wer} übergeben</b> – {k} übernimmt das Angebot beim nächsten Abgleich. "
                                        "Bis dahin lässt sich die Übergabe zurücknehmen.")
                return
            offen = teilen.offen_bei(self.db, nr)
            jetzt = (f" <b>{k} hat es gerade geöffnet</b> (seit {str(offen[1])[11:16] or offen[1]})."
                     if offen else "")
            self.fremd_text.setText(f"<b>Angebot von {wer}</b> – nur zum Ansehen (Stand des letzten Abgleichs).{jetzt} "
                                    "Ändern kann es nur der Bearbeiter; zum Weiterarbeiten als eigene Kopie übernehmen "
                                    "oder die Übernahme anfragen.")

    def _anfragen(self, notiz=None):
        from . import teilen_fenster
        return teilen_fenster.anfragen(self.f, self.id, notiz)

    def _zuruecknehmen(self):
        from . import teilen_fenster
        return teilen_fenster.zuruecknehmen(self.f, self.id)

    def als_kopie(self):
        """Fremdes (oder eigenes) Angebot kopieren: eigene Nummer, öffnet die Kopie."""
        neu = self.db.angebot_kopieren(self.id)
        self.f.angebote.neu_laden()
        self.f.angebot_oeffnen(neu)
        self.f.meldung(f"Kopie {self.db.angebot(neu)['nummer']} von Angebot {self.kopf.get('nummer')} angelegt.")
        return neu

    def neu_laden(self, *_):
        # Kalkulation nur einmal je Neuladen rechnen (Übersicht, Staffeln, Nachkalkulation; Performance-Audit 22.10.2026)
        self._kalk_merken = {}
        try:
            self._neu_laden()
            self._auto_planen()          # nutzt den eben geprüften Optimierungsstand mit (Plan C2)
            self._st_seite.planen()      # angelegte Staffeln nach Änderungen selbst neu rechnen (28.10.2026)
        finally:
            self._kalk_merken = None

    # Plan Arbeitsabläufe W1: kurz nach einer Änderung selbst optimieren (nur Entwürfe, kleine Angebote, eigene)
    AUTO_PAUSE_MS = 800
    AUTO_BIS_TEILEN = 500       # darüber dauert es spürbar (1.500 Teile ≈ 1,3 s): dann weiter F9 bzw. Knopf;
                                # ab HINTERGRUND_AB_TEILEN rechnet auch das automatische Optimieren im Hintergrund

    def auto_optimieren_moeglich(self):
        """True, wenn das Angebot jetzt automatisch optimiert werden soll: Optimierung nicht aktuell, Entwurf, eigenes
        Angebot ohne Lesemodus, 1 … Einstellung 'auto_optimieren_bis' aktive Positionen, weniger als AUTO_BIS_TEILEN
        Teile, und nicht schon mit genau diesen Eingaben gescheitert."""
        grenze = self.db.einstellung("auto_optimieren_bis") or 0
        aktiv = [p for p in self.positionen if position_aktiv(p)]
        if not grenze or not aktiv or len(aktiv) > grenze or self.fremd() or self.db.nur_lesen:
            return False
        if (self.kopf.get("vorgang") or "Entwurf") != "Entwurf":
            return False        # verschickte Angebote behalten ihren Schnittplan, bis jemand von Hand optimiert
        if sum(int(rechnen._n(p.get("stueck"))) for p in aktiv) >= self.AUTO_BIS_TEILEN:
            return False
        if self.stand_optimierung() == "aktuell":
            return False
        return self._eingabe_kennung() != getattr(self, "_auto_fehlgeschlagen", None)

    def _auto_planen(self):
        if not hasattr(self, "_auto_timer"):
            self._auto_timer = QTimer(self)
            self._auto_timer.setSingleShot(True)
            self._auto_timer.timeout.connect(self.auto_optimieren)
        if self.auto_optimieren_moeglich():
            self._auto_timer.start(self.AUTO_PAUSE_MS)      # jede weitere Änderung schiebt den Lauf hinaus
            self.uebersicht_bereich.wird_berechnet()        # V7: kein vorläufiger Preis ohne Material
        else:
            self._auto_timer.stop()

    def auto_optimieren(self):
        """Automatisch optimieren (W1), ohne Meldungsfenster. Ergebnis: True = optimiert, False = nicht nötig oder
        gescheitert (Grund in der Statuszeile, gleiche Eingaben werden nicht erneut versucht)."""
        # Dialog offen oder Zelle in Bearbeitung (Neuladen würde den Editor schließen): danach erneut versuchen
        if QApplication.activeModalWidget() is not None or \
                self.pos_ansicht.state() == QAbstractItemView.EditingState:
            self._auto_timer.start(self.AUTO_PAUSE_MS)
            return False
        if not self.auto_optimieren_moeglich():
            return False
        kennung = rechnen.eingabe_kennung(self.kopf, self.positionen, self.k, self.tabellen, self.einst)
        ok = self.optimieren(automatisch=True)
        if not ok:
            self._auto_fehlgeschlagen = kennung
        return ok

    def _neu_laden(self):
        a = self.db.angebot(self.id)
        if a is None:
            return
        if not self.db.nur_lesen and self.db.fracht_auto_nachfuehren(self.id):      # Haken 'Fracht automatisch berechnen': nach jeder Änderung
            a = self.db.angebot(self.id)
        self.kopf = a
        self._fremd_anzeigen()
        self.ergebnis = a["ergebnis"]
        self.positionen = self.db.positionen(self.id)
        if not self.db.nur_lesen:
            self._baugruppen_abgleichen()
        # festgeschriebene Materialpreise und Schneiddaten gehen den aktuellen Stammdaten vor
        self.k_aktuell, self.tabellen_aktuell = self.db.kontext(), self.db.tabellen()
        self.k, self.tabellen = rechnen.preisbasis_anwenden(a, self.k_aktuell, self.tabellen_aktuell)
        self._konturen_einteilen()
        # mit Werten des Angebots; nach dem Angebots-PDF mit den festgeschriebenen Einstellungen (Zuschläge, Mindestpreis …)
        self.einst = rechnen.einstellungen_angebot(a, rechnen.einstellungen_fest(self.tabellen, self.db.einstellungen()))
        self.stufen = self.db.staffeln(self.id)
        self.stufen_daten = self.db.staffel_stufen(self.id)
        self.blech_daten = self.db.blech_daten()        # Richtpreis der Blechteile je Staffelstufe
        self._kopf_anzeigen()
        self.pos_modell.rechnen()
        self._gruppieren()
        leer = not self.positionen
        self.ablage_gross.setVisible(leer)
        self.pos_ansicht.setVisible(not leer)
        self._spalten_zeigen()
        self._ergebnisse_anzeigen()
        self.f.reiter_titel(self)
        self.verlauf.merken()

    def _gruppieren(self):
        """Positionsliste gruppiert (D3): Einzelteile direkt unter ihrer Schweißbaugruppe (nur die Anzeige; die
        Zeilennummern im Modell bleiben), Klick auf den Zeilenkopf der Baugruppe klappt die Teile zu bzw. auf."""
        folge, zu = baugruppe.gruppen_reihenfolge(self.positionen)
        # Sätze (27.10.2026): Positionen eines Satzes zusammen, Klammer am Zeilenkopf, zuklappbar
        aus = set(zu) | {i for i, _ in baugruppe.baugruppen(self.positionen).values()}
        saetze = satzgruppen.saetze(self.positionen, aus)
        folge = satzgruppen.ordnen(folge, saetze)
        self.satz_zeilen = {ix[0]: n for n, ix in saetze.items() if len(ix) > 1}
        self.satz_zu &= set(self.satz_zeilen.values())
        self.pos_modell.satz, self.pos_modell.satz_zu = satzgruppen.info(self.positionen, saetze), self.satz_zu
        kopf = self.pos_ansicht.verticalHeader()
        self._kopf_ordnet = True        # eigenes Umsortieren ist kein Drag & Drop (_kopf_gezogen)
        try:
            for v, logisch in enumerate(folge):
                if kopf.visualIndex(logisch) != v:
                    kopf.moveSection(kopf.visualIndex(logisch), v)
        finally:
            self._kopf_ordnet = False
        self.bg_zeilen = {i: bg_id for bg_id, (i, _) in baugruppe.baugruppen(self.positionen).items()} if zu else {}
        self.bg_zu &= set(self.bg_zeilen.values())
        texte = {i: ("▸ " if b in self.bg_zu else "▾ ") + str(i + 1) for i, b in self.bg_zeilen.items()}
        texte.update({j: "└ " + str(j + 1) for j in zu})
        texte.update(satzgruppen.kopf_texte(saetze, self.satz_zu))
        self.pos_modell.kopf_text = texte
        satz_zu = {i for n in self.satz_zu for i in saetze[n][1:]}
        for r in range(len(self.positionen)):
            self.pos_ansicht.setRowHidden(r, zu.get(r) in self.bg_zu or r in satz_zu)
        if self.positionen:
            self.pos_modell.headerDataChanged.emit(Qt.Vertical, 0, len(self.positionen) - 1)
            self.pos_modell.dataChanged.emit(self.pos_modell.index(0, 0),
                                             self.pos_modell.index(len(self.positionen) - 1,
                                                                   len(self.pos_modell.spalten) - 1))

    def _kopf_klick(self, zeile):
        """Zeilenkopf einer Schweißbaugruppe: ihre Einzelteile zu- bzw. aufklappen (D3)."""
        bg_id = getattr(self, "bg_zeilen", {}).get(zeile)
        satz = getattr(self, "satz_zeilen", {}).get(zeile)
        if bg_id:
            self.bg_zu ^= {bg_id}
            self._gruppieren()
        elif satz:
            self.satz_zu ^= {satz}
            self._gruppieren()

    def _baugruppen_abgleichen(self):
        """Satz, Stück je Satz und Stückzahl der Schweißbaugruppen und ihrer Teile folgen der Struktur
        (baugruppe.abgleich), z. B. nach geänderter Anzahl Baugruppen. Ohne Baugruppen ändert sich nichts."""
        aenderungen = baugruppe.abgleich(self.positionen)
        for i, feld, wert in aenderungen:
            self.db.position_aendern(self.positionen[i]["id"], feld, wert)
        if aenderungen:
            self.positionen = self.db.positionen(self.id)
            self.f.meldung(f"Stückzahlen von {len({i for i, _, _ in aenderungen})} Position(en) an die "
                           "Schweißbaugruppe angepasst.")

    def _konturen_einteilen(self):
        """Konturklassen neu einteilen, wenn die Regel (Grenzen und Faktoren der Maschine, Wandstärke des Profils) nicht
        die ist, mit der die Konturliste der Position eingeteilt wurde (andere Maschine oder anderes Profil gewählt,
        Grenzen in den Stammdaten geändert)."""
        m = rechnen.maschine(self.kopf, self.k)
        if m is None:
            return
        neu = [(p, z) for p in self.positionen
               if (z := rechnen.konturklassen_neu(p, m, rechnen.wand_position(p, self.k)))]
        for p, z in neu:
            for feld, wert in z.items():
                self.db.position_aendern(p["id"], feld, wert)
        if neu:
            self.positionen = self.db.positionen(self.id)
            self.f.meldung(f"Konturklassen von {len(neu)} Position(en) mit den Grenzen der Maschine "
                           f"{self.kopf.get('maschine')} ({neu[0][1]['kontur_grenzen']}) neu eingeteilt.")

    def _kopf_anzeigen(self):
        self._laden = True
        try:
            self.kopf_bereich.anzeigen()
            self.kopf_bereich.kopf_aufklappen(not self.kopf_bereich.kopf_ausgefuellt(), automatisch=True)
        finally:
            self._laden = False

    def resizeEvent(self, ereignis):
        super().resizeEvent(ereignis)
        self.kopf_bereich.breite_anpassen(ereignis.size().width(), ereignis.size().height())

    def showEvent(self, ereignis):
        super().showEvent(ereignis)
        if not getattr(self, "_teiler_gesetzt", False):
            self._teiler_gesetzt = True
            b = self.spalten.width()
            rechts = UEBERSICHT_BREIT if b >= 1700 else UEBERSICHT_MIN
            self.spalten.setSizes([max(b - rechts, 400), rechts])
            if self.teiler.height() < 700 and self.db.einstellung(KALK_OFFEN_EINSTELLUNG) is None:   # kleiner Bildschirm
                self.kopf_bereich.kalkulation_aufklappen(False)
            self._oben_anpassen_jetzt()

    def oben_anpassen(self):
        """Oberen Teil (Kopf, Kalkulation, Fracht) so hoch wie nötig, höchstens gut die Hälfte; nach dem Auf- oder
        Zuklappen des Angebotskopfs."""
        if getattr(self, "_teiler_gesetzt", False):
            QTimer.singleShot(0, self, self._oben_anpassen_jetzt)      # erst nach dem Layout des Auf- oder Zuklappens

    def _oben_anpassen_jetzt(self):
        h = self.teiler.height()
        self.kopf_bereich.adjustSize()
        oben = min(self.kopf_bereich.sizeHint().height() + 6, int(h * 0.55))
        self.teiler.setSizes([oben, max(h - oben, 200)])

    def _kopf_speichern(self, fd, wert):
        if self._laden or wert == self.kopf.get(fd.name):
            return
        vorher = self._verkauf() if fd.name in KALK_NAMEN or fd.name == "mindestpreis_anwenden" else None
        try:
            self.db.angebot_aendern(self.id, fd.name, wert)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            self._kopf_anzeigen()
            return
        meldung = f"{fd.titel} gespeichert."
        a = self.db.angebot(self.id) or {}
        if fd.name.startswith("lieferzeit") and a.get("lieferzeit_art") == "Lieferdatum" and a.get("lieferzeit_wert") \
                and a["lieferzeit_wert"] < (a.get("datum") or ""):
            meldung += " Achtung: Das Lieferdatum liegt vor dem Angebotsdatum."
        self.neu_laden()
        if vorher is not None:          # Kalkulationswert: was sich am Preis ändert, in der Statuszeile
            meldung += f" {preis_aenderung(vorher, self._verkauf())}"
        self.f.meldung(meldung)

    def termin_pruefen(self, antwort=None):
        """Knopf „Termin prüfen …“ (Vorschlag V2, terminplan.py): frühester Liefertermin nach Maschinenauslastung und
        Material-Lieferzeit; „Als Lieferzeit übernehmen“ setzt die Lieferzeit auf diese Kalenderwoche. antwort: True =
        übernehmen, False = nur ansehen (Tests ohne Fenster). Ergebnis: terminplan.Termin oder None."""
        from . import auftrag, terminplan
        from .stammdaten import KALENDERWOCHE
        if not self.ergebnis:
            self.f.meldung("Termin prüfen: bitte zuerst optimieren (die Laserzeit kommt aus dem Schnittplan).",
                           fehler=True)
            return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            t = terminplan.fruehester(self.db, self.id)
        finally:
            QApplication.restoreOverrideCursor()
        zugesagt = auftrag.termin_vorschlag(self.kopf) if self.kopf.get("lieferzeit_art") and \
            self.kopf.get("lieferzeit_wert") or self.kopf.get("liefertermin") else None
        text = terminplan.text(t, zugesagt)
        if t is None or t.datum is None:
            self.f.meldung(text, fehler=t is None)
            return t
        if antwort is None and not self.f.stumm:
            box = QMessageBox(QMessageBox.Information, "Liefertermin nach Auslastung", text, parent=self)
            ja = box.addButton(f"Als Lieferzeit übernehmen (KW {t.datum.isocalendar()[1]})", QMessageBox.AcceptRole)
            box.addButton("Schließen", QMessageBox.RejectRole)
            box.exec()
            antwort = box.clickedButton() is ja
        if antwort:
            self.db.angebot_aendern(self.id, "lieferzeit_art", KALENDERWOCHE)
            self.db.angebot_aendern(self.id, "lieferzeit_wert", terminplan.kw_wert(t.datum))
            self.neu_laden()
            self.f.meldung(f"Lieferzeit auf KW {terminplan.kw_wert(t.datum)} gesetzt. {text}")
        else:
            self.f.meldung(text)
        return t

    def abruf_bearbeiten(self, werte=None):
        """Fenster „Abruf-/Rahmenangebot“ (abruf_dialog); werte = Kopffelder ohne Fenster übernehmen (Tests).
        Ergebnis: True, wenn gespeichert."""
        from .abruf_dialog import AbrufDialog
        if werte is None:
            stueck = max((rechnen._n(p.get("stueck")) for p in self.positionen if position_aktiv(p)), default=0)
            d = AbrufDialog(self, self.kopf, self.db.einstellungen(), stueck=stueck or None)
            if self.f.stumm or not d.exec():
                self._kopf_anzeigen()
                return False
            werte = d.werte()
        vorher = self._verkauf()
        try:
            for n, w in werte.items():
                if w != self.kopf.get(n):
                    self.db.angebot_aendern(self.id, n, w)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            self._kopf_anzeigen()
            return False
        self.neu_laden()
        self.f.meldung("Abruf-/Rahmenangebot gespeichert. " + (preis_aenderung(vorher, self._verkauf())
                                                                 if vorher is not None else ""))
        return True

    def abruf_umschalten(self, an):
        """Haken „Abruf-/Rahmenangebot“: an ohne Jahres-/Abrufmenge öffnet das Fenster, aus behält die Werte."""
        from . import abruf
        if an and not abruf.daten(dict(self.kopf, abruf="ja")):
            return self.abruf_bearbeiten()
        return self.abruf_bearbeiten({"abruf": "ja" if an else None})

    def _verkauf(self):
        """Verkaufspreis netto des Angebots mit den gespeicherten Werten (None ohne Positionen)."""
        if not any(position_aktiv(p) for p in self.positionen):
            return None
        return self._rechnung()[1]["verkauf"]

    def material_fuer_alle(self, herkunft):
        """Material (Eigenmaterial / Kunde beigestellt) für alle Rohrlaserteil-Positionen setzen."""
        n = 0
        for p in self.positionen:
            if not kein_laserteil(p) and (p.get("material_herkunft") or EIGENMATERIAL) != herkunft:
                self.db.position_aendern(p["id"], "material_herkunft", herkunft)
                n += 1
        self.neu_laden()
        self.f.meldung(f"Material „{herkunft}“ für {n} Position(en) gesetzt." if n else
                       f"Alle Positionen haben schon „{herkunft}“.")
        return n

    def kalkulation_zuruecksetzen(self):
        """Kalkulationswerte, Stundensätze und Zeitvorgaben des Angebots auf die Einstellungen setzen; die Rückfrage
        nennt, was sich ändert."""
        kalk, zeiten = self.kopf_bereich.abweichungen()
        if not kalk and not zeiten:
            self.f.meldung("Alle Kalkulationswerte, Stundensätze und Zeitvorgaben entsprechen den Einstellungen.")
            return False
        liste = [f"{f.titel.split('[')[0].strip()}: {zahl_als_text(w, f.stellen)} → {zahl_als_text(std, f.stellen)}"
                 for f, w, std in kalk] + zeiten
        # ohne Rückfrage, mit „Rückgängig“; die Liste der Werte steht im Bericht (Plan Bedienung B2)
        vorher = self._verkauf()
        self.db.kalkulation_zuruecksetzen(self.id)
        self.neu_laden()
        self.rueckgaengig_anbieten(
            f"{len(liste)} Werte aus den Einstellungen übernommen. {preis_aenderung(vorher, self._verkauf())}",
            bericht=("Kalkulation", "\n".join(liste) + "\n\nVon Hand eingetragene Werte an den Positionen "
                     "(Meterpreis, Schneidzeit, Zukaufteile) bleiben."))
        return True

    def stangenwechsel_setzen(self, sekunden):
        """Stangenwechsel je Stange (ohne feste Schweißnaht) nur für dieses Angebot ändern: im Snapshot der
        Zeitvorgaben (kopf['zeitbasis']); der Stangenwechsel SN bleibt. Ergebnis: True, wenn geändert."""
        if self._laden:
            return False
        zb = self.kopf.get("zeitbasis")
        zb = copy.deepcopy(zb) if isinstance(zb, dict) else self.db.zeitbasis_vorgabe(self.kopf.get("maschine"))
        m = zb.get("maschine") or {}
        if m.get("maschinen_id") != self.kopf.get("maschine"):
            m = self.db.zeitbasis_vorgabe(self.kopf.get("maschine"))["maschine"]
        if rechnen._n(m.get("stangenwechsel")) == sekunden:
            return False
        if m.get("stangenwechsel_sn") is None:      # Snapshot vor 0.8.10: SN behält den bisherigen Wert
            m["stangenwechsel_sn"] = m.get("stangenwechsel")
        m["stangenwechsel"] = sekunden
        zb["maschine"] = m
        vorher = self._verkauf()
        self.db.zeitbasis_speichern(self.id, zb)
        self.neu_laden()
        self.f.meldung(f"Stangenwechsel je Stange {sekunden} s für dieses Angebot gespeichert. "
                       f"{preis_aenderung(vorher, self._verkauf())}")
        return True

    def fracht_berechnen(self):
        """Dialog 'Fracht berechnen' (fracht_seite.FrachtDialog); im stummen Betrieb (Tests) nur anlegen."""
        from .fracht_seite import FrachtDialog
        d = FrachtDialog(self)
        if not self.f.stumm:
            d.exec()
        return d

    def fracht_auto_setzen(self, an):
        """Haken 'Fracht automatisch berechnen': an = Ziel-PLZ (leer: aus dem Kunden) und Tarifkopie festhalten."""
        if self._laden or an == fracht_angebot.auto(self.kopf):
            return
        if an:
            if not self.kopf.get("fracht_plz"):
                plz, land = fracht_angebot.ziel_aus_kunde(self.db.kunde(self.kopf.get("kundennr")))
                self.db.angebot_aendern(self.id, "fracht_plz", plz or None)
                self.db.angebot_aendern(self.id, "fracht_land", land)
            self.db.angebot_aendern(self.id, "fracht_auto", "ja")
            self._fracht_auto_rechnen()
        else:
            self.db.angebot_aendern(self.id, "fracht_auto", None)
            self.f.meldung("Fracht wird nicht mehr automatisch berechnet (letzter Betrag bleibt).")
        self.neu_laden()

    def fracht_ziel_setzen(self, plz, land):
        """Ziel-PLZ und Land der automatischen Fracht ändern (neue Zone und Tarifkopie)."""
        plz = "".join(str(plz or "").split()).upper() or None
        land = (land or "").strip().upper() or "DE"
        if self._laden or (plz == self.kopf.get("fracht_plz") and land == (self.kopf.get("fracht_land") or "DE")):
            return
        self.db.angebot_aendern(self.id, "fracht_plz", plz)
        self.db.angebot_aendern(self.id, "fracht_land", land)
        if fracht_angebot.auto(self.kopf):
            self._fracht_auto_rechnen()
        self.neu_laden()

    def _fracht_auto_rechnen(self):
        d = self.db.fracht_auto_aktualisieren(self.id)
        if d.get("fehler"):
            self.f.meldung("Fracht nicht berechnet: " + d["fehler"], fehler=True)
        else:
            self.f.meldung(f"Fracht automatisch berechnet: {d.get('text')}.")

    def kunde_waehlen(self, kundennr):
        """Kundennummer übernehmen; steht der Kunde im Kundenstamm, auch Name und Zahlungsbedingungen."""
        kundennr = (kundennr or "").strip() or None
        if self._laden or kundennr == self.kopf.get("kundennr"):
            return
        k = self.db.kunde_uebernehmen(self.id, kundennr)
        vorgaben = (k or {}).get("vorgaben")
        self.f.meldung(f"Kunde {k['name']} übernommen (Name und Zahlungsbedingungen"
                       + (f"; Kundenvorgaben: {', '.join(vorgaben)}" if vorgaben else "") + ")." if k
                       else "Kundennummer gespeichert (nicht im Kundenstamm).")
        if k and fracht_angebot.auto(self.kopf):     # automatische Fracht: Ziel des neuen Kunden
            plz, land = fracht_angebot.ziel_aus_kunde(k)
            if plz:
                self.db.angebot_aendern(self.id, "fracht_plz", plz)
                self.db.angebot_aendern(self.id, "fracht_land", land)
            self._fracht_auto_rechnen()
        self.neu_laden()

    def kunde_zeigen(self):
        """Doppelklick auf Kunde im Angebotskopf: Kunden des Angebots im Reiter Kunden zeigen."""
        return self.f.kunde_zeigen(self.kopf.get("kundennr"), self.kopf.get("kunde"))

    def stand_optimierung(self):
        if not self.ergebnis:
            return "noch nicht optimiert"
        aktuell = self._eingabe_kennung() == self.ergebnis.get("kennung")
        return "aktuell" if aktuell else "VERALTET – Angebot oder Stammdaten geändert, bitte neu optimieren"

    def _eingabe_kennung(self):
        """rechnen.eingabe_kennung der jetzigen Eingaben; während neu_laden nur einmal gerechnet (Plan C2)."""
        merken = getattr(self, "_kalk_merken", None)
        if merken is None:
            return rechnen.eingabe_kennung(self.kopf, self.positionen, self.k, self.tabellen, self.einst)
        if "kennung" not in merken:
            merken["kennung"] = rechnen.eingabe_kennung(self.kopf, self.positionen, self.k, self.tabellen, self.einst)
        return merken["kennung"]

    def freigabe_punkte(self, summen=None, zeilen=None, preis_abweichung=None):
        """Angebots-Check (Plan A2): alle offenen Punkte vor dem Angebots-PDF (rechnen.freigabe_punkte)."""
        if summen is None or zeilen is None:
            zeilen, summen = self._rechnung()
        try:
            veraltet = self._st_seite.anzahl_veraltet() if self.stufen else 0     # ohne Füllen (P9)
        except (ValueError, TypeError, KeyError):
            veraltet = 0
        if preis_abweichung is None:
            preis_abweichung = rechnen.preisbasis_abweichung(self.kopf, self.k_aktuell, self.tabellen_aktuell)
        kundennr = self.kopf.get("kundennr")
        return rechnen.freigabe_punkte(
            self.kopf, self.positionen, self.pos_modell.status, self.stand_optimierung(), summen, veraltet,
            gueltig_bis(self.kopf, self.db.einstellung("gueltigkeit")), kalk_zeilen=zeilen,
            kunde=(self.db.kunde(kundennr) or {}) if kundennr else None, preis_abweichung=preis_abweichung,
            mindestmarge=self.db.einstellung("mindestmarge") or 0,
            admin=bool(getattr(self.f, "bereich", None) and self.f.bereich.admin),
            laser_hinweise=rechnen.laser_hinweise(self.positionen, self.k)
            + rechnen.teuerung_hinweise(self.positionen, self.k),
            staffel_widersprueche=self._staffel_widersprueche(zeilen),
            plausibel=plausibel.punkte(self.positionen, zeilen, summen, self.k, self._preis_vergleich()))

    def _preis_vergleich(self):
        """€/kg je Abmessung aus früher verschickten Angeboten (Plan C3), einmal je geöffnetem Angebot gelesen."""
        if getattr(self, "_preis_vergleich_cache", None) is None:
            try:
                self._preis_vergleich_cache = plausibel.vergleich_aus(self.db.versand_verlaeufe(self.id))
            except Exception:       # Plausibilität ist nur ein Hinweis: nie das Angebot blockieren
                self._preis_vergleich_cache = {}
        return self._preis_vergleich_cache

    def _staffel_widersprueche(self, kalk_zeilen):
        """Staffelpreise (letzter gespeicherter Stand), die im Angebots-PDF dem Preis der Zeile widersprechen
        (ausgabe.staffel_widersprueche); ohne Stufen nichts."""
        sp = (self.kopf.get("staffelpreise") or {}).get("zeilen")
        if not self.stufen or not sp:
            return []
        try:
            return ausgabe.staffel_widersprueche(ausgabe.angebot(self.kopf, self.positionen, kalk_zeilen, self.k,
                                                                 self.einst, sp, ergebnis=self.ergebnis))
        except (ValueError, TypeError, KeyError, ZeroDivisionError):     # unvollständiges Angebot: ohne Prüfung
            return []

    def check_link(self, ziel):
        """„Hinspringen“ aus dem Angebots-Check (Übersicht oder Fenster); ziel wie angebot_check (ohne 'check:')."""
        art, _, wert = ziel.removeprefix("check:").partition(":")
        self.f.reiter.setCurrentWidget(self)
        if art == "pos":
            return self.zur_position(zeile=int(wert))
        if art == "kopf":
            return self.kopf_bereich.feld_zeigen(wert)
        if art == "kunde":
            return self.kunde_zeigen()
        if art == "fracht":
            return self.kopf_bereich.feld_zeigen("fracht_modus")
        if art == "optimieren":
            return self.optimieren()
        if art == "staffeln":
            return self.reiter.setCurrentWidget(self.st_seite)
        if art == "preise":
            return self.preise_aktualisieren()
        if art == "kalkulation":
            return self.reiter.setCurrentWidget(self.kalk_seite)
        if art == "bohrungen":
            return self.bohrungen_alle_pruefen()
        return None

    def vor_verschickt(self):
        """Angebots-Check vor dem Vorgang „Verschickt“ ohne PDF. Wurde ein FEHLER oder eine WARNUNG übergangen, steht das
        mit Begründung im Versandverlauf. Ergebnis: True = Vorgang setzen."""
        punkte = self.freigabe_punkte()
        if not angebot_check.offen(punkte):
            return True
        ok, begruendung = self.check_zeigen("Als verschickt markieren", punkte)
        if ok:
            self.db.versand_merken(self.id, dict(datum=datetime.date.today().isoformat(), netto=None, datei=None,
                                                 check=angebot_check.versand_eintrag(punkte, begruendung)))
        return ok

    def check_zeigen(self, weiter=None, punkte=None):
        """Fenster Angebots-Check; weiter = Text des Weiter-Knopfs (None = nur ansehen). Ergebnis: (weiter ja/nein,
        Begründung). „Hinspringen“ springt nach dem Schließen zur Stelle und zählt als Abbrechen."""
        from .angebot_check_dialog import CheckDialog
        d = CheckDialog(self, self.freigabe_punkte() if punkte is None else punkte, weiter)
        ok = d.exec() == QDialog.Accepted
        if d.ziel:
            self.check_link(d.ziel)
        return ok, d.text_begruendung()

    def _schritte_setzen(self):
        """Schrittanzeige; „Verschickt“ erst mit CSV-Export im Versandverlauf (Patrick 24.10.2026)."""
        csv = any(isinstance(e, dict) and e.get("art") == "csv" for e in self.kopf.get("versand") or ())
        self.schritte.setzen(schritte.erledigt(self.positionen, self.stand_optimierung(),
                                               angebot_check.offen(getattr(self, "_punkte", [])), vorgang(self.kopf),
                                               csv))

    def _ergebnisse_anzeigen(self):
        self.uebersicht_bereich.stand_setzen(self.stand_optimierung())
        erg = self.ergebnis
        zeilen, summen = self._rechnung()
        preis_abw = rechnen.preisbasis_abweichung(self.kopf, self.k_aktuell, self.tabellen_aktuell)
        self.uebersicht_bereich.preisstand_setzen(
            self.kopf.get("preisbasis"), preis_abw,
            rechnen.verschickt_abweichung(self.kopf.get("preisbasis"), summen.get("verkauf")),
            self.kopf.get("versand"))
        markiert = satzgruppen.zeilen_markieren(self.positionen, zeilen)      # Sätze getönt (27.10.2026)
        self.kalk.setzen([z for z in markiert if z])
        stat = self.pos_modell.status
        teile = sum(p.get("stueck") or 0 for p in self.positionen)
        gewicht = sum(w["gewicht_position"] or 0 for w in self.pos_modell.werte)
        self.uebersicht_bereich.kennzahlen_setzen(dict(
            positionen=str(sum(1 for s in stat if s)), stueck=f"{_z(teile, 0)} Stk",
            gewicht=f"{_z(gewicht)} kg"))
        self.uebersicht_bereich.meldungen_setzen(
            [(p.get("pos"), st) for p, st in zip(self.positionen, stat) if st.startswith(("FEHLER", "WARNUNG", "HINWEIS"))])
        punkte = self.freigabe_punkte(summen, zeilen, preis_abw)
        self.uebersicht_bereich.freigabe_setzen(punkte)
        self._punkte = punkte
        self._schritte_setzen()
        kosten = rechnen.kostenarten(summen, self.einst)
        self.uebersicht_bereich.kosten_setzen(kosten)
        vk = next(w for (_, w, _), (_, n, _) in zip(kosten, rechnen.KOSTENARTEN) if n == "verkauf")
        stand = self.stand_optimierung()
        if not self.db.nur_lesen:          # Kennzahlen für die Angebotsliste (im Lesemodus bleibt der alte Stand)
            self.db.kennzahlen_merken(self.id, round(vk, 2) if isinstance(vk, (int, float)) else None,
                                      "aktuell" if stand == "aktuell" else "offen" if not self.ergebnis else "veraltet")
        self.uebersicht_bereich.zeiten_setzen(rechnen.zeit_summen(summen["zeiten"], summen.get("teile")))
        self.uebersicht_bereich.baugruppen_setzen(self._baugruppen_kosten())
        self.wiederholteile_anzeigen()
        self.zeiten_seite.setzen(summen)
        self.zukauf.setzen(zukauf_zeilen(summen["zukauf"]))
        self.zukauf_info.setText(zukauf_info(summen))
        self.summen.setText(" · ".join(f"<b>{t} {_z(w)} €</b>" if fett else f"{t} {_z(w)} €"
                                       for t, w, fett in kosten if fett or sichtbar(w)))
        self.kompakt.setzen(kompakt_zeilen(self.positionen, markiert))
        self.kompakt_ansicht.setColumnHidden(next(c for c, sp in enumerate(KOMPAKT_SPALTEN) if sp[1] == "satz"),
                                             not any(z.get("satz") for z in self.kompakt.zeilen))
        katalog = self.tabellen.get("zusatzarbeiten") or ()
        self.unter_texte = {i: unterzeilen.schritte(p, z, katalog) for i, (p, z) in enumerate(zip(self.positionen,
                                                                                                   zeilen))}
        self.pos_unter.aktualisieren()
        self.kompakt_unter.aktualisieren()
        leere_ausblenden(self.kompakt_ansicht, self.kompakt, KOMPAKT_IMMER)
        self._kalk_info_setzen()
        if erg:
            sw = rechnen.stangen_werte(erg, self.kopf, self.positionen, self.k, self.tabellen)
            # Schnittplan wie geladen: zugeschnittene Lieferstangen als ihre Werkstücke
            paare = rechnen.anzeige_stangen(erg, sw)
            self.stangen.setzen([dict(s, **w) for s, w in paare])
            ausw = rechnen.auswertung_zeilen(erg, sw)
            self.ausw.setzen(ausw)
            self.fehler.setzen(erg["fehler"])
        else:
            paare = []
            self.stangen.setzen([])
            self.ausw.setzen([])
            self.fehler.setzen([])
        gleich = gleiche_ausblenden(self.stangen_ansicht, self.stangen, PLAN_GLEICH)
        self.plan_info.setText(f"{len(self.stangen.zeilen)} Stangen" + (" · für alle gleich: " + " · ".join(gleich)
                                                                          if gleich else "")
                               if self.stangen.zeilen else "Noch nicht optimiert.")
        self.fehler_titel.setText(
            "" if not erg else "<span style='color:#1E6B34'><b>✓ Alle Teile eingeplant.</b></span>"
            if not erg["fehler"] else f"<span style='color:#B42318'><b>Nicht eingeplante Teile "
                                      f"({len(erg['fehler'])})</b></span>")
        self.fehler_ansicht.setVisible(bool(erg and erg["fehler"]))
        self.teile.setzen([])
        self.laengen_ansicht.setHtml(laengen_html(erg, self.kopf, self.positionen, self.k, self.tabellen, self.einst))
        hinweis = laengen_sinnvoll(erg, self.kopf, self.positionen, self.k, self.tabellen, self.einst)
        self.laengen_knopf.setVisible(bool(hinweis))
        self.laengen_hinweis.setVisible(bool(hinweis))
        self.laengen_hinweis.setText(f"<b>Lieferlängen:</b> {hinweis}" if hinweis else "")
        self.stangen_seite.setzen(paare, self._abwicklung_funktion() if erg else None)
        self.teile_baum.setzen(abmessung.teilebaum(self.kopf, self.positionen, erg))
        self.prot.setzen(self.db.protokoll(self.id))
        self._spaeter_fuellen("st_seite", lambda: self._st_seite.setzen())
        self._spaeter_fuellen("nachkalk", lambda: self._nachkalk.neu_laden())
        if self.stangen.zeilen:          # Teile der ersten Stange gleich zeigen, nicht erst nach einem Klick
            zeile = max(self.stangen_ansicht.currentIndex().row(), 0)
            self.stangen_ansicht.selectRow(min(zeile, len(self.stangen.zeilen) - 1))
            self._stange_gewaehlt(self.stangen_ansicht.currentIndex())

    # Performance-Plan P9: Staffeln und Nachkalkulation erst füllen, wenn ihr Reiter gezeigt wird oder jemand sie
    # braucht (Zugriff über self.st_seite bzw. self.nachkalk füllt nach). Ergebnis gleich, Neuladen schneller.
    def _spaeter_fuellen(self, name, fuellen):
        offen = self.__dict__.setdefault("_offen_fuellen", {})
        if self.reiter.currentWidget() is getattr(self, "_" + name):
            offen.pop(name, None)
            fuellen()
        else:
            offen[name] = fuellen

    def _verdeckte_fuellen(self, seite):
        for name in ("st_seite", "nachkalk"):
            if seite is getattr(self, "_" + name, None):
                getattr(self, name)

    def _gefuellt(self, name):
        fuellen = self.__dict__.get("_offen_fuellen", {}).pop(name, None)
        if fuellen is not None:
            fuellen()
        return getattr(self, "_" + name)

    st_seite = property(lambda self: self._gefuellt("st_seite"))
    nachkalk = property(lambda self: self._gefuellt("nachkalk"))

    def _abwicklung_funktion(self):
        """Abwicklung einer Stange für Stangen-Detail (stangen_abwicklung.stange) mit den Positionen dieses Stands."""
        positionen, profil_von = list(self.positionen), stangen_abwicklung.profil_funktion(self.kopf, self.k)
        merker = {}         # gleiche Teile auf mehreren Stangen einmal (Performance-Plan P7)
        return lambda s: stangen_abwicklung.stange(s, positionen, profil_von, merker)

    def _vorschau_netz(self, zeile):
        """3D-Modell einer Position für die Vorschau im Teilebaum: (Netz oder None, Titel). Netz aus dem STEP-Import,
        sonst aus den Eingaben des Teile-Editors (rohr3d)."""
        if not 0 <= zeile < len(self.positionen):
            return None, ""
        p = self.positionen[zeile]
        if p.get("id") is not None:
            daten = self.db.netz(p["id"])
            if daten:
                return daten, "3D aus dem STEP-Import"
        profil = self.k.profile.get(p.get("profil_id"))
        if not profil or kein_laserteil(p):
            return None, ""
        try:
            from . import rohr3d
            profil = rechnen.profil_im_angebot(profil, self.kopf, p.get("profil_id"), p.get("werkstoff_id"), self.k)
            from .anbau import eingaben_mit_gravur
            e = eingaben_mit_gravur(schneidweg.aus_position(schneidweg.lesen(p.get("technik")), p, profil)[0], p)
            netz = rohr3d.netz(e, profil,
                               p.get("laenge"), p.get("naht_winkel") if naht.vorgabe(p) == naht.FEST else None,
                               dreid.schwenk_grenze(rechnen.maschine(self.kopf, self.k)))
        except (ValueError, TypeError, KeyError, ZeroDivisionError):
            netz = None
        return netz, "3D-Modell aus den Eingaben" if netz else ""

    def _baum_gewaehlt(self, ref):
        """Position im Teilebaum gewählt: im Stangenbild hervorheben, im Schnittplan die erste Stange mit dem Teil."""
        self.stangen_seite.markieren(ref)
        if not self.ergebnis:
            return
        stangen = rechnen.anzeige_stangen(self.ergebnis)
        i = next((i for i, s in enumerate(stangen) if any(t["ref"] == ref for t in s["teile"])), None)
        if i is None:
            return
        modell = self.stangen_ansicht.model()
        quelle = modell.sourceModel() if hasattr(modell, "sourceModel") else None
        index = modell.mapFromSource(quelle.index(i, 0)) if quelle is not None else modell.index(i, 0)
        if index.isValid():
            self.stangen_ansicht.setCurrentIndex(index)
            self.stangen_ansicht.scrollTo(index)
            r = next((j for j, t in enumerate(self.teile.zeilen) if t.get("ref") == ref), None)
            if r is not None:
                self.teile_ansicht.selectRow(r)

    def _stange_gewaehlt(self, aktuell, _=None):
        if not aktuell.isValid() or not self.ergebnis:
            self.teile.setzen([])
            self.teile_titel.setText("")
            return
        zeile = self.stangen_ansicht.model().mapToSource(aktuell).row() if hasattr(
            self.stangen_ansicht.model(), "mapToSource") else aktuell.row()
        s = rechnen.anzeige_stangen(self.ergebnis)[zeile]     # in der Liste ist 'teile' die Anzahl
        self.teile.setzen([dict(t, platz=i) for i, t in enumerate(s["teile"], start=1)])
        leere_ausblenden(self.teile_ansicht, self.teile, {"platz", "pos", "artikel", "laenge", "von", "bis"})
        self.teile_titel.setText(f"<b>Teile auf Stange {s.get('nr') or zeile + 1}</b> (Stange oben wählen)")

    def _spalten_zeigen(self):
        """Sichtbare Spalten der Positionsliste: Standardspalten immer, optionale Spalten mit Werten oder nach Wahl
        unter 'Weitere Spalten', STEP-Werte und berechnete Werte über die Häkchen."""
        m = self.pos_modell
        neu = set()
        for i, (art, x) in enumerate(m.spalten):
            name = m.name(i)
            if art == "berechnet":
                zeigen = self.zeige_berechnet.isChecked()
            elif art == "feld" and x.name in STEP_FELDER:
                zeigen = self.zeige_step.isChecked()
            elif art == "abweichung":
                zeigen = self.zeige_step.isChecked() or self._spalte_hat_werte(i)
            elif name in OPTIONALE_SPALTEN:
                zeigen = self.spalten_wahl.get(name, self._spalte_hat_werte(i))
            else:
                zeigen = True
            if zeigen and self.pos_ansicht.isColumnHidden(i):
                neu.add(i)
            self.pos_ansicht.setColumnHidden(i, not zeigen)
        if neu and self.pos_ansicht.auto_groesse.eingepasst:     # neu gezeigte Spalten einpassen (sonst beim Füllen)
            self.pos_ansicht.auto_groesse.einpassen(neu)
        aus = sum(1 for i, (art, _) in enumerate(m.spalten) if m.name(i) in OPTIONALE_SPALTEN
                  and self.pos_ansicht.isColumnHidden(i))
        n = sum(1 for p in self.positionen if position_aktiv(p) or p.get("artikel"))
        self.pos_info.setText(f"{n} {'Position' if n == 1 else 'Positionen'}"
                              + (f" · {aus} optionale Spalten ausgeblendet (Weitere Spalten)" if aus else ""))

    def _spalte_hat_werte(self, c):
        return spalte_sichtbar([self.pos_modell.roh(r, c) for r in range(self.pos_modell.rowCount())])

    def _spalten_menue_fuellen(self):
        m, menue = self.pos_modell, self.spalten_menue
        menue.clear()
        for i, (art, x) in enumerate(m.spalten):
            name = m.name(i)
            if name not in OPTIONALE_SPALTEN:
                continue
            a = menue.addAction(x.titel + ("" if self._spalte_hat_werte(i) else "  (leer)"))
            a.setCheckable(True)
            a.setChecked(not self.pos_ansicht.isColumnHidden(i))
            a.toggled.connect(lambda an, name=name: self.spalte_waehlen(name, an))
        menue.addSeparator()
        menue.addAction("Automatisch: Spalten mit Werten zeigen", lambda: self.spalte_waehlen(None, None))

    def spalte_waehlen(self, name, zeigen):
        """Optionale Spalte fest ein- (True) oder ausblenden (False); name=None: alle wieder automatisch."""
        if name is None:
            self.spalten_wahl = {}
        else:
            self.spalten_wahl[name] = zeigen
        if not self.db.nur_lesen:          # Spaltenwahl ist Ansicht: im Lesemodus nur für diese Sitzung
            self.db.einstellung_setzen(SPALTEN_EINSTELLUNG, self.spalten_wahl)
        self._spalten_zeigen()

    # -------------------------------------------------------------- Bearbeiten
    def position_neu(self, typ=None, dialog=None):
        """Neue Position: zuerst der Typ (neue_position.TypDialog), dann Rohr / Profil = Schneidweg-Rechner mit
        Kopfzeile, Blech / Kantteil = Blech-Editor (Richtpreis als EK), Zukaufteil = Schnellanlage Zukaufartikel, leere
        Zeile = wie bisher. Ohne Rückfragen (stumm) und ohne typ:
        leere Zeile. dialog(d) bedient den Rechner statt exec (Tests). Ergebnis: Typ oder None (abgebrochen)."""
        from .neue_position import BLECH, DXF, LEER, PDF, RAHMEN, ROHR, SCHWEISS, UEBERNEHMEN, ZUKAUF, TypDialog
        if typ is None:
            if self.f.stumm:
                typ = LEER
            else:
                d = TypDialog(self, pdf=self.db.einstellung("pdf_zeichnung") == "ja",
                              ohne=[t for t, n in ((BLECH, "funktion_blech"), (ZUKAUF, "funktion_zukauf"),
                                                   (SCHWEISS, "funktion_schweissen")) if not funktionen.an(n)])
                if d.exec() != QDialog.Accepted or not d.typ:
                    return None
                typ = d.typ
        if typ == BLECH:
            return typ if self.blech_neu(dialog=dialog) else None
        if typ == DXF:
            return typ if self.blech_aus_dxf() else None
        if typ == PDF:
            return typ if self.rohr_aus_pdf(dialog=dialog) else None
        if typ == ZUKAUF:
            return typ if self.zukauf_schnell(zeilen=[], blech=False) else None
        if typ == ROHR:
            return typ if self.rohr_neu(dialog=dialog) else None
        if typ == SCHWEISS:
            return typ if self.baugruppe_neu(dialog=dialog) else None
        if typ == RAHMEN:
            return typ if self.rahmen_assistent(dialog=dialog) else None
        if typ == UEBERNEHMEN:
            return typ if self.positionen_uebernehmen(dialog=dialog) else None
        self.db.position_neu(self.id, {"pos": self._naechste_pos()})
        self.neu_laden()
        r = len(self.positionen) - 1
        i = self.pos_modell.index(r, 1)
        self.reiter.setCurrentIndex(0)
        self.pos_ansicht.scrollTo(i)
        self.pos_ansicht.setCurrentIndex(i)
        self.pos_ansicht.edit(i)
        return typ

    def zeile_anhaengen(self):
        """Leere Position am Ende (↓ bzw. Eingabe in der letzten Zeile, W5), ohne Dialog; nicht, solange die letzte
        Position noch ganz leer ist (gehaltenes ↓ legt keine Reihe leerer Zeilen an). Ergebnis: True = angelegt."""
        if self.db.nur_lesen or self.fremd():
            return False
        if self.positionen and not any(self.positionen[-1].get(n) for n in ("artikel", "bezeichnung", "profil_id",
                                                                             "laenge", "stueck", "zukauf")):
            self.f.meldung("Die letzte Position ist noch leer.")
            return False
        self.db.position_neu(self.id, {"pos": self._naechste_pos()})
        self.neu_laden()
        self.f.meldung("Neue Position angelegt.")
        return True

    def _schnell_vorschau(self, text):
        from . import schnellzeile
        zeilen = schnellzeile.lesen(text, self.k.profile, self.k.werkstoffe, self._schnell_bevorzugt()) \
            if text.strip() else []
        self.schnell_vorschau.setText(schnellzeile.vorschau(zeilen[0], lambda z: rechnen.zahl(z, 1)) if zeilen else "")

    def _schnell_bevorzugt(self):
        """Werkstoffe für ein mehrdeutiges Wort der Schnellzeile (S235): letzte Position, Vorgabe step_werkstoff, dann
        die zuletzt benutzten."""
        letzter = next((p.get("werkstoff_id") for p in reversed(self.positionen) if p.get("werkstoff_id")), None)
        try:
            zuletzt = self.db.zuletzt_benutzt("werkstoff")
        except Exception:       # noqa: BLE001 – Datendatei geschlossen o. Ä.
            zuletzt = []
        return [w for w in dict.fromkeys([letzter, self.db.einstellung("step_werkstoff"), *zuletzt]) if w]

    def schnellzeile(self, text=None):
        """Positionen aus der Schnellzeile (B6) anlegen; text = mehrere Zeilen (Einfügen), sonst das Feld. Werkstoff
        ohne Angabe: der der letzten Position bzw. die Vorgabe der Einstellungen. Zeilen mit Fehler bleiben im Feld.
        Ergebnis: Anzahl angelegter Positionen."""
        from . import schnellzeile
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return 0
        quelle = self.schnell.text() if text is None else text
        zeilen = schnellzeile.lesen(quelle, self.k.profile, self.k.werkstoffe, self._schnell_bevorzugt())
        if not zeilen:
            return 0
        for z in zeilen:        # eben neu angelegte Abmessung mit eigener Profil-ID (abmessung_neu)
            pid = getattr(self, "abm_zuordnung", {}).get(z.get("rest"))
            if pid in self.k.profile and not z.get("profil_id"):
                z["profil_id"] = pid
                z["fehler"] = [x for x in z["fehler"] if "nicht gefunden" not in x]
        letzter = next((p.get("werkstoff_id") for p in reversed(self.positionen) if p.get("werkstoff_id")), None)
        vorgabe = letzter or self.db.einstellung("step_werkstoff") or None
        vorgabe = vorgabe if vorgabe in self.k.werkstoffe else None
        gut, schlecht = [], []
        self.verlauf.pause += 1
        try:
            for z in zeilen:
                if z["fehler"]:
                    schlecht.append(z)
                    continue
                werte = dict(pos=self._naechste_pos(), profil_id=z["profil_id"], laenge=z["laenge"],
                             stueck=z.get("stueck") or 1, werkstoff_id=z.get("werkstoff_id") or vorgabe)
                if z.get("artikel"):
                    werte["artikel"] = z["artikel"]
                self.db.position_neu(self.id, werte)
                self.positionen.append(dict(werte))         # für die nächste Pos.-Nummer
                gut.append(z)
        finally:
            self.verlauf.pause -= 1
        # nicht erkannte Zeilen: die erste ins Feld, die übrigen folgen nacheinander nach Eingabe (nichts geht verloren)
        rest = [z["text"] for z in schlecht] + getattr(self, "schnell_rest", [])
        self.schnell_rest = rest[1:]
        self.schnell.setText(rest[0] if rest else "")
        bericht = ("Schnellzeile – nicht erkannt", "\n".join(f"{z['text']}  ({', '.join(z['fehler'])})"
                                                             for z in schlecht)) if len(schlecht) > 1 else None
        if gut:
            self.neu_laden()
            text_ = f"{len(gut)} Position(en) aus der Schnellzeile angelegt."
            if schlecht:
                text_ += f" {len(schlecht)} Zeile(n) nicht erkannt: " + "; ".join(
                    f"„{z['text']}“ ({', '.join(z['fehler'])})" for z in schlecht[:3])
            self.rueckgaengig_anbieten(text_, bericht=bericht)
        else:
            self.f.meldung("Schnellzeile: " + "; ".join(f"„{z['text']}“: {', '.join(z['fehler'])}"
                                                        for z in schlecht[:3]), fehler=True, bericht=bericht)
        # Abmessung der Zeile im Feld fehlt in den Stammdaten: Menü „neu anlegen …“ unter dem Feld (Patrick 28.10.)
        erste = schlecht[0] if schlecht else None
        if erste and erste.get("rest") and not erste.get("profil_id") and \
                any("nicht gefunden" in x for x in erste["fehler"]):
            self.abmessung_neu_anbieten(erste["rest"], self.schnell, lambda pid: self.schnellzeile())
        return len(gut)

    def abmessung_neu_anbieten(self, text, feld=None, weiter=None):
        """Getippte Abmessung fehlt in den Stammdaten (Schnellzeile, Profilspalte): Menü unter dem Feld mit
        „Abmessung … neu anlegen …“ (profil_neu.anbieten). weiter(pid) läuft nach dem Anlegen. Ergebnis: Menü
        oder None (nur ansehen, keine Zahl im Text)."""
        if self.fremd() or self.db.nur_lesen:
            return None
        wo = feld.mapToGlobal(feld.rect().bottomLeft()) if feld is not None else None
        self.abm_menue = profil_neu.anbieten(self, text, lambda t: self.abmessung_neu(t, weiter), wo)
        return self.abm_menue

    def abmessung_neu(self, text, weiter=None, dialog=None):
        """Fenster „Neue Abmessung anlegen“ mit Form und Maßen aus text (profil_neu.vorschlag); bestätigt: Zeile in
        den Stammdaten (Profile), danach weiter(pid). Den Materialpreis rät das Programm nicht: die Meldung weist
        darauf hin, die Position zeigt ihn als fehlend. dialog(d) bedient das Fenster (Tests). Ergebnis: Profil-ID
        oder None."""
        d = profil_neu.ProfilNeuDialog(self, self.k.profile, None, self.k.profilformen, eingabe=text,
                                       bemerkung=f"im Angebot angelegt ({datetime.date.today():%d.%m.%Y})")
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or d.fehler():
            return None
        werte = d.werte()
        pid = werte["profil_id"]
        self.db.profile_anlegen([werte])
        zeile = next((z for z in self.db.zeilen("profile") if z.get("profil_id") == pid), werte)
        for k in {id(x): x for x in (self.k, getattr(self, "k_aktuell", None)) if x is not None}.values():
            k.profile[pid] = zeile
        self.abm_zuordnung = dict(getattr(self, "abm_zuordnung", {}), **{" ".join(text.split()): pid})
        if weiter:
            weiter(pid)
        self.f.meldung(f"Abmessung {pid} in den Stammdaten angelegt. Materialpreis fehlt noch: unter Einstellungen → "
                       "Werkstoffe/Materialpreise oder im Angebot über „Material …“ als Meterpreis eintragen.")
        return pid

    def _naechste_pos(self):
        vorher = [p["pos"] for p in self.positionen if isinstance(p.get("pos"), (int, float))]
        return int(max(vorher, default=0)) + 10

    def rahmen_assistent(self, dialog=None, satz_dialog=None):
        """Rahmen-Assistent (A8): Rechteckrahmen oder Quader aus Rohr ohne STEP-Datei als Satz. Die Rohre werden
        Positionen (Länge, Enden, Schneidweg) mit Netz, Einbaulage und Stößen; danach öffnet Satz in 3D (mit
        „stumpf mit Steckverbindungen“ sind die Verbindungen dort schon angelegt, mit „Knickrahmen“ öffnet
        Knickrahmen erstellen für alle Rohre). dialog(d) bzw. satz_dialog(d)
        bedienen die Fenster (Tests). Ergebnis: Name des Satzes oder None."""
        from . import rahmen
        from .ansicht3d import packen
        from .rahmen_dialog import RahmenDialog
        from .satz3d import saetze
        letzte = next((p for p in reversed(self.positionen) if p.get("werkstoff_id")), {})
        d = RahmenDialog(self, self.k.profile, self.k.werkstoffe,
                         letzte.get("werkstoff_id") or self.db.einstellung("step_werkstoff"))
        if not d.profile:
            self.f.meldung("Rahmen-Assistent: In den Profilen gibt es kein Quadrat-, Rechteck- oder Rundrohr.",
                           fehler=True)
            return None
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or not d.ergebnis:
            return None
        w = d.ergebnis
        profil = self.k.profile[w["profil_id"]]
        name, n = w["name"], 2
        while name in saetze(self.positionen):
            name, n = f"{w['name']} {n}", n + 1
        hinweise = []
        for t in w["erg"]["teile"]:
            je = len(t["lagen"])
            pid = self.db.position_neu(self.id, dict(
                pos=self._naechste_pos(), profil_id=w["profil_id"], werkstoff_id=w["werkstoff_id"],
                laenge=t["laenge"], stueck=w["saetze"] * je, satz=name, je_satz=je,
                bezeichnung=f"{name} {t['name']}", technik=schneidweg.speichern(t["eingaben"])))
            netz = rahmen.netz(t, profil)
            if netz:
                self.db.netz_speichern(pid, packen(netz))
            self.neu_laden()
            zeile = next(r for r, q in enumerate(self.positionen) if q["id"] == pid)
            alt_stumm, self.f.stumm = self.f.stumm, True
            try:
                if not self.schneidweg_berechnen(zeile, t["eingaben"], ueberschreiben=True):
                    hinweise.append(f"{t['name']}: Schneidweg nicht gerechnet")
            finally:
                self.f.stumm = alt_stumm
        self.db.satz_daten_speichern(self.id, name, dict(stoesse=w["erg"]["stoesse"]))
        self.neu_laden()
        self.f.meldung(f"Rahmen-Assistent: Satz {name} mit {sum(len(t['lagen']) for t in w['erg']['teile'])} Rohren "
                       "angelegt." + "".join(f" {h}" for h in hinweise))
        stecken, knick = w["erg"]["stecken"], w["erg"].get("knick")
        if satz_dialog is not None or not self.f.stumm or stecken or knick:
            def bedienen(sd):
                if stecken:
                    sd.steck_alle(melden=False)
                if knick:           # Ecke Knickrahmen: alle Rohre markiert, Knickrahmen-Fenster (stumm: Vorgaben)
                    sd.teile_tab.selectAll()
                    sd.knick_erstellen(dialog=(lambda kd: QDialog.Accepted) if self.f.stumm else None,
                                       melden=not self.f.stumm)
                if satz_dialog is not None:
                    return satz_dialog(sd)
                if self.f.stumm:
                    sd._ok()
                    return sd.result()
                return sd.exec()
            self.satz_3d(satz=name, dialog=bedienen)
        return name

    def rohr_neu(self, dialog=None, dxf=None):
        """Neue Rohr-/Profilposition im Schneidweg-Rechner mit Kopfzeile anlegen. Vorbelegt: Profil und Werkstoff der
        letzten Rohrposition (sonst erstes Profil, Werkstoff aus der Einstellung step_werkstoff), Stückzahl 1.
        dxf = (Dateiname, Ergebnis von dxf_rohr.erkennen): alles aus der Zeichnung vorbelegt (Plan 3E-12).
        Ergebnis: True = angelegt."""
        if not self.k.profile:
            self.f.meldung("Neue Position: Es gibt noch keine Profile in den Stammdaten.", fehler=True)
            return False
        letzte = next((p for p in reversed(self.positionen) if not kein_laserteil(p)
                       and p.get("profil_id") in self.k.profile), {})
        pid = letzte.get("profil_id") or sorted(self.k.profile, key=str.lower)[0]
        wst = letzte.get("werkstoff_id") or self.db.einstellung("step_werkstoff") or None
        if dxf:
            from . import dxf_rohr
            pid = dxf_rohr.profil_id(dxf[1]["profil"], self.k.profile) or \
                dxf_rohr.ersatz_profil(dxf[1]["profil"], self.k.profile) or pid
        p = dict(pos=self._naechste_pos(), profil_id=pid, werkstoff_id=wst if wst in self.k.werkstoffe else None,
                 stueck=(dxf[1].get("stueck") if dxf else None) or 1)
        d = SchneidwegDialog(self, p, self.k.profile[pid], self.kopf, self.k, self.tabellen, self.db, self.positionen,
                             neu=True)
        if dxf:
            d.dxf_uebernehmen(dxf[1], dxf[0])
        if (dialog(d) if dialog else teile_editor.ausfuehren(d)) != QDialog.Accepted:
            return False
        eingaben = d.eingaben()
        grenzen = rechnen.kontur_regel(rechnen.maschine(self.kopf, self.k), rechnen.wand_schneiden(d.profil))
        erg = schneidweg.rechnen(eingaben, d.profil, grenzen, gewinde_liste(self.tabellen), rechnen.maschine(self.kopf, self.k))
        if erg["fehler"] or d.kopf_fehler():
            self.f.meldung("Neue Position: " + " ".join(erg["fehler"] + d.kopf_fehler()), fehler=True)
            return False
        werte = dict(pos=p["pos"], **d.kopf_werte(), **erg["felder"], technik=schneidweg.speichern(eingaben))
        werte.update({k_: v for k_, v in d.naht_werte().items() if v is not None})
        werte["muster"] = d.muster_haken.wert()
        from . import bohrbild     # Gewinde, Senken, Flowdrill, Bohren < 0,7 × Wand: von Hand eingegeben = bestätigt
        bild = bohrbild.aus_rechner(erg, [], gewinde_liste(self.tabellen) or step.KERNLOCH,
                                    rechnen.wand_schneiden(d.profil), self.db.einstellung("fliessloch_laser"),
                                    self.db.einstellung("bohren_laser"))
        if bild:
            werte.update(bohrbild.anwenden(werte, bild, None, self.tabellen.get("zusatzarbeiten") or [],
                                           rechnen.stundensaetze(self.tabellen)))
            werte.pop("_fehlt", None)
        if erg.get("laenge"):           # Knickrahmen: gestreckte Länge
            werte["laenge"] = erg["laenge"]
        self._knicken_eintragen(werte, werte, erg)
        self._stege_eintragen(werte, werte)
        pid_neu = self.db.position_neu(self.id, {k_: v for k_, v in werte.items() if v is not None})
        self._radius_uebernehmen(dict(werte, id=pid_neu), eingaben)
        self.neu_laden()
        self.f.meldung(f"Pos. {p['pos']} angelegt: {werte.get('profil_id')}, Schneidweg "
                       f"{rechnen.zahl(erg['schneidweg'], 1)} mm.")
        self.zur_position(zeile=next((r for r, x in enumerate(self.positionen) if x["id"] == pid_neu), None))
        return True

    def rohr_aus_pdf(self, pfade=None, dialog=None, zuordnung=None, wand=None):
        """Rohrteile aus PDF-Zeichnungen (Plan W7, Test): ein PDF aus dem CAD (Linien) geht durch die Rohrerkennung
        der DXF (Stufe 2, pdf_vektor.py: Enden und Konturen, bei Unsicherheit das Zuordnungsfenster); sonst Profil,
        Länge, Werkstoff, Artikel, Benennung und Stückzahl aus dem Text (Stufe 1, Scans mit Tesseract,
        pdf_zeichnung.py). Profil nur aus den Maßen am Schnitt (ohne Wand): die Wandstärke wird aus den passenden
        Profilen der Stammdaten gewählt. Je Datei öffnet der Rohr-Editor damit. dialog(d) bedient den Rohr-Editor,
        zuordnung(d) das Zuordnungsfenster, wand(liste) die Wahl der Wandstärke statt exec (Tests). Ergebnis: Anzahl
        angelegter Positionen."""
        from . import dxf_rohr_dialog, pdf_vektor, pdf_zeichnung
        if self.fremd():
            return 0
        if not pfade:
            pfade, _ = QFileDialog.getOpenFileNames(self, "Aus PDF-Zeichnung", str(self.db.einstellung("dxf_ordner") or ""),
                                                    "Zeichnungen (*.pdf *.PDF *.png *.jpg *.jpeg *.tif *.tiff)")
            if not pfade:
                return 0
            self.db.einstellung_setzen("dxf_ordner", str(Path(pfade[0]).parent))
        n = 0
        for pfad in pfade:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                erg = pdf_zeichnung.erkennen(pfad, self.f.programmordner)
                try:
                    linien = pdf_vektor.dxf_text(pfad) if Path(pfad).suffix.lower() == ".pdf" else None
                except Exception:       # beschädigtes PDF o. ä.: nur der Text
                    linien = None
            finally:
                QApplication.restoreOverrideCursor()
            if linien:
                lin = dxf_rohr_dialog.rohr_erkennen(self, self.db, pfad, dialog=zuordnung, text=linien)
                if lin["ok"] and not lin.get("abgebrochen"):
                    erg = pdf_zeichnung.mit_linien(lin, erg)
                elif erg["ok"]:         # Zuordnung abgebrochen oder kein Rohr in den Linien: nur der Text
                    erg["hinweise"].append("Die Linien der Zeichnung ergaben kein Rohr: nur Angaben aus dem Text.")
            if not erg["ok"]:
                self.f.meldung(f"{Path(pfad).name}: " + " ".join(erg["warnungen"]), fehler=True)
                continue
            if erg["profil"].get("wand") is None and not self._wand_waehlen(erg, Path(pfad).name, wand):
                continue
            n += bool(self.rohr_neu(dialog=dialog, dxf=(Path(pfad).name, erg)))
        if n > 1:
            self.f.meldung(f"{n} Positionen aus PDF-Zeichnungen angelegt.")
        return n

    def _wand_waehlen(self, erg, name, wand=None):
        """Profil ohne Wandstärke (aus den Maßen am Schnitt einer PDF-Zeichnung): die Profile der Stammdaten mit
        gleicher Form und gleichem Außenmaß zur Wahl (eines: ohne Frage), ohne solche das ähnlichste der Form. Setzt
        erg['profil']['wand']; False = abgebrochen oder kein Profil der Form."""
        from . import dxf_rohr
        pr = erg["profil"]
        passend = sorted((pid for pid, p in self.k.profile.items() if p.get("form") == pr["form"]
                          and abs(float(p.get("a") or 0) - pr["a"]) < 0.05
                          and abs(float(p.get("b") or p.get("a") or 0) - pr["b"]) < 0.05),
                         key=lambda pid: float(self.k.profile[pid].get("wand") or 0))
        if not passend:
            pid = dxf_rohr.ersatz_profil(dict(pr, wand=0.0), self.k.profile)
            if not pid:
                self.f.meldung(f"{name}: kein {pr['form']} in den Stammdaten.", fehler=True)
                return False
            erg["warnungen"].append(f"Kein Profil {dxf_rohr._z(pr['a'])}×{dxf_rohr._z(pr['b'])} in den Stammdaten: "
                                    f"das ähnlichste ({pid}) ist gewählt.")
        elif len(passend) == 1:
            pid = passend[0]
        else:
            if wand:
                pid = wand(passend)
            else:
                pid, ok = QInputDialog.getItem(self, "Wandstärke wählen",
                                               f"{name}: Profil {dxf_rohr._z(pr['a'])}×{dxf_rohr._z(pr['b'])} aus den "
                                               "Maßen am Schnitt, die Wandstärke steht nicht in der Zeichnung.\n"
                                               "Profil:", passend, 0, False)
                pid = pid if ok else None
            if not pid:
                return False
        p = self.k.profile[pid]
        erg["profil"] = dict(form=p.get("form"), a=float(p.get("a") or 0), b=float(p.get("b") or p.get("a") or 0),
                             wand=float(p.get("wand") or 0))
        return True

    def blech_neu(self, dialog=None):
        """Blech- oder Kantteil im Blech-Editor beschreiben; der Richtpreis wird EK eines neuen Zukaufartikels
        (Kategorie Blechteile, Artikeltyp Blech) und die Position (Zukaufteil) behält die Eingaben in 'technik'.
        dialog(d) bedient den Editor statt exec (Tests). Ergebnis: True = angelegt."""
        from .blech_dialog import BlechDialog
        d = BlechDialog(self, self.db, neu=True)
        if (dialog(d) if dialog else teile_editor.ausfuehren(d)) != QDialog.Accepted or not d.ergebnis.get("richtpreis"):
            return False
        return self._blech_anlegen(d.eingaben(), d.ergebnis, d.kopf_werte())

    def _blech_anlegen(self, e, erg, kopf):
        """Neue Position (Zukaufteil) mit neuem Zukaufartikel aus Blech-Eingaben e und Ergebnis erg (blech.rechnen);
        kopf: bezeichnung, artikelnr, lieferant, stueck. Ergebnis: True = angelegt."""
        zs = erg["zuschnitt"]
        werte, bezuege = artikel_werte(kopf["bezeichnung"], kopf["artikelnr"], "Blechteile", kopf["lieferant"],
                                       erg["richtpreis"], None)
        werte.update(artikeltyp="Blech", laenge=round(zs["laenge"], 1), breite=round(zs["breite"], 1),
                     dicke=e["dicke"], werkstoff=e["werkstoff"], herkunft=blech.QUELLE)
        try:
            aid = self.db.zukauf_speichern(None, werte, bezuege, "Richtpreis aus dem Blech-Editor")
        except ValueError as x:
            self.f.meldung(f"Blech-Editor: {x}", fehler=True)
            return False
        nr = self._naechste_pos()
        self.db.position_neu(self.id, dict(
            pos=nr, art=ZUKAUFTEIL, artikel=kopf["artikelnr"] or kopf["bezeichnung"], bezeichnung=kopf["bezeichnung"],
            stueck=kopf["stueck"], technik=blech.speichern(dict(e, richtpreise=[dict(ab=1, preis=erg["richtpreis"])])),
            gewicht_teil=round(erg["gewicht"], 3), muster=kopf.get("muster"),
            zukauf=json.dumps([dict(artikel_id=aid, menge=1, stand=self.db.zukauf_stand(aid))], ensure_ascii=False)))
        self.neu_laden()
        self.f.meldung(f"Pos. {nr} angelegt: {kopf['bezeichnung']}, Richtpreis {rechnen.zahl(erg['richtpreis'], 2)} € "
                       "je Stück als EK (Zukaufteil).")
        return True

    def blech_aus_dxf(self, pfade=None, dialog=None, rohr_dialog=None, zuordnung=None):
        """Bleche aus DXF-Dateien (3E-9): je Datei das Importfenster (alle Teile mit Haken), je angehaktem Teil eine
        Position wie aus dem Blech-Editor. Zeigt die Datei ein Rohrlaserteil in Ansichten (Rohrschnitt, 3E-12), öffnet
        stattdessen der Rohr-Editor mit Profil, Länge, Enden und Konturen aus der Zeichnung. dialog(d) bzw.
        rohr_dialog(d) bedient das Fenster statt exec (Tests). Ist die Rohrzeichnung unsicher (3E-15), kommt erst das
        Zuordnungsfenster (zuordnung(d) statt exec). Ergebnis: Anzahl."""
        from . import dxf_rohr_dialog
        from .dxf_import_dialog import DxfImportDialog
        if self.fremd():
            return 0
        if not pfade:
            pfade, _ = QFileDialog.getOpenFileNames(self, "Aus DXF", str(self.db.einstellung("dxf_ordner") or ""),
                                                    "DXF-Dateien (*.dxf *.DXF)")
            if not pfade:
                return 0
            self.db.einstellung_setzen("dxf_ordner", str(Path(pfade[0]).parent))
        werkstoffe = {z["blech_werkstoff_id"]: z for z in self.db.zeilen("blech_werkstoffe")
                      if z.get("blech_werkstoff_id")}
        laser, einst = self.db.zeilen("blechlaser"), self.db.blech_einstellungen()
        n = 0
        for pfad in pfade:
            # Rohrzeichnung (Ansichten eines Rohrlaserteils, 3E-12): Rohr-Editor mit allem aus der Zeichnung
            try:
                rohr = dxf_rohr_dialog.rohr_erkennen(self, self.db, pfad, dialog=zuordnung, blech_moeglich=True)
            except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
                rohr = None
            if rohr and rohr.get("abgebrochen"):
                continue
            if rohr and rohr["ok"]:
                n += bool(self.rohr_neu(dialog=rohr_dialog, dxf=(Path(pfad).name, rohr)))
                continue
            d = DxfImportDialog(self, self.db, pfad)
            if d.fehler:
                self.f.meldung(f"{Path(pfad).name}: {d.fehler}", fehler=True)
                continue
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                continue
            for e, kopf in d.ergebnisse():
                erg = blech.rechnen(e, werkstoffe, laser, einst)
                if erg["fehler"] or not erg.get("richtpreis"):
                    self.f.meldung(f"{kopf.get('bezeichnung') or Path(pfad).name}: " + "; ".join(erg["fehler"]
                                   or ["kein Richtpreis"]), fehler=True)
                    continue
                bez = kopf.get("bezeichnung") or blech.bezeichnung_vorschlag(e, erg["zuschnitt"])
                if self._blech_anlegen(e, erg, dict(bezeichnung=bez, artikelnr=None, stueck=kopf["stueck"],
                                                    lieferant=zukauf.lieferant_vorgabe("Blechteile"))):
                    n += 1
        if n > 1:
            self.f.meldung(f"{n} Positionen aus DXF angelegt.")
        return n

    @blaetterbar()
    def blech_bearbeiten(self, zeile=None, dialog=None):
        """Blech-Editor einer Position aus dem Blech-Editor wieder öffnen; der neue Richtpreis wird als EK ab der
        Stückzahl der Position im Artikel eingetragen. Ergebnis: True = übernommen."""
        from .blech_dialog import BlechDialog
        if zeile is None:
            zeile = self.pos_ansicht.currentIndex().row()
        if zeile is None or not 0 <= zeile < len(self.positionen):
            return False
        p = self.positionen[zeile]
        e = blech.lesen(p.get("technik"))
        liste = zukauf.json_liste(p.get("zukauf"))
        if e is None or not liste:
            self.f.meldung("Diese Position stammt nicht aus dem Blech-Editor.", fehler=True)
            return False
        lief = ((liste[0].get("stand") or {}).get("bezug") or {}).get("lieferant") or \
            zukauf.lieferant_vorgabe("Blechteile")
        d = BlechDialog(self, self.db, dict(e, stueck=p.get("stueck") or e.get("stueck")),
                        dict(bezeichnung=p.get("bezeichnung"), artikelnr=None, lieferant=lief,
                             stueck=p.get("stueck"), muster=p.get("muster")), neu=False)
        d.p = p                 # STEP speichern: Netz der Position für die Prüfung gegen die Mutter-STEP
        self._blaettern_einbauen(d, zeile, lambda: (d.eingaben(), d.kopf_werte()))
        if (dialog(d) if dialog else teile_editor.ausfuehren(d)) != QDialog.Accepted or not d.ergebnis.get("richtpreis"):
            return False
        e, erg, kopf = d.eingaben(), d.ergebnis, d.kopf_werte()
        self._blech_uebernehmen(p, e, erg, kopf["lieferant"], kopf["stueck"])
        if kopf.get("muster") != (p.get("muster") or None):     # Häkchen Muster (wie in allen Editoren)
            self.db.position_aendern(p["id"], "muster", kopf.get("muster"))
        self.neu_laden()
        self.f.meldung(f"Richtpreis {rechnen.zahl(erg['richtpreis'], 2)} € je Stück als EK übernommen.")
        return True

    def _blech_uebernehmen(self, p, e, erg, lieferant, stueck):
        """Eingaben e und Richtpreis erg des Blech-Editors in die Position p und als EK ab stueck in den Artikel."""
        liste = zukauf.json_liste(p.get("zukauf"))
        aid = liste[0].get("artikel_id")
        self.db.zukauf_ek_eintragen(aid, erg["richtpreis"], lieferant, ab=stueck,
                                    bemerkung=f"Richtpreis Blech-Editor (ab {stueck} St)")
        liste[0]["stand"] = self.db.zukauf_stand(aid, lieferant)
        ab = max(1, float(stueck or 1))      # gemerkte Richtpreise: so unterscheiden die Stufen sie vom EK
        merk = [r for r in (blech.lesen(p.get("technik")) or {}).get("richtpreise") or ()
                if isinstance(r, dict) and r.get("ab") != ab] + [dict(ab=ab, preis=erg["richtpreis"])]
        for feld, wert in (("technik", blech.speichern(dict(e, richtpreise=merk))), ("stueck", stueck),
                           ("gewicht_teil", round(erg["gewicht"], 3)),
                           ("zukauf", json.dumps(liste, ensure_ascii=False))):
            self.db.position_aendern(p["id"], feld, wert)
        if stueck != p.get("stueck") and p.get("id"):     # Satzposition: Stück je Satz folgt (31.10.2026)
            h = self.satz_nachziehen(p, "stueck", stueck)
            if h:
                self.f.meldung(h)

    def blech_gravur(self, p, hoehe):
        """Text-Gravur der Artikelnummer im Blechteil p setzen (hoehe > 0, Lage automatisch bzw. wie bisher) oder
        entfernen und den Richtpreis neu rechnen. Ergebnis: Hinweis oder None."""
        e = blech.lesen(p.get("technik"))
        liste = zukauf.json_liste(p.get("zukauf"))
        if e is None or not liste:
            return None
        text = str(p.get("artikel") or "").strip()
        alt = next((z for z in e.get("konturen") or () if z.get("art") == schneidweg.TEXT_GRAVUR and z.get("artikel")),
                   None)
        konturen = [z for z in e.get("konturen") or () if z is not alt]
        if hoehe and text:
            z = dict(alt or {}, art=schneidweg.TEXT_GRAVUR, anzahl=1, text=text, hoehe=hoehe, artikel=True)
            if alt is None or alt.get("text") != text or alt.get("hoehe") != hoehe:
                lage = blech.gravur_lage(dict(e, konturen=konturen), z) or {}
                z.update({n: lage[n] for n in ("x", "y", "winkel") if n in lage})
            konturen.append(z)
        if konturen == list(e.get("konturen") or ()):
            return None
        e = dict(e, konturen=konturen)
        werkstoffe = {z["blech_werkstoff_id"]: z for z in self.db.zeilen("blech_werkstoffe")
                      if z.get("blech_werkstoff_id")}
        stueck = p.get("stueck") or e.get("stueck")
        erg = blech.rechnen(dict(e, stueck=stueck), werkstoffe, self.db.zeilen("blechlaser"),
                            self.db.blech_einstellungen())
        if not erg.get("richtpreis"):
            return f"Pos. {p.get('pos') or ''}: Gravur nicht übernommen, " + " ".join(erg["fehler"])
        lief = ((liste[0].get("stand") or {}).get("bezug") or {}).get("lieferant") or \
            zukauf.lieferant_vorgabe("Blechteile")
        self._blech_uebernehmen(p, e, erg, lief, stueck)
        return "; ".join(f"Pos. {p.get('pos') or ''}: {h}" for h in erg["hinweise"] if "Gravur" in h) or None

    def zusatzarbeiten(self, zeilen=None, werte=None):
        """Gewinde und Zusatzarbeiten der markierten Positionen wählen (Dialog). werte = (Gewinde, JSON) setzt
        sie ohne Dialog (Tests, Bildschirmfotos). Ergebnis: True = gespeichert."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        if not zeilen:
            self.f.meldung("Bitte zuerst die Position(en) markieren.", fehler=True)
            return False
        # Mehrere Positionen (Plan Angebotsablauf V0): nur das Gemeinsame zeigen und ändern, eigene Werte bleiben
        vorher = zusatz_dialog.gemeinsam([self.positionen[r] for r in zeilen]) if len(zeilen) > 1 else None
        if werte is None:
            weitere = {}
            if len(zeilen) == 1 and not kein_laserteil(self.positionen[zeilen[0]]):
                weitere = {"Schweißnaht …": lambda: self.schweissnaht(list(zeilen)),
                           "Bohrungen prüfen …": lambda: self.bohrungen_pruefen(list(zeilen))}
            p = self.positionen[zeilen[0]]
            if vorher is not None:
                p = dict(p, gewinde=vorher[0] or "", zusatz=json.dumps(vorher[1], ensure_ascii=False))
            d = ZusatzDialog(self, p, len(zeilen), self.k, self.tabellen, self.db.zusatz_haeufigkeit(), weitere,
                             gewinde_verschieden=vorher is not None and vorher[0] is None, kopf=self.kopf)
            if d.exec() != QDialog.Accepted:
                return False
            werte = d.ergebnis
        for r in zeilen:
            p = self.positionen[r]
            gewinde, zusatz = werte if vorher is None else zusatz_dialog.zusammenfuehren(p, vorher, werte)
            self.db.position_aendern(p["id"], "gewinde", gewinde)
            self.db.position_aendern(p["id"], "zusatz", zusatz)
        self.f.meldung(f"Zusatzarbeiten für {len(zeilen)} Position(en) gespeichert.")
        self.neu_laden()
        return True

    def _doppelklick(self, i, auf_bild=None):
        """Doppelklick in der Positionsliste: Spalten mit eigenem Dialog; Status führt zur Lösung (STATUS_ZIELE);
        Schneidweg, Einstiche und STEP-Werte öffnen den Schneidweg-Rechner, bei einem Teil mit 3D-Daten das kleine
        STEP-Bild der Artikelnummer ebenfalls (auf_bild, ohne Angabe aus der Mausposition), die Nummer daneben die
        3D-Ansicht; das Bild einer selbst angelegten Position öffnet ihren Editor (Rechner bzw. Blech-Editor); sonst
        wird die Zelle bearbeitet."""
        if not i.isValid() or i.row() >= len(self.positionen):
            return
        art, name, r = self.pos_modell.spalten[i.column()][0], self.pos_modell.name(i.column()), i.row()
        p = self.positionen[r]
        if art == "status":
            self.status_beheben(r)
            return
        if ist_baugruppe(p) and art != "zukauf":
            self.baugruppe_bearbeiten([r])
            return
        if name == "satz" and p.get("satz") and not self.fremd():     # Satz (31.10.2026): Anzahl Sätze …
            from . import satz_menge
            if satz_menge.gehoert_zum_satz(p, self.positionen):
                self.satz_bearbeiten(r)
                return
        ziel = {"zusatz": self.zusatzarbeiten, "zukauf": self.zukaufteile, "naht": self.schweissnaht,
                "bohrbild": self.bohrungen_pruefen, "anbau": self.anbauteile_pruefen}.get(art)
        if ziel:
            ziel([r])
        elif ist_zukaufteil(p) and blech.lesen(p.get("technik")) and art != "zukauf" and not (
                name == "artikel" and p.get("id") in self.pos_modell.mit_netz and not self._auf_bild(i, auf_bild)):
            self.blech_bearbeiten(r)            # Blech (auch aus STEP): Editor; Nummer mit 3D-Modell: 3D-Ansicht
        elif (name in RECHNER_SPALTEN or art == "abweichung") and not kein_laserteil(p) \
                and p.get("profil_id") in self.k.profile:
            self.schneidweg_berechnen(r)
        elif name == "artikel" and (p.get("id") in self.pos_modell.mit_netz or self.pos_modell.vorschau(r)):
            auf_bild = self._auf_bild(i, auf_bild)
            rechner = not kein_laserteil(p) and p.get("profil_id") in self.k.profile
            if p.get("id") not in self.pos_modell.mit_netz and not auf_bild:
                if self.pos_modell.flags(i) & Qt.ItemIsEditable:     # selbst angelegt: Nummer bearbeiten
                    self.pos_ansicht.edit(i)
            elif auf_bild and rechner:
                self.schneidweg_berechnen(r)
            else:
                self.ansicht_3d(r)
        elif self.pos_modell.flags(i) & Qt.ItemIsEditable:
            self.pos_ansicht.edit(i)

    def _vorlagen_db(self):
        """Datenbank für Baugruppen-Vorlagen im Editor; im Lesemodus keine (Speichern schreibt)."""
        return None if self.db.nur_lesen else self.db

    # Rechtsklick (B5): Eintrag -> Arten, für die er erscheint (rohr, blech, zukauf, baugruppe); fehlt = immer
    MENUE_ARTEN = {"Schneidweg berechnen …": {"rohr"}, "Blech-Editor …": {"blech"},
                   "Baugruppe bearbeiten …": {"baugruppe"}, "Schweißnaht …": {"rohr"}, "Material …": {"rohr"},
                   "Bohrungen prüfen …": {"rohr"}, "Anbauteile prüfen …": {"rohr"},
                   "STEP-Merkmale prüfen …": {"rohr"}}

    def _markierte_zeilen(self):
        return sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()
                       if i.row() < len(self.positionen)})

    def position_art(self, p):
        """Art einer Position für Rechtsklick und Editoren: rohr, blech, zukauf oder baugruppe."""
        if ist_baugruppe(p):
            return "baugruppe"
        if ist_zukaufteil(p):
            return "blech" if blech.lesen(p.get("technik")) else "zukauf"
        return "rohr"

    def editor_art(self, p):
        """Welcher Editor eine Position bearbeitet (Blättern, B3): rohr (mit Profil), blech, baugruppe oder None."""
        art = self.position_art(p)
        if art == "rohr":
            return "rohr" if p.get("profil_id") in self.k.profile else None
        if art == "blech":
            return "blech" if zukauf.json_liste(p.get("zukauf")) else None
        return "baugruppe" if art == "baugruppe" else None

    def _blaettern_einbauen(self, d, zeile, zustand=None):
        """Knöpfe ◀ Vorige / Nächste ▶ (Alt+← / Alt+→) im Editor der Position in zeile (B3). Beim Wechsel werden
        Änderungen übernommen (F3a); ohne Änderung (zustand() wie beim Öffnen) schließt der Editor ohne Speichern.
        Der Titel zeigt Pos. und „n von m“ der Positionen dieser Art."""
        p = self.positionen[zeile] if 0 <= zeile < len(self.positionen) else None
        art = self.editor_art(p) if p else None
        reihe = [r for r, q in enumerate(self.positionen) if art and self.editor_art(q) == art]
        if zeile not in reihe or len(reihe) < 2:
            return None
        i = reihe.index(zeile)
        start = zustand() if zustand else None
        d.blaettern_knoepfe = {}

        def gehen(schritt):
            if not 0 <= i + schritt < len(reihe):
                return
            self._blaettern_ziel = reihe[i + schritt]
            if zustand is not None and zustand() == start:
                d.reject()                  # nichts geändert: nicht speichern (keine Rückfrage zu STEP-Werten)
            else:
                getattr(d, "_ok", d.accept)()           # wie OK: prüfen und Ergebnis setzen (Baugruppe, Schneidweg)
                if d.result() != QDialog.Accepted:      # Eingaben unvollständig: Editor bleibt offen
                    self._blaettern_ziel = None
        boxen = d.findChildren(QDialogButtonBox)
        for text, schritt, taste in (("◀ Vorige", -1, "Alt+Left"), ("Nächste ▶", 1, "Alt+Right")):
            b = QPushButton(text)
            b.setToolTip(f"{'Vorige' if schritt < 0 else 'Nächste'} Position dieser Art öffnen ({taste.replace('Left', '←').replace('Right', '→')}); "
                         "Änderungen werden übernommen")
            b.setEnabled(0 <= i + schritt < len(reihe))
            b.clicked.connect(lambda _=False, s=schritt: gehen(s))
            QShortcut(QKeySequence(taste), d, activated=lambda s=schritt: gehen(s))
            if boxen:
                boxen[0].addButton(b, QDialogButtonBox.ResetRole)
            d.blaettern_knoepfe[schritt] = b
        d.setWindowTitle(f"{d.windowTitle()} – Pos. {p.get('pos') or ''} ({i + 1} von {len(reihe)})")
        return reihe

    def _pos_menue_anpassen(self):
        """Rechtsklick-Menü passend zu den markierten Positionen (B5)."""
        zeilen = self._markierte_zeilen()
        arten = {self.position_art(self.positionen[r]) for r in zeilen}
        mit_bg = any(ist_baugruppe(self.positionen[r]) or baugruppe.zuordnung(self.positionen[r])[0] for r in zeilen)
        mit_satz = any(self.positionen[r].get("satz") for r in zeilen)
        mit_virtuell = any(virtuell.technik_lesen(self.positionen[r]) for r in zeilen)
        for text, a in self.pos_aktionen.items():
            noetig = self.MENUE_ARTEN.get(text)
            sichtbar = not zeilen or noetig is None or bool(arten & noetig)
            if text in ("Satz in 3D …", "Satz bearbeiten (Anzahl Sätze) …"):
                sichtbar = mit_satz
            elif text == "Baugruppe in anderes Angebot kopieren …":
                sichtbar = mit_bg
            elif text in ("Virtuelles Bauteil als STEP …", "Stege abtrennen an/aus"):
                sichtbar = mit_virtuell
            elif text == "Für markierte setzen …":
                sichtbar = len(zeilen) > 1 and "rohr" in arten
            elif text in ("Position duplizieren", "Positionen aus anderem Angebot übernehmen …"):
                sichtbar = text != "Position duplizieren" or bool(zeilen)
            elif text == "Muster an/aus" and not funktionen.an("funktion_muster"):
                sichtbar = any(ist_muster(self.positionen[r]) for r in zeilen)     # vorhandene Muster zurücknehmen
            elif text == "Schweißnaht …" and not funktionen.an("funktion_schweissen"):
                sichtbar = False
            a.setVisible(sichtbar)
        return [t for t, a in self.pos_aktionen.items() if a.isVisible()]

    def fuer_markierte_setzen(self, zeilen=None, werkstoff=None, oberflaeche=None, dialog=None):
        """Werkstoff und/oder Oberfläche für alle markierten Rohrlaserteile auf einmal setzen (B5), ein Schritt für
        Rückgängig. Ohne Werte fragt ein kleiner Dialog; dialog(d) bedient ihn statt exec (Tests). Ergebnis: Anzahl
        geänderter Positionen oder None (abgebrochen)."""
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return None
        zeilen = [r for r in (zeilen if zeilen is not None else self._markierte_zeilen())
                  if self.position_art(self.positionen[r]) == "rohr"]
        if not zeilen:
            self.f.meldung("Bitte zuerst Rohrlaserteile markieren.", fehler=True)
            return None
        if werkstoff is None and oberflaeche is None:
            from .fenster import liste_fuellen
            d = QDialog(self)
            d.setWindowTitle(f"Für {len(zeilen)} markierte Positionen setzen")
            form = QFormLayout(d)
            ws, ob = QComboBox(), QComboBox()
            liste_fuellen(ws, self.k, "werkstoff", "(nicht ändern)")
            liste_fuellen(ob, self.k, "oberflaeche", "(nicht ändern)")
            ob.insertItem(1, "(ohne Oberfläche)")
            form.addRow("Werkstoff-ID", ws)
            form.addRow("Oberfläche", ob)
            knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            knoepfe.accepted.connect(d.accept)
            knoepfe.rejected.connect(d.reject)
            form.addRow(knoepfe)
            d.ws, d.ob = ws, ob
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                return None
            werkstoff = ws.currentText() if ws.currentIndex() > 0 else None
            oberflaeche = ("" if ob.currentIndex() == 1 else ob.currentText()) if ob.currentIndex() > 0 else None
        n = 0
        for r in zeilen:
            p = self.positionen[r]
            neu = False
            if werkstoff is not None and p.get("werkstoff_id") != werkstoff:
                self.db.position_aendern(p["id"], "werkstoff_id", werkstoff)
                neu = True
            if oberflaeche is not None and (p.get("oberflaeche") or "") != oberflaeche:
                self.db.position_aendern(p["id"], "oberflaeche", oberflaeche or None)
                neu = True
            n += neu
        if n:
            self.neu_laden()
            self.rueckgaengig_anbieten(f"{n} Position(en) geändert"
                                       + (f": Werkstoff {werkstoff}" if werkstoff is not None else "")
                                       + (f", Oberfläche {oberflaeche or 'ohne'}" if oberflaeche is not None else "")
                                       + ".")
        else:
            self.f.meldung("Nichts geändert: die markierten Positionen haben diese Werte schon.")
        return n

    def _menue_zeile(self, punkt):
        """Rechtsklick auf eine nicht markierte Zeile: diese Zeile markieren, damit das Menü für sie gilt."""
        i = self.pos_ansicht.indexAt(punkt)
        if i.isValid() and i.row() not in {x.row() for x in self.pos_ansicht.selectedIndexes()}:
            self.pos_ansicht.setCurrentIndex(i)

    def baugruppe_kopieren(self, zeilen=None, ziel=None):
        """Schweißbaugruppe der Zeile (oder des Einzelteils) mit allen Einzelteilen in ein anderes Angebot kopieren
        (P7): neue Kennung, Zuordnung der Teile mitgenommen, Pos.-Nummern hinter den vorhandenen, 3D-Modelle mit.
        ziel = Angebots-ID (sonst Auswahl). Ergebnis: Anzahl kopierter Positionen (0 = nichts kopiert)."""
        if self.db.nur_lesen:
            self.f.meldung("Im Lesemodus kann nichts kopiert werden.", fehler=True)
            return 0
        zeilen = zeilen if zeilen is not None else sorted({i.row() for i in self.pos_ansicht.selectedIndexes()})
        if not zeilen or zeilen[0] >= len(self.positionen):
            self.f.meldung("Bitte eine Schweißbaugruppe oder eines ihrer Teile markieren.", fehler=True)
            return 0
        p = self.positionen[zeilen[0]]
        bg_id = (baugruppe.lesen(p.get("baugruppe")) or {}).get("id") if ist_baugruppe(p) else baugruppe.zuordnung(p)[0]
        if not bg_id or bg_id not in baugruppe.baugruppen(self.positionen):
            self.f.meldung("Bitte eine Schweißbaugruppe oder eines ihrer Teile markieren.", fehler=True)
            return 0
        if ziel is None:
            andere = [a for a in self.db.angebote() if a["id"] != self.id and not a.get("fremd")]
            if not andere:
                self.f.meldung("Es gibt kein anderes eigenes Angebot.", fehler=True)
                return 0
            texte = [f"{a.get('nummer') or a['id']}  {a.get('kunde') or ''}".strip() for a in andere]
            wahl, ok = QInputDialog.getItem(self, "Baugruppe kopieren", "In welches Angebot?", texte, 0, False)
            if not ok:
                return 0
            ziel = andere[texte.index(wahl)]["id"]
        vorhanden = [q.get("pos") for q in self.db.positionen(ziel) if isinstance(q.get("pos"), (int, float))]
        neu = baugruppe.kopie(self.positionen, bg_id, int(max(vorhanden, default=0)) + 10)
        netze = self.db.netze(self.id)
        for alt, werte in neu:
            i = self.db.position_neu(ziel, werte)
            if alt.get("id") in netze:
                self.db.netz_speichern(i, netze[alt["id"]])
        nummer = (self.db.angebot(ziel) or {}).get("nummer") or ziel
        self.f.meldung(f"Schweißbaugruppe mit {len(neu) - 1} Einzelteil(en) in Angebot {nummer} kopiert.")
        return len(neu)

    # -------------------------------------------------------------- Position als neue Position kopieren (30.10.2026)
    def position_duplizieren(self, zeilen=None):
        """Markierte Positionen im selben Angebot als neue Positionen kopieren (position_kopie.py): alles, was zur
        Position gehört, eindeutige Artikelnummer; eine Position bzw. Gruppe direkt hinter das Original, wenn dort
        Positionsnummern frei sind, sonst ans Ende. Ergebnis: Anzahl neuer Positionen (0 = nichts kopiert)."""
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen. Zum Weiterarbeiten das Angebot kopieren.",
                           fehler=True)
            return 0
        zeilen = self._markierte_zeilen() if zeilen is None else list(zeilen)
        einheiten = position_kopie.einheiten(self.positionen, zeilen)
        if not einheiten:
            self.f.meldung("Bitte zuerst die Position markieren, die kopiert werden soll.", fehler=True)
            return 0
        return self._kopien_einfuegen(self.id, self.positionen, einheiten, gleiches=True)

    def positionen_uebernehmen(self, quelle=None, zeilen=None, staffeln=True, dialog=None):
        """Positionen aus einem anderen Angebot (auch eines Kollegen oder festgeschrieben, wird nur gelesen) als neue
        Positionen ans Ende übernehmen. Ohne quelle: Auswahl im Fenster (position_kopie_dialog); dialog(d) bedient es
        statt exec (Tests). Ergebnis: Anzahl neuer Positionen (0 = nichts übernommen)."""
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return 0
        if quelle is None:
            from .position_kopie_dialog import UebernehmenDialog
            d = UebernehmenDialog(self, self.db, self.id)
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or not d.quelle:
                return 0
            quelle, zeilen, staffeln = d.quelle, d.zeilen, d.staffeln
        if quelle == self.id:
            return self.position_duplizieren(zeilen)
        positionen = self.db.positionen(quelle)
        einheiten = position_kopie.einheiten(positionen, zeilen or [])
        if not einheiten:
            self.f.meldung("Keine Position gewählt.", fehler=True)
            return 0
        return self._kopien_einfuegen(quelle, positionen, einheiten, gleiches=False, staffeln=staffeln)

    def _kopien_einfuegen(self, quelle_id, quelle, einheiten, gleiches, staffeln=True):
        """Kopien der Einheiten (position_kopie.einheiten) aus dem Angebot quelle_id anlegen: Positionen, 3D-Netze,
        Daten „Satz in 3D“, Staffeln; ein Schritt für Rückgängig. Ergebnis: Anzahl neuer Positionen."""
        paare, saetze = position_kopie.kopien(quelle, einheiten, self.positionen, gleiches)
        if not paare:
            return 0
        original = None
        if gleiches and len(einheiten) == 1 and reihenfolge.aufsteigend(self.positionen):
            i0 = einheiten[0][1][0]
            block = next((ix for _, ix in reihenfolge.bloecke(self.positionen) if i0 in ix), [i0])
            nummern = [self.positionen[i].get("pos") for i in block
                       if isinstance(self.positionen[i].get("pos"), (int, float))]
            frei = position_kopie.luecke(self.positionen, max(nummern), len(paare)) if nummern else None
            if frei:
                for (_, w), n in zip(paare, frei):
                    w["pos"] = n
                original = self.positionen[i0]["id"]
        self.verlauf.pause += 1         # Anlegen und Einordnen: ein Schritt für Rückgängig
        try:
            neue = self._kopien_schreiben(quelle_id, paare, saetze, staffeln, original)
        finally:
            self.verlauf.pause -= 1
        zeilen = [k for k, p in enumerate(self.positionen) if p["id"] in set(neue)]
        if zeilen:
            self.zur_position(zeile=zeilen[0])
            auswahl = self.pos_ansicht.selectionModel()
            for r in zeilen:
                auswahl.select(self.pos_modell.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        if gleiches:
            artikel = [w.get("artikel") for _, w in paare if w.get("artikel")]
            text = (f"{position_kopie.text(paare)} als Kopie angelegt"
                    + (f" (Artikel {', '.join(artikel[:3])}{' …' if len(artikel) > 3 else ''})" if artikel else "")
                    + (", direkt hinter dem Original." if original is not None else ", am Ende."))
        else:
            nummer = (self.db.angebot(quelle_id) or {}).get("nummer") or quelle_id
            text = f"{position_kopie.text(paare)} aus Angebot {nummer} übernommen."
        self.rueckgaengig_anbieten(text)
        return len(paare)

    def _kopien_schreiben(self, quelle_id, paare, saetze, staffeln, original):
        """Teil von _kopien_einfuegen: Positionen, Netze, Satz in 3D und Staffeln schreiben, dann (original = ID)
        hinter das Original einordnen. Ergebnis: neue Positions-IDs."""
        netze = self.db.netze(quelle_id)
        neue = []
        for alt, w in paare:
            pid = self.db.position_neu(self.id, w)
            neue.append(pid)
            if alt.get("id") in netze:
                self.db.netz_speichern(pid, netze[alt["id"]])
        daten = self.db.satz_daten(quelle_id)
        for alt_name, neu_name in saetze.items():
            if daten.get(alt_name):
                self.db.satz_daten_speichern(self.id, neu_name, daten[alt_name])
        if staffeln:
            for stufe, mengen in position_kopie.staffeln_kopieren(self.db.staffeln(quelle_id),
                                                                  self.db.staffel_stufen(quelle_id), paare, saetze):
                sid = self.db.staffel_stufe_neu(self.id, stufe)
                for z in mengen:
                    self.db.staffel_neu(self.id, dict(z, stufe_id=sid))
        self.neu_laden()
        if original is not None:
            ix = {p["id"]: k for k, p in enumerate(self.positionen)}
            folge = position_kopie.folge_dahinter(self.positionen, neue, ix[original])
            self.db.positionen_ordnen(self.id, [(pid, self.positionen[ix[pid]].get("pos")) for pid in folge])
            self.neu_laden()
        return neue

    def _baugruppen_kosten(self):
        """Kostenbalken je Schweißbaugruppe für die Übersicht (D2): Titel, Kostenteile und größte Posten je Baugruppe."""
        out, saetze = [], None
        for p in self.positionen:
            if not ist_baugruppe(p) or baugruppe.daten_fehler(p.get("baugruppe")):
                continue
            saetze = saetze if saetze is not None else self._saetze()
            r = baugruppe.rechnen(p, self.tabellen, saetze, None,
                                  bg_mengen.je_knoten(baugruppe.lesen(p.get("baugruppe")), self.positionen, self.k))
            out.append((f"Pos. {p.get('pos') or ''} {baugruppe.name(p)}".strip(), baugruppe.kostenaufteilung(r),
                        baugruppe.groesste_posten(r)))
        return out

    def baugruppe_neu(self, dialog=None):
        """Neue Schweißbaugruppe im Editor anlegen; markierte Positionen sind als Einzelteile vorgewählt.
        dialog(d) bedient den Editor statt exec (Tests). Ergebnis: True = angelegt."""
        markiert = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        vorwahl = {self.positionen[r]["id"] for r in markiert if r < len(self.positionen)
                   and not ist_baugruppe(self.positionen[r]) and not self.positionen[r].get("bg_knoten")}
        p = dict(pos=self._naechste_pos(), art=BAUGRUPPE, stueck=1)
        d = BaugruppeDialog(self, p, self.positionen, self.tabellen, self._saetze(), vorwahl, db=self._vorlagen_db(),
                            einstellungen=self._vk_einstellungen(), netze=self.db.netze(self.id),
                            profile=self.k.profile)
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or not d.ergebnis:
            return False
        vorab = self.teilen_anwenden(d.ergebnis)
        werte = dict(d.ergebnis["position"], pos=p["pos"])
        pid = self.db.position_neu(self.id, {k_: v for k_, v in werte.items() if v is not None})
        hinweise = vorab + self._baugruppe_teile(d.ergebnis["teile"], None)
        self.naehte_schreiben(d.ergebnis.get("naehte"))
        hinweise += self.stecken_anwenden(d.ergebnis.get("stecken"))
        hinweise += self.knicke_anwenden(d.ergebnis.get("knicke"))
        self.neu_laden()
        self.f.meldung(f"Schweißbaugruppe Pos. {p['pos']} angelegt." + "".join(f" {h}" for h in hinweise))
        self.zur_position(zeile=next((r for r, x in enumerate(self.positionen) if x["id"] == pid), None))
        return True

    @blaetterbar(liste=True)
    def baugruppe_bearbeiten(self, zeilen, dialog=None, fokus=None):
        """Editor der Schweißbaugruppe in der Zeile; bei einem Einzelteil der Editor seiner Baugruppe.
        fokus: Status, dessen Zeile der Editor zeigt (Doppelklick auf den Status). Ergebnis: True = gespeichert."""
        p = self.positionen[zeilen[0]]
        if fokus and not ist_baugruppe(p):
            fokus = f"Pos. {p.get('pos') or ''}: {fokus}"
        if not ist_baugruppe(p):
            bg_id = baugruppe.zuordnung(p)[0]
            ziel = baugruppe.baugruppen(self.positionen).get(bg_id)
            if ziel is None:
                self.f.meldung("Die Baugruppe dieser Position gibt es nicht mehr: Spalte 'Baugruppe (Zuordnung)' "
                               "leeren oder das Teil im Editor einer Baugruppe neu zuordnen.", fehler=True)
                return False
            p = self.positionen[ziel[0]]
        d = BaugruppeDialog(self, p, self.positionen, self.tabellen, self._saetze(), db=self._vorlagen_db(),
                            nur_lesen=bool(self.fremd() or self.db.nur_lesen), einstellungen=self._vk_einstellungen(),
                            netze=self.db.netze(self.id), profile=self.k.profile)
        if fokus:
            d.fokus(fokus)
        self._blaettern_einbauen(d, next(r for r, q in enumerate(self.positionen) if q["id"] == p["id"]))
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or not d.ergebnis or d.nur_lesen:
            return False
        alt_name = baugruppe.name(p)
        vorab = self.teilen_anwenden(d.ergebnis)
        for feld, wert in d.ergebnis["position"].items():
            if p.get(feld) != wert:
                self.db.position_aendern(p["id"], feld, wert)
        hinweise = vorab + self._baugruppe_teile(d.ergebnis["teile"], alt_name)
        self.naehte_schreiben(d.ergebnis.get("naehte"))
        hinweise += self.stecken_anwenden(d.ergebnis.get("stecken"))
        hinweise += self.knicke_anwenden(d.ergebnis.get("knicke"))
        self.neu_laden()
        self.f.meldung(f"Schweißbaugruppe Pos. {p.get('pos') or ''} gespeichert." + "".join(f" {h}" for h in hinweise))
        return True

    def _baugruppe_teile(self, teile, alt_name):
        """Zuordnung der Einzelteile schreiben; ein herausgenommenes Teil verliert auch Satz und Stück je Satz der
        Baugruppe (Satz und Stückzahlen setzt danach _baugruppen_abgleichen)."""
        nach_id = {q["id"]: q for q in self.positionen}
        hinweise = []
        for pid, z in teile.items():
            for feld, wert in z.items():
                self.db.position_aendern(pid, feld, wert)
            if "bg_gravur" in z and nach_id.get(pid):     # Blechteil: Gravur als Zeile des Blech-Editors
                h = self.blech_gravur(dict(nach_id[pid], bg_gravur=z["bg_gravur"]), z["bg_gravur"])
                if h:
                    hinweise.append(h)
            q = nach_id.get(pid) or {}
            if z.get("bg_knoten") is None and q.get("bg_knoten") and (q.get("satz") or None) in (alt_name, None):
                self.db.position_aendern(pid, "satz", None)
                self.db.position_aendern(pid, "je_satz", None)
        return hinweise

    def _vk_einstellungen(self):
        return {n: self.db.einstellung(n) for n in ("schweiss_vk_satz", "schweiss_vk_satz_nacharbeit", "gravur_artikel",
                                                    "gravur_schrifthoehe", "schweiss_vk_step", "schweiss_a_regel",
                                                    "steck_anzahl", "steck_nase_min", "steck_nase_rand", "knick_z", "knick_freistich",
                                                    "knick_k",
                                                    "steck_spiel", "steck_ueberstand", "steck_marke", "step_naht_spalt")}

    def naehte_schreiben(self, naehte):
        """Längsnähte aus dem 3D (Längsnaht per Klick) in die Positionen: {Positions-ID: Nahtfelder}."""
        for pid, felder in (naehte or {}).items():
            for name, wert in felder.items():
                self.db.position_aendern(pid, name, wert)

    def stecken_anwenden(self, stecken):
        """Steckverbindungen aus dem Editor der Baugruppe in die Teile schreiben (stecken = dict(weg, dazu) aus
        steckverbindung.aenderungen): Schlitze in die Aufnahme, Nasen an das Ende des Steckers, Schneidweg neu,
        Länge des Steckers um die Nasen länger (bzw. wieder kürzer). Ergebnis: Hinweise."""
        from . import steckverbindung as sv
        if not stecken or not (stecken.get("weg") or stecken.get("dazu")):
            return []
        self.neu_laden()
        nach_id = {q["id"]: q for q in self.positionen}
        eing, laenge, hinweise = {}, {}, []

        def eingaben(pid):
            if pid not in eing:
                q = nach_id[pid]
                profil = self.k.profile.get(q.get("profil_id")) or {}
                eing[pid] = schneidweg.aus_position(schneidweg.lesen(q.get("technik")), q, profil)[0]
                laenge[pid] = 0.0
            return eing[pid]
        for v in stecken.get("weg") or ():
            for pid in {q["id"] for q in self.positionen if v["id"] in sv.rollen(q.get("technik"))}:
                eing[pid], weniger = sv.entfernen(eingaben(pid), v["id"])
                laenge[pid] -= weniger
        for v in stecken.get("dazu") or ():
            a, s_ = (v.get("aufnahme") or {}).get("id"), (v.get("stecker") or {}).get("id")
            if a not in nach_id or s_ not in nach_id:
                hinweise.append(f"Steckverbindung {v['id']}: Teil fehlt, nicht übernommen")
                continue
            pa, ps = (self.k.profile.get(nach_id[x].get("profil_id")) or {} for x in (a, s_))
            try:
                ea, es = eingaben(a), eingaben(s_)
                lg = [nach_id[x].get("laenge") for x in (a, s_)]
                lg = [g + laenge[x] if isinstance(g, (int, float)) else None for g, x in zip(lg, (a, s_))]
                eing[a], eing[s_], plus = sv.anwenden(v, ea, es, pa, ps, lg, hinweise)
            except ValueError as f:
                hinweise.append(f"Steckverbindung Pos. {nach_id[a].get('pos') or ''}/{nach_id[s_].get('pos') or ''}: {f}")
                continue
            laenge[s_] += plus
        for pid, e in eing.items():
            zeile = next((r for r, q in enumerate(self.positionen) if q["id"] == pid), None)
            if zeile is None:
                continue
            if laenge[pid] and isinstance(self.positionen[zeile].get("laenge"), (int, float)):
                self.db.position_aendern(pid, "laenge", round(self.positionen[zeile]["laenge"] + laenge[pid], 1))
                self.neu_laden()
                zeile = next(r for r, q in enumerate(self.positionen) if q["id"] == pid)
            alt_stumm, self.f.stumm = self.f.stumm, True
            try:
                ok = self.schneidweg_berechnen(zeile, e, ueberschreiben=True)
            finally:
                self.f.stumm = alt_stumm
            if not ok:
                hinweise.append(f"Pos. {self.positionen[zeile].get('pos') or ''}: Steckverbindung, Schneidweg nicht "
                                "gerechnet (Schneidweg-Rechner öffnen)")
        n = len(stecken.get("dazu") or ())
        if n:
            hinweise.append(f"{n} Steckverbindung(en) in die Teile geschrieben (Schlitze und Nasen).")
        return hinweise

    def teilen_anwenden(self, ergebnis):
        """Gleiche Teile mit anderer Lage der Nasen oder Schlitze in eigene Positionen (Alle Stöße stecken, Patrick
        25.10.2026; ergebnis['teilen'] = [dict(von, neu, koerper)]): je Eintrag eine Kopie der Position mit diesen
        Körpern (je Satz, Stück, Netz), die alte zählt sie nicht mehr. Die vorläufigen IDs '<ID>~<n>' im Ergebnis des
        Editors werden durch die neuen ersetzt (in place). Ergebnis: Hinweise."""
        from .ansicht3d import entpacken, packen
        hinweise = []
        for pid, lagen in ((ergebnis or {}).get("lagen") or {}).items():     # gedreht/gewendet eingebaute gleiche Rohre
            netz = entpacken(self.db.netz(pid))
            if not netz or not lagen:
                continue
            koerper = [str(k) for k in netz.get("koerper") or ()]
            alt = netz.get("lagen") or ([netz["lage"]] if netz.get("lage") else [])
            if len(alt) != len(koerper):
                continue
            neu = [lagen.get(k, alt[j]) for j, k in enumerate(koerper)]
            self.db.netz_speichern(pid, packen(dict(netz, lagen=neu, lage=neu[0])))
        teilen = (ergebnis or {}).get("teilen") or []
        if not teilen:
            return hinweise
        self.neu_laden()
        karte = {}
        nr = int(max((q["pos"] for q in self.positionen if isinstance(q.get("pos"), (int, float))), default=0))
        for t in teilen:
            q = next((x for x in self.positionen if x["id"] == t["von"]), None)
            netz = entpacken(self.db.netz(t["von"])) if q else None
            if not netz:
                continue
            lagen = netz.get("lagen") or ([netz["lage"]] if netz.get("lage") else [])
            koerper = [str(k) for k in netz.get("koerper") or ()]
            idx = [koerper.index(str(k)) for k in t["koerper"] if str(k) in koerper]
            rest = [j for j in range(len(koerper)) if j not in idx]
            if not idx or not rest:
                continue
            je_alt = q.get("je_satz") or len(koerper)
            je = len(idx)
            saetze_ = q["stueck"] / je_alt if isinstance(q.get("stueck"), (int, float)) and je_alt else None
            werte = {n: w for n, w in q.items() if n not in ("id", "nr", "angebot_id")}
            nr += 10
            werte.update(pos=nr, je_satz=je if q.get("satz") else None,
                         stueck=round(saetze_ * je) if saetze_ else q.get("stueck"))
            if isinstance(q.get("je_knoten"), (int, float)) and q["je_knoten"] > 0:
                werte["je_knoten"] = max(1, round(q["je_knoten"] * je / je_alt))
            pid = self.db.position_neu(self.id, werte)
            for n_, liste in (("neu", idx), ("alt", rest)):
                teil = dict(netz, lage=lagen[liste[0]], koerper=[netz["koerper"][j] for j in liste])
                if len(liste) > 1:
                    teil["lagen"] = [lagen[j] for j in liste]
                else:
                    teil.pop("lagen", None)
                self.db.netz_speichern(pid if n_ == "neu" else t["von"], packen(teil))
            je_rest = je_alt - je
            self.db.position_aendern(t["von"], "je_satz", je_rest if q.get("satz") else q.get("je_satz"))
            if saetze_:
                self.db.position_aendern(t["von"], "stueck", round(saetze_ * je_rest))
            if isinstance(q.get("je_knoten"), (int, float)) and q["je_knoten"] > 0:
                self.db.position_aendern(t["von"], "je_knoten", max(1, q["je_knoten"] - werte["je_knoten"]))
            karte[t["neu"]] = pid
            hinweise.append(f"Pos. {q.get('pos') or ''} geteilt: {je} Stück mit anderen Nasen/Schlitzen als Pos. {nr}.")
            self.neu_laden()
        if karte:
            ergebnis.update({n: _ids_ersetzen(w, karte) for n, w in ergebnis.items() if n not in ("teilen", "lagen")})
        return hinweise

    def knicke_anwenden(self, knicke):
        """Neue Knickrahmen aus dem Fenster „Satz in 3D“ (knicke = [dict(koerper, leit, eingaben, netz, text)]):
        je Rahmen eine Position wie das Leitteil mit dem gestreckten Rohr (Schneidweg-Rechner, Länge, Zusatzarbeit
        Knicken) und dem gefalteten Netz; gleiche Rahmen werden eine Position mit „je Satz“ = Anzahl. Die Rohre
        zählen je Satz weniger, ohne übrige Körper fällt die Position weg. Ergebnis: Hinweise."""
        from .ansicht3d import entpacken, packen
        if not knicke:
            return []
        self.neu_laden()
        nach_id = {q["id"]: q for q in self.positionen}
        gruppen = {}
        for k in knicke:
            if k["leit"] in nach_id:
                gruppen.setdefault(json.dumps([k["leit"], k["eingaben"]], sort_keys=True, default=str), []).append(k)
        verbraucht = {}
        for k in knicke:
            for pid, j in k["koerper"]:
                verbraucht.setdefault(pid, set()).add(j)

        def saetze(q):
            je, st = q.get("je_satz") or 1, q.get("stueck")
            return st / je if isinstance(st, (int, float)) and je else None

        def je_knoten(q, je):
            """Stück je Unterbaugruppe (Teil einer Schweißbaugruppe) im Verhältnis zu je Satz."""
            alt, js = q.get("je_knoten"), q.get("je_satz") or 1
            return max(1, round(alt * je / js)) if isinstance(alt, (int, float)) and alt > 0 else alt
        hinweise, nr = [], int(max((q["pos"] for q in self.positionen if isinstance(q.get("pos"), (int, float))),
                                   default=0))
        for gr in gruppen.values():
            q = nach_id[gr[0]["leit"]]
            werte = {n: w for n, w in q.items() if n not in ("id", "nr", "angebot_id")}
            nr += 10
            s_ = saetze(q)
            werte.update(pos=nr, je_satz=len(gr) if q.get("satz") else None,
                         stueck=round(s_ * len(gr)) if s_ else q.get("stueck"), je_knoten=je_knoten(q, len(gr)))
            pid = self.db.position_neu(self.id, werte)
            netz = entpacken(gr[0]["netz"]) if gr[0].get("netz") else None
            if netz:
                if len(gr) > 1:         # Lage je Körper passend zum Netz des ersten (gedreht/gewendet eingebaut)
                    from .lage_abgleich import lagen_abgleichen
                    netz["lagen"] = lagen_abgleichen(netz, [entpacken(k["netz"]) or {} for k in gr])
                nummern = [x for k in gr for x in k.get("nummern") or ()]
                if nummern:             # Körper der Schenkel: Nahtgruppen und Stöße finden das Teil
                    netz["koerper"] = nummern
                self.db.netz_speichern(pid, packen(netz))
            self.neu_laden()
            zeile = next(r for r, x in enumerate(self.positionen) if x["id"] == pid)
            alt_stumm, self.f.stumm = self.f.stumm, True
            try:
                ok = self.schneidweg_berechnen(zeile, gr[0]["eingaben"], ueberschreiben=True)
            finally:
                self.f.stumm = alt_stumm
            hinweise.append(f"Pos. {nr}: {gr[0]['text']}" + (f", {len(gr)} je Satz" if len(gr) > 1 else "") + "."
                            + ("" if ok else " Schneidweg nicht gerechnet (Schneidweg-Rechner öffnen)."))
        weg = []
        for pid, nrs in verbraucht.items():
            q = nach_id.get(pid)
            if q is None:
                continue
            netz = entpacken(self.db.netz(pid)) or {}
            lagen = netz.get("lagen") or ([netz["lage"]] if netz.get("lage") else [])
            rest = [j for j in range(len(lagen)) if j not in nrs]
            je = (q.get("je_satz") or len(lagen) or 1) - len(nrs)
            if je <= 0 or not rest:
                weg.append(pid)
                continue
            s_ = saetze(q)
            if q.get("bg_knoten") and q.get("je_knoten"):
                self.db.position_aendern(pid, "je_knoten", je_knoten(q, je))
            self.db.position_aendern(pid, "je_satz", je)
            if s_:
                self.db.position_aendern(pid, "stueck", round(s_ * je))
            koerper = netz.get("koerper") or []
            netz["lage"] = lagen[rest[0]]
            if len(rest) > 1:
                netz["lagen"] = [lagen[j] for j in rest]
            else:
                netz.pop("lagen", None)
            if len(koerper) == len(lagen):
                netz["koerper"] = [koerper[j] for j in rest]
            self.db.netz_speichern(pid, packen(netz))
            hinweise.append(f"Pos. {q.get('pos') or ''}: {je} je Satz (übrige im Knickrahmen).")
        if weg:
            self.db.positionen_loeschen(weg)
            hinweise.append("Im Knickrahmen aufgegangen und entfernt: Pos. "
                            + ", ".join(str(nach_id[p].get("pos") or "") for p in weg) + ".")
        self.neu_laden()
        self._baugruppen_abgleichen()           # Teile einer Schweißbaugruppe: Satz und Stück folgen der Struktur
        return hinweise

    def gravur_vorgeben(self, pos, bericht):
        """Einstellung gravur_artikel = ja nach dem STEP-Import: Artikelnummer auf alle Bleche und Rohre der neuen
        Schweißbaugruppen (Pos.-Nummern pos) gravieren, die noch keine Wahl haben."""
        from .baugruppe_dialog import gravierbar
        h = self.db.einstellung("gravur_schrifthoehe") or 10
        ids = {baugruppe.lesen(p.get("baugruppe")).get("id") for p in self.positionen if ist_baugruppe(p)
               and p.get("pos") in pos and baugruppe.lesen(p.get("baugruppe"))} - {None}
        n = 0
        for q in self.positionen:
            if baugruppe.zuordnung(q)[0] not in ids or q.get("bg_gravur") is not None or not gravierbar(q):
                continue
            self.db.position_aendern(q["id"], "bg_gravur", float(h))
            hinweis = self.blech_gravur(dict(q, bg_gravur=h), h)
            if hinweis:
                bericht.append(hinweis)
            n += 1
        if n:
            bericht.append(f"Gravur Artikelnummer (Einstellung): {n} Teil(e) der Schweißbaugruppe(n)")
            self.neu_laden()

    def _vorkalkulieren(self, pos, bericht):
        """Vorkalkulation der neuen Schweißbaugruppen (Pos.-Nummern pos) nach dem STEP-Import (Einstellung
        schweiss_vk_step): Vorschläge in die Baugruppe schreiben, Ergebnis in den Bericht."""
        einst = self._vk_einstellungen()
        for p in [p for p in self.positionen if ist_baugruppe(p) and p.get("pos") in pos]:
            r = vorkalk.komplett(p, self.positionen, self.tabellen, einst, self.k)
            if r["bg"] is None:
                continue
            r["bg"]["stamm"]["vk_auto"] = True
            self.db.position_aendern(p["id"], "baugruppe", baugruppe.speichern(r["bg"]))
            bericht.append(f"Schweißbaugruppe {baugruppe.name(p)}: Vorkalkulation, {len(r['aenderungen'])} "
                           "Vorschläge" + (", " + "; ".join(r["hinweise"]) if r["hinweise"] else ""))
        self.neu_laden()

    def _saetze(self):
        return rechnen.zeitbasis(self.kopf, self.k, self.tabellen)["saetze"]

    def laser_teil_eur(self, q, eingaben=None, laenge=None):
        """Laserkosten je Teil für den €-Vergleich der Vorschläge (Plan Baugruppen automatisch, P1): Schneidweg-Rechner
        mit den Eingaben (ohne: die der Position), Schneidzeit mit den Schneiddaten des Angebots × Stundensatz
        Maschine. Ergebnis (€ oder None, Grund)."""
        profil = self.k.profile.get(q.get("profil_id"))
        if not profil:
            return None, "Profil fehlt in den Stammdaten"
        if eingaben is None:
            try:
                eingaben = schneidweg.aus_position(schneidweg.lesen(q.get("technik")), q, profil)[0]
            except (ValueError, TypeError, KeyError) as f:
                return None, str(f)
        profil = rechnen.profil_im_angebot(profil, self.kopf, q.get("profil_id"), q.get("werkstoff_id"), self.k)
        m = rechnen.maschine(self.kopf, self.k)
        erg = schneidweg.rechnen(eingaben, profil, rechnen.kontur_regel(m, rechnen.wand_schneiden(profil)),
                                 gewinde_liste(self.tabellen), m, laenge=laenge or q.get("laenge"))
        if erg["fehler"]:
            return None, " ".join(erg["fehler"])
        p = dict(q, **erg["felder"])
        if laenge:
            p["laenge"] = laenge
        _, _, zeit = rechnen.schneidzeit(p, self.kopf, rechnen.wand_position(p, self.k), self.tabellen, self.k)
        satz = (rechnen.zeitbasis(self.kopf, self.k, self.tabellen).get("maschine") or {}).get("stundensatz")
        if zeit is None:
            return None, "keine Schneiddaten für Maschine und Werkstoff"
        if not isinstance(satz, (int, float)) or satz <= 0:
            return None, "Stundensatz Maschine fehlt"
        return zeit / 3600 * satz, None

    def _auf_bild(self, i, auf_bild=None):
        """Doppelklick auf das kleine Bild der Zelle i (auf_bild vorgegeben: Tests), sonst aus der Mausposition."""
        if auf_bild is not None:
            return auf_bild
        maus = self.pos_ansicht.viewport().mapFromGlobal(QCursor.pos())
        zelle = self.pos_ansicht.visualRect(i)
        return zelle.contains(maus) and maus.x() <= zelle.left() + self.pos_ansicht.iconSize().width() + 8

    # -------------------------------------------------------------- Wiederholteile (Plan A1, wiederholteile.py)
    def wiederholteile_suchen(self, warten=True):
        """{Positions-ID: [Treffer]}; gerechnet nur, wenn sich die suchrelevanten Werte oder andere Angebote geändert
        haben. warten=False (Anzeige): die Datenbank liefert die möglichen Treffer sofort, eingestuft wird in einem
        eigenen Thread; bis dahin bleibt das bisherige Ergebnis (None, wenn es noch keines gibt), danach zeigt
        _wt_fertig() das neue an. Ohne Bildschirm (stumm) wird immer gleich gerechnet."""
        from . import wiederholteile
        kennung = (wiederholteile.stand(self.db), self.kopf.get("kundennr"),
                   tuple(tuple(p.get(f) for f in wiederholteile.FELDER) for p in self.positionen))
        if getattr(self, "_wt_kennung", None) == kennung:
            return self._wt
        zeilen = wiederholteile.laden(self.db, self.id, self.positionen)
        if warten or self.f.stumm:
            self._wt_kennung, self._wt_lauf = kennung, None
            self._wt = wiederholteile.auswerten(zeilen, self.kopf.get("kundennr"), self.positionen)
            return self._wt
        lauf = getattr(self, "_wt_lauf", None)
        if lauf is not None and lauf[0] == kennung:
            return getattr(self, "_wt", None)
        ende = {}
        positionen, kundennr = [dict(p) for p in self.positionen], self.kopf.get("kundennr")

        def rechnen_():
            ende["treffer"] = wiederholteile.auswerten(zeilen, kundennr, positionen)

        t = threading.Thread(target=rechnen_, name="Wiederholteile", daemon=True)
        self._wt_lauf = (kennung, t, ende)
        t.start()
        if getattr(self, "_wt_zeitgeber", None) is None:
            self._wt_zeitgeber = QTimer(self)
            self._wt_zeitgeber.setInterval(50)
            self._wt_zeitgeber.timeout.connect(self._wt_fertig)
        self._wt_zeitgeber.start()
        return getattr(self, "_wt", None)

    def _wt_fertig(self):
        """Zeitgeber: Einstufen im Thread fertig -> Ergebnis übernehmen und anzeigen (nur der neueste Lauf zählt)."""
        lauf = getattr(self, "_wt_lauf", None)
        if lauf is None:
            self._wt_zeitgeber.stop()
            return
        kennung, t, ende = lauf
        if t.is_alive():
            return
        self._wt_zeitgeber.stop()
        self._wt_lauf = None
        if "treffer" in ende:
            self._wt_kennung, self._wt = kennung, ende["treffer"]
        self.wiederholteile_anzeigen()

    def wiederholteile_anzeigen(self):
        treffer = self.wiederholteile_suchen(warten=False)
        if treffer is None:             # erstes Ergebnis kommt noch aus dem Thread
            return
        self.uebersicht_bereich.wiederholteile_setzen(
            [(r, " · ".join(str(x) for x in (f"Pos. {p.get('pos')}" if p.get("pos") is not None else None,
                                            p.get("artikel") or p.get("bezeichnung")) if x), treffer[p["id"]])
             for r, p in enumerate(self.positionen) if p["id"] in treffer])

    def wiederholteil_link(self, ziel):
        art, _, wert = ziel.partition(":")
        if art == "hin":
            self.f.reiter.setCurrentWidget(self)
            self.zur_position(zeile=int(wert))
        elif art == "oeffnen":
            self.f.angebot_oeffnen(int(wert))
        elif art == "werte":
            self.werte_uebernehmen(int(wert))

    def werte_uebernehmen(self, zeile, felder=None):
        """Übernehmbare Werte des besten Treffers in die Position (Dialog mit Haken je Wert; felder = ohne Dialog).
        Der Preis wird nie übernommen. Ergebnis: Liste der übernommenen Felder."""
        from .wiederholteile import UEBERNEHMBAR
        p = self.positionen[zeile]
        treffer = (self.wiederholteile_suchen().get(p["id"]) or [None])[0]
        if treffer is None or not treffer.werte:
            return []
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return []
        if felder is None:
            d = WerteUebernehmenDialog(self, p, treffer, UEBERNEHMBAR)
            if d.exec() != QDialog.Accepted:
                return []
            felder = d.gewaehlt()
        felder = [f for f in felder if f in treffer.werte]
        for f in felder:
            self.db.position_aendern(p["id"], f, treffer.werte[f])
        if felder:
            self.f.meldung(f"{len(felder)} Wert(e) aus {treffer.angebot['nummer']} übernommen.")
            self.neu_laden()
        return felder

    def zur_position(self, ref=None, zeile=None):
        """Reiter Positionen zeigen und die Position markieren (ref = Bezug aus der Optimierung oder zeile).
        Ergebnis: Zeile oder None."""
        if zeile is None:
            zeile = next((r for r, p in enumerate(self.positionen) if rechnen.schluessel(p, r) == ref), None)
        if zeile is None or zeile >= len(self.positionen):
            return None
        self.reiter.setCurrentWidget(self.pos_seite)
        c = self.pos_ansicht.currentIndex().column()
        index = self.pos_modell.index(zeile, c if c >= 0 and not self.pos_ansicht.isColumnHidden(c) else 0)
        self.pos_ansicht.scrollTo(index)
        self.pos_ansicht.setCurrentIndex(index)
        self.pos_ansicht.selectRow(zeile)
        self.pos_ansicht.setFocus()
        return zeile

    def protokoll_zur_position(self, zeile):
        """Zeile des STEP-Protokolls: zur Position mit derselben Pos.-Nummer springen."""
        if zeile >= len(self.prot.zeilen):
            return None
        pos = self.prot.zeilen[zeile][step.PROTOKOLL.index("Pos.")]
        r = next((r for r, p in enumerate(self.positionen) if pos is not None and p.get("pos") == pos), None)
        if r is None:
            self.f.meldung("Zu dieser Protokollzeile gibt es keine Position (mehr).", fehler=True)
            return None
        return self.zur_position(zeile=r)

    def status_beheben(self, zeile):
        """Zum Status der Position springen: passenden Dialog öffnen oder die Zelle zum Eintragen öffnen.
        Ergebnis: das Ziel aus STATUS_ZIELE oder None (Status ohne Ziel, z. B. OK)."""
        ziel = status_ziel(self.pos_modell.status[zeile])
        if not ziel:
            return None
        ziel = ziel[0]
        if ziel.startswith("feld:"):
            self.zelle_bearbeiten(zeile, ziel[5:])
        elif ziel == "optimieren":
            self.optimieren()
        elif ziel == "schneidweg_berechnen":
            self.schneidweg_berechnen(zeile)
        elif ziel == "baugruppe_bearbeiten":
            self.baugruppe_bearbeiten([zeile], fokus=self.pos_modell.status[zeile])
        elif ziel == "bohrungen_pruefen" and len(offen := self.bohrungen_offen()) > 1:
            self.bohrungen_alle_pruefen(offen)      # V3: alle offenen in einem Fenster, nicht eines je Position
        else:
            getattr(self, ziel)([zeile])
        return ziel

    def zelle_bearbeiten(self, zeile, name):
        """Zelle der Spalte name in der Zeile markieren und zum Eintragen öffnen (ausgeblendete Spalte einblenden)."""
        m = self.pos_modell
        c = next((c for c in range(m.columnCount()) if m.name(c) == name), None)
        if c is None:
            return False
        if self.pos_ansicht.isColumnHidden(c):
            if name in OPTIONALE_SPALTEN:
                self.spalte_waehlen(name, True)
            else:
                self.pos_ansicht.setColumnHidden(c, False)
        index = m.index(zeile, c)
        self.pos_ansicht.scrollTo(index)
        self.pos_ansicht.setCurrentIndex(index)
        self.pos_ansicht.edit(index)
        return True

    def bohrungen_pruefen(self, zeilen=None, werte=None):
        """Gewinde-Vorschläge, Senkungen und Fließlochbohrungen der (ersten) markierten Position bestätigen oder
        ablehnen (BohrbildDialog). werte = (Bohrbild-Liste, Gewinde von Hand) setzt sie ohne Dialog (Tests).
        Ergebnis: True = gespeichert."""
        from . import bohrbild
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        zeilen = [r for r in zeilen if r < len(self.positionen)]
        if not zeilen:
            self.f.meldung("Bitte zuerst eine Position markieren.", fehler=True)
            return False
        gewinde = [(g["gewinde"], g.get("kernloch")) for g in self.tabellen["gewinde"] if g.get("gewinde")]
        if werte is None and len(zeilen) > 1:       # mehrere markiert: ein Fenster für alle (Plan Angebotsablauf V3)
            mit = [r for r in zeilen if not kein_laserteil(self.positionen[r]) and bohrbild.aus_position(
                self.positionen[r], gewinde, rechnen.wand_position(self.positionen[r], self.k))]
            if len(mit) > 1:
                return self.bohrungen_alle_pruefen(mit)
            zeilen = mit or zeilen[:1]
        p = self.positionen[zeilen[0]]
        katalog = self.tabellen.get("zusatzarbeiten") or []
        if werte is None:
            from .bohrbild_dialog import BohrbildDialog
            d = BohrbildDialog(self, p, gewinde, rechnen.wand_position(p, self.k),
                               self.db.einstellung("bohren_laser"), katalog, rechnen.stundensaetze(self.tabellen),
                               {g["gewinde"]: g.get("preis") for g in self.tabellen["gewinde"] if g.get("gewinde")})
            if d.exec() != QDialog.Accepted:
                return False
            werte = d.ergebnis
        liste, hand = werte
        felder = bohrbild.anwenden(p, liste, hand, katalog, rechnen.stundensaetze(self.tabellen))
        fehlt = felder.pop("_fehlt", None)
        for name, wert in felder.items():
            self.db.position_aendern(p["id"], name, wert)
        arbeiten = bohrbild.arbeiten_text(liste)
        self.f.meldung(f"Bohrungen von Pos. {p.get('pos') or ''} gespeichert"
                       + (f", Zusatzarbeiten {arbeiten}" if arbeiten else "")
                       + (f", {bohrbild.offen(liste)} noch offen" if bohrbild.offen(liste) else "") + "."
                       + (f" Zusatzarbeit {', '.join(fehlt)} fehlt in den Stammdaten (Einstellungen › Zusatzarbeiten)."
                          if fehlt else ""), fehler=bool(fehlt))
        self.neu_laden()
        return True

    def bohrungen_offen(self):
        """Zeilen der Positionen mit ungeprüften Gewinde-Vorschlägen, Senkungen, Flowdrill oder Bohren."""
        from . import bohrbild
        gewinde = [(g["gewinde"], g.get("kernloch")) for g in self.tabellen["gewinde"] if g.get("gewinde")]
        return [r for r, p in enumerate(self.positionen) if not kein_laserteil(p) and bohrbild.offen(
            bohrbild.aus_position(p, gewinde, rechnen.wand_position(p, self.k)))]

    def bohrungen_alle_pruefen(self, zeilen=None, werte=None, dialog=None):
        """Bohrungen mehrerer Positionen in einem Fenster prüfen (Plan Angebotsablauf V3, BohrbildSammelDialog);
        ohne zeilen alle mit offenen Zeilen. werte = {Zeile: Bohrbild} setzt sie ohne Dialog, dialog(d) bedient das
        Fenster statt exec (Tests). Ergebnis: True = gespeichert."""
        from . import bohrbild
        zeilen = self.bohrungen_offen() if zeilen is None else [r for r in zeilen if r < len(self.positionen)]
        if not zeilen:
            self.f.meldung("Keine Position mit offenen Bohrungen oder Gewinde-Vorschlägen.")
            return False
        katalog = self.tabellen.get("zusatzarbeiten") or []
        if werte is None:
            from .bohrbild_dialog import BohrbildSammelDialog
            gewinde = [(g["gewinde"], g.get("kernloch")) for g in self.tabellen["gewinde"] if g.get("gewinde")]
            d = BohrbildSammelDialog(self, [(r, self.positionen[r], rechnen.wand_position(self.positionen[r], self.k))
                                            for r in zeilen], gewinde, self.db.einstellung("bohren_laser"))
            if dialog is not None:
                dialog(d)
            elif d.exec() != QDialog.Accepted:
                return False
            if d.ergebnis is None:
                return False
            werte = d.ergebnis
        fehlt, offen = set(), 0
        for r, liste in werte.items():
            p = self.positionen[r]
            felder = bohrbild.anwenden(p, liste, None, katalog, rechnen.stundensaetze(self.tabellen))
            fehlt |= set(felder.pop("_fehlt", None) or ())
            for name, wert in felder.items():
                self.db.position_aendern(p["id"], name, wert)
            offen += bohrbild.offen(liste)
        self.f.meldung(f"Bohrungen von {len(werte)} Position(en) gespeichert"
                       + (f", {offen} Zeile(n) noch offen" if offen else "") + "."
                       + (f" Zusatzarbeit {', '.join(sorted(fehlt))} fehlt in den Stammdaten (Einstellungen › "
                          "Zusatzarbeiten)." if fehlt else ""), fehler=bool(fehlt))
        self.neu_laden()
        return True

    def step_merkmale_pruefen(self, zeilen=None, dialog=None):
        """Prüfstatus je STEP-Merkmal der (ersten) markierten Position mit Rohdaten und Korrekturen (step_pruefung);
        „Alle geprüft“ bestätigt sie. dialog(d) bedient das Fenster statt exec (Tests). Ergebnis: Dialog oder None."""
        from . import step_pruefung
        from .step_pruefung_dialog import MerkmaleDialog
        if zeilen is None:
            zeilen = self._markierte_zeilen()
        zeilen = [r for r in zeilen if r < len(self.positionen)]
        if not zeilen:
            self.f.meldung("Bitte zuerst eine Position markieren.", fehler=True)
            return None
        p = self.positionen[zeilen[0]]
        aktuell = next((x for x in self.db.positionen(self.id) if x["id"] == p["id"]), p)      # mit Korrekturen
        if not step_pruefung.lesen(aktuell.get("step_merkmale")):
            self.f.meldung(f"Pos. {p.get('pos') or ''}: keine STEP-Merkmale (nicht aus dem STEP-Import oder vor "
                           "Version 0.9.161 importiert).", fehler=True)
            return None
        d = MerkmaleDialog(self, aktuell)
        (dialog(d) if dialog else d.exec())
        if d.bestaetigt:
            self.db.position_aendern(p["id"], "step_merkmale", step_pruefung.bestaetigen(
                aktuell.get("step_merkmale"), self.db.einstellung("benutzer_kuerzel") or ""))
            self.f.meldung(f"Pos. {p.get('pos') or ''}: STEP-Merkmale als geprüft bestätigt.")
            self.neu_laden()
        return d

    def arbeitsgaenge_zeilen(self):
        """Arbeitsgänge aller Positionen mit Vorschlägen der Arbeitsgang-Regeln (arbeitsgaenge.uebersicht)."""
        from . import arbeitsgaenge
        return arbeitsgaenge.uebersicht(self.kopf, self.positionen, self.k, self.tabellen,
                                        self.db.zeilen("arbeitsgang_regeln"))

    def arbeitsgaenge_vorschlagen(self, dialog=None):
        """Fenster „Arbeitsgänge je Position“: Vorschläge annehmen oder ablehnen. dialog(d) bedient das Fenster statt
        exec (Tests). Ergebnis: Dialog."""
        from .arbeitsgaenge_dialog import ArbeitsgaengeDialog
        d = ArbeitsgaengeDialog(self, self)
        (dialog(d) if dialog else d.exec())
        return d

    def _position_frisch(self, position_id):
        return next((x for x in self.db.positionen(self.id) if x["id"] == position_id), None)

    def arbeitsgang_annehmen(self, position_id, name):
        """Vorgeschlagene Zusatzarbeit in die Position übernehmen (mit Preisstand); doppelt nie. Ergebnis: True."""
        from . import arbeitsgaenge
        p = self._position_frisch(position_id)
        neu = arbeitsgaenge.annehmen(p, name, self.db.zeilen("arbeitsgang_regeln"), self.tabellen,
                                                self.kopf, self.k) if p else None
        if neu is None:
            self.f.meldung(f"„{name}“ ist schon in der Position oder nicht in den Zusatzarbeiten.", fehler=True)
            return False
        self.db.position_aendern(position_id, "zusatz", neu)
        if name in arbeitsgaenge.lesen(p)["abgelehnt"]:
            self.db.position_aendern(position_id, "arbeitsgaenge", arbeitsgaenge.ablehnen(p, name, zurueck=True))
        self.f.meldung(f"Pos. {p.get('pos') or ''}: „{name}“ angenommen, wird jetzt gerechnet.")
        self.neu_laden()
        return True

    def arbeitsgang_ablehnen(self, position_id, name, zurueck=False):
        """Vorschlag ablehnen bzw. Ablehnung zurücknehmen (bleibt in positionen.arbeitsgaenge). Ergebnis: True."""
        from . import arbeitsgaenge
        p = self._position_frisch(position_id)
        if p is None:
            return False
        self.db.position_aendern(position_id, "arbeitsgaenge", arbeitsgaenge.ablehnen(p, name, zurueck))
        self.neu_laden()
        return True

    def anbauteile_pruefen(self, zeilen=None, werte=None):
        """Anbauteile der (ersten) markierten Position aus dem STEP-Import prüfen (AnbauDialog): Art, Bearbeitung,
        Gravur, bestätigen oder ausschließen. werte = neue Liste setzt sie ohne Dialog (Tests). Ergebnis: True =
        gespeichert."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        zeilen = [r for r in zeilen if r < len(self.positionen)]
        if not zeilen:
            self.f.meldung("Bitte zuerst eine Position markieren.", fehler=True)
            return False
        p = self.positionen[zeilen[0]]
        if not anbau.lesen(p.get("anbauteile")):
            self.f.meldung(f"Pos. {p.get('pos') or ''} hat keine Anbauteile aus dem STEP-Import.", fehler=True)
            return False
        if werte is None:
            from .anbau_dialog import AnbauDialog
            titel = " ".join(str(x) for x in (f"Pos. {p.get('pos')}" if p.get("pos") else "", p.get("artikel")) if x)
            d = AnbauDialog(self, p.get("anbauteile"), titel, p.get("gravur"))
            if d.exec() != QDialog.Accepted:
                return False
            werte = d.ergebnis
        for name, wert in anbau.position_anwenden(p, werte).items():
            self.db.position_aendern(p["id"], name, wert)
        n = anbau.offen(werte)
        self.f.meldung(f"Anbauteile von Pos. {p.get('pos') or ''} gespeichert" + (f", {n} noch offen." if n else "."))
        self.neu_laden()
        return True

    @blaetterbar()
    def schneidweg_berechnen(self, zeile=None, eingaben=None, dialog=None, ueberschreiben=None):
        """Schneidweg-Rechner für die markierte Position (Dialog): Enden, Konturen und Gravur eingeben, Werte in die
        Position übernehmen. eingaben = dict setzt sie ohne Dialog, dialog(d) bedient den Dialog statt exec,
        ueberschreiben = True/False beantwortet die Rückfrage bei STEP-Werten (Tests). Ergebnis: True = gespeichert."""
        if zeile is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
            if len(zeilen) != 1:
                self.f.meldung("Bitte genau eine Position markieren.", fehler=True)
                return False
            zeile = zeilen[0]
        p = self.positionen[zeile]
        profil = self.k.profile.get(p.get("profil_id"))
        if kein_laserteil(p) or not profil:
            self.f.meldung("Schneidweg-Rechner: Die Position braucht ein Profil aus den Stammdaten (kein Zukaufteil).",
                           fehler=True)
            return False
        if eingaben is None:
            d = SchneidwegDialog(self, p, profil, self.kopf, self.k, self.tabellen, self.db, self.positionen,
                                 step_lesen=lambda: self.step_messen(titel="STEP-Datei dieses Teils wählen"))
            self._blaettern_einbauen(d, zeile, lambda: (d.eingaben(), d.naht_geaendert(), d.muster_geaendert()))
            if (dialog(d) if dialog else teile_editor.ausfuehren(d)) != QDialog.Accepted:
                return False
            eingaben = d.eingaben()
            naht_neu = dict(d.naht_geaendert(), **d.muster_geaendert())
        else:
            naht_neu = {}
        profil = rechnen.profil_im_angebot(profil, self.kopf, p.get("profil_id"), p.get("werkstoff_id"), self.k)
        grenzen = rechnen.kontur_regel(rechnen.maschine(self.kopf, self.k), rechnen.wand_schneiden(profil))
        erg = schneidweg.rechnen(eingaben, profil, grenzen, gewinde_liste(self.tabellen), rechnen.maschine(self.kopf, self.k),
                                 laenge=p.get("laenge"))
        if erg["fehler"]:
            self.f.meldung("Schneidweg-Rechner: " + " ".join(erg["fehler"]), fehler=True)
            return False
        step_werte = p.get("a_schnitt") is not None and schneidweg.lesen(p.get("technik")).get("quelle") != \
            schneidweg.QUELLE
        if step_werte:
            if ueberschreiben is None:
                ueberschreiben = self.f.stumm or QMessageBox.question(
                    self, "Schneidweg", "Die Position hat Werte aus dem STEP-Import (Schneidweg, Enden, Konturen). "
                    "Durch die Werte des Schneidweg-Rechners ersetzen?") == QMessageBox.Yes
            if not ueberschreiben:
                return False
        felder = dict(erg["felder"], technik=schneidweg.speichern(eingaben), **naht_neu)
        # Bohrbild neu aus den Eingaben (Gewinde, Senken, Flowdrill, Bohren < 0,7 × Wand; neu eingegeben = bestätigt),
        # Prüfstatus gleicher Bohrungen bleibt; Gewinde von Hand ohne Zeile im alten Bohrbild bleiben stehen
        from . import bohrbild
        g_liste = gewinde_liste(self.tabellen) or step.KERNLOCH
        alt = bohrbild.aus_position(p, g_liste)         # ohne Bohrbild: aus Gewinde-Vorschlag und Gewinde geprüft
        bild = bohrbild.aus_rechner(erg, alt, g_liste,
                                    rechnen.wand_schneiden(profil), self.db.einstellung("fliessloch_laser"),
                                    self.db.einstellung("bohren_laser"))
        if bild or p.get("bohrbild") or erg["felder"].get("gewinde_vorschlag"):
            felder.update(bohrbild.anwenden(dict(p, **felder, bohrbild=None), bild, bohrbild.hand_gewinde(p, alt),
                                            self.tabellen.get("zusatzarbeiten") or [],
                                            rechnen.stundensaetze(self.tabellen)))
            felder.pop("_fehlt", None)
        if erg.get("laenge"):           # Knickrahmen: gestreckte Länge
            felder["laenge"] = erg["laenge"]
        self._knicken_eintragen(felder, dict(p, **felder), erg)
        self._stege_eintragen(felder, dict(p, **felder))
        for name, wert in felder.items():
            self.db.position_aendern(p["id"], name, wert)
        weitere = self._radius_uebernehmen(p, eingaben)
        self.f.meldung(f"Pos. {p.get('pos') or ''}: Schneidweg {rechnen.zahl(erg['schneidweg'], 1)} mm, "
                       f"{erg['einstiche']} Einstiche aus dem Schneidweg-Rechner übernommen."
                       + (f" Außenradius auch für {weitere} weitere Position(en) neu gerechnet." if weitere else ""))
        self.neu_laden()
        return True

    def profil_gewechselt(self, p):
        """Profil einer Position aus dem STEP-Import in der Tabelle geändert (Patrick 25.10.2026: Winkel 33x30x6 auf
        60x40x6): Enden, Konturen und – bei Winkel/U/C aus einem größeren Profil – die Längsschnitte zwischen den
        Stegen 2 mm wie im Rohr-Editor neu rechnen (schneidweg.rechnen) und in die Position schreiben. Ergebnis: Text
        für die Meldung oder None (keine STEP-Werte, Profil unbekannt, Fehler)."""
        e = schneidweg.lesen(p.get("technik"))
        pid = p.get("profil_id")
        profil = self.k.profile.get(pid) or opt.profil_aus_name(pid) if pid else None
        if not p.get("technik") or e.get("quelle") != schneidweg.QUELLE_STEP or not profil or kein_laserteil(p):
            return None
        profil = dict(profil, profil_id=pid)
        neu = self._profil_neu_messen(p, e, profil)
        if neu:
            return neu
        if pid in self.k.profile:
            profil = rechnen.profil_im_angebot(profil, self.kopf, pid, p.get("werkstoff_id"), self.k)
        m = rechnen.maschine(self.kopf, self.k)
        e, _ = schneidweg.aus_position(e, p, profil)
        erg = schneidweg.rechnen(e, profil, rechnen.kontur_regel(m, rechnen.wand_schneiden(profil)),
                                 gewinde_liste(self.tabellen), m, laenge=p.get("laenge"))
        if erg["fehler"]:
            return None
        for name in PROFILWECHSEL_FELDER:
            if name in erg["felder"]:
                self.db.position_aendern(p["id"], name, erg["felder"][name])
        sk = next((h for h in erg["hinweise"] if "Schenkel gekürzt" in h or "aus dem Rohr" in h), None)
        return f"Schneidweg für {pid} neu gerechnet: {rechnen.zahl(erg['schneidweg'], 1)} mm" + \
            (f" ({sk})" if sk else "") + "."

    def _profil_neu_messen(self, p, e, profil):
        """Profilwechsel einer Position mit gemessenem Winkel/U (technik step_datei, schenkel_mess): größeres Profil
        gleicher Form -> virtuelles Bauteil mit Stegen messen, gezeichnetes Profil -> wie gezeichnet messen; Werte und
        3D-Netz der Position ersetzen. Ergebnis: Text für die Meldung oder None (keine Datei, nicht messbar)."""
        mess = schneidweg._messprofil(e.get("schenkel_mess"))
        pfad = e.get("step_datei")
        if not mess or not pfad or not Path(pfad).is_file() or profil.get("form") != mess["form"]:
            return None
        m0 = dict(profilform=mess["form"], abm_a=mess["a"], abm_b=mess["b"], wandstaerke=mess["wand"],
                  laenge=e.get("l_step"))
        ziel = step.stege_ziel(m0, profil)
        gleich = not ziel and all(abs(float(profil.get(x) or 0) - y) <= step.TOL_MASS
                                  for x, y in (("a", max(mess["a"], mess["b"] or 0)), ("b", min(mess["a"], mess["b"] or 0))))
        if not ziel and not gleich:
            return None
        if ziel:
            zeilen = self._virtuell_messen(pfad, ziel)
        else:
            zeilen = self.step_messen([pfad])
        z = next((x for x in zeilen or () if str(x.get("koerper")) == str(e.get("step_koerper") or 1)), None)
        if z is None or (ziel and "stege=virtuell" not in (z.get("sicherheit") or "")):
            return None
        m = dict(z, _uebernehmen=True, _pfad=pfad, _profil=profil["profil_id"])
        if ziel:
            m["_mess_original"] = m0
        erg = step.uebernehmen([m], [], self.k, self.tabellen["gewinde"], rechnen.maschine(self.kopf, self.k),
                               p.get("werkstoff_id"), p.get("stueck"))
        if not erg["positionen"]:
            return None
        q = erg["positionen"][0]
        t_neu = schneidweg.lesen(q.get("technik"))
        if e.get("stege_abtrennen") and virtuell.ist_virtuell(t_neu):     # Wahl „Stege abtrennen“ bleibt
            q["technik"] = json.dumps(dict(t_neu, stege_abtrennen=True), ensure_ascii=False)
        zusatz = {}
        self._stege_eintragen(zusatz, dict(p, technik=q.get("technik")))
        for name in PROFILWECHSEL_FELDER + ("technik",):
            if name in q:
                self.db.position_aendern(p["id"], name, q[name])
        for name, wert in zusatz.items():
            self.db.position_aendern(p["id"], name, wert)
        if q.get("_netz"):
            self.db.netz_speichern(p["id"], q["_netz"])
        return (f"Schneidweg für {profil['profil_id']} neu gemessen: {rechnen.zahl(q['schneidweg'], 1)} mm"
                + (" (Bauteil mit Stegen 2 mm)." if ziel else " (wie gezeichnet)."))

    def _radius_uebernehmen(self, p, eingaben):
        """Außenradius aus dem Rechner (eingaben['r_aussen']) als Radius des Angebots für Profil + Werkstoff speichern
        und die übrigen Positionen der Gruppe mit Eingaben des Rechners neu rechnen (Positionen ohne Eingaben rechnen
        die Schnittlänge ohnehin mit dem Radius des Angebots, gemessene STEP-Werte bleiben). Ergebnis: Anzahl der
        neu gerechneten Positionen."""
        r = eingaben.get("r_aussen")
        r = float(r) if isinstance(r, (int, float)) and not isinstance(r, bool) and r >= 0 else None
        pid, wst = p.get("profil_id"), p.get("werkstoff_id")
        if r == rechnen.radius_angebot(self.kopf, pid, wst) or (self.k.profile.get(pid) or {}).get("form") \
                not in opt.RADIUS_FORMEN:
            return 0
        radien = dict(self.kopf.get("radien") or {})
        radien[naht.gruppe_schluessel(pid, wst)] = r
        radien = {g: w for g, w in radien.items() if w is not None}
        self.db.radien_speichern(self.id, radien)
        self.kopf["radien"] = radien or None
        n = 0
        for q in self.positionen:
            if q["id"] == p["id"] or q.get("profil_id") != pid or q.get("werkstoff_id") != wst:
                continue
            e = schneidweg.lesen(q.get("technik"))
            if not q.get("technik") or e.get("quelle") != schneidweg.QUELLE:
                continue
            profil = rechnen.profil_im_angebot(self.k.profile[pid], self.kopf, pid, wst, self.k)
            grenzen = rechnen.kontur_regel(rechnen.maschine(self.kopf, self.k), rechnen.wand_schneiden(profil))
            erg = schneidweg.rechnen(e, profil, grenzen, gewinde_liste(self.tabellen),
                                     rechnen.maschine(self.kopf, self.k), laenge=q.get("laenge"))
            if erg["fehler"]:
                continue
            for name in ("schneidweg", "a_schnitt", "b_schnitt"):
                if name in erg["felder"]:
                    self.db.position_aendern(q["id"], name, erg["felder"][name])
            n += 1
        return n

    def _stege_eintragen(self, felder, p):
        """Zusatzarbeit 'Stege abtrennen' (virtuelles Bauteil) nach technik stege_abtrennen in felder['zusatz']
        eintragen bzw. wieder herausnehmen (nur Einträge aus dem Schneidweg-Rechner)."""
        an = bool(virtuell.technik_lesen(p).get("stege_abtrennen"))
        alt = p.get("zusatz") or None
        if not an and virtuell.ZUSATZ_STEGE not in str(alt or ""):
            return
        zu, fehlt = virtuell.zusatz_eintragen(alt, an, self.tabellen.get("zusatzarbeiten") or [], schneidweg.QUELLE)
        if zu != alt:
            felder["zusatz"] = zu
        if fehlt:
            self.f.meldung(f"Zusatzarbeit '{virtuell.ZUSATZ_STEGE}' fehlt in den Stammdaten.", fehler=True)

    def muster_umschalten(self, zeilen=None, an=None):
        """Markierte Positionen als Musterteil kennzeichnen (an=True) oder wieder als Serienteil (False); None =
        umschalten nach der ersten Zeile. Ein Satz wird immer ganz umgeschaltet. Musterteile stehen mit 0 € im
        Angebot, ihre Kosten gehen auf die Serie (Patrick 28.10.2026). Ergebnis: Zahl geänderter Positionen."""
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return 0
        zeilen = [r for r in (zeilen if zeilen is not None else self._markierte_zeilen()) if r < len(self.positionen)]
        if not zeilen:
            self.f.meldung("Bitte zuerst die Position(en) markieren.", fehler=True)
            return 0
        saetze = {self.positionen[r].get("satz") for r in zeilen if self.positionen[r].get("satz")}
        zeilen = sorted(set(zeilen) | {r for r, q in enumerate(self.positionen) if q.get("satz") in saetze})
        if an is None:
            an = not ist_muster(self.positionen[zeilen[0]])
        n = 0
        for r in zeilen:
            p = self.positionen[r]
            if ist_muster(p) != an:
                self.db.position_aendern(p["id"], "muster", muster_haken.wert(an))
                n += 1
        if n:
            self.neu_laden()
            self.f.meldung(f"{n} Position(en) " + ("als Muster gekennzeichnet: 0 € im Angebot, Kosten auf die Serie."
                                                   if an else "wieder als Serienteil gerechnet."))
        return n

    def stege_abtrennen(self, zeilen=None, an=None):
        """Virtuelles Bauteil (Winkel aus größerem Profil, offenes Rohr): Stege 2 mm an den Enden abtrennen (an=True,
        Zusatzarbeit, Gewicht wie gezeichnet) oder am Teil lassen (False); None = umschalten nach der ersten Zeile.
        Ergebnis: Zahl geänderter Positionen."""
        if zeilen is None:
            zeilen = self._markierte_zeilen()
        ziele = [(r, virtuell.technik_lesen(self.positionen[r])) for r in zeilen if r < len(self.positionen)]
        ziele = [(r, e) for r, e in ziele if e]
        if not ziele:
            self.f.meldung("Keine Position mit virtuellem Bauteil (Stege 2 mm) markiert.", fehler=True)
            return 0
        if an is None:
            an = not ziele[0][1].get("stege_abtrennen")
        n = 0
        for r, e in ziele:
            if bool(e.get("stege_abtrennen")) == an:
                continue
            p = self.positionen[r]
            e = dict(e)
            if an:
                e["stege_abtrennen"] = True
            else:
                e.pop("stege_abtrennen", None)
            felder = dict(technik=json.dumps(e, ensure_ascii=False))
            self._stege_eintragen(felder, dict(p, **felder))
            for name, wert in felder.items():
                self.db.position_aendern(p["id"], name, wert)
            n += 1
        if n:
            self.neu_laden()
            self.f.meldung(f"{n} Position(en): Stege {'werden abgetrennt (Nacharbeit)' if an else 'bleiben am Teil'}.")
        return n

    def virtuell_erzeugen(self, p, ordner):
        """Körper des virtuellen Bauteils der Position p (Teil mit Stegen bzw. Ringen, so wird gelasert) als STEP
        in Dateilage: die Kundendatei wird mit STEP-Import.exe --virtuell neu gemessen (je Datei und Zielprofil
        einmal, Unterordner von ordner). Ergebnis: Pfad oder None (Datei fehlt, Messung ohne Stege)."""
        import hashlib
        e = virtuell.technik_lesen(p)
        datei = e.get("step_datei")
        if not e or not datei or not Path(datei).is_file():
            return None
        befehl = step.messprogramm(self.f.programmordner)
        if befehl is None:
            return None
        ziel_stege = None
        if e.get("stege_virtuell"):
            pr = self.k.profile.get(p.get("profil_id")) or {}
            ziel_stege = "|".join([str(pr.get("form") or ""), f"{float(pr.get('a') or 0):g}",
                                   f"{float(pr.get('b') or pr.get('a') or 0):g}", f"{float(pr.get('wand') or 0):g}"])
        unter = Path(ordner) / hashlib.sha1(f"{datei}|{ziel_stege}".encode("utf-8")).hexdigest()[:16]
        if not unter.is_dir():
            ausgabe = unter / "messwerte.txt"
            unter.mkdir(parents=True)
            self._messen(befehl + [str(datei), "--ausgabe", str(ausgabe), "--virtuell", str(unter / "virtuell"),
                                   "--flachstahl-bis", str(self.flach_bis())]
                         + (["--stege", ziel_stege] if ziel_stege else [])
                         + step_einstellungen.mess_argumente(self.db), 1, ausgabe)
        quelle = unter / "virtuell" / f"k{int(e.get('step_koerper') or 1)}.step"
        return quelle if quelle.is_file() else None

    def virtuell_step_speichern(self, zeile=None, pfad=None):
        """Virtuelles Bauteil (so wird gelasert: Teil mit Stegen bzw. Ringen) als STEP: die Kundendatei wird mit
        STEP-Import.exe --virtuell neu gemessen, der Körper unverändert in Dateilage geschrieben. Ohne pfad:
        Dateidialog. Ergebnis: Pfad oder None."""
        if zeile is None:           # die erste markierte virtuelle Position (das Menü zeigt den Eintrag, wenn eine es ist)
            zeilen = self._markierte_zeilen()
            zeile = next((z for z in zeilen if z < len(self.positionen) and virtuell.technik_lesen(self.positionen[z])),
                         zeilen[0] if zeilen else None)
        if zeile is None or zeile >= len(self.positionen):
            return None
        p = self.positionen[zeile]
        e = virtuell.technik_lesen(p)
        datei = e.get("step_datei")
        if not e or not datei or not Path(datei).is_file():
            self.f.meldung("Virtuelles Bauteil: STEP-Datei der Position nicht gefunden (nur für Teile aus dem "
                           "STEP-Import mit Stegen).", fehler=True)
            return None
        if step.messprogramm(self.f.programmordner) is None:
            self.f.meldung("STEP-Messprogramm nicht gefunden.", fehler=True)
            return None
        if pfad is None:
            name = f"Pos {p.get('pos') or ''} {p.get('artikel') or ''} virtuell".strip()
            vorschlag = self._ziel(name, ".step") if hasattr(self, "_ziel") else name + ".step"
            pfad, _ = QFileDialog.getSaveFileName(self, "Virtuelles Bauteil als STEP", str(vorschlag),
                                                  "STEP-Dateien (*.step *.stp)")
            if not pfad:
                return None
        with tempfile.TemporaryDirectory() as tmp:
            quelle = self.virtuell_erzeugen(p, tmp)
            if quelle is None:
                self.f.meldung("Virtuelles Bauteil konnte nicht erzeugt werden (Messung ohne Stege, z. B. Enden "
                               "nicht eben).", fehler=True)
                return None
            shutil.copyfile(quelle, pfad)
        self.f.meldung(f"Virtuelles Bauteil gespeichert: {pfad}")
        return pfad

    def _knicken_eintragen(self, felder, p, erg):
        """Zusatzarbeit Knicken mit der Zahl der V-Ausschnitte (Knickrahmen) in felder['zusatz'] eintragen bzw. wieder
        herausnehmen (nur Einträge aus dem Schneidweg-Rechner)."""
        from . import knickrahmen
        n = erg.get("knicke") or 0
        alt = p.get("zusatz") or None
        if not n and knickrahmen.ZUSATZ_KNICKEN not in str(alt or ""):
            return
        zu, fehlt = knickrahmen.zusatz_eintragen(alt, n, self.tabellen.get("zusatzarbeiten") or [], schneidweg.QUELLE)
        if zu != alt:
            felder["zusatz"] = zu
        if fehlt:
            self.f.meldung(f"Zusatzarbeit '{knickrahmen.ZUSATZ_KNICKEN}' fehlt in den Stammdaten.", fehler=True)

    def schweissnaht(self, zeilen=None, werte=None, dialog=None, stange=None):
        """Schweißnaht der markierten Positionen wählen (Dialog mit Querschnitt). werte = dict der Nahtfelder setzt
        sie ohne Dialog, stange dazu die Nahtlage der Lieferstange ('' = aus den Teilen, None = unverändert);
        dialog(d) bedient den Dialog statt exec (Tests, Bildschirmfotos). Ergebnis: True = gespeichert."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        zeilen = [z for z in zeilen if not kein_laserteil(self.positionen[z])]
        if not zeilen:
            self.f.meldung("Bitte zuerst die Rohrlaserteil-Position(en) markieren.", fehler=True)
            return False
        p = self.positionen[zeilen[0]]
        eigene = False          # Nahtwinkel je Position behalten (mehrere Positionen, Winkel nicht geändert)
        if werte is None:
            winkel = {(q.get("naht_winkel"), q.get("querschnitt_lage")) for q in (self.positionen[z] for z in zeilen)
                      if naht.vorgabe(q) == naht.FEST}
            d = NahtDialog(self, p, self.k.profile.get(p.get("profil_id")), len(zeilen),
                           naht.stange_eingetragen(self.kopf, p.get("profil_id"), p.get("werkstoff_id")),
                           unterschiedlich=len(winkel) > 1)
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                return False
            werte = d.werte()
            eigene = d.unterschiedlich and not d.winkel_geaendert
            if werte.get("naht_vorgabe") == naht.FEST and naht.form_von(d.profil) == "Rechteckrohr":
                stange = d.stange_wert() or ""       # "" = aus den Teilen (Eintrag löschen)
        if stange is not None:      # Nahtlage der Lieferstange gilt für die Rechteckrohr-Gruppen der Positionen
            self.naht_stange_setzen({(q.get("profil_id"), q.get("werkstoff_id")) for q in
                                     (self.positionen[z] for z in zeilen)
                                     if naht.form_von(self.k.profile.get(q.get("profil_id"))) == "Rechteckrohr"},
                                    stange or None, laden=False)
        for z in zeilen:
            q = self.positionen[z]
            for name, wert in self._naht_fuer(q, werte, eigene).items():
                if q.get(name) != wert:
                    self.db.position_aendern(q["id"], name, wert)
        self.f.meldung(f"Schweißnaht für {len(zeilen)} Position(en) gespeichert.")
        self.neu_laden()
        return True

    def _naht_fuer(self, q, werte, eigene=False):
        """Nahtfelder für Position q, wenn werte (aus dem Dialog der ersten markierten Position) für mehrere Positionen
        gelten (29.10.2026): eigene = Winkel und Lage einer Position mit fester Naht bleiben unverändert; sonst gibt
        es die Querschnittslage nur bei Rechteckrohr, und bei Quadrat- und Rechteckrohr liegt die Naht auf einer
        Seitenmitte (0°, 90°, 180°, 270°), auch wenn der Winkel von einem Rundrohr kommt."""
        w = dict(werte)
        if w.get("naht_vorgabe") != naht.FEST:
            return w
        if eigene and naht.vorgabe(q) == naht.FEST and q.get("naht_winkel") is not None:
            return dict(w, naht_winkel=q.get("naht_winkel"), querschnitt_lage=q.get("querschnitt_lage"))
        profil = self.k.profile.get(q.get("profil_id"))
        form = naht.form_von(profil)
        if form != "Rechteckrohr":
            w["querschnitt_lage"] = None
        if form in ("Quadratrohr", "Rechteckrohr") and w.get("naht_winkel") is not None:
            mitte = naht.wirksamer_winkel(profil, w["naht_winkel"])
            w["naht_winkel"] = mitte if mitte is not None else naht.normieren(round(
                naht.normieren(w["naht_winkel"]) / 90) * 90)
        return w

    def naht_stange_setzen(self, gruppen, wert, laden=True):
        """Nahtlage der Lieferstange (Breitseite/Schmalseite, None = aus den Teilen) für Gruppen {(Profil, Werkstoff)}
        im Angebot speichern."""
        wahl = dict(self.kopf.get("naht_stangen") or {})
        for profil, werkstoff in gruppen:
            wahl[naht.gruppe_schluessel(profil, werkstoff)] = wert
        self.db.naht_stangen_speichern(self.id, wahl)
        self.kopf["naht_stangen"] = {s: w for s, w in wahl.items() if w} or None
        if laden:
            self.neu_laden()

    def zukaufteile(self, zeilen=None, werte=None, dialog=None):
        """Zukaufteile der markierten Positionen wählen (Dialog). werte = JSON (oder None) setzt sie ohne Dialog;
        dialog(d) bedient den Dialog statt exec (Tests, Bildschirmfotos). Ergebnis: True = gespeichert."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        if not zeilen:
            self.f.meldung("Bitte zuerst die Position(en) markieren.", fehler=True)
            return False
        if werte is None:
            d = ZukaufDialog(self, self.db, self.positionen[zeilen[0]], len(zeilen))
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                return False
            werte = d.ergebnis
        for r in zeilen:
            self.db.position_aendern(self.positionen[r]["id"], "zukauf", werte)
        self.f.meldung(f"Zukaufteile für {len(zeilen)} Position(en) gespeichert.")
        self.neu_laden()
        return True

    def zukauf_schnell(self, zeilen=None, dialog=None, blech=True):
        """Neue Zukaufartikel schnell anlegen (z. B. Bleche): jeder wird eine eigene Position der Art Zukaufteil.
        Die Menge bezieht sich auf die erste markierte Position: 'je Satz' = gleicher Satz mit Menge als Stück je
        Satz, 'je Teil' = Menge × Stückzahl der markierten Position; ohne Markierung ist sie die Stückzahl.
        dialog(d) bedient den Dialog statt exec (Tests). Ergebnis: Anzahl neuer Positionen."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        bezug = self.positionen[zeilen[0]] if zeilen else None
        satz = str((bezug or {}).get("satz") or "").strip()
        if bezug is None:
            hinweis = "Jeder Artikel wird eine eigene Position (Zukaufteil) mit dieser Stückzahl."
        else:
            hinweis = (f"Jeder Artikel wird eine eigene Position (Zukaufteil). Bezug Pos. {bezug.get('pos') or ''}: "
                       + (f"je Satz = Stück je Satz {satz}, " if satz else "")
                       + "je Teil = Menge × Stückzahl dieser Position.")
        d = SchnellDialog(self, self.db, bool(satz), ganz=True, hinweis=hinweis, ohne_je=bezug is None, blech=blech)
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or not d.ergebnis:
            return 0
        nr = int(max((p["pos"] for p in self.positionen if isinstance(p.get("pos"), (int, float))), default=0))
        for x in d.ergebnis:
            nr += 10
            menge = int(x["menge"])
            p = dict(pos=nr, art=ZUKAUFTEIL, artikel=x["artikelnr"] or x["bezeichnung"], bezeichnung=x["bezeichnung"],
                     zukauf=json.dumps([dict(artikel_id=x["artikel_id"], menge=1, stand=self.db.zukauf_stand(
                         x["artikel_id"]))], ensure_ascii=False), **(x.get("position") or {}))
            if bezug is None:
                p["stueck"] = menge
            elif x["je"] == zukauf.JE_SATZ and satz:
                saetze = zukauf.bezugsmenge(dict(je=zukauf.JE_SATZ), bezug)
                p.update(satz=bezug.get("satz"), je_satz=menge, stueck=round(saetze * menge) or None)
            else:
                s = bezug.get("stueck")
                p["stueck"] = round(s * menge) if isinstance(s, (int, float)) and s > 0 else None
            self.db.position_neu(self.id, p)
        self.f.meldung(f"{len(d.ergebnis)} Zukaufartikel angelegt, je als eigene Position (Zukaufteil).")
        self.neu_laden()
        return len(d.ergebnis)

    def zukauf_ek(self, zeilen=None, preise=None, dialog=None):
        """Einkaufspreise der Zukaufteile im Angebot eintragen (z. B. Bleche aus dem STEP-Import ohne EK): markierte
        Positionen, ohne Markierung alle Zukaufteile ohne EK. Der Preis wird im Artikel beim Lieferanten des
        Preisstands (sonst zukauf.BLECH_LIEFERANT) als Staffelzeile 'ab Stückzahl der Position' gespeichert und die
        Position bekommt den neuen Preisstand. preise = [Preis je Zeile oder None] statt Dialog; dialog(d) bedient den
        Dialog statt exec (Tests). Ergebnis: Anzahl eingetragener Preise."""
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        liste = zukauf_ek.zeilen([(r, self.positionen[r]) for r in (zeilen or range(len(self.positionen)))],
                                 nur_fehlend=not zeilen)
        if not liste:
            self.f.meldung("Keine Zukaufteile ohne EK gefunden." if not zeilen
                           else "Die markierten Positionen haben keine Zukaufteile.", fehler=True)
            return 0
        if preise is None:
            d = zukauf_ek.EkDialog(self, liste)
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                return 0
            paare = d.ergebnis
        else:
            paare = [(z, w) for z, w in zip(liste, preise) if w]
        nummer = self.kopf.get("nummer") or ""
        geaendert = {}
        for z, preis in paare:
            menge = float(z["menge"])
            menge = int(menge) if menge.is_integer() else menge
            lief = z["lieferant"] or zukauf.BLECH_LIEFERANT["Blechteile"]
            self.db.zukauf_ek_eintragen(z["artikel_id"], preis, lief, ab=menge,
                                        bemerkung=f"EK aus Angebot {nummer} (ab {menge} St)".replace("  ", " "))
            p = self.positionen[z["zeile"]]
            liste_p = geaendert.setdefault(z["zeile"], zukauf.json_liste(p.get("zukauf")))
            liste_p[z["nr"]]["stand"] = self.db.zukauf_stand(z["artikel_id"], lief)
        for r, liste_p in geaendert.items():
            self.db.position_aendern(self.positionen[r]["id"], "zukauf", json.dumps(liste_p, ensure_ascii=False))
        self.f.meldung(f"EK für {len(paare)} Zukaufteil(e) eingetragen und im Artikel gespeichert.")
        self.neu_laden()
        return len(paare)

    # -------------------------------------------------------------- Rückgängig, Einfügen (Tastenkürzel)
    def rueckgaengig_anbieten(self, text, bericht=None):
        """Meldung nach einer Änderung ohne Rückfrage (Plan Bedienung B2) mit Knopf „Rückgängig“. Der Knopf nimmt
        nur genau diese Änderung zurück: kam inzwischen eine weitere dazu, verweist er auf Strg+Z."""
        self.verlauf.merken()
        stand = self.verlauf.stand

        def zurueck():
            self.verlauf.merken()
            if self.verlauf.stand is not stand or not self.verlauf.zurueck:
                self.f.meldung("Inzwischen wurde weiter geändert: bitte Bearbeiten → Rückgängig (Strg+Z) nutzen.",
                               fehler=True)
                return None
            return self.rueckgaengig()
        self.f.meldung(text, aktion=("Rückgängig", zurueck), bericht=bericht)
        return zurueck

    def rueckgaengig(self):
        return self._verlauf_schritt(self.verlauf.rueckgaengig, "Rückgängig", "Nichts mehr rückgängig zu machen.")

    def wiederholen(self):
        return self._verlauf_schritt(self.verlauf.wiederholen, "Wiederholt", "Nichts zu wiederholen.")

    def _verlauf_schritt(self, schritt, wort, nichts):
        was = schritt()
        if was is None:
            self.f.meldung(nichts, fehler=True)
            return None
        aktuell = self.pos_ansicht.currentIndex()
        self.pos_modell.bilder.clear()
        self.neu_laden()
        if aktuell.isValid() and aktuell.row() < self.pos_modell.rowCount():
            self.pos_ansicht.setCurrentIndex(self.pos_modell.index(aktuell.row(), aktuell.column()))
        self.f.meldung(f"{wort}: {was}")
        return was

    def _gesammelt(self, aendern):
        """Mehrere Zellen ändern, einmal neu rechnen, ein Schritt für Rückgängig."""
        self.verlauf.pause += 1
        self.pos_modell.blockSignals(True)
        try:
            n = aendern(self.pos_ansicht)
        finally:
            self.pos_modell.blockSignals(False)
            self.verlauf.pause -= 1
        if n:
            self.neu_laden()
        self.f.meldung(f"{n} Zelle(n) geändert." if n else "Keine bearbeitbare Zelle.", fehler=not n)
        return n

    def _einfuegen(self, text=None):
        if QApplication.focusWidget() is not self.pos_ansicht and text is None:
            return False                        # andere Tabelle: allgemeines Einfügen im Hauptfenster
        return self._gesammelt(lambda v: tastatur.einfuegen(v, text))

    def _ausschneiden(self):
        if QApplication.focusWidget() is not self.pos_ansicht:
            return False
        tastatur.kopieren(self.pos_ansicht)
        return self._gesammelt(tastatur.leeren)

    def stueck_aendern(self, zeilen=None, faktor=None, wert=None, dialog=None):
        """Stückzahl der markierten Positionen (ohne Markierung: aller aktiven) × Faktor oder = Wert setzen (Plan
        Arbeitsabläufe W4), ein Schritt für Rückgängig. Ohne faktor und wert fragt ein Dialog; dialog(d) bedient ihn
        statt exec (Tests). Ergebnis: Anzahl geänderter Positionen oder None (abgebrochen)."""
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return None
        if zeilen is None:
            zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        alle = not zeilen
        if alle:
            zeilen = [r for r, p in enumerate(self.positionen) if position_aktiv(p)]
        if not zeilen:
            self.f.meldung("Das Angebot hat noch keine Positionen.", fehler=True)
            return None
        if faktor is None and wert is None:
            from .mengen_dialog import StueckDialog
            d = StueckDialog(self, len(zeilen), alle)
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
                return None
            faktor, wert = d.faktor, d.wert
        from .mengen_dialog import neue_stueckzahl
        n = 0
        for r in zeilen:
            p = self.positionen[r]
            neu = neue_stueckzahl(p.get("stueck"), faktor, wert)
            if neu is not None and neu != p.get("stueck"):
                self.db.position_aendern(p["id"], "stueck", neu)
                n += 1
        if n:
            self.neu_laden()
        self.f.meldung(f"Stückzahl in {n} Position(en) geändert." if n else "Keine Stückzahl geändert.", fehler=not n)
        return n

    # -------------------------------------------------------------- Sätze (Patrick 31.10.2026)
    def satz_nachziehen(self, p, feld, wert):
        """Nach einer Eingabe in Stückzahl bzw. Stück je Satz einer Satzposition p (Stand vor der Eingabe): Stück je
        Satz bzw. Stückzahl ziehen mit (satz_menge). Ergebnis: Hinweis für die Meldung oder None."""
        from . import satz_menge
        if feld == "stueck":
            aend, hinweis = satz_menge.stueck_geaendert(p, self.positionen, wert)
        else:
            aend, hinweis = satz_menge.je_satz_geaendert(p, self.positionen, wert)
        for pid, f, w in aend:
            self.db.position_aendern(pid, f, w)
        return hinweis

    def saetze_anwenden(self, satz, n, je=None):
        """n Sätze (und Stück je Satz je = {Positions-ID: Wert}) in die Positionen des Satzes schreiben, ohne neu zu
        laden. Ergebnis: Anzahl geänderter Positionen."""
        from . import satz_menge
        aend = satz_menge.saetze_setzen(self.positionen, satz, n, je)
        for pid, f, w in aend:
            self.db.position_aendern(pid, f, w)
        return len({pid for pid, _, _ in aend})

    def satz_bearbeiten(self, zeile=None, satz=None, dialog=None):
        """Fenster „Satz bearbeiten“ (satz_dialog.py) für den Satz der Zeile: Anzahl Sätze und Stück je Satz, die
        Stückzahlen folgen; ein Schritt für Rückgängig. dialog(d) bedient das Fenster statt exec (Tests).
        Ergebnis: True = gespeichert."""
        from . import satz_menge
        from .satz_dialog import SatzDialog
        if satz is None:
            if zeile is None:
                zeilen = self._markierte_zeilen()
                zeile = zeilen[0] if zeilen else None
            p = self.positionen[zeile] if zeile is not None and 0 <= zeile < len(self.positionen) else None
            satz = satz_menge.name(p)
        if not satz or not satz_menge.satz_positionen(self.positionen, satz):
            r = zeile if zeile is not None else -1
            if 0 <= r < len(self.positionen) and baugruppe.zuordnung(self.positionen[r])[0]:
                return self.baugruppe_bearbeiten([r], dialog=dialog)    # Schweißbaugruppe: Anzahl Baugruppen dort
            self.f.meldung("Satz bearbeiten: Bitte eine Position markieren, die in einem Satz steht (Spalte Satz).",
                           fehler=True)
            return False
        d = SatzDialog(self, satz, self.positionen, nur_lesen=bool(self.fremd() or self.db.nur_lesen))
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or d.saetze is None:
            return False
        n = self.saetze_anwenden(satz, d.saetze, d.je)
        if n:
            self.neu_laden()
        self.f.meldung(f"Satz {satz}: {d.saetze} {'Satz' if d.saetze == 1 else 'Sätze'}, {n} Position(en) geändert."
                       if n else f"Satz {satz}: nichts geändert.")
        return True

    def positionen_loeschen(self):
        zeilen = sorted({i.row() for i in self.pos_ansicht.selectionModel().selectedIndexes()})
        if not zeilen:
            self.f.meldung("Bitte zuerst die Positionen markieren, die gelöscht werden sollen.", fehler=True)
            return
        # ohne Rückfrage, dafür „Rückgängig“ in der Einblendung (Plan Bedienung B2, Freigabe F1a)
        self.db.positionen_loeschen([self.positionen[r]["id"] for r in zeilen])
        self.neu_laden()
        self.rueckgaengig_anbieten(f"{len(zeilen)} Position(en) gelöscht.")

    # -------------------------------------------------------------- Reihenfolge der Positionen (29.10.2026)
    def positionen_hoch(self):
        return self.positionen_verschieben(reihenfolge.OBEN)

    def positionen_runter(self):
        return self.positionen_verschieben(reihenfolge.UNTEN)

    def positionen_verschieben(self, ziel, zeilen=None):
        """Markierte Positionen eine Zeile nach oben/unten bzw. an den Anfang/ans Ende (reihenfolge.verschieben):
        Baugruppen wandern mit ihren Teilen, Sätze mit ihren Positionen. Ergebnis: True = umgestellt."""
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return False
        zeilen = self._markierte_zeilen() if zeilen is None else list(zeilen)
        if not zeilen:
            self.f.meldung("Bitte zuerst die Positionen markieren, die verschoben werden sollen.", fehler=True)
            return False
        return self._reihenfolge_setzen(reihenfolge.verschieben(self.positionen, zeilen, ziel), zeilen)

    def _kopf_gezogen(self, logisch, _alt, neu):
        """Zeilenkopf per Drag & Drop verschoben: Position vor die Zeile setzen, die jetzt darunter steht."""
        if getattr(self, "_kopf_ordnet", False):
            return
        kopf = self.pos_ansicht.verticalHeader()
        vor = next((kopf.logicalIndex(v) for v in range(neu + 1, kopf.count())
                    if not self.pos_ansicht.isRowHidden(kopf.logicalIndex(v))), None)
        folge = None if self.fremd() or self.db.nur_lesen else \
            reihenfolge.einsetzen(self.positionen, logisch, vor)
        if folge is None:               # nicht erlaubt bzw. unverändert: Anzeige wie vorher
            QTimer.singleShot(0, self._gruppieren)
            if self.fremd() or self.db.nur_lesen:
                self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return
        QTimer.singleShot(0, lambda: self._reihenfolge_setzen(folge, [logisch]))

    def positionsnummern_vergeben(self):
        """Positionsnummern neu vergeben: 10, 20, 30 … in der Reihenfolge der Liste (reihenfolge.nummern)."""
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return False
        folge = reihenfolge.anzeige(self.positionen)
        if [p.get("pos") for p in reihenfolge.anordnung(self.positionen, folge, True)[0]] == \
                [self.positionen[i].get("pos") for i in folge] and folge == list(range(len(folge))):
            self.f.meldung("Positionsnummern sind schon 10, 20, 30 … in der Reihenfolge der Liste.")
            return False
        return self._reihenfolge_setzen(folge, neu_vergeben=True)

    def _reihenfolge_setzen(self, folge, markiert=(), neu_vergeben=False):
        """Neue Reihenfolge speichern (Liste alter Indizes, reihenfolge.py): nr und Positionsnummern, Staffeln je
        Position; ein aktueller Schnittplan bleibt aktuell (gleiche Stangen, neue Nummern). Ein Schritt für
        Rückgängig. Ergebnis: True = umgestellt."""
        if folge is None:
            self.f.meldung("Reihenfolge unverändert (schon ganz oben bzw. ganz unten).")
            return False
        neu, pos_neu = reihenfolge.anordnung(self.positionen, folge, neu_vergeben)
        geaendert = sum(self.positionen[i].get("pos") != p.get("pos") for i, p in zip(folge, neu))
        ergebnis = False                # Schnittplan veraltet ohnehin: so lassen
        if self.ergebnis and self.stand_optimierung() == "aktuell":
            ergebnis = reihenfolge.ergebnis_umstellen(self.ergebnis, self.positionen, folge, pos_neu)
            ergebnis["kennung"] = rechnen.eingabe_kennung(self.kopf, neu, self.k, self.tabellen, self.einst)
        self.db.positionen_ordnen(self.id, [(p["id"], p["pos"]) for p in neu],
                                  reihenfolge.staffel_schluessel(self.positionen, folge, pos_neu), ergebnis)
        self.neu_laden()
        neu_ix = {alt: k for k, alt in enumerate(folge)}
        zeilen = sorted(neu_ix[i] for i in markiert if i in neu_ix)
        if zeilen:                      # die verschobenen Positionen bleiben markiert
            c = max(self.pos_ansicht.currentIndex().column(), 0)
            self.pos_ansicht.setCurrentIndex(self.pos_modell.index(zeilen[0], c))
            auswahl = self.pos_ansicht.selectionModel()
            for r in zeilen:
                auswahl.select(self.pos_modell.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
            self.pos_ansicht.scrollTo(self.pos_modell.index(zeilen[0], c))
        self.rueckgaengig_anbieten("Positionsnummern neu vergeben (10, 20, 30 …)." if neu_vergeben else
                                   f"Reihenfolge geändert ({len(zeilen)} Position(en) verschoben"
                                   + (f", {geaendert} Positionsnummer(n) mitgezogen)." if geaendert else ")."))
        return True

    # ab so vielen Teilen rechnet die Optimierung im Hintergrund mit Fortschritt und Abbruch (Prüfbericht B-6)
    HINTERGRUND_AB_TEILEN = 150

    def _optimierung_rechnen(self):
        """rechnen.optimieren für dieses Angebot. Große Angebote rechnen in einem Hintergrund-Thread; das Fenster
        zeigt solange Fortschritt und Abbrechen (Eingaben gesperrt, damit sich die Daten nicht ändern). Ergebnis wie
        rechnen.optimieren; abgebrochen: rechnen.Abbruch."""
        args = (self.kopf, self.positionen, self.k, self.tabellen, self.einst)
        teile = sum(int(rechnen._n(p.get("stueck"))) for p in self.positionen if position_aktiv(p))
        if teile < self.HINTERGRUND_AB_TEILEN:
            return rechnen.optimieren(*args)
        stand, ende, abbrechen = dict(schritt=0, schritte=1, text="Gruppen bilden"), {}, threading.Event()

        def fortschritt(schritt, schritte, text):
            stand.update(schritt=schritt, schritte=max(schritte, 1), text=text)
            if abbrechen.is_set():
                raise rechnen.Abbruch()

        def lauf():
            try:
                ende["erg"] = rechnen.optimieren(*args, fortschritt=fortschritt)
            except BaseException as e:      # noqa: BLE001 – im Hauptthread weitergeben
                ende["fehler"] = e

        t = threading.Thread(target=lauf, name="Optimieren", daemon=True)
        t.start()
        dlg = QProgressDialog("Optimieren …", "Abbrechen", 0, 1000, self)
        dlg.setWindowTitle("Optimieren")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(400)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        start = time.monotonic()
        while t.is_alive():
            t.join(0.03)
            if dlg.wasCanceled() and not abbrechen.is_set():
                abbrechen.set()
                dlg.setLabelText("Wird abgebrochen … (nach der laufenden Abmessung)")
            elif not abbrechen.is_set():
                dlg.setValue(int(1000 * stand["schritt"] / stand["schritte"]))
                dlg.setLabelText(f"{stand['text']}\n{teile} Teile · {time.monotonic() - start:.0f} s")
            QApplication.processEvents(QEventLoop.AllEvents, 30)
        dlg.close()
        if "fehler" in ende:
            raise ende["fehler"]
        return ende["erg"]

    def optimieren(self, automatisch=False):
        """Optimieren und speichern. automatisch=True (W1): Fehler nur in der Statuszeile, Meldung „automatisch“."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            erg = self._optimierung_rechnen()
        except rechnen.Abbruch:
            QApplication.restoreOverrideCursor()
            self.f.meldung("Optimieren abgebrochen, nichts gespeichert.")
            return False
        except ValueError as e:
            QApplication.restoreOverrideCursor()
            if automatisch:
                self.f.meldung(f"Automatisch optimieren nicht möglich: {e}", fehler=True)
            else:
                QMessageBox.warning(self, "Optimieren", str(e))
            return False
        except AssertionError as e:   # Kontrolle der Optimierung angeschlagen: nie ein falsches Ergebnis speichern
            QApplication.restoreOverrideCursor()
            if automatisch:
                self.f.meldung(f"Automatisch optimieren: Kontrolle hat angeschlagen ({e}), bitte F9.", fehler=True)
            else:
                QMessageBox.critical(self, "Optimieren", f"Die Kontrolle der Optimierung hat angeschlagen: {e}")
            return False
        QApplication.restoreOverrideCursor()
        if erg["neue_profile"]:
            self.db.profile_anlegen(erg["neue_profile"])
            erg["kennung"] = rechnen.eingabe_kennung(self.kopf, self.positionen, self.db.kontext(), self.tabellen,
                                                     self.einst)
        self.db.ergebnis_speichern(self.id, erg, von_hand=not automatisch)
        self.neu_laden()
        n_teile = sum(len(s["teile"]) for s in erg["stangen"])
        text = f"{len(erg['stangen'])} Stangen, {n_teile} Teile eingeplant"
        if erg["fehler"]:
            text += f", {sum(f['anzahl'] for f in erg['fehler'])} Teile nicht eingeplant (siehe Auswertung)"
        if erg["neue_profile"]:
            text += f", {len(erg['neue_profile'])} Profil(e) aus dem Namen angelegt"
        self.f.meldung(("Automatisch optimiert: " if automatisch else "") + text + ".")
        return True

    def laengen_zeigen(self, nur=None):
        """Vergleich der Lieferlängen im großen Fenster öffnen; nur = Indizes der Gruppen (eine Abmessung aus dem
        Material-Fenster), None = alle."""
        self.laengen_ansicht.setHtml(laengen_html(self.ergebnis, self.kopf, self.positionen, self.k, self.tabellen,
                                                  self.einst, nur))
        self.laengen_dialog.setWindowTitle("Lieferlängen: 6 m gegen 12 m" + (" – eine Abmessung" if nur else ""))
        self.laengen_dialog.show()
        self.laengen_dialog.raise_()
        self.laengen_dialog.activateWindow()

    def laenge_waehlen(self, link):
        """Link 'laenge:<Gruppe>:<Länge>' aus dem Vergleich der Lieferlängen: Länge für die Gruppe übernehmen (0 = wieder
        die Stangenlänge des Angebots), speichern und neu optimieren. 'mischung:<Gruppe>:<Länge>': Stangenbelegung
        des Vorschlags Mischen ansehen (mischung_zeigen)."""
        if link.startswith("mischung:"):
            return self.mischung_zeigen(link)
        try:
            _, i, laenge = link.split(":")
            vg = self.ergebnis["laengen"][int(i)]
            laenge = int(laenge)
        except (ValueError, IndexError, KeyError, TypeError):
            return False
        wahl = dict(self.kopf.get("laengenwahl") or {})
        if laenge:
            wahl[vg["schluessel"]] = laenge
        else:
            wahl.pop(vg["schluessel"], None)
        self.db.laengenwahl_speichern(self.id, wahl)
        self.neu_laden()
        ok = self.optimieren()
        if ok:
            self.f.meldung(f"{vg['profil']} / {vg['werkstoff']}: " + (
                f"{rechnen.m_text(laenge)}-m-Stangen übernommen, Schnittplan neu optimiert." if laenge else
                f"wieder mit {rechnen.m_text(vg['stange'])}-m-Stangen geplant, Schnittplan neu optimiert."))
        return ok

    def mischung_zeigen(self, link):
        """Stangenbelegung des Vorschlags Mischen (z. B. 10 × 12 m + 1 × 6 m) in einem eigenen Fenster, nur zum
        Ansehen: der Schnittplan bleibt (Patrick 28.10.2026)."""
        try:
            _, i, laenge = link.split(":")
            vg = self.ergebnis["laengen"][int(i)]
            laenge = int(laenge)
        except (ValueError, IndexError, KeyError, TypeError):
            return False
        stangen = rechnen.mischung_stangen(self.kopf, self.positionen, self.k, self.tabellen, self.einst, vg, laenge)
        if not stangen:
            self.f.meldung("Der Vorschlag Mischen gilt nicht mehr: bitte neu optimieren.", fehler=True)
            return False
        n_lang = sum(1 for s in stangen if s["stange"] == laenge)
        titel = (f"Vorschlag Mischen {vg['profil']}: {n_lang} × {rechnen.m_text(laenge)} m + "
                 f"{len(stangen) - n_lang} × {rechnen.m_text(vg['stange'])} m (nur Ansicht)")
        d = QDialog(self)
        d.setWindowTitle(titel)
        d.resize(1250, 760)
        lay = QVBoxLayout(d)
        hinweis = QLabel(f"<b>{titel}</b><br>Zugeschnittene {rechnen.m_text(laenge)}-m-Stangen erscheinen als ihre "
                         "Werkstücke. Nur ein Vorschlag: Schnittplan und Kalkulation bleiben unverändert.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        seite = StangenSeite(STANGEN_UEBERSICHT)
        seite.setzen([(s, None) for s in rechnen.anzeige_stangen(dict(stangen=stangen))])
        lay.addWidget(seite, 1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(d.reject)
        lay.addWidget(knoepfe)
        self.mischung_dialog = d          # Verweis halten (nicht modal)
        d.show()
        return True

    # -------------------------------------------------------------- Staffeln (staffel_seite.py)
    def staffel_neu(self):
        self.st_seite.neu()

    def staffeln_aus_angebot(self):
        return self.st_seite.aus_angebot()

    def staffeln_loeschen(self):
        self.st_seite.loeschen()

    def staffelpreise_rechnen(self):
        """Alle Stufen neu rechnen und speichern. Ergebnis: bepreiste Zeilen oder None (abgebrochen bzw. Angebot nur
        zum Ansehen: fremdes Angebot oder Lesemodus, F8)."""
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return None
        return self.st_seite.rechnen()

    def staffelpreise_aktuell(self):
        """Staffelpreise fürs Angebot; veraltete Stufen werden vorher neu gerechnet. None = abgebrochen."""
        return self.st_seite.aktuell()

    # -------------------------------------------------------------- Ausgabe (PDF, CSV)
    def _vor_ausgabe(self, pruefen=False, weiter="Weiter"):
        """Vor einer Ausgabe (Plan W7, eine Sammelrückfrage): veralteten Schnittplan ohne Rückfrage neu optimieren
        (ein Schnittplan, der nicht zum Angebot passt, ergäbe falschen Materialbedarf, B-10), dann höchstens eine
        Rückfrage. pruefen = ganzer Angebots-Check (Angebots-PDF, Verschickt), sonst nur die Fracht. Ergebnis: True =
        weiter; die Begründung beim Übergehen eines FEHLERS steht danach in self.check_uebergangen."""
        self.check_uebergangen = None
        if self.stand_optimierung() != "aktuell":
            if not self.optimieren(automatisch=self.f.stumm):
                return False
        punkte = self.freigabe_punkte()
        if not pruefen:
            punkte = [p for p in punkte if p.ziel == "fracht"]
        if not angebot_check.offen(punkte):
            return True
        if self.f.stumm:                        # Tests: Punkte melden, nicht fragen
            self.f.meldung("Angebots-Check: " + "; ".join(p.text for p in angebot_check.offen(punkte)), fehler=True)
            self.check_uebergangen = angebot_check.versand_eintrag(punkte, "")
            return True
        ok, begruendung = self.check_zeigen(weiter, punkte)
        if ok:
            self.check_uebergangen = angebot_check.versand_eintrag(punkte, begruendung)
        return ok

    def _ziel(self, zusatz, endung, mit_kunde=False):
        try:
            return self.f.angebot_ordner(self.kopf) / (ausgabe.dateiname(self.kopf, zusatz, mit_kunde) + endung)
        except OSError as e:
            QMessageBox.warning(self, "Ablage", f"Der Ordner des Angebots lässt sich nicht anlegen:\n{e}")
            return None

    def _schreiben(self, art, pfad, schreiben, oeffnen=True):
        """Datei schreiben und öffnen (oeffnen=False: nur schreiben). Ergebnis: Pfad oder None."""
        if pfad is None:
            return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            schreiben(pfad)
        except PermissionError:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, art, f"Die Datei konnte nicht gespeichert werden:\n{pfad}\n\n"
                                "Ist sie noch in einem anderen Programm geöffnet?")
            return None
        QApplication.restoreOverrideCursor()
        self.f.meldung(f"{art} gespeichert: {pfad}")
        if oeffnen:
            self.f.datei_oeffnen(pfad)
        return pfad

    def _kalk_info_setzen(self):
        if self.kalk_kompakt.isChecked():
            text = "kompakte Übersicht, alle Spalten ohne Häkchen „Kompakt“"
        else:
            n = leere_ausblenden(self.kalk_ansicht, self.kalk, KALK_IMMER)
            text = "Beträge auf 2 Stellen (genauer Wert im Tooltip)" + (f" · {n} Spalten ohne Werte ausgeblendet" if n else "")
        self.kalk_info.setText(f"{len(self.kalk.zeilen)} Positionen · {text}")

    def _kompakt_umschalten(self, an, merken=True):
        self.kompakt_ansicht.setVisible(an)
        self.kalk_ansicht.setVisible(not an)
        if merken:
            self.db.einstellung_setzen(KOMPAKT_EINSTELLUNG, bool(an))
            self._kalk_info_setzen()

    def _unter_haken(self, an):
        """Häkchen „Zusatzarbeiten unter Position“ (Positionsliste und kompakte Kalkulation, gleiche Einstellung)."""
        c = QCheckBox("Zusatzarbeiten unter Position")
        c.setToolTip("Unter jeder Position je Arbeitsschritt eine Zeile: Programmieren, Gewinde, Zusatzarbeiten und "
                     "Zukaufteile mit Menge, Preis je Einheit, € je Teil und € der Position.\nDoppelklick auf die "
                     "Zeilen: Zusatzarbeiten der Position bearbeiten.")
        c.setChecked(an)
        c.toggled.connect(self._unter_umschalten)
        return c

    def _unter_umschalten(self, an):
        for c in (getattr(self, "unter_haken_pos", None), getattr(self, "unter_haken_kalk", None)):
            if c is not None and c.isChecked() != an:
                c.blockSignals(True)
                c.setChecked(an)
                c.blockSignals(False)
        self.pos_unter.setzen(an)
        self.kompakt_unter.setzen(an)
        if not self.db.nur_lesen:
            self.db.einstellung_setzen(unterzeilen.EINSTELLUNG, bool(an))

    def _kompakt_unter_texte(self, r):
        modell = self.kompakt_ansicht.model()
        q = modell.mapToSource(modell.index(r, 0)).row() if hasattr(modell, "mapToSource") else r
        return self.unter_texte.get(self.kompakt.zeilen[q]["zeile"], ()) if 0 <= q < len(self.kompakt.zeilen) else ()

    def _kompakt_doppelklick(self, index):
        modell = self.kompakt_ansicht.model()
        r = modell.mapToSource(index).row() if hasattr(modell, "mapToSource") else index.row()
        if 0 <= r < len(self.kompakt.zeilen):
            self.zur_position(zeile=self.kompakt.zeilen[r]["zeile"])

    def _rechnung(self):
        """rechnen.kalkulation für dieses Angebot. Während neu_laden wird sie nur einmal gerechnet; jeder Aufrufer
        bekommt eine eigene Kopie (die Eingaben ändern sich innerhalb eines Neuladens nicht)."""
        merken = getattr(self, "_kalk_merken", None)
        if merken is None:
            return rechnen.kalkulation(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen, self.einst)
        if "ergebnis" not in merken:
            merken["ergebnis"] = rechnen.kalkulation(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen,
                                                     self.einst)
        return copy.deepcopy(merken["ergebnis"])

    def angebot_daten(self, staffeln=True):
        """Inhalt des Angebots mit aktuellen Staffelpreisen (None = abgebrochen); staffeln=False: ohne."""
        sp = self.staffelpreise_aktuell() if staffeln else ()
        if sp is None:
            return None
        zeilen, _ = self._rechnung()
        ang = ausgabe.angebot(self.kopf, self.positionen, zeilen, self.k, self.einst, sp, ergebnis=self.ergebnis)
        ang["anschrift"] = ausgabe.anschrift(self.db.kunde(self.kopf.get("kundennr")))
        ang["ansprechpartner"] = teilen.mitarbeiter(self.db, self.kopf["bearbeiter"]) if self.kopf.get("bearbeiter") else {}
        return ang

    def angebot_pdf(self, oeffnen=True, daten=None):
        """Angebots-PDF schreiben (oeffnen=False: nicht anzeigen), im Versandverlauf merken. daten = {} bekommt
        'netto'. Ergebnis: Pfad oder None."""
        if not self.nummer_endgueltig("Angebots-PDF"):
            return None
        if not any(position_aktiv(p) for p in self.positionen):
            self.f.meldung("Das Angebot hat keine Positionen.", fehler=True)
            return None
        # Angebots-Check (Plan A2/W7): eine Sammelrückfrage, nur wenn FEHLER oder WARNUNG offen sind
        if not self._vor_ausgabe(pruefen=not self.fremd(), weiter="Angebot erstellen"):
            return None
        uebergangen = self.check_uebergangen
        ang = self.angebot_daten()
        if ang is None:
            return None
        pfad = self._schreiben("Angebot", self._ziel("Angebot", ".pdf"),
                               lambda p: pdf.angebot_pdf(p, self.kopf, ang, self.einst), oeffnen)
        if daten is not None:
            daten["netto"] = ang.get("netto")
        if pfad is not None and not self.fremd():     # Angebot eines Kollegen: nur ansehen, nichts festschreiben
            self.preise_festschreiben()
            eintrag = dict(datum=datetime.date.today().isoformat(), netto=ang["netto"], datei=Path(pfad).name)
            zeilen, _ = self._rechnung()        # Preis je kg je Position für die Plausibilität späterer Angebote
            eintrag["kennwerte"] = plausibel.kennwerte(self.positionen, zeilen, self.k)
            if uebergangen:
                eintrag["check"] = uebergangen
            self.db.versand_merken(self.id, eintrag)
            if not (self.db.angebot(self.id) or {}).get("vorgang"):     # Entwurf -> Verschickt (sonst bleibt er)
                self.db.vorgang_setzen(self.id, "Verschickt")
                self.f.angebote.neu_laden()
        return pfad

    def angebot_mail(self, dialog=None, ausfuehren=None):
        """Angebot per E-Mail (Vorschlag V1, 31.10.2026): Angebots-PDF erstellen, dann Fenster mit Empfänger, Betreff
        und Text; „In Outlook öffnen“ (als Antwort auf die Anfrage-Mail, wenn sie als .msg im Angebotsordner liegt)
        oder E-Mail-Datei. Vermerk im Versandverlauf (art 'mail'). dialog(d) bedient das Fenster statt exec,
        ausfuehren ersetzt den Outlook-Aufruf (Tests)."""
        from . import angebot_mail
        from . import mail as mail_
        from .angebot_mail_dialog import AngebotMailDialog
        if self.fremd():
            self.f.meldung("Angebot per E-Mail nur für eigene Angebote.", fehler=True)
            return None
        daten = {}
        pfad = self.angebot_pdf(oeffnen=False, daten=daten)
        if pfad is None:
            return None
        try:
            ordner = self.f.angebot_ordner(self.kopf)
        except OSError:
            ordner = Path(pfad).parent
        anfrage = None
        for p in angebot_mail.anfrage_mails(ordner):
            m = mail_.lesen(p)
            if m is not None:
                anfrage = (p, m)
                break
        d = AngebotMailDialog(self, self.kopf, self.db.kunde(self.kopf.get("kundennr")), self.einst, pfad, anfrage,
                              self._ziel("Angebot E-Mail", ".eml"), self.f.datei_oeffnen, ausfuehren,
                              netto=daten.get("netto"))
        (dialog(d) if dialog else d.exec())
        if d.eintrag:
            self.db.versand_merken(self.id, d.eintrag)
            self.kopf["versand"] = (self.db.angebot(self.id) or {}).get("versand") or []
        if d.meldung:
            self.f.meldung(d.meldung)
        return d

    def auftragsbestaetigung_pdf(self, abweichung_ok=None):
        """Auftragsbestätigung als PDF (Plan 29.10.2026 1c): Layout und Preise des Angebots (festgeschrieben),
        bestellte Mengen ohne Staffelpreise, Bestellnummer und Liefertermin aus „Beauftragt“. Noch nicht beauftragt:
        Rückfrage, dann Vorgang Beauftragt. Weicht die Summe vom zuletzt verschickten Angebot ab, fragt das Programm
        nach (abweichung_ok: Antwort ohne Fenster). Vermerk im Versandverlauf (art 'ab') mit der AB-Nummer."""
        if self.fremd():
            self.f.meldung("Auftragsbestätigungen nur für eigene Angebote.", fehler=True)
            return None
        if not self.nummer_endgueltig("Auftragsbestätigung"):
            return None
        if not any(position_aktiv(p) for p in self.positionen):
            self.f.meldung("Das Angebot hat keine Positionen.", fehler=True)
            return None
        kopf = self.db.angebot(self.id) or {}
        if kopf.get("vorgang") != "Beauftragt":
            if self.f.stumm:
                self.f.meldung("Auftragsbestätigung: das Angebot ist noch nicht beauftragt.", fehler=True)
                return None
            if QMessageBox.question(self, "Auftragsbestätigung", "Das Angebot ist noch nicht beauftragt.\n\nJetzt "
                                    "als beauftragt markieren (Bestellnummer und Liefertermin) und die "
                                    "Auftragsbestätigung erstellen?") != QMessageBox.Yes:
                return None
            if not self.f.angebote.vorgang_setzen("Beauftragt", angebot_id=self.id):
                return None
            kopf = self.db.angebot(self.id) or {}
        if not self._vor_ausgabe(weiter="Auftragsbestätigung erstellen"):
            return None
        ang = self.angebot_daten(staffeln=False)
        if ang is None:
            return None
        verschickt = [e for e in kopf.get("versand") or () if isinstance(e, dict) and not e.get("art")
                      and e.get("netto") is not None]
        if verschickt and abs(verschickt[-1]["netto"] - ang["netto"]) > 0.005:
            frage = (f"Die Summe weicht vom zuletzt verschickten Angebot ab:\n\nAngebot "
                     f"{ausgabe.datum_text(verschickt[-1].get('datum'))}: {ausgabe.euro_text(verschickt[-1]['netto'])} € "
                     f"netto\nAuftragsbestätigung: {ausgabe.euro_text(ang['netto'])} € netto\n\nTrotzdem erstellen?")
            if abweichung_ok is None:
                abweichung_ok = not self.f.stumm and QMessageBox.question(
                    self, "Auftragsbestätigung", frage) == QMessageBox.Yes
            if not abweichung_ok:
                return None
        try:
            nr = angebotsnummern.ab_nummer(self.db, kopf)
        except OSError as e:
            QMessageBox.warning(self, "Auftragsbestätigung", f"Keine AB-Nummer: {e}")
            return None
        ab = dict(nummer=nr, datum=datetime.date.today().isoformat(), bestellung=kopf.get("auftragsnr"),
                  liefertermin=kopf.get("liefertermin"), text=self.einst.get("ab_text") or "")
        pfad = self._schreiben("Auftragsbestätigung", self._ziel("Auftragsbestätigung", ".pdf"),
                               lambda p: pdf.auftragsbestaetigung_pdf(p, self.kopf, ang, self.einst, ab))
        if pfad is not None:
            self.db.versand_merken(self.id, dict(art="ab", datum=ab["datum"], nummer=nr, netto=ang["netto"],
                                                 datei=Path(pfad).name))
            self.kopf["versand"] = (self.db.angebot(self.id) or {}).get("versand")
            self.f.meldung(f"Auftragsbestätigung {nr} erstellt.")
        return pfad

    def reklamation_erfassen(self, dialog=None):
        """Reklamation zu diesem Auftrag (reklamation_dialog.erfassen); die Nachkalkulation zeigt die Kosten gleich
        mit und speichert sie, wenn schon Ist-Werte erfasst sind. Ergebnis: id oder None."""
        from . import reklamation_dialog
        i = reklamation_dialog.erfassen(self.f, self.id, self, dialog)
        if i is not None:
            self._nachkalk.neu_laden()
            if self.kopf.get("nachkalkulation") and not self.db.nur_lesen:
                self._nachkalk._speichern()
        return i

    def etiketten_pdf(self, dialog=None):
        """Etiketten mit QR-Code je Position (etiketten_dialog.drucken). Ergebnis: Pfad oder None."""
        if not self.nummer_endgueltig("Etiketten"):
            return None
        from . import etiketten_dialog
        return etiketten_dialog.drucken(self.f, self.id, self, dialog)

    def preise_festschreiben(self):
        """Materialpreise und Schneiddaten, mit denen das Angebot gerade rechnet, im Angebot speichern (nach dem
        Angebots-PDF). Schon festgeschriebene Werte bleiben, neue Profile, Werkstoffe und Oberflächen kommen dazu."""
        pb = rechnen.preisbasis_aus(self.kopf, self.positionen, self.k, self.tabellen)
        # Nettosumme und Datum des verschickten Angebots: spätere Änderungen zeigt die Übersicht als Abweichung
        verkauf = self._verkauf()
        pb["verschickt"] = dict(netto=round(verkauf, 2), datum=pb["datum"]) if verkauf is not None else None
        alt = self.kopf.get("preisbasis")
        if isinstance(alt, dict) and rechnen.preisbasis_gleich(alt, pb) and alt.get("verschickt") == pb["verschickt"]:
            return
        self.db.preisbasis_speichern(self.id, pb)
        self.neu_laden()

    def preise_aktualisieren(self):
        """Festgeschriebene Preise auf die aktuellen Stammdaten setzen: ohne Rückfrage, mit „Rückgängig“ und der
        Liste der Abweichungen im Bericht (Plan Bedienung B2)."""
        abw = rechnen.preisbasis_abweichung(self.kopf, self.k_aktuell, self.tabellen_aktuell)
        vorher = self._verkauf()
        self.db.preisbasis_speichern(self.id, None)
        self.neu_laden()
        self.rueckgaengig_anbieten(
            f"Aktuelle Materialpreise und Schneiddaten übernommen. {preis_aenderung(vorher, self._verkauf())}",
            bericht=("Aktuelle Preise übernehmen", "Geänderte Preisgrundlagen:\n" + "\n".join(abw) + "\n\nEin bereits "
                     "verschicktes Angebots-PDF bleibt unverändert; erst das nächste Angebots-PDF schreibt die neuen "
                     "Preise wieder fest."))
        return True

    def werkstatt_pdf(self, gruppe=None):
        """Werkstattpapiere als PDF; gruppe = Abmessung aus dem Material-Fenster (rechnen.material_abmessungen): nur
        deren Stangen, Datei '<Nr> Werkstattpapiere <Profil>'."""
        if not self._vor_ausgabe():
            return None
        nur_bg = not (self.ergebnis and self.ergebnis["stangen"]) and baugruppe.baugruppen(self.positionen) and \
            not any(not kein_laserteil(p) for p in self.positionen)        # nur Baugruppen und Zukaufteile
        if not nur_bg and (not self.ergebnis or not self.ergebnis["stangen"]):
            self.f.meldung("Der Schnittplan ist leer. Bitte zuerst optimieren.", fehler=True)
            return None
        erg = self.ergebnis if self.ergebnis else rechnen.optimieren(self.kopf, self.positionen, self.k, self.tabellen,
                                                                     self.einst)
        name = "Werkstattpapiere"
        if gruppe is not None:
            erg = dict(erg, stangen=[s for s in erg["stangen"] if abmessung.gruppe_der_stange(s) == gruppe["gruppe"]])
            name += f" {gruppe['profil']}"
        wp = ausgabe.werkstatt(self.kopf, self.positionen, erg, self.k, self.tabellen)
        if gruppe is not None:          # nur der Schnittplan dieser Abmessung: ohne Zukaufteile und Schweißpläne
            wp = dict(wp, zukaufteile=[], schweissplan=[])
        elif self.kopf.get("vorgang") == "Beauftragt" and self.f.versand_an() and \
                self.db.einstellung("palettenschein_werkstatt") == "ja":
            from . import palettenschein        # Palettenscheine hinten anhängen (Plan Palettenbegleitschein F8a)
            z = palettenschein.zusammenstellen(self.db, self.id)
            wp = dict(wp, palettenscheine=palettenschein.seiten(z["kopf"], z["schein"], z["packliste"], z["gruppen"]))
        if gruppe is None:              # Montageblätter der Sätze und Baugruppen mit Steckverbindungen (A7)
            wp = dict(wp, montage=self.montageblaetter())
        wp = dict(wp, freigabe=self.freigabe_stand())
        aktuell = self.stand_optimierung() == "aktuell"
        return self._schreiben("Werkstattpapiere", self._ziel(name, ".pdf"),
                               lambda p: pdf.werkstatt_pdf(p, self.kopf, wp, aktuell, self.einst))

    def freigabe_stand(self):
        """Freigegebener Auftragsstand für die Werkstattpapiere (fertigung.stand_text) mit Positionen und stabilen IDs;
        None ohne Freigabe."""
        from . import fertigung
        if not self.f.fertigung_an():
            return None
        text, warnung = fertigung.stand_text(self.db, self.id, self.db.angebot(self.id), self.db.positionen(self.id))
        if not text:
            return None
        return dict(text=text, warnung=warnung, positionen=[
            dict(id=p["id"], pos=p.get("pos"), artikel=p.get("artikel"), bezeichnung=p.get("bezeichnung"),
                 stueck=p.get("stueck")) for p in self.positionen])

    def montageblaetter(self):
        """Montageblätter der Werkstattpapiere (A7): je Schweißbaugruppe und je Satz mit Steckverbindungen und Stößen
        aus der STEP-Datei die Montagefolge (steck_montage.montage_folge) mit Titel."""
        from . import satz3d, steck_montage as sm
        from .ansicht3d import entpacken
        roh = self.db.netze(self.id)
        netze = {}

        def netz(pid):
            if pid not in netze:
                netze[pid] = entpacken(roh.get(pid)) or {}
            return netze[pid]
        out = []

        def blatt(titel, idx, daten, stoesse):
            verb = satz3d.verbindungen_laden(daten, self.positionen, idx)
            if not verb or not stoesse:
                return
            pos = {self.positionen[i]["id"]: self.positionen[i] for i in idx}
            f = sm.montage_folge(pos, verb, stoesse, {pid: netz(pid) for pid in pos if pid in roh})
            if f:
                out.append(dict(f, titel=titel))
        for bg_id, (i, bg) in baugruppe.baugruppen(self.positionen).items():
            p = self.positionen[i]
            blatt(f"Schweißbaugruppe Pos. {p.get('pos') or ''} {baugruppe.name(p, bg)}",
                  baugruppe.teile(self.positionen, bg_id), bg, bg.get("stoesse"))
        satz_daten = self.db.satz_daten(self.id)
        for satz in satz3d.saetze(self.positionen):
            daten = satz_daten.get(satz) or {}
            blatt(f"Satz {satz}", satz3d.satz_teile(self.positionen, satz), daten, daten.get("stoesse"))
        return out

    def kalkulation_pdf(self):
        if not self._vor_ausgabe():
            return None
        zeilen, summen = self._rechnung()
        aktuell = self.stand_optimierung() == "aktuell"
        material = rechnen.material_abmessungen(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen)
        muster = ausgabe.werkstatt(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen)["muster"] \
            if self.ergebnis and self.ergebnis.get("stangen") else None
        # Kalkulations-PDF 30.10.2026: gespeicherte Staffeln (nicht neu rechnen), Warnungen der Preis-Gegenprobe,
        # Maschine für den Rechenweg des ermittelten Stundensatzes
        staffel = (self.kopf.get("staffelpreise") or {}).get("zeilen") if self.stufen else None
        plausi = plausibel.punkte(self.positionen, zeilen, summen, self.k, self._preis_vergleich())
        maschine = self.k.maschinen.get(self.kopf.get("maschine"))
        return self._schreiben("Kalkulation", self._ziel("Kalkulation", ".pdf"),
                               lambda p: pdf.kalkulation_pdf(p, self.kopf, zeilen, summen, self.einst, aktuell,
                                                             material, muster, self.k.profile,
                                                             rechnen.laser_hinweise(self.positionen, self.k),
                                                             positionen=self.positionen, staffel=staffel,
                                                             plausi=plausi, maschine=maschine))

    CSV_ARTEN = {"kopf": "Angebotskopf", "positionen": "Angebotspositionen", "baugruppen": "Schweissbaugruppen"}

    def csv_export(self, art="alle", ordner=None):
        """CSV-Export als einzelne Dateien ('<Nr> Angebotskopf.csv', '<Nr> Angebotspositionen.csv', mit Baugruppen
        '<Nr> Schweissbaugruppen.csv'); art 'alle', 'kopf' oder 'positionen'. Den Ordner wählt der Bediener (Start:
        zuletzt gewählter Ordner, sonst Ordner des Angebots); ordner setzt ihn ohne Dialog, ohne Rückfragen (stumm)
        gilt der Ordner des Angebots. Der Export wird im Versandverlauf vermerkt (Schritt „Verschickt“ erst danach
        grün). Ergebnis: Liste der Pfade (art 'alle') bzw. Pfad, None bei Abbruch oder Fehler."""
        def fehler(text):
            QApplication.restoreOverrideCursor()
            if self.f.stumm:
                self.f.meldung("CSV-Export: " + text.replace("\n", " "), fehler=True)
            else:
                QMessageBox.warning(self, "CSV-Export", text)
            return None

        if not self._vor_ausgabe():
            return None
        if not any(position_aktiv(p) for p in self.positionen):
            return fehler("Das Angebot hat keine Positionen.")
        try:
            angebot_ordner = self.f.angebot_ordner(self.kopf)
        except OSError as e:
            return fehler(f"Der Ordner des Angebots lässt sich nicht anlegen:\n{e}")
        if ordner is None and not self.f.stumm:
            zuletzt = self.db.einstellung("csv_ordner")
            start = zuletzt if zuletzt and Path(zuletzt).is_dir() else str(angebot_ordner)
            ordner = QFileDialog.getExistingDirectory(self, "CSV-Export: Ordner wählen", start)
            if not ordner:
                return None
            self.db.einstellung_setzen("csv_ordner", ordner)
        ziel = Path(ordner) if ordner else angebot_ordner
        QApplication.setOverrideCursor(Qt.WaitCursor)
        geschrieben = []
        try:
            zeilen, summen = self._rechnung()
            bearbeiter = self.kopf.get("bearbeiter")
            kopfzeile, pos_zeilen = export.daten(
                self.kopf, self.positionen, self.ergebnis, zeilen, summen, self.k, self.tabellen, self.einst,
                kunde=self.db.kunde(self.kopf.get("kundennr")),
                ersteller=teilen.mitarbeiter(self.db, bearbeiter).get("name") if bearbeiter else None)
            arten = ["kopf", "positionen"] if art == "alle" else [art]
            bg_zeilen = export.baugruppen_zeilen(self.positionen, zeilen) if art == "alle" else None
            if bg_zeilen:
                arten.append("baugruppen")
            for a in arten:
                pfad = ziel / (ausgabe.dateiname(self.kopf, self.CSV_ARTEN[a]) + ".csv")
                if a == "kopf":
                    export.kopf_csv(pfad, kopfzeile)
                elif a == "positionen":
                    export.positionen_csv(pfad, pos_zeilen)
                else:
                    export.baugruppen_csv(pfad, bg_zeilen)
                geschrieben.append(pfad)
        except PermissionError:
            return fehler(f"Die Datei konnte nicht gespeichert werden:\n{pfad}\n\n"
                          "Ist sie noch in einem anderen Programm geöffnet?")
        except (OSError, ValueError) as e:
            return fehler(f"Der Export ist nicht gelungen:\n{ziel}\n\n{e}")
        QApplication.restoreOverrideCursor()
        if not self.db.nur_lesen and not self.fremd():      # Vermerk für die Schrittanzeige (Patrick 24.10.2026)
            self.db.versand_merken(self.id, dict(art="csv", datum=datetime.date.today().isoformat(),
                                                 datei=", ".join(p.name for p in geschrieben), ordner=str(ziel)))
            self.kopf["versand"] = (self.db.angebot(self.id) or {}).get("versand") or []
            self._schritte_setzen()
        self.f.meldung(f"CSV-Export gespeichert in {ziel}: " + ", ".join(p.name for p in geschrieben)
                       + f" ({len(pos_zeilen)} Positionen)")    # Einblendung (L14)
        return geschrieben if art == "alle" else geschrieben[0]

    def csv_kopf(self, ordner=None):
        return self.csv_export("kopf", ordner)

    def csv_positionen(self, ordner=None):
        return self.csv_export("positionen", ordner)

    # -------------------------------------------------------------- Material je Abmessung
    def material_einstellen(self, dialog=None):
        """Fenster 'Material …': Materialeinsatz und Materialwerte je Abmessung (Werkstoff, Oberfläche, Lieferlänge, Eigen-/
        Kundenmaterial, Meterpreis) und Handling Kundenmaterial; Änderungen werden an allen Positionen der Abmessung
        gespeichert und gehen so in die Kalkulation ein. Doppelklick und Kontextmenü öffnen die Zusatzfenster
        (abmessung_fenster.py); Schritte, die das Fenster schließen (zur Position, Positionen markieren, neu
        optimieren, 12-m-Vergleich, Materialanfrage), laufen danach (d.nachher, _material_nachher). dialog(d) bedient
        das Fenster statt exec (Tests). Ergebnis: Anzahl geänderter Abmessungen bzw. Werte oder None (nichts zu
        zeigen)."""
        from .meterpreis_dialog import MeterpreisDialog
        gruppen = rechnen.material_abmessungen(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen)
        if not gruppen:
            self.f.meldung("Material: keine Position mit Profil und Werkstoff im Angebot.", fehler=True)
            return None
        ohne_plan = not self.ergebnis or not self.ergebnis.get("stangen")
        d = MeterpreisDialog(self, gruppen, self.k, self.kopf,
                             lambda g: [z["laenge"] for z in rechnen.lieferlaengen(g["profil"], g["werkstoff"], self.k,
                                                                                   self.tabellen, auto=False)
                                        if rechnen._n(z.get("laenge")) > 0],
                             self.einst, veraltet=not ohne_plan and self.stand_optimierung() != "aktuell",
                             ohne_plan=ohne_plan, seite=self)
        if not (dialog(d) if dialog else d.exec() == QDialog.Accepted):
            return 0
        n = len(d.aenderungen) + len(d.kopf_aenderungen) + (d.vorgaben is not None)
        if n:
            self._material_speichern(d)
        if d.nachher:
            self._material_nachher(*d.nachher)
        return n

    def _material_speichern(self, d):
        n = len(d.aenderungen) + len(d.kopf_aenderungen) + (d.vorgaben is not None)
        vorher = self._verkauf()
        if d.vorgaben is not None:      # von Hand vorgegebene Stangen (Patrick 26.10.2026)
            self.db.stangen_vorgabe_speichern(self.id, d.vorgaben)
        for g, felder in d.aenderungen:
            for pid in g["ids"]:
                for feld, wert in felder.items():
                    self.db.position_aendern(pid, feld, wert)
        for feld, wert in d.kopf_aenderungen.items():
            self.db.angebot_aendern(self.id, feld, wert)
        self.neu_laden()
        plan = any(set(f) & {"werkstoff_id", "oberflaeche", "stange", "material_herkunft"} for _, f in d.aenderungen)
        self.f.meldung(f"Material: {n} Änderung(en) gespeichert. {preis_aenderung(vorher, self._verkauf())}"
                       + (" Werkstoff, Lieferlänge, Oberfläche oder Material geändert: bitte neu optimieren." if plan else
                          " Vorgegebene Stangen geändert: bitte neu optimieren." if d.vorgaben is not None else ""))

    def _material_nachher(self, aktion, wert=None):
        """Schritt aus dem Material-Fenster, nachdem es geschlossen ist: 'position' (wert = Bezug ref), 'markieren'
        (wert = Abmessung: alle ihre Positionen markieren), 'optimieren', 'laengen' (wert = Indizes im Vergleich der
        Lieferlängen), 'anfrage' (wert = Abmessung). Ergebnis wie die aufgerufene Methode."""
        if aktion == "position":
            return self.zur_position(ref=wert)
        if aktion == "markieren":
            zeilen = [r for r, p in enumerate(self.positionen) if p.get("id") in set(wert["ids"])]
            if not zeilen:
                return None
            self.zur_position(zeile=zeilen[0])
            auswahl = self.pos_ansicht.selectionModel()
            for r in zeilen[1:]:
                auswahl.select(self.pos_modell.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
            self.f.meldung(f"{wert['profil']}: {len(zeilen)} Position(en) markiert.")
            return zeilen
        if aktion == "optimieren":         # danach das Material-Fenster mit dem neuen Schnittplan wieder zeigen
            ok = self.optimieren()
            if ok and not self.f.stumm:
                self.material_einstellen()
            return ok
        if aktion in ("laengen", "anfrage") and self.stand_optimierung() != "aktuell":
            # z. B. gerade Werkstoff oder Lieferlänge geändert: Vergleich und Bedarf kämen aus dem alten Schnittplan
            self.f.meldung("Der Schnittplan passt nicht mehr zum Angebot: bitte zuerst neu optimieren.", fehler=True)
            return None
        if aktion == "laengen":
            return self.laengen_zeigen(wert)
        if aktion == "anfrage":
            return self.material_anfragen(gruppe=wert)
        return None

    # -------------------------------------------------------------- Materialanfrage
    def material_anfragen(self, dialog=None, ausfuehren=None, gruppe=None):
        """Materialanfrage an den Lieferanten (Dialog): Bedarf aus der Optimierung, Lieferant und Text prüfen, dann 'In Outlook öffnen' (gesendet wird nur in Outlook) oder 'Als E-Mail-Datei speichern'.
        dialog(d) bedient den Dialog statt exec, ausfuehren ersetzt den Outlook-Aufruf (Tests). gruppe = nur diese
        Abmessung (Material-Fenster, rechnen.material_abmessungen)."""
        from .materialanfrage_dialog import AnfrageDialog
        if not self.nummer_endgueltig("Materialanfrage"):
            return None
        if not self.ergebnis or not self.ergebnis.get("stangen"):
            self.f.meldung("Materialanfrage: bitte zuerst optimieren (der Stangenbedarf kommt aus der Optimierung).",
                           fehler=True)
            return None
        werte = rechnen.stangen_werte(self.ergebnis, self.kopf, self.positionen, self.k, self.tabellen)
        erg = self.ergebnis
        if gruppe is not None:
            paare = abmessung.lieferstangen(erg, gruppe["gruppe"], werte)
            erg, werte = dict(erg, stangen=[s for s, _ in paare]), [w for _, w in paare]
        from . import lager
        aus_lager = lager.aus_lager(self.db, self.id, self.ergebnis) if self.f.lager_an() else set()
        if aus_lager:               # Stangen aus dem Lager (reserviert) nicht anfragen
            paare = [(s, w) for s, w in zip(erg["stangen"], werte) if s["nr"] not in aus_lager]
            erg, werte = dict(erg, stangen=[s for s, _ in paare]), [w for _, w in paare]
            self.f.meldung(f"Materialanfrage: {len(aus_lager)} Stange(n) kommen aus dem Lager und werden nicht "
                           "angefragt.")
        zeilen = materialanfrage.bedarf(self.positionen, erg, self.k, self.tabellen, werte, self.kopf)
        if not zeilen:
            self.f.meldung("Materialanfrage: kein Eigenmaterial im Angebot (Kundenmaterial wird nicht angefragt).",
                           fehler=True)
            return None
        vorher = self.kopf.get("naht_stangen")
        d = AnfrageDialog(self, self.kopf, zeilen, self.k, self.einst,
                          materialanfrage.lieferanten(self.db.zeilen("zukauf_lieferanten")),
                          self._ziel("Materialanfrage", ".eml"), self.f.datei_oeffnen, ausfuehren,
                          lambda profil, werkstoff, seite: self.naht_stange_setzen({(profil, werkstoff)}, seite,
                                                                                   laden=False))
        (dialog(d) if dialog else d.exec())
        if self.kopf.get("naht_stangen") != vorher:     # Nahtlage geändert: Status der Positionen neu prüfen
            self.neu_laden()
        if d.meldung:
            self.f.meldung(d.meldung)
        return d

    # -------------------------------------------------------------- Lager
    def material_aus_lager(self, dialog=None):
        """Fenster „Material aus Lager“ (lager_seite.LagerplanDialog): nur beauftragte, optimierte Angebote.
        dialog(d) bedient das Fenster statt exec (Tests)."""
        from .lager_seite import LagerplanDialog
        if not self.f.lager_an():
            return None
        if self.kopf.get("vorgang") != "Beauftragt":
            self.f.meldung("Material aus Lager: erst nach „Beauftragt“ (Vorgang ▾).", fehler=True)
            return None
        if not self.ergebnis or not self.ergebnis.get("stangen") or self.stand_optimierung() != "aktuell":
            self.f.meldung("Material aus Lager: bitte zuerst (neu) optimieren.", fehler=True)
            return None
        d = LagerplanDialog(self)
        (dialog(d) if dialog else d.exec())
        return d

    def varianten_gruppen(self):
        """Varianten je Stangengruppe (varianten.gruppen); mit Lager-Variante, wenn das Lager eingeschaltet und der
        Schnittplan aktuell ist (Planung ohne Buchung)."""
        from . import lager, varianten
        if not self.ergebnis or self.stand_optimierung() != "aktuell":
            return []
        plan = None
        if self.f.lager_an():
            werte = rechnen.stangen_werte(self.ergebnis, self.kopf, self.positionen, self.k, self.tabellen)
            plan = lager.planen(self.db, self.id, self.ergebnis, werte)
        return varianten.gruppen(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen, self.einst, plan)

    def varianten_vergleichen(self, dialog=None):
        """Fenster „Varianten vergleichen“ (varianten_dialog). dialog(d) bedient das Fenster statt exec (Tests)."""
        from .varianten_dialog import VariantenDialog
        if not self.ergebnis or self.stand_optimierung() != "aktuell":
            self.f.meldung("Varianten vergleichen: bitte zuerst (neu) optimieren.", fehler=True)
            return None
        d = VariantenDialog(self, self)
        (dialog(d) if dialog else d.exec())
        return d

    # -------------------------------------------------------------- STEP-Import
    def _gezogene_dateien(self, ereignis):
        return step.step_dateien(self._gezogene_pfade(ereignis))

    def _ablage_hervorheben(self, an):
        for feld in (self.ablage_klein, self.ablage_gross):
            feld.hervorheben(an)

    def _gezogene_pfade(self, ereignis):
        urls = ereignis.mimeData().urls() if ereignis.mimeData().hasUrls() else []
        return [u.toLocalFile() for u in urls if u.isLocalFile()]

    @staticmethod
    def _dxf_pfade(pfade):
        return [p for p in pfade if str(p).lower().endswith(".dxf")]

    def dragEnterEvent(self, ereignis):
        pfade = self._gezogene_pfade(ereignis)
        if step.step_kandidaten(pfade) or self._dxf_pfade(pfade):   # ohne Ordnersuche, die stockt beim Ziehen
            ereignis.acceptProposedAction()
            self._ablage_hervorheben(True)

    def dragLeaveEvent(self, ereignis):
        self._ablage_hervorheben(False)

    def dropEvent(self, ereignis):
        self._ablage_hervorheben(False)
        pfade = self._gezogene_pfade(ereignis)
        dxf_pfade = self._dxf_pfade(pfade)
        rest = [p for p in pfade if p not in dxf_pfade]
        if dxf_pfade and not self.fremd() and not step.step_kandidaten(rest):    # DXF: je Datei Bleche (3E-9)
            step_drop(self.f, ereignis, self, lambda: self.blech_aus_dxf(dxf_pfade))
        elif step.step_kandidaten(rest) and not self.fremd():
            step_drop(self.f, ereignis, self, lambda: (self._drop_importieren(rest),
                                                       self.blech_aus_dxf(dxf_pfade) if dxf_pfade else 0))

    def dateien_waehlen(self, dateien=None):
        """Klick aufs Ablagefeld: STEP- und DXF-Dateien in einem Dateidialog wählen (auch beides zugleich); STEP geht
        in den STEP-Import, DXF ins DXF-Importfenster (Bleche bzw. Rohr aus Ansichten). dateien = statt des Dialogs
        (Tests). Ergebnis: (STEP-Dateien, DXF-Dateien) oder None (abgebrochen)."""
        if self.fremd():
            return None
        if dateien is None:
            dateien, _ = QFileDialog.getOpenFileNames(
                self, "STEP- und DXF-Dateien wählen", str(step_ablage.start_ordner(self.db)),
                "STEP und DXF (*.step *.stp *.STEP *.STP *.dxf *.DXF);;STEP-Dateien (*.step *.stp *.STEP *.STP);;"
                "DXF-Dateien (*.dxf *.DXF)")
            if not dateien:
                return None
        dxf_pfade = self._dxf_pfade(dateien)
        step_pfade = [p for p in dateien if p not in dxf_pfade]
        if step_pfade:
            step_ablage.ordner_merken(self.db, step_pfade)
            self.step_importieren(step_pfade)
        if dxf_pfade:
            self.db.einstellung_setzen("dxf_ordner", str(Path(dxf_pfade[0]).parent))
            self.blech_aus_dxf(dxf_pfade)
        return step_pfade, dxf_pfade

    def _drop_importieren(self, pfade):
        """Nach dem Drop (step_drop): Ordner durchsuchen und importieren."""
        dateien = step.step_dateien(pfade)
        if not dateien:
            self.f.meldung("Keine STEP-Dateien gefunden.", fehler=True)
            return None
        return self.step_importieren([str(d) for d in dateien])

    def importprofil(self):
        """Importprofil (STEP) des Kunden dieses Angebots oder None."""
        from . import importprofil
        return importprofil.fuer_kunde(self.db, (self.kopf or {}).get("kundennr"))

    def flach_bis(self, kundennr=None):
        """Grenze Flachstahl/Blech für die Messung: 0 = ebene flache Teile immer als Blech (Einstellung flach_als,
        Vorgabe, oder Importprofil des Kunden; kundennr = anderer Kunde als im Angebot), Flachstahl bleibt im
        Prüfdialog als andere Art wählbar."""
        from .stammdaten import FLACH_ALS
        from . import importprofil
        kundennr = kundennr if kundennr is not None else (getattr(self, "kopf", None) or {}).get("kundennr")
        profil = importprofil.fuer_kunde(self.db, kundennr)
        flach_als = (profil or {}).get("flach_als") or self.db.einstellung("flach_als") or FLACH_ALS[0]
        if flach_als == FLACH_ALS[0]:
            return 0
        return self.db.einstellung("flachstahl_bis") or 150

    def step_messen(self, dateien=None, mit_ablage=False, titel="STEP-Dateien wählen"):
        """STEP-Dateien wählen (ohne dateien) und mit STEP-Import.exe messen. Ergebnis: Messwerte (mit_ablage:
        (Messwerte, Pfad des abgelegten JSON-Ergebnisses)) oder None (abgebrochen, Fehler gemeldet)."""
        befehl = step.messprogramm(self.f.programmordner)
        if befehl is None:
            QMessageBox.warning(self, "STEP-Import", "STEP-Import.exe wurde nicht gefunden.\n\nDer Ordner 'STEP-Import' "
                                f"muss im Programmordner liegen:\n{self.f.programmordner}")
            return None
        if not dateien:
            # Start im Standardordner (Einstellungen), sonst im zuletzt benutzten STEP-Ordner
            dateien, _ = QFileDialog.getOpenFileNames(self, titel, str(step_ablage.start_ordner(self.db)),
                                                      "STEP-Dateien (*.step *.stp *.STEP *.STP)")
            if not dateien:
                return None
            step_ablage.ordner_merken(self.db, dateien)
        gross = step.grosse_dateien(step.step_dateien(dateien))
        if gross and not getattr(self.f, "stumm", False) and QMessageBox.question(
                self, "STEP-Import", gross, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return None
        step_einstellungen.anwenden(self.db)
        with tempfile.TemporaryDirectory() as tmp:
            liste, ausgabe = Path(tmp) / "liste.txt", Path(tmp) / "messwerte.txt"
            self.step_dateien_zuletzt = [str(d) for d in dateien]     # für die Kopie in den Angebotsordner
            liste.write_text("\n".join(str(d) for d in dateien), encoding="utf-8")
            netze, ergebnis = Path(tmp) / "netze", Path(tmp) / "messung.json"
            if not self._messen(befehl + ["--liste", str(liste), "--ausgabe", str(ausgabe), "--netze", str(netze),
                                          "--json", str(ergebnis), "--flachstahl-bis", str(self.flach_bis())]
                                + step_einstellungen.mess_argumente(self.db), len(dateien), ausgabe):
                return None
            if not ausgabe.exists():
                QMessageBox.warning(self, "STEP-Import", "Die Messung hat keine Messwerte geschrieben.")
                return None
            messwerte = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(ausgabe), netze), ergebnis)
            json_ablage = self._messung_ablegen(ergebnis) if mit_ablage else None
        return (messwerte, json_ablage) if mit_ablage else messwerte

    def step_importieren(self, dateien=None, werkstoff=None, stueck=None, als_satz=None, kunde_waehlen=False,
                         formulare=None, referenz=None, hinweis=None, werkstoff_text=None):
        """STEP-Dateien messen und übernehmen. formulare: gelesene Anfrageformulare (W6b/W6c, dict text/ocr/unsicher):
        Stückzahlen je
        Artikelnummer bzw. Dateiname werden im Prüfdialog vorbelegt. als_satz: Mehrteilige Dateien als Satz anlegen (None = wie im
        Prüfdialog im Feld „Sätze“ eingetragen, ohne Rückfragen ja). kunde_waehlen: Kunde oben im Prüfdialog wählen
        (neues Angebot aus STEP, Plan Bedienung B1); referenz = Vorschlag der Anfrage-Nr. des Kunden (aus dem
        Ordnernamen, Plan Angebotsablauf V5). Alles Weitere fragt der Prüfdialog selbst (fehlende Profile,
        doppelte Artikel); danach eine ruhige Meldung mit Bericht, mit „Übernehmen und Angebot (PDF)“ gleich das PDF.
        Aus einer E-Mail der Anfrage (28.10.2026): hinweis = Zeilen „Aus E-Mail/Formular“ oben im Prüfdialog; werkstoff_text
        = Mailtext, ein dort eindeutig genannter Werkstoff (mail.werkstoff) ersetzt die Vorgabe."""
        from . import importprofil
        ws_aus_mail = False
        profil = self.importprofil()
        vorgaben = importprofil.vorgaben(profil)
        if werkstoff is None:       # Vorgabe für Rohre und Profile (Importprofil, Einstellung), Bleche bleiben offen
            werkstoff = vorgaben.get("werkstoff") or self.db.einstellung("step_werkstoff") or None
            werkstoff = werkstoff if werkstoff in self.k.werkstoffe else None
            hinweis = list(hinweis or ())
            if werkstoff_text:      # Werkstoff aus der E-Mail: nur eindeutig, sonst nur Hinweis
                from . import mail
                ws, wort, kandidaten = mail.werkstoff(werkstoff_text, self.db.zeilen("werkstoffe"), werkstoff)
                if ws and ws in self.k.werkstoffe:
                    werkstoff, ws_aus_mail = ws, True
                    hinweis.append(f"Werkstoff {ws} (aus „{wort}“)")
                elif wort:
                    hinweis.append(f"Werkstoff „{wort}“ nicht eindeutig ({', '.join(kandidaten[:4])}) – bitte wählen")
        flach_gemessen = self.flach_bis()
        gemessen = self.step_messen(dateien, mit_ablage=True)
        if gemessen is None:
            return None
        messwerte, json_ablage = gemessen
        dateien = list(getattr(self, "step_dateien_zuletzt", None) or dateien or [])
        pfade = {Path(d).name: str(d) for d in step.step_dateien(dateien)}
        for m in messwerte:             # STEP-Datei je Teil (virtuelles Bauteil beim Profilwechsel, step_schenkel)
            if m.get("datei") in pfade:
                m["_pfad"] = pfade[m["datei"]]
        # Artikel aus Bauteilnamen, Normteile abwählen, Anbauteile wie im Importprofil des Kunden
        importprofil.anwenden(messwerte, profil, {n: self.db.einstellung(n) for n in ("step_benennung",
                                                                                     "step_normteile")})
        if "anbau_weglassen" in vorgaben:
            for m in messwerte:
                m.setdefault("_anbau_weglassen", vorgaben["anbau_weglassen"])
        katalog_namen = [z["name"] for z in self.db.zeilen("zusatzarbeiten") if z.get("name")
                         and z.get("aktiv") != "nein"]
        self._step_zusatz = [n for n in vorgaben.get("zusatz") or () if n in katalog_namen]
        for m in messwerte:             # Importprofil: Zusatzarbeiten für alle Teile (Plan Angebotsablauf V4)
            if self._step_zusatz:
                m.setdefault("_zusatz", list(self._step_zusatz))
        formular_bericht, pdf_neu = None, None
        if formulare:                   # Stückzahlen aus dem Anfrageformular (Plan W6b/W6c, Formular gilt)
            from . import pdf_art
            ws_zeilen = None if ws_aus_mail else self.db.zeilen("werkstoffe")
            wahl = {}                   # Datei -> Wahl im Prüfdialog (pdf_art.AUTO, FORMULAR, ZEICHNUNG, NICHT)

            def anwenden():
                aktiv = [pdf_art.zusammen(f, wahl.get(f.get("datei"), f.get("wahl", pdf_art.AUTO))) if f.get("seiten") else f
                         for f in formulare]
                erg = pdf_art.anwenden(messwerte, aktiv, ws_zeilen)
                n, unsicher = erg["formular"], erg["unsicher"]
                quelle = "der E-Mail" if all(f.get("mail") for f in formulare) else "dem Anfrageformular"
                return (f"Stückzahlen aus {quelle}: {n} Teil(e)"
                        + (f", davon {unsicher} unsicher (bitte prüfen)" if unsicher else "")
                        + (f"; ohne Treffer: {len(messwerte) - n}" if n < len(messwerte) else "")
                        + (f"; aus Zeichnungen (Schriftfeld): {erg['zeichnung']} Teil(e), bitte prüfen"
                           if erg["zeichnung"] else ""))

            def pdf_neu(datei, w):      # im Prüfdialog umgeschaltet: neu zuordnen, nichts neu lesen
                nonlocal formular_bericht
                wahl[datei] = w
                formular_bericht = anwenden()

            formular_bericht = anwenden()
        zukauf_liste = self.db.zukauf_artikel_liste()     # Bleche werden Zukaufteile (Dubletten aus dieser Liste)
        # Bleche: Blech-Werkstoffe und Richtpreis wie im Blech-Editor (nie die Rohrlaser-Daten)
        blech_daten = dict(werkstoffe={z["blech_werkstoff_id"]: z for z in self.db.zeilen("blech_werkstoffe")
                                       if z.get("blech_werkstoff_id")},
                           laserdaten=self.db.zeilen("blechlaser"),
                           einst=self.db.blech_einstellungen())
        kopieren = self.db.einstellung("step_kopieren") == "ja"    # STEP-Dateien in den Angebotsordner
        fehlend, doppelt = step.vorpruefung(messwerte, self.positionen, self.k)
        neue_profile, erneut, pdf_danach = True, False, False   # ohne Dialog: Profile anlegen, Doppelte überspringen
        gelernt = None
        if not self.f.stumm:        # Rohre und Bleche prüfen: je Teil übernehmen, Profil bzw. Zukaufartikel, Werkstoff
            from .step_dialog import StepPruefDialog
            # Stückzahl der Einzelteile im Dialog: 1 vorbelegt (Sätze zählt das Feld „Sätze“, Vorgabe 1 Satz)
            knick = {n: self.db.einstellung(f"knick_{n}") for n in ("z", "freistich", "k")}
            dlg = StepPruefDialog(self, messwerte, self.k, werkstoff, 1 if stueck is None else stueck,
                                  zukauf_liste, blech_daten["werkstoffe"], knick, step_kopieren=kopieren,
                                  maschine_3d=dreid.kann_3d(rechnen.maschine(self.kopf, self.k)),
                                  kunden=self.db.zeilen("kunden") if kunde_waehlen else None,
                                  kundennr=self.kopf.get("kundennr"), kunde_gewechselt=lambda nr: self._step_kunde_gewechselt(nr, messwerte),
                                  vorpruefung=lambda: step.vorpruefung(messwerte, self.positionen, self.k),
                                  lernen=True, maschine=rechnen.maschine(self.kopf, self.k),
                                  zusatzarbeiten=katalog_namen, zusatz_vorgabe=vorgaben.get("zusatz"),
                                  referenz=(self.kopf.get("kundenreferenz") or referenz or "") if kunde_waehlen
                                  or referenz else None, hinweis=hinweis,
                                  pdf_formulare=[f for f in formulare or () if f.get("seiten")], pdf_neu=pdf_neu,
                                  vorhandene_artikel=[p.get("artikel") for p in self.positionen])
            if dlg.exec() != QDialog.Accepted:
                self.f.meldung("STEP-Import abgebrochen.")
                return None
            kopieren = dlg.kopieren_haken.isChecked()
            fehlend, doppelt = step.vorpruefung(messwerte, self.positionen, self.k)
            neue_profile, erneut, pdf_danach = dlg.neue_profile_anlegen(), dlg.doppelte_eintragen(), dlg.pdf_danach
            werkstoff = dlg.werkstoff
            if dlg.referenz_text() and dlg.referenz_text() != (self.kopf.get("kundenreferenz") or None):
                self.db.angebot_aendern(self.id, "kundenreferenz", dlg.referenz_text())     # V5
                self.neu_laden()
            if kunde_waehlen and str(dlg.kundennr or "") != str(self.kopf.get("kundennr") or ""):
                self.kunde_waehlen(str(dlg.kundennr or ""))
                self.f.angebote.neu_laden()
                if self.flach_bis() != flach_gemessen:      # flache Teile gibt der Kunde anders vor: neu messen
                    self.f.meldung("Der gewählte Kunde gibt flache Teile anders vor (Importprofil) – die STEP-Dateien "
                                   "werden dafür neu gemessen.")
                    return self.step_importieren(dateien, None, stueck, als_satz, formulare=formulare,
                                                 referenz=referenz, hinweis=[h for h in hinweis or ()
                                                                             if not h.startswith("Werkstoff")],
                                                 werkstoff_text=werkstoff_text)
            if dlg.lernen_werte and not self.db.nur_lesen:      # B8: Korrekturen fürs nächste Mal
                gelernt = importprofil.merken(self.db, dlg.kundennr, dlg.lernen_werte)
        neue_profile = bool(fehlend) and neue_profile
        erneut = bool(doppelt) and erneut
        mehr = step.mehrteilig(messwerte, mit_blechen=True)
        if als_satz is None:        # Prüfdialog: Feld „Sätze“ je Datei (leer = Einzelpositionen); ohne Dialog als Satz
            als_satz = self.f.stumm and not any("_saetze" in m for m in messwerte)
        stege_bericht = self._stege_messen(messwerte)
        m = rechnen.maschine(self.kopf, self.k)
        erg = step.uebernehmen(messwerte, self.positionen, self.k, self.tabellen["gewinde"], m, werkstoff, stueck,
                               neue_profile, erneut, saetze=list(mehr) if als_satz else (), zukauf_liste=zukauf_liste,
                               fliessloch_laser=self.db.einstellung("fliessloch_laser"),
                               bohren_laser=self.db.einstellung("bohren_laser"), blech_daten=blech_daten,
                               biegerohr_faktor=self.db.einstellung("biegerohr_faktor"),
                               zusatz_katalog=self.db.zeilen("zusatzarbeiten"))
        self.db.profile_anlegen(erg["profile"])
        neue_ids = {schl: self.db.zukauf_speichern(None, werte, bezuege, bemerkung="aus STEP-Import angelegt")
                    for schl, (werte, bezuege) in erg["zukauf_neu"].items()}
        bleche_neu = [b for w, b in erg["zukauf_neu"].values() if not vollmaterial.ist_voll(w)]
        voll_neu = len(erg["zukauf_neu"]) - len(bleche_neu)
        ohne_ek = sum(not any(b.get("preise") for b in bezuege) for bezuege in bleche_neu)
        if voll_neu:
            erg["bericht"].append(f"{voll_neu} Zukaufartikel (Vollmaterial) neu angelegt, EK = Gewicht × €/kg "
                                  "(Vorgabe Tonnenpreis des Werkstoffs, bitte prüfen); Sägen als Zusatzarbeit.")
        if bleche_neu:
            erg["bericht"].append(f"{len(bleche_neu)} Zukaufartikel (Blech) neu angelegt" + (
                f", {ohne_ek} ohne EK (Blech-Werkstoff offen): bitte unter Zukaufartikel mit 'EK eintragen …' "
                "nachtragen." if ohne_ek else ", EK = Blech-Richtpreis (bitte durch das Angebot des Lieferanten "
                                              "ersetzen)."))
        for p in erg["positionen"]:
            verweis = p.pop("_zukauf", None)
            if verweis:
                aid = verweis.get("artikel_id") or neue_ids.get(verweis.get("neu"))
                p["zukauf"] = json.dumps([dict(artikel_id=aid, menge=1, stand=self.db.zukauf_stand(aid))],
                                         ensure_ascii=False)
            netz = p.pop("_netz", None)
            pid = self.db.position_neu(self.id, p)
            if netz:
                self.db.netz_speichern(pid, netz)
        self.db.protokoll_anhaengen(self.id, erg["protokoll"])
        alt = self.db.satz_daten(self.id)
        for satz, daten in (erg.get("satz_daten") or {}).items():    # Stöße je Satz für „Satz in 3D“
            self.db.satz_daten_speichern(self.id, satz, dict(alt.get(satz) or {}, **daten))
        self.neu_laden()
        if any(ist_baugruppe(p) for p in erg["positionen"]) and self.db.einstellung("gravur_artikel") == "ja":
            self.gravur_vorgeben({p["pos"] for p in erg["positionen"] if ist_baugruppe(p)}, erg["bericht"])
        if any(ist_baugruppe(p) for p in erg["positionen"]) and self.db.einstellung("schweiss_vk_step") == "ja":
            self._vorkalkulieren({p["pos"] for p in erg["positionen"] if ist_baugruppe(p)}, erg["bericht"])
        if json_ablage:
            erg["bericht"].append(f"Messergebnis (JSON): {json_ablage}")
        if gelernt:
            erg["bericht"].append(gelernt)
        if formular_bericht:
            erg["bericht"].append(formular_bericht)
        if stege_bericht:
            erg["bericht"].append(stege_bericht)
        if kopieren:
            erg["bericht"].append(self._step_kopieren(getattr(self, "step_dateien_zuletzt", [])))
        text = f"{len(erg['positionen'])} Position(en) in das Angebot übernommen."
        # ruhige Meldung statt Fenster (B1/B2); Einzelheiten hinter „Bericht …“ und im Meldungsverlauf. Offene
        # Bohrungen (Gewinde, Senkungen, Flowdrill): Knopf führt gleich zum Prüfen aller (Plan Angebotsablauf V3)
        offen = self.bohrungen_offen()
        aktion = None
        if offen and not pdf_danach:
            text += f" {len(offen)} Position(en) mit Bohrungen/Gewinde zu prüfen."
            aktion = ("Bohrungen prüfen …", lambda: self.bohrungen_alle_pruefen() if len(self.bohrungen_offen()) > 1
                      else self.bohrungen_pruefen(self.bohrungen_offen()[:1] or None))
        self.f.meldung(text, aktion=aktion, bericht=("STEP-Import", "\n".join(erg["bericht"])))
        if pdf_danach:
            self.angebot_pdf()
        return erg

    def _step_kunde_gewechselt(self, kundennr, messwerte):
        """Prüfdialog (B1): Kunde gewechselt. Importprofil des neuen Kunden auf die Messwerte anwenden (Benennung,
        Normteile, Zusatzarbeiten) und (Werkstoff-Vorgabe, Zusatzarbeiten) liefern. Der Angebotskopf folgt erst beim
        Übernehmen."""
        from . import importprofil
        profil = importprofil.fuer_kunde(self.db, kundennr)
        importprofil.anwenden(messwerte, profil, {n: self.db.einstellung(n) for n in ("step_benennung",
                                                                                     "step_normteile")})
        ws = importprofil.vorgaben(profil).get("werkstoff") or self.db.einstellung("step_werkstoff") or None
        # Zusatzarbeiten des alten Importprofils durch die des neuen ersetzen, von Hand gewählte bleiben (V4)
        katalog = {z["name"] for z in self.db.zeilen("zusatzarbeiten") if z.get("name") and z.get("aktiv") != "nein"}
        alt = getattr(self, "_step_zusatz", [])
        neu = [n for n in importprofil.vorgaben(profil).get("zusatz") or () if n in katalog]
        for m in messwerte:
            liste = [n for n in m.get("_zusatz") or () if n not in alt]
            liste += [n for n in neu if n not in liste]
            if liste:
                m["_zusatz"] = liste
            else:
                m.pop("_zusatz", None)
        self._step_zusatz = neu
        return (ws if ws in self.k.werkstoffe else None), neu

    def _virtuell_messen(self, pfad, ziel):
        """Eine STEP-Datei mit STEP-Import.exe --stege ziel messen (Winkel/U aus größerem Profil als virtuelles
        Bauteil, step_messung/step_schenkel). Ergebnis: Messwerte je Körper (mit 3D-Netz) oder None."""
        befehl = step.messprogramm(self.f.programmordner)
        if befehl is None or not Path(pfad).is_file():
            return None
        with tempfile.TemporaryDirectory() as tmp:
            ausgabe, netze = Path(tmp) / "messwerte.txt", Path(tmp) / "netze"
            if not self._messen(befehl + [str(pfad), "--ausgabe", str(ausgabe), "--netze", str(netze), "--stege", ziel,
                                          "--flachstahl-bis", str(self.flach_bis())]
                                + step_einstellungen.mess_argumente(self.db), 1, ausgabe) or not ausgabe.exists():
                return None
            return step.lade_netze(step.lies_messwerte(ausgabe), netze)

    def _stege_messen(self, messwerte):
        """Winkel/U, für die im Prüfdialog ein größeres Profil gleicher Form gewählt ist (Patrick 26.10.2026: „ein
        virtuelles Bauteil anlegen“): Teil + Stege 2 mm des größeren Profils neu messen und die Messwerte ersetzen;
        ohne Messung (Datei fehlt, Enden nicht eben) rechnet die Übernahme mit der Formel. Ergebnis: Berichtzeile."""
        auftraege = {}
        for i, m in enumerate(messwerte):
            if m.get("fehler") or not step.gewaehlt(m) or not m.get("_pfad") or not m.get("_profil"):
                continue
            pr = self.k.profile.get(m["_profil"]) or opt.profil_aus_name(m["_profil"])
            ziel = step.stege_ziel(m, pr)
            if ziel:
                auftraege.setdefault((m["_pfad"], ziel), []).append(i)
        gemessen, formel = 0, 0
        for (pfad, ziel), liste in auftraege.items():
            neu = {str(z.get("koerper")): z for z in self._virtuell_messen(pfad, ziel) or ()}
            for i in liste:
                z = neu.get(str(messwerte[i].get("koerper")))
                if z and step.virtuell_einsetzen(messwerte[i], z):
                    gemessen += 1
                else:
                    formel += 1
        if not gemessen and not formel:
            return None
        return (f"Winkel/U aus größerem Profil: {gemessen} Teil(e) als Bauteil mit Stegen 2 mm gemessen"
                + (f", {formel} mit der Formel gerechnet (Enden nicht eben oder Messung nicht möglich)" if formel else ""))

    def _step_kopieren(self, dateien):
        """STEP-Dateien in den Unterordner STEP des Angebotsordners kopieren. Ergebnis: Zeile für den Bericht."""
        try:
            ziel = self.f.angebot_ordner(self.kopf) / angebotsordner.STEP_ORDNER
        except OSError as e:
            return f"STEP-Dateien nicht kopiert: {e}"
        kopiert, fehler = angebotsordner.step_kopieren(dateien, ziel)
        text = f"{kopiert} STEP-Datei(en) nach {ziel} kopiert"
        return text + (" (nicht kopiert: " + "; ".join(fehler) + ")" if fehler else "")

    def _messung_ablegen(self, ergebnis):
        """Messergebnis im JSON-Format (versioniert, siehe step_messung/step_ergebnis.py) in die Ablage kopieren:
        '<Angebot> STEP-Messung <Datum Uhrzeit>.json'. Im Selbsttest (stumm) nicht. Ergebnis: Pfad oder None."""
        if self.f.stumm or not ergebnis.exists():
            return None
        ziel = self._ziel(f"STEP-Messung {datetime.datetime.now():%Y-%m-%d %H%M%S}", ".json")
        if ziel is None:
            return None
        try:
            ziel.write_bytes(ergebnis.read_bytes())
        except OSError as e:
            self.f.meldung(f"Messergebnis (JSON) nicht gespeichert: {e}")
            return None
        return ziel

    def editor_oeffnen(self, r):
        """Editor der Position in Zeile r: Baugruppe, Blech-Editor oder Schneidweg-Rechner (Teile-Editor); False, wenn
        die Position keinen hat."""
        if not 0 <= r < len(self.positionen):
            return False
        p = self.positionen[r]
        if ist_baugruppe(p):
            self.baugruppe_bearbeiten([r])
        elif ist_zukaufteil(p) and blech.lesen(p.get("technik")):
            self.blech_bearbeiten(r)
        elif not kein_laserteil(p) and p.get("profil_id") in self.k.profile:
            self.schneidweg_berechnen(r)
        else:
            self.f.meldung("Für diese Position gibt es keinen Teile-Editor (kein Laserteil).", fehler=True)
            return False
        return True

    def ansicht_3d(self, zeile=None):
        """3D-Ansicht der Positionen (Teile aus dem STEP-Import); zeigt zuerst die markierte Position."""
        from .step_dialog import Positionen3DDialog
        netze = self.db.netze(self.id)
        if not netze:
            self.f.meldung("3D-Ansicht: In diesem Angebot gibt es keine Teile mit 3D-Daten (sie entstehen beim "
                           "STEP-Import).", fehler=True)
            return None
        if zeile is None:
            i = self.pos_ansicht.currentIndex()
            zeile = i.row() if i.isValid() else next(r for r, p in enumerate(self.positionen) if p["id"] in netze)
        d = Positionen3DDialog(self, self.positionen, netze, zeile, bearbeiten=self.editor_oeffnen)
        if not self.f.stumm:
            d.exec()
        return d

    def satz_3d(self, zeile=None, satz=None, dialog=None):
        """Fenster „Satz in 3D“ (satz3d.py) für den Satz der markierten Position (ohne Satz: der einzige Satz des
        Angebots bzw. Auswahl). Mit OK: Längsnähte, Steckverbindungen (Schlitze, Nasen, Länge, Schneidweg) und die
        Daten des Satzes speichern. dialog(d) bedient das Fenster statt exec (Tests). Ergebnis: True = gespeichert."""
        from .satz3d import Satz3dDialog, saetze, satz_teile
        if satz is None:
            if zeile is None:
                i = self.pos_ansicht.currentIndex()
                zeile = i.row() if i.isValid() else None
            if zeile is not None and 0 <= zeile < len(self.positionen):
                satz = self.positionen[zeile].get("satz")
            alle = saetze(self.positionen)
            if not satz and len(alle) == 1:
                satz = alle[0]
            elif not satz and alle and not self.f.stumm:
                satz, ok = QInputDialog.getItem(self, "Satz in 3D", "Satz:", alle, 0, False)
                satz = satz if ok else None
            if not satz:
                if not alle:
                    self.f.meldung("Satz in 3D: Im Angebot gibt es keinen Satz (Teile mit Eintrag in der Spalte Satz, "
                                   "z. B. aus dem STEP-Import einer Baugruppe).", fehler=True)
                return False
        teile = [self.positionen[i] for i in satz_teile(self.positionen, satz)]
        bg = next((r for r, q in enumerate(self.positionen) if ist_baugruppe(q) and q.get("satz") == satz), None)
        if bg is not None or any(q.get("bg_knoten") for q in teile):
            self.f.meldung(f"Satz {satz} ist eine Schweißbaugruppe: Steckverbindungen und 3D im Editor der "
                           "Schweißbaugruppe.")
            return self.baugruppe_bearbeiten([bg if bg is not None else self.positionen.index(teile[0])],
                                             dialog=dialog)
        d = Satz3dDialog(self, satz, self.positionen, self.k.profile, self._vk_einstellungen(), self.db.netze(self.id),
                         self.db.satz_daten(self.id).get(satz), nur_lesen=bool(self.fremd() or self.db.nur_lesen))
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or not d.ergebnis or d.nur_lesen:
            return False
        vorab = self.teilen_anwenden(d.ergebnis)
        self.naehte_schreiben(d.ergebnis["naehte"])
        if "muster" in d.ergebnis:          # Häkchen „Satz als Muster“: alle Teile des Satzes
            for q in teile:
                self.db.position_aendern(q["id"], "muster", d.ergebnis["muster"])
        self.db.satz_daten_speichern(self.id, satz, d.ergebnis["daten"])
        hinweise = vorab + self.stecken_anwenden(d.ergebnis["stecken"]) + self.knicke_anwenden(d.ergebnis.get("knicke"))
        if d.ergebnis.get("saetze"):        # Anzahl Sätze geändert (31.10.2026): Stückzahlen folgen
            self.neu_laden()
            n = d.ergebnis["saetze"]
            if self.saetze_anwenden(satz, n):
                hinweise.append(f"Anzahl Sätze: {n}, Stückzahlen angepasst.")
        self.neu_laden()
        n = len(d.ergebnis["naehte"])
        self.f.meldung(f"Satz {satz} gespeichert." + (f" Längsnaht für {n} Teil(e) gesetzt." if n else "")
                       + "".join(f" {h}" for h in hinweise))
        return True

    def _teilergebnis(self, ausgabe_datei, anzahl):
        """Nach Abbruch: gibt es schon gemessene Dateien, fragen, ob sie übernommen werden sollen."""
        try:
            text = ausgabe_datei.read_text(encoding="utf-8") if ausgabe_datei else ""
            if text and not text.endswith("\n"):       # beim Abbruch halb geschriebene Zeile weglassen
                text = text[:text.rfind("\n") + 1]
                ausgabe_datei.write_text(text, encoding="utf-8")
            zeilen = text.splitlines()[1:]
        except OSError:
            zeilen = []
        n = len({z.split("\t", 1)[0] for z in zeilen if z.strip()})
        if not n or self.f.stumm:
            return False
        return QMessageBox.question(
            self, "STEP-Import", f"Messung abgebrochen. {n} von {anzahl} Dateien sind schon gemessen.\n\n"
            "Diese Dateien übernehmen?", QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes

    def _messen(self, befehl, anzahl, ausgabe_datei=None):
        """Messung als eigener Prozess mit Fortschrittsanzeige (Datei, Körper, Restzeit). True = Messung beendet
        oder nach Abbruch die schon gemessenen Dateien übernehmen (stehen in ausgabe_datei)."""
        proz = QProcess(self)
        fortschritt = QProgressDialog("STEP-Dateien werden gemessen …", "Abbrechen", 0, anzahl, self)
        fortschritt.setWindowModality(Qt.WindowModal)
        fortschritt.setMinimumDuration(0 if getattr(self.f, "step_drop_laeuft", False) else 300)   # nach einem Drop gleich zeigen
        schleife = QEventLoop()
        start, stand = time.monotonic(), dict(fertig=0, aus_speicher=0)

        def restzeit():
            n = stand["fertig"] - stand["aus_speicher"]
            if n < 1 or stand["fertig"] >= anzahl:
                return ""
            s = (time.monotonic() - start) / n * (anzahl - stand["fertig"])
            return f"\nRestzeit etwa {s / 60:.0f} min" if s >= 90 else f"\nRestzeit etwa {max(5, round(s, -1)):.0f} s"

        def ausgabe():
            for z in bytes(proz.readAllStandardOutput()).decode("utf-8", "replace").splitlines():
                if z.startswith("{"):           # je Körper (Messung mit Zeitlimit)
                    try:
                        d = json.loads(z)
                        text = f"Datei {d['datei']} von {d['dateien']}: {d['name']}"
                        if d.get("koerper"):
                            text += f"\nKörper {d['koerper']} von {d['koerper_n']}"
                        fortschritt.setLabelText(text + restzeit())
                    except (ValueError, KeyError, TypeError):
                        pass
                elif z.startswith("[") and "/" in z:
                    try:
                        stand["fertig"] = int(z[1:z.index("/")])
                        if z.endswith("aus dem Zwischenspeicher"):
                            stand["aus_speicher"] = stand["fertig"]
                        fortschritt.setValue(stand["fertig"] - 1 if stand["fertig"] < anzahl else anzahl - 1)
                        fortschritt.setLabelText(z + restzeit())
                    except ValueError:
                        pass
        proz.readyReadStandardOutput.connect(ausgabe)
        proz.finished.connect(schleife.quit)
        proz.errorOccurred.connect(lambda _: schleife.quit())
        abgebrochen = []
        fortschritt.canceled.connect(lambda: (abgebrochen.append(1), proz.kill()) if proz.state() != QProcess.NotRunning else None)
        umgebung = proz.processEnvironment()
        umgebung.insert("PYTHONIOENCODING", "utf-8")
        proz.setProcessEnvironment(umgebung)
        proz.start(befehl[0], befehl[1:])
        if proz.state() != QProcess.NotRunning or proz.waitForStarted(5000):
            schleife.exec()
        fortschritt.close()     # close() meldet auch 'canceled', darum zählt nur ein Abbruch bei laufender Messung
        if abgebrochen:
            return self._teilergebnis(ausgabe_datei, anzahl)
        if proz.exitStatus() != QProcess.NormalExit or proz.exitCode() not in (0, 1):
            fehler = bytes(proz.readAllStandardError()).decode("utf-8", "replace")[-800:]
            QMessageBox.warning(self, "STEP-Import", f"Die Messung ist fehlgeschlagen (Rückgabewert {proz.exitCode()})."
                                + (f"\n\n{fehler}" if fehler else ""))
            return False
        return True
