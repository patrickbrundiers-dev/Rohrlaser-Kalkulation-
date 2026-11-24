"""Fenster „Produktionsdaten & Lernsystem“ (Lernsystem L3, Patrick 20.11.2026 „Alles einbauen nach allen
Empfehlungen“): Kacheln oben, darunter die Reiter Produktionsdaten (gelesene LST-Teile mit Datenqualität), Vergleich
(Zuordnung zu Angebot/Position, unsere Zeit gegen TRUMPF/gemessen, Liste „STEP-Messung prüfen“), Vorschläge
(gelernte Faktoren je Ebene mit Preiswirkung; Freigeben, Ablehnen; Laserzeit je Baustein in der Kalibrierung) und
Protokoll (Freigaben, Ablehnungen, Zurücksetzen). Logik in produktion_lst.py, lst_vergleich.py, lst_lernen.py.

„LST-Ordner einlesen“ liest im Hintergrund (L6): das Fenster bleibt bedienbar, gespeichert wird danach in einem
Schritt. Ohne Freigabe ändert sich an der Kalkulation nichts.

Produktionsdaten-Intelligenz (Patrick 24.11.2026): das Fenster heißt jetzt so und liest LST und BPF; zweite
Kachelzeile (BPF-Dateien, Datenqualität, Bearbeitungsschritte, Zeitabweichung, Lernfortschritt, Zeitmodelle), Knöpfe
„Dateien importieren …“ (mehrere LST/BPF, im Hintergrund) und „Abbrechen“; neue Reiter Maschinendaten (alle Werte
eines Teils mit Quelle, Einheit, Deutung), Abgleich (12 Werte Kalkulation ↔ Maschine, Ursachen der Zeitabweichung),
Genauigkeit (je Werkstoff, Wandbereich, Profilart, Monat), Lernanalyse (Zeitmodell je Konturklasse, Ursachen über
alle Teile, auffällige Datensätze) und Importprotokoll (Format, Version, Fehler, nicht gedeutete Felder);
Vorschläge mit Gegenprobe."""
import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog,
                               QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from . import VERSION, stil
from . import lst_lernen as ll
from . import lst_vergleich as lv
from . import maschinendaten as md
from . import produktion_abgleich as pa
from . import produktion_genauigkeit as pg
from . import produktion_lst as pl
from . import produktion_zeitmodell as zm
from .kacheln import KachelZeile
from .stil import GELB_FLAECHE, ROT_FLAECHE, TEXT_GRAU

KACHELN = (
    ("dateien", "LST-Dateien", "Gelesene LST-Dateien (jede Datei einmal, auch umbenannt)"),
    ("teile", "Teile", "Gelesene Teile, davon vollständig (fürs Lernen geeignet)"),
    ("gemessen", "Mit gemessener Zeit", "Nach dem Lauf an der Maschine gespeicherte LST (Zeit der Maschine)"),
    ("zugeordnet", "Zugeordnet", "Teile mit Angebot und Position (PPEASE-Nummer, Artikel, Merkmale, von Hand)"),
    ("abweichung", "Abweichung (Median)", "Mittlere Abweichung gemessen bzw. TRUMPF gegen unsere Laserzeit"),
    ("step", "STEP-Messung prüfen", "Teile, deren Schneidweg, Einstiche oder Länge nicht zur Position passen"),
    ("vorschlaege", "Vorschläge bereit", "Gelernte Faktoren mit genug Daten (ab 10 Teilen aus 3 Programmen)"),
)
KACHELN2 = (
    ("bpf", "BPF-Dateien", "Gelesene BLM-BPF-Dateien (Geometrie, Schnittlänge, Konturen; ohne Zeiten)"),
    ("qualitaet", "Datenqualität", "Anteil vollständiger Teile; darunter der Anteil mit gemessener Zeit"),
    ("schritte", "Bearbeitungsschritte", "Erkannte Konturen und Einstiche aller Teile"),
    ("genauigkeit", "Zeitabweichung", "Mittlere |Abweichung| unserer Zeit gegen die Maschinendaten (zugeordnete Teile)"),
    ("fortschritt", "Lernfortschritt", "Teile mit gemessener Zeit, die fürs Lernen zählen (ab 10 je Gruppe)"),
    ("modelle", "Zeitmodelle", "Gruppen mit Zeitmodell je Konturklasse (ab 3 Programmen)"),
)
P_SPALTEN = ("Programm", "PPEASE", "Maschine", "Werkstoff", "Profil", "Länge", "Schneidweg", "Einstiche",
             "TRUMPF [s]", "Gemessen [s]", "Messungen", "Qualität", "Gründe", "Datei")
V_SPALTEN = ("Programm", "Angebot", "Pos.", "Zuordnung", "Unsere Zeit [s]", "TRUMPF [s]", "Gemessen [s]",
             "Abweichung [s]", "Abweichung [%]", "Geometrie", "Lernen")
