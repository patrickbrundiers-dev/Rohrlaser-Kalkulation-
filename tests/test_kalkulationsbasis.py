"""Prüfung Kalkulationsbasis (Patrick 02.11.2026 „Alle Empfehlungen“, 1a-8a).

1 Grundwerte-Check: leere Nebenzeit/Zeit je Kontur mit €-Wirkung, Beispiel-Stundensätze, Zuschlag Material 0.
2 Schneiddaten zwischen den Wandstufen linear interpoliert (2,6 mm zwischen 2 und 3 mm), festgeschrieben: Stufe.
3 Wiederholteile mit Programm: Programmierzeit = Einstellung (Vorgabe 1 min).
4 Rüsten je Abmessung, nur Wand anders: weniger Minuten bei gleicher Außenkontur, RP-Profile nie.
5 Doppelzählung: Gemeinkosten im ermittelten Satz + Zuschlag Fertigung, Staffel-Verlust + Ausschuss, Entgraten zweimal.
6 Ausschuss im Hundert (a ÷ (1 − a)), festgeschrieben: a.
7 Strom nach mittlerer Last in der Stundensatz-Ermittlung.
8 Gewinn auf Material getrennt; Staffel mit den Mengen des Angebots = Angebot.

Aufruf: python tests/test_kalkulationsbasis.py
"""
import dataclasses
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import beispiel_angebot as bsp_a  # noqa: E402
from rohrlaser import grundwerte, rechnen, stundensatz  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
import beispiel_baugruppe as bsp  # noqa: E402
from rohrlaser import staffeln  # noqa: E402


# Prüfangebot und Gegenprobe wie tests/test_kalkulation_verbessern.py
def ok(text):
    print("OK    ", text)


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) <= eps * max(1.0, abs(a), abs(b)), f"{text}: {a} != {b}"


NEU = dict(zeit_teil=4.0, gas_n2=12.0, gas_o2=3.0, ruest_form=20, gas_zusatz="ja")


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



tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "kb.db")
k, tab, e = db.kontext(), db.tabellen(), db.einstellungen()
kopf = dict(bsp_a.KOPF)
pos = [dict(p, id=i) for i, p in enumerate(bsp_a.POSITIONEN, 1)]
erg = rechnen.optimieren(kopf, pos, k)

# ------------------------------------------------------------------ 2 Schneiddaten interpolieren
w50 = rechnen.position_werte(pos[4], kopf, k, tab)["wand_schneiden"]
assert abs(w50 - 2.6) < 1e-9, w50
sd = rechnen.schneiddaten("T11", pos[4]["werkstoff_id"], 2.6, tab, rechnen.kategorie(pos[4]["werkstoff_id"], k),
                          rechnen.werkstoff_zeile(pos[4]["werkstoff_id"], k))
u = rechnen.schneiddaten("T11", pos[4]["werkstoff_id"], 2.0, tab, "Stahl")
o = rechnen.schneiddaten("T11", pos[4]["werkstoff_id"], 3.0, tab, "Stahl")
assert sd["wand_bis"] == 3 and sd["interpoliert"] == (2, 3) and "interpoliert" not in u and "interpoliert" not in o
for n in ("vorschub_gross", "einstechzeit"):
    nah(sd[n], u[n] + 0.6 * (o[n] - u[n]), n)
alt_tab = dict(tab, einstellungen=dict(tab.get("einstellungen") or {}, sd_interpolieren="nein"))
sd_alt = rechnen.schneiddaten("T11", pos[4]["werkstoff_id"], 2.6, alt_tab, "Stahl")
assert sd_alt["vorschub_gross"] == o["vorschub_gross"] and "interpoliert" not in sd_alt
over = rechnen.schneiddaten("T11", pos[4]["werkstoff_id"], 3.0, tab, "Stahl")
assert "interpoliert" not in over          # genau auf der Stufe: unverändert
z_neu, s_neu = rechnen.kalkulation(kopf, pos, erg, k, tab, e)
z_alt, s_alt = rechnen.kalkulation(kopf, pos, erg, k, alt_tab, e)
assert z_neu[4]["laser_netto"] < z_alt[4]["laser_netto"] and z_neu[0]["laser_netto"] == z_alt[0]["laser_netto"]
ok(f"2 Schneiddaten 2,6 mm interpoliert: {sd['vorschub_gross']:.0f} statt {o['vorschub_gross']:.0f} mm/min, Pos. 50 "
   f"{z_neu[4]['laser_netto']:.1f} s statt {z_alt[4]['laser_netto']:.1f} s; festgeschrieben mit der Stufe")

