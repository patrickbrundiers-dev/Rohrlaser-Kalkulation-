"""Startdatei für PyInstaller (STEP-Import.exe): Die Messung selbst steckt übersetzt in step_messen (kompilieren.py),
hier steht nur der Aufruf, damit kein eigener Code als Bytecode im Startskript der .exe liegt."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()     # STEP-Import.exe: Unterprozesse der Messung
    import step_messen
    sys.exit(step_messen.main())
