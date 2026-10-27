"""Reiter „Lager“ (Materialbestand und Reststücke, lager.py) und Fenster „Material aus Lager“ eines beauftragten
Angebots. Nur mit der Einstellung 'lager_aktiv' sichtbar."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import lager, rechnen
from .stammdaten import zahl_als_text, zahl_aus_text

SPALTEN = (("Kennung", "kennung"), ("Art", "art"), ("Profil-ID", "profil"), ("Werkstoff-ID", "werkstoff"),
           ("Oberfläche", "oberflaeche"), ("Länge [mm]", "laenge"), ("Bestand", "anzahl"), ("reserviert", "reserviert"),
           ("verfügbar", "verfuegbar"), ("Charge", "charge"), ("Lagerort", "lagerort"), ("Herkunft", "herkunft"))
BUCHUNG_SPALTEN = (("Zeit", "zeit"), ("Buchung", "art"), ("Kennung", "kennung"), ("Angebot", "nummer"),
                   ("Anzahl", "anzahl"), ("Länge [mm]", "laenge"), ("Text", "text"), ("Kürzel", "kuerzel"))
PLAN_SPALTEN = (("Stange", "nr"), ("Profil-ID", "profil"), ("Werkstoff-ID", "werkstoff"), ("Länge Plan [mm]", "stange"),
                ("Bedarf [mm]", "bedarf"), ("Quelle", "quelle"), ("Kennung", "kennung"), ("Länge Posten [mm]", "laenge"),
                ("Charge", "charge"), ("Lagerort", "lagerort"), ("Neukauf gespart [€]", "ersparnis"))


def _text(w):
    if isinstance(w, float):
        return zahl_als_text(w, 2 if abs(w - round(w)) > 1e-9 and abs(w) < 1000 else 0)
    return "" if w is None else str(w)


def _fuellen(tabelle, spalten, zeilen):
    tabelle.setRowCount(len(zeilen))
    for r, z in enumerate(zeilen):
        for c, (_, name) in enumerate(spalten):
            it = QTableWidgetItem(_text(z.get(name)))
            if isinstance(z.get(name), (int, float)):
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tabelle.setItem(r, c, it)


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels([s for s, _ in spalten])
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


class ZugangDialog(QDialog):
    """Zugang erfassen: Art, Profil, Werkstoff, Oberfläche, Länge, Anzahl, Charge, Lagerort, Bemerkung."""

    def __init__(self, parent, db):
        super().__init__(parent)
        self.setWindowTitle("Lager: Zugang")
        self.db = db
        k = db.kontext()
        form = QFormLayout(self)
        self.art = QComboBox()
        self.art.addItems(["Stange"] + (["Rest"] if lager.reste_aktiv(db) else []))
        self.profil = QComboBox()
        self.profil.setEditable(True)
        self.profil.addItems(sorted(k.profile))
        self.werkstoff = QComboBox()
        self.werkstoff.setEditable(True)
        self.werkstoff.addItems(sorted(k.werkstoffe))
        self.oberflaeche = QLineEdit()
        self.laenge = QLineEdit("6000")
        self.anzahl = QSpinBox()
        self.anzahl.setRange(1, 10000)
        self.charge, self.lagerort, self.bemerkung = QLineEdit(), QLineEdit(), QLineEdit()
        for titel, w in (("Art", self.art), ("Profil-ID", self.profil), ("Werkstoff-ID", self.werkstoff),
                         ("Oberfläche (leer = roh)", self.oberflaeche), ("Länge [mm]", self.laenge),
                         ("Anzahl", self.anzahl), ("Charge", self.charge), ("Lagerort", self.lagerort),
                         ("Bemerkung", self.bemerkung)):
            form.addRow(titel, w)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #B42318;")
        form.addRow(self.fehler)
        kn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        kn.accepted.connect(self.speichern)
        kn.rejected.connect(self.reject)
        form.addRow(kn)
        self.ids = []

    def speichern(self):
        try:
            laenge = zahl_aus_text(self.laenge.text())
            self.ids = lager.zugang(self.db, self.art.currentText(), self.profil.currentText(),
                                    self.werkstoff.currentText(), laenge, self.anzahl.value(), self.oberflaeche.text(),
                                    self.charge.text(), self.lagerort.text(), "Zugang", self.bemerkung.text())
        except (ValueError, PermissionError) as e:
            self.fehler.setText(str(e))
            return
        self.accept()


class LagerSeite(QWidget):
    titel = "Lager"

    def __init__(self, fenster):
        super().__init__()
        self.f, self.db = fenster, fenster.db
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen nach Kennung, Profil, Werkstoff, Charge, Lagerort …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self.neu_laden)
        oben = QHBoxLayout()
        oben.addWidget(self.suche, 1)
        for text, ziel, tip in (("Zugang …", self.zugang, "Stangen oder Reststücke ins Lager buchen"),
                                ("Bestand korrigieren …", self.korrigieren, "Bestand des markierten Postens setzen "
                                 "(Inventur)"),
                                ("Ausbuchen …", self.ausbuchen, "Markierten Posten ganz ausbuchen (Schrott, verkauft)")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            oben.addWidget(b)
        self.tabelle = _tabelle(SPALTEN)
        self.buchungen = _tabelle(BUCHUNG_SPALTEN)
        self.reiter = QTabWidget()
        self.reiter.addTab(self.tabelle, "Bestand")
        self.reiter.addTab(self.buchungen, "Buchungen")
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.reiter, 1)
        lay.addWidget(self.info)
        self.zeilen = []
        self.neu_laden()

    def neu_laden(self, *_):
        such = self.suche.text().strip().lower()
        zeilen = lager.bestand(self.db)
        if such:
            zeilen = [z for z in zeilen if such in " ".join(str(z.get(n) or "") for n in
                                                        ("kennung", "profil", "werkstoff", "charge", "lagerort",
                                                         "herkunft")).lower()]
        self.zeilen = zeilen
        _fuellen(self.tabelle, SPALTEN, zeilen)
        _fuellen(self.buchungen, BUCHUNG_SPALTEN, lager.buchungen(self.db)[:2000])
        reste = sum(1 for z in zeilen if z["art"] == "Rest")
        self.info.setText(f"{len(zeilen)} Posten, davon {reste} Reststücke; reserviert "
                          f"{sum(z['reserviert'] for z in zeilen)} Stück. "
                          + ("Reststücke werden verwaltet." if lager.reste_aktiv(self.db) else
                             "Reststücke sind aus (Einstellungen → Lager und Fertigung)."))

    def _gewaehlt(self):
        r = self.tabelle.currentRow()
        return self.zeilen[r] if 0 <= r < len(self.zeilen) else None

    def zugang(self, dialog=None):
        d = ZugangDialog(self, self.db)
        if not (dialog(d) if dialog else d.exec() == QDialog.Accepted) or not d.ids:
            return None
        self.neu_laden()
        self.f.meldung(f"Lager: {len(d.ids)} Posten gebucht.")
        return d.ids

    def korrigieren(self, anzahl=None, grund=None):
        z = self._gewaehlt()
        if z is None:
            return self.f.meldung("Lager: bitte einen Posten markieren.", fehler=True)
        if anzahl is None:
            anzahl, ok = QInputDialog.getInt(self, "Bestand korrigieren", f"{z['kennung']}: neuer Bestand",
                                             z["anzahl"], 0, 1 if z["art"] == "Rest" else 100000)
            if not ok:
                return None
        if grund is None:
            grund, ok = QInputDialog.getText(self, "Bestand korrigieren", "Grund (z. B. Inventur):")
            if not ok:
                return None
        try:
            lager.korrigieren(self.db, z["id"], anzahl, grund)
        except (ValueError, PermissionError) as e:
            return self.f.meldung(str(e), fehler=True)
        self.neu_laden()
        self.f.meldung(f"Lager: {z['kennung']} auf {anzahl} gesetzt.")
        return True

    def ausbuchen(self, grund=None):
        z = self._gewaehlt()
        return self.korrigieren(0, grund) if z is not None else self.korrigieren()


class LagerplanDialog(QDialog):
    """Material eines beauftragten Angebots aus dem Lager: Plan zeigen, reservieren, freigeben, Verbrauch buchen und
    stornieren. s = Angebotsseite (db, id, kopf, positionen, ergebnis, k, tabellen)."""

    def __init__(self, s):
        super().__init__(s)
        self.s, self.db = s, s.db
        self.setWindowTitle(f"Material aus Lager – {s.kopf.get('nummer') or ''}")
        self.resize(1100, 520)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.tabelle = _tabelle(PLAN_SPALTEN)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        kn = QHBoxLayout()
        self.knoepfe = {}
        for text, ziel in (("Neu planen", self.neu_planen), ("Reservieren", self.reservieren),
                           ("Reservierung freigeben", self.freigeben), ("Verbrauch buchen", self.verbrauchen),
                           ("Verbrauch stornieren …", self.stornieren)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            kn.addWidget(b)
            self.knoepfe[text] = b
        kn.addStretch(1)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        kn.addWidget(zu)
        lay = QVBoxLayout(self)
        lay.addWidget(self.status)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(self.summe)
        lay.addLayout(kn)
        self.meldung = ""
        self.plan = None
        self.neu_planen(laden=True)

    def _werte(self):
        s = self.s
        return rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)

    def neu_planen(self, laden=False):
        a = lager.auftrag(self.db, self.s.id)
        if laden and a and a["status"] in ("reserviert", "verbraucht") and not lager.veraltet(self.db, self.s.id,
                                                                                              self.s.ergebnis):
            self.plan = a["plan"]
        else:
            self.plan = lager.planen(self.db, self.s.id, self.s.ergebnis, self._werte())
        self._zeigen()

    def _zeigen(self):
        a = lager.auftrag(self.db, self.s.id)
        st = a["status"] if a else "nicht geplant"
        veraltet = lager.veraltet(self.db, self.s.id, self.s.ergebnis)
        self.status.setText(f"<b>Lagerauftrag: {st}</b>"
                            + (" – <b style='color:#B42318'>das Angebot ist seit der Reservierung anders optimiert: "
                               "bitte neu planen und reservieren.</b>" if veraltet else "")
                            + "<br>Die Teile liegen genau wie im Schnittplan; ein Posten wird nur genommen, wenn er "
                            "mindestens so lang ist wie der Bedarf der Stange (Endbeschnitt + Teile + Schnitte + "
                            "Greiferrest). Die Kalkulation des Angebots ändert sich dadurch nicht.")
        p = self.plan
        _fuellen(self.tabelle, PLAN_SPALTEN, p["stangen"])
        self.summe.setText(f"Aus dem Lager: {p['aus_lager']} Stangen (Lagerwert {zahl_als_text(p['lagerwert'], 2)} €), "
                           f"Neukauf: {p['neukauf']} Stangen. Neukauf gespart: {zahl_als_text(p['ersparnis'], 2)} €."
                           + (f" Neue Reststücke: {len(p.get('neue_reste') or ())}." if p.get("neue_reste") else ""))
        self.knoepfe["Reservieren"].setEnabled(st != "verbraucht" and p["aus_lager"] > 0)
        self.knoepfe["Reservierung freigeben"].setEnabled(st == "reserviert")
        self.knoepfe["Verbrauch buchen"].setEnabled(st == "reserviert" and not veraltet)
        self.knoepfe["Verbrauch stornieren …"].setEnabled(st == "verbraucht")

    def _tun(self, f, text):
        try:
            erg = f()
        except (ValueError, PermissionError) as e:
            self.meldung = str(e)
            self.s.f.meldung(str(e), fehler=True)
            self._zeigen()
            return None
        self.meldung = text if not isinstance(erg, list) else text + (f" Neue Reststücke: {', '.join(erg)}." if erg else "")
        self.s.f.meldung(self.meldung)
        self.neu_planen(laden=True)
        if hasattr(self.s.f, "lager"):
            self.s.f.lager.neu_laden()
        return True

    def reservieren(self):
        return self._tun(lambda: lager.reservieren(self.db, self.s.id, self.s.kopf.get("nummer"), self.plan),
                         "Lager: Material reserviert.")

    def freigeben(self):
        return self._tun(lambda: lager.freigeben(self.db, self.s.id, "von Hand"), "Lager: Reservierung freigegeben.")

    def verbrauchen(self):
        return self._tun(lambda: lager.verbrauchen(self.db, self.s.id), "Lager: Verbrauch gebucht.")

    def stornieren(self, grund=None):
        if grund is None:
            grund, ok = QInputDialog.getText(self, "Verbrauch stornieren", "Grund:")
            if not ok:
                return None
        return self._tun(lambda: lager.verbrauch_stornieren(self.db, self.s.id, grund), "Lager: Verbrauch storniert.")
