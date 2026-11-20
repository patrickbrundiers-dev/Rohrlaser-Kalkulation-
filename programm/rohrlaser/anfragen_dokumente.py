"""Seite „Anfragen“, rechts: Reiter „Dokumente & Mails“ und „Chronik“, Fenster für Kunde zuordnen und Anfragen
zusammenführen (Patrick 19./20.11.2026, Pakete Z1-Z4; Daten in anfragen_sammeln und mail_zuordnung).

Dokumente & Mails: alle Mails und Dokumente der Anfrage nach Kategorie, Mehrfachauswahl, Ablagefläche zum Hineinziehen
(Dateien aus dem Explorer, Mails direkt aus dem klassischen Outlook), Knöpfe Hinzufügen …, Outlook-Auswahl,
Zu anderer Anfrage …, Zusammenführen …, Rückgängig und Kategorie. Doppelklick öffnet die Vorschau."""
import html
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import anfragen_akten as ak
from . import anfragen_sammeln as sa
from . import mail_zuordnung as mz

OUTLOOK_MIME = ("FileGroupDescriptorW", "FileGroupDescriptor", "RenPrivateMessages", "RenPrivateItem")


def ist_outlook_zug(mime):
    """Kommt der Zug aus Outlook (Mails, keine Dateien)?"""
    return not mime.hasUrls() and any(any(k in f for k in OUTLOOK_MIME) for f in mime.formats())


def _datum(iso):
    t = str(iso or "")
    return f"{t[8:10]}.{t[5:7]}.{t[:4]} {t[11:16]}".strip() if len(t) >= 10 else t


