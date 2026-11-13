"""Hauptadmin-Lizenz ohne Rechner-ID mit Passwort beim Start (programm/rohrlaser/hauptadmin.py, Patrick 12.11.2026).

H1 Hauptadmin ohne Rechner-ID · H2 auf mehreren Rechnern · H3 Passwort richtig/falsch · H4 Passwort ändern (alte Kopie
gilt danach nicht mehr) · H5 mehrere Fehlversuche (Sperre, Verdopplung, zweiter Zähler, Notfallcode) · H6 Kundenlizenz
mit Rechner-ID unverändert · H7 keine Admin-Rechte ohne Anmeldung · H8 Manipulation der Dateien · H9 Start ohne gültige
Lizenz · H10 Anmeldefenster, Lizenzdialog, Menü Hauptadmin · H11 Rohrlaser Auslastung · H12 Lizenz-Werkzeug ·
H13 Einstellungen sichern/wiederherstellen/zurücksetzen.

Jeder Lauf erzeugt eigene Testschlüssel; kein echtes Passwort, kein echter Schlüssel.
Aufruf: python tests/test_hauptadmin.py
"""
import copy
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "werkzeuge"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from rohrlaser import einstellungen_sicherung as ES  # noqa: E402
from rohrlaser import hauptadmin as H  # noqa: E402
from rohrlaser import lizenz  # noqa: E402

# H0 Rohrlaser Auslastung nutzt hauptadmin + anmelde_fenster: keine Module der Kalkulation (auch nicht in Funktionen
# nachgeladen), sonst bricht programm/auslastung.spec ab (Auslastung-Release 2.9.1)
import ast  # noqa: E402

ERLAUBT = {"lizenz", "lizenz_schluessel", "passwort", "klartext", "stil", "hauptadmin", "NAME"}
for modul in ("hauptadmin.py", "anmelde_fenster.py"):
    baum = ast.parse((Path(__file__).resolve().parent.parent / "programm" / "rohrlaser" / modul).read_text("utf-8"))
    for k in ast.walk(baum):
        if isinstance(k, ast.ImportFrom) and k.level == 1:
            namen = {k.module} if k.module else {n.name for n in k.names}
            assert namen <= ERLAUBT, (modul, namen)
print("OK     H0 Hauptadmin-Anmeldung ohne Module der Kalkulation (Programm Rohrlaser Auslastung)")

tmp = Path(tempfile.mkdtemp(prefix="hauptadmin_"))
fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


PRIVAT = Ed25519PrivateKey.generate()
FREMD = Ed25519PrivateKey.generate()
SCHL = {"T1": lizenz.oeffentlich_text(PRIVAT)}
KDF = dict(n=2 ** 14)               # schneller als die Vorgabe, gleiche Verfahren
PW = "Rohr-Laser-2026!"             # Testpasswort (kein echtes)
RECHNER_A = lizenz.rechner_id("rechner-a")
RECHNER_B = lizenz.rechner_id("rechner-b")
HEUTE = datetime.date.today()           # Stufe 2 (Durchsetzung) ist in den Stellen fest eingeschaltet


class Uhr:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def datei(passwort=PW, privat=PRIVAT, lid="HA-2026-0001", **mehr):
    return H.erstellen("Patrick", passwort, privat, "T1", lid, datetime.date(2026, 11, 12), kdf=KDF, **mehr)


def platz(name, rechner, daten=None, db=None, kunde=None):
    """Rechner mit eigenem Lizenzordner; daten: Hauptadmin-Datei, kunde: Kundenlizenz (aktiv.lizenz)."""
    o = tmp / name / "Lizenz"
    o.mkdir(parents=True, exist_ok=True)
    if daten is not None:
        (o / H.DATEI).write_text(json.dumps(daten), encoding="utf-8")
    if kunde is not None:
        lizenz.lizenz_laden(o, kunde, HEUTE, rechner, SCHL)
    s = lizenz.LizenzStelle(o, db, SCHL, rechner, durchsetzung=True)
    s.sperre_orte = [o / H.ANMELDUNG, tmp / name / "profil" / H.ANMELDUNG]
    return s


def kundenlizenz(rechner, art="benutzer", lid="L-2026-0007"):
    inhalt = dict(lizenz_id=lid, art=art, inhaber="Kunde", firma="Muster GmbH", ausgestellt=(HEUTE - datetime.timedelta(days=10)).isoformat(),
                  gueltig_ab=(HEUTE - datetime.timedelta(days=10)).isoformat(),
                  gueltig_bis=(HEUTE + datetime.timedelta(days=120)).isoformat(), rechner=[rechner], funktionen=["alle"],
                  test=False, schluessel_id="T1", hinweis="")
    return dict(format=1, inhalt=inhalt, signatur=lizenz.signieren(inhalt, PRIVAT))


