"""Zusatzarbeiten besser erkennen, leichter wählen, schneller neu anlegen (Plan Patrick 03.11.2026, Freigabe
1a 2a 3c 4a 5a 6a): Erkennungswörter (längeres Wort gewinnt, Verneinung, RAL-Farbe), Schema 75 mit Vorbelegung,
gelbe Vorschläge in der Positionsliste ohne Preisänderung, Übernehmen und Ablehnen, Anfrage-Mail, Zukaufteile ohne
Vorschlag, neues Auswahlfenster (Häkchen, kein Doppel, € je Teil), Rechtsklick-Schnellmenü, Kurzformular (Admin: in die
Einstellungen, sonst nur dieses Angebot) mit Vorlagen, „Aus Angeboten übernehmen“, Auswahl im Baugruppen-Editor.

Aufruf: python tests/test_zusatz_erkennung.py
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
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import arbeitsgaenge as ag, rechnen, zusatz_erkennung as ze  # noqa: E402
from rohrlaser.datenbank import ERKENNUNG_STAND, SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import beispiel_zusatzarbeiten  # noqa: E402
from rohrlaser.zusatz_dialog import EIGEN, ZusatzDialog, ZusatzWahl  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ E1 Wörter
kat = beispiel_zusatzarbeiten()
assert ze.treffer("Riegel fvz", kat) == [("Feuerverzinken", "fvz")]
assert ze.treffer("Stiel galvanisch verzinkt", kat) == [("Galvanisch verzinken", "galvanisch verzinkt")]
assert ze.treffer("unverzinkt", kat) == [] and ze.treffer("ohne Pulver", kat) == [] and ze.treffer("Zentralrohr", kat) == []
assert ze.treffer("Rohr nicht verzinkt", kat) == []
assert {n for n, _ in ze.treffer("verzinkte Strebe, gestrahlt SA 2,5", kat)} == {"Feuerverzinken", "Strahlen"}
assert ze.ral("Platte RAL7016 matt") == "RAL 7016" and ze.ral("Ralf") is None
e = ze.erkannt(dict(bezeichnung="Abdeckung RAL 9005 pulverbeschichtet"), kat)
assert e == [dict(name="Pulverbeschichten", quelle="Bezeichnung", wort="pulverbeschichtet", text="RAL 9005")], e
assert ze.erkannt(dict(art="Zukaufteil", bezeichnung="Scharnier verzinkt"), kat) == []
ok("E1 Erkennungswörter: längeres Wort gewinnt, Verneinung, kurze Wörter nur ganz, RAL-Farbe als Text, "
   "Zukaufteile ohne Vorschlag")

# ------------------------------------------------------------------ E2 Schema 75, Vorbelegung, alte Datei
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fvz = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == "Feuerverzinken")
assert "fvz" in fvz["erkennung"] and db.einstellung("erkennung_stand") == ERKENNUNG_STAND
alt = tmp / "alt.db"
d2 = Datenbank(alt)
d2.schliessen()
con = sqlite3.connect(alt)
con.execute("UPDATE zusatzarbeiten SET erkennung=NULL")
con.execute("UPDATE zusatzarbeiten SET erkennung='eigen' WHERE name='Strahlen'")
con.execute("DELETE FROM einstellungen WHERE name='erkennung_stand'")
con.execute("DELETE FROM zusatzarbeiten WHERE name='Einnietmuttern setzen'")
con.execute(f"PRAGMA user_version={SCHEMA_VERSION - 1}")
con.commit()
con.close()
d2 = Datenbank(alt)
z2 = {z["name"]: z.get("erkennung") for z in d2.zeilen("zusatzarbeiten")}
assert "fvz" in z2["Feuerverzinken"] and z2["Strahlen"] == "eigen" and not z2["Gravur extra"]
assert "nietmutter" in z2["Einnietmuttern setzen"]          # Einnietmuttern einmalig ergänzt
d2.schliessen()
ok("E2 Schema 75: Erkennungswörter vorbelegt, alte Datei ergänzt nur leere Felder (eigene bleiben)")

# ------------------------------------------------------------------ E3 Vorschläge in der Positionsliste
fenster = Hauptfenster(db, tmp, stumm=True)
aid = beispiel_angebot.anlegen(db)
pos = [p for p in db.positionen(aid) if p.get("profil_id") and p.get("art") != "Zukaufteil"]
assert len(pos) >= 3
for p in pos:
    db.position_aendern(p["id"], "bezeichnung", "Riegel")
    db.position_aendern(p["id"], "zusatz", None)
db.position_aendern(pos[0]["id"], "bezeichnung", "Riegel tZn")
db.position_aendern(pos[1]["id"], "bezeichnung", "Abdeckung RAL 7016 pulverbeschichtet")
s = fenster.angebot_oeffnen(aid)
r0 = next(r for r, p in enumerate(s.positionen) if p["id"] == pos[0]["id"])
r1 = next(r for r, p in enumerate(s.positionen) if p["id"] == pos[1]["id"])
r2 = next(r for r, p in enumerate(s.positionen) if p["id"] == pos[2]["id"])
vorher = s._rechnung()[0]
vs0 = s.pos_modell.vorschlaege[r0]
assert [v["name"] for v in vs0] == ["Feuerverzinken"] and vs0[0]["herkunft"] == "Erkannt: Bezeichnung „tZn“", vs0
spalte = next(c for c, (art, _) in enumerate(s.pos_modell.spalten) if art == "zusatz")
assert "＋ Feuerverzinken ?" in s.pos_modell.data(s.pos_modell.index(r0, spalte))
assert s.pos_modell.data(s.pos_modell.index(r0, spalte), Qt.BackgroundRole).color().name().lower() != \
    s.pos_modell.data(s.pos_modell.index(r2, spalte), Qt.BackgroundRole).color().name().lower()
assert not s.vorschlag_knopf.isHidden() and s.vorschlag_knopf.text() == "2 Vorschläge", s.vorschlag_knopf.text()
assert s._rechnung()[0] == vorher, "Vorschlag darf nichts kosten"
zeilen = {(x["position_id"], x["arbeitsgang"]): x for x in s.arbeitsgaenge_zeilen()}
x = zeilen[(pos[1]["id"], "Pulverbeschichten")]          # Beispielregel „Pulver laut Bezeichnung“ geht vor
assert x["status"] == ag.VORSCHLAG and x["betrag"] > 0 and x["herkunft"] == "Regel: Pulver laut Bezeichnung", x
assert s.pos_modell.vorschlaege[r1][0]["text"] == "RAL 7016"     # Farbe aus der Bezeichnung trotzdem
ok("E3 erkannt: gelb „＋ Feuerverzinken ?“ in der Spalte, Knopf „2 Vorschläge“, Preis unverändert, "
   "in „Arbeitsgänge vorschlagen“ mit Betrag")

# ------------------------------------------------------------------ E4 Übernehmen, Ablehnen
assert s.vorschlaege_uebernehmen([r1]) == 1
e1 = next(e for e in rechnen.zusatz_liste(s.positionen[r1]))
assert e1["name"] == "Pulverbeschichten" and e1["text"] == "RAL 7016" and e1["quelle"].startswith("Regel:"), e1
assert e1["stand"]["art"] == "€/m²"
assert s._rechnung()[0][r1]["zusatz_teil"] > vorher[r1]["zusatz_teil"]
assert s.vorschlaege_ablehnen([r0]) == 1
assert not s.pos_modell.vorschlaege[r0] and s.vorschlag_knopf.isHidden()
zeilen = {(x["position_id"], x["arbeitsgang"]): x for x in s.arbeitsgaenge_zeilen()}
assert zeilen[(pos[0]["id"], "Feuerverzinken")]["status"] == ag.ABGELEHNT
assert s.arbeitsgang_ablehnen(pos[0]["id"], "Feuerverzinken", zurueck=True)
assert [v["name"] for v in s.pos_modell.vorschlaege[r0]] == ["Feuerverzinken"]
assert s.arbeitsgang_annehmen(pos[0]["id"], "Feuerverzinken")
assert rechnen.zusatz_liste(s.positionen[r0])[0]["quelle"] == "Erkannt: Bezeichnung „tZn“"
ok("E4 Übernehmen mit RAL-Farbe und Preisstand (rechnet), Ablehnen gemerkt und zurücknehmbar, Annehmen in "
   "„Arbeitsgänge vorschlagen“")

# ------------------------------------------------------------------ E5 Anfrage-Mail
neu = ze.text_merken(None, "Hallo, bitte alle Teile feuerverzinkt anbieten. Gruß", db.zeilen("zusatzarbeiten"),
                     "E-Mail")
assert json.loads(neu)["erkannt"] == [dict(name="Feuerverzinken", quelle="E-Mail", wort="feuerverzinkt", text=None)]
assert ze.text_merken(neu, "nichts", db.zeilen("zusatzarbeiten"), "E-Mail") == neu
p2 = dict(s.positionen[r2], arbeitsgaenge=neu)
assert [v["herkunft"] for v in ze.offen(p2, s.kopf, s.k, s.tabellen)] == ["Erkannt: E-Mail „feuerverzinkt“"]
ok("E5 Anfrage-Mail: erkannte Zusatzarbeit wird an der Position gemerkt und als Vorschlag gezeigt")

# ------------------------------------------------------------------ E6 Auswahlfenster
d = ZusatzDialog(s, s.positionen[r2], 1, s.k, s.tabellen, {"Entgraten": 3}, kunde_haeufig={"Strahlen": 1},
                 positionen=s.positionen)
titel = [d.liste.item(i).text() for i in range(d.liste.count()) if d.liste.item(i).data(Qt.UserRole) is None]
assert "Häufig verwendet" in titel and "Bei diesem Kunden" in titel and "Oberfläche" in titel, titel
it = next(d.liste.item(i) for i in range(d.liste.count()) if d.liste.item(i).data(Qt.UserRole) == "Entgraten")
it.setCheckState(Qt.Checked)
assert d.gewaehlt() == ["Entgraten"]
d.hinzufuegen("Entgraten")
assert d.gewaehlt() == ["Entgraten"], "doppelt eingetragen"
assert d.tabelle.cellWidget(0, 4).text() == "0,50 €" and "Summe je Teil 0,50 €" in d.summe.text(), d.summe.text()
r = d.zeile_neu()
assert d.tabelle.cellWidget(r, 0).currentText() == ""
d.tabelle.cellWidget(r, 0).setCurrentText("Entgraten")
assert "nur einmal" in d.fehler.text()
try:
    d.werte()
    raise AssertionError("doppelte Zusatzarbeit nicht abgewiesen")
except ValueError as e_:
    assert "steht schon" in str(e_)
d.tabelle.removeRow(r)
d.suche.setText("verzink")
sichtbar = [d.liste.item(i).data(Qt.UserRole) for i in range(d.liste.count())
            if not d.liste.item(i).isHidden() and d.liste.item(i).data(Qt.UserRole)]
assert set(sichtbar) == {"Feuerverzinken", "Galvanisch verzinken"}, sichtbar
it.setCheckState(Qt.Unchecked)
assert d.gewaehlt() == []
dv = ZusatzDialog(s, s.positionen[r2], 1, s.k, s.tabellen, positionen=s.positionen)
assert dv.vorschlag_leiste.isHidden()
dv = ZusatzDialog(s, dict(s.positionen[r2], bezeichnung="Strebe gestrahlt"), 1, s.k, s.tabellen)
assert not dv.vorschlag_leiste.isHidden() and "Strahlen" in dv.vorschlag_text.text()
dv.vorschlaege_uebernehmen()
assert dv.gewaehlt() == ["Strahlen"] and dv.vorschlag_leiste.isHidden()
assert json.loads(dv.werte()[1])[0]["quelle"] == "Erkannt: Bezeichnung „gestrahlt“"
ok("E6 Auswahlfenster: Gruppen (häufig, Kunde, Kategorie), Häkchen trägt ein und entfernt, nichts vorgewählt, kein "
   "Doppel, € je Teil und Summe, Suche nach Erkennungswort, Vorschläge oben gelb übernehmen")

# ------------------------------------------------------------------ E7 Rechtsklick-Schnellmenü
s.pos_ansicht.selectRow(r2)
assert "Zusatzarbeit hinzufügen" in s._pos_menue_anpassen()
s._zusatz_schnellmenue_fuellen()
texte = [a.text() for a in s.zusatz_schnellmenue.actions() if a.text()]
assert "Weitere …" in texte and "Neue Zusatzarbeit …" in texte and len([t for t in texte if "…" not in t]) == 8, texte
assert s.zusatz_schnell("Entgraten", [r2, r1]) == 2
assert s.zusatz_schnell("Entgraten", [r2]) == 0          # schon da: nicht doppelt
assert [e["name"] for e in rechnen.zusatz_liste(s.positionen[r2])] == ["Entgraten"]
ok("E7 Rechtsklick → Zusatzarbeit hinzufügen: 8 häufigste, Weitere, Neue; für markierte, nie doppelt")

# ------------------------------------------------------------------ E8 Kurzformular, Vorlagen, Admin
def ausfuellen(name, preis, art="€/m²", vorlage=None, haken=None):
    def f(d):
        if vorlage:
            assert d.vorlage_nehmen(vorlage)
        else:
            d.name.setText(name)
            d.art_setzen(art)
            d.preis.setText(preis)
            d.erkennung.setText("eloxiert; E6")
        if haken is not None:
            assert d.stammdaten.isEnabled() is haken
        assert "€ je Teil" in d.vorschau.text() or art == "€/Angebot", d.vorschau.text()
        d._ok()
        return d.result()
    return f


s.zusatz_gesperrt = lambda: False                   # Admin (kein Passwort gesetzt oder freigeschaltet)
assert s.zusatz_neu_anlegen([r2], ausfuellen("Eloxieren E6", "14,5", haken=True)) == "Eloxieren E6"
z = next(z for z in db.zeilen("zusatzarbeiten") if z["name"] == "Eloxieren E6")
assert z["art"] == "€/m²" and z["preis"] == 14.5 and z["erkennung"] == "eloxiert; E6"
assert rechnen.zusatz_liste(s.positionen[r2])[-1]["name"] == "Eloxieren E6"
s.zusatz_gesperrt = lambda: True                    # Platz nicht als Admin freigeschaltet
assert s.zusatz_neu_anlegen([r2], ausfuellen(None, None, vorlage="Richten", haken=False)) == "Richten"
assert "Richten" not in {z["name"] for z in db.zeilen("zusatzarbeiten")}
e = rechnen.zusatz_liste(s.positionen[r2])[-1]
assert e["name"] == "Richten" and e["quelle"] == EIGEN and e["stand"]["preis"] == 2.5
assert next(z for z in s._rechnung()[0][r2]["zusatzarbeiten"] if z["name"] == "Richten")["betrag"] == 2.5
assert "Richten" in db.zusatz_eigene()
dl = ZusatzDialog(s, s.positionen[r1], 1, s.k, s.tabellen, positionen=s.positionen)
assert "Nur in diesem Angebot" in [dl.liste.item(i).text() for i in range(dl.liste.count())]
dl.hinzufuegen("Richten")
dl.stand_verwerfen()                                # behält den Stand (keine Stammdaten)
assert json.loads(dl.werte()[1])[-1]["stand"]["preis"] == 2.5
assert s.zusatz_schnell("Richten", [r1]) == 1
i = db.zusatz_aus_angebot("Richten")
z = next(z for z in db.zeilen("zusatzarbeiten") if z["id"] == i)
assert z["art"] == "€/Stück" and z["preis"] == 2.5 and "gerichtet" in z["erkennung"] and z["kategorie"] == "Nachbearbeitung"
assert "Richten" not in db.zusatz_eigene()
assert all(e.get("quelle") != EIGEN for p in db.positionen(aid) for e in rechnen.zusatz_liste(p))
ok("E8 Kurzformular: Admin legt in den Einstellungen an, sonst nur in diesem Angebot (rechnet mit Preisstand, in "
   "anderen Positionen wählbar); Vorlage Richten; „Aus Angeboten übernehmen“ legt die Stammdaten an")

# ------------------------------------------------------------------ E9 Baugruppen-Editor: gleiche Auswahl
w = ZusatzWahl(None, {z["name"]: z for z in db.zeilen("zusatzarbeiten")}, ["Strahlen"])
assert w.liste.item(0).text() == "Vorschläge (erkannt)"
assert w.anhaken("Strahlen") and w.anhaken("Entgraten") and w.gewaehlt() == ["Strahlen", "Entgraten"]
w.suche.setText("pulver")
assert [w.liste.item(i).data(Qt.UserRole) for i in range(w.liste.count())
        if not w.liste.item(i).isHidden() and w.liste.item(i).data(Qt.UserRole)] == ["Pulverbeschichten"]
assert QDialog.Accepted == 1
ok("E9 Baugruppen-Editor „Aus Zusatzarbeiten …“: Auswahl mit Suche, Häkchen und erkannten oben")

# ------------------------------------------------------------------ E10 Einnietmuttern aus der Geometrie
import math  # noqa: E402
sechs = "; ".join(f"{6.5 * math.cos(math.radians(60 * i)):.3f},{6.5 * math.sin(math.radians(60 * i)):.3f}"
                  for i in range(6))
assert ze.ist_sechskant([(6.5 * math.cos(math.radians(60 * i + 15)), 6.5 * math.sin(math.radians(60 * i + 15)))
                         for i in range(6)] + [(6.5 * math.cos(math.radians(15)), 6.5 * math.sin(math.radians(15)))])
assert not ze.ist_sechskant([(0, 0), (10, 0), (10, 10), (0, 10)])
assert not ze.ist_sechskant([(0, 0), (20, 0), (24, 5), (20, 10), (0, 10), (-4, 5)])     # gestreckt
um = [[3.75 * k, -6.5] for k in (-1, 1)] + [[7.5, 0]] + [[3.75 * k, 6.5] for k in (1, -1)] + [[-7.5, 0]]
technik = json.dumps(dict(quelle="STEP-Import", konturen=[
    dict(art="Polygon", anzahl=2, punkte=sechs),                                   # Rohr-/Blech-Editor
    dict(art="Sonderkontur", anzahl=1, laenge=45.03, huelle=15.01, umriss=um),     # STEP-Import mit Umriss
    dict(art="Sonderkontur", anzahl=1, laenge=34.64, huelle=11.55),                # nur Länge und Hüllmaß
    dict(art="Sonderkontur", anzahl=1, laenge=47.1, huelle=15.0),                  # rund: kein Sechskant
    dict(art="Rechteck", anzahl=3, b=10, h=10, r=0)]))
bild = json.dumps([dict(art="Senkung", d=8.4, D=12.4, anzahl=2, status="offen"),
                   dict(art="Senkung", d=6.6, D=11, anzahl=1, status="abgelehnt")])
assert ze.geometrie(dict(technik=technik, bohrbild=bild)) == (4, 2)
assert ze.geometrie(dict(technik=json.dumps(dict(konturen=[dict(art="Senkung", d=8.4, D=12.4, anzahl=3)])))) == (0, 3)
k_ = db.zeilen("zusatzarbeiten")
p6 = dict(s.positionen[r1], technik=technik, bohrbild=bild, zusatz=None, arbeitsgaenge=None)
vs = [v for v in ze.offen(p6, s.kopf, s.k, s.tabellen) if v["name"] == "Einnietmuttern setzen"]
assert len(vs) == 1 and vs[0]["menge"] == 6 and vs[0]["herkunft"] == "Erkannt: Geometrie 4 Sechskantlöcher, 2 Senkungen", vs
e = json.loads(ze.uebernehmen(p6, vs, s.tabellen))[-1]
assert e["name"] == "Einnietmuttern setzen" and e["menge"] == 6 and e["stand"]["preis"] == 0.6, e
z = next(z for z in rechnen.zusatz_werte(dict(p6, zusatz=json.dumps([e])), s.k, s.tabellen, s.kopf))
assert abs(z["betrag"] - 3.6) < 1e-9, z
assert not [v for v in ze.offen(dict(p6, technik=None, bohrbild=None), s.kopf, s.k, s.tabellen)
            if v["name"] == "Einnietmuttern setzen"]
assert not ze.offen(dict(p6, zusatz=json.dumps([e])), s.kopf, s.k, s.tabellen) or all(
    v["name"] != "Einnietmuttern setzen" for v in ze.offen(dict(p6, zusatz=json.dumps([e])), s.kopf, s.k, s.tabellen))
assert any(z["name"] == "Einnietmuttern setzen" and z.get("aktiv") == "ja" for z in k_)
ok("E10 Einnietmuttern: Sechskantlöcher (Polygon, Umriss, Länge/Hüllmaß) und Senkungen ergeben einen Vorschlag mit "
   "Menge = Anzahl je Teil (0,60 € je Mutter), abgelehnte Senkungen zählen nicht, Runde/Rechtecke nicht")
print("OK: Zusatzarbeiten erkennen, wählen und neu anlegen")
