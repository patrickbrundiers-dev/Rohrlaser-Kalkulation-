"""Anfragen sammeln und zusammenführen (Patrick 20.11.2026, Entwicklungsauftrag „Outlook-E-Mail-Verwaltung und
intelligente Anfragezusammenführung“): die 10 Abnahme-Szenarien aus Punkt 10, mit erfundenen Testmails.

  S1  eine MSG-Datei einer bestehenden Anfrage hinzufügen (Anhänge ausgepackt, Herkunft Von/An/Datum/Betreff)
  S2  zehn unterschiedliche E-Mails einer gemeinsamen Anfrage zuordnen (Chronik nach Sendezeit)
  S3  mehrere PDF- und Excel-Dateien hinzufügen (Kategorien vorgeschlagen, änderbar, eigene Kategorie)
  S4  zwei bestehende Anfragen zusammenführen (Übersicht vorher, alles übernommen, alte Nummern dokumentiert)
  S5  doppelte Anhänge erkennen (beim Hinzufügen und Zusammenführen nur einmal gespeichert)
  S6  eine E-Mail nachträglich einer anderen Anfrage zuweisen (Outlook-Zuordnung zieht mit)
  S7  Zusammenführung rückgängig machen
  S8  Import bei Netzwerkunterbrechung kontrolliert abbrechen und fortsetzen (keine halben Dateien)
  S9  gleichzeitige Bearbeitung durch mehrere Benutzer (Sperre, Rechte, eigene Verlaufsdateien)
  S10 vollständige Wiederherstellung nach einem Programmabsturz mitten im Zusammenführen
  dazu: Vorschläge „gehört vielleicht zu …“ (nie automatisch), Antworten auf eine zusammengeführte Anfrage landen
  in der Hauptanfrage

Aufruf: python tests/test_anfragen_sammeln.py
"""
import datetime
import shutil
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import mail_testdateien as t  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import anfragen_sammeln as sa  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
ein = tmp / "eingang"
ein.mkdir()
D = datetime.datetime(2026, 11, 20, 8, 0)
abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")


def datei(name, inhalt):
    p = ein / name
    p.write_bytes(inhalt if isinstance(inhalt, bytes) else inhalt.encode("utf-8"))
    return p


def mail_datei(name, betreff, text, wann, anhaenge=(), absender="einkauf@neumann.example", iid=None):
    return datei(name, t.msg(betreff, text, "Hans Neumann", absender, wann, list(anhaenge),
                             an=[("Anfrage", "anfrage@laser.example")],
                             ids={0x1035: f"<{iid or Path(name).stem}@neumann.example>"}))


def akte_neu(betreff, dateien, kunde="10002", kurz="", n=[0]):
    n[0] += 1
    a, neu = abl.anlegen(dict(quelle="ordner", betreff=betreff, kundennr=kunde, absender="einkauf@neumann.example",
                              eingang=D, kurz=kurz), dateien, f"test-{n[0]}", jetzt=D)
    assert neu
    return a


# ------------------------------------------------------------------ S1
erste = mail_datei("anfrage.msg", "Anfrage Gestell G-100", "Bitte anbieten. Projekt-Nr. P-4711", D,
                   [("G-100_Zeichnung.pdf", b"%PDF-1.4 zeichnung g100")])
a1 = akte_neu("Anfrage Gestell G-100", [erste], kurz="Bitte anbieten. Projekt-Nr. P-4711")
nachtrag = mail_datei("nachtrag.msg", "AW: Anfrage Gestell G-100", "Anbei die Stückliste.", D + datetime.timedelta(hours=3),
                      [("Stueckliste_G-100.xlsx", b"PK\x03\x04 stueckliste")])
r = sa.hinzufuegen(abl, a1, [nachtrag], quelle="drag", jetzt=D + datetime.timedelta(hours=4))
a1 = r["akte"]
assert r["neu"] == ["nachtrag.msg", "Stueckliste_G-100.xlsx"] and not r["fehler"], r
d = {x["name"]: x for x in sa.dokumente(a1)}
assert d["nachtrag.msg"]["herkunft"]["von"] == "einkauf@neumann.example" and d["nachtrag.msg"]["herkunft"]["an"] == \
    ["anfrage@laser.example"] and d["nachtrag.msg"]["herkunft"]["quelle"] == "drag", d["nachtrag.msg"]
