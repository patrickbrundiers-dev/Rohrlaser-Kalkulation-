"""Normteile ohne Preis gesammelt nachtragen (Vorschlag M6, Patrick 07.11.2026): Unterreiter der Zukaufartikel mit allen
Normteilen (Kategorie Normteile bzw. Artikeltyp Normteil) ohne Einkaufspreis. Der EK wird direkt in der Zeile
eingetragen; „Speichern“ schreibt alle eingetragenen Preise auf einmal (db.zukauf_ek_eintragen, Protokoll der
Preisänderungen wie sonst). Der Angebots-Check nennt Normteile ohne Preis eines Angebots und springt hierher.

„Preise aus CSV …“ (L5, Patrick 08.11.2026): Preisliste des Lieferanten (Spalten Bezeichnung, Artikelnummer, Preis;
Semikolon, Komma oder Tab) lesen, den Normteilen zuordnen (Artikelnummer, sonst Norm + Gewinde + Länge, sonst gleiche
Bezeichnung) und die Preise in die Zeilen eintragen; gespeichert wird erst mit „Preise speichern“.
"""
import csv
import io
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import zukauf

TITEL = "Normteile ohne Preis"


def ist_normteil(a):
    from .step import NORMTEIL_KATEGORIE, NORMTEIL_TYP
    return a.get("kategorie") == NORMTEIL_KATEGORIE or a.get("artikeltyp") == NORMTEIL_TYP


def ohne_preis(db):
    """Normteil-Artikel (nicht archiviert) ohne Einkaufspreis, nach Bezeichnung."""
    return sorted((a for a in db.zukauf_artikel_liste() if ist_normteil(a) and a.get("status") != "archiviert"
                   and zukauf.ek_fehlt(a)), key=lambda a: (a.get("bezeichnung") or "").casefold())


def ids_ohne_preis(db):
    return {a["id"] for a in ohne_preis(db)}


# ------------------------------------------------------------------ L5 Preisliste des Lieferanten
SPALTE_BEZ = ("bezeichnung", "artikelbezeichnung", "beschreibung", "text", "artikeltext", "benennung")
SPALTE_NR = ("artikelnummer", "artikelnr", "artnr", "art-nr", "art.-nr.", "art.nr.", "bestellnummer", "bestellnr",
             "nummer", "sachnummer", "materialnummer")
SPALTE_PREIS = ("preis", "ek", "einkaufspreis", "nettopreis", "netto", "preis netto", "preis/stück", "stückpreis",
                "preis je stück", "ek je stück", "listenpreis")


def _kopf(t):
    return re.sub(r"\s+", " ", (t or "").replace("\ufeff", "").strip().casefold().replace("€", "").strip(" []()"))


def _spalte(kopf, namen):
    for i, k in enumerate(kopf):
        if k in namen:
            return i
    for i, k in enumerate(kopf):                    # „Preis netto EUR“, „Artikelnummer Lieferant“ …
        if any(k.startswith(n) for n in namen if len(n) > 3):
            return i
    return None


def _preis(text):
    t = re.sub(r"[^\d,.\-]", "", text or "")
    if not t:
        return None
    if "," in t:                                    # deutsch: 1.234,56
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def preisliste_lesen(roh):
    """CSV-Text oder -Bytes der Preisliste -> [dict(bezeichnung, artikelnr, preis)]; ValueError, wenn die Kopfzeile
    keine Preis-Spalte oder weder Bezeichnung noch Artikelnummer hat. Zeilen ohne lesbaren Preis über 0 € entfallen."""
    if isinstance(roh, bytes):
        for kod in ("utf-8-sig", "cp1252"):
            try:
                roh = roh.decode(kod)
                break
            except UnicodeDecodeError:
                continue
    zeilen = [z for z in roh.splitlines() if z.strip()]
    if not zeilen:
        raise ValueError("Die Datei ist leer.")
    trenner = max(";\t,", key=lambda c: zeilen[0].count(c))
    daten = list(csv.reader(io.StringIO("\n".join(zeilen)), delimiter=trenner))
    kopf = [_kopf(k) for k in daten[0]]
    ib, inr, ip = _spalte(kopf, SPALTE_BEZ), _spalte(kopf, SPALTE_NR), _spalte(kopf, SPALTE_PREIS)
    if ip is None or (ib is None and inr is None):
        raise ValueError("Kopfzeile mit den Spalten Bezeichnung und/oder Artikelnummer und Preis fehlt "
                         f"(gefunden: {'; '.join(daten[0])}).")
    out = []
    for z in daten[1:]:
        def w(i):
            return z[i].strip() if i is not None and i < len(z) else ""
        preis = _preis(w(ip))
        if preis and preis > 0 and (w(ib) or w(inr)):
            out.append(dict(bezeichnung=w(ib), artikelnr=w(inr), preis=preis))
    return out


