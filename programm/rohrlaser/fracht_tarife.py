"""Tarifvorlagen, Packmittel-Vorlagen und Tarifstände (Fracht 2.0, Patrick 25.11.2026).

Recherche 25.11.2026 (Bericht https://claude.ai/artifact/BczvCC93BZcG6vS8W2arWW): öffentlich sind nur Listenpreise für
Privat- bzw. Online-Kunden (DHL, GLS, Hermes). Geschäftskundenpreise von MBE, UPS, FedEx, DPD, Cargoboard und den
Speditionen (Dachser, DB Schenker, Raben, regionale Spediteure) sind individuell: sie kommen als **Tariflücke** ohne
Preise ins Programm, werden nie automatisch gewählt und zeigen im Vergleich „Tarif fehlt – Angebot einholen“. Ein
Angebot wird per CSV (fracht_daten.preise_csv_lesen) oder von Hand in die Preisstaffeln übernommen; dann wird die
Tarifbasis „Geschäftskundenangebot“.

Keine Vorlage wird automatisch geladen: „Tarifvorlagen laden“ legt sie an, vorhandene Einträge mit gleicher Kennung
bleiben (der eigene gilt). Prioritäten 71–89 liegen hinter den Richtwert-Tarifen (50–70), damit die automatische Fracht
bestehender Angebote gleich bleibt. Ohne Qt.
"""
import datetime

from .fracht_daten import (DIENSTLEISTER, LAENDER, LHT, LUECKE, PREISE, TARIFE, ZONEN)

STAND = "2026-11-25"
Q_DHL_2026 = "DHL Paket online, Preise 2026 (shippypro.com/blog/de/paketversand-kosten-2026, 28.08.2026); Maße: " \
    "DHL Leistungsbeschreibung 10/2026"
Q_DHL_2027 = "DHL geplante Preisanpassungen ab 01.01.2027 (group.dhl.com, Pressemitteilung 11/2026), Onlinepreis"
Q_DHL_EU = "DHL Paket EU online 2026 (shippypro.com/blog/de/paketversand-kosten-2026, 28.08.2026)"
Q_GLS = "GLS Onlinefrankierung Haustür, Stand 2026 (paketda.de/frankieren/gls-porto.html, 03.04.2026)"
Q_GLS_EU = "GLS Ausland Privatkunden (paketda.de/frankieren/gls-porto.html, 03.04.2026)"
Q_HERMES = "Hermes Haustür online, gültig seit 02.03.2026 (shippypro.com/blog/de/paketversand-kosten-2026)"

EU = ("AT", "BE", "BG", "CY", "CZ", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV",
      "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK")
GLS_EU = ("AT", "FR", "BE", "NL", "LU", "IT", "PL", "ES")
PLZ_STELLEN = {"AT": 4, "BE": 4, "BG": 4, "CY": 4, "CZ": 5, "DK": 4, "EE": 5, "ES": 5, "FI": 5, "FR": 5, "GR": 5,
               "HR": 5, "HU": 4, "IE": 3, "IT": 5, "LT": 5, "LU": 4, "LV": 4, "MT": 4, "NL": 4, "PL": 5, "PT": 4,
               "RO": 6, "SE": 5, "SI": 4, "SK": 5}


def _zeile(t, **werte):
    z = {f.name: None for f in t.felder}
    z.update(werte)
    return z


def _paket(tarif_id, bez, dl, quelle, staffel, bezug="Packstück", laender="DE", ab="2026-01-01", bis=None,
           prio=80, stand=STAND, **regeln):
    """Pakettarif mit Preis je Paket (staffel = [(bis, Preis)], bis in kg bzw. mm Größenklasse)."""
    t = _zeile(TARIFE, tarif_id=tarif_id, bezeichnung=bez, dienstleister=dl, tarifart="Standardtarif",
               modell="Pakettarif", versandart="Paket", laender=laender, gueltig_ab=ab, gueltig_bis=bis,
               waehrung="EUR", prioritaet=prio, version=ab[:7], aktiv="ja", basis="Listenpreis", quelle=quelle,
               stand=stand, bemerkung="Listenpreis (Online/Privat), Geschäftskundenpreis bitte als eigenen Tarif "
               "eintragen", **regeln)
    preise = [_zeile(PREISE, tarif_id=tarif_id, bezug=bezug, bis=b, preis=p, preisart="Festpreis",
                     bemerkung=quelle[:120]) for b, p in staffel]
    return t, preise


