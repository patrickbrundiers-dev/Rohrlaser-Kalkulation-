"""Prüft die Zusammenarbeit über den gemeinsamen Ordner (teilen.py, Patrick 28.10.2026, Freigabe „Alles 1-4“):
wer arbeitet woran (geöffnete Angebote in der Info der Datei), Angebot an einen Kollegen übergeben (auch über einen
dritten Mitarbeiter hinweg, zurücknehmen), Übernahme anfragen (ablehnen, übergeben) und Konflikte (dieselbe
Stammdatenzeile hier und beim Kollegen geändert: gemerkt, verlorene Fassung wiederherstellbar).

Aufruf: python tests/test_teilen_zusammenarbeit.py
"""
import datetime
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import teilen  # noqa: E402
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


def nach_nummer(db, nr):
    return next((a for a in db.angebote() if a["nummer"] == nr), None)


POS = dict(pos=10, artikel="T-1", bezeichnung="Holm", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
           stueck=5, schneidweg=320, einstiche=2)

pb = arbeitsplatz("Patrick", "PB")
a1 = pb.angebot_neu(dict(kunde="Kunde A", datum="2026-10-28"))
a2 = pb.angebot_neu(dict(kunde="Kunde B", datum="2026-10-28"))
pb.position_neu(a1, POS)
pb.netz_speichern(pb.positionen(a1)[0]["id"], b"NETZ" * 50)
n1, n2 = pb.angebot(a1)["nummer"], pb.angebot(a2)["nummer"]
teilen.abgleichen(pb)
mk = arbeitsplatz("Martin", "MK")
teilen.abgleichen(mk, teilen.UEBERNEHMEN)
xy = arbeitsplatz("Xaver", "XY")
teilen.abgleichen(xy, teilen.UEBERNEHMEN)
assert nach_nummer(mk, n1)["fremd"] == "PB" and nach_nummer(xy, n1)["fremd"] == "PB"
teilen.abgleichen(mk)
teilen.abgleichen(pb)
assert set(teilen.kollegen(pb)) == {"MK", "XY"} and set(teilen.kollegen(mk)) == {"PB", "XY"}

# ---------------------------------------------------------------- 2 wer arbeitet woran
teilen.schreiben(pb, offen={n1: "2026-10-28T10:12:00"})
teilen.lesen(mk)
assert teilen.offen_bei(mk, n1) == ("PB", "2026-10-28T10:12:00")
assert teilen.offen_bei(mk, n2) is None and teilen.offen_bei(pb, n1) is None
spaeter = datetime.datetime.now() + datetime.timedelta(minutes=teilen.FRISCH_MIN + 1)
assert teilen.offen_bei(mk, n1, spaeter) is None, "alte Datei (Programm abgestürzt): gilt nicht mehr als geöffnet"
teilen.schreiben(pb, offen={})
teilen.lesen(mk)
assert teilen.offen_bei(mk, n1) is None
ok("geöffnete Angebote stehen in der Datei; Kollege sieht „PB seit 10:12“, nach FRISCH_MIN ohne Schreiben nicht mehr")

# ---------------------------------------------------------------- 3 übergeben
teilen.uebergeben(pb, a1, "mk", "bitte fertig rechnen")
a = pb.angebot(a1)
assert a["fremd"] == "MK" and a["bearbeiter"] == "MK", a
assert teilen.vorgang_offen(pb, n1, teilen.UEBERGABE)["an"] == "MK"
try:
    teilen.uebergeben(pb, a1, "XY")
    raise AssertionError("schon übergeben")
except teilen.TeilenFehler:
    pass
teilen.abgleichen(pb)
teilen.abgleichen(pb)
assert pb.angebot(a1) is not None, "Übergabe unterwegs: Angebot bleibt beim Absender"
b = teilen.abgleichen(xy)
assert nach_nummer(xy, n1) is None and b["angebote_weg"] == 1, "bei PB nicht mehr: beim Dritten erst einmal weg"
b = teilen.abgleichen(mk)
assert [u["nummer"] for u in b["uebernommen"]] == [n1] and b["uebernommen"][0]["notiz"] == "bitte fertig rechnen"
m1 = nach_nummer(mk, n1)
assert not m1["fremd"] and m1["bearbeiter"] == "MK" and len(mk.positionen(m1["id"])) == 1
assert list(mk.netze(m1["id"]).values()) == [b"NETZ" * 50], "3D-Netze kommen mit"
b = teilen.abgleichen(mk)
assert not b["uebernommen"], "nur einmal übernommen"
teilen.abgleichen(pb)
assert teilen.vorgang_offen(pb, n1, teilen.UEBERGABE) is None, "übernommen: Vorgang erledigt"
assert pb.angebot(a1)["fremd"] == "MK"
b = teilen.abgleichen(xy)
assert nach_nummer(xy, n1)["fremd"] == "MK" and not b["hinweise"], b["hinweise"]
mk.angebot_aendern(m1["id"], "kunde", "Kunde A (MK)")
teilen.abgleichen(mk)
teilen.abgleichen(pb)
assert pb.angebot(a1)["kunde"] == "Kunde A (MK)", "Absender sieht den Stand des neuen Bearbeiters"
ok("Übergabe PB → MK mit Notiz und 3D-Netz; PB sieht es nur noch an; XY sieht es danach bei MK; kein Doppel-Hinweis")

