"""Anfragen aus dem klassischen Outlook am PC (Anfragenverwaltung Paket 2, Freigabe Patrick 13.11.2026).

Ohne Azure, ohne Anmeldung bei Microsoft: das Programm spricht über PowerShell (COM) mit dem klassischen Outlook
dieses Rechners, wie schon „In Outlook öffnen“ (materialanfrage.outlook_oeffnen). Das neue Outlook hat diese
Schnittstelle nicht.

Ablauf je Abruf (Takt TAKT_S, nur auf dem Rechner, der abruft):
  1. Mails, deren Akte im Programm den Status gewechselt hat, in den passenden Unterordner verschieben
     (Programm -> Outlook).
  2. Mails direkt im Ordner „Anfragen“ als .msg sichern und nach „Anfragen\\Neu“ verschieben; jede wird eine Akte
     (Doppel-Schutz über die Internet-Nachrichten-ID, Schlüssel outlook-<SHA>).
  3. Die Unterordner Neu, In Bearbeitung, Erledigt auflisten. Hat jemand eine Mail in Outlook verschoben, folgt die
     Akte (Outlook -> Programm): nach „In Bearbeitung“ = übernommen, nach „Erledigt“ = erledigt, zurück nach „Neu“
     = zurückgegeben. Haben beide Seiten gleichzeitig geändert, gilt das Programm.

Nur ein Rechner ruft ab: Einstellung EIN (an diesem Arbeitsplatz) und die Abruf-Marke _outlook/abruf.marke im
Akten-Ordner (gilt LEASE_S Sekunden, wird bei jedem Abruf erneuert). Der letzte bekannte Outlook-Ordner jeder Mail
steht in _outlook/stand.json (schreibt nur der abrufende Rechner). Es wird nie etwas gelöscht oder gesendet.

Ordner und Kategorien (Patrick 16.11.2026, Freigabe „Alle Empfehlungen“): Eingang, Neu, In Bearbeitung und Erledigt
lassen sich einzeln wählen (Outlook-Ordnerauswahl, auch in einem anderen Postfach; gespeichert wird der Outlook-Pfad
wie „Postfach > Posteingang > Anfragen“); leer = wie bisher Unterordner des Eingangs. Eine Outlook-Kategorie steht für einen Mitarbeiter
(Zuordnung im Fenster „Outlook …“, sonst automatisch: Kategorie heißt wie Kürzel, Name oder ein Teil des Namens):
Kategorie an der Mail gesetzt = Anfrage diesem Mitarbeiter zugewiesen (bleibt in Neu, F1 a); im Programm zugewiesen
oder übernommen = das Programm setzt die Kategorie an der Mail, andere Kategorien bleiben (F2 a). Zwei Mitarbeiter-
Kategorien an einer Mail: die zuletzt gesetzte gilt, Hinweis im Verlauf (F3 a). Erledigte Anfragen bleiben, wie sie
sind. Der zuletzt gesehene Stand der Kategorien je Mail steht in _outlook/kategorien_stand.json, die Kategorien des
Postfachs in _outlook/kategorien.json.

Andere Postfächer (Patrick 17.11.2026): zu jedem über die Outlook-Auswahl gewählten Ordner merkt sich das Programm
auch dessen feste Outlook-Kennung (EntryID + StoreID, Einstellung ORDNER_IDS). Beim Abruf wird der Ordner zuerst
über diese Kennung geöffnet (Namespace.GetFolderFromID), erst dann über den Pfad. So klappen auch Ordner, die nur
als „Freigegebener Ordner“ eines anderen Benutzers sichtbar sind und nicht als eigenes Postfach in der Liste
stehen.

Keine Mail geht verloren (Patrick 17.11.2026 „Absichern“): das Programm löscht in Outlook nie etwas, es verschiebt
nur zwischen den gewählten Ordnern. Eine Mail wird erst verschoben, wenn ihre Kopie als .msg gesichert und nicht leer
ist. Klappt das Anlegen der Akte nicht (auch bei einer unlesbaren Mail), bleibt die Mail in „Neu“ und wird beim nächsten
Abruf nachgeholt; eine unlesbare Mail wird trotzdem Akte („Mail nicht lesbar“) und hält den Abruf nie auf. Mails ohne
Internet-Nachrichten-ID bekommen einen Schlüssel aus Eingang, Absender und Betreff, der beim Verschieben gleich bleibt
(die EntryID ändert sich in Exchange beim Verschieben). Einträge, die keine Mail sind (Termin, Lesebestätigung,
Unzustellbar), bleiben unberührt im Eingang; ihre Zahl steht im Fenster „Outlook …“."""
import datetime
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from . import anfragen_akten as ak

