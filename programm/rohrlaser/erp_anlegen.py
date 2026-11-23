"""Profile und Werkstoffe aus dem ERP-Einkauf automatisch anlegen (Patrick 23.11.2026: „Profile über EK automatisch
anlegen mit Werkstoffe, Norm, Naht usw.“). Ohne Qt.

Aus jeder EK-Bezeichnung (mit Zusatztext und Hinweis aus der Artikelnummer, erp_preise.artikelnr_hinweis) liest
erp_preise die Abmessung, die Güte, die Norm-Familie und die Naht:
- EN 10219 kaltgefertigt = geschweißt; EN 10210 warmgefertigt bzw. „nahtlos“; EN 10305 Präzisionsrohr (E-Güten),
- „nahtlos“ / „geschweißt“ / SNB/SNS in Text oder Artikelnummer bestimmt die Rohrart.

plan() schlägt je ERP-Artikel vor, was fehlt, und nur, was sicher ist:
- Profil: Profilart und Maße erkannt, das Profil gibt es noch nicht (Profil-ID wie beim STEP-Import),
- Werkstoff: Güte erkannt (S235/S275/S355/S420/S460, E195/E235/E355) und Norm-Familie eindeutig, aber kein
  Werkstoff dieser Güte und Familie vorhanden. Er wird von einem vorhandenen Werkstoff derselben Güte kopiert
  (Kategorie, Werkstoff-Nr., Dichte, Tonnenpreis, Lasereigenschaften) und bekommt Norm, Rohrart und Angebotstext der
  Familie. Ohne Vorlage derselben Güte: keiner (lieber von Hand).
- Gefundener Werkstoff der falschen Familie (Text sagt nahtlos/EN 10210, gefunden ist EN 10219): richtiger
  Werkstoff wird angelegt bzw. genommen.
- Zuordnung des ERP-Artikels zu Profil + Werkstoff + Oberfläche wird gemerkt (erp_zuordnung), damit die Käufe
  in Historie, Vorschlägen und Angeboten zählen.
ausfuehren() legt nach einer Sicherung an, schreibt „aus ERP-EK angelegt“ in die Bemerkung und ins KI-Protokoll.
Was unsicher ist (Abmessung oder Güte nicht erkannt, mehrdeutig), bleibt in der Prüfliste des ERP-Imports.
"""
import datetime
import re

from . import erp_preise

FAMILIEN = {
    "10219": dict(norm="EN 10219 kaltgefertigt, geschweißt", rohrart="geschweißt", text="EN10219"),
    "10210": dict(norm="EN 10210 warmgefertigt", rohrart=None, text="EN10210",
                  laser_hinweis="warmgefertigt: Zunder auf der Oberfläche, Vorschub etwas geringer, Einstich unruhiger"),
    "10305": dict(norm="EN 10305-3 Präzisionsstahlrohr, geschweißt, maßgewalzt", rohrart="geschweißt",
                  text="EN10305-3"),
}
# Güte-Bezeichnung je Familie (Hohlprofile: H; Präzisionsrohr ohne Zusatz)
GUETE_NAME = {("235", "10219"): "S235JRH", ("275", "10219"): "S275J0H",
              ("275", "10210"): "S275J0H", ("355", "10219"): "S355J2H", ("355", "10210"): "S355J2H",
              ("420", "10219"): "S420MH", ("460", "10219"): "S460MH", ("420", "10210"): "S420NH",
              ("460", "10210"): "S460NH"}
_GUETE = re.compile(r"(?i)(?<![\w.])([SE])(195|235|275|355|420|460)(?:[A-Z0-9+]*)?(?![\d])")
_NORM = re.compile(r"(?<!\d)(10219|10210|10305)(?!\d)")
# Nur Hohlprofile haben Rohrnormen (EN 10219/10210/10305); Flachstahl, Winkel, Träger behalten die Erkennung des Imports
HOHLPROFILE = ("Rundrohr", "Quadratrohr", "Rechteckrohr", "Flachoval", "Halbflachoval", "Elliptisch")


def guete(text):
    """('S', '235') aus dem Text oder None (erste Güte; Doppelzeugnis S235/S275 = S235)."""
    m = _GUETE.search(str(text or ""))
    return (m.group(1).upper(), m.group(2)) if m else None


def familie(text, buchstabe="S"):
    """'10219', '10210', '10305' oder None: Norm im Text, sonst kalt/warm gefertigt, sonst Naht (geschweißt = 10219,
    nahtlos = 10210, erp_preise._familie). E-Güten sind Präzisionsrohr EN 10305."""
    if buchstabe == "E":
        return "10305"
    t = str(text or "")
    normen = set(_NORM.findall(t))
    if len(normen) == 1:
        return normen.pop()
    if re.search(r"(?i)kalt\s*gefertigt", t):
        return "10219"
    if re.search(r"(?i)warm\s*gefertigt", t):
        return "10210"
    f = erp_preise._familie(t)
    return f.pop() if len(f) == 1 else None


