"""Zusatzarbeit mit eigener Formel und Wertetabelle (Plan PROfirst-/LogiTRACE-Handbücher 12.11.2026, G3).

PROfirst rechnet frei definierte Arbeitsgänge mit einer Formel aus Fragen und Teilewerten. Hier bekommt eine
Zusatzarbeit (Abrechnung €/Stück) in den Stammdaten optional
- eine Formel für den Preis je Teil in €, z. B. „2,50 + 0,004 * L“ (Richten nach Länge) oder „(30 + 0,05 * U) / 3600
  * H“ (Zeit aus dem Umfang × Stundensatz), und/oder
- eine Wertetabelle „bis Wert = Betrag“, z. B. „1000 = 1,20; 3000 = 1,80; 6000 = 2,60“, nachgeschlagen nach einer
  Größe (Spalte „Tabelle nach“, z. B. L oder Q); ihr Betrag steht in der Formel als T (ohne Formel ist T der Preis).

Größen: L Länge [mm], A und B Abmessung [mm], W Wandstärke [mm], Q Querschnitt [mm²], U Umfang [mm], G Gewicht je
Teil [kg], F Außenfläche [m²], N Anzahl Bohrungen, I Anzahl Innenkonturen, S Stückzahl der Position, H Stundensatz der
Zusatzarbeit [€/h], T Wert der Tabelle. Erlaubt sind Zahlen (Komma oder Punkt), + − × ÷, Klammern, min(), max(),
rund() (aufrunden auf ganze Zahl). Gewinde, Senken, Flowdrill und Bohren bleiben fest € je Stück (Regel Patrick).
Eine von Hand eingetragene Menge oder ein Preis in der Position gehen vor. Fehlt eine Größe (z. B. kein Gewicht), ist
das Ergebnis None: dann gilt der feste Preis (Spalte Festpreis)."""
import ast
import math
import operator
import re

GROESSEN = ("L", "A", "B", "W", "Q", "U", "G", "F", "N", "I", "S", "H", "T")
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow}
_FUNK = {"min": min, "max": max, "rund": math.ceil, "aufrunden": math.ceil}


class FormelFehler(ValueError):
    pass


def _text(formel):
    # Dezimalkomma -> Punkt (nur zwischen Ziffern), × und ÷ -> * und /, Semikolon als Trenner in min/max
    t = str(formel or "").strip().replace("×", "*").replace("÷", "/").replace("−", "-")
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    return t.replace(";", ",")


def pruefen(formel):
    """Fehlertext der Formel oder '' (für die Stammdatenprüfung)."""
    if not str(formel or "").strip():
        return ""
    try:
        baum = ast.parse(_text(formel), mode="eval")
        _pruefe_knoten(baum.body)
    except (SyntaxError, FormelFehler) as e:
        return f"Formel nicht lesbar: {e}"
    return ""


def _pruefe_knoten(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return
    if isinstance(n, ast.Name):
        if n.id not in GROESSEN:
            raise FormelFehler(f"unbekannte Größe {n.id} (erlaubt: {', '.join(GROESSEN)})")
        return
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        _pruefe_knoten(n.left)
        _pruefe_knoten(n.right)
        return
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
        _pruefe_knoten(n.operand)
        return
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNK and not n.keywords:
        for a in n.args:
            _pruefe_knoten(a)
        return
    raise FormelFehler("nur Zahlen, Größen, + - * / ( ) und min, max, rund erlaubt")


def _rechne(n, w):
    if isinstance(n, ast.Constant):
        return float(n.value)
    if isinstance(n, ast.Name):
        v = w.get(n.id)
        if not isinstance(v, (int, float)):
            raise KeyError(n.id)
        return float(v)
    if isinstance(n, ast.BinOp):
        return _OPS[type(n.op)](_rechne(n.left, w), _rechne(n.right, w))
    if isinstance(n, ast.UnaryOp):
        x = _rechne(n.operand, w)
        return -x if isinstance(n.op, ast.USub) else x
    return float(_FUNK[n.func.id](*[_rechne(a, w) for a in n.args]))


def auswerten(formel, werte):
    """Ergebnis der Formel mit den Größen (dict) oder None (fehlende Größe, Division durch 0, nicht lesbar)."""
    if pruefen(formel) or not str(formel or "").strip():
        return None
    try:
        return _rechne(ast.parse(_text(formel), mode="eval").body, werte or {})
    except (KeyError, ZeroDivisionError, OverflowError, TypeError, ValueError):
        return None


def tabelle_lesen(text):
    """Wertetabelle „bis = Betrag; …“ (auch je Zeile) -> [(bis, Betrag)] aufsteigend; unlesbare Teile entfallen."""
    out = []
    for teil in re.split(r"[;\n]+", str(text or "")):
        m = re.match(r"\s*(?:bis\s*)?([0-9]+(?:[.,][0-9]+)?)\s*(?:=|:|->)\s*([0-9]+(?:[.,][0-9]+)?)\s*$", teil,
                     re.IGNORECASE)
        if m:
            out.append((float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))))
    return sorted(out)


def tabelle_wert(text, x):
    """Betrag der ersten Zeile mit bis >= x; über der letzten Zeile deren Betrag; None ohne Tabelle oder Größe."""
    zeilen = tabelle_lesen(text)
    if not zeilen or not isinstance(x, (int, float)):
        return None
    return next((b for bis, b in zeilen if x <= bis + 1e-9), zeilen[-1][1])


def hat_formel(kz):
    """True, wenn die Zusatzarbeit (Stammdaten oder Preisstand) eine Formel oder Wertetabelle trägt."""
    return bool(str((kz or {}).get("formel") or "").strip() or tabelle_lesen((kz or {}).get("wertetabelle")))


def groessen(p, k, tabellen=None, satz=None):
    """Größen der Position für die Formel (fehlende Werte fehlen im dict)."""
    from . import rechnen
    from . import zusatz_regeln as zr
    w = {}
    pr = (k.profile.get(p.get("profil_id")) if k is not None else None) or {}

    def setz(name, v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            w[name] = float(v)

    setz("L", p.get("laenge"))
    setz("A", pr.get("a"))
    setz("B", pr.get("b") if pr.get("b") is not None else pr.get("a"))
    setz("W", pr.get("wand"))
    setz("S", p.get("stueck"))
    setz("H", satz)
    try:
        setz("G", rechnen.zusatz_menge_auto("€/kg", p, k))
        setz("F", rechnen.zusatz_menge_auto("€/m²", p, k))
    except Exception:
        pass
    if "F" in w and w.get("L"):
        w["U"] = w["F"] * 1e6 / w["L"]
    try:
        from .stammdaten import flaeche_wirksam
        setz("Q", flaeche_wirksam(pr) if pr else None)
    except Exception:
        pass
    try:
        setz("N", zr.anzahl_bohrungen(p))
        setz("I", zr.anzahl_innen(p))
    except Exception:
        pass
    return w


def preis(kz, p, k, tabellen=None, satz=None):
    """Preis je Teil [€] aus Formel und Wertetabelle der Zusatzarbeit kz oder None (keine Formel, Größe fehlt)."""
    if not hat_formel(kz):
        return None
    w = groessen(p, k, tabellen, satz)
    nach = str(kz.get("tabelle_nach") or "L").strip().upper() or "L"
    t = tabelle_wert(kz.get("wertetabelle"), w.get(nach))
    if t is not None:
        w["T"] = t
    formel = str(kz.get("formel") or "").strip()
    if not formel:
        return t
    v = auswerten(formel, w)
    return max(v, 0.0) if v is not None else None
