"""Geschlossene Dialoge wirklich freigeben (Auftrag Patrick 27.11.2026 „Fensterstabilität“, Punkt Speicherlecks).

Befund (Rundgang aller Menüfenster, tests/test_fenster_stabilitaet.py): Fast jeder Dialog wird mit dem Hauptfenster
als Elternfenster gebaut und mit exec() gezeigt. Nach dem Schließen ist er nur verborgen; Qt löscht ihn erst mit dem
Elternfenster, also beim Beenden. Jedes Öffnen ließ so alle Bedienelemente des Dialogs zurück (Prüfregeln 223,
KI-Zentrale 335, Produktionsdaten 282 Elemente je Öffnen). Über einen Arbeitstag sammeln sich Zehntausende verborgene
Elemente an: mehr Speicher, langsamere Fenstersuche und Ereignisfilter, verborgene Fenster unter Windows.

Lösung ohne Eingriff in jeden Dialog: exec() merkt sich den Dialog nach dem Schließen. Sobald das Programm wieder in
der Hauptschleife steht (kein anderer Dialog offen, der Aufrufer ist fertig) und kein Programmteil den Dialog mehr
hält, wird er mit deleteLater() gelöscht. „Hält“ heißt: ein Attribut eines anderen Objekts, eine Liste, ein Wörterbuch
oder eine Variable außerhalb des Dialogs verweist auf ihn (z. B. self.suche = SucheDialog(self) zum Wiederverwenden).
Solche Dialoge bleiben unberührt. Ebenso Dialoge, die wieder sichtbar sind, und Dialoge mit WA_DeleteOnClose.
"""
import gc
import sys
import types

from PySide6.QtCore import QObject, Qt, QThread, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

WARTEN_MS = 1500                    # nach dem Schließen so lange warten (Aufrufer liest noch Werte) [ms]
VERSUCHE = 3                        # so oft prüfen, ob ein gehaltener Dialog frei geworden ist
_versuche = {}                      # id(Dialog) -> Anzahl Prüfungen, bei denen er gehalten war
_kandidaten = []                    # geschlossene Dialoge (Python-Objekte), die vielleicht gelöscht werden können
_zeit = None                        # QTimer für den nächsten Durchgang
statistik = dict(geloescht=0, gehalten=0, durchgaenge=0)
gruende = []                        # Diagnose: (Dialog, Art des Verweises) gehaltener Dialoge
_alt_exec = None
_alt_mb_exec = None


def _gueltig(o):
    """Qt-Objekt noch nicht gelöscht (wie shiboken6.isValid, ohne eigenes Paket im Windows-Bau, vgl. freigeben)."""
    try:
        o.objectName()
        return True
    except RuntimeError:            # „Internal C++ object … already deleted“
        return False


def _vorfahr(o, d):
    """Ist o der Dialog d selbst oder steckt es in d (QObject-Kind, auch tiefer)?"""
    try:
        while o is not None:
            if o is d:
                return True
            o = o.parent()
    except RuntimeError:
        return False
    return False


GRUND = []                          # Diagnose: warum zuletzt ein Dialog gehalten wurde
_eigene_listen = []                 # Ergebnislisten von gc.get_referrers (zählen nicht als Verweis)


def _verweise(o):
    """gc.get_referrers(o) ohne Frames, ohne die Vormerkliste und ohne eigene Ergebnislisten."""
    liste = gc.get_referrers(o)
    _eigene_listen.append(liste)
    eigene = {id(e) for e in _eigene_listen}
    eigene.add(id(_eigene_listen))
    ergebnis = []
    for x in liste:
        if not isinstance(x, (types.FrameType, types.GeneratorType)) and x is not _kandidaten and id(x) not in eigene:
            ergebnis.append(x)
    _eigene_listen.append(ergebnis)
    return ergebnis


