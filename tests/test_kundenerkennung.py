"""Kundenerkennung aus Outlook-Mails (Patrick 19.11.2026, Entwicklungsauftrag „Outlook-E-Mail-Integration vollständig
verbessern“, Paket Z1): die 15 Testfälle des Auftrags mit erfundenen Testmails.

Grundregel: „Lieber eine Anfrage zur manuellen Prüfung vorlegen, als automatisch einen falschen Kunden oder
Ansprechpartner zuzuordnen.“ Nur „eindeutig“ setzt die Kundennummer.

  E1  .msg: An, CC, Reply-To, Message-ID, In-Reply-To, References; Exchange-Empfänger ohne @ gilt als intern
  E2  .eml: dieselben Kopfzeilen
  E3  direkte Mail, Adresse beim Kunden: eindeutig, Ansprechpartner aus dem Absender
  E4  intern weitergeleitet (im Text): Kunde aus der Mail des Kunden, Weiterleiter getrennt gespeichert
  E5  mehrfach weitergeleitet (Kette über zwei Kollegen)
  E6  als Anlage weitergeleitet: Empfänger und Message-ID der Original-Mail bekannt, eigenes Postfach erkannt
  E7  Sammelpostfach des Kunden (info@): Kunde ja, Ansprechpartner nein
  E8  nur die Domain passt: wahrscheinlich, Kundennummer bleibt leer, „Kunde prüfen“
  E9  Domain plus Firmenname in der Signatur: eindeutig (zwei unabhängige Merkmale)
  E10 dieselbe Adresse bei zwei Kunden: mehrdeutig
  E11 Freemail-Absender ohne Treffer: nicht erkannt
  E12 interne Anfrage (Kollege nennt den Kunden): nie Kunde/Ansprechpartner aus dem Kollegen, Kunde nur Vorschlag
  E13 Lernregeln: Adresse → Kunde, „nie automatisch“, interne Adresse; sichtbar und löschbar
  E14 Outlook-Abruf: dieselbe Kundenmail auf zweitem Weg ergibt keine zweite Anfrage; Antwort über In-Reply-To ohne
      AW: im Betreff kommt in die Anfrage; jede Zuordnung steht mit Kriterien und Message-ID im Verlauf
  E15 Korrekturen von Hand (Kunde, Ansprechpartner, Absender, Intern ohne Kunde, Zurücksetzen) im Verlauf; Antwort an den
      Kunden nie auf die intern weitergeleitete Mail (interne Notizen gehen nicht mit)

Aufruf: python tests/test_kundenerkennung.py
"""
import datetime
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import mail_testdateien as t  # noqa: E402
from outlook_nachbau import Outlook  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import mail  # noqa: E402
from rohrlaser import mail_zuordnung as mz  # noqa: E402
from rohrlaser import outlook_anfragen as ol  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
D = datetime.datetime(2026, 11, 19, 9, 15)
EIGEN = {"laser.example"}
FIRMA = "Laser Brundiers GmbH"
KUNDEN = [dict(kundennr="10001", name="Metallbau Krüger GmbH", email="h.krueger@krueger-metall.de; info@krueger-metall.de",
               telefon="0231 445566", zustaendig="pb"),
          dict(kundennr="10002", name="Stahlbau Neumann GmbH", email="einkauf@stahlbau-neumann.de", telefon="0221 778899"),
          dict(kundennr="10003", name="Gestellbau Weber KG", email="sammel@agentur.example"),
          dict(kundennr="10004", name="Rahmenwerk Schulz GmbH", email="sammel@agentur.example"),
          dict(kundennr="10005", name="Laser Brundiers GmbH", email="info@laser.example")]   # Falle: eigene Firma


def m_aus(daten, endung=".msg"):
    m = mail.aus_bytes(daten, endung)
    assert m is not None
    return m


def z(m, regeln=()):
    return mz.zuordnen(m, KUNDEN, EIGEN, FIRMA, regeln)


SIG_NEUMANN = "\n\nMit freundlichen Grüßen\nHans Neumann\nStahlbau Neumann GmbH\nTel. 0221 778899\n"

# ------------------------------------------------------------------ E1/E2 Kopfzeilen lesen
kopf = ("Received: from x\r\nFrom: Hans <h.krueger@krueger-metall.de>\r\nTo: Anfrage <anfrage@laser.example>\r\n"
        "Cc: Eva Krüger <e.krueger@krueger-metall.de>\r\nReply-To: angebote@krueger-metall.de\r\n"
        "Message-ID: <abc123@krueger-metall.de>\r\nIn-Reply-To: <vorher1@laser.example>\r\n"
        "References: <start0@laser.example> <vorher1@laser.example>\r\n\r\n")
