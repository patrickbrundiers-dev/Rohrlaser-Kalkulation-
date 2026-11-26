"""Startdatei für PyInstaller (Rohrlaser-Angebotskalkulation.exe)."""
import os
import sys

if len(sys.argv) == 4 and sys.argv[1] == "--optimierer":     # Hilfsprozess für Schnittpläne (rohrlaser.parallel)
    from rohrlaser.parallel import dienst
    sys.exit(dienst(sys.argv[2], sys.argv[3]))

if len(sys.argv) > 1 and sys.argv[1] == "--server":       # Serverversion: Befehle auf dem Server-Rechner
    from rohrlaser.server_betrieb import konsole_main
    sys.exit(konsole_main(sys.argv[2:]))

if sys.stdout is None:   # Fensterprogramm ohne Konsole: Ausgaben verwerfen statt abzustürzen
    sys.stdout = sys.stderr = open(os.devnull, "w")

from rohrlaser.__main__ import main  # noqa: E402

sys.exit(main())
