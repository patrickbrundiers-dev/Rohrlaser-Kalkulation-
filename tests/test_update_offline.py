"""Updates hinter Firewall und offline (Auftrag Patrick 19.11.2026): Update-Ordner (Netzwerkordner, USB-Stick),
Update-Datei (.rlupdate), Quellen-Auswahl, Freigabe und Rückmeldung, Proxy/Zertifikat, Diagnose, vorige Version
wiederherstellen, Schema-Prüfung. Alles mit eigenen Testschlüsseln (Signaturpflicht wie im echten Programm).

Fehlerszenarien: manipuliertes Paket, unsignierte oder fremd signierte Liste, ältere Version (Downgrade), fremde
Dateien und Pfade in der Update-Datei, Ordner nicht erreichbar, Proxy mit Passwort, Netz gesperrt.

Aufruf: python tests/test_update_offline.py
"""
import json
import shutil
import ssl
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from rohrlaser import lizenz, update, update_diagnose, update_netz, update_quellen, update_verteilen  # noqa: E402

PRIVAT, FREMD = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
update.update_schluessel = lambda: {"U1": lizenz.oeffentlich_text(PRIVAT)}
tmp = Path(tempfile.mkdtemp(prefix="upd_offline_"))


def ok(text):
    print("OK    ", text)


def fehler(f, *a, text=None, art=update.UpdateFehler, **k):
    try:
        f(*a, **k)
    except art as e:
        assert text is None or text in str(e), e
        return e
    raise AssertionError(f"{art.__name__} erwartet: {getattr(f, '__name__', f)}")


def programm(ordner, kennung):
    ordner = Path(ordner)
    for rel, inhalt in {"Rohrlaser-Angebotskalkulation.exe": b"MZ" + kennung + bytes(200_000),
                        "_internal/gross.dll": bytes(range(256)) * 6000 + kennung,
                        "_internal/klein.pyd": b"pyd" + kennung,
                        "Bedienungsanleitung.pdf": b"%PDF" + bytes(10_000)}.items():
        (ordner / rel).parent.mkdir(parents=True, exist_ok=True)
        (ordner / rel).write_bytes(inhalt)
    (ordner / "Daten").mkdir(exist_ok=True)
    (ordner / "Daten" / "rohrlaser.db").write_bytes(b"DATEN")
    return ordner


def build(ordner, ziel, stand, schluessel=PRIVAT, schema=95):
    """Wie der Build: Dateiliste, Pakete, Signatur."""
    liste = update.erstellen(ordner, ziel, stand, aenderung=f"Stand {stand}", schema=schema)
    sig = update.signatur_erstellen((Path(ziel) / update.DATEILISTE).read_bytes(), schluessel, "U1")
    (Path(ziel) / update.SIGNATUR).write_text(json.dumps(sig), encoding="ascii")
    return liste


def installieren(von_build, ordner):
    """Programmordner wie aus dem ZIP: Dateien + signierte Dateiliste."""
    shutil.copyfile(Path(von_build) / update.DATEILISTE, Path(ordner) / update.DATEILISTE)
    shutil.copyfile(Path(von_build) / update.SIGNATUR, Path(ordner) / update.SIGNATUR)


def stimmt(ordner, liste):
    for rel, d in liste["dateien"].items():
        assert update.pruefsumme(Path(ordner) / rel) == d["sha256"], rel


# Stand 10 installiert, Stand 11 gebaut (wie im Release update-dateien)
inst = programm(tmp / "inst", b"-10")
build(programm(tmp / "q10", b"-10"), tmp / "b10", 10)
installieren(tmp / "b10", inst)
l11 = build(programm(tmp / "q11", b"-11"), tmp / "b11", 11)
assert l11["schema"] == 95
internet = update_quellen.Quelle(str(tmp / "b11" / update.DATEILISTE), "Testserver")    # Pfad statt https

