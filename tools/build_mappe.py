import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.comments import Comment

import os, sys
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "mappe", "Rohrlaser_Kalkulation_v01.xlsx")
F = "Arial"
N_MASTER = 300          # Datenzeilen je Stammdatenblatt (Zeile 5..304)
M0, M1 = 5, 5 + N_MASTER - 1
O0, O1 = 13, 13 + 500 - 1   # Auftragspositionen Zeile 13..512

f_title = Font(name=F, size=14, bold=True)
f_bold = Font(name=F, bold=True)
f_head = Font(name=F, bold=True, color="FFFFFF")
f_in = Font(name=F, color="0000FF")
f_calc = Font(name=F, color="000000")
f_link = Font(name=F, color="008000")
f_note = Font(name=F, italic=True, color="595959", size=9)
fill_head = PatternFill("solid", fgColor="1F4E78")
fill_in = PatternFill("solid", fgColor="FFF2CC")
fill_calc = PatternFill("solid", fgColor="EDEDED")
thin = Side(style="thin", color="BFBFBF")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
wrap = Alignment(wrap_text=True, vertical="top")

wb = Workbook()


def header(ws, row, cols):
    """cols: list of (title, width, kind) kind in in/calc"""
    for i, (t, w, kind) in enumerate(cols, start=1):
        c = ws.cell(row=row, column=i, value=t)
        c.font = f_head
        c.fill = fill_head
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        c.border = border
        ws.column_dimensions[c.column_letter].width = w
    ws.row_dimensions[row].height = 45


def style_rows(ws, r0, r1, cols, fmts=None):
    fmts = fmts or {}
    for r in range(r0, r1 + 1):
        for i, (_, _, kind) in enumerate(cols, start=1):
            c = ws.cell(row=r, column=i)
            c.border = border
            if kind == "in":
                c.fill = fill_in
                c.font = f_in
            elif kind == "link":
                c.fill = fill_calc
                c.font = f_link
            else:
                c.fill = fill_calc
                c.font = f_calc
            if i in fmts:
                c.number_format = fmts[i]


def title(ws, text, sub):
    ws["A1"] = text
    ws["A1"].font = f_title
    ws["A2"] = sub
    ws["A2"].font = f_note


def add_dv(ws, dv, rng):
    ws.add_data_validation(dv)
    dv.add(rng)


def num_dv(op_min, op_max, whole=False, title_="Ungültige Eingabe", msg=""):
    dv = DataValidation(type="whole" if whole else "decimal", operator="between",
                        formula1=str(op_min), formula2=str(op_max), allow_blank=True)
    dv.error = msg or f"Bitte einen Wert zwischen {op_min} und {op_max} eingeben."
    dv.errorTitle = title_
    dv.showErrorMessage = True
    return dv


def list_dv(name, msg):
    dv = DataValidation(type="list", formula1=f"={name}", allow_blank=True)
    dv.error = msg
    dv.errorTitle = "Ungültige Auswahl"
    dv.showErrorMessage = True
    return dv


# ---------------------------------------------------------------- Anleitung
ws = wb.active
ws.title = "Anleitung"
ws.column_dimensions["A"].width = 26
ws.column_dimensions["B"].width = 100
title(ws, "Kalkulation Rohrlaserteile – Version 0.1 (Schritt 1: Grundstruktur)",
      f"Erstellt {datetime.date(2026, 10, 15).strftime('%d.%m.%Y')}. Optimierung (VBA), STEP-Import und Kostenrechnung folgen in Schritt 2–4.")
