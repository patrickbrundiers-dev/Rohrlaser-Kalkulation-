"""Maschinen-Editor je Maschine (Patrick 16.11.2026: „Einen Maschinen-Editor erstellen je Maschine, übersichtlich
gestalten, so wie jetzt alles in einer Reihe ist zu unübersichtlich“; Aufbau „Liste links, Editor rechts“).

Links die Maschinen, daneben die Gruppen, rechts die Werte der gewählten Gruppe mit Einheit, Erklärung, Richtwert und
„Auf Richtwert zurücksetzen“. Werte, die gerade nicht in die Rechnung eingehen (z. B. der feste Stangenwechsel,
solange er aus Laden, Spannen und Vermessen berechnet wird), stehen grau mit dem Grund daneben. Gespeichert wird über
das Tabellenmodell (gleiche Prüfung, Teilen-Sperre und Admin-Schutz wie in der Tabelle); Rechnung und Daten bleiben
unverändert. Die Tabelle bleibt über „Als Tabelle“ erreichbar."""
import re

from . import stammdaten, zeit_zusatz
from .stammdaten import MASCHINEN, wert_als_text

# (Schlüssel, Titel, Erklärung, Felder): jedes Maschinenfeld steht in genau einer Gruppe (tests/test_maschinen_editor)
GRUPPEN = (
    ("allgemein", "Allgemein", "Name, Laser und Bemerkung der Maschine.",
     ("maschinen_id", "bezeichnung", "laser_kw", "bemerkung")),
    ("stange", "Stange und Spannen",
     "Welche Stangen und Profile die Maschine aufnimmt und was an jeder Stange als Rest bleibt.",
     ("max_stange", "min_stange", "max_huellkreis", "min_huellkreis", "max_kg_m", "max_stange_kg", "kleines_rohr_bis",
      "endbeschnitt", "greiferrest", "min_teil", "duese_min", "sonder_spannbar", "ganze_stange", "stangenende",
      "stangenende_min", "stangenende_max", "abfall_max")),
    ("schnitt", "Konturen und Schnitt",
     "Einteilung der Konturen in klein, mittel und groß, Schnittabstände und Anfahrweg.",
     ("kontur_klein", "kontur_mittel", "kontur_klein_wand", "kontur_mittel_wand", "schnittverlust", "abstand",
      "anfahrweg_zugabe", "anfahrweg", "zeit_kontur", "kanten_innen", "rand_ohne_einstich", "active_tilt",
      "beschleunigung_dick")),
    ("dynamik", "Dynamik und Kopfweg",
     "Eilgang, Beschleunigung und Drehachse: daraus rechnet das Programm Verfahren, Drehen, Ecken und Kopfhub. Der "
     "Kopf bleibt bei kurzen Wegen unten, hebt bei langen Wegen während der Fahrt (Froschsprung) und vor einer "
     "Drehung über die Kante so weit, dass die Ecke darunter durchdreht.",
     ("eilgang_x", "beschl_x", "drehzahl", "beschl_dreh", "beschl_schnitt", "zeit_drehen", "hub_z", "eilgang_z",
      "beschl_z", "zeit_regelung", "hub_ab_weg", "hub_sicherheit", "froschsprung")),
    ("einstechen", "Einstechen",
     "Die Einstechzeit wird aus Wandstärke, Laserleistung und Werkstoff berechnet.",
     ("einstich_grund", "einstich_ueberwachung")),
    ("laden", "Laden und Stangenwechsel",
     "Stangenwechsel = Laden + Spannen + Vermessen + Einziehen (mit Eilgang X); mit Schweißnaht-Vorgabe kommt "
     "„Schweißnaht suchen“ dazu.",
     ("zeit_laden", "laden_parallel", "zeit_spannen", "zeit_vermessen", "zeit_naht", "stangenwechsel",
      "stangenwechsel_sn", "schwer_ab_kg", "zeit_schwer", "zeit_ausrichten", "lademinimum")),
    ("entladen", "Entladen und Nebenzeit",
     "Nebenzeit je Teil = Ausschieben (mit Eilgang X) + Entladen; Entladen = Grundzeit + Zeit je m + Zeit je kg.",
     ("entladen_grund", "entladen_je_m", "entladen_je_kg", "zeit_entladen", "zeit_teil", "entlade_laenge",
      "entlade_kg", "zeit_entnahme", "handling_laenge", "handling_kg", "zeit_handling")),
    ("messen", "Messen und von Hand",
     "Messzyklen aus Antastweg und -geschwindigkeit; Arbeit von Hand aus Grundzeit, Gewicht und Länge.",
     ("antast_weg", "antast_v", "zeit_messen_schnell", "zeit_messen_sorgfaeltig", "hand_grund", "hand_je_kg",
      "hand_je_m", "zeit_hand_laden")),
    ("d3", "3D-Bearbeitung", "Schwenkkopf: Winkelbereich, Greifmaß und Zuschläge.",
     ("d3", "schwenk_min", "schwenk_max", "schwenk_ueber", "greif_3d", "zeit_3d", "faktor_3d", "param_3d")),
    ("kosten", "Stundensatz, Gas und Schicht",
     "Stundensatz von Hand oder ermittelt, Schneidgas, Rüsten, Schicht und mannlose Fertigung.",
     ("stundensatz", "satz_art", "gas_zusatz", "anschaffung", "nutzungsdauer", "flaeche", "instandhaltung",
      "wartung", "leistung_kw", "last_anteil", "verschleiss", "bediener_anteil", "gas_n2", "gas_o2", "gas_luft",
      "ruestzeit", "ruest_form", "ruest_sonder", "schicht_stunden", "sperrtage", "mannlos_ab", "mannlos_satz")),
    ("kalibrierung", "Kalibrierung",
     "Faktoren je Baustein aus den Ist-Zeiten der Nachkalkulation (Kalibrieren in den Schneiddaten); leer = 1.",
     ("faktor_schneiden", "faktor_einstechen", "faktor_ecken", "faktor_bewegen", "faktor_neben")),
)