D = datei()

# ------------------------------------------------------------------ H1 ohne Rechner-ID
daten, inhalt = H.pruefen(D, SCHL)
pruefe(inhalt["art"] == "hauptadmin" and inhalt["rechner"] == [] and "admin_passwort" not in inhalt
       and "gueltig_bis" not in inhalt, "H1 Hauptadmin-Lizenz: keine Rechner-ID, unbefristet, kein Passwort-Hash")
pruefe(PW not in json.dumps(D) and "pbkdf2" not in json.dumps(D),
       "H1 Passwort steht weder als Text noch als Hash in der Datei")
pruefe(D["tresor"]["kdf"] == "scrypt" and len(bytes.fromhex(D["tresor"]["salz"])) == 16,
       "H1 Tresor: scrypt mit eigenem Salz (16 Byte), AES-GCM")
pruefe(datei()["tresor"]["salz"] != D["tresor"]["salz"] and datei()["inhalt"]["admin_schluessel"]
       != D["inhalt"]["admin_schluessel"], "H1 jede Ausstellung: neues Salz, neuer Admin-Schlüssel")
try:
    lizenz.pruefen(D, SCHL)
    pruefe(False, "H1 Kundenlizenz-Prüfung lehnt die Hauptadmin-Datei ab")
except lizenz.LizenzFehler as e:
    pruefe("Unbekannte Lizenzart" in str(e), f"H1 Kundenlizenz-Prüfung lehnt die Hauptadmin-Datei ab ({e})")

a = platz("a", RECHNER_A, D)
pruefe(a.hauptadmin_noetig(), "H1 Rechner A mit Hauptadmin-Datei: Anmeldung nötig")
z = a.pruefen(HEUTE)
pruefe(not z.admin and not z.hauptadmin and z.stufe == "lesemodus",
       "H1 vor der Anmeldung: keine Admin-Rechte (ohne Kundenlizenz Lesemodus)")
e = a.hauptadmin_anmelden(PW, HEUTE)
pruefe(e.ok and a.hauptadmin_ok and a.zustand.hauptadmin and a.zustand.admin and not a.zustand.nur_lesen,
       "H1 nach der Anmeldung: Hauptadmin, voller Zugriff, ohne Rechner-ID")
pruefe(a.zustand.darf("premium_irgendwas") and a.zustand.darf(), "H1 Hauptadmin darf alle (auch künftige) Funktionen")
pruefe("Hauptadmin-Lizenz HA-2026-0001" in a.text() and "ohne Rechner-ID" in a.text(), f"H1 Text: {a.text()}")
pruefe(not a.hauptadmin_noetig(), "H1 angemeldet: keine zweite Abfrage")

# ------------------------------------------------------------------ H2 mehrere Rechner
for name, rid in (("b", RECHNER_B), ("c", lizenz.rechner_id("rechner-c")), ("d", "")):
    s = platz(name, rid, D)
    pruefe(s.hauptadmin_anmelden(PW, HEUTE).ok and s.zustand.hauptadmin,
           f"H2 dieselbe Datei auf Rechner {name} ({rid or 'ohne lesbare Rechner-ID'}): Anmeldung geht")
viele = [platz(f"viel{i}", lizenz.rechner_id(f"pc-{i}"), D) for i in range(6)]
pruefe(all(s.hauptadmin_anmelden(PW, HEUTE).ok for s in viele), "H2 keine Gerätebegrenzung (6 weitere Rechner)")

# ------------------------------------------------------------------ H3 Passwort richtig / falsch
s = platz("h3", RECHNER_A, D)
e = s.hauptadmin_anmelden("falsch-falsch", HEUTE)
pruefe(not e.ok and not s.hauptadmin_ok and "falsch" in e.text and e.rest == 4,
       f"H3 falsches Passwort: abgelehnt ({e.text})")
pruefe(not s.hauptadmin_anmelden("", HEUTE).ok, "H3 leeres Passwort: abgelehnt")
pruefe(not s.hauptadmin_anmelden(PW.upper(), HEUTE).ok, "H3 Groß-/Kleinschreibung zählt")
pruefe(s.hauptadmin_anmelden(PW, HEUTE).ok, "H3 richtiges Passwort: angemeldet")
pruefe(s.sperre().fehlversuche() == 0, "H3 Erfolg setzt den Fehlversuch-Zähler zurück")

# ------------------------------------------------------------------ H4 Passwort ändern
NEU = "Neues-Passwort-77"
s = platz("h4", RECHNER_A, copy.deepcopy(D))
s.hauptadmin_anmelden(PW, HEUTE)
try:
    s.hauptadmin_passwort_aendern("falsch-falsch", NEU)
    pruefe(False, "H4 falsches bisheriges Passwort: nicht geändert")
