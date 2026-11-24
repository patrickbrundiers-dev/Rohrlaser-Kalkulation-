"""Angebots-Cache (Patrick 19.11.2026, „Angebotsbezogene Zwischenspeicherung“): dauermerker.py je Angebot.

Jedes Szenario vergleicht das Ergebnis mit einer vollständigen Neuberechnung ohne Cache (typgenau, repr):
- Ablage typgenau (Tupel, Zahlen-Schlüssel, -0.0, nan), unpassende Werte werden nicht gemerkt,
- neues Angebot: eigene Datei Angebote/A<id>.db mit Kopf (Angebot, Nummer, Version, Schema),
- erneut öffnen / nach Neustart: Kalkulation aus dem Cache, gleich der Neuberechnung,
- ein bzw. mehrere Bauteile ändern: nur deren Schnittzeiten neu, die übrigen aus dem Cache,
- Materialpreis ändern: Kalkulation neu, Schnittzeiten aus dem Cache (lesen keine Preise),
- Maschinenparameter und Geometrie ändern: betroffene Rechnungen neu,
- Cache-Datei beschädigen, löschen, unlesbarer Eintrag; Ordner weg („Netz unterbrochen“): rechnet ohne,
- mehrere Programme gleichzeitig (Prozesse schreiben in dieselbe Datei),
- Programm während des Schreibens beendet: Datei danach in Ordnung,
- Softwareupdate (andere Programmversion): alte Einträge gelten nicht, Aufräumen entfernt sie,
- Verwaltung: Übersicht, Prüfen und reparieren, Löschen, Exportieren, Aufräumen (gelöschtes Angebot),
  Kennzahlen, Fenster Hauptadmin → Angebots-Cache, Diagnose-Bericht,
- Teilen über den gemeinsamen Ordner: ein zweiter Platz übernimmt die Ergebnisse (gleich), nichts aus anderer
  Version oder beschädigter Kopie, Aufräumen nur der eigenen Kopien; laufender Abgleich (allgemeine Ergebnisse
  inklusive), keine erneute Übernahme nach Neustart, Vorwärmen beim Start, Ablage beim Beenden.
Aufruf: python tests/test_angebots_cache.py
"""
import copy
import json
import math
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_regression_ergebnisse import KONTUR_ANGEBOTE, kontur_rechnen, merker_leeren  # noqa: E402

from rohrlaser import dauermerker, diagnose, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


TMP = Path(tempfile.mkdtemp())
CACHE = TMP / dauermerker.ORDNER

# ------------------------------------------------------------------ Ablage typgenau
import decimal  # noqa: E402
proben = [(1, 2.5, None), {1: "a", (2, 3): [True, -0.0]}, [float("inf"), -0.0, "x\x00y"], {"\x00t": 1}, (), {},
          {"menge": decimal.Decimal("1.50")}, {"\x00m": "x"}]
for w in proben:
    a, d = dauermerker._packen(w)
    zurueck = dauermerker._auspacken(a, d)
    assert repr(zurueck) == repr(w) and type(zurueck) is type(w), (w, zurueck)
nan = dauermerker._auspacken(*dauermerker._packen([float("nan")]))
assert math.isnan(nan[0])
for schlecht in ({1, 2}, object(), [1, {2: {3}}]):
    try:
        dauermerker.kodieren(schlecht)
        raise AssertionError(f"nicht genau ablegbar und trotzdem kodiert: {schlecht!r}")
    except dauermerker.NichtAblegbar:
        pass
gross = dauermerker._packen(["x" * 5000])
assert gross[0] == 1 and isinstance(gross[1], bytes) and len(gross[1]) < 500, "große Werte nicht komprimiert"
ok("Ablage typgenau (Tupel, Zahlen-Schlüssel, Decimal, -0.0, inf/nan), Mengen/Objekte nicht gemerkt, große Werte komprimiert")


