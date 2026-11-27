"""Anmeldung über Active Directory / LDAP (zusätzlich zu den eigenen Benutzerkonten).

Einstellung "ldap" (JSON):
  aktiv          true/false
  server         z. B. "ldaps://dc01.klinik.local" (mehrere durch Komma)
  domaene        UPN-Suffix, z. B. "klinik.local" → Anmeldung als benutzer@klinik.local
  basis_dn       z. B. "DC=klinik,DC=local" (für die Suche nach Namen, E-Mail und Gruppen)
  zugang_gruppe  nur Mitglieder dieser Gruppe dürfen sich anmelden, "" = alle aus dem Verzeichnis
  gruppen        [{"gruppe": "CN=Anforderung-Admins,OU=…" oder "Anforderung-Admins", "recht": "verwalten"}, …]

Benutzer aus dem Verzeichnis werden bei der ersten Anmeldung angelegt (quelle "ldap").
Name und E-Mail werden bei jeder Anmeldung aktualisiert. Rechte aus Gruppen kommen hinzu,
was der Admin im Tool vergeben hat, bleibt erhalten. Vorgesetzter, Freigabegrenze,
Kostenstelle und Kataloge pflegt der Admin im Tool.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

STANDARD = {"aktiv": False, "server": "", "domaene": "", "basis_dn": "", "zugang_gruppe": "", "gruppen": []}


class VerzeichnisFehler(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def einstellungen(db) -> dict:
    e = dict(STANDARD)
    e.update(db.einstellung("ldap", {}) or {})
    return e


def _escape(wert: str) -> str:
    return re.sub(r"([\\*()\x00])", lambda m: "\\%02x" % ord(m.group(1)), wert)


def _cn(dn: str) -> str:
    m = re.match(r"\s*CN=([^,]+)", dn, re.IGNORECASE)
    return m.group(1) if m else dn


def anmelden(e: dict, benutzer: str, passwort: str, verbindung=None) -> dict:
    """Prüft Benutzer und Passwort am Verzeichnis. Gibt {anzeigename, email, gruppen} zurück.

    verbindung(server, user, passwort) → ldap3.Connection (für Tests austauschbar).
    """
    if not passwort or not benutzer:
        raise VerzeichnisFehler("anmeldung_falsch")
    if not re.match(r"^[A-Za-z0-9._-]{1,64}$", benutzer):
        raise VerzeichnisFehler("anmeldung_falsch")
    upn = f"{benutzer}@{e['domaene']}" if e.get("domaene") else benutzer
    if verbindung is None:
        verbindung = _ldap3_verbindung
    try:
        con = verbindung(e["server"], upn, passwort)
    except VerzeichnisFehler:
        raise
    except Exception as ex:
        log.warning("LDAP nicht erreichbar: %s", ex)
        raise VerzeichnisFehler("verzeichnis_nicht_erreichbar") from ex
    try:
        anzeigename, email, gruppen = benutzer, "", []
        if e.get("basis_dn"):
            con.search(e["basis_dn"], f"(|(sAMAccountName={_escape(benutzer)})(userPrincipalName={_escape(upn)}))",
                       attributes=["displayName", "mail", "memberOf"])
            if con.entries:
                eintrag = con.entries[0]
                if "displayName" in eintrag and eintrag.displayName.value:
                    anzeigename = str(eintrag.displayName.value)
                if "mail" in eintrag and eintrag.mail.value:
                    email = str(eintrag.mail.value)
                if "memberOf" in eintrag and eintrag.memberOf.values:
                    gruppen = [str(g) for g in eintrag.memberOf.values]
        return {"anzeigename": anzeigename, "email": email, "gruppen": gruppen}
    finally:
        try:
            con.unbind()
        except Exception:
            pass


def _ldap3_verbindung(server: str, upn: str, passwort: str):
    import ldap3

    pool = ldap3.ServerPool([ldap3.Server(s.strip(), get_info=ldap3.NONE, connect_timeout=5) for s in server.split(",") if s.strip()],
                            ldap3.FIRST, active=1, exhaust=True)
    con = ldap3.Connection(pool, user=upn, password=passwort, authentication=ldap3.SIMPLE, receive_timeout=10)
    if not con.bind():
        raise VerzeichnisFehler("anmeldung_falsch")
    return con


def _mitglied(gruppe: str, namen: set[str]) -> bool:
    g = (gruppe or "").strip().lower()
    return bool(g) and (g in namen or _cn(g).lower() in namen)


def zugang(e: dict, gruppen: list[str]) -> bool:
    if not (e.get("zugang_gruppe") or "").strip():
        return True
    namen = {g.lower() for g in gruppen} | {_cn(g).lower() for g in gruppen}
    return _mitglied(e["zugang_gruppe"], namen)


def rechte_fuer(e: dict, gruppen: list[str]) -> set[str]:
    namen = {g.lower() for g in gruppen} | {_cn(g).lower() for g in gruppen}
    return {z.get("recht") for z in e.get("gruppen", []) if _mitglied(z.get("gruppe", ""), namen) and z.get("recht")}
