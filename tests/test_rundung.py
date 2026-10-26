"""Prüft die Rundung im Angebot: Stückpreise kaufmännisch auf Cent, Gesamtpreis jeder Zeile = Stückpreis × Menge,
Nettosumme = Summe der Zeilen, MwSt. und Brutto auf den Cent, Staffelpreise ebenso (Preis je Einheit × Menge +
einmalige Kosten = Gesamt). Geprüft an allen Abnahme-Angeboten, dem Beispielangebot mit Sätzen und Staffeln und
an Grenzfällen (halber Cent).

Aufruf: python tests/test_rundung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from abnahme_angebote import ANGEBOTE, programm_positionen  # noqa: E402
from rohrlaser import ausgabe  # noqa: E402
from rohrlaser.ausgabe import kaufm_runden  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import Kontext  # noqa: E402


def ok(text):
    print("OK    ", text)


def cent(x):
    """Betrag in ganzen Cent (der Wert muss schon auf Cent stehen)."""
    c = Decimal(repr(float(x))) * 100
    assert c == c.to_integral_value(), f"{x} ist nicht auf den Cent gerundet"
    return int(c)


def kaufm_cent(x):
    return int((Decimal(repr(float(x))) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ------------------------------------------------------------------ R1 kaufmännisch runden
for wert, soll in ((2.675, 2.68), (1.005, 1.01), (0.125, 0.13), (2.665, 2.67), (-1.005, -1.01), (10.0, 10.0),
                   (0.1 + 0.2, 0.3), (123456.785, 123456.79)):
    assert kaufm_runden(wert) == soll, (wert, kaufm_runden(wert), soll)
ok("R1 kaufmännisch runden: halber Cent immer aufwärts (2,675 → 2,68; 1,005 → 1,01), auch wo round() abrundet")

# ------------------------------------------------------------------ R2 Angebotsinhalt: Grenzfall halber Cent
positionen = [dict(profil_id="X", stueck=3, pos=10), dict(profil_id="X", stueck=7, pos=20, satz="A", je_satz=1),
              dict(profil_id="X", stueck=7, pos=30, satz="A", je_satz=1)]
kalk = [dict(preis_teil=2.675, hinweis=None), dict(preis_teil=1.005, hinweis=None),
        dict(preis_teil=0.125, hinweis=None)]
ang = ausgabe.angebot({}, positionen, kalk, Kontext(), dict(mwst=0.19))
teil, satz = ang["zeilen"][0], ang["zeilen"][1]
assert (teil["preis"], teil["gesamt"]) == (2.68, 8.04), teil
assert (satz["preis"], satz["menge"], satz["gesamt"]) == (1.14, 7, 7.98), satz
assert cent(ang["netto"]) == 1602 and cent(ang["mwst"]) == kaufm_cent(16.02 * 0.19) == 304
assert cent(ang["brutto"]) == 1906
ok("R2 halber Cent im Stückpreis: 2,675 → 2,68 € × 3 = 8,04 €; Satz 1,01 + 0,13 = 1,14 € × 7 = 7,98 €; "
   "netto 16,02 €, MwSt. 3,04 €, brutto 19,06 €")


# ------------------------------------------------------------------ R3 alle Abnahme-Angebote und Beispiel
def pr_mwst(st):
    return st["wirksam"]["mwst"]


def pruefen(name, ang, kalk_zeilen):
    zeilen = [z for z in ang["zeilen"] if z["gesamt"] is not None]
    for z in zeilen:
        assert cent(z["gesamt"]) == cent(z["preis"]) * int(z["menge"]), (name, z)
    assert cent(ang["netto"]) == sum(cent(z["gesamt"]) for z in zeilen), name
    assert cent(ang["mwst"]) == kaufm_cent(ang["netto"] * ang["mwst_satz"]), name
    assert cent(ang["brutto"]) == cent(ang["netto"]) + cent(ang["mwst"]), name
    for z in ang["staffeln"]:
        st = next(x for x in staffeln if x["menge"] == z["menge"] and x.get("preis_gesamt") is not None and (
            x.get("preis_einheit") == z["preis"] or (x.get("preis") or {}).get("einmalig")))
        einmalig = (st.get("preis") or {}).get("einmalig") or 0
        if einmalig:        # Rüsten separat: im Angebot im Stufenpreis enthalten (aufgerundet)
            assert cent(z["gesamt"]) == cent(z["preis"]) * int(z["menge"]) >= cent(st["preis_gesamt"]), (name, z)
            continue
        assert cent(z["gesamt"]) == cent(z["preis"]) * int(z["menge"]), (name, z)
        pr = st["preis"]
        assert cent(pr["mwst"]) == kaufm_cent(z["gesamt"] * pr_mwst(st)), (name, pr)
        assert cent(pr["brutto"]) == cent(z["gesamt"]) + cent(pr["mwst"]), (name, pr)
    return len(zeilen), len(ang["staffeln"])


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
n_zeilen = n_staffeln = 0
for angebot in ANGEBOTE + [None]:
    if angebot is None:
        aid, name = beispiel_angebot.anlegen(db), "Beispielangebot"
    else:
        aid = db.angebot_neu({n: angebot[n] for n in ("nummer", "kunde", "maschine", "stange")})
        for p in programm_positionen(angebot):
            db.position_neu(aid, p)
        name = angebot["name"]
    s = fenster.angebot_oeffnen(aid)
    assert s.optimieren()
    staffeln = s.staffelpreise_rechnen() or []
    ang = s.angebot_daten()
    z, st = pruefen(name, ang, None)
    n_zeilen, n_staffeln = n_zeilen + z, n_staffeln + st
assert n_staffeln, "Beispielangebot hat Staffeln"
ok(f"R3 {len(ANGEBOTE) + 1} Angebote, {n_zeilen} Preiszeilen und {n_staffeln} Staffelpreise: Gesamt = Stückpreis × "
   "Menge, Netto = Summe der Zeilen, MwSt. und Brutto auf den Cent")
print("Alle Prüfungen bestanden.")
