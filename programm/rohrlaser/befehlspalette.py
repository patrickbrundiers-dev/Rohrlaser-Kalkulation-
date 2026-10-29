"""Befehlspalette Strg+K (Layout-Plan L20): ein Suchfeld für Angebote, Kunden, Profile, Werkstoffe, Einstellungen
und Befehle aus den Menüs. Tippen filtert, ↑/↓ wählt, Enter führt aus, Esc schließt.

eintraege() sammelt die Ziele, treffer() sucht darin (alle Wörter müssen vorkommen; Treffer am Wortanfang und im
Titel zuerst). Beides ist ohne Fenster testbar.
"""
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

MAX_TREFFER = 40
MAX_ANGEBOTE = 500          # so viele neueste Angebote durchsucht die Palette


@dataclass
class Eintrag:
    art: str                # Angebot, Kunde, Profil, Werkstoff, Einstellung, Befehl, Reiter
    titel: str
    zusatz: str
    aktion: Callable


def _menue_befehle(f):
    """Alle Menüpunkte des Hauptfensters (Menü → Punkt), nur freigegebene."""
    aus = []
    for a in f.menuBar().actions():
        m = a.menu()
        if m is None:
            continue
        name = a.text().replace("&", "")
        for b in m.actions():
            if b.isSeparator() or not b.text() or b.menu() is not None:
                continue
            aus.append((name, b))
    return aus


def eintraege(f):
    """Ziele der Palette im Hauptfenster f."""
    from . import einstellungen_ordnung
    from .stammdaten import EINSTELLUNGEN
    aus = []
    for i in range(f.reiter.count()):
        seite = f.reiter.widget(i)
        if not f.reiter.isTabVisible(i):        # z. B. Versand ausgeschaltet
            continue
        aus.append(Eintrag("Reiter", f.reiter.tabText(i), "Reiter öffnen",
                           lambda seite=seite: f.reiter.setCurrentWidget(seite)))
    for name, a in _menue_befehle(f):
        if a.isEnabled():
            kurz = a.shortcut().toString()
            aus.append(Eintrag("Befehl", a.text().replace("&", ""), f"Menü {name}" + (f" · {kurz}" if kurz else ""),
                               lambda a=a: a.trigger()))
    seite = f.reiter.currentWidget()
    if hasattr(seite, "check_zeigen"):          # geöffnetes Angebot: Angebots-Check (Plan A2)
        aus.append(Eintrag("Befehl", "Angebots-Check …", f"Angebot {seite.kopf.get('nummer') or ''}".strip(),
                           lambda seite=seite: seite.check_zeigen()))
    for z in f.db.angebote()[:MAX_ANGEBOTE]:
        aus.append(Eintrag("Angebot", str(z.get("nummer") or ""),
                           " · ".join(str(x) for x in (z.get("kunde"), z.get("datum"), z.get("vorgang")) if x),
                           lambda aid=z["id"]: f.angebot_oeffnen(aid)))
    for z in f.db.zeilen("kunden"):
        aus.append(Eintrag("Kunde", str(z.get("name") or ""), str(z.get("kundennr") or ""),
                           lambda z=z: f.kunde_zeigen(z.get("kundennr"), z.get("name"))))
    seiten = {s.t.name: s for s in f.seiten}
    for tabelle, feld, art in (("profile", "profil_id", "Profil"), ("werkstoffe", "werkstoff_id", "Werkstoff")):
        seite = seiten.get(tabelle)
        if seite is None:
            continue
        for z in f.db.zeilen(tabelle):
            wert = str(z.get(feld) or "")
            if wert:
                aus.append(Eintrag(art, wert, f"Einstellungen → {seite.t.titel}",
                                   lambda seite=seite, wert=wert: _stammdaten(f, seite, wert)))
    for e in EINSTELLUNGEN:
        if e.gruppe == "Frachtkosten":      # stehen nicht in den Vorgaben, sondern im Reiter Frachtkosten
            if getattr(f, "fracht", None) is not None:
                aus.append(Eintrag("Einstellung", e.titel, "Frachtkosten → Historie, Einstellungen",
                                   lambda e=e: _fracht_einstellung(f, e.titel)))
            continue
        seiten = einstellungen_ordnung.seiten_von(e.name)
        if not seiten:                      # intern (z. B. zuletzt gewählter CSV-Ordner)
            continue
        aus.append(Eintrag("Einstellung", e.titel, f"Einstellungen → {einstellungen_ordnung.SEITE[seiten[0]].titel}",
                           lambda e=e: _einstellung(f, e.titel, e.name)))
    return aus


