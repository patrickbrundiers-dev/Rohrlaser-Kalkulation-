"""STEP-Messung für den STEP-Import des Programms (wird als STEP-Import.exe ausgeliefert).

Misst je Körper Profil, Länge, Schneidweg und Konturen (step_geometrie.py), dazu Importdaten (Einheit der Datei,
Körperart, Geometrieprüfung, Volumen, Oberfläche, Flächen-/Kantenzahl, Hüllquader, Meldungen des STEP-Lesers).
Flächenmodelle werden zu Volumen genäht; was nicht messbar ist, steht mit Hinweis als eigene Zeile drin.
und schreibt die Messwerte als Textdatei (UTF-8, Tabulator-getrennt, Dezimalpunkt).
"STEP importieren" im Programm startet diese Messung und übernimmt die Werte ins Angebot.

Aufruf:
    STEP-Import.exe --ausgabe MESSWERTE.txt [--json ERGEBNIS.json] [--netze ORDNER] [--flachstahl-bis MM]
                    (--liste DATEILISTE.txt | DATEI_ODER_ORDNER ...)

--json ERGEBNIS.json: alle Messwerte zusätzlich im versionierten JSON-Format (step_ergebnis.py, Schema-Version darin).

--flachstahl-bis MM: größte Breite eines Flachstahls (Vorgabe 150); breitere oder kurze flache Teile gelten als Blech.
  0 = ebene flache Teile immer als Blech (Vorgabe im Programm), Flachstahl steht dann in der Spalte "alternative".

--netze ORDNER: je Teil zusätzlich ein Dreiecksnetz für die 3D-Ansicht als JSON-Datei (Spalte "netz" = Dateiname);
  "lage" = Einbaulage in der Datei (Ende A, Rohrachse, X-Richtung), damit Baugruppen zusammengesetzt gezeigt werden.

--flach-laenge F, --gekantet-anteil A: Grenzwerte der Erkennung aus den Einstellungen (step_geometrie.einstellen).

--prozesse N: gleichzeitige Messprozesse (0 = automatisch, Kerne − 1). --zeitlimit S: Sekunden je Körper (0 = ohne);
  mit Zeitlimit misst jeder Prozess unter Aufsicht: braucht ein Körper länger (oder stürzt die Messung ab), wird der
  Prozess beendet, der Körper als "nicht gemessen" gemeldet und die Datei ohne ihn weiter gemessen.

--cache ORDNER [--cache-mb MB] [--kennung TEXT]: Zwischenspeicher. Schlüssel = SHA-256 der Datei + Kennung
  (Programmversion) + wirksame Einstellungen; gleiche Datei mit gleichen Einstellungen wird nicht neu gemessen.
  Älteste Einträge fallen weg, wenn der Ordner größer als MB wird.

Fortschritt auf stdout: "[n/m] Datei" je fertiger Datei und JSON-Zeilen {"datei": n, "dateien": m, "name": …,
  "koerper": k, "koerper_n": K} je Körper (mit Zeitlimit). Die Messwerte stehen schon während der Messung je fertiger
  Datei in der Ausgabe (Teilergebnis bei Abbruch); am Ende wird sie in der Reihenfolge der Dateien neu geschrieben.

STEP-Export (Plan 3D-Editor 3E-8): STEP-Import.exe --export BAUPLAN.json --step ZIEL.step --ergebnis ERGEBNIS.json
  baut Volumenkörper aus einem Bauplan des Programms (step_schreiben.py).

DATEILISTE.txt: ein Pfad je Zeile (UTF-8). Rückgabewert 0 = alle Dateien gelesen,
1 = mindestens eine Datei mit Fehler (steht in der Spalte "fehler"), 2 = Aufruf falsch.
"""
import argparse
import hashlib
import json
import os
import queue
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import step_ergebnis  # noqa: E402
import step_geometrie  # noqa: E402
from step_geometrie import FLACHSTAHL_BIS, analysiere_datei  # noqa: E402

