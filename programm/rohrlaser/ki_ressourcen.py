"""KI-Plattform Phase 1: Ressourcen messen (CPU, RAM, GPU, VRAM) für die KI-Zentrale und die automatische
Modellwahl. Ohne Zusatzpakete: Windows über kernel32/psapi, Linux über /proc, Grafikkarten über nvidia-smi (wenn
vorhanden, sonst „keine NVIDIA-GPU erkannt“: das Modell läuft dann auf der CPU). Ohne Qt.

messen(mit_gpu=True) -> dict(cpu_kerne, cpu_last_pct, ram_gesamt_gb, ram_frei_gb, ram_last_pct, prozess_mb, gpus
[dict(name, vram_gesamt_gb, vram_frei_gb, last_pct)], gpu_text, zeit)
CPU-Last ist die Last seit dem letzten Aufruf (beim ersten Aufruf: über 0,2 s gemessen)."""
import datetime
import os
import shutil
import subprocess
import sys
import time

_LETZTE = {}            # CPU-Zeiten des letzten Aufrufs


def _win_speicher():
    import ctypes

    class Status(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    s = Status()
    s.dwLength = ctypes.sizeof(Status)
    if not ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(s)):
        return None, None
    return s.ullTotalPhys / 1024 ** 3, s.ullAvailPhys / 1024 ** 3


def _win_cpu_zeiten():
    import ctypes
    leer, kern, benutzer = ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong()
    if not ctypes.WinDLL("kernel32").GetSystemTimes(ctypes.byref(leer), ctypes.byref(kern), ctypes.byref(benutzer)):
        return None
    return leer.value, kern.value + benutzer.value          # Kernzeit enthält die Leerlaufzeit


def _win_prozess_mb():
    import ctypes
    from ctypes import wintypes

    class Zaehler(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    z = Zaehler()
    z.cb = ctypes.sizeof(Zaehler)
    psapi = ctypes.WinDLL("psapi")      # eigene Instanz: andere Module dürfen restype/argtypes nicht stören
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    if psapi.GetProcessMemoryInfo(wintypes.HANDLE(-1), ctypes.byref(z), z.cb):     # -1 = dieser Prozess
        return z.WorkingSetSize / 1024 ** 2
    return None


def _linux_speicher():
    werte = {}
    with open("/proc/meminfo", encoding="ascii") as f:
        for z in f:
            n, _, w = z.partition(":")
            werte[n] = float(w.split()[0]) / 1024 ** 2          # kB -> GB
    return werte.get("MemTotal"), werte.get("MemAvailable", werte.get("MemFree"))


def _linux_cpu_zeiten():
    with open("/proc/stat", encoding="ascii") as f:
        teile = [float(x) for x in f.readline().split()[1:]]
    leer = teile[3] + (teile[4] if len(teile) > 4 else 0)
    return leer, sum(teile)


def _linux_prozess_mb():
    with open("/proc/self/status", encoding="ascii") as f:
        for z in f:
            if z.startswith("VmRSS:"):
                return float(z.split()[1]) / 1024
    return None


def _cpu_zeiten():
    try:
        return _win_cpu_zeiten() if sys.platform == "win32" else _linux_cpu_zeiten()
    except Exception:       # noqa: BLE001 – siehe messen()
        _warnung("CPU-Zeiten")
        return None


def _warnung(was):
    try:
        from . import protokoll
        protokoll.warnung(f"ki_ressourcen: {was} nicht messbar")
    except Exception:       # noqa: BLE001 – Protokoll fehlt (Tests ohne Paket): einfach weiter
        return


def cpu_last():
    """CPU-Last in % seit dem letzten Aufruf (erster Aufruf: 0,2 s messen); None = unbekannt."""
    jetzt = _cpu_zeiten()
    if jetzt is None:
        return None
    alt = _LETZTE.get("cpu")
    if alt is None:
        time.sleep(0.2)
        alt, jetzt = jetzt, _cpu_zeiten() or jetzt
    _LETZTE["cpu"] = jetzt
    leer, gesamt = jetzt[0] - alt[0], jetzt[1] - alt[1]
    return round(max(0.0, min(100.0, 100.0 * (1 - leer / gesamt))), 1) if gesamt > 0 else None


def gpus(ausfuehren=None):
    """NVIDIA-Grafikkarten über nvidia-smi: [dict(name, vram_gesamt_gb, vram_frei_gb, last_pct)]; leer = keine.
    ausfuehren(befehl) -> Text ersetzt den Aufruf (Tests)."""
    befehl = ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu",
              "--format=csv,noheader,nounits"]
    try:
        if ausfuehren:
            text = ausfuehren(befehl)
        else:
            if not shutil.which("nvidia-smi"):
                return []
            extra = dict(creationflags=0x08000000) if sys.platform == "win32" else {}
            r = subprocess.run(befehl, capture_output=True, text=True, timeout=3, **extra)
            if r.returncode != 0:
                return []
            text = r.stdout
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for z in str(text or "").splitlines():
        t = [x.strip() for x in z.split(",")]
        if len(t) < 4:
            continue
        try:
            gesamt, belegt = float(t[1]) / 1024, float(t[2]) / 1024
            out.append(dict(name=t[0], vram_gesamt_gb=round(gesamt, 2), vram_frei_gb=round(gesamt - belegt, 2),
                            last_pct=float(t[3])))
        except ValueError:
            continue
    return out


def messen(mit_gpu=True, ausfuehren=None):
    try:
        gesamt, frei = _win_speicher() if sys.platform == "win32" else _linux_speicher()
    except Exception:       # noqa: BLE001 – Messung darf die KI-Zentrale nie aufhalten (auch ctypes.ArgumentError)
        _warnung("RAM")
        gesamt = frei = None
    try:
        prozess = _win_prozess_mb() if sys.platform == "win32" else _linux_prozess_mb()
    except Exception:       # noqa: BLE001 – siehe oben
        _warnung("Prozessspeicher")
        prozess = None
    g = gpus(ausfuehren) if mit_gpu else []
    return dict(cpu_kerne=os.cpu_count(), cpu_last_pct=cpu_last(),
                ram_gesamt_gb=round(gesamt, 2) if gesamt else None, ram_frei_gb=round(frei, 2) if frei else None,
                ram_last_pct=round(100 * (1 - frei / gesamt), 1) if gesamt and frei is not None else None,
                prozess_mb=round(prozess, 1) if prozess else None, gpus=g,
                gpu_text=", ".join(f"{x['name']} ({x['vram_gesamt_gb']:.0f} GB)" for x in g) if g else
                "keine NVIDIA-GPU erkannt – Modelle laufen auf der CPU",
                zeit=datetime.datetime.now().isoformat(timespec="seconds"))


def empfehlung(r):
    """Welche Modellgröße passt auf diesen PC (Text), aus RAM und VRAM."""
    vram = max((x["vram_gesamt_gb"] for x in r.get("gpus") or []), default=0)
    ram = r.get("ram_gesamt_gb") or 0
    if vram >= 10:
        return "Grafikkarte reicht für 7–14B-Modelle (Q4) mit voller GPU-Beschleunigung."
    if vram >= 6:
        return "Grafikkarte reicht für 7–8B-Modelle (Q4)."
    if ram >= 30:
        return "Ohne passende GPU: 7–8B-Modelle (Q4) auf der CPU, etwa 5–10 Token/s."
    if ram >= 15:
        return "Ohne passende GPU: 3–8B-Modelle (Q4) auf der CPU; 3B für schnelle Antworten."
    return "Wenig Arbeitsspeicher: höchstens 1–3B-Modelle, sonst regelbasiert arbeiten."
