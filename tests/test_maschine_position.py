"""Maschine je Position (MACH-006 Variante B, Patrick 13.11.2026 „Alle Empfehlungen“), Paket 1:

- M1 Spalte „Maschine abweichend“: leer bzw. gleich der Kopf-Maschine rechnet bitgleich wie bisher
- M2 Schnittplan: Teile der abweichenden Maschine nie mit Teilen der Kopf-Maschine auf einer Stange, Stangen tragen
  die Maschine; Material je Teil bleibt gleich
- M3 Kalkulation: Laserzeit mit Schneiddaten und Stundensatz der abweichenden Maschine, Rüsten Maschine je
  eingesetzter Maschine einmal
- M4 unbekannte Maschine: nicht eingeplant mit Grund, Angebots-Check FEHLER; abweichende Maschine: HINWEIS

Aufruf: python tests/test_maschine_position.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


db = Datenbank(Path(tempfile.mkdtemp()) / "r.db")
k, tab = db.kontext(), db.tabellen()
assert {"T03", "LT7"} <= set(k.maschinen)
kopf = dict(maschine="T03", stange=6000, skonto=0)
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())


def positionen(m_b=None):
    return [dict(pos=10, artikel="A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000, stueck=10,
                 schneidweg=200, einstiche=1),
            dict(pos=20, artikel="B", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000, stueck=10,
                 schneidweg=200, einstiche=1, maschine=m_b)]


def rechne(m_b):
    pos = positionen(m_b)
    erg = rechnen.optimieren(kopf, pos, k, tab, einst)
    z, s = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
    return erg, z, s


# ------------------------------------------------------------------ M1
erg0, z0, s0 = rechne(None)
erg1, z1, s1 = rechne("T03")
assert erg1["stangen"] == erg0["stangen"] and abs(s1["verkauf"] - s0["verkauf"]) < 1e-9
assert [x["preis_position"] for x in z1] == [x["preis_position"] for x in z0]
assert all("maschine" not in st for st in erg0["stangen"])
ok(f"M1 ohne bzw. mit gleicher Maschine wie der Kopf: unverändert ({s0['verkauf']:.2f} €, {len(erg0['stangen'])} Stangen)")

# ------------------------------------------------------------------ M2
erg2, z2, s2 = rechne("LT7")
lt7 = [st for st in erg2["stangen"] if st.get("maschine") == "LT7"]
t03 = [st for st in erg2["stangen"] if not st.get("maschine")]
assert lt7 and t03
assert all({t["artikel"] for t in st["teile"]} == {"B"} for st in lt7)
assert all({t["artikel"] for t in st["teile"]} == {"A"} for st in t03)
assert abs(z2[0]["material_teil"] - z0[0]["material_teil"]) < 1e-9 and z2[1]["material_teil"] > 0
assert not erg2["fehler"]
ok(f"M2 Schnittplan: {len(t03)} Stangen T03 nur mit A, {len(lt7)} Stangen LT7 nur mit B, Material je Teil gleich")

# ------------------------------------------------------------------ M3
assert abs(z2[0]["laser_teil"] - z0[0]["laser_teil"]) < 1e-9            # A rechnet weiter auf T03
kopf_lt7 = dict(kopf, maschine="LT7")
erg_l, z_l, s_l = (lambda p: (lambda e: (e,) + rechnen.kalkulation(kopf_lt7, p, e, k, tab, einst))(
    rechnen.optimieren(kopf_lt7, p, k, tab, einst)))(positionen())
assert abs(z2[1]["laser_teil"] - z_l[1]["laser_teil"]) < 1e-9, (z2[1]["laser_teil"], z_l[1]["laser_teil"])
assert abs(z2[1]["laser_teil"] - z0[1]["laser_teil"]) > 1e-6                # LT7 rechnet anders als T03
rm_t03 = s0["ruesten_maschine"]
rm_lt7 = s_l["ruesten_maschine"]
assert abs(s2["ruesten_maschine"] - (rm_t03 + rm_lt7)) < 1e-6, (s2["ruesten_maschine"], rm_t03, rm_lt7)
assert s2["maschinen"] == ["T03", "LT7"]
ok(f"M3 Kalkulation: B mit Laserzeit und Satz der LT7 ({z2[1]['laser_teil']:.3f} € statt {z0[1]['laser_teil']:.3f} € "
   f"je Teil), Rüsten Maschine {rm_t03:.2f} € + {rm_lt7:.2f} €")

# ------------------------------------------------------------------ M4
pos = positionen("GIBT-ES-NICHT")
erg4 = rechnen.optimieren(kopf, pos, k, tab, einst)
assert any("nicht in den Stammdaten" in f["grund"] and f["artikel"] == "B" for f in erg4["fehler"]), erg4["fehler"]
app = QApplication.instance() or QApplication([])
f = Hauptfenster(db, stumm=True)
a = db.angebot_neu(dict(kunde="Beispiel GmbH", maschine="T03", stange=6000))
for p in positionen("LT7"):
    db.position_neu(a, p)
s = f.angebot_oeffnen(a)
punkte = s._maschine_punkte()
assert len(punkte) == 1 and punkte[0][0] == "HINWEIS" and "LT7" in punkte[0][1] and "20" in punkte[0][1], punkte
assert s.optimieren()
assert any(st.get("maschine") == "LT7" for st in db.angebot(a)["ergebnis"]["stangen"])
assert "maschine" in __import__("rohrlaser.angebot_fenster", fromlist=["x"]).OPTIONALE_SPALTEN
ok("M4 unbekannte Maschine: nicht eingeplant mit Grund; Angebots-Check HINWEIS für Pos. 20 auf LT7; "
   "im Angebot optimiert mit LT7-Stangen")
print("Alle Prüfungen bestanden.")