# Vorsilben, die der Gruppentitel schon sagt
_VORSILBEN = ("Dynamik: ", "Ermittlung: ", "3D: ", "Kalibrierung: ", "Schicht: ", "Mannlos: ", "Messen: ",
              "Von Hand: ", "Entladen: ", "Stangenende: ", "Stangenwechsel berechnen: ", "Nebenzeit berechnen: ",
              "Entladen berechnen: ", "Anfahrweg berechnen: ", "Einstechen berechnen: ", "Kopfweg: ")
_KLAMMER = re.compile(r"\s*\(([^()]*)\)\s*$")


def gruppe_von(feld):
    return next((g[0] for g in GRUPPEN if feld in g[3]), None)


def beschriftung(f):
    """(Bezeichnung, Zusatz in Klammern oder '') aus dem Feldtitel, ohne die Vorsilbe der Gruppe."""
    t = f.titel
    for v in _VORSILBEN:
        if t.startswith(v):
            t = t[len(v):]
            t = t[0].upper() + t[1:]
            break
    zusatz = ""
    m = _KLAMMER.search(t)
    if m and not m.group(1).startswith(("°", "mm", "s", "kg", "m", "€", "%", "kW", "U/", "×")):
        zusatz, t = m.group(1), t[:m.start()]
    return t, zusatz


_RICHT = ((stammdaten.DYNAMIK_FELDER, stammdaten.DYNAMIK_RICHTWERTE),
          (stammdaten.EINSTICH_FELDER, stammdaten.EINSTICH_RICHTWERTE),
          (stammdaten.ZEITEN_FELDER, stammdaten.ZEITEN_RICHTWERTE),
          (stammdaten.KOPFWEG_FELDER, stammdaten.KOPFWEG_RICHTWERTE))


def richtwert(feld, maschinen_id):
    """Mitgelieferter Richtwert des Felds für die Maschine (T03, T11, LT7; andere Maschinen: Werte der T11), sonst
    None."""
    for felder, werte in _RICHT:
        if feld in felder:
            reihe = werte.get(maschinen_id) or werte.get("T11")
            return reihe[felder.index(feld)] if reihe else None
    return None


def _zahl(w):
    return isinstance(w, (int, float)) and not isinstance(w, bool)


def _leer(w):
    return w in (None, "")


