"""KI 4: Trainingsdaten für ein eigenes Modell (Fine-Tuning) – strukturiert, bereinigt, anonymisiert, fest getrennt und
versioniert (Master-Prompt Patrick 21.11.2026, Punkte 4 und 12, Schritte 3 bis 6; Plan
https://claude.ai/artifact/88Dk7571GLveJM3Kq3MofA).

Das Programm trainiert nicht selbst (dafür braucht es PyTorch und eine NVIDIA-Grafikkarte). Es schreibt die Daten als
JSONL im Chat-Format, das gängige Trainingswerkzeuge lesen (Unsloth, axolotl, llama.cpp-finetune), in einen Ordner
(z. B. Netzwerkordner zum Trainings-PC). Das fertige Modell kommt als GGUF-Datei zurück, wird in der KI-Zentrale
importiert, im Modell-Register eingetragen, mit dem Prüfsatz geprüft und erst dann produktiv (ki_register).

Aufgaben (nur bestätigte oder sicher erkannte Fälle):
  absage      Absage-Mail bzw. Bemerkung → Absagegrund (vom Mitarbeiter im Absage-Dialog bestätigt)
  mail_art    Mail-Text → Mail-Art (Korrekturen von Hand in der Anfragen-Erkennung, anfrage_lernen)
  einordnen   Frage an den Assistenten → Absicht (nur die von den festen Regeln sicher erkannten)
Bereinigt: leere und zu kurze Eingaben, unbekannte Antworten, Doppelte (gleiche Eingabe; bei Widerspruch fliegen alle
Fälle dieser Eingabe raus). Anonymisiert: Mail-Adressen, Telefonnummern, Internet-Adressen, Kunden- und
Ansprechpartnernamen. Getrennt: fest nach Prüfsumme der Eingabe, 10 % Test (bleibt bei jedem Export im Test).
Versioniert: Ordner ki_training_<Datum>_<Prüfsumme>, manifest.json mit Anzahl und SHA-256 je Datei. Ohne Qt."""
import datetime
import hashlib
import json
import re
from pathlib import Path

from . import protokoll

TEST_ANTEIL = 10            # Prozent
MIN_LAENGE = 8
SYSTEM = {
    "absage": "Du bist die KI einer Rohrlaser-Lohnfertigung. Wähle den Absagegrund des Kunden aus der Liste.",
    "mail_art": "Du bist die KI einer Rohrlaser-Lohnfertigung. Ordne die E-Mail einer Mail-Art zu.",
    "einordnen": "Du bist die KI einer Rohrlaser-Lohnfertigung. Ordne die Frage des Kalkulators einer Absicht zu.",
}
LIESMICH = """Trainingsdaten Rohrlaser-KI ({version})

Erstellt {zeit} mit Programmversion {programm}. Inhalt siehe manifest.json (Anzahl, SHA-256 je Datei).
Format: JSONL, je Zeile {{"messages": [system, user, assistant]}} – passt für Unsloth, axolotl und llama.cpp.

Training (auf einem PC mit NVIDIA-Grafikkarte, OHNE Internet):
1. Basismodell als Datei bereitstellen (z. B. Qwen3-4B oder Qwen3-8B, Apache-2.0), nicht herunterladen lassen.
2. QLoRA mit den *_train.jsonl-Dateien trainieren (2-3 Epochen, Lernrate 2e-4, LoRA-Rang 16).
3. Ergebnis zusammenführen und als GGUF (Q4_K_M) exportieren – mit neuem, eindeutigem Dateinamen
   (z. B. rohrlaser-ki-{version}.gguf), damit frühere Versionen in Ollama bleiben und „Zurücksetzen“ geht.
4. GGUF-Datei in den Modell-Ordner legen, in der KI-Zentrale importieren, im Reiter Modellversionen
   „Prüfen“ (Prüfsatz plus *_test.jsonl) und erst bei gleich gutem oder besserem Ergebnis „Aktivieren“.
5. Als Datensatz-Version beim Eintrag „{version}“ angeben.
"""


def _jetzt():
    return datetime.datetime.now()


def _hash(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def ist_test(eingabe):
    """Feste Trennung: dieselbe Eingabe ist bei jedem Export im Test bzw. im Training."""
    return int(_hash(_norm(eingabe))[:8], 16) % 100 < TEST_ANTEIL


def _norm(t):
    return re.sub(r"\s+", " ", str(t or "")).strip().casefold()


# ------------------------------------------------------------------ Anonymisieren
def namen(db):
    """Kunden- und Ansprechpartnernamen (zum Maskieren), längste zuerst."""
    out = set()
    try:
        cur = db.con.execute("SELECT * FROM kunden")
        spalten = [d[0] for d in cur.description]
        for r in cur.fetchall():
            for s, w in zip(spalten, r):
                if s in ("name", "firma", "name2", "ansprechpartner", "kontakt") and isinstance(w, str) and len(w) >= 3:
                    out.add(w.strip())
    except Exception:           # noqa: BLE001 – ohne Kundentabelle nur Mail/Telefon maskieren
        protokoll.warnung("ki_training: Kunden nicht lesbar")
    return sorted(out, key=len, reverse=True)


def anonymisieren(text, namen_=()):
    t = str(text or "")
    t = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "<EMAIL>", t)
    t = re.sub(r"https?://\S+|www\.\S+", "<URL>", t)
    t = re.sub(r"(?:\+|00)\d[\d /()-]{7,}\d|\b0\d{2,5}[ /-]?\d{3,}[\d /-]*\d", "<TELEFON>", t)
    for n in namen_:
        t = re.sub(re.escape(n), "<KUNDE>", t, flags=re.I)
    return t