def _intern(r, d, tiefe=0, besucht=None):
    """Hängt das Objekt r nur am Dialog d (an d selbst, einem Kind von d oder einer Signalverbindung in d)?"""
    if besucht is None:
        besucht = set()
    if id(r) in besucht:
        return True                 # Kreis (Funktionen, die sich gegenseitig kennen): schon geprüft
    besucht.add(id(r))
    if isinstance(r, QObject):
        return True                 # Elternfenster (hält die Kinderliste) oder ein Kind/ein Objekt von Qt
    if isinstance(r, (types.FrameType, types.MethodType)) or r is _kandidaten:
        return True                 # laufende Funktion dieses Moduls; gebundene Methode als Slot
    if tiefe > 14:
        return False
    if isinstance(r, dict):         # Attribute eines Objekts: nur von d oder Kindern von d erlaubt
        besitzer = _verweise(r)
        if not besitzer:
            return True
        return all(isinstance(b, QObject) and _vorfahr(b, d) for b in besitzer)
    if isinstance(r, types.FunctionType):
        # nur von Qt gehalten (Signalverbindung): innen nur, wenn die Funktion im Dialog selbst entstand
        # (z. B. „Klasse.__init__.<locals>.<lambda>“); eine Lambda von außen (Menü, Timer) hält den Dialog
        if not (_im_dialog(r, d) or _vor_exec_verdrahtet(r, d)):
            return False
        return all(_intern(x, d, tiefe + 1, besucht) for x in _verweise(r))
    if isinstance(r, (types.CellType, tuple, list)):     # Closure einer Funktion, Liste in einem Attribut
        weiter = _verweise(r)
        return bool(weiter) and all(_intern(x, d, tiefe + 1, besucht) for x in weiter)
    return False


_orte = {}                          # id(Dialog) -> [(Code, Zeile)] der aufrufenden Funktionen beim Start von exec()


def _vor_exec_verdrahtet(f, d):
    """Entstand die Funktion in der Funktion, die den Dialog gezeigt hat, und zwar VOR dem Aufruf von exec()
    (Knöpfe des Dialogs verdrahten, z. B. „def rueck(): …; knopf.clicked.connect(rueck); d.exec()“)? Eine danach
    angelegte Lambda (z. B. an eine Menüaktion gehängt) hält den Dialog weiter."""
    code = f.__code__
    for aufrufer, zeile in _orte.get(id(d), ()):
        if any(c is code for c in aufrufer.co_consts) and code.co_firstlineno < zeile:
            return True
    return False


def _im_dialog(f, d):
    """Entstand die Funktion in einer Methode der Klasse des Dialogs (oder einer Oberklasse aus dem Programm)?"""
    vorne = f.__qualname__.split(".<locals>", 1)[0].split(".", 1)[0]
    return any(k.__qualname__ == vorne for k in type(d).__mro__ if not k.__module__.startswith(("PySide6", "shiboken")))


def _beschreibung(r):
    if isinstance(r, dict):
        b = [type(x).__name__ for x in gc.get_referrers(r) if getattr(x, "__dict__", None) is r]
        return f"Attribute von {b[0] if b else '?'}: {[k for k, v in r.items()][:3]}"
    if isinstance(r, types.FunctionType):
        return r.__qualname__
    if isinstance(r, list):
        b = [type(x).__name__ for x in gc.get_referrers(r) if not isinstance(x, types.FrameType)]
        return f"Liste in {b[:3]}"
    if isinstance(r, types.CellType):
        f = [g for t in gc.get_referrers(r) if isinstance(t, tuple) for g in gc.get_referrers(t)
             if isinstance(g, types.FunctionType)]
        return f"Lambda/Funktion {f[0].__qualname__ if f else '?'}"
    return ""


def _gehalten(d, eigene=None):
    """Verweist außer dem Dialog selbst (und seinen Kindern) noch etwas auf d?"""
    try:
        for r in _verweise(d):
            if r is not eigene and not _intern(r, d):
                GRUND[:] = [type(d).__name__, type(r).__name__, _beschreibung(r)]
                return True
        return False
    finally:
        _eigene_listen.clear()


def einmal(f, attribut, neu, auffrischen="aktualisieren"):
    """Nicht modales Fenster nur einmal: steht unter f.<attribut> noch eins, kommt es nach vorn (aufgefrischt),
    sonst wird neu() gebaut, gezeigt und gemerkt. Ergebnis: das Fenster. (Vorher legte jedes Öffnen ein weiteres
    Fenster an; das alte blieb bis zum Programmende im Speicher, Mehrfachöffnung.)"""
    w = getattr(f, attribut, None)
    if w is not None and _gueltig(w):
        try:
            if callable(getattr(w, auffrischen, None)):
                getattr(w, auffrischen)()
            if w.isMinimized():
                w.showNormal()
            w.show()
            w.raise_()
            w.activateWindow()
            return w
        except RuntimeError:
            pass
    w = neu()
    setattr(f, attribut, w)
    w.show()
    return w


