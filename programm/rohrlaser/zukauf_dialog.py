"""Dialog 'Zukaufteile …' einer oder mehrerer Positionen: Zukaufartikel direkt in der Position erfassen, bearbeiten,
duplizieren und entfernen, mit Menge je Teil oder je Satz, EK, Aufschlag und VK (Patrick 12.11.2026, Konzept
„Zukaufartikel direkt in der Position“, Freigabe alle a).

Ein Artikel muss nicht im Artikelstamm stehen: Bezeichnung in die leere Zeile unten (oder oben in das Feld Artikel)
tippen, Menge und EK eintragen, fertig. Der Artikel gehört zur Position und wird mit dem Angebot gespeichert
(zukauf.frei_eintrag). Stammartikel lassen sich weiter wählen (Suche oben); beim Hinzufügen wird ihr Preisstand in
der Position gespeichert (zukauf.stand), spätere Änderungen am Stamm ändern das Angebot erst nach 'Aus Stammdaten
aktualisieren'. Wird ein Stammartikel in der Position geändert, gilt das nur für diese Position (F4).
'Im Artikelstamm merken' legt einen freien Artikel bei Bedarf im Stamm an (optional).

Die Vorschau rechnet nur diese Position und sofort bei jeder Eingabe; im Angebot werden gleiche Artikel aller
Positionen zu einer Bestellung zusammengefasst. Ein eingetippter VK rechnet den Aufschlag % zurück (F2), damit
gibt es genau einen Aufschlag."""
import copy
import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from . import stil, zukauf
from .stammdaten import zahl_als_text, zahl_aus_text
from .zukauf_schnell import SchnellDialog

SPALTEN = ("Bezeichnung", "Menge", "je", "Einheit", "Artikelnr.", "EK [€/Einh.]", "Aufschlag [%]", "VK [€/Einh.]",
           "Gesamt je Teil", "Herkunft")
EDIT = {0: "bezeichnung", 1: "menge", 4: "artikelnr", 5: "ek", 6: "aufschlag", 7: "vk"}   # bearbeitbare Spalten
JE = 2
NEU_TEXT = "＋ Bezeichnung eintippen …"
OHNE_STAMM = "ohne Artikelstamm"
# Felder des Detailbereichs (markierte Zeile): (Name im Preisstand, Titel)
DETAILS = (("hersteller", "Hersteller"), ("lieferant", "Lieferant"), ("fracht", "Bezugskosten je Bestellung [€]"),
           ("kategorie", "Kategorie"), ("beschreibung", "Beschreibung"), ("bemerkung", "Bemerkung"))


