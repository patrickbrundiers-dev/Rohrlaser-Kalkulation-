"""Fenster „Online-Preise“ (Entwicklungsauftrag Patrick 18.11.2026): Preisvergleich der Lieferanten, Preisverlauf,
Lieferantenverwaltung und Protokoll; dazu der automatische Abruf für das Hauptfenster (auto_abruf).

Preisvergleich: Abmessung eintippen („RE 80x40x3“) oder Profilart, Maße, Güte, Länge, Oberfläche, Hersteller,
Artikelnummer wählen; die Tabelle zeigt je Lieferant die aktuellen Preisstände auf €/m, €/kg und €/Stange umgerechnet,
mit Einstand für die Menge (Fracht, Mindermenge, Verpackung, Bearbeitung), Quelle und Abrufzeit. Der günstigste
übernehmbare Preis ist grün, veraltete Stände orange, unsichere Zuordnungen grau. „Übernehmen“ schreibt den Preis in
die Stammdaten Preise (mit Sicherung vorher); bestehende Angebote und Aufträge ändern sich nicht."""
import datetime
import threading
import webbrowser

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QFont, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from . import onlinepreise as op
from . import onlinepreise_abruf as ab
from . import onlinepreise_adapter as ad
from . import stil, zugang
from .stammdaten import zahl_als_text

GRUEN, ORANGE, GRAU = stil.farbe_fest(stil.GRUEN_FLAECHE), stil.farbe_fest("#B35C00"), stil.farbe_fest("#7A8594")
FORMEN = ("", "Rundrohr", "Quadratrohr", "Rechteckrohr", "Flachstahl", "L-Profil", "U-Profil")
SPALTEN = ("Lieferant", "Artikelnr.", "Bezeichnung", "Güte", "Abmessung", "Länge [mm]", "€/m", "€/kg", "€/Stange",
           "Einstand €/m", "Mindestmenge", "VE", "Verfügbarkeit", "Lieferzeit [Tage]", "Gültig bis", "Abruf", "Quelle",
           "Zuordnung", "Preis")
LIEF_SPALTEN = (("name", "Lieferant"), ("aktiv", "Aktiv"), ("weg", "Weg"), ("aktualisierung", "Aktualisierung"),
                ("nur_verwendete", "Nur verwendete"), ("shop_adresse", "Shop-Adresse"),
                ("such_adresse", "Suchadresse ({suche})"), ("oci_adresse", "OCI-Einstiegsadresse"),
                ("oci_hintergrund", "OCI-Hintergrundsuche"), ("preisliste_ordner", "Preislisten-Ordner"),
                ("preisart", "Preise sind"), ("brutto", "Brutto"), ("mwst", "MwSt %"),
                ("rabatt", "Rabatt % (Listenpreis)"), ("fracht", "Fracht €"), ("frei_ab", "Frachtfrei ab €"),
                ("mindermenge_bis", "Mindermenge bis €"), ("mindermenge_zuschlag", "Mindermengenzuschlag €"),
                ("verpackung", "Verpackung €"), ("bearbeitung", "Bearbeitung €"), ("min_abstand_h", "Mindestabstand h"),
                ("kundennr", "Unsere Kundennr."), ("spalten", "Spaltenzuordnung (JSON)"), ("bemerkung", "Bemerkung"))
AUSWAHL = {"aktiv": ("ja", "nein"), "weg": op.WEGE, "aktualisierung": op.INTERVALLE, "nur_verwendete": ("nein", "ja"),
           "oci_hintergrund": ("nein", "ja"), "preisart": op.PREISARTEN, "brutto": ("nein", "ja")}
ZAHLEN = {"mwst", "rabatt", "fracht", "frei_ab", "mindermenge_bis", "mindermenge_zuschlag", "verpackung", "bearbeitung",
          "min_abstand_h"}


def _z(w, stellen=2):
    return "" if w is None else zahl_als_text(w, stellen)


def _zeit(t):
    return str(t or "")[:16].replace("T", " ")


def _item(text, tipp=None):
    it = QTableWidgetItem(str(text if text is not None else ""))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if tipp:
        it.setToolTip(tipp)
    return it


def abmessung_text(z):
    if z.get("profil_id"):
        return z["profil_id"]
    f, a, b, w = z.get("form"), z.get("a"), z.get("b"), z.get("wand")
    if not a:
        return ""
    return " ".join(x for x in (f or "", "x".join(_z(v, 1) for v in (a, b, w) if v)) if x)