except H.HauptadminFehler:
    pruefe(True, "H4 falsches bisheriges Passwort: nicht geändert")
for schwach in ("kurz", "aaaaaaaaaaaa", PW):
    try:
        s.hauptadmin_passwort_aendern(PW, schwach)
        pruefe(False, f"H4 zu schwaches/gleiches Passwort abgelehnt ({schwach})")
    except H.HauptadminFehler as e:
        pruefe(True, f"H4 zu schwaches/gleiches Passwort abgelehnt ({e})")
neu_daten = s.hauptadmin_passwort_aendern(PW, NEU)
gespeichert = json.loads(s.hauptadmin_pfad().read_text(encoding="utf-8"))
pruefe(H.stand(gespeichert) == 2 and gespeichert["signatur"] == D["signatur"] and gespeichert["inhalt"] == D["inhalt"],
       "H4 neuer Tresor (Stand 2), Signatur und Inhalt unverändert")
s2 = platz("h4", RECHNER_A)
s2.sperre_orte = s.sperre_orte
pruefe(not s2.hauptadmin_anmelden(PW, HEUTE).ok, "H4 altes Passwort gilt nicht mehr")
pruefe(s2.hauptadmin_anmelden(NEU, HEUTE).ok, "H4 neues Passwort gilt")
s2.hauptadmin_pfad().write_text(json.dumps(D), encoding="utf-8")      # ältere Kopie zurückgelegt
s3 = platz("h4", RECHNER_A)
s3.sperre_orte = s.sperre_orte
daten_, _, grund = s3.hauptadmin_lesen()
pruefe(daten_ is None and "Ältere Kopie" in grund and not s3.hauptadmin_noetig(),
       f"H4 ältere Kopie (altes Passwort) nimmt der Rechner nicht mehr an ({grund[:45]} …)")
pruefe(not s3.hauptadmin_anmelden(PW, HEUTE).ok, "H4 ältere Kopie: auch mit altem Passwort keine Anmeldung")
try:
    s3.hauptadmin_laden(json.dumps(D), PW)
    pruefe(False, "H4 ältere Kopie lässt sich nicht wieder laden")
except H.HauptadminFehler:
    pruefe(True, "H4 ältere Kopie lässt sich nicht wieder laden")
anderer = platz("h4b", RECHNER_B)
e = anderer.hauptadmin_laden(json.dumps(neu_daten), NEU)
pruefe(e.ok and anderer.zustand.hauptadmin, "H4 neue Datei auf einem weiteren Rechner geladen (mit neuem Passwort)")

# ------------------------------------------------------------------ H5 mehrere Fehlversuche
uhr = Uhr()
s = platz("h5", RECHNER_A, D)
sp = H.Sperre(s.sperre_orte, uhr)
s.sperre = lambda: sp
for i in range(H.FEHL_FREI - 1):
    e = s.hauptadmin_anmelden(f"falsch-{i:05d}", HEUTE)
pruefe(not e.ok and e.warten == 0 and e.rest == 1, f"H5 4 Fehlversuche: noch ohne Wartezeit ({e.text})")
e = s.hauptadmin_anmelden("falsch-xxxxx", HEUTE)
pruefe(not e.ok and e.warten == H.SPERRE_ERSTE_S, f"H5 5. Fehlversuch: Sperre 1 Minute ({e.text})")
e = s.hauptadmin_anmelden(PW, HEUTE)
pruefe(not e.ok and e.warten > 0 and "warten" in e.text and not s.hauptadmin_ok,
       f"H5 während der Sperre: auch das richtige Passwort abgelehnt ({e.text})")
uhr.t += 61
e = s.hauptadmin_anmelden("falsch-yyyyy", HEUTE)
pruefe(not e.ok and e.warten == 2 * H.SPERRE_ERSTE_S, "H5 nächster Fehlversuch: Sperre verdoppelt (2 Minuten)")
for _ in range(20):
    uhr.t += 4000
    e = s.hauptadmin_anmelden("falsch-zzzzz", HEUTE)
pruefe(e.warten == H.SPERRE_MAX_S, "H5 Sperre höchstens 60 Minuten")
(s.sperre_orte[0]).unlink()                   # Zähler im Lizenzordner gelöscht
pruefe(sp.wartezeit() > 0 and sp.fehlversuche() >= 20, "H5 Zähler im Benutzerprofil gilt weiter (Datei gelöscht)")
notfall = lizenz.notfallcode(RECHNER_A, HEUTE, PRIVAT, "T1")
e = s.hauptadmin_anmelden(notfall, HEUTE)
pruefe(e.ok and e.notfall and s.hauptadmin_notfall and s.zustand.hauptadmin and "Notfallcode" in s.zustand.hinweis,
       "H5 Notfallcode (Lizenz-Werkzeug, für diese Rechner-ID) meldet trotz Sperre an")
