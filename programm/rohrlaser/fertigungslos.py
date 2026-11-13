"""Fertigungslos (Plan ArTube-Unterlagen A2, Patrick 12.11.2026): mehrere beauftragte Aufträge gemeinsam schneiden.

Die Laserteile der gewählten Aufträge kommen zusammen in eine Optimierung: gleiche Abmessung (Profil, Werkstoff,
Oberfläche, Stangenlänge) teilt sich die Stangen, wie in der Adige-Fertigungsliste mehrere Programme auf einer Stange.
Kundenmaterial und Muster bleiben getrennt (eigenes Material, eigener Lauf) und stehen weiter in den Papieren ihres
Auftrags. Die Angebotspreise ändern sich nicht; das Los liefert nur Werkstattpapiere (Schnittpläne, Stangenbild) und
den Vergleich „Stangen im Los / Stangen einzeln“. Alle Aufträge eines Loses müssen auf derselben Maschine laufen.

Je Teil nennt das Los den Auftrag: Artikel = „<Angebotsnummer> / <Artikel>“; die Position wird fortlaufend
nummeriert (10, 20, …), damit jede Position eine eigene Farbe im Stangenbild hat.

Rüstoptimierte Reihenfolge (MACH-008, Plan Phase 3 und 4, 13.11.2026): Vorschlag, in welcher Reihenfolge die
Abmessungen des Loses laufen, damit möglichst selten umgerüstet wird. Kosten eines Wechsels (Punkte, keine Zeit):
Werkstoff-Kategorie anders (Schneidgas/Düse) 3, Profilform anders (Spannbacken) 2, Außenmaß anders bis 1 je 100 %
Unterschied; gleiche Abmessung 0. Gesucht wird mit „nächster Nachbar“ ab jeder Abmessung, die günstigste Folge
gewinnt. Nur Vorschlag für die Werkstatt (Dialog und Papiere), die Schnittpläne bleiben. Ohne Qt."""
import datetime

from . import ausgabe, rechnen
from .angebot import ist_muster, kein_laserteil


class LosFehler(ValueError):
    """Los nicht möglich (Text für den Benutzer)."""


def kandidaten(db):
    """Beauftragte Aufträge, die noch nicht fertig gemeldet sind: [dict(id, nummer, kunde, maschine, status)]."""
    from . import fertigung
    out = []
    for z in fertigung.uebersicht(db):
        if z["status"] == "Fertig gemeldet":
            continue
        a = db.angebot(z["id"]) or {}
        out.append(dict(id=z["id"], nummer=z.get("nummer") or "", kunde=z.get("kunde") or "",
                        auftragsnr=z.get("auftragsnr") or "", maschine=a.get("maschine") or "",
                        liefertermin=z.get("liefertermin"), status=z["status"]))
    return out


def _stangen(erg):
    return len((erg or {}).get("stangen") or ())


def zusammenstellen(db, angebot_ids, fortschritt=None):
    """Los aus den Aufträgen: dict(kopf, positionen, ergebnis, auftraege=[dict(id, nummer, kunde, stangen)],
    stangen_los, stangen_einzeln, getrennt=[Text je nicht aufgenommener Position], fehler=[Optimierungsfehler]).
    LosFehler bei weniger als zwei Aufträgen oder verschiedenen Maschinen."""
    ids = list(dict.fromkeys(angebot_ids))
    if len(ids) < 2:
        raise LosFehler("Für ein Fertigungslos bitte mindestens zwei Aufträge wählen.")
    k, tabellen = db.kontext(), db.tabellen()
    einst = rechnen.einstellungen_fest(tabellen, db.einstellungen())
    kopfe = [db.angebot(i) for i in ids]
    maschinen = sorted({a.get("maschine") or "" for a in kopfe})
    if len(maschinen) > 1:
        raise LosFehler("Die Aufträge laufen auf verschiedenen Maschinen (" + ", ".join(maschinen) + "). Ein "
                        "Fertigungslos geht nur auf einer Maschine.")
    positionen, getrennt, auftraege = [], [], []
    nr = 0
    for a in kopfe:
        eigene = []
        for p in db.positionen(a["id"]):
            if kein_laserteil(p):
                continue
            artikel = p.get("artikel") or p.get("bezeichnung") or f"Pos. {p.get('pos')}"
            if rechnen.beigestellt(p) or ist_muster(p):
                getrennt.append(f"{a.get('nummer')} Pos. {p.get('pos')} {artikel}: "
                                + ("Kundenmaterial" if rechnen.beigestellt(p) else "Muster") + " bleibt im Auftrag")
                continue
            nr += 10
            eigene.append(dict(p, pos=nr, artikel=f"{a.get('nummer')} / {artikel}",
                               stange=p.get("stange") or a.get("stange"), los_angebot=a.get("nummer"),
                               los_pos=p.get("pos")))
        positionen += eigene
        einzeln = rechnen.optimieren(dict(a, stangen_vorgabe=None), eigene, k, tabellen, einst) if eigene else None
        auftraege.append(dict(id=a["id"], nummer=a.get("nummer") or "", kunde=a.get("kunde") or "",
                              stangen=_stangen(einzeln), teile=sum(int(p.get("stueck") or 0) for p in eigene)))
        if fortschritt:
            fortschritt(len(auftraege), len(kopfe) + 1)
    if not positionen:
        raise LosFehler("Die gewählten Aufträge haben keine Laserteile aus eigenem Material.")
    heute = datetime.date.today()
    nummern = ", ".join(a["nummer"] for a in auftraege)
    kopf = dict(maschine=maschinen[0], stange=None, nummer=f"Los {heute:%d.%m.%Y}", kunde="Fertigungslos",
                bezeichnung=f"Fertigungslos aus {nummern}", vorgang="Beauftragt", datum=heute.isoformat())
    erg = rechnen.optimieren(kopf, positionen, k, tabellen, einst)
    return dict(kopf=kopf, positionen=positionen, ergebnis=erg, auftraege=auftraege, stangen_los=_stangen(erg),
                stangen_einzeln=sum(a["stangen"] for a in auftraege), getrennt=getrennt,
                fehler=[f"{f.get('artikel')}: {f.get('grund')}" for f in erg.get("fehler") or ()], k=k,
                tabellen=tabellen, einst=einst)


