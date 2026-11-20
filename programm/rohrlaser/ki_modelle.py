"""KI-Plattform Phase 1: lokale Sprachmodelle verwalten (Master-Prompt Patrick 20.11.2026 „Lokale KI massiv erweitern“).

Die KI-Plattform arbeitet immer auch OHNE Sprachmodell: alle Prüfungen, Zahlen und Vorschläge kommen aus der
deterministischen Programmlogik (ki_agenten.py). Ein Sprachmodell ist optional und hilft nur beim Verstehen freier
Fragen, beim Herausziehen von Werten aus Text und beim Formulieren der Antwort. Es darf keine Zahl liefern, die nicht
in den Befunden der Programmlogik steht (ki_orchestrator.faktencheck).

Erlaubt sind nur Modell-Server auf dem eigenen Rechner oder im eigenen Netz (anfrage_ki_lokal.erlaubt: localhost,
127.x, ::1, 10.x, 172.16–31.x, 192.168.x, *.local), nie ein Internet-Dienst; Aufrufe gehen ohne Proxy. Damit läuft
alles auch hinter Firewall und ohne Internet.

Server-Arten:
  ollama   Ollama (http://localhost:11434): /api/tags, /api/ps, /api/generate, /api/embed, /api/show
  openai   OpenAI-kompatibler lokaler Server (llama.cpp-Server, LM Studio, vLLM im eigenen Netz): /v1/models,
           /v1/chat/completions, /v1/embeddings
Einstellungen (nur dieser Arbeitsplatz, der Modell-Server steht ja an diesem PC):
  ki_aktiv       ja/nein (Vorgabe nein): Sprachmodell benutzen; aus = alles regelbasiert
  ki_server      [{name, art, url}] (leer = die URL der Anfragen-KI, sonst Ollama auf localhost)
  ki_rollen      {Rolle: Modellname} (leer = automatisch wählen)
  ki_messungen   {Modell: {tokens_s, am}} letzte Geschwindigkeitsmessung
  ki_modell_ordner  Ordner (auch Netzwerkordner) mit Modell-Dateien (*.gguf) zum Importieren
Rollen (automatische Modellwahl je Aufgabe): verstehen (Frage einordnen, klein und schnell), extrahieren (Werte aus
Text als JSON), erklaeren (Antwort formulieren, größtes Modell, das in den Speicher passt), einbettung (semantische
Suche, nur Einbettungsmodelle).

Modelle kommen nie mit dem Programm (Größe): Import aus Datei oder Netzwerkordner (importieren). Ohne Qt."""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import anfrage_ki_lokal

AKTIV, SERVER, ROLLEN_EINST, MESSUNGEN, MODELL_ORDNER, OLLAMA_ORDNER = (
    "ki_aktiv", "ki_server", "ki_rollen", "ki_messungen", "ki_modell_ordner", "ki_ollama_ordner")
OLLAMA_PORT = 11434
OLLAMA, OPENAI = "ollama", "openai"
ARTEN = {OLLAMA: "Ollama", OPENAI: "OpenAI-kompatibel (llama.cpp, LM Studio)"}
VERSTEHEN, EXTRAHIEREN, ERKLAEREN, EINBETTUNG = "verstehen", "extrahieren", "erklaeren", "einbettung"
ROLLEN = ((VERSTEHEN, "Frage verstehen", "klein und schnell"),
          (EXTRAHIEREN, "Werte aus Text", "mittel, JSON-Ausgabe"),
          (ERKLAEREN, "Antwort formulieren", "größtes Modell, das in den Speicher passt"),
          (EINBETTUNG, "Semantische Suche", "nur Einbettungsmodelle"))
ROLLE_TITEL = {r: t for r, t, _ in ROLLEN}
EMBED_WOERTER = ("embed", "bge", "e5-", "minilm", "gte-")
SPEICHER_ANTEIL = 0.7           # ein Modell passt, wenn es höchstens 70 % des freien RAM (+ VRAM) braucht
TIMEOUT = 120
TEXT_MAX = 12000


class KiFehler(Exception):
    """Modell oder Server nicht erreichbar, nicht erlaubt oder Antwort unbrauchbar (Text für die Anzeige)."""


# ------------------------------------------------------------------ Einstellungen
def _einst(db, name, vorgabe=None):
    try:
        w = db.einstellung(name)
    except Exception:           # noqa: BLE001 – ohne Datenbank: Vorgabe
        return vorgabe
    return vorgabe if w in (None, "") else w


