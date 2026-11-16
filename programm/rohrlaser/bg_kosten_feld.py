"""Feld „Kalkulation: Kosten je Baugruppe“ im Fenster Schweißbaugruppe (Konzept 12.11.2026, Paket 2): aufklappbare
Kostenposten (bg_kosten.uebersicht), darunter Zuschläge, Selbstkosten, Gewinn, Verkaufspreis, Deckungsbeitrag und
Marge. Ein Klick auf einen Posten klappt ihn auf und zeigt, woraus er besteht (bei Schweißen: Nahtgruppen mit
Rechenweg)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout, QHeaderView, QLabel, QLineEdit, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from . import bg_vorgabe, stil
from .stammdaten import zahl_als_text, zahl_aus_text


def euro(w):
    return zahl_als_text(round(w or 0.0, 2), 2) + " €" if isinstance(w, (int, float)) else ""


def zahl_lesen(text):
    """Zahl aus einer Eingabe (Komma, € und % erlaubt) oder None (leer); ValueError bei Unsinn oder negativ."""
    t = str(text or "").replace("€", "").replace("%", "").strip()
    if not t:
        return None
    w = zahl_aus_text(t)
    if w < 0:
        raise ValueError("negativ")
    return w


class KostenFeld(QFrame):
    """Signale: preis_geaendert(object) = Verkaufspreis je BG von Hand (None = berechnet); kopf_geaendert(dict) =
    Gewinn bzw. Zuschlag Fremdleistung des Angebots in % (None = aus den Einstellungen)."""
    preis_geaendert = Signal(object)
    kopf_geaendert = Signal(dict)

    def __init__(self, parent=None, nur_lesen=False, mit_angebot=False, mit_preis=True, einheit="Baugruppe"):
        super().__init__(parent)
        self.nur_lesen = nur_lesen
        self.setObjectName("kosten_feld")
        self.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(3)
        self.titel = QLabel(f"<b>Kalkulation: Kosten je {einheit}</b>")
        lay.addWidget(self.titel)
        self.baum = QTreeWidget()
        self.baum.setObjectName("kosten_baum")
        self.baum.setColumnCount(2)
        self.baum.setHeaderHidden(True)
        self.baum.setRootIsDecorated(True)
        self.baum.setUniformRowHeights(True)
        self.baum.setSelectionMode(QAbstractItemView.NoSelection)
        self.baum.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.baum.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.baum.header().setStretchLastSection(False)
        self.baum.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.baum.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.baum.itemClicked.connect(lambda it, _c: it.setExpanded(not it.isExpanded()) if it.childCount() else None)
        self.baum.itemExpanded.connect(lambda _it: self._hoehe())
        self.baum.itemCollapsed.connect(lambda _it: self._hoehe())
        lay.addWidget(self.baum)
        self.preis = QLabel()
        self.preis.setObjectName("kosten_preis")
        self.preis.setTextFormat(Qt.RichText)
        self.preis.setWordWrap(True)
        lay.addWidget(self.preis)
        # Schnell ändern: Verkaufspreis von Hand je Baugruppe, Gewinn und Zuschlag Fremdleistung des Angebots
        g = QGridLayout()
        g.setContentsMargins(0, 2, 0, 0)
        g.setHorizontalSpacing(6)
        g.setColumnStretch(1, 1)
        self.felder = {}
        for r, (n, t, tipp) in enumerate((
                ("preis", "Preis je BG von Hand [€]", "Verkaufspreis je Baugruppe inkl. Einzelteile, gilt für diese "
                 "Anzahl Baugruppen (Staffelstufen rechnen normal). Der Unterschied zum berechneten Preis zählt wie "
                 "Gewinn. Leer = berechnet."),
                ("gewinn", "Gewinn Angebot [%]", "Gewinn des ganzen Angebots (Kalkulationswerte); leer = Einstellungen"),
                ("zuschlag_fremdleistung", "Zuschlag Fremd Angebot [%]",
                 "Zuschlag Fremdleistung des ganzen Angebots; leer = Einstellungen"))):
            k = QLabel(t)
            k.setToolTip(tipp)
            g.addWidget(k, r, 0)
            f = QLineEdit()
            f.setObjectName(f"kosten_{n}")
            f.setPlaceholderText("berechnet" if n == "preis" else "Einstellungen")
            f.setToolTip(tipp)
            f.setReadOnly(nur_lesen)
            f.editingFinished.connect(lambda n=n: self._melden(n))
            g.addWidget(f, r, 1)
            b = QToolButton()
            b.setText("↺")
            b.setToolTip("Zurück auf den berechneten Wert bzw. die Einstellungen")
            b.setEnabled(not nur_lesen)
            b.clicked.connect(lambda _=False, n=n: self._zurueck(n))
            g.addWidget(b, r, 2)
            self.felder[n] = (k, f, b)
            for w in (k, f, b):
                w.setVisible(mit_angebot if n != "preis" else mit_preis)
        lay.addLayout(g)
        self._gitter = g
        self.hand_info = QLabel()
        self.hand_info.setWordWrap(True)
        self.hand_info.setTextFormat(Qt.RichText)
        lay.addWidget(self.hand_info)
        self.u = None
        self._offen = set()

    def preis_zeile(self):
        """Zeile „Preis je BG von Hand“ als eigenes Widget (Plan Schweißbaugruppe Teil 2, L7): das Fenster setzt
        sie fest unter den Preis, damit sie auch bei zugeklappter Kostenübersicht sichtbar ist."""
        from PySide6.QtWidgets import QHBoxLayout, QWidget
        w = QWidget()
        w.setObjectName("kosten_preis_zeile")
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        k, f, b = self.felder["preis"]
        for x in (k, f, b):
            self._gitter.removeWidget(x)
        h.addWidget(k)
        h.addWidget(f, 1)
        h.addWidget(b)
        self._preis_aussen = True
        return w

    def werte_setzen(self, preis=None, kopf=None):
        """Eingabefelder füllen (ohne Signal): preis = von Hand je BG oder None, kopf = {gewinn, zuschlag_fremdleistung}."""
        for n, w in (("preis", preis), *((kopf or {}).items())):
            if n not in self.felder:
                continue
            f = self.felder[n][1]
            if f.hasFocus() and f.isModified():
                continue
            f.blockSignals(True)
            f.setText(zahl_als_text(w, 2) if isinstance(w, (int, float)) else "")
            f.setModified(False)
            f.blockSignals(False)
            f.setStyleSheet(f"background: {stil.umsetzen(stil.GELB_FLAECHE)}; font-weight: bold;"
                            if isinstance(w, (int, float)) else "")
            self.felder[n][2].setVisible(isinstance(w, (int, float)) and (
                self.felder[n][0].isVisibleTo(self) or (n == "preis" and getattr(self, "_preis_aussen", False))))

    def _melden(self, n):
        f = self.felder[n][1]
        try:
            w = zahl_lesen(f.text())
        except ValueError:
            self.hand_info.setText(f"<span style='color:{stil.umsetzen(stil.ROT)}'>„{f.text()}“ ist keine gültige "
                                   "Zahl.</span>")
            return
        f.setModified(False)
        if n == "preis":
            self.preis_geaendert.emit(w)
        else:
            self.kopf_geaendert.emit({n: w})

    def _zurueck(self, n):
        self.felder[n][1].setText("")
        self._melden(n)

    def showEvent(self, e):         # Zeilenhöhe steht erst nach dem Anzeigen fest (Satz in 3D: vorher gefüllt)
        super().showEvent(e)
        self._hoehe()

    def _hoehe(self):
        n = 0
        it = self.baum.invisibleRootItem()
        stapel = [it.child(i) for i in range(it.childCount())]
        while stapel:
            x = stapel.pop()
            n += 1
            if x.isExpanded():
                stapel += [x.child(i) for i in range(x.childCount())]
        h = self.baum.sizeHintForRow(0) if self.baum.topLevelItemCount() else 18
        self.baum.setFixedHeight(max(1, n) * max(h, 16) + 6)

    def setzen(self, u):
        """Anzeige aus bg_kosten.uebersicht (u = None: leer)."""
        self.u = u
        self._offen = {self.baum.topLevelItem(i).text(0) for i in range(self.baum.topLevelItemCount())
                       if self.baum.topLevelItem(i).isExpanded()}
        self.baum.clear()
        if not u:
            self.preis.setText("")
            self._hoehe()
            return
        grau = stil.umsetzen(stil.TEXT_GRAU)
        for x in u["posten"]:
            it = QTreeWidgetItem([x["titel"], euro(x["eur"])])
            it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            for name, eur, text in x["kinder"]:
                k = QTreeWidgetItem([name, euro(eur)])
                k.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                k.setForeground(0, stil.farbe(stil.TEXT_GRAU))
                k.setForeground(1, stil.farbe(stil.TEXT_GRAU))
                if text:
                    k.setToolTip(0, text)
                    k.setToolTip(1, text)
                    k.addChild(QTreeWidgetItem([text, ""]))
                    k.child(0).setForeground(0, stil.farbe(stil.TEXT_GRAU))
                it.addChild(k)
            self.baum.addTopLevelItem(it)
            if x["titel"] in self._offen:
                it.setExpanded(True)
        summe = QTreeWidgetItem(["Kosten vor Zuschlägen", euro(u["kosten"])])
        summe.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        f = summe.font(0)
        f.setBold(True)
        summe.setFont(0, f)
        summe.setFont(1, f)
        self.baum.addTopLevelItem(summe)
        self._hoehe()
        zeile = "<tr><td>{}</td><td align=right>&nbsp;{}</td></tr>".format
        fett = "<tr><td><b>{}</b></td><td align=right>&nbsp;<b>{}</b></td></tr>".format
        t = "<table cellspacing=0 cellpadding=1 width='100%'>"
        if u["verkauf"] is None:
            t += ("</table><span style='color:%s'>Preis, Zuschläge und Gewinn stehen nach dem Speichern im Angebot "
                  "(ohne Angebot nur die eigenen Leistungen der Baugruppe).</span>" % grau)
            self.preis.setText(t)
            return
        t += zeile("+ Zuschläge (Material, Fertigung, Fremd)", euro(u["zuschlaege"]))
        t += fett("= Selbstkosten", euro(u["selbst"]))
        t += zeile("+ Gewinn", euro(u["gewinn"]))
        if u["fracht"]:
            t += zeile("+ Fracht", euro(u["fracht"]))
        if u["skonto"]:
            t += zeile("+ Skonto", euro(u["skonto"]))
        if abs(u["rest"]) > 0.005:
            t += zeile("+ Mindestpreis, Muster u. a.", euro(u["rest"]))
        e = u.get("einheit") or "BG"
        t += fett(f"= Verkaufspreis je {e}", euro(u["verkauf"]))
        n_txt = f"{u['n']:g}".replace(".", ",")
        t += zeile(f"Verkaufspreis Auftrag ({n_txt} Stk.)", euro(u["verkauf_auftrag"]))
        t += zeile(f"Deckungsbeitrag je {e}", euro(u["db"]))
        t += zeile("Gewinnmarge", (zahl_als_text(round(u["marge"], 1), 1) + " %") if u["marge"] is not None else "")
        if e == "BG":
            t += zeile("Arbeitszeit Baugruppe je BG", bg_vorgabe.zeit_text(u["arbeit_min"]))
        if u["maschine_min"]:
            t += zeile(f"Laserzeit Einzelteile je {e}", bg_vorgabe.zeit_text(u["maschine_min"]))
        t += "</table>"
        t += (f"<span style='color:{grau}'>Deckungsbeitrag = Verkaufspreis − Material − Zukauf"
              + (" − Fremdleistungen − Schweißzusatz/Gas" if e == "BG" else "") + ". Marge = Gewinn ÷ Verkaufspreis."
              "</span>")
        self.preis.setText(t)
        ph = u.get("preis_hand")
        if ph:
            farbe = stil.ROT if ph["ziel"] < ph["selbst"] - 1e-6 else stil.ORANGE
            self.hand_info.setText(
                f"<span style='color:{stil.umsetzen(farbe)}'>● Preis von Hand {euro(ph['ziel'])} je BG "
                f"(berechnet {euro(ph['berechnet'])}, {'+' if ph['diff'] >= 0 else '−'}{euro(abs(ph['diff']))})"
                + (" – unter den Selbstkosten!" if farbe == stil.ROT else "") + "</span>")
        else:
            self.hand_info.setText("")
