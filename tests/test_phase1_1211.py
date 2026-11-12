"""Roadmap Kalkulation, Phase 1 (Freigabe Patrick 12.11.2026 „Mit Phase 1 beginnen“).

Paket 1 Preissicherheit:
MAT-009 Preisalter-Warnung (preisalter.py): Materialpreis aus 'Preise'/'Lieferlängen' älter als preisalter_tage →
        HINWEIS mit Ziel Materialanfrage; 0 = aus; ohne Datum, mit €/m in der Position oder Kundenmaterial kein Hinweis.
OFFER-017 Mindermengenzuschlag als eigene Zeile (mindermenge_zeile = ja): Stückpreise ohne Anhebung, Summe gleich.
OFFER-018 Gültigkeit je Werkstoff-Kategorie (gueltigkeit_kategorie): die kürzeste gilt, länger verlängert nie.
CAM-010 „bis zu x Stück mehr passen ohne weitere Stange“ (mehrmenge.py): Hinweis mit Stückpreis, Probe-Optimierung
        ohne zusätzliche Stange; Sätze ohne Hinweis.
CAD-004 Live-Preis im Rohr-Editor: Stückpreis mit den Eingaben und Differenz zum Öffnen (live_preis.py).
GEO-018 unklare STEP-Merkmale als Frage in der Rückfrage-Mail (rueckfrage.step_fragen).
OFFER-020 Angebotstext mit Bearbeitung aus den Merkmalen (angebotstext_bearbeitung).
ERP-001 Kunden-Stückliste (CSV/Excel) als Anfrageformular (stueckliste.py): Stückzahlen und Werkstoff je Teil.
OFFER-006 Kundenpreisliste aus dem Teilekatalog (teilekatalog.preisliste_csv) ohne interne Spalten.
OFFER-005 Preisaufteilung je Stück im Angebots-PDF (preis_aufteilung): Material + Bearbeitung (+ Fracht) = Preis.
CALC-011 Menge je Teil „Schnittlänge [m]“ und „Kantenlänge außen [m]“ (Entgraten/Trovalisieren je m).
CALC-021 Beispiel-Zusatzarbeit Reiben (€ je Stück, wie Bohren immer je Stück).
MAT-015 Werkstoff-Gleichnamen (werkstoff_namen): AISI 316L, X5CrNi18-10, St37-2 in Mail/Formular und STEP.
MACH-009 Maschine samt Schneiddaten als Datei speichern/einlesen (maschinen_datei, Knöpfe in Stammdaten Maschinen).
ASM-003 Stückliste je Satz/Schweißbaugruppe als CSV (export.stueckliste_zeilen, CSV-Export „Stückliste …“).
OFFER-010 Vorbehalt bei ungeprüften STEP-Teilen (vorbehalt_ungeprueft): Text unter der Position, leer = aus.

Aufruf: python tests/test_phase1_1211.py
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot as B  # noqa: E402
from rohrlaser import preisalter, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k != "nummer"}
ROHR = dict(B.POSITIONEN[0])          # RR 42,4x2,0 S235, 1250 mm (Profilpreis 1,45 €/kg in den Beispieldaten)
HEUTE = datetime.date.today()


def ok(text):
    print("OK  ", text)


def angebot(*positionen, kopf=None):
    i = db.angebot_neu(dict(KOPF, **(kopf or {})))
    for p in positionen:
        db.position_neu(i, p)
    s = fenster.angebot_oeffnen(i)
    s.optimieren()
    return s


def verkauf(s):
    return s._rechnung()[1]["verkauf"]


# ------------------------------------------------------------------ MAT-009 Preisalter
zeile = next(z for z in db.zeilen("preise") if (z["profil_id"], z["werkstoff_id"]) == ("RR 42,4x2,0", "S235-10219"))
db.aendern("preise", zeile["id"], "gueltig_ab", None)      # ohne Datum: kein Hinweis
s = angebot(dict(ROHR, stueck=24))
assert not [p for p in s.freigabe_punkte() if p.ziel == preisalter.ZIEL]
vorher = verkauf(s)
alt = (HEUTE - datetime.timedelta(days=45)).isoformat()
db.aendern("preise", zeile["id"], "gueltig_ab", alt)
s.neu_laden()
punkte = [p for p in s.freigabe_punkte() if p.ziel == preisalter.ZIEL]
assert len(punkte) == 1 and punkte[0].art == "HINWEIS", punkte
assert "RR 42,4x2,0 S235-10219" in punkte[0].text and "45 Tage alt" in punkte[0].text, punkte[0].text
assert "Materialanfrage" in punkte[0].details and "Pos. 10" in punkte[0].details, punkte[0].details
assert abs(verkauf(s) - vorher) < 1e-9                 # nur Hinweis
ok(f"MAT-009 Preis seit {alt} (45 Tage): {punkte[0].text}")
# Grenze, aus, €/m in der Position, Kundenmaterial
db.einstellung_setzen("preisalter_tage", 60)
assert not preisalter.punkte(s.positionen, s.k, s.tabellen, db.einstellungen())
db.einstellung_setzen("preisalter_tage", 0)
assert not preisalter.punkte(s.positionen, s.k, s.tabellen, db.einstellungen())
db.einstellung_setzen("preisalter_tage", 30)
p = dict(s.positionen[0])
assert preisalter.alte([p], s.k, s.tabellen, db.einstellungen())
assert not preisalter.alte([dict(p, preis_m=3.0)], s.k, s.tabellen, db.einstellungen())
assert not preisalter.alte([dict(p, material_herkunft=rechnen.KUNDENMATERIAL)], s.k, s.tabellen, db.einstellungen())
# zwei Positionen derselben Abmessung: ein Punkt mit beiden Positionen
e = preisalter.alte([p, dict(p, pos=20)], s.k, s.tabellen, db.einstellungen())
assert len(e) == 1 and e[0]["zeilen"] == [0, 1] and e[0]["tage"] == 45
# Hinspringen öffnet die Materialanfrage
gerufen = []
s.material_anfragen = lambda *a, **kw: gerufen.append(1)
s.check_link("check:materialanfrage")
assert gerufen == [1]
db.aendern("preise", zeile["id"], "gueltig_ab", HEUTE.isoformat())
ok("MAT-009 Grenze 60 Tage/0 = aus, €/m und Kundenmaterial ohne Hinweis, Hinspringen → Materialanfrage")

# ------------------------------------------------------------------ OFFER-017 Mindermengenzuschlag
import json  # noqa: E402

from rohrlaser import ausgabe  # noqa: E402

db.einstellung_setzen("mindestpreis", 2000.0)
klein = angebot(dict(ROHR, stueck=2))
su = klein._rechnung()[1]
assert su["mindestpreis_gilt"], su["verkauf_kalkuliert"]
mit = klein.angebot_daten(staffeln=False)
assert not [z for z in mit["zeilen"] if z.get("mindermenge")] and mit["mindestpreis"]
db.einstellung_setzen("mindermenge_zeile", "ja")
klein = angebot(dict(ROHR, stueck=2))
ohne = klein.angebot_daten(staffeln=False)
zz = [z for z in ohne["zeilen"] if z.get("mindermenge")]
teil = next(z for z in ohne["zeilen"] if z["art"] == "teil")
assert len(zz) == 1 and zz[0]["art"] == "einmal" and "Mindermengenzuschlag" in zz[0]["text"], ohne["zeilen"]
assert "2.000,00" in zz[0]["text"] and not ohne["mindestpreis"], zz[0]["text"]
assert teil["preis"] < next(z for z in mit["zeilen"] if z["art"] == "teil")["preis"]
assert abs(ohne["netto"] - mit["netto"]) <= 0.02, (ohne["netto"], mit["netto"])
assert abs(verkauf(klein) - su["verkauf"]) < 1e-6           # Rechnung unverändert
ok(f"OFFER-017 Stückpreis {teil['preis']:.2f} € + Mindermengenzuschlag {zz[0]['preis']:.2f} € = "
   f"{ohne['netto']:.2f} € (vorher {mit['netto']:.2f} € in den Stückpreisen)")
db.einstellung_setzen("mindermenge_zeile", "nein")
db.einstellung_setzen("mindestpreis", 0.0)

# ------------------------------------------------------------------ OFFER-018 Gültigkeit je Kategorie
einst = dict(db.einstellungen(), gueltigkeit=30)
assert ausgabe.gueltigkeit_tage(einst, s.positionen, s.k) == 30
assert ausgabe.gueltigkeit_kategorien(dict(einst, gueltigkeit_kategorie="Edelstahl 14; Stahl: 10 Tage")) == \
    {"edelstahl": 14, "stahl": 10}
assert ausgabe.gueltigkeit_tage(dict(einst, gueltigkeit_kategorie="Edelstahl 14"), s.positionen, s.k) == 30
assert ausgabe.gueltigkeit_tage(dict(einst, gueltigkeit_kategorie="Stahl 10"), s.positionen, s.k) == 10
assert ausgabe.gueltigkeit_tage(dict(einst, gueltigkeit_kategorie="Stahl 60"), s.positionen, s.k) == 30
db.einstellung_setzen("gueltigkeit_kategorie", "Stahl 10")
g = angebot(dict(ROHR, stueck=24), kopf=dict(datum="2026-11-01"))
d = g.angebot_daten(staffeln=False)
assert d["gueltig_tage"] == 10
assert ausgabe.gueltig_bis(g.kopf, g.einst, g.positionen, g.k) == datetime.date(2026, 11, 11)
db.einstellung_setzen("gueltigkeit_kategorie", "")
ok("OFFER-018 Stahl 10 Tage: gültig bis 11.11.2026 statt 01.12.2026; Edelstahl 14 und Stahl 60 ändern nichts")

# ------------------------------------------------------------------ OFFER-010 Vorbehalt
gelb = dict(ROHR, stueck=24, step_merkmale=json.dumps(dict(ampel="gelb", ampel_gruende=["Gewinde unklar"])))
v = angebot(gelb, dict(ROHR, pos=20, stueck=24))
assert not any("Vorbehalt" in z["text"] for z in v.angebot_daten(staffeln=False)["zeilen"])
db.einstellung_setzen("vorbehalt_ungeprueft", "Preis unter Vorbehalt der Zeichnungsprüfung")
v = angebot(gelb, dict(ROHR, pos=20, stueck=24))
texte = [z["text"] for z in v.angebot_daten(staffeln=False)["zeilen"] if z["art"] == "teil"]
assert texte[0].endswith("\nPreis unter Vorbehalt der Zeichnungsprüfung") and "Vorbehalt" not in texte[1], texte
db.einstellung_setzen("vorbehalt_ungeprueft", "")
ok("OFFER-010 nur die gelbe Position bekommt den Vorbehalt, leer = aus")

# ------------------------------------------------------------------ CAM-010 Mehrmenge
from rohrlaser import mehrmenge  # noqa: E402

m = angebot(dict(ROHR, stueck=22))
n_st = len(m.ergebnis["stangen"])
kand = mehrmenge.kandidaten(m.kopf, m.positionen, m.ergebnis, m.k)
assert kand.get(0, 0) >= 1, (kand, [x.get("rest") for x in m.ergebnis["stangen"]])
pk = [p for p in m.freigabe_punkte(mehrmenge=True) if "Stück mehr passen ohne weitere Stange" in p.text]
assert len(pk) == 1 and pk[0].art == "HINWEIS" and pk[0].ziel == "pos:0", pk
mehr = int(pk[0].text.split("bis zu ")[1].split(" ")[0])
probe = angebot(dict(ROHR, stueck=22 + mehr))
assert len(probe.ergebnis["stangen"]) == n_st, (len(probe.ergebnis["stangen"]), n_st)
assert probe._rechnung()[0][0]["preis_teil"] < m._rechnung()[0][0]["preis_teil"]
assert m.positionen[0]["stueck"] == 22                     # nur Hinweis
assert not [p for p in probe.freigabe_punkte(mehrmenge=True) if "Stück mehr passen" in p.text]     # Stangen jetzt voll
assert not mehrmenge.geeignet(dict(m.positionen[0], satz="A"))
ok(f"CAM-010 {pk[0].text}; Probe mit {22 + mehr} Stück: {n_st} Stangen wie vorher")

# ------------------------------------------------------------------ CAD-004 Live-Preis
from rohrlaser import live_preis  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

lv = angebot(dict(ROHR, stueck=24))
p0 = lv.positionen[0]
d = SchneidwegDialog(lv, p0, lv.k.profile[p0["profil_id"]], lv.kopf, lv.k, lv.tabellen, lv.db, lv.positionen)
d.rechnen()
jetzt, start = d.live_preis()
assert abs(jetzt - start) < 1e-6 and abs(start - lv._rechnung()[0][0]["preis_teil"]) < 0.1, (jetzt, start)
assert live_preis.text(jetzt, start)[1] == "Stückpreis wie beim Öffnen"
alt_eingaben = d.eingaben
d.eingaben = lambda: dict(alt_eingaben(), konturen=[dict(art="Bohrung", anzahl=12, d=12)])
d.rechnen()
jetzt2, start2 = d.live_preis()
assert start2 == start and jetzt2 > start + 0.01, (jetzt2, start)
wert, tip = live_preis.text(jetzt2, start2)
assert "(+" in wert and "beim Öffnen" in tip, (wert, tip)
assert lv.positionen[0] == p0                           # nur Anzeige
assert SchneidwegDialog(lv, dict(p0, id=None), lv.k.profile[p0["profil_id"]], lv.kopf, lv.k, lv.tabellen,
                        neu=True).live_preis() is None
ok(f"CAD-004 Live-Preis: 12 Bohrungen Ø12 → {wert} (beim Öffnen {start:.2f} €)")

# ------------------------------------------------------------------ GEO-018 Rückfrage aus dem Prüfstatus
from rohrlaser import rueckfrage  # noqa: E402

fr = rueckfrage.step_fragen([
    dict(ROHR, step_merkmale=json.dumps(dict(ampel="gelb", ampel_gruende=["Gewinde ja/nein unklar"]))),
    dict(ROHR, pos=20, artikel="4711-002", step_merkmale=json.dumps(dict(merkmale=[
        dict(merkmal="Werkstoff", wert="", status="nicht erkannt", grund="nicht in der STEP"),
        dict(merkmal="Länge", wert="1250", status="sicher")]))),
    dict(ROHR, pos=30, step_merkmale=json.dumps(dict(geprueft=True, ampel="gelb", ampel_gruende=["x"]))),
    dict(ROHR, pos=40)])
assert fr == ["Pos. 10 4711-001: bitte bestätigen – Gewinde ja/nein unklar",
              "Pos. 20 4711-002: bitte bestätigen – Werkstoff (nicht in der STEP)"], fr
assert fr[1] in rueckfrage.punkte([], [dict(ROHR, pos=20, artikel="4711-002", step_merkmale=json.dumps(dict(
    merkmale=[dict(merkmal="Werkstoff", wert="", status="nicht erkannt", grund="nicht in der STEP")])))], [None])
ok("GEO-018 gelbe Gründe und offene Merkmale als Fragen, bestätigte und ohne STEP nicht")

# ------------------------------------------------------------------ OFFER-020 Bearbeitung im Angebotstext
tech = json.dumps(dict(a=dict(winkel=45), b=dict(winkel=0), konturen=[
    dict(art="Bohrung", anzahl=4, d=8), dict(art="Bohrung", anzahl=2, d=10), dict(art="Langloch", anzahl=1, l=20, b=8),
    dict(art="Gravur", anzahl=1)]))
assert ausgabe.bearbeitung_text(dict(ROHR, technik=tech)) == "Bearbeitung: Gehrung 45°, 6 × Bohrung, 1 × Langloch"
assert ausgabe.bearbeitung_text(dict(ROHR)) == ""
bt = angebot(dict(ROHR, stueck=24, technik=tech))
assert "Bearbeitung:" not in bt.angebot_daten(staffeln=False)["zeilen"][0]["text"]
db.einstellung_setzen("angebotstext_bearbeitung", "ja")
bt = angebot(dict(ROHR, stueck=24, technik=tech))
t0 = bt.angebot_daten(staffeln=False)["zeilen"][0]["text"]
assert "\nBearbeitung: Gehrung 45°, 6 × Bohrung, 1 × Langloch" in t0, t0
db.einstellung_setzen("angebotstext_bearbeitung", "nein")
ok("OFFER-020 Angebotstext: " + t0.replace("\n", " | "))

# ------------------------------------------------------------------ ERP-001 Kunden-Stückliste
import zipfile  # noqa: E402

from rohrlaser import anfragen, formular, pdf_art, stueckliste  # noqa: E402

liste = tmp / "Stueckliste.csv"
liste.write_bytes("Stückliste Projekt 4711\nPos.;Zeichnungs-Nr.;Benennung;Werkstoff;Menge\n"
                  "1;MG-01;Stiel;1.4301;20\n2;MG-02;Riegel;S235JRH;8\nSumme;;;;28\n".encode("cp1252"))
g = pdf_art.lesen(liste)
assert g and g["datei"] == "Stueckliste.csv" and len(g["tabelle"]) == 2, g
assert g["tabelle"][0]["artikel"] == "MG-01" and g["tabelle"][0]["menge"] == "20", g["tabelle"]
st = formular.stueck_tabelle(g["tabelle"], ["MG-01 Stiel.stp", "MG-02.stp", "MG-03.stp"])
assert st == {"MG-01 Stiel.stp": (20, True), "MG-02.stp": (8, True)}, st
assert formular.datei_lesen(liste)["tabelle"] == g["tabelle"]
assert ".csv" in anfragen.FORMULAR and ".csv" not in anfragen.BILD
# Excel mit Spalte Datei statt Artikel
x = tmp / "Liste.xlsx"
with zipfile.ZipFile(x, "w") as z:
    z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               "<si><t>Datei</t></si><si><t>Anzahl</t></si><si><t>Rahmen A.step</t></si></sst>")
    z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row>'
               '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="C2"><v>12.0</v></c></row></sheetData></worksheet>')
assert stueckliste.zellen(x) == [["Datei", "", "Anzahl"], ["Rahmen A.step", "", "12"]], stueckliste.zellen(x)
gx = pdf_art.lesen(x)
assert gx["tabelle"][0]["artikel"] == "Rahmen A" and gx["tabelle"][0]["menge"] == "12", gx["tabelle"]
assert formular.stueck_tabelle(gx["tabelle"], ["Rahmen A.step"]) == {"Rahmen A.step": (12, True)}
assert stueckliste.lesen(tmp / "fehlt.csv") is None
ok("ERP-001 CSV (cp1252, Titelzeile, Summe) und Excel mit Spalte Datei: Stückzahlen je STEP-Datei")

# ------------------------------------------------------------------ OFFER-006 Kundenpreisliste
from rohrlaser import teilekatalog  # noqa: E402

sp = dict(zeilen=[dict(schluessel=10, einheit="Stk", menge=50, preis_einheit=10.9),
                  dict(schluessel=10, einheit="Stk", menge=10, preis_einheit=12.34),
                  dict(schluessel=20, einheit="Stk", menge=10, preis_einheit=5.0)])
assert teilekatalog.stufen_aus_staffeln(sp, 10) == [(10, 12.34), (50, 10.9)]
pl = teilekatalog.preisliste_csv([
    dict(artikel="4711-001", bezeichnung="Holm", werkstoff="S235", laenge=1250.0, preis=12.34, menge=10,
         stufen=[(10, 12.34), (50, 10.9)], datum="2026-11-12", nummer="A-1", vorgang="Beauftragt", auftraege=2),
    dict(artikel="ohne Preis", preis=None)])
zeilen_pl = pl.strip().split("\r\n")
assert zeilen_pl[0] == "Artikel;Bezeichnung;Werkstoff;Länge [mm];Preis je Stück [€ netto];Stand;Angebot", zeilen_pl
assert zeilen_pl[1] == "4711-001;Holm;S235;1.250;ab 10 Stk: 12,34; ab 50 Stk: 10,90;2026-11-12;A-1" or \
    "ab 10 Stk: 12,34; ab 50 Stk: 10,90" in zeilen_pl[1], zeilen_pl
assert len(zeilen_pl) == 2 and "Beauftragt" not in pl
ok("OFFER-006 Kundenpreisliste: " + zeilen_pl[1])

# ------------------------------------------------------------------ OFFER-005 Preisaufteilung
pa = angebot(dict(ROHR, stueck=20))
t0 = next(z for z in pa.angebot_daten(staffeln=False)["zeilen"] if z["art"] == "teil")
assert "Preisaufteilung" not in t0["text"], t0["text"]
db.einstellung_setzen("preis_aufteilung", "ja")
pa = angebot(dict(ROHR, stueck=20))
t1 = next(z for z in pa.angebot_daten(staffeln=False)["zeilen"] if z["art"] == "teil")
zeile_pa = t1["text"].splitlines()[-1]
assert zeile_pa.startswith("Preisaufteilung je Stück: Material "), t1["text"]
kz = pa._rechnung()[0][0]
m, b, f = ausgabe.preis_aufteilung(kz)
assert m > 0 and b > 0 and abs(m + b + f - kz["preis_teil"]) < 0.011, (m, b, f, kz["preis_teil"])
assert t1["preis"] == t0["preis"]
assert ausgabe.preis_aufteilung(dict(preis_teil=0.0)) is None
db.einstellung_setzen("preis_aufteilung", "nein")
ok(f"OFFER-005 {zeile_pa} (Stückpreis {kz['preis_teil']:.2f} €)")

# ------------------------------------------------------------------ ASM-003 Stückliste
from rohrlaser import export  # noqa: E402

s_st = angebot(dict(ROHR, pos=10, artikel="H-1", satz="Gestell", je_satz=2, stueck=8),
               dict(ROHR, pos=20, artikel="H-2", satz="Gestell", je_satz=1, stueck=4, laenge=600.0),
               dict(ROHR, pos=30, artikel="E-1", stueck=5))
st = export.stueckliste_zeilen(s_st.kopf, s_st.positionen, s_st.k, s_st.tabellen)
sp_ = export.STUECKLISTE_SPALTEN
assert [z[0] for z in st] == ["1", "2", "2", "1"], st
assert st[0][sp_.index("Menge_gesamt")] == "4" and st[0][sp_.index("Bezeichnung")] == "Satz Gestell", st[0]
assert st[1][sp_.index("Menge_je_Satz")] == "2" and st[1][sp_.index("Menge_gesamt")] == "8", st[1]
assert st[2][sp_.index("Laenge_mm")] == "600" and st[2][sp_.index("Zukauf")] == "nein", st[2]
assert st[3][sp_.index("Satz")] == "" and float(st[3][sp_.index("Gewicht_kg_je_Stueck")]) > 0, st[3]
ziel = tmp / "csv"
ziel.mkdir()
pfad = s_st.csv_stueckliste(str(ziel))
assert pfad and pfad.name.endswith("Stueckliste.csv"), pfad
assert pfad.read_bytes().decode("utf-8-sig").startswith(";".join(sp_)), pfad.read_text()
ok("ASM-003 Stückliste: " + " | ".join(";".join(z) for z in st[:2]))

# ------------------------------------------------------------------ MACH-009 Maschinendatei
from rohrlaser import maschinen_datei as md  # noqa: E402
from rohrlaser.fenster import StammdatenSeite  # noqa: E402
from rohrlaser.stammdaten import MASCHINEN  # noqa: E402

meld = []
ms = StammdatenSeite(db, MASCHINEN, lambda text, fehler=False: meld.append(text))
m0 = ms.modell.daten[0]
mid = m0["maschinen_id"]
n_sd = sum(1 for z in db.zeilen("schneiddaten") if z["maschinen_id"] == mid)
assert n_sd > 0
datei = ms.maschine_speichern(tmp / f"m{md.ENDUNG}", zeile=m0)
assert datei and md.lesen(datei)["maschine"]["maschinen_id"] == mid
# gleiche ID ohne Wahl: Fehler, nichts geändert
assert ms.maschine_einlesen(datei, ersetzen=False) is None and "gibt es schon" in meld[-1], meld[-1]
# unter neuer ID: Maschine + alle Schneiddaten neu
e = ms.maschine_einlesen(datei, neue_id="Test-PC")
assert e and not e["ersetzt"] and e["schneiddaten"] == n_sd and e["sicherung"], e
assert sum(1 for z in db.zeilen("schneiddaten") if z["maschinen_id"] == "Test-PC") == n_sd
# ersetzen: geänderte Werte kommen zurück, eigene Zeile der Maschine fällt weg
t = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "Test-PC")
db.aendern("maschinen", t["id"], "bezeichnung", "geändert")
db.neu("schneiddaten", dict(next(z for z in db.zeilen("schneiddaten") if z["maschinen_id"] == "Test-PC"),
                            wand_bis=99.0))
d = md.lesen(datei)
d["maschine"]["unbekannt"] = 1
e = md.importieren(db, d, neue_id="Test-PC", ersetzen=True, sichern=False)
assert e["ersetzt"] and e["weggelassen"] == ["unbekannt"], e
t = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "Test-PC")
assert t["bezeichnung"] == m0.get("bezeichnung"), t
assert sum(1 for z in db.zeilen("schneiddaten") if z["maschinen_id"] == "Test-PC") == n_sd
(tmp / "kaputt.rlmaschine").write_text("{}", encoding="utf-8")
assert ms.maschine_einlesen(tmp / "kaputt.rlmaschine") is None and "keine Maschinendatei" in meld[-1]
ok(f"MACH-009 Maschine {mid} mit {n_sd} Schneiddaten gespeichert, als Test-PC eingelesen und ersetzt")

# ------------------------------------------------------------------ CALC-011 Schnittlänge / Kantenlänge außen
import json as _json  # noqa: E402
import math  # noqa: E402

from rohrlaser import zusatz_regeln as zr  # noqa: E402
from rohrlaser.stammdaten import REGEL_MENGEN  # noqa: E402

assert zr.SCHNITTLAENGE in REGEL_MENGEN and zr.KANTE_AUSSEN in REGEL_MENGEN
sc = angebot(dict(ROHR, schneidweg=850.0))
pc = sc.positionen[0]
assert abs(zr.laenge_bezug(zr.SCHNITTLAENGE, pc, sc.k) - 0.85) < 1e-9
assert abs(zr.laenge_bezug(zr.KANTE_AUSSEN, pc, sc.k) - 2 * math.pi * 42.4 / 1000) < 1e-6
assert zr.laenge_bezug(zr.SCHNITTLAENGE, dict(pc, schneidweg=None), sc.k) is None
entgr = next(z for z in sc.tabellen["zusatzarbeiten"] if z["name"] == "Entgraten")
st_e = rechnen.zusatz_stand(entgr, rechnen.stundensaetze(sc.tabellen))
regel = dict(name="Entgraten je m", zusatzarbeit="Entgraten", zuordnung="nur Preis", aktiv="ja", art="€/m",
             preis=0.8, menge_art=zr.SCHNITTLAENGE)
pe = dict(pc, zusatz=_json.dumps([dict(name="Entgraten", menge=None, preis=None, text=None, stand=st_e)]))
ze = rechnen.zusatz_werte(pe, sc.k, dict(sc.tabellen, arbeitsgang_regeln=[regel]))[0]
assert abs(ze["menge"] - 0.85) < 1e-9 and abs(ze["betrag"] - 0.68) < 1e-9, ze
ze2 = rechnen.zusatz_werte(pe, sc.k, dict(sc.tabellen, arbeitsgang_regeln=[dict(regel, menge_art=zr.KANTE_AUSSEN)]))[0]
assert abs(ze2["menge"] - 2 * math.pi * 0.0424) < 1e-6, ze2
ok(f"CALC-011 Entgraten 0,80 €/m: Schnittlänge 0,85 m = {ze['betrag']:.2f} €, Kantenlänge außen "
   f"{ze2['menge']:.3f} m = {ze2['betrag']:.2f} €")

# ------------------------------------------------------------------ CALC-021 Reiben
reiben = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == "Reiben")
assert reiben["art"] == "€/Stück" and reiben["preis"] > 0 and reiben["aktiv"] == "ja" and zr.nur_stueck("Reiben")
ok("CALC-021 Reiben vorbelegt: 0,80 € je Bohrung, nur € je Stück")

# ------------------------------------------------------------------ MAT-015 Werkstoff-Gleichnamen
from rohrlaser import mail, step_material, werkstoff_namen  # noqa: E402

ws = db.zeilen("werkstoffe")
assert mail.werkstoff("Material: AISI 441, 20 Stück", ws)[0] == "1.4509"
assert mail.werkstoff("Werkstoff X6Cr17", ws)[0] == "1.4016"
w_st = mail.werkstoff("Rohr aus St37-2", ws)
assert w_st[0] is None and set(w_st[2]) == {"S235-10219", "S235-10210"}, w_st      # zwei passen: Rückfrage
assert mail.werkstoff("Rohr aus St37-2", ws, vorgabe="S235-10219")[0] == "S235-10219"
assert mail.werkstoff("Werkstoff AlMgSi0,5", ws)[0] == "AW6060-T66"
assert mail.werkstoff("Werkstoff S235", ws)[0] is None                # wie bisher: mehrdeutig
wsd = {z["werkstoff_id"]: z for z in ws}
assert step_material.vorschlag("AISI 430", wsd)[0] == "1.4016"
assert step_material.vorschlag("Stainless Steel X2CrTiNb18", wsd)[0] == "1.4509"
# eigene Gruppe aus der Einstellung
assert mail.werkstoff("Rohr RSt37-2", ws, vorgabe="S235-10219")[0] is None
db.einstellung_setzen("werkstoff_gleichnamen", "S235JRH = RSt37-2; 1.4301 = A2")
assert mail.werkstoff("Rohr RSt37-2", ws, vorgabe="S235-10219")[0] == "S235-10219"
assert mail.werkstoff("Schrauben A2, Rohr", ws)[0] == "1.4301"
db.einstellung_setzen("werkstoff_gleichnamen", "")
assert not werkstoff_namen.eigene_namen()
ok("MAT-015 AISI 441 → 1.4509, X6Cr17 → 1.4016, St37-2 → S235 (Vorgabe), AlMgSi0,5 → AW6060, eigene Gruppe RSt37-2")

print("Alle Tests Phase 1 bestanden.")
