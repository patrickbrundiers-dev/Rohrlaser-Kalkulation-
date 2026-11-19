"""Update-Center (Hilfe → Update-Center …, Auftrag Patrick 19.11.2026): alles rund ums Update an einer Stelle.

Oben der Stand (installiert, verfügbar, Quelle, letzte erfolgreiche Aktualisierung, vorige Version) und die
Aktionen: suchen, aktualisieren, Update-Datei oder Ordner (USB-Stick) einspielen, vorige Version wiederherstellen.
Reiter: Quellen (Ergebnis der letzten Suche je Quelle), Verlauf, Einstellungen (Quelle, Update-Ordner, Proxy,
Firmenzertifikat), Diagnose (Bericht für die IT) und – nur für Admins – Verteilen (Update im Netzwerkordner
bereitstellen, Update-Datei erstellen, Freigabe, Stand aller Arbeitsplätze).

Die Logik steckt in update.py, update_quellen.py, update_verteilen.py und update_diagnose.py; hier nur Anzeige.
"""
import datetime
import threading
from pathlib import Path

from PySide6.QtCore import QDate, QObject, Qt, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QProgressDialog, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import protokoll, update, update_diagnose, update_netz, update_quellen, update_verteilen

STUFE_TEXT = {"ok": "OK", "warnung": "Warnung", "fehler": "Fehler", "info": "Info"}


def _zeit(text):
    try:
        return datetime.datetime.fromisoformat(str(text)).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return str(text or "")


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.horizontalHeader().setSectionResizeMode(len(spalten) - 1, QHeaderView.Stretch)
    for i in range(len(spalten) - 1):
        t.setColumnWidth(i, 150)
    t.setWordWrap(True)
    return t


def _breiten(t):
    """Spalten an den Inhalt anpassen (höchstens 320 px), letzte Spalte füllt den Rest."""
    t.resizeColumnsToContents()
    for i in range(t.columnCount() - 1):
        t.setColumnWidth(i, min(max(t.columnWidth(i), 110), 320))
    t.resizeRowsToContents()


def _fuellen(t, zeilen):
    t.setRowCount(len(zeilen))
    for r, zeile in enumerate(zeilen):
        for c, wert in enumerate(zeile):
            it = QTableWidgetItem("" if wert is None else str(wert))
            it.setToolTip(it.text())
            t.setItem(r, c, it)
    _breiten(t)


class _Diagnose(QObject):
    fertig = Signal(object)

    def starten(self, ordner, db, quellen):
        def arbeit():
            try:
                self.fertig.emit(update_diagnose.pruefen(ordner, db, quellen))
            except Exception as e:      # noqa: BLE001 – Diagnose darf nie abstürzen
                self.fertig.emit([dict(gruppe="Diagnose", name="Abbruch", stufe="fehler", text=str(e), tipp="")])
        threading.Thread(target=arbeit, name="Update-Diagnose", daemon=True).start()


