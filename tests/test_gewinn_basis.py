"""Prüft, worauf der Gewinn rechnet (Plan „Preisaufbau und Zeiten“, Patrick 23.10.2026: 1a 2a 3a 4a).

Neu: Gewinn auf die Selbstkosten (Herstellkosten + Programmierung + Pauschale je Abmessung + Angebotsaufschlag +
Zukaufteile), Fracht ohne Gewinn danach, Skonto im Hundert zuletzt. Festgeschriebene Angebote ohne gewinn_basis
rechnen wie bisher (Gewinn nur auf die Herstellkosten). Geprüft an Abnahmeangeboten, am Beispielangebot mit Fracht,
an einer Zukaufteil-Position, an der Preisschicht der Staffeln und am Festschreiben.

Aufruf: python tests/test_gewinn_basis.py
"""
import json
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import beispiel_angebot  # noqa: E402
from abnahme_angebote import ANGEBOTE, programm_positionen  # noqa: E402
from rohrlaser import rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, eps=1e-6):
    return abs(a - b) <= eps * max(1.0, abs(a), abs(b))


def rechne(db, kopf, positionen, basis=None):
    """(zeilen, summen) eines Angebots; basis = gewinn_basis der Einstellungen (None = Vorgabe)."""
    aid = db.angebot_neu(kopf)
    for p in positionen:
        db.position_neu(aid, p)
    kopf, positionen = db.angebot(aid), db.positionen(aid)
    erg = rechnen.optimieren(kopf, positionen, db.kontext())
    if erg["neue_profile"]:
        db.profile_anlegen(erg["neue_profile"])
    db.ergebnis_speichern(aid, erg)
    kopf = db.angebot(aid)
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    if basis:
        einst["gewinn_basis"] = basis
    return rechnen.kalkulation(kopf, positionen, kopf["ergebnis"], db.kontext(), db.tabellen(), einst)


def teile(s):
    """Summen der Bausteine: Herstellkosten, weitere (Programmierung, Pauschalen, Aufschlag), Zukauf, Fracht."""
    return (s["herstell"], s["programmierung"] + s["pauschalen"] + s["angebotsaufschlag"],
            s["zukauf_einstand"] + s["zukauf_aufschlag"], s["fracht"])