def _nr(t):
    return re.sub(r"[\s.\-_/]", "", (t or "").upper())


def _bez(t):
    return re.sub(r"[\s,;]", "", (t or "").upper().replace("×", "X"))


def normteil_schluessel(t):
    """Norm, Nummer, Gewinde/Größe und Länge aus einer Bezeichnung, z. B. 'Sechskantschraube DIN 933 M8 x 20 8.8'
    -> ('DIN', '933', 'M8', '20'); None ohne Norm oder ohne Größe."""
    t = (t or "").upper().replace("×", "X").replace(",", ".")
    n = re.search(r"\b(DIN|ISO|EN)\s*(?:EN\s*)?(?:ISO\s*)?(\d{2,5})\b", t)
    g = re.search(r"\bM\s*(\d+(?:\.\d+)?)(?:\s*X\s*(\d+(?:\.\d+)?))?", t)
    if not n or not g:
        return None
    return n.group(1), n.group(2), "M" + g.group(1), g.group(2) or ""


def zuordnen(artikel, liste):
    """Zeilen der Preisliste den Normteilen zuordnen. Ergebnis: ({artikel_id: (zeile, wie)}, [nicht zugeordnete
    Zeilen]). Reihenfolge: Artikelnummer (auch die des Lieferanten), dann Norm + Gewinde + Länge, dann gleiche
    Bezeichnung; nur eindeutige Treffer."""
    nach_nr, nach_schl, nach_bez = {}, {}, {}
    for a in artikel:
        nummern = {_nr(a.get("artikelnr"))} | {_nr(b.get("lieferanten_artnr")) for b in a.get("bezuege") or ()}
        for n in nummern - {""}:
            nach_nr.setdefault(n, []).append(a)
        s = normteil_schluessel(a.get("bezeichnung"))
        if s:
            nach_schl.setdefault(s, []).append(a)
        nach_bez.setdefault(_bez(a.get("bezeichnung")), []).append(a)
    treffer, rest = {}, []
    for z in liste:
        wahl = None
        for wie, kand in (("Artikelnummer", nach_nr.get(_nr(z["artikelnr"])) if _nr(z["artikelnr"]) else None),
                          ("Norm und Größe", nach_schl.get(normteil_schluessel(z["bezeichnung"]))
                           if normteil_schluessel(z["bezeichnung"]) else None),
                          ("Bezeichnung", nach_bez.get(_bez(z["bezeichnung"])) if _bez(z["bezeichnung"]) else None)):
            if kand and len(kand) == 1 and kand[0]["id"] not in treffer:
                wahl = (kand[0], wie)
                break
        if wahl:
            treffer[wahl[0]["id"]] = (z, wahl[1])
        else:
            rest.append(z)
    return treffer, rest


