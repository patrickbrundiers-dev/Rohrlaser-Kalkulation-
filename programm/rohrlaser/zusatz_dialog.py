"""Dialog 'Zusatzarbeiten …' einer oder mehrerer Positionen: Gewinde (Anzahl x Größe) und Zusatzarbeiten
aus den Stammdaten (Verzinken, Pulverbeschichten, Gravur extra …) mit Menge, Preis bzw. Zeit und Text.

Aufbau seit dem Plan „Zusatzarbeiten besser erkennen“ (Patrick 03.11.2026, 4a): links eine Liste mit Suchfeld und
Häkchen (Vorschläge, häufig verwendet, bei diesem Kunden, nach Kategorie, nur in diesem Angebot), rechts die gewählten
mit Menge, Preis und € je Teil (live) und der Summe. Anhaken trägt ein, Abhaken entfernt; eine Zusatzarbeit steht
höchstens einmal in der Position. „＋ Neue Zusatzarbeit …“ öffnet das Kurzformular (zusatz_neu_dialog.py). Zur Auswahl
stehen nur aktive Zusatzarbeiten. Beim Hinzufügen wird der Preisstand (Abrechnung, Preis je Einheit, Mindestbetrag,
Fremdleistung) in der Position gespeichert; spätere Änderungen der Stammdaten ändern das Angebot erst nach 'Preise aus
Stammdaten übernehmen'."""
import json
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSplitter,
                               QTableWidget, QVBoxLayout, QWidget)

from . import hilfe, rechnen, zusatz_erkennung
from .angebot import POSITIONEN
from .stammdaten import ZUSATZ_EINHEIT, wert_aus_text, zahl_als_text, zahl_aus_text
from .eingabe import RechenSpinGanz
from .stil import GELB_FLAECHE, GELB_TEXT

SPALTEN = ("Zusatzarbeit", "Abrechnung", "Menge je Teil", "Preis je Einheit", "€ je Teil", "Text (z. B. RAL-Farbe)")
TIPPS = ("Zusatzarbeit aus den Stammdaten (oder nur in diesem Angebot angelegt)", "Abrechnung der Zusatzarbeit",
         "Menge je Teil: leer = automatisch (Gewicht, Außenfläche, Länge oder 1 Stück); bei €/h Sekunden je Teil",
         "Preis je Einheit: leer = Preisstand bzw. Stammdaten; bei s/Stück Zeit in s, bei €/h Stundensatz",
         "Betrag je Teil ohne Zuschläge und Gewinn (s/Stück: Zeit je Teil, kommt zur Laserzeit; €/Angebot: einmal)",
         "Text im Angebot, z. B. RAL 7016")
MENGE, PREIS, BETRAG, TEXT = 2, 3, 4, 5


def _euro(w):
    """Betrag mit zwei Nachkommastellen: 0,50 €."""
    return f"{w:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".") + " €"
EIGEN = "nur in diesem Angebot"         # Herkunft einer Zusatzarbeit aus dem Kurzformular (Plan 3c)


def _zahl(text, titel):
    t = text.strip()
    if not t:
        return None
    try:
        return zahl_aus_text(t)
    except ValueError:
        raise ValueError(f"{titel}: '{t}' ist keine Zahl.")


def _gleich(e):
    """Vergleichswert einer Zusatzarbeit (Name, Menge, Preis, Text) für 'haben alle Positionen gemeinsam'."""
    return e.get("name"), e.get("menge"), e.get("preis"), e.get("text") or None


def gemeinsam(positionen):
    """Was mehrere Positionen gemeinsam haben (Dialog bei Mehrfachauswahl): (Gewinde oder None, wenn es sich
    unterscheidet; Zusatzarbeiten, die in allen Positionen gleich stehen, Einträge der ersten Position)."""
    gewinde = {(p.get("gewinde") or "").strip() for p in positionen}
    listen = [rechnen.zusatz_liste(p) for p in positionen]
    alle = [{_gleich(e) for e in liste} for liste in listen[1:]]
    zusatz = [e for e in (listen[0] if listen else []) if all(_gleich(e) in s for s in alle)]
    return (gewinde.pop() if len(gewinde) == 1 else None), zusatz


def zusammenfuehren(p, vorher, ergebnis):
    """Neue Werte (Gewinde, Zusatzarbeiten) einer Position bei Mehrfachauswahl (Plan Angebotsablauf V0): nur das
    Gemeinsame (vorher = gemeinsam(...)) wird geändert, eigene Einträge der Position bleiben. Gewinde: war es
    überall gleich, gilt der neue Text; sonst werden eingegebene Gewinde angehängt, die die Position noch nicht hat. Zusatzarbeiten: gemeinsame, die
    im Dialog gelöscht oder geändert wurden, fallen weg; neue bzw. geänderte kommen dazu (gleicher Name ersetzt den
    eigenen Eintrag). Unveränderte behalten den Eintrag der Position (Menge, Preisstand, Herkunft)."""
    g_vorher, z_vorher = vorher
    g_neu, z_json = ergebnis
    if g_vorher is not None:
        gewinde = g_neu
    else:
        eigen = [x.strip() for x in re.split(r"[;,]", p.get("gewinde") or "") if x.strip()]
        dazu = [x.strip() for x in re.split(r"[;,]", g_neu or "") if x.strip() and x.strip() not in eigen]
        gewinde = "; ".join(eigen + dazu) or None
    neu = rechnen.zusatz_liste(dict(zusatz=z_json)) if z_json else []
    neu_gleich = {_gleich(e) for e in neu}
    weg = {_gleich(e) for e in z_vorher} - neu_gleich          # gemeinsam, im Dialog gelöscht oder geändert
    unveraendert = {_gleich(e) for e in z_vorher} & neu_gleich
    neu_namen = {e["name"] for e in neu if _gleich(e) not in unveraendert}
    liste = [e for e in rechnen.zusatz_liste(p) if _gleich(e) not in weg and e["name"] not in neu_namen]
    vorhanden = {_gleich(e) for e in liste}
    liste += [e for e in neu if _gleich(e) not in vorhanden]
    return gewinde, (json.dumps(liste, ensure_ascii=False) if liste else None)