def aktiv(db):
    return _einst(db, AKTIV, "nein") == "ja"


def server_liste(db):
    """Konfigurierte Server; leer = Anfragen-KI-URL (falls dort eingetragen), sonst Ollama auf diesem Rechner."""
    s = _einst(db, SERVER)
    if isinstance(s, str):
        try:
            s = json.loads(s)
        except ValueError:
            s = None
    out = [dict(name=str(x.get("name") or x.get("url")), art=x.get("art") if x.get("art") in ARTEN else OLLAMA,
                url=str(x.get("url") or "").rstrip("/")) for x in (s or []) if isinstance(x, dict) and x.get("url")]
    if not out:
        url = (_einst(db, anfrage_ki_lokal.URL) or anfrage_ki_lokal.VORGABE_URL).strip().rstrip("/")
        out = [dict(name="Ollama (dieser PC)" if "localhost" in url or "127.0.0.1" in url else "Ollama", art=OLLAMA,
                    url=url)]
    return out


def server_setzen(db, liste):
    for s in liste:
        if not anfrage_ki_lokal.erlaubt(s.get("url")):
            raise KiFehler(f"Nur ein Server auf dem eigenen Rechner oder im eigenen Netz ist erlaubt, nicht "
                           f"{s.get('url')}.")
    db.einstellung_setzen(SERVER, [dict(name=s.get("name") or s["url"], art=s.get("art") or OLLAMA,
                                        url=str(s["url"]).rstrip("/")) for s in liste])


def rollen(db):
    r = _einst(db, ROLLEN_EINST, {})
    return dict(r) if isinstance(r, dict) else {}


def rolle_setzen(db, rolle, modell):
    r = rollen(db)
    if modell:
        r[rolle] = modell
    else:
        r.pop(rolle, None)
    db.einstellung_setzen(ROLLEN_EINST, r)


