"""Lizenz-Werkzeug für den Verkauf (Absicherungsplan Phase 8, Variante A): Status je Lizenz, Erinnerung vor Ablauf,
Kundenübersicht, Verlängern, Sperrliste hochladen (GitHub nachgebaut, kein Netz) und das Fenster dazu.
Jeder Lauf erzeugt eigene Testschlüssel; der echte Schlüssel kommt in keinem Test vor.

Aufruf: python tests/test_lizenz_werkzeug.py
"""
import datetime
import io
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "werkzeuge"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import lizenz_werkzeug as wz  # noqa: E402
from rohrlaser import lizenz  # noqa: E402


def ok(text):
    print("OK    ", text)


PW = b"test-passwort-123"
tmp = Path(tempfile.mkdtemp(prefix="lizenz_werkzeug_"))
ordner = tmp / "lizenz"
oeffentlich = wz.schluessel_erzeugen(ordner, "K1", PW, ausgabe=False)
SCHLUESSEL = {"K1": oeffentlich}
H = datetime.date(2026, 10, 24)
T = datetime.timedelta

a = wz.ausstellen(ordner, "benutzer", "Anna", "Muster GmbH", H + T(days=10), ["RL-AAAA-AAAA-AAAA-AAAA"], heute=H, pw=PW)
b = wz.ausstellen(ordner, "benutzer", "Ben", "Muster GmbH", H + T(days=200), ["RL-BBBB-BBBB-BBBB-BBBB"], heute=H, pw=PW)
c = wz.ausstellen(ordner, "test", "Carla", "Probe AG", H - T(days=5), [], heute=H - T(days=40), pw=PW)
d = wz.ausstellen(ordner, "benutzer", "Dora", "Alt KG", H - T(days=90), ["RL-DDDD-DDDD-DDDD-DDDD"], heute=H - T(days=200),
                  pw=PW)
ADMIN_PW = "admin-geheim-1"
for art, apw, text in (("admin", "", "mindestens"), ("admin", "kurz", "mindestens"), ("benutzer", ADMIN_PW, "Nur")):
    try:
        wz.ausstellen(ordner, art, "X", "", None if art == "admin" else H + T(days=5), ["RL-PPPP-PPPP-PPPP-PPPP"],
                      heute=H, pw=PW, admin_passwort=apw)
        raise AssertionError("Fehler erwartet")
    except SystemExit as e:
        assert text in str(e), e
adm = wz.ausstellen(ordner, "admin", "Patrick", "", None, ["RL-PPPP-PPPP-PPPP-PPPP"], heute=H, pw=PW,
                    admin_passwort=ADMIN_PW)
ai = lizenz.pruefen(lizenz.lesen(adm), SCHLUESSEL)
from rohrlaser import passwort  # noqa: E402
assert passwort.ist_hash(ai["admin_passwort"]) and passwort.pruefen(ADMIN_PW, ai["admin_passwort"])
assert ADMIN_PW not in adm.read_text(encoding="utf-8")
ok("Admin-Lizenz: Admin-Passwort Pflicht (mind. 10 Zeichen), nur als Hash in der Lizenz, nicht bei Benutzerlizenz")
zeilen = wz.register_lesen(ordner)
nach_id = {z["inhaber"]: z for z in zeilen}

# Status je Lizenz
assert wz.status(nach_id["Anna"], H) == ("laeuft_ab", 10)
assert wz.status(nach_id["Ben"], H) == ("gueltig", 200)
assert wz.status(nach_id["Carla"], H) == ("abgelaufen", 5)
assert wz.status(nach_id["Patrick"], H) == ("unbefristet", None)
assert wz.status_text(nach_id["Anna"], H) == "läuft in 10 Tagen ab"
assert wz.status_text(nach_id["Carla"], H) == "abgelaufen seit 5 Tagen"
assert wz.status_text(dict(nach_id["Anna"], gueltig_bis=H.isoformat()), H) == "läuft heute ab"
ok("Status: läuft ab, gültig, abgelaufen, unbefristet")

# Erinnerung: bald ablaufend und kürzlich abgelaufen, nicht Admin, nicht lange abgelaufen, nicht gesperrt
f = wz.faellig(zeilen, H)
assert [z["inhaber"] for z, _, _ in f] == ["Carla", "Anna"], f
assert [st for _, st, _ in f] == ["abgelaufen", "laeuft_ab"]
assert wz.faellig(zeilen, H, tage=5) == [f[0]]
ok("Erinnerung: Anna (läuft in 10 Tagen ab), Carla (seit 5 Tagen abgelaufen); Dora zu lange her, Admin nie")

# Kundenübersicht
k = {x["kunde"]: x for x in wz.kunden(zeilen, H)}
assert k["Muster GmbH"]["aktiv"] == 2 and k["Muster GmbH"]["rechner"] == 2
assert k["Muster GmbH"]["naechster_ablauf"] == (H + T(days=10)).isoformat()
assert k["Probe AG"]["aktiv"] == 0 and k["Alt KG"]["gesamt"] == 1
assert k["Patrick"]["aktiv"] == 1 and k["Patrick"]["naechster_ablauf"] == ""
ok("Kunden: aktive Lizenzen, Rechner, nächster Ablauf je Firma")

