"""Werkstoff-Kategorien, Oberflächen und Schneiddaten je Kategorie und Schneidgas (N₂/O₂).

Aufruf: python tests/test_werkstoffe.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import ausgabe, rechnen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.stammdaten import TABELLE, beispiel_schneiddaten, kategorie_raten, pruefen  # noqa: E402

tmp = Path(tempfile.mkdtemp())

# 1) Neue Datenbank: Werkstoffe mit Kategorie, Oberflächen, Schneiddaten je Kategorie, alles ohne Prüffehler
db = Datenbank(tmp / "a" / "rohrlaser.db")
k, tab = db.kontext(), db.tabellen()
kat = {w["werkstoff_id"]: w["kategorie"] for w in db.zeilen("werkstoffe")}
assert len(kat) == 12 and set(kat.values()) == {"Stahl", "Edelstahl", "Aluminium"}, kat
assert kat["1.4404"] == "Edelstahl" and kat["AW6082-T6"] == "Aluminium" and kat["E355-10305"] == "Stahl"
assert [o["oberflaeche"] for o in db.zeilen("oberflaechen")] == ["roh", "gestrahlt", "K240", "K320", "gebeizt", "E6/EV1"]
for t in ("werkstoffe", "oberflaechen", "schneiddaten"):
    for z in db.zeilen(t):
        assert pruefen(TABELLE[t], z, k) == "OK", (t, z, pruefen(TABELLE[t], z, k))
assert all(z["werkstoff_id"] is None and z["gas"] in ("N₂", "O₂") for z in db.zeilen("schneiddaten"))
assert {z["maschinen_id"] for z in db.zeilen("schneiddaten")} == {"T03", "T11", "LT7"}

# Auswahl im Angebot nach Kategorie gruppiert, Oberflächen 'roh' und die für alle zuerst
gr = k.gruppiert("werkstoff")
assert [g for g, _ in gr] == ["Stahl", "Edelstahl", "Aluminium"], gr
assert gr[1][1] == ["1.4301", "1.4307", "1.4404", "1.4509", "1.4571"]
assert k.gruppiert("oberflaeche")[0] == ("alle Werkstoffe", ["roh", "gestrahlt"])
assert len(k.auswahl("werkstoff")) == 12 and "K240" in k.auswahl("oberflaeche")

# Prüfung der Schneiddaten: Werkstoff-ID oder Kategorie, eins von beiden; ohne Gas Warnung
z = dict(maschinen_id="LT7", wand_bis=2, vorschub_gross=100, gas="N₂")
assert pruefen(TABELLE["schneiddaten"], z, k).startswith("FEHLER: Werkstoff-ID oder Kategorie")
assert pruefen(TABELLE["schneiddaten"], dict(z, werkstoff_id="1.4301", kategorie="Edelstahl"), k).startswith("FEHLER")
assert pruefen(TABELLE["schneiddaten"], dict(z, kategorie="Kupfer"), k) == "FEHLER: Kategorie unbekannt"
assert pruefen(TABELLE["schneiddaten"], dict(z, kategorie="Stahl", gas=None), k) == "WARNUNG: Schneidgas fehlt"

# 2) Schneiddaten: N₂ solange es eine N₂-Zeile gibt, darüber O₂; Kategorie, wenn der Werkstoff keine eigene hat
sd = lambda m, w, s: rechnen.schneiddaten(m, w, s, tab, rechnen.kategorie(w, k))
assert (sd("LT7", "S235-10219", 3)["gas"], sd("LT7", "S235-10219", 3)["vorschub_gross"]) == ("N₂", 5000)
assert (sd("LT7", "S235-10219", 4)["gas"], sd("LT7", "S235-10219", 4.5)["gas"]) == ("N₂", "O₂")
assert sd("LT7", "E355-10305", 5)["vorschub_gross"] == 2600 and sd("LT7", "S355-10219", 10)["wand_bis"] == 10
assert sd("LT7", "S235-10219", 13) is None
assert (sd("LT7", "1.4404", 9)["gas"], sd("LT7", "1.4404", 11)) == ("N₂", None)       # Edelstahl nur N₂
assert (sd("LT7", "AW6060-T66", 6)["gas"], sd("LT7", "AW6082-T6", 8.5)) == ("N₂", None)
assert (sd("T03", "S235-10219", 3)["gas"], sd("T03", "S235-10219", 3)["vorschub_gross"]) == ("O₂", 3000)   # CO₂
assert sd("LT7", "S235-10219", 3)["einstechzeit"] < sd("LT7", "S235-10219", 5)["einstechzeit"]
# eigene Zeile des Werkstoffs geht vor, auch mit O₂; ohne passende Wandstärke gilt wieder die Kategorie
db.neu("schneiddaten", dict(maschinen_id="LT7", werkstoff_id="S235-10219", gas="O₂", wand_bis=3,
                            vorschub_gross=4000, einstechzeit=0.5))
tab = db.tabellen()
assert sd("LT7", "S235-10219", 2)["vorschub_gross"] == 4000 and sd("LT7", "S355-10219", 2)["vorschub_gross"] == 8000
assert sd("LT7", "S235-10219", 4)["kategorie"] == "Stahl"
# Werkstoff ohne Kategorie und ohne eigene Zeilen: keine Schneiddaten
db.neu("werkstoffe", dict(werkstoff_id="CuZn37", dichte=8.4, tonnenpreis=9000))
k = db.kontext()
assert sd("LT7", "CuZn37", 2) is None
assert pruefen(TABELLE["werkstoffe"], k.werkstoffe["CuZn37"], k) == "WARNUNG: Kategorie fehlt"
# Kalkulation zeigt Wandstärke-Stufe und Schneidgas
kopf = dict(maschine="LT7", stange=6000)
p0 = dict(pos=10, artikel="A", profil_id="RE 120x60x4", werkstoff_id="1.4301", laenge=1000, stueck=2, schneidweg=800,
          einstiche=2)
erg = rechnen.optimieren(kopf, [p0], k)
zk, _ = rechnen.kalkulation(kopf, [p0], erg, k, tab, db.einstellungen())
assert (zk[0]["wand_stufe"], zk[0]["gas"], zk[0]["vorschub_gross"]) == (4, "N₂", 2800), zk[0]
assert rechnen.position_werte(p0, kopf, k, tab)["gas"] == "N₂"

# 3) Oberfläche: eigene Stangen, Aufpreis je m, Text im Angebot, Prüfungen
pos = [dict(pos=10, artikel="roh", profil_id="RR 42,4x2,0", werkstoff_id="1.4301", laenge=1000, stueck=3),
       dict(pos=20, artikel="K240", profil_id="RR 42,4x2,0", werkstoff_id="1.4301", oberflaeche="K240", laenge=1000,
            stueck=3),
       dict(pos=30, artikel="leer", profil_id="RR 42,4x2,0", werkstoff_id="1.4301", oberflaeche="roh", laenge=1000,
            stueck=2)]
erg = rechnen.optimieren(kopf, pos, k)
assert not erg["fehler"]
gruppen = {rechnen.gruppe_der_stange(s): s for s in erg["stangen"]}
assert set(gruppen) == {("RR 42,4x2,0", "1.4301", "", 6000), ("RR 42,4x2,0", "1.4301", "K240", 6000)}, set(gruppen)
for s in erg["stangen"]:      # nie gemischt: auf einer K240-Stange nur K240-Teile
    assert {t["artikel"] == "K240" for t in s["teile"]} == {s["oberflaeche"] == "K240"}
sw = rechnen.stangen_werte(erg, kopf, pos, k, tab)
kosten = {s["oberflaeche"]: w["kosten"] for s, w in zip(erg["stangen"], sw)}
# Preise: RR 42,4x2,0 + 1.4301 = 62 € je 6-m-Stange, K240 dazu 2,20 €/m
assert abs(kosten[""] - 62.0) < 1e-9 and abs(kosten["K240"] - (62.0 + 2.20 * 6)) < 1e-9, kosten
zk, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, db.einstellungen())
assert abs(zk[1]["material_gruppe"] - kosten["K240"]) < 1e-9 and abs(zk[0]["anteil"] - 3 / 5) < 1e-9
# abweichender Materialpreis ersetzt Preis und Aufpreis
pos_ab = [dict(p, preis_m=20.0) if p["artikel"] == "K240" else p for p in pos]
sw_ab = rechnen.stangen_werte(erg, kopf, pos_ab, k, tab)
assert abs({s["oberflaeche"]: w["kosten"] for s, w in zip(erg["stangen"], sw_ab)}["K240"] - 120.0) < 1e-9
assert ausgabe.angebotstext(pos[1], k).endswith("\ninkl. Material 1.4301 EN10217-7\nOberfläche K240 geschliffen")
assert ausgabe.angebotstext(pos[2], k).endswith("inkl. Material 1.4301 EN10217-7")
st = lambda p: rechnen.status(p, rechnen.position_werte(p, kopf, k, tab), kopf, k)
assert st(dict(pos[1], oberflaeche="K999")) == "FEHLER: Oberfläche unbekannt"
assert st(dict(pos[1], werkstoff_id="S235-10219")) == "WARNUNG: Oberfläche K240 ist für Edelstahl"
assert "Oberfläche" not in st(dict(pos[1], oberflaeche="gestrahlt", werkstoff_id="S235-10219"))
assert [f["grund"] for f in rechnen.optimieren(kopf, [dict(pos[1], oberflaeche="K999")], k)["fehler"]] == \
    ["Oberfläche unbekannt"]
# Werkstattpapier und Nachkalkulation führen die Oberfläche beim Werkstoff
wst = ausgabe.werkstatt(kopf, pos, erg, k, tab)
assert sorted(m["werkstoff"] for m in wst["material"]) == ["1.4301", "1.4301 K240"]
from rohrlaser import nachkalkulation  # noqa: E402
assert sorted(g["schluessel"] for g in nachkalkulation.gruppen(erg, kopf, pos, k, tab)) == \
    ["RR 42,4x2,0|1.4301|6000", "RR 42,4x2,0|1.4301|6000|K240"]
# Staffelpreise veralten, wenn sich der Aufpreis einer Oberfläche ändert
from rohrlaser import staffeln  # noqa: E402
stufen = [dict(schluessel="20", menge=3)]
vorher = staffeln.kennung(kopf, pos, stufen, k, tab, db.einstellungen())
db.aendern("oberflaechen", next(o["id"] for o in db.zeilen("oberflaechen") if o["oberflaeche"] == "K240"),
           "aufpreis_m", 3.0)
assert staffeln.kennung(kopf, pos, stufen, db.kontext(), tab, db.einstellungen()) != vorher
# Gespeicherte Ergebnisse älterer Versionen (ohne Oberfläche) rechnen unverändert, Kennung bleibt gleich
alt = [dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=900, stueck=5)]
e_alt = rechnen.optimieren(kopf, alt, k)
z_neu, s_neu = rechnen.kalkulation(kopf, alt, e_alt, k, tab, db.einstellungen())
for s in e_alt["stangen"] + e_alt["auswertung"]:
    del s["oberflaeche"]
z_alt, s_alt = rechnen.kalkulation(kopf, alt, e_alt, k, tab, db.einstellungen())
assert s_alt["verkauf"] == s_neu["verkauf"] and rechnen.auswertung_zeilen(e_alt, rechnen.stangen_werte(
    e_alt, kopf, alt, k, tab))[0]["stangen"] == 1
assert rechnen.eingabe_kennung(kopf, alt, k) == rechnen.eingabe_kennung(kopf, [dict(alt[0], oberflaeche=None)], k)
db.schliessen()

# 4) Kategorie raten (ältere Datendateien)
assert kategorie_raten(dict(werkstoff_id="AlMgSi", dichte=2.7)) == "Aluminium"
assert kategorie_raten(dict(werkstoff_id="V2A", werkstoff_nr="1.4301", dichte=7.9)) == "Edelstahl"
assert kategorie_raten(dict(werkstoff_id="X", werkstoff="X5CrNi18-10", dichte=7.9)) == "Edelstahl"
assert kategorie_raten(dict(werkstoff_id="S235-10219", werkstoff_nr="1.0039", dichte=7.85)) == "Stahl"


# 5) Datendatei aus Schema 10 wird erweitert
def schema10(pfad, eigene):
    d = Datenbank(pfad)
    if eigene:      # eigene Schneiddaten ohne Gas und eigener Werkstoff
        d.neu("schneiddaten", dict(maschinen_id="LT7", werkstoff_id="1.4301", wand_bis=3, vorschub_gross=3333))
        d.neu("werkstoffe", dict(werkstoff_id="AlMg3", dichte=2.66, tonnenpreis=5000))
    d.schliessen()
    con = sqlite3.connect(pfad)
    con.execute("DROP TABLE oberflaechen")
    con.execute("DROP INDEX schneiddaten_schluessel")
    con.execute("DELETE FROM schneiddaten WHERE werkstoff_id IS NULL")
    for t, sp in (("schneiddaten", "kategorie"), ("schneiddaten", "gas"), ("werkstoffe", "kategorie")):
        con.execute(f"ALTER TABLE {t} DROP COLUMN {sp}")
    con.execute("CREATE UNIQUE INDEX schneiddaten_schluessel ON schneiddaten (maschinen_id, werkstoff_id, wand_bis)")
    con.execute("DELETE FROM werkstoffe WHERE werkstoff_id IN ('1.4404', 'E235-10305')")
    if not eigene:     # alte Beispiel-Schneiddaten
        con.execute("INSERT INTO schneiddaten (maschinen_id, werkstoff_id, wand_bis, vorschub_gross, bemerkung) "
                    "VALUES ('RL-1', 'S235-10219', 2, 6000, 'Beispiel')")
    con.execute("PRAGMA user_version=10")
    con.commit()
    con.close()
    return Datenbank(pfad)


# a) unveränderte Beispieldaten: Schneiddaten werden durch die neuen Beispielwerte ersetzt
d = schema10(tmp / "b" / "rohrlaser.db", eigene=False)
assert d.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert d.anzahl("schneiddaten") == len(beispiel_schneiddaten()) and d.anzahl("oberflaechen") == 6
assert d.anzahl("werkstoffe") == 12 and all(w["kategorie"] for w in d.zeilen("werkstoffe"))
assert d.einstellung("stammdaten_herkunft") == "Beispieldaten"
d.schliessen()
# b) eigene Werte: bleiben erhalten und gehen vor; Kategorie wird geraten, Beispielwerte je Kategorie kommen dazu
d = schema10(tmp / "c" / "rohrlaser.db", eigene=True)
kd, tb = d.kontext(), d.tabellen()
assert kd.werkstoffe["AlMg3"]["kategorie"] == "Aluminium" and kd.werkstoffe["1.4404"]["kategorie"] == "Edelstahl"
assert d.anzahl("schneiddaten") == len(beispiel_schneiddaten()) + 1
eigen = rechnen.schneiddaten("LT7", "1.4301", 2, tb, "Edelstahl")
assert eigen["vorschub_gross"] == 3333 and eigen["gas"] is None
assert rechnen.schneiddaten("LT7", "1.4301", 5, tb, "Edelstahl")["gas"] == "N₂"
assert rechnen.schneiddaten("LT7", "AlMg3", 2, tb, "Aluminium")["vorschub_gross"] == 7000
try:
    d.neu("schneiddaten", dict(maschinen_id="LT7", kategorie="Stahl", gas="N₂", wand_bis=2, vorschub_gross=1))
    raise AssertionError("doppelte Schneiddaten angenommen")
except Exception as e:
    assert "UNIQUE" in str(e), e
d.schliessen()

# 6) Auswahlliste im Programm: Überschriften je Kategorie sind nicht wählbar
from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402
from rohrlaser.fenster import liste_fuellen  # noqa: E402
app = QApplication.instance() or QApplication([])
cb = QComboBox()
liste_fuellen(cb, k, "werkstoff")
texte = [cb.itemText(i) for i in range(cb.count())]
assert texte[:3] == ["", "— Stahl —", "E235-10305"] and "— Edelstahl —" in texte and "— ohne Kategorie —" in texte
assert not cb.model().item(1).isEnabled() and cb.model().item(2).isEnabled()
print("OK: Werkstoff-Kategorien, Oberflächen und Schneiddaten je Kategorie und Schneidgas")
