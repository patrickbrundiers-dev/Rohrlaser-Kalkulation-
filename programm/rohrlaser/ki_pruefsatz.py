"""KI 4: fachlicher Prüfsatz – feste Aufgaben aus dem Rohrlaser-Alltag, mit denen jede Modellversion vor dem
Produktiveinsatz geprüft wird (Master-Prompt Patrick 21.11.2026, Punkt 12 Schritte 8 und 9; Plan
https://claude.ai/artifact/88Dk7571GLveJM3Kq3MofA).

Vier Arten, je Aufgabe ein Punkt:
  einordnen   Frage eines Kalkulators einer Absicht des Assistenten zuordnen (wie ki_orchestrator.absicht_modell)
  auslesen    Werte aus einer Anfrage als JSON (Werkstoff, Abmessung, Länge, Menge) – Zahl muss genau stimmen
  absage      Absagegrund aus einer Kunden-Mail wählen (nur aus absage.GRUENDE)
  erklaeren   kurze Erklärung aus vorgegebenen Fakten – bestanden nur ohne erfundene Zahl (Faktencheck) und mit der
              wichtigsten Zahl aus den Fakten
Dazu kommen, wenn vorhanden, die Testanteile der eigenen Trainingsdaten (ki_training, 10 % fest getrennt).

pruefen(db, modell) ruft das Modell direkt auf (ohne Rollen) und liefert Punkte, Quote, je Art und die Einzelantworten.
Das Ergebnis speichert ki_register.pruefung_speichern; ki_register.aktivieren verlangt es. Ohne Qt, ohne Internet."""
import json
import re
import time

from . import protokoll

PRUEFSATZ = "PS-1"          # Version des Prüfsatzes; ändert sich, wenn Aufgaben dazukommen

EINORDNEN = (
    ("Warum ist dieses Angebot so teuer?", "teuer"),
    ("Prüf bitte das ganze Angebot auf Fehler.", "pruefung"),
    ("Wie kann ich Material sparen, der Verschnitt ist hoch?", "material"),
    ("Mach mir eine Mengenstaffel für 10, 50 und 100 Stück.", "staffel"),
    ("Wie hoch ist das Preisrisiko bei diesem Angebot?", "risiko"),
    ("Wann können wir liefern, wo sind Engpässe?", "liefertermin"),
    ("Was bedeuten die Fehlermeldungen von gestern?", "fehlerlog"),
    ("Schreib die Rückfrage an den Kunden auf Englisch.", "englisch"),
)

AUSLESEN = (
    ("Bitte Angebot über 40 Stück Rundrohr 42,4x2,0 S235, Länge 1250 mm, entgratet.",
     dict(menge=40, laenge_mm=1250, werkstoff="S235", abmessung="42,4x2,0")),
    ("Anfrage: 120 Stk. Quadratrohr 40x40x3, Werkstoff S355, L = 860 mm.",
     dict(menge=120, laenge_mm=860, werkstoff="S355", abmessung="40x40x3")),
    ("Wir benötigen 25 Teile aus Edelstahl 1.4301, Rechteckrohr 60x40x2, je 2000 mm lang.",
     dict(menge=25, laenge_mm=2000, werkstoff="1.4301", abmessung="60x40x2")),
    ("Preis für 8 Stück Rundrohr 33,7x2,6 aus S235JR, 640 mm, bitte mit Werkszeugnis 3.1.",
     dict(menge=8, laenge_mm=640, werkstoff="S235", abmessung="33,7x2,6")),
)

ABSAGE = (
    ("Leider war ein anderer Anbieter deutlich günstiger.", "Preis zu hoch"),
    ("Das Projekt wurde vom Endkunden auf nächstes Jahr verschoben.", "Projekt verschoben oder gestrichen"),
    ("Wir haben uns entschieden, die Teile künftig im Haus auf unserer eigenen Anlage zu fertigen.",
     "Kunde fertigt selbst"),
    ("Ihre Lieferzeit von sechs Wochen ist für uns leider zu lang.", "Lieferzeit zu lang"),
)

