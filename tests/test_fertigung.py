"""Freigabe und Fertigungsstatus (Wettbewerbsvergleich P1-6) mit P2-Auswertungen (fertigung.py): Status nur für
beauftragte Angebote, nicht doppelt, nicht vor der Freigabe, zurück nur mit Grund; Freigabe hält den Stand fest,
Werkstattpapiere nennen ihn und warnen nach Änderungen; Durchlaufzeiten, Export JSON/CSV, Materialverbrauch je
Charge, Lesemodus, Löschen, ältere Dateien.

Aufruf: python tests/test_fertigung.py
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import fertigung as fe, lager, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank, Lesemodus  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
assert fenster.fertigung_an() and fe.status_liste(db) == list(fe.VORGABE)
aid = beispiel_angebot.anlegen(db)


def fehler(f, text):
    try:
        f()
    except fe.FertigungFehler as ex:
        assert text in str(ex), ex
        return
    raise AssertionError(f"kein Fehler: {text}")


# ------------------------------------------------------------------ Regeln
fehler(lambda: fe.setzen(db, aid, "Freigegeben"), "nur für beauftragte")
db.vorgang_setzen(aid, "Beauftragt")
fehler(lambda: fe.setzen(db, aid, "In Fertigung"), "Zuerst „Freigegeben“")
fehler(lambda: fe.setzen(db, aid, "Gibt es nicht"), "nicht in der Liste")
z = fe.setzen(db, aid, "Freigegeben", wer="PB")
f = fe.freigabe(db, aid)
assert f["version"] == 1 and f["wer"] == "PB" and f["positionen"] == [p["id"] for p in db.positionen(aid)]
assert z["version"] == 1 and not fe.geaendert(db, aid)
fe.setzen(db, aid, "Arbeitsvorbereitung")
fehler(lambda: fe.setzen(db, aid, "Arbeitsvorbereitung"), "steht schon auf")
fe.setzen(db, aid, "In Fertigung")                       # vorwärts darf übersprungen werden
fehler(lambda: fe.setzen(db, aid, "Material bereit"), "nur mit Grund")
fe.setzen(db, aid, "Material bereit", "Material fehlte noch")
assert [x["status"] for x in fe.verlauf(db, aid)] == ["Freigegeben", "Arbeitsvorbereitung", "In Fertigung",
                                                      "Material bereit"]

# Änderung nach der Freigabe: erkannt; Prüfprotokolle zählen nicht; neue Freigabe nur mit Grund -> Version 2
p0 = db.positionen(aid)[0]
db.position_aendern(p0["id"], "step_merkmale", json.dumps(dict(merkmale=[])))
assert not fe.geaendert(db, aid)
db.position_aendern(p0["id"], "stueck", (p0["stueck"] or 0) + 1)
assert fe.geaendert(db, aid)
text, warnung = fe.stand_text(db, aid)
assert "Version 1" in text and "geändert" in warnung
fehler(lambda: fe.setzen(db, aid, "Freigegeben"), "nur mit Grund")
fe.setzen(db, aid, "Freigegeben", "Stückzahl erhöht")
assert fe.freigabe(db, aid)["version"] == 2 and not fe.geaendert(db, aid)
assert fe.verlauf(db, aid)[-1]["version"] == 2

# ------------------------------------------------------------------ Werkstattpapiere mit festgehaltenem Stand
s = fenster.angebot_oeffnen(aid)
assert s.optimieren()
fs = s.freigabe_stand()
assert fs and "Version 2" in fs["text"] and not fs["warnung"]
assert [x["id"] for x in fs["positionen"]] == [p["id"] for p in s.positionen]
w = s.werkstatt_pdf()
if shutil.which("pdftotext"):
    t = subprocess.run(["pdftotext", str(w), "-"], capture_output=True, text=True).stdout
    assert "Freigegebener Stand: Version 2" in t and "Positionen des Auftrags" in t and "ACHTUNG: Angebot" not in t
db.position_aendern(p0["id"], "laenge", 1300.0)
s.neu_laden()
assert s.freigabe_stand()["warnung"]
if shutil.which("pdftotext"):
    assert s.optimieren()
    t = subprocess.run(["pdftotext", str(s.werkstatt_pdf()), "-"], capture_output=True, text=True).stdout
    assert "ACHTUNG: Angebot nach der Freigabe geändert" in t, t[:2000]
fe.setzen(db, aid, "Freigegeben", "Länge geändert")

# ------------------------------------------------------------------ Durchlaufzeiten (Zeitpunkte gesetzt)
a2 = beispiel_angebot.anlegen(db)
db.vorgang_setzen(a2, "Beauftragt")
for st in fe.VORGABE:
    if st != "Fremdvergabe":
        fe.setzen(db, a2, st)
zeiten = ["2026-10-01T08:00:00", "2026-10-01T10:00:00", "2026-10-01T11:00:00", "2026-10-01T15:00:00",
          "2026-10-01T16:30:00", "2026-10-02T08:00:00"]
for (i,), am in zip(db.con.execute("SELECT id FROM auftrag_status WHERE angebot_id=? ORDER BY id", (a2,)).fetchall(),
                    zeiten):
    db.con.execute("UPDATE auftrag_status SET am=? WHERE id=?", (am, i))
db.con.commit()
d = fe.durchlaufzeiten(db, a2)
(a,) = d["auftraege"]
assert a["fertig"] and abs(a["gesamt_h"] - 24.0) < 1e-9
assert a["je_status"] == {"Freigegeben": 2.0, "Arbeitsvorbereitung": 1.0, "Material bereit": 4.0, "In Fertigung": 1.5,
                          "Qualitätsprüfung": 15.5}, a["je_status"]
assert abs(sum(a["je_status"].values()) - a["gesamt_h"]) < 1e-9          # Kontrolle: Summe = Durchlauf
alle = fe.durchlaufzeiten(db)
assert alle["fertig"] == 1 and len(alle["auftraege"]) == 2
fehler(lambda: fe.setzen(db, a2, "Fertig gemeldet"), "steht schon auf")

# ------------------------------------------------------------------ Export und Rückverfolgbarkeit
db.einstellung_setzen("lager_aktiv", "ja")
s = fenster.angebot_oeffnen(aid)
assert s.optimieren()
erst = s.ergebnis["stangen"][0]
lager.zugang(db, "Stange", erst["profil"], erst["werkstoff"], erst["stange"], 1, charge="CH-4711", lagerort="A1")
werte = rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)
plan = lager.planen(db, aid, s.ergebnis, werte)
lager.reservieren(db, aid, s.kopf["nummer"], plan)
lager.verbrauchen(db, aid)
ex = fe.export(db, aid, s.ergebnis)
assert ex["auftrag"]["nummer"] == s.kopf["nummer"] and ex["freigabe"]["version"] == 3
assert [p["id"] for p in ex["positionen"]] == [p["id"] for p in db.positionen(aid)]
assert "preis" not in json.dumps(ex["positionen"])                       # ohne Preise
assert ex["lager"]["status"] == "verbraucht" and any(b["charge"] == "CH-4711" for b in ex["lager"]["stangen"])
assert len(ex["stangen"]) == len(s.ergebnis["stangen"])
csv = fe.export_csv(ex)
assert csv.splitlines()[0].startswith("auftrag;id;pos") and len(csv.splitlines()) == len(ex["positionen"]) + 1
ch = [x for x in lager.verbrauch_je_charge(db) if x["charge"] == "CH-4711"]
assert len(ch) == 1 and ch[0]["nummer"] == s.kopf["nummer"] and ch[0]["laenge"] == erst["stange"]

# ------------------------------------------------------------------ Reiter Fertigung
seite = fenster.fertigung
assert fenster.fertigung_zeigen(aid) and fenster.reiter.currentWidget() is seite
assert seite.markiert()["id"] == aid and seite.verlauf.rowCount() == len(fe.verlauf(db, aid))
assert seite.setzen("Arbeitsvorbereitung", "")
assert not seite.setzen("Arbeitsvorbereitung", "") and "steht schon" in seite.meldung.text()
pfad = seite.exportieren(tmp / "auftrag.json")
assert json.loads(pfad.read_text(encoding="utf-8"))["format"] == "rohrlaser-fertigungsauftrag"
assert pfad.with_suffix(".csv").is_file()
seite.charge_suche.setText("CH-4711")
assert seite.chargen.rowCount() == 1
assert seite.zeiten.rowCount() > 0 and "1 von 2" in seite.zeiten_info.text()
nicht = db.angebot_neu(dict(kunde="offen"))
assert not fenster.fertigung_zeigen(nicht)                               # nicht beauftragt
db.einstellung_setzen("fertigung_aktiv", "nein")
fenster.fertigung_anwenden()
assert not fenster.reiter.isTabVisible(fenster.reiter.indexOf(seite)) and s.freigabe_stand() is None
db.einstellung_setzen("fertigung_aktiv", "ja")
fenster.fertigung_anwenden()

# eigene Statusliste
db.einstellung_setzen("fertigung_status", "Freigegeben\nGelasert\n\nGelasert\nAusgeliefert")
assert fe.status_liste(db) == ["Freigegeben", "Gelasert", "Ausgeliefert"]
fehler(lambda: fe.setzen(db, a2, "Qualitätsprüfung"), "nicht in der Liste")

# ------------------------------------------------------------------ Lesemodus, Löschen
db.lesemodus("Test")
try:
    fe.setzen(db, aid, "Gelasert")
    raise AssertionError("Lesemodus nicht beachtet")
except Lesemodus:
    pass
assert fe.verlauf(db, aid)
db.lesemodus("")
db.angebot_loeschen(a2)
assert not fe.verlauf(db, a2)
db.schliessen()

# ------------------------------------------------------------------ ältere Datei (Schema 64)
alt = tmp / "alt.db"
Datenbank(alt).schliessen()
con = sqlite3.connect(alt)
con.execute("DROP TABLE auftrag_status")
con.execute("ALTER TABLE angebote DROP COLUMN freigabe")
con.execute("PRAGMA user_version=64")
con.commit()
con.close()
d2 = Datenbank(alt)
i = d2.angebot_neu(dict(kunde="alt"))
assert fe.freigabe(d2, i) is None and fe.verlauf(d2, i) == [] and not fe.geaendert(d2, i)
d2.schliessen()
print("test_fertigung OK")
