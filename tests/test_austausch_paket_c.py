"""Austauschordner 2.0, Paket C: Anbindung an die anderen Teile des Programms, Rechte, mehrere Benutzer.

- C1 Rechte des Austauschordners: Tabelle je Rolle in „Benutzer und Rollen“, Administrator immer alles, ohne Lesen
     kein anderes Recht; die Tabelle ist admin-geschützt (geht mit den Admin-Vorgaben an alle Plätze)
- C2 STEP-Viewer: „Im STEP-Viewer öffnen“ im Menü und im Infobereich, öffnet die Datei aus dem Austauschordner
- C3 LST/BPF neben der STEP gleichen Namens: „Zugehörige Programme“ im Infobereich, Klick wählt die Datei
- C4 „Dateien im Austausch“ bei Kunde, Angebot (auch PPEASE-Nummer im Pfad) und Auftrag
- C5 Outlook: Anhänge einer MSG/EML auspacken, gleicher Anhang nie doppelt, anderer gleichen Namens nie
     überschrieben, Zuordnung der Mail geht an die Anhänge, ausführbare Anhänge bleiben draußen
- C6 Mehrere Benutzer gleichzeitig: zwei Plätze laden je 25 Dateien zugleich hoch, nichts geht verloren
- C7 Netzwerkausfall: gemeinsamer Ordner mitten im Hochladen weg -> Meldung, keine halbe Datei unter echtem Namen;
     Ordner nicht erreichbar -> Seite bleibt bedienbar, Hochladen meldet den Fehler

Aufruf: python tests/test_austausch_paket_c.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import email.message
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import admin_schutz, admin_signatur, rollen  # noqa: E402
from rohrlaser import austausch_dateien as ad  # noqa: E402
from rohrlaser.austausch_seite import ZUGEORDNET  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.rollen_seite import RollenTeil  # noqa: E402

app = QApplication.instance() or QApplication([])
TMP = Path(tempfile.mkdtemp())
gemeinsam = TMP / "Gemeinsam"
gemeinsam.mkdir()


def ok(t):
    print("OK    ", t)


def platz(k, name):
    (TMP / k).mkdir(exist_ok=True)
    db = Datenbank(TMP / k / "rohrlaser.db")
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("teilen_ordner", str(gemeinsam))
    db.einstellung_setzen("ablageordner", str(TMP / k / "ablage"))
    return db


db = platz("PB", "Patrick")
db2 = platz("MK", "Max")
quelle = TMP / "quelle"
quelle.mkdir()


def datei(name, inhalt="x"):
    p = quelle / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(inhalt if isinstance(inhalt, bytes) else inhalt.encode())
    return p


STEP = "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"

# ------------------------------------------------------------------ C1 Rechte
assert "austausch_rechte" in admin_signatur.RECHTE
assert "austausch_rechte" in admin_schutz.einstellungen_geschuetzt(db)
assert ad.recht_setzen(db, "admin", ad.LESEN, False)            # Administrator darf immer alles
assert ad.recht_setzen(db, "chef", ad.LESEN, True) and ad.recht_setzen(db, "werkstatt", "fliegen", True)
assert ad.rechte(db)["werkstatt"] == (ad.LESEN, ad.HOCHLADEN)
assert ad.recht_setzen(db, "werkstatt", ad.LOESCHEN, True) == ""
assert set(ad.rechte(db)["werkstatt"]) == {ad.LESEN, ad.HOCHLADEN, ad.LOESCHEN}
assert ad.recht_setzen(db, "versand", ad.LESEN, False) == "" and ad.rechte(db)["versand"] == ()
assert ad.recht_setzen(db, "versand", ad.BEARBEITEN, True) == ""
assert set(ad.rechte(db)["versand"]) == {ad.LESEN, ad.BEARBEITEN}     # wer bearbeitet, muss sehen
rollen.benutzer_setzen(db, "PB", "Patrick", ["werkstatt"])
assert ad.darf(db, ad.LOESCHEN) and not ad.darf(db, ad.VERSCHIEBEN)
rollen.entfernen(db, "PB")
ad.rechte_vorgabe(db)
assert ad.rechte(db) == {r: tuple(v) for r, v in ad.RECHTE_VORGABE.items()}
meldungen = []
teil = RollenTeil(db, lambda t, fehler=False: meldungen.append((t, fehler)))
spalte = [a for a, _ in ad.AKTIONEN].index(ad.LOESCHEN)
zeile = [r for r, _ in rollen.ROLLEN].index("werkstatt")
it = teil.austausch.item(zeile, spalte)
assert it.checkState() == Qt.Unchecked and it.flags() & Qt.ItemIsEnabled
it.setCheckState(Qt.Checked)
assert ad.LOESCHEN in ad.rechte(db)["werkstatt"] and "Löschen erlaubt" in meldungen[-1][0]
admin = teil.austausch.item([r for r, _ in rollen.ROLLEN].index("admin"), spalte)
assert admin.checkState() == Qt.Checked and not admin.flags() & Qt.ItemIsEnabled
teil.schutz_setzen(True)                     # Seite gesperrt (Admin-Schutz): nichts änderbar
assert not teil.austausch.item(zeile, spalte).flags() & Qt.ItemIsEnabled and not teil.austausch_vorgabe()
teil.schutz_setzen(False)
assert teil.austausch_vorgabe() and ad.LOESCHEN not in ad.rechte(db)["werkstatt"]
assert teil.austausch.item(zeile, spalte).checkState() == Qt.Unchecked
ok("C1 Rechte je Rolle (Tabelle in Benutzer und Rollen), Administrator fest, admin-geschützt, Vorgabe")

# ------------------------------------------------------------------ Seite mit Dateien
f = Hauptfenster(db, stumm=True)
s = f.austausch
b = ad.hochladen(db, [datei("Halter.step", STEP), datei("Halter.lst", "LST"), datei("Halter_02.bpf", "BPF"),
                      datei("Halterung.lst", "andere"), datei("Rahmen.step", STEP)], ad.DATEIEN, erkennen=False)
assert b.ok and len(b.neu) == 5, b.text()

# ------------------------------------------------------------------ C2 STEP-Viewer
s.neu_laden(einlesen=True)
s.gehe("bereich", ad.DATEIEN, "")
e = s.waehlen("dateien:Halter.step")
assert e is not None and s.info.k_viewer.isVisibleTo(s.info)
texte = [x[0] for x in s.menue_aktionen([e]) if x]
assert "Im STEP-Viewer öffnen" in texte and "In Kalkulation übernehmen …" in texte
v = s.step_viewer()
assert v is not None and Path(v.pfad).name == "Halter.step" and v in f._step_viewer
v.close()
s.waehlen("dateien:Halter.lst")
assert not s.info.k_viewer.isVisibleTo(s.info) and s.step_viewer() is None
ok("C2 STEP-Datei im STEP-Viewer öffnen (Menü und Infobereich), nur für STEP")

# ------------------------------------------------------------------ C3 Zugehörige Programme
alle = s.alle_eintraege()
halter = next(x for x in alle if x.name == "Halter.step")
assert [x.name for x in ad.zugehoerige(alle, halter)] == ["Halter.lst", "Halter_02.bpf"]       # nicht Halterung
lst = next(x for x in alle if x.name == "Halter_02.bpf")
assert [x.name for x in ad.zugehoerige(alle, lst)] == ["Halter.step"]
assert ad.zugehoerige(alle, next(x for x in alle if x.name == "Rahmen.step")) == []
s.waehlen("dateien:Halter.step")
assert "Zugehörige Programme" in s.info.zugehoerig.text() and 'href="z:1"' in s.info.zugehoerig.text()
assert "_" not in s.info.zugehoerig.text().split('href="')[1].split('"')[0]        # QUrl: nie Unterstrich
s.info._zugehoerig_geklickt("z:1")
assert s.gewaehlt_eins().name == "Halter_02.bpf" and "Zugehörige STEP" in s.info.zugehoerig.text()
ok("C3 LST/BPF neben der STEP gleichen Namens, Klick wählt die Datei")

# ------------------------------------------------------------------ C4 Dateien im Austausch
ad.setzen(db, ["dateien:Halter.step"], kundennr="10077", angebot="2026-00122")
ad.setzen(db, ["dateien:Rahmen.step"], auftrag="A-2026-0042")
pp = gemeinsam / "Austausch" / "PPEASE 2026-44327"
pp.mkdir()
(pp / "Zeichnung.pdf").write_bytes(b"%PDF-1.4")
s.neu_laden(einlesen=True)
namen = sorted(e.name for e in f.austausch_zeigen(kundennr="10077"))
assert namen == ["Halter.step"] and s.ansicht[0] == ZUGEORDNET and f.reiter.currentWidget() is s
assert "Kunde 10077" in s.pfad_zeile.itemAt(0).widget().text()
assert sorted(e.name for e in f.austausch_zeigen(angebot=["2026-00122", "2026-44327"])) == ["Halter.step",
                                                                                         "Zeichnung.pdf"]
assert [e.name for e in f.austausch_zeigen(auftrag="A-2026-0042")] == ["Rahmen.step"]
assert f.austausch_zeigen() == [] and f.austausch_angebot({}) is None
kopf = dict(id=None, nummer="2026-00122", kundennr="10077", auftragsnr="A-2026-0042")
assert sorted(e.name for e in f.austausch_angebot(kopf)) == ["Halter.step", "Rahmen.step"]
s.suche.setText("Rahmen")
s.filter_anwenden()
assert s.ansicht[0] == "alle"           # Suche verlässt die Ansicht und sucht überall
s.suche.setText("")
db.einstellung_setzen("austausch_aktiv", "nein")
assert f.austausch_zeigen(kundennr="10077") is None
db.einstellung_setzen("austausch_aktiv", "ja")
ok("C4 Dateien im Austausch zu Kunde, Angebot (mit PPEASE-Nummer im Pfad) und Auftrag")

# ------------------------------------------------------------------ C5 Outlook-Anhänge
m = email.message.EmailMessage()
m["From"] = "Einkauf <einkauf@kunde.example>"
m["Subject"] = "Anfrage Halter"
m.set_content("Bitte anbieten.")
m.add_attachment(STEP.encode(), maintype="application", subtype="octet-stream", filename="Teil A.step")
m.add_attachment(b"%PDF-1.4 a", maintype="application", subtype="pdf", filename="Zeichnung A.pdf")
m.add_attachment(b"MZ", maintype="application", subtype="octet-stream", filename="rechnung.exe")
(quelle / "Anfrage.eml").write_bytes(bytes(m))
b = ad.hochladen(db, [quelle / "Anfrage.eml"], ad.DATEIEN, "Mails", erkennen=False)
assert b.ok
ad.setzen(db, ["dateien:Mails/Anfrage.eml"], kundennr="10077", anfrage="ANF-77")
s.gehe("bereich", ad.DATEIEN, "Mails")
s.neu_laden(einlesen=True)
mail_e = s.waehlen("dateien:Mails/Anfrage.eml")
assert "Anhänge auspacken" in [x[0] for x in s.menue_aktionen([mail_e]) if x]
berichte = s.anhaenge_auspacken()
assert len(berichte) == 1 and sorted(berichte[0].neu) == ["dateien:Mails/Teil A.step", "dateien:Mails/Zeichnung A.pdf"]
assert any("rechnung.exe" in n for n, _ in berichte[0].uebersprungen)
assert not (gemeinsam / "Austausch" / "Mails" / "rechnung.exe").exists()
mm = ad.meta(db, "dateien:Mails/Teil A.step")
assert mm["kundennr"] == "10077" and mm["anfrage"] == "ANF-77" and mm["hochgeladen_von"] == "PB"
assert any("Anhang aus Anfrage.eml" in v["text"] for v in ad.verlauf(db, "dateien:Mails/Teil A.step"))
b = ad.anhaenge_auspacken(db, "dateien:Mails/Anfrage.eml")         # zweites Mal: nichts doppelt
assert not b.neu and not b.umbenannt and len(b.uebersprungen) == 3, b
(gemeinsam / "Austausch" / "Mails" / "Teil A.step").write_text("vom Kollegen geändert")
b = ad.anhaenge_auspacken(db, "dateien:Mails/Anfrage.eml")
assert [d for _, d in b.umbenannt] == ["dateien:Mails/Teil A (2).step"]
assert (gemeinsam / "Austausch" / "Mails" / "Teil A.step").read_text() == "vom Kollegen geändert"   # nie überschrieben
try:
    ad.anhaenge_auspacken(db, "dateien:Halter.step")
    raise AssertionError("STEP hat keine Anhänge")
except ad.AustauschFehler:
    pass
rollen.benutzer_setzen(db, "PB", "Patrick", ["werkstatt"])
db.einstellung_setzen(ad.RECHTE, {"werkstatt": ["lesen"]})
try:
    ad.anhaenge_auspacken(db, "dateien:Mails/Anfrage.eml")
    raise AssertionError("ohne Recht Hochladen kein Auspacken")
except ad.AustauschFehler as fehler:
    assert "Berechtigung" in str(fehler)
rollen.entfernen(db, "PB")
db.einstellung_setzen(ad.RECHTE, None)
ok("C5 Outlook-Anhänge auspacken: sicher, ohne Doppel, ohne Überschreiben, Zuordnung der Mail übernommen")

# ------------------------------------------------------------------ C6 zwei Plätze gleichzeitig
fehler_ = []


def lauf(d, k):
    try:
        ql = [datei(f"{k}/Teil_{k}_{i:02d}.step", STEP + k * i) for i in range(25)]
        b = ad.hochladen(d, ql, ad.DATEIEN, "Gleichzeitig", erkennen=False)
        if not b.ok or len(b.neu) != 25:
            fehler_.append(b.text())
    except Exception as x:       # noqa: BLE001
        fehler_.append(repr(x))


t1, t2 = threading.Thread(target=lauf, args=(db, "PB")), threading.Thread(target=lauf, args=(db2, "MK"))
t1.start()
t2.start()
t1.join(120)
t2.join(120)
assert not fehler_, fehler_
ziel = gemeinsam / "Austausch" / "Gleichzeitig"
dateien = sorted(p.name for p in ziel.iterdir() if p.is_file())
assert len(dateien) == 50 and not any(n.endswith(ad.TEIL) for n in dateien), dateien
assert (ziel / "Teil_MK_03.step").read_text() == STEP + "MK" * 3
assert not ad.laufende_uploads(db)
ok("C6 zwei Plätze laden gleichzeitig je 25 Dateien hoch: alle 50 vollständig, keine Zwischendateien")

# ------------------------------------------------------------------ C7 Netzwerkausfall
gross = datei("Gross.step", b"x" * (3 * ad.BLOCK + 10))
weg = TMP / "Gemeinsam_weg"
w = ad.wurzeln(db)


def ausfall(n, _g, _name):
    if n > ad.BLOCK and gemeinsam.exists():
        gemeinsam.rename(weg)             # Netzlaufwerk fällt mitten im Kopieren weg


b = ad.hochladen(db, [gross], ad.DATEIEN, "", fortschritt=ausfall, erkennen=False, w=w)
assert b.fehler and not b.neu, b.text()
weg.rename(gemeinsam)
assert not (gemeinsam / "Austausch" / "Gross.step").exists()            # nichts Halbes unter echtem Namen
for p in ad.reste(db, alter_s=-1):
    assert p.name.endswith(ad.TEIL)
ad.reste_entfernen(db)
b = ad.hochladen(db, [gross], ad.DATEIEN, erkennen=False)                # wieder da: geht
assert b.ok and (gemeinsam / "Austausch" / "Gross.step").stat().st_size == 3 * ad.BLOCK + 10
sperre = TMP / "keinnetz.txt"
sperre.write_text("kein Ordner")
db.einstellung_setzen("teilen_ordner", str(sperre / "Server" / "Freigabe"))   # nicht erreichbar, nicht anlegbar
s.neu_laden(einlesen=True)
s.gehe("bereich", ad.DATEIEN, "")
try:
    ad.hochladen(db, [datei("Neu.pdf", b"%PDF")], ad.DATEIEN, erkennen=False)
    raise AssertionError("nicht erreichbarer Ordner muss gemeldet werden")
except ad.AustauschFehler as fehler:
    assert "nicht erreichbar" in str(fehler)
gemeldet = []
s._fehler = lambda x: gemeldet.append(str(x))
assert s.hochladen([str(quelle / "Neu.pdf")], ad.DATEIEN, "") is None and "nicht erreichbar" in gemeldet[-1]
del s._fehler
db.einstellung_setzen("teilen_ordner", str(gemeinsam))
s.neu_laden(einlesen=True)
assert any(e.name == "Gross.step" for e in s.alle_eintraege())
ok("C7 Netzwerkausfall: Meldung statt halber Datei, Seite bleibt bedienbar, danach geht alles wieder")

f.close()
shutil.rmtree(TMP, ignore_errors=True)
print("Alle Tests Austauschordner Paket C bestanden.")
