"""KI-Plattform Phase 4: lokale Wissensdatenbank mit Quellenangabe (Master-Prompt Patrick 20.11.2026, Punkt 8).

Kein Zusatzprogramm, keine Vektordatenbank-Installation: ein kleiner Suchindex im Datenordner (ki_wissen/index.json),
neu gebaut, wenn sich Angebote oder Stammdaten geändert haben. Gesucht wird immer per Volltext (BM25, ohne Groß-/
Kleinschreibung und Umlaut-Varianten, Abmessungen wie „42,4x2,0“ als ein Wort); ist ein Einbettungsmodell da
(ki_modelle, Rolle einbettung), kommt die semantische Ähnlichkeit dazu (Vektoren in ki_wissen/vektoren.json,
nur für die Dokumente, die sich geändert haben). Jeder Treffer nennt Quelle und Datenstand.

Inhalt: Angebote mit Positionen (Nummer, Kunde, Vorgang, Datum, Artikel, Bezeichnung, Profil, Werkstoff, Länge),
Kunden, Zukaufartikel und Normteile, Lieferanten, Werkstoffe, Profile, Maschinen, Zusatzarbeiten, Arbeitsgang- und
Angebotsregeln, Prüfregeln, Lernwerte (Kennwerte-Historie) und die Abschnitte der Bedienungsanleitung.
Ohne Qt."""
import json
import math
import re
import time
import unicodedata
from pathlib import Path

ORDNER = "ki_wissen"
K1, B = 1.4, 0.72
ANGEBOTE_MAX = 5000
VEKTOREN_MAX = 3000
STOPP = set("der die das und oder ein eine einer eines einem einen zu zum zur im in am an auf aus bei mit von vom für "
            "fuer ist sind was wie wer wo welche welcher welches warum wieso bitte mir uns ich wir es den dem des "
            "nicht noch auch nur so als ob dass".split())
_INDEX = {}             # Pfad -> (stand, index)


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "").casefold())
    t = t.replace("ß", "ss")
    return "".join(c for c in t if not unicodedata.combining(c))


def woerter(text):
    """Suchwörter: klein, ohne Akzente; Abmessungen (42,4x2,0 / 40x40x3) bleiben ein Wort."""
    t = _norm(text)
    t = re.sub(r"(\d)\s*[x×*]\s*(\d)", r"\1x\2", t)
    out = []
    for w in re.findall(r"[a-z0-9][a-z0-9,.x_-]*[a-z0-9]|[a-z0-9]", t):
        w = w.strip(".,-")
        if len(w) < 2 or w in STOPP:
            continue
        out.append(w)
        if len(w) > 6 and w.isalpha():          # einfache Wortstämme für deutsche Endungen
            for e in ("ungen", "ung", "en", "er", "es", "e", "n", "s"):
                if w.endswith(e) and len(w) - len(e) >= 5:
                    out.append(w[: -len(e)])
                    break
    return out


def _dok(art, titel, text, quelle, stand="", ziel=""):
    return dict(art=art, titel=str(titel)[:200], text=str(text)[:3000], quelle=quelle, stand=str(stand or ""),
                ziel=ziel)


def _zeilen(db, tabelle):
    try:
        return db.zeilen(tabelle)
    except Exception:           # noqa: BLE001 – Tabelle fehlt in alten Dateien
        return []


