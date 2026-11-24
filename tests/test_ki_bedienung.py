"""KI 3 (Pakete B-Rest, C, D; Freigabe Patrick 20.11.2026 „Alles einbauen nach Empfehlungen“): Preisrisiko, englischer
Entwurf mit Zahlenprüfung, Lieferantenangebot aus der Mail mit Sprachmodell (nur mit Beleg), Absagegrund aus der
Mail (Regeln und Modell, Dialog), Hilfe aus der Anleitung, Fehlermeldungen erklären, Liefertermin und Engpässe,
Befehle in Worten für Bohrungen (Vorschlag, Übernehmen erst auf Klick) und die Fragen im KI-Assistenten.

Aufruf: python tests/test_ki_bedienung.py
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = Path(tempfile.mkdtemp())
os.environ["LOCALAPPDATA"] = str(TMP / "appdata")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import (absage, bohrbild, ki_agenten, ki_assistent, ki_auslesen, ki_befehle, ki_hilfe,  # noqa: E402
                       ki_kalkulation, ki_modelle, ki_orchestrator, lieferantenantwort, rechnen)
from rohrlaser.absage_dialog import AbsageDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
db = Datenbank(TMP / "rohrlaser.db")
f = Hauptfenster(db, TMP, stumm=True)
db.einstellung_setzen(ki_modelle.AKTIV, "nein")

bid = beispiel_angebot.anlegen(db)
kopf, pos = db.angebot(bid), db.positionen(bid)
M8 = dict(art="Bohrung", d=8.5, anzahl=4, gewinde="M10", status="offen")
db.position_aendern(pos[0]["id"], "bohrbild", bohrbild.schreiben([M8, dict(art="Bohrung", d=6.8, anzahl=2,
                                                                         gewinde="M8", status="offen")]))
pos = db.positionen(bid)
erg = rechnen.optimieren(kopf, pos, db.kontext())
db.profile_anlegen(erg.get("neue_profile") or [])
db.ergebnis_speichern(bid, erg)
db.con.commit()

# ------------------------------------------------------------------ Preisrisiko
r = ki_kalkulation.preisrisiko(ki_agenten.Kontext(db, bid))
assert r and r["stufe"] in ("niedrig", "mittel", "hoch") and r["text"].startswith("Preisrisiko"), r
db.einstellung_setzen("mindestmarge", 0.9)          # unrealistisch hoch: Marge muss als knapp zählen
r2 = ki_kalkulation.preisrisiko(ki_agenten.Kontext(db, bid))
assert any("Marge" in g["text"] for g in r2["gruende"]) and r2["punkte"] > r["punkte"], r2
db.einstellung_setzen("mindestmarge", 0.0)
ok("Preisrisiko: Stufe mit Gründen, knappe Marge zählt")

# ------------------------------------------------------------------ Englisch mit Zahlenprüfung
ANTWORT = {}


def modell(url, pfad, daten=None):
    if pfad == "/api/tags":
        return {"models": [{"name": "qwen3:8b", "size": 5_200_000_000, "details": {"parameter_size": "8.2B"}}]}
    if pfad in ("/api/ps",):
        return {"models": []}
    if pfad == "/api/version":
        return {"version": "0.12.0"}
    if pfad == "/api/generate":
        d = ANTWORT["d"]
        return {"response": d if isinstance(d, str) else json.dumps(d), "eval_count": 10,
                "eval_duration": 100_000_000}
    raise OSError(pfad)


de = "Der Preis beträgt 1.224,11 € für 152 Teile."
u = ki_kalkulation.uebersetzen(db, de, senden=modell)
assert not u["ok"] and u["text"] == de and "Sprachmodell" in u["hinweis"]
db.einstellung_setzen(ki_modelle.AKTIV, "ja")
ki_modelle.modelle(db, senden=modell)
ANTWORT["d"] = "The price is 1,224.11 € for 152 parts."
u = ki_kalkulation.uebersetzen(db, de, senden=modell)
assert u["ok"] and u["text"].startswith("The price"), u
ANTWORT["d"] = "The price is 1,300.00 € for 152 parts."           # erfundene Zahl
u = ki_kalkulation.uebersetzen(db, de, senden=modell)
assert not u["ok"] and u["text"] == de and 1300.0 in u["fremde_zahlen"], u
ok("Englischer Entwurf: nur mit lokalem Modell, erfundene Zahl verwirft die Übersetzung")

# ------------------------------------------------------------------ Lieferantenangebot: Regeln + KI-Stufe
paare = [("RR 42,4x2,0", "S235-10219"), ("QR 40x40x3", "S235-10219")]
profile = {p["profil_id"]: p for p in db.zeilen("profile")}
MAIL = ("Sehr geehrte Damen und Herren,\nfür Ihre Anfrage bieten wir an:\nRundrohr 42,4 x 2,0 S235: 1,85 €/kg\n"
        "Quadratrohr vierzig mal vierzig, Wand 3: Stangenpreis 41,20 EUR\nLieferzeit 5 Arbeitstage\n")
regel = lieferantenantwort.auslesen(MAIL, paare, profile)
assert [z["profil_id"] for z in regel] == ["RR 42,4x2,0"], regel
ANTWORT["d"] = {"preise": [{"profil": "QR 40x40x3", "preis": "41,20", "einheit": "Stange",
                            "beleg": "Quadratrohr vierzig mal vierzig, Wand 3: Stangenpreis 41,20 EUR"},
                           {"profil": "QR 40x40x3", "preis": "39,00", "einheit": "Stange",
                            "beleg": "Quadratrohr vierzig mal vierzig, Wand 3: Stangenpreis 41,20 EUR"},
                           {"profil": "RE 80x40x3", "preis": "2", "einheit": "kg", "beleg": "erfunden"}]}
ki_auslesen._CACHE.clear()
k = ki_auslesen.lieferant_ki(db, MAIL, [paare[1]], profile, senden=modell)
assert len(k) == 1 and k[0]["preis"] == 41.2 and k[0]["basis"] == "€/Stange" and k[0]["quelle"] == "KI", k
ok("Lieferantenangebot: Regeln zuerst, Sprachmodell für die Lücke nur mit wörtlichem Beleg und passender Zahl")

# ------------------------------------------------------------------ Absagegrund aus der Mail
v = ki_auslesen.absage_aus_text(db, "Hallo,\nleider war ein anderer Anbieter deutlich günstiger, er liegt bei "
                                    "1.050,00 €.\nGruß", mit_modell=False)
assert v["grund"] == "Preis zu hoch" and v["preis"] == 1050.0 and v["quelle"] == "Regel", v
v2 = ki_auslesen.absage_aus_text(db, "Leider haben wir uns für einen anderen Anbieter entschieden, der Preis lag bei "
                                 "2.380 Euro.", mit_modell=False)
assert v2["grund"] == "Preis zu hoch" and v2["preis"] == 2380, v2
assert ki_auslesen.absage_aus_text(db, "Das Projekt wurde leider verschoben.", mit_modell=False)["grund"] == \
    "Projekt verschoben oder gestrichen"
ANTWORT["d"] = {"grund": "Kunde fertigt selbst", "beleg": "Wir machen das künftig auf der eigenen Anlage."}
ki_auslesen._CACHE.clear()
v = ki_auslesen.absage_aus_text(db, "Danke für das Angebot.\nWir machen das künftig auf der eigenen Anlage.",
                                senden=modell)
assert v["grund"] == "Kunde fertigt selbst" and v["quelle"] == "KI", v
ANTWORT["d"] = {"grund": "Kunde fertigt selbst", "beleg": "nicht im Text"}
ki_auslesen._CACHE.clear()
assert ki_auslesen.absage_aus_text(db, "Danke, wir melden uns.", senden=modell) is None
d = AbsageDialog(None, dict(nummer="A-1", kunde="X"))
d.mail.setPlainText("Leider ist die Lieferzeit zu lang für uns.")
v = d.vorschlagen(db=db, mit_modell=False)
assert d.grund.currentText() == "Lieferzeit zu lang" and "Aus Mail" in d.bemerkung.text() and "prüfen" in \
    d.vorschlag_text.text()
assert d.grund.currentText() in absage.GRUENDE
ok("Absagegrund: Regeln, Wettbewerbspreis, Sprachmodell nur mit Beleg, Dialog füllt die Felder als Vorschlag")
db.einstellung_setzen(ki_modelle.AKTIV, "nein")

# ------------------------------------------------------------------ Hilfe, Fehler, Liefertermin
h = ki_hilfe.hilfe(db, "Wie lege ich einen Rahmenauftrag an?")
assert h and any("ahmen" in x["titel"] or "ahmen" in x["text"] for x in h), h
log = Path(db.pfad).parent / "Protokoll"
log.mkdir(exist_ok=True)
jetzt = datetime.datetime.now() - datetime.timedelta(hours=1)
(log / "fehler.log").write_text(
    f"{jetzt:%Y-%m-%d %H:%M:%S},100 ERROR export.speichern | PermissionError: [Errno 13] Permission denied: "
    f"'X.xlsx'\n{jetzt:%Y-%m-%d %H:%M:%S},200 ERROR step.lesen | No module named 'OCP'\n", encoding="utf-8")
fe = ki_hilfe.fehler_erklaeren(log)
assert len(fe) == 2 and any("STEP-Bibliothek" in x["erklaerung"] for x in fe) and \
    any("anderen Programm" in x["erklaerung"] for x in fe), fe
lt = ki_hilfe.liefertermin(db, bid, heute=datetime.date(2026, 11, 23))
assert lt["stunden"] and lt["kw"] == 48 and lt["liefertag"] > datetime.date(2026, 11, 27), lt
ok("Hilfe aus der Anleitung, Fehler mit Erklärung und Lösung, Liefertermin aus der Auslastung")

# ------------------------------------------------------------------ Befehle für Bohrungen
assert ki_befehle.lesen("Welche Bohrungen haben M10?") is None
assert ki_befehle.lesen("Wie teuer ist das Angebot") is None
b = ki_befehle.lesen("Alle Bohrungen Ø 8,5 als M10")
assert b["d"] == 8.5 and b["gewinde"] == "M10" and b["aus"] == bohrbild.GEWINDE_SCHNEIDEN, b
assert ki_befehle.lesen("Ø 6,8 als Einnietmutter M8")["aus"] == bohrbild.EINNIET
assert ki_befehle.lesen("Bohrungen Ø 6,8 ablehnen")["status"] == bohrbild.ABGELEHNT
ok("Befehle lesen: Ø, Gewinde, Ausführung, Ablehnen; Fragen sind keine Befehle")

seite = f.angebot_oeffnen(bid) or f._seite()
ass = ki_assistent.zeigen(f)
vorher = db.positionen(bid)[0]["bohrbild"]
e = ass.fragen("Alle Bohrungen Ø 8,5 als M10", mit_modell=False)
assert e["absicht"] == "befehl" and e["aktion"] and "M10" in e["text"] and ass.uebernehmen_knopf.isEnabled(), e
assert db.positionen(bid)[0]["bohrbild"] == vorher                  # erst Vorschlag, nichts geändert
assert ass.uebernehmen()
neu = bohrbild.lesen(db.positionen(bid)[0]["bohrbild"])
z = next(x for x in neu if abs(x["d"] - 8.5) < 0.01)
assert z["status"] == bohrbild.BESTAETIGT and z["gewinde"] == "M10", neu
assert next(x for x in neu if abs(x["d"] - 6.8) < 0.01)["status"] == "offen"
assert not ass.uebernehmen_knopf.isEnabled()
e = ass.fragen("Alle Bohrungen Ø 3,3 als M4", mit_modell=False)
assert not e.get("aktion") and "Keine passende Bohrung" in e["text"]
ok("Befehl im Assistenten: Vorschlag mit Vorher/Nachher, Übernehmen speichert nur die betroffenen Bohrungen")

for frage, absicht in (("Wie hoch ist das Preisrisiko dieses Angebots?", "risiko"),
                       ("Schreib die Rückfrage auf Englisch.", "englisch"),
                       ("Wann können wir liefern, wo sind Engpässe?", "liefertermin"),
                       ("Was bedeuten die Fehlermeldungen der letzten Tage?", "fehlerlog"),
                       ("Wie lege ich einen Rahmenauftrag an?", "hilfe")):
    a = ki_orchestrator.fragen(db, frage, seite=seite, mit_modell=False)
    assert a["absicht"] == absicht and a["text"], (frage, a["absicht"], a["text"])
a = ki_orchestrator.fragen(db, "Schreib die Rückfrage auf Englisch.", seite=seite, mit_modell=False)
assert "Sprachmodell" in a["text"] or "Kein Text" in a["text"], a["text"]
ass.close()
ok("Orchestrator: Preisrisiko, Englisch, Liefertermin, Fehler, Hilfe")

print("ALLE TESTS OK")