def _luecke(tarif_id, bez, dl, versandart, modell, laender="DE", prio=85, bemerkung=""):
    return _zeile(TARIFE, tarif_id=tarif_id, bezeichnung=bez, dienstleister=dl, tarifart="Rahmenvertrag",
                  modell=modell, versandart=versandart, laender=laender, waehrung="EUR", prioritaet=prio,
                  aktiv="ja", basis=LUECKE, stand=STAND,
                  bemerkung="Tariflücke: keine öffentlichen Preise (Recherche 25.11.2026). " + bemerkung +
                  " Angebot einholen und die Preisstaffeln per CSV einlesen oder von Hand eintragen.")


DHL_REGELN = dict(paket_max_l=1200, paket_max_b=600, paket_max_h=600, paket_max_gurt=3600, paket_max_kg=31.5,
                  sperr_max_l=2000, sperr_max_gurt=3600, sperr_zuschlag=28.99)


def vorlagen():
    """Tarifvorlagen {Tabelle: [Zeilen]}: Dienstleister, Länder und Zonen der EU, Listenpreis-Tarife DHL/GLS/Hermes,
    Tariflücken für MBE, UPS, FedEx, DPD, Cargoboard und Speditionen."""
    dl = [_zeile(DIENSTLEISTER, dienstleister_id=i, name=n, versandarten=v, aktiv="ja", bemerkung=b) for i, n, v, b in (
        ("DHL", "DHL Paket", "Paket", "Listenpreise 2026/2027 als Vorlage; Geschäftskundenpreise eintragen"),
        ("GLS", "GLS", "Paket", "Listenpreise 2026 als Vorlage"),
        ("HERMES", "Hermes", "Paket", "Listenpreise 2026 als Vorlage"),
        ("DPD", "DPD", "Paket", "Geschäftskunden: individuelle Konditionen"),
        ("UPS", "UPS", "Paket, Express", "nur Geschäftskunden-Konditionen; Rating API möglich (Schnittstellen)"),
        ("FEDEX", "FedEx", "Paket, Express", "keine öffentliche Preisliste; Rate API möglich (Schnittstellen)"),
        ("MBE", "MBE – Mail Boxes Etc. (Center)", "Paket, Palettenversand, Stückgut",
         "Preise je Center individuell (mbe.de 25.11.2026): Angebot Ihres MBE-Centers eintragen"),
        ("CARGOBOARD", "Cargoboard (digitale Spedition)", "Palettenversand, Stückgut, Teilladung, Komplettladung",
         "Online-Rechner ab 65 € je Sendung; Preis-API mit Kundenkonto (Schnittstellen)"),
        ("DACHSER", "Dachser", "Stückgut, Palettenversand, Teilladung", "nur Angebot"),
        ("SCHENKER", "DB Schenker", "Stückgut, Palettenversand, Teilladung", "nur Angebot"),
        ("RABEN", "Raben", "Stückgut, Palettenversand, Teilladung", "nur Angebot"))]
    tarife, preise = [], []
    for t, p in (
            _paket("DHL-PAKET-2026", "DHL Paket national (Liste 2026)", "DHL", Q_DHL_2026,
                   [(2, 6.19), (5, 7.69), (10, 10.49), (20, 18.99), (31.5, 23.99)], bis="2026-12-31", prio=80,
                   **DHL_REGELN),
            _paket("DHL-PAKET-2027", "DHL Paket national (Liste ab 2027)", "DHL", Q_DHL_2027,
                   [(2, 6.19), (5, 7.69), (10, 11.49), (20, 19.99), (31.5, 24.99)], ab="2027-01-01", prio=80,
                   **DHL_REGELN),
            _paket("DHL-PAKET-EU-2026", "DHL Paket EU (Liste 2026)", "DHL", Q_DHL_EU,
                   [(5, 20.49), (10, 25.49), (20, 31.49), (30, 48.49)], laender=", ".join(EU), prio=81,
                   paket_max_l=1200, paket_max_b=600, paket_max_h=600, paket_max_gurt=3000, paket_max_kg=30,
                   sperr_max_l=2000, sperr_max_gurt=3600, sperr_zuschlag=29.75),
            _paket("GLS-PAKET-2026", "GLS Paket national (Liste 2026)", "GLS", Q_GLS,
                   [(350, 4.59), (500, 5.49), (700, 6.89), (900, 10.99), (2600, 22.00)], bezug="Paketgröße",
                   prio=82, paket_max_l=2000, paket_max_b=800, paket_max_h=600, paket_max_gurt=3000, paket_max_kg=40),
            _paket("GLS-PAKET-EU-2026", "GLS Paket EU (Liste 2026, bis Größe M)", "GLS", Q_GLS_EU,
                   [(350, 9.70), (500, 13.00), (700, 16.00)], bezug="Paketgröße", laender=", ".join(GLS_EU),
                   prio=83, paket_max_l=2000, paket_max_b=800, paket_max_h=600, paket_max_gurt=3000,
                   paket_max_kg=40),
            _paket("HERMES-PAKET-2026", "Hermes Paket national (Liste 2026)", "HERMES", Q_HERMES,
                   [(500, 5.79), (800, 6.99), (1200, 10.99), (1500, 28.99), (2000, 33.99)], bezug="Paketgröße",
                   ab="2026-03-02", prio=84, paket_max_kg=25)):
        tarife.append(t)
        preise += p
    tarife += [
        _luecke("MBE-PAKET", "MBE Paket national", "MBE", "Paket", "Pakettarif", prio=86,
                bemerkung="MBE kalkuliert je Center; Volumengewicht laut einem Center L×B×H/6000."),
        _luecke("MBE-SPERRGUT", "MBE Sperrgut", "MBE", "Paket", "Pakettarif", prio=87,
                bemerkung="Sperrgut ab längster Seite über 120 cm oder Umfang über 3 m (mbe.de)."),
        _luecke("MBE-INTERNATIONAL", "MBE Paket international", "MBE", "Paket", "Pakettarif", laender=", ".join(EU),
                prio=86),
        _luecke("MBE-PALETTE", "MBE Palette/Spedition", "MBE", "Palettenversand", "Palettentarif", prio=86),
        _luecke("UPS-STANDARD", "UPS Standard", "UPS", "Paket", "Pakettarif", prio=86,
                bemerkung="Grenzen laut Fachartikel: 274 cm Länge, Länge+Umfang 400 cm, 70 kg, Volumengewicht ÷ 5.000."),
        _luecke("UPS-EXPRESS", "UPS Express", "UPS", "Express", "Pakettarif", prio=86),
        _luecke("FEDEX-PAKET", "FedEx", "FEDEX", "Paket", "Pakettarif", prio=86),
        _luecke("DPD-CLASSIC", "DPD Classic Geschäftskunden", "DPD", "Paket", "Pakettarif", prio=86,
                bemerkung="Privat-Listenpreise der Quellen widersprechen sich; Geschäftskunden individuell."),
        _luecke("CARGOBOARD-PALETTE", "Cargoboard Palette/Stückgut", "CARGOBOARD", "Palettenversand", "Palettentarif",
                prio=86, bemerkung="Online ab 65 € je Sendung (cargoboard.com/de/preise), Beispiele ohne Stand."),
        _luecke("CARGOBOARD-TEILLADUNG", "Cargoboard Teilladung", "CARGOBOARD", "Teilladung", "Individueller Tarif",
                prio=86, bemerkung="Online ab 290 € (cargoboard.com/de/transporte/teilladung-versenden)."),
        _luecke("DACHSER-STUECKGUT", "Dachser Stückgut", "DACHSER", "Stückgut", "Gewichtstarif", prio=86),
        _luecke("SCHENKER-STUECKGUT", "DB Schenker Stückgut", "SCHENKER", "Stückgut", "Gewichtstarif", prio=86),
        _luecke("RABEN-STUECKGUT", "Raben Stückgut", "RABEN", "Stückgut", "Gewichtstarif", prio=86),
        _luecke("SPED-TEILLADUNG", "Teilladung (Spedition)", None, "Teilladung", "Individueller Tarif", prio=88,
                bemerkung="Preis je Lademeter bzw. km eintragen."),
        _luecke("SPED-KOMPLETT", "Komplettladung (Spedition)", None, "Komplettladung", "Individueller Tarif", prio=88,
                bemerkung="Preis je Fahrzeug und km eintragen."),
        _luecke("EXPRESS-KURIER", "Express / Direktfahrt", None, "Express", "Individueller Tarif", prio=88)]
    laender = [_zeile(LAENDER, land=x, plz_laenge=PLZ_STELLEN.get(x), waehrung="EUR", aktiv="ja",
                      bemerkung="Tarifvorlage EU (Fracht 2.0)") for x in EU]
    zonen = [_zeile(ZONEN, zone_id=f"EU-{x}", bezeichnung=f"EU {x}", land=x, art="Ausland", standard="ja", aktiv="ja",
                    bemerkung="Tarifvorlage EU: Standardzone des Landes") for x in EU]
    return {"fracht_dienstleister": dl, "fracht_tarife": tarife, "fracht_preise": preise,
            "fracht_laender": laender, "fracht_zonen": zonen}