S_SPALTEN = ("Ebene", "Gruppe", "Faktor Ist ÷ Soll", "Teile", "Programme", "Streuung", "Preiswirkung", "Gegenprobe",
             "Status")
M_SPALTEN = ("Bedeutung", "Wert", "Einheit", "Quelle in der Datei", "Deutung")
A_SPALTEN = ("Parameter", "Kalkulation", "Art", "Maschinendaten", "Art ", "Abweichung", "Abweichung [%]", "Hinweis")
U_SPALTEN = ("Ursache", "Anteil [s]", "Rechnung")
G_SPALTEN = ("Nach", "Gruppe", "Teile", "Zeit |Abw.| [%]", "Material |Abw.| [%]")
L_SPALTEN = ("Art", "Gruppe", "Teile", "Programme", "Ergebnis")
I_SPALTEN = ("Datei", "Format", "Version", "Gelesen", "Teile", "Nicht gedeutete Felder", "Fehler", "Pfad")
REITER = ("Produktionsdaten", "Maschinendaten", "Vergleich", "Abgleich", "Genauigkeit", "Vorschläge", "Lernanalyse",
          "Importprotokoll", "Protokoll")
R_SPALTEN = ("Was", "Am", "Ebene", "Gruppe", "Faktor", "Teile", "Text")


def _z(w, n=1):
    return "" if w is None else f"{w:.{n}f}".replace(".", ",")


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.ExtendedSelection)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    t.setSortingEnabled(False)
    return t


def _fuellen(tab, zeilen, farbe=None, rechts=()):
    tab.setRowCount(len(zeilen))
    for r, werte in enumerate(zeilen):
        f = farbe(r) if farbe else None
        for c, w in enumerate(werte):
            it = QTableWidgetItem("" if w is None else str(w))
            if c in rechts:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if f == "grau":
                it.setForeground(QBrush(stil.farbe(TEXT_GRAU)))
            elif f:
                it.setBackground(QBrush(stil.farbe(f)))
            tab.setItem(r, c, it)
    tab.resizeColumnsToContents()


def _gegenprobe(val):
    if not val or val.get("besser") is None:
        return ""
    return (f"{_z(val['fehler_vorher'])} → {_z(val['fehler_nachher'])} %" + ("" if val["besser"] else " (nicht besser)"))


def _profil(t):
    if t.get("profilform") == "Rundrohr":
        return f"Ø{_z(t.get('a'))}×{_z(t.get('wand'))}"
    if t.get("a"):
        return f"{_z(t['a'], 0)}×{_z(t.get('b'), 0)}×{_z(t.get('wand'))}"
    return ""


