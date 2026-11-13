"""Arbeitsgänge je Position als Kürzel und Detailbereich unter der Positionsliste (UI-Modernisierung U4, Patrick
12./13.11.2026, Konzeptbild „Oberfläche Rohrlaser-Kalkulation“).

Spalte „Arbeitsgänge“: je Arbeitsgang ein kleines Kürzel (P Programmieren, L Laser, G Gewinde, E Entgraten …), blau
wenn gerechnet, gelb wenn nur vorgeschlagen oder zu prüfen; der Tooltip nennt alle Namen. Detailbereich: für die
gewählte Position die Arbeitsgänge ausgeschrieben, Material und Preis je Teil. Alles nur Anzeige aus den Werten,
die das Programm ohnehin rechnet (arbeitsgaenge.position, rechnen.kalkulation); die Rechnung ändert sich nicht.
"""
from html import escape

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QStyle, QStyledItemDelegate, QVBoxLayout

from . import arbeitsgaenge as ag
from . import stil

GERECHNET, VORSCHLAG, PRUEFEN = "gerechnet", "vorschlag", "pruefen"

# (Wortanfang klein, Kürzel); sonst der erste Buchstabe des Namens
KUERZEL = (("programm", "P"), ("laser", "L"), ("gewinde", "G"), ("entgrat", "E"), ("säg", "S"), ("saeg", "S"),
           ("bieg", "B"), ("kant", "K"), ("schweiß", "W"), ("schweiss", "W"), ("zukauf", "Z"), ("strahl", "St"),
           ("pulver", "Pb"), ("verzink", "V"), ("lack", "La"), ("senk", "Se"), ("flowdrill", "F"), ("bohr", "Bo"),
           ("richt", "R"), ("wasch", "Wa"), ("verpack", "Vp"))

# Farben (Text, Fläche) je Art; Dunkelmodus über stil.farbe
FARBEN = {GERECHNET: ("#1F4E78", "#DDEBF7"), VORSCHLAG: ("#7A5A00", "#FFF4CE"), PRUEFEN: ("#7A5A00", "#FFF4CE")}


def kuerzel(name):
    n = (name or "").strip().lower()
    for anfang, k in KUERZEL:
        if n.startswith(anfang) or f" {anfang}" in n:
            return k
    return (name or "?").strip()[:1].upper() or "?"


def _zeit(sekunden):
    if not sekunden:
        return ""
    return f"{sekunden:.1f} s".replace(".", ",") if sekunden < 60 else f"{sekunden / 60:.0f} min"


def eintraege(zeilen, prog_min=None, laser_s=None):
    """Arbeitsgänge einer Position für Spalte und Detailbereich: [dict(kuerzel, name, text, art)].

    zeilen: arbeitsgaenge.position(...) dieser Position; prog_min: Programmierzeit [min] (vorn als P, wenn > 0);
    laser_s: Schneidzeit je Teil [s] (am Laser-Eintrag). Abgelehnte Vorschläge fehlen, mehrere Gewinde werden ein
    Kürzel G mit allen Größen."""
    out = []
    if prog_min:
        out.append(dict(kuerzel="P", name="Programmieren", text=f"Programmieren {prog_min:.0f} min", art=GERECHNET))
    gewinde = []
    for z in zeilen or ():
        status = z.get("status")
        if status == ag.ABGELEHNT:
            continue
        art = GERECHNET if status in (ag.IM_ANGEBOT, ag.AUTOMATISCH) else PRUEFEN if status == ag.ZU_PRUEFEN \
            else VORSCHLAG
        name = z.get("name") or z.get("arbeitsgang") or ""
        if name.startswith("Gewinde "):
            gewinde.append((name[len("Gewinde "):], art, z.get("menge")))
            continue
        text = z.get("arbeitsgang") or name
        if name == "Laser schneiden" and laser_s:
            text = f"Laser {_zeit(laser_s)}"
        if art == VORSCHLAG:
            text += " · Vorschlag"
        elif art == PRUEFEN:
            text += " · prüfen"
        out.append(dict(kuerzel=kuerzel(name), name=name, text=text, art=art))
    if gewinde:
        art = GERECHNET if all(a == GERECHNET for _, a, _ in gewinde) else PRUEFEN
        teile = ", ".join((f"{m:.0f}× " if m and m > 1 else "") + g for g, _, m in gewinde)
        out.append(dict(kuerzel="G", name="Gewinde", text=f"Gewinde {teile}" + (" · prüfen" if art == PRUEFEN else ""),
                        art=art))
    return out