rows = [
    ("Farblegende", None),
    ("Gelb / blaue Schrift", "Eingabefeld. Nur hier Werte eintragen."),
    ("Grau / schwarze Schrift", "Berechnet (Formel). Nicht überschreiben."),
    ("Grau / grüne Schrift", "Aus anderem Blatt nachgeschlagen (Formel). Nicht überschreiben."),
    ("", ""),
    ("Blätter", None),
    ("Auftrag", "Auftragskopf (Auftrag, Kunde, Maschine, Standard-Stangenlänge) und bis zu 500 Positionen. Spalte W zeigt je Zeile den Prüfstatus."),
    ("Profile", "Profil-Stammdaten: Form, Abmessungen, Wandstärke, Querschnitt; optional profilspezifischer Endbeschnitt/Greiferrest."),
    ("Werkstoffe", "Werkstoff/Materialqualität mit Dichte."),
    ("Preise", "Materialpreis je Profil + Werkstoff, wahlweise €/kg oder €/Stange."),
    ("Maschinen", "Maschinenparameter: Endbeschnitt, Greiferrest, Schnittverlust, max. Stangenlänge, Stundensatz."),
    ("Schneiddaten", "Vorschub und Einstechzeit je Maschine, Werkstoff und Wandstärke (für Laserzeit in Schritt 4)."),
    ("Listen", "Auswahllisten (Profilform, Preisbasis)."),
    ("", ""),
    ("Arbeitsablauf", None),
    ("1.", "Stammdaten pflegen (Profile, Werkstoffe, Preise, Maschinen, Schneiddaten). Die vorhandenen Zeilen sind BEISPIELWERTE und müssen durch eigene Daten ersetzt werden."),
    ("2.", "Auftragskopf ausfüllen, Maschine wählen, Standard-Stangenlänge prüfen (Vorgabe 6.000 mm)."),
    ("3.", "Positionen eintragen (Profil und Werkstoff per Auswahlliste). Schneidweg später automatisch per STEP-Import (Schritt 2)."),
    ("4.", "Status-Spalte prüfen: FEHLER muss behoben werden, WARNUNG/HINWEIS sollte geprüft werden."),
    ("", ""),
    ("Annahmen", None),
    ("A1", "Microsoft 365 / Excel 2019 oder neuer. Diese Version ist .xlsx ohne Makros; ab Schritt 3 wird sie zu .xlsm (Makros erforderlich)."),
    ("A2", "Ein Auftrag je Blatt 'Auftrag'. Alle Positionen laufen auf der im Kopf gewählten Maschine."),
    ("A3", "Stangenlänge: Standard aus dem Auftragskopf, je Position abweichend überschreibbar (Spalte J)."),
    ("A4", "Endbeschnitt und Greiferrest kommen von der Maschine; ist am Profil ein abweichender Wert eingetragen, gilt der Profilwert."),
    ("A5", "Nutzlänge je Stange = Stangenlänge − Endbeschnitt − Greiferrest. Ein Teil passt nur, wenn Teilelänge + Schnittverlust ≤ Nutzlänge (konservativ, genaue Regel folgt mit der Optimierung)."),
    ("A6", "Querschnitt berechnet ohne Eckradien (Quadrat-/Rechteckrohr ca. 1–4 % zu schwer). Für exakte Gewichte den Herstellerwert in 'Fläche manuell' eintragen; Sonderprofile benötigen immer 'Fläche manuell'."),
    ("A7", "Metergewicht [kg/m] = Querschnitt [mm²] × Dichte [kg/dm³] / 1000."),
    ("A8", "Keine Restlagerverwaltung: Reststücke werden nur als Verschnitt ausgewiesen (Entscheidung vom 15.10.2026)."),
    ("A9", "Kapazität: 300 Zeilen je Stammdatenblatt, 500 Auftragspositionen. Erweiterbar, indem Formelzeilen nach unten kopiert und die Namen in Formeln > Namens-Manager angepasst werden."),
    ("A10", "Einheiten: Längen in mm, Gewicht in kg, Preise in € netto."),
]
r = 4
for a, b in rows:
    ws.cell(row=r, column=1, value=a)
    if b is None:
        ws.cell(row=r, column=1).font = f_bold
    else:
        ws.cell(row=r, column=1).font = Font(name=F)
        c = ws.cell(row=r, column=2, value=b)
        c.font = Font(name=F)
        c.alignment = wrap
    r += 1
ws["A5"].fill = fill_in; ws["A5"].font = f_in
ws["A6"].fill = fill_calc
ws["A7"].fill = fill_calc; ws["A7"].font = f_link

# ---------------------------------------------------------------- Listen
wl = wb.create_sheet("Listen")
title(wl, "Auswahllisten", "Werte für Dropdowns. Ergänzungen hier eintragen.")
wl["A4"], wl["B4"] = "Profilform", "Preisbasis"
for c in (wl["A4"], wl["B4"]):
    c.font = f_head; c.fill = fill_head
for i, v in enumerate(["Rundrohr", "Quadratrohr", "Rechteckrohr", "Sonderprofil"], start=5):
    wl.cell(row=i, column=1, value=v).font = f_in
for i, v in enumerate(["€/kg", "€/Stange"], start=5):
    wl.cell(row=i, column=2, value=v).font = f_in
wl.column_dimensions["A"].width = 18
wl.column_dimensions["B"].width = 14
wb.defined_names["lst_Profilform"] = DefinedName("lst_Profilform", attr_text="Listen!$A$5:$A$20")
wb.defined_names["lst_Preisbasis"] = DefinedName("lst_Preisbasis", attr_text="Listen!$B$5:$B$6")

