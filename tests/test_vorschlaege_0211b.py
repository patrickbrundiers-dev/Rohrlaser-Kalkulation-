"""Prüft die Vorschläge F, G, H und J vom 02.11.2026 (Freigaben Patrick „Alle weiter …“, „Alle Empfehlungen …“,
„Alle Empfehlungen j4 nicht Einbau“).

Aufruf: python tests/test_vorschlaege_0211b.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import (auslastung, etiketten, fassung_vergleich, freigabe, kalk_hinweise, lager,  # noqa: E402
                       lieferantenangebote, lieferschein, maschinen_vergleich, monatsbericht, positionsvorlagen,
                       preisschicht, rechnen, rueckfrage, sammel_preis, teilekatalog, terminplan)
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
a = db.angebot_neu(dict(nummer="A-2026-0300", kundennr="K-1001", kunde="Beispiel Metallbau GmbH", datum="2026-10-20",
                        maschine="T11", stange=6000))
p10 = db.position_neu(a, dict(pos=10, artikel="AB-10", bezeichnung="Strebe", profil_id="RE 60x40x3",
                              werkstoff_id="S235-10219", laenge=485.0, stueck=400, schneidweg=380, einstiche=4))
p20 = db.position_neu(a, dict(pos=20, artikel="AB-20", bezeichnung="Riegel", profil_id="RE 60x40x3",
                              werkstoff_id="S235-10219", laenge=900.0, stueck=100, schneidweg=380, einstiche=2))
kopf, pos = db.angebot(a), db.positionen(a)
k, tab = db.kontext(), db.tabellen()
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
db.ergebnis_speichern(a, erg)

# ------------------------------------------------------------------ F1 Maschinenvergleich
liste = maschinen_vergleich.vergleich(kopf, pos, k, tab, db.einstellungen(), db.zeitbasis_vorgabe)
assert liste[0]["maschine"] == "T11" and len(liste) == len(k.maschinen), liste
assert all(r["verkauf"] for r in liste if r["moeglich"])
billig = dict(liste[0], verkauf=liste[0]["verkauf"] * 0.9, maschine="X")
assert maschinen_vergleich.check_punkt(liste + [billig], "T11")[0] == "HINWEIS"
assert maschinen_vergleich.check_punkt(liste[:1], "T11") is None
ok(f"F1 Maschinenvergleich: {', '.join(r['maschine'] for r in liste)}, Hinweis ab 5 %")

# ------------------------------------------------------------------ F7 Sperrtage
gesperrt = auslastung.betriebsruhe("10.11.2026; 12.11.2026-13.11.2026")
assert datetime.date(2026, 11, 12) in gesperrt and datetime.date(2026, 11, 13) in gesperrt
mo = datetime.date(2026, 11, 9)
voll = auslastung.kapazitaet(mo, 8, 0, 1.0, "NW", set())
weniger = auslastung.kapazitaet(mo, 8, 0, 1.0, "NW", gesperrt)
assert abs(voll - weniger - 24) < 1e-6, (voll, weniger)
assert "Sperrtag 10.11., 12.11., 13.11." in auslastung.gesperrt_text(set(), gesperrt, mo)
d = terminplan.arbeitstage_spaeter(datetime.date(2026, 11, 9), 2, "NW", gesperrt)
assert d == datetime.date(2026, 11, 16), d
assert terminplan.arbeitstage_zwischen(datetime.date(2026, 11, 9), datetime.date(2026, 11, 16), "NW", gesperrt) == 2
ok("F7 Sperrtage: Kapazität ohne gesperrte Tage, Terminplan rechnet sie heraus")

# ------------------------------------------------------------------ F2 Fassungsvergleich
db.staffelpreise_speichern(a, dict(zeilen=[dict(schluessel="10", einheit="Stk", menge=400, preis_einheit=4.2),
                                           dict(schluessel="20", einheit="Stk", menge=100, preis_einheit=7.9)],
                                   kennung="x", am="2026-10-20"))
db.vorgang_setzen(a, "Verschickt")
a2 = db.angebot_fassung(a)
assert fassung_vergleich.vorgaenger(db, a2) == a and fassung_vergleich.vorgaenger(db, a) is None
pos2 = db.positionen(a2)
db.position_aendern(next(p["id"] for p in pos2 if p["pos"] == 10), "stueck", 600)
db.positionen_loeschen([next(p["id"] for p in pos2 if p["pos"] == 20)])
db.position_neu(a2, dict(pos=30, artikel="AB-30", bezeichnung="Lasche", profil_id="RE 60x40x3",
                         werkstoff_id="S235-10219", laenge=120.0, stueck=50, schneidweg=200))
v = fassung_vergleich.vergleich(db, a, a2)
arten = {z["artikel"]: z["art"] for z in v["zeilen"]}
assert arten == {"AB-10": "geändert", "AB-20": "entfällt", "AB-30": "neu"}, arten
assert any("Menge 400 → 600" in t for z in v["zeilen"] for t in z["aenderungen"])
h = fassung_vergleich.html(v, nur_aenderungen=True)
assert "AB-30" in h and v["neu"].endswith("-2")
ok("F2 Fassungsvergleich: neu, entfällt, geändert mit Menge alt → neu")

# ------------------------------------------------------------------ F3 Teilekatalog
kat = teilekatalog.katalog(db, "K-1001")
art = {r["artikel"]: r for r in kat}
assert set(art) == {"AB-10", "AB-30"}, art            # AB-20 nur in der abgelösten Fassung
assert art["AB-10"]["nummer"].endswith("-2")
assert teilekatalog.katalog(db, "") == []
csv_t = teilekatalog.csv_text(kat)
assert csv_t.startswith("Artikel;Bezeichnung") and "AB-30" in csv_t
alt_kat = teilekatalog.nach_angebot(kat)
assert set(alt_kat) == {a2}
ok("F3 Teilekatalog: ein Eintrag je Artikel, ohne abgelöste Fassung, CSV")

# ------------------------------------------------------------------ Preisschicht G2 G3 G6 G7 J1 J2 J3 J6
a3 = db.angebot_neu(dict(nummer="A-2026-0301", kundennr="K-1001", datum="2026-11-02", maschine="T11", stange=6000))
for n in (10, 20):
    q = next(p for p in pos if p["pos"] == n)
    db.position_neu(a3, {f: q[f] for f in ("pos", "artikel", "bezeichnung", "profil_id", "werkstoff_id", "laenge",
                                           "stueck", "schneidweg", "einstiche")})
k3, p3 = db.angebot(a3), db.positionen(a3)
e3 = rechnen.einstellungen_angebot(k3, db.einstellungen())
erg3 = rechnen.optimieren(k3, p3, k, tab, e3)


def kalk(kopf=None, **einst_):
    return rechnen.kalkulation(dict(k3, **(kopf or {})), p3, erg3, k, tab, dict(e3, **einst_))


z0, s0 = kalk()
assert all(s0[n] == 0 for n in preisschicht.FELDER)
assert 0 < s0["untergrenze_kurz"] < s0["untergrenze_lang"] <= s0["verkauf"], s0["untergrenze_lang"]
z, s = kalk(runden_stueck=0.05)
assert all(abs(x["preis_teil"] / 0.05 - round(x["preis_teil"] / 0.05)) < 1e-6 for x in z if x)
assert s["verkauf"] >= s0["verkauf"] and s["rundung"] > 0
z, s = kalk(runden_gesamt=10.0)
assert abs(s["verkauf"] / 10 - round(s["verkauf"] / 10)) < 1e-6 and s["verkauf"] >= s0["verkauf"]
z, s = kalk(dict(rabatt=10.0), rabatt=0.10)
assert abs(s["verkauf"] - 0.9 * s0["verkauf"]) < 0.01 and s["rabatt"] < 0
z, s = kalk(dict(zahlungsziel=30), finanz_zins=0.06, termin_material_tage=3)
assert abs(s["finanzierung"] - s0["selbst"] * 0.06 * 33 / 360) < 0.01, (s["finanzierung"], s0["selbst"])
assert abs(s["verkauf"] - s0["verkauf"] - s["finanzierung"] - (s["skonto"] - s0["skonto"])) < 0.01
z, s = kalk(dict(neuteile=json.dumps([p3[0]["id"]])), neuteil_zuschlag=0.05)
erw = (z0[0]["material_teil"] + z0[0]["laser_teil"]) * 0.05 * z0[0]["stueck"]
assert abs(s["neuteil"] - erw) < 0.01 and z[1]["neuteil_teil"] == 0
tab_v = dict(tab, verpackung=[dict(name="Europalette", preis=18.0, max_kg=2000, max_laenge=1200, aktiv="ja"),
                              dict(name="Karton L", preis=4.5, max_kg=25, max_laenge=600, aktiv="ja")])
z, s = rechnen.kalkulation(k3, p3, erg3, k, tab_v, e3)
assert s["verpackung"] == 18.0 and "Europalette" in s["verpackung_text"], s.get("verpackung_text")
z, s = rechnen.kalkulation(dict(k3, verpackung="nein"), p3, erg3, k, tab_v, e3)
assert s["verpackung"] == 0
assert preisschicht.packmittel(tab_v["verpackung"], 30, 500)[0]["name"] == "Karton L"
m = k.maschinen["T11"]
alt_m = dict(m)
m.update(mannlos_ab=0.01, mannlos_satz=_satz - 50 if (_satz := rechnen._n(m.get("stundensatz"))) > 50 else 0)
z, s = kalk()
assert s["mannlos"] < 0 and s["verkauf"] < s0["verkauf"], s["mannlos"]
m.clear()
m.update(alt_m)
k_mw = dict(k3, mindestwert=s0["verkauf"] * 3)
z, s = rechnen.kalkulation(k_mw, p3, erg3, k, tab, rechnen.einstellungen_angebot(k_mw, db.einstellungen()))
assert s["mindestpreis_gilt"] and s["verkauf"] > 2.5 * s0["verkauf"]
ok("Preisschicht: Runden, Rabatt, Finanzierung, Neuteil, Verpackung, mannlos, Mindestwert, "
   "Untergrenze")

# ------------------------------------------------------------------ G1 Zielpreis, G4, G5, J1, J5 (Rechenhilfen)
g = kalk_hinweise.gewinn_fuer_ziel(lambda x: 100 * (1 + x), 130)
assert abs(g - 0.30) < 1e-4, g
assert kalk_hinweise.gewinn_fuer_ziel(lambda x: 100 * (1 + x), 40) is None
assert kalk_hinweise.menge_fuer_ziel(lambda n: 10 + 1000 / n, 100, 15) == 200
assert "ohne Gewinn" in kalk_hinweise.ziel_text(40, 0.2, None)
pk = kalk_hinweise.untergrenze_punkte(dict(verkauf=100, skonto=0, untergrenze_kurz=60, untergrenze_lang=110), ziel=50)
assert len(pk) == 2 and "langfristigen" in pk[0][1] and "kurzfristigen" in pk[1][1], pk
assert kalk_hinweise.auslastung_punkt(0.95, "KW 46")[1].startswith("Die Maschine ist in KW 46 zu 95 %")
assert "Spielraum" in kalk_hinweise.auslastung_punkt(0.3, "KW 46")[1]
assert kalk_hinweise.auslastung_punkt(0.7, "KW 46") is None
assert kalk_hinweise.losgroesse(5000, 200, 5, 0.08) == 2236
assert kalk_hinweise.losgroesse(0, 200, 5, 0.08) is None
ok("G1/G4/J1/J5: Zielpreis rückwärts, Menge für Stück-Ziel, Untergrenze, Auslastung, Andler-Losgröße")

# ------------------------------------------------------------------ H2 Vier-Augen-Freigabe
sm = dict(verkauf=30000, gewinn=3000, selbst=27000)
assert freigabe.noetig(sm, dict(freigabe_ab=25000)).startswith("Netto")
assert freigabe.noetig(sm, dict(freigabe_marge=0.15)).startswith("Marge")
assert freigabe.noetig(sm, {}) is None
e = freigabe.eintrag("PB", sm, "Netto")
assert freigabe.gueltig(e, sm) and freigabe.gueltig(e, dict(verkauf=30100))
assert not freigabe.gueltig(e, dict(verkauf=30300)) and not freigabe.gueltig(None, sm)
assert "Freigegeben von PB" in freigabe.text(e)
ok("H2 Vier-Augen-Freigabe: ab Netto, unter Marge, gilt bis 0,5 % Preisänderung")

# ------------------------------------------------------------------ H5 Rückfrage
pkt = rueckfrage.punkte([("FEHLER", "Werkstoff fehlt", None), ("HINWEIS", "egal", None),
                         ("WARNUNG", "Werkstoff fehlt", None)], [dict(pos=10, artikel="AB-10")],
                        [dict(hinweis="Zeichnung fehlt")])
assert pkt == ["Werkstoff fehlt", "Pos. 10 AB-10: Zeichnung fehlt"], pkt
t = rueckfrage.text(dict(nummer="X"), dict(ansprechpartner="Frau Muster"), pkt, "Patrick")
assert "Guten Tag Frau Muster" in t and "2. Pos. 10" in t
assert rueckfrage.wiedervorlage(datetime.date(2026, 11, 2)) == datetime.date(2026, 11, 5)
ok("H5 Rückfrage: Fehler/Warnungen und Positionshinweise ohne Doppelte, Mail-Text, Wiedervorlage +3 Tage")

# ------------------------------------------------------------------ H6 Positionsvorlagen
p_v = db.positionen(a3)[0]
vid = positionsvorlagen.speichern(db, p_v, "Strebe Standard")
assert positionsvorlagen.speichern(db, p_v, "Strebe Standard") == vid
w = positionsvorlagen.werte(db.zeilen("positionsvorlagen")[0])
assert w["profil_id"] == "RE 60x40x3" and "stueck" not in w and "pos" not in w
assert positionsvorlagen.werte(dict(daten="kaputt")) is None
try:
    positionsvorlagen.speichern(db, p_v, " ")
    raise AssertionError("leerer Name")
except ValueError:
    pass
ok("H6 Positionsvorlagen: ohne Stückzahl/Pos., gleicher Name ersetzt, beschädigte Vorlage = None")

# ------------------------------------------------------------------ F6 Lieferschein, F5 Werkszeugnisse
db.vorgang_setzen(a3, "Beauftragt")
st = lieferschein.stand(db.positionen(a3), lieferschein.scheine(db, a3))
assert [z["offen"] for z in st] == [400, 100]
heute = datetime.date(2026, 11, 2)
s1 = lieferschein.anlegen(db, a3, {st[0]["pid"]: 300}, heute)
assert s1["nummer"] == "LS-2026-00001"
st = lieferschein.stand(db.positionen(a3), lieferschein.scheine(db, a3))
assert st[0]["offen"] == 100 and lieferschein.offen_text(st) == "geliefert 300/500 Stk"
try:
    lieferschein.anlegen(db, a3, {st[0]["pid"]: 150}, heute)
    raise AssertionError("mehr als offen")
except ValueError:
    pass
assert lieferschein.naechste_nummer(db, datetime.date(2027, 1, 2)) == "LS-2027-00001"
s2 = lieferschein.anlegen(db, a3, {z["pid"]: z["offen"] for z in st}, heute)
assert s2["nummer"] == "LS-2026-00002"
assert lieferschein.offen_text(lieferschein.stand(db.positionen(a3), lieferschein.scheine(db, a3))) == \
    "komplett geliefert"
lieferschein.pdf(tmp / "ls.pdf", db.angebot(a3), s1, db.einstellungen(), ["Beispiel GmbH", "Hauptstr. 1"], st)
assert (tmp / "ls.pdf").stat().st_size > 1000
db.einstellung_setzen("lager_aktiv", "ja")
ids = lager.zugang(db, "Stange", "RE 60x40x3", "S235-10219", 6000, 5, charge="C-77")
with db.con:
    db.con.execute("INSERT INTO lager_reservierung (bestand_id, angebot_id, anzahl, status) VALUES (?, ?, 2, "
                   "'reserviert')", (ids[0], a3))
zi = lieferschein.zeugnisse_sammeln(db, a3)
assert not zi["vorhanden"] and "C-77" in zi["fehlt"][0], zi
(tmp / "zeugnis.pdf").write_bytes(b"%PDF-1.4 Zeugnis")
lager.zeugnis_setzen(db, ids[0], str(tmp / "zeugnis.pdf"))
zi = lieferschein.zeugnisse_sammeln(db, a3, tmp / "Werkszeugnisse")
assert zi["vorhanden"] and not zi["fehlt"] and (tmp / "Werkszeugnisse" / "zeugnis.pdf").is_file()
assert lager.bestand(db)[0]["zeugnis"]
ok("F5/F6 Lieferschein: Teillieferung, Nummernkreis je Jahr, PDF, Werkszeugnis der Charge gesammelt/fehlt")

# ------------------------------------------------------------------ F4 Lieferantenangebote, H7 Bewertung
a4 = db.angebot_neu(dict(nummer="A-2026-0302", kundennr="K-1001", datum="2026-11-01", maschine="T11", stange=6000))
for q in p3:
    db.position_neu(a4, {f: q[f] for f in ("pos", "artikel", "bezeichnung", "profil_id", "werkstoff_id", "laenge",
                                           "stueck", "schneidweg", "einstiche")})
db.ergebnis_speichern(a4, erg3)
db.preisbasis_speichern(a4, rechnen.preisbasis_aus(db.angebot(a4), db.positionen(a4), k, tab))
db.vorgang_setzen(a4, "Verschickt")
i1 = lieferantenangebote.erfassen(db, a3, "Stahl Nord", "RE 60x40x3", "S235-10219", "€/m", 5.20, 5, heute=heute)
i2 = lieferantenangebote.erfassen(db, a3, "Stahl Süd", "RE 60x40x3", "S235-10219", "€/Stange", 30.0, 10, laenge=6000,
                                  heute=heute)
vg = lieferantenangebote.vergleich(lieferantenangebote.liste(db, a3), k)
assert vg[0]["antwort"]["lieferant"] == "Stahl Süd" and vg[0]["bester"] and abs(vg[0]["je_m"] - 5.0) < 1e-9
try:
    lieferantenangebote.erfassen(db, a3, "", "RE 60x40x3", "S235-10219", "€/m", 1)
    raise AssertionError("ohne Lieferant")
except ValueError:
    pass
pid_preis = lieferantenangebote.uebernehmen(db, a3, i2, heute)
zp = next(z for z in db.zeilen("preise") if z["id"] == pid_preis)
assert zp["preis"] == 30.0 and zp["basis"] == "€/Stange" and zp["lieferant"] == "Stahl Süd"
lieferantenangebote.eingang_setzen(db, a3, i2, datetime.date(2026, 11, 20))
lieferantenangebote.eingang_setzen(db, a3, i1, datetime.date(2026, 11, 5))
bw = {b["lieferant"]: b for b in lieferantenangebote.bewertung(db, k)}
assert bw["Stahl Süd"]["rang"] == 1 and bw["Stahl Süd"]["termintreue"] == 0.0
assert bw["Stahl Nord"]["termintreue"] == 1.0
assert "Preisrang Ø 1" in lieferantenangebote.bewertung_text(bw["Stahl Süd"])
ok("F4/H7 Lieferantenangebote: €/m-Vergleich, Übernehmen in Preise, Wareneingang, Rang und Termintreue")

# ------------------------------------------------------------------ H4 Laserzeit per Scan
pa3 = db.positionen(a3)[0]
code3 = etiketten.code(db.angebot(a3)["nummer"], pa3["pos"])
assert etiketten.LASER_START in etiketten.scan_schritte(db)
r = etiketten.rueckmelden(db, code3, etiketten.LASER_START, wer="PB")
assert r["menge"] == 0 and "Laser Start" in r["text"]
with db.con:
    db.con.execute("DELETE FROM rueckmeldungen WHERE angebot_id=?", (a3,))
    for schritt, am in ((etiketten.LASER_START, "2026-11-02T07:00:00"), (etiketten.LASER_ENDE, "2026-11-02T09:30:00"),
                        (etiketten.LASER_START, "2026-11-03T07:00:00"), (etiketten.LASER_ENDE, "2026-11-03T08:00:00"),
                        (etiketten.LASER_START, "2026-11-03T10:00:00")):
        db.con.execute("INSERT INTO rueckmeldungen (angebot_id, position_id, pos, schritt, menge, am) VALUES "
                       "(?, ?, '10', ?, 0, ?)", (a3, pa3["id"], schritt, am))
lz = etiketten.laserzeit(db, a3)
assert abs(lz["stunden"] - 3.5) < 1e-9 and lz["laeufe"] == 2 and lz["offen"], lz
assert etiketten.laserzeit(db, a) is None
assert etiketten.stand_je_position(db, a3)[0]["schritte"].get("Geschnitten", 0) == 0
ok("H4 Laserzeit per Scan: Start bis Ende summiert (3,5 h aus 2 Läufen), offener Start gemeldet, zählt keine Menge")

# ------------------------------------------------------------------ H1 Sammel-Preisprüfung, H3 Monatsbericht
liste_p = sammel_preis.pruefen(db, heute=datetime.date(2026, 11, 3))
assert [r["id"] for r in liste_p] == [a4], liste_p      # nur verschickt + festgeschrieben, beauftragt zählt nicht
assert abs(liste_p[0]["abweichung"]) > 0.01, liste_p    # Preis aus dem Lieferantenangebot übernommen
assert sammel_preis.pruefen(db, heute=datetime.date(2027, 3, 1)) == []                 # abgelaufen
mb = monatsbericht.bericht(db, 2026, 11)
assert mb["titel"] == "November 2026" and mb["beauftragt"] >= 1 and mb["trefferquote"] == 1.0, mb
monatsbericht.pdf(tmp / "monat.pdf", mb, db.einstellungen())
assert (tmp / "monat.pdf").stat().st_size > 1000
ok(f"H1/H3: Sammel-Preisprüfung ({len(liste_p)} offen), Monatsbericht {mb['titel']} als PDF")

# ------------------------------------------------------------------ Oberfläche
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.fenster import Hauptfenster  # noqa: E402

hf = Hauptfenster(db, stumm=True)
s = hf.angebot_oeffnen(a2)
assert not s.kopf_bereich.maschinen_knopf.isHidden()
mv = s.maschinen_vergleichen(waehlen="LT7")
assert s.kopf["maschine"] == "LT7", s.kopf["maschine"]
s.maschinen_vergleichen(waehlen="T11")
assert s.kopf["maschine"] == "T11"
assert s._vorige_fassung() == a
fv = s.fassung_vergleichen(zeigen=False)
assert {z["art"] for z in fv["zeilen"]} == {"neu", "entfällt", "geändert"}
d = hf.kunden.teilekatalog("K-1001", zeigen=False)
assert d.tabelle.rowCount() == 3
neu = hf.kunden.katalog_angebot("K-1001", d.liste)
assert neu and {p["artikel"] for p in db.positionen(neu)} == {"AB-10", "AB-20", "AB-30"}
assert db.angebot(neu)["kundennr"] == "K-1001"
ok("Oberfläche F: Maschinen vergleichen und nehmen, Fassungsvergleich, Teilekatalog → neues Angebot")
# ------------------------------------------------------------------ Oberfläche G, H, J
s3 = hf.angebot_oeffnen(a3)
assert s3.lieferschein() is None or True          # alles geliefert -> Meldung, kein Absturz
d_la = s3.lieferantenangebote(zeigen=False)
assert d_la.tabelle.rowCount() == 2 and len(d_la.vergleich) == 2
assert s3._antwort_erfassen(dict(lieferant="Stahl West", profil_id="RE 60x40x3", werkstoff_id="S235-10219",
                                 basis="€/kg", preis=1.1)) == 2
eml = tmp / "rueckfrage.eml"
rf = s3.rueckfrage(eml=eml, punkte=["Bitte Werkstoff bestätigen"])
assert rf and eml.is_file() and "Werkstoff bestätigen" in eml.read_text(encoding="utf-8", errors="replace")
assert any(v.get("art") == "rueckfrage" for v in db.angebot(a3)["versand"])
sv = hf.angebot_oeffnen(a2)
assert sv.als_vorlage_speichern(0, "Vorlage GUI")
vor = next(v for v in db.zeilen("positionsvorlagen") if v["name"] == "Vorlage GUI")
n_alt = len(sv.positionen)
assert sv.position_aus_vorlage(vor["id"]) and len(sv.positionen) == n_alt + 1
db.einstellung_setzen("freigabe_ab", 1.0)
sv.einst = rechnen.einstellungen_angebot(sv.kopf, db.einstellungen())
assert sv.freigabe_offen()
from rohrlaser import admin_schutz  # noqa: E402
admin_schutz.SITZUNG = admin_schutz.Sitzung()
if admin_schutz.aktiv(db):
    assert sv.freigeben() is None                  # ohne Admin keine Freigabe
    admin_schutz.SITZUNG.freischalten()
assert sv.freigeben() and not sv.freigabe_offen()
db.einstellung_setzen("freigabe_ab", 0)
erg_z = sv.zielpreis(ziel=round(sv._verkauf() * 1.1, 2), setzen=False)
assert erg_z and erg_z["gewinn"] is not None and erg_z["gewinn"] > rechnen._n(sv.einst.get("gewinn"))
sv.positionen = db.positionen(sv.id)
assert isinstance(sv._kalk_punkte(sv._rechnung()[1]), list)
nk3 = s3._nachkalk
if nk3 is not None:
    nk3.neu_laden()
    assert nk3.scan and nk3.scan_uebernehmen() and abs(nk3.ist["laser_h"] - 3.5) < 1e-9
d_op = hf.offene_pruefen(zeigen=False)
assert d_op.tabelle.rowCount() == len(d_op.liste)
assert hf.monatsbericht(2026, 11, str(tmp / "monat2.pdf")) and (tmp / "monat2.pdf").is_file()
ok("Oberfläche G/H/J: Lieferantenangebote, Rückfrage (E-Mail-Datei), Vorlagen, Freigabe, Zielpreis, Scan-Zeit, "
   "Offene Angebote, Monatsbericht")
print("Alle Prüfungen bestanden.")
