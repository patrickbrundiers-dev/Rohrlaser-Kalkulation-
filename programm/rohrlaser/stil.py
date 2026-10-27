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
# Farben der Positionen im Stangenbild, in der Stangen-Übersicht und in der Abwicklung der Stange (je Position gleich)
TEIL_FARBEN = ("#4E79A7", "#F28E2B", "#59A14F", "#B07AA1", "#76B7B2", "#EDC948", "#FF9DA7", "#9C755F", "#E15759",
               "#BAB0AC")
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


# ------------------------------------------------------------------ Themes (Plan B1/B2, Layout-Plan D2)
# Die Farben oben sind das Theme „Hell“ und zugleich die Schlüssel: jedes andere Theme setzt eine Hell-Farbe auf seine
# eigene um (UMSETZUNG). So gilt dieselbe Tabelle für das Stylesheet, für Farben im Programmtext (farbe, farbe_fest)
# und für Farben in Texten von Beschriftungen. „Hell“ bleibt dadurch Zeichen für Zeichen wie bisher.
THEMES = ("Hell", "Dunkel", "Hoher Kontrast", "Wie Windows")
DICHTEN = ("kompakt", "normal", "komfortabel")

UMSETZUNG = {
    "Dunkel": {
        "#FFFFFF": "#1E2530", "#F5F7FA": "#161B22", "#EEF1F5": "#232A35", "#F7F9FB": "#2A3240", "#F1F4F8": "#2A3240",
        "#E2E8F0": "#334052", "#F3F6FA": "#232A35", "#F5F8FB": "#222935", "#D5DBE3": "#3A4555", "#E3E7EC": "#2E3744",
        "#DDE2E8": "#364050", "#C5CCD6": "#485568", "#C9D0D8": "#445064", "#1F4E78": "#6CA6DE", "#183E60": "#8BBBE8",
        "#1F2937": "#E6EAF0", "#111827": "#F3F4F6", "#CFE0F5": "#2D4A6B", "#3A4656": "#C3CBD6", "#5F6B7A": "#9AA6B5",
        "#9AA3AF": "#6B7685", "#EEF4FB": "#1F2F44", "#C9DAEE": "#34506F", "#E3F4E8": "#173523", "#1E6B34": "#7FD39A",
        "#B7DFC3": "#2F6B43", "#FFF6DB": "#3A3016", "#7A5A00": "#F0C75E", "#F0D98C": "#6B5A22", "#FDECEA": "#3D1D1B",
        "#8C1D18": "#F4A29B", "#F3B8B2": "#7A3530", "#B42318": "#F28B82", "#FFF4CE": "#3A3016", "#B35C00": "#F5A55B",
        "#DDEBF7": "#1F3247", "#000000": "#F3F4F6", "#FFFCF0": "#243041", "#EDEDED": "#1A1F27",
        "#F8CBAD": "#4A2620", "#FFD966": "#4D4016", "#FFF2CC": "#3D3418", "#595959": "#B8C0CC", "#404040": "#CDD3DC",
        "#202020": "#E6EAF0", "#333333": "#D5DAE1", "#6B4A00": "#F0C75E", "#B7791F": "#E9B44C", "#2E7D32": "#81C784",
        "#C00000": "#F28B82", "#FFF4D6": "#3A3016", "#E8F5E9": "#173523", "#B26A00": "#F5A55B", "#7F7F7F": "#9AA6B5",
        "#FCE4D6": "#4A2B1E", "#E2EFDA": "#1E3320", "#FFEB9C": "#4D4016",
        "#BDD7EE": "#2D4A6B", "#FFF4CC": "#3D3418", "#E8EEF5": "#2A3240", "#ECEEF1": "#2A3038", "#6B7280": "#9AA3AF",
        "#E2F0D9": "#1E3320",
        # Dunkelmodus verbessert (24.10.2026): Eingabezellen blaugrau statt olivbraun, berechnete Zellen dunkler
        # (Unterschied bleibt sichtbar), dazu Flächen und Linien von Skizzen, 3D-Ansicht und STEP-Ablagefeld
        "#FFF9E0": "#243041", "#FFF9E5": "#243041", "#F2F2F2": "#1A1F27", "#F4F7FB": "#1F2732", "#DCE9F8": "#1F3550",
        "#8FA6C1": "#5A7090", "#1F5FAD": "#8BBBE8", "#3D5573": "#A9BBD0", "#F1F3F6": "#232A35", "#EAF1F8": "#2A3646",
        "#E9EEF4": "#2A3240", "#DCE6F2": "#2D3A4C", "#DCE3EA": "#2A3340", "#F8D7DA": "#4A2422", "#C6EFCE": "#1E4A2C",
        "#FFC7CE": "#4F2328", "#D0D7E2": "#3A4555", "#BFBFBF": "#4A5566", "#E8C66B": "#7A6326", "#7A5B00": "#F0C75E",
        "#68727E": "#A3ADBA", "#B54708": "#F5A55B", "#2E6B30": "#81C784", "#1E7B34": "#7FD39A", "#1E6B35": "#7FD39A",
        "#1F4E79": "#6CA6DE", "#1F3864": "#8FB3E8", "#5A6470": "#A3ADBA", "#C0392B": "#F28B82", "#7F6000": "#E0C060",
        "#A0A0A0": "#7A8494", "#999999": "#7A8494", "#C62828": "#F28B82", "#1565C0": "#64A8F0", "#00838F": "#4DD0E1",
        "#E8F0FA": "#22324A",
        # Sätze in Positionsliste und Kalkulation (satzgruppen.py, 27.10.2026): Tönung Blau/Violett und Satzname
        "#E4EEFA": "#1E3550", "#EEE6F7": "#35284A", "#285F9E": "#8BBBE8", "#6E3FA3": "#C7A6F0",
    },
    "Hoher Kontrast": {
        "#1F2937": "#000000", "#111827": "#000000", "#3A4656": "#111111", "#5F6B7A": "#2F3742", "#9AA3AF": "#5F6B7A",
        "#D5DBE3": "#5F6B7A", "#E3E7EC": "#8A94A1", "#DDE2E8": "#6B7685", "#C5CCD6": "#3A4656", "#C9D0D8": "#3A4656",
        "#1F4E78": "#123456", "#183E60": "#0B2440", "#7A5A00": "#4D3800", "#1E6B34": "#0F4A22", "#B42318": "#8C1414",
        "#8C1D18": "#6E0F0B", "#B35C00": "#7A3E00", "#F5F8FB": "#EAF0F7", "#CFE0F5": "#9EC1EA", "#595959": "#222222",
        "#404040": "#111111", "#7F7F7F": "#3A3A3A", "#B7791F": "#7A4E00", "#6B4A00": "#4D3800", "#6B7280": "#3A4656",
    },
}
ZUSATZ = {      # nur in diesen Themes: deutlicher Tastaturfokus (B9)
    # Hell- und Dunkelmodus optisch verbessert (26.10.2026): Fusion zeichnet Rahmen von Eingabefeldern und Häkchen-
    # kästchen aus der Fensterfarbe (dunkler) – auf dunklem Grund fast unsichtbar; Hauptknopf weiße Schrift auf
    # Hellblau war kaum lesbar (2,6 : 1), jetzt kräftiges Blau (5,5 : 1)
    "Dunkel": "QLineEdit, QComboBox, QAbstractSpinBox, QPlainTextEdit, QTextEdit { border: 1px solid #56657A; "
              "border-radius: 3px; "
              "padding: 1px 3px; }\n"
              "QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled { border-color: #343E4C; }\n"
              "QComboBox::drop-down, QDateTimeEdit::drop-down { border: none; width: 18px; }\n"
              "QComboBox::down-arrow, QDateTimeEdit::down-arrow { image: url({PFEIL}); width: 9px; height: 9px; }\n"
              "QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { border: none; width: 14px; }\n"
              "QAbstractSpinBox::up-arrow { image: url({PFEIL_AUF}); width: 7px; height: 7px; }\n"
              "QAbstractSpinBox::down-arrow { image: url({PFEIL}); width: 7px; height: 7px; }\n"
              "QCheckBox::indicator, QAbstractItemView::indicator, QGroupBox::indicator { width: 13px; height: 13px; "
              "border: 1px solid #7A889B; border-radius: 3px; background: #1A2029; }\n"
              "QCheckBox::indicator:checked, QAbstractItemView::indicator:checked, QGroupBox::indicator:checked "
              "{ background: #6CA6DE; border-color: #6CA6DE; image: url({HAKEN}); }\n"
              "QCheckBox::indicator:disabled, QAbstractItemView::indicator:disabled { border-color: #3A4555; }\n"
              "QRadioButton::indicator { width: 13px; height: 13px; border: 1px solid #7A889B; border-radius: 7px; "
              "background: #1A2029; }\n"
              "QRadioButton::indicator:checked { background: #1A2029; border-color: #6CA6DE; image: url({PUNKT}); }\n"
              "QPushButton#primaer { background: #2F6CA8; color: #FFFFFF; border-color: #5B93CB; }\n"
              "QPushButton#primaer:hover { background: #3A7BBD; }\n"
              "QPushButton#primaer:disabled { background: #2A3646; color: #7A8494; border-color: #3A4555; }\n"
              "QToolTip { color: #E6EAF0; background: #2A3240; border: 1px solid #56657A; }\n"
              "QMenu { border: 1px solid #3A4555; }\n"
              "QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus "
              "{ border: 2px solid #8BBBE8; border-radius: 3px; }\nQPushButton:focus { border: 2px solid #8BBBE8; }\n",
    "Hoher Kontrast": "QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus "
                      "{ border: 2px solid #000000; border-radius: 3px; }\nQPushButton:focus { border: 2px solid #000000; }"
                      "\nQPushButton { border: 1px solid #3A4656; }\n",
}
DICHTE_CSS = {
    "kompakt": "QPushButton { padding: 2px 8px; }\nQTabBar::tab { padding: 2px 8px; }\nQTreeView::item { min-height: 18px; }\n"
               "QHeaderView::section { padding: 1px; }\n",
    "normal": "",
    "komfortabel": "QPushButton { padding: 7px 14px; }\nQTabBar::tab { padding: 7px 14px; }\n"
                   "QTreeView::item { min-height: 26px; }\nQHeaderView::section { padding: 6px; }\n",
}
_HEX = None
_thema = "Hell"                 # wirksames Theme (nach „Wie Windows“ aufgelöst), gesetzt von anwenden()
_FEST = []                      # [(QColor, Hell-Farbe)]: Farbkonstanten, die anwenden() umfärbt


