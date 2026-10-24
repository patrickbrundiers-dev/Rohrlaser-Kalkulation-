"""Nachfassen verschickter Angebote (Plan A9): E-Mail-Entwurf aus der Vorlage (Einstellungen nachfassen_betreff,
nachfassen_text), wie die Materialanfrage nur in Outlook angezeigt bzw. als E-Mail-Datei gespeichert, nie gesendet.

Platzhalter: {angebot}, {kunde}, {angebot_datum}, {gueltig_bis}, {ansprechpartner}, {anrede}, {absender}.
"""
import datetime

from . import materialanfrage as ma


def _datum_text(d):
    if isinstance(d, str):
        try:
            d = datetime.date.fromisoformat(d[:10])
        except ValueError:
            return d
    return d.strftime("%d.%m.%Y") if d else ""


def werte(kopf, kunde, einst, gueltig_bis=None):
    ansprech = ((kunde or {}).get("ansprechpartner") or "").strip()
    return dict(angebot=kopf.get("nummer") or "", kunde=kopf.get("kunde") or "",
                angebot_datum=_datum_text(kopf.get("datum")), gueltig_bis=_datum_text(gueltig_bis),
                ansprechpartner=ansprech, anrede=f"Guten Tag {ansprech}," if ansprech else
                "Sehr geehrte Damen und Herren,", absender=ma.absender(einst))


def betreff(kopf, kunde, einst, gueltig_bis=None):
    return ma._vorlage(ma._einst(einst, "nachfassen_betreff"), werte(kopf, kunde, einst, gueltig_bis)).strip()


def text(kopf, kunde, einst, gueltig_bis=None):
    return ma._vorlage(ma._einst(einst, "nachfassen_text"), werte(kopf, kunde, einst, gueltig_bis))

