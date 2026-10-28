"""Anfrage-Ordner (Plan W6a, Patrick 25.10.2026, Freigabe „a a a a a“).

STEP-Dateien und Anfrageformulare aus E-Mails werden in einen Ordner gelegt (Einstellung „anfrage_ordner“, bei
mehreren Arbeitsplätzen ein gemeinsamer Ordner). Das Programm zeigt sie auf der Startseite als „Neue Anfragen“:
- ein Unterordner ist eine Anfrage (samt Unterordnern darin),
- lose Dateien direkt im Ordner gehören zusammen, solange zwischen zwei Dateien weniger als ABSTAND_MIN Minuten liegen;
  eine lose Mail mit STEP-Anhang ist immer eine Anfrage für sich.
Wer eine Anfrage öffnet, sperrt sie (Datei SPERRE mit Kürzel im Unterordner; lose Dateien kommen dazu vorher in einen
eigenen Unterordner). Nach dem Übernehmen der Positionen werden die Dateien in den Angebotsordner verschoben, ein
leerer Unterordner entfällt; bei Abbruch wird nur die Sperre wieder aufgehoben.
E-Mails (Patrick 28.10.2026): aus Outlook gezogene .msg- und .eml-Dateien gehören zur Anfrage; STEP-Dateien und
Formulare in ihren Anhängen zählen mit und werden beim Öffnen in den Unterordner ausgepackt (mail.py). Ohne Qt."""
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
MAIL = {".msg", ".eml"}     # E-Mail aus Outlook (mail.py)
BILD, BILD_MIN = FORMULAR - {".pdf"}, 30 * 1024     # Bilder aus Mails erst ab 30 KB (Scan), sonst Logo/Signatur
ZIEL_FORMULAR = "Anfrage"   # Unterordner im Angebotsordner für Formulare (STEP-Dateien: angebotsordner.STEP_ORDNER)


def _relevant(p):
    return p.is_file() and not p.name.startswith((".", "~$")) and p.suffix.lower() in STEP | FORMULAR | MAIL


_ANHAENGE = {}              # (Pfad, Größe, Änderungszeit) -> Namen der Anhänge (Ordner wird alle 30 s angesehen)


def mail_anhaenge(p):
    """Namen der Anhänge einer Mail (zwischengespeichert, solange sich die Datei nicht ändert)."""
    from . import mail
    try:
        st = p.stat()
    except OSError:
        return []
    k = (str(p), st.st_size, st.st_mtime_ns)
    if k not in _ANHAENGE:
        if len(_ANHAENGE) > 500:
            _ANHAENGE.clear()
        _ANHAENGE[k] = mail.anhang_namen(p)
    return _ANHAENGE[k]


def _hat_step(dateien):
    """STEP-Datei dabei, direkt oder als Anhang einer Mail."""
    return any(d.suffix.lower() in STEP or (d.suffix.lower() in MAIL and any(
        Path(n).suffix.lower() in STEP for n in mail_anhaenge(d))) for d in dateien)


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
    def mails(self):
        return [d for d in self.dateien if d.suffix.lower() in MAIL]

    def step_anzahl(self):
        """STEP-Dateien samt denen in Mail-Anhängen (noch nicht ausgepackt, gleiche Namen einmal)."""
        namen = {d.name.lower() for d in self.step}
        for m in self.mails:
            namen |= {n.lower() for n in mail_anhaenge(m) if Path(n).suffix.lower() in STEP}
        return len(namen)

    @property
    def schluessel(self):
        """Eindeutig je Anfrage (für Auswahl und Zusammenfassen)."""
        return str(self.ordner) if self.ordner else "|".join(map(str, self.dateien))

    def text(self):
        teile = [f"{self.step_anzahl()} STEP"] + ([f"{len(self.formulare)} Formular"] if self.formulare else []) \
            + ([f"{len(self.mails)} E-Mail"] if self.mails else [])
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
            if not _hat_step(dateien):
                continue
            if any((_zeit(d) or jetzt) > ruhig for d in dateien):
                continue
            out.append(Anfrage(e.name, e, dateien, kunde_aus_ordner(kunden, dateien) if kunden else None,
                               sperre_lesen(e, jetzt)))
        elif _relevant(e) and (_zeit(e) or jetzt) <= ruhig:
            lose.append(e)
    lose.sort(key=lambda d: _zeit(d) or jetzt)
    einzeln = [[d] for d in lose if d.suffix.lower() in MAIL and _hat_step([d])]   # Mail mit STEP: für sich
    lose = [d for d in lose if [d] not in einzeln]
    gruppen = []
    for d in lose:
        if gruppen and (_zeit(d) - _zeit(gruppen[-1][-1])) < datetime.timedelta(minutes=abstand):
            gruppen[-1].append(d)
        else:
            gruppen.append([d])
    for g in gruppen + einzeln:
        if not _hat_step(g):
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


