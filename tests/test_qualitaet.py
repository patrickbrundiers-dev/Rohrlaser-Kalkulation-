"""Qualitätskosten aus dem Prüfplan (Plan X4, Patrick 12.11.2026 „Alle Empfehlungen (X1–X8)“).

- Tabelle Qualitätsstufen leer ausgeliefert; Position ohne Stufe rechnet wie bisher
- Q = (Merkmale × Messzeit × geprüfte Teile + 60 × (Erstmuster + Protokoll)) / 3600 × Stundensatz QS, je Los
- Prüfanteil alle / jedes n-te / erste n; Staffel = eigenes Los (Erstmuster und Protokoll wieder einmal)
- eigene Kostenart „Qualität (Prüfplan)“ mit Zuschlag Fertigung, kein Prozentaufschlag
- Zusatzarbeit Erstmusterprüfung an der Position: Erstmusterzeit der Stufe zählt nicht (keine Doppelzählung)
- ohne Stundensatz: 0 € mit Hinweis, nichts erfunden; festgeschriebene Angebote behalten ihre Stufen

Aufruf: python tests/test_qualitaet.py
"""
import json
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import pruefplan, qualitaet, rechnen, schneidweg, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def nahe(a, b, text):
    assert abs(a - b) < 1e-6, f"{text}: {a} statt {b}"


db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
assert db.zeilen("qualitaetsstufen") == [], "Qualitätsstufen leer ausgeliefert"
tab = db.tabellen()
sid, satz = next((s, w) for s, w in rechnen.stundensaetze(tab).items() if w)
stufe = dict(name="Messbericht", aktiv="ja", zeit_merkmal=20.0, pruefanteil="jedes n-te Teil", pruef_n=10,
             erstmuster=30.0, protokoll=15.0, satz_id=sid)
db.neu("qualitaetsstufen", stufe)
tab = db.tabellen()
assert [z["name"] for z in tab["qualitaetsstufen"]] == ["Messbericht"]
k = db.kontext()
assert k.auswahl("qualitaetsstufe") == ["Messbericht"]
ok("Tabelle leer ausgeliefert, angelegte Stufe in der Auswahl der Position")

m = next(iter(k.maschinen))
pid = next(p for p, w in k.profile.items() if w.get("form") == "Quadratrohr")
pr = dict(k.profile[pid], profil_id=pid)
wst = next(iter(k.werkstoffe))
e = dict(seite_a=dict(art="gerade"), seite_b=dict(art="gerade"),
         konturen=[dict(art=schneidweg.BOHRUNG, anzahl=1, d=8, x=200, seite=0),
                   dict(art=schneidweg.LANGLOCH, anzahl=1, l=40, b=12, x=600, seite=0)])
try:
    r = schneidweg.rechnen(e, pr, rechnen.kontur_regel(k.maschinen[m], pr["wand"]))
    felder, technik = r["felder"], json.dumps(dict(e, quelle=schneidweg.QUELLE))
except Exception:
    felder, technik = {}, None
a = db.angebot_neu(dict(kunde="Test", maschine=m))
db.angebot_aendern(a, "skonto", 0)
db.angebot_aendern(a, "fracht_modus", "keine Fracht")


def position(stueck=40, qual="Messbericht", zusatz=None):
    return dict(id=1, pos=10, artikel="Q1", profil_id=pid, werkstoff_id=wst, laenge=1000, stueck=stueck,
                technik=technik, qualitaet=qual, zusatz=zusatz, **felder)


p = position()
mm = len(pruefplan.merkmale(p))
assert mm >= 1
q = qualitaet.kosten(p, 40, tab)
n = math.ceil(40 / 10)
sek = mm * 20 * n + 60 * (30 + 15)
nahe(q["eur"], sek / 3600 * satz, "Formel Q")
assert q["merkmale"] == mm and q["gepruefte"] == n and not q["hinweis"]
ok(f"Q = ({mm} Merkmale × 20 s × {n} Teile + 60 × (30 + 15)) / 3600 × {rechnen.zahl(satz)} €/h "
   f"= {rechnen.zahl(q['eur'])} €")
