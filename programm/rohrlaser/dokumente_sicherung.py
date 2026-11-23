"""Angebotsdokumente mit der Datenbank sichern und zurückholen (Datenbank-Auftrag 19.11.2026, Schritt 4).

Die Datenbank-Sicherung (Datenbank.sicherung) enthält Angebote und Positionen, nicht aber die Dateien der Angebote
(PDFs, Angebotsakte, STEP-Kopien, Materialanfragen in der Ablage). Dieses Modul legt einen Spiegel der Ablage neben die
Sicherungen und merkt je Datenbank-Sicherung, welche Dateien zu diesem Stand gehörten:

    <Sicherung>/Dokumente/aktuell/<Pfad in der Ablage>     zuletzt gesehener Stand jeder Datei
    <Sicherung>/Dokumente/alt/<JJJJ-MM-TT>/<Pfad>          ältere Stände (geändert oder gelöscht), ALT_TAGE lang
    <Sicherung>/<Sicherung>.dokumente.json                 Liste {Pfad: [Größe, Zeit]} zu dieser Sicherung

Gespiegelt wird nur, was sich geändert hat (Größe oder Zeit), die erste Sicherung dauert also am längsten. Nichts wird
in der Ablage gelöscht oder überschrieben, was neuer ist: zurückholen() legt nur fehlende Dateien und Dateien mit
anderem Stand zurück und verschiebt den abweichenden Stand vorher nach <Ablage>/_vor_Wiederherstellung/<Zeit>/.
Ohne Qt.
"""
import datetime
import json
import os
import shutil
from pathlib import Path

ORDNER = "Dokumente"
AKTUELL, ALT = "aktuell", "alt"
ANFRAGEN = "Anfragen"           # Spiegel der Anfrage-Akten (Mails, Dokumente, Verlauf), Anfragen zusammenführen
LISTE = ".dokumente.json"
ALT_TAGE = 60                   # ältere Stände so lange aufheben
VOR_WIEDERHERSTELLUNG = "_vor_Wiederherstellung"
ZEIT_TOLERANZ_NS = 2_000_000_000     # Netzlaufwerke und FAT speichern Zeiten auf 2 s genau
_AUSLASSEN = (".tmp", ".part", ".lock", ".neu")


def lang(p):
    """Pfad, der unter Windows auch über 260 Zeichen geht (Präfix \\\\?\\): der Spiegel liegt eine Ebene tiefer als die
    Ablage, lange Mail-Namen in Anfrage-Ordnern scheiterten sonst mit „[WinError 3] Das System kann den angegebenen
    Pfad nicht finden“ (Supportpaket 23.11.2026). Andere Systeme: unverändert."""
    if os.name != "nt":
        return Path(p)
    t = os.path.abspath(str(p))
    if t.startswith("\\\\?\\"):
        return Path(t)
    if t.startswith("\\\\"):                       # Netzlaufwerk \\server\freigabe
        return Path("\\\\?\\UNC\\" + t[2:])
    return Path("\\\\?\\" + t)


def ablage(db, vorgabe):
    """Ablage der Angebotsdokumente wie im Hauptfenster (Hauptfenster.ablage): mit gemeinsamem Ordner dessen
    Unterordner „Angebote“, sonst die eigene Ablage. Für die Sicherung beim Start, bevor das Fenster steht."""
    from . import ausgabe, teilen
    gemeinsam = teilen.unterordner(db, teilen.ANGEBOTE, "teilen_ablage", anlegen=True)
    return gemeinsam if gemeinsam is not None else ausgabe.ablageordner(db.einstellung("ablageordner"), vorgabe)


def _auslassen(rel):
    teile = Path(rel).parts
    name = teile[-1]
    return (name.startswith("~$") or name.startswith(".") or name.lower().endswith(_AUSLASSEN)
            or teile[0] == VOR_WIEDERHERSTELLUNG)


def bestand(ablage):
    """{relativer Pfad (mit /): [Größe, mtime_ns]} aller Dateien der Ablage (ohne Office-Sperrdateien und Reste)."""
    ablage = Path(ablage)
    ergebnis = {}
    for wurzel, ordner, dateien in os.walk(ablage):
        ordner[:] = [o for o in ordner if not o.startswith(".") and o != VOR_WIEDERHERSTELLUNG]
        for d in dateien:
            p = Path(wurzel) / d
            rel = p.relative_to(ablage).as_posix()
            if _auslassen(rel):
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            ergebnis[rel] = [st.st_size, st.st_mtime_ns]
    return ergebnis


def _gleich(p, merkmal):
    try:
        st = p.stat()
    except OSError:
        return False
    return st.st_size == merkmal[0] and abs(st.st_mtime_ns - merkmal[1]) <= ZEIT_TOLERANZ_NS


def _kopieren(quelle, ziel):
    ziel.parent.mkdir(parents=True, exist_ok=True)
    neu = ziel.with_name(ziel.name + ".neu")
    shutil.copy2(quelle, neu)
    os.replace(neu, ziel)


