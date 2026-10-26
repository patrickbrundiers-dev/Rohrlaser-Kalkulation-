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

# 9) Änderung eines Werts der Stufe: sofort neue Preise, kein neuer Mengenlauf
from PySide6.QtCore import Qt  # noqa: E402
from rohrlaser.staffel_seite import StufeDialog, angebotspreise  # noqa: E402
st = s.st_seite
m = st.modell
assert m.rowCount() == 6 and m.data(m.index(0, 2)) == "Satz Rahmen: 2"     # alte Aufrufe: je Menge eine Stufe
am = s.kopf["staffelpreise"]["am"]
vorher = st.zeilen[3]["preis_einheit"]


def speichern(zeile, mengen=None, preise=None, **werte):
    """Stufe der Zeile wie über ihr Fenster speichern (Werte, die fehlen, bleiben wie sie sind)."""
    stufe = m.daten[zeile]
    alt = {f.name: stufe.get(f.name) for f in staffeln.EINSTELLUNG_FELDER if f.name != "meterpreise"}
    if mengen is None:
        mengen = [(staffeln.txt(z["schluessel"]), z["menge"], z.get("bis")) for z in s.stufen
                  if z.get("stufe_id") == stufe["id"]]
    st.stufe_speichern(stufe["id"], dict(alt, **werte),
                       staffeln.meterpreise(stufe) if preise is None else preise, mengen)


speichern(3, mat_zuschlag=40)
assert db.staffel_stufen(a)[3]["mat_zuschlag"] == 40
nachher = st.zeilen[3]["preis_einheit"]
assert nachher > vorher and s.kopf["staffelpreise"]["am"] == am and st.anzahl_veraltet() == 0
assert db.angebot(a)["staffelpreise"]["zeilen"][3]["preis_einheit"] == nachher          # gleich gespeichert
assert st.zeilen[0]["preis_einheit"] == sp[0]["preis_einheit"]                        # andere Stufen unverändert
assert st.baum.zeile("aenderung").text(1 + 2 * 3).startswith("+")
assert "aktuell" in s.staffel_info.text() and "Materialzuschlag 40,00 %" in m.data(m.index(3, 3))
assert st.baum.zeile("m_zuschlag") is not None and st.baum.zeile("brutto") is not None
speichern(3, mat_zuschlag=None)
assert st.zeilen[3]["preis_einheit"] == vorher and m.data(m.index(3, 3)) == "wie Angebot"
ok("9  Wert der Stufe geändert: Preis sofort neu und gespeichert, ohne neuen Mengenlauf; andere Stufen unverändert")

# Fenster der Stufe: Felder wie im Angebot, leer = grau der Wert des Angebots; Prüfung der Eingaben
d = StufeDialog(st, m.daten[3])
assert d.felder["gewinn"].placeholderText().endswith("(Angebot)") and d.felder["gewinn"].text() == ""
assert {"gewinn", "zuschlag_fremdleistung", "ruesten_abmessung", "pauschale_abmessung", "programmierung_zeit",
        "programmierung_teil", "angebotsaufschlag", "handling_beistellung", "fracht", "skonto", "verlust", "neben_einheit"} <= set(d.felder)
assert d.mengen.rowCount() == len(staffeln.auswahl(s.positionen)) and d.preise.rowCount() >= 1
d.felder["gewinn"].setText("-5")
try:
    d.werte()
    raise AssertionError("negativer Gewinn ohne Rabatt angenommen")
except ValueError:
    pass
d.felder["gewinn"].setText("12,5")
d.felder["neben_einheit"].setText("2,5")
# Häkchen je Satz bzw. Position: bestehende Stufe = ihre Mengenzeilen angehakt
aw = staffeln.auswahl(s.positionen)
assert [d.drin(r) for r in range(len(aw))] == [any(staffeln.txt(z["schluessel"]) == schl and z.get("stufe_id") ==
                                                   m.daten[3]["id"] for z in s.stufen) for schl, _, _ in aw]
d.alle_haken(True)
d.mengen_aus_angebot(2)
for r, (_, _, menge) in enumerate(aw):
    if not menge:                     # ohne Menge im Angebot: angehakt und leer -> Fehler, also abhaken
        try:
            d.werte()
            raise AssertionError("angehakt ohne Menge angenommen")
        except ValueError as e:
            assert "Häkchen" in str(e)
        d.mengen.item(r, 0).setCheckState(Qt.Unchecked)
