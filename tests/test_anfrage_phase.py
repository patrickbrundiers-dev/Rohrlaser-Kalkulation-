"""Phasen bis zum Auftrag, Outlook-Ordner je Phase, Bearbeiter-Vorschlag, zuverlässiger Abruf (Patrick 20.11.2026,
Plan K6–K8, „Alles einbauen“).

  C1 Phase aus Status, Rückfrage, Angebot, Auftrag; von Hand gesetzte Phase gilt, bis der Ablauf weiter ist
  C2 Phase aus verknüpften Angeboten und Aufträgen (beauftragt, in Produktion, ausgeliefert)
  C3 Bearbeiter-Vorschlag mit Gründen (Kundenstamm, frühere Anfragen, Sachgebiet, offene Anfragen); automatisch
     zugewiesen nur sichere Vorschläge und nur einmal
  C4 Outlook-Ordner je Phase: Programm verschiebt beim Phasenwechsel, Verschieben in Outlook setzt die Phase
     (steht im Verlauf), Nicht relevant = aussortiert; ohne Phasen-Ordner alles wie bisher
  C5 Zuverlässig: fehlgeschlagene Mail beim nächsten Abruf, dann nach 5/30 Minuten, „Erneut verarbeiten“, Abrufstatus mit Outlook nicht
     erreichbar
  C6 Seite „Anfragen“: Phase und Vorschlag rechts, Phase ändern, Statuszeile, Phasen-Ordner im Fenster „Outlook …“

Aufruf: python tests/test_anfrage_phase.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import mail_testdateien as t  # noqa: E402
from outlook_nachbau import Outlook  # noqa: E402
from rohrlaser import anfrage_phase as ph  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import auftraege as au  # noqa: E402
from rohrlaser import outlook_anfragen as ol  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
D = datetime.datetime(2026, 11, 20, 8, 0)
abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")


def akte(betreff, kunde="", n=[0], **kopf):
    n[0] += 1
    k = dict(quelle="ordner", betreff=betreff, eingang=D + datetime.timedelta(minutes=n[0]), **kopf)
    if kunde:
        k["kundennr"] = kunde
    a, _ = abl.anlegen(k, [], f"t{n[0]}", jetzt=D)
    return a


# ---------------------------------------------------------------------------------------------- C1
a = akte("Anfrage Halter")
assert ph.phase(a) == ph.NEU
a = abl.uebernehmen(a, jetzt=D)
assert ph.phase(a) == ph.BEARBEITUNG
a = abl.phase_setzen(a, ph.PRUEFUNG, jetzt=D)
assert ph.phase(a) == ph.PRUEFUNG and "Technische Prüfung" in ak.verlauf_text(a.verlauf[-1])
a = abl.rueckfrage(a, "Welche Wandstärke?", jetzt=D)
assert ph.phase(a) == ph.RUECKFRAGE                     # Rückfrage ist weiter als Technische Prüfung
a = abl.angebot_verknuepfen(a, "2026-00999", jetzt=D)
assert ph.phase(a) == ph.ANGEBOT
assert ph.phase(a, ph.PRODUKTION) == ph.PRODUKTION
a = abl.phase_setzen(a, "", jetzt=D)
assert ph.phase(a) == ph.ANGEBOT and "automatisch" in ak.verlauf_text(a.verlauf[-1])
a = abl.erledigen(a, jetzt=D)
assert ph.phase(a, ph.PRODUKTION) == ph.ERLEDIGT        # Status Erledigt geht immer vor
b = abl.aussortieren(akte("Newsletter"), "Werbung", jetzt=D)
assert ph.phase(b) == ph.NICHT_RELEVANT
try:
    abl.phase_setzen(b, "quatsch")
    raise AssertionError("unbekannte Phase angenommen")
except ak.AblageFehler:
    pass
ok("C1 Phase aus Status, Rückfrage, Angebot; von Hand, zurück auf automatisch; Erledigt/Nicht relevant gehen vor")

# ---------------------------------------------------------------------------------------------- C2
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE IF NOT EXISTS auftrag_kopf (uid TEXT PRIMARY KEY, nummer TEXT, status TEXT)")
con.execute("CREATE TABLE IF NOT EXISTS auftrag_angebote (auftrag TEXT, angebot TEXT, nummer TEXT, am TEXT)")
con.execute("CREATE TABLE angebote (id INTEGER PRIMARY KEY, nummer TEXT, vorgang TEXT)")
con.executemany("INSERT INTO angebote (nummer, vorgang) VALUES (?, ?)",
                [("A1", "Offen"), ("A2", "Beauftragt"), ("A3", "Beauftragt"), ("A4", "Beauftragt")])
con.executemany("INSERT INTO auftrag_kopf VALUES (?, ?, ?)", [("u3", "AU-3", au.PRODUKTION),
                                                               ("u4", "AU-4", au.AUSGELIEFERT)])
con.executemany("INSERT INTO auftrag_angebote VALUES (?, ?, ?, ?)", [("u3", "x3", "A3", "1"), ("u4", "x4", "A4", "1")])
db = SimpleNamespace(con=con)
assert ph.angebots_phase(db, []) == ""
assert ph.angebots_phase(db, ["A1"]) == ph.ANGEBOT
assert ph.angebots_phase(db, ["A2"]) == ph.AUFTRAG
assert ph.angebots_phase(db, ["A1", "A3"]) == ph.PRODUKTION
assert ph.angebots_phase(db, ["A4"]) == ph.ERLEDIGT
assert ph.angebots_phase(None, ["A1"]) == ph.ANGEBOT
ok("C2 Phase aus Angebot (erstellt, beauftragt) und Auftrag (in Produktion, ausgeliefert)")

# ---------------------------------------------------------------------------------------------- C3
abl3 = ak.OrdnerAblage(tmp / "akten3", "PB", platz="BUERO1")
abl, alt_abl = abl3, abl
fr = []
for wer in ("MK", "MK", "MK"):
    x = akte("Alt", kunde="200", einordnung=dict(art="anfrage", sachgebiete=["rohr"]))
    fr.append(abl.uebernehmen(x, wer, jetzt=D))
y = akte("Blech", kunde="300", einordnung=dict(art="anfrage", sachgebiete=["blech"]))
abl.uebernehmen(y, "AS", jetzt=D)
neu1 = akte("Neue Anfrage", kunde="200", einordnung=dict(art="anfrage", sachgebiete=["rohr"]))
neu2 = akte("Ohne Kunde", einordnung=dict(art="anfrage", sachgebiete=["blech"]))
neu3 = akte("Fester Kunde", kunde="400")
akten = abl.alle()
v = ph.vorschlag(neu1, akten)
assert v["kuerzel"] == "MK" and v["sicher"] and any("dieses Kunden" in g for g in v["gruende"]), v
v2 = ph.vorschlag(neu2, akten)
assert v2["kuerzel"] == "AS" and not v2["sicher"] and any("Sachgebiet" in g for g in v2["gruende"]), v2
kunden = [dict(kundennr="400", zustaendig="ps")]
v3 = ph.vorschlag(neu3, akten, kunden)
assert v3["kuerzel"] == "PS" and v3["sicher"] and "Kundenstamm" in v3["gruende"][0]
assert ph.vorschlag(neu1, akten, mitarbeiter=["AS"]) is None       # MK gibt es nicht mehr
assert ph.vorschlag(akte("Fremd"), akten) is None
erg = ph.vorschlaege_zuweisen(abl, abl.alle(), kunden, jetzt=D)
assert sorted(erg) == [(neu1.nr, "MK"), (neu3.nr, "PS")], erg       # neu2 nur Vorschlag (nicht sicher)
n1 = abl.neu_lesen(neu1)
assert n1.stand["zugewiesen"] == "MK" and n1.verlauf[-1].get("vorschlag")
abl.zuweisen(n1, "", jetzt=D)                   # von Hand aufgehoben bleibt aufgehoben
assert ph.vorschlaege_zuweisen(abl, abl.alle(), kunden, jetzt=D) == []
ok("C3 Bearbeiter-Vorschlag mit Gründen; automatisch nur sichere, nur einmal, Aufheben bleibt")
abl = alt_abl

# ---------------------------------------------------------------------------------------------- C4
P = "\\\\Postfach\\Anfragen\\"
phasen = {ph.PRUEFUNG: P + "Prüfung", ph.ANGEBOT: P + "Angebot", ph.NICHT_RELEVANT: P + "Nicht relevant",
          ph.RUECKFRAGE: ""}
assert set(ol.phasen_ordner(phasen)) == {ph.PRUEFUNG, ph.ANGEBOT, ph.NICHT_RELEVANT}
assert ol.phasen_ordner({ph.PRUEFUNG: "X", ph.ANGEBOT: "x"}) == {ph.PRUEFUNG: "X"}      # derselbe Ordner nur einmal
d = ol.ps_daten("Anfragen", "z", phasen=phasen)
assert d["unter"][3:] == ["Technische Prüfung", "Angebot erstellt", "Nicht relevant"], d["unter"]
assert d["begrenzt"] == ["Erledigt", "Nicht relevant"]
assert ol.ps_daten("Anfragen", "z")["unter"] == ["Neu", "In Bearbeitung", "Erledigt"]

abl4 = ak.OrdnerAblage(tmp / "akten4", "PB", platz="BUERO1")
ou = Outlook(pfade={ph.text(p): w for p, w in phasen.items() if w})
ou.mail("<p1@kunde.example>", "Anfrage Rahmen", "Bitte anbieten.", "max@kunde.example")
ou.mail("<p2@kunde.example>", "Anfrage Deckel", "Bitte anbieten.", "max@kunde.example")
ou.mail("<p3@kunde.example>", "Rabattaktion", "Jetzt kaufen.", "info@shop.example")
erg = ol.abrufen(abl4, "Anfragen", ausfuehren=ou, jetzt=D, phasen=phasen)
assert len(erg["neu"]) == 3 and not erg["fehler"], erg
x = {a.kopf["nachrichten_id"]: a for a in abl4.alle()}
# Programm -> Outlook: Phase von Hand / aus dem Angebot
abl4.phase_setzen(abl4.uebernehmen(x["<p1@kunde.example>"], jetzt=D), ph.PRUEFUNG, jetzt=D)
abl4.angebot_verknuepfen(abl4.uebernehmen(x["<p2@kunde.example>"], jetzt=D), "2026-01000", jetzt=D)
ol.abrufen(abl4, "Anfragen", ausfuehren=ou, jetzt=D, phasen=phasen)
assert ou.wo("<p1@kunde.example>") == "Technische Prüfung" and ou.wo("<p2@kunde.example>") == "Angebot erstellt"
ol.abrufen(abl4, "Anfragen", ausfuehren=ou, jetzt=D, phasen=phasen)
p1 = abl4.neu_lesen(x["<p1@kunde.example>"])
assert ph.phase(p1) == ph.PRUEFUNG and p1.verlauf[-1]["aktion"] == ak.PHASE      # kein Hin und Her
# Outlook -> Programm
ou.schieben("<p1@kunde.example>", "In Bearbeitung")
erg = ol.abrufen(abl4, "Anfragen", ausfuehren=ou, jetzt=D, phasen=phasen)
p1 = abl4.neu_lesen(p1)
assert ph.phase(p1) == ph.BEARBEITUNG and erg["gefolgt"], erg
assert "in Outlook nach „In Bearbeitung“ gezogen" in ak.verlauf_text(p1.verlauf[-1])
ou.schieben("<p1@kunde.example>", "Technische Prüfung")
ol.abrufen(abl4, "Anfragen", ausfuehren=ou, jetzt=D, phasen=phasen)
p1 = abl4.neu_lesen(p1)
assert p1.stand["phase"] == ph.PRUEFUNG and p1.verlauf[-1].get("outlook") == "Technische Prüfung"
ou.schieben("<p3@kunde.example>", "Nicht relevant")
ol.abrufen(abl4, "Anfragen", ausfuehren=ou, jetzt=D, phasen=phasen)
p3 = abl4.neu_lesen(x["<p3@kunde.example>"])
assert p3.aussortiert and ph.phase(p3) == ph.NICHT_RELEVANT and ou.wo("<p3@kunde.example>") == "Nicht relevant"
assert ol.ziel_ordner(p3, {}) == "Erledigt" and ol.ziel_ordner(p1, {}) == "In Bearbeitung"    # ohne Ordner
assert not [e for a in abl4.alle() for e in a.verlauf if e.get("ungueltig")]
ok("C4 Phasen-Ordner: Programm verschiebt, Outlook setzt die Phase (im Verlauf), Nicht relevant, ohne Ordner wie bisher")

# ---------------------------------------------------------------------------------------------- C5
abl5 = ak.OrdnerAblage(tmp / "akten5", "PB", platz="BUERO1")
ou = Outlook()
ou.mail("<f1@kunde.example>", "Anfrage", "Bitte.", "max@kunde.example")
ou.nicht_sicherbar.add("<f1@kunde.example>")
erg = ol.abrufen(abl5, "Anfragen", ausfuehren=ou, jetzt=D)
f = ol.fehler_lesen(abl5)["<f1@kunde.example>"]
assert f["anzahl"] == 1 and f["naechster"].startswith("2026-11-20T08:00") and erg["wartet"] == 1, f
s = ol.abruf_status(abl5)
assert s["ok"] is False and s["outlook_erreicht"] and s["wartet"] == 1 and s["fehlversuche"] == 1, s
assert "1 Mail(s) warten" in ol.status_text(s)
ol.abrufen(abl5, "Anfragen", ausfuehren=ou, jetzt=D + datetime.timedelta(seconds=60))     # nächster Abruf: Versuch
f = ol.fehler_lesen(abl5)["<f1@kunde.example>"]
assert f["anzahl"] == 2 and f["naechster"].startswith("2026-11-20T08:06"), f       # dann 5 Minuten warten
n = len(ou.aufrufe)
ol.abrufen(abl5, "Anfragen", ausfuehren=ou, jetzt=D + datetime.timedelta(minutes=2))
assert "<f1@kunde.example>" in ou.aufrufe[n]["spaeter"] and ol.fehler_lesen(abl5)["<f1@kunde.example>"]["anzahl"] == 2
assert ol.erneut_verarbeiten(abl5) == 1
ou.nicht_sicherbar.clear()
erg = ol.abrufen(abl5, "Anfragen", ausfuehren=ou, jetzt=D + datetime.timedelta(minutes=3))
assert len(erg["neu"]) == 1 and not ol.fehler_lesen(abl5) and ol.abruf_status(abl5)["ok"]
assert ol.abruf_status(abl5)["fehlversuche"] == 0
ou.fehler = "Klasse nicht registriert 80040154"
erg = ol.abrufen(abl5, "Anfragen", ausfuehren=ou, jetzt=D + datetime.timedelta(minutes=4))
s = ol.abruf_status(abl5)
assert not s["outlook_erreicht"] and s["letzter_erfolg"].startswith("2026-11-20T08:03")
assert "nicht erreichbar" in ol.status_text(s) and "zuletzt geklappt 20.11. 08:03" in ol.status_text(s)
assert "Restrict" in ol.ABRUF_PS and "fehl_mid" in ol.ABRUF_PS and "spaeter" in ol.ABRUF_PS
ok("C5 Fehlgeschlagene Mail: nächster Abruf, dann 5 Minuten warten, Erneut verarbeiten, Status inkl. Outlook nicht erreichbar")

# ---------------------------------------------------------------------------------------------- C6
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
sa = seite.ablage()
for i in range(3):
    k = dict(quelle="ordner", eingang=D + datetime.timedelta(minutes=i), betreff=f"Alt {i}", kundennr="500")
    x, _ = sa.anlegen(k, [], f"alt{i}", jetzt=D)
    sa.uebernehmen(x, "MK", jetzt=D)
p = tmp / "neu.msg"
p.write_bytes(t.msg("Anfrage Halter", "Bitte 20 Stück.", "Kunde", "k@kunde.example", D, []))
neu, _ = sa.anlegen(dict(quelle="ordner", eingang=D + datetime.timedelta(hours=1), betreff="Anfrage Halter",
                         kundennr="500"), [p], "neu", jetzt=D)
seite.neu_laden()
seite.waehlen(neu.nr)
html_ = "".join(seite._erkannt_html(seite.akte()))
assert "<b>Phase:</b> Neu" in html_ and "phase:" in html_, html_[:500]
assert "Vorschlag Bearbeiter:</b> MK (sicher)" in html_ and "vorschlag:MK" in html_, html_[:800]
seite.zuweisen("MK")
assert sa.neu_lesen(neu).stand["zugewiesen"] == "MK"
from rohrlaser import anfrage_lernen  # noqa: E402
r = anfrage_lernen.rueckmeldungen(sa.wurzel, "bearbeiter")
assert r and r[-1]["richtig"] and r[-1]["auto"] == "MK", r
seite.uebernehmen()
seite.phase_setzen(ph.PRUEFUNG)
a = sa.neu_lesen(neu)
assert a.stand["phase"] == ph.PRUEFUNG
seite.neu_laden()
seite.waehlen(neu.nr)
zeile = next(r for r in range(seite.tabelle.rowCount()) if seite.tabelle.item(r, 0).text() == neu.nr)
assert seite.tabelle.item(zeile, 7).text().startswith("Technische Prüfung"), seite.tabelle.item(zeile, 7).text()
assert "(von Hand, PB)" in "".join(seite._erkannt_html(seite.akte()))
ol._json_schreiben(Path(sa.wurzel) / ol.STAMM / "abruf_status.json",
                   dict(zeit="2026-11-20T09:00:00", platz="BUERO1", neu=2, fehler=[], wartet=1, outlook_erreicht=True))
assert "Erneut verarbeiten" in seite.ol_status_zeigen() and seite.ol_status.isVisibleTo(seite)
d = seite.outlook_zeigen()
assert "phase_pruefung" in d.pfade and "phase_nicht_relevant" in d.pfade
assert d._pfad_setzen("phase_pruefung", "\\\\Postfach\\Prüfung") == ""
assert db.einstellung(ph.ORDNER_EINSTELLUNG + ph.PRUEFUNG) == "\\\\Postfach\\Prüfung"
assert ph.ordner_einstellungen(db) == {ph.PRUEFUNG: "\\\\Postfach\\Prüfung"}
assert d._pfad_setzen("phase_angebot", "\\\\Postfach\\Prüfung") == "doppelt"
ok("C6 Seite: Phase und Vorschlag rechts, Zuweisen lernt, Phase ändern, Liste, Statuszeile, Phasen-Ordner im Fenster")

print("Alle Tests bestanden.")
