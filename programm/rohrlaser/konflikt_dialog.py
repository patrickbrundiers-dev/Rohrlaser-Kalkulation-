"""Rückfrage bei einem Änderungskonflikt (Datenbank-Auftrag 19.11.2026, Schritt 3 „Versionsnummern“).

Jede Eingabe in Stammdaten, Positionen und Angebotskopf wird mit der beim Anzeigen gelesenen Versionsnummer und dem
angezeigten Wert gespeichert (Datenbank.aendern/position_aendern/angebot_aendern version=…, erwartet=…). Hat jemand
dasselbe Feld inzwischen anders gespeichert (Abgleich mit Kollegen, zweites Fenster), wird nichts still
überschrieben: dieser Dialog zeigt beide Werte und lässt wählen.

fragen(k) -> MEINE (Eingabe trotzdem speichern) oder NEU_LADEN (gespeicherten Wert behalten und anzeigen).
In Tests ohne Fenster: ANTWORT setzen.
"""
from PySide6.QtWidgets import QApplication, QMessageBox

MEINE, NEU_LADEN = "meine", "neu_laden"
ANTWORT = None          # Tests: MEINE oder NEU_LADEN statt der Rückfrage


def _text(w):
    return "leer" if w in (None, "") else str(w)


def fragen(k, titel="", parent=None):
    """k: datenbank.AenderungsKonflikt. Gelöschte Zeile: nur Hinweis, Ergebnis NEU_LADEN."""
    if ANTWORT is not None:
        return NEU_LADEN if k.geloescht else ANTWORT
    parent = parent or QApplication.activeWindow()
    feld = titel or k.feld
    if k.geloescht:
        QMessageBox.information(parent, "Zeile gelöscht", "Diese Zeile wurde inzwischen gelöscht (Abgleich oder "
                                "anderes Fenster). Ihre Eingabe ist nicht gespeichert; die Ansicht wird neu geladen.")
        return NEU_LADEN
    box = QMessageBox(QMessageBox.Icon.Warning, "Inzwischen geändert",
                      f"„{feld}“ wurde inzwischen woanders geändert (Abgleich mit einem Kollegen oder ein anderes "
                      f"Fenster).\n\nJetzt gespeichert: {_text(k.jetzt)}\nIhre Eingabe: {_text(k.eingabe)}\n\n"
                      "Welcher Wert soll gelten?", parent=parent)
    meine = box.addButton("Meine Eingabe speichern", QMessageBox.ButtonRole.AcceptRole)
    neu = box.addButton("Gespeicherten Wert behalten", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(neu)
    box.exec()
    return MEINE if box.clickedButton() is meine else NEU_LADEN
