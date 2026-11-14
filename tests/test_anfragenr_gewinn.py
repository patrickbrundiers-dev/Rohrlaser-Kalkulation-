"""Angebotsliste mit Anfrage-Nr. und Gewinn, gestaffelter Gewinn im Angebot (Patrick 08.11.2026).

- Angebotsliste: Spalte „Anfrage-Nr.“ (Kopffeld kundenreferenz), die Suche findet sie; Spalte „Gewinn [%]“ mit dem
  festen Gewinn des Angebots bzw. dem beim Öffnen gemerkten wirksamen Gewinn (gestaffelt).
- Kalkulation dieses Angebots: bei gestaffeltem Gewinn steht im Feld „gestaffelt · 30,0 %“ statt des festen Gewinns
  der Einstellungen; eine Zahl = fester Gewinn, Knopf „Gestaffelt“ nimmt ihn wieder weg.
- Bugfix: die Kurzzeile der Kalkulation zeigt keine leeren Felder („Rabatt  %“).
Aufruf: python tests/test_anfragenr_gewinn.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import db_verbindung  # noqa: E402
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from rohrlaser import angebot_fenster, angebot_oben, stil  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


STUFEN = dict(gewinn_bis_1=500, gewinn_satz_1=0.30, gewinn_bis_2=2000, gewinn_satz_2=0.20, gewinn_bis_3=10000,
              gewinn_satz_3=0.12, gewinn_satz_4=0.08)

angebot_fenster.AngebotSeite.CHECK_SOFORT = False
stil.anwenden(app, "hell")
db = Datenbank(Path(tempfile.mkdtemp()) / "x.db")
assert SCHEMA_VERSION >= 77 and "vk_gewinn" in set(db_verbindung.spalten(db.con, "angebote"))
ids = []
for i, (kunde, ref) in enumerate((("Müller", "ANF-2026-0815"), ("Schmidt", "4711"), ("Becker", None))):
    a = db.angebot_neu(dict(kunde=kunde, kundennr=f"K-1004{i}", maschine="T11", stange=6000, kundenreferenz=ref))
    for j in range(3):
        db.position_neu(a, dict(pos=10 * (j + 1), artikel=f"ART-{i}{j}", bezeichnung=f"Teil {j}",
                                profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=500.0 + 300 * j,
                                stueck=10 * (j + 1), schneidweg=400.0, einstiche=4))
    ids.append(a)
for n, w in STUFEN.items():         # gestaffelter Gewinn erst jetzt an: Angebote 1-3 haben festen Gewinn 10 %
    db.einstellung_setzen(n, w)
db.angebot_aendern(ids[0], "gewinn", None)      # Angebot 1: ohne eigenen Gewinn = gestaffelt
assert db.angebot(ids[1])["gewinn"] == 10.0

# ------------------------------------------------------------------ Liste: Anfrage-Nr. und Suche
f = Hauptfenster(db, stumm=True)
f.resize(1366, 728)
f.show()
seite = f.angebote
titel = [s[0] for s in seite.SPALTEN]
assert titel.index("Anfrage-Nr.") == titel.index("Kundennr.") + 1
assert titel.index("Gewinn [%]") == titel.index("Verkaufspreis netto [€]") + 1
seite.suchen("0815")
assert [z["nummer"] for z in seite.modell.zeilen] == [db.angebot(ids[0])["nummer"]], seite.modell.zeilen
spalte = titel.index("Anfrage-Nr.")
assert seite.modell.wert(0, spalte) == "ANF-2026-0815"
seite.suchen("")
ok("Angebotsliste: Spalte Anfrage-Nr. neben der Kundennr., Suche „0815“ findet ANF-2026-0815")

# ------------------------------------------------------------------ Angebot mit gestaffeltem Gewinn
s = f.angebot_oeffnen(ids[0])
QTest.qWait(200)
s.optimieren()
QTest.qWait(300)
kb = s.kopf_bereich
w = kb.felder["gewinn"]
assert kb.gewinn_gestaffelt()
satz = 100 * s._rechnung()[1]["gewinn_satz"]
assert abs(satz - 30.0) < 1e-6, satz
assert w.value() == angebot_oben.GESTAFFELT and w.text() == "gestaffelt · 30,0 %", w.text()
assert "bis 500 €: 30,0 %" in w.toolTip() and "über 10.000 €: 8,0 %" in w.toolTip(), w.toolTip()
assert kb.wert("gewinn") == 30.0 and kb.gewinn_knopf.isHidden()
kurz = kb.kalk_kurz.text()
assert "Gewinn gestaffelt 30,0 %" in kurz and "Gewinn 10,0" not in kurz, kurz
assert "Rabatt" not in kurz and "Eilzuschlag" not in kurz and "Frachtfrei" not in kurz and "  %" not in kurz, kurz
ok("Kalkulation: Gewinnfeld „gestaffelt · 30,0 %“ (vorher fest 10,0), Stufen im Tooltip; Kurzzeile ohne leere Felder")
w.editingFinished.emit()           # Feld nur verlassen: bleibt gestaffelt
assert db.angebot(ids[0])["gewinn"] is None
# Liste: gemerkter wirksamer Gewinn
assert db.con.execute("SELECT vk_gewinn FROM angebote WHERE id=?", (ids[0],)).fetchone()[0] == 30.0
# fester Gewinn eintippen, dann zurück auf gestaffelt
w.setValue(15.0)
w.editingFinished.emit()
QTest.qWait(100)
assert db.angebot(ids[0])["gewinn"] == 15.0 and not kb.gewinn_gestaffelt()
assert w.value() == 15.0 and w.text().startswith("15") and not kb.gewinn_knopf.isHidden()
assert "Gewinn 15,0 %" in kb.kalk_kurz.text()
assert db.con.execute("SELECT vk_gewinn FROM angebote WHERE id=?", (ids[0],)).fetchone()[0] == 15.0
kb.gewinn_knopf.click()
QTest.qWait(100)
assert db.angebot(ids[0])["gewinn"] is None and kb.gewinn_gestaffelt() and w.text() == "gestaffelt · 30,0 %"
ok("Zahl eintippen = fester Gewinn 15 %, Knopf „Gestaffelt“ nimmt ihn wieder weg")

# ------------------------------------------------------------------ Angebot mit festem Gewinn: kein Knopf ohne Stufen
s2 = f.angebot_oeffnen(ids[1])
QTest.qWait(200)
assert s2.kopf_bereich.felder["gewinn"].value() == 10.0 and not s2.kopf_bereich.gewinn_knopf.isHidden()
for n in STUFEN:
    db.einstellung_setzen(n, 0 if n == "gewinn_bis_1" else STUFEN[n])
s2.neu_laden()
assert s2.kopf_bereich.gewinn_knopf.isHidden()
ok("fester Gewinn 10 %: Knopf „Gestaffelt“ nur, solange der gestaffelte Gewinn in den Einstellungen an ist")

# ------------------------------------------------------------------ Liste: Spalte Gewinn
seite.neu_laden()
g = titel.index("Gewinn [%]")
werte = {z["nummer"]: seite.modell.wert(r, g) for r, z in enumerate(seite.modell.zeilen)}
assert werte[db.angebot(ids[0])["nummer"]] == 30.0, werte       # gestaffelt, beim Öffnen gemerkt
assert werte[db.angebot(ids[1])["nummer"]] == 10.0, werte       # fest im Angebot
assert werte[db.angebot(ids[2])["nummer"]] == 10.0, werte       # fest (vor den Stufen angelegt)
db.angebot_aendern(ids[2], "gewinn", None)
seite.neu_laden()
r = next(r for r, z in enumerate(seite.modell.zeilen) if z["id"] == ids[2])
assert seite.modell.wert(r, g) is None
assert "Öffnen" in seite.modell.data(seite.modell.index(r, g), angebot_fenster.Qt.ItemDataRole.ToolTipRole)
ok("Angebotsliste: Spalte Gewinn zeigt festen bzw. gestaffelten Gewinn (beim Öffnen gemerkt), sonst leer")
print("Alle Prüfungen bestanden.")