# ---------------------------------------------------------------- Werkstoffe
ww = wb.create_sheet("Werkstoffe", 2)
title(ww, "Werkstoffe / Materialqualität", "Werkstoff-ID ist der Schlüssel für Preise, Schneiddaten und Auftrag. Beispielwerte ersetzen.")
cols_w = [("Werkstoff-ID", 18, "in"), ("Werkstoff", 16, "in"), ("Werkstoff-Nr.", 14, "in"),
          ("Norm / Qualität", 30, "in"), ("Dichte [kg/dm³]", 12, "in"), ("Bemerkung", 30, "in")]
header(ww, 4, cols_w)
style_rows(ww, M0, M1, cols_w, {5: "0.00"})
for i, row in enumerate([
    ("S235-10219", "S235JRH", "1.0039", "EN 10219 kaltgefertigt, geschweißt", 7.85, "Beispiel"),
    ("S355-10219", "S355J2H", "1.0576", "EN 10219 kaltgefertigt, geschweißt", 7.85, "Beispiel"),
    ("1.4301", "X5CrNi18-10", "1.4301", "EN 10217-7 / ASTM A554", 7.90, "Beispiel"),
    ("AW6060-T66", "EN AW-6060 T66", "3.3206", "EN 755-2", 2.70, "Beispiel"),
], start=M0):
    for j, v in enumerate(row, start=1):
        ww.cell(row=i, column=j, value=v)
add_dv(ww, num_dv(0.5, 25, msg="Dichte in kg/dm³ (z. B. Stahl 7,85, Alu 2,70)."), f"E{M0}:E{M1}")
dup = DataValidation(type="custom", formula1=f"=COUNTIF($A${M0}:$A${M1},A{M0})=1", allow_blank=True)
dup.error = "Diese Werkstoff-ID existiert bereits."; dup.showErrorMessage = True
add_dv(ww, dup, f"A{M0}:A{M1}")
ww.freeze_panes = "B5"
wb.defined_names["lst_Werkstoff"] = DefinedName("lst_Werkstoff", attr_text=f"Werkstoffe!$A${M0}:$A${M1}")

# ---------------------------------------------------------------- Profile
wp = wb.create_sheet("Profile", 2)
title(wp, "Profile / Abmessungen",
      "Abmessung A = Ø (Rundrohr) bzw. Breite; Abmessung B = Höhe (nur Rechteckrohr). Endbeschnitt/Greiferrest nur eintragen, wenn vom Maschinenwert abweichend.")
cols_p = [("Profil-ID", 20, "in"), ("Profilform", 15, "in"), ("Abmessung A [mm]", 12, "in"),
          ("Abmessung B [mm]", 12, "in"), ("Wandstärke [mm]", 12, "in"), ("Fläche manuell [mm²] (optional)", 14, "in"),
          ("Endbeschnitt abweichend [mm]", 14, "in"), ("Greiferrest abweichend [mm]", 14, "in"),
          ("Bemerkung", 26, "in"), ("Fläche berechnet [mm²]", 13, "calc"), ("Fläche wirksam [mm²]", 13, "calc")]
header(wp, 4, cols_p)
style_rows(wp, M0, M1, cols_p, {3: "0.0", 4: "0.0", 5: "0.00", 6: "0.0", 7: "0", 8: "0", 10: "0.0", 11: "0.0"})
for i, row in enumerate([
    ("RR 42,4x2,0", "Rundrohr", 42.4, None, 2.0, None, None, None, "Beispiel"),
    ("RR 48,3x2,6", "Rundrohr", 48.3, None, 2.6, None, None, None, "Beispiel"),
    ("QR 40x40x3", "Quadratrohr", 40, None, 3.0, None, None, None, "Beispiel"),
    ("RE 60x40x3", "Rechteckrohr", 60, 40, 3.0, None, None, None, "Beispiel"),
    ("RE 120x60x4", "Rechteckrohr", 120, 60, 4.0, None, 30, 120, "Beispiel: profilspezifischer Endbeschnitt/Greiferrest"),
], start=M0):
    for j, v in enumerate(row, start=1):
        if v is not None:
            wp.cell(row=i, column=j, value=v)
for r in range(M0, M1 + 1):
    hb = f'IF(B{r}="Quadratrohr",C{r},D{r})'
    wp[f"J{r}"] = (f'=IF(OR(A{r}="",C{r}="",E{r}=""),"",IF(B{r}="Rundrohr",PI()/4*(C{r}^2-(C{r}-2*E{r})^2),'
                   f'IF(OR(B{r}="Quadratrohr",AND(B{r}="Rechteckrohr",D{r}<>"")),C{r}*{hb}-(C{r}-2*E{r})*({hb}-2*E{r}),"")))')
    wp[f"K{r}"] = f'=IF(A{r}="","",IF(F{r}<>"",F{r},J{r}))'
