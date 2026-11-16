"""Werkstatt und Maschine (Plan ArTube-Unterlagen E1, E3, Patrick 12.11.2026 „Alles einbauen“):
- W1 Hinweis für den Bediener je Position: in den Werkstattpapieren (Hinweise) und auf dem Etikett
- W2 CAM-Paket: Stückliste mit Messungen, Schnittqualität, Kante oxidfrei, Mikrostege, Teil am Stangenende, Hinweis
- W3 Ist-Zeiten aus CSV (E2): Trennzeichen, Zeitformate, Spaltenvorschlag, Zuordnung über Position/Programmname,
  Nachkalkulation übernimmt die Laufzeit je Teil
- W5 Schrift ausschneiden als Schablonenschrift mit Stegen (D5): Schneidweg, Einstiche, Stege
- W4 Gravurtext mit Platzhaltern (D2): ausfüllen, laufende Nummer, Grenzen, Gravurlänge, CAM-Gravurtexte

Aufruf: python tests/test_werkstatt_artube.py
"""
import csv
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import ausgabe, cam_paket, etiketten, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "w.db")
ma = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
db.aendern("maschinen", ma["id"], "stangenende", "ja")
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(a, dict(pos=10, artikel="W1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=2900,
                        stueck=2, schneidweg=320, einstiche=2, bediener="Grat innen entfernen", messungen=2,
                        messart="sorgfältig", schnittqualitaet="Qualität", oxidfrei="ja"))
db.position_neu(a, dict(pos=20, artikel="W2", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500,
                        stueck=1, schneidweg=320, einstiche=2))
kopf, pos = db.angebot(a), db.positionen(a)
k, tab = db.kontext(), db.tabellen()
erg = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())

# ------------------------------------------------------------------ W1
wp = ausgabe.werkstatt(kopf, pos, erg, k, tab)
h = [x for x in wp["hinweise"] if x["text"] == "Grat innen entfernen"]
assert h and h[0]["werkstoff"].startswith("Pos. 10"), wp["hinweise"]
et = etiketten.etiketten(kopf, pos)
assert "! Grat innen entfernen" in et[0]["zeilen"] and not any(z.startswith("! ") for z in et[1]["zeilen"])
ok("W1 Hinweis für den Bediener: Werkstattpapiere „Pos. 10 W1: Grat innen entfernen“, Etikett „! …“")

# ------------------------------------------------------------------ W2
ziel = tmp / "cam"
cam_paket.schreiben(ziel, kopf, pos, erg, k, tab, db.einstellungen(), step=False)
with open(ziel / "Stueckliste.csv", encoding="utf-8-sig") as f:
    zeilen = list(csv.reader(f, delimiter=";"))
kopfzeile = zeilen[0]
for n in ("Messungen", "Schnittqualität", "Kante oxidfrei", "Mikrostege", "Teil am Stangenende",
          "Hinweis für den Bediener"):
    assert n in kopfzeile, kopfzeile
z10 = dict(zip(kopfzeile, next(z for z in zeilen[1:] if z[0] == "10")))
assert z10["Messungen"] == "2 × sorgfältig" and z10["Schnittqualität"] == "Qualität" and z10["Kante oxidfrei"] == "ja"
assert z10["Hinweis für den Bediener"] == "Grat innen entfernen"
ende = {z[0]: dict(zip(kopfzeile, z))["Teil am Stangenende"] for z in zeilen[1:]}
assert any(ende.values()) == any(s.get("stangenende") for s in erg["stangen"]), (ende, erg["stangen"])
ok(f"W2 CAM-Stückliste mit neuen Spalten, Teil am Stangenende {ende}")
# ------------------------------------------------------------------ W3
from rohrlaser import istzeiten  # noqa: E402
assert istzeiten.zeit_s("01:02:03") == 3723 and istzeiten.zeit_s("2:30") == 150
assert istzeiten.zeit_s("1,5 min") == 90 and istzeiten.zeit_s("95 s") == 95 and istzeiten.zeit_s("12", "min") == 720
assert istzeiten.zeit_s("0,1 h") == 360 and istzeiten.zeit_s("abc") is None
kopf_csv, zeilen_csv = istzeiten.lesen(text="Programmname,Stk,Bearbeitungszeit\nW1_QR40.lst,2,00:01:10\n"
                                            "W1_QR40.lst,2,00:01:30\nX9.lst,1,10\n")
