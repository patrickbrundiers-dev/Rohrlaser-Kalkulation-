"""Prüft die Oberfläche der Zusammenarbeit über den gemeinsamen Ordner (teilen_fenster.py, Patrick 28.10.2026):
automatischer Abgleich (nur bei Neuem lesen, nur bei Änderungen schreiben), Stand in der Statusleiste, „● geöffnet“
in der Liste und im Hinweis des Angebots, Angebot an Kollegen übergeben (Vorgang-Menü) und zurücknehmen, Übernahme
anfragen (Knopf im gelben Hinweis), Konflikte im Dialog wiederherstellen.

Aufruf: python tests/test_teilen_zusammenarbeit_fenster.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import teilen, teilen_fenster  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def arbeitsplatz(name, k):
    db = Datenbank(tmp / name / "rohrlaser.db")
    for n, w in (("benutzer_name", name), ("benutzer_kuerzel", k), ("teilen_ordner", str(gemeinsam))):
        db.einstellung_setzen(n, w)
    return db


pb, mk = arbeitsplatz("Patrick", "PB"), arbeitsplatz("Martin", "MK")
a1 = pb.angebot_neu(dict(kunde="Kunde A"))
a2 = pb.angebot_neu(dict(kunde="Kunde B"))
n1, n2 = pb.angebot(a1)["nummer"], pb.angebot(a2)["nummer"]
f_pb, f_mk = Hauptfenster(pb, tmp, stumm=True), Hauptfenster(mk, tmp, stumm=True)
assert teilen_fenster.abgleichen(f_pb) is not None
teilen.lesen(mk, teilen.UEBERNEHMEN)
assert teilen_fenster.abgleichen(f_mk) is not None
assert teilen_fenster.abgleichen(f_pb) is not None
assert f_pb.teilen_status.text().startswith("⇄ abgeglichen") and "MK" in f_pb.teilen_status.toolTip()
assert teilen_fenster.takt_ms(pb) == 60_000
pb.einstellung_setzen("teilen_takt", 0)
assert teilen_fenster.takt_ms(pb) == 0
pb.einstellung_setzen("teilen_takt", 2)
ok("Statusleiste „⇄ abgeglichen 14:32“ mit Kollegen im Tipp; Abgleich jede Minute (Einstellung, 0 = aus)")

# ---------------------------------------------------------------- automatischer Abgleich
teilen_fenster.auto_abgleich(f_pb)
assert teilen_fenster.auto_abgleich(f_pb) is None, "nichts Neues: weder lesen noch schreiben"
datei = gemeinsam / "Rohrlaser_PB" / "haupt.sqlite"
vorher = datei.stat().st_mtime_ns
seite = f_pb.angebot_oeffnen(a1)
b = teilen_fenster.auto_abgleich(f_pb)
assert b is not None and datei.stat().st_mtime_ns != vorher, "Angebot geöffnet: wird geschrieben"
assert n1 in teilen.info_lesen(datei)["offen"]
assert teilen_fenster.auto_abgleich(f_pb) is None
pb.angebot_aendern(a2, "kunde", "Kunde B neu")
assert teilen_fenster.auto_abgleich(f_pb) is not None, "eigene Änderung: wird geschrieben"
b = teilen_fenster.auto_abgleich(f_mk)
assert b is not None and b["angebote_geaendert"] == 1
assert teilen.offen_bei(mk, n1)[0] == "PB"
ok("automatischer Abgleich: nur bei Neuem; geöffnete Angebote und Änderungen gehen hinaus, Kollege liest sie")

au = f_mk.angebote
au.neu_laden()
spalte = [s[0] for s in au.SPALTEN].index("Bearbeiter")
zeile = next(r for r in range(au.modell.rowCount()) if au.modell.zeilen[r]["nummer"] == n1)
assert au.modell.data(au.modell.index(zeile, spalte)) == "PB ● geöffnet"
fid1 = au.modell.zeilen[zeile]["id"]
fs = f_mk.angebot_oeffnen(fid1)
assert "gerade geöffnet" in fs.fremd_text.text()
assert fs.anfrage_knopf.isVisibleTo(fs) and fs.anfrage_knopf.isEnabled() and not fs.zurueck_knopf.isVisibleTo(fs)
ok("„PB ● geöffnet“ in der Liste und „PB hat es gerade geöffnet“ im Hinweis; Knopf Übernahme anfragen")

f_pb.angebot_schliessen(a1)
assert teilen_fenster.auto_abgleich(f_pb) is not None, "geschlossen: wird geschrieben"
assert teilen_fenster.auto_abgleich(f_mk) is not None
assert au.modell.data(au.modell.index(zeile, spalte)) == "PB", "Liste ohne ● geöffnet, ohne Knopf Aktualisieren"
assert "gerade geöffnet" not in fs.fremd_text.text()
seite = f_pb.angebot_oeffnen(a1)
teilen_fenster.auto_abgleich(f_pb)
teilen_fenster.auto_abgleich(f_mk)
assert au.modell.data(au.modell.index(zeile, spalte)) == "PB ● geöffnet" and "gerade geöffnet" in fs.fremd_text.text()
ok("nur geöffnet/geschlossen beim Kollegen: Liste und Hinweis folgen beim automatischen Abgleich")

# ---------------------------------------------------------------- Übernahme anfragen
assert fs._anfragen("bitte an mich") is True
assert not fs.anfrage_knopf.isEnabled() and fs.anfrage_knopf.text() == "Übernahme angefragt"
b = teilen_fenster.abgleichen(f_pb)
assert [a["nummer"] for a in b["anfragen"]] == [n1], "stumm: nicht gefragt, Anfrage bleibt"
teilen.beantworten(pb, b["anfragen"][0], True)
seite.neu_laden()
assert seite.fremd() == "MK" and seite.zurueck_knopf.isVisibleTo(seite) and "übergeben" in seite.fremd_text.text()
teilen_fenster.abgleichen(f_pb)
b = teilen_fenster.abgleichen(f_mk)
assert [u["nummer"] for u in b["uebernommen"]] == [n1]
assert fid1 in f_mk.offen and not f_mk.offen[fid1].fremd() and f_mk.offen[fid1].kopf_bereich.isEnabled()
ok("Übernahme anfragen und zusagen: das offene Angebot wird beim Kollegen bearbeitbar")

# ---------------------------------------------------------------- übergeben und zurücknehmen
pb_au = f_pb.angebote
assert pb_au.uebergeben(a2, "MK", "eilt") is True
assert pb.angebot(a2)["fremd"] == "MK"
s2 = f_pb.angebot_oeffnen(a2)
assert s2.zurueck_knopf.isVisibleTo(s2) and not s2.anfrage_knopf.isVisibleTo(s2)
assert s2._zuruecknehmen() is True and not pb.angebot(a2)["fremd"]
assert pb_au.uebergeben(a2, "MK", "jetzt aber") is True
b = teilen_fenster.abgleichen(f_mk)
assert [(u["nummer"], u["notiz"]) for u in b["uebernommen"]] == [(n2, "jetzt aber")]
teilen_fenster.abgleichen(f_pb)
s2 = f_pb.offen[a2]
assert not s2.zurueck_knopf.isVisibleTo(s2), "übernommen: nicht mehr zurücknehmen"
assert f_mk.offen.get(fid1) is not None
assert pb_au.uebergeben(a2, "XY") is False, "fremdes Angebot: Übergeben gesperrt"
ok("Vorgang → An Kollegen übergeben (mit Notiz), zurücknehmen, solange nicht übernommen")

# ---------------------------------------------------------------- Konflikte
kunde = pb.zeilen("kunden", True)[0]
k_mk = next(z for z in mk.zeilen("kunden", True) if z["uid"] == kunde["uid"])
pb.aendern("kunden", kunde["id"], "bemerkung", "A")
mk.aendern("kunden", k_mk["id"], "bemerkung", "B")
teilen_fenster.abgleichen(f_pb)
time.sleep(0.01)
b = teilen_fenster.abgleichen(f_mk)
assert len(b["konflikte"]) == 1 and "Konflikte" in f_mk.teilen_status.text()
assert f_mk.letzte_aktion and f_mk.letzte_aktion[0] == "Konflikte …"
d = f_mk.konflikte_zeigen()
assert d.liste.count() == 1 and "gilt die Änderung von MK" in d.liste.item(0).text()
d.liste.setCurrentRow(0)
assert d.zurueck.isEnabled()
d._erledigt(True)
assert next(z for z in mk.zeilen("kunden", True) if z["uid"] == kunde["uid"])["bemerkung"] == "A"
assert not d.zurueck.isEnabled() and "wiederhergestellt" in d.liste.item(0).text()
assert "Konflikte" not in f_mk.teilen_status.text()
ok("Konflikt: Hinweis mit Knopf, Dialog zeigt wer gewann, andere Fassung wiederhergestellt")

for f in (f_pb, f_mk):
    f.teilen_takt = None
    f.close()
print("OK: Oberfläche Zusammenarbeit über den gemeinsamen Ordner")
