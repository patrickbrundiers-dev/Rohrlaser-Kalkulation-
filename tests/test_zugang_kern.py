"""Zugangssystem Paket A (programm/rohrlaser/zugang_*.py): Kern, Entwickler-Ausweis, Prüfstelle. Fälle Z1–Z45.

Deckt aus dem Auftrag (Abschnitt 10) die Teile von Test 4 (Entwicklerzugang), 5 (Berechtigungen) und 7 (Sicherheit)
ab, die ohne Oberfläche und Datenbank prüfbar sind; die übrigen folgen mit den Paketen B–F.
Jeder Lauf erzeugt eigene Test-Schlüssel (Schlüssel-ID K9); der echte Lizenzschlüssel kommt nicht vor.
Aufruf: python tests/test_zugang_kern.py
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "werkzeuge"))
PW = "test-passwort-zugang"
os.environ["ROHRLASER_LIZENZ_PASSWORT"] = PW

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

import lizenz_werkzeug as W  # noqa: E402

from rohrlaser import lizenz, passwort  # noqa: E402
from rohrlaser import zugang_authentifizierung as A  # noqa: E402
from rohrlaser import zugang_ausweis as AW  # noqa: E402
from rohrlaser import zugang_berechtigung as B  # noqa: E402
from rohrlaser import zugang_protokoll as P  # noqa: E402
from rohrlaser import zugang_pruefstelle as PS  # noqa: E402
from rohrlaser.zugang_sitzungen import Sitzungen  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="zugang_"))
fehler = []
SCHNELL = dict(n=2 ** 14)          # Tresor im Test schnell (Programm: 2**17)
HEUTE = datetime.date(2026, 11, 27)


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


def wirft(f, *a, **k):
    try:
        f(*a, **k)
    except (lizenz.LizenzFehler, SystemExit, PermissionError, ValueError) as e:
        return str(e) or type(e).__name__
    return ""


privat = Ed25519PrivateKey.generate()
SCH = {"K9": lizenz.oeffentlich_text(privat)}
fremd = Ed25519PrivateKey.generate()


class Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ------------------------------------------------------------------ Passwort-Hash und Regeln
h = A.hash_bilden("Sehr-geheim-123", SCHNELL)
pruefe(h.startswith("scrypt$") and "Sehr-geheim-123" not in h, "Z1 Hash ist scrypt mit Salz, kein Klartext")
pruefe(A.pruefen("Sehr-geheim-123", h) and not A.pruefen("sehr-geheim-123", h), "Z2 richtig/falsch erkannt")
pruefe(A.hash_bilden("Sehr-geheim-123", SCHNELL) != h, "Z3 gleiches Passwort, anderes Salz, anderer Hash")
alt = passwort.hash_bilden("Altes-Passwort-1")
pruefe(A.pruefen("Altes-Passwort-1", alt) and A.braucht_umstellung(alt), "Z4 alter PBKDF2-Hash gilt, wird umgestellt")
pruefe(not A.pruefen("klartext", "klartext") and not A.pruefen("x", ""), "Z5 Klartext und leer werden nie angenommen")
pruefe(not A.pruefen("x", "scrypt$3$8$1$00$00"), "Z6 kaputter/unzulässiger Hash wird abgelehnt")
pruefe(A.passwort_regeln("kurz") and A.passwort_regeln("123456", pin=True) and not A.passwort_regeln("482915", pin=True)
       and A.passwort_regeln("Mueller-12345", name="Mueller") and not A.passwort_regeln("Gute-Laenge-42"),
       "Z7 Regeln für Passwort und PIN")

# ------------------------------------------------------------------ Einmalcode (RFC 6238, Testvektor SHA-1)
G = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"      # "12345678901234567890"
pruefe(A.totp_code(G, 59) == "287082" and A.totp_code(G, 1111111109) == "081804", "Z8 TOTP-Testvektoren RFC 6238")
s = A.totp_pruefen(G, "287082", 59)
pruefe(s == 1 and A.totp_pruefen(G, "287082", 59, zuletzt=s) is None, "Z9 Einmalcode gilt nur einmal")
pruefe(A.totp_pruefen(G, "287082", 59 + 30 * 5) is None, "Z10 alter Einmalcode (2,5 Min.) abgelehnt")

# ------------------------------------------------------------------ Sicherheitsprotokoll
prot = P.Protokoll(tmp / "prot", "INST-1", "PLATZ-1")
prot.schreiben(P.ANMELDUNG_FEHLER, "MU", passwort="Geheim!", details=dict(token="abc", pin="1234", ok="sichtbar"))
text = (tmp / "prot" / P.DATEI).read_text("utf-8")
pruefe("Geheim!" not in text and "abc" not in text and "1234" not in text and "sichtbar" in text,
       "Z11 Protokoll enthält keine Passwörter, PINs oder Tokens")
e = prot.lesen()[-1]
pruefe(e["installation"] == "INST-1" and e["arbeitsplatz"] == "PLATZ-1" and e["benutzer"] == "MU" and e["zeit"],
       "Z12 Eintrag hat Benutzer, Zeit, Installation, Arbeitsplatz, Aktion")

# ------------------------------------------------------------------ Entwickler-Ausweis
BIS = HEUTE + datetime.timedelta(days=700)
EPW = "Entwickler-Passwort-2026!"
d = AW.erstellen("Patrick", EPW, privat, "K9", "EW-2026-0001", BIS, heute=HEUTE, kdf=SCHNELL)
pruefe(EPW not in json.dumps(d) and d["inhalt"]["rechner"] == [], "Z13 Ausweis ohne Passwort und ohne Rechner-ID")
daten, inhalt = AW.pruefen(d, SCH, HEUTE, umgebung="produktiv", installation="INST-1")
pruefe(inhalt["ausweis_id"] == "EW-2026-0001", "Z14 gültiger Ausweis wird angenommen")
pruefe(AW.tresor_oeffnen(d, EPW) is not None and AW.tresor_oeffnen(d, EPW + "x") is None, "Z15 Tresor nur mit Passwort")
f = json.loads(json.dumps(d))
f["inhalt"]["gueltig_bis"] = "2099-01-01"
pruefe("Signatur" in wirft(AW.pruefen, f, SCH, HEUTE), "Z16 verlängerter Ausweis: Signatur ungültig")
pruefe("Signatur" in wirft(AW.pruefen, AW.erstellen("X", EPW, fremd, "K9", "EW-2026-0099", BIS, heute=HEUTE,
                                                     kdf=SCHNELL), SCH, HEUTE),
       "Z17 Ausweis mit fremdem Schlüssel (Kundenadmin) wird abgelehnt")
pruefe("abgelaufen" in wirft(AW.pruefen, d, SCH, BIS + datetime.timedelta(days=1)), "Z18 abgelaufener Ausweis")
pruefe("gesperrt" in wirft(AW.pruefen, d, SCH, HEUTE, gesperrt=["EW-2026-0001"]), "Z19 gesperrter Ausweis")
nur_test = AW.erstellen("Patrick", EPW, privat, "K9", "EW-2026-0002", BIS, ("test",), ("INST-T",), HEUTE, kdf=SCHNELL)
pruefe("Umgebung" in wirft(AW.pruefen, nur_test, SCH, HEUTE, umgebung="produktiv")
       and "Installation" in wirft(AW.pruefen, nur_test, SCH, HEUTE, umgebung="test", installation="INST-1")
       and not wirft(AW.pruefen, nur_test, SCH, HEUTE, umgebung="test", installation="INST-T"),
       "Z20 Umgebungen und Installationen werden geprüft")
anderer = AW.erstellen("Patrick", EPW, privat, "K9", "EW-2026-0003", BIS, heute=HEUTE, kdf=SCHNELL)
mix = dict(d, tresor=anderer["tresor"])
pruefe(AW.tresor_oeffnen(mix, EPW) is None, "Z21 Tresor eines anderen Ausweises passt nicht")
pruefe("Laufzeit" in wirft(AW.erstellen, "P", EPW, privat, "K9", "EW-1", HEUTE + datetime.timedelta(days=5000),
                           heute=HEUTE), "Z22 zu lange Laufzeit wird nicht ausgestellt")
pruefe("12 Zeichen" in wirft(AW.erstellen, "P", "kurz", privat, "K9", "EW-1", BIS, heute=HEUTE),
       "Z23 Entwickler-Passwort mindestens 12 Zeichen")
neu = AW.passwort_aendern(d, EPW, "Neues-Entwickler-PW-27", kdf=SCHNELL)
pruefe(AW.stand(neu) == 2 and AW.tresor_oeffnen(neu, "Neues-Entwickler-PW-27") is not None
       and AW.tresor_oeffnen(neu, EPW) is None and not wirft(AW.pruefen, neu, SCH, HEUTE),
       "Z24 Passwort ändern: neuer Tresor, Signatur bleibt gültig")

# Anmeldenachweis (wie gegenüber einem Server)
seed = AW.tresor_oeffnen(d, EPW)
jetzt = datetime.datetime(2026, 11, 27, 12, 0, tzinfo=datetime.timezone.utc)
a = AW.anfrage_signieren(seed, inhalt, "INST-1", jetzt)
gesehen = set()
pruefe(AW.anfrage_pruefen(a, inhalt, "INST-1", jetzt, gesehen), "Z25 Anmeldeanfrage wird anerkannt")
pruefe("schon benutzt" in wirft(AW.anfrage_pruefen, a, inhalt, "INST-1", jetzt, gesehen),
       "Z26 Wiederholte Anfrage (Replay) abgelehnt")
pruefe("anderen Installation" in wirft(AW.anfrage_pruefen, AW.anfrage_signieren(seed, inhalt, "INST-1", jetzt), inhalt,
                                      "INST-2", jetzt), "Z27 Anfrage für eine andere Installation abgelehnt")
pruefe("zu alt" in wirft(AW.anfrage_pruefen, AW.anfrage_signieren(seed, inhalt, "INST-1", jetzt), inhalt, "INST-1",
                         jetzt + datetime.timedelta(minutes=5)), "Z28 alte Anfrage abgelehnt")
b = AW.anfrage_signieren(seed, inhalt, "INST-1", jetzt)
b["nonce"] = "manipuliert"
pruefe("nicht echt" in wirft(AW.anfrage_pruefen, b, inhalt, "INST-1", jetzt), "Z29 veränderte Anfrage abgelehnt")

# Hinterlegen und Stick
inst = tmp / "inst"
AW.hinterlegen(inst, d, "INST-1", G, HEUTE, SCH)
h_ = AW.hinterlegt(inst)
pruefe(h_["ausweis"]["inhalt"]["ausweis_id"] == "EW-2026-0001" and h_["totp"] == G and EPW not in json.dumps(h_),
       "Z30 Ausweis für eine Installation hinterlegt (ohne Passwort)")
pruefe("Installation" in wirft(AW.hinterlegen, inst, nur_test, "INST-1", "", HEUTE, SCH),
       "Z30b Ausweis lässt sich nur an einer erlaubten Installation hinterlegen")
stick = tmp / "stick"
(stick / "NexTube").mkdir(parents=True)
(stick / "NexTube" / AW.DATEI).write_text(json.dumps(d), "utf-8")
pruefe(AW.auf_stick_suchen([tmp / "leer", stick]) == stick / "NexTube" / AW.DATEI, "Z31 Ausweis auf dem Stick gefunden")

# ------------------------------------------------------------------ Rollen und Rechte
r_kalk = B.wirksame_rechte([B.KALK_STANDARD])
pruefe("angebot.erstellen" in r_kalk and "preise.ek_sehen" not in r_kalk and "benutzer.verwalten" not in r_kalk,
       "Z32 Kalkulator Standard: Angebote ja, EK und Verwaltung nein")
pruefe(B.wirksame_rechte([B.MITARBEITER], plus=["qs.bearbeiten"]) == {"qs.bearbeiten"}
       and "angebot.loeschen" not in B.wirksame_rechte([B.KALK_PRO], minus=["angebot.loeschen"]),
       "Z33 Einzelrechte geben und entziehen")
pruefe(not any(x.schreibt for x in B.RECHTE if x.name in B.wirksame_rechte([B.NUR_LESEN])),
       "Z34 Nur Lesen enthält kein schreibendes Recht")
admin_r = B.wirksame_rechte([B.ADMIN])
pruefe("Entwickler" in B.vergabe_fehler(B.wirksame_rechte([B.SYSTEMADMIN]), False, [B.ENTWICKLER])
       and "Entwickler" in B.vergabe_fehler(frozenset(), True, [B.ENTWICKLER])
       and B.vergabe_fehler(admin_r, False, [B.SYSTEMADMIN])
       and not B.vergabe_fehler(admin_r, False, [B.KALK_PRO])
       and B.vergabe_fehler(r_kalk, False, [B.KALK_STANDARD])
       and B.vergabe_fehler(admin_r, False, plus=["entwickler.dashboard"]),
       "Z35 Keine Rechte-Ausweitung: Entwickler nie vergebbar, nur eigene Rechte vergebbar")
pruefe(B.ENTWICKLER not in B.wirksame_rechte([B.ENTWICKLER]) and not B.wirksame_rechte([B.ENTWICKLER]),
       "Z36 Rolle Entwickler in einem Konto bringt keine Rechte")

# ------------------------------------------------------------------ Sitzungen
uhr = Uhr()
sz = Sitzungen(uhr)
s1 = sz.anlegen("u1", "MU", rechte=["angebot.sehen"])
tok = s1.token
pruefe(len(tok) == 64 and sz.pruefen(tok) is s1, "Z37 Sitzung mit zufälligem Token")
uhr.t += 31 * 60
pruefe("Inaktivität" in wirft(sz.pruefen) and s1.gesperrt and not s1.beendet, "Z38 nach 30 Min. Inaktivität gesperrt")
sz.entsperren()
sz.beenden()
s2 = sz.anlegen("u2", "SC")
pruefe("nicht mehr gültig" in wirft(sz.pruefen, tok) and sz.pruefen(s2.token) is s2,
       "Z39 beendetes Token gilt nie wieder (Wiederverwendung)")

# ------------------------------------------------------------------ Prüfstelle
uhr = Uhr()
lesemodus = [False]
erlaubt_module = {"auftrag"}
ps = PS.Pruefstelle(P.Protokoll(tmp / "ps", "INST-1", "PLATZ-1"), Sitzungen(uhr), "INST-1", "produktiv", "PLATZ-1",
                    modul_erlaubt=lambda m: m in erlaubt_module, nur_lesen=lambda: lesemodus[0])
pruefe(not ps.darf("angebot.sehen") and "Nicht angemeldet" in wirft(ps.verlangen, "angebot.sehen"),
       "Z40 ohne Anmeldung kein Zugriff")
konto = dict(id="u1", kuerzel="MU", name="Müller", hash=A.hash_bilden("Mueller-Passwort-1", SCHNELL),
             status="aktiv", rollen=[B.KALK_STANDARD])
sp = A.Sperre([tmp / "sperre_mu.json"], uhr)
falsch = [ps.benutzer_anmelden(konto, "falsch", sperre=sp) for _ in range(5)]
pruefe(all(not r.ok for r in falsch) and falsch[0].text.startswith(PS.FALSCH) and falsch[-1].warten == 60
       and ps.benutzer_anmelden(None, "x").text.startswith(PS.FALSCH)
       and "warten" in ps.benutzer_anmelden(konto, "Mueller-Passwort-1", sperre=sp).text,
       "Z41 Fehlversuche: gleiche Meldung für Name/Passwort, Sperre ab dem 5. Versuch")
uhr.t += 61
r = ps.benutzer_anmelden(konto, "Mueller-Passwort-1", sperre=sp)
pruefe(r.ok and ps.darf("angebot.erstellen") and not ps.darf("preise.ek_sehen") and not ps.darf("benutzer.verwalten")
       and "Keine Berechtigung" in wirft(ps.verlangen, "stamm.faktoren")
       and any(e["aktion"] == P.ZUGRIFF_VERWEIGERT for e in ps.protokoll.lesen()),
       "Z42 Rechte nach Rolle; verweigerter Zugriff wird protokolliert (Fachlogik-Prüfung)")
pruefe(not ps.darf("baugruppen.verwenden") and "Modul" in ps.grund("baugruppen.verwenden")
       and ps.darf("auftrag.sehen") and not ps.darf("auftrag.bearbeiten"),
       "Z43 Lizenz-Ebene: Modul ohne Lizenz gesperrt; lizenziertes Modul nur mit Recht")
lesemodus[0] = True
pruefe(not ps.darf("angebot.erstellen") and ps.darf("angebot.sehen"), "Z44 Lesemodus: Ansehen ja, Ändern nein")
lesemodus[0] = False
gesperrt_k = dict(konto, status="gesperrt")
pruefe(not ps.benutzer_anmelden(gesperrt_k, "Mueller-Passwort-1").ok, "Z45 gesperrtes Konto meldet sich nicht an")
k2 = dict(konto, hash=alt, kuerzel="AL")
r2 = ps.benutzer_anmelden(k2, "Altes-Passwort-1")
pruefe(r2.ok and r2.neuer_hash.startswith("scrypt$"), "Z46 alter Hash: Anmeldung ok, neuer scrypt-Hash geliefert")
k3 = dict(konto, kuerzel="TO", totp=G)
pruefe(ps.benutzer_anmelden(k3, "Mueller-Passwort-1").zweiter_faktor_fehlt
       and ps.benutzer_anmelden(k3, "Mueller-Passwort-1", totp_code=A.totp_code(G, 5000), jetzt=5000).ok,
       "Z47 zweiter Faktor für Benutzer")
ps.abmelden(wechsel=True)
pruefe(not ps.darf("angebot.sehen") and ps.protokoll.lesen()[-1]["aktion"] == P.BENUTZERWECHSEL,
       "Z48 Benutzerwechsel beendet die Sitzung")

# Entwickler an zwei Arbeitsplätzen und zwei Installationen, ohne Platzlizenz
spe = A.Sperre([tmp / "sperre_ew.json"], uhr)
for platz, inst_id in (("PLATZ-1", "INST-1"), ("PLATZ-2", "INST-1"), ("SERVER-A", "INST-SA"), ("SERVER-B", "INST-SB")):
    pe = PS.Pruefstelle(P.Protokoll(tmp / platz, inst_id, platz), Sitzungen(uhr), inst_id, "produktiv", platz,
                        modul_erlaubt=lambda m: False, nur_lesen=lambda: True)
    re_ = pe.entwickler_anmelden(d, EPW, von_stick=True, sperre=spe, schluessel=SCH, heute=HEUTE)
    ok = (re_.ok and pe.darf("baugruppen.verwenden") and pe.darf("lizenz.verwalten") and pe.darf("entwickler.dashboard")
          and pe.darf("kuenftiges.recht") and pe.sitzung.minuten == 15)
    pruefe(ok, f"Z49 Entwickler an {platz} ({inst_id}): Vollzugriff trotz fehlender Lizenz/Lesemodus")
pe = PS.Pruefstelle(P.Protokoll(tmp / "x", "INST-1", "P1"), Sitzungen(uhr), "INST-1", "produktiv", "P1")
pruefe(not pe.entwickler_anmelden(d, "falsch-falsch-falsch", True, schluessel=SCH, heute=HEUTE).ok
       and not pe.darf("angebot.sehen"), "Z50 Entwickler mit falschem Passwort: kein Zugriff")
sp2 = A.Sperre([tmp / "sp3.json"], uhr)
pe.entwickler_anmelden(neu, "Neues-Entwickler-PW-27", True, sperre=sp2, schluessel=SCH, heute=HEUTE)
pruefe("altes Passwort" in pe.entwickler_anmelden(d, EPW, True, sperre=sp2, schluessel=SCH, heute=HEUTE).text,
       "Z52 nach Passwortwechsel: alte Kopie mit altem Passwort abgelehnt")
pruefe(pe.entwickler_anmelden(d, EPW, False, totp_geheimnis=G, schluessel=SCH, heute=HEUTE).zweiter_faktor_fehlt
       and pe.entwickler_anmelden(d, EPW, False, totp_code=A.totp_code(G, 7000), totp_geheimnis=G, schluessel=SCH,
                                  heute=HEUTE, jetzt=7000).ok,
       "Z53 hinterlegter Ausweis: Einmalcode wird verlangt")
pruefe(any(e["aktion"] == P.ENTWICKLER_ZUGRIFF for e in pe.protokoll.lesen())
       and EPW not in (tmp / "x" / P.DATEI).read_text("utf-8"), "Z54 Entwicklerzugriff protokolliert, ohne Passwort")
pruefe(not pe.entwickler_anmelden(nur_test, EPW, True, schluessel=SCH, heute=HEUTE).ok,
       "Z55 Ausweis nur für Test gilt nicht an der Produktiv-Installation")
pruefe(PS.AKTUELL is None and PS.darf("x") and PS.verlangen("x"), "Z56 ohne Prüfstelle bleibt alles wie bisher")

# ------------------------------------------------------------------ Lizenz-Werkzeug
WZ = tmp / "werkzeug"
WZ.mkdir()
W.schluessel_erzeugen(WZ, "K7", PW.encode(), ausgabe=False)
datei = W.ausweis_ausstellen(WZ, "Patrick", EPW, 24, None, None, heute=HEUTE, pw=PW.encode(), kdf=SCHNELL)
wz_sch = {"K7": lizenz.oeffentlich_text(W.privat_laden(WZ, "K7", PW.encode()))}
dd, ii = AW.pruefen(Path(datei), wz_sch, HEUTE)
z = [z for z in W.register_lesen(WZ) if z["lizenz_id"] == ii["ausweis_id"]]
pruefe(ii["ausweis_id"] == "EW-2026-0001" and z and z[0]["art"] == AW.ART and AW.tresor_oeffnen(dd, EPW) is not None,
       "Z58 Lizenz-Werkzeug stellt einen gültigen Ausweis aus und trägt ihn ins Register")
datei2 = W.ausweis_ausstellen(WZ, "Patrick", EPW, 24, None, None, "EW-2026-0001", heute=HEUTE, pw=PW.encode(),
                              kdf=SCHNELL)
pruefe(AW.pruefen(Path(datei2), wz_sch, HEUTE)[1]["ausweis_id"] == "EW-2026-0002"
       and list(Path(datei2).parent.glob("*_vor_EW-2026-0002*")), "Z59 Ersatz-Ausweis, alte Datei bleibt erhalten")
pruefe(W.main(["--ordner", str(WZ), "pruefen", str(datei2)]) == 0, "Z60 pruefen erkennt den Ausweis")

shutil.rmtree(tmp, ignore_errors=True)
print()
if fehler:
    print(f"{len(fehler)} FEHLER")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
