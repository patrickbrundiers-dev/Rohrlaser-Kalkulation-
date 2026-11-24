"""Kunde aus einer Anfrage-Mail (.msg/.eml): Daten auslesen, Kunden erkennen, mit dem Kundenstamm vergleichen,
ausgewählte Werte übernehmen oder neuen Kunden anlegen (Patrick 23.11.2026, Master-Auftrag „Outlook-.MSG-
Anfrageerkennung vollständig reparieren“). Ohne Qt; die Oberfläche steht in anfrage_kunde_dialog.py.

Grundregeln:
- Nie still überschreiben: übernommen werden nur Felder, die der Benutzer in der Gegenüberstellung
  „Feld | Datenbank | Neue E-Mail“ anhakt; jedes geänderte Feld wird gegen den gespeicherten Wert geprüft
  (kunden_daten.speichern, Konflikt mit Kollegen) und steht in der Kundenhistorie.
- Lieber zur Prüfung vorlegen als falsch zuordnen: erkennen() nennt Kandidaten mit Punkten und Gründen;
  „eindeutig“ nur bei genau passender Adresse bzw. USt-ID ohne zweiten Kandidaten.
- Neue Kunden über kunden_daten.anlegen (Kundennummer reserviert, Ansprechpartner, Dublettenprüfung).
"""
import re

from . import kunden_daten as kd
from . import mail

# ------------------------------------------------------------------ Auslesen
MOBIL = re.compile(r"(?:^|[\s|,;])(?:Mobil(?:telefon)?|Handy|Mobile|Cell|M)\.?\s*[:.]?\s*(\+?\d[\d \t/()\-.]{5,}\d)",
                   re.I | re.M)
TELEFON = re.compile(r"(?:^|[\s|,;])(?:Tel(?:efon)?|Fon|Phone|T)\.?\s*[:.]?\s*(\+?\d[\d \t/()\-.]{5,}\d)", re.I | re.M)
UST_ID = re.compile(r"(?:USt\.?[\s-]*Id(?:ent)?(?:[\s.-]*Nr)?\.?|UID(?:[\s-]*Nr)?\.?|VAT(?:[\s-]*(?:ID|No|Reg))?\.?|"
                    r"Umsatzsteuer[\s-]*(?:Id(?:entifikations)?)?(?:[\s-]*(?:nummer|Nr))?\.?)\s*[:.]?\s*"
                    r"([A-Z]{2}\s?[0-9A-Z](?:\s?[0-9A-Z]){7,11})", re.I)
UST_DE = re.compile(r"\bDE\s?\d{3}\s?\d{3}\s?\d{3}\b")
WEB = re.compile(r"\b(?:https?://)?(www\.[a-z0-9-]+(?:\.[a-z0-9-]+)+)\b", re.I)
POSITION_WORT = re.compile(r"(?:leiter|leitung|einkauf|vertrieb|technik|konstruktion|geschäftsführ|geschaeftsfuehr|"
                           r"inhaber|manager|meister|ingenieur|sachbearbeit|assistenz|projekt|arbeitsvorbereitung|"
                           r"purchas|buyer|engineer|sales|ceo|cto|prokurist|disposition|qualität|beschaffung)", re.I)


def _nummer(t):
    return re.sub(r"\s+", " ", str(t or "")).strip(" -/.")


