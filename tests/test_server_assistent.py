"""Server-Setup: Einrichtungs-Assistent (Patrick 27.11.2026).

- Angaben prüfen (Kürzel, Passwort, Pfade, Uhrzeiten), PowerShell-Text sicher in Anführungszeichen;
- Schritte in der Reihenfolge des IT-Handbuchs, Firewall/Freigabe/NAS/erste Sicherung je nach Angabe;
- echter Durchlauf mit PostgreSQL: Server angelegt, Ablage und zweites Ziel eingetragen, erste Sicherung mit Probe,
  Zugangsdatei und Fingerabdruck, Protokoll ohne Passwörter; Windows-Schritte über eine Attrappe, ein
  misslungener Nicht-Pflicht-Schritt (Firewall) wird Warnung; zweiter Durchlauf auf demselben Ordner geht;
- Pflichtschritt misslingt: Abbruch mit Protokoll;
- Fenster: Seiten, Prüfung je Seite, Zusammenfassung mit allen Schritten.
Als root (initdb verweigert root) oder ohne PostgreSQL-Programme nur die Teile ohne Datenbank.

Aufruf: python tests/test_server_assistent.py
"""
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import pg_lokal, server_assistent as sa, server_betrieb as sb, server_sicherung as ss  # noqa: E402


def ok(text):
    print("OK     " + text)


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


tmp = Path(tempfile.mkdtemp())
PW = "Geheim-PB-123"


def angaben(**w):
    a = sa.Angaben(ordner=str(tmp / "Server"), firma="Muster GmbH", admin="PB", admin_passwort=PW,
                   adressen=["rohrlaser-srv", "127.0.0.1"], port=freier_port(), konto="FIRMA\\pb",
                   konto_passwort="Win-Geheim-1")
    for k, v in w.items():
        setattr(a, k, v)
    return a


# Angaben prüfen
assert sa.pruefen(angaben()) == [], sa.pruefen(angaben())
f = sa.pruefen(angaben(admin="1X", admin_passwort="kurz", firma=" ", adressen=[], ordner="relativ",
                       uhrzeiten="25:00", nas="NAS", freigabe_name="a b"))
for t in ("Server-Ordner", "Administrator: Kürzel", "Administrator: Passwort", "Firmenname", "Mindestens eine",
          "Sicherungszeiten", "Zweites Sicherungsziel", "Name der Freigabe"):
    assert any(x.startswith(t) for x in f), (t, f)
assert sa.pruefen(angaben(ordner=r"D:\RohrlaserServer")) == []
assert sa.ps_text("O'Brien; Remove-Item") == "'O''Brien; Remove-Item'"
v = sa.vorschlag()
assert v.adressen and v.konto and v.uhrzeiten == ss.UHRZEITEN
ok("Angaben prüfen; PowerShell-Text sicher; Vorschlag aus diesem Rechner")

# Schritte
a = angaben(nas=str(tmp / "NAS"))
s = sa.schritte(a)
titel = [x.titel for x in s]
assert titel[0] == "Voraussetzungen prüfen" and titel[1].startswith("Server anlegen") and titel[-1] == "Zustand prüfen"
arten = [x.befehl[0] for x in s if x.art == "server"]
assert arten == ["einrichten", "ablage", "sicherungsziel", "aufgaben", "sichern", "status"], arten
win = [x for x in s if x.art == "windows"]
assert len(win) == 2 and not win[0].pflicht and win[1].pflicht
assert "New-NetFirewallRule" in win[0].befehl[0] and f"-LocalPort {a.port}" in win[0].befehl[0]
assert "New-SmbShare" in win[1].befehl[0] and "'GG-Rohrlaser-Benutzer'" in win[1].befehl[0]
assert "'FIRMA\\pb'" in win[1].befehl[0] and "-CachingMode None" in win[1].befehl[0]
ein = s[1].befehl
assert ein[ein.index("--adresse") + 1:] == ["rohrlaser-srv", "127.0.0.1"] and "--admin" in ein
assert sa.ablage_unc(a) == "\\\\rohrlaser-srv\\Rohrlaser-Ablage"
auf = next(x.befehl for x in s if x.befehl and x.befehl[0] == "aufgaben")
assert auf[auf.index("--uhrzeit") + 1] == ss.UHRZEITEN and auf[auf.index("--konto") + 1] == "FIRMA\\pb"
s2 = sa.schritte(angaben(firewall=False, freigabe=False, erste_sicherung=False, ablage_pfad=r"\\X\Y"))
assert [x.art for x in s2].count("windows") == 0 and [x.befehl[0] for x in s2 if x.art == "server"] == \
    ["einrichten", "ablage", "aufgaben", "status"]
assert all(PW not in " ".join(x.befehl) for x in s), "Passwort nie in der Befehlszeile"
ok("Schritte in Handbuch-Reihenfolge; Firewall/Freigabe/NAS/erste Sicherung je nach Angabe; kein Passwort im Befehl")

# Antwortdatei
d = tmp / "antworten.json"
d.write_text(json.dumps({"ordner": str(tmp / "X"), "admin": "PB", "firma": "F"}), encoding="utf-8")
assert sa.aus_datei(d).admin == "PB"
d.write_text(json.dumps({"unbekannt": 1}), encoding="utf-8")
try:
    sa.aus_datei(d)
    raise AssertionError("unbekannte Angabe angenommen")
except sa.AssistentFehler:
    pass
