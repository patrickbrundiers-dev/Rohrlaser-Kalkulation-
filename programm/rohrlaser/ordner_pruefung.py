"""Gemeinsamen Ordner prüfen (Patrick 31.10.2026, Plan „Gemeinsamen Ordner weiter ausbauen“, Paket A Baustein 3).

Eine Prüfung ohne Qt: Ordner erreichbar, Schreiben/Lesen und Geschwindigkeit, Uhr gegenüber dem Ordner, eigenes
Kürzel, Programmversion und letzter Abgleich der Kollegen, alte Dateien (Format 1), Konfliktkopien (OneDrive,
SharePoint, Dropbox, Nextcloud), doppelt reservierte Nummern, vorläufige Nummern, liegengebliebene Zwischendateien und
freier Platz. Ergebnis: Liste von Befunden {stufe, titel, text, tun} mit stufe OK, HINWEIS oder FEHLER. kurz() liefert
die wichtigsten Warnungen für die Statuszeile, ohne den Ordner zu beschreiben.
"""
import datetime
import shutil

from . import VERSION, nummern, teilen

OK, HINWEIS, FEHLER = "ok", "hinweis", "fehler"
LANGSAM_MB_S = 0.5              # langsamer: Hinweis (Abgleich und Angebotsordner werden zäh)
ALT_TAGE = 30                   # so lange nicht abgeglichen: Hinweis (Mitarbeiter ausgeschieden?)
PLATZ_MIN_GB = 1.0
SYMBOL = {OK: "✓", HINWEIS: "⚠", FEHLER: "✗"}


def _befund(stufe, titel, text, tun=""):
    return dict(stufe=stufe, titel=titel, text=text, tun=tun)


def _version(v):
    try:
        return tuple(int(x) for x in str(v or "").split("."))
    except ValueError:
        return ()


def _datum(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso or ""))
    except ValueError:
        return None


def kopie_text(c):
    """„Rohrlaser_PB/haupt-PC01.sqlite (Kopie von haupt.sqlite)“"""
    ort = f"{c['bereich']}/" if c["bereich"] else ""
    return f"{ort}{c['pfad'].name} (Kopie von {c['original']})"


