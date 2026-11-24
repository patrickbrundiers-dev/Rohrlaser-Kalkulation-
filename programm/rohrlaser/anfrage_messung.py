"""Messwerte der Anfrage-Erkennung (Patrick 20.11.2026, Plan K11, „Alles einbauen“).

korpus_messen()        Mail-Art an festen Beispielen (die Fälle aus dem Auftrag und Gegenbeispiele, alle erfunden):
                       Trefferquote, Verwechslungen, Anteil „unklar“, Zeit je Mail
akten_messen(abl, db)  im echten Akten-Ordner: Anfragen je Mail-Art/Sicherheit/Phase, Korrekturanteil je Feld,
                       Kunde automatisch erkannt, Ø bis Übernahme, wartende Mails, letzter Abruf, gelerntes Modell
verlauf(akten, wurzel)  je Kalenderwoche (23.11.2026, Stufe 2 Punkt 4): Eingänge, Mail-Art unklar, von Hand
                       korrigiert, Kunde sicher erkannt, Ø bis Übernahme, Rückfragen, nachgefasst
bericht(werte)         lesbarer Text
Aufruf: python werkzeuge/anfrage_messung.py [AKTEN-ORDNER] [--json]. Ohne Qt."""
import time

from . import anfrage_art as aa
from . import anfrage_lernen as al
from . import anfrage_phase as ph
from . import anfragen_akten as ak

STEP, PDF = ["teil.step"], ["zeichnung.pdf"]
# (Betreff, Text, Dateien, erwartete Art, ist Antwort, hat Angebot)
KORPUS = [
    ("Preisanfrage", "Können Sie uns hierfür einen Preis nennen?", STEP, aa.ANFRAGE, False, False),
    ("Zeichnungen", "Bitte kalkulieren Sie die beigefügten Zeichnungen.", PDF, aa.ANFRAGE, False, False),
    ("Anfrage", "Wir benötigen ein Angebot für 250 Stück.", STEP, aa.ANFRAGE, False, False),
    ("Rohrkonstruktion", "Was würde die Fertigung dieser Rohrkonstruktion kosten?", STEP, aa.ANFRAGE, False, False),
    ("STEP-Dateien", "Bitte prüfen Sie die angehängten STEP-Dateien.", STEP + ["b.step"], aa.ANFRAGE, False, False),
    ("Anfrage ohne Anhang", "Bitte bieten Sie uns 40 Stück Rohr 40x40x3, Länge 500 mm an.", [], aa.ANFRAGE, False,
     False),
    ("AW: Angebot 2026-00122", "Wie ist der Stand zu unserem Angebot? Wir warten auf Ihr Angebot.", [],
     aa.NACHFRAGE, True, True),
    ("AW: Angebot 2026-00122", "Bitte ändern Sie das Angebot auf 500 Stück statt 250.", [], aa.AENDERUNG,
     True, True),
    ("Bestellung 4500012345", "Hiermit bestellen wir gemäß Ihrem Angebot 2026-00122.", ["bestellung.pdf"],
     aa.BESTELLUNG, False, True),
    ("Reklamation Lieferung", "Die gelieferten Teile sind fehlerhaft, die Bohrungen sitzen falsch. Wir reklamieren.",
     ["foto.jpg"], aa.REKLAMATION, False, False),
    ("Liefertermin", "Wann können Sie liefern? Bitte nennen Sie uns den Liefertermin für Bestellung 4500012345.", [],
     aa.LIEFERTERMIN, False, False),
    ("Frage zur Zeichnung", "Technische Rückfrage: welche Toleranz gilt für die Bohrung auf Blatt 2?", [],
     aa.TECHNIK, True, False),
    ("Newsletter November", "Jetzt 20 % Rabatt auf alle Schweißgeräte! Abmelden: hier klicken.", [], aa.WERBUNG,
     False, False),
    ("Material", "Wir benötigen nur das Material: 10 Stangen à 6000 mm Rundrohr 30x2, ohne Bearbeitung.", [],
     aa.MATERIAL, False, False),
    ("Kurze Info", "Vielen Dank, wir melden uns nächste Woche.", [], aa.ALLGEMEIN, True, False),
]


def korpus_messen(korpus=None):
    """Mail-Art an den Beispielen: dict(n, richtig, quote, unklar, verwechselt=[(Text, Erwartet, Erkannt)], ms)."""
    korpus = KORPUS if korpus is None else korpus
    richtig = unklar = 0
    falsch = []
    t0 = time.perf_counter()
    for betreff, text, dateien, soll, antwort, angebot in korpus:
        e = aa.einordnen(text, betreff, dateien, hat_angebot=angebot, ist_antwort=antwort)
        unklar += e["sicherheit"] == aa.UNKLAR
        if e["art"] == soll:
            richtig += 1
        else:
            falsch.append((text[:60], soll, e["art"]))
    ms = (time.perf_counter() - t0) * 1000 / max(len(korpus), 1)
    n = len(korpus)
    return dict(n=n, richtig=richtig, quote=round(100 * richtig / n) if n else None, unklar=unklar,
                verwechselt=falsch, ms=round(ms, 2))