def thema():
    return _thema


def windows_dunkel():
    """Ist das System auf dunkel gestellt? Unter Windows zuerst die Einstellung „Standard-App-Modus“ (Registry
    AppsUseLightTheme), denn Qt meldet das Farbschema beim Start nicht immer (dann wurde bisher Hell gewählt, Windows
    färbte Fenster aber dunkel: weiße Karten auf dunklem Grund, 24.10.2026). Sonst Qt (QStyleHints.colorScheme)."""
    import sys
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as schluessel:
                return winreg.QueryValueEx(schluessel, "AppsUseLightTheme")[0] == 0
        except OSError:
            pass
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        schema = QGuiApplication.styleHints().colorScheme()
        if schema != Qt.ColorScheme.Unknown:
            return schema == Qt.ColorScheme.Dark
        return QGuiApplication.palette().window().color().lightness() < 128
    except Exception:       # noqa: BLE001 – ältere Qt-Version oder ohne Anwendung
        return False


def thema_aufloesen(name, windows_dunkel_=None):
    """„Wie Windows“ -> Dunkel oder Hell; Unbekanntes -> Hell."""
    if name == "Wie Windows":
        if windows_dunkel_ is None:
            windows_dunkel_ = windows_dunkel()
        return "Dunkel" if windows_dunkel_ else "Hell"
    return name if name in UMSETZUNG or name == "Hell" else "Hell"


