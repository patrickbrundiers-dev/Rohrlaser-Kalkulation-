"""Artikelnummer aus der STEP-Datei (Thread „Artikelnummer aus STEP besser bestimmen“, Patrick 28.10.2026, alle a):

A1 Bereinigung: Dateiendung, CAD-Zusatz („Rohr:1“, „Teil1<1>“), Kopie-Zusätze („Kopie von“, „ - Kopie“, „ (1)“).
A2 CAD-Standardnamen (Teil1, Part1, Body1, PRT0001, COMPOUND) gelten wie kein Name: der Dateiname wird Artikel (gelb).
A3 Teilenummer der STEP (PRODUCT-ID) vor der Benennung, die Benennung wird Bezeichnung (F1).
A4 Revision am Ende („_Rev B“, „_v2“, „Index C“) abgetrennt, steht in der Bezeichnung (F2).
A5 Nummer im Namen („Strebe links 4711-020“) automatisch, gelb (F3); Abmessungen, ISO/DIN, 1.4301 nie.
A6 Prüfdialog: Herkunft im Tooltip, gelb wenn unsicher, Artikelnummer per Doppelklick änderbar (F4); bleibt beim
   erneuten Anwenden (Kundenwechsel).
Mit echten STEP-Dateien (OpenCascade, erzeugt im Temp-Ordner, Namen erfunden).

Aufruf: python tests/test_artikel_step.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
MESSEN = HIER.parent / "programm" / "step_messung" / "step_messen.py"

from erzeuge_struktur_teile import Dokument, lage  # noqa: E402
from erzeuge_testteile import kastenrohr  # noqa: E402
from rohrlaser import importprofil as ip, step  # noqa: E402
from rohrlaser.stammdaten import BENENNUNGEN  # noqa: E402


def ok(text):
    print("OK:", text)


def a1_bis_a5_regeln():
    for roh, rein in (("Rohr 40x40x2:1", "Rohr 40x40x2"), ("Teil1<1>", "Teil1"), ("12345-01.SLDPRT", "12345-01"),
                      ("Kopie von 4711", "4711"), ("4711 (1)", "4711"), ("4711 - Kopie", "4711"),
                      ("4711 - Kopie (2)", "4711"), ("4711_Kopie", "4711"), ("Rahmen (links)", "Rahmen (links)"),
                      ("Strebe Länge ÄÖÜß", "Strebe Länge ÄÖÜß")):
        assert ip.bereinigt(roh) == rein, (roh, ip.bereinigt(roh))
    ok("A1 Endung, CAD-Zusatz und Kopie-Zusätze entfernt, Umlaute und Klammertext bleiben")
    for n in ("Teil1", "Bauteil 3", "Part12", "Body1", "PRT0001", "COMPOUND", "Körper2", "Solid"):
        assert ip.standardname(n), n
    for n in ("Rohr", "Teilrohr", "Halter 4711", "Strebe"):
        assert not ip.standardname(n), n
    ok("A2 CAD-Standardnamen erkannt (Rohr, Teilrohr, Strebe sind echte Namen)")
    for roh, erg in (("4711-020_Rev B", ("4711-020", "Rev B")), ("4711_v2", ("4711", "v2")),
                     ("4711 Index C", ("4711", "Index C")), ("Halter V2A", ("Halter V2A", "")),
                     ("Rev B", ("Rev B", ""))):
        assert ip.revision(roh) == erg, (roh, ip.revision(roh))
    ok("A4 Revision am Ende abgetrennt (V2A bleibt)")
    for roh, nr in (("Strebe links 4711-020", "4711-020"), ("Halter 4711 QR40x3", "4711"),
                    ("Rohr 40x40x2 L1000", ""), ("Schraube ISO 4017 M8x20", ""), ("Rohr 40x2 1.4301", ""),
                    ("Lasche 4711 und 4712", ""), ("4711", "")):
        assert ip.nummer_im_namen(roh) == nr, (roh, ip.nummer_im_namen(roh))
    ok("A5 Nummer im Namen nur eindeutig, nie Abmessung, Norm oder Werkstoffnummer")


def dateien(tmp):
    """Erfundene STEP-Dateien: (Dateiname, [Bauteilnamen]); Teilenummer per PRODUCT-ID nachträglich gesetzt."""
    out = {}
    for name, teile in (("Kopie von 9001 Gestell (1)", ["Teil1", "Teil2"]),
                        ("Rahmen_Rev C", ["Holm:1", "Strebe links 4711-020", "Querrohr_v2"]),
                        ("Konsole", ["KONSOLE-BENENNUNG"]),
                        ("Lasche", ["Lasche Ü"])):
        d = Dokument()
        labs = [d.teil(n, kastenrohr(40, 40, 2, 300 + 50 * i, 3)) for i, n in enumerate(teile)]
        if len(labs) > 1:
            d.baugruppe(name, [(lab, lage(x=100 * i)) for i, lab in enumerate(labs)])
        pfad = tmp / f"{name}.step"
        d.schreiben(pfad)
        out[name] = pfad
    p = out["Konsole"]          # CAD schreibt Teilenummer und Benennung getrennt: PRODUCT('7788-01', 'Konsole links')
    p.write_text(p.read_text(encoding="utf-8").replace("PRODUCT('KONSOLE-BENENNUNG','KONSOLE-BENENNUNG'",
                                                       "PRODUCT('7788-01','Konsole links'"), encoding="utf-8")
    p = out["Lasche"]           # Umlaut kodiert wie in vielen CAD-Dateien (\X2\00DC\X0\)
    p.write_text(p.read_text(encoding="utf-8").replace("PRODUCT('Lasche Ü','Lasche Ü'",
                                                       "PRODUCT('L-5544','Lasche \\X2\\00DC\\X0\\'"), encoding="utf-8")
    return out


def a_import(tmp):
    pfade = dateien(tmp)
    aus = tmp / "m.txt"
    r = subprocess.run([sys.executable, str(MESSEN), "--ausgabe", str(aus), *map(str, pfade.values())],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr
    mw = step.lies_messwerte(aus)
    nach_name = {Path(p).name: str(p) for p in pfade.values()}
    for m in mw:
        m["_pfad"] = nach_name.get(m.get("datei"))
    ip.anwenden(mw, None, {"step_benennung": BENENNUNGEN[0]})
    art = {(m["datei"], m.get("bauteil")): (m["artikel"], m.get("_bezeichnung"), m.get("_artikel_unsicher"))
           for m in mw}
    herkunft = {m["artikel"]: m.get("_artikel_herkunft") for m in mw}
    g = "Kopie von 9001 Gestell (1).step"
    assert art[(g, "Teil1")] == ("9001 Gestell-K1", None, True), art[(g, "Teil1")]
    assert art[(g, "Teil2")] == ("9001 Gestell-K2", None, True), art[(g, "Teil2")]
    assert "CAD-Standardname" in herkunft["9001 Gestell-K1"]
    ok("A1/A2 Teil1/Teil2 aus „Kopie von 9001 Gestell (1).step“ -> 9001 Gestell-K1/-K2 (gelb)")
    r_ = "Rahmen_Rev C.step"
    assert art[(r_, "Holm:1")] == ("Holm", None, False), art[(r_, "Holm:1")]
    assert art[(r_, "Strebe links 4711-020")] == ("4711-020", "Strebe links 4711-020", True)
    assert art[(r_, "Querrohr_v2")] == ("Querrohr", "Querrohr_v2", False), art[(r_, "Querrohr_v2")]
    assert "Revision „v2“ abgetrennt" in herkunft["Querrohr"]
    ok("A4/A5 Holm:1 -> Holm, Querrohr_v2 -> Querrohr (Revision in der Bezeichnung), 4711-020 aus dem Namen (gelb)")
    assert art[("Konsole.step", "Konsole links")] == ("7788-01", "Konsole links", False), art
    assert herkunft["7788-01"].startswith("Teilenummer der STEP-Datei")
    assert art[("Lasche.step", "Lasche Ü")] == ("L-5544", "Lasche Ü", False), art
    ok("A3 Teilenummer der STEP vor der Benennung (auch mit kodiertem Umlaut), Benennung = Bezeichnung")
    erg = step.uebernehmen(mw, [], db_k[0], db_k[1], None, "S235-10219", 1)
    pos = {p["artikel"]: p for p in erg["positionen"]}
    assert pos["7788-01"].get("bezeichnung") == "Konsole links" and "Querrohr" in pos, sorted(pos)
    ok("Übernehmen: Positionen mit den neuen Nummern und Bezeichnungen")
    return mw


def a6_pruefdialog(mw, k):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from rohrlaser import stil
    from rohrlaser.step_dialog import StepPruefDialog
    app = QApplication.instance() or QApplication([])
    mw = [{n: v for n, v in x.items() if not n.startswith("_") or n in ("_pfad", "_struktur", "_netz")} for x in mw]
    ip.anwenden(mw, None, {"step_benennung": BENENNUNGEN[0]})
    d = StepPruefDialog(None, mw, k, "S235-10219", 1, None, {})
    z = next(z for z in d.zeilen if z.it.text(0) == "4711-020")
    assert "Nummer im Bauteilnamen" in z.it.toolTip(0) and "Doppelklick" in z.it.toolTip(0)
    assert z.it.background(0).color() == stil.farbe(stil.GELB_FLAECHE)
    k_ = next(z for z in d.zeilen if z.it.text(0) == "7788-01")
    assert "Teilenummer der STEP-Datei" in k_.it.toolTip(0) and k_.it.background(0).style() == Qt.NoBrush
    z.it.setText(0, "4711-020-A")           # wie nach Doppelklick und Eingabe
    app.processEvents()
    m = mw[z.liste[0]]
    assert m["artikel"] == "4711-020-A" and m["_artikel_hand"] and z.it.background(0).style() == Qt.NoBrush
    ip.anwenden(mw, None, {"step_benennung": BENENNUNGEN[0]})        # Kundenwechsel: Handeingabe bleibt
    assert m["artikel"] == "4711-020-A"
    d.werte_schreiben()
    assert m["artikel"] == "4711-020-A"
    d.reject()
    app.processEvents()
    ok("A6 Prüfdialog: Herkunft im Tooltip, gelb wenn unsicher, Nummer änderbar und bleibt")


if __name__ == "__main__":
    a1_bis_a5_regeln()
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        from rohrlaser.datenbank import Datenbank
        db = Datenbank(tmp / "rohrlaser.db")
        db_k = (db.kontext(), db.zeilen("gewinde"))
        mw = a_import(tmp)
        a6_pruefdialog(mw, db_k[0])