ERKLAEREN = (
    ("Material 312,40 €, Laserzeit 96,00 €, Rüsten 45,00 €, Zukauf 0 €, Summe netto 453,40 €. Größter Posten: "
     "Material.", "312,40"),
    ("Laserzeit je Teil 1,8 min, davon Einstechen 0,4 min, 14 Einstiche je Teil, Stückzahl 250.", "14"),
    ("Marge 6 %, Zielmarge 15 %, Preisuntergrenze 1.180,00 €, Angebotspreis 1.240,00 €.", "6"),
)


def aufgaben():
    """Alle Aufgaben als dict(art, eingabe, erwartet)."""
    out = [dict(art="einordnen", eingabe=f, erwartet=a) for f, a in EINORDNEN]
    out += [dict(art="auslesen", eingabe=t, erwartet=w) for t, w in AUSLESEN]
    out += [dict(art="absage", eingabe=t, erwartet=g) for t, g in ABSAGE]
    out += [dict(art="erklaeren", eingabe=f, erwartet=z) for f, z in ERKLAEREN]
    return out


def _json(text):
    t = str(text or "").strip()
    m = re.search(r"\{.*\}", t, re.S)
    try:
        return json.loads(m.group(0) if m else t)
    except (ValueError, TypeError):
        return {}


def _norm(s):
    return re.sub(r"\s+", "", str(s or "")).casefold().replace("×", "x").replace(".", ",")