m = m_aus(t.msg("Anfrage Rohr", "Bitte anbieten", "Hans Krüger", "h.krueger@krueger-metall.de", D,
                an=[("Anfrage", "anfrage@laser.example"), ("Patrick", "/o=ExchangeLabs/ou=Exchange/cn=Recipients/cn=pb")],
                cc=[("Eva Krüger", "e.krueger@krueger-metall.de")], kopfzeilen=kopf))
assert ("anfrage", "anfrage@laser.example") == (m.an[0][0].lower(), m.an[0][1]), m.an
assert m.cc == [("Eva Krüger", "e.krueger@krueger-metall.de")], m.cc
assert m.antwort_an == "angebote@krueger-metall.de" and m.nachrichten_id == "abc123@krueger-metall.de"
assert m.in_reply_to == "vorher1@laser.example" and m.referenzen == ["start0@laser.example", "vorher1@laser.example"]
assert mail.ist_intern(m.an[1][1], EIGEN) and mail.ist_exchange(m.an[1][1])
assert not mail.ist_intern("h.krueger@krueger-metall.de", EIGEN)
ok("E1 .msg: An, CC, Reply-To, Message-ID, In-Reply-To, References; Exchange-Empfänger ohne @ gilt als intern")

e = m_aus(t.eml("Anfrage", "Text", "Hans", "h.krueger@krueger-metall.de", D, an="info@laser.example",
                cc="Eva <e@krueger-metall.de>", kopf={"Message-ID": "<e1@x.de>", "In-Reply-To": "<v@laser.example>",
                                                     "References": "<a@laser.example> <v@laser.example>"}), ".eml")
assert e.an == [("", "info@laser.example")] and e.cc == [("Eva", "e@krueger-metall.de")]
assert e.nachrichten_id == "e1@x.de" and e.in_reply_to == "v@laser.example" and len(e.referenzen) == 2
ok("E2 .eml: dieselben Kopfzeilen")

# ------------------------------------------------------------------ E3 direkte Mail
r = z(m)
assert r["stufe"] == mz.EINDEUTIG and r["kundennr"] == "10001" and r["art"] == mz.DIREKT, r
assert r["ansprechpartner"] == "Hans Krüger" and r["postfach"] == "anfrage@laser.example", r
assert any("steht beim Kunden" in k for k in r["kriterien"]) and r["zustaendig"] == "PB", r
assert r["internet_id"] == "abc123@krueger-metall.de"
ok("E3 direkte Mail, Adresse beim Kunden: eindeutig, Ansprechpartner, eigenes Postfach, Zuständiger, Kriterien")

# ------------------------------------------------------------------ E4/E5 weitergeleitet im Text
WG = ("Hallo Patrick, bitte anbieten, eilt.\nGruß Max\n\n________________________________\n"
      "Von: Hans Neumann <h.neumann@stahlbau-neumann.de>\nGesendet: Mittwoch, 18. November 2026 16:40\n"
      "An: info@laser.example\nBetreff: Anfrage Gestell\n\nBitte 5 Gestelle anbieten." + SIG_NEUMANN)
m4 = m_aus(t.msg("WG: Anfrage Gestell", WG, "Max Kollege", "max@laser.example", D))
r = z(m4)
assert r["art"] == mz.WEITERGELEITET and r["original"]["adresse"] == "h.neumann@stahlbau-neumann.de", r
assert [w["adresse"] for w in r["weiterleiter"]] == ["max@laser.example"], r["weiterleiter"]
assert r["postfach"] == "info@laser.example" and r["ansprechpartner"] == "Hans Neumann", r
assert r["stufe"] == mz.EINDEUTIG and r["kundennr"] == "10002", r     # Domain + Firma/Telefon in der Signatur
assert all("max" not in str(v.get("gruende")) for v in r["vorschlaege"])
ok("E4 intern weitergeleitet: Kunde aus der Mail des Kunden, Kollege nur als Weiterleiter, Postfach info@")

KETTE = ("Patrick, kannst du das machen?\nEva\n\n-----Ursprüngliche Nachricht-----\nVon: Max Kollege "
         "<max@laser.example>\nGesendet: 19.11.2026 08:00\nAn: eva@laser.example\nBetreff: WG: Anfrage Gestell\n\n"
         + WG)