add_dv(wp, list_dv("lst_Profilform", "Bitte Profilform aus der Liste wählen."), f"B{M0}:B{M1}")
add_dv(wp, num_dv(1, 1000, msg="Abmessung in mm (1–1000)."), f"C{M0}:D{M1}")
wt = DataValidation(type="custom", formula1=f"=AND(E{M0}>0,E{M0}*2<C{M0})", allow_blank=True)
wt.error = "Wandstärke muss > 0 und kleiner als die halbe Abmessung A sein."; wt.showErrorMessage = True
add_dv(wp, wt, f"E{M0}:E{M1}")
add_dv(wp, num_dv(1, 100000, msg="Querschnittsfläche in mm²."), f"F{M0}:F{M1}")
add_dv(wp, num_dv(0, 2000, msg="Wert in mm (0–2000)."), f"G{M0}:H{M1}")
dup = DataValidation(type="custom", formula1=f"=COUNTIF($A${M0}:$A${M1},A{M0})=1", allow_blank=True)
dup.error = "Diese Profil-ID existiert bereits."; dup.showErrorMessage = True
add_dv(wp, dup, f"A{M0}:A{M1}")
wp["F4"].comment = Comment("Herstellerwert eintragen, wenn exaktes Gewicht nötig (Eckradien) oder bei Sonderprofil.", "Kalkulation")
wp.freeze_panes = "B5"
wb.defined_names["lst_Profil"] = DefinedName("lst_Profil", attr_text=f"Profile!$A${M0}:$A${M1}")

# ---------------------------------------------------------------- Preise
wpr = wb.create_sheet("Preise", 4)
title(wpr, "Materialpreise", "Je Kombination Profil + Werkstoff genau eine Zeile. Preisbasis €/kg oder €/Stange (bezogen auf die Liefer-Stangenlänge).")
cols_pr = [("Profil-ID", 20, "in"), ("Werkstoff-ID", 16, "in"), ("Preisbasis", 11, "in"), ("Preis [€]", 11, "in"),
           ("Liefer-Stangenlänge [mm]", 13, "in"), ("Gültig ab", 12, "in"), ("Lieferant", 20, "in"),
           ("Bemerkung", 22, "in"), ("Prüfung", 26, "calc")]
header(wpr, 4, cols_pr)
style_rows(wpr, M0, M1, cols_pr, {4: "#,##0.00", 5: "#,##0", 6: "DD.MM.YYYY"})
for i, row in enumerate([
    ("RR 42,4x2,0", "S235-10219", "€/kg", 1.45, 6000, datetime.date(2026, 10, 1), "Beispiel-Lieferant", "Beispiel"),
    ("RR 48,3x2,6", "S235-10219", "€/kg", 1.45, 6000, datetime.date(2026, 10, 1), "Beispiel-Lieferant", "Beispiel"),
    ("QR 40x40x3", "S235-10219", "€/kg", 1.50, 6000, datetime.date(2026, 10, 1), "Beispiel-Lieferant", "Beispiel"),
    ("RE 60x40x3", "S355-10219", "€/kg", 1.60, 6000, datetime.date(2026, 10, 1), "Beispiel-Lieferant", "Beispiel"),
    ("RR 42,4x2,0", "1.4301", "€/Stange", 62.00, 6000, datetime.date(2026, 10, 1), "Beispiel-Lieferant", "Beispiel"),
], start=M0):
    for j, v in enumerate(row, start=1):
        wpr.cell(row=i, column=j, value=v)
for r in range(M0, M1 + 1):
    wpr[f"I{r}"] = (f'=IF(A{r}&B{r}="","",IF(ISNA(MATCH(A{r},lst_Profil,0)),"FEHLER: Profil unbekannt",'
                    f'IF(ISNA(MATCH(B{r},lst_Werkstoff,0)),"FEHLER: Werkstoff unbekannt",'
                    f'IF(COUNTIFS($A${M0}:$A${M1},A{r},$B${M0}:$B${M1},B{r})>1,"FEHLER: doppelt",'
                    f'IF(OR(C{r}="",D{r}=""),"FEHLER: Preis unvollständig",'
                    f'IF(AND(C{r}="€/Stange",E{r}=""),"FEHLER: Stangenlänge fehlt","OK"))))))')
