"""Prüft die Einlastung der Maschinen und die Seite Auslastung (Plan Maschinenauslastung, Patrick 10.11.2026):

- E1 Tagesstunden wie die Wochenkapazität (Feiertag, Betriebsruhe, Sperrtag, Samstag); Summe der Tage = Woche
- E2 Einlastung nach Liefertermin: Überlast rutscht in die Folgewoche, Summe eingelastet = Summe Bedarf, kein Tag
  über seiner Kapazität; Fertig-Datum, lieferbar = fertig + Vorlauf, Puffer, Terminrisiko ok / knapp / überschritten /
  ohne Termin; verschickte Angebote erst nach allen Aufträgen
- E3 gemessene Laserstunden aus den Scans „Laser Start/Ende“ je Maschine und Woche
- E4 Was-wäre-wenn: andere Maschine, Zusatzstunden, Samstag ändern nur die Rechnung, nicht die Daten
- E5 Seite: Wochenbalken, Plantafel, Details je Woche, Terminrisiko-Liste, Sicht Terminwoche, PDF, Reiter Fertigung,
  Kachel der Startseite, Satz in „Termin prüfen“, Merker rechnet nur Geändertes neu

Aufruf: python tests/test_einlastung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import auslastung, auslastung_ansicht, einlastung, etiketten  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


def nah(a, b, tol=1e-6):
    return abs(a - b) <= tol


D = datetime.date
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
heute = D(2026, 11, 4)                      # Mittwoch KW 45
kw45, kw46, kw47 = D(2026, 11, 2), D(2026, 11, 9), D(2026, 11, 16)
db.einstellung_setzen("schicht_stunden", 8.0)
db.einstellung_setzen("schicht_verfuegbar", 0.5)       # 4 h je Tag nutzbar
db.einstellung_setzen("betriebsruhe", "12.11.2026")
with db.con:
    db.con.execute("UPDATE maschinen SET sperrtage='13.11.2026' WHERE maschinen_id='T11'")

# ---- E1 ----
aus = auslastung.berechnen(db, heute, 4)
assert einlastung.tagesstunden(aus, "T03", D(2026, 11, 4)) == 4
assert einlastung.tagesstunden(aus, "T03", D(2026, 11, 7)) == 0 and einlastung.tagesstunden(aus, "T03", D(2026, 11, 8)) == 0
assert einlastung.tagesstunden(aus, "T03", D(2026, 11, 12)) == 0, "Betriebsruhe"
assert einlastung.tagesstunden(aus, "T11", D(2026, 11, 13)) == 0 and einlastung.tagesstunden(aus, "T03", D(2026, 11, 13)) == 4
assert einlastung.tagesstunden(aus, "T03", D(2026, 12, 25)) == 0, "Feiertag"
for m in ("T03", "T11"):
    for mo in (kw46, kw47):
        assert nah(sum(einlastung.tagesstunden(aus, m, mo + datetime.timedelta(days=i)) for i in range(7)),
                   aus["kapazitaet"][(m, mo)]), (m, mo)
s = einlastung.Szenario()
s.samstag = 6.0
assert einlastung.tagesstunden(aus, "T03", D(2026, 11, 7), s) == 3
ok("E1 Tagesstunden = Wochenkapazität, Feiertag, Betriebsruhe, Sperrtag, Samstag im Szenario")


def kuenstlich(auftraege, wochen=4):
    """Auslastung mit vorgegebenen Laserstunden (ohne Kalkulation): [(id, Maschine, h, Termin, Art)]."""
    a = auslastung.berechnen(db, heute, wochen)
    a["auftraege"], a["bedarf"] = {}, {}
    for i, m, h, termin, art in auftraege:
        bis = auslastung._termin(dict(liefertermin=termin.isoformat()), a["vorlauf"], a["land"]) if termin else None
        sp = (auslastung.OHNE if bis is None else auslastung.UEBERFAELLIG if bis < kw45 else
              auslastung.montag(bis) if auslastung.montag(bis) in [x for _, _, x in a["spalten"]] else auslastung.SPAETER)
        a["auftraege"].setdefault((m, sp), []).append(dict(
            id=i, nummer=f"A{i:02d}", kunde="K", h=h, termin=termin.isoformat() if termin else None, art=art,
            gewicht=1.0, geschnitten=0.0, maschine=m, bis=bis))
        a["bedarf"][(m, sp)] = a["bedarf"].get((m, sp), 0.0) + h
    return a


# ---- E2 ----  T03: 4 h je Tag; KW 45 ab Mi = 12 h, KW 46 = 16 h (Do Ruhe), KW 47 = 20 h
aus = kuenstlich([(1, "T03", 10.0, D(2026, 11, 13), "Auftrag"),      # Mi-Fr (4+4+2)            -> fertig Fr 06.11.
                  (2, "T03", 12.0, D(2026, 11, 11), "Auftrag"),      # früherer Termin: zuerst  -> siehe unten
                  (3, "T03", 6.0, None, "Auftrag"),                  # ohne Termin: nach den Terminen
                  (4, "T03", 4.0, D(2026, 11, 6), "Angebot"),        # Angebot: nach allen Aufträgen
                  (5, "T11", 3.0, D(2026, 11, 30), "Auftrag")])
ein = einlastung.rechnen(aus)
a = {x["id"]: x for x in ein["auftraege"]}
# Reihenfolge T03: 2 (Termin 11.11.), 1 (13.11.), 3 (ohne), 4 (Angebot)
assert a[2]["start"] == heute and a[2]["fertig"] == D(2026, 11, 6), a[2]            # 12 h = Mi, Do, Fr
assert a[2]["lieferbar"] == D(2026, 11, 10) and a[2]["puffer"] == 1 and a[2]["risiko"] == einlastung.KNAPP, a[2]
assert a[1]["start"] == D(2026, 11, 9) and a[1]["fertig"] == D(2026, 11, 11), a[1]  # 10 h = Mo, Di, Mi(2)
assert a[1]["lieferbar"] == D(2026, 11, 16), a[1]["lieferbar"]                      # +2 AT: Fr 13., Mo 16. (Do Ruhe)
assert a[1]["risiko"] == einlastung.UEBER and a[1]["puffer"] == -1, a[1]
assert a[3]["risiko"] == einlastung.OHNE and a[3]["start"] == D(2026, 11, 11) and a[3]["fertig"] == D(2026, 11, 13)
assert a[4]["start"] == D(2026, 11, 16) and a[4]["art"] == "Angebot", a[4]
assert a[5]["risiko"] == einlastung.OK and a[5]["fertig"] == heute and a[5]["puffer"] >= 2
assert ein["risiko"] == {einlastung.OK: 1, einlastung.KNAPP: 1, einlastung.UEBER: 1, einlastung.OHNE: 1}, ein["risiko"]
w45, w46, w47 = (einlastung.wochenwerte(aus, ein, "T03", mo) for mo in (kw45, kw46, kw47))
assert nah(w45[0], 12) and nah(w45[2], 12) and nah(w46[0], 16) and nah(w46[2], 16), (w45, w46)   # voll, Rest rutscht
assert nah(w47[0], 0) and nah(w47[1], 4) and nah(w47[2], 20), w47
assert nah(sum(sum(v.values()) for (m, _), v in ein["woche"].items() if m == "T03"), 10 + 12 + 6 + 4)
for (m, tag), v in ein["belegt"].items():
    assert sum(v.values()) <= ein["kapazitaet"][(m, tag)] + 1e-9, (m, tag)
assert [x["id"] for x in einlastung.kritische(ein)] == [1, 2]
# Terminwochen-Sicht bleibt: alles in der Woche Termin minus Vorlauf (A1: 13.11. - 2 AT = Di 10.11., Do Ruhe zählt
# dort als Arbeitstag der bisherigen Rechnung)
assert einlastung.terminwerte(aus, "T03", kw46)[0] == 22.0
assert nah(einlastung.frei_bis(aus, ein, "T11", D(2026, 11, 6)), 12 - 3)
# passt nicht in den Horizont
ein2 = einlastung.rechnen(kuenstlich([(9, "T03", 50.0, D(2026, 11, 13), "Auftrag")]), horizont=10)
assert ein2["spaeter"]["T03"] > 0 and ein2["auftraege"][0]["risiko"] == einlastung.UEBER
ok("E2 Einlastung: Reihenfolge, Überlauf in die Folgewoche, Fertig-Datum, Puffer, Terminrisiko, Summen")


# ---- echte Aufträge ----
def auftrag(termin, stueck=100, maschine="T03", vorgang="Beauftragt"):
    a = db.angebot_neu(dict(kunde="Kunde", skonto=0, stange=6000, maschine=maschine, datum=heute.isoformat()))
    db.position_neu(a, dict(pos=10, artikel="T", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                            stueck=stueck, schneidweg=300, einstiche=2))
    seite = f.angebot_oeffnen(a)
    seite.optimieren()
    seite.neu_laden()
    f.angebot_schliessen(a)
    db.vorgang_setzen(a, vorgang)
    if vorgang == "Beauftragt":
        db.auftrag_setzen(a, "B", termin.isoformat() if termin else None)
    return a


a1 = auftrag(D(2026, 11, 13), 3000)
a2 = auftrag(D(2026, 11, 6), 3000)
a3 = auftrag(None, 500, "LT7")
a4 = auftrag(D(2026, 11, 20), 2000, vorgang="Verschickt")

# ---- E3 ----
with db.con:
    for aid, schritt, am in ((a1, etiketten.LASER_START, "2026-10-27T06:00:00"), (a1, etiketten.LASER_ENDE, "2026-10-27T09:30:00"),
                             (a1, etiketten.LASER_START, "2026-10-28T06:00:00"), (a1, etiketten.LASER_ENDE, "2026-10-28T07:00:00"),
                             (a3, etiketten.LASER_START, "2026-10-20T10:00:00"), (a3, etiketten.LASER_ENDE, "2026-10-20T12:00:00"),
                             (a3, etiketten.LASER_START, "2026-11-03T10:00:00"),          # offen: zählt nicht
                             (a2, etiketten.LASER_START, "2026-09-01T10:00:00"), (a2, etiketten.LASER_ENDE, "2026-09-01T12:00:00")):
        db.con.execute("INSERT INTO rueckmeldungen (angebot_id, schritt, menge, am) VALUES (?, ?, 0, ?)", (aid, schritt, am))
aus = auslastung.berechnen(db, heute, 8, offene=True)
gem = einlastung.gemessen(db, heute, 4, aus)
assert gem["montage"] == [D(2026, 10, 5), D(2026, 10, 12), D(2026, 10, 19), D(2026, 10, 26)], gem["montage"]
assert nah(gem["stunden"][("T03", D(2026, 10, 26))], 4.5) and nah(gem["stunden"][("LT7", D(2026, 10, 19))], 2.0)
assert gem["laeufe"] == 3 and len(gem["stunden"]) == 2, gem
assert nah(gem["kapazitaet"][("T03", D(2026, 10, 26))], 20)
ok("E3 gemessene Laserstunden je Maschine und Woche aus den Scans, offener Lauf und alte Läufe zählen nicht")

# ---- E4 ----
ein = einlastung.rechnen(aus)
vorher = {x["id"]: (x["maschine"], x["fertig"]) for x in ein["auftraege"]}
h_t11 = einlastung.andere_maschine(db, a1, "T11")
assert h_t11 and h_t11 > 0
s = einlastung.Szenario()
assert s.leer() and einlastung.rechnen(aus, s)["szenario"] is None
s.maschine[a1] = ("T11", h_t11)
s.zusatz[("T03", kw45)] = 9.0
e2 = einlastung.rechnen(aus, s)
n = {x["id"]: x for x in e2["auftraege"]}
assert n[a1]["maschine"] == "T11" and n[a1]["ursprung"] == "T03" and nah(n[a1]["h"], h_t11)
assert nah(e2["wochen_kap"][("T03", kw45)], ein["wochen_kap"][("T03", kw45)] + 9.0)
assert n[a2]["fertig"] <= vorher[a2][1] and "T11" in s.text() or "Maschine" in s.text()
assert {x["id"]: (x["maschine"], x["fertig"]) for x in einlastung.rechnen(aus)["auftraege"]} == vorher, "Daten unverändert"
assert db.angebot(a1)["maschine"] == "T03"
ok("E4 Was-wäre-wenn: andere Maschine mit deren Laserzeit, Zusatzstunden; nichts wird gespeichert")

# ---- E5 ----
v = auslastung_ansicht.AuslastungAnsicht(f, heute)
v.resize(1300, 780)
v.offene.setChecked(True)
assert v.daten is not None and v.geladen
v.show()
app.processEvents()
zeilen = v.balken.zeilen
assert [z["maschine"] for z in zeilen] == v.ein["maschinen"]
t03 = next(z for z in zeilen if z["maschine"] == "T03")
arten = [sp["art"] for sp in t03["spalten"]]
assert arten == ["ist"] * 4 + ["woche"] * 8 + ["rest"], arten
assert nah(t03["spalten"][3]["ist"], 4.5) and "gemessen" in v.balken.tipp(t03, t03["spalten"][3])
w = t03["spalten"][4]
assert w["key"] == kw45 and nah(w["kap"], 12) and nah(w["auftrag"], 12), w             # volle Woche, Rest rutscht
assert "Terminrisiko" in v.info.text() and "Verschickte Angebote zählen mit" in v.info.text()
assert v.details.rowCount() == len(einlastung.kritische(v.ein)) >= 1                    # ohne Auswahl: Terminrisiko
v._woche_gewaehlt("T03", kw46)
nummern = {v.details.item(i, 0).text() for i in range(v.details.rowCount())}
assert db.angebot(a1)["nummer"] in nummern and "KW 46" in v.details_titel.text(), (nummern, v.details_titel.text())
assert v.details.horizontalHeaderItem(9).text() == "Terminrisiko"
v.sicht.setCurrentIndex(1)                                                             # Terminwoche
t03 = next(z for z in v.balken.zeilen if z["maschine"] == "T03")
assert [sp["key"] for sp in t03["spalten"] if sp["art"] == "rest"] == [auslastung.UEBERFAELLIG, auslastung.SPAETER,
                                                                         auslastung.OHNE]
kw46_spalte = next(sp for sp in t03["spalten"] if sp["key"] == kw46)
assert nah(kw46_spalte["auftrag"], v.daten["bedarf"][("T03", kw46)] - einlastung.terminwerte(v.daten, "T03", kw46)[1])
assert "Bedarf / Kapazität" in v.info.text()
v.sicht.setCurrentIndex(0)
# Plantafel: Flächen nach dem Zeichnen, Auswahl, Doppelklick öffnet
v.grab()
assert v.tafel.flaechen and {x["id"] for _, x in v.tafel.flaechen} >= {a1, a2}
assert "Terminrisiko" in v.tafel.tipp(next(x for _, x in v.tafel.flaechen if x["id"] == a2))
v.tafel.gewaehlt.emit(a1)
assert v.auftrag == a1
v.zoom.setCurrentIndex(1)
assert v.tafel.minimumWidth() > 1000
v.zoom.setCurrentIndex(0)
assert v.tafel.minimumWidth() == 0
# Was-wäre-wenn in der Seite
assert v.ww_verlegen(a1, "T11") and not v.ww_banner.isHidden() and "nichts wird gespeichert" in v.ww_banner.text()
assert next(x for x in v.ein["auftraege"] if x["id"] == a1)["maschine"] == "T11"
v._woche_gewaehlt("T03", kw45)
assert v.ww_zusatz(stunden=5.0) and ("T03", kw45) in v.szenario.zusatz
v.ww_samstag.setChecked(True)
assert v.szenario.samstag == 6.0
v.ww_leeren()
assert v.szenario.leer() and v.ww_banner.isHidden() and db.angebot(a1)["maschine"] == "T03"
v._woche_gewaehlt(None, None)
assert not v.ww_zusatz() and "Balken einer Woche" in v.ww_banner.text()
v.ww_leeren()
pfad = v.pdf(tmp / "auslastung.pdf")
assert Path(pfad).read_bytes()[:4] == b"%PDF" and Path(pfad).stat().st_size > 3000
ok("E5a Seite: Wochenbalken mit gemessenen Wochen, Details, Terminwoche, Plantafel, Was-wäre-wenn, PDF")

# Merker: zweites Laden rechnet kein Angebot neu, nach einer Änderung nur dieses
zaehler = []
echt = auslastung.maschinenzeit
auslastung.maschinenzeit = lambda *a, **k: (zaehler.append(a[1]["id"]), echt(*a, **k))[1]
v.laden()
assert zaehler == [], zaehler
db.angebot_aendern(a2, "bemerkung", "x")
v.laden()
assert set(zaehler) <= {a2}, zaehler
auslastung.maschinenzeit = echt

# Dialog und Menü, Reiter Fertigung, Kachel, Termin prüfen
from rohrlaser.auslastung_dialog import AuslastungDialog  # noqa: E402
dlg = f.maschinenauslastung()
assert isinstance(dlg, AuslastungDialog) and dlg.tabelle.rowCount() == 3 and dlg.balken.zeilen
seite = f.fertigung
assert seite.seiten.tabText(1) == "Auslastung" and not seite.auslastung.geladen
seite.auslastung_zeigen()
assert seite.seiten.currentIndex() == 1 and seite.auslastung.geladen
start = next(w for w in (f.reiter.widget(i) for i in range(f.reiter.count())) if hasattr(w, "auslastung_kachel"))
assert start.auslastung_laden(heute) and not start.auslastung_kachel.isHidden()
text = start.auslastung_kachel.text()
assert "T03 100 %" in text and "Terminrisiko" in text, text
start.auslastung_kachel.grab()
satz = auslastung_ansicht.frei_satz(db, "T11", D(2026, 11, 6), heute)
assert "Freie Laserzeit auf T11 bis 06.11.2026: 12,0 h" in satz, satz
assert auslastung_ansicht.frei_satz(db, None, heute) == "" and auslastung_ansicht.frei_satz(db, "T03", None) == ""
ok("E5b Merker, Fenster, Reiter Fertigung → Auslastung, Kachel der Startseite, Satz für „Termin prüfen“")
print("Alle Einlastungs-Tests bestanden.")