def naht(text):
    """'nahtlos', 'geschweißt' oder None aus Text/Artikelnummer-Hinweis."""
    t = str(text or "")
    if re.search(r"(?i)nahtlos", t):
        return "nahtlos"
    if erp_preise._GESCHWEISST.search(t):
        return "geschweißt"
    return None


def _norm_von(w):
    return next((n for n in FAMILIEN if n in " ".join(str(w.get(f) or "") for f in ("werkstoff_id", "norm",
                                                                                    "angebotstext"))), None)


def werkstoff_fuer(text, k):
    """(Werkstoff-ID vorhanden oder None, neuer Werkstoff dict oder None, Grund). Sucht einen Werkstoff mit Güte und
    Familie des Textes; fehlt er, wird er von einer Vorlage derselben Güte abgeleitet."""
    g = guete(text)
    if g is None:
        return None, None, "Güte nicht erkannt"
    fam = familie(text, g[0])
    if fam is None:
        return None, None, "Norm/Naht nicht eindeutig"
    from .datenbank import GIBT_ES_NICHT       # Patrick 20.11.2026: S235 EN 10210 gibt es nicht -> S235 EN 10219
    ersatz = GIBT_ES_NICHT.get(f"{g[0]}{g[1]}-{fam}")
    if ersatz:
        return (ersatz, None, "vorhanden") if ersatz in k.werkstoffe else (None, None, f"{ersatz} fehlt")
    gleich = [wid for wid, w in k.werkstoffe.items() if re.search(rf"(?i)(?<![\d]){g[0]}{g[1]}", str(wid) + " "
                                                                   + str(w.get("werkstoff") or ""))
              and not w.get("archiviert") == "ja"]
    passend = [wid for wid in gleich if _norm_von(k.werkstoffe[wid]) == fam]
    if passend:
        # Grundgüte vor Sondergüten (S355J2WH wetterfest nur, wenn es im Text steht)
        passend.sort(key=lambda w: (str(k.werkstoffe[w].get("werkstoff") or "").upper() not in str(text).upper(),
                                    len(str(w))))
        return passend[0], None, "vorhanden"
    vorlagen = [wid for wid in gleich if _norm_von(k.werkstoffe[wid]) in FAMILIEN]
    if not vorlagen:
        return None, None, f"kein Werkstoff {g[0]}{g[1]} als Vorlage"
    vorlage = sorted(vorlagen, key=len)[0]
    v = dict(k.werkstoffe[vorlage])
    f = FAMILIEN[fam]
    neu_id = f"{g[0]}{g[1]}-{fam}"
    if neu_id in k.werkstoffe:
        return neu_id, None, "vorhanden"
    heute = datetime.date.today().strftime("%d.%m.%Y")
    neu = {kk: vv for kk, vv in v.items() if kk not in ("id", "uid", "werkstoff_id", "archiviert")}
    neu.update(werkstoff_id=neu_id, werkstoff=GUETE_NAME.get((g[1], fam), v.get("werkstoff")),
               norm=f["norm"], angebotstext=f"{g[0]}{g[1]} {f['text']}",
               rohrart=f["rohrart"] or naht(text) or ("nahtlos" if fam == "10210" else "geschweißt"),
               bemerkung=f"aus ERP-EK angelegt {heute} (Vorlage {vorlage}: Dichte, Tonnenpreis, Lasereigenschaften "
                         "übernommen, bitte prüfen)")
    if f.get("laser_hinweis") and not neu.get("laser_hinweis"):
        neu["laser_hinweis"] = f["laser_hinweis"]
    if fam == "10210" and neu.get("vorschub_faktor") in (None, 1, 1.0):
        neu["vorschub_faktor"] = 0.95
    return None, neu, f"neu nach Vorlage {vorlage}"


def voll_werkstoff(text, k, a):
    """Werkstoff für Flachstahl, Winkel, Träger: der genannte (z. B. S235JR, 1.4301) ohne Rohrnorm, sonst die
    Erkennung des Imports, solange sie keine Rohrnorm ist (EN 10219 gilt nicht für Vollmaterial)."""
    t = str(text or "").upper().replace(" ", "")
    treffer = [wid for wid, w in k.werkstoffe.items() if _norm_von(w) is None and w.get("archiviert") != "ja"
               and any(x and str(x).upper().replace(" ", "") in t for x in (wid, w.get("werkstoff")))]
    if treffer:
        return sorted(treffer, key=lambda w: -len(str(w)))[0]
    wid = a.get("werkstoff_id")
    return wid if wid in k.werkstoffe and _norm_von(k.werkstoffe[wid]) is None else None


