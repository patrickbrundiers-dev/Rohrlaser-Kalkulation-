"""Plan „Quellcode schützen“: eigene Module übersetzt statt als Bytecode (Q3, programm/kompilieren.py und
release_pruefen.py --kompiliert), Download-Bereich im Update-Repository (Q2, paket.yml) und Lizenzbedingungen (Q4).

Das Übersetzen selbst (Cython, C-Compiler) läuft nur im Windows-Build; hier wird geprüft, dass Modulliste, Tausch in
den .spec-Dateien, Release-Prüfung, Workflow und Lizenzbedingungen zusammenpassen.

Aufruf: python tests/test_quellcode_schutz.py
"""
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
PROGRAMM = WURZEL / "programm"
sys.path.insert(0, str(PROGRAMM))
import kompilieren  # noqa: E402
import release_pruefen as rp  # noqa: E402
import rohrlaser  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Q3 Modulliste
module = dict(kompilieren.module())
quellen = {f"rohrlaser/{p.name}" for p in (PROGRAMM / "rohrlaser").glob("*.py")}
quellen |= {f"step_messung/{p.name}" for p in (PROGRAMM / "step_messung").glob("step_*.py")}
assert set(module.values()) == quellen - kompilieren.BLEIBT, quellen - kompilieren.BLEIBT - set(module.values())
assert module["rohrlaser.rechnen"] == "rohrlaser/rechnen.py" and module["rohrlaser.lizenz"] == "rohrlaser/lizenz.py"
assert module["rohrlaser.__main__"] == "rohrlaser/__main__.py" and module["step_messen"] == "step_messung/step_messen.py"
assert "rohrlaser" not in module and "step_start" not in module
assert all(kompilieren.eigen(n) for n in module) and not kompilieren.eigen("PySide6.QtCore")
assert kompilieren.SCHNELL <= set(module) | {"rohrlaser.rohr3d"}, kompilieren.SCHNELL - set(module)
assert kompilieren.DIREKTIVEN["annotation_typing"] is False and kompilieren.DIREKTIVEN["binding"] is True
# was Python bleibt, ist nur Kopf und Aufruf
kopf = (PROGRAMM / "rohrlaser" / "__init__.py").read_text(encoding="utf-8")
assert len(kopf.splitlines()) < 20 and "def lizenzbedingungen" in kopf
start = (PROGRAMM / "step_messung" / "step_start.py").read_text(encoding="utf-8")
assert "step_messen.main()" in start and "freeze_support" in start and len(start.splitlines()) < 15
ok(f"Q3 {len(module)} eigene Module werden übersetzt, Python bleiben nur Paketkopf und Startdateien")

# ------------------------------------------------------------------ Q3 Tausch in der .spec


class Analyse:
    def __init__(self, pure):
        self.pure = list(pure)
        self.binaries = [("Qt6Core.dll", "C:/qt/Qt6Core.dll", "BINARY")]


tmp = Path(tempfile.mkdtemp(prefix="quellcode_"))
for ordner in ("rohrlaser", "step_messung"):
    (tmp / ordner).mkdir()
for name, rel in module.items():
    (tmp / rel).write_text("# Quelle")
    (tmp / rel).with_suffix(".cp312-win_amd64.pyd").write_bytes(b"MZ")
(tmp / "rohrlaser" / "__init__.py").write_text("VERSION = '0'")
(tmp / "step_messung" / "step_start.py").write_text("# Start")
pure = [("rohrlaser", "rohrlaser/__init__.py", "PYMODULE"), ("rohrlaser.rechnen", "rohrlaser/rechnen.py", "PYMODULE"),
        ("rohrlaser.__main__", "rohrlaser/__main__.py", "PYMODULE"), ("step_geometrie", "step_geometrie.py", "PYMODULE"),
        ("reportlab.pdfgen", "reportlab/pdfgen/__init__.py", "PYMODULE")]
a = Analyse(pure)
assert kompilieren.kompiliert_tauschen(a, tmp) == 3
assert [e[0] for e in a.pure] == ["rohrlaser", "reportlab.pdfgen"], a.pure
ziele = {e[0]: e for e in a.binaries}
assert "rohrlaser/rechnen.cp312-win_amd64.pyd" in ziele and "rohrlaser/__main__.cp312-win_amd64.pyd" in ziele
assert "step_geometrie.cp312-win_amd64.pyd" in ziele and ziele["step_geometrie.cp312-win_amd64.pyd"][2] == "EXTENSION"
# fehlt ein übersetztes Modul, bricht der Build ab (lieber kein Paket als ein lesbares)
(tmp / "rohrlaser" / "rechnen.cp312-win_amd64.pyd").unlink()
try:
    kompilieren.kompiliert_tauschen(Analyse(pure), tmp)
    raise AssertionError("fehlendes übersetztes Modul nicht bemerkt")
except SystemExit as e:
    assert "rohrlaser.rechnen" in str(e)
