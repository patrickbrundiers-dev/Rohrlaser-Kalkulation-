"""Prüft Absagegrund und Angebots-Auswertung (Plan 29.10.2026 Schritt 1b):

- A1 Vorgang Abgelehnt mit Grund, Bemerkung, Wettbewerbspreis: Eintrag im Versandverlauf, Text im Verlauf, Tooltip
- A2 der Eintrag zählt nicht als Versand (Wiedervorlage/Nachfassen unverändert)
- A3 Auswertung je Kunde, Werkstoff-Kategorie, Preisklasse, Absagegrund; Trefferquote beauftragt/entschieden;
  Zeitraum; ersetzte Fassungen und Angebote der Kollegen zählen nicht
- A4 Dialoge: Absagegrund (Abbrechen setzt nichts), Auswertung nur mit Admin-Rechten, Menü Datei
- A5 Lesemodus: absage_merken ist schreibend, angebot_werkstoffe lesend

Aufruf: python tests/test_absage.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import absage, cockpit  # noqa: E402
from rohrlaser.angebot_oben import _versand_text  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
heute = datetime.date.today()


def angebot(kunde, werkstoff, netto, vorgang=None, tage=0):
    a = db.angebot_neu(dict(kunde=kunde, skonto=0, stange=6000, datum=(heute - datetime.timedelta(days=tage)).isoformat()))
    db.position_neu(a, dict(pos=10, artikel="T", profil_id="RR 42,4x2,0", werkstoff_id=werkstoff, laenge=1000, stueck=5))
    with db.con:
        db.con.execute("UPDATE angebote SET vk_netto=? WHERE id=?", (netto, a))
    if vorgang:
        db.vorgang_setzen(a, vorgang)
    return a


# A1 Absage mit Grund
a1 = angebot("Muster GmbH", "1.4301", 1800.0, "Verschickt")
db.versand_merken(a1, dict(datum=(heute - datetime.timedelta(days=5)).isoformat(), netto=1800.0, datei="A.pdf"))
assert f.angebote.vorgang_setzen("Abgelehnt", angebot_id=a1, absage=("Preis zu hoch", "Wettbewerb X", 1500.0))
kopf = db.angebot(a1)
assert kopf["vorgang"] == "Abgelehnt"
e = absage.letzte(kopf)
assert e["grund"] == "Preis zu hoch" and e["preis"] == 1500.0 and e["bemerkung"] == "Wettbewerb X", e
assert _versand_text(e) == f"{heute.strftime('%d.%m.%Y')}: abgelehnt – Preis zu hoch (Wettbewerb 1.500,00 €): Wettbewerb X", \
    _versand_text(e)
f.angebote.neu_laden()
m = f.angebote.modell
r = next(i for i, z in enumerate(m.zeilen) if z["id"] == a1)
c = next(i for i, s in enumerate(m.spalten) if s[0] == "Vorgang")
assert m.data(m.index(r, c), Qt.ItemDataRole.ToolTipRole) == "Absagegrund: Preis zu hoch – Wettbewerb X"
ok("A1 Absagegrund im Versandverlauf, Text und Tooltip")

# A2 kein Versand
versandt, nachgefasst, wv = cockpit.verlauf(kopf)
assert versandt == heute - datetime.timedelta(days=5) and nachgefasst is None and wv is None
assert absage.eintrag("", heute=heute) == dict(art="absage", datum=heute.isoformat(), grund="ohne Angabe")
ok("A2 Absage zählt nicht als Versand")

# A3 Auswertung
a2 = angebot("Muster GmbH", "1.4301", 900.0, "Beauftragt")
a3 = angebot("Muster GmbH", "S235-10219", 12000.0, "Beauftragt")
a4 = angebot("Weber KG", "S235-10219", 300.0)
a5 = angebot("Weber KG", "S235-10219", 2500.0, "Abgelehnt")
db.absage_merken(a5, "Lieferzeit zu lang")
a_alt = angebot("Alt AG", "S235-10219", 700.0, "Abgelehnt", tage=200)
a_misch = angebot("Weber KG", "1.4301", 400.0, "Beauftragt")
db.position_neu(a_misch, dict(pos=20, artikel="U", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=500, stueck=1))
a_ersetzt = angebot("Muster GmbH", "1.4301", 999.0, "Abgelehnt")
with db.con:
    db.con.execute("UPDATE angebote SET ersetzt_durch='X' WHERE id=?", (a_ersetzt,))
kat = {w: z.get("kategorie") for w, z in db.kontext().werkstoffe.items()}
aw = absage.auswertung(db.angebote(), db.angebot_werkstoffe(), kat, heute, 90)
g = aw["gesamt"]
assert (g["angebote"], g["beauftragt"], g["abgelehnt"], g["offen"]) == (6, 3, 2, 1), g
assert abs(g["trefferquote"] - 3 / 5) < 1e-9 and g["auftragswert"] == 13300.0
k = {x["name"]: x for x in aw["kunde"]}
assert k["Muster GmbH"]["angebote"] == 3 and abs(k["Muster GmbH"]["trefferquote"] - 2 / 3) < 1e-9
assert k["Weber KG"]["offen"] == 1 and "Alt AG" not in k
ka = {x["name"]: x for x in aw["kategorie"]}
assert ka["Edelstahl"]["angebote"] == 2 and ka["Stahl"]["angebote"] == 3 and ka["gemischt"]["angebote"] == 1, ka
pk = [x["name"] for x in aw["preisklasse"]]
assert pk == ["bis 500 €", "500 bis 2.000 €", "2.000 bis 10.000 €", "über 10.000 €"], pk
gr = {x["name"]: x["angebote"] for x in aw["grund"]}
assert gr == {"Preis zu hoch": 1, "Lieferzeit zu lang": 1}, gr
assert len(aw["wettbewerb"]) == 1 and abs(aw["wettbewerb"][0]["abstand"] - 0.2) < 1e-9
alle = absage.auswertung(db.angebote(), db.angebot_werkstoffe(), kat, heute, None)
assert alle["gesamt"]["angebote"] == 7 and {x["name"] for x in alle["grund"]} >= {"ohne Angabe"}
assert absage.preisklasse(None) == "ohne Preis" and absage.preisklasse(500) == "bis 500 €"
ok("A3 Auswertung je Kunde, Kategorie, Preisklasse, Grund, Zeitraum")

# A4 Dialoge und Menü
from rohrlaser.absage_dialog import AbsageDialog, AuswertungDialog  # noqa: E402
d = AbsageDialog(f, kopf)
d.grund.setCurrentText("Kunde fertigt selbst")
d.bemerkung.setText("macht es intern")
d._ok()
assert d.ergebnis == ("Kunde fertigt selbst", "macht es intern", None)
d2 = AbsageDialog(f, kopf)
d2.reject()
assert d2.ergebnis is None
f.bereich.admin = False
assert f.angebots_auswertung() is None
f.bereich.admin = True
ad = f.angebots_auswertung()
assert isinstance(ad, AuswertungDialog) and ad.tabellen["kunde"].rowCount() == 2
assert "Trefferquote 60 %" in ad.kopf.text(), ad.kopf.text()
ad.zeitraum.setCurrentIndex(2)
assert ad.tabellen["kunde"].rowCount() == 3 and ad.wettbewerb.rowCount() == 1
g0 = ad.tabellen["grund"]
assert g0.columnCount() == 4 and g0.rowCount() == 3 and g0.item(0, 2).text().endswith("%"), g0.rowCount()
assert "Angebots-Auswertung …" in f.datei_aktionen
ok("A4 Absage-Dialog, Auswertung nur mit Admin-Rechten, Menü Datei")

# A5 Lesemodus-Einordnung
assert Datenbank.absage_merken.zugriff == "schreibt" and Datenbank.angebot_werkstoffe.zugriff == "liest"
ok("A5 Lesemodus-Einordnung")
print("Alle Absage-Tests bestanden.")