def plan(db, kaeufe=None):
    """Was aus dem ERP-Einkauf angelegt würde: dict(profile [Werte], werkstoffe [Werte], zuordnungen [dict(schluessel,
    artikelnr, bezeichnung, profil_id, werkstoff_id, oberflaeche)], offen [dict(bezeichnung, grund)]). Gemerkte und
    übersprungene ERP-Artikel bleiben, wie sie sind."""
    from .profil_neu import profil_id
    k = db.kontext()
    kaeufe = erp_preise.gespeicherte(db) if kaeufe is None else kaeufe
    artikel = erp_preise.artikel(kaeufe, erp_preise.zuordnungen(db), k)
    profile, werkstoffe, zuord, offen = {}, {}, [], []
    for a in artikel:
        if a.get("gemerkt") or a.get("ignorieren"):
            continue
        text = a["bezeichnung"] + erp_preise.artikelnr_hinweis(a["artikelnr"])
        pid, form = a.get("profil_id"), None
        if pid in k.profile:
            form = k.profile[pid].get("form")
        if pid is None:
            mas = erp_preise.masse(text)
            if mas is None:
                offen.append(dict(bezeichnung=a["bezeichnung"], grund="Abmessung nicht erkannt"))
                continue
            form = mas["form"]
            pid = profil_id(mas["form"], mas["a"], mas["b"], mas["wand"])
            if pid not in k.profile and pid not in profile:
                profile[pid] = dict(profil_id=pid, form=mas["form"], a=mas["a"], b=mas["b"], wand=mas["wand"],
                                    bemerkung=f"aus ERP-EK angelegt ({a['bezeichnung'][:60]})")
        wid, neu, grund = werkstoff_fuer(text, k) if form in HOHLPROFILE else (voll_werkstoff(text, k, a), None,
                                                                               "Werkstoff für Vollmaterial unklar")
        if neu is not None:
            wid = neu["werkstoff_id"]
            werkstoffe.setdefault(wid, neu)
        if wid is None and form in HOHLPROFILE:
            wid = a.get("werkstoff_id")         # Erkennung des Imports (z. B. Edelstahl 1.4301, Aluminium)
        if wid is None:
            offen.append(dict(bezeichnung=a["bezeichnung"], grund=grund))
            continue
        ober, unbekannt = erp_preise.oberflaeche_finden(text, k.oberflaechen, k.werkstoffe.get(wid))
        if unbekannt:
            offen.append(dict(bezeichnung=a["bezeichnung"], grund=f"Oberfläche „{ober}“ fehlt in den Stammdaten"))
            continue
        if (a.get("ampel") == erp_preise.GRUEN and a.get("profil_id") == pid and a.get("werkstoff_id") == wid
                and (a.get("oberflaeche") or "") == ober):
            continue                            # erkennt der Import schon richtig: nichts zu merken
        zuord.append(dict(schluessel=a["schluessel"], artikelnr=a["artikelnr"], bezeichnung=a["bezeichnung"],
                          profil_id=pid, werkstoff_id=wid, oberflaeche=ober))
    return dict(profile=list(profile.values()), werkstoffe=list(werkstoffe.values()), zuordnungen=zuord, offen=offen)


def ausfuehren(db, p, mit_werkstoffen=True):
    """Plan anlegen (vorher Sicherung): Profile, Werkstoffe (nur mit_werkstoffen, sonst entfallen ihre Zuordnungen),
    Zuordnungen merken, KI-Protokoll. Ergebnis dict(profile, werkstoffe, zuordnungen, sicherung)."""
    from . import ki_protokoll
    if not (p["profile"] or p["werkstoffe"] or p["zuordnungen"]):
        from . import material_stamm
        stamm = material_stamm.ergaenzen(db, quelle="ERP-EK")
        return dict(profile=0, werkstoffe=0, zuordnungen=0, sicherung=None, stamm_neu=stamm["neu"],
                    nummern=stamm["nummern"])
    try:
        sich = db.sicherung(zusatz="vor ERP-Anlegen")
    except Exception:           # noqa: BLE001  (ohne Sicherungsordner: trotzdem anlegen, wie Preisliste)
        sich = None
    neu_w = {w["werkstoff_id"] for w in p["werkstoffe"]} if mit_werkstoffen else set()
    for w in p["werkstoffe"]:
        if w["werkstoff_id"] in neu_w:
            db.neu("werkstoffe", w)
    for pr in p["profile"]:
        db.neu("profile", {kk: v for kk, v in pr.items() if v is not None})
    n = 0
    vorhanden_w = set(db.kontext().werkstoffe)
    for z in p["zuordnungen"]:
        if z["werkstoff_id"] not in vorhanden_w:
            continue
        erp_preise.zuordnung_merken(db, z["schluessel"], z["artikelnr"], z["bezeichnung"], z["profil_id"],
                                    z["werkstoff_id"], z["oberflaeche"])
        n += 1
    from . import material_stamm        # Artikelnummer je Abmessung × Werkstoff in den Materialstamm
    stamm = material_stamm.ergaenzen(db, quelle="ERP-EK angelegt")
    erg = dict(profile=len(p["profile"]), werkstoffe=len(neu_w), zuordnungen=n, sicherung=sich,
               stamm_neu=stamm["neu"], nummern=stamm["nummern"])
    ki_protokoll.schreiben(db, "Materialprüfung", "Aus ERP-Einkauf angelegt",
                           ergebnis=f"{erg['profile']} Profile, {erg['werkstoffe']} Werkstoffe, {n} Zuordnungen",
                           quellen=[x["profil_id"] for x in p["profile"]] + sorted(neu_w))
    return erg