# ------------------------------------------------------------------ Packmittel-Vorlagen
def packmittel():
    """Standard-Packmittel mit Normmaßen (keine Einkaufspreise: die trägt jeder selbst ein). Europalette EPAL 1200 ×
    800 × 144 mm, 25 kg, 1.500 kg; Aufsetzrahmen 200 mm; Gitterbox EPAL außen 1240 × 835 × 970, innen 1200 × 800 ×
    800 mm, 85 kg, 1.500 kg; lange Versandkartons für Rohre."""
    q = "Normmaße (EPAL/Hersteller), Preis bitte eintragen"
    werte = [
        dict(lht_id="EUR-R", bezeichnung="Europalette mit Aufsetzrahmen", art="Palette mit Aufsetzrahmen", laenge=1160,
             breite=760, hoehe=144, eigengewicht=25, nutzlast=1000, max_laenge=1160, stellplaetze=1,
             aussen_laenge=1200, aussen_breite=800, rahmen_hoehe=200, rahmen_gewicht=10, rahmen_max=5,
             abrechnung="Tausch", bemerkung=q + "; Innenmaß Rahmen ca. 1160 × 760 mm"),
        dict(lht_id="GB-EP", bezeichnung="Gitterbox EPAL (Europool)", art="Gitterbox", laenge=1200, breite=800,
             hoehe=800, eigengewicht=85, nutzlast=1500, max_laenge=1200, stapelbar="ja", stapelfaktor=5,
             stellplaetze=1, aussen_laenge=1240, aussen_breite=835, aussen_hoehe=970, abrechnung="Tausch",
             bemerkung=q + "; Europool-Tausch"),
        dict(lht_id="K-R2", bezeichnung="Rohrkarton 2000 × 150 × 150", art="Karton", laenge=2000, breite=150,
             hoehe=150, eigengewicht=1.2, nutzlast=30, max_laenge=2000, aussen_laenge=2010, aussen_breite=160,
             aussen_hoehe=160, abrechnung="Kauf", bemerkung=q + "; über 120 cm Sperrgut bei DHL"),
        dict(lht_id="K-R1", bezeichnung="Rohrkarton 1200 × 150 × 150", art="Karton", laenge=1200, breite=150,
             hoehe=150, eigengewicht=0.8, nutzlast=30, max_laenge=1200, aussen_laenge=1210, aussen_breite=160,
             aussen_hoehe=160, abrechnung="Kauf", bemerkung=q),
        # Packmittelmanagement (26.11.2026): weitere Paletten mit Normmaßen, Werte trägt jeder selbst ein
        dict(lht_id="EUR", bezeichnung="Europalette", art="Europalette", laenge=1200, breite=800, hoehe=144,
             eigengewicht=25, nutzlast=1500, max_laenge=1200, stellplaetze=1, abrechnung="Tausch",
             bemerkung=q + "; Wiederbeschaffungswert eintragen (nicht getauschte Paletten)"),
        dict(lht_id="HP", bezeichnung="Halbpalette (Düsseldorfer)", art="Halbpalette", laenge=800, breite=600,
             hoehe=144, eigengewicht=10, nutzlast=500, max_laenge=800, stellplaetze=0.5, abrechnung="Tausch",
             bemerkung=q),
        dict(lht_id="EW", bezeichnung="Einwegpalette 1200 × 800", art="Einwegpalette", laenge=1200, breite=800,
             hoehe=120, eigengewicht=15, nutzlast=1000, max_laenge=1200, stellplaetze=1, abrechnung="Kauf",
             bemerkung=q + "; wird nicht getauscht (Kaufpreis)"),
        dict(lht_id="IP", bezeichnung="Industriepalette 1200 × 1000", art="Industriepalette", laenge=1200,
             breite=1000, hoehe=144, eigengewicht=30, nutzlast=1500, max_laenge=1200, stellplaetze=1.25,
             abrechnung="Tausch", bemerkung=q),
        dict(lht_id="SB", bezeichnung="Sonderbehälter (Maße eintragen)", art="Sonderbehälter", aktiv="nein",
             abrechnung="Kauf", bemerkung="Vorlage: Maße, Gewicht und Preis eintragen, dann aktivieren")]
    return [dict(_zeile(LHT), aktiv="ja", **w) if "aktiv" not in w else dict(_zeile(LHT), **w) for w in werte]


