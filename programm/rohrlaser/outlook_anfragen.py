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
steht in _outlook/stand.json (schreibt nur der abrufende Rechner). Es wird nie etwas gelöscht oder gesendet."""
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
function Mid($m) { $k = ''; try { $k = [string]$m.PropertyAccessor.GetProperty($MID) } catch { }; if (-not $k) { $k = 'entry:' + $m.EntryID }; return $k }
$inbox = $ns.GetDefaultFolder(6)
$wurzel = $inbox.Parent
$a = $null
if ($d.ordner.Contains('\')) { $a = $wurzel; foreach ($t in $d.ordner.Split('\')) { if ($a) { $a = Suchen $a $t } } }
else { $a = Suchen $inbox $d.ordner; if (-not $a) { $a = Suchen $wurzel $d.ordner } }
if (-not $a) { throw ("Outlook-Ordner '" + $d.ordner + "' nicht gefunden") }
$unter = @{}
foreach ($n in $d.unter) { $u = Suchen $a $n; if (-not $u) { $u = $a.Folders.Add($n) }; $unter[$n] = $u }
$aus = @{ neu = @(); liste = @(); verschoben = @(); fehler = @() }
$wunsch = @{}; foreach ($v in $d.verschieben) { $wunsch[$v.mid] = $v.nach }
$hol = @{}; foreach ($k in $d.nachholen) { $hol[$k] = 1 }
$grenze = (Get-Date).AddDays(-[int]$d.tage)
$nr = 0
function Sichern($m, $k) {
    $script:nr++
    $datei = Join-Path $d.ziel ('mail_' + $script:nr + '.msg')
    $m.SaveAs($datei, 9)
    $kv = ''; try { $kv = [string]$m.ConversationID } catch { }
    $script:aus.neu += @{ mid = $k; datei = $datei; eingang = $m.ReceivedTime.ToString('s'); konversation = $kv }
}
# 1. Programm -> Outlook
if ($wunsch.Count -gt 0) {
    foreach ($n in $d.unter) {
        foreach ($m in @($unter[$n].Items)) {
            if ($m.Class -ne 43) { continue }
            $k = Mid $m
            if ($wunsch.ContainsKey($k) -and $wunsch[$k] -ne $n) {
                try { [void]$m.Move($unter[$wunsch[$k]]); $aus.verschoben += $k } catch { $aus.fehler += ($k + ': ' + $_) }
            }
        }
    }
}
# 2. neue Mails im Ordner selbst
foreach ($m in @($a.Items)) {
    if ($m.Class -ne 43) { continue }
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
        $aus.liste += @{ mid = $k; ordner = $n }
        if ($hol.ContainsKey($k) -and $aus.neu.Count -lt [int]$d.max) { try { Sichern $m $k } catch { $aus.fehler += ($k + ': ' + $_) } }
    }
}
$aus | ConvertTo-Json -Depth 4 -Compress | Set-Content -Encoding UTF8 -LiteralPath $args[1]
"""


def ps_daten(ordner_, ziel, verschieben=(), nachholen=()):
    return dict(ordner=ordner_, ziel=str(ziel), unter=[UNTER[ak.NEU], UNTER[ak.BEARBEITUNG], UNTER[ak.ERLEDIGT]],
                verschieben=[dict(mid=m, nach=n) for m, n in verschieben], nachholen=list(nachholen),
                tage=ERLEDIGT_TAGE, max=HOECHSTENS)


def outlook_lauf(daten, ausfuehren=None, timeout=180):
    """Skript ausführen. ausfuehren(befehl) ersetzt subprocess.run (Tests; das Skript bekommt Daten- und
    Ergebnisdatei). Ergebnis: (dict, '') oder (None, Fehlertext)."""
    if ausfuehren is None and sys.platform != "win32":
        return None, "Outlook gibt es nur unter Windows."
    with tempfile.TemporaryDirectory() as tmp:
        skript, ein, aus = Path(tmp) / "abruf.ps1", Path(tmp) / "abruf.json", Path(tmp) / "ergebnis.json"
        skript.write_text(ABRUF_PS, encoding="utf-8-sig")
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
    for k in ("neu", "liste", "verschoben", "fehler"):
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


def abrufen(abl, ordner_=ORDNER_VORGABE, kunden=(), ausfuehren=None, jetzt=None):
    """Ein Abruf. Ergebnis: dict(neu=[Akte], gefolgt=[Text], verschoben=n, fehler=[Text], anderer=Marke|None)."""
    out = dict(neu=[], gefolgt=[], verschoben=0, fehler=[], anderer=None, antworten=[])
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
    with tempfile.TemporaryDirectory() as ziel:
        erg, fehler = outlook_lauf(ps_daten(ordner_, ziel, verschieben, nachholen), ausfuehren)
        if erg is None:
            out["fehler"].append(fehler)
            return out
        out["fehler"] += [str(f) for f in erg["fehler"]]
        # neue Mails (und nachgeholte) als Akte
        for n in erg["neu"]:
            mid, datei = str(n.get("mid") or ""), Path(str(n.get("datei") or ""))
            if not mid or not datei.exists() or mid in akten:
                continue
            kopf = kopf_aus_mail(datei, mid, n.get("eingang") or "", kunden)
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
            except OSError as e:
                out["fehler"].append(f"Akte nicht angelegt: {e}")
                continue
            if akte is not None:
                akten[mid] = akte
                alle.append(akte)
                stand.pop(mid, None)    # nachgeholt: die Akte folgt dem Outlook-Ordner, in dem die Mail liegt
                if neu:
                    out["neu"].append(akte)
    gemacht = {str(x) for x in erg["verschoben"]}
    out["verschoben"] = len(gemacht)
    neu_stand = {}
    for e in erg["liste"]:
        mid, o = str(e.get("mid") or ""), str(e.get("ordner") or "")
        if not mid or o not in STATUS_ZU:
            continue
        neu_stand[mid] = o
        akte = akten.get(mid)
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
    return out
