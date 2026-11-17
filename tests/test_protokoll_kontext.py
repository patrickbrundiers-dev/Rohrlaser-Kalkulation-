"""Prüft das Fehlerprotokoll nach der Systemprüfung 17.11.2026 (LOG-01, ERR-01):

K1 Jede Zeile nennt Modul und Funktion, die Kopfzeile Version, Kürzel und Datenspeicher.
K2 Zugangsdaten (Passwort, Token, Bearer, Notfallcode) stehen nie im Protokoll, auch nicht im Stacktrace.
K3 warnung() schreibt einen abgefangenen Fehler mit Stacktrace als WARNING, höchstens dreimal je Programmstelle.
K4 fehler_seit (Startseite „N Fehler seit gestern“) liest altes und neues Format; Warnungen zählen dort nicht.
K5 Ein abgefangener Fehler in der Zusatzformel ändert das Ergebnis nicht, steht aber im Protokoll.
K6 Keine neuen stillen Ausnahmen: except Exception: pass/continue ohne Protokoll höchstens so oft wie heute.

Aufruf: python tests/test_protokoll_kontext.py
"""
import ast
import datetime
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
WURZEL = HIER.parent
sys.path.insert(0, str(WURZEL / "programm"))

from rohrlaser import protokoll, zusatz_formel  # noqa: E402

ordner = Path(tempfile.mkdtemp()) / "Protokoll"
pfad = protokoll.einrichten(ordner, zeigen=lambda text, details: None)


def inhalt():
    for h in protokoll._log.handlers:
        h.flush()
    return pfad.read_text(encoding="utf-8")


# ---------------------------------------------------------------- K1 Modul, Funktion, Kopfzeile
def start_melden():
    protokoll.kopfzeile("9.9.9", "PB", "postgres")


start_melden()
zeile = [z for z in inhalt().splitlines() if "Start Version" in z][0]
assert "INFO test_protokoll_kontext.start_melden | Start Version 9.9.9, Kürzel PB, Datenspeicher postgres" in zeile, zeile

# ---------------------------------------------------------------- K2 Zugangsdaten entfernt
geheim = ["S3hrG3heim!", "tok_abc123", "eyJhbGciOi.xyz", "NOTF-1234"]
protokoll.info("Verbindung host=localhost port=5432 password=S3hrG3heim! dbname=rohrlaser")
protokoll.info('Antwort {"token": "tok_abc123"} Authorization: Bearer eyJhbGciOi.xyz')
try:
    raise RuntimeError("Anmeldung fehlgeschlagen, Passwort: S3hrG3heim! Notfallcode=NOTF-1234")
except RuntimeError:
    protokoll.warnung("Test mit Zugangsdaten")
text = inhalt()
for g in geheim:
    assert g not in text, (g, text)
assert "password=***" in text and '"token": "***"' in text and "Bearer ***" in text, text
assert protokoll.bereinigen("passwort=abc;rest") == "passwort=***;rest"
assert protokoll.bereinigen("Gewinn 0.21, Menge 5") == "Gewinn 0.21, Menge 5"      # normale Werte bleiben


# ---------------------------------------------------------------- K3 warnung mit Stacktrace, begrenzt
def rechnen_mit_fehler(i):
    try:
        return 1 / 0
    except ZeroDivisionError:
        protokoll.warnung(f"Schleife {i}")


for i in range(10):
    rechnen_mit_fehler(i)
text = inhalt()
eintraege = [z for z in text.splitlines() if "WARNING test_protokoll_kontext.rechnen_mit_fehler | Schleife" in z]
assert len(eintraege) == protokoll.WARNUNG_JE_STELLE == 3, eintraege
assert "weitere an dieser Stelle werden nicht mehr protokolliert" in eintraege[-1]
assert text.count("ZeroDivisionError: division by zero") == 3, text

# ---------------------------------------------------------------- K4 fehler_seit: alt + neu, Warnungen zählen nicht
alt = ordner / "fehler.log.1"
alt.write_text("2026-11-10 08:00:00,123 ERROR Unerwarteter Fehler\nTraceback …\nValueError: alt\n", encoding="utf-8")
try:
    raise KeyError("neu")
except KeyError:
    protokoll._haken(*sys.exc_info())
f = protokoll.fehler_seit(ordner, datetime.datetime(2026, 1, 1))
texte = [t for _, t in f]
assert texte[0] == "ValueError: alt" and texte[-1] == "KeyError: 'neu'", texte
assert len(f) == 2, texte

# ---------------------------------------------------------------- K5 Zusatzformel: Ergebnis gleich, Fehler protokolliert
vorher = inhalt().count("Zusatzformel:")
w = zusatz_formel.groessen({"menge": 1}, None)          # k=None: G/F lassen sich nicht berechnen
assert isinstance(w, dict)
assert inhalt().count("Zusatzformel:") > vorher, "abgefangener Fehler der Zusatzformel fehlt im Protokoll"

# ---------------------------------------------------------------- K6 keine neuen stillen Ausnahmen
GRENZE = 72          # Stand 0.9.377: 91 vor der Systemprüfung, 19 in Kalkulations-, Ausgabe- und Abgleichwegen protokolliert
still = []
for datei in sorted((WURZEL / "programm").rglob("*.py")):
    baum = ast.parse(datei.read_text(encoding="utf-8"))
    for knoten in ast.walk(baum):
        if (isinstance(knoten, ast.ExceptHandler) and (knoten.type is None or ast.unparse(knoten.type) in (
                "Exception", "BaseException")) and len(knoten.body) == 1
                and isinstance(knoten.body[0], (ast.Pass, ast.Continue))):
            still.append(f"{datei.relative_to(WURZEL)}:{knoten.lineno}")
assert len(still) <= GRENZE, (f"{len(still)} stille 'except Exception: pass' (höchstens {GRENZE}) – neue Stellen bitte "
                              "mit protokoll.warnung(...) protokollieren:\n" + "\n".join(still))

print(f"OK: Protokoll mit Modul/Funktion, ohne Zugangsdaten, Warnungen begrenzt, {len(still)} stille Ausnahmen "
      f"(Grenze {GRENZE})")