# ------------------------------------------------------------------ Verbindung
def _senden(url, pfad, daten=None, timeout=TIMEOUT):
    """HTTP ohne Proxy (eigenes Netz). daten None = GET."""
    req = urllib.request.Request(url.rstrip("/") + pfad, method="GET" if daten is None else "POST",
                                 data=None if daten is None else json.dumps(daten).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


def _rufen(server, pfad, daten=None, senden=None, timeout=TIMEOUT):
    if not anfrage_ki_lokal.erlaubt(server["url"]):
        raise KiFehler(f"Nur ein Server auf dem eigenen Rechner oder im eigenen Netz ist erlaubt, nicht "
                       f"{server['url']}.")
    try:
        if senden:                  # Tests: senden(url, pfad, daten)
            return senden(server["url"], pfad, daten)
        return _senden(server["url"], pfad, daten, timeout)
    except KiFehler:
        raise
    except (OSError, ValueError) as e:
        raise KiFehler(f"{server.get('name') or server['url']} nicht erreichbar: {e}") from e


# ------------------------------------------------------------------ Modelle
def _ist_embed(name, familie=""):
    n = f"{name} {familie}".lower()
    return any(w in n for w in EMBED_WOERTER)


def ist_cloud(m):
    """Ollama-Cloud-Modell (läuft auf fremden Servern im Internet)?"""
    name = str(m.get("name") or m.get("model") or "").lower()
    return bool(m.get("remote_host") or m.get("remote_model")) or name.endswith("-cloud") or ":cloud" in name \
        or "-cloud:" in name


def _parameter_b(text):
    """'7.6B' / '8B' / '334M' -> Milliarden."""
    m = re.search(r"([\d.]+)\s*([BbMm])", str(text or ""))
    if not m:
        return None
    w = float(m.group(1))
    return w if m.group(2).lower() == "b" else w / 1000


def modelle(db, senden=None, server=None):
    """Alle Modelle aller Server: [dict(server, art, url, name, groesse_gb, parameter, parameter_b, quantisierung,
    familie, einbettung, geladen, vram_gb, fehler)]. Ein nicht erreichbarer Server liefert eine Zeile mit fehler."""
    out = []
    for s in server or server_liste(db):
        basis = dict(server=s["name"], art=s["art"], url=s["url"])
        try:
            if s["art"] == OPENAI:
                for m in (_rufen(s, "/v1/models", senden=senden).get("data") or []):
                    name = str(m.get("id") or "")
                    out.append(dict(basis, name=name, groesse_gb=None, parameter="", parameter_b=_parameter_b(name),
                                    quantisierung="", familie="", einbettung=_ist_embed(name), geladen=True,
                                    vram_gb=None, fehler=""))
                continue
            tags = _rufen(s, "/api/tags", senden=senden).get("models") or []
            try:
                laufend = {m.get("name"): m for m in (_rufen(s, "/api/ps", senden=senden).get("models") or [])}
            except KiFehler:
                laufend = {}
            for m in tags:
                d, name = m.get("details") or {}, str(m.get("name") or m.get("model") or "")
                if ist_cloud(m):            # Ollama-Cloud-Modelle rechnen im Internet: nie anbieten
                    continue
                lauf = laufend.get(name)
                out.append(dict(basis, name=name, groesse_gb=round((m.get("size") or 0) / 1e9, 2),
                                parameter=d.get("parameter_size") or "", parameter_b=_parameter_b(
                                    d.get("parameter_size") or name), quantisierung=d.get("quantization_level") or "",
                                familie=d.get("family") or "", einbettung=_ist_embed(name, d.get("family") or ""),
                                geladen=lauf is not None,
                                vram_gb=round((lauf.get("size_vram") or 0) / 1e9, 2) if lauf else None, fehler=""))
        except KiFehler as e:
            out.append(dict(basis, name="", groesse_gb=None, parameter="", parameter_b=None, quantisierung="",
                            familie="", einbettung=False, geladen=False, vram_gb=None, fehler=str(e)))
    return out


def waehlen(liste, rolle, vorgabe=None, speicher_gb=None):
    """Modell für eine Rolle: die Vorgabe (wenn vorhanden), sonst automatisch. speicher_gb = freier RAM + freies VRAM;
    ein Modell passt, wenn es höchstens SPEICHER_ANTEIL davon braucht (unbekannte Größe passt). None = keins."""
    ok = [m for m in liste if m.get("name") and not m.get("fehler")]
    if vorgabe:
        for m in ok:
            if m["name"] == vorgabe or m["name"].split(":")[0] == vorgabe:
                return m
    if rolle == EINBETTUNG:
        emb = [m for m in ok if m["einbettung"]]
        return min(emb, key=lambda m: m.get("groesse_gb") or 0) if emb else None
    text = [m for m in ok if not m["einbettung"]]
    if speicher_gb:
        passt = [m for m in text if not m.get("groesse_gb") or m["groesse_gb"] <= SPEICHER_ANTEIL * speicher_gb]
        text = passt or sorted(text, key=lambda m: m.get("groesse_gb") or 0)[:1]
    if not text:
        return None

    def groesse(m):
        return m.get("parameter_b") or m.get("groesse_gb") or 0
    if rolle == ERKLAEREN:          # das stärkste Modell, das passt; geladene bevorzugt bei gleicher Größe
        return max(text, key=lambda m: (groesse(m), m.get("geladen")))
    if rolle == VERSTEHEN:          # klein und schnell, aber mindestens 1 Mrd. Parameter, wenn es so eins gibt
        gross_genug = [m for m in text if groesse(m) >= 1] or text
        return min(gross_genug, key=lambda m: (not m.get("geladen"), groesse(m)))
    mittel = [m for m in text if 3 <= groesse(m) <= 14] or text     # extrahieren: mittel
    return min(mittel, key=lambda m: (not m.get("geladen"), abs(groesse(m) - 7)))


def modell_fuer(db, rolle, senden=None, liste=None):
    """Das Modell für eine Rolle oder None (Sprachmodell aus, kein Server, kein passendes Modell)."""
    if not aktiv(db):
        return None
    if liste is None:
        liste = modelle(db, senden=senden)
    try:
        from . import ki_ressourcen
        r = ki_ressourcen.messen(mit_gpu=False)
        speicher = (r.get("ram_frei_gb") or 0) + sum(g.get("vram_frei_gb") or 0 for g in r.get("gpus") or [])
    except Exception:           # noqa: BLE001 – ohne Messung: Größe nicht prüfen
        speicher = None
    return waehlen(liste, rolle, rollen(db).get(rolle), speicher or None)


# ------------------------------------------------------------------ Aufrufen
def erzeugen(db, rolle, prompt, system="", json_format=False, senden=None, modell=None):
    """Text vom Modell der Rolle: dict(text, modell, server, tokens, dauer_s, tokens_s). Fehler: KiFehler."""
    m = modell or modell_fuer(db, rolle, senden=senden)
    if not m:
        raise KiFehler("Kein lokales Sprachmodell verfügbar (KI-Zentrale → Modelle).")
    s = dict(name=m["server"], art=m["art"], url=m["url"])
    prompt = str(prompt or "")[:TEXT_MAX]
    t0 = time.perf_counter()
    if m["art"] == OPENAI:
        daten = dict(model=m["name"], temperature=0, stream=False,
                     messages=([dict(role="system", content=system)] if system else []) +
                     [dict(role="user", content=prompt)])
        if json_format:
            daten["response_format"] = {"type": "json_object"}
        a = _rufen(s, "/v1/chat/completions", daten, senden=senden)
        text = (((a.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        tokens = (a.get("usage") or {}).get("completion_tokens") or 0
        dauer = time.perf_counter() - t0
        tps = tokens / dauer if tokens and dauer > 0 else None
    else:
        daten = dict(model=m["name"], prompt=prompt, stream=False, options=dict(temperature=0))
        if system:
            daten["system"] = system
        if json_format:
            daten["format"] = "json"
        a = _rufen(s, "/api/generate", daten, senden=senden)
        text = a.get("response") or ""
        tokens = a.get("eval_count") or 0
        dauer = time.perf_counter() - t0
        ev = (a.get("eval_duration") or 0) / 1e9
        tps = tokens / ev if tokens and ev > 0 else (tokens / dauer if tokens and dauer > 0 else None)
    return dict(text=str(text), modell=m["name"], server=m["server"], tokens=tokens, dauer_s=round(dauer, 3),
                tokens_s=round(tps, 1) if tps else None)


def einbetten(db, texte, senden=None, modell=None):
    """Vektoren für Texte (Liste von Listen) mit dem Einbettungsmodell. Fehler: KiFehler."""
    m = modell or modell_fuer(db, EINBETTUNG, senden=senden)
    if not m:
        raise KiFehler("Kein Einbettungsmodell verfügbar (z. B. nomic-embed-text importieren).")
    s = dict(name=m["server"], art=m["art"], url=m["url"])
    texte = [str(t or "")[:4000] for t in texte]
    if m["art"] == OPENAI:
        a = _rufen(s, "/v1/embeddings", dict(model=m["name"], input=texte), senden=senden)
        return [d.get("embedding") or [] for d in a.get("data") or []]
    try:
        a = _rufen(s, "/api/embed", dict(model=m["name"], input=texte), senden=senden)
        if a.get("embeddings"):
            return a["embeddings"]
    except KiFehler:
        pass
    return [(_rufen(s, "/api/embeddings", dict(model=m["name"], prompt=t), senden=senden).get("embedding") or [])
            for t in texte]


def testen(db, m, senden=None):
    """Geschwindigkeit eines Modells messen und merken: dict(ok, tokens_s, dauer_s, text, fehler)."""
    try:
        if m.get("einbettung"):
            t0 = time.perf_counter()
            v = einbetten(db, ["Rundrohr 42,4 x 2,0 S235"], senden=senden, modell=m)
            r = dict(ok=bool(v and v[0]), tokens_s=None, dauer_s=round(time.perf_counter() - t0, 3),
                     text=f"{len(v[0]) if v else 0} Dimensionen", fehler="")
        else:
            a = erzeugen(db, VERSTEHEN, "Antworte nur mit: bereit", senden=senden, modell=m)
            r = dict(ok=True, tokens_s=a["tokens_s"], dauer_s=a["dauer_s"], text=a["text"][:80], fehler="")
    except KiFehler as e:
        return dict(ok=False, tokens_s=None, dauer_s=None, text="", fehler=str(e))
    mess = _einst(db, MESSUNGEN, {})
    mess = dict(mess) if isinstance(mess, dict) else {}
    mess[m["name"]] = dict(tokens_s=r["tokens_s"], dauer_s=r["dauer_s"],
                           am=datetime.datetime.now().isoformat(timespec="seconds"))
    try:
        db.einstellung_setzen(MESSUNGEN, mess)
    except Exception:           # noqa: BLE001 – nur lesen: Messung nicht merken
        pass
    return r


def messungen(db):
    m = _einst(db, MESSUNGEN, {})
    return m if isinstance(m, dict) else {}


# ------------------------------------------------------------------ Import ohne Internet
def dateien(ordner):
    """Modell-Dateien (*.gguf) in einem Ordner (auch Netzwerkordner): [dict(pfad, name, groesse_gb)]."""
    try:
        p = Path(ordner)
        return [dict(pfad=str(f), name=f.stem, groesse_gb=round(f.stat().st_size / 1e9, 2))
                for f in sorted(p.glob("*.gguf"))] if ordner and p.is_dir() else []
    except OSError:
        return []


def ollama_ziel():
    """Ordner, in den das Programm Ollama für diesen PC kopiert (ohne Admin-Rechte, im Benutzerprofil)."""
    basis = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(basis) / "Rohrlaser" / "Ollama"


def _exe_name():
    return "ollama.exe" if sys.platform == "win32" else "ollama"


def ollama_bereitstellen(quelle, ziel=None):
    """Ollama aus einem Ordner (Netzwerkordner mit entpackter ZIP-Datei) nach ollama_ziel() kopieren, wenn dort
    nichts oder ein anderer Stand liegt. Ergebnis: Pfad zu ollama(.exe). Fehler: KiFehler."""
    q, z = Path(quelle), Path(ziel) if ziel else ollama_ziel()
    exe = q / _exe_name()
    if not exe.is_file():
        treffer = list(q.glob("*/" + _exe_name()))
        if not treffer:
            raise KiFehler(f"Im Ordner {q} liegt keine {_exe_name()} (ZIP-Datei von Ollama dort entpacken).")
        q, exe = treffer[0].parent, treffer[0]
    ziel_exe = z / _exe_name()
    try:
        alt = ziel_exe.stat()
        neu = exe.stat()
        if alt.st_size == neu.st_size and int(alt.st_mtime) >= int(neu.st_mtime):
            return ziel_exe
    except OSError:
        pass
    try:
        z.mkdir(parents=True, exist_ok=True)
        for f in q.rglob("*"):
            if f.is_file():
                d = z / f.relative_to(q)
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, d)
    except OSError as e:
        raise KiFehler(f"Ollama ließ sich nicht kopieren: {e}") from e
    return ziel_exe


def ollama_umgebung(basis=None):
    """Umgebung für Ollama: nur dieser PC, keine Cloud-Modelle, Modelle im eigenen Ordner."""
    env = dict(os.environ if basis is None else basis)
    env.update(OLLAMA_HOST=f"127.0.0.1:{OLLAMA_PORT}", OLLAMA_NO_CLOUD="1",
               OLLAMA_MODELS=str(ollama_ziel() / "models"))
    for n in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        env.pop(n, None)            # Ollama soll nichts von außen holen können
    return env


def ollama_laeuft(senden=None):
    try:
        _rufen(dict(name="Ollama", art=OLLAMA, url=f"http://127.0.0.1:{OLLAMA_PORT}"), "/api/version", senden=senden,
               timeout=2)
        return True
    except KiFehler:
        return False


def ollama_starten(db=None, starten=None, senden=None):
    """Ollama dieses PCs im Hintergrund starten (ollama serve mit ollama_umgebung). Ergebnis dict(ok, text).
    starten(befehl, env) ersetzt subprocess.Popen (Tests)."""
    if ollama_laeuft(senden):
        return dict(ok=True, text="Ollama läuft bereits.")
    exe = None
    if db is not None and _einst(db, OLLAMA_ORDNER):    # neuer Stand im Netzwerkordner: vorher kopieren
        try:
            exe = str(ollama_bereitstellen(_einst(db, OLLAMA_ORDNER)))
        except KiFehler:
            exe = None
    exe = exe or _ollama_programm()
    if not exe:
        return dict(ok=False, text="Ollama nicht gefunden: in der KI-Zentrale den Ollama-Ordner wählen.")
    befehl, env = [exe, "serve"], ollama_umgebung()
    try:
        if starten:
            starten(befehl, env)
        else:
            extra = dict(creationflags=0x08000000 | 0x00000008) if sys.platform == "win32" else \
                dict(start_new_session=True)
            subprocess.Popen(befehl, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, **extra)
    except OSError as e:
        return dict(ok=False, text=f"Ollama ließ sich nicht starten: {e}")
    if starten is None:
        for _ in range(20):
            if ollama_laeuft():
                break
            time.sleep(0.5)
    return dict(ok=True, text="Ollama gestartet (nur dieser PC, Cloud aus).")


def _ollama_programm():
    eigen = ollama_ziel() / _exe_name()
    if eigen.is_file():
        return str(eigen)
    exe = shutil.which("ollama")
    if exe:
        return exe
    if sys.platform == "win32":
        kandidat = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if kandidat.is_file():
            return str(kandidat)
    return None


def modellname(text):
    n = re.sub(r"[^a-z0-9._:-]+", "-", str(text or "").lower()).strip("-.")
    return n[:60] or "modell"


def importieren(datei, name=None, programm=None, ausfuehren=None):
    """Modell-Datei (GGUF) ohne Internet in Ollama übernehmen (ollama create NAME -f Modelfile mit FROM <Datei>).
    Ergebnis dict(ok, name, text). Ohne Ollama-Programm: ok False mit Anleitung (llama.cpp-Server startet die Datei
    direkt). ausfuehren(befehl) ersetzt subprocess.run (Tests)."""
    datei = Path(datei)
    if datei.suffix.lower() != ".gguf" or not datei.is_file():
        return dict(ok=False, name="", text=f"{datei.name}: keine Modell-Datei (*.gguf).")
    name = modellname(name or datei.stem)
    exe = programm or _ollama_programm()
    if not exe:
        return dict(ok=False, name=name, text="Ollama ist auf diesem PC nicht installiert. Mit einem llama.cpp-Server "
                    f"die Datei direkt starten (llama-server -m \"{datei}\") und ihn in der KI-Zentrale als Server "
                    "„OpenAI-kompatibel“ eintragen.")
    modelfile = datei.with_name(f".{name}.Modelfile")
    try:
        modelfile.write_text(f'FROM "{datei}"\n', encoding="utf-8")
    except OSError:
        import tempfile
        modelfile = Path(tempfile.gettempdir()) / f"{name}.Modelfile"
        modelfile.write_text(f'FROM "{datei}"\n', encoding="utf-8")
    befehl = [exe, "create", name, "-f", str(modelfile)]
    try:
        if ausfuehren:
            r = ausfuehren(befehl)
        else:
            extra = dict(creationflags=0x08000000) if sys.platform == "win32" else {}
            r = subprocess.run(befehl, capture_output=True, text=True, timeout=3600, env=ollama_umgebung(), **extra)
    except (OSError, subprocess.SubprocessError) as e:
        return dict(ok=False, name=name, text=f"Import fehlgeschlagen: {e}")
    finally:
        try:
            modelfile.unlink()
        except OSError:
            pass
    ok = getattr(r, "returncode", 1) == 0
    return dict(ok=ok, name=name, text=("Importiert als " + name) if ok else
                f"Import fehlgeschlagen: {(getattr(r, 'stderr', '') or getattr(r, 'stdout', ''))[-400:]}")


def status(db, senden=None, liste=None):
    """Kurzstatus für Dashboard und Startseite: dict(aktiv, server [dict(name, url, ok, fehler)], modelle, geladen,
    rollen {Rolle: Modellname oder ''}, text)."""
    if liste is None:
        liste = modelle(db, senden=senden) if aktiv(db) else []
    srv = {}
    for m in liste:
        e = srv.setdefault(m["server"], dict(name=m["server"], url=m["url"], ok=False, fehler=""))
        if m.get("fehler"):
            e["fehler"] = m["fehler"]
        elif m.get("name"):
            e["ok"] = True
    echte = [m for m in liste if m.get("name")]
    rol = {}
    for r, _, _ in ROLLEN:
        w = waehlen(liste, r, rollen(db).get(r)) if echte else None
        rol[r] = w["name"] if w else ""
    if not aktiv(db):
        text = "Sprachmodell aus – alle KI-Funktionen laufen regelbasiert"
    elif not echte:
        text = "Kein lokales Modell erreichbar – KI-Funktionen laufen regelbasiert"
    else:
        text = f"{len(echte)} Modell{'e' if len(echte) != 1 else ''}, {sum(1 for m in echte if m['geladen'])} geladen"
    return dict(aktiv=aktiv(db), server=list(srv.values()), modelle=len(echte),
                geladen=sum(1 for m in echte if m["geladen"]), rollen=rol, text=text)