class DokumentePanel(QWidget):
    """Reiter „Dokumente & Mails“ der gewählten Anfrage; seite = AnfragenSeite."""

    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        self.ablage_hinweis = QLabel("Dateien oder Mails aus Outlook hierher ziehen, um sie dieser Anfrage hinzuzufügen")
        self.ablage_hinweis.setObjectName("ablageflaeche")
        self.ablage_hinweis.setAlignment(Qt.AlignCenter)
        self.ablage_hinweis.setMinimumHeight(38)
        self.ablage_hinweis.setStyleSheet("QLabel#ablageflaeche { border: 1px dashed #8A94A6; border-radius: 6px;"
                                          " color: #667085; }")
        lay.addWidget(self.ablage_hinweis)
        self.baum = QTreeWidget()
        self.baum.setHeaderLabels(["Dokument", "Rolle", "Von / Herkunft", "Datum", "Größe"])
        self.baum.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.baum.setAlternatingRowColors(True)
        self.baum.itemDoubleClicked.connect(lambda it, _c: self.oeffnen(it))
        self.baum.setColumnWidth(0, 260)
        lay.addWidget(self.baum, 1)
        zeile = QHBoxLayout()
        self.k_hinzu = QPushButton("Hinzufügen …")
        self.k_hinzu.setToolTip("Mails (.msg/.eml) und Dokumente (PDF, Excel, Word, Bilder, STEP) hinzufügen, "
                                "mehrere auf einmal")
        self.k_hinzu.clicked.connect(lambda: self.seite.dokumente_hinzufuegen())
        self.k_outlook = QPushButton("Outlook-Auswahl")
        self.k_outlook.setToolTip("Die im Outlook-Fenster markierten Mails dieser Anfrage hinzufügen")
        self.k_outlook.clicked.connect(lambda: self.seite.outlook_auswahl_hinzufuegen())
        self.k_weg = QPushButton("Zu anderer Anfrage …")
        self.k_weg.setToolTip("Markierte Mails/Dateien einer anderen Anfrage zuweisen (hier bleiben sie als "
                              "„verschoben“ sichtbar)")
        self.k_weg.clicked.connect(lambda: self.seite.dokumente_verschieben())
        self.k_zusammen = QPushButton("Zusammenführen …")
        self.k_zusammen.setToolTip("Weitere Anfragen in diese übernehmen (mit Übersicht vorher, rückgängig machbar)")
        self.k_zusammen.clicked.connect(lambda: self.seite.zusammenfuehren())
        self.k_trennen = QPushButton("Zusammenführung rückgängig")
        self.k_trennen.clicked.connect(lambda: self.seite.trennen())
        self.kategorie = QComboBox()
        self.kategorie.setToolTip("Kategorie der markierten Dokumente ändern")
        self.kategorie.activated.connect(lambda _i: self.seite.kategorie_setzen(self.kategorie.currentData()))
        for b in (self.k_hinzu, self.k_outlook, self.k_weg, self.k_zusammen, self.k_trennen):
            zeile.addWidget(b)
        zeile.addStretch(1)
        zeile.addWidget(QLabel("Kategorie:"))
        zeile.addWidget(self.kategorie)
        lay.addLayout(zeile)

    def gewaehlt(self):
        """Schlüssel der markierten Dokumente."""
        return [it.data(0, Qt.UserRole) for it in self.baum.selectedItems() if it.data(0, Qt.UserRole)]

    def fuellen(self, akte, wurzel):
        self.baum.clear()
        self.kategorie.clear()
        self.kategorie.addItem("– ändern –", None)
        for k in (sa.kategorien(wurzel) if wurzel else sa.KATEGORIEN):
            self.kategorie.addItem(k, k)
        self.kategorie.addItem("Neue Kategorie …", "__neu__")
        da = akte is not None
        for b in (self.k_hinzu, self.k_outlook, self.k_weg, self.k_zusammen, self.kategorie):
            b.setEnabled(da and not getattr(self.seite.db, "nur_lesen", False))
        self.k_trennen.setVisible(da and any(z["aktiv"] for z in akte.stand.get("zusammen", [])))
        if not da:
            return
        rollen = {x["datei"]: x for x in (self.seite.anhaenge(akte) if hasattr(self.seite, "anhaenge") else [])}
        for kat, liste in sa.nach_kategorie(akte, wurzel).items():
            knoten = QTreeWidgetItem([f"{kat} ({len(liste)})"])
            f = knoten.font(0)
            f.setBold(True)
            knoten.setFont(0, f)
            self.baum.addTopLevelItem(knoten)
            for d in liste:
                h = d.get("herkunft") or {}
                von = h.get("von_name") or h.get("von") or ""
                quelle = sa.QUELLE_TEXT.get(h.get("quelle"), "")
                if h.get("akte"):
                    quelle = f"aus {h['akte']}"
                text = " · ".join(x for x in (von, quelle) if x)
                if d.get("aus_mail"):
                    text = f"Anhang von {d['aus_mail']}"
                x = rollen.get(d.get("datei", d["name"]))
                rolle = ""
                if x is not None:       # 20.11.2026 (anhang_analyse): Rolle, Revision, neuer Stand
                    rolle = x["rolle"] + (f" · Rev. {x['revision']}" if x["revision"] else "") \
                        + (" · neuer Stand" if x["neuer_stand_von"] else "") + (" ⚠" if x["hinweise"] else "")
                it = QTreeWidgetItem([d["name"], rolle, text, _datum(h.get("datum") or h.get("zeit")),
                                      f"{(d.get('groesse') or 0) / 1024:.0f} KB"])
                if x is not None and (x["hinweise"] or x["neuer_stand_von"]):
                    it.setToolTip(1, "\n".join(([f"neuer Stand von {x['neuer_stand_von']}"]
                                                 if x["neuer_stand_von"] else []) + x["hinweise"]))
                it.setData(0, Qt.UserRole, d.get("datei", d["name"]))
                it.setToolTip(0, f"{d['id']} · {ak.ART_TEXT.get(d['art'], '')}" + (f"\nBetreff: {h['betreff']}"
                                                                                    if h.get("betreff") else ""))
                knoten.addChild(it)
            knoten.setExpanded(True)
        weg = [d for d in akte.dateien(mit_weg=True) if d.get("weg")]
        if weg:
            knoten = QTreeWidgetItem([f"Verschoben / getrennt ({len(weg)})"])
            self.baum.addTopLevelItem(knoten)
            for d in weg:
                knoten.addChild(QTreeWidgetItem([d["name"], "", f"→ {d['weg']}", "", ""]))

    def oeffnen(self, it):
        schl = it.data(0, Qt.UserRole)
        a = self.seite.akte()
        if not schl or a is None:
            return
        d = next((x for x in a.dateien() if x.get("datei", x["name"]) == schl), None)
        if d is not None and not d.get("gesperrt"):
            self.seite.vorschau(a, d)

    # Ziehen und Ablegen
    def dragEnterEvent(self, e):
        m = e.mimeData()
        if m.hasUrls() or ist_outlook_zug(m):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        self.dragEnterEvent(e)

    def dropEvent(self, e):
        m = e.mimeData()
        if m.hasUrls():
            pfade = [Path(u.toLocalFile()) for u in m.urls() if u.isLocalFile()]
            self.seite.dokumente_hinzufuegen(pfade, quelle="drag")
        elif ist_outlook_zug(m):
            self.seite.outlook_auswahl_hinzufuegen(quelle="drag")
        e.acceptProposedAction()