# --- 1. Update-Ordner bereitstellen (Admin) und daraus aktualisieren -----------------------------------------------
netz = tmp / "netz" / "Updates"
gemeldet = []
l = update_verteilen.bereitstellen(internet, netz, fortschritt=lambda n, g: gemeldet.append((n, g)))
k = netz / update_verteilen.UNTERORDNER
assert l["stand"] == 11 and (k / update.DATEILISTE).read_bytes() == (tmp / "b11" / update.DATEILISTE).read_bytes()
assert (k / update.SIGNATUR).is_file() and all((k / p).is_file() for p in l11["pakete"])
assert gemeldet and gemeldet[-1][0] == gemeldet[-1][1] == sum(p["groesse"] for p in l11["pakete"].values())
assert not list(k.glob("*.teil"))
ordner = update_quellen.OrdnerQuelle(netz)
assert ordner.adresse() == str(k / update.DATEILISTE)
online, plan = update.aktualisieren(inst, ordner.adresse())
stimmt(inst, l11)
assert update.lokale_liste(inst)["stand"] == 11 and (inst / "Daten" / "rohrlaser.db").read_bytes() == b"DATEN"
assert (inst / update.SIGNATUR).read_bytes() == (tmp / "b11" / update.SIGNATUR).read_bytes(), "Signatur abgelegt"
ok("Update-Ordner: Admin stellt bereit, Arbeitsplatz aktualisiert ohne Internet (signiert, nur Geändertes)")

# Ordner direkt gewählt (USB-Stick von Hand befüllt: Update.json direkt im Ordner)
usb = tmp / "usb"
shutil.copytree(tmp / "b11", usb)
assert update_verteilen.liste_im_ordner(usb) == usb / update.DATEILISTE
assert update_verteilen.liste_im_ordner(tmp / "gibtsnicht") is None
fehler(update_quellen.OrdnerQuelle(tmp / "gibtsnicht").liste, text="kein Update")
ok("USB-Stick/Ordner: Update.json direkt oder im Unterordner Kalkulation, fehlender Ordner klar gemeldet")

# --- 2. Vorige Version wiederherstellen (ohne Internet) ------------------------------------------------------------
update.aufraeumen(inst)
vorige = update.vorige_version(inst)
assert vorige["stand"] == 10 and vorige.signatur, "vorige Dateiliste samt Signatur gemerkt"
aus = update.zurueck_vorbereiten(inst)
assert sorted(aus["plan"]["neu"]) == ["Rohrlaser-Angebotskalkulation.exe", "_internal/gross.dll", "_internal/klein.pyd"]
update.einspielen(inst, aus["online"], aus["plan"], aus["neu_ordner"])
stimmt(inst, update.lokale_liste(tmp / "b10"))
assert update.lokale_liste(inst)["stand"] == 10
assert (inst / update.SIGNATUR).read_bytes() == (tmp / "b10" / update.SIGNATUR).read_bytes()
update.aufraeumen(inst)
assert update.vorige_version(inst)["stand"] == 11, "nach dem Zurücksetzen lässt sich wieder vorwärts"
# unvollständige vorige Version: klare Meldung, nichts angefasst
(inst / update.VORIGE / "_internal" / "klein.pyd").write_bytes(b"kaputt")
fehler(update.zurueck_vorbereiten, inst, text="nicht vollständig")
stimmt(inst, update.lokale_liste(tmp / "b10"))
update.verwerfen(inst)
ok("Vorige Version: Wiederherstellungspunkt nach jedem Update, zurück und wieder vor, Prüfsummen geprüft")

# --- 3. Update-Datei (.rlupdate) -----------------------------------------------------------------------------------
datei = update_verteilen.datei_erstellen(k, tmp / "Rohrlaser-Update")
assert datei.name == "Rohrlaser-Update.rlupdate"
with zipfile.ZipFile(datei) as z:
    namen = set(z.namelist())
assert namen == {update.DATEILISTE, update.SIGNATUR, *l11["pakete"]}, namen
q = update_quellen.DateiQuelle(datei, inst / update.ARBEITSORDNER / "import")
liste = q.liste()
assert liste["stand"] == 11 and not list((inst / update.ARBEITSORDNER / "import").glob("*.zip")), "erst Liste"
plan = update.planen(inst, liste, update.lokale_liste(inst))
q.vorbereiten(liste, plan)
neu = update.laden(inst, q.adresse(), liste, plan)
update.einspielen(inst, liste, plan, neu)
stimmt(inst, l11)
ok("Update-Datei: erstellt, geprüft, nur gebrauchte Pakete ausgepackt, eingespielt")

