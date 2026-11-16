"""Zukaufteile im STEP-Import einordnen und auflisten (CAD-Entwicklungsplan Paket 1, Patrick 12.11.2026).

Jedes Normteil bekommt Kategorie, Norm, Größe, Grund und Vertrauensstufe:
- sicher: bekannte Norm im Bauteilnamen (Tabelle NORMEN) oder an der Form gemessen (Kugel, Sechskant: step_drehfraes);
- wahrscheinlich: Begriff im Bauteilnamen (Schraube, washer, Niet …);
- Vorschlag: nur die Form passt (runde Scheibe mit Loch, kurzer Stift, Hülse, Niet mit Kopf). Ein Vorschlag ändert
  nichts: das Teil bleibt Fertigungsteil, bis er in der Liste „Zukaufteile“ angenommen wird.
Eine Norm wird nie erfunden: sie steht nur da, wenn sie im Namen steht. Die Größe kommt aus dem Namen (M12x40),
sonst aus der Messung und ist dann als gemessen bezeichnet. Halbzeug-Normen (EN 10219, DIN 2395 …) machen aus einem
Rohr kein Normteil.
"""
import re

SICHER, WAHRSCHEINLICH, VORSCHLAG = "sicher", "wahrscheinlich", "Vorschlag"

SCHRAUBE, MUTTER, SCHEIBE, RING, NIET, STIFT = "Schraube", "Mutter", "Scheibe", "Sicherungsring", "Niet", "Stift"
GEWINDE, HUELSE, LAGER, KUGEL, PASSFEDER, SONST = ("Gewindestange/-bolzen", "Hülse/Buchse", "Lager", "Kugel",
                                                   "Passfeder", "Normteil")
EINSATZ = "Gewindeeinsatz"        # Einpress-/Nietmutter, Gewindebuchse, Drahtgewindeeinsatz (Paket 5)
KOPFTEIL = "Schraube/Niet"      # nur aus der Form (Kopf mit Schaft): Schraube, Niet oder Bolzen mit Kopf
KATEGORIEN = (SCHRAUBE, MUTTER, EINSATZ, SCHEIBE, RING, NIET, KOPFTEIL, STIFT, GEWINDE, HUELSE, LAGER, KUGEL, PASSFEDER, SONST)

# Bekannte Normen der Verbindungselemente: Nummer -> Kategorie. DIN und ISO haben getrennte Nummernkreise.
_DIN = {
    SCHRAUBE: (84, 85, 316, 404, 444, 478, 479, 480, 561, 564, 571, 580, 601, 603, 604, 605, 607, 608, 609, 912, 913,
               914, 915, 916, 931, 933, 960, 961, 963, 964, 965, 966, 6912, 6914, 6921, 7500, 7504, 7513, 7516, 7971,
               7972, 7973, 7976, 7981, 7982, 7983, 7984, 7985, 7991),
    MUTTER: (315, 439, 466, 467, 546, 555, 557, 562, 582, 917, 928, 929, 934, 935, 936, 937, 979, 980, 981, 982, 985,
             986, 1587, 1804, 1816, 6330, 6331, 6334, 6915, 6923, 6924, 6925, 6926, 6927),
    SCHEIBE: (125, 126, 127, 128, 137, 433, 434, 435, 436, 440, 1052, 2093, 6319, 6340, 6796, 6797, 6798, 6916, 6917,
              6918, 7349, 7989, 9021),
    RING: (471, 472, 983, 984, 6799, 7993),
    NIET: (124, 302, 660, 661, 662, 674, 7337, 7338, 7339, 7340, 7341),
    STIFT: (1, 7, 94, 258, 1433, 1434, 1435, 1436, 1443, 1444, 1469, 1470, 1471, 1472, 1473, 1474, 1475, 1476, 1477,
            1481, 6325, 7343, 7344, 7346, 7978, 7979, 11024),
    GEWINDE: (835, 938, 939, 940, 975, 976),
    LAGER: (615, 617, 625, 628, 630, 635, 711, 720, 1850),
    PASSFEDER: (6885, 6888),
    EINSATZ: (8140,),           # Drahtgewindeeinsätze
}
_ISO = {
    SCHRAUBE: (1207, 1479, 1481, 1482, 1483, 1580, 2009, 2010, 4014, 4016, 4017, 4018, 4026, 4027, 4028, 4029, 4762,
               7045, 7046, 7047, 7049, 7050, 7051, 7379, 7380, 8676, 8765, 10642, 14579, 14580, 14581, 14583, 14584,
               15480, 15481, 15482, 15483),
    MUTTER: (4032, 4033, 4034, 4035, 4036, 4161, 7040, 7042, 8673, 8674, 8675, 10511, 10512, 10513, 21670),
    SCHEIBE: (7089, 7090, 7091, 7092, 7093, 7094, 10673),
    NIET: (1051, 15977, 15978, 15979, 15980, 15981, 15982, 15983, 15984, 16582, 16583, 16584, 16585),
    STIFT: (1234, 2338, 2339, 2340, 2341, 8733, 8734, 8735, 8736, 8737, 8739, 8740, 8741, 8742, 8743, 8744, 8745,
            8746, 8747, 8748, 8750, 8751, 8752, 13337),
    LAGER: (3547, 4379),
    PASSFEDER: (2491, 3912),
}
NORMEN = {("DIN", n): k for k, liste in _DIN.items() for n in liste}
NORMEN.update({("ISO", n): k for k, liste in _ISO.items() for n in liste})

