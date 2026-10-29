"""Prüft, was zusätzlich über den gemeinsamen Ordner läuft (Patrick 28.10.2026 „Alle“): Anfragen im Unterordner
„Anfragen“ samt Zuweisen an einen Kollegen, Angebotsordner im Unterordner „Angebote“ (alte Ordner bleiben in der
eigenen Ablage), Notizen an Kollegen mit Wiedervorlage (Startseite, Quittung) und die Sicherung beim Beenden im
Unterordner „Sicherungen“.

Aufruf: python tests/test_teilen_ordner.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import anfragen, angebotsordner, teilen, teilen_fenster  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def arbeitsplatz(name, k):
    db = Datenbank(tmp / k / "rohrlaser.db")
    for n, w in (("benutzer_name", name), ("benutzer_kuerzel", k), ("teilen_ordner", str(gemeinsam)),
                 ("ablageordner", str(tmp / k / "Ablage"))):
        db.einstellung_setzen(n, w)
    return db


pb, mk = arbeitsplatz("Patrick", "PB"), arbeitsplatz("Martin", "MK")
alt = pb.angebot_neu(dict(kunde="Altkunde"))
alt_kopf = pb.angebot(alt)
lokal_alt = angebotsordner.ordner(tmp / "PB" / "Ablage", alt_kopf)        # Ordner aus der Zeit vorher
f_pb, f_mk = Hauptfenster(pb, tmp, stumm=True), Hauptfenster(mk, tmp, stumm=True)
teilen_fenster.abgleichen(f_pb)
teilen.lesen(mk, teilen.UEBERNEHMEN)
teilen_fenster.abgleichen(f_mk)
teilen_fenster.abgleichen(f_pb)

# ---------------------------------------------------------------- d Sicherung
pfade, fehler = pb.sicherungen(zusatz="beenden")
ziel = gemeinsam / "Sicherungen" / "PB"
assert fehler is None and any(Path(p).parent == ziel for p in pfade), pfade
assert len(list(ziel.glob("*.db"))) == 1 and ziel in pb.sicherungsordner()
pb.sicherungen()                                 # Knopf „Datensicherung erstellen“: nur lokal
assert len(list(ziel.glob("*.db"))) == 1
pb.einstellung_setzen("teilen_sicherung", "nein")
assert pb.sicherung_gemeinsam() is None and len(pb.sicherungen(zusatz="beenden")[0]) == 1
pb.einstellung_setzen("teilen_sicherung", "ja")
ok("Sicherung beim Beenden auch in Sicherungen/PB im gemeinsamen Ordner (abschaltbar), Wiederherstellen sieht sie")

# ---------------------------------------------------------------- b Angebotsordner
assert f_pb.ablage() == gemeinsam / "Angebote" and f_pb.ablage_lokal() == tmp / "PB" / "Ablage"
assert f_pb.angebot_ordner(alt_kopf) == lokal_alt, "alter Ordner bleibt in der eigenen Ablage"
neu = pb.angebot_neu(dict(kunde="Neukunde"))
o = f_pb.angebot_ordner(pb.angebot(neu))
assert o.parent == gemeinsam / "Angebote" and o.name.endswith("Neukunde"), o
teilen_fenster.abgleichen(f_pb)
teilen_fenster.abgleichen(f_mk)
fremd = next(a for a in mk.angebote() if a["nummer"] == pb.angebot(neu)["nummer"])
assert f_mk.angebot_ordner(fremd) == o, "Kollege findet denselben Ordner (PDFs des anderen)"
pb.einstellung_setzen("teilen_ablage", "nein")
assert f_pb.ablage() == tmp / "PB" / "Ablage"
pb.einstellung_setzen("teilen_ablage", "ja")
ok("Angebotsordner im gemeinsamen Ordner „Angebote“, Kollege öffnet denselben; ältere Ordner bleiben lokal")

# ---------------------------------------------------------------- a Anfragen
wurzel = anfragen.ordner(pb)
assert wurzel == gemeinsam / "Anfragen" and wurzel.is_dir()
alt_t = time.time() - 600
for name in ("Teil-1.stp", "Teil-2.stp"):
    (wurzel / name).write_text("ISO-10303-21;")
    os.utime(wurzel / name, (alt_t, alt_t))
liste = anfragen.suchen(wurzel)
assert len(liste) == 1 and liste[0].ordner is None
karte_pb = f_pb.start.anfragen
karte_pb.neu_laden(erzwingen=True)
assert karte_pb.karte.isVisibleTo(f_pb.start), "Karte mit dem gemeinsamen Anfrage-Ordner sichtbar"
assert karte_pb.zuweisen(karte_pb.anfragen[:1], "MK", "Kunde kennt dich") is True
liste = anfragen.suchen(wurzel)
assert liste[0].ordner is not None and liste[0].zugewiesen["an"] == "MK" and liste[0].zugewiesen["von"] == "PB"
assert "für MK („Kunde kennt dich“)" in liste[0].text()
karte_mk = f_mk.start.anfragen
karte_mk.neu_laden(erzwingen=True)
assert "1 für Sie" in karte_mk.titel.text() and karte_mk.liste.item(0).font().bold()
assert karte_mk.knopf_zuweisen.isVisibleTo(karte_mk.karte)
karte_pb.neu_laden(erzwingen=True)
assert "für Sie" not in karte_pb.titel.text()
mk.einstellung_setzen("anfrage_ordner", str(tmp / "eigen"))
assert anfragen.ordner(mk) == tmp / "eigen", "eingetragener Anfrage-Ordner hat Vorrang"
mk.einstellung_setzen("anfrage_ordner", "")
a = anfragen.zuweisen(liste[0], wurzel, "")
assert not a.zugewiesen and not anfragen.suchen(wurzel)[0].zugewiesen
anfragen.zuweisen(a, wurzel, "MK", "PB")
gesperrt = anfragen.sperren(anfragen.suchen(wurzel)[0], wurzel, "MK")
n, fehler = anfragen.verschieben(gesperrt, tmp / "Ziel")
assert n == 2 and not fehler and not gesperrt.ordner.exists(), "Zuweisung verschwindet mit der Anfrage"
ok("Anfragen im gemeinsamen Ordner: zuweisen (lose Dateien in Unterordner), „für MK“ für alle, fett beim Kollegen")

# ---------------------------------------------------------------- c Notizen
morgen = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
assert f_pb.angebote.notiz(neu, "MK", "bitte Preis prüfen") is True
assert f_pb.angebote.notiz(neu, "MK", "Kunde ruft an", morgen) is True
assert len([v for v in teilen._vorgaenge(pb).values() if v["art"] == teilen.NOTIZ]) == 2
b = teilen_fenster.abgleichen(f_mk)
assert [n["notiz"] for n in b["notizen"]] == ["bitte Preis prüfen", "Kunde ruft an"]
assert not teilen_fenster.abgleichen(f_mk)["notizen"], "nur einmal"
offen = teilen.notizen(mk, offen_nur=True)
assert len(offen) == 2 and {n["faellig_jetzt"] for n in offen} == {True, False}
st = f_mk.start
st.neu_laden()
assert st.notizen.count() == 2 and "(1)" in st.notiz_titel.text()
assert st.notizen.item(0).text().startswith("PB: bitte Preis prüfen")
st.notizen.setCurrentRow(0)
st.notiz_erledigt()
assert st.notizen.count() == 1 and len(teilen.notizen(mk, offen_nur=True)) == 1
teilen_fenster.abgleichen(f_pb)
assert not [v for v in teilen._vorgaenge(pb).values() if v["art"] == teilen.NOTIZ], "angekommen: Vorgang weg"
teilen_fenster.abgleichen(f_mk)
assert not teilen_fenster.abgleichen(f_mk)["notizen"]
assert "Notiz" in teilen.bericht_text(dict(notizen=offen))
try:
    teilen.notiz_senden(pb, "PB", "an mich")
    raise AssertionError("an sich selbst")
except teilen.TeilenFehler:
    pass
ok("Notizen an Kollegen: kommen einmal an, fällige zuerst, Wiedervorlage grau, Erledigt, Absender sieht Quittung")

for f in (f_pb, f_mk):
    f.close()
print("OK: weitere Inhalte im gemeinsamen Ordner")