def _stammdaten(f, seite, wert):
    f.zeigen(seite)
    if hasattr(seite, "suche"):
        seite.suche.setText(wert)


def _einstellung(f, titel, name=None):
    if name is None or getattr(f, "einstellung_zeigen", lambda n: None)(name) is None:
        f.zeigen(f.einstellungen)
    nav = f.bereich.unter
    if hasattr(nav, "suche"):
        nav.suche.setText(titel)


def _fracht_einstellung(f, titel):
    seite = f.fracht.historie
    f.fracht.zeigen(seite)
    seite.einstellungen.filtern(titel)


def treffer(liste, suche, anzahl=MAX_TREFFER):
    """Passende Einträge, bester zuerst. Leere Suche: Reiter und Befehle."""
    worte = suche.lower().split()
    if not worte:
        return [e for e in liste if e.art in ("Reiter", "Befehl")][:anzahl]
    gefunden = []
    for n, e in enumerate(liste):
        titel, zusatz = e.titel.lower(), e.zusatz.lower()
        text = f"{titel} {zusatz} {e.art.lower()}"
        if not all(w in text for w in worte):
            continue
        punkte = 0
        for w in worte:
            if titel.startswith(w):
                punkte += 4
            elif any(t.startswith(w) for t in titel.replace("-", " ").split()):
                punkte += 3
            elif w in titel:
                punkte += 2
        gefunden.append((-punkte, n, e))
    gefunden.sort(key=lambda x: (x[0], x[1]))
    return [e for _, _, e in gefunden[:anzahl]]


class Befehlspalette(QDialog):
    ENTER_SCHLIESST = True      # Enter führt den gewählten Befehl aus (tastatur.EnterRegel: Ausnahme)

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f = fenster
        self.setWindowTitle("Befehlspalette")
        self.setMinimumWidth(620)
        self.liste_alle = eintraege(fenster)
        lay = QVBoxLayout(self)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Angebot, Kunde, Profil, Einstellung oder Befehl suchen …")
        self.suche.textChanged.connect(self.filtern)
        self.suche.installEventFilter(self)
        self.liste = QListWidget()
        self.liste.itemActivated.connect(self.ausfuehren)
        hinweis = QLabel("↑/↓ wählen · Enter ausführen · Esc schließen")
        hinweis.setStyleSheet("color: #5F6B7A;")
        lay.addWidget(self.suche)
        lay.addWidget(self.liste, 1)
        lay.addWidget(hinweis)
        self.resize(680, 460)
        self.filtern("")

    def filtern(self, text):
        self.liste.clear()
        for e in treffer(self.liste_alle, text):
            it = QListWidgetItem(f"{e.art}:  {e.titel}" + (f"   —   {e.zusatz}" if e.zusatz else ""))
            it.setData(Qt.UserRole, e)
            self.liste.addItem(it)
        if self.liste.count():
            self.liste.setCurrentRow(0)

    def eventFilter(self, obj, ereignis):
        if obj is self.suche and ereignis.type() == ereignis.Type.KeyPress:
            taste = ereignis.key()
            if taste in (Qt.Key_Down, Qt.Key_Up):
                schritt = 1 if taste == Qt.Key_Down else -1
                n = self.liste.count()
                if n:
                    self.liste.setCurrentRow((self.liste.currentRow() + schritt) % n)
                return True
            if taste in (Qt.Key_Return, Qt.Key_Enter):
                self.ausfuehren(self.liste.currentItem())
                return True
        return super().eventFilter(obj, ereignis)

    def ausfuehren(self, item=None):
        if item is None:
            return None
        e = item.data(Qt.UserRole)
        self.accept()
        e.aktion()
        return e