TEILEN_AB = int(os.environ.get("STEP_MESSEN_TEILEN_AB", 4))    # Datei auf Prozesse verteilen ab so vielen Körpern
PROZESSE_MAX = 4      # ohne Zeitlimit: gleichzeitige Messprozesse bei vielen Dateien (jeder lädt OpenCascade einmal)
SPALTEN = ["datei", "artikel", "koerper", "profilform", "abm_a", "abm_b", "wandstaerke", "flaeche", "laenge",
           "schneidweg", "konturen", "ende_a", "ende_a_gerade", "ende_b", "ende_b_gerade", "innen",
           "innen_konturen", "gravur", "gravur_konturen", "bohrungen", "innen_liste", "profil_id_vorschlag",
           "hinweise", "einheit", "koerperart", "gueltig", "volumen", "oberflaeche", "n_flaechen", "n_kanten",
           "huelle", "meldungen", "innen_a", "innen_b", "wand_messungen", "sicherheit", "konturen_liste",
           "pruefstatus", "netz", "bauteiltyp", "blech", "stegdicke", "flanschdicke", "normprofil",
           "symmetrisch", "radius", "ende_a_huelle", "ende_b_huelle", "senkungen", "fliessloecher", "anbauteile",
           "trennung", "gravur_anbau", "kammern", "kontur_umfang", "verbund", "bauteil", "pfad", "knoten", "ersatz",
           "biegerohr", "knick_schenkel", "offene_seite", "geschlossen", "alternative", "fehler"]
# Spalte "alternative": Grenzfall Flachstahl/Blech bzw. Profil/Kantteil, das Teil in der anderen Art gemessen, bzw.
# bei abgetrennten Anbauteilen die Messung ohne Trennung, als JSON {Spalte: Wert} mit den Messwerten (ohne Datei, Artikel, Körper, Netz); leer = keine Alternative
OHNE_ALTERNATIVE = ("datei", "artikel", "koerper", "netz", "bauteil", "pfad", "knoten", "geschlossen", "alternative",
                    "fehler")
# Spalte "geschlossen": offen gezeichnetes Quadrat-/Rechteckrohr (step_offenes_rohr), das Teil als Rohr mit Stegen
# gemessen, JSON {Spalte: Wert} wie "alternative"; leer = kein offenes Rohr
# Spalte "offene_seite": offen gezeichnetes Rohr als Rohr gemessen (in "geschlossen" bzw. nach dem Umschalten), JSON
# {seite, luecken, breite, laenge, vorher, steg, radius, ueberstand, normrohr, …}; leer = keins
# Spalte "knick_schenkel": Knickrahmen aus einem Körper (step_knickrahmen), die geraden Rohrstücke in Reihenfolge als
# JSON-Liste [{Spalte: Wert, "lage": [Ende A, Achse, X-Richtung in der Datei]}] (ohne OHNE_ALTERNATIVE); leer = keiner


def _z(x):
    return repr(float(x))


def _text(s):
    return str(s).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _lesen(datei):
    """Datei lesen (step_geometrie.datei_lesen); Pfade mit Umlauten o. ä. über eine Kopie mit einfachem Namen, weil
    OpenCascade solche Pfade unter Windows nicht in jeder Version öffnet."""
    if str(datei).isascii() or not datei.is_file():
        return step_geometrie.datei_lesen(datei)
    ordner = None   # auch der Temp-Ordner kann Umlaute enthalten (Benutzername)
    if not tempfile.gettempdir().isascii():
        ordner = next((p for p in (os.environ.get("PUBLIC"), os.environ.get("SystemDrive", "C:") + "\\")
                       if p and p.isascii() and os.access(p, os.W_OK)), None)
    with tempfile.TemporaryDirectory(dir=ordner) as tmp:
        kopie = Path(tmp) / "teil.step"
        shutil.copyfile(datei, kopie)
        return step_geometrie.datei_lesen(kopie, datei.stem)


def zeilen(datei, netze=None, nr=1, flach_bis=FLACHSTAHL_BIS):
    """Messwerte einer Datei als Zeilen (Liste von Feldern in der Reihenfolge SPALTEN). netze: Ordner für die
    Dreiecksnetze (None = keine), nr: laufende Nummer der Datei (Name der Netzdateien)."""
    return messen(datei, netze, nr, flach_bis)[0]