add_dv(wpr, list_dv("lst_Profil", "Bitte Profil-ID aus Blatt 'Profile' wählen."), f"A{M0}:A{M1}")
add_dv(wpr, list_dv("lst_Werkstoff", "Bitte Werkstoff-ID aus Blatt 'Werkstoffe' wählen."), f"B{M0}:B{M1}")
add_dv(wpr, list_dv("lst_Preisbasis", "Bitte €/kg oder €/Stange wählen."), f"C{M0}:C{M1}")
add_dv(wpr, num_dv(0.01, 100000, msg="Preis in € (> 0)."), f"D{M0}:D{M1}")
add_dv(wpr, num_dv(500, 20000, whole=True, msg="Stangenlänge in mm (500–20000)."), f"E{M0}:E{M1}")
dd = DataValidation(type="date", operator="greaterThan", formula1="36526", allow_blank=True)
dd.error = "Bitte gültiges Datum eingeben."; dd.showErrorMessage = True
add_dv(wpr, dd, f"F{M0}:F{M1}")
wpr.freeze_panes = "C5"

# ---------------------------------------------------------------- Maschinen
wm = wb.create_sheet("Maschinen", 5)
title(wm, "Maschinenparameter", "Endbeschnitt = Anschnitt am Stangenanfang; Greiferrest = nicht nutzbares Ende im Greifer; Schnittverlust = Materialverlust je Trennschnitt.")
cols_m = [("Maschinen-ID", 16, "in"), ("Bezeichnung", 26, "in"), ("Endbeschnitt [mm]", 12, "in"),
          ("Greiferrest [mm]", 12, "in"), ("Schnittverlust je Schnitt [mm]", 13, "in"),
          ("Max. Stangenlänge [mm]", 13, "in"), ("Stundensatz [€/h]", 12, "in"), ("Bemerkung", 30, "in")]
header(wm, 4, cols_m)
style_rows(wm, M0, M1, cols_m, {3: "0", 4: "0", 5: "0.0", 6: "#,##0", 7: "#,##0.00"})
for i, row in enumerate([
    ("RL-1", "Rohrlaser 1 (Beispiel)", 20, 80, 0.3, 6500, 120.00, "Beispielwerte"),
    ("RL-2", "Rohrlaser 2 (Beispiel)", 15, 120, 0.3, 8500, 140.00, "Beispielwerte"),
], start=M0):
    for j, v in enumerate(row, start=1):
        wm.cell(row=i, column=j, value=v)
add_dv(wm, num_dv(0, 2000, msg="Wert in mm (0–2000)."), f"C{M0}:D{M1}")
add_dv(wm, num_dv(0, 20, msg="Schnittverlust in mm (0–20)."), f"E{M0}:E{M1}")
add_dv(wm, num_dv(500, 20000, whole=True, msg="Stangenlänge in mm (500–20000)."), f"F{M0}:F{M1}")
add_dv(wm, num_dv(0, 10000, msg="Stundensatz in €/h."), f"G{M0}:G{M1}")
dup = DataValidation(type="custom", formula1=f"=COUNTIF($A${M0}:$A${M1},A{M0})=1", allow_blank=True)
dup.error = "Diese Maschinen-ID existiert bereits."; dup.showErrorMessage = True
add_dv(wm, dup, f"A{M0}:A{M1}")
wm.freeze_panes = "B5"
wb.defined_names["lst_Maschine"] = DefinedName("lst_Maschine", attr_text=f"Maschinen!$A${M0}:$A${M1}")

# ---------------------------------------------------------------- Schneiddaten
wsd = wb.create_sheet("Schneiddaten", 6)
title(wsd, "Schneiddaten (Laserzeit)", "Je Maschine + Werkstoff gestaffelt nach Wandstärke: es gilt die Zeile mit der kleinsten 'Wandstärke bis', die ≥ der Profilwandstärke ist.")
cols_sd = [("Maschinen-ID", 16, "in"), ("Werkstoff-ID", 16, "in"), ("Wandstärke bis [mm]", 12, "in"),
           ("Vorschub [mm/min]", 12, "in"), ("Einstechzeit [s]", 12, "in"), ("Bemerkung", 30, "in")]
header(wsd, 4, cols_sd)
style_rows(wsd, M0, M1, cols_sd, {3: "0.0", 4: "#,##0", 5: "0.0"})
sd_rows = []
for m in ("RL-1",):
    for w, data in (("S235-10219", [(2, 6000, 0.3), (3, 4500, 0.5), (5, 3000, 0.8)]),
                    ("S355-10219", [(2, 5800, 0.3), (3, 4300, 0.5), (5, 2800, 0.8)]),
                    ("1.4301", [(2, 5000, 0.4), (3, 3500, 0.6), (5, 2000, 1.0)]),
                    ("AW6060-T66", [(2, 7000, 0.3), (3, 5000, 0.5), (5, 3200, 0.8)])):
        for t, v, e in data:
            sd_rows.append((m, w, t, v, e, "Beispiel"))
