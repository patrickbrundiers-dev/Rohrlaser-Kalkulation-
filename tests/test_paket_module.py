"""Prüft, dass das Windows-Paket alle Module enthält, die das Programm importiert (0.9.231: STEP-Import brach mit
„No module named numpy“ ab, Etiketten-PDF mit „No module named reportlab.graphics.barcode.code128“):

- P1 Fremdpakete: jeder Import in programm/rohrlaser (auch in Funktionen) ist Standardbibliothek, eigenes Modul oder
  ein Paket aus programm/requirements.txt (Pillow kommt mit reportlab); keines steht in excludes der .spec
- P2 reportlab-Barcodes: alle Untermodule als hiddenimports (reportlab lädt sie über Namen nach)

Aufruf: python tests/test_paket_module.py
"""
import ast
import re
import sys
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
ERLAUBT = {"PySide6", "reportlab", "cryptography", "pypdfium2", "pypdfium2_raw", "olefile", "PIL"}

spec = (PROGRAMM / "rohrlaser.spec").read_text(encoding="utf-8")
excludes = set(re.findall(r'"([\w.]+)"', spec[spec.index("excludes=["):spec.index("]", spec.index("excludes=["))]))
fremd = {}
for f in sorted((PROGRAMM / "rohrlaser").rglob("*.py")):
    for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
        namen = [a.name for a in n.names] if isinstance(n, ast.Import) else \
            [n.module] if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module else []
        for m in namen:
            if m.split(".")[0] not in sys.stdlib_module_names and m.split(".")[0] != "rohrlaser":
                fremd.setdefault(m, f.name)
falsch = {m: d for m, d in fremd.items() if m.split(".")[0] not in ERLAUBT}
assert not falsch, f"Import fehlt im Windows-Paket (requirements/spec): {falsch}"
ausgeschlossen = {m: d for m, d in fremd.items() if any(m == e or m.startswith(e + ".") for e in excludes)}
assert not ausgeschlossen, f"Import steht in excludes der rohrlaser.spec: {ausgeschlossen}"
req = (PROGRAMM / "requirements.txt").read_text(encoding="utf-8").lower()
for p in ERLAUBT - {"PIL", "pypdfium2_raw"}:
    assert p.lower() in req, p
print(f"OK: P1 {len(fremd)} Fremd-Importe, alle im Paket")

assert 'collect_submodules("reportlab.graphics.barcode")' in spec and "hiddenimports=BARCODE" in spec
print("OK: P2 reportlab-Barcodes als hiddenimports")
print("Alle Paket-Modul-Tests bestanden.")
