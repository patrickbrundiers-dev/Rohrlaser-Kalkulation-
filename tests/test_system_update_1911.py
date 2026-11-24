"""Großes System-Update 19.11.2026 (Patrick): Tempo und Stabilität ohne andere Ergebnisse.

Geprüft wird ohne Bildschirm:
- Einstellungen gemerkt (datenbank._einst_texte): gleiche Werte wie aus der Datei, auch nach Ändern über diese
  Verbindung (einstellung_setzen, db.con direkt), nach verworfener Transaktion, nach Schreiben einer zweiten
  Verbindung (SQLite data_version); jeder Aufruf bekommt ein eigenes Objekt; viel weniger Anweisungen,
- Reiterwechsel ohne Änderung lädt Angebot und Angebotsliste nicht neu; nach jeder Änderung (Position, Stammdaten,
  Einstellung), nach Tageswechsel und nach ANZEIGE_HOECHSTENS_S wieder; das Angebot zeigt danach denselben Stand,
- Zusatzarbeiten-Erkennung (Sechskant/Senkung) gemerkt: gleiche Zahlen wie neu gerechnet,
- Rechenmerker über den Programmstart (dauermerker): Ablegen und Holen, Schlüssel mit Programmversion,
  beschädigte Datei wird ersetzt, nicht beschreibbarer Ordner schaltet ab (Protokoll, gerechnet wird trotzdem),
  Schneidfolge (dynamik.folge) und Endabfall (zeit_zusatz.ende_abfall) gleich wie ohne Merker, nach „Neustart“ aus
  der Datei; ein unpassender gemerkter Wert wird nicht benutzt,
- Lebenszeichen: Hauptdatei im gemeinsamen Ordner nur bei Änderung gelesen; fehlende Datei wird nicht angelegt,
- Anfragen-Seite: dieselbe Ablage für denselben Ordner (gelesene Akten gemerkt); der 30-s-Takt liest keine Datei
  mehr, wenn sich keine Akte geändert hat, und zeigt eine geänderte Akte sofort.
Aufruf: python tests/test_system_update_1911.py
"""
import datetime
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import (anfragen_akten as ak, dauermerker, db_verbindung, diagnose, dynamik, teilen,  # noqa: E402
                       zusatz_erkennung)
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())

# ------------------------------------------------------------------ Einstellungen gemerkt
db = Datenbank(tmp / "e.db")


def aus_datei(name):
    r = db.con.execute("SELECT wert FROM einstellungen WHERE name=?", (name,)).fetchone()
    return json.loads(r[0]) if r else None


db.einstellung_setzen("gewinn", 0.17)
assert db.einstellung("gewinn") == 0.17 == aus_datei("gewinn")
db.con.execute("UPDATE einstellungen SET wert=? WHERE name='gewinn'", (json.dumps(0.21),))
db.con.commit()
assert db.einstellung("gewinn") == 0.21, "Änderung über db.con direkt nicht gesehen"
db.con.beginnen()
db.con.execute("UPDATE einstellungen SET wert=? WHERE name='gewinn'", (json.dumps(0.33),))
assert db.einstellung("gewinn") == 0.33, "eigene offene Transaktion nicht gesehen"
db.con.rollback()
assert db.einstellung("gewinn") == 0.21 == aus_datei("gewinn"), "verworfene Transaktion noch gemerkt"
zweite = Datenbank(tmp / "e.db")
zweite.einstellung_setzen("gewinn", 0.44)
if not db_verbindung.ist_sqlite(db.con):    # PostgreSQL: fremde Änderungen gelten nach höchstens EINST_PRUEFEN_S
    time.sleep(db.EINST_PRUEFEN_S + 0.05)
assert db.einstellung("gewinn") == 0.44, "Schreiben einer anderen Verbindung nicht gesehen (data_version)"
zweite.con.close()
db.einstellung_setzen("teilen_mitarbeiter", {"MK": {"name": "Martin"}})
a1 = db.einstellung("teilen_mitarbeiter")
a1["MK"]["name"] = "verändert"
assert db.einstellung("teilen_mitarbeiter") == {"MK": {"name": "Martin"}}, "Aufrufer verändert den Merker"
assert db.einstellung("gibt_es_nicht") is None
assert db.einstellungen()["gewinn"] == 0.44
zaehler = [0]
alt = db_verbindung.zaehler
db_verbindung.zaehler = lambda d: zaehler.__setitem__(0, zaehler[0] + 1)
try:
    for _ in range(200):
        db.einstellung("gewinn")
        db.einstellung("benutzer_kuerzel")