def pruefen(db, geschwindigkeit=True):
    """Alle Prüfungen; geschwindigkeit=False lässt die Testdatei (1 MB) weg."""
    out = []
    ordner, k = teilen.ordner(db), teilen.kuerzel(db)
    if ordner is None:
        return [_befund(FEHLER, "Gemeinsamer Ordner", "Es ist kein gemeinsamer Ordner eingetragen.",
                        "Datei → Benutzer und gemeinsamer Ordner …")]
    w = teilen.weg(db)
    if not w.erreichbar():
        return [_befund(FEHLER, "Gemeinsamer Ordner", f"Nicht erreichbar: {ordner}",
                        "Netzlaufwerk verbinden bzw. OneDrive starten, dann erneut prüfen.")]
    out.append(_befund(OK, "Gemeinsamer Ordner", f"Erreichbar: {ordner}"))
    if not k:
        out.append(_befund(FEHLER, "Kürzel", "Kein Kürzel eingetragen.", "Datei → Benutzer und gemeinsamer Ordner …"))
        return out

    # ---- Schreiben, Lesen, Geschwindigkeit
    if geschwindigkeit:
        try:
            g = w.geschwindigkeit(k)
            text = (f"Schreiben und Lesen gehen ({g['mb_s']:.1f} MB/s schreiben, 1 MB in {g['schreiben_s']:.2f} s, "
                    f"lesen {g['lesen_s']:.2f} s).")
            if g["mb_s"] < LANGSAM_MB_S:
                out.append(_befund(HINWEIS, "Geschwindigkeit", text,
                                   "Langsame Verbindung (VPN, WLAN?): Abgleich und Angebotsordner brauchen länger."))
            else:
                out.append(_befund(OK, "Geschwindigkeit", text))
        except OSError as e:
            out.append(_befund(FEHLER, "Schreibrechte", f"Im eigenen Ordner lässt sich nicht schreiben: {e}",
                               "Schreibrechte für den gemeinsamen Ordner geben lassen."))

    # ---- Uhr
    v = w.uhr_messen(k)
    teilen.uhr_merken(db, v)
    if v is None:
        out.append(_befund(HINWEIS, "Uhr", "Die Uhr des Ordners ließ sich nicht messen (Ordner zu langsam).",
                           "Später erneut prüfen."))
    elif abs(v) > teilen.UHR_HOECHSTENS:
        out.append(_befund(FEHLER, "Uhr", f"Die PC-Uhr geht gegenüber dem gemeinsamen Ordner {teilen.uhr_text(v)}. "
                                          "Das ist mehr als ein Tag; der Abgleich rechnet das nicht heraus.",
                           "Datum und Uhrzeit des PCs (oder des Datei-Servers) richtig stellen."))
    elif abs(v) >= teilen.UHR_HINWEIS_AB:
        out.append(_befund(HINWEIS, "Uhr", f"Die PC-Uhr geht gegenüber dem gemeinsamen Ordner {teilen.uhr_text(v)}. "
                                           "Der Abgleich rechnet die Abweichung heraus.",
                           "Uhrzeit des PCs automatisch stellen lassen (Windows: Einstellungen → Zeit)."))
    else:
        out.append(_befund(OK, "Uhr", f"PC-Uhr und gemeinsamer Ordner stimmen überein (Abweichung "
                                      f"{abs(v):.0f} s)." + (" Wird herausgerechnet." if teilen.uhr_versatz(db) else "")))

    # ---- eigenes Kürzel
    haupt = w.haupt(k)
    if haupt is not None:
        info = teilen.info_lesen(haupt)
        if info and info.get("installation") not in (None, teilen.installation(db)):
            wer = ", ".join(x for x in (info.get("name"), info.get("rechner")) if x) or "unbekannt"
            out.append(_befund(FEHLER, "Kürzel", f"Das Kürzel {k} benutzt auch ein anderer Arbeitsplatz ({wer}).",
                               "Jeder Arbeitsplatz braucht ein eigenes Kürzel (Datei → Benutzer …)."))
        else:
            out.append(_befund(OK, "Kürzel", f"Das Kürzel {k} gehört diesem Arbeitsplatz."))
    else:
        out.append(_befund(HINWEIS, "Kürzel", f"Im Ordner liegen noch keine Daten von {k}.",
                           "Datei → Mit den Kollegen abgleichen."))

    # ---- Kollegen
    try:
        andere = w.mitarbeiter(k, teilen.kuerzel_sauber)
    except OSError:
        andere = {}
    eigen = _version(VERSION)
    jetzt = datetime.datetime.now()
    alle_gut = True
    for k2, pfad in sorted(andere.items()):
        info = teilen.info_lesen(pfad)
        name = f"{k2} {info.get('name') or ''}".strip()
        if not info:
            out.append(_befund(HINWEIS, f"Kollege {k2}", "Datei nicht lesbar (wird vielleicht gerade geschrieben).",
                               "Später erneut prüfen."))
            alle_gut = False
            continue
        v2 = _version(info.get("version"))
        if pfad.name == teilen.datei_name(k2):
            out.append(_befund(HINWEIS, f"Kollege {name}", f"Arbeitet noch mit dem alten Dateiformat 1 (Programm "
                                                           f"{info.get('version') or 'vor 0.9.185'}).",
                               "Programm dort aktualisieren."))
            alle_gut = False
        elif v2 and eigen and v2 < eigen:
            out.append(_befund(HINWEIS, f"Kollege {name}", f"Hat eine ältere Programmversion ({info.get('version')}).",
                               "Programm dort aktualisieren (Hilfe → Nach Updates suchen …)."))
            alle_gut = False
        elif v2 and eigen and v2 > eigen:
            out.append(_befund(HINWEIS, f"Kollege {name}", f"Hat eine neuere Programmversion ({info.get('version')}).",
                               "Dieses Programm aktualisieren."))
            alle_gut = False
        stand = _datum(info.get("stand"))
        if stand and (jetzt - stand).days >= ALT_TAGE:
            out.append(_befund(HINWEIS, f"Kollege {name}", f"Seit {(jetzt - stand).days} Tagen nicht abgeglichen "
                                                           f"(zuletzt {stand:%d.%m.%Y}).",
                               "Ausgeschieden? Dann seine Angebote übernehmen lassen."))
            alle_gut = False
        u2 = info.get("uhr_abweichung")
        if isinstance(u2, (int, float)) and abs(u2) >= teilen.UHR_HINWEIS_AB:
            out.append(_befund(HINWEIS, f"Kollege {name}", f"Seine PC-Uhr geht {teilen.uhr_text(u2)}"
                                                           + (" (wird herausgerechnet)." if info.get("uhr_versatz")
                                                              else "."),
                               "Uhrzeit dort automatisch stellen lassen."))
            alle_gut = False
    if andere and alle_gut:
        out.append(_befund(OK, "Kollegen", f"{len(andere)} Kollegen ({', '.join(sorted(andere))}): gleiche Version, "
                                           "zuletzt abgeglichen in den letzten 30 Tagen."))
    elif not andere:
        out.append(_befund(OK, "Kollegen", "Noch keine Kollegen im Ordner."))

    # ---- Konfliktkopien
    try:
        kopien = teilen.konfliktkopien(db)
    except OSError:
        kopien = []
    for c in kopien:
        if c["pfad"].suffix == ".nummer":
            nr = c["original"].removesuffix(".nummer")
            bereich = "AB-Nummer" if c["bereich"] == "AB-Nummern" else "Angebotsnummer"
            out.append(_befund(FEHLER, "Doppelte Nummer",
                               f"{bereich} mit Zählerstand {int(nr)} wurde zweimal reserviert ({kopie_text(c)}"
                               + (f", Kopie von {c['kuerzel']}" if c["kuerzel"] else "") + ").",
                               "Prüfen, welches Angebot die Nummer behält; das andere neu anlegen. Danach die Kopie "
                               "löschen."))
        elif c["eigene"]:
            out.append(_befund(HINWEIS, "Konfliktkopie", f"Eigene: {kopie_text(c)}.",
                               "„Eigene aufräumen“ oder nächster Abgleich: kommt nach Daten/Teilen/Konfliktkopien."))
        else:
            wem = f" von {c['kuerzel']}" if c["kuerzel"] else ""
            out.append(_befund(HINWEIS, "Konfliktkopie", f"Fremde{wem}: {kopie_text(c)}.",
                               "Räumt der Kollege beim nächsten Abgleich selbst auf; bleibt sie, löschen."))
    if not kopien:
        out.append(_befund(OK, "Konfliktkopien", "Keine Konfliktkopien im gemeinsamen Ordner."))

    # ---- Zwischendateien, vorläufige Nummern, Platz
    try:
        reste = w.reste()
    except OSError:
        reste = []
    if reste:
        out.append(_befund(HINWEIS, "Abgebrochene Schreibvorgänge",
                           f"{len(reste)} Zwischendateien (*.neu) älter als 1 Stunde: "
                           + ", ".join(f"{p.parent.name}/{p.name}" for p in reste[:5]) + (" …" if len(reste) > 5 else ""),
                           "Eigene räumt der nächste Abgleich auf; fremde dürfen gelöscht werden."))
    vorl = [r[0] for r in db.con.execute("SELECT nummer FROM angebote WHERE fremd IS NULL OR fremd=''")
            if nummern.vorlaeufig(r[0])]
    if vorl:
        out.append(_befund(HINWEIS, "Vorläufige Nummern", f"{len(vorl)} eigene Angebote haben noch eine vorläufige "
                                                         f"Nummer ({', '.join(vorl[:5])}" + (" …" if len(vorl) > 5 else "")
                           + ").", "Mit den Kollegen abgleichen: dann kommt die endgültige Nummer."))
    try:
        frei = shutil.disk_usage(ordner).free / (1 << 30)
        if frei < PLATZ_MIN_GB:
            out.append(_befund(HINWEIS, "Speicherplatz", f"Im gemeinsamen Ordner sind nur noch {frei:.2f} GB frei.",
                               "Platz schaffen (alte Sicherungen, Angebotsordner)."))
    except OSError:
        pass
    return out


