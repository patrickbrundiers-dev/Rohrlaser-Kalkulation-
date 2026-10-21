"""Dialog 'Schneidweg berechnen …' einer Position ohne STEP-Datei: Enden (gerade oder Gehrung), Innenkonturen
(Bohrung, Langloch, Rechteck, Schlitz, sonstige Kontur) und Gravur eingeben; Schnittlängen, Einstiche,
Konturklassen und die Schneidzeit mit den Schneiddaten der Maschine stehen sofort darunter. Die Formeln stehen in
schneidweg.py; OK schreibt die Werte in die Position (Angebotsseite.schneidweg_berechnen)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from . import rechnen, schneidweg as sw
from .stammdaten import zahl_aus_text

KONTUR_SPALTEN = ("Art", "Anzahl", "Maß 1 [mm]", "Maß 2 [mm]", "Maß 3 [mm]", "Text")
ERGEBNIS_SPALTEN = ("Schnitt", "Anzahl", "je Stück [mm]", "gesamt [mm]", "Einstiche", "Hüllmaß [mm]", "Klasse")
MASS_HILFE = ("Maße: Bohrung Ø · Langloch Länge, Breite · Rechteck Breite, Höhe, Eckradius · Schlitz (offen, vom "
              "Rand) Tiefe, Breite · sonstige Kontur Schnittlänge, Hüllmaß (leer = groß)")


def _zahl(text):
    t = (text or "").strip()
    if not t:
        return None
    try:
        return zahl_aus_text(t)
    except ValueError:
        return None


class SchneidwegDialog(QDialog):
    """p: Position, profil: Stammdaten-Zeile des Profils, kopf/k/tabellen: Angebot und Stammdaten (Maschine,
    Konturgrenzen, Schneiddaten). Nach OK: self.eingaben (dict) und self.ergebnis (schneidweg.rechnen)."""

    def __init__(self, parent, p, profil, kopf, k, tabellen):
        super().__init__(parent)
        self.p, self.profil, self.kopf, self.k, self.tabellen = p, profil, kopf, k, tabellen
        self.grenzen, vorgabe = rechnen.kontur_grenzen(rechnen.maschine(kopf, k))
        self.ergebnis = None
        e = sw.lesen(p.get("technik"))
        self.setWindowTitle(f"Schneidweg berechnen – Pos. {p.get('pos') or ''} {p.get('artikel') or ''}".strip())
        self.resize(900, 640)
        lay = QVBoxLayout(self)
        form = profil.get("form")
        info = QLabel(f"Profil {p.get('profil_id')} ({form}), Werkstoff {p.get('werkstoff_id') or '–'}, Maschine "
                      f"{kopf.get('maschine') or '–'}, Konturgrenzen klein bis {rechnen.zahl(self.grenzen[0])} mm, "
                      f"mittel bis {rechnen.zahl(self.grenzen[1])} mm" + (" (Vorgabe)" if vorgabe else ""))
        info.setWordWrap(True)
        lay.addWidget(info)

        enden = QGridLayout()
        self.winkel, self.achse = {}, {}
        for r, (seite, titel) in enumerate((("a", "Anfangsschnitt"), ("b", "Endschnitt"))):
            w = QDoubleSpinBox()
            w.setRange(0, 79.9)
            w.setDecimals(1)
            w.setSuffix(" °")
            w.setValue(sw._z(e[seite].get("winkel")))
            w.setToolTip("Gehrung: Abweichung vom rechtwinkligen Schnitt (0° = gerader Schnitt)")
            w.valueChanged.connect(self.rechnen)
            a = QComboBox()
            a.addItems(sw.ACHSEN)
            a.setCurrentText(e[seite].get("achse") or sw.ACHSEN[0])
            a.setEnabled(form in sw.ROHRE_ECKIG)
            a.setToolTip("Quadrat-/Rechteckrohr: Seite, über die die Gehrung läuft (Höhe = Maß a, Breite = Maß b)")
            a.currentTextChanged.connect(self.rechnen)
            self.winkel[seite], self.achse[seite] = w, a
            enden.addWidget(QLabel(titel + ": Gehrung"), r, 0)
            enden.addWidget(w, r, 1)
            enden.addWidget(a, r, 2)
        self.gravur = QDoubleSpinBox()
        self.gravur.setRange(0, 100000)
        self.gravur.setDecimals(1)
        self.gravur.setSuffix(" mm")
        self.gravur.setValue(sw._z(e.get("gravur")))
        self.gravur.valueChanged.connect(self.rechnen)
        enden.addWidget(QLabel("Gravur (Länge)"), 2, 0)
        enden.addWidget(self.gravur, 2, 1)
        enden.setColumnStretch(3, 1)
        lay.addLayout(enden)

        lay.addWidget(QLabel("<b>Innenkonturen</b>"))
        self.tabelle = QTableWidget(0, len(KONTUR_SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(KONTUR_SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        for i, b in enumerate((140, 70, 95, 95, 95)):
            self.tabelle.setColumnWidth(i, b)
        self.tabelle.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.tabelle.itemChanged.connect(self.rechnen)
        lay.addWidget(self.tabelle, 1)
        hilfe = QLabel(MASS_HILFE)
        hilfe.setWordWrap(True)
        hilfe.setStyleSheet("color: #595959;")
        lay.addWidget(hilfe)
        leiste = QHBoxLayout()
        for art in sw.ARTEN:
            b = QPushButton(f"+ {art}")
            b.clicked.connect(lambda _=False, art=art: self.zeile_neu(dict(art=art, anzahl=1)))
            leiste.addWidget(b)
        weg = QPushButton("Markierte entfernen")
        weg.clicked.connect(self._entfernen)
        leiste.addStretch(1)
        leiste.addWidget(weg)
        lay.addLayout(leiste)

        lay.addWidget(QLabel("<b>Ergebnis je Teil</b>"))
        self.ergebnis_tabelle = QTableWidget(0, len(ERGEBNIS_SPALTEN))
        self.ergebnis_tabelle.setHorizontalHeaderLabels(ERGEBNIS_SPALTEN)
        self.ergebnis_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ergebnis_tabelle.verticalHeader().setVisible(False)
        self.ergebnis_tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self.ergebnis_tabelle, 1)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        self.summe.setTextFormat(Qt.RichText)
        lay.addWidget(self.summe)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("In Position übernehmen")
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.ok_knopf = knoepfe.button(QDialogButtonBox.Ok)
        for z in e["konturen"]:
            self.zeile_neu(z, rechnen_=False)
        self.rechnen()

    # ------------------------------------------------------------------ Eingaben
    def zeile_neu(self, z, rechnen_=True):
        self.tabelle.blockSignals(True)
        r = self.tabelle.rowCount()
        self.tabelle.insertRow(r)
        art = QComboBox()
        art.addItems(sw.ARTEN)
        art.setCurrentText(z.get("art") or sw.BOHRUNG)
        art.currentTextChanged.connect(lambda _=None, art=art: self._art_geaendert(art))
        self.tabelle.setCellWidget(r, 0, art)
        werte = [z.get("anzahl")] + [z.get(k_) for k_, _ in sw.MASSE.get(art.currentText(), ())]
        werte += [None] * (4 - len(werte))
        for c, v in enumerate(werte, start=1):
            self.tabelle.setItem(r, c, QTableWidgetItem(rechnen.zahl(v, 3) if isinstance(v, (int, float)) else ""))
        self.tabelle.setItem(r, 5, QTableWidgetItem(z.get("text") or ""))
        self._kopf_hinweise(r)
        self.tabelle.blockSignals(False)
        if rechnen_:
            self.rechnen()

    def _art_geaendert(self, combo):
        for r in range(self.tabelle.rowCount()):
            if self.tabelle.cellWidget(r, 0) is combo:
                self._kopf_hinweise(r)
        self.rechnen()

    def _kopf_hinweise(self, r):
        """Tooltip je Maßzelle: welches Maß die Art an dieser Stelle braucht."""
        masse = sw.MASSE.get(self.tabelle.cellWidget(r, 0).currentText(), ())
        for i in range(3):
            it = self.tabelle.item(r, 2 + i)
            if it is not None:
                it.setToolTip(masse[i][1] if i < len(masse) else "nicht benötigt")
                it.setFlags(it.flags() | Qt.ItemIsEditable if i < len(masse) else it.flags() & ~Qt.ItemIsEditable)
                if i >= len(masse):
                    it.setText("")

    def _entfernen(self):
        for r in sorted({i.row() for i in self.tabelle.selectedIndexes()}, reverse=True):
            self.tabelle.removeRow(r)
        self.rechnen()

    def eingaben(self):
        konturen = []
        for r in range(self.tabelle.rowCount()):
            art = self.tabelle.cellWidget(r, 0).currentText()
            z = dict(art=art, anzahl=_zahl(self.tabelle.item(r, 1).text()))
            for i, (k_, _) in enumerate(sw.MASSE.get(art, ())):
                z[k_] = _zahl(self.tabelle.item(r, 2 + i).text())
            t = self.tabelle.item(r, 5).text().strip()
            if t:
                z["text"] = t
            konturen.append(z)
        enden = {s: dict(winkel=self.winkel[s].value(), achse=self.achse[s].currentText()) for s in ("a", "b")}
        return dict(enden, gravur=self.gravur.value() or None, konturen=konturen)

    # ------------------------------------------------------------------ Ergebnis
    def rechnen(self, *_):
        erg = sw.rechnen(self.eingaben(), self.profil, self.grenzen)
        self.ergebnis = erg
        t = self.ergebnis_tabelle
        t.setRowCount(len(erg["schritte"]))
        for r, s in enumerate(erg["schritte"]):
            werte = (s["text"] + (" (Schätzung)" if s["schaetzung"] else ""), str(s["anzahl"]),
                     rechnen.zahl(s["laenge_stueck"], 1), rechnen.zahl(s["laenge"], 1), str(s["einstiche"]),
                     "–" if s["huelle"] is None else rechnen.zahl(s["huelle"], 1), s["klasse"])
            for c, v in enumerate(werte):
                it = QTableWidgetItem(v)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
        f = erg["felder"]
        zeit = self.schneidzeit()
        teile = [f"<b>Schneidweg {rechnen.zahl(f['schneidweg'], 1)} mm</b>, {f['einstiche']} Einstiche "
                 f"(Enden {rechnen.zahl(f['a_schnitt'], 1)} + {rechnen.zahl(f['b_schnitt'], 1)} mm, Innenkonturen "
                 f"{rechnen.zahl(f['innen'], 1)} mm: klein {f['klein_n']}, mittel {f['mittel_n']}, groß {f['gross_n']})",
                 f"Schneidzeit je Teil {rechnen.zahl(zeit, 1)} s (Schneiddaten der Maschine)" if zeit is not None
                 else "<span style='color:#7A5A00'>Keine Schneiddaten für Maschine, Werkstoff und Wandstärke: "
                      "Schneidzeit von Hand eintragen.</span>"]
        if erg["schaetzung"]:
            teile.append("<span style='color:#7A5A00'>Gehrung an diesem Profil: Schnittlänge geschätzt (gerade "
                         "Schnittlänge / cos Winkel).</span>")
        if not sw._z(self.p.get("zeit_manuell")) == 0:
            teile.append("<span style='color:#7A5A00'>Die Position hat eine Schneidzeit von Hand; sie gilt weiter, "
                         "bis sie in der Positionsliste gelöscht wird.</span>")
        if erg["fehler"]:
            teile.append("<span style='color:#B42318'>" + "<br>".join(erg["fehler"]) + "</span>")
        self.summe.setText("<br>".join(teile))
        if hasattr(self, "ok_knopf"):
            self.ok_knopf.setEnabled(not erg["fehler"])

    def schneidzeit(self):
        """Schneidzeit je Teil [s] mit den neuen Werten oder None ohne Schneiddaten."""
        p = dict(self.p, **self.ergebnis["felder"])
        return rechnen.schneidzeit(p, self.kopf, rechnen.wand_schneiden(self.profil), self.tabellen, self.k)[2]

    def _ok(self):
        self.rechnen()
        if not self.ergebnis["fehler"]:
            self.accept()