# Bereitstellen aus einer Update-Datei in einen leeren Ordner (USB-Stick für einen Rechner ohne Netzwerk)
stick = tmp / "stick"
update_verteilen.bereitstellen(update_quellen.DateiQuelle(datei, tmp / "arbeit"), stick)
assert update.online_liste(str(update_verteilen.liste_im_ordner(stick)))["stand"] == 11
ok("Update-Datei → Update-Ordner (USB-Stick)")

# Manipulierte Update-Dateien
def boese_datei(name, eintraege):
    p = tmp / name
    with zipfile.ZipFile(p, "w") as z:
        for n, d in eintraege.items():
            z.writestr(n, d)
    return p


echt_liste = (k / update.DATEILISTE).read_bytes()
echt_sig = (k / update.SIGNATUR).read_bytes()
for name, inhalt, text in (
        ("pfad.rlupdate", {update.DATEILISTE: echt_liste, "../boese.exe": b"x"}, "unerwarteter Inhalt"),
        ("fremd.rlupdate", {update.DATEILISTE: echt_liste, "Daten/rohrlaser.db": b"x"}, "unerwarteter Inhalt"),
        ("ohne.rlupdate", {update.SIGNATUR: echt_sig}, "keine Dateiliste"),
        ("kein_zip.rlupdate", None, "nicht als Update-Datei")):
    p = boese_datei(name, inhalt) if inhalt is not None else tmp / name
    if inhalt is None:
        p.write_bytes(b"kein zip")
    fehler(update_verteilen.datei_pruefen, p, text=text)
# unsigniert bzw. fremd signiert -> Signaturfehler, nichts eingespielt
fremd = update.signatur_erstellen(echt_liste, FREMD, "U1")
for name, eintraege in (("unsigniert.rlupdate", {update.DATEILISTE: echt_liste}),
                        ("fremdsig.rlupdate", {update.DATEILISTE: echt_liste, update.SIGNATUR: json.dumps(fremd)})):
    qq = update_quellen.DateiQuelle(boese_datei(name, eintraege), tmp / ("a_" + name))
    fehler(qq.liste)
# Liste verändert (anderer Stand), Signatur alt -> abgelehnt
veraendert = json.loads(echt_liste)
veraendert["stand"] = 99
qq = update_quellen.DateiQuelle(boese_datei("veraendert.rlupdate", {update.DATEILISTE: json.dumps(veraendert),
                                                                    update.SIGNATUR: echt_sig}), tmp / "a_ver")
fehler(qq.liste, text="signiert")
ok("Update-Datei: Pfade, fremde Dateien, fehlende Liste, unsigniert, fremd signiert, verändert abgelehnt")

# Manipuliertes Paket im Update-Ordner: Prüfsumme schlägt an, Programm bleibt
inst2 = programm(tmp / "inst2", b"-10")
installieren(tmp / "b10", inst2)
kaputt = tmp / "kaputt"
shutil.copytree(k, kaputt)
paket = l11["dateien"]["_internal/gross.dll"]["paket"]
(kaputt / paket).write_bytes(b"PK manipuliert")
fehler(update.aktualisieren, inst2, str(kaputt / update.DATEILISTE))
assert update.lokale_liste(inst2)["stand"] == 10
stimmt(inst2, update.lokale_liste(tmp / "b10"))
ok("Manipuliertes Paket im Ordner: abgelehnt, installierte Version unverändert")

# --- 4. Downgrade-Schutz ------------------------------------------------------------------------------------------
assert not update.neuer(update.online_liste(str(tmp / "b10" / update.DATEILISTE)), update.lokale_liste(inst))
fehler(update_verteilen.bereitstellen, update_quellen.Quelle(str(tmp / "b10" / update.DATEILISTE)), netz,
       text="neuerer Stand")
