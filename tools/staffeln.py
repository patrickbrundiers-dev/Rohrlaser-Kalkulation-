# -*- coding: utf-8 -*-
"""Staffelpreise: Mengenstufen aus dem Blatt 'Staffeln' in Rechenläufe übersetzen.

Referenz für die gleiche Logik im VBA-Modul 'Staffel'. Jede Mengenstufe ist ein
eigener Auftrag, der nur die Positionen dieser Staffel enthält:

* Schlüssel ist eine Satzbezeichnung (Auftrag Spalte AQ) oder eine
  Positionsnummer (Auftrag Spalte A).
* Für einen Satz ist die Menge die Anzahl Sätze; die Stückzahl je Position ist
  Menge × 'Stück je Satz' (Spalte AR, leer = 1).
* Für eine Position ist die Menge die Stückzahl.

Damit fallen Rüstzeit, Stangenwechsel und Verschnitt je Stufe neu an.
"""

O0, O1 = 13, 512
T0, T1 = 5, 104

SATZ = 43          # Auftrag Spalte AQ
JE_SATZ = 44       # Auftrag Spalte AR


def _txt(v):
    """Schlüssel immer als Text vergleichen; ganze Zahlen ohne Nachkommastellen."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v) == int(v) else repr(float(v))
    return str(v).strip()


def _zahl(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def je_satz(wa, zeile):
    n = _zahl(wa.cell(zeile, JE_SATZ).value)
    return n if n >= 1 else 1.0


def saetze(wa, schluessel):
    """Anzahl Sätze eines Satzes = Stückzahl / Stück je Satz (größter Wert)."""
    n = 0.0
    for r in range(O0, O1 + 1):
        if _txt(wa.cell(r, SATZ).value) == schluessel:
            n = max(n, _zahl(wa.cell(r, 7).value) / je_satz(wa, r))
    return max(1, int(round(n)))


def stufen(wb):
    """Mengenstufen aus dem Blatt 'Staffeln': [(schluessel, menge)]."""
    wsa = wb["Staffeln"]
    out = []
    for r in range(T0, T1 + 1):
        schl = _txt(wsa.cell(r, 1).value)
        menge = _zahl(wsa.cell(r, 2).value)
        if schl and menge >= 1:
            out.append((schl, menge))
    return out


def szenarien(wb):
    """[(schluessel, menge, ist_satz, {zeile: stückzahl})] – ein Eintrag je Stufe.

    Nicht beteiligte Positionen fehlen in der Zuordnung, ihre Stückzahl wird im
    Rechenlauf geleert.
    """
    wa = wb["Auftrag"]
    out = []
    for schl, menge in stufen(wb):
        ist_satz = any(_txt(wa.cell(r, SATZ).value) == schl for r in range(O0, O1 + 1))
        mengen = {}
        for r in range(O0, O1 + 1):
            if wa.cell(r, 4).value in (None, ""):
                continue
            treffer = (_txt(wa.cell(r, SATZ).value) == schl) if ist_satz else (_txt(wa.cell(r, 1).value) == schl)
            if treffer:
                mengen[r] = menge * (je_satz(wa, r) if ist_satz else 1)
        out.append((schl, menge, ist_satz, mengen))
    return out


def setze(wb, mengen):
    """Stückzahlen für einen Rechenlauf setzen: nur die Positionen in mengen bleiben besetzt."""
    wa = wb["Auftrag"]
    for r in range(O0, O1 + 1):
        wa.cell(r, 7).value = mengen.get(r)
