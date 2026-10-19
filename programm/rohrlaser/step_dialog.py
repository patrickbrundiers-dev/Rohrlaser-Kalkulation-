"""Dialoge mit 3D-Ansicht: Prüfen der STEP-Messung vor dem Übernehmen und Ansehen der Positionen eines Angebots."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .ansicht3d import Ansicht3DMitKnoepfen
from .stammdaten import zahl_als_text

def _f(m, name):
    try:
        return float(m.get(name) or 0)
    except ValueError:
        return 0.0


def _messinfo(m):
    if m.get("fehler"):
        return f"<b style='color:#C00000'>FEHLER: {m['fehler']}</b>"
    z = lambda name, st=1: zahl_als_text(_f(m, name), st)
    return (f"<b>{m.get('artikel')}</b>: {m.get('profilform')} {m.get('profil_id_vorschlag') or ''}, Länge {z('laenge')} mm, "
            f"Schneidweg {z('schneidweg')} mm (Anfangsschnitt {z('ende_a')}, Endschnitt {z('ende_b')}, Innenkonturen "
            f"{z('innen')} mm in {m.get('innen_konturen') or 0} Konturen), Gravur {z('gravur')} mm, Einstiche "
            f"{m.get('konturen') or 0}" + (f" · {m['hinweise']}" if m.get("hinweise") else ""))


class _Mit3D(QDialog):
    def __init__(self, parent, titel, spalten):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.resize(1250, 680)
        self.liste = QTableWidget(0, len(spalten))
        self.liste.setHorizontalHeaderLabels(spalten)
        self.liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.liste.setSelectionMode(QAbstractItemView.SingleSelection)
        self.liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.liste.verticalHeader().setDefaultSectionSize(22)
        self.liste.currentCellChanged.connect(lambda r, *_: self._zeigen(r))
        self.ansicht = Ansicht3DMitKnoepfen()
        teil = QSplitter(Qt.Horizontal)
        teil.addWidget(self.liste)
        teil.addWidget(self.ansicht)
        teil.setSizes([520, 730])
        self.lay = QVBoxLayout(self)
        self.lay.addWidget(teil, 1)

    def _fuellen(self, zeilen):
        self.liste.setRowCount(len(zeilen))
        for r, werte in enumerate(zeilen):
            for c, w in enumerate(werte):
                it = QTableWidgetItem("" if w is None else str(w))
                if isinstance(w, (int, float)):
                    it.setText(zahl_als_text(w, 1 if isinstance(w, float) else 0))
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.liste.setItem(r, c, it)
        self.liste.resizeColumnsToContents()


class StepPruefDialog(QDialog):
    """Gemessene Rohre je Profil mit 3D-Ansicht. Je Teil übernehmen ja/nein, Profil, Werkstoff und Stückzahl;
    gleiche Teile einer Datei stehen in einer Zeile (Spalte 'In Datei'). OK schreibt die Werte als _uebernehmen,
    _profil, _werkstoff, _stueck in die Messwerte (step.uebernehmen liest sie)."""
    SPALTEN = ("Teil", "In Datei", "Profil-ID", "Werkstoff-ID", "Stückzahl", "Länge [mm]", "Schneidweg [mm]",
               "Konturen", "Hinweis")

    def __init__(self, parent, messwerte, k, werkstoff=None, stueck=None):
        from . import step
        super().__init__(parent)
        self.messwerte, self.k = messwerte, k
        self.setWindowTitle(f"STEP-Import prüfen ({len(messwerte)} Teil{'e' if len(messwerte) != 1 else ''})")
        self.resize(1350, 720)
        self.baum = QTreeWidget()
        self.baum.setColumnCount(len(self.SPALTEN))
        self.baum.setHeaderLabels(self.SPALTEN)
        self.baum.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.baum.setUniformRowHeights(True)
        self.baum.setStyleSheet("QTreeView::item { min-height: 26px; }")     # Platz für Auswahlfelder
        self.baum.currentItemChanged.connect(lambda it, *_: self._zeigen(it))
        self.zeilen = []        # (Item, [Indizes der Messwerte], Profil-Combo, Werkstoff-Combo, Stückzahl-Spin)
        gruppen = {}            # gemessenes Profil -> Gruppen-Item
        teile = step.gleiche_teile(messwerte)
        fehler = [i for i, m in enumerate(messwerte) if not any(i in l for l in teile.values())]
        profile, werkstoffe = k.auswahl("profil"), k.auswahl("werkstoff")
        for erster, liste in sorted(teile.items(), key=lambda e: step.profil_vorschlag(messwerte[e[0]], k.profile) or ""):
            m = messwerte[erster]
            vorschlag = step.profil_vorschlag(m, k.profile)
            fehlt = vorschlag not in k.profile
            g = gruppen.get(vorschlag)
            if g is None:
                g = gruppen[vorschlag] = QTreeWidgetItem(self.baum)
                g.setFirstColumnSpanned(True)
                g.setData(0, Qt.UserRole, vorschlag)
                f = g.font(0)
                f.setBold(True)
                g.setFont(0, f)
                g.setBackground(0, QBrush(QColor("#FCE4D6" if fehlt else "#DDEBF7")))
                g.setExpanded(True)
            it = QTreeWidgetItem(g)
            it.setText(0, m.get("artikel") or m.get("datei") or "")
            it.setCheckState(0, Qt.Checked if step.gewaehlt(m) else Qt.Unchecked)
            it.setText(1, str(len(liste)))
            for c, w in ((5, _f(m, "laenge")), (6, _f(m, "schneidweg"))):
                it.setText(c, zahl_als_text(w, 1))
            it.setText(7, str(int(_f(m, "konturen"))))
            hinweis = ["Profil fehlt in den Stammdaten"] if fehlt else []
            hinweis += [h for h in [m.get("hinweise")] if h]
            it.setText(8, "; ".join(hinweis))
            for c in (1, 4, 5, 6, 7):
                it.setTextAlignment(c, int(Qt.AlignRight | Qt.AlignVCenter))
            pr = QComboBox()
            pr.setEditable(True)            # neue Profil-ID eintippen: wird beim Übernehmen angelegt (Rückfrage)
            pr.addItems(sorted(set(profile) | ({vorschlag} if vorschlag else set())))
            pr.setCurrentText(m.get("_profil") or vorschlag or "")
            ws = QComboBox()
            ws.addItems([""] + werkstoffe)
            ws.setCurrentText(m.get("_werkstoff", werkstoff) or "")
            sp = QSpinBox()
            sp.setRange(0, 100000)
            sp.setSpecialValueText("leer")
            sp.setValue(m.get("_stueck", stueck) or 0)
            for c, w in ((2, pr), (3, ws), (4, sp)):
                self.baum.setItemWidget(it, c, w)
            it.setData(0, Qt.UserRole, len(self.zeilen))
            self.zeilen.append((it, liste, pr, ws, sp, vorschlag))
        for g in gruppen.values():
            n = g.childCount()
            g.setText(0, f"{g.data(0, Qt.UserRole) or 'ohne Profil'} – {n} Teil{'e' if n != 1 else ''}"
                      + ("  (Profil fehlt in den Stammdaten)" if g.data(0, Qt.UserRole) not in k.profile else ""))
        if fehler:
            g = QTreeWidgetItem(self.baum, ["Nicht übernehmbar"])
            g.setFirstColumnSpanned(True)
            g.setBackground(0, QBrush(QColor("#F8CBAD")))
            g.setExpanded(True)
            for i in fehler:
                m = messwerte[i]
                it = QTreeWidgetItem(g, [f"{m.get('datei')} Körper {m.get('koerper') or ''}", "", "", "", "", "",
                                         "", "", m.get("fehler") or "kein Rohrteil erkannt"])
                it.setData(1, Qt.UserRole, i)
        for c, b in enumerate((250, 55, 130, 120, 75, 80, 95, 65, 260)):
            self.baum.setColumnWidth(c, b)

        # Werte für mehrere Teile auf einmal
        self.leiste = QWidget()
        alle = QHBoxLayout(self.leiste)
        alle.setContentsMargins(0, 0, 0, 0)
        alle.addWidget(QLabel("Werte setzen:"))
        self.alle_ws = QComboBox()
        self.alle_ws.addItems(["(Werkstoff)"] + werkstoffe)
        self.alle_stk = QSpinBox()
        self.alle_stk.setRange(0, 100000)
        self.alle_stk.setSpecialValueText("(Stückzahl)")
        alle.addWidget(self.alle_ws)
        alle.addWidget(self.alle_stk)
        for text, nur in (("Für markierte", True), ("Für alle", False)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, nur=nur: self.alle_setzen(nur_markierte=nur))
            alle.addWidget(b)
        alle.addSpacing(12)
        for text, an in (("Alle wählen", True), ("Keine wählen", False)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, an=an: self.alle_waehlen(an))
            alle.addWidget(b)
        alle.addStretch(1)

        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.baum, 1)
        ll.addWidget(self.leiste)
        self.ansicht = Ansicht3DMitKnoepfen()
        teil = QSplitter(Qt.Horizontal)
        teil.addWidget(links)
        teil.addWidget(self.ansicht)
        teil.setSizes([820, 530])
        lay = QVBoxLayout(self)
        lay.addWidget(teil, 1)
        hinweis = QLabel("Häkchen = Teil übernehmen. Profil, Werkstoff und Stückzahl je Teil wählen; leer = später "
                         "eintragen. Mehrere Zeilen markieren (Strg/Umschalt) und unten Werte setzen. Gleiche Teile einer Datei stehen "
                         "in einer Zeile. Bei einem Satz zählt die Stückzahl "
                         "die Sätze. In der 3D-Ansicht: Anfangsschnitt orange, Endschnitt violett, Innenkonturen rot, "
                         "Gravur grün.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        knoepfe = QDialogButtonBox()
        knoepfe.addButton("Übernehmen", QDialogButtonBox.AcceptRole)
        knoepfe.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        if self.zeilen:
            self._zeigen(self.zeilen[0][0])      # 3D des ersten Teils, ohne es zu markieren

    def _zeile(self, it):
        if it is None or it.parent() is None:
            return None
        n = it.data(0, Qt.UserRole)
        return self.zeilen[n] if isinstance(n, int) and 0 <= n < len(self.zeilen) and self.zeilen[n][0] is it else None

    def _zeigen(self, it):
        z = self._zeile(it)
        if z:
            m = self.messwerte[z[1][0]]
            self.ansicht.setzen(m.get("_netz"), m.get("artikel") or "", _messinfo(m))
        elif it is not None and it.data(1, Qt.UserRole) is not None:
            m = self.messwerte[it.data(1, Qt.UserRole)]
            self.ansicht.setzen(None, m.get("datei") or "", _messinfo(m))

    def _markiert(self):
        z = [self._zeile(it) for it in self.baum.selectedItems()]
        return [x for x in z if x]

    def alle_setzen(self, werkstoff=None, stueck=None, nur_markierte=False):
        """Werkstoff und/oder Stückzahl (None = Auswahl unten) in alle bzw. die markierten Zeilen schreiben."""
        werkstoff = werkstoff if werkstoff is not None else (
            self.alle_ws.currentText() if self.alle_ws.currentIndex() > 0 else None)
        stueck = stueck if stueck is not None else (self.alle_stk.value() or None)
        for _, _, _, ws, sp, _ in (self._markiert() if nur_markierte else self.zeilen):
            if werkstoff is not None:
                ws.setCurrentText(werkstoff)
            if stueck is not None:
                sp.setValue(stueck)

    def alle_waehlen(self, an):
        for it, *_ in self.zeilen:
            it.setCheckState(0, Qt.Checked if an else Qt.Unchecked)

    def zeile_setzen(self, artikel, uebernehmen=None, profil=None, werkstoff=None, stueck=None):
        """Werte einer Zeile ohne Maus setzen (Tests, Bildschirmfotos)."""
        for it, liste, pr, ws, sp, _ in self.zeilen:
            if it.text(0) == artikel:
                if uebernehmen is not None:
                    it.setCheckState(0, Qt.Checked if uebernehmen else Qt.Unchecked)
                if profil is not None:
                    pr.setCurrentText(profil)
                if werkstoff is not None:
                    ws.setCurrentText(werkstoff)
                if stueck is not None:
                    sp.setValue(stueck)
                return
        raise KeyError(artikel)

    def werte_schreiben(self):
        """Gewählte Werte in die Messwerte schreiben (_uebernehmen, _profil, _werkstoff, _stueck)."""
        for it, liste, pr, ws, sp, vorschlag in self.zeilen:
            profil = pr.currentText().strip()
            for i in liste:
                m = self.messwerte[i]
                m["_uebernehmen"] = it.checkState(0) == Qt.Checked
                m["_werkstoff"] = ws.currentText() or None
                m["_stueck"] = sp.value() or None
                if profil and profil != vorschlag:
                    m["_profil"] = profil
                else:
                    m.pop("_profil", None)
        return self.messwerte

    def accept(self):
        self.werte_schreiben()
        super().accept()


class Positionen3DDialog(_Mit3D):
    """3D-Ansicht der Positionen eines Angebots (Teile aus dem STEP-Import)."""

    def __init__(self, parent, positionen, netze, gewaehlt=0):
        super().__init__(parent, "3D-Ansicht der Positionen", ("Pos.", "Artikelnummer", "Bezeichnung", "Profil-ID",
                                                              "Teilelänge [mm]", "3D"))
        self.positionen, self.netze = positionen, netze
        self._fuellen([(p.get("pos"), p.get("artikel"), p.get("bezeichnung"), p.get("profil_id"), p.get("laenge"),
                        "ja" if p["id"] in netze else "–") for p in positionen])
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        self.lay.addWidget(knoepfe)
        if positionen:
            self.liste.selectRow(gewaehlt)
            self._zeigen(gewaehlt)

    def _zeigen(self, r):
        if 0 <= r < len(self.positionen):
            p = self.positionen[r]
            titel = f"Pos. {p.get('pos') or ''} {p.get('artikel') or ''}"
            info = "" if p["id"] in self.netze else "Für diese Position gibt es keine 3D-Daten (nicht per STEP-Import)."
            self.ansicht.setzen(self.netze.get(p["id"]), titel, info)
