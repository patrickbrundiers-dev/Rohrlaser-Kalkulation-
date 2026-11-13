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


class Schritt(tuple):
    """Unterzeile (Text, Warnung) mit aktion = dict(art, name, ok) für ✓/✗ (Patrick 04.11.2026: „so für alle
    Zusatzarbeiten“, auch Gewinde und Bohrungen) bzw. None ohne Knöpfe. Vergleicht sich wie ein Tupel."""

    def __new__(cls, text, warnung=False, aktion=None, klappen=None):
        t = super().__new__(cls, (text, warnung))
        t.aktion = aktion
        t.klappen = klappen         # Summenzeile der Zukaufartikel: Klick klappt die Einzelzeilen auf bzw. zu
        return t


ZUKAUF_KLAPPEN_AB = 2       # ab so vielen Zukaufartikeln eine Summenzeile, Einzelzeilen eingeklappt (F6 a)


def schritte(p, z, katalog=(), offen=False):
    """Unterzeilen einer Position: [(Text, Warnung)] in der Reihenfolge STUFEN. p = Position, z = ihre Zeile aus
    rechnen.kalkulation (None = nicht gerechnet: keine Unterzeilen), katalog = Stammdaten Zusatzarbeiten (Kategorie
    und Prüfung unbekannter Namen). Ab ZUKAUF_KLAPPEN_AB Zukaufartikeln steht eine Summenzeile da; die Zeilen je
    Artikel nur mit offen=True (Klick auf die Summenzeile, Patrick 12.11.2026)."""
    if not z:
        return []
    from . import arbeitsgaenge
    kat = {x.get("name"): x.get("kategorie") for x in katalog or ()}
    stueck = float(z.get("stueck") or p.get("stueck") or 0)
    ok = set(arbeitsgaenge.geprueft(p))
    out = []           # (Stufe, Nr., Text, Warnung, Aktion)

    def neu(stufe, text, warnung=False, aktion=None, klappen=None):
        out.append((STUFEN.index(stufe), len(out), text, warnung, aktion, klappen))

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
                                     "eigen")), aktion=dict(art="gewinde", name="Gewinde", ok="Gewinde" in ok))
    for e in z.get("zusatzarbeiten") or ():
        text = _zusatz_zeile(e, stueck)
        if text:      # automatische gelb: sie stehen nicht in der Liste der Position
            neu(KATEGORIE_STUFE.get(kat.get(e["name"]), "Sonstiges"), text, AUTO if e.get("auto") else False,
                dict(art="auto" if e.get("auto") else "zusatz", name=e["name"], ok=e["name"] in ok))
    if katalog:
        unbekannt = rechnen.zusatz_unbekannt(p, katalog)
        if unbekannt:
            neu("Sonstiges", f"{unbekannt}{TRENNER}Zusatzarbeit unbekannt (Stammdaten prüfen)", True)
        ohne = rechnen.zusatz_ohne_zeit(p, katalog)
        if ohne:
            neu(KATEGORIE_STUFE.get(kat.get(ohne), "Sonstiges"), f"{ohne}{TRENNER}ohne Zeit je Teil", True)
    # Zukaufteile (Anbauteile) eines Rohrlaserteils; ein Zukaufteil oder eine Baugruppe ist selbst die Zeile
    if not z.get("zukaufteil") and not z.get("baugruppe"):
        paare = list(zip(zukauf.eintraege(p), z.get("zukauf_einzeln") or ()))
        if len(paare) >= ZUKAUF_KLAPPEN_AB:
            summe = sum(float(x.get("vk") or 0) for _, x in paare if not x.get("fehler"))
            fehlt = sum(1 for _, x in paare if x.get("fehler"))
            teile = [f"{'▾' if offen else '▸'} Zukaufartikel ({len(paare)})", f"Summe {_eur(summe / stueck)}/Teil"
                     if stueck else "", f"{_eur(summe)} Pos.", "Zukauf",
                     f"{fehlt} ohne EK" if fehlt else "", "" if offen else "Klick: aufklappen"]
            neu("Montage", TRENNER.join(t for t in teile if t), bool(fehlt), klappen=True)
            if not offen:
                paare = []
        for e, x in paare:
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
    # Programmieren allein (Standard je Position, steht in der Spalte Programmierzeit) ist keine eigene Zeile wert:
    # sonst hat jede Position eine Unterzeile und Sätze/Baugruppen gehen unter (Patrick 03.11.2026). Von Hand
    # geändert oder zusammen mit echten Arbeitsschritten bleibt sie.
    if len(out) == 1 and out[0][0] == STUFEN.index("Programmieren") and not z.get("prog_hand"):
        out = []
    return [Schritt(text, warnung, aktion, klappen) for _, _, text, warnung, aktion, klappen in
            sorted(out, key=lambda x: x[:2])]


