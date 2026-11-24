"""Fenster „Bauteil aus Text“ (bauteil_generator.py, Wettbewerbsanalyse 247TailorSteel 20.11.2026): Beschreibung
eintippen oder eine Vorlage wählen, „Erstellen“ zeigt Teile, 3D, erkannte Angaben, Annahmen (orange), Hinweise und
Fehler (rot). Änderungen per Satz („Breite 1200“, „6 Querstreben“) kommen in den Verlauf und lassen sich
zurücknehmen. Übernehmen erst ohne Fehler; nach OK steht in self.ergebnis dict(plan, werkstoff_id,
blech_werkstoff_id, saetze, name, text, verlauf)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import bauteil_generator as bg
from .eingabe import RechenSpinGanz

VORLAGEN = (("Vorlage wählen …", ""),
            ("Rohrrahmen mit Querstreben und Fußplatten",
             "Rohrrahmen 1000 x 600 mm aus 40 x 40 x 3 mit vier Querstreben und zwei Befestigungsplatten"),
            ("Gestell (Quader)", "Gestell 1200 x 800 x 900 aus 40 x 40 x 3, stumpf, 4 Fußplatten 120 x 120 x 10"),
            ("Rahmen aus Rundrohr", "Rahmen aus Rundrohr Ø 48,3 x 2,6, Breite 1200, Höhe 800, 2 waagrechte Streben"),
            ("Lasche mit Bohrungen", "Lasche 80 x 40 x 5 mit 2 Bohrungen Ø 9"),
            ("L-Winkel", "L-Winkel 60 x 40 x 5, Länge 100 mit 2 Bohrungen Ø 9"),
            ("Flanschring", "Flanschring Ø 200 x Ø 100 x 8 mit 6 Bohrungen Ø 11 auf Lochkreis 160"))
ROT, ORANGE, GRAU = "#C62828", "#B26A00", "#555"


def _liste(titel, zeilen, farbe=None):
    if not zeilen:
        return ""
    stil = f" style='color:{farbe}'" if farbe else ""
    return f"<b>{titel}</b><ul style='margin:0'>" + "".join(f"<li{stil}>{z}</li>" for z in zeilen) + "</ul>"


class BauteilGeneratorDialog(QDialog):
    def __init__(self, parent=None, profile=None, werkstoffe=None, werkstoff=None, blech_werkstoffe=None,
                 stange=6000.0, profil_anlegen=None):
        super().__init__(parent)
        self.setWindowTitle("Bauteil aus Text")
        self.profile = profile or {}
        self.werkstoffe = werkstoffe or {}
        self.blech_werkstoffe = blech_werkstoffe or {}
        self.stange = stange
        self.profil_anlegen = profil_anlegen          # Funktion(text) → Profil-ID oder None
        self.werte, self.plan, self.verlauf, self.ergebnis = bg.vorgabe(), None, [], None
        self.erkannt, self.unklar = [], []
        aussen = QHBoxLayout(self)
        links = QWidget()
        lay = QVBoxLayout(links)
        lay.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(links)
        from .ansicht3d import Ansicht3DMitKnoepfen
        self.ansicht = Ansicht3DMitKnoepfen()
        self.ansicht.setMinimumSize(440, 400)
        aussen.addWidget(self.ansicht, 1)
        info = QLabel("Bauteil in eigenen Worten beschreiben: Rohrrahmen, Gestell, Querstreben, Befestigungsplatten, "
                      "Laschen, L-Winkel, Flanschringe. Das Programm liest die Angaben (ohne Internet), zeigt jede "
                      "Annahme und prüft die Teile. Erst „Übernehmen“ legt Positionen an.")
        info.setWordWrap(True)
        info.setMaximumWidth(480)
        lay.addWidget(info)
        self.vorlage = QComboBox()
        self.vorlage.addItems([v[0] for v in VORLAGEN])
        self.vorlage.currentIndexChanged.connect(self._vorlage)
        lay.addWidget(self.vorlage)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("z. B. Rohrrahmen 1000 x 600 mm aus 40 x 40 x 3 mm Stahlrohr mit vier "
                                     "Querstreben und zwei Befestigungsplatten")
        self.text.setMaximumHeight(80)
        lay.addWidget(self.text)
        zeile = QHBoxLayout()
        self.erstellen_knopf = QPushButton("Erstellen")
        self.erstellen_knopf.clicked.connect(lambda: self.erstellen())
        zeile.addWidget(self.erstellen_knopf)
        self.aenderung = QLineEdit()
        self.aenderung.setPlaceholderText("Änderung, z. B. „Breite 1200“, „6 Querstreben“, „ohne Platten“")
        self.aenderung.returnPressed.connect(lambda: self.aendern())
        zeile.addWidget(self.aenderung, 1)
        self.aendern_knopf = QPushButton("Ändern")
        self.aendern_knopf.clicked.connect(lambda: self.aendern())
        zeile.addWidget(self.aendern_knopf)
        lay.addLayout(zeile)
        self.verlauf_liste = QListWidget()
        self.verlauf_liste.setMaximumHeight(70)
        self.verlauf_liste.setToolTip("Verlauf: Beschreibung und Änderungen")
        lay.addWidget(self.verlauf_liste)
        self.zurueck_knopf = QPushButton("Letzte Änderung zurücknehmen")
        self.zurueck_knopf.clicked.connect(lambda: self.zuruecknehmen())
        lay.addWidget(self.zurueck_knopf)
        form = QFormLayout()
        self.werkstoff = QComboBox()
        self.werkstoff.addItems([""] + sorted(self.werkstoffe, key=str.lower))
        if werkstoff in self.werkstoffe:
            self.werkstoff.setCurrentText(werkstoff)
        self.blech_werkstoff = QComboBox()
        self.blech_werkstoff.addItems(sorted(self.blech_werkstoffe, key=str.lower))
        self.saetze = RechenSpinGanz()
        self.saetze.setRange(1, 100000)
        self.name = QLineEdit()
        self.name.setPlaceholderText("leer = Vorschlag")
        form.addRow("Werkstoff Rohr", self.werkstoff)
        form.addRow("Werkstoff Blech", self.blech_werkstoff)
        form.addRow("Stück / Sätze", self.saetze)
        form.addRow("Name", self.name)
        lay.addLayout(form)
        self.bericht = QLabel()
        self.bericht.setWordWrap(True)
        self.bericht.setMaximumWidth(470)
        self.bericht.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        rollen = QScrollArea()          # langer Bericht (viele Annahmen, Rückfragen darunter) bleibt lesbar
        rollen.setWidget(self.bericht)
        rollen.setWidgetResizable(True)
        rollen.setFrameShape(QFrame.NoFrame)
        rollen.setMinimumHeight(160)
        lay.addWidget(rollen, 1)
        # Rückfragen (Stufe 2): offene Punkte mit Knöpfen, ein Klick wirkt wie eine getippte Änderung
        self.fragen = QWidget()
        self.fragen_lay = QVBoxLayout(self.fragen)
        self.fragen_lay.setContentsMargins(0, 0, 0, 0)
        self.fragen_knoepfe = []            # [(Frage, Knopftext, QPushButton)] für Tests
        lay.addWidget(self.fragen)
        self.profil_knopf = QPushButton("Fehlendes Profil anlegen …")
        self.profil_knopf.clicked.connect(lambda: self._profil_anlegen())
        self.profil_knopf.setVisible(False)
        lay.addWidget(self.profil_knopf)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen")
        self.knoepfe.accepted.connect(self._ok)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        self.setMinimumWidth(1000)
        self.zeigen()

    # ------------------------------------------------------------------ Ablauf
    def _vorlage(self, i):
        if i > 0:
            self.text.setPlainText(VORLAGEN[i][1])
            self.erstellen()

    def erstellen(self, text=None):
        """Beschreibung neu lesen (alles vorher Gesagte fällt weg)."""
        if text is not None:
            self.text.setPlainText(text)
        t = self.text.toPlainText().strip()
        w, self.erkannt, self.unklar = bg.lesen(t)
        self.werte = dict(bg.vorgabe(), **w)
        self.verlauf = [(t, dict(self.werte))]
        self._uebernehmen_werte()
        self.zeigen()
        return self.plan

    def aendern(self, text=None):
        """Änderung per Satz auf den aktuellen Stand."""
        t = (text if text is not None else self.aenderung.text()).strip()
        if not t:
            return self.plan
        if not self.verlauf:
            return self.erstellen(t)
        self.werte, self.erkannt, self.unklar = bg.aendern(self.werte, t)
        self.verlauf.append((t, dict(self.werte)))
        self.aenderung.clear()
        self._uebernehmen_werte()
        self.zeigen()
        return self.plan

    def zuruecknehmen(self):
        if len(self.verlauf) <= 1:
            return
        self.verlauf.pop()
        self.werte = dict(self.verlauf[-1][1])
        self.erkannt, self.unklar = [f"zurück auf: {self.verlauf[-1][0]}"], []
        self.zeigen()

    def _uebernehmen_werte(self):
        """Stückzahl und Werkstoffe aus dem Text in die Felder."""
        if self.werte.get("saetze"):
            self.saetze.setValue(int(self.werte["saetze"]))
        wort = self.werte.get("werkstoff_wort")
        if wort:
            from .schnellzeile import werkstoff_finden
            wid = werkstoff_finden(wort, self.werkstoffe)
            if wid:
                self.werkstoff.setCurrentText(wid)
        zeile = self.werkstoffe.get(self.werkstoff.currentText()) or {}
        bw = bg.blech_werkstoff(self.blech_werkstoffe, zeile.get("kategorie"), wort, zeile.get("werkstoff"))
        if bw:
            self.blech_werkstoff.setCurrentText(bw)

    def _profil_anlegen(self):
        if not self.plan or not self.plan["fehlende_profile"] or not self.profil_anlegen:
            return
        pid = self.profil_anlegen(self.plan["fehlende_profile"][0])
        if pid:
            self.zeigen()

    def zeigen(self):
        if not self.verlauf:
            self.plan = None
            self.bericht.setText("<span style='color:#555'>Noch nichts erstellt.</span>")
            self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(False)
            self.zurueck_knopf.setEnabled(False)
            self.ansicht.setzen(None, "", "")
            return
        self.verlauf_liste.clear()
        self.verlauf_liste.addItems([("Beschreibung: " if i == 0 else "Änderung: ") + t
                                     for i, (t, _) in enumerate(self.verlauf)])
        self.zurueck_knopf.setEnabled(len(self.verlauf) > 1)
        self.plan = bg.bauen(self.werte, self.profile, self.stange)
        p = self.plan
        teile = bg.zusammenfassung(p) if not p["fehler"] else []
        self.bericht.setText(
            _liste("Teile je Stück/Satz", teile) + _liste("Fehler (vor dem Übernehmen beheben)", p["fehler"], ROT)
            + _liste("Annahmen (bitte prüfen)", p["annahmen"], ORANGE) + _liste("Hinweise", p["hinweise"], ORANGE)
            + _liste("Erkannt", self.erkannt, GRAU) + _liste("Nicht verstanden", self.unklar, ROT))
        self._fragen_zeigen(p.get("rueckfragen") or [])
        self.profil_knopf.setVisible(bool(p["fehlende_profile"] and self.profil_anlegen))
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(not p["fehler"])
        if p["fehler"] and not p.get("erg") and not p.get("blech"):
            self.ansicht.setzen(None, "", "")
            return
        e = bg.blech_e(p, self.blech_werkstoff.currentText() or None)
        self.ansicht.setzen(bg.vorschau(p, e), self.satz_name(), "Vorschau in Einbaulage, gleiche Teile in gleicher "
                            "Farbe. Nach dem Übernehmen im Satz in 3D bzw. im Editor weiter bearbeitbar.")

    def _fragen_zeigen(self, fragen):
        while self.fragen_lay.count():
            it = self.fragen_lay.takeAt(0)
            if it.widget():
                it.widget().hide()          # sofort weg (deleteLater wirkt erst in der Ereignisschleife)
                it.widget().deleteLater()
        self.fragen_knoepfe = []
        if fragen:
            kopf = QLabel(f"<b style='color:{ORANGE}'>Rückfragen</b> <span style='color:{GRAU}'>(eingesetzt ist der "
                          "markierte Vorschlag; ein Klick ändert und kommt in den Verlauf)</span>")
            kopf.setWordWrap(True)
            kopf.setMaximumWidth(480)
            self.fragen_lay.addWidget(kopf)
        for f in fragen:
            zeile = QWidget()
            zl = QHBoxLayout(zeile)
            zl.setContentsMargins(0, 0, 0, 0)
            lab = QLabel(f["frage"])
            lab.setWordWrap(True)
            lab.setMaximumWidth(220)
            zl.addWidget(lab, 1)
            for o in f["optionen"]:
                k = QPushButton(("✓ " if o["vorschlag"] else "") + o["text"])
                k.setToolTip(f"Änderung: {o['satz']}")
                k.clicked.connect(lambda _=False, satz=o["satz"]: self.aendern(satz))
                zl.addWidget(k)
                self.fragen_knoepfe.append((f["frage"], o["text"], k))
            self.fragen_lay.addWidget(zeile)

    def frage_beantworten(self, frage_anfang, knopf_text):
        """Rückfrage per Knopf beantworten (Tests): erster Knopf, dessen Frage so beginnt und dessen Text passt."""
        for f, t, k in self.fragen_knoepfe:
            if f.startswith(frage_anfang) and t == knopf_text:
                k.click()
                return True
        return False

    def wiederherstellen(self, verlauf):
        """Gespeicherten Verlauf (Beschreibung + Änderungen) erneut abspielen: „Satz per Text ändern“."""
        if not verlauf:
            return self.plan
        self.erstellen(verlauf[0])
        for t in verlauf[1:]:
            self.aendern(t)
        return self.plan

    def satz_name(self):
        return self.name.text().strip() or (bg.name_vorschlag(self.plan) if self.plan and not self.plan["fehler"]
                                            else "Bauteil")

    def _ok(self):
        if not self.plan or self.plan["fehler"]:
            return
        self.ergebnis = dict(plan=self.plan, werkstoff_id=self.werkstoff.currentText() or None,
                             blech_werkstoff_id=self.blech_werkstoff.currentText() or None,
                             saetze=self.saetze.value(), name=self.satz_name(),
                             text=self.verlauf[0][0], verlauf=[t for t, _ in self.verlauf])
        self.accept()
