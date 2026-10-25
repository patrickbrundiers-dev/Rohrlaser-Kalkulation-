"""Anfrage-Ordner (Plan W6a, Patrick 25.10.2026, Freigabe „a a a a a“).

STEP-Dateien und Anfrageformulare aus E-Mails werden in einen Ordner gelegt (Einstellung „anfrage_ordner“, bei
mehreren Arbeitsplätzen ein gemeinsamer Ordner). Das Programm zeigt sie auf der Startseite als „Neue Anfragen“:
- ein Unterordner ist eine Anfrage (samt Unterordnern darin),
- lose Dateien direkt im Ordner gehören zusammen, solange zwischen zwei Dateien weniger als ABSTAND_MIN Minuten liegen.
Wer eine Anfrage öffnet, sperrt sie (Datei SPERRE mit Kürzel im Unterordner; lose Dateien kommen dazu vorher in einen
eigenen Unterordner). Nach dem Übernehmen der Positionen werden die Dateien in den Angebotsordner verschoben, ein
leerer Unterordner entfällt; bei Abbruch wird nur die Sperre wieder aufgehoben. Ohne Qt."""
import datetime
import shutil
from pathlib import Path

EINSTELLUNG = "anfrage_ordner"
ABSTAND_MIN = 10            # Minuten: lose Dateien mit kleinerem Abstand sind eine Anfrage
RUHE_S = 15                 # Sekunden: jüngere Dateien werden evtl. noch geschrieben (Kopieren aus der E-Mail)
SPERRE = ".in_bearbeitung"  # Datei im Unterordner: Kürzel und Zeit des Bearbeiters
SPERRE_STUNDEN = 12         # ältere Sperren gelten als vergessen (Programm abgestürzt)
STEP = {".step", ".stp"}
FORMULAR = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}     # Anfrageformulare (gelesen ab W6b/W6c)
ZIEL_FORMULAR = "Anfrage"   # Unterordner im Angebotsordner für Formulare (STEP-Dateien: angebotsordner.STEP_ORDNER)


def _relevant(p):
    return p.is_file() and not p.name.startswith((".", "~$")) and p.suffix.lower() in STEP | FORMULAR


def _zeit(p):
    try:
        return datetime.datetime.fromtimestamp(p.stat().st_mtime)
    except OSError:
        return None


class Anfrage:
    """Eine Anfrage im Ordner: name (Anzeige), ordner (Unterordner oder None bei losen Dateien), dateien [Path],
    zeit (jüngste Datei), kunde (Kundennummer oder None), gesperrt (Kürzel oder None)."""

    def __init__(self, name, ordner, dateien, kunde=None, gesperrt=None):
        self.name, self.ordner, self.dateien = name, ordner, sorted(dateien)
        self.kunde, self.gesperrt = kunde, gesperrt
        zeiten = [z for z in map(_zeit, self.dateien) if z]
        self.zeit = max(zeiten) if zeiten else None

    @property
    def step(self):
        return [d for d in self.dateien if d.suffix.lower() in STEP]

    @property
    def formulare(self):
        return [d for d in self.dateien if d.suffix.lower() in FORMULAR]

    @property
    def schluessel(self):
        """Eindeutig je Anfrage (für Auswahl und Zusammenfassen)."""
        return str(self.ordner) if self.ordner else "|".join(map(str, self.dateien))

    def text(self):
        teile = [f"{len(self.step)} STEP"] + ([f"{len(self.formulare)} Formular"] if self.formulare else [])
        z = f" · {self.zeit.strftime('%d.%m. %H:%M')}" if self.zeit else ""
        return f"{self.name} ({', '.join(teile)}){z}" + (f" · in Bearbeitung: {self.gesperrt}" if self.gesperrt else "")

    def __repr__(self):
        return f"Anfrage({self.name!r}, {len(self.dateien)} Dateien)"


def sperre_lesen(ordner, jetzt=None):
    """Kürzel der Sperre im Unterordner oder None (keine oder älter als SPERRE_STUNDEN)."""
    if not ordner:
        return None
    s = Path(ordner) / SPERRE
    try:
        text = s.read_text(encoding="utf-8").strip()
        alt = (jetzt or datetime.datetime.now()) - datetime.datetime.fromtimestamp(s.stat().st_mtime)
    except OSError:
        return None
    if alt > datetime.timedelta(hours=SPERRE_STUNDEN):
        return None
    return text.split("|")[0].strip() or "?"


def suchen(ordner, kunden=(), jetzt=None, abstand=ABSTAND_MIN):
    """Anfragen im Ordner, älteste zuerst. kunden = Zeilen der Kundentabelle (für den Kunden aus dem Ordnernamen).
    Anfragen ohne STEP-Datei und Dateien, die gerade noch geschrieben werden, fehlen."""
    from .step_neu import kunde_aus_ordner
    jetzt = jetzt or datetime.datetime.now()
    wurzel = Path(ordner) if ordner else None
    if not wurzel or not wurzel.is_dir():
        return []
    ruhig = jetzt - datetime.timedelta(seconds=RUHE_S)
    out = []
    try:
        eintraege = sorted(wurzel.iterdir())
    except OSError:
        return []
    lose = []
    for e in eintraege:
        if e.name.startswith((".", "~$")):
            continue
        if e.is_dir():
            try:
                dateien = [d for d in e.rglob("*") if _relevant(d)]
            except OSError:
                continue
            if not any(d.suffix.lower() in STEP for d in dateien):
                continue
            if any((_zeit(d) or jetzt) > ruhig for d in dateien):
                continue
            out.append(Anfrage(e.name, e, dateien, kunde_aus_ordner(kunden, dateien) if kunden else None,
                               sperre_lesen(e, jetzt)))
        elif _relevant(e) and (_zeit(e) or jetzt) <= ruhig:
            lose.append(e)
    lose.sort(key=lambda d: _zeit(d) or jetzt)
    gruppen = []
    for d in lose:
        if gruppen and (_zeit(d) - _zeit(gruppen[-1][-1])) < datetime.timedelta(minutes=abstand):
            gruppen[-1].append(d)
        else:
            gruppen.append([d])
    for g in gruppen:
        if not any(d.suffix.lower() in STEP for d in g):
            continue
        name = g[0].stem if len(g) == 1 else f"{len(g)} Dateien vom {_zeit(g[0]).strftime('%d.%m. %H:%M')}"
        out.append(Anfrage(name, None, g, kunde_aus_ordner(kunden, g) if kunden else None))
    return sorted(out, key=lambda a: a.zeit or jetzt)


