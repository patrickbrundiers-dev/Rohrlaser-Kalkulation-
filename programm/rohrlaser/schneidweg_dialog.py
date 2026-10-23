"""Dialog 'Schneidweg berechnen …' einer Position: Enden (gerade, Gehrung oder Ausklinkung), Innenkonturen (Bohrung,
Langloch, Rechteck, Schlitz, Polygon aus Koordinaten, sonstige Kontur), Gravur und Schweißnaht eingeben;
Skizze, Schnittlängen, Einstiche, Konturklassen, Gewinde-Vorschlag und die Schneidzeit mit den Schneiddaten der
Maschine stehen sofort daneben. Teile aus dem STEP-Import zeigen die gemessenen Werte (auch ältere Positionen aus
den gespeicherten Feldern, STEP neu einlesen holt Lage und Maße aus der Datei). Die Formeln stehen in schneidweg.py;
OK schreibt die Werte in die Position (Angebotsseite.schneidweg_berechnen), Zeichnung als PDF in zeichnung.py."""
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu,
                               QMessageBox, QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from . import stil
from . import biegerohr, dfm, dreid, hilfe, naht, profil_neu, rechnen, schneidweg as sw, skizze as sk
from .ansicht3d import Ansicht3DMitKnoepfen
from .leiste import UmbruchLeiste
from .skizze_widget import MODI, Skizze
from .teile_editor import EditorRahmen
from .stammdaten import zahl_aus_text
from .step import KERNLOCH

KONTUR_SPALTEN = ("Art", "Anzahl", "Maß 1 [mm]", "Maß 2 [mm]", "Maß 3 [mm]", "Lage ab Ende A [mm]",
                  "Abstand Muster [mm]", "Seite", "Versatz quer [mm]", "3D", "Neigung längs [°]", "Neigung quer [°]",
                  "Bemerkung", "Gewinde")
SPALTEN_HILFE = (
    "Art der Innenkontur (Bohrung, Senkung, Langloch …)",
    "Anzahl gleicher Konturen je Teil",
    "erstes Maß der Konturart (markierte Zeile: Name steht in der Überschrift)",
    "zweites Maß der Konturart (markierte Zeile: Name steht in der Überschrift)",
    "drittes Maß der Konturart (markierte Zeile: Name steht in der Überschrift)",
    "Mitte der (ersten) Kontur in mm ab Ende A; leer = gleichmäßig verteilt",
    "Muster längs: Abstand von Mitte zu Mitte; die Anzahl Konturen folgt im Abstand",
    "Fläche, auf der die Kontur sitzt, von Ende A gesehen (Rechteck-/Quadratrohr 0° oben, 90° vorne = rechts, 180° "
    "unten, 270° hinten = links; Rundrohr Winkel am Umfang)",
    "Versatz der Kontur quer zur Flächenmitte in mm (+ zur nächsten Fläche hin)",
    "Bohrung in 3D: Achse nicht senkrecht zur Rohroberfläche (schräg, Kopf geschwenkt); nur mit Häkchen "
    "„3D-Schnittbearbeitung aktivieren“",
    "Neigung der Bohrungsachse gegen die Wandnormale längs zum Rohr: + = Richtung Ende B, − = Richtung Ende A, "
    "0° = senkrecht zur Wand (nicht der Umfangswinkel, der steht in Seite)",
    "Neigung der Bohrungsachse quer: + = im Uhrzeigersinn von Ende A gesehen (Richtung 90°), − = dagegen",
    "freier Text (erscheint in der Skizze und der Zeichnung)",
    "Gewinde der Bohrung oder des Flowdrill-Lochs: automatisch nach dem Kernloch-Ø, kein Gewinde oder ein Gewinde "
    "aus den Stammdaten; kommt beim Übernehmen bestätigt in die Position")
# Bedeutung der Maße je Konturart (Erklärung unter der Tabelle für die markierte Zeile)
ART_HILFE = {
    sw.BOHRUNG: "Maß 1 = Durchmesser Ø d. Schnittlänge π × d.",
    sw.SENKUNG: "Maß 1 = Bohrung Ø d (wird geschnitten), Maß 2 = Senk-Ø D außen (Senken kommt als Zusatzarbeit in "
                "die Position).",
    sw.FLOWDRILL: "Maß 1 = Kernloch Ø d des Flowdrill-Lochs (nicht geschnitten, nur markiert: Gravur oder Loch Ø 0,5 "
                  "wie in den Einstellungen); Flowdrill und Gewinde kommen als Zusatzarbeit in die Position.",
    sw.LANGLOCH: "Maß 1 = Gesamtlänge l außen (längs zum Teil), Maß 2 = Breite b (= Ø der Rundungen).",
    sw.RECHTECK: "Maß 1 = Breite b (längs zum Teil), Maß 2 = Höhe h (quer), Maß 3 = Eckradius r (0 = scharfkantig).",
    sw.SCHLITZ: "Schlitz offen vom Rand: Maß 1 = Tiefe l, Maß 2 = Breite b.",
    sw.AUSKLINKUNG: "Ausklinkung am Ende: Maß 1 = Länge l ab Ende, Maß 2 = Breite b, Maß 3 = Eckradius r innen; "
                    "ohne Lage an Ende A, für Ende B Lage = Teilelänge − l/2.",
    sw.POLYGON: "Maß 1 = Eckpunkte x,y in mm, getrennt mit Semikolon, z. B. 0,0; 40,0; 40,20; 0,20.",
    sw.SONSTIGE: "Maß 1 = Schnittlänge in mm, Maß 2 = Hüllmaß (größte Ausdehnung, leer = groß) für die Konturklasse.",
    sw.SONDERKONTUR: "Freie Kontur, auch über mehrere Flächen (aus dem STEP-Import mit echtem Umriss): Maß 1 = "
                     "Schnittlänge, Maß 2 = Hüllmaß für die Konturklasse.",
    sw.GRAVUR: "Gravur (Markierung, Prägung) an dieser Stelle: Maß 1 = Gravurlänge; zählt zur Gravur, nie zum "
               "Schneidweg. In der Skizze grün."}
LAGE_HILFE = ("Lage ab Ende A = Mitte der Kontur, Abstand Muster = Mitte zu Mitte, Seite = Fläche von Ende A gesehen, "
              "Versatz quer = ab Flächenmitte. Lage, Seite und Versatz zählen nur für Skizze und Zeichnung.")
LAGE_SPALTE, ABSTAND_SPALTE, SEITE_SPALTE, QUER_SPALTE, D3_SPALTE, NL_SPALTE, NQ_SPALTE, TEXT_SPALTE, GEWINDE_SPALTE = range(5, 14)
GEWINDE_AUTO, GEWINDE_KEIN = "automatisch", "kein Gewinde"
SCHNELLWAHL = tuple("0°" if not w else f"{w:+d}°".replace("-", "−") for w in dreid.SCHNELLWAHL)
ERGEBNIS_SPALTEN = ("Schnitt", "Anz.", "je Stück [mm]", "gesamt [mm]", "Einst.", "Hüllmaß [mm]", "Klasse")
VORLAGEN = "rechner_vorlagen"          # Einstellung: {Name: {a, b, gravur, konturen, profilform}}
MASS_HILFE = ("Maße: Bohrung Ø · Senkung Bohrung Ø, Senk-Ø · Langloch Länge, Breite · Rechteck Breite, Höhe, "
              "Eckradius · Schlitz (offen, vom Rand) Tiefe, Breite · Ausklinkung am Ende Länge, Breite, Eckradius · "
              "Polygon Eckpunkte in Maß 1, z. B. 0,0; 40,0; 40,20; 0,20 · sonstige Kontur "
              "Schnittlänge, Hüllmaß (leer = groß). Lage ab Anfang = Mitte der (ersten) Kontur, leer = verteilt; Abstand = "
              "Muster längs (Anzahl Konturen im Abstand); Seite und Versatz quer zur Flächenmitte bzw. beim Rundrohr der "
              "Winkel (0° oben, 90° vorne). Rechteck- und Quadratrohr: Seite nur 0°, 90°, 180° oder 270°. Lage, Seite "
              "und Versatz zählen nur für die Skizze, nicht für den Schneidweg.")
NAHT_WAHL = {"0° oben": 0.0, "90° vorne (rechts)": 90.0, "180° unten": 180.0, "270° hinten (links)": 270.0}


def _zahl(text):
    t = (text or "").strip()
    if not t:
        return None
    try:
        return zahl_aus_text(t)
    except ValueError:
        return None


