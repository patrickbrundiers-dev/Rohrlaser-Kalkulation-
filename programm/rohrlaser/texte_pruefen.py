"""Abgeschnittene Texte finden (Verbesserungsplan 06.11.2026, E1).

abgeschnitten(wurzel) geht alle sichtbaren Bedienelemente unter wurzel durch und meldet, wo ein Text nicht ganz zu
sehen ist: Beschriftungen (QLabel) breiter als ihr Platz oder bei Zeilenumbruch höher, Knöpfe und Häkchen schmaler
als ihr Text, Platzhalter in Eingabefeldern, die nicht hineinpassen, und Spaltenköpfe von Tabellen, deren Text
breiter ist als die Spalte. Gemeint ist der Text, den man ohne Scrollen sehen soll; Elemente außerhalb des
sichtbaren Bereichs (Bildlauf) zählen nicht.

Ergebnis: Liste von Funden (Art, Text, Fenster-/Objektname, fehlende Pixel). Ohne Fenster nutzbar in Tests und
beim Erzeugen der Anleitungsbilder (anleitung/bilder.py, Umgebungsvariable RL_TEXTE_PRUEFEN).
"""
import re
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QAbstractScrollArea, QCheckBox, QComboBox,
                               QLabel, QLineEdit, QRadioButton, QTabBar, QWidget)

TOL = 2             # Pixel Spielraum (Kantenglättung, Rundung)


@dataclass
class Fund:
    art: str        # Beschriftung, Knopf, Platzhalter, Spaltenkopf, Auswahl
    text: str
    ort: str        # Kette der Objekt-/Klassennamen bis zum Fenster
    fehlt: int      # so viele Pixel fehlen

    def __str__(self):
        return f"{self.art} „{self.text[:60]}“ ({self.fehlt} px) in {self.ort}"


def _klartext(t):
    t = re.sub(r"<br\s*/?>", "\n", t or "", flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


def _ort(w):
    teile = []
    while w is not None:
        teile.append(w.objectName() or type(w).__name__)
        if w.isWindow():
            break
        w = w.parentWidget()
    return " < ".join(teile[:4])


def _sichtbarkeit(w):
    """(ganz sichtbar, im Bildlauf): ob w ganz zu sehen ist und ob ein Rollbereich (Bildlauf) es beschneidet –
    dann ist der Rest nach dem Scrollen zu sehen und zählt nicht."""
    fenster = w.window()
    r0 = QRect(w.mapTo(fenster, QPoint(0, 0)), w.size())
    r, rollen = QRect(r0), False
    p = w.parentWidget()
    while p is not None:
        pr = QRect(p.mapTo(fenster, QPoint(0, 0)) if p is not fenster else QPoint(0, 0), p.size())
        neu = r.intersected(pr)
        if neu != r and isinstance(p.parentWidget(), QAbstractScrollArea) and p is p.parentWidget().viewport():
            rollen = True
        r = neu
        if p is fenster:
            break
        p = p.parentWidget()
    return r.width() >= r0.width() - 1 and r.height() >= r0.height() - 1, rollen


def abgeschnitten(wurzel, mit_platzhalter=True):
    funde = []
    for w in [wurzel] + wurzel.findChildren(QWidget):
        if not w.isVisible() or w.width() <= 2 or w.height() <= 2:
            continue
        ganz, rollen = _sichtbarkeit(w)
        if not ganz:
            text = w.text() if isinstance(w, (QLabel, QAbstractButton)) else ""
            if text and not rollen and not isinstance(w, QTabBar):
                funde.append(Fund("verdeckt", _klartext(text), _ort(w), 0))
            continue
        fm = w.fontMetrics()
        if getattr(w, "gekuerzt_mit_tooltip", False):
            continue                # kürzt selbst mit „…“, der Tooltip zeigt den ganzen Text (z. B. KurzZeile)
        if isinstance(w, QLabel):
            if w.pixmap() is not None and not w.pixmap().isNull() or not w.text():
                continue
            text = _klartext(w.text())
            if not text or w.textFormat() == Qt.RichText and "<table" in w.text().lower():
                continue
            platz = w.contentsRect()
            if w.wordWrap():
                # heightForWidth gilt für das ganze Element (mit Rand und Innenabstand aus dem Stylesheet)
                hoch = w.heightForWidth(w.width())
                if hoch > w.height() + TOL and w.sizePolicy().verticalPolicy() != 0:
                    funde.append(Fund("Beschriftung", text, _ort(w), hoch - w.height()))
            else:
                breit = max(fm.horizontalAdvance(z) for z in text.split("\n")) + 2 * w.margin() + w.indent() \
                    if w.indent() > 0 else max(fm.horizontalAdvance(z) for z in text.split("\n")) + 2 * w.margin()
                if breit > platz.width() + TOL:
                    funde.append(Fund("Beschriftung", text, _ort(w), breit - platz.width()))
        elif isinstance(w, (QAbstractButton,)) and not isinstance(w, QTabBar) and w.text():
            soll = w.sizeHint().width()
            if isinstance(w, (QCheckBox, QRadioButton)) or w.text():
                if soll > w.width() + TOL:
                    funde.append(Fund("Häkchen" if isinstance(w, (QCheckBox, QRadioButton)) else "Knopf",
                                      w.text().replace("&", ""), _ort(w), soll - w.width()))
        elif isinstance(w, QLineEdit) and mit_platzhalter and w.placeholderText() and not w.text():
            frei = w.width() - 12
            if fm.horizontalAdvance(w.placeholderText()) > frei + TOL:
                funde.append(Fund("Platzhalter", w.placeholderText(), _ort(w),
                                  fm.horizontalAdvance(w.placeholderText()) - frei))
        elif isinstance(w, QComboBox) and not w.isEditable() and w.currentText():
            frei = w.width() - 28           # Pfeil und Rand
            if fm.horizontalAdvance(w.currentText()) > frei + TOL:
                funde.append(Fund("Auswahl", w.currentText(), _ort(w), fm.horizontalAdvance(w.currentText()) - frei))
        if isinstance(w, QAbstractItemView) and isinstance(w, QAbstractScrollArea) and hasattr(w, "horizontalHeader"):
            kopf = w.horizontalHeader()
            m = w.model()
            if kopf is None or m is None or not kopf.isVisible():
                continue
            hfm = kopf.fontMetrics()
            for i in range(m.columnCount()):
                if kopf.isSectionHidden(i) or kopf.sectionSize(i) <= 0:
                    continue
                x = kopf.sectionViewportPosition(i)
                if x < 0 or x + kopf.sectionSize(i) > kopf.viewport().width():
                    continue                # außerhalb: erst nach Bildlauf zu sehen
                t = m.headerData(i, Qt.Horizontal) or ""
                if not isinstance(t, str) or not t.strip():
                    continue
                # Spaltenköpfe brechen um: zu sehen ist der Text, wenn jedes Wort in die Spalte passt und alle
                # Zeilen in die Kopfhöhe
                platz = kopf.sectionSize(i) - 8
                wort = max(hfm.horizontalAdvance(z) for z in t.split())
                hoch = hfm.boundingRect(QRect(0, 0, max(platz, 1), 10000), Qt.TextWordWrap, t).height()
                if wort > platz + TOL:
                    funde.append(Fund("Spaltenkopf", t.replace("\n", " "), _ort(w), wort - platz))
                elif hoch > kopf.height() - 4 + TOL:
                    funde.append(Fund("Spaltenkopf", t.replace("\n", " "), _ort(w), hoch - kopf.height() + 4))
    return funde
