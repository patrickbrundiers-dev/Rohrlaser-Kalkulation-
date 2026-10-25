"""Steckverbindung (Plan K2-1): Rechenkern für Schlitze in der Aufnahme und Nasen am Ende des Steckers.
- S1 Beispiel aus dem Plan (QR 40 × 40 × 2 auf QR 40 × 40 × 2, bN 20, Spiel 0,1): Schlitz 20,2 × 2,2 mm, 44,8 mm je
  Schlitz, Aufnahme + 89,6 mm und + 2 Einstiche, Stecker-Ende 168 statt 160 mm, Länge + 2 mm.
- S2 Vorgaben aus den Einstellungen (halbe Wandbreite, mindestens 10 mm), Wände 'längs', 4 Nasen, Fehler.
- S3 Rundrohr (Aufnahme mit Sattel, Stecker mit Bogen-Nase) und schräger Stoß (Flanken und Schlitz länger).
- S4 Anwenden und Entfernen auf beiden Eingaben, Lage der Schlitze, erneutes Anwenden ersetzt.
- S6 Editor der Schweißbaugruppe: Reiter Steckverbindungen, hinzufügen, tauschen, Speichern schreibt Schlitze und
  Nasen in beide Teile (Schneidweg, Länge), Entfernen nimmt sie wieder heraus.
- S7 Alle Stöße stecken: der STEP-Import (JSON 1.18) kennt je Rohrende an Rohrwand die Lage („stoss“); der Knopf
  legt daraus die Verbindungen an, bei gleichen Teilen Schlitze nur einmal je Aufnahme und Nasen nur einmal je Ende.
- S8 Nasen nie in die Außenwand (Patrick 25.10.2026): bündig oben auf dem Träger passen die Nasen; am Ende eines
  Trägers nur die innere Nase (schmaler, wenn nötig); gleiche Teile an beiden Enden ohne gemeinsame Lage: keine Nasen;
  Quadratrohr auf Rundrohr: Nasen längs der Achse, nicht seitlich am Bogen.
- S5 Prüfung: Nase zu schmal (abschaltbar, ältere Datei bekommt die Regel), Steckverbindung ohne Gegenstück (FEHLER
  im Status der Baugruppe), Daten der Baugruppe.

Aufruf: python tests/test_steckverbindung.py
"""
import json
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import baugruppe as bgm, dfm, schneidweg as sw, steckverbindung as sv  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.01):
    return abs(a - b) <= tol


def fehler(f):
    try:
        f()
    except ValueError as x:
        return str(x)
    raise AssertionError("muss abgelehnt werden")


QR2 = dict(form="Quadratrohr", a=40, b=40, wand=2, profil_id="QR 40x40x2", r_aussen=0)
RR = dict(form="Rundrohr", a=60, wand=3, profil_id="RR 60x3")
RE = dict(form="Rechteckrohr", a=60, b=40, wand=3, profil_id="RE 60x40x3")
V = dict(id="sv1", aufnahme=dict(pos=10, knoten=""), stecker=dict(pos=20, knoten="", ende="a"), x=300,
         seite="oben", anzahl=2, bN=20, c=0.1, ueberstand=0, waende="quer", winkel=90)
LEER = dict(a={}, b={}, konturen=[])

