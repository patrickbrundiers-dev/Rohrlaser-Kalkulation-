"""Fenster „Ähnliche Teile und Revisionen“ (GEO-014, GEO-019; aehnliche_teile.py): ähnliche Teile aus früheren
Angeboten mit Ähnlichkeit, Unterschieden und dem Preis von damals; für die gewählte Zeile die Preiswirkung jeder
Änderung (heute gerechnet). Nur Anzeige: übernommen wird nichts, ein Doppelklick öffnet das alte Angebot."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import aehnliche_teile as at

SPALTEN = ("Ähnlichkeit", "Angebot", "Datum", "Kunde", "Artikel", "Profil", "Länge [mm]", "Konturen",
           "Unterschiede", "Preis damals", "Status")


def _datum(d):
    d = str(d or "")
    return f"{d[8:10]}.{d[5:7]}.{d[:4]}" if len(d) >= 10 else d


def _zahl(w, n=0):
    return f"{w:.{n}f}".replace(".", ",") if isinstance(w, (int, float)) else ""


class AehnlicheDialog(QDialog):
    def __init__(self, parent, p, treffer, preiswirkung=None, oeffnen=None):
        """treffer = aehnliche_teile.suchen; preiswirkung(alt) -> dict (aehnliche_teile.preiswirkung) oder None;
        oeffnen(angebot_id) öffnet das alte Angebot."""
        super().__init__(parent)
        self.p, self.treffer, self._wirkung, self._oeffnen = p, treffer, preiswirkung, oeffnen
        self.setWindowTitle(f"Ähnliche Teile und Revisionen – Pos. {p.get('pos') or ''} "
                            f"{p.get('artikel') or p.get('bezeichnung') or ''}".strip())
        self.resize(1200, 520)
        lay = QVBoxLayout(self)
        kopf = QLabel(f"{len(treffer)} ähnliche Teile in früheren Angeboten (ab {round(100 * at.GRENZE)} % "
                      "Ähnlichkeit: Profilform und Maß, Länge, Konturen, Schneidweg je Meter, Werkstoff). Der Preis "
                      "von damals ist nur zum Vergleich, gerechnet wird immer neu." if treffer else
                      "Keine ähnlichen Teile in früheren Angeboten gefunden.")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        self.tabelle = QTableWidget(len(treffer), len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.verticalHeader().hide()
        for r, t in enumerate(treffer):
            q, a = t["position"], t["angebot"]
            kont = "/".join(str(int(q.get(n) or 0)) for n in ("klein_n", "mittel_n", "gross_n"))
            preis = (f"{_zahl(t['preis'][1], 2)} € bei {_zahl(t['preis'][0])} Stk" if t["preis"] else "")
            werte = (f"{round(100 * t['aehnlichkeit'])} %", a["nummer"] or "", _datum(a["datum"]), a["kunde"] or "",
                     q.get("artikel") or q.get("bezeichnung") or "", q.get("profil_id") or "", _zahl(q.get("laenge")),
                     kont, ", ".join(t["unterschiede"]) or "gleich", preis,
                     a["vorgang"] + (" (Kollege)" if a.get("fremd") else ""))
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                if c in (0, 6):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(r, c, it)
        k = self.tabelle.horizontalHeader()
        for c in range(len(SPALTEN)):
            k.setSectionResizeMode(c, QHeaderView.Stretch if SPALTEN[c] == "Unterschiede" else
                                   QHeaderView.ResizeToContents)
        self.tabelle.itemSelectionChanged.connect(self._gewaehlt)
        self.tabelle.itemDoubleClicked.connect(lambda _it: self.oeffnen())
        lay.addWidget(self.tabelle, 1)
        self.wirkung = QLabel("Zeile wählen: zeigt, was jede Änderung gegenüber dem alten Teil heute am Preis je Stück "
                              "ausmacht.")
        self.wirkung.setWordWrap(True)
        self.wirkung.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.wirkung)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        self.oeffnen_knopf = QPushButton("Angebot öffnen")
        self.oeffnen_knopf.setEnabled(False)
        self.oeffnen_knopf.clicked.connect(self.oeffnen)
        knoepfe.addButton(self.oeffnen_knopf, QDialogButtonBox.ActionRole)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        if treffer:
            self.tabelle.selectRow(0)

    def zeile(self):
        r = self.tabelle.currentRow()
        return r if 0 <= r < len(self.treffer) else None

    def _gewaehlt(self):
        r = self.zeile()
        self.oeffnen_knopf.setEnabled(r is not None and self._oeffnen is not None)
        if r is None:
            return
        t = self.treffer[r]
        if not t["unterschiede"]:
            self.wirkung.setText(f"Gleiche Geometrie wie in {t['angebot']['nummer']}.")
            return
        w = self._wirkung(t["position"]) if self._wirkung else None
        if not w:
            self.wirkung.setText("Preiswirkung: lässt sich nicht rechnen (Daten unvollständig).")
            return
        e = (lambda x: f"{x:.2f}".replace(".", ",") + " €")
        txt = at.preiswirkung_text(w) or "keine messbare Wirkung"
        damals = (f"; Angebotspreis damals {e(t['preis'][1])} bei {_zahl(t['preis'][0])} Stk" if t["preis"] else "")
        self.wirkung.setText(f"<b>Preiswirkung</b> gegenüber {t['angebot']['nummer']} (heute gerechnet, Teil allein): "
                             f"{txt}. Heute {e(w['heute'])} je Stück, mit den alten Werten {e(w['alt_gerechnet'])}"
                             f"{damals}.")

    def oeffnen(self):
        r = self.zeile()
        if r is not None and self._oeffnen is not None:
            self._oeffnen(self.treffer[r]["angebot"]["id"])
            self.accept()
