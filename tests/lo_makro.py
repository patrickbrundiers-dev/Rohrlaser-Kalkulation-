"""Führt VBA-Makros der Mappe in LibreOffice (headless) aus, für automatische Tests unter Linux.

LibreOffice liest das VBA-Projekt der .xlsm und führt es im VBA-Kompatibilitätsmodus aus.
Damit lässt sich prüfen, dass der Quelltext übersetzt und die VBA-Fassung dieselben
Ergebnisse liefert wie die Python-Fassung. Excel selbst kann hier nicht laufen.

    with LibreOffice() as lo:
        rueckgabe = lo.ausfuehren("ein.xlsm", "Optimierung.OptimiereTest", "aus.xlsx")
"""
import os
import subprocess
import tempfile
import time

import uno
from com.sun.star.beans import PropertyValue


def _pv(name, wert):
    p = PropertyValue()
    p.Name, p.Value = name, wert
    return p


class LibreOffice:
    def __init__(self, port=2002):
        self.port = port

    def __enter__(self):
        self._profil = tempfile.TemporaryDirectory()
        self.proc = subprocess.Popen(
            ["soffice", "--headless", "--invisible", "--norestore", "--nologo",
             f"-env:UserInstallation=file://{self._profil.name}",
             f"--accept=socket,host=localhost,port={self.port};urp;"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        lokal = uno.getComponentContext()
        res = lokal.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", lokal)
        for _ in range(120):
            try:
                ctx = res.resolve(f"uno:socket,host=localhost,port={self.port};urp;StarOffice.ComponentContext")
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("LibreOffice startet nicht")
        self.desk = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        return self

    def ausfuehren(self, mappe, makro, ausgabe=None, argumente=()):
        """makro = 'Modul.Prozedur' oder Liste [(makro, argumente), ...] (nacheinander im selben Dokument).
        Speichert das Ergebnis als .xlsx (Formelwerte berechnet). Rückgabe des (letzten) Makros."""
        url = uno.systemPathToFileUrl(os.path.abspath(mappe))
        doc = self.desk.loadComponentFromURL(url, "_blank", 0, (_pv("Hidden", True), _pv("MacroExecutionMode", 4)))
        aufrufe = makro if isinstance(makro, list) else [(makro, argumente)]
        try:
            for makro, argumente in aufrufe:
                skript = doc.getScriptProvider().getScript(
                    f"vnd.sun.star.script:VBAProject.{makro}?language=Basic&location=document")
                rueckgabe = skript.invoke(tuple(argumente), (), ())[0]
                if isinstance(rueckgabe, str) and rueckgabe.startswith("FEHLER"):
                    break
            if ausgabe:
                doc.calculateAll()
                doc.storeToURL(uno.systemPathToFileUrl(os.path.abspath(ausgabe)),
                               (_pv("FilterName", "Calc MS Excel 2007 XML"),))
        finally:
            doc.close(True)
        return rueckgabe

    def __exit__(self, *exc):
        try:
            self.desk.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self._profil.cleanup()
