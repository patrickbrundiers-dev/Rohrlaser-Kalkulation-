"""Test: Pack-Logik im Frachtrechner (Patrick 29.10.2026, Freigabe „B a a a“).

- Knopf 'Aus Angebot laden …' übernimmt Gewicht, längstes Teil, Kunde und Bezeichnung eines Angebots und packt nach
  Maßen und Stückzahl (paletten.py) statt nur nach Gewicht.
- Günstigste Kombination: jeder mögliche Standard-Ladungsträger wird gepackt und mit dem Tarif gerechnet, lange Teile
  bleiben auf Langgut; übernommen wird der günstigste, der Vergleich steht in der Packliste.
- Packliste mit Skizze je Ladungsträger (Draufsicht, Seitenansicht), zeichnet ohne Fehler.
- Fenster 'Fracht berechnen …' im Angebot nutzt denselben Vorschlag.
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import fracht, fracht_angebot, paletten, rechnen  # noqa: E402
from rohrlaser.angebot import aktiv  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.fracht_seite import FrachtDialog  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
db.einstellung_setzen("absender_plz", "33129")
db.fracht_richtwerte_laden("33129")
aid = beispiel_angebot.anlegen(db)
fenster = Hauptfenster(db, stumm=True)
fenster.resize(1300, 900)
r = fenster.fracht.rechner
fenster.fracht.zeigen(r)
r.plz.setText("20095")

# vorher: nur Gewicht und längstes Teil -> 1 Langgut
r.netto.setValue(406.1)
r.max_laenge.setText("2150")
r.packvorschlag()
assert [e["lht_id"] for e in r.lht_eintraege()] == ["LG"] and not r.packliste_box.isVisibleTo(r)
ok("Ohne Angebot: Packvorschlag nur nach Gewicht und längstem Teil (1 × Langgut), keine Packliste")

assert r.aus_angebot_laden(aid)
pos = db.positionen(aid)
kopf = db.angebot(aid)
werte = [rechnen.position_werte(p, kopf, db.kontext(), db.tabellen()) if aktiv(p) else None for p in pos]
netto, laenge, _ = fracht_angebot.ware(pos, werte)
assert abs(r.netto.value() - round(netto, 1)) < 0.06 and r.max_laenge.text() == "2.150", (r.netto.value(), netto)
assert r.bezeichnung.text().endswith(kopf["nummer"]) and "152 Teile" in r.ware_text.text(), r.ware_text.text()
ok(f"Aus Angebot geladen: {netto:.1f} kg, längstes Teil 2.150 mm, 152 Teile, Bezeichnung mit Angebotsnummer")

# günstigste Kombination: alle Kandidaten gerechnet, sortiert, der erste übernommen
v = r.vergleich_liste
ids = {x["std_id"] for x in v}
assert {"EUR", "EW", "IND", "GB", "SOND"} <= ids and "LG" not in ids and "SL" not in ids, ids
preise = [x["gesamt"] for x in v if x["gesamt"] is not None]
assert preise == sorted(preise) and v[0]["gesamt"] == min(preise), preise
assert r.lht_eintraege()[0]["lht_id"] == v[0]["lht"][0]["lht_id"]
e = r.rechnen()
assert e["gesamt"] == v[0]["gesamt"], (e["gesamt"], v[0]["gesamt"])
eur = next(x for x in v if x["std_id"] == "EUR")
assert any(t["lht_id"] == "LG" for t in eur["lht"]), eur["lht"]
assert v[0]["gesamt"] < eur["gesamt"], (v[0], eur["gesamt"])
assert "günstigste" in r.vergleich.text()
ok(f"Günstigste Kombination: {v[0]['bezeichnung']} {fracht.euro(v[0]['gesamt'])} statt Europalette + Langgut "
   f"{fracht.euro(eur['gesamt'])}; Vergleich aller {len(v)} Ladungsträger in der Packliste")

# gleiche Rechnung wie paletten.packen mit dem gewählten Träger
pl = paletten.packen(pos, werte, db.fracht_daten()["lht"], v[0]["std_id"], db.einstellung("fracht_lht_langgut"),
                     {n: db.einstellung(n) for n in fracht_angebot.PALETTEN_EINST})
assert pl["anzahl"] == r.packliste["anzahl"] and pl["je_lht"] == r.packliste["je_lht"]
stueck = sum(n for p in r.packliste["paletten"] for _, n in p["inhalt"])
assert stueck == r.packliste["gesamt_stueck"] == 152, stueck
for p in r.packliste["paletten"]:
    assert p["schichten"] and p["masse"][0] > 0 and p["hoehe_max"] == 1200
    assert p["hoehe"] <= p["hoehe_max"] + 1e-6, p
    for s in p["schichten"]:
        geo = r.packliste["stuecke"][s["k"]]["plan_geo"]
        assert geo and geo["reihen"] >= 1 and geo["teil"][0] > 0
ok(f"Packliste: {paletten.kurz(r.packliste)}, alle 152 Teile eingeplant, Höhe je Palette höchstens 1.200 mm, "
   "Lagengeometrie für die Skizze vorhanden")

# Skizze zeichnet (sichtbar, Höhe nach Inhalt)
app.processEvents()
assert r.packliste_box.isVisibleTo(r) and r.packliste_ansicht.minimumHeight() > 150
bild = r.packliste_ansicht.grab()
assert not bild.isNull() and bild.height() > 150
ok("Skizze je Ladungsträger (Draufsicht, Seitenansicht, Aufbau) gezeichnet")

# teurer Standard-Träger wird nicht gewählt, auch wenn er eingestellt ist
db.einstellung_setzen("fracht_lht_standard", "IND")
r.packvorschlag()
assert r.vergleich_liste[0]["std_id"] != "IND" or r.vergleich_liste[0]["gesamt"] == min(
    x["gesamt"] for x in r.vergleich_liste if x["gesamt"] is not None)
db.einstellung_setzen("fracht_lht_standard", "EUR")
ok("Eingestellter Standard-Ladungsträger gilt nur bei gleichem Preis")

# Fenster 'Fracht berechnen …' im Angebot: gleicher Vorschlag, kein Laden-Knopf
seite = fenster.angebot_oeffnen(aid)
seite.kopf["fracht_sendung"] = None
dlg = FrachtDialog(seite)
dlg.rechner.plz.setText("20095")
dlg.rechner.packvorschlag()
assert dlg.rechner.laden_knopf.isHidden() and dlg.rechner.vergleich_liste
assert dlg.rechner.vergleich_liste[0]["std_id"] == v[0]["std_id"]
dlg.reject()
ok("Fracht berechnen im Angebot: derselbe günstigste Vorschlag mit Packliste")

fenster.close()
db.schliessen()
print("OK: Pack-Logik im Frachtrechner")