# ------------------------------------------------------------------ S1 Beispiel 5.2
m = sv.masse(V, QR2, QR2)
assert nah(m["schlitz_l"], 2.2) and nah(m["schlitz_b"], 20.2) and nah(m["schlitz"], 44.8)
assert nah(m["aufnahme_plus"], 89.6) and m["einstiche_plus"] == 2
assert nah(m["ende_plus"], 8) and nah(m["laenge_plus"], 2) and nah(m["lN"], 2)
auf, st, dl = sv.anwenden(V, LEER, LEER, QR2, QR2)
assert dl == 2
r0_a, r0_s = sw.rechnen(LEER, QR2, (10, 50)), sw.rechnen(LEER, QR2, (10, 50))
ra, rs = sw.rechnen(auf, QR2, (10, 50)), sw.rechnen(st, QR2, (10, 50))
assert not ra["fehler"] and not rs["fehler"], (ra["fehler"], rs["fehler"])
assert nah(ra["schneidweg"] - r0_a["schneidweg"], 89.6, 0.06) and ra["einstiche"] == r0_a["einstiche"] + 2
assert nah(rs["felder"]["a_schnitt"], 168) and nah(r0_s["felder"]["a_schnitt"], 160)
assert rs["felder"]["a_gerade"] == "nein" and "2 Nasen 20 × 2 (Steckverbindung)" in rs["schritte"][0]["text"]
assert any("2 mm länger" in h for h in rs["hinweise"])
ok("S1 Beispiel: Schlitz 20,2 × 2,2 = 44,8 mm, Aufnahme + 89,6 mm + 2 Einstiche, Ende 168 mm, Länge + 2 mm")

# ------------------------------------------------------------------ S2 Vorgaben, Wände, Fehler
vg = sv.vorgaben(QR2)
assert vg["anzahl"] == 2 and vg["bN"] == 20 and vg["c"] == 0.1 and vg["ueberstand"] == 0 and vg["winkel"] == 90
assert sv.vorgaben(dict(QR2, a=16, b=16, wand=1.5))["bN"] == 10            # mindestens 10 mm
assert sv.vorgaben(RE)["bN"] == 30 and sv.vorgaben(RE, waende="längs")["bN"] == 20
e = sv.vorgaben(QR2, dict(anzahl=4, spiel=0.2, ueberstand=1, nase_min=25))
assert e["anzahl"] == 4 and e["c"] == 0.2 and e["ueberstand"] == 1 and e["bN"] == 25
m = sv.masse(dict(V, waende="längs"), QR2, QR2)
assert nah(m["schlitz_l"], 20.2) and nah(m["schlitz_b"], 2.2) and m["nasen"] == [(0.0, 19.0), (0.0, -19.0)]
m4 = sv.masse(dict(V, anzahl=4), QR2, QR2)
assert m4["einstiche_plus"] == 4 and nah(m4["aufnahme_plus"], 4 * 44.8) and nah(m4["ende_plus"], 16)
assert {(round(dx, 1), round(dq, 1)) for dx, dq in m4["nasen"]} == {(19, 0), (-19, 0), (0, 19), (0, -19)}
m = sv.masse(dict(V, ueberstand=1), QR2, QR2)
assert nah(m["lN"], 3) and nah(m["ende_plus"], 12) and nah(m["schlitz_l"], 2.2)    # Überstand ändert den Schlitz nicht
assert "1, 2 oder 4" in fehler(lambda: sv.masse(dict(V, anzahl=3), QR2, QR2))
# größte Nase (Patrick 25.10.2026 „c“): gerade Wandfläche − 2 × Rand; QR 40 × 2 mit R 4 (EN): 40 − 8 − 4 = 28 mm
Q = dict(QR2, r_aussen=None)
assert nah(sv.nase_max(Q), 28) and nah(sv.nase_max(Q, rand=0), 32) and nah(sv.nase_max(dict(Q, r_aussen=2)), 32)
assert nah(sv.nase_max(QR2), 36)            # scharfkantig: höchstens die Wand innen (40 − 2 × 2)
m = sv.masse(dict(V, bN=37), QR2, Q)
assert nah(m["bN"], 28) and m["gekuerzt"] == 28 and nah(m["schlitz_b"], 28.2) and "gekürzt" in sv.text(dict(V, bN=37), m)
assert sv.masse(dict(V, bN=20), QR2, Q)["gekuerzt"] is None
assert nah(sv.masse(dict(V, bN=37, rand=5), QR2, Q)["bN"], 22)
assert nah(sv.vorgaben(Q, dict(nase_min=35))["bN"], 28) and sv.vorgaben(Q)["rand"] == 2.0
assert nah(sv.vorgaben(Q, dict(nase_min=35, nase_rand=1))["bN"], 30)
assert nah(sv.nase_max(RR), 56)
assert "zu schmal" in fehler(lambda: sv.masse(dict(V, rand=20), QR2, Q))
assert "30° bis 90°" in fehler(lambda: sv.masse(dict(V, winkel=20), QR2, QR2))
assert "Rundrohr sein" in fehler(lambda: sv.masse(V, dict(form="Flachstahl", a=40, wand=5), QR2))
assert "Ende des Steckers" in fehler(lambda: sv.anwenden(dict(V, stecker={}), LEER, LEER, QR2, QR2))
ok("S2 Vorgaben (halbe Wand, min. 10 mm, Einstellungen), Wände längs, 4 Nasen, größte Nase gekürzt, Fehler")