for spec in (PROGRAMM / "rohrlaser.spec", PROGRAMM / "step_messung" / "step_messung.spec"):
    text = spec.read_text(encoding="utf-8")
    assert "kompiliert_tauschen(a, os.environ[\"RL_KOMPILIERT\"])" in text and text.index("kompiliert_tauschen") < text.index("PYZ(a.pure)")
assert '"step_start.py"' in (PROGRAMM / "step_messung" / "step_messung.spec").read_text(encoding="utf-8")
ok("Q3 .spec tauscht Bytecode gegen übersetzte Module, fehlendes Modul bricht ab")

# ------------------------------------------------------------------ Q3 Release-Prüfung --kompiliert
o = tmp / "dist"
for rel in ("Rohrlaser-Angebotskalkulation.exe", "STEP-Import/STEP-Import.exe"):
    (o / rel).parent.mkdir(parents=True, exist_ok=True)
    (o / rel).write_bytes(b"MZ")
(o / "_internal" / "rohrlaser").mkdir(parents=True)
(o / "_internal" / "rohrlaser" / "rechnen.cp312-win_amd64.pyd").write_bytes(b"MZ")
(o / "STEP-Import" / "_internal").mkdir()
(o / "STEP-Import" / "_internal" / "step_geometrie.cp312-win_amd64.pyd").write_bytes(b"MZ")
assert rp.kompiliert_pruefen(o, lesen=lambda exe: []) == []
befunde = rp.kompiliert_pruefen(o, lesen=lambda exe: ["rohrlaser.rechnen"] if exe.name.startswith("Rohr") else [])
assert befunde == ["Rohrlaser-Angebotskalkulation.exe: eigenes Modul rohrlaser.rechnen als Bytecode (nicht übersetzt)"], befunde
(o / "STEP-Import" / "_internal" / "step_geometrie.cp312-win_amd64.pyd").unlink()
befunde = rp.kompiliert_pruefen(o, lesen=lambda exe: [])
assert len(befunde) == 1 and "keine übersetzten eigenen Module" in befunde[0] and "STEP-Import" in befunde[0], befunde
(o / "STEP-Import" / "STEP-Import.exe").unlink()
assert any("STEP-Import/STEP-Import.exe: fehlt" == b for b in rp.kompiliert_pruefen(o, lesen=lambda exe: []))
ok("Q3 Release-Prüfung --kompiliert: Bytecode eigener Module, fehlende übersetzte Module, fehlende .exe")

# ------------------------------------------------------------------ Workflow
wf = (WURZEL / ".github" / "workflows" / "paket.yml").read_text(encoding="utf-8")
assert wf.index("programm/kompilieren.py") < wf.index("pyinstaller --noconfirm --clean programm/step_messung/step_messung.spec")
assert "cython==3.2.4" in wf and "RL_KOMPILIERT:" in wf
assert "release_pruefen.py pruefen dist/Rohrlaser-Angebotskalkulation --kompiliert" in wf
# Q2: Download im öffentlichen Update-Repository, nur Kundendateien, nicht im Vorabkanal
i = wf.index('Release "download"')
schritt = wf[i:wf.find("\n      - ", i)]
assert "inputs.kanal != 'test'" in schritt and "UPDATES_TOKEN" in schritt and "$env:UPDATE_REPO" in schritt
for datei in ("Rohrlaser-Angebotskalkulation-Setup.exe", "Rohrlaser-Angebotskalkulation.zip", "Lizenzbedingungen.txt"):
    assert datei in schritt, datei
hoch = schritt[schritt.index("foreach"):]
for nie in ("Lizenz-Werkzeug", "Release-Zusammenfassung", "Update.json"):
    assert nie not in hoch, nie
ok("Workflow: übersetzen vor PyInstaller, Prüfung --kompiliert, Download-Release nur mit Kundendateien")

# ------------------------------------------------------------------ Q4 Lizenzbedingungen
text = rohrlaser.lizenzbedingungen()
roh = (PROGRAMM / "rohrlaser" / "Lizenzbedingungen.txt").read_bytes()
assert roh.startswith(b"\xef\xbb\xbf"), "UTF-8 mit BOM, sonst zeigt Inno Setup Umlaute falsch"
for teil in ("Patrick Brundiers", "§ 69e UrhG", "zurückzuentwickeln", "Lizenzprüfung"):
    assert teil in text, teil
assert "©" in rohrlaser.URHEBER
iss = (PROGRAMM / "installer" / "rohrlaser.iss").read_text(encoding="utf-8")
assert "LicenseFile=..\\rohrlaser\\Lizenzbedingungen.txt" in iss
assert '"Lizenzbedingungen.txt"), "rohrlaser")' in (PROGRAMM / "rohrlaser.spec").read_text(encoding="utf-8")
fenster = (PROGRAMM / "rohrlaser" / "fenster.py").read_text(encoding="utf-8")
assert 'QAction("Lizenzbedingungen …"' in fenster and "{URHEBER}" in fenster
ok("Q4 Lizenzbedingungen: Setup, Programmpaket, Hilfe-Menü, Urheberrechtsvermerk unter Über")

print("Alle Tests Quellcode-Schutz bestanden")
