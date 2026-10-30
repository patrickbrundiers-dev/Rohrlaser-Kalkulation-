"""Austauschweg: wie die Arbeitsplätze ihre Daten tauschen (Plan Server-Synchronisation, Patrick 30.10.2026, Schritt 1).

teilen.py, nummern.py, Anfragen, Angebotsordner und Sicherung greifen nicht mehr selbst auf den gemeinsamen Ordner zu,
sondern nur über diese Schnittstelle. Heute gibt es genau einen Weg, den gemeinsamen Ordner (OrdnerWeg); Aufbau der
Dateien und Verhalten sind dieselben wie vorher. Später kommt ein Server als zweiter Weg mit denselben Aufgaben dazu:

- Daten der Mitarbeiter: eigene Hauptdatei finden, die der Kollegen auflisten und lokal holen, eigene Daten ablegen
- Nummern: höchsten belegten Zählerstand eines Bereichs (Nummern, AB-Nummern) lesen und einen Zählerstand exklusiv belegen
- Dateien: Unterordner für Anfragen, Angebotsordner und Sicherungen; einzelne Dateien lesen und atomar schreiben
  (Admin-Vorgaben, admin_schutz.py)
"""
import json
import os
import shutil
from pathlib import Path

PRAEFIX = "Rohrlaser_"
ENDUNG = ".sqlite"
HAUPT = "haupt.sqlite"
MONAT_PRAEFIX = "Angebote_"
NUMMER_ENDUNG = ".nummer"


def datei_name(k):
    return f"{PRAEFIX}{k}{ENDUNG}"


def ordner_name(k):
    return f"{PRAEFIX}{k}"


def lokal_kopieren(quelle, ziel):
    """Datei in den Zwischenspeicher kopieren (nur wenn neu oder geändert): so liest das Programm nie eine Datei, die
    gerade ausgetauscht oder synchronisiert wird."""
    st = quelle.stat()
    merk = ziel.with_suffix(".stand")
    stand = f"{st.st_size}|{st.st_mtime_ns}"
    if ziel.exists() and merk.exists() and merk.read_text() == stand:
        return ziel
    tmp = ziel.with_name(ziel.name + ".neu")
    shutil.copyfile(quelle, tmp)
    os.replace(tmp, ziel)
    merk.write_text(stand)
    return ziel


def hinlegen(quelle, ziel):
    """Datei in einem Schritt austauschen: erst daneben kopieren, dann umbenennen."""
    tmp = ziel.with_name(ziel.name + ".neu")
    try:
        shutil.copy2(quelle, tmp)
        os.replace(tmp, ziel)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


