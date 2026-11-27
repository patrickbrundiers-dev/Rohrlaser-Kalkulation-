"""Bausteine des Designsystems „Klar“ (UI/UX Next Level, Freigabe Patrick 26.11.2026, Variante A).

Neue und überarbeitete Oberflächen setzen sich aus diesen Bausteinen zusammen, statt eigene Farben, Rahmen und
Abstände zu setzen. Das Aussehen kommt allein aus dem Stylesheet (stil.py) über die Objektnamen; die Werte stehen in
design.py. Dadurch passen spätere Erweiterungen automatisch zum Gesamtbild, und Hell, Dunkel und Hoher Kontrast
gelten ohne Zutun.

- seitenkopf(titel, untertitel, aktionen): Titel und Untertitel links, Aktionen rechts (Hauptknopf zuletzt)
- karte(titel): Karte mit Titelzeile; Inhalt in karte.inhalt (QVBoxLayout)
- kennzahl(titel, wert, unter, hervor): Kennzahl-Kachel, hervor = Akzentfläche (z. B. Verkaufspreis)
- chip(text, stufe): Status-Chip ok / warnung / fehler / info / neutral, immer mit Zeichen (✓ ! ✕ i)
- hinweisband(text, stufe, knopf): Hinweis über die volle Breite mit optionalem Knopf
- knopf(text, haupt, symbol): Knopf; haupt = Hauptknopf der Seite (höchstens einer je Seite)
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from . import design

STUFEN = tuple(design.CHIPS)


def _stufe(stufe):
    return stufe if stufe in design.CHIPS else "neutral"


def knopf(text, haupt=False, symbol=None, klick=None):
    """QPushButton im Stil des Designsystems; haupt=True setzt den Hauptknopf (Akzentfläche)."""
    k = QPushButton(text)
    if haupt:
        k.setObjectName("primaer")
    if symbol is not None:
        k.setIcon(symbol)
    if klick is not None:
        k.clicked.connect(klick)
    return k


def chip(text, stufe="neutral", zeichen=True):
    """Status-Chip. Das Zeichen der Stufe (✓ ! ✕ i) steht vor dem Text, damit der Status nie nur an der Farbe hängt.
    stufe unbekannt = neutral. Ergebnis: QLabel mit Objektname chip_<stufe>."""
    stufe = _stufe(stufe)
    z = design.CHIPS[stufe][2]
    label = QLabel(f"{z} {text}".strip() if zeichen and z and not str(text).startswith(z) else str(text))
    label.setObjectName("chip_" + stufe)
    label.setProperty("stufe", stufe)
    label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return label


def chip_setzen(label, text, stufe="neutral", zeichen=True):
    """Text und Stufe eines vorhandenen Chips ändern (Objektname wechselt, Stylesheet greift neu)."""
    neu = chip(text, stufe, zeichen)
    label.setText(neu.text())
    label.setObjectName(neu.objectName())
    label.setProperty("stufe", neu.property("stufe"))
    neu.deleteLater()
    label.style().unpolish(label)
    label.style().polish(label)
    return label


def seitenkopf(titel, untertitel="", aktionen=()):
    """Kopf einer Seite: Titel (groß) und Untertitel links, Aktionen rechts. Ergebnis: QFrame mit .titel, .untertitel
    und .aktionen (QHBoxLayout, weitere Knöpfe mit addWidget)."""
    rahmen = QFrame()
    rahmen.setObjectName("seitenkopf")
    zeile = QHBoxLayout(rahmen)
    zeile.setContentsMargins(0, 0, 0, design.ABSTAND_KLEIN)
    zeile.setSpacing(design.ABSTAND)
    links = QVBoxLayout()
    links.setSpacing(2)
    rahmen.titel = QLabel(titel)
    rahmen.titel.setObjectName("seitentitel")
    rahmen.untertitel = QLabel(untertitel)
    rahmen.untertitel.setObjectName("nebentext")
    if not untertitel:  # nur ausblenden (geister.py)
        rahmen.untertitel.hide()
    rahmen.untertitel.setWordWrap(True)
    links.addWidget(rahmen.titel)
    links.addWidget(rahmen.untertitel)
    zeile.addLayout(links, 1)
    rahmen.aktionen = QHBoxLayout()
    rahmen.aktionen.setSpacing(design.ABSTAND_KLEIN)
    for a in aktionen:
        rahmen.aktionen.addWidget(a)
    zeile.addLayout(rahmen.aktionen)
    return rahmen


def karte(titel="", rechts=()):
    """Karte mit optionaler Titelzeile (Titel links, Widgets rechts). Inhalt in karte.inhalt (QVBoxLayout)."""
    rahmen = QFrame()
    rahmen.setObjectName("karte")
    aussen = QVBoxLayout(rahmen)
    aussen.setContentsMargins(design.ABSTAND_GROSS, design.ABSTAND, design.ABSTAND_GROSS, design.ABSTAND)
    aussen.setSpacing(design.ABSTAND_KLEIN)
    rahmen.titel = None
    if titel or rechts:
        kopf = QHBoxLayout()
        rahmen.titel = QLabel(titel)
        rahmen.titel.setObjectName("abschnitt")
        kopf.addWidget(rahmen.titel)
        kopf.addStretch(1)
        for w in rechts:
            kopf.addWidget(w)
        aussen.addLayout(kopf)
    rahmen.inhalt = QVBoxLayout()
    rahmen.inhalt.setSpacing(design.ABSTAND_KLEIN)
    aussen.addLayout(rahmen.inhalt)
    return rahmen


def kennzahl(titel, wert="", unter="", hervor=False):
    """Kennzahl-Kachel: Titel (klein), Wert (groß), Zeile darunter. hervor=True: Akzentfläche für die wichtigste Zahl
    der Seite. Ergebnis: QFrame mit .titel, .wert, .unter (QLabel) und setzen(wert, unter)."""
    rahmen = QFrame()
    rahmen.setObjectName("kennzahl_hervor" if hervor else "kennzahl")
    v = QVBoxLayout(rahmen)
    v.setContentsMargins(design.ABSTAND, design.ABSTAND_KLEIN + 2, design.ABSTAND, design.ABSTAND_KLEIN + 2)
    v.setSpacing(2)
    rahmen.titel = QLabel(titel)
    rahmen.titel.setObjectName("kennzahltitel")
    rahmen.wert = QLabel(wert)
    rahmen.wert.setObjectName("kennzahl_gross")
    rahmen.unter = QLabel(unter)
    rahmen.unter.setObjectName("kennzahltitel")
    rahmen.unter.setWordWrap(True)
    rahmen.unter.setVisible(bool(unter))
    for w in (rahmen.titel, rahmen.wert, rahmen.unter):
        v.addWidget(w)

    def setzen(wert_, unter_=None):
        rahmen.wert.setText(wert_)
        if unter_ is not None:
            rahmen.unter.setText(unter_)
            rahmen.unter.setVisible(bool(unter_))
    rahmen.setzen = setzen
    return rahmen


def kennzahlleiste(eintraege, rechts=()):
    """Schmale Zeile mit Kennzahlen nebeneinander (Titel klein über dem Wert), z. B. im Kopf eines Fensters statt
    großer Kacheln (UI Next Level Phase 4). eintraege = [(Schlüssel, Titel, Wert)]; rechts = Widgets am rechten Rand
    (z. B. ein Chip). Ergebnis: QFrame mit .werte {Schlüssel: QLabel} und .titel {Schlüssel: QLabel}."""
    rahmen = QFrame()
    rahmen.setObjectName("kennzahlleiste")
    zeile = QHBoxLayout(rahmen)
    zeile.setContentsMargins(design.ABSTAND_GROSS, design.ABSTAND, design.ABSTAND_GROSS, design.ABSTAND)
    zeile.setSpacing(design.ABSTAND_GROSS + 8)
    rahmen.werte, rahmen.titel = {}, {}
    for key, titel, wert in eintraege:
        spalte = QVBoxLayout()
        spalte.setSpacing(0)
        t = QLabel(titel)
        t.setObjectName("kennzahltitel")
        w = QLabel(wert)
        w.setObjectName("kennzahlwert_leiste")
        spalte.addWidget(t)
        spalte.addWidget(w)
        zeile.addLayout(spalte)
        rahmen.werte[key], rahmen.titel[key] = w, t
    zeile.addStretch(1)
    for w in rechts:
        zeile.addWidget(w)
    return rahmen


def wertzeilen(zeilen):
    """Kleine Tabelle „Bezeichnung … Wert“ (Werte rechtsbündig), z. B. im Detailbereich. zeilen = [(Text, Wert)],
    Wert darf ein Widget sein. Ergebnis: QWidget mit .werte {Text: QLabel/Widget}."""
    from PySide6.QtWidgets import QGridLayout
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(design.ABSTAND)
    g.setVerticalSpacing(design.ABSTAND_KLEIN)
    g.setColumnStretch(0, 1)
    w.werte = {}
    for r, (text, wert) in enumerate(zeilen):
        t = QLabel(text)
        t.setObjectName("nebentext")
        g.addWidget(t, r, 0)
        ziel = wert if isinstance(wert, QWidget) else QLabel(str(wert))
        if isinstance(ziel, QLabel):
            ziel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        g.addWidget(ziel, r, 1, Qt.AlignRight)
        w.werte[text] = ziel
    return w


def hinweisband(text, stufe="warnung", knopf_text="", klick=None, schliessen=False):
    """Hinweis über die volle Breite (z. B. „Stammdaten sind Beispielwerte“) mit Zeichen, Text und optional einem
    Knopf rechts; schliessen=True ergänzt „Später“, das das Band ausblendet. Ergebnis: QFrame mit .text, .knopf."""
    stufe = _stufe(stufe)
    rahmen = QFrame()
    rahmen.setObjectName("hinweis_" + ("info" if stufe == "neutral" else stufe))
    zeile = QHBoxLayout(rahmen)
    zeile.setContentsMargins(design.ABSTAND + 2, design.ABSTAND_KLEIN, design.ABSTAND_KLEIN, design.ABSTAND_KLEIN)
    zeile.setSpacing(design.ABSTAND)
    zeichen = QLabel(f"<b>{design.CHIPS[stufe][2] or 'i'}</b>")
    rahmen.text = QLabel(text)
    rahmen.text.setWordWrap(True)
    rahmen.text.setTextFormat(Qt.RichText)
    zeile.addWidget(zeichen)
    zeile.addWidget(rahmen.text, 1)
    rahmen.knopf = None
    if knopf_text:
        rahmen.knopf = knopf(knopf_text, klick=klick)
        zeile.addWidget(rahmen.knopf)
    if schliessen:
        spaeter = QPushButton("Später")
        spaeter.setFlat(True)
        spaeter.clicked.connect(lambda: rahmen.setVisible(False))
        zeile.addWidget(spaeter)
    return rahmen


def knopfzeile(*knoepfe, rechts=True):
    """Zeile mit Knöpfen, rechtsbündig (Dialoge: Hauptknopf rechts außen). Ergebnis: QWidget."""
    w = QWidget()
    zeile = QHBoxLayout(w)
    zeile.setContentsMargins(0, 0, 0, 0)
    zeile.setSpacing(design.ABSTAND_KLEIN)
    if rechts:
        zeile.addStretch(1)
    for k in knoepfe:
        zeile.addWidget(k)
    return w
