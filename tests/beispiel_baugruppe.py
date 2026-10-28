"""Abnahme-Beispiel 'Rahmen R1' (Schweißbaugruppe mit Handrechnung, T4) für tests/test_baugruppe_abnahme.py.

Rahmen R1, 2 Stück: Unterbaugruppe Querstrebe (1×), drei Nahtgruppen, sechs Arbeitsgänge/Vorrichtungen, Teile
Rohr (4 je Rahmen), Strebe (1 je Querstrebe), Lasche (2 je Querstrebe), 8 Schrauben je Rahmen. Je Baugruppe:
Schweißen 5,2 + 14,4 + 10 = 29,6 min (37,00 €), Arbeitsgänge 6 + 6 = 12,00 €, Einmalkosten (30 € Rüsten +
100 € Vorrichtung anteilig) ÷ 2 = 65,00 €, Fremdleistung Verzinken 15,00 €: eigen 114,00 €, fremd 15,00 €.
Drei Mengenstufen: 1, 5 und 20 Rahmen."""
import json

from rohrlaser import baugruppe, zukauf
from rohrlaser.angebot import BAUGRUPPE, ZUKAUFTEIL

KENNWERTE = {
    "schweissverfahren": [dict(verfahren="MAG", bezeichnung="MAG Hand", satz_id="Schweißen", lichtbogen=40, heft_s=6,
                               aktiv="ja", status="geprüft")],
    "schweiss_kennwerte": [dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=4, min_m=1.5, status="geprüft"),
                           dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=5, min_m=2.4, status="geprüft"),
                           # a5 genau auf einer Zeile: Handrechnung bleibt, seit 0.9.177 rechnet ein a zwischen zwei
                           # Zeilen nach dem Nahtquerschnitt (tests/test_bg_naht_rechnung.py)
                           dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=6, min_m=2.4, status="geprüft"),
                           dict(verfahren="MAG", nahtart="Stumpfnaht", mass_bis=5, min_m=3.0, status="geprüft")],
    "schweiss_faktoren": [dict(art="Schweißlage", wert="PF", faktor=1.2, status="geprüft")],
}
EIGEN, FREMD, EINMAL = 114.0, 15.0, 130.0          # Handrechnung je Baugruppe bzw. je Auftrag (siehe oben)
STUFEN = (1, 5, 20)


def _artikel(db, nr, bez, preis):
    return db.zukauf_speichern(None, dict(artikelnr=nr, bezeichnung=bez, einheit="Stück",
                                          aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT,
                                          aufschlag_wert=0),
                               [dict(lieferant="L", preiseinheit=1, preise=[dict(ab=1, preis=preis)])])


def rahmen():
    g = baugruppe.leer()
    g["id"] = "r1abnahme0"                         # feste Kennung: Ergebnis bitgleich vergleichbar
    g["stamm"] = dict(zeichnung="Z-4711", revision="B", werkstoff="S235")
    g["knoten"] = [dict(id="k1", parent="", name="Querstrebe", menge=1)]
    g["naehte"] = [
        dict(id="n1", knoten="", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=120, anzahl=8,
             heftpunkte=2, lage="PA"),
        dict(id="n2", knoten="k1", nr="2", verfahren="MAG", nahtart="Kehlnaht", mass=5, laenge=250, anzahl=4,
             beidseitig=True, lage="PF"),
        dict(id="n3", knoten="", nr="3", verfahren="MAG", nahtart="Stumpfnaht", mass=4, laenge=180, anzahl=2,
             zeit_hand=10)]
    g["arbeitsgaenge"] = [
        dict(id="a1", knoten="", name="Schleifen", satz=60, zeit_min=6, menge=1),
        dict(id="a2", knoten="", name="Vorrichten", satz=60, ruest_min=30),
        dict(id="a3", knoten="", name="Vorrichtung bauen", einmal_eur=400, umlage="anteilig", anteil=25),
        dict(id="a4", knoten="", name="Schweißlehre", einmal_eur=250, umlage="wiederverwendbar"),
        dict(id="a5", knoten="", name="Verzinken", fremd=True, kosten_einheit=1.20, menge=12.5),
        dict(id="a6", knoten="k1", name="Querstrebe ausrichten", satz=60, zeit_min=3, menge=2)]
    return g


def anlegen(db):
    """Stammdaten (Kennwerte, Zukaufartikel) und Angebot 'Rahmen R1' mit drei Mengenstufen anlegen; Satz, Stück je
    Satz und Stückzahl der Teile sind abgeglichen. Ergebnis: Angebots-ID."""
    db.stammdaten_ersetzen(KENNWERTE, {}, "Abnahme")
    db.einstellung_setzen("mindestpreis", 0.0)
    schraube = _artikel(db, "Z-M8", "Schraube M8x25", 0.10)
    lasche = _artikel(db, "Z-L", "Blechlasche 80x60x8", 1.50)
    g = rahmen()
    a = db.angebot_neu(dict(kunde="Abnahme", kundennr="4711", maschine="T11"))
    db.position_neu(a, dict(pos=100, art=BAUGRUPPE, artikel="R1", bezeichnung="Rahmen R1", stueck=2,
                            baugruppe=baugruppe.speichern(g),
                            zukauf=json.dumps([dict(artikel_id=schraube, menge=8, stand=db.zukauf_stand(schraube))])))
    db.position_neu(a, dict(pos=10, artikel="Rohr", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
                            stueck=1, schneidweg=320, einstiche=2, bg_knoten=g["id"], je_knoten=4))
    db.position_neu(a, dict(pos=20, artikel="Strebe", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800,
                            stueck=1, schneidweg=320, einstiche=2, bg_knoten=baugruppe.zuordnung_text(g["id"], "k1"),
                            je_knoten=1))
    db.position_neu(a, dict(pos=30, art=ZUKAUFTEIL, artikel="Lasche", bezeichnung="Blechlasche", stueck=1,
                            zukauf=json.dumps([dict(artikel_id=lasche, menge=1, stand=db.zukauf_stand(lasche))]),
                            bg_knoten=baugruppe.zuordnung_text(g["id"], "k1"), je_knoten=2))
    pos = db.positionen(a)
    for i, feld, wert in baugruppe.abgleich(pos):
        db.position_aendern(pos[i]["id"], feld, wert)
    for m in STUFEN:
        db.staffel_neu(a, dict(schluessel="Rahmen R1", menge=m))
    return a
