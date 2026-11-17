"""Outlook-Abruf: keine Mail geht verloren (Patrick 17.11.2026 „Es können keine E-Mails im Outlook verloren gehen?
Absichern“).

Geprüft mit dem nachgebauten Outlook (tests/outlook_nachbau.py) und am Text der PowerShell-Skripte, nur erfundene
Testmails:
  K1 Die Skripte löschen in Outlook nie etwas (kein Delete, keine Papierkorb-Ordner), sie verschieben nur.
  K2 Eine Mail wird erst verschoben, wenn ihre Kopie gesichert und nicht leer ist; sonst bleibt sie im Eingang.
  K3 Eine unlesbare Mail wird trotzdem Akte („Mail nicht lesbar“) und hält den Abruf der anderen nicht auf.
  K4 Scheitert das Anlegen der Akte, bleibt die Mail in Outlook (Neu) und wird beim nächsten Abruf nachgeholt.
  K5 Mails ohne Internet-Nachrichten-ID haben einen Schlüssel, der beim Verschieben gleich bleibt (nicht die EntryID).
  K6 Einträge, die keine Mail sind, bleiben im Eingang; ihre Zahl wird gemeldet.

Aufruf: python tests/test_outlook_kein_verlust.py
"""
import datetime
import re
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
from outlook_nachbau import Outlook  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import outlook_anfragen as ol  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
JETZT = datetime.datetime.now().replace(microsecond=0)

# ------------------------------------------------------------------ K1 nie löschen
for skript in (ol.ABRUF_PS, ol.WAEHLEN_PS, ol.KATEGORIEN_PS):
    assert not re.search(r"\.(Delete|PermanentDelete)\s*\(", skript, re.I), "Skript darf nichts löschen"
    assert "GetDefaultFolder(3)" not in skript and "GetDefaultFolder(23)" not in skript   # Gelöschte/Junk
assert ol.ABRUF_PS.count(".Move(") == 2 and "Remove-Item" not in ol.ABRUF_PS
ok("K1 die Outlook-Skripte löschen nie etwas, sie verschieben nur zwischen den gewählten Ordnern")

# ------------------------------------------------------------------ K2 erst gesichert, dann verschoben
s = ol.ABRUF_PS
assert s.index("$m.SaveAs($datei, 9)") < s.index("Length -eq 0") < s.index("[void]$m.Move($unter[$d.unter[0]])")
assert "try { Sichern $m $k; [void]$m.Move(" in s       # Fehler beim Sichern = kein Verschieben
abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")
ou = Outlook()
ou.mail("<k1@kunde.example>", "Anfrage Gestell", "Bitte 2 Gestelle.", "kauf@kunde.example")
ou.mail("<k2@kunde.example>", "Anfrage Halter", "Bitte 5 Halter.", "kauf@kunde.example")
ou.nicht_sicherbar = {"<k2@kunde.example>"}
erg = ol.abrufen(abl, "Anfragen", ausfuehren=ou, jetzt=JETZT)
assert ou.wo("<k2@kunde.example>") == "" and ou.wo("<k1@kunde.example>") == "Neu"
assert any("nicht gesichert" in f for f in erg["fehler"]) and len(erg["neu"]) == 1, erg
ou.nicht_sicherbar = set()
erg = ol.abrufen(abl, "Anfragen", ausfuehren=ou, jetzt=JETZT)
assert ou.wo("<k2@kunde.example>") == "Neu" and [a.betreff for a in erg["neu"]] == ["Anfrage Halter"], erg
ok("K2 Kopie nicht gesichert: Mail bleibt im Eingang und kommt beim nächsten Abruf")

# ------------------------------------------------------------------ K3 unlesbare Mail hält nichts auf
alt = ol.kopf_aus_mail


def kaputt(pfad, mid, eingang="", kunden=()):
    if mid == "<k3@kunde.example>":
        raise ValueError("Mail beschädigt")
    return alt(pfad, mid, eingang, kunden)


ol.kopf_aus_mail = kaputt
try:
    ou.mail("<k3@kunde.example>", "Kaputt", "…", "a@kunde.example")
    ou.mail("<k4@kunde.example>", "Anfrage Rahmen", "Bitte 3 Rahmen.", "kauf@kunde.example")
    erg = ol.abrufen(abl, "Anfragen", ausfuehren=ou, jetzt=JETZT)
finally:
    ol.kopf_aus_mail = alt
assert sorted(a.betreff for a in erg["neu"]) == ["Anfrage Rahmen", "Mail nicht lesbar"], erg
assert ou.wo("<k3@kunde.example>") == "Neu" and ou.wo("<k4@kunde.example>") == "Neu"
k3 = next(a for a in abl.alle() if a.kopf.get("nachrichten_id") == "<k3@kunde.example>")
assert any(d["art"] == "mail" for d in k3.dateien())                 # die Mail selbst liegt in der Akte
ok("K3 unlesbare Mail: wird Akte „Mail nicht lesbar“ mit der Mail, die anderen Mails kommen trotzdem")

# ------------------------------------------------------------------ K4 Akte scheitert: nachholen
anlegen = abl.anlegen
abl.anlegen = lambda *a, **k: (_ for _ in ()).throw(ak.AblageFehler("Ordner gesperrt"))
try:
    ou.mail("<k5@kunde.example>", "Anfrage Konsole", "Bitte 4 Konsolen.", "kauf@kunde.example")
    erg = ol.abrufen(abl, "Anfragen", ausfuehren=ou, jetzt=JETZT)
finally:
    abl.anlegen = anlegen
assert not erg["neu"] and any("nachgeholt" in f for f in erg["fehler"]) and ou.wo("<k5@kunde.example>") == "Neu", erg
assert "<k5@kunde.example>" in ol.stand_lesen(abl)
erg = ol.abrufen(abl, "Anfragen", ausfuehren=ou, jetzt=JETZT)
assert [a.betreff for a in erg["neu"]] == ["Anfrage Konsole"], erg
assert ou.wo("<k5@kunde.example>") == "Neu"
ok("K4 Akte nicht angelegt: Mail bleibt in Neu, Fehler wird gemeldet, beim nächsten Abruf nachgeholt")

# ------------------------------------------------------------------ K5 Schlüssel ohne Nachrichten-ID
mid = re.search(r"function Mid\(\$m\) \{.*\}", ol.ABRUF_PS).group(0)
assert "'ohne:'" in mid and "ReceivedTime" in mid and "EntryID" not in mid
ok("K5 Mails ohne Nachrichten-ID: Schlüssel aus Eingang, Absender, Betreff (bleibt beim Verschieben gleich)")

# ------------------------------------------------------------------ K6 Nicht-Mails bleiben, werden gezählt
assert "$aus.andere++" in ol.ABRUF_PS
ou.andere = 2
erg = ol.abrufen(abl, "Anfragen", ausfuehren=ou, jetzt=JETZT)
assert erg["andere"] == 2 and not erg["fehler"], erg
ok("K6 Termine, Lesebestätigungen usw. bleiben im Eingang, ihre Zahl wird gemeldet")
print("Alle Tests bestanden.")