EIN = "outlook_abruf"            # ja/nein: dieser Rechner holt Anfragen aus Outlook (Vorgabe nein)
ORDNER_EINSTELLUNG = "outlook_ordner"
ORDNER_VORGABE = "Anfragen"
# Outlook-Pfade der drei Ordner (leer = Unterordner des Eingangs mit dem Namen aus UNTER)
PFAD_EINSTELLUNG = {"neu": "outlook_ordner_neu", "bearbeitung": "outlook_ordner_bearbeitung",
                    "erledigt": "outlook_ordner_erledigt"}
ORDNER_IDS = "outlook_ordner_ids"     # JSON {Outlook-Pfad: {"e": EntryID, "s": StoreID}} der gewählten Ordner
KATEGORIEN_EINSTELLUNG = "outlook_kategorien"   # JSON {Kategorie: Kürzel oder "" (kein Mitarbeiter)}
UNTER = {ak.NEU: "Neu", ak.BEARBEITUNG: "In Bearbeitung", ak.ERLEDIGT: "Erledigt"}
STATUS_ZU = {v: k for k, v in UNTER.items()}
TAKT_S = 60
LEASE_S = 300
ERLEDIGT_TAGE = 90               # Erledigt-Ordner nur so weit zurück auflisten
HOECHSTENS = 50                  # neue Mails je Abruf (der Rest beim nächsten Mal)
STAMM = "_outlook"


def an(db):
    return (db.einstellung(EIN) or "nein") == "ja"


def ordner(db):
    return (db.einstellung(ORDNER_EINSTELLUNG) or "").strip() or ORDNER_VORGABE


def unter_pfade(db):
    """[Pfad Neu, Pfad In Bearbeitung, Pfad Erledigt] (leer = Unterordner des Eingangs)."""
    return [(db.einstellung(PFAD_EINSTELLUNG[k]) or "").strip() for k in ("neu", "bearbeitung", "erledigt")]


def ordner_ids(db):
    """Feste Outlook-Kennungen der gewählten Ordner {Pfad: {"e": EntryID, "s": StoreID}}."""
    try:
        z = json.loads(db.einstellung(ORDNER_IDS) or "{}")
    except ValueError:
        return {}
    if not isinstance(z, dict):
        return {}
    return {str(k): dict(e=str(v.get("e") or ""), s=str(v.get("s") or "")) for k, v in z.items()
            if isinstance(v, dict) and v.get("e")}


def ordner_id_merken(db, pfad, entry_id, store_id=""):
    """Kennung zu einem gewählten Ordner speichern; nicht mehr benutzte Pfade fallen dabei heraus."""
    benutzt = {ordner(db), *unter_pfade(db), str(pfad)}
    z = {k: v for k, v in ordner_ids(db).items() if k in benutzt}
    if entry_id:
        z[str(pfad)] = dict(e=str(entry_id), s=str(store_id or ""))
    else:
        z.pop(str(pfad), None)
    db.einstellung_setzen(ORDNER_IDS, json.dumps(z, ensure_ascii=False, sort_keys=True))


def zuordnung(db):
    """Von Hand festgelegte Zuordnung {Kategorie: Kürzel oder ""}."""
    try:
        z = json.loads(db.einstellung(KATEGORIEN_EINSTELLUNG) or "{}")
    except ValueError:
        return {}
    return {str(k): str(v or "") for k, v in z.items()} if isinstance(z, dict) else {}


def zuordnung_setzen(db, kategorie, kuerzel):
    z = zuordnung(db)
    z[str(kategorie)] = str(kuerzel or "")
    db.einstellung_setzen(KATEGORIEN_EINSTELLUNG, json.dumps(z, ensure_ascii=False, sort_keys=True))


def pfad_name(pfad):
    """Kurzer Name eines Outlook-Pfads für Anzeige und Verlauf (letzter Teil)."""
    return str(pfad or "").rstrip("\\").split("\\")[-1]


# ------------------------------------------------------------------ Kategorien = Mitarbeiter
def kat_liste(wert):
    """Kategorien einer Mail als Liste (Outlook trennt mit dem Listentrennzeichen, „,“ oder „;“)."""
    if not wert:
        return []
    if isinstance(wert, str):
        import re
        return [t.strip() for t in re.split(r"[,;]", wert) if t.strip()]
    return [str(t).strip() for t in wert if str(t).strip()]


