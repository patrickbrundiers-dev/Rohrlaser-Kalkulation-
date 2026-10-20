"""Prüft die Konturklassen klein/mittel/groß in der Schneidzeit: Schnittweg je Klasse mit dem Vorschub der Klasse,
Anteil groß nie negativ, Warnung bei widersprüchlichen Konturwerten, Zeitanteile in der Kalkulation und im
Kalkulation-PDF.

Aufruf: python tests/test_konturklassen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import pdf, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


# --- Rechenregel mit festen Vorschüben (groß 3000, mittel 2000, klein 1000, Gravur 6000, Einstich 0,5 s)
V = (3000, 2000, 1000, 6000, 0.5)
p = dict(schneidweg=697.1, klein_mm=125.7, mittel_mm=91.4, gross_mm=240.0, innen=457.1, gravur=0, einstiche=8)
a = rechnen.zeitanteile(p, V)
assert abs(a["gross"] - 60 * 480.0 / 3000) < EPS and abs(a["mittel"] - 60 * 91.4 / 2000) < EPS
assert abs(a["klein"] - 60 * 125.7 / 1000) < EPS and abs(a["einstiche"] - 4.0) < EPS
assert abs(sum(a.values()) - 23.884) < 1e-3
ok(f"Beispiel aus dem Prüfbericht: {sum(a.values()):.1f} s (groß {a['gross']:.1f}, mittel {a['mittel']:.1f}, "
   f"klein {a['klein']:.1f}, Einstiche {a['einstiche']:.1f})")
assert rechnen.konturen_pruefen(p) is None
ok("stimmige Konturwerte: keine Warnung")

# A: Schneidweg von Hand kleiner als klein + mittel -> Anteil groß 0 statt negativ, Warnung
q = dict(p, schneidweg=100)
assert rechnen.gross_rest(q) == 0 and rechnen.zeitanteile(q, V)["gross"] == 0
assert rechnen.konturen_pruefen(q) == "Konturen klein + mittel länger als Schneidweg"
ok("Schneidweg 100 mm < klein + mittel: Anteil groß 0 s, Warnung")
q = dict(p, innen=200)
assert rechnen.konturen_pruefen(q) == "Konturklassen länger als Innenkonturen"
ok("Konturklassen länger als Innenkonturen: Warnung")
assert rechnen.konturen_pruefen(dict(schneidweg=300, einstiche=2)) is None
assert rechnen.konturen_pruefen(dict(p, schneidweg=217.3)) is None      # Rundung bis 0,5 mm erlaubt
ok("ohne Konturklassen bzw. innerhalb der Rundung: keine Warnung")
assert rechnen.zeitanteile(p, (None, None, None, None, None)) is None
ok("ohne Schneiddaten keine Zeitanteile")

# --- im Programm: Status, Kalkulation, Spalten, PDF
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
an = db.angebot_neu(dict(kunde="Test", kundennr="4711"))
db.position_neu(an, dict(pos=10, artikel="K10", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800,
                         stueck=4, einstiche=8, **{n: p[n] for n in ("schneidweg", "klein_mm", "mittel_mm", "gross_mm",
                                                                    "innen")}))
db.position_neu(an, dict(pos=20, artikel="K20", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=900,
                         stueck=2, schneidweg=100, einstiche=8, klein_mm=125.7, mittel_mm=91.4))
s = fenster.angebot_oeffnen(an)
assert s.optimieren()
st = [rechnen.status(x, rechnen.position_werte(x, s.kopf, s.k, s.tabellen), s.kopf, s.k) for x in s.positionen]
assert st[0] == "OK" or not st[0].startswith("WARNUNG: Kontur"), st
assert st[1] == "WARNUNG: Konturen klein + mittel länger als Schneidweg", st
ok(f"Status: Pos. 10 {st[0]!r}, Pos. 20 {st[1]!r}")
zeilen, summen = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)
z1, z2 = zeilen
assert z2["hinweis"] == "Konturen klein + mittel länger als Schneidweg"
for z in zeilen:
    teile = [z[f"zeit_{n}"] for n in rechnen.ZEITANTEILE]
    assert all(t is not None and t >= 0 for t in teile)
    assert abs(sum(teile) - z["laser_brutto"]) < 1e-6
    assert abs(z["zeit_gross"] - 60 * z["mm_gross"] / z["vorschub_gross"]) < 1e-6
    assert abs(z["zeit_klein"] - 60 * z["mm_klein"] / z["vorschub_klein"]) < 1e-6
    assert abs(z["zeit_mittel"] - 60 * z["mm_mittel"] / z["vorschub_mittel"]) < 1e-6
assert z2["mm_gross"] == 0 and z2["zeit_gross"] == 0
ok(f"Kalkulation: Zeitanteile ergeben die Laserzeit brutto (Pos. 10 {z1['laser_brutto']:.1f} s, "
   f"Vorschub groß/mittel/klein {z1['vorschub_gross']:g}/{z1['vorschub_mittel']:g}/{z1['vorschub_klein']:g})")
from rohrlaser.angebot_spalten import KALK_SPALTEN  # noqa: E402
assert {"zeit_gross", "zeit_mittel", "zeit_klein", "zeit_gravur", "zeit_einstiche"} <= {x[1] for x in KALK_SPALTEN}
ok("Reiter Kalkulation und CSV: Spalten 'davon …' je Konturklasse")
ziel = tmp / "kalkulation.pdf"
pdf.kalkulation_pdf(ziel, s.kopf, zeilen, summen, s.einst)
inhalt = ziel.read_bytes()
assert ziel.stat().st_size > 1000 and b"%PDF" in inhalt[:10]
ok("Kalkulation-PDF mit Tabelle 'Schneidzeit je Teil nach Konturklassen' erzeugt")
print("Alle Prüfungen bestanden.")
