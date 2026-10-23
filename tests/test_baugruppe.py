"""Prüft den Rechenkern der Schweißbaugruppen (Patrick 23.10.2026, Plan Schweißbaugruppen, PR 1):
- B1 Schema 46: Positionsart Schweißbaugruppe, Spalten baugruppe/bg_knoten/je_knoten, Schweiß-Stammdaten (leer)
- B2 Struktur: Mengen über Unterbaugruppen, Zyklen und unbekannte Knoten werden erkannt
- B3 Abgleich: Satz, Stück je Satz und Stückzahl der Teile folgen der Baugruppe
- B4 Nahtgruppen: Lichtbogenzeit × Faktoren ÷ Lichtbogenzeitfaktor + Heftpunkte, beidseitig, Zeit von Hand
- B5 Arbeitsgänge: laufend je Stück, Einmalkosten je Auftrag / anteilig / wiederverwendbar, Fremdleistung
- B6 Beispielbaugruppe (Plan 18.3) mit Handrechnung: Preis der Baugruppen-Position, Teile ohne Doppelrechnung
- B7 Status: Warnungen und Hinweise, nie still mit fehlenden Werten
- B8 Staffeln: Einmalkosten verteilen sich auf die Menge der Stufe
- B9 Angebot: Baugruppe als Satz mit Zeile 'Schweißen und Fertigung'; Kopie behält die Baugruppe
- B10 Richtwerte: hergeleitet (Nahtquerschnitt × Dichte ÷ Abschmelzleistung), Status Richtwert = HINWEIS

Aufruf: python tests/test_baugruppe.py
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import ausgabe, baugruppe, rechnen, staffeln, zukauf  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE, POSITIONEN, ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "bg.db")

# ------------------------------------------------------------------ B1 Schema
assert SCHEMA_VERSION >= 46
spalten = {r[1] for r in db.con.execute("PRAGMA table_info(positionen)")}
assert {"baugruppe", "bg_knoten", "je_knoten"} <= spalten
for t in ("schweissverfahren", "schweiss_kennwerte", "schweiss_faktoren"):
    assert db.anzahl(t) == 0, t                      # leer ausgeliefert (Freigabe 4a)
assert BAUGRUPPE not in db.kontext().auswahl("positionsart")   # anlegen erst mit dem Baugruppen-Editor (PR 2)
assert POSITIONEN.feld("je_knoten").art == "ganz"
ok("B1 Schema 46: Positionsart Schweißbaugruppe, Spalten, Schweiß-Stammdaten leer")

# eigene, geprüfte Kennwerte für die Handrechnung
db.stammdaten_ersetzen({
    "schweissverfahren": [dict(verfahren="MAG", bezeichnung="MAG Hand", satz_id="Schweißen", lichtbogen=40, heft_s=6,
                               aktiv="ja", status="geprüft")],
    "schweiss_kennwerte": [dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=4, min_m=1.5, status="geprüft"),
                           dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=6, min_m=2.4, status="geprüft"),
                           dict(verfahren="MAG", nahtart="Stumpfnaht", mass_bis=5, min_m=3.0, status="geprüft")],
    "schweiss_faktoren": [dict(art="Schweißlage", wert="PF", faktor=1.2, status="geprüft")],
}, {}, "Test")
db.einstellung_setzen("mindestpreis", 0.0)
tab = db.tabellen()
saetze = rechnen.stundensaetze(tab)
assert saetze["Schweißen"] == 75

# ------------------------------------------------------------------ B2 Struktur
bg = baugruppe.leer()
bg["knoten"] = [dict(id="k1", parent="", name="Querstrebe", menge=1),
                dict(id="k2", parent="k1", name="Konsole", menge=3)]
assert baugruppe.faktor(bg, "") == 1 and baugruppe.faktor(bg, "k1") == 1 and baugruppe.faktor(bg, "k2") == 3
bg["knoten"][0]["menge"] = 2
assert baugruppe.faktor(bg, "k2") == 6
assert not baugruppe.darf_unter(bg, "k1", "k2") and baugruppe.darf_unter(bg, "k2", "")
zyklus = json.loads(baugruppe.speichern(bg))
zyklus["knoten"][0]["parent"] = "k2"
assert "enthält sich selbst" in baugruppe.struktur_fehler(baugruppe.lesen(json.dumps(zyklus)))
assert baugruppe.faktor(baugruppe.lesen(json.dumps(zyklus)), "k2") is None
fremd = json.loads(baugruppe.speichern(bg))
fremd["knoten"][1]["parent"] = "gibtsnicht"
assert "übergeordnete Baugruppe fehlt" in baugruppe.struktur_fehler(baugruppe.lesen(json.dumps(fremd)))
assert baugruppe.lesen("kaputt{") is None and baugruppe.lesen("") is None
ok("B2 Mengen über Unterbaugruppen (2 × 3 = 6), Zyklus und unbekannter Knoten erkannt")

# ------------------------------------------------------------------ Beispielbaugruppe (Plan 18.3)
schraube = db.zukauf_speichern(None, dict(artikelnr="Z-M8", bezeichnung="Schraube M8x25", einheit="Stück",
                                          aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT,
                                          aufschlag_wert=0),
                               [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=0.10)])])
lasche = db.zukauf_speichern(None, dict(artikelnr="Z-L", bezeichnung="Blechlasche 80x60x8", einheit="Stück",
                                        aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT,
                                        aufschlag_wert=0),
                             [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=1.50)])])


def eintrag(aid, menge):
    return dict(artikel_id=aid, menge=menge, stand=db.zukauf_stand(aid))


rahmen = baugruppe.leer()
rahmen["stamm"] = dict(zeichnung="Z-4711", revision="B", werkstoff="S235")
rahmen["knoten"] = [dict(id="k1", parent="", name="Querstrebe", menge=1)]
rahmen["naehte"] = [
    # N1 Kehlnaht a3, 8 × 120 mm, 2 Heftpunkte je Naht: 0,96 m × 1,5 min/m = 1,44 min ÷ 0,40 = 3,6 min + 16 × 6 s
    dict(id="n1", knoten="", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=120, anzahl=8,
         heftpunkte=2, lage="PA"),
    # N2 Kehlnaht a5, 4 × 250 mm beidseitig, Steigend (PF 1,2): 2,0 m × 2,4 × 1,2 = 5,76 min ÷ 0,40 = 14,4 min
    dict(id="n2", knoten="k1", nr="2", verfahren="MAG", nahtart="Kehlnaht", mass=5, laenge=250, anzahl=4,
         beidseitig=True, lage="PF"),
    # N3 Stumpfnaht t = 4, 2 × 180 mm, Zeit von Hand 10 min
    dict(id="n3", knoten="", nr="3", verfahren="MAG", nahtart="Stumpfnaht", mass=4, laenge=180, anzahl=2,
         zeit_hand=10)]
rahmen["arbeitsgaenge"] = [
    dict(id="a1", knoten="", name="Schleifen", satz=60, zeit_min=6, menge=1),                       # 6,00 €
    dict(id="a2", knoten="", name="Vorrichten", satz=60, ruest_min=30),                             # 30 € einmal
    dict(id="a3", knoten="", name="Vorrichtung bauen", einmal_eur=400, umlage="anteilig", anteil=25),  # 100 €
    dict(id="a4", knoten="", name="Schweißlehre", einmal_eur=250, umlage="wiederverwendbar"),     # 0 €
    dict(id="a5", knoten="", name="Verzinken", fremd=True, kosten_einheit=1.20, menge=12.5),       # 15,00 € fremd
    dict(id="a6", knoten="k1", name="Querstrebe ausrichten", satz=60, zeit_min=3, menge=2)]         # 6,00 €

a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
p_bg = db.position_neu(a, dict(pos=100, art=BAUGRUPPE, artikel="R1", bezeichnung="Rahmen R1", stueck=2,
                               baugruppe=baugruppe.speichern(rahmen),
                               zukauf=json.dumps([eintrag(schraube, 8)])))
p10 = db.position_neu(a, dict(pos=10, artikel="Rohr", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                              laenge=1000, stueck=1, schneidweg=320, einstiche=2,
                              bg_knoten=rahmen["id"], je_knoten=4))
p20 = db.position_neu(a, dict(pos=20, artikel="Strebe", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                              laenge=800, stueck=1, schneidweg=320, einstiche=2,
                              bg_knoten=baugruppe.zuordnung_text(rahmen["id"], "k1"), je_knoten=1))
p30 = db.position_neu(a, dict(pos=30, art=ZUKAUFTEIL, artikel="Lasche", bezeichnung="Blechlasche", stueck=1,
                              zukauf=json.dumps([eintrag(lasche, 1)]),
                              bg_knoten=baugruppe.zuordnung_text(rahmen["id"], "k1"), je_knoten=2))


def laden():
    kopf = db.angebot(a)
    return kopf, db.positionen(a), db.kontext(), db.tabellen(), rechnen.einstellungen_angebot(kopf, db.einstellungen())


# ------------------------------------------------------------------ B3 Abgleich
kopf, pos, k, tab, einst = laden()
aend = baugruppe.abgleich(pos)
assert aend, "Teile müssen abgeglichen werden"
w = rechnen.position_werte(pos[1], kopf, k, tab)
assert "Baugruppe" in rechnen.status(pos[1], w, kopf, k, None, pos)          # vor dem Abgleich: Warnung
for i, feld, wert in aend:
    db.position_aendern(pos[i]["id"], feld, wert)
kopf, pos, k, tab, einst = laden()
assert baugruppe.abgleich(pos) == []
soll = {10: ("Rahmen R1", 4, 8), 20: ("Rahmen R1", 1, 2), 30: ("Rahmen R1", 2, 4), 100: ("Rahmen R1", 1, 2)}
for p in pos:
    assert (p["satz"], p["je_satz"], p["stueck"]) == soll[p["pos"]], (p["pos"], p["satz"], p["je_satz"], p["stueck"])
ok("B3 Abgleich: Satz 'Rahmen R1', Stück je Satz 4/1/2, Stückzahl 8/2/4 bei 2 Baugruppen")

# ------------------------------------------------------------------ B4 Nahtgruppen
r1 = baugruppe.naht_rechnen(rahmen["naehte"][0], tab, saetze)
nah(r1["naht_m"], 0.96, "N1 Naht")
nah(r1["lichtbogen_min"], 1.44, "N1 Lichtbogen")
nah(r1["heft_min"], 1.6, "N1 Heften")
nah(r1["zeit_min"], 5.2, "N1 Zeit")
nah(r1["kosten"], 6.5, "N1 Kosten")
r2 = baugruppe.naht_rechnen(rahmen["naehte"][1], tab, saetze)
nah(r2["naht_m"], 2.0, "N2 beidseitig")
nah(r2["zeit_min"], 14.4, "N2 Zeit")
r3 = baugruppe.naht_rechnen(rahmen["naehte"][2], tab, saetze)
assert r3["hand"] and r3["fehlt"] is None
nah(r3["kosten"], 12.5, "N3 von Hand")
r4 = baugruppe.naht_rechnen(dict(rahmen["naehte"][0], mass=8), tab, saetze)    # a8 > größter Kennwert
assert r4["zeit_min"] == 0 and "kein Kennwert" in r4["fehlt"]
ok("B4 Nahtgruppen: 5,2 min (6,50 €), beidseitig PF 14,4 min (18,00 €), von Hand 10 min; a8 ohne Kennwert")

# ------------------------------------------------------------------ B5 Arbeitsgänge, Einmalkosten
r = baugruppe.rechnen(pos[0], tab, saetze)
nah(r["schweiss_min"], 5.2 + 14.4 + 10, "Schweißzeit je Baugruppe")
nah(r["einmal_gesamt"], 30 + 100, "Einmalkosten je Auftrag")
nah(r["einmal"], 65, "Einmal je Baugruppe bei 2 Stück")
nah(r["eigen"], 6.5 + 18 + 12.5 + 6 + 15 + 50 + 6, "eigen je Baugruppe")             # 114,00 €
nah(r["fremd"], 15, "Fremdleistung je Baugruppe")
assert r["wiederverwendbar"] == 1 and not r["warnungen"]
r10 = baugruppe.rechnen(pos[0], tab, saetze, anzahl=10)
nah(r10["eigen"], 114 - 65 + 13, "eigen je Baugruppe bei 10 Stück")
assert sum(nt["naht_m"] for nt in [r1, r2, r3]) == sum(r["naht_m"].values())
ok("B5 Arbeitsgänge: 114,00 € Fertigung + 15,00 € Fremdleistung je Baugruppe; Einmal 130 € auf 2 bzw. 10 verteilt")

# ------------------------------------------------------------------ B6 Kalkulation mit Handrechnung
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
zf, zfl, gew = (einst.get(n) or 0 for n in ("zuschlag_fertigung", "zuschlag_fremdleistung", "gewinn"))
herstell = 114 * (1 + zf) + 15 * (1 + zfl)
sk = (kopf.get("skonto") or 0) / 100
preis = (herstell * (1 + gew) + 8 * 0.10) / (1 - sk)       # + 8 Schrauben je Baugruppe à 0,10 € (ohne Aufschlag)
zb = zeilen[0]
nah(zb["herstell_teil"], herstell, "Herstellkosten je Baugruppe")
nah(zb["preis_teil"] - zb["fracht_teil"] / (1 - sk), preis, "Preis der Baugruppen-Position je Baugruppe")
assert zb["material_teil"] == 0 and zb["laser_teil"] == 0 and zb["baugruppe"]
nah(summen["baugruppe_eigen"], 228, "Summe Schweißbaugruppen")
nah(summen["baugruppe_fremd"], 30, "Summe Fremdleistung Baugruppen")
nah(summen["verkauf"], sum(z["preis_position"] for z in zeilen if z), "Summe Verkauf")
kosten = dict((n, w) for (_, w, _), (_, n, _) in zip(rechnen.kostenarten(summen, einst), rechnen.KOSTENARTEN))
nah(kosten["baugruppe_eigen"], 228, "Kostenart")
# ohne Baugruppe (gleiche Teile, gleiche Stückzahlen): Teile rechnen genau gleich, nichts doppelt
ohne = [dict(p, bg_knoten=None, je_knoten=None) for p in pos[1:]]
erg2 = rechnen.optimieren(kopf, ohne, k, tab, einst)
zeilen2, summen2 = rechnen.kalkulation(kopf, ohne, erg2, k, tab, einst)
for z1, z2 in zip(zeilen[1:], zeilen2):
    for n in ("material_teil", "laser_teil", "ruesten_teil", "zukauf_teil", "herstell_teil"):
        assert z1[n] == z2[n], (n, z1[n], z2[n])
assert summen2["baugruppe_eigen"] == 0 and summen2["baugruppen"] == 0
nah(summen["herstell"] - summen2["herstell"], 2 * herstell, "Herstellkosten nur um die Baugruppe höher")
ok(f"B6 Rahmen R1: Herstellkosten {herstell:.2f} €, Preis {preis:.2f} € je Baugruppe; Teile ohne Doppelrechnung")

# ------------------------------------------------------------------ B7 Status
w = rechnen.position_werte(pos[0], kopf, k, tab)
st = rechnen.status(pos[0], w, kopf, k, None, pos)
assert st == "HINWEIS: wiederverwendbare Vorrichtung nicht berechnet", st
for p in pos[1:]:
    st_t = rechnen.status(p, rechnen.position_werte(p, kopf, k, tab), kopf, k, None, pos)
    assert "Baugruppe" not in st_t, (p["pos"], st_t)
fall = [dict(pos[0], baugruppe=baugruppe.speichern(dict(rahmen, naehte=[dict(rahmen["naehte"][0], mass=8)])))] + pos[1:]
assert rechnen.status(fall[0], w, kopf, k, None, fall).startswith("WARNUNG: Nahtgruppe 1: kein Kennwert")
fall = [dict(pos[0], baugruppe=baugruppe.speichern(dict(rahmen, arbeitsgaenge=[dict(id="x", name="X", satz=60,
                                                                                    zeit_min=-1)])))] + pos[1:]
assert rechnen.status(fall[0], w, kopf, k, None, fall).startswith("FEHLER:")
assert rechnen.status(pos[0], w, kopf, k, None, pos[:1]) == "WARNUNG: Baugruppe ohne Einzelteile"
fall = [pos[0], dict(pos[1], zusatz=json.dumps([dict(name="Schweißen", menge=30)]))] + pos[2:]
assert "Zusatzarbeit Schweißen" in rechnen.status(pos[0], w, kopf, k, None, fall)
fall = [dict(pos[0], baugruppe=baugruppe.speichern(dict(rahmen, arbeitsgaenge=[dict(id="x", name="Montage",
                                                                                    satz_id="gibtsnicht",
                                                                                    zeit_min=5)])))] + pos[1:]
assert rechnen.status(fall[0], w, kopf, k, None, fall) == "WARNUNG: Stundensatz fehlt (Montage)"
lose = dict(pos[1], bg_knoten="weg")
assert rechnen.status(lose, rechnen.position_werte(lose, kopf, k, tab), kopf, k, None, [pos[0], lose]) == \
    "WARNUNG: Baugruppe der Zuordnung fehlt"
assert rechnen.status(dict(pos[0], stueck=None), w, kopf, k, None, pos).startswith("FEHLER: Stückzahl")
ok("B7 Status: wiederverwendbare Vorrichtung (HINWEIS), Kennwert/Stundensatz fehlt, doppelt Schweißen, ohne Teile")

# ------------------------------------------------------------------ B8 Staffeln
s2 = staffeln.stufe_rechnen(kopf, pos, "Rahmen R1", 2, k, tab, einst)
s10 = staffeln.stufe_rechnen(kopf, pos, "Rahmen R1", 10, k, tab, einst)
assert s2["einheit"] == "Satz" and s2["preis_einheit"] is not None, s2.get("hinweis")
satzpreis = sum(z["preis_teil"] * p["je_satz"] for z, p in zip(zeilen, pos))
nah(s2["preis_einheit"], round(satzpreis, 2), "Stufe 2 Sätze = Satzpreis des Angebots", 0.011)
assert s10["preis_einheit"] < s2["preis_einheit"]
fert = dict((n, x) for n, x, _ in s10["bausteine"]["fertigung"])
nah(fert["Schweißbaugruppe"], 10 * (114 - 65 + 13), "Baugruppe in der Stufe 10")
ok(f"B8 Staffeln: 2 Sätze {s2['preis_einheit']:.2f} € (= Angebot), 10 Sätze {s10['preis_einheit']:.2f} € je Satz")

# ------------------------------------------------------------------ B9 Angebot, Kopie
ang = ausgabe.angebot(kopf, pos, zeilen, k, db.einstellungen())
satz = [z for z in ang["zeilen"] if z["art"] == "satz"]
assert len(satz) == 1 and satz[0]["menge"] == 2 and satz[0]["text"] == "Satz Rahmen R1"
teile = [z["text"] for z in ang["zeilen"] if z["art"] == "satzteil"]
assert any("Schweißen und Fertigung der Baugruppe" in t and "Zeichnung Z-4711 Rev. B" in t for t in teile), teile
kopie = db.angebot_kopieren(a)
pk = db.positionen(kopie)
assert baugruppe.lesen(pk[0]["baugruppe"])["id"] == rahmen["id"]
assert baugruppe.abgleich(pk) == [] and {p["bg_knoten"] for p in pk[1:]} == {p["bg_knoten"] for p in pos[1:]}
ok("B9 Angebot: Satz 'Rahmen R1' mit Zeile 'Schweißen und Fertigung', Kopie behält Baugruppe und Zuordnung")

# ------------------------------------------------------------------ B10 Richtwerte
rw = baugruppe.richtwerte()
mag3 = next(z for z in rw["schweiss_kennwerte"] if (z["verfahren"], z["nahtart"], z["mass_bis"]) == ("MAG", "Kehlnaht", 3))
nah(mag3["min_m"], round(9 * 1.1 * 7.85 / 1000 / 3.5 * 60, 2), "MAG a3")      # 1,33 min/m
v4 = next(z for z in rw["schweiss_kennwerte"] if (z["verfahren"], z["nahtart"], z["mass_bis"]) == ("MAG", "Stumpfnaht", 4))
nah(v4["min_m"], round((16 * math.tan(math.radians(30)) + 6) * 1.1 * 7.85 / 1000 / 3.5 * 60, 2), "MAG V4")
assert all(z["status"] == "Richtwert" for t in rw.values() for z in t)
db2 = Datenbank(tmp / "rw.db")
db2.stammdaten_ersetzen(rw, {}, "Richtwerte")
k2 = db2.kontext()
from rohrlaser.stammdaten import TABELLE, pruefen  # noqa: E402
for t in ("schweissverfahren", "schweiss_kennwerte", "schweiss_faktoren"):
    for z in db2.zeilen(t):
        assert pruefen(TABELLE[t], z, k2) == "OK", (t, z, pruefen(TABELLE[t], z, k2))
st = baugruppe.naht_stand(rahmen["naehte"][0], db2.tabellen())
assert st["richtwert"] and st["min_m"] == mag3["min_m"]
p_rw = dict(pos[0], baugruppe=baugruppe.speichern(dict(rahmen, arbeitsgaenge=[], naehte=rahmen["naehte"][:1])))
w2 = rechnen.position_werte(p_rw, kopf, k2, db2.tabellen())
assert rechnen.status(p_rw, w2, kopf, k2, None, [p_rw] + pos[1:]) == "HINWEIS: Schweißzeit aus ungeprüften Richtwerten"
# gemerkter Stand gilt vor den Stammdaten (spätere Änderungen verändern das Angebot nicht)
gemerkt = dict(rahmen["naehte"][0], stand=baugruppe.naht_stand(rahmen["naehte"][0], tab))
nah(baugruppe.naht_rechnen(gemerkt, db2.tabellen(), saetze)["zeit_min"], 5.2, "Stand der Nahtgruppe")
ok(f"B10 Richtwerte hergeleitet (MAG Kehlnaht a3 {mag3['min_m']} min/m), prüfbar, Status Richtwert = HINWEIS")

print("\nAlle Baugruppen-Tests bestanden.")
