"""Dialog 'Schneidweg berechnen …' einer Position ohne STEP-Datei: Enden (gerade, Gehrung oder Ausklinkung),
Innenkonturen (Bohrung, Langloch, Rechteck, Schlitz, Polygon aus Koordinaten, sonstige Kontur) und Gravur eingeben;
Skizze, Schnittlängen, Einstiche, Konturklassen, Gewinde-Vorschlag und die Schneidzeit mit den Schneiddaten der
Maschine stehen sofort daneben. Die Formeln stehen in schneidweg.py; OK schreibt die Werte in die Position
(Angebotsseite.schneidweg_berechnen)."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton, QSizePolicy, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import rechnen, schneidweg as sw
from .stammdaten import zahl_aus_text

KONTUR_SPALTEN = ("Art", "Anzahl", "Maß 1 [mm]", "Maß 2 [mm]", "Maß 3 [mm]", "Lage ab Anfang [mm]", "Text")
TEXT_SPALTE, LAGE_SPALTE = 6, 5
ERGEBNIS_SPALTEN = ("Schnitt", "Anzahl", "je Stück [mm]", "gesamt [mm]", "Einstiche", "Hüllmaß [mm]", "Klasse")
MASS_HILFE = ("Maße: Bohrung Ø · Langloch Länge, Breite · Rechteck Breite, Höhe, Eckradius · Schlitz (offen, vom "
              "Rand) Tiefe, Breite · Polygon Eckpunkte in Maß 1, z. B. 0,0; 40,0; 40,20; 0,20 · sonstige Kontur "
              "Schnittlänge, Hüllmaß (leer = groß). Lage ab Anfang nur für die Skizze (leer = verteilt).")


def _zahl(text):
    t = (text or "").strip()
    if not t:
        return None
    try:
        return zahl_aus_text(t)
    except ValueError:
        return None


class SchneidwegDialog(QDialog):
    """p: Position, profil: Stammdaten-Zeile des Profils, kopf/k/tabellen: Angebot und Stammdaten (Maschine,
    Konturgrenzen, Schneiddaten). Nach OK: self.eingaben (dict) und self.ergebnis (schneidweg.rechnen)."""

    def __init__(self, parent, p, profil, kopf, k, tabellen):
        super().__init__(parent)
        self.p, self.profil, self.kopf, self.k, self.tabellen = p, profil, kopf, k, tabellen
        self.grenzen, vorgabe = rechnen.kontur_grenzen(rechnen.maschine(kopf, k))
        self.gewinde = gewinde_liste(tabellen)
        self.ergebnis = None
        e = sw.lesen(p.get("technik"))
        self.setWindowTitle(f"Schneidweg berechnen – Pos. {p.get('pos') or ''} {p.get('artikel') or ''}".strip())
        self.resize(1000, 760)
        lay = QVBoxLayout(self)
        form = profil.get("form")
        info = QLabel(f"Profil {p.get('profil_id')} ({form}), Werkstoff {p.get('werkstoff_id') or '–'}, Maschine "
                      f"{kopf.get('maschine') or '–'}, Konturgrenzen klein bis {rechnen.zahl(self.grenzen[0])} mm, "
                      f"mittel bis {rechnen.zahl(self.grenzen[1])} mm" + (" (Vorgabe)" if vorgabe else ""))
        info.setWordWrap(True)
        lay.addWidget(info)

        enden = QGridLayout()
        self.winkel, self.achse, self.sattel = {}, {}, {}
        for r, (seite, titel) in enumerate((("a", "Anfangsschnitt"), ("b", "Endschnitt"))):
            w = QDoubleSpinBox()
            w.setRange(0, 79.9)
            w.setDecimals(1)
            w.setSuffix(" °")
            w.setSpecialValueText("gerade")
            w.setValue(sw._z(e[seite].get("winkel")))
            w.setToolTip("Gehrung: Abweichung vom rechtwinkligen Schnitt (0° = gerader Schnitt)")
            w.valueChanged.connect(self.rechnen)
            a = QComboBox()
            a.addItems(sw.ACHSEN)
            a.setCurrentText(e[seite].get("achse") or sw.ACHSEN[0])
            a.setEnabled(form != "Rundrohr")
            a.setToolTip("Richtung, in die die Gehrung läuft (Höhe = Maß a, Breite = Maß b des Profils)")
            a.currentTextChanged.connect(self.rechnen)
            sa = QDoubleSpinBox()
            sa.setRange(0, 2000)
            sa.setDecimals(1)
            sa.setSuffix(" mm")
            sa.setSpecialValueText("keine")
            sa.setValue(sw._z(e[seite].get("sattel")))
            sa.setEnabled(form == "Rundrohr")
            sa.setToolTip("Ausklinkung (Sattelschnitt): Ø des Rundrohrs, auf das dieses Ende rechtwinklig gesetzt wird")
            sa.valueChanged.connect(self.rechnen)
            self.winkel[seite], self.achse[seite], self.sattel[seite] = w, a, sa
            enden.addWidget(QLabel(titel + ": Gehrung"), r, 0)
            enden.addWidget(w, r, 1)
            enden.addWidget(a, r, 2)
            enden.addWidget(QLabel("Ausklinkung auf Rundrohr Ø"), r, 3)
            enden.addWidget(sa, r, 4)
        self.gravur = QDoubleSpinBox()
        self.gravur.setRange(0, 100000)
        self.gravur.setDecimals(1)
        self.gravur.setSuffix(" mm")
        self.gravur.setValue(sw._z(e.get("gravur")))
        self.gravur.valueChanged.connect(self.rechnen)
        enden.addWidget(QLabel("Gravur (Länge)"), 2, 0)
        enden.addWidget(self.gravur, 2, 1)
        enden.setColumnStretch(5, 1)
        lay.addLayout(enden)

        lay.addWidget(QLabel("<b>Innenkonturen</b>"))
        self.tabelle = QTableWidget(0, len(KONTUR_SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(KONTUR_SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        for i, b in enumerate((130, 60, 150, 80, 80, 140)):
            self.tabelle.setColumnWidth(i, b)
        self.tabelle.horizontalHeader().setSectionResizeMode(TEXT_SPALTE, QHeaderView.Stretch)
        self.tabelle.itemChanged.connect(self.rechnen)
        lay.addWidget(self.tabelle, 1)
        hilfe = QLabel(MASS_HILFE)
        hilfe.setWordWrap(True)
        hilfe.setStyleSheet("color: #595959;")
        lay.addWidget(hilfe)
        leiste = QHBoxLayout()
        for art in sw.ARTEN:
            b = QPushButton(f"+ {art}")
            b.clicked.connect(lambda _=False, art=art: self.zeile_neu(dict(art=art, anzahl=1)))
            leiste.addWidget(b)
        weg = QPushButton("Markierte entfernen")
        weg.clicked.connect(self._entfernen)
        leiste.addStretch(1)
        leiste.addWidget(weg)
        lay.addLayout(leiste)

        self.skizze = Skizze(profil, p.get("laenge"))
        lay.addWidget(self.skizze)
        lay.addWidget(QLabel("<b>Ergebnis je Teil</b>"))
        self.ergebnis_tabelle = QTableWidget(0, len(ERGEBNIS_SPALTEN))
        self.ergebnis_tabelle.setHorizontalHeaderLabels(ERGEBNIS_SPALTEN)
        self.ergebnis_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ergebnis_tabelle.verticalHeader().setVisible(False)
        self.ergebnis_tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self.ergebnis_tabelle, 1)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        self.summe.setTextFormat(Qt.RichText)
        lay.addWidget(self.summe)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("In Position übernehmen")
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.ok_knopf = knoepfe.button(QDialogButtonBox.Ok)
        for z in e["konturen"]:
            self.zeile_neu(z, rechnen_=False)
        self.rechnen()

    # ------------------------------------------------------------------ Eingaben
    def zeile_neu(self, z, rechnen_=True):
        self.tabelle.blockSignals(True)
        r = self.tabelle.rowCount()
        self.tabelle.insertRow(r)
        art = QComboBox()
        art.addItems(sw.ARTEN)
        art.setCurrentText(z.get("art") or sw.BOHRUNG)
        art.currentTextChanged.connect(lambda _=None, art=art: self._art_geaendert(art))
        self.tabelle.setCellWidget(r, 0, art)
        werte = [z.get("anzahl")] + [z.get(k_) for k_, _ in sw.MASSE.get(art.currentText(), ())]
        werte += [None] * (4 - len(werte)) + [z.get("x")]
        for c, v in enumerate(werte, start=1):
            self.tabelle.setItem(r, c, QTableWidgetItem(rechnen.zahl(v, 3) if isinstance(v, (int, float)) else
                                                        v if isinstance(v, str) else ""))
        self.tabelle.setItem(r, TEXT_SPALTE, QTableWidgetItem(z.get("text") or ""))
        self._kopf_hinweise(r)
        self.tabelle.blockSignals(False)
        if rechnen_:
            self.rechnen()

    def _art_geaendert(self, combo):
        for r in range(self.tabelle.rowCount()):
            if self.tabelle.cellWidget(r, 0) is combo:
                self._kopf_hinweise(r)
        self.rechnen()

    def _kopf_hinweise(self, r):
        """Tooltip je Maßzelle: welches Maß die Art an dieser Stelle braucht."""
        masse = sw.MASSE.get(self.tabelle.cellWidget(r, 0).currentText(), ())
        for i in range(3):
            it = self.tabelle.item(r, 2 + i)
            if it is not None:
                it.setToolTip(masse[i][1] if i < len(masse) else "nicht benötigt")
                it.setFlags(it.flags() | Qt.ItemIsEditable if i < len(masse) else it.flags() & ~Qt.ItemIsEditable)
                if i >= len(masse):
                    it.setText("")

    def _entfernen(self):
        for r in sorted({i.row() for i in self.tabelle.selectedIndexes()}, reverse=True):
            self.tabelle.removeRow(r)
        self.rechnen()

    def eingaben(self):
        konturen = []
        for r in range(self.tabelle.rowCount()):
            art = self.tabelle.cellWidget(r, 0).currentText()
            z = dict(art=art, anzahl=_zahl(self.tabelle.item(r, 1).text()))
            for i, (k_, _) in enumerate(sw.MASSE.get(art, ())):
                text = self.tabelle.item(r, 2 + i).text()
                z[k_] = text.strip() if k_ == "punkte" else _zahl(text)
            x = _zahl(self.tabelle.item(r, LAGE_SPALTE).text())
            if x is not None:
                z["x"] = x
            t = self.tabelle.item(r, TEXT_SPALTE).text().strip()
            if t:
                z["text"] = t
            konturen.append(z)
        enden = {s: dict(winkel=self.winkel[s].value(), achse=self.achse[s].currentText(),
                         sattel=self.sattel[s].value() or None) for s in ("a", "b")}
        return dict(enden, gravur=self.gravur.value() or None, konturen=konturen)

    # ------------------------------------------------------------------ Ergebnis
    def rechnen(self, *_):
        eingaben = self.eingaben()
        erg = sw.rechnen(eingaben, self.profil, self.grenzen, self.gewinde)
        self.ergebnis = erg
        t = self.ergebnis_tabelle
        t.setRowCount(len(erg["schritte"]))
        for r, s in enumerate(erg["schritte"]):
            werte = (s["text"] + (" (Schätzung)" if s["schaetzung"] else ""), str(s["anzahl"]),
                     rechnen.zahl(s["laenge_stueck"], 1), rechnen.zahl(s["laenge"], 1), str(s["einstiche"]),
                     "–" if s["huelle"] is None else rechnen.zahl(s["huelle"], 1), s["klasse"])
            for c, v in enumerate(werte):
                it = QTableWidgetItem(v)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
        f = erg["felder"]
        zeit = self.schneidzeit()
        teile = [f"<b>Schneidweg {rechnen.zahl(f['schneidweg'], 1)} mm</b>, {f['einstiche']} Einstiche "
                 f"(Enden {rechnen.zahl(f['a_schnitt'], 1)} + {rechnen.zahl(f['b_schnitt'], 1)} mm, Innenkonturen "
                 f"{rechnen.zahl(f['innen'], 1)} mm: klein {f['klein_n']}, mittel {f['mittel_n']}, groß {f['gross_n']})",
                 f"Schneidzeit je Teil {rechnen.zahl(zeit, 1)} s (Schneiddaten der Maschine)" if zeit is not None
                 else "<span style='color:#7A5A00'>Keine Schneiddaten für Maschine, Werkstoff und Wandstärke: "
                      "Schneidzeit von Hand eintragen.</span>"]
        if f.get("gewinde_vorschlag"):
            teile.append(f"<span style='color:#7A5A00'>Vorschlag: Bohrungen {f['bohrungen']} passen zu Kernlöchern "
                         f"für <b>{f['gewinde_vorschlag']}</b>. Erst nach Prüfung in <i>Gewinde geprüft</i> "
                         "eintragen (Zusatzarbeiten …).</span>")
        if erg["schaetzung"]:
            teile.append("<span style='color:#7A5A00'>Gehrung an diesem Profil: Schnittlänge geschätzt (gerade "
                         "Schnittlänge / cos Winkel).</span>")
        if not sw._z(self.p.get("zeit_manuell")) == 0:
            teile.append("<span style='color:#7A5A00'>Die Position hat eine Schneidzeit von Hand; sie gilt weiter, "
                         "bis sie in der Positionsliste gelöscht wird.</span>")
        if erg["fehler"]:
            teile.append("<span style='color:#B42318'>" + "<br>".join(erg["fehler"]) + "</span>")
        self.summe.setText("<br>".join(teile))
        if hasattr(self, "skizze"):
            self.skizze.zeigen(eingaben, erg)
        if hasattr(self, "ok_knopf"):
            self.ok_knopf.setEnabled(not erg["fehler"])

    def schneidzeit(self):
        """Schneidzeit je Teil [s] mit den neuen Werten oder None ohne Schneiddaten."""
        p = dict(self.p, **self.ergebnis["felder"])
        return rechnen.schneidzeit(p, self.kopf, rechnen.wand_schneiden(self.profil), self.tabellen, self.k)[2]

    def _ok(self):
        self.rechnen()
        if not self.ergebnis["fehler"]:
            self.accept()


def gewinde_liste(tabellen):
    """[(Gewinde, Kernloch-Ø)] aus den Stammdaten Gewinde (leer: übliche Kernlöcher, wie der STEP-Import)."""
    return [(g["gewinde"], g["kernloch"]) for g in (tabellen.get("gewinde") or ())
            if g.get("gewinde") and isinstance(g.get("kernloch"), (int, float))] or None


class Skizze(QWidget):
    """Seitenansicht des Teils (nicht maßstäblich in der Höhe): Enden mit Gehrung bzw. Ausklinkung, Innenkonturen an
    ihrer Lage (ohne Lage gleichmäßig verteilt), Hüllmaß als Größe. Nur zur Kontrolle der Eingaben."""

    def __init__(self, profil, laenge):
        super().__init__()
        self.profil, self.laenge = profil, laenge if isinstance(laenge, (int, float)) and laenge > 0 else None
        self.eingaben, self.ergebnis = {}, None
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def zeigen(self, eingaben, ergebnis):
        self.eingaben, self.ergebnis = eingaben, ergebnis
        self.update()

    def formen(self):
        """[(x Mitte ab Anfang, Hüllmaß, Art, Text)] je Kontur (Anzahl einzeln), x aus der Eingabe oder verteilt."""
        L = self.laenge or 1000.0
        liste = []
        for e in self.eingaben.get("konturen") or ():
            try:
                _, hk, n = sw.kontur(e)
            except ValueError:
                continue
            liste += [(e.get("x"), hk, e.get("art"))] * n
        frei = [i for i, (x, _, _) in enumerate(liste) if x is None]
        out = []
        for i, (x, hk, art) in enumerate(liste):
            if x is None:
                x = L * (frei.index(i) + 1) / (len(frei) + 1)
            out.append((x, hk, art))
        return out

    def paintEvent(self, _):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        g.fillRect(self.rect(), QColor("#FFFFFF"))
        L = self.laenge or 1000.0
        hoehe = sw._z(self.profil.get("a")) or 40.0
        rand = 30
        breite = max(50, self.width() - 2 * rand)
        m = breite / L                                    # mm -> Pixel in der Länge
        hp = min(self.height() - 50, max(30, hoehe * m))  # Höhe: mindestens lesbar
        y0 = (self.height() - hp) / 2
        stift = QPen(QColor("#1F3864"), 1.5)
        g.setPen(stift)

        def ende_x(seite):
            e = self.eingaben.get(seite) or {}
            w = abs(sw._z(e.get("winkel")))
            return min(hp * math.tan(math.radians(w)), breite / 3) if w < 80 else 0, sw._z(e.get("sattel"))
        da, sa = ende_x("a")
        db, sb = ende_x("b")
        links, rechts = rand, rand + breite
        umriss = QPolygonF([QPointF(links + da, y0), QPointF(rechts - db, y0), QPointF(rechts, y0 + hp),
                            QPointF(links, y0 + hp)])
        g.drawPolygon(umriss)
        for x, s_ in ((links, sa), (rechts, sb)):
            if s_:      # Ausklinkung als Bogen des Gegenrohrs
                r = max(s_ / 2 * m, hp / 2)
                mitte = x - r if x == links else x + r
                g.drawEllipse(QRectF(mitte - r, y0 + hp / 2 - r, 2 * r, 2 * r))
        g.setPen(QPen(QColor("#B42318"), 1.2))
        for x, hk, art in self.formen():
            d = max(6.0, min(hp * 0.8, (hk if hk and hk < sw.OHNE_HUELLE else hoehe * 0.6) * m))
            box = QRectF(rand + x * m - d / 2, y0 + hp / 2 - d / 2, d, d)
            if art == sw.BOHRUNG:
                g.drawEllipse(box)
            elif art == sw.LANGLOCH:
                g.drawRoundedRect(QRectF(box.x(), box.y() + d / 4, d, d / 2), d / 4, d / 4)
            else:
                g.drawRect(box)
        g.setPen(QColor("#595959"))
        txt = f"Länge {rechnen.zahl(L, 1)} mm" if self.laenge else "Teilelänge fehlt: Skizze mit 1000 mm"
        g.drawText(QRectF(rand, y0 + hp + 4, breite, 18), Qt.AlignHCenter, txt)
        g.drawText(QRectF(rand, 4, breite, 18), Qt.AlignLeft, "Skizze (nicht maßstäblich in der Höhe)")
        g.end()