def umsetzen(text, name=None):
    """Hell-Farben (#RRGGBB) in einem Text auf das Theme umsetzen; „Hell“ und Unbekanntes bleiben unverändert."""
    global _HEX
    tabelle = UMSETZUNG.get(name or _thema)
    if not tabelle or not text or "#" not in text:
        return text
    if _HEX is None:
        import re
        _HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
    return _HEX.sub(lambda m: tabelle.get(m.group(0).upper(), m.group(0)), text)


def farbe(hell, alpha=None):
    """QColor einer Hell-Farbe im aktuellen Theme (für Farben, die beim Zeichnen entstehen); alpha 0 … 255."""
    from PySide6.QtGui import QColor
    c = QColor(umsetzen(hell))
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def farbe_fest(hell):
    """QColor-Konstante (auf Modulebene): anwenden() färbt sie beim Themewechsel an Ort und Stelle um."""
    c = farbe(hell)
    _FEST.append((c, hell))
    return c


def stylesheet(name="Hell", dichte="normal"):
    """Stylesheet für Theme und Dichte; Hell + normal = STIL unverändert."""
    name = thema_aufloesen(name)
    zusatz = ZUSATZ.get(name, "")
    if "{" + "HAKEN}" in zusatz or "{" + "PFEIL" in zusatz:
        for schluessel, datei in _zeichen().items():
            zusatz = zusatz.replace("{" + schluessel + "}", datei)
    return umsetzen(STIL, name) + zusatz + DICHTE_CSS.get(dichte, "")