def tooltip(liste):
    if not liste:
        return "Keine Arbeitsgänge"
    zeichen = {GERECHNET: "✓", VORSCHLAG: "?", PRUEFEN: "!"}
    return "\n".join(f"{zeichen[e['art']]} {e['kuerzel']}: {e['text']}" for e in liste) + \
        "\n✓ wird gerechnet · ? Vorschlag, noch nicht gerechnet · ! zu prüfen"


class ArbeitsgangDelegate(QStyledItemDelegate):
    """Zeichnet die Kürzel der Spalte „Arbeitsgänge“ als kleine Kästchen (Daten: UserRole = eintraege(...))."""

    ABSTAND, RAND = 3, 4

    def _font(self, option):
        f = QFont(option.font)
        f.setPointSizeF(max(6.5, f.pointSizeF() * 0.8))
        f.setBold(True)
        return f

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        option.text = ""
        option.widget.style().drawControl(QStyle.CE_ItemViewItem, option, painter, option.widget) \
            if option.widget else super().paint(painter, option, index)
        liste = index.data(Qt.ItemDataRole.UserRole) or ()
        if not liste:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        f = self._font(option)
        painter.setFont(f)
        fm = QFontMetrics(f)
        h = fm.height() + 2
        x = option.rect.x() + self.RAND
        # Zeilen mit Kopfband (Satz, Baugruppe) sind höher, das Band steht oben: Kürzel in die normale Zeile unten
        zeile = option.rect.height()
        kopf = getattr(option.widget, "verticalHeader", None)
        if kopf is not None:
            zeile = min(zeile, kopf().defaultSectionSize())
        y = option.rect.bottom() - zeile + 1 + (zeile - h) // 2
        for e in liste:
            w = max(h, fm.horizontalAdvance(e["kuerzel"]) + 8)
            if x + w > option.rect.right() - 2:
                painter.setPen(QColor(stil.farbe("#5F6B7A")))
                painter.drawText(QRect(x, y, 14, h), Qt.AlignCenter, "…")
                break
            text, flaeche = FARBEN[e["art"]]
            r = QRect(x, y, w, h)
            painter.setPen(QPen(QColor(stil.farbe(text)), 1) if e["art"] != GERECHNET else Qt.NoPen)
            painter.setBrush(QColor(stil.farbe(flaeche)))
            painter.drawRoundedRect(r, 3, 3)
            painter.setPen(QColor(stil.farbe(text)))
            painter.drawText(r, Qt.AlignCenter, e["kuerzel"])
            x += w + self.ABSTAND
        painter.restore()

    def sizeHint(self, option, index):
        liste = index.data(Qt.ItemDataRole.UserRole) or ()
        fm = QFontMetrics(self._font(option))
        h = fm.height() + 2
        breite = sum(max(h, fm.horizontalAdvance(e["kuerzel"]) + 8) + self.ABSTAND for e in liste)
        return QSize(max(60, breite + 2 * self.RAND), h + 6)


def _z(w, stellen=2):
    if w is None:
        return "–"
    return f"{w:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


