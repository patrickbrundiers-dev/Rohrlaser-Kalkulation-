"""Übergabe an das Rohr-CAM (Vorschlag S4, Patrick 02.11.2026 „S4b“: erst der allgemeine Ordner, CAM-Format später).

Ein Ordner je Angebot (z. B. „2026-00517_CAM“) neben den Angebotsdateien:
- je Rohrlaserteil bzw. Blech eine STEP-Datei „Artikel_Stück_Werkstoff.stp“, gebaut wie „STEP speichern“ im Editor
  (step_export: Teil im eigenen System, Ende A bei Z = 0, Konturen aus den Eingaben der Position, die aus der STEP
  kommen; nichts verschoben). Biegerohre, virtuelle Bauteile und Teile ohne Eingaben bekommen keine eigene Datei,
  dafür liegen die Kundendateien unverändert im Unterordner „Kundendateien“.
- Stueckliste.csv (Semikolon, UTF-8 mit BOM für Excel): Pos., Artikel, Bezeichnung, Profil, Werkstoff, Länge,
  Stück, Stangenlänge, Schweißnaht, Gravur, STEP-Datei, Geometrie. Positionen „nur kalkuliert“ (geometrie.py, aus
  PDF-Zeichnung oder Schnellpreis) bekommen keine STEP-Datei, bis die Geometrie gesichert ist.
- Schnittplan.pdf: die Werkstattpapiere (Stangen mit Teilen), wenn der Schnittplan aktuell ist.
Der Ordner wird bei jedem Erstellen neu gefüllt (vorhandene Dateien gleichen Namens überschrieben)."""
import csv
import json
import re
import shutil
from pathlib import Path

from . import geometrie, rechnen

UNTERORDNER = "Kundendateien"


def ordnername(kopf):
    return re.sub(r'[<>:"/\\|?*]+', "_", f"{kopf.get('nummer') or 'Angebot'}_CAM")


def dateiname(p):
    """„Artikel_Stück_Werkstoff.stp“ ohne Zeichen, die Windows nicht erlaubt."""
    teile = [str(p.get("artikel") or f"Pos{p.get('pos') or ''}").strip(), str(int(p.get("stueck") or 0)),
             str(p.get("werkstoff_id") or "").strip()]
    return re.sub(r'[<>:"/\\|?*\s]+', "_", "_".join(t for t in teile if t)) + ".stp"


def _naht(p):
    return " ".join(str(x) for x in (p.get("naht_vorgabe"), f"{p['naht_winkel']}°" if p.get("naht_winkel") not in
                                     (None, "") else None) if x)


def _gravur(p):
    from . import schneidweg as sw
    t = sw.lesen(p.get("technik")) or {}
    texte = [k.get("text") for k in t.get("konturen") or () if isinstance(k, dict) and k.get("art") == sw.TEXT_GRAVUR
             and k.get("text")]
    return "; ".join(texte)


def bauplan(p, kopf, k):
    """(Bauplan oder None, Hinweis) für die STEP-Datei einer Position."""
    from . import blech, schneidweg as sw, step_export, virtuell
    from .anbau import eingaben_mit_gravur
    name = step_export.teilname(p)
    if virtuell.ist_virtuell(virtuell.technik_lesen(p)):
        return None, f"{name}: virtuelles Bauteil, siehe Kundendatei"
    e_blech = blech.lesen(p.get("technik"))
    if e_blech:
        try:
            return step_export.blech_teil(e_blech, blech.zuschnitt(e_blech), name), ""
        except (ValueError, TypeError, ZeroDivisionError, KeyError) as f:
            return None, f"{name}: Blech nicht gebaut ({f})"
    e = sw.lesen(p.get("technik")) or {}
    if not e or e.get("biegerohr"):
        return None, f"{name}: {'Biegerohr' if e.get('biegerohr') else 'ohne Eingaben'}, siehe Kundendatei"
    pid = p.get("profil_id")
    if pid not in k.profile:
        return None, f"{name}: Profil {pid} nicht in den Stammdaten"
    profil = rechnen.profil_im_angebot(k.profile[pid], kopf, pid, p.get("werkstoff_id"), k)
    try:
        return step_export.rohr_teil(eingaben_mit_gravur(e, p), profil, p.get("laenge"), name,
                                     artikel=p.get("artikel"), gravur_h=p.get("bg_gravur")), ""
    except (ValueError, TypeError, ZeroDivisionError, KeyError) as f:
        return None, f"{name}: kein 3D-Modell aus den Eingaben ({f})"


