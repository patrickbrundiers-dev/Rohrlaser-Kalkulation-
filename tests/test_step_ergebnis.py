"""Prüft das versionierte Ergebnisformat (JSON) der STEP-Messung und den Umgang des Programms mit dem Prüfstatus:
- JSON: Schema und Version, alle Felder je Körper, unbekannte Werte null statt erfundener Maße, Importstatus defekter
  Dateien, Prüfstatus und Erkennungssicherheit je Merkmal, Wand-Einzelmessungen, Schnittwinkel.
- Programm: Teile mit unsicherer Erkennung werden ohne Bestätigung nicht übernommen und stehen im Prüfdialog
  abgehakt mit Hinweis; nach Anhaken werden sie übernommen.

Aufruf: python tests/test_step_ergebnis.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
sys.path.insert(0, str(HIER.parent / "programm"))
import step_ergebnis  # noqa: E402
import step_messen  # noqa: E402

DATEIEN = [HIER / "step_konturen" / "K01_RE60x40x3_Konturen.step", HIER / "step_konturen" / "K03_RR42-4x2_Konturen.step",
           HIER / "step_import" / "I04_Flaechenmodell_offen.step", HIER / "step_import" / "I05_defekt.step",
           HIER / "step_profile" / "P01_U50x30x3_L800.step", HIER / "step_profile" / "P10_RE60x40_Wand2und3_L600.step",
           HIER / "step_referenz" / "REF18_Z60x40x4_L500.step", HIER / "step_traeger" / "TR01_IPE200_L1000.step"]
KOERPER_FELDER = {"nr", "artikel_vorschlag", "koerperart", "geometrie_gueltig", "volumen_mm3", "oberflaeche_mm2",
                  "anzahl_flaechen", "anzahl_kanten", "huellquader_datei", "bauteiltyp", "profiltyp",
                  "profil_id_vorschlag", "blech", "normprofil", "traeger",
                  "aussenmasse", "innenmasse", "querschnittsflaeche_mm2", "wandstaerke", "laenge", "laengsachse",
                  "schnittwinkel", "schneidweg", "konturen", "enden", "senkungen", "fliessloecher", "pruefstatus", "warnungen",
                  "erkennungssicherheit", "ersatzwerte", "alternative"}
fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"FEHLER {name}: {e}")
        return fn
    return deko


tmp = Path(tempfile.mkdtemp())
step_messen.main(["--ausgabe", str(tmp / "m.txt"), "--json", str(tmp / "m.json")] + [str(d) for d in DATEIEN])
ERG = json.loads((tmp / "m.json").read_text(encoding="utf-8"))
NACH = {d["datei"]: d for d in ERG["dateien"]}


@fall("Schema, Version und Felder")
def _():
    assert ERG["schema"] == step_ergebnis.SCHEMA and ERG["schema_version"] == step_ergebnis.SCHEMA_VERSION, ERG["schema"]
    assert "keine Fertigungsfreigabe" in ERG["hinweis"]
    assert [d["datei"] for d in ERG["dateien"]] == [d.name for d in DATEIEN]
    for d in ERG["dateien"]:
        for k in d["koerper"]:
            assert set(k) == KOERPER_FELDER, set(k) ^ KOERPER_FELDER
            assert k["pruefstatus"] in ("plausibel", "prüfen", "nicht messbar"), k["pruefstatus"]


@fall("K01: Maße, Achse, Wand-Einzelmessungen, Schnittwinkel, Konturen")
def _():
    d = NACH["K01_RE60x40x3_Konturen.step"]
    assert d["importstatus"] == "gelesen" and d["einheit_datei"] == "mm" and d["einheit_ausgabe"] == "mm"
    (k,) = d["koerper"]
    assert k["profiltyp"] == "Rechteckrohr" and k["aussenmasse"] == {"a": 60.0, "b": 40.0}, k["aussenmasse"]
    assert k["innenmasse"] == {"a": 54.0, "b": 34.0}, k["innenmasse"]
    assert k["laengsachse"]["richtung"] == [0.0, 0.0, 1.0] and k["laengsachse"]["ende_a"] == [0.0, 0.0, 0.0], k
    w = k["wandstaerke"]
    assert w["wert"] == 3.0 and w["minimum"] == 3.0 and w["maximum"] == 3.0 and len(w["einzelmessungen"]) >= 12, w
    assert k["schnittwinkel"]["Ende B"] == {"form": "Gehrung", "gesamt": 30.0, "um_x": 30.0, "um_y": 0.0,
                                                 "richtung": 0.0}
    assert [c["art"] for c in k["konturen"]] == ["Bohrung", "Bohrung", "Langloch", "Rechteckausschnitt",
                                                 "Sackbohrung"], k["konturen"]
    assert k["pruefstatus"] == "prüfen" and any("Sackbohrung" in x for x in k["warnungen"])   # Sackbohrung: prüfen
    assert all(v == "sicher" for v in k["erkennungssicherheit"].values()), k["erkennungssicherheit"]


@fall("K03: plausibel ohne Warnungen; Rundrohr mit Durchmessern")
def _():
    (k,) = NACH["K03_RR42-4x2_Konturen.step"]["koerper"]
    assert k["pruefstatus"] == "plausibel" and k["warnungen"] == [], (k["pruefstatus"], k["warnungen"])
    assert k["aussenmasse"] == {"durchmesser": 42.4} and k["innenmasse"] == {"durchmesser": 38.4}, k


@fall("Unbekannte Werte sind null: offenes Flächenmodell, defekte Datei, Konturen eines Z-Profils")
def _():
    (k,) = NACH["I04_Flaechenmodell_offen.step"]["koerper"]
    assert k["pruefstatus"] == "nicht messbar"
    for f in ("profiltyp", "aussenmasse", "innenmasse", "wandstaerke", "laenge", "laengsachse", "schneidweg",
              "konturen", "volumen_mm3", "querschnittsflaeche_mm2"):
        assert k[f] is None, f"{f} = {k[f]!r}"
    d = NACH["I05_defekt.step"]
    assert d["importstatus"] == "nicht lesbar" and "nicht lesbar" in d["fehler"] and d["koerper"] == []
    (u,) = NACH["REF18_Z60x40x4_L500.step"]["koerper"]
    assert u["profiltyp"] == "offenes Sonderprofil" and u["innenmasse"] is None and u["konturen"] is None and \
        u["schneidweg"] is None, u
    assert u["erkennungssicherheit"]["konturen"] == "nicht ausgewertet"
    # U-Profil: Konturen ausgewertet (seit 20.10.2026), Innenmaße bleiben null
    (u,) = NACH["P01_U50x30x3_L800.step"]["koerper"]
    assert u["profiltyp"] == "U-Profil" and u["innenmasse"] is None and u["schneidweg"]["gesamt"] > 0, u


@fall("Träger: Normprofil und Block traeger (Steg, Flansch, symmetrisch, Ausrundung)")
def _():
    (k,) = NACH["TR01_IPE200_L1000.step"]["koerper"]
    assert k["profiltyp"] == "I-/H-Träger" and k["normprofil"] == "IPE 200" and k["profil_id_vorschlag"] == "IPE 200", k
    assert k["traeger"] == dict(stegdicke=5.6, flanschdicke=8.5, symmetrisch=True, ausrundung=12.0), k["traeger"]
    (z,) = NACH["P01_U50x30x3_L800.step"]["koerper"]
    assert z["traeger"] is None and z["normprofil"] is None, z


@fall("P10: ungleiche Wand -> prüfen, Wandstärke unsicher, Einzelwerte 2 und 3 mm")
def _():
    (k,) = NACH["P10_RE60x40_Wand2und3_L600.step"]["koerper"]
    assert k["pruefstatus"] == "prüfen" and k["erkennungssicherheit"]["wandstaerke"] == "unsicher"
    assert k["wandstaerke"]["minimum"] == 2.0 and k["wandstaerke"]["maximum"] == 3.0, k["wandstaerke"]


@fall("Programm: unsichere Erkennung erst nach Bestätigung übernehmen")
def _():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from rohrlaser import step
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.step_dialog import StepPruefDialog
    app = QApplication.instance() or QApplication([])  # noqa: F841
    mw = [m for m in step.lies_messwerte(tmp / "m.txt") if m["datei"].startswith(("K03", "P10"))]
    assert [m["pruefstatus"] for m in mw] == ["plausibel", "prüfen"], [m["pruefstatus"] for m in mw]
    assert step.unsicher(mw[1]) == ["wandstaerke"] and not step.unsicher(mw[0])
    db = Datenbank(tmp / "rohrlaser.db")
    k = db.kontext()
    erg = step.uebernehmen([dict(m) for m in mw], [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                           neue_profile=True)
    assert [p["artikel"] for p in erg["positionen"]] == ["K03_RR42-4x2_Konturen"], erg["positionen"]
    assert any("Erkennung unsicher (wandstaerke)" in z for z in erg["bericht"]), erg["bericht"]
    dlg = StepPruefDialog(None, [dict(m) for m in mw], k, "S235-10219", 1)
    zustand = {z.it.text(0): z.it.checkState(0) for z in dlg.zeilen}
    assert zustand == {"K03_RR42-4x2_Konturen": Qt.Checked, "P10_RE60x40_Wand2und3_L600": Qt.Unchecked}, zustand
    p10 = next(z for z in dlg.zeilen if z.it.text(0).startswith("P10"))
    assert "UNSICHER: wandstaerke" in p10.it.text(9), p10.it.text(9)
    p10.it.setCheckState(0, Qt.Checked)        # Bestätigung durch Anhaken
    dlg.werte_schreiben()
    erg = step.uebernehmen(dlg.messwerte, [], k, db.zeilen("gewinde"), None, "S235-10219", 1, neue_profile=True)
    assert sorted(p["artikel"] for p in erg["positionen"]) == ["K03_RR42-4x2_Konturen", "P10_RE60x40_Wand2und3_L600"]


sys.exit(1 if fehler else 0)
