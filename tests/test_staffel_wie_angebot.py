"""Staffelmengen = normale Angebotskalkulation (Master-Prompt Patrick 24.11.2026).

„Eine Staffelmenge muss exakt so kalkuliert werden wie ein normales Angebot mit derselben Menge und denselben
Kalkulationsparametern.“ Geprüft wird automatisiert:

1. Gegenprobe Angebot ↔ Staffel: jedes Angebot wird mit der Menge × f als normales Angebot gerechnet (optimieren,
   kalkulieren, Preis wie im Angebots-PDF, ausgabe.angebot) und dieselbe Menge als Staffelstufe des Angebots mit der
   Grundmenge (staffeln.rechnen_alle). Je Position bzw. Satz muss der Preis je Einheit auf den Cent gleich sein –
   für die Abnahme-Angebote, das Beispielangebot mit Satz, Gewinde und Zusatzarbeiten, die Schweißbaugruppe R1 mit
   Zukaufteilen und für alle Kalkulationsparameter: Rabatt, Verpackung, Finanzierung, Runden (Stück und gesamt),
   Frachtfrei ab, gestaffelter Gewinn, Gewinn auf Material, Skonto, Eilzuschlag, Zuschlag Material und Fertigung,
   Programmierung, Angebotsaufschlag, Mindestauftragswert, feste Fracht, Preiseinheit, Neuteil-Zuschlag.
2. Eigene Werte der Stufe wie im Angebot (Gewinn, Faktor Laserzeit) = Angebot mit diesen Werten.
3. Einmalige und variable Kosten: Rüsten und Programmierung je Stufe einmal (Preis je Einheit fällt mit der Menge),
   Material nach dem Schnittplan der Stufe (Stangen neu optimiert).
4. Nie veraltet: jede kalkulationsrelevante Änderung (Einstellung, Wert der Stufe) macht die Stufe veraltet, reine
   Oberflächen-Einstellungen (Angebotsnummer, Ansicht) nicht.
5. Sonderwerte der Staffel (Erweitert, z. B. Nebenkosten je Einheit) wirken als Zuschlag auf den Preis der
   Kalkulation.
6. Tempo: sieben Stufen (1 … 250) in einem Lauf, ein zweiter Lauf übernimmt alles ohne neue Rechnung.

Aufruf: python tests/test_staffel_wie_angebot.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import beispiel_angebot  # noqa: E402
import beispiel_baugruppe  # noqa: E402
from abnahme_angebote import ANGEBOTE, programm_positionen  # noqa: E402
from rohrlaser import ausgabe, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

CENT = 0.005 + 1e-9


def ok(text):
    print("OK    ", text)


def angebotspreise(kopf, pos, k, tab, e):
    """Wie das normale Angebot: optimieren, kalkulieren, Preis je Einheit wie im Angebots-PDF.
    Ergebnis: ({Schlüssel (Pos. bzw. Satz): Preis je Einheit}, summen)."""
    kopf = dict(kopf)
    erg = rechnen.optimieren(kopf, pos, k, tab, e)
    kopf["ergebnis"] = erg
    zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, e)
    inhalt = ausgabe.angebot(kopf, pos, zeilen, k, e)
    out = {}
    for z in inhalt["zeilen"]:
        if z["art"] == "teil":
            out[str(z["pos"])] = z["preis"]
        elif z["art"] == "satz":
            out[str(z["satz"])] = z["preis"]
    return out, summen


def skaliert(pos, f):
    return [dict(p, stueck=p["stueck"] * f) if isinstance(p.get("stueck"), (int, float)) else dict(p) for p in pos]


def staffelpreise(kopf, pos, f, k, tab, e, stufe=None):
    """Eine Stufe mit allen Sätzen und Positionen des Angebots, Menge = Menge des Angebots × f."""
    mz = [dict(id=1000 + i, stufe_id=1, schluessel=schl, menge=int(menge * f))
          for i, (schl, _, menge) in enumerate(staffeln.auswahl(pos)) if menge]
    daten = [dict(dict(stufe or {}), id=1, nr=1)]
    return {z["schluessel"]: z for z in staffeln.rechnen_alle(kopf, pos, mz, k, tab, e, stufen_daten=daten)}


def vergleichen(name, kopf, pos, k, tab, e, faktoren=(1, 5), stufe=None, kopf_angebot=None, e_angebot=None):
    """Gegenprobe für alle Faktoren; Ergebnis: Anzahl verglichener Preise."""
    n = 0
    for f in faktoren:
        ang, _ = angebotspreise(kopf_angebot or kopf, skaliert(pos, f), k, tab, e_angebot or e)
        st = staffelpreise(kopf, pos, f, k, tab, e, stufe)
        for schl, preis in ang.items():
            z = st.get(schl)
            assert z is not None, (name, f, schl)
            if z.get("preis_einheit") is None:       # Staffel meldet einen Fehler (z. B. Teil zu lang, ohne Material)
                assert (z.get("hinweis") or "").startswith("FEHLER"), (name, f, schl, z.get("hinweis"))
                continue
            assert abs(z["preis_einheit"] - preis) < CENT, \
                f"{name} × {f}, {schl}: Angebot {preis} €, Staffel {z['preis_einheit']} € ({z.get('hinweis')})"
            n += 1
    return n


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
k, tab0, e_db = db.kontext(), db.tabellen(), db.einstellungen()
VERPACKUNG = [dict(name="Karton", preis=25.0, max_kg=30, max_laenge=4000, aktiv="ja"),
              dict(name="Palette", preis=60.0, max_kg=800, aktiv="ja")]
# (Kopfwerte des Angebots, Einstellungen, Tabellen)
FAELLE = {
    "ohne Sonderwerte": ({}, {}, {}),
    "Preisschicht des Angebots": (dict(rabatt=5, fracht=80, frachtfrei_ab=400),
                                  dict(finanz_zins=0.06, runden_stueck=0.05), dict(verpackung=VERPACKUNG)),
    "Gesamtpreis runden, Verpackung": ({}, dict(runden_gesamt=5.0), dict(verpackung=VERPACKUNG)),
    "Gewinn und Zuschläge": (dict(gewinn_material=5, skonto=3, eilzuschlag=10, programmierung_zeit=10,
                                  angebotsaufschlag=40),
                             dict(gewinn_bis_1=500, gewinn_satz_1=0.25, gewinn_bis_2=5000, gewinn_satz_2=0.15,
                                  gewinn_satz_3=0.08, zuschlag_material=0.1, zuschlag_fertigung=0.15), {}),
    "Mindestauftragswert": (dict(mindestwert=5000), {}, {}),
    "Preiseinheit": ({}, dict(preiseinheit_ab=0.5), {}),
}

# ------------------------------------------------------------------ 1 Abnahme-Angebote × Kalkulationsparameter
n = 0
for fall, (kp, ep, tp) in FAELLE.items():
    tab = dict(tab0, **tp)
    for an in ANGEBOTE:
        kopf = dict(maschine=an["maschine"], stange=an["stange"], **kp)
        pos = programm_positionen(an)
        e = rechnen.einstellungen_angebot(kopf, dict(rechnen.einstellungen_fest(tab, e_db), **ep))
        n += vergleichen(f"{an['nummer']} ({fall})", kopf, pos, k, tab, e)
ok(f"{len(ANGEBOTE)} Abnahme-Angebote × {len(FAELLE)} Kalkulationsfälle × Menge 1 und 5: {n} Preise je Einheit "
   "der Staffel = Preis des normalen Angebots (auf den Cent)")

# ------------------------------------------------------------------ Beispielangebot: Satz, Gewinde, Zusatzarbeiten
aid = beispiel_angebot.anlegen(db)
for p in db.positionen(aid):
    if p["pos"] == 10:
        db.position_aendern(p["id"], "gewinde", "2xM8")
        db.position_aendern(p["id"], "zusatz", json.dumps([dict(name="Entgraten", menge=1, preis=0.8)]))
kopf_b, pos_b = db.angebot(aid), db.positionen(aid)
neuteile = [p["id"] for p in pos_b if p["pos"] in (20, 50)]
for fall, (kp, ep, tp) in FAELLE.items():
    tab = dict(tab0, **tp)
    kopf = dict(kopf_b, **kp)
    e = rechnen.einstellungen_angebot(kopf, dict(rechnen.einstellungen_fest(tab, e_db), **ep))
    n_b = vergleichen(f"Beispielangebot ({fall})", kopf, pos_b, k, tab, e, faktoren=(1, 3))
kopf = dict(kopf_b, neuteile=json.dumps(neuteile))
e = rechnen.einstellungen_angebot(kopf, dict(rechnen.einstellungen_fest(tab0, e_db), neuteil_zuschlag=0.05))
vergleichen("Beispielangebot (Neuteil-Zuschlag)", kopf, pos_b, k, tab0, e, faktoren=(1, 3))
ok("Beispielangebot mit Satz 'Rahmen', Gewinde und Zusatzarbeit, alle Kalkulationsfälle und Neuteil-Zuschlag: "
   "Satzpreis und Stückpreise der Staffel = Angebot")

# ------------------------------------------------------------------ Schweißbaugruppe mit Zukaufteilen
db2 = Datenbank(tmp / "bg" / "rohrlaser.db")
a2 = beispiel_baugruppe.anlegen(db2)
k2, tab2 = db2.kontext(), db2.tabellen()
kopf2, pos2 = db2.angebot(a2), db2.positionen(a2)
e2 = rechnen.einstellungen_angebot(kopf2, rechnen.einstellungen_fest(tab2, db2.einstellungen()))
n_bg = vergleichen("Baugruppe R1", kopf2, pos2, k2, tab2, e2, faktoren=(1, 5, 20))
e2r = rechnen.einstellungen_angebot(dict(kopf2, rabatt=3), rechnen.einstellungen_fest(dict(tab2, verpackung=VERPACKUNG),
                                                                                         db2.einstellungen()))
vergleichen("Baugruppe R1 (Rabatt, Verpackung)", dict(kopf2, rabatt=3), pos2, k2, dict(tab2, verpackung=VERPACKUNG),
            e2r, faktoren=(1, 5))
ok(f"Schweißbaugruppe R1 mit Unterbaugruppe, Zukaufteilen und Einmalkosten, Menge 1/5/20 ({n_bg} Preise) und mit "
   "Rabatt und Verpackung: Preis je Baugruppe der Staffel = Angebot")
db2.schliessen()

# ------------------------------------------------------------------ 2 eigene Werte der Stufe wie im Angebot
an = ANGEBOTE[0]
kopf, pos = dict(maschine=an["maschine"], stange=an["stange"]), programm_positionen(an)
e = rechnen.einstellungen_angebot(kopf, rechnen.einstellungen_fest(tab0, e_db))
for werte in (dict(gewinn=25), dict(faktor_laserzeit=1.3), dict(zuschlag_fremdleistung=20, eilzuschlag=5)):
    kopf_a = dict(kopf, **werte)
    vergleichen(f"Stufe mit {werte}", kopf, pos, k, tab0, e, faktoren=(1, 4), stufe=werte, kopf_angebot=kopf_a,
                e_angebot=rechnen.einstellungen_angebot(kopf_a, rechnen.einstellungen_fest(tab0, e_db)))
ok("Stufe mit eigenem Gewinn, Faktor Laserzeit, Zuschlag Fremdleistung und Eilzuschlag = Angebot mit diesen Werten")

# ------------------------------------------------------------------ 3 einmalige und variable Kosten
e = rechnen.einstellungen_angebot(kopf_b, rechnen.einstellungen_fest(tab0, e_db))
mengen = (1, 5, 10, 25, 50, 100, 250)
mz = [dict(id=i, stufe_id=i, schluessel="10", menge=m) for i, m in enumerate(mengen, 1)]
daten = [dict(id=i, nr=i) for i in range(1, len(mengen) + 1)]
t0 = time.perf_counter()
zeilen = staffeln.rechnen_alle(kopf_b, pos_b, mz, k, tab0, e, stufen_daten=daten)
dauer = time.perf_counter() - t0
preise_je = [z["preis_einheit"] for z in zeilen]
assert all(a > b for a, b in zip(preise_je, preise_je[1:])), preise_je
ruesten = [sum(w for n_, w, _ in z["preis"]["ruesten"] if n_.startswith("Rüsten")) for z in zeilen]
assert ruesten[0] > 0 and max(ruesten) - min(ruesten) < 0.01, ruesten     # Rüsten einmal je Stufe (ohne Stangenwechsel)
mat = [z["preis"]["m_grund"] / z["menge"] for z in zeilen]
assert mat[0] > mat[-1] * 1.5, mat                             # 1 Stück braucht eine ganze Stange
stangen = [z["stangen"] for z in zeilen]
assert stangen == sorted(stangen) and stangen[-1] > stangen[0], stangen
for z, m in zip(zeilen, mengen):                               # jede Menge = normales Angebot mit dieser Menge
    pos_m = [dict(p, stueck=m if p["pos"] == 10 else None) for p in pos_b]
    ang, _ = angebotspreise(kopf_b, pos_m, k, tab0, e)
    assert abs(ang["10"] - z["preis_einheit"]) < CENT, (m, ang["10"], z["preis_einheit"])
ok(f"Pos. 10 in 7 Stufen 1 … 250 Stück: Preis je Stück fällt ({preise_je[0]} → {preise_je[-1]} €), Rüsten einmal je "
   f"Stufe ({ruesten[0]:.2f} €), Material nach Schnittplan ({stangen[0]} → {stangen[-1]} Stangen), jede Stufe = "
   f"Angebot mit dieser Menge; Rechenzeit {dauer:.2f} s")

# ------------------------------------------------------------------ 6 Tempo: zweiter Lauf ohne neue Rechnung
laeufe = []
alt_lauf = staffeln.stufe_lauf


def zaehlen(*a, **kw):
    laeufe.append(1)
    return alt_lauf(*a, **kw)


staffeln.stufe_lauf = zaehlen
try:
    zweite = staffeln.rechnen_alle(kopf_b, pos_b, mz, k, tab0, e, alt=zeilen, stufen_daten=daten)
finally:
    staffeln.stufe_lauf = alt_lauf
assert not laeufe and [z["preis_einheit"] for z in zweite] == preise_je
ok("Zweiter Lauf mit unveränderten Eingaben: kein neuer Mengenlauf, gleiche Preise")

# ------------------------------------------------------------------ 4 nie veraltet
sp = dict(zeilen=zeilen)


def veraltet(e_neu=None, daten_neu=None, kopf_neu=None):
    return staffeln.veraltet(sp, kopf_neu or kopf_b, pos_b, mz, k, tab0, e_neu or e, daten_neu or daten)


assert veraltet() == 0
for name, wert in (("gaspreis_o2", 9.99), ("gewinn", 0.2), ("zuschlag_fertigung", 0.3), ("runden_stueck", 0.1),
                   ("finanz_zins", 0.05), ("mindestpreis", 999.0), ("faktor_laserzeit", 1.2)):
    assert veraltet(dict(e, **{name: wert})) == len(mengen), name
for name, wert in (("letzte_angebotsnummer", "2026-99999"), ("ansicht_thema", "dunkel"), ("benutzer_name", "X"),
                   ("angebot_mail_text", "Hallo")):
    assert veraltet(dict(e, **{name: wert})) == 0, name
assert veraltet(daten_neu=[dict(d, faktor_laserzeit=1.4) if d["id"] == 2 else d for d in daten]) == 1
assert veraltet(daten_neu=[dict(d, gewinn=30) if d["id"] == 3 else d for d in daten]) == 1
assert veraltet(kopf_neu=dict(kopf_b, verpackung="nein")) == len(mengen)
ok("Jede kalkulationsrelevante Änderung (Gaspreis, Gewinn, Zuschläge, Runden, Finanzierung, Mindestpreis, Faktor "
   "Laserzeit, Wert der Stufe, Verpackung je Angebot) macht die Stufen veraltet, Angebotsnummer/Ansicht/Texte nicht")

# ------------------------------------------------------------------ 5 Sonderwerte der Staffel als Zuschlag
st = staffelpreise(kopf_b, pos_b, 1, k, tab0, e)
mit = staffelpreise(kopf_b, pos_b, 1, k, tab0, e, stufe=dict(neben_einheit=2.0))
for schl, z in st.items():
    if z.get("preis_einheit") is None:
        continue
    d = mit[schl]["preis_einheit"] - z["preis_einheit"]
    g = z["wirksam"]["gewinn"]
    assert 2.0 * (1 + g) - 0.02 < d < 2.0 * (1 + g) + 0.1, (schl, d, g)      # Gewinn darauf, Cent je Stück
    assert abs(mit[schl]["preis"]["angleich"] - z["preis"]["angleich"]) < 1e-6
ok("Nebenkosten je Einheit der Stufe (Erweitert): Preis der Kalkulation + 2,00 € mit Gewinn, gleicher "
   "Angleich an die Kalkulation")

# ------------------------------------------------------------------ Übersicht je Staffel (Punkt 4)
for z in zeilen:
    u = staffeln.uebersicht(z)
    teile = u["material"] + u["maschine"] + u["personal"] + u["zusatz"] + u["gemeinkosten"]
    assert abs(teile - u["herstell"]) < 1e-6 and u["maschine"] > 0 and u["material"] > 0, u
    assert abs(u["herstell"] + u["gewinn"] + u["fracht_skonto"] - u["netto"]) < 1e-6
    assert u["gegenprobe"] == "= Angebotskalkulation" and u["netto_einheit"] == z["preis_einheit"]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(aid)
assert s.optimieren()
st = s.st_seite
assert st.rechnen() is not None and st.anzahl_veraltet() == 0
assert [st.ergebnis_reiter.tabText(i) for i in range(st.ergebnis_reiter.count())] == ["Kosten", "Stangen", "Übersicht"]
assert st.uebersicht.rowCount() == len(st.zeilen) == 6
for r in range(st.uebersicht.rowCount()):
    w = st.uebersicht.werte(r)
    assert w["Gegenprobe"] == "= Angebotskalkulation" and w["Herstellkosten gesamt [€]"] and w["Marge"].endswith("%"), w
assert st.baum.zeile("preisschicht") is None              # ohne Verpackung, Rabatt … keine Zeile Preisschicht
fenster.close()
ok("Reiter Staffeln → Übersicht: je Stufe Herstellkosten = Material + Maschine + Personal + Zusatz + Gemeinkosten, "
   "dazu Gewinn, Netto, Deckungsbeitrag, Marge und Gegenprobe „= Angebotskalkulation“")

db.schliessen()
print("OK: Staffelmengen rechnen wie das normale Angebot")