def _zahl(text, titel, leer_erlaubt=True):
    t = (text or "").strip().replace("€", "").replace("%", "").strip().strip("()").strip()
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
        self.resize(1100, 460)
        lay = QVBoxLayout(self)
        neu = QHBoxLayout()
        self.auswahl = QComboBox()
        self.auswahl.setEditable(True)
        self.auswahl.setInsertPolicy(QComboBox.NoInsert)
        self.auswahl.lineEdit().setPlaceholderText("Bezeichnung eintippen oder Artikel aus dem Stamm wählen")
        self.auswahl.setToolTip("Neuen Artikel einfach eintippen (er gehört zur Position, kein Artikelstamm nötig) "
                                "oder einen vorhandenen Artikel aus dem Artikelstamm wählen")
        for a in sorted(self.artikel.values(), key=lambda a: (a.get("kategorie") or "", artikel_name(a).lower())):
            if (a.get("status") or "aktiv") == "aktiv":
                self.auswahl.addItem(artikel_name(a), a["id"])
        self.auswahl.setCurrentIndex(-1)
        self.menge = QLineEdit("1")
        self.menge.setMaximumWidth(70)
        self.je = _je_feld(self._satz())
        self.ek = QLineEdit()
        self.ek.setMaximumWidth(90)
        self.ek.setPlaceholderText("EK €")
        self.ek.setToolTip("Einkaufspreis je Einheit (netto) für einen neuen Artikel; leer = EK fehlt, später "
                           "nachtragen. Bei Stammartikeln gilt der Preis aus dem Stamm.")
        dazu = QPushButton("Hinzufügen")
        dazu.setObjectName("primaer")
        dazu.clicked.connect(self._hinzufuegen_klick)
        self.auswahl.lineEdit().returnPressed.connect(self._hinzufuegen_klick)
        schnell = QPushButton("Neuer Artikel …")
        schnell.setToolTip("Formular für einen neuen Zukaufartikel (auch Vollmaterial); auf Wunsch auch im "
                           "Artikelstamm speichern")
        schnell.clicked.connect(lambda: self.schnell())
        neu.addWidget(QLabel("Artikel"))
        neu.addWidget(self.auswahl, 1)
        neu.addWidget(QLabel("Menge"))
        neu.addWidget(self.menge)
        neu.addWidget(self.je)
        neu.addWidget(self.ek)
        neu.addWidget(dazu)
        neu.addWidget(schnell)
        lay.addLayout(neu)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                     | QAbstractItemView.AnyKeyPressed | QAbstractItemView.SelectedClicked)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        self.tabelle.horizontalHeader().setMinimumSectionSize(50)
        for i, b in enumerate((230, 60, 80, 55, 100, 90, 95, 90, 100)):
            self.tabelle.setColumnWidth(i, b)
        self.tabelle.horizontalHeader().setSectionResizeMode(9, QHeaderView.Stretch)
        self.tabelle.itemChanged.connect(self._geaendert)
        self.tabelle.itemSelectionChanged.connect(self._details_fuellen)
        lay.addWidget(self.tabelle, 1)
        leiste = QHBoxLayout()
        for text, ziel in (("Duplizieren", lambda: self.duplizieren(self._markiert())),
                           ("Entfernen", lambda: self.entfernen(self._markiert())),
                           ("Aus Stammdaten aktualisieren …", lambda: self.aktualisieren(self._markiert()))):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            leiste.addWidget(b)
        leiste.addStretch(1)
        self.details_knopf = QToolButton()
        self.details_knopf.setText("Details ▸")
        self.details_knopf.setCheckable(True)
        self.details_knopf.setToolTip("Hersteller, Lieferant, Bezugskosten, Kategorie, Beschreibung und Bemerkung "
                                      "der markierten Zeile")
        self.details_knopf.toggled.connect(self._details_zeigen)
        leiste.addWidget(self.details_knopf)
        lay.addLayout(leiste)
        lay.addWidget(self._details_bauen())
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
        for b in knoepfe.buttons():
            b.setAutoDefault(False)
        lay.addWidget(knoepfe)
        self.ergebnis = None
        self._details_zeigen(False)
        self._zeigen()

    # -------------------------------------------------------------- Detailbereich
    def _details_bauen(self):
        self.details = QWidget()
        g = QGridLayout(self.details)
        g.setContentsMargins(0, 0, 0, 0)
        self.detail_felder = {}
        for n, (name, titel) in enumerate(DETAILS):
            f = QLineEdit()
            f.editingFinished.connect(lambda name=name: self._detail_geaendert(name))
            g.addWidget(QLabel(titel), n // 3, (n % 3) * 2)
            g.addWidget(f, n // 3, (n % 3) * 2 + 1)
            self.detail_felder[name] = f
        self.detail_einheit = QComboBox()
        self.detail_einheit.addItems(zukauf.EINHEITEN)
        self.detail_einheit.currentTextChanged.connect(lambda t: self._detail_geaendert("einheit", t))
        self.detail_text = QCheckBox("im Angebotstext nennen")
        self.detail_text.setToolTip("Kundenangebot: „inkl. 4 St Schraube M8“ beim Artikel (nie mit Preisen)")
        self.detail_text.toggled.connect(lambda an: self._detail_geaendert("angebotstext", an))
        self.merken_knopf = QPushButton("Im Artikelstamm merken")
        self.merken_knopf.setToolTip("Optional: den Artikel auch im Artikelstamm anlegen, um ihn in anderen "
                                     "Angeboten wieder zu wählen. Für die Kalkulation nicht nötig.")
        self.merken_knopf.clicked.connect(lambda: self.merken(self._markiert()))
        z = len(DETAILS) // 3
        g.addWidget(QLabel("Einheit"), z, 0)
        g.addWidget(self.detail_einheit, z, 1)
        g.addWidget(self.detail_text, z, 2, 1, 2)
        g.addWidget(self.merken_knopf, z, 4, 1, 2)
        return self.details

    def _details_zeigen(self, an):
        self.details.setVisible(bool(an))
        self.details_knopf.setText("Details ▾" if an else "Details ▸")
        if an:
            self._details_fuellen()

    def _details_fuellen(self):
        zeilen = [r for r in self._markiert() if r < len(self.eintraege)]
        e = self.eintraege[zeilen[0]] if len(zeilen) == 1 else None
        st = (e or {}).get("stand") or {}
        b = st.get("bezug") or {}
        vorher, self._fuellen = self._fuellen, True
        try:
            for name, f in self.detail_felder.items():
                w = b.get(name) if name in ("lieferant", "fracht") else st.get(name)
                f.setText(zahl_als_text(float(w), 2) if name == "fracht" and w is not None else (w or ""))
                f.setEnabled(e is not None)
            self.detail_einheit.setCurrentText(st.get("einheit") or "Stück")
            self.detail_text.setChecked(st.get("angebotstext") == "ja")
            for w in (self.detail_einheit, self.detail_text):
                w.setEnabled(e is not None)
            self.merken_knopf.setEnabled(e is not None and zukauf.ist_frei(e))
        finally:
            self._fuellen = vorher

    def _detail_geaendert(self, name, wert=None):
        if self._fuellen:
            return
        zeilen = [r for r in self._markiert() if r < len(self.eintraege)]
        if len(zeilen) != 1:
            return
        if wert is None and name in self.detail_felder:
            wert = self.detail_felder[name].text()
            if name == "fracht":
                try:
                    wert = _zahl(wert, "Bezugskosten")
                except ValueError as ex:
                    self.info.setText(str(ex))
                    return
        self.feld_setzen(zeilen[0], name, wert)

    # -------------------------------------------------------------- Aktionen
    def _markiert(self):
        return sorted({i.row() for i in self.tabelle.selectedIndexes()})

    def _stamm_wahl(self):
        """ID des Stammartikels, wenn der Text oben genau einem Eintrag der Liste entspricht, sonst None."""
        t = self.auswahl.currentText().strip()
        if not t:
            return None
        i = self.auswahl.findText(t, Qt.MatchFixedString)
        return self.auswahl.itemData(i) if i >= 0 else None

    def _hinzufuegen_klick(self):
        try:
            menge = _zahl(self.menge.text(), "Menge", False)
            aid = self._stamm_wahl()
            if aid is not None:
                self.hinzufuegen(aid, menge, je=self.je.currentData())
            else:
                self.frei_hinzufuegen(self.auswahl.currentText(), menge, je=self.je.currentData(),
                                      ek=_zahl(self.ek.text(), "EK"))
        except ValueError as e:
            self.info.setText(str(e))
            return
        self.auswahl.setCurrentIndex(-1)
        self.auswahl.setEditText("")
        self.ek.clear()
        self.menge.setText("1")
        self.auswahl.setFocus()

    def _satz(self):
        """Position gehört zu einem Satz: neue Zukaufteile standardmäßig 'je Satz'."""
        return bool(str(self.p.get("satz") or "").strip())

    def hinzufuegen(self, artikel_id, menge=1, aufschlag=None, lieferant=None, je=None):
        """Stammartikel mit aktuellem Preisstand anhängen; je = zukauf.JE_SATZ: Menge je Satz."""
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

    def regeln(self, kategorie=None):
        """Aufschlagsregel eines freien Artikels (F3): Kategorie, sonst Standard der Einstellungen. Der Aufschlag
        Zukaufteile des Angebots ersetzt sie wie bei Stammartikeln (zukauf.mit_angebotsaufschlag)."""
        return zukauf.aufschlagsregeln(dict(kategorie=kategorie), self.db.zukauf_kategorien(),
                                       self.db.einstellung("zukauf_aufschlag"))

    def frei_hinzufuegen(self, bezeichnung, menge=1, je=None, ek=None, aufschlag=None, **werte):
        """Freien Artikel (ohne Artikelstamm) anhängen: Bezeichnung und Menge Pflicht, alles andere optional
        (artikelnr, hersteller, lieferant, fracht, beschreibung, bemerkung, einheit, kategorie, angebotstext).
        Ergebnis: Zeile."""
        e = zukauf.frei_eintrag(bezeichnung, menge, je=je, aufschlag=aufschlag, ek=ek,
                                regeln=self.regeln(werte.get("kategorie")), **werte)
        self.eintraege.append(e)
        self._zeigen()
        return len(self.eintraege) - 1

    def schnell(self, dialog=None):
        """Neue Artikel per Formular anlegen und anhängen (frei oder, mit Häkchen, auch im Stamm); dialog(d) bedient
        den Dialog statt exec (Tests). Ergebnis: Anzahl angehängter Artikel."""
        d = SchnellDialog(self, self.db, self.je.currentData() == zukauf.JE_SATZ)
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
            return 0
        self.artikel = {a["id"]: a for a in self.db.zukauf_artikel_liste()}
        for x in d.ergebnis:
            if x.get("artikel_id") is not None:
                a = self.artikel[x["artikel_id"]]
                self.auswahl.addItem(artikel_name(a), a["id"])
                self.hinzufuegen(x["artikel_id"], x["menge"], je=x["je"])
            else:
                e = dict(x["eintrag"], menge=x["menge"])
                if x["je"] == zukauf.JE_SATZ:
                    e["je"] = zukauf.JE_SATZ
                self.eintraege.append(e)
        self._zeigen()
        return len(d.ergebnis)

    def entfernen(self, zeilen):
        for r in sorted((r for r in zeilen if r < len(self.eintraege)), reverse=True):
            del self.eintraege[r]
        self._zeigen()

    def duplizieren(self, zeilen):
        for r in [r for r in zeilen if r < len(self.eintraege)]:
            self.eintraege.append(copy.deepcopy(self.eintraege[r]))
        self._zeigen()

    def feld_setzen(self, zeile, feld, wert):
        """Ein Feld einer Zeile ändern (Preisstand: zukauf.stand_setzen; menge, aufschlag, vk direkt am Eintrag).
        Ergebnis: True = geändert; Fehler stehen in der Infozeile."""
        e = self.eintraege[zeile]
        try:
            if feld == "menge":
                if wert is None or wert <= 0:
                    raise ValueError("Menge muss größer als 0 sein.")
                e["menge"] = wert
            elif feld == "aufschlag":
                if wert is not None and wert < 0:
                    raise ValueError("Aufschlag darf nicht negativ sein.")
                e["aufschlag"] = wert
            elif feld == "vk":
                w = self._vorschau([e])[0]
                e["aufschlag"] = zukauf.aufschlag_aus_vk(w["einstand_einheit"], wert) if wert is not None else None
            elif not zukauf.stand_setzen(e, feld, wert):
                return False
        except ValueError as ex:
            self._zeigen()
            self.info.setText(str(ex))
            return False
        self._zeigen()
        return True

    def merken(self, zeilen):
        """Freie Artikel der Zeilen auch im Artikelstamm anlegen (optional). Der Preisstand der Position bleibt,
        die Rechnung ändert sich nicht. Ergebnis: Anzahl angelegter Artikel."""
        n = 0
        for r in [r for r in zeilen if r < len(self.eintraege) and zukauf.ist_frei(self.eintraege[r])]:
            e = self.eintraege[r]
            werte, bezuege = zukauf.frei_artikel_werte(e)
            try:
                aid = self.db.zukauf_speichern(None, werte, bezuege, "Aus Angebot in den Artikelstamm übernommen")
            except ValueError as ex:
                self.info.setText(f"{werte.get('bezeichnung')}: {ex}")
                continue
            e.pop(zukauf.FREI, None)
            e["artikel_id"] = aid
            n += 1
        if n:
            self.artikel = {a["id"]: a for a in self.db.zukauf_artikel_liste()}
            for r in zeilen:
                a = self.artikel.get(self.eintraege[r].get("artikel_id")) if r < len(self.eintraege) else None
                if a and self.auswahl.findData(a["id"]) < 0:
                    self.auswahl.addItem(artikel_name(a), a["id"])
            self._zeigen()
            self._details_fuellen()
            self.info.setText(f"{n} Artikel im Artikelstamm gespeichert (die Kalkulation bleibt gleich).")
        return n

    def vergleich(self, zeilen=None):
        """[(Zeile, Artikel, VK je Teil alt, VK je Teil neu, neuer Stand)] der Stammartikel mit geändertem
        Preisstand (zeilen None = alle). Freie Artikel haben keinen Stamm und fehlen hier."""
        out = []
        for r in range(len(self.eintraege)) if zeilen is None or not zeilen else zeilen:
            if r >= len(self.eintraege):
                continue
            e = self.eintraege[r]
            if zukauf.ist_frei(e):
                continue
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
            self.info.setText("Alle gewählten Zukaufteile aus dem Artikelstamm haben den aktuellen Preisstand.")
            return 0
        text = "; ".join(f"{name}: VK je Teil {preis_text(a)} € → {preis_text(n)} €" for _, name, a, n, _ in liste)
        # B3 (Verbesserungsplan 06.11.2026): ohne Rückfrage; Abbrechen verwirft, nach OK nimmt Strg+Z es zurück
        if bestaetigt is False:
            return 0
        for r, _, _, _, neu in liste:
            self.eintraege[r]["stand"] = neu
            self.eintraege[r].pop(zukauf.GEAENDERT, None)
        self._zeigen()
        self.info.setText(f"Neuer Preisstand übernommen ({text}). Abbrechen verwirft das, nach OK geht es mit "
                          "Strg+Z zurück.")
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
        r, name = it.row(), EDIT[it.column()]
        if r >= len(self.eintraege):              # leere Zeile unten: neuer freier Artikel
            t = it.text().strip()
            if name == "bezeichnung" and t and t != NEU_TEXT:
                try:
                    self.frei_hinzufuegen(t, 1, je=self.je.currentData())
                except ValueError as ex:
                    self.info.setText(str(ex))
                    self._zeigen()
                    return
                QTimer.singleShot(0, self, lambda: self.tabelle.setCurrentCell(r, 1))
            else:
                self._zeigen()
            return
        try:
            w = it.text() if name in ("bezeichnung", "artikelnr") else \
                _zahl(it.text(), SPALTEN[it.column()], name != "menge")
        except ValueError as ex:
            self._zeigen()
            self.info.setText(str(ex))
            return
        self.feld_setzen(r, name, w)

    # -------------------------------------------------------------- Anzeige
    def _stueck(self):
        s = self.p.get("stueck")
        return s if isinstance(s, (int, float)) and s > 0 else 1

    def _vorschau(self, eintraege):
        """Beträge für die Stückzahl der Position: einstand, vk je Teil; einstand_einheit, vk_einheit je Einheit
        des Artikels; regel, fehler, warnung."""
        c = self._stueck()
        _, je = zukauf.rechnen([(n, zukauf.mit_angebotsaufschlag(e, self.kopf, self.blech_ids),
                                 zukauf.bezugsmenge(e, self.p, c)) for n, e in enumerate(eintraege)])
        out = []
        for n in range(len(eintraege)):
            x, v = je[n], je[n]["verbrauch"]
            out.append(dict(x, einstand=x["einstand"] / zukauf.dez(c), vk=x["vk"] / zukauf.dez(c),
                            einstand_einheit=x["einstand"] / v if v else None, vk_einheit=x["vk"] / v if v else None))
        return out

    def _regel_kurz(self, e, text):
        """Kurzanzeige der wirksamen Regel in der Spalte Aufschlag, z. B. '(10)' für 10 % auf den Einstand (grau);
        andere Methoden mit ganzem Text."""
        regeln = (zukauf.mit_angebotsaufschlag(e, self.kopf, self.blech_ids).get("stand") or {}).get("regeln") or []
        if len(regeln) == 1 and regeln[0].get("methode") == zukauf.PROZENT and regeln[0].get("wert") is not None:
            return f"({zahl_als_text(regeln[0]['wert'], 1)})"
        return text

    def _herkunft(self, e, veraltet):
        if zukauf.ist_frei(e):
            return OHNE_STAMM
        st = e.get("stand") or {}
        return ("Stamm, Stand " + datum_text(st.get("datum")) + (" · in Position geändert" if e.get(zukauf.GEAENDERT)
                                                                 else "")
                + (" · neuer Stand im Stamm" if veraltet else "")
                + ("" if e.get("artikel_id") in self.artikel else " · Artikel gelöscht"))

    def _zeigen(self):
        self._fuellen = True
        try:
            markiert = self._markiert()
            werte = self._vorschau(self.eintraege)
            self.tabelle.setRowCount(len(self.eintraege) + 1)
            veraltet = {r for r, *_ in self.vergleich()}
            grau = stil.farbe(stil.TEXT_GRAU)
            for r, (e, w) in enumerate(zip(self.eintraege, werte)):
                st = e.get("stand") or {}
                a = self.artikel.get(e.get("artikel_id"))
                ek = zukauf.ek_einheit(st)
                auf = zahl_als_text(e["aufschlag"], 1) if e.get("aufschlag") is not None else ""
                zellen = (st.get("bezeichnung") or (a or {}).get("bezeichnung") or st.get("artikelnr") or "?",
                          zahl_als_text(e.get("menge"), 3) if e.get("menge") is not None else "", "",
                          zukauf.EINHEIT_KURZ.get(st.get("einheit"), st.get("einheit") or ""),
                          st.get("artikelnr") or "", preis_text(ek) if ek is not None else "",
                          auf or self._regel_kurz(e, w["regel"]),
                          preis_text(w["vk_einheit"]) if not w["fehler"] and w["vk_einheit"] is not None else "",
                          preis_text(w["vk"]) + " €" if not w["fehler"] else w["fehler"],
                          self._herkunft(e, r in veraltet))
                for c, t in enumerate(zellen):
                    it = QTableWidgetItem(t)
                    if c not in EDIT:
                        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    if c in (1, 5, 6, 7, 8):
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if c == 6 and not auf:
                        it.setForeground(grau)
                        it.setToolTip(f"Wirksam: {w['regel']}.\nLeer = Aufschlag des Angebots (Zukaufteile) bzw. "
                                      "Regel des Artikels; eine Zahl ersetzt ihn für diese Position (% auf den "
                                      "Einstandspreis)")
                    if c == 7:
                        it.setToolTip("VK je Einheit eintippen: der Aufschlag % wird daraus gerechnet")
                    if c == 5 and ek is None:
                        it.setToolTip("EK fehlt: Einkaufspreis je Einheit eintragen")
                    if c == 0:
                        tipp = [f"{n}: {st[k]}" for k, n in (("hersteller", "Hersteller"), ("beschreibung",
                                "Beschreibung"), ("bemerkung", "Bemerkung")) if st.get(k)]
                        lief = (st.get("bezug") or {}).get("lieferant")
                        it.setToolTip("\n".join(tipp + ([f"Lieferant: {lief}"] if lief else [])))
                    if c == 9 and zukauf.ist_frei(e):
                        it.setForeground(grau)
                    self.tabelle.setItem(r, c, it)
                feld = self.tabelle.cellWidget(r, JE)
                if feld is None:      # Auswahlfeld je Zeile nur einmal anlegen: ein ersetztes Feld bliebe bis zum
                    feld = _je_feld()  # Löschen sichtbar und läge über anderen Zellen
                    feld.currentIndexChanged.connect(lambda _=0, r=r, feld=feld: self.je_setzen(r, feld.currentData()))
                    self.tabelle.setCellWidget(r, JE, feld)
                feld.blockSignals(True)
                feld.setCurrentIndex(1 if e.get("je") == zukauf.JE_SATZ else 0)
                feld.blockSignals(False)
            # leere Zeile unten: Bezeichnung eintippen = neuer Artikel (ohne Artikelstamm)
            r = len(self.eintraege)
            if self.tabelle.cellWidget(r, JE) is not None:
                self.tabelle.removeCellWidget(r, JE)
            for c in range(len(SPALTEN)):
                it = QTableWidgetItem(NEU_TEXT if c == 0 else "")
                if c:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setForeground(grau)
                    schrift = QFont(it.font())
                    schrift.setItalic(True)
                    it.setFont(schrift)
                    it.setToolTip("Bezeichnung eintippen: neuer Zukaufartikel dieser Position, ohne Artikelstamm")
                self.tabelle.setItem(r, c, it)
            gesamt = sum((w["vk"] for w in werte if not w["fehler"]), zukauf.NULL)
            fehler = sum(1 for w in werte if w["fehler"])
            self.info.setText(
                f"Summe Zukaufartikel: {preis_text(gesamt)} € je Teil, "
                f"{preis_text(gesamt * zukauf.dez(self._stueck()))} € für {zahl_als_text(self._stueck(), 0)} Teile "
                "(ohne Skonto)."
                + (f" {fehler} Artikel ohne Einkaufspreis: das Angebot zeigt dafür einen Hinweis." if fehler else "")
                + (f" {len(veraltet)} Artikel mit neuem Preisstand im Artikelstamm." if veraltet else "")
                + " Im Angebot werden gleiche Artikel aller Positionen zusammen bestellt (Staffel, Mindestmenge, "
                  "Bezugskosten einmal)." if self.eintraege else
                "Noch keine Zukaufartikel: Bezeichnung oben oder in die leere Zeile tippen, Menge und EK eintragen.")
            if markiert and markiert[0] < self.tabelle.rowCount():
                self.tabelle.selectRow(markiert[0])
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
