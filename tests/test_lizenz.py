"""Lizenz (programm/rohrlaser/lizenz.py) und Lizenz-Werkzeug (werkzeuge/lizenz_werkzeug.py): Fälle L1–L18, S7.

Jeder Lauf erzeugt ein eigenes Testschlüsselpaar; der echte Schlüssel kommt in keinem Test vor.
Aufruf: python tests/test_lizenz.py
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "werkzeuge"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from rohrlaser import lizenz  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="lizenz_"))
fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


PRIVAT = Ed25519PrivateKey.generate()
FREMD = Ed25519PrivateKey.generate()
SCHL = {"T1": lizenz.oeffentlich_text(PRIVAT)}
HEUTE = datetime.date(2026, 11, 15)
RECHNER = lizenz.rechner_id("1234abcd-0000-1111-2222-333344445555")


def lizenzdatei(art="benutzer", bis=HEUTE + datetime.timedelta(days=100), rechner=None, privat=PRIVAT, **mehr):
    inhalt = dict(lizenz_id="L-2026-0001", art=art, inhaber="Max Mustermann", firma="Musterbau GmbH",
                  ausgestellt="2026-11-01", gueltig_ab="2026-11-01",
                  gueltig_bis=bis.isoformat() if bis else None,
                  rechner=[RECHNER] if rechner is None else rechner, funktionen=["alle"], test=art == "test",
                  schluessel_id="T1", hinweis="")
    inhalt.update(mehr)
    return dict(format=1, inhalt=inhalt, signatur=lizenz.signieren(inhalt, privat))


def zustand(daten, heute=HEUTE, **k):
    k.setdefault("durchsetzung", True)
    return lizenz.ermitteln(daten, heute, k.pop("rechner", RECHNER), SCHL, **k)


# ------------------------------------------------------------------ Rechner-ID
pruefe(len(RECHNER) == 22 and RECHNER.startswith("RL-") and RECHNER.count("-") == 4,
       f"Rechner-ID im Format RL-XXXX-XXXX-XXXX-XXXX ({RECHNER})")
pruefe(lizenz.rechner_id("1234ABCD-0000-1111-2222-333344445555") == RECHNER, "Rechner-ID unabhängig von Groß/klein")
pruefe(lizenz.rechner_id("") == "", "ohne Kennung: leere ID")
eigene = lizenz.rechner_id()
pruefe(eigene == "" or eigene.startswith("RL-"), f"Rechner-ID dieses Rechners ({eigene or 'keine'})")

# ------------------------------------------------------------------ L1–L10
z = zustand(lizenzdatei())
pruefe(z.stufe == "gueltig" and not z.nur_lesen and z.darf() and z.tage_rest == 100, "L1 gültige Benutzerlizenz")
z = zustand(lizenzdatei(bis=HEUTE + datetime.timedelta(days=20)))
pruefe(z.stufe == "bald" and z.farbe == "gelb" and not z.nur_lesen and not z.start_hinweis, "L2 20 Tage: läuft bald ab")
z = zustand(lizenzdatei(bis=HEUTE + datetime.timedelta(days=5)))
pruefe(z.stufe == "bald" and z.start_hinweis, "L2 5 Tage: zusätzlich Hinweis beim Start")
z = zustand(lizenzdatei(bis=HEUTE))
pruefe(z.stufe == "bald" and z.tage_rest == 0, "gültig_bis gilt einschließlich (letzter Tag)")
z = zustand(lizenzdatei(bis=HEUTE - datetime.timedelta(days=5)))
pruefe(z.stufe == "kulanz" and z.farbe == "rot" and not z.nur_lesen and "Lesemodus ab" in z.hinweis,
       f"L3 seit 5 Tagen abgelaufen: Kulanz ({z.hinweis})")
z = zustand(lizenzdatei(bis=HEUTE - datetime.timedelta(days=14)))
pruefe(z.stufe == "kulanz", "14 Tage abgelaufen: noch Kulanz")
z = zustand(lizenzdatei(bis=HEUTE - datetime.timedelta(days=15)))
pruefe(z.stufe == "lesemodus" and z.nur_lesen, "15 Tage abgelaufen: Lesemodus")
z = zustand(lizenzdatei(bis=HEUTE - datetime.timedelta(days=30)))
pruefe(z.stufe == "lesemodus" and "abgelaufen" in z.nur_lesen and not z.darf(), f"L4 30 Tage: Lesemodus ({z.nur_lesen})")

d = lizenzdatei()
d["inhalt"]["gueltig_bis"] = "2099-12-31"
z = zustand(d)
pruefe(z.stufe == "lesemodus" and "Signatur" in z.nur_lesen, "L5 Ablaufdatum geändert: ungültig")
d = json.loads(json.dumps(lizenzdatei(), indent=4))          # andere Leerzeichen/Reihenfolge: bleibt gültig
pruefe(zustand(json.dumps(d, indent=3, sort_keys=False)).stufe == "gueltig", "Leerzeichen in der Datei ändern nichts")
z = zustand(lizenzdatei(privat=FREMD))
pruefe(z.stufe == "lesemodus" and "Signatur" in z.nur_lesen, "L6 fremder Schlüssel: ungültig")
z = zustand(lizenzdatei(rechner=["RL-0000-0000-0000-0000"]))
pruefe(z.stufe == "lesemodus" and "andere Rechner-ID" in z.nur_lesen and RECHNER in z.nur_lesen,
       "L7 falscher Rechner")
z = zustand(lizenzdatei(rechner=[]))
pruefe(z.stufe == "gueltig", "Benutzer mit rechner [] gilt überall")
z = zustand(lizenzdatei(rechner=[RECHNER.lower().replace("-", "- ", 1)]))
pruefe(z.stufe == "gueltig", "Rechner-ID unabhängig von Schreibweise")
z = zustand(lizenzdatei(art="admin", bis=None))
pruefe(z.stufe == "admin" and z.admin and z.darf() and not z.hinweis, "L8 Admin ohne Datum, Rechner passt")
z = zustand(lizenzdatei(art="admin", bis=None), heute=datetime.date(2040, 1, 1))
pruefe(z.stufe == "admin", "Admin auch in 13 Jahren")
z = zustand(lizenzdatei(bis=None))
pruefe(z.stufe == "lesemodus" and "Ablaufdatum" in z.nur_lesen, "L9 Benutzer ohne Datum: ungültig")
z = zustand(lizenzdatei(art="admin", bis=None, rechner=[]))
pruefe(z.stufe == "lesemodus" and "Rechner" in z.nur_lesen, "L9 Admin ohne Rechner: ungültig")
z = zustand(lizenzdatei(art="admin", bis=None, rechner=[RECHNER, "RL-1", "RL-2", "RL-3"]))
pruefe(z.stufe == "lesemodus", "Admin mit 4 Rechnern: ungültig")
d = lizenzdatei()
d["format"] = 2
z = zustand(d)
pruefe(z.stufe == "lesemodus" and "neuere Programmversion" in z.nur_lesen, "L10 unbekanntes Format: neuere Version")
d = lizenzdatei(schluessel_id="K9")
z = zustand(d)
pruefe(z.stufe == "lesemodus" and "unbekanntem Schlüssel" in z.nur_lesen, "unbekannte Schlüssel-ID")
z = zustand(lizenzdatei(gueltig_ab="2026-12-01"))
pruefe(z.stufe == "lesemodus" and "erst ab" in z.nur_lesen, "gültig_ab in der Zukunft")
z = zustand(lizenzdatei(art="test", bis=HEUTE + datetime.timedelta(days=10)))
pruefe(z.test and z.stufe == "bald" and "Testlizenz" in z.hinweis, "Testlizenz erkannt")
pruefe(not zustand(lizenzdatei()).test, "Benutzerlizenz ist keine Testlizenz")
z = zustand(lizenzdatei(funktionen=["schweissbaugruppen"]))
pruefe(z.darf("schweissbaugruppen") and not z.darf("anderes"), "Feld funktionen vorbereitet")
pruefe(zustand(lizenzdatei(funktionen=["alle", "unbekannt"])).darf("x"), "unbekannte Funktionsnamen stören nicht")
pruefe(zustand("kein json").stufe == "lesemodus", "kaputte Datei: Lesemodus")

# ------------------------------------------------------------------ L11–L12 Sperrliste
sl = lizenz.sperrliste_signieren(3, ["L-2026-0001"], PRIVAT, "T1")
pruefe(lizenz.sperrliste_pruefen(sl, SCHL) is not None, "Sperrliste gültig signiert")
z = zustand(lizenzdatei(), sperrliste=lizenz.sperrliste_pruefen(sl, SCHL))
pruefe(z.stufe == "lesemodus" and "gesperrt" in z.nur_lesen, "L11 Lizenz auf der Sperrliste")
z = zustand(lizenzdatei(art="admin", bis=None), sperrliste=lizenz.sperrliste_pruefen(sl, SCHL))
pruefe(z.stufe == "lesemodus", "auch Admin ist sperrbar")
falsch = dict(sl, gesperrt=["L-2026-0001", "L-2026-0002"])
pruefe(lizenz.sperrliste_pruefen(falsch, SCHL) is None, "veränderte Sperrliste zählt nicht")
pruefe(lizenz.sperrliste_pruefen(lizenz.sperrliste_signieren(4, [], FREMD, "T1"), SCHL) is None,
       "Sperrliste mit fremdem Schlüssel zählt nicht")
o = tmp / "sperr"
pruefe(lizenz.sperrliste_uebernehmen(o, sl, SCHL), "Sperrliste Stand 3 übernommen")
alt = lizenz.sperrliste_signieren(2, [], PRIVAT, "T1")
pruefe(not lizenz.sperrliste_uebernehmen(o, alt, SCHL), "L12 ältere Sperrliste (Stand 2) nicht übernommen")
pruefe(not lizenz.sperrliste_uebernehmen(o, sl, SCHL), "gleicher Stand nicht noch einmal")
pruefe(lizenz.sperrliste_pruefen(o / lizenz.SPERRLISTE, SCHL)["stand"] == 3, "Stand 3 bleibt")
pruefe(lizenz.sperrliste_uebernehmen(o, lizenz.sperrliste_signieren(4, [], PRIVAT, "T1"), SCHL)
       and lizenz.sperrliste_pruefen(o / lizenz.SPERRLISTE, SCHL)["gesperrt"] == [], "neuere Liste (Stand 4) ersetzt")

# ------------------------------------------------------------------ L13 Uhr
o = tmp / "uhr"
lic = o / lizenz.AKTIV
o.mkdir()
lic.write_text(json.dumps(lizenzdatei()), encoding="utf-8")
z, neu = lizenz.zustand_im_ordner(o, HEUTE, RECHNER, SCHL, durchsetzung=True)
pruefe(z.stufe == "gueltig" and neu == HEUTE.isoformat(), "Datum gemerkt")
z, neu = lizenz.zustand_im_ordner(o, HEUTE - datetime.timedelta(days=5), RECHNER, SCHL, durchsetzung=True)
pruefe(z.stufe == "lesemodus" and "Systemzeit prüfen" in z.nur_lesen and neu is None,
       "L13 Uhr 5 Tage zurück: Systemzeit prüfen, nichts gemerkt")
z, _ = lizenz.zustand_im_ordner(o, HEUTE - datetime.timedelta(days=2), RECHNER, SCHL, durchsetzung=True)
pruefe(z.stufe == "gueltig", "2 Tage zurück (Zeitzone, Datumswechsel): noch in Ordnung")
z, _ = lizenz.zustand_im_ordner(o, HEUTE, RECHNER, SCHL, durchsetzung=True)
pruefe(z.stufe == "gueltig", "L13 nach Korrektur wieder gültig")
(o / lizenz.ZEIT).unlink()
z, _ = lizenz.zustand_im_ordner(o, HEUTE - datetime.timedelta(days=5), RECHNER, SCHL,
                                db_zuletzt=HEUTE.isoformat(), durchsetzung=True)
pruefe(z.stufe == "lesemodus", "zeit.json gelöscht: Einstellung lizenz_zuletzt zählt weiter")
lic.write_text(json.dumps(lizenzdatei(art="admin", bis=None)), encoding="utf-8")
z, _ = lizenz.zustand_im_ordner(o, HEUTE - datetime.timedelta(days=50), RECHNER, SCHL,
                                db_zuletzt=HEUTE.isoformat(), durchsetzung=True)
pruefe(z.stufe == "admin", "Admin unabhängig von der Uhr")

# ------------------------------------------------------------------ L14 keine Lizenz, Stufe 1
o = tmp / "leer"
z, _ = lizenz.zustand_im_ordner(o, HEUTE, RECHNER, SCHL, durchsetzung=True)
pruefe(z.stufe == "lesemodus" and RECHNER in z.nur_lesen and RECHNER in z.hinweis, "L14 keine Lizenz: Rechner-ID im Hinweis")
z, _ = lizenz.zustand_im_ordner(o, HEUTE, RECHNER, SCHL, durchsetzung=False)
pruefe(z.stufe == "lesemodus" and not z.nur_lesen and z.darf() and "braucht das Programm eine Lizenz" in z.hinweis
       and z.farbe == "gelb", "Stufe 1: keine Sperre, nur Hinweis")
z = zustand(lizenzdatei(bis=HEUTE - datetime.timedelta(days=60)), durchsetzung=False)
pruefe(not z.nur_lesen and z.darf(), "Stufe 1: abgelaufene Lizenz sperrt nicht")
pruefe(lizenz.DURCHSETZUNG is True and lizenz.DURCHSETZUNG_AB == datetime.date(2026, 11, 20)
       and lizenz.STICHTAG == "20.11.2026", "Stufe 2 ab 20.11.2026 (Patrick 30.10.: b)")
pruefe(not lizenz.durchsetzung_aktiv(datetime.date(2026, 11, 19)) and lizenz.durchsetzung_aktiv(datetime.date(2026, 11, 20)),
       "Stufe 1 bis 19.11., Stufe 2 ab 20.11.")
pruefe(lizenz.durchsetzung_aktiv(datetime.date(2026, 11, 1), datetime.date(2026, 12, 1)),
       "Uhr zurückgestellt: das späteste gesehene Datum zählt")
z = lizenz.ermitteln(None, datetime.date(2026, 11, 19), RECHNER, SCHL)
pruefe(not z.nur_lesen and "Ab 20.11.2026 braucht das Programm eine Lizenz" in z.hinweis, "19.11. ohne Lizenz: Hinweis mit Termin")
z = lizenz.ermitteln(None, datetime.date(2026, 11, 20), RECHNER, SCHL)
pruefe(z.nur_lesen and z.durchsetzung, "20.11. ohne Lizenz: Lesemodus")
for art in ("benutzer", "admin"):
    z = lizenz.ermitteln(lizenzdatei(art=art, bis=None if art == "admin" else HEUTE + datetime.timedelta(days=100)),
                         HEUTE, RECHNER, SCHL, durchsetzung=True, veraendert="lizenz geändert")
    pruefe(z.stufe == "lesemodus" and "Programmdateien verändert (lizenz geändert)" in z.nur_lesen,
           f"veränderte Programmdateien: Lesemodus auch mit gültiger Lizenz ({art})")
z = lizenz.ermitteln(lizenzdatei(), HEUTE, RECHNER, SCHL, durchsetzung=False, veraendert="lizenz geändert")
pruefe(not z.nur_lesen and z.darf(), "veränderte Programmdateien in Stufe 1: nur Hinweis")

# ------------------------------------------------------------------ L15 Lizenz laden
o = tmp / "laden"
gut = tmp / "gut.lizenz"
gut.write_text(json.dumps(lizenzdatei()), encoding="utf-8")
inhalt = lizenz.lizenz_laden(o, gut, HEUTE, RECHNER, SCHL)
pruefe(inhalt["lizenz_id"] == "L-2026-0001" and lizenz.aktive_lizenz(o), "gültige Lizenz geladen")
vorher = (o / lizenz.AKTIV).read_text(encoding="utf-8")
for name, daten in (("verändert", dict(lizenzdatei(), signatur=lizenzdatei(privat=FREMD)["signatur"])),
                    ("anderer Rechner", lizenzdatei(rechner=["RL-0000-0000-0000-0000"])),
                    ("abgelaufen", lizenzdatei(bis=HEUTE - datetime.timedelta(days=40)))):
    schlecht = tmp / f"{name}.lizenz"
    schlecht.write_text(json.dumps(daten), encoding="utf-8")
    try:
        lizenz.lizenz_laden(o, str(schlecht), HEUTE, RECHNER, SCHL)
        pruefe(False, f"L15 ungültige Datei ({name}) abgelehnt")
    except lizenz.LizenzFehler as e:
        pruefe((o / lizenz.AKTIV).read_text(encoding="utf-8") == vorher, f"L15 {name}: abgelehnt, gültige bleibt ({e})")
lizenz.lizenz_laden(o, lizenzdatei(lizenz_id="L-2026-0002"), HEUTE, RECHNER, SCHL)
pruefe(len(list((o / lizenz.ALT).glob("*.lizenz"))) == 1, "ersetzte Lizenz liegt in alt/")

# ------------------------------------------------------------------ L11–L13 über den Update-Weg (L4)
from rohrlaser import update  # noqa: E402

rel = tmp / "release"
rel.mkdir()
(rel / update.DATEILISTE).write_text("{}", encoding="utf-8")
z = update.lizenz_zusatz(str(rel / update.DATEILISTE))
pruefe(z == dict(sperrliste=None, datum=None), "Update-Check ohne Sperrliste: nichts")
(rel / update.SPERRLISTE).write_text(json.dumps(lizenz.sperrliste_signieren(5, ["L-2026-0001"], PRIVAT, "T1")),
                                     encoding="utf-8")
z = update.lizenz_zusatz(str(rel / update.DATEILISTE))
o = tmp / "updateweg"
o.mkdir()
(o / lizenz.AKTIV).write_text(json.dumps(lizenzdatei(bis=datetime.date.today() + datetime.timedelta(days=90),
                                                      gueltig_ab=datetime.date.today().isoformat())),
                              encoding="utf-8")
stelle = lizenz.LizenzStelle(o, None, SCHL, RECHNER, durchsetzung=True)
pruefe(stelle.pruefen().stufe == "gueltig", "Update-Weg: vorher gültig")
pruefe(z["sperrliste"] and stelle.sperrliste(z["sperrliste"].decode()) and stelle.zustand.stufe == "lesemodus"
       and "gesperrt" in stelle.zustand.nur_lesen, "L11 Sperrliste über den Update-Check: gesperrt")
pruefe(not stelle.sperrliste(json.dumps(lizenz.sperrliste_signieren(4, [], PRIVAT, "T1"))),
       "L12 ältere Sperrliste über den Update-Check nicht übernommen")
pruefe(stelle.sperrliste(json.dumps(lizenz.sperrliste_signieren(6, [], PRIVAT, "T1")))
       and stelle.zustand.stufe == "gueltig", "neuere Sperrliste hebt die Sperre auf")
z = stelle.zeit_abgleich(datetime.date.today() + datetime.timedelta(days=5))
pruefe(z.stufe == "lesemodus" and "Systemzeit" in z.nur_lesen, "L13 Server-Datum 5 Tage voraus: Systemzeit prüfen")
(o / lizenz.ZEIT).unlink()
pruefe(stelle.pruefen().stufe == "gueltig", "L13 nach Korrektur wieder gültig")
pruefe(stelle.zeit_abgleich(datetime.date.today() - datetime.timedelta(days=30)).stufe == "gueltig",
       "älteres Server-Datum ändert nichts")
pruefe(stelle.zeit_abgleich(None).stufe == "gueltig", "ohne Server-Datum: nichts")

# ------------------------------------------------------------------ L16 Admin-Passwort beim Start
class _Db:
    """Nur was LizenzStelle braucht: Einstellungen und Lesemodus."""
    nur_lesen = ""

    def __init__(self, passwort):
        self.werte = dict(passwort=passwort)

    def einstellung(self, n):
        return self.werte.get(n)

    def einstellung_setzen(self, n, w):
        self.werte[n] = w

    def lesemodus(self, grund):
        self.nur_lesen = grund


from rohrlaser.lizenz_dialog import admin_beim_start  # noqa: E402

o = tmp / "adminstart"
o.mkdir()
(o / lizenz.AKTIV).write_text(json.dumps(lizenzdatei("admin", bis=None, rechner=[RECHNER], gueltig_ab=datetime.date.today().isoformat())), encoding="utf-8")


def admin_stelle(passwort="geheim"):
    st = lizenz.LizenzStelle(o, _Db(passwort), SCHL, RECHNER, durchsetzung=True)
    st.pruefen()
    return st


eingaben = []


def abfrage(werte):
    werte = list(werte)

    def f(_eltern, versuch):
        eingaben.append(versuch)
        return werte.pop(0) if werte else None
    return f


st = admin_stelle()
pruefe(st.zustand.stufe == "admin" and not st.zustand.admin and st.admin_passwort_noetig(),
       "L16 Admin-Lizenz mit Passwort: Abfrage nötig, vorher keine Admin-Rechte")
pruefe(admin_beim_start(st, abfrage(["geheim"])) and st.zustand.admin and not st.zustand.admin_aus,
       "L16 richtiges Passwort: Admin-Rechte")
eingaben.clear()
st = admin_stelle()
pruefe(admin_beim_start(st, abfrage(["a", "b", "geheim"])) and eingaben == [0, 1, 2],
       "L16 dritter Versuch richtig: Admin-Rechte")
eingaben.clear()
st = admin_stelle()
ok = admin_beim_start(st, abfrage(["a", "b", "c", "geheim"]))
pruefe(not ok and len(eingaben) == 3 and not st.zustand.admin and st.zustand.admin_aus
       and st.zustand.farbe == "gelb" and "Admin-Passwort" in st.zustand.hinweis and not st.zustand.nur_lesen,
       "L16 dreimal falsch: ohne Admin-Rechte, kein Lesemodus, gelber Hinweis")
pruefe(not st.pruefen().admin and "ohne Admin-Rechte" in st.text(), "L16 bleibt ohne Admin-Rechte nach erneuter Prüfung")
pruefe(not st.admin_freigeben("falsch") and st.admin_freigeben("geheim") and st.zustand.admin,
       "L16 Hilfe → Lizenz: Admin freischalten mit Passwort")
st = admin_stelle()
pruefe(not admin_beim_start(st, abfrage([])) and st.zustand.admin_aus, "L16 Abbrechen: ohne Admin-Rechte")
st = admin_stelle("")
eingaben.clear()
pruefe(admin_beim_start(st, abfrage([])) and not eingaben and st.zustand.admin,
       "L16 ohne Passwort in den Einstellungen: keine Abfrage, Admin-Rechte")
pruefe(not admin_beim_start(None), "L16 ohne Lizenzstelle: keine Abfrage")
pruefe(not admin_stelle().zustand.admin, "L16 ohne Passworteingabe (z. B. Abfrage abgestürzt): keine Admin-Rechte")
# ------------------------------------------------------------------ L17 Admin-Passwort in der Admin-Lizenz
from rohrlaser import passwort  # noqa: E402

LPW = passwort.hash_bilden("lizenz-pw-123")
o3 = tmp / "adminpw"
o3.mkdir()
(o3 / lizenz.AKTIV).write_text(json.dumps(lizenzdatei("admin", bis=None, rechner=[RECHNER], admin_passwort=LPW,
                                                      gueltig_ab=datetime.date.today().isoformat())), encoding="utf-8")
st = lizenz.LizenzStelle(o3, _Db("geheim"), SCHL, RECHNER, durchsetzung=True)
st.pruefen()
pruefe(st.admin_passwort_in_lizenz() and st.admin_passwort_noetig(), "L17 Admin-Lizenz mit Passwort: Abfrage nötig")
pruefe(not st.admin_freigeben("geheim") and not st.zustand.admin, "L17 Passwort der Einstellungen gilt nicht mehr")
pruefe(st.admin_freigeben("lizenz-pw-123") and st.zustand.admin and not st.notfall, "L17 Passwort der Lizenz gilt")
st = lizenz.LizenzStelle(o3, _Db(""), SCHL, RECHNER, durchsetzung=True)
st.pruefen()
pruefe(st.admin_passwort_noetig() and not st.zustand.admin,
       "L17 Einstellungen ohne Passwort: Abfrage trotzdem (Passwort steht in der Lizenz)")
pruefe(not lizenz.LizenzStelle(o, _Db("geheim"), SCHL, RECHNER, durchsetzung=True).admin_passwort_in_lizenz(),
       "L17 ältere Admin-Lizenz ohne Passwort: Passwort der Einstellungen gilt weiter (3a)")
for daten, text in ((lizenzdatei(admin_passwort=LPW), "Nur eine Admin-Lizenz"),
                    (lizenzdatei("admin", bis=None, admin_passwort="klartext"), "kein gültiger Hash")):
    try:
        lizenz.pruefen(daten, SCHL)
        pruefe(False, f"L17 abgelehnt: {text}")
    except lizenz.LizenzFehler as e:
        pruefe(text in str(e), f"L17 abgelehnt: {e}")
geaendert = lizenzdatei("admin", bis=None, admin_passwort=LPW)
geaendert["inhalt"]["admin_passwort"] = passwort.hash_bilden("eigenes")
pruefe(zustand(geaendert).stufe == "lesemodus", "L17 Passwort-Hash in der Lizenz getauscht: Signatur ungültig")
code = lizenz.notfallcode(RECHNER, datetime.date.today(), PRIVAT, "T1")
st = lizenz.LizenzStelle(o3, _Db(""), SCHL, RECHNER, durchsetzung=True)
st.pruefen()
pruefe(not st.admin_freigeben(lizenz.notfallcode(RECHNER, datetime.date.today(), FREMD, "T1")),
       "L17 Notfallcode mit fremdem Schlüssel: abgelehnt")
pruefe(not st.admin_freigeben(lizenz.notfallcode(lizenz.rechner_id("anders"), datetime.date.today(), PRIVAT, "T1")),
       "L17 Notfallcode für einen anderen Rechner: abgelehnt")
pruefe(st.admin_freigeben(" " + code + "\n") and st.zustand.admin and st.notfall, "L17 Notfallcode schaltet frei")
pruefe(lizenz.notfallcode_gueltig(code, RECHNER, datetime.date.today() + datetime.timedelta(days=1), SCHL)
       and not lizenz.notfallcode_gueltig(code, RECHNER, datetime.date.today() + datetime.timedelta(days=2), SCHL)
       and not lizenz.notfallcode_gueltig(code, RECHNER, datetime.date.today() - datetime.timedelta(days=1), SCHL)
       and not lizenz.notfallcode_gueltig("NF-T1-kaputt", RECHNER, schluessel=SCHL),
       "L17 Notfallcode gilt heute und morgen, sonst nicht")
alt_code = lizenz.notfallcode(RECHNER, datetime.date.today() - datetime.timedelta(days=5), PRIVAT, "T1")
pruefe(lizenz.notfallcode_gueltig(alt_code, RECHNER, datetime.date.today() - datetime.timedelta(days=5), SCHL)
       and not lizenz.notfallcode_gueltig(alt_code, RECHNER, datetime.date.today() - datetime.timedelta(days=5), SCHL,
                                          spaetestes=datetime.date.today()),
       "L17 Notfallcode: zurückgestellte Uhr macht einen alten Code nicht wieder gültig (spätestes Datum)")
o5 = tmp / "notfall_uhr"
o5.mkdir()
(o5 / lizenz.AKTIV).write_text((o3 / lizenz.AKTIV).read_text(encoding="utf-8"), encoding="utf-8")
(o5 / lizenz.ZEIT).write_text(json.dumps({"zuletzt": datetime.date.today().isoformat()}), encoding="utf-8")
st = lizenz.LizenzStelle(o5, _Db(""), SCHL, RECHNER, durchsetzung=True)
st.pruefen()
pruefe(not st.admin_freigeben(alt_code, heute=datetime.date.today() - datetime.timedelta(days=5)),
       "L17 Admin freischalten: alter Notfallcode mit zurückgestellter Uhr abgelehnt")

# ------------------------------------------------------------------ L18 ersetzte Admin-Lizenz (neues Passwort)
o4 = tmp / "ersetzt"
o4.mkdir()
alt_l = lizenzdatei("admin", bis=None, lizenz_id="L-2026-0010", admin_passwort=LPW)
neu_l = lizenzdatei("admin", bis=None, lizenz_id="L-2026-0011", admin_passwort=passwort.hash_bilden("neu-pw-12345"),
                    ersetzt="L-2026-0010")
lizenz.lizenz_laden(o4, alt_l, HEUTE, RECHNER, SCHL)
lizenz.lizenz_laden(o4, neu_l, HEUTE, RECHNER, SCHL)
try:
    lizenz.lizenz_laden(o4, alt_l, HEUTE, RECHNER, SCHL)
    pruefe(False, "L18 ersetzte Lizenz lässt sich nicht mehr laden")
except lizenz.LizenzFehler as e:
    pruefe("ersetzt" in str(e) and lizenz.pruefen(o4 / lizenz.AKTIV, SCHL)["lizenz_id"] == "L-2026-0011",
           "L18 ersetzte Lizenz lässt sich nicht mehr laden, neue bleibt aktiv")
(o4 / lizenz.AKTIV).write_text(json.dumps(alt_l), encoding="utf-8")       # von Hand zurückkopiert
z, _ = lizenz.zustand_im_ordner(o4, HEUTE, RECHNER, SCHL, durchsetzung=True, merken=False)
pruefe(z.stufe == "lesemodus" and "gesperrt" in z.grund, "L18 von Hand zurückkopierte alte Lizenz gilt nicht")

o2 = tmp / "adminladen"
o2.mkdir()
(o2 / lizenz.AKTIV).write_text(json.dumps(lizenzdatei(bis=datetime.date.today() + datetime.timedelta(days=90),
                                                       gueltig_ab=datetime.date.today().isoformat())), encoding="utf-8")
st = lizenz.LizenzStelle(o2, _Db("geheim"), SCHL, RECHNER, durchsetzung=True)
pruefe(st.pruefen().stufe == "gueltig", "L16 Benutzerlizenz geladen")
neu = tmp / "admin_neu.lizenz"
neu.write_text(json.dumps(lizenzdatei("admin", bis=None, rechner=[RECHNER], lizenz_id="L-2026-0009",
                                      gueltig_ab=datetime.date.today().isoformat())), encoding="utf-8")
z = st.laden(neu)
pruefe(z.stufe == "admin" and not z.admin and z.admin_aus, "L16 Admin-Lizenz im laufenden Programm geladen: erst Passwort")
pruefe(lizenz.STANDARD_MONATE == 3, "Vorgabe-Laufzeit Benutzerlizenz 3 Monate")

# ------------------------------------------------------------------ Lizenz-Werkzeug
umg = dict(os.environ, ROHRLASER_LIZENZ_PASSWORT="test-passwort-123", ROHRLASER_LIZENZ_ORDNER=str(tmp / "werkzeug"),
           ROHRLASER_ADMIN_PASSWORT="admin-test-123")
WZ = [sys.executable, str(WURZEL / "werkzeuge" / "lizenz_werkzeug.py")]


def wz(*args):
    r = subprocess.run(WZ + list(args), env=umg, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


code, aus = wz("schluessel-erzeugen")
pruefe(code == 0 and '"K1": "' in aus, "Werkzeug: Schlüsselpaar K1 erzeugt")
pem = (tmp / "werkzeug" / "privat_K1.pem").read_text()
pruefe("ENCRYPTED PRIVATE " + "KEY" in pem, "privater Schlüssel mit Passwort geschützt")
code, _ = wz("schluessel-erzeugen")
pruefe(code != 0 and (tmp / "werkzeug" / "privat_K1.pem").read_text() == pem, "vorhandener Schlüssel nie überschrieben")
k1 = aus.split('"K1": "')[1].split('"')[0]
code, aus = wz("erstellen", "--inhaber", "Max Mustermann", "--firma", "Musterbau GmbH", "--rechner", RECHNER)
pruefe(code == 0 and "L-" in aus, "Werkzeug: Benutzerlizenz erstellt")
code, aus2 = wz("admin", "--rechner", RECHNER, "--rechner", "RL-AAAA-BBBB-CCCC-DDDD")
code3, aus3 = wz("erstellen", "--art", "test", "--inhaber", "Interessent", "--beliebig")
code4, _ = wz("erstellen", "--inhaber", "Ohne Rechner")
pruefe(code == 0 and code3 == 0 and code4 != 0, "Werkzeug: Admin, Test (beliebig); ohne --rechner abgelehnt")
dateien = sorted((tmp / "werkzeug" / "Lizenzen").glob("*.lizenz"))
pruefe(len(dateien) == 3, f"drei Lizenzdateien ({', '.join(d.name for d in dateien)})")
s = {"K1": k1}
heute = datetime.date.today()
arten = {}
for d in dateien:
    inh = lizenz.pruefen(d, s)
    arten[inh["art"]] = (inh, lizenz.ermitteln(d, heute, RECHNER, s, durchsetzung=True))
b_inh, b_z = arten["benutzer"]
pruefe(passwort.pruefen("admin-test-123", arten["admin"][0].get("admin_passwort")),
       "Werkzeug: Admin-Lizenz enthält das Admin-Passwort als Hash")
code5, aus5 = wz("notfallcode", "--rechner", RECHNER)
nf = next((w for w in aus5.split() if w.startswith("NF-K1-")), "")
pruefe(code5 == 0 and lizenz.notfallcode_gueltig(nf, RECHNER, heute, s), "Werkzeug: Notfallcode für den Rechner")
import lizenz_werkzeug  # noqa: E402
erwartet = lizenz_werkzeug.monate_spaeter(heute, 3)
pruefe(b_z.stufe == "gueltig" and b_inh["gueltig_bis"] == erwartet.isoformat(),
       f"Benutzerlizenz 3 Monate ({b_inh['gueltig_bis']})")
pruefe(arten["admin"][1].stufe == "admin" and arten["admin"][0]["gueltig_bis"] is None, "Admin-Lizenz gültig")
t_inh, t_z = arten["test"]
pruefe(t_z.test and t_inh["rechner"] == [] and (datetime.date.fromisoformat(t_inh["gueltig_bis"]) - heute).days == 29,
       "Testlizenz 30 Tage, beliebiger Rechner")
pruefe(lizenz_werkzeug.monate_spaeter(datetime.date(2026, 11, 1), 6) == datetime.date(2027, 4, 30)
       and lizenz_werkzeug.monate_spaeter(datetime.date(2026, 8, 31), 6) == datetime.date(2027, 2, 27),
       "6 Monate: 1.11. bis 30.4., 31.8. bis 27.2.")
ids = sorted(lizenz.pruefen(d, s)["lizenz_id"] for d in dateien)
pruefe(ids == [f"L-{heute.year}-000{i}" for i in (1, 2, 3)], f"Lizenz-IDs fortlaufend ({ids})")
code, aus = wz("pruefen", str(dateien[0]))
pruefe("Signatur" in aus, "Werkzeug: pruefen gibt Ergebnis aus")
code, aus = wz("sperren", ids[0])
sp = json.loads((tmp / "werkzeug" / "Sperrliste.json").read_text(encoding="utf-8"))
pruefe(code == 0 and lizenz.sperrliste_pruefen(sp, s) == dict(stand=1, gesperrt=[ids[0]], schluessel_id="K1"),
       "Werkzeug: Sperrliste Stand 1 signiert")
wz("sperren", ids[1])
sp = json.loads((tmp / "werkzeug" / "Sperrliste.json").read_text(encoding="utf-8"))
pruefe(lizenz.sperrliste_pruefen(sp, s)["stand"] == 2 and len(sp["gesperrt"]) == 2, "zweite Sperrung: Stand 2")
code, aus = wz("liste")
pruefe(code == 0 and sum(z.startswith("L-") for z in aus.splitlines()) == 3 and "GESPERRT" in aus, "Werkzeug: liste mit Register")
umg["ROHRLASER_LIZENZ_PASSWORT"] = "falsch-falsch"
code, aus = wz("erstellen", "--inhaber", "X", "--beliebig")
pruefe(code != 0 and "Passwort falsch" in aus, "falsches Passwort abgelehnt")

# Fenster des Werkzeugs (Doppelklick auf Lizenz-Werkzeug.exe)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import lizenz_werkzeug_fenster  # noqa: E402

fw = lizenz_werkzeug_fenster.QApplication.instance() or lizenz_werkzeug_fenster.QApplication([])
w = lizenz_werkzeug_fenster.Fenster(tmp / "werkzeug")
pruefe(w.tabelle.rowCount() == 3 and not w.schluessel_knopf.isEnabled() and "K1" in w.ordner_text.text(),
       "Werkzeug-Fenster: Register mit 3 Lizenzen, Schlüssel K1 vorhanden")
w.art.setCurrentIndex(2)
pruefe(not w.bis.isEnabled() and w.inhaber.text() == "Patrick", "Werkzeug-Fenster: Admin ohne Datum")
w.art.setCurrentIndex(0)
q = w.bis.date()
pruefe(datetime.date(q.year(), q.month(), q.day()) == lizenz_werkzeug.monate_spaeter(heute, 3),
       "Werkzeug-Fenster: Benutzer 3 Monate vorgeschlagen")
w2 = lizenz_werkzeug_fenster.Fenster(tmp / "werkzeug_leer")
pruefe(w2.schluessel_knopf.isEnabled() and w2.tabelle.rowCount() == 0, "Werkzeug-Fenster ohne Schlüssel")

# ------------------------------------------------------------------ S7 Repository
git = subprocess.run(["git", "ls-files"], cwd=WURZEL, capture_output=True, text=True)
if git.returncode == 0:
    treffer = []
    for rel in git.stdout.split():
        p = WURZEL / rel
        if p.suffix.lower() in (".pem", ".lizenz", ".key"):
            treffer.append(rel)
            continue
        try:
            if p.stat().st_size < 5_000_000 and b"PRIVATE " + b"KEY" in p.read_bytes():
                treffer.append(rel)
        except OSError:
            pass
    pruefe(not treffer, f"S7 kein privater Schlüssel im Repository {treffer or ''}")
ignor = (WURZEL / ".gitignore").read_text(encoding="utf-8").split()
pruefe("*.pem" in ignor and "*.lizenz" in ignor, ".gitignore enthält *.pem und *.lizenz")
from rohrlaser.lizenz_schluessel import SCHLUESSEL  # noqa: E402
pruefe(all(len(__import__("base64").b64decode(v)) == 32 for v in SCHLUESSEL.values()),
       "lizenz_schluessel.py enthält nur öffentliche Schlüssel (32 Byte)")

print(f"\n{len(fehler)} Fehler" if fehler else "\nAlle Lizenz-Prüfungen bestanden.")
sys.exit(1 if fehler else 0)