# ------------------------------------------------------------------ S3 Rundrohr und schräg
m = sv.masse(dict(V, bN=30), RR, RR)               # Stecker RR 60 × 3: Bogenhöhe der Nase über der Sehne 30
bogen = 30 - math.sqrt(30 ** 2 - 15 ** 2)
assert nah(m["staerke"], 3 + bogen) and nah(m["schlitz_l"], 3 + bogen + 0.2)
assert nah(m["schlitz_b"], 2 * 30 * math.asin(30.2 / 60))       # auf dem Bogen der Aufnahme
z = sv.schlitz_zeilen(dict(V, waende="längs", seite="oben (0°)"), RR, QR2)
assert {x["seite"] for x in z} == {f"{round(math.degrees(19 / 30), 1):g}°", f"{round(360 - math.degrees(19 / 30), 1):g}°"}
assert all("q" not in x for x in z)
st = sv.anwenden(dict(V, bN=30), LEER, dict(a=dict(sattel=60), b={}, konturen=[]), RR, RR)[1]
rs = sw.rechnen(st, RR, (10, 50))
r0 = sw.rechnen(dict(a=dict(sattel=60), b={}, konturen=[]), RR, (10, 50))
assert not rs["fehler"] and nah(rs["felder"]["a_schnitt"] - r0["felder"]["a_schnitt"], 4 * 3)
m = sv.masse(dict(V, winkel=60), QR2, QR2)
s60, t60 = math.sin(math.radians(60)), math.tan(math.radians(60))
assert nah(m["flanke"], 2 / s60) and nah(m["ende_plus"], 8 / s60) and nah(m["laenge_plus"], 2 / s60)
assert nah(m["schlitz_l"], 2 / s60 + 2 / t60 + 0.2) and nah(m["nasen"][0][0], 19 / s60)
assert "schräg 60°" in sv.text(dict(V, winkel=60))
ok("S3 Rundrohr (Bogen-Nase, Schlitz auf dem Bogen, Sattel + Nasen) und schräger Stoß 60°")

# ------------------------------------------------------------------ S4 Anwenden, Entfernen
alt = dict(a={}, b=dict(winkel=45), konturen=[dict(art="Bohrung", anzahl=1, d=8, x=100)])
auf, st, dl = sv.anwenden(V, alt, alt, QR2, QR2)
assert [z_["x"] for z_ in auf["konturen"][1:]] == [319, 281] and auf["konturen"][1]["seite"] == "oben"
assert all(z_["quelle"] == "Steckverbindung sv1" for z_ in auf["konturen"][1:]) and auf["konturen"][0]["d"] == 8
assert st["a"]["nasen"]["id"] == "sv1" and st["b"] == dict(winkel=45) and alt["konturen"][1:] == []
auf2, st2, dl2 = sv.anwenden(dict(V, bN=16, x=200), auf, st, QR2, QR2)     # ersetzt die eigenen Zeilen
assert len(auf2["konturen"]) == 3 and dl2 == 0 and auf2["konturen"][1]["h"] == 16.2
st3 = sv.anwenden(dict(V, stecker=dict(V["stecker"], ende="b")), auf2, st2, QR2, QR2)[1]
assert "nasen" not in st3["a"] and st3["b"]["nasen"]["id"] == "sv1" and st3["b"]["winkel"] == 45
ohne_a, w_a = sv.entfernen(auf2, "sv1")
ohne_s, w_s = sv.entfernen(st3, "sv1")
assert ohne_a["konturen"] == alt["konturen"] and w_a == 0 and w_s == 2 and ohne_s["b"] == dict(winkel=45)
assert sv.rollen(sw.speichern(auf2)) == {"sv1": {"aufnahme"}} and sv.rollen(sw.speichern(st3)) == {"sv1": {"stecker"}}
ok("S4 Anwenden auf beide Teile (Lage x ± 19 mm), erneut anwenden ersetzt, Ende tauschen, Entfernen")

