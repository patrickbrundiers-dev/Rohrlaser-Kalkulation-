"""Datei → KI-Zentrale … (KI-Plattform, Master-Prompt Patrick 20.11.2026, Punkte 2 und 6): Dashboard und Verwaltung.

Reiter
  Übersicht     KI-Status, Modelle, Geschwindigkeit, CPU/GPU-Last, RAM/VRAM, analysierte Kalkulationen, erkannte
                Fehler, offene Empfehlungen, Lernfortschritt, Datenqualität, letzte Lernvorgänge, die zehn Agenten
  Modelle       Sprachmodell ein/aus, Ollama-Ordner (Programm startet Ollama selbst, nur dieser PC, Cloud aus),
                Server, Modellliste mit Testen, Rollen (automatisch oder fest), Import aus Modell-Ordner (*.gguf)
  Empfehlungen  offene KI-Empfehlungen: Öffnen (Angebot), Erledigt, Ablehnen
  Lernen        Lernhistorie aller Lernsysteme (Zurücknehmen bei Kennwerten), reife Vorschläge mit Vergleich alt/neu,
                verdächtige Lerndaten, Lernzentrale
  Wissen        Suche in der Wissensdatenbank mit Quelle und Stand, Index neu bauen
  Protokoll     alle KI-Aktionen
Ändern (Modelle, Zurücknehmen) nur mit Admin-Recht, sobald ein Admin-Passwort gesetzt ist."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import ki_agenten, ki_lernhistorie, ki_modelle, ki_protokoll, ki_ressourcen, ki_wissen


def darf_verwalten(db, f=None):
    """Modelle, Server und Zurücknehmen ändern: ohne Admin-Passwort jeder, sonst nur freigeschalteter Admin."""
    try:
        from . import admin_schutz
        return admin_schutz.ist_admin(db)
    except Exception:           # noqa: BLE001
        return True


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(list(spalten))
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.verticalHeader().setVisible(False)
    return t


def _fuellen(t, zeilen):
    t.setRowCount(len(zeilen))
    for r, z in enumerate(zeilen):
        for c, w in enumerate(z):
            t.setItem(r, c, QTableWidgetItem("" if w is None else str(w)))


def _gb(v):
    return "–" if v is None else f"{v:.1f} GB".replace(".", ",")


class KiZentrale(QDialog):
    def __init__(self, f, senden=None):
        super().__init__(f)
        self.f, self.db, self.senden = f, f.db, senden
        self.setWindowTitle("KI-Zentrale")
        self.resize(1150, 680)
        self.liste = []
        lay = QVBoxLayout(self)
        self.reiter = QTabWidget()
        lay.addWidget(self.reiter)
        self._uebersicht()
        self._modelle()
        self._empfehlungen()
        self._lernen()
        self._wissen()
        self._protokoll()
        leiste = QDialogButtonBox(QDialogButtonBox.Close)
        leiste.rejected.connect(self.reject)
        self.neu_knopf = leiste.addButton("Aktualisieren", QDialogButtonBox.ActionRole)
        self.neu_knopf.clicked.connect(self.neu_laden)
        lay.addWidget(leiste)
        self.uhr = QTimer(self)
        self.uhr.setInterval(5000)
        self.uhr.timeout.connect(lambda: self._ressourcen_setzen())
        self.uhr.start()
        self.neu_laden()

    # ------------------------------------------------------------------ Übersicht
    def _uebersicht(self):
        w = QWidget()
        g = QGridLayout(w)
        self.status = {}
        felder = (("ki", "KI-Status"), ("modelle", "Geladene Modelle"), ("tempo", "Modellgeschwindigkeit"),
                  ("cpu", "CPU"), ("ram", "RAM"), ("gpu", "GPU / VRAM"), ("passend", "Passende Modelle"), ("analysiert", "Analysierte Kalkulationen"),
                  ("fehler", "Erkannte Fehler und Warnungen"), ("einsparung", "Einsparpotenziale (Hinweise)"),
                  ("offen", "Offene KI-Empfehlungen"), ("lernen", "Lernfortschritt"), ("qualitaet", "Datenqualität"),
                  ("letzte", "Letzte Lernvorgänge"), ("wissen", "Wissensdatenbank"))
        box = QGroupBox("Status")
        form = QFormLayout(box)
        for name, titel in felder:
            lbl = QLabel("…")
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.status[name] = lbl
            form.addRow(titel, lbl)
        g.addWidget(box, 0, 0)
        abox = QGroupBox("Fach-Agenten (alle Zahlen aus der Programmlogik)")
        al = QVBoxLayout(abox)
        self.agenten_tabelle = _tabelle(("Agent", "Aufgabe", "Quellen"))
        _fuellen(self.agenten_tabelle, [[a.titel, a.aufgabe, ", ".join(a.quellen)] for a in ki_agenten.AGENTEN])
        al.addWidget(self.agenten_tabelle)
        g.addWidget(abox, 0, 1)
        g.setColumnStretch(1, 1)
        self.reiter.addTab(w, "Übersicht")

    def _ressourcen_setzen(self, immer=False):
        if not immer and not self.isVisible():      # Uhr: nur messen, solange das Fenster zu sehen ist
            return None
        r = ki_ressourcen.messen()
        self.status["cpu"].setText(f"{r['cpu_kerne']} Kerne, Last {r['cpu_last_pct'] if r['cpu_last_pct'] is not None else '–'} %"
                                   f", Programm {r['prozess_mb'] or '–'} MB")
        self.status["ram"].setText(f"{_gb(r['ram_frei_gb'])} frei von {_gb(r['ram_gesamt_gb'])}"
                                   f" ({r['ram_last_pct'] or '–'} % belegt)")
        gpus = r["gpus"]
        self.status["gpu"].setText("; ".join(f"{x['name']}: {_gb(x['vram_frei_gb'])} von {_gb(x['vram_gesamt_gb'])} frei, "
                                             f"Last {x['last_pct']:.0f} %" for x in gpus) if gpus else
                                   "keine NVIDIA-GPU, Modelle laufen auf der CPU")
        self.status["passend"].setText(ki_ressourcen.empfehlung(r))
        return r

    def neu_laden(self):
        st = ki_modelle.status(self.db, senden=self.senden, liste=self._modelle_laden())
        self.status["ki"].setText(st["text"] + ("" if st["aktiv"] else " (Modelle → „Sprachmodell benutzen“)"))
        self.status["modelle"].setText(", ".join(f"{m['name']} ({m['server']})" for m in self.liste
                                                 if m.get("geladen") and m.get("name")) or "keines geladen")
        mess = ki_modelle.messungen(self.db)
        self.status["tempo"].setText(", ".join(f"{n}: {v['tokens_s']} Token/s" for n, v in mess.items()
                                               if v.get("tokens_s")) or "noch nicht gemessen (Modelle → Testen)")
        self._ressourcen_setzen(immer=True)
        z = ki_protokoll.zaehlen(self.db)
        self.status["analysiert"].setText(f"{z['angebote']} Angebote in {z['pruefungen']} Prüfungen, "
                                          f"{z['fragen']} Fragen an den Assistenten")
        offen = ki_protokoll.empfehlungen(self.db)
        self.status["fehler"].setText(f"{z['befunde_fehler']} insgesamt, davon "
                                      f"{sum(1 for e in offen if e['art'] in ('FEHLER', 'WARNUNG'))} offen")
        self.status["einsparung"].setText(str(sum(1 for e in offen if e["agent"] in ("Material-KI", "Kalkulations-KI")
                                                  and e["art"] in ("HINWEIS", "VORSCHLAG", "WARNUNG"))))
        self.status["offen"].setText(f"{len(offen)} (übernommen {z['uebernommen']}, abgelehnt {z['abgelehnt']})")
        try:
            ls = ki_lernhistorie.lernstand(self.db)
            self.status["lernen"].setText(f"{ls['kennwerte_aktiv']} freigegebene Kennwerte, {ls['reif']} reife "
                                          f"Vorschläge, {ls['gelernt']} Einträge Lernzentrale, {ls['bg_zeiten']} "
                                          f"BG-Zeiten, {ls['nachkalkuliert']} nachkalkulierte Aufträge")
            self.status["qualitaet"].setText("noch keine Lerndaten" if ls["datenqualitaet_pct"] is None else
                                             f"{ls['datenqualitaet_pct']} % unauffällig ({ls['verdaechtig']} "
                                             f"verdächtige von {ls['faelle']} Fällen)")
        except Exception as e:  # noqa: BLE001
            self.status["lernen"].setText(f"nicht lesbar: {e}")
        self.historie = ki_lernhistorie.eintraege(self.db)
        self.status["letzte"].setText("; ".join(f"{e['datum'][:10]} {e['titel']}" for e in self.historie[:3]) or "–")
        wi = ki_wissen.info(self.db)
        self.status["wissen"].setText(f"{wi['n']} Dokumente, gebaut {wi['gebaut']}" if wi["n"] else
                                      "Index wird bei der ersten Suche gebaut")
        self._modelle_setzen()
        self._empfehlungen_setzen(offen)
        self._lernen_setzen()
        self._protokoll_setzen()

    # ------------------------------------------------------------------ Modelle
    def _modelle(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.aktiv_haken = QCheckBox("Sprachmodell benutzen (nur auf diesem PC bzw. im eigenen Netz; aus = alles "
                                     "regelbasiert)")
        self.aktiv_haken.toggled.connect(self._aktiv_setzen)
        v.addWidget(self.aktiv_haken)
        self.schloss = QLabel("Ändern nur als Admin: in den Einstellungen mit dem Schloss freischalten.")
        self.schloss.setStyleSheet("color:#B45309")
        v.addWidget(self.schloss)
        form = QFormLayout()
        z1 = QHBoxLayout()
        self.ollama_feld = QLineEdit()
        self.ollama_feld.setPlaceholderText(r"z. B. \\Server\Rohrlaser\KI\Ollama (entpackte ZIP-Datei)")
        k1 = QPushButton("Wählen …")
        k1.clicked.connect(lambda: self._ordner_waehlen(self.ollama_feld, ki_modelle.OLLAMA_ORDNER))
        self.start_knopf = QPushButton("Ollama starten")
        self.start_knopf.clicked.connect(self._ollama_starten)
        for x in (self.ollama_feld, k1, self.start_knopf):
            z1.addWidget(x)
        form.addRow("Ollama-Ordner", z1)
        z2 = QHBoxLayout()
        self.server_feld = QLineEdit()
        self.server_art = QComboBox()
        for a, t in ki_modelle.ARTEN.items():
            self.server_art.addItem(t, a)
        k2 = QPushButton("Übernehmen")
        k2.clicked.connect(self._server_setzen)
        for x in (self.server_feld, self.server_art, k2):
            z2.addWidget(x)
        form.addRow("Server-Adresse", z2)
        v.addLayout(form)
        self.modell_tabelle = _tabelle(("Modell", "Server", "Größe", "Parameter", "Quantisierung", "Geladen", "VRAM",
                                        "Art", "Geschwindigkeit", "Hinweis"))
        v.addWidget(self.modell_tabelle)
        z3 = QHBoxLayout()
        self.test_knopf = QPushButton("Testen")
        self.test_knopf.clicked.connect(self._testen)
        z3.addWidget(self.test_knopf)
        self.rollen_combo = {}
        for r, t, hilfe in ki_modelle.ROLLEN:
            c = QComboBox()
            c.setToolTip(hilfe)
            c.currentIndexChanged.connect(lambda _i, r=r, c=c: self._rolle_setzen(r, c))
            self.rollen_combo[r] = c
            z3.addWidget(QLabel(t))
            z3.addWidget(c)
        z3.addStretch(1)
        v.addLayout(z3)
        box = QGroupBox("Modell importieren (ohne Internet)")
        bl = QVBoxLayout(box)
        z4 = QHBoxLayout()
        self.ordner_feld = QLineEdit()
        self.ordner_feld.setPlaceholderText(r"z. B. \\Server\Rohrlaser\KI\Modelle")
        k4 = QPushButton("Wählen …")
        k4.clicked.connect(lambda: self._ordner_waehlen(self.ordner_feld, ki_modelle.MODELL_ORDNER))
        for x in (self.ordner_feld, k4):
            z4.addWidget(x)
        bl.addLayout(z4)
        self.datei_tabelle = _tabelle(("Datei", "Größe"))
        self.datei_tabelle.setMaximumHeight(130)
        bl.addWidget(self.datei_tabelle)
        self.import_knopf = QPushButton("Importieren")
        self.import_knopf.clicked.connect(lambda: self._importieren())
        bl.addWidget(self.import_knopf, 0, Qt.AlignLeft)
        v.addWidget(box)
        self.reiter.addTab(w, "Modelle")

    def _modelle_laden(self):
        self.liste = ki_modelle.modelle(self.db, senden=self.senden) if ki_modelle.aktiv(self.db) else []
        return self.liste

    def _modelle_setzen(self):
        frei = darf_verwalten(self.db, self.f)
        self.schloss.setVisible(not frei)
        self.aktiv_haken.blockSignals(True)
        self.aktiv_haken.setChecked(ki_modelle.aktiv(self.db))
        self.aktiv_haken.blockSignals(False)
        for x in (self.aktiv_haken, self.server_feld, self.import_knopf, self.start_knopf):
            x.setEnabled(frei)
        s = ki_modelle.server_liste(self.db)[0]
        self.server_feld.setText(s["url"])
        self.server_art.setCurrentIndex(max(0, self.server_art.findData(s["art"])))
        self.ollama_feld.setText(str(self.db.einstellung(ki_modelle.OLLAMA_ORDNER) or ""))
        self.ordner_feld.setText(str(self.db.einstellung(ki_modelle.MODELL_ORDNER) or ""))
        mess = ki_modelle.messungen(self.db)
        _fuellen(self.modell_tabelle, [[m["name"] or "–", m["server"], _gb(m["groesse_gb"]), m["parameter"],
                                        m["quantisierung"], "ja" if m["geladen"] else "", _gb(m["vram_gb"]) if
                                        m["vram_gb"] is not None else "", "Einbettung" if m["einbettung"] else "Text",
                                        f"{(mess.get(m['name']) or {}).get('tokens_s') or ''} Token/s"
                                        if (mess.get(m["name"]) or {}).get("tokens_s") else "", m["fehler"]]
                                       for m in self.liste])
        echte = [m for m in self.liste if m.get("name")]
        gew = ki_modelle.rollen(self.db)
        for r, c in self.rollen_combo.items():
            c.blockSignals(True)
            c.clear()
            auto = ki_modelle.waehlen(self.liste, r)
            c.addItem(f"automatisch ({auto['name']})" if auto else "automatisch", "")
            for m in echte:
                if (r == ki_modelle.EINBETTUNG) == bool(m["einbettung"]):
                    c.addItem(m["name"], m["name"])
            c.setCurrentIndex(max(0, c.findData(gew.get(r, ""))))
            c.setEnabled(frei)
            c.blockSignals(False)
        self._dateien_setzen()

    def _dateien_setzen(self):
        self.dateien = ki_modelle.dateien(self.ordner_feld.text().strip())
        _fuellen(self.datei_tabelle, [[d["name"], _gb(d["groesse_gb"])] for d in self.dateien])

    def _aktiv_setzen(self, an):
        self.db.einstellung_setzen(ki_modelle.AKTIV, "ja" if an else "nein")
        ki_protokoll.schreiben(self.db, "KI-Zentrale", "einstellung", ergebnis=f"Sprachmodell {'an' if an else 'aus'}")
        self.neu_laden()

    def _ordner_waehlen(self, feld, einst, pfad=None):
        p = pfad or QFileDialog.getExistingDirectory(self, "Ordner wählen", feld.text())
        if p:
            feld.setText(p)
            self.db.einstellung_setzen(einst, p)
            self._dateien_setzen()
        return p

    def _ollama_starten(self):
        q = self.ollama_feld.text().strip()
        if q:
            self.db.einstellung_setzen(ki_modelle.OLLAMA_ORDNER, q)
        try:
            r = ki_modelle.ollama_starten(self.db, senden=self.senden)
        except ki_modelle.KiFehler as e:
            r = dict(ok=False, text=str(e))
        ki_protokoll.schreiben(self.db, "KI-Zentrale", "ollama_starten", ergebnis=r["text"],
                               status="ok" if r["ok"] else "fehler")
        self.f.meldung(r["text"], fehler=not r["ok"])
        self.neu_laden()
        return r

    def _server_setzen(self):
        try:
            ki_modelle.server_setzen(self.db, [dict(name="Modell-Server", art=self.server_art.currentData(),
                                                    url=self.server_feld.text().strip())])
        except ki_modelle.KiFehler as e:
            self.f.meldung(str(e), fehler=True)
            return False
        self.neu_laden()
        return True

    def _rolle_setzen(self, rolle, combo):
        ki_modelle.rolle_setzen(self.db, rolle, combo.currentData() or "")

    def _testen(self):
        reihen = sorted({i.row() for i in self.modell_tabelle.selectedIndexes()}) or range(len(self.liste))
        texte = []
        for r in reihen:
            m = self.liste[r]
            if not m.get("name"):
                continue
            e = ki_modelle.testen(self.db, m, senden=self.senden)
            texte.append(f"{m['name']}: " + (f"{e['tokens_s'] or '–'} Token/s, {e['dauer_s']} s" if e["ok"]
                                             else e["fehler"]))
            ki_protokoll.schreiben(self.db, "KI-Zentrale", "modelltest", ergebnis=texte[-1], modell=m["name"],
                                   dauer=e.get("dauer_s") or 0, status="ok" if e["ok"] else "fehler")
        if texte:
            self.f.meldung(" · ".join(texte))
        self.neu_laden()
        return texte

    def _importieren(self, ausfuehren=None):
        reihen = sorted({i.row() for i in self.datei_tabelle.selectedIndexes()}) or range(len(self.dateien))
        texte = []
        for r in reihen:
            d = self.dateien[r]
            e = ki_modelle.importieren(d["pfad"], ausfuehren=ausfuehren)
            texte.append(f"{d['name']}: {e['text']}")
            ki_protokoll.schreiben(self.db, "KI-Zentrale", "import", ergebnis=texte[-1], modell=e["name"],
                                   status="ok" if e["ok"] else "fehler")
        if texte:
            self.f.meldung(" · ".join(texte), fehler=not all("Importiert" in t for t in texte))
        self.neu_laden()
        return texte

    # ------------------------------------------------------------------ Empfehlungen
    def _empfehlungen(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Offene Empfehlungen der KI-Prüfungen. Nichts ändert sich von selbst: „Öffnen“ zeigt das "
                           "Angebot, dort erledigt man den Punkt wie gewohnt."))
        self.empf_tabelle = _tabelle(("Art", "Agent", "Angebot", "Empfehlung", "Quelle", "Seit"))
        self.empf_tabelle.doubleClicked.connect(lambda _i: self._empf_oeffnen())
        v.addWidget(self.empf_tabelle)
        z = QHBoxLayout()
        for t, fn in (("Öffnen", self._empf_oeffnen), ("Erledigt", lambda: self._empf_status(ki_protokoll.ERLEDIGT)),
                      ("Ablehnen", lambda: self._empf_status(ki_protokoll.ABGELEHNT))):
            k = QPushButton(t)
            k.clicked.connect(fn)
            z.addWidget(k)
        z.addStretch(1)
        v.addLayout(z)
        self.reiter.addTab(w, "Empfehlungen")

    def _empfehlungen_setzen(self, offen):
        self.offen = offen
        nummern = {}
        try:
            nummern = {a["id"]: a.get("nummer") for a in self.db.angebote()}
        except Exception:       # noqa: BLE001
            pass
        _fuellen(self.empf_tabelle, [[e["art"], e["agent"], nummern.get(e["angebot_id"], e["angebot_id"] or ""),
                                      e["text"], ", ".join(e["quellen"]) if isinstance(e["quellen"], list) else "",
                                      (e["erstellt"] or "")[:16]] for e in offen])
        self.reiter.setTabText(2, f"Empfehlungen ({len(offen)})")

    def _markiert(self, t):
        return sorted({i.row() for i in t.selectedIndexes()})

    def _empf_oeffnen(self):
        for r in self._markiert(self.empf_tabelle)[:1]:
            e = self.offen[r]
            if e["angebot_id"] and hasattr(self.f, "angebot_oeffnen"):
                seite = self.f.angebot_oeffnen(e["angebot_id"])
                if seite is not None and e.get("ziel") and hasattr(seite, "check_link"):
                    seite.check_link(e["ziel"])
                self.accept()

    def _empf_status(self, status):
        for r in self._markiert(self.empf_tabelle):
            ki_protokoll.empfehlung_setzen(self.db, self.offen[r]["id"], status)
        self.neu_laden()

    # ------------------------------------------------------------------ Lernen
    def _lernen(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Alle Lernwerte mit Stand und Version. Kalkulationsparameter ändern sich nur nach Freigabe "
                           "(Lernzentrale → Kennwerte prüfen); jede Freigabe lässt sich zurücknehmen."))
        self.lern_tabelle = _tabelle(("Quelle", "Lernwert", "Was", "Datum", "Version", "Status"))
        v.addWidget(self.lern_tabelle)
        z = QHBoxLayout()
        self.zurueck_knopf = QPushButton("Zurücknehmen")
        self.zurueck_knopf.clicked.connect(self._zuruecknehmen)
        k2 = QPushButton("Lernzentrale …")
        k2.clicked.connect(lambda: self.f.lernzentrale() if hasattr(self.f, "lernzentrale") else None)
        for x in (self.zurueck_knopf, k2):
            z.addWidget(x)
        z.addStretch(1)
        v.addLayout(z)
        v.addWidget(QLabel("Reife Vorschläge und verdächtige Lerndaten"))
        self.vorschlag_tabelle = _tabelle(("Art", "Vorschlag / Befund", "Quelle"))
        v.addWidget(self.vorschlag_tabelle)
        z2 = QHBoxLayout()
        self.vergleich_knopf = QPushButton("Vergleich alt/neu …")
        self.vergleich_knopf.setToolTip("Rechnet Prüfangebote bzw. die letzten beauftragten Angebote mit und ohne den "
                                        "Vorschlag – nichts wird gespeichert")
        self.vergleich_knopf.clicked.connect(self._vergleich)
        z2.addWidget(self.vergleich_knopf)
        self.vergleich_text = QLabel("")
        self.vergleich_text.setWordWrap(True)
        z2.addWidget(self.vergleich_text, 1)
        v.addLayout(z2)
        self.reiter.addTab(w, "Lernen")

    def _lernen_setzen(self):
        _fuellen(self.lern_tabelle, [[e["quelle"], e["titel"], e["was"], (e["datum"] or "")[:16], e["version"],
                                      e["status"]] for e in self.historie])
        self.zurueck_knopf.setEnabled(darf_verwalten(self.db, self.f))
        try:
            self.vorschlaege = ki_lernhistorie.offene_vorschlaege(self.db)
        except Exception:       # noqa: BLE001
            self.vorschlaege = []
        try:
            verd = ki_lernhistorie.fehlerhafte_daten(self.db)
        except Exception:       # noqa: BLE001
            verd = []
        _fuellen(self.vorschlag_tabelle, [["Vorschlag", f"{v['titel']}: {v['text']}", v["quelle"]]
                                          for v in self.vorschlaege] +
                 [["Lerndaten prüfen", x["text"], x["quelle"]] for x in verd])

    def _zuruecknehmen(self):
        n = 0
        for r in self._markiert(self.lern_tabelle):
            n += ki_lernhistorie.zuruecknehmen(self.db, self.historie[r])
        self.f.meldung(f"{n} Werte zurückgesetzt." if n else "Nur aktive Kennwerte lassen sich hier zurücknehmen.")
        self.neu_laden()
        return n

    def _vergleich(self):
        r = (self._markiert(self.vorschlag_tabelle) or [0])[0]
        if r >= len(self.vorschlaege) or self.vorschlaege[r]["quelle"] != "Kennwerte":
            self.vergleich_text.setText("Bitte einen Kennwert-Vorschlag markieren.")
            return None
        e = ki_lernhistorie.vergleich(self.db, self.vorschlaege[r]["vorschlag"])
        teile = [e["text"]] + [f"{a['nummer']}: {a['alt']} → {a['neu']} € ({a['prozent']} %)" for a in e["angebote"][:6]]
        self.vergleich_text.setText("\n".join(teile))
        ki_protokoll.schreiben(self.db, "Lern-KI", "vergleich", ergebnis=e["text"])
        return e

    # ------------------------------------------------------------------ Wissen
    def _wissen(self):
        w = QWidget()
        v = QVBoxLayout(w)
        z = QHBoxLayout()
        self.such_feld = QLineEdit()
        self.such_feld.setPlaceholderText("Suchen in Angeboten, Kunden, Zukauf, Stammdaten, Regeln, Anleitung …")
        self.such_feld.returnPressed.connect(lambda: self._suchen())
        k = QPushButton("Suchen")
        k.clicked.connect(lambda: self._suchen())
        k2 = QPushButton("Index neu bauen")
        k2.clicked.connect(lambda: (ki_wissen.index(self.db, neu=True), self.neu_laden()))
        for x in (self.such_feld, k, k2):
            z.addWidget(x)
        v.addLayout(z)
        self.such_tabelle = _tabelle(("Treffer", "Quelle", "Stand", "Weg", "Auszug"))
        self.such_tabelle.doubleClicked.connect(lambda _i: self._treffer_oeffnen())
        v.addWidget(self.such_tabelle)
        self.reiter.addTab(w, "Wissen")

    def _suchen(self, text=None):
        q = text if isinstance(text, str) else self.such_feld.text()
        self.treffer = ki_wissen.suchen(self.db, q, 30, senden=self.senden) if q.strip() else []
        _fuellen(self.such_tabelle, [[t["titel"], t["quelle"], (t["stand"] or "")[:16], t["weg"], t["text"][:160]]
                                     for t in self.treffer])
        ki_protokoll.schreiben(self.db, "Wissensdatenbank", "suche", frage=q, ergebnis=f"{len(self.treffer)} Treffer")
        return self.treffer

    def _treffer_oeffnen(self):
        for r in self._markiert(self.such_tabelle)[:1]:
            z = self.treffer[r]["ziel"]
            if z.startswith("angebot:") and hasattr(self.f, "angebot_oeffnen"):
                self.f.angebot_oeffnen(int(z.split(":")[1]))
                self.accept()

    # ------------------------------------------------------------------ Protokoll
    def _protokoll(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.prot_tabelle = _tabelle(("Zeit", "Wer", "Agent", "Aktion", "Frage", "Ergebnis", "Modell", "Dauer [s]",
                                      "Status"))
        v.addWidget(self.prot_tabelle)
        self.reiter.addTab(w, "Protokoll")

    def _protokoll_setzen(self):
        _fuellen(self.prot_tabelle, [[a["zeit"], a["benutzer"], a["agent"], a["aktion"], (a["frage"] or "")[:80],
                                      (a["ergebnis"] or "")[:120], a["modell"], a["dauer"], a["status"]]
                                     for a in ki_protokoll.liste(self.db, 500)])


def zeigen(f, dialog=None, senden=None):
    d = KiZentrale(f, senden=senden)
    if dialog:
        dialog(d)
    else:
        d.exec()
    d.uhr.stop()
    return d
