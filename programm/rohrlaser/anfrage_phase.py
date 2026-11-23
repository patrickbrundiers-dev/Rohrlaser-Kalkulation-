"""Phasen einer Anfrage bis zum Auftrag und Bearbeiter-Vorschlag (Patrick 20.11.2026, Plan K6/K7, „Alles einbauen“).

Phasen (PHASEN, in dieser Reihenfolge): Neu, In Bearbeitung, Technische Prüfung, Rückfrage, Angebot erstellt,
Auftrag erhalten, Produktion, Erledigt, Nicht relevant. Es gibt keinen zweiten Status: die Phase wird gerechnet aus
  - dem Status der Akte (Neu / In Bearbeitung / Erledigt, „Keine Anfrage“ = Nicht relevant),
  - der offenen Rückfrage an den Kunden,
  - den verknüpften Angeboten und Aufträgen (Angebot erstellt, beauftragt, Auftrag in Produktion, ausgeliefert),
  - einer Phase von Hand (Technische Prüfung, Rückfrage …; Ereignis ak.PHASE, auch aus einem Outlook-Ordner).
Die von Hand gesetzte Phase gilt, bis der Ablauf weiter ist (z. B. ein Angebot entsteht); Erledigt und Nicht
relevant aus dem Status gehen immer vor.

Outlook-Ordner je Phase (ordner_einstellungen): für Technische Prüfung, Rückfrage, Angebot erstellt, Auftrag
erhalten, Produktion und Nicht relevant kann ein eigener Ordner gewählt werden. Leer = wie bisher (In Bearbeitung
bzw. Erledigt). Siehe outlook_anfragen.

Bearbeiter-Vorschlag (vorschlag): Punkte für den im Kundenstamm Zuständigen, wer die letzten Anfragen dieses
Kunden hatte, Erfahrung im Sachgebiet und wie viele offene Anfragen jemand hat. Ergebnis mit Gründen; „sicher“ nur,
wenn der Kunde einen Zuständigen hat oder die letzten drei Anfragen beim selben lagen. Zugewiesen wird automatisch
nur mit der Einstellung AUTO (Vorgabe aus). Ohne Qt."""
from . import anfragen_akten as ak

NEU, BEARBEITUNG, PRUEFUNG, RUECKFRAGE = "neu", "bearbeitung", "pruefung", "rueckfrage"
ANGEBOT, AUFTRAG, PRODUKTION, ERLEDIGT, NICHT_RELEVANT = ("angebot", "auftrag", "produktion", "erledigt",
                                                         "nicht_relevant")
PHASEN = (NEU, BEARBEITUNG, PRUEFUNG, RUECKFRAGE, ANGEBOT, AUFTRAG, PRODUKTION, ERLEDIGT, NICHT_RELEVANT)
PHASE_TEXT = {NEU: "Neu", BEARBEITUNG: "In Bearbeitung", PRUEFUNG: "Technische Prüfung", RUECKFRAGE: "Rückfrage",
              ANGEBOT: "Angebot erstellt", AUFTRAG: "Auftrag erhalten", PRODUKTION: "Produktion",
              ERLEDIGT: "Erledigt", NICHT_RELEVANT: "Nicht relevant"}
VON_HAND = (BEARBEITUNG, PRUEFUNG, RUECKFRAGE, ANGEBOT, AUFTRAG, PRODUKTION)    # im Programm wählbar
# Phasen mit eigenem (wählbarem) Outlook-Ordner und der Status, den eine Mail dort bedeutet
ORDNER_PHASEN = {PRUEFUNG: ak.BEARBEITUNG, RUECKFRAGE: ak.BEARBEITUNG, ANGEBOT: ak.BEARBEITUNG,
                 AUFTRAG: ak.BEARBEITUNG, PRODUKTION: ak.BEARBEITUNG, NICHT_RELEVANT: ak.ERLEDIGT}
ORDNER_EINSTELLUNG = "outlook_ordner_phase_"        # + Phase: Outlook-Pfad (leer = nicht benutzt)
AUTO = "anfragen_auto_zuweisen"                     # ja: sichere Bearbeiter-Vorschläge automatisch zuweisen
GELERNT = 40                                        # Punkte für den Tipp des freigegebenen Bearbeiter-Modells