def messen(datei, netze=None, nr=1, flach_bis=FLACHSTAHL_BIS, einst=None, auslassen=None, melden=None, gel=None,
           vorgemessen=None):
    """Wie zeilen, dazu das Ergebnis im versionierten JSON-Format (step_ergebnis.datei). einst: Grenzwerte der
    Erkennung (step_geometrie.einstellen), auslassen/melden wie analysiere_datei. gel: schon gelesene Datei (_lesen);
    vorgemessen: {Körpernummer: Teil} aus anderen Prozessen, dann nur noch datei_abschliessen."""
    step_geometrie.einstellen(einst)
    try:
        gel = gel or _lesen(datei)
        if vorgemessen is not None:
            if melden:
                melden(len(gel.koerper) + 1, len(gel.koerper))
            teile = step_geometrie.datei_abschliessen(gel, vorgemessen, netze is not None, flach_bis, auslassen)
        else:
            teile = analysiere_datei(datei, netze is not None, flach_bis, auslassen, melden, gel)
    except Exception as e:  # Datei defekt o. ä.: als Fehlerzeile melden
        return _fehler_ergebnis(datei, _text(e) or type(e).__name__)
    out = []
    for t in teile:
        artikel = t.datei if len(teile) == 1 else f"{t.datei}-K{t.koerper}"
        netz = ""
        if netze is not None and t.netz:
            netz = f"{nr:05d}_{t.koerper}.json"
            if "lage" not in t.netz and t.ende_a_global and t.achse_global and t.x_global:   # Einbaulage (Baugruppe)
                t.netz["lage"] = [round(v, 6) for v in (*t.ende_a_global, *t.achse_global, *t.x_global)]
            (Path(netze) / netz).write_text(json.dumps(t.netz, separators=(",", ":")), encoding="utf-8")
        z = _zeile(t, datei.name, artikel, netz)
        if t.geschlossen is not None:
            zu = dict(zip(SPALTEN, _zeile(t.geschlossen, datei.name, artikel, netz)))
            z[SPALTEN.index("geschlossen")] = json.dumps({k: v for k, v in zu.items() if k not in OHNE_ALTERNATIVE},
                                                         ensure_ascii=False, separators=(",", ":"))
        if t.alternative is not None:
            alt = dict(zip(SPALTEN, _zeile(t.alternative, datei.name, artikel, netz)))
            z[SPALTEN.index("alternative")] = json.dumps({k: v for k, v in alt.items() if k not in OHNE_ALTERNATIVE},
                                                         ensure_ascii=False, separators=(",", ":"))
        out.append(z)
    return out, step_ergebnis.datei(datei.name, teile)


def _zeile(t, name, artikel, netz):
    """Messwerte eines Teils als Felder in der Reihenfolge SPALTEN (Spalten geschlossen und alternative leer)."""
    return ([name, artikel, str(t.koerper), t.profilform, _z(t.abm_a), _z(t.abm_b), _z(t.wandstaerke),
            _z(t.flaeche), _z(t.laenge), _z(t.schneidweg), str(t.konturen), _z(t.ende_a),
            "1" if t.ende_a_gerade else "0", _z(t.ende_b), "1" if t.ende_b_gerade else "0", _z(t.innen),
            str(t.innen_konturen), _z(t.gravur), str(t.gravur_konturen),
            "|".join(f"{_z(d)}:{n}" for d, n in t.bohrungen.items()),
            "|".join(f"{_z(g)}:{_z(l)}" for g, l in t.innen_liste),
            t.profil_id_vorschlag, _text("; ".join(t.hinweise)), t.einheit, t.koerperart,
            "" if t.gueltig is None else "1" if t.gueltig else "0", _z(t.volumen), _z(t.oberflaeche),
            str(t.n_flaechen), str(t.n_kanten), "|".join(_z(x) for x in t.huelle),
            _text("; ".join(t.meldungen)), _z(t.innen_a), _z(t.innen_b),
            "|".join(":".join([_z(z), _z(x), _z(y), _z(w), s]) for z, x, y, w, s in t.wand_messungen),
            ";".join(f"{k}={v}" for k, v in t.sicherheit.items()),
            json.dumps(t.konturen_liste, ensure_ascii=False, separators=(",", ":")), t.pruefstatus, netz,
            t.bauteiltyp, json.dumps(t.blech, ensure_ascii=False, separators=(",", ":")) if t.blech else "",
            _z(t.stegdicke), _z(t.flanschdicke), t.normprofil,
            "" if t.symmetrisch is None else "1" if t.symmetrisch else "0", _z(t.radius),
            _z(t.ende_a_huelle), _z(t.ende_b_huelle),
            "|".join(f"{_z(d)}/{_z(s_)}:{n}" for (d, s_), n in sorted(t.senkungen.items())),
            "|".join(f"{_z(d)}:{n}" for d, n in sorted(t.fliessloecher.items())),
            json.dumps(t.anbauteile, ensure_ascii=False, separators=(",", ":")) if t.anbauteile else "",
            json.dumps(t.trennung, ensure_ascii=False, separators=(",", ":")) if t.trennung else "",
            _z(t.gravur_anbau) if t.anbauteile else "",
            str(t.kammern) if t.kammern else "", _z(t.kontur_umfang) if t.kontur_umfang else "", _text(t.verbund),
            _text(t.bauteil), _text(t.pfad), t.knoten, "1" if t.ersatz else "",
            json.dumps(t.biegerohr, ensure_ascii=False, separators=(",", ":")) if t.biegerohr else "",
            _knick_schenkel(t),
            json.dumps(t.offene_seite, ensure_ascii=False, separators=(",", ":")) if t.offene_seite else "",
            "", "", ""])


