"""Prüft Musterteile im Angebot (Patrick 28.10.2026, Plan „Musterteile im Angebot“, Freigabe „Alle a“):
- K1 Musterpositionen voll gerechnet, Preis 0, Verkaufswert mit Gewinn nach Selbstkosten auf die Serie umgelegt
  (Summe des Angebots und Gewinn gleich, keine Minusmarge), Kostenarten gehen auf.
- K2 eigener Lauf: Musterteile nie mit Serienteilen auf einer Stange, Material nur nach belegter Länge, eigenes
  Rüsten der Maschine und je Abmessung.
- K3 eigene Zeile „Musterkosten einmalig“ (Kopf) und automatisch ohne Serienposition.
- K4 Mindestauftragswert mit Musterteilen.
- K5 Staffeln: Musterkosten einmal je Stufe wie Rüsten; Stufe mit den Mengen des Angebots = Angebot.
- K6 Angebot/PDF/CSV: Vermerk an den Mustern, eigene Zeile, Hinweis falls keine Serie bestellt wird.
- K7 Oberfläche: Spalte Muster, Rechtsklick „Muster an/aus“ (Satz ganz), Musterkosten im Kopf, Häkchen in Rohr-,
  Blech-, Baugruppen-Editor und „Satz in 3D“, Kompaktansicht.

Aufruf: python tests/test_musterteile.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import beispiel_angebot as B  # noqa: E402
from rohrlaser import ausgabe, export, pdf, rechnen, staffeln  # noqa: E402
from rohrlaser.angebot_spalten import kompakt_zeilen, muster_info  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import MUSTER_ZEILE  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=1e-6):
    return a is not None and abs(a - b) <= tol


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
a = B.anlegen(db)
MUSTER = ((60, "QR 40x40x3", 480, 2), (70, "RR 48,3x2,6", 900, 2), (80, "RE 60x40x3", 650, 1))
for nr, prof, laenge, st in MUSTER:
    db.position_neu(a, dict(pos=nr, artikel=f"M{nr}", bezeichnung="Muster", profil_id=prof,
                            werkstoff_id="S235-10219", laenge=laenge, stueck=st, schneidweg=400, einstiche=3))
k, tab = db.kontext(), db.tabellen()
kopf, pos = db.angebot(a), db.positionen(a)
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
M_POS = {nr for nr, *_ in MUSTER}


def mit_muster(positionen, nummern=M_POS):
    return [dict(p, muster="ja") if p["pos"] in nummern else p for p in positionen]


def kalk(positionen, kopf_=None, einst_=None):
    kp = kopf_ or kopf
    e = einst_ or einst
    erg = rechnen.optimieren(kp, positionen, k, tab, e)
    z, s = rechnen.kalkulation(kp, positionen, erg, k, tab, e)
    return z, s, erg


def kosten_gehen_auf(s):
    """Herstellkosten + … + Mindestpreis = Verkaufspreis (keine Kostenart doppelt, keine fehlt)."""
    teile = [w for (t, w, _), (_, n, _) in zip(rechnen.kostenarten(s, einst), rechnen.KOSTENARTEN)
             if n in ("herstell", "gewinn", "pauschalen", "programmierung", "angebotsaufschlag", "fracht",
                      "zukauf_einstand", "zukauf_aufschlag", "skonto", "mindestpreis_anhebung")]
    return nah(sum(teile), s["verkauf"], 1e-6)


# ------------------------------------------------------------------ K1 Umlage auf die Serie
z0, s0, e0 = kalk(pos)
pm = mit_muster(pos)
z1, s1, e1 = kalk(pm)
assert s0.get("muster_positionen") == 0 and not any(z.get("muster_teil") for z in z0 if z)
assert s1["muster_positionen"] == 3 and not s1["muster_zeile"] and s1["muster_einmalig"] == 0
muster = [z for z in z1 if z and z.get("muster") == "ja"]
serie = [z for z in z1 if z and z.get("muster") != "ja"]
assert len(muster) == 3 and all(z["preis_teil"] == 0 and z["preis_position"] == 0 for z in muster)
assert all(z["selbst_teil"] > 0 and z["gewinn_teil"] > 0 and z["muster_preis_teil"] > z["selbst_teil"] for z in muster)
betrag = sum(z["muster_preis_position"] for z in muster)
assert nah(betrag, s1["muster_betrag"]) and betrag > 0
umgelegt = sum(z["muster_teil"] * z["stueck"] for z in serie)
assert nah(umgelegt, betrag, 1e-6)
# nach Selbstkosten verteilt (F2 a)
w = sum(z["selbst_position"] for z in serie)
assert all(nah(z["muster_teil"] * z["stueck"], betrag * z["selbst_position"] / w, 1e-9) for z in serie)
# Summe gleich: Verkaufswert der Muster geht vollständig in die Serie, Gewinn der Muster bleibt (F3 a)
assert nah(s1["verkauf"], sum(z["preis_position"] - z["muster_teil"] * z["stueck"] for z in serie) + betrag, 1e-6)
assert s1["gewinn"] > s0["gewinn"] and nah(s1["gewinn"], sum(z["gewinn_teil"] * z["stueck"] for z in z1 if z))
assert s1["verkauf"] - s1["selbst"] >= s1["gewinn"] - 1e-6        # nie Minusmarge
assert kosten_gehen_auf(s0) and kosten_gehen_auf(s1)
text = next(t for t, _, _ in rechnen.kostenarten(s1, einst) if t.startswith("Verkaufspreis"))
assert "davon Musterteile" in text and "auf die Serie umgelegt" in text, text
ok(f"K1 3 Muster mit 0 €, Wert {betrag:.2f} € nach Selbstkosten auf die Serie, Summe {s1['verkauf']:.2f} € = "
   "Serie + Musterwert, Gewinn der Muster bleibt")

# ------------------------------------------------------------------ K2 eigener Lauf
ms = [s for s in e1["stangen"] if s.get("muster")]
assert len(ms) == 3 and all(t["pos"] in M_POS for s in ms for t in s["teile"])
assert all(t["pos"] not in M_POS for s in e1["stangen"] if not s.get("muster") for t in s["teile"])
sw = rechnen.stangen_werte(e1, kopf, pm, k, tab)
for s, x in zip(e1["stangen"], sw):
    if s.get("muster"):
        assert x["kosten_voll"] > x["kosten"] > 0 and nah(x["kosten"], x["kosten_voll"] * x["belegt"] / s["stange"])
    else:
        assert "kosten_voll" not in x
assert s1["laeufe"] == 2 and s0["laeufe"] == 1
assert nah(s1["ruesten_maschine"], 2 * s0["ruesten_maschine"]) and nah(s1["ruestzeit"], 2 * s0["ruestzeit"])
assert s1["abmessungen"] == s0["abmessungen"] + 3        # Muster je Abmessung eigens gerüstet
assert "2 Läufe" in next(t for t, _, _ in rechnen.kostenarten(s1, einst) if t.startswith("Rüsten Maschine"))
# Stangen der Serie wie ein Angebot ganz ohne die Muster
_, _, e_ohne = kalk([p for p in pos if p["pos"] not in M_POS])
assert [[t["pos"] for t in s["teile"]] for s in e_ohne["stangen"]] == \
    [[t["pos"] for t in s["teile"]] for s in e1["stangen"] if not s.get("muster")]
ok(f"K2 eigener Lauf: {len(ms)} Musterstangen getrennt, Material nur belegte Länge, Rüsten Maschine × 2, "
   f"{s1['abmessungen']} Abmessungen")

# ------------------------------------------------------------------ K3 eigene Zeile
kz = dict(kopf, muster_darstellung=MUSTER_ZEILE)
z2, s2, _ = kalk(pm, kz)
assert s2["muster_zeile"] and nah(s2["muster_einmalig"], s2["muster_betrag"]) and nah(s2["verkauf"], s1["verkauf"])
for a1, a2 in zip(z1, z2):
    if a1 and a1.get("muster") != "ja":
        assert nah(a2["preis_teil"], a1["preis_teil"] - a1["muster_teil"]) and not a2.get("muster_teil")
        assert nah(a2["muster_getrennt_selbst_teil"], a1["muster_selbst_teil"])
assert nah(sum(z["muster_einmal_position"] for z in z2 if z and z.get("muster") == "ja"), s2["muster_einmalig"])
assert kosten_gehen_auf(s2)
nur = [p for p in pm if p["pos"] in M_POS]
z3, s3, _ = kalk(nur)
assert s3["muster_zeile"] and s3["muster_ohne_serie"] and nah(s3["verkauf"], s3["muster_einmalig"]) and s3["verkauf"] > 0
assert "keine Serienposition" in rechnen.muster_text(s3)
ok(f"K3 eigene Zeile: Serie ohne Umlage, Musterkosten einmalig {s2['muster_einmalig']:.2f} €; ohne Serie automatisch")

# ------------------------------------------------------------------ K4 Mindestauftragswert
klein = [p for p in pm if p["pos"] in (50, 60)]
klein = [dict(p, stueck=2) if p["pos"] == 50 else p for p in klein]
for kp in (kopf, kz):
    zm, sm, _ = kalk(klein, kp, dict(einst, mindestpreis=500))
    sk = 1 - sm["skonto_satz"] / 100       # Mindestpreis gilt für die Ware ohne Fracht nach Skonto
    ware = sum(z["preis_teil"] * sk * z["stueck"] - z["fracht_teil"] * z["stueck"] for z in zm if z) + (
        sm["muster_einmalig"] * sk - sum(z["muster_fracht_teil"] * z["stueck"] for z in zm if z and z.get("muster"))
        if sm["muster_zeile"] else 0)
    assert sm["mindestpreis_gilt"] and nah(ware, 500, 1e-6) and kosten_gehen_auf(sm), ware
ok("K4 Mindestauftragswert: Ware inkl. Musterkosten genau 500 € (umgelegt und als eigene Zeile)")

# ------------------------------------------------------------------ K5 Staffeln
eine = [p for p in pm if p["pos"] in M_POS | {10}]
for kp in (kopf, kz):
    zs, ss, _ = kalk(eine, kp)
    st = staffeln.stufe_rechnen(kp, eine, "10", 24, k, tab, einst)
    assert st["preis"] and abs(st["preis_gesamt"] - ss["verkauf"]) < 0.03 * 2, (st["preis_gesamt"], ss["verkauf"])
    if kp is kz:
        assert st["preis"]["muster_einmalig"] > 0 and nah(st["preis"]["muster_einmalig"], ss["muster_einmalig"], 0.01)
    else:
        assert st["preis"]["muster_umlage"] > 0 and st["preis"]["muster_einmalig"] == 0
    gross = staffeln.stufe_rechnen(kp, eine, "10", 240, k, tab, einst)
    assert gross["preis_einheit"] < st["preis_einheit"]           # Musterkosten verteilen sich auf mehr Teile
# Stufe für ein Muster selbst: als Serienteil gerechnet
st_m = staffeln.stufe_rechnen(kopf, eine, "60", 10, k, tab, einst)
assert st_m["preis_einheit"] > 0
ok("K5 Staffeln: Stufe mit der Menge des Angebots = Angebot (umgelegt und eigene Zeile), größere Menge billiger")

# ------------------------------------------------------------------ K6 Angebot, PDF, CSV
db.einstellung_setzen("muster_frist", 60)
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
ang = ausgabe.angebot(kopf, pm, z1, k, einst)
mz = [z for z in ang["zeilen"] if z.get("muster")]
assert len(mz) == 3 and all(z["preis"] == 0 and z["gesamt"] == 0 and ausgabe.MUSTER_VERMERK in z["text"] for z in mz)
assert not any(z["art"] == "einmal" for z in ang["zeilen"]) and abs(ang["netto"] - s1["verkauf"]) < 0.5
assert "Pos. 60, 70, 80" in ang["muster"] and ausgabe.euro_text(betrag) in ang["muster"], ang["muster"]
assert "14.12.2026" in ang["muster"], ang["muster"]           # 15.10.2026 + 60 Tage
ang2 = ausgabe.angebot(kz, pm, z2, k, einst)
ein = [z for z in ang2["zeilen"] if z["art"] == "einmal"]
assert len(ein) == 1 and nah(ein[0]["preis"], round(s2["muster_einmalig"], 2), 0.006) and "Musterkosten einmalig" in ein[0]["text"]
assert ang2["muster"] == "" and all(ausgabe.MUSTER_VERMERK_ZEILE in z["text"] for z in ang2["zeilen"] if z.get("muster"))
assert abs(ang2["netto"] - s2["verkauf"]) < 0.5
assert ausgabe.muster_hinweis(kopf, dict(einst, muster_hinweis=""), [60], 10) == ""
assert ausgabe.muster_hinweis(kopf, dict(einst, muster_hinweis="Muster {falsch}"), [60], 10) == "Muster {falsch}"
for ziel, an in (("a.pdf", ang), ("b.pdf", ang2)):
    pdf.angebot_pdf(tmp / ziel, kopf, an, einst)
    assert (tmp / ziel).stat().st_size > 1000
pz = export.positions_zeilen(kopf, pm, e1, z1, s1, k, tab)
assert [x["Kommentar"] for x in pz if x["Pos."] in ("60", "70", "80")] == ["Muster, im Serienpreis enthalten"] * 3
assert all(x["Stückpr."] == "0.00" for x in pz if x["Pos."] in ("60", "70", "80"))
werk = ausgabe.werkstatt(kopf, pm, e1, k, tab)
assert sum(1 for m in werk["muster"] if "MUSTERTEILE" in ausgabe.muster_titel(m)) == 3
assert sum(1 for m in werk["material"] if "MUSTER" in m["werkstoff"]) == 3
ok("K6 Angebot: Muster 0 € mit Vermerk, Hinweis mit Betrag und Frist, eigene Zeile; PDF, CSV, Werkstattpapiere")

# ------------------------------------------------------------------ K7 Oberfläche
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.muster_haken import MusterHaken  # noqa: E402

app = QApplication.instance() or QApplication([])
assert muster_info(dict(muster="ja", muster_preis_position=12.5)).startswith("Muster, Wert 12,50")
assert muster_info(dict(muster_teil=0.25)).startswith("+0,250 €") and muster_info({}) == ""
h = MusterHaken(dict(muster="ja"))
assert h.isChecked() and h.geaendert() == {}
h.setChecked(False)
assert h.geaendert() == {"muster": None} and MusterHaken({}).geaendert() == {}
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
zeile = {p["pos"]: r for r, p in enumerate(s.positionen)}
assert s.muster_umschalten([zeile[60], zeile[70]]) == 2
assert [p["pos"] for p in db.positionen(a) if p.get("muster") == "ja"] == [60, 70]
n = s.muster_umschalten([zeile[30]], an=True)       # Satz Rahmen: Pos. 30 und 40 zusammen
assert n == 2 and {p["pos"] for p in db.positionen(a) if p.get("muster") == "ja"} == {30, 40, 60, 70}
assert s.muster_umschalten([zeile[40]], an=False) == 2
assert "Muster an/aus" in s._pos_menue_anpassen()
kb = s.kopf_bereich
assert not kb.muster_wahl.isHidden()
kb.muster_darstellung.setCurrentText(MUSTER_ZEILE)
assert db.angebot(a)["muster_darstellung"] == MUSTER_ZEILE
kb.muster_darstellung.setCurrentText(kb.muster_darstellung.itemText(0))
assert db.angebot(a)["muster_darstellung"] is None
spalten = [s.pos_modell.name(c) for c in range(len(s.pos_modell.spalten))]
assert "muster" in spalten
kompakt = kompakt_zeilen(s.positionen, s._rechnung()[0])
assert any(x["muster"].startswith("Muster, Wert") for x in kompakt) and any(x["muster"].startswith("+") for x in kompakt)
# Editoren: Rohr-Editor, Blech-Editor, Schweißbaugruppe, Satz in 3D
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402
p60 = db.positionen(a)[zeile[60]]
d = SchneidwegDialog(s, p60, k.profile[p60["profil_id"]], s.kopf, k, tab, db, s.positionen)
assert d.muster_haken.isChecked() and d.muster_geaendert() == {}
d.muster_haken.setChecked(False)
assert d.muster_geaendert() == {"muster": None}


def rohr_ok(d):
    d.muster_haken.setChecked(False)
    return 1


assert s.schneidweg_berechnen(zeile[60], dialog=rohr_ok, ueberschreiben=True)
assert db.positionen(a)[zeile[60]].get("muster") is None
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
bd = BlechDialog(s, db, neu=True)
assert bd.kopf_werte()["muster"] is None
bd.muster_haken.setChecked(True)
assert bd.kopf_werte()["muster"] == "ja"
import inspect  # noqa: E402
from rohrlaser import baugruppe_dialog, satz3d  # noqa: E402
assert "muster_haken" in inspect.getsource(baugruppe_dialog.BaugruppeDialog.__init__)
assert "\"muster\"" in inspect.getsource(baugruppe_dialog.BaugruppeDialog.werte)
assert "muster_haken" in inspect.getsource(satz3d.Satz3dDialog.__init__)
ok("K7 Spalte Muster, Rechtsklick (Satz ganz), Musterkosten im Kopf, Häkchen in Rohr-, Blech-, Baugruppen-Editor und "
   "Satz in 3D, Kompaktansicht")
db.schliessen()
print("Alle Prüfungen bestanden.")