# ------------------------------------------------------------------ 3 Wiederholteile
assert e.get("programmierung_wiederholteil") == 1.0
_, s0 = rechnen.kalkulation(kopf, pos, erg, k, tab, e)
_, s1 = rechnen.kalkulation(dict(kopf, wiederholt="[1, 2]"), pos, erg, k, tab, e)
assert s1["wiederholt_prog"] == 2
p1 = rechnen.programmier_zeit(pos[0], e)[0] + rechnen.programmier_zeit(pos[1], e)[0]
nah(s0["programmierung"] - s1["programmierung"], (p1 - 2 * 1.0) / 60 * 60.0, "Programmierung weniger")
_, s2 = rechnen.kalkulation(dict(kopf, wiederholt="[1, 2]"), pos, erg, k, tab, dict(e, programmierung_wiederholteil=None))
nah(s2["programmierung"], s0["programmierung"], "leer = volle Zeit")
hand = rechnen.programmier_zeit(dict(pos[0], prog_zeit=7), e, True)
assert hand == (7, True)
ok(f"3 Wiederholteile mit Programm: 1 min statt {p1:.1f} min für 2 Positionen, von Hand geht vor")

# ------------------------------------------------------------------ 4 Rüsten nur Wand anders
k4 = dataclasses.replace(k, profile=dict(k.profile, **{"QR 40x40x2": dict(k.profile["QR 40x40x3"], wand=2.0)}))
pos4 = [dict(id=1, pos=10, artikel="A", profil_id="QR 40x40x2", werkstoff_id="S235-10219", laenge=800, stueck=20,
             schneidweg=300, einstiche=2),
        dict(id=2, pos=20, artikel="B", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800, stueck=20,
             schneidweg=300, einstiche=2)]
erg4 = rechnen.optimieren(kopf, pos4, k4)
_, a4 = rechnen.kalkulation(kopf, pos4, erg4, k4, tab, e)
_, b4 = rechnen.kalkulation(kopf, pos4, erg4, k4, tab, dict(e, ruesten_abmessung_wand=5))
satz = k.maschinen["T11"]["stundensatz"]
nah(a4["ruesten_abmessungen"], 2 * 15 / 60 * satz, "volle Rüstzeit")
nah(b4["ruesten_abmessungen"], (15 + 5) / 60 * satz, "zweite Wand 5 min")
zr = next(z for z in b4["zeiten"] if z["schritt"] == "Rüsten je Abmessung")
nah(zr["gesamt_min"], 20, "Minuten") and None
assert b4["abmessungen_wand"] == 1
rp = [p for p in k.profile if p.startswith("RP 0103-50") or p.startswith("RP 0111-50")]
pos_rp = [dict(pos4[0], profil_id=rp[0]), dict(pos4[1], profil_id=rp[1])]
erg_rp = rechnen.optimieren(kopf, pos_rp, k)
_, c4 = rechnen.kalkulation(kopf, pos_rp, erg_rp, k, tab, dict(e, ruesten_abmessung_wand=5))
assert c4["abmessungen_wand"] == 0
ok(f"4 Rüsten QR 40×40×2 + ×3: {b4['ruesten_abmessungen']:.2f} € statt {a4['ruesten_abmessungen']:.2f} €, "
   "RP-Profile mit gleichem A/B nie")

# ------------------------------------------------------------------ 6 Ausschuss im Hundert
_, a6 = rechnen.kalkulation(kopf, pos, erg, k, tab, dict(e, ausschuss=0.03))
_, b6 = rechnen.kalkulation(kopf, pos, erg, k, tab, dict(e, ausschuss=0.03, ausschuss_hundert="nein"))
nah(a6["ausschuss_material"], b6["ausschuss_material"] / 0.97, "im Hundert")
assert rechnen.ausschuss_faktor({}) == 0 and abs(rechnen.ausschuss_faktor(dict(ausschuss=0.05)) - 0.05 / 0.95) < 1e-12
ok(f"6 Ausschuss 3 % im Hundert: {a6['ausschuss_material']:.2f} € statt {b6['ausschuss_material']:.2f} € Material")

# ------------------------------------------------------------------ 7 Strom nach mittlerer Last
m = dict(k.maschinen["T11"], satz_art="ermittelt", anschaffung=600000, nutzungsdauer=10, leistung_kw=35)
voll = stundensatz.ermitteln(m, e)
halb = stundensatz.ermitteln(dict(m, last_anteil=50), e)
nah(voll - halb, 35 * 0.5 * e["strompreis"] * (1 + e["gemeinkosten"]), "Strom halbe Last")
zeilen7 = stundensatz.posten(dict(m, last_anteil=50), e)[0]
assert any("50 % mittlere Last" in (z[1] or "") for z in zeilen7)
ok(f"7 Strom 35 kW bei 50 % Last: Stundensatz {halb:.2f} statt {voll:.2f} €/h")