def dokumente(db):
    """Alle Dokumente des Index (Liste von dicts)."""
    out = []
    try:
        angebote = db.angebote()[:ANGEBOTE_MAX]
    except Exception:           # noqa: BLE001
        angebote = []
    pos_je = {}
    try:
        for r in db.con.execute("SELECT angebot_id, pos, artikel, bezeichnung, profil_id, werkstoff_id, laenge, stueck "
                                "FROM positionen ORDER BY angebot_id, nr"):
            pos_je.setdefault(r[0], []).append(r[1:])
    except Exception:           # noqa: BLE001
        pass
    for a in angebote:
        teile = []
        for pos, art, bez, prof, ws, laenge, stk in pos_je.get(a["id"], [])[:60]:
            teile.append(" ".join(str(x) for x in (f"Pos. {pos}" if pos else "", art or "", bez or "", prof or "",
                                                   ws or "", f"{laenge:g} mm" if isinstance(laenge, (int, float))
                                                   else "", f"{stk} Stk." if stk else "") if x))
        out.append(_dok("angebot", f"Angebot {a.get('nummer')} – {a.get('kunde') or ''}",
                        f"{a.get('vorgang') or ''} {a.get('datum') or ''} Kunde {a.get('kundennr') or ''} "
                        f"{a.get('kunde') or ''}; " + "; ".join(teile), "Angebote", a.get("geaendert") or a.get("datum"),
                        f"angebot:{a['id']}"))
    for tabelle, art, titel_f, felder, quelle in (
            ("kunden", "kunde", ("name", "kundennr"), None, "Kunden"),
            ("zukauf_artikel", "zukauf", ("bezeichnung", "artikelnr"), None, "Zukaufartikel und Normteile"),
            ("zukauf_lieferanten", "lieferant", ("name",), None, "Lieferanten"),
            ("werkstoffe", "werkstoff", ("werkstoff_id",), None, "Werkstoffe"),
            ("profile", "profil", ("profil_id",), None, "Profile"),
            ("maschinen", "maschine", ("maschinen_id", "name"), None, "Maschinen"),
            ("zusatzarbeiten", "regel", ("name",), None, "Zusatzarbeiten"),
            ("arbeitsgang_regeln", "regel", ("name", "arbeitsgang"), None, "Arbeitsgang-Regeln"),
            ("angebotsregeln", "regel", ("name", "text"), None, "Angebotsregeln"),
            ("pruefregeln", "regel", ("name", "text"), None, "Prüfregeln"),
            ("kennwerte_historie", "lernwert", ("quelle", "datum"), None, "Lernwerte (Kennwerte-Historie)")):
        for z in _zeilen(db, tabelle):
            titel = " ".join(str(z.get(f)) for f in titel_f if z.get(f) not in (None, "")) or f"{quelle} {z.get('id')}"
            text = "; ".join(f"{k}: {v}" for k, v in z.items() if k not in ("id", "uid", "version", "geaendert")
                             and v not in (None, "") and not str(k).startswith("_"))
            out.append(_dok(art, f"{quelle}: {titel}", text, quelle, z.get("geaendert") or z.get("datum") or "",
                            f"stamm:{tabelle}:{z.get('id')}"))
    out += anleitung_abschnitte()
    return out


def anleitung_abschnitte():
    """Abschnitte der Bedienungsanleitung (Texte aus anleitung/erzeuge_anleitung.py, wenn vorhanden)."""
    out = []
    for kandidat in (Path(__file__).resolve().parents[2] / "anleitung" / "erzeuge_anleitung.py",
                     Path(__file__).resolve().parent / "anleitung_texte.json"):
        try:
            if kandidat.suffix == ".json" and kandidat.is_file():
                for t, x in json.loads(kandidat.read_text(encoding="utf-8")):
                    out.append(_dok("anleitung", f"Anleitung: {t}", x, "Bedienungsanleitung"))
                return out
            if kandidat.is_file():
                text = kandidat.read_text(encoding="utf-8")
                for m in re.finditer(r'(?:kapitel|abschnitt|ueberschrift)\(\s*["\']([^"\']{3,80})["\']', text):
                    rest = text[m.end(): m.end() + 2500]
                    saetze = " ".join(re.findall(r'"([^"]{20,})"', rest))[:2000]
                    if saetze:
                        out.append(_dok("anleitung", f"Anleitung: {m.group(1)}", saetze, "Bedienungsanleitung"))
                if out:
                    return out
        except (OSError, ValueError):
            continue
    return out


def _stand(db):
    try:
        from . import db_verbindung
        a = db.con.execute("SELECT COUNT(*), MAX(geaendert) FROM angebote").fetchone()
        return [str(db.stammdaten_stand()), a[0], str(a[1] or ""), db_verbindung.aenderungsstand(db.con)]
    except Exception:           # noqa: BLE001
        return [time.time()]


def _ordner(db):
    p = Path(db.pfad).parent / ORDNER
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def index(db, neu=False):
    """Suchindex (gemerkt; neu gebaut bei geändertem Datenstand): dict(stand, doks, df, laenge, n, gebaut)."""
    pfad = _ordner(db) / "index.json"
    stand = _stand(db)
    alt = _INDEX.get(str(pfad))
    if not neu and alt and alt[0] == stand:
        return alt[1]
    if not neu and alt is None:
        try:
            d = json.loads(pfad.read_text(encoding="utf-8"))
            if d.get("stand") == stand:
                _INDEX[str(pfad)] = (stand, d)
                return d
        except (OSError, ValueError):
            pass
    t0 = time.perf_counter()
    doks = dokumente(db)
    df, laengen = {}, []
    for d in doks:
        w = woerter(d["titel"] + " " + d["text"])
        d["tf"] = {}
        for x in w:
            d["tf"][x] = d["tf"].get(x, 0) + 1
        laengen.append(len(w))
        for x in d["tf"]:
            df[x] = df.get(x, 0) + 1
    ix = dict(stand=stand, doks=doks, df=df, mittel=(sum(laengen) / len(laengen)) if laengen else 1.0,
              n=len(doks), gebaut=time.strftime("%Y-%m-%dT%H:%M:%S"), dauer_s=round(time.perf_counter() - t0, 2))
    try:
        pfad.write_text(json.dumps(ix, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    _INDEX[str(pfad)] = (stand, ix)
    return ix


def _bm25(ix, frage_w):
    n, mittel = max(ix["n"], 1), ix["mittel"] or 1.0
    werte = []
    for i, d in enumerate(ix["doks"]):
        tf, laenge = d["tf"], sum(d["tf"].values()) or 1
        s = 0.0
        for w in frage_w:
            f = tf.get(w)
            if not f:
                continue
            idf = math.log(1 + (n - ix["df"].get(w, 0) + 0.5) / (ix["df"].get(w, 0) + 0.5))
            s += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * laenge / mittel))
        if s > 0:
            werte.append((s, i))
    return werte


