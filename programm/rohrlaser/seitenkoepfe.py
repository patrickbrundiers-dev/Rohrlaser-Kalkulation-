"""Einheitlicher Seitenkopf der Bereiche (UI/UX Next Level Phase 5, Variante A „Klar“, Freigabe Patrick 26.11.2026).

Start und Einstellungen haben seit Phase 2 und 4 einen Seitenkopf mit Titel und kurzer Erklärung. Hier bekommen die
übrigen Bereiche denselben Kopf, aber einzeilig (Titel groß, Erklärung daneben), damit Tabellen kaum Höhe verlieren.
Der Kopf wird oben in das vorhandene Layout der Seite gesetzt: dieselben Seitenobjekte, dieselben Knöpfe, nichts an
den Funktionen ändert sich. Bereiche mit eigenem Kopf (Start, Kunden, Einstellungen, Austausch, Auswertung) bleiben, wie sie sind.
"""
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from . import design

# Attribut am Hauptfenster: Erklärung (Titel = Text des Reiters, damit Umbenennungen nur an einer Stelle stehen)
KOEPFE = (
    ("anfragen_seite", "Eingegangene Anfragen aus Outlook: zuordnen, prüfen und zum Angebot machen."),
    ("materialanfragen", "Anfragen an Lieferanten mit Stand und Antworten."),
    ("angebote", "Alle Angebote mit Vorgang, Stand und Verkaufspreis. Doppelklick öffnet."),
    ("auftraege", "Beauftragte Angebote von der Arbeitsvorbereitung bis zur Auslieferung."),
    ("rahmen", "Rahmenaufträge mit Abrufen, Restmengen und Laufzeit."),
    ("produktion", "Arbeitsgänge der Werkstatt: beginnen, unterbrechen, fertig melden."),
    ("versand", "Palettenscheine, Ladelisten und Lieferdaten der beauftragten Angebote."),
    ("fertigung", "Freigabe und Stand der beauftragten Angebote für die Werkstatt."),
    ("lager", "Materialbestand und Reststücke."),
    ("fracht", "Frachtkosten einer Sendung rechnen und vergleichen."),
    ("zukauf", "Zukaufartikel mit Kategorien, Lieferanten und Aufschlägen."),
    ("material", "Werkstoffe, Abmessungen, Einkaufspreise und Lieferanten."),
)


def kopf(titel, erklaerung=""):
    """Einzeiliger Seitenkopf: Titel (objectName seitentitel) und Erklärung (nebentext) auf einer Linie."""
    rahmen = QFrame()
    rahmen.setObjectName("seitenkopf")
    zeile = QHBoxLayout(rahmen)
    zeile.setContentsMargins(0, 0, 0, design.ABSTAND_KLEIN)
    zeile.setSpacing(design.ABSTAND_GROSS)
    rahmen.titel = QLabel(titel)
    rahmen.titel.setObjectName("seitentitel")
    from .angebot_oben import KurzZeile       # endet mit „…“, wenn der Platz fehlt; Tooltip zeigt den ganzen Satz
    rahmen.untertitel = KurzZeile()
    rahmen.untertitel.setObjectName("nebentext")
    rahmen.untertitel.setText(erklaerung)
    rahmen.untertitel.setToolTip(erklaerung)
    rahmen.untertitel.setVisible(bool(erklaerung))
    zeile.addWidget(rahmen.titel)
    zeile.addWidget(rahmen.untertitel, 1)
    return rahmen


def anwenden(f):
    """Köpfe einsetzen; liefert {Attribut: Kopf}. Mehrfacher Aufruf setzt nichts doppelt."""
    gesetzt = {}
    for attr, erklaerung in KOEPFE:
        w = getattr(f, attr, None)
        lay = w.layout() if w is not None else None
        if not isinstance(lay, QVBoxLayout):
            continue
        if getattr(w, "seitenkopf", None) is None:
            i = f.reiter.indexOf(w)
            titel = f.reiter.tabText(i).replace("&&", "&") if i >= 0 else getattr(w, "titel", "")
            w.seitenkopf = kopf(titel if isinstance(titel, str) else "", erklaerung)
            lay.insertWidget(0, w.seitenkopf)
        gesetzt[attr] = w.seitenkopf
    return gesetzt
