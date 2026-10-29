"""Dialog 'Zukaufteile …' einer oder mehrerer Positionen: Zukaufartikel mit Menge je Teil oder je Satz und
optionalem Aufschlag der Position. 'Neuer Artikel …' legt Artikel per Schnellanlage an (zukauf_schnell).

Beim Hinzufügen wird der Preisstand des Artikels (Einkaufspreise des Lieferanten, Bezugskosten, Aufschlagsregel)
in der Position gespeichert (zukauf.stand). Spätere Änderungen am Artikel ändern das Angebot erst nach
'Aus Stammdaten aktualisieren', mit Vergleich alter und neuer Preis. Die Vorschau rechnet nur diese Position;
im Angebot werden gleiche Artikel aller Positionen zu einer Bestellung zusammengefasst."""
import copy
import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from . import zukauf
from .stammdaten import zahl_als_text, zahl_aus_text
from .zukauf_schnell import SchnellDialog

SPALTEN = ("Artikel", "Menge", "je", "Einheit", "Lieferant", "Aufschlag Pos. [%]", "Aufschlagsregel",
           "Einstand je Teil", "VK je Teil", "Preisstand")
EDIT = {1: "menge", 5: "aufschlag"}       # bearbeitbare Spalten (je: Auswahlfeld)
JE = 2


def _zahl(text, titel, leer_erlaubt=True):
    t = (text or "").strip()
    if not t:
        if leer_erlaubt:
            return None
        raise ValueError(f"{titel} fehlt.")
    try:
        return zahl_aus_text(t)
    except ValueError:
        raise ValueError(f"{titel}: '{t}' ist keine Zahl.")


def artikel_name(a):
    return " – ".join(x for x in (a.get("artikelnr"), a.get("bezeichnung")) if x)


def datum_text(iso):
    """'2026-10-20' -> '20.10.2026'"""
    t = (iso or "")[:10]
    return ".".join(reversed(t.split("-"))) if len(t) == 10 else t


def preis_text(w):
    return "" if w is None else zahl_als_text(float(w), 4 if abs(w) < 1 else 2)


