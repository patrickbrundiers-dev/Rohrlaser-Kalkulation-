"""Kontur-Vorlagen im Teile-Editor (Plan 3D-Editor E1, E3, Schritt 3E-6): gewählte Konturzeilen (z. B. ein Bohrbild
oder eine Steckverbindung, mit ihren Abständen) unter einem Namen speichern und in andere Teile einsetzen; optional nur
für einen Kunden. Getrennt nach Rohr und Blech (die Lage zählt anders: Rohr x ab Ende A und Seite, Blech x/y in der
Abwicklung). Dazu die Auswahl mit Vorschaubild für „Aus Position“ und für die Vorlagen.

Tabelle kontur_vorlagen (Schema 58, mit den Stammdaten geteilt): name, art (Rohr/Blech), kunde, profilform,
konturen (JSON), inhalt (Kurztext), angelegt, bemerkung.
"""
import datetime
import json

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem,
                               QVBoxLayout)

from . import blech, schneidweg as sw

TABELLE = "kontur_vorlagen"
ROHR, BLECH = "Rohr", "Blech"
VORSCHAU_PROFIL = {      # Profil für das Vorschaubild, wenn das Teil keines hat (Blech braucht keins)
    "Rundrohr": dict(form="Rundrohr", a=48.3, wand=2.6),
    "Rechteckrohr": dict(form="Rechteckrohr", a=60, b=40, wand=3),
}
VORSCHAU_STANDARD = dict(form="Quadratrohr", a=40, b=40, wand=3)
_z = sw._z


def inhalt(konturen):
    """Kurztext wie '2× Bohrung, Langloch' (Anzahl der Zeilen je Art, in der Reihenfolge des ersten Auftretens)."""
    n = {}
    for z in konturen:
        a = z.get("art") or "?"
        n[a] = n.get(a, 0) + 1
    return ", ".join(f"{k}× {a}" if k > 1 else a for a, k in n.items())


def sauber(konturen):
    """Konturzeilen ohne Messwerte aus dem STEP-Import und ohne Kopien am Umfang (die rechnet der Editor neu)."""
    weg = ("gemessen", "step", "kopien", "quelle")
    return [{k: v for k, v in z.items() if k not in weg and v not in (None, "")} for z in konturen if z.get("art")]


def liste(db, art, kunde=None):
    """Vorlagen der Art (Rohr/Blech): allgemeine und die des Kunden, die des Kunden zuerst, sonst nach Name."""
    if db is None:
        return []
    out = [z for z in db.zeilen(TABELLE) if (z.get("art") or ROHR) == art and (not z.get("kunde") or z["kunde"] == kunde)]
    return sorted(out, key=lambda z: (not z.get("kunde"), (z.get("name") or "").lower()))


def speichern(db, name, art, konturen, kunde=None, profilform=None, bemerkung=None, ueberschreiben=False):
    """Konturzeilen als Vorlage speichern; ValueError ohne Namen/Konturen oder bei vorhandenem Namen (gleiche Art
    und gleicher Kunde) ohne ueberschreiben. Ergebnis: ID."""
    name = (name or "").strip()
    k = sauber(konturen)
    if not name:
        raise ValueError("Bitte einen Namen für die Vorlage eintragen.")
    if not k:
        raise ValueError("Keine Konturen gewählt.")
    werte = dict(name=name, art=art, kunde=kunde or None, profilform=profilform or None,
                 konturen=json.dumps(k, ensure_ascii=False), inhalt=inhalt(k),
                 angelegt=datetime.datetime.now().isoformat(timespec="seconds"), bemerkung=bemerkung)
    alt = next((z for z in db.zeilen(TABELLE) if z.get("name") == name and (z.get("art") or ROHR) == art
                and (z.get("kunde") or None) == (kunde or None)), None)
    if alt and not ueberschreiben:
        raise ValueError(f"Die Vorlage '{name}' gibt es schon.")
    if alt:
        for feld in ("profilform", "konturen", "inhalt", "angelegt", "bemerkung"):
            db.aendern(TABELLE, alt["id"], feld, werte[feld])
        return alt["id"]
    return db.neu(TABELLE, werte)


def loeschen(db, vorlage_id):
    db.loeschen(TABELLE, [vorlage_id])


