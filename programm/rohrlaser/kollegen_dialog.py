"""Fenster „Kollegen im gemeinsamen Ordner“ (Datei-Menü, Patrick 31.10.2026, Paket B Baustein 6).

Je Mitarbeiter: Kürzel, Name, ob er gerade da ist (Lebenszeichen, sonst „zuletzt vor …“), Rechner, Programmversion,
letzter Abgleich, Zahl der Angebote, gerade geöffnete Angebote, eigene Vorgänge an ihn, die er noch nicht umgesetzt
hat, und die Abweichung seiner PC-Uhr. Der eigene Arbeitsplatz steht oben.

Paket C: Der Admin trägt einen ausgeschiedenen Mitarbeiter aus (AusgeschiedenDialog): seine Angebote übernimmt der Admin
oder ein Kollege (je Angebot oder für alle), sein Ordner kommt ins Archiv des gemeinsamen Ordners."""
import datetime
import socket

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from . import VERSION, admin_schutz, stil, teilen

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
        self.weg = QPushButton("Ausgeschieden …")
        self.weg.setToolTip("Nur Admin: Angebote des markierten Kollegen übernehmen bzw. verteilen, seinen Ordner "
                            "ins Archiv legen")
        self.weg.clicked.connect(self._ausgeschieden)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        zeile.addWidget(self.neu)
        zeile.addWidget(self.notiz)
        zeile.addWidget(self.weg)
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
        kollege = bool(k) and k != teilen.kuerzel(self.db)
        self.notiz.setEnabled(kollege)
        self.weg.setVisible(admin_schutz.ist_admin(self.db))
        self.weg.setEnabled(kollege and not self.db.nur_lesen)

    def _ausgeschieden(self):
        k = self._gewaehlt()
        if not k:
            return None
        d = AusgeschiedenDialog(self.f, k)
        if self.f.stumm:            # Tests: Auswahl vorher über vorgabe
            d.bestaetigt = getattr(self, "vorgabe", None) is not None
            for i, kk in (getattr(self, "vorgabe", None) or {}).items():
                c = d.combos[[a["id"] for a in d.angebote].index(i)]
                c.setCurrentIndex(c.findData(kk))
        elif d.exec() != QDialog.Accepted:
            return d
        if not getattr(d, "bestaetigt", False):
            return d
        try:
            erg = teilen.ausgeschieden(self.db, k, d.zuordnung())
        except teilen.TeilenFehler as e:
            self.f.meldung(str(e), fehler=True)
            return d
        self.f.alles_neu_laden()
        self.f.meldung(f"{k} ausgetragen: {erg['uebernommen']} Angebote übernommen, {erg['uebergeben']} an Kollegen "
                       f"übergeben; Ordner im Archiv ({erg['archiv'].name}).")
        self.laden(lesen=True)
        return d

    def _notiz(self):
        from . import teilen_fenster
        k = self._gewaehlt()
        if k and teilen_fenster.notiz_senden(self.f, vorschlag=k):
            self.laden()


class AusgeschiedenDialog(QDialog):
    """Ausgeschiedenen Mitarbeiter austragen: je Angebot den neuen Bearbeiter wählen (oben: für alle)."""
    def __init__(self, fenster, k2):
        super().__init__(fenster)
        self.f, self.db, self.k2 = fenster, fenster.db, k2
        self.setWindowTitle(f"Mitarbeiter {k2} ausgeschieden")
        self.resize(720, 460)
        lay = QVBoxLayout(self)
        m = teilen.mitarbeiter(self.db, k2)
        p = teilen.lebenszeichen(self.db).get(k2)
        warnung = ""
        if p and p["online"]:
            warnung = f"\n\n⚠ Das Programm von {k2} läuft gerade. Erst dort beenden, sonst legt es seine Daten wieder ab."
        text = QLabel(f"{k2} {m.get('name') or ''}: Seine Angebote bekommt ein neuer Bearbeiter, sein Ordner kommt in "
                      "den Ordner Archiv des gemeinsamen Ordners (bleibt erhalten, wird nicht mehr gelesen). Angebote "
                      "für Kollegen gehen als Übergabe hinaus und kommen beim nächsten Abgleich an." + warnung)
        text.setWordWrap(True)
        text.setTextFormat(Qt.PlainText)
        lay.addWidget(text)
        self.wahl = [(teilen.kuerzel(self.db), f"{teilen.kuerzel(self.db)} (ich)")] + [
            (k, f"{k} – {n}" if n else k) for k, n in teilen.kollegen(self.db).items() if k != k2]
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Alle an"))
        self.alle = QComboBox()
        for k, t in self.wahl:
            self.alle.addItem(t, k)
        self.alle.currentIndexChanged.connect(self._alle)
        oben.addWidget(self.alle)
        oben.addStretch(1)
        lay.addLayout(oben)
        self.angebote = teilen.angebote_von(self.db, k2)
        self.liste = QTableWidget(len(self.angebote), 4)
        self.liste.setHorizontalHeaderLabels(["Nummer", "Kunde", "Datum", "Neuer Bearbeiter"])
        self.liste.verticalHeader().setVisible(False)
        self.liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.liste.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.liste.horizontalHeader().setStretchLastSection(True)
        self.combos = []
        for z, a in enumerate(self.angebote):
            for sp, t in enumerate((a["nummer"], a["kunde"], a["datum"])):
                self.liste.setItem(z, sp, QTableWidgetItem(str(t or "")))
            c = QComboBox()
            for k, t in self.wahl:
                c.addItem(t, k)
            self.liste.setCellWidget(z, 3, c)
            self.combos.append(c)
        lay.addWidget(self.liste, 1)
        lay.addWidget(QLabel(f"{len(self.angebote)} Angebote von {k2}."))
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Austragen")
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def _alle(self):
        for c in self.combos:
            c.setCurrentIndex(self.alle.currentIndex())

    def zuordnung(self):
        return {a["id"]: c.currentData() for a, c in zip(self.angebote, self.combos)}

    def _ok(self):
        if QMessageBox.question(self, "Ausgeschieden", f"{self.k2} wirklich austragen? Der Ordner von {self.k2} kommt "
                                "ins Archiv.") == QMessageBox.Yes:
            self.bestaetigt = True
            self.accept()


def zeigen(fenster):
    d = KollegenDialog(fenster)
    if not fenster.stumm:
        d.exec()
    return d
