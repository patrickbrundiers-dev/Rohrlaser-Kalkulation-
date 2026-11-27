"""Fensterprobe unter echtem Windows (Auftrag Patrick 27.11.2026 „X in jedem Fenster ausgegraut/ohne Funktion“).

Läuft nur unter Windows (eigener Workflow fenster-windows.yml auf einem Windows-Rechner von GitHub). Baut Fenster
so auf wie das Programm (Theme, Wache gegen losgelöste Teile, Fensterplatz, zentrale Fensterverwaltung) und prüft je
Fenster mit der Windows-Schnittstelle (ctypes, user32):
- Stil der Titelleiste (Systemmenü, Minimieren, Maximieren), Fensterklasse ohne Schließen (CS_NOCLOSE),
  Eintrag „Schließen“ im Systemmenü ausgegraut, Fenster gesperrt (IsWindowEnabled), Vordergrundfenster,
- einen echten Mausklick auf das X (Lage über WM_NCHITTEST = HTCLOSE ermittelt): schließt das Fenster?
Szenarien: Dialog ohne Programmrahmen (Vergleich), Dialog mit Programmrahmen, Dialog mit Tabelle (maximiert),
modaler Dialog (exec) und das Hauptfenster dahinter, minimierter modaler Dialog, nach Tooltip und Menü.
Ergebnis als Tabelle (Markdown) auf stdout und in GITHUB_STEP_SUMMARY, Bildschirmfotos in fenster_windows/.

Aufruf (nur Windows): python tests/windows_fenster.py
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

if sys.platform != "win32":
    print("Nur unter Windows.")
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from PySide6.QtCore import QPoint, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QLabel, QMainWindow, QMenu, QPushButton,  # noqa: E402
                               QTableWidget, QToolTip, QVBoxLayout)

u32 = ctypes.WinDLL("user32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
u32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
u32.GetClassLongPtrW.restype = ctypes.c_size_t
u32.GetClassLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
u32.GetSystemMenu.restype = wintypes.HMENU
u32.GetSystemMenu.argtypes = (wintypes.HWND, wintypes.BOOL)
u32.GetMenuState.restype = wintypes.UINT
u32.GetMenuState.argtypes = (wintypes.HMENU, wintypes.UINT, wintypes.UINT)
u32.SendMessageW.restype = LRESULT
u32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
u32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
u32.IsWindowEnabled.argtypes = (wintypes.HWND,)
u32.GetForegroundWindow.restype = wintypes.HWND
u32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
u32.GetWindow.restype = wintypes.HWND
u32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)

GWL_STYLE, GCL_STYLE, GW_OWNER = -16, -26, 4
WS_SYSMENU, WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_DISABLED = 0x80000, 0x20000, 0x10000, 0x8000000
CS_NOCLOSE = 0x200
SC_CLOSE, MF_GRAYED, MF_DISABLED = 0xF060, 0x1, 0x2
WM_NCHITTEST, HTCLOSE = 0x84, 20
INPUT_MOUSE, LEFTDOWN, LEFTUP = 0, 0x2, 0x4


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t))


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = (("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32))
    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _U))


app = QApplication.instance() or QApplication(sys.argv)
ORDNER = Path("fenster_windows")
ORDNER.mkdir(exist_ok=True)
ZEILEN = []
FEHLER = []


def warten(sek=0.4):
    ende = time.time() + sek
    while time.time() < ende:
        app.processEvents()
        time.sleep(0.02)


def x_finden(hwnd):
    """Bildschirmpunkt des X-Knopfs (WM_NCHITTEST = HTCLOSE) oder None."""
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    for dy in range(4, 40, 2):
        for dx in range(4, 120, 2):
            x, y = r.right - dx, r.top + dy
            lp = (y & 0xFFFF) << 16 | (x & 0xFFFF)
            if u32.SendMessageW(hwnd, WM_NCHITTEST, 0, lp) == HTCLOSE:
                return x, y
    return None


def klicken(x, y):
    u32.SetCursorPos(x, y)
    warten(0.15)
    for flag in (LEFTDOWN, LEFTUP):
        i = INPUT(type=INPUT_MOUSE)
        i.mi = MOUSEINPUT(0, 0, 0, flag, 0, 0)
        u32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
        warten(0.08)


def befund(name, w, klick=True, erwartet_zu=True):
    """Windows-Zustand von w aufschreiben, X klicken (optional) und prüfen, ob es zu ist."""
    warten(0.5)
    hwnd = int(w.winId())
    stil = u32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    klasse = u32.GetClassLongPtrW(hwnd, GCL_STYLE)
    menue = u32.GetSystemMenu(hwnd, False)
    zustand = u32.GetMenuState(menue, SC_CLOSE, 0) if menue else 0xFFFFFFFF
    puffer = ctypes.create_unicode_buffer(128)
    u32.GetClassNameW(hwnd, puffer, 128)
    vorne = u32.GetForegroundWindow() == hwnd
    pos = x_finden(hwnd)
    app_modal = QApplication.activeModalWidget()
    foto = ORDNER / f"{len(ZEILEN) + 1:02d}_{name.replace(' ', '_').replace('/', '-')}.png"
    QApplication.primaryScreen().grabWindow(0).save(str(foto))
    zu = None
    if klick and pos:
        klicken(*pos)
        warten(0.6)
        zu = not w.isVisible()
    zeile = dict(name=name, klasse=puffer.value, sysmenu=bool(stil & WS_SYSMENU), min=bool(stil & WS_MINIMIZEBOX),
                 max=bool(stil & WS_MAXIMIZEBOX), gesperrt=bool(stil & WS_DISABLED) or not u32.IsWindowEnabled(hwnd),
                 noclose=bool(klasse & CS_NOCLOSE),
                 x_grau="–" if zustand == 0xFFFFFFFF else bool(zustand & (MF_GRAYED | MF_DISABLED)),
                 vorne=vorne, x_gefunden=pos is not None, modal=type(app_modal).__name__ if app_modal else "–",
                 qt_flags=hex(int(w.windowFlags().value if hasattr(w.windowFlags(), "value") else w.windowFlags())),
                 zu=zu)
    ZEILEN.append(zeile)
    if klick and erwartet_zu is not None and zu != erwartet_zu:
        FEHLER.append(f"{name}: X-Klick {'schloss nicht' if erwartet_zu else 'schloss trotzdem'}")
    print(zeile, flush=True)
    return zeile


class FakeDB:
    def __init__(self):
        self.d = {}

    def einstellung(self, k, vorgabe=None):
        return self.d.get(k, vorgabe)

    def einstellung_setzen(self, k, v):
        self.d[k] = v


def programmrahmen(haupt):
    """Wie fenster.Hauptfenster: Theme mit Wache und Tooltips, Fensterplatz, zentrale Fensterverwaltung."""
    from rohrlaser import ereignis_verteiler, fenster_platz, stil
    from rohrlaser.fenster_merken import ARTEN, FensterMerker
    stil.anwenden(app, "Hell")
    haupt.fenster_platz = fenster_platz.einrichten(haupt)
    haupt.fenster_merker = FensterMerker(FakeDB(), haupt, benutzer="T")
    ereignis_verteiler.anmelden(haupt.fenster_merker, ARTEN)


def dialog(haupt, titel, tabelle=False):
    d = QDialog(haupt)
    d.setWindowTitle(titel)
    lay = QVBoxLayout(d)
    lay.addWidget(QLabel("Probe"))
    if tabelle:
        lay.addWidget(QTableWidget(30, 6))
        d.resize(900, 650)
    b = QPushButton("OK")
    b.clicked.connect(d.accept)
    lay.addWidget(b)
    return d


class Hauptfenster(QMainWindow):        # Klassenname wie im Programm (fenster_merken lässt es aus)
    pass


def lauf():
    # 1 Vergleich: Dialog ohne Programmrahmen
    roh = QMainWindow()
    roh.setWindowTitle("Roh")
    roh.resize(900, 600)
    roh.show()
    d = dialog(roh, "Dialog ohne Rahmen")
    d.show()
    befund("Dialog ohne Programmrahmen", d)
    roh.close()
    warten()

    haupt = Hauptfenster()
    haupt.setWindowTitle("Rohrlaser-Probe")
    haupt.resize(1000, 700)
    programmrahmen(haupt)
    haupt.show()
    warten()
    menue = QMenu(haupt)
    for t in ("Eins", "Zwei"):
        menue.addAction(t)
    haupt.menuBar().addMenu(menue).setText("Datei")

    # 2 Dialog mit Programmrahmen (nicht modal)
    d = dialog(haupt, "Dialog mit Rahmen")
    d.show()
    befund("Dialog mit Programmrahmen", d)
    # 3 Dialog mit Tabelle (öffnet maximiert)
    d = dialog(haupt, "Liste", tabelle=True)
    d.show()
    befund("Dialog mit Tabelle (maximiert)", d)
    # 4 nach Tooltip und Menü
    d = dialog(haupt, "Nach Tooltip")
    d.show()
    warten()
    QToolTip.showText(d.mapToGlobal(QPoint(20, 20)), "Hilfe\nzweite Zeile", d)
    warten(0.6)
    QToolTip.hideText()
    menue.popup(haupt.mapToGlobal(QPoint(40, 40)))
    warten(0.4)
    menue.close()
    befund("Dialog nach Tooltip und Menü", d)
    # 5 modaler Dialog (exec): X am modalen, am Hauptfenster dahinter
    ergebnis = {}

    def im_modal():
        m = QApplication.activeModalWidget()
        befund("Hauptfenster hinter modalem Dialog", haupt, erwartet_zu=False)
        befund("Modaler Dialog (exec)", m)
        ergebnis["fertig"] = True
    m = dialog(haupt, "Modal")
    QTimer.singleShot(700, im_modal)
    m.exec()
    # 6 modaler Dialog minimiert: Hauptfenster dahinter
    m = dialog(haupt, "Modal minimiert")

    def minimiert():
        mm = QApplication.activeModalWidget()
        mm.showMinimized()
        warten(0.6)
        befund("Hauptfenster bei minimiertem modalem Dialog", haupt, erwartet_zu=None)
        ZEILEN[-1]["name"] += f" (Dialog noch sichtbar: {mm.isVisible()}, minimiert: {mm.isMinimized()})"
        mm.showNormal()
        warten(0.4)
        mm.reject()
    QTimer.singleShot(700, minimiert)
    m.exec()
    # 7 Hauptfenster selbst
    if haupt.isVisible():
        befund("Hauptfenster", haupt)


lauf()
kopf = list(ZEILEN[0].keys()) if ZEILEN else []
md = ["| " + " | ".join(kopf) + " |", "|" + "---|" * len(kopf)]
md += ["| " + " | ".join(str(z[k]) for k in kopf) + " |" for z in ZEILEN]
text = "\n".join(["## Fensterprobe Windows", ""] + md + [""] + [f"- FEHLER {f}" for f in FEHLER])
print(text)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
        f.write(text + "\n")
sys.exit(1 if FEHLER else 0)
