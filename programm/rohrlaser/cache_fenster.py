"""Hauptadmin → Angebots-Cache … (Patrick 19.11.2026, Angebotsbezogene Zwischenspeicherung): Verwaltung der
Rechenmerker-Dateien (dauermerker.py) und Kennzahlen zum Nutzen.

Zeigt je Datei Angebot, Größe, Einträge, Bereiche, Programmversion, angelegt, zuletzt benutzt und veraltete Einträge;
darüber die Kennzahlen seit dem Programmstart (Berechnungen gesamt, aus dem Cache, neu gerechnet, Trefferquote,
eingesparte Rechenzeit, Ladezeit, Größe). Knöpfe: Prüfen und reparieren, Neu aufbauen (markierte Angebote: löschen,
offene Angebote neu rechnen), Löschen, Exportieren (ZIP), Aufräumen, Mit Kollegen abgleichen. Der Cache ist nur ein Zwischenspeicher: jede
Aktion ist ohne Risiko für Angebote und Kalkulationen, gerechnet wird aus der Datenbank.
"""
import datetime
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHeaderView, QLabel,
                               QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import dauermerker

SPALTEN = ("Angebot", "Datei", "Größe", "Einträge", "Bereiche", "Version", "Angelegt", "Zuletzt benutzt", "Veraltet",
           "Zustand")


def _zeit(t):
    if not t:
        return "–"
    return datetime.datetime.fromtimestamp(t).strftime("%d.%m.%Y %H:%M")


def groesse_text(n):
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB".replace(".", ",")
    return f"{n / 1024:.0f} KB"


def kennzahlen_text(k=None, kollegen=None):
    """Übersicht wie in Patricks Beispiel (Kennzahl | Ergebnis); kollegen = dauermerker.teilen_stand(…)."""
    k = k or dauermerker.kennzahlen()
    q = f"{100 * k['quote']:.0f} %" if k["quote"] is not None else "–"
    zeilen = [("Berechnungen gesamt", f"{k['gesamt']}"), ("Aus Cache geladen", f"{k['treffer']}"),
              ("Neu berechnet", f"{k['neu']}"), ("Cache-Trefferquote", q),
              ("Eingesparte Berechnungen", f"{k['treffer']}"),
              ("Eingesparte Rechenzeit", f"{k['gespart_s']:.1f} s".replace(".", ",")),
              ("Ladezeit aus dem Cache", f"{k['laden_s']:.2f} s".replace(".", ",")),
              ("Rechenzeit neu berechnet", f"{k['rechnen_s']:.1f} s".replace(".", ",")),
              ("Cache-Dateien / Größe", f"{k['dateien']} / {groesse_text(k['groesse'])}"),
              ("Von Kollegen übernommen", f"{k.get('von_kollegen', 0)} Einträge (gemeinsamer Ordner)"),
              ("In den gemeinsamen Ordner gelegt", f"{k.get('geteilt', 0)} Angebot(e)"),
              ("Letzter Abgleich mit Kollegen", _zeit(k.get("abgleich")) if k.get("abgleich") else "–")]
    for kuerzel, e in sorted((kollegen or {}).items()):
        zeilen.append((f"  Kopien von {kuerzel}", f"{e['dateien']} Datei(en), {groesse_text(e['groesse'])}, "
                                                  f"Stand {_zeit(e['neueste'])}"))
    if k.get("aus"):
        zeilen.append(("Zustand", "aus (kein Datenordner oder nicht nutzbar)"))
    breite = max(len(a) for a, _ in zeilen)
    return "\n".join(f"{a:<{breite}}  {b}" for a, b in zeilen)


