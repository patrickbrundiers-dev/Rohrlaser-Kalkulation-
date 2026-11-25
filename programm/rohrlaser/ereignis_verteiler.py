"""Ein gemeinsamer Ereignisfilter der Anwendung statt vieler (Generalüberholung 24.11.2026, Befund B9).

Bis 0.9.472 hatten Stil (Umfärben beim Polieren), Mausrad, Enter-Regel, Zeitwächter, Fensterlage, Admin-Eingabe-
wächter und Fenstermerker je einen eigenen Filter an der QApplication. Qt ruft jeden davon für JEDES Ereignis der
Anwendung auf (beim Aufbau des Hauptfensters über 100.000), jedes Mal ein Sprung von C++ nach Python. Jetzt gibt es
einen Filter; er schaut einmal auf die Art des Ereignisses und gibt es nur an die Filter weiter, die diese Art
brauchen.

Verhalten wie vorher: Reihenfolge wie bei Qt (der zuletzt angemeldete Filter zuerst), ein Filter, der True liefert,
verschluckt das Ereignis für alle danach. Ein gelöschter Filter (z. B. mit seinem Hauptfenster) meldet sich selbst ab.

    ereignis_verteiler.anmelden(filter_objekt, (QEvent.Show, QEvent.Hide))   # Arten, die der Filter braucht
    ereignis_verteiler.abmelden(filter_objekt)
"""
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication


class _Verteiler(QObject):
    def __init__(self, app):
        super().__init__(app)
        self._eintraege = []        # [(Filter, Arten)], zuletzt angemeldet zuerst
        self._je_art = {}           # Ereignisart -> (Filter, …) in Aufrufreihenfolge

    def _neu_ordnen(self):
        je_art = {}
        for f, arten in self._eintraege:
            for a in arten:
                je_art.setdefault(a, []).append(f)
        self._je_art = {a: tuple(fs) for a, fs in je_art.items()}

    def eventFilter(self, obj, ereignis):       # noqa: N802 – Qt-Name
        filter_ = self._je_art.get(ereignis.type())
        if filter_ is None:
            return False
        for f in filter_:
            try:
                if f.eventFilter(obj, ereignis):
                    return True
            except RuntimeError:        # Filter gerade gelöscht (Qt-Objekt weg), Abmelden folgt
                continue
        return False


def _verteiler(app=None):
    app = app or QApplication.instance()
    v = getattr(app, "_ereignis_verteiler", None)
    if v is None:
        v = app._ereignis_verteiler = _Verteiler(app)
        app.installEventFilter(v)
    return v


def anmelden(filter_objekt, arten, app=None):
    """filter_objekt (QObject mit eventFilter) für diese Ereignisarten an der Anwendung anmelden."""
    v = _verteiler(app)
    abmelden(filter_objekt, app)
    v._eintraege.insert(0, (filter_objekt, tuple(arten)))
    v._neu_ordnen()
    try:
        filter_objekt.destroyed.connect(lambda *_a, v=v, i=id(filter_objekt): _weg(v, i))
    except (AttributeError, RuntimeError):
        pass
    return filter_objekt


def _weg(v, ident):
    try:
        v._eintraege = [(f, a) for f, a in v._eintraege if id(f) != ident]
        v._neu_ordnen()
    except RuntimeError:            # Verteiler schon mit der Anwendung gelöscht
        pass


def abmelden(filter_objekt, app=None):
    v = _verteiler(app)
    vorher = len(v._eintraege)
    v._eintraege = [(f, a) for f, a in v._eintraege if f is not filter_objekt]
    if len(v._eintraege) != vorher:
        v._neu_ordnen()


def angemeldet(app=None):
    """Angemeldete Filter in Aufrufreihenfolge (für Tests)."""
    return [f for f, _ in _verteiler(app)._eintraege]
