"""EK-CSV-Import (Master-Auftrag 25.11.2026): gemeinsame Importbasis (Kodierung, Trennzeichen, Kopfzeile oder nicht,
Dezimalformat, Spaltennamen deutsch/englisch), Materialerkennung in vielen Schreibweisen („RR 50/50/3“ =
50x50x3), Werkstoffe nie verwechselt, drei Zuordnungsstufen, Preisprüfung je Lieferant (fremder Lieferant wird nie
überschrieben), Mengeneinheiten und Währung, Vorschau ohne Datenbankänderung, Importlauf mit Rückgängig,
Fehlerbericht, Importprofile auch bei anderer Spaltenreihenfolge, Assistent in 6 Schritten, 10.000 Zeilen.
Alle Preise sind Testwerte.

Aufruf: python tests/test_ek_import.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import csv_import  # noqa: E402
from rohrlaser import erp_preise as E  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
HEUTE = datetime.date.today()


def ok(text):
    print("OK    ", text)


def tag(vor):
    return (HEUTE - datetime.timedelta(days=vor)).strftime("%d.%m.%Y")


# ------------------------------------------------------------------ 1 Format erkennen
KOPF = ["Belegdatum", "Artikelnummer", "Artikelbezeichnung", "Werkstoff", "Menge", "ME", "Preis", "Währung",
        "Lieferant"]
Z = [[tag(30), "100500", "Rohr 50 x 50 x 3", "S235JRH EN10219", "120", "m", "5,10", "EUR", "Stahl Nord"],
     [tag(29), "100501", "RR 50/50/3", "S355J2H EN10219", "60", "m", "6,20", "EUR", "Stahl Nord"],
     [tag(28), "100502", "Rechteckrohr 100x50x4", "S235JRH EN 10219", "1.250,5", "mm", "9,40", "EUR", ""],
     [tag(27), "100503", "Rundrohr Ø60x3", "1.4301", "6", "St", "11,00", "EUR", "Edel GmbH"]]
for kod, trenner in (("utf-8", ";"), ("cp1252", ";"), ("utf-8", ","), ("cp1252", "\t")):
    def zelle(x):
        return f'"{x}"' if trenner in x else x
    text = "\r\n".join(trenner.join(zelle(x) for x in z) for z in [KOPF] + Z)
    d = E.lesen(text.encode(kod), "ek.csv")
    assert d["mit_kopf"] and d["trenner"] == trenner and d["kopf"] == KOPF, (kod, trenner, d["kopf"], d["trenner"])
    assert d["zeilen"][3][2] == "Rundrohr Ø60x3", d["zeilen"][3]
ok("UTF-8 und Windows-1252, Semikolon, Komma und Tab: Kopf, Zellen und Ø richtig gelesen")
ohne = E.lesen("\n".join(";".join(z) for z in Z).encode("cp1252"), "ohne.csv")
assert not ohne["mit_kopf"] and len(ohne["zeilen"]) == 4 and ohne["kopf"][0].startswith("Spalte"), ohne["kopf"]
erk = E.spalten_erkennen(ohne)
assert erk["datum"]["spalte"] == 0 and erk["bezeichnung"]["spalte"] == 2, erk
assert all(e["sicherheit"] == csv_import.VORSCHLAG for e in erk.values())
ok("Datei ohne Kopfzeile: Spalten am Inhalt erkannt, aber nur als Vorschlag")
assert csv_import.zahl("1.250", "Punkt") == 1.25 and csv_import.zahl("1.250", "Komma") == 1250
assert csv_import.zahl("1,234.56") == 1234.56 and csv_import.zahl("1.234,56") == 1234.56
ok("Dezimalformat: 1.250 je nach Datei 1,25 oder 1.250")

daten = E.lesen("\r\n".join(";".join(z) for z in [KOPF] + Z).encode("cp1252"), "ek.csv")
erk = E.spalten_erkennen(daten)
sp = csv_import.zuordnung(erk)
assert sp == dict(datum=0, artikelnr=1, bezeichnung=2, werkstoff=3, menge=4, einheit=5, preis=6, waehrung=7,
                  lieferant=8), sp
en = E.lesen("Date;Item No;Description;Qty;Unit price;Currency;Supplier\n01.11.2026;1;QR 40x40x3;6;5,5;EUR;X\n"
             .encode(), "en.csv")
assert csv_import.zuordnung(E.spalten_erkennen(en)) == dict(datum=0, artikelnr=1, bezeichnung=2, menge=3, preis=4,
                                                            waehrung=5, lieferant=6)
ok("Spaltennamen deutsch und englisch erkannt (Belegdatum, ME, Währung, Lieferant / Date, Qty, Supplier)")

# ------------------------------------------------------------------ 2 Material erkennen
for t, soll in (("Rohr 50 x 50 x 3", (50, 50, 3)), ("Vierkantrohr 50x50x3", (50, 50, 3)),
                ("50 X 50 X 3 mm", (50, 50, 3)), ("RR 50/50/3", (50, 50, 3)), ("Rechteckrohr 100x50x4", (100, 50, 4)),
                ("Rundrohr Ø60x3", (60, None, 3)), ("Rundrohr ⌀60x3", (60, None, 3))):
    m = E.masse(t)
    ist = (m["a"], m["b"] if m["form"] != "Quadratrohr" else m["a"], m["wand"]) if m else None
    assert ist == soll, (t, m)
assert E.masse("RR 50/50/3")["form"] == "Quadratrohr" and E.masse("Rundrohr Ø60x3")["form"] == "Rundrohr"
ok("Schreibweisen: „Rohr 50 x 50 x 3“, „Vierkantrohr 50x50x3“, „50 X 50 X 3 mm“, „RR 50/50/3“ = 50x50x3; "
   "„Rechteckrohr 100x50x4“; „Rundrohr Ø60x3“")

db = Datenbank(tmp / "ek.db")
for pid, form, a, b, w in (("QR 50x50x3", "Quadratrohr", 50, None, 3), ("RE 100x50x4", "Rechteckrohr", 100, 50, 4),
                           ("RR 60x3", "Rundrohr", 60, None, 3)):
    if pid not in db.kontext().profile:
        db.neu("profile", dict(profil_id=pid, form=form, a=a, b=b, wand=w))
k = db.kontext()
werk = {}
for t in ("QR 50x50x3 S235JRH EN10219", "QR 50x50x3 S355J2H EN10219", "QR 50x50x3 1.4301", "QR 50x50x3 1.4571",
          "QR 50x50x3 S355MC"):
    z = E.zerlegen(t, k)
    werk[t] = z["werkstoff_id"]
assert werk["QR 50x50x3 S235JRH EN10219"] == "S235-10219" and werk["QR 50x50x3 S355J2H EN10219"] == "S355-10219"
assert werk["QR 50x50x3 1.4301"] == "1.4301" and werk["QR 50x50x3 1.4571"] == "1.4571"
assert werk["QR 50x50x3 S355MC"] is None, werk
assert len({w for w in werk.values() if w}) == 4
ok("Werkstoffe getrennt: S235, S355J2H, 1.4301, 1.4571; S355MC wird nie einem anderen Werkstoff zugeordnet")

# ------------------------------------------------------------------ 3 Vorschau mit Stufen, Einheiten, Fehlern
Z2 = Z + [[tag(26), "100504", "QR 50x50x3 S355J2H", "", "12", "m", "6,90", "USD", "Stahl Nord"],      # Währung
          [tag(25), "100505", "Gewindestange M12", "", "1", "m", "abc", "EUR", ""],                     # Preis kaputt
          [tag(30), "100500", "Rohr 50 x 50 x 3", "S235JRH EN10219", "120", "m", "5,10", "EUR", "Stahl Nord"]]
daten = E.lesen("\r\n".join(";".join(z) for z in [KOPF] + Z2).encode("cp1252"), "ek.csv")
vor_db = db.con.execute("SELECT COUNT(*) FROM erp_kaeufe").fetchone()[0] if "erp_kaeufe" in \
    __import__("rohrlaser.db_verbindung", fromlist=["x"]).tabellen(db.con) else 0
v = E.vorschau_import(db, daten, sp)
assert (db.con.execute("SELECT COUNT(*) FROM erp_kaeufe").fetchone()[0]) == vor_db
ok("Vorschau ändert die Datenbank nicht")
g = v["gruppe"]
assert g[2] == E.NEU_KAUF and g[8] == E.DOPPELT and g[6] == E.FEHLERHAFT and g[7] == E.FEHLERHAFT, g
gruende = {n: grund for n, grund, _r in v["fehler"]}
assert "USD" in gruende[6] or "Währung" in gruende[6], gruende
kauf = {x["zeile"]: x for x in v["kaeufe"]}
assert abs(kauf[4]["menge"] - 1.2505) < 1e-6 and kauf[4]["lieferant"] == "", kauf[4]
assert abs(kauf[4]["preis"] - 9.4) < 1e-9 and "€/m" in kauf[4]["hinweis"], kauf[4]     # 9.400 €/m wäre unplausibel
assert abs(kauf[5]["menge"] - 36) < 1e-6 and "6 m" in kauf[5]["hinweis"], kauf[5]
ok("Mengeneinheit mm und Stück (×6 m mit Hinweis) umgerechnet; fremde Währung und kaputter Preis = fehlerhaft; "
   "doppelte Zeile erkannt")
stufe = {a["artikelnr"]: a["stufe"] for a in v["artikel"]}
assert stufe["100500"] == E.EXAKT and stufe["100501"] == E.EXAKT and stufe["100503"] == E.EXAKT, stufe
assert stufe["100502"] == E.EXAKT, stufe
ok("Zuordnungsstufen: eindeutige Abmessung + Werkstoff = exakter Treffer")
d3 = E.lesen(f"Datum;Menge;Preis;Bezeichnung\n{tag(5)};6;5;QR 50x50x3 S355J2H\n{tag(5)};6;5;QR 70x70x5 S235JRH\n"
             .encode(), "x.csv")
v3 = E.vorschau_import(db, d3, csv_import.zuordnung(E.spalten_erkennen(d3)))
st3 = {a["bezeichnung"]: a for a in v3["artikel"]}
assert st3["QR 50x50x3 S355J2H"]["stufe"] == E.WAHRSCHEINLICH, st3["QR 50x50x3 S355J2H"]
assert st3["QR 50x50x3 S355J2H"]["vorschlag_zuordnung"]["werkstoff_id"] == "S355-10219"
assert st3["QR 70x70x5 S235JRH"]["stufe"] == E.KEIN_TREFFER and any(
    p["profil_id"] == "QR 70x70x5" for p in v3["plan"]["profile"]), v3["plan"]
ok("Werkstoff ohne Norm = wahrscheinlicher Treffer (zum Bestätigen), unbekanntes Profil = kein Treffer, neu anlegen")

# ------------------------------------------------------------------ 4 Übernehmen, Lieferanten, Rückgängig
erg = E.uebernehmen(db, v, "ek.csv", lieferant="")
assert erg["neu"] == 4, erg
gesp = {r["bestellnr"] or r["artikelnr"]: dict(r) for r in db.con.execute("SELECT * FROM erp_kaeufe")}
assert gesp["100500"]["lieferant"] == "Stahl Nord" and gesp["100500"]["import_id"] == erg["import_id"]
# gleiches Material, anderer Lieferant, später: alter Preis des ersten Lieferanten bleibt
d4 = E.lesen(("\r\n".join(";".join(z) for z in [KOPF, [tag(3), "X-1", "Rohr 50 x 50 x 3", "S235JRH EN10219", "60",
                                                         "m", "6,00", "EUR", "Rohr Süd"]])).encode(), "ek2.csv")
v4 = E.vorschau_import(db, d4, sp)
p4 = v4["pruefung"][0]
assert p4["lieferant"] == "Rohr Süd" and p4["anderer_lieferant"] and p4["alt_lieferant"] == "Stahl Nord", p4
assert abs(p4["pct"] - (6 / 5.1 - 1) * 100) < 1e-6 and p4["markiert"], p4
erg4 = E.uebernehmen(db, v4, "ek2.csv")
preise = {(r["lieferant"], r["preis"]) for r in db.con.execute("SELECT lieferant, preis FROM erp_kaeufe")}
assert ("Stahl Nord", 5.1) in preise and ("Rohr Süd", 6.0) in preise, preise
ok("Preisprüfung: anderer Lieferant nur zum Vergleich (+17,6 % markiert), beide Preise bleiben gespeichert")
laeufe = csv_import.laeufe(db, csv_import.ART_EK)
assert [z["id"] for z in laeufe[:2]] == [erg4["import_id"], erg["import_id"]]
n, _m = E.rueckgaengig(db, erg4["import_id"])
assert ("Rohr Süd", 6.0) not in {(r["lieferant"], r["preis"]) for r in db.con.execute(
    "SELECT lieferant, preis FROM erp_kaeufe")}
ok("Importläufe je Art, Rückgängig nimmt nur den gewählten Lauf zurück")
bericht = E.fehlerbericht(v, daten["kopf"])
assert bericht.startswith("﻿Zeile;Gruppe;Grund;Belegdatum") and "USD" in bericht and "abc" in bericht
ok("Fehlerbericht (CSV für Excel) mit fehlerhaften und doppelten Zeilen")

# Rückgängig überschreibt keine Zuordnung, die seit dem Import geändert wurde
d5 = E.lesen(f"Datum;Menge;Preis;Bezeichnung\n{tag(2)};6;5;QR 50x50x3 S355J2H Rückgängig\n".encode(), "r.csv")
v5 = E.vorschau_import(db, d5, csv_import.zuordnung(E.spalten_erkennen(d5)))
a5 = [a for a in v5["artikel"] if a["stufe"] == E.WAHRSCHEINLICH][0]
e5 = E.uebernehmen(db, v5, "r.csv", bestaetigt=[(a5, None)], anlegen=False)
E.zuordnung_merken(db, a5["schluessel"], a5["artikelnr"], a5["bezeichnung"], "QR 50x50x3", "S235-10219", "")
_n, meld5 = E.rueckgaengig(db, e5["import_id"])
assert E.zuordnungen(db)[a5["schluessel"]]["werkstoff_id"] == "S235-10219" and any("bleibt" in m for m in meld5)
ok("Rückgängig lässt eine danach von Hand geänderte Zuordnung stehen")

# ------------------------------------------------------------------ 5 Importprofile
csv_import.profil_speichern(db, E.IMPORTPROFILE, "Stahl Nord", KOPF, sp, lieferant="Stahl Nord")
um = [KOPF[i] for i in (8, 7, 6, 5, 4, 3, 2, 1, 0)]
name, prof, sp_um = csv_import.profil_passend(csv_import.profile(db, E.IMPORTPROFILE), um)
assert name == "Stahl Nord" and prof["lieferant"] == "Stahl Nord" and sp_um["datum"] == 8 and sp_um["lieferant"] == 0
ok("Importprofil mit Lieferant, erkannt auch bei anderer Spaltenreihenfolge")

# ------------------------------------------------------------------ 6 Assistent in 6 Schritten
from rohrlaser import ek_import_assistent as EA  # noqa: E402

pfad = tmp / "ek3.csv"
pfad.write_bytes(("\r\n".join(";".join(z) for z in [["Datum", "Menge", "Preis", "Bezeichnung"],
                                                     [tag(4), "6", "5", "QR 50x50x3 S355J2H"],
                                                     [tag(4), "6", "7", "QR 70x70x5 S235JRH EN10219"],
                                                     [tag(4), "x", "7", "kaputt"]])).encode())
a = EA.assistent(None, db, pfad)
assert len(a.schritte) == 6 and a.nr == 0
a.lieferant.setText("Rohr Süd")
assert a.weiter() and a.nr == 1
a.spalten.wahl["preis"].setCurrentIndex(0)
assert not a.weiter() and "Meterpreis" in a.meldung.text() or "Preis" in a.meldung.text()
a.spalten.wahl["preis"].setCurrentIndex(3)
assert a.spalten.profil_speichern("Test-Profil") == "Test-Profil"
assert a.weiter() and a.nr == 2
m = a.material
w = [r for r, x in enumerate(m.sichtbar) if x["stufe"] == E.WAHRSCHEINLICH][0]
m.t.item(w, 0).setCheckState(Qt.Checked)
assert len(m.liste_bestaetigt()) == 1
assert a.weiter() and a.nr == 3 and a.preise.t.rowCount() >= 1
assert a.weiter() and a.nr == 4
assert a.vorschau_s.t.rowCount() == 3 and "fehlerhaft" in a.vorschau_s.kopf.text()
assert a.weiter() and a.nr == 5 and "Bereit zum Import" in a.abschluss.info.text()
assert a.abschluss.bericht(str(tmp / "bericht.csv")) and "kaputt" in (tmp / "bericht.csv").read_text("utf-8-sig")
vorher = db.con.execute("SELECT COUNT(*) FROM erp_kaeufe").fetchone()[0]
assert a.weiter() and a.fertig and a.abschluss.ergebnis["neu"] == 2, a.meldung.text()
assert "QR 70x70x5" in db.kontext().profile
assert db.con.execute("SELECT COUNT(*) FROM erp_kaeufe WHERE lieferant='Rohr Süd'").fetchone()[0] >= 2
assert a.abschluss.rueckgaengig()
assert db.con.execute("SELECT COUNT(*) FROM erp_kaeufe").fetchone()[0] == vorher
assert "QR 70x70x5" not in db.kontext().profile
ok("Assistent: 6 Schritte, Pflichtspalte geprüft, Profil gespeichert, Vorschlag bestätigt, Import, Rückgängig")
a2 = EA.assistent(None, db, pfad)
assert a2.spalten.profilname == "Test-Profil" and a2.lieferant.text() == "Rohr Süd"
ld = a2.datei.laeufe_zeigen(zeigen=False)
assert ld.t.rowCount() >= 3
ok("zweite Datei: Importprofil mit Lieferant automatisch, letzte Importe mit Rückgängig")

# ------------------------------------------------------------------ 7 Tempo: 10.000 Zeilen
zeilen = [["Datum", "Artikelnummer", "Bezeichnung", "Menge", "Preis", "Lieferant"]]
for i in range(10000):
    zeilen.append([tag(i % 300 + 1), f"9{i % 400:05d}", f"QR {40 + i % 40}x{40 + i % 40}x{2 + i % 3} S235JRH EN10219",
                   str(6 + i % 50), f"{4 + (i % 97) / 10:.2f}".replace(".", ","), ("Nord", "Süd")[i % 2]])
gross = E.lesen("\n".join(";".join(z) for z in zeilen).encode(), "gross.csv")
t0 = time.perf_counter()
vg = E.vorschau_import(db, gross, csv_import.zuordnung(E.spalten_erkennen(gross)))
t1 = time.perf_counter()
eg = E.uebernehmen(db, vg, "gross.csv")
t2 = time.perf_counter()
assert eg["neu"] == 10000 and t1 - t0 < 60 and t2 - t1 < 60, (eg, t1 - t0, t2 - t1)
ok(f"10.000 Zeilen: Vorschau {t1 - t0:.1f} s, Import {t2 - t1:.1f} s ({eg['profile']} Profile angelegt)")
t3 = time.perf_counter()
E.rueckgaengig(db, eg["import_id"])
ok(f"Rückgängig 10.000 Zeilen {time.perf_counter() - t3:.1f} s")
print("Alle Prüfungen bestanden.")
