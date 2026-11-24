"""Rückmeldungen zur Anfrage-Erkennung (Patrick 20.11.2026, Plan K9, „Alles einbauen“).

Jede Korrektur von Hand (Mail-Art, Sachgebiet, Kunde, Zuordnung zu einer Anfrage, Bearbeiter, erkannte Werte) wird
als eine Zeile in _outlook/rueckmeldung.jsonl im Akten-Ordner gespeichert: was automatisch erkannt war, was der
Mitarbeiter gewählt hat, wer, wann, die Anfrage und (für die Mail-Art) die ersten Zeichen des Mail-Texts als
Lernstoff. Alle Plätze schreiben in dieselbe Datei (nur anhängen, nie überschreiben).

rueckmelden(wurzel, feld, auto, neu, nr, kuerzel, text)   eine Rückmeldung anhängen
rueckmeldungen(wurzel, feld=None)                          alle (bzw. eines Felds), älteste zuerst
auswertung(wurzel, akten)                                  Trefferquote je Feld, häufige Verwechslungen, Kennzahlen

Kontrolliertes Lernen der Mail-Art (Plan K9): aus den Korrekturen wird ein kleines Wortmodell gerechnet (naiver Bayes,
nur Wörter, lokal, ohne Bibliothek). Es läuft zuerst nur im Schatten: geprüft wird es an allen Korrekturen (jede
einmal herausgenommen) gegen die Regeln. Wirksam wird es erst, wenn ein Admin es freigibt (freigeben), und nur, wenn es
dabei mindestens so gut war wie die Regeln und genug Beispiele hatte. Ein neues Training ändert nie das freigegebene
Modell; zuruecknehmen stellt das vorherige wieder her. Das Modell ändert nur unsichere Einordnungen und sagt dazu,
dass es gelernt ist. Ohne Qt."""
import datetime
import json
import math
import re
from pathlib import Path

DATEI = "rueckmeldung.jsonl"
STAMM = "_outlook"
TEXT_MAX = 2000
FELDER = {"art": "Mail-Art", "sachgebiet": "Sachgebiet", "kunde": "Kunde", "zuordnung": "Zuordnung zu Anfrage",
          "bearbeiter": "Bearbeiter", "wert": "Erkannter Wert", "ordner": "Outlook-Ordner", "phase": "Phase"}


def pfad(wurzel):
    return Path(wurzel) / STAMM / DATEI


def rueckmelden(wurzel, feld, auto, neu, nr="", kuerzel="", text="", jetzt=None, **weitere):
    """Eine Rückmeldung anhängen. auto: was automatisch erkannt war; neu: was der Mitarbeiter gewählt hat.
    Gleiches auto und neu ist eine Bestätigung (richtig erkannt). Ergebnis: der Eintrag (dict)."""
    if not wurzel:
        return None
    e = dict(zeit=(jetzt or datetime.datetime.now()).isoformat(timespec="seconds"), feld=feld,
             auto=auto if auto is not None else "", neu=neu if neu is not None else "", richtig=auto == neu, nr=nr,
             kuerzel=kuerzel)
    if text:
        e["text"] = str(text)[:TEXT_MAX]
    e.update({k: v for k, v in weitere.items() if v not in (None, "")})
    p = pfad(wurzel)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return e


def rueckmeldungen(wurzel, feld=None):
    """Alle Rückmeldungen (bzw. eines Felds), älteste zuerst; kaputte Zeilen werden übersprungen."""
    p = pfad(wurzel) if wurzel else None
    if p is None or not p.is_file():
        return []
    out = []
    for z in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(z)
        except ValueError:
            continue
        if isinstance(e, dict) and (feld is None or e.get("feld") == feld):
            out.append(e)
    out.sort(key=lambda e: e.get("zeit", ""))
    return out


