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
Formulare in ihren Anhängen zählen mit und werden beim Öffnen in den Unterordner ausgepackt (mail.py).
Mehrere Mails zur selben Anfrage (Patrick 28.10.2026, F1-F4 a): Mails vom selben Absender mit derselben Anfrage-Nr.
oder demselben Betreff (ohne AW:/WG:) innerhalb von ZUSAMMEN_TAGE Tagen gehören zu einer Anfrage, auch ein Nachtrag
ohne STEP; beim Auspacken gilt bei gleichem Dateinamen die neueste Version, die ältere bleibt als 'Name (alt)'.
Gemeinsamer Ordner (Patrick 28.10.2026): ohne eigenen Anfrage-Ordner gilt der Unterordner „Anfragen“ des gemeinsamen
Ordners (ordner). Eine Anfrage lässt sich einem Kollegen zuweisen (Datei ZUGEWIESEN im Unterordner, für alle
sichtbar). Ohne Qt."""
import datetime
import os
import re
import shutil
from pathlib import Path

EINSTELLUNG = "anfrage_ordner"
ABSTAND_MIN = 10            # Minuten: lose Dateien mit kleinerem Abstand sind eine Anfrage
RUHE_S = 15                 # Sekunden: jüngere Dateien werden evtl. noch geschrieben (Kopieren aus der E-Mail)
SPERRE = ".in_bearbeitung"  # Datei im Unterordner: Kürzel und Zeit des Bearbeiters
SPERRE_STUNDEN = 12         # ältere Sperren gelten als vergessen (Programm abgestürzt)
ZUGEWIESEN = ".zugewiesen"  # Datei im Unterordner: Kürzel des Kollegen, Absender, Zeit, Notiz
STEP = {".step", ".stp"}
FORMULAR = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}     # Anfrageformulare (gelesen ab W6b/W6c)
MAIL = {".msg", ".eml"}     # E-Mail aus Outlook (mail.py)
ARCHIV = {".zip"}           # ZIP mit STEP-Dateien (Patrick 28.10.2026): wird wie eine Mail beim Öffnen ausgepackt
BEHAELTER = MAIL | ARCHIV
ZUSAMMEN_TAGE = 3           # Mails zur selben Anfrage (Anfrage-Nr. bzw. Betreff, gleicher Absender) so lange zusammen
ALT = re.compile(r" \(alt\)(?: \(\d+\))?$", re.I)     # ältere Version einer Datei aus einer früheren Mail
BILD, BILD_MIN = FORMULAR - {".pdf"}, 30 * 1024     # Bilder aus Mails erst ab 30 KB (Scan), sonst Logo/Signatur
ZIEL_FORMULAR = "Anfrage"   # Unterordner im Angebotsordner für Formulare (STEP-Dateien: angebotsordner.STEP_ORDNER)


def ordner(db):
    """Anfrage-Ordner: eingetragener Ordner, sonst „Anfragen“ im gemeinsamen Ordner (Einstellung teilen_anfragen),
    sonst None (aus)."""
    from . import teilen
    eigen = str(db.einstellung(EINSTELLUNG) or "").strip()
    if eigen:
        return Path(eigen)
    return teilen.unterordner(db, teilen.ANFRAGEN, "teilen_anfragen", anlegen=True)


def _relevant(p):
    return p.is_file() and not p.name.startswith((".", "~$")) and p.suffix.lower() in STEP | FORMULAR | BEHAELTER


_ANHAENGE = {}              # (Pfad, Größe, Änderungszeit) -> Namen der Anhänge (Ordner wird alle 30 s angesehen)


def mail_anhaenge(p):
    """Namen der Anhänge einer Mail bzw. der Dateien einer ZIP (zwischengespeichert, solange sich die Datei nicht
    ändert)."""
    from . import mail
    try:
        st = p.stat()
    except OSError:
        return []
    k = (str(p), st.st_size, st.st_mtime_ns)
    if k not in _ANHAENGE:
        if len(_ANHAENGE) > 500:
            _ANHAENGE.clear()
        _ANHAENGE[k] = [n for n, _ in _zip_dateien(p)] if p.suffix.lower() in ARCHIV else mail.anhang_namen(p)
    return _ANHAENGE[k]


def _zip_dateien(p):
    """Dateien einer ZIP [(Name, bytes)] samt ZIPs und Mails darin (mail.zip_inhalt), [] wenn nicht lesbar."""
    from . import mail
    try:
        return mail.zip_inhalt(Path(p).read_bytes())
    except OSError:
        return []


def _hat_step(dateien):
    """STEP-Datei dabei, direkt oder als Anhang einer Mail bzw. in einer ZIP."""
    return any(d.suffix.lower() in STEP or (d.suffix.lower() in BEHAELTER and any(
        Path(n).suffix.lower() in STEP for n in mail_anhaenge(d))) for d in dateien)


def _zeit(p):
    try:
        return datetime.datetime.fromtimestamp(p.stat().st_mtime)
    except OSError:
        return None


def ist_alt(p):
    """Ältere Version aus einer früheren Mail ('Teil1 (alt).step'): wird mit verschoben, aber nicht importiert."""
    return bool(ALT.search(Path(p).stem))


PRAEFIX = re.compile(r"^\s*(?:(?:AW|RE|WG|FW|FWD|TR|VS|SV|Antw(?:ort)?|Weiterleitung)\s*(?:\[\d+\])?\s*:\s*)+", re.I)
GENERISCH = {"anfrage", "angebot", "angebotsanfrage", "preisanfrage", "bitte", "um", "ihr", "ihre", "unser", "unsere",
             "neue", "neu", "zur", "zum", "für", "fuer", "info", "request", "quotation", "rfq", "inquiry", "mail", "-"}


def betreff_kern(betreff):
    """Betreff ohne AW:/WG:/RE:, klein, Leerzeichen vereinheitlicht; None bei Allerweltsbetreffs wie „Anfrage“."""
    t = re.sub(r"\s+", " ", PRAEFIX.sub("", betreff or "")).strip().lower()
    return t if set(t.replace(":", " ").split()) - GENERISCH else None


_KOPF = {}                  # (Pfad, Größe, Änderungszeit, eigene Domains) -> Kopfdaten (mail_kopf)
EIGENE = set()              # eigene Domains (eigene_domains), setzt die Anfrage-Karte vor dem Suchen


def eigene_domains(db):
    """Domains der eigenen Firma (Patrick 31.10.2026 F1 a): aus Briefkopf und Benutzer-E-Mail, dem Feld „Weitere
    eigene Domains“ (Einstellungen → Firma) und den E-Mail-Adressen aller Arbeitsplätze im gemeinsamen Ordner."""
    from . import mail
    texte = [db.einstellung(n) for n in ("briefkopf_1", "briefkopf_2", "briefkopf_3", "briefkopf_4", "benutzer_email")]
    try:
        from . import teilen
        texte += [str(v.get("email") or "") for v in teilen.mitarbeiter(db).values() if isinstance(v, dict)]
    except Exception:       # gemeinsamer Ordner nicht lesbar: dann nur die übrigen
        pass
    out = mail.eigene_domains(texte)
    for w in re.split(r"[\s,;]+", str(db.einstellung("eigene_domains") or "")):
        d = w.strip().lower().lstrip("@").rpartition("@")[2].strip(".")
        if "." in d:
            out.add(d)
    return out


def mail_kopf(p):
    """Was zum Zusammenfassen zählt: dict(nummer, betreff, absender, domain, zeit) oder None (keine Mail). Intern
    weitergeleitet (31.10.2026): Absender und Betreff der Mail des Kunden, damit ein Nachtrag direkt vom Kunden dazu
    passt; die Zeit bleibt die der Weiterleitung."""
    from . import formular, mail
    p = Path(p)
    if p.suffix.lower() not in MAIL:
        return None
    try:
        st = p.stat()
    except OSError:
        return None
    k = (str(p), st.st_size, st.st_mtime_ns, frozenset(EIGENE))
    if k not in _KOPF:
        if len(_KOPF) > 500:
            _KOPF.clear()
        m = mail.lesen(p)
        w = mail.weiterleitung(m, EIGENE) if m is not None else None
        o = w.original if w and w.original is not None and w.original.absender else m
        _KOPF[k] = None if m is None else dict(
            nummer=formular.anfragenummer(m.volltext()), betreff=betreff_kern(o.betreff), absender=o.absender,
            domain=o.domain, zeit=m.datum or datetime.datetime.fromtimestamp(st.st_mtime))
    return _KOPF[k]


def gleiche_anfrage(a, b, tage=ZUSAMMEN_TAGE):
    """Zwei Mails (mail_kopf) gehören zur selben Anfrage: höchstens tage auseinander, gleicher Absender (gleiche Firma
    bzw. bei Freemail gleiche Adresse) und gleiche Anfrage-Nr. oder gleicher Betreff."""
    from . import mail
    if not a or not b or abs(a["zeit"] - b["zeit"]) > datetime.timedelta(days=tage):
        return False
    if not a["domain"] or a["domain"] != b["domain"] or (a["domain"] in mail.FREEMAIL and a["absender"] != b["absender"]):
        return False
    return bool((a["nummer"] and a["nummer"].lower() == (b["nummer"] or "").lower())
                or (a["betreff"] and a["betreff"] == b["betreff"]))


def quell_zeit(p):
    """Zeit einer Mail (gesendet) bzw. einer Datei (geändert) für „die neueste gilt“."""
    k = mail_kopf(p)
    return k["zeit"] if k else (_zeit(Path(p)) or datetime.datetime.min)


class Anfrage:
    """Eine Anfrage im Ordner: name (Anzeige), ordner (Unterordner oder None bei losen Dateien), dateien [Path],
    zeit (jüngste Datei), kunde (Kundennummer oder None), gesperrt (Kürzel oder None)."""

    def __init__(self, name, ordner, dateien, kunde=None, gesperrt=None, zugewiesen=None):
        self.name, self.ordner, self.dateien = name, ordner, sorted(dateien)
        self.kunde, self.gesperrt = kunde, gesperrt
        self.zugewiesen = zugewiesen or {}      # {an, von, zeit, notiz} oder {}
        zeiten = [z for z in map(_zeit, self.dateien) if z]
        self.zeit = max(zeiten) if zeiten else None

    @property
    def step(self):
        return [d for d in self.dateien if d.suffix.lower() in STEP and not ist_alt(d)]

    @property
    def formulare(self):
        return [d for d in self.dateien if d.suffix.lower() in FORMULAR and not ist_alt(d)]

    @property
    def mails(self):
        return [d for d in self.dateien if d.suffix.lower() in MAIL]

    @property
    def archive(self):
        return [d for d in self.dateien if d.suffix.lower() in ARCHIV]

    def step_anzahl(self):
        """STEP-Dateien samt denen in Mail-Anhängen (noch nicht ausgepackt, gleiche Namen einmal)."""
        namen = {d.name.lower() for d in self.step}
        for m in self.mails + self.archive:
            namen |= {n.lower() for n in mail_anhaenge(m) if Path(n).suffix.lower() in STEP}
        return len(namen)

    @property
    def schluessel(self):
        """Eindeutig je Anfrage (für Auswahl und Zusammenfassen)."""
        return str(self.ordner) if self.ordner else "|".join(map(str, self.dateien))

    def text(self):
        teile = [f"{self.step_anzahl()} STEP"] + ([f"{len(self.formulare)} Formular"] if self.formulare else []) \
            + ([f"{len(self.mails)} E-Mail"] if self.mails else []) \
            + ([f"{len(self.archive)} ZIP"] if self.archive else [])
        z = f" · {self.zeit.strftime('%d.%m. %H:%M')}" if self.zeit else ""
        an = self.zugewiesen.get("an")
        notiz = self.zugewiesen.get("notiz")
        return (f"{self.name} ({', '.join(teile)}){z}" + (f" · für {an}" if an else "")
                + (f" („{notiz}“)" if an and notiz else "")
                + (f" · in Bearbeitung: {self.gesperrt}" if self.gesperrt else ""))

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


def suchen(ordner, kunden=(), jetzt=None, abstand=ABSTAND_MIN, ohne_step=None, angebote=None):
    """Anfragen im Ordner, älteste zuerst. kunden = Zeilen der Kundentabelle (für den Kunden aus dem Ordnernamen).
    Anfragen ohne STEP-Datei und Dateien, die gerade noch geschrieben werden, fehlen; ohne_step (Liste) bekommt die
    Namen der Ordner bzw. Dateien, die nur Zeichnungen/Formulare haben (Hinweis, Patrick 28.10.2026: aus Zeichnungen
    nichts automatisch anlegen). Mails zur selben Anfrage (gleiche_anfrage) kommen zusammen, auch ein Nachtrag ohne
    STEP (lose Dateien auch zu einem nicht gesperrten Unterordner). angebote = {Anfrage-Nr.: (Angebotsnummer,
    Kundennummer)}: ein Nachtrag des Kunden zu einer schon übernommenen Anfrage steht in ohne_step als
    'Mail (Nachtrag zu Angebot …)'."""
    from .step_neu import kunde_aus_ordner
    jetzt = jetzt or datetime.datetime.now()
    wurzel = Path(ordner) if ordner else None
    if not wurzel or not wurzel.is_dir():
        return []
    ruhig = jetzt - datetime.timedelta(seconds=RUHE_S)
    try:
        eintraege = sorted(wurzel.iterdir())
    except OSError:
        return []
    gruppen, lose = [], []      # gruppen: [Unterordner oder None, [Dateien], Sperre]
    for e in eintraege:
        if e.name.startswith((".", "~$")):
            continue
        if e.is_dir():
            try:
                dateien = [d for d in e.rglob("*") if _relevant(d)]
            except OSError:
                continue
            if _hat_step(dateien) and any((_zeit(d) or jetzt) > ruhig for d in dateien):
                continue
            if dateien:
                gruppen.append([e, dateien, sperre_lesen(e, jetzt)])
        elif _relevant(e) and (_zeit(e) or jetzt) <= ruhig:
            lose.append(e)
    lose.sort(key=lambda d: _zeit(d) or jetzt)
    # Mail/ZIP mit STEP für sich; eine Mail ohne STEP erst für sich (Nachtrag zu einer anderen Mail?), sonst unten zu
    # den losen Dateien aus derselben Zeit
    einzeln = [[d] for d in lose if d.suffix.lower() in BEHAELTER and (_hat_step([d]) or mail_kopf(d))]
    lose = [d for d in lose if [d] not in einzeln]
    zeitlich = []
    for d in lose:
        if zeitlich and (_zeit(d) - _zeit(zeitlich[-1][-1])) < datetime.timedelta(minutes=abstand):
            zeitlich[-1].append(d)
        else:
            zeitlich.append([d])
    gruppen += [[None, g, None] for g in einzeln]
    gruppen = _mails_zusammen(gruppen)
    zeitlich = [[None, g, None] for g in zeitlich]
    for g in list(gruppen):
        if g[0] is None and len(g[1]) == 1 and not _hat_step(g[1]) and g[1][0].suffix.lower() in MAIL:
            t = _zeit(g[1][0]) or jetzt
            nah = [z for z in zeitlich if any(abs((_zeit(d) or jetzt) - t) < datetime.timedelta(minutes=abstand)
                                              for d in z[1])]
            if nah:
                nah[0][1].append(g[1][0])
                gruppen.remove(g)
    gruppen += zeitlich
    out = []
    for o, g, gesperrt in gruppen:
        if not _hat_step(g):
            if ohne_step is not None:
                ohne_step += [o.name] if o else _ohne_step_namen(g, angebote, kunden)
            continue
        if o:
            name = o.name
        else:
            g = sorted(g, key=quell_zeit)             # Mails nach Sendezeit, älteste zuerst
            name = g[0].stem if len(g) == 1 else (f"{g[0].stem} + Nachtrag" if g[0].suffix.lower() in MAIL else
                                                  f"{len(g)} Dateien vom {_zeit(g[0]).strftime('%d.%m. %H:%M')}")
        out.append(Anfrage(name, o, g, kunde_aus_ordner(kunden, g) if kunden else None, gesperrt,
                           zuweisung_lesen(o) if o else None))
    return sorted(out, key=lambda a: a.zeit or jetzt)


def _mails_zusammen(gruppen):
    """Gruppen [Unterordner, Dateien, Sperre] zusammenlegen, deren Mails zur selben Anfrage gehören. Zwei Unterordner
    bleiben getrennt (kein Verschieben ganzer Ordner), ein gesperrter Unterordner bekommt nichts dazu."""
    koepfe = [[k for d in g[1] if (k := mail_kopf(d))] for g in gruppen]
    i = 0
    while i < len(gruppen):
        j = i + 1
        while j < len(gruppen):
            a, b = gruppen[i], gruppen[j]
            erlaubt = not (a[0] and b[0]) and not a[2] and not b[2]
            if erlaubt and any(gleiche_anfrage(x, y) for x in koepfe[i] for y in koepfe[j]):
                a[0] = a[0] or b[0]
                a[1] = a[1] + [d for d in b[1] if d not in a[1]]
                koepfe[i] += koepfe.pop(j)
                gruppen.pop(j)
                j = i + 1           # neue Mails in der Gruppe: noch einmal mit allen vergleichen
            else:
                j += 1
        i += 1
    return gruppen


def _ohne_step_namen(dateien, angebote=None, kunden=()):
    """Namen für den Hinweis „Ohne STEP“: Formulare und Mails; Mail mit Anfrage-Nr. eines vorhandenen Angebots als
    Nachtrag dazu, wenn sie vom Kunden des Angebots kommt (gleiche Firma bzw. Adresse; Kunde ohne E-Mail: nur die
    Nummer)."""
    out = []
    for d in dateien:
        if d.suffix.lower() in FORMULAR:
            out.append(d.name)
        elif d.suffix.lower() in MAIL:
            k = mail_kopf(d)
            nr = k and k["nummer"] and next((v for n, v in (angebote or {}).items()
                                             if str(n).lower() == k["nummer"].lower() and _vom_kunden(k, v[1], kunden)),
                                            None)
            out.append(f"{d.name} (Nachtrag zu Angebot {nr[0]})" if nr else d.name)
    return out


def _vom_kunden(kopf, kundennr, kunden):
    from . import mail
    adressen = [a.lower() for z in kunden or () if str(z.get("kundennr")) == str(kundennr)
                for a in mail.ADRESSE.findall(str(z.get("email") or ""))]
    if not adressen:
        return True
    return any(a == kopf["absender"] or (a.rpartition("@")[2] == kopf["domain"] and kopf["domain"] not in mail.FREEMAIL)
               for a in adressen)


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


def _in_unterordner(anfrage, wurzel, jetzt):
    """Lose Dateien in einen eigenen Unterordner ('Anfrage 2026-10-25 20-13'), ein Nachtrag (lose Mail) zu einem
    Unterordner in diesen. Ergebnis: Anfrage mit ordner."""
    o = anfrage.ordner
    draussen = [d for d in anfrage.dateien if not o or not d.is_relative_to(o)]
    if not draussen:
        return anfrage
    if o is None:
        o = _frei(Path(wurzel) / f"Anfrage {(anfrage.zeit or jetzt).strftime('%Y-%m-%d %H-%M')}")
        o.mkdir(parents=True)
    neu = [d for d in anfrage.dateien if d not in draussen]
    for d in draussen:
        z = _frei(o / d.name)
        shutil.move(str(d), str(z))
        neu.append(z)
    return Anfrage(o.name, o, neu, anfrage.kunde, anfrage.gesperrt, anfrage.zugewiesen)


def zuweisung_lesen(o):
    """Zuweisung im Unterordner: {an, von, zeit, notiz} oder {}."""
    try:
        teile = (Path(o) / ZUGEWIESEN).read_text(encoding="utf-8").split("|", 3)
    except OSError:
        return {}
    teile += [""] * (4 - len(teile))
    an = teile[0].strip()
    return dict(an=an, von=teile[1].strip(), zeit=teile[2].strip(), notiz=teile[3].strip()) if an else {}


def zuweisen(anfrage, wurzel, an, von="", notiz="", jetzt=None):
    """Anfrage einem Kollegen zuweisen (an leer = Zuweisung aufheben); lose Dateien kommen dazu in einen eigenen
    Unterordner. Alle sehen „für MK“ in der Liste. Ergebnis: die Anfrage. OSError: nicht möglich."""
    jetzt = jetzt or datetime.datetime.now()
    anfrage = _in_unterordner(anfrage, wurzel, jetzt)
    datei = anfrage.ordner / ZUGEWIESEN
    if not an:
        datei.unlink(missing_ok=True)
        anfrage.zugewiesen = {}
        return anfrage
    notiz = " ".join(str(notiz or "").split())
    datei.write_text(f"{an}|{von}|{jetzt.isoformat(timespec='seconds')}|{notiz}", encoding="utf-8")
    anfrage.zugewiesen = dict(an=an, von=von, zeit=jetzt.isoformat(timespec="seconds"), notiz=notiz)
    return anfrage


def sperren(anfrage, wurzel, kuerzel, jetzt=None):
    """Anfrage für diesen Arbeitsplatz sperren. Lose Dateien kommen vorher in einen eigenen Unterordner
    ('Anfrage 2026-10-25 20-13'); ein Nachtrag (lose Mail) zu einem Unterordner kommt in diesen. Ergebnis: die Anfrage
    (mit ordner). OSError: nicht möglich."""
    jetzt = jetzt or datetime.datetime.now()
    anfrage = _in_unterordner(anfrage, wurzel, jetzt)
    (anfrage.ordner / SPERRE).write_text(f"{kuerzel or '?'}|{jetzt.isoformat(timespec='seconds')}", encoding="utf-8")
    anfrage.gesperrt = kuerzel or "?"
    return anfrage


def auspacken(anfrage):
    """STEP-Dateien und Formulare aus den Anhängen der Mails und aus ZIP-Dateien in den Unterordner der (gesperrten)
    Anfrage legen, älteste Mail zuerst. Liegt eine gleiche Datei schon dort (zweites Öffnen nach Abbruch), wird sie
    nicht doppelt angelegt. Gleicher Name, anderer Inhalt (Patrick 28.10.2026, F4 a): die neueste Version (nach Datum
    der Mail bzw. Änderungszeit der Datei) bekommt den Namen, die ältere heißt 'Name (alt)'; die ausgepackte Datei
    bekommt dazu die Zeit ihrer Mail. Ergebnis: die Anfrage mit den neuen Dateien. OSError: nicht möglich."""
    from . import mail
    if not anfrage.ordner or not (anfrage.mails or anfrage.archive):
        return anfrage
    neu, umbenannt = [], {}
    for m in sorted(anfrage.mails + anfrage.archive, key=quell_zeit):
        gelesen = mail.lesen(m) if m.suffix.lower() in MAIL else None
        inhalt = _zip_dateien(m) if m.suffix.lower() in ARCHIV else (gelesen.anhaenge if gelesen else ())
        zeit, aus_dieser = quell_zeit(m), set()
        for name, daten in inhalt:
            endung = Path(name).suffix.lower()
            if endung not in STEP | FORMULAR or (endung in BILD and len(daten) < BILD_MIN):
                continue            # kleine Bilder: Logo der Signatur, kein Formular
            ziel = anfrage.ordner / name
            vorhanden = [p for p in [ziel] + list(anfrage.ordner.glob(f"{ziel.stem} (*){ziel.suffix}"))
                         if p.is_file() and p.stat().st_size == len(daten) and p.read_bytes() == daten]
            if vorhanden:
                continue
            if ziel.exists() and ziel not in aus_dieser:        # andere Version aus einer anderen Mail/Datei
                alt = _frei(ziel.with_name(f"{ziel.stem} (alt){ziel.suffix}"))
                if (_zeit(ziel) or datetime.datetime.min) <= zeit:
                    ziel.rename(alt)
                    umbenannt[ziel] = alt
                    neu = [alt if d == ziel else d for d in neu]
                else:
                    ziel = alt
            ziel = _frei(ziel)
            ziel.write_bytes(daten)
            if zeit > datetime.datetime(1971, 1, 1):
                os.utime(ziel, (zeit.timestamp(), zeit.timestamp()))
            aus_dieser.add(ziel)
            neu.append(ziel)
    if not neu:
        return anfrage
    dateien = [umbenannt.get(d, d) for d in anfrage.dateien]
    return Anfrage(anfrage.name, anfrage.ordner, dateien + [d for d in neu if d not in dateien], anfrage.kunde,
                   anfrage.gesperrt,
                   anfrage.zugewiesen)


def umbenennen(anfrage, name):
    """Unterordner der (gesperrten) Anfrage umbenennen, z. B. 'Kunde – Anfragenummer' aus dem Formular (W6b).
    Gleicher Name schon da: 'Name (2)'. Ergebnis: die Anfrage mit neuen Pfaden. OSError: nicht möglich."""
    if not anfrage.ordner or not name or anfrage.ordner.name == name:
        return anfrage
    neu = _frei(anfrage.ordner.with_name(name))
    alt = anfrage.ordner
    alt.rename(neu)
    a = Anfrage(neu.name, neu, [neu / d.relative_to(alt) for d in anfrage.dateien], anfrage.kunde, anfrage.gesperrt,
                anfrage.zugewiesen)
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
            (anfrage.ordner / ZUGEWIESEN).unlink(missing_ok=True)
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
    Dazu (Patrick 28.10.2026 „robuster und intelligenter“): Kunde auch über den Domainnamen (passt zum Kundennamen),
    Hinweise auf unbekannte Absender, gewünschte Staffelmengen, erwähnte Zusatzarbeiten und schon vorhandene Angebote
    mit derselben Anfrage-Nr. Ein Fehler beim Auswerten bricht das Öffnen nie ab (dann nur ohne Vorschläge).
    Ergebnis (Kundennummer oder None, Anfrage-Nr. oder None, weitere Werte für neu_aus_step)."""
    try:
        return _werte(db, gelesen, mails, ordner_kunde)
    except Exception as e:          # nie am Auswerten scheitern: Anfrage öffnet ohne Vorschläge
        weitere = dict(formulare=list(gelesen)) if gelesen else {}
        if mails:
            weitere["hinweis"] = [f"E-Mail nur teilweise ausgewertet ({type(e).__name__}) – bitte selbst prüfen"]
        return ordner_kunde, None, weitere