class LernsystemDialog(QDialog):
    def __init__(self, parent, db, frage=None):
        super().__init__(parent)
        self.f, self.db, self.geaendert = parent, db, False
        self.frage = frage or self._frage     # frage(Titel, Text) -> bool (Tests: ohne Fenster)
        self.eingabe = None                   # eingabe(Titel, Text, Vorgabe) -> Text oder None (Tests)
        self._lauf = None
        self.dateien_waehlen = None           # dateien_waehlen() -> [Pfade] (Tests: ohne Dateiauswahl)
        self.setWindowTitle("Produktionsdaten-Intelligenz")
        self.resize(1300, 800)
        lay = QVBoxLayout(self)
        info = QLabel("Maschinendaten aus TRUMPF-LST und BLM-BPF gegen unsere Kalkulation: alle ausgelesenen Werte "
                      "mit Quelle, Vergleich Kalkulation ↔ Maschine mit Ursachen, Genauigkeit und Lernanalyse. Das "
                      "Programm schlägt Faktoren vor (ab 10 Teilen aus 3 Programmen, neuere Teile zählen mehr); "
                      "geändert wird nur mit „Freigeben“, jede Freigabe lässt sich zurücksetzen. Die Einstichzeit "
                      "bleibt ein eigener Posten.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.kacheln = KachelZeile(KACHELN)
        self.kacheln.geklickt.connect(self._kachel)
        lay.addWidget(self.kacheln)
        self.kacheln2 = KachelZeile(KACHELN2)
        self.kacheln2.geklickt.connect(self._kachel)
        lay.addWidget(self.kacheln2)
        oben = QHBoxLayout()
        self.einlesen_knopf = QPushButton("LST-Ordner einlesen")
        self.einlesen_knopf.setToolTip("Neue und geänderte LST-Dateien des eingestellten Ordners lesen (im "
                                       "Hintergrund; unveränderte Dateien werden nicht geöffnet)")
        self.einlesen_knopf.clicked.connect(lambda: self.einlesen())
        oben.addWidget(self.einlesen_knopf)
        self.import_knopf = QPushButton("Dateien importieren …")
        self.import_knopf.setToolTip("Eine oder mehrere LST- und BPF-Dateien wählen und im Hintergrund lesen (doppelte "
                                     "Dateien werden erkannt)")
        self.import_knopf.clicked.connect(lambda: self.importieren())
        oben.addWidget(self.import_knopf)
        self.abbrechen_knopf = QPushButton("Abbrechen")
        self.abbrechen_knopf.setToolTip("Laufendes Einlesen anhalten; schon gelesene Dateien werden gespeichert")
        self.abbrechen_knopf.setEnabled(False)
        self.abbrechen_knopf.clicked.connect(lambda: self.abbrechen())
        oben.addWidget(self.abbrechen_knopf)
        knopf = QPushButton("Aktualisieren")
        knopf.clicked.connect(lambda: self.neu_laden())
        oben.addWidget(knopf)
        self.status = QLabel()
        oben.addWidget(self.status, 1)
        lay.addLayout(oben)
        self.reiter = QTabWidget()
        lay.addWidget(self.reiter, 1)
        # Produktionsdaten
        self.ptab = _tabelle(P_SPALTEN)
        self.ptab.itemSelectionChanged.connect(self._merkmale_fuellen)
        self.reiter.addTab(self._seite(self.ptab), "Produktionsdaten")
        # Maschinendaten: alle Werte des gewählten Teils
        self.mtab = _tabelle(M_SPALTEN)
        self.m_titel = QLabel("Ein Teil unter „Produktionsdaten“ wählen.")
        self.m_titel.setWordWrap(True)
        self.reiter.addTab(self._seite(self.mtab, [self.m_titel]), "Maschinendaten")
        # Vergleich
        self.vtab = _tabelle(V_SPALTEN)
        self.nur_step = QCheckBox("Nur „STEP-Messung prüfen“")
        self.nur_step.toggled.connect(lambda _: self._vergleich_fuellen())
        knoepfe = []
        for text, fn, tipp in (("Zuordnung ändern …", self.zuordnen, "Angebot und Position von Hand wählen (wird "
                                                                      "gemerkt, auch bei den Kollegen)"),
                               ("Zuordnung bestätigen", self.bestaetigen, "Unsichere Zuordnung als richtig merken"),
                               ("Nie zuordnen", self.nie_zuordnen, "Dieses Teil nicht zuordnen (zählt nicht)"),
                               ("Zuordnung vergessen", self.vergessen, "Gemerkte Zuordnung entfernen (automatisch)")):
            b = QPushButton(text)
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            knoepfe.append(b)
        self.vtab.itemSelectionChanged.connect(self._abgleich_fuellen)
        self.reiter.addTab(self._seite(self.vtab, [self.nur_step] + knoepfe), "Vergleich")
        # Abgleich: 12 Werte und Ursachen der gewählten Zeile
        w = QWidget()
        al = QVBoxLayout(w)
        al.setContentsMargins(0, 6, 0, 0)
        self.a_titel = QLabel("Ein zugeordnetes Teil unter „Vergleich“ wählen.")
        self.a_titel.setWordWrap(True)
        al.addWidget(self.a_titel)
        self.atab = _tabelle(A_SPALTEN)
        al.addWidget(self.atab, 3)
        al.addWidget(QLabel("Woher kommt die Zeitabweichung?"))
        self.utab = _tabelle(U_SPALTEN)
        al.addWidget(self.utab, 2)
        self.reiter.addTab(w, "Abgleich")
        # Genauigkeit
        self.gtab = _tabelle(G_SPALTEN)
        self.g_text = QLabel()
        self.g_text.setWordWrap(True)
        self.reiter.addTab(self._seite(self.gtab, [self.g_text]), "Genauigkeit")
        # Vorschläge
        self.stab = _tabelle(S_SPALTEN)
        self.mit_ruhenden = QCheckBox("Abgelehnte zeigen")
        self.mit_ruhenden.toggled.connect(lambda _: self._vorschlaege_laden())
        knoepfe = []
        for text, fn, tipp in (("Freigeben …", self.freigeben, "Gewählten Vorschlag übernehmen (Vorschübe ÷ Faktor, "
                                                              "Historie unter Kennwerte)"),
                               ("Ablehnen", self.ablehnen, "Vorschlag ruht, bis sich die Daten deutlich ändern"),
                               ("Wieder aufnehmen", self.wieder_aufnehmen, "Abgelehnten Vorschlag wieder zeigen"),
                               ("Laserzeit je Baustein …", self.bausteine, "Faktoren je Baustein (Schneiden, "
                                                                           "Einstechen …) mit den LST-Zeiten")):
            b = QPushButton(text)
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            knoepfe.append(b)
        self.reiter.addTab(self._seite(self.stab, [self.mit_ruhenden] + knoepfe), "Vorschläge")
        # Lernanalyse und Importprotokoll
        self.ltab = _tabelle(L_SPALTEN)
        self.reiter.addTab(self._seite(self.ltab), "Lernanalyse")
        self.itab = _tabelle(I_SPALTEN)
        self.reiter.addTab(self._seite(self.itab), "Importprotokoll")
        # Protokoll
        self.rtab = _tabelle(R_SPALTEN)
        b = QPushButton("Zurücksetzen")
        b.setToolTip("Gewählte Freigabe zurücknehmen (alte Werte, nur wenn sie seitdem niemand geändert hat)")
        b.clicked.connect(lambda: self.zuruecksetzen())
        self.reiter.addTab(self._seite(self.rtab, [b]), "Protokoll")
        schluss = QDialogButtonBox(QDialogButtonBox.Close)
        schluss.rejected.connect(self.reject)
        lay.addWidget(schluss)
        self.neu_laden()

    # ------------------------------------------------------------------ Aufbau
    def _seite(self, tab, knoepfe=()):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        if knoepfe:
            z = QHBoxLayout()
            for k in knoepfe:
                z.addWidget(k)
            z.addStretch(1)
            lay.addLayout(z)
        lay.addWidget(tab, 1)
        return w

    def _frage(self, titel, text):
        return QMessageBox.question(self, titel, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == \
            QMessageBox.Yes

    def _text_eingeben(self, titel, text, vorgabe=""):
        if self.eingabe is not None:
            return self.eingabe(titel, text, vorgabe)
        t, ok = QInputDialog.getText(self, titel, text, text=vorgabe)
        return t if ok else None

    def zeige_reiter(self, name):
        self.reiter.setCurrentIndex(REITER.index(name))

    def _kachel(self, schluessel):
        ziel = {"step": "Vergleich", "vorschlaege": "Vorschläge", "fortschritt": "Vorschläge", "zugeordnet": "Vergleich",
                "abweichung": "Vergleich", "genauigkeit": "Genauigkeit", "modelle": "Lernanalyse",
                "schritte": "Lernanalyse", "bpf": "Importprotokoll", "dateien": "Importprotokoll",
                "qualitaet": "Produktionsdaten"}.get(schluessel, "Produktionsdaten")
        self.zeige_reiter(ziel)
        if schluessel == "step":
            self.nur_step.setChecked(True)

    # ------------------------------------------------------------------ Laden
    def neu_laden(self):
        self.teile = pl.teile(self.db)
        self.zeilen = lv.vergleich(self.db, self.teile)
        u = pl.uebersicht(self.db)
        kz = lv.kennzahlen(self.zeilen)
        k = self.kacheln.kacheln
        k["dateien"].setzen(str(u["dateien"]))
        k["teile"].setzen(str(u["teile"]), f"{u['voll']} vollständig")
        k["gemessen"].setzen(str(u["gemessen"]))
        k["zugeordnet"].setzen(str(kz["zugeordnet"]), f"{kz['lernbar']} fürs Lernen")
        k["abweichung"].setzen(f"{_z(kz['abweichung_pct'], 0)} %" if kz["abweichung_pct"] is not None else "–",
                               f"aus {kz['verglichen']} Teilen" if kz["verglichen"] else "")
        k["step"].setzen(str(kz["step_pruefen"]))
        _fuellen(self.ptab, [[t["programm"], t.get("ppease"), t.get("maschine"), t.get("werkstoff"), _profil(t),
                              _z(t.get("laenge")), _z(t.get("schneidweg"), 0), t.get("einstiche"),
                              _z(pl.zeit_s(t, gemessen=False), 2),
                              _z(pl.zeit_s(t), 2) if t.get("zeiten_gemessen") else "", t.get("messungen") or "",
                              t.get("qualitaet"), "; ".join(t.get("gruende") or ()), t.get("datei")]
                             for t in self.teile],
                 farbe=lambda r: None if self.teile[r]["qualitaet"] == "vollständig" else "grau",
                 rechts=(5, 6, 7, 8, 9, 10))
        self.abgleich = pa.auswerten(self.db, self.zeilen)
        self._abgleich_je = {(e["zeile"]["teil"]["programm"], e["zeile"]["teil"]["teil_nr"]): e for e in self.abgleich}
        self._vergleich_fuellen()
        self._vorschlaege_laden()
        self._protokoll_laden()
        self._intelligenz_laden(u, kz)
        if not self.teile:
            ordner = self.db.einstellung("lst_ordner")
            self.status.setText("Noch keine LST-Dateien gelesen. " + (
                "„LST-Ordner einlesen“ liest den eingestellten Ordner." if ordner else
                "Bitte zuerst den Ordner der gefertigten LST-Dateien einstellen (Einstellungen, STEP-Import)."))

    def _vergleich_fuellen(self):
        self.v_zeilen = lv.step_pruefen(self.zeilen) if self.nur_step.isChecked() else list(self.zeilen)

        def farbe(r):
            z = self.v_zeilen[r]
            if z["geometrie"]:
                return ROT_FLAECHE
            if z["zuordnung"].get("position_id") and not z["zuordnung"].get("sicher"):
                return GELB_FLAECHE
            return None if z["lernbar"] else "grau"

        _fuellen(self.vtab, [[z["teil"]["programm"], z["zuordnung"].get("nummer"), z["zuordnung"].get("pos"),
                              z["zuordnung"]["art"] + ("" if z["zuordnung"].get("sicher") or
                                                       not z["zuordnung"].get("position_id") else " (unsicher)"),
                              _z(z["soll_s"], 2), _z(z["lst_s"], 2), _z(z["ist_s"], 2), _z(z["diff_s"], 2),
                              f"{z['diff_pct']:+.1f} %".replace(".", ",") if z["diff_pct"] is not None else "",
                              "; ".join(z["geometrie"]), "ja" if z["lernbar"] else z["grund"]]
                             for z in self.v_zeilen], farbe=farbe, rechts=(2, 4, 5, 6, 7, 8))

    def _vorschlaege_laden(self):
        self.vorschlaege = ll.vorschlaege(self.db, self.zeilen, mit_ruhenden=self.mit_ruhenden.isChecked())
        bereit = sum(1 for v in self.vorschlaege if v["status"] == "ok" and v["anwendbar"] and not v["ruht"])
        self.kacheln.kacheln["vorschlaege"].setzen(str(bereit), f"{len(self.vorschlaege)} Gruppen")

        def farbe(r):
            v = self.vorschlaege[r]
            if v["status"] != "ok" or v["ruht"]:
                return "grau"
            if v["warnung"] or (v["preiswirkung"] is not None and abs(v["preiswirkung"]) > ll.PREIS_GRENZE):
                return ROT_FLAECHE
            return GELB_FLAECHE if v["faktor"] and abs(v["faktor"] - 1) >= 0.1 else None

        def status(v):
            if v["ruht"]:
                return "abgelehnt (ruht)"
            t = v["status"] if v["anwendbar"] else f"{v['status']}, nur Hinweis"
            return t + (f"; {v['warnung']}" if v["warnung"] else "")

        _fuellen(self.stab, [[v["titel"], ll.text_schluessel(v), _z(v["faktor"], 3), v["n"], v["programme"],
                              _z(v["streuung"], 3),
                              f"{v['preiswirkung']:+.1f} %".replace(".", ",") if v["preiswirkung"] is not None else "",
                              _gegenprobe(v.get("validierung")), status(v)] for v in self.vorschlaege],
                 farbe=farbe, rechts=(2, 3, 4, 5, 6))

    def _protokoll_laden(self):
        self.protokoll = ll.protokoll(self.db)
        _fuellen(self.rtab, [[p["art"], p["am"].replace("T", " "), p["ebene"], p["gruppe"], _z(p["faktor"], 3),
                              p["n"], p["text"]] for p in self.protokoll],
                 farbe=lambda r: "grau" if self.protokoll[r]["art"] != "freigegeben" else None, rechts=(4, 5))

    # ------------------------------------------------------------------ Produktionsdaten-Intelligenz
    def _intelligenz_laden(self, u, kz):
        k2 = self.kacheln2.kacheln
        q = pg.qualitaet(self.teile)
        k2["bpf"].setzen(str(u.get("bpf", 0)), f"{u.get('lst', 0)} LST" + (f", {u['fehler']} mit Fehler"
                                                                           if u.get("fehler") else ""))
        k2["qualitaet"].setzen(f"{_z(q['vollstaendig_pct'], 0)} %" if q["vollstaendig_pct"] is not None else "–",
                               f"{_z(q['gemessen_pct'], 0)} % gemessen" if q["gemessen_pct"] is not None else "")
        kont = sum(md.w(t.get("merkmale"), "konturen", 0) or 0 for t in self.teile)
        stiche = sum(t.get("einstiche") or 0 for t in self.teile)
        k2["schritte"].setzen(str(int(kont + stiche)), f"{int(kont)} Konturen, {int(stiche)} Einstiche")
        pct = [abs(z["diff_pct"]) for z in self.zeilen if z["diff_pct"] is not None]
        k2["genauigkeit"].setzen(f"{_z(sum(pct) / len(pct), 1)} %" if pct else "–",
                                 f"aus {len(pct)} Teilen" if pct else "keine zugeordneten Teile")
        k2["fortschritt"].setzen(str(sum(1 for z in self.zeilen if z["lernbar"])), "Teile fürs Lernen")
        self.modelle = zm.modelle(self.teile, [e["zeile"] for e in self.abgleich])
        k2["modelle"].setzen(str(sum(1 for m in self.modelle if m["status"] == "ok")),
                             f"{len(self.modelle)} Gruppen mit Klassenwerten")
        # Genauigkeit
        zeilen = []
        for merkmal, titel in (("werkstoff", "Werkstoff"), ("wand", "Wandbereich"), ("profil", "Profilart"),
                               ("monat", "Monat")):
            for g in pg.genauigkeit_nach(self.abgleich, merkmal):
                zeilen.append([titel, g["gruppe"], g["n"], _z(g["zeit_pct"]), _z(g["material_pct"], 2)])
        _fuellen(self.gtab, zeilen, rechts=(2, 3, 4))
        werte, _ = pa.zusammenfassung(self.abgleich)
        self.g_text.setText("Noch keine zugeordneten Teile: die Genauigkeit zeigt sich, sobald Maschinendaten "
                            "Angebotspositionen zugeordnet sind." if not self.abgleich else
                            "Mittlere |Abweichung| je Wert: " + "; ".join(
                                f"{pa.TITEL[s]} {_z(w['mittel_abs_pct'])} % ({w['n']})" for s, w in werte.items()))
        # Lernanalyse
        _, urs = pa.zusammenfassung(self.abgleich)
        lz = [["Zeitmodell je Konturklasse", m["text"], m["n"], m["programme"], zm.text(m)] for m in self.modelle]
        lz += [["Ursache der Zeitabweichung", u, d["n"], "", f"Median {_z(d['median_s'], 2)} s je Teil"]
               for u, d in sorted(urs.items(), key=lambda x: -abs(x[1]["median_s"]))]
        for z in self.zeilen:
            if z["diff_pct"] is not None and abs(z["diff_pct"]) > 50:
                lz.append(["Auffälliger Datensatz", z["teil"]["programm"], 1, 1,
                           f"Abweichung {z['diff_pct']:+.0f} % – Zuordnung und Geometrie prüfen".replace(".", ",")])
        for t in self.teile:
            if t.get("qualitaet") == "unplausibel":
                lz.append(["Auffälliger Datensatz", t["programm"], 1, 1, "unplausibel: " + "; ".join(
                    t.get("gruende") or ())])
        if not lz:
            lz = [["Hinweis", "", "", "", "Noch keine Klassenwerte oder Vergleiche: Muster zeigen sich ab mehreren "
                                          "Programmen mit Laser-an-Zeit und Konturklassen."]]
        _fuellen(self.ltab, lz, farbe=lambda r: None if lz[r][0] != "Auffälliger Datensatz" else GELB_FLAECHE,
                 rechts=(2, 3))
        # Importprotokoll
        self.protokoll_dateien = pl.dateien(self.db)
        _fuellen(self.itab, [[d["name"], d["format"], d["version"], (d["gelesen"] or "").replace("T", " "), d["teile"],
                              d["unbekannt"] or "", d["fehler"] or "", d["pfad"]] for d in self.protokoll_dateien],
                 farbe=lambda r: ROT_FLAECHE if self.protokoll_dateien[r]["fehler"] else None, rechts=(4, 5))
        self._merkmale_fuellen()
        self._abgleich_fuellen()

    def _merkmale_fuellen(self):
        gew = self._gewaehlte(self.ptab, self.teile)
        if not gew:
            self.mtab.setRowCount(0)
            self.m_titel.setText("Ein Teil unter „Produktionsdaten“ wählen: hier stehen dann alle ausgelesenen Werte.")
            return
        t = gew[0]
        m = t.get("merkmale") or {}
        self.m_titel.setText(f"{t['programm']} ({t.get('format') or 'LST'}, {t.get('datei')}): {len(m)} Werte. Was "
                             "nicht in der Datei steht, fehlt hier (nichts ergänzt).")
        zeilen = []
        for schl, x in m.items():
            v, einheit, quelle, deutung, sicher = (list(x) + [None] * 5)[:5]
            zeilen.append([deutung or schl, _z(v, 2) if isinstance(v, float) else v, einheit, quelle,
                           "sicher" if sicher else "aus Beispielen geschlossen"])
        _fuellen(self.mtab, zeilen, farbe=lambda r: None if zeilen[r][4] == "sicher" else "grau")

    def _abgleich_fuellen(self):
        gew = self._gewaehlte(self.vtab, getattr(self, "v_zeilen", []))
        e = self._abgleich_je.get((gew[0]["teil"]["programm"], gew[0]["teil"]["teil_nr"])) if gew else None
        if e is None:
            self.atab.setRowCount(0)
            self.utab.setRowCount(0)
            self.a_titel.setText("Ein zugeordnetes Teil unter „Vergleich“ wählen: hier stehen dann Kalkulation und "
                                 "Maschinendaten nebeneinander." if not gew else "Dieses Teil ist keiner Position "
                                 "zugeordnet.")
            return
        z = e["zeile"]
        self.a_titel.setText(f"{z['teil']['programm']} ↔ Angebot {z['zuordnung'].get('nummer')}, Position "
                             f"{z['zuordnung'].get('pos')} ({z['zuordnung']['art']})")
        ws = e["werte"]
        _fuellen(self.atab, [[w["titel"] + (f" [{w['einheit']}]" if w["einheit"] else ""), _z(w["kalk"], 2),
                              w["kalk_art"], _z(w["maschine"], 2), w["maschine_art"], _z(w["diff"], 2),
                              f"{w['diff_pct']:+.1f} %".replace(".", ",") if w["diff_pct"] is not None else "",
                              w["quelle"]] for w in ws],
                 farbe=lambda r: "grau" if ws[r]["diff"] is None else ROT_FLAECHE
                 if ws[r]["diff_pct"] is not None and abs(ws[r]["diff_pct"]) > 20 else None, rechts=(1, 3, 5, 6))
        us = e["ursachen"]
        _fuellen(self.utab, [[u["ursache"], _z(u["anteil_s"], 2), u["rechnung"]] for u in us] or
                 [["keine Zeitabweichung zu erklären", "", ""]], rechts=(1,))

    def importieren(self, pfade=None, warten=False):
        """Gewählte LST/BPF-Dateien im Hintergrund lesen (wie der Ordner)."""
        if self._lauf is not None:
            return
        if pfade is None:
            if self.dateien_waehlen is not None:
                pfade = self.dateien_waehlen()
            else:
                from PySide6.QtWidgets import QFileDialog
                pfade, _ = QFileDialog.getOpenFileNames(self, "Maschinendateien importieren",
                                                        str(self.db.einstellung("lst_ordner") or ""),
                                                        "Maschinendaten (*.lst *.LST *.bpf *.BPF)")
        pfade = [p for p in (pfade or []) if md.format_von(p)]
        if not pfade:
            self.status.setText("Keine LST- oder BPF-Datei gewählt.")
            return
        self._starten(pfade, warten)

    def abbrechen(self):
        if self._lauf is not None:
            self._lauf["abbrechen"] = True
            self.status.setText("Wird abgebrochen …")

    # ------------------------------------------------------------------ Einlesen (Hintergrund, L6)
    def einlesen(self, warten=False):
        """LST-Ordner im Hintergrund lesen; warten=True (Tests): bis zum Ende."""
        if self._lauf is not None:
            return
        ordner = self.db.einstellung("lst_ordner")
        if not str(ordner or "").strip() or not pl.Path(str(ordner)).is_dir():
            self.status.setText(pl.ordner_einlesen(self.db, ordner)["fehler"][0])     # Text: kein/fehlender Ordner
            return
        self._starten(pl.dateien_im_ordner(ordner), warten)

    def _starten(self, pfade, warten=False):
        summen, dateien = pl.bekannt(self.db)
        lauf = dict(fertig=False, ergebnis=None, abbrechen=False)

        def arbeit():
            try:
                lauf["ergebnis"] = pl.vorbereiten(pfade, summen, dateien, lambda: lauf["abbrechen"])
            except Exception as e:  # noqa: BLE001 – im Fenster melden
                lauf["fehler"] = str(e)
            lauf["fertig"] = True

        self._lauf = lauf
        self.einlesen_knopf.setEnabled(False)
        self.import_knopf.setEnabled(False)
        self.abbrechen_knopf.setEnabled(True)
        self.status.setText(f"Lese {len(pfade)} Maschinendateien im Hintergrund …")
        th = threading.Thread(target=arbeit, daemon=True)
        th.start()
        if warten:
            th.join()
            self._lauf_pruefen()
            return
        self._takt = QTimer(self)
        self._takt.timeout.connect(self._lauf_pruefen)
        self._takt.start(200)

    def _lauf_pruefen(self):
        lauf = self._lauf
        if lauf is None or not lauf["fertig"]:
            return
        if getattr(self, "_takt", None) is not None:
            self._takt.stop()
            self._takt = None
        self._lauf = None
        self.einlesen_knopf.setEnabled(True)
        self.import_knopf.setEnabled(True)
        self.abbrechen_knopf.setEnabled(False)
        if lauf.get("fehler"):
            self.status.setText(f"Einlesen abgebrochen: {lauf['fehler']}")
            return
        erg = pl.schreiben(self.db, lauf["ergebnis"] or [])
        self.neu_laden()
        self.status.setText(pl.ergebnis_text(erg) + (" – abgebrochen" if lauf.get("abbrechen") else ""))

    def reject(self):
        if self._lauf is not None:
            self._lauf["abbrechen"] = True
        super().reject()

    # ------------------------------------------------------------------ Zuordnung
    def _gewaehlte(self, tab, liste):
        return [liste[r] for r in sorted({i.row() for i in tab.selectedIndexes()}) if r < len(liste)]

    def zuordnen(self):
        gew = self._gewaehlte(self.vtab, self.v_zeilen)
        if not gew:
            self.status.setText("Bitte zuerst ein Teil im Vergleich wählen.")
            return
        z = gew[0]["zuordnung"]
        t = self._text_eingeben("Zuordnung ändern", "Angebot und Position, z. B. 2026-00122/10:",
                                f"{z.get('nummer') or ''}/{z.get('pos') or ''}" if z.get("nummer") else "")
        if t is None:
            return
        nummer, _, pos = t.strip().partition("/")
        try:
            pos = int(pos.strip()) if pos.strip() else None
        except ValueError:
            self.status.setText("Position bitte als Zahl, z. B. 2026-00122/10.")
            return
        for x in gew:
            lv.merken(self.db, x["teil"], nummer.strip(), pos, self._kuerzel())
        self.neu_laden()

    def bestaetigen(self):
        for x in self._gewaehlte(self.vtab, self.v_zeilen):
            z = x["zuordnung"]
            if z.get("position_id"):
                lv.merken(self.db, x["teil"], z["nummer"], z["pos"], self._kuerzel())
        self.neu_laden()

    def nie_zuordnen(self):
        for x in self._gewaehlte(self.vtab, self.v_zeilen):
            lv.merken(self.db, x["teil"], "", None, self._kuerzel())
        self.neu_laden()

    def vergessen(self):
        for x in self._gewaehlte(self.vtab, self.v_zeilen):
            lv.vergessen(self.db, x["teil"])
        self.neu_laden()

    def _kuerzel(self):
        from .teilen import kuerzel
        return kuerzel(self.db)

    # ------------------------------------------------------------------ Vorschläge
    def freigeben(self):
        gew = self._gewaehlte(self.stab, self.vorschlaege)
        if not gew:
            self.status.setText("Bitte zuerst einen Vorschlag wählen.")
            return None
        v = gew[0]
        pw = v.get("preiswirkung")
        text = (f"{v['titel']}\n{ll.text_schluessel(v)}\n\nFaktor {_z(v['faktor'], 3)} aus {v['n']} Teilen "
                f"({v['programme']} Programme)" + (f", Preiswirkung {_z(pw, 1)} %" if pw is not None else "") +
                ".\n\nÜbernehmen? Die Freigabe steht im Protokoll und lässt sich zurücksetzen.")
        if not self.frage("Vorschlag freigeben", text):
            return None
        try:
            hid = ll.freigeben(self.db, v, VERSION)
        except ll.BestaetigungNoetig as e:
            if not self.frage("Ausdrücklich bestätigen", str(e)):
                return None
            hid = ll.freigeben(self.db, v, VERSION, bestaetigt=True)
        except ValueError as e:
            self.status.setText(str(e))
            return None
        self.geaendert = True
        self.neu_laden()
        self.status.setText("Freigegeben; im Protokoll zurücksetzbar.")
        return hid

    def ablehnen(self):
        gew = self._gewaehlte(self.stab, self.vorschlaege)
        for v in gew:
            ll.ablehnen(self.db, v, "", self._kuerzel())
        if gew:
            self.neu_laden()

    def wieder_aufnehmen(self):
        gew = self._gewaehlte(self.stab, self.vorschlaege)
        for v in gew:
            ll.wieder_aufnehmen(self.db, v)
        if gew:
            self.neu_laden()

    def bausteine(self):
        from .kalibrierung_dialog import KalibrierDialog
        d = KalibrierDialog(self, self.db)
        d.exec()
        self.neu_laden()

    def zuruecksetzen(self):
        gew = [p for p in self._gewaehlte(self.rtab, self.protokoll) if p["historie_id"] and not p["zurueck"]]
        if not gew:
            self.status.setText("Bitte eine Freigabe wählen, die noch gilt.")
            return 0
        n = sum(ll.zuruecksetzen(self.db, p["historie_id"]) for p in gew)
        self.geaendert = True
        self.neu_laden()
        self.status.setText(f"{n} Wert(e) zurückgesetzt.")
        return n


def zeigen(f, dialog=None):
    """Fenster öffnen; dialog(d) bedient es statt exec (Tests)."""
    d = LernsystemDialog(f, f.db)
    if dialog:
        dialog(d)
    else:
        d.exec()
        if d.geaendert and hasattr(f, "alles_neu_laden"):
            f.alles_neu_laden()
    return d