assert d["Stueckliste_G-100.xlsx"]["aus_mail"] == "nachtrag.msg" and d["Stueckliste_G-100.xlsx"]["kategorie"] == sa.STUECKLISTE
assert d["anfrage.msg"]["kategorie"] == sa.KUNDENANFRAGE and d["nachtrag.msg"]["kategorie"] == sa.VERLAUF
assert d["G-100_Zeichnung.pdf"]["kategorie"] == sa.ZEICHNUNG and d["anfrage.msg"]["id"].startswith("D-")
assert len({x["id"] for x in d.values()}) == len(d)
assert "nachtrag@neumann.example" in a1.stand["internet_ids"]
assert any(p["art"] == "hinzufuegen" and p["akte"] == a1.nr for p in sa.protokoll(abl))
ok("S1 MSG zu bestehender Anfrage: Anhänge ausgepackt, Herkunft (Von/An/Datum/Betreff), Kategorie, Dokument-ID, "
   "Protokoll")

# ------------------------------------------------------------------ S2
a2 = akte_neu("Rahmen R-7", [mail_datei("r7.msg", "Rahmen R-7", "Bitte anbieten", D)])
zehn = [mail_datei(f"m{i}.msg", f"AW: Rahmen R-7 ({i})", f"Nachricht {i}", D + datetime.timedelta(minutes=10 * (10 - i)))
        for i in range(10)]
r = sa.hinzufuegen(abl, a2, zehn, jetzt=D + datetime.timedelta(days=1))
a2 = r["akte"]
assert len(r["neu"]) == 10 and len([x for x in a2.dateien() if x["art"] == "mail"]) == 11, r
mails = [c for c in sa.chronik(a2) if c["art"] == "mail"]
assert len(mails) == 11 and [c["zeit"] for c in mails] == sorted(c["zeit"] for c in mails)
assert "Nachricht" not in "".join(c["text"] for c in mails) and "Rahmen R-7 (9)" in mails[1]["text"], mails[:2]
ok("S2 zehn Mails einer Anfrage zugeordnet, Chronik nach Sendezeit")

# ------------------------------------------------------------------ S3
dateien = [datei("Zeichnung_A.pdf", b"%PDF-1.4 a"), datei("Zeichnung_B.pdf", b"%PDF-1.4 b"),
           datei("Angebot_Lieferant.pdf", b"%PDF-1.4 angebot"), datei("Teile.xlsx", b"PK\x03\x04 teile"),
           datei("Materialanfrage_Rohr.xlsx", b"PK\x03\x04 mat"), datei("Foto.jpg", b"\xff\xd8" + b"x" * 40000)]
r = sa.hinzufuegen(abl, a2, dateien)
a2 = r["akte"]
assert len(r["neu"]) == 6, r
k = {x["name"]: x["kategorie"] for x in sa.dokumente(a2)}
assert k["Zeichnung_A.pdf"] == sa.ZEICHNUNG and k["Angebot_Lieferant.pdf"] == sa.ANGEBOT
assert k["Teile.xlsx"] == sa.STUECKLISTE and k["Materialanfrage_Rohr.xlsx"] == sa.MATERIAL and k["Foto.jpg"] == sa.NACHTRAG
sa.kategorie_anlegen(abl.wurzel, "Prüfberichte")
a2 = sa.kategorie_setzen(abl, a2, "Foto.jpg", "Prüfberichte")
assert {x["name"]: x["kategorie"] for x in sa.dokumente(a2)}["Foto.jpg"] == "Prüfberichte"
assert "Prüfberichte" in sa.nach_kategorie(a2, abl.wurzel) and "Prüfberichte" in sa.kategorien(abl.wurzel)
ok("S3 mehrere PDF/Excel/Bilder: Kategorien vorgeschlagen, änderbar, eigene Kategorie")

# ------------------------------------------------------------------ S5 (beim Hinzufügen)
r = sa.hinzufuegen(abl, a2, [datei("Zeichnung_A_Kopie.pdf", b"%PDF-1.4 a"), zehn[0]])
assert not r["neu"] and len(r["doppelt"]) == 2 and "Zeichnung_A.pdf" in r["doppelt"][0], r
ok("S5 doppelte Anhänge/Mails beim Hinzufügen erkannt (gleicher Inhalt, anderer Name), nichts doppelt gespeichert")

# ------------------------------------------------------------------ S4 + Vorschläge
b = akte_neu("Nachtrag Gestell G-100", [mail_datei("b.msg", "Nachtrag Gestell G-100", "Neue Version, Projekt-Nr. P-4711",
                                                    D + datetime.timedelta(days=1),
                                                    [("G-100_Zeichnung.pdf", b"%PDF-1.4 zeichnung g100"),
                                                     ("G-100_Zeichnung_rev2.pdf", b"%PDF-1.4 rev2")], iid="b")])
