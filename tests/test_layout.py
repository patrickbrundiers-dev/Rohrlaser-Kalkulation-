"""Prüft das Layout der Mappe auf Fehler, die nur in Excel auffallen.

1. Schaltflächen: keine liegt in einer zugeklappten (ausgeblendeten) Spalte. Excel zeigt eine
   Schaltfläche, deren Anker in ausgeblendeten Spalten liegt, mit Breite null an.
2. Kopfbereich (Zeilen 1–11) von Auftrag und Kalkulation: keine beschriebene Zelle in einer
   ausgeblendeten Spalte, sonst sind Übersicht oder Summen unsichtbar.
3. Menüband und Schaltflächen rufen nur Makros auf, die es im VBA-Quelltext gibt.

Aufruf: python tests/test_layout.py
"""
import re
import zipfile
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

HIER = Path(__file__).parent
MAPPE = HIER.parent / "mappe" / "Rohrlaser_Kalkulation_v02.xlsm"


def ausgeblendet(ws):
    """1-basierte Nummern der ausgeblendeten Spalten."""
    spalten = set()
    for buchst, dim in ws.column_dimensions.items():
        if dim.hidden:
            von = column_index_from_string(buchst)
            spalten.update(range(dim.min or von, (dim.max or von) + 1))
    return spalten


def main():
    wb = load_workbook(MAPPE)
    z = zipfile.ZipFile(MAPPE)

    # 1. Schaltflächen im Blatt Auftrag
    zeichnung = z.read("xl/drawings/schaltflaechen1.xml").decode()
    verborgen = ausgeblendet(wb["Auftrag"])
    anker = re.findall(r"<xdr:(oneCellAnchor|twoCellAnchor)>(.*?)</xdr:\1>", zeichnung)
    assert anker, "keine Schaltflächen gefunden"
    makros = []
    for art, inhalt in anker:
        spalten = [int(c) + 1 for c in re.findall(r"<xdr:col>(\d+)</xdr:col>", inhalt)]
        name = re.search(r'macro="\[0\]!(\w+)"', inhalt).group(1)
        makros.append(name)
        assert art == "oneCellAnchor", f"{name}: feste Größe (oneCellAnchor) erwartet"
        assert not set(spalten) & verborgen, f"Schaltfläche {name} liegt in ausgeblendeter Spalte {spalten}"
    print(f"OK     {len(anker)} Schaltflächen in sichtbaren Spalten")

    # 2. Kopfbereich ohne Inhalt in ausgeblendeten Spalten
    for blatt in ("Auftrag", "Kalkulation"):
        ws = wb[blatt]
        verborgen = ausgeblendet(ws)
        assert verborgen, f"{blatt}: keine zugeklappten Spalten gefunden"
        for zeile in ws.iter_rows(min_row=1, max_row=11):
            for c in zeile:
                if c.value not in (None, "") and c.column in verborgen:
                    # Ausnahme: Kalkulation D4:F8 (Auftragskosten) steht zusätzlich als Text in Spalte W
                    if blatt == "Kalkulation" and c.column in (4, 5, 6) and 3 <= c.row <= 8:
                        continue
                    raise AssertionError(f"{blatt}!{c.coordinate} liegt in einer zugeklappten Spalte: {c.value!r}")
    print("OK     Kopfbereich von Auftrag und Kalkulation sichtbar")

    # 3. Makros vorhanden
    quelltext = "\n".join(p.read_text(encoding="utf-8") for p in (HIER.parent / "vba").glob("*.bas"))
    oeffentlich = set(re.findall(r"^Public Sub (\w+)", quelltext, re.M))
    menue = re.findall(r'onAction="(\w+)"', z.read("customUI/customUI.xml").decode())
    fehlt = [m for m in makros + menue if m not in oeffentlich]
    assert not fehlt, f"Makros fehlen im VBA-Quelltext: {fehlt}"
    assert "RbStangenbild" in menue and "StangenbildZeigen" in makros
    print(f"OK     {len(menue)} Menüband-Einträge und {len(makros)} Schaltflächen rufen vorhandene Makros")


if __name__ == "__main__":
    main()
