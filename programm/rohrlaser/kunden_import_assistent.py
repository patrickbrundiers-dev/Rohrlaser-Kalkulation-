"""Kundenlisten-CSV-Import als Assistent in 5 Schritten (Master-Auftrag 25.11.2026, gleiche Bedienung wie der
EK-Import, gemeinsamer Rahmen import_assistent): 1 Datei und Format (Modus ergänzen/überschreiben) · 2 Spalten
(deutsch/englisch erkannt, mehrdeutige als Vorschlag, Importprofile) · 3 Prüfung und Dubletten (je Zeile
aktualisieren / neu anlegen / überspringen / manuell zuordnen, Kundennummer für Neukunden von Hand) · 4 Vorschau
(neu, aktualisiert, unverändert, Dubletten, fehlerhaft) · 5 Abschluss (Datensicherung, ein Importlauf, Protokoll,
Fehlerbericht, Rückgängig). Bis Schritt 5 ändert nichts die Datenbank; Kundennummern vorhandener Kunden ändern sich
nie (Angebote und Aufträge bleiben verknüpft)."""
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPushButton

from . import csv_import
from . import import_assistent as IA
from . import kunden_csv as K

GRUPPE_FARBE = {K.G_NEU: IA.GRUEN, K.G_AENDERN: IA.BLAU, K.G_GLEICH: None, K.G_DUBLETTE: IA.GELB,
                K.G_FEHLER: IA.ROT, K.G_UEBERSPRUNGEN: IA.GRAU}
VORSCHLAG = "– bitte wählen –"


def _treffer_text(a, e):
    out = []
    for nr, gruende, _p in e["treffer"][:3]:
        k = a.index_kunden.get(nr) or {}
        out.append(f"{nr} {k.get('name') or ''} ({', '.join(gruende)})")
    return " | ".join(out)