def dateien_waehlen(parent):
    namen, _ = QFileDialog.getOpenFileNames(
        parent, "Zur Anfrage hinzufügen", "",
        "Mails und Dokumente (*.msg *.eml *.pdf *.xlsx *.xls *.xlsm *.csv *.docx *.doc *.jpg *.jpeg *.png *.tif "
        "*.tiff *.bmp *.step *.stp *.igs *.iges *.dxf *.dwg *.zip *.txt);;Alle Dateien (*.*)")
    return [Path(n) for n in namen]


def chronik_html(akte):
    e = html.escape
    zeilen = []
    for c in sa.chronik(akte):
        farbe = "#2F6FB3" if c["art"] == "mail" else "#555"
        zeilen.append(f"<tr><td style='color:#666'>{e(_datum(c['zeit']))}&nbsp;</td>"
                      f"<td style='color:{farbe}'>{'✉ ' if c['art'] == 'mail' else ''}{e(c['text'])}</td>"
                      f"<td style='color:#888'>&nbsp;{e(c.get('kuerzel', ''))}</td></tr>")
    return "<table>" + "".join(zeilen) + "</table>" if zeilen else "<i>Noch nichts</i>"


# ------------------------------------------------------------------ Herkunft und Kunde
def herkunft_html(akte, kunden_namen=None):
    """Kasten „Herkunft und Kunde“ (über dem Mailtext): Rollen, Stufe, Kriterien, Hinweise, Korrektur-Links."""
    z = akte.zuordnung
    if not z:
        return ""
    e = html.escape
    namen = kunden_namen or {}
    farbe = {"eindeutig": "#2F7D4F", "wahrscheinlich": "#A66A00", "mehrdeutig": "#B42318", "unbekannt": "#B42318"}
    stufe = z.get("stufe") or "unbekannt"
    zeilen = []
    kunde = akte.kunde
    if z.get("ohne_kunde"):
        k = "<b>Intern (ohne Kunde)</b>"
    elif kunde:
        k = f"<b>{e(kunde)} {e(namen.get(kunde) or z.get('kunde_name') or akte.kopf.get('kunde_name') or '')}</b>"
    else:
        k = "<b>kein Kunde gesetzt</b>"
    wer = f" von {e(z['bestaetigt_von'])}" if z.get("bestaetigt_von") else ""
    zeilen.append(f"Kunde: {k} <span style='color:{farbe.get(stufe, '#666')}'>({e(mz.STUFE_TEXT.get(stufe, stufe))}"
                  f"{' von Hand' + wer if not z.get('automatisch', True) or z.get('bestaetigt_von') else ''})</span>")
    if not kunde and not z.get("ohne_kunde"):
        for v in z.get("vorschlaege") or []:
            zeilen.append(f"&nbsp;&nbsp;Vorschlag {e(v['kundennr'])} {e(v['name'])} ({v['punkte']} Punkte: "
                          f"{e('; '.join(v['gruende']))}) · <a href='kunde_ok:{e(v['kundennr'])}'>übernehmen</a>")
    o = z.get("original") or {}
    korr = akte.stand.get("absender_korr")
    if korr:
        zeilen.append(f"Ursprünglicher Absender: {e(korr.get('name') or '')} &lt;{e(korr.get('adresse'))}&gt; "
                      "(korrigiert)")
    elif o.get("adresse"):
        zeilen.append(f"Ursprünglicher Absender: {e(o.get('name') or '')} &lt;{e(o['adresse'])}&gt;"
                      + (" · Sammelpostfach" if z.get("zentral") else ""))
    if z.get("ansprechpartner"):
        zeilen.append(f"Ansprechpartner: {e(z['ansprechpartner'])}")
    if z.get("anfragender_intern"):
        i = z["anfragender_intern"]
        zeilen.append(f"Interne Anfrage von {e(i.get('name') or i.get('adresse') or '')}")
    if z.get("weiterleiter"):
        zeilen.append("Weitergeleitet von " + " ← ".join(
            e(w.get("name") or w.get("adresse") or "?") + (f" ({_datum(w['datum'])})" if w.get("datum") else "")
            for w in z["weiterleiter"]))
    if z.get("postfach"):
        zeilen.append(f"Eingegangen über {e(z['postfach'])}")
    if z.get("zustaendig"):
        zeilen.append(f"Zuständig: {e(z['zustaendig'])}")
    for h in z.get("hinweise") or []:
        zeilen.append(f"<span style='color:#A66A00'>{e(h)}</span>")
    if z.get("kriterien"):
        zeilen.append(f"<span style='color:#666'>Erkannt über: {e('; '.join(z['kriterien']))}</span>")
    zeilen.append("<a href='kunde_wahl:'>Kunde ändern …</a> · <a href='kunde_neu:'>Neuen Kunden anlegen …</a> · "
                  "<a href='ansprechpartner:'>Ansprechpartner …</a> · <a href='absender:'>Absender korrigieren …</a> · "
                  "<a href='ohne_kunde:'>Intern (ohne Kunde)</a> · <a href='angebot_hand:'>Angebot verknüpfen …</a> · "
                  "<a href='zuruecksetzen:'>Zurücksetzen</a>")
    rand = farbe.get("eindeutig" if kunde or z.get("ohne_kunde") else stufe, "#666")
    return (f"<div style='border-left:3px solid {rand}; padding-left:6px; margin-bottom:6px'><b>Herkunft und Kunde"
            "</b><br>" + "<br>".join(zeilen) + "</div>")