vs = sa.vorschlaege(abl.alle(), b, "Projekt-Nr. P-4711")
assert vs and vs[0][0].nr == a1.nr and "P-4711" in vs[0][1] and "gleiche Datei" in vs[0][1], vs
assert abl.lesen(b.nr).status == ak.NEU and not abl.lesen(b.nr).stand["zusammengefuehrt_in"]   # nie automatisch
v = sa.vorschau(a1, [b])
assert [x[1] for x in v["doppelt"]] == ["G-100_Zeichnung.pdf"] and ("b.msg" in [x[1] for x in v["dateien"]]), v
assert len(v["mails"]) == 1 and not v["warnungen"], v
jid = sa.zusammenfuehren(abl, a1, [b], jetzt=D + datetime.timedelta(days=2))
a1, b = abl.lesen(a1.nr), abl.lesen(b.nr)
namen = [x["name"] for x in a1.dateien()]
assert "b.msg" in namen and "G-100_Zeichnung_rev2.pdf" in namen and namen.count("G-100_Zeichnung.pdf") == 1, namen
hb = next(x for x in sa.dokumente(a1) if x["name"] == "b.msg")["herkunft"]
assert hb["akte"] == b.nr and hb["von"] == "einkauf@neumann.example" and hb["datum"].startswith("2026-11-21"), hb
assert b.status == ak.ERLEDIGT and b.stand["zusammengefuehrt_in"] == a1.nr and b.dateien()      # bleibt lesbar
assert any(e["aktion"] == ak.ZUSAMMEN and e["von"] == [b.nr] for e in a1.verlauf)
assert b.nr in ak.verlauf_text(next(e for e in a1.verlauf if e["aktion"] == ak.ZUSAMMEN))
assert "b@neumann.example" in a1.stand["internet_ids"]
ok("S4 zwei Anfragen zusammengeführt: Übersicht vorher, Mails/Anhänge/Herkunft übernommen, alte Nummer im Verlauf, "
   "Vorschlag nur als Vorschlag")
ok("S5 doppelter Anhang beim Zusammenführen nur einmal gespeichert")
# Antwort auf die zusammengeführte Anfrage kommt in die Hauptanfrage
ziel = ak.antwort_zu(abl.alle(), "x", "a@b.de", in_reply_to="b@neumann.example")
assert ziel is not None and ziel.nr == a1.nr

# ------------------------------------------------------------------ S7
wieder = sa.rueckgaengig(abl, a1, jid, jetzt=D + datetime.timedelta(days=3))
a1, b = abl.lesen(a1.nr), abl.lesen(b.nr)
assert [x.nr for x in wieder] == [b.nr] and b.status == ak.NEU and not b.stand["zusammengefuehrt_in"]
assert "b.msg" not in [x["name"] for x in a1.dateien()] and "G-100_Zeichnung.pdf" in [x["name"] for x in a1.dateien()]
assert (a1.pfad / ak.DATEIEN / "b.msg").exists()                    # nichts gelöscht
assert any(e["aktion"] == ak.TRENNEN for e in a1.verlauf) and b.nr in ak.verlauf_text(a1.verlauf[-1])
ok("S7 Zusammenführung rückgängig: Hauptanfrage ohne die übernommenen Inhalte, die andere wieder offen")

# ------------------------------------------------------------------ S6
c = akte_neu("Andere Anfrage", [mail_datei("c.msg", "Andere Anfrage", "x", D)])
a2_alt = abl.lesen(a2.nr)
falsch = next(x for x in a2_alt.dateien() if x["name"] == "m3.msg")
von, nach = sa.verschieben(abl, a2_alt, c, [falsch.get("datei", falsch["name"])], jetzt=D + datetime.timedelta(days=3))
assert "m3.msg" not in [x["name"] for x in von.dateien()] and "m3.msg" in [x["name"] for x in nach.dateien()]
weg = next(x for x in von.dateien(mit_weg=True) if x["name"] == "m3.msg")
assert weg["weg"] == c.nr and (von.pfad / ak.DATEIEN / "m3.msg").exists()
assert next(x for x in sa.dokumente(nach) if x["name"] == "m3.msg")["herkunft"]["akte"] == a2.nr
# die Outlook-Mail selbst (erste Mail) verschieben: die Outlook-Zuordnung zieht mit
o, _ = abl.anlegen(dict(quelle="outlook", betreff="O", nachrichten_id="<o1@x>", eingang=D),
                   [mail_datei("o.msg", "O", "x", D)], "test-o", jetzt=D)
from rohrlaser import outlook_anfragen as ol  # noqa: E402
_, c = sa.verschieben(abl, o, c, ["o.msg"])
assert ol.index(abl.alle())["<o1@x>"].nr == c.nr
ok("S6 Mail nachträglich einer anderen Anfrage zugewiesen (alte zeigt „verschoben“, Outlook-Zuordnung folgt)")

# ------------------------------------------------------------------ S8
orig = shutil.copy2
zahl = [0]


def bricht(src, dst, *x, **y):
    zahl[0] += 1
    if zahl[0] == 3:
        Path(dst).write_bytes(b"halb")      # halbe Datei, dann bricht das Netz ab
        raise OSError("Netzwerkpfad nicht mehr verfügbar")
    return orig(src, dst, *x, **y)


