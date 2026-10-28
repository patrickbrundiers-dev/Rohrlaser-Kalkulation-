"""Zusatzarbeiten als Unterzeilen unter der Position (Patrick 26.10.2026, Plan „Zusatzarbeiten unter der Position“,
Freigabe 1a 2a 3b 4b).

Mit dem Häkchen „Zusatzarbeiten unter Position“ steht unter jedem Artikel der Positionsliste und der kompakten
Kalkulation je Arbeitsschritt eine eingerückte Zeile mit den wichtigsten Angaben: Name (mit Zusatztext), Menge je
Teil, Preis je Einheit, Zeit, € je Teil, € der Position, eigen oder Fremdleistung. Die Werte kommen aus derselben
Rechnung wie die Kalkulation (rechnen.kalkulation), nichts wird doppelt gerechnet.

Reihenfolge wie in der Werkstatt (STUFEN): Programmieren, Gewinde, Nachbearbeitung (Senken, Bohren, Entgraten,
Biegen, Sägen …), Montage (Zukaufteile, Schweißen), Oberfläche, Prüfung, Verpackung, Sonstiges; die Stufe einer
Zusatzarbeit ist ihre Kategorie (Stammdaten), innerhalb einer Stufe bleibt die eingetragene Reihenfolge.
Zusatzarbeiten mit Zeit je Stück (s/Stück, z. B. Gravur extra) fließen in die Laserzeit und erscheinen nicht.

Die Unterzeilen sind nur Anzeige: die Zeile der Tabelle bleibt die Position (Auswahl, Bearbeiten, Löschen usw.
unverändert). Die Zeile wird um die Unterzeilen höher (spaltenbreite.AutoGroesse), die Zellen zeichnen sich oben
(UnterzeilenDelegat) und eine durchsichtige Fläche über der Tabelle zeichnet die Unterzeilen darunter (Unterzeilen).
"""
from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QWidget

from . import rechnen, zukauf
from .stammdaten import ZUSATZ_EINHEIT, zahl_als_text
from .stil import GELB_FLAECHE, GELB_TEXT, farbe

EINSTELLUNG = "ansicht_zusatz_unterzeilen"      # Häkchen (Vorgabe an, Freigabe 4b)
STUFEN = ("Programmieren", "Gewinde", "Nachbearbeitung", "Montage", "Oberfläche", "Prüfung", "Verpackung", "Sonstiges")
KATEGORIE_STUFE = {"Laser": "Nachbearbeitung", "Nachbearbeitung": "Nachbearbeitung", "Montage": "Montage",
                   "Oberfläche": "Oberfläche", "Prüfung": "Prüfung", "Verpackung": "Verpackung"}
TRENNER = "  ·  "
AUTO = "automatisch"       # zweiter Wert einer Unterzeile: automatische Zusatzarbeit (gelb), True = Warnung (rot)


def _eur(w, stellen=2):
    return f"{zahl_als_text(float(w or 0), stellen)} €"


def _menge(w):
    return zahl_als_text(round(float(w), 2)) if isinstance(w, (int, float)) else ""


def _zusatz_zeile(e, stueck):
    """Text einer Zusatzarbeit (Eintrag aus rechnen.kalkulation, zeilen[i]['zusatzarbeiten']) oder None (s/Stück)."""
    art = e.get("art")
    if art == "s/Stück":
        return None
    name = e["name"] + (f" {e['text']}" if e.get("text") else "")
    if e.get("auto"):          # Arbeitsgang-Regel mit Zuordnung automatisch (Plan Abrechnungsregeln)
        name += f" (automatisch, Regel {e.get('regel')})"
    elif e.get("regel"):
        name += f" (Preis: Regel {e['regel']})"
    teil = float(e.get("teil") or 0)
    if art == "€/Angebot":
        teile = [f"pauschal {_eur(e.get('pauschal'))}", f"umgelegt {_eur(teil)}/Teil"]
    elif art == "€/h":
        teile = [f"{_menge(e.get('menge'))} s/Teil", f"{_eur(e.get('preis'))}/h", f"{_eur(teil)}/Teil"]
    else:
        einheit = e.get("einheit") or ZUSATZ_EINHEIT.get(art, "")
        teile = [f"{_menge(e.get('menge'))} {einheit}".strip(), f"{_eur(e.get('preis'))}/{einheit}",
                 f"{_eur(teil)}/Teil"]
        if e.get("arbeit_s"):
            teile.insert(2, f"{zahl_als_text(round(float(e['arbeit_s'])))} s/Teil")
    if teil > float(e.get("betrag") or 0) + 0.005 and art != "€/Angebot":
        teile.append("inkl. Mindestbetrag")
    teile += [f"{_eur(teil * stueck)} Pos.", "Fremdleistung" if e.get("fremd") else "eigen"]
    return TRENNER.join([name] + [t for t in teile if t])