r = z(m_aus(t.msg("WG: WG: Anfrage Gestell", KETTE, "Eva Vertrieb", "eva@laser.example", D)))
assert [w["adresse"] for w in r["weiterleiter"]] == ["eva@laser.example", "max@laser.example"], r["weiterleiter"]
assert r["original"]["adresse"] == "h.neumann@stahlbau-neumann.de" and r["kundennr"] == "10002", r
ok("E5 mehrfach weitergeleitet: Kette Eva → Max → Kunde, Kunde bleibt der Kunde")

# ------------------------------------------------------------------ E6 als Anlage weitergeleitet
innen = dict(betreff="Anfrage Rohrrahmen", text="Bitte anbieten." + SIG_NEUMANN, absender_name="Hans Neumann",
             absender="einkauf@stahlbau-neumann.de", datum=D - datetime.timedelta(hours=3), anhaenge=[],
             an=[("Vertrieb", "vertrieb@laser.example")], ids={0x1035: "<orig42@stahlbau-neumann.de>"})
m6 = m_aus(t.msg("WG: Anfrage Rohrrahmen", "Siehe Anhang.\nMax", "Max Kollege", "max@laser.example", D,
                 anhaenge=[("Anfrage.msg", innen)]))
r = z(m6)
assert r["art"] == mz.WEITERGELEITET and r["kundennr"] == "10002" and r["stufe"] == mz.EINDEUTIG, r
assert r["postfach"] == "vertrieb@laser.example" and r["internet_id"] == "orig42@stahlbau-neumann.de", r
ok("E6 als Anlage weitergeleitet: Original-Mail mit Empfänger und Message-ID ausgewertet")

# ------------------------------------------------------------------ E7 Sammelpostfach des Kunden
r = z(m_aus(t.msg("Anfrage", "Bitte anbieten.", "info", "info@krueger-metall.de", D)))
assert r["kundennr"] == "10001" and r["ansprechpartner"] == "" and r["zentral"], r
assert any("Sammelpostfach" in h for h in r["hinweise"]), r["hinweise"]
ok("E7 Sammelpostfach des Kunden: Kunde erkannt, kein Ansprechpartner (Hinweis)")

# ------------------------------------------------------------------ E8/E9 Domain allein bzw. mit Signatur
r = z(m_aus(t.msg("Anfrage", "Bitte anbieten.", "Otto Neu", "o.neu@krueger-metall.de", D)))
assert r["stufe"] == mz.WAHRSCHEINLICH and r["kundennr"] == "" and r["vorschlaege"][0]["kundennr"] == "10001", r
k = ak.mail_kopf({}, m_aus(t.msg("Anfrage", "Bitte anbieten.", "Otto Neu", "o.neu@krueger-metall.de", D)), KUNDEN,
                 EIGEN, FIRMA, regeln=[])
assert not k.get("kundennr") and k["zuordnung"]["stufe"] == mz.WAHRSCHEINLICH, k
ok("E8 nur die Domain passt: wahrscheinlich, keine Kundennummer, Kunde nur als Vorschlag")
r = z(m_aus(t.msg("Anfrage", "Bitte anbieten.\n\nMit freundlichen Grüßen\nOtto Neu\nMetallbau Krüger GmbH\n",
                  "Otto Neu", "o.neu@krueger-metall.de", D)))
assert r["stufe"] == mz.EINDEUTIG and r["kundennr"] == "10001" and len(r["vorschlaege"][0]["gruende"]) >= 2, r
ok("E9 Domain plus Firmenname in der Signatur: eindeutig")

# ------------------------------------------------------------------ E10/E11 mehrdeutig, unbekannt
r = z(m_aus(t.msg("Anfrage", "Bitte anbieten.", "Agentur", "sammel@agentur.example", D)))
assert r["stufe"] == mz.MEHRDEUTIG and r["kundennr"] == "" and len(r["vorschlaege"]) == 2, r
ok("E10 dieselbe Adresse bei zwei Kunden: mehrdeutig, keine Kundennummer")
r = z(m_aus(t.msg("Anfrage", "Bitte anbieten.", "Privat", "max.muster@gmail.com", D)))
assert r["stufe"] == mz.UNBEKANNT and r["kundennr"] == "" and not r["vorschlaege"], r
ok("E11 Freemail-Absender ohne Treffer: nicht erkannt (zur Prüfung)")

# ------------------------------------------------------------------ E12 interne Anfrage
m12 = m_aus(t.msg("Anfrage für Krüger", "Patrick, Metallbau Krüger braucht 20 Rahmen wie letztes Mal, bitte "
                  "anbieten.\nGruß Max", "Max Kollege", "max@laser.example", D))
