"""Maschinenplanung mit Datenbank und Server: Einrichten, Anmeldung, Rollen, Aufträge ohne Dubletten, Einplanen mit
Vorschau, Nachrücken, fixierte Belegungen, Konflikte zweier gleichzeitig angemeldeter Benutzer, Live-Meldungen,
Historie, Sicherung und Wiederöffnen der Datei.

Aufruf: python tests/test_planung_server.py
"""
import http.cookiejar
import json
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from planung.datenbank import Planungsdatenbank  # noqa: E402
from planung.server import starten  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Planungsdatenbank(tmp / "planung.db")
srv = starten(db, "127.0.0.1", 0)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASIS = f"http://127.0.0.1:{srv.server_address[1]}"


class Sitzung:
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def __call__(self, methode, pfad, daten=None, kennung=True, erwartet=200):
        req = urllib.request.Request(BASIS + pfad, method=methode,
                                     data=json.dumps(daten).encode() if daten is not None else None)
        req.add_header("Content-Type", "application/json")
        if kennung:
            req.add_header("X-Planung", "1")
        try:
            with self.op.open(req, timeout=10) as r:
                status, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        antwort = json.loads(body) if body else None
        assert status == erwartet, (methode, pfad, status, antwort)
        return antwort


anna, bernd, gast = Sitzung(), Sitzung(), Sitzung()

# 1) Einrichten: erster Benutzer wird Verwalter, danach nicht mehr möglich
assert anna("GET", "/api/status")["eingerichtet"] is False
anna("POST", "/api/einrichten", dict(name="Anna", passwort="geheim123", anzeige="Anna"))
bernd("POST", "/api/einrichten", dict(name="x", passwort="geheim123"), erwartet=403)
assert anna("GET", "/api/status")["benutzer"]["rolle"] == "verwalten"
anna("POST", "/api/benutzer", dict(name="bernd", passwort="geheim456", rolle="planen", anzeige="Bernd"))
anna("POST", "/api/benutzer", dict(name="gast", passwort="geheim789", rolle="lesen"))
bernd("POST", "/api/anmelden", dict(name="bernd", passwort="falsch!!"), erwartet=401)
bernd("POST", "/api/anmelden", dict(name="Bernd", passwort="geheim456"))
gast("POST", "/api/anmelden", dict(name="gast", passwort="geheim789"))
# ohne Anmeldung / ohne Kennung / falsche Rolle
Sitzung()("GET", "/api/plan?von=2026-10-19T00:00&bis=2026-10-26T00:00", erwartet=401)
bernd("POST", "/api/auftraege", dict(auftragsnummer="X"), kennung=False, erwartet=403)
gast("POST", "/api/auftraege", dict(auftragsnummer="X"), erwartet=403)
bernd("PUT", "/api/maschinen/T03/schichten", dict(schichten=[]), erwartet=403)

# 2) Maschinen und Kalender: drei Maschinen, Schichtmodell T03 und LT7 (Testwerte), Feiertage
ms = anna("GET", "/api/kalender")["maschinen"]
assert [m["id"] for m in ms] == ["T03", "T11", "LT7"], ms
for m in ("T03", "LT7"):
    anna("PUT", f"/api/maschinen/{m}/schichten",
         dict(schichten=[dict(wochentag=w, beginn="06:00", ende="14:00") for w in range(5)]))
anna("PUT", "/api/maschinen/T03/schichten", dict(schichten=[dict(wochentag=9, beginn="06:00", ende="14:00")]),
     erwartet=400)
assert anna("POST", "/api/feiertage", dict(jahr=2026))["eingetragen"] == 9
assert anna("POST", "/api/feiertage", dict(jahr=2026))["eingetragen"] == 0          # keine Dubletten

# 3) Aufträge: Pflichtfelder, keine doppelte Auftragsnummer, Zahlen mit Komma
a1 = bernd("POST", "/api/auftraege", dict(auftragsnummer="A-1", kunde="Testkunde 1", maschinenzeit_min="420",
                                          ruestzeit_min="60", liefertermin="2026-11-06", prioritaet=1))
a2 = bernd("POST", "/api/auftraege", dict(auftragsnummer="A-2", kunde="Testkunde 2", maschinenzeit_min="240,5",
                                          liefertermin="2026-11-04"))
a3 = bernd("POST", "/api/auftraege", dict(auftragsnummer="A-3", maschinenzeit_min=120, maschinen_erlaubt="lt7"))
bernd("POST", "/api/auftraege", dict(auftragsnummer="A-1"), erwartet=400)
bernd("POST", "/api/auftraege", dict(auftragsnummer="A-9", liefertermin="31.02.2026"), erwartet=400)
bernd("POST", "/api/auftraege", dict(auftragsnummer="A-9", maschinen_erlaubt="T99"), erwartet=400)
assert a2["maschinenzeit_min"] == 240.5 and a3["maschinen_erlaubt"] == "LT7"

