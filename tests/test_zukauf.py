"""Prüft den Rechenkern und die Datenhaltung der Zukaufartikel (zukauf.py, datenbank.zukauf_*).

Testplan (Plan_Zukaufartikel.md, Abschnitt 3): 3 Umrechnung Preiseinheit, 4 Aufschlagsmethoden, 5 Priorität
Position > Artikel > Kategorie > Standard, 6 Aufschlag und Zielmarge, 7 Einkaufsstaffel, 8 Mindestmenge und
Verpackungseinheit, 11 Bezugskosten nur einmal; dazu Speichern, Prüfungen, Preisprotokoll und Datei der
Vorversion (Schema 15). Alle Preise sind Testwerte.

Aufruf: python tests/test_zukauf.py
"""
import shutil
import sqlite3
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import zukauf  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())
D = Decimal


def ok(text):
    print("OK    ", text)


def gleich(a, b, text):
    assert a == b, f"{text}: {a!r} statt {b!r}"


def artikel(**w):
    a = dict(bezeichnung="Testartikel", einheit="Stück")
    a.update(w)
    return a


def bezug(preise, pe=1, **w):
    b = dict(lieferant="Lieferant A", preiseinheit=pe, preise=[dict(ab=ab, preis=p) for ab, p in preise])
    b.update(w)
    return b


def je_einheit(a, b, verbrauch, kat=None, std=None):
    return zukauf.vorschau(a, b, kat, std, verbrauch)


# ------------------------------------------------------------------ 3 Umrechnung
ek, _ = zukauf.ek_je_einheit(bezug([(1, 12.00)], pe=100), 100)
gleich(ek, D("0.12"), "12,00 € je 100 Stück")
ek, _ = zukauf.ek_je_einheit(bezug([(1, 8.40)], pe=1), 3)
gleich(ek, D("8.4"), "8,40 € je Meter")
ek, _ = zukauf.ek_je_einheit(bezug([(1, 100.00)], pe=100, rabatt=10), 1)
gleich(ek, D("0.9"), "Rabatt 10 %")
v = je_einheit(artikel(), bezug([(1, 0.0835)]), 2000)
gleich(v["bestellung"]["einkauf"], D("167.0000"), "0,0835 € × 2.000 ohne Gleitkommafehler")
gleich(zukauf.runden(v["bestellung"]["ek"], zukauf.STELLEN_EINHEIT), 0.0835, "Einheitspreis 4 Stellen")
ok("3 Einkaufspreis je Preiseinheit umgerechnet (12,00 €/100 St = 0,12 €/St), Rabatt, Decimal")

# ------------------------------------------------------------------ 4 Aufschlagsmethoden
b10 = bezug([(1, 10.00)])
ind = lambda m, w=None, st=None: artikel(aufschlag_quelle="individuell", aufschlag_methode=m, aufschlag_wert=w,
                                         aufschlag_staffel=st)
gleich(je_einheit(ind(zukauf.PROZENT, 25), b10, 1)["vk"], D("12.5"), "25 % auf 10 €")
gleich(je_einheit(ind(zukauf.JE_EINHEIT, 1.5), b10, 4)["vk"], D("46"), "1,50 € je Einheit × 4")
gleich(je_einheit(ind(zukauf.JE_BESTELLUNG, 5), b10, 4)["vk"], D("45"), "5 € je Bestellung")
staffel = [dict(ab=1, wert=30), dict(ab=100, wert=20), dict(ab=500, wert=10)]
gleich(je_einheit(ind(zukauf.STAFFEL, st=staffel), b10, 99)["aufschlag_pct"], D("30"), "Staffel 99")
gleich(je_einheit(ind(zukauf.STAFFEL, st=staffel), b10, 100)["aufschlag_pct"], D("20"), "Staffel 100")
gleich(je_einheit(ind(zukauf.STAFFEL, st=staffel), b10, 600)["aufschlag_pct"], D("10"), "Staffel 600")
ok("4 Aufschlag % auf Einstand, € je Einheit, € je Bestellung, Mengenstaffel")

# ------------------------------------------------------------------ 5 Priorität
kat = {"Blech": dict(name="Blech", aufschlag_methode=zukauf.PROZENT, aufschlag_wert=20, aktiv="ja"),
       "Leer": dict(name="Leer", aktiv="ja")}
