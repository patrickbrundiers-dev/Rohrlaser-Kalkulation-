"""Zentrale Stilwerte der Oberfläche: Farben und Stylesheet an einer Stelle (Prüfbericht 22.10.2026, C-10).

Neue Oberflächen nehmen die Farben von hier statt eigener Farbwerte; die PDF-Ausgaben (pdf.py) haben eigene Farben
für den Druck.
"""
AKZENT = "#1F4E78"          # Dunkelblau: aktiver Reiter, Titel, Hauptknöpfe
AKZENT_DUNKEL = "#183E60"
TEXT = "#1F2937"
TEXT_GRAU = "#5F6B7A"       # Nebentext, berechnete Werte, Hinweise
ROT = "#B42318"             # Fehler
ROT_FLAECHE = "#FDECEA"
GELB_TEXT = "#7A5A00"       # Warnung
GELB_FLAECHE = "#FFF4CE"
ORANGE = "#B35C00"          # Abweichung (von den Einstellungen, vom verschickten Angebot)
GRUEN = "#1E6B34"           # in Ordnung
GRUEN_FLAECHE = "#E3F4E8"
BLAU_FLAECHE = "#DDEBF7"
RAHMEN = "#D5DBE3"
LINIE = "#E3E7EC"
FLAECHE = "#F5F7FA"
# Abschnitte in Balken (kostenbalken.py) der Reihe nach: gut unterscheidbar, auch in Graustufen
BALKEN_FARBEN = ("#1F4E78", "#5B8DB8", "#B35C00", "#7F8A99", "#1E6B34", "#B07AA1")
ROTER_RAHMEN = f"border: 1px solid {ROT}; border-radius: 3px; background: {ROT_FLAECHE};"

# Einheitliches Aussehen angelehnt an die PDF-Ausgaben: Dunkelblau #1F4E78 als Akzent (aktiver Reiter, Titel,
# Hauptknöpfe, Linie unter Tabellenköpfen), helle neutrale Flächen, Karten mit dünnem Rahmen, Zebra-Zeilen
STIL = """
QFrame#karte { background: #FFFFFF; border: 1px solid #D5DBE3; border-radius: 6px; }
QLabel#kartentitel { font-weight: bold; color: #1F4E78; }
QLabel#gruppentitel { font-weight: bold; color: #3A4656; padding-bottom: 2px; border-bottom: 1px solid #E3E7EC; }
QFrame#kennzahl { background: #F5F7FA; border: 1px solid #E3E7EC; border-radius: 4px; }
QLabel#kennzahltitel { color: #5F6B7A; }
QLabel#kennzahlwert { font-weight: bold; color: #1F2937; }
QLabel#summenzeile { background: #F5F7FA; border: 1px solid #E3E7EC; border-radius: 4px; padding: 6px; }
QFrame#preis { background: #EEF4FB; border: 1px solid #C9DAEE; border-radius: 4px; }
QLabel#preiswert { font-weight: bold; font-size: 17pt; color: #1F4E78; }
QLabel#preiswert_klein { font-weight: bold; font-size: 11pt; color: #3A4656; }
QLabel#stand_ok { background: #E3F4E8; color: #1E6B34; border: 1px solid #B7DFC3; border-radius: 4px; font-weight: bold; }
QLabel#stand_offen { background: #FFF6DB; color: #7A5A00; border: 1px solid #F0D98C; border-radius: 4px; font-weight: bold; }
QLabel#stand_veraltet { background: #FDECEA; color: #8C1D18; border: 1px solid #F3B8B2; border-radius: 4px; font-weight: bold; }
QToolButton#kartenknopf { border: none; font-weight: bold; color: #1F4E78; padding: 2px 0; }
QToolButton#aufklapper { border: none; text-align: left; color: #3A4656; padding: 2px 0; }
QToolButton#meldung_ok { border: none; color: #1E6B34; font-weight: bold; padding: 2px 0; }
QToolButton#meldung_warnung { border: none; color: #7A5A00; font-weight: bold; padding: 2px 0; }
QToolButton#meldung_fehler { border: none; color: #B42318; font-weight: bold; padding: 2px 0; }
QPushButton { padding: 4px 10px; border: 1px solid #C5CCD6; border-radius: 4px; background: #FFFFFF; }
QPushButton:hover { background: #F1F4F8; }
QPushButton:pressed { background: #E2E8F0; }
QPushButton:disabled { color: #9AA3AF; }
QPushButton#primaer { background: #1F4E78; color: #FFFFFF; border-color: #183E60; font-weight: bold; }
QPushButton#primaer:hover { background: #183E60; }
QPushButton::menu-indicator { subcontrol-position: right center; right: 4px; }
QPushButton[menu="true"] { padding-right: 18px; }
QTabWidget::pane { border: 1px solid #D5DBE3; top: -1px; }
QTabBar::tab { background: #EEF1F5; color: #3A4656; border: 1px solid #D5DBE3; border-bottom: none;
               border-top-left-radius: 4px; border-top-right-radius: 4px; padding: 4px 10px; margin-right: 1px; }
QTabBar::tab:selected { background: #FFFFFF; color: #1F4E78; border-top: 3px solid #1F4E78; padding-top: 2px; }
QTabBar::tab:hover:!selected { background: #F7F9FB; }
QGroupBox { background: #FFFFFF; border: 1px solid #D5DBE3; border-radius: 6px; margin-top: 16px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 8px; padding: 0 4px;
                   color: #1F4E78; font-weight: bold; }
QTreeView::item { min-height: 20px; }
QTableView, QTreeView { gridline-color: #E3E7EC; selection-background-color: #CFE0F5; selection-color: #111827;
                        alternate-background-color: #F5F8FB; }
QHeaderView::section { background: #F3F6FA; color: #1F2937; border: none; border-right: 1px solid #DDE2E8;
                       border-bottom: 2px solid #1F4E78; padding: 3px; font-weight: bold; }
QHeaderView::section:vertical { border-bottom: 1px solid #E3E7EC; border-right: 1px solid #C9D0D8; font-weight: normal; }
"""


