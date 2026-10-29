"""Plan „Kalkulation und Berechnung verbessern“ (Patrick 29.10.2026, „Alles einbauen“).

- C1 Gegenprobe: ein Angebot mit Rohrlaserteilen in zwei Profilformen, Schweißbaugruppe mit Zukaufteilen, Zukaufteil-
  Position, Musterteil und Fracht; eine Staffelstufe mit genau den Mengen des Angebots ergibt cent-genau dessen Preis
  (ohne und mit allen neuen Werten).
- C2 gemeinsame Preisschicht: rechnen.gewinn_fracht an allen Stellen; leere neue Werte = Preise bitgleich wie bisher.
- A1 Nebenzeit je Teil, B1 Schneidgas je Gas, B2 Ausschuss, B4 Rüsten je weiterer Profilform, B5 Schrotterlös: jeder
  Wert von Hand nachgerechnet, Kostenarten addieren sich zum Verkaufspreis.
- B3 Preiseinheit für Kleinteile: 0,034 € je Teil steht als 3,40 € je 100 im Angebot, Summe ohne Rundungsverlust.
- C3 Preis-Plausibilität: Preis unter Material (WARNUNG), €/kg gegen frühere Angebote, Ertrag je Laserstunde.
- Festgeschriebene Angebote rechnen ohne die neuen Werte.

Aufruf: python tests/test_kalkulation_verbessern.py
"""
import json
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import beispiel_baugruppe as bsp  # noqa: E402
from rohrlaser import ausgabe, plausibel, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) <= eps * max(1.0, abs(a), abs(b)), f"{text}: {a} != {b}"


NEU = dict(zeit_teil=4.0, gas_n2=12.0, gas_o2=3.0, ruest_form=20)


def angebot(db, maschine=None, einst=None):
    """Prüfangebot: Rahmen R1 (Baugruppe, 2 Rohrlaserteile, Zukaufteil-Position), dazu Rundrohr in Edelstahl
    (zweite Profilform), ein Musterteil und 60 € Fracht. Ergebnis: (kopf, positionen, k, tabellen, einst)."""
    for n, w in (einst or {}).items():
        db.einstellung_setzen(n, w)
    for x in db.zeilen("maschinen"):
        for n, w in (maschine or {}).items():
            db.aendern("maschinen", x["id"], n, w)
    a = bsp.anlegen(db)
    for n, w in (("fracht", 60), ("fracht_modus", "manuell"), ("skonto", 2)):
        db.angebot_aendern(a, n, w)
    db.position_neu(a, dict(pos=200, artikel="VA-1", profil_id="RR 42,4x2,0", werkstoff_id="1.4301", laenge=720,
                            stueck=40, schneidweg=290, einstiche=2))
    db.position_neu(a, dict(pos=210, artikel="VA-2", profil_id="RR 42,4x2,0", werkstoff_id="1.4301", laenge=380,
                            stueck=6, schneidweg=310, einstiche=4, muster="ja"))
    kopf, pos = db.angebot(a), db.positionen(a)
    k, tab = db.kontext(), db.tabellen()
    erg = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())
    db.ergebnis_speichern(a, erg)
    kopf = db.angebot(a)
    e = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    return kopf, pos, k, tab, e


def stufe_wie_angebot(pos):
    """Eine Stufe mit allen Sätzen und Einzelpositionen in den Mengen des Angebots (ohne Musterteile)."""
    zeilen, saetze = [], {}
    for p in pos:
        if p.get("muster") == "ja" or not p.get("stueck"):
            continue
        if p.get("satz"):
            je = p.get("je_satz") if (p.get("je_satz") or 0) >= 1 else 1
            saetze[p["satz"]] = max(saetze.get(p["satz"], 0), p["stueck"] / je)
        else:
            zeilen.append(dict(schluessel=str(p["pos"]), menge=p["stueck"], stufe_id=1))
    zeilen += [dict(schluessel=s, menge=round(m), stufe_id=1) for s, m in saetze.items()]
    return [dict(z, id=i) for i, z in enumerate(zeilen, 1)], [dict(id=1, nr=1)]


