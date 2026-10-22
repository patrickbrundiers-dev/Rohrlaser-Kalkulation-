"""RP-Profile in den Stammdaten 'Profile': MegaCAD-Makros (.mac) laden und den Querschnitt eines RP-Profils zeigen.

Die Rechnung steckt in rp_profile.py; hier nur Dateiauswahl, Meldungen und die Zeichnung."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from . import rp_profile


def _z(x, stellen=1):
    return f"{x:.{stellen}f}".replace(".", ",")


def kennwerte_text(e):
    """Kennwerte eines RP-Profils als Text (mehrzeilig)."""
    kammern = e.get("kammern") or 0
    zeilen = [f"Breite × Höhe: {_z(e['breite'])} × {_z(e['hoehe'])} mm, Blechdicke {_z(e['wand'], 2)} mm",
              f"Fläche {_z(e['flaeche'])} mm² ({_z(e['flaeche'] * 7.85e-3, 2)} kg/m Stahl), "
              f"Außenumfang {_z(e['umfang'])} mm",
              f"Schnittlänge gerade {_z(e['schnitt'])} mm, davon durch die Doppellage {_z(e.get('schnitt_doppel', 0))} mm",
              f"Ecken {e.get('ecken', 0)}, " + ("offenes Profil" if not kammern else
                                                 f"{kammern} Kammer{'n' * (kammern > 1)}")]
    if e.get("serie"):
        zeilen.append(f"Bibliothek RP-ROHRE, {e['serie']}")
    return "\n".join(zeilen)


class QuerschnittBild(QWidget):
    """Kontur eines RP-Profils (Linien und Bögen des Makros) maßstäblich, Nullpunkt unten links."""

    def __init__(self, eintrag, parent=None):
        super().__init__(parent)
        self.e = eintrag
        self.setMinimumSize(360, 300)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        b, h = max(self.e["breite"], 1), max(self.e["hoehe"], 1)
        rand = 16
        m = min((self.width() - 2 * rand) / b, (self.height() - 2 * rand) / h)
        ox, oy = (self.width() - b * m) / 2, (self.height() + h * m) / 2

        def punkt(x, y):
            return QPointF(ox + x * m, oy - y * m)

        pfad = QPainterPath()
        for el in self.e.get("elemente", ()):
            if el[0] == rp_profile.LINIE:
                pfad.moveTo(punkt(el[1], el[2]))
                pfad.lineTo(punkt(el[3], el[4]))
            elif el[0] == rp_profile.BOGEN:
                pts = rp_profile.bogen_punkte(el, sehne=0.05)
                pfad.moveTo(punkt(*pts[0]))
                for q in pts[1:]:
                    pfad.lineTo(punkt(*q))
        p.setPen(QPen(QColor("#1f4e79"), 1.6))
        p.drawPath(pfad)
        p.setPen(QPen(QColor("#999999"), 1, Qt.DashLine))
        p.drawRect(QRectF(punkt(0, h), punkt(b, 0)))
        p.end()


def querschnitt_zeigen(parent, profil_id, stumm=False):
    """Dialog mit Querschnitt und Kennwerten eines RP-Profils (Bibliothek oder selbst geladen). Ergebnis: der Dialog
    (stumm: nicht anzeigen) oder None, wenn die Profil-ID keine bekannte RP-Kontur hat."""
    e = rp_profile.daten(profil_id)
    if not e:
        if not stumm:
            QMessageBox.information(parent, "RP-Querschnitt",
                                    f"Zu '{profil_id}' gibt es keine RP-Kontur. Bitte ein RP-Profil wählen (Profil-ID "
                                    "'RP …') oder das MegaCAD-Makro mit 'RP-Profile aus MegaCAD laden …' einlesen.")
        return None
    d = QDialog(parent)
    d.setWindowTitle(f"Querschnitt {profil_id}")
    lay = QVBoxLayout(d)
    lay.addWidget(QuerschnittBild(e), 1)
    text = QLabel(kennwerte_text(e))
    text.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lay.addWidget(text)
    knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
    knoepfe.rejected.connect(d.reject)
    lay.addWidget(knoepfe)
    d.resize(520, 480)
    if not stumm:
        d.exec()
    return d


def makros_laden(parent, db, pfade=None):
    """MegaCAD-Makros wählen (pfade = None: Dateidialog), auswerten und als RP-Profile speichern (Datenbank.rp_laden).
    Ergebnis: (neu, geändert, Meldungen) oder None (abgebrochen bzw. nichts lesbar)."""
    if pfade is None:
        pfade, _ = QFileDialog.getOpenFileNames(parent, "RP-Profile aus MegaCAD laden", "",
                                                "MegaCAD-Makros (*.mac *.MAC);;Alle Dateien (*)")
    if not pfade:
        return None
    eintraege, meldungen = rp_profile.laden(pfade)
    if not eintraege:
        return None if not meldungen else (0, 0, meldungen)
    neu, geaendert = db.rp_laden(eintraege)
    return neu, geaendert, meldungen
