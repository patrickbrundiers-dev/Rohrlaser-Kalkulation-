"""Zugriff auf die gemeinsamen Python-Fassungen in tools/ (Optimierung), die auch die Mappe nutzt.

In der .exe sind sie mit eingebunden (pathex in rohrlaser.spec), beim Entwickeln liegen sie im
Ordner tools/ des Repositorys.
"""
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    _tools = Path(__file__).resolve().parents[2] / "tools"
    if str(_tools) not in sys.path:
        sys.path.insert(0, str(_tools))

import optimierung  # noqa: E402,F401