def gegenprobe(kopf, pos, k, tab, e):
    erg = kopf["ergebnis"]
    zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, e)
    mz, stufen = stufe_wie_angebot(pos)
    st = staffeln.rechnen_alle(kopf, pos, mz, k, tab, e, stufen_daten=stufen)
    assert all(z.get("preis") for z in st), [z.get("hinweis") for z in st]
    netto = sum(z["preis"]["netto"] for z in st)
    nah(netto, summen["verkauf"], "Staffel = Angebot")
    # Kostenarten addieren sich: Herstellkosten, Selbstkosten, Verkaufspreis
    w = {n: summen.get(n, 0.0) for _, n, _ in rechnen.KOSTENARTEN}
    teile = ("material", "schrott", "laser_schneiden", "schneidgas", "gewinde", "ruesten_maschine",
             "ruesten_abmessungen", "stangenwechsel_kosten", "arbeitsschritte", "zusatz", "handling_beistellung",
             "baugruppe_eigen", "baugruppe_fremd", "ausschuss", "zuschlag_material", "zuschlag_fertigung",
             "zuschlag_fremdleistung")
    nah(sum(w[n] for n in teile), w["herstell"], "Herstellkosten = Summe der Kostenarten")
    nah(w["selbst"] + w["gewinn"] + w["fracht"] + w["skonto"] + w["mindestpreis_anhebung"], w["verkauf"] -
        summen.get("muster_einmalig", 0.0), "Verkaufspreis = Selbstkosten + Gewinn + Fracht + Skonto")
    return zeilen, summen, st


# ------------------------------------------------------------------ C1/C2: ohne neue Werte
tmp = Path(tempfile.mkdtemp())
db0 = Datenbank(tmp / "alt.db")
kopf, pos, k, tab, e = angebot(db0)
z0, s0, _ = gegenprobe(kopf, pos, k, tab, e)
assert s0["schneidgas"] == 0 and s0["ausschuss"] == 0 and s0["schrott"] == 0 and s0["ruesten_form"] == 0
assert all(not z or not z.get("zeit_neben") for z in z0)
assert s0["muster_positionen"] == 1 and s0["baugruppen"] == 1 and s0["fracht"] == 60
ok(f"C1 Gegenprobe ohne neue Werte: Stufe mit den Mengen des Angebots = {s0['verkauf']:.2f} € (Baugruppe, Zukauf, "
   "Muster, Fracht, Skonto)")

# ------------------------------------------------------------------ A1, B1, B2, B4, B5 mit Werten
db1 = Datenbank(tmp / "neu.db")
kopf, pos, k, tab, e = angebot(db1, NEU, dict(ausschuss=0.03, schrott_anteil=0.2))
z1, s1, st1 = gegenprobe(kopf, pos, k, tab, e)
ok(f"C1 Gegenprobe mit allen neuen Werten: Stufe = Angebot {s1['verkauf']:.2f} €")

laser = [i for i, z in enumerate(z1) if z and not z.get("zukaufteil") and not z.get("baugruppe")]
for i in laser:
    a, b = z0[i], z1[i]
    nah(b["zeit_neben"], 4.0, "Nebenzeit je Teil")
    nah(b["laser_brutto"], a["laser_brutto"] + 4.0, "Laser brutto + Nebenzeit")
    gas = 12.0 if b["gas"] == "N₂" else 3.0
    nah(b["schneidgas_teil"], b["laser_netto"] / 3600 * gas, f"Schneidgas Pos. {b['pos']}")
    nah(b["ausschuss_teil"], 0.03 * b["material_teil"] + 0.03 * b["laser_teil"], "Ausschuss")
    assert b["schrott_teil"] <= 0
ok("A1 Nebenzeit 4 s je Teil in der Laserzeit, B1 Schneidgas = Laserzeit × 12 €/h (N₂) bzw. 3 €/h (O₂), "
   "B2 Ausschuss 3 % auf Material und Laserzeit")

