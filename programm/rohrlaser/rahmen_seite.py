"""Seite „Rahmenaufträge“ und Fenster eines Rahmenauftrags (Patrick 20.11.2026, Master-Auftrag Rahmenaufträge und
Abrufe). Daten und Regeln in rahmenauftrag.py, Rechnung in rahmen_kalk.py, Dokumente in rahmen_pdf.py.

Seite: Kennzahlen oben (aktive Rahmen, Volumen, Restwert, überfällige Abrufe, rot/gelb), Filter nach Kunde, Artikel,
Status und Vertragsende, Liste mit Ampel. Doppelklick öffnet das Rahmenfenster mit den Reitern Vertrag, Positionen,
Abrufe (mit Grafik Plan/geliefert), Wirtschaftlichkeit (A/B/C, feste Lose, Material, Gegenprüfung), Preisstaffel,
Preisbindung (Auswirkung einer Materialpreisänderung, Vorschlag und Freigabe), Material und Lose, Protokoll und
Abschluss."""
import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import rahmen_kalk as rk
from . import rahmenauftrag as ra
from .auftraege_seite import _datum, _eur, _zeit

AMPEL = {rk.GRUEN: "#1E6B34", rk.GELB: "#B86E00", rk.ROT: "#B42318"}
AMPEL_FL = {rk.GRUEN: "#E3F4E8", rk.GELB: "#FFF3E0", rk.ROT: "#FDECEA"}
SPALTEN = ("", "Rahmen", "Kunde", "Projekt", "Status", "Ende", "Menge", "Abgerufen", "Geliefert", "Offen",
           "Restwert €", "Abrufe offen", "Überfällig", "Marge", "Hinweis")
ENDE_FILTER = (("Alle Laufzeiten", None), ("endet in 30 Tagen", 30), ("endet in 90 Tagen", 90),
               ("endet in 180 Tagen", 180))


def _z(x, stellen=0):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return ""
    t = f"{f:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return t


def _pz(x):
    return f"{100 * x:.1f} %".replace(".", ",") if isinstance(x, (int, float)) else ""