try:
    s.hauptadmin_passwort_aendern(PW, NEU)       # Passwort wäre richtig, aber …
    pruefe(True, "H5 nach Notfallcode: Passwort ändern mit dem bisherigen Passwort möglich")
except H.HauptadminFehler as f:
    pruefe("warten" in str(f) or "falsch" in str(f), f"H5 nach Notfallcode: Ändern verlangt das bisherige Passwort ({f})")
fremd_code = lizenz.notfallcode(RECHNER_B, HEUTE, PRIVAT, "T1")
s4 = platz("h5b", RECHNER_A, D)
pruefe(not s4.hauptadmin_anmelden(fremd_code, HEUTE).ok, "H5 Notfallcode für einen anderen Rechner: abgelehnt")
alt_code = lizenz.notfallcode(RECHNER_A, HEUTE - datetime.timedelta(days=3), PRIVAT, "T1")
pruefe(not s4.hauptadmin_anmelden(alt_code, HEUTE).ok, "H5 alter Notfallcode: abgelehnt")

# ------------------------------------------------------------------ H6 Kundenlizenz unverändert
k = platz("h6", RECHNER_A, kunde=kundenlizenz(RECHNER_A))
z = k.pruefen(HEUTE)
pruefe(z.stufe == "gueltig" and not z.admin and not z.hauptadmin and not k.hauptadmin_noetig(),
       "H6 Kundenlizenz mit Rechner-ID: gültig, ohne Admin-Rechte, keine Anmeldung")
pruefe(not k.hauptadmin_anmelden(PW, HEUTE).ok, "H6 Kundenplatz ohne Hauptadmin-Datei: Hauptadmin-Anmeldung geht nicht")
k2 = platz("h6b", RECHNER_B)
try:
    lizenz.lizenz_laden(k2.ordner, kundenlizenz(RECHNER_A), HEUTE, RECHNER_B, SCHL)
    pruefe(False, "H6 Kundenlizenz auf fremdem Rechner: abgelehnt")
except lizenz.LizenzFehler:
    pruefe(True, "H6 Kundenlizenz auf fremdem Rechner: abgelehnt (Rechner-ID-Bindung bleibt)")
beide = platz("h6c", RECHNER_A, D, kunde=kundenlizenz(RECHNER_A))
pruefe(beide.pruefen(HEUTE).stufe == "gueltig" and not beide.zustand.admin, "H6 beide Dateien: vor Anmeldung Kundenlizenz")
beide.hauptadmin_anmelden(PW, HEUTE)
pruefe(beide.zustand.hauptadmin, "H6 beide Dateien: nach Anmeldung Hauptadmin")
beide.hauptadmin_abmelden(HEUTE)
pruefe(beide.zustand.stufe == "gueltig" and not beide.zustand.admin, "H6 abgemeldet: wieder die Kundenlizenz")
adm = lizenz.ermitteln(kundenlizenz(RECHNER_A, art="admin") | {}, HEUTE, RECHNER_A, SCHL, durchsetzung=True)
pruefe(adm.stufe != "admin" or not adm.hauptadmin, "H6 bisherige Admin-Lizenz: kein Hauptadmin")

# ------------------------------------------------------------------ H7 keine Rechteausweitung
from rohrlaser.datenbank import Datenbank  # noqa: E402
db = Datenbank(tmp / "h7" / "rohrlaser.db")
from rohrlaser.passwort import hash_bilden  # noqa: E402
db.einstellung_setzen("passwort", hash_bilden("Mitarbeiter-Passwort"))
s = platz("h7", RECHNER_A, D, db=db, kunde=kundenlizenz(RECHNER_A))
s.pruefen(HEUTE)
pruefe(not s.hauptadmin_anmelden("Mitarbeiter-Passwort", HEUTE).ok,
       "H7 Passwort der Einstellungen (Admin-Schutz) meldet nicht als Hauptadmin an")
pruefe(not s.admin_freigeben("falsch-falsch") and not s.zustand.hauptadmin, "H7 Admin freischalten: kein Hauptadmin")
s.admin_freigeben("Mitarbeiter-Passwort")
pruefe(not s.zustand.hauptadmin, "H7 auch mit Admin-Schutz-Passwort: kein Hauptadmin")
for name, wert in (("hauptadmin", True), ("admin_seiten", []), ("lizenz_info", {"art": "hauptadmin", "stufe": "admin"})):
    db.einstellung_setzen(name, wert)