class OnlinePreiseDialog(QDialog):
    """vorwahl: dict(profil_id, werkstoff_id, menge_m, stangenlaenge) aus dem Angebot bzw. den Stammdaten."""

    def __init__(self, db, parent=None, vorwahl=None, reiter=0):
        super().__init__(parent)
        self.db, self.k = db, db.kontext()
        self.vorwahl = dict(vorwahl or {})
        self.zeilen, self.gesichert, self.uebernommen = [], False, []
        self.zeigen = lambda f: f.exec()          # Tests ersetzen das Öffnen weiterer Fenster
        self.browser = webbrowser.open            # Tests ersetzen den Browser
        self.empfang = None
        if not db.nur_lesen:
            op.vorbelegen(db)
        self.setWindowTitle("Online-Preise der Lieferanten")
        self.resize(1500, 760)
        lay = QVBoxLayout(self)
        self.reiter = QTabWidget()
        lay.addWidget(self.reiter, 1)
        self.reiter.addTab(self._vergleich_seite(), "Preisvergleich")
        self.reiter.addTab(self._verlauf_seite(), "Preisverlauf")
        self.reiter.addTab(self._lieferanten_seite(), "Lieferanten")
        self.reiter.addTab(self._protokoll_seite(), "Protokoll")
        self.reiter.currentChanged.connect(self._reiter_gewechselt)
        unten = QDialogButtonBox(QDialogButtonBox.Close)
        unten.rejected.connect(self.reject)
        lay.addWidget(unten)
        self._vorwahl_setzen()
        self.suchen()
        self.reiter.setCurrentIndex(reiter)

    # ------------------------------------------------------------------ Preisvergleich
    def _vergleich_seite(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        hinweis = QLabel("Jeder Preis mit Quelle und Abrufzeit. Kein Preis wird geschätzt; leer = nicht vorhanden bzw. "
                         "nicht umrechenbar. Übernehmen geht nur bei genau passender Abmessung und Güte (Zuordnung "
                         "„sicher“ oder „bestätigt“). Bestehende Angebote und Aufträge ändern sich nicht.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {GRAU.name()};")
        lay.addWidget(hinweis)
        g = QGridLayout()
        self.e_abmessung = QLineEdit()
        self.e_abmessung.setPlaceholderText("z. B. RE 80x40x3 oder Rundrohr 42,4x2")
        self.e_abmessung.editingFinished.connect(self._abmessung_zerlegen)
        self.e_form = QComboBox()
        self.e_form.addItems(FORMEN)
        self.e_a, self.e_b, self.e_wand, self.e_laenge = (QLineEdit() for _ in range(4))
        self.e_werkstoff = QComboBox()
        self.e_werkstoff.addItem("", None)
        for wid, ws in sorted(self.k.werkstoffe.items()):
            self.e_werkstoff.addItem(f"{wid} ({ws.get('werkstoff') or ''})", wid)
        self.e_oberflaeche, self.e_hersteller, self.e_artikel, self.e_menge = (QLineEdit() for _ in range(4))
        self.e_menge.setPlaceholderText("für Einstand")
        for i, (titel, feld) in enumerate((("Abmessung", self.e_abmessung), ("Profilart", self.e_form),
                                           ("A / Ø [mm]", self.e_a), ("B [mm]", self.e_b), ("Wand [mm]", self.e_wand),
                                           ("Länge [mm]", self.e_laenge))):
            g.addWidget(QLabel(titel), 0, 2 * i)
            g.addWidget(feld, 0, 2 * i + 1)
        for i, (titel, feld) in enumerate((("Güte", self.e_werkstoff), ("Oberfläche", self.e_oberflaeche),
                                           ("Hersteller", self.e_hersteller), ("Artikelnr.", self.e_artikel),
                                           ("Menge [m]", self.e_menge))):
            g.addWidget(QLabel(titel), 1, 2 * i)
            g.addWidget(feld, 1, 2 * i + 1)
        such = QPushButton("Suchen")
        such.setDefault(True)
        such.clicked.connect(self.suchen)
        g.addWidget(such, 1, 11)
        lay.addLayout(g)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tabelle.setColumnWidth(2, 260)
        self.tabelle.doubleClicked.connect(lambda _: self.details())
        lay.addWidget(self.tabelle, 1)
        self.leer = QLabel()
        self.leer.setWordWrap(True)
        lay.addWidget(self.leer)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.info)
        knoepfe = QHBoxLayout()
        self.k_uebernehmen = QPushButton("Übernehmen")
        self.k_uebernehmen.setToolTip("Markierten (sonst den günstigsten) Preis in die Stammdaten Preise übernehmen; "
                                      "vorher Datensicherung. Gilt für neue Kalkulationen.")
        self.k_uebernehmen.clicked.connect(lambda: self.uebernehmen())
        self.einstand = QCheckBox("Einstand übernehmen (mit Fracht und Zuschlägen für die Menge)")
        self.k_zuordnung = QPushButton("Zuordnung bestätigen …")
        self.k_zuordnung.clicked.connect(lambda: self.zuordnung())
        self.k_shop = QPushButton("Im Shop suchen")
        self.k_shop.setMenu(QMenu(self.k_shop))
        self.k_oci = QPushButton("Im Shop auswählen (OCI)")
        self.k_oci.setMenu(QMenu(self.k_oci))
        self.k_erfassen = QPushButton("Preis erfassen …")
        self.k_erfassen.setToolTip("Preis aus Shop, Telefon oder Angebot von Hand eintragen (Quelle und Datum werden "
                                   "gemerkt)")
        self.k_erfassen.clicked.connect(lambda: self.erfassen())
        self.k_abrufen = QPushButton("Jetzt abrufen")
        self.k_abrufen.setToolTip("Preislisten und OCI-Hintergrundsuche aller aktiven Lieferanten für diese Suche")
        self.k_abrufen.clicked.connect(lambda: self.alle_abrufen())
        self.k_details = QPushButton("Details …")
        self.k_details.clicked.connect(lambda: self.details())
        for k in (self.k_uebernehmen, self.einstand, self.k_zuordnung, self.k_shop, self.k_oci, self.k_erfassen,
                  self.k_abrufen, self.k_details):
            knoepfe.addWidget(k)
        knoepfe.addStretch(1)
        lay.addLayout(knoepfe)
        self._menues_fuellen()
        for k in (self.k_uebernehmen, self.k_zuordnung, self.k_erfassen, self.k_abrufen, self.k_oci):
            k.setEnabled(not self.db.nur_lesen)
        return w

    def _menues_fuellen(self):
        for knopf, art in ((self.k_shop, "shop"), (self.k_oci, "oci")):
            m = knopf.menu()
            m.clear()
            for lief in op.lieferanten(self.db, nur_aktiv=True):
                if art == "oci" and not lief.get("oci_adresse"):
                    continue
                a = m.addAction(lief["name"])
                a.triggered.connect(lambda _=False, n=lief["name"], x=art: (self.shop_suche(n) if x == "shop"
                                                                            else self.oci_auswahl(n)))
            if m.isEmpty():
                a = m.addAction("Kein Lieferant mit OCI-Zugang (Reiter Lieferanten)" if art == "oci"
                                else "Kein aktiver Lieferant")
                a.setEnabled(False)

    def _vorwahl_setzen(self):
        v = self.vorwahl
        p = self.k.profile.get(v.get("profil_id")) if v.get("profil_id") else None
        if p:
            self.e_abmessung.setText(p["profil_id"])
            self._felder_aus(p.get("form"), p.get("a"), p.get("b"), p.get("wand"))
        if v.get("werkstoff_id"):
            i = self.e_werkstoff.findData(v["werkstoff_id"])
            if i >= 0:
                self.e_werkstoff.setCurrentIndex(i)
        if v.get("menge_m"):
            self.e_menge.setText(_z(v["menge_m"], 1))

    def _felder_aus(self, form, a, b, wand):
        self.e_form.setCurrentText(form or "")
        self.e_a.setText(_z(a, 2) if a else "")
        self.e_b.setText(_z(b, 2) if b and form not in ("Rundrohr", "Quadratrohr", "Flachstahl") else "")
        self.e_wand.setText(_z(wand, 2) if wand else "")

    def _abmessung_zerlegen(self):
        t = self.e_abmessung.text().strip()
        if not t:
            return
        p = self.k.profile.get(t)
        if p:
            self._felder_aus(p.get("form"), p.get("a"), p.get("b"), p.get("wand"))
            return
        z = op.zerlegen(t.replace("RE ", "Rechteckrohr ").replace("QR ", "Quadratrohr ").replace("RR ", "Rundrohr "))
        if z["form"] and z["a"]:
            self._felder_aus(z["form"], z["a"], z["b"], z["wand"])

    def suche(self):
        """Suchkriterien als dict für onlinepreise.vergleich."""
        s = dict(form=self.e_form.currentText() or None, werkstoff_id=self.e_werkstoff.currentData(),
                 a=op.zahl(self.e_a.text()), b=op.zahl(self.e_b.text()), wand=op.zahl(self.e_wand.text()),
                 laenge=op.zahl(self.e_laenge.text()), oberflaeche=self.e_oberflaeche.text().strip() or None,
                 hersteller=self.e_hersteller.text().strip() or None, artikelnr=self.e_artikel.text().strip() or None)
        return {k: v for k, v in s.items() if v not in (None, "")}

    def menge(self):
        return op.zahl(self.e_menge.text())

    def suchen(self):
        s = self.suche()
        tage = op.zahl(self.db.einstellung("online_veraltet_tage"))
        self.zeilen = op.vergleich(self.db, self.k, s, self.menge(), self.vorwahl.get("stangenlaenge"),
                                   tage=op.VERALTET_TAGE if tage is None else tage) if s else []
        t = self.tabelle
        t.setRowCount(len(self.zeilen))
        fett = QFont()
        fett.setBold(True)
        for r, x in enumerate(self.zeilen):
            z, n = x["zeile"], x["norm"]
            werte = (z.get("lieferant"), z.get("artikelnr"), z.get("bezeichnung"), z.get("werkstoff"),
                     abmessung_text(z), _z(n["laenge_mm"], 0), _z(n["je_m"], 3), _z(n["je_kg"], 3),
                     _z(n["je_stange"], 2), _z(n["einstand_je_m"], 3),
                     f"{_z(z.get('mindestmenge'), 0)} {z.get('mengeneinheit') or ''}".strip(), z.get("ve"),
                     z.get("verfuegbarkeit"), z.get("lieferzeit"), z.get("gueltig_bis"), _zeit(z.get("abruf")),
                     z.get("quelle"), z.get("zuordnung"),
                     f"{_z(z.get('preis'), 4)} {z.get('basis')} {'brutto' if op.ja(z.get('brutto')) else 'netto'}"
                     f" ({z.get('preisart') or ''})")
            for c, w in enumerate(werte):
                it = _item(w)
                if c == 17:
                    it.setToolTip(z.get("zuordnung_grund") or "")
                if c in (6, 7, 8, 9) and not w:
                    it.setText("–")
                    it.setToolTip("; ".join(n["hinweise"]) or "kein Preis")
                if x["bester"]:
                    it.setBackground(QBrush(GRUEN))
                    if c in (6, 9):
                        it.setFont(fett)
                if not x["uebernehmbar"]:
                    it.setForeground(QBrush(GRAU))
                elif x["veraltet"]:
                    it.setForeground(QBrush(ORANGE))
                    it.setToolTip("Veraltet: letzter Abruf älter als die Einstellung „Online-Preise veraltet nach“ "
                                  "oder Gültigkeit abgelaufen")
                t.setItem(r, c, it)
        if not s:
            self.leer.setText("Bitte eine Abmessung, Profilart mit Maßen, Güte oder Artikelnummer eingeben.")
        elif not self.zeilen:
            self.leer.setText("Keine Online-Preise für diese Suche. Preise kommen über Preislisten, OCI-Punchout oder "
                              "„Preis erfassen …“ (z. B. nach „Im Shop suchen“). Ohne Online-Preis rechnet die "
                              "Kalkulation wie bisher mit den Stammdaten.")
        else:
            self.leer.setText("")
        self._info_setzen()
        if self.reiter.currentIndex() == 1:
            self.verlauf_neu()

    def _paar(self):
        """(profil_id, werkstoff_id) der Suche, wenn genau ein Profil der Stammdaten passt."""
        s = self.suche()
        ws = s.get("werkstoff_id")
        if not ws or not s.get("form") or not s.get("a") or not s.get("wand"):
            return None, ws
        e = dict(form=s["form"], a=s["a"], b=s.get("b"), wand=s["wand"], werkstoff=ws)
        zu = op.zuordnen(e, self.k)
        return zu.get("profil_id"), ws

    def _info_setzen(self):
        p, w = self._paar()
        if not p or not w:
            self.info.setText("")
            return
        stamm, quelle = op.stammdaten_je_m(self.db, self.k, p, w)
        kz = op.kennzahlen(self.db, self.k, p, w)
        beste = next((x for x in self.zeilen if x["bester"]), None)
        teile = [f"<b>{p} · {w}</b>",
                 f"Materialstamm: {_z(stamm, 3)} €/m ({quelle})" if stamm else "Materialstamm: kein Preis"]
        if beste and stamm:
            d = 100 * (beste["norm"]["je_m"] - stamm) / stamm
            teile.append(f"bester Online-Preis {_z(beste['norm']['je_m'], 3)} €/m ({'+' if d >= 0 else ''}"
                         f"{_z(d, 1)} % zum Stamm)")
        if kz["tiefst"] is not None:
            teile.append(f"historischer Tiefstpreis {_z(kz['tiefst'], 3)} €/m ({kz['tiefst_lieferant']}, "
                         f"{kz['tiefst_datum']})")
        if kz["letzter_einkauf"] is not None:
            teile.append(f"letzter Einkaufspreis {_z(kz['letzter_einkauf'], 3)} €/m ({kz['letzter_text']})")
        self.info.setText(" · ".join(teile))

    def markiert(self):
        r = self.tabelle.currentRow()
        return self.zeilen[r] if 0 <= r < len(self.zeilen) else None

    def uebernehmen(self, zeile=None, frage=True):
        """Markierten bzw. günstigsten übernehmbaren Preis in die Stammdaten Preise. Ergebnis: ID der Preiszeile."""
        x = zeile or self.markiert() or next((z for z in self.zeilen if z["bester"]), None)
        if x is None:
            return self._meldung("Bitte einen Preis markieren.")
        if not x["uebernehmbar"]:
            return self._meldung("Dieser Preis lässt sich nicht übernehmen: "
                                 + (x["zeile"].get("zuordnung_grund") or "Zuordnung nicht sicher")
                                 + ".\nBitte zuerst „Zuordnung bestätigen …“.")
        z = x["zeile"]
        if frage and QMessageBox.question(
                self, "Preis übernehmen",
                f"{z['lieferant']}: {_z(x['norm']['je_m'], 3)} €/m für {z['profil_id']} · {z['werkstoff_id']} in die "
                "Stammdaten Preise übernehmen?\n\nVorher wird eine Datensicherung erstellt. Bestehende Angebote und "
                "Aufträge ändern sich nicht; offene Angebote meldet der Preiswächter.") != QMessageBox.Yes:
            return None
        try:
            i = op.uebernehmen(self.db, self.k, z["id"], self.menge(), self.einstand.isChecked(),
                               sichern=not self.gesichert)
        except (ValueError, OSError) as f:
            return self._meldung(str(f))
        self.gesichert = True
        self.uebernommen.append(i)
        self.k = self.db.kontext()
        self.suchen()
        return i

    def _meldung(self, text):
        QMessageBox.information(self, "Online-Preise", text) if self.isVisible() else None
        self.letzte_meldung = text
        return None

    def zuordnung(self, zeile=None, profil_id=None, werkstoff_id=None):
        x = zeile or self.markiert()
        if x is None:
            return self._meldung("Bitte einen Preis markieren.")
        z = x["zeile"]
        if profil_id is None:
            d = ZuordnungDialog(self, self.k, z)
            if self.zeigen(d) != QDialog.Accepted:
                return None
            profil_id, werkstoff_id = d.wahl()
        op.zuordnung_bestaetigen(self.db, z["id"], profil_id, werkstoff_id, self.db.einstellung("benutzer_kuerzel"),
                                 self.k)
        self.suchen()
        return True

    def details(self):
        x = self.markiert()
        if x is None:
            return
        z = x["zeile"]
        zeilen = [f"{f.titel}: {z.get(f.name)}" for f in op.PREISE.felder if z.get(f.name) not in (None, "")]
        zeilen.append("Umrechnung: " + ("; ".join(x["norm"]["hinweise"]) or "direkt"))
        QMessageBox.information(self, "Preisdetails", "\n".join(zeilen))

    def suchtext(self):
        s = self.suche()
        ws = self.k.werkstoffe.get(s.get("werkstoff_id")) or {}
        return ad.suchtext(s.get("form"), s.get("a"), s.get("b"), s.get("wand"), ws.get("werkstoff"),
                           self.e_abmessung.text().strip())

    def shop_suche(self, name):
        """Shop-Suche im Browser (Mensch nutzt den Shop mit seinem Login); Suchtext in der Zwischenablage."""
        lief = op.lieferant(self.db, name) or {}
        text = self.suchtext()
        adr = ad.shop_adresse(lief, text)
        if not adr:
            return self._meldung("Für diesen Lieferanten ist keine Shop-Adresse eingetragen (Reiter Lieferanten).")
        QGuiApplication.clipboard().setText(text)
        self.browser(adr)
        return adr

    def erfassen(self, werte=None):
        """Preis von Hand (Quelle „Shop (von Hand)“ oder gewählt); werte: für Tests statt Fenster."""
        if werte is None:
            d = ErfassenDialog(self, self.db, self.suchtext(), self.suche())
            if self.zeigen(d) != QDialog.Accepted:
                return None
            werte = d.werte()
        lief = werte.pop("lieferant")
        quelle = werte.pop("quelle", None) or "Shop (von Hand)"
        try:
            art, i = op.eintragen(self.db, lief, werte, quelle, self.k,
                                  benutzer=self.db.einstellung("benutzer_kuerzel"))
        except ValueError as f:
            return self._meldung(f"Nicht gespeichert: {f}")
        op.protokollieren(self.db, lief, "von Hand", "manuell", "ok", 1, int(art == "neu"), int(art == "geändert"),
                          quelle)
        self.suchen()
        self.protokoll_neu()
        return i

    # ------------------------------------------------------------------ Abruf
    def abrufen(self, name, dateien=None, nochmal=False):
        """Einen Lieferanten jetzt abrufen. Preisliste: Ordner bzw. gewählte Dateien; OCI mit Hintergrundsuche:
        Suchtext der Suche (sonst verwendete Materialien); OCI ohne Hintergrundsuche: Shop-Auswahl; Shop-Suche:
        Browser. Ergebnis: dict oder None."""
        lief = op.lieferant(self.db, name)
        if lief is None:
            return None
        weg = lief.get("weg")
        if dateien is not None or weg == "Preisliste":
            erg = ab.preislisten(self.db, lief, self.k, "manuell", dateien, nochmal,
                                 self.db.einstellung("benutzer_kuerzel"))
        elif weg == "OCI-Punchout" and op.ja(lief.get("oci_hintergrund")):
            texte = [self.suchtext()] if self.suche() else ab.suchtexte(self.db, self.k, op.verwendete(self.db))
            geholt = ab.holen_oci(lief, zugang.lesen(name), [t for t in texte if t])
            erg = ab.oci_speichern(self.db, lief, self.k, geholt, "manuell", self.db.einstellung("benutzer_kuerzel"))
        elif weg == "OCI-Punchout":
            return self.oci_auswahl(name)
        else:
            self.shop_suche(name)
            return None
        self.k = self.db.kontext()
        self.suchen()
        self.lieferanten_neu()
        self.protokoll_neu()
        return erg

    def alle_abrufen(self):
        out = {}
        for lief in op.lieferanten(self.db, nur_aktiv=True):
            if lief.get("weg") == "Preisliste" or (lief.get("weg") == "OCI-Punchout" and op.ja(lief.get("oci_hintergrund"))):
                out[lief["name"]] = self.abrufen(lief["name"])
        text = "\n".join(f"{n}: {e['ergebnis']}, {e['neu']} neu, {e['geaendert']} geändert, {e['gleich']} gleich"
                         + (f" ({'; '.join(e['meldungen'][:3])})" if e["meldungen"] else "") for n, e in out.items() if e)
        self._meldung(text or "Kein Lieferant mit Preisliste oder OCI-Hintergrundsuche. Shop-Suche: Knopf „Im Shop "
                      "suchen“.")
        return out

    def oci_auswahl(self, name):
        """OCI-Punchout interaktiv: Shop im Browser mit dem OCI-Zugang öffnen, Warenkorb kommt zurück."""
        lief = op.lieferant(self.db, name) or {}
        z = zugang.lesen(name)
        if not lief.get("oci_adresse") or not z:
            return self._meldung("Für OCI braucht es die Einstiegsadresse und den OCI-Zugang vom Lieferanten "
                                 "(Reiter Lieferanten, „Zugangsdaten …“).")
        if self.empfang:
            self.empfang.stoppen()
        self.empfang = ad.OciEmpfang(lief["oci_adresse"], z[0], z[1], self.suchtext())
        self.browser(self.empfang.start_adresse)
        self._oci_name, self._oci_start = name, datetime.datetime.now()
        self.oci_uhr = QTimer(self)
        self.oci_uhr.timeout.connect(self._oci_pruefen)
        self.oci_uhr.start(500)
        self.leer.setText(f"{name}: Shop ist im Browser geöffnet. Artikel wählen und „Warenkorb übertragen“ "
                          "drücken; die Preise erscheinen dann hier.")
        return self.empfang

    def _oci_pruefen(self):
        e = self.empfang
        if e is None:
            self.oci_uhr.stop()
            return
        if e.fertig.is_set() or (datetime.datetime.now() - self._oci_start).total_seconds() > 1800:
            self.oci_uhr.stop()
            e.stoppen()
            self.empfang = None
            if e.fertig.is_set():
                lief = op.lieferant(self.db, self._oci_name)
                eintraege, meldungen = e.ergebnis
                erg = ab.oci_speichern(self.db, lief, self.k, ([(eintraege, "OCI-Warenkorb")], meldungen), "manuell",
                                       self.db.einstellung("benutzer_kuerzel"))
                self.leer.setText(f"{self._oci_name}: {erg['anzahl']} Artikel übertragen ({erg['neu']} neu, "
                                  f"{erg['geaendert']} geändert).")
                self.suchen()
                self.protokoll_neu()
            else:
                self.leer.setText("OCI-Sitzung nach 30 Minuten ohne Warenkorb beendet.")

    def reject(self):
        if self.empfang:
            self.empfang.stoppen()
            self.empfang = None
        super().reject()

    # ------------------------------------------------------------------ Preisverlauf
    def _verlauf_seite(self):
        from .preisverlauf_dialog import Kurve
        w = QWidget()
        lay = QVBoxLayout(w)
        oben = QHBoxLayout()
        self.v_titel = QLabel()
        oben.addWidget(self.v_titel, 1)
        self.v_lieferant = QComboBox()
        self.v_lieferant.currentIndexChanged.connect(lambda _: self.verlauf_neu())
        oben.addWidget(QLabel("Lieferant:"))
        oben.addWidget(self.v_lieferant)
        lay.addLayout(oben)
        self.kurve = Kurve(einheit="€/m")
        lay.addWidget(self.kurve)
        self.v_tabelle = QTableWidget(0, 6)
        self.v_tabelle.setHorizontalHeaderLabels(("Seit", "Lieferant", "€/m", "Änderung [%]", "Status", "Quelle"))
        self.v_tabelle.verticalHeader().setVisible(False)
        self.v_tabelle.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.v_tabelle, 1)
        self.v_info = QLabel()
        self.v_info.setWordWrap(True)
        lay.addWidget(self.v_info)
        return w

    def verlauf_neu(self):
        p, w = self._paar()
        if not p or not w:
            self.v_titel.setText("Bitte im Preisvergleich eine Abmessung mit Güte wählen.")
            self.kurve.setzen([])
            self.v_tabelle.setRowCount(0)
            return []
        self.v_titel.setText(f"<b>{p} · {w}</b>: alle Preisstände der Lieferanten")
        alle = op.verlauf(self.db, self.k, p, w)
        namen = sorted({r["lieferant"] for r in alle})
        akt = self.v_lieferant.currentText()
        self.v_lieferant.blockSignals(True)
        self.v_lieferant.clear()
        self.v_lieferant.addItems(namen)
        if akt in namen:
            self.v_lieferant.setCurrentText(akt)
        self.v_lieferant.blockSignals(False)
        wahl = self.v_lieferant.currentText()
        reihe = [r for r in alle if r["lieferant"] == wahl]
        punkte = {}
        for r in reihe:
            d = op._datum(r["datum"])
            if d:
                punkte[d] = r["je_m"]
        self.kurve.setzen(sorted(punkte.items()), "€/m")
        schwelle = op.zahl(self.db.einstellung("online_sprung"))
        schwelle = op.SPRUNG if schwelle is None else schwelle
        self.v_tabelle.setRowCount(len(alle))
        for i, r in enumerate(reversed(alle)):
            z = r["zeile"]
            werte = (_zeit(z.get("seit")), r["lieferant"], _z(r["je_m"], 3), _z(z.get("aenderung"), 1),
                     z.get("status"), z.get("quelle"))
            for c, wert in enumerate(werte):
                it = _item(wert)
                if c == 3 and z.get("aenderung") is not None and abs(z["aenderung"]) >= schwelle:
                    it.setForeground(QBrush(stil.farbe(stil.ROT)))
                    it.setToolTip(f"Ungewöhnliche Preisänderung (ab {_z(schwelle, 0)} %, Einstellung)")
                self.v_tabelle.setItem(i, c, it)
        kz = op.kennzahlen(self.db, self.k, p, w)
        self.v_info.setText(" · ".join(t for t in (
            f"Aktuell verfügbar ab {_z(kz['aktuell'], 3)} €/m" if kz["aktuell"] is not None else "Kein aktueller Preis",
            f"historischer Tiefstpreis {_z(kz['tiefst'], 3)} €/m ({kz['tiefst_lieferant']}, {kz['tiefst_datum']})"
            if kz["tiefst"] is not None else "",
            f"letzter Einkaufspreis {_z(kz['letzter_einkauf'], 3)} €/m ({kz['letzter_text']})"
            if kz["letzter_einkauf"] is not None else "") if t))
        return alle

    # ------------------------------------------------------------------ Lieferanten
    def _lieferanten_seite(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        t = QLabel("Zugangsdaten (OCI-Benutzer und Passwort) liegen nur in der Windows-Anmeldeinformationsverwaltung "
                   "dieses PCs, nicht in der Datenbank und nicht im gemeinsamen Ordner. Der normale Shop-Login wird "
                   "nicht automatisch genutzt (Nutzungsbedingungen der Shops); dafür gibt es „Im Shop suchen“.")
        t.setWordWrap(True)
        t.setStyleSheet(f"color: {GRAU.name()};")
        lay.addWidget(t)
        self.l_tabelle = QTableWidget(0, len(LIEF_SPALTEN) + 2)
        self.l_tabelle.setHorizontalHeaderLabels([s for _, s in LIEF_SPALTEN] + ["Zugang", "Letzter Abruf"])
        self.l_tabelle.verticalHeader().setVisible(False)
        self.l_tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.l_tabelle.itemChanged.connect(self._lief_geaendert)
        self.l_tabelle.setColumnWidth(0, 230)
        lay.addWidget(self.l_tabelle, 1)
        k = QHBoxLayout()
        for text, f in (("Neuer Lieferant", self.lieferant_neu), ("Entfernen …", self.lieferant_weg),
                        ("Zugangsdaten …", self.zugang_bearbeiten), ("Verbindung testen", self.verbindung_testen),
                        ("Jetzt abrufen", lambda: self.abrufen(self._lief_name()) if self._lief_name() else None),
                        ("Preisliste importieren …", self.preisliste_waehlen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, f=f: f())
            b.setEnabled(not self.db.nur_lesen or text == "Verbindung testen")
            k.addWidget(b)
        k.addStretch(1)
        lay.addLayout(k)
        self.l_status = QLabel()
        self.l_status.setWordWrap(True)
        lay.addWidget(self.l_status)
        self.lieferanten_neu()
        return w

    def lieferanten_neu(self):
        t = self.l_tabelle
        t.blockSignals(True)
        zeilen = op.lieferanten(self.db)
        t.setRowCount(len(zeilen))
        for r, z in enumerate(zeilen):
            for c, (feld, _) in enumerate(LIEF_SPALTEN):
                if feld in AUSWAHL:
                    cb = QComboBox()
                    cb.addItems(AUSWAHL[feld])
                    wert = z.get(feld) or op.VORGABE_WERTE.get(feld) or AUSWAHL[feld][0]
                    cb.setCurrentText(str(wert))
                    cb.setEnabled(not self.db.nur_lesen)
                    cb.currentTextChanged.connect(lambda w, i=z["id"], f=feld: self._lief_setzen(i, f, w))
                    t.setCellWidget(r, c, cb)
                    continue
                w = z.get(feld)
                it = QTableWidgetItem(_z(w, 2) if feld in ZAHLEN and w is not None else str(w or ""))
                it.setData(Qt.UserRole, (z["id"], feld))
                if self.db.nur_lesen:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                t.setItem(r, c, it)
            t.setItem(r, len(LIEF_SPALTEN), _item("hinterlegt" if zugang.vorhanden(z["name"]) else "–"))
            letzt = op.protokoll(self.db, z["name"], 1)
            t.setItem(r, len(LIEF_SPALTEN) + 1, _item(
                f"{_zeit(letzt[0]['zeit'])} {letzt[0]['ergebnis']}" if letzt else "noch nie",
                letzt[0]["meldung"] if letzt else None))
        t.blockSignals(False)
        if hasattr(self, "k_shop"):
            self._menues_fuellen()

    def _lief_setzen(self, i, feld, wert):
        if self.db.nur_lesen:
            return
        if feld in ZAHLEN:
            wert = op.zahl(wert)
        if feld == "name":
            wert = str(wert or "").strip()
            if not wert:
                self.l_status.setText("Der Name darf nicht leer sein.")
                self.lieferanten_neu()
                return
        if feld == "spalten" and wert:
            import json
            try:
                json.loads(wert)
            except ValueError:
                self.l_status.setText("Spaltenzuordnung: bitte JSON wie {\"preis\": \"Nettopreis\"}.")
                self.lieferanten_neu()
                return
        try:
            self.db.aendern(op.LIEFERANTEN.name, i, feld, wert)
        except Exception as f:
            self.l_status.setText(f"Nicht gespeichert: {f}")
            self.lieferanten_neu()
            return
        self.l_status.setText("Gespeichert.")
        if feld in ("name", "aktiv", "oci_adresse"):
            self._menues_fuellen()

    def _lief_geaendert(self, it):
        d = it.data(Qt.UserRole)
        if d:
            self._lief_setzen(d[0], d[1], it.text())

    def _lief_name(self):
        r = self.l_tabelle.currentRow()
        it = self.l_tabelle.item(r, 0) if r >= 0 else None
        if it is None:
            self.l_status.setText("Bitte einen Lieferanten markieren.")
            return None
        return it.text()

    def lieferant_neu(self, name=None):
        n = name or "Neuer Lieferant"
        vorhanden = {z["name"] for z in op.lieferanten(self.db)}
        i = 2
        while n in vorhanden:
            n, i = f"{name or 'Neuer Lieferant'} {i}", i + 1
        neu = self.db.neu(op.LIEFERANTEN.name, dict(op.VORGABE_WERTE, name=n, weg="Preisliste"))
        self.lieferanten_neu()
        return neu

    def lieferant_weg(self, frage=True):
        n = self._lief_name()
        if not n:
            return
        if frage and QMessageBox.question(self, "Lieferant entfernen", f"{n} aus dem Online-Preisabruf entfernen? "
                                          "Abgerufene Preise bleiben in der Historie.") != QMessageBox.Yes:
            return
        z = op.lieferant(self.db, n)
        self.db.loeschen(op.LIEFERANTEN.name, [z["id"]])
        zugang.loeschen(n)
        self.lieferanten_neu()

    def zugang_bearbeiten(self, benutzer=None, passwort=None):
        n = self._lief_name()
        if not n:
            return None
        if benutzer is None:
            d = ZugangDialog(self, n, zugang.lesen(n))
            if self.zeigen(d) != QDialog.Accepted:
                return None
            if d.loeschen:
                zugang.loeschen(n)
                self.lieferanten_neu()
                self.l_status.setText(f"Zugang für {n} gelöscht.")
                return False
            benutzer, passwort = d.benutzer.text().strip(), d.passwort.text()
        try:
            dauerhaft = zugang.speichern(n, benutzer, passwort)
        except OSError as f:
            self.l_status.setText(str(f))
            return None
        self.l_status.setText(f"Zugang für {n} gespeichert" + (" (Windows-Anmeldeinformationsverwaltung)." if dauerhaft
                                                               else " (nur bis zum Programmende, kein Windows)."))
        self.lieferanten_neu()
        return True

    def verbindung_testen(self, oeffnen=None):
        n = self._lief_name()
        if not n:
            return None
        ok, text = ad.testen(op.lieferant(self.db, n), zugang.lesen(n), oeffnen)
        self.l_status.setText(f"{n}: {'✓' if ok else '✗'} {text}")
        if not self.db.nur_lesen:
            op.protokollieren(self.db, n, (op.lieferant(self.db, n) or {}).get("weg"), "Verbindungstest",
                              "ok" if ok else "fehler", meldung=text)
            self.protokoll_neu()
        return ok, text

    def preisliste_waehlen(self, dateien=None):
        n = self._lief_name()
        if not n:
            return None
        if dateien is None:
            dateien, _ = QFileDialog.getOpenFileNames(self, f"Preisliste von {n}", "",
                                                      "Preislisten (*.csv *.xlsx *.txt)")
            if not dateien:
                return None
        erg = self.abrufen(n, dateien=dateien, nochmal=True)
        if erg:
            self.l_status.setText(f"{n}: {erg['anzahl']} Preise gelesen ({erg['neu']} neu, {erg['geaendert']} "
                                  f"geändert, {erg['gleich']} gleich)" + (
                                      f"; {len(erg['meldungen'])} Hinweis(e): " + "; ".join(erg["meldungen"][:5])
                                      if erg["meldungen"] else "."))
        return erg

    # ------------------------------------------------------------------ Protokoll
    def _protokoll_seite(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.p_tabelle = QTableWidget(0, 9)
        self.p_tabelle.setHorizontalHeaderLabels(("Zeit", "Lieferant", "Weg", "Anlass", "Ergebnis", "Preise", "neu",
                                                  "geändert", "Meldung"))
        self.p_tabelle.verticalHeader().setVisible(False)
        self.p_tabelle.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.p_tabelle, 1)
        self.protokoll_neu()
        return w

    def protokoll_neu(self):
        if not hasattr(self, "p_tabelle"):
            return
        zeilen = op.protokoll(self.db)
        self.p_tabelle.setRowCount(len(zeilen))
        for r, z in enumerate(zeilen):
            for c, f in enumerate(("zeit", "lieferant", "weg", "anlass", "ergebnis", "anzahl", "neu", "geaendert",
                                   "meldung")):
                it = _item(_zeit(z[f]) if f == "zeit" else z[f], z["meldung"] if f == "meldung" else None)
                if f == "ergebnis" and z[f] == "fehler":
                    it.setForeground(QBrush(stil.farbe(stil.ROT)))
                self.p_tabelle.setItem(r, c, it)

    def _reiter_gewechselt(self, i):
        if i == 1:
            self.verlauf_neu()
        elif i == 3:
            self.protokoll_neu()


class ZuordnungDialog(QDialog):
    def __init__(self, parent, k, z):
        super().__init__(parent)
        self.setWindowTitle("Zuordnung bestätigen")
        lay = QFormLayout(self)
        lay.addRow(QLabel(f"<b>{z.get('lieferant')}</b>: {z.get('artikelnr') or ''} {z.get('bezeichnung') or ''}"))
        lay.addRow(QLabel(f"Güte laut Lieferant: {z.get('werkstoff') or '–'}  ·  Vorschlag: "
                          f"{z.get('zuordnung_grund') or ''}"))
        self.profil = QComboBox()
        self.profil.setEditable(True)
        self.profil.addItems([""] + sorted(k.profile))
        self.profil.setCurrentText(z.get("profil_id") or "")
        self.werkstoff = QComboBox()
        self.werkstoff.setEditable(True)
        self.werkstoff.addItems([""] + sorted(k.werkstoffe))
        self.werkstoff.setCurrentText(z.get("werkstoff_id") or "")
        self.keins = QCheckBox("Gehört zu keinem Profil der Stammdaten")
        lay.addRow("Profil-ID:", self.profil)
        lay.addRow("Werkstoff-ID:", self.werkstoff)
        lay.addRow("", self.keins)
        hinweis = QLabel("Bitte nur bestätigen, wenn der Artikel technisch genau diesem Profil und Werkstoff entspricht "
                         "(Norm, Herstellung, Oberfläche). Die Bestätigung gilt für alle Plätze und künftige Abrufe.")
        hinweis.setWordWrap(True)
        lay.addRow(hinweis)
        kn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        kn.accepted.connect(self.accept)
        kn.rejected.connect(self.reject)
        lay.addRow(kn)
        self.k = k

    def wahl(self):
        if self.keins.isChecked():
            return None, None
        p, w = self.profil.currentText().strip(), self.werkstoff.currentText().strip()
        return (p if p in self.k.profile else None), (w if w in self.k.werkstoffe else None)


class ZugangDialog(QDialog):
    def __init__(self, parent, name, alt):
        super().__init__(parent)
        self.loeschen = False
        self.setWindowTitle(f"Zugangsdaten {name}")
        lay = QFormLayout(self)
        t = QLabel("OCI-Benutzer und OCI-Passwort, die der Lieferant für den Punchout freigeschaltet hat (nicht der "
                   "normale Shop-Login). Gespeichert in der Windows-Anmeldeinformationsverwaltung dieses PCs.")
        t.setWordWrap(True)
        lay.addRow(t)
        self.benutzer = QLineEdit(alt[0] if alt else "")
        self.passwort = QLineEdit(alt[1] if alt else "")
        self.passwort.setEchoMode(QLineEdit.Password)
        lay.addRow("Benutzer:", self.benutzer)
        lay.addRow("Passwort:", self.passwort)
        kn = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        weg = kn.addButton("Zugang löschen", QDialogButtonBox.DestructiveRole)
        weg.setEnabled(bool(alt))
        weg.clicked.connect(self._weg)
        kn.accepted.connect(self.accept)
        kn.rejected.connect(self.reject)
        lay.addRow(kn)

    def _weg(self):
        self.loeschen = True
        self.accept()


class ErfassenDialog(QDialog):
    """Preis von Hand eintragen (aus Shop, Telefon, Lieferantenangebot)."""

    def __init__(self, parent, db, text, suche):
        super().__init__(parent)
        self.setWindowTitle("Preis erfassen")
        lay = QFormLayout(self)
        self.lieferant = QComboBox()
        self.lieferant.setEditable(True)
        self.lieferant.addItems([z["name"] for z in op.lieferanten(db)])
        self.artikel, self.bezeichnung = QLineEdit(), QLineEdit(text)
        ws = (db.kontext().werkstoffe.get(suche.get("werkstoff_id")) or {}) if suche.get("werkstoff_id") else {}
        norm = "".join(c for c in str(suche.get("werkstoff_id") or "") if c.isdigit())[-5:]
        self.werkstoff = QLineEdit(" ".join(x for x in (ws.get("werkstoff"), f"EN {norm}" if len(norm) == 5 else "")
                                            if x))
        self.basis = QComboBox()
        self.basis.addItems(op.BASEN)
        self.preis, self.laenge, self.lieferzeit, self.gueltig, self.verfuegbar = (QLineEdit() for _ in range(5))
        self.laenge.setText(_z(suche.get("laenge"), 0) if suche.get("laenge") else "6000")
        self.preisart = QComboBox()
        self.preisart.addItems(op.PREISARTEN)
        self.brutto = QCheckBox("Preis ist brutto (mit MwSt)")
        self.quelle = QLineEdit("Shop (von Hand)")
        for titel, f in (("Lieferant", self.lieferant), ("Artikelnummer", self.artikel),
                         ("Bezeichnung (mit Abmessung)", self.bezeichnung), ("Güte (mit Norm)", self.werkstoff),
                         ("Preisbasis", self.basis), ("Preis [€]", self.preis), ("Länge [mm]", self.laenge),
                         ("Preisart", self.preisart), ("", self.brutto), ("Lieferzeit [Tage]", self.lieferzeit),
                         ("Gültig bis (TT.MM.JJJJ)", self.gueltig), ("Verfügbarkeit", self.verfuegbar),
                         ("Quelle", self.quelle)):
            lay.addRow(titel, f)
        kn = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        kn.accepted.connect(self._ok)
        kn.rejected.connect(self.reject)
        lay.addRow(kn)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #C00000;")
        lay.addRow(self.fehler)

    def _ok(self):
        if not op.zahl(self.preis.text()) or not self.lieferant.currentText().strip():
            self.fehler.setText("Bitte Lieferant und Preis angeben.")
            return
        self.accept()

    def werte(self):
        g = op._datum(self.gueltig.text())
        return dict(lieferant=self.lieferant.currentText().strip(), artikelnr=self.artikel.text().strip(),
                    bezeichnung=self.bezeichnung.text().strip(), werkstoff=self.werkstoff.text().strip(),
                    basis=self.basis.currentText(), preis=op.zahl(self.preis.text()), laenge=op.zahl(self.laenge.text()),
                    preisart=self.preisart.currentText(), brutto="ja" if self.brutto.isChecked() else "nein",
                    lieferzeit=op.zahl(self.lieferzeit.text()), gueltig_bis=g.isoformat() if g else None,
                    verfuegbarkeit=self.verfuegbar.text().strip(), quelle=self.quelle.text().strip())


# ---------------------------------------------------------------------- automatischer Abruf (Hauptfenster)
def auto_abruf(fenster, anlass, paare=None):
    """Fällige Lieferanten abrufen (Programmstart, stündliche Uhr, Öffnen eines Angebots). Preislisten sofort (lokale
    Dateien), OCI-Hintergrundsuche im Hilfsfaden; Speichern immer im Hauptfaden. Fehler ändern keinen Preis.
    Ergebnis: Liste der gestarteten Lieferanten."""
    from . import funktionen
    db = getattr(fenster, "db", None)
    if db is None or db.nur_lesen or not funktionen.an("funktion_onlinepreise", db):
        return []
    try:
        faellig = ab.faellige(db, anlass)
    except Exception:
        return []
    if not faellig:
        return []
    k = db.kontext()
    gestartet = []
    for lief in faellig:
        nur = None
        if op.ja(lief.get("nur_verwendete")) or lief.get("weg") == "OCI-Punchout":
            nur = op.verwendete(db, dazu=paare or ())
        if anlass == "oeffnen" and paare:
            nur = set(paare)
        if lief.get("weg") == "Preisliste":
            try:
                ab.preislisten(db, lief, k, anlass, nur=nur if op.ja(lief.get("nur_verwendete")) or anlass == "oeffnen"
                               else None)
            except Exception as f:
                op.protokollieren(db, lief["name"], "Preisliste", anlass, "fehler", meldung=str(f))
            gestartet.append(lief["name"])
            continue
        if ab.laeuft(lief["name"]):
            continue
        texte = ab.suchtexte(db, k, nur)
        z = zugang.lesen(lief["name"])
        ergebnis = {}

        def holen(lief=lief, texte=texte, z=z, ergebnis=ergebnis):
            ergebnis["daten"] = ab.holen_oci(lief, z, texte)
        faden = threading.Thread(target=holen, daemon=True)
        faden.start()
        uhr = QTimer(fenster)

        def fertig(lief=lief, faden=faden, uhr=uhr, ergebnis=ergebnis, nur=nur):
            if faden.is_alive():
                return
            uhr.stop()
            try:
                ab.oci_speichern(db, lief, db.kontext(), ergebnis.get("daten") or ([], ["kein Ergebnis"]), anlass,
                                 nur=nur)
            except Exception as f:
                op.protokollieren(db, lief["name"], "OCI-Punchout", anlass, "fehler", meldung=str(f))
        uhr.timeout.connect(fertig)
        uhr.start(500)
        gestartet.append(lief["name"])
    return gestartet