def automatisch_text(p, k, tabellen, kopf=None):
    """Hinweis auf automatische Zusatzarbeiten der Position (Arbeitsgang-Regeln mit Zuordnung automatisch), leer ohne."""
    auto = [z for z in rechnen.zusatz_werte(p, k, tabellen, kopf) if z["auto"]] if k else []
    if not auto:
        return ""
    teile = [f"{z['name']} (Regel „{z['regel']}“: {rechnen.zahl(z['menge'])} {z['einheit']} × "
             f"{rechnen.zahl(z['preis'])} € = {rechnen.zahl(z['betrag'] + z['pauschal'])} € je Teil)" for z in auto]
    return ("Automatisch aus den Regeln: " + "; ".join(teile) + ". Abwählen oder fest übernehmen: „Arbeitsgänge "
            "vorschlagen …“. Wer sie hier hinzufügt, rechnet sie nur einmal (der eigene Eintrag gilt).")


def katalog_aktiv(tabellen):
    """Aktive Zusatzarbeiten der Stammdaten {Name: Zeile}."""
    return {z["name"]: z for z in tabellen.get("zusatzarbeiten") or () if z.get("name") and z.get("aktiv") != "nein"}


def angebot_eigene(positionen, tabellen):
    """{Name: Preisstand} der Zusatzarbeiten, die nur in diesem Angebot angelegt sind (Eintrag mit Preisstand, Name
    nicht in den Stammdaten), nach Namen sortiert."""
    namen = {z.get("name") for z in tabellen.get("zusatzarbeiten") or ()}
    out = {}
    for p in positionen or ():
        for e in rechnen.zusatz_liste(p):
            if e["name"] not in namen and isinstance(e.get("stand"), dict):
                out.setdefault(e["name"], e["stand"])
    return dict(sorted(out.items(), key=lambda x: x[0].lower()))


def neuer_eintrag(name, tabellen, positionen=()):
    """Eintrag für positionen.zusatz mit Preisstand: aus den Stammdaten bzw. der Zusatzarbeit nur dieses Angebots;
    None, wenn es sie nicht gibt."""
    kz = katalog_aktiv(tabellen).get(name)
    if kz is not None:
        return dict(name=name, menge=None, preis=None, text=None, stand=rechnen.zusatz_stand(
            kz, rechnen.stundensaetze(tabellen)))
    stand = angebot_eigene(positionen, tabellen).get(name)
    return dict(name=name, menge=None, preis=None, text=None, quelle=EIGEN, stand=dict(stand)) if stand else None


def haeufigste(tabellen, haeufig, n=8):
    """Die n häufigsten aktiven Zusatzarbeiten (Rechtsklick-Schnellmenü), aufgefüllt nach Kategorie und Name."""
    aktive = katalog_aktiv(tabellen)
    oft = sorted((x for x in aktive if (haeufig or {}).get(x)), key=lambda x: (-haeufig[x], x.lower()))
    rest = sorted((x for x in aktive if x not in oft),
                  key=lambda x: ((aktive[x].get("kategorie") or "~").lower(), x.lower()))
    return (oft + rest)[:n]


