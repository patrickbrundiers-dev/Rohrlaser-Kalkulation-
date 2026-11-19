"""Updates ohne Internet verteilen (Auftrag Patrick 19.11.2026): Update-Ordner im Firmennetz oder auf einem
USB-Stick, Update-Datei (.rlupdate) zum Mitnehmen, Freigabe durch den Administrator, Rückmeldung der Arbeitsplätze.

Keine zweite Update-Logik: Ein Update-Ordner enthält genau das, was das Online-Update im Release „update-dateien“
findet – die signierte Dateiliste Update.json, ihre Signatur Update.json.sig und die inhaltsadressierten Pakete.
update.online_liste/laden/einspielen lesen ihn wie eine Adresse (Pfade statt https) und prüfen dieselbe Signatur
und dieselben Prüfsummen. Wer Dateien in den Ordner legt, kann deshalb kein fremdes oder verändertes Programm
einschleusen und keine ältere Version erzwingen (update.neuer).

Aufbau des Update-Ordners (z. B. \\\\server\\Rohrlaser\\Updates oder der Unterordner Updates im gemeinsamen
Ordner):

    <Ordner>\\Kalkulation\\Update.json, Update.json.sig, Sperrliste.json, d-….zip, p-….zip
    <Ordner>\\Kalkulation\\Freigabe.json        Vorgaben des Admins: Pflicht ab Datum, Hinweis, nur aus dem Ordner
    <Ordner>\\Kalkulation\\Plaetze\\<PC>.json     Rückmeldung je Arbeitsplatz: Version, Zeit, Ergebnis

Update-Datei (.rlupdate): ein ZIP (ungepackt gespeichert, die Pakete sind schon gepackt) mit denselben Dateien.
Beim Einlesen sind nur diese Namen erlaubt; jede andere Datei, ein Pfad oder ein Ordner macht die Datei ungültig.

Ohne Qt, ohne Datenbank.
"""
import datetime
import json
import os
import re
import socket
import zipfile
from pathlib import Path

from . import update

UNTERORDNER = "Kalkulation"
FREIGABE = "Freigabe.json"
PLAETZE = "Plaetze"
ENDUNG = ".rlupdate"
DATEI_MAX = 4 << 30                  # ganze Update-Datei
HINWEIS_MAX = 500
_ERLAUBT = re.compile(r"(Update\.json|Update\.json\.sig|Sperrliste\.json|[dp]-[0-9a-f]{40}\.zip)")


class VerteilFehler(update.UpdateFehler):
    pass


def jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ Update-Ordner finden
def liste_im_ordner(ordner):
    """Pfad der Update.json in einem Update-Ordner (…\\Kalkulation\\Update.json oder direkt im Ordner, z. B. ein
    von Hand befüllter USB-Stick) oder None."""
    if not ordner:
        return None
    o = Path(str(ordner).strip())
    for p in (o / UNTERORDNER / update.DATEILISTE, o / update.DATEILISTE):
        try:
            if p.is_file():
                return p
        except OSError:         # Netzlaufwerk weg
            return None
    return None


def kalkulation_ordner(ordner):
    return Path(str(ordner).strip()) / UNTERORDNER


# ------------------------------------------------------------------ Bereitstellen (Admin)
def bereitstellen(quelle, ziel_ordner, fortschritt=None, melden=None, erzwingen=False):
    """Update aus quelle (Objekt aus update_quellen: Internet, anderer Ordner oder Update-Datei) in den Update-Ordner
    ziel_ordner legen: erst alle Pakete (geprüft), dann Signatur und Dateiliste, zuletzt Pakete löschen, die weder
    die neue noch die vorige Liste braucht (Arbeitsplätze, die gerade die vorige Liste laden, finden ihre Pakete
    noch). Ein Ordner mit einem neueren Stand wird nicht überschrieben (außer erzwingen). Ergebnis: Dateiliste."""
    online = quelle.liste()
    ziel = kalkulation_ordner(ziel_ordner)
    try:
        ziel.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise VerteilFehler(f"Der Update-Ordner {ziel} lässt sich nicht anlegen ({e}). Schreibrechte prüfen.") from e
    vorher = update.lokale_liste(ziel)
    if vorher and not erzwingen and int(vorher.get("stand") or 0) > int(online.get("stand") or 0):
        raise VerteilFehler(f"Im Update-Ordner liegt schon ein neuerer Stand ({update.stand_text(vorher)}) als "
                            f"{update.stand_text(online)}. Nichts geändert.")
    gesamt = sum(p.get("groesse", 0) for p in online["pakete"].values())
    erledigt = [0]

    def weiter(n):
        erledigt[0] += n
        if fortschritt:
            fortschritt(erledigt[0], gesamt)

    for paket, info in sorted(online["pakete"].items()):
        z = ziel / paket
        if info.get("sha256") and update._vorhanden(z, info["sha256"]):
            weiter(info.get("groesse", 0))
            continue
        teil = ziel / (paket + ".teil")
        quelle.paket_holen(online, paket, teil, weiter, melden)
        if info.get("sha256") and update.pruefsumme(teil) != info["sha256"]:
            teil.unlink(missing_ok=True)
            raise VerteilFehler(f"Prüfsumme des Pakets {paket} falsch, der Update-Ordner bleibt wie er war.")
        os.replace(teil, z)
    # Signatur zuerst, dann die Liste: ein Platz, der dazwischen liest, versucht es einmal neu (online_liste)
    _schreiben(ziel / update.SIGNATUR, online.signatur) if online.signatur else (ziel / update.SIGNATUR).unlink(
        missing_ok=True)
    _schreiben(ziel / update.DATEILISTE, online.roh or json.dumps(online, ensure_ascii=False).encode("utf-8"))
    sperr = quelle.sperrliste()
    if sperr:
        _schreiben(ziel / update.SPERRLISTE, sperr)
    gebraucht = set(online["pakete"]) | set((vorher or {}).get("pakete") or ())
    for p in ziel.iterdir():
        if (p.suffix == ".zip" and p.name not in gebraucht) or p.name.endswith(".teil"):
            p.unlink(missing_ok=True)
    return online


