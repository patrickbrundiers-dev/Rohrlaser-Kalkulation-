"""EK-CSV-Import als Assistent in 6 Schritten (Master-Auftrag 25.11.2026, gemeinsamer Rahmen import_assistent):
1 Datei, Lieferant, Format · 2 Spalten (automatisch, von Hand, Importprofile) · 3 Materialerkennung (exakt =
automatisch, wahrscheinlich = bestätigen, kein Treffer = neues Material vorschlagen) · 4 Preisprüfung (alter/neuer EK
je Lieferant, € und %, Markierung ab einstellbarer Grenze) · 5 Vorschau (neu, unverändert, doppelt, fehlerhaft) ·
6 Abschluss (übernehmen als ein Importlauf, Protokoll, Fehlerbericht, Rückgängig). Bis Schritt 6 ändert nichts die
Datenbank."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QHBoxLayout, QLineEdit, QPushButton

from . import csv_import
from . import erp_preise as E
from . import import_assistent as IA

STUFE_FARBE = {E.EXAKT: IA.GRUEN, E.WAHRSCHEINLICH: IA.GELB, E.KEIN_TREFFER: IA.ROT}
GRUPPE_FARBE = {E.NEU_KAUF: IA.GRUEN, E.VORHANDEN: IA.GRAU, E.DOPPELT: IA.GELB, E.FEHLERHAFT: IA.ROT}


def _material(a):
    v = a.get("vorschlag_zuordnung")
    pid, wid, ober = ((v["profil_id"], v["werkstoff_id"], v.get("oberflaeche")) if v else
                      (a.get("profil_id"), a.get("werkstoff_id"), a.get("oberflaeche")))
    if a.get("ignorieren"):
        return "übersprungen"
    return " · ".join(x for x in (pid or "Profil ?", wid or "Werkstoff ?", ober or "") if x)


def _datum(d):
    return d.strftime("%d.%m.%Y") if hasattr(d, "strftime") else str(d or "")


class MaterialSchritt(IA.TabellenSchritt):
    titel = "Materialerkennung"

    def __init__(self, a):
        super().__init__("Materialerkennung", ("Stufe", "Bezeichnung in der Datei", "Artikelnr.", "Erkannt als",
                                               "Begründung", "Käufe"), (150, 300, 110, 240, 300),
                         filter_=E.STUFEN)
        self.a = a
        self.alle_k = QPushButton("Alle wahrscheinlichen Treffer bestätigen")
        self.alle_k.clicked.connect(lambda: self.alle(True))
        self.anlegen = QCheckBox("Materialien ohne Treffer neu anlegen (Profile, Werkstoffe, Materialstamm)")
        self.anlegen.setChecked(True)
        self.werkstoffe = QCheckBox("auch neue Werkstoffe anlegen")
        self.werkstoffe.setChecked(True)
        self.oben.insertWidget(self.oben.count() - 1, self.alle_k)
        z = QHBoxLayout()
        z.addWidget(self.anlegen)
        z.addWidget(self.werkstoffe)
        z.addStretch(1)
        self.layout().insertLayout(2, z)
        self.bestaetigt = set()           # Schlüssel der bestätigten wahrscheinlichen Treffer
        self.t.itemChanged.connect(self._haken)

    def betreten(self):
        v = self.a.vorschau()
        z = v["zaehler"]
        p = v["plan"]
        self.kopf.setText(
            f"<b>{z[E.EXAKT]}</b> exakt erkannt (werden automatisch zugeordnet) · <b>{z[E.WAHRSCHEINLICH]}</b> "
            f"wahrscheinlich (Haken = bestätigen) · <b>{z[E.KEIN_TREFFER]}</b> ohne Treffer. Neu anzulegen: "
            f"{len(p['profile'])} Profile, {len(p['werkstoffe'])} Werkstoffe"
            + (f"; <span style='color:#B42318'>{len(p['offen'])} nicht erkennbar (bleiben offen)</span>"
               if p["offen"] else "") + ". Gleiche Abmessung in anderer Schreibweise wird nicht doppelt angelegt.")
        self.anzeigen()

    def _liste(self, filt):
        return [a for a in self.a.vorschau()["artikel"] if filt is None or a.get("stufe") == filt]

    def zeilen(self, filt):
        self.sichtbar = self._liste(filt)
        return ([(a.get("stufe"), a["bezeichnung"], a.get("artikelnr"), _material(a), a.get("stufe_grund") or
                  a.get("hinweis"), a.get("kaeufe")) for a in self.sichtbar],
                [STUFE_FARBE.get(a.get("stufe")) for a in self.sichtbar])

    def anzeigen(self):
        self.t.blockSignals(True)
        super().anzeigen()
        for r, a in enumerate(self.sichtbar[:self.t.rowCount()]):
            if a.get("stufe") == E.WAHRSCHEINLICH and a.get("vorschlag_zuordnung"):
                it = self.t.item(r, 0)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if a["schluessel"] in self.bestaetigt else Qt.Unchecked)
        self.t.blockSignals(False)

    def _haken(self, it):
        if it.column() != 0 or it.row() >= len(self.sichtbar):
            return
        s = self.sichtbar[it.row()]["schluessel"]
        (self.bestaetigt.add if it.checkState() == Qt.Checked else self.bestaetigt.discard)(s)

    def alle(self, an=True):
        for a in self.a.vorschau()["artikel"]:
            if a.get("stufe") == E.WAHRSCHEINLICH and a.get("vorschlag_zuordnung"):
                (self.bestaetigt.add if an else self.bestaetigt.discard)(a["schluessel"])
        self.anzeigen()

    def liste_bestaetigt(self):
        return [(a, None) for a in self.a.vorschau()["artikel"] if a["schluessel"] in self.bestaetigt]


class PreisSchritt(IA.TabellenSchritt):
    titel = "Preisprüfung"

    def __init__(self, a):
        super().__init__("Preisprüfung", ("Material / ERP-Artikel", "Lieferant", "EK bisher", "vom", "EK neu", "vom",
                                          "Änderung €", "Änderung %", "", "Hinweis"),
                         (260, 140, 80, 80, 80, 80, 85, 85, 90),
                         filter_=("nur markierte", E.ERHOEHUNG, E.SENKUNG, E.ERSTER))
        self.a = a
        self.grenze = QDoubleSpinBox()
        self.grenze.setRange(0, 1000)
        self.grenze.setDecimals(1)
        self.grenze.setSuffix(" %")
        self.grenze.setToolTip("Preisänderungen ab diesem Betrag werden markiert (Einstellung "
                               "„EK-Preisänderung markieren ab“)")
        self.grenze.valueChanged.connect(lambda _v: self.anzeigen())
        self.oben.insertWidget(self.oben.count() - 1, IA.QLabel("markieren ab"))
        self.oben.insertWidget(self.oben.count() - 1, self.grenze)

    def betreten(self):
        v = self.a.vorschau()
        self.grenze.blockSignals(True)
        self.grenze.setValue(float(v["grenze_pct"] or 0))
        self.grenze.blockSignals(False)
        self.anzeigen()

    def zeilen(self, filt):
        g = self.grenze.value()
        out, farben = [], []
        liste = self.a.vorschau()["pruefung"]
        for p in liste:
            p["markiert"] = (p["pct"] is not None and abs(p["pct"]) >= g and p["richtung"] in (E.ERHOEHUNG, E.SENKUNG))
            if filt == "nur markierte" and not p["markiert"] or filt in (E.ERHOEHUNG, E.SENKUNG, E.ERSTER) and \
                    p["richtung"] != filt:
                continue
            mat = p["material"]
            name = " · ".join(x for x in mat if x) if p["zugeordnet"] else f"{p['bezeichnung']} (nicht zugeordnet)"
            hinweis = []
            if p.get("anderer_lieferant"):
                hinweis.append(f"Vergleich mit {p['alt_lieferant'] or 'ohne Lieferant'} (dessen Preis bleibt)")
            if p.get("anzahl", 1) > 1:
                hinweis.append(f"{p['anzahl']} Käufe, neuester zählt")
            out.append((name, p["lieferant"], IA.zahl(p["alt"]), _datum(p["alt_datum"]), IA.zahl(p["neu"]),
                        _datum(p["neu_datum"]), IA.zahl(p["euro"]) if p["euro"] is not None else "",
                        IA.zahl(p["pct"], 1) if p["pct"] is not None else "", p["richtung"], "; ".join(hinweis)))
            farben.append(IA.ROT if p["markiert"] and p["richtung"] == E.ERHOEHUNG else
                          IA.GRUEN if p["markiert"] else IA.GELB if p["richtung"] in (E.ERHOEHUNG, E.SENKUNG) else
                          None)
        n_m = sum(1 for p in liste if p["markiert"])
        self.kopf.setText(f"Je Material und Lieferant der neueste EK der Datei gegen den letzten bisherigen. "
                          f"<b>{n_m}</b> Änderung(en) ab {self.grenze.value():g} % markiert (rot = teurer, grün = "
                          "günstiger, gelb = kleinere Änderung). Ein Preis eines anderen Lieferanten wird nie "
                          "überschrieben, jeder Kauf bleibt mit seinem Lieferanten gespeichert.")
        return out, farben


class VorschauSchritt(IA.TabellenSchritt):
    titel = "Vorschau"

    def __init__(self, a):
        super().__init__("Vorschau", ("Zeile", "Ergebnis", "Datum", "Artikelnr.", "Bezeichnung", "Menge [m]", "€/m",
                                      "Lieferant", "Hinweis / Fehler"), (55, 170, 80, 100, 260, 80, 70, 120),
                         filter_=(E.NEU_KAUF, E.VORHANDEN, E.DOPPELT, E.FEHLERHAFT))
        self.a = a

    def betreten(self):
        z = self.a.vorschau()["zaehler"]
        self.kopf.setText(f"<b style='color:#2E7D32'>{z[E.NEU_KAUF]} neu</b> · {z[E.VORHANDEN]} unverändert (schon "
                          f"eingelesen) · <b style='color:#9A6700'>{z[E.DOPPELT]} doppelt</b> in der Datei · "
                          f"<b style='color:#B42318'>{z[E.FEHLERHAFT]} fehlerhaft</b> (werden nicht übernommen, "
                          "stehen im Fehlerbericht). Es wurde noch nichts gespeichert.")
        self.anzeigen()

    def zeilen(self, filt):
        v = self.a.vorschau()
        out = []
        for x in v["kaeufe"]:
            g = v["gruppe"].get(x["zeile"])
            hinw = x.get("hinweis") or ""
            if g == E.DOPPELT:
                hinw = f"gleicher Kauf wie Zeile {x.get('doppelt_wie')}"
            out.append((x["zeile"], g, _datum(x["datum"]), x.get("artikelnr"), x["bezeichnung"],
                        IA.zahl(x["menge"], 2), IA.zahl(x["preis"], 2), x.get("lieferant"), hinw))
        for n, grund, roh in v["fehler"]:
            out.append((n, E.FEHLERHAFT, "", "", " | ".join(str(c) for c in (roh or ())[:4]), "", "", "", grund))
        out.sort(key=lambda z: z[0])
        out = [z for z in out if filt is None or z[1] == filt]
        return out, [GRUPPE_FARBE.get(z[1]) for z in out]


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
        v = self.a.vorschau()
        z = v["zaehler"]
        m = self.a.material
        self.info.setText(
            f"<b>Bereit zum Import</b> von <b>{Path(self.a.pfad).name}</b>"
            + (f" (Lieferant {self.a.lieferant.text().strip()})" if self.a.lieferant.text().strip() else "")
            + f":<ul><li>{z[E.NEU_KAUF]} neue Käufe</li><li>{len(m.bestaetigt)} bestätigte Zuordnungen, "
            f"{z[E.EXAKT]} exakt erkannt</li><li>neu anzulegen: "
            + (f"{len(v['plan']['profile'])} Profile, {len(v['plan']['werkstoffe']) if m.werkstoffe.isChecked() else 0}"
               " Werkstoffe" if m.anlegen.isChecked() else "nichts (abgewählt)")
            + f"</li><li>{z['preise_geaendert']} Preisänderungen, davon {z['preise_markiert']} markiert</li>"
            f"<li>{z[E.FEHLERHAFT]} fehlerhafte und {z[E.DOPPELT]} doppelte Zeilen werden nicht übernommen</li></ul>"
            "Alles wird in einem Schritt gespeichert und lässt sich vollständig rückgängig machen (auch später unter "
            "„Letzte Importe“). Die Preise in den Stammdaten und vorhandene Angebote bleiben unverändert.")

    def abschliessen(self):
        v = self.a.vorschau()
        m = self.a.material
        try:
            self.ergebnis = E.uebernehmen(self.a.db, v, self.a.pfad, m.liste_bestaetigt(), anlegen=m.anlegen.isChecked(),
                                          mit_werkstoffen=m.werkstoffe.isChecked(),
                                          importprofil=self.a.spalten.profilname,
                                          lieferant=self.a.lieferant.text().strip())
        except E.ErpFehler as e:
            raise ValueError(str(e)) from e
        e = self.ergebnis
        self.info.setText(f"<b style='color:#2E7D32'>Import Nr. {e['import_id']} abgeschlossen:</b> {e['neu']} Käufe "
                          f"gespeichert, {e['zuordnungen']} Zuordnungen, {e['profile']} Profile und {e['werkstoffe']} "
                          f"Werkstoffe angelegt, {e['stamm_neu']} Materialstamm-Zeilen. Protokoll unter „Letzte "
                          "Importe“.")
        self.zurueck_k.setVisible(True)
        return e

    def bericht(self, pfad=None):
        inhalt = E.fehlerbericht(self.a.vorschau(), self.a.daten["kopf"])
        p = Path(self.a.pfad)
        return IA.fehlerbericht_speichern(self, inhalt, p.with_name(p.stem + "_Fehlerbericht.csv"), pfad)

    def rueckgaengig(self):
        if not self.ergebnis:
            return None
        n, meldungen = E.rueckgaengig(self.a.db, self.ergebnis["import_id"])
        self.info.setText(f"Import Nr. {self.ergebnis['import_id']} zurückgenommen ({n} Änderungen)."
                          + (" " + "; ".join(meldungen[:5]) if meldungen else ""))
        self.zurueck_k.setVisible(False)
        self.ergebnis = None
        return n, meldungen


class EkAssistent(IA.Assistent):
    def __init__(self, parent, db, pfad, daten, profilname="", spalten=None, lieferant=""):
        self.db, self.pfad, self.daten = db, pfad, daten
        self._v, self._v_schl = None, None
        self.lieferant = QLineEdit(lieferant)
        self.lieferant.setPlaceholderText("Lieferant aller Zeilen, wenn die Datei keine Lieferantenspalte hat")
        erkannt = E.spalten_erkennen(daten)
        if spalten:
            erkannt = {f: dict(spalte=i, sicherheit=csv_import.SICHER, grund=f"aus Importprofil „{profilname}“")
                       for f, i in spalten.items()}
        self.datei = IA.DateiSchritt(pfad, daten, profilname, zusatz=(("Lieferant", self.lieferant),),
                                     laeufe=lambda: csv_import.laeufe(db, csv_import.ART_EK),
                                     rueckgaengig=lambda i: E.rueckgaengig(db, i))
        self.spalten = IA.SpaltenSchritt(db, E.IMPORTPROFILE, E.FELDER, E.PFLICHT, daten, erkannt, profilname,
                                         extras=lambda: dict(lieferant=self.lieferant.text().strip()))
        self.material = MaterialSchritt(self)
        try:            # Admin-Schutz: ohne Freigabe für Werkstoffe nur Profile anlegen
            from . import admin_schutz
            if "werkstoffe" in admin_schutz.tabellen_geschuetzt(db) and not admin_schutz.ist_admin(db):
                self.material.werkstoffe.setChecked(False)
                self.material.werkstoffe.setEnabled(False)
                self.material.werkstoffe.setToolTip("Werkstoffe sind durch den Admin geschützt")
        except Exception:       # noqa: BLE001  (Datei ohne Admin-Vorgaben)
            from . import protokoll
            protokoll.warnung("Admin-Schutz für Werkstoffe nicht lesbar")
        self.preise = PreisSchritt(self)
        self.vorschau_s = VorschauSchritt(self)
        self.abschluss = AbschlussSchritt(self)
        super().__init__(parent, f"EK-Preise importieren: {Path(pfad).name}",
                         (self.datei, self.spalten, self.material, self.preise, self.vorschau_s, self.abschluss))

    def vorschau(self):
        """Vorschau (ohne Datenbankänderung) zur aktuellen Spaltenzuordnung, nur neu gerechnet, wenn sich Spalten
        oder Lieferant geändert haben."""
        schl = (tuple(sorted(self.spalten.zuordnung().items())), self.lieferant.text().strip())
        if self._v is None or schl != self._v_schl:
            self._v = E.vorschau_import(self.db, self.daten, self.spalten.zuordnung(), fortschritt=self.fortschritt,
                                        lieferant=self.lieferant.text().strip())
            self._v_schl = schl
            self.material.bestaetigt.clear()
        return self._v


def assistent(seite, db, pfad):
    """EK-Assistent zur Datei bauen (nicht zeigen): Datei lesen, passendes Importprofil (auch bei anderer
    Spaltenreihenfolge), sonst automatische Erkennung. Ergebnis EkAssistent; ErpFehler bei unlesbarer Datei."""
    roh = Path(pfad).read_bytes()
    daten = E.lesen(roh, str(pfad))
    name, profil, sp = csv_import.profil_passend(csv_import.profile(db, E.IMPORTPROFILE), daten["kopf"])
    lief = (profil or {}).get("lieferant") or ""
    if sp is None:          # alte Vorlagen (vor dem Assistenten) gelten weiter
        z, gespeichert = E.zuordnung_fuer(daten["kopf"], db.einstellung(E.VORLAGEN) or {})
        sp = z if gespeichert else None
    return EkAssistent(seite, db, str(pfad), daten, name or "", sp, lief)
