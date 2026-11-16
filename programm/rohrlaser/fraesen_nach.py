"""Fräsen nach der Bearbeitung (Patrick 03.11.2026, Schritt 4 zum Richtpreis Dreh-/Frästeile): ein Rohrlaserteil,
Blech oder eine geschweißte Baugruppe wird danach noch gefräst (Flansch planfräsen, Bohrungen, Gewinde, Passungen,
Nut/Tasche). Das STEP zeigt nur das fertige Teil, deshalb gibt man die Bearbeitungen ein; die Zeiten rechnen mit
denselben Schnittwerten, Stundensätzen und Rüstzeiten wie der Richtpreis der Dreh-/Frästeile (drehfraes_preis).

Ergebnis ist eine Zusatzarbeit „Fräsen nach Bearbeitung“ in €/Stück an der Position (Preisstand mit den Eingaben):
- eigene Fräsmaschine (Fremdleistung nein): Zeit × Stundensatz Fräsen + Rüsten/Stückzahl, Gewinn wie bei jeder
  Zusatzarbeit im Angebot;
- Lohnfertiger (Fremdleistung ja): dazu der Aufschlag des Lieferanten, im Angebot als Fremdleistung.
Gewinde werden als Zeit gerechnet (Gewindebohren/-fräsen je Gewinde); wer feste €/Gewinde hat, trägt sie unter
Zusätze €/Stück ein.
"""
import datetime
import math

from . import drehfraes_preis as dp

NAME = "Fräsen nach Bearbeitung"
QUELLE = "Fräsen nach Bearbeitung"
PLAN, BOHRUNG, GEWINDE, REIBEN, SENKUNG, TASCHE = ("Planfläche", "Bohrung", "Gewindebohrung", "Passbohrung (Reiben)",
                                                    "Senkung/Fase", "Tasche/Nut")
ARTEN = (PLAN, BOHRUNG, GEWINDE, REIBEN, SENKUNG, TASCHE)
# je Art: welche Maße gelten (für Dialog und Prüfung)
MASSE = {PLAN: ("l", "b", "t"), BOHRUNG: ("d", "t"), GEWINDE: ("d", "t"), REIBEN: ("d", "t"), SENKUNG: ("d",),
         TASCHE: ("l", "b", "t")}
MASS_TITEL = {"l": "Länge", "b": "Breite", "t": "Tiefe/Aufmaß", "d": "Ø"}
KRAN_KG, SCHWER_KG = 25.0, 100.0


def _z(x, vorgabe=0.0):
    return dp._z(x, vorgabe)


def _f(x):
    return dp._fmm(x)