# ---------------------------------------------------------------------------------------------- Auswertung
def auswertung(wurzel, akten=()):
    """Kennzahlen der Erkennung: je Feld Anzahl, richtig, Quote und häufigste Verwechslungen (aus den Rückmeldungen);
    aus den Akten die Verteilung der Mail-Art-Sicherheit und der Kunden-Erkennung."""
    felder = {}
    for e in rueckmeldungen(wurzel):
        f = felder.setdefault(e.get("feld") or "?", dict(anzahl=0, richtig=0, verwechselt={}))
        f["anzahl"] += 1
        if e.get("richtig"):
            f["richtig"] += 1
        else:
            k = f"{e.get('auto') or '–'} → {e.get('neu') or '–'}"
            f["verwechselt"][k] = f["verwechselt"].get(k, 0) + 1
    for f in felder.values():
        f["quote"] = round(100 * f["richtig"] / f["anzahl"]) if f["anzahl"] else None
        f["verwechselt"] = sorted(f["verwechselt"].items(), key=lambda x: -x[1])[:5]
    sicherheit, kunde, n = {}, {}, 0
    for a in akten:
        n += 1
        ein = a.kopf.get("einordnung") or {}
        if ein:
            x = "korrigiert" if a.stand.get("art_korr") else ein.get("sicherheit") or "?"
            sicherheit[x] = sicherheit.get(x, 0) + 1
        z = a.kopf.get("zuordnung") or {}
        st = "korrigiert" if a.stand.get("kunde") is not None else (z.get("stufe") or "ohne")
        kunde[st] = kunde.get(st, 0) + 1
    return dict(felder=felder, akten=n, sicherheit=sicherheit, kunde=kunde)


# ---------------------------------------------------------------------------------------------- Wortmodell (Mail-Art)
MIN_BEISPIELE = 20          # weniger Korrekturen: kein Freigeben
MIN_P = 0.75                # so sicher muss das Modell sein, um eine unsichere Einordnung zu ändern
MODELL = "modell_art.json"              # Schatten (zuletzt trainiert)
AKTIV = "modell_art_aktiv.json"         # freigegeben
VORHER = "modell_art_vorher.json"       # vor der letzten Freigabe (für Zurücknehmen)
_WORT = re.compile(r"[a-zäöüß]{3,}")


def woerter(text):
    return _WORT.findall(str(text or "").lower())


# 23.11.2026 (Stufe 2 Punkt 3): dasselbe Verfahren auch für das Sachgebiet und den Bearbeiter. Jedes Ziel hat
# eigene Dateien (Schatten, freigegeben, vorher) und eine eigene Freigabe; die Mail-Art behält ihre Dateinamen.
ZIELE = {"art": "Mail-Art", "sachgebiet": "Sachgebiet", "bearbeiter": "Bearbeiter"}
KEINS = "keins"                 # Sachgebiet: keines erkannt


def _dateien(ziel):
    if ziel == "art":
        return MODELL, AKTIV, VORHER
    return f"modell_{ziel}.json", f"modell_{ziel}_aktiv.json", f"modell_{ziel}_vorher.json"


def sg_klasse(sachgebiete):
    return "+".join(sorted(str(x) for x in sachgebiete or ())) or KEINS


def merkmale(betreff="", kunde="", sachgebiete=()):
    """Merkmale für den Bearbeiter: Wörter des Betreffs, Kunde und Sachgebiete als eigene Merkmale."""
    return woerter(betreff) + ([f"kunde_{kunde}"] if kunde else []) + [f"sg_{x}" for x in sachgebiete or ()]


def _beispiele(wurzel, ziel="art"):
    """[(Merkmale, Klasse, automatisch)] aus den Rückmeldungen (letzte je Anfrage zählt). Mail-Art und Sachgebiet
    aus den Korrekturen der Mail-Art (mit Mail-Text), der Bearbeiter aus angenommenen bzw. geänderten Vorschlägen."""
    je = {}
    if ziel == "bearbeiter":
        for e in rueckmeldungen(wurzel, "bearbeiter"):
            if e.get("neu"):
                je[e.get("nr") or e.get("zeit")] = (merkmale(e.get("betreff"), e.get("kunde"), e.get("sachgebiete")),
                                                    str(e["neu"]).upper(), str(e.get("auto") or "").upper())
        return list(je.values())
    for e in rueckmeldungen(wurzel, "art"):
        if not e.get("text") or not e.get("neu"):
            continue
        if ziel == "sachgebiet":
            if "sachgebiete" not in e:
                continue
            je[e.get("nr") or e.get("zeit")] = (woerter(e["text"]), sg_klasse(e["sachgebiete"]),
                                                sg_klasse(e.get("sachgebiete_auto")))
        else:
            je[e.get("nr") or e.get("zeit")] = (woerter(e["text"]), e["neu"], e.get("auto") or "")
    return list(je.values())