# ------------------------------------------------------------------ Hilfen
def kalk(db, aid, k=None, tab=None):
    kopf, pos = db.angebot(aid), db.positionen(aid)
    k, tab = k or db.kontext(), tab or db.tabellen()
    e = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    return repr(rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e))


def voll(db, aid, k=None, tab=None):
    """Vollständige Neuberechnung ohne jeden Merker."""
    alt = dauermerker.ordner()
    dauermerker.einrichten(None)
    merker_leeren()
    try:
        return kalk(db, aid, k, tab)
    finally:
        dauermerker.einrichten(alt)
        merker_leeren()


def neustart():
    """Wie ein Programmneustart: Merker im Speicher leer, Cache-Dateien bleiben."""
    dauermerker.einrichten(CACHE)
    merker_leeren()
    dauermerker.zaehler_zuruecksetzen()


def bereich(name):
    return dauermerker.stand()["bereiche"].get(name, dict(treffer=0, neu=0))


gerechnet = []
_orig_sz = rechnen._schneidzeit_teile_rechnen


def _zaehlend(p, *a, **kw):
    gerechnet.append(p.get("pos"))
    return _orig_sz(p, *a, **kw)


rechnen._schneidzeit_teile_rechnen = _zaehlend


def schnittzeiten(db, aid, k=None, tab=None):
    """Schnittzeiten aller Positionen wie die Positionstabelle (im Merker-Block), Liste der neu gerechneten."""
    kopf, pos = db.angebot(aid), db.positionen(aid)
    k, tab = k or db.kontext(), tab or db.tabellen()
    gerechnet.clear()
    with rechnen.merker():
        werte = [repr(rechnen._schneidzeit_teile(p, kopf, rechnen._n(k.profile[p["profil_id"]]["wand"]), tab, k))
                 for p in pos]
    return werte, sorted(gerechnet)


# ------------------------------------------------------------------ neues Angebot
dauermerker.einrichten(CACHE)
db = Datenbank(TMP / "cache.db")
kontur_rechnen(KONTUR_ANGEBOTE[2], db)          # REG-K2: zwei Positionen auf LT7, Gehrungen
kontur_rechnen(KONTUR_ANGEBOTE[0], db)          # REG-K1: zwei Positionen auf T11
aid, aid2 = [r[0] for r in db.con.execute("SELECT id FROM angebote ORDER BY id")]
merker_leeren()
erst = kalk(db, aid)
sz_erst, neu = schnittzeiten(db, aid)
dauermerker.angebot_benutzt(aid, db.angebot(aid)["nummer"])
assert dauermerker.leeren()
datei = CACHE / dauermerker.ANGEBOTE / f"A{aid}.db"
assert datei.exists(), "keine eigene Datei je Angebot"
ueb = {e["angebot_id"]: e for e in dauermerker.uebersicht()}
e = ueb[aid]
assert e["nummer"] == db.angebot(aid)["nummer"] and e["programm"] == rechnen.__dict__.get("VERSION", e["programm"])
assert e["schema"] == str(dauermerker.SCHEMA) and "Kalkulation" in e["bereiche"], e
assert erst == voll(db, aid)
ok(f"Neues Angebot: eigene Datei {datei.name} mit Nummer, Version, Schema und Bereichen {sorted(e['bereiche'])}")

# ------------------------------------------------------------------ erneut öffnen / Neustart
neustart()
assert kalk(db, aid) == erst and bereich("Kalkulation")["treffer"] == 1 and bereich("Kalkulation")["neu"] == 0
sz, neu = schnittzeiten(db, aid)
assert sz == sz_erst and neu == [], neu
ok("Nach Neustart: Kalkulation und Schnittzeiten aus dem Cache, gleich der Neuberechnung")

