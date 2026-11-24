"""Rückfrage nachfassen (Patrick 23.11.2026 „Weiter erweitern und verbessern“, Stufe 2 Punkt 1).

Eine Rückfrage an den Kunden (ak.RUECKFRAGE, „wartet auf Kunde“) ohne Antwort nach TAGE Arbeitstagen (Einstellung,
Vorgabe VORGABE; 0 = aus) ist „nachzufassen“: Hinweis in der Akte, Schnellfilter „Nachfassen“, tägliche Erinnerung.
„Erinnerung …“ öffnet eine Antwort in Outlook mit den Fragen der Rückfrage (nie automatisch gesendet) und vermerkt
die Rückfrage neu (Ereignis RUECKFRAGE mit nachfassen=True: die Wartezeit läuft neu, gezählt in stand „nachgefasst“).

Was die Antwort liefert (geliefert): die Rückfrage merkt die fehlenden Angaben (Ereignis-Feld fehlt); kam danach
eine Antwort, wird verglichen, was jetzt nicht mehr fehlt und was weiter fehlt. Nur Anzeige, nichts wird übernommen.
Ohne Qt."""
import datetime

from . import anfragen_akten as ak

TAGE = "anfragen_nachfassen_tage"
VORGABE = 3


def tage(db):
    try:
        v = db.einstellung(TAGE)
    except Exception:                   # noqa: BLE001 – ohne Einstellung: Vorgabe
        v = None
    if v in (None, ""):
        return VORGABE
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return VORGABE


def stand(akte, tage_, jetzt=None, land=None):
    """None (keine offene Rückfrage, erledigt oder aus) oder dict(seit, faellig (date), faellig_ist (bool),
    nachgefasst (Anzahl), text)."""
    from . import feiertage
    s = akte.stand
    if not tage_ or akte.status == ak.ERLEDIGT or akte.aussortiert or not s.get("rueckfrage"):
        return None
    seit = ak._datum(s["rueckfrage"])
    if not seit:
        return None
    jetzt = jetzt or datetime.datetime.now()
    faellig = feiertage.arbeitstage_spaeter(seit.date(), int(tage_), land)
    ist = jetzt.date() >= faellig
    n = int(s.get("nachgefasst") or 0)
    text = (f"Rückfrage vom {seit:%d.%m.} ohne Antwort" + (f", schon {n}× erinnert" if n else "")
            if ist else f"Rückfrage vom {seit:%d.%m.}, nachfassen ab {faellig:%d.%m.}")
    return dict(seit=seit, faellig=faellig, faellig_ist=ist, nachgefasst=n, text=text)


def _fragen(text):
    """Die Fragezeilen („- …“) einer Rückfrage; ohne solche Zeilen der ganze Text (ohne Anrede und Gruß)."""
    zeilen = [z.strip() for z in str(text or "").splitlines()]
    fragen = [z for z in zeilen if z.startswith("- ") and len(z) > 2]
    if fragen:
        return fragen
    return [z for z in zeilen if z and not z.lower().startswith(("sehr geehrte", "hallo", "guten tag", "mit freund",
                                                                 "vielen dank", "viele grüße"))][:12]


def erinnerung_text(kunde, akte, absender=""):
    """Text der Erinnerung: Anrede, Bezug auf die Rückfrage vom …, ihre Fragen, Gruß (Signatur setzt Outlook)."""
    from . import angebot_mail
    s = akte.stand
    seit = ak._datum(s.get("rueckfrage") or "")
    betreff = akte.betreff or "Ihre Anfrage"
    zeilen = [angebot_mail.anrede(kunde), "",
              f"zu Ihrer Anfrage „{betreff}“ hatten wir Sie" + (f" am {seit:%d.%m.%Y}" if seit else "")
              + " um folgende Angaben gebeten:", ""]
    zeilen += _fragen(s.get("rueckfrage_text")) or ["- "]
    zeilen += ["", "Sobald uns die Angaben vorliegen, erstellen wir Ihnen gern das Angebot.", "",
               "Mit freundlichen Grüßen"]
    if absender:
        zeilen.append(absender)
    return "\n".join(zeilen)


def geliefert(akte, fehlt_jetzt):
    """Nach der Antwort auf eine Rückfrage: (geliefert, fehlt weiter) als Schlüssel von anfrage_erkennung.FEHLT, oder
    None (keine beantwortete Rückfrage mit gemerkten Angaben)."""
    s = akte.stand
    alt = list(s.get("rueckfrage_fehlt") or [])
    if s.get("rueckfrage") or not alt or not s.get("antwort_am"):
        return None
    jetzt = set(fehlt_jetzt or ())
    return [k for k in alt if k not in jetzt], [k for k in alt if k in jetzt]


KURZ = dict(werkstoff="Werkstoff", werkstoff_unsicher="Werkstoff", termin="Wunschtermin", menge="Stückzahl",
            zeichnung="Zeichnung/STEP", step="STEP-Datei")


def _namen(schluessel):
    return ", ".join(dict.fromkeys(KURZ.get(k, k) for k in schluessel))


def geliefert_text(gl):
    if not gl:
        return ""
    ja, nein = gl
    teile = []
    if ja:
        teile.append(f"Die Antwort liefert: {_namen(ja)}")
    if nein:
        teile.append(f"fehlt weiter: {_namen(nein)}")
    return " · ".join(teile)
