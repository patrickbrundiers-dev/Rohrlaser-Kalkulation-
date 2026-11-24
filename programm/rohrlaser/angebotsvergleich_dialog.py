"""Datei → „Angebote vergleichen …“ und „Vergleichen …“ in der Angebotsliste (angebotsvergleich.py, Plan
CSV-Angebotsvergleich 30.10.2026).

Oben je Seite (A und B) die Quelle: CSV/ZIP-Datei oder ein Angebot aus der Liste; fremde CSVs bekommen die
Spaltenzuordnung (SpaltenDialog, Vorlage je Quelle). Darunter das Ergebnis in einem Satz, die Tabelle je Position
(Differenz B − A, markierte Positionen hinterlegt) und die Knöpfe zum Zuordnen von Hand, PDF und CSV. Es wird nichts
in den Angeboten gespeichert, nur die Vorlagen der Spaltenzuordnung."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import angebotsvergleich as av
from . import stil

SPALTEN = ("Pos. A", "Pos. B", "Artikel / Bezeichnung", "Zuordnung", "Menge A", "Menge B", "Stückpreis\nA [€]",
           "Stückpreis\nB [€]", "Differenz\nStück [€]", "Differenz\n[%]", "Gesamt A\n[€]", "Gesamt B auf\nMenge A [€]",
           "Differenz\nGesamt [€]", "Hinweise")
RECHTS = range(4, 13)
MARKIERT, NUR_EINE = "#FFF2CC", "#EDEDED"
TEURER, GUENSTIGER = "#B42318", "#1E7B34"
DATEIFILTER = "Angebote (*.csv *.zip *.txt);;Alle Dateien (*)"


class SpaltenDialog(QDialog):
    """Spaltenzuordnung einer fremden CSV: je Feld eine Spalte der Datei, Vorschau der ersten Zeilen, Vorlage."""

    def __init__(self, parent, quelle, zuordnung, vorlage=""):
        super().__init__(parent)
        self.quelle = quelle
        self.setWindowTitle(f"Spalten zuordnen – {quelle['name']}")
        self.resize(820, 560)
        hinweis = QLabel("Welche Spalte der Datei enthält was? Der Vorschlag kommt aus den Spaltentiteln. Nötig sind "
                         "der Stückpreis oder der Gesamtpreis und eine Kennung (Artikelnummer, Bezeichnung oder "
                         "Position); alles andere ist freiwillig. Zahlen dürfen mit Komma oder Punkt, mit € oder % "
                         "stehen.")
        hinweis.setWordWrap(True)
        form = QFormLayout()
        self.felder = {}
        for feld, titel, _ in av.FELDER:
            cb = QComboBox()
            cb.addItem("–", "")
            for s in quelle["spalten"]:
                if s.strip():
                    cb.addItem(s, s)
            i = cb.findData(zuordnung.get(feld, ""))
            cb.setCurrentIndex(max(i, 0))
            self.felder[feld] = cb
            form.addRow(titel, cb)
        vorschau = QTableWidget(min(5, len(quelle["zeilen"])), len(quelle["spalten"]))
        vorschau.setHorizontalHeaderLabels(quelle["spalten"])
        vorschau.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, z in enumerate(quelle["zeilen"][:5]):
            for c, w in enumerate(z[:len(quelle["spalten"])]):
                vorschau.setItem(r, c, QTableWidgetItem(w))
        vorschau.resizeColumnsToContents()
        self.vorlage = QLineEdit(vorlage or Path(quelle["name"]).stem)
        self.speichern = QCheckBox("als Vorlage speichern")
        self.speichern.setChecked(True)
        self.speichern.setToolTip("Dateien mit denselben Spaltentiteln bekommen diese Zuordnung beim nächsten Mal "
                                  "gleich vorgeschlagen (z. B. je Wettbewerber oder Lieferant).")
        unten = QHBoxLayout()
        unten.addWidget(QLabel("Vorlage"))
        unten.addWidget(self.vorlage, 1)
        unten.addWidget(self.speichern)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(hinweis)
        lay.addLayout(form)
        lay.addWidget(QLabel("Erste Zeilen der Datei:"))
        lay.addWidget(vorschau, 1)
        lay.addLayout(unten)
        lay.addWidget(knoepfe)

    def zuordnung(self):
        return {f: cb.currentData() for f, cb in self.felder.items() if cb.currentData()}

    def _ok(self):
        fehler = av.zuordnung_pruefen(self.zuordnung())
        if fehler:
            QMessageBox.warning(self, "Spalten zuordnen", fehler)
            return
        self.accept()


class AngebotsvergleichDialog(QDialog):
    """Zwei Angebote Position für Position vergleichen."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.quellen = {"A": None, "B": None}
        self.zuordnungen = {"A": None, "B": None}
        self.pos = {"A": [], "B": []}
        self.hinweise = {"A": [], "B": []}
        self.paare, self.zeilen, self.summen = [], [], {}
        self.setWindowTitle("Angebote vergleichen")
        self.resize(1250, 700)
        oben = QHBoxLayout()
        self.titel, self.spalten_knopf = {}, {}
        for seite in ("A", "B"):
            box = QGroupBox(f"Angebot {seite}")
            lay = QVBoxLayout(box)
            self.titel[seite] = QLabel("– noch nichts gewählt –")
            self.titel[seite].setWordWrap(True)
            knoepfe = QHBoxLayout()
            datei = QPushButton("CSV/ZIP-Datei …")
            datei.setToolTip("Eigener CSV-Export (Angebotspositionen.csv oder das ZIP) oder eine fremde CSV, z. B. "
                             "ein Konkurrenz- oder Lieferantenangebot")
            datei.clicked.connect(lambda _=False, s=seite: self.datei_waehlen(s))
            liste = QPushButton("Aus Angebotsliste …")
            liste.clicked.connect(lambda _=False, s=seite: self.angebot_waehlen(s))
            spalten = QPushButton("Spalten …")
            spalten.setToolTip("Spaltenzuordnung der fremden CSV ändern")
            spalten.clicked.connect(lambda _=False, s=seite: self.spalten_zuordnen(s, dialog=True))
            spalten.setEnabled(False)
            self.spalten_knopf[seite] = spalten
            for k in (datei, liste, spalten):
                knoepfe.addWidget(k)
            knoepfe.addStretch(1)
            lay.addWidget(self.titel[seite])
            lay.addLayout(knoepfe)
            oben.addWidget(box, 1)
        self.schwelle_text = QLabel()
        self.schwelle_text.setObjectName("kennzahltitel")
        self.schwelle_text.setWordWrap(True)
        self.ergebnis_text = QLabel("Zwei Angebote wählen.")
        self.ergebnis_text.setWordWrap(True)
        self.ergebnis_text.setTextFormat(Qt.RichText)
        self.nur_abw = QCheckBox("nur Abweichungen")
        self.nur_abw.setToolTip("Nur markierte Positionen und Positionen, die nur in einem Angebot stehen")
        self.nur_abw.toggled.connect(self._zeigen)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.verticalHeader().hide()
        self.tabelle.itemSelectionChanged.connect(self._knoepfe_setzen)
        self.zuordnen_knopf = QPushButton("Zuordnen")
        self.zuordnen_knopf.setToolTip("Eine Zeile „nur in A“ und eine Zeile „nur in B“ markieren (Strg+Klick) und "
                                       "einander zuordnen")
        self.zuordnen_knopf.clicked.connect(lambda: self.zuordnen())
        self.trennen_knopf = QPushButton("Zuordnung lösen")
        self.trennen_knopf.clicked.connect(lambda: self.trennen())
        self.pdf_knopf = QPushButton("PDF …")
        self.pdf_knopf.clicked.connect(lambda: self.pdf())
        self.csv_knopf = QPushButton("CSV …")
        self.csv_knopf.setToolTip("Vergleich als CSV für Excel speichern")
        self.csv_knopf.clicked.connect(lambda: self.csv())
        leiste = QHBoxLayout()
        for w in (self.nur_abw, self.zuordnen_knopf, self.trennen_knopf):
            leiste.addWidget(w)
        leiste.addStretch(1)
        leiste.addWidget(self.pdf_knopf)
        leiste.addWidget(self.csv_knopf)
        unten = QDialogButtonBox()
        unten.addButton("Schließen", QDialogButtonBox.RejectRole)
        unten.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.schwelle_text)
        lay.addWidget(self.ergebnis_text)
        lay.addLayout(leiste)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(unten)
        self._knoepfe_setzen()

    # -------------------------------------------------------------- Quellen
    def schwellen(self):
        return (float(self.db.einstellung("vergleich_schwelle_anteil") or 0),
                float(self.db.einstellung("vergleich_schwelle_eur") or 0))

    def _fehler(self, text):
        if self.f.stumm:
            self.f.meldung("Angebotsvergleich: " + text.replace("\n", " "), fehler=True)
        else:
            QMessageBox.warning(self, "Angebote vergleichen", text)

    def datei_waehlen(self, seite, pfad=None, zuordnung=None):
        """CSV/ZIP für Seite A oder B lesen; fremde CSV: Spaltenzuordnung (zuordnung: ohne Dialog). Ergebnis: True
        bei Erfolg."""
        if pfad is None:
            start = self.db.einstellung("csv_ordner") or ""
            pfad, _ = QFileDialog.getOpenFileName(self, f"Angebot {seite}: Datei wählen", start, DATEIFILTER)
            if not pfad:
                return False
        try:
            quelle = av.datei_lesen(pfad)
        except av.VergleichFehler as e:
            self._fehler(str(e))
            return False
        return self.quelle_setzen(seite, quelle, zuordnung)

    def angebot_waehlen(self, seite, angebot_id=None):
        """Angebot aus der Liste (Auswahl nach Nummer und Kunde) für Seite A oder B."""
        if angebot_id is None:
            alle = self.db.angebote("")
            if not alle:
                self._fehler("Es gibt noch keine Angebote.")
                return False
            texte = [f"{z.get('nummer') or ''} – {z.get('kunde') or ''}" for z in alle]
            text, ok = QInputDialog.getItem(self, f"Angebot {seite}", "Angebot (Nummer – Kunde):", texte, 0, False)
            if not ok:
                return False
            angebot_id = alle[texte.index(text)]["id"]
        try:
            quelle = av.aus_angebot(self.db, angebot_id)
        except av.VergleichFehler as e:
            self._fehler(str(e))
            return False
        return self.quelle_setzen(seite, quelle)

    def quelle_setzen(self, seite, quelle, zuordnung=None):
        self.quellen[seite] = quelle
        self.zuordnungen[seite] = None
        if not quelle["eigen"] and not self.spalten_zuordnen(seite, zuordnung):
            self.quellen[seite] = None
            self._titel_setzen()
            return False
        self._lesen(seite)
        return True

    def spalten_zuordnen(self, seite, zuordnung=None, dialog=False):
        """Spaltenzuordnung der fremden CSV: gespeicherte Vorlage mit gleichen Spaltentiteln, sonst Vorschlag; der
        Dialog zeigt sie zum Prüfen (stumm/zuordnung gegeben: ohne Dialog)."""
        quelle = self.quellen[seite]
        if quelle is None or quelle["eigen"]:
            return True
        vorlagen = self.db.einstellung(av.VORLAGEN) or {}
        name = av.vorlage_finden(vorlagen, quelle["spalten"])
        if zuordnung is None:
            zuordnung = self.zuordnungen[seite] or (vorlagen[name]["zuordnung"] if name else
                                                    av.vorschlag(quelle["spalten"]))
            if not self.f.stumm:
                d = SpaltenDialog(self, quelle, zuordnung, name or "")
                if d.exec() != QDialog.Accepted:
                    return False
                zuordnung = d.zuordnung()
                if d.speichern.isChecked() and d.vorlage.text().strip():
                    vorlagen = dict(vorlagen)
                    vorlagen[d.vorlage.text().strip()] = dict(spalten=list(quelle["spalten"]), zuordnung=zuordnung)
                    self.db.einstellung_setzen(av.VORLAGEN, vorlagen)
        fehler = av.zuordnung_pruefen(zuordnung)
        if fehler:
            self._fehler(fehler)
            return False
        self.zuordnungen[seite] = zuordnung
        if dialog:
            self._lesen(seite)
        return True

    def _lesen(self, seite):
        self.pos[seite], self.hinweise[seite] = av.positionen(self.quellen[seite], self.zuordnungen[seite])
        if self.quellen["A"] and self.quellen["B"]:
            self.paare = av.zuordnen(self.pos["A"], self.pos["B"])
        self.rechnen()

    def _titel_setzen(self):
        for seite, q in self.quellen.items():
            if q is None:
                self.titel[seite].setText("– noch nichts gewählt –")
                self.spalten_knopf[seite].setEnabled(False)
                continue
            art = "eigener CSV-Export" if q["eigen"] and "angebot_id" not in q else (
                "aus der Angebotsliste" if q["eigen"] else "fremde CSV")
            text = f"<b>{q['titel']}</b> ({art}, {len(self.pos[seite])} Positionen)"
            if self.hinweise[seite]:
                text += "<br><span style='color:#8a6d00'>" + "<br>".join(self.hinweise[seite][:4]) + (
                    f"<br>… und {len(self.hinweise[seite]) - 4} weitere" if len(self.hinweise[seite]) > 4 else "") \
                    + "</span>"
            self.titel[seite].setText(text)
            self.spalten_knopf[seite].setEnabled(not q["eigen"])

    # -------------------------------------------------------------- Rechnen und Zeigen
    def rechnen(self):
        self._titel_setzen()
        anteil, eur = self.schwellen()
        teile = [f"ab {av.prozent(anteil, False)} Abweichung im Stückpreis" if anteil else "",
                 f"ab {av.euro(eur)} € je Position" if eur else ""]
        self.schwelle_text.setText("Differenz = B − A (rot = B teurer, grün = B günstiger). Gelb markiert: "
                                   + (" oder ".join(t for t in teile if t) or "nichts (Schwellen aus)")
                                   + " (Einstellungen → Automatik und Prüfung). Grau: nur in einem Angebot.")
        if not (self.quellen["A"] and self.quellen["B"]):
            self.zeilen, self.summen = [], {}
            self.ergebnis_text.setText("Zwei Angebote wählen.")
            self._zeigen()
            return
        self.zeilen, self.summen = av.vergleichen(self.pos["A"], self.pos["B"], self.paare, anteil, eur)
        s = self.summen
        text = (f"<b>{av.ergebnis_text(s)}</b><br>Zugeordnet {s['paare']} Positionen: A "
                f"{av.euro(s['paar_a'])} €, B auf Mengen von A {av.euro(s['paar_b'])} €, Differenz "
                f"{av.euro(s['diff'], True)} € ({av.prozent(s['anteil'])}); {s['markiert']} markiert.")
        if s["nur_a"] or s["nur_b"]:
            text += (f" Nur in A: {s['nur_a']} ({av.euro(s['nur_a_eur'])} €), nur in B: {s['nur_b']} "
                     f"({av.euro(s['nur_b_eur'])} €).")
        text += f" Summe laut Datei: A {av.euro(s['summe_a'])} €, B {av.euro(s['summe_b_datei'])} €."
        self.ergebnis_text.setText(text)
        self._zeigen()

    def _zeigen(self, *_):
        self.tabelle.setRowCount(0)
        nur = self.nur_abw.isChecked()
        for i, z in enumerate(self.zeilen):
            if nur and not z["markiert"]:
                continue
            a, b = z["a"] or {}, z["b"] or {}
            werte = [a.get("pos", ""), b.get("pos", ""), av.kennung(z), z["zuordnung"], av._t(z.get("menge_a")),
                     av._t(z.get("menge_b")), av.euro(z.get("stk_a")), av.euro(z.get("stk_b")),
                     av.euro(z.get("diff_stk"), True), av.prozent(z.get("anteil")), av.euro(z.get("ges_a")),
                     av.euro(z.get("ges_b")), av.euro(z.get("diff_ges"), True), "; ".join(z["hinweise"])]
            r = self.tabelle.rowCount()
            self.tabelle.insertRow(r)
            hinter = (NUR_EINE if z["art"] != "paar" else MARKIERT) if z["markiert"] else None
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                it.setData(Qt.UserRole, i)
                if c in RECHTS:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if hinter:
                    it.setBackground(QBrush(stil.farbe(hinter)))
                if c in (8, 9, 12) and z.get("diff_stk"):
                    it.setForeground(QBrush(stil.farbe(TEURER if z["diff_stk"] > 0 else GUENSTIGER)))
                if c == 3 and z["art"] != "paar":
                    f = QFont(it.font())
                    f.setItalic(True)
                    it.setFont(f)
                self.tabelle.setItem(r, c, it)
        self.tabelle.resizeColumnsToContents()
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(2, QHeaderView.Interactive)
        if self.tabelle.columnWidth(2) > 320:
            self.tabelle.setColumnWidth(2, 320)
        kopf.setStretchLastSection(True)
        self._knoepfe_setzen()

    def markierte(self):
        """Indizes in self.zeilen der markierten Tabellenzeilen."""
        rows = sorted({i.row() for i in self.tabelle.selectedIndexes()})
        return [self.tabelle.item(r, 0).data(Qt.UserRole) for r in rows if self.tabelle.item(r, 0)]

    def _knoepfe_setzen(self):
        gew = [self.zeilen[i] for i in self.markierte()] if self.zeilen else []
        arten = sorted(z["art"] for z in gew)
        self.zuordnen_knopf.setEnabled(arten == ["nur_a", "nur_b"])
        self.trennen_knopf.setEnabled(len(gew) == 1 and gew[0]["art"] == "paar")
        for k in (self.pdf_knopf, self.csv_knopf):
            k.setEnabled(bool(self.zeilen))

    def zuordnen(self, i_a=None, i_b=None):
        """Position i_a (A) mit i_b (B) von Hand zuordnen; ohne Angabe die zwei markierten Zeilen."""
        if i_a is None:
            gew = [self.zeilen[i] for i in self.markierte()]
            i_a = next((z["i_a"] for z in gew if z["art"] == "nur_a"), None)
            i_b = next((z["i_b"] for z in gew if z["art"] == "nur_b"), None)
        if i_a is None or i_b is None:
            return
        self.paare = av.von_hand(self.paare, i_a, i_b)
        self.rechnen()

    def trennen(self, i_a=None):
        if i_a is None:
            gew = [self.zeilen[i] for i in self.markierte()]
            i_a = gew[0]["i_a"] if len(gew) == 1 and gew[0]["art"] == "paar" else None
        if i_a is None:
            return
        self.paare = av.trennen(self.paare, i_a)
        self.rechnen()

    # -------------------------------------------------------------- Ausgabe
    def _dateiname(self, endung):
        def kurz(q):
            return "".join(c if c.isalnum() or c in "-_" else "_" for c in q["titel"])[:40].strip("_")
        return f"Vergleich {kurz(self.quellen['A'])} gegen {kurz(self.quellen['B'])}{endung}"

    def _ziel(self, endung, filter_text, pfad):
        if pfad is not None:
            return Path(pfad)
        try:
            start = Path(self.f.ablage()) / self._dateiname(endung)
        except OSError:
            start = Path(self._dateiname(endung))
        if self.f.stumm:
            return start
        pfad, _ = QFileDialog.getSaveFileName(self, "Vergleich speichern", str(start), filter_text)
        return Path(pfad) if pfad else None

    def pdf(self, pfad=None):
        """Vergleich als PDF (A4 quer). Ergebnis: Pfad oder None."""
        if not self.zeilen:
            return None
        ziel = self._ziel(".pdf", "PDF (*.pdf)", pfad)
        if ziel is None:
            return None
        from . import pdf
        try:
            pdf.angebotsvergleich_pdf(ziel, self.quellen["A"]["titel"], self.quellen["B"]["titel"], self.zeilen,
                                      self.summen, self.db.einstellungen(), self.schwellen())
        except PermissionError:
            self._fehler(f"Die Datei konnte nicht gespeichert werden:\n{ziel}\n\nIst sie noch geöffnet?")
            return None
        except OSError as e:
            self._fehler(f"Die PDF ließ sich nicht speichern:\n{ziel}\n\n{e}")
            return None
        if not self.f.stumm:
            self.f.datei_oeffnen(ziel)
        self.f.meldung(f"Angebotsvergleich gespeichert: {ziel}")
        return ziel

    def csv(self, pfad=None):
        """Vergleich als CSV für Excel. Ergebnis: Pfad oder None."""
        if not self.zeilen:
            return None
        ziel = self._ziel(".csv", "CSV (*.csv)", pfad)
        if ziel is None:
            return None
        try:
            ziel.write_bytes(av.csv_text(self.zeilen, self.summen, self.quellen["A"]["titel"],
                                         self.quellen["B"]["titel"]).encode("utf-8"))
        except OSError as e:
            self._fehler(f"Die CSV ließ sich nicht speichern:\n{ziel}\n\n{e}")
            return None
        self.f.meldung(f"Angebotsvergleich gespeichert: {ziel}")
        return ziel
