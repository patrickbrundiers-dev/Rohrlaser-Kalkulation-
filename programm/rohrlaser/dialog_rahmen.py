"""Einheitlicher Dialog-Rahmen, Variante B (Freigabe Patrick 28.11.2026, Auftrag „Expertenmodus professionalisieren“).

Aufbau eines freigegebenen Dialogs:
- Kopf über die volle Breite: Titel und die Erklärung des Dialogs (erstes Label mit Umbruch oder langem Text);
- Aktionen auf markierte Zeilen als Leiste über der Tabelle: höchstens drei sichtbar, der Rest und alles Gefährliche
  (Löschen, Vergessen, Zurücksetzen, …) unter „Weitere Aktionen“, Gefährliches mit Trennstrich am Ende;
- Fußleiste: rechts Hauptaktion (OK, Übernehmen) und Schließen/Abbrechen.
Ohne Tabelle bleiben die Aktionen links in der Fußleiste.

Nur Dialoge mit der Eigenschaft dialog_rahmen bekommen den Rahmen (je Ansicht freigegeben, siehe FREIGEGEBEN);
die zentrale Fensterverwaltung (fenster_merken) setzt ihn beim ersten Zeigen. Knöpfe bleiben dieselben Objekte:
Signale, Tastenkürzel und Aktivierung (setEnabled) gelten weiter, versteckte Knöpfe stehen im Menü mit ihrem Zustand.
Farben stehen im Stylesheet des Themes (stil.STIL), Dunkel und Hoher Kontrast setzen sie um.
"""
from PySide6.QtWidgets import (QAbstractItemView, QDialogButtonBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QMenu,
                               QPushButton, QVBoxLayout, QWidget)

EIGENSCHAFT = "dialog_rahmen"
# Freigegebene Ansichten (Freigabeseite 1, Variante B); neue Dialoge nur nach Freigabe ergänzen
FREIGEGEBEN = ("Lernzentrale", "Angebots-Cache", "Automatik-Protokoll", "Preis-Simulator", "Diagnose: Rechenzähler",
               "Sicherung wiederherstellen", "Archiv durchsuchen", "Referenzangebote prüfen", "Kostentreiber")
GEFAHR = ("löschen", "vergessen", "zurücksetzen", "aufräumen", "neu aufbauen", "nicht mehr lernen", "entfernen")
MAX_SICHTBAR = 3
HINWEIS = "Zeilen markieren, dann Aktion wählen"


def vormerken(d):
    """Dialog für den Rahmen vormerken (vor dem ersten Zeigen). Ergebnis: der Dialog."""
    d.setProperty(EIGENSCHAFT, True)
    return d


def gefaehrlich(text):
    t = text.replace("&", "").lower()
    return any(g in t for g in GEFAHR)


def _knoepfe(d):
    """Knopfleiste des Dialogs zerlegen: (Box, Aktionen, Hauptaktionen, Schließen)."""
    box = next((b for b in d.findChildren(QDialogButtonBox) if b.window() is d), None)
    aktionen, haupt, schliessen = [], [], []
    if box is None:
        return None, aktionen, haupt, schliessen
    for b in box.buttons():
        rolle = box.buttonRole(b)
        std = box.standardButton(b)
        if rolle == QDialogButtonBox.RejectRole or std in (QDialogButtonBox.Close, QDialogButtonBox.Cancel):
            schliessen.append(b)
        elif rolle in (QDialogButtonBox.AcceptRole, QDialogButtonBox.YesRole, QDialogButtonBox.ApplyRole):
            haupt.append(b)
        else:
            aktionen.append(b)
    return box, aktionen, haupt, schliessen


def _weitere(liste, eltern):
    """Knopf „Weitere Aktionen“ mit Menü; die Einträge übernehmen Text, Tooltip und Aktivierung beim Öffnen."""
    if not liste:
        return None
    k = QPushButton("Weitere Aktionen", eltern)
    k.setObjectName("weitere")
    m = QMenu(k)
    eintraege = []
    for i, b in enumerate(liste):
        if i and gefaehrlich(b.text()) and not gefaehrlich(liste[i - 1].text()):
            m.addSeparator()
        a = m.addAction(b.text())
        a.setToolTip(b.toolTip())
        a.triggered.connect(b.click)
        eintraege.append((a, b))
        b.hide()

    def auffrischen():
        for a, b in eintraege:
            a.setText(b.text())
            a.setEnabled(b.isEnabled())
    m.aboutToShow.connect(auffrischen)
    m.setToolTipsVisible(True)
    k.setMenu(m)
    return k


