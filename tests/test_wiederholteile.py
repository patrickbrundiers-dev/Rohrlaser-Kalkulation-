"""Wiederholteile erkennen (Plan A1): Treffer exakt (Artikelnummer, Kunde, Geometrie), Werte einzeln übernehmen, nie
den Preis."""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import wiederholteile as wt  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# ohne Datenbank: Einstufung und Geometrie
neu = dict(artikel="4711-001", profil_id="RR 42,4x2,0", werkstoff_id="S235", laenge=1250.0, schneidweg=410.5, klein_n=2)
assert wt.einstufen(neu, dict(neu, artikel=" 4711-001 "), "K1", "K1") == wt.SICHER       # Leerzeichen egal
assert wt.einstufen(neu, dict(neu), "K1", "K2") == wt.PRUEFEN
assert wt.einstufen(neu, dict(neu, artikel="X"), "K1", "K1") == wt.AEHNLICH
assert wt.einstufen(neu, dict(neu, artikel="X", laenge=1250.5), "K1", "K1") == wt.AEHNLICH       # ± 0,5 mm
assert wt.einstufen(neu, dict(neu, artikel="X", laenge=1250.6), "K1", "K1") is None
assert wt.einstufen(neu, dict(neu, artikel="X", schneidweg=414.6), "K1", "K1") == wt.AEHNLICH    # < 1 %
assert wt.einstufen(neu, dict(neu, artikel="X", schneidweg=416.0), "K1", "K1") is None
assert wt.einstufen(neu, dict(neu, artikel="X", klein_n=3), "K1", "K1") is None                  # Konturanzahl
assert wt.einstufen(neu, dict(neu, artikel="X", werkstoff_id="S355"), "K1", "K1") is None
assert wt.einstufen(dict(neu, artikel=""), dict(neu, artikel=""), "", "") == wt.AEHNLICH
assert wt.preis_aus_staffeln({"zeilen": [dict(schluessel="10", menge=24, preis_einheit=5.1),
                                         dict(schluessel="10", menge=50, preis_einheit=4.85),
                                         dict(schluessel="Rahmen", einheit="Satz", menge=50, preis_einheit=99)]},
                             10, 45) == (50, 4.85)
ok("Einstufung: sicher (Nummer + Kunde), prüfen (anderer Kunde), ähnlich (Profil, Werkstoff, Länge ±0,5, "
   "Schneidweg ±1 %, Konturen); Preis aus den Staffelpreisen bei der nächsten Menge")

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
alt_id = beispiel_angebot.anlegen(db, dict(datum="2026-09-12"))
alt_pos = db.positionen(alt_id)
db.position_aendern(alt_pos[0]["id"], "zeit_manuell", 38.0)
db.position_aendern(alt_pos[0]["id"], "prog_zeit", 7.5)
db.vorgang_setzen(alt_id, "Beauftragt")
s_alt = f.angebot_oeffnen(alt_id)
assert s_alt.optimieren() and s_alt.staffelpreise_rechnen()
anderer = beispiel_angebot.anlegen(db, dict(kundennr="K-99999", kunde="Andere AG", datum="2026-08-01"))

neu_id = db.angebot_neu(dict(kundennr="K-10045", kunde="Beispiel GmbH"))
for p in beispiel_angebot.POSITIONEN[:1] + [dict(pos=99, artikel="NEU-1", profil_id="QR 40x40x3",
                                                 werkstoff_id="S235-10219", laenge=2150.3, stueck=5, schneidweg=520.0,
                                                 einstiche=3),
                                            dict(pos=98, artikel="EINZEL", profil_id="QR 40x40x3",
                                                 werkstoff_id="S235-10219", laenge=999.0, stueck=1)]:
    db.position_neu(neu_id, p)
s = f.angebot_oeffnen(neu_id)
treffer = s.wiederholteile_suchen()
pos = {p["pos"]: p for p in s.positionen}
t10 = treffer[pos[10]["id"]]
assert [t.art for t in t10] == [wt.SICHER, wt.PRUEFEN], [t.art for t in t10]
assert t10[0].angebot["id"] == alt_id and t10[0].angebot["vorgang"] == "Beauftragt"
assert t10[0].preis == (24, next(z["preis_einheit"] for z in s_alt.kopf["staffelpreise"]["zeilen"]
                                 if z["schluessel"] == "10" and z["menge"] == 24))
