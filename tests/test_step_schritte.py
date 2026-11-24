"""Schritte des STEP-Imports messbar machen (Master-Auftrag Patrick 21.11.2026 „STEP-Import vollständig
weiterentwickeln“: Analyse mit getrennt messbaren Phasen, Fortschritt mit Phase und Anzahl).

- S1 lies_step_info/datei_lesen: Dauer je Schritt (lesen, umwandeln/heilen, Struktur, Kopien suchen) und Zahl der
  Kopien in info["phasen"]; die Messung selbst bleibt unverändert
- S2 Tempo-Protokoll: ZEITEN enthält je verteilter Datei die Schritte; tempo.log nennt sie
- S3 Fortschritt: Schritt der Messung (gelesen, Körper messen, Baugruppe auswerten)

Aufruf: python tests/test_step_schritte.py
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]

import step_geometrie  # noqa: E402
import step_messen  # noqa: E402
from erzeuge_struktur_teile import Dokument, lage  # noqa: E402
from test_step_wie_modell import box  # noqa: E402

fehler = 0


def pruefe(ok, text):
    global fehler
    print(("OK     " if ok else "FEHLER ") + text)
    fehler += not ok


tmp = Path(tempfile.mkdtemp())
d = Dokument()
platte = d.teil("Platte", box(0, 0, 0, 100, 50, 5))
d.baugruppe("Gestell", [(platte, lage()), (platte, lage(0, 200, 0)), (platte, lage(0, 400, 0, um_x=0.5)),
                        (d.teil("Leiste", box(0, 0, 0, 300, 20, 5)), lage(500, 0, 0))])
pfad = tmp / "Schritte.step"
with contextlib.redirect_stdout(io.StringIO()):
    d.schreiben(pfad)
gel = step_geometrie.datei_lesen(pfad)
ph = gel.info.get("phasen") or {}
pruefe(all(isinstance(ph.get(k), float) and ph[k] >= 0 for k in ("lesen_s", "uebertragen_s", "struktur_s", "kopien_s")),
       f"S1 Dauer je Schritt beim Lesen ({', '.join(sorted(ph))})")
pruefe(ph.get("verschoben") == len(gel.gleich) == 1 and ph.get("gedreht") == len(gel.gedreht) == 1,
       f"S1 Zahl der Kopien: {ph.get('verschoben')} verschoben, {ph.get('gedreht')} gedreht")

aus = io.StringIO()
with contextlib.redirect_stdout(aus):
    step_messen._zeiten_melden([("datei", "Schritte.step", None, 0.4, "geteilt")], 1.0, 2, {"Schritte.step": ph})
z = json.loads(aus.getvalue().strip()[7:])
sch = z["dateien"]["Schritte.step"].get("schritte") or {}
pruefe(sch.get("verschoben") == 1 and "lesen_s" in sch and z["dateien"]["Schritte.step"]["lesen"] == 0.4,
       "S2 ZEITEN mit Schritten je Datei")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import tempo  # noqa: E402
from rohrlaser.angebot_fenster import step_messung_protokollieren  # noqa: E402

with tempfile.TemporaryDirectory() as t:
    w = tempo.Waechter(Path(t))
    w.starten()
    try:
        text = step_messung_protokollieren(12.0, 1, {"zeiten": z}, ["x"]) or ""
    finally:
        w.stoppen()
pruefe("STEP lesen" in text and "Kopien: 1 verschoben, 1 gedreht" in text, f"S2 tempo.log: {text[-150:]}")
pruefe([step_messen.phase_text(k, 8) for k in (0, 3, 9)] == ["Datei gelesen, Körper werden verteilt", "Körper messen",
                                                             "Baugruppe auswerten (Anbauteile, Verbund, Nähte)"],
       "S3 Schritt der Messung im Fortschritt")
if fehler:
    print(f"{fehler} Fehler")
    sys.exit(1)
print("Alle Tests bestanden.")
