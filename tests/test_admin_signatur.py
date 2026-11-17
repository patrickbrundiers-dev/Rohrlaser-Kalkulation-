"""Signierte Admin-Vorgaben (Systemprüfung 17.11.2026, Befunde SEC-01 und SEC-02, admin_signatur.py).

Vorher konnte jeder mit Schreibrecht im gemeinsamen Ordner die Datei Admin/admin_vorgaben.json fälschen (Prüfsumme neu
rechnen) und so Admin-Passwort, Admin-Liste und geschützte Werte wie den Gewinn an allen Plätzen ersetzen; ohne Paket
lief das Admin-Passwort sogar über den normalen Abgleich. Geprüft wird:

S1 Hauptadmin signiert mit dem Schlüssel seiner Hauptadmin-Lizenz, jeder Platz nimmt das Paket an und merkt sich das.
S2 Fälschungen werden abgelehnt (ohne Signatur, Inhalt geändert, eigener „Hauptadmin“-Anker) – Werte bleiben, Hinweis.
S3 Admin-Passwort aus einer manipulierten Datendatei geht nicht mehr über den normalen Abgleich (SEC-02).
S4 Weiterer Admin signiert mit dem Schlüssel aus seinem Passwort; er darf keine Rechte ändern; gesperrt = abgelehnt.
S5 Übergang: ohne Hauptadmin-Lizenz im Betrieb wie bisher (unsignierte Pakete, test_admin_schutz.py).

Aufruf: python tests/test_admin_signatur.py
"""
import json
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from rohrlaser import admin_schutz, admin_signatur as sig, hauptadmin as H, lizenz as L, passwort, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK     " + text)


# Testschlüssel statt Patricks Lizenzschlüssel (nur in diesem Prozess)
LIZENZ_PRIVAT = Ed25519PrivateKey.generate()
L.standard_schluessel = lambda: {"T9": L.oeffentlich_text(LIZENZ_PRIVAT)}
SCHNELL = dict(n=2 ** 14, r=8, p=1)
HAUPT_PW = "Haupt-Pass-123"

tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()
datei = gemeinsam / admin_schutz.ORDNER / admin_schutz.DATEI


def platz(name, k):
    d = Datenbank(tmp / name / "rohrlaser.db")
    d.einstellung_setzen("benutzer_name", name)
    d.einstellung_setzen("benutzer_kuerzel", k)
    d.einstellung_setzen("teilen_ordner", str(gemeinsam))
    return d


def abgleich(db, sitzung, art=None):
    admin_schutz.SITZUNG = sitzung
    return teilen.abgleichen(db, art) if art else teilen.abgleichen(db)


def paket():
    return json.loads(datei.read_text("utf-8"))


def schreiben(p):
    datei.write_text(json.dumps(p, ensure_ascii=False), "utf-8")


kein = admin_schutz.Sitzung()
pb, ma = platz("Patrick", "PB"), platz("Max", "MA")
pb.einstellung_setzen("passwort", HAUPT_PW)

# ---------------------------------------------------------------- S1 Hauptadmin signiert
daten = H.erstellen("Patrick", HAUPT_PW, LIZENZ_PRIVAT, "T9", "HA-2026-0001", kdf=SCHNELL)
seed = H.tresor_oeffnen(daten, HAUPT_PW)
assert seed is not None
haupt = admin_schutz.Sitzung()
haupt.freischalten(admin_schutz.HAUPTADMIN, sig.hauptadmin_schluessel(daten, seed))
assert "seed" not in repr(haupt.schluessel) and seed.hex() not in repr(haupt.schluessel)
pb.einstellung_setzen("gewinn", 0.21)
abgleich(pb, haupt, teilen.ZUSAMMENFUEHREN)
p = paket()
assert p["signatur"]["art"] == sig.HAUPT and p["signatur"]["anker"]["inhalt"]["lizenz_id"] == "HA-2026-0001"
assert "tresor" not in p["signatur"]["anker"], "nie den Tresor in den Ordner"
assert admin_schutz.signiert_gemerkt(pb)
abgleich(ma, kein, teilen.UEBERNEHMEN)
assert ma.einstellung("gewinn") == 0.21 and ma.passwort_pruefen(HAUPT_PW)
assert admin_schutz.signiert_gemerkt(ma), "MA merkt sich: ab jetzt nur noch signierte Pakete"
ok("S1 Hauptadmin signiert die Admin-Vorgaben, der andere Platz übernimmt sie und merkt sich die Signatur")

