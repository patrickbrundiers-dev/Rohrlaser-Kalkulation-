"""Stückliste der Schweißbaugruppe im Editor (Editor 2.0, 19.11.2026): alle Einzelteile mit Art, Unterbaugruppe und
Stückzahl je Unterbaugruppe, je Baugruppe und für den Auftrag; dazu Nahtgruppen und Arbeitsgänge als Zahl. Die Liste
entsteht aus dem Stand des Fensters (auch ungespeichert), lässt sich kopieren und als CSV speichern. Die Stückliste
des Angebots (Datei → CSV, export.stueckliste_zeilen) bleibt daneben bestehen."""
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QLabel, QPushButton, QVBoxLayout)

from . import baugruppe
from .angebot import ist_zukaufteil

SPALTEN = ("Pos.", "Artikel", "Bezeichnung", "Art", "Profil", "Unterbaugruppe", "je Unterbaugruppe", "je Baugruppe",
           "Auftrag")
ROHR, BLECH, ZUKAUF = "Rohrteil", "Blechteil", "Zukaufteil"


def teil_art(p):
    """Art eines Einzelteils für Baum und Stückliste."""
    if ist_zukaufteil(p):
        return ZUKAUF
    return BLECH if p.get("technik") and not p.get("profil_id") else ROHR


def _zahl(w):
    return f"{w:g}".replace(".", ",") if isinstance(w, (int, float)) else ""


def zeilen(bg, teile, anzahl):
    """[[Text je Spalte]] für die Teile im Fenster (dicts mit _q = Position, drin, knoten, je), sortiert nach Pos."""
    namen = {k["id"]: k.get("name") or "Unterbaugruppe" for k in bg.get("knoten") or ()}
    out = []
    for t in teile:
        if not t.get("drin"):
            continue
        q = t["_q"]
        kid = t.get("knoten") or ""
        f = baugruppe.faktor(bg, kid)
        je = t.get("je") or 1
        je_bg = je * f if f is not None else None
        out.append([str(q.get("pos") or ""), str(q.get("artikel") or ""), str(q.get("bezeichnung") or ""), teil_art(q),
                    str(q.get("profil_id") or ""), namen.get(kid, ""), _zahl(je), _zahl(je_bg) if je_bg is not None
                    else "?", _zahl(je_bg * anzahl) if je_bg is not None and anzahl else ""])

    def schluessel(z):
        try:
            return (0, float(z[0].replace(",", ".")), z[0])
        except ValueError:
            return (1, 0.0, z[0])
    return sorted(out, key=schluessel)


def als_text(liste, trenner="\t"):
    return "\n".join(trenner.join(z) for z in [list(SPALTEN)] + liste)


class StuecklisteDialog(QDialog):
    def __init__(self, parent, bg, teile, anzahl, titel=""):
        super().__init__(parent)
        from .bg_zeit_dialoge import _tabelle, _zelle
        self.setWindowTitle("Stückliste der Schweißbaugruppe")
        self.resize(900, 420)
        self.liste = zeilen(bg, teile, anzahl)
        lay = QVBoxLayout(self)
        arten = {}
        for z in self.liste:
            arten[z[3]] = arten.get(z[3], 0) + 1
        self.kopf = QLabel(f"<b>{titel or 'Baugruppe'}</b>: {len(self.liste)} Einzelteile ("
                           + ", ".join(f"{n} {a}{'e' if n != 1 else ''}" for a, n in sorted(arten.items()))
                           + f"), {len(bg.get('naehte') or ())} Nahtgruppen, {len(bg.get('arbeitsgaenge') or ())} "
                           f"Arbeitsgänge · Auftrag {anzahl:g} Baugruppen")
        self.kopf.setWordWrap(True)
        lay.addWidget(self.kopf)
        self.tab = _tabelle(list(SPALTEN))
        self.tab.setObjectName("bg_stueckliste_tabelle")
        for z in self.liste:
            i = self.tab.rowCount()
            self.tab.insertRow(i)
            for c, text in enumerate(z):
                self.tab.setItem(i, c, _zelle(text, c in (0, 6, 7, 8)))
        lay.addWidget(self.tab)
        k = QDialogButtonBox(QDialogButtonBox.Close)
        kop = QPushButton("Kopieren")
        kop.setToolTip("Stückliste in die Zwischenablage (z. B. für Excel)")
        kop.clicked.connect(lambda: QApplication.clipboard().setText(als_text(self.liste)))
        k.addButton(kop, QDialogButtonBox.ActionRole)
        csv = QPushButton("Als CSV speichern …")
        csv.clicked.connect(lambda: self.speichern())
        k.addButton(csv, QDialogButtonBox.ActionRole)
        k.rejected.connect(self.reject)
        lay.addWidget(k)

    def speichern(self, pfad=None):
        if not pfad:
            pfad, _ = QFileDialog.getSaveFileName(self, "Stückliste speichern", "Stueckliste_Baugruppe.csv", "CSV (*.csv)")
        if not pfad:
            return None
        with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
            f.write(als_text([[x.replace(";", ",") for x in z] for z in self.liste], ";") + "\n")
        return pfad