# ------------------------------------------------------------------ S5 Prüfung und Baugruppe
schmal = sv.anwenden(dict(V, bN=5), LEER, LEER, QR2, QR2)[1]
p_s = dict(technik=sw.speichern(schmal), laenge=500)
b = {x.regel: x for x in dfm.rohr(p_s, QR2)}
assert b[dfm.NASE_SCHMAL].stufe == dfm.WARNUNG and "Nase 5 mm unter 3 × Wand (6 mm)" in b[dfm.NASE_SCHMAL].text
p_ok = dict(technik=sw.speichern(sv.anwenden(V, LEER, LEER, QR2, QR2)[1]), laenge=500)
assert dfm.NASE_SCHMAL not in {x.regel for x in dfm.rohr(p_ok, QR2)}
assert dfm.NASE_SCHMAL not in {x.regel for x in dfm.rohr(p_s, QR2, zeilen=[dict(regel=dfm.NASE_SCHMAL, aktiv="nein")])}
bg = bgm.leer()
bg["steckverbindungen"] = [V]
auf, st, _ = sv.anwenden(V, LEER, LEER, QR2, QR2)
kopf = dict(art="Baugruppe", stueck=1, baugruppe=bgm.speichern(bg), pos=1)
teil_a = dict(pos=10, stueck=1, je_satz=1, bg_knoten=bgm.zuordnung_text(bg["id"]), technik=sw.speichern(auf))
teil_s = dict(pos=20, stueck=1, je_satz=1, bg_knoten=bgm.zuordnung_text(bg["id"]), technik=sw.speichern(st))
pos = [kopf, teil_a, teil_s]
assert bgm.lesen(kopf["baugruppe"])["steckverbindungen"][0]["id"] == "sv1"
assert sv.teile_finden(pos, bgm.teile(pos, bg["id"]), "sv1") == (1, 2)
assert sv.fehler(bg, pos, bgm.teile(pos, bg["id"])) is None
assert "Steckverbindung" not in bgm.status(kopf, {}, pos)
t = bgm.status(kopf, {}, [kopf, teil_a])
assert t == "FEHLER: Steckverbindung 1 ohne Gegenstück (Stecker nicht in der Baugruppe)", t
d = json.loads(kopf["baugruppe"])
d["steckverbindungen"] = [V, dict(V)]
assert "Steckverbindung Nr. 2 hat eine doppelte Kennung (sv1)" in bgm.daten_fehler(json.dumps(d))
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert dfm.NASE_SCHMAL in {z["regel"] for z in db.zeilen("pruefregeln")}
assert db.einstellung("steck_anzahl") == 2 and db.einstellung("steck_spiel") == 0.1
db.con.execute("DELETE FROM pruefregeln WHERE regel=?", (dfm.NASE_SCHMAL,))
db.con.execute("DELETE FROM einstellungen WHERE name='steck_stand'")
db.con.commit()
db.schliessen()
db = Datenbank(tmp / "rohrlaser.db")
assert dfm.NASE_SCHMAL in {z["regel"] for z in db.zeilen("pruefregeln")}
db.schliessen()
ok("S5 Nase zu schmal (abschaltbar, ältere Datei ergänzt), ohne Gegenstück = FEHLER, Daten der Baugruppe")