_RANG = {p: i for i, p in enumerate(PHASEN)}


def rang(p):
    return _RANG.get(p, 0)


def angebots_phase(db, nummern):
    """Weiteste Phase der verknüpften Angebote: 'angebot', 'auftrag', 'produktion', 'erledigt' (ausgeliefert/
    abgeschlossen) oder '' (kein Angebot). Ohne Datenbank oder bei Fehlern: 'angebot', wenn Nummern da sind."""
    if not nummern:
        return ""
    if db is None:
        return ANGEBOT
    from . import auftraege as au
    best = ANGEBOT
    for n in nummern:
        try:
            z = db.con.execute("SELECT k.status FROM auftrag_angebote a JOIN auftrag_kopf k ON k.uid=a.auftrag "
                               "WHERE a.nummer=? ORDER BY a.am DESC LIMIT 1", (n,)).fetchone()
        except Exception:           # noqa: BLE001 – ohne Auftragstabellen: nur „Angebot erstellt“
            z = None
        if z is None:
            try:
                v = db.con.execute("SELECT vorgang FROM angebote WHERE nummer=? ORDER BY id DESC LIMIT 1",
                                   (n,)).fetchone()
            except Exception:       # noqa: BLE001
                v = None
            p = AUFTRAG if v and str(v[0] or "") == "Beauftragt" else ANGEBOT
        else:
            s = z[0]
            p = ERLEDIGT if s in (au.AUSGELIEFERT, au.ABGESCHLOSSEN) else (
                PRODUKTION if s in (au.BEREIT, au.PRODUKTION, au.QS, au.TEILWEISE, au.FERTIG) else AUFTRAG)
        if rang(p) > rang(best):
            best = p
    return best


def phase(akte, angebot_phase=""):
    """Phase der Akte (siehe oben). angebot_phase: Ergebnis von angebots_phase (sonst nur aus der Akte)."""
    s = akte.stand
    if akte.aussortiert or s.get("status") == ak.AUSSORTIERT:
        return NICHT_RELEVANT
    if akte.status == ak.ERLEDIGT:
        return ERLEDIGT
    p = NEU if akte.status == ak.NEU else BEARBEITUNG
    if s.get("rueckfrage"):
        p = RUECKFRAGE
    ap = angebot_phase or (ANGEBOT if s.get("angebote") else "")
    if ap and rang(ap) > rang(p):
        p = ap
    hand = s.get("phase") or ""
    if hand in PHASE_TEXT and rang(hand) >= rang(p) and hand not in (ERLEDIGT, NICHT_RELEVANT):
        p = hand
    elif hand == PRUEFUNG and p in (NEU, BEARBEITUNG):
        p = PRUEFUNG
    return p


def text(p):
    return PHASE_TEXT.get(p, p or "")


def ordner_einstellungen(db):
    """{Phase: Outlook-Pfad} der gewählten Phasen-Ordner (nur gesetzte)."""
    out = {}
    for p in ORDNER_PHASEN:
        try:
            w = (db.einstellung(ORDNER_EINSTELLUNG + p) or "").strip()
        except Exception:           # noqa: BLE001
            w = ""
        if w:
            out[p] = w
    return out