def nicht_wirksam(feld, m):
    """Grund, warum der Wert gerade nicht in die Rechnung eingeht (Text), sonst None."""
    m = m or {}
    if feld in ("stangenwechsel", "stangenwechsel_sn") and zeit_zusatz.stangenwechsel_berechnet(m) is not None:
        return "wird berechnet (Laden + Spannen + Vermessen + Einziehen)"
    if feld in ("laden_parallel", "zeit_spannen", "zeit_vermessen", "zeit_naht") and not _zahl(m.get("zeit_laden")):
        return "gilt erst, wenn „Laden“ eingetragen ist"
    if feld == "zeit_entladen" and _zahl(m.get("entladen_grund")):
        return "wird berechnet (Grundzeit + je m + je kg)"
    if feld in ("entladen_je_m", "entladen_je_kg") and not _zahl(m.get("entladen_grund")):
        return "gilt erst mit einer Grundzeit"
    if feld == "zeit_teil" and zeit_zusatz.nebenzeit_s(m, {"laenge": 1000}) is not None:
        return "wird berechnet (Ausschieben + Entladen)"
    if feld in ("zeit_messen_schnell", "zeit_messen_sorgfaeltig") and zeit_zusatz.messung_s(m, "schnell") is not None:
        return "wird aus Antastweg und -geschwindigkeit berechnet"
    if feld == "zeit_hand_laden" and _zahl(m.get("hand_grund")):
        return "wird aus den Von-Hand-Werten berechnet"
    if feld in ("hand_je_kg", "hand_je_m") and not _zahl(m.get("hand_grund")):
        return "gilt erst mit einer Grundzeit"
    if feld == "anfahrweg" and _zahl(m.get("anfahrweg_zugabe")):
        return "wird berechnet (Materialstärke + Zugabe)"
    if feld in ("eilgang_z", "beschl_z", "zeit_regelung", "hub_ab_weg", "hub_sicherheit", "froschsprung") \
            and not _zahl(m.get("hub_z")):
        return "gilt erst mit einem Kopfhub"
    if feld in ("hub_sicherheit", "froschsprung") and not _zahl(m.get("hub_ab_weg")):
        return "gilt erst mit „Kopf heben ab Weg“"
    if feld in GRUPPEN[8][3][1:] and m.get("d3") != "ja":
        return "gilt nur mit 3D-Bearbeitung"
    if feld in ("anschaffung", "nutzungsdauer", "flaeche", "instandhaltung", "wartung", "leistung_kw", "last_anteil",
                "verschleiss", "bediener_anteil") and m.get("satz_art") != "ermittelt":
        return "gilt nur bei Stundensatz „ermittelt“"
    if feld in ("stangenende_min", "stangenende_max") and m.get("stangenende") != "ja":
        return "gilt nur mit „Teil am Stangenende“"
    if feld == "mannlos_satz" and _leer(m.get("mannlos_ab")):
        return "gilt erst mit „ab Laufzeit je Los“"
    if feld == "zeit_schwer" and _leer(m.get("schwer_ab_kg")):
        return "gilt erst mit „Schwere Stange ab“"
    if feld == "zeit_handling" and _leer(m.get("handling_laenge")) and _leer(m.get("handling_kg")):
        return "gilt erst mit einer Grenze Länge oder Gewicht"
    return None


def _s(t):
    return f"{t:.1f} s".replace(".", ",")