def bohr_schritte(liste):
    """Offene Zeilen des Bohrbilds (Gewinde-Vorschläge, Senkungen, Flowdrill, Bohren aus STEP bzw. Zeichnung) als gelbe
    Unterzeilen mit ✓ (bestätigen) und ✗ (ablehnen); aktion name = Index der Zeile im Bohrbild."""
    from . import bohrbild
    out = []
    for i, z in enumerate(liste):
        if z.get("status", bohrbild.OFFEN) != bohrbild.OFFEN:
            continue
        aus = bohrbild.KURZ.get(bohrbild.ausfuehrung(z), z.get("art"))
        teile = [f"{aus} ?", f"{z.get('anzahl')}× " + (z.get("gewinde") or f"Ø{bohrbild.dez(z.get('d'))}")]
        if z.get("art") == "Senkung" and z.get("D"):
            teile[-1] += f"/{bohrbild.dez(z['D'])}"
        teile.append("aus STEP, noch nicht bestätigt")
        out.append(Schritt(TRENNER.join(teile), AUTO, dict(art="bohr", name=i, ok=False, gruppe=aus,
                                                            gewinde=z.get("gewinde"))))
    return out


# ------------------------------------------------------------------ Anzeige
class UnterzeilenMixin:
    """Vor einen QStyledItemDelegate gesetzt: die Zelle zeichnet und bearbeitet sich nur im oberen Teil der Zeile,
    darunter stehen die Unterzeilen (Unterzeilen in ansicht.unterzeilen)."""

    def _oben(self, option, index):
        u = getattr(self.parent(), "unterzeilen", None)
        h = u.hoehe(index.row()) if u is not None else 0
        k = u.kopf_hoehe(index.row()) if u is not None else 0
        if not h and not k:
            return option
        o = QStyleOptionViewItem(option)
        if u.kopf_zu(index.row()):          # zugeklappte Gruppe: die Zeile ist nur noch das Band
            o.rect = QRect(option.rect.left(), option.rect.bottom(), option.rect.width(), 0)
            return o
        k = min(k, max(option.rect.height() - 4, 0))
        o.rect = option.rect.adjusted(0, k, 0, -min(h, max(option.rect.height() - k - 4, 0)))
        return o

    def paint(self, painter, option, index):
        o = self._oben(option, index)
        if o.rect.height() > 0:
            super().paint(painter, o, index)

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

    KNOPF = 18          # ✓/✗ links in einer Unterzeile mit aktion (knopf_klick(r, aktion, ja))

    def __init__(self, ansicht, texte, spalte, doppelklick=None, an=True, kopf=None, kopf_klick=None,
                 knopf_klick=None, klapp_klick=None):
        super().__init__(ansicht)
        self.knopf_klick = knopf_klick
        self.klapp_klick = klapp_klick      # klapp_klick(r): Klick auf eine Summenzeile (Schritt.klappen)
        self.ansicht, self.texte, self.spalte, self.doppelklick, self.an = ansicht, texte, spalte, doppelklick, an
        self.schrift = QFont(ansicht.font())
        self.schrift.setPointSizeF(max(ansicht.font().pointSizeF() * 0.92, 6))
        self.zeile_h = QFontMetrics(self.schrift).lineSpacing() + 4
        # Kopfband über der ersten Zeile eines Satzes bzw. einer Schweißbaugruppe (Patrick 04.11.2026):
        # kopf(r) -> dict(titel, info, flaeche, text) oder None; kopf_klick(r, art, x) mit art "klick", "doppel",
        # "rechts" und x = Abstand vom linken Rand (▾/▸ bis 30 px)
        self.kopf, self.kopf_klick = kopf, kopf_klick
        self.kopf_schrift = QFont(ansicht.font())
        self.kopf_schrift.setBold(True)
        self.kopf_h = QFontMetrics(self.kopf_schrift).lineSpacing() + 10
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
        """Zusätzliche Höhe der Zeile r für ihre Unterzeilen [px] (zugeklappte Gruppe: keine)."""
        return 0 if self.kopf_zu(r) else self.anzahl(r) * self.zeile_h

    def kopf_zu(self, r):
        """Zeile r ist das Band einer zugeklappten Gruppe (Satz, Baugruppe, Einzelteile): nur das Band, keine Zelle
        darunter (Patrick 04.11.2026)."""
        if self.kopf is None:
            return False
        k = self.kopf(r)
        return bool(k and k.get("zu"))

    def kopf_hoehe(self, r):
        """Zusätzliche Höhe oben für das Kopfband eines Satzes bzw. einer Baugruppe [px]."""
        return self.kopf_h if self.kopf is not None and self.kopf(r) else 0

    def kopf_bei(self, y):
        """Zeile, in deren Kopfband der Punkt y (Viewport) liegt, sonst -1."""
        r = self.ansicht.rowAt(y)
        if r < 0:
            return -1
        oben = self.ansicht.rowViewportPosition(r)
        return r if oben <= y < oben + self.kopf_hoehe(r) else -1

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
        elif t in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick) and self.kopf_klick is not None:
            r = self.kopf_bei(ereignis.position().toPoint().y())
            if r >= 0:
                x = ereignis.position().toPoint().x()
                if t == QEvent.MouseButtonDblClick:
                    self.kopf_klick(r, "doppel", x)
                    return True
                self.kopf_klick(r, "rechts" if ereignis.button() == Qt.RightButton else "klick", x)
                return ereignis.button() != Qt.RightButton      # Rechtsklick: danach das Menü der Tabelle
        if t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease) and self.klapp_klick is not None \
                and ereignis.button() == Qt.LeftButton:
            treffer = self.text_bei(ereignis.position().toPoint())
            if treffer and getattr(treffer[1], "klappen", None):
                if t == QEvent.MouseButtonRelease:
                    self.klapp_klick(treffer[0])
                return True
        if t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick) and \
                self.knopf_klick is not None:
            treffer = self.knopf_bei(ereignis.position().toPoint())
            if treffer:
                if t == QEvent.MouseButtonRelease and ereignis.button() == Qt.LeftButton:
                    self.knopf_klick(*treffer)
                return True
        if t == QEvent.MouseButtonDblClick and self.doppelklick is not None:
            r = self._zeile_bei(ereignis.position().toPoint().y())
            if r >= 0:
                self.doppelklick(r)
                return True
        return False

    def text_bei(self, punkt):
        """(Zeile, Unterzeile) unter punkt (Viewport) oder None."""
        r = self._zeile_bei(punkt.y())
        if r < 0:
            return None
        zeilen = self.texte(r)
        a = self.ansicht
        y0 = a.rowViewportPosition(r) + a.rowHeight(r) - len(zeilen) * self.zeile_h
        n = (punkt.y() - y0) // self.zeile_h
        return (r, zeilen[n]) if 0 <= n < len(zeilen) else None

    def knoepfe(self, r):
        """[(Rechteck ✓, Rechteck ✗, aktion)] der Unterzeilen von Zeile r (Viewport), nur mit knopf_klick."""
        if self.knopf_klick is None or not self.an:
            return []
        a = self.ansicht
        zeilen = self.texte(r)
        if not zeilen:
            return []
        x0 = 0 if a.isColumnHidden(self.spalte) else max(a.columnViewportPosition(self.spalte), 0)
        y0 = a.rowViewportPosition(r) + a.rowHeight(r) - len(zeilen) * self.zeile_h
        out = []
        for n, z in enumerate(zeilen):
            aktion = getattr(z, "aktion", None)
            if not aktion:
                continue
            y = y0 + n * self.zeile_h + 1
            h = self.zeile_h - 2
            ja = QRect(x0 + 6, y, self.KNOPF, h)
            out.append((ja, QRect(ja.right() + 4, y, self.KNOPF, h), aktion))
        return out

    def knopf_bei(self, punkt):
        """(Zeile, aktion, ja) des ✓/✗ unter punkt (Viewport) oder None."""
        r = self._zeile_bei(punkt.y())
        if r < 0:
            return None
        for ja, nein, aktion in self.knoepfe(r):
            if ja.contains(punkt):
                return r, aktion, True
            if nein.contains(punkt):
                return r, aktion, False
        return None

    def zeichnen(self, p):
        self._koepfe_zeichnen(p)
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
        for r in self._sichtbare_zeilen():
            zeilen = self.texte(r)
            if not zeilen:
                continue
            y = a.rowViewportPosition(r) + a.rowHeight(r) - len(zeilen) * self.zeile_h
            p.fillRect(QRect(x0, y, breite, len(zeilen) * self.zeile_h - 1), hinter)
            p.setPen(linie)
            p.drawLine(x0, y, x0 + breite, y)
            knoepfe = {n: k for n, k in enumerate(self.knoepfe(r))} if self.knopf_klick is not None else {}
            mit = [n for n, z in enumerate(zeilen) if getattr(z, "aktion", None)] if knoepfe else []
            for n, (t, warnung) in enumerate(zeilen):
                einzug = 10 + (2 * self.KNOPF + 10 if mit else 0)
                rect = QRect(x0 + einzug, y + n * self.zeile_h, breite - einzug - 4, self.zeile_h)
                if warnung == AUTO:
                    p.fillRect(QRect(x0 + 4, y + n * self.zeile_h + 1, breite - 8, self.zeile_h - 2), gelb_flaeche)
                    p.setPen(gelb)
                else:
                    p.setPen(rot if warnung else text)
                p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText("↳  " + t, Qt.ElideRight, rect.width()))
                if n in mit:
                    self._knopf_zeichnen(p, *knoepfe[mit.index(n)])
        p.end()

    def _knopf_zeichnen(self, p, ja, nein, aktion):
        """✓ grün (bestätigt: gefüllt) und ✗ rot."""
        gruen, rot = farbe("#1E7B34"), farbe("#B42318")
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if aktion.get("ok"):
            p.setBrush(gruen)
            p.setPen(gruen)
            p.drawRoundedRect(ja.adjusted(0, 0, -1, -1), 3, 3)
            p.setPen(farbe("#FFFFFF"))
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(gruen)
            p.drawRoundedRect(ja.adjusted(0, 0, -1, -1), 3, 3)
        p.drawText(ja, Qt.AlignCenter, "✓")
        p.setBrush(Qt.NoBrush)
        p.setPen(rot)
        p.drawRoundedRect(nein.adjusted(0, 0, -1, -1), 3, 3)
        p.drawText(nein, Qt.AlignCenter, "✗")
        p.restore()

    def _sichtbare_zeilen(self):
        """Logische Zeilen im sichtbaren Bereich, in Anzeige-Reihenfolge (der Zeilenkopf ordnet Sätze und Baugruppen
        um: logische und angezeigte Reihenfolge unterscheiden sich)."""
        a = self.ansicht
        kopf = a.verticalHeader()
        h = a.viewport().height()
        oben = kopf.visualIndexAt(0)
        unten = kopf.visualIndexAt(h - 1)
        oben = 0 if oben < 0 else oben
        unten = kopf.count() - 1 if unten < 0 else unten
        return [r for r in (kopf.logicalIndex(v) for v in range(oben, unten + 1)) if r >= 0 and not a.isRowHidden(r)]

    def _koepfe_zeichnen(self, p):
        """Kopfbänder: über die ganze Breite die Farbe des Satzes, links ein kräftiger Balken, Titel fett, dahinter die
        Summen des Satzes (Anzahl, Teile, Fläche, Gewicht, Preis)."""
        if self.kopf is None:
            return
        a = self.ansicht
        vp = a.viewport()
        normal = QFont(a.font())
        for r in self._sichtbare_zeilen():
            k = self.kopf(r)
            if not k:
                continue
            y = a.rowViewportPosition(r)
            h = self.kopf_h
            breite = vp.width()
            flaeche, text = farbe(k["flaeche"]), farbe(k["text"])
            p.fillRect(QRect(0, y, breite, h), flaeche)
            p.fillRect(QRect(0, y, 5, h), text)
            p.setPen(text)
            p.drawLine(0, y, breite, y)
            p.setFont(self.kopf_schrift)
            fm = QFontMetrics(self.kopf_schrift)
            x = 12
            titel = k["titel"]
            p.drawText(QRect(x, y, breite - x, h), Qt.AlignVCenter | Qt.AlignLeft, titel)
            x += fm.horizontalAdvance(titel) + 16
            if k.get("info"):
                p.setFont(normal)
                p.setPen(QColor(a.palette().color(QPalette.Text)))
                rect = QRect(x, y, max(breite - x - 8, 0), h)
                p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft,
                           QFontMetrics(normal).elidedText(k["info"], Qt.ElideRight, rect.width()))