_ZEICHEN = None


def _zeichen():
    """Häkchen, Punkt und Pfeile für das Dunkel-Stylesheet als kleine PNG-Dateien (Stylesheets brauchen eine Datei;
    gezeichnet, ohne Bilddatei im Programm). Ergebnis: {Platzhalter: Pfad mit /}."""
    global _ZEICHEN
    if _ZEICHEN is not None:
        return _ZEICHEN
    import tempfile
    from pathlib import Path
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
    ordner = Path(tempfile.gettempdir()) / "rohrlaser_stil"
    ergebnis = {}
    try:
        ordner.mkdir(exist_ok=True)
        for name, zeichnen in (
                ("HAKEN", lambda p: (p.setPen(QPen(QColor("#10161F"), 3.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)),
                                     p.drawPolyline([QPointF(6, 13.5), QPointF(11, 18.5), QPointF(20, 8)]))),
                ("PUNKT", lambda p: (p.setPen(Qt.NoPen), p.setBrush(QColor("#6CA6DE")),
                                     p.drawEllipse(QRectF(7, 7, 12, 12)))),
                ("PFEIL", lambda p: (p.setPen(Qt.NoPen), p.setBrush(QColor("#C3CBD6")),
                                     p.drawPolygon(QPolygonF([QPointF(4, 8), QPointF(22, 8), QPointF(13, 19)])))),
                ("PFEIL_AUF", lambda p: (p.setPen(Qt.NoPen), p.setBrush(QColor("#C3CBD6")),
                                         p.drawPolygon(QPolygonF([QPointF(4, 18), QPointF(22, 18), QPointF(13, 7)]))))):
            bild = QImage(26, 26, QImage.Format_ARGB32)
            bild.fill(0)
            p = QPainter(bild)
            p.setRenderHint(QPainter.Antialiasing)
            zeichnen(p)
            p.end()
            datei = ordner / f"{name.lower()}.png"
            bild.save(str(datei))
            ergebnis[name] = datei.as_posix()
    except OSError:         # Temp-Ordner nicht beschreibbar: Kästchen ohne Häkchen-Bild (gefüllt = an)
        ergebnis = {k: "" for k in ("HAKEN", "PUNKT", "PFEIL", "PFEIL_AUF")}
    _ZEICHEN = ergebnis
    return ergebnis


