"""Erste Schritte für neue Arbeitsplätze (Verbesserungsplan 06.11.2026, B4).

Eine kurze Liste mit Häkchen: Firma und Kürzel, Maschine und Preise, erstes Angebot aus STEP, Optimieren, Angebot als
PDF. Jeder Punkt hat einen Knopf, der die richtige Stelle öffnet. Was sich am Datenbestand erkennen lässt, ist von
selbst abgehakt (Briefkopf und Kürzel eingetragen, ein Angebot mit Positionen, ein optimiertes, ein verschicktes);
„Maschine und Preise prüfen“ gilt mit dem Klick auf „Öffnen“ bzw. dem Häkchen als erledigt.

Beim Start erscheint die Liste einmal je Arbeitsplatz, solange noch etwas offen ist; Arbeitsplätze mit schon fünf
Angeboten bekommen sie nicht ungefragt. Hilfe → Erste Schritte … öffnet sie jederzeit. Gemerkt wird in der Einstellung
'erste_schritte' (nur dieser Platz, wird nicht geteilt).
"""
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QLabel, QPushButton, QVBoxLayout)

EINSTELLUNG = "erste_schritte"      # {Schlüssel: True (abgehakt)}, "_gezeigt": True
SCHON_ERFAHREN = 5                  # ab so vielen Angeboten erscheint die Liste nicht von selbst
VERSCHICKT = ("Verschickt", "Beauftragt", "Abgelehnt")


@dataclass
class Punkt:
    name: str
    titel: str
    text: str
    knopf: str
    oeffnen: Callable           # oeffnen(fenster)
    erkannt: Callable           # erkannt(db, angebote) -> bool


def _angebote(db):
    try:
        return db.angebote()
    except Exception:
        return []


def _firma(db, _a):
    kopf = (db.einstellung("briefkopf_1") or "").strip()
    return bool(kopf and kopf != "Firmenname" and (db.einstellung("benutzer_kuerzel") or "").strip())


def _stammdaten_seite(f, tabelle):
    seite = next((s for s in getattr(f, "seiten", ()) if s.t.name == tabelle), None)
    if seite is not None:
        f.zeigen(seite)
    return seite


def _neues_angebot_step(f):
    f.reiter.setCurrentWidget(f.angebote)
    return f.angebote.neu_aus_step()


def _zur_angebotsliste(f):
    f.reiter.setCurrentWidget(f.angebote)


PUNKTE = (
    Punkt("firma", "Firma und Kürzel eintragen",
          "Briefkopf und Logo für das Angebots-PDF, dazu Ihr Kürzel als Bearbeiter.", "Öffnen",
          lambda f: f.einstellung_zeigen("briefkopf_1"), _firma),
    Punkt("preise", "Maschine und Preise prüfen",
          "Maschine (Stangenlänge, Greiferrest), Stundensätze, Schneiddaten und Zuschläge: die Richtwerte an die "
          "eigene Fertigung anpassen.", "Öffnen", lambda f: _stammdaten_seite(f, "maschinen"), lambda _db, _a: False),
    Punkt("step", "Erstes Angebot aus einer STEP",
          "Neues Angebot aus STEP: Datei wählen, im Prüfdialog die Teile ansehen und übernehmen.", "Neues Angebot …",
          _neues_angebot_step, lambda _db, a: any(z.get("positionen") for z in a)),
    Punkt("optimieren", "Optimieren",
          "Im Angebot auf Optimieren klicken (F9): plant die Stangen und rechnet Material und Preise.",
          "Zu den Angeboten", _zur_angebotsliste, lambda _db, a: any(z.get("optimiert_am") for z in a)),
    Punkt("pdf", "Angebot als PDF verschicken",
          "Angebot (PDF) erstellen und verschicken; der Vorgang wird dabei „Verschickt“.", "Zu den Angeboten",
          _zur_angebotsliste, lambda _db, a: any(z.get("vorgang") in VERSCHICKT for z in a)),
)


def stand(db):
    """{Name: erledigt} je Punkt (erkannt oder abgehakt)."""
    gemerkt = dict(db.einstellung(EINSTELLUNG) or {})
    a = _angebote(db)
    aus = {}
    for p in PUNKTE:
        try:
            erkannt = bool(p.erkannt(db, a))
        except Exception:
            erkannt = False
        aus[p.name] = erkannt or bool(gemerkt.get(p.name))
    return aus


def _merken(db, **werte):
    if getattr(db, "nur_lesen", False):
        return
    gemerkt = dict(db.einstellung(EINSTELLUNG) or {})
    gemerkt.update(werte)
    db.einstellung_setzen(EINSTELLUNG, gemerkt)


def beim_start_zeigen(db):
    """True, wenn die Liste beim Start erscheinen soll: noch nicht gezeigt, etwas offen, kein erfahrener Platz."""
    gemerkt = dict(db.einstellung(EINSTELLUNG) or {})
    if gemerkt.get("_gezeigt"):
        return False
    if len(_angebote(db)) >= SCHON_ERFAHREN or all(stand(db).values()):
        _merken(db, _gezeigt=True)
        return False
    return True


class ErsteSchritte(QDialog):
    def __init__(self, fenster):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.setWindowTitle("Erste Schritte")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Willkommen!</b> Diese fünf Schritte führen zum ersten Angebot. Jeder Knopf öffnet die "
                             "richtige Stelle; erledigte Schritte sind abgehakt."))
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)
        self.haken, self.knoepfe = {}, {}
        for i, p in enumerate(PUNKTE):
            h = QCheckBox(f"{i + 1}. {p.titel}")
            h.toggled.connect(lambda an, n=p.name: self._abhaken(n, an))
            text = QLabel(p.text)
            text.setWordWrap(True)
            text.setStyleSheet("color: #5F6B7A; margin-left: 22px;")
            k = QPushButton(p.knopf)
            k.clicked.connect(lambda _=False, p=p: self.oeffnen(p))
            g.addWidget(h, 2 * i, 0)
            g.addWidget(k, 2 * i, 1, Qt.AlignRight)
            g.addWidget(text, 2 * i + 1, 0, 1, 2)
            self.haken[p.name], self.knoepfe[p.name] = h, k
        g.setColumnStretch(0, 1)
        lay.addLayout(g)
        lay.addWidget(QLabel("<span style='color:#5F6B7A'>Die Liste steht jederzeit unter Hilfe → Erste Schritte …"
                             "</span>"))
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.auffrischen()
        _merken(self.db, _gezeigt=True)

    def auffrischen(self):
        for n, fertig in stand(self.db).items():
            h = self.haken[n]
            h.blockSignals(True)
            h.setChecked(fertig)
            h.blockSignals(False)

    def _abhaken(self, name, an):
        _merken(self.db, **{name: bool(an)})
        self.auffrischen()

    def oeffnen(self, p):
        """Stelle des Punkts öffnen; „Maschine und Preise“ gilt damit als erledigt. Die Liste schließt sich."""
        if p.name == "preise":
            _merken(self.db, preise=True)
        self.accept()
        return p.oeffnen(self.f)


def zeigen(fenster):
    d = ErsteSchritte(fenster)
    if not fenster.stumm:
        d.open()
    return d