# ------------------------------------------------------------------ S6 Editor der Schweißbaugruppe
import os  # noqa: E402
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.angebot import ist_baugruppe  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
a = db.angebot_neu(dict(kunde="Test"))
r_a = db.position_neu(a, dict(pos=10, artikel="Holm", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800,
                              stueck=1))
r_s = db.position_neu(a, dict(pos=20, artikel="Strebe", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=400,
                              stueck=1))
seite = f.angebot_oeffnen(a)
vorher = {q["id"]: q for q in db.positionen(a)}
seite.schneidweg_berechnen(next(i for i, q in enumerate(seite.positionen) if q["id"] == r_a), dict(LEER),
                           ueberschreiben=True)
seite.schneidweg_berechnen(next(i for i, q in enumerate(seite.positionen) if q["id"] == r_s), dict(LEER),
                           ueberschreiben=True)
vorher = {q["id"]: q for q in db.positionen(a)}
gesehen = {}


def dialog(d):
    d.teil_setzen(r_a, True)
    d.teil_setzen(r_s, True)
    vid = d.steck_neu(r_s, r_a, x=1, seite="oben")         # erst falsch herum, dann tauschen
    d.steck_tauschen([0])
    z = d.bg["steckverbindungen"][0]
    gesehen.update(auf=z["_auf"], st=z["_st"], fehler=d._steck_fehler(z), vid=vid)
    z["x"], z["seite"] = 300.0, "vorne"
    gesehen["text"] = d._steck_text(z, 0)
    d._ok()
    return d.result()


assert seite.baugruppe_neu(dialog=dialog)
assert gesehen["auf"] == r_a and gesehen["st"] == r_s and gesehen["fehler"] == "Lage x auf der Aufnahme fehlt", gesehen
assert "Schlitz 3,2 × 20,2 mm" in gesehen["text"], gesehen
pos = {q["id"]: q for q in db.positionen(a)}
ea, es = sw.lesen(pos[r_a]["technik"]), sw.lesen(pos[r_s]["technik"])
assert [z["x"] for z in ea["konturen"]] == [318.5, 281.5] and {z["seite"] for z in ea["konturen"]} == {"vorne"}
assert nah(pos[r_a]["schneidweg"] - vorher[r_a]["schneidweg"], 93.6, 0.06)
assert pos[r_a]["einstiche"] == vorher[r_a]["einstiche"] + 2
assert es["a"]["nasen"]["id"] == gesehen["vid"] and pos[r_s]["laenge"] == 403
assert nah(pos[r_s]["a_schnitt"] - vorher[r_s]["a_schnitt"], 12, 0.06)
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402
for rid in (r_a, r_s):          # Teile-Editor: Schlitze (Herkunft) und Nasen bleiben beim Übernehmen
    d = SchneidwegDialog(seite, pos[rid], seite.k.profile["QR 40x40x3"], seite.kopf, seite.k, seite.tabellen)
    e = d.eingaben()
    if rid == r_a:
        assert [z.get("quelle") for z in e["konturen"]] == [ea["konturen"][0]["quelle"]] * 2, e["konturen"]
    else:
        assert e["a"]["nasen"] == es["a"]["nasen"] and "Nasen" in d.gemessen_text["a"].text()
    d.reject()
bg_pos = next(q for q in pos.values() if ist_baugruppe(q))
bg = bgm.lesen(bg_pos["baugruppe"])
assert bg["steckverbindungen"][0]["aufnahme"]["id"] == r_a and bg["steckverbindungen"][0]["stecker"]["ende"] == "a"
assert "Steckverbindung" not in bgm.status(bg_pos, {}, list(pos.values()))
i = next(i for i, q in enumerate(seite.positionen) if ist_baugruppe(q))


def weg(d):
    d.steck_tab.selectRow(0)
    d._entfernen(d.bg["steckverbindungen"], d.steck_tab)
    d._ok()
    return d.result()


