"""Plan N4 (Patrick 16.11.2026, „Alle Empfehlungen“): Vorrichtungskosten vorschlagen (ASM-006) und Teilefamilien mit
Variablen (CAD-010).

Prüft:
1 Rechenkern Teilefamilie: Konturen mitziehen (hintere Hälfte mit Ende B, Lochreihe über die Mitte streckt sich, neue
  Anzahl gleichmäßig verteilt), Zeilen aus Excel (Kopfzeile, Dezimalkomma), Blech Länge/Breite;
2 Angebot: Rohr- und Blech-Familie als neue Positionen (Rohr wie aus dem Rohr-Editor gerechnet, Blech neuer
  Zukaufartikel mit Richtpreis), Fenster mit Einfügen und Prüfung (doppelte Artikel), Vorlage mit allen Teilen;
3 Editoren: Knopf Teilefamilie im Rohr-Editor (neu und vorhanden), Blech-Editor, Schweißbaugruppe (neue Teile in
  dieselbe Baugruppe) und Satz in 3D (derselbe Satz);
4 Vorrichtung: Vorschlag aus Teilen, Größe und enger Toleranz mit Richtwerten bzw. eigenen Stammdaten, Übernehmen,
  Hinweis bei Wiederholauftrag desselben Kunden mit Übernehmen (wiederverwendbar).

Aufruf: python tests/test_vorrichtung_familie_1611.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

import beispiel_angebot as B  # noqa: E402
from rohrlaser import baugruppe, blech, positionsvorlagen, schneidweg as sw, teilefamilie as tf, vorrichtung  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
for _n in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.No))
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("funktion_zukauf_stamm", "ja")     # zentrale Zukaufartikelverwaltung
f = Hauptfenster(db, tmp, stumm=True)
KOPF = {k: v for k, v in B.KOPF.items() if k not in ("nummer", "kundennr", "kunde")}
ROHR = dict(B.POSITIONEN[0], satz=None, je_satz=None)          # RR 42,4x2,0 S235
K1 = db.zeilen("kunden")[0]["kundennr"]


def angebot(*positionen, kopf=None):
    i = db.angebot_neu(dict(KOPF, kundennr=K1, kunde="Kunde", **(kopf or {})))
    for p in positionen:
        db.position_neu(i, p)
    return f.angebot_oeffnen(i)


def nach(s, artikel):
    return next(p for p in s.positionen if p.get("artikel") == artikel)


# ------------------------------------------------------------------ 1 Rechenkern
K = [dict(art=sw.BOHRUNG, d=8, anzahl=5, x=50, abstand=225, seite=0),        # Reihe über die Mitte (50 … 950)
     dict(art=sw.BOHRUNG, d=10, anzahl=1, x=960, seite=0),                    # hintere Hälfte
     dict(art=sw.LANGLOCH, l=20, b=8, anzahl=3, x=40, abstand=30, seite=90),  # vordere Hälfte (40 … 100)
     dict(art=sw.BOHRUNG, d=6, anzahl=2)]                                     # ohne Lage
neu, fehler = tf.konturen_anpassen(K, 1000, 800, {0: 4, 2: 4})
assert not fehler, fehler
assert (neu[0]["x"], neu[0]["anzahl"], neu[0]["abstand"]) == (50, 4, 233.33), neu[0]       # 50 … 750
assert neu[1]["x"] == 760, neu[1]                                                       # 40 vor Ende B
assert (neu[2]["x"], neu[2]["abstand"]) == (40, 20), neu[2]                            # bleibt 40 … 100
assert neu[3] == K[3]
_, fehler = tf.konturen_anpassen(K, 1000, 90, {})
assert fehler and "außerhalb" in fehler[0], fehler
z = tf.zeilen_aus_text("Länge\tAnzahl\tArtikel\n1.250,5\t6\tA-1\n800\t\tA-2\n", ["laenge", "n1", "artikel"])
assert z == [dict(laenge=1250.5, n1=6, artikel="A-1"), dict(laenge=800, n1=None, artikel="A-2")], z
assert tf.zeilen_aus_text("700;3", ["laenge", "n1"]) == [dict(laenge=700, n1=3)]
assert tf.bezeichnung_vorschlag("Sprosse L=1000", dict(laenge=850)) == "Sprosse L=850"
eb = dict(werkstoff="x", dicke=3, art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=300, breite=200,
          konturen=[dict(art=sw.BOHRUNG, d=10, anzahl=1, x=30, y=30), dict(art=sw.BOHRUNG, d=10, anzahl=1, x=270, y=170)],
          step=True)
e2, fehler = tf.blech_eingaben(eb, dict(laenge=400, breite=250))
assert not fehler and (e2["laenge"], e2["breite"]) == (400, 250) and "step" not in e2
assert [(k["x"], k["y"]) for k in e2["konturen"]] == [(30, 30), (370, 220)], e2["konturen"]
ok("Rechenkern: Konturen mitziehen, Lochreihe neu verteilen, Excel-Zeilen, Blech Länge/Breite")

# ------------------------------------------------------------------ 2 Angebot: Rohr, Blech, Fenster, Vorlage
E = dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, d=8, anzahl=5, x=50, abstand=225, seite=0),
                               dict(art=sw.BOHRUNG, d=10, anzahl=1, x=960, seite=0)])
s = angebot(dict(ROHR, pos=10, artikel="SP", bezeichnung="Sprosse", laenge=1000, stueck=20))
assert s.schneidweg_berechnen(zeile=0, eingaben=E)
quelle = nach(s, "SP")
ids = s.teilefamilie(zeile=0, zeilen=[dict(laenge=800, artikel="SP-80", bezeichnung="Sprosse L=800", n1=4),
                                      dict(laenge=1200, artikel="SP-120", bezeichnung="Sprosse L=1200", stueck=5)])
assert len(ids) == 2, ids
a, b = nach(s, "SP-80"), nach(s, "SP-120")
assert (a["laenge"], a["stueck"], b["laenge"], b["stueck"]) == (800, 20, 1200, 5), (a, b)
ka, kb = sw.lesen(a["technik"])["konturen"], sw.lesen(b["technik"])["konturen"]
assert (ka[0]["anzahl"], ka[0]["abstand"], ka[1]["x"]) == (4, 233.33, 760), ka
assert kb[1]["x"] == 1160 and a["einstiche"] == quelle["einstiche"] - 1 and b["schneidweg"] == quelle["schneidweg"]
assert a["pos"] > quelle["pos"] and nach(s, "SP")["laenge"] == 1000          # das Teil selbst bleibt
ok("Angebot: Rohr-Familie wie aus dem Rohr-Editor gerechnet (Konturen, Einstiche, Schneidweg), Teil bleibt")

daten = db.blech_daten()
wst = sorted(daten["werkstoffe"])[0]
eb = dict(eb, werkstoff=wst)
eb.pop("step")
erg = blech.rechnen(dict(eb, stueck=10), daten["werkstoffe"], daten["laser"], daten["einst"])
assert s._blech_anlegen(eb, erg, dict(bezeichnung="Platte", artikelnr="PL-1", stueck=10, lieferant="Blech GmbH"))
zb = s.positionen.index(nach(s, "PL-1"))
assert [v for v, _ in tf.basis(s.positionen[zb])["variablen"]] == ["laenge", "breite", "stueck", "werkstoff_id"]
ids = s.teilefamilie(zeile=zb, zeilen=[dict(laenge=400, breite=250, artikel="PL-2", bezeichnung="Platte 400")])
p2 = nach(s, "PL-2")
e2 = blech.lesen(p2["technik"])
assert len(ids) == 1 and (e2["laenge"], e2["breite"]) == (400, 250) and p2["art"] == "Zukaufteil"
st = (s.db.zukauf_stand(p2_aid := json.loads(p2["zukauf"])[0]["artikel_id"]))
assert st and p2_aid != json.loads(nach(s, "PL-1")["zukauf"])[0]["artikel_id"]
assert e2["richtpreise"][0]["preis"] > erg["richtpreis"]                  # größer = teurer
ok("Angebot: Blech-Familie mit eigenem Zukaufartikel und Richtpreis")

gesehen = {}


def fenster_bedienen(d):
    d.variable_setzen("n1")
    gesehen["start"] = d.zeilen()
    n = d.einfuegen("Länge\tAnzahl Bohrung\tArtikel\tBezeichnung\n600\t3\tSP-60\t\n700,5\t4\tSP-60\t")
    gesehen["doppelt"] = dict(d.fehler())
    d.tabelle.item(1, 2).setText("SP-70")
    gesehen["fehler"] = dict(d.fehler())
    gesehen["n"] = n
    gesehen["vorlage"] = d.als_vorlage("Sprossen")
    d._ok()
    return d.result()


ids = s.teilefamilie(zeile=s.positionen.index(nach(s, "SP")), dialog=fenster_bedienen)
assert gesehen["start"][0]["artikel"] == "SP-1" and gesehen["n"] == 2, gesehen
assert -1 in gesehen["doppelt"] and "mehrfach" in gesehen["doppelt"][-1][0] and not gesehen["fehler"], gesehen
assert len(ids) == 2 and nach(s, "SP-70")["laenge"] == 700.5 and nach(s, "SP-60")["bezeichnung"] == "Sprosse L=600"
v = next(x for x in db.zeilen(positionsvorlagen.TABELLE) if x["id"] == gesehen["vorlage"])
assert tf.aus_vorlage(v)[1][1]["artikel"] == "SP-70" and "Teilefamilie mit 2" in v["inhalt"]
s2 = angebot()
pid = s2.position_aus_vorlage(v["id"])
assert pid and sorted(p["artikel"] for p in s2.positionen) == ["SP-60", "SP-70"], [p["artikel"] for p in s2.positionen]
ok("Fenster: Excel einfügen, doppelte Artikel gemeldet, Vorlage legt die ganze Familie an")

# ------------------------------------------------------------------ 3 Editoren
def familie_500(d):
    if "n1" in d.haken:
        d.variable_setzen("n1")
    d.setzen([dict(laenge=500, artikel="E-500", bezeichnung="Editor 500", **({"n1": 2} if "n1" in d.haken else {}))])
    d._ok()
    return d.result()


def rohr_editor(d):
    assert d.editor.familie_knopf.isEnabled()
    assert d.editor.teilefamilie(dialog=familie_500) == 1 and d.editor.familie_knopf.text() == "Teilefamilie (1)"
    return QDialog.Accepted


s3 = angebot(dict(ROHR, pos=10, artikel="R", bezeichnung="Rohr", laenge=1000, stueck=3))
assert s3.schneidweg_berechnen(zeile=0, eingaben=E)
assert s3.schneidweg_berechnen(zeile=0, dialog=rohr_editor)
r = nach(s3, "E-500")
assert r["laenge"] == 500 and sw.lesen(r["technik"])["konturen"][0]["anzahl"] == 2


def rohr_neu(d):
    d.k_laenge.setValue(700)
    d.k_artikel.setText("N-1")
    d.editor.teilefamilie(dialog=lambda x: (x.setzen([dict(laenge=900, artikel="N-2", bezeichnung="Neu 900")]),
                                            x._ok(), x.result())[2])
    return QDialog.Accepted


assert s3.rohr_neu(dialog=rohr_neu)
assert nach(s3, "N-1")["laenge"] == 700 and nach(s3, "N-2")["laenge"] == 900


def blech_editor(d):
    d.eingaben_setzen(dict(eb, stueck=4))
    d.editor.teilefamilie(dialog=lambda x: (x.setzen([dict(laenge=350, breite=210, artikel="B-2", bezeichnung="B2")]),
                                            x._ok(), x.result())[2])
    return QDialog.Accepted


assert s3.blech_neu(dialog=blech_editor)
assert blech.lesen(nach(s3, "B-2")["technik"])["laenge"] == 350
ok("Rohr-Editor (vorhanden und neu) und Blech-Editor: Knopf Teilefamilie, Teile entstehen mit OK")

s4 = angebot(dict(ROHR, pos=10, artikel="G-1", bezeichnung="Holm", laenge=1000, stueck=2),
             dict(ROHR, pos=20, artikel="G-2", bezeichnung="Sprosse", laenge=400, stueck=2), kopf=dict())
r1, r2 = (q["id"] for q in s4.positionen)
s4.pos_ansicht.clearSelection()


def bg_editor(d):
    d.teil_setzen(r1, True)
    d.teil_setzen(r2, True)
    d.aktualisieren()
    d.wahl_3d = [r2]
    d.teile_tab.clearSelection()
    n = d.teilefamilie_teil(dialog=lambda x: (x.setzen([dict(laenge=450, artikel="G-3", bezeichnung="Sprosse 450")]),
                                              x._ok(), x.result())[2], melden=False)
    assert n and "1 weitere" in str(n) or n == 1, n
    d._ok()
    return d.result()


assert s4.baugruppe_neu(dialog=bg_editor)
g2, g3 = nach(s4, "G-2"), nach(s4, "G-3")
assert g3["bg_knoten"] and g3["bg_knoten"] == g2["bg_knoten"] and g3["laenge"] == 450, (g2["bg_knoten"], g3)
s5 = angebot(dict(ROHR, pos=10, artikel="S-1", laenge=800, satz="S1", je_satz=1),
             dict(ROHR, pos=20, artikel="S-2", laenge=600, satz="S1", je_satz=2))


def satz_editor(d):
    d.wahl_3d = [nach(s5, "S-2")["id"]]
    d.teile_tab.clearSelection()
    d.teilefamilie_teil(dialog=lambda x: (x.setzen([dict(laenge=650, artikel="S-3", bezeichnung="Satzteil")]),
                                          x._ok(), x.result())[2], melden=False)
    d._ok()
    return d.result()


assert s5.satz_3d(satz="S1", dialog=satz_editor)
s3_ = nach(s5, "S-3")
assert (s3_["satz"], s3_["je_satz"], s3_["laenge"]) == ("S1", 2, 650), s3_
ok("Schweißbaugruppe und Satz in 3D: Teilefamilie aus dem markierten Teil landet in derselben Baugruppe/demselben Satz")

# ------------------------------------------------------------------ 4 Vorrichtung
bg = dict(baugruppe.leer(), stamm={})
pos = [dict(id=1, art="Rohrlaserteil", laenge=1250, bg_knoten=bg["id"], je_knoten=2),
       dict(id=2, art="Rohrlaserteil", laenge=400, bg_knoten=bg["id"]),
       dict(id=3, art="Zukaufteil", bg_knoten=bg["id"], je_knoten=8)]           # Schrauben zählen nicht
v1 = vorrichtung.vorschlag(bg, pos, {})
assert (v1["teile"], v1["groesse"], v1["faktor_groesse"], v1["betrag"]) == (3, 1250, 1.5, 337.5), v1
assert v1["richtwert"] and "längstes Einzelteil" in v1["text"]
bg[vorrichtung.TOLERANZ] = True
bg["stamm"]["abmessungen"] = "1600 x 800 x 400"
v2 = vorrichtung.vorschlag(bg, pos, dict(schweiss_regeln=[dict(art="Vorrichtung", wert="Grundbetrag", zahl=200.0,
                                                                status="geprüft")]))
assert (v2["groesse"], v2["faktor_groesse"], v2["betrag"]) == (1600, 2.0, 825.0), v2      # (200+75)×2×1,5
vorrichtung.uebernehmen(bg, v2["betrag"])
assert [(a["name"], a["einmal_eur"]) for a in bg["arbeitsgaenge"]] == [("Vorrichtung", 825.0)]
fehlt = baugruppe.richtwerte_fehlend({})["schweiss_regeln"]
assert {"Grundbetrag", "Faktor enge Toleranz"} <= {z["wert"] for z in fehlt if z["art"] == "Vorrichtung"}
ok("Vorrichtung: Vorschlag aus Teilen, Größe (Teil bzw. Abmessungen), enger Toleranz; eigene Werte, Richtwerte laden")

# früher beauftragte Baugruppe desselben Kunden mit Vorrichtung
alt = dict(baugruppe.leer(), arbeitsgaenge=[dict(id="v", name="Vorrichtung", einmal_eur=480.0,
                                                 umlage=baugruppe.UMLAGE_AUFTRAG)])
s6 = angebot(dict(art=BAUGRUPPE, pos=10, artikel="RAHMEN-7", bezeichnung="Rahmen", stueck=5,
                  baugruppe=baugruppe.speichern(alt)))
db.vorgang_setzen(s6.id, "Beauftragt")
tr = vorrichtung.frueher(db, None, K1, "rahmen-7 ", "")
assert tr and tr["betrag"] == 480.0 and tr["angebot_id"] == s6.id, tr
assert vorrichtung.frueher(db, s6.id, K1, "RAHMEN-7", "") is None                 # nicht das eigene Angebot
assert vorrichtung.frueher(db, None, "anderer", "RAHMEN-7", "") is None
s7 = angebot(dict(ROHR, pos=10, artikel="T-1", laenge=900, stueck=5))
gesehen.clear()


def bg_wieder(d):
    d.bezeichnung.setText("Rahmen")
    d.artikel.setText("RAHMEN-7")
    d.teil_setzen(s7.positionen[0]["id"], True)
    d.aktualisieren()
    gesehen["wieder_sichtbar"] = not d.wieder_knopf.isHidden()
    gesehen["meldung"] = any("schon vorhanden" in t for t in d._rahmen_meldungen())
    gesehen["betrag"] = d.vorrichtung_vorschlag_uebernehmen()
    gesehen["n"] = d.vorrichtung_wieder_uebernehmen()
    gesehen["danach"] = not d.wieder_knopf.isHidden()
    d._ok()
    return d.result()


# der Hinweis braucht Artikel/Bezeichnung beim Öffnen: Baugruppe mit Artikel anlegen, dann bearbeiten
s7.baugruppe_neu(dialog=lambda d: (d.artikel.setText("RAHMEN-7"), d.bezeichnung.setText("Rahmen"),
                                   d.teil_setzen(s7.positionen[0]["id"], True), d.aktualisieren(), d._ok(),
                                   d.result())[-1])
zbg = next(i for i, p in enumerate(s7.positionen) if p.get("art") == BAUGRUPPE)
assert s7.baugruppe_bearbeiten([zbg], dialog=bg_wieder)
assert gesehen["wieder_sichtbar"] and gesehen["meldung"] and gesehen["betrag"] == 262.5 and gesehen["n"] == 1, gesehen
assert not gesehen["danach"]
bg7 = baugruppe.lesen(next(p for p in s7.positionen if p.get("art") == BAUGRUPPE)["baugruppe"])
assert [(a["einmal_eur"], a["umlage"]) for a in bg7["arbeitsgaenge"] if vorrichtung.ist_vorrichtung(a)] == \
    [(262.5, baugruppe.UMLAGE_WIEDER)], bg7["arbeitsgaenge"]
ok("Wiederholauftrag: Hinweis „Vorrichtung schon vorhanden“, Übernehmen rechnet sie als wiederverwendbar")
print("Alle Prüfungen bestanden.")
