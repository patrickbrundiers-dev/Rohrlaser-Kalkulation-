"""Prüft das IT-Handbuch des Servers (anleitung/erzeuge_it_handbuch.py, Patrick 27.11.2026): es entsteht ohne Fehler,
nennt die aktuellen Werte des Programms (Version, Port, Verbindungen, Sicherung, Zertifikat, PostgreSQL-Version)
und jeden Befehl von server_betrieb. Kommt ein neuer Server-Befehl dazu, steht er automatisch in der
Befehlsreferenz; fehlt er dort (z. B. weil die Hilfe anders aufgebaut wurde), schlägt dieser Test fehl.

Aufruf: python tests/test_it_handbuch.py
"""
import re
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "anleitung"))
import erzeuge_it_handbuch as it  # noqa: E402
from rohrlaser import VERSION  # noqa: E402
from rohrlaser import server_betrieb as sb  # noqa: E402
from rohrlaser import server_sicherung as ss  # noqa: E402


def ok(text):
    print("OK  ", text)


assert re.fullmatch(r"\d+\.\d+", it.pg_version()), "PostgreSQL-Version aus paket.yml gelesen"
ok(f"PostgreSQL-Version aus dem Bau-Workflow: {it.pg_version()}")

pg = it.pg_einstellungen()
assert pg["port"] == str(sb.PORT) and pg["max_connections"] == str(sb.MAX_VERBINDUNGEN) and pg["ssl"] == "on"
assert pg["shared_buffers"] and pg["password_encryption"] == "scram-sha-256"
ok("Datenbank-Einstellungen aus derselben Funktion wie beim Einrichten")

namen = {b.split()[0] for b, _ in it.befehle()}
# die erlaubten Befehle aus main(): choices der Befehlszeile
quelle = (HIER.parent / "programm" / "rohrlaser" / "server_betrieb.py").read_text(encoding="utf-8")
choices = set(re.findall(r'"(\w+)"', re.search(r'"befehl", choices=\((.*?)\)\)', quelle, re.S).group(1)))
assert choices and choices <= namen, f"Befehle fehlen in der Befehlsreferenz: {sorted(choices - namen)}"
assert all(t for _, t in it.befehle()), "jeder Befehl mit Beschreibung"
ok(f"Befehlsreferenz vollständig ({len(choices)} Befehle)")

with tempfile.TemporaryDirectory() as tmp:
    ziel = it.erzeugen(Path(tmp) / "IT-Handbuch_Server.pdf")
    daten = ziel.read_bytes()
    assert daten.startswith(b"%PDF") and len(daten) > 50_000
    seiten = len(re.findall(rb"/Type\s*/Page[^s]", daten))
    assert seiten >= 15, seiten
    ok(f"PDF erzeugt: {seiten} Seiten, {len(daten) // 1024} KB")
    try:
        import pypdfium2 as pdfium
    except ImportError:
        pdfium = None
    if pdfium:
        pdf = pdfium.PdfDocument(str(ziel))
        text = "\n".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
        pdf.close()
        text = re.sub(r"\s+", " ", text)
        for erwartet in (VERSION, f"TCP {sb.PORT}", str(sb.MAX_VERBINDUNGEN), f"{sb.ZERT_JAHRE} Jahre",
                         f"{ss.BEHALTEN} neuesten", f"{ss.WARNEN_H} Stunden", sb.ZUGANG_DATEI,
                         f"PostgreSQL {it.pg_version()}"):
            assert erwartet in text, f"fehlt im PDF: {erwartet}"
        for befehl in sorted(choices):
            assert befehl in text, f"Befehl fehlt im PDF: {befehl}"
        for kapitel in ("Voraussetzungen", "Vorbereitung durch die IT", "Netzwerk und Sicherheit",
                        "Einrichtung Schritt für Schritt", "Sicherung, Wiederherstellung und Notfall",
                        "Störungen und Lösungen", "Abnahme-Checkliste"):
            assert kapitel in text, kapitel
        ok("Text im PDF: Version, Port, Verbindungen, Zertifikat, Sicherung, alle Befehle, alle Kapitel")
print("alle Prüfungen bestanden")
