"""Abnahme Schweißbaugruppe 'Rahmen R1' (Verbesserungen T3 und T4, tests/beispiel_baugruppe.py).

- A1 Handrechnung: Herstellkosten je Baugruppe = 114,00 € × (1 + Zuschlag Fertigung) + 15,00 € × (1 + Zuschlag
  Fremdleistung), Einmalkosten 130 € in der Stufe wie Rüsten.
- A2 Festwerte: Kalkulation, Angebot und drei Mengenstufen gleichen tests/abnahme_baugruppe_r1.json bitgleich; jede
  Änderung an der Baugruppen-Rechnung fällt sofort auf (neu schreiben nur bewusst: --neu).
- A3 Staffel-Seite im Hintergrund (T3): die Hintergrundrechnung der drei Stufen ergibt dieselben Zeilen wie die Rechnung
  im Vordergrund, nach einer Änderung an der Baugruppe ist nur sie veraltet und wird neu gerechnet.

Aufruf: python tests/test_baugruppe_abnahme.py [--neu]
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_baugruppe as bsp  # noqa: E402
from rohrlaser import ausgabe, baugruppe, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

FESTWERTE = HIER / "abnahme_baugruppe_r1.json"


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


def stufen_kurz(zeilen):
    return [dict(menge=z["menge"], preis_einheit=z["preis_einheit"], preis_gesamt=z["preis_gesamt"],
                 bg_einmalig=z["preis"].get("bg_einmalig")) for z in zeilen]


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("aufschlag_blech", None)   # Regeln der Artikel prüfen: ohne Aufschlag im Angebot
db.einstellung_setzen("aufschlag_zukauf", None)
fenster = Hauptfenster(db, tmp, stumm=True)
a = bsp.anlegen(db)
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
kopf, pos, k, tab, einst = s.kopf, s.positionen, s.k, s.tabellen, s.einst

# ------------------------------------------------------------------ A1 Handrechnung
saetze = rechnen.stundensaetze(tab)
r = baugruppe.rechnen(pos[0], tab, saetze)
nah(r["eigen"], bsp.EIGEN, "eigen je Baugruppe")
nah(r["fremd"], bsp.FREMD, "Fremdleistung je Baugruppe")
nah(r["einmal_gesamt"], bsp.EINMAL, "Einmalkosten je Auftrag")
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
zf, zfl = (einst.get(n) or 0 for n in ("zuschlag_fertigung", "zuschlag_fremdleistung"))
herstell = bsp.EIGEN * (1 + zf) + bsp.FREMD * (1 + zfl)
nah(zeilen[0]["herstell_teil"], herstell, "Herstellkosten je Baugruppe")
nah(summen["baugruppe_eigen"], 2 * bsp.EIGEN, "Summe Schweißbaugruppen")
st20 = staffeln.stufe_rechnen(kopf, pos, "Rahmen R1", 20, k, tab, einst)
nah(dict((n, x) for n, x, _ in st20["bausteine"]["ruesten"])["Schweißbaugruppe einmalig"], bsp.EINMAL,
    "Einmalkosten in der Stufe wie Rüsten")
ok(f"A1 Handrechnung Rahmen R1: Herstellkosten {herstell:.2f} € je Baugruppe, Einmalkosten {bsp.EINMAL:.0f} € je Stufe")

# ------------------------------------------------------------------ A3 Staffel-Seite: Vordergrund = Hintergrund
st = s.st_seite
vorne = s.staffelpreise_rechnen()
assert len(vorne) == 3 and all(z["preis_einheit"] for z in vorne), vorne
assert [z["menge"] for z in vorne] == list(bsp.STUFEN)
assert vorne[0]["preis_einheit"] > vorne[1]["preis_einheit"] > vorne[2]["preis_einheit"]
g = baugruppe.lesen(pos[0]["baugruppe"])
g["arbeitsgaenge"][0]["zeit_min"] = 7                          # Schleifen 6 → 7 min: alle Stufen veraltet
db.position_aendern(pos[0]["id"], "baugruppe", baugruppe.speichern(g))
s.neu_laden()
assert st.anzahl_veraltet() == 3, st.anzahl_veraltet()
assert st.rechnen(alle=False) is not None and st.anzahl_veraltet() == 0
hinten = st.zeilen
for z1, z2 in zip(vorne, hinten):
    assert z2["preis_einheit"] > z1["preis_einheit"], (z1["menge"], z1["preis_einheit"], z2["preis_einheit"])
neu_vorne = staffeln.rechnen_alle(*st._args(), stufen_daten=st._daten())
assert stufen_kurz(neu_vorne) == stufen_kurz(hinten), (stufen_kurz(neu_vorne), stufen_kurz(hinten))
g["arbeitsgaenge"][0]["zeit_min"] = 6
db.position_aendern(pos[0]["id"], "baugruppe", baugruppe.speichern(g))
s.neu_laden()
assert st.rechnen(alle=False) is not None and stufen_kurz(st.zeilen) == stufen_kurz(vorne)
ok("A3 Staffel-Seite: 3 Stufen über den Knopf = direkt gerechnet, Änderung an der Baugruppe macht alle Stufen veraltet")

# ------------------------------------------------------------------ A2 Festwerte
kopf, pos = s.kopf, s.positionen
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, einst)
ang = ausgabe.angebot(kopf, pos, zeilen, k, db.einstellungen(), st.zeilen)
ist = dict(
    summen={n: round(summen[n], 6) for n in ("herstell", "verkauf", "baugruppe_eigen", "baugruppe_fremd", "material",
                                              "laser") if n in summen},
    zeilen=[dict(pos=p["pos"], herstell_teil=round(z["herstell_teil"], 6), preis_teil=round(z["preis_teil"], 6))
            for p, z in zip(pos, zeilen) if z],
    angebot=dict(netto=ang["netto"], zeilen=[(z["art"], z.get("pos"), z.get("menge"), z.get("preis"))
                                             for z in ang["zeilen"]]),
    stufen=stufen_kurz(st.zeilen))
ist = json.loads(json.dumps(ist))
if "--neu" in sys.argv or not FESTWERTE.exists():
    FESTWERTE.write_text(json.dumps(ist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("Festwerte neu geschrieben:", FESTWERTE)
soll = json.loads(FESTWERTE.read_text(encoding="utf-8"))
for teil in ("summen", "zeilen", "angebot", "stufen"):
    assert ist[teil] == soll[teil], f"{teil} weicht ab:\n ist  {ist[teil]}\n soll {soll[teil]}"
ok(f"A2 Festwerte bitgleich: netto {ist['angebot']['netto']:.2f} €, Stufen "
   + ", ".join(f"{x['menge']}: {x['preis_einheit']:.2f} €" for x in ist["stufen"]))

print("\nAbnahme Rahmen R1 bestanden.")