# ------------------------------------------------------------------ Quellen
def _absagen(db):
    from . import absage
    out = []
    try:
        zeilen = db.angebote()
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_training: Angebote nicht lesbar")
        return out
    for z in zeilen:
        z = dict(z)
        if isinstance(z.get("versand"), str):
            try:
                z["versand"] = json.loads(z["versand"])
            except ValueError:
                z["versand"] = []
        e = absage.letzte(z)
        if not e or e.get("grund") not in absage.GRUENDE:
            continue
        text = re.sub(r"^Aus Mail:\s*", "", str(e.get("bemerkung") or "")).strip()
        if text:
            out.append(dict(eingabe=text, antwort=e["grund"], quelle=f"Angebot {z.get('nummer') or z.get('id')}"))
    return out


def _mail_arten(db, wurzel=None):
    from . import anfrage_lernen
    out = []
    try:
        if wurzel is None:
            from . import anfragen_akten
            wurzel = anfragen_akten.wurzel(db)
        for r in anfrage_lernen.rueckmeldungen(wurzel, "art"):
            if r.get("text") and r.get("neu"):
                out.append(dict(eingabe=r["text"], antwort=str(r["neu"]), quelle=f"Anfrage {r.get('nr') or ''}".strip()))
    except Exception:           # noqa: BLE001 – ohne Akten-Ordner: keine Mail-Arten
        protokoll.warnung("ki_training: Rückmeldungen nicht lesbar")
    return out


def _einordnungen(db):
    from . import ki_protokoll
    from .ki_orchestrator import ABSICHTEN, absicht_regeln
    titel = {t[0]: n for n, t in ABSICHTEN.items()}
    out = []
    for z in ki_protokoll.liste(db, anzahl=5000, agent="Orchestrator", aktion="frage"):
        frage = z.get("frage") or ""
        t = str(z.get("ergebnis") or "").split(":")[0]
        n = titel.get(t)
        if n and z.get("status") in (None, "", "ok") and absicht_regeln(frage)[0] == n:
            out.append(dict(eingabe=frage, antwort=n, quelle=f"KI-Protokoll {z.get('zeit') or ''}".strip()))
    return out


def sammeln(db, wurzel=None):
    """{Aufgabe: [dict(eingabe, antwort, quelle)]} aus allen Quellen (noch nicht bereinigt)."""
    return dict(absage=_absagen(db), mail_art=_mail_arten(db, wurzel), einordnen=_einordnungen(db))


def bereinigen(faelle, namen_=()):
    """(gute Fälle, verworfen {Grund: Anzahl}): anonymisiert, ohne leere/kurze, ohne Doppelte und Widersprüche."""
    verworfen = {}

    def weg(grund):
        verworfen[grund] = verworfen.get(grund, 0) + 1
    je = {}
    for f in faelle:
        e = anonymisieren(f.get("eingabe"), namen_).strip()[:4000]
        a = str(f.get("antwort") or "").strip()
        if len(e) < MIN_LAENGE:
            weg("Eingabe leer oder zu kurz")
            continue
        if not a:
            weg("ohne Antwort")
            continue
        je.setdefault(_norm(e), []).append(dict(f, eingabe=e, antwort=a))
    gut = []
    for liste in je.values():
        antworten = {x["antwort"] for x in liste}
        if len(antworten) > 1:
            for _ in liste:
                weg("widersprüchliche Antworten")
            continue
        for _ in liste[1:]:
            weg("doppelt")
        gut.append(liste[0])
    return gut, verworfen


def _zeile(aufgabe, f):
    return json.dumps(dict(messages=[dict(role="system", content=SYSTEM[aufgabe]),
                                     dict(role="user", content=f["eingabe"]),
                                     dict(role="assistant", content=f["antwort"])]), ensure_ascii=False)


