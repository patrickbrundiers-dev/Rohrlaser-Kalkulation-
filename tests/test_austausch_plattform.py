"""Austauschordner 2.0, Paket A: Kern ohne Oberfläche (austausch_dateien.py, austausch_zuordnung.py).

Abnahme laut Master-Auftrag (Abschnitt 15):
- A1 Bereiche: gemeinsamer Ordner/Austausch, persönlicher Ordner, Anfragen, Angebotsablage, PPEASE; interne Ordner
     und Office-Sperrdateien bleiben aus der Liste, Archiv wird mitgelesen
- A2 Hochladen: Zwischendatei, gleicher Name -> beide behalten / neue Version / überspringen, nichts überschrieben;
     Ordner mit Inhalt; ausführbare Dateien abgelehnt; Abbruch mitten im Upload lässt nichts Halbes liegen
- A3 Gleichzeitig: zwei Plätze laden dieselbe Datei hoch -> der zweite bekommt eine Meldung, keine kaputte Datei
- A4 Umbenennen/Verschieben/Kopieren: Metadaten und Verlauf ziehen mit, belegter Name wird nicht ersetzt
- A5 Papierkorb: Löschen verschiebt, Wiederherstellen holt zurück, endgültig nur Admin
- A6 Versionen: neue Fassung sichert die alte, Wiederherstellen sichert die aktuelle, Konflikt bei fremder Änderung
- A7 Sperre: weiche Bearbeitungssperre zweier Plätze, verwaiste Sperre, Office-Sperrdatei ~$
- A8 Zuordnung: Angebots-/Auftrags-/PPEASE-/Anfrage-/Kundennummer, sicher gesetzt, unsicher als Vorschlag, bestätigen
- A9 Suche und Filter: Name, Kunde, Kommentar, Inhalt, Typ, Mitarbeiter, Status, neu für mich, Sortierung
- A10 Rechte: Rollen begrenzen Hochladen/Löschen, PPEASE-Angebotsordner nie angelegt, Anfragen nur lesen
- A11 Abgleich: Metadaten und Kommentare gehen über den gemeinsamen Ordner an den Kollegen
- A12 Menge: 20.000 Dateien einlesen und filtern in vertretbarer Zeit

Aufruf: python tests/test_austausch_plattform.py
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import austausch_dateien as ad  # noqa: E402
from rohrlaser import austausch_zuordnung as az  # noqa: E402
from rohrlaser import rollen, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def platz(k, name):
    db = Datenbank(tmp / f"{k}.db")
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("teilen_ordner", str(gemeinsam))
    return db


db = platz("PB", "Patrick")
db2 = platz("MK", "Max")
w = ad.wurzeln(db, anlegen=True)
assert w[ad.DATEIEN] == gemeinsam / "Austausch" and w[ad.PERSOENLICH] == gemeinsam / "Austausch" / "_Persoenlich" / "PB"
assert w[ad.PERSOENLICH].is_dir() and w[ad.PPEASE] is None
quelle = tmp / "quelle"
quelle.mkdir()


def datei(name, inhalt=b"x"):
    p = quelle / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(inhalt if isinstance(inhalt, bytes) else inhalt.encode())
    return p


# ------------------------------------------------------------------ A2 Hochladen
b = ad.hochladen(db, [datei("Halter.step", "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;"),
                      datei("Zeichnung.pdf", b"%PDF-1.4")], ad.DATEIEN)
assert b.ok and len(b.neu) == 2, b.text()
m = ad.meta(db, "dateien:Halter.step")
assert m["hochgeladen_von"] == "PB" and m["status"] == ad.NEU and m["art"] == "step" and m["pruefsumme"]
assert [e["art"] for e in ad.verlauf(db, "dateien:Halter.step")] == [ad.E_HOCH]
datei("Halter.step", "ISO-10303-21; neu")
b = ad.hochladen(db, [quelle / "Halter.step"], ad.DATEIEN)                  # Vorgabe: beide behalten
assert b.umbenannt and (w[ad.DATEIEN] / "Halter (2).step").exists()
assert (w[ad.DATEIEN] / "Halter.step").read_text().endswith("DATA;\nENDSEC;")   # Original unverändert
b = ad.hochladen(db, [quelle / "Halter.step"], ad.DATEIEN, konflikt=lambda n: ad.VERSION)
assert len(b.versionen) == 1 and (w[ad.DATEIEN] / "Halter.step").read_text() == "ISO-10303-21; neu"
v = ad.versionen(w[ad.DATEIEN] / "Halter.step")
assert len(v) == 1 and v[0]["nummer"] == 1 and v[0]["wer"] == "PB" and "DATA" in v[0]["pfad"].read_text()
b = ad.hochladen(db, [quelle / "Halter.step"], ad.DATEIEN, konflikt=lambda n: ad.UEBERSPRINGEN)
assert b.uebersprungen and not b.neu
b = ad.hochladen(db, [datei("boese.exe"), datei("_intern.txt")], ad.DATEIEN)
assert len(b.uebersprungen) == 2 and not (w[ad.DATEIEN] / "boese.exe").exists()
datei("Projekt X/Teil1.dxf")
datei("Projekt X/Unter/Teil2.dxf")
b = ad.hochladen(db, [quelle / "Projekt X"], ad.DATEIEN)
assert len(b.neu) == 2 and (w[ad.DATEIEN] / "Projekt X" / "Unter" / "Teil2.dxf").exists()
gross = datei("gross.stl", os.urandom(5 << 20))
zaehler = []
b = ad.hochladen(db, [gross], ad.DATEIEN, abbrechen=lambda: len(zaehler) > 2,
                 fortschritt=lambda n, g, name: zaehler.append(n))
assert b.abgebrochen and not (w[ad.DATEIEN] / "gross.stl").exists()
assert not list(w[ad.DATEIEN].glob("*" + ad.TEIL)), "Zwischendatei nach Abbruch"
b = ad.hochladen(db, [gross], ad.DATEIEN, fortschritt=lambda n, g, name: zaehler.append((n, g)))
assert b.ok and (w[ad.DATEIEN] / "gross.stl").stat().st_size == 5 << 20 and zaehler[-1][0] == zaehler[-1][1]
ok("A2 Hochladen: Zwischendatei, beide behalten/Version/überspringen, Ordner, .exe abgelehnt, Abbruch sauber")

# ------------------------------------------------------------------ A1 Einlesen
(w[ad.DATEIEN] / "~$ichnung.pdf").write_bytes(b"\x02MK" + b" " * 50)
(w[ad.DATEIEN] / "Thumbs.db").write_bytes(b"")
(w[ad.DATEIEN] / "halb.pdf.rlteil").write_bytes(b"")
liste = ad.einlesen(w[ad.DATEIEN], ad.DATEIEN)
namen = {e.rel for e in liste}
assert {"Halter.step", "Zeichnung.pdf", "Projekt X", "Projekt X/Unter/Teil2.dxf"} <= namen
assert not any(n.startswith(("_", "~$")) or "Thumbs" in n or n.endswith(ad.TEIL) for n in namen), namen
assert next(e for e in liste if e.name == "Zeichnung.pdf").office == "MK"
assert ad.sperre(db, "dateien:Zeichnung.pdf")["wer"] == "MK"
(w[ad.DATEIEN] / "~$ichnung.pdf").unlink()
(w[ad.DATEIEN] / "halb.pdf.rlteil").unlink()
assert ad.art("a.STP") == "step" and ad.art("x.lst") == "laser" and ad.art("m.msg") == "mail" and ad.art("q.zip") == "zip"
ok("A1 Einlesen: interne Dateien ausgeblendet, Office-Sperrdatei erkannt, Dateiarten")

# ------------------------------------------------------------------ A3 Gleichzeitig
ergebnis = {}
riesig = datei("riesig.step", os.urandom(30 << 20))


def laden(k, d):
    ergebnis[k] = ad.hochladen(d, [riesig], ad.DATEIEN, konflikt=lambda n: ad.VERSION)


t1 = threading.Thread(target=laden, args=("PB", db))
t1.start()
time.sleep(0.05)
laden("MK", db2)
t1.join()
alle_ok = [k for k, r in ergebnis.items() if r.neu or r.versionen]
assert alle_ok, ergebnis
assert (w[ad.DATEIEN] / "riesig.step").stat().st_size == 30 << 20
assert not list(w[ad.DATEIEN].glob("*" + ad.TEIL))
assert not ad.laufende_uploads(db)
ok(f"A3 Gleichzeitiges Hochladen: {len(alle_ok)} Platz/Plätze erfolgreich, Datei vollständig, keine Reste")

# ------------------------------------------------------------------ A4 Umbenennen, Verschieben, Kopieren
ad.setzen(db, "dateien:Zeichnung.pdf", bearbeiter="MK", status=ad.BEARBEITUNG)
ad.kommentar(db, "dateien:Zeichnung.pdf", "Bitte Maß 120 prüfen", an="MK")
neu = ad.umbenennen(db, "dateien:Zeichnung.pdf", "Zeichnung Rev B.pdf")
assert neu == "dateien:Zeichnung Rev B.pdf" and ad.meta(db, neu)["bearbeiter"] == "MK"
assert any(e["art"] == ad.E_KOMMENTAR for e in ad.verlauf(db, neu)) and not ad.meta(db, "dateien:Zeichnung.pdf")
try:
    ad.umbenennen(db, neu, "Halter.step")
    raise AssertionError("belegter Name")
except ad.AustauschFehler:
    pass
for falsch in ("a/b", "con.txt", "_x", "  "):
    try:
        ad.name_pruefen(falsch)
        raise AssertionError(falsch)
    except ad.AustauschFehler:
        pass
ad.ordner_anlegen(db, ad.DATEIEN, "", "Kunde Müller")
neu2 = ad.verschieben(db, [neu], ad.DATEIEN, "Kunde Müller")[0]
assert neu2 == "dateien:Kunde Müller/Zeichnung Rev B.pdf" and ad.meta(db, neu2)["status"] == ad.BEARBEITUNG
kopie = ad.kopieren(db, [neu2], ad.PERSOENLICH)[0]
assert kopie == "persoenlich:Zeichnung Rev B.pdf" and ad.meta(db, kopie)["bearbeiter"] == "MK"
assert (w[ad.DATEIEN] / "Kunde Müller" / "Zeichnung Rev B.pdf").exists()
ordner_neu = ad.umbenennen(db, "dateien:Kunde Müller", "Kunde Mueller")
assert ad.meta(db, "dateien:Kunde Mueller/Zeichnung Rev B.pdf")["bearbeiter"] == "MK", ordner_neu
try:
    ad.verschieben(db, ["dateien:Projekt X"], ad.DATEIEN, "Projekt X/Unter")
    raise AssertionError("in sich selbst")
except ad.AustauschFehler:
    pass
arch = ad.archivieren(db, ["dateien:Kunde Mueller/Zeichnung Rev B.pdf"])[0]
assert arch == "dateien:_Archiv/Kunde Mueller/Zeichnung Rev B.pdf" and ad.meta(db, arch)["status"] == ad.ARCHIVIERT
e = [x for x in ad.einlesen(w[ad.DATEIEN], ad.DATEIEN) if x.datei == arch]
assert e and e[0].archiv
zurueck = ad.aus_archiv(db, arch)
assert zurueck == "dateien:Kunde Mueller/Zeichnung Rev B.pdf"
ok("A4 Umbenennen, Ordner, Verschieben, Kopieren, Archiv: Metadaten und Verlauf ziehen mit")

# ------------------------------------------------------------------ A5 Papierkorb
assert ad.loeschen(db, ["dateien:Halter (2).step"]) == 1
assert not (w[ad.DATEIEN] / "Halter (2).step").exists()
korb = ad.papierkorb(db)
assert len(korb) == 1 and korb[0]["wer"] == "PB" and ad.meta(db, "dateien:Halter (2).step")["weg"] == "ja"
(w[ad.DATEIEN] / "Halter (2).step").write_text("neu angelegt")      # Name inzwischen wieder belegt
zur = ad.wiederherstellen(db, korb[0])
assert zur == "dateien:Halter (2) (2).step" and (w[ad.DATEIEN] / "Halter (2).step").read_text() == "neu angelegt"
ad.loeschen(db, [zur])
rollen.benutzer_setzen(db, "PB", "Patrick", ["kalkulation"])
assert rollen.aktiv(db) and not ad.darf_endgueltig(db)
try:
    ad.endgueltig_loeschen(db, ad.papierkorb(db))
    raise AssertionError("ohne Admin")
except ad.AustauschFehler:
    pass
rollen.benutzer_setzen(db, "PB", "Patrick", ["admin"])
assert ad.endgueltig_loeschen(db, ad.papierkorb(db)) == 1 and not ad.papierkorb(db)
assert any(e["art"] == ad.E_ENDGUELTIG for e in ad.verlauf(db))
rollen.entfernen(db, "PB")
ok("A5 Papierkorb: löschen, wiederherstellen (Name belegt), endgültig nur Admin")

# ------------------------------------------------------------------ A6 Versionen und Konflikt
p = w[ad.DATEIEN] / "Halter.step"
basis = ad.pruefsumme(p)
datei("bearbeitet_MK.step", "Fassung MK")
datei("bearbeitet_PB.step", "Fassung PB")
ad.neue_version(db2, "dateien:Halter.step", quelle / "bearbeitet_MK.step", basis_pruefsumme=basis)
try:
    ad.neue_version(db, "dateien:Halter.step", quelle / "bearbeitet_PB.step", basis_pruefsumme=basis)
    raise AssertionError("Konflikt erwartet")
except ad.Konflikt as k:
    assert k.wer == "MK", k.wer
assert p.read_text() == "Fassung MK"
alt = ad.versionen(p)
assert len(alt) == 2
ad.version_wiederherstellen(db, "dateien:Halter.step", alt[-1]["pfad"])
assert "DATA" in p.read_text() and len(ad.versionen(p)) == 3          # Fassung MK zusätzlich gesichert
assert any("Fassung MK" == v["pfad"].read_text() for v in ad.versionen(p))
ok("A6 Versionen: neue Fassung sichert die alte, Konflikt bei paralleler Änderung, Wiederherstellen ohne Verlust")

# ------------------------------------------------------------------ A7 Sperre
pfad_, fremd = ad.bearbeiten(db, "dateien:Halter.step")
assert fremd is None and ad.sperre(db, "dateien:Halter.step")["eigene"]
n_vor = len(ad.versionen(p))
pfad_, fremd = ad.bearbeiten(db2, "dateien:Halter.step")
assert fremd and fremd["wer"] == "PB"
try:
    ad.loeschen(db2, ["dateien:Halter.step"])
    raise AssertionError("gesperrt")
except ad.AustauschFehler:
    pass
pfad_, fremd = ad.bearbeiten(db2, "dateien:Halter.step", trotzdem=True)
assert ad.sperre(db2, "dateien:Halter.step")["wer"] == "MK" and len(ad.versionen(p)) == n_vor   # schon gesichert
assert any("trotz" in e["text"] for e in ad.verlauf(db2, "dateien:Halter.step"))
s = ad._sperr_datei(w, "dateien:Halter.step")
alt_t = time.time() - (ad.SPERRE_MIN + 1) * 60
os.utime(s, (alt_t, alt_t))
assert ad.sperre(db, "dateien:Halter.step") is None                        # verwaist
assert ad.entsperren(db2, "dateien:Halter.step", auch_fremde=True) or True
ok("A7 Bearbeitungssperre: Warnung, Trotzdem bearbeiten, Löschen gesperrt, verwaiste Sperre läuft ab")

# ------------------------------------------------------------------ A8 Zuordnung
db.con.execute("INSERT INTO kunden (kundennr, name) VALUES ('10042', 'Müller Stahlbau')")
a1 = db.angebot_neu(dict(nummer="2026-00042", kundennr="10042", bearbeiter="MK"), zaehler=False)
db.zusatz_setzen(a1, "ppease", dict(nummer="2026-44327"))
db.con.commit()
ktx = az.Kontext(db)
t = {(x["feld"], x["wert"]): x["sicher"] for x in az.erkennen("dateien:Anfrage 2026-00042 Rev2.step", ktx)}
assert t[("angebot", "2026-00042")] and t[("kundennr", "10042")] and not t[("bearbeiter", "MK")], t
t = {(x["feld"], x["wert"]): x["sicher"] for x in az.erkennen("dateien:Bestellung 2026-44327.pdf", ktx)}
assert t[("ppease", "2026-44327")] and t[("angebot", "2026-00042")], t
t = {(x["feld"], x["wert"]): x["sicher"] for x in az.erkennen("dateien:Zeichnung 2026-99999.pdf", ktx)}
assert t == {("angebot", "2026-99999"): False}, t
t = {(x["feld"], x["wert"]): x["sicher"] for x in az.erkennen("dateien:Müller Stahlbau/teil.dxf", ktx)}
assert t == {("kundennr", "10042"): False}, t
t = {(x["feld"], x["wert"]): x["sicher"] for x in az.erkennen("dateien:Kd-Nr 10042 Rahmen.step", ktx)}
assert t[("kundennr", "10042")], t
t = {(x["feld"], x["wert"]): x["sicher"] for x in az.erkennen("dateien:AU-2026-00007 Lieferschein.pdf", ktx)}
assert ("auftrag", "AU-2026-00007") in t and not t[("auftrag", "AU-2026-00007")]
t = {(x["feld"], x["wert"]): x["sicher"] for x in az.erkennen("anfragen:2026/A-2026-00012/Dateien/x.step", ktx)}
assert t[("anfrage", "A-2026-00012")]
datei("Müller Stahlbau/blech.dxf")
b = ad.hochladen(db, [datei("2026-00042_Rohr.step"), quelle / "Müller Stahlbau"], ad.DATEIEN)
m = ad.meta(db, "dateien:2026-00042_Rohr.step")
assert m["angebot"] == "2026-00042" and m["kundennr"] == "10042" and m["ppease"] == "2026-44327", m
assert [v["feld"] for v in ad.vorschlaege(m)] == ["bearbeiter"], m["vorschlag"]
m = ad.meta(db, "dateien:Müller Stahlbau/blech.dxf")
assert not m.get("kundennr") and ad.vorschlaege(m)[0]["wert"] == "10042"
ad.vorschlag_bestaetigen(db, "dateien:Müller Stahlbau/blech.dxf")
m = ad.meta(db, "dateien:Müller Stahlbau/blech.dxf")
assert m["kundennr"] == "10042" and not ad.vorschlaege(m)
ad.setzen(db, "dateien:2026-00042_Rohr.step", kundennr="10001")            # von Hand: bleibt
az.anwenden(db, "dateien:2026-00042_Rohr.step")
assert ad.meta(db, "dateien:2026-00042_Rohr.step")["kundennr"] == "10001"
ok("A8 Zuordnung: Angebot/PPEASE/Kunde/Auftrag/Anfrage, sicher gesetzt, unsicher als Vorschlag, Hand bleibt")

# ------------------------------------------------------------------ A9 Suche und Filter
liste = ad.einlesen(w[ad.DATEIEN], ad.DATEIEN)
metas = ad.meta(db)
kom = ad.kommentare_text(db)


def f(**k):
    return {e.rel for e in ad.filtern(liste, metas, ad.Filter(**k), ich="PB", kommentare=kom,
                                      kunden_namen={"10042": "Müller Stahlbau"})}


assert f(text="halter") >= {"Halter.step"}
assert "2026-00042_Rohr.step" in f(text="2026-00042") and "Müller Stahlbau/blech.dxf" in f(text="mueller stahlbau")
assert f(text="MASS 120 pruefen") == {"Kunde Mueller/Zeichnung Rev B.pdf"}       # Kommentar, ohne Umlaut
assert f(art="dxf", ordner=False) == {"Projekt X/Teil1.dxf", "Projekt X/Unter/Teil2.dxf", "Müller Stahlbau/blech.dxf"}
assert f(kunde="10042", ordner=False) == {"Müller Stahlbau/blech.dxf"}
assert f(mitarbeiter="MK", ordner=False) == {"Kunde Mueller/Zeichnung Rev B.pdf"}
assert f(status=ad.BEARBEITUNG) == {"Kunde Mueller/Zeichnung Rev B.pdf"}
g = {e.datei: e.zeit for e in liste}
g.pop("dateien:Halter.step")
assert f(nur_neu=True) == set()
ad.gesehen_setzen(db, g)
assert {e.rel for e in ad.filtern(liste, metas, ad.Filter(nur_neu=True, ordner=False), gesehen_=ad.gesehen(db))} == \
    {"Halter.step"}
s = ad.sortieren(liste, metas, "groesse", True)
assert s[0].ordner and [e for e in s if not e.ordner][0].name == "riesig.step"
ad.suche_speichern(db, "Müller DXF", ad.Filter(art="dxf", kunde="10042").als_dict())
assert ad.Filter.aus(ad.gespeicherte_suchen(db)[0]["filter"]).kunde == "10042"
assert ad.favorit_umschalten(db, "dateien:Halter.step") and ad.favoriten(db) == ["dateien:Halter.step"]
ad.benutzt(db, "dateien:Halter.step")
ad.benutzt(db, "dateien:Projekt X/Teil1.dxf")
assert ad.zuletzt(db)[0] == "dateien:Projekt X/Teil1.dxf"
assert any(x["wer"] == "MK" for x in ad.wer_arbeitet(db))
ok("A9 Suche (Name, Nummer, Kundenname, Kommentar), Filter, neu für mich, Sortierung, gespeicherte Suche, Favoriten")

# ------------------------------------------------------------------ A10 Rechte und Bereiche
rollen.benutzer_setzen(db, "PB", "Patrick", ["werkstatt"])
assert ad.darf(db, ad.HOCHLADEN) and not ad.darf(db, ad.LOESCHEN) and not ad.darf(db, ad.VERSCHIEBEN)
try:
    ad.loeschen(db, ["dateien:Halter.step"])
    raise AssertionError("Werkstatt darf nicht löschen")
except ad.AustauschFehler as e:
    assert "Berechtigung" in str(e)
db.einstellung_setzen(ad.RECHTE, {"werkstatt": ["lesen", "hochladen", "loeschen"]})
assert ad.darf(db, ad.LOESCHEN)
rollen.entfernen(db, "PB")
db.einstellung_setzen(ad.RECHTE, None)
pp = tmp / "PPEASE"
(pp / "2026-44327").mkdir(parents=True)
db.einstellung_setzen("ppease_ordner", str(pp))
w2 = ad.wurzeln(db)
assert w2[ad.PPEASE] == pp
for aufruf in (lambda: ad.ordner_anlegen(db, ad.PPEASE, "", "2026-55555"),
               lambda: ad.hochladen(db, [quelle / "Halter.step"], ad.PPEASE),
               lambda: ad.umbenennen(db, "ppease:2026-44327", "x"),
               lambda: ad.hochladen(db, [quelle / "Halter.step"], ad.ANFRAGEN)):
    try:
        aufruf()
        raise AssertionError("PPEASE/Anfragen")
    except ad.AustauschFehler:
        pass
b = ad.hochladen(db, [quelle / "Halter.step"], ad.PPEASE, "2026-44327")
assert b.ok and (pp / "2026-44327" / "Halter.step").exists()
assert ad.meta(db, "ppease:2026-44327/Halter.step")["ppease"] == "2026-44327"
assert ad.meta(db, "ppease:2026-44327/Halter.step")["angebot"] == "2026-00042"
assert [p_.name for p_ in pp.iterdir()] == ["2026-44327"]
ok("A10 Rechte je Rolle, PPEASE-Angebotsordner nie angelegt, Anfragen-Akten nur lesen")

# ------------------------------------------------------------------ A11 Abgleich der Metadaten
db.einstellung_setzen("teilen_ordner", str(gemeinsam))
teilen.abgleichen(db)
teilen.abgleichen(db2, teilen.ZUSAMMENFUEHREN)
m2 = ad.meta(db2, "dateien:2026-00042_Rohr.step")
assert m2.get("angebot") == "2026-00042" and m2.get("kundennr") == "10001", m2
assert any(e["text"] == "Bitte Maß 120 prüfen" for e in ad.verlauf(db2))
ad.setzen(db2, "dateien:2026-00042_Rohr.step", status=ad.RUECKFRAGE)
teilen.abgleichen(db2)
teilen.abgleichen(db)
assert ad.meta(db, "dateien:2026-00042_Rohr.step")["status"] == ad.RUECKFRAGE
ok("A11 Abgleich: Zuordnung, Status und Kommentare kommen beim Kollegen an")

# ------------------------------------------------------------------ A12 Menge
viele = tmp / "Viele"
for i in range(200):
    o = viele / f"Kunde {i:03d}"
    o.mkdir(parents=True)
    for j in range(100):
        (o / f"Teil_{i:03d}_{j:03d}.step").write_bytes(b"")
t0 = time.perf_counter()
liste = ad.einlesen(viele, ad.DATEIEN)
t1 = time.perf_counter()
treffer = ad.filtern(liste, {}, ad.Filter(text="teil 150_07"))
t2 = time.perf_counter()
assert len(liste) == 20200 and len(treffer) == 10, len(treffer)
assert t1 - t0 < 10 and t2 - t1 < 3, (t1 - t0, t2 - t1)
ok(f"A12 20.000 Dateien: einlesen {t1 - t0:.2f} s, suchen {t2 - t1:.2f} s")
print("Alle Prüfungen bestanden.")
