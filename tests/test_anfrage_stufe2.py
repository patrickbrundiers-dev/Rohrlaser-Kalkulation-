"""Anfragen Stufe 2 (Patrick 23.11.2026 „Weiter erweitern und verbessern“).

  S1 Rückfrage nachfassen: nach TAGE Arbeitstagen ohne Antwort fällig, Erinnerung mit den Fragen der Rückfrage,
     Wartezeit läuft neu, Zähler; nach der Antwort: was die Antwort liefert und was weiter fehlt; 0 = aus
  S2 Wichtig zuerst: Punkte mit Gründen (Frist, Priorität, Mail-Art, Kunde, Menge, Rückfrage), Sortierung
  S3 Breiter lernen: Sachgebiet- und Bearbeiter-Modell mit eigenen Dateien und eigener Freigabe, Mail-Art-Modell
     unverändert; Sachgebiet nur bei unsicherer Einordnung, Bearbeiter-Tipp gibt Punkte, nie „sicher“
  S4 Kennzahlen je Woche: Eingänge, unklar, korrigiert, Kunde eindeutig, Ø bis Übernahme, Rückfragen, nachgefasst
  S6 Fehler 23.11.: Links mit „_“ (Kunde ändern, Neuen Kunden anlegen …) waren keine gültige QUrl und taten nichts;
     Schnellfilter deutlich sichtbar und „Filter zurücksetzen“
  S5 Seite „Anfragen“: Schnellfilter „Nachfassen“, Erinnerung … öffnet Outlook (nie senden), Kopf zeigt Gründe,
     „Wichtig zuerst“ sortiert die Liste, tägliche Erinnerung nennt nachzufassende Rückfragen

Aufruf: python tests/test_anfrage_stufe2.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import anfrage_art as aa  # noqa: E402
from rohrlaser import anfrage_lernen as al  # noqa: E402
from rohrlaser import anfrage_messung as am  # noqa: E402
from rohrlaser import anfrage_phase as ph  # noqa: E402
from rohrlaser import anfrage_nachfassen as anf  # noqa: E402
from rohrlaser import anfrage_reihenfolge as ar  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
D = datetime.datetime(2026, 11, 23, 8, 0)          # Montag
abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")


def akte(betreff, n=[0], **kopf):
    n[0] += 1
    k = dict(quelle="ordner", betreff=betreff, eingang=D + datetime.timedelta(minutes=n[0]), **kopf)
    a, _ = abl.anlegen(k, [], f"t{n[0]}", jetzt=D)
    return a


# ---------------------------------------------------------------------------------------------- S1
a = abl.uebernehmen(akte("Anfrage Rahmen"), jetzt=D)
assert anf.stand(a, 3, jetzt=D) is None                     # keine Rückfrage
text = "Sehr geehrte Damen und Herren,\n\nbitte noch:\n\n- Welcher Werkstoff?\n- Welche Stückzahl?\n\nMit freundl"
a = abl.rueckfrage(a, text, jetzt=D, fehlt=["werkstoff", "menge"])
assert a.stand["rueckfrage_fehlt"] == ["werkstoff", "menge"] and a.stand["nachgefasst"] == 0
st = anf.stand(a, 3, jetzt=D + datetime.timedelta(days=2))
assert st and not st["faellig_ist"] and "nachfassen ab 26.11." in st["text"], st
st = anf.stand(a, 3, jetzt=D + datetime.timedelta(days=3))  # Donnerstag = 3 Arbeitstage
assert st["faellig_ist"] and "ohne Antwort" in st["text"], st
assert anf.stand(a, 0, jetzt=D + datetime.timedelta(days=9)) is None      # 0 = aus
fr = datetime.datetime(2026, 11, 27, 8, 0)                  # Freitag: Wochenende zählt nicht
b = abl.rueckfrage(abl.uebernehmen(akte("Freitag"), jetzt=fr), "- Termin?", jetzt=fr)
assert not anf.stand(b, 2, jetzt=fr + datetime.timedelta(days=3))["faellig_ist"]     # Montag: 1 Arbeitstag
assert anf.stand(b, 2, jetzt=fr + datetime.timedelta(days=4))["faellig_ist"]         # Dienstag
erin = anf.erinnerung_text(None, a)
assert "am 23.11.2026" in erin and "- Welcher Werkstoff?" in erin and "- Welche Stückzahl?" in erin, erin
assert "Sehr geehrte Damen und Herren,\n\nbitte" not in erin
spaeter = D + datetime.timedelta(days=3, hours=2)
a = abl.rueckfrage(a, erin, jetzt=spaeter, nachfassen=True)
assert a.stand["nachgefasst"] == 1 and a.stand["rueckfrage_text"] == text          # Fragen der ersten Rückfrage
assert a.stand["rueckfrage"].startswith("2026-11-26") and not anf.stand(a, 3, jetzt=spaeter)["faellig_ist"]
assert "Erinnerung an die Rückfrage" in ak.verlauf_text(a.verlauf[-1])
assert "schon 1× erinnert" in anf.stand(a, 3, jetzt=spaeter + datetime.timedelta(days=5))["text"]
c = abl.uebernehmen(akte("ohne Rückfrage"), jetzt=D)
try:
    abl.rueckfrage(c, "x", nachfassen=True)
    raise AssertionError("Erinnerung ohne Rückfrage angenommen")
except ak.AblageFehler:
    pass
assert anf.geliefert(a, ["menge"]) is None                  # Rückfrage noch offen
a = abl.antwort_erhalten(a, jetzt=spaeter + datetime.timedelta(days=1))
gl = anf.geliefert(a, ["menge"])
assert gl == (["werkstoff"], ["menge"]), gl
assert anf.geliefert_text(gl) == "Die Antwort liefert: Werkstoff · fehlt weiter: Stückzahl"
assert anf.geliefert_text(anf.geliefert(a, [])) == "Die Antwort liefert: Werkstoff, Stückzahl"
ok("S1 Nachfassen nach Arbeitstagen, Erinnerung mit den Fragen, Zähler, Antwort liefert / fehlt weiter, 0 = aus")

# ---------------------------------------------------------------------------------------------- S2
best = akte("Bestellung 4500")
p1, t1 = ar.punkte(best, "rot", dict(art=aa.BESTELLUNG), [dict(feld="stueckzahl", wert="1.000")],
                   (12000.0, "Kunde vergibt ca. 40 %, üblich 30.000 €"))
assert p1 == 40 + 35 + 20 + 10, (p1, t1)
assert "Antwortfrist überschritten (+40)" in ar.text(t1) and "Bestellung (+35)" in ar.text(t1)
assert "1000 Stück (+10)" in ar.text(t1) and "Kunde vergibt" in ar.text(t1)
werb = akte("Newsletter")
p2, t2 = ar.punkte(werb, None, dict(art=aa.WERBUNG))
assert p2 == -50 and "−50" in ar.text(t2)
norm = akte("Anfrage")
p3, t3 = ar.punkte(norm, None, dict(art=aa.ANFRAGE))
assert p3 == 0 and ar.text(t3) == "keine Besonderheit"
eilt = akte("Eilt")
abl.prioritaet(eilt, "eilt", jetzt=D)
eilt = abl.neu_lesen(eilt)
p4, t4 = ar.punkte(eilt, "gelb", None, [dict(feld="stueckzahl", wert="150 Stück")])
assert p4 == 25 + 30 + 5, (p4, t4)
p5, _ = ar.punkte(a, None, None, nachfassen=None)
assert p5 == 0                                              # Rückfrage beantwortet
wart = abl.rueckfrage(abl.uebernehmen(akte("wartet"), jetzt=D), "- ?", jetzt=D)
assert ar.punkte(wart, None, None)[0] == ar.WARTET
assert ar.punkte(wart, None, None, nachfassen=dict(faellig_ist=True))[0] == ar.NACHFASSEN
erl = abl.erledigen(abl.uebernehmen(akte("fertig"), jetzt=D), jetzt=D)
assert ar.punkte(erl, "rot", dict(art=aa.BESTELLUNG)) == (None, [])
je = {x.nr: ar.punkte(x, *arg) for x, arg in ((best, ("rot", dict(art=aa.BESTELLUNG))), (werb, (None, dict(
    art=aa.WERBUNG))), (norm, (None, None)), (erl, (None, None)), (eilt, ("gelb", None)))}
assert [x.nr for x in ar.sortieren([werb, erl, norm, eilt, best], je)] == [best.nr, eilt.nr, norm.nr, werb.nr,
                                                                           erl.nr]
ok("S2 Wichtig zuerst: Punkte mit Gründen (Frist, Priorität, Art, Kunde, Menge, Rückfrage), Sortierung")

# ---------------------------------------------------------------------------------------------- S3
w = tmp / "lernen"
for i in range(14):
    al.rueckmelden(w, "art", "anfrage", "anfrage", f"B{i}", "PB", f"Blech {i} Laserteile Tafel Kantteil",
                   sachgebiete_auto=["rohr"], sachgebiete=["blech"])
for i in range(12):
    al.rueckmelden(w, "art", "anfrage", "anfrage", f"R{i}", "PB", f"Rohr {i} Rundrohr Gehrung Halter",
                   sachgebiete_auto=["rohr"], sachgebiete=["rohr"])
m = al.trainieren(w, ziel="sachgebiet")
assert m["ziel"] == "sachgebiet" and m["n"] == 26 and set(m["klassen"]) == {"blech", "rohr"}, m["klassen"]
assert (w / al.STAMM / "modell_sachgebiet.json").is_file() and not al.modell_lesen(w)     # Mail-Art: kein Modell
assert m["pruefung"]["modell"] > m["pruefung"]["regeln"], m["pruefung"]
ok_, grund = al.freigeben(w, "PB", ziel="sachgebiet")
assert ok_ and al.aktiv_lesen(w, "sachgebiet")["version"] == 1 and not al.aktiv_lesen(w), grund
ms = al.aktiv_lesen(w, "sachgebiet")
ein = dict(art="anfrage", sicherheit=aa.WAHRSCHEINLICH, sachgebiete=["rohr"], gruende=[])
neu = al.sachgebiete_anwenden(ms, ein, "Laserteile aus Blech, Tafel 3 mm, Kantteil", "Anfrage")
assert neu["sachgebiete"] == ["blech"] and neu["gelernt_sg"] and "Sachgebiet gelernt" in neu["gruende"][-1][0], neu
sicher = dict(ein, sicherheit=aa.SICHER_ART)
assert al.sachgebiete_anwenden(ms, sicher, "Blech Tafel Kantteil") is sicher           # sichere bleiben
for i in range(22):
    al.rueckmelden(w, "bearbeiter", "PB", "MK", f"Z{i}", "PB", betreff=f"Anfrage Blech {i}", kunde="700",
                   sachgebiete=["blech"])
mb = al.trainieren(w, ziel="bearbeiter")
assert mb["n"] == 22 and mb["pruefung"]["regeln"] == 0 and mb["pruefung"]["modell"] == 100, mb["pruefung"]
assert al.freigeben(w, "PB", ziel="bearbeiter")[0]
tipp = al.bearbeiter_tipp(al.aktiv_lesen(w, "bearbeiter"), "Anfrage Blech Tafel", "700", ["blech"])
assert tipp and tipp[0] == "MK" and tipp[2] == 22, tipp
nb = akte("Anfrage Blech Tafel", kundennr="700")
v = ph.vorschlag(nb, [nb], gelernt=tipp)
assert v["kuerzel"] == "MK" and v["punkte"] == ph.GELERNT and not v["sicher"] and "gelernt aus 22" in v["gruende"][0]
assert "Modell 1 gilt wieder" not in al.zuruecknehmen(w, "bearbeiter") and not al.aktiv_lesen(w, "bearbeiter")
assert al.aktiv_lesen(w, "sachgebiet")                      # andere Ziele unberührt
ok("S3 Sachgebiet- und Bearbeiter-Modell: eigene Dateien/Freigabe, nur unsichere Fälle, Tipp nie „sicher“")

# ---------------------------------------------------------------------------------------------- S4
jetzt = datetime.datetime(2026, 11, 25, 12, 0)
abl4 = ak.OrdnerAblage(tmp / "akten4", "PB", platz="BUERO1")
w1 = datetime.datetime(2026, 11, 17, 9, 0)                  # KW 47
w2 = datetime.datetime(2026, 11, 24, 9, 0)                  # KW 48
for i, (t_, sich, stufe) in enumerate(((w1, aa.SICHER_ART, "eindeutig"), (w1, aa.UNKLAR, "unbekannt"),
                                       (w2, aa.SICHER_ART, "eindeutig"), (w2, aa.SICHER_ART, "eindeutig"))):
    x, _ = abl4.anlegen(dict(quelle="ordner", eingang=t_, betreff=f"A{i}", einordnung=dict(
        art="anfrage", sicherheit=sich, sachgebiete=[]), zuordnung=dict(stufe=stufe)), [], f"v{i}", jetzt=t_)
    x = abl4.uebernehmen(x, jetzt=t_ + datetime.timedelta(hours=2 + 2 * i))
    if i == 1:
        x = abl4.rueckfrage(x, "- ?", jetzt=t_ + datetime.timedelta(hours=5))
        abl4.rueckfrage(x, "Erinnerung", jetzt=t_ + datetime.timedelta(days=4), nachfassen=True)
    if i == 3:
        al.rueckmelden(abl4.wurzel, "kunde", "1", "2", x.nr, "PB")
vl = am.verlauf(abl4.alle(), abl4.wurzel, wochen=3, jetzt=jetzt)
assert [x["woche"] for x in vl] == ["2026-W46", "2026-W47", "2026-W48"], vl
assert vl[0]["eingaenge"] == 0 and vl[0]["unklar"] is None
k47, k48 = vl[1], vl[2]
assert k47["eingaenge"] == 2 and k47["unklar"] == 50 and k47["kunde_sicher"] == 50 and k47["std_bis_uebernahme"] == 3.0
assert k47["rueckfragen"] == 1 and k47["nachgefasst"] == 1, k47
assert k48["eingaenge"] == 2 and k48["korrigiert"] == 50 and k48["kunde_sicher"] == 50, k48
ok("S4 Kennzahlen je Woche: Eingänge, unklar, korrigiert, Kunde eindeutig, Ø bis Übernahme, Rückfragen")

# ---------------------------------------------------------------------------------------------- S5
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
alt = datetime.datetime.now() - datetime.timedelta(days=10)
x, _ = sa.anlegen(dict(quelle="ordner", eingang=alt, betreff="Rohrteile Halter"), [], "s5a", jetzt=alt)
x = sa.rueckfrage(sa.uebernehmen(x, jetzt=alt), "- Welcher Werkstoff?", jetzt=alt, fehlt=["werkstoff"])
y, _ = sa.anlegen(dict(quelle="ordner", eingang=alt, betreff="Bestellung 4711",
                       einordnung=dict(art=aa.BESTELLUNG, sicherheit=aa.SICHER_ART, sachgebiete=[])), [], "s5b",
                  jetzt=alt)
z, _ = sa.anlegen(dict(quelle="ordner", eingang=alt, betreff="Newsletter",
                       einordnung=dict(art=aa.WERBUNG, sicherheit=aa.SICHER_ART, sachgebiete=[])), [], "s5c",
                  jetzt=alt)
seite.neu_laden()
assert "nachfassen" in seite.schnell and seite.schnell["nachfassen"].text() == "Nachfassen"
seite.ordner = "in_bearbeitung"
seite.schnell["nachfassen"].setChecked(True)
assert [a.nr for a in seite.sichtbare()] == [x.nr]
seite.schnell["nachfassen"].setChecked(False)
seite.waehlen(x.nr)
kopf = seite.kopf.text()
assert "ohne Antwort" in kopf and "nachfassen:" in kopf, kopf
geoeffnet = []
seite.rueckfrage_ausfuehren = lambda *arg, **kw: geoeffnet.append(arg) or SimpleNamespace(returncode=0, stdout="", stderr="")
seite.f.stumm = False
import rohrlaser.anfragen_seite as asm  # noqa: E402
asm.QInputDialog.getMultiLineText = staticmethod(lambda *arg: (arg[3], True))
seite.nachfassen()
seite.f.stumm = True
assert geoeffnet, "Outlook nicht geöffnet"
x = sa.neu_lesen(x)
assert x.stand["nachgefasst"] == 1 and x.stand["rueckfrage"]
seite.ordner = ak.NEU
seite.wichtig_zuerst.setChecked(True)
reihe = [a.nr for a in seite.sichtbare()]
assert reihe.index(y.nr) < reihe.index(z.nr), reihe
seite.waehlen(y.nr)
assert "Wichtig: " in seite.kopf.text() and "Bestellung (+35)" in seite.kopf.text(), seite.kopf.text()
seite.wichtig_zuerst.setChecked(False)
db.einstellung_setzen(asm.ERINNERT, "")
x2, _ = sa.anlegen(dict(quelle="ordner", eingang=alt, betreff="Zweite"), [], "s5d", jetzt=alt)
sa.rueckfrage(sa.uebernehmen(x2, jetzt=alt), "- ?", jetzt=alt)
seite.neu_laden()
db.einstellung_setzen(asm.ERINNERT, "")
titel = seite._erinnern(jetzt=datetime.datetime.now().replace(hour=9))
assert "nachfassen" in titel, titel
d = seite.mitarbeiter_zeigen()
assert d.verlauf.rowCount() == 12 and sum(int(d.verlauf.item(r, 1).text()) for r in range(12)) == 4
assert [d.ziel.itemData(i) for i in range(d.ziel.count())] == ["art", "sachgebiet", "bearbeiter"]
d.ziel.setCurrentIndex(2)
assert "Bearbeiter:" in d.erkennung_zeigen() and "Noch kein Modell geprüft" in d.erkennung_zeigen()
d.trainieren()
assert (Path(sa.wurzel) / al.STAMM / "modell_bearbeiter.json").is_file()
ok("S5 Seite: Schnellfilter Nachfassen, Erinnerung öffnet Outlook, Wichtig zuerst mit Gründen, Tageserinnerung, "
   "Auswertung je Woche und Modell je Ziel")

# ---------------------------------------------------------------------------------------------- S6
from PySide6.QtCore import QUrl  # noqa: E402

from rohrlaser import anfragen_dokumente as adok  # noqa: E402
html_ = "".join(seite._erkannt_html(seite.akte(x.nr) or sa.neu_lesen(x)))
import re  # noqa: E402
for href in re.findall(r"href='([^']*)'", html_) + ["kunde-wahl:", "kunde-neu:", "kunde-ok:1", "angebot-hand:",
                                                       "ohne-kunde:", "nachtrag-gesehen:"]:
    assert QUrl(href).toString(), f"ungültiger Link {href}"          # sonst kommt beim Klick nichts an
aufrufe = []
for name in ("kunde_zuordnen", "kunde_neu_anlegen", "angebot_hand", "nachtrag_gesehen"):
    setattr(seite, name, (lambda n: lambda *a, **k: aufrufe.append(n))(name))
seite.waehlen(x.nr)
for href in ("kunde-wahl:", "kunde-neu:", "kunde-ok:1", "angebot-hand:", "nachtrag-gesehen:"):
    seite._link(QUrl(href))
assert aufrufe == ["kunde_zuordnen", "kunde_neu_anlegen", "kunde_zuordnen", "angebot_hand", "nachtrag_gesehen"], aufrufe
for quelle in (adok.__file__, asm.__file__):     # kein Link-Ziel mit „_“ (QUrl verwirft es still)
    falsch = re.findall(r"href=['\"]([a-z0-9]*_[a-z0-9_]*):", Path(quelle).read_text(encoding="utf-8"))
    assert not falsch, (quelle, falsch)
seite.ordner = ak.NEU
seite.liste_fuellen()
assert not seite.k_filter_zurueck.isVisibleTo(seite)
alle = seite.tabelle.rowCount()
seite.schnell["dringend"].setChecked(True)
seite.schnell["unklar"].setChecked(True)
seite.suche.setText("gibt es nicht")
assert seite.tabelle.rowCount() == 0 and seite.k_filter_zurueck.isVisibleTo(seite)
assert "Dringend" in seite.k_filter_zurueck.toolTip() and "Suche" in seite.k_filter_zurueck.toolTip()
assert "QToolButton:checked" in seite.schnell["dringend"].styleSheet()
assert seite.filter_zuruecksetzen() == alle and not any(b.isChecked() for b in seite.schnell.values())
assert seite.suche.text() == "" and not seite.k_filter_zurueck.isVisibleTo(seite)
ok("S6 Links Kunde ändern/anlegen kommen an (gültige QUrl), Schnellfilter sichtbar und zurücksetzbar")

print("Alle Tests bestanden.")