def _knick_schenkel(t):
    if not t.knick_schenkel:
        return ""
    out = []
    for x in t.knick_schenkel:
        d = {k: v for k, v in zip(SPALTEN, _zeile(x, "", "", "")) if k not in OHNE_ALTERNATIVE + ("knick_schenkel",)}
        if x.ende_a_global and x.achse_global and x.x_global:
            d["lage"] = [round(v, 6) for v in (*x.ende_a_global, *x.achse_global, *x.x_global)]
        out.append(d)
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def step_dateien(pfade):
    out = []
    for p in map(Path, pfade):
        if p.is_dir():
            out += sorted(x for x in p.iterdir() if x.suffix.lower() in (".step", ".stp"))
        else:
            out.append(p)
    return out


# ------------------------------------------------------------------ Zwischenspeicher
def cache_schluessel(datei, kennung, einst):
    """SHA-256 über Inhalt der Datei, Kennung (Programmversion) und wirksame Einstellungen der Messung."""
    h = hashlib.sha256()
    with open(datei, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    h.update(json.dumps([kennung, step_ergebnis.SCHEMA_VERSION, einst], sort_keys=True).encode("utf-8"))
    return h.hexdigest()


def cache_lesen(ordner, schluessel, netze, nr):
    """Ergebnis aus dem Zwischenspeicher (Zeilen, JSON) mit Netzen für die laufende Nummer nr, oder None."""
    eintrag = Path(ordner) / schluessel
    try:
        daten = json.loads((eintrag / "ergebnis.json").read_text(encoding="utf-8"))
        alt, neu = f"{int(daten['nr']):05d}_", f"{nr:05d}_"
        i = SPALTEN.index("netz")
        zeilen_ = daten["zeilen"]
        for z in zeilen_:
            if z[i].startswith(alt):
                if netze is None:
                    z[i] = ""
                    continue
                ziel = Path(netze) / (neu + z[i][len(alt):])
                shutil.copyfile(eintrag / z[i], ziel)
                z[i] = ziel.name
        os.utime(eintrag)           # zuletzt benutzt (Aufräumen nach Alter)
        return zeilen_, daten["json"]
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None


def cache_schreiben(ordner, schluessel, ergebnis, netze, nr, mb):
    """Messung einer Datei merken (nicht bei Fehlern oder ausgelassenen Körpern) und den Ordner auf mb MB
    begrenzen (älteste zuerst weg)."""
    zeilen_, js = ergebnis
    if any(z[-1] for z in zeilen_) or "nicht gemessen: " in json.dumps(js, ensure_ascii=False):
        return
    eintrag = Path(ordner) / schluessel
    tmp = Path(ordner) / (schluessel + ".neu")
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        i = SPALTEN.index("netz")
        for z in zeilen_:
            if z[i] and netze is not None:
                shutil.copyfile(Path(netze) / z[i], tmp / z[i])
        (tmp / "ergebnis.json").write_text(json.dumps(dict(nr=nr, zeilen=zeilen_, json=js), ensure_ascii=False),
                                           encoding="utf-8")
        shutil.rmtree(eintrag, ignore_errors=True)
        tmp.rename(eintrag)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)
        return
    cache_begrenzen(ordner, mb)


