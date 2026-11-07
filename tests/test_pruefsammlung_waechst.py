"""Prüfsammlung wächst von selbst (Vorschlag N5, Patrick 07.11.2026): eine im Prüfdialog von Hand geänderte Art merkt
sich das Programm in Daten/Prüfsammlung (Kennwerte der Messung + Vorschaubild, keine STEP-Datei, keine Datei- oder
Artikelnamen); das Support-Paket nimmt sie mit.

Aufruf: python tests/test_pruefsammlung_waechst.py
"""
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import step_messen  # noqa: E402
from formen_baukasten import ohne, quader, schreibe, zyl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import art_korrekturen, step, support  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


langloch = ohne(quader(150, 35, 8.5), quader(20, 9, 8.5, 20, 13), zyl(4.5, 8.5, 0, 20, 17.5), zyl(4.5, 8.5, 0, 40, 17.5),
                quader(20, 9, 8.5, 110, 13), zyl(4.5, 8.5, 0, 110, 17.5), zyl(4.5, 8.5, 0, 130, 17.5))
schreibe({"Kunde_4711_Lasche": langloch, "Kunde_4711_Platte": quader(200, 120, 5)}, TMP)
aus = TMP / "m.txt"
step_messen.main(["--ausgabe", str(aus), "--netze", str(TMP / "netze"), str(TMP / "Kunde_4711_Lasche.step"),
                  str(TMP / "Kunde_4711_Platte.step")])
mw = step.lade_netze(step.lies_messwerte(aus), TMP / "netze")
assert [step.art_gruppe(m) for m in mw] == [step.ART_BLECH, step.ART_BLECH], [(m["bauteiltyp"], m["profilform"]) for m in mw]

app = QApplication.instance() or QApplication([])
db = Datenbank(TMP / "Daten" / "a.db")
k = db.kontext()
d = StepPruefDialog(None, mw, k, "S235-10219", 1, zukauf_liste=[])
d.art_gruppe_setzen(0, step.ART_PROFIL)
d.accept()
assert len(d.art_korrekturen) == 1, d.art_korrekturen
kor = d.art_korrekturen[0]
assert kor["gemessen"].startswith(step.ART_BLECH) and "Flachstahl" in kor["gewaehlt"], kor
ok(f"Prüfdialog: von Hand geänderte Art erkannt ({kor['gemessen']} → {kor['gewaehlt']}), unverändertes Teil nicht")

ordner = art_korrekturen.ordner(db.pfad)
assert art_korrekturen.merken(ordner, d.art_korrekturen) == 1
e = art_korrekturen.eintraege(ordner)
assert len(e) == 1 and e[0]["kennwerte"]["bauteiltyp"] == "Blech" and e[0]["kennwerte"].get("huelle"), e
text = json.dumps(e, ensure_ascii=False)
assert "Kunde_4711" not in text and "datei" not in e[0]["kennwerte"] and "artikel" not in e[0]["kennwerte"], text
assert (ordner / e[0]["bild"]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
assert not list(ordner.glob("*.step")) and not list(ordner.glob("*.stp"))
ok("Daten/Prüfsammlung: Kennwerte und Vorschaubild, keine STEP-Datei, keine Datei-/Artikelnamen")

alt = art_korrekturen.HOECHSTENS
art_korrekturen.HOECHSTENS = 2
for _ in range(3):
    art_korrekturen.merken(ordner, d.art_korrekturen)
assert len(art_korrekturen.eintraege(ordner)) == 2 and len(list(ordner.glob("*.png"))) == 2
art_korrekturen.HOECHSTENS = alt
ok("Höchstens HOECHSTENS Einträge: die ältesten fallen samt Bild weg")

erg = support.erstellen(db, system=[])
namen = zipfile.ZipFile(erg["pfad"]).namelist()
assert "pruefsammlung/korrekturen.jsonl" in namen and sum(n.endswith(".png") for n in namen) == 2, namen
assert "Prüfsammlung" in support.text(erg) and ".png" not in support.text(erg)
ok("Support-Paket: pruefsammlung/ mit Einträgen und Bildern")
db.con.close()
print("Prüfsammlung wächst: alle Tests bestanden.")