# Verlängern: im Anschluss, gleiche Angaben, die Erinnerung verschwindet
assert wz.verlaengerung_bis(nach_id["Anna"], H) == wz.monate_spaeter(H + T(days=11), lizenz.STANDARD_MONATE)
assert wz.verlaengerung_bis(nach_id["Carla"], H) == H + T(days=lizenz.TEST_TAGE - 1)       # ab heute
neu = wz.verlaengern(ordner, nach_id["Anna"]["lizenz_id"], heute=H, pw=PW)
inhalt = lizenz.pruefen(lizenz.lesen(neu), SCHLUESSEL)
assert inhalt["inhaber"] == "Anna" and inhalt["firma"] == "Muster GmbH"
assert inhalt["rechner"] == ["RL-AAAA-AAAA-AAAA-AAAA"] and inhalt["art"] == "benutzer"
assert inhalt["hinweis"] == f"Verlängerung von {nach_id['Anna']['lizenz_id']}"
assert inhalt["gueltig_bis"] == wz.monate_spaeter(H + T(days=11), lizenz.STANDARD_MONATE).isoformat()
zeilen = wz.register_lesen(ordner)
assert [z["inhaber"] for z, _, _ in wz.faellig(zeilen, H)] == ["Carla"]
neu_c = wz.verlaengern(ordner, nach_id["Carla"]["lizenz_id"], heute=H, pw=PW)
assert lizenz.pruefen(lizenz.lesen(neu_c), SCHLUESSEL)["rechner"] == []          # beliebiger Rechner bleibt
admin_id = next(z["lizenz_id"] for z in zeilen if z["art"] == "admin")
for lid, text in ((admin_id, "mindestens"), ("L-1999-0001", "nicht im Register")):
    try:
        wz.verlaengern(ordner, lid, heute=H, pw=PW)
        raise AssertionError("Fehler erwartet")
    except SystemExit as e:
        assert text in str(e), e
ersatz = lizenz.pruefen(lizenz.lesen(wz.verlaengern(ordner, admin_id, heute=H, pw=PW, admin_passwort="ganz-neu-2026")),
                        SCHLUESSEL)
assert ersatz["art"] == "admin" and ersatz["gueltig_bis"] is None and ersatz["rechner"] == ["RL-PPPP-PPPP-PPPP-PPPP"]
assert ersatz["hinweis"] == f"Ersatz für {admin_id}" and passwort.pruefen("ganz-neu-2026", ersatz["admin_passwort"])
assert not passwort.pruefen(ADMIN_PW, ersatz["admin_passwort"])
ok("Verlängern: neue Lizenz im Anschluss mit denselben Angaben, Erinnerung erledigt, unbekannt abgelehnt, "
   "Admin = neu ausstellen mit neuem Passwort")

# Notfallcode (Admin-Passwort vergessen)
code = wz.notfallcode(ordner, "rl-pppp-pppp-pppp-pppp", PW, heute=H)
assert lizenz.notfallcode_gueltig(code, "RL-PPPP-PPPP-PPPP-PPPP", H, SCHLUESSEL)
assert lizenz.notfallcode_gueltig(code, "RL-PPPP-PPPP-PPPP-PPPP", H + T(days=1), SCHLUESSEL)
assert not lizenz.notfallcode_gueltig(code, "RL-PPPP-PPPP-PPPP-PPPP", H + T(days=2), SCHLUESSEL)
assert not lizenz.notfallcode_gueltig(code, "RL-AAAA-AAAA-AAAA-AAAA", H, SCHLUESSEL)
try:
    wz.notfallcode(ordner, "keine-id", PW)
    raise AssertionError("Fehler erwartet")
except SystemExit:
    pass
ok("Notfallcode: gilt für den Rechner heute und morgen, nicht übermorgen, nicht für andere Rechner")

# Sperren + Sperrliste hochladen (GitHub nachgebaut)
wz.sperren(ordner, [nach_id["Dora"]["lizenz_id"]], PW)
try:
    wz.verlaengern(ordner, nach_id["Dora"]["lizenz_id"], heute=H, pw=PW)
    raise AssertionError("gesperrte Lizenz verlängert")
except SystemExit as e:
    assert "gesperrt" in str(e)


class Antwort(io.BytesIO):
    def __init__(self, status, daten=b""):
        super().__init__(daten)
        self.status = status