# B5 Schrotterlös: (Stangenlänge − Teile − Lagerrest) × Preis je mm × 20 %
sw = rechnen.stangen_werte(kopf["ergebnis"], kopf, pos, k, tab)
soll = 0.0
for s_, x in zip(kopf["ergebnis"]["stangen"], sw):
    if s_.get("muster"):
        soll += (x["belegt"] - x["summe"]) * x["kosten_voll"] / s_["stange"] * 0.2
    else:
        soll += (s_["stange"] - x["summe"]) * x["kosten"] / s_["stange"] * 0.2
nah(-s1["schrott"], soll, "Schrotterlös")
assert s1["schrott"] < 0
ok(f"B5 Schrotterlös 20 % auf den Verschnitt: {-s1['schrott']:.2f} € Gutschrift")

# B4: zwei Profilformen (Quadratrohr, Rundrohr) → ein Zuschlag 20 min × Satz 'Rüsten je Abmessung'
sa = [z for z in s1["zeiten"] if z["schritt"] == "Rüsten je Abmessung"][0]["satz"]
assert s1["formen_weitere"] == 1
nah(s1["ruesten_form"], 20 / 60 * sa, "Rüsten Profilform")
nah(s1["ruesten_abmessungen"] - s0["ruesten_abmessungen"], s1["ruesten_form"], "in Rüsten je Abmessung")
text = dict((t.split(" (")[0], t) for t, _, _ in rechnen.kostenarten(s1, e))
assert "1 × 20 min weitere Profilform" in text["Rüsten je Abmessung"], text["Rüsten je Abmessung"]
assert {x["schritt"] for x in s1["zeiten"]} >= {"Schneidgas", "Ausschuss"}
ok(f"B4 Rüsten je weiterer Profilform: 1 × 20 min = {s1['ruesten_form']:.2f} €, in Kostenarten und Zeiten")

# ------------------------------------------------------------------ B3 Preiseinheit
assert ausgabe.preiseinheit(0.034, 0.1) == 100 and ausgabe.preiseinheit(0.004, 0.1) == 1000
assert ausgabe.preiseinheit(0.5, 0.1) == 1 and ausgabe.preiseinheit(0.034, 0) == 1
zeilen = [dict(pos=10, preis_teil=0.0344, stueck=10000, hinweis="")]
pos_k = [dict(pos=10, artikel="K", stueck=10000, profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=20)]
ang = ausgabe.angebot({}, pos_k, zeilen, k, dict(preiseinheit_ab=0.1, mwst=0.19))
z = ang["zeilen"][0]
assert z["preiseinheit"] == 100 and z["preis"] == 3.44 and z["gesamt"] == 344.0, z
alt = ausgabe.angebot({}, pos_k, zeilen, k, dict(preiseinheit_ab=0, mwst=0.19))["zeilen"][0]
assert alt["preiseinheit"] == 1 and alt["preis"] == 0.03 and alt["gesamt"] == 300.0
b = dict(material=100.0, material_fehlt=0, fertigung=[("Laser schneiden", 244.0, "")], ruesten=[], fremd=0.0,
         pauschalen=0.0, programmierung=0.0, angebotsaufschlag=0.0, fracht=0.0, skonto_satz=0.0, satz_maschine=60.0,
         verkauf=None)
basis = dict(zuschlag_material=0, zuschlag_fertigung=0, zuschlag_fremdleistung=0, gewinn=0, mwst=0.19)
p = staffeln.preise(b, 10000, staffeln.wirksam({}, dict(basis, preiseinheit_ab=0.1)))
assert p["preiseinheit"] == 100 and p["preis_pe"] == 3.44 and p["preis_gesamt"] == 344.0, p
p = staffeln.preise(b, 10000, staffeln.wirksam({}, basis))
assert p["preiseinheit"] == 1 and p["preis_einheit"] == 0.03 and p["preis_gesamt"] == 300.0
st = [dict(preis_einheit=0.0344, preis_gesamt=344.0, menge=10000, schluessel="10", einheit="Stück",
           preis=dict(preiseinheit=100, preis_pe=3.44, einmalig=0))]
