"""Fenster „Varianten vergleichen“ (varianten.py): Lieferlängen und Material aus dem Lager je Stangengruppe mit
Zielgröße, Punkten, Empfehlung und Status der Optimierung; Reiter „Schachtelvergleich“ (schachtelvergleich.py, Plan
X3): einfache Einteilung, optimiert, ohne gemeinsamen Schnitt, Lieferlängen und Lager in einer Tabelle."""
from PySide6.QtGui import QBrush, QFont
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import schachtelvergleich as sv, stil, varianten as va
from .rechnen import zahl

SPALTEN = ("Gruppe / Variante", "Kosten [€]", "Verschnitt [%]", "Lieferstangen (Neukauf)", "Beladungen",
           "Wechselzeit [min]", "Punkte", "Status der Optimierung", "Hinweis")
EMPFOHLEN, GEPLANT, GRUPPE = "#E3F4E8", "#EEF4FB", "#F2F2F2"


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
        self.reiter = QTabWidget()
        seite1 = QWidget()
        lay1 = QVBoxLayout(seite1)
        lay1.addLayout(oben)
        lay1.addWidget(self.info)
        lay1.addWidget(self.tabelle, 1)
        self.reiter.addTab(seite1, "Varianten")
        # Plan X3: Schachtelvergleich in einer Tabelle
        seite2 = QWidget()
        lay2 = QVBoxLayout(seite2)
        self.sv_info = QLabel(
            "Je Stangengruppe: 1 einfache Einteilung (Eingabereihenfolge, Stange voll, dann die nächste), 2 der "
            "Schnittplan, 3 dieselbe Optimierung ohne gemeinsamen Schnitt (nur zum Ausweisen seines Nutzens, wird nie "
            "geplant), 4 andere Lieferlängen, 5 Material aus dem Lager (nur mit eingeschaltetem Lager). Übernehmen "
            "einer Lieferlänge im Reiter Varianten. Einsparung gegenüber der einfachen Einteilung.")
        self.sv_info.setWordWrap(True)
        self.sv_tabelle = QTableWidget(0, len(sv.SPALTEN) + 1)
        self.sv_tabelle.setHorizontalHeaderLabels([t for _, t in sv.SPALTEN] + ["Hinweis"])
        self.sv_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.sv_tabelle.verticalHeader().setVisible(False)
        self.sv_tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.sv_tabelle.horizontalHeader().setStretchLastSection(True)
        lay2.addWidget(self.sv_info)
        lay2.addWidget(self.sv_tabelle, 1)
        self.reiter.addTab(seite2, "Schachtelvergleich")
        lay = QVBoxLayout(self)
        lay.addWidget(self.reiter, 1)
        lay.addLayout(kn)
        self.gruppen = self.seite.varianten_gruppen()
        self.laden()
        self.schachtel = self.seite.schachtel_vergleich() if hasattr(self.seite, "schachtel_vergleich") else []
        self.schachtel_laden()

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
                (t.item(r, c) or self._setzen(r, c, "")).setBackground(QBrush(stil.farbe(GRUPPE)))
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
                        it.setBackground(QBrush(stil.farbe(EMPFOHLEN)))
                    elif v["geplant"]:
                        it.setBackground(QBrush(stil.farbe(GEPLANT)))
                self.zeilen.append((g, v))
        self.info.setText(
            ("Noch nicht optimiert." if not self.gruppen else
             "Alle Varianten stammen aus derselben Optimierung mit denselben Fertigungsregeln; nicht ausführbare "
             "Varianten und fehlende Preise werden nie empfohlen. Die Laserzeit ist in allen Varianten gleich. "
             "Punkte: je Kriterium Wert ÷ bester Wert, gewichtet nach der Zielgröße (1,000 = überall die beste). ")
            + (f"{offen} Gruppe(n) ohne bewiesenes Optimum (Suche begrenzt): Stangenzahl kann noch kleiner gehen."
               if offen else ""))
        self._knoepfe()

    def schachtel_laden(self):
        t = self.sv_tabelle
        t.setRowCount(0)
        fett = QFont()
        fett.setBold(True)
        for g in self.schachtel:
            r = t.rowCount()
            t.insertRow(r)
            kopf = QTableWidgetItem(f"{g['profil']} · {g['werkstoff']}" + (f" {g['oberflaeche']}" if g["oberflaeche"]
                                                                          else "")
                                    + f" ({g['teile']} Teile, {zahl(g['stange'] / 1000, 2)} m)")
            kopf.setFont(fett)
            t.setItem(r, 0, kopf)
            for c in range(t.columnCount()):
                (t.item(r, c) or self._setzen_in(t, r, c, "")).setBackground(QBrush(stil.farbe(GRUPPE)))
            for w in g["zeilen"]:
                r = t.rowCount()
                t.insertRow(r)
                for c, (schl, _) in enumerate(sv.SPALTEN):
                    it = self._setzen_in(t, r, c, ("   " if c == 0 else "") + sv.text(w, schl))
                    if w["art"] == sv.OPTIMIERT:
                        it.setBackground(QBrush(stil.farbe(GEPLANT)))
                self._setzen_in(t, r, len(sv.SPALTEN), w.get("hinweis") or "")
        if not self.schachtel:
            t.insertRow(0)
            self._setzen_in(t, 0, 0, "Noch nicht optimiert.")

    @staticmethod
    def _setzen_in(t, r, c, w):
        it = QTableWidgetItem("" if w is None else str(w))
        t.setItem(r, c, it)
        return it

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