class NormteilPreisSeite(QWidget):
    """Liste der Normteile ohne EK mit Eingabefeld je Zeile und „Speichern“."""
    titel = TITEL
    SPALTEN = ("Bezeichnung", "Artikelnummer", "Lieferant", "EK je Stück [€]", "Herkunft")

    def __init__(self, db, meldung):
        super().__init__()
        self.db, self.meldung = db, meldung
        self.artikel = []
        lay = QVBoxLayout(self)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.tabelle = QTableWidget(0, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.verticalHeader().setDefaultSectionSize(28)
        for c, b in enumerate((260, 130, 150, 130)):
            self.tabelle.setColumnWidth(c, b)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tabelle, 1)
        unten = QHBoxLayout()
        self.csv_knopf = QPushButton("Preise aus CSV …")
        self.csv_knopf.setToolTip("Preisliste des Lieferanten (Bezeichnung, Artikelnummer, Preis) lesen und den "
                                  "Normteilen zuordnen; die Preise stehen danach zum Prüfen in den Zeilen, gespeichert "
                                  "wird erst mit „Preise speichern“")
        self.csv_knopf.clicked.connect(lambda: self.csv_waehlen())
        unten.addWidget(self.csv_knopf)
        unten.addStretch(1)
        self.speichern_knopf = QPushButton("Preise speichern")
        self.speichern_knopf.setToolTip("Alle eingetragenen Einkaufspreise speichern (Zeilen mit 0 € bleiben offen)")
        self.speichern_knopf.clicked.connect(lambda: self.speichern())
        unten.addWidget(self.speichern_knopf)
        lay.addLayout(unten)
        self.neu_laden()

    def neu_laden(self):
        self.artikel = ohne_preis(self.db)
        t = self.tabelle
        for r in range(t.rowCount()):        # alte Eingabefelder sofort weg (deleteLater kommt erst in der Ereignisschleife)
            alt = t.cellWidget(r, 3)
            if alt is not None:
                alt.hide()
        t.setRowCount(0)
        t.setRowCount(len(self.artikel))
        for r, a in enumerate(self.artikel):
            b = (a.get("bezuege") or [{}])[0]
            for c, w in enumerate((a.get("bezeichnung"), a.get("artikelnr"), b.get("lieferant"), None,
                                   a.get("herkunft"))):
                if c == 3:
                    continue
                it = QTableWidgetItem("" if w is None else str(w))
                it.setData(Qt.UserRole, a["id"])
                t.setItem(r, c, it)
            feld = QDoubleSpinBox()
            feld.setDecimals(zukauf.STELLEN_EINHEIT)
            feld.setRange(0, 1_000_000)
            feld.setSuffix(" €")
            feld.setSpecialValueText("–")
            t.setCellWidget(r, 3, feld)
        n = len(self.artikel)
        self.info.setText(
            f"{n} Normteil{'e' if n != 1 else ''} ohne Einkaufspreis. EK je Stück eintragen und „Preise speichern“: "
            "der Preis gilt dann in allen Angeboten (beim nächsten Import und beim Aktualisieren der Zukaufpreise)."
            if n else "Alle Normteile haben einen Einkaufspreis.")
        self.speichern_knopf.setEnabled(bool(n))
        self.csv_knopf.setEnabled(bool(n))
        if getattr(self, "nach_laden", None):
            self.nach_laden()

    def preis_setzen(self, zeile, preis):
        """Für Tests und Tastatur: EK der Zeile eintragen (noch nicht gespeichert)."""
        self.tabelle.cellWidget(zeile, 3).setValue(preis)

    def csv_waehlen(self):
        pfad, _ = QFileDialog.getOpenFileName(self, "Preisliste des Lieferanten", "", "CSV (*.csv *.txt);;Alle (*)")
        if pfad:
            with open(pfad, "rb") as f:
                return self.csv_uebernehmen(f.read())
        return None

    def csv_uebernehmen(self, roh):
        """L5: Preisliste lesen, zuordnen und die Preise in die Zeilen eintragen (gelb hinterlegt, Herkunft im
        Tooltip); noch nicht gespeichert. Ergebnis: (zugeordnet, nicht zugeordnet)."""
        try:
            liste = preisliste_lesen(roh)
        except ValueError as e:
            self.meldung(f"Preisliste nicht lesbar: {e}", True)
            return 0, []
        treffer, rest = zuordnen(self.artikel, liste)
        farbe = QColor(255, 243, 176)
        for r, a in enumerate(self.artikel):
            if a["id"] not in treffer:
                continue
            z, wie = treffer[a["id"]]
            feld = self.tabelle.cellWidget(r, 3)
            feld.setValue(z["preis"])
            feld.setToolTip(f"Aus der Preisliste ({wie}): {z['bezeichnung'] or ''} {z['artikelnr'] or ''}".strip())
            for c in (0, 1, 2, 4):
                it = self.tabelle.item(r, c)
                if it is not None:
                    it.setBackground(farbe)
        n = len(treffer)
        self.info.setText(f"Preisliste: {n} von {len(liste)} Zeile{'n' if len(liste) != 1 else ''} zugeordnet "
                          "(gelb). Preise prüfen und „Preise speichern“."
                          + (f" Nicht zugeordnet: {len(rest)} (z. B. "
                             + ", ".join((z['bezeichnung'] or z['artikelnr']) for z in rest[:3]) + ")" if rest else ""))
        return n, rest

    def speichern(self):
        """Alle Zeilen mit EK über 0 € speichern. Ergebnis: Anzahl gespeicherter Preise."""
        n, fehler = 0, []
        for r, a in enumerate(self.artikel):
            preis = self.tabelle.cellWidget(r, 3).value()
            if preis <= 0:
                continue
            try:
                self.db.zukauf_ek_eintragen(a["id"], preis, bemerkung="Normteile ohne Preis")
                n += 1
            except ValueError as e:
                fehler.append(f"{a.get('bezeichnung')}: {e}")
        self.neu_laden()
        if n or fehler:
            self.meldung(f"{n} Normteil-Preis{'e' if n != 1 else ''} gespeichert."
                         + (" Nicht gespeichert: " + "; ".join(fehler) if fehler else ""), bool(fehler))
        return n
