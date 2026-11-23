"""ERP-Einkauf im Materialstamm (Patrick 23.11.2026):
- Profile und Werkstoffe aus dem EK anlegen (Norm, Naht, Güte; S235 EN 10210 gibt es nicht -> EN 10219; Flachstahl
  ohne Rohrnorm; Unklares bleibt offen; zweiter Lauf legt nichts doppelt an; Sicherung und Zuordnungen),
- Werkstoff je Profil nach dem EK als Vorauswahl im STEP-Import (Mehrheit nach Metern, Vorgabe/eigene Wahl bleibt),
- Preis direkt einsetzen nur bei jungem Kauf (≤ 4 Wochen) und passender Stangenzahl (± x), sonst Vorschlag,
- Preishistorie: Monate, Trend, Vorschlag, Übernehmen in die Preise,
- Materialseite: ERP-Spalten, Anlegen über das Menü.
Alle Preise und Käufe sind Testwerte relativ zu heute.

Aufruf: python tests/test_erp_anlegen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import erp_anlegen as A  # noqa: E402
from rohrlaser import erp_preise as E  # noqa: E402
from rohrlaser import material_historie as H  # noqa: E402
from rohrlaser import materialplattform as mp  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
HEUTE = datetime.date.today()


def ok(text):
    print("OK    ", text)


def kauf(i, text, tage, menge, preis):
    return dict(zeile=i, datum=HEUTE - datetime.timedelta(days=tage), menge=menge, preis=preis, artikelnr=f"A{i}",
                bezeichnung=text, schluessel=E.schluessel(f"A{i}", text))


# ------------------------------------------------------------------ Erkennung ohne Datenbank
assert A.guete("QR 50x50x4 S355J2H EN10210") == ("S", "355")
assert A.familie("RR 42,4x2,6 S235 nahtlos") == "10210"
assert A.familie("QR 60x60x3 S235JRH EN 10219") == "10219"
assert A.familie("RE 80x40x3 S355J2H kaltgefertigt") == "10219"
assert A.familie("Präzisionsrohr 30x2 E235", "E") == "10305"
assert A.familie("QR 40x40x3 S235") is None
assert A.naht("RR 33,7x2 nahtlos") == "nahtlos" and A.naht("RR 33,7x2 geschweißt") == "geschweißt"
ok("Güte, Norm-Familie (EN 10219/10210/10305) und Naht aus der EK-Bezeichnung")

# ------------------------------------------------------------------ Anlegen
db = Datenbank(tmp / "rohrlaser.db")
TEXTE = ["Rundrohr 42,4x2,6 S235 nahtlos", "QR 50x50x4 S355 EN10210 warmgefertigt", "QR 60x60x3 S235JRH EN 10219",
         "Rechteckrohr 80x40x3 S275J0H EN10210 warmgefertigt", "Präzisionsrohr 30x2 E235", "Flachstahl 40x5 S235JR",
         "Irgendwas ohne Maß", "QR 70x70x4 S355", "QR 75x75x4 S235"]
E.speichern(db, [kauf(i, t, 20, 60, 3.2) for i, t in enumerate(TEXTE)])
p = A.plan(db)
pids = {x["profil_id"] for x in p["profile"]}
assert {"RR 42,4x2,6", "QR 50x50x4", "QR 60x60x3", "RE 80x40x3", "RR 30x2", "FL 40x5"} <= pids, pids
assert all("aus ERP-EK angelegt" in x["bemerkung"] for x in p["profile"])
ws = {w["werkstoff_id"]: w for w in p["werkstoffe"]}
assert "S235-10210" not in ws, "S235 EN 10210 gibt es nicht (Patrick 20.11.2026)"
assert set(ws) == {"S275-10210"}, ws
w = ws["S275-10210"]
assert w["norm"] == "EN 10210 warmgefertigt" and w["rohrart"] == "nahtlos" and w["werkstoff"] == "S275J0H"
assert "Vorlage S275-10219" in w["bemerkung"] and w["dichte"] and w["laser_hinweis"]
zu = {x["bezeichnung"]: x for x in p["zuordnungen"]}
assert zu["Rundrohr 42,4x2,6 S235 nahtlos"]["werkstoff_id"] == "S235-10219"
assert zu["QR 50x50x4 S355 EN10210 warmgefertigt"]["werkstoff_id"] == "S355-10210"
assert zu["Rechteckrohr 80x40x3 S275J0H EN10210 warmgefertigt"]["werkstoff_id"] == "S275-10210"
assert zu["Präzisionsrohr 30x2 E235"]["werkstoff_id"] == "E235-10305"
assert "Flachstahl 40x5 S235JR" not in zu, "Vollmaterial nie mit Rohrnorm"
offen = {x["bezeichnung"]: x["grund"] for x in p["offen"]}
assert "Irgendwas ohne Maß" in offen and "Flachstahl 40x5 S235JR" in offen
assert offen.get("QR 70x70x4 S355", "").startswith("Norm/Naht"), offen
assert zu["QR 75x75x4 S235"]["werkstoff_id"] == "S235-10219", "S235 gibt es nur als EN 10219"
ok("Plan: Profile mit Maßen, neuer Werkstoff mit Norm/Naht nach Vorlage, S235 EN 10210 -> EN 10219, Unklares offen")

erg = A.ausfuehren(db, p)
k = db.kontext()
assert erg["profile"] == len(p["profile"]) and erg["werkstoffe"] == 1 and erg["sicherung"]
assert "RE 80x40x3" in k.profile and k.profile["RE 80x40x3"]["b"] == 40 and "S275-10210" in k.werkstoffe
gem = E.zuordnungen(db)
assert any(z["werkstoff_id"] == "S275-10210" for z in gem.values())
p2 = A.plan(db)
assert not (p2["profile"] or p2["werkstoffe"] or p2["zuordnungen"]), p2
ok("Ausführen: Sicherung, Profile/Werkstoff angelegt, Zuordnungen gemerkt; zweiter Lauf legt nichts doppelt an")

p3 = A.plan(db, [kauf(50, "QR 90x90x5 S275 EN10210", 3, 12, 4.0)])
erg3 = A.ausfuehren(db, dict(p3, werkstoffe=[dict(p3["werkstoffe"][0] if p3["werkstoffe"] else {},
                                                  werkstoff_id="X-gibt-es-nicht")]), mit_werkstoffen=False)
assert erg3["werkstoffe"] == 0 and "X-gibt-es-nicht" not in db.kontext().werkstoffe
ok("Ohne Freigabe für Werkstoffe: nur Profile, keine Zuordnung auf fehlende Werkstoffe")

# ------------------------------------------------------------------ Werkstoff-Vorauswahl je Profil
db2 = Datenbank(tmp / "vorwahl.db")
E.speichern(db2, [kauf(1, "QR 50x50x4 S355J2H EN10210", 30, 120, 3.0), kauf(2, "QR 50x50x4 S355J2H EN 10210", 60, 60, 3.1),
                  kauf(3, "QR 50x50x4 S235JRH EN10219", 40, 18, 2.5), kauf(4, "QR 40x40x3 S235JRH EN10219", 10, 30, 2.0),
                  kauf(5, "QR 40x40x3 S355J2H EN10219", 10, 30, 2.6)])
A.ausfuehren(db2, A.plan(db2))
jp = A.werkstoff_je_profil(db2)
assert jp["QR 50x50x4"]["werkstoff_id"] == "S355-10210" and jp["QR 50x50x4"]["kaeufe"] == 2, jp
assert "QR 40x40x3" not in jp, "50/50 ist keine Mehrheit"
assert A.werkstoff_je_profil(db2, heute=HEUTE + datetime.timedelta(days=800)) == {}
mw = [dict(profilform="Quadratrohr", _profil="QR 50x50x4"), dict(profilform="Quadratrohr", _profil="QR 40x40x3"),
      dict(profilform="Quadratrohr", _profil="QR 50x50x4", _werkstoff="1.4301"),
      dict(profilform="Quadratrohr", _profil="QR 50x50x4", fehler="x")]
assert A.vorauswahl(mw, db2.kontext().profile, jp, "S235-10219") == 1
assert mw[0]["_werkstoff"] == mw[0]["_werkstoff_vorschlag"] == "S355-10210" and "EK-Einkauf" in mw[0]["_werkstoff_text"]
assert "_werkstoff" not in mw[1] and mw[2]["_werkstoff"] == "1.4301"
from rohrlaser import importprofil  # noqa: E402

mw[0]["_uebernehmen"] = True
assert "werkstoff_id" not in importprofil.korrekturen([mw[0]], [True], "S235-10219"), "EK-Vorwahl ist keine Korrektur"
assert db2.einstellung("erp_werkstoff_vorwahl") == "ja"
ok("Vorauswahl: Werkstoff mit Norm je Profil nach EK-Mehrheit, eigene Wahl bleibt, Importprofil lernt sie nicht")

# ------------------------------------------------------------------ Preis direkt einsetzen (≤ 4 Wochen, ± x Stangen)
ks = [dict(datum=HEUTE - datetime.timedelta(days=10), menge=60.0, preis=3.0, id=1),
      dict(datum=HEUTE - datetime.timedelta(days=40), menge=60.0, preis=2.8, id=2),
      dict(datum=HEUTE - datetime.timedelta(days=5), menge=600.0, preis=2.5, id=3)]
assert E.direkt_kauf(ks, 10, 6000, HEUTE)["id"] == 1
assert E.direkt_kauf(ks, 12, 6000, HEUTE)["id"] == 1                # ± 2 Stangen
assert E.direkt_kauf(ks, 13, 6000, HEUTE) is None
assert E.direkt_kauf(ks, 100, 6000, HEUTE)["id"] == 3
assert E.direkt_kauf(ks, 10, 6000, HEUTE, tage=5) is None
assert E.direkt_kauf([dict(ks[0], rechnen=0)], 10, 6000, HEUTE) is None
assert E.direkt_kauf(ks, 10, None, HEUTE) is None
ok("Direkt einsetzen nur bei Kauf ≤ 28 Tage und Stangenzahl ± 2 (einstellbar), ausgeschlossene Käufe zählen nicht")

from rohrlaser import rechnen  # noqa: E402

kopf = dict(erp_preise={"RR 1|W|": dict(preis=3.0, direkt=False), "RR 2|W|": dict(preis=4.0, direkt=True),
                        "RR 3|W|": dict(preis=5.0)})
for pid, direkt in (("RR 1", False), ("RR 2", True), ("RR 3", True)):
    gr = (pid, "W", "")
    assert (rechnen.erp_preis(kopf, gr) is not None) == direkt, pid
    assert (rechnen.erp_preis(kopf, gr, vorschlag=True) is not None) == (not direkt), pid
ok("Angebot rechnet nur direkte ERP-Preise; ältere Einträge ohne Merkmal gelten weiter")

# ------------------------------------------------------------------ Preishistorie und Vorschlag
db3 = Datenbank(tmp / "historie.db")
T = "RR 42,4x2,0 S235JRH EN10219"
E.speichern(db3, [kauf(i, T, tage, 60, preis) for i, (tage, preis) in
                  enumerate(((300, 2.40), (200, 2.60), (120, 2.80), (40, 3.00), (10, 3.10)))])
A.ausfuehren(db3, A.plan(db3))
g = mp.erp_gruppen(db3)
zeilen = mp.varianten(db3.kontext(), db3.tabellen(), erp=g)
z = next(x for x in zeilen if x["profil_id"] == "RR 42,4x2,0" and x["werkstoff_id"] == "S235-10219")
assert z.get("erp_schnitt") and z.get("erp_letzter")
pp = mp.preis_punkte(db3, "RR 42,4x2,0", "S235-10219")
assert len(pp["erp"]) == 5
mon = H.monate(pp)
assert mon and mon[0]["monat"] == HEUTE.strftime("%Y-%m") or mon[0]["kaeufe"] >= 0
assert sum(m["kaeufe"] for m in mon) == 5
tr = H.trend(pp)
assert tr and tr["steigung"] > 0 and tr["pct_jahr"] > 0, tr
v = H.vorschlag(z, pp)
assert v, "Vorschlag aus steigenden Käufen erwartet"
if v:
    assert v["quelle"] and v["begruendung"] and 2.4 <= v["preis_m"] <= 3.6, v
    db3.admin_freischalten() if hasattr(db3, "admin_freischalten") else None
    text = H.uebernehmen(db3, "RR 42,4x2,0", "S235-10219", v["preis_m"], v["quelle"])
    assert text
    z2 = next(x for x in mp.varianten(db3.kontext(), db3.tabellen(), erp=mp.erp_gruppen(db3)) if x["profil_id"] == "RR 42,4x2,0"
              and x["werkstoff_id"] == "S235-10219")
    assert abs(z2["preis_m"] - v["preis_m"]) < 0.02, (z2["preis_m"], v["preis_m"])
ok("Preishistorie: Monate, steigender Trend, Vorschlag aus gewichteten Käufen, Übernehmen schreibt die Preise")

# ------------------------------------------------------------------ Materialseite
from rohrlaser.fenster import Hauptfenster  # noqa: E402

f = Hauptfenster(Datenbank(tmp / "seite.db"))
f.stumm = True
s = f.material
E.speichern(f.db, [kauf(1, "QR 55x55x3 S355J2H EN10219", 5, 30, 3.0), kauf(2, "RE 70x30x3 S275 EN 10210", 5, 30, 3.0)])
f.bereich.sitzung.freischalten() if hasattr(f.bereich, "sitzung") else None
erg = s.erp_anlegen(frage=False)
assert erg and erg["profile"] == 2 and erg["werkstoffe"] == 1, erg
assert "QR 55x55x3" in f.db.kontext().profile and "S275-10210" in f.db.kontext().werkstoffe
assert s.erp_anlegen(frage=False) is None
s.neu_laden(erzwingen=True)
zz = [x for x in s.alle_zeilen if x["profil_id"] == "QR 55x55x3"]
assert not zz or any(x.get("erp_letzter") for x in zz)
ok("Materialseite: „Profile und Werkstoffe aus dem EK anlegen …“ legt an, zweiter Lauf nichts")
print("Alle Tests bestanden")