r = z(m12)
assert r["art"] == mz.INTERN and r["anfragender_intern"]["adresse"] == "max@laser.example", r
assert r["kundennr"] == "" and r["stufe"] != mz.EINDEUTIG and r["ansprechpartner"] == "", r
assert r["vorschlaege"] and r["vorschlaege"][0]["kundennr"] == "10001", r
k = ak.mail_kopf({}, m12, KUNDEN, EIGEN, FIRMA, regeln=[])
assert k["absender"] == "" and not k.get("kundennr"), k
r = z(m_aus(t.msg("Teile für Halle 3", "Bitte 4 Stützen für unsere Halle.\nMax", "Max", "max@laser.example", D)))
assert r["art"] == mz.INTERN and not r["vorschlaege"] and r["stufe"] == mz.UNBEKANNT, r
ok("E12 interne Anfrage: Kollege nie Kunde/Ansprechpartner, genannter Kunde nur Vorschlag, sonst zur Prüfung")

# ------------------------------------------------------------------ E13 Lernregeln
wurzel = tmp / "akten"
regel = mz.regel_anlegen(wurzel, "adresse", "o.neu@krueger-metall.de", "10001", "Metallbau Krüger GmbH", von="PB")
mz.regel_anlegen(wurzel, "nie", "sammel@agentur.example", von="PB")
mz.regel_anlegen(wurzel, "intern", "max.privat@gmail.com", von="PB")
regeln = mz.regeln_lesen(wurzel)
assert len(regeln) == 3 and all(mz.regel_text(x) for x in regeln)
r = z(m_aus(t.msg("Anfrage", "Bitte anbieten.", "Otto Neu", "o.neu@krueger-metall.de", D)), regeln)
assert r["stufe"] == mz.EINDEUTIG and r["kundennr"] == "10001" and any("Regel" in x for x in r["kriterien"]), r
r = z(m_aus(t.msg("WG: Anfrage", WG, "Max", "max.privat@gmail.com", D)), regeln)
assert r["art"] == mz.WEITERGELEITET and r["kundennr"] == "10002", r      # private Adresse des Kollegen = intern
assert mz.regel_loeschen(wurzel, regel["id"]) == 1 and len(mz.regeln_lesen(wurzel)) == 2
r = z(m_aus(t.msg("Anfrage", "Bitte anbieten.", "Otto Neu", "o.neu@krueger-metall.de", D)), mz.regeln_lesen(wurzel))
assert r["stufe"] == mz.WAHRSCHEINLICH, r
ok("E13 Lernregeln: Adresse → Kunde, interne Adresse, sichtbar als Text und löschbar")

# ------------------------------------------------------------------ E14 Outlook-Abruf: Dubletten, Antwort, Protokoll
abl = ak.OrdnerAblage(tmp / "akten14", "PB", platz="BUERO1")
ou = Outlook()
direkt = t.msg("Anfrage Gestell", "Bitte 5 Gestelle anbieten." + SIG_NEUMANN, "Hans Neumann",
               "einkauf@stahlbau-neumann.de", D, an=[("Info", "info@laser.example")],
               ids={0x1035: "<g1@stahlbau-neumann.de>"})
ou.mail("<g1@stahlbau-neumann.de>", "", "", "x@y.de", roh=direkt)
erg = ol.abrufen(abl, "Anfragen", KUNDEN, ausfuehren=ou, eigene=EIGEN, firma=FIRMA)
assert len(erg["neu"]) == 1, erg
a1 = erg["neu"][0]
assert a1.kunde == "10002" and a1.zuordnung["stufe"] == mz.EINDEUTIG, a1.kopf
auto = [e for e in a1.verlauf if e.get("aktion") == ak.ZUORDNUNG and e.get("feld") == "automatisch"]
assert auto and auto[0]["adresse"] == "einkauf@stahlbau-neumann.de" and auto[0]["kriterien"], auto
assert auto[0]["nachrichten_id"] == "<g1@stahlbau-neumann.de>" and "eindeutig" in ak.verlauf_text(auto[0])
# derselbe Kunde, dieselbe Mail: von Max zusätzlich als Anlage weitergeleitet
innen2 = dict(betreff="Anfrage Gestell", text="Bitte 5 Gestelle anbieten." + SIG_NEUMANN, absender_name="Hans Neumann",
              absender="einkauf@stahlbau-neumann.de", datum=D, anhaenge=[], ids={0x1035: "<g1@stahlbau-neumann.de>"})