def _werte(db, gelesen, mails, ordner_kunde=None):
    from . import formular, mail
    formular_text = "\n".join(g["text"] for g in gelesen if g.get("text"))
    # mehrere Mails zur selben Anfrage (F3 a): die neueste gilt, andere Werte älterer Mails nur als Hinweis
    mails = sorted(mails, key=lambda m: m.datum or m.datei_zeit or datetime.datetime.min,
                   reverse=True)
    gelesen = list(gelesen) + [dict(text=m.volltext(), ocr=False, unsicher=set(), mail=True, quelle="der " + _mail_name(m, mails))
                               for m in mails]
    if not gelesen:
        return ordner_kunde, None, {}
    kunden = db.zeilen("kunden")
    eigen_name = db.einstellung("briefkopf_1") or ""
    e = formular.auswerten("\n".join(g["text"] for g in gelesen), kunden, eigene=[eigen_name])
    e["nummer"] = formular.nummer_aus([g for g in gelesen if not g.get("mail")]) or e["nummer"]   # Kopftabelle
    kunde_mail, hinweis = None, []
    domains = eigene_domains(db)
    # intern weitergeleitet (Patrick 31.10.2026): Kunde, Signatur und Anfragetext aus der Mail des Kunden darin
    weiter = {id(m): mail.weiterleitung(m, domains, eigen_name) for m in mails}
    for w in filter(None, weiter.values()):
        domains |= {mail._domain(a) for _, a, _ in w.weiterleiter if a}
    vom_kunden = [(w.original if w.original is not None else mail.Mail(datum=m.datum, betreff=m.betreff))
                  if (w := weiter[id(m)]) else m for m in mails]
    for w in filter(None, weiter.values()):
        kollege = w.weiterleiter[0][0] or w.weiterleiter[0][1] or "Kollege"
        if w.original is not None:
            o = w.original
            von = " ".join(x for x in (o.absender_name, f"<{o.absender}>" if o.absender else "") if x)
            hinweis.append(f"Intern {w.text()} – Anfrage von {von or 'unbekannt'}"
                           + (f" vom {o.datum.strftime('%d.%m.%Y')}" if o.datum else ""))
        else:
            hinweis.append(f"Intern {w.text()} – ursprünglicher Absender nicht erkennbar, Kunde bitte selbst wählen")
        if w.notiz:
            hinweis.append(f"Notiz von {kollege}: „{w.notiz[:150]}{'…' if len(w.notiz) > 150 else ''}“")
    treffer = [t for t in (mail.kunde(m, kunden, domains) for m in vom_kunden) if t[0]]
    if treffer:             # mehrere Mails: genaue Absenderadresse vor Domain
        kunde_mail, wie = next((t for t in treffer if t[1].startswith("Absender")), treffer[0])
        hinweis.append(f"Kunde {kunde_text(kunden, kunde_mail)} ({wie})")
    kunde_domain = None
    if mails and not kunde_mail and not e["kunde"]:
        for m in vom_kunden:
            kunde_domain, wie = mail.kunde_aus_domain(m, kunden, domains)
            if kunde_domain:
                hinweis.append(f"Kunde {kunde_text(kunden, kunde_domain)} ({wie}, bitte prüfen)")
                break
    kunde = kunde_mail or e["kunde"] or kunde_domain or ordner_kunde
    weitere, kopf = dict(formulare=gelesen), {}
    if not kunde:           # unbekannter Kunde: neu anlegen mit „Kunde prüfen“ (Patrick 28.10.2026)
        absender = next((m for m in vom_kunden if mail.adressen(m, domains)), None)
        daten = mail.kunde_daten(absender, formular_text, domains)
        if daten and not _eigene_firma(daten, eigen_name, domains):
            weitere["neuer_kunde"] = daten
            hinweis.append(f"Neuer Kunde „{daten['name']}“ angelegt (Bemerkung „Kunde prüfen“)")
    elif mails and not kunde_mail:
        fremd = next((a for m in vom_kunden for a in mail.adressen(m, domains)), None)
        if fremd:
            hinweis.append(f"Absender {fremd} steht bei keinem Kunden – beim Kunden unter E-Mail eintragen, dann "
                           "erkennt das Programm ihn nächstes Mal")
    if e["nummer"]:
        kopf["kundenreferenz"] = e["nummer"]
    if kunde:
        weitere["vorschlag"] = kunde
    if mails:
        kopf["bemerkung"] = "; ".join(mail.bemerkung(m, weiter[id(m)]) for m in mails)
    # Mail und Anfrageformular gleich auswerten (Patrick 28.10.2026): erst die Mails (neueste zuerst), dann das Formular;
    # weitergeleitet: erst die Notiz des Kollegen (neuester Stand, F2 a), dann die Mail des Kunden
    benannt = []
    for m in mails:
        w = weiter[id(m)]
        if not w:
            benannt.append((_mail_name(m, mails), m.volltext()))
            continue
        if w.notiz:
            benannt.append((f"Notiz von {w.weiterleiter[0][0] or w.weiterleiter[0][1]}", w.notiz))
        benannt.append(("die weitergeleitete Mail des Kunden",
                        w.original.volltext() if w.original is not None else m.volltext()))
    benannt.append(("Anfrageformular", formular_text))
    mehrere = len(mails) > 1 or any(weiter.values())
    benannt = [(n, q) for n, q in benannt if q.strip()]
    quellen = [q for _, q in benannt]
    from .angebot import lieferzeit_text
    gilt = None
    for n, q in benannt:
        art, wert, satz = mail.termin(q)
        if not art:
            continue
        if gilt is None:
            gilt, gilt_n = (art, wert), n.removeprefix("die ")
            kopf.update(lieferzeit_art=art, lieferzeit_wert=wert)
            hinweis.append(f"{lieferzeit_text(kopf).rstrip('.')} (aus „{satz[:60]}“"
                           + (f", {n}" if len(mails) > 1 else "") + ")")
        elif (art, wert) != gilt and mehrere:
            anders = lieferzeit_text(dict(lieferzeit_art=art, lieferzeit_wert=wert)).rstrip(".")
            anders = anders.removeprefix("Lieferzeit: ")
            hinweis.append(f"{n[0].upper() + n[1:]} nennt {anders} – es gilt "
                           + (f"die {gilt_n}" if len(mails) == 1 else "die neueste"))
    for q in quellen:
        staffel = mail.staffel_mengen(q)
        if staffel:
            hinweis.append(f"Mengen {' / '.join(map(str, staffel))} angefragt – Staffel bei Bedarf von Hand anlegen")
            break
    katalog = [z["name"] for z in db.zeilen("zusatzarbeiten") if z.get("name") and z.get("aktiv") != "nein"]
    erwaehnt = {}
    for q in quellen:
        for name, wort in mail.zusatz_erwaehnt(q, katalog):
            erwaehnt.setdefault(name, wort)
    for name, wort in erwaehnt.items():
        hinweis.append(f"„{wort}“ erwähnt – Zusatzarbeit {name} mit „Für alle“ setzen")
    if quellen:
        weitere["werkstoff_text"] = "\n".join(quellen)
        if mehrere:             # Werkstoff: die neueste Quelle, die einen nennt
            ws = db.zeilen("werkstoffe")
            gefunden = [(n, q, mail.werkstoff(q, ws)) for n, q in benannt]
            gefunden = [(n, q, w) for n, q, w in gefunden if w[1]]
            if gefunden:
                weitere["werkstoff_text"] = gefunden[0][1]
                for n, _, w in gefunden[1:]:
                    if w[1] != gefunden[0][2][1]:
                        hinweis.append(f"{n[0].upper() + n[1:]} nennt Werkstoff {w[1]} – es gilt {gefunden[0][2][1]} "
                                       f"({gefunden[0][0]})")
    if len(mails) > 1:
        hinweis.insert(0, f"{len(mails)} E-Mails zu dieser Anfrage – bei verschiedenen Angaben gilt die neueste "
                          f"({_mail_name(mails[0], mails)})")
    if e["nummer"]:
        schon = db.con.execute("SELECT nummer FROM angebote WHERE kundenreferenz=? ORDER BY id", (e["nummer"],)
                               ).fetchall()
        if schon:
            hinweis.append(f"Anfrage-Nr. {e['nummer']} gibt es schon in Angebot "
                           f"{', '.join(z[0] for z in schon[:3])}")
    if hinweis:
        weitere["hinweis"] = hinweis
    if kopf:
        weitere["kopf"] = kopf
    return kunde, e["nummer"], weitere