ang = ausgabe.angebot({}, pos_k, zeilen, k, dict(preiseinheit_ab=0.1, mwst=0.19), st)
assert ang["staffeln"][0]["preis"] == 3.44 and ang["staffeln"][0]["preiseinheit"] == 100
assert ausgabe.staffel_widersprueche(ang) == []
ok("B3 Preiseinheit: 0,0344 € je Teil → 3,44 € je 100, 10.000 Stück = 344,00 € statt 300,00 €; Staffel ebenso")

# ------------------------------------------------------------------ C3 Plausibilität
kopf, pos, k, tab, e = angebot(Datenbank(tmp / "pl.db"))
zeilen, summen = rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e)
assert plausibel.punkte(pos, zeilen, summen, k) == []
kw = plausibel.kennwerte(pos, zeilen, k)
assert kw and all(w["eur_kg"] > 0 for w in kw) and not any(w["profil_id"] is None for w in kw)
va = [w for w in kw if w["werkstoff_id"] == "1.4301"]
assert len(va) == 1, "Musterteil zählt nicht"
verlauf = [[dict(kennwerte=[dict(va[0], eur_kg=va[0]["eur_kg"] / 5)])]] * 3
vgl = plausibel.vergleich_aus(verlauf)
pk = plausibel.punkte(pos, zeilen, summen, k, vgl)
assert len(pk) == 1 and pk[0][0] == "HINWEIS" and "frühere Angebote" in pk[0][1], pk
falsch = [dict(z, preis_teil=z["material_teil"] * 0.5) if z and z.get("pos") == 200 else z for z in zeilen]
pk = plausibel.punkte(pos, falsch, summen, k)
assert pk[0][0] == "WARNUNG" and "unter den Materialkosten" in pk[0][1], pk
pk = plausibel.punkte(pos, zeilen, dict(summen, verkauf=summen["material"]), k)
assert any("Ertrag je Laserstunde" in t for _, t, _ in pk), pk
from rohrlaser import angebot_check  # noqa: E402
pp = angebot_check.punkte(kopf, pos, [""] * len(pos), "aktuell", summen, plausibel=[("WARNUNG", "Test", 1)])
assert any(p_.text == "Test" and p_.ziel == "pos:1" for p_ in pp)
db = Datenbank(tmp / "pl.db")
aid = db.angebote()[0]["id"]
db.versand_merken(aid, dict(datum="2026-10-29", netto=1.0, datei="x.pdf", kennwerte=kw))
assert plausibel.vergleich_aus(db.versand_verlaeufe())[("RR 42,4x2,0", "1.4301")] == [va[0]["eur_kg"]]
assert db.versand_verlaeufe(aid) == []
ok("C3 Plausibilität: Preis unter Material = WARNUNG, €/kg 5× über früheren Angeboten = HINWEIS, Ertrag je "
   "Laserstunde, Kennwerte im Versandverlauf")

# ------------------------------------------------------------------ festgeschrieben vor dem 29.10.2026
kopf, pos, k, tab, e = angebot(Datenbank(tmp / "fest.db"), NEU, dict(ausschuss=0.03, schrott_anteil=0.2,
                                                                       preiseinheit_ab=0.1))
pb = rechnen.preisbasis_aus(kopf, pos, k, tab)
assert all(n in pb["einstellungen"] for n in rechnen.EINST_NEU)
alt_pb = dict(pb, einstellungen={n: w for n, w in pb["einstellungen"].items() if n not in rechnen.EINST_NEU},
              maschinen={m: {n: v for n, v in x.items() if n not in rechnen.MASCHINE_NEU}
                         for m, x in pb["maschinen"].items()})
k2, tab2 = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=alt_pb), k, tab)
e2 = rechnen.einstellungen_angebot(kopf, rechnen.einstellungen_fest(tab2, e))
assert all(e2[n] == 0 for n in rechnen.EINST_NEU)
zz, ss = rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k2, tab2, e2)
assert ss["ausschuss"] == 0 and ss["schrott"] == 0 and all(not z or not z.get("zeit_neben") for z in zz)
ok("festgeschrieben vor dem 29.10.2026: ohne Ausschuss, Schrotterlös, Nebenzeit und Preiseinheit")
json.dumps(rechnen.preisbasis_aus(kopf, pos, k, tab))
print("OK: Kalkulation und Berechnung verbessert")
