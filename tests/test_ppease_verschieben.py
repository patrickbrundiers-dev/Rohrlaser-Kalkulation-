"""PPEASE-Ablage verschiebt statt zu kopieren (Patrick 26.11.2026: „Msg-Datei und alles, was darin enthalten ist, plus
die Kalkulations-PDF bzw. Ordner Angebotsakte soll in den PPEASE-Angebotsordner verschoben werden … ich möchte keine
doppelten Daten“, vorerst nur von Hand).

- V1 Verschieben: Mail, Anhänge, STEP, DXF und Dokumente der Angebotsakte liegen danach nur noch im PPEASE-Ordner;
     Programmdateien (JSON der Akte, Zwischenspeicher, Messungen) bleiben unverändert am alten Platz; ablage.json merkt
     den alten Pfad, wo() findet jede Datei wieder; Angebotsakte-Menü und STEP der Position finden sie
- V2 Sicherheit: gesperrtes Original bleibt (Kopie geprüft), nächstes Mal wird es entfernt; Kopierfehler/Netzwerk weg:
     Original bleibt; Zieldatei mit anderem Inhalt: Original bleibt (Überspringen); Datei im Zielordner selbst wird nie
     gelöscht; Sperre eines Kollegen blockiert
- V3 Anfrage-Akte: nach dem Verschieben zeigt die Akte ihre Dateien am neuen Ort (Kopf und Verlauf bleiben), das
     Fenster bietet sie nicht noch einmal an
- V4 Fenster: Vorgabe Verschieben, Rückfrage, Liste danach ohne die verschobenen Dateien, Merker je Arbeitsplatz

Aufruf: python tests/test_ppease_verschieben.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import ppease_ablage as pa  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())


def angebotsordner(name):
    o = tmp / "Ablage" / name
    for rel, inhalt in (("Angebotsakte/PDF/Angebot_2026-00042_Gesamt.pdf", b"%PDF gesamt"),
                        ("Angebotsakte/PDF/Angebot_2026-00042_Kunde.pdf", b"%PDF kunde"),
                        ("Angebotsakte/Schnittschemata/Angebot_2026-00042_Schnittschema.pdf", b"%PDF schnitt"),
                        ("Angebotsakte/Kalkulationsdaten/akte.json", b'{"versionen": []}'),
                        ("Angebotsakte/Kalkulationsdaten/kalkulation_V1.json", b"{}"),
                        ("Angebotsakte/Technische_Daten/Pos_10.png", b"png"),
                        ("STEP/Rahmen.stp", b"ISO-10303 rahmen"), ("STEP/Rahmen.stp.teile.json", b"[]"),
                        ("Anfrage/Anfrage.msg", b"msg"), ("Anfrage/Kundenzeichnung.pdf", b"%PDF zeichnung"),
                        ("2026-00042 Abwicklung.dxf", b"0\nSECTION"), ("_messung/abc/ergebnis.json", b"{}")):
        (o / rel).parent.mkdir(parents=True, exist_ok=True)
        (o / rel).write_bytes(inhalt)
    return o


# ------------------------------------------------------------------ V1 Verschieben
assert pa.intern("x/Kalkulationsdaten/kalkulation_V1.json") and pa.intern("STEP/a.stp.teile.json")
assert pa.intern("Akte/_messung/abc/netz.bin") and pa.intern("~$Angebot.xlsx") and pa.intern("a.pdf.rl-teil")
assert pa.intern("Akte/_arbeit_20261126_101010/a.stp")
assert not pa.intern("Anfrage/Anfrage.msg") and not pa.intern("STEP/Rahmen.stp") and not pa.intern("a.pdf")
ang = angebotsordner("2026-00042 Müller")
haupt = tmp / "PPEASE"
ziel = haupt / "2026-44327"
ziel.mkdir(parents=True)
v = pa.Vorgaben(ordner=str(haupt))
dok = pa.dokumente_sammeln(ang)
intern = sorted(d.name for d in dok if d.intern)
assert intern == ["Rahmen.stp.teile.json", "ergebnis.json", "kalkulation_V1.json"], intern
assert all(not d.gewaehlt for d in dok if d.intern) and dok[-1].intern            # Programmdateien unten, nicht gewählt
bewegt = [d for d in dok if not d.intern]
b = pa.ablegen(v, ziel, dok, "PB", angebot="2026-00042", nummer="2026-44327", verschieben=True)
assert b.ok and len(b.verschoben) == len(bewegt) == 8 and not b.nicht_entfernt, b
for d in bewegt:
    assert not d.pfad.exists(), d.pfad                                              # echt verschoben
assert (ziel / "07_Kundenunterlagen/Anfrage.msg").read_bytes() == b"msg"
assert (ziel / "05_3D_Modelle/Rahmen.stp").read_bytes() == b"ISO-10303 rahmen"
assert (ziel / "01_Angebot/Angebot_2026-00042_Gesamt.pdf").read_bytes() == b"%PDF gesamt"
for rel in ("Angebotsakte/Kalkulationsdaten/akte.json", "Angebotsakte/Kalkulationsdaten/kalkulation_V1.json",
            "STEP/Rahmen.stp.teile.json", "_messung/abc/ergebnis.json"):
    assert (ang / rel).is_file(), rel                                               # Programmdaten bleiben
assert not list(ziel.rglob("*.json")) or all("_Protokoll" in p.parts for p in ziel.rglob("*.json"))
verz = pa.verzeichnis(ziel)
assert len(verz["verschoben"]) == 8 and all(e.get("verschoben") for e in verz["dateien"].values())
assert sum(e["aktion"] == "gespeichert" for e in pa.protokoll(ziel)) == 8
alt = ang / "STEP/Rahmen.stp"
assert pa.wo(None, None, alt, ordner=ziel) == ziel / "05_3D_Modelle/Rahmen.stp"
assert pa.wo(None, None, ang / "Angebotsakte/Kalkulationsdaten/akte.json", ordner=ziel) == \
    ang / "Angebotsakte/Kalkulationsdaten/akte.json"                                # liegt noch da
assert pa.wo(None, None, tmp / "anderswo/Rahmen.stp", ordner=ziel) == ziel / "05_3D_Modelle/Rahmen.stp"   # Name
assert pa.wo(None, None, tmp / "gibt_es_nicht.pdf", ordner=ziel) is None
# zweiter Lauf: nichts mehr zu verschieben, nichts doppelt
b2 = pa.ablegen(v, ziel, pa.dokumente_sammeln(ang), "PB", verschieben=True)
assert b2.ok and not b2.verschoben and not b2.gespeichert
ok("V1 Mail, Anhänge, STEP, DXF und Angebotsakte verschoben (Original weg), JSON/Messungen bleiben, wo() findet alles")

# ------------------------------------------------------------------ V2 Sicherheit
ang2 = angebotsordner("2026-00043 Meier")
ziel2 = haupt / "2026-44328"
ziel2.mkdir()
dok2 = [d for d in pa.dokumente_sammeln(ang2) if not d.intern]
gesperrt = ang2 / "Anfrage/Anfrage.msg"
echt_unlink = os.unlink


def unlink_gesperrt(p, *a, **k):
    if Path(p) == gesperrt:
        raise PermissionError(13, "Die Datei wird von einem anderen Prozess verwendet")
    return echt_unlink(p, *a, **k)


os.unlink = unlink_gesperrt
try:
    b = pa.ablegen(v, ziel2, dok2, "PB", verschieben=True)
finally:
    os.unlink = echt_unlink
assert b.ok and len(b.verschoben) == 7 and [n for n, _ in b.nicht_entfernt] == ["Anfrage.msg"], b
assert gesperrt.is_file() and (ziel2 / "07_Kundenunterlagen/Anfrage.msg").read_bytes() == b"msg"   # nichts verloren
b = pa.ablegen(v, ziel2, [d for d in pa.dokumente_sammeln(ang2) if not d.intern], "PB", verschieben=True)
assert b.ok and len(b.verschoben) == 1 and not gesperrt.exists() and not b.gespeichert, b        # nachgeholt
assert str(gesperrt) in pa.verzeichnis(ziel2)["verschoben"]
# Kopierfehler (Netzwerk weg) mitten im Verschieben: Original bleibt
ang3 = angebotsordner("2026-00044 Schulz")
ziel3 = haupt / "2026-44329"
ziel3.mkdir()
dok3 = [d for d in pa.dokumente_sammeln(ang3) if not d.intern]
echt = pa._sicher_kopieren
zaehler = {"n": 0}


def kaputt(q, z):
    zaehler["n"] += 1
    if zaehler["n"] == 3:
        raise OSError("Der Netzwerkpfad wurde nicht gefunden")
    return echt(q, z)


pa._sicher_kopieren = kaputt
try:
    b = pa.ablegen(v, ziel3, dok3, "PB", verschieben=True)
finally:
    pa._sicher_kopieren = echt
assert len(b.verschoben) == 7 and len(b.fehler) == 1 and b.fehler[0][0] == dok3[2].name, b
assert dok3[2].pfad.is_file()                                      # Original der fehlgeschlagenen Datei bleibt
for d in dok3:
    assert d.pfad.exists() or pa.wo(None, None, d.pfad, ordner=ziel3) is not None, d.name   # jede Datei auffindbar
# Ziel hat eine andere Datei gleichen Namens: Überspringen, Original bleibt
ang4 = angebotsordner("2026-00045 Kraus")
ziel4 = haupt / "2026-44330"
(ziel4 / "05_3D_Modelle").mkdir(parents=True)
(ziel4 / "05_3D_Modelle/Rahmen.stp").write_bytes(b"ISO-10303 ANDERER rahmen")
b = pa.ablegen(v, ziel4, [d for d in pa.dokumente_sammeln(ang4) if not d.intern], "PB", verschieben=True)
assert (ang4 / "STEP/Rahmen.stp").is_file() and (ziel4 / "05_3D_Modelle/Rahmen.stp").read_bytes() == \
    b"ISO-10303 ANDERER rahmen" and any(n == "Rahmen.stp" for n, _ in b.uebersprungen)
# Datei, die schon im Zielordner liegt, wird nie gelöscht
drin = pa.Dokument(ziel4 / "05_3D_Modelle/Rahmen.stp", pa.Q_ANFRAGE, pa.MODELL)
b = pa.ablegen(v, ziel4, [drin], "PB", verschieben=True)
assert (ziel4 / "05_3D_Modelle/Rahmen.stp").is_file() and not b.verschoben
# Kollege speichert gerade: nichts passiert
(ziel4 / pa.PROTOKOLL).mkdir(exist_ok=True)
(ziel4 / pa.PROTOKOLL / pa.SPERRE).write_text(json.dumps(dict(von="KO", platz="ANDERER-PC", pid=1,
                                                              zeit=datetime.datetime.now().isoformat())))
try:
    pa.ablegen(v, ziel4, [d for d in pa.dokumente_sammeln(ang4) if not d.intern], "PB", verschieben=True)
    raise AssertionError("Sperre ignoriert")
except pa.Gesperrt:
    pass
assert (ang4 / "STEP/Rahmen.stp").is_file()
pa.entsperren(ziel4)
ok("V2 Original erst nach geprüfter Kopie weg; gesperrt/Netzwerkfehler/anderer Inhalt: Original bleibt; Sperre hält")

# ------------------------------------------------------------------ V3 Anfrage-Akte und Fenster
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
db.einstellung_setzen("ablageordner", str(tmp / "Ablage2"))
db.einstellung_setzen("ppease_ordner", str(haupt))
a = db.angebot_neu(dict(nummer="2026-00050", kunde="Lang", maschine="T11"))
eingang = tmp / "Eingang"
eingang.mkdir()
(eingang / "Anfrage Lang.msg").write_bytes(b"msg lang")
(eingang / "Gestell.stp").write_bytes(b"ISO-10303 gestell")
abl = ak.ablage(db)
akte, neu = abl.anlegen(dict(betreff="Gestell", quelle="ordner"), [eingang / "Anfrage Lang.msg",
                                                                   eingang / "Gestell.stp"], "test-lang")
assert neu
db.zusatz_setzen(a, "anfrage_akte", akte.nr)
ordner = fenster.angebot_ordner(db.angebot(a))
akte_pdf = ordner / "Angebotsakte/PDF/Angebot_2026-00050_Gesamt.pdf"
akte_pdf.parent.mkdir(parents=True)
akte_pdf.write_bytes(b"%PDF gesamt lang")
(ordner / "Angebotsakte/Kalkulationsdaten").mkdir(parents=True)
(ordner / "Angebotsakte/Kalkulationsdaten/akte.json").write_text('{"versionen": []}', encoding="utf-8")
(haupt / "2026-44400").mkdir()
meldungen = []
d = fenster.ppease_ablage(db.angebot(a))
d.melden = lambda t, x: meldungen.append(x)
d.fragen = lambda t, x: meldungen.append(x) or True
assert d.verschieben.isChecked() and d.knopf_speichern.text() == "Dokumente verschieben"
assert {x.name for x in d.dokumente if not x.intern} == {"Angebot_2026-00050_Gesamt.pdf", "Anfrage Lang.msg",
                                                         "Gestell.stp"}, [x.name for x in d.dokumente]
d.nummer.setText("2026-44400")
d.aktualisieren()
b = d.speichern()
assert b is not None and b.ok and len(b.verschoben) == 3, (b, meldungen)
assert "verschoben" in meldungen[-1] and "bleiben" in meldungen[-1]                # Rückfrage mit Erklärung
assert not akte_pdf.exists() and (ordner / "Angebotsakte/Kalkulationsdaten/akte.json").is_file()
assert not any(not x.intern for x in d.dokumente)                                  # Liste ohne die verschobenen
akte = abl.neu_lesen(akte)
dateien = {x["name"]: x for x in akte.dateien()}
assert dateien["Gestell.stp"]["abgelegt"] and dateien["Gestell.stp"]["pfad"] == haupt / "2026-44400/05_3D_Modelle/Gestell.stp"
assert dateien["Anfrage Lang.msg"]["pfad"].read_bytes() == b"msg lang"
assert not (akte.pfad / ak.DATEIEN / "Gestell.stp").exists() and (akte.pfad / ak.KOPF).is_file()   # Kopf bleibt
assert any(e.get("aktion") == ak.ABGELEGT for e in akte.verlauf)
assert "PPEASE" in ak.verlauf_text([e for e in akte.verlauf if e.get("aktion") == ak.ABGELEGT][0])
# Angebotsakte-Menü findet das verschobene PDF, STEP der Position auch
from PySide6.QtWidgets import QMenu  # noqa: E402
from rohrlaser import akte_ausgabe  # noqa: E402
m = QMenu()
akte_ausgabe.menue_fuellen(m, fenster, db.angebot(a))
unter = m.actions()[0].menu()
assert unter.actions()[0].isEnabled()                                             # „Komplettes Dokument öffnen“
assert pa.wo(db, a, akte_pdf) == haupt / "2026-44400/01_Angebot/Angebot_2026-00050_Gesamt.pdf"
# nochmal öffnen: nichts mehr anzubieten, Akte-Dateien nicht doppelt, Kopieren-Merker je Platz
d2 = fenster.ppease_ablage(db.angebot(a))
assert not [x for x in d2.dokumente if not x.intern], [x.name for x in d2.dokumente]
d2.verschieben.setChecked(False)
assert db.einstellung("leiste_ppease_verschieben") is False
assert not fenster.ppease_ablage(db.angebot(a)).verschieben.isChecked()
ok("V3/V4 Fenster verschiebt nach Rückfrage, Anfrage-Akte zeigt den neuen Ort, Akte-Menü und wo() finden die Dateien")
print("Alle Prüfungen bestanden.")
