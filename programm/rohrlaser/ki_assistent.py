"""KI-Assistent (Datei → KI-Assistent …, Strg+Alt+K; Master-Prompt Patrick 20.11.2026, Punkt 5).

Fragen in normaler Sprache zum offenen Angebot oder zu allen Daten. Der Orchestrator (ki_orchestrator.fragen) wählt
die Fach-Agenten; alle Zahlen kommen aus der Programmlogik, ein lokales Sprachmodell formuliert höchstens die Antwort
(mit Faktencheck). Befunde mit Ziel lassen sich per Doppelklick im Angebot anspringen. „Bericht speichern“ schreibt die
vollständige Angebotsprüfung als PDF. „Anfrage auslesen …“ liest Positionen, Kundenvorgaben und Zusatzarbeiten aus
einer Anfrage (PDF, Text, Mail oder eingefügter Text); erst „Als Angebotsentwurf anlegen“ legt ein neues Angebot an
(KI 2, Patrick 20.11.2026). Sonst ändert der Assistent nie Daten."""
import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from .stammdaten import zahl_als_text
from . import ki_agenten, ki_auslesen, ki_bericht, ki_orchestrator, ki_protokoll

FARBE = {ki_agenten.FEHLER: "#B91C1C", ki_agenten.WARNUNG: "#B45309", ki_agenten.VORSCHLAG: "#1F4E78",
         ki_agenten.HINWEIS: "#4B5563", ki_agenten.INFO: "#4B5563"}