def schrift_auf(flaeche):
    """Lesbare Schriftfarbe auf einer farbigen Fläche (QColor oder #RRGGBB): dunkel auf hellen Farben, weiß auf
    dunklen – z. B. Positionsnummern im Stangenbild auf Orange, Grün oder Gelb."""
    from PySide6.QtGui import QColor
    c = QColor(flaeche)
    hell_ = kontrast("#FFFFFF", c.name()) < kontrast("#111827", c.name())
    return QColor("#111827" if hell_ else "#FFFFFF")       # fest: hängt nur von der Fläche ab, nicht vom Theme


def kontrast(vorne, hinten):
    """Kontrastverhältnis nach WCAG 2.1 zweier Farben #RRGGBB (1 … 21)."""
    def hell(h):
        def kanal(c):
            c /= 255
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * kanal(r) + 0.7152 * kanal(g) + 0.0722 * kanal(b)
    a, b = sorted((hell(vorne), hell(hinten)), reverse=True)
    return (a + 0.05) / (b + 0.05)


# Textfarbe auf Fläche, die in jedem Theme WCAG AA (4,5 : 1) erreichen müssen (Prüfung: tests/test_themes.py)
KONTRAST_PAARE = [
    (TEXT, "#FFFFFF", "Text auf Karte"), (TEXT, FLAECHE, "Text auf Fläche"), (TEXT_GRAU, "#FFFFFF", "Nebentext auf Karte"),
    (AKZENT, "#FFFFFF", "Kartentitel"), ("#FFFFFF", AKZENT, "Hauptknopf"), (ROT, ROT_FLAECHE, "Fehler"),
    (GELB_TEXT, GELB_FLAECHE, "Warnung"), (GRUEN, GRUEN_FLAECHE, "OK"), ("#8C1D18", "#FDECEA", "Stand veraltet"),
    ("#7A5A00", "#FFF6DB", "Stand offen"), (TEXT, "#FFFCF0", "Eingabezelle"), (TEXT, "#EDEDED", "berechnete Zelle"),
    ("#111827", "#CFE0F5", "Auswahl"), ("#285F9E", "#E4EEFA", "Satzname Blau"), ("#6E3FA3", "#EEE6F7", "Satzname Violett"),
    (TEXT, "#E4EEFA", "Satzzeile Blau"), (TEXT, "#EEE6F7", "Satzzeile Violett"), ("#3A4656", "#EEF1F5", "Reiter"), (AKZENT, "#EEF4FB", "Verkaufspreis"),
]


def palette(name):
    """QPalette für Fenster, Eingabefelder und Standarddialoge (Fusion). Auch Hell wird fest gesetzt: sonst übernimmt
    Qt im Windows-Dunkelmodus die dunklen Systemfarben und mischt sie mit dem hellen Stylesheet."""
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication
    p = QPalette(QApplication.style().standardPalette())      # Fusion: immer die helle Standardpalette
    if name == "Hell":
        # Fensterfläche im kühlen Grau der Karten und Kennzahlen statt Fusion-Grau #EFEFEF (26.10.2026): weniger
        # Mischung aus warmem und kühlem Grau
        p.setColor(QPalette.Window, QColor(FLAECHE))
        p.setColor(QPalette.Button, QColor("#EEF1F5"))
        return p
    u = lambda h: QColor(umsetzen(h, name))     # noqa: E731
    rollen = {QPalette.Window: FLAECHE, QPalette.WindowText: TEXT, QPalette.Base: "#FFFFFF",
              QPalette.AlternateBase: "#F5F8FB", QPalette.Text: TEXT, QPalette.Button: "#EEF1F5",
              QPalette.ButtonText: TEXT, QPalette.Highlight: "#CFE0F5", QPalette.HighlightedText: "#111827",
              QPalette.ToolTipBase: "#FFFFFF", QPalette.ToolTipText: TEXT, QPalette.PlaceholderText: "#9AA3AF",
              QPalette.Link: AKZENT, QPalette.Light: "#FFFFFF", QPalette.Mid: "#C5CCD6", QPalette.Dark: "#9AA3AF"}
    for rolle, hell in rollen.items():
        p.setColor(rolle, u(hell))
    for rolle in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, rolle, u("#9AA3AF"))
    return p


