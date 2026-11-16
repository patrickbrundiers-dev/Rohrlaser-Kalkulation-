"""Normteile ohne Preis gesammelt nachtragen (Vorschlag M6, Patrick 07.11.2026): Unterreiter der Zukaufartikel mit allen
Normteilen (Kategorie Normteile bzw. Artikeltyp Normteil) ohne Einkaufspreis. Der EK wird direkt in der Zeile
eingetragen; „Speichern“ schreibt alle eingetragenen Preise auf einmal (db.zukauf_ek_eintragen, Protokoll der
Preisänderungen wie sonst). Der Angebots-Check nennt Normteile ohne Preis eines Angebots und springt hierher.

„Preise aus CSV …“ (L5, Patrick 08.11.2026): Preisliste des Lieferanten (Spalten Bezeichnung, Artikelnummer, Preis;
Semikolon, Komma oder Tab) lesen, den Normteilen zuordnen (Artikelnummer, sonst Norm + Gewinde + Länge, sonst gleiche
Bezeichnung) und die Preise in die Zeilen eintragen; gespeichert wird erst mit „Preise speichern“.

PART-009 (Roadmap Phase 2, Paket 2e, 13.11.2026): „Preise anfragen …“ schreibt je Lieferant eine Preisanfrage mit allen
Normteilen ohne Preis (Lieferant des bevorzugten Bezugs, sonst der oben gewählte) und öffnet sie in Outlook bzw.
speichert sie als E-Mail-Datei (.eml); gesendet wird nie von selbst.

K4 (Patrick 08.11.2026): Lieferant der Preisliste wählbar (wird beim Speichern beim Artikel eingetragen); weicht der
Preis der Liste bei Normteilen MIT Preis ab, zeigt „Vorhandene Preise aktualisieren (N) …“ alt → neu zum Prüfen.
"""
import csv
import io
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

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


def mit_preis(db):
    """K4: Normteil-Artikel (nicht archiviert) mit Einkaufspreis."""
    return [a for a in db.zukauf_artikel_liste() if ist_normteil(a) and a.get("status") != "archiviert"
            and not zukauf.ek_fehlt(a)]


def ek_aktuell(a, lieferant=None):
    """EK je Stück (ab 1) beim Lieferanten bzw. dem bevorzugten Bezug, None ohne Preis."""
    b = zukauf.bezug_waehlen(a.get("bezuege"), lieferant)
    ek = zukauf.ek_je_einheit(b, 1)[0] if b else None
    return float(ek) if ek is not None else None


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


def _merkmal_kand(nach_merkmal, bezeichnung):
    """PART-004: Artikel mit gleichen Normteil-Merkmalen wie die Zeile der Preisliste."""
    from . import normteil
    m = normteil.merkmale(bezeichnung)
    if not normteil.schluessel(m):
        return None
    return [a for a, ma in nach_merkmal if normteil.gleich(ma, m)] or None


def zuordnen(artikel, liste):
    """Zeilen der Preisliste den Normteilen zuordnen. Ergebnis: ({artikel_id: (zeile, wie)}, [nicht zugeordnete
    Zeilen]). Reihenfolge: Artikelnummer (auch die des Lieferanten), dann Norm + Gewinde + Länge, dann gleiche
    Bezeichnung; nur eindeutige Treffer."""
    nach_nr, nach_schl, nach_bez, nach_merkmal = {}, {}, {}, []
    for a in artikel:
        nummern = {_nr(a.get("artikelnr"))} | {_nr(b.get("lieferanten_artnr")) for b in a.get("bezuege") or ()}
        for n in nummern - {""}:
            nach_nr.setdefault(n, []).append(a)
        s = normteil_schluessel(a.get("bezeichnung"))
        if s:
            nach_schl.setdefault(s, []).append(a)
        else:           # PART-004: Merkmale des Artikels (DIN = ISO gleichwertig, Festigkeit/Oberfläche)
            from . import normteil
            m = normteil.von_artikel(a)
            if normteil.schluessel(m):
                nach_merkmal.append((a, m))
        nach_bez.setdefault(_bez(a.get("bezeichnung")), []).append(a)
    treffer, rest = {}, []
    for z in liste:
        wahl = None
        for wie, kand in (("Artikelnummer", nach_nr.get(_nr(z["artikelnr"])) if _nr(z["artikelnr"]) else None),
                          ("Norm und Größe", nach_schl.get(normteil_schluessel(z["bezeichnung"]))
                           if normteil_schluessel(z["bezeichnung"]) else None),
                          ("Norm und Größe", _merkmal_kand(nach_merkmal, z["bezeichnung"])),
                          ("Bezeichnung", nach_bez.get(_bez(z["bezeichnung"])) if _bez(z["bezeichnung"]) else None)):
            if kand and len(kand) == 1 and kand[0]["id"] not in treffer:
                wahl = (kand[0], wie)
                break
        if wahl:
            treffer[wahl[0]["id"]] = (z, wahl[1])
        else:
            rest.append(z)
    return treffer, rest