# ---------------------------------------------------------------- S2 Fälschungen
echt = paket()


def faelschen(aendern, signatur=True):
    p = json.loads(json.dumps(echt))
    aendern(p)
    p["stand"] = "2099-01-01T00:00:00"
    p["hash"] = admin_schutz._hash(p["inhalt"])
    if not signatur:
        p.pop("signatur", None)
    schreiben(p)
    return abgleich(ma, kein)


def boese(p):
    p["inhalt"]["einstellungen"]["passwort"] = json.dumps(passwort.hash_bilden("max123"))
    p["inhalt"]["einstellungen"]["gewinn"] = "0.01"


# a) wie im Nachweis der Prüfung: ohne Signatur
b = faelschen(boese, signatur=False)
assert ma.einstellung("gewinn") == 0.21 and ma.passwort_pruefen(HAUPT_PW) and not ma.passwort_pruefen("max123")
assert any("abgelehnt" in h and "nicht signiert" in h for h in b["hinweise"]), b["hinweise"]
# b) Signatur des Hauptadmins behalten, Inhalt geändert (Prüfsumme neu)
b = faelschen(boese)
assert ma.einstellung("gewinn") == 0.21 and any("passt nicht" in h for h in b["hinweise"]), b["hinweise"]
# c) eigener Anker: selbst gebaute „Hauptadmin-Lizenz“ mit eigenem Lizenzschlüssel
fremd = Ed25519PrivateKey.generate()
f_daten = H.erstellen("Max", "Max-Pass-1234", fremd, "T9", "HA-2026-0099", kdf=SCHNELL)
f_schl = sig.hauptadmin_schluessel(f_daten, H.tresor_oeffnen(f_daten, "Max-Pass-1234"))
p = json.loads(json.dumps(echt))
boese(p)
p["stand"], p["hash"] = "2099-01-01T00:00:00", admin_schutz._hash(p["inhalt"])
schreiben(sig.signieren(p, f_schl))
b = abgleich(ma, kein)
assert ma.einstellung("gewinn") == 0.21 and any("nicht von Patrick signiert" in h for h in b["hinweise"]), b["hinweise"]
# d) gesperrte Hauptadmin-Lizenz
assert sig.pruefen(echt, {}, {}, gesperrt={"HA-2026-0001"})[0] is None
assert sig.pruefen(echt, {}, {})[0] == sig.HAUPT
# beim Hauptadmin selbst ebenso: die Fälschung ändert dort nichts
b = abgleich(pb, kein)
assert pb.einstellung("gewinn") == 0.21 and pb.passwort_pruefen(HAUPT_PW)
schreiben(echt)
ok("S2 Fälschungen abgelehnt (ohne Signatur, Inhalt geändert, eigener Anker, gesperrte Lizenz) – Werte bleiben, Hinweis")

# ---------------------------------------------------------------- S3 Admin-Passwort nicht über den normalen Abgleich
time.sleep(1.1)
ma.con.execute("UPDATE einstellungen SET wert=? WHERE name='passwort'", (json.dumps(passwort.hash_bilden("max123")),))
ma.con.commit()
abgleich(ma, kein)
abgleich(pb, kein)
assert pb.passwort_pruefen(HAUPT_PW) and not pb.passwort_pruefen("max123"), "SEC-02: manipulierte Datendatei"
abgleich(ma, kein)
assert ma.passwort_pruefen(HAUPT_PW), "das signierte Paket stellt das Passwort am manipulierten Platz wieder her"
ok("S3 Admin-Passwort aus einer manipulierten Datendatei geht nicht über den Abgleich; das Paket stellt es wieder her")

