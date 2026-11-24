"""Passwort der Einstellungen (zugleich Admin-Passwort beim Start) als PBKDF2-Hash mit Salz statt im Klartext
(Plan „Intelligenteres Programm“ C5, Patrick 23.10.2026).

Gespeichert wird 'pbkdf2_sha256$<Runden>$<Salz hex>$<Hash hex>' (nur Standardbibliothek). Ein noch im Klartext
gespeichertes Passwort (ältere Version, geteilte Datei eines älteren Arbeitsplatzes) gilt weiter; die Datenbank stellt
es beim Öffnen auf den Hash um (Datenbank._passwort_umstellen). Leer = ohne Passwort.
"""
import hashlib
import hmac
import os

ART = "pbkdf2_sha256"
RUNDEN = 200_000


def ist_hash(wert):
    teile = str(wert or "").split("$")
    return len(teile) == 4 and teile[0] == ART and teile[1].isdigit()


def hash_bilden(text, salz=None, runden=RUNDEN):
    """Hash zum Speichern; leerer Text bleibt leer (= ohne Passwort)."""
    if not text:
        return ""
    salz = salz if salz is not None else os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", str(text).encode("utf-8"), salz, runden)
    return f"{ART}${runden}${salz.hex()}${h.hex()}"


def speicherwert(wert):
    """Wert so, wie er in die Datendatei kommt: Klartext wird zum Hash, ein Hash bleibt unverändert."""
    return wert if not wert or ist_hash(wert) else hash_bilden(wert)


def pruefen(text, gespeichert):
    """True, wenn text zum gespeicherten Passwort passt (Hash oder noch Klartext). Ohne Passwort: immer True."""
    if not gespeichert:
        return True
    text = "" if text is None else str(text)
    if not ist_hash(gespeichert):
        return hmac.compare_digest(text.encode("utf-8"), str(gespeichert).encode("utf-8"))
    _, runden, salz, soll = str(gespeichert).split("$")
    try:
        ist = hash_bilden(text, bytes.fromhex(salz), int(runden)) if text else ""
    except ValueError:
        return False
    return bool(ist) and hmac.compare_digest(ist.split("$")[3], soll)
