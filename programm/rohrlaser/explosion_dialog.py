"""Explosionsfenster (Auftrag Patrick 20.11.2026 „Explosionsansicht erweitern und professionalisieren“): Seitenfenster
neben jeder 3D-Ansicht mit Stärke, Richtung, Ebenen (Unterbaugruppen), Überlappung, Verbindungslinien,
Positionsnummern/Beschriftung, Teile von Hand ziehen (frei oder entlang X/Y/Z) und mit Zahlen verschieben, Fixieren,
Zurücksetzen, Rückgängig/Wiederholen, Animation (auseinander, zusammen, schrittweise, Montagereihenfolge, Pause,
Tempo), gespeicherte Ansichten mit Namen und Kamera, Explosionszeichnung als PDF/Bild mit Stückliste (auch in die
Angebotsakte). Nur Anzeige: Geometrie, Lage im Export (= STEP) und Kalkulation bleiben genau gleich; die
Verschiebungen sind eigene Anzeigedaten (explosion.Stand)."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSlider, QVBoxLayout)

from . import explosion
from .explosion_zeichnung import zeichnung_speichern

ACHSEN = {"Frei (in der Bildebene)": "frei", "Nur X": "x", "Nur Y": "y", "Nur Z": "z"}
ANIMATIONEN = (("Auseinander", "auseinander"), ("Zusammen", "zusammen"), ("Schrittweise", "schrittweise"),
               ("Montagereihenfolge", "montage"))


# ---------------------------------------------------------------- Ablage der gespeicherten Ansichten
def ansichten(a):
    """Gespeicherte Explosionsansichten der Ansicht (Baugruppe: bg['explosionen'], Satz: Satzdaten; sonst nur
    solange das Fenster offen ist)."""
    ab = getattr(a, "explosion_ablage", None)
    if ab is not None:
        try:
            return explosion.ansichten_lesen(ab[0]())
        except Exception:       # noqa: BLE001 – nur Anzeige
            return []
    return explosion.ansichten_lesen(getattr(a, "_explo_ansichten", []))


def ablage_einhaengen(a, daten, seite=None):
    """Gespeicherte Ansichten unter daten['explosionen'] (Baugruppe: bg, gespeichert mit baugruppe.speichern; Satz:
    Satzdaten) und die Angebotsakte des Angebots (seite: Angebotsseite mit f und kopf)."""
    hol = daten if callable(daten) else (lambda: daten)        # Funktion: das Fenster ersetzt sein dict später
    a.explosion_ablage = (lambda: hol().get("explosionen") or [],
                          lambda liste: hol().__setitem__("explosionen", liste))
    f, kopf = getattr(seite, "f", None), getattr(seite, "kopf", None)
    if f is not None and kopf and hasattr(f, "angebot_ordner"):
        a.explosion_akte = lambda: (f.angebot_ordner(kopf), kopf.get("nummer"))


def ansichten_schreiben(a, liste):
    ab = getattr(a, "explosion_ablage", None)
    if ab is not None:
        ab[1](liste)
    else:
        a._explo_ansichten = liste


def stueckliste(a):
    """Stückliste der gezeigten Explosion: Zeilen wie explosion.stueckliste (ohne Teile: Nummer und Name)."""
    el = a.wahl.elemente() if a.voll is not None else None
    if el is None:
        return []
    ids = []
    for k in el.koerper_von:
        if k not in ids and k not in a.wahl.versteckt:
            ids.append(k)
    teil = getattr(a, "explosion_teil", None)
    paare = []
    for k in ids:
        q = None
        if teil is not None:
            try:
                q = teil(k)
            except Exception:       # noqa: BLE001
                q = None
        if q is None:
            q = dict(id=k, bezeichnung=(a.wahl.koerper_name(k) if a.wahl.koerper_name else None) or str(k))
        paare.append((a._explo_nummer(k, ids), q))
    zeilen = explosion.stueckliste(paare)

    def schl(z):
        n = str(z["nr"])
        return (0, int(n)) if n.isdigit() else (1, n)
    return sorted(zeilen, key=schl)


def in_akte_legen(a, name=None):
    """Explosionszeichnung als PDF und PNG in die Angebotsakte (Technische_Daten) des Angebots legen; von dort nimmt
    sie die Dokumentenablage mit. Ergebnis: [Pfade] oder None (kein Angebot bekannt)."""
    akte = getattr(a, "explosion_akte", None)
    ziel = akte() if akte is not None else None
    if not ziel:
        return None
    from . import akte_ablage
    from .angebotsordner import sauber
    o = akte_ablage.ordner(ziel[0]) / akte_ablage.TECHNIK
    stamm = sauber(f"Explosionszeichnung {name or a.titel or 'Baugruppe'}").replace(" ", "_")
    return [zeichnung_speichern(a, o / f"{stamm}.pdf"), zeichnung_speichern(a, o / f"{stamm}.png")]


# ---------------------------------------------------------------- Fenster
class ExplosionsDialog(QDialog):
    """Seitenfenster „Explosion einstellen“ (nicht modal, eines je Ansicht). Jede Änderung wirkt sofort."""

    def __init__(self, ansicht, parent=None):
        super().__init__(parent or ansicht)
        self.setWindowTitle("Explosionsansicht")
        self.setWindowFlag(Qt.Tool, True)
        self.a = ansicht
        self._laedt = False
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Nur Anzeige: Teile, Lage im Export (laut STEP) und Kalkulation bleiben genau gleich."))

        g = QGroupBox("Auseinanderziehen")
        gl = QGridLayout(g)
        self.staerke = QSlider(Qt.Horizontal)
        self.staerke.setRange(0, int(explosion.FAKTOR_MAX * 100))
        self.staerke_text = QLabel()
        self.richtung = QComboBox()
        self.richtung.addItems(list(explosion.RICHTUNGEN))
        self.ebenen = QCheckBox("Nach Unterbaugruppen (Ebenen)")
        self.ueberlappung = QCheckBox("Überlappung vermeiden")
        self.linien = QCheckBox("Verbindungslinien zur Einbaulage")
        self.beschriftung = QComboBox()
        self.beschriftung.addItems(list(explosion.BESCHRIFTUNGEN))
        gl.addWidget(QLabel("Stärke"), 0, 0)
        gl.addWidget(self.staerke, 0, 1)
        gl.addWidget(self.staerke_text, 0, 2)
        gl.addWidget(QLabel("Richtung"), 1, 0)
        gl.addWidget(self.richtung, 1, 1, 1, 2)
        gl.addWidget(self.ebenen, 2, 0, 1, 3)
        gl.addWidget(self.ueberlappung, 3, 0, 1, 3)
        gl.addWidget(self.linien, 4, 0, 1, 3)
        gl.addWidget(QLabel("Beschriftung"), 5, 0)
        gl.addWidget(self.beschriftung, 5, 1, 1, 2)
        lay.addWidget(g)

        g = QGroupBox("Teile von Hand")
        gl = QGridLayout(g)
        self.ziehen = QCheckBox("Teile mit der Maus ziehen")
        self.ziehen.setToolTip("Linke Maustaste auf ein Teil und ziehen; gewählte Teile gehen zusammen. Fixierte "
                               "Teile bleiben stehen.")
        self.achse = QComboBox()
        self.achse.addItems(list(ACHSEN))
        gl.addWidget(self.ziehen, 0, 0, 1, 2)
        gl.addWidget(self.achse, 0, 2, 1, 2)
        self.zahlen = []
        for i, n in enumerate("XYZ"):
            s = QDoubleSpinBox()
            s.setRange(-100000.0, 100000.0)
            s.setDecimals(1)
            s.setSuffix(" mm")
            s.setPrefix(f"{n} ")
            gl.addWidget(s, 1, i)
            self.zahlen.append(s)
        setzen = QPushButton("Setzen")
        setzen.setToolTip("Eigenen Versatz der gewählten Teile auf diese Werte setzen")
        gl.addWidget(setzen, 1, 3)
        self.k_fix = QPushButton("Fixieren")
        self.k_los = QPushButton("Lösen")
        self.k_null = QPushButton("Gewählte zurück")
        self.k_alle = QPushButton("Alles zurücksetzen")
        for i, k in enumerate((self.k_fix, self.k_los, self.k_null, self.k_alle)):
            gl.addWidget(k, 2, i)
        self.k_zurueck = QPushButton("Rückgängig")
        self.k_vor = QPushButton("Wiederholen")
        gl.addWidget(self.k_zurueck, 3, 0, 1, 2)
        gl.addWidget(self.k_vor, 3, 2, 1, 2)
        lay.addWidget(g)

        g = QGroupBox("Animation")
        gl = QGridLayout(g)
        for i, (t, art) in enumerate(ANIMATIONEN):
            k = QPushButton(t)
            k.clicked.connect(lambda _=False, art=art: self.animieren(art))
            gl.addWidget(k, 0, i)
        self.k_pause = QPushButton("Pause / Weiter")
        self.tempo = QDoubleSpinBox()
        self.tempo.setRange(0.2, 10.0)
        self.tempo.setSingleStep(0.1)
        self.tempo.setValue(1.5)
        self.tempo.setSuffix(" s")
        self.tempo.setToolTip("Dauer der Animation (schrittweise: je Teil)")
        gl.addWidget(self.k_pause, 1, 0, 1, 2)
        gl.addWidget(QLabel("Dauer"), 1, 2)
        gl.addWidget(self.tempo, 1, 3)
        lay.addWidget(g)

        g = QGroupBox("Gespeicherte Ansichten (mit Blickrichtung)")
        gl = QGridLayout(g)
        self.liste = QComboBox()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name, z. B. Montage Seite links")
        k_merk, k_lade, k_weg = QPushButton("Speichern"), QPushButton("Zeigen"), QPushButton("Löschen")
        gl.addWidget(self.name, 0, 0, 1, 2)
        gl.addWidget(k_merk, 0, 2)
        gl.addWidget(self.liste, 1, 0, 1, 2)
        z = QHBoxLayout()
        z.addWidget(k_lade)
        z.addWidget(k_weg)
        gl.addLayout(z, 1, 2)
        lay.addWidget(g)

        g = QGroupBox("Explosionszeichnung mit Stückliste")
        gl = QHBoxLayout(g)
        k_pdf = QPushButton("PDF/Bild speichern …")
        self.k_akte = QPushButton("In die Angebotsakte legen")
        self.k_akte.setToolTip("PDF und Bild unter Angebotsakte\\Technische_Daten des Angebots")
        gl.addWidget(k_pdf)
        gl.addWidget(self.k_akte)
        lay.addWidget(g)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        lay.addWidget(self.hinweis)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.close)
        lay.addWidget(zu, 0, Qt.AlignRight)

        self.staerke.valueChanged.connect(self._staerke)
        self.staerke.sliderPressed.connect(self.a.explo.merken)
        for sig in (self.richtung.currentIndexChanged, self.ebenen.toggled, self.ueberlappung.toggled,
                    self.linien.toggled, self.beschriftung.currentIndexChanged):
            sig.connect(self._optionen)
        self.ziehen.toggled.connect(self._ziehen)
        self.achse.currentIndexChanged.connect(self._ziehen)
        setzen.clicked.connect(self.versatz_setzen)
        self.k_fix.clicked.connect(lambda: self._mit_gewaehlten(lambda ids: self.a.explo.fixieren(ids, True)))
        self.k_los.clicked.connect(lambda: self._mit_gewaehlten(lambda ids: self.a.explo.fixieren(ids, False)))
        self.k_null.clicked.connect(lambda: self._mit_gewaehlten(lambda ids: self.a.explo.zuruecksetzen(ids)))
        self.k_alle.clicked.connect(self.alles_zuruecksetzen)
        self.k_zurueck.clicked.connect(lambda: self.a.explo.rueckgaengig() and self._neu())
        self.k_vor.clicked.connect(lambda: self.a.explo.wiederholen() and self._neu())
        self.k_pause.clicked.connect(self.a.explosion_pause)
        k_merk.clicked.connect(lambda: self.merken())
        k_lade.clicked.connect(lambda: self.laden())
        k_weg.clicked.connect(lambda: self.loeschen())
        k_pdf.clicked.connect(lambda: self.zeichnung())
        self.k_akte.clicked.connect(lambda: self.akte())
        self.a.gedreht.connect(self.stand_zeigen)
        self.a.wahl.geaendert.connect(self.stand_zeigen)
        self.stand_zeigen()
        self.liste_fuellen()

    # -------------------------------------------------------------- Anzeige
    def stand_zeigen(self, *_):
        if self._laedt:
            return
        s = self.a.explo
        self._laedt = True
        try:
            self.staerke.setValue(int(round(float(s.faktor or 0.0) * 100)))
            self.staerke_text.setText(f"{float(s.faktor or 0.0):.2f}×")
            self.richtung.setCurrentIndex(max(0, list(explosion.RICHTUNGEN.values()).index(s.richtung)
                                              if s.richtung in explosion.RICHTUNGEN.values() else 0))
            self.ebenen.setChecked(bool(s.ebenen))
            self.ueberlappung.setChecked(bool(s.ueberlappung))
            self.linien.setChecked(bool(s.linien))
            self.beschriftung.setCurrentIndex(explosion.BESCHRIFTUNGEN.index(s.beschriftung)
                                              if s.beschriftung in explosion.BESCHRIFTUNGEN else 0)
            self.ziehen.setChecked(bool(self.a.explo_ziehen))
            ids = self._gewaehlt()
            if len(ids) == 1:
                v = s.versatz.get(ids[0]) or (0.0, 0.0, 0.0)
                for sp, x in zip(self.zahlen, v):
                    sp.setValue(float(x))
            fix = [k for k in ids if k in s.fix]
            self.k_zurueck.setEnabled(s.kann_zurueck())
            self.k_vor.setEnabled(s.kann_vor())
            self.k_akte.setEnabled(getattr(self.a, "explosion_akte", None) is not None)
            n = len(set(self.a.wahl.elemente().koerper_von)) if self.a.voll is not None else 0
            teile = f"{len(ids)} gewählt" + (f", davon {len(fix)} fixiert" if fix else "") if ids else "keins gewählt"
            self.hinweis.setText(f"{n} Teile, {teile}; {len(s.fix)} fixiert, {len(s.versatz)} mit eigenem Versatz."
                                 + ("" if n > 1 or s.versatz else " Das Modell hat nur einen Körper."))
        finally:
            self._laedt = False

    def _neu(self):
        self.a.explosion_anwenden()
        self.stand_zeigen()
        return True

    def _gewaehlt(self):
        w = self.a.wahl
        return list(w.koerper_ids()) if w.an else []

    # -------------------------------------------------------------- Bedienung
    def _staerke(self, v):
        if self._laedt:
            return
        self.a.explo.faktor = v / 100.0
        self.staerke_text.setText(f"{v / 100.0:.2f}×")
        self.a.explosion_anwenden()

    def _optionen(self, *_):
        if self._laedt:
            return
        s = self.a.explo
        s.merken()
        s.richtung = list(explosion.RICHTUNGEN.values())[self.richtung.currentIndex()]
        s.ebenen, s.ueberlappung = self.ebenen.isChecked(), self.ueberlappung.isChecked()
        s.linien = self.linien.isChecked()
        s.beschriftung = explosion.BESCHRIFTUNGEN[self.beschriftung.currentIndex()]
        self._neu()

    def _ziehen(self, *_):
        if self._laedt:
            return
        self.a.explo_ziehen = self.ziehen.isChecked()
        self.a.explo_achse = list(ACHSEN.values())[self.achse.currentIndex()]
        if self.a.explo_ziehen and self.a.messen:
            self.a.messen_setzen(False)
        if not self.a.explo_ziehen:
            self.a.explosion_anwenden()     # Bildausschnitt wieder an die Teile anpassen

    def _mit_gewaehlten(self, tun):
        ids = self._gewaehlt()
        if not ids:
            self.hinweis.setText("Bitte zuerst Teile wählen (Klick ins 3D oder in die Liste).")
            return False
        tun(ids)            # Stand.fixieren/versatz_setzen/zuruecksetzen merken selbst für Rückgängig
        return self._neu()

    def versatz_setzen(self):
        v = [s.value() for s in self.zahlen]
        return self._mit_gewaehlten(lambda ids: self.a.explo.versatz_setzen(ids, v))

    def alles_zuruecksetzen(self):
        s = self.a.explo
        s.zuruecksetzen()
        s.faktor = 0.0
        return self._neu()

    def animieren(self, art):
        self.a.explosion_animieren(art, self.tempo.value())

    # -------------------------------------------------------------- Ansichten
    def liste_fuellen(self, wahl=None):
        self.liste.clear()
        for e in ansichten(self.a):
            self.liste.addItem(e["name"])
        if wahl:
            self.liste.setCurrentText(wahl)

    def merken(self, name=None):
        name = (name or self.name.text() or "").strip() or f"Ansicht {self.liste.count() + 1}"
        k = dict(self.a.kamera(), perspektive=bool(getattr(self.a, "perspektive", False)))
        ansichten_schreiben(self.a, explosion.ansicht_merken(ansichten(self.a), name, self.a.explo, k))
        self.liste_fuellen(name)
        self.hinweis.setText(f"Ansicht „{name}“ gespeichert (mit der Baugruppe bzw. dem Satz beim Speichern).")
        return name

    def laden(self, name=None):
        name = name or self.liste.currentText()
        e = next((x for x in ansichten(self.a) if x["name"] == name), None)
        if e is None:
            return False
        self.a.explosion_stand_laden(e["stand"], e["kamera"])
        self.stand_zeigen()
        return True

    def loeschen(self, name=None):
        name = name or self.liste.currentText()
        ansichten_schreiben(self.a, [x for x in ansichten(self.a) if x["name"] != name])
        self.liste_fuellen()

    # -------------------------------------------------------------- Zeichnung
    def zeichnung(self, pfad=None):
        if pfad is None:
            from PySide6.QtWidgets import QFileDialog
            pfad, _ = QFileDialog.getSaveFileName(self, "Explosionszeichnung speichern", "Explosionszeichnung.pdf",
                                                  "PDF (*.pdf);;Bild (*.png)")
            if not pfad:
                return None
        out = zeichnung_speichern(self.a, pfad)
        self.hinweis.setText(f"Gespeichert: {Path(out).name}")
        return out

    def akte(self):
        try:
            out = in_akte_legen(self.a, self.liste.currentText() or None)
        except OSError as e:
            self.hinweis.setText(f"Angebotsakte nicht erreichbar: {e}")
            return None
        self.hinweis.setText("Kein Angebot zu dieser Ansicht." if not out else
                             f"In die Angebotsakte gelegt: {', '.join(Path(p).name for p in out)}")
        return out


def zeigen(a):
    """Explosionsfenster der Ansicht öffnen (eines je Ansicht)."""
    d = getattr(a, "_explo_dialog", None)
    if d is None:
        d = a._explo_dialog = ExplosionsDialog(a, a.window())
    d.stand_zeigen()
    d.liste_fuellen()
    d.show()
    d.raise_()
    return d