# ------------------------------------------------------------------ Tarifstände
def staende(tarife, tarif_id):
    """Alle Stände eines Tarifs (gleiche Grundkennung ohne Versionsendung „-V2“ bzw. gleiche Bezeichnung und
    gleicher Dienstleister), nach Gültig ab: [dict(tarif_id, gueltig_ab, gueltig_bis, stand, basis, aktiv)]."""
    t = next((x for x in tarife if x.get("tarif_id") == tarif_id), None)
    if not t:
        return []

    def grund(x):
        i = str(x.get("tarif_id") or "")
        for teil in ("-V", "-20"):
            if teil in i:
                i = i[:i.rindex(teil)]
        return i
    g = grund(t)
    gleich = [x for x in tarife if grund(x) == g and x.get("dienstleister") == t.get("dienstleister")]
    return [dict(tarif_id=x["tarif_id"], gueltig_ab=x.get("gueltig_ab"), gueltig_bis=x.get("gueltig_bis"),
                 stand=x.get("stand"), basis=x.get("basis"), aktiv=x.get("aktiv") or "ja")
            for x in sorted(gleich, key=lambda x: (x.get("gueltig_ab") or "", x["tarif_id"]))]


def alter_tage(t, heute=None):
    """Alter des Preisstands in Tagen (None ohne Stand)."""
    s = t.get("stand")
    if not s:
        return None
    try:
        return ((heute or datetime.date.today()) - datetime.date.fromisoformat(s)).days
    except ValueError:
        return None
