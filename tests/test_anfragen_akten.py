"""Anfragenverwaltung, Paket 1 (Patrick 12./13.11.2026): Akten mit Verlauf, Doppel-Schutz, Übernahme durch genau
einen Mitarbeiter (auch bei 8 gleichzeitig), Zuweisen, Bearbeiter ändern, Priorität, Notiz, Erledigen, Wieder öffnen,
Zurückgeben, Zählerleiste, Suche, Mitarbeiter-Übersicht; Eingang aus dem Anfrage-Ordner (Mail mit STEP, Nachtrag),
Seite „Anfragen“: Übernehmen legt die Originale weg, Kalkulieren erstellt ein Angebot und verknüpft es, Erledigt
bleibt aufrufbar. Nur erfundene Testmails, keine Kundendaten.

Aufruf: python tests/test_anfragen_akten.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import mail_testdateien  # noqa: E402
from rohrlaser import anfragen  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


T0 = datetime.datetime(2026, 11, 13, 8, 0)


def t(minuten):
    return T0 + datetime.timedelta(minutes=minuten)


tmp = Path(tempfile.mkdtemp())
quelle = tmp / "quelle"
quelle.mkdir()
(quelle / "a.step").write_text("ISO-10303-21; Teil A")
(quelle / "z.pdf").write_bytes(b"%PDF-1.4 Zeichnung")
(quelle / "setup.exe").write_bytes(b"MZ")
wurzel = tmp / "gemeinsam" / ak.ORDNER
pb = ak.OrdnerAblage(wurzel, "PB", "PC1")
mk = ak.OrdnerAblage(wurzel, "MK", "PC2")

# ------------------------------------------------------------------ Anlegen, Doppel-Schutz
kopf = dict(quelle="ordner", absender="einkauf@kunde-a.example", absender_name="Einkauf Kunde A",
            betreff="Anfrage Rahmen 40x40", kurz="Bitte um Angebot für 50 Stück", eingang=t(0), kundennr="10001")
a1, neu = pb.anlegen(kopf, [quelle / "a.step", quelle / "z.pdf", quelle / "setup.exe"], "schluessel1", jetzt=t(1))
assert neu and a1.nr == "A-2026-00001" and a1.status == ak.NEU, a1
a1b, neu = mk.anlegen(kopf, [quelle / "a.step"], "schluessel1", jetzt=t(2))
assert not neu and a1b.nr == a1.nr
a2, neu = mk.anlegen(dict(kopf, betreff="Anfrage Konsole"), [quelle / "a.step"], "schluessel2", jetzt=t(3))
assert neu and a2.nr == "A-2026-00002"
assert [a.nr for a in pb.alle()] == ["A-2026-00001", "A-2026-00002"]
d = {x["name"]: x for x in a1.dateien()}
assert d["a.step"]["art"] == "step" and d["z.pdf"]["art"] == "pdf" and len(d["a.step"]["sha256"]) == 64
assert d["setup.exe"]["warnung"] and (a1.pfad / ak.DATEIEN / "a.step").read_text() == "ISO-10303-21; Teil A"
k = json.loads((a1.pfad / ak.KOPF).read_text(encoding="utf-8"))
assert k["eingang"] == "2026-11-13T08:00:00" and k["absender"] == "einkauf@kunde-a.example"
ok("Akte mit Nummer A-2026-00001, Kopie der Dateien mit SHA-256, derselbe Schlüssel ergibt keine zweite Akte")

# ------------------------------------------------------------------ Übernehmen: genau einer gewinnt
gewinner, verlierer = [], []
sperre = threading.Barrier(8)


def versuch(k):
    abl = ak.OrdnerAblage(wurzel, k)
    akte = abl.lesen(a2.nr)
    sperre.wait()
    try:
        abl.uebernehmen(akte, jetzt=t(10))
        gewinner.append(k)
    except ak.SchonUebernommen as e:
        verlierer.append((k, e.kuerzel))


laeufe = [threading.Thread(target=versuch, args=(f"M{i}",)) for i in range(8)]
for x in laeufe:
    x.start()
for x in laeufe:
    x.join()
assert len(gewinner) == 1 and len(verlierer) == 7, (gewinner, verlierer)
assert all(v[1] == gewinner[0] for v in verlierer), verlierer
a2 = pb.lesen(a2.nr)
assert a2.status == ak.BEARBEITUNG and a2.bearbeiter == gewinner[0] and a2.stand["uebernommen_am"]
try:
    pb.uebernehmen(a2)
    raise AssertionError("zweite Übernahme")
except ak.SchonUebernommen as e:
    assert gewinner[0] in str(e)
ok(f"8 Arbeitsplätze übernehmen gleichzeitig: genau einer ({gewinner[0]}), die anderen sehen ihn")

# ------------------------------------------------------------------ Ablauf mit Verlauf
a1 = pb.zuweisen(a1, "MK", jetzt=t(20))
assert a1.status == ak.NEU and a1.stand["zugewiesen"] == "MK"
assert ak.zaehlen(pb.alle(), "MK")["meine"] == 1
a1 = mk.uebernehmen(a1, jetzt=t(30))
assert a1.bearbeiter == "MK" and a1.stand["zugewiesen"] == "" and a1.stand["uebernommen_am"] == "2026-11-13T08:30:00"
a1 = pb.prioritaet(a1, "eilt", jetzt=t(31))
a1 = mk.notiz(a1, "Werkstoff beim Kunden erfragt", jetzt=t(32))
a1 = mk.bearbeitungsstand(a1, "Rückfrage Werkstoff offen", jetzt=t(33))
a1 = pb.bearbeiter_aendern(a1, "PB", jetzt=t(40))
assert a1.bearbeiter == "PB" and a1.prioritaet == "eilt" and a1.stand["stand"] == "Rückfrage Werkstoff offen"
assert [n["text"] for n in a1.stand["notizen"]] == ["Werkstoff beim Kunden erfragt"]
a1 = pb.angebot_verknuepfen(a1, "2026-00042", jetzt=t(50))
a1 = pb.erledigen(a1, jetzt=t(60))
assert a1.status == ak.ERLEDIGT and a1.stand["erledigt_von"] == "PB" and a1.stand["angebote"] == ["2026-00042"]
try:
    pb.erledigen(a1)
    raise AssertionError("zweimal erledigt")
except ak.AblageFehler:
    pass
assert not hasattr(pb, "loeschen") and not hasattr(ak, "loeschen")
a1 = pb.wieder_oeffnen(a1, jetzt=t(70))
assert a1.status == ak.BEARBEITUNG and a1.stand["angebote"] == ["2026-00042"]
a1 = pb.zurueckgeben(a1, jetzt=t(80))
assert a1.status == ak.NEU and a1.stand["generation"] == 2
a1 = mk.uebernehmen(a1, jetzt=t(90))
assert a1.bearbeiter == "MK" and (a1.pfad / "uebernahme_2.sperre").exists()
a1 = mk.erledigen(a1, jetzt=t(120))
dateien = sorted(p.name for p in a1.pfad.glob("verlauf_*.jsonl"))
assert dateien == ["verlauf_MK.jsonl", "verlauf_PB.jsonl"], dateien
texte = [ak.verlauf_text(e) for e in sorted(a1.verlauf, key=lambda e: e["zeit"])]
assert texte[0].startswith("13.11.2026 08:01  PB  Eingegangen (Anfrage-Ordner)"), texte[0]
assert any("Priorität: Normal → Eilt" in x for x in texte) and any("Bearbeiter geändert: MK → PB" in x for x in texte)
ok("Zuweisen, Übernehmen, Priorität, Notiz, Stand, Bearbeiter ändern, Angebot, Erledigt, Wieder öffnen, "
   "Zurückgeben: alles im Verlauf je Mitarbeiter, Löschen gibt es nicht")

# widersprüchlicher Verlauf (z. B. Datei von Hand kopiert): zweites „übernommen“ zählt nicht
s = ak.stand_aus_verlauf([dict(zeit="2026-11-13T09:00:00", kuerzel="A", aktion=ak.UEBERNOMMEN, neu="A"),
                          dict(zeit="2026-11-13T09:00:05", kuerzel="B", aktion=ak.UEBERNOMMEN, neu="B")])
assert s["bearbeiter"] == "A"
ok("Stand aus dem Verlauf: ein späteres zweites „übernommen“ zählt nicht")

# ------------------------------------------------------------------ Liste, Suche, Mitarbeiter
alle = pb.alle()
z = ak.zaehlen(alle, "MK")
assert z == {ak.NEU: 0, ak.BEARBEITUNG: 1, ak.ERLEDIGT: 1, "meine": 0} or z["erledigt"] == 1, z
assert [a.nr for a in ak.filtern(alle, ak.ERLEDIGT)] == ["A-2026-00001"]
assert [a.nr for a in ak.filtern(alle, None, text="konsole")] == ["A-2026-00002"]
assert [a.nr for a in ak.filtern(alle, None, text="2026-00042")] == ["A-2026-00001"]
assert [a.nr for a in ak.filtern(alle, None, text="z.pdf rahmen")] == ["A-2026-00001"]
assert ak.filtern(alle, None, text="gibtsnicht") == []
m = ak.mitarbeiter(alle)
assert m["MK"]["erledigt"] == 1 and m["MK"]["std_bearbeitung"] == 0.5, m
assert ak.dauer_text(0.5) == "30 min" and ak.dauer_text(3) == "3,0 h" and ak.dauer_text(72) == "3,0 Tage"
ok("Zähler, Ordner, Suche über Text/Datei/Angebot, Mitarbeiter mit Bearbeitungsdauer")

# Arbeitskopie für „Kalkulieren“: ohne ausführbare Datei, Akte bleibt vollständig
arbeit = ak.arbeitskopie(pb.lesen("A-2026-00001"), jetzt=t(200))
assert sorted(p.name for p in arbeit.dateien) == ["a.step", "z.pdf"] and [p.name for p in arbeit.step] == ["a.step"]
assert (a1.pfad / ak.DATEIEN / "setup.exe").exists()
ok("Arbeitskopie: ausführbare Dateien bleiben draußen, die Akte behält alle Dateien")

# ------------------------------------------------------------------ Eingang aus dem Anfrage-Ordner
eingang = tmp / "Eingang"
eingang.mkdir()
alt = (datetime.datetime.now() - datetime.timedelta(minutes=30)).timestamp()
m1 = eingang / "Anfrage Halter.eml"
m1.write_bytes(mail_testdateien.eml("Anfrage Halter 2026-77", "Bitte 20 Stück anbieten.\nGruß", "Max Muster",
                                    "max@muster-metall.example", datetime.datetime(2026, 11, 13, 7, 15),
                                    [("halter.step", b"ISO-10303-21; Halter")]))
os.utime(m1, (alt, alt))
liste = anfragen.suchen(eingang)
assert len(liste) == 1
abl = ak.OrdnerAblage(tmp / "akten2", "PB")
erfasst = ak.aus_ordner(abl, liste)
assert len(erfasst) == 1
akte = next(iter(erfasst.values()))
assert akte.kopf["absender"] == "max@muster-metall.example" and akte.betreff == "Anfrage Halter 2026-77"
assert "20 Stück" in akte.kopf["kurz"] and akte.eingang == datetime.datetime(2026, 11, 13, 7, 15)
assert ak.aus_ordner(abl, anfragen.suchen(eingang)) and len(abl.alle()) == 1       # zweiter Blick: keine zweite Akte
nachtrag = eingang / "AW Anfrage Halter.eml"
nachtrag.write_bytes(mail_testdateien.eml("AW: Anfrage Halter 2026-77", "Anbei noch die Zeichnung.", "Max Muster",
                                          "max@muster-metall.example", datetime.datetime(2026, 11, 13, 7, 40),
                                          [("halter.pdf", b"%PDF Zeichnung")]))
os.utime(nachtrag, (alt, alt))
liste = anfragen.suchen(eingang)
assert len(liste) == 1 and len(liste[0].dateien) == 2, liste
ak.aus_ordner(abl, liste)
akte = abl.alle()[0]
namen = sorted(d["name"] for d in akte.dateien())
assert len(abl.alle()) == 1 and namen == ["AW Anfrage Halter.eml", "Anfrage Halter.eml", "halter.pdf", "halter.step"], namen
d = {x["name"]: x for x in akte.dateien()}
assert d["halter.step"]["aus_mail"] == "Anfrage Halter.eml" and d["halter.step"]["pfad"].read_bytes() == \
    b"ISO-10303-21; Halter"
ok("Anfrage-Ordner: Mail mit STEP wird einmal zur Akte (Absender, Betreff, Eingang, Kurztext), Nachtrag kommt dazu, "
   "Anhänge der Mails ausgepackt zum Ansehen")

# Anhang mit ausführbarer Datei: nur genannt, nicht gespeichert; Logo (kleines Bild) fehlt
m3 = quelle / "boese.eml"
m3.write_bytes(mail_testdateien.eml("Rechnung", "siehe Anhang", "X", "x@unbekannt.example", None,
                                    [("rechnung.exe", b"MZ..."), ("logo.png", b"PNG klein"), ("teil.step", b"S")]))
a3, _ = abl.anlegen(dict(quelle="ordner", betreff="Rechnung"), [m3], "boese")
d = {x["name"]: x for x in a3.dateien()}
assert d["rechnung.exe"].get("gesperrt") and not d["rechnung.exe"]["pfad"].exists() and "logo.png" not in d
arbeit = ak.arbeitskopie(a3)
assert [p.name for p in arbeit.dateien] == ["boese.eml"] and arbeit.step_anzahl() == 1
ok("Ausführbarer Anhang wird nur genannt, nie gespeichert; Kalkulieren nimmt die Mail (STEP darin)")

# ------------------------------------------------------------------ Seite „Anfragen“ im Programm
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
o2 = tmp / "Eingang2"
o2.mkdir()
m2 = o2 / "Anfrage Winkel.eml"
m2.write_bytes(mail_testdateien.eml("Anfrage Winkel", "Bitte 5 Stück Winkel anbieten.", "Erika Beispiel",
                                    "erika@beispiel-bau.example", datetime.datetime(2026, 11, 12, 15, 0),
                                    [("winkel.step", b"ISO-10303-21; Winkel")]))
os.utime(m2, (alt, alt))
db.einstellung_setzen(anfragen.EINSTELLUNG, str(o2))
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
karte = fenster.start.anfragen
karte.neu_laden(erzwingen=True)
seite.neu_laden()
assert fenster.reiter.indexOf(seite) >= 0 and seite.zaehler["neu"].text().endswith("1"), seite.zaehler["neu"].text()
assert seite.tabelle.rowCount() == 1 and seite.tabelle.item(0, 2).text() == "Anfrage Winkel"
assert ak.wurzel(db) == tmp / "prog" / ak.ORDNER
nr = seite.akten[0].nr
assert seite.waehlen(nr) is not None and "Bitte 5 Stück" in seite.inhalt.toPlainText()
assert seite.k_uebernehmen.isVisibleTo(seite) and not seite.k_erledigt.isVisibleTo(seite)
ok("Seite Anfragen: Zähler, Liste, Lesebereich mit Mailtext; Akten neben der Datendatei ohne gemeinsamen Ordner")

seite.prioritaet("hoch")
seite.notiz("Kunde ruft morgen an")
a = seite.uebernehmen()
assert a is not None and a.status == ak.BEARBEITUNG and a.bearbeiter == "PB"
assert seite.ordner == ak.BEARBEITUNG and seite.zaehler["in_bearbeitung"].text().endswith("1")
assert not m2.exists() and (o2 / ".uebernommen" / nr / "Anfrage Winkel.eml").exists()
karte.neu_laden(erzwingen=True)
assert karte.liste.count() == 0
ok("Übernehmen mit einem Klick: In Bearbeitung, Original aus dem Anfrage-Ordner weggelegt (nichts gelöscht)")

importe = []


def step_importieren(self, dateien=None, *a, **kw):
    importe.append(dateien)
    return {}


AngebotSeite.step_importieren = step_importieren
vorher = len(db.angebote())
angebot = seite.kalkulieren(kundennr="10417")
assert angebot is not None and len(db.angebote()) == vorher + 1, importe
nummer = angebot.kopf["nummer"]
a = seite.akte(nr)
assert a.stand["angebote"] == [nummer], a.stand
assert db.zusatz(angebot.id, "anfrage_akte") == nr, db.zusatz(angebot.id)
assert importe and Path(importe[-1][0]).name == "winkel.step"
assert (a.pfad / ak.DATEIEN / "Anfrage Winkel.eml").exists() and not list(a.pfad.glob("_arbeit_*"))
assert nummer in seite.inhalt.toPlainText()
ok("Kalkulieren: neues Angebot aus der STEP der Anfrage, ohne neues Hochladen, Anfrage und Angebot verknüpft")

seite.erledigen()
a = seite.akte(nr)
assert a.status == ak.ERLEDIGT
seite.ordner_waehlen(ak.ERLEDIGT)
assert seite.tabelle.rowCount() == 1 and seite.zaehler["erledigt"].text().endswith("1")
d = seite.mitarbeiter_zeigen()
assert d.tabelle.rowCount() == 1 and d.tabelle.item(0, 2).text() == "1"
seite.wieder_oeffnen()
assert seite.akte(nr).status == ak.BEARBEITUNG and seite.akte(nr).stand["angebote"] == [nummer]
ok("Erledigt: bleibt aufrufbar mit Angebot, Mitarbeiter-Übersicht, Wieder öffnen")

db.einstellung_setzen(ak.EINSTELLUNG, "nein")
assert not ak.aktiv(db)
print("Alle Tests bestanden.")
