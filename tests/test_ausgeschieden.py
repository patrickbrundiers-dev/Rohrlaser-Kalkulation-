"""Gemeinsamen Ordner ausbauen, Paket C (Patrick 31.10.2026): ausgeschiedene Mitarbeiter, Lizenzen der Plätze.

Prüft: nur der Admin trägt einen Kollegen aus; seine Angebote übernimmt der Admin oder sie gehen als Übergabe an einen
Kollegen; sein Ordner liegt danach im Archiv und wird nicht mehr gelesen; die Kollegen bekommen die Angebote ohne
„doppelte Nummer“ unter dem neuen Bearbeiter, der Kollege mit Übergabe als eigenes; der Ausgeschiedene verschwindet aus
der Liste der Kollegen; startet sein Programm noch einmal, legt es nichts mehr ab; Lizenzhinweise: aktiver Platz ohne
gültige Lizenz, dieselbe Lizenz an zwei Kürzeln, lange nicht abgeglichene Plätze zählen nicht; die Prüfung und die
Übersicht zeigen das; das Fenster trägt aus.

Aufruf: python tests/test_ausgeschieden.py
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import admin_schutz, ordner_pruefung, teilen  # noqa: E402
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
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("teilen_ordner", str(gemeinsam))
    return db


pb, mk, sk = arbeitsplatz("Patrick", "PB"), arbeitsplatz("Martin", "MK"), arbeitsplatz("Sandra", "SK")
teilen.abgleichen(pb)
teilen.abgleichen(mk, teilen.UEBERNEHMEN)
teilen.abgleichen(sk, teilen.UEBERNEHMEN)
ids_sk = [sk.angebot_neu(dict(kunde=f"Kunde {i}", datum=f"2026-10-0{i + 1}")) for i in range(3)]
nummern_sk = [sk.angebot(i)["nummer"] for i in ids_sk]
teilen.abgleichen(sk)
teilen.abgleichen(pb)
teilen.abgleichen(mk)
von_sk = teilen.angebote_von(pb, "SK")
assert sorted(a["nummer"] for a in von_sk) == sorted(nummern_sk) and von_sk[0]["kunde"] == "Kunde 2"
ok("Angebote eines Kollegen aufgelistet (neueste zuerst)")

try:
    teilen.ausgeschieden(mk, "SK", {}, ich_admin=False)
    raise AssertionError("ohne Admin-Recht")
except teilen.TeilenFehler as e:
    assert "Admin" in str(e)
try:
    teilen.ausgeschieden(pb, "PB", {})
    raise AssertionError("sich selbst")
except teilen.TeilenFehler:
    pass
assert (gemeinsam / "Rohrlaser_SK").is_dir()
ok("Nur der Admin trägt aus, nicht sich selbst; vorher bleibt alles, wie es ist")

an_mk = next(a["id"] for a in von_sk if a["nummer"] == nummern_sk[0])
admin = admin_schutz.Sitzung()
admin.freischalten()
admin_schutz.SITZUNG = admin                    # PB ist als Admin freigeschaltet
erg = teilen.ausgeschieden(pb, "SK", {an_mk: "MK"})
admin_schutz.SITZUNG = None
assert erg["uebernommen"] == 2 and erg["uebergeben"] == 1, erg
assert not (gemeinsam / "Rohrlaser_SK").exists() and erg["archiv"].parent.name == "Archiv"
assert (erg["archiv"] / "Rohrlaser_SK" / "haupt.sqlite").is_file()
eigene = {r[0]: (r[1], r[2]) for r in pb.con.execute("SELECT nummer, fremd, bearbeiter FROM angebote")}
assert eigene[nummern_sk[1]] == (None, "PB") and eigene[nummern_sk[2]] == (None, "PB")
assert eigene[nummern_sk[0]] == ("MK", "MK")              # Übergabe unterwegs
assert "SK" not in teilen.kollegen(pb) and set(teilen.andere_dateien(pb)) == {"MK"}
ok("Ausgetragen: Ordner im Archiv, zwei Angebote beim Admin, eines als Übergabe an MK")

b = teilen.abgleichen(mk)
assert not any("doppelte" in h for h in b["hinweise"]), b["hinweise"]
bei_mk = {r[0]: r[1] for r in mk.con.execute("SELECT nummer, fremd FROM angebote")}
assert bei_mk[nummern_sk[0]] is None, bei_mk                  # übernommen als eigenes
assert bei_mk[nummern_sk[1]] == "PB" and bei_mk[nummern_sk[2]] == "PB"
assert "SK" not in teilen.kollegen(mk)
b = teilen.abgleichen(pb)
assert not any("doppelte" in h for h in b["hinweise"]), b["hinweise"]
assert {r[0]: r[1] for r in pb.con.execute("SELECT nummer, fremd FROM angebote")}[nummern_sk[0]] == "MK"
ok("Beim Kollegen: Angebote unter dem neuen Bearbeiter, Übergabe als eigenes, keine doppelten Nummern, SK weg")

try:
    teilen.schreiben(sk)
    raise AssertionError("archiviertes Kürzel schreibt nicht")
except teilen.TeilenFehler as e:
    assert "ausgeschieden" in str(e)
assert not (gemeinsam / "Rohrlaser_SK").exists()
ok("Das Programm des Ausgeschiedenen legt nichts mehr ab (Hinweis: neues Kürzel)")

# ---------------------------------------------------------------- Lizenzen
gueltig = dict(art="benutzer", lizenz_id="L-1", stufe="gueltig", gueltig_bis="2027-01-31")
pb.einstellung_setzen(admin_schutz.LIZENZ_INFO, dict(gueltig, stufe="admin", lizenz_id="L-ADMIN"))
m = dict(pb.einstellung("teilen_mitarbeiter"))
jetzt = datetime.datetime.now().isoformat(timespec="seconds")
m["MK"] = dict(m["MK"], stand=jetzt, lizenz=dict(gueltig))
m["AB"] = dict(name="Alt", stand="2026-01-01T08:00:00", lizenz=dict(gueltig, stufe="lesemodus"))
pb.einstellung_setzen("teilen_mitarbeiter", m)
assert teilen.lizenz_hinweise(pb) == []
m["MK"]["lizenz"] = dict(gueltig, stufe="lesemodus", gueltig_bis="2026-10-01")
m["XY"] = dict(name="Neu", stand=jetzt, lizenz=dict(gueltig, lizenz_id="L-ADMIN"))
pb.einstellung_setzen("teilen_mitarbeiter", m)
h = teilen.lizenz_hinweise(pb)
admin_schutz.SITZUNG = admin
assert "2 Lizenzhinweise" in ordner_pruefung.kurz(pb)
admin_schutz.SITZUNG = None
assert "2 Lizenzhinweise" not in ordner_pruefung.kurz(pb)       # nur der Admin sieht sie in der Statusleiste
assert any(t.startswith("MK arbeitet ohne gültige Lizenz") for t in h), h
assert "PB und XY nutzen dieselbe Lizenz (L-ADMIN)" in h and not any("AB" in t for t in h), h
befunde = ordner_pruefung.pruefen(pb, geschwindigkeit=False)
assert sum(1 for b in befunde if b["titel"] == "Lizenz") == 2
ok("Lizenzen: ohne gültige Lizenz und doppelte Lizenz gemeldet, alte Plätze nicht; Prüfung zeigt sie")
m.pop("XY")
m["MK"]["lizenz"] = dict(gueltig)
pb.einstellung_setzen("teilen_mitarbeiter", m)

# ---------------------------------------------------------------- Oberfläche
neu = pb.angebot_neu(dict(kunde="Kunde MK", datum="2026-10-30"))     # noch ein Kollege zum Austragen: MK
teilen.abgleichen(mk)
teilen.abgleichen(pb)
f = Hauptfenster(pb, tmp, stumm=True)
admin_schutz.SITZUNG = admin
d = f.kollegen_zeigen()
assert not d.weg.isHidden()
zeile = [i for i in range(d.liste.rowCount()) if d.liste.item(i, 0).data(0x0100) == "MK"][0]
d.liste.selectRow(zeile)
assert d.weg.isEnabled() and d.notiz.isEnabled()
d.vorgabe = {}
ad = d._ausgeschieden()
assert ad.liste.rowCount() == len(teilen.angebote_von(pb, "MK")) or not (gemeinsam / "Rohrlaser_MK").exists()
assert not (gemeinsam / "Rohrlaser_MK").exists() and "MK" not in teilen.kollegen(pb)
assert len(list((gemeinsam / "Archiv").iterdir())) == 2
d.close()
assert neu
ok("Fenster: Knopf Ausgeschieden … (Admin), trägt den markierten Kollegen aus")

print("OK: Gemeinsamen Ordner ausbauen, Paket C (ausgeschiedene Mitarbeiter, Lizenzen)")
