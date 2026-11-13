"""Teilbestell-Risiko (Roadmap Kalkulation Phase 2, OFFER-003; Freigabe Patrick 13.11.2026 „Ganze Phase 2 nach
Empfehlung“).

Alle Positionen eines Angebots werden gemeinsam optimiert und kalkuliert: sie teilen sich Stangen, das Rüsten der
Maschine, Programmier- und Pauschalkosten und den Mindestauftragswert. Bestellt der Kunde nur einen Teil, war der Preis
zu niedrig. Hier wird jede Position bzw. jeder Satz zusätzlich allein gerechnet, genau wie eine Staffelstufe mit nur
diesem Satz bzw. dieser Position (staffeln.stufe_rechnen), und mit dem Stückpreis im Angebot verglichen.

Einstellung 'teilbestell_schwelle' [%]: ab dieser Abweichung nennt der Angebots-Check die Position; 0 = aus (Vorgabe).
„Erledigen“ setzt im Angebot den Haken „Vorbehalt bei Teilbestellung“: das Angebots-PDF nennt dann unter den
Bedingungen den Text der Einstellung 'teilbestell_text' (leer = TEXT). Kein Preis ändert sich von selbst. Ohne Qt."""
from .angebot import aktiv as position_aktiv
from .stammdaten import zahl_als_text as zahl

TEXT = ("Die Preise gelten bei Bestellung aller angebotenen Positionen in den genannten Mengen; bei einer "
        "Teilbestellung behalten wir uns eine Neuberechnung vor.")
HOECHSTENS = 12             # so viele Sätze bzw. Positionen werden allein gerechnet (je eine Optimierung)
ZIEL_PREFIX = "pos:"


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def schwelle(einst):
    """Schwelle in % (0 = aus)."""
    return max(0.0, _n((einst or {}).get("teilbestell_schwelle")))


def text(einst):
    """Text des Vorbehalts im Angebots-PDF."""
    t = str((einst or {}).get("teilbestell_text") or "").strip()
    return t or TEXT


def schluessel(positionen):
    """[(Schlüssel, Menge, [Indizes], ist_satz)]: je Satz bzw. Position ohne Satz eine Zeile (wie die Staffeln)."""
    from .staffeln import je_satz, txt
    out, saetze = [], {}
    for i, p in enumerate(positionen):
        if not position_aktiv(p) or _n(p.get("stueck")) <= 0:
            continue
        s = txt(p.get("satz"))
        if s:
            saetze.setdefault(s, []).append(i)
        elif txt(p.get("pos")):
            out.append((txt(p.get("pos")), _n(p.get("stueck")), [i], False))
    for s, idx in saetze.items():
        menge = max(_n(positionen[i].get("stueck")) / je_satz(positionen[i]) for i in idx)
        out.append((s, max(1, int(menge + 0.5)), idx, True))
    return out


def preis_im_angebot(positionen, kalk_zeilen, idx, ist_satz):
    """Preis je Stück bzw. Satz im gemeinsam gerechneten Angebot."""
    from .staffeln import je_satz
    if ist_satz:
        return sum(_n((kalk_zeilen[i] or {}).get("preis_teil")) * je_satz(positionen[i]) for i in idx)
    return _n((kalk_zeilen[idx[0]] or {}).get("preis_teil"))


def rechnen(kopf, positionen, kalk_zeilen, k, tabellen, einst, hoechstens=HOECHSTENS):
    """Je Satz bzw. Position: dict(schluessel, menge, satz, zeile, angebot, allein, pct) mit den Preisen je Einheit;
    allein = None, wenn der Lauf einen Fehler hatte. Leer bei weniger als zwei Sätzen/Positionen (kein Risiko)."""
    from .staffeln import stufe_rechnen
    liste = schluessel(positionen)
    if len(liste) < 2 or not kalk_zeilen:
        return []
    out = []
    for schl, menge, idx, ist_satz in liste[:hoechstens]:
        im = preis_im_angebot(positionen, kalk_zeilen, idx, ist_satz)
        try:
            x = stufe_rechnen(kopf, positionen, schl, menge, k, tabellen, einst)
        except Exception:       # noqa: BLE001 – nur Hinweis: ein Fehler im Lauf nennt die Position nicht
            x = None
        allein = _n(x.get("preis_gesamt")) / menge if x and x.get("preis_gesamt") is not None and menge else None
        pct = 100.0 * (allein - im) / im if allein is not None and im > 0 else None
        out.append(dict(schluessel=schl, menge=menge, satz=ist_satz, zeile=idx[0], angebot=im, allein=allein,
                        pct=pct))
    return out


def ueber_schwelle(ergebnis, grenze):
    return [r for r in ergebnis if r["pct"] is not None and grenze > 0 and r["pct"] >= grenze]


def punkte(kopf, positionen, kalk_zeilen, k, tabellen, einst):
    """HINWEIS-Punkte für den Angebots-Check (nur mit Schwelle > 0); Aktion 'teilbestell' setzt den Vorbehalt."""
    from . import angebot_check
    grenze = schwelle(einst)
    if not grenze:
        return []
    treffer = ueber_schwelle(rechnen(kopf, positionen, kalk_zeilen, k, tabellen, einst), grenze)
    if not treffer:
        return []
    vorbehalt = (kopf or {}).get("teilbestell_vorbehalt") == "ja"
    out = []
    for r in sorted(treffer, key=lambda r: -r["pct"]):
        einheit = "Satz" if r["satz"] else "Stück"
        name = f"Satz {r['schluessel']}" if r["satz"] else f"Pos. {r['schluessel']}"
        t = (f"Teilbestell-Risiko {name}: allein bestellt {zahl(r['allein'], 2)} € statt {zahl(r['angebot'], 2)} € "
             f"je {einheit} (+{zahl(r['pct'], 0)} %)")
        t += " – Vorbehalt steht im Angebot" if vorbehalt else " – Vorbehalt ins Angebot oder Einzelpreise prüfen"
        out.append(angebot_check.Punkt(
            angebot_check.HINWEIS, t, f"{ZIEL_PREFIX}{r['zeile']}",
            "Gerechnet wie eine Staffelstufe nur mit diesem Satz bzw. dieser Position: eigene Stangen, eigenes Rüsten, "
            "eigene Programmierung und Pauschalen, Mindestauftragswert. Schwelle: Einstellungen → Kalkulation "
            "„Teilbestell-Risiko ab [%]“.", aktion=None if vorbehalt else "teilbestell"))
    return out
