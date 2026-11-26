"""Lizenz 2.0, Paket L2-1: Lizenzzertifikat, Lizenzschlüssel, Geräteschlüssel und Aktivierung ohne Internet.

Ablauf (Freigabe Patrick 26.11.2026, F4a/F6a):
1. Patrick stellt im Lizenz-Werkzeug ein **Lizenzzertifikat** aus (Lizenznehmer, Typ einzelplatz/mehrplatz/server,
   Plätze, Benutzer, Aktivierungen, Module, Laufzeit) und gibt dem Kunden den **Lizenzschlüssel** LZ-XXXXX-…
   Der Schlüssel ist nur die Nummer zum Zertifikat (mit Prüfzeichen gegen Tippfehler) und enthält kein Geheimnis.
2. Am Rechner erzeugt das Programm bei „Mit Lizenzschlüssel aktivieren“ ein eigenes Ed25519-**Geräteschlüsselpaar**.
   Der private Teil liegt unter Windows mit DPAPI (Bereich Rechner) verschlüsselt in Lizenz/geraet.schluessel und
   verlässt den Rechner nie. Die **Aktivierungsanfrage** (Datei oder Code zum Kopieren) enthält Lizenzschlüssel,
   öffentlichen Geräteschlüssel und drei Gerätemerkmale (nur als Prüfwerte) und ist mit dem Geräteschlüssel signiert.
3. Patrick prüft die Anfrage im Lizenz-Werkzeug (Plätze frei?) und schickt eine **Aktivierungsantwort** zurück: mit
   seinem Lizenzschlüssel signiert, enthält das Zertifikat und bindet es an den öffentlichen Geräteschlüssel.
4. Beim Start prüft das Programm: Signatur von Antwort und Zertifikat, der private Geräteschlüssel passt (Probe-
   Signatur), mindestens 2 von 3 Gerätemerkmalen stimmen. Ein kopierter Lizenzordner ist auf einem anderen Rechner
   deshalb wertlos, auch mit gefälschter MachineGuid.
5. **Platz freigeben**: Der Rechner signiert einen Freigabebeleg mit seinem Geräteschlüssel und löscht Aktivierung
   und Geräteschlüssel. Mit dem Beleg gibt das Lizenz-Werkzeug den Platz wieder frei.

Kein Internet nötig, keine Systemüberwachung. Fehler führen über lizenz.py in Kulanz bzw. Lesemodus, nie zum
Datenverlust. Ohne Qt; alle Prüfungen sind reine Funktionen mit Parametern (testbar).
"""
import base64
import datetime
import hashlib
import json
import os
import secrets
import sys
import zlib
from pathlib import Path

FORMAT = 2
TYPEN = ("einzelplatz", "mehrplatz", "server")
TYP_TEXT = dict(einzelplatz="Einzelplatz", mehrplatz="Mehrplatz", server="Server")
ART_ZERTIFIKAT, ART_ANFRAGE, ART_ANTWORT, ART_FREIGABE = "zertifikat", "anfrage", "aktivierung", "freigabe"
DATEI_AKTIVIERUNG = "aktivierung.lizenz"
DATEI_GERAET = "geraet.schluessel"
MERKMALE = ("guid", "platte", "board")
MERKMALE_MIN = 2                 # so viele der drei Gerätemerkmale müssen stimmen (kleiner Hardwaretausch geht)
PRAEFIX = "LZ"                   # Lizenzschlüssel LZ-XXXXX-XXXXX-XXXXX-XXXXX
CODE_PRAEFIX = {ART_ANFRAGE: "ANFRAGE", ART_ANTWORT: "AKTIVIERUNG", ART_FREIGABE: "FREIGABE"}
_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # Crockford: ohne I, L, O, U
_DPAPI_ENTROPIE = b"rohrlaser-geraet-1"
_CRYPTPROTECT_LOCAL_MACHINE = 0x4
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _fehler(text):
    from .lizenz import LizenzFehler
    return LizenzFehler(text)


# ------------------------------------------------------------------ Lizenzschlüssel
def _pruefzeichen(rumpf):
    return _B32[hashlib.sha256(("rl-lz|" + rumpf).encode("ascii")).digest()[0] % 32]


