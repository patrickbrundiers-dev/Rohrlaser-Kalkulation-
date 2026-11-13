"""Seite „Anfragen“ (Patrick 12.11.2026, Konzept „Outlook-Anbindung und Anfragenverwaltung“, Paket 1).

Oben eine Zählerleiste Neu · In Bearbeitung · Erledigt · Meine (ein Klick filtert), dazu Suche und Filter. Links die
Liste der Anfragen, rechts die gewählte Anfrage: Mailtext, Anhänge, verknüpfte Angebote, Notizen und Verlauf, darunter
die Knöpfe je Status (Übernehmen, Kalkulieren, Als erledigt markieren …). Die Daten kommen aus den Akten
(anfragen_akten.py); neue Anfragen erfasst die Karte „Neue Anfragen“ der Startseite aus dem Anfrage-Ordner. Alle
AKTUALISIEREN_S Sekunden sieht die Seite in die Akten (Übernahmen anderer Arbeitsplätze)."""
import datetime
import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from . import anfragen_akten as ak
from .klartext import fehler_text

AKTUALISIEREN_S = 30
SPALTEN = ("Nr.", "Kunde / Absender", "Betreff", "Eingang", "Anhänge", "Priorität", "Bearbeiter", "Status")
FARBE = {ak.NEU: "#8A94A6", ak.BEARBEITUNG: "#2F6FB3", ak.ERLEDIGT: "#2F7D4F"}     # dezent: Rand/Schrift
PRIO_FARBE = {"eilt": "#B42318", "hoch": "#A66A00"}
ORDNER = (("neu", "Neu"), ("in_bearbeitung", "In Bearbeitung"), ("erledigt", "Erledigt"), ("meine", "Meine"))
ERLEDIGT_TAGE = 90          # Erledigt zeigt standardmäßig die letzten 90 Tage


def _zeit(d):
    return d.strftime("%d.%m.%Y %H:%M") if d else ""


