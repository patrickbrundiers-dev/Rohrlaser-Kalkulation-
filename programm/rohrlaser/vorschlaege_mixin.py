"""Angebotsfenster: Aktionen der Vorschläge vom 02.11.2026 (F5/F6 Lieferschein und Werkszeugnisse, G1 Zielpreis,
G4/G5/J1 Hinweise im Angebots-Check, H2 Vier-Augen-Freigabe, H5 Rückfrage an den Kunden, H6 Positionsvorlagen,
J5 Losgröße, J6 Neuteile). Teil von AngebotSeite (angebot_fenster.py); die Rechnung steht in den Modulen
kalk_hinweise, preisschicht, lieferschein, freigabe, rueckfrage und positionsvorlagen."""
import datetime
import json
import os

from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QInputDialog, QLabel,
                               QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import funktionen, rechnen
from .stammdaten import zahl_als_text as zahl


def _kopf_feld(name):
    from .angebot import KOPF
    return next(f for f in KOPF if f.name == name)


class VorschlaegeMixin:
    # ------------------------------------------------------------------ J6 Neuteile
    def neuteile_aktualisieren(self, treffer):
        """Neuteile = Positionen ohne beauftragtes Wiederholteil (wiederholteile.suchen); nur mit Neuteil-Zuschlag,
        nur im Entwurf (verschickte Preise bleiben). Ergebnis: True = geändert."""
        if not rechnen._n(self.db.einstellung("neuteil_zuschlag")) or self.fremd() or self.db.nur_lesen:
            return False
        if (self.db.angebot(self.id) or {}).get("vorgang") not in (None, "", "Entwurf"):
            return False
        neu = sorted(p["id"] for p in self.positionen if p.get("profil_id") and not any(
            t.angebot.get("vorgang") == "Beauftragt" for t in (treffer or {}).get(p["id"], ())))
        alt = sorted(json.loads(self.kopf.get("neuteile") or "[]"))
        if neu == alt:
            return False
        self._kopf_speichern(_kopf_feld("neuteile"), json.dumps(neu) if neu else None)
        return True

    # ------------------------------------------------------------------ G1 Zielpreis
    def zielpreis(self, ziel=None, setzen=None):
        """Kopf „Zielpreis …“: nötigen Gewinn für den Zielpreis (netto gesamt) zeigen; setzen=True stellt den Gewinn
        des Angebots so ein (None = fragen). Ergebnis: dict(ziel, gewinn, marge, text) oder None."""
        from . import freigabe, kalk_hinweise
        if ziel is None:
            if self.f.stumm:
                return None
            alt = (self.db.zusatz(self.id, "zielpreis") or {}).get("gesamt") or round(self._verkauf(), 2)
            ziel, ok = QInputDialog.getDouble(self, "Zielpreis", "Zielpreis netto für das ganze Angebot [€]:",
                                              float(alt), 0, 1e9, 2)
            if not ok:
                return None
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return None
        self.db.zusatz_setzen(self.id, "zielpreis", dict(gesamt=round(ziel, 2)) if ziel else None)
        if not ziel:
            return None

        def verkauf_bei(g):
            e = dict(self.einst, gewinn=g, gewinn_bis_1=0)
            return rechnen.kalkulation(self.kopf, self.positionen, self.ergebnis, self.k, self.tabellen, e)[1]["verkauf"]

        jetzt = rechnen._n(self.einst.get("gewinn"))
        g = kalk_hinweise.gewinn_fuer_ziel(verkauf_bei, ziel)
        marge = None
        if g is not None:
            e = dict(self.einst, gewinn=g, gewinn_bis_1=0)
            marge = freigabe.marge(rechnen.kalkulation(self.kopf, self.positionen, self.ergebnis, self.k,
                                                       self.tabellen, e)[1])
        text = kalk_hinweise.ziel_text(ziel, jetzt, g, self.db.einstellung("mindestmarge"), marge)
        _, s = self._rechnung()
        unter = kalk_hinweise.untergrenze_punkte(s, ziel)
        text += "".join(" " + t for _, t, _ in unter if "Zielpreis" in t)
        if setzen is None and g is not None and not self.f.stumm:
            setzen = QMessageBox.question(self, "Zielpreis", text + "\n\nGewinn des Angebots jetzt so einstellen?",
                                          QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes
        elif setzen is None:
            self.f.meldung(text)
        if setzen and g is not None:
            self._kopf_speichern(_kopf_feld("gewinn"), round(100 * g, 2))
            self.f.meldung(f"Auf Zielpreis gesetzt: Gewinn {zahl(100 * g, 2)} %.")
        return dict(ziel=ziel, gewinn=g, marge=marge, text=text)

    def zielpreis_menge(self, zeile, ziel_stueck):
        """G1 je Position: kleinste Stückzahl, bei der der Stückpreis der Position mit dem normalen Gewinn den
        Ziel-Stückpreis erreicht (Vielfache der Anfrage), oder None."""
        from . import kalk_hinweise
        p = self.positionen[zeile]

        def preis_bei(menge):
            pos = [dict(x, stueck=menge) if x["id"] == p["id"] else x for x in self.positionen]
            erg = rechnen.optimieren(self.kopf, pos, self.k, self.tabellen, self.einst)
            zeilen, _ = rechnen.kalkulation(self.kopf, pos, erg, self.k, self.tabellen, self.einst)
            return zeilen[zeile]["preis_teil"] if zeilen[zeile] else float("inf")

        return kalk_hinweise.menge_fuer_ziel(preis_bei, rechnen._n(p.get("stueck")) or 1, ziel_stueck)

    # ------------------------------------------------------------------ Angebots-Check: G1/J1, G4, G5
    def _kalk_punkte(self, summen):
        from . import kalk_hinweise
        out = []
        try:
            ziel = (self.db.zusatz(self.id, "zielpreis") or {}).get("gesamt")
            out += kalk_hinweise.untergrenze_punkte(summen, ziel)
            out += [p for p in (self._auslastung_punkt(summen), self._markt_punkt(summen)) if p]
        except Exception:           # Hinweise nie wichtiger als der Check selbst
            pass
        return out

    def _auslastung_punkt(self, summen):
        """G4b: Belegung der Lieferwoche der Maschine (mit diesem Angebot), nur Hinweis."""
        from . import auftrag, auslastung, feiertage, kalk_hinweise
        if not funktionen.an("funktion_auslastung", self.db) or not self.ergebnis:
            return None
        heute = datetime.date.today()
        schluessel = (heute, self.db.einstellung("stammdaten_stand"), self.kopf.get("maschine"),
                      self.kopf.get("liefertermin"), round(rechnen._n(summen.get("verkauf")), 2))
        alt = getattr(self, "_ausl_cache", None)
        if alt and alt[0] == schluessel:
            return alt[1]
        land = self.db.einstellung("versand_bundesland") or feiertage.VORGABE
        termin = auftrag.termin_vorschlag(self.kopf, heute, land)
        aus = auslastung.berechnen(self.db, heute=heute)
        m, mo = self.kopf.get("maschine"), auslastung.montag(termin)
        kap = aus["kapazitaet"].get((m, mo))
        punkt = None
        if kap:
            eigen = 0.0 if (self.db.angebot(self.id) or {}).get("vorgang") == "Beauftragt" else \
                sum(rechnen._n(z.get("laser_netto")) * rechnen._n(z.get("stueck")) for z in self._rechnung()[0] if z) / 3600
            q = (aus["bedarf"].get((m, mo), 0.0) + eigen) / kap
            punkt = kalk_hinweise.auslastung_punkt(q, f"KW {mo.isocalendar()[1]}",
                                                   self.db.einstellung("auslastung_hoch") or 0,
                                                   self.db.einstellung("auslastung_niedrig") or 0)
        self._ausl_cache = (schluessel, punkt)
        return punkt

    def _markt_punkt(self, summen):
        """G5a: Wettbewerbsabstand bei ähnlichen Absagen (ab 3)."""
        from . import kalk_hinweise
        m = self.marktpreis(summen)
        return ("HINWEIS", kalk_hinweise.markt_text(m), None) if m else None

    def marktpreis(self, summen=None):
        from . import absage, kalk_hinweise
        if summen is None:
            summen = self._rechnung()[1]
        kat = {w: z.get("kategorie") for w, z in self.k.werkstoffe.items()}
        eigene = {p.get("werkstoff_id") for p in self.positionen if p.get("werkstoff_id")}
        return kalk_hinweise.marktpreis(self.db.angebote(), self.db.angebot_werkstoffe(), kat,
                                        absage.kategorie_des_angebots(eigene, kat), summen.get("verkauf"),
                                        ohne_id=self.id)

    # ------------------------------------------------------------------ H2 Vier-Augen-Freigabe
    def freigabe_offen(self, summen=None):
        """Grund, warum das Angebot noch eine Freigabe braucht, oder None."""
        from . import freigabe
        if self.fremd():
            return None
        if summen is None:
            summen = self._rechnung()[1]
        grund = freigabe.noetig(summen, self.einst)
        if grund and not freigabe.gueltig(self.db.zusatz(self.id, "freigabe"), summen):
            return grund
        return None

    def freigeben(self):
        """Ausgaben → „Freigeben (Admin) …“: nur ein Admin (Schloss in den Einstellungen). Ergebnis: Eintrag oder
        None."""
        from . import admin_schutz, freigabe
        _, s = self._rechnung()
        grund = freigabe.noetig(s, self.einst)
        if not grund:
            self.f.meldung("Dieses Angebot braucht keine Freigabe.")
            return None
        if not admin_schutz.ist_admin(self.db):
            self.f.meldung("Freigeben darf nur ein Admin (Schloss oben in den Einstellungen).", fehler=True)
            return None
        wer = self.db.einstellung("benutzer_kuerzel") or self.db.einstellung("benutzer_name") or "Admin"
        e = freigabe.eintrag(wer, s, grund)
        self.db.zusatz_setzen(self.id, "freigabe", e)
        self.db.versand_merken(self.id, e)
        self.kopf["versand"] = (self.db.angebot(self.id) or {}).get("versand") or []
        self.f.meldung(freigabe.text(e))
        return e

    def _freigabe_vor_pdf(self):
        """Vor dem Angebots-PDF: True = weiter. Ohne Freigabe ein Hinweis (Admin kann gleich freigeben)."""
        from . import admin_schutz
        grund = self.freigabe_offen()
        if not grund:
            return True
        if admin_schutz.ist_admin(self.db) and not self.f.stumm and QMessageBox.question(
                self, "Freigabe nötig", f"Dieses Angebot braucht eine Vier-Augen-Freigabe ({grund}). Jetzt als "
                                        "Admin freigeben?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            return self.freigeben() is not None
        self.f.meldung(f"Freigabe nötig ({grund}): ein Admin gibt das Angebot unter Ausgaben → Freigeben (Admin) … "
                       "frei.", fehler=True)
        return False

    # ------------------------------------------------------------------ H5 Rückfrage an den Kunden
    def rueckfrage(self, ausfuehren=None, eml=None, punkte=None):
        """Ausgaben → „Rückfrage an Kunden …“: Mail-Entwurf mit den offenen Punkten (Outlook, als Antwort auf die
        Anfrage-Mail; sonst E-Mail-Datei eml), Vermerk im Versandverlauf und Wiedervorlage. ausfuehren ersetzt den
        Outlook-Aufruf (Tests). Ergebnis: dict(text, an, weg) oder None."""
        from . import angebot_mail, materialanfrage, rueckfrage
        from . import mail as mail_
        if self.fremd():
            self.f.meldung("Rückfrage nur für eigene Angebote.", fehler=True)
            return None
        zeilen, summen = self._rechnung()
        liste = punkte if punkte is not None else rueckfrage.punkte(self.freigabe_punkte(summen, zeilen),
                                                                    self.positionen, zeilen)
        if not liste:
            self.f.meldung("Keine offenen Punkte für eine Rückfrage.")
            return None
        kunde = self.db.kunde(self.kopf.get("kundennr"))
        anfrage = None
        try:
            for p in angebot_mail.anfrage_mails(self.f.angebot_ordner(self.kopf)):
                m = mail_.lesen(p)
                if m is not None:
                    anfrage = (p, m)
                    break
        except OSError:
            pass
        an = angebot_mail.empfaenger(kunde, anfrage[1] if anfrage else None)
        betreff = rueckfrage.betreff(self.kopf)
        text = rueckfrage.text(self.kopf, kunde, liste, self.db.einstellung("benutzer_name") or "")
        weg = None
        if ausfuehren is not None or os.name == "nt":
            antwort = str(anfrage[0]) if anfrage and angebot_mail.antwort_moeglich(anfrage[0]) else None
            ok, _ = materialanfrage.outlook_oeffnen(an, betreff, text, (), ausfuehren=ausfuehren, antwort=antwort)
            weg = "outlook" if ok else None          # kein Outlook: E-Mail-Datei
        if weg is None:
            ziel = eml or self._ziel("Rückfrage", ".eml")
            if ziel is None:
                return None
            materialanfrage.eml(ziel, an, betreff, text)
            weg = str(ziel)
            if not self.f.stumm:
                self.f.datei_oeffnen(ziel)
        self.db.versand_merken(self.id, rueckfrage.eintrag(an, len(liste)))
        self.db.wiedervorlage_setzen(self.id, rueckfrage.wiedervorlage())
        self.kopf["versand"] = (self.db.angebot(self.id) or {}).get("versand") or []
        self.f.meldung(f"Rückfrage mit {len(liste)} Punkten vorbereitet, Wiedervorlage in "
                       f"{rueckfrage.WIEDERVORLAGE_TAGE} Tagen.")
        return dict(text=text, an=an, weg=weg)

    # ------------------------------------------------------------------ H6 Positionsvorlagen
    def als_vorlage_speichern(self, zeile=None, name=None):
        """Markierte Position als Positionsvorlage (für alle Arbeitsplätze). Ergebnis: ID oder None."""
        from . import positionsvorlagen
        if zeile is None:
            i = self.pos_ansicht.currentIndex()
            zeile = i.row() if i.isValid() else None
        if zeile is None or not (0 <= zeile < len(self.positionen)):
            self.f.meldung("Bitte zuerst eine Position wählen.", fehler=True)
            return None
        p = self.positionen[zeile]
        if name is None:
            if self.f.stumm:
                return None
            name, ok = QInputDialog.getText(self, "Als Vorlage speichern", "Name der Vorlage:",
                                            text=p.get("bezeichnung") or p.get("artikel") or "")
            if not ok:
                return None
        try:
            i = positionsvorlagen.speichern(self.db, p, name)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
        self.f.meldung(f"Positionsvorlage „{name}“ gespeichert.")
        return i

    def position_aus_vorlage(self, vorlage_id=None):
        """Neue Position aus einer Vorlage (Auswahl mit Suche). Ergebnis: ID der neuen Position oder None."""
        from . import positionsvorlagen
        if self.fremd() or self.db.nur_lesen:
            self.f.meldung("Dieses Angebot lässt sich nur ansehen.", fehler=True)
            return None
        vorlagen = self.db.zeilen("positionsvorlagen")
        if not vorlagen:
            self.f.meldung("Noch keine Positionsvorlagen: an einer Position „Als Vorlage speichern“.", fehler=True)
            return None
        if vorlage_id is None:
            if self.f.stumm:
                return None
            namen = [f"{v['name']} – {v.get('inhalt') or ''}" for v in vorlagen]
            wahl, ok = QInputDialog.getItem(self, "Neue Position aus Vorlage", "Vorlage:", namen, 0, True)
            if not ok or wahl not in namen:
                return None
            vorlage_id = vorlagen[namen.index(wahl)]["id"]
        v = next((x for x in vorlagen if x["id"] == vorlage_id), None)
        werte = positionsvorlagen.werte(v)
        if werte is None:
            self.f.meldung("Die Vorlage ist leer oder beschädigt.", fehler=True)
            return None
        pid = self.db.position_neu(self.id, dict(werte, pos=self._naechste_pos()))
        self.neu_laden()
        self.f.meldung(f"Position aus Vorlage „{v['name']}“ angelegt; Stückzahl eintragen.")
        return pid

    # ------------------------------------------------------------------ F5/F6 Lieferschein und Werkszeugnisse
    def lieferschein(self, mengen=None, pfad=None, oeffnen=True):
        """Ausgaben → „Lieferschein …“ (nur beauftragte Angebote): Mengen je Position (Vorgabe: offen), PDF,
        Werkszeugnisse in den Ordner „Werkszeugnisse“ daneben. Ergebnis: dict(schein, pfad, zeugnisse) oder None."""
        from . import ausgabe, lieferschein
        if self.fremd():
            self.f.meldung("Lieferscheine nur für eigene Aufträge.", fehler=True)
            return None
        if (self.db.angebot(self.id) or {}).get("vorgang") != "Beauftragt":
            self.f.meldung("Lieferscheine gibt es für beauftragte Angebote (Vorgang Beauftragt).", fehler=True)
            return None
        st = lieferschein.stand(self.positionen, lieferschein.scheine(self.db, self.id))
        if not any(z["offen"] > 0 for z in st):
            self.f.meldung("Alles ist schon geliefert.", fehler=True)
            return None
        if mengen is None:
            if self.f.stumm:
                mengen = {z["pid"]: z["offen"] for z in st}
            else:
                mengen = self._lieferschein_dialog(st)
                if mengen is None:
                    return None
        z_info = None
        if self.kopf.get("zeugnis_31") == "ja":
            z_info = lieferschein.zeugnisse_sammeln(self.db, self.id)
            if z_info["fehlt"] and not self.f.stumm and QMessageBox.question(
                    self, "Werkszeugnis fehlt", "Für diese Lagerposten fehlt das Werkszeugnis 3.1:\n"
                    + "\n".join(z_info["fehlt"]) + "\n\nLieferschein trotzdem erstellen?",
                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return None
        try:
            schein = lieferschein.anlegen(self.db, self.id, mengen)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
        rest = lieferschein.stand(self.positionen, lieferschein.scheine(self.db, self.id))
        ziel = pfad or self._ziel(schein["nummer"], ".pdf")
        if ziel is None:
            return None
        anschrift = [self.kopf.get("kunde")] + ausgabe.anschrift(self.db.kunde(self.kopf.get("kundennr")))
        pfad = self._schreiben("Lieferschein", ziel, lambda p: lieferschein.pdf(p, self.kopf, schein, self.einst,
                                                                               anschrift, rest),
                               oeffnen and not self.f.stumm)
        if z_info is not None and z_info["vorhanden"] and pfad:
            from pathlib import Path
            lieferschein.zeugnisse_sammeln(self.db, self.id, Path(pfad).parent / "Werkszeugnisse")
        if z_info and z_info["fehlt"]:
            self.f.meldung(f"Lieferschein {schein['nummer']}: Werkszeugnis fehlt für {len(z_info['fehlt'])} "
                           "Lagerposten.", fehler=True)
        return dict(schein=schein, pfad=pfad, zeugnisse=z_info)

    def _lieferschein_dialog(self, st):
        from .eingabe import RechenSpin
        d = QDialog(self)
        d.setWindowTitle("Lieferschein")
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel("Mengen dieser Lieferung (Vorgabe: noch offen). 0 = Position nicht dabei."))
        t = QTableWidget(len(st), 5)
        t.setHorizontalHeaderLabels(["Pos.", "Bezeichnung", "Bestellt", "Geliefert", "Diese Lieferung"])
        t.setSelectionMode(QAbstractItemView.NoSelection)
        spins = []
        for r, z in enumerate(st):
            for c, w in enumerate((z["pos"], z["bezeichnung"] or z["artikel"], f"{z['bestellt']:g}",
                                   f"{z['geliefert']:g}")):
                t.setItem(r, c, QTableWidgetItem(str(w or "")))
            s = RechenSpin()
            s.setRange(0, z["offen"])
            s.setDecimals(0)
            s.setValue(z["offen"])
            t.setCellWidget(r, 4, s)
            spins.append(s)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        lay.addWidget(t)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.accepted.connect(d.accept)
        k.rejected.connect(d.reject)
        lay.addWidget(k)
        d.resize(620, 360)
        if d.exec() != QDialog.Accepted:
            return None
        return {z["pid"]: s.value() for z, s in zip(st, spins)}

    # ------------------------------------------------------------------ J5 Losgröße
    def losgroesse(self):
        """J5b: wirtschaftliche Abrufmenge (Andler) für Abruf-Angebote, sonst None: Rüsten, Stangenwechsel und Fracht
        je Abruf gegen den Lagerzins auf die Stückkosten."""
        from . import abruf, kalk_hinweise
        if not abruf.aktiv(self.kopf):
            return None
        zeilen, s = self._rechnung()
        stueck = sum(rechnen._n(z.get("stueck")) for z in zeilen if z)
        if not stueck:
            return None
        ruest = (rechnen._n(s.get("ruesten_maschine")) + rechnen._n(s.get("ruesten_abmessungen"))
                 + rechnen._n(s.get("fracht")))
        jahr = (rechnen._n(self.kopf.get("abruf_jahr_von")) + rechnen._n(self.kopf.get("abruf_jahr_bis"))) / 2
        zins = rechnen._n(self.kopf.get("abruf_lagerzins") or self.db.einstellung("abruf_lagerzins")) / 100 or 0.08
        return kalk_hinweise.losgroesse(jahr, ruest, rechnen._n(s.get("selbst")) / stueck, zins)

    # ------------------------------------------------------------------ F4 Lieferantenangebote, H7 Bewertung
    def lieferantenangebote(self, zeigen=True):
        """Ausgaben → „Lieferantenangebote …“: Antworten auf die Materialanfrage, Vergleich (günstigste je Abmessung
        grün) mit Bewertung der Lieferanten; Antwort erfassen, Übernehmen in die Stammdaten, Wareneingang.
        zeigen=False: nur den Dialog bauen (Tests). Ergebnis: der Dialog."""
        from PySide6.QtGui import QColor
        from . import lieferantenangebote as la
        from .tabelle_dialog import TabellenDialog
        antworten = la.liste(self.db, self.id)
        v = la.vergleich(antworten, self.k)
        bew = {b["lieferant"]: b for b in la.bewertung(self.db, self.k)}
        zeilen, farben = [], {}
        for r, z in enumerate(v):
            e = z["antwort"]
            zeilen.append([e["profil_id"], e["werkstoff_id"], e["lieferant"], zahl(e["preis"], 2), e["basis"],
                           zahl(z["je_m"], 2) if z["je_m"] is not None else "", e.get("lieferzeit") or "",
                           e.get("gueltig_bis") or "", la.bewertung_text(bew.get(e["lieferant"])),
                           "übernommen" if e.get("gewaehlt") else "", e.get("eingang") or ""])
            if z["bester"]:
                farben[r] = QColor("#1B7F3B")

        def neu_zeigen(d_alt):
            d_alt.accept()
            if not self.f.stumm:
                self.lieferantenangebote()

        def erfassen(_m):
            if self._antwort_erfassen():
                neu_zeigen(d)

        def uebernehmen(m):
            if not m:
                self.f.meldung("Bitte eine Antwort markieren.", fehler=True)
                return
            for r in m:
                la.uebernehmen(self.db, self.id, v[r]["index"])
            self.f.meldung(f"{len(m)} Preis(e) in die Stammdaten übernommen (Gültig ab heute).")
            neu_zeigen(d)

        def eingang(m):
            for r in m:
                la.eingang_setzen(self.db, self.id, v[r]["index"])
            if m:
                self.f.meldung("Wareneingang mit heutigem Datum eingetragen.")
                neu_zeigen(d)

        d = TabellenDialog(self, "Lieferantenangebote",
                           "Antworten der Lieferanten auf die Materialanfrage. Grün = günstigste je Abmessung (in €/m "
                           "umgerechnet). Bewertung aus allen Angeboten: Preisrang, Termintreue, Reklamationen.",
                           ["Profil", "Werkstoff", "Lieferant", "Preis", "Basis", "€/m", "Lieferzeit [Tage]",
                            "gültig bis", "Bewertung", "Stand", "Wareneingang"], zeilen, rechts=(3, 5, 6),
                           farben=farben, breite=1100,
                           knoepfe=[("Antwort erfassen …", erfassen), ("Übernehmen", uebernehmen),
                                    ("Wareneingang", eingang)])
        d.vergleich = v
        if zeigen and not self.f.stumm:
            d.exec()
        return d

    def _antwort_erfassen(self, werte=None):
        """Formular für eine Lieferantenantwort; werte = dict ohne Fenster (Tests). Ergebnis: Index oder None."""
        from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit
        from . import lieferantenangebote as la
        from .eingabe import RechenSpin
        from .stammdaten import PREISBASIS
        if werte is None:
            d = QDialog(self)
            d.setWindowTitle("Antwort erfassen")
            form = QFormLayout(d)
            lief = QComboBox()
            lief.setEditable(True)
            lief.addItems(sorted({z.get("name") or "" for z in self.db.zeilen("zukauf_lieferanten")} - {""}))
            abm = QComboBox()
            paare = sorted({(p.get("profil_id"), p.get("werkstoff_id")) for p in self.positionen
                            if p.get("profil_id") and p.get("werkstoff_id")})
            abm.addItems([f"{a} | {b}" for a, b in paare])
            basis = QComboBox()
            basis.addItems(list(PREISBASIS))
            preis, laenge, zeit = RechenSpin(), RechenSpin(), RechenSpin()
            preis.setRange(0, 1e6)
            preis.setDecimals(3)
            laenge.setRange(0, 30000)
            laenge.setDecimals(0)
            laenge.setValue(rechnen._n(self.kopf.get("stange")))
            zeit.setRange(0, 365)
            zeit.setDecimals(0)
            bis = QLineEdit()
            bis.setPlaceholderText("JJJJ-MM-TT")
            for t, w in (("Lieferant", lief), ("Profil | Werkstoff", abm), ("Preisbasis", basis), ("Preis [€]", preis),
                         ("Stangenlänge [mm] (bei €/Stange)", laenge), ("Lieferzeit [Tage]", zeit),
                         ("Gültig bis", bis)):
                form.addRow(t, w)
            k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            k.accepted.connect(d.accept)
            k.rejected.connect(d.reject)
            form.addRow(k)
            if d.exec() != QDialog.Accepted or not paare:
                return None
            pr, ws = paare[abm.currentIndex()]
            werte = dict(lieferant=lief.currentText(), profil_id=pr, werkstoff_id=ws, basis=basis.currentText(),
                         preis=preis.value(), laenge=laenge.value(), lieferzeit=zeit.value(),
                         gueltig_bis=bis.text().strip() or None)
        try:
            return la.erfassen(self.db, self.id, **werte)
        except ValueError as e:
            self.f.meldung(str(e), fehler=True)
            return None
