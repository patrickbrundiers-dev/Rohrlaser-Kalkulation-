"""Prüft „Neue Fassung“ (Plan „Arbeitsabläufe effizienter“ W10, Schritt AB3): gleiche Nummer mit Zusatz -2, -3,
gleicher Kunde, heutiges Datum, aktuelle Preise und Stundensätze, Positionen und Staffeln mitkopiert; die alte
Fassung steht auf „Ersetzt durch …“, zählt in keinem Vorgang; der Zähler der Angebotsnummern bleibt.

Aufruf: python tests/test_neue_fassung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from rohrlaser import cockpit  # noqa: E402
from rohrlaser.angebot_fenster import VORGANG_FILTER, vorgang  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert SCHEMA_VERSION >= 52
fenster = Hauptfenster(db, tmp, stumm=True)
a = beispiel_angebot.anlegen(db)
alt = db.angebot(a)
db.angebot_aendern(a, "datum", "2026-01-15")
db.vorgang_setzen(a, "Verschickt")
db.preisbasis_speichern(a, {"test": 1})          # festgeschriebene Preise der verschickten Fassung
assert db.angebot(a)["preisbasis"]
letzte = db.einstellung("letzte_angebotsnummer")
n_pos, n_st = len(db.positionen(a)), len(db.staffeln(a))

# Datenbank: Nummer, Kunde, Datum, Inhalt, Zähler
assert db.fassung_nummer(a) == alt["nummer"] + "-2"
f2 = db.angebot_fassung(a)
k2 = db.angebot(f2)
assert k2["nummer"] == alt["nummer"] + "-2" and k2["kundennr"] == alt["kundennr"] and k2["kunde"] == alt["kunde"]
assert k2["datum"] != "2026-01-15" and (k2.get("vorgang") or "Entwurf") == "Entwurf" and not k2.get("preisbasis")
assert len(db.positionen(f2)) == n_pos and len(db.staffeln(f2)) == n_st
assert db.angebot(a)["ersetzt_durch"] == k2["nummer"] and k2["fassung_basis"] == alt["nummer"]
assert db.einstellung("letzte_angebotsnummer") == letzte
neu = db.angebot(db.angebot_neu())
assert not neu["nummer"].endswith("-2") and neu["nummer"] != k2["nummer"]
ok("Neue Fassung: Nummer -2, gleicher Kunde, heute, Entwurf, Positionen/Staffeln, aktuelle Preise; Zähler unberührt")

# Fassung der Fassung: -3 (Basis bleibt die ursprüngliche Nummer), auch aus der alten Fassung heraus
f3 = db.angebot_fassung(f2)
assert db.angebot(f3)["nummer"] == alt["nummer"] + "-3" and db.angebot(f2)["ersetzt_durch"] == alt["nummer"] + "-3"
assert db.fassung_nummer(a) == alt["nummer"] + "-4"
ok("Fassung von -2 wird -3 (nicht -2-2); nächste wäre -4")

# Liste und Startseite: alte Fassungen „Ersetzt“, in keinem Vorgang, eigener Filter
zeilen = {z["id"]: z for z in db.angebote()}
assert vorgang(zeilen[a]) == "Ersetzt" and vorgang(zeilen[f3]) == "Entwurf"
assert not VORGANG_FILTER["Offen (Entwurf, Verschickt)"](vorgang(zeilen[a]), False, zeilen[a])
assert VORGANG_FILTER["Ersetzt (alte Fassungen)"](vorgang(zeilen[f2]), False, zeilen[f2])
zeilen[a]["vorgang"] = "Verschickt"
assert all(w[0]["id"] not in (a, f2) for w in cockpit.wiedervorlagen(list(zeilen.values()), 1, vorlauf=10000))
verschickt = dict((v, n) for v, n, _ in cockpit.pipeline(list(zeilen.values())))["Verschickt"]
assert verschickt == 0, verschickt
liste = fenster.angebote
liste.neu_laden()
texte = [liste.modell.data(liste.modell.index(r, 5)) for r in range(liste.modell.rowCount())]
assert f"Ersetzt durch {alt['nummer']}-2" in texte, texte
ok("Angebotsliste: „Ersetzt durch …“, nicht offen, Filter „Ersetzt (alte Fassungen)“, keine Wiedervorlage")

# Oberfläche: Datei → Neue Fassung des Angebots für das offene Angebot; alte Fassung schließt
s = fenster.angebot_oeffnen(f3)
fenster.datei_aktionen["Neue Fassung des Angebots"].trigger()
app.processEvents()
f4 = max(z["id"] for z in db.angebote())
assert db.angebot(f4)["nummer"] == alt["nummer"] + "-4" and f3 not in fenster.offen
assert fenster.reiter.currentWidget() is fenster.offen[f4]
assert "Neue Fassung" in fenster.verlauf.eintraege[-1][1]     # Statuszeile läuft nach 8 s ab
ok("Datei → Neue Fassung des Angebots: neue Fassung offen, alte geschlossen, Statuszeile")

# Lesemodus und fremde Angebote: keine Fassung
n = len(db.angebote())
db.nur_lesen = "Test"
assert liste.neue_fassung(f4) is None and len(db.angebote()) == n
db.nur_lesen = None
db.con.execute("UPDATE angebote SET fremd='XY' WHERE id=?", (neu["id"],))
assert liste.neue_fassung(neu["id"]) is None and len(db.angebote()) == n
ok("Lesemodus und Angebote der Kollegen: keine neue Fassung")

print("Alle Prüfungen bestanden.")