class ZusatzDialog(QDialog):
    """p: erste gewählte Position (für Vorgaben und automatische Mengen), anzahl: gewählte Positionen."""

    def __init__(self, parent, p, anzahl, k, tabellen, haeufig=None, weitere=None, gewinde_verschieden=False,
                 kopf=None, kunde_haeufig=None, positionen=None, neu=None):
        """weitere: {Knopftext: Funktion} für die übrige Bearbeitung der Position (Schweißnaht, Bohrungen), damit
        alles über einen Dialog erreichbar ist (Prüfbericht C-5). Mehrere Positionen: p zeigt nur, was alle gemeinsam
        haben (gemeinsam); gewinde_verschieden = die Gewinde unterscheiden sich, das Feld ergänzt dann nur.
        kunde_haeufig: {Name: Anzahl} beim Kunden dieses Angebots; positionen: alle Positionen des Angebots (für die
        Zusatzarbeiten nur dieses Angebots); neu(): Kurzformular, Ergebnis Eintrag für die Position oder None."""
        super().__init__(parent)
        self.p, self.k, self.tabellen, self.kopf = p, k, tabellen, kopf
        self.anzahl = anzahl
        self.katalog = {z["name"]: z for z in tabellen.get("zusatzarbeiten") or () if z.get("name")}
        self.eigene = angebot_eigene(positionen or (), tabellen)
        self.saetze = rechnen.stundensaetze(tabellen)
        self.haeufig = haeufig or {}
        self.kunde_haeufig = kunde_haeufig or {}
        self.neu_funktion = neu
        self.stand = {}         # Auswahlfeld -> (Name beim Öffnen, gespeicherter Preisstand)
        self.quelle = {}        # Auswahlfeld -> Herkunft des Eintrags (bohrbild.QUELLE, Erkannt …) oder None
        self.gewinde_tab = tabellen.get("gewinde") or []
        self.vorschlaege = zusatz_erkennung.offen(p, kopf, k, tabellen) if anzahl == 1 and k is not None else []
        self._sync = False
        self.setWindowTitle("Zusatzarbeiten" + (f" für {anzahl} Positionen" if anzahl > 1 else
                                               f" Pos. {p.get('pos') or ''} {p.get('artikel') or ''}"))
        self.resize(1080, 520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.gewinde = QLineEdit(p.get("gewinde") or "")
        self.gewinde.setPlaceholderText("unterschiedlich – Eingabe wird bei jeder Position ergänzt"
                                        if gewinde_verschieden else "z. B. 4xM6; 2xM8")
        self.gewinde.textChanged.connect(self._gewinde_info)
        self.gewinde_info = QLabel()
        self.gewinde_info.setStyleSheet("color: #5F6B7A;")
        # Gewinde aus der Liste der Stammdaten hinzufügen statt frei tippen: Anzahl × Größe
        zeile = QHBoxLayout()
        zeile.addWidget(self.gewinde, 1)
        self.gewinde_anzahl = RechenSpinGanz()
        self.gewinde_anzahl.setRange(1, 999)
        self.gewinde_anzahl.setSuffix(" ×")
        self.gewinde_wahl = QComboBox()
        self.gewinde_wahl.addItems([str(g.get("gewinde")) for g in self.gewinde_tab if g.get("gewinde")])
        dazu = QPushButton("Gewinde hinzufügen")
        dazu.setToolTip("Anzahl × gewähltes Gewinde an die Liste anhängen (z. B. 4xM6; 2xM8)")
        dazu.clicked.connect(self.gewinde_hinzufuegen)
        for w in (self.gewinde_anzahl, self.gewinde_wahl, dazu):
            zeile.addWidget(w)
        form.addRow("Gewinde ergänzen" if gewinde_verschieden else "Gewinde (geprüft)", zeile)
        form.addRow("", self.gewinde_info)
        lay.addLayout(form)
        # erkannte Zusatzarbeiten und Regel-Vorschläge (Plan 03.11.2026, 1a): gelb, erst nach Übernehmen gerechnet
        self.vorschlag_leiste = QWidget()
        vl = QHBoxLayout(self.vorschlag_leiste)
        vl.setContentsMargins(6, 4, 6, 4)
        self.vorschlag_text = QLabel()
        self.vorschlag_text.setWordWrap(True)
        vl.addWidget(self.vorschlag_text, 1)
        self.vorschlag_knopf = QPushButton("Alle übernehmen")
        self.vorschlag_knopf.clicked.connect(self.vorschlaege_uebernehmen)
        vl.addWidget(self.vorschlag_knopf)
        self.vorschlag_leiste.setStyleSheet(f"background: {GELB_FLAECHE}; color: {GELB_TEXT};")
        lay.addWidget(self.vorschlag_leiste)
        # links: Suche und Liste mit Häkchen, rechts: gewählte mit € je Teil
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen (Name, Kategorie, Erkennungswort) …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self._filtern)
        self.liste = QListWidget()
        self.liste.setToolTip("Häkchen setzen = Zusatzarbeit eintragen, Häkchen weg = entfernen")
        self.liste.itemChanged.connect(self._liste_geklickt)
        ll.addWidget(self.suche)
        ll.addWidget(self.liste, 1)
        self.neu_knopf = QPushButton("＋ Neue Zusatzarbeit …")
        self.neu_knopf.setToolTip("Kurzformular: Name, Abrechnung, Preis, Fremdleistung, Kategorie, Erkennungswörter. "
                                  "Gilt erst nur in diesem Angebot; ein Admin übernimmt sie in die Einstellungen.")
        self.neu_knopf.clicked.connect(self.neu_anlegen)
        self.neu_knopf.setVisible(neu is not None)
        ll.addWidget(self.neu_knopf)
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        for i, tipp in enumerate(TIPPS):
            self.tabelle.horizontalHeaderItem(i).setToolTip(tipp)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        kopf_ = self.tabelle.horizontalHeader()
        for i, b in enumerate((170, 82, 120, 130, 75)):
            self.tabelle.setColumnWidth(i, b)
        kopf_.setSectionResizeMode(TEXT, QHeaderView.Stretch)
        rl.addWidget(self.tabelle, 1)
        self.summe = QLabel()
        self.summe.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.summe.setStyleSheet("font-weight: bold;")
        rl.addWidget(self.summe)
        teiler = QSplitter(Qt.Horizontal)
        teiler.addWidget(links)
        teiler.addWidget(rechts)
        teiler.setStretchFactor(1, 1)
        teiler.setSizes([240, 840])
        teiler.setChildrenCollapsible(False)
        lay.addWidget(teiler, 1)
        leiste = QHBoxLayout()
        neu_zeile = QPushButton("Zusatzarbeit hinzufügen")
        neu_zeile.setToolTip("Leere Zeile anhängen und die Zusatzarbeit in der Zeile wählen (oder links anhaken)")
        neu_zeile.clicked.connect(lambda: self.zeile_neu())
        weg = QPushButton("Markierte entfernen")
        weg.clicked.connect(self._entfernen)
        self.stammdaten_knopf = QPushButton("Preise aus Stammdaten übernehmen")
        self.stammdaten_knopf.setToolTip("Gespeicherten Preisstand der Zeilen durch die aktuellen Werte der "
                                         "Stammdaten ersetzen (gilt beim Klick auf OK)")
        self.stammdaten_knopf.clicked.connect(self.stand_verwerfen)
        leiste.addWidget(neu_zeile)
        leiste.addWidget(weg)
        leiste.addWidget(self.stammdaten_knopf)
        leiste.addStretch(1)
        self.weitere_knoepfe = {}
        if weitere:
            leiste.addWidget(QLabel("Weitere Bearbeitung:"))
            for text, ziel in weitere.items():
                b = QPushButton(text)
                b.clicked.connect(lambda _=False, ziel=ziel: ziel())
                leiste.addWidget(b)
                self.weitere_knoepfe[text] = b
        lay.addLayout(leiste)
        # automatische Zusatzarbeiten aus den Arbeitsgang-Regeln (Plan Abrechnungsregeln): gelb, nur Anzeige
        self.automatisch = QLabel(automatisch_text(p, k, tabellen, kopf) if anzahl == 1 else "")
        self.automatisch.setWordWrap(True)
        self.automatisch.setStyleSheet(f"background: {GELB_FLAECHE}; color: {GELB_TEXT}; padding: 4px;")
        self.automatisch.setVisible(bool(self.automatisch.text()))
        lay.addWidget(self.automatisch)
        text = ("Links anhaken = eintragen. Menge und Preis leer lassen = automatisch: Menge aus der Position "
                "(Gewicht, Außenfläche, Länge oder 1 Stück), Preis aus den Stammdaten. € je Teil ohne Zuschläge und "
                "Gewinn. Abrechnung s/Stück: Zeit wird zur Schneidzeit addiert. Abrechnung €/h (z. B. Schweißen): "
                "Sekunden je Teil eintragen, gerechnet wird Sekunden ÷ 3600 × Stundensatz. Gelb = erkannt bzw. "
                "vorgeschlagen, kostet erst nach Übernehmen.")
        if anzahl > 1:
            text += (f" Gilt für alle {anzahl} markierten Positionen: die Liste zeigt nur, was alle gemeinsam haben. "
                     "Hinzugefügtes kommt bei jeder Position dazu, Gelöschtes fällt überall weg; eigene Gewinde und "
                     "Zusatzarbeiten einzelner Positionen (z. B. aus „Bohrungen prüfen“) bleiben. Automatische Mengen "
                     "rechnet jede Position selbst.")
        if not self.katalog:
            text += " Unter Einstellungen (Zusatzarbeiten) ist noch keine Zusatzarbeit angelegt."
        text += (" Der Preis der Stammdaten wird beim Hinzufügen in der Position gespeichert (Preisstand); spätere "
                 "Änderungen der Stammdaten gelten erst nach 'Preise aus Stammdaten übernehmen'.")
        hinweis = hilfe.Hinweis(text, schluessel="zusatz_dialog")
        lay.addWidget(hinweis)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #B42318;")
        lay.addWidget(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self._sync = True
        for e in rechnen.zusatz_liste(p):
            self.zeile_neu(e)
        self._sync = False
        self._liste_fuellen()
        self._vorschlaege_zeigen()
        self._gewinde_info()
        self._betraege()
        self.ergebnis = None

    # -------------------------------------------------------------- Liste links
    def gewaehlt(self):
        """Namen der Zeilen rechts (in Reihenfolge, ohne leere)."""
        return [self.tabelle.cellWidget(r, 0).currentText() for r in range(self.tabelle.rowCount())
                if self.tabelle.cellWidget(r, 0).currentText()]

    def _gruppen(self):
        """[(Überschrift, [Name])] für die Liste: Vorschläge, häufig, bei diesem Kunden, Kategorien, nur dieses Angebot."""
        aktive = [z for z in self.katalog.values() if z.get("aktiv") != "nein"]
        namen = {z["name"] for z in aktive}
        out = []
        vs = [v["name"] for v in self.vorschlaege if v["name"] in namen]
        if vs:
            out.append(("Vorschläge (erkannt)", vs))
        if len(aktive) > 5:
            oft = sorted((n for n in namen if self.haeufig.get(n)), key=lambda n: (-self.haeufig[n], n.lower()))[:5]
            if oft:
                out.append(("Häufig verwendet", oft))
            kunde = sorted((n for n in namen if self.kunde_haeufig.get(n)),
                           key=lambda n: (-self.kunde_haeufig[n], n.lower()))[:5]
            if kunde:
                out.append(("Bei diesem Kunden", kunde))
        gruppen = {}
        for z in aktive:
            gruppen.setdefault(z.get("kategorie") or "ohne Kategorie", []).append(z["name"])
        for g in sorted(gruppen, key=lambda g: (g == "ohne Kategorie", g.lower())):
            out.append((g, sorted(gruppen[g], key=str.lower)))
        if self.eigene:
            out.append(("Nur in diesem Angebot", list(self.eigene)))
        return out

    def _liste_fuellen(self):
        self._sync = True
        self.liste.clear()
        gewaehlt = set(self.gewaehlt())
        vs = {v["name"] for v in self.vorschlaege}
        for titel, namen in self._gruppen():
            it = QListWidgetItem(titel)
            it.setFlags(Qt.NoItemFlags)
            f = QFont()
            f.setBold(True)
            it.setFont(f)
            it.setData(Qt.UserRole, None)
            self.liste.addItem(it)
            for n in namen:
                it = QListWidgetItem("   " + n)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if n in gewaehlt else Qt.Unchecked)
                it.setData(Qt.UserRole, n)
                kz = self.katalog.get(n) or {}
                it.setToolTip(" · ".join(x for x in (kz.get("art") or (self.eigene.get(n) or {}).get("art"),
                                                    kz.get("bemerkung"), "Erkennung: " + kz["erkennung"]
                                                    if kz.get("erkennung") else None) if x))
                if n in vs and titel.startswith("Vorschläge"):
                    it.setBackground(QBrush(QColor(GELB_FLAECHE)))
                self.liste.addItem(it)
        self._sync = False
        self._filtern()

    def _filtern(self):
        """Suche: Name, Kategorie, Erkennungswörter (Überschriften ohne Treffer werden ausgeblendet)."""
        such = self.suche.text().strip().lower()
        titel = None
        sichtbar = False
        for i in range(self.liste.count()):
            it = self.liste.item(i)
            n = it.data(Qt.UserRole)
            if n is None:
                if titel is not None:
                    titel.setHidden(not sichtbar)
                titel, sichtbar = it, False
                continue
            kz = self.katalog.get(n) or {}
            text = " ".join(str(x or "") for x in (n, kz.get("kategorie"), kz.get("erkennung"))).lower()
            zeigen = not such or such in text
            it.setHidden(not zeigen)
            sichtbar = sichtbar or zeigen
        if titel is not None:
            titel.setHidden(not sichtbar)

    def _liste_geklickt(self, it):
        if self._sync or it.data(Qt.UserRole) is None:
            return
        n = it.data(Qt.UserRole)
        if it.checkState() == Qt.Checked:
            self.hinzufuegen(n)
        else:
            for r in reversed(range(self.tabelle.rowCount())):
                if self.tabelle.cellWidget(r, 0).currentText() == n:
                    self.tabelle.removeRow(r)
            self._liste_abgleichen()
            self._betraege()

    def _liste_abgleichen(self):
        """Häkchen links wie die Zeilen rechts."""
        gewaehlt = set(self.gewaehlt())
        self._sync = True
        for i in range(self.liste.count()):
            it = self.liste.item(i)
            if it.data(Qt.UserRole) is not None:
                it.setCheckState(Qt.Checked if it.data(Qt.UserRole) in gewaehlt else Qt.Unchecked)
        self._sync = False

    def hinzufuegen(self, name):
        """Zusatzarbeit name eintragen (höchstens einmal); erkannte mit Herkunft und RAL-Farbe. Ergebnis: Zeile."""
        if name in self.gewaehlt():
            self._liste_abgleichen()
            return next(r for r in range(self.tabelle.rowCount()) if self.tabelle.cellWidget(r, 0).currentText() == name)
        v = next((x for x in self.vorschlaege if x["name"] == name), None)
        e = dict(name=name)
        if v:
            e.update(text=v.get("text"), quelle=v["herkunft"])
        if name in self.eigene and name not in self.katalog:
            e.update(stand=dict(self.eigene[name]), quelle=EIGEN)
        r = self.zeile_neu(e)
        return r

    # -------------------------------------------------------------- Vorschläge
    def _vorschlaege_zeigen(self):
        offen = [v for v in self.vorschlaege if v["name"] not in set(self.gewaehlt())]
        self.vorschlag_leiste.setVisible(bool(offen))
        self.vorschlag_text.setText("Erkannt bzw. vorgeschlagen (noch nicht gerechnet): " + "; ".join(
            f"<b>{v['name']}</b>" + (f" {v['text']}" if v.get("text") else "") + f" ({v['herkunft']})" for v in offen))

    def vorschlaege_uebernehmen(self):
        for v in self.vorschlaege:
            if v["name"] in self.katalog:
                self.hinzufuegen(v["name"])
        self._vorschlaege_zeigen()

    def neu_anlegen(self):
        """Kurzformular (Plan 3c): neue Zusatzarbeit, gleich als Zeile eingetragen."""
        if self.neu_funktion is None:
            return None
        e = self.neu_funktion()
        if not e:
            return None
        if e["name"] not in self.katalog:
            self.eigene[e["name"]] = e["stand"]
            if e.get("stammdaten"):
                self.katalog[e["name"]] = e["stammdaten"]
        self._liste_fuellen()
        self.zeile_neu({k_: v for k_, v in e.items() if k_ != "stammdaten"})
        return e["name"]

    # -------------------------------------------------------------- Zeilen
    def zeile_neu(self, e=None):
        e = e or {}
        r = self.tabelle.rowCount()
        self.tabelle.insertRow(r)
        cb = QComboBox()
        self._auswahl_fuellen(cb, e.get("name"))
        if e.get("name"):
            cb.setCurrentText(e["name"])
        self.stand[cb] = (e.get("name"), e.get("stand") if isinstance(e.get("stand"), dict) else None)
        self.quelle[cb] = e.get("quelle")        # z. B. aus 'Bohrungen prüfen' (Senken, Flowdrill, Bohren)
        self.tabelle.setCellWidget(r, 0, cb)
        self.tabelle.setCellWidget(r, 1, QLabel())
        menge = QLineEdit(zahl_als_text(e.get("menge"), tausender=False) if e.get("menge") is not None else "")
        preis = QLineEdit(zahl_als_text(e.get("preis"), tausender=False) if e.get("preis") is not None else "")
        self.tabelle.setCellWidget(r, MENGE, menge)
        self.tabelle.setCellWidget(r, PREIS, preis)
        betrag = QLabel()
        betrag.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.tabelle.setCellWidget(r, BETRAG, betrag)
        self.tabelle.setCellWidget(r, TEXT, QLineEdit(e.get("text") or ""))
        if e.get("quelle"):
            cb.setToolTip(f"Herkunft: {e['quelle']}")
        cb.currentTextChanged.connect(lambda _=None, cb=cb: self._gewechselt(cb))
        for w in (menge, preis):
            w.textChanged.connect(lambda _=None: self._betraege())
        self._vorgaben(cb)
        if not self._sync:
            self._liste_abgleichen()
            self._vorschlaege_zeigen()
            self._betraege()
        return r

    def _gewechselt(self, cb):
        self._vorgaben(cb)
        n = cb.currentText()
        doppelt = n and self.gewaehlt().count(n) > 1
        self.fehler.setText(f"{n} steht schon in der Liste – jede Zusatzarbeit nur einmal je Position."
                            if doppelt else "")
        self._liste_abgleichen()
        self._vorschlaege_zeigen()
        self._betraege()

    def _zeile_von(self, widget):
        return next(r for r in range(self.tabelle.rowCount()) if self.tabelle.cellWidget(r, 0) is widget)

    def _auswahl_fuellen(self, cb, name=None):
        """Aktive Zusatzarbeiten: häufig verwendete zuerst, dann nach Kategorie (Überschriften nicht wählbar), dazu die
        nur in diesem Angebot angelegten. Ein inaktiver oder gelöschter Name der Position bleibt am Ende wählbar. Ohne
        Namen ist nichts vorgewählt (früher der erste Eintrag, das gab leicht doppelte Zeilen)."""
        modell = QStandardItemModel(cb)

        def ueberschrift(t):
            it = QStandardItem(f"— {t} —")
            it.setFlags(Qt.NoItemFlags)
            modell.appendRow(it)

        aktive = [z for z in self.katalog.values() if z.get("aktiv") != "nein"]
        oft = sorted((z["name"] for z in aktive if self.haeufig.get(z["name"])),
                     key=lambda n: (-self.haeufig[n], n.lower()))[:5]
        if oft and len(aktive) > 5:
            ueberschrift("Häufig verwendet")
            for n in oft:
                modell.appendRow(QStandardItem(n))
        gruppen = {}
        for z in aktive:
            gruppen.setdefault(z.get("kategorie") or "ohne Kategorie", []).append(z["name"])
        for g in sorted(gruppen, key=lambda g: (g == "ohne Kategorie", g.lower())):
            if len(gruppen) > 1 or oft and len(aktive) > 5:
                ueberschrift(g)
            for n in sorted(gruppen[g], key=str.lower):
                modell.appendRow(QStandardItem(n))
        eigene = [n for n in self.eigene if n not in {z["name"] for z in aktive}]
        if eigene:
            ueberschrift("nur in diesem Angebot")
            for n in eigene:
                modell.appendRow(QStandardItem(n))
        if name and name not in {z["name"] for z in aktive} and name not in eigene:
            ueberschrift("nicht mehr aktiv" if name in self.katalog else "nicht in den Stammdaten")
            modell.appendRow(QStandardItem(name))
        cb.setModel(modell)
        cb.setCurrentIndex(-1)

    def stand_verwerfen(self):
        """Preisstand aller Zeilen verwerfen: beim OK gelten die aktuellen Stammdaten (Zusatzarbeiten nur dieses
        Angebots behalten ihren Stand, sie haben keine Stammdaten)."""
        for cb in list(self.stand):
            if self.stand[cb][0] in self.katalog:
                self.stand[cb] = (self.stand[cb][0], None)
            self._vorgaben(cb)
        self._betraege()

    def eintrag(self, cb):
        """(Stammdaten-ähnliche Zeile mit Preis je Einheit, Preisstand oder None) der gewählten Zusatzarbeit: der
        gespeicherte Preisstand, solange der Name nicht geändert wurde, sonst die Stammdaten bzw. der Stand der
        Zusatzarbeit nur dieses Angebots."""
        name0, stand = self.stand.get(cb, (None, None))
        if stand and cb.currentText() == name0:
            return stand, stand
        kz = self.katalog.get(cb.currentText())
        if kz is None:
            eigen = self.eigene.get(cb.currentText())
            return (dict(eigen), dict(eigen)) if eigen else (None, None)
        return rechnen.zusatz_stand(kz, self.saetze), None

    def _vorgaben(self, cb):
        """Abrechnung und Vorgabewerte (grau) der gewählten Zusatzarbeit anzeigen."""
        r = self._zeile_von(cb)
        kz, stand = self.eintrag(cb)
        art = (kz or {}).get("art")
        self.tabelle.cellWidget(r, 1).setText(art or ("" if not cb.currentText() else "unbekannt"))
        auto = rechnen.zusatz_menge_auto(art, self.p, self.k) if art and self.k is not None else None
        einheit = ZUSATZ_EINHEIT.get(art, "")
        if art == "€/h":             # Sekunden je Teil: Vorgabezeit der Stammdaten, sonst von Hand
            vorgabe = rechnen.zusatz_vorgabe_s(kz)
            self.tabelle.cellWidget(r, MENGE).setPlaceholderText(
                f"Vorgabe: {rechnen.zahl(vorgabe, 1)} s" if vorgabe else "Sekunden je Teil eingeben")
        else:
            self.tabelle.cellWidget(r, MENGE).setPlaceholderText(
                f"auto: {rechnen.zahl(auto, 3)} {einheit}" if auto is not None else f"{einheit} je Teil")
        einheit_preis = {"s/Stück": "s", "€/h": "€/h"}.get(art, "€")
        quelle = "Preisstand " + ".".join(reversed((stand.get("datum") or "").split("-"))) if stand else "Stammdaten"
        self.tabelle.cellWidget(r, PREIS).setPlaceholderText(
            f"{quelle}: {rechnen.zahl((kz or {}).get('preis'))} {einheit_preis}" if kz else "")

    def _zeilen_werte(self):
        """[(Zeile, Eintrag)] mit gültigen Zahlen (für € je Teil; falsche Eingaben zählen leer)."""
        out = []
        for r in range(self.tabelle.rowCount()):
            cb = self.tabelle.cellWidget(r, 0)
            if not cb.currentText():
                continue
            e = dict(name=cb.currentText(), text=None)
            for n, c in (("menge", MENGE), ("preis", PREIS)):
                try:
                    e[n] = _zahl(self.tabelle.cellWidget(r, c).text(), "")
                except ValueError:
                    e[n] = None
            stand = self.eintrag(cb)[0]
            if stand:
                e["stand"] = stand
            out.append((r, e))
        return out

    def _betraege(self):
        """€ je Teil je Zeile (rechnen.zusatz_werte mit den Werten im Fenster) und Summe mit Gewinde."""
        if self.k is None:
            self.summe.setText("")
            return
        zeilen = self._zeilen_werte()
        probe = dict(self.p, zusatz=json.dumps([e for _, e in zeilen], ensure_ascii=False), arbeitsgaenge=json.dumps(
            dict(abgelehnt=[r["zusatzarbeit"] for r in self.tabellen.get("arbeitsgang_regeln") or ()
                            if r.get("zusatzarbeit")])))
        try:
            werte = {z["name"]: z for z in rechnen.zusatz_werte(probe, self.k, self.tabellen, self.kopf)}
        except (TypeError, ValueError, KeyError, ZeroDivisionError):
            werte = {}
        summe = 0.0
        for r in range(self.tabelle.rowCount()):
            lab = self.tabelle.cellWidget(r, BETRAG)
            z = werte.get(self.tabelle.cellWidget(r, 0).currentText())
            if z is None:
                lab.setText("")
            elif z["art"] == "s/Stück":
                lab.setText(f"{rechnen.zahl(z['zeit'], 1)} s")
            elif z["art"] == "€/Angebot":
                lab.setText(f"{rechnen.zahl(z['pauschal'])} €/Ang.")
            else:
                lab.setText(_euro(z["betrag"]))
                summe += z["betrag"]
        try:
            gew = rechnen.gewinde_preis(self.gewinde.text(), self.gewinde_tab, rechnen.gewinde_preise_position(self.p))
        except (TypeError, ValueError):
            gew = 0.0
        summe += gew or 0.0
        stk = self.p.get("stueck") if self.anzahl == 1 else None
        self.summe.setText(f"Summe je Teil {_euro(summe)}" + (
            f" · Position ({stk:g} Stk) {_euro(summe * stk)}" if isinstance(stk, (int, float)) and stk
            else "") + " (ohne Zuschläge und Gewinn)")

    def _entfernen(self):
        for r in sorted({i.row() for i in self.tabelle.selectedIndexes()}, reverse=True):
            self.tabelle.removeRow(r)
        self._liste_abgleichen()
        self._vorschlaege_zeigen()
        self._betraege()

    def gewinde_hinzufuegen(self):
        g = self.gewinde_wahl.currentText()
        if not g:
            return
        alt = self.gewinde.text().strip().rstrip(";,").strip()
        self.gewinde.setText((alt + "; " if alt else "") + f"{self.gewinde_anzahl.value()}x{g}")

    def _gewinde_info(self):
        anz = {g: n for g, n in rechnen.gewinde_anzahl(self.gewinde.text(), self.gewinde_tab).items() if n}
        fehlt = rechnen.gewinde_unbekannt(self.gewinde.text(), self.gewinde_tab)
        if hasattr(self, "summe"):
            self._betraege()
        if fehlt:
            self.gewinde_info.setText(f"<span style='color:#B42318'>Nicht erkannt: {fehlt} – rechnet mit 0 €. "
                                      "Format Anzahl x Gewinde, z. B. 4xM6; 2xM8</span>")
            return
        if not anz:
            self.gewinde_info.setText("Gewinde aus den Stammdaten; Festpreis je Gewinde, sonst Zeit × Stundensatz.")
            return
        preise = {g.get("gewinde"): g.get("preis") for g in self.gewinde_tab}
        teile = [f"{n:g} × {g} à {rechnen.zahl(preise[g])} €" if preise.get(g) is not None else f"{n:g} × {g} (Zeit)"
                 for g, n in anz.items()]
        self.gewinde_info.setText("Je Teil: " + ", ".join(teile)
                                  + f" = {rechnen.zahl(rechnen.gewinde_preis(self.gewinde.text(), self.gewinde_tab))} €")

    # -------------------------------------------------------------- Ergebnis
    def werte(self):
        """(Gewinde-Text oder None, Zusatzarbeiten als JSON-Text oder None). ValueError bei falscher Eingabe oder
        doppelter Zusatzarbeit."""
        gewinde = wert_aus_text(POSITIONEN.feld("gewinde"), self.gewinde.text())
        liste = []
        gesehen = {}
        for r in range(self.tabelle.rowCount()):
            name = self.tabelle.cellWidget(r, 0).currentText().strip()
            if not name:
                continue
            if name in gesehen:
                raise ValueError(f"Zeile {r + 1}: {name} steht schon in Zeile {gesehen[name] + 1} (jede Zusatzarbeit "
                                 "nur einmal je Position).")
            gesehen[name] = r
            e = dict(name=name, menge=_zahl(self.tabelle.cellWidget(r, MENGE).text(), f"Zeile {r + 1}: Menge"),
                     preis=_zahl(self.tabelle.cellWidget(r, PREIS).text(), f"Zeile {r + 1}: Preis bzw. Zeit"),
                     text=self.tabelle.cellWidget(r, TEXT).text().strip() or None)
            cb = self.tabelle.cellWidget(r, 0)
            stand = self.eintrag(cb)[0]
            if stand:
                e["stand"] = stand
            if self.quelle.get(cb) and name == self.stand.get(cb, (None,))[0]:
                e["quelle"] = self.quelle[cb]
            for n in ("menge", "preis"):
                if e[n] is not None and e[n] < 0:
                    raise ValueError(f"Zeile {r + 1}: negative Werte sind nicht zulässig.")
            liste.append(e)
        return gewinde, (json.dumps(liste, ensure_ascii=False) if liste else None)

    def _ok(self):
        try:
            self.ergebnis = self.werte()
        except ValueError as e:
            self.fehler.setText(str(e))
            return
        self.accept()


