"""KI 3, Paket D „Bedienung“ (Plan 20.11.2026, Freigabe Patrick „Alles einbauen nach Empfehlungen“). Ohne Qt.

hilfe(db, frage)               Fragen zur Bedienung aus der Bedienungsanleitung beantworten (Abschnitte mit Quelle)
fehler_erklaeren(ordner)       Fehler im Protokoll (fehler.log) verständlich erklären, mit Lösungsvorschlag
liefertermin(db, ctx)          Engpässe der Laser-Auslastung in Worten und frühester realistischer Liefertermin

Alles regelbasiert aus den Programmdaten; ein Sprachmodell formuliert höchstens um (Faktencheck im Orchestrator).
Nichts wird geändert, nichts geht ins Internet."""
import datetime
import re
from pathlib import Path

from . import protokoll

# ------------------------------------------------------------------ Hilfe aus der Anleitung
HILFE_N = 3


def hilfe(db, frage, n=HILFE_N, senden=None):
    """[dict(titel, text, quelle)] – die passendsten Abschnitte der Bedienungsanleitung."""
    from . import ki_wissen
    treffer = [t for t in ki_wissen.suchen(db, frage, n=25, senden=senden) if t.get("art") == "anleitung"]
    if not treffer:         # Index ohne Anleitung (z. B. alter Index): direkt in den Abschnitten suchen
        w = set(ki_wissen.woerter(frage))
        abschnitte = ki_wissen.anleitung_abschnitte()
        bewertet = sorted(((len(w & set(ki_wissen.woerter(a["titel"] + " " + a["text"]))), a) for a in abschnitte),
                          key=lambda x: -x[0])
        treffer = [a for p, a in bewertet if p > 0]
    out = []
    for t in treffer[:n]:
        text = re.sub(r"\s+", " ", t.get("text") or "").strip()
        out.append(dict(titel=str(t.get("titel") or "").replace("Anleitung: ", ""), text=text[:600],
                        quelle="Bedienungsanleitung"))
    return out


def hilfe_text(liste):
    if not liste:
        return ("Dazu steht nichts in der Bedienungsanleitung. Tipp: Strg+K (Befehlspalette) findet Befehle und "
                "Einstellungen nach Namen.")
    return "\n\n".join(f"Abschnitt „{x['titel']}“:\n{x['text']}" for x in liste) + \
        "\n\n(Hilfe → Bedienungsanleitung öffnet die ganze Anleitung.)"


# ------------------------------------------------------------------ Fehlermeldungen erklären
# (Muster im Fehlertext, Erklärung, Lösung) – erste passende Zeile gewinnt
FEHLERBILDER = (
    (r"No module named '?OCP|OCC|cadquery", "Die STEP-Bibliothek fehlt oder ist beschädigt.",
     "Programm über Hilfe → Update-Center neu einspielen; die portable ZIP komplett entpacken."),
    (r"database is locked|could not obtain lock|deadlock", "Die Datenbank war gerade von einem anderen Vorgang belegt.",
     "Kurz warten und wiederholen; bleibt es, das Programm neu starten."),
    (r"connection refused|could not connect to server|server closed the connection|psycopg.*Operational",
     "Die lokale PostgreSQL-Datenbank war nicht erreichbar.",
     "Programm neu starten (es startet die Datenbank selbst). Bleibt es, Supportpaket erstellen."),
    (r"PermissionError|Zugriff verweigert|Permission denied|WinError 5\b|WinError 32\b",
     "Auf eine Datei oder einen Ordner durfte nicht zugegriffen werden (geöffnet in einem anderen Programm oder keine "
     "Rechte im Netzwerkordner).", "Datei in Excel/PDF-Anzeige schließen bzw. Rechte im Netzwerkordner prüfen."),
    (r"FileNotFoundError|No such file|WinError 2\b|WinError 3\b",
     "Eine Datei oder ein Ordner wurde nicht gefunden (verschoben, umbenannt oder Netzlaufwerk nicht verbunden).",
     "Pfad in den Einstellungen prüfen, Netzlaufwerk verbinden."),
    (r"No space left|Errno 28|Datenträger.*voll", "Der Datenträger ist voll.",
     "Platz schaffen (alte Supportpakete, Sicherungen) und wiederholen."),
    (r"MemoryError|Speicher reicht nicht|out of memory", "Der Arbeitsspeicher hat nicht gereicht (meist sehr große "
     "STEP-Dateien).", "Andere Programme schließen, STEP in kleineren Teilen einlesen."),
    (r"TimeoutError|timed out|Zeitüberschreitung|ConnectionResetError|getaddrinfo",
     "Eine Verbindung im Firmennetz hat nicht geantwortet (Netzwerkordner, KI-Server, Mailserver).",
     "Netzwerk prüfen und wiederholen."),
    (r"UnicodeDecodeError|codec can't decode", "Eine Datei hatte eine unerwartete Zeichenkodierung.",
     "Datei als UTF-8 bzw. aus dem Originalprogramm neu speichern."),
    (r"Lizenz|license", "Ein Lizenzproblem.", "Hilfe → Lizenz prüfen; Lizenz für diesen PC einspielen."),
    (r"KiFehler|Sprachmodell|ollama", "Das lokale Sprachmodell hat nicht geantwortet.",
     "KI-Zentrale → Modelle: Ollama starten bzw. „Testen“; ohne Modell läuft alles regelbasiert weiter."),
    (r"ZeroDivisionError|KeyError|TypeError|AttributeError|IndexError|ValueError",
     "Ein Programmfehler bei ungewöhnlichen Daten.",
     "Hilfe → Support-Paket erstellen und schicken; die Daten bleiben erhalten."),
)