def _item(text, rechts=False, farbe=None):
    it = QTableWidgetItem(str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if rechts:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if farbe:
        it.setBackground(QColor(farbe))
    return it


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(list(spalten))
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def _fuellen(t, zeilen, rechts=(), farben=None):
    t.setRowCount(len(zeilen))
    for r, z in enumerate(zeilen):
        for c, w in enumerate(z):
            t.setItem(r, c, _item(w, c in rechts, (farben or {}).get(r)))


def _meldung(parent, text, titel="Rahmenauftrag"):
    if getattr(getattr(parent, "f", None), "stumm", False) or getattr(parent, "stumm", False):
        return
    QMessageBox.information(parent, titel, text)


# ------------------------------------------------------------------ Seite
class RahmenSeite(QWidget):
    titel = "Rahmenaufträge"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.stumm = getattr(fenster, "stumm", False)
        self.zeilen = []
        self.kacheln = QLabel()
        self.kacheln.setTextFormat(Qt.RichText)
        self.kunde = QLineEdit()
        self.kunde.setPlaceholderText("Kunde …")
        self.artikel = QLineEdit()
        self.artikel.setPlaceholderText("Artikel …")
        self.status = QComboBox()
        self.status.addItem("Alle Status", None)
        for s in ra.STATUS_LISTE:
            self.status.addItem(s, s)
        self.ende = QComboBox()
        for t, d in ENDE_FILTER:
            self.ende.addItem(t, d)
        for w in (self.kunde, self.artikel):
            w.setClearButtonEnabled(True)
            w.textChanged.connect(self.neu_laden)
        for w in (self.status, self.ende):
            w.currentIndexChanged.connect(self.neu_laden)
        oben = QHBoxLayout()
        for w in (self.kunde, self.artikel, self.status, self.ende):
            oben.addWidget(w)
        self.tabelle = _tabelle(SPALTEN)
        self.tabelle.cellDoubleClicked.connect(lambda r, c: self.oeffnen())
        knoepfe = QHBoxLayout()
        self.knopf = {}
        for name, text, ziel in (("neu", "Neuer Rahmenauftrag …", self.neu), ("angebot", "Aus Angebot …", self.aus_angebot),
                                 ("oeffnen", "Öffnen", self.oeffnen)):
            b = QPushButton(text)
            b.clicked.connect(ziel)
            knoepfe.addWidget(b)
            self.knopf[name] = b
        knoepfe.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addWidget(self.kacheln)
        lay.addLayout(oben)
        lay.addWidget(self.tabelle, 1)
        lay.addLayout(knoepfe)
        self.neu_laden()

    def marge_min(self):
        return rk.mindestmarge_satz(self.db.einstellungen())

    def filter_werte(self):
        f = dict(kunde=self.kunde.text().strip(), artikel=self.artikel.text().strip(), status=self.status.currentData())
        tage = self.ende.currentData()
        if tage:
            f["ende_bis"] = (datetime.date.today() + datetime.timedelta(days=tage)).isoformat()
        return f

    def neu_laden(self, *_):
        self.zeilen = ra.dashboard(self.db, marge_min=self.marge_min(), filter_=self.filter_werte())
        s = ra.summen(self.zeilen)
        self.kacheln.setText(
            f"<b>{s['aktiv']}</b> aktive Rahmen · Volumen <b>{_eur(s['volumen'])} €</b> · Restwert "
            f"<b>{_eur(s['restwert'])} €</b> · abgerufen {_z(s['abgerufen'])} / offen {_z(s['offen'])} Stk. · "
            f"<span style='color:{AMPEL[rk.ROT]}'>{s['rot']} rot</span> · "
            f"<span style='color:{AMPEL[rk.GELB]}'>{s['gelb']} gelb</span> · {s['ueberfaellig']} Abrufe überfällig")
        zeilen = []
        for r, z in enumerate(self.zeilen):
            zeilen.append(["●", z["nummer"] or "", z["kunde"] or "", z["projekt"] or "", z["status"] or "",
                           _datum(z["ende"]), _z(z["menge"]), _z(z["abgerufen"]), _z(z["geliefert"]), _z(z["offen"]),
                           _eur(z["restwert"]), str(z["abrufe_offen"]), str(z["ueberfaellig"] or ""), _pz(z["marge"]),
                           "; ".join(t for _, t in z["warnungen"][:2])])
        _fuellen(self.tabelle, zeilen, rechts=(6, 7, 8, 9, 10, 11, 12, 13))
        for r, z in enumerate(self.zeilen):
            it = self.tabelle.item(r, 0)
            it.setForeground(QColor(AMPEL[z["ampel"]]))
            it.setToolTip("\n".join(t for _, t in z["warnungen"]) or "Alles im Plan")
            if z["ampel"] != rk.GRUEN:
                self.tabelle.item(r, 14).setBackground(QColor(AMPEL_FL[z["ampel"]]))
        return self.zeilen

    def gewaehlt(self):
        r = self.tabelle.currentRow()
        return self.zeilen[r]["uid"] if 0 <= r < len(self.zeilen) else None

    def neu(self, *_, werte=None):
        if werte is None:
            kunde, ok = QInputDialog.getText(self, "Neuer Rahmenauftrag", "Kunde:")
            if not ok or not kunde.strip():
                return None
            werte = dict(kunde=kunde.strip(), start=datetime.date.today().isoformat(),
                         ende=ra._plus_monate(datetime.date.today(), 12).isoformat())
        try:
            uid = ra.anlegen(self.db, werte)
        except ra.RahmenFehler as e:
            _meldung(self, str(e))
            return None
        self.neu_laden()
        self.oeffnen(uid)
        return uid

    def aus_angebot(self, *_, angebot_id=None):
        if angebot_id is None:
            nr, ok = QInputDialog.getText(self, "Rahmenauftrag aus Angebot", "Angebotsnummer:")
            if not ok:
                return None
            treffer = [a for a in self.db.angebote(nr.strip()) if (a.get("nummer") or "") == nr.strip()] or \
                self.db.angebote(nr.strip())
            if not treffer:
                _meldung(self, f"Angebot {nr} nicht gefunden.")
                return None
            angebot_id = treffer[0]["id"]
        try:
            uid = ra.aus_angebot(self.db, angebot_id)
        except ra.RahmenFehler as e:
            _meldung(self, str(e))
            return None
        self.neu_laden()
        self.oeffnen(uid)
        return uid

    def oeffnen(self, uid=None):
        uid = uid or self.gewaehlt()
        if not uid:
            return None
        d = RahmenFenster(self, uid)
        self.fenster_offen = d
        if not self.stumm:
            d.exec()
            self.neu_laden()
        return d


# ------------------------------------------------------------------ Grafik der Abrufe
class AbrufGrafik(QWidget):
    """Balken je Abruf: Abrufmenge hell, geliefert dunkel, storniert durchgestrichen grau; rote Marke = überfällig."""

    def __init__(self):
        super().__init__()
        self.abrufe = []
        self.setMinimumHeight(150)

    def setzen(self, abrufe):
        self.abrufe = list(abrufe)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        unten, oben, links = h - 24, 14, 8
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        if not self.abrufe:
            p.setPen(QColor("#5B6773"))
            p.drawText(self.rect(), Qt.AlignCenter, "Noch keine Abrufe")
            return
        top = max(max(a["menge"] for a in self.abrufe), 1)
        bw = (w - links) / len(self.abrufe)
        heute = datetime.date.today().isoformat()
        p.setPen(QPen(QColor("#16212B"), 1))
        p.drawLine(links, unten, w, unten)
        for i, a in enumerate(self.abrufe):
            x = links + i * bw + bw * 0.15
            b = bw * 0.7
            hh = (unten - oben) * a["menge"] / top
            st = a.get("status") == ra.STORNIERT
            p.setPen(QPen(QColor("#9AA4AE" if st else "#0B5563"), 1))
            p.setBrush(QColor("#ECEEF1" if st else "#E3F0F2"))
            p.drawRect(int(x), int(unten - hh), int(b), int(hh))
            if a.get("geliefert_menge") and not st:
                gh = (unten - oben) * a["geliefert_menge"] / top
                p.setBrush(QColor("#0B5563"))
                p.drawRect(int(x), int(unten - gh), int(b), int(gh))
            if st:
                p.drawLine(int(x), int(unten - hh), int(x + b), int(unten))
            if a.get("status") in ra.OFFEN_A and (a.get("datum") or "9") < heute:
                p.setBrush(QColor("#B42318"))
                p.setPen(Qt.NoPen)
                p.drawEllipse(int(x + b / 2 - 4), int(unten - hh - 11), 8, 8)
            p.setPen(QColor("#5B6773"))
            p.drawText(int(x - 6), unten + 4, int(b + 12), 16, Qt.AlignHCenter, _datum(a.get("datum"))[:6])
        p.end()


# ------------------------------------------------------------------ Fenster eines Rahmens
class RahmenFenster(QDialog):
    def __init__(self, seite, uid):
        super().__init__(seite)
        self.s, self.db, self.uid = seite, seite.db, uid
        self.stumm = seite.stumm
        self.erg = None
        self.modell = None
        self.auswirkung_erg = None
        self.setWindowTitle("Rahmenauftrag")
        self.resize(1180, 760)
        self.kopf = QLabel()
        self.kopf.setTextFormat(Qt.RichText)
        self.reiter = QTabWidget()
        self._vertrag()
        self._positionen()
        self._abrufe()
        self._wirtschaft()
        self._staffel()
        self._bindung()
        self._material()
        self._protokoll()
        self._abschluss()
        unten = QHBoxLayout()
        self.dok = QPushButton("Dokumente …")
        menue = QMenu(self.dok)
        from . import rahmen_pdf
        for art, (titel, _) in rahmen_pdf.ARTEN.items():
            menue.addAction(titel, lambda a=art: self.dokument(a))
        self.dok.setMenu(menue)
        self.status_k = QPushButton("Status …")
        self.status_k.clicked.connect(self.status_aendern)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        unten.addWidget(self.dok)
        unten.addWidget(self.status_k)
        unten.addStretch(1)
        unten.addWidget(zu)
        lay = QVBoxLayout(self)
        lay.addWidget(self.kopf)
        lay.addWidget(self.reiter, 1)
        lay.addLayout(unten)
        self.laden()

    # ---------------------------------------------------------- Laden
    def laden(self):
        self.z = ra.sicht(self.db, self.uid)
        self.k = ra.kennzahlen(self.z)
        z, k = self.z, self.k
        w = rk.warnungen(z, marge_min=rk.mindestmarge_satz(self.db.einstellungen()))
        a = rk.ampel(w)
        self.setWindowTitle(f"Rahmenauftrag {z.get('nummer')} · {z.get('kunde') or ''}")
        self.kopf.setText(
            f"<span style='font-size:15px'><b>{z.get('nummer')}</b> · {z.get('kunde') or ''} · "
            f"{z.get('projekt') or ''}</span>&nbsp;&nbsp;<span style='color:{AMPEL[a]}'>● {z.get('status')}</span><br>"
            f"Rahmenmenge {_z(k['menge'])} · abgerufen {_z(k['abgerufen'])} · geliefert {_z(k['geliefert'])} · "
            f"offen {_z(k['offen'])} · noch abrufbar {_z(max(k['verfuegbar'], 0))} · Restwert {_eur(k['restwert'])} € · "
            f"{len(k['offene_abrufe'])} offene Abrufe"
            + ("<br><span style='color:%s'>%s</span>" % (AMPEL[a], " · ".join(t for _, t in w)) if w else ""))
        self._vertrag_laden()
        self._positionen_laden()
        self._abrufe_laden()
        self._bindung_laden()
        self._material_laden()
        self._protokoll_laden()
        self._abschluss_laden()

    # ---------------------------------------------------------- Vertrag
    def _vertrag(self):
        w = QWidget()
        form = QFormLayout(w)
        self.felder = {}
        for n, t in ra.KOPF:
            if n in ("bedingungen", "bemerkung", "abrufbedingungen", "lieferbedingungen"):
                e = QPlainTextEdit()
                e.setFixedHeight(48)
            else:
                e = QLineEdit()
                if n in ("start", "ende", "preis_gueltig"):
                    e.setPlaceholderText("JJJJ-MM-TT")
            self.felder[n] = e
            form.addRow(t, e)
        b = QPushButton("Vertragsdaten speichern")
        b.clicked.connect(self.vertrag_speichern)
        form.addRow("", b)
        self.reiter.addTab(w, "Vertrag")

    def _vertrag_laden(self):
        for n, e in self.felder.items():
            v = self.z.get(n)
            t = "" if v is None else (_z(v, 2).rstrip("0").rstrip(",") if isinstance(v, float) else str(v))
            e.setPlainText(t) if isinstance(e, QPlainTextEdit) else e.setText(t)

    def vertrag_speichern(self, *_, werte=None):
        werte = werte or {n: (e.toPlainText() if isinstance(e, QPlainTextEdit) else e.text()).strip() or None
                          for n, e in self.felder.items()}
        zahlen = ("jahresbedarf", "gesamtpreis", "min_abruf", "max_abruf", "abrufe_geplant", "intervall")
        n_ = 0
        for n, v in werte.items():
            if n in zahlen and v is not None:
                try:
                    v = float(str(v).replace(".", "").replace(",", ".")) if "," in str(v) else float(v)
                except ValueError:
                    _meldung(self, f"{ra.KOPF_TITEL[n]}: keine Zahl")
                    return 0
            alt = self.z.get(n)
            if (alt if alt not in ("", None) else None) != v:
                ra.aendern(self.db, self.uid, n, v)
                n_ += 1
        self.laden()
        return n_

    def status_aendern(self, *_, status=None):
        if status is None:
            status, ok = QInputDialog.getItem(self, "Status", "Status des Rahmenauftrags:", list(ra.STATUS_LISTE),
                                              ra.STATUS_LISTE.index(self.z["status"]), False)
            if not ok:
                return
        ra.status_setzen(self.db, self.uid, status)
        self.laden()

    # ---------------------------------------------------------- Positionen
    def _positionen(self):
        w = QWidget()
        self.pos_t = _tabelle(("Pos.", "Artikel", "Bezeichnung", "Rahmenmenge", "Stückpreis €", "kg/Stk.", "Abgerufen",
                               "Geplant", "Geliefert", "Offen", "Noch abrufbar", "Gefertigt", "Auf Lager", "Restwert €"))
        knoepfe = QHBoxLayout()
        for t, f in (("Position ergänzen …", self.position_neu), ("Menge ändern …", lambda: self.position_feld("menge")),
                     ("Preis ändern …", lambda: self.position_feld("preis")),
                     ("Gewicht ändern …", lambda: self.position_feld("kg_teil"))):
            b = QPushButton(t)
            b.clicked.connect(f)
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        lay = QVBoxLayout(w)
        lay.addWidget(self.pos_t, 1)
        lay.addLayout(knoepfe)
        self.reiter.addTab(w, "Positionen")

    def _positionen_laden(self):
        _fuellen(self.pos_t, [[p["pos"], p.get("artikel") or "", p.get("bezeichnung") or "", _z(p["menge"]),
                               _z(p.get("preis"), 2) if p.get("preis") is not None else "–", _z(p["kg_teil"], 3),
                               _z(p["abgerufen"]), _z(p["geplant"]), _z(p["geliefert"]), _z(p["offen"]),
                               _z(p["verfuegbar"]), _z(p["gefertigt"]), _z(p["bestand"]), _eur(p["restwert"])]
                              for p in self.k["positionen"]], rechts=tuple(range(3, 14)))

    def _pos_gewaehlt(self):
        r = self.pos_t.currentRow()
        return self.k["positionen"][r] if 0 <= r < len(self.k["positionen"]) else None

    def position_neu(self, *_, werte=None):
        if werte is None:
            nr, ok = QInputDialog.getText(self, "Position", "Pos.-Nr.:")
            if not ok or not nr.strip():
                return
            bez, _ = QInputDialog.getText(self, "Position", "Bezeichnung:")
            menge, ok = QInputDialog.getInt(self, "Position", "Rahmenmenge [Stk.]:", 1000, 1, 100000000)
            if not ok:
                return
            werte = dict(pos=nr.strip(), bezeichnung=bez, menge=menge)
        ra.position_neu(self.db, self.uid, werte)
        self.laden()

    def position_feld(self, feld, wert=None, pos=None):
        p = pos or self._pos_gewaehlt()
        if not p:
            return
        if wert is None:
            wert, ok = QInputDialog.getDouble(self, "Position", f"{feld} für Pos. {p['pos']}:", float(p.get(feld) or 0),
                                              0, 1e9, 3 if feld == "kg_teil" else 2)
            if not ok:
                return
        try:
            ra.position_aendern(self.db, self.uid, p["uid"], feld, wert)
        except ra.RahmenFehler as e:
            _meldung(self, str(e))
        self.laden()

    # ---------------------------------------------------------- Abrufe
    def _abrufe(self):
        w = QWidget()
        self.grafik = AbrufGrafik()
        self.abr_t = _tabelle(("Nr.", "Termin", "Geliefert am", "Status", "Menge", "Geliefert", "Wert €", "Lieferort",
                               "Auftrag/Lieferschein", "Mengen je Position", "Bemerkung"))
        knoepfe = QHBoxLayout()
        for t, f in (("Abruf anlegen …", self.abruf_neu), ("Abrufplan erzeugen …", self.plan_erzeugen),
                     ("Menge ändern …", self.abruf_menge), ("Verschieben …", self.abruf_verschieben),
                     ("Abgerufen", lambda: self.abruf_status(ra.ABGERUFEN)), ("Liefern …", self.abruf_liefern),
                     ("Abschließen", lambda: self.abruf_status(ra.ABGESCHLOSSEN_A)),
                     ("Stornieren …", self.abruf_stornieren)):
            b = QPushButton(t)
            b.clicked.connect(f)
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        lay = QVBoxLayout(w)
        lay.addWidget(self.grafik)
        lay.addWidget(self.abr_t, 1)
        lay.addLayout(knoepfe)
        self.reiter.addTab(w, "Abrufe")

    def _abrufe_laden(self):
        heute = datetime.date.today().isoformat()
        zeilen, farben = [], {}
        for r, a in enumerate(self.k["abrufe"]):
            zeilen.append([str(a["nr"]), _datum(a.get("datum")), _datum(a.get("ist_datum")), a.get("status") or "",
                           _z(a["menge"]), _z(a["geliefert_menge"]), _eur(a["wert"]), a.get("lieferort") or "",
                           a.get("auftragsnr") or "", ", ".join(f"{p}: {_z(q)}" for p, q in (a.get("mengen") or {}).items()),
                           a.get("storno_grund") or a.get("bemerkung") or ""])
            if a.get("status") == ra.STORNIERT:
                farben[r] = "#ECEEF1"
            elif a.get("status") in ra.OFFEN_A and (a.get("datum") or "9") < heute:
                farben[r] = AMPEL_FL[rk.ROT]
            elif a.get("status") in (ra.GELIEFERT, ra.ABGESCHLOSSEN_A):
                farben[r] = AMPEL_FL[rk.GRUEN]
        _fuellen(self.abr_t, zeilen, rechts=(4, 5, 6), farben=farben)
        self.grafik.setzen(self.k["abrufe"])

    def _abruf_gewaehlt(self):
        r = self.abr_t.currentRow()
        return self.k["abrufe"][r] if 0 <= r < len(self.k["abrufe"]) else None

    def _mengen_dialog(self, titel, vorgabe=None, datum=None):
        d = QDialog(self)
        d.setWindowTitle(titel)
        form = QFormLayout(d)
        de = QDateEdit(QDate.fromString(datum or datetime.date.today().isoformat(), "yyyy-MM-dd"))
        de.setCalendarPopup(True)
        form.addRow("Termin", de)
        spins = {}
        for p in self.k["positionen"]:
            s = QSpinBox()
            s.setRange(0, 100000000)
            s.setValue(int((vorgabe or {}).get(p["pos"], 0)))
            form.addRow(f"Pos. {p['pos']} {p.get('bezeichnung') or ''}", s)
            spins[p["pos"]] = s
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.accepted.connect(d.accept)
        k.rejected.connect(d.reject)
        form.addRow(k)
        if d.exec() != QDialog.Accepted:
            return None, None
        return de.date().toString("yyyy-MM-dd"), {p: s.value() for p, s in spins.items() if s.value()}

    def abruf_neu(self, *_, datum=None, mengen=None):
        if mengen is None:
            datum, mengen = self._mengen_dialog("Abruf anlegen")
            if not mengen:
                return None
        try:
            uid, warn = ra.abruf_neu(self.db, self.uid, datum, mengen)
        except ra.RahmenFehler as e:
            _meldung(self, str(e))
            return None
        if warn:
            _meldung(self, warn)
        self.laden()
        return uid

    def plan_erzeugen(self, *_, anzahl=None, erster=None, intervall=None):
        if anzahl is None:
            anzahl, ok = QInputDialog.getInt(self, "Abrufplan", "Anzahl Abrufe:", int(self.z.get("abrufe_geplant") or 6),
                                             1, 240)
            if not ok:
                return []
            intervall, ok = QInputDialog.getInt(self, "Abrufplan", "Abstand [Monate]:",
                                                int(self.z.get("intervall") or 2), 1, 24)
            if not ok:
                return []
            erster = self.z.get("start") or datetime.date.today().isoformat()
        plan = ra.plan_vorschlag(self.z, anzahl, erster, intervall)
        uids = ra.abrufplan(self.db, self.uid, plan)
        self.laden()
        return uids

    def abruf_menge(self, *_, abruf=None, mengen=None):
        a = abruf or self._abruf_gewaehlt()
        if not a:
            return
        if mengen is None:
            _, mengen = self._mengen_dialog(f"Abruf {a['nr']} Menge", a.get("mengen"), a.get("datum"))
            if mengen is None:
                return
        try:
            warn = ra.abruf_aendern(self.db, self.uid, a["uid"], "mengen", mengen)
            if warn:
                _meldung(self, warn)
        except ra.RahmenFehler as e:
            _meldung(self, str(e))
        self.laden()

    def abruf_verschieben(self, *_, abruf=None, datum=None):
        a = abruf or self._abruf_gewaehlt()
        if not a:
            return
        if datum is None:
            datum, _ = self._mengen_dialog(f"Abruf {a['nr']} verschieben", a.get("mengen"), a.get("datum"))
            if datum is None:
                return
        ra.abruf_aendern(self.db, self.uid, a["uid"], "datum", datum)
        self.laden()

    def abruf_status(self, status, abruf=None):
        a = abruf or self._abruf_gewaehlt()
        if not a:
            return
        try:
            ra.abruf_status(self.db, self.uid, a["uid"], status)
        except ra.RahmenFehler as e:
            _meldung(self, str(e))
        self.laden()

    def abruf_liefern(self, *_, abruf=None, lieferschein=None):
        a = abruf or self._abruf_gewaehlt()
        if not a:
            return
        if lieferschein is None and not self.stumm:
            lieferschein, ok = QInputDialog.getText(self, "Lieferung", "Lieferschein (optional):")
            if not ok:
                return
        try:
            ra.lieferung(self.db, self.uid, a["uid"], lieferschein=lieferschein or None)
        except ra.RahmenFehler as e:
            _meldung(self, str(e))
        self.laden()

    def abruf_stornieren(self, *_, abruf=None, grund=None):
        a = abruf or self._abruf_gewaehlt()
        if not a:
            return
        if grund is None:
            grund, ok = QInputDialog.getText(self, "Abruf stornieren", f"Grund für die Stornierung von Abruf {a['nr']}:")
            if not ok:
                return
        try:
            ra.abruf_stornieren(self.db, self.uid, a["uid"], grund)
        except ra.RahmenFehler as e:
            _meldung(self, str(e))
        self.laden()

    # ---------------------------------------------------------- Wirtschaftlichkeit
    def _wirtschaft(self):
        w = QWidget()
        self.mat_art = QComboBox()
        self.mat_art.addItems(list(rk.MATERIAL_ARTEN))
        b = QPushButton("Berechnen")
        b.clicked.connect(self.berechnen)
        self.fest_k = QPushButton("Kalkulation festschreiben")
        self.fest_k.clicked.connect(self.festschreiben)
        self.preise_k = QPushButton("Stückpreise übernehmen")
        self.preise_k.setToolTip("Vorgeschlagene Stückpreise der empfohlenen Variante als Vertragspreise (nur vor "
                                 "„Aktiv“; danach nur über Preisänderung mit Freigabe)")
        self.preise_k.clicked.connect(self.preise_uebernehmen)
        self.lose_k = QPushButton("Lose anlegen")
        self.lose_k.clicked.connect(self.lose_anlegen)
        par_k = QPushButton("Parameter …")
        par_k.clicked.connect(self.parameter_dialog)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Material:"))
        oben.addWidget(self.mat_art)
        for x in (b, par_k, self.fest_k, self.preise_k, self.lose_k):
            oben.addWidget(x)
        oben.addStretch(1)
        self.empf = QLabel("Noch nicht berechnet. Die Kosten je Los kommen aus der Kalkulation des Angebots.")
        self.empf.setWordWrap(True)
        self.empf.setTextFormat(Qt.RichText)
        self.var_t = _tabelle(("Posten", "A je Abruf", "B gesamt", "C optimiert"))
        self.fest_t = _tabelle(("Feste Losgröße", "Lose", "Selbstkosten €", "Preis €/Stk.", "Marge"))
        self.gp_t = _tabelle(("Los", "Stück", "Modell €", "Zentrale Rechnung €", "Abweichung", "Material Abw."))
        unten = QHBoxLayout()
        unten.addWidget(self.fest_t)
        unten.addWidget(self.gp_t)
        lay = QVBoxLayout(w)
        lay.addLayout(oben)
        lay.addWidget(self.empf)
        lay.addWidget(self.var_t, 2)
        lay.addLayout(unten, 1)
        self.reiter.addTab(w, "Wirtschaftlichkeit")

    def angebot(self):
        from . import auftraege
        u = self.z.get("angebot_uid")
        return auftraege.angebot_id(self.db, u) if u else None

    def kostenmodell(self):
        """Kostenmodell aus der zentralen Rechnung des Angebots (Fehlertext statt Modell, wenn das nicht geht)."""
        from . import rechnen
        aid = self.angebot()
        if not aid:
            return None, "Kein Angebot verknüpft: die Kosten je Los kommen aus der Kalkulation eines Angebots."
        kopf, pos = self.db.angebot(aid), self.db.positionen(aid)
        einst = rechnen.einstellungen_angebot(kopf, self.db.einstellungen())
        k, tab = self.db.kontext(), self.db.tabellen()
        modell, info = rk.kostenmodell_aus_angebot(kopf, pos, self.k["positionen"], self.z["abrufe"], k, tab, einst)
        if modell is None:
            return None, info
        self._lauf = (kopf, pos, k, tab, einst)
        return modell, None

    def berechnen(self, *_):
        if self.z.get("parameter", {}).get("material") != self.mat_art.currentText():
            par = dict(self.z.get("parameter") or {}, material=self.mat_art.currentText())
            ra.parameter_setzen(self.db, self.uid, par, "Materialart")
            self.laden()
        modell, fehler = self.kostenmodell()
        if fehler:
            self.empf.setText(f"<span style='color:{AMPEL[rk.ROT]}'>{fehler}</span>")
            self.erg = None
            return None
        erg = rk.berechnen(self.z, modell, self.db.einstellungen())
        if erg.get("fehler"):
            self.empf.setText(f"<span style='color:{AMPEL[rk.ROT]}'>{erg['fehler']}</span>")
            self.erg = None
            return None
        kopf, pos, k, tab, einst = self._lauf
        erg["gegenpruefung"] = rk.gegenpruefung(kopf, pos, erg["ergebnis"], k, tab, einst, modell)
        self.erg, self.modell = erg, modell
        self._wirtschaft_zeigen()
        self._staffel_zeigen()
        return erg

    def _wirtschaft_zeigen(self):
        erg = self.erg
        v = erg["varianten"]
        mv = erg["materialvergleich"]
        e = erg["ergebnis"]
        self.empf.setText(
            f"<b>Empfehlung: Variante {v['empfehlung']} – {rk.VARIANTE_TEXT[v['empfehlung']]}</b> mit {e['lose']} "
            f"Los(en), Selbstkosten {_eur(e['selbst'])} €, Preis {_z(e['preis_stueck'], 3)} €/Stk., Marge "
            f"{_pz(e['marge'])}. Material: <b>{mv['empfehlung']}</b> ist {_eur(mv['ersparnis'])} € günstiger. "
            + (f"Andler-Richtwert {_z(v['andler'])} Stk. " if v.get("andler") else "")
            + (f"<br><span style='color:{AMPEL[rk.GELB]}'>{erg['rest_unwirtschaftlich']}</span>"
               if erg.get("rest_unwirtschaftlich") else "")
            + (f"<br>{e['material_hinweis']}" if e.get("material_hinweis") else ""))
        posten = (("Lose", "lose", 0), ("Rüsten (je Los)", "ruesten", 2), ("Fertigung (je Stück)", "fertigung", 2),
                  ("Programmierung", "programmierung", 2), ("Material", "material", 2),
                  ("Kapitalbindung Material", "material_kapital", 2), ("Lager", "lager", 2),
                  ("Kapitalbindung Fertigteile", "kapital", 2), ("Lieferung je Abruf", "lieferung", 2),
                  ("Einmalig / Verwaltung", "einmalig", 2), ("Selbstkosten", "selbst", 2), ("Gewinn", "gewinn", 2),
                  ("Anhebung Mindestmarge", "anhebung", 2), ("Fracht", "fracht", 2), ("Netto", "netto", 2),
                  ("Preis je Stück", "preis_stueck", 3), ("Marge", "marge", None))
        zeilen = []
        for t, n, s in posten:
            zeilen.append([t] + [(_pz(v[x][n]) if s is None else _z(v[x][n], s)) + (" (gesperrt)" if v[x].get("gesperrt")
                                                                                    and n == "lose" else "")
                                 for x in (rk.A, rk.B, rk.C)])
        _fuellen(self.var_t, zeilen, rechts=(1, 2, 3))
        col = "ABC".index(v["empfehlung"]) + 1
        for r in range(self.var_t.rowCount()):
            self.var_t.item(r, col).setBackground(QColor(AMPEL_FL[rk.GRUEN]))
        _fuellen(self.fest_t, [[_z(g), str(x["lose"]), _eur(x["selbst"]), _z(x["preis_stueck"], 3), _pz(x["marge"])]
                               for g, x in v["feste"]], rechts=(0, 1, 2, 3, 4))
        gp = erg.get("gegenpruefung")
        _fuellen(self.gp_t, [[str(x["los"]), _z(x["stueck"]), _eur(x["modell"]), _eur(x["exakt"]),
                              f"{x['abweichung']:.1f} %".replace(".", ","),
                              f"{x['material_abweichung']:.1f} %".replace(".", ",")]
                             for x in (gp if isinstance(gp, list) else [])], rechts=(1, 2, 3, 4, 5))

    def festschreiben(self, *_):
        if not self.erg and not self.berechnen():
            return None
        aid = self.angebot()
        daten = dict(self.erg, angebot=dict(id=aid, preisbasis=(self.db.angebot(aid) or {}).get("preisbasis"))
                     if aid else None, eingaben=dict(positionen=self.z["positionen"], abrufe=self.z["abrufe"]))
        nr = ra.version_festschreiben(self.db, self.uid, daten, "Kalkulation festgeschrieben")
        self.laden()
        _meldung(self, f"Kalkulation als Version {nr} festgeschrieben.")
        return nr

    def preise_uebernehmen(self, *_):
        if not self.erg:
            return 0
        n = 0
        for p in self.k["positionen"]:
            x = self.erg["je_position"].get(p["pos"])
            if x and x["preis_stueck"] != p.get("preis"):
                try:
                    ra.position_aendern(self.db, self.uid, p["uid"], "preis", x["preis_stueck"],
                                        "aus Rahmenkalkulation")
                    n += 1
                except ra.RahmenFehler as e:
                    _meldung(self, str(e))
                    break
        self.laden()
        return n

    def lose_anlegen(self, *_):
        """Fertigungslose der empfohlenen Variante als Plan (nur für noch nicht geplante Abrufe)."""
        if not self.erg:
            return 0
        schon = {n for los in self.z.get("lose") or () if los.get("status") != "storniert" for n in los.get("abrufe") or ()}
        n = 0
        abr = self.erg["varianten"]["abrufe"]
        for los in self.erg["ergebnis"]["je_los"]:
            nrn = [x for i in los["abrufe"] for x in abr[i - 1].get("nr") or ()]
            if set(nrn) & schon:
                continue
            ra.los_neu(self.db, self.uid, los["datum"], los["mengen"], nrn)
            n += 1
        self.laden()
        return n

    def parameter_dialog(self, *_, werte=None):
        par = rk.parameter(self.db.einstellungen(), self.z.get("parameter"))
        if werte is None:
            d = QDialog(self)
            d.setWindowTitle("Kalkulationsparameter des Rahmens")
            form = QFormLayout(d)
            spins = {}
            titel = dict(zins="Zins [% p. a.]", lagerplatz="Lagerplatz [€ je Palette und Monat]",
                         teile_palette="Teile je Palette", einlagern="Einlagern [€ je Los]",
                         prog_wiederholung="Programmierung je weiterem Los [%]",
                         kommission_min="Kommissionieren [min je Abruf]", kommission_satz="Stundensatz Versand [€/h]",
                         verpackung="Verpackung [€ je Abruf]", abwicklung="Lieferabwicklung [€ je Abruf]",
                         verwaltung="Verwaltung [€ je Rahmen]", einmalig="Einmalig: Vorrichtung/Werkzeug [€]",
                         bestellkosten="Bestellkosten Material [€]", moq_kg="Mindestbestellmenge [kg]",
                         max_lagerdauer="Höchste Lagerdauer [Monate, 0 = ohne]",
                         gleit_schwelle="Bagatellgrenze Gleitklausel [%]")
            for n in rk.VORGABEN:
                s = QDoubleSpinBox()
                s.setRange(0, 1e7)
                s.setDecimals(2)
                s.setValue(par[n])
                form.addRow(titel.get(n, n), s)
                spins[n] = s
            staffel = QLineEdit("; ".join(f"{a:g}:{b:g}" for a, b in par["staffel"]))
            staffel.setPlaceholderText("ab kg:Rabatt %, z. B. 1000:3; 5000:6")
            form.addRow("Materialpreisstaffel", staffel)
            k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            k.accepted.connect(d.accept)
            k.rejected.connect(d.reject)
            form.addRow(k)
            if d.exec() != QDialog.Accepted:
                return None
            werte = {n: s.value() for n, s in spins.items()}
            try:
                werte["material_staffel"] = [[float(a.replace(",", ".")), float(b.replace(",", "."))]
                                             for a, b in (x.split(":") for x in staffel.text().split(";") if ":" in x)]
            except ValueError:
                _meldung(self, "Materialpreisstaffel: bitte „kg:Rabatt“ durch Semikolon getrennt.")
                return None
        werte = dict(self.z.get("parameter") or {}, **werte)
        ra.parameter_setzen(self.db, self.uid, werte, "Parameter von Hand")
        self.laden()
        return werte

    # ---------------------------------------------------------- Preisstaffel
    def _staffel(self):
        w = QWidget()
        self.staffel_t = _tabelle(("Rahmenmenge", "Szenario", "Selbstkosten €/Stk.", "Gewinn €/Stk.", "Marge",
                                   "Preis €/Stk.", "Lose", "Hinweis"))
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Gleicher Abrufrhythmus, Mengen anteilig; je Szenario die beste Losbildung. "
                             "Mindestmarge geschützt (Anhebung)."))
        lay.addWidget(self.staffel_t, 1)
        self.reiter.addTab(w, "Preisstaffel")

    def _staffel_zeigen(self):
        zeilen, farben = [], {}
        for z in self.erg.get("preisstaffel") or ():
            for i, s in enumerate(z["szenarien"]):
                if s["unter_mindestmarge"]:
                    farben[len(zeilen)] = AMPEL_FL[rk.GELB]
                zeilen.append([_z(z["menge"]) if i == 0 else "", s["name"], _z(s["selbst_stueck"], 3),
                               _z(s["gewinn_stueck"], 3), _pz(s["marge"]), _z(s["preis_stueck"], 3), str(s["lose"]),
                               "auf Mindestmarge angehoben" if s["unter_mindestmarge"] else ""])
        _fuellen(self.staffel_t, zeilen, rechts=(0, 2, 3, 4, 5, 6), farben=farben)

    # ---------------------------------------------------------- Preisbindung
    def _bindung(self):
        w = QWidget()
        self.b_modell = QComboBox()
        self.b_modell.addItems(list(rk.PREISMODELLE))
        self.b_bis = QLineEdit()
        self.b_bis.setPlaceholderText("JJJJ-MM-TT")
        self.b_anteil = QDoubleSpinBox()
        self.b_anteil.setRange(0, 100)
        self.b_anteil.setSuffix(" %")
        self.b_anteil.setToolTip("Materialanteil am Preis; 0 = aus der Kalkulation je Position")
        self.b_schwelle = QDoubleSpinBox()
        self.b_schwelle.setRange(0, 100)
        self.b_schwelle.setSuffix(" %")
        self.b_basis = QLineEdit()
        self.b_basis.setPlaceholderText("z. B. 2,50 €/kg S235 oder Index Eisen/Stahl 01/2027")
        self.b_termine = QLineEdit()
        self.b_termine.setPlaceholderText("Prüftermine JJJJ-MM-TT; …")
        speichern = QPushButton("Preisbindung speichern")
        speichern.clicked.connect(self.bindung_speichern)
        form = QFormLayout()
        for t, x in (("Modell", self.b_modell), ("gilt bis", self.b_bis), ("Materialanteil", self.b_anteil),
                     ("Bagatellgrenze", self.b_schwelle), ("Basis (Preis/Index)", self.b_basis),
                     ("Prüftermine", self.b_termine), ("", speichern)):
            form.addRow(t, x)
        hinweis = QLabel("Preisgleitklauseln vor Vertragsschluss rechtlich prüfen lassen (Preisklauselgesetz, AGB).")
        hinweis.setStyleSheet("color:#5B6773")
        self.alt_kg = QDoubleSpinBox()
        self.alt_kg.setRange(0, 1000)
        self.alt_kg.setDecimals(3)
        self.alt_kg.setValue(2.5)
        self.neu_kg = QDoubleSpinBox()
        self.neu_kg.setRange(0, 1000)
        self.neu_kg.setDecimals(3)
        self.neu_kg.setValue(2.9)
        rechnen_k = QPushButton("Auswirkung berechnen")
        rechnen_k.clicked.connect(self.auswirkung)
        vorschlag_k = QPushButton("Preisänderung vorschlagen")
        vorschlag_k.clicked.connect(self.vorschlagen)
        zeile = QHBoxLayout()
        for x in (QLabel("Materialpreis alt €/kg"), self.alt_kg, QLabel("neu €/kg"), self.neu_kg, rechnen_k,
                  vorschlag_k):
            zeile.addWidget(x)
        zeile.addStretch(1)
        self.aus_text = QLabel()
        self.aus_text.setWordWrap(True)
        self.aus_text.setTextFormat(Qt.RichText)
        self.aus_t = _tabelle(("Pos.", "Offen", "Preis €", "Material alt €", "Material neu €", "Differenz €",
                               "Gewinn alt €", "Gewinn neu €", "Materialanteil", "Gleitpreis €"))
        self.vor_t = _tabelle(("Vorgeschlagen", "Von", "Neue Preise", "Grund", "Status", "Entschieden"))
        vk = QHBoxLayout()
        for t, f in (("Freigeben", self.freigeben), ("Ablehnen", self.ablehnen)):
            b = QPushButton(t)
            b.clicked.connect(f)
            vk.addWidget(b)
        vk.addStretch(1)
        lay = QVBoxLayout(w)
        lay.addLayout(form)
        lay.addWidget(hinweis)
        lay.addLayout(zeile)
        lay.addWidget(self.aus_text)
        lay.addWidget(self.aus_t, 1)
        lay.addWidget(QLabel("Preisänderungen (gelten erst nach Freigabe):"))
        lay.addWidget(self.vor_t)
        lay.addLayout(vk)
        self.reiter.addTab(w, "Preisbindung")

    def _bindung_laden(self):
        b = self.z.get("preisbindung") or {}
        self.b_modell.setCurrentText(b.get("modell") or rk.FEST_LAUFZEIT)
        self.b_bis.setText(b.get("bis") or "")
        self.b_anteil.setValue(float(b.get("anteil") or 0))
        self.b_schwelle.setValue(float(b.get("schwelle") or rk.VORGABEN["gleit_schwelle"]))
        self.b_basis.setText(b.get("basis") or "")
        self.b_termine.setText("; ".join(b.get("pruef_termine") or ()))
        _fuellen(self.vor_t, [[_zeit(v.get("am")), v.get("wer") or "",
                               ", ".join(f"{p}: {_z(x, 2)} €" for p, x in (v.get("preise") or {}).items()),
                               v.get("bemerkung") or "", v.get("status"),
                               _zeit((v.get("entschieden") or {}).get("am"))] for v in self.z.get("vorschlaege") or ()])

    def bindung_speichern(self, *_):
        werte = dict(modell=self.b_modell.currentText(), bis=self.b_bis.text().strip() or None,
                     anteil=self.b_anteil.value(), schwelle=self.b_schwelle.value(),
                     basis=self.b_basis.text().strip() or None,
                     pruef_termine=[t.strip() for t in self.b_termine.text().split(";") if t.strip()])
        ra.preisbindung_setzen(self.db, self.uid, werte)
        self.laden()

    def auswirkung(self, *_, faktor=None):
        v = self.z.get("version")
        if not v:
            self.aus_text.setText("Bitte zuerst die Kalkulation festschreiben (Reiter Wirtschaftlichkeit).")
            return None
        if faktor is None:
            alt = self.alt_kg.value()
            faktor = self.neu_kg.value() / alt if alt else 1.0
        offen = [dict(pos=p["pos"], preis=p.get("preis"), offen=p["offen"]) for p in self.k["positionen"]]
        a = rk.auswirkung(offen, v["je_position"], faktor, self.z.get("preisbindung"),
                          (v.get("modell") or {}).get("skonto") or 0.0)
        self.auswirkung_erg = a
        self.aus_text.setText(
            f"Materialpreis {(faktor - 1) * 100:+.1f} % auf die offene Restmenge: Materialkosten {_eur(a['material_alt'])} → "
            f"{_eur(a['material_neu'])} € (<b>{_eur(a['differenz'])} €</b>), Selbstkosten {_eur(a['selbst_alt'])} → "
            f"{_eur(a['selbst_neu'])} €, Gewinn {_eur(a['gewinn_alt'])} → <b>{_eur(a['gewinn_neu'])} €</b>, Marge "
            f"{_pz(a['marge_alt'])} → {_pz(a['marge_neu'])}. {a['text']}. "
            + ("<b>Anpassung fällig</b> (über der Bagatellgrenze)." if a["faellig"] else
               "Vertragspreis bleibt (gebunden oder unter der Bagatellgrenze).")
            + " Vertragspreise ändern sich nur nach Freigabe.")
        _fuellen(self.aus_t, [[z["pos"], _z(z["offen"]), _z(z["preis"], 2), _eur(z["material_alt"]),
                               _eur(z["material_neu"]), _eur(z["differenz"]), _eur(z["gewinn_alt"]),
                               _eur(z["gewinn_neu"]), _pz(z["anteil"]), _z(z["preis_neu"], 2)] for z in a["zeilen"]],
                 rechts=tuple(range(1, 10)))
        return a

    def vorschlagen(self, *_):
        a = self.auswirkung_erg or self.auswirkung()
        if not a:
            return None
        u = ra.preis_vorschlagen(self.db, self.uid, a["vorschlag"],
                                 f"Materialpreis {(a['faktor'] - 1) * 100:+.1f} % ({a['text']})",
                                 ab=datetime.date.today().isoformat(),
                                 auswirkung={n: a[n] for n in ("differenz", "gewinn_alt", "gewinn_neu", "faktor")})
        self.laden()
        return u

    def _vorschlag_gewaehlt(self):
        r = self.vor_t.currentRow()
        v = self.z.get("vorschlaege") or []
        return v[r] if 0 <= r < len(v) else next((x for x in v if x.get("status") == "offen"), None)

    def freigeben(self, *_):
        v = self._vorschlag_gewaehlt()
        if v:
            try:
                ra.preis_freigeben(self.db, self.uid, v["uid"])
            except ra.RahmenFehler as e:
                _meldung(self, str(e))
        self.laden()

    def ablehnen(self, *_):
        v = self._vorschlag_gewaehlt()
        if v:
            ra.preis_ablehnen(self.db, self.uid, v["uid"])
        self.laden()

    # ---------------------------------------------------------- Material und Lose
    def _material(self):
        w = QWidget()
        self.mat_text = QLabel()
        self.mat_text.setWordWrap(True)
        self.mat_t = _tabelle(("Datum", "Art", "kg", "€", "Lieferant / Los", "Bemerkung"))
        self.lose_t = _tabelle(("Fertigung am", "Für Abrufe", "Mengen", "Status", "Gefertigt"))
        mk = QHBoxLayout()
        for t, f in (("Materialkauf erfassen …", self.material_kauf), ("Verbrauch erfassen …", self.material_verbrauch),
                     ("Los gefertigt", self.los_fertig)):
            b = QPushButton(t)
            b.clicked.connect(f)
            mk.addWidget(b)
        mk.addStretch(1)
        lay = QVBoxLayout(w)
        lay.addWidget(self.mat_text)
        lay.addWidget(self.mat_t, 1)
        lay.addWidget(QLabel("Fertigungslose:"))
        lay.addWidget(self.lose_t, 1)
        lay.addLayout(mk)
        self.reiter.addTab(w, "Material und Lose")

    def _material_laden(self):
        m = self.k["material"]
        self.mat_text.setText(
            f"Materialkonto dieses Rahmens (kein allgemeines Restelager): gekauft {_z(m['gekauft_kg'], 1)} kg "
            f"({_eur(m['gekauft_eur'])} €), verbraucht {_z(m['verbraucht_kg'], 1)} kg, Bestand {_z(m['bestand_kg'], 1)} kg. "
            f"Bedarf offen {_z(m['bedarf_offen_kg'], 1)} kg, noch zu kaufen {_z(m['noch_kaufen_kg'], 1)} kg.")
        mat = self.z.get("material") or {}
        zeilen = [[_datum(x.get("datum")), "Kauf", _z(x.get("kg"), 1), _eur(x.get("eur")), x.get("lieferant") or "", ""]
                  for x in mat.get("kaeufe") or ()]
        zeilen += [[_datum(x.get("datum")), "Verbrauch", _z(-float(x.get("kg") or 0), 1), "", x.get("los") or "", ""]
                   for x in mat.get("verbrauch") or ()]
        _fuellen(self.mat_t, zeilen, rechts=(2, 3))
        _fuellen(self.lose_t, [[_datum(los.get("datum")), ", ".join(map(str, los.get("abrufe") or ())),
                                ", ".join(f"{p}: {_z(q)}" for p, q in (los.get("mengen") or {}).items()), los.get("status"),
                                ", ".join(f"{p}: {_z(q)}" for p, q in (los.get("gefertigt") or {}).items())]
                               for los in self.z.get("lose") or ()])

    def material_kauf(self, *_, kg=None, eur=None, lieferant=None):
        if kg is None:
            kg, ok = QInputDialog.getDouble(self, "Materialkauf", "Menge [kg]:", self.k["material"]["noch_kaufen_kg"], 0,
                                            1e8, 1)
            if not ok:
                return
            eur, ok = QInputDialog.getDouble(self, "Materialkauf", "Betrag [€]:", 0, 0, 1e9, 2)
            if not ok:
                return
            lieferant, _ = QInputDialog.getText(self, "Materialkauf", "Lieferant:")
        ra.material_kauf(self.db, self.uid, kg, eur, lieferant=lieferant or None)
        self.laden()

    def material_verbrauch(self, *_, kg=None):
        if kg is None:
            kg, ok = QInputDialog.getDouble(self, "Materialverbrauch", "Verbraucht [kg]:", 0, 0, 1e8, 1)
            if not ok:
                return
        ra.material_verbrauch(self.db, self.uid, kg)
        self.laden()

    def los_fertig(self, *_, los=None):
        r = self.lose_t.currentRow()
        lose = self.z.get("lose") or []
        los = los or (lose[r] if 0 <= r < len(lose) else next((x for x in lose if x.get("status") == "geplant"), None))
        if not los:
            return
        ra.los_gefertigt(self.db, self.uid, los["uid"], los.get("mengen"))
        self.laden()

    # ---------------------------------------------------------- Protokoll
    def _protokoll(self):
        w = QWidget()
        self.prot_t = _tabelle(("Zeit", "Benutzer", "Rechner", "Was", "Detail"))
        self.prot_info = QLabel()
        lay = QVBoxLayout(w)
        lay.addWidget(self.prot_info)
        lay.addWidget(self.prot_t, 1)
        self.reiter.addTab(w, "Protokoll")

    def _protokoll_laden(self):
        zeilen = [[_zeit(t), wer, rechner, was, det] for t, wer, rechner, was, det in ra.protokoll(self.db, self.uid)]
        _fuellen(self.prot_t, zeilen[::-1])
        falsch = ra.pruefen(self.db, self.uid)
        konf = self.z.get("konflikte") or []
        self.prot_info.setText(
            ("Alle Einträge unverändert (Prüfsumme in Ordnung)." if not falsch else
             f"ACHTUNG: {len(falsch)} Eintrag/Einträge nachträglich geändert.")
            + (f" {len(konf)} gleichzeitige Änderung(en): " + "; ".join(
                f"{k['feld']} von {k.get('wer') or '?'} ({_zeit(k['am'])})" for k in konf) if konf else ""))

    # ---------------------------------------------------------- Abschluss
    def _abschluss(self):
        w = QWidget()
        self.abs_text = QLabel()
        self.abs_text.setWordWrap(True)
        self.abs_t = _tabelle(("Pos.", "Menge", "Abgerufen", "Geliefert", "Nicht abgerufen", "Gefertigt", "Auf Lager",
                               "Lieferverpflichtung", "Umsatz €", "Restwert €"))
        lay = QVBoxLayout(w)
        lay.addWidget(self.abs_text)
        lay.addWidget(self.abs_t, 1)
        self.reiter.addTab(w, "Abschluss")

    def _abschluss_laden(self):
        a = rk.abschluss(self.z)
        _fuellen(self.abs_t, [[z["pos"], _z(z["menge"]), _z(z["abgerufen"]), _z(z["geliefert"]), _z(z["nicht_abgerufen"]),
                               _z(z["gefertigt"]), _z(z["bestand"]), _z(z["verpflichtung"]), _eur(z["umsatz"]),
                               _eur(z["restwert"])] for z in a["zeilen"]], rechts=tuple(range(1, 10)))
        self.abs_text.setText(f"Umsatz geliefert {_eur(a['umsatz'])} €, Restwert {_eur(a['restwert'])} €, "
                              f"Abrufe {a['abrufe_ist']} von {a['abrufe_plan']} geliefert, {a['storniert']} storniert."
                              + ("<br>" + "<br>".join("• " + h for h in a["hinweise"]) if a["hinweise"] else ""))
        self.abs_text.setTextFormat(Qt.RichText)

    # ---------------------------------------------------------- Dokumente
    def dokument(self, art, pfad=None):
        from . import rahmen_pdf
        if art in rahmen_pdf.BRAUCHT_RECHNUNG and not self.erg and not self.berechnen():
            _meldung(self, "Bitte zuerst die Wirtschaftlichkeit berechnen (Angebot verknüpft?).")
            return None
        if pfad is None:
            vorschlag = f"{self.z.get('nummer')}_{art}.pdf"
            pfad, _ = QFileDialog.getSaveFileName(self, "Dokument speichern", vorschlag, "PDF (*.pdf)")
            if not pfad:
                return None
        rahmen_pdf.schreiben(Path(pfad), art, self.z, self.erg, self.db.einstellungen())
        if art == "kunde":
            gefunden = rahmen_pdf.kunde_pruefen(pfad)
            if gefunden:
                _meldung(self, "Achtung, interne Begriffe im Kundenangebot: " + ", ".join(gefunden))
        return pfad