pruefe(not s.pruefen(HEUTE).hauptadmin and not s.zustand.admin, "H7 manipulierte Einstellungen schalten nichts frei")
(s.ordner / H.ANMELDUNG).write_text(json.dumps({"fehl": 0, "bis": 0, "angemeldet": True, "staende": {}}))
pruefe(not s.pruefen(HEUTE).hauptadmin, "H7 manipulierte anmeldung.json schaltet nichts frei")
s.hauptadmin_anmelden(PW, HEUTE)
pruefe(s.zustand.hauptadmin and s.admin_passwort() and s.passwort_gilt(PW),
       "H7 Hauptadmin-Passwort gilt danach auch für den Admin-Schutz (nur als Hash in den Einstellungen)")
pruefe(PW not in json.dumps(db.einstellung("passwort")), "H7 in den Einstellungen nur der Hash")

# ------------------------------------------------------------------ H8 Manipulation
def manipuliert(text, aendern):
    d = copy.deepcopy(D)
    aendern(d)
    m = platz(f"h8_{len(fehler)}_{abs(hash(text)) % 99999}", RECHNER_A, d)
    ok = m.hauptadmin_anmelden(PW, HEUTE).ok
    pruefe(not ok and not (m.zustand and m.zustand.hauptadmin), f"H8 {text}: nicht angenommen")


manipuliert("Rechner-ID eingetragen", lambda d: d["inhalt"].update(rechner=[RECHNER_A]))
manipuliert("Inhaber geändert", lambda d: d["inhalt"].update(inhaber="Jemand"))
manipuliert("Art in admin geändert", lambda d: d["inhalt"].update(art="admin"))
manipuliert("Signatur entfernt", lambda d: d.pop("signatur"))
fremd = H.erstellen("Patrick", PW, FREMD, "T1", "HA-2026-0001", kdf=KDF)
manipuliert("mit fremdem Schlüssel signiert", lambda d: d.update(fremd))


def eigener_tresor(d):
    """Angreifer baut einen Tresor mit eigenem Passwort und eigenem Schlüssel."""
    neu = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization
    seed = neu.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    d["tresor"] = H.tresor_bilden(seed, PW, d["inhalt"], 99, KDF)


d8 = datei(passwort="Ganz-anderes-PW-1")
m = platz("h8_tresor", RECHNER_A, d8)
eigener_tresor(d8)
(m.hauptadmin_pfad()).write_text(json.dumps(d8), encoding="utf-8")
pruefe(not m.hauptadmin_anmelden(PW, HEUTE).ok, "H8 eigener Tresor (eigenes Passwort, eigener Schlüssel): abgelehnt")
manipuliert("Tresor beschädigt", lambda d: d["tresor"].update(daten=d["tresor"]["daten"][:-8] + "AAAAAAA="))
manipuliert("Tresor fehlt", lambda d: d.pop("tresor"))
manipuliert("Tresor auf schwache Parameter (n=2)", lambda d: d["tresor"].update(n=2))
m = platz("h8_kunde", RECHNER_A)
(m.ordner / lizenz.AKTIV).write_text(json.dumps(D), encoding="utf-8")   # als Kundenlizenz hingelegt
z = m.pruefen(HEUTE)
pruefe(z.stufe == "lesemodus" and not z.admin, "H8 Hauptadmin-Datei als aktiv.lizenz: Lesemodus, keine Rechte")
try:
    lizenz.lizenz_laden(m.ordner, D, HEUTE, RECHNER_A, SCHL)
    pruefe(False, "H8 Hauptadmin-Datei lässt sich nicht als Kundenlizenz laden")
except lizenz.LizenzFehler:
    pruefe(True, "H8 Hauptadmin-Datei lässt sich nicht als Kundenlizenz laden")
gesperrt = platz("h8_sperre", RECHNER_A, D)
(gesperrt.ordner / lizenz.SPERRLISTE).write_text(json.dumps(lizenz.sperrliste_signieren(1, ["HA-2026-0001"], PRIVAT,
                                                                                           "T1")))
daten_, _, grund = gesperrt.hauptadmin_lesen()
pruefe(daten_ is None and "gesperrt" in grund and not gesperrt.hauptadmin_anmelden(PW, HEUTE).ok,
       "H8 Hauptadmin-Lizenz auf der Sperrliste: widerrufen")
ersatz = datei(lid="HA-2026-0002", ersetzt="HA-2026-0001", passwort="Ersatz-Passwort-9")
r = platz("h8_ersatz", RECHNER_A, D)
pruefe(r.hauptadmin_laden(json.dumps(ersatz), "Ersatz-Passwort-9").ok, "H8 Ersatz-Lizenz geladen")
try:
    r.hauptadmin_laden(json.dumps(D), PW)
    pruefe(False, "H8 ersetzte Hauptadmin-Lizenz lässt sich nicht mehr laden")