class ZusatzWahl(QDialog):
    """Auswahl mehrerer Zusatzarbeiten mit Suche und Häkchen (Baugruppen-Editor „Aus Zusatzarbeiten …“; gleiche
    Auswahl wie im Fenster Zusatzarbeiten, Plan 03.11.2026 Schritt 2). katalog: {Name: Zeile}; vorschlaege: erkannte
    Namen (oben gelb). Ergebnis: gewaehlt() nach OK."""

    def __init__(self, parent, katalog, vorschlaege=(), titel="Zusatzarbeiten wählen"):
        super().__init__(parent)
        self.katalog = katalog
        self.setWindowTitle(titel)
        self.resize(380, 520)
        lay = QVBoxLayout(self)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen (Name, Kategorie, Erkennungswort) …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self._filtern)
        self.liste = QListWidget()
        lay.addWidget(self.suche)
        lay.addWidget(self.liste, 1)
        gruppen = []
        vs = [n for n in vorschlaege if n in katalog]
        if vs:
            gruppen.append(("Vorschläge (erkannt)", vs))
        kat = {}
        for n, z in katalog.items():
            kat.setdefault(z.get("kategorie") or "ohne Kategorie", []).append(n)
        for g in sorted(kat, key=lambda g: (g == "ohne Kategorie", g.lower())):
            gruppen.append((g, sorted(kat[g], key=str.lower)))
        for titel_, namen in gruppen:
            it = QListWidgetItem(titel_)
            it.setFlags(Qt.NoItemFlags)
            f = QFont()
            f.setBold(True)
            it.setFont(f)
            self.liste.addItem(it)
            for n in namen:
                it = QListWidgetItem("   " + n)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked)
                it.setData(Qt.UserRole, n)
                if titel_.startswith("Vorschläge"):
                    it.setBackground(QBrush(QColor(GELB_FLAECHE)))
                self.liste.addItem(it)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def _filtern(self):
        such = self.suche.text().strip().lower()
        titel, sichtbar = None, False
        for i in range(self.liste.count()):
            it = self.liste.item(i)
            n = it.data(Qt.UserRole)
            if n is None:
                if titel is not None:
                    titel.setHidden(not sichtbar)
                titel, sichtbar = it, False
                continue
            z = self.katalog.get(n) or {}
            zeigen = not such or such in " ".join(str(x or "") for x in (n, z.get("kategorie"),
                                                                       z.get("erkennung"))).lower()
            it.setHidden(not zeigen)
            sichtbar = sichtbar or zeigen
        if titel is not None:
            titel.setHidden(not sichtbar)

    def anhaken(self, name, an=True):
        for i in range(self.liste.count()):
            it = self.liste.item(i)
            if it.data(Qt.UserRole) == name:
                it.setCheckState(Qt.Checked if an else Qt.Unchecked)
                return True
        return False

    def gewaehlt(self):
        """Angehakte Namen (jeder einmal, in Listenreihenfolge)."""
        out = []
        for i in range(self.liste.count()):
            it = self.liste.item(i)
            n = it.data(Qt.UserRole)
            if n and it.checkState() == Qt.Checked and n not in out:
                out.append(n)
        return out