def kat_kuerzel(kat, zu=None, mitarbeiter=None):
    """Kürzel zur Kategorie oder "": von Hand zugeordnet, sonst automatisch (Kategorie = Kürzel, Name oder genau ein
    Wort aus genau einem Namen, Groß-/Kleinschreibung egal)."""
    zu, mitarbeiter = zu or {}, mitarbeiter or {}
    if kat in zu:
        return zu[kat]
    k = str(kat).strip().casefold()
    if not k:
        return ""
    for kz, name in mitarbeiter.items():
        if k == str(kz).casefold() or (name and k == str(name).strip().casefold()):
            return kz
    treffer = [kz for kz, name in mitarbeiter.items() if name and k in str(name).casefold().split()]
    return treffer[0] if len(treffer) == 1 else ""


def kuerzel_kat(kuerzel, bekannte, zu=None, mitarbeiter=None):
    """Kategorie, die für den Mitarbeiter steht (von Hand zugeordnet vor automatisch), oder ""."""
    if not kuerzel:
        return ""
    for kat in list((zu or {}).keys()) + [k for k in bekannte if k not in (zu or {})]:
        if kat_kuerzel(kat, zu, mitarbeiter) == kuerzel:
            return kat
    return ""


def schluessel(mid):
    return "outlook-" + hashlib.sha256(str(mid).strip().encode("utf-8")).hexdigest()[:40]


# ------------------------------------------------------------------ Abruf-Marke (ein Rechner)
def _marke(abl):
    return Path(abl.wurzel) / STAMM / "abruf.marke"