finally:
    db_verbindung.zaehler = alt
assert zaehler[0] == 0, f"{zaehler[0]} Anweisungen für 400 gelesene Einstellungen"
ok(f"Einstellungen gemerkt: gleiche Werte nach jeder Änderung (direkt, Rollback, zweite Verbindung), eigene Objekte; "
   f"400 Abfragen → {zaehler[0]} Anweisungen (je Aufruf nur der Änderungszähler der Datei)")
db.con.close()

# ------------------------------------------------------------------ Reiterwechsel ohne Änderung
db = Datenbank(tmp / "r.db")
AngebotSeite.CHECK_SOFORT = False
f = Hauptfenster(db, tmp, stumm=True)
aid = db.angebot_neu(dict(kunde="Reiter", kundennr="K-9", maschine="T11", stange=6000))
for i in range(4):
    db.position_neu(aid, dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=500.0 + 90 * i,
                              stueck=3 + i, schneidweg=150.0))
s = f.angebot_oeffnen(aid)
app.processEvents()
geladen = [0]
orig = AngebotSeite._neu_laden


def zaehlend(self):
    geladen[0] += 1
    return orig(self)


AngebotSeite._neu_laden = zaehlend
try:
    vorher = repr(s._rechnung())
    for _ in range(3):
        f.reiter.setCurrentWidget(f.angebote)
        f.reiter.setCurrentWidget(s)
    assert geladen[0] == 0, f"{geladen[0]} × neu geladen ohne Änderung"
    assert repr(s._rechnung()) == vorher
    f.reiter.setCurrentWidget(f.angebote)
    db.position_aendern(db.positionen(aid)[0]["id"], "stueck", 9) if hasattr(db, "position_aendern") else \
        db.con.execute("UPDATE positionen SET stueck=9 WHERE id=?", (db.positionen(aid)[0]["id"],))
    db.con.commit()
    f.reiter.setCurrentWidget(s)
    assert geladen[0] == 1 and s.positionen[0]["stueck"] == 9, (geladen, s.positionen[0]["stueck"])
    f.reiter.setCurrentWidget(f.angebote)
    db.einstellung_setzen("gewinn", 0.31)
    f.reiter.setCurrentWidget(s)
    assert geladen[0] == 2, "Einstellung geändert: nicht neu geladen"
    f.reiter.setCurrentWidget(f.angebote)
    s._anzeige_merk = (s._anzeige_merk[0], s._anzeige_merk[1] - f.ANZEIGE_HOECHSTENS_S - 1)
    f.reiter.setCurrentWidget(s)
    assert geladen[0] == 3, "nach ANZEIGE_HOECHSTENS_S nicht neu geladen"
    f.reiter.setCurrentWidget(f.angebote)
    alt_merk = s._anzeige_merk
    s._anzeige_merk = ((alt_merk[0][:3] + (datetime.date.today() - datetime.timedelta(days=1),) + alt_merk[0][4:]),
                       alt_merk[1])
    f.reiter.setCurrentWidget(s)
    assert geladen[0] == 4, "nach Tageswechsel nicht neu geladen"
    st = diagnose.stand()["merker"]
    assert any(m["name"].endswith("Reiterwechsel ohne Neuladen") and m["treffer"] >= 3 for m in st), st
finally:
    AngebotSeite._neu_laden = orig
ok("Reiterwechsel ohne Änderung lädt nicht neu (gleiches Ergebnis); nach Position, Einstellung, 5 min und "
   "Tageswechsel wieder; Diagnose zählt die gesparten Neuladen")

# ------------------------------------------------------------------ Zusatzarbeiten-Erkennung gemerkt
konturen = [dict(art="Polygon", punkte=[[10 * __import__("math").cos(a / 3 * 3.14159265), 10 * __import__("math").sin(
    a / 3 * 3.14159265)] for a in range(6)], anzahl=2), dict(art="Senkung", anzahl=3), dict(art="Bohrung", d=8)]