for i, row in enumerate(sd_rows, start=M0):
    for j, v in enumerate(row, start=1):
        wsd.cell(row=i, column=j, value=v)
add_dv(wsd, list_dv("lst_Maschine", "Bitte Maschinen-ID aus Blatt 'Maschinen' wählen."), f"A{M0}:A{M1}")
add_dv(wsd, list_dv("lst_Werkstoff", "Bitte Werkstoff-ID aus Blatt 'Werkstoffe' wählen."), f"B{M0}:B{M1}")
add_dv(wsd, num_dv(0.1, 50, msg="Wandstärke in mm."), f"C{M0}:C{M1}")
add_dv(wsd, num_dv(1, 100000, msg="Vorschub in mm/min."), f"D{M0}:D{M1}")
add_dv(wsd, num_dv(0, 60, msg="Einstechzeit in s."), f"E{M0}:E{M1}")
wsd.freeze_panes = "C5"

# ---------------------------------------------------------------- Auftrag
wa = wb.create_sheet("Auftrag", 1)
title(wa, "Auftrag – Eingabe", "Kopf ausfüllen, dann Positionen ab Zeile 13. Status in Spalte W beachten. Beispielpositionen vor Gebrauch löschen (nur gelbe Zellen).")
kopf = [("Auftragsnummer", "A-2026-0001"), ("Kundennummer", "K-10045"), ("Kundenname", "Beispiel GmbH"),
        ("Datum", datetime.date(2026, 10, 15)), ("Maschine", "RL-1"), ("Standard-Stangenlänge [mm]", 6000)]
for i, (lab, val) in enumerate(kopf, start=4):
    wa.cell(row=i, column=1, value=lab).font = f_bold
    wa.merge_cells(start_row=i, start_column=1, end_row=i, end_column=2)
    c = wa.cell(row=i, column=3, value=val)
    c.font = f_in; c.fill = fill_in; c.border = border
    wa.merge_cells(start_row=i, start_column=3, end_row=i, end_column=4)
wa["C7"].number_format = "DD.MM.YYYY"
wa["C9"].number_format = "#,##0"

mlook = lambda col: f'=IF($C$8="","",IFERROR(INDEX(Maschinen!${col}${M0}:${col}${M1},MATCH($C$8,lst_Maschine,0)),"?"))'
mk = [("Endbeschnitt [mm]", mlook("C"), "0"), ("Greiferrest [mm]", mlook("D"), "0"),
      ("Schnittverlust [mm]", mlook("E"), "0.0"), ("Max. Stangenlänge [mm]", mlook("F"), "#,##0"),
      ("Stundensatz [€/h]", mlook("G"), "#,##0.00")]
for i, (lab, fml, fmt) in enumerate(mk, start=4):
    wa.cell(row=i, column=6, value=lab).font = f_bold
    wa.merge_cells(start_row=i, start_column=6, end_row=i, end_column=7)
    c = wa.cell(row=i, column=8, value=fml)
    c.font = f_link; c.fill = fill_calc; c.border = border; c.number_format = fmt
wa["F3"] = "Maschinenwerte (aus Blatt 'Maschinen')"; wa["F3"].font = f_note
OR_ = f"{O0}:{{c}}{O1}"
rng = lambda c: f"${c}${O0}:${c}${O1}"
summ = [("Positionen", f'=COUNTIF({rng("W")},"?*")', "0"),
        ("davon FEHLER", f'=COUNTIF({rng("W")},"FEHLER*")', "0"),
        ("davon WARNUNG/HINWEIS", f'=COUNTIF({rng("W")},"WARNUNG*")+COUNTIF({rng("W")},"HINWEIS*")', "0"),
        ("Teile gesamt [Stk]", f'=SUM({rng("G")})', "#,##0"),
        ("Teilelänge gesamt [m]", f'=SUM({rng("P")})/1000', "#,##0.00"),
        ("Teilegewicht gesamt [kg]", f'=SUM({rng("X")})', "#,##0.00")]
for i, (lab, fml, fmt) in enumerate(summ, start=4):
    wa.cell(row=i, column=10, value=lab).font = f_bold
    wa.merge_cells(start_row=i, start_column=10, end_row=i, end_column=12)
    c = wa.cell(row=i, column=13, value=fml)
    c.font = f_calc; c.fill = fill_calc; c.border = border; c.number_format = fmt
wa["J3"] = "Übersicht"; wa["J3"].font = f_note