def exportieren(db, ordner, wurzel=None, jetzt=None, faelle=None):
    """Trainingsdaten schreiben. Ergebnis: dict(version, ordner, aufgaben {Aufgabe: dict(train, test, verworfen)},
    gesamt, manifest). faelle ersetzt sammeln() (Tests)."""
    from . import VERSION as programm
    jetzt = jetzt or _jetzt()
    roh = faelle if faelle is not None else sammeln(db, wurzel)
    nm = namen(db)
    bereinigt = {a: bereinigen(f, nm) for a, f in roh.items()}
    inhalt = json.dumps({a: sorted(f["eingabe"] + "→" + f["antwort"] for f in g) for a, (g, _) in bereinigt.items()},
                        ensure_ascii=False, sort_keys=True)
    version = f"{jetzt:%Y-%m-%d}_{_hash(inhalt)[:8]}"
    ziel = Path(ordner) / f"ki_training_{version}"
    ziel.mkdir(parents=True, exist_ok=True)
    manifest = dict(version=version, erstellt=jetzt.isoformat(timespec="seconds"), programm=programm,
                    test_anteil=TEST_ANTEIL, aufgaben={}, dateien={})
    for a, (gut, verworfen) in bereinigt.items():
        train = [f for f in gut if not ist_test(f["eingabe"])]
        test = [f for f in gut if ist_test(f["eingabe"])]
        for teil, liste in (("train", train), ("test", test)):
            p = ziel / f"{a}_{teil}.jsonl"
            daten = "".join(_zeile(a, f) + "\n" for f in sorted(liste, key=lambda x: _hash(x["eingabe"])))
            p.write_text(daten, encoding="utf-8")
            manifest["dateien"][p.name] = dict(anzahl=len(liste), sha256=_hash(daten))
        manifest["aufgaben"][a] = dict(train=len(train), test=len(test), verworfen=verworfen,
                                       quellen=sorted({f.get("quelle", "").split(" ")[0] for f in gut} - {""}))
    (ziel / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (ziel / "LIESMICH.txt").write_text(LIESMICH.format(version=version, zeit=manifest["erstellt"], programm=programm),
                                       encoding="utf-8")
    gesamt = sum(x["train"] + x["test"] for x in manifest["aufgaben"].values())
    _merken(db, dict(version=version, ordner=str(ziel), erstellt=manifest["erstellt"], gesamt=gesamt,
                     aufgaben={a: [x["train"], x["test"]] for a, x in manifest["aufgaben"].items()}))
    return dict(version=version, ordner=str(ziel), aufgaben=manifest["aufgaben"], gesamt=gesamt, manifest=manifest)


def _merken(db, eintrag):
    from .ki_register import TRAININGSDATEN
    try:
        alt = db.einstellung(TRAININGSDATEN)
        liste = list(alt) if isinstance(alt, list) else []
        liste.append(eintrag)
        db.einstellung_setzen(TRAININGSDATEN, liste[-50:])
    except Exception:           # noqa: BLE001 – Export ist trotzdem gültig
        protokoll.warnung("ki_training: Export nicht gemerkt")


def exporte(db):
    from .ki_register import TRAININGSDATEN
    try:
        w = db.einstellung(TRAININGSDATEN)
    except Exception:           # noqa: BLE001
        protokoll.warnung("ki_training: Exporte nicht lesbar")
        return []
    return list(reversed(w)) if isinstance(w, list) else []


def manifest_pruefen(ordner):
    """(ok, Fehler): stimmen Anzahl und SHA-256 aller Dateien mit dem Manifest? (erkennt veränderte Trainingsdaten)"""
    o = Path(ordner)
    try:
        m = json.loads((o / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return False, [f"manifest.json: {e}"]
    fehler = []
    for name, info in (m.get("dateien") or {}).items():
        try:
            daten = (o / name).read_text(encoding="utf-8")
        except OSError:
            fehler.append(f"{name} fehlt")
            continue
        if _hash(daten) != info.get("sha256"):
            fehler.append(f"{name} verändert")
    return not fehler, fehler


def testfaelle(db, n_max=40):
    """Aufgaben für den Prüfsatz aus dem Testanteil des letzten Exports (nur wenn sein Manifest stimmt)."""
    ex = exporte(db)
    if not ex:
        return []
    o = Path(ex[0]["ordner"])
    ok, _ = manifest_pruefen(o)
    if not ok:
        return []
    out = []
    for p in sorted(o.glob("*_test.jsonl")):
        aufgabe = p.name[:-len("_test.jsonl")]
        for zeile in p.read_text(encoding="utf-8").splitlines():
            try:
                m = json.loads(zeile)["messages"]
            except (ValueError, KeyError, TypeError):
                continue
            out.append(dict(art=f"eigen_{aufgabe}", eingabe=m[1]["content"], erwartet=m[2]["content"],
                            system=m[0]["content"] + " Antworte nur mit der Antwort, ohne Zusatz.",
                            prompt=m[1]["content"], json=False))
            if len(out) >= n_max:
                return out
    return out


def eigen_bewerten(a, text):
    """Bewertung eigener Testfälle: Antwort muss die erwartete enthalten."""
    return (1, "richtig") if _norm(a["erwartet"]) in _norm(text) else (0, f"„{str(text)[:40]}“ statt „{a['erwartet']}“")