# ---------------------------------------------------------------------------------------------- Bearbeiter
def vorschlag(akte, akten, kunden=(), mitarbeiter=(), sachgebiete=None, gelernt=None):
    """Bearbeiter-Vorschlag: dict(kuerzel, punkte, sicher, gruende=[…], weitere=[(Kürzel, Punkte)]) oder None.
    mitarbeiter: Kürzel der möglichen Bearbeiter (leer = alle, die in den Akten vorkommen). gelernt: (Kürzel, p, n)
    aus dem freigegebenen Bearbeiter-Modell (anfrage_lernen.bearbeiter_tipp, 23.11.2026): +GELERNT Punkte, macht
    den Vorschlag aber nie „sicher“."""
    punkte, gruende = {}, {}

    def dazu(k, p, g):
        if not k:
            return
        k = str(k).strip().upper()
        punkte[k] = punkte.get(k, 0) + p
        gruende.setdefault(k, []).append(g)

    sicher_von = ""
    zust = {str(k.get("kundennr")): str(k.get("zustaendig") or "").strip().upper() for k in kunden or ()}
    if akte.kunde and zust.get(akte.kunde):
        dazu(zust[akte.kunde], 100, "im Kundenstamm zuständig")
        sicher_von = zust[akte.kunde]
    frueher = sorted((a for a in akten if a.nr != akte.nr and akte.kunde and a.kunde == akte.kunde
                      and a.bearbeiter), key=lambda a: a.eingang or "", reverse=True)[:5]
    for i, a in enumerate(frueher):
        dazu(a.bearbeiter, 25 if i < 3 else 10, f"hatte {a.nr} dieses Kunden")
    letzte3 = [a.bearbeiter for a in frueher[:3]]
    if len(letzte3) == 3 and len(set(letzte3)) == 1 and not sicher_von:
        sicher_von = letzte3[0]
    sg = set(sachgebiete if sachgebiete is not None else ((akte.einordnung or {}).get("sachgebiete") or ()))
    if sg:
        erfahrung = {}
        for a in akten:
            if a.nr == akte.nr or not a.bearbeiter:
                continue
            if sg & set((a.einordnung or {}).get("sachgebiete") or ()):
                erfahrung[a.bearbeiter] = erfahrung.get(a.bearbeiter, 0) + 1
        for k, n in erfahrung.items():
            dazu(k, min(n * 5, 30), f"{n} Anfrage(n) im selben Sachgebiet")
    if gelernt:
        dazu(gelernt[0], GELERNT, f"gelernt aus {gelernt[2]} Zuweisungen ({round(100 * gelernt[1])} %)")
    offen = {}
    for a in akten:
        wer = a.bearbeiter if a.status == ak.BEARBEITUNG else (a.stand.get("zugewiesen") if a.status == ak.NEU
                                                                else "")
        if wer:
            offen[wer.upper()] = offen.get(wer.upper(), 0) + 1
    erlaubt = {str(m).strip().upper() for m in mitarbeiter or () if m}
    for k in list(punkte):
        if erlaubt and k not in erlaubt:
            punkte.pop(k)
            continue
        if offen.get(k):
            punkte[k] -= min(offen[k] * 3, 30)
            gruende[k].append(f"{offen[k]} offene Anfrage(n)")
    if not punkte:
        return None
    reihe = sorted(punkte.items(), key=lambda x: (-x[1], offen.get(x[0], 0), x[0]))
    k, p = reihe[0]
    return dict(kuerzel=k, punkte=p, sicher=k == sicher_von, gruende=gruende.get(k, []), weitere=reihe[1:4])


def vorschlaege_zuweisen(abl, akten, kunden=(), mitarbeiter=(), jetzt=None):
    """Mit Einstellung AUTO: neue, nie zugewiesene Anfragen mit sicherem Vorschlag zuweisen (ein Platz je Akte über
    die Sperrdatei wie ak.OrdnerAblage.zustaendig_zuweisen; von Hand aufgehoben bleibt aufgehoben).
    Ergebnis: [(Nummer, Kürzel)]."""
    out = []
    for a in akten:
        if a.status != ak.NEU or any(e.get("aktion") in (ak.ZUGEWIESEN, ak.UEBERNOMMEN) for e in a.verlauf):
            continue
        v = vorschlag(a, akten, kunden, mitarbeiter)
        if not v or not v["sicher"]:
            continue
        if not ak._exklusiv(a.pfad / "zuweisung_auto.sperre", v["kuerzel"]):
            continue
        abl.ereignis(a, ak.ZUGEWIESEN, alt="", neu=v["kuerzel"], automatisch=True, vorschlag=True,
                     grund="; ".join(v["gruende"][:3]), jetzt=jetzt)
        out.append((a.nr, v["kuerzel"]))
    return out