def konturen(zeile):
    """Konturzeilen einer Vorlage (Liste, leer bei beschädigten Daten)."""
    try:
        k = json.loads((zeile or {}).get("konturen") or "[]")
    except (TypeError, ValueError):
        return []
    return [z for z in k if isinstance(z, dict) and z.get("art")] if isinstance(k, list) else []


def _verschoben_rohr(k, L):
    """Lage x bleibt, wenn alle Konturen ins Teil passen; sonst die Gruppe mittig ins Teil schieben."""
    xs = [_z(z["x"]) for z in k if z.get("x") is not None]
    if not xs or not L or (min(xs) >= 0 and max(xs) <= L):
        return k
    d = L / 2 - (min(xs) + max(xs)) / 2
    return [dict(z, x=round(_z(z["x"]) + d, 3)) if z.get("x") is not None else z for z in k]


def _verschoben_blech(k, lg, br):
    pk = [(_z(z["x"]), _z(z["y"])) for z in k if z.get("x") is not None and z.get("y") is not None]
    if not pk or not lg or not br:
        return k
    xs, ys = [p[0] for p in pk], [p[1] for p in pk]
    if min(xs) >= 0 and max(xs) <= lg and min(ys) >= 0 and max(ys) <= br:
        return k
    dx, dy = lg / 2 - (min(xs) + max(xs)) / 2, br / 2 - (min(ys) + max(ys)) / 2
    return [dict(z, x=round(_z(z["x"]) + dx, 3), y=round(_z(z["y"]) + dy, 3))
            if z.get("x") is not None and z.get("y") is not None else z for z in k]


def einsetzbar(zeile, art, laenge=None, breite=None):
    """Konturzeilen zum Anhängen: Lage wie gespeichert, außerhalb des Teils mittig hineingeschoben (Rohr: Teilelänge,
    Blech: Länge × Breite der Abwicklung)."""
    k = [dict(z) for z in konturen(zeile)]
    return _verschoben_rohr(k, laenge) if art == ROHR else _verschoben_blech(k, laenge, breite)


def bild(zeile, art, profil=None, breite=220, hoehe=56):
    """Vorschaubild einer Vorlage (QPixmap) oder None."""
    from . import vorschau
    k = konturen(zeile)
    if art == BLECH:
        pk = [(_z(z.get("x")), _z(z.get("y"))) for z in k if z.get("x") is not None and z.get("y") is not None]
        lg = max([x for x, _ in pk] + [60.0]) + 30
        br = max([y for _, y in pk] + [30.0]) + 30
        e = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=2, laenge=lg, breite=br, konturen=k)
        return vorschau.blech_bild(e, breite, hoehe)
    profil = profil or VORSCHAU_PROFIL.get((zeile or {}).get("profilform"), VORSCHAU_STANDARD)
    xs = [_z(z.get("x")) for z in k if z.get("x") is not None]
    L = max(xs + [100.0]) + 40
    p = dict(laenge=L, technik=json.dumps(dict(a={}, b={}, konturen=k)))
    return vorschau.rohr(p, profil, breite, hoehe)


class AuswahlMitBild(QDialog):
    """Liste mit großem Vorschaubild je Eintrag (E3: „Aus Position“ mit Vorschau statt Textliste). eintraege:
    [(Text, Bild oder None, Wert)]; nach OK: wert."""

    def __init__(self, parent, titel, hinweis, eintraege, bildgroesse=QSize(220, 56)):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.wert = None
        lay = QVBoxLayout(self)
        if hinweis:
            lay.addWidget(QLabel(hinweis))
        self.liste = QListWidget()
        self.liste.setIconSize(bildgroesse)
        self.liste.setSelectionMode(QAbstractItemView.SingleSelection)
        self.liste.setSpacing(2)
        for text, pm, wert in eintraege:
            it = QListWidgetItem(QIcon(pm) if pm is not None else QIcon(), text)
            it.setData(Qt.UserRole, wert)
            it.setSizeHint(QSize(bildgroesse.width() + 360, bildgroesse.height() + 8))
            self.liste.addItem(it)
        self.liste.itemDoubleClicked.connect(lambda _: self.accept())
        lay.addWidget(self.liste, 1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        if self.liste.count():
            self.liste.setCurrentRow(0)
        self.resize(bildgroesse.width() + 420, min(640, 120 + self.liste.count() * (bildgroesse.height() + 12)))

    def accept(self):
        it = self.liste.currentItem()
        self.wert = it.data(Qt.UserRole) if it is not None else None
        super().accept()
