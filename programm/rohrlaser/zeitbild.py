"""Zeitbild in 7 Zeitarten (Plan X1–X8, Paket X2, Patrick 12.11.2026, Freigabe „Alle Empfehlungen“).

Gliedert die Maschinenzeit je Teil, die die Kalkulation schon rechnet, neu – es ändert sich keine Zahl:
  1 Laserbearbeitung  Schneiden groß/mittel/klein, Gravur, 3D-Mehrzeit, Ecken, Doppellage, Anfahrweg, Abfall
                      zerteilen, abzüglich der Einsparung gemeinsamer Schnitte (bzw. die Schneidzeit von Hand)
  2 Einstich          Einstiche × Einstechzeit
  3 Positionieren     Anfahren je Kontur (feste Zeit je Kontur), Drehen je Seitenwechsel
  4 Bewegung          Leerwege und Drehen zwischen den Konturen aus der Maschinendynamik (dynamik.py), wenn gesetzt
  5 Nebenzeit         Nebenzeit je Teil, Messzyklen, Entnahme von Hand, Zusatzzeiten, Prüfzeit Anbauteile
  6 Rüsten            Rüsten Maschine, Rüsten je Abmessung, Stangenwechsel (mit Ausrichten und Laden von Hand),
                      je Teil umgelegt
  7 Maschinenbelegung Summe 1–6
Summe 1–5 = Laserzeit netto je Teil (laser_netto), Test tests/test_zeitbild.py.

Je Bestandteil steht, aus welchem Feld er kommt. Ist der Bestandteil 0 und das Feld leer, heißt er „nicht
berücksichtigt“ (das Programm rechnet ohne diesen Wert, statt einen zu erfinden); ist er 0 bei gesetztem Feld, kommt
er beim Teil nicht vor. Ohne Qt."""

LASER, EINSTICH, POSITIONIEREN, BEWEGUNG, NEBEN, RUESTEN, BELEGUNG = (
    "laser", "einstich", "positionieren", "bewegung", "neben", "ruesten", "belegung")
ARTEN = ((LASER, "Laserbearbeitung"), (EINSTICH, "Einstich"), (POSITIONIEREN, "Positionieren"),
         (BEWEGUNG, "Bewegung"), (NEBEN, "Nebenzeit"), (RUESTEN, "Rüsten"), (BELEGUNG, "Maschinenbelegung"))
NAME = dict(ARTEN)

# Bestandteil: (Zeitart, Name, Schlüssel in der Kalkulationszeile, Quelle (Tabelle, Feld) oder None, Vorgabe bei leer)
# Vorgabe = das Programm rechnet bei leerem Feld mit einem festen Richtwert (zeit_zusatz), dann nie „nicht berücksichtigt“
TEILE = (
    (LASER, "Kontur groß + Rest", "zeit_gross", ("schneiddaten", "vorschub_gross"), False),
    (LASER, "Kontur mittel", "zeit_mittel", ("schneiddaten", "vorschub_mittel"), True),
    (LASER, "Kontur klein", "zeit_klein", ("schneiddaten", "vorschub_klein"), True),
    (LASER, "Gravur", "zeit_gravur", ("schneiddaten", "vorschub_gravur"), True),
    (LASER, "Mehrzeit 3D", "zeit_d3", None, False),
    (LASER, "Ecken", "zeit_ecken", None, False),
    (LASER, "Anschlag doppelt", "zeit_doppel", None, False),
    (LASER, "Anfahrweg", "zeit_anfahrweg", ("maschine", "anfahrweg"), False),
    (LASER, "Abfall zerteilen", "zeit_abfall", ("maschine", "abfall_max"), False),
    (EINSTICH, "Einstiche", "zeit_einstiche", ("schneiddaten", "einstechzeit"), False),
    (POSITIONIEREN, "Anfahren je Kontur", "zeit_anfahren", ("maschine", "zeit_kontur"), False),
    (POSITIONIEREN, "Drehen je Seitenwechsel", "zeit_drehen", ("maschine", "zeit_drehen"), False),
    (BEWEGUNG, "Leerwege und Drehen (Dynamik)", "zeit_anfahren", ("maschine", "eilgang_x"), False),
    (NEBEN, "Nebenzeit je Teil", "zeit_neben", ("maschine", "zeit_teil"), False),
    (NEBEN, "Messzyklen", "zeit_messen", ("maschine", "zeit_messen_schnell"), True),
    (NEBEN, "Entnahme von Hand", "zeit_entnahme", ("maschine", "zeit_entnahme"), True),
    (NEBEN, "Zusatzzeiten je Stück", "zeit_extra", None, False),
    (NEBEN, "Prüfzeit Anbauteile", "zeit_pruefung", ("einstellungen", "pruefzeit_anbau"), False),
    (RUESTEN, "Rüsten Maschine", "zeit_ruest_maschine", ("maschine", "ruestzeit"), False),
    (RUESTEN, "Rüsten je Abmessung", "zeit_ruest_abm", ("einstellungen", "ruesten_abmessung"), False),
    (RUESTEN, "Stangenwechsel", "zeit_stangenwechsel", ("maschine", "stangenwechsel"), False),
)
FELD_NAMEN = {"vorschub_gross": "Vorschub groß", "vorschub_mittel": "Vorschub mittel", "vorschub_klein": "Vorschub klein",
              "vorschub_gravur": "Vorschub Gravur", "zeit_ecke": "Zeit je Ecke", "einstechzeit": "Einstechzeit",
              "anfahrweg": "Anfahrweg je Innenkontur", "abfall_max": "Größter Abfall ohne Zerteilen",
              "zeit_kontur": "Zeit je Kontur", "zeit_drehen": "Drehzeit je Seitenwechsel",
              "eilgang_x": "Dynamik: Eilgang X", "zeit_teil": "Nebenzeit je Teil",
              "zeit_messen_schnell": "Messzyklus", "zeit_entnahme": "Entnahme von Hand",
              "pruefzeit_anbau": "Prüfzeit Anbauteile", "ruestzeit": "Rüstzeit je Angebot",
              "ruesten_abmessung": "Rüstzeit je Abmessung", "stangenwechsel": "Stangenwechsel je Stange"}