assert seite.baugruppe_bearbeiten([i], dialog=weg)
pos = {q["id"]: q for q in db.positionen(a)}
assert not sw.lesen(pos[r_a]["technik"])["konturen"] and "nasen" not in sw.lesen(pos[r_s]["technik"])["a"]
assert pos[r_s]["laenge"] == 400 and nah(pos[r_a]["schneidweg"], vorher[r_a]["schneidweg"], 0.06)
assert not bgm.lesen(next(q for q in pos.values() if ist_baugruppe(q))["baugruppe"]).get("steckverbindungen")
db.schliessen()
ok("S6 Editor: hinzufügen, tauschen, Speichern schreibt Schlitze (x ± 18,5) und Nasen (+3 mm), Entfernen")

# ------------------------------------------------------------------ S7 Alle Stöße stecken (STEP)
sys.path.insert(0, str(Path(__file__).parent.parent / "programm" / "step_messung"))
import step_messen  # noqa: E402
from rohrlaser import step  # noqa: E402
from rohrlaser.ansicht3d import entpacken  # noqa: E402

datei = Path(__file__).parent / "step_struktur" / "S03_Rahmen_geschweisst.step"
tmp = Path(tempfile.mkdtemp())
step_messen.main(["--ausgabe", str(tmp / "m.txt"), "--json", str(tmp / "m.json"), "--netze", str(tmp / "netze"),
                  str(datei)])
js = json.loads((tmp / "m.json").read_text(encoding="utf-8"))
stoss = [k["stoss"] for k in js["dateien"][0]["nahtkandidaten"] if k.get("stoss")]
assert js["schema_version"] >= "1.18" and len(stoss) == 4, stoss
assert {(x["stecker"], x["ende"], x["aufnahme"], x["z"], x["seite"], x["achswinkel"]) for x in stoss} == {
    (3, "a", 1, 200.0, "0°", 90.0), (4, "a", 1, 800.0, "0°", 90.0), (3, "b", 2, 200.0, "180°", 90.0),
    (4, "b", 2, 800.0, "180°", 90.0)}, stoss
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(tmp / "m.txt"), tmp / "netze"), tmp / "m.json")
for x in mw:
    x.update(_saetze=1, _stueck=1, _baugruppe=True, _uebernehmen=True)
db = Datenbank(tmp / "stoss.db")
k = db.kontext()
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True, zukauf_liste=[])
db.profile_anlegen(erg["profile"])
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for q in erg["positionen"]:
    netz = q.pop("_netz", None)
    q.pop("_zukauf", None)
    pid = db.position_neu(a, q)
    if netz:
        db.netz_speichern(pid, netz)
pos = {q["id"]: q for q in db.positionen(a)}
bg_pos = next(q for q in pos.values() if ist_baugruppe(q))
assert len(bgm.lesen(bg_pos["baugruppe"])["stoesse"]) == 4
netze = db.netze(a)
rolle = {}
for pid, q in pos.items():
    for kn in (entpacken(netze[pid]) or {}).get("koerper") or () if pid in netze else ():
        rolle[kn] = pid
holm, strebe = rolle["1"], rolle["3"]
assert rolle["2"] == holm and rolle["4"] == strebe
f = Hauptfenster(db, stumm=True)
seite = f.angebot_oeffnen(a)
vorher = {q["id"]: q for q in db.positionen(a)}
gesehen = {}


def stecken(d):
    gesehen["erg"] = d.steck_alle(melden=False)
    gesehen["zeilen"] = [(z["_auf"], z["_st"], z["_ende"], z["x"], z.get("seite"), z["_schlitze"], z["_nasen"])
                         for z in d.bg["steckverbindungen"]]
    gesehen["fehler"] = [d._steck_fehler(z) for z in d.bg["steckverbindungen"]]
    gesehen["nochmal"] = d.steck_alle(melden=False)
    gesehen["lagen"] = {str(k): {str(n): w for n, w in v.items()} for k, v in getattr(d, "steck_lagen", {}).items()}
    d._ok()
    return d.result()