assert sa.merken(angaben()) is None, "ohne fertige .exe nichts neben das Programm schreiben"
m = sa.merken(angaben(ordner=r"D:\RohrlaserServer", port=5433), programmordner=tmp)
assert m.read_text(encoding="utf-8").splitlines() == [r"D:\RohrlaserServer", "5433"]
iss = (HIER.parent / "programm" / "installer" / "server.iss").read_text(encoding="utf-8")
assert sa.MERKER in iss and "PrivilegesRequired=admin" in iss and "--server-assistent" in iss
assert "OutputBaseFilename=NexTube-Server-Setup" in iss and "--server stoppen" in iss
ok("Antwortdatei: Angaben übernommen, unbekannte abgewiesen; Merker für das Server-Setup (Stoppen vor Update)")

# Fenster
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from rohrlaser import server_assistent_fenster as saf  # noqa: E402

app = QApplication.instance() or QApplication([])
gemeldet = []
QMessageBox.warning = lambda *x: gemeldet.append(x[2])
w = saf.Assistent(angaben())
w.show()
w.next()
w.f_firma.setText("")
assert not w.validateCurrentPage() and "Firmenname" in gemeldet[-1]
w.f_firma.setText("Muster GmbH")
w.next()
w.f_admin.setText("pb")
w.f_pw1.setText(PW)
w.f_pw2.setText(PW + "x")
assert not w.validateCurrentPage() and "verschieden" in gemeldet[-1]
w.f_pw2.setText(PW)
w.next()
w.next()
w.f_kpw.setText("Win-Geheim-1")
w.next()
assert w.currentPage() is w.s_zus, w.currentId()
text = w.zus.toPlainText()
assert "Muster GmbH" in text and "Erste Sicherung" in text and "Firewall" in text and w.a.admin == "PB"
assert PW not in text
ok("Fenster: Seiten, Prüfung je Seite (Firma, Passwort), Zusammenfassung mit allen Schritten, ohne Passwort")

if hasattr(os, "getuid") and os.getuid() == 0:
    print("Durchlauf übersprungen: initdb läuft nicht als root")
    print("alle Prüfungen bestanden")
    sys.exit(0)
try:
    pg_lokal.programme()
except pg_lokal.PgFehlt:
    print("Durchlauf übersprungen: keine PostgreSQL-Programme")
    print("alle Prüfungen bestanden")
    sys.exit(0)

# echter Durchlauf
a = angaben(nas=str(tmp / "NAS"))
ps = []


def windows(befehl):
    ps.append(befehl)
    if "NetFirewallRule" in befehl:
        raise sa.AssistentFehler("Zugriff verweigert")
    return ""


zustaende = []
zeilen = []
try:
    erg = sa.ausfuehren(a, melden=zeilen.append, fortschritt=lambda *x: zustaende.append(x), windows=windows)
    assert erg["gut"], "\n".join(zeilen)
    assert len(ps) == 2 and any(z[3] == "Warnung" and "Firewall" in z[2] for z in zustaende), zustaende
    assert erg["warnungen"] and "Zugriff verweigert" in erg["warnungen"][-1]
    assert Path(erg["zugang"]).exists() and erg["fingerabdruck"]
    zug = json.loads(Path(erg["zugang"]).read_text(encoding="utf-8"))
    assert zug["fingerabdruck"] == erg["fingerabdruck"] and zug["name"] == "Muster GmbH"
    assert zug["adressen"] == ["rohrlaser-srv", "127.0.0.1"] and zug["port"] == a.port
    srv = sb.ZentralerServer(a.ordner, port=a.port)
    with srv.verwalter_verbinden(sb.DATENBANK) as con:
        info = sb.info_lesen(con)
        kuerzel = [b["kuerzel"] for b in sb.benutzer_liste(con)]
    assert info["ablage"] == "\\\\rohrlaser-srv\\Rohrlaser-Ablage" and "PB" in kuerzel, (info, kuerzel)
    assert ss.ziel2_lesen(srv) == str(tmp / "NAS")
    liste = ss.sicherungen(srv)
    assert len(liste) == 1 and liste[0]["gut"] and liste[0]["anlass"] == "Einrichtung", liste
    assert any(p.suffix == ss.ENDUNG for p in (tmp / "NAS").iterdir()), "Kopie auf dem zweiten Ziel"
    prot = Path(erg["protokoll"]).read_text(encoding="utf-8")
    assert "FERTIG" in prot and PW not in prot and "Win-Geheim-1" not in prot and "läuft (Port" in prot
    assert all(z[3] in ("läuft", "gut", "Warnung") for z in zustaende)
    ok("Durchlauf: Server, Administrator, Ablage, zweites Ziel, erste Sicherung mit Probe, Zugangsdatei; "
       "Firewall-Fehler nur Warnung; Protokoll ohne Passwörter")

    time.sleep(1.1)     # Sicherungen heißen nach der Sekunde
    erg2 = sa.ausfuehren(a, melden=lambda t: None, windows=lambda b: "")
    assert erg2["gut"] and erg2["fingerabdruck"] == erg["fingerabdruck"], "zweiter Lauf: Server bleibt"
    assert len(ss.sicherungen(srv)) == 2, [(x["datei"].name, x["gut"]) for x in ss.sicherungen(srv)]
    ok("zweiter Durchlauf auf demselben Ordner: Server und Zertifikat bleiben")

    b = angaben(ordner=str(tmp / "Kaputt"), port=a.port, freigabe=True)       # Port belegt
    zust = []
    erg3 = sa.ausfuehren(b, melden=lambda t: None, fortschritt=lambda *x: zust.append(x), windows=lambda c: "")
    assert not erg3["gut"] and zust[-1][3] == "Fehler" and zust[-1][0] == 1, zust
    assert "belegt" in Path(erg3["protokoll"]).read_text(encoding="utf-8")
    ok("Pflichtschritt misslingt (Port belegt): Abbruch, Protokoll mit Grund")
finally:
    sb.ZentralerServer(a.ordner, port=a.port).stoppen()
print("alle Prüfungen bestanden")