# Normen für Rohre, Profile, Bleche und Stahlsorten: kein Normteil (EN 10219 im Namen eines Rohrs)
_HALBZEUG_DIN = {59, 174, 175, 176, 177, 178, 1013, 1014, 1015, 1016, 1017, 1022, 1024, 1025, 1026, 1027, 1028, 1029,
                 1615, 1623, 1626, 1629, 1630, 1651, 2391, 2393, 2394, 2395, 2440, 2441, 2448, 2458, 2462, 2463, 11850,
                 17100, 17175, 17440, 17455, 17456, 17457, 17458, 59410, 59411}
_HALBZEUG_ISO = {657, 1127, 4019, 4200, 9445, 10799, 12633}

_NORM = re.compile(r"(?<![A-Za-z])(DIN\s*EN\s*ISO|DIN\s*EN|DIN\s*ISO|EN\s*ISO|DIN|ISO|EN)[\s_\-]*(\d{1,5})(?!\d)",
                   re.IGNORECASE)
_GEWINDE = re.compile(r"(?<![A-Za-z0-9])M\s?(\d{1,2}(?:[.,]\d)?)((?:\s?[x×*]\s?\d{1,4}(?:[.,]\d{1,2})?){0,2})(?![0-9])",
                      re.IGNORECASE)
_MASS = re.compile(r"(?<![0-9A-Za-z.,])(\d{1,3}(?:[.,]\d{1,2})?(?:\s?[x×*]\s?\d{1,4}(?:[.,]\d{1,2})?){1,2})(?![0-9])")

# Begriffe im Bauteilnamen (deutsch und englisch), als eigenes Wort bzw. Wortende/-anfang wie angegeben
_BEGRIFFE = (
    (EINSATZ, r"(?:ein)?nietmuttern?|blindnietmuttern?|einpressmuttern?|einpressbolzen|einschraubbuchsen?|"
              r"gewindeeins(?:ä|ae)tze?|gewindebuchsen?|helicoils?|rivet\s?nuts?|rivnuts?|press\s?nuts?|"
              r"clinch\s?nuts?|self\s?clinching\s?nuts?|threaded\s?inserts?"),
    (NIET, r"blindniet\w*|\w*niet(?:e|en|mutter)?|rivets?|blind\s?rivets?|pop\s?rivets?"),
    (MUTTER, r"\w*mutter|\w*muttern|(?:hex\s?|lock\s?|flange\s?|weld\s?|wing\s?)?nuts?"),
    (RING, r"sicherungsring\w*|seegerring\w*|sprengring\w*|circlips?|retaining\s?rings?|snap\s?rings?"),
    (SCHEIBE, r"(?:unterleg|beileg|karosserie|feder|spann|zahn|f(?:ä|ae)cher|sicherungs|keil|pass|u-|u)?scheiben?|"
              r"federring\w*|tellerfeder\w*|(?:flat\s?|plain\s?|spring\s?|lock\s?)?washers?"),
    (GEWINDE, r"gewindestangen?|gewindebolzen|gewindestifte?|stehbolzen|threaded\s?rods?|studs?|set\s?screws?|"
              r"grub\s?screws?"),
    (SCHRAUBE, r"\w*schrauben?|(?:hex\s?|cap\s?|socket\s?|machine\s?)?screws?|bolts?"),
    (STIFT, r"(?:zylinder|pass|kegel|kerb|spann|scher)?stifte?|spannh(?:ü|ue)lsen?|splinte?|dowels?|dowel\s?pins?|"
            r"(?:spring\s?|roll\s?|cotter\s?|split\s?|taper\s?)?pins?"),
    (HUELSE, r"(?:distanz|abstands)?h(?:ü|ue)lsen?|distanz(?:rohr|st(?:ü|ue)ck)\w*|(?:gleit|lager|bund)?buchsen?|"
             r"spacers?|sleeves?|bush(?:es|ing|ings)?"),
    (LAGER, r"(?:kugel|rillenkugel|rollen|nadel|gleit|pendel|gelenk|flansch|steh)lager|bearings?"),
    (KUGEL, r"kugel|kugeln|balls?"),
    (PASSFEDER, r"passfedern?|feather\s?keys?|parallel\s?keys?"),
)
_WORT = [(k, re.compile(r"(?<![0-9A-Za-zÄÖÜäöüß])(?:" + muster + r")(?![A-Za-zÄÖÜäöüß])", re.IGNORECASE))
         for k, muster in _BEGRIFFE]

