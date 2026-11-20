"""Lokale KI-Plattform (Master-Prompt Patrick 20.11.2026, Dauerregel „nie ins Internet, alles lokal“):
Modellverwaltung mit Cloud-Filter und Netzsperre, Modellwahl je Rolle, Ollama-Selbststart und Import ohne Internet,
Ressourcen, zehn Agenten auf einem optimierten Angebot, KI ändert keine Daten, Orchestrator mit Faktencheck,
Protokoll und Empfehlungen, Lernhistorie und Vergleich alt/neu, Wissensdatenbank, Mengenstaffel, Bericht (PDF),
KI-Zentrale und KI-Assistent im Fenster, KI-Prüfung im Angebots-Check, offline und Last.

Aufruf: python tests/test_ki_plattform.py
"""
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = Path(tempfile.mkdtemp())
os.environ["LOCALAPPDATA"] = str(TMP / "appdata")        # Ollama-Kopie im Test-Ordner
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import (anfrage_ki_lokal, ki_agenten, ki_bericht, ki_lernhistorie, ki_modelle, ki_orchestrator,  # noqa: E402
                       ki_prognose, ki_protokoll, ki_ressourcen, ki_wissen, rechnen)
from rohrlaser.datenbank import ALLE_TABELLEN, SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
db = Datenbank(TMP / "rohrlaser.db")
f = Hauptfenster(db, TMP, stumm=True)

# ------------------------------------------------------------------ Schema und Tabellen
assert SCHEMA_VERSION >= 100
ki_protokoll.bereit(db)
db.con.execute("SELECT COUNT(*) FROM ki_aktionen").fetchone()
db.con.execute("SELECT COUNT(*) FROM ki_empfehlungen").fetchone()
ok("Tabellen ki_aktionen und ki_empfehlungen da")

# ------------------------------------------------------------------ Netzsperre: nur dieser PC / Firmennetz
for url in ("https://api.openai.com", "http://8.8.8.8:11434", "https://ollama.com", "http://example.org"):
    assert not anfrage_ki_lokal.erlaubt(url), url
    try:
        ki_modelle.server_setzen(db, [dict(url=url)])
        raise AssertionError(url)
    except ki_modelle.KiFehler:
        pass
    try:
        ki_modelle._rufen(dict(name="x", art="ollama", url=url), "/api/tags", senden=lambda *a: {})
        raise AssertionError(url)
    except ki_modelle.KiFehler:
        pass
for url in ("http://localhost:11434", "http://127.0.0.1:8080", "http://192.168.1.20:11434", "http://10.0.0.5:1234"):
    assert anfrage_ki_lokal.erlaubt(url), url
ok("Internet-Adressen gesperrt, nur localhost und Firmennetz erlaubt")

# ------------------------------------------------------------------ Modelle mit nachgebautem Ollama
AUFRUFE = []
ANTWORT = {"text": "bereit"}


def ollama(url, pfad, daten=None):
    AUFRUFE.append((url, pfad, daten))
    if pfad == "/api/version":
        return {"version": "0.12.0"}
    if pfad == "/api/tags":
        return {"models": [
            {"name": "qwen3:8b", "size": 5_200_000_000, "details": {"parameter_size": "8.2B",
                                                                     "quantization_level": "Q4_K_M", "family": "qwen3"}},
            {"name": "qwen3:1.7b", "size": 1_400_000_000, "details": {"parameter_size": "1.7B", "family": "qwen3"}},
            {"name": "nomic-embed-text:latest", "size": 274_000_000,
             "details": {"parameter_size": "137M", "family": "nomic-bert"}},
            {"name": "gpt-oss:120b-cloud", "size": 0, "remote_host": "https://ollama.com:443",
             "details": {"parameter_size": "116.8B"}},
            {"name": "deepseek-v3.1:671b-cloud", "size": 0, "details": {}}]}
    if pfad == "/api/ps":
        return {"models": [{"name": "qwen3:1.7b", "size_vram": 1_500_000_000}]}
    if pfad == "/api/generate":
        return {"response": ANTWORT["text"], "eval_count": 40, "eval_duration": 800_000_000}
    if pfad == "/api/embed":
        return {"embeddings": [[float(len(t) % 7), float("rohr" in t.lower()), 1.0] for t in daten["input"]]}
    raise OSError("unbekannt " + pfad)