def auspacken(anfrage):
    """STEP-Dateien und Formulare aus den Anhängen der Mails in den Unterordner der (gesperrten) Anfrage legen. Liegt
    eine gleiche Datei schon dort (zweites Öffnen nach Abbruch), wird sie nicht doppelt angelegt. Ergebnis: die Anfrage
    mit den neuen Dateien. OSError: nicht möglich."""
    from . import mail
    if not anfrage.ordner or not anfrage.mails:
        return anfrage
    neu = []
    for m in anfrage.mails:
        gelesen = mail.lesen(m)
        for name, daten in (gelesen.anhaenge if gelesen else ()):
            endung = Path(name).suffix.lower()
            if endung not in STEP | FORMULAR or (endung in BILD and len(daten) < BILD_MIN):
                continue            # kleine Bilder: Logo der Signatur, kein Formular
            ziel = anfrage.ordner / name
            vorhanden = [p for p in [ziel] + list(anfrage.ordner.glob(f"{ziel.stem} (*){ziel.suffix}"))
                         if p.is_file() and p.stat().st_size == len(daten) and p.read_bytes() == daten]
            if vorhanden:
                continue
            ziel = _frei(ziel)
            ziel.write_bytes(daten)
            neu.append(ziel)
    if not neu:
        return anfrage
    return Anfrage(anfrage.name, anfrage.ordner, anfrage.dateien + neu, anfrage.kunde, anfrage.gesperrt)


def umbenennen(anfrage, name):
    """Unterordner der (gesperrten) Anfrage umbenennen, z. B. 'Kunde – Anfragenummer' aus dem Formular (W6b).
    Gleicher Name schon da: 'Name (2)'. Ergebnis: die Anfrage mit neuen Pfaden. OSError: nicht möglich."""
    if not anfrage.ordner or not name or anfrage.ordner.name == name:
        return anfrage
    neu = _frei(anfrage.ordner.with_name(name))
    alt = anfrage.ordner
    alt.rename(neu)
    a = Anfrage(neu.name, neu, [neu / d.relative_to(alt) for d in anfrage.dateien], anfrage.kunde, anfrage.gesperrt)
    return a


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
        unter = step_ordner if d.suffix.lower() in STEP else ZIEL_FORMULAR     # Mails zu den Formularen
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


def werte(db, gelesen, mails, ordner_kunde=None):
    """Was Formulare und E-Mails einer Anfrage vorbelegen (W6b/W6c, Mail 28.10.2026, Freigabe F1-F4 a). gelesen =
    gelesene Formulare (dict text/ocr/unsicher), mails = mail.Mail. Kunde: Absenderadresse der Mail (F1), sonst Name im
    Text, sonst ordner_kunde; Anfrage-Nr. aus Formular, Betreff oder Text; Wunschtermin als Lieferzeit (F2); interne
    Bemerkung (F3); der Mailtext geht als werkstoff_text an den Import (F4) und mit den Formularen in die Stückzahlen.
    Ergebnis (Kundennummer oder None, Anfrage-Nr. oder None, weitere Werte für neu_aus_step)."""
    from . import formular, mail
    gelesen = list(gelesen) + [dict(text=m.volltext(), ocr=False, unsicher=set(), mail=True) for m in mails]
    if not gelesen:
        return ordner_kunde, None, {}
    kunden = db.zeilen("kunden")
    e = formular.auswerten("\n".join(g["text"] for g in gelesen), kunden, eigene=[db.einstellung("briefkopf_1") or ""])
    kunde_mail, hinweis = None, []
    domains = mail.eigene_domains([db.einstellung(n) for n in ("briefkopf_1", "briefkopf_2", "briefkopf_3",
                                                               "briefkopf_4", "benutzer_email")])
    for m in mails:
        kunde_mail, wie = mail.kunde(m, kunden, domains)
        if kunde_mail:
            hinweis.append(f"Kunde {kunde_text(kunden, kunde_mail)} ({wie})")
            break
    kunde = kunde_mail or e["kunde"] or ordner_kunde
    weitere, kopf = dict(formulare=gelesen), {}
    if e["nummer"]:
        kopf["kundenreferenz"] = e["nummer"]
    if kunde:
        weitere["vorschlag"] = kunde
    if mails:
        text = "\n".join(m.volltext() for m in mails)
        kopf["bemerkung"] = "; ".join(mail.bemerkung(m) for m in mails)
        art, wert, satz = mail.termin(text)
        if art:
            from .angebot import lieferzeit_text
            kopf.update(lieferzeit_art=art, lieferzeit_wert=wert)
            hinweis.append(f"{lieferzeit_text(kopf).rstrip('.')} (aus „{satz[:60]}“)")
        weitere.update(werkstoff_text=text, hinweis=hinweis)
    if kopf:
        weitere["kopf"] = kopf
    return kunde, e["nummer"], weitere


def mails_neben(pfade):
    """E-Mails (.msg/.eml) unter den gezogenen Dateien und Ordnern (Ordner samt Unterordnern)."""
    out = []
    for p in map(Path, pfade or ()):
        try:
            kandidaten = sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
        except OSError:
            continue
        out += [x for x in kandidaten if x.suffix.lower() in MAIL and not x.name.startswith(("~$", "."))
                and x not in out]
    return out


def neben_auspacken(mail_pfad):
    """STEP-Anhänge einer Mail neben die Mail legen (Kundenordner gezogen), gleiche Dateien nicht doppelt. Ergebnis:
    [Pfade der STEP-Dateien aus der Mail]."""
    a = auspacken(Anfrage(mail_pfad.parent.name, mail_pfad.parent, [mail_pfad]))
    namen = {n.lower() for n in mail_anhaenge(mail_pfad) if Path(n).suffix.lower() in STEP}
    return [d for d in a.step] + [d for d in mail_pfad.parent.iterdir() if d.name.lower() in namen
                                  and d not in a.step]


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
