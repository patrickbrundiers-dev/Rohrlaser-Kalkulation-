"""Fenster „Schnellpreis …“ (Vorschlag V5, 31.10.2026, schnellpreis.py): Richtpreis für Telefonanfragen.

Eine Zeile wie in der Schnellzeile („QR 40x3 S235 1250 20“ = Profil, Werkstoff, Länge, Stückzahl), dazu Bohrungen,
weitere Konturen und Enden; Enter rechnet. Ergebnis: Preis je Stück, gesamt und eine kleine Staffel. „Als Angebot
übernehmen“ legt ein neues Angebot mit dieser Position an und öffnet es."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from . import schnellpreis, schnellzeile
from .ausgabe import euro_text

ENDEN = ("beide gerade", "ein Ende Gehrung 45°", "beide Enden Gehrung 45°")


class SchnellpreisDialog(QDialog):
    def __init__(self, fenster):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.ergebnis = None
        self.setWindowTitle("Schnellpreis")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        hilfe = QLabel("Richtpreis für eine Anfrage am Telefon: gerechnet wie ein Angebot (Vorgaben eines neuen "
                       "Angebots, Stangen optimiert), gespeichert wird nichts.")
        hilfe.setWordWrap(True)
        lay.addWidget(hilfe)
        form = QFormLayout()
        self.zeile = QLineEdit()
        self.zeile.setPlaceholderText("Profil Werkstoff Länge Stück, z. B. QR 40x3 S235 1250 20")
        self.zeile.returnPressed.connect(lambda: self.rechnen())
        self.erkannt = QLabel()
        self.erkannt.setStyleSheet("color: #666;")
        self.zeile.textChanged.connect(self._vorschau)
        form.addRow("Teil", self.zeile)
        form.addRow("", self.erkannt)
        self.bohrungen, self.bohr_d = QSpinBox(), QDoubleSpinBox()
        self.bohrungen.setRange(0, 999)
        self.bohr_d.setRange(0, 500)
        self.bohr_d.setDecimals(1)
        self.bohr_d.setSuffix(" mm")
        self.bohr_d.setValue(8.5)
        b = QHBoxLayout()
        b.addWidget(self.bohrungen)
        b.addWidget(QLabel("Stück, Ø"))
        b.addWidget(self.bohr_d)
        b.addStretch(1)
        form.addRow("Bohrungen", b)
        self.konturen, self.kontur_mm = QSpinBox(), QDoubleSpinBox()
        self.konturen.setRange(0, 999)
        self.kontur_mm.setRange(0, 1000000)
        self.kontur_mm.setDecimals(0)
        self.kontur_mm.setSuffix(" mm je Teil")
        self.kontur_mm.setToolTip("Schnittlänge aller weiteren Konturen zusammen (Langlöcher, Ausschnitte)")
        k = QHBoxLayout()
        k.addWidget(self.konturen)
        k.addWidget(QLabel("Stück, zusammen"))
        k.addWidget(self.kontur_mm)
        k.addStretch(1)
        form.addRow("Weitere Konturen", k)
        self.enden = QComboBox()
        self.enden.addItems(ENDEN)
        form.addRow("Enden", self.enden)
        self.kunde = QComboBox()
        self.kunde.addItem("– ohne Kunde –", None)
        for z in sorted(self.db.zeilen("kunden"), key=lambda z: str(z.get("name") or "").lower()):
            self.kunde.addItem(f"{z.get('name')} ({z.get('kundennr')})", z.get("kundennr"))
        self.kunde.setToolTip("Mit Kunde gelten seine Vorgaben (Maschine, Gewinn …) wie bei einem neuen Angebot")
        form.addRow("Kunde", self.kunde)
        lay.addLayout(form)
        self.preis = QLabel("–")
        f = self.preis.font()
        f.setPointSizeF(f.pointSizeF() * 1.6)
        f.setBold(True)
        self.preis.setFont(f)
        self.preis.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.preis)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.staffel = QTableWidget(0, 3)
        self.staffel.setHorizontalHeaderLabels(("Stückzahl", "€ je Stück", "€ gesamt"))
        self.staffel.verticalHeader().setVisible(False)
        self.staffel.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.staffel.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.staffel, 1)
        knoepfe = QHBoxLayout()
        rechnen = QPushButton("Rechnen")
        rechnen.setObjectName("primaer")
        rechnen.clicked.connect(lambda: self.rechnen())
        self.uebernehmen_knopf = QPushButton("Als Angebot übernehmen")
        self.uebernehmen_knopf.setEnabled(False)
        self.uebernehmen_knopf.clicked.connect(lambda: self.uebernehmen())
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.reject)
        knoepfe.addStretch(1)
        for w in (rechnen, self.uebernehmen_knopf, zu):
            w.setAutoDefault(False)
            knoepfe.addWidget(w)
        lay.addLayout(knoepfe)

    # ------------------------------------------------------------------ Eingabe
    def _bevorzugt(self):
        v = self.db.einstellung("step_werkstoff")
        return [v] if v else []

    def gelesen(self):
        k = self.db.kontext()
        return schnellzeile.zeile_lesen(self.zeile.text(), k.profile, k.werkstoffe, self._bevorzugt())

    def _vorschau(self, *_):
        z = self.gelesen()
        self.erkannt.setText(schnellzeile.vorschau(z, lambda x: f"{x:g}".replace(".", ",")) if self.zeile.text().strip()
                             else "")

    def eingabe(self):
        z = self.gelesen()
        werkstoff = z.get("werkstoff_id") or (self._bevorzugt() or [None])[0]
        return dict(profil_id=z.get("profil_id"), werkstoff_id=werkstoff, laenge=z.get("laenge"),
                    stueck=z.get("stueck") or 1, bohrungen=self.bohrungen.value(), bohr_d=self.bohr_d.value(),
                    konturen=self.konturen.value(), kontur_mm=self.kontur_mm.value(),
                    gehrung=self.enden.currentIndex())

    # ------------------------------------------------------------------ Aktionen
    def rechnen(self):
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            erg = schnellpreis.berechnen(self.db, self.eingabe(), kundennr=self.kunde.currentData())
        finally:
            QApplication.restoreOverrideCursor()
        self.ergebnis = erg
        h = erg.get("haupt") or {}
        fehler = erg.get("fehler") or h.get("fehler")
        self.uebernehmen_knopf.setEnabled(not erg.get("fehler"))
        self.staffel.setRowCount(0)
        if fehler:
            self.preis.setText("–")
            self.info.setText(f"Kein Preis: {fehler}")
            return erg
        self.preis.setText(f"{euro_text(h['preis_stueck'])} € je Stück")
        p = erg["position"]
        self.info.setText(f"{h['stueck']} Stück, {euro_text(h['verkauf'])} € netto gesamt · {h['stangen']} Stange(n) · "
                          f"Schneidweg {p['schneidweg']:.0f} mm, {p['einstiche']} Einstiche je Teil · Maschine "
                          f"{erg['kopf'].get('maschine') or '–'}" + ("\n" + "; ".join(h["hinweise"])
                                                                     if h.get("hinweise") else ""))
        zeilen = sorted([h] + [s for s in erg["staffel"] if not s.get("fehler")], key=lambda s: s["stueck"])
        self.staffel.setRowCount(len(zeilen))
        for r, s in enumerate(zeilen):
            for c, t in enumerate((str(s["stueck"]), euro_text(s["preis_stueck"]), euro_text(s["verkauf"]))):
                it = QTableWidgetItem(t)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if s is h:
                    fnt = it.font()
                    fnt.setBold(True)
                    it.setFont(fnt)
                self.staffel.setItem(r, c, it)
        return erg

    def uebernehmen(self):
        """Neues Angebot mit dieser Position anlegen, optimieren und öffnen. Ergebnis: Angebot-ID oder None."""
        if not self.ergebnis or self.ergebnis.get("fehler"):
            return None
        kopf = {n: v for n, v in (("kundennr", self.kunde.currentData()),) if v}
        i = self.db.angebot_neu(kopf)
        p = dict(self.ergebnis["position"])
        p.pop("bezeichnung", None)
        self.db.position_neu(i, p)
        self.f.angebote.neu_laden()
        seite = self.f.angebot_oeffnen(i)
        if seite is not None:
            seite.optimieren(automatisch=True)
        self.f.meldung(f"Angebot {self.db.angebot(i)['nummer']} aus dem Schnellpreis angelegt.")
        self.accept()
        return i
