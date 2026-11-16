"""Fenster „Teilefamilie“ (CAD-010, teilefamilie.py): Variablen wählen, Wertetabelle füllen (auch aus Excel einfügen),
Prüfung je Zeile; OK liefert variablen() und zeilen()."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import teilefamilie as tf

PRUEFUNG = "_pruefung"


class TeilefamilieDialog(QDialog):
    """b: teilefamilie.basis(); profile, werkstoffe: gültige IDs (Prüfung); speichern(variablen, zeilen, name):
    als Vorlage speichern (None = ohne Knopf)."""

    def __init__(self, parent, b, profile=(), werkstoffe=(), speichern=None):
        super().__init__(parent)
        self.b, self.profile, self.werkstoffe, self._speichern = b, set(profile), set(werkstoffe), speichern
        self.setWindowTitle("Teilefamilie – mehrere Teile aus einer Wertetabelle")
        self.resize(980, 560)
        lay = QVBoxLayout(self)
        name = b["werte"].get(tf.BEZEICHNUNG) or b["werte"].get(tf.ARTIKEL) or "Teil"
        kopf = QLabel(f"<b>{name}</b> ({b['art']}): jede Zeile wird eine neue Position, gerechnet wie aus dem "
                      "Editor. Das Teil selbst bleibt, wie es ist. Konturen in der hinteren Hälfte wandern mit Ende B, "
                      "eine Lochreihe mit eigener Anzahl wird gleichmäßig neu verteilt.")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        for h in b.get("hinweise") or ():
            x = QLabel("Hinweis: " + h)
            x.setWordWrap(True)
            lay.addWidget(x)
        lay.addWidget(QLabel("Werte, die sich ändern:"))
        haken = QHBoxLayout()
        self.haken = {}
        start = b.get("start") or (None, None)
        gewaehlt = set(start[0] or ([tf.LAENGE] if any(v == tf.LAENGE for v, _ in b["variablen"]) else []))
        for v, titel in b["variablen"]:
            c = QCheckBox(titel)
            c.setChecked(v in gewaehlt)
            c.toggled.connect(lambda _=False: self._spalten())
            haken.addWidget(c)
            self.haken[v] = c
        haken.addStretch(1)
        lay.addLayout(haken)
        self.tabelle = QTableWidget()
        self.tabelle.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabelle.itemChanged.connect(lambda _: self._pruefen())
        lay.addWidget(self.tabelle, 1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        leiste = QHBoxLayout()
        for text, fn, tipp in (
                ("Zeile hinzufügen", lambda: self.zeile_neu(), "Neue Zeile mit den Werten der letzten Zeile"),
                ("Markierte entfernen", lambda: self.markierte_entfernen(), ""),
                ("Aus Zwischenablage einfügen", lambda: self.einfuegen(),
                 "Zeilen aus Excel einfügen: Spalten in der Reihenfolge der Tabelle (Kopfzeile wird erkannt)"),
                ("Bezeichnung mit Maß", lambda: self.bezeichnungen_setzen(),
                 "Bezeichnung jeder Zeile mit ihrer Länge, z. B. „Sprosse L=850“")):
            k = QPushButton(text)
            k.setToolTip(tipp)
            k.clicked.connect(fn)
            leiste.addWidget(k)
        if speichern is not None:
            k = QPushButton("Als Vorlage speichern …")
            k.setToolTip("Teil, Variablen und Zeilen als Positionsvorlage („Neue Position aus Vorlage“ legt die ganze "
                         "Familie an)")
            k.clicked.connect(lambda: self.als_vorlage())
            leiste.addWidget(k)
        leiste.addStretch(1)
        lay.addLayout(leiste)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Positionen anlegen")
        self.knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        self.knoepfe.accepted.connect(self._ok)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        self._spalten_liste = []
        self._spalten(start[1] or tf.standard_zeilen(b))

    # -------------------------------------------------------------- Spalten und Zeilen
    def variablen(self):
        return [v for v, c in self.haken.items() if c.isChecked()]

    def spalten(self):
        return self.variablen() + list(tf.IMMER)

    def _titel(self, s):
        return tf.TITEL.get(s) or next((t for v, t in self.b["variablen"] if v == s), s)

    def _spalten(self, zeilen=None):
        zeilen = self.zeilen() if zeilen is None else zeilen
        self._spalten_liste = self.spalten()
        self.tabelle.blockSignals(True)
        self.tabelle.clear()
        self.tabelle.setColumnCount(len(self._spalten_liste) + 1)
        self.tabelle.setHorizontalHeaderLabels([self._titel(s) for s in self._spalten_liste] + ["Prüfung"])
        kopf = self.tabelle.horizontalHeader()
        for i in range(len(self._spalten_liste)):
            kopf.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(len(self._spalten_liste), QHeaderView.Stretch)
        self.tabelle.setRowCount(0)
        self.tabelle.blockSignals(False)
        for z in zeilen:
            self._zeile_schreiben(z)
        self._pruefen()

    def _zeile_schreiben(self, z, zeile=None):
        self.tabelle.blockSignals(True)
        if zeile is None:
            zeile = self.tabelle.rowCount()
            self.tabelle.insertRow(zeile)
        for i, s in enumerate(self._spalten_liste):
            v = z.get(s, self.b["werte"].get(s))
            text = tf._text(v) if (s in tf.ZAHLEN or tf.reihe_index(s) is not None) else str(v or "")
            self.tabelle.setItem(zeile, i, QTableWidgetItem(text))
        it = QTableWidgetItem("")
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        self.tabelle.setItem(zeile, len(self._spalten_liste), it)
        self.tabelle.blockSignals(False)

    def zeilen(self):
        """Zeilen der Tabelle als [dict] (nur die Spalten der Tabelle; Zahlen als Zahl)."""
        out = []
        for r in range(self.tabelle.rowCount()):
            z = {}
            for i, s in enumerate(self._spalten_liste):
                it = self.tabelle.item(r, i)
                t = (it.text() if it else "").strip()
                if s in tf.ZAHLEN or tf.reihe_index(s) is not None:
                    v = tf._z(t)
                    z[s] = (int(v) if s == tf.STUECK or tf.reihe_index(s) is not None else tf._mm(v)) \
                        if v is not None else None
                else:
                    z[s] = t
            out.append(z)
        return out

    def setzen(self, zeilen):
        """Tabelle durch zeilen ersetzen (Tests, Vorlage)."""
        self._spalten(zeilen)

    def variable_setzen(self, name, an=True):
        self.haken[name].setChecked(an)

    def zeile_neu(self, werte=None):
        alt = self.zeilen()
        z = dict(alt[-1]) if alt else dict(self.b["werte"])
        art = str(self.b["werte"].get(tf.ARTIKEL) or "").strip()
        if art:
            z[tf.ARTIKEL] = f"{art}-{len(alt) + 1}"
        z.update(werte or {})
        self._zeile_schreiben(z)
        self._pruefen()

    def markierte_entfernen(self):
        for r in sorted({i.row() for i in self.tabelle.selectedIndexes()}, reverse=True):
            self.tabelle.removeRow(r)
        self._pruefen()

    def einfuegen(self, text=None):
        """Zeilen aus der Zwischenablage (oder text) anhängen; die erste, unveränderte Startzeile wird ersetzt."""
        text = QGuiApplication.clipboard().text() if text is None else text
        neu = tf.zeilen_aus_text(text, self._spalten_liste)
        if not neu:
            self.info.setText("Keine Zeilen in der Zwischenablage (Excel: Zellen markieren, kopieren).")
            return 0
        alt = self.zeilen()
        if alt == tf.standard_zeilen(self.b) or [{k: z.get(k) for k in self._spalten_liste} for z in alt] == \
                [{k: z.get(k) for k in self._spalten_liste} for z in tf.standard_zeilen(self.b)]:
            alt = []
        art = str(self.b["werte"].get(tf.ARTIKEL) or "").strip()
        for i, z in enumerate(neu):
            if not z.get(tf.ARTIKEL) and art:
                z[tf.ARTIKEL] = f"{art}-{len(alt) + i + 1}"
            if not z.get(tf.BEZEICHNUNG):
                z[tf.BEZEICHNUNG] = tf.bezeichnung_vorschlag(self.b["werte"].get(tf.BEZEICHNUNG),
                                                             dict(self.b["werte"], **z), self.b["art"])
        self._spalten(alt + neu)
        return len(neu)

    def bezeichnungen_setzen(self):
        zeilen = self.zeilen()
        for z in zeilen:
            z[tf.BEZEICHNUNG] = tf.bezeichnung_vorschlag(z.get(tf.BEZEICHNUNG) or self.b["werte"].get(tf.BEZEICHNUNG),
                                                         dict(self.b["werte"], **{k: v for k, v in z.items()
                                                                                  if v is not None}), self.b["art"])
        self._spalten(zeilen)

    # -------------------------------------------------------------- Prüfung
    def fehler(self):
        """{Zeile: [Fehler]} und allgemeine Fehler unter -1."""
        out = {}
        zeilen = self.zeilen()
        for r, z in enumerate(zeilen):
            f = tf.zeile_pruefen(self.b, {k: v for k, v in z.items() if v not in (None, "")},
                                 self.profile or None, self.werkstoffe or None)
            if f:
                out[r] = f
        doppelt = tf.doppelte_artikel(zeilen)
        if doppelt:
            out[-1] = ["Artikel mehrfach: " + ", ".join(doppelt)]
        if not zeilen:
            out[-1] = out.get(-1, []) + ["Mindestens eine Zeile eintragen"]
        return out

    def _pruefen(self):
        f = self.fehler()
        self.tabelle.blockSignals(True)
        for r in range(self.tabelle.rowCount()):
            it = self.tabelle.item(r, len(self._spalten_liste))
            if it is not None:
                it.setText("; ".join(f.get(r, [])) or "ok")
                it.setForeground(Qt.red if r in f else Qt.darkGreen)
        self.tabelle.blockSignals(False)
        n = self.tabelle.rowCount()
        fehl = len([r for r in f if r >= 0])
        self.info.setText(f"{n} Teil(e), {n - fehl} ohne Fehler." + (" " + " ".join(f[-1]) if -1 in f else ""))
        ok = self.knoepfe.button(QDialogButtonBox.Ok) if hasattr(self, "knoepfe") else None
        if ok is not None:
            ok.setEnabled(not f)
        return f

    def _ok(self):
        if not self._pruefen():
            self.accept()

    def als_vorlage(self, name=None):
        if self._speichern is None:
            return None
        if name is None:
            name, ok = QInputDialog.getText(self, "Als Vorlage speichern", "Name der Teilefamilie:",
                                            text=str(self.b["werte"].get(tf.BEZEICHNUNG) or ""))
            if not ok or not name.strip():
                return None
        return self._speichern(self.variablen(), self.zeilen(), name.strip())
