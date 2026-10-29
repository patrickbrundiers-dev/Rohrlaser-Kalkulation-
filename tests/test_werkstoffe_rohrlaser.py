"""Werkstoffliste für den Rohrlaser (Patrick 24.10.2026 „Alles umsetzen“: 1b, 2a, 3a, 4b, 5b).
- R1 neue Datei: 29 Werkstoffe, Kategorie Buntmetall mit Faser-Richtwerten (nicht auf T03), Tooltip-Text
- R2 Schneiddaten: Vorschub-Faktor nur auf Kategorie-Zeilen, Schneidgas 'nur N₂'/'nur O₂'
- R3 Prüfung 'nur Faser' auf CO₂-Maschine, Werkstoff ohne Naht: Nahtvorgabe entfällt, kein Stangenwechsel SN
- R4 Laser-Hinweise: Angebots-Check, Werkstattpapiere, Kalkulation-PDF; Materialanfrage nennt 'nahtlos'
- R5 Festschreiben: Schneidgas und Faktor im Snapshot, Abweichungstext
- R6 Update einer bestehenden Datei (werkstoffe_stand): fehlende Werkstoffe, Buntmetall, eigene Werte bleiben

Aufruf: python tests/test_werkstoffe_rohrlaser.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import angebot_check, ausgabe, materialanfrage, naht, pdf, rechnen  # noqa: E402
from rohrlaser.datenbank import WERKSTOFFE_STAND, Datenbank  # noqa: E402
from rohrlaser.stammdaten import TABELLE, beispiel_werkstoffe, pruefen, werkstoff_info  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())

# ------------------------------------------------------------------ R1 neue Datei
db = Datenbank(tmp / "a" / "rohrlaser.db")
k, tab = db.kontext(), db.tabellen()
assert len(k.werkstoffe) == 29 and "Buntmetall" in k.kategorien
assert all(pruefen(TABELLE["werkstoffe"], z, k) == "OK" for z in k.werkstoffe.values())
for m in ("T03", "T11", "LT7"):
    assert pruefen(TABELLE["maschinen"], k.maschinen[m], k) == "OK", (m, pruefen(TABELLE["maschinen"], k.maschinen[m], k))
bunt = {z["maschinen_id"] for z in tab["schneiddaten"] if z["kategorie"] == "Buntmetall"}
assert bunt == {"T11", "LT7"}, bunt
assert k.werkstoffe["DX51D+Z275"]["gas_vorgabe"] == "nur N₂" and k.werkstoffe["1.4462"]["vorschub_faktor"] == 0.8
assert k.werkstoffe["AW6060-T66"]["rohrart"] == "stranggepresst" and k.werkstoffe["Cu-DHP"]["laser"] == "nur Faser"
info = werkstoff_info(k.werkstoffe["DX51D+Z275"])
assert "Rohrlaser: geschweißt, nur N₂, Vorschub × 0,9" in info and "Zinkdampf" in info, info
assert werkstoff_info({}) == "" and len(beispiel_werkstoffe()[0]) == len(TABELLE["werkstoffe"].felder)
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402
from rohrlaser.fenster import liste_fuellen  # noqa: E402
app = QApplication.instance() or QApplication([])
cb = QComboBox()
liste_fuellen(cb, k, "werkstoff")
i = cb.findText("Cu-DHP")
assert "nur Faser" in cb.itemData(i, Qt.ToolTipRole) and cb.itemData(1, Qt.ToolTipRole) is None
ok("R1 29 Werkstoffe, Buntmetall-Richtwerte nur Faser, Tooltip in der Werkstoffwahl")

# ------------------------------------------------------------------ R2 Schneiddaten
sd = lambda m, w, s: rechnen.schneiddaten(m, w, s, tab, rechnen.kategorie(w, k), rechnen.werkstoff_zeile(w, k))
assert sd("LT7", "S235-10219", 3)["vorschub_gross"] == 3500      # ab 0.9.197, bis 0.9.196 4.500
z = sd("LT7", "DX51D+Z275", 3)
assert (z["gas"], z["vorschub_gross"], z["vorschub_mittel"]) == ("N₂", 3150, 1890), z   # × 0,9; bis 0.9.196 4.050 / 2.430
assert sd("LT7", "S235-10219", 5)["gas"] == "O₂" and sd("LT7", "DX51D+Z275", 5) is None      # nur N₂
assert sd("LT7", "Cu-DHP", 2)["gas"] == "O₂" and sd("LT7", "Cu-DHP", 2)["vorschub_gross"] == 1800
assert sd("LT7", "CuZn37", 2)["gas"] == "N₂" and sd("T03", "CuZn37", 2) is None
assert sd("T11", "1.4462", 3)["vorschub_gross"] == 4640          # 5.800 × 0,8
# ohne Werkstoffzeile wie bisher; eigene Zeile des Werkstoffs ohne Faktor (2a)
assert rechnen.schneiddaten("LT7", "DX51D+Z275", 3, tab, "Stahl")["vorschub_gross"] == 3500
db.neu("schneiddaten", dict(maschinen_id="LT7", werkstoff_id="1.4462", gas="N₂", wand_bis=3, vorschub_gross=3000))
tab = db.tabellen()
assert sd("LT7", "1.4462", 3)["vorschub_gross"] == 3000 and sd("LT7", "1.4462", 4)["vorschub_gross"] == 3600   # 4.500 × 0,8 (bis 0.9.196 2.800)
assert rechnen.vorschub_faktor(dict(vorschub_faktor=0)) == 1 and rechnen.gase_von(None) == ("N₂", "O₂")
ok("R2 Vorschub-Faktor auf Kategorie-Zeilen, eigene Zeilen ohne Faktor, Schneidgas nur N₂/nur O₂")

# ------------------------------------------------------------------ R3 Prüfungen, nahtlos
kopf = dict(maschine="T03", stange=6000)
p = dict(pos=10, artikel="Cu", profil_id="RR 42,4x2,0", werkstoff_id="Cu-DHP", laenge=500, stueck=2, schneidweg=300,
         einstiche=2, preis_m=10.0)
st = lambda p, kopf: rechnen.status(p, rechnen.position_werte(p, kopf, k, tab), kopf, k)
assert st(p, kopf) == "WARNUNG: Cu-DHP nur mit Faserlaser – Maschine T03 ist ein CO₂-Laser", st(p, kopf)
assert "Faserlaser" not in st(p, dict(kopf, maschine="LT7"))
fest = dict(naht_vorgabe=naht.FEST, naht_winkel=0, naht_quelle="Kunde")
kopf = dict(maschine="LT7", stange=6000)
mit = dict(p, werkstoff_id="S235-10219", **fest)
ohne = dict(p, werkstoff_id="P235GH-10216", **fest)
assert "ohne Schweißnaht" not in st(mit, kopf)
assert st(ohne, kopf) == "HINWEIS: Werkstoff P235GH-10216 ohne Schweißnaht – Nahtvorgabe entfällt", st(ohne, kopf)
for pos, sn in (([mit], 1), ([ohne], 0)):
    erg = rechnen.optimieren(kopf, pos, k)
    assert rechnen.beladungen_sn(erg["stangen"]) == sn, (pos, erg["stangen"])
assert rechnen.naht_wirksam(ohne, k) == naht.KEINE and rechnen.naht_wirksam(mit, k) == naht.FEST
ok("R3 'nur Faser' warnt auf CO₂, Werkstoff ohne Naht: Hinweis, frei drehbar, kein Stangenwechsel SN")

# ------------------------------------------------------------------ R4 Hinweise, Materialanfrage
pos = [dict(p, werkstoff_id="DX51D+Z275"), dict(p, pos=20, werkstoff_id="DX51D+Z275"),
       dict(p, pos=30, werkstoff_id="S235-10219"), dict(p, pos=40, werkstoff_id="1.4462", profil_id=None)]
h = rechnen.laser_hinweise(pos, k)
assert [(x["werkstoff"], x["zeilen"]) for x in h] == [("DX51D+Z275", [0, 1])], h
punkte = angebot_check.punkte(kopf, pos, ["OK"] * 4, "aktuell", {}, laser_hinweise=h)
treffer = [x for x in punkte if x.text.startswith("Werkstoff DX51D+Z275: verzinkt")]
assert len(treffer) == 1 and treffer[0].art == angebot_check.HINWEIS and treffer[0].ziel == "pos:0", punkte
erg = rechnen.optimieren(kopf, pos[:3], k)
wp = ausgabe.werkstatt(kopf, pos[:3], erg, k, tab)
assert wp["hinweise"] == h
pdf.werkstatt_pdf(tmp / "werkstatt.pdf", dict(kopf, nummer="T-1"), wp, True, db.einstellungen())
zeilen, summen = rechnen.kalkulation(kopf, pos[:3], erg, k, tab, db.einstellungen())
pdf.kalkulation_pdf(tmp / "kalk.pdf", dict(kopf, nummer="T-1"), zeilen, summen, db.einstellungen(), hinweise=h)
assert (tmp / "werkstatt.pdf").stat().st_size > 1000 and (tmp / "kalk.pdf").stat().st_size > 1000
assert materialanfrage.anforderungen("P235GH-10216", k) == "nahtlos"
assert materialanfrage.anforderungen("S235-10219", k) == ""
ok("R4 Laser-Hinweis im Angebots-Check und in den PDFs, Materialanfrage nennt 'nahtlos'")

# ------------------------------------------------------------------ R5 Festschreiben
pb = rechnen.preisbasis_aus(kopf, pos[:3], k, tab)
assert pb["werkstoff_laser"] == {"DX51D+Z275": dict(gas_vorgabe="nur N₂", vorschub_faktor=0.9)}, pb["werkstoff_laser"]
i = k.werkstoffe["DX51D+Z275"]["id"]
db.aendern("werkstoffe", i, "vorschub_faktor", 0.5)
k2, tab2 = db.kontext(), db.tabellen()
kf, tf = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=pb), k2, tab2)
assert kf.werkstoffe["DX51D+Z275"]["vorschub_faktor"] == 0.9 and kf.werkstoffe["S235-10219"]["gas_vorgabe"] is None
assert "Schneidgas/Vorschub-Faktor DX51D+Z275 geändert" in rechnen.preisbasis_abweichung(dict(kopf, preisbasis=pb), k2, tab2)
alt = {n: v for n, v in pb.items() if n != "werkstoff_laser"}          # älterer Snapshot: aktuelle Werte
kf, _ = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=alt), k2, tab2)
assert kf.werkstoffe["DX51D+Z275"]["vorschub_faktor"] == 0.5
assert not [t for t in rechnen.preisbasis_abweichung(dict(kopf, preisbasis=alt), k2, tab2) if "Faktor" in t]
db.schliessen()
ok("R5 Schneidgas und Faktor festgeschrieben, Abweichung genannt, alte Snapshots mit aktuellen Werten")

# ------------------------------------------------------------------ R6 Update einer bestehenden Datei
pfad = tmp / "b" / "rohrlaser.db"
d = Datenbank(pfad)
neue = [w[0] for w in beispiel_werkstoffe()[12:]]
d.con.execute(f"DELETE FROM werkstoffe WHERE werkstoff_id IN ({', '.join('?' * len(neue))})", neue)
d.con.execute("UPDATE werkstoffe SET rohrart=NULL, gas_vorgabe=NULL, vorschub_faktor=NULL, laser=NULL, "
              "laser_hinweis=NULL")
d.con.execute("UPDATE werkstoffe SET rohrart='nahtlos' WHERE werkstoff_id='S355-10219'")     # eigener Wert
d.con.execute("DELETE FROM schneiddaten WHERE kategorie='Buntmetall'")
d.con.execute("DELETE FROM einstellungen WHERE name='werkstoffe_stand'")
d.con.execute("INSERT OR REPLACE INTO einstellungen VALUES ('kategorien', ?)", (json.dumps("Stahl\nEdelstahl\nAluminium"),))
d.con.commit()
d.schliessen()
d = Datenbank(pfad)
kd = d.kontext()
assert len(kd.werkstoffe) == 29 and d.einstellung("werkstoffe_stand") == WERKSTOFFE_STAND
assert kd.kategorien == ("Stahl", "Edelstahl", "Aluminium", "Buntmetall"), kd.kategorien
assert kd.werkstoffe["S235-10219"]["rohrart"] == "geschweißt" and kd.werkstoffe["1.4571"]["vorschub_faktor"] == 0.95
assert kd.werkstoffe["S355-10219"]["rohrart"] == "nahtlos" and kd.werkstoffe["S355-10219"]["gas_vorgabe"] is None
assert {z["maschinen_id"] for z in d.zeilen("schneiddaten") if z["kategorie"] == "Buntmetall"} == {"T11", "LT7"}
d.schliessen()
ok("R6 Update: fehlende Werkstoffe und Buntmetall ergänzt, eigene Werte bleiben")
print("OK: Werkstoffliste für den Rohrlaser")
