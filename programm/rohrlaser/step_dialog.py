"""Dialoge mit 3D-Ansicht: Prüfen der STEP-Messung vor dem Übernehmen und Ansehen der Positionen eines Angebots."""
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QLineEdit, QSizePolicy,
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from . import einblendung, step_pruefung, stil
from . import hilfe
from .ansicht3d import ARTEN, TEILFARBEN, Ansicht3DMitKnoepfen
from .fenster import liste_fuellen
from .stammdaten import zahl_als_text
from .eingabe import RechenSpinGanz

FARBE_FEHLT = next(f for a, _, f, _ in ARTEN if a == "N")     # nicht übernehmbare Teile in der 3D-Ansicht


def grund(m):
    """Warum ein Teil nicht übernommen werden kann, mit Hüllmaß (zum Wiederfinden in der STEP-Datei)."""
    from . import step
    text = m.get("fehler") or (step.blech_text(m) + ": Blech, kein Rohrlaserteil" if step.blech(m) else "") \
        or m.get("hinweise") or "kein Rohrteil erkannt"
    try:
        masse = sorted((float(x) for x in (m.get("huelle") or "").split("|") if x), reverse=True)
    except ValueError:
        masse = []
    if len(masse) == 3 and masse[0] > 0:
        text += " – Hüllmaß " + " × ".join(zahl_als_text(x, 0) for x in masse) + " mm"
    return text


def hat_huelle(m):
    return len([x for x in (m.get("huelle") or "").split("|") if x]) == 3


def _f(m, name):
    try:
        return float(m.get(name) or 0)
    except ValueError:
        return 0.0


def _messinfo(m):
    from . import step
    if m.get("fehler"):
        return f"<b style='color:#B42318'>FEHLER: {m['fehler']}</b>"
    z = lambda name, st=1: zahl_als_text(_f(m, name), st)
    status = m.get("pruefstatus") or ""
    farbe = {"plausibel": "#1E6B34", "prüfen": "#7A5A00", "nicht messbar": "#B42318"}.get(status, "#000000")
    unsicher = step.unsicher(m)
    b = step.blech(m)
    if b is not None:
        bo = ", ".join(f"{n}× Ø{zahl_als_text(float(d), 1)}" for d, n in (b.get("bohrungen") or {}).items())
        return (f"<b>{m.get('artikel')}</b>: {step.blech_text(m)}, Kontur {b.get('kontur') or ''}, "
                f"{b.get('innen') or 0} Innenkonturen" + (f" (Bohrungen {bo})" if bo else "")
                + (f" · {m['hinweise']}" if m.get("hinweise") else "")
                + (f"<br><b style='color:{farbe}'>Prüfstatus: {status}</b>" if status else ""))
    traeger = (f"Steg {z('stegdicke')} mm, Flansch {z('flanschdicke')} mm"
               + ("" if m.get("symmetrisch") != "0" else ", unsymmetrisch") + ", "
               if _f(m, "stegdicke") > 0 else "")
    norm = f"Normprofil {m['normprofil']}, " if m.get("normprofil") else ""
    anbau = step.anbau_text(m)
    return (f"<b>{m.get('artikel')}</b>: {m.get('profilform')} {m.get('profil_id_vorschlag') or ''}, {norm}{traeger}"
            f"Länge {z('laenge')} mm, "
            f"Schneidweg {z('schneidweg')} mm (Anfangsschnitt {z('ende_a')}, Endschnitt {z('ende_b')}, Innenkonturen "
            f"{z('innen')} mm in {m.get('innen_konturen') or 0} Konturen), Gravur {z('gravur')} mm, Einstiche "
            f"{m.get('konturen') or 0}" + (f"<br>{anbau}" if anbau else "")
            + (f" · {m['hinweise']}" if m.get("hinweise") else "")
            + (f"<br><b style='color:{farbe}'>Prüfstatus: {status}</b>" if status else "")
            + (f" · unsicher: {', '.join(unsicher)} (erst nach Anhaken übernommen)" if unsicher else "")
            + "<br>" + step_pruefung.html(step_pruefung.merkmale(m, step.gewinde_vorschlag(m.get("bohrungen"),
                                                                                           step.KERNLOCH))))


class _Mit3D(QDialog):
    def __init__(self, parent, titel, spalten):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.resize(1250, 680)
        self.liste = QTableWidget(0, len(spalten))
        self.liste.setHorizontalHeaderLabels(spalten)
        self.liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.liste.setSelectionMode(QAbstractItemView.SingleSelection)
        self.liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.liste.verticalHeader().setDefaultSectionSize(22)
        self.liste.currentCellChanged.connect(lambda r, *_: self._zeigen(r))
        self.ansicht = Ansicht3DMitKnoepfen()
        teil = QSplitter(Qt.Horizontal)
        teil.addWidget(self.liste)
        teil.addWidget(self.ansicht)
        teil.setSizes([520, 730])
        self.lay = QVBoxLayout(self)
        self.lay.addWidget(teil, 1)

    def _fuellen(self, zeilen):
        self.liste.setRowCount(len(zeilen))
        for r, werte in enumerate(zeilen):
            for c, w in enumerate(werte):
                it = QTableWidgetItem("" if w is None else str(w))
                if isinstance(w, (int, float)):
                    it.setText(zahl_als_text(w, 1 if isinstance(w, float) else 0))
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.liste.setItem(r, c, it)
        self.liste.resizeColumnsToContents()


class _Zeile:
    """Eine Zeile der Rohrliste: gleiche Teile einer Datei. werte = Stückzahl je Modus ('einzeln' bzw. 'satz' =
    Stück je Satz); der Spin zeigt den Wert des Modus der Datei."""

    def __init__(self, it, liste, pr, ws, sp, vorschlag, datei, stueck, je_satz, blech=False):
        self.it, self.liste, self.pr, self.ws, self.sp, self.vorschlag, self.datei = it, liste, pr, ws, sp, vorschlag, datei
        self.werte = {"einzeln": stueck or 0, "satz": je_satz}
        self.blech = blech      # Blech, Vollmaterial: pr = Wahl des Zukaufartikels (Artikel-ID, None = automatisch)