def schluessel_neu():
    """Neuer Lizenzschlüssel LZ-XXXXX-XXXXX-XXXXX-XXXXX (19 Zufallszeichen = 95 Bit + 1 Prüfzeichen)."""
    rumpf = "".join(secrets.choice(_B32) for _ in range(19))
    roh = rumpf + _pruefzeichen(rumpf)
    return PRAEFIX + "-" + "-".join(roh[i:i + 5] for i in range(0, 20, 5))


def schluessel_normal(text):
    """Lizenzschlüssel in fester Schreibweise (groß, Verwechsler O→0, I/L→1) oder '' wenn er nicht passt."""
    t = "".join(ch for ch in str(text or "").upper() if ch.isalnum())
    if t.startswith(PRAEFIX):
        t = t[len(PRAEFIX):]
    t = t.translate(str.maketrans("OIL", "011"))
    if len(t) != 20 or any(ch not in _B32 for ch in t) or _pruefzeichen(t[:19]) != t[19]:
        return ""
    return PRAEFIX + "-" + "-".join(t[i:i + 5] for i in range(0, 20, 5))


def schluessel_pruefwert(schluessel):
    """Prüfwert des Lizenzschlüssels im Zertifikat (der Schlüssel selbst steht nicht darin)."""
    return hashlib.sha256(("rl-lizenzschluessel|" + schluessel_normal(schluessel)).encode("ascii")).hexdigest()[:32]


# ------------------------------------------------------------------ Gerätemerkmale
def _merkmal(name, wert):
    wert = str(wert or "").strip().lower()
    return hashlib.sha256(f"rl-merkmal|{name}|{wert}".encode("utf-8")).hexdigest()[:16] if wert else ""


def _registry(pfad, namen):
    import winreg
    werte = []
    for zugriff in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pfad, 0, zugriff) as k:
                for n in namen:
                    try:
                        werte.append(str(winreg.QueryValueEx(k, n)[0]))
                    except OSError:
                        pass
            break
        except OSError:
            continue
    return "|".join(werte)


def _platte_windows():
    import ctypes
    seriennr = ctypes.c_uint32(0)
    laufwerk = (os.environ.get("SystemDrive") or "C:") + "\\"
    ok = ctypes.windll.kernel32.GetVolumeInformationW(ctypes.c_wchar_p(laufwerk), None, 0, ctypes.byref(seriennr),
                                                      None, None, None, 0)
    return f"{seriennr.value:08X}" if ok else ""


def _datei(pfad):
    try:
        return Path(pfad).read_text(encoding="ascii", errors="ignore").strip()
    except OSError:
        return ""


def merkmale_roh():
    """Drei Merkmale dieses Rechners (Klartext, nur im Speicher): Windows-Kennung, Systemplatte, Hauptplatine/CPU.
    Nicht lesbare Merkmale bleiben leer."""
    from .lizenz import _machine_guid
    if sys.platform == "win32":
        try:
            platte = _platte_windows()
        except Exception:      # noqa: BLE001 – ohne Seriennummer zählen die anderen beiden
            platte = ""
        try:
            board = (_registry(r"HARDWARE\DESCRIPTION\System\BIOS",
                               ("BaseBoardManufacturer", "BaseBoardProduct", "SystemManufacturer", "SystemProductName"))
                     + "|" + _registry(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", ("ProcessorNameString",)))
        except Exception:      # noqa: BLE001
            board = ""
        return dict(guid=_machine_guid(), platte=platte, board=board.strip("|"))
    try:
        platte = str(os.stat("/").st_dev)
    except OSError:
        platte = ""
    board = "|".join(x for x in (_datei("/sys/class/dmi/id/board_vendor"), _datei("/sys/class/dmi/id/board_name"),
                                 _datei("/sys/class/dmi/id/product_name")) if x)
    return dict(guid=_machine_guid(), platte=platte, board=board)


def merkmale(roh=None):
    """Prüfwerte der drei Merkmale (je 16 Hexzeichen, '' = nicht lesbar). roh: dict wie merkmale_roh() (Tests)."""
    roh = merkmale_roh() if roh is None else roh
    return {n: _merkmal(n, roh.get(n)) for n in MERKMALE}


def merkmale_treffer(soll, ist):
    """Anzahl gleicher, nicht leerer Merkmale."""
    return sum(1 for n in MERKMALE if (soll or {}).get(n) and (soll or {}).get(n) == (ist or {}).get(n))


# ------------------------------------------------------------------ Geräteschlüssel
def _dpapi(daten, schuetzen):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b):
        puffer = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(puffer, ctypes.POINTER(ctypes.c_char))), puffer

    ein, _p1 = blob(daten)
    ent, _p2 = blob(_DPAPI_ENTROPIE)
    aus = BLOB()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    flags = _CRYPTPROTECT_UI_FORBIDDEN | (_CRYPTPROTECT_LOCAL_MACHINE if schuetzen else 0)
    if schuetzen:
        ok = crypt32.CryptProtectData(ctypes.byref(ein), "Rohrlaser Geraet", ctypes.byref(ent), None, None, flags,
                                      ctypes.byref(aus))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(ein), None, ctypes.byref(ent), None, None, flags,
                                        ctypes.byref(aus))
    if not ok:
        raise OSError("DPAPI")
    try:
        return ctypes.string_at(aus.pbData, aus.cbData)
    finally:
        kernel32.LocalFree(aus.pbData)


