"""Spaltenbreite und Zeilenhöhe der Tabellen automatisch an den Inhalt anpassen.

Regeln (für alle Tabellen gleich, damit das Layout ruhig und übersichtlich bleibt):
- Spalte so breit wie Inhalt bzw. Kopf (Kopf höchstens zweizeilig, kein Wort abgeschnitten), höchstens MAX_BREITE.
- Beim ersten Füllen werden alle Spalten eingepasst, danach wachsen sie nur noch (nie schmaler), damit die Tabelle
  beim Tippen nicht springt.
- Eine Spalte, die der Benutzer mit der Maus breiter oder schmaler zieht, bleibt so, bis die Tabelle neu
  aufgebaut wird (Doppelklick auf den Spaltenrand passt sie wie bisher an).
- Zeilen mit langem Text werden höher (Text umgebrochen), höchstens MAX_ZEILEN Textzeilen; der Rest wird mit …
  gekürzt und steht vollständig im Tooltip. Zeilen ohne langen Text bleiben einzeilig, damit wenig gescrollt wird.
- Bei sehr vielen Zeilen (über MAX_ANZAHL) bleiben die Zeilen einzeilig (Geschwindigkeit).
- Die Spaltenbreite richtet sich nach den sichtbaren und höchstens PRUEF_ZEILEN Zeilen (Geschwindigkeit: die
  Angebotsliste mit 1.000 Angeboten brauchte sonst 4,6 s je Taste im Suchfeld; Performance-Audit F1, 23.10.2026).
  Ein sehr langer Eintrag weiter unten kann dann gekürzt sein, er steht vollständig im Tooltip.
- Eine Tabelle, die gerade nicht zu sehen ist (anderer Reiter), wird erst beim Zeigen eingepasst (Performance-Audit
  22.10.2026: das Einpassen verdeckter Tabellen kostete beim Angebots-PDF eines Angebots mit 200 Positionen ~20 s).
"""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication

MAX_BREITE = 260
MIN_BREITE = 40
MAX_ZEILEN = 3
MAX_ANZAHL = 500
PRUEF_ZEILEN = 100


def kopfbreite(ansicht, c):
    """Breite, die der Spaltenkopf mindestens braucht: höchstens zweizeilig, kein Wort abgeschnitten."""
    schrift = QFont(ansicht.horizontalHeader().font())
    schrift.setBold(True)           # Spaltenköpfe sind fett (STIL), sonst wird der Kopf abgeschnitten
    fm = QFontMetrics(schrift)
    titel = str(ansicht.model().headerData(c, Qt.Horizontal, Qt.DisplayRole) or "")
    woerter = [fm.horizontalAdvance(w) for w in titel.split()] or [0]
    return max(max(woerter), fm.horizontalAdvance(titel) / 2) + 20


def passende_breite(ansicht, c, max_breite=MAX_BREITE):
    inhalt = ansicht.sizeHintForColumn(c) + 8
    return int(min(max(kopfbreite(ansicht, c), inhalt, MIN_BREITE), max_breite))


