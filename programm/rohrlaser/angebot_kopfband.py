"""Kopfband des Angebots (UI/UX Next Level Phase 3, Freigabe Patrick 26.11.2026, Variante A mit F4).

Über den Reitern des Angebots eine Zeile mit allem, was man beim Bearbeiten sehen will, ohne die Übersicht rechts:
links Angebotsnummer, Vorgang und Stand der Optimierung als Chips, darunter Kunde, Kundennummer, Maschine und
Gültigkeit; rechts Verkaufspreis groß, Marge als Chip (Ampel der Preisleiter: gut, knapp, kritisch) mit
Deckungsbeitrag, der Hauptknopf „Angebot (PDF)“ und ein Knopf „Übersicht“, der die bisherige Übersicht rechts
ein- und ausblendet (F4: sie entfällt als Vorgabe, bleibt aber erreichbar).

Das Band rechnet nichts selbst: es zeigt die Zahlen, die das Angebot für die Übersicht schon gerechnet hat
(Verkaufspreis aus dem Preisaufbau, Marge und Ampel aus preisleiter.bewertung, Deckungsbeitrag aus ertrag).
Die Optik kommt aus dem Designsystem (bausteine.py, stil.py), Farben stehen hier keine.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout

from . import bausteine, design

STAND_CHIP = {"aktuell": ("Optimiert", "ok"), "noch nicht optimiert": ("Nicht optimiert", "warnung")}
VORGANG_CHIP = {"Entwurf": "neutral", "Verschickt": "info", "Beauftragt": "ok", "Abgelehnt": "fehler",
                "Ersetzt": "neutral"}


def _z(wert, stellen=2):
    return f"{wert:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def stand_chip(stand):
    """(Text, Stufe) für den Stand der Optimierung; alles andere ist veraltet (rot)."""
    return STAND_CHIP.get(stand, ("Veraltet", "fehler"))


def marge_chip(bewertung):
    """(Text, Stufe) für die Marge aus preisleiter.bewertung; ohne Bewertung neutral."""
    if not bewertung or bewertung.get("marge") is None:
        return "Marge –", "neutral"
    from . import preisleiter as pl
    stufe = {pl.GUT: "ok", pl.KNAPP: "warnung", pl.KRITISCH: "fehler"}.get(bewertung.get("stufe"), "neutral")
    return f"Marge {_z(100 * bewertung['marge'], 1)} %", stufe


def unterzeile(kopf, gueltig=None):
    """Kunde · Kd.-Nr. · Maschine · gültig bis TT.MM.JJJJ (leere Teile fallen weg)."""
    teile = [kopf.get("kunde") or "Ohne Kunde"]
    if kopf.get("kundennr"):
        teile.append(f"Kd.-Nr. {kopf['kundennr']}")
    if kopf.get("maschine"):
        teile.append(f"Maschine {kopf['maschine']}")
    if gueltig is not None:
        teile.append(f"gültig bis {gueltig:%d.%m.%Y}")
    return " · ".join(teile)


class Kopfband(QFrame):
    """Band über den Reitern. aktionen: Widgets, die rechts außen stehen (Hauptknopf zuletzt)."""

    def __init__(self, aktionen=(), uebersicht_umschalten=None):
        super().__init__()
        self.setObjectName("kopfband")
        zeile = QHBoxLayout(self)
        zeile.setContentsMargins(design.ABSTAND_GROSS, design.ABSTAND_KLEIN, design.ABSTAND, design.ABSTAND_KLEIN)
        zeile.setSpacing(design.ABSTAND_GROSS)
        links = QVBoxLayout()
        links.setSpacing(2)
        oben = QHBoxLayout()
        oben.setSpacing(design.ABSTAND_KLEIN)
        self.nummer = QLabel()
        self.nummer.setObjectName("seitentitel")
        self.nummer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.vorgang = bausteine.chip("Entwurf", "neutral", zeichen=False)
        self.stand = bausteine.chip("Nicht optimiert", "warnung")
        for w in (self.nummer, self.vorgang, self.stand):
            oben.addWidget(w, 0, Qt.AlignVCenter)
        oben.addStretch(1)
        self.unter = QLabel()
        self.unter.setObjectName("nebentext")
        self.unter.setTextInteractionFlags(Qt.TextSelectableByMouse)
        links.addLayout(oben)
        links.addWidget(self.unter)
        zeile.addLayout(links, 1)

        preis = QVBoxLayout()
        preis.setSpacing(0)
        titel = QLabel("Verkaufspreis")
        titel.setObjectName("kennzahltitel")
        titel.setAlignment(Qt.AlignRight)
        self.vk = QLabel("–")
        self.vk.setObjectName("kennzahl_gross")
        self.vk.setAlignment(Qt.AlignRight)
        self.vk.setTextInteractionFlags(Qt.TextSelectableByMouse)
        preis.addWidget(titel)
        preis.addWidget(self.vk)
        zeile.addLayout(preis)
        marge = QVBoxLayout()
        marge.setSpacing(2)
        self.marge = bausteine.chip("Marge –", "neutral")
        self.db_text = QLabel()
        self.db_text.setObjectName("nebentext")
        self.db_text.setAlignment(Qt.AlignRight)
        marge.addWidget(self.marge, 0, Qt.AlignRight)
        marge.addWidget(self.db_text)
        zeile.addLayout(marge)
        self.aktionen = QHBoxLayout()
        self.aktionen.setSpacing(design.ABSTAND_KLEIN)
        self.uebersicht = None
        if uebersicht_umschalten is not None:
            self.uebersicht = QToolButton()
            self.uebersicht.setText("Übersicht")
            self.uebersicht.setCheckable(True)
            self.uebersicht.setToolTip("Übersicht rechts (Preisaufbau, Zeiten, Kennzahlen, Meldungen) ein- oder "
                                       "ausblenden; auch unter Ansicht")
            self.uebersicht.toggled.connect(uebersicht_umschalten)
            self.aktionen.addWidget(self.uebersicht)
        for w in aktionen:
            self.aktionen.addWidget(w)
        zeile.addLayout(self.aktionen)

    def setzen(self, kopf, vk=None, stand="noch nicht optimiert", bewertung=None, deckung=None, gueltig=None,
               vorgang="Entwurf"):
        """Werte zeigen. vk: Betrag oder Text („wird berechnet …“); deckung: Deckungsbeitrag in €."""
        self.nummer.setText(kopf.get("nummer") or "Neues Angebot")
        bausteine.chip_setzen(self.vorgang, vorgang, VORGANG_CHIP.get(vorgang, "neutral"), zeichen=False)
        bausteine.chip_setzen(self.stand, *stand_chip(stand))
        self.stand.setToolTip("" if stand in STAND_CHIP else str(stand))
        self.unter.setText(unterzeile(kopf, gueltig))
        if isinstance(vk, (int, float)):
            self.vk.setText(f"{_z(vk)} €")
        else:
            self.vk.setText(str(vk) if vk else "–")
        bausteine.chip_setzen(self.marge, *marge_chip(bewertung))
        self.marge.setToolTip((bewertung or {}).get("text") or "")
        self.db_text.setText(f"DB {_z(deckung)} €" if isinstance(deckung, (int, float)) else "")
        self.db_text.setVisible(isinstance(deckung, (int, float)))
        return self
