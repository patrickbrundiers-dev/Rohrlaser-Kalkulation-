"""Feld „Kalkulation: Kosten je Baugruppe“ im Fenster Schweißbaugruppe (Konzept 12.11.2026, Paket 2): aufklappbare
Kostenposten (bg_kosten.uebersicht), darunter Zuschläge, Selbstkosten, Gewinn, Verkaufspreis, Deckungsbeitrag und
Marge. Ein Klick auf einen Posten klappt ihn auf und zeigt, woraus er besteht (bei Schweißen: Nahtgruppen mit
Rechenweg)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from . import bg_vorgabe, stil
from .stammdaten import zahl_als_text


def euro(w):
    return zahl_als_text(round(w or 0.0, 2), 2) + " €" if isinstance(w, (int, float)) else ""


class KostenFeld(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kosten_feld")
        self.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(3)
        self.titel = QLabel("<b>Kalkulation: Kosten je Baugruppe</b>")
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
        self.u = None
        self._offen = set()

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
        t += fett("= Verkaufspreis je BG", euro(u["verkauf"]))
        n_txt = f"{u['n']:g}".replace(".", ",")
        t += zeile(f"Verkaufspreis Auftrag ({n_txt} Stk.)", euro(u["verkauf_auftrag"]))
        t += zeile("Deckungsbeitrag je BG", euro(u["db"]))
        t += zeile("Gewinnmarge", (zahl_als_text(round(u["marge"], 1), 1) + " %") if u["marge"] is not None else "")
        t += zeile("Arbeitszeit Baugruppe je BG", bg_vorgabe.zeit_text(u["arbeit_min"]))
        if u["maschine_min"]:
            t += zeile("Laserzeit Einzelteile je BG", bg_vorgabe.zeit_text(u["maschine_min"]))
        t += "</table>"
        t += (f"<span style='color:{grau}'>Deckungsbeitrag = Verkaufspreis − Material − Zukauf − Fremdleistungen − "
              "Schweißzusatz/Gas. Marge = Gewinn ÷ Verkaufspreis.</span>")
        self.preis.setText(t)