class PositionsDetail(QFrame):
    """Detailbereich unter der Positionsliste: Arbeitsgänge, Material und Preis je Teil der gewählten Position."""

    arbeitsgang_neu = Signal()      # „+ Arbeitsgang“: Zusatzarbeiten der Position wählen

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("karte")
        lay = QGridLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setHorizontalSpacing(24)
        lay.setVerticalSpacing(2)
        self.titel, self.ag, self.material, self.preis = QLabel(), QLabel(), QLabel(), QLabel()
        for w in (self.titel, self.ag, self.material, self.preis):
            w.setTextFormat(Qt.RichText)
            w.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.ag.setWordWrap(True)
        self.ag.linkActivated.connect(lambda _l: self.arbeitsgang_neu.emit())
        kopf = {}
        for i, t in enumerate(("Material", "Preis je Teil")):
            kopf[i] = QLabel(t.upper())
            kopf[i].setObjectName("kennzahltitel")
        lay.addWidget(self.titel, 0, 0)
        lay.addWidget(kopf[0], 0, 1)
        lay.addWidget(kopf[1], 0, 2)
        spalte = QVBoxLayout()
        spalte.addWidget(self.ag)
        spalte.addStretch(1)
        lay.addLayout(spalte, 1, 0)
        lay.addWidget(self.material, 1, 1)
        lay.addWidget(self.preis, 1, 2)
        lay.setColumnStretch(0, 3)
        lay.setColumnStretch(1, 2)
        lay.setColumnStretch(2, 2)
        self.titel.setObjectName("kennzahltitel")

    @staticmethod
    def _tabelle(zeilen):
        html = "<table width='100%' cellpadding='0' cellspacing='0'>"
        for t, w, fett in zeilen:
            a, b = ("<b>", "</b>") if fett else ("", "")
            html += f"<tr><td>{a}{escape(t)}{b}</td><td align='right'>&nbsp;&nbsp;{a}{escape(w)}{b}</td></tr>"
        return html + "</table>"

    def setzen(self, p, liste, werte=None, kalk=None, meterpreis=None):
        """p: Position; liste: eintraege(...); werte: rechnen.position_werte; kalk: Zeile der Kalkulation (je Teil)."""
        werte, kalk = werte or {}, kalk or {}
        self.titel.setText(escape(f"Pos. {p.get('pos') or ''} · {p.get('artikel') or ''} "
                                  f"{p.get('bezeichnung') or ''}".strip().upper()) + " · ARBEITSGÄNGE")
        zeichen = {GERECHNET: "✓", VORSCHLAG: "?", PRUEFEN: "!"}
        chips = []
        for e in liste:
            text, flaeche = (stil.umsetzen(c) for c in FARBEN[e["art"]])
            chips.append(f"<span style='color:{text};background-color:{flaeche}'>&nbsp;{zeichen[e['art']]} "
                         f"{escape(e['text'])}&nbsp;</span>")
        chips.append(f"<a href='neu' style='color:{stil.umsetzen('#1F4E78')}'>+ Arbeitsgang</a>")
        self.ag.setText(" &nbsp;".join(chips))
        mat = [(" · ".join(x for x in (p.get("profil_id"), p.get("werkstoff_id")) if x) or "–", "", False)]
        if meterpreis:
            mat.append(("Meterpreis", f"{_z(meterpreis)} €/m", False))
        if p.get("laenge"):
            mat.append(("Länge", f"{_z(p['laenge'], 1)} mm", False))
        if werte.get("gewicht"):
            mat.append(("Gewicht je Teil", f"{_z(werte['gewicht'], 2)} kg", False))
        self.material.setText(self._tabelle(mat))
        n = lambda *namen: sum(kalk.get(x) or 0 for x in namen)     # noqa: E731
        preis = [("Material", f"{_z(kalk.get('material_teil'))} €", False),
                 ("Laser + Rüsten", f"{_z(n('laser_schneiden_teil', 'ruesten_maschine_teil', 'ruesten_abm_teil', 'stangenwechsel_teil'))} €", False)]
        if n("gewinde_teil", "zusatz_teil", "arbeit_teil"):
            preis.append(("Gewinde + Zusatzarbeiten", f"{_z(n('gewinde_teil', 'zusatz_teil', 'arbeit_teil'))} €", False))
        preis.append(("Herstellkosten", f"{_z(kalk.get('herstell_teil'))} €", False))
        preis.append(("Verkauf", f"{_z(kalk.get('preis_teil'))} €", True))
        self.preis.setText(self._tabelle(preis))