# 4) Einplanen mit Vorschau: A-1 Montag 02.11. 06:00 auf T03, 480 min = bis 14:00
v = bernd("POST", "/api/plan/vorschau", dict(auftrag_id=a1["id"], maschine="T03", beginn="2026-11-02T06:00"))
assert not v["fehler"] and v["belegungen"][0]["ende"] == "2026-11-02T14:00", v
bernd("POST", "/api/plan/speichern", dict(aenderung=dict(auftrag_id=a1["id"], maschine="T03",
                                                         beginn="2026-11-02T06:00"),
                                          maschinen_versionen=v["maschinen_versionen"], grund="Erstplanung"))
# A-2 über zwei Tage: 240,5 min ab Di 12:00
v = bernd("POST", "/api/plan/vorschau", dict(auftrag_id=a2["id"], maschine="T03", beginn="2026-11-03T12:00"))
assert v["belegungen"][0]["ende"] == "2026-11-04T08:01", v          # 08:00:30 auf die Minute aufgerundet
bernd("POST", "/api/plan/speichern", dict(aenderung=dict(auftrag_id=a2["id"], maschine="T03", beginn="2026-11-03T12:00"),
                                          maschinen_versionen=v["maschinen_versionen"]))
# schon eingeplant
v = bernd("POST", "/api/plan/vorschau", dict(auftrag_id=a2["id"], maschine="T03", beginn="2026-11-05T06:00"))
assert v["fehler"], v
# A-3 ist nur für LT7 freigegeben: Warnung auf T03
v = bernd("POST", "/api/plan/vorschau", dict(auftrag_id=a3["id"], maschine="T03", beginn="2026-11-06T06:00"))
assert any("nur für LT7" in w for w in v["warnungen"]), v

plan = gast("GET", "/api/plan?von=2026-11-02T00:00&bis=2026-11-09T00:00")
t03 = next(m for m in plan["maschinen"] if m["id"] == "T03")
assert t03["kennzahlen"]["verfuegbar_min"] == 5 * 480, t03["kennzahlen"]
assert t03["kennzahlen"]["geplant_min"] == 480 + 241, t03["kennzahlen"]
t11 = next(m for m in plan["maschinen"] if m["id"] == "T11")
assert t11["ohne_schicht"] and t11["kennzahlen"]["auslastung"] is None
b1 = next(b for b in plan["belegungen"] if b["auftragsnummer"] == "A-1")
b2 = next(b for b in plan["belegungen"] if b["auftragsnummer"] == "A-2")
assert b1["risiko"] == "ok" and (b2["risiko"], b2["puffer_tage"]) == ("kritisch", 0), (b1, b2)   # endet am Liefertag

# 5) Überschneidung ohne Nachrücken wird abgelehnt, mit Nachrücken rückt A-2 hinter A-1
aend = dict(id=b1["id"], maschine="T03", beginn="2026-11-03T08:00")
v = bernd("POST", "/api/plan/vorschau", aend)
assert any("überschneidet" in f for f in v["fehler"]), v
bernd("POST", "/api/plan/speichern", dict(aenderung=aend, maschinen_versionen=v["maschinen_versionen"]), erwartet=400)
aend["nachruecken"] = True
v = bernd("POST", "/api/plan/vorschau", aend)
assert not v["fehler"], v
assert [b["auftragsnummer"] for b in v["belegungen"]] == ["A-1", "A-2"], v
assert v["belegungen"][0]["ende"] == "2026-11-04T08:00" and v["belegungen"][1]["beginn"] == "2026-11-04T08:00", v

# 6) Zwei Benutzer gleichzeitig: Anna speichert zuerst eine andere Änderung auf T03, Bernds Vorschau ist veraltet
va = anna("POST", "/api/plan/vorschau", dict(id=b2["id"], maschine="T03", beginn="2026-11-05T06:00"))
anna("POST", "/api/plan/speichern", dict(aenderung=dict(id=b2["id"], maschine="T03", beginn="2026-11-05T06:00"),
                                         maschinen_versionen=va["maschinen_versionen"], grund="Kunde verschoben"))
k = bernd("POST", "/api/plan/speichern", dict(aenderung=aend, maschinen_versionen=v["maschinen_versionen"]),
          erwartet=409)
assert "inzwischen von Anna geändert" in k["fehler"] and k["letzte"]["benutzer"] == "Anna", k
# Auftrag gleichzeitig bearbeiten: zweite Speicherung mit alter Version scheitert, nichts wird überschrieben
alt = bernd("GET", "/api/auftraege")
x = next(a for a in alt if a["auftragsnummer"] == "A-3")
anna("PUT", f"/api/auftraege/{x['id']}", dict(daten=dict(kunde="Anna war hier"), version=x["version"]))
k = bernd("PUT", f"/api/auftraege/{x['id']}", dict(daten=dict(kunde="Bernd"), version=x["version"]), erwartet=409)
assert k["aktuell"]["kunde"] == "Anna war hier" and "Anna" in k["fehler"], k

