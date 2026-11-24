"""Abgleich zwischen PCs feldweise (Plan Datenbank-Modernisierung, Phase 6).

Prüft: ändern zwei Mitarbeiter verschiedene Felder derselben Stammdatenzeile, bleiben beide Änderungen bei allen
(kein Konflikt); dasselbe Feld verschieden geändert: die jüngere Änderung gilt, der Konflikt nennt das Feld und lässt
sich wiederherstellen, ohne die andere Änderung zu verlieren; Löschen kommt weiter an; ein Kollege mit älterem
Programm (Datei ohne Feldzeiten) wird zeilenweise wie bisher abgeglichen; Nummernvorrat je PC: ohne gemeinsamen
Ordner endgültige Nummer aus dem Vorrat, ist er leer, vorläufige Nummer wie bisher.

Aufruf: python tests/test_abgleich_feldweise.py
"""
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import nummern, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def arbeitsplatz(name, k):
    db = Datenbank(tmp / name / "rohrlaser.db")
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("teilen_ordner", str(gemeinsam))
    return db


def zeile(db, tabelle, uid):
    return next(z for z in db.zeilen(tabelle, True) if z["uid"] == uid)


def warte():
    time.sleep(0.02)


pb = arbeitsplatz("Patrick", "PB")
teilen.abgleichen(pb)
mk = arbeitsplatz("Martin", "MK")
teilen.abgleichen(mk, teilen.UEBERNEHMEN)
teilen.abgleichen(pb)
k = pb.neu("kunden", dict(kundennr="K-100", name="Muster GmbH", plz_ort="Alt", bemerkung="leer"))
u = pb.zeilen("kunden", True)[[z["id"] for z in pb.zeilen("kunden", True)].index(k)]["uid"]
teilen.abgleichen(pb)
teilen.abgleichen(mk)
assert zeile(mk, "kunden", u)["plz_ort"] == "Alt"
assert teilen.felder(pb.con).get(("kunden", u)), "Feldzeiten gemerkt"

# ---------------------------------------------------------------- verschiedene Felder: beide Änderungen bleiben
warte()
pb.aendern("kunden", zeile(pb, "kunden", u)["id"], "plz_ort", "Bocholt")
teilen.abgleichen(pb)
warte()
mk.aendern("kunden", zeile(mk, "kunden", u)["id"], "bemerkung", "Rahmenvertrag")     # MK hat PB noch nicht gelesen
b_mk = teilen.lesen(mk)
teilen.schreiben(mk)
b_pb = teilen.abgleichen(pb)
teilen.abgleichen(mk)
for db in (pb, mk):
    z = zeile(db, "kunden", u)
    assert (z["plz_ort"], z["bemerkung"]) == ("Bocholt", "Rahmenvertrag"), (db.einstellung("benutzer_kuerzel"), z)
assert not b_mk["konflikte"] and not b_pb["konflikte"], (b_mk["konflikte"], b_pb["konflikte"])
ok("Verschiedene Felder derselben Zeile geändert: beide Änderungen bei beiden, kein Konflikt")

# ---------------------------------------------------------------- gleiches Feld: jüngere gilt, Konflikt nennt das Feld
warte()
pb.aendern("kunden", zeile(pb, "kunden", u)["id"], "plz_ort", "Rhede")
pb.aendern("kunden", zeile(pb, "kunden", u)["id"], "name", "Muster GmbH & Co. KG")
teilen.schreiben(pb)
warte()
mk.aendern("kunden", zeile(mk, "kunden", u)["id"], "plz_ort", "Borken")
b = teilen.abgleichen(mk)
teilen.abgleichen(pb)
for db in (pb, mk):
    z = zeile(db, "kunden", u)
    assert (z["plz_ort"], z["name"], z["bemerkung"]) == ("Borken", "Muster GmbH & Co. KG", "Rahmenvertrag"), z
assert len(b["konflikte"]) == 1 and b["konflikte"][0]["felder"] == ["plz_ort"], b["konflikte"]
kf = teilen.konflikte(mk, offen_nur=True)[0]
assert kf["gewinner"] == "MK" and kf["verloren"]["plz_ort"] == "Rhede" and kf["verloren"]["name"] == "Muster GmbH & Co. KG"
from rohrlaser.teilen_fenster import konflikt_text  # noqa: E402
assert "PLZ Ort" in konflikt_text(kf), konflikt_text(kf)
assert teilen.konflikt_erledigt(mk, kf["id"], wiederherstellen=True)
warte()
teilen.abgleichen(mk)
teilen.abgleichen(pb)
for db in (pb, mk):
    z = zeile(db, "kunden", u)
    assert (z["plz_ort"], z["name"]) == ("Rhede", "Muster GmbH & Co. KG"), z