QUELLE = {"schneiddaten": "Schneiddaten", "maschine": "Maschine", "einstellungen": "Einstellungen"}


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _leer(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _feld_leer(quelle, z, m, einst):
    """True, wenn das Quellfeld leer bzw. 0 ist (ohne Quelle: nie)."""
    if not quelle:
        return False
    tab, feld = quelle
    if tab == "schneiddaten":
        v = z.get(feld)
    elif tab == "maschine":
        v = (m or {}).get(feld)
    else:
        v = (einst or {}).get(feld)
    return _leer(v) or _n(v) == 0 and not isinstance(v, str)


def zeitbild(z, m=None, einst=None):
    """Zeitbild einer Kalkulationszeile (rechnen.kalkulation, je Teil). m = Maschine, einst = Einstellungen (beide
    nur für „nicht berücksichtigt“). Ergebnis dict(arten=[dict(art, name, s, teile=[dict(name, s, feld, status)])],
    s={Zeitart: s}, belegung, laser_netto) oder None ohne Laserzeit (Zukaufteil, Baugruppe, keine Schneiddaten).
    status: 'gerechnet', 'nicht berücksichtigt' (Feld leer), 'kommt nicht vor' (Feld gesetzt, beim Teil 0)."""
    if not z or z.get("laser_netto") is None:
        return None
    manuell = z.get("zeit_manuell") == "ja"
    dyn = z.get("zeit_dynamik") == "ja"
    teile = {a: [] for a, _ in ARTEN}
    for art, name, schl, quelle, vorgabe in TEILE:
        if art == BEWEGUNG and not dyn or art == POSITIONIEREN and schl == "zeit_anfahren" and dyn:
            continue
        if manuell and art in (LASER, EINSTICH, POSITIONIEREN, BEWEGUNG) or manuell and schl in (
                "zeit_neben", "zeit_messen", "zeit_entnahme"):
            continue
        s = _n(z.get(schl))
        if s:
            status = "gerechnet"
        elif not vorgabe and _feld_leer(quelle, z, m, einst):
            status = "nicht berücksichtigt"
        else:
            status = "kommt nicht vor"
        feld = f"{QUELLE[quelle[0]]}: {FELD_NAMEN.get(quelle[1], quelle[1])}" if quelle else ""
        teile[art].append(dict(name=name, s=s, feld=feld, status=status))
    if manuell:
        # Schneidzeit von Hand ersetzt die berechnete Zeit (rechnen._laserzeit): ein Bestandteil
        hand = _n(z.get("laser_netto")) - _n(z.get("zeit_extra")) - _n(z.get("zeit_pruefung"))
        teile[LASER].insert(0, dict(name="Schneidzeit von Hand", s=hand, feld="Position: Schneidzeit manuell",
                                    status="gerechnet"))
    else:
        brutto = _n(z.get("laser_brutto"))
        gespart = min(_n(z.get("einsparung")), brutto)      # wie rechnen._laserzeit: max(0, brutto − Einsparung)
        if gespart:
            teile[LASER].append(dict(name="Einsparung gemeinsamer Schnitt", s=-gespart, feld="Schnittplan",
                                     status="gerechnet"))
    s = {a: sum(t["s"] for t in teile[a]) for a, _ in ARTEN if a != BELEGUNG}
    s[BELEGUNG] = sum(s.values())
    arten = [dict(art=a, name=n, s=s[a], teile=teile[a]) for a, n in ARTEN]
    return dict(arten=arten, s=s, belegung=s[BELEGUNG], laser_netto=_n(z.get("laser_netto")))


def felder(z, m=None, einst=None):
    """Zeitbild als Zeilenfelder zb_<art> [s je Teil] (Spalten, Kalkulations-PDF); leer ohne Laserzeit."""
    b = zeitbild(z, m, einst)
    return {f"zb_{a}": (b["s"][a] if b else None) for a, _ in ARTEN}


def nicht_beruecksichtigt(zeilen, m=None, einst=None):
    """Namen der Bestandteile, die in keiner Zeile gerechnet wurden, weil ihr Feld leer ist (Hinweis unter der
    Tabelle). Kommt ein Bestandteil in einer Zeile vor, fehlt er hier."""
    nie, gerechnet = {}, set()
    for z in zeilen or ():
        b = zeitbild(z, m, einst)
        for a in (b or {}).get("arten", ()):
            for t in a["teile"]:
                if t["status"] == "gerechnet":
                    gerechnet.add(t["name"])
                elif t["status"] == "nicht berücksichtigt":
                    nie.setdefault(t["name"], t["feld"])
    return [(n, f) for n, f in nie.items() if n not in gerechnet]


def summen(zeilen, m=None, einst=None):
    """Zeitbild über das Angebot [s]: je Zeitart Σ Zeit je Teil × Stück."""
    out = {a: 0.0 for a, _ in ARTEN}
    for z in zeilen or ():
        b = zeitbild(z, m, einst)
        if b:
            for a, _ in ARTEN:
                out[a] += b["s"][a] * _n(z.get("stueck"))
    return out
