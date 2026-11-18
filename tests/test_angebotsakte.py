"""Angebotsakte: neues Angebots- und Kalkulationsdokument (Patrick 18.11.2026, Entwicklungsauftrag „Neues
PDF-Angebots- und Kalkulationssystem“).

Geprüft mit einem realistischen Angebot (Schweißbaugruppe mit Satzteilen, Zukaufteile, Edelstahl mit Gewinde, Muster,
zweite Profilform, gestaffelter Gewinn, Fracht, Skonto, Staffeln) und einem großen Angebot mit 60 Positionen:
- alle Werte aus der einen Kalkulation (Positionen = Netto, Kostenpositionen = Verkaufspreis, Rechnung unverändert),
- Kunden-PDF ohne interne Begriffe und Werte, internes PDF mit INTERN-Leiste und allen Seiten,
- Schnittschema = Schnittplan (Rohre, Teile je Position, eindeutige Teilnummern),
- Gewinde nur €/Stück, Gewinnbasis ohne Zukauf,
- Ablage mit Unterordnern, Versionen (nichts überschrieben), Fingerabdruck aktuell/veraltet, automatische Erneuerung
  mit dem Angebots-PDF, Fenster mit Auswahl Kunde/Intern/Komplett und Seiten, Menü der Angebotsübersicht,
- Seitenumbrüche bei vielen Positionen, nichts ragt aus dem Blatt.

Aufruf: python tests/test_angebotsakte.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pypdfium2 as pdfium  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_baugruppe as bsp  # noqa: E402
from rohrlaser import akte_ablage, akte_pdf, angebotsakte, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def seiten(pfad):
    """[(Text, Zeichen außerhalb des Blatts)] je Blatt."""
    out = []
    d = pdfium.PdfDocument(str(pfad))
    for i in range(len(d)):
        s = d[i]
        b, h = s.get_size()
        tp = s.get_textpage()
        aussen = 0
        for j in range(tp.count_chars()):
            if tp.get_text_range(j, 1).strip():
                x0, y0, x1, y1 = tp.get_charbox(j)
                aussen += x0 < 2 or x1 > b - 2 or y0 < 2 or y1 > h - 2
        out.append((" ".join(tp.get_text_range().split()), aussen))
    d.close()
    return out


app = QApplication.instance() or QApplication([])
STUFEN = dict(gewinn_bis_1=500, gewinn_satz_1=0.30, gewinn_bis_2=2000, gewinn_satz_2=0.20, gewinn_bis_3=10000,
              gewinn_satz_3=0.12, gewinn_satz_4=0.08)


def angebot(viele=0):
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "r.db")
    for n, w in dict(STUFEN, gaspreis_n2=0.9, ausschuss=0.02, schrott_anteil=0.10, pdf_vorschau="nein",
                     briefkopf_1="Muster Rohrtechnik GmbH (erfunden) · Werkstraße 12 · 48155 Münster",
                     briefkopf_2="Tel. 0251 123456 · info@muster-rohrtechnik.example",
                     briefkopf_3="Amtsgericht Münster HRB 1234 · USt-IdNr. DE123456789").items():
        db.einstellung_setzen(n, w)
    a = bsp.anlegen(db)
    for n, w in dict(fracht=60, fracht_modus="manuell", skonto=2, kundenreferenz="Gestell Linie 3").items():
        db.angebot_aendern(a, n, w)
    for p in (dict(pos=200, artikel="VA-1", bezeichnung="Halter Edelstahl", profil_id="RR 42,4x2,0",
                   werkstoff_id="1.4301", laenge=720, stueck=40, schneidweg=290, einstiche=2, gewinde="2xM8"),
              dict(pos=210, artikel="VA-2", bezeichnung="Muster", profil_id="RR 42,4x2,0", werkstoff_id="1.4301",
                   laenge=380, stueck=6, schneidweg=310, einstiche=4, muster="ja"),
              dict(pos=220, artikel="ST-3", bezeichnung="Stütze", profil_id="RE 60x40x3", werkstoff_id="S355-10219",
                   laenge=1795.5, stueck=16, schneidweg=618.2, einstiche=4)):
        db.position_neu(a, p)
    for i in range(viele):
        db.position_neu(a, dict(pos=300 + 10 * i, artikel=f"GR-{i:02d}", bezeichnung=f"Strebe {i}",
                                profil_id=("RE 60x40x3", "QR 40x40x3", "RR 42,4x2,0")[i % 3],
                                werkstoff_id=("S355-10219", "S235-10219", "1.4301")[i % 3], laenge=300 + 37 * i,
                                stueck=3 + i % 9, schneidweg=200 + 5 * i, einstiche=2 + i % 3))
    f = Hauptfenster(db, tmp, stumm=True)
    db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
    s = f.angebot_oeffnen(a)
    assert s.optimieren()
    return s, tmp


# ------------------------------------------------------------------ ein realistisches Angebot, komplett
s, tmp = angebot()
s.staffelpreise_rechnen()
zeilen, summen = s._rechnung()
verkauf = summen["verkauf"]
ang = s.angebot_daten(zeilen=zeilen)
bericht = s.angebotsdokument(art="gesamt", vorschau=False, oeffnen=False)
assert bericht and bericht["version"] == 1, bericht
assert abs(s._rechnung()[1]["verkauf"] - verkauf) < 1e-9, "die Akte ändert keine Rechnung"
o = bericht["ordner"]
assert o.name == "Angebotsakte" and o.parent == s.f.angebot_ordner(s.kopf)
for art in ("gesamt", "kunde", "intern", "schnittschema", "kalkulationsdaten"):
    assert bericht["dateien"][art].exists(), art
for u in ("PDF", "PDF/Versionen", "Technische_Daten", "Schnittschemata", "Kalkulationsdaten"):
    assert (o / u).is_dir(), u
assert (o / "Kalkulationsdaten" / "akte.json").exists()
pngs = list((o / "Technische_Daten").glob("*.png"))
assert len(pngs) >= 3, pngs       # Rohrteile ohne STEP: Bild aus dem Rohrmodell des 3D-Editors
assert bericht["dateien"]["gesamt"].name == f"Angebot_{s.kopf['nummer']}_Gesamt.pdf"
ok("Ablage: Angebotsakte im Angebotsordner mit PDF, Versionen, Technische_Daten, Schnittschemata, Kalkulationsdaten")

kunde = seiten(bericht["dateien"]["kunde"])
intern = seiten(bericht["dateien"]["intern"])
gesamt = seiten(bericht["dateien"]["gesamt"])
assert len(gesamt) == len(kunde) + len(intern), (len(gesamt), len(kunde), len(intern))
assert all(a == 0 for _, a in kunde + intern + gesamt), "nichts ragt aus dem Blatt"
kt = " ".join(t for t, _ in kunde)
for z in ang["zeilen"]:
    assert akte_pdf.geld(z["gesamt"]) in kt, z
for w in (akte_pdf.geld(ang["netto"]), akte_pdf.geld(ang["mwst"]), akte_pdf.geld(ang["brutto"]), "Netto-Zwischensumme",
          "Mehrwertsteuer 19 %", "Gesamtsumme brutto", "Lieferzeit", "Angebotsgültigkeit", "Zahlungsbedingungen",
          "Technische Bauteilübersicht", "Werkstoffgüte", "Wandstärke", "Bauteillänge", "Gestell Linie 3",
          f"Seite 1 von {len(kunde)}", s.kopf["nummer"]):
    assert w.lower() in kt.lower(), w
ok("Seite 1–2: Positionen, Netto, MwSt., Brutto, Konditionen, Technik, Seitenzahlen = Angebot")

assert akte_pdf.kunde_pruefen(bericht["dateien"]["kunde"]) == []
for intern_wert in ("97,60", "€/kg", "Selbstkosten", "INTERN", "Gewinn", "Einstand", akte_pdf.geld(summen["selbst"])):
    assert intern_wert not in kt, intern_wert
assert all(t.startswith("Seite") is False for t, _ in kunde)
ok("Kunden-PDF ohne interne Begriffe, Stundensätze, Einkaufspreise, Selbstkosten, Gewinn")

it = " ".join(t for t, _ in intern)
for w in ("INTERN", "Schnittschema und Materialausnutzung", "Materialkalkulation", "Fertigungskalkulation",
          "Zukauf- und Normteile", "Gesamtkalkulation", "Selbstkosten", "Deckungsbeitrag", "Gewinnmarge",
          "Maschinenlaufzeit", "Rüstzeit", "Programmierzeit", "Schneidzeit", "Stundensatz", "Materialhandling",
          "Lieferant", "Einkaufspreis", "Verschnitt", "Restmaterialwert", "Schraube M8x25", "Fremdfertigungsleistungen",
          "Prüfliste", "Kalkulationsstand", akte_pdf.geld(verkauf), akte_pdf.geld(summen["gewinn"]),
          akte_pdf.geld(summen["selbst"])):
    assert w.lower() in it.lower(), w
assert "Kundenangebot" not in intern[0][0]
ok("Seiten 3–7 mit INTERN-Leiste: Schnittschema, Material, Fertigung, Zukauf, Gesamtkalkulation, Prüfliste")

# Werte aus der einen Kalkulation
akte = s.akte_sammeln(bilder=False)
g = akte["gesamt"]
assert abs(sum(x["betrag"] for x in g["gruppen"]) - verkauf) < 1e-6
assert abs(g["selbst"] - summen["selbst"]) < 1e-9 and abs(g["gewinn"] - summen["gewinn"]) < 1e-9
assert abs(g["gewinn_basis"] - (summen["selbst"] - summen["zukauf_einstand"] - summen["zukauf_aufschlag"])) < 0.01
assert any(x["titel"].startswith("Aufschlag Zukaufteile") and x["stufe"] == 1 for x in g["gruppen"])
stufen = dict(angebotsakte.pruefen(akte, summen))
assert ("OK", "Alle Kostenpositionen ergeben den Verkaufspreis der Kalkulation") in angebotsakte.pruefen(akte, summen)
assert angebotsakte.schlimmste(akte["pruefung"]) in ("OK", "HINWEIS"), akte["pruefung"]
ok("Gesamtkalkulation = Kalkulation: Gruppen ergeben den Verkaufspreis, Gewinnbasis ohne Zukauf (nur Aufschlag)")

gew = [x for x in akte["fertigung"]["schritte"] if x["art"] == "Gewinde"]
assert gew and all(x["min"] is None for x in gew) and abs(sum(x["eur"] for x in gew) - summen["gewinde"]) < 1e-6
ok("Gewinde nur mit Preis je Stück, Summe = Kalkulation")

sch = akte["schnitt"]
anzeige = rechnen.anzeige_stangen(s.ergebnis)
assert sum(m["anzahl"] for gr in sch["gruppen"] for m in gr["muster"]) == len(anzeige)
assert sch["summe"]["lieferstangen"] == summen["stangen"]
for p in s.positionen:
    if p.get("profil_id") and p.get("art") is None:
        n = sum(1 for st in anzeige for t in st["teile"] if t["pos"] == p["pos"])
        nummern = [x for gr in sch["gruppen"] for m in gr["muster"] for x in m["teilnummern"].get(
            angebotsakte.pos_text(p["pos"]), [])]
        assert sorted(nummern) == list(range(1, n + 1)), (p["pos"], nummern, n)
for gr in sch["gruppen"]:
    for m in gr["muster"]:
        assert all(t["bis"] <= m["stange"] - m["greif"] + 0.01 for t in m["teile"]), "keine Stange überladen"
ok("Schnittschema = Schnittplan: Rohre, Teile je Position eindeutig nummeriert, keine Stange überladen")

# ------------------------------------------------------------------ Versionen, Stand, automatische Erneuerung
assert akte_ablage.stand(o, akte["fingerabdruck"]) == akte_ablage.AKTUELL
b2 = s.angebotsdokument(art="gesamt", vorschau=False, oeffnen=False)
assert b2["version"] == 2 and akte_ablage.versionen(o), "alte Fassung aufbewahrt"
alt = akte_ablage.versionen(o)
assert any("_Gesamt_V1_" in p.name for p in alt) and any("_Kunde_V1_" in p.name for p in alt), alt
v = akte_ablage.verzeichnis(o)["versionen"]
assert [e["version"] for e in v] == [1, 2] and v[-1]["fingerabdruck"] == akte["fingerabdruck"]
assert (o / "Kalkulationsdaten" / "kalkulation_V2.json").exists()
daten = json.loads((o / "Kalkulationsdaten" / "kalkulation_V2.json").read_text(encoding="utf-8"))
assert abs(daten["gesamt"]["verkauf"] - verkauf) < 1e-9 and "bild" not in json.dumps(daten)
ok("Neu erzeugen: Version 2, Version 1 unter PDF/Versionen, akte.json mit Fingerabdruck, Kalkulationsdaten je Version")

pos = next(p for p in s.positionen if p.get("pos") == 220)
s.db.position_aendern(pos["id"], "stueck", 20) if hasattr(s.db, "position_aendern") else s.db.aendern(
    "positionen", pos["id"], "stueck", 20)
s.neu_laden()
assert s.optimieren()
neu = s.akte_sammeln(bilder=False)
assert neu["fingerabdruck"] != akte["fingerabdruck"]
assert akte_ablage.stand(o, neu["fingerabdruck"]) == akte_ablage.VERALTET
ziel = tmp / "angebot.pdf"
s._ziel = lambda *a, **kw: ziel
assert s.angebot_pdf(oeffnen=False)
assert akte_ablage.letzte(o)["version"] == 3 and akte_ablage.stand(o, neu["fingerabdruck"]) == akte_ablage.AKTUELL
assert s.angebot_pdf(oeffnen=False) and akte_ablage.letzte(o)["version"] == 3, "unverändert: keine neue Version"
s.db.einstellung_setzen("akte_automatisch", "nein")
ok("Stückzahl geändert: Akte veraltet; Angebots-PDF erneuert die Akte automatisch (nur bei Änderung)")

# ------------------------------------------------------------------ Fenster: Auswahl und Seiten
from rohrlaser.akte_dialog import AkteDialog  # noqa: E402


def waehlen(d):
    assert d.knoepfe["gesamt"].isChecked() and d.liste.count() >= 3
    d.knoepfe["kunde"].setChecked(True)
    assert not d.haken[3].isEnabled() and d.haken[1].isEnabled()
    d.haken[2].setChecked(False)
    d.vorschau.setChecked(False)
    assert d.seiten == [1] and d.art == "kunde"
    return True


b4 = s.angebotsdokument(dialog=waehlen, oeffnen=False)
assert b4 and set(b4["dateien"]) >= {"kunde"} and "intern" not in b4["dateien"]
assert akte_ablage.letzte(o)["seiten"] == {"kunde": [1]}
assert "Technische Bauteilübersicht" not in " ".join(t for t, _ in seiten(b4["dateien"]["kunde"]))
d = AkteDialog(None, neu)
d.knoepfe["intern"].setChecked(True)
assert not d.haken[1].isEnabled() and d.seiten == [3, 4, 5, 6, 7]
for h in d.haken.values():
    h.setChecked(False)
assert not d.ok.isEnabled(), "ohne Seite kein Erstellen"
ok("Fenster: Kundenangebot / Intern / Komplett, Seiten wählbar, Prüfliste, Vorschau abwählbar")

# Vorschau: Abbrechen speichert nichts, Speichern legt ab
from rohrlaser import pdf_vorschau  # noqa: E402


def abbrechen(d):
    assert d.bilder
    d.ergebnis = pdf_vorschau.ABBRECHEN


vorher = akte_ablage.letzte(o)["version"]
assert s.akte_erzeugen(neu, "intern", vorschau=True, vorschau_dialog=abbrechen) is None
assert akte_ablage.letzte(o)["version"] == vorher


def speichern(d):
    d.ergebnis = pdf_vorschau.SPEICHERN


assert s.akte_erzeugen(neu, "intern", vorschau=True, vorschau_dialog=speichern)["version"] == vorher + 1
ok("Vorschau vor dem Speichern: Abbrechen legt nichts ab, Speichern legt die nächste Version ab")

# Angebotsübersicht: Untermenü Angebotsakte
s.f.angebote.neu_laden()
liste = s.f.angebote
zeile = next(r for r in range(liste.filter.rowCount()) if liste._id(liste.filter.index(r, 0)) == s.id)
liste.ansicht.selectRow(zeile)
menue = liste.kontextmenue(zeigen=False)
unter = next(a.menu() for a in menue.actions() if a.menu() and a.text().startswith("Angebotsakte"))
texte = [a.text() for a in unter.actions() if a.text()]
for t in ("Komplettes Dokument öffnen", "Kundenangebot öffnen", "Interne Kalkulation öffnen", "Drucken …",
          "Erstellen / neu erzeugen …", "Ordner der Akte öffnen"):
    assert t in texte, (t, texte)
assert all(a.isEnabled() for a in unter.actions() if a.text() in ("Kundenangebot öffnen", "Interne Kalkulation öffnen"))
ok("Angebotsübersicht: Akte öffnen (komplett, Kunde, intern), drucken, neu erzeugen, Ordner")

# ------------------------------------------------------------------ großes Angebot: Seitenumbrüche, Lesbarkeit
s2, tmp2 = angebot(viele=60)
b5 = s2.angebotsdokument(art="gesamt", vorschau=False, oeffnen=False)
g5 = seiten(b5["dateien"]["gesamt"])
k5 = seiten(b5["dateien"]["kunde"])
assert len(g5) >= 12 and all(a == 0 for _, a in g5), (len(g5), [a for _, a in g5])
gt = " ".join(t for t, _ in g5)
for i in range(60):
    assert f"GR-{i:02d}" in gt, i
assert all(f"Seite {i} von {len(k5)}" in t for i, (t, _) in enumerate(k5, start=1))
assert all(f"Seite {i} von {len(g5)}" in t for i, (t, _) in enumerate(g5, start=1))
assert all(s2.kopf["nummer"] in t for t, _ in g5), "Angebotsnummer auf jedem Blatt"
assert akte_pdf.kunde_pruefen(b5["dateien"]["kunde"]) == []
ok(f"60 Positionen: {len(g5)} Blätter, jede Position, Seitenzahlen und Angebotsnummer auf jedem Blatt, nichts abgeschnitten")

assert akte_pdf.plex_geladen(), "Schrift IBM Plex aus programm/rohrlaser/schriften"
print("OK: Angebotsakte")