def _tabelle(d):
    return next((v for v in d.findChildren(QAbstractItemView)
                 if v.window() is d and not isinstance(v, QHeaderView) and v.isVisibleTo(d)), None)


def anwenden(d):
    """Rahmen einsetzen (einmal je Dialog). Ergebnis: True, wenn gesetzt."""
    lay = d.layout()
    if not isinstance(lay, QVBoxLayout) or d.property("_dialog_rahmen_gesetzt"):
        return False
    d.setProperty("_dialog_rahmen_gesetzt", True)
    # 1 Kopf: Titel + Erklärung
    erkl = None
    if lay.count() and isinstance(lay.itemAt(0).widget(), QLabel):
        erste = lay.itemAt(0).widget()
        if erste.wordWrap() or len(erste.text()) > 60:
            erkl = erste
            lay.removeWidget(erste)
    kopf = QFrame(d)
    kopf.setObjectName("dialogkopf")
    kz = QVBoxLayout(kopf)
    kz.setContentsMargins(20, 14, 20, 12)
    kz.setSpacing(3)
    titel = QLabel(d.windowTitle(), kopf)
    titel.setObjectName("dialogtitel")
    d.windowTitleChanged.connect(titel.setText)
    kz.addWidget(titel)
    if erkl is not None:
        erkl.setObjectName("nebentext")
        erkl.setWordWrap(True)
        kz.addWidget(erkl)
    # 2 Knöpfe
    box, aktionen, haupt, schliessen = _knoepfe(d)
    if box is not None:
        for b in box.buttons():
            box.removeButton(b)
        box.hide()
    for b in haupt:
        b.setObjectName("primaer")
    normal = [b for b in aktionen if not gefaehrlich(b.text())]
    sichtbar = normal[:MAX_SICHTBAR]
    mehr = normal[MAX_SICHTBAR:] + [b for b in aktionen if gefaehrlich(b.text())]
    fuss = QFrame(d)
    fuss.setObjectName("dialogfuss")
    fz = QHBoxLayout(fuss)
    fz.setContentsMargins(20, 10, 20, 10)
    fz.setSpacing(8)
    tabelle = _tabelle(d)
    if tabelle is not None and aktionen:
        leiste = QWidget(d)
        leiste.setObjectName("dialogaktionen")
        lz = QHBoxLayout(leiste)
        lz.setContentsMargins(0, 0, 0, 6)
        lz.setSpacing(8)
        for b in sichtbar:
            lz.addWidget(b)
        w = _weitere(mehr, leiste)
        if w is not None:
            lz.addWidget(w)
        lz.addStretch(1)
        h = QLabel(HINWEIS, leiste)
        h.setObjectName("nebentext")
        lz.addWidget(h)
        idx = lay.indexOf(tabelle)
        p = tabelle
        while idx < 0 and p is not None:
            p = p.parentWidget()
            idx = lay.indexOf(p) if p is not None else -1
        lay.insertWidget(max(0, idx), leiste)
    else:
        for b in sichtbar:
            fz.addWidget(b)
        w = _weitere(mehr, fuss)
        if w is not None:
            fz.addWidget(w)
    fz.addStretch(1)
    for b in haupt + schliessen:
        fz.addWidget(b)
        b.show()
    if haupt:
        haupt[0].setDefault(True)
    # 3 Inhalt mit 20 px Rand, Kopf und Fuß über die volle Breite; Platz für Tabelle/Text
    inhalt = QWidget(d)
    il = QVBoxLayout(inhalt)
    il.setContentsMargins(20, 14, 20, 14)
    il.setSpacing(max(6, lay.spacing()))
    while lay.count():
        it = lay.takeAt(0)
        if it.widget() is not None:
            if it.widget() is not box:
                il.addWidget(it.widget())
        elif it.layout() is not None:
            il.addLayout(it.layout())
        elif it.spacerItem() is not None:
            il.addItem(it.spacerItem())
    gross = ("QPlainTextEdit", "QTextEdit", "QTextBrowser", "QTabWidget", "QSplitter")
    for i in range(il.count()):
        wdg = il.itemAt(i).widget()
        if wdg is not None and (isinstance(wdg, QAbstractItemView) or type(wdg).__name__ in gross
                                or (wdg.objectName() != "dialogaktionen" and wdg.findChild(QAbstractItemView))):
            il.setStretch(i, 1)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(kopf)
    lay.addWidget(inhalt, 1)
    lay.addWidget(fuss)
    return True
