"""Ausgaben der Angebotsseite (Technik V6, 31.10.2026: aus angebot_fenster.py herausgelöst, damit die große Datei
kleiner wird und parallele Änderungen seltener aneinanderstoßen): Angebots-PDF, Angebot per E-Mail,
Auftragsbestätigung, Werkstattpapiere, Etiketten, Kalkulation, CSV-Export, Material je Abmessung, Materialanfrage.

AusgabeMixin wird von angebot_fenster.AngebotSeite geerbt; die Methoden nutzen deren Attribute (db, kopf, positionen,
ergebnis, k, tabellen, einst, f …). Verhalten unverändert."""
import datetime
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from . import abmessung, angebot_check, ausgabe, baugruppe, export, materialanfrage, pdf, plausibel, rechnen, teilen
from . import nummern as angebotsnummern
from .angebot import aktiv as position_aktiv, kein_laserteil


def preis_aenderung(vorher, nachher):
    from .angebot_fenster import preis_aenderung as p     # angebot_fenster lädt dieses Modul
    return p(vorher, nachher)


class AusgabeMixin:
    # -------------------------------------------------------------- Ausgabe (PDF, CSV)
    def _vor_ausgabe(self, pruefen=False, weiter="Weiter"):
        """Vor einer Ausgabe (Plan W7, eine Sammelrückfrage): veralteten Schnittplan ohne Rückfrage neu optimieren
        (ein Schnittplan, der nicht zum Angebot passt, ergäbe falschen Materialbedarf, B-10), dann höchstens eine
        Rückfrage. pruefen = ganzer Angebots-Check (Angebots-PDF, Verschickt), sonst nur die Fracht. Ergebnis: True =
        weiter; die Begründung beim Übergehen eines FEHLERS steht danach in self.check_uebergangen."""
        self.check_uebergangen = None
        if self.stand_optimierung() != "aktuell":
            if not self.optimieren(automatisch=self.f.stumm):
                return False
        punkte = self.freigabe_punkte()
        if not pruefen:
            punkte = [p for p in punkte if p.ziel == "fracht"]
        if not angebot_check.offen(punkte):
            return True
        if self.f.stumm:                        # Tests: Punkte melden, nicht fragen
            self.f.meldung("Angebots-Check: " + "; ".join(p.text for p in angebot_check.offen(punkte)), fehler=True)
            self.check_uebergangen = angebot_check.versand_eintrag(punkte, "")
            return True
        ok, begruendung = self.check_zeigen(weiter, punkte)
        if ok:
            self.check_uebergangen = angebot_check.versand_eintrag(punkte, begruendung)
        return ok

    def _ziel(self, zusatz, endung, mit_kunde=False):
        try:
            return self.f.angebot_ordner(self.kopf) / (ausgabe.dateiname(self.kopf, zusatz, mit_kunde) + endung)
        except OSError as e:
            QMessageBox.warning(self, "Ablage", f"Der Ordner des Angebots lässt sich nicht anlegen:\n{e}")
            return None

    def _schreiben(self, art, pfad, schreiben, oeffnen=True):
        """Datei schreiben und öffnen (oeffnen=False: nur schreiben). Ergebnis: Pfad oder None."""
        if pfad is None:
            return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            schreiben(pfad)
        except PermissionError:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, art, f"Die Datei konnte nicht gespeichert werden:\n{pfad}\n\n"
                                "Ist sie noch in einem anderen Programm geöffnet?")
            return None
        QApplication.restoreOverrideCursor()
        self.f.meldung(f"{art} gespeichert: {pfad}")
        if oeffnen:
            self.f.datei_oeffnen(pfad)
        return pfad

    def angebot_daten(self, staffeln=True):
        """Inhalt des Angebots mit aktuellen Staffelpreisen (None = abgebrochen); staffeln=False: ohne."""
        sp = self.staffelpreise_aktuell() if staffeln else ()
        if sp is None:
            return None
        zeilen, _ = self._rechnung()
        ang = ausgabe.angebot(self.kopf, self.positionen, zeilen, self.k, self.einst, sp, ergebnis=self.ergebnis)
        ang["anschrift"] = ausgabe.anschrift(self.db.kunde(self.kopf.get("kundennr")))
        ang["ansprechpartner"] = teilen.mitarbeiter(self.db, self.kopf["bearbeiter"]) if self.kopf.get("bearbeiter") else {}
        return ang

    def angebot_pdf(self, oeffnen=True, daten=None):
        """Angebots-PDF schreiben (oeffnen=False: nicht anzeigen), im Versandverlauf merken. daten = {} bekommt
        'netto'. Ergebnis: Pfad oder None."""
        if not self.nummer_endgueltig("Angebots-PDF"):
            return None
        if not any(position_aktiv(p) for p in self.positionen):
            self.f.meldung("Das Angebot hat keine Positionen.", fehler=True)
            return None
        # Angebots-Check (Plan A2/W7): eine Sammelrückfrage, nur wenn FEHLER oder WARNUNG offen sind
        if not self._vor_ausgabe(pruefen=not self.fremd(), weiter="Angebot erstellen"):
            return None
        uebergangen = self.check_uebergangen
        ang = self.angebot_daten()
        if ang is None:
            return None
        pfad = self._schreiben("Angebot", self._ziel("Angebot", ".pdf"),
                               lambda p: pdf.angebot_pdf(p, self.kopf, ang, self.einst), oeffnen)
        if daten is not None:
            daten["netto"] = ang.get("netto")
        if pfad is not None and not self.fremd():     # Angebot eines Kollegen: nur ansehen, nichts festschreiben
            self.preise_festschreiben()
            eintrag = dict(datum=datetime.date.today().isoformat(), netto=ang["netto"], datei=Path(pfad).name)
            zeilen, _ = self._rechnung()        # Preis je kg je Position für die Plausibilität späterer Angebote
            eintrag["kennwerte"] = plausibel.kennwerte(self.positionen, zeilen, self.k)
            if uebergangen:
                eintrag["check"] = uebergangen
            self.db.versand_merken(self.id, eintrag)
            if not (self.db.angebot(self.id) or {}).get("vorgang"):     # Entwurf -> Verschickt (sonst bleibt er)
                self.db.vorgang_setzen(self.id, "Verschickt")
                self.f.angebote.neu_laden()
        return pfad

    def angebot_mail(self, dialog=None, ausfuehren=None):
        """Angebot per E-Mail (Vorschlag V1, 31.10.2026): Angebots-PDF erstellen, dann Fenster mit Empfänger, Betreff
        und Text; „In Outlook öffnen“ (als Antwort auf die Anfrage-Mail, wenn sie als .msg im Angebotsordner liegt)
        oder E-Mail-Datei. Vermerk im Versandverlauf (art 'mail'). dialog(d) bedient das Fenster statt exec,
        ausfuehren ersetzt den Outlook-Aufruf (Tests)."""
        from . import angebot_mail
        from . import mail as mail_
        from .angebot_mail_dialog import AngebotMailDialog
        if self.fremd():
            self.f.meldung("Angebot per E-Mail nur für eigene Angebote.", fehler=True)
            return None
        daten = {}
        pfad = self.angebot_pdf(oeffnen=False, daten=daten)
        if pfad is None:
            return None
        try:
            ordner = self.f.angebot_ordner(self.kopf)
        except OSError:
            ordner = Path(pfad).parent
        anfrage = None
        for p in angebot_mail.anfrage_mails(ordner):
            m = mail_.lesen(p)
            if m is not None:
                anfrage = (p, m)
                break
        d = AngebotMailDialog(self, self.kopf, self.db.kunde(self.kopf.get("kundennr")), self.einst, pfad, anfrage,
                              self._ziel("Angebot E-Mail", ".eml"), self.f.datei_oeffnen, ausfuehren,
                              netto=daten.get("netto"))
        (dialog(d) if dialog else d.exec())
        if d.eintrag:
            self.db.versand_merken(self.id, d.eintrag)
            self.kopf["versand"] = (self.db.angebot(self.id) or {}).get("versand") or []
        if d.meldung:
            self.f.meldung(d.meldung)
        return d

    def auftragsbestaetigung_pdf(self, abweichung_ok=None):
        """Auftragsbestätigung als PDF (Plan 29.10.2026 1c): Layout und Preise des Angebots (festgeschrieben),
        bestellte Mengen ohne Staffelpreise, Bestellnummer und Liefertermin aus „Beauftragt“. Noch nicht beauftragt:
        Rückfrage, dann Vorgang Beauftragt. Weicht die Summe vom zuletzt verschickten Angebot ab, fragt das Programm
        nach (abweichung_ok: Antwort ohne Fenster). Vermerk im Versandverlauf (art 'ab') mit der AB-Nummer."""
        if self.fremd():
            self.f.meldung("Auftragsbestätigungen nur für eigene Angebote.", fehler=True)
            return None
        if not self.nummer_endgueltig("Auftragsbestätigung"):
            return None
        if not any(position_aktiv(p) for p in self.positionen):
            self.f.meldung("Das Angebot hat keine Positionen.", fehler=True)
            return None
        kopf = self.db.angebot(self.id) or {}
        if kopf.get("vorgang") != "Beauftragt":
            if self.f.stumm:
                self.f.meldung("Auftragsbestätigung: das Angebot ist noch nicht beauftragt.", fehler=True)
                return None
            if QMessageBox.question(self, "Auftragsbestätigung", "Das Angebot ist noch nicht beauftragt.\n\nJetzt "
                                    "als beauftragt markieren (Bestellnummer und Liefertermin) und die "
                                    "Auftragsbestätigung erstellen?") != QMessageBox.Yes:
                return None
            if not self.f.angebote.vorgang_setzen("Beauftragt", angebot_id=self.id):
                return None
            kopf = self.db.angebot(self.id) or {}
        if not self._vor_ausgabe(weiter="Auftragsbestätigung erstellen"):
            return None
        ang = self.angebot_daten(staffeln=False)
        if ang is None:
            return None
        verschickt = [e for e in kopf.get("versand") or () if isinstance(e, dict) and not e.get("art")
                      and e.get("netto") is not None]
        if verschickt and abs(verschickt[-1]["netto"] - ang["netto"]) > 0.005:
            frage = (f"Die Summe weicht vom zuletzt verschickten Angebot ab:\n\nAngebot "
                     f"{ausgabe.datum_text(verschickt[-1].get('datum'))}: {ausgabe.euro_text(verschickt[-1]['netto'])} € "
                     f"netto\nAuftragsbestätigung: {ausgabe.euro_text(ang['netto'])} € netto\n\nTrotzdem erstellen?")
            if abweichung_ok is None:
                abweichung_ok = not self.f.stumm and QMessageBox.question(
                    self, "Auftragsbestätigung", frage) == QMessageBox.Yes
            if not abweichung_ok:
                return None
        try:
            nr = angebotsnummern.ab_nummer(self.db, kopf)
        except OSError as e:
            QMessageBox.warning(self, "Auftragsbestätigung", f"Keine AB-Nummer: {e}")
            return None
        ab = dict(nummer=nr, datum=datetime.date.today().isoformat(), bestellung=kopf.get("auftragsnr"),
                  liefertermin=kopf.get("liefertermin"), text=self.einst.get("ab_text") or "")
        pfad = self._schreiben("Auftragsbestätigung", self._ziel("Auftragsbestätigung", ".pdf"),
                               lambda p: pdf.auftragsbestaetigung_pdf(p, self.kopf, ang, self.einst, ab))
        if pfad is not None:
            self.db.versand_merken(self.id, dict(art="ab", datum=ab["datum"], nummer=nr, netto=ang["netto"],
                                                 datei=Path(pfad).name))
            self.kopf["versand"] = (self.db.angebot(self.id) or {}).get("versand")
            self.f.meldung(f"Auftragsbestätigung {nr} erstellt.")
        return pfad

    def reklamation_erfassen(self, dialog=None):
        """Reklamation zu diesem Auftrag (reklamation_dialog.erfassen); die Nachkalkulation zeigt die Kosten gleich
        mit und speichert sie, wenn schon Ist-Werte erfasst sind. Ergebnis: id oder None."""
        from . import reklamation_dialog
        i = reklamation_dialog.erfassen(self.f, self.id, self, dialog)
        if i is not None:
            self._nachkalk.neu_laden()
            if self.kopf.get("nachkalkulation") and not self.db.nur_lesen:
                self._nachkalk._speichern()
        return i

    def etiketten_pdf(self, dialog=None):
        """Etiketten mit QR-Code je Position (etiketten_dialog.drucken). Ergebnis: Pfad oder None."""
        if not self.nummer_endgueltig("Etiketten"):
            return None
        from . import etiketten_dialog
        return etiketten_dialog.drucken(self.f, self.id, self, dialog)

    def preise_festschreiben(self):
        """Materialpreise und Schneiddaten, mit denen das Angebot gerade rechnet, im Angebot speichern (nach dem
        Angebots-PDF). Schon festgeschriebene Werte bleiben, neue Profile, Werkstoffe und Oberflächen kommen dazu."""
        pb = rechnen.preisbasis_aus(self.kopf, self.positionen, self.k, self.tabellen)
        # Nettosumme und Datum des verschickten Angebots: spätere Änderungen zeigt die Übersicht als Abweichung
        verkauf = self._verkauf()
        pb["verschickt"] = dict(netto=round(verkauf, 2), datum=pb["datum"]) if verkauf is not None else None
        alt = self.kopf.get("preisbasis")
        if isinstance(alt, dict) and rechnen.preisbasis_gleich(alt, pb) and alt.get("verschickt") == pb["verschickt"]:
            return
        self.db.preisbasis_speichern(self.id, pb)
        self.neu_laden()

    def preise_aktualisieren(self):
        """Festgeschriebene Preise auf die aktuellen Stammdaten setzen: ohne Rückfrage, mit „Rückgängig“ und der
        Liste der Abweichungen im Bericht (Plan Bedienung B2)."""
        abw = rechnen.preisbasis_abweichung(self.kopf, self.k_aktuell, self.tabellen_aktuell)
        vorher = self._verkauf()
        self.db.preisbasis_speichern(self.id, None)
        self.neu_laden()
        self.rueckgaengig_anbieten(
            f"Aktuelle Materialpreise und Schneiddaten übernommen. {preis_aenderung(vorher, self._verkauf())}",
            bericht=("Aktuelle Preise übernehmen", "Geänderte Preisgrundlagen:\n" + "\n".join(abw) + "\n\nEin bereits "
                     "verschicktes Angebots-PDF bleibt unverändert; erst das nächste Angebots-PDF schreibt die neuen "
                     "Preise wieder fest."))
        return True

    def werkstatt_pdf(self, gruppe=None):
        """Werkstattpapiere als PDF; gruppe = Abmessung aus dem Material-Fenster (rechnen.material_abmessungen): nur
        deren Stangen, Datei '<Nr> Werkstattpapiere <Profil>'."""
        if not self._vor_ausgabe():
            return None
        nur_bg = not (self.ergebnis and self.ergebnis["stangen"]) and baugruppe.baugruppen(self.positionen) and \
            not any(not kein_laserteil(p) for p in self.positionen)        # nur Baugruppen und Zukaufteile
        if not nur_bg and (not self.ergebnis or not self.ergebnis["stangen"]):
            self.f.meldung("Der Schnittplan ist leer. Bitte zuerst optimieren.", fehler=True)
            return None
        erg = self.ergebnis if self.ergebnis else rechnen.optimieren(self.kopf, self.positionen, self.k, self.tabellen,
                                                                     self.einst)
        name = "Werkstattpapiere"
        if gruppe is not None:
            erg = dict(erg, stangen=[s for s in erg["stangen"] if abmessung.gruppe_der_stange(s) == gruppe["gruppe"]])
            name += f" {gruppe['profil']}"
        wp = ausgabe.werkstatt(self.kopf, self.positionen, erg, self.k, self.tabellen)
        if gruppe is not None:          # nur der Schnittplan dieser Abmessung: ohne Zukaufteile und Schweißpläne
            wp = dict(wp, zukaufteile=[], schweissplan=[])
        elif self.kopf.get("vorgang") == "Beauftragt" and self.f.versand_an() and \
                self.db.einstellung("palettenschein_werkstatt") == "ja":
            from . import palettenschein        # Palettenscheine hinten anhängen (Plan Palettenbegleitschein F8a)
            z = palettenschein.zusammenstellen(self.db, self.id)
            wp = dict(wp, palettenscheine=palettenschein.seiten(z["kopf"], z["schein"], z["packliste"], z["gruppen"]))
        if gruppe is None:              # Montageblätter der Sätze und Baugruppen mit Steckverbindungen (A7)
            wp = dict(wp, montage=self.montageblaetter())
        wp = dict(wp, freigabe=self.freigabe_stand())
        aktuell = self.stand_optimierung() == "aktuell"
        return self._schreiben("Werkstattpapiere", self._ziel(name, ".pdf"),
                               lambda p: pdf.werkstatt_pdf(p, self.kopf, wp, aktuell, self.einst))

    def freigabe_stand(self):
        """Freigegebener Auftragsstand für die Werkstattpapiere (fertigung.stand_text) mit Positionen und stabilen IDs;
        None ohne Freigabe."""
        from . import fertigung
        if not self.f.fertigung_an():
            return None
        text, warnung = fertigung.stand_text(self.db, self.id, self.db.angebot(self.id), self.db.positionen(self.id))
        if not text:
            return None
        return dict(text=text, warnung=warnung, positionen=[
            dict(id=p["id"], pos=p.get("pos"), artikel=p.get("artikel"), bezeichnung=p.get("bezeichnung"),
                 stueck=p.get("stueck")) for p in self.positionen])

    def montageblaetter(self):
        """Montageblätter der Werkstattpapiere (A7): je Schweißbaugruppe und je Satz mit Steckverbindungen und Stößen
        aus der STEP-Datei die Montagefolge (steck_montage.montage_folge) mit Titel."""
        from . import satz3d, steck_montage as sm
        from .ansicht3d import entpacken
        roh = self.db.netze(self.id)
        netze = {}

        def netz(pid):
            if pid not in netze:
                netze[pid] = entpacken(roh.get(pid)) or {}
            return netze[pid]
        out = []

        def blatt(titel, idx, daten, stoesse):
            verb = satz3d.verbindungen_laden(daten, self.positionen, idx)
            if not verb or not stoesse:
                return
            pos = {self.positionen[i]["id"]: self.positionen[i] for i in idx}
            f = sm.montage_folge(pos, verb, stoesse, {pid: netz(pid) for pid in pos if pid in roh})
            if f:
                out.append(dict(f, titel=titel))
        for bg_id, (i, bg) in baugruppe.baugruppen(self.positionen).items():
            p = self.positionen[i]
            blatt(f"Schweißbaugruppe Pos. {p.get('pos') or ''} {baugruppe.name(p, bg)}",
                  baugruppe.teile(self.positionen, bg_id), bg, bg.get("stoesse"))
        satz_daten = self.db.satz_daten(self.id)
        for satz in satz3d.saetze(self.positionen):
            daten = satz_daten.get(satz) or {}
            blatt(f"Satz {satz}", satz3d.satz_teile(self.positionen, satz), daten, daten.get("stoesse"))
        return out

    def kalkulation_pdf(self):
        if not self._vor_ausgabe():
            return None
        zeilen, summen = self._rechnung()
        aktuell = self.stand_optimierung() == "aktuell"
        material = rechnen.material_abmessungen(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen)
        muster = ausgabe.werkstatt(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen)["muster"] \
            if self.ergebnis and self.ergebnis.get("stangen") else None
        # Kalkulations-PDF 30.10.2026: gespeicherte Staffeln (nicht neu rechnen), Warnungen der Preis-Gegenprobe,
        # Maschine für den Rechenweg des ermittelten Stundensatzes
        staffel = (self.kopf.get("staffelpreise") or {}).get("zeilen") if self.stufen else None
        plausi = plausibel.punkte(self.positionen, zeilen, summen, self.k, self._preis_vergleich())
        maschine = self.k.maschinen.get(self.kopf.get("maschine"))
        return self._schreiben("Kalkulation", self._ziel("Kalkulation", ".pdf"),
                               lambda p: pdf.kalkulation_pdf(p, self.kopf, zeilen, summen, self.einst, aktuell,
                                                             material, muster, self.k.profile,
                                                             rechnen.laser_hinweise(self.positionen, self.k),
                                                             positionen=self.positionen, staffel=staffel,
                                                             plausi=plausi, maschine=maschine))

    CSV_ARTEN = {"kopf": "Angebotskopf", "positionen": "Angebotspositionen", "baugruppen": "Schweissbaugruppen"}

    def csv_export(self, art="alle", ordner=None):
        """CSV-Export als einzelne Dateien ('<Nr> Angebotskopf.csv', '<Nr> Angebotspositionen.csv', mit Baugruppen
        '<Nr> Schweissbaugruppen.csv'); art 'alle', 'kopf' oder 'positionen'. Den Ordner wählt der Bediener (Start:
        zuletzt gewählter Ordner, sonst Ordner des Angebots); ordner setzt ihn ohne Dialog, ohne Rückfragen (stumm)
        gilt der Ordner des Angebots. Der Export wird im Versandverlauf vermerkt (Schritt „Verschickt“ erst danach
        grün). Ergebnis: Liste der Pfade (art 'alle') bzw. Pfad, None bei Abbruch oder Fehler."""
        def fehler(text):
            QApplication.restoreOverrideCursor()
            if self.f.stumm:
                self.f.meldung("CSV-Export: " + text.replace("\n", " "), fehler=True)
            else:
                QMessageBox.warning(self, "CSV-Export", text)
            return None

        if not self._vor_ausgabe():
            return None
        if not any(position_aktiv(p) for p in self.positionen):
            return fehler("Das Angebot hat keine Positionen.")
        try:
            angebot_ordner = self.f.angebot_ordner(self.kopf)
        except OSError as e:
            return fehler(f"Der Ordner des Angebots lässt sich nicht anlegen:\n{e}")
        if ordner is None and not self.f.stumm:
            zuletzt = self.db.einstellung("csv_ordner")
            start = zuletzt if zuletzt and Path(zuletzt).is_dir() else str(angebot_ordner)
            ordner = QFileDialog.getExistingDirectory(self, "CSV-Export: Ordner wählen", start)
            if not ordner:
                return None
            self.db.einstellung_setzen("csv_ordner", ordner)
        ziel = Path(ordner) if ordner else angebot_ordner
        QApplication.setOverrideCursor(Qt.WaitCursor)
        geschrieben = []
        try:
            zeilen, summen = self._rechnung()
            bearbeiter = self.kopf.get("bearbeiter")
            kopfzeile, pos_zeilen = export.daten(
                self.kopf, self.positionen, self.ergebnis, zeilen, summen, self.k, self.tabellen, self.einst,
                kunde=self.db.kunde(self.kopf.get("kundennr")),
                ersteller=teilen.mitarbeiter(self.db, bearbeiter).get("name") if bearbeiter else None)
            arten = ["kopf", "positionen"] if art == "alle" else [art]
            bg_zeilen = export.baugruppen_zeilen(self.positionen, zeilen) if art == "alle" else None
            if bg_zeilen:
                arten.append("baugruppen")
            for a in arten:
                pfad = ziel / (ausgabe.dateiname(self.kopf, self.CSV_ARTEN[a]) + ".csv")
                if a == "kopf":
                    export.kopf_csv(pfad, kopfzeile)
                elif a == "positionen":
                    export.positionen_csv(pfad, pos_zeilen)
                else:
                    export.baugruppen_csv(pfad, bg_zeilen)
                geschrieben.append(pfad)
        except PermissionError:
            return fehler(f"Die Datei konnte nicht gespeichert werden:\n{pfad}\n\n"
                          "Ist sie noch in einem anderen Programm geöffnet?")
        except (OSError, ValueError) as e:
            return fehler(f"Der Export ist nicht gelungen:\n{ziel}\n\n{e}")
        QApplication.restoreOverrideCursor()
        if not self.db.nur_lesen and not self.fremd():      # Vermerk für die Schrittanzeige (Patrick 24.10.2026)
            self.db.versand_merken(self.id, dict(art="csv", datum=datetime.date.today().isoformat(),
                                                 datei=", ".join(p.name for p in geschrieben), ordner=str(ziel)))
            self.kopf["versand"] = (self.db.angebot(self.id) or {}).get("versand") or []
            self._schritte_setzen()
        self.f.meldung(f"CSV-Export gespeichert in {ziel}: " + ", ".join(p.name for p in geschrieben)
                       + f" ({len(pos_zeilen)} Positionen)")    # Einblendung (L14)
        return geschrieben if art == "alle" else geschrieben[0]

    def csv_kopf(self, ordner=None):
        return self.csv_export("kopf", ordner)

    def csv_positionen(self, ordner=None):
        return self.csv_export("positionen", ordner)

    # -------------------------------------------------------------- Material je Abmessung
    def material_einstellen(self, dialog=None):
        """Fenster 'Material …': Materialeinsatz und Materialwerte je Abmessung (Werkstoff, Oberfläche, Lieferlänge, Eigen-/
        Kundenmaterial, Meterpreis) und Handling Kundenmaterial; Änderungen werden an allen Positionen der Abmessung
        gespeichert und gehen so in die Kalkulation ein. Doppelklick und Kontextmenü öffnen die Zusatzfenster
        (abmessung_fenster.py); Schritte, die das Fenster schließen (zur Position, Positionen markieren, neu
        optimieren, 12-m-Vergleich, Materialanfrage), laufen danach (d.nachher, _material_nachher). dialog(d) bedient
        das Fenster statt exec (Tests). Ergebnis: Anzahl geänderter Abmessungen bzw. Werte oder None (nichts zu
        zeigen)."""
        from .meterpreis_dialog import MeterpreisDialog
        gruppen = rechnen.material_abmessungen(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen)
        if not gruppen:
            self.f.meldung("Material: keine Position mit Profil und Werkstoff im Angebot.", fehler=True)
            return None
        ohne_plan = not self.ergebnis or not self.ergebnis.get("stangen")
        d = MeterpreisDialog(self, gruppen, self.k, self.kopf,
                             lambda g: [z["laenge"] for z in rechnen.lieferlaengen(g["profil"], g["werkstoff"], self.k,
                                                                                   self.tabellen, auto=False)
                                        if rechnen._n(z.get("laenge")) > 0],
                             self.einst, veraltet=not ohne_plan and self.stand_optimierung() != "aktuell",
                             ohne_plan=ohne_plan, seite=self)
        if not (dialog(d) if dialog else d.exec() == QDialog.Accepted):
            return 0
        n = len(d.aenderungen) + len(d.kopf_aenderungen) + (d.vorgaben is not None)
        if n:
            self._material_speichern(d)
        if d.nachher:
            self._material_nachher(*d.nachher)
        return n

    def _material_speichern(self, d):
        n = len(d.aenderungen) + len(d.kopf_aenderungen) + (d.vorgaben is not None)
        vorher = self._verkauf()
        if d.vorgaben is not None:      # von Hand vorgegebene Stangen (Patrick 26.10.2026)
            self.db.stangen_vorgabe_speichern(self.id, d.vorgaben)
        for g, felder in d.aenderungen:
            for pid in g["ids"]:
                for feld, wert in felder.items():
                    self.db.position_aendern(pid, feld, wert)
        for feld, wert in d.kopf_aenderungen.items():
            self.db.angebot_aendern(self.id, feld, wert)
        self.neu_laden()
        plan = any(set(f) & {"werkstoff_id", "oberflaeche", "stange", "material_herkunft"} for _, f in d.aenderungen)
        self.f.meldung(f"Material: {n} Änderung(en) gespeichert. {preis_aenderung(vorher, self._verkauf())}"
                       + (" Werkstoff, Lieferlänge, Oberfläche oder Material geändert: bitte neu optimieren." if plan else
                          " Vorgegebene Stangen geändert: bitte neu optimieren." if d.vorgaben is not None else ""))

    def _material_nachher(self, aktion, wert=None):
        """Schritt aus dem Material-Fenster, nachdem es geschlossen ist: 'position' (wert = Bezug ref), 'markieren'
        (wert = Abmessung: alle ihre Positionen markieren), 'optimieren', 'laengen' (wert = Indizes im Vergleich der
        Lieferlängen), 'anfrage' (wert = Abmessung). Ergebnis wie die aufgerufene Methode."""
        if aktion == "position":
            return self.zur_position(ref=wert)
        if aktion == "markieren":
            zeilen = [r for r, p in enumerate(self.positionen) if p.get("id") in set(wert["ids"])]
            if not zeilen:
                return None
            self.zur_position(zeile=zeilen[0])
            auswahl = self.pos_ansicht.selectionModel()
            for r in zeilen[1:]:
                auswahl.select(self.pos_modell.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
            self.f.meldung(f"{wert['profil']}: {len(zeilen)} Position(en) markiert.")
            return zeilen
        if aktion == "optimieren":         # danach das Material-Fenster mit dem neuen Schnittplan wieder zeigen
            ok = self.optimieren()
            if ok and not self.f.stumm:
                self.material_einstellen()
            return ok
        if aktion in ("laengen", "anfrage") and self.stand_optimierung() != "aktuell":
            # z. B. gerade Werkstoff oder Lieferlänge geändert: Vergleich und Bedarf kämen aus dem alten Schnittplan
            self.f.meldung("Der Schnittplan passt nicht mehr zum Angebot: bitte zuerst neu optimieren.", fehler=True)
            return None
        if aktion == "laengen":
            return self.laengen_zeigen(wert)
        if aktion == "anfrage":
            return self.material_anfragen(gruppe=wert)
        return None

    # -------------------------------------------------------------- Materialanfrage
    def material_anfragen(self, dialog=None, ausfuehren=None, gruppe=None):
        """Materialanfrage an den Lieferanten (Dialog): Bedarf aus der Optimierung, Lieferant und Text prüfen, dann 'In Outlook öffnen' (gesendet wird nur in Outlook) oder 'Als E-Mail-Datei speichern'.
        dialog(d) bedient den Dialog statt exec, ausfuehren ersetzt den Outlook-Aufruf (Tests). gruppe = nur diese
        Abmessung (Material-Fenster, rechnen.material_abmessungen)."""
        from .materialanfrage_dialog import AnfrageDialog
        if not self.nummer_endgueltig("Materialanfrage"):
            return None
        if not self.ergebnis or not self.ergebnis.get("stangen"):
            self.f.meldung("Materialanfrage: bitte zuerst optimieren (der Stangenbedarf kommt aus der Optimierung).",
                           fehler=True)
            return None
        werte = rechnen.stangen_werte(self.ergebnis, self.kopf, self.positionen, self.k, self.tabellen)
        erg = self.ergebnis
        if gruppe is not None:
            paare = abmessung.lieferstangen(erg, gruppe["gruppe"], werte)
            erg, werte = dict(erg, stangen=[s for s, _ in paare]), [w for _, w in paare]
        from . import lager
        aus_lager = lager.aus_lager(self.db, self.id, self.ergebnis) if self.f.lager_an() else set()
        if aus_lager:               # Stangen aus dem Lager (reserviert) nicht anfragen
            paare = [(s, w) for s, w in zip(erg["stangen"], werte) if s["nr"] not in aus_lager]
            erg, werte = dict(erg, stangen=[s for s, _ in paare]), [w for _, w in paare]
            self.f.meldung(f"Materialanfrage: {len(aus_lager)} Stange(n) kommen aus dem Lager und werden nicht "
                           "angefragt.")
        zeilen = materialanfrage.bedarf(self.positionen, erg, self.k, self.tabellen, werte, self.kopf)
        if not zeilen:
            self.f.meldung("Materialanfrage: kein Eigenmaterial im Angebot (Kundenmaterial wird nicht angefragt).",
                           fehler=True)
            return None
        vorher = self.kopf.get("naht_stangen")
        d = AnfrageDialog(self, self.kopf, zeilen, self.k, self.einst,
                          materialanfrage.lieferanten(self.db.zeilen("zukauf_lieferanten")),
                          self._ziel("Materialanfrage", ".eml"), self.f.datei_oeffnen, ausfuehren,
                          lambda profil, werkstoff, seite: self.naht_stange_setzen({(profil, werkstoff)}, seite,
                                                                                   laden=False))
        (dialog(d) if dialog else d.exec())
        if self.kopf.get("naht_stangen") != vorher:     # Nahtlage geändert: Status der Positionen neu prüfen
            self.neu_laden()
        if d.meldung:
            self.f.meldung(d.meldung)
        return d