pct = lambda a, std=None: je_einheit(a, b10, 1, kat, std)["aufschlag_pct"]
gleich(pct(artikel(kategorie="Blech"), 10), D("20"), "Kategorie vor Standard")
gleich(pct(artikel(kategorie="Leer"), 10), D("10"), "Standard, wenn Kategorie keinen hat")
gleich(pct(artikel(kategorie="Leer")), D("0"), "kein Aufschlag")
gleich(je_einheit(artikel(kategorie="Leer"), b10, 1, kat)["warnung"], "kein Aufschlag hinterlegt", "Warnung")
gleich(pct(artikel(kategorie="Blech", aufschlag_quelle="individuell", aufschlag_methode=zukauf.PROZENT,
                   aufschlag_wert=25), 10), D("25"), "individuell ersetzt Kategorie")
gleich(pct(artikel(kategorie="Blech", aufschlag_quelle="individuell", aufschlag_methode=zukauf.PROZENT,
                   aufschlag_wert=25, kombiniert="ja")), D("45"), "kombiniert: Kategorie + individuell")
gleich(pct(artikel(kategorie="Blech", aufschlag_quelle="Standard"), 10), D("10"), "Standard ausdrücklich gewählt")
gleich(pct(artikel(kategorie="Blech", aufschlag_quelle="individuell"), 10), D("20"),
       "individuell ohne Wert: Kategorie")
st = zukauf.stand(artikel(kategorie="Blech"), b10, kat, 10)
g, je = zukauf.rechnen([("a", dict(artikel_id=1, menge=1, stand=st), 1),
                        ("b", dict(artikel_id=1, menge=1, aufschlag=50, stand=st), 1)])
gleich(je["a"]["aufschlag"], D("2"), "Position ohne eigenen Aufschlag: Kategorie 20 %")
gleich(je["b"]["aufschlag"], D("5"), "Positionsaufschlag 50 % ersetzt Kategorie")
assert "Positionsaufschlag" in je["b"]["regel"] and "Kategorie Blech" in je["a"]["regel"]
ok("5 Priorität Position > Artikel > Kategorie > Standard, Kombination nur ausdrücklich, Quelle sichtbar")

# ------------------------------------------------------------------ 6 Aufschlag und Marge
gleich(je_einheit(ind(zukauf.PROZENT, 20), b10, 1)["vk"], D("12"), "20 % Aufschlag")
gleich(je_einheit(ind(zukauf.MARGE, 20), b10, 1)["vk"], D("12.5"), "20 % Zielmarge")
gleich(je_einheit(ind(zukauf.MARGE, 20), b10, 1)["marge_pct"], D("20"), "Marge vom VK")
assert "Zielmarge" in zukauf.regel_text(zukauf.regel(zukauf.MARGE, 20, quelle="individuell"))
assert "Zielmarge muss unter 100 % liegen" in zukauf.artikel_fehler(ind(zukauf.MARGE, 100))
ok("6 20 % Aufschlag = 12,00 €, 20 % Zielmarge = 12,50 € (bei 10,00 € Einstand), Methode im Text")

# ------------------------------------------------------------------ 7 Einkaufsstaffel
bs = bezug([(1, 1.20), (100, 0.95), (500, 0.80)])
for menge, preis in ((1, "1.2"), (99, "1.2"), (100, "0.95"), (499, "0.95"), (500, "0.8"), (5000, "0.8")):
    gleich(zukauf.ek_je_einheit(bs, menge)[0], D(preis), f"Staffel bei {menge}")
gleich(zukauf.ek_je_einheit(bezug([(10, 2.0)]), 3)[0], D("2"), "unter der ersten Grenze: erste Zeile")
gleich(zukauf.ek_je_einheit(bezug([]), 3)[0], None, "ohne Preis")
v = je_einheit(artikel(), bezug([]), 3)
gleich(v["fehler"], "kein Einkaufspreis", "fehlender Preis wird gekennzeichnet")
ok("7 Einkaufsstaffel 1–99 / 100–499 / ab 500 richtig gewählt, fehlender Preis gekennzeichnet")

