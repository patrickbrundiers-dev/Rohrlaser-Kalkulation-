"""Synthetische TRUMPF-LST-Dateien im Aufbau der echten (keine Kundendaten im Repo) für die Tests des Lernsystems."""

ZEITEN = ["Calculated First Cut Machine Time", "Calculated Contour Machine Time", "Calculated Cut Off Machine Time",
          "Last Program Run Measured First Cut Machine Time", "Last Program Run Measured Contour Machine Time",
          "Last Program Run Measured Cut Off Machine Time", "Number Of Recorded Part Times",
          "Average Measured First Cut Machine Time", "Average Measured Contour Machine Time",
          "Average Measured Cut Off Machine Time", "Data Set Name"]


def abschnitt(name, namen, zeilen):
    mm = "\n".join(f"MM,AT,1,{10 * (i + 1):4d},1,1,,'{n}',,'',T" for i, n in enumerate(namen))
    da = ["DA," + ",".join(f"'{w}'" if isinstance(w, str) else str(w) for w in z) for z in zeilen]
    return f"BEGIN_{name}\nC\nZA,MM,{len(namen)}\n{mm}\nC\nZA,DA,{len(zeilen)}\n" + "\n".join(da) + \
        f"\nC\nENDE_{name}\nC\n"


def lst(name, weg=1978.5, konturen=15, ber=(6.32, 13.17, 2.96), letzt=(0, 0, 0), n=0, mittel=(0, 0, 0), job="",
        rund=None, h=60.0, b=40.0, wand=2.0, laenge=425.0, material="St37", artikel="10186133", datum="10.03.2025",
        maschine="Tube 5000 (T11) 1"):
    """LST eines Programms mit einem Teil; rund = Durchmesser (Rundrohr), sonst Rechteck h × b."""
    info = abschnitt("EINRICHTEPLAN_INFO", ["Maschine", "Programmnummer", "Datum", "Material-ID", "Maschinenzeit",
                                            "Cutting length", "viewer name machine"],
                     [["T11", name, datum, material, round(sum(ber) / 60, 2), weg, maschine]])
    if rund:
        tech = abschnitt("TUBE_TECH", ["Rohr-ID", "Querschnitt", "Rohrlaenge", "Wandstaerke",
                                       "(Huellkreis-)Durchmesser (Rechteck-/Rundrohr)", "Material", "Mass Per Meter"],
                         [["RR", 0, 6000.0, wand, rund, material, 2.0]])
    else:
        tech = abschnitt("TUBE_TECH", ["Rohr-ID", "Querschnitt", "Rohrlaenge", "Wandstaerke",
                                       "Eckenradius (Rechteckrohr)", "Hoehe (Rechteckrohr)", "Breite (Rechteckrohr)",
                                       "Material", "Mass Per Meter"],
                         [["1_400X600X20_1_20", 1, 6000.0, wand, 2.0, h, b, material, 2.31]])
    teil = abschnitt("TUBE_PART_TECH", ["Tabellenidentifikator", "Work Part Length"], [["TPT-1", laenge]])
    zeit = abschnitt("TUBE_PART_TIMES", ZEITEN, [[*ber, *letzt, n, *mittel, "TPT-1"]])
    verbr = abschnitt("CONSUMPTION_TIMES", ["ConsumptionGroup", "GasType", "OnTime"], [[1, 2, 21.31], [2, 0, 9.0]])
    nc = ["BEGIN_PROGRAMM"] + [f'TC_LASER_ON(1,"ST020",{k},100)\nG1 X10\nTC_LASER_OFF(2)' for k in range(konturen)]
    kopf = abschnitt("FERTIGUNG_AUFTRAG_TMP", ["Jobname", "FertAuftrBez", "Programmname", "SollAnzahl"],
                     [[job, artikel, name, 2]]) if job else ""
    return ("BD\n" + kopf + "ED\nC\n" if job else "") + "BD\nSET_METRIC\nC\n" + info + tech + teil + zeit + verbr + \
        "\n".join(nc) + "\nENDE_PROGRAMM\nC\nED\n"
