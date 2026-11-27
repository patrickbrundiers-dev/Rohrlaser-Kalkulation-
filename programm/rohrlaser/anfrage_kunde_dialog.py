"""Fenster „Kunde aus der Anfrage“ (Patrick 23.11.2026, MSG-Auftrag): links die erkannten Kunden mit Punkten und
Gründen (Suche nach anderen, „Neuen Kunden anlegen …“), rechts die Gegenüberstellung Feld | Datenbank | Neue E-Mail
mit Farben (gleich, neu, abweichend) und je Zeile einem Haken „übernehmen“. Unten: Ansprechpartner wählen bzw. neu,
dann „Zuordnen und übernehmen“ oder „Nur zuordnen“. Gespeichert wird nur Angehaktes (anfrage_kunde.uebernehmen).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import anfrage_kunde as ak
from . import kunden_daten as kd
from . import stil

FARBE = {ak.GLEICH: (stil.GRUEN_FLAECHE, "gleich"), ak.NEU: (stil.BLAU_FLAECHE, "neu"),
         ak.ANDERS: (stil.GELB_FLAECHE, "abweichend"), ak.NUR_DB: ("#FFFFFF", "nur in der Datenbank")}
STUFE_TEXT = {ak.EINDEUTIG: "eindeutig", ak.WAHRSCHEINLICH: "wahrscheinlich – bitte prüfen",
              ak.UNSICHER: "unsicher – bitte prüfen"}
NEUE_PERSON = "__neu__"


class KundeAusMailDialog(QDialog):
    """Ergebnis nach accept(): self.ergebnis = dict(kundennr, kunde=[geänderte Felder], person=id, neu_person,
    angelegt=bool). stumm (Tests): keine Rückfragen."""

    def __init__(self, eltern, db, daten, kunden_bereich=None, vorschlag=None, stumm=False, adresse=""):
        super().__init__(eltern)
        self.db, self.daten, self.kb, self.stumm = db, dict(daten or {}), kunden_bereich, stumm
        self.ergebnis = None
        self.kundennr = None
        self.zeilen = []
        self.setWindowTitle("Kunde aus der Anfrage")
        lay = QVBoxLayout(self)
        p = self.daten.get("person") or {}
        kopf = " · ".join(x for x in (self.daten.get("name"), kd.name_voll(p) if p else "", self.daten.get("email"),
                                      kd.plz_ort(self.daten.get("plz"), self.daten.get("ort"))) if x)
        info = QLabel(f"<b>Aus der E-Mail erkannt:</b> {kopf or '–'}")
        info.setWordWrap(True)
        lay.addWidget(info)
        teiler = QSplitter(Qt.Horizontal)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Passende Kunden (Punkte und Gründe):"))
        self.liste = QListWidget()
        self.liste.currentItemChanged.connect(lambda it, _alt: self.kunde_waehlen(it.data(Qt.UserRole) if it else None))
        ll.addWidget(self.liste, 1)
        self.grund = QLabel()
        self.grund.setWordWrap(True)
        self.grund.setStyleSheet(f"color: {stil.TEXT_GRAU};")
        ll.addWidget(self.grund)
        z = QHBoxLayout()
        self.suchen_knopf = QPushButton("Anderen Kunden suchen …")
        self.suchen_knopf.setToolTip("Kunden im Kundenstamm suchen und vergleichen")
        self.suchen_knopf.clicked.connect(lambda: self.suchen())
        self.neu_knopf = QPushButton("Neuen Kunden anlegen …")
        self.neu_knopf.setToolTip("Eingabemaske mit den Daten aus der Mail (Dublettenprüfung, Kundennummer automatisch)")
        self.neu_knopf.clicked.connect(lambda: self.neu_anlegen())
        z.addWidget(self.suchen_knopf)
        z.addWidget(self.neu_knopf)
        ll.addLayout(z)
        teiler.addWidget(links)
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        self.titel = QLabel("Bitte links einen Kunden wählen.")
        rl.addWidget(self.titel)
        pz = QHBoxLayout()
        pz.addWidget(QLabel("Ansprechpartner:"))
        self.person = QComboBox()
        self.person.setToolTip("Mit welchem Ansprechpartner vergleichen (oder die Person aus der Mail neu anlegen)")
        self.person.currentIndexChanged.connect(lambda _: self._vergleichen())
        pz.addWidget(self.person, 1)
        rl.addLayout(pz)
        self.tabelle = QTableWidget(0, 5)
        self.tabelle.setHorizontalHeaderLabels(["Übernehmen", "Feld", "Datenbank", "Neue E-Mail", "Stand"])
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        kopf_t = self.tabelle.horizontalHeader()
        kopf_t.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf_t.setSectionResizeMode(2, QHeaderView.Stretch)
        kopf_t.setSectionResizeMode(3, QHeaderView.Stretch)
        rl.addWidget(self.tabelle, 1)
        legende = QLabel(" · ".join(f"<span style='background:{stil.umsetzen(f)}'>&nbsp;{t}&nbsp;</span>"
                                    for f, t in FARBE.values()) +
                         " — abweichende Werte sind nie vorab angehakt; nichts wird ohne Haken geändert.")
        legende.setTextFormat(Qt.RichText)
        legende.setWordWrap(True)
        rl.addWidget(legende)
        teiler.addWidget(rechts)
        teiler.setSizes([320, 680])
        lay.addWidget(teiler, 1)
        # wie bisher im Fenster „Kunde zuordnen“: Lernregel Adresse bzw. Domain → Kunde, Grund fürs Protokoll
        regeln = QHBoxLayout()
        self.regel = QCheckBox(f"Als Regel merken: {adresse} gehört immer zu diesem Kunden" if adresse
                               else "Als Regel merken")
        self.regel.setEnabled(bool(adresse))
        self.regel.setToolTip("Gilt für neue Mails; die Regel steht im Fenster „Outlook …“ und lässt sich löschen")
        dom = adresse.rpartition("@")[2] if "@" in (adresse or "") else ""
        self.domain = QCheckBox(f"… auch für alle Adressen @{dom}")
        from . import mail
        if not (bool(dom) and dom not in mail.FREEMAIL):  # nur ausblenden (geister.py)
            self.domain.hide()
        self.grund_text = QLineEdit()
        self.grund_text.setPlaceholderText("Grund (für das Protokoll, freiwillig)")
        regeln.addWidget(self.regel)
        regeln.addWidget(self.domain)
        regeln.addWidget(self.grund_text, 1)
        lay.addLayout(regeln)
        unten = QHBoxLayout()
        unten.addStretch(1)
        self.nur_knopf = QPushButton("Nur zuordnen")
        self.nur_knopf.setToolTip("Anfrage dem gewählten Kunden zuordnen, Kundendaten nicht ändern")
        self.nur_knopf.clicked.connect(lambda: self.speichern(nur_zuordnen=True))
        self.ok_knopf = QPushButton("Zuordnen und übernehmen")
        self.ok_knopf.setToolTip("Anfrage zuordnen und die angehakten Werte in den Kunden bzw. Ansprechpartner "
                                 "schreiben (mit Historie)")
        self.ok_knopf.setDefault(True)
        self.ok_knopf.clicked.connect(lambda: self.speichern())
        ab = QPushButton("Abbrechen")
        ab.clicked.connect(self.reject)
        for k in (self.nur_knopf, self.ok_knopf, ab):
            unten.addWidget(k)
        lay.addLayout(unten)
        self.kandidaten = ak.erkennen(db, self.daten)
        self._liste_fuellen(vorschlag)
        self.resize(1050, 560)

    # ---------------------------------------------------------- Kandidaten
    def _liste_fuellen(self, vorschlag=None, extra=None):
        self.liste.blockSignals(True)
        self.liste.clear()
        nummern = [x["kundennr"] for x in self.kandidaten]
        for x in self.kandidaten:
            it = QListWidgetItem(f"{x['kundennr']} {x['name']}\n{STUFE_TEXT[x['stufe']]} · {x['punkte']} Punkte")
            it.setData(Qt.UserRole, x["kundennr"])
            it.setToolTip("\n".join(x["gruende"]))
            self.liste.addItem(it)
        for nr in [n for n in (vorschlag, extra) if n and n not in nummern]:
            k = kd.kunde(self.db, nr) or {}
            it = QListWidgetItem(f"{nr} {k.get('name') or ''}\nvon Hand gewählt")
            it.setData(Qt.UserRole, nr)
            self.liste.addItem(it)
        self.liste.blockSignals(False)
        ziel = extra or vorschlag or (self.kandidaten[0]["kundennr"] if self.kandidaten else None)
        for i in range(self.liste.count()):
            if self.liste.item(i).data(Qt.UserRole) == ziel:
                self.liste.setCurrentRow(i)
                return
        self.kunde_waehlen(None)

    def kunde_waehlen(self, kundennr):
        """Kunden links wählen: Gegenüberstellung mit diesem Kunden (Ansprechpartner: passender vorgeschlagen)."""
        self.kundennr = str(kundennr) if kundennr else None
        k = kd.kunde(self.db, self.kundennr) if self.kundennr else None
        self.nur_knopf.setEnabled(k is not None)
        self.ok_knopf.setEnabled(k is not None)
        x = next((c for c in self.kandidaten if c["kundennr"] == self.kundennr), None)
        self.grund.setText("\n".join(x["gruende"]) if x else "")
        self.person.blockSignals(True)
        self.person.clear()
        if k is None:
            self.titel.setText("Kein Kunde gewählt: links wählen, suchen oder neu anlegen.")
            self.tabelle.setRowCount(0)
            self.person.blockSignals(False)
            return
        hinweis = "  (gesperrt)" if k.get("status") == kd.GESPERRT else ("  (archiviert)" if k.get("archiviert") == "ja"
                                                                         else "")
        self.titel.setText(f"<b>{k['kundennr']} {k.get('name') or ''}</b>{hinweis}")
        p = self.daten.get("person") or {}
        passt = ak.person_finden(self.db, self.kundennr, p)
        self.person.addItem("– Ansprechpartner nicht ändern –", None)
        if p:
            self.person.addItem(f"Neu: {kd.name_voll(p)} (aus der Mail)", NEUE_PERSON)
        for q in kd.ansprechpartner(self.db, self.kundennr):
            self.person.addItem(kd.name_voll(q) + (" (Haupt)" if q.get("haupt") == "ja" else ""), q["id"])
        i = self.person.findData(passt) if passt else (self.person.findData(NEUE_PERSON) if p else 0)
        self.person.setCurrentIndex(max(i, 0))
        self.person.blockSignals(False)
        self._vergleichen()

    def _vergleichen(self):
        if not self.kundennr:
            return
        wahl = self.person.currentData()
        daten = self.daten if wahl is not None else dict(self.daten, person=None)
        self.zeilen = ak.vergleich(self.db, self.kundennr, daten, None if wahl in (None, NEUE_PERSON) else wahl)
        self.tabelle.setRowCount(len(self.zeilen))
        for r, z in enumerate(self.zeilen):
            farbe, stand = FARBE[z["status"]]
            haken = QTableWidgetItem()
            if z["mail"] and z["status"] != ak.GLEICH:
                haken.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                haken.setCheckState(Qt.Checked if z["vorschlag"] else Qt.Unchecked)
            else:
                haken.setFlags(Qt.ItemIsEnabled)
            titel = ("Ansprechpartner: " if z["bereich"] == "person" else "") + z["titel"]
            werte = [haken, QTableWidgetItem(titel), QTableWidgetItem(z["db"]), QTableWidgetItem(z["mail"]),
                     QTableWidgetItem(stand)]
            for c, it in enumerate(werte):
                if c:
                    it.setBackground(stil.farbe(farbe))
                self.tabelle.setItem(r, c, it)

    def auswahl(self):
        """Angehakte Zeilen als {(bereich, feld)}."""
        out = set()
        for r, z in enumerate(self.zeilen):
            it = self.tabelle.item(r, 0)
            if it is not None and it.flags() & Qt.ItemIsUserCheckable and it.checkState() == Qt.Checked:
                out.add((z["bereich"], z["feld"]))
        return out

    def haken(self, bereich, feld, an=True):
        """Haken einer Zeile setzen (Tests, Tastatur)."""
        for r, z in enumerate(self.zeilen):
            if (z["bereich"], z["feld"]) == (bereich, feld):
                it = self.tabelle.item(r, 0)
                if it.flags() & Qt.ItemIsUserCheckable:
                    it.setCheckState(Qt.Checked if an else Qt.Unchecked)
                    return True
        return False

    # ---------------------------------------------------------- Aktionen
    def suchen(self, kundennr=None):
        """Anderen Kunden suchen (Kundensuche); gewählter Kunde kommt in die Liste und wird verglichen."""
        if kundennr is None:
            if self.stumm:
                return None
            from .kunden_seite import KundenSuche
            d = KundenSuche(self, self.db, self.daten.get("name") or "", titel="Kunde für die Anfrage suchen")
            if d.exec() != QDialog.Accepted or not d.kundennr:
                return None
            kundennr = d.kundennr
        self._liste_fuellen(extra=str(kundennr))
        return kundennr

    def neu_anlegen(self, werte=None, dubletten_ok=None):
        """Neuen Kunden mit den Daten der Mail anlegen (Eingabemaske der Kundenverwaltung mit Dublettenprüfung) und
        gleich zuordnen. Ergebnis: Kundennummer oder None."""
        vorschlag = ak.vorschlag_neu(self.daten)
        if self.kb is not None:
            nr = self.kb.neuer_kunde(vorschlag=vorschlag, stumm=self.stumm, werte=werte, dubletten_ok=dubletten_ok,
                                     oeffnen=False)
        else:
            try:
                nr = ak.neu_anlegen(self.db, dict(self.daten, **(werte or {})), dubletten_ok=bool(dubletten_ok),
                                    kundennr=(werte or {}).get("kundennr"))
            except kd.KundenFehler as e:
                if not self.stumm:
                    QMessageBox.warning(self, "Neuer Kunde", str(e))
                return None
        if not nr:
            return None
        self.ergebnis = dict(kundennr=nr, kunde=[], person=None, neu_person=False, angelegt=True)
        self.accept()
        return nr

    def speichern(self, nur_zuordnen=False):
        """Zuordnen und (ohne nur_zuordnen) die angehakten Werte übernehmen. Fehler (Konflikt mit Kollegen,
        Lesemodus, Eingabe) werden gezeigt, das Fenster bleibt offen. Ergebnis: self.ergebnis oder None."""
        if not self.kundennr:
            return None
        k = kd.kunde(self.db, self.kundennr) or {}
        if k.get("status") == kd.GESPERRT and not self.stumm:
            if QMessageBox.question(self, "Kunde gesperrt", f"{self.kundennr} ist gesperrt. Trotzdem zuordnen?") \
                    != QMessageBox.Yes:
                return None
        erg = dict(kundennr=self.kundennr, kunde=[], person=None, neu_person=False, angelegt=False)
        wahl = self.person.currentData()
        if not nur_zuordnen and self.auswahl():
            try:
                erg.update(ak.uebernehmen(self.db, self.kundennr, self.zeilen, self.auswahl(),
                                          None if wahl in (None, NEUE_PERSON) else wahl, self.daten))
            except Exception as e:              # noqa: BLE001 – zeigen, nichts halb speichern
                from .kunden_seite import fehler_zeigen
                self.fehler = fehler_zeigen(self, "Kunde übernehmen", e, self.stumm)
                return None
        elif wahl not in (None, NEUE_PERSON):
            erg["person"] = wahl
        self.ergebnis = erg
        self.accept()
        return erg
