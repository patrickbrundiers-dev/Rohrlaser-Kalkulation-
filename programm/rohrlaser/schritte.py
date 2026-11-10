"""Schrittanzeige im Angebot (Layout-Plan L10): ① Positionen erfasst → ② Optimiert → ③ Geprüft → ④ Verschickt.

Erledigte Schritte grün mit Haken, der aktuelle (erste offene) blau und fett, die übrigen grau (Nebentext-Grau, gut
lesbar; nur die Pfeile dazwischen sind hellgrau). Grundlage sind die
vorhandenen Stände: Positionen, Stand der Optimierung, offene Punkte im „Angebots-Check“, der Vorgang und der
CSV-Export (Vermerk im Versandverlauf).

Seit Verbesserungsplan 06.11.2026 (B2) ist jeder Schritt anklickbar (Signal gewaehlt(Index): das Angebot führt den
Schritt aus, z. B. Optimieren), und der Knopf „Weiter: …“ führt den nächsten offenen Schritt aus.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from . import stil

SCHRITTE = ("Positionen erfasst", "Optimiert", "Geprüft", "Verschickt")
NUMMERN = "①②③④"
# was im jeweils aktuellen Schritt zu tun ist (Tooltip)
NAECHSTES = ("Positionen anlegen: Neue Position oder STEP importieren.",
             "Optimieren (F9) – plant die Stangen und rechnet die Preise.",
             "Offene Punkte im „Angebots-Check“ in der Übersicht erledigen.",
             "Angebot (PDF) erstellen und verschicken (der Vorgang wird dabei Verschickt) und CSV-Export "
             "(Ausgaben → CSV-Export); erst mit beidem wird „Verschickt“ grün.",
             "Alle Schritte erledigt.")
VERSCHICKT = ("Verschickt", "Beauftragt", "Abgelehnt")
# Knopf „Weiter: …“ je aktuellem Schritt (B2)
WEITER = ("Neue Position", "Optimieren", "Angebots-Check", "Angebot (PDF)")


def erledigt(positionen, stand, offene_punkte, vorgang, csv=False):
    """Je Schritt erledigt ja/nein. stand: Ergebnis von stand_optimierung ('aktuell' = optimiert); „Verschickt“ erst,
    wenn auch der CSV-Export gemacht ist (csv, Patrick 24.10.2026)."""
    return (bool(positionen), stand == "aktuell", bool(positionen) and stand == "aktuell" and not offene_punkte,
            vorgang in VERSCHICKT and bool(csv))


def aktuell(fertig):
    """Index des ersten offenen Schritts (len(SCHRITTE) = alles erledigt)."""
    return next((i for i, f in enumerate(fertig) if not f), len(SCHRITTE))


class _Marke(QLabel):
    geklickt = Signal()

    def mousePressEvent(self, ereignis):
        if ereignis.button() == Qt.LeftButton:
            self.geklickt.emit()
        super().mousePressEvent(ereignis)


class Schrittanzeige(QWidget):
    gewaehlt = Signal(int)          # Schritt angeklickt bzw. „Weiter: …“ (Index in SCHRITTE)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 4, 0)
        lay.setSpacing(4)
        self.marken = []
        for i, text in enumerate(SCHRITTE):
            if i:
                pfeil = QLabel("→")
                pfeil.setStyleSheet("color: #9AA3AF;")
                lay.addWidget(pfeil)
            m = _Marke(f"{NUMMERN[i]} {text}")
            m.setAlignment(Qt.AlignVCenter)
            m.setCursor(Qt.PointingHandCursor)
            m.geklickt.connect(lambda i=i: self.gewaehlt.emit(i))
            self.marken.append(m)
            lay.addWidget(m)
        self.weiter = QToolButton()
        self.weiter.setObjectName("weiter")
        self.weiter.setCursor(Qt.PointingHandCursor)
        self.weiter.setStyleSheet(f"QToolButton#weiter {{ color: white; background: {stil.AKZENT}; border: none; "
                                  "border-radius: 3px; padding: 1px 8px; font-weight: bold; }")
        self.weiter.clicked.connect(lambda: self.gewaehlt.emit(aktuell(self.fertig)))
        lay.addSpacing(6)
        lay.addWidget(self.weiter)
        self.fertig = (False,) * len(SCHRITTE)
        self.setzen(self.fertig)

    def setzen(self, fertig):
        self.fertig = tuple(fertig)
        jetzt = aktuell(self.fertig)
        for i, (m, f) in enumerate(zip(self.marken, self.fertig)):
            if i == jetzt:
                farbe, fett, zeichen = stil.AKZENT, "bold", NUMMERN[i]
            elif f:
                farbe, fett, zeichen = stil.GRUEN, "normal", "✓"
            else:       # offene Schritte grau, aber lesbar (TEXT_GRAU 5,4 : 1 statt #9AA3AF 2,6 : 1, Design-Prüfung)
                farbe, fett, zeichen = stil.TEXT_GRAU, "normal", NUMMERN[i]
            m.setText(f"{zeichen} {SCHRITTE[i]}")
            m.setStyleSheet(f"color: {farbe}; font-weight: {fett};")
            m.setToolTip(f"Klick: {WEITER[i]}" + (" (nächster Schritt)" if i == jetzt else ""))
        self.setToolTip("Nächster Schritt: " + NAECHSTES[jetzt])
        self.weiter.setVisible(jetzt < len(WEITER))
        if jetzt < len(WEITER):
            self.weiter.setText(f"Weiter: {WEITER[jetzt]} ▸")
            self.weiter.setToolTip(NAECHSTES[jetzt])