KEIN_ROHR = (None, "", "Drehteil", "Frästeil", "Rundstahl", "Vierkantstahl", "Flachstahl", "Blech")
KLEIN_BIS = 150.0           # Begriff im Namen gilt als Zukaufteil, wenn das Teil höchstens so groß ist (mm)
SCHEIBE_D_MAX = 60.0        # Vorschlag Scheibe: runde Scheibe mit einem Loch in der Mitte bis Ø
SCHEIBE_DICKE_MAX = 6.0
STIFT_D_MAX = 16.0          # Vorschlag Stift: glatter Rundstahl bis Ø und bis Länge
STIFT_L_MAX = 120.0
HUELSE_D_MAX = 40.0         # Vorschlag Hülse/Buchse: kurzes dickwandiges Rohr bis Ø
NIET_D_MAX = 20.0           # Vorschlag Niet/Bolzen mit Kopf: Kopf bis Ø


def _z(m, feld):
    try:
        return float(m.get(feld) or 0)
    except (TypeError, ValueError):
        return 0.0


def _mm(x):
    return f"{float(x):.1f}".rstrip("0").rstrip(".").replace(".", ",")


def _art(roh):
    r = re.sub(r"\s+", " ", roh.upper())
    return "ISO" if "ISO" in r else "DIN" if "DIN" in r else "EN"


def normen(name):
    """Normangaben im Namen: Liste (Text wie im Namen, Nummernkreis DIN/ISO/EN, Nummer)."""
    return [(re.sub(r"[\s_\-]+", " ", f"{a.upper()} {n}").replace("DINEN", "DIN EN").replace("ENISO", "EN ISO")
             .replace("DINISO", "DIN ISO"), _art(a), int(n)) for a, n in _NORM.findall(name or "")]


def _halbzeug(a, n):
    return (a == "EN" and 10000 <= n <= 10399) or (a == "DIN" and n in _HALBZEUG_DIN) or \
        (a == "ISO" and n in _HALBZEUG_ISO)


def halbzeug_norm(name):
    """Der Name nennt nur Normen für Rohre, Profile, Bleche oder Stahlsorten (EN 10xxx, DIN 2395 …), keine eines
    Verbindungselements: der Begriff DIN/ISO/EN macht daraus kein Normteil."""
    gefunden = normen(name)
    if not gefunden or any((a, n) in NORMEN for _, a, n in gefunden):
        return False
    return all(_halbzeug(a, n) for _, a, n in gefunden)


def norm(name):
    """(Normtext, Kategorie) der ersten bekannten Norm im Namen, sonst (erste Normangabe, None) bzw. (None, None)."""
    gefunden = normen(name)
    for text, a, n in gefunden:
        if (a, n) in NORMEN:
            return text, NORMEN[(a, n)]
    for text, a, n in gefunden:
        if not _halbzeug(a, n):
            return text, None
    return None, None


def begriff(name):
    """(Kategorie, gefundenes Wort) des ersten Begriffs im Namen, sonst (None, None)."""
    ohne = _NORM.sub(" ", name or "").replace("_", " ")
    for k, muster in _WORT:
        t = muster.search(ohne)
        if t:
            return k, t.group(0)
    return None, None


