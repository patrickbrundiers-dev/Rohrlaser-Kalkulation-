"""Dokumentenablage nach PPEASE-Angebotsnummer (Patrick 19.11.2026, ppease_ablage.py, ppease_dialog.py).

Abnahme laut Entwicklungsauftrag, Abschnitt 12:
- P1 Angebotsnummer: Plausibilität (leer, verbotene Zeichen, Muster nur Hinweis), Ordnername mit Kunde/Bezeichnung
- P2 Speicherpfad: lokal ok, fehlender Ordner (Server/NAS nicht erreichbar), keine Schreibrechte, hängendes
     Netzlaufwerk (Zeitlimit), leer
- P3 Ordner: Jahresordner, vorhandener Ordner (auch aus einem anderen Jahr, auch von Hand angelegt '123456 …') wird
     wiederverwendet, 1234567 ist nicht 123456
- P4 Dokumente: Angebotsordner mit Angebotsakte (ohne Versionen/akte.json), Anfrage, Zielordner-Vorschläge, extern
     mit Ordnern, nichts doppelt
- P5 Speichern: Unterordner nur bei Bedarf, Verzeichnis + Protokoll, mehrfaches Speichern = nichts doppelt
- P6 Nachspeichern: geänderte Datei nie ungefragt überschrieben; Ersetzen sichert in _Versionen, neue Version daneben,
     Überspringen; eigene Kategorien
- P7 Mehrbenutzer: Sperre eines anderen Platzes blockiert, verwaiste Sperre wird übernommen, zwei Protokolldateien
- P8 Absturz: Zwischendatei und unterbrochener Vorgang werden erkannt und aufgeräumt; Netzwerkfehler mitten im
     Speichern bricht ab, kopierte Dateien vollständig
- P9 Fenster: Datei-Menü und Angebot, vier Bereiche, Status/Zielordner/Aktion, Speichern mit Fortschritt, Nummer am
     Angebot gemerkt (ohne neue Spalte), Pfad ändern, Ablage prüfen, Hinzufügen per Ziehen

Aufruf: python tests/test_ppease_ablage.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QGroupBox  # noqa: E402

from rohrlaser import ppease_ablage as pa  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
JAHR = datetime.date.today().year

# ------------------------------------------------------------------ P1 Nummer und Ordnername
assert pa.nummer_pruefen(" 2026 - 44327 ") == ("2026-44327", None, None)      # Patrick: Jahr-Nummer
assert pa.nummer_pruefen("123456", r"^\d{4,10}$") == ("123456", None, None)
assert pa.nummer_pruefen("")[1]
assert pa.nummer_pruefen("12/34")[1]
nr, fehler, hinweis = pa.nummer_pruefen("AN-77")
assert nr == "AN-77" and fehler is None and "2026-44327" in hinweis
assert pa.nummer_pruefen("AN-77", r"^AN-\d+$")[2] is None
assert pa.nummer_pruefen("2026-12345", "[kaputt")[2] is None          # kaputtes Muster: Vorgabe
v0 = pa.Vorgaben(ordner=str(tmp / "Haupt"))                         # Vorgabe: Hauptordner\2026-44327
assert pa.ordnername(v0, "2026-44327", "Müller", "Gestell") == "2026-44327"
assert pa.neuer_ordner(v0, "2026-44327") == tmp / "Haupt" / "2026-44327"
v = pa.Vorgaben(ordner=str(tmp / "Haupt"), praefix="Angebot_", jahresordner=True)    # mit Vorsatz und Jahr
assert pa.ordnername(v, "123456", "Müller GmbH", "Gestell") == "Angebot_123456"
v.ordnername = "kunde"
assert pa.ordnername(v, "123456", 'Müller/"Bau"', "Gestell") == "Angebot_123456 Müller__Bau_"
v.ordnername = "kunde_bezeichnung"
assert pa.ordnername(v, "123456", "Müller", "Gestell Linie 3") == "Angebot_123456 Müller – Gestell Linie 3"
v.ordnername = "nummer"
ok("P1 Nummer geprüft (Fehler/Hinweis), Ordnername mit Kunde und Bezeichnung")

# ------------------------------------------------------------------ P2 Speicherpfad
haupt = tmp / "Haupt"
haupt.mkdir()
assert pa.pfad_pruefen(haupt).ok
assert not list(haupt.iterdir())                                   # Prüfdatei wieder weg
assert pa.pfad_pruefen("").art == "leer"
assert pa.pfad_pruefen(tmp / "Server_weg").art == "fehlt"
(tmp / "datei.txt").write_text("x")
assert pa.pfad_pruefen(tmp / "datei.txt").art == "kein_ordner"
nur_lesen = tmp / "NurLesen"
nur_lesen.mkdir()
os.chmod(nur_lesen, 0o555)
if os.access(nur_lesen, os.W_OK):           # als root sind Rechte wirkungslos: Schreibfehler nachstellen
    alt_write = Path.write_bytes
    Path.write_bytes = lambda self, d: (_ for _ in ()).throw(PermissionError("Zugriff verweigert"))
    assert pa.pfad_pruefen(nur_lesen).art == "nur_lesen"
    Path.write_bytes = alt_write
else:
    assert pa.pfad_pruefen(nur_lesen).art == "nur_lesen"
os.chmod(nur_lesen, 0o755)
alt_exists = Path.exists
Path.exists = lambda self: time.sleep(3) or True                   # hängendes Netzlaufwerk
t0 = time.time()
r = pa.pfad_pruefen(haupt, sek=0.5)
Path.exists = alt_exists
assert r.art == "zeit" and time.time() - t0 < 2.5, r
ok("P2 Speicherpfad: erreichbar, fehlt, kein Ordner, keine Schreibrechte, hängt (Zeitlimit)")

# ------------------------------------------------------------------ P3 Ordner finden/anlegen
o, da = pa.ordner_status(v, "123456")
assert o == haupt / str(JAHR) / "Angebot_123456" and not da
alt = haupt / str(JAHR - 1) / "Angebot_123456 Müller"
alt.mkdir(parents=True)
assert pa.ordner_status(v, "123456") == (alt, True)                # anderes Jahr, anderer Zusatz
(haupt / str(JAHR - 1) / "Angebot_1234567").mkdir()
assert pa.finden(haupt, "123456", "Angebot_") == alt
assert pa.finden(haupt, "12345", "Angebot_") is None
(haupt / "998877 von Hand").mkdir()
assert pa.finden(haupt, "998877") == haupt / "998877 von Hand"
v2 = pa.Vorgaben(ordner=str(haupt), jahresordner=False)
assert pa.neuer_ordner(v2, "555") == haupt / "555"
(haupt / "2026-44327").mkdir()
(haupt / "2026-443270").mkdir()
assert pa.ordner_status(v0, "2026-44327") == (haupt / "2026-44327", True)
assert pa.finden(haupt, "2026-4432", "") is None
ok("P3 Jahresordner, vorhandene Ordner (anderes Jahr, von Hand) wiederverwendet, 1234567 ≠ 123456")

# ------------------------------------------------------------------ P4 Dokumente sammeln
ang = tmp / "Ablage" / "2026-00042 Müller"
for rel, inhalt in (("2026-00042 Kalkulation.pdf", b"%PDF kalk"), ("2026-00042 Angebot.pdf", b"%PDF ang"),
                    ("Angebotsakte/PDF/Angebot_2026-00042_Kunde.pdf", b"%PDF kunde"),
                    ("Angebotsakte/PDF/Angebot_2026-00042_Intern.pdf", b"%PDF intern"),
                    ("Angebotsakte/PDF/Versionen/Angebot_2026-00042_Kunde_V1.pdf", b"alt"),
                    ("Angebotsakte/Schnittschemata/Angebot_2026-00042_Schnittschema.pdf", b"%PDF schnitt"),
                    ("Angebotsakte/Kalkulationsdaten/akte.json", b"{}"),
                    ("Angebotsakte/Kalkulationsdaten/kalkulation_V1.json", b"{}"),
                    ("Angebotsakte/Technische_Daten/Pos_10.png", b"png"),
                    ("STEP/Rahmen.stp", b"ISO-10303 rahmen"), ("2026-00042 Materialanfrage.csv", b"a;b"),
                    ("2026-00042 Abwicklung.dxf", b"0\nSECTION"), ("~$offen.xlsx", b"x")):
    (ang / rel).parent.mkdir(parents=True, exist_ok=True)
    (ang / rel).write_bytes(inhalt)
anfrage = tmp / "Anfrage"
anfrage.mkdir()
(anfrage / "Kundenzeichnung.pdf").write_bytes(b"%PDF kunde zeichnung")
(anfrage / "Anfrage.msg").write_bytes(b"msg")
dok = pa.dokumente_sammeln(ang, [anfrage / "Kundenzeichnung.pdf", anfrage / "Anfrage.msg", ang / "STEP/Rahmen.stp"])
namen = {d.name: d for d in dok}
assert "Angebot_2026-00042_Kunde_V1.pdf" not in namen and "akte.json" not in namen and "~$offen.xlsx" not in namen
assert len(dok) == 12, sorted(namen)
erwartet = {"Angebot_2026-00042_Kunde.pdf": pa.ANGEBOT, "Angebot_2026-00042_Intern.pdf": pa.KALKULATION,
            "2026-00042 Kalkulation.pdf": pa.KALKULATION, "2026-00042 Angebot.pdf": pa.ANGEBOT,
            "Angebot_2026-00042_Schnittschema.pdf": pa.SCHNITT, "kalkulation_V1.json": pa.KALKULATION,
            "Pos_10.png": pa.ZEICHNUNG, "Rahmen.stp": pa.MODELL, "2026-00042 Materialanfrage.csv": pa.MATERIAL,
            "2026-00042 Abwicklung.dxf": pa.ZEICHNUNG, "Kundenzeichnung.pdf": pa.KUNDE, "Anfrage.msg": pa.KUNDE}
for n, k in erwartet.items():
    assert namen[n].kategorie == k, (n, namen[n].kategorie, k)
assert namen["Angebot_2026-00042_Kunde.pdf"].quelle == pa.Q_AKTE and namen["Anfrage.msg"].quelle == pa.Q_ANFRAGE
assert dok[0].quelle == pa.Q_AKTE                                 # Akte zuerst
extra = tmp / "Extra"
(extra / "Unter").mkdir(parents=True)
(extra / "Foto.jpg").write_bytes(b"jpg")
(extra / "Unter" / "Stueckliste.xlsx").write_bytes(b"xlsx")
neu = pa.extern([extra, extra / "Foto.jpg", ang / "STEP/Rahmen.stp"], dok)
assert sorted(d.name for d in neu) == ["Foto.jpg", "Stueckliste.xlsx"] and neu[0].quelle == pa.Q_EXTERN
assert {d.name: d.kategorie for d in neu} == {"Foto.jpg": pa.SONSTIGE, "Stueckliste.xlsx": pa.MATERIAL}
assert pa.dateityp("a.STEP") == "STEP" and pa.groesse_text(2_500_000) == "2,4 MB"
ok("P4 Dokumente aus Angebotsordner/Akte/Anfrage (ohne Versionen, Hilfsdateien), Zielordner-Vorschläge, extern")

# ------------------------------------------------------------------ P5 Speichern, mehrfach
ziel = haupt / str(JAHR) / "Angebot_700001"
b = pa.ablegen(v, ziel, dok, "PB", angebot="2026-00042", nummer="700001")
assert not b.ok and not ziel.exists() and "PPEASE" in b.fehler[0][1]     # Angebotsordner nie anlegen (Patrick)
ziel.mkdir(parents=True)                                            # legt PPEASE an
b = pa.ablegen(v, ziel, dok, "PB", angebot="2026-00042", nummer="700001")
assert b.ok and not b.angelegt and len(b.gespeichert) == 12, b
unter = sorted(p.name for p in ziel.iterdir())
assert unter == ["01_Angebot", "02_Kalkulation", "03_Schnittschema", "04_Zeichnungen", "05_3D_Modelle",
                 "06_Materiallisten", "07_Kundenunterlagen", "_Protokoll"], unter
dok_extra = dok + [d for d in neu if d.name == "Stueckliste.xlsx"]
assert (ziel / "05_3D_Modelle/Rahmen.stp").read_bytes() == b"ISO-10303 rahmen"
verz = pa.verzeichnis(ziel)
e = verz["dateien"]["01_Angebot/Angebot_2026-00042_Kunde.pdf"]
assert e["version"] == 1 and e["von"] == "PB" and len(e["sha256"]) == 64 and e["angebot"] == "2026-00042"
assert verz["nummer"] == "700001"
pr = pa.protokoll(ziel)
assert pr[0]["aktion"] == "begonnen" and pr[-1]["aktion"] == "fertig" and sum(
    x["aktion"] == "gespeichert" for x in pr) == 12
b2 = pa.ablegen(v, ziel, dok_extra, "PB")
assert b2.ok and b2.gespeichert == ["06_Materiallisten/Stueckliste.xlsx"] and len(b2.uebersprungen) == 12, b2
assert not pa.sperre_lesen(ziel) and not list(ziel.rglob("*" + pa.TEIL))
st = pa.vergleichen(v, ziel, dok_extra)
assert {s for s, _ in st.values()} == {pa.GLEICH}
ok("P5 Angebotsordner nie angelegt, Unterordner nur nach Bedarf, Verzeichnis+Protokoll, zweites Speichern legt nichts doppelt ab")

# ------------------------------------------------------------------ P6 Nachspeichern mit Versionen
kunde = namen["Angebot_2026-00042_Kunde.pdf"]
time.sleep(0.01)
kunde.pfad.write_bytes(b"%PDF kunde NEU")
st = pa.vergleichen(v, ziel, [kunde])[id(kunde)]
assert st[0] == pa.GEAENDERT and "Version 1" in st[1]
b3 = pa.ablegen(v, ziel, [kunde], "PB")                          # ohne Aktion: nie überschreiben
assert not b3.gespeichert and b3.uebersprungen and (ziel / "01_Angebot" / kunde.name).read_bytes() == b"%PDF kunde"
b4 = pa.ablegen(v, ziel, [kunde], "PB", aktionen={id(kunde): pa.ERSETZEN})
assert b4.ersetzt and (ziel / "01_Angebot" / kunde.name).read_bytes() == b"%PDF kunde NEU"
gesichert = list((ziel / "01_Angebot" / pa.VERSIONEN).iterdir())
assert len(gesichert) == 1 and gesichert[0].name.startswith("Angebot_2026-00042_Kunde_V1_") and \
    gesichert[0].read_bytes() == b"%PDF kunde"
assert pa.verzeichnis(ziel)["dateien"]["01_Angebot/" + kunde.name]["version"] == 2
kunde.pfad.write_bytes(b"%PDF kunde DRITTE")
b5 = pa.ablegen(v, ziel, [kunde], "PB", aktionen={id(kunde): pa.NEUE_VERSION})
assert b5.versionen == ["01_Angebot/Angebot_2026-00042_Kunde_V2.pdf"], b5.versionen
assert (ziel / "01_Angebot/Angebot_2026-00042_Kunde.pdf").read_bytes() == b"%PDF kunde NEU"
assert pa.vorhandene(ziel) and all(pa.VERSIONEN not in r and pa.PROTOKOLL not in r for r, _, _ in pa.vorhandene(ziel))
# eigene Kategorien und umbenannte Ordner
v3 = pa.Vorgaben(ordner=str(haupt), kategorien=pa.kategorien_lesen("A_Angebot\n\n\n\n\n\n\n\n09_Prüfberichte"))
assert v3.kategorie_ordner(pa.ANGEBOT) == "A_Angebot" and v3.kategorie_ordner(pa.KALKULATION) == "02_Kalkulation"
assert pa.alle_kategorien(v3)[-1] == ("09_Prüfberichte", "09_Prüfberichte")
pb = pa.Dokument(extra / "Foto.jpg", kategorie="09_Prüfberichte")
assert pa.ablegen(v3, ziel, [pb], "PB").gespeichert == ["09_Prüfberichte/Foto.jpg"]
ok("P6 Nachspeichern: nie ungefragt, Ersetzen sichert nach _Versionen, neue Version daneben, eigene Kategorien")

# ------------------------------------------------------------------ P7 Mehrbenutzer
(ziel / pa.PROTOKOLL / pa.SPERRE).write_text(json.dumps(dict(von="KM", platz="ANDERER-PC", pid=1, zeit=datetime.datetime.now().isoformat(timespec="seconds"))))
try:
    pa.ablegen(v, ziel, dok, "PB")
    raise AssertionError("Sperre nicht beachtet")
except pa.Gesperrt as e:
    assert "KM" in str(e) and "ANDERER-PC" in str(e)
assert pa.sperre_lesen(ziel)["von"] == "KM"                      # fremde Sperre bleibt
alt_zeit = (datetime.datetime.now() - datetime.timedelta(minutes=pa.SPERRE_MIN + 1)).isoformat(timespec="seconds")
(ziel / pa.PROTOKOLL / pa.SPERRE).write_text(json.dumps(dict(von="KM", platz="ANDERER-PC", pid=1, zeit=alt_zeit)))
assert pa.ablegen(v, ziel, dok, "KM2").ok                         # verwaiste Sperre übernommen
assert not pa.sperre_lesen(ziel)
assert sorted(p.name for p in (ziel / pa.PROTOKOLL).glob("protokoll_*")) == ["protokoll_KM2.jsonl",
                                                                              "protokoll_PB.jsonl"]
ok("P7 Sperre eines Kollegen blockiert, verwaiste Sperre übernommen, Protokoll je Mitarbeiter")

# ------------------------------------------------------------------ P8 Absturz und Netzwerkausfall
(ziel / "01_Angebot" / ("halb.pdf" + pa.TEIL)).write_bytes(b"halb")
pa.protokoll_schreiben(ziel, "PB", dict(aktion="begonnen", vorgang="absturz-1", dateien=["halb.pdf"]))
with open(ziel / pa.PROTOKOLL / "protokoll_PB.jsonl", "a", encoding="utf-8") as f:
    f.write('{"aktion": "gespeich')                               # halbe Zeile beim Absturz
r = pa.aufraeumen(ziel)
assert r["entfernt"] == ["01_Angebot/halb.pdf" + pa.TEIL] and r["unterbrochen"]["vorgang"] == "absturz-1"
pa.unterbrochen_vermerken(ziel, "PB", r["unterbrochen"])
assert pa.aufraeumen(ziel) == dict(entfernt=[], unterbrochen=None)
ziel2 = haupt / str(JAHR) / "Angebot_700002"
import rohrlaser.ppease_ablage as modul  # noqa: E402
echt = modul._sicher_kopieren
zaehler = {"n": 0}


def wackelt(q, z):
    zaehler["n"] += 1
    if zaehler["n"] == 3:
        import shutil
        shutil.rmtree(haupt / str(JAHR) / "Angebot_700002")      # Netzlaufwerk weg
        raise OSError("Der Netzwerkpfad wurde nicht gefunden")
    return echt(q, z)


modul._sicher_kopieren = wackelt
ziel2.mkdir(parents=True)
b6 = pa.ablegen(v, ziel2, dok[:6], "PB")
modul._sicher_kopieren = echt
assert b6.abgebrochen and len(b6.gespeichert) == 2 and len(b6.fehler) == 1, b6
ok("P8 Absturz: Zwischendatei entfernt, unterbrochener Vorgang gemeldet; Netzwerkausfall bricht sauber ab")

# ------------------------------------------------------------------ P9 Fenster
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
a = db.angebot_neu(dict(nummer="2026-00042", kunde="Müller", maschine="T11", kundenreferenz="Gestell Linie 3"))
assert fenster.datei_aktionen.get("Dokumentenablage / PPEASE-Verknüpfung …")
seite = fenster.angebot_oeffnen(a)
assert seite is not None
meldungen = []
d = fenster.ppease_ablage()                                       # sichtbares Angebot
d.melden = lambda t, x: meldungen.append(x)
d.fragen = lambda t, x: meldungen.append(x) or True
assert d.kopf["id"] == a and d.angebotsordner == fenster.angebot_ordner(db.angebot(a))
assert {x.name for x in d.dokumente} >= {"Angebot_2026-00042_Kunde.pdf", "Rahmen.stp"}
assert d.kunde.text() == "Müller" and d.bezeichnung.text() == "Gestell Linie 3"
assert "Noch kein Speicherpfad" in d.ordner_info.text() or "noch nicht" in d.pfad.text()
assert not d.speichern() and "Angebotsnummer" in meldungen[-1]
d.nummer.setText("2026-88011")
assert d.speichern() is None and "nicht" in meldungen[-1]       # ohne Speicherpfad nichts gespeichert
d.pfad_aendern(str(haupt))
assert db.einstellung("ppease_ordner") == str(haupt) and "2026-88011" in d.ordner_info.text() and "in PPEASE anlegen" in d.ordner_info.text()
n = len(meldungen)
assert d.speichern() is None and "nichts gespeichert" in meldungen[-1] and len(meldungen) > n
assert not (haupt / "2026-88011").exists()                         # nie angelegt
(haupt / "2026-88011").mkdir()                                      # legt PPEASE an
d.aktualisieren()
assert "Vorhandener Ordner" in d.ordner_info.text()
d.liste.topLevelItem(1).setCheckState(0, Qt.Unchecked)
assert d.zahl.text().startswith(f"{len(d.dokumente) - 1} von")
b = d.speichern()
assert b.ok and len(b.gespeichert) == len(d.dokumente) - 1 and d.fortschritt.format() == "fertig", b
assert "Vorhandener Ordner" in d.ordner_info.text() and d.vorhanden_liste.count() == len(b.gespeichert)
assert pa.gemerkt(db, a)["nummer"] == "2026-88011" and pa.gemerkt(db, a)["ordner"] == str(haupt / "2026-88011")
assert "ppease_nummer" not in db.angebot(a)                       # keine neue Spalte
assert d.liste.topLevelItem(0).text(5) == pa.STATUS_TEXT[pa.GLEICH]
# geänderte Datei: Aktion „Ersetzen“ mit Rückfrage
p0 = d.dokumente[0].pfad
p0.write_bytes(p0.read_bytes() + b" neu")
d.aktualisieren()
assert d.liste.topLevelItem(0).text(5) == pa.STATUS_TEXT[pa.GEAENDERT]
assert d.liste.itemWidget(d.liste.topLevelItem(0), 6).currentData() == pa.ERSETZEN
d.nur_neue()
assert [x.gewaehlt for x in d.dokumente].count(True) == 2         # geänderte + nicht gespeicherte
n = len(meldungen)
b = d.speichern()
assert b.ersetzt and "ersetzen" in meldungen[n].lower() and "_Versionen" in meldungen[n]
# Zielordner ändern
c = d.liste.itemWidget(d.liste.topLevelItem(2), 4)
c.setCurrentIndex(c.findData(pa.SONSTIGE))
assert d.dokumente[2].kategorie == pa.SONSTIGE and d.liste.topLevelItem(2).text(5) in (
    pa.STATUS_TEXT[pa.SCHON], pa.STATUS_TEXT[pa.NEU])
# Ziehen & Ablegen, Ablage prüfen
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(str(extra / "Foto.jpg"))])
vorher = len(d.dokumente)
d.dropEvent(QDropEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
assert len(d.dokumente) == vorher + 1 and d.dokumente[-1].quelle == pa.Q_EXTERN
assert d.hinzufuegen([extra / "Foto.jpg"]) == 0                    # nicht doppelt
(d.ordner / "01_Angebot" / ("rest.pdf" + pa.TEIL)).write_bytes(b"x")
text = d.ablage_pruefen()
assert "Zwischendatei" in text and "Schreibrechte vorhanden" in text
# nochmal öffnen: Nummer kommt aus dem Angebot
d2 = fenster.ppease_ablage(db.angebot(a))
assert d2.nummer.text() == "2026-88011" and d2.vorhanden
# Übersicht: Kontextmenü, ohne Angebot
d3 = fenster.ppease_ablage({})
assert d3.angebotsordner is None and not d3.dokumente and "Kein Angebot" in d3.hinweis.text()
assert sorted(g.title() for g in d.findChildren(QGroupBox)) == ["1  Angebotszuordnung", "2  Dokumentenauswahl",
                                                        "3  Speicherübersicht", "4  Aktionen"]
ok("P9 Fenster: Menü, vier Bereiche, Status/Zielordner/Aktion, Speichern, Nummer am Angebot, Pfad, Prüfen, Ziehen")
print("Alle Prüfungen bestanden.")