ou.mail("<w9@laser.example>", "", "", "x@y.de",
        roh=t.msg("WG: Anfrage Gestell", "bitte anbieten\nMax", "Max", "max@laser.example", D, [("a.msg", innen2)]))
erg = ol.abrufen(abl, "Anfragen", KUNDEN, ausfuehren=ou, eigene=EIGEN, firma=FIRMA)
assert not erg["neu"] and len(erg.get("doppelt", [])) == 1 and erg["doppelt"][0].nr == a1.nr, erg
assert len(abl.alle()) == 1
# Antwort des Kunden ohne AW: im Betreff, nur über In-Reply-To
ou.mail("<g2@stahlbau-neumann.de>", "", "", "x@y.de",
        roh=t.msg("Zeichnung zum Gestell", "anbei die Zeichnung", "Hans Neumann", "einkauf@stahlbau-neumann.de",
                  D + datetime.timedelta(hours=2), [("Gestell.pdf", b"%PDF-1.4 x")],
                  ids={0x1042: "<g1@stahlbau-neumann.de>"}))
erg = ol.abrufen(abl, "Anfragen", KUNDEN, ausfuehren=ou, eigene=EIGEN, firma=FIRMA)
assert not erg["neu"] and [a.nr for a in erg["antworten"]] == [a1.nr], erg
assert len(abl.alle()) == 1 and any(d["name"] == "Gestell.pdf" for d in abl.lesen(a1.nr).dateien())
ok("E14 Abruf: zweiter Weg derselben Mail = keine zweite Anfrage, Antwort über In-Reply-To, Zuordnung im Verlauf")

# ------------------------------------------------------------------ E15 Korrekturen von Hand, sichere Antwort
abl15 = ak.OrdnerAblage(tmp / "akten15", "PB", platz="BUERO1")
ou15 = Outlook()
ou15.mail("<o1@krueger-metall.de>", "", "", "x@y.de",
          roh=t.msg("Anfrage", "Bitte anbieten.", "Otto Neu", "o.neu@krueger-metall.de", D))
a = ol.abrufen(abl15, "Anfragen", KUNDEN, ausfuehren=ou15, eigene=EIGEN, firma=FIRMA)["neu"][0]
assert a.kunde == "" and a.kunde_pruefen(), a.kopf
a = abl15.zuordnung_aendern(a, "bestaetigt", "10001", "Metallbau Krüger GmbH")
assert a.kunde == "10001" and not a.kunde_pruefen() and a.zuordnung["stufe"] == mz.EINDEUTIG
a = abl15.zuordnung_aendern(a, "kunde", "10002", "Stahlbau Neumann GmbH", grund="falsch erkannt")
a = abl15.zuordnung_aendern(a, "ansprechpartner", "Herr Neu")
a = abl15.zuordnung_aendern(a, "absender", "otto@neumann.example", "Otto Neu")
assert a.kunde == "10002" and a.zuordnung["ansprechpartner"] == "Herr Neu" and a.absender_adresse == "otto@neumann.example"
texte = [ak.verlauf_text(e) for e in a.verlauf if e.get("aktion") == ak.ZUORDNUNG]
assert any("10001 → 10002" in x and "falsch erkannt" in x for x in texte), texte
a = abl15.zuordnung_aendern(a, "ohne_kunde")
assert a.kunde == "" and a.zuordnung.get("ohne_kunde") and not a.kunde_pruefen()
a = abl15.zuordnung_aendern(a, "zuruecksetzen")
assert a.kunde == "" and a.kunde_pruefen() and a.absender_adresse == "o.neu@krueger-metall.de"
assert len([e for e in a.verlauf if e.get("aktion") == ak.ZUORDNUNG]) == 7      # automatisch + 6 von Hand
an, antwort, grund = mz.antwort_ziel(m4, EIGEN, FIRMA)
assert an == "h.neumann@stahlbau-neumann.de" and not antwort and "intern" in grund.lower()
an, antwort, _ = mz.antwort_ziel(m12, EIGEN, FIRMA)
assert an == "" and not antwort
an, antwort, _ = mz.antwort_ziel(m, EIGEN, FIRMA)
assert an == "angebote@krueger-metall.de" and antwort          # Reply-To des Kunden
dub = mz.kunden_dubletten(KUNDEN, dict(name="Metallbau Krüger", email="neu@krueger-metall.de"))
assert [k["kundennr"] for k, _ in dub] == ["10001"], dub
ok("E15 Korrekturen von Hand im Verlauf (auch zurücksetzen), Antwort nie auf die interne Weiterleitung, "
   "Kunden-Dubletten vor dem Anlegen")
print("Alle Tests bestanden.")
