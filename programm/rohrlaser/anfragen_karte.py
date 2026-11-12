"""Karte „Neue Anfragen“ auf der Startseite (Plan W6a): Anfragen aus dem Anfrage-Ordner (anfragen.py), Öffnen als
neues Angebot aus STEP, mehrere Anfragen eines Kunden auf Wunsch zusammen. Sichtbar nur mit Einstellung
„anfrage_ordner“; alle ANFRAGEN_S Sekunden wird nachgesehen. Anfrageformulare werden schon vorher im Hintergrund
gelesen (Scans mit Tesseract dauern einige Sekunden je Seite, Plan W6c); die Liste zeigt solange „liest Formular …“.

Automationen 03.11.2026 (anfrage_vorab, nachtrag, bestellung, wiederholanfrage): STEP-Dateien werden im Hintergrund
vorgemessen (Zusammenfassung mit Richtpreis in der Liste), die Ampel zeigt die Antwortfrist und sortiert danach,
Nachträge zu vorhandenen Angeboten legt das Programm selbst in den Angebotsordner, Bestellungen und
Wiederholanfragen ohne STEP erscheinen als Zeile mit Link."""
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHBoxLayout, QInputDialog, QLabel, QListWidget, \
    QListWidgetItem, QMessageBox, QPushButton

from . import anfrage_vorab, anfragen, angebotsordner
from .klartext import fehler_text

ANFRAGEN_S = 30             # Sekunden zwischen zwei Blicken in den Ordner