def cache_begrenzen(ordner, mb):
    eintraege = []
    for e in Path(ordner).iterdir():
        if e.is_dir() and not e.name.endswith(".neu"):
            try:
                eintraege.append((e.stat().st_mtime, sum(f.stat().st_size for f in e.iterdir()), e))
            except OSError:
                pass
    summe = sum(g for _, g, _ in eintraege)
    for _, g, e in sorted(eintraege, key=lambda x: x[0]):
        if summe <= mb * 1024 * 1024:
            break
        shutil.rmtree(e, ignore_errors=True)
        summe -= g


# ------------------------------------------------------------------ Messung unter Aufsicht (Zeitlimit)
def _arbeiter(auftraege, ereignisse, wid):
    """Messprozess: erledigt Aufträge (Schlüssel, Datei, netze, flach_bis, einst, auslassen, Zusatz) und meldet Körper
    und Ergebnis. Schlüssel ("datei", nr): ganze Datei messen; ist Zusatz = teilen_ab > 0 und hat die Datei
    mindestens so viele zu messende Körper, nur lesen und die Körper zurückmelden ("geteilt"). ("koerper", nr, k):
    einen Körper messen ("teil"). ("abschluss", nr): Zusatz = gemessene Teile, Datei fertig auswerten. Die zuletzt
    gelesene Datei bleibt im Speicher. Endet von selbst, wenn der aufsichtführende Prozess nicht mehr läuft (Abbruch
    im Programm beendet nur ihn)."""
    import multiprocessing as mp
    import threading

    def wache():
        eltern = mp.parent_process()
        while eltern is not None and eltern.is_alive():
            time.sleep(1)
        os._exit(3)
    threading.Thread(target=wache, daemon=True).start()
    gelesen = {}
    while True:
        a = auftraege.get()
        if a is None:
            return
        schluessel, datei, netze, flach_bis, einst, auslassen, zusatz = a
        datei = Path(datei)
        haengt = os.environ.get("STEP_MESSEN_TEST_HAENGT", "")      # nur für Tests: "Datei:Körper" hängt

        def melden(k, n, schluessel=schluessel, datei=datei):
            ereignisse.put(("koerper", wid, schluessel, k, n))
            if haengt == f"{datei.name}:{k}" and k not in auslassen:
                time.sleep(3600)
        if schluessel[0] == "datei":
            gelesen.clear()
            try:
                step_geometrie.einstellen(einst)
                gel = _lesen(datei)
            except Exception as e:  # wie messen: Fehlerzeile
                ereignisse.put(("fertig", wid, schluessel, _fehler_ergebnis(datei, _text(e) or type(e).__name__)))
                continue
            gelesen[str(datei)] = gel
            n = len(gel.koerper)
            messbar = [k for k in range(1, n + 1) if k not in gel.gleich and k not in auslassen]
            if zusatz and len(messbar) >= zusatz:
                ereignisse.put(("geteilt", wid, schluessel, messbar, n))
                continue
            erg = messen(datei, netze, schluessel[1], flach_bis, einst, auslassen, melden, gel)
            ereignisse.put(("fertig", wid, schluessel, erg))
            continue
        gel = gelesen.get(str(datei))
        if gel is None:
            gelesen.clear()
            step_geometrie.einstellen(einst)
            gel = gelesen[str(datei)] = _lesen(datei)
        if schluessel[0] == "koerper":
            step_geometrie.einstellen(einst)
            k = schluessel[2]
            melden(k, len(gel.koerper))
            t = step_geometrie.koerper_messen(gel, k, netze is not None, flach_bis, auslassen)
            ereignisse.put(("teil", wid, schluessel, step_geometrie.teil_uebergeben(t)))
        else:
            erg = messen(datei, netze, schluessel[1], flach_bis, einst, auslassen, melden, gel, zusatz)
            ereignisse.put(("fertig", wid, schluessel, erg))


