"""KI 2 (Patrick 20.11.2026 „Alles einbauen nach Empfehlungen“): Anfrage auslesen und Angebotsentwurf, Kundenvorgaben,
Freitext → Zusatzarbeiten mit Sprachmodell (nur wörtlich belegte Werte, nur Katalog-Namen), Widersprüche Zeichnung ↔
Position, Preis erklären (intern/Kunde), vergessene Positionen, Muster aus der Nachkalkulation, Rückfrage-Entwurf,
Suche in normaler Sprache, Orchestrator-Absichten und der Ablauf im KI-Assistenten. Alles lokal, nichts ändert Preise.

Aufruf: python tests/test_ki_auslesen.py
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
TMP = Path(tempfile.mkdtemp())
os.environ["LOCALAPPDATA"] = str(TMP / "appdata")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import ki_agenten, ki_assistent, ki_auslesen, ki_kalkulation, ki_modelle, ki_orchestrator, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
db = Datenbank(TMP / "rohrlaser.db")
f = Hauptfenster(db, TMP, stumm=True)
db.einstellung_setzen(ki_modelle.AKTIV, "nein")

ANFRAGE = """Sehr geehrte Damen und Herren,
bitte um Angebot für folgende Teile, Anfrage-Nr. AN-55821, Projekt Hallenbau Nord:
Pos 1  4711-001  Holm links  Rundrohr 42,4x2,0  Länge 1250 mm  S235  24 Stück
Pos 2  4711-002  Querstrebe  Rundrohr 42,4x2,0  L=860 mm  S235  40 Stk.
Alle Teile entgraten und verzinken.
Werkszeugnis 3.1 erforderlich. Lieferung frei Haus, Liefertermin KW 50.
Mit freundlichen Grüßen
"""

# ------------------------------------------------------------------ Punkt 1+3: Anfrage auslesen (ohne Modell)
e = ki_auslesen.anfrage(db, ANFRAGE, mit_modell=False)
assert len(e["positionen"]) == 2, e["positionen"]
p1, p2 = e["positionen"]
assert p1["profil_id"] == "RR 42,4x2,0" and p1["laenge"] == 1250 and p1["menge"] == 24, p1
assert p2["laenge"] == 860 and p2["menge"] == 40 and p1["werkstoff_id"], p2
arten = {v["art"] for v in e["vorgaben"]}
assert any("3.1" in a or "Zeugnis" in a for a in arten), arten
assert any("Liefer" in a for a in arten), arten
assert e["kopf"].get("kundenreferenz") == "AN-55821" and "Hallenbau" in (e["kopf"].get("projekt") or ""), e["kopf"]
assert not e["modell"]
ok("Anfrage auslesen: Positionen, Profil, Länge, Menge, Werkstoff, Anfrage-Nr., Projekt, Kundenvorgaben")

txt = ki_orchestrator.anfrage_text(e)
assert "2 Positionen" in txt and "Kundenvorgaben" in txt, txt
vorher = len(db.angebote())
aid = ki_auslesen.entwurf_anlegen(db, e, dict(kunde="Neukunde GmbH"))
assert len(db.angebote()) == vorher + 1
kopf = db.angebot(aid)
assert kopf["kundenreferenz"] == "AN-55821" and str(kopf.get("zeugnis_31")).lower() in ("ja", "1", "true"), kopf
assert "KI-Auslesen" in kopf["bemerkung"] and "frei Haus" in kopf["bemerkung"], kopf["bemerkung"]
pos = db.positionen(aid)
assert [(p["profil_id"], p["laenge"], p["stueck"]) for p in pos] == [("RR 42,4x2,0", 1250, 24),
                                                                       ("RR 42,4x2,0", 860, 40)], pos
erkannt = json.loads(pos[0].get("arbeitsgaenge") or "{}").get("erkannt") or []
assert erkannt, pos[0].get("arbeitsgaenge")          # entgraten/verzinken als gelbe Vorschläge
ok("Angebotsentwurf: Kopf, Zeugnis 3.1, Bemerkung mit Vorgaben, Positionen, Zusatzarbeiten als Vorschläge")

# ------------------------------------------------------------------ Punkt 2: Freitext → Zusatzarbeiten mit Modell
katalog = db.zeilen("zusatzarbeiten")
namen = [z["name"] for z in katalog]
assert namen
ANTWORT = {}


def modell(url, pfad, daten=None):
    if pfad == "/api/tags":
        return {"models": [{"name": "qwen3:8b", "size": 5_200_000_000, "details": {"parameter_size": "8.2B"}}]}
    if pfad == "/api/ps":
        return {"models": []}
    if pfad == "/api/version":
        return {"version": "0.12.0"}
    if pfad == "/api/generate":
        return {"response": json.dumps(ANTWORT["d"]), "eval_count": 10, "eval_duration": 100_000_000}
    raise OSError(pfad)


db.einstellung_setzen(ki_modelle.AKTIV, "ja")
ki_modelle.modelle(db, senden=modell)
FREITEXT = "Die Enden bitte sauber entgraten, Bohrung mit Gewinde M8 an beiden Seiten."
ANTWORT["d"] = {"zusatz": [{"name": namen[0], "beleg": "entgraten"},
                           {"name": "Erfundene Arbeit", "beleg": "Gewinde M8"},
                           {"name": namen[0], "beleg": "nicht im Text"}]}
ki_auslesen._CACHE.clear()
funde = ki_auslesen.zusatz_ki(db, FREITEXT, katalog, senden=modell)
assert all(x["name"] in namen for x in funde), funde                   # nur Namen aus dem Katalog
assert all(ki_auslesen.fundstelle(FREITEXT, x.get("beleg") or x.get("wort") or "") for x in funde), funde
assert "Erfundene Arbeit" not in {x["name"] for x in funde}
ag = ki_auslesen.text_merken_ki(None, funde, "Mail")
if funde:
    assert all(str(x["quelle"]).startswith("KI") for x in json.loads(ag)["erkannt"]), ag
ok("Freitext → Zusatzarbeiten: nur Katalog-Namen mit wörtlichem Beleg, Quelle „KI: …“")

# erfundene Werte aus dem Modell werden verworfen (Zeichnung)
ZEICHNUNG = "Rundrohr 42,4 x 4,0\nWerkstoff 1.4301\nGesamtlänge 1250"
ANTWORT["d"] = {"aussen": 42.4, "wand": 4.0, "laenge": 1250, "werkstoff": "1.4301", "gewinde": "M12"}
ki_auslesen._CACHE.clear()
w = ki_auslesen.zeichnung_werte(ZEICHNUNG, db.zeilen("werkstoffe"), db, senden=modell)
assert "M12" not in json.dumps(w, ensure_ascii=False), w
ok("Zeichnung: Modellwerte nur mit Fundstelle im Dokument (erfundenes M12 verworfen)")

# ------------------------------------------------------------------ Punkt 5: Widersprüche Zeichnung ↔ Position
profile = db.zeilen("profile")
wid = ki_auslesen.abgleich(dict(profil_id="RR 42,4x2,0", laenge=1250, werkstoff_id="S235-10219"), w,
                           profile, "Zeichnung")
assert any("Wand" in x for x in wid), wid
ok("Widerspruch Zeichnung ↔ Position (Wandstärke) erkannt")
db.einstellung_setzen(ki_modelle.AKTIV, "nein")

# ------------------------------------------------------------------ Punkt 7, 6, 9, 10, 12 am Beispielangebot
bid = beispiel_angebot.anlegen(db)
kopf, pos = db.angebot(bid), db.positionen(bid)
erg = rechnen.optimieren(kopf, pos, db.kontext())
db.profile_anlegen(erg.get("neue_profile") or [])
db.ergebnis_speichern(bid, erg)
db.con.commit()
ctx = ki_agenten.Kontext(db, bid)
pe = ki_kalkulation.preis_erklaeren(ctx)
assert pe and "Material" in pe["text"], pe
pk = ki_kalkulation.preis_erklaeren(ctx, fuer_kunde=True)
assert pk and pk["text"] and pk["text"] != pe["text"], pk
ok("Preis erklären: intern nach Kostenblöcken und als Satz für den Kunden")

# vergessene Positionen: drei frühere Angebote desselben Kunden mit Zeugnis 3.1
for i in range(3):
    beispiel_angebot.anlegen(db, dict(zeugnis_31="ja", datum=f"2026-0{i + 1}-10"))
v = ki_kalkulation.vergessene_positionen(ki_agenten.Kontext(db, bid))
assert any(x["name"] == "Werkszeugnis 3.1" for x in v), v
ok("Vergessene Positionen: Zeugnis 3.1 hatten alle früheren Angebote des Kunden")

m = ki_kalkulation.nachkalk_muster(db)
assert isinstance(m, list)
r = ki_kalkulation.rueckfrage_entwurf(ctx)
assert r is None or (r["betreff"] and r["text"])
ok("Nachkalkulations-Muster und Rückfrage-Entwurf laufen (ohne Daten: leer)")

filt, liste = ki_kalkulation.suche(db, "Zeig alle Angebote mit Rundrohr über 1 m")
assert filt.get("form") and filt.get("laenge_min") == 1000, filt
assert any(x["angebot_id"] == bid for x in liste), liste
filt2, liste2 = ki_kalkulation.suche(db, "Angebote mit Rechteckrohr 60x40")
assert any(x["angebot_id"] == bid for x in liste2), (filt2, liste2)
assert ki_kalkulation.filter_text(filt)
ok("Suche in normaler Sprache: Form, Länge, Maß als Filter")

# ------------------------------------------------------------------ Orchestrator
for frage, absicht in (("Erkläre den Preis, auch mit einem Satz für den Kunden.", "erklaeren"),
                       ("Schreib eine Rückfrage an den Kunden.", "rueckfragemail"),
                       ("Wo kalkulieren wir laut Nachkalkulation systematisch zu knapp?", "muster")):
    a = ki_orchestrator.fragen(db, frage, angebot_id=bid, mit_modell=False)
    assert a["absicht"] == absicht and a["text"], (frage, a["absicht"], a["text"])
a = ki_orchestrator.fragen(db, "Erkläre den Preis", angebot_id=bid, mit_modell=False)
assert "Satz für den Kunden" in a["text"], a["text"]
a = ki_orchestrator.fragen(db, "Zeig alle Angebote mit Rundrohr über 1 m", mit_modell=False)
assert a["absicht"] == "suche" and a["treffer"] and a["treffer"][0]["ziel"].startswith("angebot:"), a
ass0 = ki_assistent.zeigen(f)
ass0.zeigen(a)
assert ass0.befunde.rowCount() == len(a["treffer"])
a = ki_orchestrator.fragen(db, ANFRAGE, mit_modell=False)
assert a["absicht"] == "auslesen" and "2 Positionen" in a["text"], a["text"]
a = ki_orchestrator.fragen(db, "Was fehlt noch?", angebot_id=bid, mit_modell=False)
assert "Werkszeugnis 3.1" in a["text"], a["text"]
ok("Orchestrator: erklären, Rückfrage, Muster, Suche, eingefügte Anfrage, vergessene Positionen")

# ------------------------------------------------------------------ KI-Assistent: Anfrage auslesen → Entwurf
ass = ki_assistent.zeigen(f)
anf = TMP / "anfrage.txt"
anf.write_text(ANFRAGE, encoding="utf-8")
e = ass.anfrage_auslesen(pfad=str(anf), mit_modell=False)
assert len(e["positionen"]) == 2 and ass.befunde.rowCount() >= 2 and ass.entwurf_knopf.isEnabled()
assert "anfrage.txt" in ass.antwort.toPlainText()
vorher = len(db.angebote())
neu = ass.entwurf_anlegen(oeffnen=False)
assert len(db.angebote()) == vorher + 1 and not ass.entwurf_knopf.isEnabled() and len(db.positionen(neu)) == 2
ass.frage.setPlainText(ANFRAGE)
e = ass.anfrage_auslesen(mit_modell=False)          # eingefügter Text statt Datei
assert e and e["quelle"] == "eingefügtem Text"
ass.kopieren()
assert QApplication.clipboard().text() == ass.antwort.toPlainText()
ass.close()
ok("KI-Assistent: Anfrage auslesen (Datei und eingefügt), Entwurf anlegen, Text kopieren")

print("ALLE TESTS OK")
