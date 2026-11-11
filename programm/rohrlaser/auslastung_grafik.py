"""Grafik der Maschinenauslastung: Wochenbalken und lesende Plantafel (QPainter). Hängt nur an einlastung.py, wochen.py
und stil.py, damit die Seite Auslastung der Kalkulation (auslastung_ansicht.py) und das eigene Programm „Rohrlaser
Auslastung“ dieselbe Darstellung nutzen."""
import datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import einlastung, stil
from . import wochen as auslastung

BALKEN = {"gruen": "#4C9A5B", "gelb": "#D9A400", "rot": "#C8372D", "ist": "#7F8A99", "angebot": "#5B8DB8",
          "auftrag": "#4E79A7"}
RISIKO_TEXT = {einlastung.OK: "ok", einlastung.KNAPP: "knapp", einlastung.UEBER: "überschritten",
               einlastung.OHNE: "ohne Termin"}


def _h(x):
    return f"{x:.1f}".replace(".", ",")


def _datum(d):
    if isinstance(d, datetime.date):
        return d.strftime("%d.%m.%Y")
    try:
        return datetime.date.fromisoformat(str(d)).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return ""


def stufe(quote):
    """'gruen', 'gelb' oder 'rot' zur Auslastung (0 … 1 …)."""
    if quote is None:
        return "rot"
    return "rot" if quote > auslastung.ROT else "gelb" if quote >= auslastung.GELB else "gruen"


def spalten_daten(aus, ein, gem, sicht_ein):
    """Zeilen für WochenBalken: [dict(maschine, spalten=[dict(key, titel, unter, kap, auftrag, angebot, ist, art)])].
    art: 'ist' (gemessen, vergangene Woche), 'woche', 'rest' (überfällig, später, ohne Termin: ohne Kapazität)."""
    zeilen = []
    for m in (ein["maschinen"] if sicht_ein else aus["maschinen"]):
        spalten = []
        for mo in (gem or {}).get("montage", ()):
            spalten.append(dict(key=("ist", mo), titel=f"KW {mo.isocalendar()[1]}", unter=mo.strftime("%d.%m."),
                                kap=gem["kapazitaet"].get((m, mo), 0.0), auftrag=0.0, angebot=0.0,
                                ist=gem["stunden"].get((m, mo), 0.0), art="ist"))
        for s, titel, mo in aus["spalten"]:
            if mo is not None:
                if sicht_ein:
                    a, b, kap = einlastung.wochenwerte(aus, ein, m, mo)
                else:
                    (a, b), kap = einlastung.terminwerte(aus, m, s), aus["kapazitaet"].get((m, mo), 0.0)
                spalten.append(dict(key=s, titel=titel, unter=mo.strftime("%d.%m."), kap=kap, auftrag=a, angebot=b,
                                    ist=0.0, art="woche"))
            elif sicht_ein:
                if s == auslastung.SPAETER:        # alles, was nach dem gezeigten Zeitraum eingelastet ist
                    letzter = max(x for _, _, x in aus["spalten"] if x is not None)
                    a = sum(w.get(einlastung.AUFTRAG, 0.0) for (mm, mo2), w in ein["woche"].items()
                            if mm == m and mo2 > letzter)
                    b = sum(w.get(einlastung.ANGEBOT, 0.0) for (mm, mo2), w in ein["woche"].items()
                            if mm == m and mo2 > letzter) + ein["spaeter"].get(m, 0.0)
                    spalten.append(dict(key=s, titel=titel, unter="", kap=None, auftrag=a, angebot=b, ist=0.0,
                                        art="rest"))
            else:
                a, b = einlastung.terminwerte(aus, m, s)
                spalten.append(dict(key=s, titel=titel, unter="", kap=None, auftrag=a, angebot=b, ist=0.0, art="rest"))
        zeilen.append(dict(maschine=m, spalten=spalten))
    return zeilen