cols_a = [("Pos.", 6, "in"), ("Artikelnummer", 16, "in"), ("Bezeichnung", 22, "in"), ("Profil-ID", 18, "in"),
          ("Werkstoff-ID", 15, "in"), ("Teilelänge [mm]", 11, "in"), ("Stückzahl", 9, "in"),
          ("Schneidweg je Teil [mm] (STEP)", 13, "in"), ("Einstiche je Teil (STEP)", 10, "in"),
          ("Stangenlänge abweichend [mm]", 12, "in"),
          ("Profilform", 13, "link"), ("Querschnitt [mm²]", 10, "link"), ("Wandstärke [mm]", 10, "link"),
          ("Metergewicht [kg/m]", 10, "calc"), ("Gewicht je Teil [kg]", 10, "calc"), ("Länge gesamt [mm]", 11, "calc"),
          ("Stangenlänge wirksam [mm]", 11, "calc"), ("Endbeschnitt wirksam [mm]", 10, "calc"),
          ("Greiferrest wirksam [mm]", 10, "calc"), ("Nutzlänge Stange [mm]", 11, "calc"),
          ("Preis hinterlegt", 9, "calc"), ("Vorschub [mm/min]", 10, "link"), ("Status", 34, "calc"), ("Gewicht Position [kg]", 11, "calc")]
header(wa, 12, cols_a)
wa.row_dimensions[12].height = 60
style_rows(wa, O0, O1, cols_a, {6: "#,##0.0", 7: "#,##0", 8: "#,##0.0", 9: "0", 10: "#,##0", 12: "0.0",
                                 13: "0.00", 14: "0.000", 15: "0.000", 16: "#,##0", 17: "#,##0", 18: "0",
                                 19: "0", 20: "#,##0", 22: "#,##0", 24: "#,##0.00"})
P = lambda col: f"Profile!${col}${M0}:${col}${M1}"
SD = lambda col: f"Schneiddaten!${col}${M0}:${col}${M1}"
for r in range(O0, O1 + 1):
    mp = f"MATCH($D{r},lst_Profil,0)"
    mw = f"MATCH($E{r},lst_Werkstoff,0)"
    wa[f"K{r}"] = f'=IF($D{r}="","",IFERROR(INDEX({P("B")},{mp}),""))'
    wa[f"L{r}"] = f'=IF($D{r}="","",IFERROR(INDEX({P("K")},{mp})+0,""))'
    wa[f"M{r}"] = f'=IF($D{r}="","",IFERROR(INDEX({P("E")},{mp})+0,""))'
    wa[f"N{r}"] = f'=IF(OR(L{r}="",$E{r}=""),"",IFERROR(L{r}*INDEX(Werkstoffe!$E${M0}:$E${M1},{mw})/1000,""))'
    wa[f"O{r}"] = f'=IF(OR(N{r}="",$F{r}=""),"",N{r}*$F{r}/1000)'
    wa[f"P{r}"] = f'=IF(OR($F{r}="",$G{r}=""),"",$F{r}*$G{r})'
    wa[f"Q{r}"] = f'=IF($D{r}="","",IF($J{r}<>"",$J{r},$C$9))'
    wa[f"R{r}"] = f'=IF($D{r}="","",IFERROR(IF(INDEX({P("G")},{mp})<>"",INDEX({P("G")},{mp}),$H$4),$H$4))'
    wa[f"S{r}"] = f'=IF($D{r}="","",IFERROR(IF(INDEX({P("H")},{mp})<>"",INDEX({P("H")},{mp}),$H$5),$H$5))'
    wa[f"T{r}"] = f'=IF(OR(Q{r}="",NOT(ISNUMBER(R{r})),NOT(ISNUMBER(S{r}))),"",Q{r}-R{r}-S{r})'
    wa[f"U{r}"] = (f'=IF(OR($D{r}="",$E{r}=""),"",IF(COUNTIFS(Preise!$A${M0}:$A${M1},$D{r},'
                   f'Preise!$B${M0}:$B${M1},$E{r},Preise!$I${M0}:$I${M1},"OK")>0,"ja","nein"))')
    thr = (f'_xlfn.MINIFS({SD("C")},{SD("A")},$C$8,{SD("B")},$E{r},{SD("C")},">="&M{r})')
    wa[f"V{r}"] = (f'=IF(OR(M{r}="",$E{r}="",$C$8=""),"",IF({thr}=0,"",'
                   f'SUMIFS({SD("D")},{SD("A")},$C$8,{SD("B")},$E{r},{SD("C")},{thr})))')
    wa[f"X{r}"] = f'=IF(OR(O{r}="",$G{r}=""),"",O{r}*$G{r})'
    wa[f"W{r}"] = (
        f'=IF(AND($D{r}="",$E{r}="",$F{r}="",$G{r}=""),"",'
        f'IF(ISNA({mp}),"FEHLER: Profil unbekannt",'
        f'IF(ISNA({mw}),"FEHLER: Werkstoff unbekannt",'
        f'IF(NOT(ISNUMBER(L{r})),"FEHLER: Querschnitt fehlt (Profil)",'
        f'IF(OR($F{r}="",$F{r}<=0),"FEHLER: Teilelänge fehlt",'
        f'IF(OR($G{r}="",$G{r}<1),"FEHLER: Stückzahl fehlt",'
        f'IF(NOT(ISNUMBER($H$4)),"FEHLER: Maschine fehlt/unbekannt",'
        f'IF(Q{r}>$H$7,"FEHLER: Stange länger als Maschine zulässt",'
        f'IF($F{r}+$H$6>T{r},"FEHLER: Teil länger als Nutzlänge",'
        f'IF(U{r}="nein","WARNUNG: kein gültiger Materialpreis",'
        f'IF($H{r}="","HINWEIS: Schneidweg fehlt",'
        f'IF(V{r}="","HINWEIS: keine Schneiddaten","OK"))))))))))))')