def kontakt_aus_mail(m, eigene=(), formular_text=""):
    """Kundendaten aus Absender, Signatur und Formularkopf einer Mail: dict mit name, firmenzusatz (leer), strasse, plz,
    ort, land, telefon, email, website, ust_id und person (anrede, vorname, nachname, position, telefon, mobil, email).
    Nur gefundene Werte; nichts wird erfunden. None, wenn nichts Verwertbares da ist (z. B. nur interne Absender)."""
    basis = mail.kunde_daten(m, formular_text, eigene) if m is not None or formular_text else None
    if not basis:                       # z. B. Freemail ohne Signatur: wenigstens die Adresse (nichts erfinden)
        adr = mail.adressen(m, eigene) if m is not None else []
        if not adr:
            return None
        basis = dict(email=adr[0])
        if m.absender_name and "@" not in m.absender_name and mail._domain(m.absender) not in set(eigene or ()):
            basis["ansprechpartner"] = m.absender_name
    out = {n: basis[n] for n in ("name", "strasse", "plz", "land", "email") if basis.get(n)}
    if basis.get("plz_ort"):
        p, o = kd.plz_ort_teilen(basis["plz_ort"])
        out["plz"] = out.get("plz") or p
        if o:
            out["ort"] = o
    text = ""
    if m is not None:
        text = mail._signatur(mail._absender_text(m, set(eigene or ())))
    text = text + "\n" + "\n".join((formular_text or "").split("\n")[:30])
    t = re.sub(r"\s+[|•·]\s+", "\n", text)
    mm = MOBIL.search(t)
    mt = next((x for x in TELEFON.finditer(t) if not mm or x.start(1) != mm.start(1)), None)
    if mt:
        out["telefon"] = _nummer(mt.group(1))
    elif basis.get("telefon") and not (mm and kd._ziffern(basis["telefon"]) == kd._ziffern(mm.group(1))):
        out["telefon"] = basis["telefon"]
    u = UST_ID.search(t) or UST_DE.search(t)
    if u:
        w = kd._ust(u.group(1) if u.re is UST_ID else u.group(0))
        if re.fullmatch(r"[A-Z]{2}[0-9A-Z]{8,12}", w):
            out["ust_id"] = w
    web = WEB.search(t)
    if web:
        out["website"] = web.group(1).lower()
    elif out.get("email") and mail._domain(out["email"]) not in mail.FREEMAIL and "name" in out:
        pass                                         # keine Website erfinden (nur, wenn sie in der Mail steht)
    person = {}
    name = basis.get("ansprechpartner") or ""
    if name and not mail.ist_zentral(out.get("email", "")):
        anrede, vor, nach = kd.name_teilen(name)
        if "," in name and not vor:                  # „Muster, Erika“
            nach, _, vor = name.partition(",")
        person.update(anrede=anrede, vorname=(vor or "").strip(), nachname=(nach or name).strip())
        zeilen = [z.strip(" \t|•·-") for z in t.split("\n")]
        for i, z in enumerate(zeilen):
            if (person["nachname"] and person["nachname"] in z) and i + 1 < len(zeilen):
                kand = zeilen[i + 1]
                if kand and len(kand) <= 60 and not re.search(r"[@\d]", kand) and POSITION_WORT.search(kand) \
                        and not mail.FIRMA.search(kand):
                    person["position"] = kand
                break
        if out.get("email"):
            person["email"] = out["email"]
        if mm:
            person["mobil"] = _nummer(mm.group(1))
        if mt:
            person["telefon"] = out["telefon"]
        out["person"] = {k: v for k, v in person.items() if v}
    return out if out.get("name") or out.get("email") else None


# ------------------------------------------------------------------ Erkennen
EINDEUTIG, WAHRSCHEINLICH, UNSICHER = "eindeutig", "wahrscheinlich", "unsicher"
P_MAIL, P_UST = 100, 100


def erkennen(db, daten):
    """Kandidaten im Kundenstamm für Kundendaten aus der Mail: [dict(kundennr, name, punkte, gruende, person)],
    stärkste zuerst, mit stufe (eindeutig nur: genau gleiche E-Mail eines Kunden/Ansprechpartners oder gleiche
    USt-ID, und kein zweiter Kandidat mit ähnlich vielen Punkten). person = passender Ansprechpartner (id) oder None."""
    daten = dict(daten or {})
    p = daten.get("person") or {}
    such = dict(daten, ansprechpartner=[p] if p else [])
    kand = {}
    for k, gruende, punkte in kd.dubletten(db, such):
        kand[str(k["kundennr"])] = dict(kundennr=str(k["kundennr"]), name=k.get("name") or "", punkte=punkte,
                                        gruende=list(gruende))
    adresse = str(daten.get("email") or p.get("email") or "").lower()
    if adresse:
        for k in kd.mit_kontakten(db):
            if adresse in [x.lower() for x in kd.mails(k.get("email"))]:
                e = kand.setdefault(str(k["kundennr"]), dict(kundennr=str(k["kundennr"]), name=k.get("name") or "",
                                                             punkte=0, gruende=[]))
                e["punkte"] += P_MAIL
                e["gruende"].insert(0, f"E-Mail {adresse} steht beim Kunden")
                e["genau"] = True
    ust = kd._ust(daten.get("ust_id"))
    if ust:
        for k in db.zeilen("kunden"):
            if kd._ust(k.get("ust_id")) == ust:
                e = kand.setdefault(str(k["kundennr"]), dict(kundennr=str(k["kundennr"]), name=k.get("name") or "",
                                                             punkte=0, gruende=[]))
                if not any("USt" in g for g in e["gruende"]):
                    e["punkte"] += P_UST
                    e["gruende"].insert(0, f"USt-ID {ust} wie beim Kunden")
                e["genau"] = True
    liste = sorted(kand.values(), key=lambda x: (-x["punkte"], x["kundennr"]))
    for i, e in enumerate(liste):
        zweiter = liste[1]["punkte"] if len(liste) > 1 and i == 0 else 0
        if e.get("genau") and i == 0 and zweiter < e["punkte"] * 0.6:
            e["stufe"] = EINDEUTIG
        elif e["punkte"] >= 60:
            e["stufe"] = WAHRSCHEINLICH
        else:
            e["stufe"] = UNSICHER
        e["person"] = person_finden(db, e["kundennr"], p)
    return liste