class KundeDialog(QDialog):
    """Kunde wählen, mit „Als Regel merken“ (Adresse bzw. Domain → Kunde)."""

    def __init__(self, parent, kunden, akte):
        super().__init__(parent)
        self.setWindowTitle(f"Kunde zuordnen – {akte.nr}")
        lay = QVBoxLayout(self)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Kunde suchen: Name, Nummer, E-Mail …")
        lay.addWidget(self.suche)
        self.liste = QListWidget()
        lay.addWidget(self.liste, 1)
        self.kunden = list(kunden)
        vorschlag = [v["kundennr"] for v in akte.zuordnung.get("vorschlaege") or []]
        self.kunden.sort(key=lambda k: (str(k.get("kundennr")) not in vorschlag, str(k.get("name") or "")))
        self.suche.textChanged.connect(self._fuellen)
        adresse = akte.absender_adresse
        self.regel = QCheckBox(f"Als Regel merken: {adresse} gehört immer zu diesem Kunden" if adresse else
                               "Als Regel merken")
        self.regel.setEnabled(bool(adresse))
        self.regel.setToolTip("Gilt für neue Mails; die Regel steht im Fenster „Outlook …“ und lässt sich löschen")
        lay.addWidget(self.regel)
        self.domain = QCheckBox(f"… auch für alle Adressen @{mz.mail._domain(adresse)}" if adresse else "")
        self.domain.setVisible(bool(adresse) and mz.mail._domain(adresse) not in mz.mail.FREEMAIL)
        lay.addWidget(self.domain)
        self.grund = QLineEdit()
        self.grund.setPlaceholderText("Grund (für das Protokoll, freiwillig)")
        lay.addWidget(self.grund)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        lay.addWidget(k)
        self.resize(520, 480)
        self._fuellen("")

    def _fuellen(self, text):
        self.liste.clear()
        t = text.lower().strip()
        for k in self.kunden:
            s = f"{k.get('kundennr')} – {k.get('name') or ''}  {k.get('email') or ''}"
            if t and t not in s.lower():
                continue
            it = QListWidgetItem(s)
            it.setData(Qt.UserRole, str(k.get("kundennr")))
            self.liste.addItem(it)
        if self.liste.count():
            self.liste.setCurrentRow(0)

    def wahl(self):
        it = self.liste.currentItem()
        return it.data(Qt.UserRole) if it else None