def _zaehlen(beispiele):
    klassen, worte = {}, {}
    for w, k, _auto in beispiele:
        klassen[k] = klassen.get(k, 0) + 1
        z = worte.setdefault(k, {})
        for x in w:
            z[x] = z.get(x, 0) + 1
    return klassen, worte


def _vorhersage(klassen, worte, w, ohne=None):
    """(Klasse, Wahrscheinlichkeit). ohne: (Wörter, Klasse) eines Beispiels, das nicht mitzählen soll."""
    gesamt = sum(klassen.values()) - (1 if ohne else 0)
    vokabel = {x for z in worte.values() for x in z}
    if gesamt <= 0 or not vokabel:
        return "", 0.0
    weg = {}
    if ohne:
        for x in ohne[0]:
            weg[x] = weg.get(x, 0) + 1
    punkte = {}
    for k, n in klassen.items():
        n -= 1 if ohne and ohne[1] == k else 0
        if n <= 0:
            continue
        z = worte.get(k, {})
        summe = sum(z.values()) - (len(ohne[0]) if ohne and ohne[1] == k else 0)
        p = math.log(n / gesamt)
        for x in w:
            c = z.get(x, 0) - (weg.get(x, 0) if ohne and ohne[1] == k else 0)
            p += math.log((c + 1) / (summe + len(vokabel)))
        punkte[k] = p
    if not punkte:
        return "", 0.0
    m = max(punkte.values())
    summe = sum(math.exp(v - m) for v in punkte.values())
    k = max(punkte, key=punkte.get)
    return k, 1 / summe


def trainieren(wurzel, jetzt=None, ziel="art"):
    """Wortmodell aus allen Korrekturen rechnen und im Schatten prüfen (jede Korrektur einmal herausgenommen: Modell
    gegen Regeln). Schreibt nur das Schatten-Modell; das freigegebene bleibt unverändert. Ergebnis: das Modell."""
    b = _beispiele(wurzel, ziel)
    klassen, worte = _zaehlen(b)
    regeln = modell = 0
    for w, k, auto in b:
        regeln += auto == k
        modell += _vorhersage(klassen, worte, w, ohne=(w, k))[0] == k
    alt = modell_lesen(wurzel, ziel)
    m = dict(ziel=ziel, version=int(alt.get("version") or 0) + 1, trainiert_am=(jetzt or datetime.datetime.now()).isoformat(
        timespec="seconds"), n=len(b), klassen=klassen, worte=worte,
        pruefung=dict(n=len(b), regeln=round(100 * regeln / len(b)) if b else None,
                      modell=round(100 * modell / len(b)) if b else None))
    _schreiben(Path(wurzel) / STAMM / _dateien(ziel)[0], m)
    return m


def freigabe_moeglich(m):
    """(ja/nein, Grund): genug Beispiele und im Schatten mindestens so gut wie die Regeln."""
    p = (m or {}).get("pruefung") or {}
    if not m or not p.get("n"):
        return False, "noch kein geprüftes Modell"
    if p["n"] < MIN_BEISPIELE:
        return False, f"erst {p['n']} Korrekturen (mindestens {MIN_BEISPIELE})"
    if (p.get("modell") or 0) < (p.get("regeln") or 0):
        return False, f"im Test schlechter als die Regeln ({p['modell']} % gegen {p['regeln']} %)"
    return True, f"im Test {p['modell']} % richtig, Regeln {p['regeln']} %"


def freigeben(wurzel, kuerzel, jetzt=None, ziel="art"):
    """Schatten-Modell freigeben (nur wenn freigabe_moeglich); das bisher freigegebene bleibt als „vorher“.
    Ergebnis: (ja/nein, Text)."""
    m = modell_lesen(wurzel, ziel)
    ok, grund = freigabe_moeglich(m)
    if not ok:
        return False, grund
    st = Path(wurzel) / STAMM
    _m, aktiv, vorher = _dateien(ziel)
    alt = _lesen(st / aktiv)
    if alt:
        _schreiben(st / vorher, alt)
    m.update(freigegeben_von=kuerzel, freigegeben_am=(jetzt or datetime.datetime.now()).isoformat(timespec="seconds"))
    _schreiben(st / aktiv, m)
    return True, f"Modell {m['version']} freigegeben ({grund})"


