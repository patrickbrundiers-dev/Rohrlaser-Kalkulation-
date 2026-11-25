"""Gemeinsamer Importassistent (Master-Aufträge 25.11.2026 EK-CSV-Import und Kundenlisten-CSV-Import): dieselbe
Bedienung für alle CSV-Importe – Schrittleiste oben, Zurück/Weiter unten, Fortschritt bei großen Dateien, Spalten
zuordnen mit Sicherheit und Beispielwerten, Importprofile (speichern, kopieren, umbenennen, löschen), Tabellen mit
Filter und Farben, Fehlerbericht und Rückgängig der letzten Importe. Die Fachlogik steht in csv_import, erp_preise und
kunden_csv; hier nur die Oberfläche.

Ein Schritt ist ein QWidget mit optional betreten() (beim Anzeigen), pruefen() -> Fehlertext oder "" (vor Weiter)
und titel. Der letzte Schritt kann abschliessen() haben (Knopf „Importieren“)."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QMessageBox, QProgressBar, QPushButton,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import csv_import, stil

KEINE = "– keine –"
GRUEN, GELB, ROT, GRAU, BLAU = "#E2F0D9", "#FFF2CC", "#F8D7DA", "#EDEDED", "#DDEBF7"
FARBE_SICHERHEIT = {csv_import.SICHER: GRUEN, csv_import.VORSCHLAG: GELB}


def tabelle(spalten, breiten=(), auswahl_mehrfach=False):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.ExtendedSelection if auswahl_mehrfach else QAbstractItemView.SingleSelection)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)
    t.setWordWrap(False)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    for i, b in enumerate(breiten):
        t.setColumnWidth(i, b)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def fuellen(t, zeilen, farben=None, rechts=(), grenze=5000):
    """Tabelle füllen; farben = [Hell-Farbe oder None je Zeile]; mehr als grenze Zeilen: nur die ersten (Hinweis)."""
    t.setUpdatesEnabled(False)
    t.setRowCount(min(len(zeilen), grenze))
    for r, zeile in enumerate(zeilen[:grenze]):
        f = farben[r] if farben else None
        brush = QBrush(stil.farbe(f)) if f else None
        for c, w in enumerate(zeile):
            it = QTableWidgetItem("" if w is None else str(w))
            it.setToolTip(it.text())
            if c in rechts:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if brush is not None:
                it.setBackground(brush)
            t.setItem(r, c, it)
    t.setUpdatesEnabled(True)
    return len(zeilen) > grenze


def text(t):
    lab = QLabel(t)
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.RichText)
    return lab


def zahl(x, stellen=2):
    if x is None:
        return ""
    return f"{x:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


# ------------------------------------------------------------------ Rahmen
class Assistent(QDialog):
    """Rahmen mit Schrittleiste, Seiten, Fortschritt und Knöpfen Zurück / Weiter / Importieren / Abbrechen."""

    def __init__(self, parent, titel, schritte):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.resize(1180, 700)
        self.schritte = list(schritte)
        self.leiste = QLabel()
        self.leiste.setTextFormat(Qt.RichText)
        self.leiste.setWordWrap(True)
        self.seiten = QStackedWidget()
        for s in self.schritte:
            s.assistent = self
            self.seiten.addWidget(s)
        self.meldung = QLabel()
        self.meldung.setWordWrap(True)
        self.meldung.setStyleSheet("color:#B42318")
        self.balken = QProgressBar()
        self.balken.setVisible(False)
        self.balken.setMaximumHeight(16)
        self.balken_text = QLabel()
        self.zurueck_k = QPushButton("◀ Zurück")
        self.weiter_k = QPushButton("Weiter ▶")
        self.weiter_k.setDefault(True)
        self.abbrechen_k = QPushButton("Abbrechen")
        self.zurueck_k.clicked.connect(self.zurueck)
        self.weiter_k.clicked.connect(self.weiter)
        self.abbrechen_k.clicked.connect(self.reject)
        unten = QHBoxLayout()
        unten.addWidget(self.balken_text)
        unten.addWidget(self.balken, 1)
        unten.addStretch(1)
        for k in (self.abbrechen_k, self.zurueck_k, self.weiter_k):
            unten.addWidget(k)
        lay = QVBoxLayout(self)
        lay.addWidget(self.leiste)
        lay.addWidget(self.seiten, 1)
        lay.addWidget(self.meldung)
        lay.addLayout(unten)
        self.fertig = False
        self.nr = 0
        self._zeigen(0)

    @property
    def schritt(self):
        return self.schritte[self.nr]

    def _zeigen(self, nr):
        self.nr = nr
        self.meldung.clear()
        teile = []
        for i, s in enumerate(self.schritte):
            t = f"{i + 1}. {s.titel}"
            teile.append(f"<b style='color:#1F4E79'>{t}</b>" if i == nr else
                         (f"<span style='color:#2E7D32'>✓ {t}</span>" if i < nr else f"<span style='color:#888'>{t}"
                                                                                     "</span>"))
        self.leiste.setText(f"<span style='font-size:13px'>{' &nbsp;›&nbsp; '.join(teile)}</span>")
        self.seiten.setCurrentIndex(nr)
        betreten = getattr(self.schritt, "betreten", None)
        if betreten:
            try:
                betreten()
            except ValueError as e:
                self.meldung.setText(str(e))
        self.knoepfe()

    def knoepfe(self):
        letzter = self.nr == len(self.schritte) - 1
        self.zurueck_k.setEnabled(self.nr > 0 and not self.fertig)
        if self.fertig:
            self.weiter_k.setText("Schließen")
            self.abbrechen_k.setVisible(False)
        else:
            self.weiter_k.setText(getattr(self.schritt, "knopf", None) or ("Importieren" if letzter else "Weiter ▶"))

    def zurueck(self):
        if self.nr > 0 and not self.fertig:
            self._zeigen(self.nr - 1)

    def weiter(self):
        """Weiter (prüft den Schritt), im letzten Schritt abschließen, danach schließen. True, wenn es weiterging."""
        if self.fertig:
            self.accept()
            return True
        pruefen = getattr(self.schritt, "pruefen", None)
        fehler = pruefen() if pruefen else ""
        if fehler:
            self.meldung.setText(fehler)
            return False
        if self.nr < len(self.schritte) - 1:
            self._zeigen(self.nr + 1)
            return True
        try:
            self.schritt.abschliessen()
        except (ValueError, OSError) as e:
            self.meldung.setText(str(e))
            return False
        self.fertig = True
        self.knoepfe()
        return True

    def fortschritt(self, i, n, was=""):
        """Fortschritt bei großen Dateien (Rückruf für die Fachfunktionen)."""
        self.balken.setVisible(i < n)
        self.balken.setMaximum(max(1, n))
        self.balken.setValue(i)
        self.balken_text.setText(was if i < n else "")
        QApplication.processEvents()


# ------------------------------------------------------------------ Schritt 1: Datei und Format
class DateiSchritt(QWidget):
    """Datei, erkanntes Format (Kodierung, Trennzeichen, Dezimalzeichen, Kopfzeile), dazu eigene Felder (Lieferant,
    Modus …) und die letzten Importe dieser Art mit Rückgängig."""
    titel = "Datei und Format"

    def __init__(self, pfad, daten, profilname="", zusatz=(), laeufe=None, rueckgaengig=None):
        super().__init__()
        self.pfad, self.daten = pfad, daten
        self.laeufe_fn, self.rueckgaengig_fn = laeufe, rueckgaengig
        lay = QVBoxLayout(self)
        lay.addWidget(text(f"<b>Datei:</b> {Path(pfad).name}<br><b>Erkannt:</b> {csv_import.format_text(daten)}"
                           + (f"<br><b>Importprofil:</b> {profilname} (Spalten aus dem Profil)" if profilname else
                              "<br><b>Importprofil:</b> keines passend – Spalten werden erkannt")))
        for m in daten.get("meldungen") or ():
            lay.addWidget(text(f"<span style='color:#9A6700'>Hinweis: {m}</span>"))
        for titel, w in zusatz:
            z = QHBoxLayout()
            lab = QLabel(titel)
            lab.setMinimumWidth(180)
            z.addWidget(lab)
            z.addWidget(w, 1)
            lay.addLayout(z)
        lay.addWidget(text("<b>Vorschau der ersten Zeilen</b> (so wie gelesen)"))
        kopf = daten["kopf"]
        self.vorschau = tabelle(kopf)
        fuellen(self.vorschau, [list(z) + [""] * (len(kopf) - len(z)) for z in daten["zeilen"][:12]])
        lay.addWidget(self.vorschau, 1)
        if laeufe:
            z = QHBoxLayout()
            self.laeufe_k = QPushButton("Letzte Importe / Rückgängig …")
            self.laeufe_k.clicked.connect(self.laeufe_zeigen)
            z.addWidget(self.laeufe_k)
            z.addStretch(1)
            lay.addLayout(z)

    def laeufe_zeigen(self, zeigen=True):
        d = LaeufeDialog(self, self.laeufe_fn, self.rueckgaengig_fn)
        if zeigen:
            d.exec()
        return d


class LaeufeDialog(QDialog):
    """Die letzten Importläufe einer Art; der gewählte lässt sich zurücknehmen."""

    def __init__(self, parent, laeufe, rueckgaengig):
        super().__init__(parent)
        self.setWindowTitle("Letzte Importe")
        self.resize(900, 380)
        self.laeufe_fn, self.rueckgaengig_fn = laeufe, rueckgaengig
        self.t = tabelle(("Nr.", "Zeit", "Datei", "Benutzer", "neu", "aktualisiert", "Fehler", "Status"),
                         (50, 140, 220, 90, 60, 80, 60))
        self.k = QPushButton("Ausgewählten Import rückgängig machen")
        self.k.clicked.connect(self.zuruecknehmen)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.t, 1)
        lay.addWidget(self.info)
        lay.addWidget(self.k)
        self.laden()

    def laden(self):
        self.liste = self.laeufe_fn()[:50]
        fuellen(self.t, [(z["id"], (z.get("zeit") or "")[:16].replace("T", " "), Path(z.get("datei") or "").name,
                          z.get("benutzer"), z.get("neu"), z.get("aktualisiert"), z.get("fehler"), z.get("status"))
                         for z in self.liste],
                [GRAU if "rückgängig" in str(z.get("status") or "") else None for z in self.liste])

    def zuruecknehmen(self, zeile=None, frage=True):
        r = self.t.currentRow() if zeile is None else zeile
        if r < 0 or r >= len(self.liste):
            return None
        z = self.liste[r]
        if "rückgängig" in str(z.get("status") or "") or "zurückgenommen" in str(z.get("status") or ""):
            self.info.setText("Dieser Import ist schon zurückgenommen.")
            return None
        if frage and QMessageBox.question(self, "Rückgängig", f"Import Nr. {z['id']} ({Path(z.get('datei') or '').name}"
                                          ") vollständig zurücknehmen?") != QMessageBox.Yes:
            return None
        n, meldungen = self.rueckgaengig_fn(z["id"])
        self.info.setText(f"{n} Änderungen zurückgenommen." + (" " + "; ".join(meldungen[:5]) if meldungen else ""))
        self.laden()
        return n, meldungen


# ------------------------------------------------------------------ Schritt 2: Spalten
class SpaltenSchritt(QWidget):
    """Je Programmfeld die Spalte der Datei (automatisch erkannt: grün sicher, gelb Vorschlag zum Prüfen), mit
    Beispielwerten; von Hand änderbar; Importprofile speichern, kopieren, umbenennen, löschen."""
    titel = "Spalten zuordnen"

    def __init__(self, db, einstellung, felder, pflicht, daten, erkannt, profilname="", extras=None, hinweis=""):
        super().__init__()
        self.db, self.einstellung, self.felder, self.pflicht, self.daten = db, einstellung, felder, pflicht, daten
        self.erkannt = dict(erkannt)
        self.extras = extras or (lambda: {})
        self.profilname = profilname
        lay = QVBoxLayout(self)
        lay.addWidget(text(hinweis or "Grün = sicher erkannt, gelb = Vorschlag (bitte prüfen), weiß = nicht "
                           "zugeordnet. Felder, die fehlen, blockieren den Import nicht (außer Pflichtfelder *)."))
        p = QHBoxLayout()
        p.addWidget(QLabel("Importprofil:"))
        self.profil = QComboBox()
        self.profil.setMinimumWidth(260)
        p.addWidget(self.profil)
        self.knoepfe = {}
        for name, ziel in (("Laden", self.profil_laden), ("Speichern …", self.profil_speichern),
                           ("Kopieren", self.profil_kopieren), ("Umbenennen …", self.profil_umbenennen),
                           ("Löschen", self.profil_loeschen)):
            k = QPushButton(name)
            k.clicked.connect(lambda _=False, z=ziel: z())
            p.addWidget(k)
            self.knoepfe[name] = k
        p.addStretch(1)
        lay.addLayout(p)
        self.t = QTableWidget(len(felder), 4)
        self.t.setHorizontalHeaderLabels(("Programmfeld", "Spalte der Datei", "Erkennung", "Beispielwerte"))
        self.t.verticalHeader().setVisible(False)
        self.t.verticalHeader().setDefaultSectionSize(26)
        self.t.setColumnWidth(0, 210)
        self.t.setColumnWidth(1, 260)
        self.t.setColumnWidth(2, 330)
        self.t.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.wahl = {}
        kopf = daten["kopf"]
        for r, (feld, titel) in enumerate(felder):
            it = QTableWidgetItem(titel + (" *" if feld in pflicht else ""))
            it.setFlags(Qt.ItemIsEnabled)
            self.t.setItem(r, 0, it)
            c = QComboBox()
            c.addItem(KEINE, None)
            for i, k in enumerate(kopf):
                c.addItem(k or f"Spalte {csv_import.spalte(i)}", i)
            c.currentIndexChanged.connect(lambda _i, f=feld: self._geaendert(f))
            self.wahl[feld] = c
            self.t.setCellWidget(r, 1, c)
            for col in (2, 3):
                x = QTableWidgetItem("")
                x.setFlags(Qt.ItemIsEnabled)
                self.t.setItem(r, col, x)
        lay.addWidget(self.t, 1)
        self.setzen(csv_import.zuordnung(self.erkannt), quelle=None)
        self.profile_laden(profilname)

    # Zuordnung
    def setzen(self, zuordnung, quelle="Profil"):
        for feld, c in self.wahl.items():
            c.blockSignals(True)
            i = zuordnung.get(feld)
            c.setCurrentIndex(0 if i is None or i >= c.count() - 1 else i + 1)
            c.blockSignals(False)
            if quelle and i is not None:
                self.erkannt[feld] = dict(spalte=i, sicherheit=csv_import.SICHER, grund=f"aus Importprofil „{quelle}“")
            elif quelle:
                self.erkannt.pop(feld, None)
            self._zeile(feld)

    def _geaendert(self, feld):
        i = self.wahl[feld].currentData()
        if i is None:
            self.erkannt.pop(feld, None)
        else:
            self.erkannt[feld] = dict(spalte=i, sicherheit="von Hand", grund="von Hand zugeordnet")
        self._zeile(feld)

    def _zeile(self, feld):
        r = [f for f, _t in self.felder].index(feld)
        e = self.erkannt.get(feld)
        i = self.wahl[feld].currentData()
        self.t.item(r, 2).setText(f"{e['sicherheit']}: {e.get('grund') or ''}" if e and i is not None else "")
        self.t.item(r, 2).setToolTip(self.t.item(r, 2).text())
        bsp = []
        if i is not None:
            for z in self.daten["zeilen"]:
                if i < len(z) and str(z[i]).strip():
                    bsp.append(str(z[i]).strip())
                if len(bsp) >= 4:
                    break
        self.t.item(r, 3).setText(" | ".join(bsp))
        farbe = (FARBE_SICHERHEIT.get(e["sicherheit"], BLAU) if e and i is not None else None)
        for col in (0, 2, 3):
            self.t.item(r, col).setBackground(QBrush(stil.farbe(farbe)) if farbe else QBrush())

    def zuordnung(self):
        return {f: c.currentData() for f, c in self.wahl.items() if c.currentData() is not None}

    def pruefen(self):
        z = self.zuordnung()
        fehlt = [t for f, t in self.felder if f in self.pflicht and f not in z]
        if fehlt:
            return "Bitte zuordnen: " + ", ".join(fehlt)
        doppelt = {i for i in z.values() if list(z.values()).count(i) > 1}
        if doppelt:
            namen = ", ".join(self.daten["kopf"][i] or csv_import.spalte(i) for i in sorted(doppelt))
            return f"Diese Spalte ist mehreren Feldern zugeordnet: {namen}"
        if self.profilname:
            csv_import.profil_benutzt(self.db, self.einstellung, self.profilname)
        return ""

    def vorschlaege(self):
        """Felder, die nur als Vorschlag erkannt sind (für den Hinweis im nächsten Schritt)."""
        return [f for f in self.zuordnung() if (self.erkannt.get(f) or {}).get("sicherheit") == csv_import.VORSCHLAG]

    # Importprofile
    def profile_laden(self, waehlen=""):
        self.profil.blockSignals(True)
        self.profil.clear()
        self.profil.addItem("– kein Profil –", "")
        for n in sorted(csv_import.profile(self.db, self.einstellung)):
            self.profil.addItem(n, n)
        i = self.profil.findData(waehlen or "")
        self.profil.setCurrentIndex(max(0, i))
        self.profil.blockSignals(False)

    def _name(self):
        return self.profil.currentData() or ""

    def profil_laden(self, name=None):
        name = name or self._name()
        p = csv_import.profile(self.db, self.einstellung).get(name)
        if not p:
            return False
        _n, _p, sp = csv_import.profil_passend({name: p}, self.daten["kopf"])
        self.setzen(sp or {f: i for f, i in (p.get("spalten") or {}).items() if i < len(self.daten["kopf"])}, name)
        self.profilname = name
        return True

    def profil_speichern(self, name=None):
        if name is None:
            name, ok = QInputDialog.getText(self, "Importprofil speichern", "Name des Profils (z. B. Lieferant):",
                                            text=self._name() or self.profilname)
            if not ok:
                return None
        name = (name or "").strip()
        if not name:
            return None
        csv_import.profil_speichern(self.db, self.einstellung, name, self.daten["kopf"], self.zuordnung(),
                                    dezimal=self.daten.get("dezimal"), **self.extras())
        self.profilname = name
        self.profile_laden(name)
        return name

    def profil_kopieren(self):
        name = self._name()
        neu = csv_import.profil_kopieren(self.db, self.einstellung, name) if name else None
        if neu:
            self.profile_laden(neu)
        return neu

    def profil_umbenennen(self, neu=None):
        alt = self._name()
        if not alt:
            return False
        if neu is None:
            neu, ok = QInputDialog.getText(self, "Importprofil umbenennen", "Neuer Name:", text=alt)
            if not ok:
                return False
        if csv_import.profil_umbenennen(self.db, self.einstellung, alt, (neu or "").strip()):
            self.profilname = neu.strip() if self.profilname == alt else self.profilname
            self.profile_laden(neu.strip())
            return True
        return False

    def profil_loeschen(self, frage=True):
        name = self._name()
        if not name:
            return False
        if frage and QMessageBox.question(self, "Importprofil löschen", f"Profil „{name}“ löschen?") != \
                QMessageBox.Yes:
            return False
        csv_import.profil_loeschen(self.db, self.einstellung, name)
        if self.profilname == name:
            self.profilname = ""
        self.profile_laden()
        return True


# ------------------------------------------------------------------ Tabelle mit Filter (Vorschau-Schritte)
class TabellenSchritt(QWidget):
    """Kopftext, Filter (Gruppen) und Tabelle; fuellen_fn(filter) -> (Zeilen, Farben) füllt die Tabelle."""

    def __init__(self, titel, spalten, breiten=(), filter_=(), kopf_text=""):
        super().__init__()
        self.titel = titel
        lay = QVBoxLayout(self)
        self.kopf = text(kopf_text)
        lay.addWidget(self.kopf)
        oben = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItem("alle Zeilen", None)
        for f in filter_:
            self.filter.addItem(f, f)
        self.filter.currentIndexChanged.connect(lambda _i: self.anzeigen())
        if filter_:
            oben.addWidget(QLabel("Anzeigen:"))
            oben.addWidget(self.filter)
        self.oben = oben
        oben.addStretch(1)
        lay.addLayout(oben)
        self.t = tabelle(spalten, breiten)
        lay.addWidget(self.t, 1)
        self.fuss = text("")
        lay.addWidget(self.fuss)

    def anzeigen(self):
        zeilen, farben = self.zeilen(self.filter.currentData())
        mehr = fuellen(self.t, zeilen, farben)
        self.fuss.setText(f"{len(zeilen):,} Zeilen".replace(",", ".") + (" (angezeigt die ersten 5.000)" if mehr else ""))

    def zeilen(self, _filter):
        return [], []


def fehlerbericht_speichern(parent, inhalt, vorschlag, pfad=None):
    """Fehlerbericht (CSV-Text) speichern; pfad ohne Dialog (Tests). Ergebnis: Pfad oder None."""
    if pfad is None:
        pfad, _ = QFileDialog.getSaveFileName(parent, "Fehlerbericht speichern", str(vorschlag), "CSV (*.csv)")
        if not pfad:
            return None
    Path(pfad).write_text(inhalt, encoding="utf-8", newline="")
    return pfad
