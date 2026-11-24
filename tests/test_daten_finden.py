"""Neue Programmkopie findet die bisherigen Daten (Patrick 26.10.2026: „option einbauen, dass die alten Daten bei
Installation übernommen werden“): jeder Start merkt sich seinen Datenordner, der erste Start einer neuen Kopie bietet
den zuletzt benutzten an (ohne den eigenen), dazu die installierte Version; Lizenz und Angebots-Ablage gehen mit,
ohne Vorhandenes zu überschreiben.

Aufruf: python tests/test_daten_finden.py
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import orte  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
umg = {"LOCALAPPDATA": str(tmp / "lokal")}
try:
    def kopie(name, mit_daten=True):
        prog = tmp / name
        prog.mkdir()
        (prog / orte.PORTABEL).write_text("", encoding="utf-8")
        o = orte.ermitteln(prog, frozen=True, umgebung=umg)
        if mit_daten:
            o.daten.mkdir(parents=True)
            o.datei.write_bytes(b"db " + name.encode())
        return o

    alt1 = kopie("Rohrlaser_alt1")
    orte.merken(alt1, umg)
    time.sleep(0.01)
    alt2 = kopie("Rohrlaser_alt2")
    os.utime(alt1.datei, (time.time() - 3600, time.time() - 3600))      # alt1 älter
    orte.merken(alt2, umg)
    orte.merken(alt1, umg)                  # nochmals: kein doppelter Eintrag
    assert len(orte._zuletzt_lesen(umg)) == 2
    neu = kopie("Rohrlaser_neu", mit_daten=False)
    gefunden = orte.fruehere_daten(neu, umg)
    assert [g["daten"] for g in gefunden] == [alt2.daten, alt1.daten], gefunden
    assert gefunden[0]["art"] == "portabel" and gefunden[0]["datei"] == alt2.datei
    orte.merken(neu, umg)
    assert all(g["daten"] != neu.daten for g in orte.fruehere_daten(neu, umg))
    ok("Zuletzt benutzte Datenordner gemerkt, neueste zuerst, eigener und doppelte ausgelassen")

    # installierte Version wird auch ohne Eintrag gefunden; verschwundene Ordner nicht
    inst = Path(umg["LOCALAPPDATA"]) / orte.ORDNER_INSTALLIERT / orte.DATEN
    inst.mkdir(parents=True)
    (inst / orte.DATENDATEI).write_bytes(b"db installiert")
    shutil.rmtree(alt1.programm)
    gefunden = orte.fruehere_daten(neu, umg)
    assert inst in [g["daten"] for g in gefunden] and alt1.daten not in [g["daten"] for g in gefunden]
    ok("Daten der installierten Version gefunden, gelöschte Kopie übergangen")

    # Lizenz und Ablage mitnehmen, nichts überschreiben
    (alt2.daten / orte.LIZENZ).mkdir()
    (alt2.daten / orte.LIZENZ / "lizenz.json").write_text("{}", encoding="utf-8")
    alt2.ablage.mkdir()
    (alt2.ablage / "A-2026-00001.pdf").write_bytes(b"%PDF")
    neu.daten.mkdir(parents=True)
    quelle = next(g for g in orte.fruehere_daten(neu, umg) if g["daten"] == alt2.daten)
    teile = orte.beiwerk_uebernehmen(quelle, neu)
    assert teile[0] == "Lizenz" and len(teile) == 2, teile
    assert (neu.daten / orte.LIZENZ / "lizenz.json").is_file() and (neu.ablage / "A-2026-00001.pdf").is_file()
    assert (alt2.ablage / "A-2026-00001.pdf").is_file()                 # Quelle unverändert
    (neu.daten / orte.LIZENZ / "lizenz.json").write_text("eigen", encoding="utf-8")
    assert orte.beiwerk_uebernehmen(quelle, neu) == []                  # schon vorhanden: nichts angefasst
    assert (neu.daten / orte.LIZENZ / "lizenz.json").read_text(encoding="utf-8") == "eigen"
    ok("Lizenz und Angebots-Ablage übernommen, Vorhandenes nie überschrieben")

    # kaputte Liste stört nicht
    orte.zuletzt_datei(umg).write_text("kaputt", encoding="utf-8")
    assert [g["daten"] for g in orte.fruehere_daten(neu, umg)] == [inst]
    orte.merken(neu, umg)
    assert len(orte._zuletzt_lesen(umg)) == 1
    ok("Kaputte Liste: ignoriert und neu angelegt")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("OK: Neue Programmkopie findet die bisherigen Daten")