class StepPruefDialog(QDialog):
    """Gemessene Rohre je STEP-Datei und Profil mit 3D-Ansicht. Oben Pfeile zum Wechseln der Datei und bei Dateien
    mit mehreren Teilen (Baugruppe) das Feld 'Anzahl' und den Knopf 'Als Satz' (Vorgabe Einzelpositionen; Anzahl
    erhöht nur die Stückzahl, ein Satz entsteht nur mit dem Knopf); ihre Teile stehen
    unter einem Knoten 'Baugruppe'. Je Teil übernehmen ja/nein, Profil, Werkstoff
    und Stückzahl (bei einem Satz: Stück je Satz); gleiche Teile einer Datei stehen in einer Zeile (Spalte
    'In Datei'). OK schreibt die Werte als _uebernehmen, _profil, _werkstoff, _stueck, _saetze, _je_satz in die
    Messwerte (step.uebernehmen liest sie).
    Mit zukauf_liste stehen Bleche je Datei in der Gruppe 'Bleche (Zukaufteile)': statt des Profils wird der
    Zukaufartikel gewählt (automatisch = vorhandene Dublette oder neu anlegen; _blech_artikel), der Werkstoff ist
    leer (offen), bis er gewählt wird, und Bleche mit Prüfstatus 'prüfen' sind erst nach Anhaken gewählt."""
    BLECHGRUPPE = "Bleche (Zukaufteile, nicht lasern)"
    VOLLGRUPPE = "Vollmaterial (Zukaufteile, gesägt)"
    AUTOMATISCH = "automatisch (vorhandenen Artikel nutzen oder neu anlegen)"
    # Hinweis gleich hinter dem Teil (Plan Angebotsablauf V2: bei 1366 px sichtbar, ganzer Text im Tooltip)
    SPALTEN = ("Teil", "In Datei", "Hinweis", "Art", "Profil-ID bzw. Zukaufartikel", "Werkstoff-ID", "Stückzahl",
               "Zusatzarbeiten", "Länge [mm]", "Schneidweg [mm]", "Konturen", "Anbauteile")
    (SP_HINWEIS, SP_ART, SP_PROFIL, SP_WERKSTOFF, SP_STUECK, SP_ZUSATZ, SP_LAENGE, SP_SCHNEIDWEG, SP_KONTUREN,
     SP_ANBAU) = range(2, 12)

    def __init__(self, parent, messwerte, k, werkstoff=None, stueck=None, zukauf_liste=None, blech_werkstoffe=None,
                 knick_vorgaben=None, step_kopieren=None, maschine_3d=False, kunden=None, kundennr=None,
                 kunde_gewechselt=None, vorpruefung=None, lernen=False, maschine=None, zusatzarbeiten=None,
                 zusatz_vorgabe=None, referenz=None, hinweis=None):
        """Plan Bedienung B1 (alles in diesem Fenster): kunden = Kundenzeilen für die Auswahl oben (neues Angebot aus
        STEP; None = ohne Auswahl), kundennr = Vorschlag; kunde_gewechselt(kundennr) wendet das Importprofil des
        neuen Kunden auf die Messwerte an und liefert dessen Werkstoff-Vorgabe; vorpruefung() = (fehlende Profile,
        Anzahl schon vorhandener Artikel) wie step.vorpruefung – statt zweier Rückfragen nach dem Übernehmen stehen
        sie als Häkchen unter der Liste. lernen (B8): Korrekturen (Werkstoff aller Rohre, abgewählte Teile,
        Anbauteile) per Häkchen als Importprofil des Kunden merken; Ergebnis nach OK in self.lernen_werte.
        Plan Angebotsablauf: alle Dateien stehen in einer Liste (◀ ▶ springen zur nächsten Datei, V1), das Fenster passt
        in 1366 px (V2); zusatzarbeiten = Namen der Zusatzarbeiten für „Werte setzen“ (V4, zusatz_vorgabe = aus dem
        Importprofil für alle Teile vorbelegt); referenz = Vorschlag der Anfrage-Nr. des Kunden (V5, None = kein Feld),
        Ergebnis in self.referenz_text(). hinweis = Zeilen, die aus der E-Mail der Anfrage übernommen wurden (Kunde,
        Lieferzeit, Werkstoff), stehen unter dem Kunden zum Prüfen."""
        from . import step
        super().__init__(parent)
        self.kundennr, self.kunde_gewechselt, self.vorpruefung = kundennr, kunde_gewechselt, vorpruefung
        self.pdf_danach = False         # Knopf „Übernehmen und Angebot (PDF)“
        self.lernen, self.lernen_werte = lernen, None
        self.messwerte, self.k = messwerte, k
        self.knick_vorgaben = knick_vorgaben or {}      # Einstellungen knick_z, knick_freistich, knick_k
        step.offene_rohre_vorbelegen(messwerte, k.profile, maschine)    # offenes Rohr: immer Rohr, außer zu groß
        from . import knickverbindung
        for m in messwerte:     # Knickrahmen aus einem Körper (K1-3), geknickt oder gestreckt gezeichnet
            if m.get("profilform") in ("Quadratrohr", "Rechteckrohr") and m.get("_knick_von") is None:
                knickverbindung.koerper_vorbereiten(m, self.knick_vorgaben)
        if zukauf_liste is not None:        # mit Blechen: Profil/Kantteil nach den Stammdaten vorbelegen
            step.kantteile_vorbelegen(messwerte, k.profile)
        self.blech_werkstoffe = blech_werkstoffe or {}      # {ID: Zeile blech_werkstoffe} für die Blechzeilen
        self.werkstoff, self.stueck, self.zukauf_liste = werkstoff, stueck, zukauf_liste
        mit_blechen = zukauf_liste is not None
        self.setWindowTitle(f"STEP-Import prüfen ({len(messwerte)} Teil{'e' if len(messwerte) != 1 else ''})")
        self.resize(1350, 720)
        self.dateien = list(dict.fromkeys(m.get("datei") for m in messwerte))
        self.mehrteilig = step.mehrteilig(messwerte, mit_blechen)
        # eigene Körper, die an ein Rohr geschweißt sind: standardmäßig nicht übernehmen (nur Gravur auf dem Rohr)
        self.anbau_von = step.anbau_von(messwerte)
        self.anbau_weglassen = all(m.get("_anbau_weglassen", True) for m in messwerte)
        # Datei -> Sätze (0 = leer = Einzelpositionen); auch Baugruppen sind leer vorbelegt, ein Satz nur auf Wunsch
        self.saetze = {d: 0 for d in self.dateien}
        for m in messwerte:
            if "_saetze" in m and m.get("datei") in self.mehrteilig:
                self.saetze[m["datei"]] = int(m["_saetze"] or 0)
        # Datei -> Anzahl oben (Einzelpositionen: Stückzahl aller Teile; Satz: Anzahl Sätze)
        self.anzahl = {d: self.saetze[d] or 1 for d in self.dateien}
        self.datei_nr = 0
        self.zusatz_vorgabe = list(zusatz_vorgabe or ())     # aus dem Importprofil (step_importieren belegt vor)

        # Kopf (V2: untereinander, damit das Fenster in 1366 px passt): Kunde und Anfrage-Nr., Datei wechseln, Sätze
        self.kopf = QWidget()
        kopf_lay = QVBoxLayout(self.kopf)
        kopf_lay.setContentsMargins(0, 0, 0, 0)
        kopf_lay.setSpacing(4)
        kunde_zeile, datei_zeile = QHBoxLayout(), QHBoxLayout()
        kopf_lay.addLayout(kunde_zeile)
        kopf_lay.addLayout(datei_zeile)
        kl = datei_zeile
        self.zurueck, self.vor = QPushButton("◀"), QPushButton("▶")
        for b, schritt, tipp in ((self.zurueck, -1, "Vorige STEP-Datei"), (self.vor, 1, "Nächste STEP-Datei")):
            b.setFixedWidth(36)
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, s=schritt: self.datei_waehlen(self.datei_nr + s))
        self.datei_text = QLabel()
        f = self.datei_text.font()
        f.setBold(True)
        self.datei_text.setFont(f)
        self.datei_text.setMinimumWidth(80)         # lange Dateinamen machen das Fenster nicht breiter (V2)
        self.datei_text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.satz_feld = QWidget()
        sl = QHBoxLayout(self.satz_feld)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(QLabel("Anzahl:"))
        self.satz_spin = RechenSpinGanz()
        self.satz_spin.setRange(1, 100000)
        self.satz_spin.setToolTip("Anzahl dieser Baugruppe. Ohne Satz: Stückzahl jedes Teils (Einzelpositionen). "
                                  "Mit „Als Satz“: Anzahl Sätze.")
        self.satz_spin.valueChanged.connect(lambda n: self.anzahl_setzen(n))
        sl.addWidget(self.satz_spin)
        self.satz_knopf = QPushButton("Als Satz")
        self.satz_knopf.setCheckable(True)
        self.satz_knopf.setToolTip("Die Teile dieser Datei als Satz anlegen (Satzname = Dateiname, gleiche Teile eine "
                                   "Position mit Stück je Satz). Nicht gedrückt = jedes Teil eine Einzelposition.")
        self.satz_knopf.toggled.connect(lambda an: self.als_satz_setzen(an))
        sl.addWidget(self.satz_knopf)
        # Schweißbaugruppe: Satz als Position der Art Schweißbaugruppe mit den Unterbaugruppen der STEP-Struktur
        self.baugruppe = {d: any(m.get("_baugruppe") for m in messwerte if m.get("datei") == d) for d in self.dateien}
        self.bg_haken = QCheckBox("als Schweißbaugruppe")
        self.bg_haken.setToolTip("Den Satz als Schweißbaugruppe anlegen: Unterbaugruppen mit Menge aus der STEP-Datei, "
                                 "Einzelteile zugeordnet. Nahtgruppen und Arbeitsgänge danach im Editor ergänzen.")
        self.bg_haken.toggled.connect(lambda an: self.baugruppe.__setitem__(self.datei, bool(an)) or
                                      self.ziel_wahl.setEnabled(bool(an)))
        sl.addSpacing(12)
        sl.addWidget(self.bg_haken)
        # P8: Datei als Unterbaugruppe in die Schweißbaugruppe einer anderen Datei dieses Imports einhängen
        self.bg_ziel = {}
        self.ziel_wahl = QComboBox()
        self.ziel_wahl.setToolTip("Mehrere STEP-Dateien als eine Baugruppe: diese Datei als Unterbaugruppe in die "
                                  "Schweißbaugruppe einer anderen Datei einhängen. 'Anzahl' gilt dann als Stück je "
                                  "übergeordneter Baugruppe.")
        self.ziel_wahl.currentIndexChanged.connect(lambda i: self._ziel_setzen(self.ziel_wahl.itemData(i)))
        sl.addWidget(self.ziel_wahl)
        self.satz_info = QLabel()
        self.kunde_wahl = None
        if kunden is not None:          # B1: Kunde direkt hier wählen (Vorschlag aus Ordnername/letztem Angebot)
            from .step_neu import OHNE_KUNDE
            self.kunde_wahl = QComboBox()
            self.kunde_wahl.setEditable(True)           # Tippen sucht (Nummer oder Name)
            self.kunde_wahl.setInsertPolicy(QComboBox.NoInsert)
            self.kunde_wahl.completer().setFilterMode(Qt.MatchContains)
            self.kunde_wahl.completer().setCompletionMode(self.kunde_wahl.completer().CompletionMode.PopupCompletion)
            self.kunde_wahl.setMinimumWidth(260)
            self.kunde_wahl.setToolTip("Kunde des neuen Angebots. Vorschlag aus dem Ordnernamen der STEP-Dateien bzw. "
                                       "dem letzten Angebot mit Importprofil; ein Wechsel wendet das Importprofil des "
                                       "Kunden an.")
            self.kunde_wahl.addItem(OHNE_KUNDE, "")
            for kd in sorted(kunden, key=lambda z: str(z.get("name") or "").lower()):
                self.kunde_wahl.addItem(f"{kd['kundennr']} – {kd.get('name') or ''}", str(kd["kundennr"]))
            i = self.kunde_wahl.findData(str(kundennr or ""))
            self.kunde_wahl.setCurrentIndex(max(i, 0))
            self.kunde_wahl.currentIndexChanged.connect(lambda _i: self._kunde_setzen())
            kunde_zeile.addWidget(QLabel("Kunde:"))
            kunde_zeile.addWidget(self.kunde_wahl)
            kunde_zeile.addSpacing(18)
        self.referenz = None
        if referenz is not None:        # V5: Anfrage-Nr. des Kunden gleich hier (Vorschlag aus Ordnername/Formular)
            self.referenz = QLineEdit(str(referenz or ""))
            self.referenz.setPlaceholderText("z. B. Anfrage-Nr. des Kunden")
            self.referenz.setToolTip("Kundenreferenz des Angebots (Anfrage-Nr. des Kunden), steht im Angebots-PDF. "
                                     "Vorschlag aus dem Ordnernamen der STEP-Dateien (z. B. „Anfrage 4711“) bzw. dem "
                                     "Anfrageformular.")
            self.referenz.setMaximumWidth(220)
            kunde_zeile.addWidget(QLabel("Anfrage-Nr.:"))
            kunde_zeile.addWidget(self.referenz)
        kunde_zeile.addStretch(1)
        self.mail_hinweis = None
        if hinweis:                     # E-Mail der Anfrage (28.10.2026): was vorbelegt wurde
            self.mail_hinweis = QLabel("✉ Aus der E-Mail: " + " · ".join(hinweis))
            self.mail_hinweis.setWordWrap(True)
            self.mail_hinweis.setStyleSheet("color: #595959;")
            self.mail_hinweis.setToolTip("Vorschläge aus der E-Mail im Anfrage-Ordner. Kunde, Werkstoff und Stückzahlen "
                                         "hier prüfen; Lieferzeit und Bemerkung stehen danach im Angebotskopf.")
            kopf_lay.insertWidget(1, self.mail_hinweis)
        self.dateien_info = QLabel()
        self.dateien_info.setStyleSheet("color: #595959;")
        kl.addWidget(self.zurueck)
        kl.addWidget(self.vor)
        kl.addSpacing(6)
        kl.addWidget(self.datei_text, 1)
        kl.addWidget(self.dateien_info)
        satz_zeile = QHBoxLayout()      # Baugruppe: Anzahl, Als Satz, Schweißbaugruppe in eigener Zeile
        satz_zeile.addWidget(self.satz_feld)
        satz_zeile.addWidget(self.satz_info)
        satz_zeile.addStretch(1)
        kopf_lay.addLayout(satz_zeile)

        self.baum = QTreeWidget()
        self.baum.setColumnCount(len(self.SPALTEN))
        self.baum.setHeaderLabels(self.SPALTEN)
        self.baum.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.baum.setUniformRowHeights(True)
        self.baum.setStyleSheet("QTreeView::item { min-height: 26px; }")     # Platz für Auswahlfelder
        self.baum.currentItemChanged.connect(lambda it, *_: self._zeigen(it))
        self.baum.currentItemChanged.connect(lambda it, *_: self._markiert_datei(it))
        self.baum.itemDoubleClicked.connect(self._doppelklick)
        self.baum.setContextMenuPolicy(Qt.CustomContextMenu)
        self.baum.customContextMenuRequested.connect(self._kontextmenue)
        self._baum_fuellen()
        for c, b in enumerate((220, 50, 150, 130, 120, 110, 70, 120, 80, 95, 65, 130)):
            self.baum.setColumnWidth(c, b)

        # Werte für mehrere Teile auf einmal (zwei Zeilen, V2): Werkstoff, Stückzahl, Zusatzarbeit (V4)
        self.leiste = QWidget()
        leiste_lay = QVBoxLayout(self.leiste)
        leiste_lay.setContentsMargins(0, 0, 0, 0)
        leiste_lay.setSpacing(4)
        alle = QHBoxLayout()
        leiste_lay.addLayout(alle)
        alle.addWidget(QLabel("Werte setzen:"))
        self.alle_ws = QComboBox()
        liste_fuellen(self.alle_ws, k, "werkstoff", "(Werkstoff)")
        self.alle_stk = RechenSpinGanz()
        self.alle_stk.setRange(0, 100000)
        self.alle_stk.setSpecialValueText("(Stückzahl)")
        alle.addWidget(self.alle_ws)
        alle.addWidget(self.alle_stk)
        self.alle_zusatz = QComboBox()
        self.alle_zusatz.addItem("(Zusatzarbeit)", None)
        for n in zusatzarbeiten or ():
            self.alle_zusatz.addItem(f"+ {n}", n)
        self.alle_zusatz.setToolTip("Zusatzarbeit (z. B. Feuerverzinken) mit „Für markierte“ bzw. „Für alle“ an die "
                                    "Teile hängen; sie kommt beim Übernehmen in jede Position (Preis aus den "
                                    "Stammdaten). Die Spalte Zusatzarbeiten zeigt die Wahl, Rechtsklick entfernt sie.")
        self.alle_zusatz.setVisible(bool(zusatzarbeiten))
        alle.addWidget(self.alle_zusatz)
        alle.addStretch(1)
        alle = QHBoxLayout()
        leiste_lay.addLayout(alle)
        for text, nur, tipp in (("Für markierte", True, "Markierte Zeilen dieser Datei"),
                                ("Für alle", False, "Alle Teile aller STEP-Dateien")):
            b = QPushButton(text)
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, nur=nur: self.alle_setzen(nur_markierte=nur))
            alle.addWidget(b)
        alle.addSpacing(12)
        for text, an in (("Alle wählen", True), ("Keine wählen", False)):
            b = QPushButton(text)
            b.setToolTip("Alle Teile aller STEP-Dateien")
            b.clicked.connect(lambda _=False, an=an: self.alle_waehlen(an))
            alle.addWidget(b)
        alle.addStretch(1)
        # 3D-Schnittbearbeitung (nur wenn ausgewählt): Gehrungen und schräge Bohrungen aller Teile in 3D
        zeile_3d = QHBoxLayout()
        self.d3 = QCheckBox("3D-Schnittbearbeitung aktivieren")
        gehr = bohr = 0
        for m in messwerte:
            g_, b_ = step.kandidaten_3d(m)
            gehr, bohr = gehr + g_, bohr + b_
        # Vorgabe an, wenn die Maschine des Angebots 3D kann und Schnitte nicht senkrecht stehen (Patrick 24.10.2026)
        self.d3.setChecked(any(m.get("_d3") for m in messwerte) if any("_d3" in m for m in messwerte)
                           else bool(maschine_3d and (gehr or bohr)))
        self.d3.setToolTip("3D = Schnittfläche nicht senkrecht (90°) zur Rohroberfläche (gemessen, ab 0,5°). "
                           "Gehrungen an den Enden und schräge Bohrungen aller Teile, die das sind, mit geschwenktem "
                           "Laserkopf (3D) rechnen; Gehrungen, die überall senkrecht zur Wand stehen, bleiben 2D. Aus = 2D wie bisher; Teile mit schrägen Bohrungen bekommen dann den "
                           "Hinweis „3D prüfen“. Teile ohne solche Schnitte bleiben 2D. Vorgabe: an, wenn die "
                           "Maschine des Angebots 3D kann. Korrektur je Teil im Rohr-Editor (Schneidweg berechnen …).")
        self.d3_info = QLabel(f"nicht senkrecht zur Oberfläche: {gehr} Gehrung{'en' if gehr != 1 else ''} an "
                              f"Enden, {bohr} schräge Bohrung{'en' if bohr != 1 else ''}" + (" – 3D prüfen" if bohr else ""))
        self.d3_info.setStyleSheet("color: #7A5A00;" if bohr else "color: #595959;")
        zeile_3d.addWidget(self.d3)
        zeile_3d.addWidget(self.d3_info, 1)
        self.anbau_weg = QCheckBox("Anbauteile nicht ins Angebot übernehmen")
        self.anbau_weg.setChecked(self.anbau_weglassen)
        self.anbau_weg.setToolTip("Eigene Körper (Bleche, Bolzen …), die an ein Rohr geschweißt sind, werden nicht "
                                  "als Positionen übernommen; das Rohr bekommt nur ihre Gravur. Aus = sie werden wie "
                                  "andere Teile übernommen.")
        self.anbau_weg.setVisible(bool(self.anbau_von))
        self.anbau_weg.toggled.connect(self.anbau_weglassen_setzen)
        zeile_3d.addWidget(self.anbau_weg)

        # Knickrahmen aus Einzelrohren (K1-2): Vorschlag, wenn Rohre mit passenden Gehrungen aneinanderstoßen
        self.knick_zeile = QWidget()
        kz = QHBoxLayout(self.knick_zeile)
        kz.setContentsMargins(0, 0, 0, 0)
        self.knick_info = QLabel()
        self.knick_info.setStyleSheet("color: #7A5A00;")
        self.knick_info.setWordWrap(True)
        self.knick_knopf = QPushButton("Knickverbindung erstellen …")
        self.knick_knopf.setToolTip("Die vorgeschlagenen Rohre zu einem Knickrahmen verbinden (ein gestrecktes Rohr "
                                    "mit V-Ausschnitten). Eigene Auswahl: Rohre markieren, Rechtsklick.")
        self.knick_knopf.clicked.connect(lambda: self.knick_erstellen())
        kz.addWidget(self.knick_info, 1)
        kz.addWidget(self.knick_knopf)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.kopf)
        ll.addWidget(self.knick_zeile)
        ll.addWidget(self.baum, 1)
        ll.addWidget(self.leiste)
        ll.addLayout(zeile_3d)
        # B1: fehlende Profile und doppelte Artikel als Häkchen statt Rückfragen nach dem Übernehmen
        self.vor_zeile = QWidget()
        vz = QVBoxLayout(self.vor_zeile)
        vz.setContentsMargins(0, 0, 0, 0)
        self.profile_haken = QCheckBox()
        self.profile_haken.setChecked(True)
        self.profile_haken.setToolTip("Profile, die in den Stammdaten fehlen, beim Übernehmen aus den Messwerten "
                                      "anlegen (danach unter Einstellungen → Profile prüfen). Aus = die Teile kommen "
                                      "ohne Profil ins Angebot.")
        self.doppelt_haken = QCheckBox()
        self.doppelt_haken.setToolTip("Artikelnummern, die schon im Angebot stehen, trotzdem noch einmal eintragen. "
                                      "Aus = diese Teile werden übersprungen.")
        self.lernen_haken = QCheckBox()     # B8: Korrekturen fürs nächste Mal merken
        self.lernen_haken.setToolTip("Was hier korrigiert wurde, beim nächsten STEP-Import dieses Kunden gleich so "
                                     "vorbelegen (Einstellungen → Importprofile). Abgewählte Teile kommen als "
                                     "Normteil-Begriffe dazu.")
        for w in (self.profile_haken, self.doppelt_haken, self.lernen_haken):
            w.setStyleSheet("color: #7A5A00;")
            vz.addWidget(w)
        ll.addWidget(self.vor_zeile)
        self.ansicht = Ansicht3DMitKnoepfen()
        teil = QSplitter(Qt.Horizontal)
        teil.addWidget(links)
        teil.addWidget(self.ansicht)
        teil.setSizes([820, 530])
        lay = QVBoxLayout(self)
        lay.addWidget(teil, 1)
        hinweis = hilfe.Hinweis("Häkchen = Teil übernehmen. Profil, Werkstoff und Stückzahl je Teil wählen; leer = später "
                         "eintragen. Art: eine andere wählen, wenn das Teil falsch erkannt wurde. Nicht übernehmbare "
                         "Teile (in 3D magenta): darunter Profilform und Profil-ID wählen und „Nachtragen“. Anbauteile (aufgeschweißte Bolzen, Laschen …): Doppelklick auf "
                         "die Spalte Anbauteile = prüfen. Mit ◀ ▶ zwischen den STEP-Dateien wechseln; Übernehmen übernimmt alle Dateien. "
                         "Enthält eine Datei mehrere Teile, steht sie als Baugruppe da; die Teile werden Einzelpositionen, "
                         "„Anzahl“ oben setzt die Stückzahl aller Teile. Knopf „Als Satz“: die Datei wird ein Satz, "
                         "Anzahl = Sätze, die Spalte zeigt Stück je Satz, "
                         "Stückzahl = Sätze × Stück je Satz. Mehrere Zeilen "
                         "markieren (Strg/Umschalt) und unten Werte setzen; „Für alle“ gilt für alle Dateien. In der "
                         "3D-Ansicht: Anfangsschnitt orange, Endschnitt violett, Innenkonturen rot, Gravur grün, "
                         "Anbauteile sandfarben.", schluessel="step_pruefen")    # erster Satz, Rest hinter „mehr“ (L7)
        lay.addWidget(hinweis)
        knoepfe = QDialogButtonBox()
        knoepfe.addButton("Übernehmen", QDialogButtonBox.AcceptRole)
        self.pdf_knopf = knoepfe.addButton("Übernehmen und Angebot (PDF)", QDialogButtonBox.ActionRole)
        self.pdf_knopf.setToolTip("Übernehmen, optimieren, prüfen und gleich das Angebots-PDF schreiben (Strg+Eingabe)")
        self.pdf_knopf.clicked.connect(self.mit_pdf)
        knoepfe.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.mit_pdf)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        # Ordner je Angebot (B3): STEP-Dateien in den Unterordner STEP kopieren, Vorgabe aus den Einstellungen
        self.kopieren_haken = QCheckBox("STEP-Dateien in den Ordner des Angebots kopieren")
        self.kopieren_haken.setToolTip("Beim Übernehmen werden die gewählten STEP-Dateien in den Unterordner „STEP“ "
                                       "im Ordner des Angebots kopiert. Vorgabe: Einstellungen → STEP-Import.")
        self.kopieren_haken.setChecked(bool(step_kopieren))
        self.kopieren_haken.setVisible(step_kopieren is not None)
        unten = QHBoxLayout()
        unten.addWidget(self.kopieren_haken)
        unten.addStretch(1)
        unten.addWidget(knoepfe)
        lay.addLayout(unten)
        for d in self.mehrteilig:       # ohne Satz: Anzahl = gemeinsame Stückzahl der Teile (z. B. aus dem Formular)
            stk = {z.werte["einzeln"] for z in self.zeilen if z.datei == d}
            if not self.saetze.get(d) and len(stk) == 1 and stk != {0}:
                self.anzahl[d] = int(stk.pop())
        self.datei_waehlen(0)
        # Häkchen der Vorprüfung nach Änderungen auffrischen, gesammelt (nicht während die Liste aufgebaut wird)
        self._vor_uhr = QTimer(self)
        self._vor_uhr.setSingleShot(True)
        self._vor_uhr.setInterval(150)
        self._vor_uhr.timeout.connect(self.vorpruefung_zeigen)
        self.baum.itemChanged.connect(lambda *_: self._vor_uhr.start())
        self.baum.currentItemChanged.connect(lambda *_: self._vor_uhr.start())
        self.anbau_weg.toggled.connect(lambda *_: self._vor_uhr.start())
        self.alle_ws.currentIndexChanged.connect(lambda *_: self._vor_uhr.start())
        self.werte_schreiben()
        self._start = [m.get("_uebernehmen") for m in self.messwerte]       # Stand beim Öffnen (B8)
        self._ws_start, self._anbau_start = self.werkstoff, self.anbau_weg.isChecked()
        self.vorpruefung_zeigen()

    def _baum_fuellen(self):
        """Rohrliste aufbauen (auch nach einem Wechsel der Art): je Datei und Profil eine Gruppe, je Gruppe gleicher
        Teile eine Zeile; Eingaben stehen in den Messwerten (_uebernehmen, _werkstoff, _stueck …)."""
        from . import anbau, step, zukauf
        messwerte, k, werkstoff, stueck, zukauf_liste = (self.messwerte, self.k, self.werkstoff, self.stueck,
                                                         self.zukauf_liste)
        mit_blechen = zukauf_liste is not None
        self.baum.clear()
        self.zeilen = []        # _Zeile je Gruppe gleicher Teile einer Datei
        self.gruppen = {}       # (Datei, gemessenes Profil) -> Gruppen-Item
        self.baugruppen = {}    # Datei mit mehreren Teilen -> Knoten 'Baugruppe' über ihren Gruppen
        for d in self.dateien:
            if d in self.mehrteilig:
                b = self.baugruppen[d] = QTreeWidgetItem(self.baum)
                b.setFirstColumnSpanned(True)
                f = b.font(0)
                f.setBold(True)
                b.setFont(0, f)
                b.setBackground(0, QBrush(stil.farbe("#FFF2CC")))
                b.setExpanded(True)
        teile = step.teile_gruppen(messwerte, mit_blechen)
        fehler = [i for i, m in enumerate(messwerte) if not any(i in l for l in teile.values())
                  and m.get("_knick_von") is None]
        profile = k.auswahl("profil")
        reihe = sorted(teile.items(), key=lambda e: (self.dateien.index(messwerte[e[0]].get("datei")),
                                                     step.profil_vorschlag(messwerte[e[0]], k.profile) or ""))
        for erster, liste in reihe:
            m = messwerte[erster]
            datei = m.get("datei")
            ist_blech = step.blech(m) is not None
            ist_voll = mit_blechen and not ist_blech and step.ist_voll(m)     # Rund-/Vierkantstahl: Zukaufteil
            ist_zk = ist_blech or ist_voll
            vorschlag = self.BLECHGRUPPE if ist_blech else self.VOLLGRUPPE if ist_voll else \
                step.profil_vorschlag(m, k.profile)
            fehlt = not ist_zk and vorschlag not in k.profile
            g = self.gruppen.get((datei, vorschlag))
            if g is None:
                g = self.gruppen[(datei, vorschlag)] = QTreeWidgetItem(self.baugruppen.get(datei) or self.baum)
                g.setFirstColumnSpanned(True)
                g.setData(0, Qt.UserRole, vorschlag)
                f = g.font(0)
                f.setBold(True)
                g.setFont(0, f)
                g.setBackground(0, QBrush(stil.farbe("#FCE4D6" if fehlt else "#E2EFDA" if ist_zk else "#DDEBF7")))
                g.setExpanded(True)
            it = QTreeWidgetItem(g)
            it.setText(0, m.get("artikel") or m.get("datei") or "")
            gewaehlt = (m.get("_uebernehmen", m.get("pruefstatus") != "prüfen" and not m.get("_normteil"))
                        is not False) if ist_blech \
                else m.get("_uebernehmen", not m.get("_normteil")) is not False if ist_voll else step.gewaehlt(m)
            anbauteil = self.anbau_von.get(erster) if self.anbau_weglassen else None
            if anbauteil is not None and "_uebernehmen" not in m:
                gewaehlt = False
            it.setCheckState(0, Qt.Checked if gewaehlt else Qt.Unchecked)
            it.setText(1, str(len(liste)))
            for c, w in ((self.SP_LAENGE, m.get("_knick_laenge") or _f(m, "laenge")),
                         (self.SP_SCHNEIDWEG, _f(m, "schneidweg"))):
                it.setText(c, zahl_als_text(w, 1))
            if m.get("_knickrahmen"):
                it.setToolTip(self.SP_LAENGE, "Gestreckte Länge des Knickrahmens; Schneidweg wird beim Übernehmen "
                                              "für das ganze Rohr gerechnet")
            it.setText(self.SP_KONTUREN, str(int(_f(m, "konturen"))))
            anbauteile = anbau.lesen(m.get("anbauteile"))
            if anbauteile:
                it.setText(self.SP_ANBAU, anbau.kurz(anbauteile))
                it.setToolTip(self.SP_ANBAU, "Doppelklick: Anbauteile prüfen (nicht gelasert, nur Gravur)")
                if anbau.offen(anbauteile):
                    it.setBackground(self.SP_ANBAU, QBrush(stil.farbe("#FFEB9C")))
            hinweis = ["Profil fehlt in den Stammdaten"] if fehlt else []
            if m.get("_knickrahmen"):
                from . import knickverbindung
                hinweis.append(knickverbindung.text(m) + (
                    "" if m.get("_knick_v") is not None else " (Rechtsklick: bearbeiten)"
                    if knickverbindung.ist_koerper(m) else " (Rechtsklick: lösen)"))
            elif m.get("_knick_fehler"):
                hinweis.append(f"Knickrahmen aus einem Körper nicht verbindbar: {m['_knick_fehler']}")
            if anbauteil is not None:
                hinweis.append(f"Anbauteil von {anbauteil}: nicht übernehmen (nur Gravur auf dem Rohr)")
            if ist_voll:
                hinweis.append(f"{step.voll_text(m)}: wird Zukaufteil (EK aus Gewicht × €/kg, Sägen als Zusatzarbeit)")
            if ist_blech:
                hinweis.append(f"{step.blech_text(m)}: wird Zukaufteil")
                if m.get("pruefstatus") == "prüfen":
                    hinweis.append("PRÜFEN – zum Übernehmen anhaken")
            if step.unsicher(m):
                hinweis.append("UNSICHER: " + ", ".join(step.unsicher(m)) + " – zum Übernehmen anhaken")
            if m.get("_normteil"):
                hinweis.append(f"Normteil ({m['_normteil']}) – zum Übernehmen anhaken")
            if m.get("pfad") and m.get("pfad") != m.get("artikel"):
                it.setToolTip(0, f"In der Baugruppe: {m['pfad']}")
            if m.get("_form_gemessen") and m["_form_gemessen"] != m.get("profilform"):
                hinweis.append(f"Art von Hand geändert (gemessen {m['_form_gemessen']})")
            hinweis += [h for h in [m.get("hinweise")] if h]
            it.setText(self.SP_HINWEIS, "; ".join(hinweis))
            if m.get("pruefstatus") == "prüfen":
                it.setBackground(self.SP_HINWEIS, QBrush(stil.farbe("#FFEB9C")))
            for c in (1, self.SP_STUECK, self.SP_LAENGE, self.SP_SCHNEIDWEG, self.SP_KONTUREN):
                it.setTextAlignment(c, int(Qt.AlignRight | Qt.AlignVCenter))
            pr = QComboBox()
            ws = QComboBox()
            if ist_blech and self.blech_werkstoffe:
                self._blech_werkstoffe_fuellen(ws)
            else:
                liste_fuellen(ws, k, "werkstoff")
            if ist_blech:                   # Zukaufartikel: automatisch oder ein vorhandener Blechartikel
                pr.addItem(self.AUTOMATISCH, None)
                gleich, aehnlich = zukauf.blech_dubletten(step.blech(m), m.get("_werkstoff"), zukauf_liste)
                for a, art in [(a, "gleich") for a in gleich] + [(a, "ähnlich") for a in aehnlich]:
                    pr.addItem(f"{a.get('bezeichnung')} ({art}" + (", EK fehlt)" if zukauf.ek_fehlt(a) else ")"),
                               a["id"])
                if gleich:
                    hinweis.append(f"vorhanden: {gleich[0].get('bezeichnung')}")
                elif aehnlich:
                    hinweis.append(f"ähnlich: {aehnlich[0].get('bezeichnung')} (Werkstoff/Kontur prüfen)")
                else:
                    hinweis.append("neuer Zukaufartikel, EK fehlt")
                pr.setCurrentIndex(max(pr.findData(m.get("_blech_artikel")), 0) if m.get("_blech_artikel") else 0)
                pr.setToolTip("Zukaufartikel des Blechs: automatisch = gleicher vorhandener Artikel, sonst neu anlegen "
                              "(ohne Einkaufspreis)")
                ws.setCurrentText(m.get("_werkstoff") or "")     # Werkstoff wird bei Blechen nie angenommen
                ws.setToolTip("Blech-Werkstoff (wie im Blech-Editor); leer = offen (wird nicht angenommen). Mit "
                              "Werkstoff bekommt ein neuer Zukaufartikel den Blech-Richtpreis als EK.")
            elif ist_voll:                  # Zukaufartikel: automatisch oder ein vorhandener Vollmaterial-Artikel
                from . import vollmaterial
                pr.addItem(self.AUTOMATISCH, None)
                ws_m = m.get("_werkstoff", werkstoff) or None
                gleich, aehnlich = vollmaterial.dubletten(m["profilform"], _f(m, "abm_a"), _f(m, "laenge"), ws_m,
                                                          zukauf_liste)
                for a, art_ in [(a, "gleich") for a in gleich] + [(a, "ähnlich") for a in aehnlich]:
                    pr.addItem(f"{a.get('bezeichnung')} ({art_}" + (", EK fehlt)" if zukauf.ek_fehlt(a) else ")"),
                               a["id"])
                hinweis.append(f"vorhanden: {gleich[0].get('bezeichnung')}" if gleich else
                               "neuer Zukaufartikel (Kategorie Vollmaterial)")
                pr.setCurrentIndex(max(pr.findData(m.get("_blech_artikel")), 0) if m.get("_blech_artikel") else 0)
                pr.setToolTip("Zukaufartikel des Vollmaterials: automatisch = gleicher vorhandener Artikel (Form, "
                              "Abmessung, Länge, Werkstoff), sonst neu anlegen (EK = Gewicht × €/kg)")
                ws.setCurrentText(ws_m or "")
            else:
                pr.setEditable(True)        # neue Profil-ID eintippen: wird beim Übernehmen angelegt (Rückfrage)
                pr.addItems(sorted(set(profile) | ({vorschlag} if vorschlag else set())))
                pr.setCurrentText(m.get("_profil") or vorschlag or "")
                ws.setCurrentText(m.get("_werkstoff", werkstoff) or "")
            it.setText(self.SP_HINWEIS, "; ".join(hinweis))
            if not ist_zk:          # anderes Profil gewählt: WARNUNG, wenn der STEP-Querschnitt davon abweicht
                pr.currentTextChanged.connect(lambda t, it=it, m=m, h="; ".join(hinweis), v=vorschlag:
                                              self._profil_warnung(it, m, t, h, v))
                self._profil_warnung(it, m, pr.currentText(), "; ".join(hinweis), vorschlag)
            sp = RechenSpinGanz()
            sp.setRange(0, 100000)
            sp.setSpecialValueText("leer")
            for c, w in ((self.SP_PROFIL, pr), (self.SP_WERKSTOFF, ws), (self.SP_STUECK, sp)):
                self.baum.setItemWidget(it, c, w)
            alt = step.alternative(m)
            # Art bei jeder Zeile wählbar (Patrick 22.10.2026): die andere Messung (Flachstahl/Blech, Profil/
            # Kantteil, ohne Trennung), bei Rohren und Profilen jede andere Profilform, bei Nachträgen zurücknehmen
            art = QComboBox()
            art.addItem(step.art_text(m, alt) + (f" – {step.VON_HAND}" if m.get("_original") else ""), None)
            zu = step.geschlossen(m)
            if alt and not step.rohr_geschlossen(m):     # die andere Messung gehört zum offenen Teil
                art.addItem(step.art_text(alt, m), "alt")
            if step.schalen(m):     # Halbschalen: mehrere je Rohrumfang ↔ eine je Rohr mit Ringen
                art.addItem(step.art_text(dict(m, _schalen=not step.schalen_gewaehlt(m))), "schalen")
            if zu:              # offen gezeichnetes Rohr: mit ergänzter Wand bzw. wieder offen (Patrick 25.10.2026)
                stamm = step.rohr_geschlossen(m) and zu.get("profilform") in ("U-Profil", "C-Profil") and \
                    step.finde_profil(zu, k.profile)
                art.addItem(step.art_text(zu, m) + (f" – Stammdaten {stamm}" if stamm else ""), "zu")
            if zu and step.rohr_geschlossen(m) and alt:     # Kantteil bzw. Profil immer als Auswahl (Patrick)
                art.addItem(step.art_text(alt), "offen_alt")
            if m.get("_original"):
                art.addItem("Nachtrag zurücknehmen (nicht übernehmbar)", "zurueck")
            if not ist_blech:
                for form in k.profilformen:
                    if form != m.get("profilform"):
                        art.addItem(form, "form:" + form)
            art.setToolTip("Erkannte Art; eine andere wählen, wenn das Teil falsch erkannt wurde. Grenzfälle "
                           "(Flachstahl/Blech, Profil/Kantteil) werden in der anderen Art neu gemessen (Ersatzwerte = "
                           "nicht so messbar: bitte prüfen); eine andere Profilform zeigt bei Profil-ID die Profile "
                           "dieser Form.")
            art.currentIndexChanged.connect(lambda n, i=erster, cb=art: n > 0 and self.art_gewaehlt(i, cb.itemData(n)))
            self.baum.setItemWidget(it, self.SP_ART, art)
            it.setData(0, Qt.UserRole, len(self.zeilen))
            z = _Zeile(it, liste, pr, ws, sp, vorschlag, datei,
                       m["_stueck"] if "_stueck" in m and not m.get("_saetze") else stueck,
                       m.get("_je_satz") or len(liste), ist_zk)
            sp.setValue(z.werte[self._modus(datei)])
            if "_stueck_formular" in m and not m.get("_saetze"):     # Stückzahl aus dem Anfrageformular (W6b)
                sicher = m["_stueck_formular"]
                sp.setToolTip("Stückzahl aus dem Anfrageformular" + ("" if sicher else
                              " – unsicher erkannt, bitte prüfen"))
                if not sicher:
                    sp.setStyleSheet(f"background: {stil.farbe(stil.GELB_FLAECHE).name()};")
            sp.valueChanged.connect(lambda v, z=z: z.werte.__setitem__(self._modus(z.datei), v))
            if datei in self.baugruppen:       # Farbe des Teils in der Baugruppen-Ansicht
                punkt = QPixmap(12, 12)
                punkt.fill(QColor(TEILFARBEN[len(self.zeilen) % len(TEILFARBEN)]))
                it.setIcon(0, QIcon(punkt))
            self.zeilen.append(z)
            self._zusatz_text(z)
            if it.text(self.SP_HINWEIS) and not it.toolTip(self.SP_HINWEIS):
                it.setToolTip(self.SP_HINWEIS, it.text(self.SP_HINWEIS))
        self.fehler_gruppen = {}
        magenta = QPixmap(12, 12)
        magenta.fill(QColor(FARBE_FEHLT))
        for i in fehler:
            m = messwerte[i]
            g = self.fehler_gruppen.get(m.get("datei"))
            if g is None:
                g = self.fehler_gruppen[m.get("datei")] = QTreeWidgetItem(self.baugruppen.get(m.get("datei"))
                                                                          or self.baum, ["Nicht übernehmbar"])
                g.setFirstColumnSpanned(True)
                g.setBackground(0, QBrush(stil.farbe("#F8CBAD")))
                g.setExpanded(True)
            # Grund über die ganze Zeile (in der Spalte Hinweis stand er rechts außerhalb des sichtbaren Bereichs)
            it = QTreeWidgetItem(g, [f"{m.get('artikel') or m.get('datei')}: {grund(m)}"])
            it.setFirstColumnSpanned(True)
            it.setToolTip(0, "Nicht übernehmbar: " + grund(m) + ". Anklicken = Teil in der 3D-Ansicht zeigen "
                          "(magenta). Darunter Profilform und Profil-ID wählen und „Nachtragen“: das Teil wird mit "
                          "Länge aus dem Hüllmaß übernommen.")
            it.setData(1, Qt.UserRole, i)
            if m.get("_netz"):
                it.setIcon(0, QIcon(magenta))
            if hat_huelle(m):               # von Hand nachtragen: Profilform, Profil-ID, Knopf
                n = QTreeWidgetItem(it, ["Von Hand nachtragen:"])
                n.setData(1, Qt.UserRole, i)
                form = QComboBox()
                form.addItem("(Profilform)", None)
                for f_ in k.profilformen:
                    form.addItem(f_, f_)
                pid = QComboBox()
                pid.setEditable(True)
                pid.setToolTip("Profil der Stammdaten wählen oder neue Profil-ID eintippen (z. B. QR 40x40x3)")
                form.currentIndexChanged.connect(lambda _n, f=form, p=pid: self._profile_der_form(p, f.currentData()))
                knopf = QPushButton("Nachtragen")
                knopf.setToolTip("Teil als Rohr/Profil übernehmen: Länge = größtes Hüllmaß, gerade Enden, Prüfstatus "
                                 "prüfen; Konturen danach im Schneidweg-Rechner ergänzen")
                knopf.clicked.connect(lambda _=False, i=i, f=form, p=pid: self.von_hand(i, f.currentData(),
                                                                                      p.currentText().strip()))
                for c, w in ((self.SP_ART, form), (self.SP_PROFIL, pid), (self.SP_WERKSTOFF, knopf)):
                    self.baum.setItemWidget(n, c, w)
                it.setExpanded(True)
        for g in self.fehler_gruppen.values():
            n = g.childCount()
            g.setText(0, f"Nicht übernehmbar – {n} Teil{'e' if n != 1 else ''} (in der 3D-Ansicht magenta)")


    def _knick_anzeigen(self):
        """Vorschlag für Knickrahmen aus Einzelrohren in der gezeigten Datei."""
        from . import knickverbindung
        v = [g for g in knickverbindung.vorschlaege(self.messwerte) if self.messwerte[g[0]].get("datei") == self.datei]
        self.knick_vorschlag = v[0] if v else None
        if v:
            namen = ", ".join(str(self.messwerte[i].get("artikel")) for i in v[0])
            self.knick_info.setText(f"Knickrahmen möglich: {len(v[0])} Rohre stoßen mit passenden Gehrungen aneinander "
                                    f"({namen})" + (f", {len(v) - 1} weitere" if len(v) > 1 else ""))
        self.knick_zeile.setVisible(bool(v))

    def _markierte_koerper(self):
        return [i for z in self._markiert() for i in z.liste]

    def _kontextmenue(self, pos):
        from PySide6.QtWidgets import QMenu
        it = self.baum.itemAt(pos)
        z = self._zeile(it)
        menue = QMenu(self)
        if any(self.messwerte[i].get("_zusatz") for x in self._markiert() or ([z] if z else []) for i in x.liste):
            menue.addAction("Zusatzarbeiten entfernen", lambda: self.zusatz_setzen(
                None, self._markiert() or [z]))
            menue.addSeparator()
        koerper = self._markierte_koerper()
        a = menue.addAction("Knickverbindung erstellen …")
        a.setEnabled(len(koerper) >= 2)
        a.triggered.connect(lambda: self.knick_erstellen(koerper))
        from . import knickverbindung
        if z and self.messwerte[z.liste[0]].get("_knick_schenkel") is not None:
            b = menue.addAction("Knickrahmen bearbeiten …")
            b.triggered.connect(lambda: self.knick_bearbeiten(z.liste[0]))
        elif z and self.messwerte[z.liste[0]].get("_knickrahmen") and not knickverbindung.ist_koerper(
                self.messwerte[z.liste[0]]):
            b = menue.addAction("Knickverbindung lösen")
            b.triggered.connect(lambda: self.knick_loesen(z.liste[0]))
        menue.exec(self.baum.viewport().mapToGlobal(pos))

    def knick_erstellen(self, indizes=None, dialog=None):
        """Knickverbindung aus den Rohren indizes (Vorgabe: der Vorschlag der Datei) im Dialog erstellen; dialog(d)
        bedient ihn statt exec (Tests, Bildschirmfotos). Ergebnis: Index des Leitteils oder None."""
        from . import knickverbindung
        from .knickrahmen_dialog import KnickverbindungDialog
        indizes = indizes or getattr(self, "knick_vorschlag", None)
        if not indizes:
            return None
        self.werte_schreiben()
        try:
            d = KnickverbindungDialog(self, self.messwerte, indizes, self.knick_vorgaben)
        except ValueError as f:
            einblendung.melden(self, str(f))
            return None
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
            return None
        try:
            leit = knickverbindung.erstellen(self.messwerte, d.kette, **d.werte())
        except ValueError as f:
            einblendung.melden(self, str(f))
            return None
        self._neu_aufbauen(leit)
        return leit

    def knick_bearbeiten(self, i, dialog=None):
        """Knickrahmen aus einem Körper (Teil i): Anfang, Laufrichtung, Freistich, Zugabe, K-Faktor und Innenwand im
        Dialog ändern; dialog(d) wie bei knick_erstellen. Ergebnis: True, wenn geändert."""
        from . import knickverbindung
        from .knickrahmen_dialog import KnickverbindungDialog
        m = self.messwerte[i]
        teile = knickverbindung.stuecke(m)
        self.werte_schreiben()
        block = m.get("_knickrahmen") or {}
        vorgaben = dict(self.knick_vorgaben, z=block.get("z"), freistich=block.get("freistich"), k=block.get("k"),
                        schraeg=block.get("schraeg"), start=(m.get("_knick_teile") or [{}])[0].get("i"))
        try:
            d = KnickverbindungDialog(self, teile, list(range(len(teile))), vorgaben, koerper=True)
        except ValueError as f:
            einblendung.melden(self, str(f))
            return False
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
            return False
        try:
            knickverbindung.erstellen(teile, d.kette, **d.werte(), ziel=m)
        except ValueError as f:
            einblendung.melden(self, str(f))
            return False
        self._neu_aufbauen(i)
        return True

    def knick_loesen(self, i):
        from . import knickverbindung
        self.werte_schreiben()
        knickverbindung.loesen(self.messwerte, i)
        self._neu_aufbauen(i)

    def _modus(self, datei):
        return "satz" if self.saetze.get(datei) else "einzeln"

    @property
    def datei(self):
        return self.dateien[self.datei_nr] if self.dateien else None

    def _datei_von(self, it):
        """STEP-Datei eines Eintrags der Liste (Teil, Profilgruppe, Baugruppe, nicht übernehmbar) oder None."""
        while it is not None:
            z = self._zeile(it)
            if z:
                return z.datei
            for d, b in list(self.baugruppen.items()) + list(self.fehler_gruppen.items()):
                if b is it:
                    return d
            g = next((k for k, g in self.gruppen.items() if g is it), None)
            if g:
                return g[0]
            it = it.parent()
        return None

    def _markiert_datei(self, it):
        """Anderer Eintrag markiert (alle Dateien in einer Liste, V1): Kopf (Anzahl, Als Satz) folgt seiner Datei."""
        d = self._datei_von(it)
        if d is not None and d != self.datei and d in self.dateien:
            self.datei_waehlen(self.dateien.index(d), springen=False)

    def datei_waehlen(self, nr, springen=True):
        """Datei Nr. nr (ab 0) wählen: Kopf (Feld Anzahl, Als Satz) für diese Datei, 3D des ersten Teils. Alle Dateien
        stehen in einer Liste (Plan Angebotsablauf V1); springen = zur Datei blättern."""
        if not self.dateien:
            return
        self.datei_nr = max(0, min(nr, len(self.dateien) - 1))
        d = self.datei
        n = len(self.dateien)
        self.datei_text.setText(f"Datei {self.datei_nr + 1} von {n}: {Path(str(d)).name}" if n > 1
                                else Path(str(d)).name)
        self.datei_text.setToolTip(str(d))
        self.dateien_info.setText("alle Dateien in der Liste, ◀ ▶ springen" if n > 1 else "")
        self.zurueck.setEnabled(self.datei_nr > 0)
        self.vor.setEnabled(self.datei_nr < n - 1)
        self.zurueck.setVisible(n > 1)
        self.vor.setVisible(n > 1)
        for (datei, vorschlag), g in self.gruppen.items():
            anz = g.childCount()
            vorn = "" if datei in self.baugruppen or n == 1 else f"{Path(str(datei)).stem} · "
            g.setText(0, f"{vorn}{vorschlag or 'ohne Profil'} – {anz} Teil{'e' if anz != 1 else ''}"
                      + ("  (Profil fehlt in den Stammdaten)" if vorschlag not in self.k.profile
                         and vorschlag not in (self.BLECHGRUPPE, self.VOLLGRUPPE) else ""))
        if springen:
            ziel = self.baugruppen.get(d) or next((g for (datei, _), g in self.gruppen.items() if datei == d),
                                                  None) or self.fehler_gruppen.get(d)
            if ziel is not None:
                self.baum.scrollToItem(ziel, QAbstractItemView.PositionAtTop)
        self.satz_feld.setVisible(d in self.mehrteilig)
        self.satz_info.setVisible(d in self.mehrteilig)
        self._kopf_werte(d)
        self._satz_anzeigen()
        self._knick_anzeigen()
        if not springen:
            return
        self.baum.clearSelection()
        erste = [z for z in self.zeilen if z.datei == d]
        if d in self.baugruppen:
            self._zeigen(self.baugruppen[d])     # Baugruppe zusammengebaut, ohne sie zu markieren
        elif erste:
            self._zeigen(erste[0].it)      # 3D des ersten Teils, ohne es zu markieren
        else:
            fg = self.fehler_gruppen.get(d)
            if fg and fg.childCount():
                self._zeigen(fg.child(0))

    def _satz_anzeigen(self):
        d = self.datei
        satz = bool(self.saetze.get(d))
        self.bg_haken.blockSignals(True)
        self.bg_haken.setChecked(bool(self.baugruppe.get(d)))
        self.bg_haken.blockSignals(False)
        self.bg_haken.setEnabled(satz)
        from .step import satzname as _sn
        self.ziel_wahl.blockSignals(True)
        self.ziel_wahl.clear()
        self.ziel_wahl.addItem("eigene Baugruppe", None)
        hat_unter = d in self.bg_ziel.values()           # nur eine Ebene: Datei mit Unterbaugruppen bleibt oben
        for andere in self.dateien:
            if not hat_unter and andere != d and andere in self.mehrteilig and andere not in self.bg_ziel:
                self.ziel_wahl.addItem(f"in Baugruppe „{_sn(andere)}“", andere)
        self.ziel_wahl.setCurrentIndex(max(0, self.ziel_wahl.findData(self.bg_ziel.get(d))))
        self.ziel_wahl.blockSignals(False)
        self.ziel_wahl.setVisible(self.ziel_wahl.count() > 1 or hat_unter)
        self.ziel_wahl.setEnabled(satz and bool(self.baugruppe.get(d)))
        self.baum.headerItem().setText(self.SP_STUECK, "Stück je Satz" if satz else "Stückzahl")
        if d in self.mehrteilig:
            koerper, verschieden = self.mehrteilig[d]
            from .step import satzname
            n = self.saetze[d]
            self.satz_info.setText(f"Satz „{satzname(d)}“" if satz else f"{koerper} Einzelteile")
            self.baugruppen[d].setText(0, f"Baugruppe „{satzname(d)}“ – {koerper} Teile, {verschieden} verschieden – "
                                       + (f"{n} {'Satz' if n == 1 else 'Sätze'}" if satz else "als Einzelteile"))

    def _ziel_setzen(self, ziel, datei=None):
        """Datei als Unterbaugruppe in die Schweißbaugruppe der Datei ziel einhängen (None = eigene Baugruppe, P8).
        Die Zieldatei wird dabei selbst Schweißbaugruppe. Nur eine Ebene: Hat die Datei selbst Unterbaugruppen oder
        hängt das Ziel schon in einer anderen Baugruppe, bleibt alles, wie es ist (Ergebnis False)."""
        datei = self.datei if datei is None else datei
        if ziel:
            if ziel == datei or ziel in self.bg_ziel or datei in self.bg_ziel.values():
                return False
            self.bg_ziel[datei] = ziel
            self.baugruppe[ziel] = True
            if not self.saetze.get(ziel) and ziel in self.mehrteilig:
                self.saetze[ziel] = 1
        else:
            self.bg_ziel.pop(datei, None)
        return True

    def _kopf_werte(self, datei):
        """Feld Anzahl und Knopf Als Satz der gezeigten Datei ohne Signale setzen."""
        for w in (self.satz_spin, self.satz_knopf):
            w.blockSignals(True)
        self.satz_spin.setValue(self.anzahl.get(datei, 1))
        self.satz_knopf.setChecked(bool(self.saetze.get(datei)))
        for w in (self.satz_spin, self.satz_knopf):
            w.blockSignals(False)

    def anzahl_setzen(self, n, datei=None):
        """Feld Anzahl einer Datei (Vorgabe: die gezeigte). Ohne Satz bekommt jedes Teil diese Stückzahl (bleibt
        Einzelposition, wird nie von selbst ein Satz); mit Satz ist es die Anzahl Sätze."""
        datei = self.datei if datei is None else datei
        if datei not in self.mehrteilig:
            raise KeyError(datei)
        n = max(1, int(n or 1))
        self.anzahl[datei] = n
        if self.saetze.get(datei):
            return self.saetze_setzen(n, datei)
        for z in self.zeilen:
            if z.datei == datei:
                z.werte["einzeln"] = n
                z.sp.blockSignals(True)
                z.sp.setValue(n)
                z.sp.blockSignals(False)
        if datei == self.datei:
            self._kopf_werte(datei)

    def als_satz_setzen(self, an, datei=None):
        """Knopf Als Satz: an = die Datei wird ein Satz mit Anzahl Sätze aus dem Feld Anzahl; aus = Einzelpositionen."""
        datei = self.datei if datei is None else datei
        self.saetze_setzen(self.anzahl.get(datei, 1) if an else 0, datei)

    def saetze_setzen(self, n, datei=None):
        """Anzahl Sätze einer Datei (Vorgabe: die gezeigte); 0 = Einzelpositionen. Wechselt die Spalte Stückzahl
        zwischen Stückzahl und Stück je Satz."""
        datei = self.datei if datei is None else datei
        if datei not in self.mehrteilig:
            raise KeyError(datei)
        self.saetze[datei] = int(n or 0)
        if n:
            self.anzahl[datei] = int(n)
        for z in self.zeilen:
            if z.datei == datei:
                z.sp.blockSignals(True)
                z.sp.setValue(z.werte[self._modus(datei)])
                z.sp.blockSignals(False)
        if datei == self.datei:
            self._kopf_werte(datei)
            self._satz_anzeigen()

    def _zeile(self, it):
        if it is None or it.parent() is None:
            return None
        n = it.data(0, Qt.UserRole)
        return self.zeilen[n] if isinstance(n, int) and 0 <= n < len(self.zeilen) and self.zeilen[n].it is it else None

    def baugruppe_zeigen(self, datei, hervor=(), vorn=""):
        """Alle Teile der Datei in Einbaulage in der 3D-Ansicht; hervor = Indizes der Messwerte, die farbig
        hervorgehoben werden; nicht übernehmbare Teile magenta. vorn: Text vor der Erklärung (z. B. der Grund)."""
        from .ansicht3d import baugruppe
        from .step import satzname
        teile = [i for i, m in enumerate(self.messwerte) if m.get("datei") == datei and m.get("_netz")]
        zeile = {i: n for n, z in enumerate(self.zeilen) for i in z.liste}      # gleiche Teile = gleiche Farbe
        fehlt = {it.data(1, Qt.UserRole) for g in self.fehler_gruppen.values() for it in
                 (g.child(n) for n in range(g.childCount()))}
        netz, ohne = baugruppe([self.messwerte[i]["_netz"] for i in teile],
                               {n for n, i in enumerate(teile) if i in set(hervor)},
                               [zeile.get(i, len(self.zeilen) + n) for n, i in enumerate(teile)],
                               {n for n, i in enumerate(teile) if i in fehlt})
        n_fehlt = sum(1 for i in teile if i in fehlt)
        info = (f"Baugruppe „{satzname(datei)}“ mit {len(teile) - ohne} Teilen in Einbaulage"
                + (", blau: die gewählten Teile" if hervor else ", gleiche Teile in gleicher Farbe")
                + (f", magenta: {n_fehlt} nicht übernehmbare{'s' if n_fehlt == 1 else ''} Teil{'e' if n_fehlt != 1 else ''}"
                   if n_fehlt and not set(hervor) >= {i for i in teile if i in fehlt} else "")
                + ". Teil in der Liste anklicken = Einzelteil "
                "mit Schnitten und Konturen.")
        if ohne:
            info += f" {ohne} Teil{'e' if ohne != 1 else ''} ohne Einbaulage (ältere Messung) fehlen."
        self.ansicht.setzen(netz, f"Baugruppe {satzname(datei)}", (vorn + "<br>" if vorn else "") + info)

    def _zeigen(self, it):
        if it is not None and it in self.baugruppen.values():
            self.baugruppe_zeigen(next(d for d, b in self.baugruppen.items() if b is it))
            return
        fg = next((d for d, g in self.fehler_gruppen.items() if g is it), None)
        if fg is not None and fg in self.baugruppen:     # Gruppe 'Nicht übernehmbar': alle diese Teile zeigen
            self.baugruppe_zeigen(fg, [it.child(n).data(1, Qt.UserRole) for n in range(it.childCount())])
            return
        gruppe = next((k for k, g in self.gruppen.items() if g is it), None)
        if gruppe and gruppe[0] in self.baugruppen:      # Profilgruppe einer Baugruppe: ihre Teile hervorheben
            self.baugruppe_zeigen(gruppe[0], [i for z in self.zeilen if z.it.parent() is it for i in z.liste])
            return
        z = self._zeile(it)
        if z:
            m = self.messwerte[z.liste[0]]
            if m.get("_knickrahmen"):           # Knickrahmen: alle Schenkel gefaltet
                from . import knickverbindung
                self.ansicht.setzen(knickverbindung.netz_gefaltet(self.messwerte, m) or m.get("_netz"),
                                    m.get("artikel") or "", knickverbindung.text(m))
                return
            self.ansicht.setzen(m.get("_netz"), m.get("artikel") or "", _messinfo(m))
        elif it is not None and it.data(1, Qt.UserRole) is not None:   # nicht übernehmbar: Grund und wo es sitzt
            i = it.data(1, Qt.UserRole)
            m = self.messwerte[i]
            vorn = f"<b style='color:#B42318'>Nicht übernehmbar: {grund(m)}</b>"
            if m.get("datei") in self.baugruppen and m.get("_netz"):
                self.baugruppe_zeigen(m["datei"], [i], vorn)
            else:
                self.ansicht.setzen(m.get("_netz"), m.get("artikel") or m.get("datei") or "",
                                    vorn + ("" if m.get("_netz") else "<br>Für dieses Teil gibt es keine 3D-Daten."))

    def _markiert(self):
        z = [self._zeile(it) for it in self.baum.selectedItems()
             if not it.isHidden() and it.parent() is not None and not it.parent().isHidden()]
        return [x for x in z if x]

    def alle_setzen(self, werkstoff=None, stueck=None, nur_markierte=False, zusatz=None):
        """Werkstoff, Stückzahl und/oder Zusatzarbeit (None = Auswahl unten) in alle Teile aller Dateien bzw. die
        markierten Zeilen schreiben. Die Stückzahl gilt nur für Teile ohne Satz (bei einem Satz zählt das Feld Anzahl
        als Sätze); die Zusatzarbeit kommt zu den schon gewählten dazu (V4)."""
        werkstoff = werkstoff if werkstoff is not None else (
            self.alle_ws.currentText() if self.alle_ws.currentIndex() > 0 else None)
        stueck = stueck if stueck is not None else (self.alle_stk.value() or None)
        zusatz = zusatz if zusatz is not None else self.alle_zusatz.currentData()
        ziel = self._markiert() if nur_markierte else self.zeilen
        if zusatz:
            self.zusatz_setzen(zusatz, ziel)
        for z in ziel:
            if werkstoff is not None:
                z.ws.setCurrentText(werkstoff)
            if stueck is not None:
                z.werte["einzeln"] = stueck
                if not self.saetze.get(z.datei):
                    z.sp.setValue(stueck)

    def zusatz_setzen(self, name, zeilen=None):
        """Zusatzarbeit name an die Teile der Zeilen (Vorgabe: alle) hängen; None = ihre Zusatzarbeiten entfernen."""
        for z in self.zeilen if zeilen is None else zeilen:
            for i in z.liste:
                m = self.messwerte[i]
                m["_zusatz"] = [n for n in m.get("_zusatz") or () if n != name] + [name] if name else []
            self._zusatz_text(z)

    def _zusatz_text(self, z):
        namen = self.messwerte[z.liste[0]].get("_zusatz") or []
        z.it.setText(self.SP_ZUSATZ, ", ".join(namen))
        z.it.setToolTip(self.SP_ZUSATZ, "Zusatzarbeiten für dieses Teil (Rechtsklick: entfernen)" if namen else "")

    def referenz_text(self):
        """Anfrage-Nr. des Kunden aus dem Feld oben (V5), None = kein Feld bzw. leer."""
        return (self.referenz.text().strip() or None) if self.referenz is not None else None

    def _blech_werkstoffe_fuellen(self, cb):
        """Blech-Werkstoffe (Einstellungen → Blech-Werkstoffe) nach Kategorie, davor leer = offen."""
        cb.addItem("")
        gruppen = {}
        for wid, z in sorted(self.blech_werkstoffe.items()):
            gruppen.setdefault(z.get("kategorie") or "", []).append(wid)
        for titel, ids in sorted(gruppen.items()):
            if titel:
                cb.addItem(f"— {titel} —")
                it = cb.model().item(cb.count() - 1)
                it.setEnabled(False)
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            cb.addItems(ids)

    def art_wechseln(self, index, rohr=False):
        """Art der Zeile mit dem Teil Nr. index umstellen (Flachstahl ↔ Blech, Profil ↔ Kantteil; rohr: offenes
        Rohr ↔ geschlossenes Rohr mit ergänzter Wand): alle gleichen Teile der Zeile bekommen die Messwerte der
        anderen Art; die Liste wird neu aufgebaut, die Eingaben der anderen Zeilen bleiben. Profil bzw. Zukaufartikel
        und Werkstoff werden für die neue Art neu vorbelegt (Blech: Werkstoff leer), die Stückzahl bleibt."""
        from . import step
        z = next(z for z in self.zeilen if index in z.liste)
        self.werte_schreiben()
        for i in z.liste:
            (step.rohr_wechseln if rohr else step.art_wechseln)(self.messwerte[i])
        self._baum_fuellen()
        self.datei_waehlen(self.datei_nr)
        neu = next((x for x in self.zeilen if index in x.liste), None)
        if neu:
            self.baum.setCurrentItem(neu.it)
        return neu

    def art_gewaehlt(self, index, wahl):
        """Auswahl in der Spalte Art: 'alt' = andere Messung, 'zu' = offenes Rohr schließen bzw. wieder offen,
        'schalen' = Halbschalen mehrere je Rohrumfang bzw. eine je Rohr, 'offen_alt' = offenes Rohr als Kantteil bzw.
        die andere Art des offenen Teils, 'zurueck' = Nachtrag zurücknehmen, andere
        Profilform 'form:F' (Profil-ID zeigt die Profile dieser Form)."""
        if wahl == "alt":
            return self.art_wechseln(index)
        if wahl == "zu":
            return self.art_wechseln(index, rohr=True)
        if wahl == "schalen":
            return self.schalen_wechseln(index)
        if wahl == "offen_alt":     # offenes Rohr als Kantteil (bzw. die andere Art des offenen Teils)
            self.art_wechseln(index, rohr=True)
            return self.art_wechseln(index)
        if wahl == "zurueck":
            return self.von_hand_zuruecknehmen(index)
        if isinstance(wahl, str) and wahl.startswith("form:"):
            return self.form_setzen(index, wahl[5:])
        return None

    def schalen_wechseln(self, index):
        """Halbschalen der Zeile mit dem Teil Nr. index: mehrere je Rohrumfang (ganz freigeschnitten) ↔ eine je Rohr mit
        Ringen an den Enden (Patrick 25.10.2026, „Rundrohr alle a“). Die Eingaben der Zeile bleiben."""
        from . import step
        z = next(z for z in self.zeilen if index in z.liste)
        self.werte_schreiben()
        for i in z.liste:
            self.messwerte[i]["_schalen"] = not step.schalen_gewaehlt(self.messwerte[i])
        return self._neu_aufbauen(index)

    def _profile_der_form(self, cb, form):
        """Profil-ID-Auswahl auf die Profile einer Form beschränken (leer = alle)."""
        text = cb.currentText()
        cb.blockSignals(True)
        cb.clear()
        cb.addItems(sorted(pid for pid, p in self.k.profile.items() if not form or p.get("form") == form))
        cb.setCurrentText(text if text in self.k.profile and (not form or self.k.profile[text].get("form") == form)
                          else "")
        cb.blockSignals(False)

    def _profil_warnung(self, it, m, profil, hinweis, vorschlag):
        """Hinweis der Zeile mit der WARNUNG step.profil_abweichung, wenn ein anderes Profil als das gemessene gewählt
        ist und der Querschnitt davon abweicht; die Enden werden beim Übernehmen für das Profil neu gerechnet."""
        from . import step
        profil = (profil or "").strip()
        warnung = step.profil_abweichung(m, self.k.profile.get(profil)) if profil and profil != vorschlag else None
        it.setText(self.SP_HINWEIS, "; ".join(filter(None, [warnung, hinweis])))
        it.setToolTip(self.SP_HINWEIS, (warnung + ". Beim Übernehmen werden Anfangs- und Endschnitt mit der gemessenen "
                                        "Form für das gewählte Profil neu gerechnet, Innenkonturen bleiben gemessen.")
                      if warnung else "")
        if warnung:
            it.setBackground(self.SP_HINWEIS, QBrush(stil.farbe("#FFD966")))
        elif m.get("pruefstatus") != "prüfen":
            it.setBackground(self.SP_HINWEIS, QBrush())

    def form_setzen(self, index, form):
        """Andere Profilform für die Zeile mit dem Teil Nr. index (Messwerte bleiben, nur die Form): die Liste wird
        neu aufgebaut, Profil-ID = passendes Profil der Stammdaten in der neuen Form, sonst leer."""
        from . import step
        z = next(z for z in self.zeilen if index in z.liste)
        self.werte_schreiben()
        for i in z.liste:
            m = self.messwerte[i]
            m.setdefault("_form_gemessen", m.get("profilform"))
            m["profilform"] = form
            m["_profil"] = step.finde_profil(m, self.k.profile)
            m["_uebernehmen"] = True
        return self._neu_aufbauen(index)

    def von_hand(self, index, form, profil_id):
        """Nicht übernehmbares Teil Nr. index (und alle gleichen der Datei, siehe Hüllmaß) von Hand als Rohr/Profil
        nachtragen; gibt die neue Zeile zurück oder None (keine Profilform gewählt)."""
        from . import step
        if not form:
            return None
        self.werte_schreiben()
        m = self.messwerte[index]
        masse = lambda x: sorted(float(v) for v in x.get("huelle", "").split("|") if v)
        gleiche = [i for g in self.fehler_gruppen.values() for i in (g.child(n).data(1, Qt.UserRole)
                                                                     for n in range(g.childCount()))
                   if self.messwerte[i].get("datei") == m.get("datei") and hat_huelle(self.messwerte[i])
                   and all(abs(a - b) <= 0.2 for a, b in zip(masse(self.messwerte[i]), masse(m)))]
        if not step.von_hand(m, form, profil_id, self.k.profile):
            return None
        for i in gleiche:           # gleiche nicht übernehmbare Körper der Datei (gleiches Hüllmaß) ebenso
            if i != index:
                step.von_hand(self.messwerte[i], form, profil_id, self.k.profile)
        return self._neu_aufbauen(index)

    def von_hand_zuruecknehmen(self, index):
        from . import step
        z = next(z for z in self.zeilen if index in z.liste)
        self.werte_schreiben()
        for i in z.liste:
            step.von_hand_zuruecknehmen(self.messwerte[i])
        self._baum_fuellen()
        self.datei_waehlen(self.datei_nr)
        return None

    def _neu_aufbauen(self, index):
        self._baum_fuellen()
        self.datei_waehlen(self.datei_nr)
        neu = next((x for x in self.zeilen if index in x.liste), None)
        if neu:
            self.baum.setCurrentItem(neu.it)
        return neu

    def anbau_weglassen_setzen(self, an):
        """Option 'Anbauteile nicht ins Angebot übernehmen': Häkchen der angeschweißten Körper ab- bzw. wieder
        anwählen (wie ohne Option vorbelegt); die Eingaben der anderen Zeilen bleiben."""
        from . import step
        self.werte_schreiben()
        self.anbau_weglassen = bool(an)
        for i in self.anbau_von:
            m = self.messwerte[i]
            m["_anbau_weglassen"] = self.anbau_weglassen
            m.pop("_uebernehmen", None)
            if not self.anbau_weglassen and step.blech(m) is None:
                m["_uebernehmen"] = step.gewaehlt(m)
        self._baum_fuellen()
        self.datei_waehlen(self.datei_nr)

    def _doppelklick(self, it, spalte):
        z = self._zeile(it)
        if z and spalte == self.SP_ANBAU and it.text(self.SP_ANBAU):
            self.anbau_pruefen(z.liste[0])

    def anbau_pruefen(self, index, dialog=False):
        """Dialog 'Anbauteile prüfen' für die Zeile mit dem Teil Nr. index; dialog=True: nur den Dialog zurückgeben
        (Tests, Bildschirmfotos), anbau_uebernehmen setzt dann sein Ergebnis."""
        from . import step
        from .anbau_dialog import AnbauDialog
        m = self.messwerte[index]
        d = AnbauDialog(self, m.get("anbauteile"), m.get("artikel") or m.get("datei") or "", _f(m, "gravur"),
                        step.ohne_trennung_text(m))
        if dialog:
            return d
        if d.exec() == QDialog.Accepted:
            return self.anbau_uebernehmen(index, d.ergebnis)
        return None

    def anbau_uebernehmen(self, index, ergebnis):
        """Ergebnis des Dialogs für alle gleichen Teile der Zeile übernehmen: neue Liste der Anbauteile (Gravur um
        den Unterschied; sind alle unsicheren entschieden, wird das Teil angehakt) oder 'ohne Trennung' (die Messung
        ohne Abtrennen gilt, wie ein Wechsel der Art). Gibt die neue Zeile zurück."""
        from . import anbau, step
        from .anbau_dialog import OHNE_TRENNUNG
        if ergebnis == OHNE_TRENNUNG:
            return self.art_wechseln(index)
        z = next(z for z in self.zeilen if index in z.liste)
        self.werte_schreiben()
        for i in z.liste:
            step.anbau_setzen(self.messwerte[i], ergebnis)
            if not anbau.offen(ergebnis) and not step.unsicher(self.messwerte[i]):
                self.messwerte[i]["_uebernehmen"] = True
        self._baum_fuellen()
        self.datei_waehlen(self.datei_nr)
        neu = next((x for x in self.zeilen if index in x.liste), None)
        if neu:
            self.baum.setCurrentItem(neu.it)
        return neu

    def alle_waehlen(self, an):
        for z in self.zeilen:
            z.it.setCheckState(0, Qt.Checked if an else Qt.Unchecked)

    def zeile_setzen(self, artikel, uebernehmen=None, profil=None, werkstoff=None, stueck=None):
        """Werte einer Zeile ohne Maus setzen (Tests, Bildschirmfotos). stueck = Wert der Spalte (bei einem Satz
        Stück je Satz)."""
        for z in self.zeilen:
            if z.it.text(0) == artikel:
                if uebernehmen is not None:
                    z.it.setCheckState(0, Qt.Checked if uebernehmen else Qt.Unchecked)
                if profil is not None:
                    z.pr.setCurrentText(profil)
                if werkstoff is not None:
                    z.ws.setCurrentText(werkstoff)
                if stueck is not None:
                    z.sp.setValue(stueck)
                return z
        raise KeyError(artikel)

    def werte_schreiben(self):
        """Gewählte Werte in die Messwerte schreiben (_uebernehmen, _profil, _werkstoff, _stueck; bei einem Satz
        _saetze = Sätze, _stueck = Sätze, _je_satz = Stück je Satz)."""
        for z in self.zeilen:
            profil = z.pr.currentText().strip()
            saetze = self.saetze.get(z.datei) if z.datei in self.mehrteilig else 0
            for i in z.liste:
                m = self.messwerte[i]
                m["_uebernehmen"] = z.it.checkState(0) == Qt.Checked
                m["_d3"] = self.d3.isChecked()
                m["_anbau_weglassen"] = self.anbau_weglassen
                m["_werkstoff"] = z.ws.currentText() or None
                m["_baugruppe"] = bool(saetze and self.baugruppe.get(z.datei))
                m["_in_baugruppe"] = self.bg_ziel.get(z.datei) if m["_baugruppe"] else None
                if saetze:
                    m["_saetze"], m["_stueck"] = saetze, saetze
                    m["_je_satz"] = z.werte["satz"] or len(z.liste)
                else:
                    m["_saetze"] = 0           # leer = Einzelpositionen (auch ohne Rückfrage)
                    m.pop("_je_satz", None)
                    m["_stueck"] = z.werte["einzeln"] or None
                if z.blech:
                    m["_blech_artikel"] = z.pr.currentData()
                elif profil and profil != z.vorschlag:
                    m["_profil"] = profil
                else:
                    m.pop("_profil", None)
        return self.messwerte

    def accept(self):
        self.werte_schreiben()
        k = self.korrekturen()
        self.lernen_werte = k if k and self.lernen_haken.isChecked() else None
        super().accept()

    def korrekturen(self):
        """Korrekturen, die sich als Importprofil des Kunden merken lassen (B8), oder {}."""
        if not self.lernen or not self.kundennr or not hasattr(self, "_start"):
            return {}
        from . import importprofil
        return importprofil.korrekturen(self.messwerte, self._start, self.werkstoff, self._anbau_start
                                        if self.anbau_von else None, self.anbau_weg.isChecked(),
                                        zusatz_vorgabe=self.zusatz_vorgabe)

    def mit_pdf(self):
        """Übernehmen und danach gleich das Angebots-PDF (B1)."""
        self.pdf_danach = True
        self.accept()

    def neue_profile_anlegen(self):
        return self.profile_haken.isChecked()

    def doppelte_eintragen(self):
        return self.doppelt_haken.isChecked()

    def vorpruefung_zeigen(self):
        """Häkchen für fehlende Profile und schon vorhandene Artikel nach dem aktuellen Stand der Auswahl."""
        if getattr(self, "_vor_laeuft", False):
            return
        self._vor_laeuft = True
        try:
            self.werte_schreiben()
            fehlend, doppelt = self.vorpruefung() if self.vorpruefung is not None else ([], 0)
            korr = self.korrekturen()
        finally:
            self._vor_laeuft = False
        from . import importprofil
        self.lernen_haken.setText(f"Für Kunde {self.kundennr} merken (Importprofil): "
                                  + importprofil.korrekturen_text(korr))
        self.lernen_haken.setVisible(bool(korr))
        self.profile_haken.setText("Fehlende Profile aus den Messwerten anlegen (bitte danach prüfen): "
                                   + ", ".join(fehlend[:8]) + (" …" if len(fehlend) > 8 else ""))
        self.profile_haken.setVisible(bool(fehlend))
        self.doppelt_haken.setText(f"{doppelt} Artikel stehen schon im Angebot – trotzdem noch einmal eintragen")
        self.doppelt_haken.setVisible(bool(doppelt))
        self.vor_zeile.setVisible(bool(fehlend or doppelt or korr))
        return fehlend, doppelt

    def _kunde_setzen(self):
        """Kunde gewechselt: Importprofil des Kunden anwenden (Benennung, Normteile, Werkstoff-Vorgabe) und die Liste
        neu aufbauen; eigene Eingaben bleiben, nur der Werkstoff der alten Vorgabe wird ersetzt."""
        neu = self.kunde_wahl.currentData()
        if neu is None or str(neu) == str(self.kundennr or ""):
            return
        self.kundennr = neu
        if self.kunde_gewechselt is None:
            return
        # Häkchen wie beim Öffnen (Vorgabe: Normteile, unsichere Teile) folgen dem neuen Importprofil; nur selbst
        # geänderte bleiben
        self.werte_schreiben()
        for m, v in zip(self.messwerte, self._start):
            if m.get("_uebernehmen") == v:
                m.pop("_uebernehmen", None)
        alt_ws = self.werkstoff
        ws = self.kunde_gewechselt(neu)
        if isinstance(ws, tuple):       # (Werkstoff, Zusatzarbeiten des neuen Importprofils)
            ws, self.zusatz_vorgabe = ws[0], list(ws[1] or ())
        if ws != alt_ws:
            for m in self.messwerte:
                if m.get("_werkstoff", alt_ws) == alt_ws and not m.get("_blech_artikel"):
                    m["_werkstoff"] = ws
            self.werkstoff = ws
        self._baum_fuellen()
        self.datei_waehlen(self.datei_nr)
        self.werte_schreiben()
        self._start = [m.get("_uebernehmen") for m in self.messwerte]   # Vorgabe des neuen Kunden (B8 lernt dazu)
        self._ws_start = self.werkstoff
        self.vorpruefung_zeigen()


