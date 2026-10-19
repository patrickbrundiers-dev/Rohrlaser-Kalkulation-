"""Abnahme des Programms (Schritt 4) mit realistischen Testaufträgen (tests/abnahme_auftraege.py).

Je Auftrag läuft der Weg des Programms: Stammdaten aus der Mappe in die Datenbank, Auftrag anlegen,
optimieren, Ergebnis speichern und wieder lesen. Das gespeicherte Ergebnis wird unabhängig von der
Optimierung nachgerechnet, nur aus den Stammdaten und den Positionen:

1. Teile korrekt eingeplant: jede gültige Position mit voller Stückzahl, kein Teil doppelt, keine
   Vermischung von Profil, Werkstoff oder Stangenlänge; ungültige Positionen stehen vollständig unter
   "nicht eingeplant".
2. Keine Stange überlastet: Lage jedes Teils (von/bis) gegen Endbeschnitt, Trennung (gemeinsamer Schnitt
   nur bei zwei geraden Enden), Schnittverlust und Greiferrest.
3. Materialbedarf und Restlängen stimmen: Belegung, Rest, Gewicht, Materialkosten je Stange, je Position
   und je Teil.
4. Besser als eine einfache manuelle Einteilung (Eingabereihenfolge, Stange voll, dann nächste) und nie
   unter der rechnerischen Untergrenze.
5. Programm rechnet wie die Mappe: derselbe Auftrag in der Mappe (Python-Optimierung + LibreOffice-
   Formeln) gegen das Programm, Zelle für Zelle (wie tests/test_programm_mappe.py).

Aufruf: python tests/test_abnahme.py [--protokoll DATEI.md] [--ohne-mappe]
        (--ohne-mappe: Punkt 5 auslassen, dann ist kein LibreOffice nötig)
"""
import argparse
import math
import shutil
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "tools"))
sys.path.insert(0, str(HIER))
from openpyxl import load_workbook  # noqa: E402
from abnahme_auftraege import AUFTRAEGE, mappe_fuellen  # noqa: E402
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.auftrag import KOPF  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.mappe_import import lies_mappe, lies_auftrag  # noqa: E402

MAPPE = HIER.parent / "mappe" / "Rohrlaser_Kalkulation_v02.xlsm"
TOL = 1e-6


def nahe(a, b, tol=TOL):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def flaeche(profil):
    """Querschnitt [mm²] aus den Abmessungen (eigene Rechnung, nicht aus dem Programm)."""
    if profil.get("flaeche_manuell"):
        return profil["flaeche_manuell"]
    a, b, s = profil["a"], profil.get("b"), profil["wand"]
    if profil["form"] == "Rundrohr":
        return math.pi / 4 * (a ** 2 - (a - 2 * s) ** 2)
    b = a if profil["form"] == "Quadratrohr" else b
    return a * b - (a - 2 * s) * (b - 2 * s)


def manuell(teile, end, nutzbar_bis, kerf, abstand):
    """Einfache manuelle Einteilung, wie man sie von Hand macht: Teile in Eingabereihenfolge, nicht gedreht,
    Stange voll, dann die nächste. Ergebnis: Anzahl Stangen."""
    n, pos, vorher = 0, None, None
    for laenge, a_ger, b_ger in teile:
        if pos is not None:
            weiter = pos + (kerf if (vorher and a_ger) else 2 * kerf + abstand) + laenge
            if weiter + kerf <= nutzbar_bis + TOL:
                pos, vorher = weiter, b_ger
                continue
        n += 1
        pos, vorher = end + laenge, b_ger
    return n