class AutoGroesse(QObject):
    """Hält Spaltenbreiten und Zeilenhöhen einer QTableView passend zum Inhalt (Regeln oben).
    Wird an die Ansicht gehängt (ansicht.auto_groesse); Änderungen am Modell lösen die Anpassung gesammelt aus."""

    def __init__(self, ansicht, max_breite=MAX_BREITE, max_zeilen=MAX_ZEILEN, max_anzahl=MAX_ANZAHL):
        super().__init__(ansicht)
        self.ansicht, self.max_breite, self.max_zeilen, self.max_anzahl = ansicht, max_breite, max_zeilen, max_anzahl
        self.von_hand = set()          # vom Benutzer gezogene Spalten
        self.eingepasst = False        # erstes Einpassen mit Daten erledigt
        self._selbst = False
        self._offen = False            # Anpassen steht aus, bis die Tabelle zu sehen ist
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.anpassen)
        ansicht.setWordWrap(True)
        ansicht.setAlternatingRowColors(True)      # Zebra-Zeilen wie in den PDF-Listen
        ansicht.setTextElideMode(Qt.ElideRight)
        kopf = ansicht.horizontalHeader()
        kopf.sectionResized.connect(self._gezogen)
        kopf.setResizeContentsPrecision(PRUEF_ZEILEN)      # sizeHintForColumn: sichtbare + bis zu so viele Zeilen
        # Köpfe zweizeilig (Regel oben), sonst wird ein langer Kopf trotz passender Breite abgeschnitten
        kopf.setDefaultAlignment(Qt.AlignCenter | Qt.TextWordWrap)
        kopf.setMinimumHeight(max(kopf.minimumHeight(), 2 * kopf.fontMetrics().lineSpacing() + 12))
        m = ansicht.model()
        for signal in (m.modelReset, m.layoutChanged, m.rowsInserted, m.rowsRemoved, m.dataChanged, m.columnsInserted):
            signal.connect(self.spaeter)
        ansicht.auto_groesse = self
        ansicht.installEventFilter(self)
        self.spaeter()

    @staticmethod
    def _maus():
        return QGuiApplication.mouseButtons() != Qt.NoButton

    def _gezogen(self, c, alt, neu):
        # Ein- und Ausblenden (Breite 0) und die gestreckte letzte Spalte sind keine Benutzeränderung
        if self._selbst or not alt or not neu or not self._maus():
            return
        kopf = self.ansicht.horizontalHeader()
        if kopf.stretchLastSection() and c == kopf.logicalIndex(kopf.count() - 1):
            return
        self.von_hand.add(c)

    def spaeter(self, *_):
        self._timer.start()

    def eventFilter(self, obj, ereignis):
        if obj is self.ansicht and ereignis.type() == QEvent.Show and self._offen:
            self.anpassen()          # vor dem ersten Zeichnen: die Tabelle erscheint gleich passend
        return False

    def neu_einpassen(self):
        """Alles neu einpassen (auch schmaler), vom Benutzer gezogene Spalten vergessen."""
        self.von_hand.clear()
        self.eingepasst = False
        self.anpassen()

    def einpassen(self, spalten):
        """Nur diese Spalten neu einpassen (auch schmaler), z. B. gerade eingeblendete."""
        self._breiten(set(spalten), wachsen=False)
        self._zeilen()

    def anpassen(self):
        self._timer.stop()
        if self.ansicht.model() is None:
            return
        if not self.ansicht.isVisible():      # verdeckt: beim Zeigen nachholen (eventFilter)
            self._offen = True
            return
        self._offen = False
        if self.ansicht.model().rowCount() == 0:      # leere Tabelle: wenigstens die Spaltenköpfe ganz zeigen
            self._koepfe()
            return
        self._breiten(None, wachsen=self.eingepasst)
        self.eingepasst = True
        self._zeilen()

    def _breiten(self, nur, wachsen):
        a, m = self.ansicht, self.ansicht.model()
        kopf = a.horizontalHeader()
        letzte = kopf.logicalIndex(kopf.count() - 1) if kopf.stretchLastSection() else None
        self._selbst = True
        try:
            for c in range(m.columnCount()):
                if a.isColumnHidden(c) or c in self.von_hand or c == letzte or (nur is not None and c not in nur):
                    continue
                b = passende_breite(a, c, self.max_breite)
                if wachsen:
                    b = max(b, a.columnWidth(c))
                if b != a.columnWidth(c):
                    a.setColumnWidth(c, b)
        finally:
            self._selbst = False

    def _koepfe(self):
        a = self.ansicht
        kopf = a.horizontalHeader()
        letzte = kopf.logicalIndex(kopf.count() - 1) if kopf.stretchLastSection() else None
        self._selbst = True
        try:
            for c in range(a.model().columnCount()):
                if a.isColumnHidden(c) or c in self.von_hand or c == letzte:
                    continue
                b = int(min(max(kopfbreite(a, c), MIN_BREITE), self.max_breite))
                if b > a.columnWidth(c):
                    a.setColumnWidth(c, b)
        finally:
            self._selbst = False

    def _zeilen(self):
        a, m = self.ansicht, self.ansicht.model()
        kopf = a.verticalHeader()
        standard = kopf.defaultSectionSize()
        n = m.rowCount()
        if n > self.max_anzahl:
            return
        hoechst = max(standard, self.max_zeilen * a.fontMetrics().lineSpacing() + 8)
        for r in range(n):
            if a.isRowHidden(r):
                continue
            h = max(standard, min(a.sizeHintForRow(r), hoechst))
            if h != a.rowHeight(r):
                a.setRowHeight(r, h)