class ZusammenDialog(QDialog):
    """Weitere Anfragen wählen (Vorschläge vorab markiert) und die Übersicht bestätigen."""

    def __init__(self, parent, haupt, akten, vorschlaege):
        super().__init__(parent)
        self.haupt = haupt
        self.akten = {a.nr: a for a in akten}
        self.setWindowTitle(f"Anfragen zusammenführen in {haupt.nr}")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Diese Anfragen in <b>{html.escape(haupt.nr)}</b> „{html.escape(haupt.betreff)}“ "
                             "übernehmen:"))
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Weitere Anfrage suchen: Nummer, Kunde, Betreff …")
        lay.addWidget(self.suche)
        self.liste = QListWidget()
        lay.addWidget(self.liste, 1)
        self.vorschau = QTextBrowser()
        lay.addWidget(self.vorschau, 1)
        self.vor = {a.nr: g for a, g in vorschlaege}
        self.suche.textChanged.connect(self._fuellen)
        self.liste.itemChanged.connect(lambda _it: self._vorschau())
        k = QDialogButtonBox(QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        self.ok = k.addButton("Zusammenführen", QDialogButtonBox.AcceptRole)
        self.ok.setObjectName("primaer")
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        lay.addWidget(k)
        self.resize(760, 640)
        self._fuellen("")

    def _fuellen(self, text):
        alt = set(self.gewaehlt())
        self.liste.blockSignals(True)
        self.liste.clear()
        t = text.lower().strip()
        kandidaten = sorted((a for a in self.akten.values() if a.nr != self.haupt.nr
                             and not a.stand.get("zusammengefuehrt_in")),
                            key=lambda a: (a.nr not in self.vor, -(a.eingang.timestamp() if a.eingang else 0)))
        for a in kandidaten[:300]:
            s = f"{a.nr} · {a.absender or a.kunde} · {a.betreff}" + (f"   ← {self.vor[a.nr]}" if a.nr in self.vor
                                                                     else "")
            if t and t not in (s + " " + a.suchtext()).lower():
                continue
            it = QListWidgetItem(s)
            it.setData(Qt.UserRole, a.nr)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if a.nr in alt or (not alt and a.nr in self.vor and len(self.vor) == 1)
                             else Qt.Unchecked)
            self.liste.addItem(it)
        self.liste.blockSignals(False)
        self._vorschau()

    def gewaehlt(self):
        return [self.liste.item(i).data(Qt.UserRole) for i in range(self.liste.count())
                if self.liste.item(i).checkState() == Qt.Checked] if hasattr(self, "liste") else []

    def _vorschau(self):
        nr = self.gewaehlt()
        self.ok.setEnabled(bool(nr))
        self.vorschau.setHtml(vorschau_html(sa.vorschau(self.haupt, [self.akten[n] for n in nr])) if nr else
                              "<i>Bitte die Anfragen wählen, die übernommen werden.</i>")


def _anz(n, eins, mehr):
    return f"{n} {eins if n == 1 else mehr}"


