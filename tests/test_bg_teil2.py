"""Plan Schweißbaugruppe Teil 2 (13.11.2026, Freigabe Patrick „Alle Empfehlungen“):
- G5 Vorwärmen dicker Stahlnähte, G6 Prüfumfang (Zeit oder Fremdleistung), G7 Vorrichtung lohnt sich ab Stückzahl,
  G8 Sicherheit des Preises
- A5 neue Schweiß-Richtwerte als Aufgabe auf der Startseite (laden auf Klick, ausblendbar), A6 Schweißbaugruppen im
  Angebots-Check, A7 alle Schweißbaugruppen nachrechnen mit Rückgängig
- L5 Ergebnis oben fest, Abschnitte zuklappbar (gemerkt), L6 Knopfzeilen brechen um, L7 Preis von Hand immer sichtbar

Aufruf: python tests/test_bg_teil2.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import angebot_check, automatik, baugruppe, bg_sicherheit, klappe, schweiss_neu, vorkalk  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


def regeln(ohne=()):
    return [dict(art=a, wert=w, bis=b, zahl=z, status="geprüft") for a, w, b, z, _ in vorkalk.RICHTWERTE
            if a not in ohne]


def tab(r):
    return dict(schweissverfahren=[dict(verfahren="MAG", satz_id="Schweißen", lichtbogen=50, heft_s=6,
                                        status="geprüft")],
                schweiss_kennwerte=[dict(verfahren="MAG", nahtart=art, mass_bis=m, min_m=z, status="geprüft")
                                    for art in ("Kehlnaht", "Stumpfnaht", "Ecknaht")
                                    for m, z in ((3, 2.0), (6, 6.0), (10, 15.0), (25, 60.0))],
                schweiss_faktoren=[dict(art=a, wert=w, faktor=f, status="geprüft")
                                   for a, w, f in baugruppe.RICHT_FAKTOREN], schweiss_regeln=r)


def ag(bg, art):
    return next((x for x in bg["arbeitsgaenge"] if (x.get("vk") or {}).get("art") == art), None)


def gruppe(naehte):
    g = baugruppe.leer()
    g["naehte"] = naehte
    return g


def pos(g, stueck=10):
    return dict(id=1, pos=100, art=BAUGRUPPE, bezeichnung="B", stueck=stueck, baugruppe=baugruppe.speichern(g))


SAETZE = {"Schweißen": 60.0}
TAB, TAB_ALT = tab(regeln()), tab(regeln(vorkalk.NEU_1311))

# ------------------------------------------------------------------ G5 Vorwärmen
dick = dict(id="n1", knoten="", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=8, dicke=25, laenge=500, anzahl=2)
duenn = dict(id="n2", knoten="", nr="2", verfahren="MAG", nahtart="Kehlnaht", mass=3, dicke=4, laenge=500, anzahl=2)
g = gruppe([dict(dick), dict(duenn)])
r = vorkalk.vorkalkulieren(pos(g), [pos(g)], TAB)
v = ag(r["bg"], vorkalk.VORWAERMEN)
assert v is not None and vorkalk.ag_status(v) == vorkalk.VORSCHLAG
nah(v["zeit_min"], 1.0 * 2.0, "1 m dicke Naht × 2 min/m")
assert "ab 20 mm" in v["vk"]["text"]
r_alt = vorkalk.vorkalkulieren(pos(g), [pos(g)], TAB_ALT)
assert ag(r_alt["bg"], vorkalk.VORWAERMEN) is None and ag(r_alt["bg"], vorkalk.ZFP) is None, "ohne Regel wie bisher"
assert r_alt["vorrichtung"] is None
ohne = [a for a in r["bg"]["arbeitsgaenge"] if (a.get("vk") or {}).get("art") not in (vorkalk.VORWAERMEN, vorkalk.ZFP)]
werte = lambda liste: [(x["name"], x.get("zeit_min"), x.get("ruest_min"), x.get("menge")) for x in liste]  # noqa: E731
assert werte(ohne) == werte(r_alt["bg"]["arbeitsgaenge"]) and r["bg"]["naehte"] == r_alt["bg"]["naehte"], \
    "alles andere bitgleich zur Rechnung ohne die neuen Regeln"
g_va = gruppe([dict(dick, werkstoff="Edelstahl")])
g_va["naehte"][0]["vk"] = {"werkstoff": dict(status="hand", wert="Edelstahl")}
assert ag(vorkalk.vorkalkulieren(pos(g_va), [pos(g_va)], TAB)["bg"], vorkalk.VORWAERMEN) is None, "Edelstahl nicht"
assert ag(vorkalk.vorkalkulieren(pos(gruppe([dict(duenn)])), [pos(g)], TAB)["bg"], vorkalk.VORWAERMEN) is None
ok("G5 Vorwärmen: nur Stahlnähte ab 20 mm, 2 min je m; ohne Regel bitgleich")

# ------------------------------------------------------------------ G6 Prüfumfang
g = gruppe([dict(duenn, qualitaet="erhöht"), dict(duenn, id="n3", nr="3")])
r = vorkalk.vorkalkulieren(pos(g), [pos(g)], TAB)
z = ag(r["bg"], vorkalk.ZFP)
nah(z["zeit_min"], 1.0 * 0.10 * 15.0, "1 m erhöht × 10 % × 15 min/m")
assert not z.get("fremd") and z.get("satz_id") == "Schweißen"
fremd = [dict(x, zahl=40.0) if (x["art"], x["wert"]) == ("Prüfumfang", "Fremdleistung je m geprüfte Naht") else x
         for x in regeln()]
r2 = vorkalk.vorkalkulieren(pos(r["bg"]), [pos(g)], tab(fremd))
z2 = ag(r2["bg"], vorkalk.ZFP)
assert z2["fremd"] is True and "zeit_min" not in z2 and "satz_id" not in z2
nah(z2["menge"], 0.1)
nah(z2["kosten_einheit"], 40.0)
e2 = baugruppe.rechnen(pos(r2["bg"]), tab(fremd), SAETZE)
zeile = next(x for x in e2["zeilen"] if x["id"] == z2["id"])
assert zeile["fremd"]
nah(zeile["kosten"], 4.0, "0,1 m × 40 €/m Fremdleistung")
r3 = vorkalk.vorkalkulieren(pos(r2["bg"]), [pos(g)], TAB)             # Regel wieder auf eigene Zeit
z3 = ag(r3["bg"], vorkalk.ZFP)
assert not z3.get("fremd") and "kosten_einheit" not in z3
nah(z3["zeit_min"], 1.5)
assert ag(vorkalk.vorkalkulieren(pos(gruppe([dict(duenn)])), [pos(g)], TAB)["bg"], vorkalk.ZFP) is None, \
    "Qualität normal: keine Prüfung über die Sichtprüfung hinaus"
ok("G6 Prüfumfang: 10 % der Nähte „erhöht“, als Zeit oder als Fremdleistung in € je m, zurück auf Zeit")

# ------------------------------------------------------------------ G8 Sicherheit des Preises
g = gruppe([dict(duenn), dict(dick)])
e = baugruppe.rechnen(pos(g), TAB, SAETZE)
s = bg_sicherheit.bewerten(g, e)
nah(s["anteile"][bg_sicherheit.GEPRUEFT], 1.0)
nah(s["spanne"], 10.0)
assert s["ampel"] == "grün" and s["kurz"] == "± 10 %"
richt = tab(regeln())
for zeile_ in richt["schweiss_kennwerte"]:
    zeile_["status"] = "Richtwert"
s = bg_sicherheit.bewerten(g, baugruppe.rechnen(pos(g), richt, SAETZE))
nah(s["spanne"], 25.0)
assert s["ampel"] == "rot" and "100 % Richtwert" in s["text"]
gh = gruppe([dict(duenn, zeit_hand=5), dict(dick)])
s = bg_sicherheit.bewerten(gh, baugruppe.rechnen(pos(gh), TAB, SAETZE))
assert 0 < s["anteile"][bg_sicherheit.HAND] < 1 and 5 < s["spanne"] < 10
rv = vorkalk.vorkalkulieren(pos(g), [pos(g)], TAB)["bg"]
s = bg_sicherheit.bewerten(rv, baugruppe.rechnen(pos(rv), TAB, SAETZE))
assert s["anteile"][bg_sicherheit.VORSCHLAG] > 0 and s["spanne"] > 10, "offene Vorschläge senken die Sicherheit"
vorkalk.bestaetigen(rv)
s = bg_sicherheit.bewerten(rv, baugruppe.rechnen(pos(rv), TAB, SAETZE))
nah(s["anteile"][bg_sicherheit.VORSCHLAG], 0.0)
s = bg_sicherheit.bewerten(g, e, dict(faktor=1.2, art="dieselbe", angebot="A-1"))
assert "Ist +20 %" in s["text"]
assert bg_sicherheit.bewerten(gruppe([]), baugruppe.rechnen(pos(gruppe([])), TAB, SAETZE)) is None
ok("G8 Sicherheit: geprüft ± 10 % grün, Richtwert ± 25 % rot, Hand und offene Vorschläge gewichtet, Nachkalkulation")

# ------------------------------------------------------------------ Oberfläche: A5, A6, A7, G7, L5–L7
app = QApplication.instance() or QApplication(sys.argv)
from rohrlaser.fenster import Hauptfenster  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "teil2.db")
db.einstellung_setzen("mindestpreis", 0.0)
f = Hauptfenster(db, stumm=True)
assert schweiss_neu.text(db) == "", "leere Stammdaten: keine Aufgabe (Richtwerte kommen beim Vorkalkulieren selbst)"
for name, zeilen in baugruppe.richtwerte().items():      # Stand vor Teil 2: alle Richtwerte ohne die neuen Regeln
    for z in zeilen:
        if not (name == "schweiss_regeln" and z["art"] in vorkalk.NEU_1311):
            db.neu(name, z)
n_alt = db.anzahl("schweiss_regeln")
t = schweiss_neu.text(db)
neu_n = sum(1 for x in vorkalk.RICHTWERTE if x[0] in vorkalk.NEU_1311)
assert t.startswith(f"Neue Schweiß-Richtwerte verfügbar: {neu_n} Regel(n)") and "Vorwärmen" in t and "Prüfumfang" in t
assert any(x["art"] == "schweiss_richtwerte" for x in automatik.aufgaben(db))
assert f.schweiss_richtwerte_neu("nein") == 0 and db.anzahl("schweiss_regeln") == n_alt
assert f.schweiss_richtwerte_neu("laden") == neu_n and db.anzahl("schweiss_regeln") == n_alt + neu_n
assert schweiss_neu.text(db) == "" and f.letzte_aktion[0] == "Rückgängig"
f.letzte_aktion[1]()
assert db.anzahl("schweiss_regeln") == n_alt and schweiss_neu.text(db), "Rückgängig: wieder als Aufgabe"
f.schweiss_richtwerte_neu("aus")
assert schweiss_neu.text(db) == "" and db.anzahl("schweiss_regeln") == n_alt, "ausgeblendet, nichts geladen"
assert not any(x["art"] == "schweiss_richtwerte" for x in automatik.aufgaben(db))
db.einstellung_setzen(schweiss_neu.AUS, [])
assert f.schweiss_richtwerte_neu("laden") == neu_n
ok(f"A5 neue Richtwerte: Aufgabe auf der Startseite, {neu_n} Regeln auf Klick geladen, Rückgängig, ausblendbar")

a = db.angebot_neu(dict(kunde="Teil 2", maschine="T11"))
g = baugruppe.leer()
g["stamm"]["vk_auto"] = True
g["naehte"] = [dict(id="n1", knoten="", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, dicke=3, laenge=150,
                    anzahl=4, qualitaet="erhöht")]
pid_bg = db.position_neu(a, dict(pos=100, art=BAUGRUPPE, artikel="A1", bezeichnung="Rahmen", stueck=200,
                                 baugruppe=baugruppe.speichern(g)))
for nr, lg in ((10, 1000), (20, 500), (30, 300)):
    db.position_neu(a, dict(pos=nr, artikel=f"T{nr}", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=lg,
                            stueck=1, schneidweg=320, einstiche=2, bg_knoten=g["id"], je_knoten=2))
seite = f.angebot_oeffnen(a)


def bg_jetzt():
    return baugruppe.lesen(next(p for p in db.positionen(a) if p["id"] == pid_bg)["baugruppe"])


# A7 alle nachrechnen
assert not bg_jetzt()["arbeitsgaenge"]
liste = seite.baugruppen_alle_nachrechnen()
assert len(liste) == 1 and liste[0][0] and liste[0][2] > liste[0][1], liste
b = bg_jetzt()
assert ag(b, vorkalk.RUESTEN) and ag(b, vorkalk.POSITIONIEREN) and ag(b, vorkalk.ZFP), "Vorschläge neu, auch Prüfumfang"
assert "1 Schweißbaugruppe(n) nachgerechnet" in f.letzte_meldung and f.letzte_aktion[0] == "Rückgängig"
assert seite.baugruppen_alle_nachrechnen() == [] and "sind aktuell" in f.letzte_meldung
ok("A7 alle Schweißbaugruppen nachrechnen: Vorschläge neu, Vorher-Nachher gemeldet, zweites Mal nichts")

# A6 Angebots-Check
seite = f.angebot_oeffnen(a)
punkte = seite.freigabe_punkte()
p_bg = [p for p in punkte if "Schweißbaugruppe" in p.text and "Vorschläge der Vorkalkulation offen" in p.text]
assert len(p_bg) == 1 and p_bg[0].art == angebot_check.HINWEIS and p_bg[0].ziel.startswith("bg:"), punkte
zeile_bg = next(i for i, p in enumerate(seite.positionen) if p["id"] == pid_bg)
assert p_bg[0].ziel == f"bg:{zeile_bg}"
assert not angebot_check.offen(p_bg), "nur Hinweis, sperrt den Versand nicht"
bb = bg_jetzt()
vorkalk.bestaetigen(bb)
db.position_aendern(pid_bg, "baugruppe", baugruppe.speichern(bb))
seite.neu_laden()
punkte = seite.freigabe_punkte()
assert not any("Vorschläge der Vorkalkulation offen" in p.text for p in punkte)
assert any("ungeprüften Richtwerten" in p.text and p.ziel.startswith("bg:") for p in punkte), [p.text for p in punkte]
ok("A6 Angebots-Check: offene Vorschläge und ungeprüfte Richtwerte der Schweißbaugruppen als Hinweis mit Sprung")

# G7 Vorrichtung, L5–L7 im Fenster
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser.fluss import FlussLayout  # noqa: E402

klappe._SITZUNG.clear()
p = seite.positionen[zeile_bg]
d = BaugruppeDialog(seite, p, seite.positionen, seite.tabellen, seite._saetze(), db=db)
vv = d.vorrichtung_info
assert vv and vv["frei"] >= 2 and vv["lohnt"] and vv["ab_stueck"] <= 200, vv
assert any(m.startswith("HINWEIS: Vorrichtung:") and "rechnen sich ab" in m for m in d._rahmen_meldungen())
d.anzahl.setValue(2)
d.aktualisieren()
assert d.vorrichtung_info and not d.vorrichtung_info["lohnt"]
assert not any("Vorrichtung:" in m for m in d._rahmen_meldungen()), "bei 2 Stück kein Hinweis"
d.anzahl.setValue(200)
d.aktualisieren()
ok(f"G7 Vorrichtung: lohnt sich ab {vv['ab_stueck']} Baugruppen, Hinweis nur wenn die Stückzahl reicht")

d.kosten_neu()
assert "Zeit je Baugruppe" in d.kopf_rechts.text() and "Sicherheit" in d.kopf_rechts.text()
assert "Preis je Baugruppe" in d.kopf_rechts.text(), "mit Kostenübersicht: Verkaufspreis oben"
assert d.kopf_rechts.toolTip().startswith("Sicherheit der Fertigungskosten")
assert any(k[0] == "Sicherheit" for k in d._rahmen_kacheln())
kz, kk, kw = d.klappen["zeit"], d.klappen["kosten"], d.klappen["werte"]
assert not kz.offen() and not kk.offen() and not kw.offen(), "ohne Zeitvorgabe alles zu: kein Rollen"
assert d.zeit_feld.isHidden() and d.kosten_feld.isHidden() and d.summe.isHidden()
assert "min" in kz.kopf.text() and "automatisch" in kz.kopf.text() and "€" in kk.kopf.text()
kz.oeffnen()
assert not d.zeit_feld.isHidden() and kz.kopf.text() == "Kalkulation: Zeit"
assert db.einstellung(klappe.EINSTELLUNG) == {"bg_zeit": True}, "Zustand in der eigenen Datendatei gemerkt"
klappe._SITZUNG.clear()
d_neu = BaugruppeDialog(seite, p, seite.positionen, seite.tabellen, seite._saetze(), db=db)
assert d_neu.klappen["zeit"].offen() and not d_neu.klappen["kosten"].offen(), "beim nächsten Öffnen wie verlassen"
kz.oeffnen(False)
# L7: Preis von Hand außerhalb der zugeklappten Kostenübersicht, wirkt wie bisher
feld = d.kosten_feld.felder["preis"][1]
assert feld.parent() is d.preis_zeile and not d.preis_zeile.isHidden() and d.kosten_feld.isHidden()
feld.setText("999")
feld.editingFinished.emit()
assert d.bg["preis_hand"]["preis"] == 999.0
d.kosten_feld._zurueck("preis")
assert "preis_hand" not in d.bg
# L6: Knopfzeilen brechen um, die Reiter erzwingen keine Breite über dem Platz eines Laptops
assert len(d.findChildren(FlussLayout)) >= 3
for i in range(d.reiter.count()):
    if d.reiter.tabText(i) in ("Nahtgruppen", "Arbeitsgänge und Vorrichtungen", "Steckverbindungen"):
        assert d.reiter.widget(i).minimumSizeHint().width() <= 700, (d.reiter.tabText(i),
                                                                     d.reiter.widget(i).minimumSizeHint().width())
ok("L5–L7 Ergebnis oben fest mit Sicherheit, Abschnitte zuklappbar und gemerkt, Preis von Hand sichtbar, kein "
   "Rollbalken durch Knopfzeilen")
print("Alle Tests Schweißbaugruppe Teil 2 bestanden.")
