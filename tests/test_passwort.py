"""Passwort der Einstellungen als PBKDF2-Hash (Plan „Intelligenteres Programm“ C5).

P1 Hash bilden/prüfen: richtig, falsch, leer, Klartext (alt) gilt weiter, kaputter Hash ist nie richtig;
P2 in der Datendatei steht nie der Klartext (einstellung_setzen, stammdaten_ersetzen);
P3 alte Datendatei mit Klartext-Passwort wird beim Öffnen umgestellt, das Passwort gilt weiter;
P4 Oberfläche: Reiter Einstellungen öffnet mit dem Passwort, Feld zeigt keinen Hash, Entfernen = ohne Passwort;
P5 Admin-Passwort beim Start (Lizenz) prüft gegen den Hash.
Aufruf: python tests/test_passwort.py
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import passwort  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="passwort_"))
fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


def roh(pfad):
    con = sqlite3.connect(pfad)
    r = con.execute("SELECT wert FROM einstellungen WHERE name='passwort'").fetchone()
    con.close()
    return None if r is None else json.loads(r[0])


# ------------------------------------------------------------------ P1
h = passwort.hash_bilden("geheim")
pruefe(passwort.ist_hash(h) and "geheim" not in h, "P1 Hash im Format pbkdf2_sha256$…, ohne Klartext")
pruefe(passwort.pruefen("geheim", h) and not passwort.pruefen("Geheim", h) and not passwort.pruefen("", h),
       "P1 richtig / falsch / leer")
pruefe(passwort.hash_bilden("geheim") != h, "P1 Salz: gleicher Text ergibt anderen Hash")
pruefe(passwort.pruefen("x", "") and passwort.pruefen("", None), "P1 ohne Passwort: immer richtig")
pruefe(passwort.pruefen("av", "av") and not passwort.pruefen("avx", "av"), "P1 Klartext (alt) gilt weiter")
pruefe(not passwort.pruefen("geheim", "pbkdf2_sha256$10$zz$00"), "P1 kaputter Hash ist nie richtig")
pruefe(passwort.speicherwert(h) == h and passwort.speicherwert("") == "", "P1 Hash und leer bleiben unverändert")

# ------------------------------------------------------------------ P2
db = Datenbank(tmp / "neu.db")
pruefe(roh(tmp / "neu.db") is None and db.passwort_pruefen("av") and not db.passwort_pruefen("falsch"),
       "P2 neue Datendatei: Vorgabe gilt, kein Passwort in der Datei")
db.einstellung_setzen("passwort", "geheim")
pruefe(passwort.ist_hash(roh(tmp / "neu.db")) and db.passwort_pruefen("geheim") and not db.passwort_pruefen("av"),
       "P2 einstellung_setzen speichert den Hash")
db.stammdaten_ersetzen({}, {"passwort": "anders"}, "Test")
pruefe(passwort.ist_hash(roh(tmp / "neu.db")) and db.passwort_pruefen("anders"), "P2 stammdaten_ersetzen speichert den Hash")
db.einstellung_setzen("passwort", "")
pruefe(roh(tmp / "neu.db") == "" and db.passwort_pruefen("egal"), "P2 leer = ohne Passwort")
db.schliessen()

# ------------------------------------------------------------------ P3
db = Datenbank(tmp / "alt.db")
db.con.execute("INSERT OR REPLACE INTO einstellungen (name, wert) VALUES ('passwort', ?)", (json.dumps("alt123"),))
db.con.commit()
db.schliessen()
pruefe(roh(tmp / "alt.db") == "alt123", "P3 Ausgangslage: Klartext in der alten Datei")
db = Datenbank(tmp / "alt.db")
pruefe(passwort.ist_hash(roh(tmp / "alt.db")) and db.passwort_pruefen("alt123") and not db.passwort_pruefen("x"),
       "P3 beim Öffnen auf Hash umgestellt, altes Passwort gilt weiter")

# ------------------------------------------------------------------ P4
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser.fenster import EinstellungenSeite, PasswortEingabe  # noqa: E402

seite = EinstellungenSeite(db, lambda *a, **k: None, gruppen=("Zugang",))
w = seite.felder["passwort"]
pruefe(isinstance(w, PasswortEingabe) and w.feld.text() == "" and w.weg.isEnabled(), "P4 Feld leer, kein Hash sichtbar")
w.feld.setText("neu789")
w.feld.editingFinished.emit()
pruefe(db.passwort_pruefen("neu789") and not db.passwort_pruefen("alt123") and w.feld.text() == "",
       "P4 neues Passwort eingegeben: gespeichert (als Hash), Feld wieder leer")
w.feld.editingFinished.emit()
pruefe(db.passwort_pruefen("neu789"), "P4 leeres Feld verlassen ändert nichts")
w.weg.click()
pruefe(db.einstellung("passwort") == "" and not w.weg.isEnabled(), "P4 Entfernen = ohne Passwort")
db.einstellung_setzen("passwort", "neu789")

# ------------------------------------------------------------------ P5
from rohrlaser import lizenz  # noqa: E402

st = lizenz.LizenzStelle.__new__(lizenz.LizenzStelle)
st.db, st.admin_ok, st.zustand = db, False, None
st.pruefen = lambda *a, **k: None
pruefe(not st.admin_freigeben("falsch") and st.admin_freigeben("neu789") and st.admin_ok,
       "P5 Admin-Passwort prüft gegen den Hash")
db.schliessen()

print()
print("Alles in Ordnung." if not fehler else f"{len(fehler)} Fehler.")
sys.exit(1 if fehler else 0)
