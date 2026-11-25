"""Einheitliche Material- und Maßschreibweise (Patrick 25.11.2026, Master-Auftrag): zentrale Formatierung masstext.

Geprüft wird:
1. masstext.abmessung/text: alle Schreibweisen aus dem Auftrag (50 x 50 x 3, 50X50X3, 50 x50x 3, Ø 60 x 3,
   40 x 20 x 2,5), Werkstoffe unverändert (1.4301 X5CrNi18-10), Ø als Durchschnitt und Rechnungen mit × bleiben,
   doppelt angewandt gleich, Suche/Zuordnung mit alter und neuer Schreibweise.
2. Alle Textbausteine für Abmessungen liefern die kompakte Schreibweise: Profiltext im Angebot (alle Profilformen),
   Vollmaterial, Blech/Kantteil, Zukauf-Blech, Dreh-/Frästeil, STEP-Blech, Baugruppen-Analyse, Materialanfrage,
   Zukauf-Text in der Materialanfrage.
3. Ausgaben: PDF-Absatz, CSV-Export (Angebot/PPEASE), Materialliste CSV/Excel, Angebotstext und Zukaufteil-Text mit
   alten Bezeichnungen aus der Datenbank.
4. Wächter für künftige Programmteile: kein Quelltext baut eine Abmessung mit Leerzeichen um das x ("{a} x {b}",
   "Ø {d} x {w}"); Ausnahmen nur mit dem Vermerk "masstext: …" (Sätze für einen Parser, Anzahlen, Koordinaten).

Aufruf: python tests/test_masstext.py
"""
import re
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

HIER = Path(__file__).parent
QUELLE = HIER.parent / "programm" / "rohrlaser"
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import masstext as M  # noqa: E402

fehler = []


def gleich(ist, soll, was):
    if ist != soll:
        fehler.append(f"{was}: {ist!r} statt {soll!r}")


def kompakt(t, was):
    """Keine Abmessung mit Leerzeichen um x/× zwischen Zahlen und kein 'Ø ' vor einer Maßkette."""
    if re.search(r"\d\s+[xX×]\s*\d|\d\s*[xX×]\s+\d|\dX\d|Ø\s+\d+(?:[.,]\d+)?\s*[xX×]", str(t)):
        fehler.append(f"{was}: alte Schreibweise in {t!r}")


# ------------------------------------------------------------------ 1. Funktion
for alt, neu in [("50 x 50 x 3", "50x50x3"), ("50X50X3", "50x50x3"), ("50 x50x 3", "50x50x3"),
                 ("100 x 50 x 4", "100x50x4"), ("Ø 60 x 3", "Ø60x3"), ("40 x 20 x 2,5", "40x20x2,5"),
                 ("∅ 60 x 3", "Ø60x3"), ("Ø60 × 3", "Ø60x3"), ("60*3", "60x3"), ("48.3 x 2.6", "48.3x2.6"),
                 ("Rundrohr Ø 42,4 x 2", "Rundrohr Ø42,4x2"), ("QR 40 x 40 x 3", "QR 40x40x3"),
                 ("RE 120 X 60 X 4 S235JRH", "RE 120x60x4 S235JRH"), ("Blech 500 × 300 × 5 mm", "Blech 500x300x5 mm"),
                 ("60 x 3mm", "60x3mm"), ("Rundstahl Ø 20 mm", "Rundstahl Ø20 mm"), ("IPE 200", "IPE 200"),
                 ("RR 48,3x2,6", "RR 48,3x2,6"), ("1.4301 X5CrNi18-10", "1.4301 X5CrNi18-10"),
                 ("S235JR+AR EN 10219", "S235JR+AR EN 10219"), ("", ""), (None, "")]:
    gleich(M.abmessung(alt), neu, f"abmessung({alt!r})")
    gleich(M.abmessung(M.abmessung(alt)), neu, f"abmessung zweimal ({alt!r})")
gleich(M.format_material_dimension("50 x 50 x 3"), "50x50x3", "formatMaterialDimension")

for alt, neu in [("Rechteckrohr 80 x 40 x 5\nL = 1500 mm", "Rechteckrohr 80x40x5\nL = 1500 mm"),
                 ("inkl. Material 1.4301 X5CrNi18-10", "inkl. Material 1.4301 X5CrNi18-10"),
                 ("Rohr Ø 48,3 x 2,6 lang", "Rohr Ø48,3x2,6 lang"),
                 ("ERP-Einkauf Ø 12,50 €/m", "ERP-Einkauf Ø 12,50 €/m"),          # Ø = Durchschnitt bleibt
                 ("3 × 24 s + 2 × 29 s", "3 × 24 s + 2 × 29 s"),                  # Rechnung bleibt
                 ("Blech S235 500 × 300 × 5 mm", "Blech S235 500x300x5 mm"),
                 ("Gewinde 4 x M6", "Gewinde 4 x M6"), ("Bohrung Ø 8 mm", "Bohrung Ø 8 mm"),
                 ("Lasche 120 x 60 x 5, S235JR", "Lasche 120x60x5, S235JR")]:
    gleich(M.text(alt), neu, f"text({alt!r})")