# 7) Fixierte Belegung wird beim Nachrücken nicht verschoben
plan = bernd("GET", "/api/plan?von=2026-11-02T00:00&bis=2026-11-09T00:00")
b2 = next(b for b in plan["belegungen"] if b["auftragsnummer"] == "A-2")
t03v = next(m for m in plan["maschinen"] if m["id"] == "T03")["version"]
bernd("POST", "/api/plan/speichern", dict(aenderung=dict(id=b2["id"], maschine="T03", beginn=b2["beginn"], fixiert=True),
                                          maschinen_versionen={"T03": t03v}))
b1 = next(b for b in plan["belegungen"] if b["auftragsnummer"] == "A-1")
v = bernd("POST", "/api/plan/vorschau", dict(id=b1["id"], maschine="T03", beginn="2026-11-05T06:00", nachruecken=True))
assert any("fixiert" in f for f in v["fehler"]), v

# 8) Verschieben auf eine andere Maschine prüft beide Maschinen; Stillstand verschiebt das Ende
v = bernd("POST", "/api/plan/vorschau", dict(id=b1["id"], maschine="LT7", beginn="2026-11-02T06:00"))
assert set(v["maschinen_versionen"]) == {"T03", "LT7"} and not v["fehler"], v
bernd("POST", "/api/plan/speichern", dict(aenderung=dict(id=b1["id"], maschine="LT7", beginn="2026-11-02T06:00"),
                                          maschinen_versionen=v["maschinen_versionen"]))
bernd("POST", "/api/stillstaende", dict(maschine="LT7", beginn="2026-11-02T10:00", ende="2026-11-02T12:00",
                                        art="Wartung"))
plan = gast("GET", "/api/plan?von=2026-11-02T00:00&bis=2026-11-09T00:00")
b1 = next(b for b in plan["belegungen"] if b["auftragsnummer"] == "A-1")
assert (b1["maschine"], b1["ende"]) == ("LT7", "2026-11-03T08:00"), b1
assert len(plan["stillstaende"]) == 1

# 9) Live-Meldung: eine offene Ereignis-Verbindung bekommt Bernds nächste Änderung
ereignis = []


def lauschen():
    req = urllib.request.Request(BASIS + "/api/ereignisse")
    with gast.op.open(req, timeout=10) as r:
        for zeile in r:
            zeile = zeile.decode().strip()
            if zeile.startswith("event: aenderung"):
                ereignis.append(json.loads(next(r).decode()[6:]))
                return


t = threading.Thread(target=lauschen, daemon=True)
t.start()
import time  # noqa: E402
time.sleep(0.3)
bernd("POST", "/api/auftraege", dict(auftragsnummer="A-4"))
t.join(5)
assert ereignis and ereignis[0]["benutzer"] == "Bernd", ereignis

# 10) Historie, Dashboard, Ausplanen
h = gast("GET", f"/api/historie?objekt=belegung&id={b2['id']}")
assert any(e["grund"] == "Kunde verschoben" and e["benutzer"] == "Anna" for e in h), h
d = gast("GET", "/api/dashboard")
assert [m["id"] for m in d["maschinen"]] == ["T03", "T11", "LT7"] and len(d["maschinen"][0]["wochen"]) == 5
assert any(a["auftragsnummer"] == "A-3" for a in d["ungeplant"])
v = bernd("POST", "/api/plan/vorschau", dict(id=b1["id"], maschine="LT7", beginn=b1["beginn"], entfernen=True))
bernd("POST", "/api/plan/speichern", dict(aenderung=dict(id=b1["id"], maschine="LT7", beginn=b1["beginn"],
                                                         entfernen=True), maschinen_versionen=v["maschinen_versionen"]))
assert all(b["auftragsnummer"] != "A-1" for b in gast("GET", "/api/plan?von=2026-11-02T00:00&bis=2026-11-09T00:00")
           ["belegungen"])

# 11) Rollen ändern wirkt sofort, letzter Verwalter bleibt
anna("PUT", "/api/benutzer/bernd", dict(rolle="lesen"))
bernd("POST", "/api/auftraege", dict(auftragsnummer="A-5"), erwartet=403)
anna("PUT", "/api/benutzer/anna", dict(rolle="lesen"), erwartet=400)

# 12) Sicherung geprüft, Datei lässt sich wieder öffnen und enthält alles
pfad = Path(anna("POST", "/api/sicherung")["pfad"])
assert pfad.exists() and sqlite3.connect(pfad).execute("PRAGMA integrity_check").fetchone()[0] == "ok"
srv.shutdown()
db.schliessen()
db2 = Planungsdatenbank(tmp / "planung.db")
assert len(db2.auftraege()) == 4 and len(db2.belegungen()) == 1 and db2.benutzer_anzahl() == 3
kopie = Planungsdatenbank(pfad)
assert len(kopie.auftraege()) == 4

print("OK: Anmeldung, Rollen, Aufträge, Vorschau, Nachrücken, Konflikte zweier Benutzer, Live-Meldung, Historie, "
      "Sicherung")
