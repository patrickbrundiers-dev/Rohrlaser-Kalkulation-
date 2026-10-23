"""Prüft den Rechenkern der Schweißbaugruppen (Patrick 23.10.2026, Plan Schweißbaugruppen, PR 1):
- B1 Schema 46: Positionsart Schweißbaugruppe, Spalten baugruppe/bg_knoten/je_knoten, Schweiß-Stammdaten (leer)
- B2 Struktur: Mengen über Unterbaugruppen, Zyklen und unbekannte Knoten werden erkannt
- B3 Abgleich: Satz, Stück je Satz und Stückzahl der Teile folgen der Baugruppe
- B4 Nahtgruppen: Lichtbogenzeit × Faktoren ÷ Lichtbogenzeitfaktor + Heftpunkte, beidseitig, Zeit von Hand
- B5 Arbeitsgänge: laufend je Stück, Einmalkosten je Auftrag / anteilig / wiederverwendbar, Fremdleistung
- B6 Beispielbaugruppe (Plan 18.3) mit Handrechnung: Preis der Baugruppen-Position, Teile ohne Doppelrechnung
- B7 Status: Warnungen und Hinweise, nie still mit fehlenden Werten
- B8 Staffeln: Einmalkosten wie Rüsten (in der Stufe auf die Menge verteilt)
- B9 Angebot: Baugruppe als Satz mit Zeile 'Schweißen und Fertigung'; Kopie behält die Baugruppe
- B10 Richtwerte: hergeleitet (Nahtquerschnitt × Dichte ÷ Abschmelzleistung), Status Richtwert = HINWEIS
- B11 Editor (PR 2): Neue Position 'Schweißbaugruppe' mit markierten Teilen, Unterbaugruppe, Nahtgruppe, Vorrichtung
- B12 Editor: Bearbeiten über ein Einzelteil, gemerkte Kennwerte, Teil herausnehmen, Anzahl folgt in der Liste
- B13 Editor: Zyklus abgewiesen, ungültige Zahl, Status führt in den Editor
- B14 Richtwerte laden (nur fehlende Zeilen, eigene bleiben) und Arbeitsgang aus Zusatzarbeiten
- B15 Angebot/PDF: Stückliste per Häkchen, Einmalkosten als eigene Zeile und in den Staffeln 'zzgl. einmalig'
- B16 Schweißbaugruppe aus der STEP-Struktur: Grenzfälle (gemischte Unterbaugruppen, Rest, ohne Struktur)
- B17 Nachkalkulation: Soll/Ist je Baugruppe (Schweißen, Arbeitsgänge, Material/Einmal, Fremd), min/m Naht
- B18 Nahtkandidaten aus STEP als Vorschläge im Editor (Übernehmen/Verwerfen)
- B19 Sollwerte einmal je Stand (T1), Datenprüfung mit Ort (T5), Nahtgruppen gelb + Sprung vom Status (D4)
- B20 Baugruppen-Vorlagen speichern/einsetzen (P1), Baugruppe mit Teilen in ein anderes Angebot kopieren (P7)
- B21 Schweißplan in den Werkstattpapieren (P2), Baugruppe in Kalkulation-PDF und CSV-Export (P3)
- B22 a-Maß-Regel (P6), Schweißzusatz und Gas (P5), Kennwerte aus der Nachkalkulation (P4), Abweichungen (D5)
- B23 Positionsliste gruppiert: Einzelteile unter ihrer Baugruppe, zu-/aufklappen (D3)

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
assert BAUGRUPPE in db.kontext().auswahl("positionsart")
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
nah(fert["Schweißbaugruppe"], 10 * (114 - 65), "Baugruppe (laufend) in der Stufe 10")
ruest = dict((n, x) for n, x, _ in s10["bausteine"]["ruesten"])
nah(ruest["Schweißbaugruppe einmalig"], 130, "Einmalkosten der Baugruppe wie Rüsten")
ok(f"B8 Staffeln: 2 Sätze {s2['preis_einheit']:.2f} € (= Angebot), 10 Sätze {s10['preis_einheit']:.2f} € je Satz")

# ------------------------------------------------------------------ B9 Angebot, Kopie
ang = ausgabe.angebot(kopf, pos, zeilen, k, db.einstellungen())
satz = [z for z in ang["zeilen"] if z["art"] == "satz"]
assert len(satz) == 1 and satz[0]["menge"] == 2 and satz[0]["einheit"] == "Stk.", satz
assert satz[0]["text"].split("\n")[:3] == ["Schweißbaugruppe Rahmen R1", "Zeichnung Z-4711 Rev. B", "S235"], satz
assert not [z for z in ang["zeilen"] if z["art"] == "satzteil"], "Stückliste nur mit Häkchen"
kopie = db.angebot_kopieren(a)
pk = db.positionen(kopie)
assert baugruppe.lesen(pk[0]["baugruppe"])["id"] == rahmen["id"]
assert baugruppe.abgleich(pk) == [] and {p["bg_knoten"] for p in pk[1:]} == {p["bg_knoten"] for p in pos[1:]}
ok("B9 Angebot: eine Zeile 'Schweißbaugruppe Rahmen R1' (ohne Stückliste), Kopie behält Baugruppe und Zuordnung")

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

# ------------------------------------------------------------------ B11 Editor: neue Baugruppe
from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from rohrlaser.angebot_fenster import status_ziel  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.neue_position import SCHWEISS  # noqa: E402

app = QApplication.instance() or QApplication([])
a3 = db.angebot_neu(dict(kunde="Test", maschine="T11"))
r1 = db.position_neu(a3, dict(pos=10, artikel="Holm", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=900,
                              stueck=1, schneidweg=320, einstiche=2))
r2 = db.position_neu(a3, dict(pos=20, artikel="Konsole", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                              laenge=200, stueck=1, schneidweg=320, einstiche=2))
r3 = db.position_neu(a3, dict(pos=30, art=ZUKAUFTEIL, artikel="Lasche", stueck=1, zukauf=json.dumps([eintrag(lasche, 1)])))
f = Hauptfenster(db, stumm=True)
seite = f.angebot_oeffnen(a3)
for r in (0, 1):
    seite.pos_ansicht.selectionModel().select(seite.pos_modell.index(r, 0),
                                              QItemSelectionModel.Select | QItemSelectionModel.Rows)
gesehen = {}


def anlegen(d):
    gesehen["vorwahl"] = {t["_id"] for t in d.teile if t["drin"]}
    kid = d.knoten_neu("Konsole", 2)
    d.teil_setzen(r1, True, "", 4)
    d.teil_setzen(r2, True, kid, 1)
    d.bezeichnung.setText("Gestell G1")
    d.anzahl.setValue(3)
    # 2 × 100 mm Kehlnaht a3 je Konsole: 0,2 m × 1,5 min/m ÷ 0,40 = 0,75 min, × 2 Konsolen = 1,5 min = 1,875 €
    d.naht_neu(dict(knoten=kid, verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=100, anzahl=2))
    d.arbeitsgang_neu(dict(name="Vorrichtung", einmal_eur=300))           # je Auftrag: 300 € ÷ 3 = 100 €
    nah(d.erg["schweiss_min"], 1.5, "Schweißzeit im Editor")
    nah(d.erg["eigen"], 1.875 + 100, "eigen im Editor")
    gesehen["status"] = d.status
    d._ok()
    return d.result()


assert seite.position_neu(typ=SCHWEISS, dialog=anlegen) == SCHWEISS
assert gesehen["vorwahl"] == {r1, r2} and gesehen["status"] == "OK", gesehen
pos3 = {q["id"]: q for q in db.positionen(a3)}
bgp = next(q for q in pos3.values() if q.get("art") == BAUGRUPPE)
bg3 = baugruppe.lesen(bgp["baugruppe"])
assert bgp["stueck"] == 3 and bgp["satz"] == "Gestell G1" and bgp["bezeichnung"] == "Gestell G1"
assert (pos3[r1]["je_satz"], pos3[r1]["stueck"], pos3[r2]["je_satz"], pos3[r2]["stueck"]) == (4, 12, 2, 6)
assert pos3[r1]["satz"] == pos3[r2]["satz"] == "Gestell G1" and not pos3[r3].get("bg_knoten")
assert bg3["naehte"][0]["stand"]["min_m"] == 1.5 and len(bg3["knoten"]) == 1
zeile = seite.positionen.index(next(q for q in seite.positionen if q["id"] == bgp["id"]))
assert seite.pos_modell.status[zeile] == "OK", seite.pos_modell.status[zeile]
ok("B11 Editor: Gestell G1 mit Unterbaugruppe, Teile vorgewählt, Stückzahlen 12/6, Nahtgruppe mit Kennwert-Stand")

# ------------------------------------------------------------------ B12 Editor: bearbeiten
kw = db.zeilen("schweiss_kennwerte")
db.stammdaten_ersetzen({"schweiss_kennwerte": [dict(z, min_m=3.0) if z["mass_bis"] == 4 else z for z in kw]}, {}, "T")
seite.neu_laden()


def bearbeiten(d):
    nah(d.erg["schweiss_min"], 1.5, "gemerkter Kennwert")          # Stammdaten jetzt 3,0 min/m
    d.anzahl.setValue(5)
    d.teil_setzen(r2, False)
    d._ok()
    return d.result()


assert seite.baugruppe_bearbeiten([next(i for i, q in enumerate(seite.positionen) if q["id"] == r2)], dialog=bearbeiten)
pos3 = {q["id"]: q for q in db.positionen(a3)}
assert pos3[r1]["stueck"] == 20 and pos3[bgp["id"]]["stueck"] == 5
assert not pos3[r2].get("bg_knoten") and not pos3[r2].get("satz") and not pos3[r2].get("je_satz")
assert baugruppe.lesen(pos3[bgp["id"]]["baugruppe"])["naehte"][0]["stand"]["min_m"] == 1.5
db.position_aendern(bgp["id"], "stueck", 2)
seite.neu_laden()
assert next(q for q in seite.positionen if q["id"] == r1)["stueck"] == 8


def neu_rechnen(d):
    d.kennwerte_neu()
    nah(d.erg["schweiss_min"], 3.0, "Kennwerte neu aus Stammdaten")
    d.reject()
    return d.result()


assert not seite.baugruppe_bearbeiten([next(i for i, q in enumerate(seite.positionen) if q["id"] == bgp["id"])],
                                      dialog=neu_rechnen)
db.stammdaten_ersetzen({"schweiss_kennwerte": kw}, {}, "T")
ok("B12 Editor über Einzelteil geöffnet, gemerkte Kennwerte, Teil herausgenommen, Anzahl 2 → Holm 8 Stück")

# ------------------------------------------------------------------ B13 Editor: Prüfungen, Status
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
d = BaugruppeDialog(None, next(q for q in seite.positionen if q["id"] == bgp["id"]), seite.positionen, seite.tabellen,
                    saetze)
ka = d.knoten_neu("A")
kb = d.knoten_neu("B", parent=ka)
next(k for k in d.bg["knoten"] if k["id"] == ka)["parent"] = kb
d._struktur_geaendert()
assert next(k for k in d.bg["knoten"] if k["id"] == ka).get("parent") is None and "sich selbst" in d.fehler.text()
d.naht_tab.cellWidget(0, 5).setText("zwölf")
assert "Zahlen" in d.pruefen()
d.naht_tab.cellWidget(0, 5).setText("100")
assert d.pruefen() is None
d.reject()
for text in ("WARNUNG: Nahtgruppe 1: kein Kennwert für MAG Kehlnaht 3 mm", "WARNUNG: Baugruppe ohne Einzelteile",
             "WARNUNG: Pos. 10 hat zusätzlich Zusatzarbeit Schweißen (doppelt?)",
             "HINWEIS: Schweißzeit aus ungeprüften Richtwerten", "WARNUNG: Stundensatz fehlt (Schleifen)"):
    assert status_ziel(text)[0] == "baugruppe_bearbeiten", text
assert QDialog.Rejected == d.result()
ok("B13 Editor: Zyklus abgewiesen, ungültige Zahl gemeldet, Status der Baugruppe öffnet den Editor")

# ------------------------------------------------------------------ B14 Richtwerte laden, Arbeitsgang aus Katalog
eigen = {(z["verfahren"], z["nahtart"], z["mass_bis"]): z["min_m"] for z in db.zeilen("schweiss_kennwerte")}
fehlt = baugruppe.richtwerte_fehlend(db.tabellen())
assert all(z["verfahren"] != "MAG" for z in fehlt["schweissverfahren"])          # MAG ist schon da (geprüft)
assert ("MAG", "Kehlnaht", 4) not in {(z["verfahren"], z["nahtart"], z["mass_bis"]) for z in fehlt["schweiss_kennwerte"]}
seite_kw = next(s_ for s_ in f.seiten if s_.t.name == "schweiss_kennwerte")
n = seite_kw.schweiss_richtwerte(bestaetigt=True)
assert n == sum(len(x) for x in fehlt.values()) > 0
for z in db.zeilen("schweiss_kennwerte"):
    if (z["verfahren"], z["nahtart"], z["mass_bis"]) in eigen:
        assert z["min_m"] == eigen[(z["verfahren"], z["nahtart"], z["mass_bis"])] and z["status"] == "geprüft"
assert next(z for z in db.zeilen("schweissverfahren") if z["verfahren"] == "MAG")["lichtbogen"] == 40
assert seite_kw.schweiss_richtwerte(bestaetigt=True) == 0                        # zweimal: nichts doppelt
assert db.anzahl("schweiss_faktoren") == len(baugruppe.RICHT_FAKTOREN)            # PF war schon da
k_ = db.kontext()
for t_ in ("schweissverfahren", "schweiss_kennwerte", "schweiss_faktoren"):
    for z in db.zeilen(t_):
        assert pruefen(TABELLE[t_], z, k_) == "OK", (t_, z)
ag = baugruppe.arbeitsgang_vorlage(dict(name="Strahlen", art="€/Stück", preis=4.5, material=0.5, fremd="ja"))
assert (ag["name"], ag["kosten_einheit"], ag["fremd"], ag["vorlage"]) == ("Strahlen", 5.0, True, "Strahlen")
ag = baugruppe.arbeitsgang_vorlage(dict(name="Richten", art="€/h", zeit=90, zeit_einheit="s", satz_id="Schweißen"))
assert ag["satz_id"] == "Schweißen" and ag["zeit_min"] == 1.5 and "kosten_einheit" not in ag
assert baugruppe.arbeitsgang_vorlage(dict(name="Prüfprotokoll", art="€/Angebot", preis=80))["einmal_eur"] == 80
nah(baugruppe.arbeitsgang_rechnen(ag, saetze)["laufend"], 1.5 / 60 * 75, "Richten 1,5 min × 75 €/h")
d = BaugruppeDialog(None, next(q for q in seite.positionen if q["id"] == bgp["id"]), seite.positionen,
                    dict(seite.tabellen, zusatzarbeiten=[dict(name="Richten", art="€/h", zeit=2, zeit_einheit="min",
                                                              satz_id="Schweißen", aktiv="ja"),
                                                         dict(name="Gravur", art="s/Stück", preis=20)]),
                    saetze)
assert set(d._katalog()) == {"Richten"}
vorher = d.erg["eigen"]
d.arbeitsgang_aus_katalog("Richten")
nah(d.erg["eigen"] - vorher, 2 / 60 * 75, "Richten aus dem Katalog im Editor")
assert set(d.stamm_wahl) == {"stueckliste", "einmal_getrennt"} and not d.daten()["stamm"].get("stueckliste")
d.stamm_wahl["stueckliste"].setChecked(True)
assert d.daten()["stamm"]["stueckliste"] is True and "einmal_getrennt" not in d.daten()["stamm"]
d.reject()
f.close()
ok(f"B14 Richtwerte laden: {n} Zeilen neu, eigene MAG-Werte unverändert; Arbeitsgang aus Zusatzarbeiten")

# ------------------------------------------------------------------ B15 Angebot: Stückliste, Einmalkosten getrennt
from rohrlaser import pdf  # noqa: E402

kopf, pos, k, tab, einst = laden()
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
s10 = staffeln.stufe_rechnen(kopf, pos, "Rahmen R1", 10, k, tab, einst)
vorher = ausgabe.angebot(kopf, pos, zeilen, k, db.einstellungen(), [s10])
g = baugruppe.lesen(pos[0]["baugruppe"])
g["stamm"].update(stueckliste=True, einmal_getrennt=True)
db.position_aendern(pos[0]["id"], "baugruppe", baugruppe.speichern(g))
kopf, pos, k, tab, einst = laden()
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
zb = zeilen[0]
nah(zb["bg_einmal_preis_teil"], 65 * (1 + zf) * (1 + gew) / (1 - sk), "Einmalkosten-Preis je Baugruppe")
s10 = staffeln.stufe_rechnen(kopf, pos, "Rahmen R1", 10, k, tab, einst)
assert "Schweißbaugruppe einmalig" not in dict((n, x) for n, x, _ in s10["bausteine"]["ruesten"])
assert s10["preis"]["bg_einmalig"] == ausgabe.kaufm_runden(130 * (1 + zf) * (1 + gew) / (1 - sk), 2)
ang = ausgabe.angebot(kopf, pos, zeilen, k, db.einstellungen(), [s10])
arten = [(z["art"], z["pos"]) for z in ang["zeilen"]]
assert arten == [("satz", 100), ("einmal", None), ("satzteil", 10), ("satzteil", 20), ("satzteil", 30)], arten
bg_z, einmal_z = ang["zeilen"][0], ang["zeilen"][1]
nah(einmal_z["gesamt"], ausgabe.kaufm_runden(zb["bg_einmal_preis_teil"] * 2, 2), "eigene Zeile Einmalkosten")
assert einmal_z["einheit"] == "pausch." and einmal_z["menge"] == 1
nah(ang["netto"], vorher["netto"], "Summe gleich, nur anders aufgeteilt", 0.03)
assert bg_z["preis"] < vorher["zeilen"][0]["preis"]
st = bg_z["staffeln"][0]
nah(st["einmal"], s10["preis"]["bg_einmalig"], "Staffel: Einmalkosten getrennt")
nah(st["gesamt"], s10["preis_gesamt"], "Staffel gesamt unverändert", 0.11)
text = pdf._staffel_text(st, True)
assert text.startswith("Ab 10 Stk. je (zzgl. einmalig ") and text.endswith(" €)"), text
pdf.angebot_pdf(tmp / "bg.pdf", kopf, ang, db.einstellungen())
assert (tmp / "bg.pdf").stat().st_size > 0
ok(f"B15 Angebot: Stückliste per Häkchen, Einmalkosten {einmal_z['gesamt']:.2f} € als eigene Zeile, Staffel '{text}'")

# ------------------------------------------------------------------ B16 STEP-Struktur (Grenzfälle)
st = dict(knoten=[dict(id="K1", name="Gestell", eltern=None, menge=1), dict(id="K2", name="Seite", eltern="K1", menge=2),
                  dict(id="K3", name="Lasche", eltern="K2", menge=3)])
teile_ = [dict(je_satz=12), dict(je_satz=3), dict(je_satz=4), dict(je_satz=5)]
g, h = baugruppe.aus_step("G", st, [(teile_[0], ["K3"] * 12), (teile_[1], ["K1", "K2", "K2"]),
                                    (teile_[2], ["K2"] * 3 + ["K2"]), (teile_[3], ["K2"] * 3)])
assert [(x["id"], x["parent"], x["menge"]) for x in g["knoten"]] == [("K2", "", 2), ("K3", "K2", 3)]
assert [(q["bg_knoten"], q["je_knoten"]) for q in teile_] == [
    (g["id"] + "/K3", 2), (g["id"], 3), (g["id"] + "/K2", 2), (g["id"], 5)], teile_
assert h[0] is None and "mehreren" in h[1] and h[2] is None and "von Hand" in h[3]
q = dict(je_satz=3)
assert baugruppe.aus_step("G", dict(knoten=[dict(id="K1", eltern=None, menge=1), dict(id="K2", eltern="K1", menge=2)]),
                          [(q, ["K2"] * 3)])[1] == ["Stückzahl passt nicht zur Unterbaugruppe: direkt der Baugruppe "
                                                    "zugeordnet, prüfen"] and q["je_knoten"] == 3
g, h = baugruppe.aus_step("G", None, [(dict(je_satz=2), [None, None])])
assert g["knoten"] == [] and h == [None]
ok("B16 STEP-Struktur: Unterbaugruppen verschachtelt, gemischte Körper und Teilung mit Rest direkt an der Baugruppe")

# ------------------------------------------------------------------ B17 Nachkalkulation
from rohrlaser import nachkalkulation  # noqa: E402

v = nachkalkulation.vergleich(kopf, pos, erg, k, tab, einst, None, kalk=(zeilen, summen))
bgz = {z["text"]: z for z in v["zeilen"] if z["text"].startswith("Rahmen R1: ")}
assert list(bgz) == ["Rahmen R1: Schweißen", "Rahmen R1: Arbeitsgänge", "Rahmen R1: Material und Einmalbeträge",
                     "Rahmen R1: Fremdleistungen"], list(bgz)
r_ = baugruppe.rechnen(pos[0], tab, saetze)        # Kennwerte inzwischen mit Richtwerten (B14)
s_min, s_eur = r_["schweiss_min"], sum(x["kosten"] for x in r_["zeilen"] if x["art"] == "Naht")
nah(bgz["Rahmen R1: Schweißen"]["soll_menge"], s_min * 2 / 60, "Schweißen Soll h")
nah(bgz["Rahmen R1: Schweißen"]["soll"], s_eur * 2, "Schweißen Soll €")
nah(bgz["Rahmen R1: Arbeitsgänge"]["soll_menge"], (6 + 6) * 2 / 60 + 0.5, "Arbeitsgänge Soll h (laufend + Rüsten)")
nah(bgz["Rahmen R1: Arbeitsgänge"]["soll"], 12 * 2 + 30, "Arbeitsgänge Soll €")
nah(bgz["Rahmen R1: Material und Einmalbeträge"]["soll"], 100, "Vorrichtung anteilig")
nah(bgz["Rahmen R1: Fremdleistungen"]["soll"], 30, "Verzinken")
nah(sum(z["soll"] for z in bgz.values()), summen["baugruppe_eigen"] + summen["baugruppe_fremd"], "Summe = Kalkulation")
assert all(z["erfasst"] == "nein" and z["abweichung"] == 0 for z in bgz.values())
gid = baugruppe.lesen(pos[0]["baugruppe"])["id"]
ist = dict(baugruppen={gid: dict(schweiss_h=1.0, fremd=40, grund="Nacharbeit Naht 2")})
assert nachkalkulation.erfasst(ist) and nachkalkulation.erfasst(dict(baugruppen={gid: dict(grund="x")}))
v2 = nachkalkulation.vergleich(kopf, pos, erg, k, tab, einst, ist, kalk=(zeilen, summen))
z2 = {z["text"]: z for z in v2["zeilen"]}
nah(z2["Rahmen R1: Schweißen"]["ist"], 1.0 * s_eur * 2 / (s_min * 2 / 60), "Ist-Stunden mit dem Satz des Solls")
nah(z2["Rahmen R1: Fremdleistungen"]["ist"], 40, "Fremdleistung Ist")
nah(v2["summe"]["ist"] - v["summe"]["ist"], z2["Rahmen R1: Schweißen"]["abweichung"] + 10, "nur die Abweichungen")
b = v2["baugruppen"][0]
nah(b["naht_m"], (0.96 + 2.0 + 0.36) * 2, "Naht je Auftrag")
nah(b["soll_min_m"], s_min * 2 / 6.64, "Soll min/m")
nah(b["ist_min_m"], 60 / 6.64, "Ist min/m")
assert b["grund"] == "Nacharbeit Naht 2"
# ohne Baugruppe: keine zusätzlichen Zeilen
v3 = nachkalkulation.vergleich(kopf, pos[1:], erg2, k, tab, einst, None, kalk=(zeilen2, summen2))
assert len(v3["zeilen"]) == 6 and v3["baugruppen"] == []
# Reiter Nachkalkulation: Tabelle der Baugruppen, Ist-Werte gespeichert
nk_s = seite.nachkalk
nk_s.neu_laden()
assert not nk_s.bg_rahmen.isHidden() and nk_s.bg_tabelle.rowCount() == 1
nk_s.setzen_baugruppe(bg3["id"], schweiss_h=0.1, grund="Heftpunkte nachgesetzt")
assert db.angebot(a3)["nachkalkulation"]["baugruppen"][bg3["id"]]["schweiss_h"] == 0.1
assert nk_s.bg_tabelle.item(0, 2).text() == "0,10" and nk_s.bg_tabelle.item(0, 9).text() == "Heftpunkte nachgesetzt"
pdf.nachkalkulation_pdf(tmp / "nk.pdf", kopf, v2, ist)
assert (tmp / "nk.pdf").stat().st_size > 0
ok("B17 Nachkalkulation: Soll je Baugruppe = Kalkulation, Ist-Stunden mit Satz des Solls, min/m Naht, Reiter und PDF")

# ------------------------------------------------------------------ B18 Nahtkandidaten aus STEP als Vorschläge
st = dict(knoten=[dict(id="K1", name="Gestell", eltern=None, menge=1), dict(id="K2", name="Seite", eltern="K1", menge=2)])
kand = ([dict(teile=[1, 2], knoten="K2", laenge_mm=152.3, stossart="Kehlnaht", dicke_mm=3.0, status="prüfen")] * 4
        + [dict(teile=[3, 4], knoten="K1", laenge_mm=200.0, stossart="Stumpfnaht", dicke_mm=4.0, status="prüfen")]
        + [dict(teile=[5, 6], knoten="K2", laenge_mm=80.0, stossart="Ecknaht", dicke_mm=2.0, status="prüfen")])
g, _ = baugruppe.aus_step("G", st, [], kand)
vs = {(v["knoten"], v["nahtart"]): v for v in g["vorschlaege"]}
assert (vs[("K2", "Kehlnaht")]["anzahl"], vs[("K2", "Kehlnaht")]["laenge"]) == (2, 152)      # 4 ÷ Menge 2
assert vs[("", "Stumpfnaht")]["anzahl"] == 1 and vs[("", "Ecknaht")]["anzahl"] == 1       # 1 ÷ 2 geht nicht auf
assert not g["naehte"]                                                                        # nie automatisch
n_k, n_s = baugruppe.vorschlag_naht(vs[("K2", "Kehlnaht")]), baugruppe.vorschlag_naht(vs[("", "Stumpfnaht")])
assert "mass" not in n_k and n_s["mass"] == 4.0 and n_k["quelle"] == "STEP"
r_ = baugruppe.naht_rechnen(dict(n_k, verfahren="MAG"), db.tabellen(), saetze)
assert r_["zeit_min"] == 0 and r_["fehlt"] == "a-Maß fehlt"
p_bg = dict(pos=900, art=BAUGRUPPE, bezeichnung="G", stueck=1, baugruppe=baugruppe.speichern(g))
d = BaugruppeDialog(None, p_bg, [p_bg], db.tabellen(), saetze)
assert not d.vorschlag_rahmen.isHidden() and d.vorschlag_tab.rowCount() == 3
neu = d.vorschlaege_uebernehmen([0, 1])
assert len(neu) == 2 and len(d.bg["naehte"]) == 2 and d.vorschlag_tab.rowCount() == 1
d.vorschlaege_verwerfen([0])
assert d.vorschlag_rahmen.isHidden() and d.daten()["vorschlaege"] == []
assert {n["nahtart"] for n in d.daten()["naehte"]} == {"Kehlnaht", "Stumpfnaht"}
d.reject()
ok("B18 Nahtkandidaten: als Vorschläge gruppiert (Anzahl je Unterbaugruppe), erst nach Übernehmen Nahtgruppen, a-Maß offen")

# ------------------------------------------------------------------ B19 T1 Sollwerte einmal, T5 Datenprüfung, D4
zaehler = {"n": 0}
_soll_echt = baugruppe._soll_werte


def _soll_zaehlen(positionen):
    zaehler["n"] += 1
    return _soll_echt(positionen)


baugruppe._soll_werte = _soll_zaehlen
kopf, pos, k, tab, einst = laden()
for p in pos:
    rechnen.status(p, rechnen.position_werte(p, kopf, k, tab), kopf, k, None, pos)
assert zaehler["n"] == 1, zaehler                              # früher einmal je Einzelteil (und doppelt im Status)
assert baugruppe.soll_werte(pos) == _soll_echt(pos)
pos[0]["stueck"] = 3                                            # Änderung in derselben Liste: neu gerechnet
assert baugruppe.teil_pruefen(pos[1], pos) == "Stückzahl passt nicht zur Baugruppe (neu abgleichen)"
assert zaehler["n"] == 2
pos[0]["stueck"] = 2
assert baugruppe.teil_pruefen(pos[1], pos) is None
baugruppe._soll_werte = _soll_echt

g = json.loads(pos[0]["baugruppe"])
for text, erwartet in (
        ("kaputt{", "Baugruppendaten beschädigt (JSON, Zeile 1, Zeichen 1)"),
        (json.dumps(dict(g, id="")), "Baugruppendaten: Kennung der Baugruppe fehlt"),
        (json.dumps(dict(g, naehte={})), "Baugruppendaten: Nahtgruppen sind keine Liste ('naehte')"),
        (json.dumps(dict(g, arbeitsgaenge=g["arbeitsgaenge"] + [7])), "Baugruppendaten: Arbeitsgang Nr. 7 ist kein "
                                                                       "Datensatz"),
        (json.dumps(dict(g, naehte=g["naehte"] + [dict(g["naehte"][0], nr="9")])),
         "Baugruppendaten: Nahtgruppe 9 hat eine doppelte Kennung (n1)"),
        (json.dumps(dict(g, naehte=[dict(g["naehte"][0], id=["x"])])),
         "Baugruppendaten: Nahtgruppe 1 hat eine ungültige Kennung")):
    assert baugruppe.daten_fehler(text) == erwartet, (baugruppe.daten_fehler(text), erwartet)
    assert rechnen.status(dict(pos[0], baugruppe=text), w, kopf, k, None, pos) == "FEHLER: " + erwartet
assert baugruppe.daten_fehler(pos[0]["baugruppe"]) is None

zeile = next(i for i, q in enumerate(seite.positionen) if q["id"] == bgp["id"])
g3 = baugruppe.lesen(seite.positionen[zeile]["baugruppe"])
g3["naehte"] += [dict(id="nx", nr="2", verfahren="MAG", nahtart="Kehlnaht", laenge=50, anzahl=1),     # a-Maß fehlt
                 dict(id="ny", nr="3", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=50, anzahl=1)]
g3["arbeitsgaenge"].append(dict(id="ax", name="Schleifen", satz_id="gibtsnicht", zeit_min=2))
db.position_aendern(bgp["id"], "baugruppe", baugruppe.speichern(g3))
seite.neu_laden()
gesehen = {}


def ansehen(d):
    gesehen["warn"] = set(d.naht_tab.warnzeilen)
    gesehen["kopf"] = d.naht_tab.verticalHeaderItem(1).text()
    gesehen["reiter"] = d.reiter.currentIndex()
    gesehen["zeile"] = d.naht_tab.markierte()
    gesehen["ag"] = d.fokus("WARNUNG: Stundensatz fehlt (Schleifen)")
    gesehen["teil"] = d.fokus("WARNUNG: Pos. 10 hat zusätzlich Zusatzarbeit Schweißen (doppelt?)")
    gesehen["teil_zeile"] = d.teile_tab.markierte()
    d.reject()
    return d.result()


st = seite.pos_modell.status[zeile]
assert st == "WARNUNG: Nahtgruppe 2: a-Maß fehlt", st
aufruf = {}
seite.baugruppe_bearbeiten, echt = (lambda z, dialog=None, fokus=None: aufruf.update(z=z, fokus=fokus)), \
    seite.baugruppe_bearbeiten
assert seite.status_beheben(zeile) == "baugruppe_bearbeiten" and aufruf == dict(z=[zeile], fokus=st), aufruf
seite.baugruppe_bearbeiten = echt
assert not seite.baugruppe_bearbeiten([zeile], dialog=ansehen, fokus=st)
assert gesehen["warn"] == {1} and gesehen["kopf"] == "⚠ 2", gesehen
assert gesehen["reiter"] == 1 and gesehen["zeile"] == [1], gesehen
assert gesehen["ag"] == (2, len(g3["arbeitsgaenge"]) - 1), gesehen
teil_r = next(i for i, t in enumerate(BaugruppeDialog(None, seite.positionen[zeile], seite.positionen, seite.tabellen,
                                                      saetze).teile) if t["_q"].get("pos") == 10)
assert gesehen["teil"] == (0, teil_r) and gesehen["teil_zeile"] == [teil_r], gesehen
db.stammdaten_ersetzen({"schweiss_kennwerte": [dict(z, status="Richtwert") for z in kw]}, {}, "T")
seite.neu_laden()
d = BaugruppeDialog(None, seite.positionen[zeile], seite.positionen, seite.tabellen, saetze)
d.kennwerte_neu()
etikett = d.naht_tab.cellWidget(2, len(d.naht_tab.spalten) - 1).text()
assert "Richtwert&nbsp;</span>" in etikett and "background" in etikett, etikett
d.reject()
db.stammdaten_ersetzen({"schweiss_kennwerte": kw}, {}, "T")
r_ = baugruppe.rechnen(pos[0], tab, saetze)
teile_ = dict(baugruppe.kostenaufteilung(r_))
nah(sum(teile_.values()), r_["eigen"] + r_["fremd"], "Kostenbalken = eigen + fremd")
nah(teile_["Einmalkosten (umgelegt)"], 65, "Einmalkosten im Balken")
assert baugruppe.groesste_posten(r_)[0][0] == "Vorrichtung bauen", baugruppe.groesste_posten(r_)   # 50 € je BG
ub = seite.uebersicht_bereich
assert not ub.bg_bereich.isHidden() and len(ub.bg_balken) == 1 and ub.bg_balken[0].summe() > 0
nah(ub.bg_balken[0].summe(), sum(dict(baugruppe.kostenaufteilung(baugruppe.rechnen(
    seite.positionen[zeile], seite.tabellen, seite._saetze()))).values()), "Balken in der Übersicht")
ub.bg_balken[0].grab()                                           # zeichnet ohne Fehler
ok("B19 Sollwerte einmal je Stand, Datenfehler mit Ort, Nahtgruppe ohne a-Maß gelb, Sprung vom Status zur Zeile")

# ------------------------------------------------------------------ B20 P1 Vorlagen, P7 Kopie in anderes Angebot
assert SCHEMA_VERSION >= 49 and db.anzahl("baugruppen_vorlagen") == 0
zeile = next(i for i, q in enumerate(seite.positionen) if q["id"] == bgp["id"])
quelle = baugruppe.lesen(seite.positionen[zeile]["baugruppe"])
d = BaugruppeDialog(None, seite.positionen[zeile], seite.positionen, seite.tabellen, saetze, db=db)
vid = d.vorlage_speichern("Gestell", "für Folgeaufträge")
try:
    d.vorlage_speichern("Gestell")
    raise AssertionError("doppelter Name angenommen")
except ValueError as e:
    assert "gibt es schon" in str(e)
assert d.vorlage_speichern("Gestell", ueberschreiben=True) == vid
d.reject()
v = db.zeilen("baugruppen_vorlagen")[0]
vd = json.loads(v["daten"])
assert "id" not in vd and all("stand" not in n for n in vd["naehte"]) and "vorschlaege" not in vd
assert len(vd["naehte"]) == len(quelle["naehte"]) and v["inhalt"].startswith("1 Unterbaugruppe")
leer = dict(pos=900, art=BAUGRUPPE, stueck=1)
d = BaugruppeDialog(None, leer, seite.positionen, seite.tabellen, saetze, db=db)
alt_id = d.bg["id"]
assert d.vorlage_einsetzen(vid) and d.bg["id"] == alt_id and d.bg["vorlage"] == "Gestell"
assert d.knoten_tab.rowCount() == len(quelle["knoten"]) and d.naht_tab.rowCount() == len(quelle["naehte"])
assert d.ag_tab.rowCount() == len(quelle["arbeitsgaenge"]) and d.erg["schweiss_min"] > 0
assert not d.vorlage_einsetzen(12345) and "beschädigt" in d.fehler.text()
d.reject()
assert BaugruppeDialog(None, leer, seite.positionen, seite.tabellen, saetze).db is None      # ohne db: keine Vorlagen

seite.pos_ansicht.clearSelection()
seite.pos_ansicht.selectRow(zeile + 1)
mi = seite.pos_modell.index(zeile, 0)
seite._menue_zeile(seite.pos_ansicht.visualRect(mi).center())                # Rechtsklick auf andere Zeile
assert {x.row() for x in seite.pos_ansicht.selectedIndexes()} == {zeile}
vorher = db.positionen(a)
n = seite.baugruppe_kopieren([zeile], ziel=a)
nachher = db.positionen(a)
teile_quelle = baugruppe.teile(seite.positionen, quelle["id"])
assert n == 1 + len(teile_quelle) and len(nachher) == len(vorher) + n
neu_pos = nachher[len(vorher):]
g_neu = baugruppe.lesen(neu_pos[0]["baugruppe"])
assert g_neu["id"] != quelle["id"] and len(baugruppe.baugruppen(nachher)) == 2
assert all(baugruppe.zuordnung(q)[0] == g_neu["id"] for q in neu_pos[1:])
assert [q["pos"] for q in neu_pos] == [max(q["pos"] for q in vorher) + 10 * (k + 1) for k in range(n)]
assert baugruppe.abgleich(nachher) == [] and baugruppe.teil_pruefen(neu_pos[1], nachher) is None
assert {q["artikel"] for q in neu_pos[1:]} == {seite.positionen[j]["artikel"] for j in teile_quelle}
for q in neu_pos:
    db.positionen_loeschen([q["id"]])
ok(f"B20 Vorlage 'Gestell' ({v['inhalt']}) gespeichert und eingesetzt, Baugruppe mit {n - 1} Teilen kopiert")

# ------------------------------------------------------------------ B21 P2 Schweißplan, P3 Kalkulation-PDF und CSV
import zipfile as _zip  # noqa: E402
from rohrlaser import export  # noqa: E402

kopf, pos, k, tab, einst = laden()
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
plan = ausgabe.schweissplan(pos, tab)
assert len(plan) == 1 and plan[0]["name"] == "Rahmen R1" and plan[0]["anzahl"] == 2
b = plan[0]
r_ = baugruppe.rechnen(pos[0], tab, saetze)
nah(b["vorgabe_min"], r_["zeit_min"], "Vorgabezeit = Zeit der Kalkulation")
assert [t["pos"] for t in b["teile"]] == [10, 20, 30] and [n["nr"] for n in b["naehte"]] == ["1", "2", "3"]
assert b["struktur"][0]["name"] == "Querstrebe" and b["arbeitsgaenge"][2]["vorrichtung"]
assert b["arbeitsgaenge"][4]["fremd"] and b["naehte"][1]["beidseitig"]
assert not any("kosten" in x or "preis" in x for x in b["naehte"] + b["arbeitsgaenge"])     # ohne Preise
wp = ausgabe.werkstatt(kopf, pos, erg, k, tab)
assert wp["schweissplan"] == plan
pdf.werkstatt_pdf(tmp / "wp.pdf", kopf, wp, einst=db.einstellungen())
pdf.kalkulation_pdf(tmp / "kalk.pdf", kopf, zeilen, summen, db.einstellungen())
try:
    from pypdf import PdfReader  # noqa: E402
except ImportError:
    PdfReader = None
if PdfReader:
    text = "".join(s_.extract_text() for s_ in PdfReader(str(tmp / "wp.pdf")).pages)
    assert "Schweißplan Pos. 100 Rahmen R1" in text and "Nahtgruppen" in text and "€" not in text.split("Schweißplan")[1]
    text = "".join(s_.extract_text() for s_ in PdfReader(str(tmp / "kalk.pdf")).pages)
    assert "Schweißbaugruppe Pos. 100 R1" in text and "Nahtgruppe 2" in text and "von Hand" in text
bz = export.baugruppen_zeilen(pos, zeilen)
assert len(bz) == 1 and len(bz[0]) == len(export.BAUGRUPPE_SPALTEN)
werte = dict(zip(export.BAUGRUPPE_SPALTEN, bz[0]))
assert werte["Pos"] == "100" and werte["Anzahl"] == "2" and werte["Nahtgruppen"] == "3"
assert werte["Fertigung_EUR_je_BG"] == export.geld(114) and werte["Fremdleistung_EUR_je_BG"] == export.geld(15)
nah(float(werte["Nahtlaenge_m_je_BG"]), sum(r_["naht_m"].values()), "Nahtlänge im CSV", 1e-3)
kz, pz = export.daten(kopf, pos, erg, zeilen, summen, k, tab, einst)
export.zip_schreiben(tmp / "mit.zip", kz, pz, bz)
export.zip_schreiben(tmp / "ohne.zip", kz, pz, export.baugruppen_zeilen(pos[1:], zeilen[1:]))
assert export.BAUGRUPPE_DATEI in _zip.ZipFile(tmp / "mit.zip").namelist()
assert _zip.ZipFile(tmp / "ohne.zip").namelist() == [export.KOPF_DATEI, export.POSITION_DATEI]   # wie bisher
# nur Baugruppe und Zukaufteil, kein Laserteil: Werkstattpapiere trotzdem (nur Schweißplan)
a_nur = db.angebot_neu(dict(kunde="Test", maschine="T11"))
bg_nur = dict(rahmen, id=baugruppe.neue_id())
db.position_neu(a_nur, dict(pos=10, art=BAUGRUPPE, bezeichnung="Nur BG", stueck=1, baugruppe=baugruppe.speichern(bg_nur)))
db.position_neu(a_nur, dict(pos=20, art=ZUKAUFTEIL, artikel="Lasche", stueck=1, zukauf=json.dumps([eintrag(lasche, 1)]),
                            bg_knoten=bg_nur["id"], je_knoten=1))
s_nur = f.angebot_oeffnen(a_nur)
pfad_nur = s_nur.werkstatt_pdf()
assert pfad_nur and Path(pfad_nur).exists()
if PdfReader:
    assert "Schweißplan" in "".join(x.extract_text() for x in PdfReader(str(pfad_nur)).pages)
ok(f"B21 Schweißplan ({len(b['naehte'])} Nahtgruppen, Vorgabe {b['vorgabe_min']:.1f} min), Kalkulation-PDF und "
   "Schweissbaugruppen.csv nur mit Baugruppe")

# ------------------------------------------------------------------ B22 P6 a-Maß-Regel, P5 Verbrauch, P4 Kennwerte, D5
from rohrlaser import kennwerte  # noqa: E402
from rohrlaser.kennwerte_dialog import KennwerteDialog  # noqa: E402

assert [baugruppe.a_mass_regel(t) for t in (3, 4, 5, 0.5, None)] == [2.0, 2.5, 3.5, None, None]
assert baugruppe.a_mass_regel(4, 0.5) == 2.0
v_k = dict(knoten="", nahtart="Kehlnaht", laenge=150, anzahl=2, dicke=4.0)
assert "mass" not in baugruppe.vorschlag_naht(v_k)                                          # ohne Häkchen wie bisher
n_r = baugruppe.vorschlag_naht(v_k, 0.7)
assert n_r["mass"] == n_r["mass_regel"] == 2.5 and baugruppe.regel_offen(n_r)
g6 = baugruppe.leer()
g6["naehte"] = [dict(n_r, id="r1", nr="1", verfahren="MAG")]
p6 = dict(pos=910, art=BAUGRUPPE, stueck=1, baugruppe=baugruppe.speichern(g6))
w6 = dict(bg_tabellen=db.tabellen(), saetze=saetze)
t6 = dict(pos=10, artikel="T", stueck=1, bg_knoten=g6["id"], je_knoten=1)
for i_, f_, w_ in baugruppe.abgleich([p6, t6]):
    [p6, t6][i_][f_] = w_
st6 = baugruppe.status(p6, w6, [p6, t6])
assert "a-Maß nach Regel" in st6, st6
db.einstellung_setzen("schweiss_a_regel", 0.5)
d = BaugruppeDialog(None, p6, [p6], db.tabellen(), saetze, db=db)
assert d._regel_faktor() == 0.5
d.regel_bestaetigen()
assert not baugruppe.regel_offen(d.bg["naehte"][0]) and d.bg["naehte"][0]["mass"] == 2.5
d.reject()
db.einstellung_setzen("schweiss_a_regel", baugruppe.A_REGEL_VORGABE)

# P5: ohne Verbrauchswerte bitgleich, mit Werten Draht + Gas als Material der Nahtgruppe
n1 = dict(rahmen["naehte"][0])
tab0 = db.tabellen()
r0 = baugruppe.naht_rechnen(n1, tab0, saetze)
assert r0["material"] == 0 and r0["verbrauch_hinweis"] is None
tab_v = dict(tab0, schweissverfahren=[dict(z, dichte=7.85, draht_eur_kg=2.5, gas_l_min=12, gas_eur_l=0.02)
                                      for z in tab0["schweissverfahren"]])
r1 = baugruppe.naht_rechnen(n1, tab_v, saetze)
draht = baugruppe.nahtquerschnitt("Kehlnaht", 3) * 0.96 * 7.85 / 1000
nah(r1["draht_kg"], draht, "Draht kg")
nah(r1["gas_l"], r0["lichtbogen_min"] * 12, "Gas l")
nah(r1["material"], draht * 2.5 + r0["lichtbogen_min"] * 12 * 0.02, "Verbrauch €")
nah(r1["kosten"], r0["kosten"] + r1["material"], "Kosten mit Verbrauch")
r2 = baugruppe.naht_rechnen(n1, dict(tab0, schweissverfahren=[dict(z, gas_l_min=12)
                                                              for z in tab0["schweissverfahren"]]), saetze)
assert r2["material"] == 0 and "Dichte Zusatz" in r2["verbrauch_hinweis"] and "Preis Gas" in r2["verbrauch_hinweis"]
r3 = baugruppe.naht_rechnen(dict(n1, zeit_hand=10), tab_v, saetze)       # Zeit von Hand: Gas nicht still 0
assert r3["gas_l"] == 0 and "Zeit von Hand" in r3["verbrauch_hinweis"] and r3["draht_kg"] > 0
rr = baugruppe.rechnen(dict(pos=100, stueck=2, baugruppe=baugruppe.speichern(rahmen)), tab_v, saetze)
teile = dict(baugruppe.kostenaufteilung(rr))
nah(teile["Schweißzusatz und Gas"], rr["verbrauch"], "Kostenbalken Verbrauch")
nah(sum(teile.values()), rr["eigen"] + rr["fremd"], "Kostenbalken Summe")
assert len(baugruppe.kostenaufteilung(baugruppe.rechnen(dict(pos=100, stueck=2, baugruppe=baugruppe.speichern(rahmen)),
                                                         tab0, saetze))) == 4

# P4: sechs nachkalkulierte Angebote MAG/Kehlnaht, einer als Ausreißer
from rohrlaser.nachkalkulation import bewertung  # noqa: E402

nummern = []
for q in (1.2, 1.2, 1.1, 1.3, 1.25, 5.0):
    g = baugruppe.leer()
    g["vorlage"] = "Lernrahmen"
    g["naehte"] = [dict(id="n", knoten="", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=1000, anzahl=1)]
    g["naehte"][0]["stand"] = baugruppe.naht_stand(g["naehte"][0], db.tabellen())
    aid = db.angebot_neu(dict(kunde="Lernen", maschine="T11"))
    db.position_neu(aid, dict(pos=10, art=BAUGRUPPE, artikel="L", stueck=4, baugruppe=baugruppe.speichern(g)))
    soll_h = 1.5 / 0.4 * 4 / 60
    db.nachkalkulation_speichern(aid, dict(am="2026-10-23", baugruppen={g["id"]: dict(schweiss_h=soll_h * q)}))
    nummern.append(db.angebot(aid)["nummer"])
faelle = [f for f in kennwerte.faelle_schweissen(db) if f["angebot"] in nummern]
assert len(faelle) == 6 and all(f["schluessel"] == ("MAG", "Kehlnaht") for f in faelle)
nah(faelle[0]["soll"], 0.25, "Soll h")
e = kennwerte.auswerten(faelle)
nah(e["faktor"], 1.2, "Median ohne Ausreißer")
assert e["n"] == 5 and [f["angebot"] for f in e["ausreisser"]] == [nummern[5]] and e["status"] == "ok"
assert kennwerte.auswerten(faelle[:3])["status"] == "zu wenig Daten"
v_ = next(v for v in kennwerte.vorschlaege(db) if v["schluessel"] == ("MAG", "Kehlnaht"))
alt = {z["id"]: z["min_m"] for z in db.zeilen("schweiss_kennwerte")}
try:
    kennwerte.freigeben(db, v_, "  ", "x")
    raise AssertionError("ohne Begründung freigegeben")
except ValueError:
    pass
dlg = KennwerteDialog(None, db)
zeile_k = next(i for i, v in enumerate(dlg.vorschlaege) if v["schluessel"] == ("MAG", "Kehlnaht"))
f_ = dlg.vorschlaege[zeile_k]["faktor"]
hid = dlg.freigeben(zeile_k, "Test Nachkalkulation")
assert hid and dlg.geaendert and dlg.hist.rowCount() == 1
neu_k = {z["id"]: z for z in db.zeilen("schweiss_kennwerte")}
for zid, m in alt.items():
    z = neu_k[zid]
    soll_m = round(m * f_, 2) if (z["verfahren"], z["nahtart"]) == ("MAG", "Kehlnaht") else m
    nah(z["min_m"], soll_m, "freigegebener Kennwert")
h = kennwerte.historie(db)[0]
assert h["begruendung"] == "Test Nachkalkulation" and h["version"] and h["n"] >= 5
assert dlg.zuruecknehmen(0) == sum(1 for z in neu_k.values() if (z["verfahren"], z["nahtart"]) == ("MAG", "Kehlnaht"))
assert {z["id"]: z["min_m"] for z in db.zeilen("schweiss_kennwerte")} == alt and kennwerte.historie(db)[0]["zurueck"]
assert kennwerte.zuruecknehmen(db, hid) == 0                                     # zweimal geht nicht
dlg.reject()

# D5: Abweichung ab 10 % farbig, Verlauf je Vorlage
vl = kennwerte.verlauf_vorlage(db, "Lernrahmen")
assert len(vl) == 6 and [v["angebot"] for v in vl] == nummern and abs(vl[0]["faktor"] - 1.2) < 1e-9
assert kennwerte.verlauf_vorlage(db, "gibtsnicht") == [] and "vorlage" not in baugruppe.vorlage_aus(g)
assert bewertung(1.0, 1.1) == "hoch" and bewertung(1.0, 0.9) == "niedrig" and bewertung(1.0, 1.05) is None
assert bewertung(0, 1) is None and bewertung(1.0, None) is None
ok(f"B22 a-Maß-Regel (a = 0,7 × 4 → 2,5 mm, bestätigen), Zusatz/Gas {r1['material']:.2f} € je Nahtgruppe, "
   f"Kennwert-Vorschlag Faktor {e['faktor']:.2f} aus {e['n']} Fällen (1 Ausreißer), Freigabe zurückgenommen")

# ------------------------------------------------------------------ B23 D3 Positionsliste gruppiert
assert baugruppe.gruppen_reihenfolge(pos[1:]) == (list(range(len(pos) - 1)), {})          # ohne Baugruppe wie bisher
seite.neu_laden()
kopf_v = seite.pos_ansicht.verticalHeader()
folge, zu = baugruppe.gruppen_reihenfolge(seite.positionen)
from PySide6.QtCore import Qt  # noqa: E402

i_bg = next(i for i, q in enumerate(seite.positionen) if q["art"] == BAUGRUPPE)
t_bg = [j for j in zu if zu[j] == baugruppe.lesen(seite.positionen[i_bg]["baugruppe"])["id"]]
assert t_bg and folge.index(i_bg) + 1 == folge.index(min(t_bg))
assert [kopf_v.logicalIndex(v) for v in range(len(folge))] == folge
assert seite.pos_modell.headerData(i_bg, Qt.Vertical).startswith("▾") and \
    seite.pos_modell.headerData(t_bg[0], Qt.Vertical).startswith("└")
seite._kopf_klick(i_bg)
assert all(seite.pos_ansicht.isRowHidden(j) for j in t_bg) and seite.pos_modell.headerData(i_bg, Qt.Vertical)[0] == "▸"
seite.neu_laden()                                                             # bleibt zugeklappt
assert all(seite.pos_ansicht.isRowHidden(j) for j in t_bg)
seite._kopf_klick(i_bg)
assert not any(seite.pos_ansicht.isRowHidden(j) for j in t_bg)
ok(f"B23 Positionsliste: {len(t_bg)} Einzelteile unter ihrer Baugruppe, zu- und aufgeklappt")

print("\nAlle Baugruppen-Tests bestanden.")