class SchneidwegDialog(QDialog):
    """p: Position, profil: Stammdaten-Zeile des Profils, kopf/k/tabellen: Angebot und Stammdaten (Maschine,
    Konturgrenzen, Schneiddaten), db: Datenbank für Vorlagen, positionen: Positionen des Angebots zum Kopieren von
    Konturen. Nach OK: self.eingaben (dict) und self.ergebnis (schneidweg.rechnen)."""

    def __init__(self, parent, p, profil, kopf, k, tabellen, db=None, positionen=None, step_lesen=None, neu=False):
        super().__init__(parent)
        self.neu = neu                  # neue Position: Kopfzeile mit Artikel, Profil, Werkstoff, Länge, Stückzahl
        self.p, self.profil, self.kopf, self.k, self.tabellen = p, profil, kopf, k, tabellen
        self.db, self.positionen = db, [x for x in (positionen or ()) if x.get("id") != p.get("id")]
        self.step_lesen = step_lesen    # Funktion: STEP-Datei wählen und messen -> [Messwerte] oder None
        m = rechnen.maschine(kopf, k)
        self.grenzen = rechnen.kontur_regel(m, rechnen.wand_schneiden(profil))
        self.gewinde = gewinde_liste(tabellen)
        self.ergebnis = None
        e, self.aus_position = sw.aus_position(sw.lesen(p.get("technik")), p, profil)
        # Profil der Position anders als gemessen (von Hand geändert): Konturen umrechnen bzw. Umriss übertragen
        e, self._umstell_hinweise, _, _ = sw.konturen_umstellen(e, dict(profil, profil_id=p.get("profil_id")))
        self.biegerohr = biegerohr.lesen(e)        # Biegerohr aus dem STEP-Import: bleibt in den Eingaben
        self._ende_step = {}            # je Ende: Eingaben wie gemessen und gemessene Werte (STEP-Import)
        self.setWindowTitle(f"Neue Position {p.get('pos') or ''} – Rohr / Profil".strip() if neu else
                            f"Schneidweg berechnen – Pos. {p.get('pos') or ''} {p.get('artikel') or ''}".strip())
        self._groesse_setzen()
        self.qs = sk.Querschnitt(profil)
        self.kasten = profil.get("form") in ("Quadratrohr", "Rechteckrohr")
        haupt = QVBoxLayout(self)
        teiler = QSplitter(Qt.Vertical)
        haupt.addWidget(teiler, 1)
        oben = QWidget()
        lay = QVBoxLayout(oben)
        lay.setContentsMargins(0, 0, 0, 0)
        teiler.addWidget(oben)
        form = profil.get("form")
        self.vorgabe_grenzen = rechnen.kontur_grenzen(m)[1]
        if neu:
            lay.addLayout(self._kopfzeile_bauen())
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self._info_zeigen()
        self.step_info = QLabel()
        self.step_info.setWordWrap(True)
        self.step_info.setStyleSheet("color: #1E6B35;")
        lay.addWidget(self.step_info)
        # 3D-Schnittbearbeitung (dreid): Häkchen am Bauteil, dann je Gehrung und Bohrung „3D“
        self.maschine = m
        zeile_3d = QHBoxLayout()
        self.d3 = QCheckBox("3D-Schnittbearbeitung aktivieren")
        self.d3.setChecked(e.get("d3") is True)
        self.d3.setToolTip("3D = die Schnittfläche steht nicht senkrecht (90°) zur Rohroberfläche, der Laserkopf wird "
                           "geschwenkt: Gehrungen in 3D und schräge Bohrungen. Bleibt der Strahl senkrecht zur "
                           "Oberfläche, ist es 2D, auch bei einer Gehrung. Aus = 2D, keine 3D-Zeiten, kein 3D-Greifmaß")
        self.d3.toggled.connect(self.rechnen)
        self.d3_info = QLabel()
        self.d3_info.setWordWrap(True)
        zeile_3d.addWidget(self.d3)
        zeile_3d.addWidget(self.d3_info, 1)
        lay.addLayout(zeile_3d)

        enden = QGridLayout()
        self.winkel, self.achse, self.sattel, self.richtung, self.gemessen_text = {}, {}, {}, {}, {}
        self.winkel_b = {}          # zweiachsiger Schrägschnitt: Winkel über Breite (Gehrungswinkel = über Höhe)
        self.ende_3d = {}
        rund = form == "Rundrohr"
        for c, (titel, tipp) in enumerate((
                ("Gehrungswinkel", "Abweichung vom rechtwinkligen Schnitt in Grad (gerade = 0°)"),
                ("gekippt über", "Richtung, über die die Gehrung kippt: Höhe = Maß a, Breite = Maß b des Profils; "
                 "„über Höhe und Breite“ = Schrägschnitt zweiachsig"),
                ("Winkel über Breite", "nur Schrägschnitt zweiachsig: Neigung über Breite (der Gehrungswinkel ist "
                 "dann die Neigung über Höhe)"),
                ("längste Seite (Gehrungsrichtung)", "Seite, an der das Teil an diesem Ende am längsten ist, von "
                 "Ende A gesehen; „automatisch“ nimmt sie aus „gekippt über“ an, die Optimierung dreht das Teil passend"),
                ("Ausklinkung auf Rundrohr Ø", "nur Rundrohr: Ende rechtwinklig auf ein Rundrohr mit diesem Ø "
                 "(Sattelschnitt)"),
                ("aus dem STEP-Import", "gemessene Schnittlänge des Endes; gilt, solange das Ende unverändert bleibt"),
                ("3D", "Gehrung in 3D: Schnittfläche nicht senkrecht zur Rohroberfläche, der Kopf wird auf den "
                       "Gehrungswinkel geschwenkt (ebene Schnittfläche durch die Wand). Ohne Häkchen ist die Gehrung "
                       "2D (Strahl senkrecht zur Oberfläche). Nur mit „3D-Schnittbearbeitung aktivieren“ und einer "
                       "Gehrung")),
                start=1):
            kopf_ = QLabel(f"<span style='color:#595959'>{titel}</span>")
            kopf_.setToolTip(tipp)
            enden.addWidget(kopf_, 0, c)
        for r, (seite, titel) in enumerate((("a", "Anfangsschnitt (Ende A)"), ("b", "Endschnitt (Ende B)")), start=1):
            w = QDoubleSpinBox()
            w.setRange(0, 79.9)
            w.setDecimals(1)
            w.setSuffix(" °")
            w.setSpecialValueText("gerade")
            zwei = e[seite].get("achse") == sw.ACHSE_ZWEI
            w.setValue(sw._z(e[seite].get("winkel_h" if zwei else "winkel")))
            w.setToolTip("Gehrung: Abweichung vom rechtwinkligen Schnitt (0° = gerader Schnitt); beim Schrägschnitt "
                         "zweiachsig die Neigung über Höhe")
            w.valueChanged.connect(self.rechnen)
            wb = QDoubleSpinBox()
            wb.setRange(0, 79.9)
            wb.setDecimals(1)
            wb.setSuffix(" °")
            wb.setSpecialValueText("–")
            wb.setValue(sw._z(e[seite].get("winkel_b")) if zwei else 0)
            wb.setEnabled(zwei)
            wb.setToolTip("Schrägschnitt zweiachsig: Neigung über Breite (Maß b)")
            wb.valueChanged.connect(self.rechnen)
            a = QComboBox()
            a.addItems(sw.ACHSEN_WAHL)
            a.setCurrentText(e[seite].get("achse") or sw.ACHSEN[0])
            a.setEnabled(not rund)
            a.setToolTip("Richtung, in die die Gehrung kippt (Höhe = Maß a, Breite = Maß b des Profils); „über Höhe "
                         "und Breite“ = Schrägschnitt zweiachsig mit zwei Winkeln")
            a.currentTextChanged.connect(lambda t, wb=wb: wb.setEnabled(t == sw.ACHSE_ZWEI))
            a.currentTextChanged.connect(self.rechnen)
            sa = QDoubleSpinBox()
            sa.setRange(0, 2000)
            sa.setDecimals(1)
            sa.setSuffix(" mm")
            sa.setSpecialValueText("keine")
            sa.setValue(sw._z(e[seite].get("sattel")))
            sa.setEnabled(rund)
            sa.setToolTip("Ausklinkung (Sattelschnitt): Ø des Rundrohrs, auf das dieses Ende rechtwinklig gesetzt wird"
                          + ("" if rund else " – nur beim Rundrohr"))
            sa.valueChanged.connect(self.rechnen)
            ri = QComboBox()
            ri.addItems(list(sw.RICHTUNGEN))
            ri.setCurrentText(next((t for t, v in sw.RICHTUNGEN.items() if v == e[seite].get("richtung")),
                                   sw.AUTOMATISCH))
            ri.setEnabled(form in sw.MIT_RICHTUNG)
            ri.setToolTip("Gehrung: Seite, an der das Teil an diesem Ende am längsten ist (Blick von Ende A, "
                          "Rechteckrohr mit der Breitseite oben). „automatisch“: aus „gekippt über“ angenommen, die "
                          "Skizze zeigt sie; die Optimierung dreht das Teil frei und legt Gehrungen ineinander.")
            ri.currentTextChanged.connect(self.rechnen)
            gm = QLabel()
            self.winkel[seite], self.achse[seite], self.sattel[seite], self.richtung[seite] = w, a, sa, ri
            self.winkel_b[seite] = wb
            self.gemessen_text[seite] = gm
            enden.addWidget(QLabel(titel), r, 0)
            enden.addWidget(w, r, 1)
            enden.addWidget(a, r, 2)
            enden.addWidget(wb, r, 3)
            enden.addWidget(ri, r, 4)
            enden.addWidget(sa, r, 5)
            enden.addWidget(gm, r, 6)
            d3 = QCheckBox("Gehrung in 3D")
            d3.setChecked(bool(e[seite].get("d3")))
            d3.toggled.connect(self.rechnen)
            self.ende_3d[seite] = d3
            enden.addWidget(d3, r, 7)
        self._step_enden(e)
        self.gravur = QDoubleSpinBox()
        self.gravur.setRange(0, 100000)
        self.gravur.setDecimals(1)
        self.gravur.setSuffix(" mm")
        self.gravur.setValue(sw._z(e.get("gravur")))
        self.gravur.setToolTip("Länge weiterer Gravurlinien je Teil (Beschriftung, Markierung), zusätzlich zu den "
                               "Zeilen der Art Gravur in der Tabelle; Vorschub Gravur, nicht im Schneidweg")
        self.gravur.valueChanged.connect(self.rechnen)
        enden.addWidget(QLabel("Gravur (Länge je Teil)"), 3, 0)
        enden.addWidget(self.gravur, 3, 1)
        from . import anbau
        anbauteile = anbau.lesen(p.get("anbauteile"))
        if anbauteile:      # Gravur der Anbauteile (STEP-Import) steckt in der Gravur; ändern mit 'Anbauteile prüfen'
            ga = QLabel(f"davon Anbauteile {anbau.dez(anbau.gravur(anbauteile))} mm ({anbau.kurz(anbauteile)})")
            ga.setToolTip("Gravur der aufgeschweißten Teile (Umriss bzw. Marke); ändern in der Angebotsposition mit "
                          "Doppelklick auf die Spalte Anbauteile")
            enden.addWidget(ga, 3, 2, 1, 4)
        # Schweißnaht (SN): wie im Dialog Schweißnaht, Winkel im Bezug Breitseite oben
        self.naht_form = naht.form_von(profil)
        self.naht_vorgabe = QComboBox()
        self.naht_vorgabe.addItems(naht.VORGABEN)
        self.naht_vorgabe.setCurrentText(naht.vorgabe(p))
        self.naht_vorgabe.setToolTip("feste Position = Naht muss an dieser Stelle liegen (Drehen gesperrt); keine "
                                     "Vorgabe = die Optimierung darf das Teil um die eigene Achse drehen")
        self.naht_winkel = self._naht_winkel_bauen(p.get("naht_winkel"))
        self.naht_quelle = QComboBox()
        self.naht_quelle.addItems(naht.QUELLEN)
        self.naht_quelle.setCurrentText(p.get("naht_quelle") or "Kunde")
        self.naht_quelle.setToolTip("Woher die Vorgabe der Naht kommt")
        self.naht_vorgabe.currentTextChanged.connect(self.rechnen)
        self.naht_info = QLabel()
        for w_ in (self.naht_vorgabe, self.naht_winkel, self.naht_quelle):
            w_.setEnabled(self.naht_form is not None)
        enden.addWidget(QLabel("Schweißnaht (SN)"), 4, 0)
        enden.addWidget(self.naht_vorgabe, 4, 1)
        enden.addWidget(self.naht_winkel, 4, 2)
        self.enden_raster = enden
        enden.addWidget(self.naht_quelle, 4, 3)
        enden.addWidget(self.naht_info, 4, 4, 1, 2)
        self._naht_start = self.naht_werte()
        enden.setColumnStretch(5, 1)
        lay.addLayout(enden)

        lay.addWidget(QLabel("<b>Innenkonturen</b>"))
        self.tabelle = QTableWidget(0, len(KONTUR_SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(KONTUR_SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        for i, b in enumerate((130, 60, 150, 80, 80, 140, 140, 120, 120, 40, 110, 110, 160, 110)):
            self.tabelle.setColumnWidth(i, b)
        self.tabelle.horizontalHeader().setSectionResizeMode(TEXT_SPALTE, QHeaderView.Stretch)
        for c, t in enumerate(SPALTEN_HILFE):
            self.tabelle.horizontalHeaderItem(c).setToolTip(t)
        self.tabelle.itemChanged.connect(self.rechnen)
        self.tabelle.itemSelectionChanged.connect(self._auswahl_tabelle)
        self.tabelle.setMinimumHeight(self.tabelle.horizontalHeader().sizeHint().height() + 5 * 26 + 6)
        lay.addWidget(self.tabelle, 1)
        self.erklaerung = QLabel()
        self.erklaerung.setWordWrap(True)
        self.erklaerung.setTextFormat(Qt.RichText)
        lay.addWidget(self.erklaerung)
        lay.addWidget(hilfe.Hinweis(MASS_HILFE, schluessel="schneidweg"))
        # Knopfleiste: Konturarten links, Kopieren/Vorlagen/Entfernen rechts (bei schmalem Fenster zweite Zeile)
        umbruch = UmbruchLeiste()
        leiste = umbruch.links_layout
        for art in sw.ARTEN:
            b = QPushButton(f"+ {art}")
            b.clicked.connect(lambda _=False, art=art: self.zeile_neu(dict(art=art, anzahl=1)))
            leiste.addWidget(b)
        leiste = umbruch.rechts_layout
        weg = QPushButton("Markierte entfernen")
        weg.clicked.connect(self._entfernen)
        kopieren = QPushButton("Aus Position kopieren …")
        kopieren.setToolTip("Konturen einer anderen Position dieses Angebots anhängen")
        kopieren.clicked.connect(self._kopieren_waehlen)
        kopieren.setEnabled(bool(self.positionen))
        leiste.addWidget(kopieren)
        self.vorlagen_knopf = QPushButton("Vorlagen")
        self.vorlagen_knopf.setToolTip("Enden, Konturen und Gravur als Vorlage speichern oder laden (für alle Angebote)")
        self.vorlagen_knopf.setMenu(QMenu(self.vorlagen_knopf))
        self.vorlagen_knopf.menu().aboutToShow.connect(self._vorlagen_menue)
        self.vorlagen_knopf.setEnabled(self.db is not None)
        leiste.addWidget(self.vorlagen_knopf)
        leiste.addWidget(weg)
        lay.addWidget(umbruch)

        mitte = QWidget()
        ml = QVBoxLayout(mitte)
        ml.setContentsMargins(0, 0, 0, 0)
        kopfzeile = QHBoxLayout()
        kopfzeile.addWidget(QLabel("<b>Skizze</b> (maßstäblich)"))
        self.ansicht_wahl = QComboBox()
        self.ansicht_wahl.addItems(MODI)
        self.ansicht_wahl.currentTextChanged.connect(lambda m: self.skizze.modus_setzen(m))
        kopfzeile.addWidget(self.ansicht_wahl)
        einpassen = QPushButton("Einpassen")
        einpassen.clicked.connect(lambda: self.skizze.einpassen())
        kopfzeile.addWidget(einpassen)
        kopfzeile.addStretch(1)
        self.step_knopf = QPushButton("STEP neu einlesen …")
        self.step_knopf.setToolTip("STEP-Datei dieses Teils messen und Konturen, Bohrungen, Enden und Gravur mit Lage "
                                   "und Maßen in den Rechner holen (ersetzt die Eingaben)")
        self.step_knopf.clicked.connect(lambda: self.step_einlesen())
        self.step_knopf.setEnabled(self.step_lesen is not None)
        kopfzeile.addWidget(self.step_knopf)
        zeichnung = QPushButton("Zeichnung als PDF …")
        zeichnung.setToolTip("Maßstäbliche Zeichnung des Teils mit Ansichten, Abwicklung, Bemaßung, Konturliste und "
                             "Schweißnaht als PDF in der Ablage des Angebots")
        zeichnung.clicked.connect(lambda: self.zeichnung_pdf())
        kopfzeile.addWidget(zeichnung)
        ml.addLayout(kopfzeile)
        self.skizze = Skizze(profil, p.get("laenge"))
        self.skizze.gewaehlt.connect(self._auswahl_skizze)
        self.skizze.verschoben.connect(self._verschoben)
        # Skizze und 3D-Ansicht des STEP-Imports (Teile-Editor: Auswahl und Messen) als Reiter
        self.bilder = QTabWidget()
        self.bilder.addTab(self.skizze, "Skizze")
        self.ansicht3d = Ansicht3DMitKnoepfen()
        netz = db.netz(p["id"]) if db is not None and p.get("id") and hasattr(db, "netz") else None
        self.ansicht3d.setzen(netz, "3D-Ansicht (STEP-Import)")
        self.bilder.addTab(self.ansicht3d, "3D")
        ml.addWidget(self.bilder, 1)
        # unten nebeneinander: Skizze (breit, das Rohr ist lang) und Ergebnis je Teil; die Eingaben oben behalten
        # die Höhe für die Konturtabelle (Patrick 22.10.2026: ab der 2. Bohrung musste gescrollt werden)
        self.teiler_unten = QSplitter(Qt.Horizontal)
        self.teiler_unten.addWidget(mitte)
        teiler.addWidget(self.teiler_unten)
        unten = QWidget()
        lay = QVBoxLayout(unten)
        lay.setContentsMargins(0, 0, 0, 0)
        self.teiler_unten.addWidget(unten)
        lay.addWidget(QLabel("<b>Ergebnis je Teil</b>"))
        self.ergebnis_tabelle = QTableWidget(0, len(ERGEBNIS_SPALTEN))
        self.ergebnis_tabelle.setHorizontalHeaderLabels(ERGEBNIS_SPALTEN)
        self.ergebnis_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ergebnis_tabelle.verticalHeader().setVisible(False)
        self.ergebnis_tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ergebnis_tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ergebnis_tabelle.verticalHeader().setDefaultSectionSize(22)
        lay.addWidget(self.ergebnis_tabelle, 1)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        self.summe.setTextFormat(Qt.RichText)
        lay.addWidget(self.summe)
        teiler.setStretchFactor(0, 5)
        teiler.setStretchFactor(1, 4)
        teiler.setChildrenCollapsible(False)
        self.teiler = teiler
        hoehe = self.height() - 60
        teiler.setSizes([int(hoehe * 0.56), hoehe - int(hoehe * 0.56)])
        self.teiler_unten.setStretchFactor(0, 1)
        self.teiler_unten.setStretchFactor(1, 1)
        breite = self.width() - 30
        self.teiler_unten.setSizes([int(breite * 0.57), breite - int(breite * 0.57)])
        lay = haupt
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Position anlegen" if neu else "In Position übernehmen")
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.ok_knopf = knoepfe.button(QDialogButtonBox.Ok)
        for z in e["konturen"]:
            self.zeile_neu(z, rechnen_=False)
        self._step_hinweis()
        self.editor = None
        self.rechnen()
        EditorRahmen(self, "rohr")

    # ------------------------------------------------------------------ Kopf (neue Position) und Profil
    def _info_zeigen(self):
        p, form = self.p, self.profil.get("form")
        self.info.setText(
            f"Profil {p.get('profil_id')} ({form}), Werkstoff {p.get('werkstoff_id') or '–'}, Teilelänge "
            f"{rechnen.zahl(p['laenge'], 1) + ' mm' if isinstance(p.get('laenge'), (int, float)) else '–'}, "
            f"Maschine {self.kopf.get('maschine') or '–'}, Konturgrenzen klein bis {rechnen.zahl(self.grenzen[0])} mm, "
            f"mittel bis {rechnen.zahl(self.grenzen[1])} mm" + (" (Vorgabe)" if self.vorgabe_grenzen else "")
            + (f", zusätzlich klein bis {rechnen.zahl(self.grenzen[2], 1)} × und mittel bis "
               f"{rechnen.zahl(self.grenzen[3], 1)} × Wandstärke {rechnen.zahl(self.grenzen[4])} mm"
               if len(self.grenzen) >= 5 else ""))

    def _kopfzeile_bauen(self):
        """Neue Position: Artikel, Bezeichnung, Profil, Werkstoff, Teilelänge und Stückzahl."""
        raster = QGridLayout()
        self.k_artikel, self.k_bezeichnung = QLineEdit(self.p.get("artikel") or ""), QLineEdit()
        self.k_artikel.setPlaceholderText("Artikelnummer")
        self.k_bezeichnung.setPlaceholderText("Bezeichnung (optional)")
        # Profil: erst die Form wählen (Vorauswahl), dann die Abmessung; fehlt es, „Neu …“ legt es an
        self.k_form = QComboBox()
        self.k_form.addItems([profil_neu.ALLE] + [f for f in self.k.profilformen
                                                   if any(p.get("form") == f for p in self.k.profile.values())])
        self.k_form.setCurrentText((self.k.profile.get(self.p.get("profil_id")) or {}).get("form") or profil_neu.ALLE)
        self.k_form.setToolTip("Profilform: die Liste daneben zeigt nur Profile dieser Form")
        self.k_form.currentTextChanged.connect(self._form_gewaehlt)
        self.k_profil = QComboBox()
        self.k_profil.setEditable(True)
        self.k_profil.setInsertPolicy(QComboBox.NoInsert)
        self.k_profil.addItems(profil_neu.profile_der_form(self.k.profile, self.k_form.currentText()))
        self.k_profil.setCurrentText(self.p.get("profil_id") or "")
        self.k_profil.completer().setFilterMode(Qt.MatchContains)
        self.k_profil.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.k_profil.setToolTip("Profil aus den Stammdaten (Eintippen sucht, z. B. 40x40)")
        self.k_profil.currentTextChanged.connect(self._profil_gewaehlt)
        self.k_profil_neu = QPushButton("Neu …")
        self.k_profil_neu.setToolTip("Profil fehlt in den Stammdaten: hier mit Form und Maßen anlegen")
        self.k_profil_neu.clicked.connect(lambda: self.profil_neu())
        profil_feld = QWidget()
        pl = QHBoxLayout(profil_feld)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(self.k_profil, 1)
        pl.addWidget(self.k_profil_neu)
        self.k_werkstoff = QComboBox()
        self.k_werkstoff.addItems([""] + sorted(self.k.werkstoffe, key=str.lower))
        self.k_werkstoff.setCurrentText(self.p.get("werkstoff_id") or "")
        self.k_werkstoff.currentTextChanged.connect(self._kopf_geaendert)
        self.k_laenge = QDoubleSpinBox()
        self.k_laenge.setRange(0, 100000)
        self.k_laenge.setDecimals(1)
        self.k_laenge.setSuffix(" mm")
        self.k_laenge.setSpecialValueText("fehlt")
        self.k_laenge.setValue(sw._z(self.p.get("laenge")))
        self.k_laenge.setToolTip("Teilelänge in mm (Spitze zu Spitze)")
        self.k_laenge.valueChanged.connect(self._kopf_geaendert)
        self.k_stueck = QSpinBox()
        self.k_stueck.setRange(0, 10 ** 7)
        self.k_stueck.setSpecialValueText("fehlt")
        self.k_stueck.setValue(int(sw._z(self.p.get("stueck"))))
        self.k_stueck.valueChanged.connect(self._kopf_geaendert)
        for c, (titel, w) in enumerate((("Artikel", self.k_artikel), ("Bezeichnung", self.k_bezeichnung),
                                         ("Profilform", self.k_form), ("Profil", profil_feld),
                                         ("Werkstoff", self.k_werkstoff),
                                         ("Teilelänge", self.k_laenge), ("Stückzahl", self.k_stueck))):
            raster.addWidget(QLabel(f"<span style='color:#595959'>{titel}</span>"), 0, c)
            raster.addWidget(w, 1, c)
        raster.setColumnStretch(1, 1)
        raster.setColumnStretch(3, 1)
        return raster

    def _form_gewaehlt(self, form):
        """Profilliste auf die Form beschränken; das gewählte Profil bleibt, wenn es passt, sonst das erste."""
        alt = self.k_profil.currentText()
        liste = profil_neu.profile_der_form(self.k.profile, form)
        self.k_profil.blockSignals(True)
        self.k_profil.clear()
        self.k_profil.addItems(liste)
        self.k_profil.setCurrentText(alt if alt in liste else (liste[0] if liste else ""))
        self.k_profil.blockSignals(False)
        self._profil_gewaehlt(self.k_profil.currentText())

    def profil_neu(self, werte=None, dialog=None):
        """Fehlendes Profil anlegen (ProfilNeuDialog; werte = fertige Zeile ohne Dialog, dialog(d) bedient ihn in
        Tests): in die Stammdaten schreiben und hier wählen. Ergebnis: Profil-ID oder None."""
        interaktiv = werte is None and dialog is None
        if werte is None:
            form = self.k_form.currentText()
            d = profil_neu.ProfilNeuDialog(self, self.k.profile, form if form != profil_neu.ALLE else None,
                                           self.k.profilformen)
            if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or d.fehler():
                return None
            werte = d.werte()
        if not werte.get("profil_id") or werte["profil_id"] in self.k.profile:
            return None
        if self.db is not None:
            self.db.profile_anlegen([werte])
            zeile = next((z for z in self.db.zeilen("profile") if z.get("profil_id") == werte["profil_id"]), werte)
        else:
            zeile = werte
        self.k.profile[werte["profil_id"]] = zeile
        if self.k_form.findText(zeile["form"]) < 0:
            self.k_form.addItem(zeile["form"])
        self.k_form.blockSignals(True)
        self.k_form.setCurrentText(zeile["form"])
        self.k_form.blockSignals(False)
        self._form_gewaehlt(zeile["form"])
        self.k_profil.setCurrentText(werte["profil_id"])
        self._profil_gewaehlt(werte["profil_id"])
        if interaktiv:
            QMessageBox.information(self, "Neues Profil", f"Profil {werte['profil_id']} angelegt. Den Materialpreis "
                                    "bitte unter Einstellungen eintragen oder im Angebot als Meterpreis.")
        return werte["profil_id"]

    def _groesse_setzen(self):
        """Fenster so groß, wie der Bildschirm erlaubt (höchstens 1600 × 1000), damit Konturtabelle, Skizze und
        Ergebnis ohne Scrollen Platz haben."""
        frei = self.screen().availableGeometry() if self.screen() else None
        breite, hoehe = (frei.width() - 40, frei.height() - 70) if frei else (1400, 900)
        self.resize(min(1600, breite), min(1000, hoehe))

    def kopf_werte(self):
        """Felder der neuen Position aus der Kopfzeile (leer ohne Kopfzeile)."""
        if not self.neu:
            return {}
        return dict(artikel=self.k_artikel.text().strip() or None, bezeichnung=self.k_bezeichnung.text().strip() or None,
                    profil_id=self.p.get("profil_id"), werkstoff_id=self.k_werkstoff.currentText() or None,
                    laenge=self.k_laenge.value() or None, stueck=self.k_stueck.value() or None)

    def kopf_fehler(self):
        if not self.neu:
            return []
        f = []
        if self.k_profil.currentText() not in self.k.profile:
            f.append("Profil aus den Stammdaten wählen.")
        if not self.k_laenge.value():
            f.append("Teilelänge eingeben.")
        return f

    def _kopf_geaendert(self, *_):
        self.p = dict(self.p, werkstoff_id=self.k_werkstoff.currentText() or None, laenge=self.k_laenge.value() or None,
                      stueck=self.k_stueck.value() or None)
        if hasattr(self, "skizze"):
            self.skizze.laenge = self.p["laenge"]
            self._info_zeigen()
            self.rechnen()

    def _profil_gewaehlt(self, pid):
        if pid in self.k.profile and pid != self.p.get("profil_id"):
            form = self.k.profile[pid].get("form")
            if self.neu and self.k_form.currentText() not in (profil_neu.ALLE, form):     # eingetippt: Form folgt
                self.k_form.blockSignals(True)
                self.k_form.setCurrentText(form)
                self.k_form.blockSignals(False)
                self._form_gewaehlt(form)
            self.profil_setzen(pid)

    def profil_setzen(self, pid):
        """Anderes Profil: Querschnitt, Konturgrenzen, Enden, Naht, Seiten und Skizze passend neu aufbauen; die
        Eingaben bleiben (Seiten, die das Profil nicht hat, fallen auf die erste Fläche)."""
        e = self.eingaben()
        self.profil = self.k.profile[pid]
        self.p = dict(self.p, profil_id=pid)
        self.grenzen = rechnen.kontur_regel(rechnen.maschine(self.kopf, self.k), rechnen.wand_schneiden(self.profil))
        self.qs = sk.Querschnitt(self.profil)
        form = self.profil.get("form")
        self.kasten = form in ("Quadratrohr", "Rechteckrohr")
        for s_ in ("a", "b"):
            self.achse[s_].setEnabled(form != "Rundrohr")
            self.sattel[s_].setEnabled(form == "Rundrohr")
            if form != "Rundrohr":
                self.sattel[s_].setValue(0)
            self.richtung[s_].setEnabled(form in sw.MIT_RICHTUNG)
        self.naht_form = naht.form_von(self.profil)
        alt = self.naht_winkel
        neu_ = self._naht_winkel_bauen(self.naht_werte_roh())
        self.enden_raster.replaceWidget(alt, neu_)
        alt.deleteLater()
        self.naht_winkel = neu_
        for w_ in (self.naht_vorgabe, self.naht_quelle):
            w_.setEnabled(self.naht_form is not None)
        self.skizze.profil, self.skizze.qs = self.profil, self.qs
        # Konturen aus dem STEP-Import: für den neuen Querschnitt neu rechnen bzw. Umriss übertragen (3b)
        e, self._umstell_hinweise, _, _ = sw.konturen_umstellen(e, dict(self.profil, profil_id=pid))
        self.tabelle.setRowCount(0)
        for z in e["konturen"]:
            self.zeile_neu(z, rechnen_=False)
        if hasattr(self, "step_info") and hasattr(self, "_ende_step"):
            self._step_hinweis()
        self._info_zeigen()
        self.rechnen()

    def naht_werte_roh(self):
        """Gewählter Nahtwinkel (Bezug Breitseite oben) oder None."""
        w = getattr(self, "naht_winkel", None)
        if w is None:
            return None
        return NAHT_WAHL.get(w.currentText()) if isinstance(w, QComboBox) else w.value()

    def _naht_winkel_bauen(self, w0):
        if self.naht_form in ("Quadratrohr", "Rechteckrohr"):
            w = QComboBox()        # nur 0°/90°/180°/270° (Patrick 22.10.2026)
            w.addItems(list(NAHT_WAHL))
            if isinstance(w0, (int, float)):
                n90 = round(float(w0) / 90) % 4 * 90.0
                w.setCurrentText(next(t for t, v in NAHT_WAHL.items() if v == n90))
            w.currentTextChanged.connect(self.rechnen)
        else:
            w = QDoubleSpinBox()
            w.setRange(0, 359.9)
            w.setDecimals(1)
            w.setSuffix(" °")
            w.setWrapping(True)
            w.setValue(float(w0) if isinstance(w0, (int, float)) else 0.0)
            w.valueChanged.connect(self.rechnen)
        w.setToolTip("Lage der Naht von Ende A gesehen: 0° oben, 90° vorne (rechts), 180° unten, 270° hinten (links); "
                     "Rechteckrohr mit der Breitseite oben")
        w.setEnabled(self.naht_form is not None)
        return w

    # ------------------------------------------------------------------ STEP und Schweißnaht
    def _step_enden(self, e):
        """Gemessene Enden merken (gelten, solange Winkel, Achse, Sattel und Richtung bleiben) und anzeigen."""
        self._ende_step = {}
        for s in ("a", "b"):
            x = e.get(s) or {}
            gm = self.gemessen_text[s]
            if sw._z(x.get("gemessen")):
                self._ende_step[s] = (self._ende_werte(s), {k_: x[k_] for k_ in (
                    "gemessen", "huelle_gemessen", "form", "messprofil", "flaechen", "huelle") if x.get(k_) is not None})
                self.winkel[s].setStyleSheet("background: #E8F5E9;")
                gm.setText(f"<span style='color:#1E6B35'>gemessen {rechnen.zahl(x['gemessen'], 1)} mm"
                           + (f", {x['form']}" if x.get("form") else "")
                           + (" (3D-Ende, für andere Profile gerechnet)" if x.get("flaechen") else "") + "</span>")
            else:
                self.winkel[s].setStyleSheet("")
                gm.setText("<span style='color:#595959'>–</span>")

    def _step_hinweis(self):
        konturen = [self.tabelle.cellWidget(r, 0) for r in range(self.tabelle.rowCount())]
        step = self._ende_step or any(getattr(c, "step", None) for c in konturen) or \
            getattr(self, "_umstell_hinweise", None)
        if not step:
            self.step_info.setVisible(False)
            return
        text = ("Werte aus dem <b>STEP-Import</b> (grün): Es gelten die gemessenen Schnittlängen, solange Art und Maße "
                "einer Zeile bzw. eines Endes unverändert bleiben.")
        if getattr(self, "_umstell_hinweise", None):
            text += " <span style='color:#7A5A00'>Profil geändert: " + "; ".join(self._umstell_hinweise) + ".</span>"
        if self.aus_position:
            text += (" <span style='color:#7A5A00'>Diese Position wurde ohne Konturliste importiert (vor Version "
                     "0.6.29): Bohrungen und Konturen stehen mit Größe und Länge da, ihre Lage ist unbekannt (in der "
                     "Skizze verteilt). <b>STEP neu einlesen …</b> holt Lage, Seite und Maße aus der Datei.</span>")
        self.step_info.setText(text)
        self.step_info.setVisible(True)

    def naht_werte(self):
        """Nahtfelder der Position wie im Dialog Schweißnaht (Winkel im Bezug Breitseite oben)."""
        if self.naht_form is None:
            return {}
        v = self.naht_vorgabe.currentText()
        if v == naht.KEINE:
            return dict(naht_vorgabe=None, naht_winkel=None, naht_quelle=None)
        if v == naht.UNBEKANNT:
            return dict(naht_vorgabe=v, naht_winkel=None, naht_quelle=None)
        w = NAHT_WAHL[self.naht_winkel.currentText()] if isinstance(self.naht_winkel, QComboBox) else \
            naht.normieren(self.naht_winkel.value())
        return dict(naht_vorgabe=v, naht_winkel=w, naht_quelle=self.naht_quelle.currentText())

    def naht_geaendert(self):
        """Nahtfelder, wenn sie im Dialog geändert wurden (sonst leer: bestehende Werte bleiben unangetastet)."""
        neu = self.naht_werte()
        if neu == self._naht_start:
            return {}
        if not neu.get("naht_vorgabe"):
            neu["querschnitt_lage"] = None
        return neu

    def _naht_anzeigen(self):
        if not hasattr(self, "naht_info"):
            return None
        fest = self.naht_vorgabe.currentText() == naht.FEST and self.naht_form is not None
        self.naht_winkel.setEnabled(fest)
        self.naht_quelle.setEnabled(fest)
        if self.naht_form is None:
            self.naht_info.setText("<span style='color:#595959'>nur Rund-, Quadrat- und Rechteckrohr</span>")
            return None
        w = self.naht_werte()
        if fest:
            s = naht.seite(self.profil, w["naht_winkel"])
            self.naht_info.setText(f"<span style='color:#C0392B'>SN: {s['text']}</span> – Drehen gesperrt")
            return w["naht_winkel"]
        self.naht_info.setText("<span style='color:#595959'>" + (
            "unbekannt: wird nicht gedreht" if self.naht_vorgabe.currentText() == naht.UNBEKANNT else
            "frei: Optimierung darf um die eigene Achse drehen") + "</span>")
        return None

    def step_einlesen(self, messwerte=None):
        """STEP-Datei messen (oder fertige Messwerte) und die Eingaben daraus setzen. Mehrere Rohrteile: Auswahl,
        das Teil mit der Artikelnummer der Position zuerst. Ergebnis: True = übernommen."""
        if messwerte is None:
            if self.step_lesen is None:
                return False
            messwerte = self.step_lesen()
        teile = [m for m in messwerte or () if m.get("profilform") and float(m.get("laenge") or 0) > 0
                 and m.get("konturen_liste")]
        if not teile:
            QMessageBox.information(self, "STEP neu einlesen", "In der Datei wurde kein Rohrteil mit Konturliste "
                                    "gemessen.")
            return False
        teile.sort(key=lambda m: str(m.get("artikel")) != str(self.p.get("artikel")))
        m = teile[0]
        if len(teile) > 1 and str(m.get("artikel")) != str(self.p.get("artikel")):
            namen = [f"{t.get('artikel')} ({t.get('profilform')}, {t.get('laenge')} mm)" for t in teile]
            text, ok = QInputDialog.getItem(self, "STEP neu einlesen", "Welches Teil?", namen, 0, False)
            if not ok:
                return False
            m = teile[namen.index(text)]
        e = step_eingaben(m, self.profil)
        if not e:
            QMessageBox.information(self, "STEP neu einlesen", "Die Messung enthält keine Konturen und Enden.")
            return False
        self.aus_position = False
        self.eingaben_setzen(e, mit_messung=True)
        laenge = float(m.get("laenge") or 0)
        if isinstance(self.p.get("laenge"), (int, float)) and abs(laenge - self.p["laenge"]) > 0.5:
            QMessageBox.information(self, "STEP neu einlesen", f"Hinweis: Die Datei misst {rechnen.zahl(laenge, 1)} mm, "
                                    f"die Position hat {rechnen.zahl(self.p['laenge'], 1)} mm Teilelänge.")
        return True

    def zeichnung_pdf(self, pfad=None):
        """Zeichnung als PDF (zeichnung.py). Ohne pfad: in die Ablage des Angebots schreiben und öffnen."""
        from . import zeichnung
        self.rechnen()
        einst = getattr(self.parent(), "einst", None) or {}
        eingaben = self.eingaben()
        erg = sw.rechnen(eingaben, self.profil, self.grenzen, self.gewinde, self.maschine)

        def schreiben(ziel):
            zeichnung.zeichnung_pdf(ziel, self.kopf, self.p, self.profil,
                                    sw.mit_angenommener_richtung(ohne_3d(eingaben), self.profil), erg, self.naht_werte(), einst,
                                    self.schneidzeit())
        if pfad is not None:
            schreiben(pfad)
            return pfad
        seite = self.parent()
        if not hasattr(seite, "_ziel"):
            return None
        ziel = seite._ziel(f"Zeichnung Pos {self.p.get('pos') or ''} {self.p.get('artikel') or ''}".strip(), ".pdf")
        return seite._schreiben("Zeichnung", ziel, schreiben)

    # ------------------------------------------------------------------ Eingaben
    def zeile_neu(self, z, rechnen_=True):
        self.tabelle.blockSignals(True)
        r = self.tabelle.rowCount()
        self.tabelle.insertRow(r)
        art = QComboBox()
        art.addItems(sw.ARTEN)
        art.setCurrentText(z.get("art") or sw.BOHRUNG)
        art.currentTextChanged.connect(lambda _=None, art=art: self._art_geaendert(art))
        self.tabelle.setCellWidget(r, 0, art)
        werte = [z.get("anzahl")] + [z.get(k_) for k_, _ in sw.MASSE.get(art.currentText(), ())]
        werte += [None] * (4 - len(werte)) + [z.get("x"), z.get("abstand")]
        for c, v in enumerate(werte, start=1):
            self.tabelle.setItem(r, c, QTableWidgetItem(rechnen.zahl(v, 3) if isinstance(v, (int, float)) else
                                                        v if isinstance(v, str) else ""))
        seite = QComboBox()
        seite.addItems(sk.seiten_anzeige(self.qs))
        if self.qs.r:
            seite.setEditable(True)         # Rundrohr: auch freier Winkel, z. B. 45°
            seite.setToolTip("Winkel am Umfang, Blick von Ende A: 0° oben, 90° vorne, 180° unten, 270° hinten")
            w = sk.winkel_aus_text(z.get("seite"))
            seite.setCurrentText(sk.winkel_text(w) if w is not None else self.qs.seiten()[0])
        else:
            seite.setToolTip("Fläche, auf der die Kontur liegt, von Ende A gesehen (siehe Ansicht von A in der Skizze)"
                             + ("; Rechteck- und Quadratrohr nur 0°, 90°, 180°, 270°" if self.kasten else ""))
            seite.setCurrentText(sk.seite_anzeige(self.qs, z.get("seite") if z.get("seite") in self.qs.seiten()
                                                  else self.qs.seiten()[0]))
        seite.currentTextChanged.connect(self.rechnen)
        self.tabelle.setCellWidget(r, SEITE_SPALTE, seite)
        quer = QTableWidgetItem(rechnen.zahl(z["q"], 3) if isinstance(z.get("q"), (int, float)) else "")
        if self.qs.r:
            quer.setFlags(quer.flags() & ~Qt.ItemIsEditable)
            quer.setToolTip("Rundrohr: Lage am Umfang über den Winkel in der Spalte Seite")
        else:
            quer.setToolTip("Versatz quer zur Mitte der Fläche [mm] (+ in Richtung der nächsten Fläche)")
        self.tabelle.setItem(r, QUER_SPALTE, quer)
        d3 = QTableWidgetItem("")
        d3.setFlags((d3.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
        d3.setCheckState(Qt.Checked if z.get("d3") else Qt.Unchecked)
        d3.setToolTip(SPALTEN_HILFE[D3_SPALTE])
        self.tabelle.setItem(r, D3_SPALTE, d3)
        for spalte, schl in ((NL_SPALTE, "neigung_l"), (NQ_SPALTE, "neigung_q")):
            cb = QComboBox()
            cb.setEditable(True)
            cb.addItems(SCHNELLWAHL)
            v = z.get(schl)
            cb.setCurrentText(winkel_anzeige(v) if isinstance(v, (int, float)) else str(v) if v else "0°")
            cb.setToolTip(SPALTEN_HILFE[spalte] + ". Schnellauswahl oder Zahl eingeben; über der Grenze der Maschine "
                                                  "wird begrenzt")
            cb.currentTextChanged.connect(self.rechnen)
            self.tabelle.setCellWidget(r, spalte, cb)
        self.tabelle.setItem(r, TEXT_SPALTE, QTableWidgetItem(z.get("text") or ""))
        g = QComboBox()
        g.addItems([GEWINDE_AUTO, GEWINDE_KEIN] + [n for n, _ in self.gewinde or KERNLOCH])
        g.setToolTip(SPALTEN_HILFE[GEWINDE_SPALTE])
        if "gewinde" in z:
            g.setCurrentText(z["gewinde"] or GEWINDE_KEIN)
        g.currentTextChanged.connect(self.rechnen)
        self.tabelle.setCellWidget(r, GEWINDE_SPALTE, g)
        self._kopf_hinweise(r)
        art.quer = bool(z.get("quer"))
        # echter Umriss (Sonderkontur, Gravur aus dem STEP-Import): bleibt, solange die Art bleibt
        extra = {k_: z[k_] for k_ in ("umriss", "waende", "tiefe", "messprofil") if z.get(k_) is not None}
        art.extra = (art.currentText(), extra) if extra else None
        if sw._z(z.get("gemessen")):        # aus dem STEP-Import: gemessene Länge, solange die Maße bleiben
            art.step = (art.currentText(), self._mass_texte(r), {k_: z[k_] for k_ in ("gemessen", "huelle_gemessen")
                                                                 if z.get(k_) is not None})
            if sw.anderer_querschnitt(z, self.profil):      # nicht umrechenbar: gelb zum Prüfen
                art.setToolTip(f"gemessen an einem anderen Querschnitt ({str(z['messprofil']).split('|')[0]}), nicht "
                               f"umrechenbar: gemessene Schnittlänge {rechnen.zahl(z['gemessen'], 1)} mm gilt, bitte "
                               "prüfen")
                self.tabelle.item(r, 1).setBackground(stil.farbe("#FFF4CC"))
            else:
                art.setToolTip(f"aus dem STEP-Import: gemessene Schnittlänge {rechnen.zahl(z['gemessen'], 1)} mm "
                               "(gilt, solange Art und Maße unverändert bleiben)")
                self.tabelle.item(r, 1).setBackground(stil.farbe("#E8F5E9"))
        self.tabelle.blockSignals(False)
        if rechnen_:
            self.rechnen()

    def _mass_texte(self, r):
        return tuple(self.tabelle.item(r, 2 + i).text() for i in range(3))

    def _ende_werte(self, s):
        return (self.winkel[s].value(), self.achse[s].currentText(), self.sattel[s].value(),
                self.richtung[s].currentText(), self.winkel_b[s].value())

    def _art_geaendert(self, combo):
        for r in range(self.tabelle.rowCount()):
            if self.tabelle.cellWidget(r, 0) is combo:
                self._kopf_hinweise(r)
        self.rechnen()

    def _kopf_hinweise(self, r):
        """Tooltip je Maßzelle: welches Maß die Art an dieser Stelle braucht."""
        art = self.tabelle.cellWidget(r, 0).currentText()
        masse = sw.MASSE.get(art, ())
        g = self.tabelle.cellWidget(r, GEWINDE_SPALTE)
        if g is not None:
            g.setEnabled(art in sw.MIT_GEWINDE)
        for i in range(3):
            it = self.tabelle.item(r, 2 + i)
            if it is not None:
                it.setToolTip(masse[i][1] if i < len(masse) else "nicht benötigt")
                it.setFlags(it.flags() | Qt.ItemIsEditable if i < len(masse) else it.flags() & ~Qt.ItemIsEditable)
                if i >= len(masse):
                    it.setText("")

    def _entfernen(self):
        for r in sorted({i.row() for i in self.tabelle.selectedIndexes()}, reverse=True):
            self.tabelle.removeRow(r)
        self.rechnen()

    def pruefung(self, eingaben=None):
        """Befunde der Fertigungsprüfung (dfm.rohr) für die aktuellen Eingaben und Teilelänge."""
        p = dict(self.p, technik=sw.speichern(eingaben or self.eingaben()),
                 laenge=self.k_laenge.value() if hasattr(self, "k_laenge") else self.p.get("laenge"))
        return dfm.rohr(p, self.profil, self.maschine, (self.tabellen or {}).get("pruefregeln"))

    def _pruefung_zeigen(self, eingaben):
        farbe = {dfm.FEHLER: "#B42318", dfm.WARNUNG: "#B26A00", dfm.HINWEIS: "#7A5A00"}
        return [f"<span style='color:{farbe[b.stufe]}'>Prüfung {b.stufe}: {b.zeile()}</span>"
                for b in self.pruefung(eingaben)]

    def eingaben(self):
        konturen = []
        for r in range(self.tabelle.rowCount()):
            art = self.tabelle.cellWidget(r, 0).currentText()
            z = dict(art=art, anzahl=_zahl(self.tabelle.item(r, 1).text()))
            for i, (k_, _) in enumerate(sw.MASSE.get(art, ())):
                text = self.tabelle.item(r, 2 + i).text()
                z[k_] = text.strip() if k_ == "punkte" else _zahl(text)
            x = _zahl(self.tabelle.item(r, LAGE_SPALTE).text())
            if x is not None:
                z["x"] = x
            ab = _zahl(self.tabelle.item(r, ABSTAND_SPALTE).text())
            if ab:
                z["abstand"] = ab
            seite = sk.seite_name(self.qs, self.tabelle.cellWidget(r, SEITE_SPALTE).currentText())
            if self.qs.r:
                w = sk.winkel_aus_text(seite)
                if w:
                    z["seite"] = w
            elif seite != self.qs.seiten()[0]:
                z["seite"] = seite
            q = _zahl(self.tabelle.item(r, QUER_SPALTE).text())
            if q and not self.qs.r:
                z["q"] = q
            t = self.tabelle.item(r, TEXT_SPALTE).text().strip()
            if t:
                z["text"] = t
            if self.tabelle.item(r, D3_SPALTE).checkState() == Qt.Checked:
                z["d3"] = True
            g = self.tabelle.cellWidget(r, GEWINDE_SPALTE).currentText()
            if art in sw.MIT_GEWINDE and g != GEWINDE_AUTO:
                z["gewinde"] = "" if g == GEWINDE_KEIN else g
            for spalte, schl in ((NL_SPALTE, "neigung_l"), (NQ_SPALTE, "neigung_q")):
                text = self.tabelle.cellWidget(r, spalte).currentText()
                try:
                    v = dreid.winkel_zahl(text)
                except ValueError:
                    v = text                    # ungültig: schneidweg.rechnen meldet den Fehler
                if v:
                    z[schl] = v
            combo = self.tabelle.cellWidget(r, 0)
            if getattr(combo, "quer", False):
                z["quer"] = True
            step = getattr(combo, "step", None)
            if step and step[0] == art and step[1] == self._mass_texte(r):
                z.update(step[2])
            extra = getattr(combo, "extra", None)
            if extra and extra[0] == art:
                z.update(extra[1])
            konturen.append(z)
        enden = {s: dict(winkel=self.winkel[s].value(), achse=self.achse[s].currentText(),
                         sattel=self.sattel[s].value() or None,
                         richtung=sw.RICHTUNGEN.get(self.richtung[s].currentText())) for s in ("a", "b")}
        for s in ("a", "b"):            # zweiachsig: Winkel über Höhe und Breite, winkel = Gesamtneigung der Ebene
            if enden[s]["achse"] == sw.ACHSE_ZWEI:
                w_h, w_b = self.winkel[s].value(), self.winkel_b[s].value()
                enden[s].update(winkel=round(sw.gesamtwinkel(w_h, w_b), 2), winkel_h=w_h, winkel_b=w_b)
        for s, (werte, gemessen) in self._ende_step.items():
            if self._ende_werte(s) == werte:
                enden[s].update(gemessen)
        for s in ("a", "b"):
            if self.ende_3d[s].isChecked():
                enden[s]["d3"] = True
        out = dict(enden, gravur=self.gravur.value() or None, konturen=konturen)
        if self.d3.isChecked():
            out["d3"] = True
        if self.biegerohr:
            out["biegerohr"] = self.biegerohr
        return out

    # ------------------------------------------------------------------ Ergebnis
    def rechnen(self, *_):
        self._rechnen()
        if getattr(self, "editor", None) is not None:
            self.editor.geaendert()

    def _rechnen(self):
        eingaben = self.eingaben()
        erg = sw.rechnen(eingaben, self.profil, self.grenzen, self.gewinde, self.maschine)
        self.ergebnis = erg
        t = self.ergebnis_tabelle
        t.setRowCount(len(erg["schritte"]))
        for r, s in enumerate(erg["schritte"]):
            werte = (s["text"] + (" (Schätzung)" if s["schaetzung"] else ""), str(s["anzahl"]),
                     rechnen.zahl(s["laenge_stueck"], 1), rechnen.zahl(s["laenge"], 1), str(s["einstiche"]),
                     "–" if s["huelle"] is None else rechnen.zahl(s["huelle"], 1), s["klasse"])
            for c, v in enumerate(werte):
                it = QTableWidgetItem(v)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    it.setToolTip(v)        # schmale Spalte: ganzer Text beim Zeigen
                t.setItem(r, c, it)
        f = erg["felder"]
        zeit = self.schneidzeit()
        teile = [f"<b>Schneidweg {rechnen.zahl(f['schneidweg'], 1)} mm</b>, {f['einstiche']} Einstiche "
                 f"(Enden {rechnen.zahl(f['a_schnitt'], 1)} + {rechnen.zahl(f['b_schnitt'], 1)} mm, Innenkonturen "
                 f"{rechnen.zahl(f['innen'], 1)} mm: klein {f['klein_n']}, mittel {f['mittel_n']}, groß {f['gross_n']})",
                 f"Schneidzeit je Teil {rechnen.zahl(zeit, 1)} s (Schneiddaten der Maschine)" if zeit is not None
                 else "<span style='color:#7A5A00'>Keine Schneiddaten für Maschine, Werkstoff und Wandstärke: "
                      "Schneidzeit von Hand eintragen.</span>"]
        if f.get("gewinde_vorschlag"):
            teile.append(f"<span style='color:#7A5A00'>Vorschlag: Bohrungen {f['bohrungen']} passen zu Kernlöchern "
                         f"für <b>{f['gewinde_vorschlag']}</b>. Mit OK kommt das Gewinde bestätigt in die Position "
                         "(Spalte Gewinde: anderes oder kein Gewinde wählen; später änderbar in <i>Bohrungen "
                         "prüfen</i>).</span>")
        for h in erg.get("hinweise") or ():
            teile.append(f"<span style='color:#7A5A00'>{h}</span>")
        if erg["schaetzung"]:
            teile.append("<span style='color:#7A5A00'>Gehrung an diesem Profil: Schnittlänge geschätzt (gerade "
                         "Schnittlänge / cos Winkel).</span>")
        if not sw._z(self.p.get("zeit_manuell")) == 0:
            teile.append("<span style='color:#7A5A00'>Die Position hat eine Schneidzeit von Hand; sie gilt weiter, "
                         "bis sie in der Positionsliste gelöscht wird.</span>")
        teile += self._d3_zeigen(eingaben)
        teile += self._pruefung_zeigen(eingaben)
        fehler = erg["fehler"] + self.kopf_fehler()
        if fehler:
            teile.append("<span style='color:#B42318'>" + "<br>".join(fehler) + "</span>")
        self.summe.setText("<br>".join(teile))
        if hasattr(self, "skizze"):
            self.skizze.naht = self._naht_anzeigen()
            self.skizze.zeigen(sw.mit_angenommener_richtung(ohne_3d(eingaben), self.profil), erg)
            self._auswahl_tabelle()
        if hasattr(self, "ok_knopf"):
            self.ok_knopf.setEnabled(not fehler)

    # ------------------------------------------------------------------ Vorlagen und Kopieren
    def eingaben_setzen(self, e, anhaengen=False, mit_messung=False):
        """Enden, Gravur und Konturen setzen (anhaengen: nur Konturen dazu; mit_messung: gemessene Werte des
        STEP-Imports behalten)."""
        e = sw.lesen(json.dumps(e if mit_messung else ohne_messung(e))) if isinstance(e, dict) else sw.lesen(e)
        if mit_messung:
            e, self._umstell_hinweise, _, _ = sw.konturen_umstellen(e, dict(self.profil,
                                                                             profil_id=self.p.get("profil_id")))
        if not anhaengen:
            for s in ("a", "b"):
                x = e.get(s) or {}
                zwei = x.get("achse") == sw.ACHSE_ZWEI
                self.winkel[s].setValue(sw._z(x.get("winkel_h" if zwei else "winkel")))
                self.winkel_b[s].setValue(sw._z(x.get("winkel_b")) if zwei else 0)
                if x.get("achse") in sw.ACHSEN_WAHL:
                    self.achse[s].setCurrentText(x["achse"])
                self.sattel[s].setValue(sw._z(x.get("sattel")) if self.sattel[s].isEnabled() else 0)
                self.richtung[s].setCurrentText(next((t for t, v in sw.RICHTUNGEN.items()
                                                      if v == x.get("richtung")), sw.AUTOMATISCH))
            self.gravur.setValue(sw._z(e.get("gravur")))
            self._step_enden(e)
            self.tabelle.setRowCount(0)
        for z in e.get("konturen") or ():
            self.zeile_neu(z, rechnen_=False)
        self._step_hinweis()
        self.rechnen()

    def vorlagen(self):
        v = self.db.einstellung(VORLAGEN) if self.db is not None else None
        return v if isinstance(v, dict) else {}

    def vorlage_speichern(self, name):
        name = (name or "").strip()
        if not name or self.db is None:
            return False
        v = self.vorlagen()
        v[name] = dict(ohne_messung(self.eingaben()), profilform=self.profil.get("form"))
        self.db.einstellung_setzen(VORLAGEN, v)
        return True

    def vorlage_laden(self, name):
        e = self.vorlagen().get(name)
        if not e:
            return False
        self.eingaben_setzen(e)
        return True

    def vorlage_loeschen(self, name):
        v = self.vorlagen()
        if v.pop(name, None) is None:
            return False
        self.db.einstellung_setzen(VORLAGEN, v)
        return True

    def _vorlagen_menue(self):
        m = self.vorlagen_knopf.menu()
        m.clear()
        m.addAction("Als Vorlage speichern …", self._vorlage_speichern_fragen)
        namen = sorted(self.vorlagen(), key=str.lower)
        laden, loeschen = m.addMenu("Vorlage laden"), m.addMenu("Vorlage löschen")
        for n in namen:
            form = self.vorlagen()[n].get("profilform")
            laden.addAction(n + (f"  ({form})" if form and form != self.profil.get("form") else ""),
                            lambda n=n: self.vorlage_laden(n))
            loeschen.addAction(n, lambda n=n: self._vorlage_loeschen_fragen(n))
        laden.setEnabled(bool(namen))
        loeschen.setEnabled(bool(namen))

    def _vorlage_speichern_fragen(self):
        name, ok = QInputDialog.getText(self, "Vorlage speichern", "Name der Vorlage (gleicher Name ersetzt sie):")
        if ok and name.strip():
            self.vorlage_speichern(name)

    def _vorlage_loeschen_fragen(self, name):
        if QMessageBox.question(self, "Vorlage löschen", f"Vorlage „{name}“ löschen?") == QMessageBox.Yes:
            self.vorlage_loeschen(name)

    def kopierbare(self):
        """[(Text, Position)] der anderen Positionen mit Konturen im Rechner."""
        out = []
        for x in self.positionen:
            k_ = sw.lesen(x.get("technik")).get("konturen")
            if k_:
                out.append((f"Pos. {x.get('pos') or ''} {x.get('artikel') or ''} – {x.get('profil_id') or ''}, "
                            f"{len(k_)} Zeile(n)".replace("  ", " "), x))
        return out

    def konturen_kopieren(self, position):
        """Konturen einer anderen Position anhängen (Seiten, die das Profil nicht hat, fallen auf die erste)."""
        k_ = sw.lesen(position.get("technik")).get("konturen")
        if not k_:
            return 0
        self.eingaben_setzen(dict(konturen=k_), anhaengen=True)
        return len(k_)

    def _kopieren_waehlen(self):
        liste = self.kopierbare()
        if not liste:
            QMessageBox.information(self, "Konturen kopieren", "Keine andere Position dieses Angebots hat Konturen im "
                                    "Schneidweg-Rechner.")
            return
        text, ok = QInputDialog.getItem(self, "Konturen kopieren", "Konturen anhängen von:", [t for t, _ in liste], 0,
                                        False)
        if ok:
            self.konturen_kopieren(dict(liste)[text])

    # ------------------------------------------------------------------ Skizze <-> Tabelle
    def _auswahl_tabelle(self):
        zeilen = sorted({i.row() for i in self.tabelle.selectedIndexes()})
        self.skizze.markieren(zeilen[0] if zeilen else None)
        self._spalten_erklaeren(zeilen[0] if zeilen else None)

    def _spalten_erklaeren(self, zeile):
        """Überschriften Maß 1–3 und Erklärung unter der Tabelle für die Art der markierten Zeile."""
        art = self.tabelle.cellWidget(zeile, 0).currentText() if zeile is not None and \
            0 <= zeile < self.tabelle.rowCount() else None
        masse = sw.MASSE.get(art, ())
        for i in range(3):
            titel = (f"{masse[i][1]} [mm]" if masse[i][0] != "punkte" else masse[i][1]) if i < len(masse) else \
                ("–" if art else KONTUR_SPALTEN[2 + i])
            self.tabelle.horizontalHeaderItem(2 + i).setText(titel)
        # eine Zeile unter der Tabelle (Platz für die Konturen); Lage, Seite und Versatz im Tooltip
        self.erklaerung.setToolTip(LAGE_HILFE)
        if art:
            self.erklaerung.setText(f"<b>Zeile {zeile + 1}, {art}</b>: {ART_HILFE.get(art, '')}")
        else:
            self.erklaerung.setText("<span style='color:#595959'>Zeile markieren: die Überschriften Maß 1–3 zeigen dann, "
                                    "welches Maß die Konturart braucht (z. B. Bohrung Maß 1 = Ø d, Langloch Maß 1 = "
                                    "Länge l, Maß 2 = Breite b).</span>")

    def _auswahl_skizze(self, zeile):
        if 0 <= zeile < self.tabelle.rowCount():
            self.tabelle.selectRow(zeile)

    def _verschoben(self, zeile, neu):
        """Kontur in der Skizze gezogen: Lage, Abstand, Seite und Versatz in die Tabelle schreiben."""
        if not 0 <= zeile < self.tabelle.rowCount():
            return
        self.tabelle.blockSignals(True)
        for name, spalte in (("x", LAGE_SPALTE), ("abstand", ABSTAND_SPALTE), ("q", QUER_SPALTE)):
            if name in neu and not (name == "q" and self.qs.r):
                v = neu[name]
                self.tabelle.item(zeile, spalte).setText(rechnen.zahl(v, 3) if v is not None else "")
        if "seite" in neu:
            cb = self.tabelle.cellWidget(zeile, SEITE_SPALTE)
            cb.blockSignals(True)
            if self.qs.r:
                cb.setCurrentText(sk.winkel_text(neu["seite"] or 0.0))
            else:
                cb.setCurrentText(sk.seite_anzeige(self.qs, neu["seite"] or self.qs.seiten()[0]))
            cb.blockSignals(False)
        self.tabelle.blockSignals(False)
        self.tabelle.selectRow(zeile)
        self.rechnen()

    def _d3_zeigen(self, eingaben):
        """3D: Häkchen je Gehrung nur mit Gehrung und 3D am Bauteil, Zeile über den Enden (Maschine, Grenzen),
        Status der Position (dreid.pruefen). Ergebnis: Texte für die Zusammenfassung."""
        an = self.d3.isChecked()
        for s in ("a", "b"):
            self.ende_3d[s].setEnabled(an and (self.winkel[s].value() > 0 or self.winkel_b[s].value() > 0)
                                       and not self.sattel[s].value())
        m = self.maschine or {}
        lo, hi = dreid.grenzen(m)
        if not dreid.kann_3d(m):
            self.d3_info.setText(f"<span style='color:{'#B42318' if an else '#595959'}'>Maschine "
                                 f"{m.get('maschinen_id') or '–'} kann keine 3D-Bearbeitung (Einstellungen › Stammdaten › "
                                 "Maschinen: 3D: Bearbeitung verfügbar)</span>")
        else:
            self.d3_info.setText(f"<span style='color:#595959'>Maschine {m.get('maschinen_id')}: Schwenkwinkel "
                                 f"{dreid._zahl(lo, 0)}° bis +{dreid._zahl(hi, 0)}°, Greifmaß "
                                 f"{rechnen.zahl(dreid.greifmass(m), 0)} mm am letzten Teil der Stange</span>")
        if not an:
            return []
        p = dict(self.p, **(self.ergebnis or {}).get("felder", {}), technik=sw.speichern(eingaben))
        st = dreid.pruefen(p, m)
        return [f"<span style='color:{'#B42318' if st.startswith('FEHLER') else '#7A5A00'}'>3D: {st}</span>"] \
            if st else []

    def schneidzeit(self):
        """Schneidzeit je Teil [s] mit den neuen Werten oder None ohne Schneiddaten (mit 3D-Mehrzeit)."""
        p = dict(self.p, **self.ergebnis["felder"], technik=sw.speichern(self.eingaben()))
        return rechnen.schneidzeit(p, self.kopf, rechnen.wand_schneiden(self.profil), self.tabellen, self.k)[2]

    def _ok(self):
        self.rechnen()
        if not self.ergebnis["fehler"] and not self.kopf_fehler():
            self.accept()


def ohne_3d(e):
    """Eingaben für Skizze und Zeichnung: ohne Häkchen am Bauteil zählt „3D“ an Konturen nicht (2D wie gerechnet)."""
    if e.get("d3") is True:
        return e
    return dict(e, konturen=[{k: v for k, v in z.items() if k != "d3"} for z in e.get("konturen") or ()])


def winkel_anzeige(w):
    """Neigung für die Eingabe: +30°, −45°, 0°."""
    return "0°" if not w else (f"+{dreid._zahl(w)}°" if w > 0 else f"{dreid._zahl(w)}°")


def step_eingaben(m, profil):
    """Eingaben des Rechners aus einer STEP-Messung (Messwerte einer Datei) für dieses Profil."""
    from .step import rechner_eingaben
    return rechner_eingaben(m, profil.get("form") or m.get("profilform"), profil.get("a") or m.get("abm_a"),
                            profil.get("b") or m.get("abm_b"))


def ohne_messung(e):
    """Eingaben ohne gemessene Werte des STEP-Imports (Vorlagen und kopierte Konturen rechnen mit den Formeln)."""
    weg = ("gemessen", "huelle_gemessen", "form")
    out = {k_: v for k_, v in e.items() if k_ not in ("a", "b", "konturen", "quelle")}
    for s in ("a", "b"):
        if isinstance(e.get(s), dict):
            out[s] = {k_: v for k_, v in e[s].items() if k_ not in weg}
    out["konturen"] = [{k_: v for k_, v in z.items() if k_ not in weg} for z in e.get("konturen") or ()]
    return out


def gewinde_liste(tabellen):
    """[(Gewinde, Kernloch-Ø)] aus den Stammdaten Gewinde (leer: übliche Kernlöcher, wie der STEP-Import)."""
    return [(g["gewinde"], g["kernloch"]) for g in (tabellen.get("gewinde") or ())
            if g.get("gewinde") and isinstance(g.get("kernloch"), (int, float))] or None