def rechnen(e, einst=None):
    """e = dict(werkstoff, stueck, gewicht [kg/Stück], laenge/breite/hoehe [mm] (Größe des Teils, optional),
    bearbeitungen=[dict(art, anzahl, l, b, t, d)], aufspannungen, ausrichten (ja: Schweißteil ausrichten),
    fremd (ja/nein), zusatz_eur). Ergebnis: dict(arbeitsgaenge, minuten, maschine, ruesten, ruesten_auftrag,
    zusatz, aufschlag, preis, machbarkeit, ampel, hinweise, fehler, gruppe)."""
    w = dp.einstellungen(einst)
    erg = dict(arbeitsgaenge=[], minuten=0.0, maschine=0.0, ruesten=0.0, ruesten_auftrag=0.0, zusatz=0.0,
               aufschlag=0.0, preis=None, machbarkeit=[], ampel=dp.GRUEN, hinweise=[], fehler=[], gruppe=None,
               stueck=max(1.0, _z(e.get("stueck"), 1.0)))
    sw, zeile = dp.werkstoff_schnittwerte(e.get("werkstoff"), w)
    if sw is None:
        erg["fehler"].append("Schnittwerte fehlen")
        return erg
    erg["gruppe"] = sw["gruppe"]
    erg["werkstoff_tabelle"] = zeile.get("drehfraes_werkstoff_id") if zeile else None
    liste = [b for b in e.get("bearbeitungen") or () if b.get("art") in ARTEN and _z(b.get("anzahl"), 1) > 0]
    if not liste:
        erg["fehler"].append("keine Bearbeitung eingetragen")
        return erg
    fr = w["df_fraeser"]
    n = sw["fraes_vc"] * 1000 / (math.pi * fr)
    vf = sw["fraes_fz"] * 4 * n
    q = 0.4 * fr * fr * vf * w["df_nutzung"] / 1000                       # cm³/min Schruppen
    rate = sw["fraes_schlicht_fz"] * 4 * n * 1.2 * 0.6 * fr / 100           # cm²/min Schlichten
    d_plan = 3 * fr
    n_p = sw["fraes_vc"] * 1000 / (math.pi * d_plan)
    gaenge, werkzeuge = [], set()
    for b in liste:
        anz = _z(b.get("anzahl"), 1)
        art = b["art"]
        fehlt = [MASS_TITEL[m] for m in MASSE[art] if _z(b.get(m)) <= 0 and not (art == PLAN and m == "t")]
        if fehlt:
            erg["fehler"].append(f"{art}: {', '.join(fehlt)} fehlt")
            continue
        if art == PLAN:
            ll, bb, tt = _z(b["l"]), _z(b["b"]), _z(b.get("t")) or 1.0
            q_p = 0.7 * d_plan * min(3.0, tt) * sw["fraes_fz"] * 6 * n_p * w["df_nutzung"] / 1000
            bahnen = max(1, math.ceil(bb / (0.7 * d_plan)))
            t = (ll * bb * tt / 1000) / q_p + (ll * bb / 100) / (rate * 1.5) if q_p > 0 and rate > 0 else 0
            t = max(t, bahnen * (ll + d_plan) / max(vf, 1))                # Mindestens die Bahnen abfahren
            werkzeuge.add("Planfräser")
            text = f"{_f(ll)} × {_f(bb)} mm, {_f(tt)} mm Aufmaß, Planfräser Ø{_f(d_plan)}"
        elif art in (BOHRUNG, GEWINDE, REIBEN):
            dm, tt = _z(b["d"]), _z(b["t"])
            t = dp.bohrzeit(dm, tt, sw) + 0.15                              # + Zentrieren/Positionieren
            werkzeuge |= {f"Bohrer Ø{_f(dm)}", "Zentrierer"}
            text = f"Ø{_f(dm)} × {_f(tt)} mm"
            if art == GEWINDE:
                n_g = sw["bohr_vc"] * 0.25 * 1000 / (math.pi * dm)          # Gewindebohren ≈ ¼ der Bohr-vc
                steigung = max(0.5, dm * 0.15)
                t += 2 * tt / (n_g * steigung) + 0.1 if n_g > 0 else 0.3    # hin und zurück
                werkzeuge.add(f"Gewindebohrer {_f(dm)}")
                text += " (Kernloch Ø, Gewinde hin/zurück)"
            elif art == REIBEN:
                t += dp.bohrzeit(dm, tt, sw) * 1.5 + 0.1                     # Reiben: langsamer Vorschub
                werkzeuge.add(f"Reibahle {_f(dm)}")
                text += " (Reiben H7)"
        elif art == SENKUNG:
            t = 0.15
            werkzeuge.add("Senker")
            text = f"Ø{_f(_z(b['d']))}"
        else:                                                               # Tasche/Nut
            ll, bb, tt = _z(b["l"]), _z(b["b"]), _z(b["t"])
            flaeche = (ll * bb + 2 * (ll + bb) * tt) / 100
            t = (ll * bb * tt / 1000) / q + flaeche / rate if q > 0 and rate > 0 else 0
            werkzeuge |= {"Schruppfräser", "Schlichtfräser"}
            text = f"{_f(ll)} × {_f(bb)} × {_f(tt)} mm"
        gaenge.append(dict(name=f"{art} ({_f(anz)}×)" if anz != 1 else art, verfahren=dp.FRAESEN,
                           minuten=t * anz, info=text))
    if erg["fehler"]:
        return erg
    gew = _z(e.get("gewicht"))
    aufsp = max(1, int(_z(e.get("aufspannungen"), 1)))
    spann = w["df_aufspannen_fraesen"] + (8.0 if gew > SCHWER_KG else 3.0 if gew > KRAN_KG else 0.0)
    if str(e.get("ausrichten") or "ja").lower().startswith("j"):
        spann += 2.0                                                        # Schweißteil ausrichten/antasten
    gaenge.append(dict(name=f"Aufspannen ({aufsp}×)", verfahren=dp.FRAESEN, minuten=aufsp * spann,
                       info=f"{_f(spann)} min je Aufspannung" + (" (Kran)" if gew > KRAN_KG else "")
                       + (", ausrichten" if str(e.get("ausrichten") or "ja").lower().startswith("j") else "")))
    gaenge.append(dict(name=f"Werkzeugwechsel ({len(werkzeuge)}×)", verfahren=dp.FRAESEN,
                       minuten=len(werkzeuge) * w["df_werkzeugwechsel"], info=", ".join(sorted(werkzeuge))))
    gaenge.append(dict(name="Entgraten", verfahren=dp.FRAESEN, minuten=w["df_entgraten"], info=""))
    hand = e.get("zeiten") or {}
    satz = w["df_stundensatz_fraesen"]
    for g in gaenge:
        g["berechnet"] = g["minuten"]
        if g["name"] in hand and _z(hand[g["name"]], -1) >= 0:
            g["minuten"], g["hand"] = _z(hand[g["name"]]), True
        g["kosten"] = g["minuten"] / 60 * satz
    erg["arbeitsgaenge"] = gaenge
    erg["minuten"] = sum(g["minuten"] for g in gaenge)
    erg["maschine"] = sum(g["kosten"] for g in gaenge)
    ruest = w["df_ruesten_fraesen"] + w["df_ruesten_aufspannung"] * (aufsp - 1) + 15.0 + \
        w["df_programm_element"] * len(liste)
    erg["ruesten_min"] = ruest
    erg["ruesten_auftrag"] = ruest / 60 * satz
    erg["ruesten"] = erg["ruesten_auftrag"] / erg["stueck"]
    erg["zusatz"] = max(0.0, _z(e.get("zusatz_eur")))
    netto = erg["maschine"] + erg["ruesten"] + erg["zusatz"]
    erg["fremd"] = str(e.get("fremd") or "nein").lower().startswith("j")
    erg["aufschlag"] = netto * w["df_aufschlag"] if erg["fremd"] else 0.0
    erg["preis"] = round(netto + erg["aufschlag"], 2)
    # Machbarkeit: Größe gegen den Verfahrweg, tiefe Bohrungen
    mb = []
    masse = sorted((_z(e.get("laenge")), _z(e.get("breite")), _z(e.get("hoehe"))), reverse=True)
    grenze = sorted((w["df_fraes_x"], w["df_fraes_y"], w["df_fraes_z"]), reverse=True)
    if any(m > g for m, g in zip(masse, grenze)):
        mb.append(dict(stufe=dp.ROT, text="Teil größer als der Verfahrweg der Fräsmaschine ("
                       + " × ".join(_f(x) for x in grenze) + " mm): größere Maschine bzw. Lohnfertiger"))
    for b in liste:
        if b["art"] in (BOHRUNG, GEWINDE, REIBEN) and _z(b.get("d")) > 0:
            v = _z(b.get("t")) / _z(b["d"])
            if v > w["df_bohr_rot"]:
                mb.append(dict(stufe=dp.ROT, text=f"{b['art']} Ø{_f(_z(b['d']))} ist {_f(v)} × Ø tief (Tieflochbohren)"))
            elif v > w["df_bohr_gelb"]:
                mb.append(dict(stufe=dp.GELB, text=f"{b['art']} Ø{_f(_z(b['d']))} ist {_f(v)} × Ø tief (Entspanen)"))
    if gew > SCHWER_KG:
        mb.append(dict(stufe=dp.GELB, text=f"schwer ({_f(gew)} kg): Kran und Spannvorrichtung nötig"))
    erg["machbarkeit"], erg["ampel"] = mb, dp.ampel(mb)
    return erg


