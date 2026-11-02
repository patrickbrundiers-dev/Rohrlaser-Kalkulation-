"""Vier-Augen-Freigabe (Vorschlag H2a, 02.11.2026, Vorgabe aus).

Einstellungen „Vier-Augen-Freigabe ab Netto [€]“ und „… unter Marge“ (je 0 = aus): ein Angebot darüber bzw. darunter
braucht vor dem Angebots-PDF die Freigabe eines Admins. Die Freigabe steht im Angebot (Zusatzdaten 'freigabe': wer,
wann, Netto) und im Versandverlauf (art 'freigabe'). Ändert sich der Netto-Preis danach um mehr als TOLERANZ, gilt sie
nicht mehr. Ohne Qt."""
import datetime

TOLERANZ = 0.005        # 0,5 %


def _n(w):
    try:
        return float(w) if w not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def marge(summen):
    """Marge am Warenwert wie im Angebots-Check: (Gewinn + Anhebung) ÷ (Selbstkosten + Gewinn + Anhebung)."""
    gewinn, selbst = _n(summen.get("gewinn")), _n(summen.get("selbst"))
    anhebung = _n(summen.get("mindestpreis_anhebung")) * (1 - _n(summen.get("skonto_satz")) / 100)
    basis = selbst + gewinn + anhebung
    return (gewinn + anhebung) / basis if basis > 0 else None


def noetig(summen, einst):
    """Grund, warum eine Freigabe nötig ist, oder None."""
    from .stammdaten import zahl_als_text as zahl
    ab, unter = _n(einst.get("freigabe_ab")), _n(einst.get("freigabe_marge"))
    netto = _n(summen.get("verkauf"))
    if ab > 0 and netto > ab:
        return f"Netto {zahl(netto, 2)} € über {zahl(ab, 2)} €"
    m = marge(summen)
    if unter > 0 and m is not None and m < unter:
        return f"Marge {zahl(100 * m, 1)} % unter {zahl(100 * unter, 1)} %"
    return None


def gueltig(eintrag, summen):
    """Freigabe vorhanden und Netto seitdem nicht mehr als TOLERANZ geändert."""
    if not eintrag or not eintrag.get("netto"):
        return False
    netto = _n(summen.get("verkauf"))
    return abs(netto - eintrag["netto"]) <= TOLERANZ * max(abs(eintrag["netto"]), 1.0)


def eintrag(wer, summen, grund, jetzt=None):
    jetzt = jetzt or datetime.datetime.now()
    return dict(art="freigabe", wer=wer or "Admin", am=jetzt.isoformat(timespec="minutes"),
                datum=jetzt.date().isoformat(), netto=round(_n(summen.get("verkauf")), 2), grund=grund)


def text(e):
    if not e:
        return ""
    am = str(e.get("am") or "")[:16].replace("T", " ")
    return f"Freigegeben von {e.get('wer')} am {am} ({e.get('grund') or ''})".strip()
