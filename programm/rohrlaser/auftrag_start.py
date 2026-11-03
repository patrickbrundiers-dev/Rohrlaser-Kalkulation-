"""Auftrag starten in einem Schritt (Automationen 03.11.2026, Vorschlag 2a).

Im Fenster „Beauftragt“ (auftrag.py) und „Bestellung prüfen“ stehen Häkchen für die Schritte nach dem Auftrag;
das Programm merkt sie je Arbeitsplatz (Einstellung auftrag_schritte). Nach OK erledigt es die gewählten Schritte
nacheinander im Angebot und meldet danach in einer Einblendung, was entstanden ist (Bericht mit den Dateien). Ein
Schritt, der nicht geht (z. B. nicht optimiert, keine Freigabe), hält die übrigen nicht auf. Gesendet wird weiter
nur in Outlook. Die Logik ohne Qt; ausfuehren() arbeitet auf der Angebotsseite."""

SCHRITTE = (("ab", "Auftragsbestätigung (PDF)"),
            ("material", "Materialbestellung beim gewählten Lieferanten (E-Mail-Entwurf)"),
            ("werkstatt", "Werkstattpapiere (PDF)"),
            ("cam", "Übergabe an CAM (Ordner mit STEP, Stückliste, Schnittplan)"),
            ("etiketten", "Etiketten mit QR-Code (PDF)"))
NAMEN = dict(SCHRITTE)
EINSTELLUNG = "auftrag_schritte"


def gewaehlt(db):
    """Gemerkte Schritte (Reihenfolge wie SCHRITTE)."""
    w = set(str(db.einstellung(EINSTELLUNG) or "").replace(",", " ").split())
    return [s for s, _ in SCHRITTE if s in w]


def merken(db, schritte):
    if getattr(db, "nur_lesen", None):
        return
    try:
        db.einstellung_setzen(EINSTELLUNG, " ".join(s for s, _ in SCHRITTE if s in set(schritte)))
    except Exception:
        pass


def ausfuehren(f, angebot_id, schritte):
    """Schritte auf der Angebotsseite ausführen. Ergebnis: [(Schritt, Ergebnis oder None, Text)]."""
    from . import automatik
    schritte = [s for s, _ in SCHRITTE if s in set(schritte or ())]
    if not schritte:
        return []
    seite = f.angebot_oeffnen(angebot_id)
    if seite is None:
        return []
    if any(s in ("material", "werkstatt", "cam", "etiketten") for s in schritte) \
            and seite.stand_optimierung() != "aktuell":
        try:
            seite.optimieren()
        except Exception:
            pass
    out = []
    for s in schritte:
        try:
            if s == "ab":
                erg = seite.auftragsbestaetigung_pdf()
            elif s == "material":
                erg = seite.material_anfragen(bestellung=True)
                erg = erg if erg is not None and getattr(erg, "ergebnis", None) else None
            elif s == "werkstatt":
                erg = seite.werkstatt_pdf()
            elif s == "cam":
                erg = seite.cam_paket()
            else:
                erg = seite.etiketten_pdf()
        except Exception as e:          # ein Schritt hält die anderen nicht auf
            erg, fehler = None, str(e)
        else:
            fehler = ""
        out.append((s, erg, NAMEN[s] + (": erledigt" if erg else ": nicht erstellt" + (f" ({fehler})" if fehler
                                                                                    else ""))))
    kopf = f.db.angebot(angebot_id) or {}
    automatik.merken(f.db, "auftrag", f"Angebot {kopf.get('nummer')}: " + "; ".join(t for _, _, t in out),
                     angebot_id)
    fertig = sum(1 for _, e, _ in out if e)
    f.meldung(f"Auftrag {kopf.get('nummer')} gestartet: {fertig} von {len(out)} Schritten erledigt.",
              fehler=fertig < len(out), bericht=("Auftrag starten", "\n".join(t for _, _, t in out)))
    return out