def _windows(plattform=None):
    return (plattform or sys.platform) == "win32"


def geraet_erzeugen(ordner, plattform=None):
    """Neues Geräteschlüsselpaar in Lizenz/geraet.schluessel (ein vorhandenes wird ersetzt, eine alte Aktivierung
    gilt dann nicht mehr). Windows: privater Teil mit DPAPI für diesen Rechner verschlüsselt. Ergebnis: öffentlicher
    Schlüssel (Base64)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from .lizenz import _schreiben, oeffentlich_text
    privat = Ed25519PrivateKey.generate()
    roh = privat.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                               serialization.NoEncryption())
    if _windows(plattform):
        try:
            daten = dict(format=1, schutz="dpapi", wert=base64.b64encode(_dpapi(roh, True)).decode("ascii"))
        except OSError:
            raise _fehler("Der Geräteschlüssel lässt sich mit Windows nicht schützen (DPAPI).") from None
    else:                       # nur Linux/Tests: ohne Windows gibt es kein DPAPI
        daten = dict(format=1, schutz="keiner", wert=base64.b64encode(roh).decode("ascii"))
    oeffentlich = oeffentlich_text(privat)
    daten["oeffentlich"] = oeffentlich
    _schreiben(Path(ordner) / DATEI_GERAET, json.dumps(daten))
    return oeffentlich


def geraet_laden(ordner, plattform=None):
    """Privater Geräteschlüssel (Ed25519PrivateKey) oder LizenzFehler. Unter Windows nur DPAPI-geschützt: eine Datei
    von einem anderen Rechner lässt sich hier nicht entschlüsseln."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    try:
        daten = json.loads((Path(ordner) / DATEI_GERAET).read_text(encoding="utf-8"))
        wert = base64.b64decode(daten["wert"])
    except (OSError, ValueError, KeyError, TypeError):
        raise _fehler("Geräteschlüssel fehlt – bitte neu aktivieren.") from None
    if _windows(plattform):
        if daten.get("schutz") != "dpapi":
            raise _fehler("Geräteschlüssel ist nicht geschützt – bitte neu aktivieren.")
        try:
            wert = _dpapi(wert, False)
        except (OSError, AttributeError):
            raise _fehler("Geräteschlüssel gehört zu einem anderen Rechner – bitte neu aktivieren.") from None
    try:
        return Ed25519PrivateKey.from_private_bytes(wert)
    except ValueError:
        raise _fehler("Geräteschlüssel beschädigt – bitte neu aktivieren.") from None


def _geraet_signatur_gueltig(inhalt, signatur, oeffentlich):
    from .lizenz import signatur_gueltig
    return signatur_gueltig(inhalt, signatur, "G", {"G": oeffentlich})


# ------------------------------------------------------------------ Codes zum Kopieren
def als_code(daten):
    """Datei-Inhalt (dict mit inhalt.art) als Code zum Kopieren: ANFRAGE-…, AKTIVIERUNG-…, FREIGABE-…"""
    from .lizenz import kanonisch
    art = (daten.get("inhalt") or {}).get("art")
    roh = base64.b32encode(zlib.compress(kanonisch(daten), 9)).decode("ascii").rstrip("=")
    zeilen = [roh[i:i + 60] for i in range(0, len(roh), 60)]
    return CODE_PRAEFIX.get(art, "CODE") + "-" + "\n".join(zeilen)


