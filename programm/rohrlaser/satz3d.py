"""Fenster „Satz in 3D“ (Patrick 24.10.2026, Schritt 2 „A“): ein Satz aus Rohrlaserteilen, der keine
Schweißbaugruppe ist (z. B. ein Rahmen, den der Kunde als Stecksystem möchte), in der Einbaulage der STEP-Datei.

- Steckverbindungen wie im Editor der Schweißbaugruppe (gemeinsamer Code baugruppe_dialog.SteckEditor): zwei
  markierte Rohre (Reiter Teile oder Strg+Klick im 3D) oder „Alle Stöße stecken“ aus den Stößen der STEP-Messung.
  Die Rohre zeigt das 3D aus den Eingaben, mit Schlitzen und Nasen (baugruppe_ansicht.rohr_netz).
- Längsnaht per Klick: „Längsnaht wählen“ an, dann die Fläche eines Rohrs anklicken; Quadrat-/Rechteckrohr: Mitte
  der Wand, Rundrohr: genau dort. Ergebnis: feste Position, Quelle manuell (wie der Dialog Schweißnaht).
- Auswahl im 3D (Patrick 26.10.2026): Klick auf ein Teil (auch nahe einer Kante) markiert es in der Liste, Strg+Klick
  nimmt es dazu bzw. weg; auf dem Reiter Steckverbindungen markiert der Klick die Verbindungen des Teils (zwei Teile:
  die Verbindung zwischen ihnen), eine Zeile dort zeigt Aufnahme und Stecker blau. Doppelklick wählt die ganze
  Gehrungskette, Rechtsklick öffnet ein Menü (AuswahlEditor).
- Knickrahmen (Schritt 2b): markierte Quadrat-/Rechteckrohre, die mit Gehrung aneinanderstoßen, werden wie im
  STEP-Prüfdialog ein Knickrahmen (knickverbindung.py): eine Position mit dem gestreckten Rohr, V-Ausschnitten und
  Zusatzarbeit Knicken; die Rohre fallen weg bzw. zählen je Satz weniger. Mehrere gleiche Rahmen im Satz werden
  eine Position mit „je Satz“ = Anzahl.

Gespeichert wird je Satz in angebote.satz_daten {Satz: {steckverbindungen, stoesse}}; die Teile finden ihre
Verbindung über die Kennung in Schlitzen und Nasen (bleibt beim Kopieren des Angebots gleich). Schlitze, Nasen,
Länge und Schneidweg schreibt das Angebot mit OK (AngebotSeite.stecken_anwenden), die Längsnaht in die Felder
naht_vorgabe, naht_winkel und naht_quelle."""
import copy

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QHeaderView,
                               QLabel, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from . import schneidweg as sw, steckverbindung, tastatur
from .angebot import ist_muster
from .muster_haken import MusterHaken
from .angebot import ist_baugruppe
from .baugruppe_dialog import (FEHLER_FARBE, AuswahlEditor, KnickEditor, LaengsnahtEditor, MontageEditor, SteckEditor, VorschlagEditor,
                               _text, teile_markieren)
from .baugruppe_step import StepBaugruppe

TEIL = "teil:"              # Kennung der Dreiecke im 3D: teil:<Nummer des Körpers>


def satz_teile(positionen, satz):
    """Indizes der Positionen des Satzes (ohne Schweißbaugruppen-Position)."""
    return [i for i, q in enumerate(positionen) if satz and (q.get("satz") or None) == satz and not ist_baugruppe(q)]


def saetze(positionen):
    """Namen der Sätze im Angebot, in der Reihenfolge der Positionen."""
    out = []
    for q in positionen:
        s = q.get("satz")
        if s and s not in out and not ist_baugruppe(q):
            out.append(s)
    return out