class PruefSchritt(IA.TabellenSchritt):
    """Zeilen, die eine Entscheidung brauchen: mögliche Dubletten, sicher erkannte Kunden (zum Prüfen), neue
    Kunden ohne Kundennummer und fehlerhafte. Option und Kundennummer je Zeile in der Tabelle."""
    titel = "Prüfung und Dubletten"
    SP = ("Zeile", "Firma in der Datei", "Kundennr. (Datei)", "Ergebnis", "Mögliche Treffer", "Entscheidung",
          "Kundennummer", "Hinweis / Fehler")

    def __init__(self, a):
        super().__init__("Prüfung und Dubletten", self.SP, (55, 220, 105, 130, 320, 210, 110),
                         filter_=(K.G_DUBLETTE, K.G_FEHLER, K.G_AENDERN, K.G_NEU))
        self.a = a
        self.neu_k = QPushButton("Neu prüfen")
        self.neu_k.clicked.connect(lambda: self.betreten())
        self.oben.insertWidget(self.oben.count() - 1, self.neu_k)

    def _uebernehmen_aus_tabelle(self):
        """Entscheidungen und Kundennummern aus der Tabelle in den Assistenten (nur was vom Vorschlag abweicht)."""
        for r, e in enumerate(getattr(self, "sichtbar", ())[:self.t.rowCount()]):
            c, feld = self.t.cellWidget(r, 5), self.t.cellWidget(r, 6)
            if c is None:
                continue
            opt, wert = c.currentData(), (feld.text().strip() if feld is not None else "")
            if opt == K.NEU_ANLEGEN:
                if wert and wert != e["kundennr"]:
                    self.a.kundennummern[e["zeile"]] = wert
                elif not wert:
                    self.a.kundennummern.pop(e["zeile"], None)
            ziel = wert if opt in (K.AKTUALISIEREN, K.ZUORDNEN) else None
            if opt is None:
                self.a.entscheidungen.pop(e["zeile"], None)
            elif opt != e["option"] or (ziel and ziel != e.get("ziel")):
                self.a.entscheidungen[e["zeile"]] = (opt, ziel)

    def betreten(self):
        if getattr(self, "sichtbar", None):
            self._uebernehmen_aus_tabelle()
        self.a.neu_rechnen()
        z = K.zaehlen_import(self.a.posten)
        self.kopf.setText(
            f"<b>{z[K.G_NEU]}</b> neu · <b>{z[K.G_AENDERN]}</b> zu aktualisieren · {z[K.G_GLEICH]} unverändert · "
            f"<b style='color:#9A6700'>{z[K.G_DUBLETTE]} mögliche Dubletten</b> (bitte entscheiden) · "
            f"<b style='color:#B42318'>{z[K.G_FEHLER]} fehlerhaft</b>. Ähnliche Namen gelten nie automatisch als "
            "derselbe Kunde. Neue Kunden brauchen eine Kundennummer von Hand (wird nie automatisch vergeben). "
            "Nach Änderungen „Neu prüfen“.")
        self.anzeigen()

    def _liste(self, filt):
        def zeigen(e):
            if e["zeile"] in self.a.entscheidungen or e["zeile"] in self.a.kundennummern:
                return True
            if e["gruppe"] in (K.G_DUBLETTE, K.G_FEHLER):
                return True
            # erkannte Kunden zum Prüfen, außer bei gleicher Kundennummer (eindeutig)
            return e["gruppe"] != K.G_UEBERSPRUNGEN and bool(e["treffer"]) and e["treffer"][0][2] < 1000
        return [e for e in self.a.posten if zeigen(e) and (filt is None or e["gruppe"] == filt)]

    def zeilen(self, filt):
        self.sichtbar = self._liste(filt)
        return ([(e["zeile"], e["name"], (e["roh"][self.a.spalten.zuordnung()["kundennr"]]
                                          if "kundennr" in self.a.spalten.zuordnung() and
                                          self.a.spalten.zuordnung()["kundennr"] < len(e["roh"]) else ""),
                  e["gruppe"], _treffer_text(self.a, e), "", "", "; ".join(e["fehler"] or e["hinweis"]))
                 for e in self.sichtbar], [GRUPPE_FARBE.get(e["gruppe"]) for e in self.sichtbar])

    def anzeigen(self):
        super().anzeigen()
        for r, e in enumerate(self.sichtbar[:self.t.rowCount()]):
            c = QComboBox()
            c.addItem(VORSCHLAG, None)
            for o in K.OPTIONEN:
                c.addItem(o, o)
            hand = self.a.entscheidungen.get(e["zeile"])
            opt = hand[0] if hand else e["option"]
            c.setCurrentIndex(max(0, c.findData(opt)))
            nr = QLineEdit()
            if opt in (K.AKTUALISIEREN, K.ZUORDNEN):
                nr.setText(str((hand[1] if hand and len(hand) > 1 else None) or e.get("ziel") or
                               (e["treffer"][0][0] if e["treffer"] else "")))
            else:
                nr.setText(str(self.a.kundennummern.get(e["zeile"]) or e.get("kundennr") or ""))
            nr.setPlaceholderText("Kundennummer")
            nr.setToolTip("Bei „neu anlegen“: neue Kundennummer von Hand; bei „aktualisieren“ / „zuordnen“: der "
                          "vorhandene Kunde")

            def gewaehlt(_i, c=c, nr=nr, e=e):
                o = c.currentData()
                if o in (K.AKTUALISIEREN, K.ZUORDNEN) and e["treffer"] and not nr.text().strip():
                    nr.setText(e["treffer"][0][0])
                elif o == K.NEU_ANLEGEN and nr.text().strip() in {t[0] for t in e["treffer"]}:
                    nr.clear()
            c.currentIndexChanged.connect(gewaehlt)
            self.t.setCellWidget(r, 5, c)
            self.t.setCellWidget(r, 6, nr)

    def setzen(self, zeile, option, kundennr=None):
        """Entscheidung für eine Dateizeile setzen (wie in der Tabelle; Tests)."""
        for r, e in enumerate(self.sichtbar):
            if e["zeile"] == zeile:
                c = self.t.cellWidget(r, 5)
                c.setCurrentIndex(c.findData(option))
                if kundennr is not None:
                    self.t.cellWidget(r, 6).setText(str(kundennr))
                return True
        return False

    def pruefen(self):
        self.betreten()
        z = K.zaehlen_import(self.a.posten)
        if z[K.G_NEU] + z[K.G_AENDERN] == 0:
            return "Es gibt nichts zu übernehmen (keine neuen und keine zu aktualisierenden Kunden)."
        return ""


