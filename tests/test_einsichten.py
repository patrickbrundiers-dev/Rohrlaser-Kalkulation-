"""Prüft „Mehr Intelligenz“ I7–I12 (Patrick 10.11.2026, Freigabe „Alle sechs“): I7 Kundenvorgabe vorschlagen, I8
Reklamations-Hinweis bei Wiederholteilen, I9 Hinweis aus der Nachkalkulation ähnlicher Aufträge, I10 Selbstkorrektur
(zweimal zurückgenommen = verlernt), I11 Programmierzeit-Vorschlag und Schneidzeit-Hinweis, I12 Verlustmuster.

Aufruf: python tests/test_einsichten.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import absage, automatik, einsichten, funktionen, kundenvorgabe, lernen, monatsbericht  # noqa: E402
from rohrlaser import reklamation, wiederholteile  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
KUNDE = "K-1001"

# ------------------------------------------------------------------ I7 Kundenvorgabe
ids = [beispiel_angebot.anlegen(db, dict(kundennr=KUNDE, kunde="Beispiel Metallbau GmbH", maschine="T11",
                                         lieferzeit_art="Arbeitstage", lieferzeit_wert="15")) for _ in range(3)]
v = einsichten.kundenvorschlaege(db)
m = next((x for x in v if x["feld"] == "maschine"), None)
lz = next((x for x in v if x["feld"] == "lieferzeit"), None)
assert m and m["wert"] == "T11" and m["angebote"] == 3 and lz and lz["wert"] == "Arbeitstage|15", v
t, zurueck = einsichten.uebernehmen(db, m)
assert kundenvorgabe.fuer_kunde(db, KUNDE)["maschine"] == "T11"
assert not any(x["feld"] == "maschine" for x in einsichten.kundenvorschlaege(db)), "schon Vorgabe: kein Vorschlag"
zurueck()
assert kundenvorgabe.fuer_kunde(db, KUNDE) is None
t, zurueck2 = einsichten.uebernehmen(db, lz)
assert kundenvorgabe.kopfwerte(db, KUNDE)["lieferzeit_art"] == "Arbeitstage"
zurueck2()
einsichten.ablehnen(db, m)
assert not any(x["feld"] == "maschine" for x in einsichten.kundenvorschlaege(db)), "abgelehnt bleibt weg"
db.angebot_aendern(ids[-1], "lieferzeit_wert", "20")
assert not any(x["feld"] == "lieferzeit" for x in einsichten.kundenvorschlaege(db)), "nur bei 3 gleichen Werten"
assert any(e["quelle"] == "einsicht" for e in lernen.uebersicht(db)) is False
db.angebot_aendern(ids[-1], "lieferzeit_wert", "15")
assert any(e["quelle"] == "einsicht" and e["bereich"] == "Vorschlag: Kundenvorgabe" for e in lernen.uebersicht(db))
assert any(a["art"] == "muster" and "Kundenvorgabe" in a["text"] for a in automatik.aufgaben(db))
ok("I7: Maschine und Lieferzeit nach 3 gleichen Angeboten als Kundenvorgabe vorgeschlagen, mit Rückgängig, Ablehnen")

# ------------------------------------------------------------------ I8 Reklamation
alt = ids[0]
db.vorgang_setzen(alt, "Beauftragt")
p_alt = next(p for p in db.positionen(alt) if p.get("profil_id"))
reklamation.speichern(db, alt, dict(position_id=p_alt["id"], menge=5, datum="2026-10-12",
                                    fehlerart="Grat oder Schlacke", ursache="intern: Fertigung"))
neu = db.positionen(ids[1])
p_neu = next(p for p in neu if p.get("profil_id"))
treffer = {p_neu["id"]: [SimpleNamespace(art=wiederholteile.SICHER, position=p_alt,
                                         angebot=dict(id=alt, nummer="2026-00001"))]}
pk = einsichten.reklamation_punkte(db, treffer, neu)
assert len(pk) == 1 and "reklamiert (12.10.2026: Grat oder Schlacke, Ursache intern: Fertigung)" in pk[0][1], pk
treffer[p_neu["id"]][0].art = wiederholteile.AEHNLICH
assert einsichten.reklamation_punkte(db, treffer, neu) == [], "nur sichere bzw. zu prüfende Wiederholteile"
ok(f"I8: {pk[0][1]}")

# ------------------------------------------------------------------ I9 Nachkalkulation
for i, (soll, ist) in zip(ids, ((2.0, 2.5), (1.0, 1.2), (3.0, 3.6))):
    nk = dict(soll=dict(profile=["QR 40x40x3"], zeilen=[["Laserzeit", "laser_h", "h", soll, ist, 100, 120, True]]))
    db.con.execute("UPDATE angebote SET nachkalkulation=? WHERE id=?", (json.dumps(nk), i))
db.con.commit()
h = einsichten.nachkalk_hinweis(db, dict(kundennr=KUNDE), [])
assert h and "3 Aufträge dieses Kunden" in h and "20 % länger" in h, h
h2 = einsichten.nachkalk_hinweis(db, dict(kundennr="K-fremd"), [dict(profil_id="QR 40x40x3")])
assert h2 and "mit diesen Profilen" in h2, h2
assert einsichten.nachkalk_hinweis(db, dict(kundennr=KUNDE), [], ohne_id=ids[0]) is None, "nur 2 Aufträge: nichts"
ok(f"I9: {h}")

# ------------------------------------------------------------------ I10 Selbstkorrektur
for n in range(3):
    lernen.entscheiden(db, lernen.ZUSATZ, KUNDE, "Entgraten", True, 100 + n)
assert lernen.wirksam(db, lernen.ZUSATZ, KUNDE) == {"Entgraten": lernen.JA}
lernen.angewendet(db, lernen.ZUSATZ, KUNDE, ["Entgraten"])
rueck = dict(art="positionsfelder", angebot_id=ids[1], alt=[],
             gelernt=dict(art=lernen.ZUSATZ, kundennr=KUNDE, schluessel=["Entgraten"]))
e1 = automatik.merken(db, "gelernt", "Test 1", ids[1], rueck)
e2 = automatik.merken(db, "gelernt", "Test 2", ids[1], rueck)
assert "verlernt" not in automatik.rueckgaengig(db, e1)
assert lernen.wirksam(db, lernen.ZUSATZ, KUNDE) == {"Entgraten": lernen.JA}, "einmal zurück: bleibt gelernt"
zeile = next(e for e in lernen.uebersicht(db) if e["quelle"] == lernen.TABELLE)
assert "1× selbst angewendet, 1× zurückgenommen" in zeile["was"], zeile["was"]
t = automatik.rueckgaengig(db, e2)
assert "verlernt: „Entgraten“" in t and lernen.wirksam(db, lernen.ZUSATZ, KUNDE) == {}, t
ok("I10: zweimal zurückgenommen = verlernt; Lernzentrale zählt angewendet und zurückgenommen")

# ------------------------------------------------------------------ I11 Zeiten
grund = db.einstellung("programmierung_zeit")
weitere = [beispiel_angebot.anlegen(db, dict(kundennr="K-2", kunde="Zwei")) for _ in range(3)]
for i in ids + weitere:
    for p in db.positionen(i):
        if p.get("profil_id"):
            db.position_aendern(p["id"], "prog_zeit", 8.0)
            db.position_aendern(p["id"], "zeit_manuell", 12.0)
z = einsichten.zeit_vorschlaege(db)
pz = next((x for x in z if x["art"] == "progzeit"), None)
sz = next((x for x in z if x["art"] == "schneidzeit"), None)
assert pz and pz["angebote"] == 6 and pz["faktor"] > 1.2 and sz and not einsichten.uebernehmbar(sz), z
t, zurueck = einsichten.uebernehmen(db, pz)
assert db.einstellung("programmierung_zeit") == pz["neu"]["programmierung_zeit"] > grund
zurueck()
assert db.einstellung("programmierung_zeit") == grund
einsichten.ablehnen(db, sz)
assert not any(x["art"] == "schneidzeit" and x["schluessel"] == sz["schluessel"] for x in einsichten.zeit_vorschlaege(db))
ok(f"I11: {pz['text']}")

# ------------------------------------------------------------------ I12 Verlustmuster
heute = datetime.date(2026, 11, 10)


def z_(i, kunde, vorgang, netto, grund=None):
    return dict(id=i, kunde=kunde, vorgang=vorgang, vk_netto=netto, datum="2026-10-01",
                versand=[absage.eintrag(grund)] if grund else [])


zeilen = ([z_(i, "A", "Beauftragt", 300) for i in range(6)]
          + [z_(10 + i, "B", "Abgelehnt", 5000, "Preis zu hoch") for i in range(4)] + [z_(20, "B", "Beauftragt", 5000)])
werk = {z["id"]: {"1.4301"} if z["kunde"] == "B" else {"S235"} for z in zeilen}
vm = einsichten.verlust_aus(zeilen, werk, {"1.4301": "Edelstahl", "S235": "Stahl"}, heute)
assert len(vm) == 2 and any(t.startswith("Edelstahl, 2.000 bis 10.000 €: 4 von 5 abgelehnt, meist „Preis zu hoch“")
                            for t in vm) and any(t.startswith("Kunde B") for t in vm), vm
assert einsichten.verlust_aus(zeilen[:8], werk, {}, heute) == [], "zu wenige in der Gruppe"
b = monatsbericht.bericht(db, 2026, 11)
assert b["verlust"] == []
monatsbericht.pdf(tmp / "m.pdf", dict(b, verlust=vm), {})
assert (tmp / "m.pdf").stat().st_size > 1000
ok(f"I12: {vm[0]}")

# ------------------------------------------------------------------ Schalter
db.einstellung_setzen(funktionen.REGELVORSCHLAEGE, "nein")
assert einsichten.vorschlaege(db) == [] and einsichten.text(db) is None
db.einstellung_setzen(funktionen.PREIS_HINWEISE, "nein")
treffer[p_neu["id"]][0].art = wiederholteile.SICHER
assert einsichten.reklamation_punkte(db, treffer, neu) == [] and einsichten.verlustmuster(db) == []
assert einsichten.nachkalk_hinweis(db, dict(kundennr=KUNDE), []) is None
for n in funktionen.INTELLIGENZ:
    db.einstellung_setzen(n, "ja")
s = fenster.angebot_oeffnen(ids[1])
assert isinstance(s._einsicht_punkte(), list)
d = fenster.lernzentrale(dialog=lambda d: None)
ok("Schalter: Vorschläge und Hinweise aus; Lernzentrale und Angebots-Check laufen")
print("Alle Einsichten-Tests bestanden.")