# ------------------------------------------------------------------ ein Bauteil, mehrere Bauteile ändern
pos = db.positionen(aid)
db.position_aendern(pos[1]["id"], "laenge", 400)
neustart()
sz, neu = schnittzeiten(db, aid)
assert neu == [pos[1]["pos"]], f"nicht nur das geänderte Bauteil neu gerechnet: {neu}"
assert sz[0] == sz_erst[0] and sz[1] != sz_erst[1]
k1 = kalk(db, aid)
assert k1 == voll(db, aid) and k1 != erst
ok("Ein Bauteil geändert: nur dessen Schnittzeit neu, die anderen aus dem Cache; Kalkulation gleich der Neuberechnung")
for p in pos:
    db.position_aendern(p["id"], "stueck", int(p["stueck"]) + 3)
neustart()
sz2, neu = schnittzeiten(db, aid)
assert sz2 == sz, "Stückzahl ändert die Schnittzeit je Teil nicht"     # Stück steht in der Position: Schlüssel neu
assert kalk(db, aid) == voll(db, aid)
ok(f"Mehrere Bauteile geändert: {len(neu)} Schnittzeit(en) neu, Ergebnis gleich der Neuberechnung")

# ------------------------------------------------------------------ Materialpreis ändern
neustart()
schnittzeiten(db, aid)
k_alt, tab_alt = db.kontext(), db.tabellen()
k_neu = copy.deepcopy(k_alt)
for z in k_neu.werkstoffe.values():
    if z.get("tonnenpreis") is not None:
        z["tonnenpreis"] = float(z["tonnenpreis"]) * 1.2
tab_neu = copy.deepcopy(tab_alt)
for z in tab_neu["preise"]:
    z["preis"] = float(z["preis"] or 0) + 0.35
vorher = kalk(db, aid, k_alt, tab_alt)
merker_leeren()
dauermerker.zaehler_zuruecksetzen()
sz3, neu = schnittzeiten(db, aid, k_neu, tab_neu)
assert neu == [] and sz3 == schnittzeiten(db, aid, k_alt, tab_alt)[0], f"Preisänderung rechnet Schnittzeiten neu: {neu}"
nachher = kalk(db, aid, k_neu, tab_neu)
assert bereich("Kalkulation")["neu"] == 1 and nachher != vorher, "Preisänderung: Kalkulation nicht neu gerechnet"
assert nachher == voll(db, aid, k_neu, tab_neu)
ok("Materialpreis geändert: Kalkulation neu (anderer Preis), Schnittzeiten aus dem Cache, gleich der Neuberechnung")

# Kopffelder ohne Einfluss auf die Schnittzeit (rechnen.KOPF_OHNE_SCHNITTZEIT): mit anderen Werten gleiche Zeit
kopf_x = dict(db.angebot(aid), **{n: "anders" for n in rechnen.KOPF_OHNE_SCHNITTZEIT})
kopf_x["ergebnis"] = {"stangen": []}
from rohrlaser import teilen as _teilen  # noqa: E402
tab_x = dict(tab_alt, einstellungen=dict(tab_alt["einstellungen"], **{n: "anderer PC" for n in _teilen.LOKAL}))
assert rechnen.stamm_pruefsumme(k_alt, tab_x, True) == rechnen.stamm_pruefsumme(k_alt, tab_alt, True)
for p in db.positionen(aid):
    w = rechnen._n(k_alt.profile[p["profil_id"]]["wand"])
    assert repr(_orig_sz(p, db.angebot(aid), w, tab_alt, k_alt)) == repr(_orig_sz(p, kopf_x, w, tab_alt, k_alt))
    p_x = dict(p, **{n: 99999 for n in rechnen.POS_OHNE_SCHNITTZEIT})       # andere Datenbank-Nummern (anderer PC)
    assert repr(_orig_sz(p, db.angebot(aid), w, tab_alt, k_alt)) == repr(_orig_sz(p_x, kopf_x, w, tab_x, k_alt))
ok("Kopffelder wie Optimierergebnis, Stand, Verkaufspreis, Datenbank-Nummern und Einstellungen nur dieses PCs "
   "ändern die Schnittzeit nicht (darum nicht im Schlüssel)")