def aus_code(text):
    """dict aus einem Code (als_code) oder aus JSON-Text; LizenzFehler bei Unlesbarem."""
    t = str(text or "").strip()
    if t.startswith("{"):
        try:
            return json.loads(t)
        except ValueError:
            raise _fehler("Der Text ist keine gültige Aktivierungsdatei.") from None
    kopf, _, rumpf = t.partition("-")
    if kopf.upper() not in CODE_PRAEFIX.values():
        raise _fehler("Unbekannter Code (erwartet ANFRAGE-…, AKTIVIERUNG-… oder FREIGABE-…).")
    rumpf = "".join(rumpf.split()).upper()
    try:
        daten = json.loads(zlib.decompress(base64.b32decode(rumpf + "=" * (-len(rumpf) % 8))))
    except (ValueError, zlib.error):
        raise _fehler("Der Code ist unvollständig oder falsch kopiert.") from None
    if not isinstance(daten, dict):
        raise _fehler("Der Code ist keine Aktivierungsdatei.")
    return daten


def lesen(quelle):
    """Pfad, Text (JSON oder Code) oder dict → dict."""
    if isinstance(quelle, dict):
        return quelle
    if isinstance(quelle, Path):
        try:
            quelle = quelle.read_text(encoding="utf-8-sig")
        except OSError as e:
            raise _fehler(f"Datei lässt sich nicht lesen: {e}") from None
    return aus_code(quelle)


def ist_format2(quelle):
    """True, wenn quelle (Pfad/Text/dict) eine Datei von Lizenz 2.0 ist (Aktivierung, Anfrage, Freigabe)."""
    try:
        d = lesen(quelle)
    except Exception:          # noqa: BLE001
        return False
    return d.get("format") == FORMAT and (d.get("inhalt") or {}).get("art") in (ART_ANTWORT, ART_ANFRAGE,
                                                                                 ART_FREIGABE, ART_ZERTIFIKAT)


# ------------------------------------------------------------------ Zertifikat
def zertifikat_pruefen(daten, schluessel=None):
    """Signiertes Lizenzzertifikat prüfen: Aufbau, Patricks Signatur, Werte. Ergebnis: Inhalt; sonst LizenzFehler."""
    from .lizenz import standard_schluessel, signatur_gueltig
    if not isinstance(daten, dict) or daten.get("format") != FORMAT or not isinstance(daten.get("inhalt"), dict):
        raise _fehler("Lizenzzertifikat fehlt oder hat ein unbekanntes Format.")
    i = daten["inhalt"]
    schluessel = standard_schluessel() if schluessel is None else schluessel
    if i.get("schluessel_id") not in schluessel:
        raise _fehler(f"Zertifikat mit unbekanntem Schlüssel {i.get('schluessel_id')!r} – bitte das Programm "
                      "aktualisieren.")
    if not signatur_gueltig(i, daten.get("signatur"), i["schluessel_id"], schluessel):
        raise _fehler("Signatur des Lizenzzertifikats ungültig: es wurde verändert.")
    if i.get("art") != ART_ZERTIFIKAT or not i.get("lizenz_nr") or i.get("typ") not in TYPEN:
        raise _fehler("Lizenzzertifikat unvollständig.")
    for feld in ("plaetze", "aktivierungen_max"):
        if not isinstance(i.get(feld), int) or i[feld] < 1:
            raise _fehler(f"Lizenzzertifikat: Feld {feld} ungültig.")
    for feld in ("gueltig_ab", "gueltig_bis", "updates_bis"):
        if i.get(feld):
            try:
                datetime.date.fromisoformat(i[feld])
            except ValueError:
                raise _fehler(f"Lizenzzertifikat: {feld} ist kein Datum.") from None
    return i