teilen.uebergeben(pb, a2, "XY")
assert pb.angebot(a2)["fremd"] == "XY"
assert teilen.zuruecknehmen(pb, a2) and not pb.angebot(a2)["fremd"] and pb.angebot(a2)["bearbeiter"] == "PB"
assert teilen.vorgang_offen(pb, n2, teilen.UEBERGABE) is None and not teilen.zuruecknehmen(pb, a2)
teilen.abgleichen(pb)
assert not teilen.abgleichen(xy)["uebernommen"]
ok("Übergabe zurücknehmen, solange der Kollege sie nicht übernommen hat")

# ---------------------------------------------------------------- 2 Übernahme anfragen
f2 = nach_nummer(mk, n2)
assert f2["fremd"] == "PB"
v = teilen.anfragen(mk, f2["id"], "Kunde hat mich angerufen")
assert teilen.anfragen(mk, f2["id"]) == v, "eine Anfrage je Angebot"
teilen.abgleichen(mk)
b = teilen.abgleichen(pb)
assert [(x["nummer"], x["von"], x["notiz"]) for x in b["anfragen"]] == [(n2, "MK", "Kunde hat mich angerufen")]
assert len(teilen.abgleichen(pb)["anfragen"]) == 1, "ohne Antwort wird wieder gefragt"
teilen.beantworten(pb, b["anfragen"][0], False, "mache ich selbst")
assert not teilen.abgleichen(pb)["anfragen"]
b = teilen.abgleichen(mk)
assert b["abgelehnt"] == [dict(nummer=n2, von="PB", notiz="mache ich selbst")]
assert teilen.vorgang_offen(mk, n2, teilen.ANFRAGE) is None
teilen.abgleichen(pb)
assert not teilen._vorgaenge(pb), "Antwort gesehen: Absage erledigt"
assert not teilen.abgleichen(mk)["abgelehnt"]
ok("Übernahme anfragen: Bearbeiter wird gefragt (bis zur Antwort), Absage mit Notiz kommt beim Kollegen an")

teilen.anfragen(mk, f2["id"])
teilen.abgleichen(mk)
b = teilen.abgleichen(pb)
teilen.beantworten(pb, b["anfragen"][0], True)
assert pb.angebot(a2)["fremd"] == "MK"
teilen.abgleichen(pb)
b = teilen.abgleichen(mk)
assert [u["nummer"] for u in b["uebernommen"]] == [n2] and not nach_nummer(mk, n2)["fremd"]
assert teilen.vorgang_offen(mk, n2, teilen.ANFRAGE) is None
teilen.abgleichen(pb)
assert not teilen._vorgaenge(pb) and not teilen.abgleichen(pb)["anfragen"]
ok("Übernahme anfragen und zusagen: Angebot wechselt zu MK, Anfrage erledigt")

# ---------------------------------------------------------------- 4 Konflikte
teilen.abgleichen(pb)
teilen.abgleichen(mk)
kunde = pb.zeilen("kunden", True)[0]
uid = kunde["uid"]
k_mk = next(z for z in mk.zeilen("kunden", True) if z["uid"] == uid)
pb.aendern("kunden", kunde["id"], "bemerkung", "PB sagt A")
mk.aendern("kunden", k_mk["id"], "bemerkung", "MK sagt B")
teilen.abgleichen(pb)
time.sleep(0.01)
b = teilen.abgleichen(mk)                      # MK erfasst später: seine Änderung ist jünger und gewinnt
assert len(b["konflikte"]) == 1, b["konflikte"]
k = b["konflikte"][0]
assert k["gewinner"] == "MK" and k["verlierer"] == "PB" and k["verloren"]["bemerkung"] == "PB sagt A"
assert k["text"].startswith("Kunden:"), k["text"]
b = teilen.abgleichen(pb)
assert len(b["konflikte"]) == 0 or b["konflikte"][0]["gewinner"] == "MK"
assert next(z for z in pb.zeilen("kunden", True) if z["uid"] == uid)["bemerkung"] == "MK sagt B"
assert teilen.konflikte(mk, offen_nur=True)[0]["id"] == k["id"]
assert "Konflikte" in teilen.bericht_text(dict(konflikte=[k]))
teilen.konflikt_erledigt(mk, k["id"], wiederherstellen=True)
assert next(z for z in mk.zeilen("kunden", True) if z["uid"] == uid)["bemerkung"] == "PB sagt A"
assert not teilen.konflikte(mk, offen_nur=True)
time.sleep(0.01)
b = teilen.abgleichen(mk)
assert not b["konflikte"]
teilen.abgleichen(pb)
assert next(z for z in pb.zeilen("kunden", True) if z["uid"] == uid)["bemerkung"] == "PB sagt A"
ok("Konflikt: jüngere Änderung gewinnt, verlorene Fassung gemerkt und wiederhergestellt (kommt bei allen an)")

pb.aendern("kunden", kunde["id"], "bemerkung", "nur PB")
teilen.abgleichen(pb)
assert not teilen.abgleichen(mk)["konflikte"], "nur eine Seite geändert: kein Konflikt"
ok("nur eine Seite geändert: kein Konflikt")

# ---------------------------------------------------------------- Stand der Dateien (Auto-Abgleich)
s1 = teilen.dateien_stand(mk)
assert s1 == teilen.dateien_stand(mk) and {k for k, _, _ in s1} == {"PB", "XY"}
time.sleep(0.02)
teilen.schreiben(pb, offen={n2: "x"})
assert teilen.dateien_stand(mk) != s1
ok("Stand der Dateien der Kollegen: unverändert = nichts zu lesen")

for d in (pb, mk, xy):
    d.con.close()
print("OK: Zusammenarbeit über den gemeinsamen Ordner")