class KiAssistent(QDialog):
    def __init__(self, f, senden=None):
        super().__init__(f)
        self.f, self.db, self.senden = f, f.db, senden
        self.ergebnis = None
        self.anfrage_erg = None
        self.setWindowTitle("KI-Assistent")
        self.setModal(False)
        self.resize(900, 640)
        lay = QVBoxLayout(self)
        self.bezug = QLabel()
        self.bezug.setWordWrap(True)
        lay.addWidget(self.bezug)
        z = QHBoxLayout()
        self.beispiele = QComboBox()
        self.beispiele.addItem("Beispielfrage wählen …", "")
        for b in ki_orchestrator.BEISPIELE:
            self.beispiele.addItem(b, b)
        self.beispiele.activated.connect(self._beispiel)
        z.addWidget(self.beispiele, 1)
        lay.addLayout(z)
        z2 = QHBoxLayout()
        self.frage = QPlainTextEdit()
        self.frage.setPlaceholderText("Frage eingeben, z. B. „Warum ist dieses Angebot so teuer?“ (Strg+Enter fragt)")
        self.frage.setMaximumHeight(70)
        z2.addWidget(self.frage, 1)
        self.frag_knopf = QPushButton("Fragen")
        self.frag_knopf.setDefault(True)
        self.frag_knopf.clicked.connect(lambda: self.fragen())
        z2.addWidget(self.frag_knopf)
        lay.addLayout(z2)
        self.antwort = QPlainTextEdit()
        self.antwort.setReadOnly(True)
        lay.addWidget(self.antwort, 2)
        self.befunde = QTableWidget(0, 4)
        self.befunde.setHorizontalHeaderLabels(["Art", "Agent", "Befund", "Quelle"])
        self.befunde.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.befunde.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.befunde.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.befunde.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.befunde.verticalHeader().setVisible(False)
        self.befunde.doubleClicked.connect(lambda i: self.hinspringen(i.row()))
        self.befunde.setToolTip("Doppelklick springt zur Stelle im Angebot")
        lay.addWidget(self.befunde, 2)
        self.fuss = QLabel()
        self.fuss.setWordWrap(True)
        self.fuss.setStyleSheet("color:#4B5563")
        lay.addWidget(self.fuss)
        z3 = QHBoxLayout()
        self.pruef_knopf = QPushButton("Vollständige Angebotsprüfung")
        self.pruef_knopf.clicked.connect(self.pruefen)
        self.bericht_knopf = QPushButton("Bericht speichern (PDF) …")
        self.bericht_knopf.clicked.connect(lambda: self.bericht_speichern())
        self.auslesen_knopf = QPushButton("Anfrage auslesen …")
        self.auslesen_knopf.setToolTip("PDF, Text oder Mail der Anfrage wählen – oder den Text oben einfügen")
        self.auslesen_knopf.clicked.connect(lambda: self.anfrage_auslesen())
        self.entwurf_knopf = QPushButton("Als Angebotsentwurf anlegen")
        self.entwurf_knopf.setEnabled(False)
        self.entwurf_knopf.clicked.connect(lambda: self.entwurf_anlegen())
        self.kopier_knopf = QPushButton("Text kopieren")
        self.kopier_knopf.setToolTip("Antwort in die Zwischenablage, z. B. Rückfrage-Mail oder Satz für den Kunden")
        self.kopier_knopf.clicked.connect(self.kopieren)
        k = QPushButton("Schließen")
        k.clicked.connect(self.close)
        for x in (self.pruef_knopf, self.bericht_knopf, self.auslesen_knopf, self.entwurf_knopf, self.kopier_knopf):
            z3.addWidget(x)
        z3.addStretch(1)
        z3.addWidget(k)
        lay.addLayout(z3)
        self.bezug_setzen()

    # ------------------------------------------------------------------
    def seite(self):
        s = self.f._seite() if hasattr(self.f, "_seite") else None
        return s if s is not None and getattr(s, "id", None) is not None else None

    def bezug_setzen(self):
        s = self.seite()
        if s is None:
            self.bezug.setText("Kein Angebot offen: der Assistent antwortet über alle Daten (Anfragen, Lernen, "
                               "Abweichungen, Suche).")
        else:
            k = self.db.angebot(s.id) or {}
            self.bezug.setText(f"Bezug: Angebot {k.get('nummer') or s.id} {k.get('kunde') or ''}".rstrip())
        self.pruef_knopf.setEnabled(s is not None)
        self.bericht_knopf.setEnabled(bool(self.ergebnis and self.ergebnis.get("befunde")))
        return s

    def _beispiel(self, i):
        t = self.beispiele.itemData(i)
        if t:
            self.frage.setPlainText(t)
            self.fragen(t)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and ev.modifiers() & Qt.ControlModifier:
            self.fragen()
            return
        super().keyPressEvent(ev)

    def fragen(self, text=None, mit_modell=True):
        frage = (text if isinstance(text, str) else self.frage.toPlainText()).strip()
        if not frage:
            return None
        s = self.bezug_setzen()
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            e = ki_orchestrator.fragen(self.db, frage, seite=s, senden=self.senden, mit_modell=mit_modell)
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.zeigen(e)
        return e

    def pruefen(self):
        s = self.bezug_setzen()
        if s is None:
            return None
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = ki_agenten.pruefen(self.db, seite=s)
        finally:
            QGuiApplication.restoreOverrideCursor()
        e = dict(text=ki_bericht.text(r, self.db.angebot(s.id) or {}), befunde=r["befunde"], treffer=[],
                 quellen=sorted({(b["quelle"], (b.get("stand") or "")[:16]) for b in r["befunde"] if b["quelle"]}),
                 modell="", faktencheck=None, fehler=r["fehler"], dauer_s=None, titel="Angebotsprüfung")
        self.zeigen(e)
        return e

    def zeigen(self, e):
        self.ergebnis = e
        self.antwort.setPlainText(e["text"])
        bf = e.get("befunde") or []
        if not bf and e.get("treffer"):         # Suchtreffer: Doppelklick öffnet das Angebot
            bf = [dict(art="Treffer", agent=t.get("quelle") or "Suche", text=f"{t['titel']}: {t.get('text') or ''}",
                       quelle=str(t.get("stand") or ""), ziel=t.get("ziel")) for t in e["treffer"]]
            e = dict(e, befunde=bf)
            self.ergebnis = e
        self.befunde.setRowCount(len(bf))
        from PySide6.QtGui import QColor
        for r, b in enumerate(bf):
            for c, w in enumerate((ki_bericht.ZEICHEN.get(b["art"], b["art"]), b["agent"], b["text"], b["quelle"])):
                it = QTableWidgetItem(str(w or ""))
                if c == 0:
                    it.setForeground(QColor(FARBE.get(b["art"], "#1F2937")))
                if b.get("begruendung"):
                    it.setToolTip(b["begruendung"])
                self.befunde.setItem(r, c, it)
        teile = []
        if e.get("quellen"):
            teile.append("Quellen: " + "; ".join(f"{q}{' (Stand ' + st + ')' if st else ''}" for q, st in e["quellen"]))
        if e.get("modell"):
            teile.append(f"formuliert von {e['modell']} (lokal)" + ("" if e.get("faktencheck") in (None, True) else
                                                                     " – Faktencheck nicht bestanden, nur Regeltext"))
        else:
            teile.append("regelbasiert (ohne Sprachmodell)")
        if e.get("fehler"):
            teile.append("nicht verfügbar: " + ", ".join(q for q, _ in e["fehler"]))
        self.fuss.setText(" · ".join(teile))
        self.bericht_knopf.setEnabled(bool(bf) and self.seite() is not None and not e.get("treffer"))

    def kopieren(self):
        QGuiApplication.clipboard().setText(self.antwort.toPlainText())

    def anfrage_auslesen(self, pfad=None, text=None, mit_modell=True):
        """Anfrage auswerten (ändert nichts): Datei oder eingefügter Text. Ergebnis wie ki_auslesen.anfrage()."""
        quelle = "eingefügtem Text"
        if text is None and pfad is None:
            t = self.frage.toPlainText().strip()
            if len(t) >= 80:
                text = t
            else:
                pfad, _ = QFileDialog.getOpenFileName(self, "Anfrage auslesen", str(Path.home()),
                                                      "Anfrage (*.pdf *.txt *.eml *.msg);;Alle Dateien (*)")
                if not pfad:
                    return None
        if pfad:
            text, quelle = ki_auslesen.text_aus_datei(pfad), Path(pfad).name
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            erg = ki_auslesen.anfrage(self.db, text or "", senden=self.senden, mit_modell=mit_modell)
        finally:
            QGuiApplication.restoreOverrideCursor()
        erg["quelle"] = quelle
        self.anfrage_erg = erg
        bf = [dict(art=ki_agenten.VORSCHLAG if p.get("profil_id") and p.get("menge") else ki_agenten.WARNUNG,
                   agent="KI-Auslesen" + (" (Sprachmodell)" if p.get("quelle") == "KI" else ""),
                   text=" · ".join(str(x) for x in (p.get("artikel"), p.get("profil_id") or p.get("profil_text"),
                                                    f"L {zahl_als_text(p['laenge'])} mm" if p.get("laenge") else "",
                                                    f"{p['menge']} Stk." if p.get("menge") else "Menge ?",
                                                    p.get("werkstoff_id")) if x),
                   quelle=(p.get("fundstelle") or "")[:120], ziel=None) for p in erg["positionen"]]
        bf += [dict(art=ki_agenten.HINWEIS, agent="Kundenvorgabe", text=f"{v['art']}: {v['text']}", quelle=quelle,
                    ziel=None) for v in erg["vorgaben"] if v.get("feld") != "projekt"]
        self.zeigen(dict(text=f"Anfrage aus {quelle}\n" + ki_orchestrator.anfrage_text(erg), befunde=bf, treffer=[],
                         quellen=[(quelle, "")], modell="", faktencheck=None, fehler=[("Sprachmodell", x) for x in erg.get("fehler") or ()],
                         titel="Anfrage auslesen"))
        self.bericht_knopf.setEnabled(False)
        self.entwurf_knopf.setEnabled(any(p.get("profil_id") for p in erg["positionen"]))
        return erg

    def entwurf_anlegen(self, oeffnen=True):
        """Neues Angebot (Entwurf) aus der letzten Auswertung; öffnet es. Ergebnis: Angebots-ID."""
        if not self.anfrage_erg:
            return None
        aid = ki_auslesen.entwurf_anlegen(self.db, self.anfrage_erg, quelle=self.anfrage_erg.get("quelle") or "Anfrage")
        self.entwurf_knopf.setEnabled(False)
        if oeffnen and hasattr(self.f, "angebot_oeffnen"):
            self.f.angebot_oeffnen(aid)
        if hasattr(self.f, "meldung"):
            self.f.meldung("Angebotsentwurf angelegt – bitte Positionen und Vorgaben prüfen.")
        self.bezug_setzen()
        return aid

    def hinspringen(self, zeile):
        bf = (self.ergebnis or {}).get("befunde") or []
        s = self.seite()
        ziel = bf[zeile].get("ziel") if zeile < len(bf) else None
        if ziel and str(ziel).startswith("angebot:") and hasattr(self.f, "angebot_oeffnen"):
            return self.f.angebot_oeffnen(int(str(ziel).split(":", 1)[1]))
        if not ziel or s is None:
            return None
        return s.check_link(bf[zeile]["ziel"])

    def bericht_speichern(self, pfad=None):
        s = self.seite()
        if not self.ergebnis or s is None:
            return None
        kopf = self.db.angebot(s.id) or {}
        if pfad is None:
            ablage = getattr(self.f, "ablage", None)
            ordner = ablage() if callable(ablage) else (ablage or Path.home())
            vorschlag = Path(ordner) / \
                f"KI-Pruefung_{kopf.get('nummer') or s.id}_{datetime.date.today():%Y%m%d}.pdf"
            pfad, _ = QFileDialog.getSaveFileName(self, "Bericht speichern", str(vorschlag), "PDF (*.pdf)")
            if not pfad:
                return None
        ki_bericht.pdf(dict(befunde=self.ergebnis["befunde"], fehler=self.ergebnis.get("fehler") or []), pfad, kopf)
        ki_protokoll.schreiben(self.db, "KI-Assistent", "bericht", ergebnis=str(pfad), angebot_id=s.id)
        if hasattr(self.f, "meldung"):
            self.f.meldung(f"Bericht gespeichert: {pfad}")
        return pfad


def zeigen(f, senden=None):
    """Nicht-modal: bleibt offen, während man im Angebot arbeitet."""
    d = getattr(f, "_ki_assistent", None)
    if d is None:
        d = KiAssistent(f, senden=senden)
        f._ki_assistent = d
    d.bezug_setzen()
    d.show()
    d.raise_()
    return d
