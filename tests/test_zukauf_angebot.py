"""Prüft Zukaufteile im Angebot (Testplan 9, 10 und 12): Rechnung je Position und Summe, gleicher Artikel in
mehreren Positionen als eine Bestellung, VK nach dem Gewinn nur mit Skonto, fehlender Einkaufspreis, Staffelpreise
mit eigener EK-Staffel je Mengenstufe, Preisstand (Stammdaten ändern das Angebot nicht, Aktualisieren mit
Vergleich alt/neu), Dialog je Position, Reiter Zukaufteile, Übernahme aus dem Artikel, Angebotstext.
Alle Preise sind Testwerte.

Aufruf: python tests/test_zukauf_angebot.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import ausgabe, rechnen, staffeln, zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def bezug(preise, pe=1, **w):
    b = dict(lieferant="Lieferant A", preiseinheit=pe, preise=[dict(ab=ab, preis=p) for ab, p in preise])
    b.update(w)
    return b


db = Datenbank(tmp / "z.db")
ind = dict(aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT)
# Schraube: 12,00 € je 100 St, ab 500 St 9,00 € je 100 St, VPE 100, Eingangsfracht 5 € je Bestellung, 25 %
schraube = db.zukauf_speichern(None, dict(artikelnr="Z-1", bezeichnung="Schraube M6x20", kategorie="Normteile",
                                          einheit="Stück", aufschlag_wert=25, angebotstext="ja",
                                          **ind),
                               [bezug([(1, 12), (500, 9)], 100, vpe=100, fracht=5)])
mutter = db.zukauf_speichern(None, dict(artikelnr="Z-2", bezeichnung="Mutter M6", einheit="Stück",
                                        aufschlag_wert=40, **ind), [bezug([(1, 0.05)])])
blech = db.zukauf_speichern(None, dict(artikelnr="Z-3", bezeichnung="Lasche", einheit="Stück", aufschlag_wert=20,
                                       angebotstext="ja", **ind), [bezug([(1, 1.20), (50, 0.95), (100, 0.80)])])
ohne = db.zukauf_speichern(None, dict(artikelnr="Z-4", bezeichnung="Drehteil", einheit="Stück"), [])

a = db.angebot_neu(dict(kunde="Test", skonto=2))
p1 = db.position_neu(a, dict(pos=10, artikel="A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                             stueck=10, schneidweg=300, einstiche=2, satz="BG", je_satz=1))
p2 = db.position_neu(a, dict(pos=20, artikel="B", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500,
                             stueck=10, schneidweg=200, einstiche=2, satz="BG", je_satz=1))
k, tab = db.kontext(), db.tabellen()


def eintrag(aid, menge, aufschlag=None):
    return dict(artikel_id=aid, menge=menge, aufschlag=aufschlag, stand=db.zukauf_stand(aid))


def rechnung():
    kopf, pos = db.angebot(a), db.positionen(a)
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    erg = rechnen.optimieren(kopf, pos, k)
    return kopf, pos, einst, rechnen.kalkulation(kopf, pos, erg, k, tab, einst)


_, _, _, (vorher, s_vorher) = rechnung()
assert s_vorher["zukauf"] == [] and s_vorher["zukauf_einstand"] == 0 and s_vorher["zukauf_aufschlag"] == 0
assert all(z["zukauf_teil"] == 0 for z in vorher if z)

# ------------------------------------------------------------------ 9 mehrere Positionen
# je Baugruppe: 4 Schrauben + 2 Muttern + 1 Lasche; Pos. 20 zusätzlich 2 Schrauben (gleicher Artikel)
db.position_aendern(p1, "zukauf", json.dumps([eintrag(schraube, 4), eintrag(mutter, 2), eintrag(blech, 1)]))
db.position_aendern(p2, "zukauf", json.dumps([eintrag(schraube, 2)]))
kopf, pos, einst, (z, s) = rechnung()
gr = {g["stand"]["artikelnr"]: g for g in s["zukauf"]}
assert sorted(gr) == ["Z-1", "Z-2", "Z-3"], "eine Bestellung je Artikel"
b = gr["Z-1"]["bestellung"]
nah(b["verbrauch"], 60, "Schrauben aus beiden Positionen zusammengezählt")
nah(b["bestellt"], 100, "VPE 100")
assert gr["Z-1"]["positionen"] == 2
# Einstand Schrauben = 100 × 0,12 + 5 Fracht = 17,00 €; Pos. 10 hat 40 von 60 St = 11,333 €, Pos. 20 5,667 €
nah(gr["Z-1"]["einstand"], 17, "Einstand Schrauben")
nah(gr["Z-1"]["vk"], 21.25, "VK Schrauben (+25 %)")
nah(gr["Z-2"]["vk"], 20 * 0.05 * 1.4, "Muttern 1,40 €")
nah(gr["Z-3"]["vk"], 10 * 1.20 * 1.2, "Laschen 10 St unter Staffel 50: 14,40 €")
vk_p1 = 21.25 * 40 / 60 + 1.40 + 14.40
nah(z[0]["zukauf_teil"] * 10, vk_p1, "Zukaufteile Pos. 10 je Teil × Stück")
nah(z[1]["zukauf_teil"] * 10, 21.25 * 20 / 60, "Zukaufteile Pos. 20")
nah(s["zukauf_einstand"] + s["zukauf_aufschlag"], 21.25 + 1.40 + 14.40, "Summe Zukaufteile")
# VK nach dem Gewinn, nur Skonto: Preisänderung je Teil = Zukauf je Teil / (1 − 2 %)
for i in (0, 1):
    nah(z[i]["preis_teil"] - vorher[i]["preis_teil"], z[i]["zukauf_teil"] / 0.98, f"Pos. {i}: nur Skonto")
    nah(z[i]["herstell_teil"], vorher[i]["herstell_teil"], "Herstellkosten ohne Zukaufteile")
nah(s["verkauf"] - s_vorher["verkauf"], (21.25 + 1.40 + 14.40) / 0.98, "Verkaufspreis Angebot", 1e-4)
kosten = dict((n, w) for (_, w, _), (_, n, _) in zip(rechnen.kostenarten(s, einst), rechnen.KOSTENARTEN))
nah(kosten["zukauf_einstand"], s["zukauf_einstand"], "Kostenart Einstand")
nah(sum(w for n, w in kosten.items() if n not in ("herstell", "verkauf", "material", "laser_schneiden", "gewinde",
                                                  "ruesten_maschine", "ruesten_abmessungen", "stangenwechsel_kosten",
                                                  "arbeitsschritte", "zusatz", "zuschlag_material",
                                                  "zuschlag_fertigung", "zuschlag_fremdleistung"))
    + kosten["herstell"], kosten["verkauf"], "Kostenarten ergeben den Verkaufspreis", 1e-6)
assert not z[0]["hinweis"].startswith("Zukauf")
text = ausgabe.angebotstext(pos[0], k)
assert "inkl. Zukaufteile: 4 St Schraube M6x20, 1 St Lasche" in text and "Mutter" not in text, text
ok("9 Mehrere Positionen: 4 Schrauben + 2 Muttern + 1 Lasche je Baugruppe, gleicher Artikel zusammen bestellt, "
   "VK nach Gewinn nur mit Skonto, Kostenarten, Angebotstext")

# Positionsaufschlag ersetzt die Regel des Artikels für diese Position
db.position_aendern(p2, "zukauf", json.dumps([eintrag(schraube, 2, aufschlag=50)]))
_, _, _, (z, s) = rechnung()
nah(z[1]["zukauf_teil"] * 10, 17 * 20 / 60 * 1.5, "Pos. 20 mit 50 %")
nah(z[0]["zukauf_teil"] * 10, 21.25 * 40 / 60 + 1.40 + 14.40, "Pos. 10 unverändert 25 %")
db.position_aendern(p2, "zukauf", json.dumps([eintrag(schraube, 2)]))

# fehlender Einkaufspreis: Hinweis, kein Preis mit 0
db.position_aendern(p2, "zukauf", json.dumps([eintrag(schraube, 2), eintrag(ohne, 1)]))
_, _, _, (z, s) = rechnung()
assert z[1]["hinweis"] == "Zukaufteil: kein Einkaufspreis", z[1]["hinweis"]
assert z[1]["zukauf_fehlt"] == 1 and s["zukauf_fehlt"] == 1
ok("Positionsaufschlag ersetzt die Artikelregel; fehlender Einkaufspreis gibt Hinweis")

# ------------------------------------------------------------------ 10 Fertigungsstaffeln
kopf, pos, einst, _ = rechnung()
st = staffeln.stufe_rechnen(kopf, pos, "BG", 10, k, tab, einst)
assert st["preis_einheit"] is None and "Zukaufteil ohne Einkaufspreis" in st["hinweis"], st["hinweis"]
db.position_aendern(p2, "zukauf", json.dumps([eintrag(schraube, 2)]))
kopf, pos, einst, (z, s) = rechnung()
werte = {}
for menge in (10, 50, 100, 500):
    st = staffeln.stufe_rechnen(kopf, pos, "BG", menge, k, tab, einst)
    p = st["preis"]
    werte[menge] = p
    # Schrauben: 6 je BG, VPE 100, ab 500 St 9 € je 100; Laschen: 1 je BG, Staffel 1,20 / 0,95 / 0,80
    sch = -(-6 * menge // 100) * 100
    ek_s = (0.09 if sch >= 500 else 0.12) * sch + 5
    ek_l = menge * (0.80 if menge >= 100 else 0.95 if menge >= 50 else 1.20)
    ek_m = 2 * menge * 0.05
    nah(p["zukauf_einstand"], ek_s + ek_l + ek_m, f"Stufe {menge}: Einstand", 1e-6)
    nah(p["zukauf_aufschlag"], ek_s * 0.25 + ek_l * 0.2 + ek_m * 0.4, f"Stufe {menge}: Aufschlag", 1e-6)
nah(werte[10]["zukauf_einstand"], 17 + 12 + 1, "10 BG: 100 Schrauben, 10 Laschen à 1,20")
nah(werte[500]["zukauf_einstand"], 3000 * 0.09 + 5 + 400 + 50, "500 BG: Staffel 500 und 100")
# ohne Werte der Stufe = Verkaufspreis der Kalkulation (gleiche Stückzahl)
st = staffeln.stufe_rechnen(kopf, pos, "BG", 10, k, tab, einst)
nah(st["preis"]["netto"], s["verkauf"], "Stufe = Kalkulation", 1e-6)
ok("10 Fertigungsstaffeln 10/50/100/500 BG mit eigener EK-Staffel und Bestellmenge je Stufe; Stufe 10 = Kalkulation")

# ------------------------------------------------------------------ 12 Preisstand
vk_alt = s["verkauf"]
art = db.zukauf_artikel(schraube)
art_bezug = art.pop("bezuege")
art_bezug[0]["preise"] = [dict(ab=1, preis=20)]
db.zukauf_speichern(schraube, art, art_bezug)
kat = db.zukauf_kategorien()
_, _, _, (z, s) = rechnung()
nah(s["verkauf"], vk_alt, "gespeichertes Angebot unverändert nach Preisänderung")
assert db.zukauf_verwendung(schraube)["veraltet"] == [db.angebot(a)["nummer"]]

f = Hauptfenster(db, stumm=True)
f.resize(1280, 900)
f.show()
seite = f.angebot_oeffnen(a)
app.processEvents()
gesehen = {}


def bedienen(d):
    gesehen["vergleich"] = [(name, float(alt), float(neu)) for _, name, alt, neu, _ in d.vergleich()]
    assert d.aktualisieren([0], bestaetigt=True) == 1
    return QDialog.Accepted if (d.accept() or True) else QDialog.Rejected


assert seite.zukaufteile([0], dialog=bedienen)
name, alt, neu = gesehen["vergleich"][0]
assert name == "Schraube M6x20"
# Vorschau je Position (Pos. 10 allein): 40 St → Bestellung 100 St; alt 100 × 0,12 + 5 = 17 €, neu 100 × 0,20 + 5
nah(alt, 17 * 1.25 / 10, "alt je Teil", 1e-4)
nah(neu, (100 * 0.20 + 5) * 1.25 / 10, "neu je Teil", 1e-4)
_, _, _, (z, s) = rechnung()
assert s["verkauf"] > vk_alt
assert len({zukauf.stand_kennung(e["stand"]) for p in db.positionen(a) for e in zukauf.eintraege(p)
            if e["artikel_id"] == schraube}) == 2, "Pos. 20 behält den alten Stand"
ok("12 Preisstand: Stammdaten ändern das Angebot nicht; Aktualisieren zeigt alt/neu und übernimmt erst nach OK")

# ------------------------------------------------------------------ Oberfläche
spalte = [seite.pos_modell.name(c) for c in range(seite.pos_modell.columnCount())].index("zukauf")
assert not seite.pos_ansicht.isColumnHidden(spalte), "Spalte Zukaufteile sichtbar, sobald Werte da sind"
assert "Schraube M6x20" in seite.pos_modell.data(seite.pos_modell.index(0, spalte))
reiter = [seite.reiter.tabText(i) for i in range(seite.reiter.count())]
assert "Zukaufteile" in reiter, reiter
zeilen = seite.zukauf.zeilen
assert len(zeilen) == 4, "Schraube in zwei Preisständen, Mutter, Lasche"
assert {z["artikel"] for z in zeilen} == {"Z-1", "Z-2", "Z-3"}
assert "Einstand" in seite.zukauf_info.text()

# Dialog: hinzufügen, Menge ändern, duplizieren, entfernen, Abbrechen ändert nichts
from rohrlaser.zukauf_dialog import ZukaufDialog  # noqa: E402
d = ZukaufDialog(seite, db, db.positionen(a)[1])
d.hinzufuegen(blech, 2)
d.tabelle.item(1, 1).setText("3")
assert d.eintraege[1]["menge"] == 3
d.duplizieren([1])
assert len(d.eintraege) == 3
d.entfernen([2])
try:
    d.hinzufuegen(blech, 0)
    raise AssertionError("Menge 0 angenommen")
except ValueError:
    pass
d.reject()
assert len(zukauf.eintraege(db.positionen(a)[1])) == 1, "Abbrechen speichert nichts"
d.accept()
assert len(json.loads(d.ergebnis)) == 2
ok("Oberfläche: Spalte und Reiter Zukaufteile, Dialog (Hinzufügen, Menge, Duplizieren, Entfernen, Abbrechen)")

# Übernahme aus dem Artikel: neue Position bekommt den Artikel mit aktuellem Stand
p3 = db.position_neu(a, dict(pos=30, artikel="C", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=300,
                             stueck=5))
f.reiter.setCurrentWidget(f.zukauf)
app.processEvents()
assert f.zukauf.artikel.in_angebot(mutter, ziel=(p3, 4)) == p3
e = zukauf.eintraege([p for p in db.positionen(a) if p["id"] == p3][0])
assert e[0]["artikel_id"] == mutter and e[0]["menge"] == 4 and e[0]["stand"]["bezeichnung"] == "Mutter M6"
assert any(p["id"] == p3 and p.get("zukauf") for p in seite.positionen), "geöffnetes Angebot neu geladen"
db.zukauf_status(blech, "archiviert")
f.zukauf.artikel.neu_laden()
assert f.zukauf.artikel.in_angebot(blech, ziel=(p3, 1)) is None, "archiviert nicht übernehmen"
_, _, _, (z, s) = rechnung()
assert z[2]["zukauf_teil"] > 0 and z[0]["zukauf_teil"] > 0, "archivierter Artikel rechnet im Angebot weiter"
ok("In Angebot übernehmen aus dem Artikel; archivierte Artikel nicht wählbar, bestehende Positionen rechnen weiter")

# Darstellung: der Reiter Zukaufteile passt in 1024 Pixel (Tabelle scrollt in sich, die Seite nicht)
seite.reiter.setCurrentIndex(reiter.index("Zukaufteile"))
app.processEvents()
assert seite.reiter.currentWidget().minimumSizeHint().width() < 1000
ok("Darstellung: Reiter Zukaufteile ab 1024 Pixel")
print("OK: Zukaufteile im Angebot und in den Staffelpreisen")