werte, preise, mengen = d.werte()
assert werte["gewinn"] == 12.5 and len(mengen) == len([x for x in aw if x[2]])
d.mengen.item(0, 0).setCheckState(Qt.Unchecked)          # abgehakt: Menge zählt nicht
assert [x[0] for x in d.werte()[2]] == [x[0] for x in aw[1:] if x[2]]
d.mengen.item(0, 2).setText("7")                          # Menge eintragen hakt an
assert d.drin(0) and d.werte()[2][0][:2] == (aw[0][0], 7)
d.alle_haken(False)
try:
    d.werte()
    raise AssertionError("Stufe ohne Position angenommen")
except ValueError:
    pass
d.reject()
d = StufeDialog(st, m.daten[3], neu=True)                 # neue Stufe: anfangs alle angehakt
assert all(d.drin(r) for r in range(d.mengen.rowCount()))
d.reject()
speichern(0, neben_einheit=2.5)
assert nah(st.zeilen[0]["preis"]["neben"], 2.5 * st.zeilen[0]["menge"])
ok("Fenster der Stufe: Einstellungen wie im Angebot (leer = grau), Rabattprüfung, Häkchen je Satz/Pos. "
   "(neu: alle), Mengen = Angebot × 2; "
   "Nebenkosten je Einheit wirken sofort")

# Schnittschema je Staffel (Patrick 26.10.2026): je Stufe der Schnittplan, je Abmessung Stangen, Meter, €/m, Kosten
from rohrlaser.staffel_seite import stufen_der_zeilen  # noqa: E402
assert st.anzahl_veraltet() == 0
for z in st.zeilen:
    sch = staffeln.schema_der_zeile(st.zeilen, z)
    assert sch and sch["stangen"] and sch["abmessungen"], z["schluessel"]
    assert sum(abm["stangen"] for abm in sch["abmessungen"]) == len(sch["stangen"]) == z["stangen"]
    for abm in sch["abmessungen"]:
        assert 0 < abm["nutz_m"] <= abm["meter"] + 1e-9 and abm["meter"] == sum(ln * n for ln, n in abm["laengen"]) / 1000
        assert abm["kunde"] or (abm["preis_m"] and abm["kosten"] > 0)
    if not z["gemeinsam"]:              # eine Mengenzeile: Stangenkosten = Material-Grundkosten der Stufe
        assert nah(sum(abm["kosten"] for abm in sch["abmessungen"]), z["bausteine"]["material"], 1e-6)
json.dumps(st.zeilen)                                      # gespeichert als JSON
assert len(stufen_der_zeilen(st.zeilen)) == m.rowCount()
mehr = max(st.zeilen, key=lambda z: z["menge"])
weniger = min((z for z in st.zeilen if z["schluessel"] == mehr["schluessel"]), key=lambda z: z["menge"])
assert len(staffeln.schema_der_zeile(st.zeilen, mehr)["stangen"]) >= len(staffeln.schema_der_zeile(st.zeilen, weniger)["stangen"])
schnitt = st.baum.zeile("schnitt")
assert schnitt is not None and schnitt.childCount() >= 1 and schnitt.text(1).endswith("Stangen")
fenster_s = st.schnittschema(mehr)
assert fenster_s.wahl.count() == m.rowCount() and fenster_s.tabelle.rowCount() >= 2
assert fenster_s.tabelle.item(fenster_s.tabelle.rowCount() - 1, 0).text() == "Summe"
assert len(fenster_s.stangen_seite.stangen) >= len(staffeln.schema_der_zeile(st.zeilen, mehr)["stangen"])
fenster_s.wahl.setCurrentIndex(0)
assert fenster_s.stangen_seite.stangen
fenster_s.reject()
ok("Schnittschema je Staffel: Stangen je Abmessung, Meter, €/m und Materialkosten je Stufe, im Ergebnis und im Fenster")

# Menge geändert: Stufe veraltet, nichts rechnet automatisch; der Knopf rechnet nur sie neu
speichern(5, mengen=[("10", 200, None)])
assert st.anzahl_veraltet() == 1 and "VERALTET" in s.staffel_info.text()
assert st.zeilen[5]["preis_einheit"] is None and st.zeilen[0]["preis_einheit"]
for _ in range(20):                                       # nie automatisch (Patrick 26.10.2026)
    app.processEvents()