def ziffern_tabellarisch(app):
    """Gleich breite Ziffern (OpenType 'tnum') in der ganzen Oberfläche: Beträge in Tabellenspalten stehen ruhig
    untereinander. Schriften ohne diese Eigenschaft bleiben unverändert."""
    from PySide6.QtGui import QFont
    schrift = app.font()
    schrift.setFeature(QFont.Tag("tnum"), 1)
    app.setFont(schrift)


# Statussymbole (Layout-Plan L4): Status nie nur über die Farbe – ✓ OK, ! Warnung, ✕ Fehler, i Hinweis
_SYMBOLE = {}
STATUS_SYMBOL_FARBE = {"OK": GRUEN, "HINWEIS": AKZENT, "WARNUNG": "#B7791F", "VERALTET": "#B7791F", "FEHLER": ROT}


def status_stufe(text):
    """Stufe eines Statustexts ('FEHLER: …', 'WARNUNG …', 'OK' …); unbekannt: None."""
    t = str(text or "").strip().upper()
    for stufe in ("FEHLER", "VERALTET", "WARNUNG", "HINWEIS", "OK"):
        if t.startswith(stufe):
            return stufe
    return None


def status_symbol(text, groesse=14):
    """QIcon für einen Statustext (gezeichnet, ohne Bilddatei); None für unbekannte Texte."""
    stufe = status_stufe(text)
    if stufe is None:
        return None
    if (stufe, groesse) in _SYMBOLE:
        return _SYMBOLE[stufe, groesse]
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
    bild = QPixmap(groesse * 2, groesse * 2)          # doppelte Auflösung, scharf auch bei 200 %
    bild.fill(Qt.transparent)
    bild.setDevicePixelRatio(2)
    p = QPainter(bild)
    p.setRenderHint(QPainter.Antialiasing)
    farbe, g = QColor(STATUS_SYMBOL_FARBE[stufe]), float(groesse)
    p.setPen(Qt.NoPen)
    p.setBrush(farbe)
    if stufe in ("WARNUNG", "VERALTET"):
        pfad = QPainterPath(QPointF(g / 2, 1))
        pfad.lineTo(g - 1, g - 1.5)
        pfad.lineTo(1, g - 1.5)
        pfad.closeSubpath()
        p.drawPath(pfad)
    else:
        p.drawEllipse(QRectF(1, 1, g - 2, g - 2))
    stift = QPen(QColor("#FFFFFF"), max(1.6, g / 8), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(stift)
    if stufe == "OK":
        p.drawPolyline([QPointF(g * .28, g * .52), QPointF(g * .44, g * .68), QPointF(g * .73, g * .35)])
    elif stufe == "FEHLER":
        p.drawLine(QPointF(g * .33, g * .33), QPointF(g * .67, g * .67))
        p.drawLine(QPointF(g * .67, g * .33), QPointF(g * .33, g * .67))
    elif stufe == "HINWEIS":
        p.drawLine(QPointF(g / 2, g * .45), QPointF(g / 2, g * .72))
        p.drawPoint(QPointF(g / 2, g * .28))
    else:
        p.drawLine(QPointF(g / 2, g * .38), QPointF(g / 2, g * .62))
        p.drawPoint(QPointF(g / 2, g * .78))
    p.end()
    _SYMBOLE[stufe, groesse] = QIcon(bild)
    return _SYMBOLE[stufe, groesse]