liste = ki_modelle.modelle(db, senden=ollama)
assert [m["name"] for m in liste] == ["qwen3:8b", "qwen3:1.7b", "nomic-embed-text:latest"], liste
assert not any("cloud" in m["name"] for m in liste)
m8 = liste[0]
assert m8["parameter_b"] == 8.2 and m8["quantisierung"] == "Q4_K_M" and not m8["geladen"]
assert liste[1]["geladen"] and liste[1]["vram_gb"] == 1.5 and liste[2]["einbettung"]
ok("Modellliste: Größe, Parameter, Quantisierung, geladen/VRAM; Cloud-Modelle ausgeblendet")

assert ki_modelle.waehlen(liste, ki_modelle.ERKLAEREN)["name"] == "qwen3:8b"
assert ki_modelle.waehlen(liste, ki_modelle.VERSTEHEN)["name"] == "qwen3:1.7b"
assert ki_modelle.waehlen(liste, ki_modelle.EXTRAHIEREN)["name"] == "qwen3:8b"
assert ki_modelle.waehlen(liste, ki_modelle.EINBETTUNG)["name"] == "nomic-embed-text:latest"
assert ki_modelle.waehlen(liste, ki_modelle.ERKLAEREN, speicher_gb=3)["name"] == "qwen3:1.7b"   # 8b passt nicht
assert ki_modelle.waehlen(liste, ki_modelle.ERKLAEREN, vorgabe="qwen3:1.7b")["name"] == "qwen3:1.7b"
assert ki_modelle.waehlen([], ki_modelle.ERKLAEREN) is None
ok("Automatische Modellwahl je Aufgabe, Speichergrenze, feste Vorgabe")

assert not ki_modelle.aktiv(db)
try:
    ki_modelle.erzeugen(db, ki_modelle.ERKLAEREN, "x", senden=ollama)
    raise AssertionError("aus")
except ki_modelle.KiFehler:
    pass
db.einstellung_setzen(ki_modelle.AKTIV, "ja")
ki_modelle.rolle_setzen(db, ki_modelle.ERKLAEREN, "qwen3:8b")
a = ki_modelle.erzeugen(db, ki_modelle.ERKLAEREN, "Hallo", senden=ollama)
assert a["text"] == "bereit" and a["modell"] == "qwen3:8b" and a["tokens_s"] == 50.0, a
assert AUFRUFE[-1][2]["options"]["temperature"] == 0
t = ki_modelle.testen(db, liste[1], senden=ollama)
assert t["ok"] and ki_modelle.messungen(db)["qwen3:1.7b"]["tokens_s"] == 50.0
v = ki_modelle.einbetten(db, ["Rundrohr 42,4"], senden=ollama)
assert len(v) == 1 and len(v[0]) == 3
st = ki_modelle.status(db, senden=ollama)
assert st["aktiv"] and st["modelle"] == 3 and st["geladen"] == 1 and st["rollen"][ki_modelle.ERKLAEREN] == "qwen3:8b"
ok("Erzeugen (Temperatur 0), Testen mit Geschwindigkeit, Einbetten, Status")


def offline(url, pfad, daten=None):
    raise OSError("Verbindung abgelehnt")


st = ki_modelle.status(db, senden=offline)
assert st["modelle"] == 0 and "regelbasiert" in st["text"] and st["server"][0]["fehler"]
ok("Server aus: Status regelbasiert, kein Absturz")

# ------------------------------------------------------------------ Ollama ohne Installation, Import ohne Internet
quelle = TMP / "netz" / "Ollama"
(quelle / "lib").mkdir(parents=True)
exe_name = "ollama.exe" if sys.platform == "win32" else "ollama"
(quelle / exe_name).write_bytes(b"x" * 100)
(quelle / "lib" / "runner.dll").write_bytes(b"y")
ziel = ki_modelle.ollama_bereitstellen(quelle)
assert ziel == ki_modelle.ollama_ziel() / exe_name and ziel.is_file() and (ziel.parent / "lib" / "runner.dll").is_file()
assert str(TMP) in str(ziel)
env = ki_modelle.ollama_umgebung({"PATH": "/bin", "HTTPS_PROXY": "http://proxy:8080", "http_proxy": "x"})
assert env["OLLAMA_HOST"] == "127.0.0.1:11434" and env["OLLAMA_NO_CLOUD"] == "1"
assert "HTTPS_PROXY" not in env and "http_proxy" not in env and env["OLLAMA_MODELS"].endswith("models")
gestartet = []
db.einstellung_setzen(ki_modelle.OLLAMA_ORDNER, str(quelle))
r = ki_modelle.ollama_starten(db, starten=lambda b, e: gestartet.append((b, e)), senden=offline)
assert r["ok"] and gestartet[0][0][1] == "serve" and gestartet[0][1]["OLLAMA_NO_CLOUD"] == "1", r
r = ki_modelle.ollama_starten(db, starten=lambda b, e: gestartet.append(b), senden=ollama)
assert r["text"] == "Ollama läuft bereits." and len(gestartet) == 1
ordner = TMP / "netz" / "Modelle"
ordner.mkdir()
(ordner / "Qwen3-8B-Q4_K_M.gguf").write_bytes(b"GGUF")
(ordner / "liesmich.txt").write_text("x")
d = ki_modelle.dateien(ordner)
assert [x["name"] for x in d] == ["Qwen3-8B-Q4_K_M"]
befehle = []


