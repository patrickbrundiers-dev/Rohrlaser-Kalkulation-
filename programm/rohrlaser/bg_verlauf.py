"""Rückgängig und Wiederholen in der Schweißbaugruppe und in „Satz in 3D“ (Plan 3D-Viewer
18.11.2026, Paket V4; im Rohr- und Blech-Editor gibt es das schon, teile_editor.Schritt).

Gemerkt wird nach jeder Änderung (aktualisieren): Steckverbindungen, Teilen gleicher Teile, Knickrahmen,
Teilefamilien, Längsnähte per Klick, Lagen der Nasen.
Der Stand ist derselbe, den „Zurücksetzen“ merkt (editor_ursprung, keine zweite Logik), dazu Teilefamilien; damit
gehören auch Eingaben in den Tabellen (Nähte, Arbeitsgänge, Kopf) und Zurücksetzen selbst dazu. Rückgängig setzt den
Stand zurück und baut Tabellen und 3D neu auf wie Zurücksetzen.

Gemeinsam für BaugruppeDialog und Satz3dDialog (Mixin neben UrsprungEditor): erwartet _ursprung_stand,
_ursprung_setzen, self._netz_cache, self.ansicht3d.knopf und self.aktualisieren()."""
import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QUndoCommand, QUndoStack

TIEFE = 100                 # so viele Schritte zurück


class _Schritt(QUndoCommand):
    def __init__(self, besitzer, vorher, nachher, text):
        super().__init__(text)
        self.b, self.vorher, self.nachher, self._erst = besitzer, vorher, nachher, True

    def redo(self):
        if self._erst:          # beim Ablegen ist der Schritt schon geschehen
            self._erst = False
            return
        self.b._verlauf_setzen(self.nachher)

    def undo(self):
        self.b._verlauf_setzen(self.vorher)


class BgVerlauf:
    """Mixin: verlauf_anlegen() einmal nach dem Bau der 3D-Leiste, verlauf_merken() am Ende von aktualisieren()."""

    def verlauf_anlegen(self, nur_lesen=False):
        self.verlauf = QUndoStack(self)
        self.verlauf.setUndoLimit(TIEFE)
        self._verlauf_stand = None              # Ausgangsstand beim ersten verlauf_merken (nach dem ersten Rechnen)
        self._verlauf_setzt = False
        self.zurueck_knopf = self.ansicht3d.knopf("Rückgängig", "Letzten Schritt zurücknehmen (Strg+Z): Steckverbindung, "
                                                  "Teilen, Knickrahmen, Teilefamilie, Längsnaht, Eingabe, Zurücksetzen",
                                                  False, lambda: self.verlauf.undo())
        self.vor_knopf = self.ansicht3d.knopf("Wiederholen", "Zurückgenommenen Schritt wiederholen (Strg+Y)", False,
                                              lambda: self.verlauf.redo())
        for k, sym in ((self.zurueck_knopf, "rueckgaengig"), (self.vor_knopf, "wiederholen")):
            try:
                from . import symbole
                k.setIcon(symbole.symbol(sym))
            except Exception:       # noqa: BLE001 – ohne Symbol bleibt der Text
                pass
        self.verlauf.canUndoChanged.connect(self.zurueck_knopf.setEnabled)
        self.verlauf.canRedoChanged.connect(self.vor_knopf.setEnabled)
        self.zurueck_knopf.setEnabled(False)
        self.vor_knopf.setEnabled(False)
        if nur_lesen:
            self.zurueck_knopf.hide()
            self.vor_knopf.hide()
            return
        # Strg+Z hat das Fenster schon (editor_ursprung, Zurücksetzen rückgängig): es ruft verlauf_zurueck
        folgen = {f.toString(): f for f in QKeySequence.keyBindings(QKeySequence.Redo) + [QKeySequence("Ctrl+Y")]}
        for folge in folgen.values():          # je Taste nur einmal (sonst mehrdeutig: keiner wirkt)
            s = QShortcut(folge, self)
            s.setContext(Qt.WindowShortcut)
            s.activated.connect(self.verlauf.redo)

    def _verlauf_lesen(self):
        """Stand wie „Zurücksetzen“ ihn merkt (editor_ursprung: Baugruppe samt Steckverbindungen und Nähten, Teile,
        Knickrahmen, Längsnähte, Teilen, Lagen, Kopf), dazu Teilefamilien und die Netze geteilter Teile."""
        return dict(u=self._ursprung_stand(), familien=copy.deepcopy(self.__dict__.get("familien")),
                    netz=dict(getattr(self, "_netz_cache", {}) or {}))

    @staticmethod
    def _verlauf_schluessel(st):
        """Was als Änderung zählt (die Netze nicht: sie folgen dem Teilen)."""
        return st["u"], st["familien"]

    def verlauf_merken(self, text=None):
        """Nach einer Änderung: neuer Schritt, wenn sich der Stand geändert hat. Der erste Aufruf (beim Öffnen, nach
        dem ersten Rechnen) setzt nur den Ausgangsstand."""
        if getattr(self, "verlauf", None) is None or self._verlauf_setzt:
            return False
        neu = self._verlauf_lesen()
        if self._verlauf_stand is None:
            self._verlauf_stand = neu
            return False
        try:
            gleich = self._verlauf_schluessel(neu) == self._verlauf_schluessel(self._verlauf_stand)
        except Exception:           # noqa: BLE001 – nicht vergleichbar: als Änderung merken
            gleich = False
        if gleich:
            return False
        alt, self._verlauf_stand = self._verlauf_stand, neu
        self.verlauf.push(_Schritt(self, alt, neu, text or self._verlauf_text(alt, neu)))
        return True

    @staticmethod
    def _verlauf_text(alt, neu):
        a, n = alt["u"], neu["u"]
        if len(n["teile"]) != len(a["teile"]):
            return "Teilen"
        if n["bg"].get("steckverbindungen") != a["bg"].get("steckverbindungen"):
            return "Steckverbindungen"
        if n["knicke"] != a["knicke"]:
            return "Knickrahmen"
        if n["laengsnaehte"] != a["laengsnaehte"]:
            return "Längsnaht"
        if neu["familien"] != alt["familien"]:
            return "Teilefamilie"
        return "Eingabe"

    def verlauf_zurueck(self):
        """Strg+Z: einen Schritt zurück (auch ein Zurücksetzen). False, wenn nichts zurückzunehmen ist."""
        if getattr(self, "verlauf", None) is None or not self.verlauf.canUndo():
            return False
        self.verlauf.undo()
        return True

    def _verlauf_setzen(self, st):
        """Stand zurückholen; Tabellen, Rechnung und 3D baut _ursprung_setzen neu auf."""
        self._verlauf_setzt = True
        try:
            if hasattr(self, "_netz_cache"):
                self._netz_cache.clear()
                self._netz_cache.update(st["netz"])
            if st["familien"] is None:
                self.__dict__.pop("familien", None)
            else:
                self.familien = copy.deepcopy(st["familien"])
            if getattr(self, "familie_knopf", None) is not None:
                self.familie_knopf.setText(f"Teilefamilie … ({sum(len(z) for _, z in self.familien or ())})")
            self.__dict__.pop("_rohr_cache", None)
            self._ursprung_setzen(copy.deepcopy(st["u"]))
            self._verlauf_stand = self._verlauf_lesen()
        finally:
            self._verlauf_setzt = False
