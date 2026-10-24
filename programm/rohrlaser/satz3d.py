"""Fenster „Satz in 3D“ (Patrick 24.10.2026, Schritt 2 „A“): ein Satz aus Rohrlaserteilen, der keine
Schweißbaugruppe ist (z. B. ein Rahmen, den der Kunde als Stecksystem möchte), in der Einbaulage der STEP-Datei.

- Steckverbindungen wie im Editor der Schweißbaugruppe (gemeinsamer Code baugruppe_dialog.SteckEditor): zwei
  markierte Rohre (Reiter Teile oder Strg+Klick im 3D) oder „Alle Stöße stecken“ aus den Stößen der STEP-Messung.
  Die Rohre zeigt das 3D aus den Eingaben, mit Schlitzen und Nasen (baugruppe_ansicht.rohr_netz).
- Längsnaht per Klick: „Längsnaht wählen“ an, dann die Fläche eines Rohrs anklicken; Quadrat-/Rechteckrohr: Mitte
  der Wand, Rundrohr: genau dort. Ergebnis: feste Position, Quelle manuell (wie der Dialog Schweißnaht).
- Knickrahmen (Schritt 2b): markierte Quadrat-/Rechteckrohre, die mit Gehrung aneinanderstoßen, werden wie im
  STEP-Prüfdialog ein Knickrahmen (knickverbindung.py): eine Position mit dem gestreckten Rohr, V-Ausschnitten und
  Zusatzarbeit Knicken; die Rohre fallen weg bzw. zählen je Satz weniger. Mehrere gleiche Rahmen im Satz werden
  eine Position mit „je Satz“ = Anzahl.

Gespeichert wird je Satz in angebote.satz_daten {Satz: {steckverbindungen, stoesse}}; die Teile finden ihre
Verbindung über die Kennung in Schlitzen und Nasen (bleibt beim Kopieren des Angebots gleich). Schlitze, Nasen,
Länge und Schneidweg schreibt das Angebot mit OK (AngebotSeite.stecken_anwenden), die Längsnaht in die Felder
naht_vorgabe, naht_winkel und naht_quelle."""
import copy
import json

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                               QLabel, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from . import schneidweg as sw, steckverbindung
from .angebot import ist_baugruppe
from .baugruppe_dialog import FEHLER_FARBE, LaengsnahtEditor, SteckEditor, _text

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


def knick_messwerte(teile, netz, profil):
    """Je Körper der Teile (teile = [(Positions-ID, Position)], netz(pid) = entpacktes Netz mit lage bzw. lagen,
    profil(pid) = Profil der Stammdaten) Messwerte wie aus der STEP-Messung für knickverbindung.kette: Profil, Länge,
    Lage und die Gehrungen der Enden aus den Eingaben der Position. pid und lage_nr sagen, welcher Körper es ist."""
    out = []
    for pid, q in teile:
        n, p, e = netz(pid) or {}, profil(pid) or {}, sw.lesen(q.get("technik"))
        liste = [dict(art=art, form="Gehrung", gehrung=x["winkel"], richtung=x["richtung"])
                 for art, x in (("Ende A", e.get("a") or {}), ("Ende B", e.get("b") or {}))
                 if x.get("winkel") and x.get("richtung") is not None and x.get("achse") != sw.ACHSE_ZWEI]
        lagen = n.get("lagen") or ([n["lage"]] if n.get("lage") else [None])
        koerper = n.get("koerper") or []
        for j, lage in enumerate(lagen):
            mehr = f" ({j + 1}/{len(lagen)})" if len(lagen) > 1 else ""
            out.append(dict(artikel=f"Pos. {_text(q.get('pos'))} {q.get('artikel') or ''}".strip() + mehr,
                            koerper=koerper[j] if j < len(koerper) else None, profilform=p.get("form"),
                            abm_a=p.get("a"), abm_b=p.get("b"), wandstaerke=p.get("wand"), laenge=q.get("laenge"),
                            _netz=dict(n, lage=lage) if lage else None, konturen_liste=json.dumps(liste), pid=pid,
                            lage_nr=j))
    return out


def knick_grund(q):
    """Grund, warum die Position nicht in einen Knickrahmen kann, oder None."""
    e = sw.lesen(q.get("technik"))
    if e.get("knickrahmen"):
        return "ist schon ein Knickrahmen"
    if steckverbindung.rollen(q.get("technik")):
        return "hat eine Steckverbindung (erst entfernen)"
    return None


class _Teile(QTableWidget):
    def markierte(self):
        return sorted({i.row() for i in self.selectionModel().selectedRows()})


