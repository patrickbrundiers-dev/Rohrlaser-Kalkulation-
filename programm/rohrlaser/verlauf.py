"""Rückgängig und Wiederholen im geöffneten Angebot (Strg+Z, Strg+Y).

Nach jeder Änderung vergleicht das Angebotsfenster den gespeicherten Stand des Angebots (Kopf, Positionen,
Staffeln, STEP-Protokoll, 3D-Netze) mit dem zuletzt gemerkten; ist er anders, kommt der alte Stand auf den
Rückgängig-Stapel. So erfasst der Verlauf jede Änderung, gleich über welchen Knopf oder Dialog sie kam.
Der Verlauf gilt, solange das Angebot geöffnet ist; Stammdaten und Einstellungen gehören nicht dazu.
"""
from .angebot import KOPF, POSITIONEN

GRENZE = 100        # so viele Schritte lassen sich zurücknehmen


class Verlauf:
    def __init__(self, db, angebot_id):
        self.db, self.id = db, angebot_id
        self.zurueck, self.vor = [], []
        self.netze = {}         # Positions-ID -> Netz-Bytes, nur einmal gelesen (Netze ändern sich praktisch nie)
        self.stand = None       # zuletzt gemerkter Stand
        self.pause = 0          # > 0: mehrere Änderungen zu einem Schritt sammeln (z. B. Einfügen mehrerer Zellen)
        self.spalten = [r[1] for r in db.con.execute("PRAGMA table_info(positionen)")]

    def _lesen(self):
        s = self.db.angebot_stand(self.id)
        if s is not None:
            for pid, laenge in s["netze"].items():
                if pid not in self.netze or len(self.netze[pid]) != laenge:
                    self.netze[pid] = self.db.netz(pid)
        return s

    def merken(self):
        """Nach einer Änderung aufrufen: Ergebnis True, wenn ein neuer Schritt entstanden ist."""
        if self.pause:
            return False
        neu = self._lesen()
        if neu is None or neu == self.stand:
            return False
        alt, self.stand = self.stand, neu
        if alt is None:             # erster Stand beim Öffnen
            return False
        self.zurueck.append(alt)
        del self.zurueck[:-GRENZE]
        self.vor.clear()
        return True

    def _setzen(self, von, nach):
        """Ergebnis: Beschreibung des Schritts (für die Statuszeile) oder None (nichts zu tun)."""
        self.merken()               # noch nicht gemerkte Änderungen (z. B. Staffelwerte) zuerst als Schritt sichern
        if not von:
            return None
        ziel, jetzt = von.pop(), self.stand
        nach.append(jetzt)
        self.db.angebot_stand_setzen(self.id, ziel, {pid: self.netze[pid] for pid in ziel["netze"]})
        self.stand = self._lesen()
        return beschreiben(jetzt, ziel, self.spalten)

    def rueckgaengig(self):
        return self._setzen(self.zurueck, self.vor)

    def wiederholen(self):
        return self._setzen(self.vor, self.zurueck)


def _titel(felder, name):
    return next((f.titel for f in felder if f.name == name), name)


def beschreiben(a, b, spalten):
    """Kurzer Text, was sich zwischen zwei Ständen unterscheidet (z. B. 'Länge [mm] Pos. 20').
    spalten: Spaltennamen der Tabelle positionen in der Reihenfolge der Stand-Zeilen."""
    pa, pb = {z[0]: z for z in a["positionen"]}, {z[0]: z for z in b["positionen"]}
    if set(pa) != set(pb):
        d = len(pb) - len(pa)
        if d:
            return f"{abs(d)} Position(en) " + ("hinzugefügt" if d > 0 else "entfernt")
        return "Positionen"
    geaendert = [pid for pid in pa if pa[pid] != pb[pid]]
    if geaendert:
        z_a, z_b = pa[geaendert[0]], pb[geaendert[0]]
        namen = [n for n, x, y in zip(spalten, z_a, z_b) if x != y and n != "nr"]
        was = ", ".join(_titel(POSITIONEN.felder, n) for n in namen[:2]) or "Position"
        pos = dict(zip(spalten, z_b)).get("pos")
        nr = f" Pos. {pos:g}" if isinstance(pos, (int, float)) else ""
        return was + nr + (f" und {len(geaendert) - 1} weitere" if len(geaendert) > 1 else "")
    ka, kb = dict(a["angebot"]), dict(b["angebot"])
    kopf = [f.name for f in KOPF if ka.get(f.name) != kb.get(f.name)]
    if kopf:
        return ", ".join(_titel(KOPF, n) for n in kopf[:2])
    if a["staffeln"] != b["staffeln"]:
        return "Staffeln"
    if ka.get("ergebnis") != kb.get("ergebnis"):
        return "Optimierung"
    if a["protokoll"] != b["protokoll"]:
        return "STEP-Import"
    return "Änderung"
