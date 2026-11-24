"""Stabilitäts-Auftrag 18.11.2026 (Patrick, Paket C): Diagnose für Administratoren und Langzeittest.

Geprüft wird ohne Bildschirm:
- diagnose: Rechnungen zählen (Anzahl, Dauer, langsam), unnötige Mehrfachberechnung mit gleichen Eingaben erkennen
  (andere Eingaben nicht), Datenbank-Anweisungen zählen, Merker-Treffer im Bericht, Zähler zurücksetzen,
- im Angebot: Kalkulation, Optimieren und Maschinenvergleich erscheinen im Bericht; ein Neuladen ohne Änderung meldet
  keine unnötige Kalkulation, der Bericht kostet kaum Zeit,
- Support-Paket enthält diagnose.txt, Hauptadmin-Menü hat den Eintrag „Diagnose: Rechenzähler …“, das Fenster zeigt
  den Bericht und setzt die Zähler zurück,
- Langzeittest: 150 × Zelle ändern + Neuladen + Check: Merker bleiben in ihrer Größe, Arbeitsspeicher wächst nicht
  über eine Grenze, keine Ausnahme, Ergebnis am Ende gleich wie frisch geöffnet (Neustart-Probe: Datei neu öffnen).
Aufruf: python tests/test_diagnose_1811.py
"""
import gc
import os
import sys
import tempfile
import time
import tracemalloc
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import diagnose, rechenmerker, support  # noqa: E402
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])

# ------------------------------------------------------------------ Zähler
diagnose.zuruecksetzen()
with diagnose.messen("Probe", ("a", 1)):
    pass
with diagnose.messen("Probe", ("a", 2)):
    pass
with diagnose.messen("Probe", ("a", 1)):
    pass
diagnose.zaehlen("Probe", diagnose.LANGSAM_S + 0.5)
e = diagnose.stand()["rechnungen"]["Probe"]
assert (e["anzahl"], e["doppelt"], e["langsam"]) == (4, 1, 1), e
assert e["max_s"] >= diagnose.LANGSAM_S
ok("Zähler: Anzahl, langsam, gleiche Eingaben erneut = doppelt, andere Eingaben nicht")

# ------------------------------------------------------------------ im Angebot
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
AngebotSeite.CHECK_SOFORT = False
f = Hauptfenster(db, tmp, stumm=True)
aid = db.angebot_neu(dict(kunde="Diagnose", kundennr="K-2", maschine="T11", stange=6000))
for i in range(6):
    db.position_neu(aid, dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=400.0 + 70 * i,
                              stueck=2 + i, schneidweg=150.0))
s = f.angebot_oeffnen(aid)
s.optimieren()
app.processEvents()
diagnose.zuruecksetzen()
db_vorher = diagnose.stand()["db"]["anweisungen"]
s.neu_laden()
uhr = s.__dict__.get("_check_uhr")
if uhr is not None:
    uhr.stop()
s._check_jetzt()
st = diagnose.stand()
assert st["rechnungen"]["Kalkulation"]["anzahl"] >= 1, st["rechnungen"]
assert "Maschinenvergleich" in st["rechnungen"], st["rechnungen"]
assert st["db"]["anweisungen"] > db_vorher, st["db"]
k_vorher = st["rechnungen"]["Kalkulation"]
s.neu_laden()
st2 = diagnose.stand()["rechnungen"]["Kalkulation"]
assert st2["doppelt"] == k_vorher["doppelt"], (k_vorher, st2)       # gleiche Eingaben: aus dem Merker, nicht doppelt
t = time.perf_counter()
text = diagnose.bericht()
assert time.perf_counter() - t < 0.5
assert "Kalkulation" in text and "Maschinenvergleich" in text and "Datenbank:" in text and "Merker" in text, text
assert any(m["name"].startswith("Rechenlauf: ") for m in diagnose.stand()["merker"])
ok("Angebot: Kalkulation, Maschinenvergleich, Datenbank und Merker im Bericht; Neuladen ohne Änderung nicht doppelt")

# ------------------------------------------------------------------ Support-Paket, Menü, Fenster
erg = support.erstellen(db, ziel_ordner=tmp / "sp", protokoll_ordner=tmp / "prot",
                        system=[("Test", "ok", "", "", "ok")])
with zipfile.ZipFile(erg["pfad"]) as z:
    assert "diagnose.txt" in z.namelist() and "Rechnungen" in z.read("diagnose.txt").decode("utf-8")
assert "Diagnose: Rechenzähler …" in f.hauptadmin_aktionen, list(f.hauptadmin_aktionen)
from rohrlaser import hauptadmin_menue  # noqa: E402
d = hauptadmin_menue.diagnose_fenster(f, zeigen=False)
assert "Kalkulation" in d.text.toPlainText()
d.zuruecksetzen()
assert "noch nichts gerechnet" in d.text.toPlainText(), d.text.toPlainText()[:300]
d.close()
ok("Support-Paket mit diagnose.txt, Hauptadmin-Menü „Diagnose: Rechenzähler …“, Fenster zeigt und setzt zurück")

# ------------------------------------------------------------------ Langzeittest
spalte = next(i for i, (_, fd) in enumerate(s.pos_modell.spalten) if fd is not None and getattr(fd, "name", None) == "stueck")
gc.collect()
tracemalloc.start()
basis_mb = None
for n in range(150):
    s.pos_modell.setData(s.pos_modell.index(n % 6, spalte), str(2 + n % 9))
    app.processEvents()
    uhr = s.__dict__.get("_check_uhr")
    if uhr is not None:
        uhr.stop()
    s._check_jetzt()
    if n == 20:
        gc.collect()
        basis_mb = tracemalloc.get_traced_memory()[0] / 1e6
gc.collect()
ende_mb = tracemalloc.get_traced_memory()[0] / 1e6
tracemalloc.stop()
for m in rechenmerker.alle().values():
    assert len(m) <= m.groesse, (m.name, len(m), m.groesse)
assert ende_mb - basis_mb < 40, (basis_mb, ende_mb)
lang = repr(s._rechnung())
s.f.angebot_schliessen(s) if hasattr(s.f, "angebot_schliessen") else None
db.con.close()
db2 = Datenbank(tmp / "r.db")
f2 = Hauptfenster(db2, tmp, stumm=True)
s2 = f2.angebot_oeffnen(aid)
assert repr(s2._rechnung()) == lang, "nach dem Neustart muss dasselbe herauskommen"
ok(f"Langzeit: 150 Änderungen, Speicher {basis_mb:.1f} → {ende_mb:.1f} MB, Merker begrenzt; nach Neuöffnen der Datei "
   "gleiches Ergebnis")
print("ALLE TESTS BESTANDEN")