class AnfragenSeite(QWidget):
    def __init__(self, fenster):
        super().__init__()
        self.f = fenster
        self.db = fenster.db
        self.titel = "Anfragen"
        self.akten, self._gewaehlt, self._mailtexte = [], None, {}
        self.ordner = "neu"
        lay = QVBoxLayout(self)
        # Zählerleiste
        oben = QHBoxLayout()
        self.gruppe = QButtonGroup(self)
        self.gruppe.setExclusive(True)
        self.zaehler = {}
        for key, text in ORDNER:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setObjectName("anfragen_zaehler")
            b.setMinimumHeight(40)
            b.clicked.connect(lambda _=False, k=key: self.ordner_waehlen(k))
            self.gruppe.addButton(b)
            self.zaehler[key] = b
            oben.addWidget(b)
        self.zaehler["neu"].setChecked(True)
        oben.addStretch(1)
        filter_ = QHBoxLayout()         # zweite Zeile: Suche und Filter (passt auch in schmale Fenster)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Kunde, Betreff, Text, Datei, Angebot …")
        self.suche.setClearButtonEnabled(True)
        self.suche.setMinimumWidth(320)
        self.suche.textChanged.connect(lambda _t: self.liste_fuellen())
        filter_.addWidget(self.suche, 2)
        self.filter_bearbeiter = QComboBox()
        self.filter_bearbeiter.setToolTip("Nur Anfragen dieses Bearbeiters")
        self.filter_bearbeiter.currentIndexChanged.connect(lambda _i: self.liste_fuellen())
        filter_.addWidget(self.filter_bearbeiter)
        self.filter_prio = QComboBox()
        self.filter_prio.addItem("Alle Prioritäten", "")
        for p in reversed(ak.PRIORITAETEN):
            self.filter_prio.addItem(ak.PRIORITAET_TEXT[p], p)
        self.filter_prio.currentIndexChanged.connect(lambda _i: self.liste_fuellen())
        filter_.addWidget(self.filter_prio)
        self.filter_zeit = QComboBox()
        for text, tage in (("Letzte 90 Tage", ERLEDIGT_TAGE), ("Letztes Jahr", 365), ("Alle", 0)):
            self.filter_zeit.addItem(text, tage)
        self.filter_zeit.setToolTip("Zeitraum für Erledigt")
        self.filter_zeit.currentIndexChanged.connect(lambda _i: self.liste_fuellen())
        filter_.addWidget(self.filter_zeit)
        knopf = QPushButton("Mitarbeiter")
        knopf.setToolTip("Offene und erledigte Anfragen je Mitarbeiter, mittlere Bearbeitungsdauer")
        knopf.clicked.connect(self.mitarbeiter_zeigen)
        oben.addWidget(knopf)
        knopf = QPushButton("Aktualisieren")
        knopf.clicked.connect(lambda: self.neu_laden(eingang=True))
        oben.addWidget(knopf)
        lay.addLayout(oben)
        lay.addLayout(filter_)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setVisible(False)
        lay.addWidget(self.hinweis)

        teiler = QSplitter(Qt.Horizontal)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setAlternatingRowColors(True)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabelle.itemSelectionChanged.connect(self._gewaehlt_neu)
        self.tabelle.itemActivated.connect(lambda _it: self.hauptaktion())
        teiler.addWidget(self.tabelle)

        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(8, 0, 0, 0)
        self.kopf = QLabel()
        self.kopf.setWordWrap(True)
        self.kopf.setTextFormat(Qt.RichText)
        rl.addWidget(self.kopf)
        self.inhalt = QTextBrowser()
        self.inhalt.setOpenLinks(False)
        self.inhalt.anchorClicked.connect(self._link)
        rl.addWidget(self.inhalt, 1)
        zeile = QHBoxLayout()
        self.wahl_bearbeiter = QComboBox()
        self.wahl_bearbeiter.setToolTip("Bearbeiter für Übernehmen bzw. Bearbeiter ändern")
        zeile.addWidget(self.wahl_bearbeiter)
        self.k_uebernehmen = QPushButton("Übernehmen")
        self.k_uebernehmen.setObjectName("primaer")
        self.k_uebernehmen.setToolTip("Anfrage für den gewählten Bearbeiter übernehmen (Enter)")
        self.k_uebernehmen.clicked.connect(lambda: self.uebernehmen())
        self.k_zuweisen = QPushButton("Zuweisen")
        self.k_zuweisen.setToolTip("Neue Anfrage dem gewählten Mitarbeiter vorschlagen (er übernimmt sie selbst)")
        self.k_zuweisen.clicked.connect(lambda: self.zuweisen())
        self.k_bearbeiter = QPushButton("Bearbeiter ändern")
        self.k_bearbeiter.clicked.connect(lambda: self.bearbeiter_aendern())
        self.k_kalkulieren = QPushButton("Kalkulieren")
        self.k_kalkulieren.setObjectName("primaer")
        self.k_kalkulieren.setToolTip("Neues Angebot aus den Dateien der Anfrage, mit der Anfrage verknüpft")
        self.k_kalkulieren.clicked.connect(lambda: self.kalkulieren())
        for b in (self.k_uebernehmen, self.k_zuweisen, self.k_bearbeiter, self.k_kalkulieren):
            zeile.addWidget(b)
        zeile.addStretch(1)
        rl.addLayout(zeile)
        zeile = QHBoxLayout()
        self.wahl_prio = QComboBox()
        for p in ak.PRIORITAETEN:
            self.wahl_prio.addItem(ak.PRIORITAET_TEXT[p], p)
        self.wahl_prio.setToolTip("Priorität")
        self.wahl_prio.activated.connect(lambda _i: self.prioritaet(self.wahl_prio.currentData()))
        zeile.addWidget(self.wahl_prio)
        self.k_notiz = QPushButton("Notiz …")
        self.k_notiz.clicked.connect(lambda: self.notiz())
        self.k_stand = QPushButton("Bearbeitungsstand …")
        self.k_stand.clicked.connect(lambda: self.bearbeitungsstand())
        self.k_zurueck = QPushButton("Zurückgeben")
        self.k_zurueck.setToolTip("Zurück nach Neu, ein anderer kann sie übernehmen")
        self.k_zurueck.clicked.connect(lambda: self.zurueckgeben())
        self.k_erledigt = QPushButton("Als erledigt markieren")
        self.k_erledigt.clicked.connect(lambda: self.erledigen())
        self.k_wieder = QPushButton("Wieder öffnen")
        self.k_wieder.clicked.connect(lambda: self.wieder_oeffnen())
        for b in (self.k_notiz, self.k_stand, self.k_zurueck, self.k_erledigt, self.k_wieder):
            zeile.addWidget(b)
        zeile.addStretch(1)
        rl.addLayout(zeile)
        teiler.addWidget(rechts)
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 2)
        teiler.setSizes([780, 620])
        lay.addWidget(teiler, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.neu_laden)
        self.timer.start(AKTUALISIEREN_S * 1000)
        self.neu_laden()

    # ------------------------------------------------------------------ Daten
    def ablage(self):
        return ak.ablage(self.db)

    def ich(self):
        return ak.kuerzel(self.db)

    def mitarbeiter_liste(self):
        from . import teilen
        namen = {self.ich(): f"{self.ich()} (ich)"}
        try:
            for k, n in teilen.kollegen(self.db).items():
                namen[k] = f"{k} – {n}" if n else k
        except Exception:
            pass
        for a in self.akten:
            for k in (a.bearbeiter, a.stand["zugewiesen"]):
                if k and k not in namen:
                    namen[k] = k
        return namen

    def neu_laden(self, eingang=False):
        """Akten neu lesen; eingang: vorher den Anfrage-Ordner ansehen (Karte der Startseite)."""
        if eingang:
            karte = getattr(getattr(self.f, "start", None), "anfragen", None)
            if karte is not None:
                karte.neu_laden(erzwingen=True)
        try:
            self.akten = self.ablage().alle()
            self.hinweis.setVisible(False)
        except OSError as e:
            self.akten = []
            self.hinweis.setText(f"Anfragen nicht lesbar: {fehler_text(e)}")
            self.hinweis.setVisible(True)
        self._zaehler_setzen()
        self._auswahl_fuellen()
        self.liste_fuellen()

    def _zaehler_setzen(self):
        z = ak.zaehlen(self.akten, self.ich())
        for key, text in ORDNER:
            self.zaehler[key].setText(f"{text}  {z[key]}")
        warten = sum(a.wartet() for a in self.akten)
        self.zaehler["neu"].setToolTip(f"{warten} Anfrage(n) warten seit über {ak.ERINNERN_STUNDEN} Stunden"
                                       if warten else "Neue Anfragen, noch nicht übernommen")
        try:
            i = self.f.reiter.indexOf(self)
            if i >= 0:
                self.f.reiter.setTabText(i, f"Anfragen ({z['neu']})" if z["neu"] else "Anfragen")
        except Exception:
            pass

    def _auswahl_fuellen(self):
        namen = self.mitarbeiter_liste()
        for box, alle in ((self.filter_bearbeiter, "Alle Bearbeiter"), (self.wahl_bearbeiter, None)):
            alt = box.currentData()
            box.blockSignals(True)
            box.clear()
            if alle:
                box.addItem(alle, "")
            for k, t in namen.items():
                box.addItem(t, k)
            i = box.findData(alt if alt is not None else (self.ich() if not alle else ""))
            box.setCurrentIndex(max(0, i))
            box.blockSignals(False)

    def sichtbare(self):
        tage = self.filter_zeit.currentData() if self.ordner == ak.ERLEDIGT else 0
        seit = datetime.datetime.now() - datetime.timedelta(days=tage) if tage else None
        return ak.filtern(self.akten, self.ordner, self.ich(), self.suche.text(),
                          self.filter_bearbeiter.currentData() or "", self.filter_prio.currentData() or "", seit)

    def liste_fuellen(self):
        alt = self._gewaehlt
        liste = self.sichtbare()
        self.tabelle.setSortingEnabled(False)
        self.tabelle.setRowCount(len(liste))
        kunden = {}
        try:
            kunden = {str(k.get("kundennr")): k.get("name") or "" for k in self.db.zeilen("kunden")}
        except Exception:
            pass
        for r, a in enumerate(liste):
            arten = {}
            for d in a.dateien():
                if d["art"] != "mail":
                    arten[d["art"]] = arten.get(d["art"], 0) + 1
            mails = sum(1 for d in a.dateien() if d["art"] == "mail")
            if not arten and mails:
                arten = {"mail": mails}
            anh = ", ".join(f"{n} {ak.ART_TEXT[x]}" for x, n in arten.items())
            kunde = kunden.get(a.kunde) or a.kopf.get("kunde_name") or a.absender or a.kopf.get("absender", "")
            werte = (a.nr, kunde, a.betreff, _zeit(a.eingang), anh, ak.PRIORITAET_TEXT.get(a.prioritaet, ""),
                     a.bearbeiter or (f"für {a.stand['zugewiesen']}" if a.stand["zugewiesen"] else ""),
                     ak.STATUS_TEXT[a.status] + (" · wartet" if a.wartet() else ""))
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                it.setData(Qt.ItemDataRole.UserRole, a.nr)
                if c == 7:
                    it.setForeground(QColor(FARBE[a.status]))
                if c == 5 and a.prioritaet in PRIO_FARBE:
                    it.setForeground(QColor(PRIO_FARBE[a.prioritaet]))
                if c == 0:
                    it.setToolTip(a.kopf.get("kurz", ""))
                if ak.ist_meine(a, self.ich()) and c in (0, 2):
                    s = it.font()
                    s.setBold(True)
                    it.setFont(s)
                self.tabelle.setItem(r, c, it)
        zeile = next((r for r, a in enumerate(liste) if a.nr == alt), 0 if liste else -1)
        if zeile >= 0:
            self.tabelle.selectRow(zeile)
            self._gewaehlt = liste[zeile].nr
            self._zeigen(liste[zeile])        # gleiche Zeile wie vorher: kein Signal, Inhalt trotzdem neu
        else:
            self._gewaehlt = None
            self._zeigen(None)

    def _gewaehlt_neu(self):
        it = self.tabelle.selectedItems()
        nr = it[0].data(Qt.ItemDataRole.UserRole) if it else None
        self._gewaehlt = nr
        self._zeigen(self.akte())

    def akte(self, nr=None):
        nr = nr or self._gewaehlt
        return next((a for a in self.akten if a.nr == nr), None)

    def waehlen(self, nr):
        """Anfrage wählen (Tests, Links): Ordner passend umschalten."""
        a = self.akte(nr)
        if a is None:
            return None
        if self.ordner not in (a.status, None) and not (self.ordner == "meine" and ak.ist_meine(a, self.ich())):
            self.ordner_waehlen(a.status)
        self._gewaehlt = nr
        self.liste_fuellen()
        return a

    def ordner_waehlen(self, key):
        self.ordner = key
        self.zaehler[key].setChecked(True)
        self.liste_fuellen()

    # ------------------------------------------------------------------ Anzeige
    def _mailtext(self, a):
        """Ganzer Text der ersten Mail der Akte (gelesen mit mail.py), sonst der Kurztext."""
        from . import mail
        if a.nr in self._mailtexte:
            return self._mailtexte[a.nr]
        text = ""
        for d in a.dateien():
            if d["art"] == "mail" and d["pfad"].exists():
                m = mail.lesen(d["pfad"])
                if m is not None:
                    text = m.text
                    break
        self._mailtexte[a.nr] = text or a.kopf.get("kurz", "")
        return self._mailtexte[a.nr]

    def _zeigen(self, a):
        self._knoepfe(a)
        if a is None:
            self.kopf.setText("<i>Keine Anfrage gewählt</i>")
            self.inhalt.clear()
            return
        e = html.escape
        s = a.stand
        absender = a.kopf.get("absender_name") or ""
        adresse = a.kopf.get("absender") or ""
        zeilen = [f"<b style='font-size:14px'>{e(a.betreff)}</b>",
                  f"{e(a.nr)} · <span style='color:{FARBE[a.status]}'>{ak.STATUS_TEXT[a.status]}</span>"
                  + (f" · {e(ak.PRIORITAET_TEXT[a.prioritaet])}" if a.prioritaet != "normal" else ""),
                  f"Von {e(absender)} &lt;{e(adresse)}&gt;" if adresse else (f"Von {e(absender)}" if absender else ""),
                  f"Eingang {_zeit(a.eingang)}"
                  + (f" · übernommen {ak._zeit_text(s['uebernommen_am'])} von {e(a.bearbeiter)}" if a.bearbeiter
                     else (f" · vorgeschlagen für {e(s['zugewiesen'])}" if s["zugewiesen"] else ""))
                  + (f" · erledigt {ak._zeit_text(s['erledigt_am'])}" if s["erledigt_am"] else "")]
        self.kopf.setText("<br>".join(z for z in zeilen if z))
        teile = []
        if s["stand"]:
            teile.append(f"<p><b>Bearbeitungsstand:</b> {e(s['stand'])}</p>")
        if s["angebote"]:
            teile.append("<p><b>Angebote:</b> " + ", ".join(
                f"<a href='angebot:{e(n)}'>{e(n)}</a>{e(self._angebot_text(n))}" for n in s["angebote"]) + "</p>")
        dateien = a.dateien()
        if dateien:
            li = []
            for d in dateien:
                gr = f"{(d.get('groesse') or 0) / 1024:.0f} KB"
                w = f" <span style='color:#B42318'>{e(d['warnung'])}</span>" if d["warnung"] else ""
                if d.get("aus_mail"):
                    w += " <span style='color:#666'>(Anhang der Mail)</span>"
                if d.get("gesperrt"):
                    li.append(f"<li>{e(d['name'])}{w}</li>")
                    continue
                li.append(f"<li><a href='datei:{e(d.get('datei', d['name']))}'>{e(d['name'])}</a> "
                          f"<span style='color:#666'>{ak.ART_TEXT[d['art']]}, {gr}</span>{w}</li>")
            teile.append(f"<p><b>Anhänge ({len(dateien)}):</b></p><ul>{''.join(li)}</ul>"
                         "<p><a href='ordner:'>Ordner der Anfrage öffnen</a></p>")
        text = self._mailtext(a)
        if text:
            teile.append("<p><b>Nachricht:</b></p><p>" + e(text).replace("\n", "<br>") + "</p>")
        if s["notizen"]:
            teile.append("<p><b>Interne Notizen:</b></p><ul>" + "".join(
                f"<li>{ak._zeit_text(n['zeit'])} {e(n['kuerzel'])}: {e(n['text'])}</li>" for n in s["notizen"])
                + "</ul>")
        verlauf = sorted(a.verlauf, key=lambda x: (x.get("zeit", ""), x.get("kuerzel", ""), x.get("nr", 0)))
        teile.append("<p><b>Verlauf:</b></p><p style='color:#555'>"
                     + "<br>".join(e(ak.verlauf_text(x)) for x in verlauf) + "</p>")
        self.inhalt.setHtml("".join(teile))

    def _angebot_text(self, nummer):
        """Summe netto und Stand des Angebots, z. B. „ (1.234,50 € netto, versendet)“."""
        try:
            z = self.db.con.execute("SELECT vk_netto, stand FROM angebote WHERE nummer=? ORDER BY id DESC LIMIT 1",
                                    (nummer,)).fetchone()
        except Exception:
            return ""
        if not z:
            return ""
        teile = []
        if z[0]:
            teile.append(f"{z[0]:,.2f} € netto".replace(",", "X").replace(".", ",").replace("X", "."))
        if z[1]:
            teile.append(str(z[1]))
        return f" ({', '.join(teile)})" if teile else ""

    def _knoepfe(self, a):
        from . import admin_schutz
        lesen = bool(getattr(self.db, "nur_lesen", False))
        st = a.status if a else None
        ich = self.ich()
        admin = admin_schutz.ist_admin(self.db)
        eigen = bool(a and (a.bearbeiter == ich or admin))
        self.k_uebernehmen.setVisible(st == ak.NEU)
        self.k_zuweisen.setVisible(st == ak.NEU)
        self.k_bearbeiter.setVisible(st == ak.BEARBEITUNG)
        self.k_kalkulieren.setVisible(st in (ak.NEU, ak.BEARBEITUNG))
        self.k_zurueck.setVisible(st == ak.BEARBEITUNG)
        self.k_erledigt.setVisible(st == ak.BEARBEITUNG)
        self.k_wieder.setVisible(st == ak.ERLEDIGT)
        for b in (self.k_uebernehmen, self.k_zuweisen, self.k_kalkulieren, self.k_notiz, self.k_stand,
                  self.wahl_prio, self.wahl_bearbeiter):
            b.setEnabled(bool(a) and not lesen)
        for b in (self.k_bearbeiter, self.k_zurueck, self.k_erledigt, self.k_wieder):
            b.setEnabled(bool(a) and not lesen and eigen)
        if a:
            self.wahl_prio.setCurrentIndex(max(0, self.wahl_prio.findData(a.prioritaet)))
            vorschlag = a.stand["zugewiesen"] or a.bearbeiter or ich
            i = self.wahl_bearbeiter.findData(vorschlag)
            if i >= 0:
                self.wahl_bearbeiter.setCurrentIndex(i)

    def _link(self, url):
        a = self.akte()
        t = url.toString()
        art, _, wert = t.partition(":")
        if art == "angebot":
            self.angebot_oeffnen(wert)
        elif art == "datei" and a:
            d = next((d for d in a.dateien() if d.get("datei", d["name"]) == wert), None)
            if d is None:
                return
            if d.get("gesperrt") or ak.Path(d["name"]).suffix.lower() in ak.GEFAEHRLICH:
                self.f.meldung(f"{d['name']}: ausführbare Datei, wird aus Sicherheitsgründen nicht geöffnet.",
                               fehler=True)
                return
            if d["warnung"] and not self.f.stumm and QMessageBox.question(
                    self, "Anhang öffnen", f"{d['name']}\n{d['warnung']}\n\nTrotzdem öffnen?") != QMessageBox.Yes:
                return
            self.f.datei_oeffnen(d["pfad"])
        elif art == "ordner" and a:
            self.f.datei_oeffnen(a.pfad / ak.DATEIEN)

    def angebot_oeffnen(self, nummer):
        z = self.db.con.execute("SELECT id FROM angebote WHERE nummer=? ORDER BY id DESC LIMIT 1",
                                (nummer,)).fetchone()
        if not z:
            self.f.meldung(f"Angebot {nummer} gibt es hier nicht (noch nicht abgeglichen?).", fehler=True)
            return None
        return self.f.angebot_oeffnen(z[0])

    # ------------------------------------------------------------------ Aktionen
    def _ausfuehren(self, tun, text=None):
        a = self.akte()
        if a is None:
            return None
        try:
            neu = tun(self.ablage(), a)
        except ak.SchonUebernommen as e:
            self.f.meldung(str(e), fehler=True)
            if not self.f.stumm:
                QMessageBox.information(self, "Anfrage übernehmen", str(e))
            self.neu_laden()
            return None
        except (ak.AblageFehler, OSError) as e:
            self.f.meldung(f"{a.nr}: {fehler_text(e) if isinstance(e, OSError) else e}", fehler=True)
            self.neu_laden()
            return None
        if text:
            self.f.meldung(text.format(nr=a.nr))
        self.neu_laden()
        return neu

    def hauptaktion(self):
        a = self.akte()
        if a and a.status == ak.NEU:
            return self.uebernehmen()
        if a and a.status == ak.BEARBEITUNG:
            return self.kalkulieren()
        return None

    def uebernehmen(self, bearbeiter=None):
        """Anfrage übernehmen (ein Klick): Bearbeiter, Zeit, Status In Bearbeitung; die Originale im Anfrage-Ordner
        kommen in dessen Unterordner .uebernommen."""
        bearbeiter = bearbeiter or self.wahl_bearbeiter.currentData() or self.ich()
        neu = self._ausfuehren(lambda abl, a: abl.uebernehmen(a, bearbeiter),
                               "Anfrage {nr} übernommen" + (f" für {bearbeiter}." if bearbeiter != self.ich() else "."))
        if neu is not None:
            self._eingang_ablegen(neu)
            self.ordner_waehlen(ak.BEARBEITUNG)
            self.waehlen(neu.nr)
        return neu

    def _eingang_ablegen(self, akte):
        karte = getattr(getattr(self.f, "start", None), "anfragen", None)
        if karte is None or not karte.ordner():
            return 0
        abl = self.ablage()
        n = 0
        for a in list(karte.anfragen):
            z = ak.akte_zu(abl, a)
            if z is not None and z.nr == akte.nr:
                n += ak.eingang_ablegen(a, karte.ordner(), akte.nr)
        if n:
            karte.neu_laden(erzwingen=True)
        return n

    def zuweisen(self, an=None):
        an = an if an is not None else (self.wahl_bearbeiter.currentData() or "")
        return self._ausfuehren(lambda abl, a: abl.zuweisen(a, an),
                                "Anfrage {nr} " + (f"für {an} vorgeschlagen." if an else "nicht mehr zugewiesen."))

    def bearbeiter_aendern(self, an=None):
        an = an or self.wahl_bearbeiter.currentData()
        return self._ausfuehren(lambda abl, a: abl.bearbeiter_aendern(a, an), f"Anfrage {{nr}}: Bearbeiter {an}.")

    def prioritaet(self, wert):
        return self._ausfuehren(lambda abl, a: abl.prioritaet(a, wert))

    def notiz(self, text=None):
        if text is None:
            if self.f.stumm:
                return None
            text, gut = QInputDialog.getMultiLineText(self, "Interne Notiz", "Notiz (sehen alle Kollegen):")
            if not gut or not text.strip():
                return None
        return self._ausfuehren(lambda abl, a: abl.notiz(a, text), "Notiz zu {nr} gespeichert.")

    def bearbeitungsstand(self, text=None):
        a = self.akte()
        if text is None:
            if self.f.stumm or a is None:
                return None
            text, gut = QInputDialog.getText(self, "Bearbeitungsstand", "Stand (z. B. „Rückfrage Werkstoff offen“):",
                                             text=a.stand["stand"])
            if not gut:
                return None
        return self._ausfuehren(lambda abl, a: abl.bearbeitungsstand(a, text))

    def erledigen(self):
        return self._ausfuehren(lambda abl, a: abl.erledigen(a), "Anfrage {nr} erledigt.")

    def wieder_oeffnen(self):
        return self._ausfuehren(lambda abl, a: abl.wieder_oeffnen(a), "Anfrage {nr} wieder in Bearbeitung.")

    def zurueckgeben(self):
        return self._ausfuehren(lambda abl, a: abl.zurueckgeben(a), "Anfrage {nr} zurück nach Neu.")

    def kalkulieren(self, kundennr=None):
        """Neues Angebot aus den Dateien der Anfrage (Arbeitskopie, die Akte bleibt vollständig): derselbe Weg wie
        „Öffnen“ in der Karte (auspacken, Formular und Mail lesen, Prüfdialog, Angebotsordner). Eine neue Anfrage wird
        dabei übernommen. Danach sind Anfrage und Angebot verknüpft. kundennr: ohne Kundenwahl (Tests).
        Ergebnis: Angebotsseite oder None."""
        import shutil
        a = self.akte()
        if a is None:
            return None
        if a.status == ak.NEU:
            a = self.uebernehmen(self.ich())
            if a is None:
                return None
        karte = getattr(getattr(self.f, "start", None), "anfragen", None)
        if karte is None:
            return None
        try:
            arbeit = ak.arbeitskopie(a)
        except OSError as e:
            self.f.meldung(f"Dateien der Anfrage nicht kopierbar: {fehler_text(e)}", fehler=True)
            return None
        if not arbeit.step_anzahl():
            shutil.rmtree(arbeit.ordner, ignore_errors=True)
            self.f.meldung(f"Anfrage {a.nr} hat keine STEP-Datei: Teile bitte von Hand im neuen Angebot anlegen.",
                           fehler=True)
            return None
        try:
            seite = karte.oeffnen([arbeit], kundennr=kundennr)
        finally:
            shutil.rmtree(arbeit.ordner, ignore_errors=True)
        self.neu_laden()
        if seite is not None:
            self.waehlen(a.nr)
        return seite

    def mitarbeiter_zeigen(self):
        d = MitarbeiterDialog(self, self.akten, self.mitarbeiter_liste())
        if not self.f.stumm:
            d.exec()
        return d


class MitarbeiterDialog(QDialog):
    """Je Mitarbeiter: offene, erledigte und vorgeschlagene Anfragen, mittlere Zeit bis zur Übernahme und Bearbeitung."""

    def __init__(self, parent, akten, namen):
        super().__init__(parent)
        self.setWindowTitle("Anfragen je Mitarbeiter")
        lay = QVBoxLayout(self)
        werte = ak.mitarbeiter(akten)
        t = QTableWidget(len(werte), 6)
        t.setHorizontalHeaderLabels(("Mitarbeiter", "Offen", "Erledigt", "Vorgeschlagen", "Ø bis Übernahme",
                                     "Ø Bearbeitung"))
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, (k, w) in enumerate(werte.items()):
            for c, v in enumerate((namen.get(k, k), w["offen"], w["erledigt"], w["zugewiesen"],
                                   ak.dauer_text(w["std_bis_uebernahme"]), ak.dauer_text(w["std_bearbeitung"]))):
                t.setItem(r, c, QTableWidgetItem(str(v)))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle = t
        lay.addWidget(t)
        knopf = QDialogButtonBox(QDialogButtonBox.Close)
        knopf.rejected.connect(self.reject)
        lay.addWidget(knopf)
        self.resize(640, 320)