def _fehler_ergebnis(datei, text):
    return ([[datei.name, datei.stem] + [""] * (len(SPALTEN) - 3) + [text]],
            step_ergebnis.datei(datei.name, fehler=text))


def _beaufsichtigt(auftraege, prozesse, zeitlimit, fertig, vorher=0, gesamt=None, teilen_ab=TEILEN_AB):
    """Aufträge {nr: (datei, netze, flach_bis, einst)} in prozesse Messprozessen messen. Braucht ein Körper länger
    als zeitlimit Sekunden oder stirbt der Prozess, wird er beendet und die Datei ohne diesen Körper neu gemessen
    (der Körper steht als "nicht gemessen" im Ergebnis). Sind Prozesse frei, wird eine Datei mit mindestens
    teilen_ab zu messenden Körpern auf die Prozesse verteilt (je Körper ein Auftrag, danach ein Abschluss mit den
    Auswertungen über die Baugruppe); das Ergebnis ist dasselbe. fertig(nr, ergebnis) je fertiger Datei; Fortschritt
    je Körper als JSON-Zeile, je Datei als "[n/m] Datei"."""
    import multiprocessing as mp
    ereignisse = mp.Queue()
    offen = [("datei", nr) for nr in sorted(auftraege)]
    auslassen = {nr: {} for nr in auftraege}
    geteilt = {}            # nr: {n, ausstehend (Körper), teile {k: Teil}}
    gesamt = gesamt or len(auftraege)
    stand = dict(erledigt=vorher)

    def starten(wid):
        q = mp.Queue()
        p = mp.Process(target=_arbeiter, args=(q, ereignisse, wid), daemon=True)
        p.start()
        return dict(p=p, q=q, auftrag=None, koerper=None, seit=None)

    def abschliessen(nr, erg):
        geteilt.pop(nr, None)
        stand["erledigt"] += 1
        fertig(nr, erg)
        print(f"[{stand['erledigt']}/{gesamt}] {Path(auftraege[nr][0]).name}", flush=True)

    def koerper_fertig(nr):
        g = geteilt[nr]
        if not g["ausstehend"]:
            offen.insert(0, ("abschluss", nr))

    def verarbeiten(ev):
        w = arbeiter[ev[1]]
        if w["auftrag"] != ev[2]:       # Meldung eines beendeten Auftrags
            return
        nr = ev[2][1]
        if ev[0] == "koerper":
            k, n = ev[3], ev[4]
            w.update(koerper=k or None, seit=time.monotonic() if k else None)
            if nr in geteilt:           # verteilt: Fortschritt = fertige Körper der Datei
                k = min(n, n - len(geteilt[nr]["ausstehend"]) + 1)
            print(json.dumps(dict(datei=stand["erledigt"] + 1, dateien=gesamt, name=Path(auftraege[nr][0]).name,
                                  koerper=min(k, n), koerper_n=n), ensure_ascii=False), flush=True)
            return
        w.update(auftrag=None, koerper=None, seit=None)
        if ev[0] == "geteilt":
            geteilt[nr] = dict(n=ev[4], ausstehend=set(ev[3]), teile={})
            offen[0:0] = [("koerper", nr, k) for k in ev[3]]
        elif ev[0] == "teil":
            g = geteilt[nr]
            g["teile"][ev[2][2]] = ev[3]
            g["ausstehend"].discard(ev[2][2])
            koerper_fertig(nr)
        else:
            abschliessen(nr, ev[3])

    def vergeben(w, auftrag):
        nr = auftrag[1]
        frei = prozesse - sum(1 for x in arbeiter if x["auftrag"] is not None) - 1
        dateien_offen = sum(1 for a in offen if a[0] == "datei")
        zusatz = None
        if auftrag[0] == "datei":       # verteilen nur, wenn sonst Prozesse ohne Arbeit blieben
            zusatz = teilen_ab if frei > dateien_offen and teilen_ab > 0 else 0
        elif auftrag[0] == "abschluss":
            zusatz = geteilt[nr]["teile"]
        w.update(auftrag=auftrag, koerper=None, seit=None)
        w["q"].put((auftrag, *auftraege[nr], dict(auslassen[nr]), zusatz))

    prozesse = max(1, prozesse)
    arbeiter = [starten(wid) for wid in range(min(prozesse, len(offen)))]
    try:
        while stand["erledigt"] < gesamt:
            for w in arbeiter:
                if w["auftrag"] is None and offen:
                    vergeben(w, offen.pop(0))
            while offen and len(arbeiter) < prozesse:      # verteilte Datei: weitere Prozesse starten
                arbeiter.append(starten(len(arbeiter)))
                vergeben(arbeiter[-1], offen.pop(0))
            try:
                verarbeiten(ereignisse.get(timeout=0.5))
            except queue.Empty:
                pass
            jetzt = time.monotonic()
            for wid, w in enumerate(arbeiter):
                if w["auftrag"] is None:
                    continue
                zu_lang = zeitlimit > 0 and w["seit"] is not None and jetzt - w["seit"] > zeitlimit
                if not w["p"].is_alive():       # gestorben: letzte Meldungen noch abholen
                    time.sleep(0.2)
                    while True:
                        try:
                            verarbeiten(ereignisse.get_nowait())
                        except queue.Empty:
                            break
                elif not zu_lang:
                    continue
                auftrag, k = w["auftrag"], w["koerper"]
                w["p"].kill()
                w["p"].join(5)
                arbeiter[wid] = starten(wid)
                if auftrag is None:             # doch noch fertig geworden
                    continue
                nr = auftrag[1]
                if k is None:                   # beim Lesen der Datei abgestürzt
                    abschliessen(nr, _fehler_ergebnis(Path(auftraege[nr][0]),
                                                      "Messung abgebrochen (Absturz beim Lesen der Datei)"))
                    continue
                auslassen[nr][k] = f"Zeitlimit {zeitlimit:g} s überschritten" if zu_lang else "Messung abgestürzt"
                if auftrag[0] == "koerper":     # verteilt: ohne diesen Körper weiter, er kommt in den Abschluss
                    geteilt[nr]["ausstehend"].discard(k)
                    koerper_fertig(nr)
                else:
                    offen.insert(0, auftrag)
    finally:
        for w in arbeiter:
            try:
                w["q"].put(None)
            except (OSError, ValueError):
                pass
        for w in arbeiter:
            w["p"].join(2)
            if w["p"].is_alive():
                w["p"].kill()