ex = [(10, "4711-001", "Holm links", "RR 42,4x2,0", "S235-10219", 1250, 24, 410.5, 4, None),
      (20, "4711-002", "Querstrebe", "RR 42,4x2,0", "S235-10219", 860, 40, 302.0, 2, None),
      (30, "4711-003", "Rahmen oben", "QR 40x40x3", "S235-10219", 2150, 12, 520.0, 3, None),
      (40, "4711-004", "Stütze", "RE 60x40x3", "S355-10219", 1795.5, 16, 618.2, 4, None),
      (50, "4711-005", "Anschlag", "RR 48,3x2,6", "S235-10219", 345, 60, 255.0, 2, None)]
for i, row in enumerate(ex, start=O0):
    for j, v in enumerate(row, start=1):
        if v is not None:
            wa.cell(row=i, column=j, value=v)

add_dv(wa, list_dv("lst_Maschine", "Bitte Maschinen-ID aus Blatt 'Maschinen' wählen."), "C8")
add_dv(wa, num_dv(500, 20000, whole=True, msg="Stangenlänge in mm (500–20000)."), "C9")
dd = DataValidation(type="date", operator="greaterThan", formula1="36526", allow_blank=True)
dd.error = "Bitte gültiges Datum eingeben."; dd.showErrorMessage = True
add_dv(wa, dd, "C7")
add_dv(wa, list_dv("lst_Profil", "Bitte Profil-ID aus Blatt 'Profile' wählen."), f"D{O0}:D{O1}")
add_dv(wa, list_dv("lst_Werkstoff", "Bitte Werkstoff-ID aus Blatt 'Werkstoffe' wählen."), f"E{O0}:E{O1}")
add_dv(wa, num_dv(1, 20000, msg="Teilelänge in mm (1–20000)."), f"F{O0}:F{O1}")
add_dv(wa, num_dv(1, 100000, whole=True, msg="Stückzahl als ganze Zahl ≥ 1."), f"G{O0}:G{O1}")
add_dv(wa, num_dv(0, 1000000, msg="Schneidweg in mm (≥ 0)."), f"H{O0}:H{O1}")
add_dv(wa, num_dv(0, 1000, whole=True, msg="Anzahl Einstiche als ganze Zahl ≥ 0."), f"I{O0}:I{O1}")
add_dv(wa, num_dv(500, 20000, whole=True, msg="Stangenlänge in mm (500–20000)."), f"J{O0}:J{O1}")
add_dv(wa, num_dv(1, 99999, whole=True, msg="Positionsnummer als ganze Zahl."), f"A{O0}:A{O1}")
wa["H12"].comment = Comment("Wird in Schritt 2 automatisch aus der STEP-Datei gefüllt; bis dahin manuell.", "Kalkulation")
wa["J12"].comment = Comment("Leer = Standard-Stangenlänge aus C9.", "Kalkulation")

wrng = f"W{O0}:W{O1}"
for prefix, color in (("FEHLER", "F8CBAD"), ("WARNUNG", "FFD966"), ("HINWEIS", "FFF2CC"), ("OK", "C6EFCE")):
    wa.conditional_formatting.add(wrng, FormulaRule(formula=[f'LEFT($W{O0},{len(prefix)})="{prefix}"'],
                                                    fill=PatternFill("solid", fgColor=color)))
wa.freeze_panes = "E13"
wa.auto_filter.ref = f"A12:X{O1}"

for s in wb.worksheets:
    s.sheet_view.zoomScale = 90
wb.save(OUT)
print("saved", OUT)