def person_finden(db, kundennr, p):
    """id des Ansprechpartners, der zur Person aus der Mail passt (gleiche E-Mail, sonst gleicher Name), sonst None."""
    if not p:
        return None
    a = str(p.get("email") or "").lower()
    nach, vor = kd.falten(p.get("nachname")), kd.falten(p.get("vorname"))
    for x in kd.ansprechpartner(db, kundennr):
        if a and a in [y.lower() for y in kd.mails(x.get("email"))]:
            return x["id"]
    for x in kd.ansprechpartner(db, kundennr):
        if nach and kd.falten(x.get("nachname")) == nach and (not vor or not x.get("vorname")
                                                              or kd.falten(x.get("vorname")) == vor):
            return x["id"]
    return None


# ------------------------------------------------------------------ Gegenüberstellung
KUNDEN_FELDER = (("name", "Firmenname"), ("strasse", "Straße"), ("plz", "PLZ"), ("ort", "Ort"), ("land", "Land"),
                 ("telefon", "Telefon (Zentrale)"), ("email", "E-Mail (allgemein)"), ("website", "Website"),
                 ("ust_id", "USt-ID"))
PERSON_FELDER = (("anrede", "Anrede"), ("vorname", "Vorname"), ("nachname", "Nachname"), ("position", "Position"),
                 ("telefon", "Telefon"), ("mobil", "Mobil"), ("email", "E-Mail"))
GLEICH, NEU, ANDERS, NUR_DB = "gleich", "neu", "abweichend", "nur in der Datenbank"


def _gleich(feld, a, b):
    if feld in ("telefon", "mobil"):
        return kd._ziffern(a)[-8:] == kd._ziffern(b)[-8:]
    if feld == "ust_id":
        return kd._ust(a) == kd._ust(b)
    if feld == "email":
        return {x.lower() for x in kd.mails(a)} >= {x.lower() for x in kd.mails(b)} and bool(kd.mails(b))
    if feld == "name":
        return kd.namenskern(a) == kd.namenskern(b) and kd.falten(a) == kd.falten(b)
    if feld == "strasse":
        return kd._strasse(a) == kd._strasse(b)
    return kd.falten(a) == kd.falten(b)


def _zeile(bereich, feld, titel, db_wert, neu_wert):
    d, n = kd._t(db_wert), kd._t(neu_wert)
    if not n:
        status = NUR_DB if d else GLEICH
    elif not d:
        status = NEU
    else:
        status = GLEICH if _gleich(feld, d, n) else ANDERS
    # Vorschlag: neue Werte anhaken; abweichende nie vorab (der Benutzer entscheidet), E-Mail nur ergänzen
    return dict(bereich=bereich, feld=feld, titel=titel, db=d, mail=n, status=status, vorschlag=status == NEU)


def vergleich(db, kundennr, daten, person_id=None):
    """Zeilen der Gegenüberstellung: [dict(bereich 'kunde'|'person', feld, titel, db, mail, status, vorschlag)].
    status: gleich, neu (nur in der Mail), abweichend, nur in der Datenbank. person_id: Ansprechpartner zum
    Vergleich (None: neuer Ansprechpartner, alle Werte der Mail neu)."""
    k = kd.kunde(db, kundennr)
    if k is None:
        raise kd.KundenFehler(f"Kunde {kundennr} gibt es nicht (mehr).")
    daten = daten or {}
    zeilen = [_zeile("kunde", f, t, k.get(f), daten.get(f)) for f, t in KUNDEN_FELDER]
    p = daten.get("person") or {}
    if p:
        alt = next((x for x in kd.ansprechpartner(db, kundennr) if x["id"] == person_id), {}) if person_id else {}
        zeilen += [_zeile("person", f, t, alt.get(f), p.get(f)) for f, t in PERSON_FELDER]
    return zeilen