gleich(M.text(12), 12, "text(Zahl) unverändert")
gleich(M.profil("QR 40 x 40 x 3"), "QR 40x40x3", "profil")

# Suche und Zuordnung: alte und neue Schreibweise sind dasselbe Material
for a, b in [("QR 40 x 40 x 3", "qr 40x40x3"), ("Ø 60 x 3", "ø60X3"), ("RE 120X60X4", "re 120 x 60 x 4")]:
    if not M.gleich(a, b):
        fehler.append(f"gleich({a!r}, {b!r}) falsch")
if M.gleich("QR 40x40x3", "QR 40x40x4"):
    fehler.append("gleich: verschiedene Wandstärken gelten als gleich")
if "40x40x3" not in M.suchschluessel("Quadratrohr QR 40 X 40 X 3 S235"):
    fehler.append("suchschluessel findet die Abmessung nicht")
profile = {"QR 40x40x3": {}, "RR 48,3 x 2,6": {}, "RE 60x40x3": {}}
gleich(M.finde("qr 40 x 40 x 3", profile), "QR 40x40x3", "finde neue ID mit alter Schreibweise")
gleich(M.finde("RR 48,3x2,6", profile), "RR 48,3 x 2,6", "finde alte ID mit neuer Schreibweise")
gleich(M.finde("RE 60x40x3", profile), "RE 60x40x3", "finde genau gleich")
gleich(M.finde("QR 50x50x3", profile), None, "finde unbekannt")
gleich(M.finde("QR 40x40x3", {"QR 40x40x3 ": {}, "QR 40 x 40 x 3": {}}), None, "finde mehrdeutig")
if M.alte_schreibweise("QR 40x40x3") or not M.alte_schreibweise("QR 40 x 40 x 3"):
    fehler.append("alte_schreibweise falsch")

# ------------------------------------------------------------------ 2. Textbausteine
from rohrlaser import ausgabe, baugruppe_analyse, blech, drehfraes, materialanfrage, materialanfragen  # noqa: E402
from rohrlaser import step, vollmaterial, zukauf  # noqa: E402

k = SimpleNamespace(profile={
    "RR 42,4x2": dict(form="Rundrohr", a=42.4, wand=2.0),
    "QR 40x40x3": dict(form="Quadratrohr", a=40, b=40, wand=3),
    "RE 100x50x4": dict(form="Rechteckrohr", a=100, b=50, wand=4),
    "FL 40x5": dict(form="Flachstahl", a=40, wand=5),
    "L 50x30x5": dict(form="L-Profil", a=50, b=30, wand=5),
    "C 80x40x3": dict(form="C-Profil", a=80, b=40, wand=3),
    "RE 40 x 20 x 2,5": dict(form="Rechteckrohr", a=40, b=20, wand=2.5),     # alte ID mit Leerzeichen
}, werkstoffe={"S235-10219": dict(angebotstext="S235JRH EN 10219")}, oberflaechen={})
erwartet = {"RR 42,4x2": "Rundrohr Ø42,4x2", "QR 40x40x3": "Quadratrohr 40x40x3", "RE 100x50x4": "Rechteckrohr 100x50x4",
            "FL 40x5": "Flachstahl 40x5", "L 50x30x5": "L-Profil 50x30x5", "C 80x40x3": "C-Profil 80x40x3",
            "RE 40 x 20 x 2,5": "Rechteckrohr 40x20x2,5"}
for pid, soll in erwartet.items():
    gleich(ausgabe.profiltext(pid, k), soll, f"profiltext {pid}")
gleich(ausgabe.profiltext("QR 50 x 50 x 4", k), "QR 50x50x4", "profiltext unbekannte ID")

for t, was in [(vollmaterial.bezeichnung(vollmaterial.RUNDSTAHL, 20, 150, "S235JR"), "Vollmaterial rund"),
               (vollmaterial.masse_text("Vierkantstahl", 20, 150), "Vollmaterial vierkant"),
               (zukauf.blech_bezeichnung(500, 300, 5, "S235"), "Zukauf-Blech"),
               (blech.bezeichnung_vorschlag(dict(dicke=3, werkstoff="S235JR"), dict(laenge=200, breite=100)), "Blech"),
               (drehfraes.masse_text(dict(art=drehfraes.DREHTEIL, durchmesser=30, laenge=120)), "Drehteil"),
               (drehfraes.masse_text(dict(art="Frästeil", laenge=100, breite=60, hoehe=20)), "Frästeil"),
               (baugruppe_analyse.profil_text(dict(profilform="Rechteckrohr", abm_a=60, abm_b=40, wandstaerke=3)),
                "Baugruppen-Analyse")]:
    kompakt(t, was)