def programm_rechnen(m, tmp):
    """Weg des Programms: Datenbank, Auftrag, Optimierung, gespeichertes Ergebnis."""
    db = Datenbank(tmp / "rohrlaser.db")
    daten, einst, hinweise = lies_mappe(m)
    assert not hinweise, hinweise
    db.stammdaten_ersetzen(daten, einst, "Abnahme")
    kopf, positionen, hinweise = lies_auftrag(m)
    assert not hinweise, hinweise
    aid = db.auftrag_neu({f.name: kopf[f.name] for f in KOPF if kopf.get(f.name) is not None})
    for p in positionen:
        db.position_neu(aid, p)
    kopf, positionen = db.auftrag(aid), db.positionen(aid)
    erg = rechnen.optimieren(kopf, positionen, db.kontext())
    if erg["neue_profile"]:
        db.profile_anlegen(erg["neue_profile"])
    db.ergebnis_speichern(aid, erg)
    gespeichert = db.auftrag(aid)["ergebnis"]
    assert gespeichert["stangen"] == erg["stangen"], "Ergebnis nach dem Speichern verändert"
    k, tabellen = db.kontext(), db.tabellen()
    zeilen, summen = rechnen.kalkulation(kopf, positionen, gespeichert, k, tabellen, db.einstellungen())
    sw = rechnen.stangen_werte(gespeichert, kopf, positionen, k, tabellen)
    stamm = dict(profile={z["profil_id"]: z for z in db.zeilen("profile")},
                 werkstoffe={z["werkstoff_id"]: z for z in db.zeilen("werkstoffe")},
                 maschinen={z["maschinen_id"]: z for z in db.zeilen("maschinen")})
    db.schliessen()
    return kopf, positionen, gespeichert, sw, zeilen, summen, stamm


