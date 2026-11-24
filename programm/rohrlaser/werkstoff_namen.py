"""Werkstoff-Gleichwertigkeiten (Roadmap Kalkulation, Phase 1, MAT-015; Freigabe Patrick 12.11.2026).

Eine gemeinsame Liste gleichwertiger Werkstoffnamen (1.4301 = X5CrNi18-10 = AISI 304 = V2A) für die Erkennung aus
Mails, Anfrageformularen, Stücklisten, Zeichnungen und STEP-Dateien. Steht in der Anfrage ein anderer Name als in den
Stammdaten (Werkstoff-ID, Werkstoff, Werkstoff-Nr.), findet das Programm den Werkstoff trotzdem, aber nur, wenn genau
einer passt; sonst bleibt es bei der Rückfrage wie bisher. Eigene Gruppen kommen aus der Einstellung
„werkstoff_gleichnamen“ (Gruppen mit ; getrennt, Namen einer Gruppe mit =), leer = nur die eingebaute Liste.
Ohne Qt."""
import re

# allgemein übliche Zuordnungen (EN 10088, EN 10025/10219, EN 573); V4A wie bisher 1.4404
EINGEBAUT = (
    ("1.4301", "X5CrNi18-10", "AISI 304", "V2A"),
    ("1.4307", "X2CrNi18-9", "AISI 304L"),
    ("1.4404", "X2CrNiMo17-12-2", "AISI 316L", "V4A"),
    ("1.4571", "X6CrNiMoTi17-12-2", "AISI 316Ti"),
    ("1.4541", "X6CrNiTi18-10", "AISI 321"),
    ("1.4016", "X6Cr17", "AISI 430"),
    ("1.4509", "X2CrTiNb18", "AISI 441"),
    ("1.4512", "X2CrTi12", "AISI 409"),
    ("1.0038", "S235JR", "St37-2"),
    ("1.0039", "S235JRH"),
    ("1.0570", "S355J2+N", "S355J2G3", "St52-3"),
    ("1.0576", "S355J2H"),
    ("3.3206", "EN AW-6060", "AlMgSi0,5"),
    ("3.2315", "EN AW-6082", "AlSi1MgMn"),
    ("3.3535", "EN AW-5754", "AlMg3"),
)
_EIGENE = ()


def norm(t):
    """Vergleichsform: Kleinbuchstaben, nur Buchstaben, Ziffern und Punkt (wie die Mail-Erkennung)."""
    return re.sub(r"[^0-9a-z.]+", "", str(t or "").lower())


def gruppen_aus_text(text):
    """'1.4301 = V2A; 1.4404 = V4A' -> ((…), (…)); Gruppen mit weniger als zwei Namen fallen weg."""
    out = []
    for g in re.split(r"[;\n]+", str(text or "")):
        namen = tuple(n.strip() for n in g.split("=") if n.strip())
        if len(namen) >= 2:
            out.append(namen)
    return tuple(out)


def eigene_setzen(text):
    """Eigene Gruppen aus der Einstellung werkstoff_gleichnamen (Datenbank beim Öffnen und beim Speichern)."""
    global _EIGENE
    _EIGENE = gruppen_aus_text(text)


def eigene_namen():
    """Alle Namen der eigenen Gruppen (für die Suche im Mailtext)."""
    return [n for g in _EIGENE for n in g]


def gleichnamen(name):
    """Alle gleichwertigen Namen (Vergleichsform) zu name, ohne name selbst; leer, wenn er in keiner Gruppe steht."""
    n = norm(name)
    if not n:
        return set()
    out = set()
    for g in _EIGENE + EINGEBAUT:
        formen = {norm(x) for x in g}
        if n in formen:
            out |= formen
    return out - {n, ""}


def _beginnt(n, g):
    """'enaw6060t66' beginnt mit 'enaw6060' (Zustand dahinter), aber nicht 's235' mit 's23' oder '1.43…'."""
    return len(g) >= 4 and not g.startswith("1.") and n.startswith(g) and not n[len(g):len(g) + 1].isdigit()


def passende(name, zeilen):
    """Werkstoff-IDs der Stammdaten-Zeilen, deren Werkstoff-ID, Werkstoff oder Werkstoff-Nr. einem gleichwertigen
    Namen entspricht (gleich in Vergleichsform, Zustand wie T66 dahinter erlaubt)."""
    gl = gleichnamen(name)
    if not gl:
        return []
    out = []
    for z in zeilen or ():
        namen = {norm(z.get(f)) for f in ("werkstoff_id", "werkstoff", "werkstoff_nr")} - {""}
        if (namen & gl or any(_beginnt(n, g) for n in namen for g in gl)) and z.get("werkstoff_id") not in out:
            out.append(z["werkstoff_id"])
    return out


def passende_im_text(text, zeilen):
    """Wie passende für einen ganzen Namen aus einer Datei ('Stainless Steel X2CrTiNb18'): der ganze Text, sonst
    je zwei benachbarte Wörter ('AISI 430'), sonst je Wort; der erste Treffer gilt."""
    worte = [w for w in re.split(r"[\s,;/()]+", str(text or "")) if w]
    for probe in [text] + [" ".join(worte[i:i + 2]) for i in range(len(worte) - 1)] + worte:
        p = passende(probe, zeilen)
        if p:
            return p
    return []
