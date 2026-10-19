"""Prüft das Windows-Programm: Datenbank, Beispieldaten, Prüfregeln, Oberfläche (Schritt 1);
Angebote, STEP-Übernahme, Optimierung und Angebotsfenster (Schritt 2), Staffeln und Ausgaben (Schritt 3).
Die Rechnung selbst rechnet tests/test_abnahme.py unabhängig nach.

Aufruf: python tests/test_programm.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import (TABELLE, PROFILE, PREISE, Kontext, beispieldaten, flaeche_berechnet,  # noqa: E402
                                  preis_je_m_automatisch, pruefen, wert_aus_text, wert_als_text)

tmp = Path(tempfile.mkdtemp())

# 1) Neue Datenbank: Beispieldaten und Vorgaben der Einstellungen
db = Datenbank(tmp / "a" / "rohrlaser.db")
assert db.einstellung("stammdaten_herkunft") == "Beispieldaten"
for name, zeilen in beispieldaten().items():
    gelesen = [{k: v for k, v in z.items() if k != "id"} for z in db.zeilen(name)]
    assert gelesen == zeilen, name
assert db.einstellung("zuschlag_fertigung") == 0.15 and db.einstellung("standard_stange") == 6000
assert db.einstellung("mwst") == 0.19
assert db.einstellung("profilformen").splitlines() == ["Rundrohr", "Quadratrohr", "Rechteckrohr", "Sonderprofil"]

# 2) Eingabe: deutsche Zahlen, Bereiche, ganze Zahlen, Datum
f = PROFILE.feld("a")
assert wert_aus_text(f, "42,4") == 42.4 and wert_aus_text(f, "42.4") == 42.4 and wert_aus_text(f, " ") is None
for falsch in ("abc", "0,5", "1001"):
    try:
        wert_aus_text(f, falsch)
        raise AssertionError(falsch)
    except ValueError:
        pass
fl = PREISE.feld("lieferlaenge")
assert wert_aus_text(fl, "6.000") == 6000 and wert_als_text(fl, 6000) == "6.000"
try:
    wert_aus_text(fl, "6000,5")
    raise AssertionError("ganze Zahl")
except ValueError:
    pass
assert wert_aus_text(PREISE.feld("gueltig_ab"), "01.10.2026") == "2026-10-01"
assert wert_als_text(PREISE.feld("preis"), 1234.5) == "1.234,50"

# 3) Berechnete Spalten
assert abs(flaeche_berechnet(dict(profil_id="x", form="Rundrohr", a=42.4, wand=2)) - math.pi / 4 * (42.4 ** 2 - 38.4 ** 2)) < 1e-9
assert flaeche_berechnet(dict(profil_id="x", form="Quadratrohr", a=40, wand=3)) == 40 * 40 - 34 * 34
assert flaeche_berechnet(dict(profil_id="x", form="Rechteckrohr", a=60, b=40, wand=3)) == 60 * 40 - 54 * 34
assert flaeche_berechnet(dict(profil_id="x", form="Rechteckrohr", a=60, b=None, wand=3)) is None
k = db.kontext()
p = preis_je_m_automatisch(dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219"), k)
assert abs(p - 444 * 7.85 / 1000 * 1000 / 1000) < 1e-9, p

# 4) Prüfung (Spalte 'Prüfung') und Eingabeprüfungen
ok = lambda t, z: pruefen(TABELLE[t], z, k)
assert ok("profile", dict(profil_id="RR 1", form="Rundrohr", a=20, wand=10)).startswith("FEHLER: Wandstärke")
assert ok("profile", dict(profil_id="RE 1", form="Rechteckrohr", a=60, wand=3)) == "FEHLER: Abmessung B fehlt"
assert ok("profile", dict(profil_id="SP 1", form="Sonderprofil", flaeche_manuell=300)) == "OK"
assert ok("profile", dict(profil_id="SP 2", form="Sonderprofil")).startswith("FEHLER: Querschnitt")
assert ok("profile", dict(profil_id="X", form="Dreieck", a=20, wand=2)) == "FEHLER: Profilform unbekannt"
z = dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", basis="€/kg", preis=1.2)
assert ok("preise", z) == "OK"
assert ok("preise", dict(z, profil_id="RR 99")) == "FEHLER: Profil-ID unbekannt"
assert ok("preise", dict(z, werkstoff_id="X")) == "FEHLER: Werkstoff-ID unbekannt"
assert ok("preise", dict(z, preis=None)) == "FEHLER: Preis [€] fehlt"
assert ok("preise", dict(z, basis="€/Stange")) == "FEHLER: Stangenlänge fehlt"
assert ok("schneiddaten", dict(maschinen_id="RL-9", werkstoff_id="1.4301", wand_bis=2, vorschub_gross=100)) \
    == "FEHLER: Maschinen-ID unbekannt"
for t in TABELLE.values():
    for zeile in db.zeilen(t.name):
        assert pruefen(t, zeile, k) == "OK", (t.name, zeile, pruefen(t, zeile, k))

# 5) Umbenennen eines Schlüssels ändert die Verweise mit; doppelte Schlüssel werden abgewiesen
pid = next(z["id"] for z in db.zeilen("profile") if z["profil_id"] == "RR 42,4x2,0")
assert db.verweise("profile", pid) == 2
db.aendern("profile", pid, "profil_id", "RR 42,4x2")
assert db.einstellung("stammdaten_herkunft") == "eigene Werte"   # Startseite: keine Beispielwerte mehr
assert sum(1 for z in db.zeilen("preise") if z["profil_id"] == "RR 42,4x2") == 2
assert not any(z["profil_id"] == "RR 42,4x2,0" for z in db.zeilen("preise"))
try:
    db.aendern("profile", pid, "profil_id", "QR 40x40x3")
    raise AssertionError("doppelte Profil-ID angenommen")
except ValueError as e:
    assert "gibt es schon" in str(e)
wid = next(z["id"] for z in db.zeilen("werkstoffe") if z["werkstoff_id"] == "1.4301")
db.aendern("werkstoffe", wid, "werkstoff_id", "1.4301-K240")
assert sum(1 for z in db.zeilen("schneiddaten") if z["werkstoff_id"] == "1.4301-K240") == 3
neu = db.neu("preise")
db.aendern("preise", neu, "profil_id", "QR 40x40x3")
try:
    db.aendern("preise", neu, "werkstoff_id", "S235-10219")
    raise AssertionError("doppelter Preis angenommen")
except ValueError:
    pass
db.loeschen("preise", [neu])

# 6) Stammdaten ersetzen setzt Tabellen und Einstellungen in einem Schritt
daten = beispieldaten()
daten["preise"] = daten["preise"][:3]
db.stammdaten_ersetzen(daten, {"zuschlag_fertigung": 0.2}, "Test")
assert db.einstellung("zuschlag_fertigung") == 0.2 and db.einstellung("stammdaten_herkunft") == "Test"
assert db.anzahl("preise") == 3 and db.anzahl("profile") == 5

# 7) Sicherung: vollständige Kopie, höchstens `behalten` Stück
for _ in range(4):
    s = db.sicherung(tmp / "sich", behalten=3)
assert len(list((tmp / "sich").glob("*.db"))) == 3
kopie = sqlite3.connect(s)
assert kopie.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == db.anzahl("profile")
kopie.close()
assert db.sicherung_heute(tmp / "sich") is None   # heute schon gesichert
db.schliessen()
db = Datenbank(tmp / "a" / "rohrlaser.db")      # wieder öffnen: Daten bleiben, keine Beispieldaten
assert db.einstellung("stammdaten_herkunft") == "Test"

# 8) Oberfläche: Bearbeiten über das Tabellenmodell speichert sofort, ungültige Eingaben werden abgewiesen
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db)
seite = next(s for s in fenster.seiten if s.t.name == "profile")
mod = seite.modell
r = next(i for i, z in enumerate(mod.daten) if z["profil_id"] == "QR 40x40x3")
c = next(i for i, (art, s) in enumerate(mod.spalten) if art == "feld" and s.name == "wand")
assert mod.setData(mod.index(r, c), "2,5")
assert next(z for z in db.zeilen("profile") if z["profil_id"] == "QR 40x40x3")["wand"] == 2.5
fl_spalte = [i for i, (art, _) in enumerate(mod.spalten) if art == "berechnet"][0]
assert mod.data(mod.index(r, fl_spalte)) == "375,0"   # 40² − 35² neu berechnet
assert not mod.setData(mod.index(r, c), "abc")
assert "keine Zahl" in fenster.statusBar().currentMessage()
assert mod.setData(mod.index(r, c), "25")         # Wandstärke 25 > halbe Abmessung: Feld erlaubt, Prüfung meldet
assert mod.roh(r, len(mod.spalten) - 1).startswith("FEHLER: Wandstärke")
assert mod.setData(mod.index(r, c), "3") and mod.roh(r, len(mod.spalten) - 1) == "OK"
n = len(mod.daten)
neu_r = mod.zeile_neu()
assert len(mod.daten) == n + 1 and mod.roh(neu_r, len(mod.spalten) - 1).startswith("FEHLER: Profil-ID fehlt")
mod.zeilen_loeschen([neu_r])
assert len(mod.daten) == n
# Sortieren nach Zahlen, leere zuletzt
seite.ansicht.sortByColumn(next(i for i, (a, s) in enumerate(mod.spalten) if a == "feld" and s.name == "b"),
                           Qt.AscendingOrder)
werte = [seite.filter.index(i, 3).data(Qt.UserRole) for i in range(seite.filter.rowCount())]
gefuellt = [w for w in werte if w is not None]
assert gefuellt == sorted(gefuellt) and werte[:len(gefuellt)] == gefuellt, werte
seite.suche.setText("RE ")
assert seite.filter.rowCount() == 2
fenster.einstellungen.felder["gewinn"].setValue(12.5)
fenster.einstellungen.felder["gewinn"].editingFinished.emit()
assert db.einstellung("gewinn") == 0.125
fenster.close()
db.schliessen()

# 9) Angebote: Nummern zählen hoch, Kopieren übernimmt Positionen, Löschen nimmt Positionen mit
import subprocess  # noqa: E402
from rohrlaser import rechnen, step  # noqa: E402
from rohrlaser.angebot import naechste_nummer  # noqa: E402
assert naechste_nummer("A-2026-0099") == "A-2026-0100" and naechste_nummer("A9") == "A10"
db = Datenbank(tmp / "b" / "rohrlaser.db")
for n in ("ruesten_abmessung", "pauschale_abmessung", "angebotsaufschlag", "programmierung_teil"):   # Vergleichswerte: ohne
    db.einstellung_setzen(n, 0)                                               # die Kosten aus Teil 14
a1 = db.angebot_neu()
a2 = db.angebot_neu()
n1, n2 = db.angebot(a1)["nummer"], db.angebot(a2)["nummer"]
assert n1 != n2 and db.einstellung("letzte_angebotsnummer") == n2
try:
    db.angebot_aendern(a2, "nummer", n1)
    raise AssertionError("doppelte Angebotsnummer nicht abgewiesen")
except ValueError:
    pass
db.position_neu(a1, dict(pos=10, artikel="X-1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000, stueck=7))
a3 = db.angebot_kopieren(a1)
assert [p["artikel"] for p in db.positionen(a3)] == ["X-1"] and db.angebot(a3)["kunde"] == db.angebot(a1)["kunde"]
db.angebot_loeschen(a3)
assert db.positionen(a3) == [] and db.angebot(a3) is None
assert {a["id"] for a in db.angebote("X-1")} == {a1}

# 10) STEP-Übernahme (vgl. tests/test_step_import.py): Werte, Gewinde-Vorschlag, Doppelimport, Profil anlegen
STEP_ORDNER = HIER / "step"
befehl = step.messprogramm(HIER.parent / "programm")
if befehl is None:
    print("HINWEIS: OpenCascade fehlt, STEP-Übernahme nicht geprüft")
else:
    messung = tmp / "messwerte.txt"
    subprocess.run(befehl + ["--ausgabe", str(messung), str(STEP_ORDNER)], check=False, capture_output=True)
    mw = sorted(step.lies_messwerte(messung), key=lambda m: m["datei"])
    k = db.kontext()
    pos = db.positionen(a1)
    erg = step.uebernehmen(mw, pos, k, db.zeilen("gewinde"), rechnen.maschine(db.angebot(a1), k), "S235-10219", 5)
    assert [p["pos"] for p in erg["positionen"]] == [20, 30, 40, 50, 60, 70, 80], erg["positionen"]
    t07 = erg["positionen"][-1]
    assert t07["gewinde_vorschlag"] == "4xM6" and t07["bohrungen"] == "4xØ5" and t07["gravur"] == 58.0, t07
    assert [t07[x] for x in ("klein_n", "klein_mm", "mittel_n", "mittel_mm", "gross_n", "gross_mm")] == [4, 62.8, 1, 60.0, 0, 0.0]
    assert "gewinde" not in t07     # geprüftes Gewinde trägt nur der Mensch ein
    t05 = [z for z in erg["protokoll"] if str(z[1]).startswith("T05")][0]
    assert "Profil fehlt" in t05[-1] and len(t05) == len(step.PROTOKOLL), t05
    assert step.vorpruefung(mw, pos, k) == (["RR 33,7x2,6"], 0)
    for p in erg["positionen"]:
        db.position_neu(a1, p)
    zweit = step.uebernehmen(mw, db.positionen(a1), k, db.zeilen("gewinde"), None)
    assert zweit["positionen"] == [] and all("übersprungen" in b for b in zweit["bericht"]), zweit["bericht"]
    neu = step.uebernehmen([m for m in mw if m["datei"].startswith("T05")], [], k, [], None, neue_profile=True)
    assert neu["profile"][0]["profil_id"] == "RR 33,7x2,6" and "neu in Stammdaten" in neu["bericht"][0]
    t05p = neu["positionen"][0]
    assert t05p["profil_id"] == "RR 33,7x2,6" and t05p["a_gerade"] == "ja" and abs(t05p["a_schnitt"] - 105.9) < 0.05
    assert "Konturgrenzen Vorgabe" not in neu["bericht"][0]   # T05 hat keine Innenkonturen

# 11) Angebotsfenster: Optimieren speichert das Ergebnis, Ändern macht es veraltet, Status und Summen stehen
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
assert fenster.anleitung_oeffnen() == HIER.parent / "anleitung" / "Bedienungsanleitung.pdf"   # Hilfe-Menü
seite = fenster.angebot_oeffnen(a1)
assert seite.stand_optimierung() == "noch nicht optimiert"
assert seite.optimieren()
e = db.angebot(a1)["ergebnis"]
assert e and e["stangen"] and seite.stand_optimierung() == "aktuell"
for s_ in e["stangen"]:
    assert s_["teile"][-1]["bis"] <= s_["stange"] - s_["greif"] + 1e-6, "Stange überbelegt"
eingeplant = sum(len(s_["teile"]) for s_ in e["stangen"])
nicht = sum(f_["anzahl"] for f_ in e["fehler"])
assert eingeplant + nicht == sum(p["stueck"] or 0 for p in db.positionen(a1)), (eingeplant, nicht)
pm = seite.pos_modell
assert pm.rowCount() == len(db.positionen(a1)) and pm.status[0] == "HINWEIS: Schneidweg fehlt", pm.status
assert pm.status[-1] == "HINWEIS: Gewinde-Vorschlag prüfen" and pm.status[1] == "OK", pm.status
c_stk = next(i for i, (art, f_) in enumerate(pm.spalten) if art == "feld" and f_.name == "stueck")
assert pm.setData(pm.index(0, c_stk), "8")
assert seite.stand_optimierung().startswith("VERALTET")
assert not pm.setData(pm.index(0, c_stk), "-3") and db.positionen(a1)[0]["stueck"] == 8
assert seite.optimieren() and seite.stand_optimierung() == "aktuell"
assert seite.kalk.rowCount() == len(db.positionen(a1)) and "Verkaufspreis" in seite.uebersicht.text()
seite.reiter.setCurrentIndex(3)
seite.bild.resize(1200, seite.bild.minimumHeight())
assert not seite.bild.grab().isNull() and len(seite.bild.muster) >= 1
seite.felder["stange"].setValue(6500)
seite.felder["stange"].editingFinished.emit()
assert db.angebot(a1)["stange"] == 6500 and seite.stand_optimierung().startswith("VERALTET")
# Beispielangebot mit Satz und Staffeln: Kopf und 5 Positionen, vorhandene Nummer wird ersetzt
import beispiel_angebot  # noqa: E402
a4 = beispiel_angebot.anlegen(db)
a5 = beispiel_angebot.anlegen(db)
fenster.angebot_oeffnen(a4)
fenster.angebot_oeffnen(a5)
assert len(db.positionen(a4)) == 5 and db.angebot(a4)["kunde"] == "Beispiel GmbH"
assert db.angebot(a4)["nummer"] != db.angebot(a5)["nummer"]
assert set(fenster.offen) == {a1, a4, a5}
fenster.angebot_schliessen(a5)
assert a5 not in fenster.offen

# 12) Schritt 3: Staffeln, Staffelpreise, PDFs und CSV-Export in die Ablage
from rohrlaser import ausgabe, staffeln  # noqa: E402
assert [(x["schluessel"], x["menge"]) for x in db.staffeln(a4)] == [("Rahmen", 2), ("Rahmen", 4), ("Rahmen", 8),
                                                                     ("10", 24), ("10", 50), ("10", 100)]
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
s4 = fenster.offen[a4]
assert [staffeln.pruefen(x, s4.positionen) for x in s4.stufen[:4]] == ["Satz mit 2 Positionen"] * 3 + ["Position"]
assert staffeln.pruefen(dict(schluessel="gibt es nicht", menge=3), s4.positionen).startswith("FEHLER")
assert staffeln.pruefen(dict(schluessel="10", menge=None), s4.positionen) == "FEHLER: Menge fehlt"
assert s4.optimieren()
sp = s4.staffelpreise_rechnen()
assert len(sp) == 6 and [z["einheit"] for z in sp] == ["Satz"] * 3 + ["Stück"] * 3
assert [z["preis_einheit"] for z in sp] == [159.19, 149.71, 138.36, 7.31, 6.71, 6.11], sp   # Referenzwerte
assert "aktuell" in s4.staffel_info.text()
st_mod = s4.staffel_modell
assert st_mod.setData(st_mod.index(5, 1), "200") and db.staffeln(a4)[5]["menge"] == 200
assert "VERALTET" in s4.staffel_info.text()
assert not st_mod.setData(st_mod.index(5, 1), "0")
ang = s4.angebot_daten()      # rechnet veraltete Staffelpreise neu
assert ang["staffeln"][-1]["menge"] == 200 and "aktuell" in s4.staffel_info.text()
assert abs(ang["netto"] - 1008.16) < 1e-9 and ang["mwst"] == 191.55, ang   # Referenzwerte
assert ang["zeilen"][0]["text"] == "Rundrohr Ø 42,4 x 2, L = 1250 mm, inkl. Material S235 EN10219"
assert [z["art"] for z in ang["zeilen"]] == ["teil", "teil", "satz", "satzteil", "satzteil", "teil"]
for aufruf, name in ((s4.angebot_pdf, "Angebot.pdf"), (s4.werkstatt_pdf, "Werkstattpapiere.pdf"),
                     (s4.kalkulation_pdf, "Kalkulation.pdf"), (s4.csv_export, "Kalkulation.csv")):
    datei = aufruf()
    assert datei and datei.parent == tmp / "Ablage" and datei.name.endswith(name) and datei.stat().st_size > 1000, datei
    if name.endswith(".pdf"):
        assert datei.read_bytes()[:5] == b"%PDF-"
import csv  # noqa: E402
with open(datei, encoding="utf-8-sig", newline="") as f_:
    csv_zeilen = list(csv.reader(f_, delimiter=";"))
assert csv_zeilen[1] == ["Angebotsnummer", db.angebot(a4)["nummer"]], csv_zeilen[:3]
assert any(z[:1] == ["Verkaufspreis"] for z in csv_zeilen), csv_zeilen
kopfzeile = next(i for i, z in enumerate(csv_zeilen) if z[:2] == ["Pos.", "Artikelnummer"])
assert len(csv_zeilen) - kopfzeile - 1 == 5 and csv_zeilen[kopfzeile + 1][:3] == ["10", "4711-001", "24"]
assert ausgabe.nummern_text([1, 2, 3, 7, 9, 10]) == "1–3, 7, 9–10"
assert ausgabe.dateiname(dict(nummer="A/1", kunde="X: Y"), "Angebot", True) == "A_1 X_ Y Angebot"
assert ausgabe.zahl_kurz(2.0) == "2" and ausgabe.zahl_kurz(42.4) == "42,4" and ausgabe.kaufm_runden(2.675) == 2.68
a6 = db.angebot_kopieren(a4)
assert len(db.staffeln(a6)) == 6
fenster.close()
db.schliessen()

# 13) Datendatei aus Schritt 2 (Schema 2, noch mit 'Aufträgen') wird beim Öffnen erweitert und umbenannt
import sqlite3  # noqa: E402
alt = tmp / "c" / "rohrlaser.db"
d_ = Datenbank(alt)
a_alt = d_.angebot_neu(dict(kunde="Altkunde"))
d_.position_neu(a_alt, dict(pos=10, artikel="ALT-1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=900,
                            stueck=3))
d_.einstellung_setzen("angebotsaufschlag", 35.0)
nr_alt = d_.angebot(a_alt)["nummer"]
d_.schliessen()
con = sqlite3.connect(alt)
con.execute("DROP TABLE staffeln")
con.execute("ALTER TABLE angebote DROP COLUMN staffelpreise")
con.execute("ALTER TABLE angebote DROP COLUMN fracht")
con.execute("ALTER TABLE maschinen DROP COLUMN max_kg_m")
con.execute("DROP INDEX angebote_nummer")
con.execute("DROP INDEX positionen_angebot")
con.execute("ALTER TABLE angebote RENAME TO auftraege")
for t_ in ("positionen", "step_protokoll"):
    con.execute(f"ALTER TABLE {t_} RENAME COLUMN angebot_id TO auftrag_id")
con.execute("CREATE UNIQUE INDEX auftraege_nummer ON auftraege (nummer)")
con.execute("CREATE INDEX positionen_auftrag ON positionen (auftrag_id, nr)")
con.execute("UPDATE einstellungen SET name='letzte_auftragsnummer' WHERE name='letzte_angebotsnummer'")
con.execute("UPDATE einstellungen SET name='auftragsaufschlag' WHERE name='angebotsaufschlag'")
con.execute("PRAGMA user_version=2")
con.commit()
con.close()
db = Datenbank(alt)
assert db.con.execute("PRAGMA user_version").fetchone()[0] == 6
tabellen_ = {r[0] for r in db.con.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'index')")}
assert "auftraege" not in tabellen_ and {"angebote", "angebote_nummer", "positionen_angebot"} <= tabellen_, tabellen_
assert db.angebot(a_alt)["kunde"] == "Altkunde" and [p_["artikel"] for p_ in db.positionen(a_alt)] == ["ALT-1"]
assert db.einstellung("angebotsaufschlag") == 35.0 and db.einstellung("letzte_angebotsnummer") == nr_alt
db.angebot_loeschen(a_alt)          # Fremdschlüssel zeigen nach dem Umbenennen auf 'angebote'
assert db.positionen(a_alt) == []
a7 = db.angebot_neu()
db.staffel_neu(a7, dict(schluessel="10", menge=5))
db.staffelpreise_speichern(a7, dict(zeilen=[], kennung="x", am=None))
assert db.angebot(a7)["staffelpreise"]["kennung"] == "x" and len(db.staffeln(a7)) == 1
db.angebot_aendern(a7, "fracht", 80.0)
assert db.angebot(a7)["fracht"] == 80.0 and "max_kg_m" in db.zeilen("maschinen")[0]
db.schliessen()

# 14) Maschinengrenzen (Hüllkreis, Metergewicht) und Kosten je Abmessung / Angebot, Fracht
from rohrlaser.stammdaten import huellkreis  # noqa: E402
assert huellkreis(dict(form="Rundrohr", a=42.4)) == 42.4
assert abs(huellkreis(dict(form="Quadratrohr", a=40)) - 56.5685) < 1e-3
assert abs(huellkreis(dict(form="Rechteckrohr", a=120, b=60)) - 134.164) < 1e-3
assert huellkreis(dict(form="Sonderprofil", a=50)) is None
db = Datenbank(tmp / "d" / "rohrlaser.db")
assert db.einstellung("ruesten_abmessung") == 15 and db.einstellung("pauschale_abmessung") == 22.5
assert db.einstellung("angebotsaufschlag") == 50
k, tab = db.kontext(), db.tabellen()
kopf = dict(maschine="RL-1", stange=6000)
pos = [dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000, stueck=6),
       dict(pos=20, artikel="B", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=4),
       dict(pos=30, artikel="C", profil_id="RE 120x60x4", werkstoff_id="S235-10219", laenge=800, stueck=5),
       dict(pos=40, artikel="D", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=700)]   # ohne Stückzahl
erg = rechnen.optimieren(kopf, pos, k)
assert not erg["fehler"] or all(f_["artikel"] == "D" for f_ in erg["fehler"])
null = dict(db.einstellungen(), ruesten_abmessung=0, pauschale_abmessung=0, angebotsaufschlag=0, programmierung_teil=0)
z0, s0 = rechnen.kalkulation(kopf, pos, erg, k, tab, null)
z1, s1 = rechnen.kalkulation(dict(kopf, fracht=120.0), pos, erg, k, tab, db.einstellungen())
satz = k.maschinen["RL-1"]["stundensatz"]
assert s1["abmessungen"] == 2 and s1["pauschalen"] == 45.0 and s1["angebotsaufschlag"] == 50 and s1["fracht"] == 120
assert db.einstellung("programmierung_teil") == 8.5 and s1["programmierung"] == 3 * 8.5   # D ohne Stückzahl zählt nicht
assert abs(s1["ruesten"] - s0["ruesten"] - 2 * 15 / 60 * satz) < 1e-9
gew = 1 + db.einstellung("gewinn")
fert = 1 + db.einstellung("zuschlag_fertigung")
# Verkaufspreis steigt um Rüsten je Abmessung (mit Zuschlag Fertigung und Gewinn) + Pauschalen + Aufschlag + Fracht
erwartet = s0["verkauf"] + 2 * 15 / 60 * satz * fert * gew + 45 + 50 + 120 + 3 * 8.5
assert abs(s1["verkauf"] - erwartet) < 1e-6, (s1["verkauf"], erwartet)
# Pauschale je Abmessung trägt nur deren Teile: QR 40x40x3 hat 10, RE 120x60x4 hat 5 Teile
# Programmierkosten 8,50 € je Position, umgelegt auf deren Stückzahl (A 6, C 5 Stück)
assert abs(z1[0]["pauschalen_teil"] - (22.5 / 10 + 170 / 15 + 8.5 / 6)) < 1e-9
assert abs(z1[2]["pauschalen_teil"] - (22.5 / 5 + 170 / 15 + 8.5 / 5)) < 1e-9
assert z1[3]["pauschalen_teil"] == 0 and z1[3]["preis_position"] == 0
# Grenzen der Maschine: RE 120x60x4 (Hüllkreis 134,2 mm, 10,9 kg/m) passt nicht mehr
db.aendern("maschinen", db.zeilen("maschinen")[0]["id"], "max_huellkreis", 130)
k = db.kontext()
w = rechnen.position_werte(pos[2], kopf, k, tab)
assert rechnen.status(pos[2], w, kopf, k) == "FEHLER: Hüllkreis größer als Maschine zulässt"
assert rechnen.status(pos[0], rechnen.position_werte(pos[0], kopf, k, tab), kopf, k) != "FEHLER: Hüllkreis größer als Maschine zulässt"
erg = rechnen.optimieren(kopf, pos, k)
assert [(f_["artikel"], f_["grund"]) for f_ in erg["fehler"] if f_["artikel"] == "C"] == \
    [("C", "Hüllkreis größer als Maschine zulässt")]
assert all(t["artikel"] != "C" for s_ in erg["stangen"] for t in s_["teile"])
db.aendern("maschinen", db.zeilen("maschinen")[0]["id"], "max_huellkreis", None)
db.aendern("maschinen", db.zeilen("maschinen")[0]["id"], "max_kg_m", 5)
k = db.kontext()
assert w["kg_m"] > 5 and rechnen.status(pos[2], w, kopf, k) == "FEHLER: Metergewicht über Maschinengrenze"
assert rechnen.position_werte(pos[0], kopf, k, tab)["kg_m"] > 3   # QR 40x40x3 ≈ 3,3 kg/m, liegt unter 5
assert "FEHLER" not in rechnen.status(pos[0], rechnen.position_werte(pos[0], kopf, k, tab), kopf, k)
erg = rechnen.optimieren(kopf, pos, k)
assert any(f_["grund"] == "Metergewicht über Maschinengrenze" for f_ in erg["fehler"])
# Staffel: jede Stufe trägt Aufschlag, Fracht, Programmierung und die Kosten ihrer Abmessungen voll
sp = staffeln.rechnen_alle(dict(kopf, fracht=120.0), pos, [dict(schluessel="10", menge=6)], k, tab, db.einstellungen())
sp0 = staffeln.rechnen_alle(kopf, pos, [dict(schluessel="10", menge=6)], k, tab, null)
assert abs(sp[0]["preis_einheit"] * 6 - sp0[0]["preis_einheit"] * 6 - (15 / 60 * satz * fert * gew + 22.5 + 8.5 + 50 + 120)) < 0.1
db.schliessen()
shutil.rmtree(tmp, ignore_errors=True)
print("OK: Programm")
