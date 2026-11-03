"""Zurücksetzen auf den Ursprung in Schweißbaugruppe und Satz in 3D (Patrick 03.11.2026, Freigabe 1a 2a 3a 4a; Regel:
Schritte aus einem Editor in alle Editoren, Rohr und Blech siehe teile_editor.EditorRahmen.ursprung).

Knopf „Zurücksetzen ▾“ mit
- „Alles wie beim Öffnen“: Struktur, Teile, Nahtgruppen, Arbeitsgänge, Steckverbindungen, neue Knickrahmen,
  Längsnähte per Klick, Kopf und Stammdaten wie beim Öffnen des Fensters;
- „Alles wie aus STEP importiert“: Schweißbaugruppe wie beim STEP-Import gemerkt (baugruppe['ursprung'], mit der
  Zuordnung der Teile nach Pos. und Artikel); Satz: ohne Steckverbindungen, neue Knickrahmen und Längsnähte;
- „Zurücksetzen rückgängig“ (Strg+Z): den Stand vor dem letzten Zurücksetzen wieder.
Vorher eine Rückfrage. Bis OK ändert nichts das Angebot (Abbrechen verwirft auch das Zurücksetzen).

Die Fenster rufen ursprung_merken() am Ende von __init__ und liefern _ursprung_kopf() / _ursprung_kopf_setzen(k) und
_ursprung_anzeigen() (Tabellen neu aufbauen, rechnen, 3D)."""
import copy

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QMessageBox, QPushButton

from . import einblendung
from .baugruppe import URSPRUNG, import_stand  # noqa: F401  (Schlüssel und Stand beim Import, ohne Qt)

OEFFNEN, IMPORT = "oeffnen", "import"


class UrsprungEditor:
    """Mixin für BaugruppeDialog und Satz3dDialog (erwartet self.bg, self.teile, self.knicke, self.laengsnaehte)."""
    URSPRUNG_STEP_TEXT = "Alles wie aus STEP importiert"

    def ursprung_knopf(self):
        k = QPushButton("Zurücksetzen")
        k.setToolTip("Auf den Ursprung zurücksetzen: wie beim Öffnen dieses Fensters oder wie aus der STEP-Datei "
                     "importiert (Strg+Z holt den Stand davor wieder)")
        menue = QMenu(k)
        self.ursprung_aktionen = {}
        for wie, text in ((OEFFNEN, "Alles wie beim Öffnen"), (IMPORT, self.URSPRUNG_STEP_TEXT),
                          ("zurueck", "Zurücksetzen rückgängig")):
            a = menue.addAction(text)
            a.triggered.connect(lambda _=False, wie=wie: self.ursprung_rueckgaengig() if wie == "zurueck"
                                else self.ursprung(wie))
            self.ursprung_aktionen[wie] = a
        menue.aboutToShow.connect(self._ursprung_pruefen)
        k.setMenu(menue)
        k.setEnabled(not getattr(self, "nur_lesen", False))
        kurz = QShortcut(QKeySequence.Undo, self)
        kurz.setContext(Qt.WindowShortcut)
        kurz.activated.connect(lambda: self._vor_ursprung is not None and self.ursprung_rueckgaengig())
        self.ursprung_k = k
        return k

    def ursprung_merken(self):
        self._oeffnen_stand = self._ursprung_stand()
        self._vor_ursprung = None

    # -------------------------------------------------------------- Stand
    def _ursprung_stand(self):
        return dict(bg=copy.deepcopy(self.bg), teile=[dict(t) for t in self.teile], knicke=list(self.knicke),
                    laengsnaehte=dict(getattr(self, "laengsnaehte", None) or {}), getrennt=list(getattr(self, "steck_getrennt", [])),
                    lagen=copy.deepcopy(getattr(self, "steck_lagen", {})), kopf=self._ursprung_kopf())

    def _ursprung_setzen(self, st):
        bg = self.bg
        for k in set(bg) | set(st["bg"]):
            neu = st["bg"].get(k)
            if isinstance(bg.get(k), list) and isinstance(neu, list):
                bg[k][:] = copy.deepcopy(neu)           # Tabellen halten die Liste
            elif k in st["bg"]:
                bg[k] = copy.deepcopy(neu)
            else:
                bg.pop(k, None)
        self.teile[:] = [dict(t) for t in st["teile"]]
        self.knicke[:] = list(st["knicke"])
        if isinstance(getattr(self, "laengsnaehte", None), dict):
            self.laengsnaehte.clear()
            self.laengsnaehte.update(st["laengsnaehte"])
        else:
            self.laengsnaehte = dict(st["laengsnaehte"])
        self.steck_getrennt = list(st["getrennt"])
        self.steck_lagen = copy.deepcopy(st["lagen"])
        self._ursprung_kopf_setzen(st["kopf"])
        self._ursprung_anzeigen()

    def _ursprung_geaendert(self):
        a, b = self._ursprung_stand(), self._oeffnen_stand
        return any(a[k] != b[k] for k in a)

    def ursprung_import(self):
        """Stand wie aus STEP importiert (dict wie _ursprung_stand) oder None."""
        return None

    def _ursprung_pruefen(self):
        a = self.ursprung_aktionen
        a[OEFFNEN].setEnabled(self._ursprung_geaendert())
        a[IMPORT].setEnabled(self.ursprung_import() is not None)
        a["zurueck"].setEnabled(self._vor_ursprung is not None)

    # -------------------------------------------------------------- Ausführen
    def ursprung(self, wie=OEFFNEN, fragen=True):
        """OEFFNEN = Stand beim Öffnen des Fensters, IMPORT = wie aus STEP importiert. Ergebnis: True = gesetzt."""
        if getattr(self, "nur_lesen", False):
            return False
        st = self._oeffnen_stand if wie == OEFFNEN else self.ursprung_import()
        if st is None:
            einblendung.melden(self, "Für diese Teile ist kein Stand aus dem STEP-Import gespeichert (vor Version "
                                     "0.9.237 eingelesen oder von Hand angelegt).")
            return False
        if wie == OEFFNEN and not self._ursprung_geaendert():
            return False
        if fragen and QMessageBox.question(
                self, "Auf Ursprung zurücksetzen",
                ("Alle Änderungen seit dem Öffnen dieses Fensters verwerfen?" if wie == OEFFNEN else
                 self._ursprung_frage()) + "\n\nStrg+Z bzw. „Zurücksetzen rückgängig“ holt den jetzigen Stand wieder; "
                "erst OK übernimmt ins Angebot.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        self._vor_ursprung = self._ursprung_stand()
        self._ursprung_setzen(st)
        einblendung.melden(self, "Wie beim Öffnen." if wie == OEFFNEN else "Wie aus STEP importiert.")
        return True

    def _ursprung_frage(self):
        return "Alles wieder so setzen, wie es aus der STEP-Datei importiert wurde? Alle Änderungen von Hand gehen verloren."

    def ursprung_rueckgaengig(self):
        if self._vor_ursprung is None:
            return False
        st, self._vor_ursprung = self._vor_ursprung, None
        self._ursprung_setzen(st)
        return True
