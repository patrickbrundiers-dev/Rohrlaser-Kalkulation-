"""Dialog "Materialanfrage (E-Mail)" (Vorschau der Anfrage).

Die Materialanfrage wird nie vom Programm gesendet: 'In Outlook öffnen' zeigt die fertige E-Mail in Outlook, gesendet
wird dort mit einem Klick des Benutzers. Geht das nicht (kein klassisches Outlook), entsteht eine E-Mail-Datei.

Materialanfragen über Outlook (Patrick 13.11.2026, Freigabe alle a): Vorlage wählen (Standardvorlage des Lieferanten
bzw. der Materialgruppe vorbelegt), weitere Lieferanten ankreuzen (je Lieferant eine eigene E-Mail, F2a; passende
nach Materialgruppe oben), Liefertermin, Angebotsgültigkeit, zusätzliche Informationen, interne Bemerkung (nur im
Programm), Anhänge (Materialliste als PDF, Zeichnungen aus dem Ordner des Angebots). Mit db wird jede geöffnete
E-Mail im Verlauf des Angebots vermerkt (Kennung im Betreff, Status Entwurf) und doppelter Versand gemeldet."""
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import materialanfrage as ma
from . import materialanfragen as mv
from .klartext import fehler_text
from .eingabe import RechenSpinGanz


