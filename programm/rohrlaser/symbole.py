"""Symbole für Hauptaktionen (Layout-Plan L19): schlichte Linien-Symbole (SVG, 24 × 24, eine Strichstärke), der Text
bleibt am Knopf. Die Farbe folgt dem Theme (stil.umsetzen); auf Hauptknöpfen (objectName "primaer") weiß.

versehen(widget) gibt allen Knöpfen und Menüpunkten darin, deren Text in KNOPF_SYMBOL steht, ihr Symbol; so
braucht keine Seite eigene Aufrufe. Ohne QtSvg (z. B. beschnittene Installation) bleiben die Knöpfe ohne Symbol.
"""
from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractButton, QMenu

from . import stil

GROESSE = 16
WEISS = "#FFFFFF"

# Pfade im Raster 24 × 24, gezeichnet mit stroke-width 2, runden Enden, ohne Füllung
PFADE = {
    "neu": "<path d='M12 5v14M5 12h14'/>",
    "oeffnen": "<path d='M4 20h16M4 4h9l7 7v9'/><path d='M13 4v7h7'/>",
    "kopieren": "<rect x='8' y='8' width='12' height='12' rx='2'/><path d='M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10"
                "a1 1 0 0 0 1 1h3'/>",
    "loeschen": "<path d='M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3'/>",
    "ordner": "<path d='M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'/>",
    "step": "<path d='M12 3l8 4.5v9L12 21l-8-4.5v-9z'/><path d='M12 12l8-4.5M12 12L4 7.5M12 12v9'/>",
    "optimieren": "<path d='M13 3L4 14h7l-1 7 9-11h-7z'/>",
    "zusatz": "<path d='M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z'/>",
    "zukauf": "<circle cx='9' cy='20' r='1.5'/><circle cx='18' cy='20' r='1.5'/><path d='M2 3h3l2.7 12h11l2-8H6.3'/>",
    "material": "<path d='M12 3l9 5-9 5-9-5z'/><path d='M3 13l9 5 9-5'/>",
    "ansicht3d": "<path d='M12 3l8 4.5v9L12 21l-8-4.5v-9z'/><path d='M12 12l8-4.5M12 12v9'/><path d='M8 5.2l8 4.6'/>",
    "pdf": "<path d='M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z'/><path d='M14 3v6h6M8 13h8M8 17h5'/>",
    "ausgaben": "<path d='M6 9V3h12v6'/><rect x='3' y='9' width='18' height='8' rx='2'/><path d='M7 14h10v7H7z'/>",
    "liste": "<path d='M9 6h11M9 12h11M9 18h11'/><circle cx='4.5' cy='6' r='1'/><circle cx='4.5' cy='12' r='1'/>"
             "<circle cx='4.5' cy='18' r='1'/>",
    "sichern": "<path d='M5 3h11l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 1-2z'/><path d='M8 3v5h7V3M8 21v-7h8v7'/>",
    "wiederherstellen": "<path d='M3 12a9 9 0 1 0 3-6.7L3 8'/><path d='M3 3v5h5'/>",
    "einstellungen": "<circle cx='12' cy='12' r='3'/><path d='M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3"
                     "M4.9 19.1L7 17M17 7l2.1-2.1'/>",
    "staffel": "<path d='M4 20V10M10 20V4M16 20v-7M22 20H2'/>",
    "abgleich": "<path d='M4 9a8 8 0 0 1 14-3l2 2M20 15a8 8 0 0 1-14 3l-2-2'/><path d='M20 3v5h-5M4 21v-5h5'/>",
    "mail": "<rect x='3' y='5' width='18' height='14' rx='2'/><path d='M3 7l9 6 9-6'/>",
    "suche": "<circle cx='11' cy='11' r='7'/><path d='M21 21l-5-5'/>",
}

# Knopf- bzw. Menütext → Symbol (Text ohne „&“). Nur Hauptaktionen: Zusatzarbeiten, Zukaufteile und Material
# bleiben ohne, sonst passt die Knopfleiste des Angebots nicht mehr in 1366 px (test_ansicht)
KNOPF_SYMBOL = {
    "Neues Angebot": "neu", "Neue Position": "neu", "Öffnen": "oeffnen", "Kopieren": "kopieren", "Löschen": "loeschen",
    "Ablage öffnen": "ordner", "Ordner öffnen": "ordner", "Abgleichen": "abgleich", "STEP importieren …": "step", "Optimieren": "optimieren",
    "3D-Ansicht …": "ansicht3d",
    "Angebot (PDF)": "pdf", "Ausgaben": "ausgaben", "Werkstattpapiere (PDF)": "pdf", "Kalkulation (PDF)": "pdf",
    "Auftragsbestätigung (PDF)": "pdf", "Etiketten mit QR-Code (PDF) …": "pdf",
    "Materialanfrage (E-Mail)": "mail", "Alle Angebote": "liste", "Datensicherung erstellen": "sichern",
    "Sicherung wiederherstellen …": "wiederherstellen", "Datenordner öffnen": "ordner",
    "Einstellungen öffnen": "einstellungen", "Staffelpreise rechnen": "staffel", "Neue Stufe …": "neu",
    "Suchen und ausführen …": "suche",
}

_cache = {}


def svg(name, farbe):
    return ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
            f"stroke='{farbe}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{PFADE[name]}</svg>")


def symbol(name, farbe=None):
    """QIcon des Symbols name; farbe = Hell-Farbe (wird ins Theme umgesetzt), Vorgabe Textfarbe. Leer ohne QtSvg."""
    farbe = farbe or stil.umsetzen(stil.TEXT)
    schl = (name, farbe)
    if schl not in _cache:
        try:
            from PySide6.QtSvg import QSvgRenderer
        except ImportError:
            return QIcon()
        icon = QIcon()
        renderer = QSvgRenderer(QByteArray(svg(name, farbe).encode()))
        for faktor in (1, 2):                               # scharf auch bei 150/200 % Windows-Skalierung
            bild = QPixmap(GROESSE * faktor, GROESSE * faktor)
            bild.fill(Qt.transparent)
            p = QPainter(bild)
            renderer.render(p, QRectF(0, 0, bild.width(), bild.height()))
            p.end()
            bild.setDevicePixelRatio(faktor)
            icon.addPixmap(bild)
        _cache[schl] = icon
    return _cache[schl]


def versehen(widget):
    """Allen Knöpfen und Menüpunkten unter widget mit bekanntem Text ihr Symbol geben (bestehende bleiben)."""
    for b in widget.findChildren(QAbstractButton):
        name = KNOPF_SYMBOL.get(b.text().replace("&", ""))
        if name and b.icon().isNull():
            b.setIcon(symbol(name, WEISS if b.objectName() == "primaer" else None))
            b.setIconSize(QSize(GROESSE, GROESSE))
    for m in widget.findChildren(QMenu):
        for a in m.actions():
            name = KNOPF_SYMBOL.get(a.text().replace("&", ""))
            if name and a.icon().isNull():
                a.setIcon(symbol(name))
