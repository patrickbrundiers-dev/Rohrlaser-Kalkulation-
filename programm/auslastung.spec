# PyInstaller-Spezifikation für Rohrlaser-Auslastung.exe (eigenes Programm zur Maschinenauslastung, läuft ohne die
# Kalkulation; Ordner-Variante). Aufruf (Windows): pyinstaller --noconfirm --clean programm/auslastung.spec
# Ergebnis: dist/Rohrlaser-Auslastung/Rohrlaser-Auslastung.exe; die Datenbank legt das Programm beim ersten Start im
# Ordner 'Daten' daneben an (anderer Ort: Auslastung.ini, siehe rl_auslastung/ort.py).
# Aus dem Paket rohrlaser kommen nur einlastung, wochen, feiertage, stil (mit design) und auslastung_grafik mit, für das
# Online-Update zusätzlich update, update_netz und update_schluessel (dazu das Paket cryptography für die Signaturprüfung), für den
# Datenspeicher je PC db_verbindung, datenspeicher, pg_lokal und db_kopie (dazu psycopg; die PostgreSQL-Programme legt
# der Workflow als Ordner pgsql neben die .exe).
import os
import re
import sys

sys.path.insert(0, SPECPATH)
import versionsinfo as vi  # noqa: E402

VERSION = re.search(r'VERSION = "([^"]+)"', open(os.path.join(SPECPATH, "rl_auslastung", "__init__.py"),
                                                 encoding="utf-8").read()).group(1)
vi.version = lambda: VERSION            # eigene Versionsnummer, nicht die der Kalkulation
vi.PRODUKT = "NexTube Auslastung"

a = Analysis([os.path.join(SPECPATH, "start_auslastung.py")], pathex=[SPECPATH], binaries=[], datas=[(os.path.join(SPECPATH, "rohrlaser", "bilder"), "rohrlaser/bilder")],
             # rohrlaser.auslastung / etiketten / qt_slots: nur in Funktionen der Kalkulation nachgeladen, hier nie;
             # rohrlaser.datenbank: nur in datenspeicher.umstellen/zurueck der Kalkulation nachgeladen, hier nie;
             # rechnen, teilen, server_*, verbindung_waechter, pruef_wiederherstellung, dokumente_sicherung, pg_abbild:
             # nur in Funktionen von datenspeicher, die allein die Kalkulation aufruft (kalkulationen, bereitstellen
             # im Serverbetrieb, status, status_werte, letzte_sicherung), hier nie
             hiddenimports=["rohrlaser.update_schluessel", "rohrlaser.lizenz_schluessel", "rohrlaser.pg_lokal",
                            "rohrlaser.db_kopie", "psycopg", "psycopg_binary"], excludes=["rohrlaser.auslastung", "rohrlaser.datenbank", "rohrlaser.rechnen", "rohrlaser.teilen", "rohrlaser.server_betrieb", "rohrlaser.server_rechnen", "rohrlaser.server_sicherung", "rohrlaser.verbindung_waechter", "rohrlaser.pruef_wiederherstellung", "rohrlaser.dokumente_sicherung", "rohrlaser.pg_abbild", "rohrlaser.etiketten", "rohrlaser.qt_slots", "tkinter", "matplotlib", "numpy", "reportlab", "pypdfium2",
                                         "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick",
                                         "PySide6.Qt3DCore", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets"],
             noarchive=False)
fremd = [n for n, *_ in a.pure if n.startswith("rohrlaser.") and n not in (
    "rohrlaser.einlastung", "rohrlaser.wochen", "rohrlaser.feiertage", "rohrlaser.stil", "rohrlaser.auslastung_grafik",
    "rohrlaser.design",                                             # Farbwerte für stil (nur Konstanten, U7)
    "rohrlaser.update", "rohrlaser.update_schluessel",              # diese zwei: Online-Update
    "rohrlaser.update_netz",                                        # Proxy und Firmen-Zertifikat für das Update
    "rohrlaser.mausrad",                                            # das Mausrad ändert keine Werte
    "rohrlaser.lizenz", "rohrlaser.lizenz_schluessel", "rohrlaser.lizenz_dialog",   # Plan 2.4: Lizenz
    "rohrlaser.aktivierung", "rohrlaser.module", "rohrlaser.marke",  # Lizenz 2.0, Module, Marke NexTube
    "rohrlaser.passwort", "rohrlaser.klartext",
    "rohrlaser.hauptadmin", "rohrlaser.anmelde_fenster",        # Hauptadmin-Anmeldung beim Start
    "rohrlaser.db_verbindung", "rohrlaser.datenspeicher",           # Datenspeicher je PC: SQLite oder PostgreSQL
    "rohrlaser.pg_lokal", "rohrlaser.db_kopie",
    "rohrlaser.zugangsschutz",                                      # pg_lokal: Zugang zur lokalen PostgreSQL
    "rohrlaser.protokoll",                                          # datenspeicher.server: Selbstheilung ins Protokoll
    "rohrlaser.ereignis_verteiler", "rohrlaser.leerhinweis",        # stil/mausrad: ein Ereignisfilter, Leerhinweise
    "rohrlaser.geister")]                                           # stil: losgelöste Knöpfe, Tooltip-Reste (27.11.)
if fremd:
    raise SystemExit("auslastung.spec: das Programm zieht Module der Kalkulation mit: " + ", ".join(fremd))
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Rohrlaser-Auslastung", console=False, upx=False,
          icon=os.path.join(SPECPATH, "rohrlaser", "bilder", "nextube.ico"),     # Marke NexTube (marke.py)
          version=vi.versionsinfo("Rohrlaser-Auslastung", "NexTube Auslastung", workpath))
coll = COLLECT(exe, a.binaries, a.datas, name="Rohrlaser-Auslastung", upx=False)