assert t10[0].werte == {"zeit_manuell": 38.0, "prog_zeit": 7.5}, t10[0].werte
assert [t.art for t in treffer[pos[99]["id"]]] == [wt.AEHNLICH, wt.AEHNLICH]          # Pos. 30 beider Angebote
assert pos[98]["id"] not in treffer
ok("Treffer exakt: Pos. 10 sicher (beauftragt, Preis aus Staffel) vor prüfen; Pos. 99 ähnlich; Pos. 98 ohne Treffer")

zeile = s.wiederholteile_suchen() and next(r for r, p in enumerate(s.positionen) if p["pos"] == 10)
text = s.uebersicht_bereich.wiederholteile.text()
assert s.uebersicht_bereich.wiederholteile_bereich.isVisibleTo(s.uebersicht_bereich)
assert "2× angeboten · zuletzt 12.09.2026" in text and "beauftragt" in text and "Werte übernehmen" in text, text
assert "Wiederholteile: 2 Positionen" in s.uebersicht_bereich.wiederholteile_bereich.knopf.text()
ok("Übersicht: Wiederholteile mit Anzahl, Datum, Angebot, Preis, Vorgang und Links")

vk_vorher = s._rechnung()[1]["verkauf"]
assert s.werte_uebernehmen(zeile, ["zeit_manuell"]) == ["zeit_manuell"]
p10 = next(p for p in s.positionen if p["pos"] == 10)
assert p10["zeit_manuell"] == 38.0 and not p10.get("prog_zeit")
assert s._rechnung()[1]["verkauf"] != vk_vorher           # Preis neu gerechnet (andere Schneidzeit), nicht kopiert
ok("Werte übernehmen: nur das gewählte Feld; der Preis entsteht neu aus der Kalkulation")

assert s.rueckgaengig() and not next(p for p in s.positionen if p["pos"] == 10).get("zeit_manuell")
ok("Übernahme lässt sich rückgängig machen")

s.wiederholteil_link(f"oeffnen:{alt_id}")
assert f.reiter.currentWidget() is s_alt
s.wiederholteil_link(f"hin:{zeile}")
assert f.reiter.currentWidget() is s and s.pos_ansicht.currentIndex().row() == zeile
ok("Links: Angebot öffnen, Hinspringen")
vorher = s.wiederholteile_suchen()
assert s.wiederholteile_suchen() is vorher                # unverändert: aus dem Zwischenspeicher
db.position_aendern(alt_pos[0]["id"], "prog_zeit", 9.0)   # anderes Angebot geändert (auch abgeglichenes des Kollegen)
s.neu_laden()
p10 = next(p for p in s.positionen if p["pos"] == 10)
assert s.wiederholteile_suchen()[p10["id"]][0].werte["prog_zeit"] == 9.0
db.angebot_loeschen(anderer)
assert [t.art for t in s.wiederholteile_suchen()[p10["id"]]] == [wt.SICHER]
ok("Zwischenspeicher: Änderung oder Löschen eines anderen Angebots wird beim Neuladen erkannt")

# Anzeige mit Bildschirm: Datenbank filtert vor (Indizes), eingestuft wird im Thread, danach erscheint die Zeile
from PySide6.QtTest import QTest  # noqa: E402

plan = " ".join(str(r[-1]) for r in db.con.execute(
    "EXPLAIN QUERY PLAN SELECT * FROM positionen p WHERE LOWER(TRIM(p.artikel)) IN ('x') OR "
    "(p.profil_id = 'RR' AND p.laenge BETWEEN 1 AND 2)"))
assert "positionen_artikel" in plan and "positionen_profil_laenge" in plan, plan
soll = {k: [(t.art, t.position["id"]) for t in v] for k, v in s.wiederholteile_suchen().items()}
f.stumm = False
try:
    s._wt_kennung = s._wt = None
    s.uebersicht_bereich.wiederholteile_setzen([])
    s.wiederholteile_anzeigen()
    assert s._wt_lauf is not None and s._wt is None, "läuft im Thread"
    assert not s.uebersicht_bereich.wiederholteile.text()
    for _ in range(200):
        if s._wt_lauf is None:
            break
        QTest.qWait(20)
    assert s._wt_lauf is None
    assert {k: [(t.art, t.position["id"]) for t in v] for k, v in s._wt.items()} == soll
    assert "schon angeboten" in s.uebersicht_bereich.wiederholteile_bereich.knopf.text()
finally:
    f.stumm = True
ok("Mit Bildschirm: Suche über Indizes, Einstufen im Hintergrund, gleiche Treffer, danach angezeigt")
print("OK: Wiederholteile")