_gepatcht = False
_HELL_TEXT, _HELL_STIL = "hell_text", "hell_stil"      # Eigenschaften: Text bzw. Stylesheet in Hell-Farben


def _farben_in_texten():
    """Farben in setStyleSheet und Beschriftungstexten (HTML) des Programms auf das Theme umsetzen. Die Hell-Fassung
    bleibt am Widget stehen, damit ein Themewechsel im laufenden Programm (umfaerben) wieder von ihr ausgeht."""
    global _gepatcht
    if _gepatcht:
        return
    from PySide6.QtWidgets import QLabel, QWidget
    alt_stil, alt_text = QWidget.setStyleSheet, QLabel.setText

    def stil_setzen(self, text):
        if text and "#" in text:
            self.setProperty(_HELL_STIL, text)
        elif self.property(_HELL_STIL) is not None:
            self.setProperty(_HELL_STIL, None)
        alt_stil(self, umsetzen(text))

    def text_setzen(self, text):
        if isinstance(text, str):
            if "#" in text:
                self.setProperty(_HELL_TEXT, text)
            elif self.property(_HELL_TEXT) is not None:
                self.setProperty(_HELL_TEXT, None)
            text = umsetzen(text)
        alt_text(self, text)
    QWidget.setStyleSheet, QLabel.setText = stil_setzen, text_setzen
    QWidget._stil_roh, QLabel._text_roh = alt_stil, alt_text
    _gepatcht = True


class _TexteBeimZeigen:
    """Beschriftungen, deren Text schon im Konstruktor steht (QLabel("<h2 style='color:…'>…")), beim ersten
    Polieren umfärben; als Ereignisfilter der Anwendung."""

    def __new__(cls):
        from PySide6.QtCore import QEvent, QObject
        from PySide6.QtWidgets import QAbstractSpinBox, QLabel, QLineEdit

        class Filter(QObject):
            def eventFilter(self, obj, ereignis):
                if ereignis.type() == QEvent.Polish and isinstance(obj, QLabel) and _thema != "Hell":
                    t = obj.text()
                    if "#" in t and obj.property(_HELL_TEXT) is None:
                        neu = umsetzen(t)
                        if neu != t:
                            obj.setText(t)          # merkt die Hell-Fassung und setzt um
                elif ereignis.type() == QEvent.Polish and isinstance(obj, QAbstractSpinBox):
                    # Dunkel: Zahlenfeld mit Rahmen aus dem Stylesheet – dort wirkt padding nicht, der Text stünde
                    # direkt am Rahmen; Abstand wie bei den Textfeldern
                    feld = obj.findChild(QLineEdit)
                    if feld is not None:
                        feld.setTextMargins(3 if _thema == "Dunkel" else 0, 0, 0, 0)
                return False
        return Filter()