assert st.anzahl_veraltet() == 1 and st.zeilen[5]["preis_einheit"] is None and "nicht automatisch" in s.staffel_info.text()
assert all(z["schluessel"] != "10" or z["menge"] != 200 for z in s.staffelpreise_aktuell() if z.get("preis_einheit"))
assert st.rechnen(alle=False) is not None and st.anzahl_veraltet() == 0 and "aktuell" in s.staffel_info.text()
assert st.zeilen[5]["menge"] == 200 and st.zeilen[5]["preis_einheit"] < sp[5]["preis_einheit"]
ok("Menge geändert: Stufe VERALTET ohne Preis, nicht automatisch gerechnet; der Knopf rechnet nur sie neu")

# Fehlerhafte Eingaben: gleiche Menge zweimal für Pos. 10 -> rot, ohne Preis, nicht im Angebot
speichern(4, mengen=[("10", 24, None)])
assert m.data(m.index(4, 5)).startswith("FEHLER: Menge doppelt"), m.data(m.index(4, 5))
ang = s.angebot_daten()
assert [x["menge"] for x in ang["staffeln"] if x["pos"] == "10"] == [200]      # beide doppelten Stufen fehlen
speichern(4, mengen=[("10", 50, None)])
assert st.rechnen(alle=False) is not None and st.anzahl_veraltet() == 0      # nur auf Knopfdruck
ang = s.angebot_daten()
assert [x["bereich"] for x in ang["staffeln"]] == ["ab 2", "ab 4", "ab 8", "ab 24", "ab 50", "ab 200"], ang["staffeln"]
# jede Stufe steht unter ihrer Angebotszeile (Satz bzw. Pos.), aufsteigend nach Menge; Summe nur aus den Hauptzeilen
unter = [x for z in ang["zeilen"] for x in z["staffeln"]]
assert all(x["zugeordnet"] for x in ang["staffeln"]) and sorted(map(id, unter)) == sorted(map(id, ang["staffeln"]))
for z in ang["zeilen"]:
    assert [x["menge"] for x in z["staffeln"]] == sorted(x["menge"] for x in z["staffeln"])
    assert all((x["art"] == "satz") == (z["art"] == "satz") for x in z["staffeln"])
assert ang["netto"] == round(sum(z["gesamt"] for z in ang["zeilen"] if z["gesamt"] is not None), 2)
ok("Doppelte Menge rot markiert und nicht im Angebot; Stufen im Angebot 'ab 2, ab 4, ab 8 …' unter ihrer Position")

# Rüstkosten separat: im Angebot als einmalige Rüstkosten
speichern(0, ruesten=staffeln.SEPARAT)
z0 = st.zeilen[0]
assert z0["preis"]["einmalig"] > 0 and z0["preis_gesamt"] == round(z0["preis_einheit"] * z0["menge"] + z0["preis"]["einmalig"], 2)
ang = s.angebot_daten()
a0 = next(x for x in ang["staffeln"] if x["menge"] == z0["menge"] and x["art"] == ("satz" if z0["einheit"] == "Satz" else "teil"))
assert "Rüstkosten" not in a0["text"] and a0["preis"] > z0["preis_einheit"]
assert a0["preis"] * z0["menge"] >= z0["preis_gesamt"] - 1e-9 and a0["gesamt"] == round(a0["preis"] * z0["menge"], 2)
assert s.angebot_pdf()
ok("Rüstkosten separat: im Angebots-PDF im Stufenpreis enthalten, keine extra Kosten")

# Stufe als gemeinsamer Auftrag: Mengen des Angebots = Preise des Angebots (Cent für Cent)
st.vorher = {}
sid = st.aus_angebot()
st.rechnen(alle=False)
haupt = angebotspreise(s.positionen, s._rechnung()[0])
gem = [z for z in st.zeilen if z.get("stufe") == sid]
assert len(gem) == len(haupt) >= 3 and all(z["gemeinsam"] for z in gem)
for z in gem:
    assert z["preis_einheit"] == ausgabe.kaufm_runden(haupt[z["schluessel"]], 2), (z["schluessel"], z["preis_einheit"])
assert nah(sum(z["preis"]["netto"] for z in gem), s._rechnung()[1]["verkauf"], 1e-6)
ok(f"Stufe mit den Mengen des Angebots ({len(gem)} Sätze/Positionen zusammen) = Stückpreise des Angebots")