VORWAHL_ANTEIL = 0.6        # ein Werkstoff gilt als Vorauswahl, wenn er mindestens 60 % der gekauften Meter hat


def werkstoff_je_profil(db, heute=None, monate=None, anteil=VORWAHL_ANTEIL):
    """Patrick 23.11.2026: „Profile automatisch nach den EK-Import-Erkenntnissen passenden Werkstoff mit Norm als
    Vorauswahl“. Je Profil der Werkstoff, den der Einkauf in den letzten erp_monate überwiegend gekauft hat (nach
    Metern, Anteil ≥ 60 %): {profil_id: dict(werkstoff_id, anteil, meter, kaeufe)}. Nur zugeordnete Käufe (grün,
    nicht übersprungen) zählen; ohne ERP-Daten leer."""
    heute = heute or datetime.date.today()
    monate = monate or int(db.einstellung("erp_monate") or 12)
    try:
        kaeufe = erp_preise.gespeicherte(db)
    except Exception:           # noqa: BLE001  (alte Datei ohne Tabelle erp_kaeufe)
        return {}
    if not kaeufe:
        return {}
    k = db.kontext()
    zu = {a["schluessel"]: a for a in erp_preise.artikel(kaeufe, erp_preise.zuordnungen(db), k)
          if a["ampel"] == erp_preise.GRUEN and not a.get("ignorieren") and a.get("profil_id")
          and a.get("werkstoff_id") in k.werkstoffe}
    ab = erp_preise._monate_zurueck(heute, monate)
    je = {}
    for kauf in kaeufe:
        a = zu.get(kauf["schluessel"])
        if a is None or kauf["datum"] < ab:
            continue
        w = je.setdefault(a["profil_id"], {}).setdefault(a["werkstoff_id"], [0.0, 0])
        w[0] += kauf["menge"]
        w[1] += 1
    out = {}
    for pid, ws in je.items():
        gesamt = sum(m for m, _ in ws.values())
        wid, (meter, n) = max(ws.items(), key=lambda x: (x[1][0], x[1][1]))
        if gesamt > 0 and meter / gesamt >= anteil:
            out[pid] = dict(werkstoff_id=wid, anteil=meter / gesamt, meter=meter, kaeufe=n)
    return out


def vorauswahl(messwerte, profile, je_profil, vorgabe=None):
    """Werkstoff der Rohre und Profile eines STEP-Imports nach dem EK vorbelegen: Körper ohne eigene Wahl (kein
    Werkstoff aus der STEP-Datei, nicht im Prüfdialog gewählt), deren Profil der Einkauf überwiegend in einem
    anderen Werkstoff als der Vorgabe kauft, bekommen ihn als _werkstoff mit Hinweis (_werkstoff_text). Bleche und
    Normteile bleiben. Als _werkstoff_vorschlag gilt er nicht als Korrektur des Kunden (Importprofil lernt ihn
    nicht). Ergebnis: Anzahl vorbelegter Körper."""
    if not je_profil:
        return 0
    from . import step
    n = 0
    for m in messwerte:
        if m.get("fehler") or "_werkstoff" in m or m.get("_normteil") or step.blech(m) is not None \
                or not m.get("profilform"):
            continue
        pid = m.get("_profil") or step.finde_profil(m, profile)
        v = je_profil.get(pid)
        if not v or v["werkstoff_id"] == vorgabe:
            continue
        m["_werkstoff"] = m["_werkstoff_vorschlag"] = v["werkstoff_id"]
        m["_werkstoff_text"] = (f"Werkstoff laut EK-Einkauf: {pid} wird zu {round(v['anteil'] * 100)} % in "
                                f"{v['werkstoff_id']} gekauft ({v['kaeufe']} Käufe, {v['meter']:.0f} m) → Vorauswahl")
        n += 1
    return n