def zuruecknehmen(wurzel, ziel="art"):
    """Freigabe zurücknehmen: das vorherige Modell gilt wieder (oder keines). Ergebnis: Text."""
    st = Path(wurzel) / STAMM
    _m, aktiv, vorher_ = _dateien(ziel)
    vorher = _lesen(st / vorher_)
    if vorher:
        _schreiben(st / aktiv, vorher)
        (st / vorher_).unlink(missing_ok=True)
        return f"Modell {vorher.get('version')} gilt wieder"
    (st / aktiv).unlink(missing_ok=True)
    return "Kein gelerntes Modell mehr aktiv, es gelten nur die Regeln"


def modell_lesen(wurzel, ziel="art"):
    return _lesen(Path(wurzel) / STAMM / _dateien(ziel)[0]) if wurzel else {}


def aktiv_lesen(wurzel, ziel="art"):
    return _lesen(Path(wurzel) / STAMM / _dateien(ziel)[1]) if wurzel else {}


def anwenden(m, ein, text, betreff=""):
    """Freigegebenes Modell auf eine Einordnung (anfrage_art.kompakt) anwenden: nur wenn die Regeln nicht sicher sind,
    das Modell sicher genug ist und etwas anderes sagt. Ergebnis: neue Einordnung oder die alte."""
    if not m or not ein or ein.get("sicherheit") in ("sicher", "bestätigt"):
        return ein
    k, p = _vorhersage(m.get("klassen") or {}, m.get("worte") or {}, woerter(f"{betreff}\n{text}"))
    if not k or k == ein.get("art") or p < MIN_P:
        return ein
    neu = dict(ein, art=k, sicherheit="wahrscheinlich", gelernt=True, regel_art=ein.get("art"))
    neu["gruende"] = [(f"gelernt aus {m.get('n')} Korrekturen (Modell {m.get('version')}, {round(100 * p)} %)", "")] \
        + list(ein.get("gruende") or [])
    return neu


def sachgebiete_anwenden(m, ein, text, betreff=""):
    """Freigegebenes Sachgebiet-Modell: nur wenn die Einordnung nicht sicher ist, das Modell sicher genug ist und
    andere Sachgebiete sagt. Ergebnis: neue Einordnung oder die alte."""
    if not m or not ein or ein.get("sicherheit") in ("sicher", "bestätigt"):
        return ein
    k, p = _vorhersage(m.get("klassen") or {}, m.get("worte") or {}, woerter(f"{betreff}\n{text}"))
    alt = sg_klasse(ein.get("sachgebiete"))
    if not k or k == alt or p < MIN_P:
        return ein
    neu = dict(ein, sachgebiete=[] if k == KEINS else k.split("+"), gelernt_sg=True, regel_sachgebiete=list(
        ein.get("sachgebiete") or []))
    neu["gruende"] = list(ein.get("gruende") or []) + [
        (f"Sachgebiet gelernt aus {m.get('n')} Korrekturen (Modell {m.get('version')}, {round(100 * p)} %)", "")]
    return neu


def bearbeiter_tipp(m, betreff="", kunde="", sachgebiete=()):
    """Freigegebenes Bearbeiter-Modell: (Kürzel, Wahrscheinlichkeit, Beispiele) bei p ≥ MIN_P, sonst None."""
    if not m:
        return None
    k, p = _vorhersage(m.get("klassen") or {}, m.get("worte") or {}, merkmale(betreff, kunde, sachgebiete))
    return (k, p, m.get("n") or 0) if k and p >= MIN_P else None


def _lesen(p):
    if not Path(p).is_file():           # kein Lesen ohne Datei (der Takt der Seite Anfragen liest sonst nichts)
        return {}
    try:
        z = json.loads(Path(p).read_text(encoding="utf-8"))
        return z if isinstance(z, dict) else {}
    except (OSError, ValueError):
        return {}


def _schreiben(p, wert):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(wert, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