def ergebnis(gruppe, m):
    """Kurzer Rechenweg der Gruppe mit den aktuellen Werten (Text) oder ''."""
    m = m or {}
    if gruppe == "laden":
        b = zeit_zusatz.stangenwechsel_berechnet(m)
        if b:
            return f"Stangenwechsel berechnet: {_s(b[0])}, mit Schweißnaht {_s(b[1])} (Stange " \
                   f"{wert_als_text(MASCHINEN.feld('max_stange'), m.get('max_stange')) or '6500'} mm)"
        return "Stangenwechsel fest: " + (_s(m["stangenwechsel"]) if _zahl(m.get("stangenwechsel")) else "leer")
    if gruppe == "entladen":
        p = {"laenge": 1000}
        ent = zeit_zusatz.entladen_s(m, p)
        neben = zeit_zusatz.nebenzeit_s(m, p)
        if neben is not None:
            return f"Beispiel Teil 1 m: Entladen {_s(ent)}, Nebenzeit je Teil {_s(neben)} (ohne Gewicht)"
        return "Nebenzeit je Teil fest: " + (_s(m["zeit_teil"]) if _zahl(m.get("zeit_teil")) else "leer")
    if gruppe == "messen":
        teile = []
        for art in ("schnell", "sorgfältig"):
            t = zeit_zusatz.messung_s(m, art)
            if t is not None:
                teile.append(f"Messung {art} {_s(t)}")
        h = zeit_zusatz.hand_s(m, 30, 6000)
        if h is not None:
            teile.append(f"Stange 6 m, 30 kg von Hand {_s(h)}")
        return "; ".join(teile)
    if gruppe == "dynamik":
        from . import dynamik
        if dynamik.kopfweg_aktiv(m) and dynamik.aktiv_verfahren(m):
            pr = {"form": "Quadratrohr", "a": 60, "b": 60, "wand": 3}
            kurz = dynamik.leerweg_art((0, 0), (10, 0), m, pr)
            lang = dynamik.leerweg_art((0, 0), (200, 0), m, pr)
            dreh = dynamik.leerweg_art((0, 0), (0, 90), m, pr)
            return (f"Beispiel Quadratrohr 60 × 60: 10 mm {kurz['t_s']:.2f} s, 200 mm {lang['t_s']:.2f} s "
                    f"({'Froschsprung' if m.get('froschsprung') != 'nein' else 'heben, fahren, senken'}), Drehen "
                    f"über die Kante {dreh['t_s']:.2f} s (Kopf {dreh['hoehe_mm']:.0f} mm hoch)").replace(".", ",")
        h = zeit_zusatz.hub_s(m)
        return f"Kopfhub je Kontur {h:.2f} s".replace(".", ",") if h is not None else ""
    return ""


