"""Winkel/U aus einem größeren Profil als virtuelles Bauteil (Patrick 26.10.2026: „ein virtuelles Rohrbauteil
anlegen, um den Schnittweg zu ermitteln“): STEP-Import.exe --stege misst Teil ∪ Stege 2 mm des größeren Profils.
Geprüft: gerades Teil, Gehrung, Ausklinkung am gekürzten Schenkel, U; Stege im 3D (Art ES); Prüfdialog-Weg
(_stege_messen, keine doppelten Längsschnitte) und Profilwechsel in der Positionstabelle (neu gemessen, zurück wie
gezeichnet).

Aufruf: python tests/test_winkel_virtuell.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
import zlib
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402
from erzeuge_testteile import cut, gehrung, profil, schreibe  # noqa: E402
import step_messen  # noqa: E402
from rohrlaser import schneidweg as sw, step  # noqa: E402

tmp = Path(tempfile.mkdtemp())
L = [(0, 0), (33, 0), (33, 6), (6, 6), (6, 30), (0, 30)]
gerade = profil(L, 500)
TEILE = {
    "W_gerade": gerade,
    "W_gehrung": gehrung(profil(L, 600), 500, 30),
    # Bohrung Ø10 im kurzen Schenkel und Ausklinkung 8 × 50 an seiner Kante (läuft in den Längsschnitt)
    "W_ausklinkung": cut(cut(gerade, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(20, -50, 250), gp_Dir(0, 1, 0)), 5,
                                                              100).Shape()),
                         BRepPrimAPI_MakeBox(gp_Pnt(25, -1, 100), 20, 10, 50).Shape()),
    "U_60x30": profil([(0, 0), (60, 0), (60, 30), (54, 30), (54, 6), (6, 6), (6, 30), (0, 30)], 400),
}
for name, s in TEILE.items():
    schreibe(s, name, tmp)
fehler = 0


def fall(text, fn):
    global fehler
    try:
        fn()
        print(f"OK     {text}")
    except AssertionError as e:
        fehler += 1
        print(f"FEHLER {text}: {e}")


def messen(name, stege=None):
    aus, netze = tmp / f"{name}_{bool(stege)}.txt", tmp / f"netze_{name}_{bool(stege)}"
    step_messen.main(["--ausgabe", str(aus), "--netze", str(netze), str(tmp / f"{name}.step")]
                     + (["--stege", stege] if stege else []))
    return step.lade_netze(step.lies_messwerte(aus), netze)[0]


def z(m, k):
    return float(m.get(k) or 0)


W60 = "L-Profil|60|40|6"


def messung():
    m0, m = messen("W_gerade"), messen("W_gerade", W60)
    assert m0["profilform"] == "L-Profil" and abs(z(m0, "schneidweg") - 126) < 0.1, m0["schneidweg"]
    assert "stege=virtuell" in m["sicherheit"] and (round(z(m, "abm_a"), 2), round(z(m, "abm_b"), 2)) == (60, 40), m["sicherheit"]
    # Enden über den ganzen Winkel 60x40, je Schenkel ein Längsschnitt zwischen den Stegen mit Querschnitten
    assert abs(z(m, "ende_a") - 100) < 0.1 and abs(z(m, "ende_b") - 100) < 0.1, (m["ende_a"], m["ende_b"])
    innen = step._paare(m["innen_liste"])
    assert len(innen) == 2 and all(abs(g - 496) < 0.1 for g, _ in innen), innen
    formel = sw.schenkel_kuerzen(dict(form="L-Profil", a=33, b=30, wand=6), dict(form="L-Profil", a=60, b=40), 500)
    assert abs(z(m, "innen") - formel["schnitt"]) < 0.02 * formel["schnitt"], (m["innen"], formel["schnitt"])
    n = json.loads(zlib.decompress(m["_netz"]).decode("utf-8"))
    assert "ES" in n["t"] and n["t"]["ES"], list(n["t"])
    # Einbaulage: das Teil (ohne Stege) liegt wie in der STEP (vorher um den Unterschied der Schwerlinien verschoben)
    assert welt_huelle(n) == ((0, 0, 0), (33, 30, 500)), welt_huelle(n)


def welt_huelle(n):
    """Hülle der Teil-Dreiecke (ohne Stege) in Dateilage, gerundet auf 0,01 mm."""
    lg, p = n["lage"], n["p"]
    o, ax, x = lg[:3], lg[3:6], lg[6:9]
    y = (ax[1] * x[2] - ax[2] * x[1], ax[2] * x[0] - ax[0] * x[2], ax[0] * x[1] - ax[1] * x[0])
    idx = {i for art, v in n["t"].items() if art not in ("ES", "EW", "EO") for i in v}
    pk = [tuple(o[k] + p[3 * i] * x[k] + p[3 * i + 1] * y[k] + p[3 * i + 2] * ax[k] for k in range(3)) for i in idx]
    return tuple(tuple(round(f(q[k] for q in pk), 2) + 0.0 for k in range(3)) for f in (min, max))


fall("gerader Winkel 33x30x6 aus 60x40x6: Enden 100 mm, zwei Längsschnitte 496 mm, Stege im 3D, Lage wie STEP",
     messung)


def gehrung_ausklinkung_u():
    m = messen("W_gehrung", W60)
    assert "stege=virtuell" in m["sicherheit"] and z(m, "ende_b") > z(m, "ende_a") + 5, (m["ende_a"], m["ende_b"])
    lang = sorted(g for g, _ in step._paare(m["innen_liste"]))
    assert lang[0] < 490, lang                  # Längsschnitt an der Gehrung kürzer als am geraden Ende
    m0, m = messen("W_ausklinkung"), messen("W_ausklinkung", W60)
    assert len(step._paare(m0["innen_liste"])) == 2 and len(step._paare(m["innen_liste"])) == 3, m["innen_liste"]
    # die Ausklinkung gehört zum Längsschnitt (kein eigener Schnitt), die Bohrung bleibt
    formel = sw.schenkel_kuerzen(dict(form="L-Profil", a=33, b=30, wand=6), dict(form="L-Profil", a=60, b=40), 500)
    assert z(m, "innen") < formel["schnitt"] + z(m0, "innen") - 30, (m["innen"], formel["schnitt"], m0["innen"])
    u = messen("U_60x30", "U-Profil|60|50|6")
    assert "stege=virtuell" in u["sicherheit"] and (round(z(u, "abm_a"), 2), round(z(u, "abm_b"), 2)) == (60, 50), (u["abm_a"], u["abm_b"])
    assert len(step._paare(u["innen_liste"])) == 2, u["innen_liste"]
    nu = json.loads(zlib.decompress(u["_netz"]).decode("utf-8"))
    assert welt_huelle(nu) == ((0, 0, 0), (60, 30, 400)), welt_huelle(nu)
    nicht = messen("U_60x30", "U-Profil|80|50|6")        # andere Steghöhe: wie gezeichnet
    assert "stege=virtuell" not in nicht["sicherheit"] and round(z(nicht, "abm_b"), 2) == 30, nicht["sicherheit"]


fall("Gehrung (Steg folgt der Endfläche), Ausklinkung im Längsschnitt, U 60x30 aus 60x50, andere Steghöhe nicht",
     gehrung_ausklinkung_u)


def programm():
    from PySide6.QtWidgets import QApplication
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.fenster import Hauptfenster
    QApplication.instance() or QApplication([])
    db = Datenbank(tmp / "w.db")
    db.profile_anlegen([dict(profil_id="L 33x30x6", form="L-Profil", a=33, b=30, wand=6),
                        dict(profil_id="L 60x40x6", form="L-Profil", a=60, b=40, wand=6)])
    f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
    s = f.angebot_oeffnen(db.angebot_neu(dict(kunde="Test", kundennr="4711")))
    # Prüfdialog-Weg: größeres Profil gewählt -> virtuelles Bauteil gemessen, keine Längsschnitte doppelt
    m = dict(messen("W_gerade"), _pfad=str(tmp / "W_gerade.step"), _profil="L 60x40x6", _uebernehmen=True)
    bericht = s._stege_messen([m])
    assert "1 Teil(e) als Bauteil mit Stegen" in bericht and m["_mess_original"]["abm_a"] == "33.0", (bericht, m)
    erg = step.uebernehmen([m], [], s.k, db.zeilen("gewinde"), None, "S235-10219", 1)
    p = erg["positionen"][0]
    assert p["profil_id"] == "L 60x40x6" and abs(p["schneidweg"] - z(m, "schneidweg")) < 0.1, p["schneidweg"]
    e = sw.lesen(p["technik"])
    assert e.get("stege_virtuell") and e.get("step_datei"), e
    from rohrlaser import rechnen
    r = sw.rechnen(e, dict(s.k.profile["L 60x40x6"], profil_id="L 60x40x6"), rechnen.kontur_regel(None, 6))
    assert abs(r["schneidweg"] - p["schneidweg"]) < 0.5, (r["schneidweg"], p["schneidweg"])   # Rohr-Editor gleich
    # Tabelle: wie gezeichnet übernommen, dann Profil geändert -> neu gemessen; zurück -> wie gezeichnet
    s.step_importieren([str(tmp / "W_gerade.step")], "S235-10219", 1, als_satz=False)
    q = s.positionen[-1]
    assert q["profil_id"] == "L 33x30x6" and abs(q["schneidweg"] - 126) < 0.1, q["profil_id"]
    zeile = len(s.positionen) - 1
    spalte = next(i for i, (art, f_) in enumerate(s.pos_modell.spalten) if art == "feld" and f_.name == "profil_id")
    assert s.pos_modell.setData(s.pos_modell.index(zeile, spalte), "L 60x40x6")
    q = s.positionen[zeile]
    assert abs(q["schneidweg"] - z(m, "schneidweg")) < 0.1 and sw.lesen(q["technik"]).get("stege_virtuell"), \
        q["schneidweg"]
    n = json.loads(zlib.decompress(db.netz(q["id"])).decode("utf-8"))
    assert "ES" in n["t"], list(n["t"])
    assert s.pos_modell.setData(s.pos_modell.index(zeile, spalte), "L 33x30x6")
    q = s.positionen[zeile]
    assert abs(q["schneidweg"] - 126) < 0.1 and not sw.lesen(q["technik"]).get("stege_virtuell"), q["schneidweg"]
    f.close()


fall("Programm: Prüfdialog misst das virtuelle Bauteil, Profilwechsel in der Tabelle misst neu (und zurück)", programm)

print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
sys.exit(1 if fehler else 0)
