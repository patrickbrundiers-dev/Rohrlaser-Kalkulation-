"""Prüft die Vorschläge vom 02.11.2026 (Freigabe Patrick „K1a K2a K3b K4a K5a S1a S2a S3a S4b“):
- K1 Gleitklausel Abruf: erst nach PDF, Material +20 % über der Schwelle, nur Material gleitet, Übernehmen mit Verlauf.
- K2 Eilzuschlag: Feld im Kopf (% auf den Fertigungszuschlag), Stufen nach Arbeitstagen zu früh.
- K3 CO₂ je Teil: Funktion Vorgabe aus, Bilanz aus Material + Strom, Abschnitt im Kalkulations-PDF.
- K4 Nachkalkulation im Wiederholteil: Rückblick Laser Ist/Soll, Hinweis im Angebots-Check, Preis unverändert.
- K5 Ertrag €/Laserstunde je Kunde in der Angebots-Auswertung.
- S1 Prüfplan: Merkmale aus Länge, Gehrung und Konturen mit ISO 2768, PDF, Zusatzarbeit Erstmusterprüfung.
- S2 Support-Paket: ZIP mit Protokoll, Info, Systemprüfung, Einstellungen ohne Passwort.
- S3 Datenschutz: anonymisieren (Preise bleiben), Auskunft-PDF, Frist (Vorgabe aus).
- S4 CAM-Ordner: Stückliste CSV, Schnittplan-PDF, Inhalt.

Aufruf: python tests/test_vorschlaege_0211.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import csv
import datetime
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import (absage, cam_paket, co2, datenschutz, einstellungen_ordnung, funktionen, gleitklausel,  # noqa: E402
                       nachkalkulation as nk, pruefplan, rechnen, support, terminplan, wiederholteile)
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.stammdaten import ABRUF_LAGER  # noqa: E402


def ok(t):
    print("OK    ", t)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert SCHEMA_VERSION >= 72
ABRUF = dict(abruf="ja", abruf_jahr_von=4000, abruf_jahr_bis=6000, abruf_von=400, abruf_bis=600, abruf_laufzeit=12)
TECHNIK = dict(quelle="STEP", a=dict(winkel=30.0), b=dict(winkel=0.0),
               konturen=[dict(art="Bohrung", d=10.0, x=50.0, anzahl=3, abstand=100.0, seite="A"),
                         dict(art="Langloch", l=30.0, b=10.0, x=400.0),
                         dict(art="Text-Gravur", text="AB-10", x=20.0)])
a = db.angebot_neu(dict(nummer="A-2026-0211", kundennr="K-1001", kunde="Beispiel Metallbau GmbH", datum="2026-11-02",
                        maschine="T11", stange=6000))
p10 = db.position_neu(a, dict(pos=10, artikel="AB-10", bezeichnung="Strebe", profil_id="RE 60x40x3",
                              werkstoff_id="S235-10219", laenge=485.0, stueck=400, schneidweg=380, einstiche=4,
                              technik=json.dumps(TECHNIK)))
for n, w in ABRUF.items():
    db.angebot_aendern(a, n, w)
kopf, pos = db.angebot(a), db.positionen(a)
k, tab = db.kontext(), db.tabellen()
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
db.ergebnis_speichern(a, erg)

# ------------------------------------------------------------------ K1 Gleitklausel
v = gleitklausel.pruefen(kopf, pos, erg, k, tab, einst)
assert "erst nach dem Angebots-PDF" in v["fehlt"]
db.preisbasis_speichern(a, rechnen.preisbasis_aus(kopf, pos, k, tab))
kopf = db.angebot(a)
v = gleitklausel.pruefen(kopf, pos, erg, k, tab, einst)
assert abs(v["prozent"]) < 1e-9 and not v["faellig"] and abs(v["verkauf_alt"] - v["verkauf_neu"]) < 1e-6
w = next(z for z in db.zeilen("werkstoffe") if z["werkstoff_id"] == "S235-10219")
db.aendern("werkstoffe", w["id"], "tonnenpreis", w["tonnenpreis"] * 1.2)
k2, tab2 = db.kontext(), db.tabellen()
v = gleitklausel.pruefen(kopf, pos, erg, k2, tab2, einst)
assert abs(v["prozent"] - 20.0) < 0.05 and v["faellig"] and v["verkauf_neu"] > v["verkauf_alt"], v["prozent"]
assert gleitklausel.pruefen(kopf, pos, erg, k2, tab2, einst, schwelle=25)["faellig"] is False
assert "fällig" in gleitklausel.text(v) and v["werkstoffe"][0]["werkstoff"] == "S235-10219"
assert "Gleitklausel Material +20,0 %" in gleitklausel.verlauf_text(gleitklausel.eintrag(v))
assert "bevorratet" in gleitklausel.moeglich(dict(kopf, abruf_material=ABRUF_LAGER))
ok(f"K1 Gleitklausel: erst nach PDF, Tonnenpreis +20 % → Material +{v['prozent']:.1f} %, fällig ab Schwelle 5 %, "
   f"netto {v['verkauf_alt']:.2f} → {v['verkauf_neu']:.2f} €")

# ------------------------------------------------------------------ K2 Eilzuschlag
z0, s0 = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
k30 = dict(kopf, eilzuschlag=30)
z1, s1 = rechnen.kalkulation(k30, pos, erg, k, tab, rechnen.einstellungen_angebot(k30, db.einstellungen()))
assert s1["verkauf"] > s0["verkauf"] and s1["eilzuschlag_satz"] == 30 and s1["eilzuschlag"] > 0
assert abs(s1["material"] - s0["material"]) < 1e-9                       # nur Fertigung, nicht Material
assert terminplan.arbeitstage_zwischen(datetime.date(2026, 11, 2), datetime.date(2026, 11, 9)) == 5
e_tp = db.einstellungen()
frei = terminplan.Termin(datetime.date(2026, 11, 20), None, 1.0, [], [])          # frühester Termin Fr 20.11.
assert terminplan.eil_vorschlag(frei, datetime.date(2026, 11, 23), e_tp) is None          # Termin hält
assert terminplan.eil_vorschlag(frei, datetime.date(2026, 11, 18), e_tp) == (2, 0.15)     # 2 Arbeitstage zu früh
assert terminplan.eil_vorschlag(frei, datetime.date(2026, 11, 13), e_tp) == (5, 0.30)     # Stufe 2
from rohrlaser.angebot import KALKULATION  # noqa: E402
assert any(f.name == "eilzuschlag" for f in KALKULATION)
ok(f"K2 Eilzuschlag 30 %: {s0['verkauf']:.2f} → {s1['verkauf']:.2f} € (Material gleich), Stufen 15 %/30 % nach "
   "Arbeitstagen")

# ------------------------------------------------------------------ K3 CO₂
f_co2 = next(f for f in funktionen.FUNKTIONEN if f.name == "funktion_co2")
assert f_co2.vorgabe == "nein" and not funktionen.an("funktion_co2", db)
b = co2.angebot(kopf, pos, z0, k, einst)
assert b["gesamt"] > 0 and b["material"] > 0 and b["strom"] > 0 and len(b["positionen"]) == 1
assert "CO₂" in co2.text(b)
from rohrlaser import pdf as pdf_  # noqa: E402
pfad = tmp / "kalk.pdf"
pdf_.kalkulation_pdf(pfad, kopf, z0, s0, einst, positionen=pos, co2=b)
assert pfad.stat().st_size > 2000
ok(f"K3 CO₂: Funktion Vorgabe aus, {b['gesamt']:.1f} kg je Angebot (Material {b['material']:.1f}, Strom "
   f"{b['strom']:.1f})")

# ------------------------------------------------------------------ K4 Wiederholteil mit Nachkalkulation
alt = db.angebot_neu(dict(nummer="A-2026-0100", kundennr="K-1001", kunde="Beispiel Metallbau GmbH",
                          datum="2026-09-01", maschine="T11", stange=6000))
db.position_neu(alt, dict(pos=10, artikel="AB-10", bezeichnung="Strebe", profil_id="RE 60x40x3",
                          werkstoff_id="S235-10219", laenge=485.0, stueck=400, schneidweg=380, einstiche=4))
ka, pa = db.angebot(alt), db.positionen(alt)
ea = rechnen.einstellungen_angebot(ka, db.einstellungen())
erga = rechnen.optimieren(ka, pa, k, tab, ea)
db.ergebnis_speichern(alt, erga)
db.vorgang_setzen(alt, "Beauftragt")
za, sa = rechnen.kalkulation(ka, pa, erga, k, tab, ea)
laser_soll_h = sum(x["laser_netto"] * x["stueck"] for x in za if x) / 3600
ist = dict(laser_h=round(laser_soll_h * 1.3, 4))
vg = nk.vergleich(ka, pa, erga, k, tab, ea, ist)
ist["soll"] = nk.soll_stand(vg, ka, pa, erga, k)
db.nachkalkulation_speichern(alt, ist)
r = nk.rueckblick(json.loads(json.dumps(ist)), pa[0]["id"])
assert r and abs(r["laser_abw"] - 0.3) < 0.01 and r["laser_quelle"] == "Auftrag", r
assert "Laser +30 %" in nk.rueckblick_text(r)
treffer = wiederholteile.auswerten(wiederholteile.laden(db, a, pos), "K-1001", pos)
tr = treffer[p10][0]
assert tr.art == wiederholteile.SICHER and tr.rueckblick and "Laser +30 %" in wiederholteile.text([tr])
punkte = wiederholteile.check_punkte(treffer, pos)
assert punkte and punkte[0][0] == "HINWEIS" and "A-2026-0100" in punkte[0][1]
assert nk.rueckblick(None, 1) is None and nk.rueckblick({"soll": {}}, 1) is None
ok(f"K4 Wiederholteil: „{punkte[0][1]}“")

# ------------------------------------------------------------------ K5 Ertrag je Laserstunde je Kunde
zeilen_a = db.angebote()
ej = absage.ertrag_je_kunde(db, zeilen_a, heute=datetime.date(2026, 11, 2), zeitraum=None)
g = ej["Beispiel Metallbau GmbH"]
assert g["auftraege"] == 1 and g["laser_h"] > 0 and g["eur_h"] and g["ist"] == 1 and g["eur_h_ist"] < g["eur_h"]
ok(f"K5 Ertrag je Laserstunde: Soll {g['eur_h']:.0f} €/h, Ist {g['eur_h_ist']:.0f} €/h ({g['laser_h']:.2f} h)")

# ------------------------------------------------------------------ S1 Prüfplan
assert pruefplan.toleranz(485, "ISO 2768-m") == 0.8 and pruefplan.toleranz(10, "ISO 2768-f") == 0.1
assert pruefplan.toleranz(485, "nach Kundenvorgabe") is None
m = pruefplan.merkmale(db.positionen(a)[0], "ISO 2768-m", 40)
texte = [x["merkmal"] for x in m]
assert texte[0] == "Teilelänge" and m[0]["toleranz"] == "± 0,8 mm"
assert any(t.startswith("Gehrung Anfang") for t in texte) and not any("Ende (Ende B)" in t for t in texte)
assert any("Bohrung (3×): Maß" == t for t in texte) and any("Teilung" in t for t in texte)
assert not any("Gravur" in t for t in texte)                     # Gravuren sind kein Prüfmerkmal
bohr = next(x for x in m if x["merkmal"] == "Bohrung: Lage x ab Ende A")
assert bohr["soll"] == "50 mm"                                        # Lage wie aus der STEP, nichts verschoben
pp = pruefplan.pdf(tmp / "Pruefplan.pdf", kopf, db.positionen(a), dict(pruef_toleranz="ISO 2768-m"), k.profile)
assert Path(pp).stat().st_size > 2000
assert pruefplan.zusatz_eintragen(db, db.positionen(a)[0], 85.0) is True
assert pruefplan.zusatz_eintragen(db, db.positionen(a)[0], 85.0) is False   # nicht doppelt
assert any(z["name"] == pruefplan.ZUSATZ and z["art"] == "€/Angebot" for z in db.zeilen("zusatzarbeiten"))
ok(f"S1 Prüfplan: {len(m)} Merkmale (Länge ± 0,8, Gehrung, Bohrungen mit Teilung, Langloch), PDF, Erstmuster")

# ------------------------------------------------------------------ S2 Support-Paket
db.einstellung_setzen("passwort", "geheim123")
(tmp / "Protokoll").mkdir(exist_ok=True)
(tmp / "Protokoll" / "fehler.log").write_text("2026-11-02 ERROR Test\n", encoding="utf-8")
e = support.erstellen(db, lizenz_text="Testlizenz", system=[("Windows", "11", "10", "11", "ok")],
                      jetzt=datetime.datetime(2026, 11, 2, 16, 30))
with zipfile.ZipFile(e["pfad"]) as zf:
    namen = zf.namelist()
    es = json.loads(zf.read("einstellungen.json"))
    info = zf.read("info.txt").decode()
assert Path(e["pfad"]).name == "Support_2026-11-02_1630.zip" and Path(e["pfad"]).parent == tmp / "Support"
assert set(namen) == {"fehler.log", "info.txt", "systempruefung.txt", "einstellungen.json"}
assert es["passwort"] == "(entfernt)" and "geheim123" not in json.dumps(es) and "Testlizenz" in info
e2 = support.erstellen(db, system=[], angebot_id=a, jetzt=datetime.datetime(2026, 11, 2, 16, 31))
assert "angebot.json" in e2["dateien"] and "beigelegten Angebot" in support.text(e2)
db.einstellung_setzen("passwort", "")
ok(f"S2 Support-Paket: {', '.join(namen)}, Passwort entfernt, Angebot nur mit Haken")

# ------------------------------------------------------------------ S3 Datenschutz
from rohrlaser import angebot_mail  # noqa: E402
db.versand_merken(alt, angebot_mail.eintrag("einkauf@beispiel-metallbau.de"))
au = datenschutz.auskunft(db, "K-1001")
assert au["kunde"]["Ansprechpartner"] == "Herr Muster" and "einkauf@beispiel-metallbau.de" in au["mails"]
assert {x["nummer"] for x in au["angebote"]} == {"A-2026-0211", "A-2026-0100"}
ap = datenschutz.auskunft_pdf(tmp / "Auskunft.pdf", au, db.einstellungen())
assert Path(ap).stat().st_size > 1500
vk_vorher = db.angebot(alt)["vk_netto"]
e3 = datenschutz.anonymisieren(db, "K-1001", heute=datetime.date(2026, 11, 2))
kd = db.kunde("K-1001")
assert kd["ansprechpartner"] == "anonymisiert 02.11.2026" and not kd["telefon"] and not kd["email"]
assert kd["name"] == "Beispiel Metallbau GmbH" and e3["mails"] == 1
assert db.angebot(alt)["versand"][-1]["an"] == "anonymisiert" and db.angebot(alt)["vk_netto"] == vk_vorher
assert datenschutz.auskunft(db, "K-1001")["mails"] == []
e4 = datenschutz.anonymisieren(db, "K-1001", alles=True, heute=datetime.date(2026, 11, 2))
assert db.kunde("K-1001")["name"] == "anonymisiert K-1001" and db.angebot(a)["kunde"] == "anonymisiert K-1001"
assert len(db.positionen(a)) == 1 and e4["angebote"] == 2
# Frist: Vorgabe aus; 2 Jahre: abgelehntes Angebot von 2023 verliert die Mail, Kunde K-1002 wird anonymisiert
assert db.einstellung("datenschutz_jahre") == 0 and datenschutz.frist_anwenden(db) is None
x = db.angebot_neu(dict(nummer="A-2023-0001", kundennr="K-1002", kunde="Muster Anlagenbau KG", datum="2023-05-01"))
db.vorgang_setzen(x, "Abgelehnt")
db.versand_merken(x, angebot_mail.eintrag("einkauf@muster-anlagenbau.de"))
db.einstellung_setzen("datenschutz_jahre", 2)
fr = datenschutz.beim_start(db, heute=datetime.date(2026, 11, 2))
assert fr == dict(angebote=1, mails=1, kunden=1), fr
assert datenschutz.ist_anonym(db.kunde("K-1002")) and db.kunde("K-1002")["name"] == "Muster Anlagenbau KG"
assert datenschutz.beim_start(db, heute=datetime.date(2026, 11, 2)) is None        # einmal am Tag
db.einstellung_setzen("datenschutz_jahre", 0)
seite = next(s for s in einstellungen_ordnung.SEITEN if s.schluessel == "e_ablage")
assert any("datenschutz_jahre" in ab.namen for ab in seite.abschnitte)
ok("S3 Datenschutz: Auskunft-PDF, anonymisieren (Preise/Positionen bleiben), auch Name, Frist 2 Jahre, aus = Vorgabe")

# ------------------------------------------------------------------ S4 CAM-Ordner
kopf = db.angebot(a)
bericht = cam_paket.schreiben(tmp / cam_paket.ordnername(kopf), kopf, db.positionen(a), erg, k, tab, einst,
                              step=False)
with open(Path(bericht["ordner"]) / "Stueckliste.csv", encoding="utf-8-sig") as f:
    reihen = list(csv.reader(f, delimiter=";"))
assert reihen[0][0] == "Pos." and reihen[1][1] == "AB-10" and reihen[1][6] == "400" and reihen[1][9] == "AB-10"
assert bericht["pdf"] == "Schnittplan.pdf" and (Path(bericht["ordner"]) / "Schnittplan.pdf").is_file()
assert (Path(bericht["ordner"]) / "Inhalt.json").is_file() and Path(bericht["ordner"]).name == "A-2026-0211_CAM"
assert cam_paket.dateiname(db.positionen(a)[0]) == "AB-10_400_S235-10219.stp"
ok(f"S4 CAM-Ordner: {cam_paket.text(bericht)}")

# ------------------------------------------------------------------ Oberfläche
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser import protokoll  # noqa: E402

hf = Hauptfenster(db, stumm=True)
assert protokoll.SUPPORT is not None
s = hf.angebot_oeffnen(a)
kb = s.kopf_bereich
assert not kb.gleit_knopf.isHidden() and kb.gleit_knopf.isEnabled()
v = s.gleitklausel_pruefen(antwort=True)
assert v["faellig"] and s.kopf["versand"][-1]["art"] == "gleitklausel"
assert gleitklausel.pruefen(s.kopf, s.positionen, s.ergebnis, s.k_aktuell, s.tabellen_aktuell, s.einst)["prozent"] \
    == 0
vor = s._verkauf()
s.eilzuschlag_setzen(15)
assert s.kopf["eilzuschlag"] == 15 and s._verkauf() > vor
s.eilzuschlag_setzen(0)
assert abs(s._verkauf() - vor) < 1e-6
plan = s.pruefplan_pdf(erstmuster=False)
assert plan and Path(plan).is_file()
# R11 (07.11.2026): keine Rückfrage; steht die Erstmusterprüfung schon drin, kein „Übernehmen“
assert s.pruefplan_pdf() and not (hf.letzte_aktion and hf.letzte_aktion[0] == "Übernehmen")
ordner = s.cam_paket(tmp / "cam_gui")
assert ordner and (Path(ordner) / "Stueckliste.csv").is_file()
sp = hf.support_paket(mit_angebot=True, oeffnen=False)
assert sp and "angebot.json" in sp["dateien"]
db.einstellung_setzen("funktion_co2", "ja")
s.neu_laden()
assert "CO₂" in s.uebersicht_bereich.uebersicht.text()
s.uebersicht_bereich._gruppe_umschalten("Material")                   # Aufklappen behält die CO₂-Zeile
assert "CO₂" in s.uebersicht_bereich.uebersicht.text()
db.einstellung_setzen("funktion_co2", "nein")
s.neu_laden()
assert "CO₂" not in s.uebersicht_bereich.uebersicht.text()
hf.kunden.ansicht.selectRow(0)
pfad_a = hf.kunden.datenauskunft("K-1001", pfad=str(tmp / "auskunft_gui.pdf"))
assert pfad_a and Path(pfad_a).is_file()
assert hf.kunden.anonymisieren("K-1001", alles=False)["kunde"]
ok("Oberfläche: Gleitklausel-Knopf, Eilzuschlag, Prüfplan, CAM, Support-Paket, Datenauskunft, Anonymisieren")
print("Alle Prüfungen der Vorschläge vom 02.11.2026 bestanden.")
