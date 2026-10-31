"""Fenster „Kollegen im gemeinsamen Ordner“ (Datei-Menü, Patrick 31.10.2026, Paket B Baustein 6).

Je Mitarbeiter: Kürzel, Name, ob er gerade da ist (Lebenszeichen, sonst „zuletzt vor …“), Rechner, Programmversion,
letzter Abgleich, Zahl der Angebote, gerade geöffnete Angebote, eigene Vorgänge an ihn, die er noch nicht umgesetzt
hat, und die Abweichung seiner PC-Uhr. Der eigene Arbeitsplatz steht oben."""
import datetime
import socket

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import VERSION, stil, teilen

SPALTEN = ("Kürzel", "Name", "Status", "Rechner", "Version", "Letzter Abgleich", "Angebote", "Gerade geöffnet",
           "Offene Vorgänge an ihn", "PC-Uhr")


def _datum(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso or ""))
    except ValueError:
        return None


def zeilen(db):
    """Zeilen der Übersicht: [dict(kuerzel, werte (Texte je Spalte), online, ich)], der eigene Platz zuerst."""
    ich = teilen.kuerzel(db)
    puls = teilen.lebenszeichen(db)
    vorgaenge = teilen.offene_vorgaenge(db)
    offen = {}
    for nummer, (k, _seit) in teilen.kollegen_offen(db).items():
        offen.setdefault(k, []).append(nummer)
    out = []
    jetzt = datetime.datetime.now()
    for k, m in sorted(teilen.mitarbeiter(db).items(), key=lambda km: (km[0] != ich, km[0])):
        p = puls.get(k)
        if k == ich:
            status, online = "● hier", True
            version, rechner = VERSION, socket.gethostname()
            stand = _datum(db.einstellung("teilen_geschrieben"))
            anzahl = db.con.execute("SELECT COUNT(*) FROM angebote WHERE fremd IS NULL OR fremd=''").fetchone()[0]
            uhr = teilen.uhr_abweichung(db)
        else:
            online = bool(p and p["online"])
            if online:
                status = "● da"
            elif p:
                status = "zuletzt " + teilen.zuletzt_text(p["vor_s"])
            else:
                stand_ = _datum(m.get("stand"))
                status = ("zuletzt " + teilen.zuletzt_text((jetzt - stand_).total_seconds())) if stand_ else "–"
            version = (p or {}).get("version") or m.get("version") or ""
            rechner = (p or {}).get("rechner") or m.get("rechner") or ""
            stand = _datum(m.get("stand"))
            anzahl = m.get("angebote")
            uhr = m.get("uhr_abweichung")
        uhr_text = "" if not isinstance(uhr, (int, float)) else (
            "stimmt" if abs(uhr) < teilen.UHR_KORREKTUR_AB else teilen.uhr_text(uhr))
        werte = [k + (" (ich)" if k == ich else ""), m.get("name") or "", status, rechner, version,
                 f"{stand:%d.%m.%Y %H:%M}" if stand else "", "" if anzahl is None else str(anzahl),
                 ", ".join(sorted(offen.get(k, []))), str(vorgaenge.get(k) or ""), uhr_text]
        out.append(dict(kuerzel=k, werte=werte, online=online, ich=k == ich))
    return out


class KollegenDialog(QDialog):
    def __init__(self, fenster):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.setWindowTitle("Kollegen im gemeinsamen Ordner")
        self.resize(1080, 380)
        lay = QVBoxLayout(self)
        self.kopf = QLabel()
        self.kopf.setWordWrap(True)
        self.kopf.setTextFormat(Qt.PlainText)
        lay.addWidget(self.kopf)
        self.liste = QTableWidget(0, len(SPALTEN))
        self.liste.setHorizontalHeaderLabels(SPALTEN)
        self.liste.verticalHeader().setVisible(False)
        self.liste.setAlternatingRowColors(True)
        self.liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.liste.setSelectionMode(QAbstractItemView.SingleSelection)
        self.liste.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.liste.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.liste, 1)
        zeile = QHBoxLayout()
        self.neu = QPushButton("Aktualisieren")
        self.neu.clicked.connect(lambda: self.laden(lesen=True))
        self.notiz = QPushButton("Notiz an …")
        self.notiz.setToolTip("Notiz an den markierten Kollegen (kommt auf seine Startseite)")
        self.notiz.clicked.connect(self._notiz)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        zeile.addWidget(self.neu)
        zeile.addWidget(self.notiz)
        zeile.addStretch(1)
        zeile.addWidget(zu)
        lay.addLayout(zeile)
        self.liste.itemSelectionChanged.connect(self._knoepfe)
        self.laden(lesen=True)

    def laden(self, lesen=False):
        if lesen:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                teilen.lebenszeichen_lesen(self.db)
            except (teilen.TeilenFehler, OSError):
                pass
            finally:
                QApplication.restoreOverrideCursor()
        self.daten = zeilen(self.db)
        self.liste.setRowCount(0)
        for d in self.daten:
            z = self.liste.rowCount()
            self.liste.insertRow(z)
            for sp, text in enumerate(d["werte"]):
                it = QTableWidgetItem(text)
                it.setData(Qt.UserRole, d["kuerzel"])
                if sp == 2:
                    it.setForeground(stil.farbe(stil.GRUEN if d["online"] else stil.TEXT_GRAU))
                if sp in (6, 8):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.liste.setItem(z, sp, it)
        da = sum(1 for d in self.daten if d["online"] and not d["ich"])
        andere = sum(1 for d in self.daten if not d["ich"])
        self.kopf.setText(f"{andere} Kollegen im gemeinsamen Ordner, {da} gerade da. „Da“ heißt: das Programm läuft "
                          f"dort und hat sich in den letzten {teilen.ONLINE_S // 60} Minuten gemeldet."
                          if andere else "Noch keine Kollegen im gemeinsamen Ordner.")
        self._knoepfe()

    def _gewaehlt(self):
        it = self.liste.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def _knoepfe(self):
        k = self._gewaehlt()
        self.notiz.setEnabled(bool(k) and k != teilen.kuerzel(self.db))

    def _notiz(self):
        from . import teilen_fenster
        k = self._gewaehlt()
        if k and teilen_fenster.notiz_senden(self.f, vorschlag=k):
            self.laden()


def zeigen(fenster):
    d = KollegenDialog(fenster)
    if not fenster.stumm:
        d.exec()
    return d