def marke_lesen(abl):
    try:
        return json.loads(_marke(abl).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def marke_nehmen(abl, platz=None, jetzt=None):
    """Abruf-Marke nehmen oder erneuern. Ergebnis: (True, None) oder (False, Marke des anderen Rechners)."""
    jetzt = jetzt or datetime.datetime.now()
    platz = platz or abl.platz or socket.gethostname()
    m = marke_lesen(abl)
    if m and m.get("platz") != platz:
        try:
            alt = datetime.datetime.fromisoformat(m.get("zeit", ""))
        except ValueError:
            alt = None
        if alt and (jetzt - alt).total_seconds() < LEASE_S:
            return False, m
    p = _marke(abl)
    p.parent.mkdir(parents=True, exist_ok=True)
    neu = dict(platz=platz, kuerzel=abl.kuerzel, zeit=ak._jetzt(jetzt))
    tmp = p.with_name(f"abruf.{ak._sauber(platz)}.tmp")
    tmp.write_text(json.dumps(neu), encoding="utf-8")
    tmp.replace(p)
    m = marke_lesen(abl)                 # zwei gleichzeitig: wessen Marke liegt, der ruft ab
    return (bool(m) and m.get("platz") == platz), m


def marke_abgeben(abl, platz=None):
    m = marke_lesen(abl)
    if m and m.get("platz") == (platz or abl.platz):
        try:
            _marke(abl).unlink()
        except OSError:
            pass


def _stand_pfad(abl):
    return Path(abl.wurzel) / STAMM / "stand.json"


def stand_lesen(abl):
    try:
        s = json.loads(_stand_pfad(abl).read_text(encoding="utf-8"))
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def _json_lesen(p, leer):
    try:
        s = json.loads(Path(p).read_text(encoding="utf-8"))
        return s if isinstance(s, type(leer)) else leer
    except (OSError, ValueError):
        return leer


def _json_schreiben(p, wert):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(wert, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def kategorien_lesen(abl):
    """Kategorien des Postfachs vom letzten Abruf (für die Zuordnung im Fenster „Outlook …“)."""
    return [str(k) for k in _json_lesen(Path(abl.wurzel) / STAMM / "kategorien.json", [])]


def kategorien_schreiben(abl, liste):
    _json_schreiben(Path(abl.wurzel) / STAMM / "kategorien.json", sorted({str(k) for k in liste if str(k).strip()}))


def stand_schreiben(abl, stand):
    p = _stand_pfad(abl)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(stand, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


# ------------------------------------------------------------------ PowerShell (klassisches Outlook, COM)
ABRUF_PS = r"""
$ErrorActionPreference = 'Stop'
$d = Get-Content -Raw -Encoding UTF8 -LiteralPath $args[0] | ConvertFrom-Json
$o = New-Object -ComObject Outlook.Application
$ns = $o.GetNamespace('MAPI')
$MID = 'http://schemas.microsoft.com/mapi/proptag/0x1035001F'
function Suchen($wurzel, $name) { foreach ($f in $wurzel.Folders) { if ($f.Name -eq $name) { return $f } }; return $null }
function Pfad($p) {
    if ($d.ids) { $k = $d.ids.PSObject.Properties[$p]; if ($k) { try { if ($k.Value.s) { return $ns.GetFolderFromID($k.Value.e, $k.Value.s) } else { return $ns.GetFolderFromID($k.Value.e) } } catch { } } }
    $t = $p.TrimStart('\').Split('\'); $f = $null; foreach ($s in $ns.Folders) { if ($s.Name -eq $t[0]) { $f = $s } }; for ($i = 1; $i -lt $t.Length -and $f; $i++) { $f = Suchen $f $t[$i] }; return $f }
$sep = (Get-Culture).TextInfo.ListSeparator + ' '
function Kats($m) { $c = [string]$m.Categories; if (-not $c) { return @() }; return @($c -split '\s*[,;]\s*' | Where-Object { $_ }) }
function Mid($m) { $k = ''; try { $k = [string]$m.PropertyAccessor.GetProperty($MID) } catch { }; if (-not $k) { $s = ''; try { $s = [string]$m.SenderEmailAddress } catch { }; $k = 'ohne:' + $m.ReceivedTime.ToString('s') + '|' + $s + '|' + [string]$m.Subject }; return $k }
$inbox = $ns.GetDefaultFolder(6)
$wurzel = $inbox.Parent
$a = $null
if ($d.ordner.StartsWith('\\')) { $a = Pfad $d.ordner }
elseif ($d.ordner.Contains('\')) { $a = $wurzel; foreach ($t in $d.ordner.Split('\')) { if ($a) { $a = Suchen $a $t } } }
else { $a = Suchen $inbox $d.ordner; if (-not $a) { $a = Suchen $wurzel $d.ordner } }
if (-not $a) { throw ("Outlook-Ordner '" + $d.ordner + "' nicht gefunden (im Fenster Outlook … neu wählen)") }
$unter = @{}
for ($i = 0; $i -lt $d.unter.Count; $i++) {
    $n = $d.unter[$i]; $p = ''; if ($d.unter_pfade) { $p = [string]$d.unter_pfade[$i] }
    if ($p) { $u = Pfad $p; if (-not $u) { throw ("Outlook-Ordner '" + $p + "' nicht gefunden (im Fenster Outlook … neu wählen)") } }
    else { $u = Suchen $a $n; if (-not $u) { $u = $a.Folders.Add($n) } }
    if ($u.EntryID -eq $a.EntryID) { throw ("Outlook-Ordner '" + $n + "' ist derselbe wie der Eingang") }
    $unter[$n] = $u
}
$aus = @{ neu = @(); liste = @(); verschoben = @(); fehler = @(); kat_gesetzt = @(); kategorien = @(); andere = 0 }
try { $aus.kategorien = @(foreach ($c in $ns.Categories) { [string]$c.Name }) } catch { }
$wunsch = @{}; foreach ($v in $d.verschieben) { $wunsch[$v.mid] = $v.nach }
$katw = @{}; foreach ($v in $d.kategorien) { $katw[$v.mid] = $v }
$hol = @{}; foreach ($k in $d.nachholen) { $hol[$k] = 1 }
$grenze = (Get-Date).AddDays(-[int]$d.tage)
$nr = 0
function Sichern($m, $k) {
    $script:nr++
    $datei = Join-Path $d.ziel ('mail_' + $script:nr + '.msg')
    $m.SaveAs($datei, 9)
    if (-not (Test-Path -LiteralPath $datei) -or (Get-Item -LiteralPath $datei).Length -eq 0) { throw 'Kopie der Mail nicht gesichert, Mail bleibt, wo sie ist' }
    $kv = ''; try { $kv = [string]$m.ConversationID } catch { }
    $script:aus.neu += @{ mid = $k; datei = $datei; eingang = $m.ReceivedTime.ToString('s'); konversation = $kv }
}
# 1. Programm -> Outlook
if ($wunsch.Count -gt 0 -or $katw.Count -gt 0) {
    foreach ($n in $d.unter) {
        foreach ($m in @($unter[$n].Items)) {
            if ($m.Class -ne 43) { continue }
            $k = Mid $m
            if ($katw.ContainsKey($k)) {
                $w = $katw[$k]; $neu = @(Kats $m | Where-Object { @($w.weg) -notcontains $_ })
                if ($w.setzen -and $neu -notcontains $w.setzen) { $neu += [string]$w.setzen }
                try { $m.Categories = ($neu -join $sep); $m.Save(); $aus.kat_gesetzt += $k } catch { $aus.fehler += ($k + ': ' + $_) }
            }
            if ($wunsch.ContainsKey($k) -and $wunsch[$k] -ne $n) {
                try { [void]$m.Move($unter[$wunsch[$k]]); $aus.verschoben += $k } catch { $aus.fehler += ($k + ': ' + $_) }
            }
        }
    }
}
# 2. neue Mails im Ordner selbst
foreach ($m in @($a.Items)) {
    if ($m.Class -ne 43) { $aus.andere++; continue }
    if ($aus.neu.Count -ge [int]$d.max) { break }
    $k = Mid $m
    try { Sichern $m $k; [void]$m.Move($unter[$d.unter[0]]) } catch { $aus.fehler += ($k + ': ' + $_) }
}
# 3. Unterordner auflisten (Erledigt nur die letzten Tage), fehlende Akten nachholen
foreach ($n in $d.unter) {
    foreach ($m in @($unter[$n].Items)) {
        if ($m.Class -ne 43) { continue }
        if ($n -eq $d.unter[2] -and $m.ReceivedTime -lt $grenze) { continue }
        $k = Mid $m
        $aus.liste += @{ mid = $k; ordner = $n; kat = @(Kats $m) }
        if ($hol.ContainsKey($k) -and $aus.neu.Count -lt [int]$d.max) { try { Sichern $m $k } catch { $aus.fehler += ($k + ': ' + $_) } }
    }
}
$aus | ConvertTo-Json -Depth 4 -Compress | Set-Content -Encoding UTF8 -LiteralPath $args[1]
"""


def ps_daten(ordner_, ziel, verschieben=(), nachholen=(), pfade=None, kategorien=(), ids=None):
    return dict(ordner=ordner_, ziel=str(ziel), unter=[UNTER[ak.NEU], UNTER[ak.BEARBEITUNG], UNTER[ak.ERLEDIGT]],
                unter_pfade=list(pfade or ["", "", ""]), ids=dict(ids or {}),
                verschieben=[dict(mid=m, nach=n) for m, n in verschieben], nachholen=list(nachholen),
                kategorien=[dict(mid=m, setzen=k, weg=list(w)) for m, k, w in kategorien],
                tage=ERLEDIGT_TAGE, max=HOECHSTENS)


# Ordner wählen: die Ordnerauswahl von Outlook selbst (auch andere Postfächer); Ergebnis der Outlook-Pfad
WAEHLEN_PS = r"""
$ErrorActionPreference = 'Stop'
$o = New-Object -ComObject Outlook.Application
$ns = $o.GetNamespace('MAPI')
$f = $ns.PickFolder()
$aus = @{ pfad = ''; id = ''; store = ''; kategorien = @() }
if ($f) { $aus.pfad = [string]$f.FolderPath; $aus.id = [string]$f.EntryID; try { $aus.store = [string]$f.StoreID } catch { } }
try { $aus.kategorien = @(foreach ($c in $ns.Categories) { [string]$c.Name }) } catch { }
$aus | ConvertTo-Json -Depth 3 -Compress | Set-Content -Encoding UTF8 -LiteralPath $args[1]
"""
KATEGORIEN_PS = WAEHLEN_PS.replace("$f = $ns.PickFolder()", "$f = $null")


def ordner_waehlen(ausfuehren=None):
    """Outlook-Ordnerauswahl öffnen. Ergebnis: (Pfad oder "" bei Abbruch, Kategorien, Fehlertext, Kennung
    {"e": EntryID, "s": StoreID} oder {})."""
    erg, fehler = outlook_lauf({}, ausfuehren, timeout=600, skript=WAEHLEN_PS)
    if erg is None:
        return "", [], fehler, {}
    kennung = dict(e=str(erg.get("id") or ""), s=str(erg.get("store") or "")) if erg.get("id") else {}
    return str(erg.get("pfad") or ""), kat_liste(erg.get("kategorien")), "", kennung


def kategorien_holen(ausfuehren=None):
    """Kategorien des Postfachs aus Outlook. Ergebnis: (Liste, Fehlertext)."""
    erg, fehler = outlook_lauf({}, ausfuehren, timeout=60, skript=KATEGORIEN_PS)
    return (kat_liste(erg.get("kategorien")), "") if erg is not None else ([], fehler)


def outlook_lauf(daten, ausfuehren=None, timeout=180, skript=None):
    """Skript ausführen. ausfuehren(befehl) ersetzt subprocess.run (Tests; das Skript bekommt Daten- und
    Ergebnisdatei). Ergebnis: (dict, '') oder (None, Fehlertext)."""
    if ausfuehren is None and sys.platform != "win32":
        return None, "Outlook gibt es nur unter Windows."
    with tempfile.TemporaryDirectory() as tmp:
        text = skript or ABRUF_PS
        skript, ein, aus = Path(tmp) / "abruf.ps1", Path(tmp) / "abruf.json", Path(tmp) / "ergebnis.json"
        skript.write_text(text, encoding="utf-8-sig")
        ein.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        befehl = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(skript), str(ein), str(aus)]
        try:
            if ausfuehren:
                r = ausfuehren(befehl)
            else:
                r = subprocess.run(befehl, capture_output=True, text=True, timeout=timeout,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, str(e)
        if r.returncode != 0:
            return None, _fehler_text((r.stderr or r.stdout or "").strip()) or f"Rückgabewert {r.returncode}"
        try:
            erg = json.loads(aus.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            return None, f"Antwort von Outlook unlesbar: {e}"
    for k in ("neu", "liste", "verschoben", "fehler", "kat_gesetzt", "kategorien"):
        if k not in erg and skript:
            continue
        v = erg.get(k) or []
        erg[k] = v if isinstance(v, list) else [v]      # PowerShell macht aus einer Liste mit einem Eintrag ein Objekt
    return erg, ""


def _fehler_text(t):
    if "80040154" in t or "Klasse nicht registriert" in t or "Class not registered" in t:
        return "Kein klassisches Outlook auf diesem Rechner (das neue Outlook hat keine Schnittstelle)."
    zeilen = [z for z in t.splitlines() if z.strip()]
    return (zeilen[0] if zeilen else t)[:400]


# ------------------------------------------------------------------ Akten
def kopf_aus_mail(pfad, mid, eingang="", kunden=()):
    from . import anfragen, mail
    m = mail.lesen(pfad)
    k = dict(quelle="outlook", nachrichten_id=mid, name=Path(pfad).stem)
    if m is not None:
        k.update(absender=m.absender, absender_name=m.absender_name, betreff=m.betreff or "Anfrage aus Outlook",
                 kurz=mail.neuester_teil(m.text))
        try:
            nr, _wie = mail.kunde(m, kunden)
        except Exception:
            nr = None
        if nr:
            k.update(kundennr=str(nr), kunde_name=anfragen.kunde_text(kunden, nr))
        if m.datum and not eingang:
            eingang = m.datum
    else:
        k.update(betreff="Anfrage aus Outlook", kurz="")
    if isinstance(eingang, str) and eingang:
        try:
            eingang = datetime.datetime.fromisoformat(eingang)
        except ValueError:
            eingang = ""
    k["eingang"] = eingang or datetime.datetime.now().replace(microsecond=0)
    return k


def _mail_dateiname(kopf, i):
    t = ak._sauber((kopf.get("betreff") or "Anfrage")[:60]).strip("_") or "Anfrage"
    return f"{t}.msg" if i == 0 else f"{t}_{i}.msg"


def index(akten):
    """{Nachrichten-ID: Akte} der Akten aus Outlook, auch die Antworten des Kunden in der Akte (Paket 3)."""
    out = {}
    for a in akten:
        for mid in a.stand.get("mids", []):
            out[mid] = a
        if a.kopf.get("nachrichten_id"):
            out[a.kopf["nachrichten_id"]] = a
    return out


def folgen(abl, akte, ordner_, jetzt=None):
    """Outlook -> Programm: Akte in den Status des Outlook-Ordners bringen. Ergebnis: Text oder ''."""
    soll = STATUS_ZU.get(ordner_)
    if soll is None or akte.status == soll:
        return ""
    if soll == ak.BEARBEITUNG:
        if akte.status == ak.NEU:
            abl.uebernehmen(akte, akte.stand["zugewiesen"] or None, jetzt=jetzt)
        else:
            abl.wieder_oeffnen(akte, jetzt=jetzt)
    elif soll == ak.ERLEDIGT:
        if akte.status == ak.NEU:
            akte = abl.uebernehmen(akte, akte.stand["zugewiesen"] or None, jetzt=jetzt)
        abl.erledigen(akte, jetzt=jetzt)
    else:
        if akte.status == ak.ERLEDIGT:
            akte = abl.wieder_oeffnen(akte, jetzt=jetzt)
        abl.zurueckgeben(akte, jetzt=jetzt)
    abl.notiz(abl.neu_lesen(akte), f"In Outlook nach „{ordner_}“ verschoben", jetzt=jetzt)
    return f"{akte.nr}: {UNTER[soll]} (in Outlook verschoben)"


def _soll(akte):
    """Mitarbeiter, für den die Mail in Outlook die Kategorie trägt: Bearbeiter, in Neu der Zugewiesene."""
    return (akte.stand.get("zugewiesen") or "") if akte.status == ak.NEU else (akte.bearbeiter or "")


def kategorie_folgen(abl, akte, alt, neu, zu, mitarbeiter, jetzt=None):
    """Outlook -> Programm: Mitarbeiter-Kategorie an der Mail geändert. alt/neu: Kategorien vorher/jetzt.
    Neu: zuweisen (bleibt in Neu), sonst Bearbeiter wechseln; die zuletzt gesetzte gilt. Ergebnis: Text oder ''."""
    ma_neu = [k for k in neu if kat_kuerzel(k, zu, mitarbeiter)]
    ma_alt = [k for k in alt if kat_kuerzel(k, zu, mitarbeiter)]
    if ma_neu == ma_alt or akte.status == ak.ERLEDIGT:
        return ""
    dazu = [k for k in ma_neu if k not in ma_alt]
    wahl = (dazu or ma_neu or [""])[-1]
    kz = kat_kuerzel(wahl, zu, mitarbeiter) if wahl else ""
    if kz == _soll(akte) or (not kz and akte.status != ak.NEU):
        return ""
    if akte.status == ak.NEU:
        akte = abl.zuweisen(akte, kz, jetzt=jetzt)
    else:
        akte = abl.bearbeiter_aendern(akte, kz, jetzt=jetzt)
    text = f"In Outlook Kategorie „{wahl}“ gesetzt" if wahl else "In Outlook Mitarbeiter-Kategorie entfernt"
    if len(ma_neu) > 1:
        text += f" (mehrere Mitarbeiter-Kategorien: {', '.join(ma_neu)}; es gilt die zuletzt gesetzte)"
    abl.notiz(abl.neu_lesen(akte), text, jetzt=jetzt)
    return f"{akte.nr}: {'zugewiesen an ' + kz if kz else 'Zuweisung aufgehoben'} (Kategorie in Outlook)"


def abrufen(abl, ordner_=ORDNER_VORGABE, kunden=(), ausfuehren=None, jetzt=None, pfade=None, zu=None,
            mitarbeiter=None, ids=None):
    """Ein Abruf. pfade: Outlook-Pfade [Neu, In Bearbeitung, Erledigt] (leer = Unterordner); ids: feste Kennungen
    der gewählten Ordner {Pfad: {"e", "s"}} (ordner_ids); zu: Zuordnung
    {Kategorie: Kürzel}; mitarbeiter: {Kürzel: Name} für die automatische Zuordnung. Ergebnis: dict(neu=[Akte],
    gefolgt=[Text], verschoben=n, fehler=[Text], anderer=Marke|None, antworten=[Akte], kategorien=n)."""
    out = dict(neu=[], gefolgt=[], verschoben=0, fehler=[], anderer=None, antworten=[], kategorien=0, andere=0)
    zu, mitarbeiter = zu or {}, mitarbeiter or {}
    ok, m = marke_nehmen(abl, jetzt=jetzt)
    if not ok:
        out["anderer"] = m
        return out
    stand = stand_lesen(abl)
    alle = abl.alle()
    akten = index(alle)
    verschieben = [(mid, UNTER[akten[mid].status]) for mid, o in stand.items()
                   if mid in akten and UNTER[akten[mid].status] != o]
    nachholen = [mid for mid in stand if mid not in akten]
    kat_pfad = Path(abl.wurzel) / STAMM / "kategorien_stand.json"
    kat_stand = _json_lesen(kat_pfad, {})
    bekannte = kategorien_lesen(abl)
    kat_wunsch = []                     # Programm -> Outlook (nur Mails, deren Kategorien schon bekannt sind)
    for mid, alt in kat_stand.items():
        a = akten.get(mid)
        if a is None or a.kopf.get("nachrichten_id") != mid or a.status == ak.ERLEDIGT:
            continue
        ma = [k for k in kat_liste(alt) if kat_kuerzel(k, zu, mitarbeiter)]
        soll = kuerzel_kat(_soll(a), bekannte + ma, zu, mitarbeiter)
        if ma != ([soll] if soll else []):
            kat_wunsch.append((mid, soll, [k for k in ma if k != soll]))
    with tempfile.TemporaryDirectory() as ziel:
        erg, fehler = outlook_lauf(ps_daten(ordner_, ziel, verschieben, nachholen, pfade, kat_wunsch, ids),
                                   ausfuehren)
        if erg is None:
            out["fehler"].append(fehler)
            return out
        out["fehler"] += [str(f) for f in erg["fehler"]]
        # neue Mails (und nachgeholte) als Akte
        for n in erg["neu"]:
            mid, datei = str(n.get("mid") or ""), Path(str(n.get("datei") or ""))
            if not mid or not datei.exists() or mid in akten:
                continue
            try:
                kopf = kopf_aus_mail(datei, mid, n.get("eingang") or "", kunden)
            except Exception:           # noqa: BLE001 – unlesbare Mail: trotzdem Akte, Abruf läuft weiter
                kopf = dict(quelle="outlook", nachrichten_id=mid, betreff="Mail nicht lesbar", kurz="",
                            eingang=datetime.datetime.now().replace(microsecond=0))
            kopf["konversation"] = str(n.get("konversation") or "")
            schoen = datei.with_name(_mail_dateiname(kopf, len(out["neu"]) + len(out["antworten"])))
            kopf["name"] = schoen.stem
            try:
                datei.replace(schoen)
                ziel = ak.antwort_zu(alle, kopf.get("betreff"), kopf.get("absender"), kopf["konversation"], jetzt)
                if ziel is not None:    # Antwort des Kunden: in die vorhandene Akte, Mail wandert mit ihr
                    abl.dateien_dazu(ziel, [schoen], jetzt=jetzt, antwort=True, nachrichten_id=mid)
                    abl.schluessel_setzen(schluessel(mid), ziel.nr)
                    akten[mid] = abl.neu_lesen(ziel)
                    out["antworten"].append(akten[mid])
                    continue
                akte, neu = abl.anlegen(kopf, [schoen], schluessel(mid), jetzt=jetzt)
            except Exception as e:      # noqa: BLE001 – Mail bleibt in Outlook (Neu) und wird nachgeholt
                out["fehler"].append(f"Akte nicht angelegt (wird beim nächsten Abruf nachgeholt): {e}")
                continue
            if akte is not None:
                akten[mid] = akte
                alle.append(akte)
                stand.pop(mid, None)    # nachgeholt: die Akte folgt dem Outlook-Ordner, in dem die Mail liegt
                if neu:
                    out["neu"].append(akte)
    try:
        out["andere"] = int(erg.get("andere") or 0)
    except (TypeError, ValueError):
        pass
    gemacht = {str(x) for x in erg["verschoben"]}
    out["verschoben"] = len(gemacht)
    kat_gemacht = {str(x) for x in erg.get("kat_gesetzt") or []}
    out["kategorien"] = len(kat_gemacht)
    if erg.get("kategorien"):
        try:
            kategorien_schreiben(abl, kat_liste(erg["kategorien"]))
        except OSError:
            pass
    neu_stand, neu_kat = {}, {}
    for e in erg["liste"]:
        mid, o = str(e.get("mid") or ""), str(e.get("ordner") or "")
        if not mid or o not in STATUS_ZU:
            continue
        neu_stand[mid] = o
        neu_kat[mid] = kat_liste(e.get("kat"))
        akte = akten.get(mid)
        if akte is not None and akte.kopf.get("nachrichten_id") == mid and mid not in kat_gemacht:
            try:                        # Kategorie in Outlook geändert (beim ersten Mal: nur wenn eine gesetzt ist)
                t = kategorie_folgen(abl, abl.neu_lesen(akte), kat_liste(kat_stand.get(mid)), neu_kat[mid], zu,
                                     mitarbeiter, jetzt=jetzt)
            except (ak.AblageFehler, OSError) as x:
                t = ""
                out["fehler"].append(f"{akte.nr}: {x}")
            if t:
                out["gefolgt"].append(t)
        if akte is None or mid in gemacht or akte.kopf.get("nachrichten_id") != mid:
            continue                    # Antworten des Kunden folgen nur der Akte, sie ändern sie nie
        letzt = stand.get(mid)
        if letzt != o:                  # in Outlook verschoben (sonst: Programm führt, Verschieben beim nächsten Mal)
            try:
                t = folgen(abl, abl.neu_lesen(akte), o, jetzt=jetzt)
            except (ak.AblageFehler, ak.SchonUebernommen, OSError) as x:
                t = ""
                out["fehler"].append(f"{akte.nr}: {x}")
            if t:
                out["gefolgt"].append(t)
    stand_schreiben(abl, neu_stand)
    try:
        _json_schreiben(kat_pfad, neu_kat)
    except OSError:
        pass
    return out