class GitHub:
    def __init__(self, token="richtig", vorhanden=True, upload_status=201, download_kaputt=False):
        self.token, self.upload_status, self.download_kaputt = token, upload_status, download_kaputt
        self.assets = {7: b"alt"} if vorhanden else {}
        self.aufrufe = []

    def __call__(self, anfrage, timeout=30):
        url, methode = anfrage.full_url, anfrage.get_method()
        auth = anfrage.get_header("Authorization")
        self.aufrufe.append((methode, url, auth))
        if url.startswith("https://github.com/"):               # anonymer Download wie im Programm
            assert auth is None, "Token beim anonymen Download"
            if not self.assets:
                raise urllib.error.HTTPError(url, 404, "nicht da", {}, io.BytesIO())
            daten = list(self.assets.values())[-1]
            return Antwort(200, daten[:-3] if self.download_kaputt else daten)
        if auth != f"Bearer {self.token}":
            raise urllib.error.HTTPError(url, 401, "Bad credentials", {}, io.BytesIO())
        if methode == "GET" and url.endswith("/releases/tags/update-dateien"):
            return Antwort(200, json.dumps(dict(id=99, assets=[dict(id=i, name=wz.SPERRLISTE)
                                                               for i in self.assets])).encode())
        if methode == "DELETE":
            self.assets.pop(int(url.rsplit("/", 1)[1]), None)
            return Antwort(204)
        if methode == "POST" and "uploads.github.com" in url and "releases/99/assets?name=Sperrliste.json" in url:
            if self.upload_status >= 400:
                raise urllib.error.HTTPError(url, self.upload_status, "Fehler", {}, io.BytesIO())
            self.assets[8] = anfrage.data
            return Antwort(201, b"{}")
        raise AssertionError(f"unerwarteter Aufruf {methode} {url}")


gh = GitHub()
stand = wz.sperrliste_hochladen(ordner, "richtig", oeffnen=gh, schluessel=SCHLUESSEL)
assert stand == 1 and list(gh.assets) == [8]
online = lizenz.sperrliste_pruefen(gh.assets[8].decode(), SCHLUESSEL)
assert online["gesperrt"] == [nach_id["Dora"]["lizenz_id"]]
assert all("richtig" not in u for _, u, _ in gh.aufrufe)
ok("Sperrliste hochladen: alte ersetzt, ohne Anmeldung nachgeprüft, Token nur im Kopf")

for g, token, text in ((GitHub(), "falsch", "Token ab"), (GitHub(upload_status=403), "richtig", "Hochladen"),
                       (GitHub(download_kaputt=True), "richtig", "Prüfung ohne Anmeldung"),
                       (GitHub(), "", "Kein GitHub-Token")):
    try:
        wz.sperrliste_hochladen(ordner, token, oeffnen=g, schluessel=SCHLUESSEL)
        raise AssertionError(f"Fehler erwartet: {text}")
    except SystemExit as e:
        assert text in str(e), (text, e)
kaputt = tmp / "kaputt"
kaputt.mkdir()
(kaputt / wz.SPERRLISTE).write_text('{"stand": 5, "gesperrt": [], "schluessel_id": "K1", "signatur": "AAAA"}')
try:
    wz.sperrliste_hochladen(kaputt, "richtig", oeffnen=GitHub(), schluessel=SCHLUESSEL)
    raise AssertionError("unsignierte Liste hochgeladen")
except SystemExit as e:
    assert "nicht gültig signiert" in str(e)
ok("Sperrliste hochladen: falscher Token, fehlende Rechte, kaputter Download, unsignierte Liste abgelehnt")

# Befehle auf der Kommandozeile
assert wz.main(["--ordner", str(ordner), "faellig", "--tage", "400"]) == 0
assert wz.main(["--ordner", str(ordner), "kunden"]) == 0
ok("Befehle faellig und kunden")

# Fenster: Status-Spalte, Farben, Erinnerung, Suche, Kundenübersicht
import lizenz_werkzeug_fenster as fw  # noqa: E402

app = fw.QApplication.instance() or fw.QApplication([])
w = fw.Fenster(ordner)
spalte = [t for _, t in fw.ANZEIGE].index("Status")
texte = [w.tabelle.item(i, spalte).text() for i in range(w.tabelle.rowCount())]
assert any("gesperrt" == t for t in texte) and any(t == "unbefristet" for t in texte)
w.filter.setText("probe ag")
sichtbar = [i for i in range(w.tabelle.rowCount()) if not w.tabelle.isRowHidden(i)]
assert sichtbar and all(w.tabelle.item(i, 3).text() == "Probe AG" for i in sichtbar)
w.filter.clear()
assert not any(w.tabelle.isRowHidden(i) for i in range(w.tabelle.rowCount()))
# Erinnerung mit einer bald ablaufenden Lizenz (heute ausgestellt, 3 Tage gültig)
heute = datetime.date.today()
wz.ausstellen(ordner, "benutzer", "Emil", "Bald GmbH", heute + T(days=3), ["RL-EEEE-EEEE-EEEE-EEEE"], pw=PW)
w.neu_laden()
assert not w.erinnerung.isHidden() and "Bald GmbH" in w.erinnerung.text() and "Erinnerung" in w.erinnerung.text()
zeile = next(i for i in range(w.tabelle.rowCount()) if w.tabelle.item(i, 2).text() == "Emil")
assert w.tabelle.item(zeile, 0).background().color().name().upper() == fw.FARBE["laeuft_ab"]
leer = fw.Fenster(tmp / "leer")
assert leer.erinnerung.isHidden() and leer.tabelle.rowCount() == 0
ok("Fenster: Status-Spalte, Farbe, Erinnerung, Suche")
print("Alle Lizenz-Werkzeug-Prüfungen bestanden.")
