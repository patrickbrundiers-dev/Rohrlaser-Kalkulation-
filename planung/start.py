"""Startdatei für PyInstaller (Rohrlaser-Maschinenplanung.exe): ruft planung.__main__.main auf."""
import sys

from planung.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
