"""KI 4 – eigenes lokales Modell (Master-Prompt Patrick 21.11.2026): Modell-Register mit Versionen, Freigabe nur nach
fachlichem Prüfsatz, Zurücksetzen; Trainingsdaten bereinigt, anonymisiert, fest getrennt und versioniert; KI-Einstellungen
über die Admin-Vorgaben; Vertrauenswerte im Assistenten; Leistungsklasse; KI-Zentrale Reiter „Modellversionen“.

Aufruf: python tests/test_ki_register.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = Path(tempfile.mkdtemp())
os.environ["LOCALAPPDATA"] = str(TMP / "appdata")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import (absage, admin_schutz, anfrage_lernen, ki_modelle, ki_orchestrator, ki_pruefsatz,  # noqa: E402
                       ki_register, ki_ressourcen, ki_training)
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


app = QApplication.instance() or QApplication([])
db = Datenbank(TMP / "rohrlaser.db")
f = Hauptfenster(db, TMP, stumm=True)

# ------------------------------------------------------------------ nachgebautes Ollama (nur localhost)
ANTWORTEN = {}          # Teiltext des Prompts -> Antwort
STANDARD = {"text": "{}"}


def ollama(url, pfad, daten=None):
    assert "localhost" in url or "127.0.0.1" in url, url
    if pfad == "/api/version":
        return {"version": "0.12.0"}
    if pfad == "/api/tags":
        return {"models": [
            {"name": "qwen3:4b", "size": 2_500_000_000, "details": {"parameter_size": "4B", "family": "qwen3"}},
            {"name": "rohrlaser-ki:latest", "size": 2_500_000_000, "details": {"parameter_size": "4B"}},
            {"name": "wildmodell:latest", "size": 1_000_000_000, "details": {"parameter_size": "1B"}}]}
    if pfad == "/api/ps":
        return {"models": []}
    if pfad == "/api/generate":
        p = daten.get("prompt", "")
        for teil, antwort in ANTWORTEN.items():
            if teil in p:
                return {"response": antwort, "eval_count": 10, "eval_duration": 100_000_000}
        return {"response": STANDARD["text"], "eval_count": 10, "eval_duration": 100_000_000}
    raise OSError("unbekannt " + pfad)


db.einstellung_setzen(ki_modelle.AKTIV, "ja")
liste = ki_modelle.modelle(db, senden=ollama)
m_gut = next(m for m in liste if m["name"].startswith("rohrlaser-ki"))
m_alt = next(m for m in liste if m["name"].startswith("qwen3"))


def richtig_antworten():
    ANTWORTEN.clear()
    for a in ki_pruefsatz.aufgaben():
        if a["art"] == "einordnen":
            ANTWORTEN[a["eingabe"]] = json.dumps({"absicht": a["erwartet"]})
        elif a["art"] == "auslesen":
            ANTWORTEN[a["eingabe"]] = json.dumps(a["erwartet"], ensure_ascii=False)
        elif a["art"] == "absage":
            ANTWORTEN[a["eingabe"]] = json.dumps({"grund": a["erwartet"]}, ensure_ascii=False)
        else:
            ANTWORTEN[a["eingabe"]] = f"Auffällig ist der Wert {a['erwartet']} in den Fakten."


# ------------------------------------------------------------------ Prüfsatz
assert len(ki_pruefsatz.aufgaben()) == 19
richtig_antworten()
e_gut = ki_pruefsatz.pruefen(db, m_gut, senden=ollama, mit_eigenen=False)
assert e_gut["punkte"] == e_gut["max"] == 19 and e_gut["quote"] == 1.0, e_gut
assert set(e_gut["je_art"]) == {"einordnen", "auslesen", "absage", "erklaeren"}
ANTWORTEN.clear()
e_schlecht = ki_pruefsatz.pruefen(db, m_alt, senden=ollama, mit_eigenen=False)
assert e_schlecht["punkte"] == 0 and e_schlecht["quote"] == 0.0
# erfundene Zahl beim Erklären = kein Punkt, auch wenn die wichtigste Zahl dabei ist
a = next(x for x in ki_pruefsatz.aufgaben() if x["art"] == "erklaeren")
assert ki_pruefsatz.bewerten(a, f"{a['erwartet']} und dazu 987,65 €")[0] == 0
assert ki_pruefsatz.bewerten(a, f"Der größte Posten ist {a['erwartet']} €.")[0] == 1
x = next(x for x in ki_pruefsatz.aufgaben() if x["art"] == "auslesen")
assert ki_pruefsatz.bewerten(x, json.dumps(dict(x["erwartet"], menge=41)))[1] == "falsch: Menge"
assert "19/19" in ki_pruefsatz.text(e_gut) and ki_pruefsatz.text(None) == "Noch nicht geprüft."


def kaputt(url, pfad, daten=None):
    if pfad == "/api/generate":
        raise OSError("weg")
    return ollama(url, pfad, daten)


e_aus = ki_pruefsatz.pruefen(db, m_gut, senden=kaputt, mit_eigenen=False)
assert e_aus["fehler"] == 19 and e_aus["punkte"] == 0
ok("Prüfsatz: 19 feste Aufgaben (Einordnen, Auslesen, Absage, Erklären), Faktencheck, ausgefallenes Modell = 0 Punkte")

# ------------------------------------------------------------------ Register: Versionen, Freigabe, Zurücksetzen
assert ki_register.lizenz("qwen3:4b").startswith("Apache") and ki_register.lizenz("wildmodell") == ki_register.UNBEKANNT
assert ki_register.vorhandene_eintragen(db, liste, "PB") == 3
assert ki_register.vorhandene_eintragen(db, liste, "PB") == 0
alt = ki_register.finden(db, "qwen3#1")
neu = ki_register.finden(db, "rohrlaser-ki#1")
wild = ki_register.finden(db, "wildmodell#1")
assert alt["status"] == neu["status"] == ki_register.TEST and neu["lizenz"] == ki_register.UNBEKANNT
neu = ki_register.angaben_setzen(db, neu["id"], basis="qwen3-4b", datensatz="2026-11-21_abcd1234", kuerzel="PB")
assert neu["lizenz"].startswith("Apache") and neu["datensatz"] == "2026-11-21_abcd1234"
# ohne Prüfung: nicht aktivierbar
try:
    ki_register.aktivieren(db, alt["id"], [ki_modelle.EXTRAHIEREN], "PB")
    raise AssertionError("ohne Prüfung aktiviert")
except ki_register.BestaetigungNoetig as grund:
    assert "Prüfsatz" in str(grund)
# erste Version erzwungen (mit Begründung), dann bessere ordentlich
ki_register.pruefung_speichern(db, alt["id"], dict(e_gut, quote=0.8, punkte=15))
ki_register.aktivieren(db, alt["id"], [ki_modelle.EXTRAHIEREN, ki_modelle.ERKLAEREN], "PB")
assert ki_modelle.rollen(db)[ki_modelle.EXTRAHIEREN] == "qwen3"
assert ki_register.produktiv(db, ki_modelle.ERKLAEREN)["id"] == "qwen3#1"
# schlechtere Version darf die bessere nicht ablösen
ki_register.pruefung_speichern(db, neu["id"], dict(e_gut, quote=0.75))
fr = ki_register.freigabe_pruefen(db, neu["id"], [ki_modelle.EXTRAHIEREN])
assert not fr[0] and "schlechter" in fr[1], fr
ki_register.pruefung_speichern(db, neu["id"], e_gut)
assert ki_register.freigabe_pruefen(db, neu["id"], [ki_modelle.EXTRAHIEREN])[0]
ki_register.aktivieren(db, neu["id"], [ki_modelle.EXTRAHIEREN], "PB")
alt = ki_register.finden(db, "qwen3#1")
assert alt["status"] == ki_register.PRODUKTIV and alt["rollen"] == [ki_modelle.ERKLAEREN]
assert alt["war_rollen"] == [ki_modelle.EXTRAHIEREN] and alt["abgeloest"]["von"] == "rohrlaser-ki#1"
assert ki_modelle.rollen(db)[ki_modelle.EXTRAHIEREN] == "rohrlaser-ki"
assert ki_modelle.modell_fuer(db, ki_modelle.EXTRAHIEREN, senden=ollama)["name"] == "rohrlaser-ki:latest"
# unbekannte Lizenz: nur mit Bestätigung
ki_register.pruefung_speichern(db, wild["id"], e_gut)
assert "Lizenz" in ki_register.freigabe_pruefen(db, wild["id"], [ki_modelle.VERSTEHEN])[1]
w = ki_register.aktivieren(db, wild["id"], [ki_modelle.VERSTEHEN], "PB", erzwingen=True, begruendung="Test")
assert w["aktiviert"]["erzwungen"] and "Begründung: Test" in ki_register.verlauf(db)[0]["was"]
# Zurücksetzen holt die abgelöste Version zurück; ohne frühere: automatisch
z = ki_register.zuruecksetzen(db, ki_modelle.EXTRAHIEREN, "PB")
assert z["id"] == "qwen3#1" and ki_modelle.rollen(db)[ki_modelle.EXTRAHIEREN] == "qwen3"
assert ki_register.finden(db, "rohrlaser-ki#1")["status"] == ki_register.ARCHIV
assert ki_register.zuruecksetzen(db, ki_modelle.VERSTEHEN, "PB") is None
assert ki_modelle.VERSTEHEN not in ki_modelle.rollen(db)
assert ki_register.finden(db, "wildmodell#1")["status"] == ki_register.ARCHIV
# neue Datei unter gleichem Namen: neue Version, alte als überschrieben (nicht zurückholbar)
ki_register.eintragen(db, "ki-x", sha256="a" * 64)
v2 = ki_register.eintragen(db, "ki-x:latest", sha256="b" * 64)
assert v2["id"] == "ki-x#2" and ki_register.finden(db, "ki-x#1")["ueberschrieben"]
assert ki_register.eintragen(db, "ki-x", sha256="b" * 64)["id"] == "ki-x#2"
d = TMP / "m.gguf"
d.write_bytes(b"GGUF" + b"x" * 1000)
import hashlib  # noqa: E402
assert ki_register.sha256_datei(d) == hashlib.sha256(d.read_bytes()).hexdigest()
ok("Register: Versionen mit Lizenz, Aktivieren nur geprüft und nicht schlechter, sonst mit Begründung; "
   "Archiv und Zurücksetzen; Prüfsumme")

# ------------------------------------------------------------------ Trainingsdaten
db.con.execute("INSERT INTO kunden (kundennr, name, ansprechpartner) VALUES ('K1', 'Muster Metallbau GmbH', "
               "'Erika Beispiel')")
db.con.commit()
aid = db.angebot_neu(dict(kunde="Muster Metallbau GmbH", skonto=0, stange=6000))
db.versand_merken(aid, absage.eintrag("Preis zu hoch", "Aus Mail: Muster Metallbau GmbH hat einen günstigeren "
                                      "Anbieter gefunden, Gruß Erika Beispiel, Tel. 02345 67890, erika@muster.de"))
aid2 = db.angebot_neu(dict(kunde="X", skonto=0, stange=6000))
db.versand_merken(aid2, absage.eintrag(absage.OHNE_GRUND, "egal"))         # ohne Grund: nicht verwendbar
wurzel = TMP / "akten"
anfrage_lernen.rueckmelden(wurzel, "art", "Sonstiges", "Anfrage", nr="A-1",
                           text="Bitte um Angebot für 20 Rohre, siehe www.muster.de/zeichnung")
anfrage_lernen.rueckmelden(wurzel, "art", "Anfrage", "Anfrage", nr="A-2", text="kurz")          # zu kurz
ki_orchestrator.fragen(db, "Warum ist dieses Angebot so teuer?", mit_modell=False)
roh = ki_training.sammeln(db, wurzel)
assert len(roh["absage"]) == 1 and len(roh["mail_art"]) == 2 and roh["einordnen"], roh
assert roh["einordnen"][0]["antwort"] == "teuer"
ex = ki_training.exportieren(db, TMP / "training", wurzel=wurzel)
ordner = Path(ex["ordner"])
alles = "".join(p.read_text(encoding="utf-8") for p in ordner.glob("*.jsonl"))
for geheim in ("Muster Metallbau", "Erika Beispiel", "erika@muster.de", "02345", "www.muster.de"):
    assert geheim not in alles, geheim
assert "<KUNDE>" in alles and "<EMAIL>" in alles and "<TELEFON>" in alles and "<URL>" in alles
assert ex["aufgaben"]["mail_art"]["verworfen"] == {"Eingabe leer oder zu kurz": 1}
zeile = json.loads(next(z for p in ordner.glob("absage_*.jsonl") for z in p.read_text(encoding="utf-8").splitlines()))
assert [m["role"] for m in zeile["messages"]] == ["system", "user", "assistant"]
assert zeile["messages"][2]["content"] == "Preis zu hoch"
man = json.loads((ordner / "manifest.json").read_text(encoding="utf-8"))
assert man["version"] == ex["version"] and len(man["dateien"]) == 8 and (ordner / "LIESMICH.txt").is_file()
assert ki_training.manifest_pruefen(ordner) == (True, [])
assert ki_training.exporte(db)[0]["version"] == ex["version"]
# gleicher Inhalt = gleiche Version; Trennung fest nach Eingabe
assert ki_training.exportieren(db, TMP / "training", wurzel=wurzel)["version"] == ex["version"]
assert all(ki_training.ist_test(f"Frage {i}") == ki_training.ist_test(f"  frage {i} ") for i in range(50))
assert 1 <= sum(ki_training.ist_test(f"Frage Nummer {i}") for i in range(200)) <= 40
# Bereinigen: Doppelte und Widersprüche
gut, weg = ki_training.bereinigen([dict(eingabe="Rohr 40x40 bitte", antwort="A"),
                                   dict(eingabe="rohr 40x40   bitte", antwort="A"),
                                   dict(eingabe="Blech 2 mm bitte", antwort="A"),
                                   dict(eingabe="Blech 2 mm bitte", antwort="B"),
                                   dict(eingabe="", antwort="A"), dict(eingabe="ohne Antwort hier", antwort="")])
assert len(gut) == 1 and weg == {"doppelt": 1, "widersprüchliche Antworten": 2, "Eingabe leer oder zu kurz": 1,
                                 "ohne Antwort": 1}, weg
# Testfälle für den Prüfsatz aus dem Testanteil; veränderte Datei wird erkannt
faelle = {"einordnen": [dict(eingabe=f"Frage Nummer {i} zum Preis", antwort="teuer") for i in range(200)],
          "absage": [], "mail_art": []}
ex2 = ki_training.exportieren(db, TMP / "training2", faelle=faelle)
tf = ki_training.testfaelle(db)
assert ex2["aufgaben"]["einordnen"]["test"] == len(tf) > 0 and tf[0]["erwartet"] == "teuer"
assert tf[0]["art"] == "eigen_einordnen" and tf[0]["prompt"] == tf[0]["eingabe"]
ANTWORTEN.clear()
STANDARD["text"] = "teuer"
e_eigen = ki_pruefsatz.pruefen(db, m_gut, senden=ollama)
assert e_eigen["je_art"]["eigen_einordnen"] == [len(tf), len(tf)] and e_eigen["max"] == 19 + len(tf)
STANDARD["text"] = "{}"
p = next(Path(ex2["ordner"]).glob("einordnen_test.jsonl"))
p.write_text(p.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
assert ki_training.manifest_pruefen(ex2["ordner"]) == (False, ["einordnen_test.jsonl verändert"])
assert ki_training.testfaelle(db) == []
ok("Trainingsdaten: Absage, Mail-Art, Einordnen; anonymisiert, bereinigt, fest getrennt, versioniert mit Manifest; "
   "Testanteil im Prüfsatz; veränderte Daten erkannt")

# ------------------------------------------------------------------ Admin-Vorgaben: KI-Einstellungen an alle PCs
assert (admin_schutz.KI, "KI-Plattform (Server, Rollen, Modellversionen)", "einstellungen") in admin_schutz.bereiche()
assert admin_schutz.KI in admin_schutz.VORGABE
namen = admin_schutz.einstellungen_geschuetzt(db)
assert {"ki_server", "ki_rollen", "ki_aktiv", "ki_modell_register", "ki_modell_ordner"} <= namen
assert "ki_ollama_ordner" not in namen and "ki_messungen" not in namen       # je PC
assert "ki_rollen" not in admin_schutz.einstellungen_geschuetzt(db, ["e_firma"])
inh = admin_schutz.inhalt(db)
assert "ki_modell_register" in inh["einstellungen"] and "ki_rollen" in inh["einstellungen"]
ok("Admin-Vorgaben: Bereich KI-Plattform (Server, Rollen, Register) geht an alle PCs, Ollama-Ordner bleibt je PC")

# ------------------------------------------------------------------ Vertrauenswerte
r = ki_orchestrator.fragen(db, "Warum ist dieses Angebot so teuer?", mit_modell=False)
assert r["absicht_quelle"] == "regeln" and r["vertrauen"][0] == ki_orchestrator.HOCH, r["vertrauen"]
r = ki_orchestrator.fragen(db, "Blubb blabb", mit_modell=False)
assert r["absicht"] is None and r["vertrauen"][0] == ki_orchestrator.NIEDRIG
assert ki_orchestrator.vertrauen("teuer", "modell")[0] == ki_orchestrator.MITTEL
assert ki_orchestrator.vertrauen("teuer", "regeln", faktencheck_ok=False)[0] == ki_orchestrator.NIEDRIG
assert ki_orchestrator.vertrauen("teuer", "regeln", fehler=[("x", "y")])[0] == ki_orchestrator.MITTEL
from rohrlaser import ki_assistent  # noqa: E402
assistent = ki_assistent.KiAssistent(f) if hasattr(ki_assistent, "KiAssistent") else None
if assistent is not None and hasattr(assistent, "zeigen"):
    assistent.zeigen(ki_orchestrator.fragen(db, "Warum ist dieses Angebot so teuer?", mit_modell=False))
    assert "Vertrauen: hoch" in assistent.fuss.text()
ok("Vertrauen je Antwort: hoch (feste Regeln), mittel (Modell/Teilausfall), niedrig (unklar/Faktencheck)")

# ------------------------------------------------------------------ Leistungsklassen
assert ki_ressourcen.klasse(dict(ram_gesamt_gb=16, gpus=[]))[0] == "S"
assert ki_ressourcen.klasse(dict(ram_gesamt_gb=64, gpus=[]))[0] == "M"
assert ki_ressourcen.klasse(dict(ram_gesamt_gb=32, gpus=[dict(vram_gesamt_gb=8)]))[0] == "L"
assert ki_ressourcen.klasse(dict(ram_gesamt_gb=64, gpus=[dict(vram_gesamt_gb=24)]))[3] is True
ok("Leistungsklassen S/M/L/XL aus RAM und VRAM")

# ------------------------------------------------------------------ KI-Zentrale: Reiter Modellversionen
from rohrlaser import ki_zentrale  # noqa: E402
gesehen = []
d = ki_zentrale.zeigen(f, dialog=gesehen.append, senden=ollama)
titel = [d.reiter.tabText(i) for i in range(d.reiter.count())]
assert "Modellversionen" in titel, titel
assert d.versionen_tabelle.rowCount() == len(ki_register.liste(db)) >= 4
assert "Klasse" in d.klasse_text.text() and "Trainingsdaten-Export" in d.export_text.text()
assert d._v_eintragen() == 0
reihe = next(i for i, e in enumerate(d.versionen) if e["id"] == "rohrlaser-ki#1")
d.versionen_tabelle.selectRow(reihe)
richtig_antworten()
erg = d._v_pruefen(warten=True)
assert erg["quote"] == 1.0 and ki_register.finden(db, "rohrlaser-ki#1")["pruefung"]["quote"] == 1.0
reihe = next(i for i, e in enumerate(d.versionen) if e["id"] == "rohrlaser-ki#1")
d.versionen_tabelle.selectRow(reihe)
x = d._v_aktivieren(rollen=[ki_modelle.EXTRAHIEREN])
assert x["status"] == ki_register.PRODUKTIV and ki_modelle.rollen(db)[ki_modelle.EXTRAHIEREN] == "rohrlaser-ki"
# ungeprüft ohne Begründung: bleibt aus; mit Begründung: aktiv
reihe = next(i for i, e in enumerate(d.versionen) if e["id"] == "ki-x#2")
d.versionen_tabelle.selectRow(reihe)
assert d._v_aktivieren(rollen=[ki_modelle.VERSTEHEN], bestaetigen="") is None
assert ki_register.finden(db, "ki-x#2")["status"] == ki_register.TEST
assert d._v_zuruecksetzen(rolle=ki_modelle.EXTRAHIEREN)["id"] == "qwen3#1"
ex3 = d._v_export(ordner=str(TMP / "training3"))
assert ex3 and Path(ex3["ordner"]).is_dir() and ex3["version"] in d.export_text.text()
assert d.versionen_verlauf.rowCount() > 5
d.uhr.stop()
# Import: nie überschreiben (eindeutiger Name), danach im Register mit Prüfsumme
merk = ki_modelle.importieren
gerufen = []


def imp(pfad, name=None, ausfuehren=None, fortschritt=None, abbrechen=None):
    gerufen.append(name)
    return dict(ok=True, name=name, sha256="c" * 64, text="Importiert als " + name)


ki_modelle.importieren = imp
d.liste = [dict(name="rohrlaser-ki:latest"), dict(name="rohrlaser-ki-v2:latest")]
t = d._import_eins(dict(name="rohrlaser-ki", pfad=str(d), groesse_gb=2.5), ausfuehren=None)
d._import_fertig([t])
ki_modelle.importieren = merk
assert gerufen == ["rohrlaser-ki-v3"], gerufen
e = ki_register.finden(db, "rohrlaser-ki-v3#1")
assert e and e["sha256"] == "c" * 64 and e["status"] == ki_register.TEST
ok("KI-Zentrale: Reiter Modellversionen mit Klasse, Prüfen, Aktivieren, Zurücksetzen, Export; Import überschreibt nie")

print("ALLE TESTS OK")
