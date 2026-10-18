"""Stammdaten und Einstellungen aus einer Kalkulationsmappe (v02, .xlsm/.xlsx) lesen.

Gelesen werden nur Eingabezellen: die Stammdatenblätter ab Zeile 5, die Zuschläge der Kalkulation,
Angebotskopf und Auftragskopf (Maschine, Stangenlänge, Auftragsnummer). Funktioniert auch mit
abgelegten Auftragsmappen, weil sie dieselben Blätter haben.
"""
import datetime
from pathlib import Path

from openpyxl import load_workbook

from .auftrag import KOPF, KOPF_ZELLE, POSITIONEN
from .stammdaten import TABELLEN, EINSTELLUNGEN, zahl_aus_text, zahl_als_text


def _wert(f, v):
    """Zellwert in den gespeicherten Wert umwandeln (Zahlen auch als Text mit Komma)."""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if f.art in ("zahl", "ganz"):
        if isinstance(v, bool):
            raise ValueError
        w = float(v) if isinstance(v, (int, float)) else zahl_aus_text(v)
        return int(w) if f.art == "ganz" and w == int(w) else w
    if f.art == "datum":
        if isinstance(v, datetime.datetime):
            return v.date().isoformat()
        if isinstance(v, datetime.date):
            return v.isoformat()
        return datetime.datetime.strptime(str(v).strip(), "%d.%m.%Y").date().isoformat()
    if isinstance(v, float):
        return f"{v:g}"
    return str(v).strip()


def lies_mappe(pfad):
    """Ergebnis: (daten {Tabelle: [Zeile]}, einstellungen {Name: Wert}, hinweise [Text]).
    Zeilen mit doppeltem Schlüssel werden übersprungen und als Hinweis gemeldet; unlesbare Werte
    bleiben leer und werden gemeldet."""
    pfad = Path(pfad)
    wb = load_workbook(pfad, read_only=True, data_only=True, keep_vba=False)
    fehlend = [t.blatt for t in TABELLEN if t.blatt and t.blatt not in wb.sheetnames]
    if fehlend:
        wb.close()
        raise ValueError(f"'{pfad.name}' ist keine Kalkulationsmappe: Blatt {', '.join(fehlend)} fehlt.")
    daten, hinweise = {}, []
    for t in TABELLEN:
        if not t.blatt:          # Tabelle gibt es nur im Programm (Zusatzarbeiten): bleibt unverändert
            continue
        ws = wb[t.blatt]
        zeilen, schluessel = [], set()
        felder = [f for f in t.felder if f.spalte]     # Felder nur im Programm bleiben leer
        breite = max(f.spalte for f in felder)
        for nr, werte in enumerate(ws.iter_rows(min_row=t.zeilen[0], max_row=t.zeilen[1], max_col=breite,
                                                values_only=True), start=t.zeilen[0]):
            werte = list(werte) + [None] * (breite - len(werte))
            if all(werte[f.spalte - 1] in (None, "") for f in felder):
                continue
            z = {}
            for f in felder:
                roh = werte[f.spalte - 1]
                try:
                    z[f.name] = _wert(f, roh)
                except (ValueError, TypeError):
                    z[f.name] = None
                    hinweise.append(f"{t.blatt} Zeile {nr}: {f.titel} '{roh}' nicht lesbar, bleibt leer.")
            schl = tuple(z.get(s) for s in t.schluessel)
            if all(s is not None for s in schl):
                if schl in schluessel:
                    text = " + ".join(str(s) if not isinstance(s, float) else zahl_als_text(s) for s in schl)
                    hinweise.append(f"{t.blatt} Zeile {nr}: '{text}' doppelt, nicht übernommen.")
                    continue
                schluessel.add(schl)
            zeilen.append(z)
        daten[t.name] = zeilen

    einstellungen = {}
    for e in EINSTELLUNGEN:
        if e.zelle is None or e.zelle[0] not in wb.sheetnames:
            continue
        v = wb[e.zelle[0]][e.zelle[1]].value
        if v is None or (isinstance(v, str) and v.startswith("=")):
            continue
        try:
            if e.art in ("zahl", "anteil"):
                v = float(v)
            elif e.art == "ganz":
                v = int(float(v))
            else:
                v = str(v).strip()
        except (TypeError, ValueError):
            hinweise.append(f"{e.zelle[0]} {e.zelle[1]}: {e.titel} '{v}' nicht lesbar, Einstellung bleibt.")
            continue
        einstellungen[e.name] = v
    if "Listen" in wb.sheetnames:
        formen = [r[0] for r in wb["Listen"].iter_rows(min_row=5, max_row=20, max_col=1, values_only=True)
                  if r[0] not in (None, "")]
        if formen:
            einstellungen["profilformen"] = "\n".join(str(f).strip() for f in formen)
    wb.close()
    return daten, einstellungen, hinweise


