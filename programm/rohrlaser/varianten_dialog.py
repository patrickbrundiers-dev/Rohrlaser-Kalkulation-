"""Fenster „Varianten vergleichen“ (varianten.py): Lieferlängen und Material aus dem Lager je Stangengruppe mit
Zielgröße, Punkten, Empfehlung und Status der Optimierung."""
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import varianten as va
from .rechnen import zahl

SPALTEN = ("Gruppe / Variante", "Kosten [€]", "Verschnitt [%]", "Lieferstangen (Neukauf)", "Beladungen",
           "Wechselzeit [min]", "Punkte", "Status der Optimierung", "Hinweis")
EMPFOHLEN, GEPLANT, GRUPPE = "#E3F4E8", "#EAF1FB", "#F2F2F2"


class VariantenDialog(QDialog):
    """seite: Angebotsseite mit varianten_gruppen() und laenge_waehlen(link)."""

    def __init__(self, parent, seite):
        super().__init__(parent)
        self.seite = seite
        self.setWindowTitle("Varianten vergleichen")
        self.resize(1150, 520)
        self.ziel = QComboBox()
        self.ziel.addItems(va.ZIELE)
        self.ziel.currentIndexChanged.connect(self.laden)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.itemSelectionChanged.connect(self._knoepfe)
        self.uebernehmen_knopf = QPushButton("Lieferlänge übernehmen und neu optimieren")
        self.uebernehmen_knopf.clicked.connect(self.uebernehmen)
        self.lager_knopf = QPushButton("Material aus Lager …")
        self.lager_knopf.clicked.connect(lambda: self.seite.material_aus_lager())
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Zielgröße:"))
        oben.addWidget(self.ziel)
        oben.addStretch(1)
        kn = QHBoxLayout()
        kn.addWidget(self.uebernehmen_knopf)
        kn.addWidget(self.lager_knopf)
        kn.addStretch(1)
        kn.addWidget(zu)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.info)
        lay.addWidget(self.tabelle, 1)
        lay.addLayout(kn)
        self.gruppen = self.seite.varianten_gruppen()
        self.laden()

    def laden(self):
        ziel = self.ziel.currentText()
        self.zeilen = []           # je Tabellenzeile (Gruppe, Variante oder None)
        self.bewertung = []
        t = self.tabelle
        t.setRowCount(0)
        fett = QFont()
        fett.setBold(True)
        offen = 0
        for g in self.gruppen:
            b = va.bewerten(g["varianten"], ziel)
            self.bewertung.append(b)
            offen += "nicht bewiesen" in (g["status"] or "")
            r = t.rowCount()
            t.insertRow(r)
            kopf = QTableWidgetItem(f"{g['profil']} · {g['werkstoff']}" + (f" {g['oberflaeche']}" if g['oberflaeche']
                                                                          else "") + f" ({g['teile'] or 0} Teile)")
            kopf.setFont(fett)
            t.setItem(r, 0, kopf)
            t.setItem(r, 8, QTableWidgetItem(b["grund"]))
            for c in range(len(SPALTEN)):
                (t.item(r, c) or self._setzen(r, c, "")).setBackground(QBrush(QColor(GRUPPE)))
            self.zeilen.append((g, None))
            for i, v in enumerate(g["varianten"]):
                r = t.rowCount()
                t.insertRow(r)
                hinweis = ("nicht ausführbar: " + v["fehler"]) if v["fehler"] else "; ".join(v["fehlt"])
                if i == b["beste"]:
                    hinweis = "empfohlen" + (f"; {hinweis}" if hinweis else "")
                werte = ("   " + v["name"] + (" (geplant)" if v["geplant"] else ""),
                         zahl(v["kosten"]) if v["kosten"] is not None else "fehlt",
                         zahl(v["verschnitt"], 1) if v["verschnitt"] is not None else "",
                         str(v["stangen"]) + (f" (+{v['aus_lager']} Lager)" if v["aus_lager"] else ""),
                         str(v["beladungen"]), zahl(v["zeit"], 1) if v["zeit"] is not None else "",
                         zahl(b["punkte"][i], 3) if b["punkte"][i] is not None else "–", v["status"], hinweis)
                for c, w in enumerate(werte):
                    it = self._setzen(r, c, w)
                    if i == b["beste"]:
                        it.setBackground(QBrush(QColor(EMPFOHLEN)))
                    elif v["geplant"]:
                        it.setBackground(QBrush(QColor(GEPLANT)))
                self.zeilen.append((g, v))
        self.info.setText(
            ("Noch nicht optimiert." if not self.gruppen else
             "Alle Varianten stammen aus derselben Optimierung mit denselben Fertigungsregeln; nicht ausführbare "
             "Varianten und fehlende Preise werden nie empfohlen. Die Laserzeit ist in allen Varianten gleich. "
             "Punkte: je Kriterium Wert ÷ bester Wert, gewichtet nach der Zielgröße (1,000 = überall die beste). ")
            + (f"{offen} Gruppe(n) ohne bewiesenes Optimum (Suche begrenzt): Stangenzahl kann noch kleiner gehen."
               if offen else ""))
        self._knoepfe()

    def _setzen(self, r, c, w):
        it = QTableWidgetItem("" if w is None else str(w))
        self.tabelle.setItem(r, c, it)
        return it

    def empfohlen(self, n):
        """Empfohlene Variante der n-ten Gruppe (Tests)."""
        b = self.bewertung[n]
        return None if b["beste"] is None else self.gruppen[n]["varianten"][b["beste"]]

    def markiert(self):
        r = self.tabelle.currentRow()
        return self.zeilen[r] if 0 <= r < len(self.zeilen) and self.tabelle.selectedItems() else (None, None)

    def _knoepfe(self):
        g, v = self.markiert()
        lesen = self.seite.db.nur_lesen
        self.uebernehmen_knopf.setEnabled(bool(
            not lesen and v and not v["fehler"] and not v.get("lager") and not v["geplant"]
            and g["laengen_index"] is not None and v["laenge"]))
        self.lager_knopf.setVisible(any(v.get("lager") for g in self.gruppen for v in g["varianten"]))

    def uebernehmen(self):
        g, v = self.markiert()
        if not v or g["laengen_index"] is None:
            return False
        laenge = 0 if v["laenge"] == g["grundlaenge"] else v["laenge"]
        ok = self.seite.laenge_waehlen(f"laenge:{g['laengen_index']}:{int(laenge)}")
        self.gruppen = self.seite.varianten_gruppen()
        self.laden()
        return ok