def kundendateien(positionen, netze):
    """Pfade der Kundendateien (Mutter-STEP) der Positionen, die es noch gibt."""
    from .ansicht3d import entpacken
    out = []
    for p in positionen:
        n = entpacken(netze.get(p.get("id"))) if netze.get(p.get("id")) else None
        pfad = (n or {}).get("mutter")
        if pfad and Path(pfad).is_file() and pfad not in out:
            out.append(pfad)
    return out


def schreiben(ziel, kopf, positionen, ergebnis, k, tabellen, einst, netze=None, step=True, programmordner=None):
    """Ordner ziel füllen. netze = {Positions-ID: Netz} (Kundendateien), step=False ohne STEP-Dateien (Tests).
    Ergebnis dict(ordner, step=[Dateien], fehlen=[Hinweise], kunde=[Dateien], csv, pdf)."""
    from . import ausgabe, blech, pdf, step_export
    from .angebot import aktiv, kein_laserteil
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    teile = [p for p in positionen if aktiv(p) and (not kein_laserteil(p) or blech.lesen(p.get("technik")))]
    bericht = dict(ordner=str(ziel), step=[], fehlen=[], kunde=[], csv=None, pdf=None)
    namen = {}
    for p in teile:
        name = dateiname(p)
        if name in namen.values():
            name = name[:-4] + f"_Pos{p.get('pos')}.stp"
        namen[p.get("id")] = name
        if geometrie.nur_kalkuliert(p):
            # nur kalkuliert (PDF-Zeichnung, Schnellpreis): keine STEP aus unsicherer Geometrie (Plan PROfirst I3)
            bericht["fehlen"].append(geometrie.cam_hinweis(Path(name).stem))
            namen[p.get("id")] = ""
            continue
        if not step:
            continue
        plan, hinweis = bauplan(p, kopf, k)
        if plan is None:
            bericht["fehlen"].append(hinweis)
            namen[p.get("id")] = ""
            continue
        erg = step_export.schreiben([plan], ziel / name, programmordner, name=Path(name).stem)
        if erg.get("ok"):
            bericht["step"].append(name)
        else:
            bericht["fehlen"].append(f"{Path(name).stem}: {erg.get('fehler') or 'STEP nicht geschrieben'}")
            namen[p.get("id")] = ""
    with open(ziel / "Stueckliste.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Pos.", "Artikel", "Bezeichnung", "Profil", "Werkstoff", "Länge [mm]", "Stück", "Stangenlänge [mm]",
                    "Schweißnaht", "Gravur", "STEP-Datei", "Geometrie"])
        for p in teile:
            w.writerow([p.get("pos") or "", p.get("artikel") or "", p.get("bezeichnung") or "", p.get("profil_id") or "",
                        p.get("werkstoff_id") or "", str(p.get("laenge") or "").replace(".", ","),
                        int(p.get("stueck") or 0), rechnen.stange_wirksam(p, kopf) or "", _naht(p), _gravur(p),
                        namen.get(p.get("id")) or "", geometrie.wert(p)])
    bericht["csv"] = "Stueckliste.csv"
    if ergebnis and ergebnis.get("stangen"):
        wp = ausgabe.werkstatt(kopf, positionen, ergebnis, k, tabellen)
        pdf.werkstatt_pdf(ziel / "Schnittplan.pdf", kopf, wp, True, einst)
        bericht["pdf"] = "Schnittplan.pdf"
    kd = kundendateien(positionen, netze or {})
    if kd:
        (ziel / UNTERORDNER).mkdir(exist_ok=True)
        for pfad in kd:
            shutil.copy2(pfad, ziel / UNTERORDNER / Path(pfad).name)
            bericht["kunde"].append(Path(pfad).name)
    (ziel / "Inhalt.json").write_text(json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")
    return bericht


def text(b):
    """Meldung nach dem Erstellen."""
    t = (f"Übergabe an CAM: {len(b['step'])} STEP-Datei(en), Stückliste"
         + (", Schnittplan" if b.get("pdf") else "") + (f", {len(b['kunde'])} Kundendatei(en)" if b["kunde"] else "")
         + f" in {b['ordner']}.")
    if b["fehlen"]:
        t += f" Ohne eigene STEP: {'; '.join(b['fehlen'][:3])}" + (" …" if len(b["fehlen"]) > 3 else "")
    return t