i = next(i for i, q in enumerate(seite.positionen) if ist_baugruppe(q))
assert seite.baugruppe_bearbeiten([i], dialog=stecken)
assert gesehen["erg"] == (3, 0) and gesehen["nochmal"] == (0, 0), gesehen
assert gesehen["zeilen"] == [(holm, strebe, "a", 200.0, "oben", True, True),
                             (holm, strebe, "a", 800.0, "oben", True, False),
                             (holm, strebe, "b", 200.0, "oben", False, True)], gesehen["zeilen"]
# der zweite Holm war um 180° gedreht eingebaut: seine Einbaulage wird gedreht, statt das gleiche Teil zu teilen
from rohrlaser.ansicht3d import entpacken
netz_h = entpacken(db.netz(holm))
assert len(netz_h["lagen"]) == 2 and netz_h["lagen"][1] == gesehen["lagen"][str(holm)][str(netz_h["koerper"][1])], netz_h
assert gesehen["fehler"] == [None, None, None], gesehen["fehler"]
pos = {q["id"]: q for q in db.positionen(a)}
eh, est = sw.lesen(pos[holm]["technik"]), sw.lesen(pos[strebe]["technik"])
schlitze = [z for z in eh["konturen"] if str(z.get("quelle", "")).startswith("Steckverbindung")]
assert len(schlitze) == 4 and {z.get("seite", "oben") for z in schlitze} == {"oben"}, schlitze
assert sorted(round(z["x"]) for z in schlitze)[0] < 200 < sorted(round(z["x"]) for z in schlitze)[1]
assert est["a"].get("nasen") and est["b"].get("nasen")
lN = est["a"]["nasen"]["lN"]
assert nah(pos[strebe]["laenge"] - vorher[strebe]["laenge"], 2 * lN, 0.01), (pos[strebe]["laenge"], lN)
assert pos[holm]["einstiche"] == vorher[holm]["einstiche"] + 4
assert "Steckverbindung" not in bgm.status(next(q for q in pos.values() if ist_baugruppe(q)), {}, list(pos.values()))
db.schliessen()
ok("S7 Alle Stöße stecken: 4 Stöße aus STEP (JSON 1.18), 3 Verbindungen, Holm 4 Schlitze oben, Strebe Nasen an A und E")

