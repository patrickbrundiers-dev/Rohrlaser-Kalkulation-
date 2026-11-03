"""Fenster „Bleche“ im Angebot (Patrick 03.11.2026: „Bleche mit Richtwerten anzeigen, die dann geändert werden
können“, „Tafelbelegung … um es visuell zu haben“, „erst nur visuell“).

Reiter Bleche: je Blech der Position Werkstoff, Dicke, Zuschnitt, Stück, Gewicht, Laserzeit, Richtpreis (immer
berechnet, eigene Werte aus dem Blech-Editor eingerechnet), Angebotspreis und Lieferant – beide hier änderbar
(leer = Richtpreis). Doppelklick auf eine andere Spalte öffnet den Blech-Editor.
Reiter Tafelbelegung: je Werkstoff und Dicke alle Bleche des Angebots gemeinsam auf Tafeln (blech.tafel_gemischt),
nur zum Ansehen; die Rechnung bleibt je Teil."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QGroupBox, QHeaderView, QLabel,
                               QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import blech, blech_preis, stil
from .blech_dialog import TafelBild
from .stammdaten import zahl_als_text, zahl_aus_text

SPALTEN = ("Pos.", "Bezeichnung", "Werkstoff", "Dicke [mm]", "Zuschnitt [mm]", "Stück", "Gewicht [kg]",
           "Laserzeit [s]", "eigene Werte", "Richtpreis [€/St]", "Angebotspreis [€/St]", "Lieferant")
PREIS, LIEFERANT = 10, 11
OEFFNEN = 2         # Ergebnis von exec: Blech-Editor der Zeile oeffnen_zeile öffnen


def _z(w, n):
    return zahl_als_text(float(w), n) if isinstance(w, (int, float)) else ""


def zeilen(positionen, daten):
    """[dict(zeile, p, e, erg, stand)] je Blech der Positionen [(Zeile, Position)]."""
    out = []
    for r, p in positionen:
        e = blech.lesen(p.get("technik"))
        st = blech_preis.stand(p, daten)
        if e is None or st is None:
            continue
        erg = blech.rechnen(dict(e, stueck=p.get("stueck") or e.get("stueck")), daten.get("werkstoffe") or {},
                            daten.get("laser") or [], daten.get("einst"))
        out.append(dict(zeile=r, p=p, e=e, erg=erg, stand=st))
    return out


def tafel_gruppen(liste, einst):
    """Gemeinsame Tafelbelegung je (Werkstoff, Dicke): [(Titel, Belegung oder None)]."""
    w = dict(blech.EINSTELLUNGEN, **{n: v for n, v in (einst or {}).items() if v is not None})
    gruppen = {}
    for z in liste:
        zs = z["erg"].get("zuschnitt")
        if not zs:
            continue
        schl = (z["e"].get("werkstoff") or "?", float(z["e"].get("dicke") or 0))
        gruppen.setdefault(schl, []).append((zs["laenge"], zs["breite"], z["p"].get("stueck") or 1,
                                             str(z["p"].get("pos") or z["zeile"] + 1)))
    out = []
    for (wst, s), teile in sorted(gruppen.items()):
        t = blech.tafel_gemischt(teile, blech.tafelformate(w.get("blech_tafeln")), blech._z(w.get("blech_tafel_rand")),
                                 blech._z(w.get("blech_tafel_steg")))
        n = sum(int(x[2]) for x in teile)
        titel = f"{wst} {s:g} mm: {len(teile)} Position(en), {n} Teile"
        if t:
            titel += (f" auf {t['tafeln']} Tafel(n) {t['format'][0]:g} × {t['format'][1]:g} mm, Ausnutzung "
                      f"{zahl_als_text(t['ausnutzung'] * 100, 0)} %")
            if t["fehlt"]:
                titel += f" · passt auf keine Tafel: Pos. {', '.join(sorted(set(t['fehlt'])))}"
        out.append((titel, t))
    return out


class BlecheDialog(QDialog):
    def __init__(self, parent, positionen, daten, nur_lesen=False):
        super().__init__(parent)
        self.setWindowTitle("Bleche: Richtwerte, Angebotspreise, Tafelbelegung")
        self.daten, self.nur_lesen = daten, nur_lesen
        self.liste = zeilen(positionen, daten)
        self.oeffnen_zeile = None
        lay = QVBoxLayout(self)
        text = QLabel("Richtpreise werden immer aus den Richtwerten berechnet (eigene Werte je Teil im Blech-Editor). "
                      "Eingeholten <b>Angebotspreis</b> des Lieferanten eintragen: er gilt dann im Angebot statt des "
                      "Richtpreises (kein Gewinn, nur Aufschlag). Leeren = wieder Richtpreis. Doppelklick auf eine "
                      "andere Spalte öffnet den Blech-Editor.")
        text.setWordWrap(True)
        lay.addWidget(text)
        self.reiter = QTabWidget()
        lay.addWidget(self.reiter, 1)
        self.tabelle = self._tabelle()
        self.reiter.addTab(self.tabelle, f"Bleche ({len(self.liste)})")
        self.reiter.addTab(self._tafeln(), "Tafelbelegung (Ansicht)")
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Preise übernehmen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.resize(1250, 640)

    def _tabelle(self):
        t = QTableWidget(len(self.liste), len(SPALTEN))
        t.setHorizontalHeaderLabels(SPALTEN)
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.AllEditTriggers if not self.nur_lesen else QAbstractItemView.NoEditTriggers)
        for r, z in enumerate(self.liste):
            p, e, erg, st = z["p"], z["e"], z["erg"], z["stand"]
            zs = erg.get("zuschnitt") or {}
            werte = (str(p.get("pos") or z["zeile"] + 1), p.get("bezeichnung") or p.get("artikel") or "",
                     e.get("werkstoff") or "", _z(e.get("dicke"), 2),
                     f"{_z(zs.get('laenge'), 1)} × {_z(zs.get('breite'), 1)}" if zs else "",
                     _z(p.get("stueck"), 0), _z(erg.get("gewicht"), 3), _z(erg.get("zeit"), 1),
                     ", ".join(n for n, *_ in blech.RICHTWERTE if n in (erg.get("eigene") or {})) or "–",
                     _z(erg.get("richtpreis") or st.get("richtpreis"), 2),
                     _z(st["ek"], 2) if st["angebot"] else "",
                     (st.get("lieferant") or "") if st["angebot"] else "")
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if c not in (PREIS, LIEFERANT) or self.nur_lesen:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setBackground(stil.farbe("#FFF2CC" if w else "#FFFFFF"))
                if c in (0, 3, 5, 6, 7, 9, 10):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 7 and "zeit" in (erg.get("aus_step") or ()):
                    it.setToolTip("Schneidweg aus der STEP gemessen")
                if c == 6 and "gewicht" in (erg.get("aus_step") or ()):
                    it.setToolTip("Gewicht aus dem Volumen der STEP")
                if c == 9:
                    it.setForeground(stil.farbe("#5F6B7A" if st["angebot"] else "#000000"))
                    it.setToolTip("Berechneter Richtpreis je Stück (EK-Vorschlag)")
                if c == PREIS:
                    it.setToolTip("Angebotspreis des Lieferanten je Stück; leer = Richtpreis")
                t.setItem(r, c, it)
        for c, b in enumerate((45, 220, 80, 70, 120, 55, 80, 80, 120, 100, 120, 130)):
            t.setColumnWidth(c, b)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        t.cellDoubleClicked.connect(self._doppelklick)
        return t

    def _doppelklick(self, r, c):
        if c in (PREIS, LIEFERANT) and not self.nur_lesen:
            return
        self.oeffnen_zeile = self.liste[r]["zeile"]
        self.done(OEFFNEN)

    def _tafeln(self):
        rollen = QScrollArea()
        rollen.setWidgetResizable(True)
        innen = QWidget()
        lay = QVBoxLayout(innen)
        for titel, t in tafel_gruppen(self.liste, self.daten.get("einst")):
            box = QGroupBox(titel)
            bl = QVBoxLayout(box)
            if not t:
                bl.addWidget(QLabel("Kein Teil passt auf ein Tafelformat (Einstellungen → Blech-Richtpreis)."))
            for i, bild in enumerate((t or {}).get("bilder") or ()):
                tb = TafelBild()
                verh = t["format"][1] / t["format"][0]
                tb.setMinimumHeight(int(min(420, max(160, 900 * verh + 44))))
                tb.setzen(dict(t, bilder=[dict(bild, titel=f"Tafel {i + 1}: {len(bild['teile'])} Teile")]), None,
                          f"Tafel {i + 1} von {t['tafeln']}")
                bl.addWidget(tb)
            lay.addWidget(box)
        lay.addStretch(1)
        rollen.setWidget(innen)
        return rollen

    def aenderungen(self):
        """[(Zeile der Position, Preis oder None, Lieferant)] der geänderten Angebotspreise."""
        out = []
        for r, z in enumerate(self.liste):
            st = z["stand"]
            t = self.tabelle.item(r, PREIS).text().strip()
            lief = self.tabelle.item(r, LIEFERANT).text().strip() or None
            try:
                preis = zahl_aus_text(t) if t else None
            except ValueError:
                continue
            preis = preis if preis and preis > 0 else None
            if preis is None and not st["angebot"]:
                continue
            if preis is not None and st["angebot"] and abs(preis - (st["ek"] or 0)) < 0.005 \
                    and (lief or None) == (st.get("lieferant") or None):
                continue
            out.append((z["zeile"], preis, lief))
        return out