def zertifikat_inhalt(lizenz_nr, schluessel, lizenznehmer, typ, plaetze, *, firma="", kundennr="", benutzer=0,
                      reserve=1, module=None, gueltig_ab=None, gueltig_bis=None, updates_bis=None, admins=(),
                      heute=None, schluessel_id="K1", hinweis="", ersetzt=""):
    """Inhalt eines Lizenzzertifikats (zum Signieren im Lizenz-Werkzeug). gueltig_bis None = unbefristet (Kauf)."""
    if typ not in TYPEN:
        raise ValueError(f"Typ {typ!r} unbekannt")
    heute = heute or datetime.date.today()
    plaetze = 1 if typ == "einzelplatz" else int(plaetze)
    d = dict(art=ART_ZERTIFIKAT, lizenz_nr=lizenz_nr, schluessel_pruef=schluessel_pruefwert(schluessel),
             lizenznehmer=lizenznehmer, firma=firma or "", kundennr=kundennr or "", typ=typ, plaetze=plaetze,
             benutzer=int(benutzer or 0), aktivierungen_max=plaetze + max(0, int(reserve)),
             module=list(module or ["alle"]), ausgestellt=heute.isoformat(),
             gueltig_ab=(gueltig_ab or heute).isoformat(), gueltig_bis=gueltig_bis.isoformat() if gueltig_bis else None,
             updates_bis=updates_bis.isoformat() if updates_bis else None, admins=list(admins),
             schluessel_id=schluessel_id, hinweis=hinweis or "")
    if ersetzt:
        d["ersetzt"] = ersetzt
    return d


# ------------------------------------------------------------------ Anfrage (Rechner)
def anfrage_erstellen(ordner, schluessel_text, name="", jetzt=None, roh=None, plattform=None):
    """Aktivierungsanfrage für diesen Rechner: Geräteschlüsselpaar (vorhandenes oder neues), Merkmale, mit dem Geräteschlüssel signiert.
    Ergebnis: dict {format, inhalt, geraet_signatur}. LizenzFehler bei falschem Lizenzschlüssel."""
    from .lizenz import rechner_id, signieren
    normal = schluessel_normal(schluessel_text)
    if not normal:
        raise _fehler("Der Lizenzschlüssel ist unvollständig oder hat einen Tippfehler (Form LZ-XXXXX-XXXXX-XXXXX-"
                      "XXXXX).")
    jetzt = jetzt or datetime.datetime.now()
    from .lizenz import LizenzFehler, oeffentlich_text
    try:                        # vorhandenen Geräteschlüssel behalten: eine laufende Aktivierung bleibt gültig
        privat = geraet_laden(ordner, plattform)
    except LizenzFehler:
        geraet_erzeugen(ordner, plattform)
        privat = geraet_laden(ordner, plattform)
    oeffentlich = oeffentlich_text(privat)
    guid = (roh or {}).get("guid") if roh is not None else None
    inhalt = dict(art=ART_ANFRAGE, lizenzschluessel=normal, geraet=oeffentlich, merkmale=merkmale(roh),
                  rechner_id=rechner_id(guid) if roh is not None else rechner_id(),
                  name=name or os.environ.get("COMPUTERNAME", "") or "", erstellt=jetzt.isoformat(timespec="seconds"),
                  zufall=secrets.token_hex(8))
    return dict(format=FORMAT, inhalt=inhalt, geraet_signatur=signieren(inhalt, privat))


def anfrage_pruefen(quelle):
    """Anfrage lesen und die Gerätesignatur prüfen (Lizenz-Werkzeug). Ergebnis: Inhalt; sonst LizenzFehler."""
    d = lesen(quelle)
    i = d.get("inhalt") if isinstance(d, dict) else None
    if d.get("format") != FORMAT or not isinstance(i, dict) or i.get("art") != ART_ANFRAGE:
        raise _fehler("Das ist keine Aktivierungsanfrage.")
    if not schluessel_normal(i.get("lizenzschluessel")):
        raise _fehler("Lizenzschlüssel in der Anfrage ungültig.")
    if not i.get("geraet") or not _geraet_signatur_gueltig(i, d.get("geraet_signatur"), i["geraet"]):
        raise _fehler("Anfrage verändert (Gerätesignatur passt nicht).")
    return i