class _R:
    returncode = 0
    stdout = stderr = ""


r = ki_modelle.importieren(d[0]["pfad"], programm="ollama", ausfuehren=lambda b: befehle.append(b) or _R())
assert r["ok"] and r["name"] == "qwen3-8b-q4_k_m" and befehle[0][1:3] == ["create", "qwen3-8b-q4_k_m"], r
assert not list(ordner.glob(".*Modelfile"))         # Hilfsdatei wieder weg
assert not ki_modelle.importieren(ordner / "liesmich.txt")["ok"]
ok("Ollama aus Netzwerkordner kopieren und starten (nur 127.0.0.1, Cloud aus, ohne Proxy), GGUF-Import")

# ------------------------------------------------------------------ Ressourcen
res = ki_ressourcen.messen(ausfuehren=lambda b: (_ for _ in ()).throw(OSError("kein nvidia-smi")))
assert res["cpu_kerne"] >= 1 and res["ram_gesamt_gb"] and res["gpus"] == []
gp = ki_ressourcen.gpus(ausfuehren=lambda b: "NVIDIA RTX 4060, 8188, 6100, 12\n")
assert gp and gp[0]["vram_gesamt_gb"] == 8.0 and gp[0]["vram_frei_gb"] == 2.04 and gp[0]["last_pct"] == 12, gp
assert ki_ressourcen.empfehlung(res)
ok("CPU/RAM gemessen, GPU über nvidia-smi, Empfehlung")

# ------------------------------------------------------------------ Angebot anlegen und optimieren
aid = beispiel_angebot.anlegen(db)
kopf, pos = db.angebot(aid), db.positionen(aid)
erg = rechnen.optimieren(kopf, pos, db.kontext())
db.profile_anlegen(erg.get("neue_profile") or [])
db.ergebnis_speichern(aid, erg)
db.con.commit()


def fingerabdruck():
    h = hashlib.sha256()
    for t in ALLE_TABELLEN:
        name = getattr(t, "name", t)
        try:
            for z in db.con.execute(f"SELECT * FROM {name} ORDER BY 1"):
                h.update(repr(tuple(z)).encode())
        except Exception:       # noqa: BLE001
            db.con.rollback() if hasattr(db.con, "rollback") else None
    return h.hexdigest()


vorher = fingerabdruck()
t0 = time.perf_counter()
r = ki_agenten.pruefen(db, aid)
dauer = time.perf_counter() - t0
bf = r["befunde"]
assert bf, r
agenten = {b["agent"] for b in bf}
assert "Kalkulations-KI" in agenten and "Rohrlaser-KI" in agenten and "Material-KI" in agenten, agenten
for b in bf:
    assert b["art"] in ki_agenten.ARTEN and b["text"] and b["agent"], b
    assert set(b) >= {"agent", "art", "text", "ziel", "quelle", "begruendung", "stand"}
assert all(len(x) == 2 for x in r["fehler"])
assert fingerabdruck() == vorher, "KI-Prüfung hat Daten geändert"
ok(f"Zehn Agenten prüfen das Angebot: {len(bf)} Befunde von {len(agenten)} Agenten in {dauer:.2f} s, Daten unverändert")
assert len(ki_agenten.AGENTEN) == 10 and len({a.name for a in ki_agenten.AGENTEN}) == 10
u = ki_agenten.uebersicht(db)
assert isinstance(u["befunde"], list)
offen = ki_protokoll.empfehlungen(db, angebot_id=aid)
n_offen = len(offen)
ki_agenten.pruefen(db, aid)
assert len(ki_protokoll.empfehlungen(db, angebot_id=aid)) == n_offen, "gleiche Empfehlung doppelt"
if offen:
    ki_protokoll.empfehlung_setzen(db, offen[0]["id"], ki_protokoll.ABGELEHNT)
    assert len(ki_protokoll.empfehlungen(db, angebot_id=aid)) == n_offen - 1
