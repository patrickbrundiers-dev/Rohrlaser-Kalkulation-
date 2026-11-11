"""Startdatei für PyInstaller (Rohrlaser-Auslastung.exe)."""
import os
import sys

if sys.stdout is None:   # Fensterprogramm ohne Konsole: Ausgaben verwerfen statt abzustürzen
    sys.stdout = sys.stderr = open(os.devnull, "w")

from rl_auslastung.__main__ import main  # noqa: E402

sys.exit(main())
