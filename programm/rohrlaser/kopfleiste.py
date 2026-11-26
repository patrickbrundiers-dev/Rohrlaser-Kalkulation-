"""Kopfleiste „Klar“ (UI/UX Next Level Phase 2, Freigabe Patrick 26.11.2026, Variante A mit F2).

Die Menüleiste zeigt statt fünf und mehr Menüs nur noch einen Knopf „☰ Menü“. Darin stehen alle Menüs, das lange
Menü Datei (rund 40 Einträge) nach Themen geteilt: Datei, Daten und Abgleich, Auswertung und Prüfung, KI. Rechts
daneben bleiben die geöffneten Angebote und die Befehlssuche (Strg+K findet jeden Menüpunkt).

Nichts geht verloren und nichts wird doppelt angelegt:
- Die bisherigen Menüs bleiben unverändert in der Menüleiste (nur ausgeblendet). Die Themen-Menüs zeigen dieselben
  QAction-Objekte, Tastenkürzel, Rechte und Ein/Aus der Punkte gelten also überall gleich.
- Alt+Buchstabe öffnet das Menü wie bisher (Alt+D Datei, Alt+B Bearbeiten …), unter dem Knopf „Menü“.
- Einstellung leiste_menue = "klassisch" (Ansicht → Klassische Menüleiste) zeigt die alte Menüleiste wieder; nur
  an diesem Arbeitsplatz (leiste_* wird nie abgeglichen).
"""
import re

from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QMenu

EINSTELLUNG = "leiste_menue"
KOMPAKT, KLASSISCH = "kompakt", "klassisch"
MENUE_TEXT = "☰  &Menü"

# Themen des Menüs Datei: erster passender Begriff im Text des Menüpunkts entscheidet (Reihenfolge der Prüfung KI,
# Daten, Auswertung); alles Übrige bleibt unter „Datei“ (Neues Angebot aus STEP, STEP-Viewer, Ablage, Beenden …)
THEMEN = (
    ("KI", ("KI-", "Lernzentrale", "Intelligenz")),
    ("Daten und Abgleich", ("Benutzer", "abgleich", "Abgleich", "Ordner prüfen", "Kollegen", "Arbeitsplatz einrichten",
                            "umziehen", "Sicherung", "Datenbank", "rchiv", "exportieren", "importieren", "Datenordner",
                            "Update")),
    ("Auswertung und Prüfung", ("Auswertung", "Simulator", "Online-Preise", "vergleichen", "prüfen", "Prüf",
                                "Protokoll", "Kostentreiber", "Monatsbericht", "auslastung", "Reklamation", "Schnellpreis",
                                "Referenz")),
)
DATEI_ZUERST = ("STEP-Viewer", "Schnellpreis", "Datensicherung")   # bleiben unter Datei, obwohl ein Begriff passt
REIHENFOLGE = ("Datei", "Bearbeiten", "Kunden", "Daten und Abgleich", "Auswertung und Prüfung", "KI", "Ansicht")


def thema(text):
    """Thema eines Punkts aus dem Menü Datei ('Datei', wenn kein Begriff passt)."""
    t = text.replace("&", "")
    if any(b in t for b in DATEI_ZUERST):
        return "Datei"
    for name, begriffe in THEMEN:
        if any(b in t for b in begriffe):
            return name
    return "Datei"


def _name(menue_aktion):
    return menue_aktion.text().replace("&", "").strip()


