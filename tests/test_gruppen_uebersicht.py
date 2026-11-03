"""Prüft „Sätze und Schweißbaugruppen übersichtlicher“ (Patrick 03.11.2026, Freigabe „Alle Empfehlungen“):
- G1 Schweißbaugruppen grün wie Sätze (Spalte Satz „⚙ Name · n Stk.“), Status in einer Zeile (Tooltip ganz)
- G2 Kalkulation (kompakt und alle Spalten) in der Reihenfolge der Positionsliste: Baugruppe mit Bezeichnung,
     Einzelteile darunter, Zeilenkopf ▾ └, zuklappbar; „Alle Gruppen zuklappen“ wird je Angebot gemerkt
- G3 Unterzeile „Programmieren“ nur noch zusammen mit echten Arbeitsschritten oder von Hand
- G4 Baugruppen-Editor: Einzelteile zuerst die der Baugruppe, freie nach Satz; nur Teile der Baugruppe sichtbar,
     „Alle Positionen zeigen“ und Suche
- G5 Schweißnaht: Rechenweg je Nahtgruppe, Vorkalkulation (Heften, Positionieren, Wenden) als Vorgabe an

Aufruf: python tests/test_gruppen_uebersicht.py   (QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QItemSelectionModel, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import baugruppe, satzgruppen, stil, unterzeilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.neue_position import SCHWEISS  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ ohne Oberfläche
assert satzgruppen.kurz("OK") == "OK"
k = satzgruppen.kurz("HINWEIS: Schweißzeit aus ungeprüften Richtwerten")
assert k.startswith("HINWEIS: Schweißzeit") and k.endswith("…") and len(k) <= 34, k
for thema in ("Hell", "Dunkel", "Hoher Kontrast"):
    vorne = stil.umsetzen(satzgruppen.TEXTE[satzgruppen.BG], thema)
    hinten = stil.umsetzen(satzgruppen.FLAECHEN[satzgruppen.BG], thema)
    assert stil.kontrast(vorne, hinten) >= 4.5 and stil.kontrast(stil.umsetzen(stil.TEXT, thema), hinten) >= 4.5
z = dict(prog_min=5.0, programmierung_anteil=0.25, stueck=20)
assert unterzeilen.schritte(dict(stueck=20), z) == []                               # nur Programmieren: keine Zeile
assert [t.split(unterzeilen.TRENNER)[0] for t, _ in unterzeilen.schritte(dict(stueck=20), dict(z, prog_hand=True))] \
    == ["Programmieren"]                                                              # von Hand: bleibt sichtbar
naht = dict(verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=120, anzahl=8, heftpunkte=3,
            stand=dict(verfahren=True, min_m=1.33, lichtbogen=35, heft_s=8, satz_id="Schweißen"))
w = baugruppe.naht_rechnen(naht, {}, {"Schweißen": 60})
assert w["rechenweg"].startswith("0,96 m × 1,33 min/m ÷ 35 % Lichtbogen = 3,6 min + Heften 24 × 8 s = 3,2 min"), \
    w["rechenweg"]
assert "ohne Heftpunkte" in baugruppe.naht_rechnen(dict(naht, heftpunkte=None), {}, {"Schweißen": 60})["rechenweg"]
ok("G1/G3/G5 Kurztext Status, Grün lesbar in allen Themes, Programmieren allein ohne Unterzeile, Rechenweg Naht")

# ------------------------------------------------------------------ Angebot mit Satz und zwei Baugruppen
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert db.einstellung("schweiss_vk_step") == "ja"
f = Hauptfenster(db, tmp, stumm=True)
f.resize(1600, 1000)
f.show()
next(s for s in f.seiten if s.t.name == "schweissverfahren").schweiss_richtwerte(bestaetigt=True)
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T03"))


def neu(nr, art, satz=None, je=None, laenge=600):
    w_ = dict(pos=nr, artikel=art, bezeichnung=art, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=laenge,
              stueck=4 * (je or 1), schneidweg=320, einstiche=2)
    if satz:
        w_.update(satz=satz, je_satz=je)
    return db.position_neu(a, w_)


for nr, satz in ((10, "Regal"), (20, "Regal")):
    neu(nr, f"R{nr}", satz, 2)
neu(30, "E30")
gestelle = [[neu(40 + 10 * k_ + 40 * g, f"G{g}{k_}", laenge=500 + 100 * k_) for k_ in range(2)] for g in range(2)]
s = f.angebot_oeffnen(a)
for g, ids in enumerate(gestelle):
    sm = s.pos_ansicht.selectionModel()
    sm.clearSelection()
    for r, p in enumerate(s.positionen):
        if p["id"] in ids:
            sm.select(s.pos_modell.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def anlegen(d, g=g):
        assert d.vk_auto.isChecked()                                      # Vorkalkulation als Vorgabe an (G5)
        sichtbar = [t["_q"]["artikel"] for r, t in enumerate(d.teile) if not d.teile_tab.isRowHidden(r)]
        assert sichtbar == [f"G{g}0", f"G{g}1"], sichtbar                  # nur Teile der Baugruppe (G4)
        assert d.teile[0]["drin"] and d.teile[1]["drin"] and d.teile[2]["_q"]["satz"] == "Regal"
        d.teile_alle.setChecked(True)
        assert not any(d.teile_tab.isRowHidden(r) for r in range(len(d.teile)))
        d.teile_suche.setText("e30")
        assert [t["_q"]["artikel"] for r, t in enumerate(d.teile) if not d.teile_tab.isRowHidden(r)] == ["E30"]
        d.teile_suche.setText("")
        d.bezeichnung.setText(f"Gestell G{g + 1}")
        d.anzahl.setValue(2)
        d.naht_neu(dict(knoten="", verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=120, anzahl=4, dicke=3))
        d.vorkalkulation()
        n = d.bg["naehte"][0]
        assert n.get("heftpunkte"), n                                    # Heftpunkte aus der Vorkalkulation
        assert "Heften" in d._naht_ergebnis(n)["rechenweg"]
        assert any((ag.get("vk") or {}).get("art") == "positionieren" for ag in d.bg["arbeitsgaenge"]), \
            d.bg["arbeitsgaenge"]
        d._ok()
        return d.result()

    assert s.position_neu(typ=SCHWEISS, dialog=anlegen) == SCHWEISS
assert s.optimieren()
QApplication.processEvents()
ok("G4/G5 Editor: nur eigene Teile, alle zeigen, Suche; Vorkalkulation mit Heftpunkten und Positionieren")

m = s.pos_modell
c = next(c for c in range(m.columnCount()) if m.name(c) == "satz")
i_bg = [i for i, p in enumerate(s.positionen) if baugruppe.ist_baugruppe(p)]
assert len(i_bg) == 2
assert m.data(m.index(i_bg[0], c)) == "⚙ Gestell G1 · 2 Stk." and m.data(m.index(i_bg[0], c), Qt.FontRole).bold()
teil = baugruppe.teile(s.positionen, baugruppe.lesen(s.positionen[i_bg[0]]["baugruppe"])["id"])[0]
assert m.data(m.index(teil, c)) == "Gestell G1"
farbe = m.data(m.index(teil, next(c_ for c_ in range(m.columnCount()) if m.name(c_) == "artikel")),
               Qt.BackgroundRole).color().name()
assert farbe != m.data(m.index(2, next(c_ for c_ in range(m.columnCount()) if m.name(c_) == "artikel")),
                       Qt.BackgroundRole).color().name()
st = next(c_ for c_ in range(m.columnCount()) if m.name(c_) == "status")
for r in range(m.rowCount()):
    assert len(m.data(m.index(r, st))) <= 34
    assert m.data(m.index(r, st), Qt.ToolTipRole).startswith(m.data(m.index(r, st)).rstrip(" …"))
ok("G1 Positionsliste: Baugruppe grün mit ⚙ Name · Stk., Einzelteile mit Namen, Status einzeilig")

kk = s.kompakt
reihen = [z["zeile"] for z in kk.zeilen]
folge = satzgruppen.anzeige_folge(s.positionen)
assert reihen == [i for i in folge if i in reihen], (reihen, folge)
r_bg = reihen.index(i_bg[0])
ks = next(c_ for c_, sp in enumerate(kk.spalten) if sp[1] == "satz")
kp = next(c_ for c_, sp in enumerate(kk.spalten) if sp[1] == "profil")
ka = next(c_ for c_, sp in enumerate(kk.spalten) if sp[1] == "artikel")
assert kk.data(kk.index(r_bg, ks)) == "⚙ Gestell G1" and kk.data(kk.index(r_bg, kp)) == "Schweißbaugruppe"
assert kk.data(kk.index(r_bg, ka)) == "Gestell G1"
assert kk.data(kk.index(r_bg + 1, ks)) == "Gestell G1"                  # Einzelteil direkt darunter
assert kk.headerData(r_bg, Qt.Vertical).startswith("▾") and kk.headerData(r_bg + 1, Qt.Vertical).startswith("└")
alle = s.kalk
assert [z["zeile"] for z in alle.zeilen] == reihen
ok("G2 Kalkulation in der Reihenfolge der Positionsliste, Baugruppe mit Bezeichnung und Profil, Klammer am Kopf")

s._kalk_kopf_klick(s.kompakt_ansicht, kk, r_bg)                        # Klick in der Kalkulation klappt zu
assert s.pos_ansicht.isRowHidden(teil) and s.kompakt_ansicht.isRowHidden(r_bg + 1)
assert kk.headerData(r_bg, Qt.Vertical).startswith("▸")
s._kopf_klick(i_bg[0])
assert not s.kompakt_ansicht.isRowHidden(r_bg + 1)
knopf = s.gruppen_knoepfe[0]
assert not knopf.isHidden() and "zuklappen" in knopf.text(), knopf.text()
knopf.click()
assert all("aufklappen" in b.text() for b in s.gruppen_knoepfe)
assert s.pos_ansicht.isRowHidden(teil) and s.pos_ansicht.isRowHidden(1) and not s.pos_ansicht.isRowHidden(0)
f.angebot_schliessen(a)
s = f.angebot_oeffnen(a)                                                  # wird je Angebot gemerkt
QApplication.processEvents()
assert s.pos_ansicht.isRowHidden(teil) and s.pos_ansicht.isRowHidden(1)
s.gruppen_knoepfe[0].click()
assert not s.pos_ansicht.isRowHidden(teil) and str(a) not in (db.einstellung("ansicht_gruppen_zu") or {})
ok("G2 Zuklappen aus der Kalkulation, „Alle Gruppen zu-/aufklappen“, Zustand je Angebot gemerkt")
print("Alle Prüfungen bestanden.")