def _farbschema_setzen(name):
    """Qt mitteilen, ob hell oder dunkel (Qt 6.8+): Titelleisten und Standarddialoge von Windows passen dann dazu."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark if name == "Dunkel" else Qt.ColorScheme.Light)
    except Exception:       # noqa: BLE001 – ältere Qt-Version
        pass


def anwenden(app, name="Hell", schrift=100, dichte="normal"):
    """Theme, Schriftgröße [%] und Dichte für die ganze Anwendung (beim Start, vor dem Hauptfenster).
    Ergebnis: wirksames Theme. Hell, 100 %, normal ändert am Aussehen nichts gegenüber bisher."""
    global _thema, _filter
    _thema = thema_aufloesen(name)
    for c, hell in _FEST:
        c.setRgba(farbe(hell).rgba())
    _farbschema_setzen(_thema)
    app.setPalette(palette(_thema))
    _farben_in_texten()
    if _filter is None:
        _filter = _TexteBeimZeigen()
        app.installEventFilter(_filter)
    try:
        prozent = max(90, min(150, int(schrift or 100)))
    except (TypeError, ValueError):
        prozent = 100
    if _basis_schrift is None:
        _schrift_merken(app)
    f = app.font()
    if _basis_schrift[0] > 0:
        f.setPointSizeF(_basis_schrift[0] * prozent / 100)
    elif _basis_schrift[1] > 0:
        f.setPixelSize(round(_basis_schrift[1] * prozent / 100))
    if prozent != 100 or f != app.font():
        app.setFont(f)
    global _dichte
    _dichte = dichte if dichte in DICHTEN else "normal"
    return _thema


def _schrift_merken(app):
    global _basis_schrift
    _basis_schrift = (app.font().pointSizeF(), app.font().pixelSize())


def umfaerben(app):
    """Themewechsel im laufenden Programm (nach anwenden): Stylesheets und Beschriftungen aller Widgets aus ihrer
    Hell-Fassung neu umsetzen und alles neu zeichnen."""
    from PySide6.QtWidgets import QLabel, QWidget
    for w in app.allWidgets():
        roh = None if w.isWindow() else w.property(_HELL_STIL)    # Fenster: Stylesheet aus aktuell() setzt der Aufrufer
        if roh is None and "#" in (w.styleSheet() or "") and not w.isWindow():
            roh = w.styleSheet()            # vor dem ersten Umsetzen gesetzt: steht noch in Hell da
        if roh:
            w.setProperty(_HELL_STIL, roh)
            QWidget._stil_roh(w, umsetzen(roh))
        if isinstance(w, QLabel):
            roh = w.property(_HELL_TEXT)
            if roh is None and "#" in (w.text() or ""):
                roh = w.text()
            if roh:
                w.setProperty(_HELL_TEXT, roh)
                QLabel._text_roh(w, umsetzen(roh))
        w.update()


class druckfarben:
    """with stil.druckfarben(): … – Bilder für PDF-Ausgaben (Zeichnung, Skizze) immer in Hell-Farben zeichnen, auch
    wenn das Programm dunkel läuft."""

    def __enter__(self):
        global _thema
        self.alt = _thema
        if self.alt != "Hell":
            _thema = "Hell"
            for c, hell in _FEST:
                c.setRgba(farbe(hell).rgba())
        return self

    def __exit__(self, *_):
        global _thema
        if self.alt != "Hell":
            _thema = self.alt
            for c, hell in _FEST:
                c.setRgba(farbe(hell).rgba())
        return False


_dichte = "normal"
_filter = None
_basis_schrift = None


def aktuell():
    """Stylesheet des Hauptfensters für das wirksame Theme und die Dichte."""
    return stylesheet(_thema, _dichte)


def fenster_stil(fenster):
    """Stylesheet des Hauptfensters setzen; ohne zweites Umsetzen der schon umgesetzten Farben."""
    from PySide6.QtWidgets import QWidget
    getattr(QWidget, "_stil_roh", QWidget.setStyleSheet)(fenster, aktuell())


def ansicht_wechseln(app, fenster, name, schrift=100, dichte="normal"):
    """Theme, Schrift und Dichte im laufenden Programm wechseln (Einstellungen › Ansicht): sofort wirksam."""
    ergebnis = anwenden(app, name, schrift, dichte)
    umfaerben(app)
    fenster_stil(fenster)
    return ergebnis
