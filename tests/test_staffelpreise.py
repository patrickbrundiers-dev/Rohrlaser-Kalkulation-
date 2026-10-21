"""Prüft die Staffelpreise mit Werten je Stufe (Testplan 1–12 und Regression).

Preisschicht (staffeln.preise) mit von Hand nachgerechneten Bausteinen, Mengenlauf mit echten Angeboten
(Beispielangebot, Abnahmeangebote), Reiter 'Staffeln' (sofortige Neuberechnung, Fehleranzeige, Hintergrundlauf)
und eine Datendatei der Vorversion (Schema 13) mit gespeicherten Staffelpreisen.

Aufruf: python tests/test_staffelpreise.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from abnahme_angebote import ANGEBOTE  # noqa: E402
from rohrlaser import ausgabe, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

EPS = 1e-9


def ok(text):
    print("OK    ", text)


def nah(a, b, eps=EPS):
    return abs(a - b) < eps


def bausteine(material=0.0, fertigung=0.0, ruesten=0.0, fremd=0.0, skonto=0.0, satz=60.0, fehlt=0, **weitere):
    """Bausteine eines Mengenlaufs von Hand (Beträge für die ganze Stufe)."""
    return dict(material=material, material_fehlt=fehlt, fertigung=[("Laser schneiden", fertigung, "")] if fertigung else [],
                ruesten=[("Rüsten Maschine", ruesten, "")] if ruesten else [], fremd=fremd,
                pauschalen=weitere.get("pauschalen", 0.0), programmierung=weitere.get("programmierung", 0.0),
                angebotsaufschlag=weitere.get("angebotsaufschlag", 0.0), fracht=weitere.get("fracht", 0.0),
                skonto_satz=skonto, satz_maschine=satz, verkauf=None)


NULL = dict(zuschlag_material=0, zuschlag_fertigung=0, zuschlag_fremdleistung=0, gewinn=0, mwst=0.19)


def preis(b, menge, stufe=None, einst=None):
    return staffeln.preise(b, menge, staffeln.wirksam(stufe or {}, dict(NULL, **(einst or {}))))


# 1) Eine Stufe ohne Zuschläge: 10 Stück, Material 120 €, Fertigung 50 €, Rüsten 30 €
p = preis(bausteine(120, 50, 30), 10)
assert nah(p["selbst"], 200) and nah(p["netto"], 200) and p["preis_einheit"] == 20.0 and p["preis_gesamt"] == 200.0
assert p["mwst"] == 38.0 and p["brutto"] == 238.0 and nah(p["gewinn"], 0) and nah(p["m_zuschlag"], 0)
ok("1  eine Stufe ohne Zuschläge: 200,00 € netto, 38,00 € MwSt, 238,00 € brutto")

# 2) + 3) Mehrere Stufen mit unterschiedlichen prozentualen Materialzuschlägen (Beispiel aus dem Auftrag)
for menge, zuschlag, soll in ((10, 20, 14.40), (50, 15, 13.80), (100, 10, 13.20), (500, 5, 12.60)):
    p = preis(bausteine(12.0 * menge), menge, dict(mat_zuschlag=zuschlag, mat_art=staffeln.PROZENT))
    assert p["preis_einheit"] == soll and nah(p["m_gesamt"] / menge, soll) and nah(p["m_zuschlag"], 12 * menge * zuschlag / 100)
    assert p["preis_gesamt"] == round(soll * menge, 2)
ok("2  mehrere Stufen: 12,00 € Grundpreis mit 20/15/10/5 % = 14,40/13,80/13,20/12,60 € je Stück")
# leer = Zuschlag Material des Angebots; der Stufenwert ersetzt ihn (nicht zusätzlich)
p = preis(bausteine(120), 10, einst=dict(zuschlag_material=0.10))
assert p["preis_einheit"] == 13.20
p = preis(bausteine(120), 10, dict(mat_zuschlag=20), einst=dict(zuschlag_material=0.10))
assert p["preis_einheit"] == 14.40
ok("3  prozentualer Zuschlag: Stufenwert ersetzt den Zuschlag Material des Angebots (10 % -> 20 %, nicht 30 %)")

# 4) Absoluter Zuschlag in € je Einheit, Rabatt nur ausdrücklich
p = preis(bausteine(120), 10, dict(mat_zuschlag=1.5, mat_art=staffeln.EURO))
assert p["preis_einheit"] == 13.50 and nah(p["m_zuschlag"], 15)
p = preis(bausteine(120), 10, dict(mat_zuschlag=-2, mat_art=staffeln.EURO, rabatt="ja"))
assert p["preis_einheit"] == 10.00
assert staffeln.fehler(dict(schluessel="10", menge=10, mat_zuschlag=-2, mat_art=staffeln.EURO), [dict(pos=10)])
assert preis(bausteine(120), 10, dict(mat_zuschlag=-13, mat_art=staffeln.EURO, rabatt="ja"))["fehler"]
ok("4  absoluter Zuschlag: 12,00 + 1,50 € = 13,50 €; Rabatt −2,00 € nur mit 'Rabatt erlaubt'; Rabatt > Material = Fehler")

# 5) Materialverlust: erst Verlust auf den Grundpreis, dann Zuschlag auf Material nach Verlust
p = preis(bausteine(120), 10, dict(verlust=5, mat_zuschlag=10))
assert nah(p["m_verlust"], 6) and nah(p["m_zuschlag"], 12.6) and p["preis_einheit"] == 13.86
p = preis(bausteine(120), 10, dict(mat_grundpreis=15, verlust=10))          # Grundpreis abweichend je Einheit
assert nah(p["m_grund"], 150) and p["preis_einheit"] == 16.50
ok("5  Materialverlust 5 % + Zuschlag 10 %: 12,00 -> 12,60 -> 13,86 €; Grundpreis abweichend 15,00 € + 10 % = 16,50 €")

# 6) Bearbeitungszeiten und Stundensätze: zusätzlicher Arbeitsgang mit Zeit × Stundensatz bzw. Maschinensatz
p = preis(bausteine(0, 0, satz=90), 20, dict(arbeitsgang="Entgraten", arbeitsgang_min=3))
assert nah(p["fert_gesamt"], 3 * 20 / 60 * 90) and p["preis_einheit"] == 4.50
p = preis(bausteine(0, 0, satz=90), 20, dict(arbeitsgang="Entgraten", arbeitsgang_min=3, arbeitsgang_satz=48,
                                              arbeitsgang_eur=0.25))
assert nah(p["fert_gesamt"], 3 * 20 / 60 * 48 + 0.25 * 20) and p["preis_einheit"] == 2.65
assert p["fertigung"][-1][0] == "Entgraten"
ok("6  Arbeitsgang 3 min je Stück: 90 €/h = 4,50 €, 48 €/h + 0,25 € = 2,65 € je Stück")

# 7) Rüstkosten bei kleinen und großen Stückzahlen, umgelegt oder separat
klein, gross = preis(bausteine(0, 0, 60), 10), preis(bausteine(0, 0, 60), 1000)
assert klein["preis_einheit"] == 6.00 and gross["preis_einheit"] == 0.06
p = preis(bausteine(100, 0, 60), 10, dict(ruesten=staffeln.SEPARAT, gewinn=10, zuschlag_fertigung=20))
assert p["einmalig"] == round(60 * 1.2 * 1.1, 2) and p["preis_einheit"] == 11.00
assert p["preis_gesamt"] == round(110 + 79.2, 2) and nah(p["netto"], 189.2)
ok("7  Rüsten 60 €: 6,00 € bei 10 Stück, 0,06 € bei 1.000 Stück; separat 79,20 € einmalig, Stückpreis ohne Rüsten")

# 8) Gewinn, Netto, Brutto, Marge; Gemeinkosten nur auf Fertigung und Rüsten, nicht auf Material
p = preis(bausteine(100, 40, 10), 10, dict(gewinn=25, zuschlag_fertigung=10))
assert nah(p["gk_fertigung"], 5) and nah(p["selbst"], 155) and nah(p["gewinn"], 38.75)
assert p["preis_einheit"] == 19.38 and p["preis_gesamt"] == 193.80 and p["mwst"] == 36.82 and p["brutto"] == 230.62
assert nah(p["marge"], 38.75 / 193.75)
p = preis(bausteine(100, skonto=2), 10, dict(gewinn=25))
assert nah(p["netto"], 125 / 0.98) and p["preis_einheit"] == 12.76
ok("8  Selbstkosten 155 € + 25 % Gewinn = 193,75 € netto (19,38 €/Stk), MwSt 36,82 €, brutto 230,62 €; Skonto eingerechnet")

# 10) Fehlerhafte oder unvollständige Eingaben (Prüfung je Stufe)
pos = [dict(pos=10, profil_id="X"), dict(pos=20, profil_id="X", satz="R", je_satz=2)]
stufen = [dict(id=1, schluessel="10", menge=10), dict(id=2, schluessel="10", menge=10),
          dict(id=3, schluessel="10", menge=50, bis=40), dict(id=4, schluessel="R", menge=5, bis=20),
          dict(id=5, schluessel="R", menge=10), dict(id=6, schluessel="99", menge=3), dict(id=7, schluessel="10")]
fehl = {s["id"]: [t for _, t in staffeln.fehler(s, pos, stufen)] for s in stufen}
assert "Menge doppelt" in fehl[1] and "Menge doppelt" in fehl[2]
assert "Menge bis kleiner als Menge ab" in fehl[3]
assert any("überschneidet" in t for t in fehl[4]) and any("überschneidet" in t for t in fehl[5])
assert "Satz/Pos. nicht im Angebot" in fehl[6] and fehl[7] == ["Menge fehlt"]
assert staffeln.pruefen(stufen[6], pos, stufen) == "FEHLER: Menge fehlt"
assert staffeln.bis_wirksam(dict(schluessel="R", menge=5), [dict(schluessel="R", menge=5), dict(schluessel="R", menge=25)]) == 24
assert staffeln.fehler(dict(schluessel="10", menge=10, mat_zuschlag=600), pos)            # % über 500
assert staffeln.fehler(dict(schluessel="10", menge=10, gewinn=-5), pos)                     # ohne Rabatt
assert not staffeln.fehler(dict(schluessel="10", menge=10, gewinn=-5, rabatt="ja"), pos)
assert staffeln.fehler(dict(schluessel="10", menge=10, verlust=-1), pos)                    # aus geänderter Datei
assert preis(bausteine(0, 10, fehlt=1), 10)["fehler"].startswith("Materialpreis fehlt")
assert preis(bausteine(0, 10, fehlt=1), 10, dict(mat_grundpreis=4))["preis_einheit"] == 5.00
z = staffeln.preise_anwenden(dict(schluessel="10", menge=10, bausteine=bausteine(0, 10, fehlt=1), hinweis=None),
                             dict(schluessel="10", menge=10), NULL, [], pos)
assert z["preis_einheit"] is None and z["hinweis"].startswith("FEHLER: Materialpreis fehlt")
assert ausgabe.angebot({}, [], [], None, dict(mwst=0.19), [z])["staffeln"] == []          # nicht ins Angebot
ok("10 Eingabefehler: doppelte Menge, bis < ab, Überschneidung, unbekannter Satz, Menge fehlt, Prozent außerhalb, "
   "Materialpreis fehlt -> kein Preis, nicht im Angebot")

# 12) Rundung: intern ungerundet, Stückpreis kaufmännisch auf Cent, Gesamt = Stückpreis × Menge
p = preis(bausteine(0.034 * 1000), 1000, dict(mat_zuschlag=10))
assert nah(p["netto"], 37.4) and p["preis_einheit"] == 0.04 and p["preis_gesamt"] == 40.0
p = preis(bausteine(0.1 * 3 + 0.2 * 3), 3)               # 0,1 + 0,2 ohne Fließkommarest
assert p["preis_einheit"] == 0.30 and p["preis_gesamt"] == 0.90
p = preis(bausteine(2.675 * 100), 100)
assert p["preis_einheit"] == 2.68 and p["preis_gesamt"] == 268.0
p = preis(bausteine(0.0049 * 7), 7, dict(mat_zuschlag=0))
assert p["preis_einheit"] == 0.0 and p["preis_gesamt"] == 0.0
ok("12 Rundung: 0,0374 € -> 0,04 €, 2,675 € -> 2,68 € (kaufmännisch), Gesamt = gerundeter Stückpreis × Menge")

# ------------------------------------------------------------------ mit Datenbank und Oberfläche
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
a = beispiel_angebot.anlegen(db)
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
sp = s.staffelpreise_rechnen()
assert len(sp) == 6 and all(z["preis_einheit"] for z in sp)

# Regression: ohne Werte je Stufe = Verkaufspreis der Kalkulation (vorherige Rechnung)
for z in sp:
    assert nah(z["preis"]["netto"], z["bausteine"]["verkauf"], 1e-6) and \
        z["preis_einheit"] == ausgabe.kaufm_runden(z["bausteine"]["verkauf"] / z["menge"], 2)
ok("Regression Beispielangebot: 6 Stufen ohne Stufenwerte = bisheriger Verkaufspreis")

# 6) Arbeitsschritte aus dem Reiter 'Zeiten & Arbeitskosten': Summe Fertigung + Rüsten = Zeiten × Stundensätze
z = sp[3]
lauf = [dict(p_, stueck=z["menge"] if str(p_["pos"]) == "10" else None) for p_ in s.positionen]
_, summen = rechnen.kalkulation(s.kopf, lauf, rechnen.optimieren(s.kopf, lauf, s.k), s.k, s.tabellen, s.einst)
zeit_kosten = sum(x["kosten"] for x in summen["zeiten"] if x["schritt"] not in ("Programmierung", "Zusatzarbeiten (€)"))
assert nah(z["preis"]["fert_gesamt"] + z["preis"]["ruest_gesamt"], zeit_kosten + summen["zusatz_eigen"], 1e-6)
assert {n for n, _, _ in z["preis"]["ruesten"]} >= {"Rüsten Maschine"}
ok("6  Fertigung und Rüsten je Stufe = Zeit × Stundensatz der Arbeitsschritte (Rüstzeit getrennt von Stückzeit)")

# 9) Änderung eines Zuschlags: sofort neue Preise, kein neuer Mengenlauf
st = s.st_seite
m = st.modell
spalte = [f.name for f in staffeln.STUFE_FELDER].index
am = s.kopf["staffelpreise"]["am"]
vorher = st.zeilen[3]["preis_einheit"]
assert m.setData(m.index(3, spalte("mat_zuschlag")), "40")
assert db.staffeln(a)[3]["mat_zuschlag"] == 40
nachher = st.zeilen[3]["preis_einheit"]
assert nachher > vorher and s.kopf["staffelpreise"]["am"] == am and st.anzahl_veraltet() == 0
assert db.angebot(a)["staffelpreise"]["zeilen"][3]["preis_einheit"] == nachher          # gleich gespeichert
assert st.zeilen[0]["preis_einheit"] == sp[0]["preis_einheit"]                        # andere Stufen unverändert
assert st.baum.zeile("aenderung").text(1 + 2 * 3).startswith("+")
assert "aktuell" in s.staffel_info.text()
assert st.baum.zeile("m_zuschlag") is not None and st.baum.zeile("brutto") is not None
assert m.data(m.index(3, spalte("mat_zuschlag"))) == "40,00 %"
assert m.data(m.index(4, spalte("mat_zuschlag"))).endswith("(Einstellungen)")    # leer = Wert der Einstellungen
assert m.setData(m.index(3, spalte("mat_art")), staffeln.EURO) and m.data(m.index(3, spalte("mat_zuschlag"))) == "40,00 €/Einheit"
assert not m.setData(m.index(3, spalte("gewinn")), "-5")                          # ohne Rabatt abgelehnt
assert not m.setData(m.index(3, spalte("mat_zuschlag")), "abc")
assert m.setData(m.index(3, spalte("mat_zuschlag")), "")                          # wieder Angebotswert
assert m.setData(m.index(3, spalte("mat_art")), "")
assert st.zeilen[3]["preis_einheit"] == vorher
ok("9  Zuschlag geändert: Preis sofort neu und gespeichert, ohne neuen Mengenlauf; andere Stufen unverändert")

# Erweiterte Einstellungen: ausgeblendet, bis eine Stufe einen Wert hat oder das Häkchen gesetzt ist
assert st.ansicht.isColumnHidden(spalte("verlust")) and not st.ansicht.isColumnHidden(spalte("gewinn"))
st.erweitert.setChecked(True)
assert not st.ansicht.isColumnHidden(spalte("verlust"))
st.erweitert.setChecked(False)
assert m.setData(m.index(0, spalte("neben_einheit")), "2,5")
assert not st.ansicht.isColumnHidden(spalte("neben_einheit")) and st.ansicht.isColumnHidden(spalte("verlust"))
assert nah(st.zeilen[0]["preis"]["neben"], 2.5 * st.zeilen[0]["menge"])
ok("Erweiterte Einstellungen nur mit Häkchen oder Wert sichtbar; Nebenkosten je Einheit wirken sofort")

# Menge geändert: Stufe veraltet, Hintergrundlauf rechnet nur sie neu
assert m.setData(m.index(5, spalte("menge")), "200")
assert st.anzahl_veraltet() == 1 and "VERALTET" in s.staffel_info.text()
assert st.zeilen[5]["preis_einheit"] is None and st.zeilen[0]["preis_einheit"]
st._hintergrund_starten()
assert st.warten() and st.anzahl_veraltet() == 0 and "aktuell" in s.staffel_info.text()
assert st.zeilen[5]["menge"] == 200 and st.zeilen[5]["preis_einheit"] < sp[5]["preis_einheit"]
ok("Menge geändert: nur diese Stufe wird im Hintergrund neu gerechnet")

# Fehlerhafte Eingaben im Reiter: rot markiert, ohne Preis, nicht im Angebot
assert m.setData(m.index(4, spalte("menge")), "24")              # gleiche Menge wie Stufe 4
assert m.data(m.index(4, len(staffeln.STUFE_FELDER))).startswith("FEHLER: Menge doppelt")
ang = s.angebot_daten()
assert [x["menge"] for x in ang["staffeln"] if x["pos"] == "10"] == [200]      # beide doppelten Stufen fehlen
assert m.setData(m.index(4, spalte("menge")), "50")
ang = s.angebot_daten()
assert [x["bereich"] for x in ang["staffeln"]] == ["ab 2", "ab 4", "ab 8", "ab 24", "ab 50", "ab 200"], ang["staffeln"]
# jede Stufe steht unter ihrer Angebotszeile (Satz bzw. Pos.), aufsteigend nach Menge; Summe nur aus den Hauptzeilen
unter = [st for z in ang["zeilen"] for st in z["staffeln"]]
assert all(st["zugeordnet"] for st in ang["staffeln"]) and sorted(map(id, unter)) == sorted(map(id, ang["staffeln"]))
for z in ang["zeilen"]:
    assert [st["menge"] for st in z["staffeln"]] == sorted(st["menge"] for st in z["staffeln"])
    assert all((st["art"] == "satz") == (z["art"] == "satz") for st in z["staffeln"])
assert ang["netto"] == round(sum(z["gesamt"] for z in ang["zeilen"] if z["gesamt"] is not None), 2)
ok("Doppelte Menge rot markiert und nicht im Angebot; Stufen im Angebot 'ab 2, ab 4, ab 8 …' unter ihrer Position")

# Rüstkosten separat: im Angebot als einmalige Rüstkosten
assert m.setData(m.index(0, spalte("ruesten")), staffeln.SEPARAT)
z0 = st.zeilen[0]
assert z0["preis"]["einmalig"] > 0 and z0["preis_gesamt"] == round(z0["preis_einheit"] * z0["menge"] + z0["preis"]["einmalig"], 2)
ang = s.angebot_daten()
a0 = next(x for x in ang["staffeln"] if x["menge"] == z0["menge"] and x["art"] == ("satz" if z0["einheit"] == "Satz" else "teil"))
assert "Rüstkosten" not in a0["text"] and a0["preis"] > z0["preis_einheit"]
assert a0["preis"] * z0["menge"] >= z0["preis_gesamt"] - 1e-9 and a0["gesamt"] == round(a0["preis"] * z0["menge"], 2)
assert s.angebot_pdf()
ok("Rüstkosten separat: im Angebots-PDF im Stufenpreis enthalten, keine extra Kosten")

# Firmenlogo: Bilddatei -> Base64-PNG in der Einstellung, im PDF eingepasst; beschädigte Daten = ohne Logo
from PySide6.QtGui import QImage  # noqa: E402
from rohrlaser import pdf  # noqa: E402
from rohrlaser.fenster import logo_aus_datei  # noqa: E402
bild = QImage(3000, 1000, QImage.Format_ARGB32)
bild.fill(0xFF1F4E78)
bild.save(str(tmp / "logo.jpg"))
logo = logo_aus_datei(tmp / "logo.jpg")
lb = pdf.logo_bild(dict(logo=logo))
assert lb is not None and abs(lb.drawWidth - 55 * pdf.mm) < 0.01 and lb.drawHeight <= 24 * pdf.mm + 0.01
assert pdf.logo_bild(dict(logo="kein Bild")) is None and pdf.logo_bild({}) is None
(tmp / "kaputt.png").write_text("x")
try:
    logo_aus_datei(tmp / "kaputt.png")
    raise AssertionError("kaputtes Bild angenommen")
except ValueError:
    pass
db.einstellung_setzen("logo", logo)
s.einst = dict(s.einst, logo=logo)
pfad = s.angebot_pdf()
assert pfad and pfad.stat().st_size > 2000
s.einst = dict(s.einst, logo="beschädigt")
assert s.angebot_pdf()
ok("Firmenlogo: auf 55 × 24 mm eingepasst, kein Bild = Fehlermeldung, beschädigte Einstellung = Angebot ohne Logo")
fenster.close()
db.schliessen()

# 11) Datendatei der Vorversion (Schema 13) mit gespeicherten Staffelpreisen
alt = tmp / "alt" / "rohrlaser.db"
d = Datenbank(alt)
a = beispiel_angebot.anlegen(d)
d.schliessen()
con = sqlite3.connect(alt)
for f in staffeln.STUFE_FELDER:
    if f.name not in ("schluessel", "menge", "bemerkung"):
        con.execute(f'ALTER TABLE staffeln DROP COLUMN "{f.name}"')
con.execute("UPDATE angebote SET staffelpreise=? WHERE id=?",
            (json.dumps(dict(zeilen=[dict(schluessel="Rahmen", menge=2, preis_einheit=1.0)], kennung="alt",
                             am="2026-10-01T10:00:00")), a))
con.execute("PRAGMA user_version=13")
con.commit()
con.close()
d = Datenbank(alt)
assert d.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
sicherung = list((alt.parent / "Sicherung").glob(f"*vor_Schema_{SCHEMA_VERSION}.db"))
assert len(sicherung) == 1
alt_con = sqlite3.connect(sicherung[0])
assert alt_con.execute("PRAGMA user_version").fetchone()[0] == 13 and alt_con.execute(
    "SELECT COUNT(*) FROM staffeln").fetchone()[0] == 6
alt_con.close()
assert all(x["mat_zuschlag"] is None and x["gewinn"] is None for x in d.staffeln(a))
fenster = Hauptfenster(d, tmp / "alt", stumm=True)
s = fenster.angebot_oeffnen(a)
assert s.st_seite.anzahl_veraltet() == 6 and "VERALTET" in s.staffel_info.text()
assert s.optimieren()
neu = s.staffelpreise_aktuell()
for z in neu:
    assert z["preis_einheit"] == ausgabe.kaufm_runden(z["bausteine"]["verkauf"] / z["menge"], 2)
fenster.close()
d.schliessen()
ok("11 Datei Schema 13: Sicherung vor der Umstellung, neue Felder leer, alte Staffelpreise veraltet und mit "
   "unveränderter Rechnung neu gerechnet")

# Regression Abnahmeangebote: jede Position als Stufe (ihre Stückzahl) = Verkaufspreis der Kalkulation
db = Datenbank(tmp / "abn" / "rohrlaser.db")
k, tab = db.kontext(), db.tabellen()
for an in ANGEBOTE:
    kopf = dict(maschine=an["maschine"], stange=an["stange"])
    positionen = [dict(pos=p_["pos"], artikel=p_["artikel"], bezeichnung=p_["bezeichnung"], profil_id=p_["profil"],
                       werkstoff_id=p_["werkstoff"], laenge=p_["laenge"], stueck=p_["stueck"],
                       **{n: p_[n] for n in ("schneidweg", "einstiche", "stange", "a_gerade", "b_gerade") if n in p_})
                  for p_ in an["positionen"]]
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    stufen = [dict(schluessel=str(p_["pos"]), menge=p_["stueck"]) for p_ in positionen[:2]]
    for z in staffeln.rechnen_alle(kopf, positionen, stufen, k, tab, einst):
        if z["preis"]:
            assert nah(z["preis"]["netto"], z["bausteine"]["verkauf"], 1e-6), (an["nummer"], z["schluessel"])
db.schliessen()
ok(f"Regression {len(ANGEBOTE)} Abnahmeangebote: Staffelpreis ohne Stufenwerte = Verkaufspreis der Kalkulation")
print("OK: Staffelpreise mit Werten je Stufe")
