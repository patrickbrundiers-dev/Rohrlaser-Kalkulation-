"""Zukaufteile im STEP-Import einordnen und auflisten (CAD-Entwicklungsplan Paket 1, Patrick 12.11.2026).

Z1 Namen: bekannte Norm (sicher) mit Kategorie und Größe, Begriff deutsch/englisch (wahrscheinlich), Halbzeug-Norm im
   Namen eines Rohrs macht kein Normteil, keine erfundene Norm.
Z2 Form: Scheibe, Stift, Hülse, Niet werden nur Vorschlag (bleiben Fertigungsteil); große Scheibe und Rohr nicht.
Z3 Importprofil: Norm/Begriff im Namen macht ein Normteil (Einstellung an), eigene Liste gilt weiter, Schalter aus.
Z4 Liste und Prüfdialog: gleiche Teile zusammengefasst, Filter, per Klick ins Angebot, Vorschlag annehmen und
   zurücknehmen; angenommene Teile kommen als Zukaufteil-Position mit Bezeichnung ins Angebot.

Aufruf: python tests/test_zukaufteile_step.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import step_messen  # noqa: E402
from formen_baukasten import ohne, plus, schreibe, zyl  # noqa: E402
from rohrlaser import importprofil, step, zukaufteile as zk  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TMP = Path(tempfile.mkdtemp())
AN = {"step_normteile": "ISO; DIN; Schraube; Mutter; Scheibe; Stift; Niet; Normteil", "step_zukauf_begriffe": "ja"}


def ok(text):
    print("OK    ", text)


# ---------------------------------------------------------------- Z1 Namen
def name(n, **m):
    return zk.einordnen(dict(bauteil=n, **m))


e = name("ISO 4032 M12:1")
assert (e["kategorie"], e["norm"], e["groesse"], e["vertrauen"]) == (zk.MUTTER, "ISO 4032", "M12", zk.SICHER), e
e = name("DIN EN ISO 4762 - M8 x 25")
assert (e["kategorie"], e["norm"], e["groesse"]) == (zk.SCHRAUBE, "DIN EN ISO 4762", "M8x25"), e
e = name("Scheibe DIN 125 A13")
assert (e["kategorie"], e["norm"], e["vertrauen"]) == (zk.SCHEIBE, "DIN 125", zk.SICHER), e
for n, kat in (("washer_M8", zk.SCHEIBE), ("Blindniet 4x10", zk.NIET), ("Hex Bolt M10 x 30", zk.SCHRAUBE),
               ("pin 8x40", zk.STIFT), ("Distanzhülse 12x8x30", zk.HUELSE), ("Kugellager 6204", zk.LAGER),
               ("Sicherungsring 20x1,2", zk.RING), ("stud M8", zk.GEWINDE)):
    e = name(n)
    assert e and (e["kategorie"], e["vertrauen"], e["norm"]) == (kat, zk.WAHRSCHEINLICH, ""), (n, e)
assert name("Hex Bolt M10 x 30")["groesse"] == "M10x30" and name("Blindniet 4x10")["groesse"] == "4x10"
for n in ("Lagerbock", "Mutterblech", "Anschraubplatte", "Nutenstein", "Part7", "Holm RE60x40x3 L800"):
    assert name(n) is None, (n, name(n))
ok("Z1 Norm im Namen (sicher) und Begriff deutsch/englisch (wahrscheinlich) mit Kategorie und Größe; Lagerbock, "
   "Mutterblech, Anschraubplatte sind keine Zukaufteile")
assert zk.halbzeug_norm("Rohr 40x40x3 EN 10219") and zk.halbzeug_norm("Rohr DIN 2395 30x30x2")
assert not zk.halbzeug_norm("DIN 933 M8") and not zk.halbzeug_norm("Rohr 40x40x3")
assert name("Rohr 40x40x3 EN 10219", profilform="Quadratrohr", laenge="800") is None
e = name("Teil nach ISO 99999")
assert e["kategorie"] == zk.SONST and e["norm"] == "ISO 99999" and "nicht bekannt" in e["grund"], e
e = name("Schraube", laenge="900", abm_a="60", profilform="Quadratrohr")
assert e["vertrauen"] == zk.VORSCHLAG, e
e = name("BUE-04-00 Hülse_Standard", laenge="40", abm_a="30", profilform="Rundrohr")
assert e["kategorie"] == zk.HUELSE and e["vertrauen"] == zk.VORSCHLAG and "Rohr/Profil" in e["grund"], e
e = name("Schraube", laenge="900", abm_a="60", profilform="Flachstahl")
assert e["vertrauen"] == zk.VORSCHLAG and "größer" in e["grund"], e
ok("Z1 Halbzeug-Norm (EN 10219, DIN 2395) macht kein Normteil; unbekannte Norm bleibt ohne Kategorie; Begriff auf "
   "einem großen Rohr ist nur ein Vorschlag")

# ---------------------------------------------------------------- Z2 Form
T = {"T1": ohne(zyl(12, 2.5), zyl(6.5, 2.5)),                         # Scheibe 13x24x2,5
     "T2": ohne(zyl(100, 8), zyl(50, 8)),                            # großer Ring: kein Vorschlag
     "T3": zyl(4, 40),                                               # Stift 8x40
     "T4": zyl(10, 200),                                             # Rundstahl 20x200: kein Vorschlag
     "T5": ohne(zyl(6, 30), zyl(4, 30)),                             # Hülse 12/8x30
     "T6": plus(zyl(4, 1.5), zyl(2, 10, 1.5)),                       # Niet Kopf 8, Schaft 4
     "T7": ohne(plus(zyl(4, 1.5), zyl(2.4, 10, 1.5)), zyl(1.3, 11.5)),   # Blindniet
     "T8": ohne(zyl(15, 500), zyl(12, 500))}                         # Rundrohr 30x3x500
schreibe(T, TMP)
aus = TMP / "m.txt"
step_messen.main(["--ausgabe", str(aus)] + [str(TMP / f"{n}.step") for n in T])
MW = {Path(m["datei"]).stem: m for m in step.lies_messwerte(aus)}
for m in MW.values():
    m["bauteil"] = Path(m["datei"]).stem          # Namen ohne Begriff: nur die Form zählt
soll = dict(T1=zk.SCHEIBE, T2=None, T3=zk.STIFT, T4=None, T5=zk.HUELSE, T6=zk.KOPFTEIL, T7=zk.NIET, T8=None)
for n, kat in soll.items():
    e = zk.einordnen(MW[n])
    assert (e or {}).get("kategorie") == kat, (n, e, MW[n].get("profilform"))
    assert e is None or (e["vertrauen"] == zk.VORSCHLAG and e["norm"] == "" and e["groesse_quelle"] == "gemessen"), e
assert "Blindniet" in zk.einordnen(MW["T7"])["grund"] and zk.einordnen(MW["T1"])["groesse"].startswith("Ø24 × 2,5")
ok("Z2 Form: Scheibe, Stift, Hülse, Niet und Blindniet sind Vorschläge ohne Norm, Größe gemessen; großer Ring, "
   "langer Rundstahl und Rohr nicht")

# ---------------------------------------------------------------- Z3 Importprofil
mw = [dict(m) for m in MW.values()]
assert importprofil.anwenden(mw, None, AN) == 0 and not any(m.get("_normteil") for m in mw)
assert sum(1 for m in mw if (m.get("_zukaufteil") or {}).get("vertrauen") == zk.VORSCHLAG) == 5
assert all(step.gewaehlt(m) == step.gewaehlt(dict(MW[Path(m["datei"]).stem])) for m in mw), "Vorschlag ändert nichts"
namen = dict(T1="Washer M12", T3="ISO 8734 8x40", T8="Rohr 30x3 EN 10305", T6="Niet")
for m in mw:
    m["bauteil"] = namen.get(Path(m["datei"]).stem, m["bauteil"])
assert importprofil.anwenden(mw, None, AN) == 3
je = {Path(m["datei"]).stem: m for m in mw}
assert je["T1"]["_normteil"] == zk.SCHEIBE and je["T3"]["_normteil"] == "ISO" and je["T6"]["_normteil"] == "Niet"
assert je["T3"]["_zukaufteil"]["kategorie"] == zk.STIFT and je["T3"]["_zukaufteil"]["groesse"] == "8x40"
assert not je["T8"].get("_normteil") and not je["T8"].get("_zukaufteil"), "Rohr mit EN 10305 bleibt Rohr"
aus_ = dict(AN, step_zukauf_begriffe="nein")
mw2 = [dict(MW["T1"], bauteil="Washer M12"), dict(MW["T3"], bauteil="ISO 8734 8x40")]
assert importprofil.anwenden(mw2, None, aus_) == 1 and not mw2[0].get("_normteil") and mw2[1]["_normteil"] == "ISO"
assert mw2[0]["_zukaufteil"]["vertrauen"] == zk.VORSCHLAG
ok("Z3 Importprofil: Begriff und Norm im Namen machen ein Normteil, die eigene Liste gilt weiter, Rohr mit "
   "Halbzeug-Norm bleibt Rohr; Schalter aus = nur Vorschlag")

# ---------------------------------------------------------------- Z4 Liste, Prüfdialog, Angebot
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog, ZukaufteileDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(TMP / "z.db")
k = db.kontext()
mw = [dict(MW[n]) for n in ("T1", "T1", "T3", "T5", "T6", "T8")]
for i, m in enumerate(mw):
    m["artikel"] = f"{m['artikel']}-{i}"
mw[2]["bauteil"] = "ISO 8734 8x40"
mw[4]["bauteil"] = "Blind Rivet 4x10"
importprofil.anwenden(mw, None, AN)
d = StepPruefDialog(None, mw, k, "S235-10219", 3, zukauf_liste=db.zukauf_artikel_liste())
zeilen = d.zukaufteil_zeilen()
status = {z["kategorie"]: z["status"] for z in zeilen}
assert status == {zk.SCHEIBE: "Vorschlag", zk.STIFT: "nicht übernommen", zk.HUELSE: "Vorschlag",
                  zk.NIET: "nicht übernommen"}, status
assert "2 + " in d.zk_knopf.text() and "Vorschl" in d.zk_knopf.text(), d.zk_knopf.text()
assert any("Könnte ein Zukaufteil sein (Scheibe" in zk.hinweis(d.messwerte[z.liste[0]]) for z in d.zeilen)
zd = d.zukaufteile_zeigen(dialog=False)
assert isinstance(zd, ZukaufteileDialog) and zd.liste.rowCount() == len(zeilen)
zd.status.setCurrentText("Vorschlag")
assert [z["kategorie"] for z in zd.sichtbare()] == [zk.SCHEIBE, zk.HUELSE]
zd.status.setCurrentText("Alle")
zd.kategorie.setCurrentText(zk.NIET)
assert [z["kategorie"] for z in zd.sichtbare()] == [zk.NIET]
zd.kategorie.setCurrentText("Alle")
r_stift = next(r for r, z in enumerate(zd.zeilen) if z["kategorie"] == zk.STIFT)
zd.liste.item(r_stift, 0).setCheckState(Qt.Checked)        # ein Klick auf das Häkchen
assert zd.zeilen[r_stift]["status"] == "ins Angebot"
r_scheibe = next(r for r, z in enumerate(zd.zeilen) if z["kategorie"] == zk.SCHEIBE)
zd.setzen(r_scheibe, True)                                         # Vorschlag annehmen
z = next(z for z in zd.zeilen if z["kategorie"] == zk.SCHEIBE)
assert z["status"] == "ins Angebot" and z["anzahl"] == 2 and z["bezeichnung"].startswith("Scheibe Ø24 × 2,5"), z
r_huelse = next(r for r, z in enumerate(zd.zeilen) if z["kategorie"] == zk.HUELSE)
zd.setzen(r_huelse, True)
zd.ablehnen(next(r for r, z in enumerate(zd.zeilen) if z["kategorie"] == zk.HUELSE))     # doch Fertigungsteil
assert next(z for z in zd.zeilen if z["kategorie"] == zk.HUELSE)["status"] == "Vorschlag"
assert not any(m.get("_zukauf_hand") for m in mw if Path(m["datei"]).stem == "T5")
ok("Z4 Liste: gleiche Teile zusammengefasst, Filter nach Status und Kategorie, ein Klick = ins Angebot, Vorschlag "
   "annehmen und zurücknehmen")

werte = d.werte_schreiben()
erg = step.uebernehmen(werte, [], k, db.zeilen("gewinde"), None, "S235-10219", 3,
                       zukauf_liste=db.zukauf_artikel_liste())
zkp = {p["bezeichnung"]: p for p in erg["positionen"] if p.get("art") == ZUKAUFTEIL and "_zukauf" in p
       and (erg["zukauf_neu"].get(p["_zukauf"].get("neu")) or ({},))[0].get("artikeltyp") == step.NORMTEIL_TYP}
assert set(zkp) == {"ISO 8734 8x40", "Scheibe Ø24 × 2,5, Bohrung Ø13"}, (set(zkp), erg["bericht"])
assert zkp["Scheibe Ø24 × 2,5, Bohrung Ø13"]["stueck"] == 6 and zkp["ISO 8734 8x40"]["stueck"] == 3, zkp
assert not any("Rivet" in (p.get("bezeichnung") or "") for p in erg["positionen"]), "nicht angehakt bleibt draußen"
ok("Z4 Angebot: angehakte Zukaufteile kommen als Zukaufteil-Positionen (Scheibe 2 × 3 Stück, Stift 3 Stück), "
   "der nicht angehakte Niet bleibt draußen")
db.con.close()
print("Zukaufteile im STEP-Import: alle Tests bestanden.")
