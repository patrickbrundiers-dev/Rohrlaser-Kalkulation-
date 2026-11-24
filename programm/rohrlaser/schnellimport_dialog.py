"""Fenster des Schnellimports (Patrick 24.11.2026, Logik in schnellimport.py):

- ModusDialog: vor dem Messen die Wahl „Vollständiger CAD-Import“ oder „Schneidweg & Zusatzarbeiten“, mit Häkchen
  „als Vorgabe merken“ (Einstellung step_importmodus).
- UebersichtDialog: nach der Messung im Schnellmodus statt des Prüfdialogs die kompakte Ergebnisübersicht
  (Geometrieanalyse, Zusatzarbeiten, Kalkulationsstatus) mit Haken je Teil, „In die Kalkulation übernehmen“ und
  „Vollständig importieren (mit 3D) …“.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QRadioButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import schnellimport as si
from . import step, stil


def _z(x, st=1):
    try:
        return f"{float(x):,.{st}f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return ""


class ModusDialog(QDialog):
    """Importmodus wählen. modus = gewählter Modus nach exec()."""

    def __init__(self, parent, dateien, vorgabe=si.MODUS_VOLL):
        super().__init__(parent)
        self.setWindowTitle("STEP-Import: Importmodus")
        self.modus = vorgabe
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{dateien} Datei{'en' if dateien != 1 else ''} importieren – wie?</b>"))
        self.knoepfe = {}
        for m in (si.MODUS_VOLL, si.MODUS_SCHNELL):
            r = QRadioButton(si.TITEL[m].replace("&", "&&"))       # & ist sonst ein Tastenkürzel
            f = r.font()
            f.setBold(True)
            r.setFont(f)
            r.setChecked(m == vorgabe)
            r.toggled.connect(lambda an, m=m: an and setattr(self, "modus", m))
            text = QLabel(si.BESCHREIBUNG[m])
            text.setWordWrap(True)
            text.setContentsMargins(24, 0, 0, 8)
            lay.addWidget(r)
            lay.addWidget(text)
            self.knoepfe[m] = r
        self.vorgabe_haken = QCheckBox("Als Vorgabe für neue Importe merken")
        self.vorgabe_haken.setToolTip("Einstellungen → STEP-Import: Ablauf → Importmodus. Dort lässt sich die Frage "
                                      "auch abschalten.")
        lay.addWidget(self.vorgabe_haken)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("Messen")
        box.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.setMinimumWidth(520)

    def als_vorgabe(self):
        return self.vorgabe_haken.isChecked()


class UebersichtDialog(QDialog):
    """Ergebnisübersicht des Schnellimports. ergebnis nach exec(): "uebernehmen" oder "voll" (vollständig
    importieren); die Haken stehen danach in messwerte[i]["_uebernehmen"]."""
    SPALTEN = ("Teil", "Art / Profil / Werkstoff", "Wand", "Länge", "Schneidweg", "Konturen", "Einstiche", "Anfahrten",
               "Schnittarten", "Bearbeitungen", "Zusatzarbeiten", "Genauigkeit")

    def __init__(self, parent, messwerte, profile=None, dauer_s=None, doppelt=0, fehlend=()):
        super().__init__(parent)
        self.messwerte, self.profile, self.ergebnis = messwerte, profile, None
        self.setWindowTitle(f"Schnellkalkulation: {len(messwerte)} Teil{'e' if len(messwerte) != 1 else ''}")
        self.resize(1250, 560)
        lay = QVBoxLayout(self)
        self.kopf = QLabel()
        self.kopf.setWordWrap(True)
        self.kopf.setTextFormat(Qt.RichText)
        lay.addWidget(self.kopf)
        self.tabelle = QTableWidget(len(messwerte), len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.horizontalHeaderItem(7).setToolTip("Je Einstich eine Anfahrt (so rechnet die Kalkulation die "
                                                        "Anfahrzeit)")
        self._fuellen()
        self.tabelle.itemChanged.connect(self._haken)
        lay.addWidget(self.tabelle, 1)
        self.unten = QLabel()
        self.unten.setWordWrap(True)
        self.unten.setTextFormat(Qt.RichText)
        lay.addWidget(self.unten)
        self.hinweis = QLabel(
            ("; ".join(x for x in (
                f"{doppelt} Artikel stehen schon im Angebot und werden übersprungen" if doppelt else "",
                "fehlende Profile werden aus den Messwerten angelegt: " + ", ".join(list(fehlend)[:6])
                if fehlend else "") if x)
             + ". " if doppelt or fehlend else "")
            + "Ohne 3D-Körper der STEP: Kalkulation, Schneidweg-Rechner und Zusatzarbeiten wie gewohnt; "
              "„3D aus STEP nachladen“ (Rechtsklick auf die Position) holt den Körper später."
            + (f" Messung {_z(dauer_s, 1)} s." if dauer_s else ""))
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet("color: gray;")
        lay.addWidget(self.hinweis)
        knoepfe = QHBoxLayout()
        self.voll_knopf = QPushButton("Vollständig importieren (mit 3D) …")
        self.voll_knopf.setToolTip("Neu messen wie im vollständigen CAD-Import und den Prüfdialog mit 3D öffnen")
        self.voll_knopf.clicked.connect(self._voll)
        knoepfe.addWidget(self.voll_knopf)
        knoepfe.addStretch(1)
        self.ok_knopf = QPushButton("In die Kalkulation übernehmen")
        self.ok_knopf.setDefault(True)
        self.ok_knopf.clicked.connect(self._uebernehmen)
        abbrechen = QPushButton("Abbrechen")
        abbrechen.clicked.connect(self.reject)
        knoepfe.addWidget(self.ok_knopf)
        knoepfe.addWidget(abbrechen)
        lay.addLayout(knoepfe)
        self._summen()

    def _fuellen(self):
        t = self.tabelle
        for r, m in enumerate(self.messwerte):
            mm = si.merkmale(m)
            stufe, gruende = si.genauigkeit(m, self.profile)
            profil = m.get("_profil") or m.get("profil_id_vorschlag") or ""
            art = step.art_gruppe(m) if m.get("profilform") else "nicht messbar"
            werte = [m.get("artikel") or m.get("datei") or "", " · ".join(str(x) for x in (art, profil or mm["profilform"], m.get("_werkstoff")) if x),
                     _z(mm["wand"], 2) if mm["wand"] else "", _z(mm["laenge"]), _z(mm["schneidweg"]),
                     str(mm["konturen"]), str(mm["einstiche"]), str(mm["anfahrten"]),
                     ", ".join(f"{e[-1]}: {f}" for e, f in sorted(mm["enden"].items())),
                     ", ".join(f"{n}× {k}" for k, n in mm["bearbeitungen"].items()),
                     ", ".join([f"{k} {_z(v, 1) if isinstance(v, float) else v}" for k, v in mm["zusatz"].items()]
                               + ([f"Gewinde-Vorschlag {mm['gewinde']}"] if mm["gewinde"] else [])),
                     si.stufe_text(stufe)]
            for c, w in enumerate(werte):
                it = QTableWidgetItem(w)
                if c in (2, 3, 4, 5, 6, 7):
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                t.setItem(r, c, it)
            erstes = t.item(r, 0)
            erstes.setFlags(erstes.flags() | Qt.ItemIsUserCheckable)
            erstes.setCheckState(Qt.Checked if step.gewaehlt(m) and not m.get("fehler") else Qt.Unchecked)
            if m.get("fehler"):
                erstes.setFlags(erstes.flags() & ~Qt.ItemIsUserCheckable)
            g = t.item(r, len(self.SPALTEN) - 1)
            g.setForeground(QBrush(stil.farbe(si.FARBEN[stufe])))
            g.setToolTip("\n".join(gruende) or si.stufe_text(stufe))
            t.item(r, 10).setToolTip(str(m.get("hinweise") or ""))
        t.resizeColumnsToContents()
        for c in (8, 9, 10):
            t.setColumnWidth(c, min(t.columnWidth(c), 220))

    def _haken(self, it):
        if it.column() != 0:
            return
        m = self.messwerte[it.row()]
        m["_uebernehmen"] = it.checkState() == Qt.Checked
        self._summen()

    def _summen(self):
        s = si.zusammenfassung(self.messwerte, self.profile)
        farbe = si.FARBEN[0 if s["status"] == si.VOLLSTAENDIG else 2 if s["status"] == si.TEILWEISE else 3]
        st = s["stufen"]
        self.kopf.setText(
            f"<b>Geometrieanalyse</b>: {s['teile']} Teil(e) erkannt, {s['gewaehlt']} zum Übernehmen · Schneidweg "
            f"gesamt {_z(s['schneidweg'])} mm · {s['konturen']} Konturen · {s['einstiche']} Einstiche · "
            f"{s['einstiche']} Anfahrten<br><b>Kalkulationsstatus</b>: <span style='color:{stil.farbe(farbe).name()}'>"
            f"{s['status']}</span> ({st[0]} sicher, {st[1]} wahrscheinlich, {st[2]} nicht eindeutig, {st[3]} manuell "
            "prüfen)")
        zusatz = ", ".join(f"{k} {_z(v, 1) if isinstance(v, float) else v}" for k, v in s["zusatz"].items())
        bearb = ", ".join(f"{n}× {k}" for k, n in s["bearbeitungen"].items())
        unsicher = [m.get("artikel") or m.get("datei") for m in self.messwerte
                    if step.gewaehlt(m) and si.genauigkeit(m, self.profile)[0] >= 2]
        self.unten.setText(f"<b>Bearbeitungen</b>: {bearb or 'keine'}<br><b>Zusatzarbeiten</b>: "
                           f"{zusatz or 'keine erkannt'} (Vorschläge erscheinen wie gewohnt gelb an der Position, "
                           "weitere über Rechtsklick → Zusatzarbeiten …)"
                           + (f"<br><b>Unsichere Erkennungen</b>: {', '.join(map(str, unsicher[:10]))}"
                              + (" …" if len(unsicher) > 10 else "") if unsicher else ""))
        self.ok_knopf.setEnabled(s["gewaehlt"] > 0)

    def _uebernehmen(self):
        self.ergebnis = "uebernehmen"
        for r, m in enumerate(self.messwerte):
            if not m.get("fehler"):
                m["_uebernehmen"] = self.tabelle.item(r, 0).checkState() == Qt.Checked
        self.accept()

    def _voll(self):
        self.ergebnis = "voll"
        self.accept()
