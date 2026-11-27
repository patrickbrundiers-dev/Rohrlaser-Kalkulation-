"""Zusatzarbeiten flexibel: allgemein für das Angebot und je Position mit Einheitspreisen (Master-Auftrag Patrick
23.11.2026, zusatz_global.py, zusatz_global_seite.py, Haken „Preis = Verkauf“ im Fenster Zusatzarbeiten).

Die 12 Szenarien des Auftrags (Abschnitt 11):
 1 Globale Zusatzarbeit hinzufügen            2 Zusatzarbeit einer einzelnen Position hinzufügen
 3 Unterschiedliche Preise je Position       4 Standardpreis aus der zentralen Verwaltung übernehmen
 5 Standardpreis individuell überschreiben   6 Positionsmenge verändern
 7 Zusatzarbeiten automatisch neu berechnen  8 Globale Pauschale hinzufügen
 9 Prozentualen Zuschlag berechnen          10 PDF-Angebot mit Zusatzarbeiten erstellen
11 Angebot erneut öffnen, Preise kontrollieren 12 Bestehende Angebote auf Datenintegrität prüfen
dazu: Überschneidungs-Warnung (global und Position), Übertragen auf mehrere Positionen, Kopie/Fassung, Darstellung
detailliert/zusammengefasst/nur Gesamtpreis, interne Werte nie im Kundenangebot, Staffeln ohne allgemeine Beträge.

Aufruf: python tests/test_zusatz_global.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import angebot_check, marge, rechnen, zusatz_global as zg  # noqa: E402
from rohrlaser.ausgabe import kaufm_runden  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


def nah(a, b, tol=0.005):
    return abs(float(a) - float(b)) < tol


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
ROHR1 = dict(pos=10, artikel="R60", bezeichnung="Rohr 60x40", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
             laenge=800, stueck=10, schneidweg=300, einstiche=2)
ROHR2 = dict(pos=20, artikel="R80", bezeichnung="Rohr 80x40", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
             laenge=450, stueck=20, schneidweg=260, einstiche=2)


def angebot(pos=(ROHR1, ROHR2)):
    a = db.angebot_neu(dict(kunde="Test (erfunden)", maschine="T11", stange=6000))
    for p in pos:
        db.position_neu(a, dict(p))
    s = oeffnen(a)
    assert s.optimieren()
    return a, s


def oeffnen(aid):
    """Angebot öffnen (bzw. zum offenen Reiter wechseln) und aus der Datenbank neu laden."""
    s = f.angebot_oeffnen(aid)
    s.neu_laden()
    return s


def rechnung(s):
    kz, summen = s._rechnung()
    return kz, summen, s.angebot_daten(staffeln=False)


# ---------------------------------------------------------------- 12 Bestand bitgleich (vorher messen)
a, s = angebot()
kz0, sum0, ang0 = rechnung(s)
assert "zusatz_global" in dict((n, 1) for _, n, _ in rechnen.KOSTENARTEN)
assert not sum0.get("zusatz_global") and not any("zusatz_vk_teil" in (z or {}) for z in kz0)
assert all(not z.get("zusatz_global") for z in ang0["zeilen"])
basis = sum0["verkauf"]
netto0 = ang0["netto"]

# ---------------------------------------------------------------- 1 globale Zusatzarbeit (Stunden)
seite = s.zusatz_seite
assert seite.hinzufuegen("Sonderbearbeitung", 3, "h", 65.0, beschreibung="Nacharbeit nach Zeichnung",
                         kosten=48.0, zeit_min=60)
s = oeffnen(a)
_, sum1, ang1 = rechnung(s)
assert nah(sum1["zusatz_global"], 195.0) and nah(sum1["verkauf"], basis + 195.0), sum1["verkauf"]
assert nah(sum1["zusatz_global_kosten"], 144.0) and nah(sum1["zusatz_global_zeit_min"], 180)
zeile = [z for z in ang1["zeilen"] if z.get("zusatz_global")]
assert len(zeile) == 1 and zeile[0]["menge"] == 3 and zeile[0]["preis"] == 65.0 and zeile[0]["gesamt"] == 195.0
assert nah(ang1["netto"], netto0 + 195.0) and nah(ang1["mwst"], kaufm_runden(ang1["netto"] * ang1["mwst_satz"], 2))
assert nah(ang1["brutto"], ang1["netto"] + ang1["mwst"])
m0, m1 = marge.werte(sum0), marge.werte(sum1)
assert nah(m1["kosten"], m0["kosten"] + 144.0) and nah(m1["gewinn"], m0["gewinn"] + 51.0), (m0, m1)
assert "48" not in zeile[0]["text"] and "Nacharbeit" not in zeile[0]["text"]      # intern bleibt intern
ok("1 Globale Zusatzarbeit: 3 h × 65 € = 195 € als eigene Zeile, netto/MwSt/brutto, Kosten nur in der Marge")

# ---------------------------------------------------------------- 8 Pauschale, 9 Prozent
assert seite.hinzufuegen("Verpackung", 1, zg.PAUSCHAL, 45.0)
assert s.zusatz_seite.hinzufuegen("Qualitätszuschlag", 2.0, zg.PROZENT, 0.0, basis=zg.BASIS[0])
s = oeffnen(a)
_, sum2, ang2 = rechnung(s)
prozent = kaufm_runden(basis * 0.02, 2)
assert nah(sum2["zusatz_global"], 195 + 45 + prozent), (sum2["zusatz_global"], prozent)
gz = [z for z in ang2["zeilen"] if z.get("zusatz_global")]
assert [z["gesamt"] for z in gz][:2] == [195.0, 45.0] and gz[1]["einheit"] == "pausch."
assert "2 %" in gz[2]["text"] and nah(gz[2]["gesamt"], kaufm_runden(netto0 * 0.02, 2))
ok(f"8 Pauschale 45 € und 9 Zuschlag 2 % auf die Positionen ({prozent:.2f} €)")

# Zeit aus dem Stundensatz (Patrick 23.11.2026): freie Einträge ohne eigene Zeit, Vorgabe 60 €/h
assert zg.stundensatz(s.einst) == 60.0
assert nah(sum2["zusatz_global_zeit_min"], 180 + 45), sum2["zusatz_global_zeit_min"]   # 45 € ÷ 60 €/h = 45 min
z_verp = s.zusatz_seite.tabelle.item(1, 7)
assert z_verp.text() == "45" and "Stundensatz" in z_verp.toolTip(), (z_verp.text(), z_verp.toolTip())
assert s.zusatz_seite.tabelle.item(0, 7).text() == "60" and not s.zusatz_seite.tabelle.item(0, 7).toolTip()
assert zg.zeit_je_einheit(dict(einheit="Stück", preis=10.0, kosten=6.0), 60.0) == 6.0     # Kosten vor Preis
assert zg.zeit_je_einheit(dict(einheit="Stück", preis=10.0, zeit_min=0), 60.0) == 0.0     # eigene Zeit 0 gilt
assert zg.zeit_je_einheit(dict(einheit="Stück", preis=10.0), 0.0) == 0.0                  # Satz 0 = aus
assert zg.zeit_je_einheit(dict(einheit=zg.PROZENT, menge=2.0), 60.0) == 0.0
ok("Zeit aus dem Stundensatz: Verpackung 45 € bei 60 €/h = 45 min (grau, überschreibbar), Kosten vor Preis, "
   "eigene Zeit gilt, Preis unverändert")

# Patrick 27.11.2026: eigene Zusatzarbeiten an der Position ohne Zeitaufwand: Zeit = Preis ÷ Stundensatz
tab = dict(s.tabellen, zusatzarbeiten=list(s.tabellen["zusatzarbeiten"]) + [
    dict(name="Test Festpreis eigen", art="€/Stück", preis=3.0, aktiv="ja", fremd="nein"),
    dict(name="Test Festpreis fremd", art="€/Stück", preis=3.0, aktiv="ja", fremd="ja")],
    einstellungen=dict(s.tabellen.get("einstellungen") or {}, zusatz_stundensatz=60.0))
pz = dict(s.positionen[0], zusatz=json.dumps([dict(name="Test Festpreis eigen", menge=2),
                                              dict(name="Test Festpreis fremd", menge=2)]))
w = {z["name"]: z for z in rechnen.zusatz_werte(pz, s.k, tab, s.kopf)}
assert nah(w["Test Festpreis eigen"]["betrag"], 6.0) and nah(w["Test Festpreis eigen"]["arbeit_s"], 360.0), w
assert w["Test Festpreis fremd"]["arbeit_s"] == 0.0                     # Fremdleistung ohne Zeit
w0 = {z["name"]: z for z in rechnen.zusatz_werte(pz, s.k, dict(tab, einstellungen=dict(
    tab["einstellungen"], zusatz_stundensatz=0)), s.kopf)}
assert w0["Test Festpreis eigen"]["arbeit_s"] == 0.0 and nah(w0["Test Festpreis eigen"]["betrag"], 6.0)   # 0 = aus
ok("Eigene Zusatzarbeit an der Position ohne Zeitaufwand: 2 × 3 € bei 60 €/h = 6 min je Teil, Fremdleistung ohne "
   "Zeit, Preis unverändert")

# Grundlage „Positionen und Zusatzarbeiten“
liste = zg.liste(s.kopf)
liste[2]["basis"] = zg.BASIS[1]
s.zusatz_seite.speichern(liste)
s = oeffnen(a)
_, sum3, _ = rechnung(s)
assert nah(sum3["zusatz_global"], 240 + kaufm_runden((basis + 240) * 0.02, 2))
ok("9b Zuschlag % auf Positionen und Zusatzarbeiten")

# ---------------------------------------------------------------- 2, 3 je Position mit festem Verkaufspreis
db.position_aendern(s.positionen[0]["id"], "zusatz", json.dumps([
    dict(name="Entgraten", menge=1, preis=2.5, vk="ja"), dict(name="Bohren", menge=4, preis=0.8, vk="ja")]))
db.position_aendern(s.positionen[1]["id"], "zusatz", json.dumps([dict(name="Entgraten", menge=1, preis=3.0, vk="ja")]))
s = oeffnen(a)
kz4, sum4, ang4 = rechnung(s)
assert nah(kz4[0]["preis_teil"], kz0[0]["preis_teil"] + 2.5 + 3.2), (kz4[0]["preis_teil"], kz0[0]["preis_teil"])
assert nah(kz4[1]["preis_teil"], kz0[1]["preis_teil"] + 3.0)
assert nah(sum4["zusatz_vk"], 10 * 5.7 + 20 * 3.0)
ok("2/3 Position 1 Entgraten 2,50 € + 4 Bohrungen × 0,80 €, Position 2 Entgraten 3,00 € je Stück (Verkauf fest)")

# Überschneidung: Entgraten jetzt auch allgemein
s.zusatz_seite.hinzufuegen("Entgraten", 1, zg.PAUSCHAL, 20.0)
s = oeffnen(a)
treffer = zg.ueberschneidungen(s.kopf, s.positionen)
assert treffer and treffer[0][0] == "Entgraten" and treffer[0][1] == [10, 20], treffer
assert s.zusatz_seite.warnung.isVisibleTo(s.zusatz_seite) and "doppelt" in s.zusatz_seite.warnung.text()
_, summen_c = s._rechnung()
punkte = angebot_check.punkte(s.kopf, s.positionen, [], "aktuell", summen_c)
assert any("doppelt" in p.text for p in punkte), [p.text for p in punkte]
s.zusatz_seite.entfernen_markierte([3])
s = oeffnen(a)
assert not zg.ueberschneidungen(s.kopf, s.positionen)
ok("Überschneidung Entgraten allgemein + Pos. 10/20: Warnung im Reiter und im Angebots-Check")

# ---------------------------------------------------------------- 6, 7 Positionsmenge ändern
db.position_aendern(s.positionen[0]["id"], "stueck", 25)
s = oeffnen(a)
assert s.optimieren()
kz6, sum6, ang6 = rechnung(s)
assert nah(sum6["zusatz_vk"], 25 * 5.7 + 20 * 3.0)
teil = [z for z in ang6["zeilen"] if z["art"] == "teil" and z["pos"] == 10][0]
assert teil["menge"] == 25
assert nah(sum6["zusatz_global"], 240 + kaufm_runden((sum6["verkauf_positionen"] + 240) * 0.02, 2))
ok("6/7 Stückzahl 10 → 25: Zusatzarbeiten je Position und Zuschlag % neu gerechnet")

# ---------------------------------------------------------------- 4, 5 Standardpreis aus der Verwaltung
katalog = {z["name"]: z for z in s.tabellen["zusatzarbeiten"]}
name = next(n for n, z in katalog.items() if z.get("art") == "€/Stück" and rechnen._n(z.get("preis")) > 0
            and z.get("aktiv") != "nein")
assert s.zusatz_seite.hinzufuegen_katalog(name)
s = oeffnen(a)
e = zg.liste(s.kopf)[-1]
kosten = rechnen.zusatz_preis(katalog[name], rechnen.stundensaetze(s.tabellen))["preis"]
erwartet = kaufm_runden(kosten * (1 + rechnen._n(s.einst.get("zuschlag_fremdleistung") if katalog[name].get("fremd") == "ja"
                                                 else s.einst.get("zuschlag_fertigung")))
                        * (1 + rechnen._n(s.einst.get("gewinn"))), 2)
assert e["katalog"] == name and nah(e["preis"], erwartet) and nah(e["kosten"], kosten) and e["stand"]["preis"] == e["preis"]
ok(f"4 Standardpreis aus der Verwaltung: {name} Kosten {kosten:.2f} € → Verkauf {erwartet:.2f} € vorgeschlagen")
liste = zg.liste(s.kopf)
liste[-1]["preis"] = 9.99
s.zusatz_seite.speichern(liste)
# Verwaltung ändert den Standardpreis: das Angebot bleibt (Snapshot)
zid = katalog[name]["id"]
db.zusatz_speichern(zid, dict(katalog[name], preis=rechnen._n(katalog[name].get("preis")) * 3))
s = oeffnen(a)
assert zg.liste(s.kopf)[-1]["preis"] == 9.99
_, sum5, _ = rechnung(s)
ok("5 Standardpreis überschrieben (9,99 €), Änderung der Verwaltung ändert das Angebot nicht")

# ---------------------------------------------------------------- Übertragen auf mehrere Positionen
s.zusatz_seite.hinzufuegen("Schleifen", 1, "Stück", 4.0, kosten=2.0)
s = oeffnen(a)
nr = len(zg.liste(s.kopf)) - 1
vor = rechnung(s)
assert s.zusatz_seite.auf_positionen(nr, [0, 1], 1.0, entfernen=True)
s = oeffnen(a)
kz7, sum7, _ = rechnung(s)
assert all(any(x["name"] == "Schleifen" and x.get("vk") for x in rechnen.zusatz_liste(p)) for p in s.positionen)
assert nah(kz7[0]["preis_teil"], vor[0][0]["preis_teil"] + 4.0) and nah(kz7[1]["preis_teil"], vor[0][1]["preis_teil"] + 4.0)
assert not any(x["name"] == "Schleifen" for x in zg.liste(s.kopf))
assert nah(kz7[0]["zusatz_vk_kosten_teil"] - vor[0][0]["zusatz_vk_kosten_teil"], 2.0)
ok("Allgemeine Zusatzarbeit „Schleifen 4 € je Stück“ auf 2 Positionen übertragen, allgemein entfernt")

# ---------------------------------------------------------------- 10 PDF: drei Darstellungen
for art in zg.DARSTELLUNGEN:
    s.zusatz_seite.speichern(darstellung=art)
    s = oeffnen(a)
    _, summen, ang = rechnung(s)
    pos1 = [z for z in ang["zeilen"] if z["art"] == "teil" and z["pos"] == 10][0]
    glob = [z for z in ang["zeilen"] if z.get("zusatz_global")]
    if art == zg.ZUSAMMEN:
        assert "inkl." in pos1["text"] and len(glob) == len(zg.liste(s.kopf))
    elif art == zg.DETAIL:
        auf = pos1["zusatz_aufstellung"]
        assert "Positionspreis einschließlich Zusatzarbeiten" in pos1["text"]
        ent = [x for x in auf if x[2] == "Stk." and x[3] == 2.5]
        assert ent, auf
        ent = ent[0]
        assert ent[1] == 25 and ent[3] == 2.5 and ent[4] == 62.5, ent
        assert "Nacharbeit nach Zeichnung" in glob[0]["text"]
    else:
        assert "Entgraten" not in pos1["text"] and len(glob) == 1
        assert nah(glob[0]["gesamt"], sum(r["gesamt"] for r in zg.zeilen(zg.liste(s.kopf), summen["verkauf_positionen"])),
                   0.02)
    assert nah(ang["netto"], sum(z["gesamt"] for z in ang["zeilen"] if z["gesamt"] is not None))
    for intern in ("Kosten", "intern", "Deckungsbeitrag"):
        assert all(intern not in (z.get("text") or "") for z in ang["zeilen"]), (art, intern)
    datei = tmp / f"angebot_{art.replace(' ', '_')}.pdf"
    from rohrlaser import pdf
    pdf.angebot_pdf(datei, s.kopf, ang, s.einst)
    assert datei.exists() and datei.stat().st_size > 1000, datei
ok("10 Kundenangebot: zusammengefasst (inkl. …), detailliert (25 × 2,50 € = 62,50 €), nur Gesamtpreis (eine Zeile); "
   "keine internen Werte")

# ---------------------------------------------------------------- 11 erneut öffnen
f.angebot_schliessen(a)
s = oeffnen(a)
_, sum11, ang11 = rechnung(s)
assert nah(sum11["verkauf"], summen["verkauf"]) and nah(ang11["netto"], ang["netto"])
assert zg.darstellung(s.kopf) == zg.NUR_GESAMT
ok("11 Angebot geschlossen und neu geöffnet: gleiche Preise, Darstellung gespeichert")

# ---------------------------------------------------------------- Kopie / Fassung
k = db.angebot_kopieren(a)
s2 = oeffnen(k)
assert s2.optimieren()
assert zg.liste(s2.kopf) == zg.liste(s.kopf) and zg.darstellung(s2.kopf) == zg.NUR_GESAMT
ok("Kopie übernimmt allgemeine Zusatzarbeiten und Darstellung")

# ---------------------------------------------------------------- Staffel ohne allgemeine Beträge
assert zg.ohne(s.kopf) is not s.kopf and not zg.liste(zg.ohne(s.kopf))
assert zg.ohne(dict(id=1)) == dict(id=1)
ok("Staffeln rechnen ohne allgemeine Zusatzarbeiten (eigene Zeilen)")

# ---------------------------------------------------------------- 12 Datenintegrität bestehender Angebote
b, sb = angebot()
kz12, sum12, ang12 = rechnung(sb)
assert nah(sum12["verkauf"], basis) and ang12["netto"] == netto0
assert [z["preis_teil"] for z in kz12] == [z["preis_teil"] for z in kz0]
assert db.angebot(b)["zusatz"] == {} or not db.angebot(b)["zusatz"].get(zg.SCHLUESSEL)
# Position ohne Haken: Preis wie bisher (Zuschlag + Gewinn)
db.position_aendern(sb.positionen[0]["id"], "zusatz", json.dumps([dict(name="Entgraten", menge=1, preis=2.5)]))
sb = oeffnen(b)
kz13, sum13, _ = rechnung(sb)
assert "zusatz_vk" not in sum13 and kz13[0]["zusatz_eigen_teil"] >= 2.5 - 1e-9
ok("12 Angebot ohne allgemeine Zusatzarbeiten und ohne Haken: Preise Cent für Cent wie vorher")
print("test_zusatz_global OK")