ok("Gleiches Feld verschieden geändert: jüngere Änderung gilt, Konflikt nennt nur dieses Feld, "
   "Wiederherstellen ändert nur dieses Feld")

# ---------------------------------------------------------------- Löschen kommt weiter an
warte()
mk.loeschen("kunden", [zeile(mk, "kunden", u)["id"]])
teilen.abgleichen(mk)
teilen.abgleichen(pb)
assert u not in {z["uid"] for z in pb.zeilen("kunden", True)}
ok("Gelöschte Zeile kommt beim Kollegen an")

# ---------------------------------------------------------------- Kollege mit älterem Programm: zeilenweise
k2 = pb.neu("kunden", dict(kundennr="K-200", name="Alt AG", plz_ort="A", bemerkung="B"))
u2 = next(z["uid"] for z in pb.zeilen("kunden", True) if z["id"] == k2)
teilen.abgleichen(pb)
teilen.abgleichen(mk)
warte()
mk.aendern("kunden", zeile(mk, "kunden", u2)["id"], "plz_ort", "von MK")
teilen.abgleichen(mk)
haupt = gemeinsam / "Rohrlaser_MK" / "haupt.sqlite"
c = sqlite3.connect(haupt)
c.execute("UPDATE stammdaten SET felder=NULL")          # wie eine Datei ohne Feldzeiten (Programm vor Phase 6)
c.commit()
c.close()
assert teilen.abgleichen(pb)["stammdaten"] >= 1
assert zeile(pb, "kunden", u2)["plz_ort"] == "von MK"
ok("Datei ohne Feldzeiten (älteres Programm): zeilenweise wie bisher")

# ---------------------------------------------------------------- Nummernvorrat je PC
pb.einstellung_setzen("nummern_vorrat", 2)
a = pb.angebot_neu(dict(kunde="Online", datum="2026-11-14"))
nr_online = pb.angebot(a)["nummer"]
vorrat = nummern.vorrat(pb)
assert len(vorrat) == 2 and all(n > nummern.zaehler(nr_online) for n in vorrat), (nr_online, vorrat)
belegt = {p.stem for p in (gemeinsam / nummern.ORDNER).iterdir()}
assert all(f"{n:05d}" in belegt for n in vorrat), "Vorrat im gemeinsamen Ordner reserviert"
a2 = mk.angebot_neu(dict(kunde="Kollege", datum="2026-11-14"))
assert nummern.zaehler(mk.angebot(a2)["nummer"]) > max(vorrat), "Kollege bekommt keine Vorratsnummer"
shutil.move(str(gemeinsam), str(tmp / "weg"))           # Netz weg
n1 = pb.angebot(pb.angebot_neu(dict(kunde="Ohne Netz 1", datum="2026-11-14")))["nummer"]
n2 = pb.angebot(pb.angebot_neu(dict(kunde="Ohne Netz 2", datum="2026-11-14")))["nummer"]
n3 = pb.angebot(pb.angebot_neu(dict(kunde="Ohne Netz 3", datum="2026-11-14")))["nummer"]
assert [nummern.zaehler(n1), nummern.zaehler(n2)] == vorrat and not nummern.vorlaeufig(n1), (n1, n2, vorrat)
assert nummern.vorlaeufig(n3), n3
assert nummern.vorrat(pb) == []
shutil.move(str(tmp / "weg"), str(gemeinsam))
pb.angebot_neu(dict(kunde="Wieder online", datum="2026-11-14"))
assert len(nummern.vorrat(pb)) == 2, "Vorrat wieder aufgefüllt"
mk.einstellung_setzen("nummern_vorrat", 0)
ok(f"Nummernvorrat: ohne Netz endgültige Nummern {n1}, {n2} aus dem Vorrat, danach vorläufig {n3}; "
   "wieder online aufgefüllt")
pb.schliessen()
mk.schliessen()
print("OK: feldweiser Abgleich und Nummernvorrat")
