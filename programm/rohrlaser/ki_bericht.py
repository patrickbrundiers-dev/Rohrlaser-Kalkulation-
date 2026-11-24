"""KI-Plattform Phase 5: Kalkulationsbericht / vollständige technische und kaufmännische Angebotsprüfung als Text und
PDF (Master-Prompt Patrick 20.11.2026, Punkt 9 „Automatische Erstellung von Kalkulationsberichten“). Inhalt sind die
Befunde der Agenten (ki_agenten.pruefen) mit Quelle und Datenstand, gegliedert nach Fachgebiet; keine Zahl kommt
aus einem Sprachmodell. Ohne Qt."""
import datetime

from . import ki_agenten as ag

ZEICHEN = {ag.FEHLER: "Fehler", ag.WARNUNG: "Warnung", ag.VORSCHLAG: "Vorschlag", ag.HINWEIS: "Hinweis",
           ag.INFO: "Kennzahl"}
ERSETZEN = {"÷": ":", "→": "->", "✗": "x", "✓": "ok", "×": "x", "–": "-", "„": '"', "“": '"', "…": "...", "≤": "<=",
            "≥": ">=", "±": "+/-", "₂": "2"}


def gliedern(befunde):
    """{Agent: [Befunde]} in der Reihenfolge der Agenten."""
    out = {a.titel: [] for a in ag.AGENTEN}
    for b in befunde:
        out.setdefault(b["agent"], []).append(b)
    return {k: v for k, v in out.items() if v}


def text(ergebnis, kopf=None, jetzt=None):
    """Bericht als Klartext."""
    kopf = kopf or {}
    jetzt = jetzt or datetime.datetime.now()
    b = ergebnis["befunde"]
    zeilen = [f"Technische und kaufmännische Angebotsprüfung – Angebot {kopf.get('nummer') or ''} "
              f"{kopf.get('kunde') or ''}".rstrip(),
              f"Erstellt {jetzt.strftime('%d.%m.%Y %H:%M')} von der KI-Plattform (regelbasiert, Zahlen aus der "
              "Kalkulation des Programms)",
              f"{len(b)} Befunde: " + ", ".join(f"{sum(1 for x in b if x['art'] == a)} {ZEICHEN[a]}"
                                                for a in ag.ARTEN if any(x["art"] == a for x in b)), ""]
    for agent, liste in gliedern(b).items():
        zeilen.append(agent)
        for x in liste:
            zeilen.append(f"  [{ZEICHEN.get(x['art'], x['art'])}] {x['text']}  (Quelle: {x['quelle'] or '–'})")
        zeilen.append("")
    if ergebnis.get("fehler"):
        zeilen.append("Nicht verfügbar: " + "; ".join(f"{q}: {t}" for q, t in ergebnis["fehler"]))
    return "\n".join(zeilen)


def _latin(t):
    for a, b in ERSETZEN.items():
        t = t.replace(a, b)
    return t.encode("latin-1", "replace").decode("latin-1")


def pdf(ergebnis, pfad, kopf=None, jetzt=None):
    """Bericht als PDF (reportlab, Standardschrift)."""
    from xml.sax.saxutils import escape
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    st = getSampleStyleSheet()
    teile = text(ergebnis, kopf, jetzt).split("\n")
    doc = SimpleDocTemplate(str(pfad), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=_latin(teile[0]))
    inhalt = [Paragraph(escape(_latin(teile[0])), st["Title"]), Paragraph(escape(_latin(teile[1])), st["Normal"]),
              Paragraph(escape(_latin(teile[2])), st["Normal"]), Spacer(1, 6 * mm)]
    agenten = set(gliedern(ergebnis["befunde"]))
    for z in teile[3:]:
        if not z.strip():
            inhalt.append(Spacer(1, 2 * mm))
        elif z in agenten:
            inhalt.append(Paragraph(escape(_latin(z)), st["Heading3"]))
        else:
            inhalt.append(Paragraph(escape(_latin(z.strip())), st["BodyText"]))
    doc.build(inhalt)
    return pfad
