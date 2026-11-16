"""Plan Schweißbaugruppe 10.11.2026, Schritt 2 „Berechnung automatisch“ (Freigabe Patrick „Alles umsetzen“):
- A1 Einzelteil außerhalb des Baugruppen-Editors geändert: Vorschläge der Baugruppe werden nachgerechnet (nur mit
  „Vorkalkulation automatisch“, nur eigener Entwurf), Werte von Hand und bestätigte bleiben
- A2 leere Schweiß-Stammdaten: Richtwerte einmal selbst laden (mit Rückgängig)
- A3 geänderte Kennwerte der Stammdaten: ungeprüfte Nahtgruppen sofort, geprüfte nur per Knopf
- A4 jede automatische Änderung wird gemeldet

Aufruf: python tests/test_bg_automatik.py
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

from rohrlaser import baugruppe, vorkalk  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication(sys.argv)
from rohrlaser.fenster import Hauptfenster  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "auto.db")
db.einstellung_setzen("mindestpreis", 0.0)
assert db.einstellung("schweiss_vk_step") == "ja"
SW_T = ("schweissverfahren", "schweiss_kennwerte", "schweiss_faktoren", "schweiss_regeln")
assert not any(db.anzahl(t) for t in SW_T), "neue Datei: Schweiß-Stammdaten leer"


def bg_neu(auto=True):
    g = baugruppe.leer()
    g["stamm"]["vk_auto"] = auto
    g["naehte"] = [dict(id="n1", knoten="", nr="1", verfahren="MAG", nahtart="Kehlnaht", mass=3, dicke=3,
                        laenge_aus="rundum Teil", laenge=149.7, laenge_auto=149.7, anzahl=4)]
    return g


a = db.angebot_neu(dict(kunde="Automatik", maschine="T11"))
g = bg_neu()
pid_bg = db.position_neu(a, dict(pos=100, art=BAUGRUPPE, artikel="A1", bezeichnung="Rahmen", stueck=1,
                                 baugruppe=baugruppe.speichern(g)))
pid_rohr = db.position_neu(a, dict(pos=10, artikel="Rohr", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                                   laenge=1000, stueck=1, schneidweg=320, einstiche=2, bg_knoten=g["id"], je_knoten=4))
pid_strebe = db.position_neu(a, dict(pos=20, artikel="Strebe", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                                     laenge=500, stueck=1, schneidweg=320, einstiche=2, bg_knoten=g["id"],
                                     je_knoten=2))
g_ = baugruppe.lesen(db.positionen(a)[0]["baugruppe"])
g_["naehte"][0]["laenge_teil"] = pid_rohr
db.position_aendern(pid_bg, "baugruppe", baugruppe.speichern(g_))

f = Hauptfenster(db, stumm=True)
seite = f.angebot_oeffnen(a)


def bg_jetzt():
    return baugruppe.lesen(next(p for p in db.positionen(a) if p["id"] == pid_bg)["baugruppe"])


def ag(bg, art):
    return next((x for x in bg["arbeitsgaenge"] if (x.get("vk") or {}).get("art") == art), None)


# ------------------------------------------------------------------ A2 Richtwerte selbst laden
assert not bg_jetzt()["arbeitsgaenge"], "erste Sicht auf das Angebot rechnet nichts"
n = seite.schweiss_richtwerte_auto()
assert n > 0 and all(db.anzahl(t) for t in SW_T)
assert "Richtwerte geladen" in f.letzte_meldung and f.letzte_aktion[0] == "Rückgängig"
f.letzte_aktion[1]()
assert not any(db.anzahl(t) for t in SW_T), "Rückgängig entfernt genau die geladenen Zeilen"
assert seite.schweiss_richtwerte_auto() == n
assert seite.schweiss_richtwerte_auto() == 0, "nur wenn alles leer ist"
ok(f"A2 leere Schweiß-Stammdaten: {n} Richtwerte selbst geladen, Rückgängig, kein zweites Mal")

# ------------------------------------------------------------------ A1 Teil außerhalb des Editors geändert
seite.neu_laden()
assert not bg_jetzt()["arbeitsgaenge"], "ohne Änderung der Teile bleibt die Baugruppe, wie sie ist"
db.position_aendern(pid_rohr, "profil_id", "RE 60x40x3")          # anderes Profil: Umfang und Gewicht ändern sich
seite.neu_laden()
b1 = bg_jetzt()
assert f.letzte_meldung.startswith("Automatisch nachgerechnet") and "Rahmen" in f.letzte_meldung, f.letzte_meldung
assert "€ je Baugruppe" in f.letzte_meldung
nt = b1["naehte"][0]
assert nt["laenge"] > 160 and nt["laenge"] == nt["laenge_auto"], "Nahtlänge folgt dem Umfang des neuen Profils"
assert vorkalk.naht_status(nt, "heftpunkte") == vorkalk.VORSCHLAG and nt["heftpunkte"] >= 3
assert ag(b1, vorkalk.RUESTEN) and ag(b1, vorkalk.POSITIONIEREN) and ag(b1, vorkalk.PRUEFEN)
pos_alt = ag(b1, vorkalk.POSITIONIEREN)["zeit_min"]
# weiteres Teil in die Baugruppe: Rüsten (je Teilenummer) und Positionieren steigen
meldung = f.letzte_meldung
seite.neu_laden()
assert bg_jetzt() == b1 and f.letzte_meldung == meldung, "nichts geändert: keine neue Rechnung, keine Meldung"
pid_neu = db.position_neu(a, dict(pos=30, artikel="Fuß", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                                  laenge=200, stueck=1, schneidweg=320, einstiche=2, bg_knoten=g["id"], je_knoten=4))
seite.neu_laden()
b2 = bg_jetzt()
assert ag(b2, vorkalk.POSITIONIEREN)["zeit_min"] > pos_alt
nah(ag(b2, vorkalk.RUESTEN)["ruest_min"], ag(b1, vorkalk.RUESTEN)["ruest_min"] + 1.0, "eine Teilenummer mehr")
# Wert von Hand und bestätigter bleiben
b = bg_jetzt()
ag(b, vorkalk.RUESTEN)["ruest_min"] = 45.0                           # von Hand
b["naehte"][0]["vk"]["heftpunkte"]["status"] = vorkalk.BESTAETIGT
heft = b["naehte"][0]["heftpunkte"]
db.position_aendern(pid_bg, "baugruppe", baugruppe.speichern(b))
seite.neu_laden()
db.position_aendern(pid_rohr, "profil_id", "RE 120x60x4")
seite.neu_laden()
b3 = bg_jetzt()
assert ag(b3, vorkalk.RUESTEN)["ruest_min"] == 45.0 and vorkalk.ag_status(ag(b3, vorkalk.RUESTEN)) == vorkalk.HAND
assert b3["naehte"][0]["heftpunkte"] == heft, "bestätigte Heftpunkte bleiben"
assert b3["naehte"][0]["laenge"] > b2["naehte"][0]["laenge"]
ok("A1 Profil geändert / Teil dazu: Nahtlänge, Heftpunkte, Rüsten, Positionieren nachgerechnet und gemeldet; "
   "Hand und bestätigt bleiben, ohne Änderung keine Rechnung")

# Häkchen aus: nichts; verschicktes Angebot: nichts
b = bg_jetzt()
b["stamm"]["vk_auto"] = False
db.position_aendern(pid_bg, "baugruppe", baugruppe.speichern(b))
seite.neu_laden()
vor = bg_jetzt()
db.position_aendern(pid_rohr, "profil_id", "QR 40x40x3")
seite.neu_laden()
assert bg_jetzt() == vor, "ohne 'Vorkalkulation automatisch' rechnet nichts von selbst"
b = bg_jetzt()
b["stamm"]["vk_auto"] = True
db.position_aendern(pid_bg, "baugruppe", baugruppe.speichern(b))
seite.neu_laden()
assert seite.bg_automatik_moeglich()
db.vorgang_setzen(a, "Verschickt")
seite.neu_laden()
assert not seite.bg_automatik_moeglich()
vor = bg_jetzt()
db.position_aendern(pid_rohr, "profil_id", "RE 60x40x3")
seite.neu_laden()
assert bg_jetzt() == vor, "verschicktes Angebot ändert sich nicht von selbst"
db.vorgang_setzen(a, "Entwurf")
seite.neu_laden()
ok("A1 nur mit Häkchen 'Vorkalkulation automatisch' und nur im eigenen Entwurf")

# ------------------------------------------------------------------ A3 Kennwerte der Stammdaten geändert
b = bg_jetzt()
tab = db.tabellen()
offen_, fest = dict(b["naehte"][0], id="o", nr="8"), dict(b["naehte"][0], id="f", nr="9")
for x in (offen_, fest):
    x.pop("laenge_aus", None)
    x["vk"] = {k_: dict(v, status=vorkalk.VORSCHLAG) for k_, v in x["vk"].items()}
    x["stand"] = baugruppe.naht_stand(x, tab)
fest["vk"] = {k_: dict(v, status=vorkalk.BESTAETIGT) for k_, v in fest["vk"].items()}
assert vorkalk.naht_offen(offen_) and not vorkalk.naht_offen(fest)
b["naehte"] = [offen_, fest]
db.position_aendern(pid_bg, "baugruppe", baugruppe.speichern(b))
seite.neu_laden()
assert not any(baugruppe.stand_veraltet(x, db.tabellen()) for x in bg_jetzt()["naehte"])
z = next(z for z in db.zeilen("schweiss_kennwerte")
         if (z["verfahren"], z["nahtart"], z["mass_bis"]) == ("MAG", "Kehlnaht", 3))
db.aendern("schweiss_kennwerte", z["id"], "min_m", z["min_m"] * 2)
f.alles_neu_laden()
b4 = {x["id"]: x for x in bg_jetzt()["naehte"]}
nah(b4["o"]["stand"]["min_m"], z["min_m"] * 2, "ungeprüfte Nahtgruppe: neuer Kennwert")
nah(b4["f"]["stand"]["min_m"], z["min_m"], "geprüfte Nahtgruppe: alter Kennwert bleibt")
assert baugruppe.stand_veraltet(b4["f"], db.tabellen()) and not baugruppe.stand_veraltet(b4["o"], db.tabellen())
assert "Kennwerte aus den Stammdaten" in f.letzte_meldung or "nachgerechnet" in f.letzte_meldung
ok("A3 Kennwert in den Stammdaten verdoppelt: ungeprüfte Nahtgruppe übernimmt ihn sofort, geprüfte bleibt "
   "(Hinweis im Editor)")
# ------------------------------------------------------------------ G3 im Programm: alte Richtwerte staffeln
alt = {(x["verfahren"], x["nahtart"], x["mass_bis"]): x["min_m"] for x in baugruppe.richtwerte(False)["schweiss_kennwerte"]}
neu = {(x["verfahren"], x["nahtart"], x["mass_bis"]): x["min_m"] for x in baugruppe.richtwerte()["schweiss_kennwerte"]}
for x in db.zeilen("schweiss_kennwerte"):          # Stand einer Installation vor 0.9.278: alte Richtwerte
    db.aendern("schweiss_kennwerte", x["id"], "min_m", alt[(x["verfahren"], x["nahtart"], x["mass_bis"])])
hand = next(x for x in db.zeilen("schweiss_kennwerte")
            if (x["verfahren"], x["nahtart"], x["mass_bis"]) == ("WIG", "Kehlnaht", 3))
db.aendern("schweiss_kennwerte", hand["id"], "status", "geprüft")
seite_kw = next(s_ for s_ in f.seiten if s_.t.name == "schweiss_kennwerte")
assert seite_kw.schweiss_richtwerte() == 0 and f.letzte_aktion[0] == "Nach Nahtgröße staffeln"
assert "alten Richtwert" in f.letzte_meldung
n_st = f.letzte_aktion[1]()
jetzt = {(x["verfahren"], x["nahtart"], x["mass_bis"]): x["min_m"] for x in db.zeilen("schweiss_kennwerte")}
assert n_st > 0 and jetzt[("MAG", "Kehlnaht", 3)] == neu[("MAG", "Kehlnaht", 3)]
assert jetzt[("WIG", "Kehlnaht", 3)] == alt[("WIG", "Kehlnaht", 3)], "geprüfte Zeile bleibt"
assert f.letzte_aktion[0] == "Rückgängig"
f.letzte_aktion[1]()
jetzt = {(x["verfahren"], x["nahtart"], x["mass_bis"]): x["min_m"] for x in db.zeilen("schweiss_kennwerte")}
assert jetzt[("MAG", "Kehlnaht", 3)] == alt[("MAG", "Kehlnaht", 3)]
ok(f"G3 Richtwerte laden bietet das Staffeln an: {n_st} Kennwerte umgestellt, geprüfte bleiben, Rückgängig")
print("Alle Tests bestanden.")