def groesse_im_namen(name):
    """Größe aus dem Namen: Gewinde (M12x40) bzw. Maße (13x24x2,5) hinter der Norm; sonst ''."""
    ohne = _NORM.sub(" ", name or "")
    t = _GEWINDE.search(ohne)
    if t:
        rest = re.sub(r"\s", "", t.group(2)).replace("×", "x").replace("*", "x")
        return f"M{t.group(1)}{rest}"
    t = _MASS.search(ohne)
    return re.sub(r"\s", "", t.group(1)).replace("×", "x").replace("*", "x") if t else ""


def _groesste(m):
    return max(_z(m, "laenge"), _z(m, "abm_a"), _z(m, "abm_b"))


def _daten(m):
    from . import drehfraes
    return drehfraes.daten(m) or {}


def groesse_gemessen(m, kategorie=None):
    """Größe aus der Messung als Text ('Ø24 × 2,5, Bohrung Ø13'); '' wenn nichts gemessen ist."""
    d = _daten(m)
    if d.get("durchmesser"):
        innen = f"/Ø{_mm(d['innen'])}" if d.get("innen") else ""
        return f"Ø{_mm(d['durchmesser'])}{innen} × {_mm(d.get('laenge') or 0)}"
    form = m.get("profilform")
    if form == "Blech" and _z(m, "abm_a"):
        loch = str(m.get("bohrungen") or "").split(":")[0]
        rund = abs(_z(m, "abm_a") - _z(m, "abm_b")) <= 0.02 * _z(m, "abm_a")
        text = (f"Ø{_mm(_z(m, 'abm_a'))}" if rund else f"{_mm(_z(m, 'abm_a'))} × {_mm(_z(m, 'abm_b'))}") \
            + f" × {_mm(_z(m, 'wandstaerke'))}"
        try:
            return text + (f", Bohrung Ø{_mm(float(loch))}" if loch and m.get("innen_konturen") in (1, "1") else "")
        except ValueError:
            return text
    if form == "Rundstahl" and _z(m, "abm_a"):
        return f"Ø{_mm(_z(m, 'abm_a'))} × {_mm(_z(m, 'laenge'))}"
    if form == "Rundrohr" and _z(m, "abm_a"):
        return f"Ø{_mm(_z(m, 'abm_a'))} × {_mm(_z(m, 'wandstaerke'))} × {_mm(_z(m, 'laenge'))}"
    return ""


def aus_form(m):
    """Vorschlag nur aus der Form: (Kategorie, Grund) oder None. Nie mehr als ein Vorschlag (ein Stift und ein
    Rundstahl-Abschnitt sehen gleich aus)."""
    if m.get("fehler"):
        return None
    form, d = m.get("profilform"), _daten(m)
    a, b, lg = _z(m, "abm_a"), _z(m, "abm_b"), _z(m, "laenge")
    if form == "Blech" and a and abs(a - b) <= 0.02 * a and a <= SCHEIBE_D_MAX and \
            0 < _z(m, "wandstaerke") <= SCHEIBE_DICKE_MAX and str(m.get("innen_konturen")) == "1" and \
            str(m.get("konturen")) == "2" and str(m.get("n_flaechen")) == "4":
        return SCHEIBE, f"runde Scheibe Ø{_mm(a)} × {_mm(_z(m, 'wandstaerke'))} mit einem Loch in der Mitte"
    if form == "Rundstahl" and 0 < a <= STIFT_D_MAX and 0 < lg <= STIFT_L_MAX and str(m.get("konturen") or "0") == "0":
        return STIFT, f"glatter Rundstahl Ø{_mm(a)} × {_mm(lg)}"
    if d.get("art") == "Drehteil" and not d.get("normteil"):
        dm, innen, aussen = float(d.get("durchmesser") or 0), float(d.get("innen") or 0), d.get("durchmesser_liste") or []
        if d.get("nur_abmessung") and innen and dm <= HUELSE_D_MAX:
            return HUELSE, f"kurzes dickwandiges Rohr Ø{_mm(dm)}/Ø{_mm(innen)} × {_mm(d.get('laenge') or 0)}"
        if len(aussen) == 2 and 0 < dm <= NIET_D_MAX and not d.get("zusatz"):
            kopf = next((x for x in (d.get("kennwerte") or {}).get("aussen") or () if abs(x["d"] - dm) < 1e-6), None)
            if kopf and kopf["l"] <= 0.6 * dm and float(d.get("laenge") or 0) > kopf["l"]:
                text = f"Kopf Ø{_mm(dm)} × {_mm(kopf['l'])} mit Schaft Ø{_mm(min(aussen))}"
                if innen:
                    return NIET, text + f", hohl Ø{_mm(innen)} (Blindniet?)"
                return KOPFTEIL, text + " (Schraube, Niet oder Bolzen mit Kopf)"
    return None