# ---------------------------------------------------------------- S4 weiterer Admin
assert admin_schutz.recht_setzen(pb, "MA", admin_schutz.ADMIN, "Max", "Start-123") == ""
e = admin_schutz.admins(pb)["MA"]
assert e["salz"] and e["pub"] and "Start-123" not in json.dumps(e)
abgleich(pb, haupt)
abgleich(ma, kein)
e = admin_schutz.admins(ma)["MA"]
assert sig.admin_schluessel("MA", "falsch-123", e, SCHNELL) is None
assert sig.admin_schluessel("MA", "Start-123", {"recht": "admin", "hash": "x"}) is None, "Eintrag ohne Schlüssel"
s_ma = admin_schutz.Sitzung()
s_ma.freischalten("MA", sig.admin_schluessel("MA", "Start-123", e))
assert s_ma.schluessel is not None
assert admin_schutz.passwort_aendern(ma, "MA", "Mein-Pass-1", s_ma) == ""      # Startpasswort ändern (eigener Eintrag)
ma.einstellung_setzen("gewinn", 0.3)
abgleich(ma, s_ma)
assert paket()["signatur"]["art"] == sig.ADMIN and paket()["signatur"]["kuerzel"] == "MA"
abgleich(pb, kein)
assert pb.einstellung("gewinn") == 0.3, "Wert des weiteren Admins gilt beim Hauptadmin"
assert sig.admin_schluessel("MA", "Mein-Pass-1", admin_schutz.admins(pb)["MA"]) is not None, "neues Passwort kam an"
# Admin will sich Rechte geben: neuen Admin XY eintragen → abgelehnt
liste = admin_schutz.admins(ma)
liste["XY"] = dict(recht=admin_schutz.ADMIN, name="Komplize", **sig.admin_eintrag("xy-pass-1"))
ma.einstellung_setzen(admin_schutz.ADMINS, liste)
ma.einstellung_setzen("gewinn", 0.4)
abgleich(ma, s_ma)
b = abgleich(pb, kein)
assert "XY" not in admin_schutz.admins(pb) and pb.einstellung("gewinn") == 0.3
assert any("nicht ändern" in h for h in b["hinweise"]), b["hinweise"]
# Hauptadmin sperrt MA: Pakete von MA gelten danach nicht mehr
haupt.freischalten(admin_schutz.HAUPTADMIN)
assert admin_schutz.recht_setzen(pb, "MA", admin_schutz.GESPERRT) == ""
abgleich(pb, haupt)
abgleich(ma, kein)
assert admin_schutz.recht(ma, "MA") == admin_schutz.GESPERRT and "XY" not in admin_schutz.admins(ma)
ma.einstellung_setzen("gewinn", 0.5)
s_ma.freischalten("MA", s_ma.schluessel)
p = admin_schutz.inhalt(ma)
q = {"format": admin_schutz.FORMAT, "stand": "2099-01-01T00:00:00", "von": "Max (MA)", "version": "x",
     "schema": admin_schutz.schema(ma), "hash": admin_schutz._hash(p), "inhalt": p, "verlauf": []}
schreiben(sig.signieren(q, s_ma.schluessel))
b = abgleich(pb, kein)
assert pb.einstellung("gewinn") == 0.3 and any("kein Admin" in h for h in b["hinweise"]), b["hinweise"]
ok("S4 weiterer Admin signiert mit eigenem Schlüssel, ändert keine Rechte; gesperrter Admin wird abgelehnt")

# ---------------------------------------------------------------- S5 ohne Signaturschlüssel kein Paket mehr
ohne = admin_schutz.Sitzung()
ohne.freischalten(admin_schutz.HAUPTADMIN)          # z. B. Einstellungs-Passwort an einem Platz ohne Hauptadmin-Lizenz
pb.einstellung_setzen("gewinn", 0.25)
assert admin_schutz.paket_schreiben(pb, ohne) is False, "unsigniertes Paket nähme kein Platz mehr an"
# frischer Betrieb ohne Hauptadmin-Lizenz: unsigniert wie bisher, nichts gemerkt
alt_ordner = tmp / "Alt"
alt_ordner.mkdir()
x = Datenbank(tmp / "x" / "rohrlaser.db")
x.einstellung_setzen("teilen_ordner", str(alt_ordner))
x.einstellung_setzen("benutzer_kuerzel", "XX")
x.einstellung_setzen("passwort", "geheim")
assert admin_schutz.paket_schreiben(x, ohne) is True and "signatur" not in json.loads(
    (alt_ordner / admin_schutz.ORDNER / admin_schutz.DATEI).read_text("utf-8"))
assert not admin_schutz.signiert_gemerkt(x) and admin_schutz.gueltig(admin_schutz.paket_lesen(x))
ok("S5 gemerkter Platz schreibt ohne Schlüssel nichts; ohne Hauptadmin-Lizenz im Betrieb wie bisher (unsigniert)")

for d in (pb, ma, x):
    d.schliessen()
print("Alle Signatur-Prüfungen bestanden.")