z = ki_protokoll.zaehlen(db)
assert z["pruefungen"] >= 2 and z["angebote"] == 1
ok("Empfehlungen ohne Doppelte, Ablehnen, Protokoll zählt Prüfungen")

# ------------------------------------------------------------------ Orchestrator und Faktencheck
assert ki_orchestrator.absicht_regeln("Warum ist dieses Angebot so teuer?")[0] == "teuer"
assert ki_orchestrator.absicht_regeln("Erstelle eine Mengenstaffel für 10, 25, 50 und 100 Stück.")[0] == "staffel"
assert ki_orchestrator.absicht_regeln("Welche Materialien müssen bestellt werden?")[0] == "bestellen"
assert ki_orchestrator.absicht_regeln("Prüfe die Schneidzeit.")[0] == "schneidzeit"
ok_f, fremd = ki_orchestrator.faktencheck("Der Preis liegt bei 1.234,50 € für 24 Stück.", "Verkauf 1.234,50 €; 24 Stück")
assert ok_f and not fremd
ok_f, fremd = ki_orchestrator.faktencheck("Der Preis liegt bei 999,00 €.", "Verkauf 1.234,50 €")
assert not ok_f and fremd
ok("Absicht erkannt, Faktencheck lässt nur Zahlen aus den Fakten durch")

db.einstellung_setzen(ki_modelle.AKTIV, "nein")
vorher = fingerabdruck()
for frage in ki_orchestrator.BEISPIELE:
    e = ki_orchestrator.fragen(db, frage, angebot_id=aid)
    assert e["text"] and isinstance(e["befunde"], list) and not e["modell"], frage
e = ki_orchestrator.fragen(db, "Erstelle eine Mengenstaffel für 10, 25, 50 und 100 Stück.", angebot_id=aid)
assert e["staffel"] and "Mengenstaffel" in e["text"], e["text"]
assert fingerabdruck() == vorher, "Assistent hat Daten geändert"
ok("Alle zwölf Beispielfragen regelbasiert beantwortet, Daten unverändert")

db.einstellung_setzen(ki_modelle.AKTIV, "ja")
ANTWORT["text"] = "Das Angebot ist teuer, weil der Preis 99.999,99 € beträgt."
e = ki_orchestrator.fragen(db, "Warum ist dieses Angebot so teuer?", angebot_id=aid, senden=ollama)
assert e["faktencheck"] is False and "99.999,99" not in e["text"], e["text"]
ANTWORT["text"] = "Der größte Kostenblock ist das Material."
e = ki_orchestrator.fragen(db, "Warum ist dieses Angebot so teuer?", angebot_id=aid, senden=ollama)
assert e["faktencheck"] is True and e["text"].startswith("Der größte Kostenblock") and e["modell"] == "qwen3:8b"
e = ki_orchestrator.fragen(db, "Warum ist dieses Angebot so teuer?", angebot_id=aid, senden=offline)
assert e["text"] and not e["modell"] and any(q == "Sprachmodell" for q, _ in e["fehler"])
ok("Mit Modell: erfundene Zahl verworfen, gute Antwort übernommen, Modell aus = Regeltext")

# ------------------------------------------------------------------ Prognose, Lernen, Wissen, Bericht
ctx = ki_agenten.Kontext(db, aid)
assert ki_prognose.mengen_aus_text("für 10, 25 und 100 Stück") == (10, 25, 100)
stf = ki_prognose.mengenstaffel(ctx, [10, 100])
preise = [s["preis_einheit"] for z in stf for s in z["mengen"] if s.get("preis_einheit") is not None]
assert stf and preise and all(x > 0 for x in preise), stf
ok("Mengenstaffel aus eigenen Rechenläufen")