def ersetzen(f, attribut, neu):
    """f.<attribut> = neu; ein altes, nicht mehr sichtbares Fenster dort wird freigegeben, ein sichtbares geschlossen
    und freigegeben (es wird ja durch das neue ersetzt). Ergebnis: neu."""
    alt = getattr(f, attribut, None)
    setattr(f, attribut, neu)
    if alt is not None and alt is not neu and _gueltig(alt):
        try:
            alt.close()
            alt.deleteLater()
        except RuntimeError:
            pass
    return neu


def merken(d):
    """Nach exec(): Dialog für den nächsten Durchgang vormerken."""
    global _zeit
    if not isinstance(d, QDialog) or not _gueltig(d):
        return
    try:
        if d.parent() is None or d.testAttribute(Qt.WA_DeleteOnClose):
            return                  # ohne Elternfenster räumt Python auf; DeleteOnClose löscht Qt selbst
    except RuntimeError:
        return
    if not any(k is d for k in _kandidaten):
        _kandidaten.append(d)
    if _zeit is None:
        app = QApplication.instance()
        if app is None:
            return
        _zeit = QTimer(app)
        _zeit.setSingleShot(True)
        _zeit.timeout.connect(aufraeumen)
    if not _zeit.isActive():
        _zeit.start(WARTEN_MS)


def aufraeumen(sofort=False):
    """Vorgemerkte Dialoge löschen, die keiner mehr hält. Ergebnis: Anzahl gelöschter Dialoge."""
    if not _kandidaten:
        return 0
    if not sofort and (QThread.currentThread().loopLevel() > 1 or QApplication.activeModalWidget() is not None):
        _zeit.start(WARTEN_MS)      # noch in einem anderen Dialog: später
        return 0
    statistik["durchgaenge"] += 1
    gc.collect()
    n = 0
    eigene = sys._getframe()
    spaeter = []
    while _kandidaten:
        d = _kandidaten.pop()           # danach hält nur noch diese Variable (Frame) den Dialog
        if not _gueltig(d):
            continue
        try:
            if d.isVisible():
                _versuche.pop(id(d), None)
                continue
            if _gehalten(d, eigene):
                statistik["gehalten"] += 1
                if len(gruende) < 50:
                    gruende.append(tuple(GRUND))
                # vielleicht nur kurz gehalten (Aufrufer noch nicht fertig): später noch einmal, höchstens 3-mal
                _versuche[id(d)] = _versuche.get(id(d), 0) + 1
                if _versuche[id(d)] <= VERSUCHE:
                    spaeter.append(d)
                else:
                    _versuche.pop(id(d), None)
                continue
            _versuche.pop(id(d), None)
            d.deleteLater()
            n += 1
        except RuntimeError:
            continue
    del d
    if spaeter:
        _kandidaten.extend(spaeter)
        if _zeit is not None:
            _zeit.start(WARTEN_MS * 4)
    statistik["geloescht"] += n
    return n


def _ort_merken(d):
    try:
        rahmen, orte = sys._getframe(2), []
        while rahmen is not None and len(orte) < 6:
            orte.append((rahmen.f_code, rahmen.f_lineno))
            rahmen = rahmen.f_back
        _orte[id(d)] = orte
        d.destroyed.connect(lambda *_a, i=id(d): _orte.pop(i, None))
    except (RuntimeError, ValueError):
        pass


def _exec(self, *args, **kwargs):
    _ort_merken(self)
    try:
        return _alt_exec(self, *args, **kwargs)
    finally:
        merken(self)


def _mb_exec(self, *args, **kwargs):
    _ort_merken(self)
    try:
        return _alt_mb_exec(self, *args, **kwargs)
    finally:
        merken(self)


def einrichten():
    """QDialog.exec und QMessageBox.exec einmal umleiten (alle Dialoge und Meldungen mit Elternfenster)."""
    global _alt_exec, _alt_mb_exec
    if _alt_exec is None:
        _alt_exec, _alt_mb_exec = QDialog.exec, QMessageBox.exec
        QDialog.exec = _exec
        QMessageBox.exec = _mb_exec
    return True