def akten_messen(abl, db=None):
    """Kennzahlen aus dem Akten-Ordner (nur lesen)."""
    from . import outlook_anfragen as ol
    akten = abl.alle()
    arten, phasen, uebernahme = {}, {}, []
    for a in akten:
        ein = a.einordnung or {}
        k = ein.get("art") or "?"
        arten[k] = arten.get(k, 0) + 1
        p = ph.phase(a, ph.angebots_phase(db, a.stand.get("angebote")) if db is not None else "")
        phasen[p] = phasen.get(p, 0) + 1
        von, bis = ak._datum(a.eingang or ""), ak._datum(a.stand.get("uebernommen_am") or "")
        if von and bis:
            uebernahme.append((bis - von).total_seconds() / 3600)
    aus = al.auswertung(abl.wurzel, akten)
    return dict(akten=len(akten), arten=arten, phasen=phasen, sicherheit=aus["sicherheit"], kunde=aus["kunde"],
                felder=aus["felder"], std_bis_uebernahme=round(sum(uebernahme) / len(uebernahme), 1) if uebernahme
                else None, wartet=len(ol.fehler_lesen(abl)), abruf=ol.abruf_status(abl),
                modell=dict(schatten=(al.modell_lesen(abl.wurzel) or {}).get("pruefung"),
                            aktiv=(al.aktiv_lesen(abl.wurzel) or {}).get("version")))


def _woche(d):
    j, w, _ = d.isocalendar()
    return f"{j}-W{w:02d}"


def _anteil(n, von):
    return round(100 * n / von) if von else None


def verlauf(akten, wurzel=None, wochen=12, jetzt=None):
    """[dict(woche, eingaenge, unklar, korrigiert, kunde_sicher (Prozent oder None), std_bis_uebernahme, rueckfragen,
    nachgefasst)] der letzten wochen Kalenderwochen, älteste zuerst; nach dem Eingang der Anfrage. korrigiert: Anteil
    der Anfragen, bei denen jemand Mail-Art oder Kunde von Hand geändert hat (Rückmeldung mit richtig=False). Nur
    lesen, nichts wird gespeichert."""
    import datetime
    jetzt = jetzt or datetime.datetime.now()
    reihe = [_woche(jetzt - datetime.timedelta(weeks=i)) for i in range(wochen - 1, -1, -1)]
    je = {w: dict(woche=w, eingaenge=0, _unklar=0, _ein=0, _korr=0, _sicher=0, _std=[], rueckfragen=0,
                  nachgefasst=0) for w in reihe}
    falsch = set()
    if wurzel:
        for e in al.rueckmeldungen(wurzel):
            if e.get("feld") in ("art", "kunde") and not e.get("richtig") and e.get("nr"):
                falsch.add(e["nr"])
    for a in akten:
        if not a.eingang or a.stand.get("zusammengefuehrt_in"):
            continue
        x = je.get(_woche(a.eingang))
        if x is None:
            continue
        x["eingaenge"] += 1
        ein = a.kopf.get("einordnung") or {}
        if ein:
            x["_ein"] += 1
            x["_unklar"] += ein.get("sicherheit") == aa.UNKLAR
        x["_korr"] += a.nr in falsch or bool(a.stand.get("art_korr"))
        x["_sicher"] += (a.kopf.get("zuordnung") or {}).get("stufe") == "eindeutig" and a.nr not in falsch
        bis = ak._datum(a.stand.get("uebernommen_am") or "")
        if bis:
            x["_std"].append((bis - a.eingang).total_seconds() / 3600)
        rf = [e for e in a.verlauf if e.get("aktion") == ak.RUECKFRAGE]
        x["rueckfragen"] += sum(1 for e in rf if not e.get("nachfassen"))
        x["nachgefasst"] += sum(1 for e in rf if e.get("nachfassen"))
    out = []
    for w in reihe:
        x = je[w]
        n = x["eingaenge"]
        out.append(dict(woche=w, eingaenge=n, unklar=_anteil(x["_unklar"], x["_ein"]), korrigiert=_anteil(
            x["_korr"], n), kunde_sicher=_anteil(x["_sicher"], n), std_bis_uebernahme=round(
            sum(x["_std"]) / len(x["_std"]), 1) if x["_std"] else None, rueckfragen=x["rueckfragen"],
            nachgefasst=x["nachgefasst"]))
    return out


def bericht(k=None, a=None):
    z = []
    if k:
        z.append(f"Mail-Art an {k['n']} Beispielen: {k['richtig']} richtig ({k['quote']} %), {k['unklar']} unklar, "
                 f"{k['ms']} ms je Mail")
        z += [f"  falsch: „{t}“ erwartet {s}, erkannt {e}" for t, s, e in k["verwechselt"]]
    if a:
        z.append(f"Akten: {a['akten']}")
        z.append("  Mail-Art: " + ", ".join(f"{aa.ARTEN.get(x, x)} {n}" for x, n in sorted(a["arten"].items())))
        z.append("  Sicherheit: " + ", ".join(f"{x} {n}" for x, n in sorted(a["sicherheit"].items())))
        z.append("  Phase: " + ", ".join(f"{ph.text(x)} {n}" for x, n in sorted(a["phasen"].items(),
                                                                                  key=lambda x: ph.rang(x[0]))))
        z.append("  Kunde: " + ", ".join(f"{x} {n}" for x, n in sorted(a["kunde"].items())))
        for f, w in a["felder"].items():
            z.append(f"  Korrekturen {al.FELDER.get(f, f)}: {w['anzahl']}, davon bestätigt {w['richtig']} "
                     f"({w['quote']} %)" + (" · häufig: " + "; ".join(f"{x} ({n}×)" for x, n in w["verwechselt"])
                                            if w["verwechselt"] else ""))
        if a["std_bis_uebernahme"] is not None:
            z.append(f"  Ø bis Übernahme: {a['std_bis_uebernahme']} h")
        z.append(f"  Mails warten auf erneuten Versuch: {a['wartet']}")
        if a["abruf"]:
            from . import outlook_anfragen as ol
            z.append("  " + ol.status_text(a["abruf"]))
        m = a["modell"]
        z.append("  Gelerntes Modell: " + (f"Schatten {m['schatten']}" if m["schatten"] else "noch keins")
                 + (f", freigegeben Version {m['aktiv']}" if m["aktiv"] else ", nicht freigegeben"))
    return "\n".join(z)
