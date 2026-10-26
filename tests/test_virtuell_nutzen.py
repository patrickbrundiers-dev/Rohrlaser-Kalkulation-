"""Virtuelles Bauteil weiter nutzen (Patrick 26.10.2026, Freigabe 1, 2, 4 und „Je nach Kunde wählbar“):
- V1 STEP-Export: STEP-Import.exe --virtuell schreibt den Körper mit Stegen (Winkel aus größerem Profil) bzw. Ringen
  (offenes Rohr) als k<Nr>.step; er liest sich wieder, Volumen = Teil + Stege, Lage wie die Kundendatei.
- V2 Messwerte -> technik: volumen_teil, volumen_gezeichnet, l_step, stege_virtuell bzw. offen_virtuell.
- V3 Gewicht je Teil aus dem Volumen (mit Stegen; abgetrennt wie gezeichnet), Rest Abfall; Zusatzarbeiten €/kg mit
  diesem Gewicht, €/m² anteilig.
- V4 Programm: Profilwechsel misst das virtuelle Bauteil, „Stege abtrennen“ (Zusatzarbeit, Gewicht, bleibt beim
  Profilwechsel), Rechtsklick nur bei virtuellen Teilen, STEP speichern, Schneidweg-Rechner behält die Messwerte,
  Zeichnung und Werkstattpapiere mit Hinweis, Netz-Ausschnitt der Enden.
- V6 Plausibilität (Prüfregel „Virtuelles Bauteil prüfen“): Mehrvolumen gegen 2 × 2 mm × Querschnittsunterschied.
- V5 Satz in 3D als STEP-Baugruppe: Stege bleiben -> exakter Körper des virtuellen Bauteils, abgetrennt -> wie
  gezeichnet, Lage wie die Kundendatei.

Aufruf: python tests/test_virtuell_nutzen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from erzeuge_testteile import profil, schreibe  # noqa: E402
import step_geometrie as g  # noqa: E402
import step_messen  # noqa: E402
from rohrlaser import rechnen, schneidweg as sw, step, virtuell  # noqa: E402

tmp = Path(tempfile.mkdtemp())
W = profil([(0, 0), (33, 0), (33, 6), (6, 6), (6, 30), (0, 30)], 500)
U = profil([(-30, -20), (30, -20), (30, 20), (28, 20), (28, -18), (-28, -18), (-28, 20), (-30, 20)], 300,
           {(-30, -20): 4, (30, -20): 4, (28, -18): 2, (-28, -18): 2})
schreibe(W, "W", tmp)
schreibe(U, "U", tmp)
W60 = "L-Profil|60|40|6"
fehler = 0


def fall(text, fn):
    global fehler
    try:
        fn()
        print(f"OK     {text}")
    except AssertionError as e:
        fehler += 1
        print(f"FEHLER {text}: {e}")


def messen(name, stege=None, ordner=None):
    aus = tmp / f"{name}_{bool(stege)}_{bool(ordner)}.txt"
    step_messen.main(["--ausgabe", str(aus), str(tmp / f"{name}.step")] + (["--stege", stege] if stege else [])
                     + (["--virtuell", str(ordner)] if ordner else []))
    return step.lies_messwerte(aus)[0]


def bbox(datei):
    k = g.lies_step(str(datei))[0]
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.Add_s(k, b)
    return k, [round(v, 2) for v in (*b.CornerMin().Coord(), *b.CornerMax().Coord())]


def export():
    mw = messen("W", W60, tmp / "vw")
    vw = virtuell.volumen(mw)
    assert vw and abs(vw[1] - 171000) < 1 and abs(vw[0] - vw[1] - 2 * 2 * (27 * 6 + 10 * 6)) < 5, vw
    k, box = bbox(tmp / "vw" / "k1.step")
    assert abs(g._volumen(k) - vw[0]) < 1, (g._volumen(k), vw)
    _, box0 = bbox(tmp / "W.step")
    # Lage wie die Kundendatei: das Teil liegt im virtuellen Körper an derselben Stelle (Ferse bei 0/0, Länge 0 … 500)
    assert box[:3] == box0[:3] and box[5] == box0[5] and box[3] > box0[3] + 20, (box, box0)
    mu = messen("U", None, tmp / "vu")
    assert virtuell.volumen(mu) is None and step.rohr_wechseln(mu)      # gilt erst als Rohr (wie die Übernahme)
    vu = virtuell.volumen(mu)
    assert vu and vu[0] > vu[1], vu
    k, _ = bbox(tmp / "vu" / "k1.step")
    assert abs(g._volumen(k) - vu[0]) < 1, (g._volumen(k), vu)
    assert not (tmp / "nichts").exists() and virtuell.volumen(messen("W")) is None   # wie gezeichnet: keins


fall("V1 STEP-Export des virtuellen Bauteils: Winkel mit Stegen, offenes Rohr mit Ringen, Lage und Volumen", export)


class K:
    def __init__(self):
        self.profile = {"L 60x40x6": dict(profil_id="L 60x40x6", form="L-Profil", a=60, b=40, wand=6),
                        "RE 60x50x2": dict(profil_id="RE 60x50x2", form="Rechteckrohr", a=60, b=50, wand=2)}
        self.werkstoffe = {"S235": dict(werkstoff_id="S235", dichte=7.85)}
        self.maschinen = {}


ERG = {}


def technik():
    mw = messen("W", W60)
    e = step.rechner_eingaben(dict(mw, _pfad=str(tmp / "W.step")), "L-Profil", 60, 40)
    assert e.get("stege_virtuell") and e.get("volumen_teil") > e.get("volumen_gezeichnet") > 0, e
    assert e.get("l_step") == 500 and e.get("step_datei", "").endswith("W.step"), e
    ERG["W"] = e
    mu = messen("U")
    assert step.rohr_wechseln(mu)
    e = step.rechner_eingaben(mu, mu["profilform"], 60, 50)
    assert e.get("offen_virtuell") and not e.get("stege_virtuell") and e.get("volumen_teil") > 0, e
    ERG["U"] = e


fall("V2 Messwerte -> technik: Volumen mit und ohne Stege, Länge, Datei, Art", technik)


def plausibel():
    from rohrlaser import dfm
    k = K()

    def befunde(e, profil_id, zeilen=None):
        p = dict(laenge=e.get("l_step") or 500, technik=json.dumps(e))
        return [b for b in dfm.rohr(p, k.profile[profil_id], zeilen=zeilen) if b.regel == dfm.VIRTUELL_PRUEFEN]
    # gemessen: passt (Winkel aus größerem Profil, offenes Rohr mit Ringen)
    assert not befunde(ERG["W"], "L 60x40x6") and not befunde(ERG["U"], "RE 60x50x2"), \
        (befunde(ERG["W"], "L 60x40x6"), befunde(ERG["U"], "RE 60x50x2"), ERG["U"])
    # kein Mehrvolumen bzw. ein Vielfaches: Warnung
    e = ERG["W"]
    ohne = befunde(dict(e, volumen_teil=e["volumen_gezeichnet"]), "L 60x40x6")
    assert len(ohne) == 1 and "ohne Mehrvolumen" in ohne[0].text and ohne[0].stufe == dfm.WARNUNG, ohne
    viel = befunde(dict(e, volumen_teil=e["volumen_gezeichnet"] + 10 * 888), "L 60x40x6")
    assert len(viel) == 1 and "erwartet etwa 0,9 cm³" in viel[0].text, viel
    assert not befunde(dict(e, volumen_teil=e["volumen_gezeichnet"] + 2 * 888), "L 60x40x6")
    # abgeschaltet: nichts
    assert not befunde(dict(e, volumen_teil=e["volumen_gezeichnet"]), "L 60x40x6",
                       [dict(regel=dfm.VIRTUELL_PRUEFEN, aktiv="nein")])
    # Datenbank: neue Regel in der Tabelle, ältere Datenbank bekommt sie einmalig dazu
    from rohrlaser.datenbank import Datenbank
    db = Datenbank(tmp / "regeln.db")
    rid = next(z["id"] for z in db.zeilen("pruefregeln") if z["regel"] == dfm.VIRTUELL_PRUEFEN)
    with db.con:
        db.con.execute("DELETE FROM pruefregeln WHERE id=?", (rid,))
    db.einstellung_setzen("stege_stand", "2026-10-26")
    db.con.close()
    db = Datenbank(tmp / "regeln.db")
    assert sum(z["regel"] == dfm.VIRTUELL_PRUEFEN for z in db.zeilen("pruefregeln")) == 1
    db.con.close()


fall("V6 Plausibilität: Mehrvolumen der Stege/Ringe gegen erwartet, Regel abschaltbar, Migration", plausibel)


T = dict(preise=[])


def gewicht():
    e = dict(stege_virtuell=True, volumen_teil=180000.0, volumen_gezeichnet=171000.0, l_step=500)
    p = dict(profil_id="L 60x40x6", werkstoff_id="S235", laenge=500, stueck=2, technik=json.dumps(e))
    k = K()
    voll = rechnen.kg_je_m("L 60x40x6", "S235", k)
    w = rechnen.position_werte(p, {}, k, T)
    assert abs(w["gewicht"] - 180000 * 7.85 / 1e6) < 1e-6 and abs(w["gewicht_position"] - 2 * w["gewicht"]) < 1e-9, w
    assert abs(w["abfall_kg"] - (voll * 0.5 - w["gewicht"])) < 1e-6, w["abfall_kg"]
    # Zusatzarbeiten €/kg (Verzinken) mit dem Teilegewicht, €/m² (Pulvern) anteilig zum ganzen Profil
    assert abs(rechnen.zusatz_menge_auto("€/kg", p, k) - w["gewicht"]) < 1e-9
    p0 = dict(p, technik=json.dumps(dict(konturen=[])))
    m2, m2_0 = rechnen.zusatz_menge_auto("€/m²", p, k), rechnen.zusatz_menge_auto("€/m²", p0, k)
    assert m2_0 and abs(m2 - m2_0 * w["gewicht"] / (voll * 0.5)) < 1e-9 and m2 < m2_0, (m2, m2_0)
    p["technik"] = json.dumps(dict(e, stege_abtrennen=True))
    assert abs(rechnen.position_werte(p, {}, k, T)["gewicht"] - 171000 * 7.85 / 1e6) < 1e-6
    w0 = rechnen.position_werte(dict(p, profil_id="L fehlt"), {}, k, T)     # Profil nicht in den Stammdaten
    assert abs(w0["gewicht"] - 171000 * 7.85 / 1e6) < 1e-6 and w0["abfall_kg"] is None, w0
    p["laenge"] = 250           # Länge geändert: anteilig
    assert abs(rechnen.position_werte(p, {}, k, T)["gewicht"] - 171000 * 7.85 / 1e6 / 2) < 1e-6
    p["technik"] = json.dumps(dict(konturen=[]))
    assert abs(rechnen.position_werte(p, {}, k, T)["gewicht"] - voll * 0.25) < 1e-9


fall("V3 Gewicht aus dem Volumen: mit Stegen, abgetrennt wie gezeichnet, Länge anteilig, sonst Metergewicht; "
     "Zusatzarbeiten €/kg und €/m²", gewicht)


def programm():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import ausgabe, zeichnung
    from rohrlaser.ansicht3d import entpacken
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.fenster import Hauptfenster
    from rohrlaser.schneidweg_dialog import SchneidwegDialog
    app = QApplication.instance() or QApplication([])
    db = Datenbank(tmp / "v.db")
    db.profile_anlegen([dict(profil_id="L 33x30x6", form="L-Profil", a=33, b=30, wand=6),
                        dict(profil_id="L 60x40x6", form="L-Profil", a=60, b=40, wand=6)])
    assert any(z["name"] == virtuell.ZUSATZ_STEGE for z in db.zeilen("zusatzarbeiten"))
    f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
    s = f.angebot_oeffnen(db.angebot_neu(dict(kunde="Test", kundennr="4711")))
    s.step_importieren([str(tmp / "W.step")], "S235-10219", 4, als_satz=False)
    zeile = len(s.positionen) - 1
    # wie gezeichnet: kein virtuelles Bauteil, Rechtsklick ohne die Einträge
    s.pos_ansicht.selectRow(zeile)
    assert "Virtuelles Bauteil als STEP …" not in s._pos_menue_anpassen()
    spalte = next(i for i, (art, f_) in enumerate(s.pos_modell.spalten) if art == "feld" and f_.name == "profil_id")
    assert s.pos_modell.setData(s.pos_modell.index(zeile, spalte), "L 60x40x6")
    q = s.positionen[zeile]
    e = virtuell.technik_lesen(q)
    assert e.get("stege_virtuell") and e.get("volumen_teil"), q.get("technik")
    s.pos_ansicht.selectRow(zeile)
    sichtbar = s._pos_menue_anpassen()
    assert "Virtuelles Bauteil als STEP …" in sichtbar and "Stege abtrennen an/aus" in sichtbar, sichtbar
    g_mit = rechnen.position_werte(q, s.kopf, s.k, s.tabellen)["gewicht"]
    # Stege abtrennen: Zusatzarbeit, Gewicht wie gezeichnet; zurück: weg
    assert s.stege_abtrennen([zeile], True) == 1
    q = s.positionen[zeile]
    assert virtuell.ZUSATZ_STEGE in (q.get("zusatz") or ""), q.get("zusatz")
    g_ab = rechnen.position_werte(q, s.kopf, s.k, s.tabellen)["gewicht"]
    assert g_ab < g_mit, (g_ab, g_mit)
    # Schneidweg-Rechner: Messwerte und Wahl bleiben beim Speichern, Häkchen sichtbar
    d = SchneidwegDialog(s, q, s.k.profile["L 60x40x6"], s.kopf, s.k, s.tabellen, db=db)
    ein = d.eingaben()
    assert ein.get("stege_virtuell") and ein.get("stege_abtrennen") and ein.get("volumen_teil"), ein
    assert d.stege_ab.isVisibleTo(d) and d.stege_ab.isChecked()
    d.stege_ab.setChecked(False)
    assert not d.eingaben().get("stege_abtrennen")
    # Zeichnung mit Hinweis und Bildern
    pdf = tmp / "z.pdf"
    erg = sw.rechnen(ein, s.k.profile["L 60x40x6"], rechnen.kontur_regel(None, 6), laenge=q.get("laenge"))
    assert any(k_.get("umriss") for k_ in ein["konturen"]), ein["konturen"]     # Längsschnitt als Rechteck
    zeichnung.zeichnung_pdf(str(pdf), s.kopf, q, s.k.profile["L 60x40x6"], ein, erg,
                            netz=entpacken(db.netz(q["id"])))
    assert pdf.stat().st_size > 20000, pdf.stat().st_size
    d.close()
    # Profilwechsel wie gezeichnet: kein virtuelles Bauteil mehr, Zusatzarbeit weg; wieder größer: wieder virtuell
    assert s.pos_modell.setData(s.pos_modell.index(zeile, spalte), "L 33x30x6")
    q = s.positionen[zeile]
    assert not virtuell.technik_lesen(q) and virtuell.ZUSATZ_STEGE not in (q.get("zusatz") or ""), q.get("zusatz")
    assert s.stege_abtrennen([zeile], True) == 0            # keine virtuelle Position: nichts
    assert s.pos_modell.setData(s.pos_modell.index(zeile, spalte), "L 60x40x6")
    assert s.stege_abtrennen([zeile], True) == 1
    # Werkstattpapiere: Hinweis je Position
    q = s.positionen[zeile]
    st = ausgabe.stege_hinweise(s.positionen)
    assert len(st) == 1 and st[0]["abtrennen"] and "abtrennen" in st[0]["text"], st
    # STEP speichern
    ziel = tmp / "virtuell_export.step"
    assert s.virtuell_step_speichern(zeile, str(ziel)) == str(ziel) and ziel.stat().st_size > 1000
    k, _ = bbox(ziel)
    assert abs(g._volumen(k) - virtuell.technik_lesen(q)["volumen_teil"]) < 1
    # Netz-Ausschnitt der Enden: nur Dreiecke nahe am Ende, Stege dabei
    n = entpacken(db.netz(q["id"]))
    a = virtuell.netz_ausschnitt(n, "a")
    zs = a["p"][2::3]
    assert zs and max(zs) - min(n["p"][2::3]) <= 80.6 and "ES" in a["t"] and len(a["p"]) < len(n["p"]), \
        (max(zs), list(a["t"]))
    assert max(j for idx in a["t"].values() for j in idx) < len(a["p"]) // 3
    # V5 Satz in 3D als STEP-Baugruppe: Stege abgetrennt -> Teil wie gezeichnet (Netz ohne Stege), Stege bleiben ->
    # der exakte Körper des virtuellen Bauteils, beide in der Lage der Kundendatei
    _, box0 = bbox(tmp / "W.step")
    erg, (k, box) = satz_export(s, db, q, "satz_ab.step")
    assert any("abgetrennt" in h for h in erg["hinweise"]) and abs(g._volumen(k) - 171000) < 1500, \
        (erg["hinweise"], g._volumen(k))
    assert all(abs(u - v) < 0.3 for u, v in zip(box, box0)), (box, box0)
    s.stege_abtrennen([zeile], False)
    q = s.positionen[zeile]
    erg, (k, box) = satz_export(s, db, q, "satz_virtuell.step")
    assert any("virtuelles Bauteil" in h for h in erg["hinweise"]), erg["hinweise"]
    assert abs(g._volumen(k) - virtuell.technik_lesen(q)["volumen_teil"]) < 1, g._volumen(k)
    _, box_v = bbox(tmp / "vw" / "k1.step")
    assert all(abs(u - v) < 0.01 for u, v in zip(box, box_v)), (box, box_v)
    f.close()
    app.processEvents()


def satz_export(s, db, q, name):
    from rohrlaser.satz3d import Satz3dDialog
    d = Satz3dDialog(s, "S1", [dict(q, satz="S1")], s.k.profile, s._vk_einstellungen(), db.netze(s.id))
    d.stumm = True
    ziel = tmp / name
    assert d.step_speichern(str(ziel)) == str(ziel) and d.step_ergebnis["einsaetze"] == 1, d.step_ergebnis
    d.close()
    return d.step_ergebnis, bbox(ziel)


fall("V4/V5 Programm: Profilwechsel, Stege abtrennen, Rechtsklick, Rechner, Zeichnung, Werkstatt, STEP speichern, "
     "Satz-Export mit virtuellem Körper", programm)

print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
sys.exit(1 if fehler else 0)