# ------------------------------------------------------------------ Maschinenparameter, Geometrie
k_m = copy.deepcopy(k_alt)
for m in k_m.maschinen.values():
    for f, v in list(m.items()):
        if f.startswith("vorschub") or f in ("beschleunigung", "eilgang"):
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v:
                m[f] = v * 0.9
m_vorher = kalk(db, aid, k_alt, tab_alt)
neustart()
sz_m, neu = schnittzeiten(db, aid, k_m, tab_alt)
assert len(neu) == len(pos), "Maschinenparameter geändert: Schnittzeiten nicht neu gerechnet"
assert kalk(db, aid, k_m, tab_alt) == voll(db, aid, k_m, tab_alt)
t = json.loads(db.positionen(aid)[0]["technik"])
t["konturen"] = t["konturen"][:-1]
db.position_aendern(pos[0]["id"], "technik", json.dumps(t))
neustart()
sz_g, neu = schnittzeiten(db, aid)
assert neu == [pos[0]["pos"]], neu
assert kalk(db, aid) == voll(db, aid) != m_vorher
ok("Maschinenparameter geändert: alle Schnittzeiten neu; Kontur entfernt: nur dieses Bauteil neu; gleich der "
   "Neuberechnung")

# ------------------------------------------------------------------ beschädigen, löschen, unlesbar, Ordner weg
stand_jetzt = kalk(db, aid)
dauermerker.leeren()
dauermerker.einrichten(None)
for n in ("", "-wal", "-shm"):
    p = datei.with_name(datei.name + n)
    if p.exists():
        p.unlink()
datei.write_bytes(b"kein SQLite " * 500)
neustart()
assert kalk(db, aid) == stand_jetzt
assert dauermerker.leeren() and dauermerker.pruefen(datei)[0]["ok"]
ok("Beschädigte Cache-Datei: ersetzt, neu gerechnet, gleiches Ergebnis")
dauermerker.loeschen(aid)
assert not datei.exists()
neustart()
assert kalk(db, aid) == stand_jetzt and bereich("Kalkulation")["neu"] == 1
dauermerker.leeren()
ok("Cache-Datei gelöscht: neu gerechnet und wieder abgelegt")
import sqlite3  # noqa: E402
con = sqlite3.connect(datei)
con.execute("UPDATE merker SET art=1, wert=? WHERE bereich='Kalkulation'", (b"kaputt",))
con.commit()
con.close()
neustart()
assert kalk(db, aid) == stand_jetzt and bereich("Kalkulation")["neu"] == 1
ok("Unlesbarer Eintrag: gelöscht und neu gerechnet")
weg = TMP / "netz"
dauermerker.einrichten(weg / dauermerker.ORDNER)
merker_leeren()
kalk(db, aid)
dauermerker.leeren()
import shutil  # noqa: E402
dauermerker._schliessen()
shutil.rmtree(weg)
weg.write_text("Laufwerk weg")                  # Ordner verschwunden, an seiner Stelle nichts Beschreibbares
merker_leeren()
assert kalk(db, aid) == stand_jetzt
dauermerker.leeren()
from rohrlaser import protokoll  # noqa: E402
assert any("dauermerker" in str(k[0]) for k in protokoll._warnungen), protokoll._warnungen
ok("Cache-Ordner verschwunden (Netz unterbrochen): Warnung im Protokoll, gerechnet wird ohne, gleiches Ergebnis")
neustart()

# ------------------------------------------------------------------ mehrere Programme, Abbruch beim Schreiben
SKRIPT = """
import sys, os
sys.path.insert(0, sys.argv[1])
from rohrlaser import dauermerker
dauermerker.einrichten(sys.argv[2])
nr = int(sys.argv[3])
for i in range(300):
    dauermerker.ablegen("Probe", dauermerker.schluessel(i % 50), {"i": i % 50, "w": [1.5] * 20}, angebot=7)
if sys.argv[4] == "abbruch":
    os._exit(0)                   # mitten im Schreiben beendet
assert dauermerker.leeren()
for i in range(50):
    assert dauermerker.holen("Probe", dauermerker.schluessel(i), 7) == {"i": i, "w": [1.5] * 20}
print("fertig", nr)
"""
s = TMP / "mehrere.py"
s.write_text(SKRIPT)
prog = str(HIER.parent / "programm")
ps = [subprocess.Popen([sys.executable, str(s), prog, str(CACHE), str(n), "normal"], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True) for n in range(4)]
for p in ps:
    out, err = p.communicate(timeout=120)
    assert p.returncode == 0 and "fertig" in out, err
