"""Prüft Kundenmaterial je Position (Schema 25): Spalte Material (Eigenmaterial / Kunde beigestellt), Vorgabe im
Angebotskopf, eigene Stangengruppe (nie mit eigenem Material auf einer Stange), keine Materialkosten und kein
Materialzuschlag, Bearbeitung unverändert, andere Positionen unverändert, Handling je kg, Status, Angebotstext,
Hinweis mit Stangenbedarf im Angebots-PDF, Staffelpreise, Werkstattpapier, Nachkalkulation, ältere Dateien.

Aufruf: python tests/test_kundenmaterial.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import ausgabe, nachkalkulation, rechnen, staffeln  # noqa: E402
from rohrlaser.angebot import KUNDENMATERIAL  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-6):
    return a is not None and abs(a - b) <= tol


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
POS = [dict(pos=10, artikel="E1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1200, stueck=8,
            schneidweg=320, einstiche=2),
       dict(pos=20, artikel="K1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1200, stueck=8,
            schneidweg=320, einstiche=2),
       dict(pos=30, artikel="R1", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=900, stueck=5,
            schneidweg=270, einstiche=2)]


def angebot(kunde_bei=(), **kopf):
    a = db.angebot_neu(dict(dict(kunde="Test", skonto=0, mindestpreis=0), **kopf))
    for p in POS:
        db.position_neu(a, dict(p, material_herkunft=KUNDENMATERIAL if p["pos"] in kunde_bei else None))
    return a


def rechnung(a, einst_extra=None):
    kopf, pos = db.angebot(a), db.positionen(a)
    k, tab = db.kontext(), db.tabellen()
    einst = dict(rechnen.einstellungen_angebot(kopf, db.einstellungen()), **(einst_extra or {}))
    erg = rechnen.optimieren(kopf, pos, k, tab, einst)
    z, s = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
    return kopf, pos, k, tab, einst, erg, z, s


eigen = angebot()
mit = angebot(kunde_bei=(20,))
_, _, _, _, _, erg0, z0, s0 = rechnung(eigen)
kopf, pos, k, tab, einst, erg, z, s = rechnung(mit)

# ------------------------------------------------------------------ K1 Optimierung: eigene Stangengruppe
assert rechnen.beigestellt(pos[1]) and not rechnen.beigestellt(pos[0])
qr = [st for st in erg["stangen"] if st["profil"] == "QR 40x40x3"]
kunde = [st for st in qr if st.get("beistellung") == "Kunde"]
eig = [st for st in qr if not st.get("beistellung")]
assert kunde and eig
assert all(pos[t["index"]]["artikel"] == "K1" for st in kunde for t in st["teile"])
assert all(pos[t["index"]]["artikel"] == "E1" for st in eig for t in st["teile"])
assert sum(len(st["teile"]) for st in kunde) == 8 and sum(len(st["teile"]) for st in eig) == 8
assert len([a for a in erg["auswertung"] if a.get("beistellung") == "Kunde"]) == 1
assert not erg["fehler"]
assert rechnen.eingabe_kennung(kopf, pos, k, tab, einst) != rechnen.eingabe_kennung(
    kopf, [dict(p, material_herkunft=None) for p in pos], k, tab, einst)
ok(f"K1 Optimierung: Kundenmaterial eigene Gruppe ({len(kunde)} Stangen nur K1), eigenes Material getrennt ({len(eig)} Stangen)")

# ------------------------------------------------------------------ K2 Kalkulation
zk, ze, zr = z[1], z[0], z[2]
assert zk["material_teil"] == 0 and zk["material_gruppe"] == 0 and zk["zuschlag_material_teil"] == 0
assert zk["kundenmaterial"] == "ja" and ze["kundenmaterial"] == "" and zk["hinweis"] == "", zk["hinweis"]
assert ze["material_teil"] > 0 and zr["material_teil"] > 0
assert nah(zk["laser_teil"], ze["laser_teil"]) and zk["laser_teil"] > 0           # Bearbeitung gleich
assert zk["ruesten_teil"] > 0 and zk["preis_teil"] < ze["preis_teil"]
# andere Positionen: Material wie ohne Kundenmaterial (eigene Gruppe hat dieselbe Belegung je Teil)
assert nah(zr["material_teil"], z0[2]["material_teil"])
assert nah(s["material"], sum(x["material_position"] for x in z if x))
assert s["material"] < s0["material"] and nah(s["laser"], s0["laser"], 1e-6)
ok("K2 Kundenmaterial: Material und Materialzuschlag 0, Laser und Rüsten wie Eigenmaterial, andere Positionen unverändert")

# ------------------------------------------------------------------ K3 Handling je kg
_, _, _, _, einst_h, erg_h, zh, sh = rechnung(mit, dict(handling_beistellung=0.5))
gew = sum(w["gewicht"] for st, w in zip(erg_h["stangen"], rechnen.stangen_werte(erg_h, kopf, pos, k, tab))
          if st.get("beistellung"))
assert nah(sh["handling_beistellung"], 0.5 * gew) and gew > 0
assert zh[0]["handling_teil"] == 0 and zh[2]["handling_teil"] == 0
assert nah(zh[1]["herstell_teil"] - z[1]["herstell_teil"], zh[1]["handling_teil"] * (1 + einst["zuschlag_fertigung"]))
kosten = {n: w for (_, w, _), (_, n, _) in zip(rechnen.kostenarten(sh, einst_h), rechnen.KOSTENARTEN)}
herstell = sum(kosten[n] for n in ("material", "laser_schneiden", "gewinde", "ruesten_maschine", "ruesten_abmessungen",
                                   "stangenwechsel_kosten", "arbeitsschritte", "zusatz", "handling_beistellung",
                                   "zuschlag_material", "zuschlag_fertigung", "zuschlag_fremdleistung"))
assert nah(herstell, sh["herstell"], 1e-6), (herstell, sh["herstell"])
assert db.einstellung("handling_beistellung") == 0 and db.angebot(mit)["handling_beistellung"] == 0
ok(f"K3 Handling 0,50 €/kg × {gew:.1f} kg Kundenmaterial = {sh['handling_beistellung']:.2f} € mit Zuschlag Fertigung; Vorgabe 0")

# ------------------------------------------------------------------ K4 Status, Meterpreis, Angebotstext und PDF-Hinweis
w = rechnen.position_werte(pos[1], kopf, k, tab)
assert rechnen.status(pos[1], w, kopf, k) == "HINWEIS: Material vom Kunden beigestellt"
assert rechnen.status(dict(pos[1], werkstoff_id="1.4301"), rechnen.position_werte(dict(pos[1], werkstoff_id="1.4301"),
                                                                                kopf, k, tab), kopf, k) \
    == "HINWEIS: Material vom Kunden beigestellt"
assert rechnen.meterpreis(pos[1], kopf, pos, k, tab) == (None, None, None) and rechnen.meterpreis(pos[0], kopf, pos, k, tab)[0]
t_k, t_e = ausgabe.angebotstext(pos[1], k), ausgabe.angebotstext(pos[0], k)
assert "Material S235 EN10219 vom Kunden beigestellt" in t_k and "inkl. Material" not in t_k, t_k
assert "inkl. Material S235 EN10219" in t_e
ang = ausgabe.angebot(kopf, pos, z, k, einst, ergebnis=erg)
assert ang["beistellung"] == f"Material wird vom Kunden beigestellt: {len(kunde)} Stange{'n' if len(kunde) > 1 else ''} " \
    "Quadratrohr 40 x 40 x 3, S235 EN10219, à 6.000 mm.", ang["beistellung"]
assert ausgabe.angebot(kopf, pos, z, k, dict(einst, beistellung_hinweis="nein"), ergebnis=erg)["beistellung"] == ""
assert ausgabe.angebot(kopf, pos, z, k, einst)["beistellung"] == "Das Material der Pos. 20 wird vom Kunden beigestellt."
assert ausgabe.angebot(db.angebot(eigen), db.positionen(eigen), z0, k, einst, ergebnis=erg0)["beistellung"] == ""
ok("K4 Status-Hinweis, kein Meterpreis, Angebotstext 'vom Kunden beigestellt', PDF-Hinweis mit Stangenbedarf (abschaltbar)")

# ------------------------------------------------------------------ K5 Staffelpreise, Werkstattpapier, Nachkalkulation
st = staffeln.stufe_rechnen(kopf, pos, "20", 50, k, tab, einst)
assert st["preis"] and st["preis"]["m_grund"] == 0 and not st["hinweis"], st["hinweis"]
st_e = staffeln.stufe_rechnen(kopf, pos, "10", 50, k, tab, einst)
assert st_e["preis"]["m_grund"] > 0 and st["preis_gesamt"] < st_e["preis_gesamt"]
ws = ausgabe.werkstatt(kopf, pos, erg, k, tab)
assert any("Kundenmaterial" in m["werkstoff"] for m in ws["material"])
assert sum(1 for m in ws["material"] if m["profil"] == "QR 40x40x3") == 2
gr = nachkalkulation.gruppen(erg, kopf, pos, k, tab)
kg = [g for g in gr if "Kundenmaterial" in g["werkstoff"]]
assert len(kg) == 1 and kg[0]["kosten"] == 0 and len({g["schluessel"] for g in gr}) == len(gr)
ok("K5 Staffelstufe ohne Materialkosten (kein 'Materialpreis fehlt'), Werkstattpapier und Nachkalkulation getrennt")

# ------------------------------------------------------------------ K6 Vorgabe im Kopf und Oberfläche
v = db.angebot_neu(dict(kunde="V", material_vorgabe=KUNDENMATERIAL))
pv = db.position_neu(v, dict(POS[0]))
assert db.positionen(v)[0]["material_herkunft"] == KUNDENMATERIAL
db.position_neu(v, dict(POS[0], material_herkunft="Eigenmaterial"))       # einzeln überschreibbar
assert db.positionen(v)[1]["material_herkunft"] == "Eigenmaterial"
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
s_ = fenster.angebot_oeffnen(eigen)
kb = s_.kopf_bereich
assert kb.mat_vorgabe.currentText() == "Eigenmaterial"
assert kb.zeilen_erweitert["handling_beistellung"][1].isHidden()        # ohne Kundenmaterial gar nicht angeboten
kb.mat_vorgabe.setCurrentText(KUNDENMATERIAL)
assert db.angebot(eigen)["material_vorgabe"] == KUNDENMATERIAL
assert s_.material_fuer_alle(KUNDENMATERIAL) == 3
assert all(p["material_herkunft"] == KUNDENMATERIAL for p in db.positionen(eigen))
assert not kb.zeilen_erweitert["handling_beistellung"][1].isHidden()    # mit Kundenmaterial: Handling 0 änderbar
m = s_.pos_modell
c = next(i for i, (art, f) in enumerate(m.spalten) if art == "feld" and f.name == "material_herkunft")
assert not s_.pos_ansicht.isColumnHidden(c)
kb.mat_vorgabe.setCurrentText("Eigenmaterial")
assert db.angebot(eigen)["material_vorgabe"] is None
ok("K6 Vorgabe 'Material neuer Positionen', 'Für alle Positionen', Spalte Material sichtbar, je Position überschreibbar")

# ------------------------------------------------------------------ K7 ältere Datei (Schema 24)
db.schliessen()
alt = tmp / "alt.db"
shutil.copy(tmp / "rohrlaser.db", alt)
con = sqlite3.connect(alt)
con.execute("ALTER TABLE positionen DROP COLUMN material_herkunft")
for sp in ("material_vorgabe", "handling_beistellung"):
    con.execute(f"ALTER TABLE angebote DROP COLUMN {sp}")
con.execute("PRAGMA user_version=24")
con.commit()
con.close()
db2 = Datenbank(alt)
assert db2.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert all(p["material_herkunft"] is None for p in db2.positionen(mit))
assert db2.sicherungen(zusatz=f"vor_Schema_{SCHEMA_VERSION}")
db2.schliessen()
ok("K7 Datei Schema 24: Spalten ergänzt, alle Positionen Eigenmaterial (Preise unverändert), Sicherung")
print("OK: Kundenmaterial")