class AnfrageDialog(QDialog):
    """Vorschau der Materialanfrage. zeilen = materialanfrage.bedarf, lieferanten = {Name: E-Mail},
    eml_ziel = Pfad der E-Mail-Datei, oeffnen(pfad) öffnet Dateien, ausfuehren ersetzt den
    Outlook-Aufruf (Tests). Nach einer Aktion: self.meldung (Text für die Statuszeile), self.ergebnis
    ('outlook', 'eml' oder None)."""
    SPALTEN = ("Anfragen", "Material", "Menge", "Zuschnitt", "Schweißnaht", "Lieferant", "Pos.")
    PDF_ANHANG = "Materialliste als PDF"
    KEINE_NAHT = "–"

    def __init__(self, parent, kopf, zeilen, k, einst, lieferanten, eml_ziel, oeffnen, ausfuehren=None,
                 naht_speichern=None, preise=None, db=None, angebot_id=None, wer="", ordner=None, rueckfrage=None,
                 pdf_schreiben=None, blech_erzeugen=None):
        """naht_speichern(profil, werkstoff, seite) speichert eine geänderte Nahtlage der Lieferstange im Angebot.
        preise = {(Profil, Werkstoff): gewählte Lieferantenantwort}: Bestellung statt Anfrage (Automationen
        03.11.2026, 8a) – Vorlage „Materialbestellung“, je Zeile der Preis, Lieferant der gewählten Antwort."""
        super().__init__(parent)
        self.preise = preise
        self.db, self.angebot_id, self.wer, self.ordner = db, angebot_id, wer, ordner
        self.rueckfrage = rueckfrage            # rueckfrage(titel, text) -> True = trotzdem (Tests)
        self.pdf_schreiben = pdf_schreiben      # pdf_schreiben(pfad, lieferant, zeilen_texte, extra) (Angebot)
        self.lief_zeilen = {z["name"]: z for z in (db.zeilen("zukauf_lieferanten") if db else ()) if z.get("name")}
        # Interner Einkauf als Empfänger (Patrick 13.11.2026): verteilt die Anfragen weiter; nicht bei Bestellungen
        self.einkauf = mv.einkauf(einst) if preise is None else None
        lieferanten = dict(lieferanten)
        if self.einkauf:
            self.lief_zeilen[self.einkauf["name"]] = self.einkauf
            lieferanten[self.einkauf["name"]] = self.einkauf["email"]
        # Blechteile: Zeichnung, DXF und STEP anhängen (erzeugt beim Öffnen der E-Mail, F 13.11.2026)
        if blech_erzeugen is None and db is not None:
            def blech_erzeugen(art, ziel, p_):
                return mv.blech_datei(art, ziel, p_, kopf, einst, db, self)
        self.blech_erzeugen, self._blech_cache, self.blech_fehler = blech_erzeugen, {}, []
        self.alle_vorlagen = mv.vorlagen(db.zeilen("mail_vorlagen") if db else (), einst, preise is not None)
        self.angelegt = []                      # Verlauf: in diesem Dialog geöffnete Anfragen
        self.naht_speichern = naht_speichern
        self.kopf, self.zeilen, self.k, self.einst = kopf, zeilen, k, einst
        self.lieferanten, self.eml_ziel = lieferanten, eml_ziel
        self.oeffnen, self.ausfuehren = oeffnen, ausfuehren
        self.meldung, self.ergebnis, self._setzen = "", None, False
        self.text_von_hand = False
        self.setWindowTitle(f"{'Materialbestellung' if preise is not None else 'Materialanfrage'} – Angebot "
                            f"{kopf.get('nummer') or ''}".strip())
        self.resize(900, 680)
        lay = QVBoxLayout(self)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Bestellung bei Lieferant:" if preise is not None else "Anfrage an Lieferant:"))
        self.lieferant = QComboBox()
        if preise:                  # Bestellung: Lieferant der gewählten Antwort vorne
            for z in zeilen:
                e = preise.get((z.get("profil"), z.get("werkstoff")))
                if e and e.get("lieferant"):
                    z["lieferant"] = e["lieferant"]
        namen = list(dict.fromkeys((z["lieferant"] or ma.OHNE_LIEFERANT) for z in zeilen))
        if self.einkauf and self.einkauf["name"] not in namen:
            namen.append(self.einkauf["name"])
        self.lieferant.addItems(namen + [n for n in sorted(lieferanten) if n not in namen])
        self.lieferant.currentTextChanged.connect(self._lieferant_gewaehlt)
        oben.addWidget(self.lieferant, 1)
        oben.addWidget(QLabel("Vorlage:"))
        self.vorlage = QComboBox()
        self.vorlage.addItems([v["name"] for v in self.alle_vorlagen])
        self.vorlage.currentTextChanged.connect(self._vorlage_gewaehlt)
        oben.addWidget(self.vorlage, 1)
        lay.addLayout(oben)

        self.tabelle = QTableWidget(len(zeilen), len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.mengen = []
        for r, z in enumerate(zeilen):
            an = QTableWidgetItem()
            an.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            an.setCheckState(Qt.Checked)
            self.tabelle.setItem(r, 0, an)
            self.tabelle.setItem(r, 1, QTableWidgetItem(z["text"]))
            m = RechenSpinGanz()
            m.setRange(1, 1000000)
            m.setValue(int(-(-(z["stangen"] + (z.get("lager_nachkauf") or 0)) // 1)))   # PROfirst H2: Meldebestand
            if z.get("lager_nachkauf"):
                m.setToolTip(f"{z['stangen']} Stangen für das Angebot + {z['lager_nachkauf']} bis zum Meldebestand "
                             "des Lagers")
            m.valueChanged.connect(self._neu)
            self.mengen.append(m)
            self.tabelle.setCellWidget(r, 2, m)
            zs = QTableWidgetItem()
            if ma.zuschnitt_text(z):        # nur Stangen, die der Lieferant nach der Planung zuschneidet
                zs.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                zs.setCheckState(Qt.Checked)
                zs.setToolTip(ma.zuschnitt_text(z))
            else:
                zs.setFlags(Qt.ItemIsEnabled)
                zs.setText("–")
                zs.setToolTip("Ganze Stangen ohne Zuschnitt")
            self.tabelle.setItem(r, 3, zs)
            self.tabelle.item(r, 1).setToolTip("\n".join(t for t in (z["text"], ma.zuschnitt_text(z),
                                                                     z.get("anforderungen")) if t))
            if z.get("naht_noetig"):        # Rechteckrohr mit Teilen fester Naht: Seite der Naht anfragen
                nb = QComboBox()
                nb.addItems(([] if z.get("naht") else [self.KEINE_NAHT]) + list(ma.naht.NAHT_STANGE))
                nb.setCurrentText(z.get("naht") or self.KEINE_NAHT)
                nb.setToolTip("Seite der Schweißnaht der Lieferstange (gilt im Angebot für dieses Profil und "
                              "diesen Werkstoff)")
                nb.currentTextChanged.connect(lambda t, r=r: self._naht_gewaehlt(r, t))
                self.tabelle.setCellWidget(r, 4, nb)
            else:
                ni = QTableWidgetItem("–")
                ni.setToolTip("Keine Teile mit fester Schweißnaht auf Rechteckrohr")
                self.tabelle.setItem(r, 4, ni)
            self.tabelle.setItem(r, 5, QTableWidgetItem(z["lieferant"] or "–"))
            self.tabelle.setItem(r, 6, QTableWidgetItem(", ".join(z["pos"])))
        kopfzeile = self.tabelle.horizontalHeader()
        for i, b in enumerate((70, 0, 75, 75, 100, 150, 90)):
            if b:
                self.tabelle.setColumnWidth(i, b)
        kopfzeile.setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabelle.itemChanged.connect(self._neu)
        self.tabelle.setMaximumHeight(170)
        lay.addWidget(self.tabelle)

        mitte = QHBoxLayout()
        form = QFormLayout()
        self.an = QLineEdit()
        self.an.setPlaceholderText("E-Mail-Adresse (Lieferanten unter Zukaufartikel → Lieferanten pflegen)")
        self.betreff = QLineEdit(ma.betreff(kopf, einst, bestellung=preise is not None))
        self.betreff.textEdited.connect(lambda _: setattr(self, "betreff_von_hand", True))
        self.betreff_von_hand = False
        self.liefertermin = QLineEdit()
        self.liefertermin.setPlaceholderText("Datum oder KW, z. B. KW 49 (leer = keine Angabe)")
        self.gueltig = QLineEdit()
        self.gueltig.setPlaceholderText("z. B. 31.12.2026 (leer = keine Angabe)")
        self.info = QLineEdit()
        self.info.setPlaceholderText("steht in der E-Mail unter der Materialliste")
        self.intern = QLineEdit()
        self.intern.setPlaceholderText("nur im Programm, nicht in der E-Mail")
        self.artikel_nennen = QCheckBox("Artikelnummern nennen")
        self.artikel_nennen.setChecked(True)
        self.artikel_nennen.setToolTip("Unter jeder Materialzeile: für Artikel … (Artikelnummern der Positionen)")
        for w in (self.liefertermin, self.gueltig, self.info):
            w.textChanged.connect(self._neu)
        self.artikel_nennen.toggled.connect(self._neu)
        form.addRow("An", self.an)
        form.addRow("Betreff", self.betreff)
        if preise is None:
            form.addRow("Liefertermin", self.liefertermin)
            form.addRow("Angebot gültig bis", self.gueltig)
            form.addRow("Zusätzliche Informationen", self.info)
            form.addRow("Interne Bemerkung", self.intern)
        form.addRow("", self.artikel_nennen)
        mitte.addLayout(form, 3)
        rechts = QVBoxLayout()
        self.weitere_titel = QLabel("Auch anfragen bei (je Lieferant eine eigene E-Mail):")
        self.weitere = QListWidget()
        self.weitere.setMaximumHeight(110)
        self.weitere.itemChanged.connect(lambda _: self._neu())
        rechts.addWidget(self.weitere_titel)
        rechts.addWidget(self.weitere)
        rechts.addWidget(QLabel("Anhänge:"))
        self.anhaenge = QListWidget()
        self.anhaenge.setMaximumHeight(110)
        self.anhaenge.itemChanged.connect(
            lambda it: setattr(self, "_pdf_von_hand", True) if it.text() == self.PDF_ANHANG else None)
        rechts.addWidget(self.anhaenge)
        mitte.addLayout(rechts, 2)
        self.weitere_titel.setVisible(preise is None)
        self.weitere.setVisible(preise is None)
        lay.addLayout(mitte)
        self.text = QPlainTextEdit()
        self.text.textChanged.connect(self._text_geaendert)
        lay.addWidget(self.text, 1)
        self.signatur = QLabel(
            "Signatur: setzt Outlook (Standardsignatur); in der E-Mail-Datei die eigene Signatur aus den Einstellungen."
            if ma.outlook_signatur(einst) else "Signatur: eigene Signatur aus den Einstellungen (Materialanfrage).")
        self.signatur.setWordWrap(True)
        self.signatur.setToolTip(ma.signatur(einst) or "keine eigene Signatur (Briefkopf leer)")
        lay.addWidget(self.signatur)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet("color: #7A5A00;")
        lay.addWidget(self.hinweis)
        knoepfe = QHBoxLayout()
        self.outlook_knopf = QPushButton("In Outlook öffnen")
        self.outlook_knopf.setObjectName("primaer")
        self.outlook_knopf.setToolTip("Outlook zeigt die fertige E-Mail; gesendet wird erst mit 'Senden' in Outlook")
        self.outlook_knopf.clicked.connect(lambda: self.in_outlook())
        self.eml_knopf = QPushButton("Als E-Mail-Datei speichern")
        self.eml_knopf.clicked.connect(lambda: self.als_datei())
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.reject)
        knoepfe.addWidget(QLabel("Gesendet wird nur in Outlook, nie vom Programm."))
        knoepfe.addStretch(1)
        for b in (self.outlook_knopf, self.eml_knopf, zu):
            knoepfe.addWidget(b)
        lay.addLayout(knoepfe)
        self._anhaenge_fuellen()
        self._lieferant_gewaehlt(self.lieferant.currentText())

    # ------------------------------------------------------------------ Inhalt
    def _lieferant_gewaehlt(self, name):
        """Zeilen dieses Lieferanten anhaken (ohne Lieferant: die Zeilen ohne), E-Mail-Adresse eintragen."""
        self._setzen = True
        intern = bool(self.einkauf) and name == self.einkauf["name"]
        for r, z in enumerate(self.zeilen):
            passt = intern or (z["lieferant"] or ma.OHNE_LIEFERANT) == name     # Einkauf: alles
            self.tabelle.item(r, 0).setCheckState(Qt.Checked if passt else Qt.Unchecked)
        self.an.setText(self.lieferanten.get(name, ""))
        v = mv.vorlage_waehlen(self.alle_vorlagen, self.lief_zeilen.get(name), self._gruppen())
        if v is not None:
            self.vorlage.blockSignals(True)
            self.vorlage.setCurrentText(v["name"])
            self.vorlage.blockSignals(False)
        self._weitere_fuellen(name)
        self._setzen = False
        self.text_von_hand = False
        self.betreff_von_hand = False
        self._neu()

    def _gruppen(self):
        return list(dict.fromkeys(mv.materialgruppe(self.zeilen[r], self.k) for r in self.gewaehlt()))

    def _vorlage_gewaehlt(self, _):
        self.text_von_hand = False
        self.betreff_von_hand = False
        self._neu()

    def aktuelle_vorlage(self):
        return next((v for v in self.alle_vorlagen if v["name"] == self.vorlage.currentText()),
                    self.alle_vorlagen[0] if self.alle_vorlagen else mv.standard_vorlage(self.einst))

    def _weitere_fuellen(self, haupt):
        """Weitere Lieferanten: passende (Lieferant des Materials, Materialgruppe) oben mit Grund, dann alle übrigen
        mit E-Mail-Adresse; angekreuzt wird nichts von selbst."""
        self.weitere.blockSignals(True)
        self.weitere.clear()
        alle = list(self.lief_zeilen.values()) or [dict(name=n, email=e) for n, e in self.lieferanten.items()]
        gewaehlt = [self.zeilen[r] for r in range(len(self.zeilen))]
        passend = mv.passende_lieferanten(gewaehlt, alle, self.k)
        gesehen = {haupt}
        if self.einkauf:                    # interner Einkauf zuerst (verteilt die Anfragen weiter)
            passend = [(self.einkauf["name"], "verteilt die Anfragen weiter")] + passend
        for name, grund in passend + [(z.get("name"), "") for z in alle]:
            if not name or name in gesehen or name == ma.OHNE_LIEFERANT:
                continue
            gesehen.add(name)
            mail = self.lieferanten.get(name) or (self.lief_zeilen.get(name) or {}).get("email") or ""
            it = QListWidgetItem(name + (f"  – {grund}" if grund else "") + ("" if mail else "  (keine E-Mail)"))
            it.setData(Qt.UserRole, name)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.weitere.addItem(it)
        self.weitere.blockSignals(False)

    def weitere_gewaehlt(self):
        return [self.weitere.item(i).data(Qt.UserRole) for i in range(self.weitere.count())
                if self.weitere.item(i).checkState() == Qt.Checked]

    def _anhaenge_fuellen(self):
        """Materialliste als PDF (nach Vorlage) und Zeichnungen aus dem Ordner des Angebots (PDF der Artikel
        vorbelegt, F6a)."""
        self.anhaenge.clear()
        if self.pdf_schreiben is not None:
            it = QListWidgetItem(self.PDF_ANHANG)
            it.setData(Qt.UserRole, None)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.anhaenge.addItem(it)
        praefix = str(self.kopf.get("nummer") or "\0")
        vorhanden = {}
        for pfad, an in mv.zeichnungen(self.ordner, self.zeilen, praefix) if self.ordner else ():
            it = QListWidgetItem(pfad.name)
            it.setData(Qt.UserRole, str(pfad))
            it.setToolTip(str(pfad))
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if an else Qt.Unchecked)
            self.anhaenge.addItem(it)
            vorhanden[pfad] = it
        self._blech_anhaenge(vorhanden)
        if not self.anhaenge.count():
            self.anhaenge.addItem(QListWidgetItem("– keine Zeichnungen im Ordner des Angebots –"))

    def _blech_anhaenge(self, vorhanden):
        """Blechteile (Patrick 13.11.2026): Zeichnung, Abwicklung (DXF) und STEP je Blechteil anhängen. Liegt eine
        passende Datei im Ordner des Angebots (Name mit Artikelnummer), wird sie angehakt, sonst erzeugt das Programm
        sie beim Öffnen der E-Mail (wie im Blech-Editor). Nur für angehakte Zeilen."""
        for r, z in enumerate(self.zeilen):
            for i, p in enumerate(z.get("blech_pos") or ()):
                da = mv.blech_vorhanden(list(vorhanden), p)
                for art, titel, _ in mv.BLECH_ANHAENGE:
                    if art in da:
                        vorhanden[da[art]].setCheckState(Qt.Checked)
                        vorhanden[da[art]].setData(Qt.UserRole + 1, r)
                        continue
                    if self.blech_erzeugen is None:
                        continue
                    it = QListWidgetItem(f"{mv.blech_name(p)}: {titel} – wird erzeugt")
                    it.setData(Qt.UserRole, f"blech:{r}:{i}:{art}")
                    it.setData(Qt.UserRole + 1, r)
                    it.setToolTip("Erzeugt das Programm beim Öffnen der E-Mail aus den Eingaben des Blech-Editors "
                                  "und legt die Datei im Ordner des Angebots ab")
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                    it.setCheckState(Qt.Checked)
                    self.anhaenge.addItem(it)

    def _blech_datei(self, kennung):
        """Datei eines Blechteils (Kennung blech:Zeile:Nr:Art) erzeugen bzw. aus dem Zwischenspeicher; None bei
        Fehler (Grund in self.blech_fehler)."""
        if kennung in self._blech_cache:
            return self._blech_cache[kennung]
        _, r, i, art = kennung.split(":")
        p = self.zeilen[int(r)]["blech_pos"][int(i)]
        name = mv.blech_name(p)
        endung = {"pdf": " Zeichnung.pdf", "dxf": ".dxf", "step": ".step"}[art]
        ordner = Path(self.ordner) if self.ordner else Path(tempfile.mkdtemp(prefix="materialanfrage_"))
        ziel = ordner / f"{self.kopf.get('nummer') or 'Anfrage'} {name}{endung}"
        try:
            pfad = str(self.blech_erzeugen(art, ziel, p))
        except (ValueError, OSError, RuntimeError) as e:
            self.blech_fehler.append(f"{name} {art.upper()}: {fehler_text(e)}")
            pfad = None
        self._blech_cache[kennung] = pfad
        return pfad

    def _pdf_item(self):
        return next((self.anhaenge.item(i) for i in range(self.anhaenge.count())
                     if self.anhaenge.item(i).text() == self.PDF_ANHANG), None)

    def dateien(self):
        """Angehakte Zeichnungen (Pfade); Dateien der Blechteile nur für angehakte Zeilen, bei Bedarf erzeugt."""
        zeilen, out = set(self.gewaehlt()), []
        for i in range(self.anhaenge.count()):
            it = self.anhaenge.item(i)
            d = it.data(Qt.UserRole)
            if not d or it.checkState() != Qt.Checked:
                continue
            r = it.data(Qt.UserRole + 1)
            if r is not None and r not in zeilen:
                continue
            if str(d).startswith("blech:"):
                d = self._blech_datei(d)
            if d and d not in out:
                out.append(d)
        return out

    def mit_pdf(self):
        it = self._pdf_item()
        return it is not None and it.checkState() == Qt.Checked

    def _naht_gewaehlt(self, r, seite):
        """Nahtlage der Lieferstange geändert: gilt für alle Zeilen mit gleichem Profil und Werkstoff, wird im
        Angebot gespeichert."""
        seite = seite if seite in ma.naht.NAHT_STANGE else None     # '–' = ohne Angabe in der E-Mail
        z0 = self.zeilen[r]
        for i, z in enumerate(self.zeilen):
            if (z["profil"], z["werkstoff"]) == (z0["profil"], z0["werkstoff"]) and z.get("naht_noetig"):
                z["naht"] = seite
                nb = self.tabelle.cellWidget(i, 4)
                if nb is not None and nb.currentText() != (seite or self.KEINE_NAHT):
                    nb.blockSignals(True)
                    nb.setCurrentText(seite or self.KEINE_NAHT)
                    nb.blockSignals(False)
        if self.naht_speichern and seite:
            self.naht_speichern(z0["profil"], z0["werkstoff"], seite)
        self._neu()

    def gewaehlt(self):
        """Indizes der angehakten Zeilen."""
        out = [r for r in range(len(self.zeilen)) if self.tabelle.item(r, 0).checkState() == Qt.Checked]
        nur = getattr(self, "_nur", None)       # beim Erstellen einer Teil-E-Mail (Einkauf Rohr/Blech)
        return out if nur is None else [r for r in out if r in nur]

    def mit_zuschnitt(self):
        """Indizes der Zeilen, deren Zuschnitt angefragt wird."""
        return [r for r in range(len(self.zeilen)) if self.tabelle.item(r, 3).flags() & Qt.ItemIsUserCheckable
                and self.tabelle.item(r, 3).checkState() == Qt.Checked]

    def _neu(self, *_):
        if self._setzen:
            return
        auswahl = self.gewaehlt()
        v = self.aktuelle_vorlage()
        it = self._pdf_item()
        if it is not None and not getattr(self, "_pdf_von_hand", False):
            self.anhaenge.blockSignals(True)
            it.setCheckState(Qt.Checked if (v.get("pdf") or "nein") == "ja" else Qt.Unchecked)
            self.anhaenge.blockSignals(False)
        betreff, text = self.mail_fuer(self.lieferant.currentText(), self._vorschau_kennung())
        if not self.text_von_hand:
            self._setzen = True
            self.text.setPlainText(text)
            self._setzen = False
        if not self.betreff_von_hand:
            self.betreff.setText(betreff)
        hinweise = []
        if not auswahl:
            hinweise.append("Keine Zeile angehakt.")
        if not self.an.text().strip():
            hinweise.append("Ohne E-Mail-Adresse: Empfänger in Outlook eintragen.")
        if self._ist_einkauf(self.lieferant.currentText()) and self.einkauf.get("blech_email"):
            hinweise.append(f"Interner Einkauf: Blechteile gehen an {self.einkauf['blech_email']}, alles andere an "
                            f"{self.einkauf['email']} (je eine E-Mail).")
        nach = [z for z in self.zeilen if z.get("lager_nachkauf")]
        if nach:
            hinweise.append("Menge enthält den Nachkauf bis zum Meldebestand des Lagers: " + ", ".join(
                f"{z['profil']} +{z['lager_nachkauf']}" for z in nach) + ".")
        self.hinweis.setText(" ".join(hinweise))
        self.outlook_knopf.setEnabled(bool(auswahl))
        self.eml_knopf.setEnabled(bool(auswahl))

    def _text_geaendert(self):
        if not self._setzen:
            self.text_von_hand = True

    def _vorschau_kennung(self):
        """Kennung, die die nächste Anfrage bekommt (nur mit Verlauf)."""
        if self.db is None or self.angebot_id is None or self.preise is not None:
            return None
        return mv.naechste_kennung(self.db, self.angebot_id, self.kopf.get("nummer"))

    def mail_fuer(self, name, kennung=None):
        """(Betreff, Text) für einen Lieferanten aus seiner bzw. der gewählten Vorlage."""
        auswahl = self.gewaehlt()
        zs = set(self.mit_zuschnitt())
        lz = self.lief_zeilen.get(name)
        v = self.aktuelle_vorlage()
        if name != self.lieferant.currentText():        # weiterer Lieferant: seine Standardvorlage, sonst die gewählte
            eigene = mv.vorlage_waehlen(self.alle_vorlagen, lz, ()) if lz and lz.get("vorlage") else None
            v = eigene or v
        return mv.mail_bauen(v, self.kopf, [self.zeilen[r] for r in auswahl], self.einst, self.k,
                             {i: self.mengen[r].value() for i, r in enumerate(auswahl)},
                             {i for i, r in enumerate(auswahl) if r in zs}, self.preise, lz, kennung,
                             self.liefertermin.text(), self.gueltig.text(), self.info.text(),
                             self.artikel_nennen.isChecked())

    def signatur_der_vorlage(self):
        return (self.aktuelle_vorlage().get("signatur") or "").strip()

    def mail(self, signatur=False):
        """(An, Betreff, Text); signatur = True: mit der eigenen Signatur (E-Mail-Datei, Outlook ohne Signatur).
        Eine Signatur der Vorlage geht der eigenen vor."""
        text = self.text.toPlainText()
        sig = self.signatur_der_vorlage() or ma.signatur(self.einst)
        return (self.an.text().strip(), self.betreff.text().strip(),
                ma.mit_signatur(text, sig) if signatur or self.signatur_der_vorlage() else text)

    def _ist_einkauf(self, name):
        return bool(self.einkauf) and name == self.einkauf["name"]

    def _mails(self):
        """Alle zu öffnenden E-Mails: [(Lieferant, An, Betreff, Text ohne Signatur, Zeilen oder None)], zuerst der
        oben gewählte Lieferant (Felder wie angezeigt), dann die angekreuzten weiteren (je eigene Kennung, Anrede,
        Vorlage). Der interne Einkauf mit eigener Blech-Adresse bekommt zwei E-Mails (Rohr und Blech getrennt)."""
        haupt = self.lieferant.currentText()
        k0 = self._vorschau_kennung()
        n = int(k0.rsplit("/", 1)[1]) - 1 if k0 else 0
        out = []

        def naechste():
            nonlocal n
            n += 1
            return mv.kennung(self.kopf.get("nummer"), n) if k0 else None

        def einkauf_mails():
            for name, mail, rows in mv.einkauf_aufteilen(self.einkauf, self.zeilen, self.gewaehlt(), self.k):
                self._nur = rows
                try:
                    b, t = self.mail_fuer(self.einkauf["name"], naechste())
                finally:
                    self._nur = None
                out.append((name, mail, b, t, rows))
        if self._ist_einkauf(haupt) and self.einkauf.get("blech_email"):
            einkauf_mails()
        else:
            naechste()
            out.append((haupt, self.an.text().strip(), self.betreff.text().strip(), self.text.toPlainText(), None))
        for name in self.weitere_gewaehlt():
            if self._ist_einkauf(name) and self.einkauf.get("blech_email"):
                einkauf_mails()
                continue
            kenn = naechste()
            b, t = self.mail_fuer(name, kenn)
            if self.betreff_von_hand:
                b = self.betreff.text().strip().replace(k0, kenn) if k0 and kenn else self.betreff.text().strip()
            if self.text_von_hand:         # von Hand geänderter Text gilt für alle, Anrede je Lieferant
                t = self.text.toPlainText()
                a_alt = mv.anrede(self.aktuelle_vorlage(), self.lief_zeilen.get(haupt))
                a_neu = mv.anrede(self.aktuelle_vorlage(), self.lief_zeilen.get(name))
                if a_alt and a_neu and t.startswith(a_alt):
                    t = a_neu + t[len(a_alt):]
            mail = self.lieferanten.get(name) or (self.lief_zeilen.get(name) or {}).get("email") or ""
            out.append((name, mail, b, t, None))
        return out

    def _mit_sig(self, text, eigene):
        sig = self.signatur_der_vorlage() or (ma.signatur(self.einst) if eigene else "")
        return ma.mit_signatur(text, sig) if sig else text

    def _doppelt_ok(self, name):
        """Doppelversand-Schutz: offene Anfrage an diesen Lieferanten mit gleichem Material -> Rückfrage."""
        if self.db is None or self.angebot_id is None or self.preise is not None:
            return True
        e = mv.doppelt(self.db, self.angebot_id, name, [mv.material_schluessel(self.zeilen[r]) for r in self.gewaehlt()])
        if e is None:
            return True
        text = mv.doppelt_text(e) + "\n\nTrotzdem eine neue Anfrage öffnen?"
        if self.rueckfrage is not None:
            return bool(self.rueckfrage("Schon angefragt", text))
        return QMessageBox.question(self, "Schon angefragt", text) == QMessageBox.Yes

    def _pdf(self, name, betreff_, text_):
        """Materialliste als PDF für diesen Lieferanten (neben der E-Mail-Datei), None ohne PDF."""
        if not self.mit_pdf() or self.pdf_schreiben is None or self.eml_ziel is None:
            return None
        ziel = self.eml_ziel.with_name(f"{self.eml_ziel.stem} {self._dateiname(name)}.pdf")
        auswahl = self.gewaehlt()
        zeilen = [dict(self.zeilen[r], menge=self.mengen[r].value()) for r in auswahl]
        try:
            return self.pdf_schreiben(ziel, name, zeilen, dict(betreff=betreff_, liefertermin=self.liefertermin.text(),
                                                               gueltig=self.gueltig.text(), info=self.info.text()))
        except OSError as e:
            self.meldung = f"PDF nicht geschrieben: {fehler_text(e)}"
            return None

    @staticmethod
    def _dateiname(name):
        import re
        return re.sub(r'[\\/:*?"<>|]+', "_", name or "Lieferant").strip()[:60]

    def _vermerken(self, name, an, betreff_, text_, anhaenge, weg):
        if self.db is None or self.angebot_id is None or self.preise is not None or getattr(self.db, "nur_lesen", False):
            return None
        auswahl = self.gewaehlt()
        kenn = next((m.group(0) for m in mv.KENNUNG.finditer(betreff_ or "")), None) or \
            mv.naechste_kennung(self.db, self.angebot_id, self.kopf.get("nummer"))
        e = mv.anlegen(self.db, self.angebot_id, dict(
            kennung=kenn, lieferant=None if name == ma.OHNE_LIEFERANT else name, an=an,
            vorlage=self.vorlage.currentText(), betreff=betreff_, text=text_,
            zeilen=[ma.zeile_text(self.zeilen[r], self.k, self.mengen[r].value())
                    if self.zeilen[r].get("art") != "zukauf" else mv.zukauf_text(self.zeilen[r], self.mengen[r].value())
                    for r in auswahl],
            schluessel=[mv.material_schluessel(self.zeilen[r]) for r in auswahl],
            anhaenge=[str(a).replace("\\", "/").rsplit("/", 1)[-1] for a in anhaenge],
            liefertermin=self.liefertermin.text().strip(), gueltig=self.gueltig.text().strip(),
            info=self.info.text().strip(), intern=self.intern.text().strip(), weg=weg,
            weg_text="in Outlook geöffnet" if weg == "outlook" else "als E-Mail-Datei gespeichert"), self.wer)
        self.angelegt.append(e)
        return e

    # ------------------------------------------------------------------ Aktionen
    def als_datei(self, oeffnen=True):
        """Siehe _als_datei; nicht erzeugte Blech-Dateien stehen in der Meldung."""
        return self._blech_hinweis(self._als_datei(oeffnen))

    def _als_datei(self, oeffnen=True):
        """E-Mail-Datei(en) (.eml) in der Ablage speichern und mit dem Standard-Mailprogramm öffnen; bei mehreren
        Lieferanten je Lieferant eine Datei. Ergebnis: Pfad der ersten Datei."""
        if self.eml_ziel is None:
            return None
        erster = None
        mails = self._mails()
        for i, (name, an, b, t, nur) in enumerate(mails):
            self._nur = nur
            try:
                if not self._doppelt_ok(name):
                    continue
                ziel = self.eml_ziel if len(mails) == 1 and i == 0 else \
                    self.eml_ziel.with_name(f"{self.eml_ziel.stem} {self._dateiname(name)}{self.eml_ziel.suffix}")
                pdf = self._pdf(name, b, t)
                anh = self.dateien() + ([pdf] if pdf else [])
                text = self._mit_sig(t, True)
                pfad = ma.eml(ziel, an, b, text, anh)
                self._vermerken(name, an, b, text, anh, "eml")
            finally:
                self._nur = None
            if oeffnen:
                self.oeffnen(pfad)
            erster = erster or pfad
        if erster is None:
            self.meldung = "Nichts geöffnet (schon angefragt)."
            return None
        self.ergebnis = "eml"
        n = len(self.angelegt) or 1
        self.meldung = (f"E-Mail-Datei gespeichert: {erster} – im Mailprogramm prüfen und senden." if n == 1 else
                        f"{n} E-Mail-Dateien gespeichert – im Mailprogramm prüfen und senden.")
        return erster

    def _blech_hinweis(self, erg):
        """Nicht erzeugte Dateien der Blechteile an die Meldung hängen (einmal)."""
        if self.blech_fehler and "Nicht angehängt" not in self.meldung:
            self.meldung += " Nicht angehängt: " + "; ".join(self.blech_fehler) + "."
        return erg

    def in_outlook(self):
        """E-Mail(s) in Outlook anzeigen (nicht senden); geht das nicht, E-Mail-Datei als Ersatz."""
        return self._blech_hinweis(self._in_outlook())

    def _in_outlook(self):
        aus_outlook = ma.outlook_signatur(self.einst) and not self.signatur_der_vorlage()
        weg = mv.VERSANDWEGE["outlook"]
        geoeffnet, fehler = 0, ""
        for name, an, b, t, nur in self._mails():
            self._nur = nur
            try:
                if not self._doppelt_ok(name):
                    continue
                pdf = self._pdf(name, b, t)
                anh = self.dateien() + ([pdf] if pdf else [])
                text = self._mit_sig(t, not aus_outlook)
                ok, fehler = weg(an, b, text, anh, ausfuehren=self.ausfuehren, signatur_=aus_outlook)
                if not ok:
                    break
                self._vermerken(name, an, b, text, anh, "outlook")
            finally:
                self._nur = None
            geoeffnet += 1
        if fehler == "" and geoeffnet:
            self.ergebnis = "outlook"
            self.meldung = ("E-Mail in Outlook geöffnet – bitte dort prüfen und senden." if geoeffnet == 1 else
                            f"{geoeffnet} E-Mails in Outlook geöffnet – bitte dort prüfen und senden.")
            self.accept()
            return True
        if fehler == "" and not geoeffnet:
            self.meldung = "Nichts geöffnet (schon angefragt)."
            return False
        if geoeffnet:           # ein Teil ging: Rest nicht doppelt als Datei
            self.meldung = (f"{geoeffnet} E-Mail(s) in Outlook geöffnet, dann Fehler ({fehler_text(fehler)}). Bitte "
                            "die übrigen Lieferanten erneut anfragen.")
            self.ergebnis = "outlook"
            self.accept()
            return False
        pfad = self.als_datei()
        self.meldung = (f"Outlook ließ sich nicht ansteuern ({fehler_text(fehler)}). Ersatz: E-Mail-Datei {pfad} "
                        "im Standard-Mailprogramm geöffnet.")
        self.accept()
        return False