# ------------------------------------------------------------------ PART-009 Sammel-Preisanfrage
OHNE_LIEFERANT = "ohne Lieferant"


def preisanfragen(artikel, mails, lieferant=None, einst=None):
    """Je Lieferant eine Anfrage: [dict(lieferant, an, betreff, text, ids)]. Lieferant des Artikels = bevorzugter
    Bezug, sonst lieferant (Auswahl oben), sonst OHNE_LIEFERANT (Empfänger leer). mails = {Lieferant: E-Mail}."""
    from . import materialanfrage, normteil
    gruppen = {}
    for a in artikel:
        b = zukauf.bezug_waehlen(a.get("bezuege")) or {}
        name = (b.get("lieferant") or "").strip() or (lieferant or "").strip() or OHNE_LIEFERANT
        gruppen.setdefault(name, []).append((a, b))
    out = []
    for name in sorted(gruppen, key=lambda n: (n == OHNE_LIEFERANT, n.casefold())):
        zeilen = []
        for a, b in gruppen[name]:
            m = normteil.text(normteil.von_artikel(a))
            nr = b.get("lieferanten_artnr") or a.get("artikelnr")
            zeilen.append(f"- {a.get('bezeichnung') or ''}" + (f" ({m})" if m and m != a.get("bezeichnung") else "")
                          + (f", Ihre Art.-Nr. {nr}" if nr else ""))
        text = ("Sehr geehrte Damen und Herren,\n\nbitte nennen Sie uns Ihre Einkaufspreise netto je Stück (bzw. je "
                "Preiseinheit) mit Lieferzeit für folgende Normteile:\n\n" + "\n".join(zeilen)
                + "\n\nVielen Dank und freundliche Grüße")
        n = len(zeilen)
        out.append(dict(lieferant=name, an="" if name == OHNE_LIEFERANT else (mails or {}).get(name, ""),
                        betreff=f"Preisanfrage Normteile ({n} Artikel)",
                        text=materialanfrage.mit_signatur(text, materialanfrage.signatur(einst)),
                        ids=[a["id"] for a, _ in gruppen[name]]))
    return out


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
        self.lieferant = QComboBox()            # K4
        self.lieferant.setEditable(True)
        self.lieferant.lineEdit().setPlaceholderText("Lieferant (wie beim Artikel)")
        self.lieferant.setMinimumWidth(200)
        self.lieferant.setToolTip("Lieferant, bei dem die Preise eingetragen werden (leer = wie beim Artikel)")
        unten.addWidget(self.lieferant)
        self.aktualisieren_knopf = QPushButton()
        self.aktualisieren_knopf.setToolTip("Normteile mit Preis, deren Preis in der Preisliste anders ist: alt → neu "
                                            "prüfen und übernehmen")
        self.aktualisieren_knopf.clicked.connect(lambda: self.vorhandene_aktualisieren())
        self.aktualisieren_knopf.hide()
        unten.addWidget(self.aktualisieren_knopf)
        self.abweichend = []
        self.anfrage_knopf = QPushButton("Preise anfragen …")      # PART-009
        self.anfrage_knopf.setToolTip("Je Lieferant eine Preisanfrage mit allen Normteilen ohne Preis: in Outlook "
                                      "öffnen (klassisches Outlook) bzw. als E-Mail-Datei speichern; gesendet wird "
                                      "erst von Ihnen")
        self.anfrage_knopf.clicked.connect(lambda: self.preise_anfragen())
        unten.addWidget(self.anfrage_knopf)
        unten.addStretch(1)
        self.speichern_knopf = QPushButton("Preise speichern")
        self.speichern_knopf.setToolTip("Alle eingetragenen Einkaufspreise speichern (Zeilen mit 0 € bleiben offen)")
        self.speichern_knopf.clicked.connect(lambda: self.speichern())
        unten.addWidget(self.speichern_knopf)
        lay.addLayout(unten)
        self.neu_laden()

    def neu_laden(self):
        self.artikel = ohne_preis(self.db)
        if hasattr(self, "lieferant"):
            text = self.lieferant.currentText()
            self.lieferant.clear()
            self.lieferant.addItems([""] + sorted(z["name"] for z in self.db.zeilen("zukauf_lieferanten")
                                                  if z.get("name")))
            self.lieferant.setCurrentText(text)
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
        if hasattr(self, "anfrage_knopf"):
            self.anfrage_knopf.setEnabled(bool(n))
        if getattr(self, "nach_laden", None):
            self.nach_laden()

    def preise_anfragen(self, ausfuehren=None, ordner=None):
        """PART-009: je Lieferant eine E-Mail in Outlook öffnen; ohne Outlook (oder mit ordner) als .eml-Dateien in
        einen Ordner. ausfuehren ersetzt den Outlook-Aufruf (Tests). Ergebnis: Liste der Anfragen (preisanfragen)."""
        from . import materialanfrage as ma
        if not self.artikel:
            return []
        einst = self.db.einstellungen()
        anfragen = preisanfragen(self.artikel, ma.lieferanten(self.db.zeilen("zukauf_lieferanten")),
                                 self.lieferant.currentText(), einst)
        offen, dateien = [], []
        for x in anfragen:
            if ordner is None:
                ok, _ = ma.outlook_oeffnen(x["an"], x["betreff"], x["text"], ausfuehren=ausfuehren)
                if ok:
                    continue
            offen.append(x)
        if offen:
            if ordner is None:
                ordner = QFileDialog.getExistingDirectory(self, "Preisanfragen als E-Mail-Dateien speichern")
                if not ordner:
                    return anfragen
            from pathlib import Path
            for x in offen:
                name = re.sub(r"[^\w\- ]", "_", x["lieferant"]).strip() or "Lieferant"
                dateien.append(ma.eml(Path(ordner) / f"Preisanfrage Normteile {name}.eml", x["an"], x["betreff"],
                                      x["text"]))
        ohne = [x for x in anfragen if not x["an"]]
        self.meldung(f"{len(anfragen)} Preisanfrage{'n' if len(anfragen) != 1 else ''} für {len(self.artikel)} "
                     f"Normteil{'e' if len(self.artikel) != 1 else ''}"
                     + (f" ({len(dateien)} als E-Mail-Datei gespeichert)" if dateien else " in Outlook geöffnet")
                     + (f"; ohne E-Mail-Adresse: {', '.join(x['lieferant'] for x in ohne)}" if ohne else "") + ".",
                     False)
        return anfragen

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
        lief = self.lieferant.currentText().strip() or None
        alt_treffer, _ = zuordnen(mit_preis(self.db), liste)          # K4: vorhandene Preise mit Abweichung
        self.abweichend = []
        for a in mit_preis(self.db):
            if a["id"] in alt_treffer:
                z, wie = alt_treffer[a["id"]]
                alt = ek_aktuell(a, lief)
                if alt is None or abs(alt - z["preis"]) > 1e-6:
                    self.abweichend.append(dict(artikel=a, alt=alt, neu=z["preis"], wie=wie))
        self.aktualisieren_knopf.setText(f"Vorhandene Preise aktualisieren ({len(self.abweichend)}) …")
        self.aktualisieren_knopf.setVisible(bool(self.abweichend))
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
        rest = [z for z in rest if not any(t[0] is z for t in alt_treffer.values())]     # schon mit Preis
        self.info.setText(f"Preisliste: {n} von {len(liste)} Zeile{'n' if len(liste) != 1 else ''} zugeordnet "
                          "(gelb). Preise prüfen und „Preise speichern“."
                          + (f" Nicht zugeordnet: {len(rest)} (z. B. "
                             + ", ".join((z['bezeichnung'] or z['artikelnr']) for z in rest[:3]) + ")" if rest else "")
                          + (f" {len(self.abweichend)} vorhandene Preis{'e' if len(self.abweichend) != 1 else ''} "
                             "weich" + ("en" if len(self.abweichend) != 1 else "t") + " ab: „Vorhandene Preise "
                             "aktualisieren …“." if self.abweichend else ""))
        return n, rest

    def vorhandene_aktualisieren(self, dialog=None):
        """K4: Liste alt → neu der abweichenden Preise mit Haken je Zeile; „Übernehmen“ speichert die angehakten
        (beim gewählten Lieferanten). dialog(d) bedient das Fenster (Tests). Ergebnis: Zahl gespeicherter Preise."""
        if not self.abweichend:
            return 0
        d = PreisAenderungDialog(self, self.abweichend)
        ok = (dialog(d) if dialog else d.exec()) == QDialog.Accepted
        if not ok:
            return 0
        lief = self.lieferant.currentText().strip() or None
        n = 0
        for x in d.gewaehlt():
            self.db.zukauf_ek_eintragen(x["artikel"]["id"], x["neu"], lieferant=lief, bemerkung="Preisliste (CSV)")
            n += 1
        self.abweichend = [x for x in self.abweichend if x not in d.gewaehlt()]
        self.aktualisieren_knopf.setText(f"Vorhandene Preise aktualisieren ({len(self.abweichend)}) …")
        self.aktualisieren_knopf.setVisible(bool(self.abweichend))
        self.meldung(f"{n} vorhandene{'r' if n == 1 else ''} Normteil-Preis{'e' if n != 1 else ''} aktualisiert.",
                     False)
        return n

    def speichern(self):
        """Alle Zeilen mit EK über 0 € speichern. Ergebnis: Anzahl gespeicherter Preise."""
        n, fehler = 0, []
        for r, a in enumerate(self.artikel):
            preis = self.tabelle.cellWidget(r, 3).value()
            if preis <= 0:
                continue
            try:
                self.db.zukauf_ek_eintragen(a["id"], preis, lieferant=self.lieferant.currentText().strip() or None,
                                            bemerkung="Normteile ohne Preis")
                n += 1
            except ValueError as e:
                fehler.append(f"{a.get('bezeichnung')}: {e}")
        self.neu_laden()
        if n or fehler:
            self.meldung(f"{n} Normteil-Preis{'e' if n != 1 else ''} gespeichert."
                         + (" Nicht gespeichert: " + "; ".join(fehler) if fehler else ""), bool(fehler))
        return n