RUEST_KATEGORIE, RUEST_FORM, RUEST_MASS = 3.0, 2.0, 1.0


def _abmessungen(los):
    """[dict(profil, werkstoff, oberflaeche, stange, stangen, form, a, kategorie)] des Loses in Plan-Reihenfolge."""
    k = los["k"]
    out = {}
    for st in (los.get("ergebnis") or {}).get("stangen") or ():
        schl = (st["profil"], st["werkstoff"], st.get("oberflaeche") or "")
        pr = k.profile.get(st["profil"]) or {}
        z = out.setdefault(schl, dict(profil=st["profil"], werkstoff=st["werkstoff"],
                                      oberflaeche=st.get("oberflaeche") or "", stangen=0, form=pr.get("form") or "",
                                      a=float(pr.get("a") or 0), kategorie=rechnen.kategorie(st["werkstoff"], k) or ""))
        z["stangen"] += 1
    return list(out.values())


def ruestkosten(x, y):
    """Punkte für den Wechsel von Abmessung x auf y (0 = gleich)."""
    c = RUEST_KATEGORIE if x["kategorie"] != y["kategorie"] else 0.0
    c += RUEST_FORM if x["form"] != y["form"] else 0.0
    m = max(x["a"], y["a"])
    c += RUEST_MASS * min(1.0, abs(x["a"] - y["a"]) / m) if m else 0.0
    return c + (0.1 if (x["profil"], x["werkstoff"]) != (y["profil"], y["werkstoff"]) and c == 0 else 0.0)


def _summe(folge):
    return sum(ruestkosten(a, b) for a, b in zip(folge, folge[1:]))


def reihenfolge(los):
    """MACH-008: dict(folge [Abmessungen], punkte, punkte_plan, wechsel, wechsel_plan) – rüstgünstige Reihenfolge
    gegen die Reihenfolge des Schnittplans; None bei weniger als zwei Abmessungen."""
    abm = _abmessungen(los)
    if len(abm) < 2:
        return None
    beste = None
    for start in range(len(abm)):
        rest = abm[:start] + abm[start + 1:]
        folge = [abm[start]]
        while rest:
            n = min(range(len(rest)), key=lambda i: (ruestkosten(folge[-1], rest[i]), i))
            folge.append(rest.pop(n))
        if beste is None or _summe(folge) < _summe(beste) - 1e-9:
            beste = folge

    def wechsel(f):
        return sum(1 for a, b in zip(f, f[1:]) if a["kategorie"] != b["kategorie"] or a["form"] != b["form"])
    return dict(folge=beste, punkte=_summe(beste), punkte_plan=_summe(abm), wechsel=wechsel(beste),
                wechsel_plan=wechsel(abm))


def reihenfolge_text(r):
    """Zeilen für Dialog und Papiere."""
    if not r:
        return []
    kopf = (f"Rüstgünstige Reihenfolge (Vorschlag): {r['wechsel']} Wechsel von Werkstoffgruppe oder Profilform statt "
            f"{r['wechsel_plan']} in der Reihenfolge des Schnittplans")
    return [kopf] + [f"{i}. {a['profil']} {rechnen.material_text(a['werkstoff'], a['oberflaeche'])} "
                     f"({a['stangen']} {'Stange' if a['stangen'] == 1 else 'Stangen'})"
                     for i, a in enumerate(r["folge"], 1)]


def zusammenfassung(los):
    """Eine Zeile für Dialog und Papiere."""
    gespart = los["stangen_einzeln"] - los["stangen_los"]
    text = (f"{len(los['auftraege'])} Aufträge, {los['stangen_los']} Stangen im Los statt "
            f"{los['stangen_einzeln']} einzeln")
    return text + (f" ({gespart} {'Stange' if gespart == 1 else 'Stangen'} gespart)" if gespart > 0 else "")


def werkstatt(los):
    """Werkstattpapier-Daten (ausgabe.werkstatt) mit den Aufträgen des Loses als Hinweis oben."""
    wp = ausgabe.werkstatt(los["kopf"], los["positionen"], los["ergebnis"], los["k"], los["tabellen"])
    zeilen = [dict(werkstoff="Fertigungslos", text=f"{zusammenfassung(los)}. Angebotspreise unverändert.")]
    zeilen += [dict(werkstoff=a["nummer"], text=f"{a['kunde']}: {a['teile']} Teile, einzeln {a['stangen']} Stangen")
               for a in los["auftraege"]]
    zeilen += [dict(werkstoff="Reihenfolge", text=t) for t in reihenfolge_text(reihenfolge(los))]
    zeilen += [dict(werkstoff="getrennt", text=t) for t in los["getrennt"]]
    zeilen += [dict(werkstoff="nicht eingeplant", text=t) for t in los["fehler"]]
    return dict(wp, zukaufteile=[], schweissplan=[], hinweise=zeilen + list(wp.get("hinweise") or ()))


def pdf_schreiben(pfad, los):
    from . import pdf
    pdf.werkstatt_pdf(pfad, los["kopf"], werkstatt(los), True, los["einst"])
    return pfad