assert update.lokale_liste(k)["stand"] == 11, "Ordner nicht auf ältere Version zurückgesetzt"
# neuerer Stand ersetzt, alte Pakete der vorigen Liste bleiben einen Stand, unbenutzte fliegen raus
l12 = build(programm(tmp / "q12", b"-12"), tmp / "b12", 12)
(k / ("d-" + "0" * 40 + ".zip")).write_bytes(b"alt")
update_verteilen.bereitstellen(update_quellen.Quelle(str(tmp / "b12" / update.DATEILISTE)), netz)
assert update.lokale_liste(k)["stand"] == 12 and not (k / ("d-" + "0" * 40 + ".zip")).exists()
assert all((k / p).is_file() for p in set(l11["pakete"]) | set(l12["pakete"]))
ok("Downgrade-Schutz: ältere Version nie angeboten, Ordner nie zurückgesetzt; Pakete aufgeräumt")

# --- 5. Schema-Verträglichkeit -------------------------------------------------------------------------------------
assert update.schema_pruefen(dict(stand=12, schema=95), 95) is None
assert update.schema_pruefen(dict(stand=12), 99) is None, "ältere Listen ohne Angabe: keine Sperre"
assert "Schema 90" in update.schema_pruefen(dict(stand=12, version="0.9.1", schema=90), 95)
ok("Schema-Prüfung: Version mit älterem Datenbank-Schema wird nicht eingespielt")

# --- 6. Quellen, Einstellungen, Freigabe ---------------------------------------------------------------------------
class Db:
    def __init__(self, pfad):
        self.werte, self.pfad = {}, Path(pfad)

    def einstellung(self, n):
        return self.werte.get(n)

    def einstellung_setzen(self, n, w):
        self.werte[n] = w


db = Db(tmp / "daten" / "rohrlaser.db")
assert [x.art for x in update_quellen.quellen(db)] == ["internet"], "ohne Ordner: nur Internet (wie bisher)"
db.werte["teilen_ordner"] = str(tmp / "netz")
db.werte["benutzer_kuerzel"] = "PB"
assert update_quellen.update_ordner(db) == tmp / "netz" / "Updates", "Vorgabe: Updates im gemeinsamen Ordner"
assert [x.art for x in update_quellen.quellen(db)] == ["ordner", "internet"]
update_quellen.speichern(db, quelle=update_quellen.ORDNER)
assert [x.art for x in update_quellen.quellen(db)] == ["ordner"]
update_quellen.speichern(db, quelle=update_quellen.INTERNET)
assert [x.art for x in update_quellen.quellen(db)] == ["internet"]
update_quellen.speichern(db, quelle=update_quellen.AUTOMATISCH)
update_verteilen.freigabe_schreiben(netz, stand=12, pflicht=True, pflicht_ab="2026-11-20", hinweis="Bis Freitag",
                                    wartung="Fr ab 16 Uhr", nur_ordner=True, von="PB")
f = update_verteilen.freigabe_lesen(netz)
assert f["pflicht"] and f["nur_ordner"] and f["hinweis"] == "Bis Freitag" and f["stand"] == 12
assert [x.art for x in update_quellen.quellen(db)] == ["ordner"], "Admin: nur aus dem Ordner"
import datetime  # noqa: E402
assert update_verteilen.pflicht_faellig(f, datetime.date(2026, 11, 20))
assert not update_verteilen.pflicht_faellig(f, datetime.date(2026, 11, 19))
(k / update_verteilen.FREIGABE).write_text("kaputt", encoding="utf-8")
assert update_verteilen.freigabe_lesen(netz) == {}, "kaputte Freigabe zählt nicht"
fehler(update_quellen.speichern, db, quelle="irgendwas", art=ValueError)
ok("Quellen: automatisch (Ordner vor Internet), nur Ordner, nur Internet, Admin-Vorgabe nur aus dem Ordner")