class VorschauSchritt(IA.TabellenSchritt):
    titel = "Vorschau"

    def __init__(self, a):
        super().__init__("Vorschau", ("Zeile", "Ergebnis", "Kundennummer", "Firma", "Änderungen", "Hinweis / Fehler"),
                         (55, 130, 105, 230, 420), filter_=K.GRUPPEN)
        self.a = a

    def betreten(self):
        z = K.zaehlen_import(self.a.posten)
        self.kopf.setText(
            f"<b style='color:#2E7D32'>{z[K.G_NEU]} neue Kunden</b> · <b style='color:#1F4E79'>{z[K.G_AENDERN]} "
            f"werden aktualisiert</b> · {z[K.G_GLEICH]} unverändert · {z[K.G_DUBLETTE]} offene Dubletten und "
            f"{z[K.G_FEHLER]} fehlerhafte Zeilen werden nicht übernommen · {z[K.G_UEBERSPRUNGEN]} übersprungen. Modus: "
            f"<b>{self.a.modus.currentText()}</b>. Es wurde noch nichts gespeichert.")
        self.anzeigen()

    def zeilen(self, filt):
        out = [e for e in self.a.posten if filt is None or e["gruppe"] == filt]
        return ([(e["zeile"], e["gruppe"], e["kundennr"], e["name"],
                  "; ".join(f"{K.FELD_TITEL.get(f, f)}: {K._kurz_wert(a)} → {K._kurz_wert(n)}"
                            for f, a, n in e["aenderungen"] if f != "plz_ort") if e["gruppe"] == K.G_AENDERN else
                  ("neuer Kunde" + (f" mit {e['person'].get('vorname') or ''} {e['person'].get('nachname') or ''}"
                                    if e.get("person") else "") if e["gruppe"] == K.G_NEU else ""),
                  "; ".join(e["fehler"] or e["hinweis"])) for e in out],
                [GRUPPE_FARBE.get(e["gruppe"]) for e in out])


class AbschlussSchritt(IA.QWidget):
    titel = "Abschluss"
    knopf = "Importieren"

    def __init__(self, a):
        super().__init__()
        self.a = a
        lay = IA.QVBoxLayout(self)
        self.info = IA.text("")
        lay.addWidget(self.info)
        z = QHBoxLayout()
        self.bericht_k = QPushButton("Fehlerbericht speichern …")
        self.bericht_k.clicked.connect(lambda: self.bericht())
        self.zurueck_k = QPushButton("Diesen Import rückgängig machen")
        self.zurueck_k.setVisible(False)
        self.zurueck_k.clicked.connect(lambda: self.rueckgaengig())
        z.addWidget(self.bericht_k)
        z.addWidget(self.zurueck_k)
        z.addStretch(1)
        lay.addLayout(z)
        lay.addStretch(1)
        self.ergebnis = None

    def betreten(self):
        z = K.zaehlen_import(self.a.posten)
        self.info.setText(
            f"<b>Bereit zum Import</b> von <b>{Path(self.a.pfad).name}</b>:<ul><li>{z[K.G_NEU]} neue Kunden</li>"
            f"<li>{z[K.G_AENDERN]} Kunden werden aktualisiert ({self.a.modus.currentText()})</li>"
            f"<li>{z[K.G_DUBLETTE] + z[K.G_FEHLER]} Zeilen werden nicht übernommen (Fehlerbericht)</li></ul>"
            "Vorher legt das Programm eine Datensicherung an. Kundennummern vorhandener Kunden bleiben, Angebote und "
            "Aufträge bleiben verknüpft. Jede Änderung steht in der Kundenhistorie; der ganze Import lässt sich "
            "rückgängig machen (auch später unter „Letzte Importe“).")

    def abschliessen(self):
        self.ergebnis = K.uebernehmen(self.a.db, self.a.posten, self.a.pfad, self.a.spalten.profilname,
                                      sichern=self.a.sichern, fortschritt=self.a.fortschritt)
        e = self.ergebnis
        self.info.setText(f"<b style='color:#2E7D32'>Import Nr. {e['import_id']} abgeschlossen:</b> {e['neu']} Kunden "
                          f"neu, {e['geaendert']} aktualisiert, {e['personen']} Ansprechpartner, {e['adressen']} "
                          f"Adressen." + (f" Sicherung vorher: {e['sicherung']}" if e.get("sicherung") else ""))
        self.zurueck_k.setVisible(True)
        return e

    def bericht(self, pfad=None):
        inhalt = K.fehlerbericht(self.a.posten, self.a.daten["kopf"])
        p = Path(self.a.pfad)
        return IA.fehlerbericht_speichern(self, inhalt, p.with_name(p.stem + "_Fehlerbericht.csv"), pfad)

    def rueckgaengig(self):
        if not self.ergebnis:
            return None
        n, meldungen = K.rueckgaengig(self.a.db, self.ergebnis["import_id"])
        self.info.setText(f"Import Nr. {self.ergebnis['import_id']} zurückgenommen ({n} Änderungen)."
                          + (" " + "; ".join(meldungen[:5]) if meldungen else ""))
        self.zurueck_k.setVisible(False)
        self.ergebnis = None
        return n, meldungen