ls = ki_lernhistorie.lernstand(db)
assert set(ls) >= {"kennwerte_aktiv", "reif", "verdaechtig", "datenqualitaet_pct"}
assert isinstance(ki_lernhistorie.eintraege(db), list)
falsch = ki_lernhistorie.fehlerhafte_daten(db, [dict(titel="Laserzeit", quelle="laserzeit", schluessel=("T11",),
                                                      faelle=[dict(soll=10, ist=0, angebot="A1"),
                                                              dict(soll=10, ist=150, angebot="A2"),
                                                              dict(soll=10, ist=10.5, angebot="A3")])])
assert len(falsch) >= 2, falsch
ok("Lernstand und verdächtige Lerndaten (Ist 0, Ausreißer)")

treffer = ki_wissen.suchen(db, "Holm links RR 42,4", 5, semantisch=False)
assert treffer and treffer[0]["quelle"] and any("Holm" in t["text"] or "Holm" in t["titel"] for t in treffer), treffer
assert ki_wissen.info(db)["n"] > 0
ok("Wissensdatenbank findet Angebotspositionen mit Quelle und Stand")

r = ki_agenten.pruefen(db, aid, protokoll=False)
txt = ki_bericht.text(r, db.angebot(aid))
assert "Angebotsprüfung" in txt and "Kalkulations-KI" in txt
pdf = ki_bericht.pdf(r, TMP / "bericht.pdf", db.angebot(aid))
assert Path(pdf).read_bytes()[:4] == b"%PDF"
ok("Bericht als Text und PDF")

# ------------------------------------------------------------------ Fenster
assert "KI-Zentrale …" in f.datei_aktionen and "KI-Assistent …" in f.datei_aktionen
assert f.datei_aktionen["KI-Assistent …"].shortcut().toString() == "Ctrl+Alt+K"
from rohrlaser import ki_assistent, ki_zentrale  # noqa: E402

gesehen = []
d = ki_zentrale.zeigen(f, dialog=gesehen.append, senden=ollama)
assert gesehen and d.reiter.count() == 6
assert d.modell_tabelle.rowCount() == 3 and d.agenten_tabelle.rowCount() == 10
assert "Modell" in d.status["ki"].text()
from rohrlaser import admin_schutz  # noqa: E402
assert d.schloss.isHidden() == admin_schutz.ist_admin(db) and d.server_feld.isEnabled() == admin_schutz.ist_admin(db)
assert "GB" in d.status["ram"].text()
d.ordner_feld.setText(str(ordner))
d._dateien_setzen()
assert d.datei_tabelle.rowCount() == 1
d._suchen("Querstrebe")
assert d.such_tabelle.rowCount() >= 1
d.neu_laden()
assert d.prot_tabelle.rowCount() >= 1
d.uhr.stop()
d.close()
ok("KI-Zentrale: sechs Reiter, Modelle, Agenten, Import-Ordner, Suche, Protokoll")

seite = f.angebot_oeffnen(aid)
seite = seite if seite is not None else f._seite()
db.einstellung_setzen(ki_modelle.AKTIV, "nein")
ass = ki_assistent.zeigen(f)
assert "Angebot" in ass.bezug.text() and ass.pruef_knopf.isEnabled()
e = ass.fragen("Warum ist dieses Angebot so teuer?")
assert e and ass.antwort.toPlainText()
e = ass.pruefen()
assert ass.befunde.rowCount() == len(e["befunde"]) > 0
mit_ziel = [i for i, b in enumerate(e["befunde"]) if b.get("ziel")]
if mit_ziel:
    ass.hinspringen(mit_ziel[0])
p = ass.bericht_speichern(TMP / "assistent.pdf")
assert Path(p).is_file()
ass.close()
assert "check:ki" in seite.uebersicht_bereich.freigabe.text()
d2 = seite.check_link("check:ki")
assert d2 is ass and ass.befunde.rowCount() > 0
ass.close()
ok("KI-Assistent: Bezug, Frage, Prüfung, Hinspringen, Bericht; Link „KI-Prüfung“ im Angebots-Check")

# ------------------------------------------------------------------ Last
t0 = time.perf_counter()
for _ in range(20):
    ki_orchestrator.fragen(db, "Welche Kalkulationspositionen fehlen?", angebot_id=aid, mit_modell=False)
lauf = time.perf_counter() - t0
assert lauf < 60, lauf
ok(f"Last: 20 Fragen in {lauf:.1f} s")
print(json.dumps(dict(befunde=len(bf), protokoll=ki_protokoll.zaehlen(db)["aktionen"])))
print("ALLE TESTS OK")