_FORM_KATEGORIE = {"Kugel": KUGEL, "Mutter": MUTTER, "Schraube/Mutter mit Sechskant": SCHRAUBE,
                   "Schraube/Gewindestange mit Mutter": GEWINDE, "Gewindebolzen": GEWINDE}


def einordnen(m):
    """Einordnung eines Körpers als Zukaufteil: dict(kategorie, norm, groesse, groesse_quelle, grund, vertrauen)
    oder None (kein Hinweis auf ein Zukaufteil). Reihenfolge: bekannte Norm im Namen, an der Form gemessenes Normteil,
    Begriff im Namen, Vorschlag aus der Form."""
    if m.get("fehler"):
        return None
    name = str(m.get("bauteil") or "")
    ntext, nkat = norm(name)
    wkat, wort = begriff(name)
    gname = groesse_im_namen(name) if (nkat or wkat or ntext) else ""
    gemessen = groesse_gemessen(m)
    groesse, quelle = (gname, "Name") if gname else (gemessen, "gemessen") if gemessen else ("", "")
    geo = _daten(m).get("normteil")
    if nkat:
        return dict(kategorie=nkat, norm=ntext, groesse=groesse, groesse_quelle=quelle, vertrauen=SICHER,
                    grund=f"Norm {ntext} im Bauteilnamen")
    if geo:
        return dict(kategorie=_FORM_KATEGORIE.get(geo, SONST), norm=ntext or "", groesse=groesse,
                    groesse_quelle=quelle, vertrauen=SICHER, grund=f"an der Form erkannt ({geo})")
    if wkat:
        # ein Rohr oder Profil, das „Hülse“ heißt, ist ein Rohrlaserteil: nur Vorschlag; ebenso ein großes Teil
        rohr = m.get("profilform") not in KEIN_ROHR
        klein = _groesste(m) <= KLEIN_BIS or m.get("profilform") in ("Drehteil", "Frästeil")
        aber = ", aber als Rohr/Profil gemessen" if rohr else "" if klein else f", aber größer als {_mm(KLEIN_BIS)} mm"
        return dict(kategorie=wkat, norm=ntext or "", groesse=groesse, groesse_quelle=quelle,
                    vertrauen=VORSCHLAG if aber else WAHRSCHEINLICH,
                    grund=f"Begriff „{wort}“ im Bauteilnamen" + aber)
    if ntext and not halbzeug_norm(name):
        return dict(kategorie=SONST, norm=ntext, groesse=groesse, groesse_quelle=quelle, vertrauen=WAHRSCHEINLICH,
                    grund=f"Norm {ntext} im Bauteilnamen (Kategorie nicht bekannt)")
    f = aus_form(m)
    if f:
        return dict(kategorie=f[0], norm="", groesse=gemessen, groesse_quelle="gemessen", vertrauen=VORSCHLAG,
                    grund=f"nur nach der Form: {f[1]}")
    return None


def bezeichnung(m, info=None):
    """Bezeichnung eines aus der Form angenommenen Zukaufteils für Angebot und Preisliste ('Scheibe Ø24 × 2,5,
    Bohrung Ø13'); steht ein Begriff oder eine Norm im Namen, bleibt der Name aus dem CAD."""
    info = info or einordnen(m) or {}
    name = re.sub(r"(?::\d+|<\d+>)$", "", str(m.get("bauteil") or "").strip())
    if name and (info.get("norm") or begriff(name)[0]):
        return name
    return " ".join(x for x in (info.get("kategorie") or SONST, info.get("groesse") or groesse_gemessen(m)) if x)


def status(m, gewaehlt):
    """Status in der Liste: 'ins Angebot' (angehakt), 'nicht übernommen', 'Vorschlag' (noch Fertigungsteil)."""
    if not m.get("_normteil"):
        return "Vorschlag"
    return "ins Angebot" if gewaehlt else "nicht übernommen"