def gleicher_kunde(anfragen):
    """{Kundennummer: [Anfragen]} für Kunden mit mehr als einer offenen (nicht gesperrten) Anfrage."""
    je = {}
    for a in anfragen:
        if a.kunde and not a.gesperrt:
            je.setdefault(str(a.kunde), []).append(a)
    return {k: v for k, v in je.items() if len(v) > 1}


def _frei(ziel):
    """ziel, sonst 'Name (2)', 'Name (3)' … (Datei oder Ordner)."""
    ziel, i = Path(ziel), 1
    neu = ziel
    while neu.exists():
        i += 1
        neu = ziel.with_name(f"{ziel.stem} ({i}){ziel.suffix}") if ziel.suffix else ziel.with_name(f"{ziel.name} ({i})")
    return neu


def _gleich(a, b):
    from .angebotsordner import _gleich as gleich
    return Path(b).exists() and gleich(Path(a), Path(b))


def sperren(anfrage, wurzel, kuerzel, jetzt=None):
    """Anfrage für diesen Arbeitsplatz sperren. Lose Dateien kommen vorher in einen eigenen Unterordner
    ('Anfrage 2026-10-25 20-13'). Ergebnis: die Anfrage (mit ordner). OSError: nicht möglich."""
    jetzt = jetzt or datetime.datetime.now()
    if anfrage.ordner is None:
        o = _frei(Path(wurzel) / f"Anfrage {(anfrage.zeit or jetzt).strftime('%Y-%m-%d %H-%M')}")
        o.mkdir(parents=True)
        neu = []
        for d in anfrage.dateien:
            z = _frei(o / d.name)
            shutil.move(str(d), str(z))
            neu.append(z)
        anfrage = Anfrage(o.name, o, neu, anfrage.kunde)
    (anfrage.ordner / SPERRE).write_text(f"{kuerzel or '?'}|{jetzt.isoformat(timespec='seconds')}", encoding="utf-8")
    anfrage.gesperrt = kuerzel or "?"
    return anfrage


def freigeben(anfrage):
    """Sperre aufheben (Import abgebrochen); die Dateien bleiben liegen."""
    if anfrage.ordner:
        try:
            (anfrage.ordner / SPERRE).unlink()
        except OSError:
            pass
    anfrage.gesperrt = None


def verschieben(anfrage, ziel, step_ordner="STEP"):
    """Dateien der Anfrage in den Angebotsordner ziel verschieben: STEP nach ziel/step_ordner, Formulare nach
    ziel/ZIEL_FORMULAR; danach den leeren Unterordner (mit Sperre) löschen. Gleicher Name: 'Name (2).stp'.
    Ergebnis: (Anzahl verschoben, [Fehlermeldungen])."""
    ziel = Path(ziel)
    n, fehler = 0, []
    for d in anfrage.dateien:
        unter = step_ordner if d.suffix.lower() in STEP else ZIEL_FORMULAR
        try:
            (ziel / unter).mkdir(parents=True, exist_ok=True)
            if _gleich(d, ziel / unter / d.name):      # schon kopiert (Häkchen „STEP-Dateien … kopieren“)
                d.unlink()
            else:
                shutil.move(str(d), str(_frei(ziel / unter / d.name)))
            n += 1
        except OSError as e:
            fehler.append(f"{d.name}: {e}")
    if anfrage.ordner and not fehler:
        try:
            (anfrage.ordner / SPERRE).unlink(missing_ok=True)
            for o in sorted((p for p in anfrage.ordner.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
                if not any(o.iterdir()):
                    o.rmdir()
            if not any(anfrage.ordner.iterdir()):
                anfrage.ordner.rmdir()
        except OSError:
            pass            # andere Dateien im Ordner (z. B. E-Mail): Ordner bleibt
    return n, fehler


def ordner_name(kunde, anfragenummer):
    """Unterordner 'Kunde – Anfragenummer' (W6b, aus dem Anfrageformular)."""
    from .angebotsordner import sauber
    return sauber(" – ".join(t for t in (str(kunde or "").strip(), str(anfragenummer or "").strip()) if t)) or "Anfrage"


def stand(anfragen):
    """Kurzer Vergleichswert, ob sich die Liste geändert hat (Startseite nur dann neu zeichnen)."""
    return tuple((a.schluessel, a.gesperrt, len(a.dateien)) for a in anfragen)


def kunde_text(kunden, nr):
    for k in kunden or ():
        if str(k.get("kundennr")) == str(nr):
            return str(k.get("name") or nr)
    return str(nr or "")
