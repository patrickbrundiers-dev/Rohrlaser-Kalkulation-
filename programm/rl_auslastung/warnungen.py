"""V3 (Plan 2.7): Warnungen der Rohrlaser Auslastung. Nur im Programm (Glocke oben, Zeile im Reiter Aufträge,
auf Wunsch ein Windows-Hinweis); keine Mail, keine Cloud.

Regeln (Grenzen in den Einstellungen):
- Liefertermin überschritten oder laut Plan nicht zu halten (Terminrisiko „nicht zu halten“),
- Material noch nicht da, aber der Auftrag soll in den nächsten warn_material_tage Arbeitstagen starten,
- eine Unterbrechung mit Grund dauert länger als warn_stopp_min Minuten (Maschine steht),
- Fremdarbeit ist weggegeben und hätte laut ihren Arbeitstagen schon zurück sein müssen,
- N1: ein Auftrag (Arbeitsgang) läuft schon länger als kalkuliert,
- V2: eine Wartung ist überfällig oder in den nächsten WARTUNG_TAGE Arbeitstagen fällig,
- V1/N6: in den nächsten BEDIENER_TAGE Arbeitstagen fehlen Bediener oder ein Einrichter an einer Maschine mit
  eingeplanter Arbeit,
- Plan 3.1: eine Maschine ist in einer der nächsten 4 Wochen über 100 % ausgelastet oder ab 95 %, während eine
  Ausweichmaschine unter 60 % liegt, mit ausgerechneter Empfehlung."""

import datetime

from rohrlaser import einlastung

from . import daten as D
from . import laufzeit, rechnung

ROT, ORANGE = "rot", "orange"
WARTUNG_TAGE, BEDIENER_TAGE = 3, 5


def _tag(d):
    return d.strftime("%d.%m.%Y") if d else ""


def _datum(text):
    try:
        return datetime.date.fromisoformat(str(text or "")[:10])
    except ValueError:
        return None


