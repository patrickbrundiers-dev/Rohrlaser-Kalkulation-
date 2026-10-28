"""Schrittanzeige im Angebot (Layout-Plan L10): ① Positionen erfasst → ② Optimiert → ③ Geprüft → ④ Verschickt.

Erledigte Schritte grün mit Haken, der aktuelle (erste offene) blau und fett, die übrigen grau (Nebentext-Grau, gut
lesbar; nur die Pfeile dazwischen sind hellgrau). Grundlage sind die
vorhandenen Stände: Positionen, Stand der Optimierung, offene Punkte im „Angebots-Check“, der Vorgang und der
CSV-Export (Vermerk im Versandverlauf).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

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


def erledigt(positionen, stand, offene_punkte, vorgang, csv=False):
    """Je Schritt erledigt ja/nein. stand: Ergebnis von stand_optimierung ('aktuell' = optimiert); „Verschickt“ erst,
    wenn auch der CSV-Export gemacht ist (csv, Patrick 24.10.2026)."""
    return (bool(positionen), stand == "aktuell", bool(positionen) and stand == "aktuell" and not offene_punkte,
            vorgang in VERSCHICKT and bool(csv))


def aktuell(fertig):
    """Index des ersten offenen Schritts (len(SCHRITTE) = alles erledigt)."""
    return next((i for i, f in enumerate(fertig) if not f), len(SCHRITTE))


class Schrittanzeige(QWidget):
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
            m = QLabel(f"{NUMMERN[i]} {text}")
            m.setAlignment(Qt.AlignVCenter)
            self.marken.append(m)
            lay.addWidget(m)
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
        self.setToolTip("Nächster Schritt: " + NAECHSTES[jetzt])