def annehmen(m, info=None):
    """Vorschlag annehmen: das Teil wird Zukaufteil (Normteil) mit Kategorie und Bezeichnung; bleibt beim
    Kundenwechsel erhalten (_zukauf_hand)."""
    info = info or m.get("_zukaufteil") or einordnen(m) or dict(kategorie=SONST)
    m["_normteil"] = m["_zukauf_hand"] = info["kategorie"]
    m["_normteil_bezeichnung"] = bezeichnung(m, info)
    m["_zukaufteil"] = dict(info, vertrauen=SICHER, grund=(info.get("grund") or "") + "; von Hand bestätigt")
    return m


def ablehnen(m):
    """Von Hand angenommenes Zukaufteil wieder Fertigungsteil."""
    if m.get("_zukauf_hand"):
        for k in ("_normteil", "_zukauf_hand", "_normteil_bezeichnung"):
            m.pop(k, None)
        m["_zukaufteil"] = einordnen(m)
    return m


def anwenden(m, eingebaut=True):
    """Einordnung in den Messwert schreiben (_zukaufteil). Ist das Teil noch kein Normteil (Begriff der eigenen
    Liste, Form), macht eine sichere oder wahrscheinliche Einordnung eines daraus (_normteil = Kategorie); mit
    eingebaut=False (Einstellung step_zukauf_begriffe aus) bleibt es beim Vorschlag. Ergebnis: True = Normteil."""
    if m.get("_zukauf_hand"):
        m["_normteil"] = m["_zukauf_hand"]
        return True
    info = einordnen(m)
    if m.get("_normteil") and (info is None or info["vertrauen"] == VORSCHLAG):
        # Begriff der eigenen Liste (Einstellungen, Importprofil) ohne bekannte Norm oder eingebauten Begriff
        info = dict(info or dict(kategorie=SONST, norm="", groesse=groesse_gemessen(m), groesse_quelle="gemessen"),
                    vertrauen=WAHRSCHEINLICH, grund=f"Begriff „{m['_normteil']}“ aus der Normteil-Liste")
    if info is None:
        m.pop("_zukaufteil", None)
        return False
    if not m.get("_normteil") and info["vertrauen"] != VORSCHLAG:
        if eingebaut:
            m["_normteil"] = info["kategorie"]
        else:
            info = dict(info, vertrauen=VORSCHLAG, grund=info["grund"] + " (eingebaute Erkennung ist ausgeschaltet)")
    m["_zukaufteil"] = info
    return bool(m.get("_normteil"))


def hinweis(m):
    """Text für die Hinweis-Spalte des Prüfdialogs oder ''."""
    info = m.get("_zukaufteil")
    if not info:
        return ""
    teile = [info["kategorie"]] + [x for x in (info.get("norm"), info.get("groesse")) if x]
    if info["vertrauen"] == VORSCHLAG:
        return (f"Könnte ein Zukaufteil sein ({' '.join(teile)}; {info['grund']}): bleibt Fertigungsteil, annehmen "
                "über „Zukaufteile …“")
    return f"Zukaufteil {' '.join(teile)} ({info['vertrauen']}: {info['grund']})"


def liste(messwerte, gruppen=None, gewaehlt=None):
    """Zeilen der Zukaufteil-Liste: je Gruppe gleicher Teile dict(indizes, datei, bezeichnung, kategorie, norm,
    groesse, groesse_quelle, anzahl, grund, vertrauen, status). gruppen: Listen von Indizes gleicher Teile (ohne:
    jedes Teil einzeln); gewaehlt(i) -> angehakt."""
    gruppen = gruppen if gruppen is not None else [[i] for i in range(len(messwerte))]
    out = []
    for g in gruppen:
        m = messwerte[g[0]]
        info = m.get("_zukaufteil")
        if not info or m.get("fehler"):
            continue
        an = bool(gewaehlt(g[0])) if gewaehlt else m.get("_uebernehmen") is True
        if m.get("_normteil"):
            from .step import normteil_name
            name = normteil_name(m)
        else:
            name = bezeichnung(m, info)
        out.append(dict(indizes=list(g), datei=m.get("datei"), bezeichnung=name, kategorie=info["kategorie"],
                        norm=info.get("norm") or "", groesse=info.get("groesse") or "",
                        groesse_quelle=info.get("groesse_quelle") or "", anzahl=len(g), grund=info["grund"],
                        vertrauen=info["vertrauen"], status=status(m, an)))
    out.sort(key=lambda z: (KATEGORIEN.index(z["kategorie"]), z["bezeichnung"].casefold()))
    return out
