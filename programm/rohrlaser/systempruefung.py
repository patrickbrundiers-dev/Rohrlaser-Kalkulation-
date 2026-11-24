"""Systemvoraussetzungen und Systemprüfung (Performance-Update P10, Patrick 25.10.2026: „können auch ins Programm“,
Freigabe 7a 8a).

VORAUSSETZUNGEN: je Bereich Mindestwert und Empfehlung (abgeleitet aus dem Belastungstest Rundrohr 84 × 2 mit
200/1.000/7.000 Bohrungen). pruefen() misst den Rechner (Windows, Kerne, Arbeitsspeicher, OpenGL, freier Speicher
am Datenort, Bildschirm) und bewertet je Bereich: OK (Empfehlung erfüllt), GENUG (Minimum erfüllt), ZU_WENIG
(unter Minimum) oder UNBEKANNT. Hilfe → Systemprüfung … zeigt die Tabelle; beim ersten Start nach Installation oder
Update warnt das Programm einmal, wenn etwas unter dem Minimum liegt (7a), danach nur noch in der Systemprüfung.
text() ist derselbe Text für Anleitung, Release- und Download-Text.
"""
import os
import platform
import shutil
import sys

OK, GENUG, ZU_WENIG, UNBEKANNT = "ok", "genug", "zu_wenig", "unbekannt"
ZEICHEN = {OK: "✓", GENUG: "✓ (Minimum)", ZU_WENIG: "✗ unter Minimum", UNBEKANNT: "?"}

# Bereich, mindestens, empfohlen (Text); Grenzen zum Prüfen stehen in pruefen()
VORAUSSETZUNGEN = (
    ("Windows", "10 (22H2) oder 11, 64 Bit", "11, 64 Bit"),
    ("Prozessor", "4 Kerne, 2 GHz", "6–8 Kerne, 3 GHz (Optimieren und STEP-Messung nutzen bis zu 4 Hilfsprozesse)"),
    ("Arbeitsspeicher", "8 GB", "16 GB (große STEP-Dateien: etwa 1,2 GB je 1.000 Bohrungen)"),
    ("Grafik", "beliebig (3D ohne OpenGL langsamer)", "OpenGL 2.0 oder höher (3D flüssig auch bei großen Baugruppen)"),
    ("Speicherplatz", "1 GB frei (Programm etwa 400 MB, Daten, Sicherungen)", "5 GB frei (Angebotsordner mit STEP-Kopien)"),
    ("Bildschirm", "1366 × 768", "1920 × 1080 oder größer"),
)
MIN_KERNE, EMPF_KERNE = 4, 6
MIN_GHZ, EMPF_GHZ = 1.9, 2.9         # Nenntakt (Registry rundet, z. B. 1.996 MHz)
MIN_GB, EMPF_GB = 8, 16
MIN_FREI_GB, EMPF_FREI_GB = 1, 5
MIN_BILD, EMPF_BILD = (1366, 768), (1920, 1080)
MIN_WINDOWS_BUILD = 19045          # Windows 10 22H2
WIN11_BUILD = 22000
RAM_TOLERANZ = 0.9                 # „8 GB“-Rechner melden etwas weniger (Grafik reserviert)
EINSTELLUNG = "systempruefung_version"      # Version, bei der zuletzt beim Start geprüft wurde (7a)


def text():
    """Systemvoraussetzungen als Klartext (Release, Download)."""
    return "Systemvoraussetzungen (mindestens / empfohlen):\n" + "\n".join(
        f"- {b}: {m} / {e}" for b, m, e in VORAUSSETZUNGEN)


