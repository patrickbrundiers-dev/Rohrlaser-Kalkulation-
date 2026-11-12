"""Teilebilder beim Auftrag (Plan PROfirst-/LogiTRACE-Handbücher 12.11.2026, G4).

Wird ein Angebot beauftragt (Schritt „Teilebilder je Position“ im Fenster Beauftragt, auftrag_start.py) oder von Hand
(Kontextmenü Ausgabe), legt das Programm im Angebotsordner den Unterordner „<Nr> Teilebilder“ an: je Position mit 3D-Netz
(STEP-Import, Editoren) ein PNG der 3D-Ansicht schräg von vorn oben, Name „Pos 10 AB-10.png“. Für Werkstatt, ERP und
Rückfragen; ändert nichts am Angebot. Positionen ohne 3D-Netz (von Hand eingegeben) fehlen und werden gemeldet."""
import re
from pathlib import Path

BREITE, HOEHE = 900, 420


def dateiname(p):
    pos = p.get("pos")
    pos = int(pos) if isinstance(pos, float) and pos.is_integer() else pos
    s = f"Pos {pos if pos not in (None, '') else '?'} {p.get('artikel') or p.get('bezeichnung') or ''}".strip()
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", s) + ".png"


def schreiben(ordner, positionen, netze, breite=BREITE, hoehe=HOEHE):
    """PNG je Position mit Netz. netze = {Positions-ID: gepackte Netz-Bytes} (Datenbank.netze). Ergebnis:
    dict(ordner, dateien=[Pfade], ohne=[Positionen ohne Netz])."""
    from .ansicht3d import entpacken, vorschaubild
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    dateien, ohne = [], []
    for p in positionen:
        roh = (netze or {}).get(p.get("id"))
        netz = entpacken(roh) if roh else None
        pix = vorschaubild(netz, breite, hoehe, 1.0) if netz else None
        if pix is None:
            ohne.append(str(p.get("pos") or p.get("artikel") or "?"))
            continue
        ziel = ordner / dateiname(p)
        if pix.save(str(ziel), "PNG"):
            dateien.append(ziel)
    return dict(ordner=ordner, dateien=dateien, ohne=ohne)


def text(bericht):
    t = f"Teilebilder: {len(bericht['dateien'])} PNG in „{Path(bericht['ordner']).name}“"
    if bericht["ohne"]:
        t += f"; ohne 3D-Ansicht: Pos. {', '.join(bericht['ohne'][:10])}{' …' if len(bericht['ohne']) > 10 else ''}"
    return t + "."