class Positionen3DDialog(_Mit3D):
    """3D-Ansicht der Positionen eines Angebots (Teile aus dem STEP-Import)."""

    def __init__(self, parent, positionen, netze, gewaehlt=0, bearbeiten=None):
        """bearbeiten(zeile): Editor der Position öffnen (Plan 3D-Editor F1: Doppelklick auf das Teil im 3D oder in
        der Liste, Knopf „Im Editor öffnen“); None = nur ansehen."""
        super().__init__(parent, "3D-Ansicht der Positionen", ("Pos.", "Artikelnummer", "Bezeichnung", "Profil-ID",
                                                              "Teilelänge [mm]", "3D"))
        self.positionen, self.netze, self.bearbeiten = positionen, netze, bearbeiten
        self.geoeffnet = None
        self._fuellen([(p.get("pos"), p.get("artikel"), p.get("bezeichnung"), p.get("profil_id"), p.get("laenge"),
                        "ja" if p["id"] in netze else "–") for p in positionen])
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        if bearbeiten is not None:
            b = knoepfe.addButton("Im Editor öffnen", QDialogButtonBox.ActionRole)
            b.setToolTip("Die gewählte Position im Teile-Editor öffnen (auch Doppelklick auf das Teil oder die Zeile)")
            b.clicked.connect(self.editor_oeffnen)
            self.liste.cellDoubleClicked.connect(lambda *_: self.editor_oeffnen())
            self.ansicht.ansicht.doppelklick_ziel = self.editor_oeffnen
        self.lay.addWidget(knoepfe)
        if positionen:
            self.liste.selectRow(gewaehlt)
            self._zeigen(gewaehlt)

    def editor_oeffnen(self):
        """Fenster schließen und den Editor der gewählten Position öffnen (bearbeiten)."""
        r = self.liste.currentRow()
        if self.bearbeiten is None or not 0 <= r < len(self.positionen):
            return
        self.geoeffnet = r
        self.accept()
        self.bearbeiten(r)

    def _zeigen(self, r):
        if 0 <= r < len(self.positionen):
            p = self.positionen[r]
            titel = f"Pos. {p.get('pos') or ''} {p.get('artikel') or ''}"
            info = "" if p["id"] in self.netze else "Für diese Position gibt es keine 3D-Daten (nicht per STEP-Import)."
            self.ansicht.setzen(self.netze.get(p["id"]), titel, info)