viele = [datei(f"Teil_{i}.pdf", f"%PDF-1.4 teil {i}".encode()) for i in range(5)]
shutil.copy2 = bricht
try:
    r = sa.hinzufuegen(abl, a2, viele)
finally:
    shutil.copy2 = orig
assert r["neu"] == ["Teil_0.pdf", "Teil_1.pdf"] and r["fehler"] and "Netzwerk" in r["fehler"][0], r
assert not list((a2.pfad / ak.DATEIEN).glob("*.teil")) and not (a2.pfad / ak.DATEIEN / "Teil_2.pdf").exists()
r = sa.hinzufuegen(abl, a2, viele)
assert r["neu"] == ["Teil_2.pdf", "Teil_3.pdf", "Teil_4.pdf"] and len(r["doppelt"]) == 2, r
ok("S8 Netzabbruch beim Import: kontrolliert abgebrochen, keine halbe Datei, Fortsetzen ohne Doppel")

# ------------------------------------------------------------------ S9
ev = ak.OrdnerAblage(tmp / "akten", "EV", platz="BUERO2")
x1 = akte_neu("Mehrbenutzer 1", [datei("x1.pdf", b"%PDF x1")])
x2 = akte_neu("Mehrbenutzer 2", [datei("x2.pdf", b"%PDF x2")])
x1 = abl.uebernehmen(x1)                                    # PB bearbeitet x1
try:
    sa.zusammenfuehren(ev, ev.lesen(x2.nr), [ev.lesen(x1.nr)], ich="EV")
    raise AssertionError("EV darf die Anfrage von PB nicht zusammenführen")
except ak.AblageFehler as e:
    assert "PB" in str(e)
assert sa._sperre_nehmen(abl.lesen(x2.nr), "PB", datetime.datetime.now())     # PB führt gerade zusammen
try:
    sa.zusammenfuehren(ev, ev.lesen(x2.nr), [ev.lesen(x1.nr)], admin=True)
    raise AssertionError("Sperre wirkt nicht")
except ak.AblageFehler as e:
    assert "anderen Platz" in str(e)
sa._sperre_geben([abl.lesen(x2.nr)])
sa.hinzufuegen(ev, ev.lesen(x2.nr), [datei("von_ev.pdf", b"%PDF ev")])
sa.hinzufuegen(abl, abl.lesen(x2.nr), [datei("von_pb.pdf", b"%PDF pb")])
x2 = abl.lesen(x2.nr)
assert {"von_ev.pdf", "von_pb.pdf"} <= {d["name"] for d in x2.dateien()}
assert (x2.pfad / "verlauf_EV.jsonl").exists() and (x2.pfad / "verlauf_PB.jsonl").exists()
jid = sa.zusammenfuehren(ev, ev.lesen(x2.nr), [ev.lesen(x1.nr)], admin=True)
assert abl.lesen(x1.nr).stand["zusammengefuehrt_in"] == x2.nr and not list(x2.pfad.glob(sa.SPERRE))
ok("S9 mehrere Benutzer: Rechte (Bearbeiter/Admin), Sperre gegen gleichzeitiges Zusammenführen, beide fügen hinzu")

# ------------------------------------------------------------------ S10
for schritt in (1, 2):
    h = akte_neu(f"Absturz {schritt} Haupt", [datei(f"h{schritt}.pdf", f"%PDF h{schritt}".encode())])
    w = akte_neu(f"Absturz {schritt} Weitere", [datei(f"w{schritt}.pdf", f"%PDF w{schritt}".encode())])
    try:
        sa.zusammenfuehren(abl, h, [w], _abbruch_nach=schritt)
        raise AssertionError("Absturz nicht nachgestellt")
    except RuntimeError:
        pass
    assert not (h.pfad / sa.SPERRE).exists()                # Sperre auch beim Absturz frei
    neu_start = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")     # Programmstart
    meldung = sa.wiederherstellen(neu_start)
    assert meldung and "fertiggestellt" in meldung[0], meldung
    h, w = neu_start.lesen(h.nr), neu_start.lesen(w.nr)
    assert f"w{schritt}.pdf" in [d["name"] for d in h.dateien()] and w.stand["zusammengefuehrt_in"] == h.nr
    assert sum(1 for e in h.verlauf if e["aktion"] == ak.ZUSAMMEN) == 1
    assert sum(1 for e in w.verlauf if e["aktion"] == ak.AUFGEGANGEN) == 1
    assert not sa.wiederherstellen(neu_start)               # nichts mehr offen
ok("S10 Absturz mitten im Zusammenführen (nach dem Kopieren bzw. vor dem Abschluss): beim Start vollständig "
   "wiederhergestellt, nichts doppelt")
print("Alle Tests bestanden.")