p = dict(technik=json.dumps(dict(konturen=konturen)), bohrbild=None)
erwartet = zusatz_erkennung._geometrie(p["technik"], None)
assert zusatz_erkennung.geometrie(p) == erwartet == zusatz_erkennung.geometrie(dict(p))
assert erwartet[1] == 3
p2 = dict(p, bohrbild=json.dumps([dict(art="Senkung", anzahl=5)]))
assert zusatz_erkennung.geometrie(p2) == zusatz_erkennung._geometrie(p2["technik"], p2["bohrbild"]) == (erwartet[0], 5)
assert zusatz_erkennung.geometrie(dict(technik=None, bohrbild=None)) == (0, 0)
ok(f"Sechskant/Senkung je Inhalt gemerkt, gleiche Zahlen wie neu gerechnet {erwartet}")

# ------------------------------------------------------------------ Rechenmerker über den Programmstart
ordner = tmp / "dm"
dauermerker.einrichten(ordner)
s1 = dauermerker.schluessel("probe", [1.0, -0.0, None], {"b": 2, "a": 1})
assert s1 == dauermerker.schluessel("probe", [1.0, -0.0, None], {"a": 1, "b": 2})
assert s1 != dauermerker.schluessel("probe", [1.0, 0.0, None], {"a": 1, "b": 2}), "-0.0 und 0.0 gleich"
assert dauermerker.holen("t", s1) is None
dauermerker.ablegen("t", s1, [3, 2.5, 1])
assert dauermerker.holen("t", s1) == [3, 2.5, 1]
dauermerker.einrichten(ordner)          # „Neustart“
assert dauermerker.holen("t", s1) == [3, 2.5, 1]
dauermerker.einrichten(None)
(ordner / dauermerker.DATEI).write_bytes(b"kaputt" * 1000)
for n in ("-wal", "-shm"):
    (ordner / (dauermerker.DATEI + n)).unlink(missing_ok=True)
dauermerker.einrichten(ordner)
assert dauermerker.holen("t", s1) is None and dauermerker.stand()["aus"] is False
dauermerker.ablegen("t", s1, [1])
assert dauermerker.holen("t", s1) == [1]
ok("Rechenmerker: Ablegen/Holen, über den Neustart, Schlüssel nach Inhalt, beschädigte Datei ersetzt")

lagen = [dict(x=50.0 + (i * 37) % 900, eingabe=dict(seite=("oben", "vorne", "unten", "hinten")[i % 4]))
         for i in range(14)]
m = dict(eilgang_x=100.0, beschl_x=10.0, drehzahl=120.0, beschl_dreh=600.0)
dauermerker.einrichten(None)
dynamik._FOLGE_MERK.clear()
ohne = dynamik.folge(lagen, m, 1000.0)
dauermerker.einrichten(tmp / "dm2")
dynamik._FOLGE_MERK.clear()
mit = dynamik.folge(lagen, m, 1000.0)
dynamik._FOLGE_MERK.clear()
gerechnet = [0]
orig_f = dynamik._folge_rechnen


def zaehlend_f(*a, **kw):
    gerechnet[0] += 1
    return orig_f(*a, **kw)


dynamik._folge_rechnen = zaehlend_f
try:
    dauermerker.einrichten(tmp / "dm2")     # Neustart: In-Speicher-Merker leer, Datei bleibt
    nach = dynamik.folge(lagen, m, 1000.0)
    assert gerechnet[0] == 0, "nach dem Neustart neu gerechnet statt aus der Datei"
    assert ohne == mit == nach and [type(x) for x in nach] == [type(x) for x in ohne]
    # unpassender Wert in der Datei (z. B. fremde Version): wird nicht benutzt
    pkt = sorted((d["x"], dynamik.winkel_der_seite(d["eingabe"]["seite"])) for d in lagen)
    schl = dauermerker.schluessel("folge", pkt, json.dumps(m, sort_keys=True, default=str), 1000.0, None, None)
    dauermerker.ablegen("dynamik.folge", schl, [0, 0, 1])
    dynamik._FOLGE_MERK.clear()
    assert dynamik.folge(lagen, m, 1000.0) == ohne and gerechnet[0] == 1
    dm = next(x for x in diagnose.stand()["merker"] if x["name"].startswith("Über Neustart gemerkt"))
    assert dm["treffer"] >= 1 and dm["eintraege"] >= 1, dm
    assert "Über Neustart gemerkt" in diagnose.bericht()
finally:
    dynamik._folge_rechnen = orig_f
ok("Diagnose zeigt die Treffer des Merkers über den Neustart")
ok("Schneidfolge über den Neustart gemerkt: gleiche Folge wie ohne Merker, unpassender Wert wird neu gerechnet")