def _kosinus(a, b):
    za = math.sqrt(sum(x * x for x in a)) or 1.0
    zb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (za * zb)


def _vektoren(db, ix, senden=None):
    """Vektoren der Dokumente (gemerkt in vektoren.json je Titel+Text); None ohne Einbettungsmodell."""
    from . import ki_modelle
    m = ki_modelle.modell_fuer(db, ki_modelle.EINBETTUNG, senden=senden)
    if not m:
        return None, None
    pfad = _ordner(db) / "vektoren.json"
    try:
        alt = json.loads(pfad.read_text(encoding="utf-8")) if pfad.is_file() else {}
    except (OSError, ValueError):
        alt = {}
    if alt.get("modell") != m["name"]:
        alt = dict(modell=m["name"], v={})
    v = alt.setdefault("v", {})
    fehlt = [(d["ziel"] or d["titel"], d["titel"] + "\n" + d["text"][:800]) for d in ix["doks"][:VEKTOREN_MAX]
             if (d["ziel"] or d["titel"]) not in v]
    for i in range(0, len(fehlt), 32):
        teil = fehlt[i:i + 32]
        for (schl, _), vek in zip(teil, ki_modelle.einbetten(db, [t for _, t in teil], senden=senden, modell=m)):
            v[schl] = [round(x, 5) for x in vek]
    if fehlt:
        try:
            pfad.write_text(json.dumps(alt), encoding="utf-8")
        except OSError:
            pass
    return v, m


def suchen(db, frage, n=8, senden=None, semantisch=True):
    """Treffer: [dict(titel, text, quelle, stand, ziel, art, punkte, weg)] beste zuerst. weg: 'Volltext',
    'semantisch' oder 'beides'."""
    ix = index(db)
    fw = woerter(frage)
    treffer = {i: dict(bm=s, sem=0.0) for s, i in _bm25(ix, fw)}
    if semantisch:
        try:
            from . import ki_modelle
            vek, m = _vektoren(db, ix, senden)
            if vek:
                q = ki_modelle.einbetten(db, [frage], senden=senden, modell=m)[0]
                sem = sorted(((_kosinus(q, vek[d["ziel"] or d["titel"]]), i) for i, d in enumerate(ix["doks"])
                              if (d["ziel"] or d["titel"]) in vek), reverse=True)[:n * 3]
                for s, i in sem:
                    if s > 0.3:
                        treffer.setdefault(i, dict(bm=0.0, sem=0.0))["sem"] = s
        except Exception:       # noqa: BLE001 – ohne Modell: nur Volltext
            pass
    if not treffer:
        return []
    bm_max = max(t["bm"] for t in treffer.values()) or 1.0
    out = []
    for i, t in treffer.items():
        d = ix["doks"][i]
        punkte = 0.6 * t["bm"] / bm_max + 0.4 * t["sem"] if t["sem"] else t["bm"] / bm_max
        weg = "beides" if t["bm"] and t["sem"] else ("semantisch" if t["sem"] else "Volltext")
        out.append(dict(titel=d["titel"], text=d["text"], quelle=d["quelle"], stand=d["stand"], ziel=d["ziel"],
                        art=d["art"], punkte=round(punkte, 3), weg=weg))
    return sorted(out, key=lambda x: -x["punkte"])[:n]


def info(db):
    ix = _INDEX.get(str(_ordner(db) / "index.json"))
    if not ix:
        return dict(n=0, gebaut="", dauer_s=None)
    return dict(n=ix[1]["n"], gebaut=ix[1]["gebaut"], dauer_s=ix[1].get("dauer_s"))