def _eigene_firma(daten, eigen_name, domains):
    """Sicherheitsnetz (31.10.2026): die eigene Firma wird nie als neuer Kunde angelegt (gleicher Name, Name enthält
    den eigenen Firmennamen oder E-Mail mit eigener Domain)."""
    from . import formular, mail
    if formular.ohne_zeichen(daten.get("name")) == formular.ohne_zeichen(eigen_name):
        return True
    kern = mail._kompakt(re.sub(mail.FIRMA, "", eigen_name or ""))
    if len(kern) >= 5 and kern in mail._kompakt(daten.get("name")):
        return True
    return mail.ist_intern(daten.get("email"), domains)


def _mail_name(m, mails):
    """'E-Mail vom 28.10. 09:15' (bei mehreren Mails mit Uhrzeit), für Hinweise und Tooltips."""
    if not m.datum:
        return "E-Mail"
    return f"E-Mail vom {m.datum.strftime('%d.%m. %H:%M' if len(mails) > 1 else '%d.%m.')}"


def mails_neben(pfade):
    """E-Mails (.msg/.eml) und ZIP-Dateien mit STEP unter den gezogenen Dateien und Ordnern (Ordner samt
    Unterordnern)."""
    out = []
    for p in map(Path, pfade or ()):
        try:
            kandidaten = sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
        except OSError:
            continue
        out += [x for x in kandidaten if not x.name.startswith(("~$", ".")) and x not in out
                and (x.suffix.lower() in MAIL or (x.suffix.lower() in ARCHIV and _hat_step([x])))]
    return out


def neben_auspacken(mail_pfad):
    """STEP-Anhänge einer Mail bzw. STEP-Dateien einer ZIP daneben legen (Kundenordner gezogen), gleiche Dateien
    nicht doppelt. Ergebnis: [Pfade der STEP-Dateien aus der Mail/ZIP]."""
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
    return tuple((a.schluessel, a.gesperrt, len(a.dateien), tuple(sorted(a.zugewiesen.items()))) for a in anfragen)


def kunde_text(kunden, nr):
    for k in kunden or ():
        if str(k.get("kundennr")) == str(nr):
            return str(k.get("name") or nr)
    return str(nr or "")