def kurz(db):
    """Wichtigste Warnungen für die Statuszeile (ohne in den Ordner zu schreiben): PC-Uhr, doppelte Nummern, fremde
    Konfliktkopien. [Text …]"""
    out = []
    v = teilen.uhr_abweichung(db)
    if v is not None and abs(v) >= teilen.UHR_HINWEIS_AB:
        out.append(f"PC-Uhr geht {teilen.uhr_text(v)}")
    try:
        kopien = teilen.konfliktkopien(db)
    except OSError:
        kopien = []
    from . import admin_schutz          # fremde Kopien gehen den Admin an (ohne Admin-Schutz: jeden)
    doppelt = sum(1 for c in kopien if c["pfad"].suffix == ".nummer")
    fremde = sum(1 for c in kopien if not c["eigene"] and c["pfad"].suffix != ".nummer") \
        if admin_schutz.ist_admin(db) else 0
    if doppelt:
        out.append(f"{doppelt} doppelte Nummer" + ("n" if doppelt > 1 else ""))
    if fremde:
        out.append(f"{fremde} Konfliktkopie" + ("n" if fremde > 1 else ""))
    return out


def bericht_text(befunde):
    """Befunde als Text zum Kopieren."""
    zeilen = []
    for b in befunde:
        zeilen.append(f"{SYMBOL[b['stufe']]} {b['titel']}: {b['text']}" + (f"  → {b['tun']}" if b["tun"] else ""))
    return "\n".join(zeilen)
