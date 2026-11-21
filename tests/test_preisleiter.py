"""Preisleiter, eine Margenformel und Wirtschaftlichkeits-Ampel (Master-Prompt Angebotserstellung, Patrick 21.11.2026).

- marge.py: Marge vom Warenwert = bisherige Check-Marge ohne Rabatt, mit Rabatt zählt der Rabatt mit; Aufschlag ↔ Marge,
- Preisleiter: Untergrenzen, Mindest- und Zielpreis mit genau der eingestellten Marge, Angebotspreis,
- „Auf Zielmarge setzen“ stellt den Gewinn so ein, dass die volle Kalkulation die Zielmarge erreicht,
- Ampel gut/knapp/kritisch und Kacheln „Gewinn und Marge“ und „Wirtschaftlichkeit“ im Angebot.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import freigabe, preisleiter as pl  # noqa: E402
from rohrlaser import marge as mg  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, eps=1e-6):
    return abs(a - b) <= eps


# ------------------------------------------------------------------ Formeln ohne Angebot
assert nah(mg.aus_aufschlag(0.25), 0.2) and nah(mg.aus_marge(0.2), 0.25) and mg.aus_marge(1) is None
s = dict(selbst=1000.0, gewinn=100.0, verkauf=1100.0 / 0.98, skonto=1100.0 / 0.98 * 0.02, skonto_satz=2.0)
w = mg.werte(s)
assert nah(w["gewinn"], 100) and nah(w["marge"], 100 / 1100) and nah(w["aufschlag"], 0.1)
alt = (100.0 + 0) / (1000 + 100 + 0)            # Formel des Angebots-Checks bis 20.11.2026
assert nah(freigabe.marge(s), alt), "ohne Rabatt bitgleich zur bisherigen Marge"
assert nah(mg.preis_bei_marge(s, w["marge"]), s["verkauf"]), "Preis bei der eigenen Marge = Verkaufspreis"
r = dict(s, verkauf=s["verkauf"] * 0.95, skonto=s["verkauf"] * 0.95 * 0.02, rabatt=-s["verkauf"] * 0.05)
assert mg.marge(r) < w["marge"] - 0.04, "Rabatt senkt die Marge"
ok("marge.py: Aufschlag 25 % = Marge 20 %, ohne Rabatt wie bisher, Rabatt zählt mit, Preis bei Marge")

b = pl.bewertung(s, dict(mindestmarge=0.05, zielmarge=0.12))
assert b["stufe"] == pl.KNAPP and "Zielmarge" in b["gruende"][0], b
assert pl.bewertung(s, dict(mindestmarge=0.10))["stufe"] == pl.KRITISCH
assert pl.bewertung(s, dict(zielmarge=0.05))["stufe"] == pl.GUT
assert pl.bewertung(s, {})["stufe"] == pl.GUT                       # 9,1 % ≥ 8 %
assert pl.bewertung(dict(s, verkauf=900.0, skonto=18.0), {})["stufe"] == pl.KRITISCH
assert pl.bewertung(s, dict(zielmarge=0.05), unsicher=0.4)["stufe"] == pl.KNAPP
ok("Ampel: knapp unter Zielmarge, kritisch unter Mindestmarge oder Kosten, unsichere Werte = knapp")

# ------------------------------------------------------------------ im Angebot
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
db.einstellung_setzen("mindestmarge", 0.05)
db.einstellung_setzen("zielmarge", 0.15)
f = Hauptfenster(db, tmp, stumm=True)
a = beispiel_angebot.anlegen(db)
s = f.angebot_oeffnen(a)
assert s.optimieren()
_, summen = s._rechnung()
z = pl.zeilen(summen, s.einst)
arten = [x["art"] for x in z]
assert {pl.ART_KURZ, pl.ART_LANG, pl.ART_MINDEST, pl.ART_ZIEL, pl.ART_ANGEBOT} <= set(arten), arten
assert [x["netto"] for x in z] == sorted(x["netto"] for x in z)
zeile = {x["art"]: x for x in z}
assert nah(zeile[pl.ART_ZIEL]["marge"], 0.15, 1e-9) and nah(zeile[pl.ART_MINDEST]["marge"], 0.05, 1e-9)
assert nah(zeile[pl.ART_ANGEBOT]["marge"], freigabe.marge(summen))
assert nah(zeile[pl.ART_ZIEL]["aufschlag"], mg.aus_marge(0.15), 1e-9)
ok(f"Preisleiter: {len(z)} Stufen aufsteigend; Zielpreis {zeile[pl.ART_ZIEL]['netto']:.2f} € mit genau 15 % Marge")

kz = s.uebersicht_bereich.kennzahl
assert "Marge" in kz["gewinn"].text() and "Aufschlag" in kz["gewinn"].text()
assert pl.KNAPP in kz["wirtschaft"].text() or pl.KRITISCH in kz["wirtschaft"].text(), kz["wirtschaft"].text()
ok("Kacheln: Gewinn mit Marge und Aufschlag, Ampel unter der Zielmarge nicht grün")

vk_alt = summen["verkauf"]
d = s.preisleiter(dialog=lambda d: None)
assert d.tabelle.rowCount() == len(z) and d.ziel_knopf.isEnabled()
g = d.setzen(pl.ART_ZIEL)
_, summen2 = s._rechnung()
m2 = mg.marge(summen2)
assert g is not None and 0.15 - 1e-9 <= m2 < 0.1505, (g, m2)
assert summen2["verkauf"] > vk_alt and nah(s.kopf["gewinn"], round(100 * g, 2))
assert pl.bewertung(summen2, s.einst, s.unsicher_anteil())["stufe"] in (pl.GUT, pl.KNAPP)
assert "gut" in kz["wirtschaft"].text() or s.unsicher_anteil(), kz["wirtschaft"].text()
ok(f"Auf Zielmarge gesetzt: Gewinn {100 * g:.2f} %, Marge {100 * m2:.2f} %, Preis {summen2['verkauf']:.2f} €")

# Rabatt: Check-Marge sinkt (vorher übersah die Marge des Checks den Rabatt)
db.angebot_aendern(a, "rabatt", 10.0)
s.neu_laden()
_, summen3 = s._rechnung()
assert mg.marge(summen3) < m2 - 0.05
assert pl.bewertung(summen3, s.einst)["stufe"] == pl.KRITISCH or mg.marge(summen3) >= 0.05
ok(f"Rabatt 10 %: Marge {100 * mg.marge(summen3):.1f} % statt {100 * m2:.1f} %")
d.deleteLater()
f.close()
print("OK: Preisleiter und Wirtschaftlichkeit")