def _schreiben(pfad, daten):
    tmp = pfad.with_name(pfad.name + ".neu")
    tmp.write_bytes(bytes(daten))
    os.replace(tmp, pfad)


# ------------------------------------------------------------------ Update-Datei (.rlupdate)
def datei_erstellen(liste_ordner, datei):
    """Update-Datei aus einem Ordner mit Update.json, Signatur und Paketen (Update-Ordner, Build: update_dateien).
    Nur die Pakete der Liste. Ergebnis: Pfad."""
    o = Path(liste_ordner)
    liste = update.lokale_liste(o)
    if not liste:
        raise VerteilFehler(f"In {o} liegt keine Dateiliste {update.DATEILISTE}.")
    datei = Path(datei)
    if datei.suffix != ENDUNG:
        datei = datei.with_name(datei.name + ENDUNG)
    fehlt = [p for p in liste.get("pakete") or () if not (o / p).is_file()]
    if fehlt:
        raise VerteilFehler(f"Im Ordner {o} fehlen {len(fehlt)} Pakete der Dateiliste (z. B. {fehlt[0]}).")
    tmp = datei.with_name(datei.name + ".teil")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
        for name in (update.DATEILISTE, update.SIGNATUR, update.SPERRLISTE):
            if (o / name).is_file():
                z.write(o / name, name)
        for p in sorted(liste["pakete"]):
            z.write(o / p, p)
    os.replace(tmp, datei)
    return datei


def datei_pruefen(datei):
    """Aufbau einer Update-Datei prüfen (nur erlaubte Namen, keine Pfade, Größen). Ergebnis: {Name: ZipInfo}."""
    datei = Path(datei)
    try:
        if datei.stat().st_size > DATEI_MAX:
            raise VerteilFehler(f"{datei.name} ist zu groß für eine Update-Datei.")
        with zipfile.ZipFile(datei) as z:
            eintraege = {}
            for e in z.infolist():
                if e.is_dir() or not _ERLAUBT.fullmatch(e.filename) or e.filename in eintraege:
                    raise VerteilFehler(f"{datei.name} ist keine gültige Update-Datei (unerwarteter Inhalt: "
                                        f"{e.filename[:80]}).")
                if e.file_size > update.PAKET_GROESSE_MAX:
                    raise VerteilFehler(f"{datei.name}: {e.filename} ist zu groß.")
                eintraege[e.filename] = e
    except (OSError, zipfile.BadZipFile) as e:
        raise VerteilFehler(f"{datei.name} lässt sich nicht als Update-Datei lesen: {e}") from e
    if update.DATEILISTE not in eintraege:
        raise VerteilFehler(f"{datei.name} enthält keine Dateiliste {update.DATEILISTE}.")
    return eintraege


def datei_auspacken(datei, ziel, namen=None):
    """Aus einer Update-Datei nach ziel auspacken: Dateiliste, Signatur, Sperrliste und die Pakete namen (None =
    alle). Je Eintrag nie mehr als angekündigt (ZIP-Bombe). Ergebnis: Pfad der Dateiliste in ziel."""
    eintraege = datei_pruefen(datei)
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    gewuenscht = {update.DATEILISTE, update.SIGNATUR, update.SPERRLISTE}
    gewuenscht |= set(eintraege) if namen is None else set(namen)
    with zipfile.ZipFile(datei) as z:
        for name, e in eintraege.items():
            if name not in gewuenscht:
                continue
            p = ziel / name
            if p.is_file() and p.stat().st_size == e.file_size and name.endswith(".zip"):
                continue        # schon da (zweiter Versuch); die Prüfsumme prüft update.laden
            kopiert = 0
            with z.open(e) as q, open(p.with_name(name + ".teil"), "wb") as f:
                for teil in iter(lambda: q.read(1 << 20), b""):
                    kopiert += len(teil)
                    if kopiert > e.file_size:
                        raise VerteilFehler(f"{Path(datei).name}: {name} größer als angekündigt.")
                    f.write(teil)
            os.replace(p.with_name(name + ".teil"), p)
    return ziel / update.DATEILISTE