def pruefen(auftrag, kopf, positionen, erg, sw, zeilen, summen, stamm):
    """Abnahmekriterien 1–4 unabhängig nachrechnen. Ergebnis: Kennzahlen für das Protokoll."""
    name = auftrag["name"]
    m = stamm["maschinen"][kopf["maschine"]]
    kerf, abstand = m["schnittverlust"], m["abstand"] or 0
    stange_von = lambda p: p.get("stange") or kopf["stange"]
    gruppe_von = lambda p: (p["profil_id"], p["werkstoff_id"], stange_von(p))

    # 1. Teile korrekt eingeplant
    gezaehlt = {}
    for s in erg["stangen"]:
        for t in s["teile"]:
            p = positionen[t["index"]]
            assert gruppe_von(p) == (s["profil"], s["werkstoff"], s["stange"]), \
                f"{name}: Pos. {p['pos']} auf Stange {s['nr']} vermischt"
            assert t["laenge"] == p["laenge"], f"{name}: Pos. {p['pos']} falsche Länge"
            gezaehlt[t["index"]] = gezaehlt.get(t["index"], 0) + 1
    fehler = {f["index"]: f for f in erg["fehler"]}
    for i, (p, soll) in enumerate(zip(positionen, auftrag["positionen"])):
        if soll.get("erwartet") == "nicht eingeplant":
            assert i not in gezaehlt and fehler.get(i, {}).get("anzahl") == p["stueck"], \
                f"{name}: Pos. {p['pos']} hätte nicht eingeplant werden dürfen"
        else:
            assert gezaehlt.get(i, 0) == p["stueck"] and i not in fehler, \
                f"{name}: Pos. {p['pos']} {gezaehlt.get(i, 0)} von {p['stueck']} eingeplant"
            assert zeilen[i]["nicht_eingeplant"] == 0 and zeilen[i]["hinweis"] != "nicht vollständig eingeplant"

    # 2. Keine Stange überlastet, 3. Material und Rest
    gruppen = {}
    for s, x in zip(erg["stangen"], sw):
        pr = stamm["profile"][s["profil"]]
        end = pr["endbeschnitt"] if pr.get("endbeschnitt") is not None else m["endbeschnitt"]
        greif = pr["greiferrest"] if pr.get("greiferrest") is not None else m["greiferrest"]
        assert (s["end"], s["greif"]) == (end, greif), f"{name}: Stange {s['nr']} Endbeschnitt/Greiferrest"
        assert s["stange"] <= m["max_stange"], f"{name}: Stange {s['nr']} länger als die Maschine zulässt"
        pos, vorher, verlust = end, None, 0.0
        for t in s["teile"]:
            p = positionen[t["index"]]
            a_ger, b_ger = p.get("a_gerade") != "nein", p.get("b_gerade") != "nein"
            if t["lage"] == "gedreht":
                a_ger, b_ger = b_ger, a_ger
            if vorher is None:
                luecke, art = 0.0, "Stangenanfang"
            elif vorher and a_ger:
                luecke, art = kerf, "gemeinsamer Schnitt"
            else:
                luecke, art = 2 * kerf + abstand, "2 Schnitte"
            assert t["trennung"] == art, f"{name}: Stange {s['nr']} Trennung {t['trennung']}, richtig {art}"
            assert nahe(t["von"], pos + luecke, 1e-9) and nahe(t["bis"] - t["von"], t["laenge"], 1e-9), \
                f"{name}: Stange {s['nr']} Pos. {p['pos']} liegt bei {t['von']}–{t['bis']}, richtig ab {pos + luecke}"
            pos, vorher, verlust = t["bis"], b_ger, verlust + luecke
        verlust += kerf                    # letzter Schnitt
        frei = s["stange"] - greif - (pos + kerf)
        assert frei >= -TOL, f"{name}: Stange {s['nr']} um {-frei:.2f} mm überlastet"
        summe = sum(t["laenge"] for t in s["teile"])
        assert nahe(s["verlust"], verlust), f"{name}: Stange {s['nr']} Schnittverlust {s['verlust']}, richtig {verlust}"
        assert nahe(x["summe"], summe) and nahe(x["belegt"], end + summe + verlust)
        assert nahe(x["rest"], s["stange"] - end - summe - verlust) and x["rest"] >= greif - TOL
        assert x["pruefung"] == "OK"
        kg = s["stange"] / 1000 * flaeche(pr) * stamm["werkstoffe"][s["werkstoff"]]["dichte"] / 1000
        assert nahe(x["gewicht"], kg), f"{name}: Stange {s['nr']} Gewicht {x['gewicht']}, richtig {kg}"
        assert x["kosten"] > 0, f"{name}: Stange {s['nr']} ohne Materialkosten"
        g = gruppen.setdefault((s["profil"], s["werkstoff"], s["stange"]),
                               dict(end=end, greif=greif, stangen=0, laenge=0.0, teile=0.0, kosten=[]))
        g["stangen"] += 1
        g["laenge"] += s["stange"]
        g["teile"] += summe
        g["kosten"].append(x["kosten"])
    for g in gruppen.values():   # Stangen einer Gruppe kosten gleich viel
        assert all(nahe(c, g["kosten"][0]) for c in g["kosten"])
    assert nahe(summen["material"], sum(x["kosten"] for x in sw)), \
        f"{name}: Materialkosten Auftrag {summen['material']} ≠ Summe der Stangen {sum(x['kosten'] for x in sw)}"
    for z in zeilen:
        if z and z["stueck"]:
            assert nahe(z["material_teil"] * z["stueck"], z["material_position"])
    # Einzelne Kostenarten ergeben Herstellkosten und Verkaufspreis
    herstell = sum(summen[n] for n in ("material", "laser_schneiden", "gewinde", "ruesten_maschine",
                                       "ruesten_abmessungen", "stangenwechsel_kosten", "zusatz", "zuschlag_material",
                                       "zuschlag_fertigung", "zuschlag_fremdleistung"))
    assert nahe(herstell, summen["herstell"]), f"{name}: Kostenarten {herstell} ≠ Herstellkosten {summen['herstell']}"
    verkauf = summen["herstell"] + sum(summen[n] for n in ("gewinn", "pauschalen", "programmierung",
                                                          "auftragsaufschlag", "fracht"))
    assert nahe(verkauf, summen["verkauf"]), f"{name}: Kostenarten {verkauf} ≠ Verkaufspreis {summen['verkauf']}"
    assert nahe(summen["laser_schneiden"] + summen["gewinde"], summen["laser"])
    assert nahe(summen["ruesten_maschine"] + summen["ruesten_abmessungen"] + summen["stangenwechsel_kosten"],
                summen["ruesten"])

    # 4. Gegen manuelle Einteilung und Untergrenze
    zeilen_protokoll = []
    for key, g in gruppen.items():
        teile = [(p["laenge"], p.get("a_gerade") != "nein", p.get("b_gerade") != "nein")
                 for i, p in enumerate(positionen) if i in gezaehlt and gruppe_von(p) == key
                 for _ in range(int(p["stueck"]))]
        nutzbar_bis = key[2] - g["greif"]
        n_man = manuell(teile, g["end"], nutzbar_bis, kerf, abstand)
        ug = math.ceil(sum(L + kerf for L, _, _ in teile) / (nutzbar_bis - g["end"]) - TOL)
        assert ug <= g["stangen"] <= n_man, \
            f"{name} {key}: {g['stangen']} Stangen, manuell {n_man}, Untergrenze {ug}"
        a = next(a for a in erg["auswertung"] if (a["profil"], a["werkstoff"], a["stange"]) == key)
        assert (a["stangen"], a["manuell"], a["untergrenze"]) == (g["stangen"], n_man, ug), \
            f"{name} {key}: Auswertung {a}"
        zeilen_protokoll.append(dict(gruppe=key, teile=len(teile), stangen=g["stangen"], manuell=n_man,
                                     untergrenze=ug, laenge=g["laenge"], teilelaenge=g["teile"],
                                     kosten=sum(g["kosten"]), kosten_manuell=n_man * g["kosten"][0],
                                     bewertung=a["bewertung"]))
    return dict(name=auftrag["name"], nummer=auftrag["nummer"], gruppen=zeilen_protokoll,
                positionen=len(positionen), eingeplant=sum(gezaehlt.values()),
                nicht_eingeplant=sum(f["anzahl"] for f in erg["fehler"]),
                gruende=sorted({f["grund"] for f in erg["fehler"]}), verkauf=summen["verkauf"])


