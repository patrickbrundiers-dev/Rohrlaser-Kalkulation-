"""Prüft „Das Programm lernt“ (Plan Patrick 08.11.2026, Freigabe „Alle Empfehlungen“ = F1a F2a F3a F4a):
L1 Lernzentrale (Übersicht, Vergessen, Kennwerte auf der Startseite), L2 aus ✓/✗ der Zusatzarbeit-Vorschläge lernen
(je Angebot einmal gezählt, nach 3 gleichen Entscheidungen gelernt, beim Import angewendet mit Rückgängig), L3 Werte
von Hand der Wiederholteile übernehmen, L4 Trefferquote als Hinweis, Teilen (Tabelle gelernt und gelernte
Einstellungen über den gemeinsamen Ordner, je Eintrag gemischt).

Aufruf: python tests/test_lernen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

import beispiel_angebot  # noqa: E402
from rohrlaser import angebot_automatik as aa, automatik, lernen, nacharbeit, teilen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


assert SCHEMA_VERSION >= 78
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert "uid" in {r[1] for r in db.con.execute("PRAGMA table_info(gelernt)")}, "gelernt wird geteilt (uid)"
assert lernen.GELERNT in teilen.GETEILT and set(lernen.EINSTELLUNGEN_GETEILT) <= set(teilen.EINSTELLUNGEN_GETEILT)
ok("Schema 78: Tabelle gelernt mit Kennung, geteilt wie Stammdaten; gelernte Einstellungen gemeinsam")

# ------------------------------------------------------------------ L2 Zählen ohne Oberfläche
K = "K-1001"
assert lernen.entscheiden(db, lernen.ZUSATZ, K, "Entgraten", False, 1) is None
assert lernen.entscheiden(db, lernen.ZUSATZ, K, "Entgraten", False, 1) is None          # gleiches Angebot zählt nicht
assert lernen.wirksam(db, lernen.ZUSATZ, K) == {}
assert lernen.entscheiden(db, lernen.ZUSATZ, K, "Entgraten", False, 2) is None
assert lernen.entscheiden(db, lernen.ZUSATZ, K, "Entgraten", False, 3) == lernen.NEIN     # drittes Angebot: gelernt
assert lernen.entscheiden(db, lernen.ZUSATZ, K, "Entgraten", False, 4) is None          # bleibt gelernt, keine Meldung
assert lernen.wirksam(db, lernen.ZUSATZ, K) == {"Entgraten": lernen.NEIN}
assert lernen.wirksam(db, lernen.ZUSATZ, "K-2") == {}                                  # nur dieser Kunde
assert lernen.entscheiden(db, lernen.ZUSATZ, K, "Entgraten", True, 5) is None           # anders: fängt neu an
assert lernen.wirksam(db, lernen.ZUSATZ, K) == {}
assert lernen.entscheiden(db, lernen.ZUSATZ, "", "Entgraten", False, 6) is None         # ohne Kunde nichts
z = db.zeilen("gelernt")[0]
assert (z["ja"], z["nein"], len(json.loads(z["angebote"]))) == (1, 4, 1), z
ok("L2: je Angebot einmal gezählt, nach 3 gleichen Entscheidungen gelernt, andere Entscheidung fängt neu an")

# ------------------------------------------------------------------ L1 Übersicht, Vergessen, Sperren
for a in (11, 12, 13):
    lernen.entscheiden(db, lernen.ZUSATZ, K, "Pulverbeschichten", True, a)
nacharbeit.merken(db, K, 21, "stange", 6500)
db.einstellung_setzen(lernen.STEP_ART, {"10|20|30|4|6|12": "Blech", "11|20|30|4|6|12": "Blech"})
db.einstellung_setzen(lernen.STEP_PROFIL, {K: {"QR 40x40x3": "QR 40x40x2,5"}})
u = lernen.uebersicht(db)
bereiche = [e["bereich"] for e in u]
assert "STEP: Teileart" in bereiche and "STEP: Profil" in bereiche and "Nacharbeit nach dem Import" in bereiche, u
pulver = next(e for e in u if "Pulverbeschichten" in e["was"])
assert pulver["gelernt"] and pulver["stand"] == "gelernt"
beob = next(e for e in u if e["quelle"] == lernen.NACHARBEIT)
assert not beob["gelernt"] and "1 von 3" in beob["stand"], beob
assert u.index(pulver) < u.index(beob), "Gelerntes zuerst"
art = next(e for e in u if e["quelle"] == lernen.STEP_ART)
assert "2 Teile" in art["was"]
lernen.vergessen(db, art)
assert all(v is None for v in db.einstellung(lernen.STEP_ART).values()), "Grabstein für die Kollegen"
lernen.vergessen(db, next(e for e in lernen.uebersicht(db) if e["quelle"] == lernen.STEP_PROFIL))
assert db.einstellung(lernen.STEP_PROFIL)[K]["QR 40x40x3"] is None
lernen.vergessen(db, next(e for e in lernen.uebersicht(db) if e["quelle"] == lernen.NACHARBEIT))
assert nacharbeit.merken(db, K, 22, "stange", 6500) is None
assert len(db.einstellung(lernen.NACHARBEIT)[f"{K}|stange|6500"]["angebote"]) == 1, "fängt nach Vergessen neu an"
lernen.sperren(db, pulver)
assert lernen.wirksam(db, lernen.ZUSATZ, K) == {}
assert lernen.entscheiden(db, lernen.ZUSATZ, K, "Pulverbeschichten", True, 14) is None
lernen.vergessen(db, next(e for e in lernen.uebersicht(db) if "Pulverbeschichten" in e["was"]))
assert not any("Pulverbeschichten" in e["was"] for e in lernen.uebersicht(db))
ok("L1: Lernzentrale zeigt Zusatzarbeiten, Nacharbeit, Teileart, Profil; Vergessen und Sperren wirken")

# ------------------------------------------------------------------ Teilen: gelernte Einstellungen mischen
hier = json.dumps({"a": "Blech", "b": "Profil"})
dort = json.dumps({"b": None, "c": "Rohr"})
assert json.loads(lernen.mischen(lernen.STEP_ART, hier, dort)) == {"a": "Blech", "b": None, "c": "Rohr"}
hier = json.dumps({K: {"x": "y"}, "K-2": {"p": "q"}})
dort = json.dumps({K: {"z": "w"}})
assert json.loads(lernen.mischen(lernen.STEP_PROFIL, hier, dort)) == {K: {"x": "y", "z": "w"}, "K-2": {"p": "q"}}
assert lernen.mischen(lernen.NACHARBEIT, "kaputt", dort) == dort
ok("Teilen: Gelerntes der Kollegen kommt dazu, eigenes bleibt, Vergessenes (leer) kommt bei allen an")

# echter Abgleich über den gemeinsamen Ordner: Zusatzarbeit gelernt bei PB kommt bei MK an, Teileart gemischt
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def platz(name, k):
    d = Datenbank(tmp / name / "rohrlaser.db")
    for feld, wert in (("benutzer_name", name), ("benutzer_kuerzel", k), ("teilen_ordner", str(gemeinsam))):
        d.einstellung_setzen(feld, wert)
    return d


pb, mk = platz("Patrick", "PB"), platz("Martin", "MK")
for a in (1, 2, 3):
    lernen.entscheiden(pb, lernen.ZUSATZ, K, "Entgraten", False, a)
pb.einstellung_setzen(lernen.STEP_ART, {"g1": "Blech"})
teilen.abgleichen(pb)
mk.einstellung_setzen(lernen.STEP_ART, {"g2": "Profil"})
teilen.abgleichen(mk, teilen.UEBERNEHMEN)
assert lernen.wirksam(mk, lernen.ZUSATZ, K) == {"Entgraten": lernen.NEIN}, mk.zeilen("gelernt")
assert mk.einstellung(lernen.STEP_ART) == {"g2": "Profil", "g1": "Blech"}, mk.einstellung(lernen.STEP_ART)
teilen.abgleichen(mk)
teilen.abgleichen(pb)
assert pb.einstellung(lernen.STEP_ART) == {"g1": "Blech", "g2": "Profil"}, pb.einstellung(lernen.STEP_ART)
lernen.vergessen(mk, next(e for e in lernen.uebersicht(mk) if e["quelle"] == lernen.TABELLE))
teilen.abgleichen(mk)
teilen.abgleichen(pb)
assert lernen.wirksam(pb, lernen.ZUSATZ, K) == {}, "Vergessen kommt beim Kollegen an"
ok("Teilen: gelernte Zusatzarbeit und Teileart kommen beim Kollegen an, beide behalten ihr Gelerntes, Vergessen auch")

# ------------------------------------------------------------------ Oberfläche: ✓/✗ lernen, beim Import anwenden
fenster = Hauptfenster(db, tmp, stumm=True)
name = next(z["name"] for z in db.zeilen("zusatzarbeiten") if z.get("erkennung") and z.get("aktiv") != "nein")
wort = [w.strip() for w in db.zeilen("zusatzarbeiten")[[z["name"] for z in db.zeilen("zusatzarbeiten")].index(name)]
        ["erkennung"].split(";") if w.strip()][0]
K2 = "K-2002"


def angebot_mit_vorschlag():
    aid = beispiel_angebot.anlegen(db, dict(kundennr=K2, kunde="Lern GmbH"))
    p = next(p for p in db.positionen(aid) if p.get("profil_id"))
    db.position_aendern(p["id"], "bezeichnung", f"Rohr {wort}")
    s = fenster.angebot_oeffnen(aid)
    r = next(i for i, x in enumerate(s.positionen) if x["id"] == p["id"])
    assert any(v["name"] == name for v in s.pos_modell.vorschlaege[r]), (name, s.pos_modell.vorschlaege[r])
    return aid, s, p["id"], r


meldungen = []
for i in range(3):
    aid, s, pid, r = angebot_mit_vorschlag()
    alt = s.f.meldung
    s.f.meldung = lambda t, *a, **k: meldungen.append(t)
    s.vorschlaege_ablehnen([r])
    s.f.meldung = alt
assert any("Gelernt" in t and name in t for t in meldungen[-1:]), meldungen
assert lernen.wirksam(db, lernen.ZUSATZ, K2) == {name: lernen.NEIN}
aid, s, pid, r = angebot_mit_vorschlag()
out = dict(texte=[], aktion=None, bericht=[])
aa.gelernte_zusatzarbeiten(s, out)
assert any("abgelehnt" in t for t in out["texte"]), out
assert not any(v["name"] == name for v in s.pos_modell.vorschlaege[r]), "gleich abgelehnt"
e = next(x for x in automatik.liste(db) if x["art"] == "gelernt")
automatik.rueckgaengig(db, e["id"])
s.neu_laden()
assert any(v["name"] == name for v in s.pos_modell.vorschlaege[r]), "Rückgängig: wieder Vorschlag"
# andersherum: dreimal übernommen -> beim Import gleich übernommen (gerechnet)
for i in range(3):
    aid, s, pid, r = angebot_mit_vorschlag()
    s.arbeitsgang_annehmen(pid, name)
assert lernen.wirksam(db, lernen.ZUSATZ, K2) == {name: lernen.JA}
aid, s, pid, r = angebot_mit_vorschlag()
out = dict(texte=[], aktion=None, bericht=[])
aa.gelernte_zusatzarbeiten(s, out)
p = next(x for x in db.positionen(aid) if x["id"] == pid)
assert name in {x["name"] for x in json.loads(p["zusatz"])}, p["zusatz"]
assert "gelernt" in json.dumps(json.loads(p["zusatz"]), ensure_ascii=False) or out["texte"], out
ok(f"L2 Oberfläche: ✗/✓ bei „{name}“ dreimal -> beim Import gleich abgelehnt bzw. übernommen, mit Rückgängig")

# ------------------------------------------------------------------ L3 Werte von Hand der Wiederholteile
a1 = beispiel_angebot.anlegen(db, dict(kundennr="K-3003", kunde="Wiederhol AG"))
p1 = next(p for p in db.positionen(a1) if p.get("profil_id"))
db.position_aendern(p1["id"], "artikel", "WT-4711")
db.position_aendern(p1["id"], "prog_zeit", 12.5)
db.position_aendern(p1["id"], "einstiche", 7)
a2 = beispiel_angebot.anlegen(db, dict(kundennr="K-3003", kunde="Wiederhol AG"))
p2 = next(p for p in db.positionen(a2) if p.get("profil_id") and p["pos"] == p1["pos"])
db.position_aendern(p2["id"], "artikel", "WT-4711")
db.position_aendern(p2["id"], "einstiche", 3)            # schon gesetzt: bleibt
s2 = fenster.angebot_oeffnen(a2)
out = dict(texte=[], aktion=None, bericht=[])
aa.wiederholwerte(s2, out)
neu = next(x for x in db.positionen(a2) if x["id"] == p2["id"])
assert neu["prog_zeit"] == 12.5 and neu["einstiche"] == 3, neu
assert any("Wiederholteil" in t for t in out["texte"]), out
e = next(x for x in automatik.liste(db) if x["art"] == "gelernt" and "Wiederholteil" in x["text"])
automatik.rueckgaengig(db, e["id"])
assert next(x for x in db.positionen(a2) if x["id"] == p2["id"])["prog_zeit"] in (None, "")
ok("L3: Programmierzeit von Hand aus dem früheren Angebot übernommen, eigene Werte bleiben, Rückgängig")

# ------------------------------------------------------------------ L4 Trefferquote
for i, (vorgang, gewinn) in enumerate([("Beauftragt", 12), ("Beauftragt", 14), ("Abgelehnt", 20), ("Entwurf", 10)]):
    x = beispiel_angebot.anlegen(db, dict(kundennr="K-4004", kunde="Treffer KG"))
    db.angebot_aendern(x, "gewinn", gewinn)
    db.vorgang_setzen(x, vorgang)
t = lernen.trefferquote(db, "K-4004")
assert (t["beauftragt"], t["abgelehnt"]) == (2, 1) and abs(t["gewinn_ja"] - 13) < 1e-9, t
text = lernen.treffer_text(t)
assert "2 von 3" in text and "67 %" in text, text
assert lernen.trefferquote(db, "K-unbekannt") is None
s4 = fenster.angebot_oeffnen(x)
s4._ergebnisse_anzeigen()
assert "2 von 3" in s4.uebersicht_bereich.treffer.text()
ok(f"L4: Trefferquote als Hinweis: {text}")

# ------------------------------------------------------------------ Lernzentrale-Fenster und Startseite
d = fenster.lernzentrale(dialog=lambda d: None)
assert d.tabelle.rowCount() == len(lernen.uebersicht(db)) and "Vergessen" in d.knoepfe
assert isinstance(automatik.aufgaben(db), list)
ok("Lernzentrale: Fenster mit Vergessen, Nicht mehr lernen, Kennwerte prüfen; Startseite ohne Fehler")
print("Alle Lern-Tests bestanden.")
