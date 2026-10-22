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
QLabel#preiswert { font-weight: bold; font-size: 13pt; color: #1F4E78; }
QLabel#preiswert_klein { font-weight: bold; font-size: 11pt; color: #1F2937; }
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