class OrdnerWeg:
    """Gemeinsamer Ordner (Netzlaufwerk, NAS, OneDrive/SharePoint): je Mitarbeiter ein Ordner Rohrlaser_<Kürzel> mit
    haupt.sqlite und Monatsdateien (Format 2), alte Einzeldateien Rohrlaser_<Kürzel>.sqlite (Format 1) werden gelesen."""
    art = "ordner"

    def __init__(self, pfad):
        self.pfad = Path(pfad)

    def __str__(self):
        return str(self.pfad)

    def erreichbar(self):
        return self.pfad.is_dir()

    # -------------------------------------------------------------- Daten der Mitarbeiter
    def haupt(self, k):
        """Hauptdatei des Kürzels k (Format 2), sonst die alte Einzeldatei (Format 1), sonst None."""
        neu = self.pfad / ordner_name(k) / HAUPT
        if neu.is_file():
            return neu
        alt = self.pfad / datei_name(k)
        return alt if alt.is_file() else None

    def mitarbeiter(self, ich, sauber):
        """{Kürzel: Hauptdatei} der anderen Mitarbeiter (Format 2 vor der alten Einzeldatei). sauber: Kürzel prüfen."""
        out = {}
        for p in sorted(self.pfad.glob(f"{PRAEFIX}*")):
            name = p.name[len(PRAEFIX):]
            if name.endswith(ENDUNG):
                name = name[:-len(ENDUNG)]
            k = sauber(name)
            if not k or k == ich or k in out or p.name not in (datei_name(k), ordner_name(k)):
                continue
            h = self.haupt(k)
            if h is not None:
                out[k] = h
        return out

    def stand(self, haupt_dateien):
        """Größe und Zeit der Hauptdateien: unverändert = nichts Neues zu lesen."""
        out = []
        for k, p in haupt_dateien.items():
            st = p.stat()
            out.append((k, st.st_size, st.st_mtime_ns))
        return tuple(out)

    def teil(self, haupt, name):
        """Verweis auf eine Monatsdatei neben der Hauptdatei."""
        return haupt.parent / name

    def holen(self, quelle, ziel):
        """Datei eines Kollegen lokal holen (nur wenn geändert). Ergebnis: lokaler Pfad."""
        return lokal_kopieren(quelle, ziel)

    def ablegen(self, k, spiegel, teile, merk_name="hingelegt.json"):
        """Eigene Daten aus dem lokalen Spiegel ablegen: Monatsdateien zuerst (nur geänderte oder dort fehlende), die
        Hauptdatei zuletzt (sie verweist auf die Monate), entfallene Monate und die alte Einzeldatei weg.
        teile: {Monatsdatei: Prüfsumme}. OSError, wenn der Ordner nicht beschreibbar ist."""
        ziel_ordner = self.pfad / ordner_name(k)
        merk = spiegel / merk_name                  # {Monatsdatei: Prüfsumme} im gemeinsamen Ordner
        try:
            hingelegt = json.loads(merk.read_text()) if merk.exists() else {}
        except ValueError:
            hingelegt = {}
        if str(hingelegt.pop("_ordner", "")) != str(ziel_ordner):
            hingelegt = {}
        ziel_ordner.mkdir(exist_ok=True)
        for name, stand in teile.items():
            if hingelegt.get(name) != stand or not (ziel_ordner / name).is_file():
                hingelegt.pop(name, None)
                hinlegen(spiegel / name, ziel_ordner / name)
                hingelegt[name] = stand
                merk.write_text(json.dumps(dict(hingelegt, _ordner=str(ziel_ordner))))
        hinlegen(spiegel / HAUPT, ziel_ordner / HAUPT)
        for p in ziel_ordner.glob(f"{MONAT_PRAEFIX}*.sqlite"):
            if p.name not in teile:
                p.unlink(missing_ok=True)
        (self.pfad / datei_name(k)).unlink(missing_ok=True)      # alte Einzeldatei (Format 1) ist abgelöst

    # -------------------------------------------------------------- Nummern
    def _bereich(self, bereich, anlegen=False):
        o = self.pfad / bereich
        if anlegen:
            o.mkdir(exist_ok=True)
        return o

    def nummer_hoechste(self, bereich):
        """Höchster belegter Zählerstand im Bereich (Unterordner Nummern bzw. AB-Nummern)."""
        o = self._bereich(bereich, anlegen=True)
        return max((int(p.stem) for p in o.iterdir() if p.suffix == NUMMER_ENDUNG and p.stem.isdigit()), default=0)

    def nummer_belegen(self, bereich, n, text):
        """Zählerstand n exklusiv belegen: True, wenn er frei war (zwei Arbeitsplätze können dieselbe Datei nicht
        beide anlegen). text: Inhalt der Reservierung (Nummer, Kürzel, Rechner, Zeit)."""
        try:
            fd = os.open(self._bereich(bereich, anlegen=True) / f"{n:05d}{NUMMER_ENDUNG}",
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return True

    # -------------------------------------------------------------- Dateien
    def datei_lesen(self, *teile):
        """Inhalt (bytes) einer Datei im gemeinsamen Ordner, z. B. ("Admin", "admin_vorgaben.json"); None = fehlt."""
        try:
            return self.pfad.joinpath(*teile).read_bytes()
        except FileNotFoundError:
            return None

    def datei_schreiben(self, daten, *teile):
        """Datei atomar ersetzen (erst daneben schreiben, dann umbenennen); fehlende Unterordner werden angelegt."""
        ziel = self.pfad.joinpath(*teile)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        tmp = ziel.with_name(f"{ziel.name}.{os.getpid()}.neu")
        tmp.write_bytes(daten)
        os.replace(tmp, ziel)

    def unterordner(self, name, anlegen=False):
        """Unterordner (Anfragen, Angebote, Sicherungen) oder None, wenn der Ordner nicht erreichbar ist."""
        if not self.erreichbar():
            return None
        u = self.pfad / name
        if anlegen:
            try:
                u.mkdir(exist_ok=True)
            except OSError:
                return None
        return u


def weg(ordner):
    """Austauschweg zum eingetragenen gemeinsamen Ordner (Path oder None)."""
    return OrdnerWeg(ordner) if ordner is not None else None