assert qualitaet.gepruefte_teile(dict(pruefanteil="erste n Teile", pruef_n=5), 40) == 5
assert qualitaet.gepruefte_teile(dict(pruefanteil="erste n Teile", pruef_n=5), 3) == 3
assert qualitaet.gepruefte_teile(dict(pruefanteil="alle Teile"), 40) == 40
ok("Prüfanteil alle / jedes n-te / erste n")

ohne_satz = dict(tab, qualitaetsstufen=[dict(stufe, satz_id=None, satz=None)])
q0 = qualitaet.kosten(p, 40, ohne_satz)
assert q0["eur"] == 0 and "Stundensatz QS fehlt" in q0["hinweis"]
assert qualitaet.pruefung(dict(stufe, satz_id=None)).startswith("WARNUNG")
assert qualitaet.pruefung(dict(stufe, pruef_n=None)).startswith("FEHLER")
assert qualitaet.kosten(dict(p, qualitaet="gibt es nicht"), 40, tab)["hinweis"].endswith("unbekannt oder aus")
ok("ohne Stundensatz 0 € mit Hinweis, unbekannte Stufe gemeldet, Prüfspalte")

zus = json.dumps([dict(name=pruefplan.ZUSATZ, menge=None, preis=None, text=None)])
q2 = qualitaet.kosten(position(zusatz=zus), 40, tab)
nahe(q2["eur"], (mm * 20 * n + 60 * 15) / 3600 * satz, "Erstmuster über Zusatzarbeit")
assert q2["erstmuster_zusatz"]
ok("Zusatzarbeit Erstmusterprüfung: Erstmusterzeit der Stufe zählt nicht")


def kalk(pos):
    kopf = db.angebot(a)
    erg = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    return rechnen.kalkulation(kopf, pos, erg, k, tab, einst), einst


(z0, s0), einst = kalk([position(qual=None)])
(z1, s1), _ = kalk([position()])
nahe(s1["qualitaet"], q["eur"], "Kostenart Qualität")
zf = rechnen._n(einst.get("zuschlag_fertigung"))
nahe(s1["herstell"] - s0["herstell"], q["eur"] * (1 + zf), "Herstellkosten + Q × (1 + Zuschlag Fertigung)")
assert s0["qualitaet"] == 0
arten = {t.split(" (")[0]: (t, w) for t, w, _ in rechnen.kostenarten(s1, einst)}
nahe(arten["Qualität"][1], q["eur"], "Preisaufbau")
ok(f"eigene Kostenart, Herstellkosten + Q × (1 + {rechnen.zahl(100 * zf)} %), ohne Stufe wie bisher")

# Staffel 400 Stück: eigenes Los, Erstmuster/Protokoll wieder einmal, geprüfte Teile 40
x = staffeln.stufe_rechnen(db.angebot(a), [position()], "10", 400, k, tab, einst)
(z4, s4), _ = kalk([position(stueck=400)])
assert abs(x["preis_einheit"] - s4["verkauf"] / 400) < 0.006, (x["preis_einheit"], s4["verkauf"] / 400)   # gerundet
assert any(n.startswith("Qualität") for n, _, _ in x["bausteine"]["fertigung"]), x["bausteine"]["fertigung"]
nahe(s4["qualitaet"], (mm * 20 * 40 + 60 * 45) / 3600 * satz, "Staffel 400: Q")
nahe(z4[0]["qualitaet_teil"] * 400, s4["qualitaet"], "Staffel: Q je Teil × Menge")
ok("Staffel 400 Stück: 40 geprüfte Teile, Erstmuster und Protokoll einmal, Staffelpreis = Kalkulation")

# festgeschriebenes Angebot: Stufen aus dem Snapshot
kopf = db.angebot(a)
pb = rechnen.preisbasis_aus(kopf, [position()], k, tab)
assert [z["name"] for z in pb["qualitaetsstufen"]] == ["Messbericht"]
_, t2 = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=pb), k, dict(tab, qualitaetsstufen=[]))
assert [z["name"] for z in t2["qualitaetsstufen"]] == ["Messbericht"]
_, t3 = rechnen.preisbasis_anwenden(dict(kopf, preisbasis={k_: v for k_, v in pb.items() if k_ != "qualitaetsstufen"}),
                                    k, tab)
assert t3["qualitaetsstufen"] == []
ok("festgeschrieben: Stufen wie im Snapshot; ältere Snapshots ohne Qualitätskosten")
print("Qualitätskosten stimmen.")