class AnfragenKarte:
    """Baut die Karte (self.karte) und hält die Anfragen (self.anfragen)."""

    def __init__(self, fenster):
        from .angebot_oben import karte
        self.f = fenster
        self.karte, lay = karte("Neue Anfragen")
        self.titel = QLabel()
        self.titel.setWordWrap(True)
        lay.addWidget(self.titel)
        self.liste = QListWidget()
        self.liste.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.liste.setToolTip("Doppelklick öffnet die Anfrage als neues Angebot. Mehrere markieren (Strg) und "
                              "„Zusammen öffnen“ rechnet sie in einem Angebot.")
        self.liste.itemActivated.connect(lambda it: self.oeffnen([self._anfrage(it)]))
        self.liste.itemSelectionChanged.connect(self._knoepfe_setzen)
        self.liste.setMaximumHeight(140)
        lay.addWidget(self.liste)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setTextFormat(Qt.RichText)
        self.hinweis.linkActivated.connect(self._link)
        lay.addWidget(self.hinweis)
        zeile = QHBoxLayout()
        self.knopf_oeffnen = QPushButton("Öffnen")
        self.knopf_oeffnen.setObjectName("primaer")
        self.knopf_oeffnen.clicked.connect(lambda: self.oeffnen(self.markierte()))
        self.knopf_zusammen = QPushButton("Zusammen öffnen")
        self.knopf_zusammen.setToolTip("Markierte Anfragen in einem Angebot (Stangen gemeinsam optimiert)")
        self.knopf_zusammen.clicked.connect(lambda: self.oeffnen(self.markierte(), zusammen=True))
        ordner = QPushButton("Ordner öffnen")
        ordner.clicked.connect(self.ordner_oeffnen)
        # Gemeinsamer Ordner (Patrick 28.10.2026): Anfrage einem Kollegen zuweisen, für alle sichtbar
        self.knopf_zuweisen = QPushButton("Zuweisen …")
        self.knopf_zuweisen.setToolTip("Markierte Anfrage einem Kollegen zuweisen (alle sehen „für MK“)")
        self.knopf_zuweisen.clicked.connect(lambda: self.zuweisen(self.markierte()[:1]))
        for b in (self.knopf_oeffnen, self.knopf_zusammen, self.knopf_zuweisen, ordner):
            zeile.addWidget(b)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.anfragen, self._stand = [], None
        self._gelesen, self._laeuft, self._pool = {}, {}, None     # Formulare: Schlüssel -> Ergebnis bzw. Future
        # Vormessen (3a): Anfrage-Schlüssel -> (Stempel, Text) bzw. (Stempel, Future); eigener Hintergrund-Thread
        self._vorab, self._vorab_laeuft, self._vorab_pool = {}, {}, None
        # Mails ohne STEP (1a, 5a, 6a): Datei-Schlüssel -> Ergebnis; Links der Hinweiszeilen
        self._ohne, self._links = {}, {}
        self._warten = QTimer(self.karte)
        self._warten.setInterval(1000)
        self._warten.timeout.connect(self._lesen_pruefen)
        self.timer = QTimer(self.karte)
        self.timer.timeout.connect(self.neu_laden)
        self.timer.start(ANFRAGEN_S * 1000)
        self.neu_laden()

    def ordner(self):
        o = anfragen.ordner(self.f.db)
        return str(o) if o else ""

    def neu_laden(self, erzwingen=False):
        o = self.ordner()
        self.karte.setVisible(bool(o))
        if not o:
            self.anfragen = []
            return
        kunden = self.f.db.zeilen("kunden")
        ich = self.f.db.einstellung("benutzer_kuerzel") or ""
        ohne = []
        try:            # Nachtrag zu einer schon übernommenen Anfrage erkennen (Anfrage-Nr. = Kundenreferenz)
            angebote = {r: (n, k) for r, n, k in self.f.db.con.execute(
                "SELECT kundenreferenz, nummer, kundennr FROM angebote WHERE COALESCE(kundenreferenz, '') <> '' "
                "ORDER BY id")}
        except Exception:
            angebote = {}
        try:            # intern weitergeleitete Mails: Absender des Kunden zum Zusammenfassen (31.10.2026)
            anfragen.EIGENE = anfragen.eigene_domains(self.f.db)
        except Exception:
            anfragen.EIGENE = set()
        dateien = []
        neu = anfragen.suchen(o, kunden, ohne_step=ohne, angebote=angebote, ohne_dateien=dateien)
        st = (anfragen.stand(neu), tuple(ohne))
        if st == self._stand and not erzwingen:
            return
        markiert = {a.schluessel for a in self.markierte()}
        auto_zeilen, verschoben = self._ohne_step(dateien, angebote, kunden)
        if verschoben:          # Nachträge (Angebotsordner), Bestellungen, Wiederholanfragen: nicht als „ohne STEP“
            ohne = [t for t in ohne if not any(t.startswith(n) for n in verschoben)]
        self._zuweisen_auto(neu, kunden)
        neu = self._ampel_sortieren(neu)
        self.anfragen, self._stand, self._kunden = neu, st, kunden
        self.liste.clear()
        self._vorlesen(neu)
        self._vormessen(neu)
        for a in neu:
            kunde = anfragen.kunde_text(kunden, a.kunde) if a.kunde else ""
            liest = " · liest Formular …" if any(_schluessel(d) in self._laeuft for d in a.formulare) else ""
            stufe, _, frist = self._ampeln.get(a.schluessel, (None, None, ""))
            vorab = self._vorab_text(a)
            wichtig = getattr(self, "_wichtig", {}).get(a.schluessel)
            if wichtig and not a.gesperrt:
                vorab = f"{vorab} · {wichtig}" if vorab else wichtig
            it = QListWidgetItem((f"{kunde}  –  {a.text()}" if kunde else a.text()) + liest
                                 + (f" · {vorab}" if vorab else "") + (f" · {frist}" if frist and not a.gesperrt else ""))
            it.setData(Qt.ItemDataRole.UserRole, a.schluessel)
            if stufe and not a.gesperrt:
                it.setIcon(_punkt(anfrage_vorab.FARBE[stufe]))
                it.setToolTip(f"Antwortfrist: {frist}")
            if a.gesperrt or (a.zugewiesen.get("an") and a.zugewiesen.get("an") != ich):
                it.setForeground(self.liste.palette().placeholderText())
            if a.zugewiesen.get("an") == ich and not a.gesperrt:
                schrift = it.font()
                schrift.setBold(True)       # mir zugewiesen
                it.setFont(schrift)
            self.liste.addItem(it)
            it.setSelected(a.schluessel in markiert)
        offen = [a for a in neu if not a.gesperrt]
        meine = [a for a in offen if ich and a.zugewiesen.get("an") == ich]
        self.titel.setText(f"<b>{len(offen)} offene Anfrage{'n' if len(offen) != 1 else ''}</b>"
                           + (f", davon <b>{len(meine)} für Sie</b>," if meine else "") + f" im Ordner {o}"
                           if neu else f"Keine neuen Anfragen im Ordner {o}")
        self.liste.setVisible(bool(neu))
        mehrere = anfragen.gleicher_kunde(neu)
        zeilen = [f"{len(v)} offene Anfragen von <b>{anfragen.kunde_text(kunden, k)}</b>: getrennt öffnen oder "
                  f"<a href='{k}'>beide markieren</a> und „Zusammen öffnen“" for k, v in mehrere.items()]
        zeilen += auto_zeilen
        nachtrag = [t for t in ohne if "(Nachtrag zu Angebot " in t]
        ohne = [t for t in ohne if t not in nachtrag]
        for t in nachtrag:  # Mail ohne STEP zu einer schon übernommenen Anfrage (Patrick 28.10.2026, F2 a)
            name, _, nr = t[:-1].partition(" (Nachtrag zu Angebot ")
            zeilen.append(f"Nachtrag zu Angebot <b>{nr}</b>: {name} – bitte im Angebot prüfen und die Mail von Hand "
                          "dazulegen")
        if ohne:        # nur Zeichnungen/Formulare: nichts automatisch daraus anlegen (Patrick 28.10.2026)
            zeilen.append(f"Ohne STEP (nicht in der Liste, z. B. nur Zeichnung als PDF): {', '.join(ohne[:4])}"
                          + (f" und {len(ohne) - 4} weitere" if len(ohne) > 4 else "")
                          + " – Teile von Hand anlegen oder die STEP dazulegen")
        self.hinweis.setText("<br>".join(zeilen))
        self.hinweis.setVisible(bool(zeilen))
        self._knoepfe_setzen()

    # ------------------------------------------------------------------ Automationen 03.11.2026
    def _zuweisen_auto(self, liste, kunden):
        """Paket D (E7): neue Anfragen dem Zuständigen des Kunden zuweisen, sonst dem Kollegen mit den wenigsten
        offenen Anfragen. Nur mit gemeinsamem Ordner; Einstellung 'anfrage_zuweisen' = nein schaltet es aus."""
        from . import automatik, teilen
        db = self.f.db
        if db.nur_lesen or not teilen.aktiv(db) or (db.einstellung("anfrage_zuweisen") or "ja") != "ja":
            return 0
        n = 0
        for a, an in anfragen.zuweisung_vorschlag(liste, kunden, teilen.kollegen(db), teilen.kuerzel(db)):
            try:
                neu = anfragen.zuweisen(a, self.ordner(), an, "Automatik", "automatisch zugewiesen")
            except OSError:
                continue
            a.ordner, a.dateien, a.zugewiesen = neu.ordner, neu.dateien, neu.zugewiesen
            automatik.merken(db, "zuweisung", f"Anfrage „{a.name}“ an {an}")
            n += 1
        return n

    def _ampel_sortieren(self, liste):
        """Anfrage-Ampel (4a): Frist je Anfrage merken (self._ampeln) und nach Dringlichkeit sortieren; gesperrte
        (in Bearbeitung) ans Ende."""
        land = self.f.db.einstellung("versand_bundesland")
        self._ampeln, eintraege = {}, []
        for a in liste:
            try:
                amp = anfrage_vorab.ampel(anfrage_vorab.eingang(a), anfrage_vorab.frist_tage(self.f.db, a.kunde),
                                          land=land)
            except Exception:
                amp = (None, None, "")
            self._ampeln[a.schluessel] = amp
            eintraege.append((a, amp[0] if not a.gesperrt else None, amp[1]))
        self._wichtig = {}
        from . import vertrieb
        if (self.f.db.einstellung("anfragen_sortierung") or vertrieb.SORT_DRINGLICH) == vertrieb.SORT_WICHTIG:
            try:            # V2 (Vorschläge 11.11.2026): erwarteter Auftragswert, rote Ampel bleibt oben
                werte = vertrieb.kunden_werte(self.f.db.angebote())
                self._wichtig = {a.schluessel: vertrieb.wichtigkeit(werte, a.kunde)[1] for a in liste}
                return vertrieb.sortieren(liste, werte, self._ampeln)
            except Exception:
                self._wichtig = {}
        if not any(e[1] for e in eintraege):
            return liste
        return [a for a, _, _ in anfrage_vorab.sortieren(eintraege)]

    def _vormessen(self, liste):
        """STEP-Dateien offener Anfragen im Hintergrund messen (3a), eine Anfrage nach der anderen."""
        for a in liste:
            if a.gesperrt or not a.step_anzahl():
                continue
            st = anfrage_vorab.stempel(a)
            fertig, laeuft = self._vorab.get(a.schluessel), self._vorab_laeuft.get(a.schluessel)
            if (fertig and fertig[0] == st) or (laeuft and laeuft[0] == st):
                continue
            try:
                job = anfrage_vorab.auftrag(self.f.db, self.f.programmordner, a)
            except Exception:
                job = None
            if not job:             # ausgeschaltet oder kein Messprogramm
                return
            self._vorab_pool = self._vorab_pool or ThreadPoolExecutor(max_workers=1)
            self._vorab_laeuft[a.schluessel] = (st, a, self._vorab_pool.submit(anfrage_vorab.messen, job, a))
        if self._vorab_laeuft and not self._warten.isActive():
            self._warten.start()

    def _vorab_pruefen(self):
        """Fertige Vormessungen auswerten (im Hauptthread: Datenbank für Profile und Richtpreis)."""
        from . import automatik
        fertig = [k for k, (_, _, fu) in self._vorab_laeuft.items() if fu.done()]
        for k in fertig:
            st, a, fu = self._vorab_laeuft.pop(k)
            werte = self._ergebnis(fu)
            if not werte:
                self._vorab[k] = (st, "")
                continue
            try:
                z = anfrage_vorab.zusammenfassung(werte, self.f.db.kontext().profile)
                preis = anfrage_vorab.richtpreis(self.f.db, a.kunde, werte)
                t = anfrage_vorab.text(z, preis, anfrage_vorab.wiederholt(self.f.db, a.kunde, z["artikel"]))
            except Exception:
                t = ""
            self._vorab[k] = (st, t)
            if t:
                automatik.merken(self.f.db, "vormessen", f"{a.name}: {t}")
        return bool(fertig)

    def _vorab_text(self, a):
        if a.gesperrt:
            return ""
        if a.schluessel in self._vorab_laeuft:
            return "wird vorbereitet …"
        v = self._vorab.get(a.schluessel)
        return v[1] if v and v[0] == anfrage_vorab.stempel(a) else ""

    def _ohne_step(self, dateien, angebote, kunden):
        """Mails ohne STEP (Automationen 1a, 5a, 6a): Nachtrag zu einem Angebot selbst einsortieren, Bestellung und
        Wiederholanfrage als Zeile mit Link. Ergebnis: (Hinweiszeilen, Namen der einsortierten Dateien)."""
        from . import bestellung, mail, nachtrag, wiederholanfrage
        db = self.f.db
        zeilen, verschoben, neu_verschoben = [], [], []
        self._links = {k: v for k, v in self._links.items() if not k.startswith(("best:", "wdh:"))}
        for d in dateien:
            if d.suffix.lower() not in anfragen.MAIL:
                continue
            nr = anfragen.nachtrag_zu(d, angebote, kunden)      # neu prüfen: das Angebot kann später entstehen
            k = (_schluessel(d), nr)
            if k not in self._ohne:
                self._ohne[k] = info = dict(art=None)
                try:
                    m = mail.lesen(d)
                except Exception:
                    m = None
                if m is None:
                    continue
                text = m.volltext()
                if nr and not db.nur_lesen:
                    row = db.con.execute("SELECT id FROM angebote WHERE nummer=? ORDER BY id DESC", (nr,)).fetchone()
                    if row:
                        try:
                            ziel = self.f.angebot_ordner(db.angebot(row[0]))
                            nachtrag.einsortieren(db, row[0], d, ziel, m)
                            info.update(art="nachtrag", nummer=nr)
                            neu_verschoben.append(nr)
                            verschoben.append(d.name)
                            continue
                        except OSError:
                            pass
                kundennr = mail.kunde(m, kunden, anfragen.EIGENE)[0]
                try:
                    erkannt = bestellung.erkennen(db, text, kundennr)
                except Exception:
                    erkannt = None
                if erkannt:
                    info.update(art="bestellung", erkannt=erkannt, text=text)
                else:
                    try:
                        treffer = wiederholanfrage.treffer(db, kundennr, text)
                    except Exception:
                        treffer = []
                    if treffer:
                        info.update(art="wiederholung", kundennr=kundennr, treffer=treffer)
            info = self._ohne[k]
            if info["art"] == "nachtrag":
                verschoben.append(d.name)
            elif info["art"] == "bestellung":
                verschoben.append(d.name)       # eigene Zeile statt „Ohne STEP“
                a = info["erkannt"]["angebot"]
                self._links[f"best:{len(self._links)}"] = lambda d=d, i=info: self.bestellung_pruefen(d, i)
                zeilen.append(f"<b>Bestellung</b> zu Angebot <b>{a.get('nummer')}</b> ({a.get('kunde') or ''}): "
                              f"{d.name} – <a href='{list(self._links)[-1]}'>Bestellung prüfen …</a>")
            elif info["art"] == "wiederholung":
                verschoben.append(d.name)
                n = len(info["treffer"])
                self._links[f"wdh:{len(self._links)}"] = lambda d=d, i=info: self.wiederholanfrage(d, i)
                zeilen.append(f"<b>Wiederholanfrage</b> von {anfragen.kunde_text(kunden, info['kundennr'])}: "
                              f"{n} bekannte Artikel in {d.name} – <a href='{list(self._links)[-1]}'>Artikel "
                              "übernehmen …</a>")
        if neu_verschoben:
            self.f.meldung(f"Nachtrag zu Angebot {', '.join(neu_verschoben)} in den Angebotsordner gelegt; Änderungen "
                           "zeigt das Angebot beim Öffnen (Rückgängig: Datei → Automatik-Protokoll).")
        return zeilen, verschoben

    def _link(self, href):
        if href in self._links:
            self._links[href]()
        else:
            self._kunde_markieren(href)

    def bestellung_pruefen(self, pfad, info, dialog=None):
        """Fenster „Bestellung prüfen“ (1a). Ergebnis: True, wenn beauftragt."""
        from . import bestellung_dialog
        ok = bestellung_dialog.pruefen(self.f, pfad, info["erkannt"], info["text"], dialog)
        self.neu_laden(erzwingen=True)
        return ok

    def wiederholanfrage(self, pfad, info, auswahl=None):
        """Wiederholanfrage (6a): bekannte Artikel wählen, neues Angebot mit den Positionen des neuesten Angebots und
        den angefragten Stückzahlen; die Mail kommt in den Angebotsordner. auswahl = Zeilennummern (Tests).
        Ergebnis: ID des neuen Angebots oder None."""
        from pathlib import Path
        from . import automatik, wiederholanfrage
        from .tabelle_dialog import TabellenDialog
        treffer = info["treffer"]
        if auswahl is None:
            if self.f.stumm:
                return None
            gewaehlt = []
            zeilen = [[r["artikel"], r.get("bezeichnung") or "", r.get("nummer") or "",
                       r["menge"] if r.get("menge") else "–"] for r in treffer]
            d = TabellenDialog(self.f, "Wiederholanfrage", f"Bekannte Artikel in {Path(pfad).name}. Markieren und "
                               "„Neues Angebot aus Auswahl“: Positionen des letzten Angebots, Stückzahlen aus der Mail, "
                               "Preise nach den aktuellen Stammdaten.", ("Artikel", "Bezeichnung", "Zuletzt in Angebot",
                                                                          "Angefragt Stk"), zeilen,
                               [("Neues Angebot aus Auswahl", lambda m: (gewaehlt.extend(m or range(len(treffer))),
                                                                         d.accept()))])
            d.tabelle.selectAll()
            d.exec()
            auswahl = gewaehlt
        liste = [treffer[i] for i in auswahl if 0 <= i < len(treffer)]
        if not liste:
            return None
        seiten = getattr(self.f, "seiten", None)
        i = seiten[0].katalog_angebot(info["kundennr"], liste) if seiten else None
        if i is None:
            return None
        n = wiederholanfrage.stueck_setzen(self.f.db, i, liste)
        kopf = self.f.db.angebot(i) or {}
        try:
            automatik.verschieben(self.f.db, pfad, Path(self.f.angebot_ordner(kopf)) / "Anfrage", "wiederholanfrage",
                                  f"Angebot {kopf.get('nummer')} aus Wiederholanfrage {Path(pfad).name}: {len(liste)} "
                                  f"Artikel, {n} Stückzahl(en) aus der Mail", i)
        except OSError as e:
            self.f.meldung(f"Wiederholanfrage: Mail nicht verschoben ({fehler_text(e)}).", fehler=True)
        seite = self.f.angebot_oeffnen(i)
        if seite is not None and hasattr(seite, "neu_laden"):
            seite.neu_laden()
        self.neu_laden(erzwingen=True)
        return i

    def _anfrage(self, it):
        schl = it.data(Qt.ItemDataRole.UserRole)
        return next((a for a in self.anfragen if a.schluessel == schl), None)

    def markierte(self):
        return [a for a in map(self._anfrage, self.liste.selectedItems()) if a is not None]

    def _knoepfe_setzen(self):
        n = len(self.markierte())
        self.knopf_oeffnen.setEnabled(n == 1 or (n == 0 and bool(self.anfragen)))
        self.knopf_zusammen.setEnabled(n > 1)
        from . import teilen
        self.knopf_zuweisen.setVisible(teilen.aktiv(self.f.db))
        self.knopf_zuweisen.setEnabled(n == 1)

    def zuweisen(self, auswahl, an=None, notiz=""):
        """Anfrage einem Kollegen zuweisen (ohne an: Auswahl); „(niemand)“ hebt die Zuweisung auf. Ergebnis: True."""
        from . import teilen
        if not auswahl:
            return False
        a = auswahl[0]
        ich = teilen.kuerzel(self.f.db)
        if an is None:
            if self.f.stumm:
                return False
            namen = {k: f"{k} – {n}" if n else k for k, n in teilen.kollegen(self.f.db).items()}
            namen[ich] = f"{ich} (ich)"
            eintraege = list(namen.values()) + ["(niemand)"]
            wahl, gut = QInputDialog.getItem(self.f, "Anfrage zuweisen", f"„{a.name}“ zuweisen an:", eintraege, 0, False)
            if not gut:
                return False
            an = next((k for k, t in namen.items() if t == wahl), "")
            if an:
                notiz, gut = QInputDialog.getText(self.f, "Anfrage zuweisen", "Notiz (darf leer sein):")
                if not gut:
                    return False
        try:
            anfragen.zuweisen(a, self.ordner(), an, ich, notiz)
        except OSError as e:
            self.f.meldung(f"Anfrage lässt sich nicht zuweisen: {fehler_text(e)}", fehler=True)
            return False
        self.f.meldung(f"Anfrage „{a.name}“ " + (f"an {an} zugewiesen." if an else "nicht mehr zugewiesen."))
        self.neu_laden(erzwingen=True)
        return True

    def _kunde_markieren(self, kundennr):
        self.liste.clearSelection()
        for i in range(self.liste.count()):
            a = self._anfrage(self.liste.item(i))
            if a and str(a.kunde) == kundennr and not a.gesperrt:
                self.liste.item(i).setSelected(True)

    def ordner_oeffnen(self):
        if self.ordner():
            self.f.datei_oeffnen(self.ordner())

    def _vorlesen(self, liste):
        """Formulare offener Anfragen im Hintergrund lesen (ein Formular nach dem anderen)."""
        from . import formular
        for a in liste:
            if a.gesperrt:
                continue
            for d in a.formulare:
                k = _schluessel(d)
                if k not in self._gelesen and k not in self._laeuft:
                    self._pool = self._pool or ThreadPoolExecutor(max_workers=1)
                    self._laeuft[k] = self._pool.submit(formular.datei_lesen, d, self.f.programmordner)
        if self._laeuft and not self._warten.isActive():
            self._warten.start()

    def _lesen_pruefen(self):
        fertig = [k for k, f in self._laeuft.items() if f.done()]
        for k in fertig:
            self._gelesen[k] = self._ergebnis(self._laeuft.pop(k))
        gemessen = self._vorab_pruefen()
        if not self._laeuft and not self._vorab_laeuft:
            self._warten.stop()
        if fertig or gemessen:
            self.neu_laden(erzwingen=True)

    @staticmethod
    def _ergebnis(future):
        try:
            return future.result()
        except Exception:
            return None

    def formular_lesen(self, d):
        """Gelesenes Formular (dict text/ocr/unsicher) oder None; wartet auf das Lesen im Hintergrund bzw. liest jetzt
        (Sanduhr)."""
        from . import formular
        k = _schluessel(d)
        if self._gelesen.get(k):
            return self._gelesen[k]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if k in self._laeuft:
                self._gelesen[k] = self._ergebnis(self._laeuft.pop(k))
            if not self._gelesen.get(k):         # vorher verschoben (Sperre) oder noch nie gelesen
                self._gelesen[k] = formular.datei_lesen(d, self.f.programmordner)
        finally:
            QApplication.restoreOverrideCursor()
        return self._gelesen[k]

    def _formulare(self, gesperrt):
        """Anfrageformulare und E-Mails lesen (Plan W6b/W6c, Mail 28.10.2026, anfragen.werte): Anfragenummer ins Feld
        „Ihre Anfrage“ und in den Ordnernamen 'Kunde – Nummer', dazu Stückzahlen, Kunde, Lieferzeit, Bemerkung und
        Werkstoff aus der Mail. Ändert gesperrt (neue Pfade). Ergebnis: weitere Werte für neu_aus_step."""
        from . import mail
        gelesen = [g for g in (self.formular_lesen(d) for a in gesperrt for d in a.formulare) if g]
        mails = [m for m in (mail.lesen(d) for a in gesperrt for d in a.mails) if m]
        kunde, nummer, weitere = anfragen.werte(self.f.db, gelesen, mails,
                                                next((a.kunde for a in gesperrt if a.kunde), None))
        if nummer and len(gesperrt) == 1:
            try:
                gesperrt[0] = anfragen.umbenennen(gesperrt[0], anfragen.ordner_name(
                    anfragen.kunde_text(self.f.db.zeilen("kunden"), kunde) if kunde else "", nummer))
            except OSError:
                pass            # Ordner offen (Explorer): Name bleibt
        if kunde:
            for a in gesperrt:
                a.kunde = a.kunde or kunde
        return weitere

    def oeffnen(self, auswahl, zusammen=False, kundennr=None):
        """Anfragen als ein neues Angebot aus STEP öffnen (ohne Auswahl: die älteste offene). Sperren, Anhänge der
        Mails auspacken, importieren,
        danach die Dateien in den Angebotsordner verschieben; bei Abbruch Sperre aufheben. kundennr: ohne Kundenwahl
        (Tests). Ergebnis: Angebotsseite oder None."""
        ich = self.f.db.einstellung("benutzer_kuerzel") or ""
        frei = [a for a in self.anfragen if not a.gesperrt and a.zugewiesen.get("an") in (None, "", ich)]
        frei.sort(key=lambda a: a.zugewiesen.get("an") != ich)       # mir zugewiesene zuerst (sonst älteste)
        auswahl = [a for a in auswahl if a] or frei[:1]
        if not auswahl:
            return None
        if len(auswahl) > 1 and not zusammen:
            auswahl = auswahl[:1]
        kuerzel = self.f.db.einstellung("benutzer_kuerzel") or ""
        fremd = [a for a in auswahl if a.gesperrt and a.gesperrt != kuerzel]
        if fremd and not self.f.stumm and QMessageBox.question(
                self.f, "Anfrage öffnen", f"„{fremd[0].name}“ ist in Bearbeitung von {fremd[0].gesperrt}. "
                "Trotzdem öffnen?") != QMessageBox.Yes:
            return None
        andere = [a for a in auswahl if a.zugewiesen.get("an") not in (None, "", kuerzel)]
        if andere and not fremd and not self.f.stumm and QMessageBox.question(
                self.f, "Anfrage öffnen", f"„{andere[0].name}“ ist {andere[0].zugewiesen['an']} zugewiesen. "
                "Trotzdem öffnen?") != QMessageBox.Yes:
            return None
        gesperrt = []
        try:
            for a in auswahl:
                gesperrt.append(anfragen.sperren(a, self.ordner(), kuerzel))
                gesperrt[-1] = anfragen.auspacken(gesperrt[-1])      # Fehler: Sperre wird unten aufgehoben
        except OSError as e:
            for a in gesperrt:
                anfragen.freigeben(a)
            self.f.meldung(f"Anfrage lässt sich nicht öffnen: {fehler_text(e)}", fehler=True)
            return None
        weitere = self._formulare(gesperrt)                         # kann den Ordner umbenennen
        dateien = [str(d) for a in gesperrt for d in a.step]
        kontakt = weitere.pop("kontakt", None)         # Signatur (12a): erst nach erfolgreichem Import speichern
        seite = self.f.angebote.neu_aus_step(dateien, kundennr, **weitere)
        if seite is not None and kontakt and str(seite.kopf.get("kundennr")) == str(kontakt["kundennr"]):
            try:
                anfragen.kontakt_uebernehmen(self.f.db, kontakt)
            except Exception:
                pass
        if seite is None:
            for a in gesperrt:
                anfragen.freigeben(a)
            self.neu_laden(erzwingen=True)
            return None
        try:                # V1 Reaktionszeit (vertrieb.py): Eingang der ältesten Anfrage am Angebot merken
            from . import vertrieb
            eingaenge = [e for e in (anfrage_vorab.eingang(a) for a in gesperrt) if e]
            vertrieb.eingang_merken(self.f.db, seite.id, min(eingaenge) if eingaenge else None)
        except Exception:
            pass
        try:
            ziel = self.f.angebot_ordner(seite.kopf)
        except OSError as e:
            self.f.meldung(f"Anfrage übernommen, Dateien nicht verschoben: {fehler_text(e)}", fehler=True)
            self.neu_laden(erzwingen=True)
            return seite
        n, fehler = 0, []
        for a in gesperrt:
            k, f = anfragen.verschieben(a, ziel, angebotsordner.STEP_ORDNER)
            n, fehler = n + k, fehler + f
        self.f.meldung(f"Anfrage übernommen: {n} Datei(en) nach {ziel} verschoben"
                       + (f" (nicht verschoben: {'; '.join(fehler)})" if fehler else "."), fehler=bool(fehler))
        self.neu_laden(erzwingen=True)
        return seite


def _schluessel(d):
    """Formular wiedererkennen, auch nach dem Verschieben in einen Unterordner: Name, Größe, Änderungszeit."""
    try:
        st = d.stat()
        return d.name, st.st_size, st.st_mtime_ns
    except OSError:
        return d.name, None, None


def _punkt(farbe):
    """Farbiger Punkt als Symbol der Ampel."""
    pm = QPixmap(12, 12)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(farbe))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 10, 10)
    p.end()
    return QIcon(pm)