def vorschau_html(v):
    e = html.escape
    t = [f"<p><b>Übernommen werden:</b> {_anz(len(v['mails']), 'Mail', 'Mails')}, "
         f"{_anz(len(v['dateien']), 'Datei', 'Dateien')}"
         + (f"; {_anz(len(v['doppelt']), 'Datei ist', 'Dateien sind')} schon vorhanden "
            "(wird nicht doppelt gespeichert)"
            if v["doppelt"] else "") + "</p>"]
    for w in v["warnungen"]:
        t.append(f"<p style='color:#B42318'>{e(w)}</p>")
    if v["mails"]:
        t.append("<p><b>Mails</b></p><ul>" + "".join(f"<li>{e(nr)}: {e(von)} {e(_datum(d))} – {e(b)}</li>"
                                                     for nr, von, d, b in v["mails"]) + "</ul>")
    if v["dateien"]:
        t.append("<p><b>Dateien</b></p><ul>" + "".join(f"<li>{e(nr)}: {e(n)} <span style='color:#666'>({e(k)})"
                                                       "</span></li>" for nr, n, k in v["dateien"]) + "</ul>")
    if v["doppelt"]:
        t.append("<p><b>Doppelt (nur einmal)</b></p><ul>" + "".join(
            f"<li>{e(nr)}: {e(n)} = {e(da)}</li>" for nr, n, da in v["doppelt"]) + "</ul>")
    if v["angebote"]:
        t.append(f"<p>Angebote danach in der Anfrage: {e(', '.join(v['angebote']))}</p>")
    t.append("<p style='color:#666'>Die übernommenen Anfragen bleiben lesbar („Zusammengeführt in …“). "
             "Rückgängig jederzeit über „Zusammenführung rückgängig“.</p>")
    return "".join(t)


class AnfrageWahlDialog(QDialog):
    """Ziel-Anfrage für „Zu anderer Anfrage …“ wählen."""

    def __init__(self, parent, akten, ohne, text):
        super().__init__(parent)
        self.setWindowTitle("Zu anderer Anfrage")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(text))
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Anfrage suchen: Nummer, Kunde, Betreff …")
        lay.addWidget(self.suche)
        self.liste = QListWidget()
        lay.addWidget(self.liste, 1)
        self.akten = [a for a in akten if a.nr != ohne and not a.stand.get("zusammengefuehrt_in")]
        self.akten.sort(key=lambda a: (a.status == ak.ERLEDIGT, -(a.eingang.timestamp() if a.eingang else 0)))
        self.suche.textChanged.connect(self._fuellen)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        lay.addWidget(k)
        self.resize(620, 480)
        self._fuellen("")

    def _fuellen(self, text):
        self.liste.clear()
        t = text.lower().strip()
        for a in self.akten[:500]:
            s = f"{a.nr} · {ak.STATUS_TEXT[a.status]} · {a.absender or a.kunde} · {a.betreff}"
            if t and t not in (s + " " + a.suchtext()).lower():
                continue
            it = QListWidgetItem(s)
            it.setData(Qt.UserRole, a.nr)
            self.liste.addItem(it)
        if self.liste.count():
            self.liste.setCurrentRow(0)

    def wahl(self):
        it = self.liste.currentItem()
        return it.data(Qt.UserRole) if it else None


def regeln_html(regeln):
    if not regeln:
        return "<i>Noch keine Regeln. Sie entstehen beim Korrigieren eines Kunden mit „Als Regel merken“.</i>"
    return "<br>".join(f"{html.escape(mz.regel_text(r))} · <a href='regel_weg:{html.escape(r['id'])}'>löschen</a>"
                       for r in regeln)


def zwischenordner():
    return Path(tempfile.mkdtemp(prefix="rohrlaser_outlook_"))


class ArtDialog(QDialog):
    """Mail-Art und Sachgebiete einer Anfrage von Hand setzen (20.11.2026, anfrage_art)."""

    def __init__(self, eltern, art, sachgebiete=()):
        from . import anfrage_art as aa
        super().__init__(eltern)
        self.setWindowTitle("Mail-Art ändern")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Was für eine Mail ist das?"))
        self.art = QComboBox()
        for schl, titel in aa.ARTEN.items():
            self.art.addItem(titel, schl)
        self.art.setCurrentIndex(max(0, self.art.findData(art)))
        lay.addWidget(self.art)
        lay.addWidget(QLabel("Sachgebiet (mehrere möglich):"))
        self.sg = {}
        for schl, titel in aa.SACHGEBIETE.items():
            c = QCheckBox(titel)
            c.setChecked(schl in (sachgebiete or ()))
            self.sg[schl] = c
            lay.addWidget(c)
        lay.addWidget(QLabel("<span style='color:#666'>Die Korrektur steht im Verlauf und hilft der Erkennung beim "
                             "Lernen.</span>"))
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        k.accepted.connect(self.accept)
        k.rejected.connect(self.reject)
        lay.addWidget(k)

    def werte(self):
        return self.art.currentData(), [s for s, c in self.sg.items() if c.isChecked()]