except H.HauptadminFehler:
    pruefe(True, "H8 ersetzte Hauptadmin-Lizenz lässt sich nicht mehr laden")
v = platz("h8_echt", RECHNER_A, D)
v.veraendert = "rohrlaser.pyd"
pruefe(not v.hauptadmin_noetig() and not v.hauptadmin_anmelden(PW, HEUTE).ok
       and v.pruefen(HEUTE).stufe == "lesemodus", "H8 veränderte Programmdateien: kein Hauptadmin, Lesemodus")

# ------------------------------------------------------------------ H9 Start ohne gültige Lizenz
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser import anmelde_fenster  # noqa: E402

leer = platz("h9", RECHNER_A)
z = leer.pruefen(HEUTE)
pruefe(z.stufe == "lesemodus" and z.nur_lesen and not z.admin, "H9 ohne Lizenz (Stufe 2): Lesemodus, keine Rechte")
pruefe(anmelde_fenster.hauptadmin_beim_start(leer, ausfuehren=lambda d: 1/0), "H9 ohne Hauptadmin-Datei: kein Login")
pruefe(anmelde_fenster.hauptadmin_beim_start(None), "H9 Lizenzprüfung fehlgeschlagen: Start wie bisher")
kaputt = platz("h9b", RECHNER_A, dict(D, signatur="AAAA"))
pruefe(anmelde_fenster.hauptadmin_beim_start(kaputt, ausfuehren=lambda d: 1/0)
       and "nicht angenommen" in kaputt.pruefen(HEUTE).hinweis,
       "H9 ungültige Hauptadmin-Datei: kein Login, Kundenlizenz-Regeln, Hinweis")
s = platz("h9c", RECHNER_A, D)
pruefe(not anmelde_fenster.hauptadmin_beim_start(s, ausfuehren=lambda d: d.reject() or 0),
       "H9 Hauptadmin-Datei, Anmeldung abgebrochen: Programm startet nicht")
pruefe(not anmelde_fenster.hauptadmin_beim_start(s, ausfuehren=lambda d: (d.versuchen("falsch-falsch"), 0)[1]),
       "H9 falsches Passwort, dann Beenden: Programm startet nicht")
pruefe(not anmelde_fenster.hauptadmin_beim_start(s, ausfuehren=lambda d: (_ for _ in ()).throw(RuntimeError("x"))),
       "H9 Fehler in der Anmeldung: Programm startet nicht (nie offen ohne Passwort)")
pruefe(anmelde_fenster.hauptadmin_beim_start(s, ausfuehren=lambda d: d.versuchen(PW)) and s.zustand.hauptadmin,
       "H9 richtiges Passwort: Programm startet als Hauptadmin")

# ------------------------------------------------------------------ H10 Oberfläche
s = platz("h10", RECHNER_A, D)
d = anmelde_fenster.AnmeldeDialog(s)
d.show()
app.processEvents()
pruefe("HA-2026-0001" in d.info.text() and d.anmelden.text() == "Anmelden" and d.beenden.text() == "Beenden",
       "H10 Anmeldefenster: Lizenz, Anmelden und Beenden")
pruefe(d.passwort.echoMode() == d.passwort.EchoMode.Password, "H10 Passwortfeld verdeckt")
pruefe(not d.versuchen("falsch-falsch") and d.fehler.isVisible() and "falsch" in d.fehler.text()
       and d.passwort.text() == "", "H10 falsches Passwort: Meldung, Feld geleert")
for i in range(5):
    d.versuchen(f"falsch-{i:04d}x")
pruefe(d.sperre.isVisible() and "Fehlversuche" in d.sperre.text(), f"H10 Sperre sichtbar ({d.sperre.text()[:50]} …)")
d.close()
s.sperre().erfolg()
d = anmelde_fenster.AnmeldeDialog(s)
pruefe(d.versuchen(PW) and d.result() == 1 and s.hauptadmin_ok, "H10 richtiges Passwort: Fenster schließt, angemeldet")
p = anmelde_fenster.PasswortAendernDialog(s)
pruefe(not p.aendern(PW, "Neu-Passwort-123", "Neu-Passwort-124") and "nicht gleich" in p.fehler.text(),
       "H10 Passwort ändern: Wiederholung muss gleich sein")
pruefe(not p.aendern("falsch-falsch", "Neu-Passwort-123", "Neu-Passwort-123") and "falsch" in p.fehler.text(),
       "H10 Passwort ändern: bisheriges Passwort falsch")
pruefe(p.aendern(PW, "Neu-Passwort-123", "Neu-Passwort-123"), "H10 Passwort ändern: geändert")