def liste(db, aus, ein, heute, jetzt=None):
    """[dict(art, schluessel, text, auftrag_id, stufe)] – dringendste (rot) zuerst. schluessel bleibt für dieselbe
    Warnung gleich (für „neu seit dem letzten Mal“)."""
    if not db.funktion("warnungen"):
        return []
    jetzt = jetzt or datetime.datetime.combine(heute, rechnung.UHRZEIT or datetime.datetime.now().time())
    plan = (ein or {}).get("plan") or {}
    stopp_min = max(1, int(db.zahl("warn_stopp_min", 30)))
    material_tage = max(0, int(db.zahl("warn_material_tage", 2)))
    out = []
    for a in db.auftraege((D.OFFEN, D.LAEUFT)):
        p = plan.get(a["id"]) or {}
        name = a["nummer"] + (f" ({a['kunde']})" if a["kunde"] else "")
        termin = _datum(a["liefertermin"])
        if termin and termin < heute:
            out.append(dict(art="termin", schluessel=f"termin:{a['id']}", auftrag_id=a["id"], stufe=ROT,
                            text=f"{name}: Liefertermin {_tag(termin)} ist überschritten"))
        elif termin and p.get("risiko") == einlastung.UEBER:
            out.append(dict(art="termin", schluessel=f"termin:{a['id']}", auftrag_id=a["id"], stufe=ROT,
                            text=f"{name}: wird laut Plan zu spät fertig (lieferbar "
                                 f"{_tag(p.get('lieferbar')) or 'später'}, Termin {_tag(termin)})"))
        ab = db.wartet_auf_material(a, heute)
        start = p.get("start")
        if ab and start and einlastung._arbeitstage(aus, D.FREMD, heute, start) <= material_tage:
            out.append(dict(art="material", schluessel=f"material:{a['id']}:{ab}", auftrag_id=a["id"], stufe=ORANGE,
                            text=f"{name}: Material noch nicht da (kommt am {_tag(ab)}), Start geplant am "
                                 f"{_tag(start)}"))
        for t in ([g for g in a["gaenge"] if g["platz"] != D.FREMD and g["status"] != D.FERTIG] if a["gaenge"]
                  else [a]):
            lief, kalk = db.gelaufen(t, jetzt), int(t["kalk_min"] or 0)
            if kalk > 0 and lief > kalk:
                was = f" · {t['name']}" if t is not a else ""
                out.append(dict(art="laenger", schluessel=f"laenger:{a['id']}:{t.get('id') if t is not a else ''}",
                                auftrag_id=a["id"], stufe=ORANGE,
                                text=f"{name}{was}: läuft länger als kalkuliert ({laufzeit.text(lief)} von "
                                     f"{laufzeit.text(kalk)})"))
        for g in a["gaenge"]:
            if g["platz"] != D.FREMD or not g["start_am"] or g["status"] == D.FERTIG:
                continue
            weg = _datum(g["start_am"])
            if weg is None:
                continue
            zurueck = rechnung.fremd_tag(aus, einlastung._spaeter(aus, D.FREMD, weg, int(g["tage"] or 0)), False)
            if zurueck < heute:
                out.append(dict(art="fremd", schluessel=f"fremd:{g['id']}", auftrag_id=a["id"], stufe=ORANGE,
                                text=f"{name} · {g['name']}: seit {_tag(weg)} außer Haus, sollte am {_tag(zurueck)} "
                                     "zurück sein"))
    for (m, d), liste in sorted((aus or {}).get("wartung", {}).items(), key=lambda x: x[0][1]):
        for x in liste:
            if x["ueber"]:
                out.append(dict(art="wartung", schluessel=f"wartung:{x['id']}:{x['faellig']}", auftrag_id=None,
                                stufe=ROT, maschine=m,
                                text=f"{m}: Wartung „{x['name']}“ ist überfällig (fällig {_tag(x['faellig'])})"))
            elif einlastung._arbeitstage(aus, m, heute, d) <= WARTUNG_TAGE:
                out.append(dict(art="wartung", schluessel=f"wartung:{x['id']}:{d}", auftrag_id=None, stufe=ORANGE,
                                maschine=m, text=f"{m}: Wartung „{x['name']}“ am {_tag(d)} "
                                                 f"({laufzeit.text(int(x['h'] * 60 + 0.5))})"))
    bes = (aus or {}).get("besetzung")
    if bes is not None:
        mit_arbeit = {x["maschine"] for x in (ein or {}).get("auftraege") or ()}   # Maschinen mit offener Arbeit
        d, n = heute, 0
        while n < BEDIENER_TAGE and d < heute + datetime.timedelta(days=21):
            tag = bes.tag(aus, d)
            if tag:
                n += 1
            for m, x in sorted(tag.items()):
                if m not in mit_arbeit:
                    continue
                fehlt = f" (fehlt: {', '.join(x['fehlt'])})" if x["fehlt"] else ""
                if x["ist"] < x["soll"]:
                    text = (f"{m} am {_tag(d)}: kein Bediener da{fehlt}" if x["ist"] == 0 else
                            f"{m} am {_tag(d)}: nur {x['ist']} von {x['soll']} Schichten besetzt{fehlt}")
                    out.append(dict(art="bediener", schluessel=f"bediener:{m}:{d}:{x['ist']}", auftrag_id=None,
                                    stufe=ORANGE, maschine=m, text=text))
                elif x["einrichter_soll"] and not x["einrichter"]:   # der Einrichter dieser Maschine fehlt
                    out.append(dict(art="bediener", schluessel=f"einrichter:{m}:{d}", auftrag_id=None,
                                    stufe=ORANGE, maschine=m, text=f"{m} am {_tag(d)}: kein Einrichter da{fehlt}"))
            d += datetime.timedelta(days=1)
    if ein and aus and db.funktion("engpass"):           # Plan 3.1: Engpässe mit Empfehlung
        schwelle = int(db.zahl("schwelle_tage", 2))
        engpaesse = sorted(rechnung.engpaesse(db, aus, ein, heute), key=lambda e: (e["art"] != "ueber", e["montag"]))
        for n, e in enumerate(engpaesse):
            vorschlag = None
            if n < rechnung.SOFORT:              # Tempo: die ersten gleich ausrechnen, die übrigen beim Klick
                try:
                    vorschlag = rechnung.empfehlung(db, aus, ein, e, heute, schwelle)
                except Exception:                # eine Empfehlung darf die Warnungen nie aufhalten
                    vorschlag = None
                e["gerechnet"] = True
            out.append(dict(art="engpass", schluessel=f"engpass:{e['art']}:{e['maschine']}:{e['montag']}",
                            auftrag_id=None, stufe=ROT if e["art"] == "ueber" else ORANGE, maschine=e["maschine"],
                            engpass=e, vorschlag=vorschlag, text=rechnung.engpass_text(e, vorschlag)))
    for s in db.offene_stopps():
        try:
            seit = datetime.datetime.fromisoformat(s["wann"])
        except ValueError:
            continue
        minuten = int((jetzt - seit).total_seconds() // 60)
        if minuten < stopp_min:
            continue
        dauer = f"{minuten} min" if minuten < 120 else f"{minuten // 60} h {minuten % 60} min"
        out.append(dict(art="stopp", schluessel=f"stopp:{s['auftrag_id']}:{s['gang_id']}:{s['wann']}",
                        auftrag_id=s["auftrag_id"], stufe=ROT,
                        text=f"{s['maschine'] or 'Maschine'} steht seit {dauer} ({s['nummer']}, Grund: {s['grund']})"))
    return sorted(out, key=lambda w: (w["stufe"] != ROT, ("stopp", "termin", "engpass", "wartung", "laenger", "material", "fremd", "bediener").index(w["art"])))
