"""Ein Rechenweg für Angebot, Staffel, Satz und Baugruppe (Plan Angebotskalkulation 16.11.2026, Paket K5).

Gleichheitstest über alle Abnahmeangebote, je in fünf Varianten (wie erfasst, mit Zusatzarbeiten, mit Satz,
gestaffelter Gewinn, Mindestpreis) und eine Schweißbaugruppe mit Zukaufteilen: Eine Staffelstufe mit genau den
Mengen des Angebots ergibt Cent für Cent die Preise im Angebots-PDF (je Satz bzw. Position) und dieselbe Summe, und
die Prüfangebote (K4) rechnen denselben Verkaufspreis wie das Angebot. Einzige gewollte Ausnahme: Positionen ohne
Materialpreis bzw. nicht eingeplante Teile (Angebot mit Fehler) bekommen in der Stufe keinen Preis, sondern FEHLER.

Aufruf: python tests/test_ein_rechenweg.py
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
from PySide6.QtWidgets import QApplication  # noqa: E402

from abnahme_angebote import ANGEBOTE  # noqa: E402
from rohrlaser import VERSION, baugruppe, pruefangebote as pa, zukauf  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE, ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
VARIANTEN = {"wie erfasst": {}, "Zusatzarbeiten": {}, "Satz": {},
             "gestaffelter Gewinn": dict(gewinn_bis_1=300, gewinn_satz_1=0.3, gewinn_satz_2=0.08),
             "Mindestpreis": dict(mindestpreis=5000)}


def vergleichen(a, name):
    """Stufe mit den Mengen des Angebots gegen das Angebot. Ergebnis: Anzahl verglichener Sätze/Positionen."""
    s = f.angebot_oeffnen(a)
    assert s.optimieren(), name
    st = s.st_seite
    st.vorher = {}
    sid = st.aus_angebot()
    st.rechnen(alle=False)
    kz, summen = s._rechnung()
    pdf = {(str(z.get("satz")) if z["art"] == "satz" else str(z.get("pos"))): z["preis"]
           for z in s.angebot_daten()["zeilen"] if z["art"] in ("teil", "satz")}
    profile = db.kontext().profile          # Abmessung unbekannt: kein Materialpreis (Angebot mit Fehler)
    fehlerhaft = {str(p.get("pos")): z["preis_teil"] * p["stueck"] for p, z in zip(s.positionen, kz)
                  if z and p.get("profil_id") and p["profil_id"] not in profile and not p.get("satz")}
    stufe = [z for z in st.zeilen if z.get("stufe") == sid]
    assert stufe, name
    for z in stufe:
        if z["schluessel"] in fehlerhaft:
            assert z["preis_einheit"] is None and "FEHLER" in (z.get("hinweis") or ""), (name, z["schluessel"])
            continue
        # seit 24.11.2026 (Staffel = Angebot) auch mit Mindestpreis und fehlerhaften Positionen: jede Position mit
        # Preis kostet in der Stufe genau so viel wie im Angebot
        assert z["preis_einheit"] == pdf[z["schluessel"]], (name, z["schluessel"], z["preis_einheit"],
                                                            pdf[z["schluessel"]])
    summe = sum(z["preis"]["netto"] for z in stufe if z.get("preis"))
    assert abs(summe + sum(fehlerhaft.values()) - summen["verkauf"]) < 0.005, (name, summe, summen["verkauf"])
    # Prüfangebot (K4): gleicher Verkaufspreis wie das Angebot
    if not fehlerhaft:
        ref = pa.markieren(db, a, VERSION)
        assert abs(ref["verkauf"] - summen["verkauf"]) < 0.005, (name, ref["verkauf"], summen["verkauf"])
        assert pa.pruefen(db, [a])[0]["abweichung"] == 0, name
    f.angebot_schliessen(a)
    return len(stufe)


n_faelle = n_zeilen = 0
for an in ANGEBOTE:
    for variante, einst in VARIANTEN.items():
        alt = {n: db.einstellung(n) for n in einst}
        for n, w in einst.items():
            db.einstellung_setzen(n, w)
        a = db.angebot_neu(dict(kunde=an["kunde"], maschine=an["maschine"], stange=an["stange"]))
        for i, p in enumerate(an["positionen"]):
            d = dict(pos=p["pos"], artikel=p["artikel"], bezeichnung=p["bezeichnung"], profil_id=p["profil"],
                     werkstoff_id=p["werkstoff"], laenge=p["laenge"], stueck=p["stueck"],
                     **{n: p[n] for n in ("schneidweg", "einstiche", "stange", "a_gerade", "b_gerade") if n in p})
            if variante == "Zusatzarbeiten":
                d["zusatz"] = json.dumps([{"name": "Entgraten"}, {"name": "Prüfbericht 3.1"}])
            if variante == "Satz" and i < 2:
                d.update(satz="S1", je_satz=p["stueck"])
            db.position_neu(a, d)
        n_zeilen += vergleichen(a, f"{an['nummer']} {variante}")
        n_faelle += 1
        for n, w in alt.items():
            db.einstellung_setzen(n, w)
ok(f"{n_faelle} Angebote ({len(ANGEBOTE)} Abnahmeangebote × {len(VARIANTEN)} Varianten), {n_zeilen} Sätze/Positionen: "
   "Stufe mit den Mengen des Angebots = Preise im Angebot, Prüfangebot = Verkaufspreis")

# Schweißbaugruppe mit Laserteilen und Zukaufteilen, dazu ein einzelnes Rohr
schraube = db.zukauf_speichern(None, dict(artikelnr="Z-M8", bezeichnung="Schraube M8x25", einheit="Stück",
                                          aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT,
                                          aufschlag_wert=0),
                               [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=0.10)])])
lasche = db.zukauf_speichern(None, dict(artikelnr="Z-L", bezeichnung="Blechlasche 80x60x8", einheit="Stück",
                                        aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT,
                                        aufschlag_wert=10),
                             [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=1.50)])])


def eintrag(aid, menge):
    return dict(artikel_id=aid, menge=menge, stand=db.zukauf_stand(aid))


rahmen = baugruppe.leer()
rahmen["knoten"] = [dict(id="k1", parent="", name="Querstrebe", menge=1)]
rahmen["naehte"] = [dict(id="n1", knoten="", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=120,
                         anzahl=8, heftpunkte=2, lage="PA")]
rahmen["arbeitsgaenge"] = [dict(id="a1", knoten="", name="Schleifen", satz=60, zeit_min=6, menge=1),
                           dict(id="a2", knoten="", name="Vorrichten", satz=60, ruest_min=30),
                           dict(id="a5", knoten="", name="Verzinken", fremd=True, kosten_einheit=1.20, menge=12.5)]
a = db.angebot_neu(dict(kunde="Test", maschine="T11", stange=6000))
db.position_neu(a, dict(pos=100, art=BAUGRUPPE, artikel="R1", bezeichnung="Rahmen R1", stueck=6, satz="R1",
                        baugruppe=baugruppe.speichern(rahmen), zukauf=json.dumps([eintrag(schraube, 8)])))
db.position_neu(a, dict(pos=110, artikel="Rohr", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
                        stueck=24, schneidweg=320, einstiche=2, satz="R1", je_satz=4, bg_knoten=rahmen["id"],
                        je_knoten=4))
db.position_neu(a, dict(pos=120, art=ZUKAUFTEIL, artikel="Lasche", bezeichnung="Blechlasche", stueck=12, satz="R1",
                        je_satz=2, zukauf=json.dumps([eintrag(lasche, 1)]), bg_knoten=rahmen["id"], je_knoten=2))
db.position_neu(a, dict(pos=200, artikel="Distanz", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=150,
                        stueck=40, schneidweg=280, einstiche=2))
vergleichen(a, "Baugruppe")
ok("Schweißbaugruppe mit Laser- und Zukaufteilen und ein Einzelteil: Stufe = Angebot, Prüfangebot = Verkaufspreis")
print("test_ein_rechenweg OK")
