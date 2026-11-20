"""Fenster „Importanalyse“ und Schrittleiste des STEP-Prüfdialogs (Importengine, Laserhub-Vergleich, Patrick
20.11.2026, Abschnitt 8 „Benutzeroberfläche modernisieren“).

Schrittleiste: ① Import › ② Analyse › ③ Ergebnis › ④ Kontrolle › ⑤ Korrektur › ⑥ Kalkulation – oben im Prüfdialog,
mit den Zahlen dieses Imports (Dateien, Teile, sicher/prüfen, nicht lesbare Dateien). Kontrolle und Korrektur bleiben
im Prüfdialog (3D, Art, Profil, „Passt“), Kalkulation ist „Übernehmen“.

Importanalyse (Knopf im Prüfdialog), alles aus bauteil_analyse/baugruppe_analyse, nichts wird neu gemessen:
- Bauteile: je verschiedenes Teil Kategorie, Konfidenz, Stufe, Profil, Länge, Anzahl, Bearbeitungen, Komplexität
- Merkmale: alle erkannten Bearbeitungen des gewählten Teils mit Lage, Abmessung, Orientierung, Schnittlänge,
  Bearbeitung und Konfidenz
- Baugruppen: Struktur (Knoten), gleiche Teile mit Stückzahl, Varianten, Schweißverbindungen, Materialbedarf
- Dateien: Befunde des Imports (ZIP, Herstellerformate, leere/defekte/doppelte Dateien)
„Bauteilliste als CSV …“ speichert die Bauteilliste.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHeaderView, QLabel, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from . import bauteil_analyse as ba
from . import baugruppe_analyse as bga
from . import stil

STUFE_FARBE = {"sicher": stil.GRUEN, "prüfen": "#B7791F", "unsicher": stil.ROT}
SCHRITTE = ("Import", "Analyse", "Ergebnis", "Kontrolle", "Korrektur", "Kalkulation")
ZIFFERN = "①②③④⑤⑥"


def schritt_zahlen(messwerte):
    """Zahlen für die Schrittleiste: dict(dateien, teile, sicher, pruefen, unsicher, nicht_lesbar, hinweise)."""
    ba.analysieren(messwerte)
    befunde = next((m["_import_befunde"] for m in messwerte if m.get("_import_befunde")), [])
    stufen = [ba.von(m)["stufe"] for m in messwerte if not m.get("_import_befund")]
    return dict(dateien=len({m.get("datei") for m in messwerte if not m.get("_import_befund")}),
                teile=len(stufen), sicher=stufen.count("sicher"), pruefen=stufen.count("prüfen"),
                unsicher=stufen.count("unsicher"),
                nicht_lesbar=sum(1 for b in befunde if b.get("stufe") == "Fehler" and b.get("datei") != "andere Dateien"),
                hinweise=sum(1 for b in befunde if b.get("stufe") == "Hinweis"))


def schritt_html(z, aktiv=3, ampel=None):
    """HTML der Schrittleiste; aktiv = Index des aktuellen Schritts (0 … 5). ampel = (sicher, prüfen, nicht
    übernehmbar) aus dem Prüfdialog (Zeilen gleicher Teile, mit fehlenden Profilen): dann zählt die Leiste genau wie
    die Zeile „Erkennung“ unter der Liste."""
    if ampel is not None:
        z = dict(z, sicher=ampel[0], pruefen=ampel[1], unsicher=ampel[2])
    texte = [
        f"{z['dateien']} Datei{'en' if z['dateien'] != 1 else ''}"
        + (f", <span style='color:{stil.ROT}'>{z['nicht_lesbar']} nicht lesbar</span>" if z["nicht_lesbar"] else ""),
        f"{z['teile']} Teil{'e' if z['teile'] != 1 else ''}",
        f"<span style='color:{stil.GRUEN}'>{z['sicher']} sicher</span>"
        + (f" · <span style='color:#B7791F'>{z['pruefen']} prüfen</span>" if z["pruefen"] else "")
        + (f" · <span style='color:{stil.ROT}'>{z['unsicher']} "
           f"{'nicht übernehmbar' if ampel is not None else 'unsicher'}</span>" if z["unsicher"] else ""),
        "3D, Merkmale", "Art, Profil, Passt", "Übernehmen"]
    teile = []
    for i, (name, text) in enumerate(zip(SCHRITTE, texte)):
        fertig = i <= 2         # Import, Analyse und Ergebnis liegen vor, wenn der Prüfdialog offen ist
        stil_ = "font-weight:600;" if i == aktiv else ""
        zeichen = " ✓" if fertig else ""
        teile.append(f"<span style='{stil_}'>{ZIFFERN[i]} {name}{zeichen}</span> "
                     f"<span style='color:{stil.TEXT_GRAU}'>{text}</span>")
    return " &nbsp;›&nbsp; ".join(teile)


def schrittleiste(messwerte):
    """QLabel mit der Schrittleiste für den Prüfdialog (lab.zahlen merkt die Zahlen für auffrischen)."""
    zahlen = schritt_zahlen(messwerte)
    lab = QLabel(schritt_html(zahlen))
    lab.zahlen = zahlen
    lab.setObjectName("schrittleiste")
    lab.setTextFormat(Qt.RichText)
    lab.setWordWrap(True)
    lab.setToolTip("Ablauf des Imports: Import und Analyse sind erledigt; hier prüfen (3D, Merkmale), bei Bedarf "
                   "korrigieren (Art, Profil, „Passt“) und mit „Übernehmen“ in die Kalkulation geben. Unsichere "
                   "Erkennungen werden nie unbemerkt übernommen: sie bleiben gelb, bis sie bestätigt sind.")
    return lab


def auffrischen(lab, ampel):
    """Schrittleiste mit den Zahlen der Erkennungs-Ampel des Prüfdialogs; alles sicher: Schritt ⑥ Kalkulation."""
    aktiv = 3 if (ampel[1] or ampel[2]) else 5
    lab.setText(schritt_html(lab.zahlen, aktiv, ampel))


def _item(text, farbe=None, rechts=False, tipp=None):
    it = QTableWidgetItem("" if text is None else str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if farbe:
        it.setForeground(QBrush(stil.farbe(farbe)))
    if rechts:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if tipp:
        it.setToolTip(tipp)
    return it


def _zahl(x, st=1):
    try:
        return f"{round(float(x), st):g}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


DATEI_SPALTEN = ("Datei", "Körper", "Volumenkörper", "Einheit", "Geometrie", "Anforderungen")


def datei_anforderungen(messwerte):
    """Je gemessener Datei: Körper, Volumenkörper (oder aus Flächen genäht/offen), Einheit, Geometrieprüfung und eine
    Bewertung wie bei Laserhub „Volumenkörper in mm“ (nur Anzeige, die Messung hat genäht bzw. umgerechnet)."""
    je = {}
    for m in messwerte or ():
        if m.get("_import_befund"):
            continue
        je.setdefault(m.get("datei") or "", []).append(m)
    out = []
    for datei, liste in je.items():
        arten = {}
        for m in liste:
            a = m.get("koerperart") or ("" if m.get("fehler") else "Volumenkörper")
            if a:
                arten[a] = arten.get(a, 0) + 1
        einheiten = sorted({str(m.get("einheit")) for m in liste if m.get("einheit")})
        ungueltig = sum(1 for m in liste if m.get("gueltig") in ("0", "False", "nein", False))
        fehler = sum(1 for m in liste if m.get("fehler"))
        hinweise = []
        if any(a != "Volumenkörper" for a in arten):
            hinweise.append("Flächenmodell: genäht – Ergebnis prüfen" if "Flächenmodell offen" not in arten
                            else "offenes Flächenmodell: Volumen nicht messbar, bitte Volumenkörper anfordern")
        if einheiten and any(e.lower() not in ("mm", "millimeter", "millimetre") for e in einheiten):
            hinweise.append(f"Einheit {', '.join(einheiten)}: in mm umgerechnet")
        if ungueltig:
            hinweise.append(f"{ungueltig} Körper geometrisch ungültig")
        if fehler:
            hinweise.append(f"{fehler} Körper nicht messbar")
        out.append(dict(datei=datei, koerper=len(liste),
                        volumen=", ".join(f"{n}× {a}" if len(arten) > 1 else a for a, n in arten.items()),
                        einheit=", ".join(einheiten) or "mm", gueltig="geprüft, gültig" if not ungueltig
                        else f"{ungueltig} ungültig", ok=not hinweise,
                        bewertung="; ".join(hinweise) or "erfüllt: Volumenkörper in mm"))
    return out


class ImportanalyseDialog(QDialog):
    BAUTEIL_SPALTEN = ("Datei", "Pos.", "Bezeichnung", "Anzahl", "Kategorie", "Konfidenz", "Profil", "Länge [mm]",
                       "Bearbeitungen", "Fertigbar", "Komplexität", "Unsicherheiten")
    MERKMAL_SPALTEN = ("Merkmal", "x [mm]", "Lage", "Abmessung", "Orientierung", "Schnittlänge [mm]", "Bearbeitung",
                       "Konfidenz", "Hinweis")

    def __init__(self, parent, messwerte, ampel=None):
        """ampel = (sicher, prüfen, nicht übernehmbar) des Prüfdialogs für die Schrittleiste (mit fehlenden
        Stammdaten-Profilen); die Konfidenz in der Liste bewertet die Erkennung der Geometrie."""
        super().__init__(parent)
        self.setWindowTitle("Importanalyse")
        self.resize(1200, 680)
        self.messwerte = messwerte
        ba.analysieren(messwerte, neu=True)        # Stand nach den Korrekturen im Prüfdialog
        self.dateien = bga.alle(messwerte)
        self.summe = bga.zusammenfassung(self.dateien)
        lay = QVBoxLayout(self)
        z = schritt_zahlen(messwerte)
        kopf = QLabel(schritt_html(z, aktiv=3, ampel=ampel))
        kopf.setTextFormat(Qt.RichText)
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        kat = ", ".join(f"{n} {k}" for k, n in sorted(self.summe["kategorien"].items(), key=lambda x: -x[1]))
        info = QLabel(f"{self.summe['koerper']} Körper in {self.summe['dateien']} Datei(en), "
                      f"{self.summe['verschiedene']} verschiedene Teile, {self.summe['baugruppen']} Rohrlaser-"
                      f"Baugruppe(n) · {kat}")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.reiter = QTabWidget()
        lay.addWidget(self.reiter, 1)
        self._bauteile_reiter()
        self._baugruppen_reiter()
        self._dateien_reiter()
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.button(QDialogButtonBox.Close).setText("Schließen")
        self.csv_knopf = QPushButton("Bauteilliste als CSV …")
        self.csv_knopf.clicked.connect(lambda: self.csv_speichern())
        knoepfe.addButton(self.csv_knopf, QDialogButtonBox.ActionRole)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    # ------------------------------------------------------------------ Bauteile + Merkmale
    def _bauteile_reiter(self):
        w = QSplitter(Qt.Vertical)
        self.bauteile = QTableWidget(0, len(self.BAUTEIL_SPALTEN))
        self.bauteile.setHorizontalHeaderLabels(self.BAUTEIL_SPALTEN)
        self.bauteile.horizontalHeaderItem(5).setToolTip(
            "Wie sicher die Geometrie erkannt ist (Ampel: grün ab 90 %, gelb 50–89 %, rot darunter). Ob das Profil "
            "in den Stammdaten fehlt, zeigt der Prüfdialog in der Spalte Hinweis.")
        self.bauteile.setSelectionBehavior(QTableWidget.SelectRows)
        self.bauteile.setSelectionMode(QTableWidget.SingleSelection)
        self.bauteile.verticalHeader().setVisible(False)
        self.zeilen = []
        for d in self.dateien:
            for p in d["positionen"]:
                self.zeilen.append((d, p))
        self.bauteile.setRowCount(len(self.zeilen))
        for r, (d, p) in enumerate(self.zeilen):
            a = ba.von(self.messwerte[p["indizes"][0]])
            bearb = ", ".join(f"{n}× {k}" for k, n in p["merkmale"].items() if k not in (ba.M_GERADE, ba.M_FERTIG))
            fb = self.messwerte[p["indizes"][0]].get("_fertigbarkeit")
            fertig = "nicht geprüft" if fb is None else "ja" if not fb else f"prüfen ({len(fb)})"
            kat = p["kategorie"] + (f" ({p['unterart']})" if p["unterart"] else "")
            werte = (d["datei"], p["nr"], p["bezeichnung"], p["anzahl"], kat, f"{p['konfidenz']} % {p['stufe']}",
                     p["profil"], _zahl(p["laenge"]), bearb, fertig, p["komplexitaet"],
                     "; ".join(a.get("unsicherheiten") or ()) or p["fehler"])
            for c, v in enumerate(werte):
                farbe = STUFE_FARBE.get(p["stufe"]) if c == 5 else STUFE_FARBE.get("prüfen") if c == 9 and fb else None
                tipp = str(v) if c in (8, 11) else "\n".join(x.get("text", "") for x in fb) if c == 9 and fb else None
                it = _item(v, farbe, c in (1, 3, 7), tipp=tipp)
                self.bauteile.setItem(r, c, it)
        self.bauteile.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.bauteile.horizontalHeader().setStretchLastSection(True)
        self.bauteile.itemSelectionChanged.connect(self._merkmale_zeigen)
        w.addWidget(self.bauteile)
        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        self.merkmal_titel = QLabel("Merkmale: Teil oben wählen")
        ul.addWidget(self.merkmal_titel)
        self.merkmale = QTableWidget(0, len(self.MERKMAL_SPALTEN))
        self.merkmale.setHorizontalHeaderLabels(self.MERKMAL_SPALTEN)
        self.merkmale.verticalHeader().setVisible(False)
        self.merkmale.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.merkmale.horizontalHeader().setStretchLastSection(True)
        ul.addWidget(self.merkmale)
        w.addWidget(unten)
        w.setSizes([380, 260])
        self.reiter.addTab(w, f"Bauteile ({len(self.zeilen)})")
        if self.zeilen:
            self.bauteile.selectRow(0)

    def _merkmale_zeigen(self):
        r = self.bauteile.currentRow()
        if r < 0 or r >= len(self.zeilen):
            return
        d, p = self.zeilen[r]
        a = ba.von(self.messwerte[p["indizes"][0]])
        liste = sorted(a.get("merkmale") or [], key=lambda x: x.get("merkmal") != ba.M_FERTIG)    # Verstöße zuerst
        k = a.get("kennzahlen") or {}
        self.merkmal_titel.setText(
            f"<b>Pos. {p['nr']} {p['bezeichnung']}</b>: {ba.kurztext(a)} · Wand {_zahl(k.get('wand'), 2)} mm, "
            f"Länge {_zahl(k.get('laenge'))} mm, Querschnitt {_zahl(k.get('querschnitt'))} mm², Volumen "
            f"{_zahl(k.get('volumen_cm3'), 2)} cm³, Gewicht (Stahl) {_zahl(k.get('gewicht_stahl_kg'), 3)} kg, "
            f"Schneidweg {_zahl(k.get('schneidweg'))} mm, {k.get('einstiche', 0)} Einstiche")
        self.merkmale.setRowCount(len(liste))
        for r_, x in enumerate(liste):
            lage = x.get("seite") or (f"{_zahl(x.get('winkel'))}°" if x.get("winkel") is not None else "") or \
                (f"Ende {x['ende']}" if x.get("ende") else "")
            anz = f"{x['anzahl']}× " if (x.get("anzahl") or 1) > 1 else ""
            stufe = "sicher" if x.get("konfidenz", 0) >= ba.GRUEN_AB else "prüfen" if x.get("konfidenz", 0) >= 70 \
                else "unsicher"
            werte = (anz + x.get("merkmal", ""), _zahl(x.get("x")) if x.get("x") is not None else "", lage,
                     x.get("abmessung") or "", x.get("orientierung") or "", _zahl(x.get("schnittlaenge")),
                     x.get("bearbeitung") or "", f"{x.get('konfidenz', 0)} %", x.get("hinweis") or "")
            for c, v in enumerate(werte):
                self.merkmale.setItem(r_, c, _item(v, STUFE_FARBE.get(stufe) if c == 7 else None, c in (1, 5, 7)))

    # ------------------------------------------------------------------ Baugruppen
    def _baugruppen_reiter(self):
        baum = QTreeWidget()
        baum.setHeaderLabels(("Baugruppe / Teil", "Anzahl", "Kategorie", "Profil", "Länge [mm]", "Konfidenz",
                              "Hinweis"))
        for d in self.dateien:
            if not d["baugruppe"]:
                continue
            art = "Rohrlaser-Baugruppe" if d["rohrlaser_baugruppe"] else "mehrteilige Datei"
            wurzel = QTreeWidgetItem([d["datei"], str(d["koerper"]), art, "", "", "",
                                      f"{d['verschiedene']} verschiedene Teile"
                                      + (f", {len(d['verbindungen'])} Verbindungen ({_zahl(d['naht_laenge'])} mm)"
                                         if d["verbindungen"] else "")])
            baum.addTopLevelItem(wurzel)
            knoten_items = {}
            for p in d["positionen"]:
                for pfad, n in (p["knoten"] or {"": p["anzahl"]}).items():
                    eltern = wurzel
                    if pfad and pfad != d["datei"].rsplit(".", 1)[0]:
                        if pfad not in knoten_items:
                            knoten_items[pfad] = QTreeWidgetItem(wurzel, [pfad, "", "Unterbaugruppe"])
                        eltern = knoten_items[pfad]
                    var = next((v for v in d["varianten"] if v["nr"] == p["nr"]), None)
                    it = QTreeWidgetItem(eltern, [f"Pos. {p['nr']} {p['bezeichnung']}", str(n), p["kategorie"],
                                                  p["profil"], _zahl(p["laenge"]), f"{p['konfidenz']} %",
                                                  f"Variante von Pos. {var['von']}: {var['text']}" if var else ""])
                    it.setForeground(5, QBrush(stil.farbe(STUFE_FARBE.get(p["stufe"], stil.TEXT))))
            if d["verbindungen"]:
                vb = QTreeWidgetItem(wurzel, ["Verbindungen (Schweißnähte, Überschneidungen)",
                                              str(len(d["verbindungen"]))])
                for v in d["verbindungen"][:200]:
                    QTreeWidgetItem(vb, [" ↔ ".join(f"Pos. {n}" for n in v["positionen"]), "", v["stossart"], "",
                                         _zahl(v["laenge"]), v["status"], v["aufteilung"]])
            if d["materialbedarf_mm"]:
                mb = QTreeWidgetItem(wurzel, ["Materialbedarf je Profil (ohne Verschnitt)"])
                for prof, mm in d["materialbedarf_mm"].items():
                    QTreeWidgetItem(mb, [prof, "", "", "", _zahl(mm, 0), "", f"{_zahl(mm / 1000, 2)} m"])
            wurzel.setExpanded(True)
        baum.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        if baum.topLevelItemCount() == 0:
            QTreeWidgetItem(baum, ["Keine Datei mit mehreren Teilen"])
        self.baugruppen = baum
        self.reiter.addTab(baum, "Baugruppen")

    # ------------------------------------------------------------------ Dateien
    def _dateien_reiter(self):
        """Anforderungen je Datei (Laserhub L6: Volumenkörper, Einheit mm, Anzahl Körper; aus der vorhandenen
        Messung) und darunter die Befunde des Imports (ZIP, Herstellerformate, Dubletten, defekte Dateien)."""
        w = QSplitter(Qt.Vertical)
        zeilen = datei_anforderungen(self.messwerte)
        t1 = QTableWidget(len(zeilen), len(DATEI_SPALTEN))
        t1.setHorizontalHeaderLabels(DATEI_SPALTEN)
        t1.verticalHeader().setVisible(False)
        for r, z in enumerate(zeilen):
            werte = (z["datei"], z["koerper"], z["volumen"], z["einheit"], z["gueltig"], z["bewertung"])
            for c, v in enumerate(werte):
                farbe = (stil.GRUEN if z["ok"] else STUFE_FARBE["prüfen"]) if c == 5 else None
                t1.setItem(r, c, _item(v, farbe, c == 1, tipp=str(v) if c == 5 else None))
        t1.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t1.horizontalHeader().setStretchLastSection(True)
        self.datei_tabelle = t1
        w.addWidget(t1)
        befunde = next((m["_import_befunde"] for m in self.messwerte if m.get("_import_befunde")), [])
        t = QTableWidget(len(befunde), 3)
        t.setHorizontalHeaderLabels(("Datei", "Stufe", "Befund"))
        t.verticalHeader().setVisible(False)
        for r, b in enumerate(befunde):
            for c, v in enumerate((b.get("datei"), b.get("stufe"), b.get("text"))):
                t.setItem(r, c, _item(v, stil.ROT if c == 1 and b.get("stufe") == "Fehler" else None))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)
        self.befunde = t
        w.addWidget(t)
        w.setSizes([300, 200])
        self.reiter.addTab(w, f"Dateien ({len(zeilen)}, {len(befunde)} Befund{'e' if len(befunde) != 1 else ''})")

    def csv_speichern(self, pfad=None):
        if pfad is None:
            pfad, _ = QFileDialog.getSaveFileName(self, "Bauteilliste speichern", "Bauteilliste.csv",
                                                  "CSV (*.csv)")
            if not pfad:
                return None
        return bga.csv_schreiben(self.dateien, pfad)