def _teil_schreiben(pfad, zs):
    with open(pfad, "a", encoding="utf-8", newline="\n") as f:      # je Datei in einem Stück (Abbruch)
        f.write("".join("\t".join(z) + "\n" for z in zs))


def main(argv=None):
    rest = list(sys.argv[1:] if argv is None else argv)
    if rest[:1] == ["--export"]:            # STEP-Export (3E-8): dieselbe .exe baut und schreibt Volumenkörper
        import step_schreiben
        return step_schreiben.main(rest)
    ap = argparse.ArgumentParser(description="STEP-Dateien messen (für den STEP-Import der Angebotskalkulation)")
    ap.add_argument("--ausgabe", required=True, help="Textdatei für die Messwerte")
    ap.add_argument("--liste", help="Textdatei mit einem STEP-Pfad je Zeile")
    ap.add_argument("--netze", help="Ordner für die Dreiecksnetze der 3D-Ansicht (JSON je Teil)")
    ap.add_argument("--json", help="Ergebnis zusätzlich als JSON-Datei (versioniertes Format, siehe step_ergebnis.py)")
    ap.add_argument("--flachstahl-bis", type=float, default=FLACHSTAHL_BIS,
                    help="größte Breite [mm], bis zu der ein flaches, stabförmiges Teil als Flachstahl gilt (sonst Blech)")
    ap.add_argument("--flach-laenge", type=float, help="Flachstahl: Länge mindestens × Breite (Vorgabe 3)")
    ap.add_argument("--gekantet-anteil", type=float, help="Kantteil-Grenze Volumenanteil (Vorgabe 0,85)")
    ap.add_argument("--prozesse", type=int, default=0, help="Messprozesse (0 = automatisch)")
    ap.add_argument("--zeitlimit", type=float, default=0, help="Sekunden je Körper (0 = ohne)")
    ap.add_argument("--cache", help="Ordner des Zwischenspeichers")
    ap.add_argument("--cache-mb", type=float, default=500, help="Größe des Zwischenspeichers höchstens [MB]")
    ap.add_argument("--kennung", default="", help="Programmversion (Teil des Schlüssels im Zwischenspeicher)")
    ap.add_argument("pfade", nargs="*", help="STEP-Dateien oder Ordner")
    a = ap.parse_args(argv)
    pfade = list(a.pfade)
    if a.liste:
        pfade += [z.strip() for z in Path(a.liste).read_text(encoding="utf-8-sig").splitlines() if z.strip()]
    if not pfade:
        ap.error("keine STEP-Dateien angegeben")
    dateien = step_dateien(pfade)
    if a.netze:
        Path(a.netze).mkdir(parents=True, exist_ok=True)
    einst = {k: v for k, v in (("flach_laenge", a.flach_laenge), ("gekantet_anteil", a.gekantet_anteil))
             if v is not None}
    ergebnis = [None] * len(dateien)
    with open(a.ausgabe, "w", encoding="utf-8", newline="\n") as f:      # Teilergebnis wächst je Datei
        f.write("\t".join(SPALTEN) + "\n")
    schluessel = {}
    if a.cache:
        Path(a.cache).mkdir(parents=True, exist_ok=True)
        wirksam = dict(einst, flachstahl_bis=a.flachstahl_bis, netze=bool(a.netze))
        for i, d in enumerate(dateien, start=1):
            try:
                schluessel[i] = cache_schluessel(d, a.kennung, wirksam)
            except OSError:
                continue
            erg = cache_lesen(a.cache, schluessel[i], a.netze, i)
            if erg is not None:
                ergebnis[i - 1] = erg
                _teil_schreiben(a.ausgabe, erg[0])
    offen = [i for i in range(1, len(dateien) + 1) if ergebnis[i - 1] is None]
    n_fertig = len(dateien) - len(offen)
    zaehler = [n_fertig]
    if n_fertig:
        print(f"[{n_fertig}/{len(dateien)}] aus dem Zwischenspeicher", flush=True)

    def fertig(i, erg):
        ergebnis[i - 1] = erg
        _teil_schreiben(a.ausgabe, erg[0])
        if i in schluessel:
            cache_schreiben(a.cache, schluessel[i], erg, a.netze, i, a.cache_mb)
    prozesse = a.prozesse if a.prozesse > 0 else max(1, (os.cpu_count() or 1) - 1)
    if a.zeitlimit > 0 and offen:
        _beaufsichtigt({i: (str(dateien[i - 1]), a.netze, a.flachstahl_bis, einst) for i in offen},
                       prozesse, a.zeitlimit, fertig, n_fertig, len(dateien))
    else:
        n_proz = min(PROZESSE_MAX if a.prozesse <= 0 else a.prozesse, (os.cpu_count() or 1) - 1, len(offen) // 3)
        if n_proz >= 2:       # viele Dateien: auf mehrere Prozesse verteilen, Reihenfolge der Ausgabe bleibt
            from concurrent.futures import ProcessPoolExecutor, as_completed
            with ProcessPoolExecutor(n_proz) as pool:
                auftraege_ = {pool.submit(messen, dateien[i - 1], a.netze, i, a.flachstahl_bis, einst): i
                              for i in offen}
                for fertig_ in as_completed(auftraege_):
                    i = auftraege_[fertig_]
                    fertig(i, fertig_.result())
                    zaehler[0] += 1
                    print(f"[{zaehler[0]}/{len(dateien)}] {dateien[i - 1].name}", flush=True)
        else:
            for i in offen:
                zaehler[0] += 1
                print(f"[{zaehler[0]}/{len(dateien)}] {dateien[i - 1].name}", flush=True)
                fertig(i, messen(dateien[i - 1], a.netze, i, a.flachstahl_bis, einst))
    fehler = False
    if a.json:
        Path(a.json).write_text(json.dumps(step_ergebnis.gesamt([e[1] for e in ergebnis]), ensure_ascii=False,
                                           indent=1), encoding="utf-8")
    with open(a.ausgabe, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(SPALTEN) + "\n")
        for zs, _ in ergebnis:
            for z in zs:
                fehler = fehler or bool(z[-1])
                f.write("\t".join(z) + "\n")
    return 1 if fehler else 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()     # STEP-Import.exe: Unterprozesse der Messung
    sys.exit(main())