class KundenAssistent(IA.Assistent):
    def __init__(self, parent, db, pfad, daten, profilname="", spalten=None, sichern=True):
        self.db, self.pfad, self.daten, self.sichern = db, pfad, daten, sichern
        self.entscheidungen, self.kundennummern, self.posten = {}, {}, []
        self.index_kunden = {}
        self.modus = QComboBox()
        for m in (K.ERGAENZEN, K.UEBERSCHREIBEN):
            self.modus.addItem(m, m)
        self.modus.setCurrentIndex(1 if K.eigener_export(daten["kopf"]) else 0)
        self.modus.setToolTip("Nur leere Felder ergänzen: vorhandene Werte bleiben (Vorgabe für fremde Listen). Werte "
                              "aus der Datei übernehmen: ersetzt vorhandene Werte (Vorgabe für den eigenen Export); "
                              "leere Zellen löschen nie etwas.")
        erkannt = K.spalten_erkennen(daten)
        if spalten:
            erkannt = {f: dict(spalte=i, sicherheit=csv_import.SICHER, grund=f"aus Importprofil „{profilname}“")
                       for f, i in spalten.items()}
        self.datei = IA.DateiSchritt(pfad, daten, profilname, zusatz=(("Vorhandene Kunden", self.modus),),
                                     laeufe=lambda: csv_import.laeufe(db, csv_import.ART_KUNDEN),
                                     rueckgaengig=lambda i: K.rueckgaengig(db, i))
        self.spalten = IA.SpaltenSchritt(db, K.IMPORTPROFILE, [(f, K.FELD_TITEL.get(f, t)) for f, t in K.FELDER], K.IMPORT_PFLICHT, daten, erkannt, profilname,
                                         hinweis="Grün = sicher erkannt, gelb = Vorschlag (bitte prüfen, z. B. "
                                         "„Name“: Firma oder Person?), weiß = nicht zugeordnet. Fehlende Felder "
                                         "blockieren den Import nicht; nötig ist nur der Firmenname *.")
        self.pruef = PruefSchritt(self)
        self.vorschau_s = VorschauSchritt(self)
        self.abschluss = AbschlussSchritt(self)
        super().__init__(parent, f"Kunden importieren: {Path(pfad).name}",
                         (self.datei, self.spalten, self.pruef, self.vorschau_s, self.abschluss))

    def neu_rechnen(self):
        self.posten = K.analysieren(self.db, self.daten, self.spalten.zuordnung(), modus=self.modus.currentData(),
                                    entscheidungen=self.entscheidungen, kundennummern=self.kundennummern,
                                    fortschritt=lambda i, n: self.fortschritt(i, n, "Kunden prüfen"))
        self.fortschritt(1, 1)
        self.index_kunden = {str(k.get("kundennr")): k for k in self.db.zeilen("kunden")}
        return self.posten


def assistent(seite, db, pfad, sichern=True):
    """Kunden-Assistent zur Datei bauen (nicht zeigen): lesen, passendes Importprofil, sonst Erkennung."""
    roh = Path(pfad).read_bytes()
    daten = K.lesen(roh, str(pfad))
    name, _profil, sp = csv_import.profil_passend(csv_import.profile(db, K.IMPORTPROFILE), daten["kopf"])
    return KundenAssistent(seite, db, str(pfad), daten, name or "", sp, sichern=sichern)