# ------------------------------------------------------------------ Freigabe durch den Admin
def freigabe_lesen(ordner):
    """Vorgaben im Update-Ordner (dict) oder {}. Felder: stand, pflicht, pflicht_ab (JJJJ-MM-TT), hinweis, wartung,
    nur_ordner, von, zeit. Unbekanntes oder Kaputtes zählt nicht (dann gilt: freiwillig, auch Internet)."""
    p = kalkulation_ordner(ordner) / FREIGABE if ordner else None
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p and p.is_file() else {}
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    erg = dict(pflicht=bool(d.get("pflicht")), nur_ordner=bool(d.get("nur_ordner")),
               hinweis=str(d.get("hinweis") or "")[:HINWEIS_MAX], wartung=str(d.get("wartung") or "")[:200],
               von=str(d.get("von") or "")[:40], zeit=str(d.get("zeit") or "")[:40])
    try:
        erg["pflicht_ab"] = datetime.date.fromisoformat(str(d.get("pflicht_ab"))).isoformat()
    except ValueError:
        erg["pflicht_ab"] = ""
    if isinstance(d.get("stand"), int):
        erg["stand"] = d["stand"]
    return erg


def freigabe_schreiben(ordner, stand=None, pflicht=False, pflicht_ab="", hinweis="", wartung="", nur_ordner=False,
                       von=""):
    """Vorgaben des Admins in den Update-Ordner schreiben (nur über das Update-Center, nur als Admin)."""
    if pflicht_ab:
        pflicht_ab = datetime.date.fromisoformat(str(pflicht_ab)).isoformat()
    d = dict(format=1, stand=stand, pflicht=bool(pflicht), pflicht_ab=pflicht_ab or "",
             hinweis=str(hinweis or "")[:HINWEIS_MAX], wartung=str(wartung or "")[:200], nur_ordner=bool(nur_ordner),
             von=str(von or "")[:40], zeit=jetzt())
    z = kalkulation_ordner(ordner)
    z.mkdir(parents=True, exist_ok=True)
    _schreiben(z / FREIGABE, json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8"))
    return d


def pflicht_faellig(freigabe, heute=None):
    """Pflicht-Update, dessen Datum erreicht ist (dann bietet das Programm kein „Später“ mehr an)."""
    if not freigabe.get("pflicht"):
        return False
    ab = freigabe.get("pflicht_ab")
    return not ab or (heute or datetime.date.today()).isoformat() >= ab


# ------------------------------------------------------------------ Rückmeldung der Arbeitsplätze
def platz_name():
    n = re.sub(r"[^A-Za-z0-9_.-]", "_", socket.gethostname() or os.environ.get("COMPUTERNAME") or "PC")
    return n[:60] or "PC"


def rueckmelden(ordner, eintrag, platz=None):
    """Stand dieses Arbeitsplatzes in den Update-Ordner schreiben (Plaetze/<PC>.json); Fehler zählen nicht (der
    Ordner kann fehlen oder schreibgeschützt sein). Keine Zugangsdaten, nur Version, Stand, Zeit, Ergebnis."""
    if not ordner:
        return False
    try:
        z = kalkulation_ordner(ordner) / PLAETZE
        z.mkdir(parents=True, exist_ok=True)
        d = dict(platz=platz or platz_name(), zeit=jetzt(),
                 **{k: eintrag.get(k) for k in ("kuerzel", "version", "stand", "ergebnis", "quelle", "fehler")})
        if d.get("fehler"):
            d["fehler"] = str(d["fehler"])[:300]
        _schreiben(z / f"{d['platz']}.json", json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8"))
        return True
    except OSError:
        return False


def plaetze(ordner):
    """Rückmeldungen aller Arbeitsplätze, neueste zuerst (für die Übersicht des Admins)."""
    z = kalkulation_ordner(ordner) / PLAETZE if ordner else None
    erg = []
    try:
        dateien = sorted(z.glob("*.json")) if z and z.is_dir() else []
    except OSError:
        dateien = []
    for p in dateien:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            erg.append(d)
    return sorted(erg, key=lambda d: str(d.get("zeit") or ""), reverse=True)


def veraltete(plaetze_liste, stand):
    """Arbeitsplätze mit einem älteren Stand als stand (Erkennung unterschiedlicher Versionen)."""
    return [p for p in plaetze_liste if isinstance(p.get("stand"), int) and p["stand"] < int(stand or 0)]