class Satz3dDialog(SteckEditor, LaengsnahtEditor, QDialog):
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
                      "markieren und „Knickrahmen erstellen …“.")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        teilung = QSplitter(Qt.Horizontal)
        self.reiter = QTabWidget()
        self.reiter.addTab(self._seite_teile(), "Teile")
        self.reiter.addTab(self._seite_stecken(), "Steckverbindungen")
        teilung.addWidget(self.reiter)
        from .baugruppe_ansicht import BaugruppenAnsicht
        self.ansicht3d = BaugruppenAnsicht(geaendert=self.zeigen, vor_messen=self.laengsnaht_aus)
        self.ansicht3d.naehte_knopf.hide()          # im Satz keine Nahtgruppen
        self.laengsnaht_knopf_anlegen(nur_lesen)
        self.ansicht3d.ansicht.angeklickt.connect(self.geklickt)
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
        self.aktualisieren()

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
        zeile = QHBoxLayout()
        self.knick_knopf = QPushButton("Knickrahmen erstellen …")
        self.knick_knopf.setToolTip("Markierte Quadrat- oder Rechteckrohre, die mit Gehrung aneinanderstoßen, werden ein "
                                    "Knickrahmen: eine Position mit dem gestreckten Rohr und einem V-Ausschnitt je Ecke")
        self.knick_knopf.clicked.connect(lambda: self.knick_erstellen())
        self.knick_weg_knopf = QPushButton("Knickrahmen lösen")
        self.knick_weg_knopf.setToolTip("Knickrahmen der markierten Teile wieder lösen (nur die in diesem Fenster "
                                        "erstellten)")
        self.knick_weg_knopf.clicked.connect(self.knick_loesen)
        for k in (self.knick_knopf, self.knick_weg_knopf):
            k.setEnabled(not self.nur_lesen)
            zeile.addWidget(k)
        zeile.addStretch(1)
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
        for n, t in enumerate(self.teile):
            netz = self._netz(t["_id"])
            for j, lage in enumerate(netz.get("lagen") or ([netz["lage"]] if netz.get("lage") else [])):
                if nur and t["_id"] not in hervor:
                    continue
                modell = rohre.get(t["_id"]) or netz
                netze.append(dict(modell, lage=lage))
                farbe.append(im_knick.get((t["_id"], j), n))
                self._koerper.append((t["_id"], lage, modell))
        bereiche = []
        netz, _ = zusammen(netze, {i for i, k in enumerate(self._koerper) if k[0] in hervor and not nur}, farbe,
                           bereiche=bereiche)
        ohne = len(self.teile) - len({k[0] for k in self._koerper}) if not nur else 0
        info = f"{len(netze)} Körper in Einbaulage" + (", blau = markiert" if hervor else "") + "."
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
        r = next(i for i, t in enumerate(self.teile) if t["_id"] == pid)
        if self.laengsnaht_knopf.isChecked():
            return self.laengsnaht_setzen(pid, treffer["punkt"], lage, modell)
        sel = self.teile_tab.selectionModel()
        strg = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        self.teile_tab.blockSignals(True)
        if not strg:
            self.teile_tab.clearSelection()
        if strg and r in self.teile_tab.markierte():
            sel.select(self.teile_tab.model().index(r, 0), QItemSelectionModel.Deselect | QItemSelectionModel.Rows)
        else:
            sel.select(self.teile_tab.model().index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self.teile_tab.blockSignals(False)
        self.zeigen()
        return pid

    # -------------------------------------------------------------- Knickrahmen (Schritt 2b)
    def _knick_melden(self, text, melden):
        if melden:
            QMessageBox.information(self, "Knickrahmen", text)
        return text

    def knick_erstellen(self, dialog=None, melden=True):
        """Knickrahmen aus den markierten Rohren (alle ihre Körper, ohne die schon verbundenen) wie im STEP-Prüfdialog:
        Kette erkennen, Dialog (erster Schenkel, Laufrichtung, Freistich, Zugabe, K-Faktor, Innenwand), gestreckte
        Eingaben und gefaltetes Netz. Mehrere getrennte Rahmen bekommen dieselben Werte. dialog(d) bedient den Dialog
        statt exec (Tests). Ergebnis: Anzahl neuer Knickrahmen bzw. Text, warum keiner geht."""
        from . import knickverbindung as kv
        from .knickrahmen_dialog import KnickverbindungDialog
        if self.nur_lesen:
            return 0
        teile = [self.teile[r] for r in self.teile_tab.markierte() if r < len(self.teile)]
        if len(teile) < 1:
            return self._knick_melden("Rohre markieren (Reiter Teile oder Strg+Klick im 3D), die mit Gehrung "
                                      "aneinanderstoßen.", melden)
        for t in teile:
            grund = knick_grund(t["_q"])
            if grund:
                return self._knick_melden(f"Pos. {_text(t['_q'].get('pos'))}: {grund}.", melden)
        belegt = {kp for k in self.knicke for kp in k["koerper"]}
        steck = {z.get(r) for z in self.bg["steckverbindungen"] for r in ("_auf", "_st")}
        if steck & {t["_id"] for t in teile}:
            return self._knick_melden("Ein markiertes Teil hat eine Steckverbindung (erst im Reiter Steckverbindungen "
                                      "entfernen).", melden)
        mw = [m for m in knick_messwerte([(t["_id"], t["_q"]) for t in teile], self._netz, self._steck_profil)
              if (m["pid"], m["lage_nr"]) not in belegt]
        gruppen = kv.vorschlaege(mw)
        if not gruppen:
            try:
                kv.kette(mw, list(range(len(mw))))
                grund = "Die markierten Rohre ergeben keinen Knickrahmen."
            except ValueError as f:
                grund = str(f)
            return self._knick_melden(grund, melden)
        vorgaben = {n: self.einstellungen.get(f"knick_{n}") for n in ("z", "freistich", "k")}
        try:
            d = KnickverbindungDialog(self, mw, gruppen[0], vorgaben)
        except ValueError as f:
            return self._knick_melden(str(f), melden)
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
            return 0
        werte = d.werte()
        start_pid = mw[d.kette["teile"][0]["i"]]["pid"]
        neu = []
        try:
            for nr, gruppe in enumerate(gruppen):
                if nr == 0:
                    k = d.kette
                else:
                    start = next((i for i in gruppe if mw[i]["pid"] == start_pid), None)
                    k = kv.kette(mw, gruppe, start, d.umkehren.isChecked())
                leit = kv.erstellen(mw, k, **werte)
                m = mw[leit]
                profil = dict(self._steck_profil(m["pid"]) or {})
                je_teil = {t["i"]: sw.lesen(self._teil_q(mw[t["i"]]["pid"]).get("technik")) for t in k["teile"]}
                eing, _ = kv.eingaben(m, je_teil, profil)
                neu.append(dict(koerper=[(mw[t["i"]]["pid"], mw[t["i"]]["lage_nr"]) for t in k["teile"]],
                                leit=m["pid"], eingaben=eing, netz=kv.netz_gefaltet(mw, m), text=kv.text(m)))
        except ValueError as f:
            return self._knick_melden(str(f), melden)
        self.knicke += neu
        self.aktualisieren()
        return len(neu)

    def _teil_q(self, pid):
        return next(t["_q"] for t in self.teile if t["_id"] == pid)

    def knick_loesen(self):
        """Neue Knickrahmen, zu denen die markierten Teile gehören, wieder lösen. Ergebnis: Anzahl gelöster."""
        ids = {self.teile[r]["_id"] for r in self.teile_tab.markierte() if r < len(self.teile)}
        vorher = len(self.knicke)
        self.knicke = [k for k in self.knicke if not ids & {pid for pid, _ in k["koerper"]}]
        if len(self.knicke) != vorher:
            self.aktualisieren()
        return vorher - len(self.knicke)

    # -------------------------------------------------------------- Speichern
    def pruefen(self):
        for n, z in enumerate(self.bg["steckverbindungen"], 1):
            f = self._steck_fehler(z)
            if f:
                return f"Steckverbindung {n}: {f}"
        im_knick = {pid for k in self.knicke for pid, _ in k["koerper"]}
        for n, z in enumerate(self.bg["steckverbindungen"], 1):
            if {z.get("_auf"), z.get("_st")} & im_knick:
                return f"Steckverbindung {n}: Teil ist in einem neuen Knickrahmen (erst Knickrahmen lösen)."
        return None

    def werte(self):
        verbindungen = [self._steck_daten(z) for z in self.bg["steckverbindungen"]]
        weg, dazu = steckverbindung.aenderungen(self.steck_alt, verbindungen)
        return dict(stecken=dict(weg=weg, dazu=dazu), naehte=self.laengsnaht_werte(), knicke=list(self.knicke),
                    daten=dict(steckverbindungen=verbindungen, stoesse=self.bg["stoesse"]))

    def _ok(self):
        if self.nur_lesen:
            return
        f = self.pruefen()
        if f:
            self.fehler.setText(f)
            return
        self.ergebnis = self.werte()
        self.accept()
