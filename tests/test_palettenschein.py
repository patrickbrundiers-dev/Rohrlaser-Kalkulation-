"""Prüft Palettenbegleitschein und Versand (Plan Palettenbegleitschein, Freigabe „a a a a a a a a b a“):
Palettenrechnung lagenweise (nachgerechnete Zahlen), Feiertage je Bundesland, Stück pro Palette von Hand,
Arbeitsschritt-Vorschlag, Schema 59, Fenster, Reiter Versand, PDFs und Anhang an die Werkstattpapiere, Lesemodus.

Aufruf: python tests/test_palettenschein.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import auftrag, feiertage, paletten, palettenschein, palettenschein_dialog, pdf  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


EUR = dict(lht_id="EUR", bezeichnung="Europalette", laenge=1200, breite=800, hoehe=144, eigengewicht=25,
           nutzlast=1500, max_laenge=1400)
LG = dict(lht_id="LG", bezeichnung="Langgut", laenge=6500, breite=800, hoehe=300, eigengewicht=60, nutzlast=1500,
          max_laenge=6500)
GB = dict(lht_id="GB", bezeichnung="Gitterbox", art="Gitterbox", laenge=1240, breite=835, hoehe=970,
          eigengewicht=85, nutzlast=1500)
V = paletten.vorgaben({})


def rohr(pos, stueck, laenge, gewicht, abm, pid=None):
    return dict(pos=pos, stueck=stueck, laenge=laenge, id=pid or pos), dict(gewicht=gewicht, profil_abm=abm)


# ------------------------------------------------------------------ Vorgaben
assert V == dict(hoehe_gesamt=1200, fuellgrad=0.9, max_brutto=1000.0, zwischenlage=0.0, mischen=False)
assert paletten.vorgaben({"palette_max_brutto": None})["max_brutto"] is None
assert paletten.stapelhoehe(EUR, V) == 1056 and paletten.stapelhoehe(GB, V) == 970
assert paletten.nutzlast(EUR, V) == 975 and paletten.nutzlast(EUR, dict(V, max_brutto=None)) == 1500
ok("Vorgaben: 1.200 mm inkl. Palette (1.056 mm Stapel), 1.000 kg brutto (975 kg Zuladung), Gitterbox Innenhöhe")

# ------------------------------------------------------------------ Lagen (von Hand nachgerechnet)
# Quadratrohr 40 × 40, 1.000 mm: 1 Reihe, 800/40 = 20 quer, × 0,9 = 18 je Lage; 1.056/40 = 26 Lagen = 468 Stück
p, h = paletten.lagenplan((1000.0, 40.0, 40.0), False, EUR, V)
assert h is None and p.je_lage == [18] and p.lagen_max == 26 and p.voll == 468, (p.je_lage, p.lagen_max)
# Rundrohr Ø 42,4, 1.250 mm: 50 mm Überstand, 18 quer -> 16 je Lage, versetzt Lagenabstand 42,4·√3/2 = 36,7 mm:
# 1 + ⌊(1.056 − 42,4) / 36,72⌋ = 28 Lagen = 448 Stück
p, h = paletten.lagenplan((1250.0, 42.4, 42.4), True, EUR, V)
assert p.je_lage == [16] and p.lagen_max == 28 and p.voll == 448 and "50 mm Überstand" in p.text, p.text
assert math.isclose(p.abstand, 42.4 * math.sqrt(3) / 2) and "versetzt" in p.text
# Kurzes Rohr 345 mm: 3 Reihen × 16 quer (versetzt 16/16) × 0,9 = 43 je Lage
p, _ = paletten.lagenplan((345.0, 48.3, 48.3), True, EUR, V)
assert p.je_lage == [43], p.je_lage
# Rechteckrohr 60 × 40 liegt flach (40 hoch): 800/60 = 13 -> 11 je Lage, 1.056/40 = 26 Lagen; hochkant wäre 18 × 17
p, _ = paletten.lagenplan((1100.0, 60.0, 40.0), False, EUR, V)
assert p.voll == max(11 * 26, 18 * 17) and p.voll == 306, (p.je_lage, p.lagen_max)
# Zwischenlage 20 mm: 40 + n·60 ≤ 1.056 -> 17 Lagen
p, _ = paletten.lagenplan((1000.0, 40.0, 40.0), False, EUR, dict(V, zwischenlage=20.0))
assert p.lagen_max == 17 and p.voll == 17 * 18
# Zu groß: 1 Stück mit Hinweis
p, h = paletten.lagenplan((1300.0, 900.0, 900.0), False, EUR, V)
assert p.voll == 1 and "Sonderladung" in h
ok("Lagen: Reihen × quer × 0,9, Überstand bis max. Teillänge, Rundrohre versetzt, flach/hochkant, Zwischenlage")

# ------------------------------------------------------------------ Packen: Gewicht und Höhe
# 3.000 Rundrohre 42,4 × 2, 1.250 mm, 2,49 kg: Lagen 448 je Palette, Gewicht 975/2,49 = 391 -> 8 Paletten
pos, werte = zip(rohr(10, 3000, 1250.0, 2.49, ("Rundrohr", 42.4, None, 2.0)))
e = paletten.packen(list(pos), list(werte), [EUR, LG], "EUR", "LG")
assert e["anzahl"] == 8 and e["stuecke"][0]["je_palette"] == 391, (e["anzahl"], e["stuecke"][0]["je_palette"])
assert [sum(n for _, n in p["inhalt"]) for p in e["paletten"]] == [391] * 7 + [263]
assert all(p["brutto"] <= 1000 + 1e-6 for p in e["paletten"]) and e["gesamt_stueck"] == 3000
assert "Lagen" in e["paletten"][0]["aufbau"][0] and paletten.kurz(e) == "8 Paletten (8 × EUR)"
# leicht (Alu-ähnlich 0,8 kg): die Höhe begrenzt -> 448 je Palette, 3.000 / 448 = 7 Paletten
e = paletten.packen([dict(pos[0])], [dict(werte[0], gewicht=0.8)], [EUR, LG], "EUR", "LG")
assert e["anzahl"] == 7 and e["stuecke"][0]["je_palette"] == 448
assert all(p["hoehe"] <= 1200 + 1e-6 for p in e["paletten"])
# lang -> Langgut; länger als Langgut -> Hinweis
e = paletten.packen(*map(list, zip(rohr(20, 10, 3000.0, 9.0, ("Quadratrohr", 40.0, None, 3.0)),
                                   rohr(30, 1, 7000.0, 20.0, ("Quadratrohr", 40.0, None, 3.0)))),
                    [EUR, LG], "EUR", "LG")
assert e["je_lht"] == {"LG": 2} and any("Sonderladung" in h for h in e["hinweise"])
# Mischen: zwei kleine Positionen teilen sich eine Palette, ohne Mischen je eine
zwei = list(map(list, zip(rohr(10, 20, 1000.0, 3.0, ("Quadratrohr", 40.0, None, 3.0)),
                          rohr(20, 30, 600.0, 2.0, ("Quadratrohr", 40.0, None, 3.0)))))
assert paletten.packen(*zwei, [EUR, LG], "EUR", "LG")["anzahl"] == 2
e = paletten.packen(*zwei, [EUR, LG], "EUR", "LG", {"palette_mischen": "ja"})
assert e["anzahl"] == 1 and [k for k, _ in e["paletten"][0]["inhalt"]] == [0, 1]
# Max. Stück je Palette von Hand
e = paletten.packen(*zwei, [EUR, LG], "EUR", "LG", max_je={"10": 7})
assert e["anzahl"] == 4 and [sum(n for _, n in p["inhalt"]) for p in e["paletten"]][:3] == [7, 7, 6]
# Ohne Ladungsträger: nichts berechnet, Hinweis
e = paletten.packen(*zwei, [], "EUR", "LG")
assert e["anzahl"] == 0 and e["hinweise"]
ok("Packen: Gewichtsgrenze (8 statt 7 Paletten), Höhe, Langgut, Sonderladung, Mischen, max. je Palette von Hand")

# ------------------------------------------------------------------ Feiertage
assert feiertage.ostersonntag(2026) == datetime.date(2026, 4, 5) and feiertage.ostersonntag(2027) == \
    datetime.date(2027, 3, 28)
nw = feiertage.feiertage(2026, "Nordrhein-Westfalen")
assert nw[datetime.date(2026, 6, 4)] == "Fronleichnam" and datetime.date(2026, 11, 1) in nw
assert datetime.date(2026, 10, 31) not in nw and datetime.date(2026, 10, 31) in feiertage.feiertage(2026, "Sachsen")
assert datetime.date(2026, 11, 18) in feiertage.feiertage(2026, "Sachsen")          # Buß- und Bettag
assert feiertage.feiertage(2026, feiertage.KEINE) == {}
# Mi 30.12.2026 + 3 AT: Do 31.12., (Fr 1.1. Neujahr), Mo 4.1., Di 5.1.
assert feiertage.arbeitstage_spaeter(datetime.date(2026, 12, 30), 3, "Nordrhein-Westfalen") == \
    datetime.date(2027, 1, 5)
assert feiertage.arbeitstage_spaeter(datetime.date(2026, 12, 30), 3, feiertage.KEINE) == datetime.date(2027, 1, 4)
assert feiertage.hinweis(datetime.date(2026, 12, 25), "Bayern") == "1. Weihnachtstag"
assert feiertage.hinweis(datetime.date(2026, 10, 24)) == "Samstag"
assert auftrag.arbeitstage_spaeter(datetime.date(2026, 5, 13), 1, "Nordrhein-Westfalen") == \
    datetime.date(2026, 5, 15)                                                       # 14.5. Himmelfahrt
ok("Feiertage je Bundesland (Ostern, Fronleichnam, Reformationstag, Buß- und Bettag), Arbeitstage, Hinweis")

# ------------------------------------------------------------------ Stück pro Palette, Verteilen, Hinweis
assert palettenschein.stueck_liste("100", 3)["werte"] == [100, 100, 100]
s = palettenschein.stueck_liste("2x80, 10", 4)
assert s["werte"] == [80, 80, 10, None] and s["summe"] == 170 and not s["einzeln"]
assert palettenschein.stueck_liste("abc", 2) == dict(fehler=True) and palettenschein.stueck_liste("", 2) is None
assert palettenschein.verteilen(250, 3) == "84, 2x83" and palettenschein.verteilen(300, 3) == "100"
assert palettenschein.verteilen(7, 2) == "4, 3"
try:
    palettenschein.verteilen(2, 3)
    raise AssertionError("verteilen 2 auf 3")
except ValueError:
    pass
assert palettenschein.hinweis_stufe("") == "leer" and palettenschein.hinweis_stufe("kurz") == "normal"
assert palettenschein.hinweis_stufe("x" * 2000) == "zu lang"
ok("Stück pro Palette ('100', '2x80, 10'), Verteilen wie im Tool, Hinweisgröße")

# ------------------------------------------------------------------ Status und Filter
d = palettenschein.leer()
heute = datetime.date(2026, 10, 21)
palettenschein.status_setzen(d, palettenschein.VERLADEBEREIT, True, heute)
assert palettenschein.ist_verladebereit(d) and palettenschein.stand(d) == "Fertig zur Verladung"
z = dict(liefertermin="2026-10-20", nummer="1")
assert palettenschein.passt(z, d, "Überfällig", heute) and palettenschein.passt(z, d, "Verladebereit", heute)
assert not palettenschein.passt(z, d, "In Bearbeitung", heute)
palettenschein.status_setzen(d, palettenschein.VERSENDET, True, heute)
assert d["versendet_am"] == "2026-10-21" and not palettenschein.passt(z, d, "Aktuell", heute)
assert palettenschein.passt(z, d, "Versendet", heute) and not palettenschein.ist_verladebereit(d)
assert palettenschein.passt(dict(liefertermin="2026-10-23"), palettenschein.leer(), "Diese Woche", heute)
d["archiviert"] = True
assert palettenschein.passt(z, d, "Archiviert", heute) and not palettenschein.passt(z, d, "Alle", heute)
assert palettenschein.lesen('{"status": ["Versendet", "Quatsch"], "max_je": {"3": 5, "4": 0}}')["status"] == \
    ["Versendet"]
assert palettenschein.lesen("kaputt") == palettenschein.leer()
ok("Status (Verladebereit, Versendet mit Datum), Filter der Versandübersicht, Lesen robust")

# ------------------------------------------------------------------ Datenbank, Beispielangebot
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert SCHEMA_VERSION >= 59
aid = beispiel_angebot.anlegen(db)
assert db.palettenschein(aid) == palettenschein.leer() and db.versand_auftraege() == []
gruppen = palettenschein.schritte(db.einstellung("versand_schritte"))
assert "Intern" in gruppen and "Extern" in gruppen and gruppen["Intern"]
z = palettenschein.zusammenstellen(db, aid)
assert z["packliste"]["anzahl"] == 5 and z["packliste"]["je_lht"] == {"EUR": 3, "LG": 2}, paletten.kurz(z["packliste"])
assert z["schein"]["arbeiten"], "Vorschlag der Arbeitsschritte aus dem Angebot"
assert all(k.partition(palettenschein.TRENNER)[0] in gruppen for k in z["schein"]["arbeiten"])
ok("Schema 59, Beispielangebot: 5 Paletten (3 × EUR, 2 × LG), Arbeitsschritte vorgeschlagen")

# Datei mit Schema 58: Sicherung vor_Schema_59, Spalte leer ergänzt
alt = tmp / "alt.db"
d0 = Datenbank(alt)
n0 = len(d0.angebote())
d0.con.execute("ALTER TABLE angebote DROP COLUMN palettenschein")
d0.con.execute("PRAGMA user_version = 58")
d0.con.commit()
d0.con.close()
d1 = Datenbank(alt)
assert d1.sicherungen(zusatz="vor_Schema_59") and len(d1.angebote()) == n0
d1.con.close()
ok("Umstellung von Schema 58: Sicherung vor_Schema_59, Spalte palettenschein ergänzt")

# Druckseiten
seiten = palettenschein.seiten(z["kopf"], z["schein"], z["packliste"], z["gruppen"], heute)
assert [s["nr"] for s in seiten] == [1, 2, 3, 4, 5] and all(s["gesamt"] == 5 for s in seiten)
assert seiten[0]["inhalt"] and seiten[0]["stueck"] == sum(r[3] for r in seiten[0]["inhalt"]) and seiten[0]["gewicht"]
d = dict(palettenschein.leer(), unbekannt=True)
s = palettenschein.seiten(z["kopf"], d, z["packliste"], z["gruppen"], heute)
assert len(s) == 1 and s[0]["nr"] is None
d = dict(palettenschein.leer(), paletten_auto=False, paletten=3, stueck_text="2x50, 12")
assert [x["stueck"] for x in palettenschein.seiten(z["kopf"], d, z["packliste"], z["gruppen"], heute)] == [50, 50, 12]
ok("Druckseiten: je Palette Inhalt + Gewicht, Anzahl unbekannt = ein Schein ohne Nummer, Stück von Hand")

# ------------------------------------------------------------------ Oberfläche
fenster = Hauptfenster(db, tmp, stumm=True)
assert fenster.angebote.vorgang_setzen("Beauftragt", aid, auftrag=("PO-4711", "2026-11-13"))
liste = db.versand_auftraege()
assert [x["id"] for x in liste] == [aid] and liste[0]["auftragsnr"] == "PO-4711"
seite = fenster.versand
seite.neu_laden()
assert seite.tabelle.rowCount() == 1 and "5" in seite.tabelle.item(0, 0).text() + "".join(
    seite.tabelle.item(0, c).text() for c in range(seite.tabelle.columnCount()) if seite.tabelle.item(0, c))

dlg = palettenschein_dialog.oeffnen(fenster, aid)
assert dlg.bestellnr.text() == "PO-4711" and dlg.auto.isChecked() and dlg.packliste.rowCount() == 5
dlg.hinweis.setPlainText("Kanten schützen")
dlg.status[palettenschein.VERLADEBEREIT].setChecked(True)
assert db.palettenschein(aid)["hinweis"] == "Kanten schützen"
assert palettenschein.VERLADEBEREIT in db.palettenschein(aid)["status"]
pfad = dlg.drucken()
assert pfad and Path(pfad).is_file() and Path(pfad).name.endswith("Palettenbegleitschein.pdf"), pfad
assert db.palettenschein(aid)["gedruckt_am"] == datetime.date.today().isoformat()
dlg.close()
ok("Reiter Versand, Fenster (Bestellnr., automatisch 5 Paletten, Hinweis/Status gespeichert), PDF im Angebotsordner")

seite.filter.setCurrentIndex(seite.filter.findData("Alle"))
seite.neu_laden()
seite.waehlen([aid])
seite.status_alle(palettenschein.VERSENDET)
seite.waehlen([aid])
assert db.palettenschein(aid)["versendet_am"] == datetime.date.today().isoformat()
vl = tmp / "verladeliste.pdf"
assert seite.verladeliste(vl) and vl.is_file()
seite.lieferdatum(datetime.date(2026, 12, 1))
seite.waehlen([aid])
assert db.angebot(aid)["liefertermin"] == "2026-12-01"
seite.archivieren()
assert db.palettenschein(aid)["archiviert"]
ok("Versandübersicht: Versendet, Verladeliste-PDF, Lieferdatum ändern, Archivieren")

# PDFs direkt, Werkstattpapiere mit Palettenscheinen
p1 = tmp / "scheine.pdf"
pdf.palettenschein_pdf(p1, seiten, db.einstellungen())
assert p1.read_bytes().count(b"/Type /Page") - p1.read_bytes().count(b"/Type /Pages") == 5
ok("PDF: ein Blatt je Palette")

assert db.einstellung("palettenschein_werkstatt") == "ja"
s = fenster.angebot_oeffnen(aid)
assert s.optimieren()
w = s.werkstatt_pdf()
text = subprocess.run(["pdftotext", str(w), "-"], capture_output=True, text=True).stdout \
    if shutil.which("pdftotext") else None
assert text is None or text.upper().count("PALETTENBEGLEITSCHEIN") >= 5, text
db.einstellung_setzen("palettenschein_werkstatt", "nein")
w2 = s.werkstatt_pdf()
assert text is None or "PALETTENBEGLEITSCHEIN" not in subprocess.run(["pdftotext", str(w2), "-"],
                                                                     capture_output=True, text=True).stdout.upper()
ok("Werkstattpapiere des beauftragten Angebots: Palettenscheine hinten (Einstellung ja/nein)")

# Kopie und neue Fassung übernehmen den Palettenschein nicht
for neu in (db.angebot_kopieren(aid), db.angebot_fassung(aid)):
    assert db.palettenschein(neu) == palettenschein.leer()
ok("Kopie und neue Fassung ohne Palettenschein")

# Lesemodus: nichts gespeichert
vorher = db.palettenschein(aid)
db.nur_lesen = "Test"
try:
    db.palettenschein_speichern(aid, dict(vorher, hinweis="geändert"))
except Exception:
    pass
db.nur_lesen = None
assert db.palettenschein(aid)["hinweis"] == "Kanten schützen"
ok("Lesemodus ändert nichts")

print("Alle Prüfungen bestanden.")