# ------------------------------------------------------------------ 8 Gewinn auf Material + Gegenprobe Staffel
_, a8 = rechnen.kalkulation(kopf, pos, erg, k, tab, dict(e, gewinn=0.23, gewinn_material=5))
z8, _ = rechnen.kalkulation(kopf, pos, erg, k, tab, dict(e, gewinn=0.23, gewinn_material=5))
zg, _ = rechnen.kalkulation(kopf, pos, erg, k, tab, dict(e, gewinn=0.23))
for x, y in zip(z8, zg):
    if x:
        nah(y["gewinn_teil"] - x["gewinn_teil"], x["material_teil"] * (0.23 - 0.05), f"Gewinn Pos. {x['pos']}")
assert a8["gewinn_material_satz"] == 5
db8 = Datenbank(tmp / "g8.db")
kopf8, pos8, k8, tab8, e8 = angebot(db8, einst=dict(gewinn_material=4.0, ausschuss=0.02, ruesten_abmessung_wand=5))
_, s8, _ = gegenprobe(kopf8, pos8, k8, tab8, e8)
ok(f"8 Gewinn Material 5 % / Rest 23 %: je Teil (Gewinn − Gewinn Material) × Material; Gegenprobe Staffel = Angebot "
   f"{s8['verkauf']:.2f} €")

# ------------------------------------------------------------------ festgeschrieben vor dem 02.11.2026
pb = rechnen.preisbasis_aus(kopf, pos, k, tab)
assert pb["einstellungen"]["sd_interpolieren"] == "ja" and pb["einstellungen"]["ausschuss_hundert"] == "ja"
alt_pb = dict(pb, einstellungen={n: w for n, w in pb["einstellungen"].items()
                                 if n not in ("sd_interpolieren", "ausschuss_hundert") + rechnen.EINST_KB})
k2, tab2 = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=alt_pb), k, dict(tab, einstellungen=dict(
    e, gewinn_material=5, ausschuss=0.03, programmierung_wiederholteil=1.0)))
e2 = rechnen.einstellungen_fest(tab2, dict(e, gewinn_material=5))
assert e2["ausschuss_hundert"] == "nein" and e2["gewinn_material"] is None and not rechnen.interpolieren(tab2)
ok("festgeschrieben vor dem 02.11.2026: Stufe, Ausschuss einfach, ohne Gewinn Material und Wiederholteil-Zeit")

# ------------------------------------------------------------------ 1 und 5 Grundwerte-Check
punkte = grundwerte.punkte(k, tab, e)
texte = " | ".join(t for _, _, t in punkte)
assert "Nebenzeit je Teil" in texte and "Zeit je Kontur" in texte and "Beispielwert" in texte
assert "Zuschlag Material ist 0" in texte and not any(a == "WARNUNG" for a, _, _ in punkte)
w = grundwerte.wirkung(kopf, pos, erg, k, tab, e)
assert w["felder"] == ["zeit_teil", "zeit_kontur"] and w["plus"] > 0
ap = grundwerte.angebot_punkte(kopf, pos, erg, k, tab, e)
assert ap and ap[0][0] == "HINWEIS" and "Richtwerten" in ap[0][1]
k1 = dataclasses.replace(k, maschinen=dict(k.maschinen, T11=dict(k.maschinen["T11"], zeit_teil=8, zeit_kontur=1.5)))
assert grundwerte.wirkung(kopf, pos, erg, k1, tab, e) is None
# 5 Doppelzählung
k5 = dataclasses.replace(k, maschinen=dict(k.maschinen, T11=m))
e5 = dict(e, zuschlag_fertigung=0.15, gemeinkosten=0.25, ausschuss=0.03)
p5 = grundwerte.angebot_punkte(kopf, [dict(pos[0], zusatz='[{"name": "Entgraten"}]')] + pos[1:], erg, k5,
                               dict(tab, arbeitsschritte=[dict(schritt="Entgraten / Nachbearbeitung", zeit=10)]),
                               e5, stufen=[dict(verlust=3)], wirkung_={})
assert [a for a, _, _ in p5] == ["WARNUNG"] * 3, p5
assert "doppelt" in p5[0][1] and "Entgraten" in p5[1][1] and "Staffelstufe" in p5[2][1]
ok(f"1 Grundwerte-Check: {len(punkte)} Hinweise ab Werk, Wirkung Nebenzeiten +{w['plus']:.2f} € "
   f"({w['prozent']:.1f} %); 5 Doppelzählung Stundensatz, Entgraten, Staffel-Verlust als WARNUNG")
print("OK: Prüfung Kalkulationsbasis")