def kurztext(e, erg):
    """Text der Zusatzarbeit, z. B. 'Planfläche 200 × 100; 4× Gewindebohrung Ø6,8 (Lohnfertiger)'."""
    teile = []
    for b in e.get("bearbeitungen") or ():
        anz = _z(b.get("anzahl"), 1)
        masse = " × ".join(_f(_z(b.get(m))) for m in MASSE.get(b.get("art"), ()) if _z(b.get(m)) > 0)
        teile.append((f"{_f(anz)}× " if anz != 1 else "") + f"{b.get('art')} {masse}".strip())
    return "; ".join(teile) + (" (Lohnfertiger)" if erg.get("fremd") else "")


def eintrag(e, erg, datum=None):
    """Zusatzarbeit für die Position (rechnen.zusatz_liste): €/Stück mit Preisstand und den Eingaben."""
    stand = dict(art="€/Stück", preis=erg["preis"], mindest=None, fremd="ja" if erg.get("fremd") else "nein",
                 angebotstext=NAME, datum=datum or datetime.date.today().isoformat())
    return dict(name=NAME, menge=1, preis=erg["preis"], text=kurztext(e, erg), stand=stand, quelle=QUELLE,
                fraesen=dict(e))


def aus_position(p):
    """Gespeicherte Eingaben der Position (Zusatzarbeit „Fräsen nach Bearbeitung“) oder None."""
    from .rechnen import zusatz_liste
    z = next((x for x in zusatz_liste(p) if x.get("quelle") == QUELLE and isinstance(x.get("fraesen"), dict)), None)
    return dict(z["fraesen"]) if z else None
