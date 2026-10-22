"""Prüft das Fenster 'Material …' (Materialeinsatz und Materialwerte je Abmessung, Patrick 22.10.2026), die
Querschnitt-Bilder und das überarbeitete Kalkulation-PDF (Materialeinsatz, leere Spalten ausgeblendet, Anteil der
Kostenarten, Stangenbild am Ende).

Aufruf: python tests/test_material_fenster.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import pdf, querschnitt, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.meterpreis_dialog import querschnitt_pixmap  # noqa: E402


def ok(text):
    print("OK    ", text)


# --- Querschnitte aller Profilformen
FORMEN = [dict(profil_id="RR 42,4x2,0", form="Rundrohr", a=42.4, wand=2),
          dict(profil_id="QR 40x40x3", form="Quadratrohr", a=40, b=40, wand=3),
          dict(profil_id="RE 60x40x3", form="Rechteckrohr", a=40, b=60, wand=3),
          dict(profil_id="U 50x30x3", form="U-Profil", a=50, b=30, wand=3),
          dict(profil_id="C 50x30x2", form="C-Profil", a=50, b=30, wand=2),
          dict(profil_id="L 40x20x3", form="L-Profil", a=20, b=40, wand=3),
          dict(profil_id="FL 50x5", form="Flachstahl", a=50, wand=5),
          dict(profil_id="IPE 200", form="I-/H-Träger", a=200, b=100, wand=5.6),
          dict(profil_id="T 50", form="T-Profil", a=50, b=50, wand=6)]
for pr in FORMEN:
    q = querschnitt.kontur(pr)
    assert q and q["flaechen"] and q["breite"] > 0 and q["hoehe"] > 0, pr
    for poly in q["flaechen"]:
        assert all(-1e-6 <= x <= q["breite"] + 1e-6 and -1e-6 <= y <= q["hoehe"] + 1e-6 for x, y in poly), pr
q = querschnitt.kontur(FORMEN[2])
assert (q["breite"], q["hoehe"]) == (60, 40) and len(q["flaechen"]) == 2
assert querschnitt.kontur(dict(profil_id="X", form="Sonderprofil", a=None)) is None
assert querschnitt.kontur(None) is None
ok("Querschnitt je Profilform im Hüllmaß, Rechteckrohr Breitseite oben, Sonderprofil ohne Bild")
from rohrlaser import rp_profile  # noqa: E402
rp = next(iter(rp_profile.bibliothek().values()), None)
if rp:
    q = querschnitt.kontur(rp_profile.stammdaten_zeile(rp))
    assert q and q["linien"] and not q["flaechen"]
    ok(f"RP-Profil {rp['profil_id']}: Kontur aus dem MegaCAD-Makro")

# --- Angebot
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
an = beispiel_angebot.anlegen(db)
s = fenster.angebot_oeffnen(an)
for pr in FORMEN[:3]:
    assert not querschnitt_pixmap(s.k.profile.get(pr["profil_id"]) or pr).isNull()
ok("Querschnitt als Bild im Fenster")

gr = rechnen.material_abmessungen(s.kopf, s.positionen, None, s.k, s.tabellen)
assert [g["profil"] for g in gr] == ["RR 42,4x2,0", "QR 40x40x3", "RE 60x40x3", "RR 48,3x2,6"]
assert gr[0]["positionen"] == [10, 20] and all(g["stangen"] == 0 for g in gr)
ok("ohne Schnittplan: je Abmessung eine Zeile, Positionen zusammengefasst")
assert s.optimieren()
gr = rechnen.material_abmessungen(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen)
sw = rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)
assert sum(g["stangen"] for g in gr) == len(s.ergebnis["stangen"])
assert abs(sum(g["kosten"] for g in gr) - sum(w["kosten"] for w in sw)) < 1e-6
assert abs(sum(g["kg"] for g in gr) - sum(w["gewicht"] for w in sw)) < 1e-6
assert all(0 < g["ausnutzung"] <= 1 and g["manuell"] is None and abs(g["wirksam"] - g["berechnet"]) < 1e-9 for g in gr)
ok(f"Materialeinsatz: {sum(g['stangen'] for g in gr)} Stangen, {sum(g['kosten'] for g in gr):.2f} € = Schnittplan")


# --- Fenster: Meterpreis, Lieferlänge, Material, Handling
def bedienen(werte):
    def f(d):
        werte(d)
        d.annehmen()
        return d.result()
    return f


def meterpreis(d):
    d.felder[0].setText("3,50")
    d.felder[1].setText(d.felder[1].placeholderText())      # berechneten Wert bestätigt: bleibt berechnet


vorher = s._rechnung()[1]["material"]
assert s.material_einstellen(bedienen(meterpreis)) == 1
pm = {p["pos"]: p.get("preis_m") for p in s.positionen}
assert pm[10] == pm[20] == 3.5 and pm[30] is None
g = rechnen.material_abmessungen(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen)[0]
assert g["manuell"] == 3.5 and g["wirksam"] == 3.5
assert s._rechnung()[1]["material"] > vorher
ok("Meterpreis 3,50 €/m an allen Positionen der Abmessung gespeichert, geht in die Kalkulation ein")

assert s.material_einstellen(bedienen(lambda d: None)) == 0
ok("unverändert übernommen: nichts gespeichert")


def leeren(d):
    assert d.felder[0].text() == "3,50"
    d.felder[0].setText("")


assert s.material_einstellen(bedienen(leeren)) == 1
assert all(p.get("preis_m") is None for p in s.positionen)
ok("Feld geleert: wieder berechnet")


def anderes(d):
    d.laengen[1].setCurrentText("12.000")
    d.herkunft[2].setCurrentText("Kunde beigestellt")
    assert not d.felder[2].isEnabled()
    d.handling.setText("0,15")
    d.werkstoffe[3].setCurrentText("S355-10219")


assert s.material_einstellen(bedienen(anderes)) == 4
p30, p40 = (next(p for p in s.positionen if p["pos"] == n) for n in (30, 40))
assert p30["stange"] == 12000 and p40["material_herkunft"] == "Kunde beigestellt"
assert abs(s.kopf["handling_beistellung"] - 0.15) < 1e-9
assert next(p for p in s.positionen if p["pos"] == 50)["werkstoff_id"] == "S355-10219"
assert s.stand_optimierung() != "aktuell"
ok("Werkstoff S355, Lieferlänge 12 m, Kundenmaterial und Handling 0,15 €/kg gespeichert; Schnittplan veraltet")


def falsch(d):
    d.felder[0].setText("abc")
    d.annehmen()
    assert d.fehler.text() and d.result() == 0
    return 0


assert s.material_einstellen(falsch) == 0
ok("ungültige Eingabe: Fehlermeldung, nichts gespeichert")

# --- Kalkulation-PDF
assert s.optimieren()
sp = pdf.spalten_waehlen(pdf.KALK, [dict(pos=10, stueck=1, gewindezeit=0, zusatz_teil=0.0004, skonto_teil=1)],
                         273 * pdf.mm)
namen = [x[0][1] for x in sp]
assert "gewindezeit" not in namen and "zusatz_teil" not in namen and "skonto_teil" in namen and "hinweis" not in namen
assert abs(sum(b for _, b in sp) - 273 * pdf.mm) < 0.01
ok("Kalkulation je Position: Spalten ohne Wert ausgeblendet, Rest auf volle Breite")
ziel = tmp / "kalkulation.pdf"
s._ziel = lambda *a: ziel
assert s.kalkulation_pdf()
inhalt = ziel.read_bytes()
seiten = inhalt.count(b"/Type /Page\n") or inhalt.count(b"/Type /Page ")
leer = tmp / "ohne.pdf"
zeilen, summen = s._rechnung()
pdf.kalkulation_pdf(leer, s.kopf, zeilen, summen, s.einst)
seiten_ohne = leer.read_bytes().count(b"/Type /Page\n") or leer.read_bytes().count(b"/Type /Page ")
assert seiten > seiten_ohne, (seiten, seiten_ohne)
ok(f"Kalkulation-PDF mit Materialeinsatz und Stangenbild: {seiten} Seiten (ohne: {seiten_ohne})")
print("Alle Prüfungen bestanden.")