from rohrlaser.lizenz_dialog import LizenzDialog, stufe_text  # noqa: E402
ld = LizenzDialog(None, s, stumm=True)
pruefe("Hauptadmin" in ld.status.text() and ld.ha_passwort.isVisibleTo(ld) and ld.ha_export.isVisibleTo(ld),
       "H10 Lizenzdialog: Hauptadmin, Passwort ändern, für weitere Rechner speichern")
ziel = tmp / "export" / "ha.lizenz"
ziel.parent.mkdir()
pruefe(ld.hauptadmin_exportieren(ziel) and H.stand(json.loads(ziel.read_text())) == 2,
       "H10 Datei für weitere Rechner: aktueller Stand")
neu_platz = platz("h10b", RECHNER_B)
ld2 = LizenzDialog(None, neu_platz, stumm=True)
pruefe(not ld2.laden(str(ziel), "falsch-falsch") and not neu_platz.hauptadmin_ok,
       "H10 Lizenzdialog: Hauptadmin-Datei mit falschem Passwort nicht übernommen")
pruefe(ld2.laden(str(ziel), "Neu-Passwort-123") and neu_platz.hauptadmin_ok and neu_platz.hauptadmin_pfad().is_file(),
       "H10 Lizenzdialog: Hauptadmin-Datei mit Passwort übernommen (Drag & Drop/Laden)")
pruefe(stufe_text(neu_platz.zustand).startswith("Hauptadmin"), "H10 Stufe im Lizenzdialog")

from rohrlaser.fenster import Hauptfenster  # noqa: E402
fdb = Datenbank(tmp / "h10f" / "rohrlaser.db")
fs = lizenz.LizenzStelle(lizenz.ordner(tmp / "h10f"), fdb, SCHL, RECHNER_A, durchsetzung=True)
fs.sperre_orte = [tmp / "h10f" / "a.json"]
fs.ordner.mkdir(parents=True, exist_ok=True)
fs.hauptadmin_pfad().write_text(json.dumps(D), encoding="utf-8")
fs.pruefen()
f = Hauptfenster(fdb, stumm=True, lizenz=fs)
pruefe(not f.hauptadmin_menue.menuAction().isVisible(), "H10 Menü Hauptadmin vor der Anmeldung unsichtbar")
fs.hauptadmin_anmelden(PW)
f.lizenz_anwenden()
pruefe(f.hauptadmin_menue.menuAction().isVisible() and f.bereich.admin and f.bereich.offen
       and not fdb.nur_lesen, "H10 angemeldet: Menü Hauptadmin, Admin-Rechte, Einstellungen offen")
from rohrlaser import admin_schutz, hauptadmin_menue  # noqa: E402
pruefe(admin_schutz.ist_haupt(fdb, f.bereich.sitzung), "H10 Hauptadmin darf Admin-Schutz und Rechte ändern")
pruefe(hauptadmin_menue.seite_zeigen(f, "plaetze_seite") is f.plaetze_seite
       and hauptadmin_menue.funktionen_zeigen(f) is not None, "H10 Menü springt zu Rechten und Funktionen")
pruefe(set(f.hauptadmin_aktionen) >= {"Passwort ändern …", "Einstellungen sichern …", "Support-Paket erstellen …",
                                      "Abmelden und beenden"}, "H10 Menü Hauptadmin vollständig")
f.close()

# ------------------------------------------------------------------ H11 Rohrlaser Auslastung
from rl_auslastung import lizenzen  # noqa: E402
kalk = tmp / "h11" / "Kalk" / "Lizenz"
kalk.mkdir(parents=True)
(kalk / H.DATEI).write_text(json.dumps(D), encoding="utf-8")
(kalk / lizenz.AKTIV).write_text("{}", encoding="utf-8")
st = lizenzen.Stelle(tmp / "h11" / "Ausl", SCHL, RECHNER_A, durchsetzung=True, kalkulation=kalk)
st.sperre_orte = [tmp / "h11" / "a.json"]
pruefe(st.hauptadmin_noetig() and st.hauptadmin_ordner() == kalk,
       "H11 Auslastung: Hauptadmin-Datei der Kalkulation erkannt, Anmeldung nötig")
pruefe(st.hauptadmin_anmelden(PW, HEUTE).ok and st.zustand.hauptadmin and not st.zustand.nur_lesen
       and "Hauptadmin" in st.text(), "H11 Auslastung: angemeldet, voller Zugriff")
w = lizenzen.Stelle(tmp / "h11" / "Werkstatt", SCHL, RECHNER_B, durchsetzung=True, kalkulation=None)
pruefe(not w.hauptadmin_noetig() and anmelde_fenster.hauptadmin_beim_start(w, ausfuehren=lambda d: 1/0),
       "H11 Werkstatt-Rechner ohne Hauptadmin-Datei: kein Login, wie bisher")

