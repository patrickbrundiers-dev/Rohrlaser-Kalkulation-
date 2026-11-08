"""Prüft „Mehr Intelligenz“ (Plan Patrick 08.11.2026, Freigabe „Alle Empfehlungen“): I1 Preis-Plausibilität gegen
frühere Teile ähnlicher Länge, I2 Auftragschance offener Angebote, I3 Erkennungswort und I4 Arbeitsgang-Regel aus
Handeinträgen, I5 Wettbewerbsabstand aus Absagen, I6 Lieferzeit aus der Ist-Durchlaufzeit.

Aufruf: python tests/test_intelligenz.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import absage, automatik, fertigung, lernen, muster, plausibel, zusatz_erkennung  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ I1 ohne Datenbank
w = dict(profil_id="QR 40x40x3", werkstoff_id="S235", eur_kg=8.0, laenge=1000)
fein = {("QR 40x40x3", "S235"): [(950, 5.0), (1100, 5.2), (1000, 4.8), (900, 5.1), (1050, 5.0), (300, 20.0)]}
f = plausibel._fein(w, fein)
assert f and f[2] == 5 and abs(f[1] - 5.0) < 1e-9 and f[0] > plausibel.FEIN_FAKTOR, f
assert plausibel._fein(dict(w, laenge=300), fein) is None, "kurze Teile: zu wenige ähnliche"
assert plausibel._fein(w, {("QR 40x40x3", "S235"): fein[("QR 40x40x3", "S235")][:3]}) is None
verl = [[dict(datum="2026-11-01", kennwerte=[dict(profil_id="A", werkstoff_id="B", eur_kg=3.0, laenge=500)])],
        [dict(datum="2026-10-01", kennwerte=[dict(profil_id="A", werkstoff_id="B", eur_kg=4.0)])]]
assert plausibel.fein_aus(verl) == {("A", "B"): [(500, 3.0)]}, "alte Einträge ohne Länge zählen nicht"
ok("I1: Vergleich nur mit Teilen ähnlicher Länge (ab 5), ab 1,5-facher Abweichung; alte Werte ohne Länge zählen nicht")

# ------------------------------------------------------------------ I2 Chance
heute = datetime.date(2026, 11, 8)


def z(i, kunde, vorgang, netto, datum="2026-11-01"):
    return dict(id=i, kundennr=kunde, kunde=kunde, vorgang=vorgang, vk_netto=netto, datum=datum, versand=[])


zeilen = [z(1, "A", "Beauftragt", 1000), z(2, "A", "Beauftragt", 1200), z(3, "A", "Beauftragt", 900),
          z(4, "B", "Abgelehnt", 1000), z(5, "B", "Abgelehnt", 1100), z(6, "B", "Abgelehnt", 800),
          z(7, "A", "Verschickt", 1000), z(8, "B", "Verschickt", 1000), z(9, "A", "Verschickt", 1000, "2026-05-01")]
c = lernen.chancen(zeilen, heute)
assert set(c) == {7, 8, 9} and c[7] > c[8] and c[9] < c[7], c
assert lernen.chancen(zeilen[:2] + zeilen[6:], heute) == {}, "zu wenig entschiedene Angebote"
ok(f"I2: Chance Kunde A {100 * c[7]:.0f} %, Kunde B {100 * c[8]:.0f} %, altes Angebot {100 * c[9]:.0f} %")

# ------------------------------------------------------------------ Datenbank
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
zusatz = next(z["name"] for z in db.zeilen("zusatzarbeiten") if z.get("aktiv") != "nein" and not z.get("erkennung"))
for n in range(4):                      # vier Angebote: „graviert“ bekommt immer die Zusatzarbeit von Hand
    aid = beispiel_angebot.anlegen(db, dict(kundennr="K-7", kunde="Strahl GmbH"))
    for p in db.positionen(aid):
        if p.get("profil_id"):
            db.position_aendern(p["id"], "bezeichnung", ("Riegel", "Pfosten", "Querholm", "Sprosse")[n] + " graviert")
            db.position_aendern(p["id"], "zusatz", json.dumps([dict(name=zusatz)]))
v = muster.vorschlaege(db)
wort = next((x for x in v if x["art"] == "wort" and x["wert"] == "graviert"), None)
assert wort and wort["zusatz"] == zusatz and wort["angebote"] == 4, v
regel = next((x for x in v if x["art"] == "regel" and x["feld"] == "kundennr" and x["wert"] == "K-7"), None)
assert regel, v
t, zurueck = muster.uebernehmen(db, wort)
zz = next(x for x in db.zeilen("zusatzarbeiten") if x["name"] == zusatz)
assert "graviert" in zusatz_erkennung.woerter(zz), zz
assert not any(x["art"] == "wort" for x in muster.vorschlaege(db)), "schon eingetragen: kein Vorschlag mehr"
zurueck()
assert "graviert" not in zusatz_erkennung.woerter(next(x for x in db.zeilen("zusatzarbeiten") if x["name"] == zusatz))
t, zurueck = muster.uebernehmen(db, regel)
r = next(x for x in db.zeilen("arbeitsgang_regeln") if x["zusatzarbeit"] == zusatz and x.get("kundennr") == "K-7")
assert r["zuordnung"] == "Vorschlag" and r["aktiv"] == "ja"
assert not any(x["art"] == "regel" and x["feld"] == "kundennr" for x in muster.vorschlaege(db))
zurueck()
muster.ablehnen(db, wort)
assert not any(x.get("wert") == "graviert" for x in muster.vorschlaege(db)), "abgelehnt bleibt weg"
assert lernen.MUSTER_AB in lernen.EINSTELLUNGEN_GETEILT
assert any(e["quelle"] == "muster" for e in lernen.uebersicht(db))
assert any(a["art"] == "muster" for a in automatik.aufgaben(db))
ok(f"I3/I4: „{zusatz}“ bei „graviert“ bzw. Kunde K-7 erkannt, übernehmen mit Rückgängig, Ablehnen bleibt")

# ------------------------------------------------------------------ I5 Wettbewerbsabstand
ids = []
for vorgang, netto, preis in [("Beauftragt", 1000, None), ("Abgelehnt", 1200, 1000), ("Abgelehnt", 1100, 1000)]:
    x = beispiel_angebot.anlegen(db, dict(kundennr="K-8", kunde="Wettbewerb AG"))
    db.vorgang_setzen(x, vorgang)
    db.con.execute("UPDATE angebote SET vk_netto=? WHERE id=?", (netto, x))
    if preis:
        db.con.execute("UPDATE angebote SET versand=? WHERE id=?",
                       (json.dumps([absage.eintrag("Preis zu hoch", preis=preis)]), x))
db.con.commit()
t = lernen.trefferquote(db, "K-8")
assert t["n_abstand"] == 2 and abs(t["abstand"] - 0.15) < 1e-9, t
assert "15 % teurer als der Wettbewerb" in lernen.treffer_text(t), lernen.treffer_text(t)
ok(f"I5: {lernen.treffer_text(t)}")

# ------------------------------------------------------------------ I6 Durchlaufzeit
liste = fertigung.status_liste(db)
for n, tage in enumerate((10, 12, 14)):
    x = beispiel_angebot.anlegen(db, dict(kundennr="K-9", kunde="Termin KG"))
    db.vorgang_setzen(x, "Beauftragt")
    start = datetime.date(2026, 9, 1) + datetime.timedelta(days=n)
    db.con.execute("INSERT INTO auftrag_status (angebot_id, status, am) VALUES (?, ?, ?)",
                   (x, liste[0], start.isoformat() + "T08:00:00"))
    db.con.execute("INSERT INTO auftrag_status (angebot_id, status, am) VALUES (?, ?, ?)",
                   (x, liste[-1], (start + datetime.timedelta(days=tage * 7 // 5)).isoformat() + "T15:00:00"))
db.con.commit()
d = lernen.durchlauf(db)
assert d and d["n"] == 3 and 8 <= d["median"] <= 13, d
h = lernen.lieferzeit_hinweis(db, dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="3"))
assert h and "zugesagt 3 Arbeitstage" in h, h
assert lernen.lieferzeit_hinweis(db, dict(lieferzeit_art="Arbeitstage", lieferzeit_wert="30")) is None
ok(f"I6: {h}")

# ------------------------------------------------------------------ Oberfläche
d = fenster.lernzentrale(dialog=lambda d: None)
assert "Übernehmen" in d.knoepfe
fenster.start.neu_laden() if hasattr(fenster, "start") else None
print("Alle Intelligenz-Tests bestanden.")