class WochenBalken(QWidget):
    """Gestapelte Wochenbalken je Maschine. Klick wählt (Maschine, Spaltenschlüssel)."""
    gewaehlt = Signal(object, object)
    LINKS, ZEILE, OBEN, UNTEN = 64, 122, 32, 34

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zeilen, self.auswahl = [], None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, zeilen, auswahl=None):
        self.zeilen, self.auswahl = zeilen, auswahl
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        return QSize(640, max(1, len(self.zeilen)) * self.ZEILE + 4)

    def minimumSizeHint(self):
        n = max((len(z["spalten"]) for z in self.zeilen), default=1)
        return QSize(self.LINKS + n * 40, self.sizeHint().height())

    def _breite(self, zeile):
        return (self.width() - self.LINKS - 4) / max(1, len(zeile["spalten"]))

    def _treffer(self, pos):
        r = int(pos.y() // self.ZEILE)
        if not 0 <= r < len(self.zeilen) or pos.x() < self.LINKS:
            return None
        z = self.zeilen[r]
        c = int((pos.x() - self.LINKS) // self._breite(z))
        return (z, z["spalten"][c]) if 0 <= c < len(z["spalten"]) else None

    def mousePressEvent(self, e):
        t = self._treffer(e.position())
        if t:
            self.auswahl = (t[0]["maschine"], t[1]["key"])
            self.update()
            self.gewaehlt.emit(*self.auswahl)

    def mouseMoveEvent(self, e):
        t = self._treffer(e.position())
        QToolTip.showText(e.globalPosition().toPoint(), self.tipp(*t) if t else "", self)

    @staticmethod
    def tipp(z, s):
        m = z["maschine"]
        if s["art"] == "ist":
            q = f" = {s['ist'] / s['kap'] * 100:.0f} %" if s["kap"] else ""
            return f"{m}, {s['titel']} (gemessen): {_h(s['ist'])} h von {_h(s['kap'])} h{q}"
        teile = [f"{m}, {s['titel']}: Aufträge {_h(s['auftrag'])} h"]
        if s["angebot"]:
            teile.append(f"Angebote gewichtet {_h(s['angebot'])} h")
        if s["kap"] is not None:
            frei = s["kap"] - s["auftrag"] - s["angebot"]
            teile.append(f"Kapazität {_h(s['kap'])} h")
            teile.append(f"frei {_h(frei)} h" if frei >= 0 else f"überlastet um {_h(-frei)} h")
        return ", ".join(teile)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetrics(self.font())
        klein = self.font()
        klein.setPointSizeF(max(6.5, klein.pointSizeF() * 0.85))
        text, grau, linie = stil.farbe(stil.TEXT), stil.farbe(stil.TEXT_GRAU), stil.farbe(stil.RAHMEN)
        for r, z in enumerate(self.zeilen):
            y0 = r * self.ZEILE
            p.setFont(self.font())
            p.setPen(text)
            f = self.font()
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(4, y0 + self.OBEN, self.LINKS - 8, 20), Qt.AlignLeft | Qt.AlignVCenter, z["maschine"])
            p.setFont(klein)
            if r:
                p.setPen(QPen(stil.farbe(stil.LINIE), 1))
                p.drawLine(QPointF(0, y0), QPointF(self.width(), y0))
            b = self._breite(z)
            hoehe = self.ZEILE - self.OBEN - self.UNTEN
            basis = y0 + self.OBEN + hoehe
            werte = [max(s["kap"] or 0.0, s["auftrag"] + s["angebot"], s["ist"]) for s in z["spalten"]]
            ymax = max(werte + [0.1]) * 1.05
            ist_ende = None
            for c, s in enumerate(z["spalten"]):
                x = self.LINKS + c * b
                bx, bb = x + b * 0.16, b * 0.68
                if s["art"] == "ist":
                    ist_ende = x + b
                if self.auswahl == (z["maschine"], s["key"]):
                    p.setPen(Qt.NoPen)
                    p.setBrush(stil.farbe(stil.BLAU_FLAECHE))
                    p.drawRoundedRect(QRectF(x + 1, y0 + 2, b - 2, self.ZEILE - 4), 4, 4)
                gesamt = s["ist"] if s["art"] == "ist" else s["auftrag"] + s["angebot"]
                quote = gesamt / s["kap"] if s["kap"] else None
                if s["kap"] is not None:             # Kapazität als Rahmen
                    kh = hoehe * s["kap"] / ymax
                    p.setPen(QPen(linie, 1))
                    p.setBrush(stil.farbe(stil.FLAECHE))
                    p.drawRect(QRectF(bx, basis - kh, bb, kh))
                p.setPen(Qt.NoPen)
                if s["art"] == "ist":
                    p.setBrush(QColor(BALKEN["ist"]))
                    p.drawRect(QRectF(bx, basis - hoehe * s["ist"] / ymax, bb, hoehe * s["ist"] / ymax))
                else:
                    farbe = QColor(BALKEN[stufe(quote) if s["art"] == "woche" else "ist"])
                    if s["art"] == "rest" and s["key"] == auslastung.UEBERFAELLIG:
                        farbe = QColor(BALKEN["rot"])
                    ah = hoehe * s["auftrag"] / ymax
                    p.setBrush(farbe)
                    p.drawRect(QRectF(bx, basis - ah, bb, ah))
                    if s["angebot"] > 0:
                        gh = hoehe * s["angebot"] / ymax
                        p.setBrush(QBrush(QColor(BALKEN["angebot"]), Qt.BDiagPattern))
                        p.setPen(QPen(QColor(BALKEN["angebot"]), 1))
                        p.drawRect(QRectF(bx, basis - ah - gh, bb, gh))
                    if s["kap"] and gesamt > s["kap"]:       # Kapazitätslinie über dem überlasteten Balken
                        p.setPen(QPen(text, 1.5, Qt.DashLine))
                        ky = basis - hoehe * s["kap"] / ymax
                        p.drawLine(QPointF(bx - 3, ky), QPointF(bx + bb + 3, ky))
                # Beschriftung: Prozent bzw. Stunden über dem Balken, KW und Stunden darunter
                oben = basis - hoehe * max(gesamt, s["kap"] or 0.0) / ymax
                if quote is not None and gesamt > 0:
                    kopf = f"{quote * 100:.0f} %"
                elif gesamt > 0:
                    kopf = f"{_h(gesamt)} h"
                else:
                    kopf = ""
                p.setPen(QColor(BALKEN["rot"]) if (quote or 0) > 1 or (s["key"] == auslastung.UEBERFAELLIG and gesamt)
                         else text)
                f = QFontMetrics(klein)
                p.drawText(QRectF(x, oben - 15, b, 14), Qt.AlignCenter, kopf)
                p.setPen(text)
                p.drawText(QRectF(x, basis + 2, b, 14), Qt.AlignCenter, f.elidedText(s["titel"], Qt.ElideRight, int(b)))
                p.setPen(grau)
                unten = (f"{_h(gesamt)}/{_h(s['kap'])} h" if s["kap"] is not None and b >= 62 else s["unter"])
                p.drawText(QRectF(x, basis + 16, b, 14), Qt.AlignCenter, f.elidedText(unten, Qt.ElideRight, int(b)))
            p.setPen(QPen(linie, 1))
            p.drawLine(QPointF(self.LINKS, basis), QPointF(self.width() - 4, basis))
            if ist_ende is not None:                 # Trennlinie Vergangenheit | ab heute
                p.setPen(QPen(grau, 1, Qt.DotLine))
                p.drawLine(QPointF(ist_ende, y0 + 6), QPointF(ist_ende, basis + self.UNTEN - 4))
                p.drawText(QRectF(self.LINKS, y0 + 2, ist_ende - self.LINKS - 4, 14), Qt.AlignRight, "gemessen")
        del fm
        p.end()


class Plantafel(QWidget):
    """Lesende Plantafel: je Maschine eine Zeile, Aufträge als Balken auf der Zeitachse (Tage ab dem Montag dieser
    Woche). Klick wählt, Doppelklick öffnet."""
    gewaehlt = Signal(object)
    oeffnen = Signal(object)
    LINKS, KOPF, ZEILE = 64, 36, 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self.aus = self.ein = None
        self.tage, self.auswahl, self.tagbreite_fest = [], None, None
        self.flaechen = []                        # [(QRectF, Auftrag)]
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, aus, ein, wochen, auswahl=None):
        self.aus, self.ein, self.auswahl = aus, ein, auswahl
        m0 = auslastung.montag(ein["heute"])
        self.tage = [m0 + datetime.timedelta(days=i) for i in range(int(wochen) * 7)]
        self._groesse()
        self.update()

    def zoom(self, tagbreite):
        """Feste Tagesbreite in Pixeln (waagerecht rollen) oder None = alles passend."""
        self.tagbreite_fest = tagbreite
        self._groesse()
        self.update()

    def _groesse(self):
        self.setMinimumWidth(self.LINKS + int(len(self.tage) * self.tagbreite_fest) + 4 if self.tagbreite_fest else 0)
        self.updateGeometry()

    def sizeHint(self):
        n = len(self.ein["maschinen"]) if self.ein else 1
        return QSize(640, self.KOPF + n * self.ZEILE + 4)

    def minimumSizeHint(self):
        return QSize(self.minimumWidth() or 300, self.sizeHint().height())

    def _tb(self):
        return self.tagbreite_fest or (self.width() - self.LINKS - 4) / max(1, len(self.tage))

    def _x(self, tag, anteil=0.0):
        return self.LINKS + ((tag - self.tage[0]).days + anteil) * self._tb()

    def laeufe(self, a, m):
        """Zusammenhängende Stücke eines Auftrags als [(x0, x1)] (ein Lauf je Folge aufeinanderfolgender Tage)."""
        out, letzter = [], None
        for tag, von, bis in a["stuecke"]:
            if tag < self.tage[0] or tag > self.tage[-1]:
                continue
            kap = self.ein["kapazitaet"].get((m, tag)) or 1.0
            x0, x1 = self._x(tag, von / kap), self._x(tag, min(1.0, bis / kap))
            if letzter is not None and (tag - letzter).days <= 1 and out:
                out[-1] = (out[-1][0], x1)
            else:
                out.append((x0, x1))
            letzter = tag
        return out

    def _treffer(self, pos):
        for rect, a in self.flaechen:
            if rect.contains(pos):
                return a
        return None

    def mousePressEvent(self, e):
        a = self._treffer(e.position())
        self.auswahl = a["id"] if a else None
        self.update()
        self.gewaehlt.emit(self.auswahl)

    def mouseDoubleClickEvent(self, e):
        a = self._treffer(e.position())
        if a:
            self.oeffnen.emit(a["id"])

    def mouseMoveEvent(self, e):
        a = self._treffer(e.position())
        QToolTip.showText(e.globalPosition().toPoint(), self.tipp(a) if a else "", self)

    @staticmethod
    def tipp(a):
        teile = [f"{a.get('nummer') or ''} {a.get('kunde') or ''}".strip(),
                 f"{a['art']}, {a['maschine']}, {_h(a['h'])} h Laserzeit"]
        if a.get("start"):
            teile.append(f"Laser {_datum(a['start'])} bis {_datum(a['fertig'])}, lieferbar {_datum(a['lieferbar'])}")
        if a.get("termin_datum"):
            teile.append(f"Liefertermin {_datum(a['termin_datum'])}"
                         + (f", Puffer {a['puffer']} Arbeitstage" if a.get("puffer") is not None else ""))
        teile.append(f"Terminrisiko: {RISIKO_TEXT[a['risiko']]}")
        return "\n".join(teile)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self.flaechen = []
        if not self.ein or not self.tage:
            p.end()
            return
        tb = self._tb()
        text, grau = stil.farbe(stil.TEXT), stil.farbe(stil.TEXT_GRAU)
        linie, flaeche, hell = stil.farbe(stil.RAHMEN), stil.farbe("#EEF1F5"), stil.farbe("#FFFFFF")
        klein = self.font()
        klein.setPointSizeF(max(6.5, klein.pointSizeF() * 0.85))
        fm = QFontMetrics(klein)
        maschinen = self.ein["maschinen"]
        unten = self.KOPF + len(maschinen) * self.ZEILE
        heute = self.ein["heute"]
        # Kopf: Kalenderwochen, darunter Tage (wenn Platz)
        p.setFont(klein)
        for i, tag in enumerate(self.tage):
            x = self.LINKS + i * tb
            if tag.weekday() == 0:
                p.setPen(QPen(linie, 1))
                p.drawLine(QPointF(x, 4), QPointF(x, unten))
                p.setPen(text)
                p.drawText(QRectF(x + 3, 2, tb * 7 - 4, 15), Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(f"KW {tag.isocalendar()[1]}  {tag.strftime('%d.%m.')}", Qt.ElideRight,
                                         int(tb * 7 - 6)))
            if tb >= 15:
                p.setPen(grau)
                p.drawText(QRectF(x, 18, tb, 14), Qt.AlignCenter, f"{tag.day}")
        for r, m in enumerate(maschinen):
            y = self.KOPF + r * self.ZEILE
            f = self.font()
            f.setBold(True)
            p.setFont(f)
            p.setPen(text)
            p.drawText(QRectF(4, y, self.LINKS - 8, self.ZEILE), Qt.AlignLeft | Qt.AlignVCenter, m)
            p.setFont(klein)
            p.setPen(QPen(stil.farbe(stil.LINIE), 1))
            p.drawLine(QPointF(0, y), QPointF(self.width(), y))
            p.setPen(Qt.NoPen)
            for i, tag in enumerate(self.tage):       # Schichttage hell; ohne Schicht (Wochenende, Feiertag, Ruhe) und
                kap = self.ein["kapazitaet"].get((m, tag))      # Vergangenheit grau
                p.setBrush(flaeche if tag < heute or not kap else hell)
                p.drawRect(QRectF(self.LINKS + i * tb, y + 1, tb + 0.5, self.ZEILE - 1))
            for a in (x for x in self.ein["auftraege"] if x["maschine"] == m):
                angebot = a["art"] == einlastung.ANGEBOT
                farbe = QColor(BALKEN["angebot" if angebot else "auftrag"])
                rahmen = {einlastung.UEBER: QColor(BALKEN["rot"]), einlastung.KNAPP: QColor(stil.umsetzen(stil.ORANGE))
                          }.get(a["risiko"]) if not angebot else None
                gesamt = None
                for x0, x1 in self.laeufe(a, m):
                    rect = QRectF(x0, y + 8, max(2.0, x1 - x0), self.ZEILE - 20)
                    p.setPen(QPen(rahmen, 2) if rahmen else QPen(farbe.darker(130), 1))
                    if a["id"] == self.auswahl:
                        p.setPen(QPen(text, 2))
                    p.setBrush(QBrush(farbe, Qt.BDiagPattern) if angebot else farbe)
                    p.drawRoundedRect(rect, 3, 3)
                    self.flaechen.append((rect.adjusted(-1, -6, 1, 6), a))
                    gesamt = rect if gesamt is None or rect.width() > gesamt.width() else gesamt
                if gesamt is not None and gesamt.width() > 30:
                    marke = "! " if rahmen else ""
                    p.setPen(text if angebot else QColor("#FFFFFF"))          # fest: weiße Schrift auf dem blauen Auftragsblock, in beiden Designs
                    p.drawText(gesamt.adjusted(4, 0, -3, 0), Qt.AlignLeft | Qt.AlignVCenter,
                               fm.elidedText(f"{marke}{a.get('nummer') or ''} {a.get('kunde') or ''}".strip(),
                                             Qt.ElideRight, int(gesamt.width() - 7)))
                t = a.get("termin_datum")
                if t and self.tage[0] <= t <= self.tage[-1] and not angebot:      # Liefertermin: Dreieck am Zeilenfuß
                    x = self._x(t, 1.0)
                    p.setPen(Qt.NoPen)
                    p.setBrush(rahmen or grau)
                    yb = y + self.ZEILE - 1
                    p.drawPolygon(QPolygonF([QPointF(x - 5, yb), QPointF(x + 5, yb), QPointF(x, yb - 8)]))
                    if a["id"] == self.auswahl and a.get("fertig"):
                        p.setPen(QPen(rahmen or grau, 1, Qt.DashLine))
                        xf = self._x(a["fertig"], 1.0)
                        p.drawLine(QPointF(min(xf, x), yb - 4), QPointF(max(xf, x), yb - 4))
        p.setPen(QPen(stil.farbe(stil.LINIE), 1))
        p.drawLine(QPointF(0, unten), QPointF(self.width(), unten))
        if self.tage[0] <= heute <= self.tage[-1]:            # heute
            x = self._x(heute)
            p.setPen(QPen(QColor(BALKEN["rot"]), 1.5))
            p.drawLine(QPointF(x, 16), QPointF(x, unten))
        p.end()
