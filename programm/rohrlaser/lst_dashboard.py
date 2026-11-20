"""Fenster „Produktionsdaten & Lernsystem“ (Lernsystem L3, Patrick 20.11.2026 „Alles einbauen nach allen
Empfehlungen“): Kacheln oben, darunter die Reiter Produktionsdaten (gelesene LST-Teile mit Datenqualität), Vergleich
(Zuordnung zu Angebot/Position, unsere Zeit gegen TRUMPF/gemessen, Liste „STEP-Messung prüfen“), Vorschläge
(gelernte Faktoren je Ebene mit Preiswirkung; Freigeben, Ablehnen; Laserzeit je Baustein in der Kalibrierung) und
Protokoll (Freigaben, Ablehnungen, Zurücksetzen). Logik in produktion_lst.py, lst_vergleich.py, lst_lernen.py.

„LST-Ordner einlesen“ liest im Hintergrund (L6): das Fenster bleibt bedienbar, gespeichert wird danach in einem
Schritt. Ohne Freigabe ändert sich an der Kalkulation nichts."""
import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog,
                               QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from . import VERSION, stil
from . import lst_lernen as ll
from . import lst_vergleich as lv
from . import produktion_lst as pl
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
P_SPALTEN = ("Programm", "PPEASE", "Maschine", "Werkstoff", "Profil", "Länge", "Schneidweg", "Einstiche",
             "TRUMPF [s]", "Gemessen [s]", "Messungen", "Qualität", "Gründe", "Datei")
V_SPALTEN = ("Programm", "Angebot", "Pos.", "Zuordnung", "Unsere Zeit [s]", "TRUMPF [s]", "Gemessen [s]",
             "Abweichung [s]", "Abweichung [%]", "Geometrie", "Lernen")
S_SPALTEN = ("Ebene", "Gruppe", "Faktor Ist ÷ Soll", "Teile", "Programme", "Streuung", "Preiswirkung", "Status")
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
        self.setWindowTitle("Produktionsdaten & Lernsystem")
        self.resize(1300, 800)
        lay = QVBoxLayout(self)
        info = QLabel("Gemessene Zeiten der Maschine aus den TRUMPF-LST-Dateien gegen unsere Kalkulation. Das "
                      "Programm schlägt Faktoren vor (ab 10 Teilen aus 3 Programmen, neuere Teile zählen mehr); "
                      "geändert wird nur mit „Freigeben“, jede Freigabe lässt sich zurücksetzen. Die Einstichzeit "
                      "bleibt ein eigener Posten.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.kacheln = KachelZeile(KACHELN)
        self.kacheln.geklickt.connect(self._kachel)
        lay.addWidget(self.kacheln)
        oben = QHBoxLayout()
        self.einlesen_knopf = QPushButton("LST-Ordner einlesen")
        self.einlesen_knopf.setToolTip("Neue und geänderte LST-Dateien des eingestellten Ordners lesen (im "
                                       "Hintergrund; unveränderte Dateien werden nicht geöffnet)")
        self.einlesen_knopf.clicked.connect(lambda: self.einlesen())
        oben.addWidget(self.einlesen_knopf)
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
        self.reiter.addTab(self._seite(self.ptab), "Produktionsdaten")
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
        self.reiter.addTab(self._seite(self.vtab, [self.nur_step] + knoepfe), "Vergleich")
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

    def _kachel(self, schluessel):
        if schluessel == "step":
            self.reiter.setCurrentIndex(1)
            self.nur_step.setChecked(True)
        elif schluessel == "vorschlaege":
            self.reiter.setCurrentIndex(2)
        elif schluessel in ("zugeordnet", "abweichung"):
            self.reiter.setCurrentIndex(1)
        else:
            self.reiter.setCurrentIndex(0)

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
        self._vergleich_fuellen()
        self._vorschlaege_laden()
        self._protokoll_laden()
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
                              status(v)] for v in self.vorschlaege], farbe=farbe, rechts=(2, 3, 4, 5, 6))

    def _protokoll_laden(self):
        self.protokoll = ll.protokoll(self.db)
        _fuellen(self.rtab, [[p["art"], p["am"].replace("T", " "), p["ebene"], p["gruppe"], _z(p["faktor"], 3),
                              p["n"], p["text"]] for p in self.protokoll],
                 farbe=lambda r: "grau" if self.protokoll[r]["art"] != "freigegeben" else None, rechts=(4, 5))

    # ------------------------------------------------------------------ Einlesen (Hintergrund, L6)
    def einlesen(self, warten=False):
        """LST-Ordner im Hintergrund lesen; warten=True (Tests): bis zum Ende."""
        if self._lauf is not None:
            return
        ordner = self.db.einstellung("lst_ordner")
        if not str(ordner or "").strip() or not pl.Path(str(ordner)).is_dir():
            self.status.setText(pl.ordner_einlesen(self.db, ordner)["fehler"][0])     # Text: kein/fehlender Ordner
            return
        pfade = pl.dateien_im_ordner(ordner)
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
        self.status.setText(f"Lese {len(pfade)} LST-Dateien im Hintergrund …")
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
        if lauf.get("fehler"):
            self.status.setText(f"Einlesen abgebrochen: {lauf['fehler']}")
            return
        erg = pl.schreiben(self.db, lauf["ergebnis"] or [])
        self.neu_laden()
        self.status.setText(pl.ergebnis_text(erg))

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