def uebernehmen(db, kundennr, zeilen, auswahl, person_id=None, daten=None):
    """Angehakte Felder (auswahl: {(bereich, feld)}) in den Kunden bzw. Ansprechpartner schreiben. Kunde: nur diese
    Felder, geprüft gegen den Stand beim Vergleich (Konflikt, wenn ein Kollege sie inzwischen geändert hat);
    E-Mail wird ergänzt, nicht ersetzt. Ansprechpartner: person_id ändern bzw. neu anlegen, wenn Personenfelder
    angehakt sind. Ergebnis: dict(kunde=[geänderte Titel], person=id oder None, neu_person=bool)."""
    auswahl = {tuple(x) for x in auswahl or ()}
    neu, alt = {}, {}
    for z in zeilen:
        if z["bereich"] != "kunde" or ("kunde", z["feld"]) not in auswahl or not z["mail"]:
            continue
        wert = z["mail"]
        if z["feld"] == "email" and z["db"]:
            wert = "; ".join(dict.fromkeys(kd.mails(z["db"]) + kd.mails(z["mail"])))
        neu[z["feld"]], alt[z["feld"]] = wert, z["db"] or None
    erg = dict(kunde=[], person=person_id, neu_person=False)
    if neu:
        if "plz" in neu or "ort" in neu:          # plz_ort mitführen (für Angebote/Altdaten)
            k = kd.kunde(db, kundennr) or {}
            for f in ("plz", "ort"):
                if f not in neu:
                    neu[f] = alt[f] = k.get(f)
        erg["kunde"] = kd.speichern(db, kundennr, neu, alt)
    pz = {z["feld"]: z["mail"] for z in zeilen if z["bereich"] == "person" and ("person", z["feld"]) in auswahl
          and z["mail"]}
    if pz:
        if person_id:
            p = next((x for x in kd.ansprechpartner(db, kundennr) if x["id"] == person_id), None)
            if p is None:
                raise kd.KundenFehler("Der Ansprechpartner wurde inzwischen gelöscht.")
            vorher = {z["feld"]: z["db"] for z in zeilen if z["bereich"] == "person"}
            for f in pz:                            # Konflikt: gespeicherter Wert anders als beim Vergleich
                if kd._t(p.get(f)) != kd._t(vorher.get(f)):
                    from .datenbank import AenderungsKonflikt
                    raise AenderungsKonflikt("kunden_ansprechpartner", person_id, f, p.get(f), pz[f])
            kd.person_speichern(db, kundennr, dict(p, **pz), person_id)
        else:
            p = dict((daten or {}).get("person") or {})
            p.update(pz)
            p.setdefault("aktiv", "ja")
            if not kd.ansprechpartner(db, kundennr):
                p["haupt"] = "ja"
            erg["person"] = kd.person_speichern(db, kundennr, p)
            erg["neu_person"] = True
    return erg


# ------------------------------------------------------------------ Neuer Kunde aus der Mail
def vorschlag_neu(daten):
    """Vorbelegung der Eingabemaske „Neuen Kunden anlegen“ aus den Maildaten."""
    d = dict(daten or {})
    p = d.pop("person", None) or {}
    w = {n: d[n] for n, _ in KUNDEN_FELDER if d.get(n)}
    w.setdefault("land", "DE")
    if p:
        w["ansprechpartner"] = [dict(p, haupt="ja")]
    w["bemerkung"] = "aus Anfrage-Mail angelegt"
    return w


def neu_anlegen(db, daten, dubletten_ok=False, kundennr=None):
    """Kunden aus den Maildaten anlegen (Ansprechpartner als Hauptansprechpartner). Ohne dubletten_ok KundenFehler
    bei möglichen Dubletten. Ergebnis: Kundennummer."""
    w = vorschlag_neu(daten)
    personen = w.pop("ansprechpartner", [])
    if kundennr:
        w["kundennr"] = kundennr
    if not w.get("name"):
        raise kd.KundenFehler("Bitte einen Firmennamen eintragen.")
    return kd.anlegen(db, w, personen, (), None, dubletten_ok=dubletten_ok)