# dieselbe Position allein als eigene Stufe ist teurer: Rüsten, Aufschlag und Programmierung trägt sie allein
allein = next(z for z in st.zeilen if z.get("stufe") != sid and z["schluessel"] == "10" and z["menge"] == 24)
assert allein["preis_einheit"] > next(z for z in gem if z["schluessel"] == "10")["preis_einheit"]
# Materialpreis je Abmessung und feste Fracht in der Stufe: neuer Mengenlauf, nur diese Stufe
r = next(i for i, x in enumerate(m.daten) if x["id"] == sid)
abm = staffeln.abmessung(next(p_ for p_ in s.positionen if str(p_.get("pos")) == "10"))
vorher10 = next(z for z in gem if z["schluessel"] == "10")["preis_einheit"]
speichern(r, preise={abm: 99.0}, fracht=100)
assert st.anzahl_veraltet() == 1
st.rechnen(alle=False)
gem = [z for z in st.zeilen if z.get("stufe") == sid]
assert next(z for z in gem if z["schluessel"] == "10")["preis_einheit"] > vorher10
assert nah(sum(z["preis"]["fracht"] for z in gem), 100.0, 1e-6)
assert "€/m für 1 Abmessung" in m.data(m.index(r, 3)) and "Frachtkosten 100,00 €" in m.data(m.index(r, 3))
ang = s.angebot_daten()
assert any(x["gemeinsam"] and x["stufe"] == r + 1 for x in ang["staffeln"])
assert s.angebot_pdf()
ok("Materialpreis €/m je Abmessung und feste Fracht je Stufe; im Angebot 'Stufe n: Ab …' mit Hinweis auf gemeinsame "
   "Bestellung")
s.st_seite.ansicht.selectRow(r)
s.st_seite.loeschen()
assert sid not in {x["id"] for x in db.staffel_stufen(a)} and not [z for z in db.staffeln(a) if z["stufe_id"] == sid]
ok("Stufe löschen entfernt ihre Mengen")

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

# Interne PDFs im Design des Angebots: kleines Logo, kein "-0,00", Abweichungen farbig
s.einst = dict(s.einst, logo=logo)
assert pdf._z(-0.001) == "0,00" and pdf._z(-0.006) == "-0,01" and pdf._z(None) == ""
assert pdf._abw_farbe(5) == pdf.ROT and pdf._abw_farbe(-5) == pdf.GRUEN and pdf._abw_farbe(0.001) is None
assert pdf._abw_farbe(5, erloes=True) == pdf.GRUEN
assert s.werkstatt_pdf() and s.kalkulation_pdf() and s.nachkalk.pdf()
ok("Werkstattpapiere, Kalkulation und Nachkalkulation mit Logo; rot = teurer, grün = günstiger; kein −0,00")
fenster.close()
db.schliessen()

# 11) Datendatei der Vorversion (Schema 13) mit gespeicherten Staffelpreisen
alt = tmp / "alt" / "rohrlaser.db"
d = Datenbank(alt)
a = beispiel_angebot.anlegen(d)
d.schliessen()
con = sqlite3.connect(alt)
con.execute("DROP TABLE staffel_stufen")
con.execute("ALTER TABLE staffeln DROP COLUMN stufe_id")
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
# Schema 36: je Satz bzw. Position die kleinste Menge in Stufe 1, die nächste in Stufe 2 …
stufen = d.staffel_stufen(a)
assert len(stufen) == 3 and stufen[0]["bemerkung"].count("Beispiel") == 2
assert sorted((z["schluessel"], z["menge"]) for z in d.staffeln(a) if z["stufe_id"] == stufen[1]["id"]) == \
    [("10", 50), ("Rahmen", 4)]
fenster = Hauptfenster(d, tmp / "alt", stumm=True)
s = fenster.angebot_oeffnen(a)
assert s.st_seite.anzahl_veraltet() == 3 and "VERALTET" in s.staffel_info.text()
assert s.optimieren()
assert not any(z.get("preis_einheit") for z in s.staffelpreise_aktuell())   # nie automatisch gerechnet
assert s.st_seite.anzahl_veraltet() == 3
neu = s.staffelpreise_rechnen()
for z in neu:
    assert z["preis_einheit"] == ausgabe.kaufm_runden(z["bausteine"]["verkauf"] / z["menge"], 2)
fenster.close()
d.schliessen()
ok("11 Datei Schema 13: Sicherung vor der Umstellung, alte Mengen der Größe nach in Stufe 1–3, alte "
   "Staffelpreise veraltet und neu gerechnet")

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
