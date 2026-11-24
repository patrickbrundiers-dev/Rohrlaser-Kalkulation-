"""KI-Andockpunkt STEP-Import (Master-Auftrag Patrick 21.11.2026 „STEP-Import vollständig weiterentwickeln“, Abschnitt
lokale KI): Trainingsaufgabe „step_art“ aus von Hand eingeordneten STEP-Teilen (ki_training), Prüfsatz-Titel.

- K1 Quellen: gemerkte Zukaufteil-/Fertigungsteil-Entscheidungen (Name + Geometrie) und gemerkte Arten (Geometrie)
- K2 nur gültige Einträge (ohne Geometrie oder unbekannte Entscheidung: weg); Eingabe lesbar, Volumen in cm³
- K3 Export: step_art_train/test.jsonl im Chat-Format, Widersprüche verworfen; Prüfsatz kennt „eigene STEP-Teile“

Aufruf: python tests/test_ki_step_art.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "programm"))

from rohrlaser import ki_pruefsatz, ki_training, step, zukaufteile as zk  # noqa: E402


class DB:
    nur_lesen = None

    def __init__(self, w):
        self.w = w

    def einstellung(self, n):
        return json.loads(json.dumps(self.w.get(n)))

    def einstellung_setzen(self, n, v):
        self.w[n] = v


db = DB({zk.GELERNT: {"8|8|20|90|3|3#schraube m8x20": [zk.ZUKAUF, zk.SCHRAUBE, "21.11.2026"],
                      "40|5|60|900|6|12#halter": [zk.FERTIGUNG, "", "21.11.2026"],
                      "#ohne geometrie": [zk.ZUKAUF, "", ""], "1|2|3|4|5|6#x": ["unbekannt", "", ""]},
         step.ART_GELERNT: {"40|40|600|9000|20|40": ["Rohrlaser-Teil", "20.11.2026"], "3|100|200|6000|6|12": "Blech"},
         "kunden_namen": []})
f = ki_training._step_arten(db)
paare = {(x["eingabe"], x["antwort"]) for x in f}
assert ("Bauteil „schraube m8x20“, Hülle 8 × 8 × 20 mm, Volumen 0.9 cm³, Flächen 3, Kanten 3",
        "Zukaufteil: Schraube") in paare, paare
assert ("Bauteil „halter“, Hülle 40 × 5 × 60 mm, Volumen 9 cm³, Flächen 6, Kanten 12", "Fertigungsteil") in paare
assert any(a == "Rohrlaser-Teil" and e.startswith("Bauteil ohne Namen, Hülle 40 × 40 × 600 mm") for e, a in paare)
assert any(a == "Blech" for _, a in paare) and len(f) == 4, f
print("OK: K1/K2 Quellen Zukauf/Fertigung und gemerkte Arten, nur gültige Einträge")

tmp = Path(tempfile.mkdtemp())
ex = ki_training.exportieren(db, tmp, faelle=dict(step_art=f + [dict(eingabe=f[0]["eingabe"], antwort="Mutter")]))
ordner = Path(ex["ordner"])
assert {p.name for p in ordner.glob("step_art_*.jsonl")} == {"step_art_train.jsonl", "step_art_test.jsonl"}
assert ex["aufgaben"]["step_art"]["verworfen"] == {"widersprüchliche Antworten": 2}, ex["aufgaben"]
zeilen = [json.loads(z) for p in ordner.glob("step_art_*.jsonl") for z in p.read_text(encoding="utf-8").splitlines()]
assert len(zeilen) == 3 and all(z["messages"][0]["content"] == ki_training.SYSTEM["step_art"] for z in zeilen)
assert ki_pruefsatz.ART_TITEL["eigen_step_art"] == "eigene STEP-Teile"
print("OK: K3 Export step_art (Chat-Format, Widersprüche raus), Prüfsatz-Titel")
print("Alle Tests bestanden.")