class PreisAenderungDialog(QDialog):
    """K4: abweichende Preise der Preisliste alt → neu, je Zeile ein Haken (vorbelegt)."""

    def __init__(self, parent, abweichend):
        super().__init__(parent)
        self.setWindowTitle("Vorhandene Normteil-Preise aktualisieren")
        self.resize(760, 420)
        self.zeilen = list(abweichend)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Diese Normteile haben schon einen Einkaufspreis, die Preisliste nennt einen anderen. "
                             "Angehakte Zeilen werden übernommen (Protokoll der Preisänderungen wie sonst)."))
        t = self.tabelle = QTableWidget(len(self.zeilen), 5)
        t.setHorizontalHeaderLabels(("Bezeichnung", "Zugeordnet über", "EK alt [€]", "EK neu [€]", "Änderung"))
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, x in enumerate(self.zeilen):
            it = QTableWidgetItem(x["artikel"].get("bezeichnung") or "")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            t.setItem(r, 0, it)
            t.setItem(r, 1, QTableWidgetItem(x["wie"]))
            alt = x["alt"]
            for c, w in ((2, "–" if alt is None else f"{alt:.4f}".replace(".", ",")),
                         (3, f"{x['neu']:.4f}".replace(".", ",")),
                         (4, "" if not alt else f"{100 * (x['neu'] - alt) / alt:+.1f} %".replace(".", ","))):
                zelle = QTableWidgetItem(w)
                zelle.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, zelle)
        t.setColumnWidth(0, 280)
        t.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(t, 1)
        k = QDialogButtonBox()
        k.addButton("Übernehmen", QDialogButtonBox.AcceptRole)
        k.addButton(QDialogButtonBox.Cancel)
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        lay.addWidget(k)

    def gewaehlt(self):
        return [x for r, x in enumerate(self.zeilen) if self.tabelle.item(r, 0).checkState() == Qt.Checked]