# ------------------------------------------------------------------ Antwort (Lizenz-Werkzeug)
def antwort_erstellen(anfrage, zertifikat, aktivierung_id, privat, schluessel_id, heute=None):
    """Aktivierungsantwort: bindet das signierte Zertifikat an den Geräteschlüssel der Anfrage."""
    from .lizenz import signieren
    heute = heute or datetime.date.today()
    inhalt = dict(art=ART_ANTWORT, aktivierung_id=aktivierung_id, lizenz_nr=zertifikat["inhalt"]["lizenz_nr"],
                  geraet=anfrage["geraet"], merkmale=anfrage["merkmale"], rechner_id=anfrage.get("rechner_id", ""),
                  name=anfrage.get("name", ""), ausgestellt=heute.isoformat(), zertifikat=zertifikat,
                  schluessel_id=schluessel_id)
    return dict(format=FORMAT, inhalt=inhalt, signatur=signieren(inhalt, privat))


def antwort_pruefen(quelle, schluessel=None):
    """Signatur der Antwort und des enthaltenen Zertifikats prüfen. Ergebnis: (Antwort-Inhalt, Zertifikat-Inhalt)."""
    from .lizenz import signatur_gueltig, standard_schluessel
    d = lesen(quelle)
    i = d.get("inhalt") if isinstance(d, dict) else None
    if d.get("format") != FORMAT or not isinstance(i, dict) or i.get("art") != ART_ANTWORT:
        raise _fehler("Das ist keine Aktivierungsantwort.")
    schluessel = standard_schluessel() if schluessel is None else schluessel
    if i.get("schluessel_id") not in schluessel:
        raise _fehler(f"Aktivierung mit unbekanntem Schlüssel {i.get('schluessel_id')!r} – bitte das Programm "
                      "aktualisieren.")
    if not signatur_gueltig(i, d.get("signatur"), i["schluessel_id"], schluessel):
        raise _fehler("Signatur der Aktivierung ungültig: sie wurde verändert oder stammt nicht von Patrick.")
    z = zertifikat_pruefen(i.get("zertifikat"), schluessel)
    if z["lizenz_nr"] != i.get("lizenz_nr") or not i.get("aktivierung_id") or not i.get("geraet"):
        raise _fehler("Aktivierung unvollständig.")
    return i, z


def _geraet_passt(antwort, ordner, plattform=None, ist_merkmale=None):
    """Privater Geräteschlüssel passt zur Aktivierung (Probe-Signatur) und genug Merkmale stimmen; sonst LizenzFehler."""
    from .lizenz import oeffentlich_text
    privat = geraet_laden(ordner, plattform)
    if oeffentlich_text(privat) != antwort["geraet"]:
        raise _fehler("Diese Aktivierung gehört zu einem anderen Rechner oder einer früheren Anfrage.")
    probe = dict(probe=secrets.token_hex(16))
    from .lizenz import signieren
    if not _geraet_signatur_gueltig(probe, signieren(probe, privat), antwort["geraet"]):
        raise _fehler("Geräteschlüssel defekt – bitte neu aktivieren.")
    ist = merkmale() if ist_merkmale is None else ist_merkmale
    if merkmale_treffer(antwort.get("merkmale"), ist) < MERKMALE_MIN:
        raise _fehler("Dieser Rechner passt nicht zur Aktivierung (Hardware oder Windows geändert) – bitte neu "
                      "aktivieren.")


def antwort_laden(ordner, quelle, schluessel=None, plattform=None, ist_merkmale=None, heute=None):
    """Aktivierungsantwort übernehmen: erst ganz prüfen (auch gegen den Geräteschlüssel dieses Rechners), dann als
    Lizenz/aktivierung.lizenz speichern (die bisherige kommt nach alt/). Ergebnis: Inhalt für lizenz.ermitteln."""
    import shutil

    from .lizenz import ALT, _schreiben
    d = lesen(quelle)
    antwort, zert = antwort_pruefen(d, schluessel)
    _geraet_passt(antwort, ordner, plattform, ist_merkmale)
    bis = zert.get("gueltig_bis")
    if bis and (heute or datetime.date.today()) > datetime.date.fromisoformat(bis) + datetime.timedelta(days=14):
        raise _fehler(f"Diese Lizenz ist schon am {datetime.date.fromisoformat(bis):%d.%m.%Y} abgelaufen.")
    o = Path(ordner)
    vorher = o / DATEI_AKTIVIERUNG
    if vorher.is_file():
        (o / ALT).mkdir(parents=True, exist_ok=True)
        shutil.copy2(vorher, o / ALT / f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}_{DATEI_AKTIVIERUNG}")
    _schreiben(vorher, json.dumps(d, indent=1, ensure_ascii=False))
    return inhalt_fuer_zustand(antwort, zert)


