"""Dialoge mit 3D-Ansicht: Prüfen der STEP-Messung vor dem Übernehmen und Ansehen der Positionen eines Angebots."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QLabel, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from .ansicht3d import Ansicht3DMitKnoepfen
from .stammdaten import zahl_als_text

PRUEF_SPALTEN = ("Datei", "Körper", "Profil", "Länge [mm]", "Schneidweg [mm]", "Innenkonturen [Stk]", "Gravur [mm]",
                 "Bohrungen", "Enden gerade", "Hinweis")


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


class StepPruefDialog(_Mit3D):
    """Messwerte aller Körper mit 3D-Ansicht; OK = übernehmen."""

    def __init__(self, parent, messwerte):
        super().__init__(parent, f"STEP-Import prüfen ({len(messwerte)} Teil{'e' if len(messwerte) != 1 else ''})",
                         PRUEF_SPALTEN)
        self.messwerte = messwerte
        self._fuellen([(m.get("datei"), m.get("koerper"), m.get("profil_id_vorschlag") or m.get("profilform"),
                        _f(m, "laenge"), _f(m, "schneidweg"), int(_f(m, "innen_konturen")), _f(m, "gravur"),
                        (m.get("bohrungen") or "").replace("|", "; "),
                        "/".join("ja" if m.get(e) == "1" else "nein" for e in ("ende_a_gerade", "ende_b_gerade")),
                        m.get("fehler") or m.get("hinweise")) for m in messwerte])
        hinweis = QLabel("Teile in der Liste wählen und in der 3D-Ansicht prüfen: Anfangsschnitt orange, Endschnitt "
                         "violett, Innenkonturen rot, Gravur grün. <b>Übernehmen</b> legt die Positionen an.")
        hinweis.setWordWrap(True)
        self.lay.addWidget(hinweis)
        knoepfe = QDialogButtonBox()
        knoepfe.addButton("Übernehmen", QDialogButtonBox.AcceptRole)
        knoepfe.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        self.lay.addWidget(knoepfe)
        if messwerte:
            self.liste.selectRow(0)
            self._zeigen(0)

    def _zeigen(self, r):
        if 0 <= r < len(self.messwerte):
            m = self.messwerte[r]
            self.ansicht.setzen(m.get("_netz"), f"{m.get('artikel')}", _messinfo(m))


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