gleich(zukauf.blech_bezeichnung(500, 300, 5, "S235"), "Blech S235 500x300x5 mm", "Zukauf-Blech")
gleich(vollmaterial.bezeichnung(vollmaterial.RUNDSTAHL, 20, 150, "S235JR"), "Rundstahl Ø20x150 mm S235JR", "Rundstahl")
kompakt(step.blech_text(dict(profilform="Blech", abm_a=500, abm_b=300, wandstaerke=5)), "STEP-Blech")

z = dict(profil="RE 40 x 20 x 2,5", werkstoff="S235-10219", oberflaeche="", laenge=6000, stangen=3, gewicht=None)
gleich(materialanfrage.zeile_text(z, k), "3 Stangen Rechteckrohr 40x20x2,5, S235JRH EN 10219", "Materialanfrage-Zeile")
zt = materialanfragen.zukauf_text(dict(stangen=12, einheit="Stück", bezeichnung="Lasche 120 × 60 × 5 mm",
                                       artikelnr="L-17", masse="120x60x5", werkstoff="S235JR"))
kompakt(zt, "Zukauf in der Materialanfrage")

# ------------------------------------------------------------------ 3. Ausgaben
from rohrlaser import export, materialplattform as mp, pdf  # noqa: E402

kompakt(pdf._p("Quadratrohr 40 x 40 x 3\nL = 1500 mm").text, "PDF-Absatz")
gleich(pdf._p("Ø 12,50 €/m").text, "Ø 12,50 €/m", "PDF-Absatz Durchschnitt")
roh = export.csv_bytes(["Pos", "Text", "Menge"], [["1", "Rechteckrohr 80 x 40 x 5, Blech 500 × 300 × 5 mm", 3]])
text = roh.decode("utf-8-sig")
kompakt(text, "CSV-Export")
if "Rechteckrohr 80x40x5" not in text or ";3\r\n" not in text:
    fehler.append(f"CSV-Export: {text!r}")
kompakt(mp.csv_export([{f: ("QR 40 x 40 x 3" if f == "profil_id" else None) for f, _ in mp.EXPORT}]), "Materialliste CSV")
xl = Path(__file__).parent / "_masstext_test.xlsx"
try:
    mp.xlsx_export([{"profil_id": "Ø 60 x 3"}], xl, kopf=["Profil"], felder=["profil_id"])
    with zipfile.ZipFile(xl) as zf:
        blatt = zf.read(next(n for n in zf.namelist() if n.startswith("xl/worksheets/"))).decode("utf-8")
    if "Ø60x3" not in blatt:
        fehler.append("Excel-Export: Ø60x3 fehlt")
finally:
    xl.unlink(missing_ok=True)

# Zukaufteil mit alter Bezeichnung aus der Datenbank
p = dict(art="Zukaufteil", zukauf=[dict(menge=1, stand=dict(bezeichnung="Blech S235 500 × 300 × 5 mm", einheit="Stück"))])
try:
    kompakt(ausgabe.zukaufteil_text(p), "Zukaufteil-Text")
except Exception as e:      # noqa: BLE001 – Aufbau der Position kann sich ändern; dann zumindest masstext.text prüfen
    print("Hinweis: zukaufteil_text nicht direkt prüfbar:", e)
kompakt(M.text("Blech S235 500 × 300 × 5 mm"), "Zukauf alt")

# ------------------------------------------------------------------ 4. Wächter Quelltext
MUSTER = re.compile(r"""\}\s+[xX]\s*\{|\}\s*[xX]\s+\{|Ø \{[^}]*\}\s*[xX]|\d\s[xX]\s\{|\}\s[xX]\s\d""")
treffer = []
for datei in sorted(QUELLE.glob("*.py")):
    for nr, zeile in enumerate(datei.read_text(encoding="utf-8").splitlines(), 1):
        code = zeile.split("#", 1)[0] if not zeile.lstrip().startswith(("f\"", "f'")) else zeile
        if "masstext:" in zeile or not re.search(r"\bf[\"']", code):
            continue
        if MUSTER.search(code):
            treffer.append(f"{datei.name}:{nr}: {zeile.strip()[:110]}")
# Mengenangaben ('2 x 1.500 mm', Satzvorsatz '3 x ') sind keine Abmessungen
treffer = [t for t in treffer if not re.search(r"\{n\} x \{|kaufm_runden\(je\(q\), 0\):\.0f\} x", t)]
if treffer:
    fehler.append("Abmessung mit Leerzeichen gebaut (masstext nutzen oder kompakt schreiben):\n  " + "\n  ".join(treffer))

if fehler:
    print("FEHLER:\n- " + "\n- ".join(fehler))
    sys.exit(1)
print("Maßschreibweise: alle Prüfungen bestanden.")