# Suche über mehrere Quellen: höchster Stand gewinnt, bei Gleichstand der Ordner; Fehler je Quelle
q_ordner = update_quellen.OrdnerQuelle(netz)
q_alt = update_quellen.Quelle(str(tmp / "b11" / update.DATEILISTE), "Internet alt")
q_weg = update_quellen.Quelle(str(tmp / "weg" / update.DATEILISTE), "weg")
erg = update_quellen.suchen([q_weg, q_alt, q_ordner])
assert erg["beste"][0] is q_ordner and erg["beste"][1]["stand"] == 12
assert erg["ergebnisse"][0][2] and erg["ergebnisse"][1][1]["stand"] == 11
erg = update_quellen.suchen([q_ordner, update_quellen.Quelle(str(k / update.DATEILISTE), "gleich")])
assert erg["beste"][0] is q_ordner, "gleicher Stand: erste Quelle (Ordner)"
assert update_quellen.suchen([q_weg])["beste"] is None
ok("Suche: höchster gültiger Stand, Ordner bei Gleichstand, Fehler je Quelle")

# --- 7. Verlauf und Rückmeldung ------------------------------------------------------------------------------------
vp = update_quellen.verlauf_pfad(db)
update_quellen.verlauf_schreiben(vp, art="geladen", ergebnis="ok", nach=12)
update_quellen.verlauf_schreiben(vp, art="eingespielt", ergebnis="ok", von=11, nach=12, quelle="Update-Ordner")
update_quellen.verlauf_schreiben(vp, art="eingespielt", ergebnis="fehler", fehler="Proxy http://max:geheim@p:8080")
v = update_quellen.verlauf_lesen(vp)
assert [e["art"] for e in v] == ["eingespielt", "eingespielt", "geladen"] and "geheim" not in json.dumps(v)
assert update_quellen.letzte_erfolgreiche(vp)["nach"] == 12
for i in range(update_quellen.VERLAUF_MAX + 5):
    update_quellen.verlauf_schreiben(vp, art="später", nach=i)
assert len(update_quellen.verlauf_lesen(vp)) == update_quellen.VERLAUF_MAX
assert update_verteilen.rueckmelden(netz, dict(kuerzel="PB", version="0.9.410", stand=12, ergebnis="ok"), platz="PC-1")
assert update_verteilen.rueckmelden(netz, dict(kuerzel="AB", version="0.9.409", stand=11, ergebnis="ok"), platz="PC-2")
assert not update_verteilen.rueckmelden(None, {})
p = update_verteilen.plaetze(netz)
assert {x["platz"] for x in p} == {"PC-1", "PC-2"}
assert [x["platz"] for x in update_verteilen.veraltete(p, 12)] == ["PC-2"]
ok("Verlauf (ohne Zugangsdaten, begrenzt) und Rückmeldung je Arbeitsplatz mit Erkennung veralteter Plätze")

# --- 8. Proxy und Zertifikat ---------------------------------------------------------------------------------------
assert update_netz.proxy_pruefen("") == "system" and update_netz.proxy_pruefen("aus") == "aus"
assert update_netz.proxy_pruefen("http://proxy.firma.local:8080/") == "proxy.firma.local:8080"
fehler(update_netz.proxy_pruefen, "max:geheim@proxy:8080", art=update_netz.NetzFehler, text="nie gespeichert")
fehler(update_netz.proxy_pruefen, "proxy", art=update_netz.NetzFehler)
fehler(update_netz.proxy_pruefen, "proxy:99999", art=update_netz.NetzFehler)
update_netz.setzen("proxy.firma.local:3128")
assert update_netz.proxies() == {"https": "http://proxy.firma.local:3128", "http": "http://proxy.firma.local:3128"}
assert "fest eingetragen" in update.systemproxy()
update_netz.setzen("aus")
assert update_netz.proxies() == {} and "abgeschaltet" in update_netz.text()
fehler(update_netz.setzen, "system", str(tmp / "fehlt.pem"), art=update_netz.NetzFehler)
assert update_netz.einstellung()["proxy"] == "aus", "ungültige Werte ändern nichts"
pem = tmp / "firma.pem"
pem.write_text("kein Zertifikat", encoding="ascii")
update_netz.setzen("system", str(pem))
fehler(update_netz.kontext, art=update_netz.NetzFehler, text="lässt sich nicht lesen")
update_netz.setzen()
k_tls = update_netz.kontext()
assert k_tls.verify_mode == ssl.CERT_REQUIRED and k_tls.check_hostname, "Zertifikatsprüfung bleibt immer an"
db.werte["update_proxy"] = "kaputt"
assert update_quellen.netz_anwenden(db) and update_netz.einstellung()["proxy"] == "system"
del db.werte["update_proxy"]
assert update_netz.ohne_zugang("http://max:geheim@p:8080") == "http://p:8080"
ok("Proxy: Windows, aus, fest; keine Passwörter; Firmenzertifikat zusätzlich, Prüfung nie aus")