# ------------------------------------------------------------------ H12 Lizenz-Werkzeug
import lizenz_werkzeug as wz  # noqa: E402
wo = tmp / "werkzeug"
os.environ["ROHRLASER_LIZENZ_PASSWORT"] = "werkzeug-test-pw"
wz.schluessel_erzeugen(wo, "K90", b"werkzeug-test-pw", ausgabe=False)   # nicht K1: den gibt es im Programm
datei_w = wz.hauptadmin_ausstellen(wo, "Patrick", PW, heute=datetime.date(2026, 11, 12), kdf=KDF)
zeile = wz.register_lesen(wo)[-1]
pruefe(datei_w.name.startswith("HA-2026-0001_Hauptadmin") and zeile["art"] == "hauptadmin"
       and zeile["gueltig_bis"] == "unbefristet", f"H12 Werkzeug stellt Hauptadmin-Lizenz aus ({datei_w.name})")
pruefe(wz.pruefen(datei_w, ordner=wo) == 0, "H12 Werkzeug prüft Hauptadmin-Dateien")
datei_w2 = wz.hauptadmin_ausstellen(wo, "Patrick", "Zweites-PW-2026", ersetzt="HA-2026-0001", kdf=KDF,
                                    heute=datetime.date(2026, 11, 12))
pruefe("HA-2026-0002" in datei_w2.name and json.loads(datei_w2.read_text())["inhalt"]["ersetzt"] == "HA-2026-0001",
       "H12 Ersatz-Lizenz (Passwort vergessen/bekannt geworden)")
datei_w3 = wz.verlaengern(wo, "HA-2026-0002", admin_passwort="Drittes-PW-2026", heute=datetime.date(2026, 11, 12))
pruefe("HA-2026-0003" in datei_w3.name and json.loads(datei_w3.read_text())["inhalt"]["ersetzt"] == "HA-2026-0002",
       "H12 Verlängern bei Hauptadmin = Ersatz mit neuem Passwort")
try:
    wz.hauptadmin_ausstellen(wo, "Patrick", "kurz", kdf=KDF)
    pruefe(False, "H12 zu kurzes Passwort abgelehnt")
except SystemExit:
    pruefe(True, "H12 zu kurzes Passwort abgelehnt")
quelle = (WURZEL / "programm" / "rohrlaser" / "hauptadmin.py").read_text(encoding="utf-8")
pruefe(PW not in quelle and "PRIVATE" + " KEY" not in quelle, "H12 kein Passwort, kein privater Schlüssel im Code")

# ------------------------------------------------------------------ H13 Einstellungen
edb = Datenbank(tmp / "h13" / "rohrlaser.db")
edb.einstellung_setzen("gewinn", 0.25)
edb.einstellung_setzen("passwort", "Admin-Schutz-1")
nummer = edb.einstellung("letzte_angebotsnummer")
sich = tmp / "h13" / "einst.json"
n = ES.einstellungen_sichern(edb, sich)
inhalt_s = sich.read_text(encoding="utf-8")
pruefe(n > 100 and '"gewinn": 0.25' in inhalt_s and "passwort" not in json.loads(inhalt_s)["werte"],
       f"H13 Einstellungen gesichert ({n}, ohne Passwort)")
n, _ = ES.einstellungen_zuruecksetzen(edb)
pruefe(edb.einstellung("gewinn") == 0.10 and edb.einstellung("passwort") and n >= 1
       and edb.einstellung("letzte_angebotsnummer") == nummer, "H13 zurückgesetzt (Passwort und Nummer bleiben)")
pruefe(any("vor_einstellungen" in p.name for p in (tmp / "h13" / "Sicherung").glob("*.db")),
       "H13 vorher Datensicherung")
n, _ = ES.einstellungen_wiederherstellen(edb, sich)
pruefe(edb.einstellung("gewinn") == 0.25, "H13 wiederhergestellt")
(tmp / "h13" / "falsch.json").write_text('{"werte": {}}')
try:
    ES.einstellungen_wiederherstellen(edb, tmp / "h13" / "falsch.json")
    pruefe(False, "H13 fremde Datei abgelehnt")
except H.HauptadminFehler:
    pruefe(True, "H13 fremde Datei abgelehnt")

for w in QApplication.topLevelWidgets():      # Fenster vor dem Ende geordnet löschen (sonst Absturz beim Beenden)
    w.deleteLater()
app.processEvents()
admin_schutz.SITZUNG = None
print()
if fehler:
    print(f"{len(fehler)} FEHLER")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