class Kopfleiste:
    """Hält den Knopf „Menü“ und die Alt-Tasten; f = Hauptfenster."""

    def __init__(self, f):
        self.f = f
        self.leiste = f.menuBar()
        self.menue = QMenu(self.leiste)
        self.menue.setObjectName("hauptmenue")
        self.knopf = QAction(MENUE_TEXT, self.leiste)
        self.knopf.setMenu(self.menue)
        self.knopf.setToolTip("Alle Menüs (Alt+M); Alt+D, Alt+B … öffnen die Menüs wie bisher")
        # hinten anhängen: actions()[0] bleibt Datei (Tests, Erweiterungen); im kompakten Modus ist der Knopf ohnehin
        # der einzige sichtbare Eintrag
        self.leiste.addAction(self.knopf)
        self.menue.aboutToShow.connect(self.aufbauen)
        self._themen = {}
        self._tasten = []
        self.modus = KOMPAKT
        self._kuerzel_merken()

    # ---------------------------------------------- Inhalt
    def originale(self):
        """Die bisherigen Menüs der Leiste: [(Name, QAction des Menüs)] ohne den Knopf."""
        return [(_name(a), a) for a in self.leiste.actions() if a is not self.knopf and a.menu() is not None]

    def erlaubt(self, a):
        """Menü darf gezeigt werden (z. B. Hauptadmin erst nach der Anmeldung, Eigenschaft erlaubt)."""
        return a.property("erlaubt") is not False

    def aufbauen(self):
        """Menü neu zusammenstellen (bei jedem Öffnen: Menüs anderer Teile, z. B. Hauptadmin, kommen später dazu)."""
        self.menue.clear()
        for m in self._themen.values():
            m.deleteLater()
        self._themen = {}
        datei = next((a.menu() for n, a in self.originale() if n == "Datei"), None)
        gruppen = {}
        if datei is not None:
            trenner = False
            for a in datei.actions():
                if a.isSeparator():
                    trenner = True
                    continue
                name = thema(a.text())
                ziel = gruppen.setdefault(name, [])
                if trenner and ziel and ziel[-1] is not None:
                    ziel.append(None)
                ziel.append(a)
                trenner = False
        for name, aktionen in gruppen.items():
            m = QMenu(name, self.menue)
            for a in aktionen:
                m.addSeparator() if a is None else m.addAction(a)
            self._themen[name] = m
        andere = {n: a.menu() for n, a in self.originale() if n != "Datei" and self.erlaubt(a)}
        namen = [n for n in REIHENFOLGE if n in self._themen or n in andere]
        namen += [n for n in andere if n not in namen and n != "Hilfe"] + (["Hilfe"] if "Hilfe" in andere else [])
        for n in namen:
            if n in self._themen:
                m = self._themen[n]
            else:
                m = self._themen[n] = self._spiegel(n, andere[n])
            if n == "Ansicht" or n == "Hilfe":
                self.menue.addSeparator()
            self.menue.addMenu(m).setVisible(any(x.isVisible() and not x.isSeparator() for x in m.actions()))
        return self.menue

    def _spiegel(self, name, original):
        """Untermenü mit denselben Einträgen (dieselben QAction-Objekte) wie das bisherige Menü. Bewusst kein
        QAction.setMenu(original): das ersetzt in Qt 6 original.menuAction() und bringt Ein/Aus der Leiste durcheinander.
        Beim Öffnen meldet es aboutToShow auch dem Original (z. B. Ansicht setzt dabei seine Haken)."""
        m = QMenu(name, self.menue)

        def fuellen():
            original.aboutToShow.emit()
            m.clear()
            for a in original.actions():
                m.addAction(a)
        m.aboutToShow.connect(fuellen)
        for a in original.actions():
            m.addAction(a)
        return m

    # ---------------------------------------------- Kompakt oder klassisch
    def anwenden(self, modus=None):
        """Kompakt: nur der Knopf „Menü“ in der Leiste; klassisch: die bisherigen Menüs, ohne Knopf."""
        if modus in (KOMPAKT, KLASSISCH):
            self.modus = modus
        kompakt = self.modus == KOMPAKT
        self.knopf.setVisible(kompakt)
        for _n, a in self.originale():
            a.setVisible(not kompakt and self.erlaubt(a))
        for t in self._tasten:
            t.setEnabled(kompakt)
        self.leiste.updateGeometry()
        ecke = self.leiste.cornerWidget()
        if ecke is not None:
            ecke.updateGeometry()
        return self.modus

    def _kuerzel_merken(self):
        """Alt+Buchstabe der bisherigen Menüs (z. B. &Datei = Alt+D) öffnet im kompakten Modus dasselbe Menü."""
        for t in self._tasten:
            t.setParent(None)
        self._tasten = []
        belegt = set()
        for _n, a in self.originale():
            m = re.search(r"&(\w)", a.text())
            if not m or m.group(1).upper() in belegt:
                continue
            buchstabe = m.group(1).upper()
            belegt.add(buchstabe)
            t = QShortcut(QKeySequence(f"Alt+{buchstabe}"), self.f)
            t.activated.connect(lambda a=a: self.zeigen(a.menu()))
            t.setEnabled(self.modus == KOMPAKT)
            self._tasten.append(t)

    def zeigen(self, menue=None):
        """Menü unter dem Knopf „Menü“ öffnen (ohne Angabe das Hauptmenü)."""
        if not self.leiste.isVisible():
            return None
        geo = self.leiste.actionGeometry(self.knopf)
        menue = menue or self.aufbauen()
        menue.popup(self.leiste.mapToGlobal(QPoint(geo.left(), geo.bottom())))
        return menue


def einrichten(f):
    """Kopfleiste am Hauptfenster einrichten (nach dem Aufbau aller Menüs). Ergebnis: Kopfleiste."""
    k = Kopfleiste(f)
    f.kopfleiste = k
    k.anwenden(f.db.einstellung(EINSTELLUNG) or KOMPAKT)
    ansicht = next((a.menu() for n, a in k.originale() if n == "Ansicht"), None)
    if ansicht is not None:
        ansicht.addSeparator()
        k.umschalter = QAction("Klassische Menüleiste (alle Menüs nebeneinander)", f)    # gehört dem Fenster
        k.umschalter.setCheckable(True)
        ansicht.addAction(k.umschalter)
        k.umschalter.setChecked(k.modus == KLASSISCH)
        k.umschalter.toggled.connect(lambda an: umschalten(f, KLASSISCH if an else KOMPAKT))
    return k


def umschalten(f, modus):
    """Ansicht → Klassische Menüleiste: merken (nur dieser Arbeitsplatz) und sofort anwenden."""
    k = getattr(f, "kopfleiste", None)
    if k is None:
        return None
    if not getattr(f.db, "nur_lesen", False):
        f.db.einstellung_setzen(EINSTELLUNG, modus)
    return k.anwenden(modus)


def menue_erlauben(f, menue, an):
    """Menü der Leiste erlauben/verbergen, ohne die Kopfleiste zu stören (ohne Kopfleiste: wie setVisible)."""
    a = menue.menuAction()
    a.setProperty("erlaubt", bool(an))
    k = getattr(f, "kopfleiste", None)
    if k is None:
        a.setVisible(bool(an))
    else:
        k.anwenden()
    return a


def menue_sichtbar(f, menue):
    """Steht das Menü für den Benutzer bereit (Leiste klassisch oder im Knopf „Menü“)? Für Prüfungen statt
    menuAction().isVisible(), das im kompakten Modus immer False ist."""
    a = menue.menuAction()
    k = getattr(f, "kopfleiste", None)
    return a.isVisible() if k is None or k.modus == KLASSISCH else a.property("erlaubt") is not False


def neu_einlesen(f):
    """Nach dem Anlegen weiterer Menüs (z. B. Hauptadmin): Sichtbarkeit und Alt-Tasten auf den neuen Stand."""
    k = getattr(f, "kopfleiste", None)
    if k is not None:
        k._kuerzel_merken()
        k.anwenden()
    return k