class ZukaufDialog(QDialog):
    """p: erste gewählte Position (Vorgaben, Stückzahl der Vorschau), anzahl: gewählte Positionen."""

    def __init__(self, parent, db, p, anzahl=1):
        super().__init__(parent)
        self.db, self.p = db, p
        self._fuellen = False
        self.eintraege = copy.deepcopy(zukauf.eintraege(p))
        self.artikel = {a["id"]: a for a in db.zukauf_artikel_liste()}
        self.kopf = getattr(parent, "kopf", None) or {}     # Aufschlag Bleche bzw. Zukaufteile des Angebots
        self.blech_ids = {i for i, a in self.artikel.items() if a.get("artikeltyp") == zukauf.BLECH}
        self.setWindowTitle("Zukaufteile" + (f" für {anzahl} Positionen" if anzahl > 1 else
                                            f" Pos. {p.get('pos') or ''} {p.get('artikel') or ''}"))
        self.resize(1000, 420)
        lay = QVBoxLayout(self)
        neu = QHBoxLayout()
        self.auswahl = QComboBox()
        self.auswahl.setEditable(True)
        self.auswahl.setInsertPolicy(QComboBox.NoInsert)
        self.auswahl.lineEdit().setPlaceholderText("Artikelnummer oder Bezeichnung")
        for a in sorted(self.artikel.values(), key=lambda a: (a.get("kategorie") or "", artikel_name(a).lower())):
            if (a.get("status") or "aktiv") == "aktiv":
                self.auswahl.addItem(artikel_name(a), a["id"])
        self.auswahl.setCurrentIndex(-1)
        self.menge = QLineEdit("1")
        self.menge.setMaximumWidth(80)
        self.je = _je_feld(self._satz())
        dazu = QPushButton("Hinzufügen")
        dazu.clicked.connect(self._hinzufuegen_klick)
        schnell = QPushButton("Neuer Artikel …")
        schnell.setToolTip("Zukaufartikel schnell anlegen (Bezeichnung, Lieferant, EK, Aufschlag) und gleich "
                           "hinzufügen")
        schnell.clicked.connect(lambda: self.schnell())
        neu.addWidget(QLabel("Artikel"))
        neu.addWidget(self.auswahl, 1)
        neu.addWidget(QLabel("Menge"))
        neu.addWidget(self.menge)
        neu.addWidget(self.je)
        neu.addWidget(dazu)
        neu.addWidget(schnell)
        lay.addLayout(neu)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        self.tabelle.horizontalHeader().setMinimumSectionSize(50)
        for i, b in enumerate((200, 70, 80, 55, 120, 110, 170, 105, 85)):
            self.tabelle.setColumnWidth(i, b)
        self.tabelle.horizontalHeader().setSectionResizeMode(9, QHeaderView.Stretch)
        self.tabelle.itemChanged.connect(self._geaendert)
        lay.addWidget(self.tabelle, 1)
        leiste = QHBoxLayout()
        for text, ziel in (("Entfernen", lambda: self.entfernen(self._markiert())),
                           ("Duplizieren", lambda: self.duplizieren(self._markiert())),
                           ("Aus Stammdaten aktualisieren …", lambda: self.aktualisieren(self._markiert()))):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            leiste.addWidget(b)
        leiste.addStretch(1)
        lay.addLayout(leiste)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: #5F6B7A;")
        lay.addWidget(self.info)
        if anzahl > 1:
            hinweis = QLabel(f"Die Liste gilt nach OK für alle {anzahl} markierten Positionen (ersetzt deren "
                             "Zukaufteile).")
            hinweis.setStyleSheet("color: #8C1D18;")
            lay.addWidget(hinweis)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.ergebnis = None
        self._zeigen()

    # -------------------------------------------------------------- Aktionen
    def _markiert(self):
        return sorted({i.row() for i in self.tabelle.selectedIndexes()})

    def _hinzufuegen_klick(self):
        aid = self.auswahl.currentData()
        if aid is None:          # eingetippter Text: erster passender Artikel
            t = self.auswahl.currentText().strip().lower()
            aid = next((self.auswahl.itemData(i) for i in range(self.auswahl.count())
                        if t and t in self.auswahl.itemText(i).lower()), None)
        try:
            self.hinzufuegen(aid, _zahl(self.menge.text(), "Menge", False), je=self.je.currentData())
        except ValueError as e:
            self.info.setText(str(e))

    def _satz(self):
        """Position gehört zu einem Satz: neue Zukaufteile standardmäßig 'je Satz'."""
        return bool(str(self.p.get("satz") or "").strip())

    def hinzufuegen(self, artikel_id, menge=1, aufschlag=None, lieferant=None, je=None):
        """Artikel mit aktuellem Preisstand anhängen; je = zukauf.JE_SATZ: Menge je Satz."""
        if artikel_id not in self.artikel:
            raise ValueError("Bitte einen Artikel wählen.")
        if menge is None or menge <= 0:
            raise ValueError("Menge muss größer als 0 sein.")
        e = dict(artikel_id=artikel_id, menge=menge, aufschlag=aufschlag,
                 stand=self.db.zukauf_stand(artikel_id, lieferant))
        if je == zukauf.JE_SATZ:
            e["je"] = je
        self.eintraege.append(e)
        self._zeigen()

    def schnell(self, dialog=None):
        """Neue Artikel per Schnellanlage anlegen und anhängen; dialog(d) bedient den Dialog statt exec (Tests).
        Ergebnis: Anzahl angehängter Artikel."""
        d = SchnellDialog(self, self.db, self.je.currentData() == zukauf.JE_SATZ)
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
            return 0
        self.artikel = {a["id"]: a for a in self.db.zukauf_artikel_liste()}
        for x in d.ergebnis:
            a = self.artikel[x["artikel_id"]]
            self.auswahl.addItem(artikel_name(a), a["id"])
            self.hinzufuegen(x["artikel_id"], x["menge"], je=x["je"])
        return len(d.ergebnis)

    def entfernen(self, zeilen):
        for r in sorted(zeilen, reverse=True):
            del self.eintraege[r]
        self._zeigen()

    def duplizieren(self, zeilen):
        for r in zeilen:
            self.eintraege.append(copy.deepcopy(self.eintraege[r]))
        self._zeigen()

    def vergleich(self, zeilen=None):
        """[(Zeile, Artikel, VK je Teil alt, VK je Teil neu, neuer Stand)] der Zeilen mit geändertem Preisstand
        (zeilen None = alle)."""
        out = []
        for r in range(len(self.eintraege)) if zeilen is None or not zeilen else zeilen:
            e = self.eintraege[r]
            lief = ((e.get("stand") or {}).get("bezug") or {}).get("lieferant")
            neu = self.db.zukauf_stand(e.get("artikel_id"), lief)
            if neu is None or zukauf.stand_kennung(neu) == zukauf.stand_kennung(e.get("stand")):
                continue
            alt_vk = self._vorschau([e])[0]["vk"]
            neu_vk = self._vorschau([dict(e, stand=neu)])[0]["vk"]
            out.append((r, (e.get("stand") or {}).get("bezeichnung"), alt_vk, neu_vk, neu))
        return out

    def aktualisieren(self, zeilen=None, bestaetigt=None):
        """Preisstand der Zeilen (keine markiert = alle) durch den aktuellen Stand der Stammdaten ersetzen, nach
        Vergleich alt/neu. bestaetigt: True/False ohne Rückfrage (Tests). Ergebnis: Anzahl aktualisierter Zeilen."""
        liste = self.vergleich(zeilen)
        if not liste:
            self.info.setText("Alle gewählten Zukaufteile haben den aktuellen Preisstand.")
            return 0
        text = "\n".join(f"{name}: VK je Teil {preis_text(a)} € → {preis_text(n)} €" for _, name, a, n, _ in liste)
        if bestaetigt is None:
            bestaetigt = QMessageBox.question(
                self, "Preisstand aktualisieren", "Neuer Preisstand aus den Stammdaten:\n\n" + text
                + "\n\nÜbernehmen? Das Angebot rechnet danach mit den neuen Preisen.") == QMessageBox.Yes
        if not bestaetigt:
            return 0
        for r, _, _, _, neu in liste:
            self.eintraege[r]["stand"] = neu
        self._zeigen()
        return len(liste)

    def je_setzen(self, zeile, je):
        """Menge der Zeile gilt je Teil oder je Satz."""
        e = self.eintraege[zeile]
        if je == zukauf.JE_SATZ:
            e["je"] = je
        else:
            e.pop("je", None)
        QTimer.singleShot(0, self, self._zeigen)      # erst nach dem Signal des Auswahlfelds neu zeigen

    def _geaendert(self, it):
        if self._fuellen or it.column() not in EDIT:
            return
        e = self.eintraege[it.row()]
        name = EDIT[it.column()]
        try:
            w = _zahl(it.text(), SPALTEN[it.column()], name == "aufschlag")
            if name == "menge" and w <= 0:
                raise ValueError("Menge muss größer als 0 sein.")
            if name == "aufschlag" and w is not None and w < 0:
                raise ValueError("Aufschlag darf nicht negativ sein.")
            e[name] = w
        except ValueError as ex:
            self.info.setText(str(ex))
        self._zeigen()

    # -------------------------------------------------------------- Anzeige
    def _stueck(self):
        s = self.p.get("stueck")
        return s if isinstance(s, (int, float)) and s > 0 else 1

    def _vorschau(self, eintraege):
        """Beträge je Teil für die Stückzahl der Position."""
        c = self._stueck()
        _, je = zukauf.rechnen([(n, zukauf.mit_angebotsaufschlag(e, self.kopf, self.blech_ids),
                                 zukauf.bezugsmenge(e, self.p, c)) for n, e in enumerate(eintraege)])
        return [dict(je[n], einstand=je[n]["einstand"] / zukauf.dez(c), vk=je[n]["vk"] / zukauf.dez(c))
                for n in range(len(eintraege))]

    def _zeigen(self):
        self._fuellen = True
        try:
            werte = self._vorschau(self.eintraege)
            self.tabelle.setRowCount(len(self.eintraege))
            veraltet = {r for r, *_ in self.vergleich()}
            for r, (e, w) in enumerate(zip(self.eintraege, werte)):
                st = e.get("stand") or {}
                a = self.artikel.get(e.get("artikel_id"))
                zellen = (artikel_name(st) or artikel_name(a or {}) or "?",
                          zahl_als_text(e.get("menge"), 3) if e.get("menge") is not None else "", "",
                          zukauf.EINHEIT_KURZ.get(st.get("einheit"), st.get("einheit") or ""),
                          (st.get("bezug") or {}).get("lieferant") or "",
                          zahl_als_text(e["aufschlag"], 1) if e.get("aufschlag") is not None else "",
                          w["regel"], preis_text(w["einstand"]) + " €" if not w["fehler"] else "",
                          preis_text(w["vk"]) + " €" if not w["fehler"] else w["fehler"],
                          (datum_text(st.get("datum")) + (" · neuer Stand in den Stammdaten" if r in veraltet else "")
                           + ("" if a else " · Artikel gelöscht")))
                for c, t in enumerate(zellen):
                    it = QTableWidgetItem(t)
                    if c not in EDIT:
                        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    if c in (1, 5, 7, 8):
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if c == 5:
                        it.setToolTip("leer = Regel des Artikels (Kategorie bzw. individuell); eine Zahl ersetzt "
                                      "sie für diese Position (% auf den Einstandspreis)")
                    self.tabelle.setItem(r, c, it)
                feld = self.tabelle.cellWidget(r, JE)
                if feld is None:      # Auswahlfeld je Zeile nur einmal anlegen: ein ersetztes Feld bliebe bis zum
                    feld = _je_feld()  # Löschen sichtbar und läge über anderen Zellen
                    feld.currentIndexChanged.connect(lambda _=0, r=r, feld=feld: self.je_setzen(r, feld.currentData()))
                    self.tabelle.setCellWidget(r, JE, feld)
                feld.blockSignals(True)
                feld.setCurrentIndex(1 if e.get("je") == zukauf.JE_SATZ else 0)
                feld.blockSignals(False)
            gesamt = sum((w["vk"] for w in werte if not w["fehler"]), zukauf.NULL)
            fehler = sum(1 for w in werte if w["fehler"])
            self.info.setText(
                f"Vorschau für {zahl_als_text(self._stueck(), 0)} Teile dieser Position: Zukaufteile "
                f"{preis_text(gesamt)} € je Teil (ohne Skonto)."
                + (f" {fehler} Artikel ohne Einkaufspreis: das Angebot zeigt dafür einen Hinweis." if fehler else "")
                + (f" {len(veraltet)} Artikel mit neuem Preisstand in den Stammdaten." if veraltet else "")
                + " Im Angebot werden gleiche Artikel aller Positionen zusammen bestellt (Staffel, Mindestmenge, "
                  "Bezugskosten einmal)." if self.eintraege else "Noch keine Zukaufteile.")
        finally:
            self._fuellen = False

    def accept(self):
        self.ergebnis = json.dumps(self.eintraege, ensure_ascii=False) if self.eintraege else None
        super().accept()


def _je_feld(satz=False):
    feld = QComboBox()
    feld.addItem("je Teil", zukauf.JE_TEIL)
    feld.addItem("je Satz", zukauf.JE_SATZ)
    feld.setCurrentIndex(1 if satz else 0)
    feld.setToolTip("je Satz: Menge gilt je Satz (z. B. 20 Bleche je Rahmen); Sätze = Stückzahl / Stück je Satz "
                    "der Position, ohne Satzangabe zählt jedes Teil als ein Satz")
    return feld
