"""PySide6-Signale und übersetzter Programmcode (Plan „Quellcode schützen“ Q3, programm/kompilieren.py).

PySide gibt einem Slot nur dann die Werte des Signals mit, wenn er eine echte Python-Funktion ist: Es liest dafür die
Parameterliste. Eine von Cython übersetzte Funktion (Typ cython_function_or_method) ruft es ohne Werte auf, aus
clicked(bool) an lambda offen: … wird „takes exactly 1 positional argument (0 given)“. Gebundene Methoden erkennt
PySide richtig.

einschalten() ersetzt deshalb SignalInstance.connect: eine übersetzte Funktion wird in eine echte Python-Funktion mit
derselben Parameterliste gehüllt (Pflichtparameter, Parameter mit Vorgabe, *args). PySide gibt dann genauso viele
Werte mit wie bei der Python-Fassung. Im Quelltext-Betrieb (Entwicklung, Tests) ändert sich nichts.
"""
_FEHLT = object()
_FABRIKEN = {}
UEBERSETZT = ("cython_function_or_method", "fused_cython_function")


def _fabrik(pflicht, optional, rest):
    """Funktion, die zu einem Ziel eine Python-Hülle mit pflicht + optional Parametern (und *rest) baut."""
    schluessel = (pflicht, optional, rest)
    if schluessel not in _FABRIKEN:
        p = [f"p{i}" for i in range(pflicht)]
        o = [f"o{i}" for i in range(optional)]
        parameter = p + [f"{n}=_FEHLT" for n in o] + (["*rest"] if rest else [])
        werte = p + ([f"*[w for w in ({', '.join(o)},) if w is not _FEHLT]"] if o else []) + (["*rest"] if rest else [])
        quelle = (f"def machen(ziel):\n"
                  f"    def huelle({', '.join(parameter)}):\n"
                  f"        return ziel({', '.join(werte)})\n"
                  f"    return huelle\n")
        raum = {"_FEHLT": _FEHLT}
        exec(quelle, raum)      # nur feste, hier erzeugte Namen; macht eine echte Python-Funktion
        _FABRIKEN[schluessel] = raum["machen"]
    return _FABRIKEN[schluessel]


def huelle(slot):
    """Python-Hülle für eine übersetzte Funktion, alles andere unverändert."""
    if type(slot).__name__ not in UEBERSETZT:
        return slot
    code = slot.__code__
    optional = len(getattr(slot, "__defaults__", None) or ())
    h = _fabrik(code.co_argcount - optional, optional, bool(code.co_flags & 0x04))(slot)
    h.__name__ = getattr(slot, "__name__", "slot")
    h.__qualname__ = getattr(slot, "__qualname__", h.__name__)
    return h


def einschalten():
    """SignalInstance.connect einmal ersetzen (beim Programmstart, nur wenn der Code übersetzt ist)."""
    from PySide6.QtCore import SignalInstance
    if getattr(SignalInstance.connect, "rohrlaser_huelle", False):
        return
    original = SignalInstance.connect

    def connect(self, slot, *args, **kwargs):
        return original(self, huelle(slot), *args, **kwargs)
    connect.rohrlaser_huelle = True
    SignalInstance.connect = connect