class CacheFenster(QDialog):
    def __init__(self, f=None):
        super().__init__(f)
        self.f = f
        self.setWindowTitle("Angebots-Cache")
        self.resize(1000, 600)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Zwischengespeicherte Rechenergebnisse auf diesem PC (Daten/Rechenmerker). Sie lassen "
                             "sich jederzeit aus der Datenbank neu rechnen; Löschen schadet nie, das nächste Öffnen "
                             "rechnet dann einmal neu."))
        self.kennzahlen = QPlainTextEdit(readOnly=True)
        self.kennzahlen.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.kennzahlen.setMaximumHeight(260)
        lay.addWidget(self.kennzahlen)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.tabelle)
        self.meldung = QLabel("")
        lay.addWidget(self.meldung)
        knoepfe = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.knoepfe = {}
        for name, tun in (("Aktualisieren", self.aktualisieren), ("Prüfen und reparieren", self.pruefen),
                          ("Neu aufbauen", self.neu_aufbauen), ("Löschen", self.loeschen),
                          ("Exportieren …", self.exportieren), ("Aufräumen", self.aufraeumen),
                          ("Mit Kollegen abgleichen", self.abgleichen)):
            b = QPushButton(name)
            b.clicked.connect(lambda _=False, t=tun: t())
            knoepfe.addButton(b, QDialogButtonBox.ButtonRole.ActionRole)
            self.knoepfe[name] = b
        knoepfe.rejected.connect(self.close)
        lay.addWidget(knoepfe)
        self.zeilen = []
        self.aktualisieren()

    def aktualisieren(self):
        kollegen = None
        geteilt = self.f._cache_geteilt() if hasattr(self.f, "_cache_geteilt") else None
        if geteilt is not None:
            kollegen = dauermerker.teilen_stand(geteilt[0])
        self.kennzahlen.setPlainText(kennzahlen_text(kollegen=kollegen))
        self.zeilen = dauermerker.uebersicht()
        self.tabelle.setRowCount(len(self.zeilen))
        for i, e in enumerate(self.zeilen):
            angebot = (e["nummer"] or f"ID {e['angebot_id']}") if e["angebot_id"] is not None else "allgemein"
            bereiche = ", ".join(f"{b} {n}" for b, n in sorted(e["bereiche"].items()))
            werte = (angebot, e["pfad"].name, groesse_text(e["groesse"]), str(e["eintraege"]), bereiche,
                     e["programm"] or "–", _zeit(e["angelegt"]), _zeit(e["benutzt"] or e["geaendert"]),
                     str(e["veraltet"]), e["fehler"] or "in Ordnung")
            for j, w in enumerate(werte):
                self.tabelle.setItem(i, j, QTableWidgetItem(w))

    def markierte(self):
        """Angebots-IDs (None = allgemeine Datei) der markierten Zeilen."""
        zeilen = sorted({i.row() for i in self.tabelle.selectedIndexes()})
        return [self.zeilen[i]["angebot_id"] for i in zeilen if i < len(self.zeilen)]

    def pruefen(self):
        erg = dauermerker.pruefen()
        unlesbar = sum(e["unlesbar"] for e in erg)
        ersetzt = sum(1 for e in erg if e["ersetzt"])
        doppelt = sum(e["doppelt"] for e in erg)
        self.meldung.setText(f"{len(erg)} Datei(en) geprüft, {sum(e['eintraege'] for e in erg)} Einträge: "
                             f"{unlesbar} unlesbare gelöscht, {ersetzt} beschädigte Datei(en) ersetzt, "
                             f"{doppelt} doppelte Inhalte (gleiches Ergebnis aus verschiedenen Eingaben, harmlos).")
        self.aktualisieren()
        return erg

    def loeschen(self, ids=None):
        ids = self.markierte() if ids is None else ids
        n = sum(dauermerker.loeschen(a) for a in ids) if ids else dauermerker.loeschen("alle")
        self.meldung.setText(f"{n} Datei(en) gelöscht; gerechnet wird beim nächsten Bedarf neu.")
        self.aktualisieren()
        return n

    def neu_aufbauen(self, ids=None):
        """Markierte (sonst alle) löschen und offene Angebote gleich neu rechnen (füllt den Cache wieder)."""
        ids = self.markierte() if ids is None else ids
        self.loeschen(ids)
        offen = getattr(self.f, "offen", {}) or {}
        neu = 0
        for aid, seite in list(offen.items()):
            if not ids or aid in ids:
                from . import rechenmerker
                rechenmerker.alle_leeren()
                seite.neu_laden()
                neu += 1
        dauermerker.leeren()
        self.meldung.setText(self.meldung.text() + f" {neu} offene(s) Angebot(e) neu gerechnet.")
        self.aktualisieren()
        return neu

    def exportieren(self, ziel=None):
        if ziel is None:
            vorschlag = Path.home() / f"Rohrlaser-Cache {datetime.date.today():%Y-%m-%d}.zip"
            ziel, _ = QFileDialog.getSaveFileName(self, "Angebots-Cache exportieren", str(vorschlag), "ZIP (*.zip)")
            if not ziel:
                return None
        pfad = dauermerker.exportieren(ziel)
        self.meldung.setText(f"Exportiert: {pfad}")
        return pfad

    def abgleichen(self, warten_s=30.0):
        """Gleich jetzt mit dem gemeinsamen Ordner abgleichen (sonst jede Minute von selbst)."""
        t = self.f._cache_abgleich() if hasattr(self.f, "_cache_abgleich") else None
        if t is None:
            alt = getattr(self.f, "_cache_abgleich_faden", None)
            if alt is None or not alt.is_alive():
                self.meldung.setText("Kein Abgleich: Kürzel und gemeinsamer Ordner sind nicht eingetragen.")
                return None
            t = alt
        t.join(warten_s)
        self.meldung.setText("Mit den Kollegen abgeglichen." if not t.is_alive() else "Abgleich läuft noch im "
                             "Hintergrund (langsames Netz).")
        self.aktualisieren()
        return t

    def aufraeumen(self):
        ids = None
        db = getattr(self.f, "db", None)
        if db is not None:
            ids = {r[0] for r in db.con.execute("SELECT id FROM angebote").fetchall()}
        weg = dauermerker.aufraeumen(ids)
        self.meldung.setText(f"Aufgeräumt: {weg['dateien']} Datei(en) und {weg['eintraege']} veraltete Einträge "
                             f"entfernt (gelöschte oder lange unbenutzte Angebote, alte Programmversionen).")
        self.aktualisieren()
        return weg


def cache_fenster(f, zeigen=True):
    from . import fenster_wache
    if zeigen:                      # nur ein Fenster; erneutes Öffnen holt es nach vorn (27.11.2026)
        return fenster_wache.einmal(f, "_cache_fenster", lambda: CacheFenster(f))
    return fenster_wache.ersetzen(f, "_cache_fenster", CacheFenster(f))