# --- 9. Diagnose ---------------------------------------------------------------------------------------------------
def dns_weg(host):
    raise OSError("Name or service not known")


def tcp_weg(host, port):
    raise OSError("Verbindung abgelehnt")


def tls_firma(host):
    raise ssl.SSLCertVerificationError(1, "certificate verify failed: self-signed certificate in chain")


class Http407(Exception):
    code = 407


def abruf_407(adresse):
    raise Http407("HTTP Error 407: Proxy Authentication Required")


update_netz.setzen("aus")        # ohne Proxy (die Testumgebung kann HTTPS_PROXY gesetzt haben)
befunde = update_diagnose.pruefen(inst, None, [update_quellen.OrdnerQuelle(netz), update_quellen.InternetQuelle()],
                                  aufloesen=dns_weg, verbinden=tcp_weg, tls=tls_firma, abruf=abruf_407,
                                  platz=50 << 20)
namen = {b["name"]: b for b in befunde}
assert namen["Schreibrecht Programmordner"]["stufe"] == "ok"
assert namen["Freier Speicherplatz"]["stufe"] == "warnung"
assert namen["DNS github.com"]["stufe"] == "fehler"
assert namen["Verbindung github.com:443"]["stufe"] == "fehler" and "443" in namen["Verbindung github.com:443"]["tipp"]
assert namen["Zertifikat"]["stufe"] == "fehler" and "Firmenzertifikat" in namen["Zertifikat"]["tipp"]
assert namen["Abruf Dateiliste"]["stufe"] == "fehler" and "Anmeldung" in namen["Abruf Dateiliste"]["tipp"]
assert any(b["gruppe"] == "Update-Ordner" and b["stufe"] == "ok" for b in befunde)
assert update_diagnose.zusammenfassung(befunde) == "fehler"
update_netz.setzen("max-proxy.firma.local:8080")
bericht = update_diagnose.bericht(befunde)
assert "release-assets.githubusercontent.com" in bericht and "Port 443" in bericht and "geheim" not in bericht
gut = update_diagnose.pruefen(inst, None, [update_quellen.InternetQuelle()], aufloesen=lambda h: ["140.82.121.4"],
                              verbinden=lambda h, p: True, tls=lambda h: "Sectigo",
                              abruf=lambda a: (200, "application/octet-stream", b"{}"), platz=5 << 30)
assert all(b["stufe"] in ("ok", "info") for b in gut), [b for b in gut if b["stufe"] not in ("ok", "info")]
assert any(b["name"] == "Verbindung max-proxy.firma.local:8080" for b in gut), "mit Proxy: Verbindung zum Proxy"
sperr = update_diagnose.pruefen(None, None, [update_quellen.InternetQuelle()], aufloesen=lambda h: ["1.2.3.4"],
                                verbinden=lambda h, p: True, tls=lambda h: "X",
                                abruf=lambda a: (200, "text/html", b"<html>gesperrt"))
assert any(b["name"] == "Abruf Dateiliste" and "Sperrseite" in b["text"] for b in sperr)
update_netz.setzen()
ok("Diagnose: DNS, Port 443, Firmenzertifikat, Proxy-Anmeldung, Sperrseite, Platz; Bericht ohne Zugangsdaten")

shutil.rmtree(tmp, ignore_errors=True)
print("OK: Offline-Update, Update-Ordner, Update-Datei, Quellen, Freigabe, Proxy, Diagnose, vorige Version")