# ------------------------------------------------------------------ 8 Mindestmenge und VPE
gleich(zukauf.bestellmenge(37, None, 50), D("50"), "VPE 50")
gleich(zukauf.bestellmenge(37, 100, 50), D("100"), "Mindestmenge 100")
gleich(zukauf.bestellmenge(120, 100, 50), D("150"), "aufgerundet auf VPE")
b8 = bezug([(1, 1.00), (50, 0.80)], vpe=50)
v = je_einheit(artikel(), b8, 37)
gleich((v["bestellung"]["verbrauch"], v["bestellung"]["bestellt"]), (D(37), D(50)), "Verbrauch bleibt 37")
gleich(v["bestellung"]["einkauf"], D("40"), "Auftrag trägt die ganze Bestellmenge 50 × 0,80")
gleich(v["bestellung"]["mehrmenge"], D(13), "Mehrmenge")
v = je_einheit(artikel(rest_lager="ja"), b8, 37)
gleich(v["bestellung"]["einkauf"], D("29.6"), "Rest ins Lager: nur Verbrauch 37 × 0,80")
ok("8 Mindestbestellmenge und Verpackungseinheit: Bestellmenge ≠ Verbrauch, Staffel nach Bestellmenge")

# ------------------------------------------------------------------ 11 Bezugskosten nur einmal
bb = bezug([(1, 1.00)], fracht=10, verpackung=2, mindermenge=5, mindermenge_bis=100)
st = zukauf.stand(artikel(), bb)
g, je = zukauf.rechnen([((0, 0), dict(artikel_id=7, menge=4, stand=st), 10),
                        ((1, 0), dict(artikel_id=7, menge=2, stand=st), 10)])
gleich(len(g), 1, "gleicher Artikel = eine Bestellung")
gleich(g[0]["bestellung"]["verbrauch"], D(60), "Verbrauch addiert")
gleich(g[0]["bestellung"]["bezug"], D(17), "Fracht 10 + Verpackung 2 + Mindermenge 5 einmal")
gleich(je[(0, 0)]["einstand"] + je[(1, 0)]["einstand"], D(77), "Einstand 60 + 17")
gleich(zukauf.runden(je[(0, 0)]["einstand"], 6), 51.333333, "nach Verbrauch verteilt (77 × 40/60)")
g, _ = zukauf.rechnen([((0, 0), dict(artikel_id=7, menge=20, stand=st), 10)])
gleich(g[0]["bestellung"]["bezug_einzeln"]["Mindermengenzuschlag"], D(0), "ab 100 kein Mindermengenzuschlag")
st2 = dict(st, bezug=dict(st["bezug"], preise=[dict(ab=1, preis=2.0)]))
g, _ = zukauf.rechnen([((0, 0), dict(artikel_id=7, menge=1, stand=st), 1),
                       ((1, 0), dict(artikel_id=7, menge=1, stand=st2), 1)])
gleich(len(g), 2, "verschiedene Preisstände bleiben getrennt")
ok("11 Bezugskosten einmal je Bestellung, nach Verbrauch verteilt; Preisstände nicht vermischt")

# ------------------------------------------------------------------ Datenbank: Speichern und Prüfung
db = Datenbank(tmp / "z.db")
assert SCHEMA_VERSION >= 17, "Schema"
gleich(list(db.zukauf_kategorien()), list(zukauf.KATEGORIEN_START), "Kategorien nur mit Namen")
assert all(z.get("aufschlag_wert") is None for z in db.zukauf_kategorien().values()), "keine erfundenen Aufschläge"
gleich(db.einstellung("zukauf_aufschlag"), None, "Standardaufschlag leer")
a1 = db.zukauf_speichern(None, dict(artikelnr="Z-1", bezeichnung="Schraube M6x20", kategorie="Normteile"),
                         [bezug([(1, 12.0)], pe=100, lieferant=" Lieferant A ")])
a = db.zukauf_artikel(a1)
gleich((a["artikelnr"], a["bezuege"][0]["bevorzugt"], a["bezuege"][0]["lieferant"]), ("Z-1", "ja", "Lieferant A"),
       "gespeichert, einziger Lieferant bevorzugt")
gleich([z["name"] for z in db.zeilen("zukauf_lieferanten")], ["Lieferant A"], "Lieferant angelegt")
for werte, bez, meldung in ((dict(artikelnr="Z-1", bezeichnung="X"), [], "gibt es schon"),
                            (dict(bezeichnung=""), [], "Artikelbezeichnung fehlt"),
                            (dict(bezeichnung="X"), [bezug([(1, -1)])], "nicht negativ"),
                            (dict(bezeichnung="X"), [bezug([(1, 1), (1, 2)])], "Staffelgrenze doppelt"),
                            (dict(bezeichnung="X"), [bezug([(1, 1)], pe=0)], "Preiseinheit"),
                            (dict(bezeichnung="X"), [bezug([(1, 1)], gueltig_von="2026-02-01",
                                                           gueltig_bis="2026-01-01")], "Gültig bis"),
                            (dict(bezeichnung="X"), [bezug([(1, 1)]), bezug([(1, 2)])], "Lieferant doppelt"),
                            (dict(bezeichnung="X", aufschlag_quelle="individuell", aufschlag_methode=zukauf.PROZENT),
                             [], "Aufschlag fehlt")):
    try:
        db.zukauf_speichern(None, werte, bez)
        raise AssertionError(f"nicht abgelehnt: {meldung}")
    except ValueError as e:
        assert meldung in str(e), (meldung, str(e))