def gleiche_einteilung(erg, m):
    """Programm über die Datenbank = Programm direkt aus der Mappe gelesen (gleiche Stangen)."""
    from rohrlaser.stammdaten import kontext_aus
    daten, _, _ = lies_mappe(m)
    kopf, positionen, _ = lies_auftrag(m)
    direkt = rechnen.optimieren(kopf, positionen, kontext_aus(daten))
    form = lambda e: [(s["profil"], s["werkstoff"], s["stange"], s["belegung"], s["verlust"]) for s in e["stangen"]]
    assert form(erg) == form(direkt), "Datenbank und Mappe ergeben verschiedene Einteilungen"


def zahl(v, stellen=0):
    return f"{v:,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def protokoll(ergebnisse, mappe_geprueft):
    z = ["# Abnahmeprotokoll Rohrlaser-Kalkulation (Programm)", "",
         "Erzeugt von `tests/test_abnahme.py` mit den Testaufträgen aus `tests/abnahme_auftraege.py` "
         "und den Beispiel-Stammdaten der Mappe v02.", "",
         "| Kriterium | Ergebnis |", "|---|---|",
         "| Teile korrekt eingeplant (volle Stückzahl, nichts doppelt, keine Vermischung) | erfüllt |",
         "| Keine Stange überlastet (Lage jedes Teils nachgerechnet) | erfüllt |",
         "| Materialbedarf, Restlängen, Gewicht und Materialkosten stimmen | erfüllt |",
         "| Besser als einfache manuelle Einteilung, nie unter der Untergrenze | erfüllt |",
         "| Programm rechnet wie die Mappe (Zelle für Zelle) | "
         + ("erfüllt |" if mappe_geprueft else "nicht geprüft (ohne LibreOffice) |"), "",
         "| Auftrag | Profil / Werkstoff / Stange | Teile | Stangen | manuell | Untergrenze | Ausnutzung "
         "| Ausnutzung manuell | Material € | Material € manuell | Bewertung |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    ges = dict(stangen=0, manuell=0, kosten=0.0, kosten_manuell=0.0, laenge=0.0, teile=0.0, laenge_manuell=0.0)
    for e in ergebnisse:
        for g in e["gruppen"]:
            stange = g["gruppe"][2]
            z.append(f"| {e['nummer']} {e['name']} | {g['gruppe'][0]} / {g['gruppe'][1]} / {zahl(stange)} "
                     f"| {g['teile']} | {g['stangen']} | {g['manuell']} | {g['untergrenze']} "
                     f"| {zahl(100 * g['teilelaenge'] / g['laenge'], 1)} % "
                     f"| {zahl(100 * g['teilelaenge'] / (g['manuell'] * stange), 1)} % "
                     f"| {zahl(g['kosten'], 2)} | {zahl(g['kosten_manuell'], 2)} | {g['bewertung']} |")
            ges["stangen"] += g["stangen"]
            ges["manuell"] += g["manuell"]
            ges["kosten"] += g["kosten"]
            ges["kosten_manuell"] += g["kosten_manuell"]
            ges["laenge"] += g["laenge"]
            ges["laenge_manuell"] += g["manuell"] * stange
            ges["teile"] += g["teilelaenge"]
    z += ["", f"**Summe:** {ges['stangen']} Stangen statt {ges['manuell']} bei manueller Einteilung "
          f"({ges['manuell'] - ges['stangen']} Stangen weniger), Ausnutzung {zahl(100 * ges['teile'] / ges['laenge'], 1)} % "
          f"statt {zahl(100 * ges['teile'] / ges['laenge_manuell'], 1)} %, Materialkosten {zahl(ges['kosten'], 2)} € "
          f"statt {zahl(ges['kosten_manuell'], 2)} € ({zahl(ges['kosten_manuell'] - ges['kosten'], 2)} € gespart).", "",
          "## Nicht eingeplante Teile", ""]
    for e in ergebnisse:
        if e["nicht_eingeplant"]:
            z.append(f"- {e['nummer']} {e['name']}: {e['nicht_eingeplant']} Teile ({', '.join(e['gruende'])}), "
                     "wie erwartet.")
    z += ["", "Manuelle Einteilung: Teile in Eingabereihenfolge, nicht gedreht, Stange voll, dann die nächste. "
          "Untergrenze: Summe aus Teilelänge und Schnittverlust geteilt durch die Nutzlänge, aufgerundet."]
    return "\n".join(z) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protokoll")
    ap.add_argument("--ohne-mappe", action="store_true")
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp())
    lo = None
    if not args.ohne_mappe:
        from lo_makro import LibreOffice
        from test_programm_mappe import mappe_rechnen, vergleichen
        lo = LibreOffice(port=2018).__enter__()
    ergebnisse = []
    try:
        for auftrag in AUFTRAEGE:
            d = tmp / auftrag["nummer"]
            d.mkdir()
            m = d / "eingabe.xlsm"
            shutil.copy(MAPPE, m)
            wb = load_workbook(m, keep_vba=True)
            mappe_fuellen(wb, auftrag)
            wb.save(m)
            kopf, positionen, erg, sw, zeilen, summen, stamm = programm_rechnen(m, d)
            gleiche_einteilung(erg, m)
            e = pruefen(auftrag, kopf, positionen, erg, sw, zeilen, summen, stamm)
            if lo:
                rechnung = d / "rechnung.xlsm"
                shutil.copy(m, rechnung)
                mappe_rechnen(rechnung, d / "werte.xlsx", lo)
                vergleichen(auftrag["name"], m, d / "werte.xlsx")
            ergebnisse.append(e)
            s = sum(g["stangen"] for g in e["gruppen"])
            mn = sum(g["manuell"] for g in e["gruppen"])
            print(f"{auftrag['nummer']} {auftrag['name']}: {e['eingeplant']} Teile auf {s} Stangen "
                  f"(manuell {mn}), {e['nicht_eingeplant']} nicht eingeplant"
                  + (", gleich wie Mappe" if lo else ""))
    finally:
        if lo:
            lo.__exit__(None, None, None)
        shutil.rmtree(tmp, ignore_errors=True)
    s = sum(g["stangen"] for e in ergebnisse for g in e["gruppen"])
    mn = sum(g["manuell"] for e in ergebnisse for g in e["gruppen"])
    assert s < mn, f"Optimierung insgesamt nicht besser als manuell: {s} gegen {mn} Stangen"
    text = protokoll(ergebnisse, lo is not None)
    if args.protokoll:
        Path(args.protokoll).write_text(text, encoding="utf-8")
    print(f"OK: Abnahme bestanden, {s} Stangen statt {mn} bei manueller Einteilung")


if __name__ == "__main__":
    main()