def schritte(p, z, katalog=()):
    """Unterzeilen einer Position: [(Text, Warnung)] in der Reihenfolge STUFEN. p = Position, z = ihre Zeile aus
    rechnen.kalkulation (None = nicht gerechnet: keine Unterzeilen), katalog = Stammdaten Zusatzarbeiten (Kategorie
    und Prüfung unbekannter Namen)."""
    if not z:
        return []
    kat = {x.get("name"): x.get("kategorie") for x in katalog or ()}
    stueck = float(z.get("stueck") or p.get("stueck") or 0)
    out = []           # (Stufe, Nr., Text, Warnung)

    def neu(stufe, text, warnung=False):
        out.append((STUFEN.index(stufe), len(out), text, warnung))

    prog, anteil = z.get("prog_min"), float(z.get("programmierung_anteil") or 0)
    if anteil or prog:
        zeit = f"{zahl_als_text(float(prog), 1)} min" + (" (von Hand)" if z.get("prog_hand") else "") \
            if isinstance(prog, (int, float)) else ""
        satz = f"{_eur(anteil * stueck * 60 / prog)}/h" if isinstance(prog, (int, float)) and prog > 0 else ""
        neu("Programmieren", TRENNER.join(t for t in ("Programmieren", zeit, satz, f"{_eur(anteil)}/Teil",
                                                       f"{_eur(anteil * stueck)} Pos.", "eigen") if t))
    if p.get("gewinde"):
        g = float(z.get("gewinde_teil") or 0)
        neu("Gewinde", TRENNER.join(("Gewinde", str(p["gewinde"]), f"{_eur(g)}/Teil", f"{_eur(g * stueck)} Pos.",
                                     "eigen")))
    for e in z.get("zusatzarbeiten") or ():
        text = _zusatz_zeile(e, stueck)
        if text:      # automatische gelb: sie stehen nicht in der Liste der Position
            neu(KATEGORIE_STUFE.get(kat.get(e["name"]), "Sonstiges"), text, AUTO if e.get("auto") else False)
    if katalog:
        unbekannt = rechnen.zusatz_unbekannt(p, katalog)
        if unbekannt:
            neu("Sonstiges", f"{unbekannt}{TRENNER}Zusatzarbeit unbekannt (Stammdaten prüfen)", True)
        ohne = rechnen.zusatz_ohne_zeit(p, katalog)
        if ohne:
            neu(KATEGORIE_STUFE.get(kat.get(ohne), "Sonstiges"), f"{ohne}{TRENNER}ohne Zeit je Teil", True)
    # Zukaufteile (Anbauteile) eines Rohrlaserteils; ein Zukaufteil oder eine Baugruppe ist selbst die Zeile
    if not z.get("zukaufteil") and not z.get("baugruppe"):
        for e, x in zip(zukauf.eintraege(p), z.get("zukauf_einzeln") or ()):
            st = e.get("stand") or {}
            einheit = zukauf.EINHEIT_KURZ.get(st.get("einheit"), st.get("einheit") or "")
            je_satz = e.get("je") == zukauf.JE_SATZ
            vk = float(x.get("vk") or 0)
            teile = [st.get("bezeichnung") or st.get("artikelnr") or "Zukaufteil",
                     f"{_menge(e.get('menge'))} {einheit}{'/Satz' if je_satz else '/Teil'}".strip(),
                     f"{_eur(vk / stueck)}/Teil" if stueck else "", f"{_eur(vk)} Pos.", "Zukauf"]
            if x.get("fehler"):
                teile.append(x["fehler"])
            neu("Montage", TRENNER.join(t for t in teile if t), bool(x.get("fehler")))
    return [(text, warnung) for _, _, text, warnung in sorted(out)]


# ------------------------------------------------------------------ Anzeige
class UnterzeilenMixin:
    """Vor einen QStyledItemDelegate gesetzt: die Zelle zeichnet und bearbeitet sich nur im oberen Teil der Zeile,
    darunter stehen die Unterzeilen (Unterzeilen in ansicht.unterzeilen)."""

    def _oben(self, option, index):
        u = getattr(self.parent(), "unterzeilen", None)
        h = u.hoehe(index.row()) if u is not None else 0
        if not h:
            return option
        o = QStyleOptionViewItem(option)
        o.rect = option.rect.adjusted(0, 0, 0, -min(h, max(option.rect.height() - 4, 0)))
        return o

    def paint(self, painter, option, index):
        super().paint(painter, self._oben(option, index), index)

    def updateEditorGeometry(self, editor, option, index):
        super().updateEditorGeometry(editor, self._oben(option, index), index)

    def editorEvent(self, ereignis, modell, option, index):
        return super().editorEvent(ereignis, modell, self._oben(option, index), index)


class UnterzeilenDelegat(UnterzeilenMixin, QStyledItemDelegate):
    pass


class _Flaeche(QWidget):
    """Durchsichtige Fläche über dem Tabelleninhalt, zeichnet die Unterzeilen."""

    def __init__(self, u):
        super().__init__(u.ansicht.viewport())
        self.u = u
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)

    def paintEvent(self, _):
        self.u.zeichnen(QPainter(self))


