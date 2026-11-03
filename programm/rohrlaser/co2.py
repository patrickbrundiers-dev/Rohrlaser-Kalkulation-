"""CO₂-Bilanz je Teil (Vorschlag K3, Patrick 02.11.2026 „K3b“: nur intern, Funktion „CO₂-Bilanz“, Vorgabe aus).

Richtwert in kg CO₂ je Teil = Teilgewicht × Faktor des Werkstoffs (kg CO₂ je kg Material) + Laserzeit × Leistung der
Maschine × Strommix (kg CO₂ je kWh). Der Faktor steht je Werkstoff in den Stammdaten (Spalte „CO₂ [kg/kg]“), leer =
Richtwert der Kategorie (KATEGORIE_VORGABE). Die Leistung ist die Anschlussleistung der Maschine (Stundensatz-
Ermittlung, leistung_kw), leer = Einstellung co2_kw. Schneidgas und Transport zählen nicht mit.

Die Werte sind Richtwerte für Kundenfragen (z. B. Nachhaltigkeitsberichte), keine zertifizierte Bilanz; die genauen
Faktoren stehen in den Werkszeugnissen bzw. Umweltproduktdeklarationen der Lieferanten.
Ohne Qt."""
from . import rechnen

# kg CO₂ je kg Material (Richtwerte Stahlindustrie Europa, Mischung Hochofen/Elektrostahl; bitte anpassen)
KATEGORIE_VORGABE = {"Stahl": 2.0, "Edelstahl": 4.5, "Aluminium": 8.6}
VORGABE = 2.0


def _n(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0


def faktor(werkstoff_id, k):
    """(kg CO₂ je kg, Quelle) des Werkstoffs."""
    w = (k.werkstoffe.get(werkstoff_id) or {}) if k is not None else {}
    if _n(w.get("co2_faktor")) > 0:
        return _n(w["co2_faktor"]), "Werkstoff"
    kat = w.get("kategorie")
    if kat in KATEGORIE_VORGABE:
        return KATEGORIE_VORGABE[kat], f"Richtwert {kat}"
    return VORGABE, "Richtwert"


def leistung(kopf, k, einst):
    m = (k.maschinen.get((kopf or {}).get("maschine")) or {}) if k is not None else {}
    return _n(m.get("leistung_kw")) or _n((einst or {}).get("co2_kw")) or 20.0


def je_teil(p, z, kopf, k, einst):
    """dict(gewicht, material, strom, gesamt) in kg je Teil oder None (kein Rohrlaserteil)."""
    if not z or not p.get("profil_id") or not p.get("werkstoff_id"):
        return None
    kgm = rechnen.kg_je_m(p.get("profil_id"), p.get("werkstoff_id"), k)
    gewicht = (kgm or 0.0) * _n(p.get("laenge")) / 1000
    f, _ = faktor(p.get("werkstoff_id"), k)
    strom = _n(z.get("laser_netto")) / 3600 * leistung(kopf, k, einst) * _n((einst or {}).get("co2_strom", 0.38))
    return dict(gewicht=gewicht, material=gewicht * f, strom=strom, gesamt=gewicht * f + strom)


def angebot(kopf, positionen, zeilen, k, einst):
    """dict(positionen=[dict(pos, bezeichnung, stueck, je_teil, position)], material, strom, gesamt) für das Angebot."""
    out, mat, strom = [], 0.0, 0.0
    for p, z in zip(positionen, zeilen or ()):
        w = je_teil(p, z, kopf, k, einst)
        if w is None:
            continue
        c = _n(z.get("stueck"))
        out.append(dict(pos=p.get("pos"), bezeichnung=p.get("bezeichnung") or p.get("artikel") or "",
                        werkstoff=p.get("werkstoff_id"), stueck=c, je_teil=w, position=w["gesamt"] * c))
        mat += w["material"] * c
        strom += w["strom"] * c
    return dict(positionen=out, material=mat, strom=strom, gesamt=mat + strom)


def text(b):
    """Kurzzeile, z. B. 'CO₂ (Richtwert) 87,1 kg: Material 86,9 kg, Strom 0,2 kg'."""
    from .stammdaten import zahl_als_text as zahl
    return (f"CO₂ (Richtwert) {zahl(b['gesamt'], 1)} kg: Material {zahl(b['material'], 1)} kg, Strom "
            f"{zahl(b['strom'], 1)} kg")