gleich(len(db.zukauf_artikel_liste()), 1, "ungültige Artikel nicht gespeichert")
db.zukauf_speichern(None, dict(bezeichnung="Ohne Nummer"), [])
db.zukauf_speichern(None, dict(bezeichnung="Noch einer ohne Nummer"), [])
ok("Speichern: eindeutige Artikelnummer (leer erlaubt), negative Preise, doppelte Staffel, Gültigkeit abgelehnt")

db.zukauf_speichern(a1, dict(a, aufschlag_quelle="individuell", aufschlag_methode=zukauf.PROZENT, aufschlag_wert=25),
                    [dict(a["bezuege"][0], preise=[dict(ab=1, preis=13.0)])], bemerkung="Preiserhöhung")
h = db.zukauf_historie(a1)
assert any(x["feld"] == "Einkaufspreise" and x["alt"] == "ab 1: 12,00" and x["neu"] == "ab 1: 13,00"
           and x["bemerkung"] == "Preiserhöhung" for x in h), h
assert any(x["feld"] == "Aufschlag [% bzw. €]" and x["neu"] == "25" for x in h), h
db.zukauf_status(a1, "archiviert")
gleich(db.zukauf_artikel(a1)["status"], "archiviert", "archiviert")
ok("Preisänderungen protokolliert (alt/neu, Bemerkung), Artikel archiviert")

# Kategorie umbenennen: Verweise in Artikeln mit; Kategorieaufschlag ändern lässt individuelle Artikel unverändert
kid = db.zukauf_kategorien()["Normteile"]["id"]
db.aendern("zukauf_kategorien", kid, "name", "Normteile DIN")
gleich(db.zukauf_artikel(a1)["kategorie"], "Normteile DIN", "Kategorie umbenannt")
db.aendern("zukauf_kategorien", kid, "aufschlag_methode", zukauf.PROZENT)
db.aendern("zukauf_kategorien", kid, "aufschlag_wert", 40)
gleich(db.zukauf_stand(a1)["regeln"][0]["wert"], 25.0, "individueller Aufschlag bleibt")
a2 = db.zukauf_speichern(None, dict(bezeichnung="Mutter M6", kategorie="Normteile DIN"), [bezug([(1, 0.05)])])
gleich(db.zukauf_stand(a2)["regeln"][0]["wert"], 40.0, "Kategorieaufschlag für Artikel ohne eigenen")
gleich(db.einstellung("stammdaten_herkunft"), "Beispieldaten", "Zukauf ändert die Stammdaten-Herkunft nicht")
ok("Kategorie: Umbenennen ändert Artikel mit, neuer Kategorieaufschlag überschreibt individuelle Artikel nicht")

# ------------------------------------------------------------------ Datei der Vorversion (Schema 16)
alt = tmp / "alt.db"
shutil.copy(tmp / "z.db", alt)
db.schliessen()
con = sqlite3.connect(alt)
for t in zukauf.TABELLEN:
    con.execute(f'DROP TABLE "{t.name}"')
con.execute("ALTER TABLE positionen DROP COLUMN zukauf")
con.execute("PRAGMA user_version=16")
con.commit()
con.close()
db2 = Datenbank(alt)
gleich(db2.con.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION, "Schema aktuell")
gleich(len(db2.zukauf_kategorien()), 7, "Kategorien ergänzt")
assert "zukauf" in {r[1] for r in db2.con.execute("PRAGMA table_info(positionen)")}
assert db2.sicherungen(zusatz=f"vor_Schema_{SCHEMA_VERSION}"), "Sicherung vor der Umstellung"
db2.schliessen()
ok("Datei Schema 16: Sicherung, neue Tabellen und Spalte, Kategorien ergänzt")

print("OK: Zukaufartikel (Rechenkern und Daten)")