def fehler_erklaeren(ordner, seit=None, n=5):
    """[dict(zeit, fehler, erklaerung, loesung, anzahl)] – die letzten verschiedenen Fehler aus dem Protokoll,
    neueste zuerst; seit Vorgabe: 7 Tage."""
    seit = seit or (datetime.datetime.now() - datetime.timedelta(days=7))
    try:
        liste = protokoll.fehler_seit(Path(ordner), seit)
    except Exception:       # noqa: BLE001 – Protokoll nicht lesbar: einfach keine Erklärung
        protokoll.warnung("ki_hilfe: Protokoll nicht lesbar")
        return []
    je = {}
    for zeit, text in liste:
        e = je.setdefault(text, dict(zeit=zeit, fehler=text, anzahl=0))
        e["anzahl"] += 1
        e["zeit"] = max(e["zeit"], zeit)
    out = []
    for e in sorted(je.values(), key=lambda x: x["zeit"], reverse=True)[:n]:
        erk, loe = "Unbekannter Fehler.", "Hilfe → Support-Paket erstellen und schicken."
        for muster, a, b in FEHLERBILDER:
            if re.search(muster, e["fehler"], re.I):
                erk, loe = a, b
                break
        out.append(dict(e, erklaerung=erk, loesung=loe))
    return out


def fehler_text(liste):
    if not liste:
        return "Im Fehlerprotokoll der letzten 7 Tage steht kein Fehler."
    return "\n".join(f"• {e['zeit']:%d.%m. %H:%M} ({e['anzahl']}×) {e['fehler']}\n  → {e['erklaerung']} "
                     f"Lösung: {e['loesung']}" for e in liste)


# ------------------------------------------------------------------ Engpässe und Liefertermin
VOLL_AB = 1.0           # Auslastung ab der eine Woche als voll gilt


def liefertermin(db, angebot_id=None, heute=None, wochen=10):
    """dict(engpaesse [Text], woche (Montag) oder None, kw, stunden, text): volle Wochen je Maschine und für das
    Angebot die erste Woche, in der seine Laserzeit noch in die Kapazität passt (vor dem Vorlauf für Entgraten und
    Versand). Rechnet mit den beauftragten Aufträgen (auslastung.berechnen)."""
    from . import auslastung
    heute = heute or datetime.date.today()
    a = auslastung.berechnen(db, heute=heute, wochen=wochen)
    wochen_ = [s for s, _, m in a["spalten"] if m is not None]
    engpaesse = []
    for m in a["maschinen"]:
        for w in wochen_:
            kap, bed = a["kapazitaet"].get((m, w), 0.0), a["bedarf"].get((m, w), 0.0)
            if kap > 0 and bed / kap >= VOLL_AB:
                engpaesse.append(f"{m} KW {w.isocalendar()[1]}: {bed:.0f} h Bedarf bei {kap:.0f} h Kapazität "
                                 f"({100 * bed / kap:.0f} %)")
    erg = dict(engpaesse=engpaesse, woche=None, kw=None, stunden=None, maschinen=a["maschinen"])
    if angebot_id is not None:
        kopf = db.angebot(angebot_id) or {}
        try:
            je = auslastung.maschinenzeit_je(db, kopf) or {}
        except Exception:       # noqa: BLE001 – nicht optimiert o. ä.
            protokoll.warnung("ki_hilfe: Maschinenzeit nicht berechenbar")
            je = {}
        if je:
            stunden = {m: h * (1 - f) for m, (h, f) in je.items()}
            erg["stunden"] = round(sum(stunden.values()), 1)
            for w in wochen_:
                if w < auslastung.montag(heute):
                    continue
                if all(a["kapazitaet"].get((m, w), 0.0) - a["bedarf"].get((m, w), 0.0) >= h for m, h in stunden.items()
                       if h > 0):
                    erg["woche"], erg["kw"] = w, w.isocalendar()[1]
                    break
            if erg["woche"] is not None:
                from . import feiertage
                tage = int(float(db.einstellung("auslastung_vorlauf") or 2))
                land = db.einstellung("versand_bundesland") or feiertage.VORGABE
                erg["liefertag"] = feiertage.arbeitstage_spaeter(erg["woche"] + datetime.timedelta(days=4), tage, land)
    teile = []
    teile.append(("Engpässe: " + "; ".join(engpaesse)) if engpaesse else
                 f"Keine volle Woche in den nächsten {wochen} Wochen (beauftragte Aufträge).")
    if erg.get("stunden") is not None:
        if erg["woche"] is not None:
            teile.append(f"Dieses Angebot braucht {str(erg['stunden']).replace('.', ',')} h Laser und passt ab KW {erg['kw']}; "
                         f"realistischer Liefertermin mit Vorlauf: {erg['liefertag']:%d.%m.%Y}.")
        else:
            teile.append(f"Dieses Angebot braucht {str(erg['stunden']).replace('.', ',')} h Laser und passt in den nächsten {wochen} "
                         "Wochen in keine Woche ganz – Termin mit der Fertigung abstimmen.")
    elif angebot_id is not None:
        teile.append("Für einen Termin bitte das Angebot zuerst optimieren.")
    erg["text"] = "\n".join(teile)
    return erg