ok("Vier Programme schreiben gleichzeitig in dieselbe Angebotsdatei: keine Fehler, alle Werte lesbar")
for n in range(3):
    r = subprocess.run([sys.executable, str(s), prog, str(CACHE), str(n), "abbruch"], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
erg = dauermerker.pruefen(CACHE / dauermerker.ANGEBOTE / "A7.db")[0]
assert erg["ok"] and erg["unlesbar"] == 0, erg
ok("Programm während des Schreibens beendet: Datei danach in Ordnung (Prüfung), Einträge lesbar")

# ------------------------------------------------------------------ Softwareupdate
neustart()
kalk(db, aid)
dauermerker.leeren()
alt_version = dauermerker.VERSION
dauermerker.VERSION = "9.9.999"
try:
    neustart()
    assert kalk(db, aid) == stand_jetzt and bereich("Kalkulation")["neu"] == 1, "alte Version benutzt"
    dauermerker.leeren()
    vorher_n = sum(e["veraltet"] for e in dauermerker.uebersicht())
    weg = dauermerker.aufraeumen({aid, aid2, 7})
    assert vorher_n > 0 and weg["eintraege"] >= vorher_n - 0 and \
        sum(e["veraltet"] for e in dauermerker.uebersicht()) == 0, (vorher_n, weg)
finally:
    dauermerker.VERSION = alt_version
neustart()
ok(f"Softwareupdate: Einträge der alten Version gelten nicht (neu gerechnet), Aufräumen entfernt {vorher_n}")

# ------------------------------------------------------------------ Prüfrechnungen ohne Cache
neustart()
kalk(db, aid)
dauermerker.zaehler_zuruecksetzen()
merker_leeren()
with dauermerker.ohne():
    assert kalk(db, aid) == stand_jetzt
assert bereich("Kalkulation")["treffer"] == 0, "Prüfrechnung (Prüf-/Referenzangebote) nahm den Cache"
ok("Prüfrechnungen (dauermerker.ohne, Prüf- und Referenzangebote) rechnen ohne Cache")

# ------------------------------------------------------------------ Größe je Bereich begrenzt
dauermerker.BEREICH_HOECHSTENS["Probe groß"] = 3
for i in range(10):
    dauermerker.ablegen("Probe groß", dauermerker.schluessel("g", i), ["x" * 3000, i], angebot=aid)
    dauermerker.leeren()
n_gross = next(e for e in dauermerker.uebersicht() if e["angebot_id"] == aid)["bereiche"]["Probe groß"]
assert n_gross == 3 and dauermerker.holen("Probe groß", dauermerker.schluessel("g", 9), aid)[1] == 9, n_gross
del dauermerker.BEREICH_HOECHSTENS["Probe groß"]
ok("Große Bereiche (Kalkulation) je Angebot begrenzt: nur die neuesten bleiben")

# ------------------------------------------------------------------ Verwaltung
kalk(db, aid2)
dauermerker.angebot_benutzt(aid2, "REG-K1")
dauermerker.leeren()
zip_pfad = dauermerker.exportieren(TMP / "export.zip")
with zipfile.ZipFile(zip_pfad) as z:
    namen = z.namelist()
assert "uebersicht.json" in namen and f"{dauermerker.ANGEBOTE}/A{aid2}.db" in namen, namen
weg = dauermerker.aufraeumen({aid})               # aid2 und 7 „gelöscht“
assert weg["dateien"] == 2 and not (CACHE / dauermerker.ANGEBOTE / f"A{aid2}.db").exists(), weg
assert (CACHE / dauermerker.ANGEBOTE / f"A{aid}.db").exists()
alt = dauermerker.uebersicht()
for e in alt:
    if e["angebot_id"] == aid:
        con = sqlite3.connect(e["pfad"])
        con.execute("UPDATE kopf SET wert='1' WHERE name='benutzt'")
        con.commit()
        con.close()
dauermerker._schliessen()
assert dauermerker.aufraeumen({aid})["dateien"] == 1, "lange unbenutzte Angebotsdatei nicht entfernt"
ok("Verwaltung: Export (ZIP mit Übersicht), Aufräumen entfernt gelöschte und lange unbenutzte Angebote")

neustart()
kalk(db, aid)
kalk(db, aid)
merker_leeren()
kalk(db, aid)
k = dauermerker.kennzahlen()
assert k["gesamt"] >= 2 and k["treffer"] >= 1 and k["dateien"] >= 1 and k["groesse"] > 0, k
assert "Angebots-Cache" in diagnose.bericht()
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser import cache_fenster  # noqa: E402


class _F:
    def __init__(self):
        self.db, self.offen = db, {}


fenster = cache_fenster.CacheFenster(None)
fenster.f = _F()
fenster.aktualisieren()
assert fenster.tabelle.rowCount() >= 1 and "Cache-Trefferquote" in fenster.kennzahlen.toPlainText()
erg = fenster.pruefen()
assert all(e["ok"] for e in erg), erg
fenster.tabelle.selectRow(next(i for i, e in enumerate(fenster.zeilen) if e["angebot_id"] == aid))
assert fenster.markierte() == [aid]
assert fenster.neu_aufbauen() == 0 and not (CACHE / dauermerker.ANGEBOTE / f"A{aid}.db").exists()
assert fenster.exportieren(TMP / "e2.zip").exists()
fenster.aufraeumen()
ok("Kennzahlen, Diagnose-Bericht und Fenster Hauptadmin → Angebots-Cache (Prüfen, Neu aufbauen, Export, Aufräumen)")

# ------------------------------------------------------------------ Teilen über den gemeinsamen Ordner
# Zwei Plätze (eigene Cache-Ordner PA/PB) teilen fertige Ergebnisse über GEM/Rechenmerker (Dateiname <uid>.<Kürzel>.db).
GEM = TMP / "gemeinsam" / dauermerker.TEILEN_ORDNER
assert dauermerker.teilen_ablegen(aid, "x", GEM, "PA") is None and not GEM.parent.exists(), \
    "fehlender gemeinsamer Ordner (Netz weg) angelegt"
GEM.parent.mkdir()
uid = db.con.execute("SELECT uid FROM angebote WHERE id=?", (aid,)).fetchone()[0]
assert uid, "Angebot ohne feste Kennung"
neustart()
erst = kalk(db, aid)
sz_erst_aktuell, _ = schnittzeiten(db, aid)
assert dauermerker.teilen_ablegen(aid, uid, GEM, "PA") > 0 and (GEM / f"{uid}.PA.db").exists()
assert dauermerker.teilen_ablegen(aid, uid, GEM, "PA") is None, "unveränderter Cache erneut abgelegt"
assert dauermerker.teilen_holen(aid, uid, GEM, "PA") == 0, "eigene Kopie wieder übernommen"
CACHE_B = TMP / "platz_b" / dauermerker.ORDNER
dauermerker.einrichten(CACHE_B)
merker_leeren()
dauermerker.zaehler_zuruecksetzen()
(GEM / f"{uid}.PX.db").write_bytes(b"kaputt" * 100)          # beschädigte Kopie eines dritten Platzes
alt_version = dauermerker.VERSION
dauermerker.VERSION = "0.0.0-anders"                          # andere Programmversion übernimmt nichts
assert dauermerker.teilen_holen(aid, uid, GEM, "PB") == 0
dauermerker.VERSION = alt_version
dauermerker._geteilt.clear()
n = dauermerker.teilen_holen(aid, uid, GEM, "PB")
assert n > 0 and dauermerker.kennzahlen()["von_kollegen"] == n, n
assert dauermerker.teilen_holen(aid, uid, GEM, "PB") == 0, "unveränderte Kopie erneut gelesen"
assert kalk(db, aid) == erst == voll(db, aid)
assert bereich("Kalkulation")["treffer"] == 1 and bereich("Kalkulation")["neu"] == 0, bereich("Kalkulation")
assert dauermerker.teilen_aufraeumen(GEM, set(), "PB") == 0 and (GEM / f"{uid}.PA.db").exists()
assert dauermerker.teilen_aufraeumen(GEM, {uid}, "PA") == 0
assert dauermerker.teilen_aufraeumen(GEM, set(), "PA") == 1 and not (GEM / f"{uid}.PA.db").exists()
assert (GEM / f"{uid}.PX.db").exists(), "fremde Kopie aufgeräumt"
# Anbindung im Hauptfenster: Schließen legt ab, Öffnen holt (Kürzel + gemeinsamer Ordner eingetragen), sonst nichts
from rohrlaser.fenster import Hauptfenster  # noqa: E402


class _Platz:
    _cache_geteilt, _cache_uid = Hauptfenster._cache_geteilt, Hauptfenster._cache_uid
    _cache_von_kollegen, _cache_fuer_kollegen = Hauptfenster._cache_von_kollegen, Hauptfenster._cache_fuer_kollegen
    _cache_abgleich, _cache_beim_beenden = Hauptfenster._cache_abgleich, Hauptfenster._cache_beim_beenden
    CACHE_HOLEN_WARTEN_S = Hauptfenster.CACHE_HOLEN_WARTEN_S

    def __init__(self, db):
        self.db, self.offen = db, {}


platz = _Platz(db)
assert platz._cache_geteilt() is None and platz._cache_fuer_kollegen(aid) is None, "ohne Teilen eingerichtet geteilt"
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("teilen_ordner", str(GEM.parent))
assert platz._cache_geteilt() == (GEM, "PB")
platz._cache_fuer_kollegen(aid).join(10)
assert (GEM / f"{uid}.PB.db").exists(), "Schließen hat nichts in den gemeinsamen Ordner gelegt"
dauermerker.einrichten(TMP / "platz_c" / dauermerker.ORDNER)
dauermerker._geteilt.clear()
platz._cache_von_kollegen(aid).join(10)
assert dauermerker.kennzahlen()["von_kollegen"] > 0
# Zweiter PC mit eigener Datenbank: dasselbe Angebot hat dort andere Nummern (Angebot, Positionen), gleiche Kennung
U2 = "kennung-zwei-pcs"
dauermerker.einrichten(TMP / "platz_f" / dauermerker.ORDNER)
db_f = Datenbank(TMP / "platz_f.db")
kontur_rechnen(KONTUR_ANGEBOTE[2], db_f)
aid_f = db_f.con.execute("SELECT MAX(id) FROM angebote").fetchone()[0]
db_f.con.execute("UPDATE angebote SET uid=? WHERE id=?", (U2, aid_f))
db_f.con.commit()
merker_leeren()
schnittzeiten(db_f, aid_f)
assert dauermerker.teilen_ablegen(aid_f, U2, GEM, "PF")
dauermerker.einrichten(TMP / "platz_e" / dauermerker.ORDNER)
db2 = Datenbank(TMP / "platz_e.db")
db2.angebot_neu(dict(nummer="Platzhalter", kunde="x"))                      # verschiebt die Nummern
kontur_rechnen(KONTUR_ANGEBOTE[2], db2)
aid_e = db2.con.execute("SELECT MAX(id) FROM angebote").fetchone()[0]
db2.con.execute("UPDATE angebote SET uid=?, angelegt=? WHERE id=?", (U2, db_f.angebot(aid_f)["angelegt"], aid_e))
db2.con.execute("UPDATE positionen SET id=id+500 WHERE angebot_id=?", (aid_e,))     # andere Positionsnummern
db2.con.commit()
assert aid_e != aid_f and {p["id"] for p in db2.positionen(aid_e)} != {p["id"] for p in db_f.positionen(aid_f)}
merker_leeren()
dauermerker._geteilt.clear()
dauermerker.zaehler_zuruecksetzen()
n_e = dauermerker.teilen_holen(aid_e, U2, GEM, "PE")
sz_e, neu_e = schnittzeiten(db2, aid_e)
merker_leeren()
alt_o = dauermerker.ordner()
dauermerker.einrichten(None)
sz_voll, _ = schnittzeiten(db2, aid_e)
dauermerker.einrichten(alt_o)
assert n_e > 0 and neu_e == [] and sz_e == sz_voll, (n_e, neu_e)
db2.schliessen()
db_f.schliessen()
for _p in GEM.glob(f"{U2}.*.db"):
    _p.unlink()
dauermerker.einrichten(TMP / "platz_c" / dauermerker.ORDNER)
ok(f"Zweiter PC mit eigener Datenbank (andere Angebots- und Positionsnummern): Schnittzeiten aller Positionen aus "
   f"der Kopie des Kollegen ({n_e} Einträge), gleich der Neuberechnung")

# Laufender Abgleich (jede Minute), allgemeine Ergebnisse, Merker über den Neustart, Vorwärmen beim Start
dauermerker._geteilt.clear()
assert dauermerker.teilen_holen(aid, uid, GEM, "PB") == 0, "nach Neustart dieselbe Kopie erneut übernommen"
platz.offen = {aid: None}
dauermerker.ablegen("Probe allgemein", dauermerker.schluessel("probe", 1), {"x": 1})
dauermerker.leeren()
platz._cache_abgleich().join(10)
assert (GEM / f"{dauermerker.ALLGEMEIN}.PB.db").exists(), "allgemeine Ergebnisse nicht geteilt"
assert dauermerker.kennzahlen()["abgleich"], "Zeit des letzten Abgleichs fehlt"
stand = dauermerker.teilen_stand(GEM)
assert set(stand) == {"PB", "PX"} and stand["PB"]["dateien"] == 2, stand
dauermerker.einrichten(TMP / "platz_d" / dauermerker.ORDNER)        # neuer PC, Programmstart
dauermerker._geteilt.clear()
dauermerker.zaehler_zuruecksetzen()
n = dauermerker.teilen_vorwaermen(GEM, "PD", {uid: aid})
assert n > 0 and dauermerker.holen("Probe allgemein", dauermerker.schluessel("probe", 1)) == {"x": 1}, n
merker_leeren()
_sz, _neu = schnittzeiten(db, aid)
assert _neu == [] and _sz == sz_erst_aktuell, ("Vorwärmen: erstes Öffnen rechnet die Schnittzeiten", _neu)
dauermerker.ablegen("Probe allgemein", dauermerker.schluessel("probe", 2), {"y": 2})
platz.db.einstellung_setzen("benutzer_kuerzel", "PD")
platz._cache_beim_beenden()
assert (GEM / f"{dauermerker.ALLGEMEIN}.PD.db").exists(), "beim Beenden nicht abgelegt"
db.einstellung_setzen("teilen_ordner", "")
db.einstellung_setzen("benutzer_kuerzel", "")
dauermerker.einrichten(CACHE)
ok(f"Teilen über den gemeinsamen Ordner: Platz B übernimmt {n} Einträge von Platz A, Kalkulation aus dem Cache und "
   "gleich der Neuberechnung; andere Version und beschädigte Kopie übernehmen nichts; Aufräumen nur eigene Kopien; "
   "laufender Abgleich mit allgemeinen Ergebnissen, Merker über den Neustart, Vorwärmen beim Start, Ablage beim Beenden")

rechnen._schneidzeit_teile_rechnen = _orig_sz
dauermerker.einrichten(None)
db.schliessen()
print("Angebots-Cache: alle Prüfungen bestanden.")
os._exit(0)