def _arbeitsspeicher_gb():
    try:
        if sys.platform == "win32":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            s = Status()
            s.dwLength = ctypes.sizeof(Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
                return s.ullTotalPhys / 1024 ** 3
            return None
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except (AttributeError, OSError, ValueError):
        return None


def _takt_ghz():
    """Nenntakt des Prozessors [GHz] aus der Windows-Registry, sonst None."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return winreg.QueryValueEx(k, "~MHz")[0] / 1000
    except (ImportError, OSError, TypeError):
        return None


def _windows():
    """(Text, Bewertung)."""
    if sys.platform != "win32":
        return f"{platform.system()} {platform.release()} (nicht Windows)", UNBEKANNT
    try:
        v = sys.getwindowsversion()
        build = v.build
    except AttributeError:
        return platform.platform(), UNBEKANNT
    bit64 = sys.maxsize > 2 ** 32 or platform.machine().endswith("64")
    name = "11" if build >= WIN11_BUILD else str(v.major)
    t = f"Windows {name} (Build {build}), {'64' if bit64 else '32'} Bit"
    if not bit64 or v.major < 10 or build < MIN_WINDOWS_BUILD:
        return t, ZU_WENIG
    return t, OK if build >= WIN11_BUILD else GENUG


def _stufe(wert, mindestens, empfohlen):
    if wert is None:
        return UNBEKANNT
    return OK if wert >= empfohlen else GENUG if wert >= mindestens else ZU_WENIG


def _zahl(w, n=1):
    return f"{w:.{n}f}".replace(".", ",")


def pruefen(datenordner=None, gl=None, bildschirm=None):
    """Liste (Bereich, gemessen, mindestens, empfohlen, Bewertung). gl: (ok, Text) wie ansicht3d_gl.gl_moeglich
    (None = selbst prüfen); bildschirm: (Breite, Höhe) in Bildpunkten (None = Hauptbildschirm über Qt)."""
    zeilen = []
    texte = {b: (m, e) for b, m, e in VORAUSSETZUNGEN}

    def dazu(bereich, gemessen, bewertung):
        zeilen.append((bereich, gemessen) + texte[bereich] + (bewertung,))

    dazu("Windows", *_windows())
    kerne, ghz = os.cpu_count(), _takt_ghz()
    stufe = _stufe(kerne, MIN_KERNE, EMPF_KERNE)
    if ghz is not None and stufe != UNBEKANNT:      # Takt mitbewerten, wenn Windows ihn nennt
        stufe = min(stufe, _stufe(ghz, MIN_GHZ, EMPF_GHZ), key=(ZU_WENIG, GENUG, OK).index)
    dazu("Prozessor", (f"{kerne} logische Kerne" if kerne else "Kerne unbekannt") +
         (f", {_zahl(ghz)} GHz" if ghz is not None else ", Takt nicht ermittelt"), stufe)
    gb = _arbeitsspeicher_gb()
    dazu("Arbeitsspeicher", f"{_zahl(gb)} GB" if gb else "unbekannt",
         _stufe(gb, MIN_GB * RAM_TOLERANZ, EMPF_GB * RAM_TOLERANZ) if gb else UNBEKANNT)
    if gl is None:
        try:
            from .ansicht3d_gl import gl_moeglich
            gl = gl_moeglich()
        except Exception as ex:         # ohne Qt-Anwendung oder OpenGL-Bibliothek
            gl = (False, f"nicht prüfbar ({type(ex).__name__})")
    dazu("Grafik", gl[1] if gl[0] else f"ohne OpenGL: {gl[1]}", OK if gl[0] else GENUG)
    frei = None
    if datenordner:
        try:
            frei = shutil.disk_usage(datenordner).free / 1024 ** 3
        except OSError:
            pass
    dazu("Speicherplatz", f"{_zahl(frei)} GB frei" if frei is not None else "unbekannt",
         _stufe(frei, MIN_FREI_GB, EMPF_FREI_GB))
    if bildschirm is None:
        try:
            from PySide6.QtGui import QGuiApplication
            sc = QGuiApplication.primaryScreen()
            if sc is not None:
                g, f = sc.geometry(), sc.devicePixelRatio()
                bildschirm = (round(g.width() * f), round(g.height() * f))
        except Exception:
            bildschirm = None
    if bildschirm:
        b, h = bildschirm
        bew = OK if b >= EMPF_BILD[0] and h >= EMPF_BILD[1] else GENUG if b >= MIN_BILD[0] and h >= MIN_BILD[1] \
            else ZU_WENIG
        dazu("Bildschirm", f"{b} × {h}", bew)
    else:
        dazu("Bildschirm", "unbekannt", UNBEKANNT)
    return zeilen


def unter_minimum(zeilen):
    return [z for z in zeilen if z[4] == ZU_WENIG]


def start_pruefung_noetig(db, version):
    """7a: True, wenn seit Installation bzw. Update (andere Version) noch nicht geprüft wurde."""
    try:
        return db.einstellung(EINSTELLUNG) != version
    except Exception:
        return False


def start_gepruft(db, version):
    try:
        if not getattr(db, "nur_lesen", False):
            db.einstellung_setzen(EINSTELLUNG, version)
    except Exception:           # Lesemodus o. ä.: beim nächsten Start noch einmal
        pass


def html(zeilen):
    """Tabelle für den Dialog Systemprüfung."""
    farbe = {OK: "#1E6B34", GENUG: "#1E6B34", ZU_WENIG: "#B42318", UNBEKANNT: "#7A5A00"}
    kopf = "".join(f"<th align='left'>{t}</th>" for t in ("Bereich", "Dieser Rechner", "Mindestens", "Empfohlen", ""))
    reihen = "".join(
        f"<tr><td><b>{b}</b></td><td>{g}</td><td>{m}</td><td>{e}</td>"
        f"<td style='color:{farbe[s]}'><b>{ZEICHEN[s]}</b></td></tr>" for b, g, m, e, s in zeilen)
    return f"<table cellspacing='0' cellpadding='4' border='0'><tr>{kopf}</tr>{reihen}</table>"