with tempfile.TemporaryDirectory() as tmp:
    db = Datenbank(Path(tmp) / "r.db")
    db.einstellung_setzen("mindestpreis", 0)
    db.einstellung_setzen("pauschale_abmessung", 22.5)      # Werte unten mit der Pauschale bis 25.10.2026

    # 1) Abnahmeangebote mit 25 % Gewinn und 2 % Skonto: neu und alt von Hand nachgerechnet
    erwartet = {"ABN-01": (475.30, 498.89), "ABN-07": (376.99, 407.60), "ABN-08": (556.45, 591.53)}     # ABN-08 bis 0.9.196 (vor Schneiddaten-Abgleich): 556,00 / 591,08; bis 0.9.61 scharfkantig: 555,60 / 590,68; bis 0.9.195 ohne Zeit je Ecke: 555,61 / 590,69
    for a in ANGEBOTE:
        kopf = dict({n: a[n] for n in ("kunde", "maschine", "stange")}, skonto=2, gewinn=25)
        _, s_neu = rechne(db, dict(kopf, nummer=a["nummer"] + "-n"), programm_positionen(a))
        _, s_alt = rechne(db, dict(kopf, nummer=a["nummer"] + "-a"), programm_positionen(a), rechnen.GEWINN_HERSTELL)
        h, w, zk, fr = teile(s_neu)
        assert nah(s_neu["selbst"], h + w + zk) and nah(s_neu["gewinn"], 0.25 * (h + w))     # Zukauf ohne Gewinn (26.10.)
        assert nah(s_neu["verkauf"], ((h + w) * 1.25 + zk + fr) / 0.98), a["nummer"]
        assert nah(s_alt["verkauf"], (h * 1.25 + w + zk + fr) / 0.98) and nah(s_alt["gewinn"], 0.25 * h)
        assert s_neu["gewinn_basis"] == rechnen.GEWINN_SELBST and s_alt["gewinn_basis"] == rechnen.GEWINN_HERSTELL
        assert teile(s_alt) == teile(s_neu), "Kosten vor dem Gewinn ändern sich nicht"
        if a["nummer"] in erwartet:
            assert (round(s_alt["verkauf"], 2), round(s_neu["verkauf"], 2)) == erwartet[a["nummer"]], \
                (a["nummer"], s_alt["verkauf"], s_neu["verkauf"])
    ok("1  Abnahmeangebote: Gewinn auf Selbstkosten, alt (nur Herstellkosten) unverändert, z. B. ABN-07 "
       "376,99 → 407,60 €")

    # 2) Fracht ohne Gewinn, Summe der Positionen = Summe des Angebots, Kostenarten addieren sich
    kopf = dict(beispiel_angebot.KOPF, nummer="B-fracht", skonto=2, gewinn=25, fracht=80, fracht_modus="manuell")
    zeilen, s = rechne(db, kopf, beispiel_angebot.POSITIONEN)
    h, w, zk, fr = teile(s)
    assert fr == 80 and nah(s["verkauf"], ((h + w) * 1.25 + zk + 80) / 0.98)
    assert nah(sum(z["preis_position"] for z in zeilen if z), s["verkauf"])
    assert nah(sum(z["selbst_position"] for z in zeilen if z), s["selbst"])
    kosten = {n: w_ for (_, w_, _), (_, n, _) in zip(rechnen.kostenarten(s, {"gewinn": 0.25}), rechnen.KOSTENARTEN)}
    assert nah(kosten["selbst"] + kosten["gewinn"] + kosten["fracht"] + kosten["skonto"], kosten["verkauf"])
    text = dict((t.split(" (")[0], t) for t, _, _ in rechnen.kostenarten(s, {"gewinn": 0.25}))
    assert "25 % auf Selbstkosten" in text["Gewinn"], text["Gewinn"]
    namen = [n for _, n, _ in rechnen.KOSTENARTEN]
    assert namen.index("herstell") < namen.index("programmierung") < namen.index("selbst") < namen.index("gewinn") \
        < namen.index("fracht") < namen.index("skonto") < namen.index("verkauf")
    ok(f"2  Fracht 80 € ohne Gewinn, Kostenarten in der Reihenfolge Herstellkosten → Selbstkosten → Gewinn → "
       f"Fracht → Skonto ({s['verkauf']:.2f} €)")

    # 3) Zukaufteil-Position: Gewinn auch auf Einstand + Aufschlag (2a), alt ohne Gewinn
    zk = [dict(einstand=100.0, aufschlag=20.0, fehler=None)]
    z_neu = rechnen._zukaufteil_zeile({"pos": 10}, 4, zk, 5.0, 0.02, gew=0.25)
    z_alt = rechnen._zukaufteil_zeile({"pos": 10}, 4, zk, 5.0, 0.02)
    assert nah(z_neu["preis_teil"], (30 * 1.25 + 5) / 0.98) and nah(z_neu["gewinn_teil"], 7.5)
    assert nah(z_alt["preis_teil"], (30 + 5) / 0.98) and z_alt["gewinn_teil"] == 0
    ok("3  Zukaufteil-Position: (Einstand + Aufschlag) × 1,25 + Fracht, Skonto zuletzt")

    # 4) Staffeln: gleiche Reihenfolge in der Preisschicht, alt bitgleich wie vorher
    b = dict(material=100.0, material_fehlt=0, fertigung=[("Laser schneiden", 50.0, "")],
             ruesten=[("Rüsten Maschine", 30.0, "")], fremd=0.0, pauschalen=10.0, programmierung=20.0,
             angebotsaufschlag=5.0, fracht=15.0, zukauf_einstand=40.0, zukauf_aufschlag=8.0, skonto_satz=2.0,
             satz_maschine=60.0, verkauf=None)
    basis = dict(zuschlag_material=0, zuschlag_fertigung=0, zuschlag_fremdleistung=0, gewinn=0.25, mwst=0.19)
    p = staffeln.preise(b, 10, staffeln.wirksam({}, basis))       # Zukaufteile 48 € ohne Gewinn (Patrick 26.10.2026, 8)
    assert nah(p["herstell"], 180) and nah(p["selbst"], 263) and nah(p["gewinn"], 53.75)
    assert nah(p["netto"], (263 + 53.75 + 15) / 0.98) and p["preis_einheit"] == round((263 + 53.75 + 15) / 0.98 / 10, 2)
    p = staffeln.preise(b, 10, staffeln.wirksam({}, dict(basis, preisregeln=rechnen.PREISREGELN_ALT)))
    assert nah(p["gewinn"], 65.75) and nah(p["netto"], (263 * 1.25 + 15) / 0.98)
    p = staffeln.preise(b, 10, staffeln.wirksam({}, dict(basis, gewinn_basis=rechnen.GEWINN_HERSTELL)))
    assert nah(p["gewinn"], 45) and p["netto"] == (180 + 45 + (10 + 20 + 5 + 15) + 40 + 8) / 0.98
    ok("4  Staffelpreise: Gewinn auf Selbstkosten 263 € ohne Zukaufteile 48 €, Fracht danach; bis 25.10.: auf 263 €; "
       "alt: Gewinn nur auf 180 €")

    # 5) Festschreiben: neue Preisbasis merkt 'Selbstkosten', alte ohne Merker rechnet nur auf Herstellkosten
    k, tab = db.kontext(), db.tabellen()
    a = db.angebot(next(x["id"] for x in db.angebote() if x["nummer"] == "B-fracht"))
    pos = db.positionen(a["id"])
    pb = rechnen.preisbasis_aus(a, pos, k, tab)
    assert pb["einstellungen"]["gewinn_basis"] == rechnen.GEWINN_SELBST
    _, tab_fest = rechnen.preisbasis_anwenden(dict(a, preisbasis=pb), k, tab)
    assert rechnen.gewinn_auf_selbstkosten(rechnen.einstellungen_fest(tab_fest, db.einstellungen()))
    assert rechnen.preisbasis_abweichung(dict(a, preisbasis=pb), k, tab) == []
    alt = dict(pb, einstellungen={n: w_ for n, w_ in pb["einstellungen"].items() if n != "gewinn_basis"})
    _, tab_alt = rechnen.preisbasis_anwenden(dict(a, preisbasis=alt), k, tab)
    assert not rechnen.gewinn_auf_selbstkosten(rechnen.einstellungen_fest(tab_alt, db.einstellungen()))
    alt07 = {n: w_ for n, w_ in pb.items() if n != "einstellungen"}        # Festgeschrieben vor 0.7.0
    _, tab_07 = rechnen.preisbasis_anwenden(dict(a, preisbasis=alt07), k, tab)
    assert tab_07["einstellungen"]["gewinn_basis"] == rechnen.GEWINN_HERSTELL
    assert "Gewinn auf Herstellkosten → auf Selbstkosten" in rechnen.preisbasis_abweichung(dict(a, preisbasis=alt), k, tab)
    ok("5  festgeschriebene Angebote: ohne Merker Gewinn auf Herstellkosten, „Aktuelle Preise übernehmen“ nennt "
       "die Umstellung")

    # 6) Zeitaufwand einer Zusatzarbeit (€/Stück mit Zeit × Stundensatz) bleibt im Preisstand für die Zeiten erhalten
    saetze = rechnen.stundensaetze(tab)
    kz = dict(name="Entgraten Test", art="€/Stück", zeit=0.5, zeit_einheit="min", satz_id="Nachbearbeitung")
    stand = rechnen.zusatz_stand(kz, saetze)
    assert stand["arbeit_s"] == 30 and stand["preis"] == rechnen.zusatz_preis(kz, saetze)["preis"]
    pos_z = dict(zusatz=json.dumps([dict(name="Entgraten Test", menge=2, stand=stand)]))
    (w,) = rechnen.zusatz_werte(pos_z, k, tab)
    assert w["arbeit_s"] == 60, w
    alt_stand = {n: v for n, v in stand.items() if n != "arbeit_s"}        # Preisstand vor 0.9.28: Stammdaten
    tab_k = dict(tab, zusatzarbeiten=list(tab.get("zusatzarbeiten") or []) + [kz])
    (w,) = rechnen.zusatz_werte(dict(zusatz=json.dumps([dict(name="Entgraten Test", menge=2, stand=alt_stand)])), k, tab_k)
    assert w["arbeit_s"] == 60, w
    ok("6  Zeitaufwand der Zusatzarbeit im Preisstand gemerkt (2 × 30 s), ältere Preisstände aus den Stammdaten")
    db.schliessen()
print("Alle Prüfungen bestanden.")