def _widgets():
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                                   QListWidgetItem, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget)
    from . import design
    from .einstellungen_nav import SeitenStapel

    class Wertzeile:
        """Bezeichnung, Eingabe, Richtwert-Knopf und Hinweis eines Felds im Raster einer Gruppe."""

        def __init__(self, editor, raster, reihe, f):
            self.editor, self.f = editor, f
            text, zusatz = beschriftung(f)
            self.name = QLabel(text)
            self.name.setToolTip(f.titel)
            self.name.setWordWrap(True)
            if f.art == "auswahl":
                self.eingabe = QComboBox()
                self.eingabe.activated.connect(lambda _i: self.speichern(self.eingabe.currentText()))
            else:
                self.eingabe = QLineEdit()
                self.eingabe.setMaximumWidth(260 if f.art == "text" else 130)
                if f.art in ("zahl", "ganz"):
                    self.eingabe.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.eingabe.editingFinished.connect(lambda: self.speichern(self.eingabe.text()))
            self.eingabe.setToolTip(f.titel)
            self.eingabe.setObjectName(f"maschine_{f.name}")
            self.zurueck = QToolButton()
            self.zurueck.setText("↺")
            self.zurueck.setAutoRaise(True)
            self.zurueck.clicked.connect(self.auf_richtwert)
            self.hinweis = QLabel()
            self.hinweis.setWordWrap(True)
            self.hinweis.setStyleSheet(f"color: {design.TEXT_GRAU};")
            self.zusatz = zusatz
            raster.addWidget(self.name, reihe, 0)
            raster.addWidget(self.eingabe, reihe, 1)
            raster.addWidget(self.zurueck, reihe, 2)
            raster.addWidget(self.hinweis, reihe, 3)

        def zeigen(self, m, auswahl):
            f, w = self.f, m.get(self.f.name)
            text = wert_als_text(f, w, bearbeiten=True) or ""
            self.eingabe.blockSignals(True)
            if isinstance(self.eingabe, QComboBox):
                self.eingabe.clear()
                self.eingabe.addItems([""] + [str(a) for a in auswahl(f.auswahl)])
                if text and self.eingabe.findText(text) < 0:
                    self.eingabe.addItem(text)
                self.eingabe.setCurrentText(text)
            else:
                self.eingabe.setText(text)
            self.eingabe.blockSignals(False)
            self.richt = richtwert(f.name, m.get("maschinen_id"))
            rt = wert_als_text(f, self.richt) if self.richt is not None else ""
            if isinstance(self.eingabe, QLineEdit):
                self.eingabe.setPlaceholderText(f"Richtwert {rt}" if rt else "leer")
            abw = self.richt is not None and not _gleich(w, self.richt)
            self.zurueck.setVisible(abw)
            self.zurueck.setToolTip(f"Auf Richtwert {rt} zurücksetzen" if rt else "")
            grund = nicht_wirksam(f.name, m)
            teile = [t for t in (self.zusatz, f"Richtwert {rt}" if abw and rt else "", grund) if t]
            self.hinweis.setText(" · ".join(teile))
            self.name.setStyleSheet(f"color: {design.TEXT_GRAU};" if grund else "")
            self.eingabe.setEnabled(not self.editor.gesperrt())

        def speichern(self, text):
            self.editor.speichern(self.f.name, text)

        def auf_richtwert(self):
            if self.richt is not None:
                self.editor.speichern(self.f.name, wert_als_text(self.f, self.richt, bearbeiten=True))

    def _gleich(a, b):
        if _zahl(a) and _zahl(b):
            return abs(a - b) < 1e-9
        return a == b

    class MaschinenEditor(QWidget):
        """Liste der Maschinen, Gruppen und Werte der gewählten Maschine; seite = StammdatenSeite der Maschinen
        (Modell, Filter und Tabellenansicht, deren Auswahl die Knöpfe Stundensatz/Datei/Löschen nutzen)."""
        gewaehlt = Signal(int)

        def __init__(self, seite):
            super().__init__()
            self.seite, self.modell, self.filter = seite, seite.modell, seite.filter
            self._ruhe = False
            self.liste = QListWidget()
            self.liste.setObjectName("maschinen_liste")
            self.liste.setMaximumWidth(230)
            self.liste.setMinimumWidth(150)
            self.liste.currentRowChanged.connect(self._maschine_gewaehlt)
            self.gruppen = QListWidget()
            self.gruppen.setObjectName("maschinen_gruppen")
            self.gruppen.setMaximumWidth(210)
            self.gruppen.setMinimumWidth(150)
            self.stapel = SeitenStapel()
            self.kopf = QLabel()
            self.kopf.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {design.AKZENT};")
            self.pruefung = QLabel()
            self.pruefung.setWordWrap(True)
            self.zeilen = {}
            self.ergebnisse = {}
            for schl, titel, erkl, felder in GRUPPEN:
                QListWidgetItem(titel, self.gruppen)
                seite_w = QWidget()
                lay = QVBoxLayout(seite_w)
                t = QLabel(titel)
                t.setStyleSheet("font-size: 14px; font-weight: 600;")
                e = QLabel(erkl)
                e.setWordWrap(True)
                e.setStyleSheet(f"color: {design.TEXT_GRAU};")
                lay.addWidget(t)
                lay.addWidget(e)
                erg = QLabel()
                erg.setWordWrap(True)
                erg.setStyleSheet(f"background: {design.BLAU_FLAECHE}; color: {design.TEXT}; padding: 4px 8px; "
                                  "border-radius: 4px;")
                self.ergebnisse[schl] = erg
                lay.addWidget(erg)
                raster = QGridLayout()
                raster.setColumnStretch(3, 1)
                raster.setColumnMinimumWidth(0, 200)
                for i, name in enumerate(felder):
                    self.zeilen[name] = Wertzeile(self, raster, i, MASCHINEN.feld(name))
                lay.addLayout(raster)
                lay.addStretch(1)
                rahmen = QScrollArea()
                rahmen.setWidgetResizable(True)
                rahmen.setFrameShape(QFrame.NoFrame)
                rahmen.setWidget(seite_w)
                self.stapel.addWidget(rahmen)
            for liste in (self.liste, self.gruppen):
                liste.setStyleSheet("QListWidget::item { padding: 6px 8px; }")
            self.gruppen.currentRowChanged.connect(self.stapel.setCurrentIndex)
            self.gruppen.setCurrentRow(0)
            rechts = QVBoxLayout()
            rechts.addWidget(self.kopf)
            rechts.addWidget(self.pruefung)
            rechts.addWidget(self.stapel, 1)
            lay = QHBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self.liste)
            lay.addWidget(self.gruppen)
            lay.addLayout(rechts, 1)
            self.stapel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.modell.modelReset.connect(self.auffrischen)
            self.filter.layoutChanged.connect(self.auffrischen)
            self.filter.rowsInserted.connect(self.auffrischen)
            self.filter.rowsRemoved.connect(self.auffrischen)
            sm = seite.ansicht.selectionModel()
            sm.currentRowChanged.connect(lambda i, _a: self._aus_tabelle(i.row()))
            self.auffrischen()

        def gesperrt(self):
            return bool(self.modell.admin_gesperrt)

        def _reihen(self):
            return [self.filter.mapToSource(self.filter.index(r, 0)).row() for r in range(self.filter.rowCount())]

        def auffrischen(self, *_):
            mid = self.aktuelle_id()
            self._ruhe = True
            self.liste.clear()
            self._quelle = self._reihen()
            for r in self._quelle:
                z = self.modell.daten[r]
                text = str(z.get("maschinen_id") or "(neu)")
                if z.get("bezeichnung") or z.get("bemerkung"):
                    text += " – " + " ".join(str(z[k]) for k in ("bezeichnung", "bemerkung") if z.get(k))
                QListWidgetItem(text, self.liste)
            ziel = next((i for i, r in enumerate(self._quelle) if self.modell.daten[r].get("maschinen_id") == mid), 0)
            self._ruhe = False
            if self._quelle:
                self.liste.setCurrentRow(ziel)
                self._maschine_gewaehlt(ziel)
            else:
                self.zeigen(None)

        def aktuelle_id(self):
            z = self.aktuelle_zeile()
            return z.get("maschinen_id") if z else None

        def aktuelle_zeile(self):
            i = self.liste.currentRow()
            q = getattr(self, "_quelle", [])
            return self.modell.daten[q[i]] if 0 <= i < len(q) and q[i] < len(self.modell.daten) else None

        def _maschine_gewaehlt(self, i):
            if self._ruhe or not (0 <= i < len(self._quelle)):
                return
            r = self._quelle[i]
            ansicht = self.seite.ansicht
            pr = self.filter.mapFromSource(self.modell.index(r, 0)).row()
            if pr >= 0 and ansicht.currentIndex().row() != pr:
                self._ruhe = True
                ansicht.selectRow(pr)
                self._ruhe = False
            self.zeigen(self.modell.daten[r])
            self.gewaehlt.emit(r)

        def _aus_tabelle(self, pr):
            if self._ruhe or pr < 0:
                return
            r = self.filter.mapToSource(self.filter.index(pr, 0)).row()
            if r in self._quelle and self.liste.currentRow() != self._quelle.index(r):
                self.liste.setCurrentRow(self._quelle.index(r))

        def zeigen(self, m):
            self.stapel.setEnabled(m is not None)
            if m is None:
                self.kopf.setText("Keine Maschine – „Neue Zeile“ legt eine an.")
                self.pruefung.setText("")
                return
            self.kopf.setText(" – ".join(str(m[k]) for k in ("maschinen_id", "bezeichnung") if m.get(k)) or "(neu)")
            p = str(stammdaten.pruefen(MASCHINEN, m, self.modell.k) or "")
            self.pruefung.setText("Prüfung: " + (p or "OK"))
            farbe = design.ORANGE if p.startswith(("FEHLER", "WARNUNG")) else design.TEXT_GRAU
            self.pruefung.setStyleSheet(f"color: {farbe};")
            for z in self.zeilen.values():
                z.zeigen(m, self.modell.k.auswahl)
            for schl, lab in self.ergebnisse.items():
                t = ergebnis(schl, m)
                lab.setText(t)
                lab.setVisible(bool(t))

        def gruppe_zeigen(self, schluessel):
            i = [g[0] for g in GRUPPEN].index(schluessel)
            self.gruppen.setCurrentRow(i)

        def speichern(self, feld, text):
            """Wert über das Tabellenmodell speichern (gleiche Prüfung und Meldungen wie in der Tabelle)."""
            i = self.liste.currentRow()
            if not (0 <= i < len(self._quelle)):
                return False
            r = self._quelle[i]
            spalte = next(c for c, (art, f) in enumerate(self.modell.spalten) if art == "feld" and f.name == feld)
            ok = self.modell.setData(self.modell.index(r, spalte), text)
            if not ok:
                self.zeigen(self.modell.daten[r] if r < len(self.modell.daten) else None)
            return ok

    return MaschinenEditor


def MaschinenEditor(seite):
    return _widgets()(seite)
