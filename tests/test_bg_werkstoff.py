"""Prüft Werkstoff und Nachbehandlung der Schweißbaugruppe (Plan Schweißbaugruppen 28.10.2026, Schritt 2):
- W1 Faktor Werkstoff auf die Lichtbogenzeit (Stand der Nahtgruppe), Richtwerte Stahl/Edelstahl/Aluminium
- W2 Vorschlag Werkstoff je Nahtgruppe aus den Teilen (nicht bei Stahl), Wechsel auf Stahl entfernt ihn
- W3 Beizen bei Edelstahl, Richten bei viel Naht je kg und dünner Wand, Sichtprüfung (Handrechnung)
- W4 ohne die neuen Regeln: keine Vorschläge, nur Edelstahl ohne Beiz-Regel meldet einen Hinweis
- W5 Editor: Spalte Werkstoff gelb als Vorschlag, Faktor in der Schweißzeit

Aufruf: python tests/test_bg_werkstoff.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import baugruppe, vorkalk  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


db = Datenbank(Path(tempfile.mkdtemp()) / "w.db")
k = db.kontext()
TAB = dict(schweissverfahren=[dict(verfahren="WIG", satz_id="Schweißen", lichtbogen=50, heft_s=0, status="geprüft")],
           schweiss_kennwerte=[dict(verfahren="WIG", nahtart="Kehlnaht", mass_bis=4, min_m=4.0, status="geprüft")],
           schweiss_faktoren=[dict(art="Werkstoff", wert="Edelstahl", faktor=1.3, status="geprüft")],
           schweiss_regeln=[dict(art=a, wert=w, bis=b, zahl=z, status="geprüft") for a, w, b, z, _ in vorkalk.RICHTWERTE])
SAETZE = {"Schweißen": 60.0}

# ------------------------------------------------------------------ W1 Faktor Werkstoff
naht = dict(verfahren="WIG", nahtart="Kehlnaht", mass=3, laenge=500, anzahl=1)
r0 = baugruppe.naht_rechnen(naht, TAB, SAETZE)
r1 = baugruppe.naht_rechnen(dict(naht, werkstoff="Edelstahl"), TAB, SAETZE)
nah(r0["zeit_min"], 0.5 * 4.0 / 0.5, "Stahl: 0,5 m × 4 min/m ÷ 50 %")
nah(r1["zeit_min"], r0["zeit_min"] * 1.3, "Edelstahl × 1,3")
st = baugruppe.naht_stand(dict(naht, werkstoff="Edelstahl"), TAB)
assert st["f_werkstoff"] == 1.3
alt = dict(st)
alt.pop("f_werkstoff")                                     # gemerkter Stand vor 0.9.171: Faktor 1, bitgleich
nah(baugruppe.naht_rechnen(dict(naht, werkstoff="Edelstahl", stand=alt), TAB, SAETZE)["zeit_min"], r0["zeit_min"])
rw = {(z["art"], z["wert"]): z["faktor"] for z in baugruppe.richtwerte()["schweiss_faktoren"]}
assert rw[("Werkstoff", "Edelstahl")] == 1.3 and rw[("Werkstoff", "Stahl")] == rw[("Werkstoff", "Aluminium")] == 1.0
ok("W1 Faktor Werkstoff auf die Lichtbogenzeit, alter Stand ohne Faktor bitgleich, Richtwerte")


# ------------------------------------------------------------------ W2 Vorschlag Werkstoff
def gestell(werkstoff="1.4301", wand_naht=2, laenge=200):
    g = baugruppe.leer()
    g["id"] = "werkstoff01"
    g["naehte"] = [dict(id="n1", nr="1", verfahren="WIG", nahtart="Kehlnaht", mass=2, laenge=laenge, anzahl=8,
                        dicke=wand_naht)]
    pos = [dict(pos=1, art=BAUGRUPPE, bezeichnung="Gestell", stueck=5, baugruppe=baugruppe.speichern(g)),
           dict(pos=10, artikel="Holm", profil_id="QR 40x40x3", werkstoff_id=werkstoff, laenge=600,
                bg_knoten=g["id"], je_knoten=4)]
    return pos


pos = gestell()
erg = vorkalk.vorkalkulieren(pos[0], pos, TAB, None, k)
nt = erg["bg"]["naehte"][0]
assert nt["werkstoff"] == "Edelstahl" and vorkalk.naht_status(nt, "werkstoff") == vorkalk.VORSCHLAG
assert "Werkstoff der Teile: Edelstahl" in nt["vk"]["werkstoff"]["text"]
assert vorkalk.vorkalkulieren(pos[0], pos, TAB)["bg"]["naehte"][0].get("werkstoff") is None     # ohne Stammdaten
pos[0]["baugruppe"] = baugruppe.speichern(erg["bg"])
pos[1]["werkstoff_id"] = "S235-10219"
nt2 = vorkalk.vorkalkulieren(pos[0], pos, TAB, None, k)["bg"]["naehte"][0]
assert "werkstoff" not in nt2 and "werkstoff" not in nt2["vk"]
pos_st = gestell("S235-10219")
assert vorkalk.vorkalkulieren(pos_st[0], pos_st, TAB, None, k)["bg"]["naehte"][0].get("werkstoff") is None
ok("W2 Werkstoff Edelstahl aus den Teilen vorgeschlagen, bei Stahl keiner, Wechsel auf Stahl entfernt ihn")

# ------------------------------------------------------------------ W3 Beizen, Richten, Prüfen
pos = gestell()
erg = vorkalk.vorkalkulieren(pos[0], pos, TAB, None, k)
ag = {a["vk"]["art"]: a for a in erg["bg"]["arbeitsgaenge"]}
m = 8 * 0.2                                                          # 1,6 m Naht je Baugruppe
nah(ag["beizen"]["zeit_min"], m * 3.0, "Beizen 1,6 m × 3 min/m")
nah(ag["pruefen"]["zeit_min"], 1.0 + m * 0.3, "Sichtprüfung 1 + 1,6 × 0,3")
from rohrlaser import bg_mengen  # noqa: E402
g = bg_mengen.mengen(erg["bg"], pos, k)["gewicht"]                     # 4 × 0,6 m QR 40x40x3 ≈ 8 kg
assert 5 < g < 12, g
assert m / g >= 0.1                                                    # 0,2 m/kg ≥ 0,1, Wand 2 ≤ 3 → Richten
nah(ag["richten"]["zeit_min"], m * 2.0, "Richten 1,6 m × 2 min/m")
assert "m/kg" in ag["richten"]["vk"]["text"]
assert ag["beizen"]["satz_id"] == ag["pruefen"]["satz_id"] == "Schweißen"
dick = gestell(wand_naht=5)
assert "richten" not in {a["vk"]["art"] for a in vorkalk.vorkalkulieren(dick[0], dick, TAB, None, k)["bg"]["arbeitsgaenge"]}
wenig = gestell(laenge=20)                                              # 0,16 m ÷ 8 kg = 0,02 m/kg
assert "richten" not in {a["vk"]["art"] for a in vorkalk.vorkalkulieren(wenig[0], wenig, TAB, None, k)["bg"]["arbeitsgaenge"]}
pos_st = gestell("S235-10219")
arten = {a["vk"]["art"] for a in vorkalk.vorkalkulieren(pos_st[0], pos_st, TAB, None, k)["bg"]["arbeitsgaenge"]}
assert "beizen" not in arten and "pruefen" in arten
ok(f"W3 Beizen 4,8 min, Richten 3,2 min ({round(m / g, 2)} m/kg, Wand 2 mm), Sichtprüfung 1,48 min; Stahl ohne Beizen")

# ------------------------------------------------------------------ W4 ohne neue Regeln
alt_regeln = dict(TAB, schweiss_regeln=[z for z in TAB["schweiss_regeln"]
                                        if z["art"] not in ("Nachbehandlung", "Richten", "Prüfen")])
e = vorkalk.vorkalkulieren(pos[0], pos, alt_regeln, None, k)
assert not {"beizen", "richten", "pruefen"} & {a["vk"]["art"] for a in e["bg"]["arbeitsgaenge"]}
assert any("Beizen Edelstahl fehlt" in h for h in e["hinweise"]), e["hinweise"]
e = vorkalk.vorkalkulieren(pos_st[0], pos_st, alt_regeln, None, k)
assert not any("Beizen" in h or "Richten" in h or "Prüf" in h for h in e["hinweise"]), e["hinweise"]
ok("W4 ältere Regeln: keine neuen Vorschläge, Hinweis nur bei Edelstahl ohne Beiz-Regel")

# ------------------------------------------------------------------ W5 Editor
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser.stil import GELB_FLAECHE  # noqa: E402
eltern = QWidget()
eltern.k = k
pos = [dict(p, id=n) for n, p in enumerate(gestell(), 1)]
d = BaugruppeDialog(eltern, pos[0], pos, TAB, SAETZE)
vorher = d.erg["schweiss_min"]
d.vorkalkulation()
sp = [x.schluessel for x in d.naht_tab.spalten]
f = d.naht_tab.cellWidget(0, sp.index("werkstoff"))
assert f.currentText() == "Edelstahl" and GELB_FLAECHE in f.styleSheet()
nah(d.erg["schweiss_min"], vorher * 1.3, "Editor: Schweißzeit × 1,3")
assert {"beizen", "richten", "pruefen"} <= {(a.get("vk") or {}).get("art") for a in d.bg["arbeitsgaenge"]}
d.reject()
ok("W5 Editor: Werkstoff gelb vorgeschlagen, Schweißzeit × 1,3, Beizen/Richten/Prüfen als Arbeitsgänge")
print("Alle Werkstoff-Tests bestanden.")