# ------------------------------------------------------------------ S8 Nasen nur in die Stoßwand
RE140 = dict(form="Rechteckrohr", a=140, b=80, wand=5, profil_id="RE 140x80x5")
RE80 = dict(form="Rechteckrohr", a=80, b=40, wand=3, profil_id="RE 80x40x3")
QR100 = dict(form="Quadratrohr", a=100, b=100, wand=5, profil_id="QR 100x100x5")
QR40 = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")
RR42 = dict(form="Rundrohr", a=42.4, wand=2.6, profil_id="RR 42,4x2,6")
bündig = dict(profil_a=RE140, w=648, q=30, laenge=3000, halb=70, quer=(80, 40), phi=0)
w_, seiten, hinweis = sv.nasen_wahl(sv.vorgaben(RE80), RE80, [bündig])
assert w_["waende"] == "quer" and w_["anzahl"] == 2 and hinweis is None, (w_, hinweis)
assert sv.nasen_wahl(dict(sv.vorgaben(RE80), waende="längs"), RE80, [bündig])[0]["waende"] == "quer"    # längs: oben raus
ecke = dict(profil_a=RE140, w=50, q=10, laenge=3000, halb=40, quer=(100, 100), phi=-90)
w_, seiten, hinweis = sv.nasen_wahl(sv.vorgaben(QR100), QR100, [ecke])
assert w_["anzahl"] == 1 and seiten == [1] and w_["bN"] <= 2 * (40 - 10 - 2 - 10 - 0.1) and "nur eine Nase" in hinweis
v1 = dict(sv.vorgaben(QR100), id="e", **w_, nase_seite=-1 if seiten[0] < 0 else 1)
assert sv.masse(v1, RE140, QR100)["nasen"][0][0] > 0            # die Nase zur Mitte des Trägers
andere_ecke = dict(ecke, w=2950)
w_, seiten, hinweis = sv.nasen_wahl(sv.vorgaben(QR100), QR100, [andere_ecke])
assert w_["anzahl"] == 1 and seiten == [-1]
assert sv.masse(dict(sv.vorgaben(QR100), id="e", **w_, nase_seite=-1), RE140, QR100)["nasen"][0][0] < 0
assert sv.nasen_wahl(sv.vorgaben(QR100), QR100, [ecke, andere_ecke])[0] is None      # gleiche Teile, beide Enden
rund = dict(profil_a=RR42, w=702.5, q=0, laenge=1426, halb=21.2, quer=(40, 40), phi=0)
w_, _, hinweis = sv.nasen_wahl(dict(sv.vorgaben(QR40), waende="längs"), QR40, [rund])
assert w_["waende"] == "quer" and w_["anzahl"] == 2 and "90°" in hinweis, (w_, hinweis)
# Ecke: Stütze unter zwei Trägern -> je Träger eine Nase, um 90° versetzt, nie zwei auf derselben Wand
traeger1 = dict(profil_a=RE140, w=50, q=10, laenge=3000, halb=40, quer=(100, 100), phi=0)
traeger2 = dict(profil_a=RE140, w=2950, q=10, laenge=3000, halb=40, quer=(100, 100), phi=90)
wahl, hinweis = sv.nasen_wahl_ecke(sv.vorgaben(QR100), QR100, [traeger1, traeger2])
assert [x["anzahl"] for x in wahl] == [1, 1] and wahl[0]["traegt"] and not wahl[1]["traegt"], wahl
assert sv.versatz_liste(wahl[0]) and "90°" in hinweis, (wahl, hinweis)
menge = sv.nasen_winkel_menge(wahl[0], 0, "Quadratrohr")
assert len(menge) == 2 and (menge[1] - menge[0]) % 180 == 90, menge
# gleiche Rohre gedreht/gewendet eingebaut: Kennung im gedrehten Rohrsystem gleich, Einbaulage passend gedreht
z1 = [dict(art="Rechteck", b=3, h=20, x=200.0, seite="oben"), dict(art="Rechteck", b=3, h=20, x=800.0, seite="oben")]
z2 = [dict(z, seite="unten") for z in z1]
z3 = [dict(art="Rechteck", b=3, h=20, x=300.0, seite="vorne")]
k1 = sv.gleich_lagen(None, None, z1, 1000, "Rechteckrohr")
assert k1[0][0] in {k for k, _, _ in sv.gleich_lagen(None, None, z2, 1000, "Rechteckrohr")}
treffer = next((d, w) for k, d, w in sv.gleich_lagen(None, None, [dict(z3[0], seite="hinten", x=700.0)], 1000,
                                                    "Quadratrohr", True)
               if k == sv.gleich_lagen(None, None, z3, 1000, "Quadratrohr", True)[0][0])
assert sv.seite_drehen("hinten", *treffer) == "vorne", treffer
lage = [0, 0, 0, 1, 0, 0, 0, 1, 0]          # Ende A im Ursprung, Achse X, Rohr-X = Welt-Y
assert sv.lage_drehen(lage, 0, True, 1000)[:6] == [1000, 0, 0, -1, 0, 0]
assert [round(v, 6) for v in sv.lage_drehen(lage, 180, False, 1000)[6:]] == [0, -1, 0]
assert len(sv.gleich_lagen(None, None, [dict(z1[0], q=5)], 1000, "Rechteckrohr")) == 1      # Querversatz: nicht drehen
ok("S8 Nasen nur in die Stoßwand: bündig quer, Ecke nur die innere Nase, gleiche Teile ohne gemeinsame Lage ohne "
   "Nasen, auf Rundrohr längs der Achse, Ecke je Träger eine Nase um 90° versetzt, gedreht eingebaute gleiche Rohre")
print("Alle Steckverbindungs-Tests bestanden.")
