"""Startdatei für PyInstaller (Rohrlaser-Kalkulation.exe)."""
import os
import sys

if sys.stdout is None:   # Fensterprogramm ohne Konsole: Ausgaben verwerfen statt abzustürzen
    sys.stdout = sys.stderr = open(os.devnull, "w")

from rohrlaser.__main__ import main  # noqa: E402

sys.exit(main())