def _zahl(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _prompt(a):
    """(System, Prompt, JSON) für eine Aufgabe."""
    if a["art"] == "einordnen":
        from .ki_orchestrator import ABSICHTEN
        liste = ", ".join(f"{n} ({t[0]})" for n, t in ABSICHTEN.items())
        return ("Ordne die Frage eines Kalkulators in einer Rohrlaser-Lohnfertigung genau einer Absicht zu: "
                f"{liste}. Antworte nur als JSON {{\"absicht\": \"name\"}}.", f"Frage: {a['eingabe']}", True)
    if a["art"] == "auslesen":
        return ("Lies aus der Anfrage Menge (Stück), Länge in mm, Werkstoff (Kurzname wie S235, S355, 1.4301) und "
                "Abmessung (wie 42,4x2,0) aus. Antworte nur als JSON {\"menge\": Zahl, \"laenge_mm\": Zahl, "
                "\"werkstoff\": \"…\", \"abmessung\": \"…\"}. Erfinde nichts.", a["eingabe"], True)
    if a["art"] == "absage":
        from .absage import GRUENDE
        return ("Warum hat der Kunde abgesagt? Wähle genau einen Grund aus " + json.dumps(list(GRUENDE),
                ensure_ascii=False) + ". Antworte nur als JSON {\"grund\": \"…\"}.", a["eingabe"], True)
    return ("Erkläre einem Kalkulator in zwei Sätzen auf Deutsch, was an diesen Werten auffällt. Verwende nur Zahlen "
            "aus den Fakten.", f"Fakten: {a['eingabe']}", False)


def bewerten(a, text):
    """(Punkt 0/1, Begründung) für eine Antwort."""
    if str(a["art"]).startswith("eigen_"):
        from .ki_training import eigen_bewerten
        return eigen_bewerten(a, text)
    if a["art"] == "einordnen":
        n = _json(text).get("absicht")
        return (1, "richtig") if n == a["erwartet"] else (0, f"„{n}“ statt „{a['erwartet']}“")
    if a["art"] == "auslesen":
        d = _json(text)
        e = a["erwartet"]
        falsch = []
        if _zahl(d.get("menge")) != float(e["menge"]):
            falsch.append("Menge")
        if _zahl(d.get("laenge_mm")) != float(e["laenge_mm"]):
            falsch.append("Länge")
        if not _norm(d.get("werkstoff")).startswith(_norm(e["werkstoff"])):
            falsch.append("Werkstoff")
        if _norm(d.get("abmessung")) != _norm(e["abmessung"]):
            falsch.append("Abmessung")
        return (0, "falsch: " + ", ".join(falsch)) if falsch else (1, "alle Werte richtig")
    if a["art"] == "absage":
        g = _json(text).get("grund")
        return (1, "richtig") if g == a["erwartet"] else (0, f"„{g}“ statt „{a['erwartet']}“")
    from .ki_orchestrator import faktencheck
    ok, fremd = faktencheck(text, a["eingabe"])
    if not ok:
        return 0, "erfundene Zahl: " + ", ".join(str(x) for x in fremd[:3])
    if a["erwartet"] not in str(text):
        return 0, f"wichtigste Zahl {a['erwartet']} fehlt"
    return 1, "nur belegte Zahlen"


def _test_aus_trainingsdaten(db, n_max=40):
    """Testfälle aus dem letzten Trainingsdaten-Export (nur Aufgaben mit fester Antwort)."""
    try:
        from . import ki_training
        return ki_training.testfaelle(db, n_max=n_max)
    except Exception:           # noqa: BLE001 – ohne Export: nur der feste Prüfsatz
        protokoll.warnung("ki_pruefsatz: Testdaten nicht lesbar")
        return []


def pruefen(db, modell, senden=None, fortschritt=None, abbrechen=None, mit_eigenen=True, eigene=None):
    """Alle Aufgaben mit einem Modell (dict aus ki_modelle.modelle): dict(modell, punkte, max, quote, je_art
    {art: [punkte, anzahl]}, details [dict(art, eingabe, antwort, punkt, grund)], dauer_s, pruefsatz, fehler).
    eigene: vorher gelesene eigene Testfälle (dann braucht der Lauf keine Datenbank, z. B. im Hintergrund-Thread)."""
    from . import ki_modelle
    if eigene is None:
        eigene = _test_aus_trainingsdaten(db) if mit_eigenen else []
    liste = aufgaben() + list(eigene)
    t0 = time.perf_counter()
    details, je_art, fehler = [], {}, 0
    for i, a in enumerate(liste):
        if abbrechen and abbrechen():
            break
        if fortschritt:
            fortschritt(i, len(liste))
        system, prompt, js = a.get("system"), a.get("prompt"), a.get("json")
        if system is None:
            system, prompt, js = _prompt(a)
        try:
            antwort = ki_modelle.erzeugen(db, ki_modelle.EXTRAHIEREN, prompt, system=system, json_format=js,
                                          senden=senden, modell=modell)["text"]
            punkt, grund = bewerten(a, antwort)
        except Exception as e:      # noqa: BLE001 – eine ausgefallene Antwort zählt 0 Punkte
            protokoll.warnung("ki_pruefsatz: Aufgabe ohne Antwort")
            antwort, punkt, grund = "", 0, f"keine Antwort: {str(e)[:100]}"
            fehler += 1
        p = je_art.setdefault(a["art"], [0, 0])
        p[0] += punkt
        p[1] += 1
        details.append(dict(art=a["art"], eingabe=str(a["eingabe"])[:200], antwort=str(antwort)[:300], punkt=punkt,
                            grund=grund))
    if fortschritt:
        fortschritt(len(liste), len(liste))
    punkte = sum(d["punkt"] for d in details)
    return dict(modell=modell.get("name"), punkte=punkte, max=len(details),
                quote=round(punkte / len(details), 3) if details else 0.0, je_art=je_art, details=details,
                dauer_s=round(time.perf_counter() - t0, 1), pruefsatz=PRUEFSATZ, fehler=fehler)


ART_TITEL = {"einordnen": "Einordnen", "auslesen": "Auslesen", "absage": "Absage", "erklaeren": "Erklären",
             "eigen_einordnen": "eigene Fragen", "eigen_absage": "eigene Absagen", "eigen_mail_art": "eigene Mail-Arten",
             "eigen_step_art": "eigene STEP-Teile"}


def text(e):
    if not e:
        return "Noch nicht geprüft."
    arten = ", ".join(f"{ART_TITEL.get(a, a)} {p}/{n}" for a, (p, n) in sorted((e.get("je_art") or {}).items()))
    return (f"{e.get('punkte')}/{e.get('max')} Punkte ({(e.get('quote') or 0):.0%}) – {arten}"
            + (f" · {e['fehler']} ohne Antwort" if e.get("fehler") else ""))