def inhalt_fuer_zustand(antwort, zert):
    """Inhalt im Aufbau einer Lizenzdatei (lizenz.ermitteln): Lizenz-ID = Lizenznummer, Art benutzer."""
    return dict(lizenz_id=zert["lizenz_nr"], art="benutzer", inhaber=zert.get("lizenznehmer", ""),
                firma=zert.get("firma", ""), ausgestellt=zert.get("ausgestellt"), gueltig_ab=zert.get("gueltig_ab"),
                gueltig_bis=zert.get("gueltig_bis"), updates_bis=zert.get("updates_bis"), rechner=[],
                funktionen=list(zert.get("module") or ["alle"]), test=False, schluessel_id=zert.get("schluessel_id"),
                hinweis=zert.get("hinweis", ""), typ=zert["typ"], plaetze=zert["plaetze"],
                benutzer=zert.get("benutzer", 0), aktivierung_id=antwort["aktivierung_id"],
                aktiviert_am=antwort.get("ausgestellt"), admins=list(zert.get("admins") or []), version=2)


def vorhanden(ordner):
    return (Path(ordner) / DATEI_AKTIVIERUNG).is_file()


def pruefen(ordner, schluessel=None, plattform=None, ist_merkmale=None):
    """Gespeicherte Aktivierung dieses Rechners vollständig prüfen (Start und jede Lizenzprüfung). Ergebnis: Inhalt
    für lizenz.ermitteln; sonst LizenzFehler mit Grund."""
    antwort, zert = antwort_pruefen(Path(ordner) / DATEI_AKTIVIERUNG, schluessel)
    _geraet_passt(antwort, ordner, plattform, ist_merkmale)
    return inhalt_fuer_zustand(antwort, zert)


# ------------------------------------------------------------------ Platz freigeben
def freigabe_erstellen(ordner, schluessel=None, plattform=None, jetzt=None):
    """Platz freigeben: Freigabebeleg mit dem Geräteschlüssel signieren, danach Aktivierung und Geräteschlüssel nach
    alt/ bzw. löschen. Der Beleg geht an Patrick (Lizenz-Werkzeug „freigeben“). Ergebnis: Beleg (dict)."""
    from .lizenz import ALT, signieren
    o = Path(ordner)
    antwort, _ = antwort_pruefen(o / DATEI_AKTIVIERUNG, schluessel)
    privat = geraet_laden(o, plattform)
    jetzt = jetzt or datetime.datetime.now()
    inhalt = dict(art=ART_FREIGABE, aktivierung_id=antwort["aktivierung_id"], lizenz_nr=antwort["lizenz_nr"],
                  geraet=antwort["geraet"], erstellt=jetzt.isoformat(timespec="seconds"))
    beleg = dict(format=FORMAT, inhalt=inhalt, geraet_signatur=signieren(inhalt, privat))
    (o / ALT).mkdir(parents=True, exist_ok=True)
    stempel = f"{jetzt:%Y-%m-%d_%H%M%S}"
    os.replace(o / DATEI_AKTIVIERUNG, o / ALT / f"{stempel}_freigegeben_{DATEI_AKTIVIERUNG}")
    (o / ALT / f"{stempel}_freigabe.json").write_text(json.dumps(beleg, indent=1), encoding="utf-8")
    try:
        (o / DATEI_GERAET).unlink()
    except OSError:
        pass
    return beleg


def freigabe_pruefen(quelle, geraet_oeffentlich=None):
    """Freigabebeleg prüfen (Lizenz-Werkzeug): Gerätesignatur mit dem Geräteschlüssel der Aktivierung. Inhalt."""
    d = lesen(quelle)
    i = d.get("inhalt") if isinstance(d, dict) else None
    if d.get("format") != FORMAT or not isinstance(i, dict) or i.get("art") != ART_FREIGABE:
        raise _fehler("Das ist kein Freigabebeleg.")
    oeff = geraet_oeffentlich or i.get("geraet")
    if i.get("geraet") != oeff or not _geraet_signatur_gueltig(i, d.get("geraet_signatur"), oeff):
        raise _fehler("Freigabebeleg verändert oder von einem anderen Gerät.")
    return i