def verbindungen_laden(daten, positionen, indizes):
    """Gespeicherte Verbindungen des Satzes mit den heutigen Positions-IDs (Suche über die Kennung, sonst die alte
    ID); Verbindungen, deren Teile fehlen, fallen weg."""
    out = []
    for v in steckverbindung.liste(daten):
        auf, st = steckverbindung.teile_finden(positionen, indizes, v["id"], v)
        if auf is None or st is None:
            continue
        v = copy.deepcopy(v)
        v["aufnahme"] = dict(v.get("aufnahme") or {}, id=positionen[auf]["id"], pos=positionen[auf].get("pos"))
        v["stecker"] = dict(v.get("stecker") or {}, id=positionen[st]["id"], pos=positionen[st].get("pos"))
        out.append(v)
    return out


class _Teile(QTableWidget):
    def markierte(self):
        return sorted({i.row() for i in self.selectionModel().selectedRows()})


class Satz3dDialog(SteckEditor, LaengsnahtEditor, KnickEditor, VorschlagEditor, MontageEditor, AuswahlEditor,
                   StepBaugruppe, QDialog):
    """satz: Name des Satzes; positionen: alle Positionen des Angebots; daten: gespeicherte Daten des Satzes
    (db.satz_daten); netze {Positions-ID: Netz-Bytes}. Ergebnis nach OK in self.ergebnis: dict(stecken = dict(weg,
    dazu), naehte = {Positions-ID: Nahtfelder}, daten = Daten des Satzes zum Speichern, knicke = neue Knickrahmen
    [dict(koerper = [(Positions-ID, Nr. der Lage)], leit, eingaben, netz, text)])."""
    STECK_WAS = "Satz"
    STECK_MARKIEREN = "im Reiter „Teile“ (oder im 3D mit Strg+Klick)"
    STECK_OHNE_STOESSE = ("Die Lage der Rohrenden kennt nur ein Satz, der mit diesem Programmstand aus der STEP-Datei "
                          "eingelesen wurde (Datei neu einlesen).")

    def __init__(self, parent, satz, positionen, profile=None, einstellungen=None, netze=None, daten=None,
                 nur_lesen=False):
        super().__init__(parent)
        self.setWindowTitle(f"Satz in 3D: {satz}")
        self.resize(1400, 860)
        self.satz, self.positionen, self.nur_lesen = satz, positionen, nur_lesen
        self.profile = profile or getattr(getattr(parent, "k", None), "profile", None) or {}
        self.einstellungen = einstellungen or {}
        self.netze, self._netz_cache = netze or {}, {}
        indizes = satz_teile(positionen, satz)
        self.teile = [dict(_id=positionen[i]["id"], _q=positionen[i], drin=True, knoten="") for i in indizes]
        daten = daten or {}
        verbindungen = verbindungen_laden(daten, positionen, indizes)
        self.steck_alt = copy.deepcopy(verbindungen)
        self.bg = dict(steckverbindungen=[self._steck_flach(v) for v in verbindungen],
                       stoesse=[s_ for s_ in daten.get("stoesse") or () if isinstance(s_, dict)])
        self.laengsnaehte = {}      # Positions-ID -> Nahtwinkel (per Klick gewählt)
        self.knicke = []            # neue Knickrahmen (mit OK zu Positionen)
        self.ergebnis, self._koerper = None, []

        lay = QVBoxLayout(self)
        kopf = QLabel(f"<b>Satz {satz}</b>: {len(self.teile)} Teile in der Einbaulage der STEP-Datei. Zwei Rohre "
                      "markieren (Reiter Teile oder Strg+Klick im 3D) und „Steckverbindung hinzufügen“, oder „Alle Stöße "
                      "stecken“; Längsnaht: „Längsnaht wählen“ und die Fläche eines Rohrs anklicken; Rohre mit Gehrung: "
                      "markieren (Doppelklick im 3D wählt die ganze Kette) und „Knickrahmen erstellen …“. Rechtsklick "
                      "im 3D: Menü.")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        # Musterteil (Patrick 28.10.2026): in allen Editoren gleich; hier für alle Teile des Satzes
        self.muster_haken = MusterHaken(dict(muster="ja") if self.teile and all(
            ist_muster(t["_q"]) for t in self.teile) else None)
        self.muster_haken.setText("Satz als Muster")
        self.muster_haken.setEnabled(not nur_lesen)
        lay.addWidget(self.muster_haken)
        teilung = QSplitter(Qt.Horizontal)
        self.reiter = QTabWidget()
        self.reiter.addTab(self._seite_teile(), "Teile")
        self.reiter.addTab(self._seite_stecken(), "Steckverbindungen")
        self._sync = False
        self.steck_tab.itemSelectionChanged.connect(self._steck_gewaehlt)
        self.reiter.currentChanged.connect(lambda _: (self._steck_aus_teilen(), self.zeigen()))
        teilung.addWidget(self.reiter)
        from .baugruppe_ansicht import BaugruppenAnsicht
        self.ansicht3d = BaugruppenAnsicht(geaendert=self.zeigen, vor_messen=self.laengsnaht_aus)
        self.ansicht3d.naehte_knopf.hide()          # im Satz keine Nahtgruppen
        self.laengsnaht_knopf_anlegen(nur_lesen)
        self.montage_knopf_anlegen()
        self.ansicht3d.ansicht.angeklickt.connect(self.geklickt)
        self.auswahl_signale()
        teilung.addWidget(self.ansicht3d)
        teilung.setSizes([560, 840])
        lay.addWidget(teilung, 1)
        self.fehler = QLabel()
        self.fehler.setStyleSheet(f"color: {FEHLER_FARBE};")
        self.fehler.setWordWrap(True)
        lay.addWidget(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        knoepfe.button(QDialogButtonBox.Ok).setEnabled(not nur_lesen)
        lay.addWidget(knoepfe)
        tastatur.enter_sperren(self)        # Enter nach einer Eingabe schließt das Fenster nicht
        self.aktualisieren()
        self.vorschlaege_info_neu()

    # -------------------------------------------------------------- Teile
    def _seite_teile(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.teile_tab = _Teile(0, 6)
        self.teile_tab.setHorizontalHeaderLabels(["Pos.", "Artikel", "Profil", "Länge [mm]", "Längsnaht",
                                                  "Knickrahmen"])
        self.teile_tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.teile_tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.teile_tab.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.teile_tab.itemSelectionChanged.connect(self.zeigen)
        lay.addWidget(self.teile_tab, 1)
        zeile = self.knick_knoepfe()
        zeile.insertWidget(zeile.count() - 1, self.step_knopf())
        lay.addLayout(zeile)
        return w

    def _teile_fuellen(self):
        tab = self.teile_tab
        mark = set(tab.markierte())
        tab.blockSignals(True)
        tab.setRowCount(len(self.teile))
        for r, t in enumerate(self.teile):
            q = t["_q"]
            w = self.laengsnaht(t["_id"])
            nahttext = (f"{_text(w, 0)}°" + (" (neu, per Klick)" if t["_id"] in self.laengsnaehte else "")) \
                if w is not None else (q.get("naht_vorgabe") or "")
            knick = ", ".join(f"Knickrahmen {n} (neu)" for n, k in enumerate(self.knicke, 1)
                              if any(pid == t["_id"] for pid, _ in k["koerper"]))
            if not knick and sw.lesen(q.get("technik")).get("knickrahmen"):
                knick = "ist Knickrahmen"
            for c, text in enumerate((_text(q.get("pos")), q.get("artikel") or "", q.get("profil_id") or "",
                                      _text(q.get("laenge"), 1), nahttext, knick)):
                tab.setItem(r, c, QTableWidgetItem(str(text)))
        tab.clearSelection()
        for r in mark:
            if r < len(self.teile):
                tab.selectionModel().select(tab.model().index(r, 0),
                                            QItemSelectionModel.Select | QItemSelectionModel.Rows)
        tab.blockSignals(False)

    # -------------------------------------------------------------- 3D
    def aktualisieren(self):
        """Nach jeder Eingabe: Teileliste, Prüfung der Verbindungen und 3D neu."""
        if hasattr(self, "steck_tab"):
            self.steck_tab.auffrischen()
        self._teile_fuellen()
        self.fehler.setText(self.pruefen() or "")
        self.zeigen()

    def zeigen(self):
        """Alle Körper des Satzes in Einbaulage, markierte Teile blau, Rohre aus den Eingaben (Schlitze und Nasen),
        Längsnähte rot. Ergebnis: Anzahl gezeigter Körper."""
        from .ansicht3d import baugruppe as zusammen
        from .baugruppe_ansicht import teil_kennung
        if not hasattr(self, "ansicht3d"):
            return 0
        hervor = {self.teile[r]["_id"] for r in self.teile_tab.markierte() if r < len(self.teile)}
        nur = bool(hervor) and self.ansicht3d.nur_gewaehlt
        rohre = self._rohr_modelle()
        netze, farbe, self._koerper = [], [], []
        reihe = {t["_id"]: n for n, t in enumerate(self.teile)}
        im_knick = {kp: reihe.get(k["leit"], 0) for k in self.knicke for kp in k["koerper"]}   # Rahmen in einer Farbe
        montage, aktuell = self.montage_berechnen(), set()
        for n, t in enumerate(self.teile):
            netz = self._netz(t["_id"])
            nummern = netz.get("koerper") or []
            for j, lage in enumerate(netz.get("lagen") or ([netz["lage"]] if netz.get("lage") else [])):
                if nur and t["_id"] not in hervor:
                    continue
                if montage:
                    lage, akt = self.montage_lage(nummern[j] if j < len(nummern) else None, lage)
                    if lage is None:
                        continue
                    if akt:
                        aktuell.add(len(netze))
                modell = rohre.get(t["_id"]) or netz
                netze.append(dict(modell, lage=lage))
                farbe.append(im_knick.get((t["_id"], j), n))
                self._koerper.append((t["_id"], lage, modell))
        bereiche = []
        netz, _ = zusammen(netze, {i for i, k in enumerate(self._koerper) if k[0] in hervor and not nur} | aktuell,
                           farbe, bereiche=bereiche)
        ohne = len(self.teile) - len({k[0] for k in self._koerper}) if not nur else 0
        info = f"{len(netze)} Körper in Einbaulage" + (
            f", blau = markiert ({self._markiert_text()})" if hervor else
            ", Klick auf ein Teil markiert es, Strg+Klick nimmt Teile dazu") + "."
        if netz:
            teil_kennung(netz, bereiche, [f"{TEIL}{i}" for i in range(len(netze))])
            nl = self.laengsnaht_linien(self._koerper)
            if nl:
                netz["l"]["NL"] = nl
                info += " Längsnähte rot."
            if self.knicke:
                info += f" {len(self.knicke)} neue{'r' if len(self.knicke) == 1 else ''} Knickrahmen je in einer Farbe."
            if rohre:
                info += " Rohre aus den Eingaben (mit Schlitzen und Nasen der Steckverbindungen)."
        if ohne:
            info += f" {ohne} Teil{'e' if ohne != 1 else ''} ohne 3D-Daten (nicht aus dem STEP-Import) fehlen."
        self.ansicht3d.setzen(netz, f"Satz {self.satz}", info)
        return len(netze)

    def geklickt(self, treffer):
        """Klick im 3D: Längsnaht setzen (Modus an) bzw. Teil markieren (Strg: dazu/weg)."""
        kennung = str((treffer or {}).get("id") or "")
        if not kennung.startswith(TEIL):
            return None
        nr = int(kennung[len(TEIL):])
        if nr >= len(self._koerper):
            return None
        pid, lage, modell = self._koerper[nr]
        if self.laengsnaht_knopf.isChecked():
            return self.laengsnaht_setzen(pid, treffer["punkt"], lage, modell)
        strg = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        ids = [self.teile[r]["_id"] for r in self.teile_tab.markierte() if r < len(self.teile)] if strg else []
        self.auswahl_setzen([x for x in ids if x != pid] if pid in ids else ids + [pid])
        return pid

    def auswahl(self):
        """Markierte Teile (Positions-IDs) in Klickfolge."""
        ids = [self.teile[r]["_id"] for r in self.teile_tab.markierte() if r < len(self.teile)]
        folge = [x for x in getattr(self, "_folge", []) if x in ids]
        return folge + [x for x in ids if x not in folge]

    def auswahl_setzen(self, ids):
        self._folge = list(ids)
        self.teile_markieren(ids)
        self._steck_aus_teilen()
        self.zeigen()

    def teile_markieren(self, ids):
        """Zeilen der Teile ids (Positions-IDs) im Reiter Teile markieren, ohne Neuzeichnen."""
        teile_markieren(self.teile_tab, self.teile, ids)

    def _markiert_text(self):
        pos = [_text(self.teile[r]["_q"].get("pos")) for r in self.teile_tab.markierte() if r < len(self.teile)]
        return "Pos. " + ", ".join(pos)

    def _steck_aus_teilen(self):
        """Auf dem Reiter Steckverbindungen: die Verbindungen der markierten Teile markieren (ein Teil: alle seine,
        mehrere: die zwischen ihnen)."""
        if self.reiter.currentIndex() != 1:
            return
        ids = {self.teile[r]["_id"] for r in self.teile_tab.markierte() if r < len(self.teile)}
        tab, sel = self.steck_tab, self.steck_tab.selectionModel()
        self._sync = True
        tab.clearSelection()
        for r, z in enumerate(self.bg["steckverbindungen"]):
            paar = {z.get("_auf"), z.get("_st")}
            if (paar & ids if len(ids) == 1 else paar <= ids) and r < tab.rowCount():
                sel.select(tab.model().index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self._sync = False
        zeilen = tab.markierte()
        if zeilen:
            tab.scrollTo(tab.model().index(zeilen[0], 0))

    def _steck_gewaehlt(self):
        """Zeile im Reiter Steckverbindungen gewählt: Aufnahme und Stecker im 3D blau (und im Reiter Teile markiert)."""
        if self._sync:
            return
        zeilen = self.bg["steckverbindungen"]
        self.teile_markieren({zeilen[r].get(k) for r in self.steck_tab.markierte() if r < len(zeilen)
                              for k in ("_auf", "_st")})
        self.zeigen()

    # -------------------------------------------------------------- Speichern
    def step_name(self):
        return f"Satz {self.satz}"

    def pruefen(self):
        for n, z in enumerate(self.bg["steckverbindungen"], 1):
            f = self._steck_fehler(z)
            if f:
                return f"Steckverbindung {n}: {f}"
        return self.knick_pruefen()

    def werte(self):
        verbindungen = [self._steck_daten(z) for z in self.bg["steckverbindungen"]]
        weg, dazu = steckverbindung.aenderungen(self.steck_alt, verbindungen)
        return dict(stecken=dict(weg=weg, dazu=dazu), naehte=self.laengsnaht_werte(), knicke=list(self.knicke),
                    teilen=list(getattr(self, "steck_getrennt", [])), lagen=dict(getattr(self, "steck_lagen", {})),
                    daten=dict(steckverbindungen=verbindungen, stoesse=self.bg["stoesse"]),
                    **self.muster_haken.geaendert())

    def _ok(self):
        if self.nur_lesen:
            return
        f = self.pruefen()
        if f:
            self.fehler.setText(f)
            return
        self.ergebnis = self.werte()
        self.accept()
