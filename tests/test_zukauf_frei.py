"""Prüft Zukaufartikel direkt in der Position ohne Artikelstamm (Patrick 12.11.2026, Konzept „Zukaufartikel direkt in
der Position“, Freigabe alle a). Die zehn Szenarien des Auftrags:
 1 neue Position ohne Zukaufartikel, 2 mit einem, 3 mit mehreren, 4 nachträglich bearbeiten (Menge, EK, VK →
 Aufschlag, Details), 5 entfernen und duplizieren, 6 speichern und erneut öffnen, 7 Angebot duplizieren,
 8 PDF intern (Kalkulation) und Kunde (keine internen Daten), 9 verschiedene Mengen und Preise (je Satz,
 Bezugskosten, gleicher Artikel in zwei Positionen = eine Bestellung, Aufschlag des Angebots, kein doppelter
 Aufschlag), 10 bestehende Angebote mit Stammartikeln rechnen unverändert.
Dazu: Summenzeile unter der Position (auf-/zuklappen), Schnellanlage ohne Stamm, EK eintragen, Im Artikelstamm merken.
Alle Preise sind Testwerte.

Aufruf: python tests/test_zukauf_frei.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

from rohrlaser import ausgabe, pdf, rechnen, unterzeilen, zukauf  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402
from rohrlaser.zukauf_dialog import EDIT, NEU_TEXT, OHNE_STAMM, ZukaufDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())
SPALTE = {name: c for c, name in EDIT.items()}


def ok(text):
    print("OK    ", text)


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


db = Datenbank(tmp / "f.db")
db.einstellung_setzen("aufschlag_blech", None)      # erst ohne Aufschlag im Angebot: Standard der Einstellungen
db.einstellung_setzen("aufschlag_zukauf", None)
db.einstellung_setzen("zukauf_aufschlag", 10)       # Standardaufschlag Zukaufteile 10 %
a = db.angebot_neu(dict(kunde="Test", skonto=0))
p1 = db.position_neu(a, dict(pos=10, artikel="Rohr A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                             laenge=1000, stueck=10, schneidweg=300, einstiche=2))
p2 = db.position_neu(a, dict(pos=20, artikel="Rohr B", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                             laenge=500, stueck=20, schneidweg=200, einstiche=2, satz="Rahmen", je_satz=2))
k, tab = db.kontext(), db.tabellen()
n_stamm = len(db.zukauf_artikel_liste())


def rechnung():
    kopf, pos = db.angebot(a), db.positionen(a)
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    erg = rechnen.optimieren(kopf, pos, k)
    return kopf, pos, einst, rechnen.kalkulation(kopf, pos, erg, k, tab, einst)


# ------------------------------------------------------------------ Rechenkern
e = zukauf.frei_eintrag("Schraube M8", 4, ek="0,15".replace(",", "."), regeln=[zukauf.regel(zukauf.PROZENT, 10)])
assert zukauf.ist_frei(e) and "artikel_id" not in e and e["stand"]["bezug"]["preise"] == [dict(ab=1, preis=0.15)]
for falsch in (dict(bezeichnung=" "), dict(bezeichnung="X", menge=0), dict(bezeichnung="X", aufschlag=-1)):
    try:
        zukauf.frei_eintrag(**falsch)
        raise AssertionError(f"angenommen: {falsch}")
    except ValueError:
        pass
leer = zukauf.frei_eintrag("Ohne EK", 1)
_, je = zukauf.rechnen([(0, leer, 5)])
assert je[0]["fehler"] == "kein Einkaufspreis", "F7: EK leer erlaubt, gilt als EK fehlt"
nah(zukauf.aufschlag_aus_vk(1, 1.25), 25, "VK 1,25 auf Einstand 1,00 = 25 %")
try:
    zukauf.aufschlag_aus_vk(1, 0.9)
    raise AssertionError("VK unter Einstand angenommen")
except ValueError:
    pass
stamm = dict(artikel_id=7, menge=1, stand=dict(bezeichnung="Stamm", bezug=dict(preise=[dict(ab=1, preis=2)])))
assert not zukauf.ist_frei(stamm) and zukauf.stand_setzen(stamm, "ek", 3) and stamm[zukauf.GEAENDERT], \
    "F4: Stammartikel in der Position geändert"
assert not zukauf.stand_setzen(stamm, "ek", 3), "gleicher Wert = keine Änderung"
ok("Rechenkern: freier Eintrag, Pflicht nur Bezeichnung + Menge, EK leer = EK fehlt, VK → Aufschlag, F4-Kennzeichen")

# ------------------------------------------------------------------ 1 ohne Zukaufartikel
_, _, _, (z, s) = rechnung()
assert s["zukauf"] == [] and all(x["zukauf_teil"] == 0 for x in z if x)
vk_ohne = s["verkauf"]
ok("1 Neue Position ohne Zukaufartikel: keine Zukaufkosten")

f = Hauptfenster(db, stumm=True)
f.resize(1600, 950)
f.show()
seite = f.angebot_oeffnen(a)
app.processEvents()


def dialog(r=0):
    return ZukaufDialog(seite, db, db.positionen(a)[r])


# ------------------------------------------------------------------ 2 ein Zukaufartikel, direkt eingetippt
d = dialog()
d.auswahl.setEditText("Schraube M8")
d.menge.setText("4")
d.ek.setText("0,15")
d._hinzufuegen_klick()
assert len(d.eintraege) == 1 and zukauf.ist_frei(d.eintraege[0]), "frei eingetippt, kein Stamm nötig"
assert d.tabelle.item(0, 9).text() == OHNE_STAMM and d.tabelle.item(1, 0).text() == NEU_TEXT, "leere Zeile unten"
nah(d._vorschau(d.eintraege)[0]["vk"], 4 * 0.15 * 1.10, "Vorschau je Teil sofort (Standard 10 %)")
d.accept()
assert seite.zukaufteile([0], werte=d.ergebnis)
assert len(db.zukauf_artikel_liste()) == n_stamm, "kein Speichern im Artikelstamm"
_, _, _, (z, s) = rechnung()
nah(s["zukauf_einstand"], 4 * 0.15 * 10, "Einstand 4 × 0,15 € × 10 Teile")
nah(s["zukauf_aufschlag"], 0.6, "Aufschlag 10 %")
nah(z[0]["zukauf_teil"], 0.66, "Zukauf je Teil")
assert s["verkauf"] > vk_ohne
ok("2 Position mit einem Zukaufartikel: Bezeichnung, Menge, EK eintippen, OK; rechnet sofort, ohne Artikelstamm")

# ------------------------------------------------------------------ 3 mehrere Zukaufartikel (Beispiel des Auftrags)
d = dialog()
d.frei_hinzufuegen("Mutter M8", 4, ek=0.08)
d.tabelle.item(2, 0).setText("Nietmutter M8")            # leere Zeile unten: Bezeichnung eintippen
assert len(d.eintraege) == 3 and d.eintraege[2]["stand"]["bezeichnung"] == "Nietmutter M8"
d.tabelle.item(2, SPALTE["menge"]).setText("2")
d.tabelle.item(2, SPALTE["ek"]).setText("0,25")
einst_teil = sum(x["einstand"] for x in d._vorschau(d.eintraege))
nah(einst_teil, 1.42, "Summe Zukaufartikel 1,42 € je Teil (Einstand)")
assert "Summe Zukaufartikel" in d.info.text()
d.accept()
assert seite.zukaufteile([0], werte=d.ergebnis)
_, _, _, (z, s) = rechnung()
nah(s["zukauf_einstand"], 14.2, "Einstand 10 Teile")
nah(z[0]["zukauf_teil"], 1.42 * 1.1, "VK je Teil")
assert len(s["zukauf"]) == 3
ok("3 Mehrere Zukaufartikel: Schraube 4 × 0,15, Mutter 4 × 0,08, Nietmutter 2 × 0,25 = 1,42 € je Teil")

# Unterzeilen: Summenzeile, eingeklappt, Klick klappt auf
texte = [t for t, _ in seite.unter_texte[0]]
summe = [t for t in texte if "Zukaufartikel (3)" in t]
assert summe and "Summe 1,56 €/Teil" in summe[0] and "15,62 € Pos." in summe[0], texte
assert not any(t.startswith("Schraube M8") for t in texte), "eingeklappt"
assert any(getattr(x, "klappen", None) for x in seite.unter_texte[0])
assert seite.zukauf_klappen(0) is True
texte = [t for t, _ in seite.unter_texte[0]]
assert any(t.startswith("Schraube M8") for t in texte) and any("▾ Zukaufartikel" in t for t in texte)
assert seite.zukauf_klappen(0) is False
ok("Unterzeilen: Summenzeile 'Zukaufartikel (3) · Summe … €/Teil', ab 2 Artikeln eingeklappt, Klick klappt auf")

# ------------------------------------------------------------------ 4 nachträglich bearbeiten
d = dialog()
d.tabelle.item(0, SPALTE["menge"]).setText("6")          # Menge
assert d.eintraege[0]["menge"] == 6
d.tabelle.item(1, SPALTE["ek"]).setText("0,10")          # EK
nah(zukauf.ek_einheit(d.eintraege[1]["stand"]), 0.10, "EK geändert")
d.tabelle.item(2, SPALTE["vk"]).setText("0,40")          # VK je Einheit → Aufschlag %
nah(d.eintraege[2]["aufschlag"], 60, "VK 0,40 auf EK 0,25 = 60 %")
nah(d._vorschau(d.eintraege)[2]["vk_einheit"], 0.40, "VK je Einheit genau")
d.tabelle.item(2, SPALTE["vk"]).setText("0,10")          # unter Einstand: abgelehnt
assert "unter dem Einstand" in d.info.text() and d.eintraege[2]["aufschlag"] == 60
d.tabelle.item(0, SPALTE["menge"]).setText("abc")
assert "keine Zahl" in d.info.text() and d.eintraege[0]["menge"] == 6
d.tabelle.selectRow(0)
d.details_knopf.setChecked(True)
assert d.details.isVisibleTo(d)
for name, wert in (("hersteller", "Würth"), ("lieferant", "Schrauben-Meyer"), ("bemerkung", "nur verzinkt"),
                   ("beschreibung", "DIN 933 8.8"), ("fracht", "5")):
    d.detail_felder[name].setText(wert)
    d._detail_geaendert(name)
st0 = d.eintraege[0]["stand"]
assert (st0["hersteller"], st0["bezug"]["lieferant"], st0["bemerkung"], st0["bezug"]["fracht"]) == \
    ("Würth", "Schrauben-Meyer", "nur verzinkt", 5.0)
d.detail_text.setChecked(True)                           # im Angebotstext nennen
assert d.eintraege[0]["stand"]["angebotstext"] == "ja"
d.tabelle.item(0, SPALTE["bezeichnung"]).setText("")      # Bezeichnung darf nicht leer werden
assert d.eintraege[0]["stand"]["bezeichnung"] == "Schraube M8"
d.accept()
assert seite.zukaufteile([0], werte=d.ergebnis)
_, _, _, (z, s) = rechnung()
# Einstand: Schraube 6 × 0,15 × 10 + 5 € Fracht = 14; Mutter 4 × 0,10 × 10 = 4; Nietmutter 2 × 0,25 × 10 = 5
nah(s["zukauf_einstand"], 14 + 4 + 5, "Einstand nach Änderung")
nah(s["zukauf_aufschlag"], 14 * 0.1 + 4 * 0.1 + 5 * 0.6, "Aufschlag: 10 % Standard, Nietmutter 60 % (VK)")
ok("4 Bearbeiten: Menge, EK, VK (rechnet Aufschlag zurück), Details (Hersteller, Lieferant, Bezugskosten, Texte)")

# ------------------------------------------------------------------ 5 entfernen, duplizieren
d = dialog()
d.duplizieren([1])
assert len(d.eintraege) == 4 and d.eintraege[3] == d.eintraege[1] and d.eintraege[3] is not d.eintraege[1]
d.entfernen([3, 1])
assert [x["stand"]["bezeichnung"] for x in d.eintraege] == ["Schraube M8", "Nietmutter M8"]
d.reject()
assert len(zukauf.eintraege(db.positionen(a)[0])) == 3, "Abbrechen ändert nichts"
d = dialog()
d.entfernen([1])
d.accept()
assert seite.zukaufteile([0], werte=d.ergebnis)
_, _, _, (z, s) = rechnung()
nah(s["zukauf_einstand"], 14 + 5, "ohne Mutter")
ok("5 Duplizieren und Entfernen; Abbrechen speichert nichts")

# ------------------------------------------------------------------ 6 speichern und erneut öffnen
gespeichert = db.positionen(a)[0]["zukauf"]
f.angebot_schliessen(a)
seite = f.angebot_oeffnen(a)
app.processEvents()
d = dialog()
assert [x["stand"]["bezeichnung"] for x in d.eintraege] == ["Schraube M8", "Nietmutter M8"]
assert d.eintraege[0]["stand"]["hersteller"] == "Würth" and d.eintraege[1]["aufschlag"] == 60
d.accept()
assert json.loads(d.ergebnis) == json.loads(gespeichert), "Öffnen und OK ohne Änderung: Daten gleich"
ok("6 Speichern und erneut öffnen: alle Felder wiederhergestellt, keine Datenverluste")

# ------------------------------------------------------------------ 7 Angebot duplizieren
kopie = db.angebot_kopieren(a)
pk = db.positionen(kopie)
assert json.loads(pk[0]["zukauf"]) == json.loads(gespeichert)
kopf2, pos2 = db.angebot(kopie), db.positionen(kopie)
einst2 = rechnen.einstellungen_angebot(kopf2, db.einstellungen())
_, s2 = rechnen.kalkulation(kopf2, pos2, rechnen.optimieren(kopf2, pos2, k), k, tab, einst2)
nah(s2["zukauf_einstand"], s["zukauf_einstand"], "Kopie rechnet gleich")
ok("7 Angebot duplizieren: Zukaufartikel mitkopiert, gleiche Kalkulation")

# ------------------------------------------------------------------ 8 PDF intern und Kunde
import pypdfium2  # noqa: E402


def pdf_text(pfad):
    dok = pypdfium2.PdfDocument(str(pfad))
    return "\n".join(dok[i].get_textpage().get_text_range() for i in range(len(dok)))


kopf, pos, einst, (z, s) = rechnung()
pdf.kalkulation_pdf(tmp / "kalk.pdf", kopf, z, s, einst, positionen=pos)
t = pdf_text(tmp / "kalk.pdf")
assert "Schraube M8" in t and "Würth" in t and "ohne Stamm" in t and "Schrauben-" in t, "intern nachvollziehbar"
assert "60 % auf Einstand (Positionsaufschlag)" in t.replace("\r\n", " "), "Positionsaufschlag im Kalkulations-PDF"
ang = ausgabe.angebot(kopf, pos, z, k, einst)
pdf.angebot_pdf(tmp / "angebot.pdf", kopf, ang, db.einstellungen())
t = pdf_text(tmp / "angebot.pdf")
assert "inkl. 6 St Schraube M8" in t, "im Angebotstext genannt (Häkchen)"
assert "Nietmutter" not in t, "ohne Häkchen nicht genannt, steckt im Stückpreis"
for intern in ("Würth", "Schrauben-Meyer", "nur verzinkt", "DIN 933", "0,15", "60 %", "Einstand", "Aufschlag"):
    assert intern not in t, f"interne Angabe im Kundenangebot: {intern}"
ok("8 PDF: Kalkulation zeigt Artikel, Pos., Hersteller, Lieferant, 'ohne Stamm'; Kundenangebot ohne interne Daten")

# ------------------------------------------------------------------ 9 Mengen und Preise
d = dialog(1)                       # Pos. 20 im Satz Rahmen: je Satz vorgewählt (20 Teile, 2 je Satz = 10 Sätze)
assert d.je.currentData() == zukauf.JE_SATZ
d.frei_hinzufuegen("Nietmutter M8", 2, je=d.je.currentData(), ek=0.25)
d.accept()
assert seite.zukaufteile([1], werte=d.ergebnis)
_, _, _, (z, s) = rechnung()
g = [x for x in s["zukauf"] if x["stand"]["bezeichnung"] == "Nietmutter M8"]
assert len(g) == 1 and g[0]["bestellung"]["verbrauch"] == 2 * 10 + 2 * 10, "gleicher freier Artikel = eine Bestellung"
assert len(g[0]["schluessel"]) == 2
fr = [x for x in s["zukauf"] if x["stand"]["bezeichnung"] == "Schraube M8"][0]
nah(fr["bestellung"]["bezug"], 5, "Bezugskosten 5 € einmal je Bestellung")
# Aufschlag Zukaufteile des Angebots ersetzt den Standard; Positionsaufschlag (60 %) bleibt vorrangig, nie doppelt
db.angebot_aendern(a, "aufschlag_zukauf", 20)
kopf = db.angebot(a)
_, _, _, (z, s) = rechnung()
schr = [x for x in s["zukauf"] if x["stand"]["bezeichnung"] == "Schraube M8"][0]
nah(schr["aufschlag"], 14 * 0.20, "Angebotsaufschlag 20 % statt Standard 10 %, nicht 30 %")
pos = db.positionen(a)
_, je = zukauf.rechnen([((0, 1), zukauf.mit_angebotsaufschlag(zukauf.eintraege(pos[0])[1], kopf), 10)])
nah(je[(0, 1)]["aufschlag"], 5 * 0.6, "Positionsaufschlag 60 % geht vor, kein zusätzlicher Angebotsaufschlag")
ok("9 Mengen/Preise: je Satz, Bezugskosten einmal, gleiche Artikel zusammen bestellt, Aufschläge nie doppelt")

# ------------------------------------------------------------------ 10 bestehende Angebote mit Stammartikeln
ind = dict(aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT)
sid = db.zukauf_speichern(None, dict(artikelnr="Z-9", bezeichnung="Lasche", einheit="Stück", aufschlag_wert=25,
                                     **ind), [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=1.2)])])
alt = [dict(artikel_id=sid, menge=2, aufschlag=None, stand=db.zukauf_stand(sid))]
a2 = db.angebot_neu(dict(kunde="Alt", skonto=0))
db.position_neu(a2, dict(pos=10, artikel="Rohr", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=800,
                         stueck=5, schneidweg=100, einstiche=1, zukauf=json.dumps(alt)))
kopf3, pos3 = db.angebot(a2), db.positionen(a2)
einst3 = rechnen.einstellungen_angebot(kopf3, db.einstellungen())
_, s3 = rechnen.kalkulation(kopf3, pos3, rechnen.optimieren(kopf3, pos3, k), k, tab, einst3)
nah(s3["zukauf_einstand"], 2 * 1.2 * 5, "Stammartikel Einstand wie bisher")
seite3 = f.angebot_oeffnen(a2)
app.processEvents()
d = ZukaufDialog(seite3, db, db.positionen(a2)[0])
assert d.tabelle.item(0, 9).text().startswith("Stamm, Stand"), d.tabelle.item(0, 9).text()
d.accept()
assert json.loads(d.ergebnis) == alt, "öffnen + OK ändert einen Stammartikel nicht"
d = ZukaufDialog(seite3, db, db.positionen(a2)[0])
d.tabelle.item(0, SPALTE["ek"]).setText("1,50")
assert d.eintraege[0][zukauf.GEAENDERT] and "in Position geändert" in d.tabelle.item(0, 9).text()
assert zukauf.json_liste(db.zukauf_artikel(sid)["bezuege"][0]["preise"])[0]["preis"] == 1.2, "Stamm bleibt"
assert d.aktualisieren([0], bestaetigt=True) == 1 and zukauf.GEAENDERT not in d.eintraege[0], "zurück auf Stamm"
d.reject()
ok("10 Bestehende Angebote mit Stammartikeln: gleiche Rechnung, Öffnen ändert nichts, Änderung nur in der Position (F4)")

# ------------------------------------------------------------------ Im Artikelstamm merken (optional)
_, _, _, (_, s_vorher) = rechnung()
d = dialog()
d.tabelle.selectRow(0)
assert d.merken([0]) == 1 and d.eintraege[0]["artikel_id"] is not None and not zukauf.ist_frei(d.eintraege[0])
neu = db.zukauf_artikel(d.eintraege[0]["artikel_id"])
assert neu["bezeichnung"] == "Schraube M8" and "Hersteller Würth" in neu["beschreibung"] and neu["herkunft"] == "Angebot"
d.accept()
assert seite.zukaufteile([0], werte=d.ergebnis)
_, _, _, (_, s_nach) = rechnung()
nah(s_nach["verkauf"], s_vorher["verkauf"], "Merken ändert die Rechnung nicht")
ok("Im Artikelstamm merken: optional, legt den Artikel an, Preisstand der Position bleibt")

# ------------------------------------------------------------------ Schnellanlage ohne Stamm, EK eintragen
n_stamm = len(db.zukauf_artikel_liste())


def schnell(x):
    assert not x.stamm.isChecked() and x.ok_knopf.text() == "Übernehmen + schließen"
    x.kategorie.setCurrentText("")
    x.bezeichnung.setText("Typenschild")
    x.lieferant.setCurrentText("")
    x.ek.setText("")                    # EK leer: erlaubt, EK fehlt
    x.menge.setText("3")
    assert x.fertig(), x.info.text()
    return x.result()


assert seite.zukauf_schnell([], dialog=schnell) == 1
assert len(db.zukauf_artikel_liste()) == n_stamm, "nichts im Stamm"
p = db.positionen(a)[-1]
assert p["art"] == ZUKAUFTEIL and p["stueck"] == 3 and zukauf.ist_frei(zukauf.eintraege(p)[0])
_, _, _, (z, s) = rechnung()
assert z[-1]["zukauf_fehlt"] == 1, "EK fehlt wird gemeldet"
assert rechnen.zukaufteil_status(p) != "", "Angebots-Check warnt"
assert seite.zukauf_ek([len(db.positionen(a)) - 1], preise=[2.5]) == 1
assert len(db.zukauf_artikel_liste()) == n_stamm, "EK nur in der Position"
_, _, _, (z, s) = rechnung()
assert z[-1]["zukauf_fehlt"] == 0
nah(z[-1]["zukauf_teil"], 2.5 * 1.2, "EK 2,50 + Aufschlag 20 % des Angebots")


def schnell_im_dialog(x):
    x.bezeichnung.setText("Scheibe M8")
    x.ek.setText("0,02")
    x.menge.setText("8")
    return QDialog.Accepted if x.fertig() else QDialog.Rejected


d = dialog()
assert d.schnell(dialog=schnell_im_dialog) == 1 and zukauf.ist_frei(d.eintraege[-1]) and d.eintraege[-1]["menge"] == 8
d.reject()
ok("Schnellanlage ohne Artikelstamm (Vorgabe), EK leer = EK fehlt, EK eintragen nur in der Position")

# Unterzeile bei genau einem Artikel ohne Summenzeile
pz = dict(zukauf=json.dumps([zukauf.frei_eintrag("Bolzen", 1, ek=1)]), stueck=2)
zz = dict(stueck=2, zukauf_einzeln=[dict(vk=2.0, fehler="")])
txt = [t for t, _ in unterzeilen.schritte(pz, zz)]
assert len(txt) == 1 and txt[0].startswith("Bolzen") and "Zukaufartikel (" not in txt[0]
ok("Unterzeile: ein Artikel ohne Summenzeile")
print("OK: Zukaufartikel direkt in der Position")