def lies_auftrag(pfad):
    """Auftragskopf und Positionen aus einer Mappe (Vorlage oder abgelegte Auftragsmappe).
    Ergebnis: (kopf, positionen, hinweise). Positionen in der Reihenfolge der Zeilen, leere Zeilen
    werden ausgelassen."""
    wb = load_workbook(Path(pfad), read_only=True, data_only=True, keep_vba=False)
    if "Auftrag" not in wb.sheetnames:
        wb.close()
        raise ValueError(f"'{Path(pfad).name}' ist keine Kalkulationsmappe: Blatt Auftrag fehlt.")
    ws, hinweise = wb["Auftrag"], []
    kopf = {}
    for f in KOPF:
        if f.name in KOPF_ZELLE:
            try:
                kopf[f.name] = _wert(f, ws[KOPF_ZELLE[f.name]].value)
            except (ValueError, TypeError):
                kopf[f.name] = None
                hinweise.append(f"Auftrag {KOPF_ZELLE[f.name]}: {f.titel} nicht lesbar.")
    felder = [f for f in POSITIONEN.felder if f.spalte]
    breite = max(f.spalte for f in felder)
    positionen = []
    for nr, werte in enumerate(ws.iter_rows(min_row=POSITIONEN.zeilen[0], max_row=POSITIONEN.zeilen[1],
                                            max_col=breite, values_only=True), start=POSITIONEN.zeilen[0]):
        werte = list(werte) + [None] * (breite - len(werte))
        if all(werte[f.spalte - 1] in (None, "") for f in felder):
            continue
        p = {}
        for f in felder:
            roh = werte[f.spalte - 1]
            try:
                p[f.name] = _wert(f, roh)
            except (ValueError, TypeError):
                p[f.name] = None
                hinweise.append(f"Auftrag Zeile {nr}: {f.titel} '{roh}' nicht lesbar, bleibt leer.")
        p["zeile"] = nr
        positionen.append(p)
    wb.close()
    return kopf, positionen, hinweise


def lies_staffeln(pfad):
    """Mengenstufen aus dem Blatt 'Staffeln' (Zeilen 5–104): [{schluessel, menge, bemerkung}].
    Mappen ohne dieses Blatt (vor Version 2) liefern eine leere Liste."""
    wb = load_workbook(Path(pfad), read_only=True, data_only=True, keep_vba=False)
    stufen = []
    if "Staffeln" in wb.sheetnames:
        for schl, menge, bem in wb["Staffeln"].iter_rows(min_row=5, max_row=104, max_col=3, values_only=True):
            if schl in (None, "") and menge in (None, ""):
                continue
            if isinstance(schl, float) and schl == int(schl):
                schl = int(schl)
            try:
                menge = int(float(menge)) if menge not in (None, "") else None
            except (TypeError, ValueError):
                menge = None
            stufen.append(dict(schluessel=None if schl in (None, "") else str(schl).strip(), menge=menge,
                               bemerkung=None if bem in (None, "") else str(bem)))
    wb.close()
    return stufen