zu = istzeiten.vorschlag_zuordnung(kopf_csv)
assert zu == dict(artikel=0, pos=None, zeit=2, stueck=1), zu
teile = [dict(id=1, pos=10, artikel="W1", stueck=2), dict(id=2, pos=20, artikel="W2", stueck=1)]
je, offen = istzeiten.zuordnen(teile, zeilen_csv, zu)
assert je == {1: 80.0} and len(offen) == 1, (je, offen)
je, _ = istzeiten.zuordnen(teile, zeilen_csv, zu, gilt=istzeiten.GESAMT)
assert je == {1: 40.0}, je                                      # 160 s für 4 Stück
k2, z2 = istzeiten.lesen(text="Pos;Laufzeit\n20;1,5\n")
assert istzeiten.zuordnen(teile, z2, istzeiten.vorschlag_zuordnung(k2), "min")[0] == {2: 90.0}
# Oberfläche: Nachkalkulation übernimmt
import os  # noqa: E402
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, tmp, stumm=True)
seite = fenster.angebot_oeffnen(a)
assert seite.optimieren()
ts = seite.nachkalk._teile_soll()
assert ts, "keine Laserteile"
datei = tmp / "ist.csv"
datei.write_text("Artikel;Laufzeit [s]\nW1;42\nW2;17\n", encoding="cp1252")
je = seite.nachkalk.csv_uebernehmen(datei, istzeiten.vorschlag_zuordnung(istzeiten.lesen(datei)[0]))
lauf = db.angebot(a)["nachkalkulation"]["laufzeit"]
assert je and all(lauf[str(t["id"])] in (42.0, 17.0) for t in ts), (je, lauf)
d = __import__("rohrlaser.nachkalk_seite", fromlist=["x"]).IstZeitenDialog(seite.nachkalk, *istzeiten.lesen(datei), ts)
assert "Treffer: 2 von 2" in d.info.text(), d.info.text()
ok(f"W3 Ist-Zeiten aus CSV: Formate, Spaltenvorschlag, Programmname „W1_QR40.lst“ → W1, übernommen {lauf}")
# ------------------------------------------------------------------ W4
from rohrlaser import gravur_platzhalter as gp, gravur_text  # noqa: E402
pg = dict(pos=10, artikel="W1", stueck=20, gravur_text="{Angebot} {Artikel} | {Nr} {KW}")
kg = dict(nummer="2026-0517", kunde="Test", datum="2026-11-12")
assert gp.ausfuellen(pg["gravur_text"], pg, kg, 3) == "2026-0517 W1 | 3/20 KW46"
assert gp.bereiche(gp.text_fuer(pg, kg)) == ["2026-0517 W1", "20/20 KW46"]
assert gp.ausfuellen("{Datum}", pg, kg) == "12.11.26" and gp.ausfuellen("{Pos}/{Stück}", pg) == "10/20"
assert len(gp.texte(pg, kg)) == 20 and gp.texte(pg, kg)[-1].startswith("2026-0517 W1 | 20/20")
assert gp.pruefen(pg, kg) == [] and gp.hoehe(pg) == 3.0
assert gp.pruefen(dict(pg, gravur_text="{Auftrag}"), kg)[0].startswith("WARNUNG: Gravurtext: Platzhalter {Auftrag}")
assert "höchstens 5" in gp.pruefen(dict(pg, gravur_text="a|b|c|d|e|f"))[0]
assert "Zeichen" in gp.pruefen(dict(pg, gravur_text="X" * 31))[0]
assert gp.pruefen(dict(pg, bg_gravur=2))[0].startswith("HINWEIS")
erw = gravur_text.laenge("2026-0517 W1", 3) + gravur_text.laenge("20/20 KW46", 3)
assert abs(rechnen.gravur_artikel(dict(pg, profil_id="QR 40x40x3"), kg) - erw) < 1e-9
assert rechnen.gravur_artikel(dict(artikel="W1", profil_id="QR 40x40x3")) == 0          # ohne Höhe, ohne Vorlage
assert gp.step_gravur(dict(artikel="W1", bg_gravur=4)) == ("W1", 4)
assert gp.step_gravur(pg, kg) == ("2026-0517 W1  1/20 KW46", 3.0)
pid = pos[0]["id"]
db.position_aendern(pid, "gravur_text", "{Artikel}-{Nr}")
kopf, pos = db.angebot(a), db.positionen(a)
erg = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())
ziel = tmp / "cam2"
bericht = cam_paket.schreiben(ziel, kopf, pos, erg, k, tab, db.einstellungen(), step=False)
with open(ziel / "Gravurtexte.csv", encoding="utf-8-sig") as f:
    gz = list(csv.reader(f, delimiter=";"))
assert gz[0] == ["Pos.", "Artikel", "lfd. Nr.", "Gravurtext"] and gz[1][3] == "W1-1/2" and gz[2][3] == "W1-2/2", gz
with open(ziel / "Stueckliste.csv", encoding="utf-8-sig") as f:
    st = list(csv.reader(f, delimiter=";"))
assert dict(zip(st[0], st[1]))["Gravurtext"] == "W1-1/2 … W1-2/2"
assert bericht.get("gravurtexte") == "Gravurtexte.csv"
ok("W4 Gravurtext „{Angebot} {Artikel} | {Nr} {KW}“ → „2026-0517 W1 | 3/20 KW46“, Grenzen 5 Bereiche/30 Zeichen/3 mm, "
   "Gravurlänge in der Laserzeit, CAM Gravurtexte.csv je Teil")
# ------------------------------------------------------------------ W5
from rohrlaser import schneidweg as sw  # noqa: E402
sch = gravur_text.schablone("OA", 12)
assert sch["einstiche"] == 3 and sch["stege"] == 3 and sch["breite"] == 2.0, sch     # O: 1 Schlitz + 1 Steg, A: 2 + 2
assert abs(sch["laenge"] - (2 * gravur_text.laenge("OA", 12) + 3 * 2 * 2.0)) < 0.05
qr = k.profile["QR 40x40x3"]
gr = rechnen.kontur_regel(ma, rechnen.wand_schneiden(qr))
txt = dict(art=sw.TEXT_GRAVUR, anzahl=1, text="OA", hoehe=12)
graviert = sw.rechnen(dict(a={}, b={}, konturen=[txt]), qr, gr, None, ma)
geschnitten = sw.rechnen(dict(a={}, b={}, konturen=[dict(txt, ausschneiden=True)]), qr, gr, None, ma)
assert geschnitten["einstiche"] - graviert["einstiche"] == 3, (geschnitten["einstiche"], graviert["einstiche"])
assert abs(geschnitten["schneidweg"] - graviert["schneidweg"] - sch["laenge"]) < 0.1
assert "Schablonenschrift, 3 Stege" in geschnitten["schritte"][-1]["text"]
ok(f"W5 Schrift ausschneiden „OA“ 12 mm: {sch['laenge']:.1f} mm Schneidweg, 3 Einstiche, 3 Stege statt Gravur")
print("Alle Werkstatt-Tests (ArTube) bestanden.")