gesperrt = tmp / "gesperrt"
gesperrt.write_text("keine Ordner hier")          # Datei statt Ordner: Merker nicht nutzbar
dauermerker.einrichten(gesperrt / "unter")
dynamik._FOLGE_MERK.clear()
assert dynamik.folge(lagen, m, 1000.0) == ohne and dauermerker.stand()["aus"]
from rohrlaser import protokoll  # noqa: E402
assert any("dauermerker" in str(k[0]) for k in protokoll._warnungen), protokoll._warnungen
dauermerker.einrichten(None)
ok("Rechenmerker-Ordner nicht nutzbar: abgeschaltet, gerechnet wird wie ohne")

# ------------------------------------------------------------------ Lebenszeichen: Hauptdatei nur bei Änderung
haupt = tmp / "Rohrlaser_PB" / teilen.HAUPT
haupt.parent.mkdir()
con = sqlite3.connect(haupt)
con.execute("CREATE TABLE info (name TEXT, wert TEXT)")
con.execute("INSERT INTO info VALUES ('installation', ?)", (json.dumps("abc"),))
con.commit()
con.close()
geoeffnet = [0]
orig_c = sqlite3.connect


def zaehl_connect(*a, **kw):
    geoeffnet[0] += 1
    return orig_c(*a, **kw)


sqlite3.connect = zaehl_connect
try:
    assert teilen.info_lesen(haupt) == {"installation": "abc"}
    i = teilen.info_lesen(haupt.parent)
    i["installation"] = "verändert"
    assert teilen.info_lesen(haupt) == {"installation": "abc"} and geoeffnet[0] == 1, geoeffnet
    con = orig_c(haupt)
    con.execute("UPDATE info SET wert=? WHERE name='installation'", (json.dumps("neu-123"),))
    con.commit()
    con.close()
    st = haupt.stat()
    os.utime(haupt, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
    assert teilen.info_lesen(haupt) == {"installation": "neu-123"} and geoeffnet[0] == 2
    weg = tmp / "Rohrlaser_XY" / teilen.HAUPT
    weg.parent.mkdir()
    assert teilen.info_lesen(weg) == {} and not weg.exists(), "fehlende Hauptdatei als leere Datei angelegt"
finally:
    sqlite3.connect = orig_c
ok("Lebenszeichen: Hauptdatei nur bei Änderung geöffnet, Aufrufer verändert den Merker nicht, fehlende nicht angelegt")

# ------------------------------------------------------------------ Anfragen: Ablage gemerkt, Takt ohne Dateien
db.einstellung_setzen("benutzer_kuerzel", "PB")
q = tmp / "q"
q.mkdir()
(q / "a.step").write_text("ISO-10303-21;")
abl = ak.ablage(db)
assert ak.ablage(db) is abl
akten = [abl.anlegen(dict(quelle="ordner", absender=f"k{i}@x.example", betreff=f"Anfrage {i}", kurz="x",
                          eingang="2026-11-13T08:00:00"), [q / "a.step"], f"s{i}")[0] for i in range(12)]
seite = f.anfragen_seite
seite.neu_laden()
gelesen = [0]
orig_r = Path.read_text


def zaehl_lesen(self, *a, **kw):
    gelesen[0] += 1
    return orig_r(self, *a, **kw)


Path.read_text = zaehl_lesen
try:
    seite.neu_laden()
    assert gelesen[0] == 0, f"Takt ohne Änderung las {gelesen[0]} Dateien"
    n_vorher = len(next(a for a in seite.akten if a.nr == akten[3].nr).verlauf)
    anderer = ak.OrdnerAblage(ak.wurzel(db), "MK", "PC2")
    anderer.ereignis(anderer.lesen(akten[3].nr), ak.UEBERNOMMEN, neu="MK", generation=0)
    seite.neu_laden()
    assert 0 < gelesen[0] < 12, gelesen         # nur die geänderte Akte (Kopf, Verlauf), nicht alle 12
    assert len(next(a for a in seite.akten if a.nr == akten[3].nr).verlauf) == n_vorher + 1
finally:
    Path.read_text = orig_r
ok("Anfragen-Takt: ohne Änderung keine Datei gelesen, geänderte Akte (anderer Platz) sofort neu")

db.con.close()
print("Großes System-Update 19.11.2026: alle Prüfungen bestanden.")
os._exit(0)
