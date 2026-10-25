"""Fenster 'Neue Position': zuerst der Typ (Patrick 22.10.2026), danach öffnet das Angebot das passende Fenster:
Rohr / Profil = Schneidweg-Rechner mit Kopfzeile (Artikel, Profil, Werkstoff, Länge, Stückzahl), Blech / Kantteil =
Schnellanlage eines Zukaufartikels (Kategorie Blechteile), Aus DXF = DXF-Import (Bleche: dxf_import_dialog, Rohrzeichnung: Rohr-Editor), Zukaufteil = dieselbe Schnellanlage ohne Kategorie,
Schweißbaugruppe = Editor der Baugruppe (baugruppe_dialog), Rahmen-Assistent = rahmen_dialog, leere
Zeile = wie bisher alles in der Positionsliste eintragen."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout

ROHR, BLECH, ZUKAUF, LEER = "Rohr / Profil", "Blech / Kantteil", "Zukaufteil", "Leere Zeile"
DXF = "Aus DXF (Blech oder Rohr)"
SCHWEISS = "Schweißbaugruppe"
RAHMEN = "Rahmen-Assistent"
TYPEN = {ROHR: "Laserteil aus Rohr oder Profil: Profil, Werkstoff, Länge und Stückzahl, dazu Enden, Bohrungen und "
               "Konturen im Schneidweg-Rechner mit Skizze.",
         BLECH: "Blech- oder Kantteil (vom Blechlaser, als Zukaufteil): Bezeichnung, Lieferant (Technik "
                "vorbelegt), Einkaufspreis und Menge.",
         DXF: "Eine oder mehrere DXF-Dateien einlesen: jedes Blech der Zeichnung wird eine Position wie aus dem "
              "Blech-Editor (Werkstoff und Dicke vorgeschlagen, Rahmen und Schriftfeld fallen weg). Zeigt die Datei "
              "ein Rohrteil in Ansichten mit Schnitt, öffnet der Rohr-Editor mit Profil, Länge, Enden und Konturen.",
         ZUKAUF: "Anderes Zukaufteil (Normteil, Schrauben, Handelsware …): Bezeichnung, Kategorie, Lieferant, "
                 "Einkaufspreis und Menge.",
         SCHWEISS: "Baugruppe aus Einzelteilen dieses Angebots: Unterbaugruppen, Nahtgruppen, Arbeitsgänge und "
                   "Vorrichtungen. Markierte Positionen sind als Einzelteile vorgewählt.",
         RAHMEN: "Rechteckrahmen oder Quader aus Quadrat-, Rechteck- oder Rundrohr ohne STEP-Datei: Maße, Profil "
                 "und Ecken (Gehrung, stumpf, gesteckt) eingeben, die Rohre werden ein Satz mit 3D.",
         LEER: "Leere Zeile in der Positionsliste, alle Werte von Hand eintragen."}


class TypDialog(QDialog):
    """Auswahl des Typs; nach OK steht er in self.typ (ROHR, BLECH, DXF, ZUKAUF, SCHWEISS, RAHMEN oder LEER)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Neue Position")
        self.typ = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Welche Art von Position?</b>"))
        for typ, text in TYPEN.items():
            b = QPushButton(typ)
            b.setMinimumHeight(40)
            b.setDefault(typ == ROHR)
            b.clicked.connect(lambda _=False, typ=typ: self.waehlen(typ))
            lay.addWidget(b)
            hinweis = QLabel(text)
            hinweis.setWordWrap(True)
            hinweis.setStyleSheet("color: #595959; margin-bottom: 6px;")
            lay.addWidget(hinweis)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Cancel)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe, 0, Qt.AlignRight)
        self.setMinimumWidth(420)

    def waehlen(self, typ):
        self.typ = typ
        self.accept()