class Unterzeilen(QObject):
    """Unterzeilen einer QTableView. texte(r) -> [(Text, Warnung)] für Zeile r der Ansicht; spalte = Spalte, an der
    die Unterzeilen beginnen (Artikelnummer); doppelklick(r) für einen Doppelklick auf die Unterzeilen (None: wie
    ein Doppelklick auf die Zeile)."""

    def __init__(self, ansicht, texte, spalte, doppelklick=None, an=True):
        super().__init__(ansicht)
        self.ansicht, self.texte, self.spalte, self.doppelklick, self.an = ansicht, texte, spalte, doppelklick, an
        self.schrift = QFont(ansicht.font())
        self.schrift.setPointSizeF(max(ansicht.font().pointSizeF() * 0.92, 6))
        self.zeile_h = QFontMetrics(self.schrift).lineSpacing() + 4
        ansicht.unterzeilen = self
        self.flaeche = _Flaeche(self)
        self.flaeche.setGeometry(ansicht.viewport().rect())
        self.flaeche.show()
        ansicht.viewport().installEventFilter(self)
        for leiste in (ansicht.horizontalScrollBar(), ansicht.verticalScrollBar()):
            leiste.valueChanged.connect(self._lage)

    def anzahl(self, r):
        return len(self.texte(r)) if self.an else 0

    def hoehe(self, r):
        """Zusätzliche Höhe der Zeile r für ihre Unterzeilen [px]."""
        return self.anzahl(r) * self.zeile_h

    def setzen(self, an):
        """Häkchen an/aus: Zeilenhöhen neu, Fläche neu zeichnen."""
        self.an = bool(an)
        self.aktualisieren()

    def aktualisieren(self):
        a = self.ansicht
        if hasattr(a, "auto_groesse"):
            a.auto_groesse.spaeter()
        self.flaeche.update()

    def _lage(self, *_):
        # QAbstractScrollArea verschiebt beim Rollen die Kinder des Viewports mit: Fläche zurück auf den Viewport
        self.flaeche.setGeometry(self.ansicht.viewport().rect())
        self.flaeche.update()

    def _zeile_bei(self, y):
        """Zeile, in deren Unterzeilen der Punkt y (Viewport) liegt, sonst -1."""
        a = self.ansicht
        r = a.rowAt(y)
        if r < 0 or not self.an:
            return -1
        h = self.hoehe(r)
        unten = a.rowViewportPosition(r) + a.rowHeight(r)
        return r if h and unten - h <= y < unten else -1

    def eventFilter(self, obj, ereignis):
        t = ereignis.type()
        if t == QEvent.Resize:
            self._lage()
        elif t == QEvent.MouseButtonDblClick and self.doppelklick is not None:
            r = self._zeile_bei(ereignis.position().toPoint().y())
            if r >= 0:
                self.doppelklick(r)
                return True
        return False

    def zeichnen(self, p):
        if not self.an:
            p.end()
            return
        a = self.ansicht
        vp = a.viewport()
        pal = a.palette()
        grund = QColor(pal.color(QPalette.Base))
        akzent = pal.color(QPalette.Highlight)
        hinter = QColor(grund)
        hinter.setRed(int(grund.red() * 0.93 + akzent.red() * 0.07))
        hinter.setGreen(int(grund.green() * 0.93 + akzent.green() * 0.07))
        hinter.setBlue(int(grund.blue() * 0.93 + akzent.blue() * 0.07))
        text = QColor(pal.color(QPalette.Text))
        text.setAlpha(190)
        rot = QColor("#D0021B")             # fest: kräftiges Rot, auf hell und dunkel lesbar
        gelb, gelb_flaeche = farbe(GELB_TEXT), farbe(GELB_FLAECHE)
        linie = QColor(pal.color(QPalette.Mid))
        linie.setAlpha(90)
        p.setFont(self.schrift)
        fm = QFontMetrics(self.schrift)
        x0 = 0 if a.isColumnHidden(self.spalte) else max(a.columnViewportPosition(self.spalte), 0)
        breite = vp.width() - x0
        oben = max(a.rowAt(0), 0)
        unten = a.rowAt(vp.height() - 1)
        unten = a.model().rowCount() - 1 if unten < 0 else unten
        for r in range(oben, unten + 1):
            if a.isRowHidden(r):
                continue
            zeilen = self.texte(r)
            if not zeilen:
                continue
            y = a.rowViewportPosition(r) + a.rowHeight(r) - len(zeilen) * self.zeile_h
            p.fillRect(QRect(x0, y, breite, len(zeilen) * self.zeile_h - 1), hinter)
            p.setPen(linie)
            p.drawLine(x0, y, x0 + breite, y)
            for n, (t, warnung) in enumerate(zeilen):
                rect = QRect(x0 + 10, y + n * self.zeile_h, breite - 14, self.zeile_h)
                if warnung == AUTO:
                    p.fillRect(QRect(x0 + 4, y + n * self.zeile_h + 1, breite - 8, self.zeile_h - 2), gelb_flaeche)
                    p.setPen(gelb)
                else:
                    p.setPen(rot if warnung else text)
                p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText("↳  " + t, Qt.ElideRight, rect.width()))
        p.end()
