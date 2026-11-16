"""Plan Schweißbaugruppe 10.11.2026, Schritt 1 „Berechnung genauer“ (Freigabe Patrick „Alles umsetzen“):
G1 Schweißlage aus dem Nahtverlauf im STEP, G2 Ansatzzeit je Naht, G3 Abschmelzleistung nach Nahtgröße,
G4 Nahtvorbereitung (Fase). Ohne die neuen Regeln rechnet alles wie bis 0.9.277."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))

from rohrlaser import baugruppe, vorkalk  # noqa: E402


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


REGELN_ALT = [dict(art=a, wert=w, bis=b, zahl=z, status="geprüft") for a, w, b, z, _ in vorkalk.RICHTWERTE
              if a not in vorkalk.NEU_1011]
REGELN = [dict(art=a, wert=w, bis=b, zahl=z, status="geprüft") for a, w, b, z, _ in vorkalk.RICHTWERTE]
FAKTOREN = [dict(art=a, wert=w, faktor=f, status="geprüft") for a, w, f in baugruppe.RICHT_FAKTOREN]
TAB = dict(schweissverfahren=[dict(verfahren="MAG", satz_id="Schweißen", lichtbogen=50, heft_s=6, status="geprüft")],
           schweiss_kennwerte=[dict(verfahren="MAG", nahtart=art, mass_bis=m, min_m=z, status="geprüft")
                               for art in ("Kehlnaht", "Stumpfnaht", "Ecknaht")
                               for m, z in ((3, 2.0), (4, 3.2), (6, 6.0), (10, 15.0))],
           schweiss_faktoren=FAKTOREN, schweiss_regeln=REGELN)
TAB_ALT = dict(TAB, schweiss_regeln=REGELN_ALT)
SAETZE = {"Schweißen": 60.0}

# ------------------------------------------------------------------ G2 Ansatzzeit je Naht
kurz = dict(verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=30, anzahl=20)       # 20 kurze Nähte = 0,6 m
lang = dict(verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=600, anzahl=1)       # eine lange Naht = 0,6 m
ra, rb = baugruppe.naht_rechnen(kurz, TAB_ALT, SAETZE), baugruppe.naht_rechnen(lang, TAB_ALT, SAETZE)
nah(ra["zeit_min"], rb["zeit_min"], "ohne Regel Ansatz: kurz = lang (wie bis 0.9.277)")
assert not ra.get("ansatz_min") and "Ansetzen" not in ra["rechenweg"]
ka, la = baugruppe.naht_rechnen(kurz, TAB, SAETZE), baugruppe.naht_rechnen(lang, TAB, SAETZE)
nah(ka["ansatz_min"], 20 * 10 / 60, "20 Nähte × 10 s")
nah(la["ansatz_min"], 10 / 60, "1 Naht × 10 s")
nah(ka["zeit_min"] - ra["zeit_min"], 20 * 10 / 60, "nur die Ansatzzeit kommt dazu")
assert "Ansetzen 20 × 10 s" in ka["rechenweg"]
beid = baugruppe.naht_rechnen(dict(lang, beidseitig=True), TAB, SAETZE)
nah(beid["ansatz_min"], 2 * 10 / 60, "beidseitig: je Seite ein Ansatz")
hand = baugruppe.naht_rechnen(dict(lang, zeit_hand=7), TAB, SAETZE)
nah(hand["zeit_min"], 7, "Zeit von Hand bleibt")
alt_stand = baugruppe.naht_stand(kurz, TAB_ALT)                 # gemerkter Stand eines alten Angebots
nah(baugruppe.naht_rechnen(dict(kurz, stand=alt_stand), TAB, SAETZE)["zeit_min"], ra["zeit_min"],
    "altes Angebot mit gemerktem Stand: unverändert")
ok("G2 Ansatzzeit: 20 kurze Nähte + 3,33 min, eine lange + 0,17 min; ohne Regel und mit altem Stand wie bisher")

# ------------------------------------------------------------------ G3 Abschmelzleistung nach Nahtgröße
neu = {(z["verfahren"], z["nahtart"], z["mass_bis"]): z["min_m"] for z in baugruppe.richtwerte()["schweiss_kennwerte"]}
alt = {(z["verfahren"], z["nahtart"], z["mass_bis"]): z["min_m"]
       for z in baugruppe.richtwerte(False)["schweiss_kennwerte"]}
q = baugruppe.nahtquerschnitt
for a, kg_h in ((3, 2.5), (4, 3.0), (5, 3.5), (6, 3.5), (8, 4.0), (10, 4.0)):
    nah(neu[("MAG", "Kehlnaht", a)], round(q("Kehlnaht", a) * 7.85 / 1000 / kg_h * 60, 2), f"MAG a{a} mit {kg_h} kg/h")
assert neu[("MAG", "Kehlnaht", 3)] > alt[("MAG", "Kehlnaht", 3)] and neu[("MAG", "Kehlnaht", 8)] < alt[("MAG", "Kehlnaht", 8)]
assert neu[("MAG", "Kehlnaht", 5)] == alt[("MAG", "Kehlnaht", 5)]
werte = list(neu[("MAG", "Kehlnaht", a)] for a in (2, 3, 4, 5, 6, 8, 10))
assert werte == sorted(werte), "größere Naht dauert je m immer länger"
zeilen = [dict(z, id=i) for i, z in enumerate(baugruppe.richtwerte(False)["schweiss_kennwerte"])]
zeilen[0]["min_m"] = 9.99                      # von Hand geändert
zeilen[1]["status"] = "geprüft"                # bestätigt
st = baugruppe.kennwerte_staffelbar(dict(schweiss_kennwerte=zeilen))
ids = {z["id"] for z, _, _ in st}
assert 0 not in ids and 1 not in ids and st, "geänderte und geprüfte Zeilen bleiben"
assert all(abs(n - z["min_m"]) >= 0.005 for z, n, _ in st)
assert baugruppe.kennwerte_staffelbar(dict(schweiss_kennwerte=baugruppe.richtwerte()["schweiss_kennwerte"])) == []
ok(f"G3 Staffel: MAG a3 {alt[('MAG', 'Kehlnaht', 3)]} → {neu[('MAG', 'Kehlnaht', 3)]} min/m, a8 "
   f"{alt[('MAG', 'Kehlnaht', 8)]} → {neu[('MAG', 'Kehlnaht', 8)]}; nur unveränderte Richtwerte umstellbar")


# ------------------------------------------------------------------ G1 Schweißlage aus STEP
def bg_mit(naehte, **stamm):
    b = baugruppe.leer()
    b["stamm"].update(stamm)
    b["naehte"] = naehte
    return b


def naht(nr, linien, seiten, **w):
    return dict(dict(id=f"n{nr}", nr=str(nr), verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=200, anzahl=1,
                     linien=linien, seiten=seiten, zugang_step="gut"), **w)


WAAG = [[0, 0, 0, 200, 0, 0]]                       # liegt in X
SENK = [[0, 0, 0, 0, 0, 200]]                       # steht in Z
RING = [[0, 0, 0, 50, 0, 0, 50, 0, 50, 0, 0, 50, 0, 0, 0]]     # geschlossen in der XZ-Ebene: halb waagerecht
b = bg_mit([naht(1, WAAG, [["+Z"]] * 3), naht(2, SENK, [["+Z", "+X"]] * 3),
            naht(3, WAAG, [["+Z"]] * 3, nahtart="Stumpfnaht", mass=4),
            naht(4, RING, [["+Z"]] * 3, rundum=True)], gewicht="12")
p = dict(art="Schweißbaugruppe", baugruppe=baugruppe.speichern(b))
r = vorkalk.vorkalkulieren(p, [p], TAB)
lagen = {n["nr"]: n.get("lage") for n in r["bg"]["naehte"]}
assert lagen == {"1": "PB", "2": "PF", "3": "PA", "4": "PA"}, lagen
assert all(vorkalk.naht_status(n, "lage") == vorkalk.VORSCHLAG for n in r["bg"]["naehte"])
assert "wird gedreht" in r["bg"]["naehte"][3]["vk"]["lage"]["text"]
b["stamm"]["gewicht"] = "35"                         # zu schwer zum Drehen
p = dict(p, baugruppe=baugruppe.speichern(b))
r35 = vorkalk.vorkalkulieren(p, [p], TAB)
assert r35["bg"]["naehte"][3]["lage"] == "PF" and "nicht drehbar" in r35["bg"]["naehte"][3]["vk"]["lage"]["text"]
# Faktor PF 1,3 wirkt in der Zeit, Rechenweg nennt die Lage
n2 = r["bg"]["naehte"][1]
z_pf = baugruppe.naht_rechnen(n2, TAB, SAETZE)
z_ohne = baugruppe.naht_rechnen({k: v for k, v in n2.items() if k != "lage"}, TAB, SAETZE)
nah(z_pf["lichtbogen_min"], z_ohne["lichtbogen_min"] * 1.3, "PF × 1,3 auf die Lichtbogenzeit")
assert "Lage PF" in z_pf["rechenweg"]
# von Hand gewählte Lage bleibt, ohne Regel Schweißlage kein Vorschlag
b2 = bg_mit([naht(1, SENK, [["+Z"]] * 3, lage="PC")])
p2 = dict(art="Schweißbaugruppe", baugruppe=baugruppe.speichern(b2))
rh = vorkalk.vorkalkulieren(p2, [p2], TAB)
assert rh["bg"]["naehte"][0]["lage"] == "PC" and vorkalk.naht_status(rh["bg"]["naehte"][0], "lage") == vorkalk.HAND
p3 = dict(art="Schweißbaugruppe", baugruppe=baugruppe.speichern(bg_mit([naht(1, SENK, [["+Z"]] * 3)])))
assert "lage" not in vorkalk.vorkalkulieren(p3, [p3], TAB_ALT)["bg"]["naehte"][0], "ohne Regel wie bisher"
p4 = dict(art="Schweißbaugruppe", baugruppe=baugruppe.speichern(bg_mit([dict(naht(1, None, None))])))
assert "lage" not in vorkalk.vorkalkulieren(p4, [p4], TAB)["bg"]["naehte"][0], "ohne STEP kein Vorschlag"
# Wenden von Hand 0, obwohl zwei Lagen nötig: die Naht der zweiten Lage bleibt über Kopf
b5 = bg_mit([naht(1, WAAG, [["+Z"]] * 3), naht(2, WAAG, [["-Z"]] * 3)])
assert baugruppe.lagen_aus_step(b5)[0] == ("+Z", "-Z") and baugruppe.wenden_aus_step(b5)[0] == 1
p5 = dict(art="Schweißbaugruppe", baugruppe=baugruppe.speichern(b5))
r5 = vorkalk.vorkalkulieren(p5, [p5], TAB)
assert [n["lage"] for n in r5["bg"]["naehte"]] == ["PB", "PB"] and r5["bg"]["wenden"] == 1
b5 = r5["bg"]
b5.pop("wenden")                                    # von Hand: nicht wenden
p5 = dict(p5, baugruppe=baugruppe.speichern(b5))
r5 = vorkalk.vorkalkulieren(p5, [p5], TAB)
assert vorkalk.wenden_status(r5["bg"]) == vorkalk.HAND
assert [n["lage"] for n in r5["bg"]["naehte"]] == ["PB", "PE"], [n["lage"] for n in r5["bg"]["naehte"]]
# Lage fehlt in den Schweiß-Faktoren: Hinweis statt Vorschlag
TAB_OHNE_PF = dict(TAB, schweiss_faktoren=[z for z in FAKTOREN if z["wert"] != "PF"])
rf = vorkalk.vorkalkulieren(p3, [p3], TAB_OHNE_PF)
assert "lage" not in rf["bg"]["naehte"][0] and any("PF" in h and "fehlt" in h for h in rf["hinweise"])
ok("G1 Schweißlage: waagerecht PB, Stumpfnaht PA, senkrecht PF, Rundnaht 12 kg PA / 35 kg PF, ohne Wenden PE; "
   "Hand bleibt, ohne Regel oder STEP kein Vorschlag")

# ------------------------------------------------------------------ G4 Nahtvorbereitung (Fase)
b = bg_mit([dict(id="a", nr="1", verfahren="MAG", nahtart="Stumpfnaht", mass=6, laenge=500, anzahl=2),
            dict(id="b", nr="2", verfahren="MAG", nahtart="Stumpfnaht", mass=3, laenge=500, anzahl=2),     # dünn
            dict(id="c", nr="3", verfahren="MAG", nahtart="Kehlnaht", mass=5, dicke=8, laenge=500, anzahl=2),
            dict(id="d", nr="4", verfahren="MAG", nahtart="Ecknaht", mass=4, laenge=250, anzahl=1)])
p = dict(art="Schweißbaugruppe", baugruppe=baugruppe.speichern(b))
r = vorkalk.vorkalkulieren(p, [p], TAB)
ag = next(a for a in r["bg"]["arbeitsgaenge"] if (a.get("vk") or {}).get("art") == vorkalk.FASE)
nah(ag["zeit_min"], (1.0 + 0.25) * 3.0, "1 m Stumpfnaht 6 mm + 0,25 m Ecknaht 4 mm × 3 min/m")
assert ag["name"] == "Nahtvorbereitung (Fase)" and vorkalk.ag_status(ag) == vorkalk.VORSCHLAG
ralt = vorkalk.vorkalkulieren(p, [p], TAB_ALT)
assert not any((a.get("vk") or {}).get("art") == vorkalk.FASE for a in ralt["bg"]["arbeitsgaenge"])
# Teil trägt die Fase schon als Zusatzarbeit: kein Arbeitsgang
import json  # noqa: E402

teil = dict(art="Rohrlaserteil", bg_knoten=baugruppe.zuordnung_text(b["id"]), je_knoten=1,
            zusatz=json.dumps([dict(name="Schweißfase anfasen", menge=2)]))
from rohrlaser import rechnen  # noqa: E402

if rechnen.zusatz_liste(teil):
    pos = [p, teil]
    rz = vorkalk.vorkalkulieren(p, pos, TAB)
    assert not any((a.get("vk") or {}).get("art") == vorkalk.FASE for a in rz["bg"]["arbeitsgaenge"])
ok("G4 Nahtvorbereitung: Stumpf-/Ecknaht ab 4 mm × 3 min/m, dünne und Kehlnähte nicht, entfällt mit Zusatzarbeit "
   "Schweißfase am Teil, ohne Regel kein Arbeitsgang")
print("Alle Tests bestanden.")