class UpdateCenter(QDialog):
    def __init__(self, fenster):
        super().__init__(fenster)
        self.f = fenster
        self.u = fenster.updater
        self.db = getattr(fenster, "db", None)
        self.befunde = []
        self.setWindowTitle("Update-Center")
        self.resize(900, 620)
        lay = QVBoxLayout(self)

        stand = QGroupBox("Stand")
        form = QFormLayout(stand)
        self.l_installiert, self.l_verfuegbar, self.l_status = QLabel(), QLabel(), QLabel()
        self.l_quelle, self.l_letzte, self.l_vorige = QLabel(), QLabel(), QLabel()
        for lab in (self.l_verfuegbar, self.l_status, self.l_quelle):
            lab.setWordWrap(True)
        form.addRow("Installiert:", self.l_installiert)
        form.addRow("Verfügbar:", self.l_verfuegbar)
        form.addRow("Update-Quelle:", self.l_quelle)
        form.addRow("Status:", self.l_status)
        form.addRow("Letzte Aktualisierung:", self.l_letzte)
        form.addRow("Vorige Version:", self.l_vorige)
        lay.addWidget(stand)

        knoepfe = QHBoxLayout()
        self.k_suchen = QPushButton("Nach Updates suchen")
        self.k_jetzt = QPushButton("Jetzt aktualisieren")
        self.k_datei = QPushButton("Update-Datei einspielen …")
        self.k_ordner = QPushButton("Aus Ordner einspielen …")
        self.k_zurueck = QPushButton("Vorige Version …")
        self.k_datei.setToolTip("Update-Datei (.rlupdate) von USB-Stick, Netzlaufwerk oder aus dem Browser-Download. "
                                "Keine Internetverbindung nötig.")
        self.k_ordner.setToolTip("Update-Ordner wählen, z. B. auf einem USB-Stick (enthält Update.json).")
        for k, f in ((self.k_suchen, self.suchen), (self.k_jetzt, self.jetzt), (self.k_datei, self.datei),
                     (self.k_ordner, self.ordner), (self.k_zurueck, self.zurueck)):
            k.clicked.connect(f)
            knoepfe.addWidget(k)
        knoepfe.addStretch(1)
        lay.addLayout(knoepfe)

        self.reiter = QTabWidget()
        lay.addWidget(self.reiter, 1)
        self.t_quellen = _tabelle(["Quelle", "Stand", "Ergebnis"])
        self.reiter.addTab(self.t_quellen, "Quellen")
        self.t_verlauf = _tabelle(["Zeit", "Vorgang", "Ergebnis", "Stand", "Quelle / Hinweis"])
        self.reiter.addTab(self.t_verlauf, "Verlauf")
        self.reiter.addTab(self._einstellungen(), "Einstellungen")
        self.reiter.addTab(self._diagnose(), "Diagnose")
        self.verteilen = self._verteilen()
        self.i_verteilen = self.reiter.addTab(self.verteilen, "Verteilen (Admin)")

        unten = QDialogButtonBox(QDialogButtonBox.Close)
        unten.rejected.connect(self.reject)
        lay.addWidget(unten)
        self.aktualisieren()

    # -------------------------------------------------------------- Anzeige
    def _admin(self):
        try:
            from . import admin_schutz
            return admin_schutz.ist_admin(self.db)
        except Exception:       # noqa: BLE001
            return False

    def aktualisieren(self):
        u = self.u
        self.l_installiert.setText(update.stand_text(u.lokal))
        erg = u.letzte_suche
        beste = erg and erg.get("beste")
        if beste:
            q, liste = beste
            neu = update.neuer(liste, u.lokal)
            self.l_verfuegbar.setText(update.stand_text(liste) + (" – neu" if neu else " – installiert ist aktuell"))
            self.l_quelle.setText(q.text())
            self.l_status.setText("Update verfügbar" if neu else "Aktuell")
            self.k_jetzt.setEnabled(neu)
        else:
            self.l_verfuegbar.setText("noch nicht gesucht" if erg is None else "keine Quelle erreichbar")
            self.l_quelle.setText(", ".join(q.text() for q in u.quellen()) or "keine")
            self.l_status.setText("Bitte „Nach Updates suchen“" if erg is None else
                                  "Keine Quelle erreichbar – siehe Reiter Quellen und Diagnose")
            self.k_jetzt.setEnabled(False)
        if u.ausstehend:
            self.l_status.setText(f"{update.stand_text(u.ausstehend['online'])} geladen, wird beim Beenden eingespielt")
        letzte = update_quellen.letzte_erfolgreiche(u.verlauf_pfad())
        self.l_letzte.setText(f"{_zeit(letzte['zeit'])} (Stand {letzte.get('nach')}, {letzte.get('quelle') or ''})"
                              if letzte else "–")
        vorige = update.vorige_version(u.ordner) if u.ordner else None
        self.l_vorige.setText(update.stand_text(vorige) if vorige else "keine gespeichert")
        self.k_zurueck.setEnabled(vorige is not None)
        _fuellen(self.t_quellen, [(q.text(), update.stand_text(liste) if liste else "",
                                   "gültig signiert" if liste else (fehler or "")[:300])
                                  for q, liste, fehler in (erg or {}).get("ergebnisse", [])])
        _fuellen(self.t_verlauf, [(_zeit(e.get("zeit")), e.get("art"), e.get("ergebnis") or "",
                                   f"{e.get('von') or ''} → {e.get('nach') or ''}",
                                   e.get("fehler") or e.get("quelle") or "")
                                  for e in update_quellen.verlauf_lesen(u.verlauf_pfad())])
        self.reiter.setTabVisible(self.i_verteilen, self._admin())
        self._plaetze_zeigen()

    # -------------------------------------------------------------- Aktionen
    def suchen(self):
        if self.u._laeuft:
            self.l_status.setText("Es wird gerade schon gesucht, bitte gleich noch einmal.")
            return
        self.l_status.setText("Suche läuft …")
        self.k_suchen.setEnabled(False)

        def fertig(_erg):
            self.k_suchen.setEnabled(True)
            self.aktualisieren()
        self.u.suchen(still=True, fertig=fertig, anbieten=False)

    def jetzt(self):
        beste = (self.u.letzte_suche or {}).get("beste")
        if beste:
            self.u.quelle_obj, online = beste
            self.u.quelle = self.u.quelle_obj.adresse()
            if self.u.anbieten(online):
                self.accept()
        self.aktualisieren()

    def datei(self):
        pfad, _ = QFileDialog.getOpenFileName(self, "Update-Datei einspielen", "",
                                              f"Update-Datei (*{update_verteilen.ENDUNG});;Alle Dateien (*)")
        if pfad and self.u.datei_einspielen(pfad):
            self.accept()
        self.aktualisieren()

    def ordner(self):
        pfad = QFileDialog.getExistingDirectory(self, "Update-Ordner wählen (z. B. USB-Stick)")
        if pfad and self.u.ordner_einspielen(pfad):
            self.accept()
        self.aktualisieren()

    def zurueck(self):
        if self.u.zuruecksetzen():
            self.accept()

    # -------------------------------------------------------------- Einstellungen
    def _einstellungen(self):
        w = QWidget()
        form = QFormLayout(w)
        e = update_quellen.einstellungen(self.db)
        self.e_quelle = QComboBox()
        for wert, text in update_quellen.MODI:
            self.e_quelle.addItem(text, wert)
        self.e_quelle.setCurrentIndex(max(0, self.e_quelle.findData(e["quelle"])))
        self.e_ordner = QLineEdit(e["ordner"])
        vorgabe = update_quellen.update_ordner(self.db) if not e["ordner"] else None
        self.e_ordner.setPlaceholderText(f"leer = {vorgabe}" if vorgabe else
                                         r"z. B. \\server\Rohrlaser\Updates (leer = Updates im gemeinsamen Ordner)")
        o = QHBoxLayout()
        o.addWidget(self.e_ordner, 1)
        k = QPushButton("Wählen …")
        k.clicked.connect(lambda: self._waehlen(self.e_ordner, ordner=True))
        o.addWidget(k)
        self.e_proxy = QLineEdit("" if e["proxy"] == update_netz.SYSTEM else e["proxy"])
        self.e_proxy.setPlaceholderText("leer = Windows-Einstellung · „aus“ = kein Proxy · proxy.firma.local:8080")
        self.e_zert = QLineEdit(e["zertifikat"])
        self.e_zert.setPlaceholderText("leer = nur Windows-Zertifikatsspeicher · Stammzertifikat der Firma (.pem/.crt)")
        z = QHBoxLayout()
        z.addWidget(self.e_zert, 1)
        k2 = QPushButton("Wählen …")
        k2.clicked.connect(lambda: self._waehlen(self.e_zert))
        z.addWidget(k2)
        self.e_start = QCheckBox("Beim Programmstart still nach Updates suchen")
        self.e_start.setChecked(e["beim_start"])
        form.addRow("Update-Quelle:", self.e_quelle)
        form.addRow("Update-Ordner:", o)
        form.addRow("Proxy:", self.e_proxy)
        form.addRow("Firmenzertifikat:", z)
        form.addRow("", self.e_start)
        hinweis = QLabel("Benutzer und Passwort für den Proxy werden nie gespeichert. Die Zertifikatsprüfung bleibt "
                         "immer an. Die Werte gelten nur für diesen Arbeitsplatz.")
        hinweis.setWordWrap(True)
        form.addRow("", hinweis)
        k3 = QPushButton("Einstellungen speichern")
        k3.clicked.connect(self.einstellungen_speichern)
        form.addRow("", k3)
        return w

    def _waehlen(self, feld, ordner=False):
        pfad = (QFileDialog.getExistingDirectory(self, "Ordner wählen", feld.text()) if ordner else
                QFileDialog.getOpenFileName(self, "Datei wählen", feld.text())[0])
        if pfad:
            feld.setText(pfad)

    def einstellungen_speichern(self):
        try:
            update_quellen.speichern(self.db, quelle=self.e_quelle.currentData(), ordner=self.e_ordner.text(),
                                     proxy=self.e_proxy.text() or update_netz.SYSTEM, zertifikat=self.e_zert.text(),
                                     beim_start=self.e_start.isChecked())
        except ValueError as e:
            QMessageBox.warning(self, "Update-Einstellungen", str(e))
            return False
        protokoll.info(f"Update-Einstellungen geändert: Quelle {self.e_quelle.currentData()}, Proxy "
                       f"{update_netz.text()}")
        self.f.meldung("Update-Einstellungen gespeichert.")
        self.u.letzte_suche = None
        self.aktualisieren()
        return True

    # -------------------------------------------------------------- Diagnose
    def _diagnose(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        zeile = QHBoxLayout()
        self.k_diag = QPushButton("Diagnose starten")
        self.k_diag.clicked.connect(self.diagnose)
        self.k_bericht = QPushButton("Bericht für die IT speichern …")
        self.k_bericht.clicked.connect(self.bericht_speichern)
        self.k_bericht.setEnabled(False)
        zeile.addWidget(self.k_diag)
        zeile.addWidget(self.k_bericht)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.t_diag = _tabelle(["Bereich", "Prüfung", "Ergebnis", "Befund und Lösung"])
        self.t_diag.setWordWrap(True)
        lay.addWidget(self.t_diag, 1)
        return w

    def diagnose(self):
        self.k_diag.setEnabled(False)
        self.k_diag.setText("Diagnose läuft …")
        self._lauf = _Diagnose()
        self._lauf.fertig.connect(self._diagnose_fertig)
        self._lauf.starten(self.u.ordner, self.db, self.u.quellen())

    def _diagnose_fertig(self, befunde):
        self.befunde = befunde
        self.k_diag.setEnabled(True)
        self.k_diag.setText("Diagnose starten")
        self.k_bericht.setEnabled(True)
        _fuellen(self.t_diag, [(b["gruppe"], b["name"], STUFE_TEXT[b["stufe"]],
                                b["text"] + (f" → {b['tipp']}" if b.get("tipp") else "")) for b in befunde])
        protokoll.info("Update-Diagnose: " + update_diagnose.zusammenfassung(befunde))

    def bericht_speichern(self, pfad=None):
        if not pfad:
            pfad, _ = QFileDialog.getSaveFileName(self, "Diagnosebericht speichern", "Update-Diagnose.txt",
                                                  "Text (*.txt)")
        if not pfad:
            return None
        Path(pfad).write_text(update_diagnose.bericht(self.befunde), encoding="utf-8")
        self.f.meldung(f"Diagnosebericht gespeichert: {pfad}")
        return pfad

    # -------------------------------------------------------------- Verteilen (Admin)
    def _verteilen(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.l_ziel = QLabel()
        self.l_ziel.setWordWrap(True)
        lay.addWidget(self.l_ziel)
        zeile = QHBoxLayout()
        self.k_bereit_netz = QPushButton("Aus dem Internet bereitstellen")
        self.k_bereit_netz.setToolTip("Dieser Rechner lädt das aktuelle Update einmal und legt es in den Update-Ordner. "
                                      "Alle Arbeitsplätze holen es dann von dort, ohne eigenen Internetzugang.")
        self.k_bereit_datei = QPushButton("Aus Update-Datei bereitstellen …")
        self.k_datei_erstellen = QPushButton("Update-Datei erstellen …")
        self.k_datei_erstellen.setToolTip("Den Inhalt des Update-Ordners als eine Datei (.rlupdate) speichern, z. B. "
                                          "für einen USB-Stick oder einen Rechner ohne Netzwerk.")
        self.k_bereit_netz.clicked.connect(lambda: self.bereitstellen(update_quellen.InternetQuelle()))
        self.k_bereit_datei.clicked.connect(self._bereit_aus_datei)
        self.k_datei_erstellen.clicked.connect(self.datei_erstellen)
        for k in (self.k_bereit_netz, self.k_bereit_datei, self.k_datei_erstellen):
            zeile.addWidget(k)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        g = QGroupBox("Freigabe für alle Arbeitsplätze")
        form = QFormLayout(g)
        self.v_pflicht = QCheckBox("Pflicht-Update")
        self.v_ab = QDateEdit(QDate.currentDate().addDays(7))
        self.v_ab.setCalendarPopup(True)
        self.v_ab.setDisplayFormat("dd.MM.yyyy")
        pf = QHBoxLayout()
        pf.addWidget(self.v_pflicht)
        pf.addWidget(QLabel("ab"))
        pf.addWidget(self.v_ab)
        pf.addStretch(1)
        self.v_hinweis = QLineEdit()
        self.v_hinweis.setPlaceholderText("z. B. Bitte bis Freitag aktualisieren, neue Fracht-Regeln")
        self.v_wartung = QLineEdit()
        self.v_wartung.setPlaceholderText("z. B. Freitag ab 16 Uhr")
        self.v_nur_ordner = QCheckBox("Arbeitsplätze holen Updates nur aus diesem Ordner (nie direkt aus dem Internet)")
        k = QPushButton("Freigabe speichern")
        k.clicked.connect(self.freigabe_speichern)
        form.addRow("", pf)
        form.addRow("Hinweis:", self.v_hinweis)
        form.addRow("Wartungsfenster:", self.v_wartung)
        form.addRow("", self.v_nur_ordner)
        form.addRow("", k)
        lay.addWidget(g)
        lay.addWidget(QLabel("Arbeitsplätze (Rückmeldung nach jedem Update):"))
        self.t_plaetze = _tabelle(["Arbeitsplatz", "Kürzel", "Stand", "Zeit", "Ergebnis"])
        lay.addWidget(self.t_plaetze, 1)
        return w

    def _ziel(self):
        return update_quellen.update_ordner(self.db)

    def _plaetze_zeigen(self):
        ziel = self._ziel()
        liste = update.lokale_liste(update_verteilen.kalkulation_ordner(ziel)) if ziel else None
        self.l_ziel.setText(f"Update-Ordner: {ziel}" + (f" – enthält {update.stand_text(liste)}" if liste else
                                                         " – noch leer") if ziel else
                            "Kein Update-Ordner: im Reiter Einstellungen eintragen oder den gemeinsamen Ordner "
                            "einrichten (dann gilt dessen Unterordner Updates).")
        for k in (self.k_bereit_netz, self.k_bereit_datei, self.k_datei_erstellen):
            k.setEnabled(bool(ziel))
        self.k_datei_erstellen.setEnabled(bool(liste))
        f = update_verteilen.freigabe_lesen(ziel) if ziel else {}
        self.v_pflicht.setChecked(f.get("pflicht", False))
        if f.get("pflicht_ab"):
            self.v_ab.setDate(QDate.fromString(f["pflicht_ab"], "yyyy-MM-dd"))
        self.v_hinweis.setText(f.get("hinweis", ""))
        self.v_wartung.setText(f.get("wartung", ""))
        self.v_nur_ordner.setChecked(f.get("nur_ordner", False))
        plaetze = update_verteilen.plaetze(ziel) if ziel else []
        stand = (liste or {}).get("stand")
        alt = {id(p) for p in update_verteilen.veraltete(plaetze, stand)} if stand else set()
        _fuellen(self.t_plaetze, [(p.get("platz"), p.get("kuerzel") or "", (p.get("version") or "") + (
            f" (Stand {p.get('stand')})" if p.get("stand") else "") + (" – veraltet" if id(p) in alt else ""),
            _zeit(p.get("zeit")), p.get("ergebnis") or "") for p in plaetze])

    def _bereit_aus_datei(self):
        pfad, _ = QFileDialog.getOpenFileName(self, "Update-Datei bereitstellen", "",
                                              f"Update-Datei (*{update_verteilen.ENDUNG})")
        if pfad:
            self.bereitstellen(update_quellen.DateiQuelle(pfad, self.u.ordner / update.ARBEITSORDNER / "import"))

    def bereitstellen(self, quelle):
        ziel = self._ziel()
        if not ziel or not self._admin():
            return None
        fortschritt = QProgressDialog("Update bereitstellen …", "Abbrechen", 0, 100, self)
        fortschritt.setWindowTitle("Update bereitstellen")
        fortschritt.setMinimumDuration(0)

        def weiter(n, gesamt):
            fortschritt.setValue(int(100 * n / max(1, gesamt)))
            fortschritt.setLabelText(f"{n / 1e6:.0f} von {gesamt / 1e6:.0f} MB".replace(".", ","))
            QApplication.processEvents()
            if fortschritt.wasCanceled():
                raise update.Abbruch()
        try:
            liste = update_verteilen.bereitstellen(quelle, ziel, fortschritt=weiter)
        except update.Abbruch:
            fortschritt.close()
            return None
        except (update.UpdateFehler, OSError) as e:
            fortschritt.close()
            protokoll.info(f"Update bereitstellen fehlgeschlagen: {e}")
            QMessageBox.warning(self, "Update bereitstellen", str(e))
            return None
        fortschritt.close()
        protokoll.info(f"Update bereitgestellt: {update.stand_text(liste)} aus {quelle.text()} in {ziel}")
        self.f.meldung(f"{update.stand_text(liste)} liegt jetzt im Update-Ordner {ziel}; die Arbeitsplätze finden es "
                       "beim nächsten Start.")
        self.aktualisieren()
        return liste

    def datei_erstellen(self, pfad=None):
        ziel = self._ziel()
        liste = update.lokale_liste(update_verteilen.kalkulation_ordner(ziel)) if ziel else None
        if not liste:
            return None
        if not pfad:
            pfad, _ = QFileDialog.getSaveFileName(
                self, "Update-Datei erstellen", f"Rohrlaser-Update-{liste.get('version')}{update_verteilen.ENDUNG}",
                f"Update-Datei (*{update_verteilen.ENDUNG})")
        if not pfad:
            return None
        try:
            erg = update_verteilen.datei_erstellen(update_verteilen.kalkulation_ordner(ziel), pfad)
        except (update.UpdateFehler, OSError) as e:
            QMessageBox.warning(self, "Update-Datei erstellen", str(e))
            return None
        self.f.meldung(f"Update-Datei gespeichert: {erg}")
        return erg

    def freigabe_speichern(self):
        ziel = self._ziel()
        if not ziel or not self._admin():
            return None
        liste = update.lokale_liste(update_verteilen.kalkulation_ordner(ziel))
        try:
            from . import teilen
            von = teilen.kuerzel(self.db)
        except Exception:       # noqa: BLE001
            von = ""
        try:
            d = update_verteilen.freigabe_schreiben(
                ziel, stand=(liste or {}).get("stand"), pflicht=self.v_pflicht.isChecked(),
                pflicht_ab=self.v_ab.date().toString("yyyy-MM-dd") if self.v_pflicht.isChecked() else "",
                hinweis=self.v_hinweis.text(), wartung=self.v_wartung.text(), nur_ordner=self.v_nur_ordner.isChecked(),
                von=von)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Freigabe", f"Freigabe lässt sich nicht speichern: {e}")
            return None
        protokoll.info(f"Update-Freigabe gespeichert: {d}")
        self.f.meldung("Freigabe für alle Arbeitsplätze gespeichert.")
        return d


def zeigen(fenster):
    d = UpdateCenter(fenster)
    d.setAttribute(Qt.WA_DeleteOnClose, False)
    d.exec()
    return d
