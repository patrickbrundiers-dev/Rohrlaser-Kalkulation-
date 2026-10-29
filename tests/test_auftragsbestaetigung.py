"""Prüft die Auftragsbestätigung als PDF (Plan 29.10.2026 Schritt 1c):

- B1 nur für beauftragte Angebote; PDF im Ordner des Angebots, Titel, AB-Nr., Bestellnummer, Liefertermin mit KW,
  Text aus der Einstellung, Preise wie im Angebot, keine Staffelpreise, keine Gültigkeit
- B2 Vermerk im Versandverlauf (art 'ab'): Text, zählt nicht als Versand
- B3 Summe weicht vom verschickten Angebot ab: ohne Zustimmung keine AB
- B4 Nummer wie Angebot (Vorgabe) oder eigener Nummernkreis AB-Jahr-Zähler; eine vergebene AB-Nummer bleibt;
  mit gemeinsamem Ordner reserviert
- B5 Menü Ausgaben, Einstellungen

Aufruf: python tests/test_auftragsbestaetigung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pypdfium2 as pdfium  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import cockpit, nummern, pdf  # noqa: E402
from rohrlaser.angebot_oben import _versand_text  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG  # noqa: E402


def ok(t):
    print("OK:", t)


def text(pfad):
    doc = pdfium.PdfDocument(str(pfad))
    try:
        return "\n".join(seite.get_textpage().get_text_range() for seite in doc)
    finally:
        doc.close()


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
f = Hauptfenster(db, stumm=True)
heute = datetime.date.today()

a = db.angebot_neu(dict(kunde="Muster GmbH", skonto=0, stange=6000))
db.position_neu(a, dict(pos=10, artikel="T-100", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                        stueck=10, schneidweg=300, einstiche=2))
s = f.angebot_oeffnen(a)
s.optimieren()
s.neu_laden()

# B1
assert s.auftragsbestaetigung_pdf() is None, "nicht beauftragt: keine AB"
p_ang = s.angebot_pdf()
netto = db.angebot(a)["versand"][-1]["netto"]
termin = heute + datetime.timedelta(days=20)
f.angebote.vorgang_setzen("Beauftragt", angebot_id=a, auftrag=("BE-4711", termin.isoformat()))
p = s.auftragsbestaetigung_pdf()
assert p is not None and Path(p).name.endswith("Auftragsbestätigung.pdf") and Path(p).parent == Path(p_ang).parent, p
t = text(p)
nr = db.angebot(a)["nummer"]
for soll in (f"Auftragsbestätigung {nr}", "AB-Nr.", "BE-4711", f"KW {termin.isocalendar()[1]}",
             termin.strftime("%d.%m.%Y"), "Vielen Dank für Ihren Auftrag", "Unser Angebot", "Liefertermin: "):
    assert soll in t, (soll, t)
assert "Gültig bis" not in t and "Ab " not in t.replace("AB-Nr.", ""), t
ang_t = text(p_ang)
assert pdf.ab_termin_text(termin.isoformat()) in t and pdf.ab_termin_text(None) == ""
summe = f"{netto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
assert summe in t and summe in ang_t, (summe, t)
ok("B1 AB nur beauftragt, Layout wie Angebot mit Bestellnummer, Liefertermin, gleicher Summe")

# B2
e = db.angebot(a)["versand"][-1]
assert e["art"] == "ab" and e["nummer"] == nr and abs(e["netto"] - netto) < 0.005
assert _versand_text(e).startswith(f"{heute.strftime('%d.%m.%Y')}: Auftragsbestätigung {nr} – "), _versand_text(e)
versandt, _, _ = cockpit.verlauf(db.angebot(a))
assert versandt == heute
assert nummern.ab_vorhanden(db.angebot(a)) == nr
ok("B2 Vermerk im Versandverlauf, zählt nicht als Versand")

# B3 Abweichung
with db.con:
    v = db.angebot(a)["versand"]
    v[0]["netto"] = netto + 50
    import json
    db.con.execute("UPDATE angebote SET versand=? WHERE id=?", (json.dumps(v), a))
n_vor = len(db.angebot(a)["versand"])
assert s.auftragsbestaetigung_pdf() is None and len(db.angebot(a)["versand"]) == n_vor
assert s.auftragsbestaetigung_pdf(abweichung_ok=True) is not None
ok("B3 abweichende Summe nur mit Zustimmung")

# B4 eigener Nummernkreis
db.einstellung_setzen("ab_nummer", nummern.AB_EIGEN)
assert nummern.ab_nummer(db, db.angebot(a)) == nr, "vergebene AB-Nummer bleibt"
b = db.angebot_neu(dict(kunde="Weber KG", skonto=0, stange=6000))
jahr = heute.year
assert nummern.ab_nummer(db, db.angebot(b)) == f"AB-{jahr}-00001"
db.versand_merken(b, dict(art="ab", datum=heute.isoformat(), nummer=f"AB-{jahr}-00001"))
c = db.angebot_neu(dict(kunde="Weber KG", skonto=0, stange=6000))
assert nummern.ab_nummer(db, db.angebot(c)) == f"AB-{jahr}-00002"
assert nummern.ab_nummer(db, db.angebot(c)) == f"AB-{jahr}-00003", "Einstellung letzte_ab_nummer zählt weiter"
assert nummern.ab_zaehler("AB-2026-00042") == 42 and nummern.ab_zaehler("2026-00042") == 0
gemeinsam = tmp / "gemeinsam"
gemeinsam.mkdir()
(gemeinsam / nummern.AB_ORDNER).mkdir()
(gemeinsam / nummern.AB_ORDNER / "00010.nummer").write_text("x")
from rohrlaser import teilen  # noqa: E402
alt_aktiv, alt_ordner = teilen.aktiv, teilen.ordner
teilen.aktiv, teilen.ordner = (lambda db: True), (lambda db: gemeinsam)
try:
    assert nummern.ab_nummer(db, db.angebot(c)) == f"AB-{jahr}-00011"
    assert (gemeinsam / nummern.AB_ORDNER / "00011.nummer").exists()
finally:
    teilen.aktiv, teilen.ordner = alt_aktiv, alt_ordner
ok("B4 Nummer wie Angebot oder eigener Nummernkreis, reserviert im gemeinsamen Ordner")

# B5
texte = [x.text() for x in s.weitere.menu().actions()]
assert "Auftragsbestätigung (PDF)" in texte, texte
assert EINSTELLUNG["ab_nummer"].vorgabe == nummern.AB_WIE_ANGEBOT and EINSTELLUNG["ab_text"].vorgabe
ok("B5 Menü Ausgaben und Einstellungen")
print("Alle Auftragsbestätigungs-Tests bestanden.")