def spiegeln(ablage, sicherungsordner, liste_fuer=None, heute=None, ordner=ORDNER):
    """Ablage in <sicherungsordner>/Dokumente spiegeln. liste_fuer: Pfad der Datenbank-Sicherung, neben die die Liste
    <name>.dokumente.json kommt. ordner: anderer Spiegel-Ordner (ANFRAGEN: die Anfrage-Akten, 20.11.2026).
    Ergebnis: dict(neu=…, geaendert=…, weg=…, dateien=…, bytes=…, fehler=[…])."""
    anzeige = Path(ablage)
    ablage, basis = lang(ablage), lang(Path(sicherungsordner) / ordner)
    aktuell = basis / AKTUELL
    heute = heute or datetime.date.today()
    alt = basis / ALT / heute.isoformat()
    jetzt = bestand(ablage) if ablage.is_dir() else {}
    gespiegelt = bestand(aktuell) if aktuell.is_dir() else {}
    z = dict(neu=0, geaendert=0, weg=0, dateien=len(jetzt), bytes=sum(m[0] for m in jetzt.values()), fehler=[])
    for rel, merkmal in jetzt.items():
        ziel = aktuell / rel
        if rel in gespiegelt and _gleich(ziel, merkmal):
            continue
        try:
            if ziel.exists():                       # alter Stand wandert nach alt/<heute>
                (alt / rel).parent.mkdir(parents=True, exist_ok=True)
                os.replace(ziel, alt / rel)
                z["geaendert"] += 1
            else:
                z["neu"] += 1
            _kopieren(ablage / rel, ziel)
        except OSError as e:
            z["fehler"].append(f"{rel}: {e}")
    for rel in set(gespiegelt) - set(jetzt):       # in der Ablage gelöscht: Stand nach alt/<heute>
        try:
            (alt / rel).parent.mkdir(parents=True, exist_ok=True)
            os.replace(aktuell / rel, alt / rel)
            z["weg"] += 1
        except OSError as e:
            z["fehler"].append(f"{rel}: {e}")
    if liste_fuer is not None:
        ziel = listenpfad(liste_fuer)
        ziel.write_text(json.dumps(dict(ablage=str(anzeige), erstellt=datetime.datetime.now().isoformat(
            timespec="seconds"), dateien=jetzt), ensure_ascii=False), encoding="utf-8")
    aufraeumen(sicherungsordner, heute, ordner)
    return z


def listenpfad(sicherung):
    p = Path(sicherung)
    return p.with_name(p.stem + LISTE)


def aufraeumen(sicherungsordner, heute=None, ordner=ORDNER):
    """Ältere Stände nach ALT_TAGE Tagen löschen."""
    heute = heute or datetime.date.today()
    alt = lang(Path(sicherungsordner) / ordner / ALT)
    if not alt.is_dir():
        return
    for o in alt.iterdir():
        try:
            tag = datetime.date.fromisoformat(o.name)
        except ValueError:
            continue
        if (heute - tag).days > ALT_TAGE:
            shutil.rmtree(o, ignore_errors=True)


def liste(sicherung):
    """Dokumentenliste einer Datenbank-Sicherung oder None (ältere Sicherung, Ablage nicht gesichert)."""
    p = listenpfad(sicherung)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _finden(basis, rel, merkmal):
    """Gespiegelte Datei mit genau diesem Stand: aktuell, sonst die älteren Stände (neueste zuerst)."""
    kandidaten = [basis / AKTUELL / rel]
    alt = basis / ALT
    if alt.is_dir():
        kandidaten += [o / rel for o in sorted(alt.iterdir(), reverse=True)]
    for k in kandidaten:
        if _gleich(k, merkmal):
            return k
    return None


def zurueckholen(sicherung, ablage, jetzt=None):
    """Dateien der Ablage auf den Stand der Datenbank-Sicherung bringen: fehlende zurücklegen, abweichende ersetzen
    (der abweichende Stand wird vorher nach <Ablage>/_vor_Wiederherstellung/<Zeit>/ verschoben). Dateien, die erst
    später entstanden sind, bleiben unberührt. Ergebnis: dict(zurueck=…, ersetzt=…, unveraendert=…, fehlt=[…])."""
    daten = liste(sicherung)
    if daten is None:
        return None
    ablage, basis = lang(ablage), lang(Path(sicherung).parent / ORDNER)
    jetzt = jetzt or datetime.datetime.now()
    beiseite = ablage / VOR_WIEDERHERSTELLUNG / f"{jetzt:%Y-%m-%d_%H%M%S}"
    z = dict(zurueck=0, ersetzt=0, unveraendert=0, fehlt=[])
    for rel, merkmal in daten["dateien"].items():
        ziel = ablage / rel
        if _gleich(ziel, merkmal):
            z["unveraendert"] += 1
            continue
        quelle = _finden(basis, rel, merkmal)
        if quelle is None:
            z["fehlt"].append(rel)
            continue
        if ziel.exists():
            (beiseite / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ziel, beiseite / rel)
            z["ersetzt"] += 1
        else:
            z["zurueck"] += 1
        _kopieren(quelle, ziel)
    return z


def text(z):
    """Kurzer Text für Meldung und Protokoll."""
    if z is None:
        return "Zu dieser Sicherung gibt es keine gesicherten Angebotsdokumente."
    if "zurueck" in z:
        t = (f"Angebotsdokumente: {z['zurueck']} zurückgelegt, {z['ersetzt']} ersetzt (vorheriger Stand in "
             f"{VOR_WIEDERHERSTELLUNG}), {z['unveraendert']} unverändert")
        return t + (f", {len(z['fehlt'])} nicht mehr in der Sicherung" if z["fehlt"] else "") + "."
    t = f"Angebotsdokumente gesichert: {z['dateien']} Dateien ({z['neu']} neu, {z['geaendert']} geändert)"
    return t + (f", {len(z['fehler'])} nicht lesbar" if z["fehler"] else "") + "."
