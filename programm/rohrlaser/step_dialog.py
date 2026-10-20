"""Dialoge mit 3D-Ansicht: Prüfen der STEP-Messung vor dem Übernehmen und Ansehen der Positionen eines Angebots."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .ansicht3d import Ansicht3DMitKnoepfen
from .fenster import liste_fuellen
from .stammdaten import zahl_als_text

def _f(m, name):
    try:
        return float(m.get(name) or 0)
    except ValueError:
        return 0.0


def _messinfo(m):
    from . import step
    if m.get("fehler"):
        return f"<b style='color:#C00000'>FEHLER: {m['fehler']}</b>"
    z = lambda name, st=1: zahl_als_text(_f(m, name), st)
    status = m.get("pruefstatus") or ""
    farbe = {"plausibel": "#375623", "prüfen": "#9C5700", "nicht messbar": "#C00000"}.get(status, "#000000")
    unsicher = step.unsicher(m)
    b = step.blech(m)
    if b is not None:
        bo = ", ".join(f"{n}× Ø{zahl_als_text(float(d), 1)}" for d, n in (b.get("bohrungen") or {}).items())
        return (f"<b>{m.get('artikel')}</b>: {step.blech_text(m)}, Kontur {b.get('kontur') or ''}, "
                f"{b.get('innen') or 0} Innenkonturen" + (f" (Bohrungen {bo})" if bo else "")
                + (f" · {m['hinweise']}" if m.get("hinweise") else "")
                + (f"<br><b style='color:{farbe}'>Prüfstatus: {status}</b>" if status else ""))
    return (f"<b>{m.get('artikel')}</b>: {m.get('profilform')} {m.get('profil_id_vorschlag') or ''}, Länge {z('laenge')} mm, "
            f"Schneidweg {z('schneidweg')} mm (Anfangsschnitt {z('ende_a')}, Endschnitt {z('ende_b')}, Innenkonturen "
            f"{z('innen')} mm in {m.get('innen_konturen') or 0} Konturen), Gravur {z('gravur')} mm, Einstiche "
            f"{m.get('konturen') or 0}" + (f" · {m['hinweise']}" if m.get("hinweise") else "")
            + (f"<br><b style='color:{farbe}'>Prüfstatus: {status}</b>" if status else "")
            + (f" · unsicher: {', '.join(unsicher)} (erst nach Anhaken übernommen)" if unsicher else ""))


class _Mit3D(QDialog):
    def __init__(self, parent, titel, spalten):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.resize(1250, 680)
        self.liste = QTableWidget(0, len(spalten))
        self.liste.setHorizontalHeaderLabels(spalten)
        self.liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.liste.setSelectionMode(QAbstractItemView.SingleSelection)
        self.liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.liste.verticalHeader().setDefaultSectionSize(22)
        self.liste.currentCellChanged.connect(lambda r, *_: self._zeigen(r))
        self.ansicht = Ansicht3DMitKnoepfen()
        teil = QSplitter(Qt.Horizontal)
        teil.addWidget(self.liste)
        teil.addWidget(self.ansicht)
        teil.setSizes([520, 730])
        self.lay = QVBoxLayout(self)
        self.lay.addWidget(teil, 1)

    def _fuellen(self, zeilen):
        self.liste.setRowCount(len(zeilen))
        for r, werte in enumerate(zeilen):
            for c, w in enumerate(werte):
                it = QTableWidgetItem("" if w is None else str(w))
                if isinstance(w, (int, float)):
                    it.setText(zahl_als_text(w, 1 if isinstance(w, float) else 0))
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.liste.setItem(r, c, it)
        self.liste.resizeColumnsToContents()


class _Zeile:
    """Eine Zeile der Rohrliste: gleiche Teile einer Datei. werte = Stückzahl je Modus ('einzeln' bzw. 'satz' =
    Stück je Satz); der Spin zeigt den Wert des Modus der Datei."""

    def __init__(self, it, liste, pr, ws, sp, vorschlag, datei, stueck, je_satz):
        self.it, self.liste, self.pr, self.ws, self.sp, self.vorschlag, self.datei = it, liste, pr, ws, sp, vorschlag, datei
        self.werte = {"einzeln": stueck or 0, "satz": je_satz}


class StepPruefDialog(QDialog):
    """Gemessene Rohre je STEP-Datei und Profil mit 3D-Ansicht. Oben Pfeile zum Wechseln der Datei und bei Dateien
    mit mehreren Teilen das Feld 'Sätze' (leer = Einzelpositionen). Je Teil übernehmen ja/nein, Profil, Werkstoff
    und Stückzahl (bei einem Satz: Stück je Satz); gleiche Teile einer Datei stehen in einer Zeile (Spalte
    'In Datei'). OK schreibt die Werte als _uebernehmen, _profil, _werkstoff, _stueck, _saetze, _je_satz in die
    Messwerte (step.uebernehmen liest sie)."""
    SPALTEN = ("Teil", "In Datei", "Profil-ID", "Werkstoff-ID", "Stückzahl", "Länge [mm]", "Schneidweg [mm]",
               "Konturen", "Hinweis")

    def __init__(self, parent, messwerte, k, werkstoff=None, stueck=None):
        from . import step
        super().__init__(parent)
        self.messwerte, self.k = messwerte, k
        self.setWindowTitle(f"STEP-Import prüfen ({len(messwerte)} Teil{'e' if len(messwerte) != 1 else ''})")
        self.resize(1350, 720)
        self.dateien = list(dict.fromkeys(m.get("datei") for m in messwerte))
        self.mehrteilig = step.mehrteilig(messwerte)
        self.saetze = {d: 0 for d in self.dateien}      # Datei -> Sätze (0 = leer = Einzelpositionen)
        for m in messwerte:
            if m.get("_saetze") and m.get("datei") in self.mehrteilig:
                self.saetze[m["datei"]] = int(m["_saetze"])
        self.datei_nr = 0

        # Kopfzeile: Datei wechseln, Sätze
        self.kopf = QWidget()
        kl = QHBoxLayout(self.kopf)
        kl.setContentsMargins(0, 0, 0, 0)
        self.zurueck, self.vor = QPushButton("◀"), QPushButton("▶")
        for b, schritt, tipp in ((self.zurueck, -1, "Vorige STEP-Datei"), (self.vor, 1, "Nächste STEP-Datei")):
            b.setFixedWidth(36)
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, s=schritt: self.datei_waehlen(self.datei_nr + s))
        self.datei_text = QLabel()
        f = self.datei_text.font()
        f.setBold(True)
        self.datei_text.setFont(f)
        self.satz_feld = QWidget()
        sl = QHBoxLayout(self.satz_feld)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(QLabel("Sätze:"))
        self.satz_spin = QSpinBox()
        self.satz_spin.setRange(0, 100000)
        self.satz_spin.setSpecialValueText("leer")
        self.satz_spin.setToolTip("Anzahl Sätze dieser Baugruppe. Leer = jedes Teil als Einzelposition laden.")
        self.satz_spin.valueChanged.connect(lambda n: self.saetze_setzen(n))
        sl.addWidget(self.satz_spin)
        self.satz_info = QLabel()
        kl.addWidget(self.zurueck)
        kl.addWidget(self.vor)
        kl.addSpacing(6)
        kl.addWidget(self.datei_text)
        kl.addSpacing(24)
        kl.addWidget(self.satz_feld)
        kl.addWidget(self.satz_info)
        kl.addStretch(1)

        self.baum = QTreeWidget()
        self.baum.setColumnCount(len(self.SPALTEN))
        self.baum.setHeaderLabels(self.SPALTEN)
        self.baum.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.baum.setUniformRowHeights(True)
        self.baum.setStyleSheet("QTreeView::item { min-height: 26px; }")     # Platz für Auswahlfelder
        self.baum.currentItemChanged.connect(lambda it, *_: self._zeigen(it))
        self.zeilen = []        # _Zeile je Gruppe gleicher Teile einer Datei
        self.gruppen = {}       # (Datei, gemessenes Profil) -> Gruppen-Item
        teile = step.gleiche_teile(messwerte)
        fehler = [i for i, m in enumerate(messwerte) if not any(i in l for l in teile.values())]
        profile = k.auswahl("profil")
        reihe = sorted(teile.items(), key=lambda e: (self.dateien.index(messwerte[e[0]].get("datei")),
                                                     step.profil_vorschlag(messwerte[e[0]], k.profile) or ""))
        for erster, liste in reihe:
            m = messwerte[erster]
            datei = m.get("datei")
            vorschlag = step.profil_vorschlag(m, k.profile)
            fehlt = vorschlag not in k.profile
            g = self.gruppen.get((datei, vorschlag))
            if g is None:
                g = self.gruppen[(datei, vorschlag)] = QTreeWidgetItem(self.baum)
                g.setFirstColumnSpanned(True)
                g.setData(0, Qt.UserRole, vorschlag)
                f = g.font(0)
                f.setBold(True)
                g.setFont(0, f)
                g.setBackground(0, QBrush(QColor("#FCE4D6" if fehlt else "#DDEBF7")))
                g.setExpanded(True)
            it = QTreeWidgetItem(g)
            it.setText(0, m.get("artikel") or m.get("datei") or "")
            it.setCheckState(0, Qt.Checked if step.gewaehlt(m) else Qt.Unchecked)
            it.setText(1, str(len(liste)))
            for c, w in ((5, _f(m, "laenge")), (6, _f(m, "schneidweg"))):
                it.setText(c, zahl_als_text(w, 1))
            it.setText(7, str(int(_f(m, "konturen"))))
            hinweis = ["Profil fehlt in den Stammdaten"] if fehlt else []
            if step.unsicher(m):
                hinweis.append("UNSICHER: " + ", ".join(step.unsicher(m)) + " – zum Übernehmen anhaken")
            hinweis += [h for h in [m.get("hinweise")] if h]
            it.setText(8, "; ".join(hinweis))
            if m.get("pruefstatus") == "prüfen":
                it.setBackground(8, QBrush(QColor("#FFEB9C")))
            for c in (1, 4, 5, 6, 7):
                it.setTextAlignment(c, int(Qt.AlignRight | Qt.AlignVCenter))
            pr = QComboBox()
            pr.setEditable(True)            # neue Profil-ID eintippen: wird beim Übernehmen angelegt (Rückfrage)
            pr.addItems(sorted(set(profile) | ({vorschlag} if vorschlag else set())))
            pr.setCurrentText(m.get("_profil") or vorschlag or "")
            ws = QComboBox()
            liste_fuellen(ws, k, "werkstoff")
            ws.setCurrentText(m.get("_werkstoff", werkstoff) or "")
            sp = QSpinBox()
            sp.setRange(0, 100000)
            sp.setSpecialValueText("leer")
            for c, w in ((2, pr), (3, ws), (4, sp)):
                self.baum.setItemWidget(it, c, w)
            it.setData(0, Qt.UserRole, len(self.zeilen))
            z = _Zeile(it, liste, pr, ws, sp, vorschlag, datei,
                       m["_stueck"] if "_stueck" in m and not m.get("_saetze") else stueck,
                       m.get("_je_satz") or len(liste))
            sp.setValue(z.werte[self._modus(datei)])
            sp.valueChanged.connect(lambda v, z=z: z.werte.__setitem__(self._modus(z.datei), v))
            self.zeilen.append(z)
        self.fehler_gruppen = {}
        for i in fehler:
            m = messwerte[i]
            g = self.fehler_gruppen.get(m.get("datei"))
            if g is None:
                g = self.fehler_gruppen[m.get("datei")] = QTreeWidgetItem(self.baum, ["Nicht übernehmbar"])
                g.setFirstColumnSpanned(True)
                g.setBackground(0, QBrush(QColor("#F8CBAD")))
                g.setExpanded(True)
            it = QTreeWidgetItem(g, [f"{m.get('datei')} Körper {m.get('koerper') or ''}", "", "", "", "", "",
                                     "", "", m.get("fehler") or (step.blech_text(m) + ": kein Rohrlaserteil" if step.blech(m) else "")
                                     or m.get("hinweise") or "kein Rohrteil erkannt"])
            it.setData(1, Qt.UserRole, i)
        for c, b in enumerate((250, 55, 130, 120, 75, 80, 95, 65, 260)):
            self.baum.setColumnWidth(c, b)

        # Werte für mehrere Teile auf einmal
        self.leiste = QWidget()
        alle = QHBoxLayout(self.leiste)
        alle.setContentsMargins(0, 0, 0, 0)
        alle.addWidget(QLabel("Werte setzen:"))
        self.alle_ws = QComboBox()
        liste_fuellen(self.alle_ws, k, "werkstoff", "(Werkstoff)")
        self.alle_stk = QSpinBox()
        self.alle_stk.setRange(0, 100000)
        self.alle_stk.setSpecialValueText("(Stückzahl)")
        alle.addWidget(self.alle_ws)
        alle.addWidget(self.alle_stk)
        for text, nur, tipp in (("Für markierte", True, "Markierte Zeilen dieser Datei"),
                                ("Für alle", False, "Alle Teile aller STEP-Dateien")):
            b = QPushButton(text)
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, nur=nur: self.alle_setzen(nur_markierte=nur))
            alle.addWidget(b)
        alle.addSpacing(12)
        for text, an in (("Alle wählen", True), ("Keine wählen", False)):
            b = QPushButton(text)
            b.setToolTip("Alle Teile aller STEP-Dateien")
            b.clicked.connect(lambda _=False, an=an: self.alle_waehlen(an))
            alle.addWidget(b)
        alle.addStretch(1)

        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.kopf)
        ll.addWidget(self.baum, 1)
        ll.addWidget(self.leiste)
        self.ansicht = Ansicht3DMitKnoepfen()
        teil = QSplitter(Qt.Horizontal)
        teil.addWidget(links)
        teil.addWidget(self.ansicht)
        teil.setSizes([820, 530])
        lay = QVBoxLayout(self)
        lay.addWidget(teil, 1)
        hinweis = QLabel("Häkchen = Teil übernehmen. Profil, Werkstoff und Stückzahl je Teil wählen; leer = später "
                         "eintragen. Mit ◀ ▶ zwischen den STEP-Dateien wechseln; Übernehmen übernimmt alle Dateien. "
                         "Enthält eine Datei mehrere Teile, oben die Anzahl Sätze eintragen (leer = Einzelpositionen); "
                         "die Spalte zeigt dann Stück je Satz, Stückzahl = Sätze × Stück je Satz. Mehrere Zeilen "
                         "markieren (Strg/Umschalt) und unten Werte setzen; „Für alle“ gilt für alle Dateien. In der "
                         "3D-Ansicht: Anfangsschnitt orange, Endschnitt violett, Innenkonturen rot, Gravur grün.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        knoepfe = QDialogButtonBox()
        knoepfe.addButton("Übernehmen", QDialogButtonBox.AcceptRole)
        knoepfe.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.datei_waehlen(0)

    def _modus(self, datei):
        return "satz" if self.saetze.get(datei) else "einzeln"

    @property
    def datei(self):
        return self.dateien[self.datei_nr] if self.dateien else None

    def datei_waehlen(self, nr):
        """Datei Nr. nr (ab 0) zeigen: nur ihre Teile, Feld Sätze, 3D des ersten Teils."""
        if not self.dateien:
            return
        self.datei_nr = max(0, min(nr, len(self.dateien) - 1))
        d = self.datei
        n = len(self.dateien)
        self.datei_text.setText(f"Datei {self.datei_nr + 1} von {n}: {Path(str(d)).name}")
        self.zurueck.setEnabled(self.datei_nr > 0)
        self.vor.setEnabled(self.datei_nr < n - 1)
        self.zurueck.setVisible(n > 1)
        self.vor.setVisible(n > 1)
        for (datei, vorschlag), g in self.gruppen.items():
            g.setHidden(datei != d)
            if datei == d:
                anz = g.childCount()
                g.setText(0, f"{vorschlag or 'ohne Profil'} – {anz} Teil{'e' if anz != 1 else ''}"
                          + ("  (Profil fehlt in den Stammdaten)" if vorschlag not in self.k.profile else ""))
        for datei, g in self.fehler_gruppen.items():
            g.setHidden(datei != d)
        self.satz_feld.setVisible(d in self.mehrteilig)
        self.satz_info.setVisible(d in self.mehrteilig)
        self.satz_spin.blockSignals(True)
        self.satz_spin.setValue(self.saetze.get(d, 0))
        self.satz_spin.blockSignals(False)
        self._satz_anzeigen()
        self.baum.clearSelection()
        erste = [z for z in self.zeilen if z.datei == d]
        if erste:
            self._zeigen(erste[0].it)      # 3D des ersten Teils, ohne es zu markieren
        else:
            fg = self.fehler_gruppen.get(d)
            if fg and fg.childCount():
                self._zeigen(fg.child(0))

    def _satz_anzeigen(self):
        d = self.datei
        satz = bool(self.saetze.get(d))
        self.baum.headerItem().setText(4, "Stück je Satz" if satz else "Stückzahl")
        if d in self.mehrteilig:
            koerper = self.mehrteilig[d][0]
            from .step import satzname
            self.satz_info.setText(f"Satz „{satzname(d)}“" if satz else f"leer = {koerper} Einzelteile")

    def saetze_setzen(self, n, datei=None):
        """Anzahl Sätze einer Datei (Vorgabe: die gezeigte); 0 = Einzelpositionen. Wechselt die Spalte Stückzahl
        zwischen Stückzahl und Stück je Satz."""
        datei = self.datei if datei is None else datei
        if datei not in self.mehrteilig:
            raise KeyError(datei)
        self.saetze[datei] = int(n or 0)
        for z in self.zeilen:
            if z.datei == datei:
                z.sp.blockSignals(True)
                z.sp.setValue(z.werte[self._modus(datei)])
                z.sp.blockSignals(False)
        if datei == self.datei:
            if self.satz_spin.value() != self.saetze[datei]:
                self.satz_spin.blockSignals(True)
                self.satz_spin.setValue(self.saetze[datei])
                self.satz_spin.blockSignals(False)
            self._satz_anzeigen()

    def _zeile(self, it):
        if it is None or it.parent() is None:
            return None
        n = it.data(0, Qt.UserRole)
        return self.zeilen[n] if isinstance(n, int) and 0 <= n < len(self.zeilen) and self.zeilen[n].it is it else None

    def _zeigen(self, it):
        z = self._zeile(it)
        if z:
            m = self.messwerte[z.liste[0]]
            self.ansicht.setzen(m.get("_netz"), m.get("artikel") or "", _messinfo(m))
        elif it is not None and it.data(1, Qt.UserRole) is not None:
            m = self.messwerte[it.data(1, Qt.UserRole)]
            self.ansicht.setzen(None, m.get("datei") or "", _messinfo(m))

    def _markiert(self):
        z = [self._zeile(it) for it in self.baum.selectedItems() if not it.isHidden() and not it.parent().isHidden()]
        return [x for x in z if x]

    def alle_setzen(self, werkstoff=None, stueck=None, nur_markierte=False):
        """Werkstoff und/oder Stückzahl (None = Auswahl unten) in alle Teile aller Dateien bzw. die markierten
        Zeilen schreiben. Die Stückzahl gilt nur für Teile ohne Satz (bei einem Satz zählt das Feld Sätze)."""
        werkstoff = werkstoff if werkstoff is not None else (
            self.alle_ws.currentText() if self.alle_ws.currentIndex() > 0 else None)
        stueck = stueck if stueck is not None else (self.alle_stk.value() or None)
        for z in (self._markiert() if nur_markierte else self.zeilen):
            if werkstoff is not None:
                z.ws.setCurrentText(werkstoff)
            if stueck is not None:
                z.werte["einzeln"] = stueck
                if not self.saetze.get(z.datei):
                    z.sp.setValue(stueck)

    def alle_waehlen(self, an):
        for z in self.zeilen:
            z.it.setCheckState(0, Qt.Checked if an else Qt.Unchecked)

    def zeile_setzen(self, artikel, uebernehmen=None, profil=None, werkstoff=None, stueck=None):
        """Werte einer Zeile ohne Maus setzen (Tests, Bildschirmfotos). stueck = Wert der Spalte (bei einem Satz
        Stück je Satz)."""
        for z in self.zeilen:
            if z.it.text(0) == artikel:
                if uebernehmen is not None:
                    z.it.setCheckState(0, Qt.Checked if uebernehmen else Qt.Unchecked)
                if profil is not None:
                    z.pr.setCurrentText(profil)
                if werkstoff is not None:
                    z.ws.setCurrentText(werkstoff)
                if stueck is not None:
                    z.sp.setValue(stueck)
                return z
        raise KeyError(artikel)

    def werte_schreiben(self):
        """Gewählte Werte in die Messwerte schreiben (_uebernehmen, _profil, _werkstoff, _stueck; bei einem Satz
        _saetze = Sätze, _stueck = Sätze, _je_satz = Stück je Satz)."""
        for z in self.zeilen:
            profil = z.pr.currentText().strip()
            saetze = self.saetze.get(z.datei) if z.datei in self.mehrteilig else 0
            for i in z.liste:
                m = self.messwerte[i]
                m["_uebernehmen"] = z.it.checkState(0) == Qt.Checked
                m["_werkstoff"] = z.ws.currentText() or None
                if saetze:
                    m["_saetze"], m["_stueck"] = saetze, saetze
                    m["_je_satz"] = z.werte["satz"] or len(z.liste)
                else:
                    m["_saetze"] = 0           # leer = Einzelpositionen (auch ohne Rückfrage)
                    m.pop("_je_satz", None)
                    m["_stueck"] = z.werte["einzeln"] or None
                if profil and profil != z.vorschlag:
                    m["_profil"] = profil
                else:
                    m.pop("_profil", None)
        return self.messwerte

    def accept(self):
        self.werte_schreiben()
        super().accept()


class Positionen3DDialog(_Mit3D):
    """3D-Ansicht der Positionen eines Angebots (Teile aus dem STEP-Import)."""

    def __init__(self, parent, positionen, netze, gewaehlt=0):
        super().__init__(parent, "3D-Ansicht der Positionen", ("Pos.", "Artikelnummer", "Bezeichnung", "Profil-ID",
                                                              "Teilelänge [mm]", "3D"))
        self.positionen, self.netze = positionen, netze
        self._fuellen([(p.get("pos"), p.get("artikel"), p.get("bezeichnung"), p.get("profil_id"), p.get("laenge"),
                        "ja" if p["id"] in netze else "–") for p in positionen])
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        self.lay.addWidget(knoepfe)
        if positionen:
            self.liste.selectRow(gewaehlt)
            self._zeigen(gewaehlt)

    def _zeigen(self, r):
        if 0 <= r < len(self.positionen):
            p = self.positionen[r]
            titel = f"Pos. {p.get('pos') or ''} {p.get('artikel') or ''}"
            info = "" if p["id"] in self.netze else "Für diese Position gibt es keine 3D-Daten (nicht per STEP-Import)."
            self.ansicht.setzen(self.netze.get(p["id"]), titel, info)
