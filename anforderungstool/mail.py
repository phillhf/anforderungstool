"""E-Mail-Versand über SMTP.

Mails werden in der Tabelle „mails“ abgelegt und von einem Hintergrund-Thread verschickt.
So blockiert ein langsamer oder ausgefallener Mailserver keine Genehmigung, und
fehlgeschlagene Mails werden später erneut versucht.

Einstellung "smtp" (JSON):
  server, port, verschluesselung ("keine" | "starttls" | "ssl"), benutzer, passwort, absender
"""

from __future__ import annotations

import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from . import APP_NAME

log = logging.getLogger(__name__)

STANDARD = {"server": "", "port": 587, "verschluesselung": "starttls", "benutzer": "", "passwort": "", "absender": ""}
MAX_VERSUCHE = 5


def einstellungen(db) -> dict:
    e = dict(STANDARD)
    e.update(db.einstellung("smtp", {}) or {})
    return e


def eingerichtet(db) -> bool:
    e = einstellungen(db)
    return bool(e["server"] and e["absender"])


def einreihen(db, an: list[str] | str, betreff: str, text: str) -> None:
    """Mail zum Versand vormerken. Leere oder doppelte Adressen werden übersprungen."""
    if isinstance(an, str):
        an = [an]
    gesehen = set()
    for adresse in an:
        adresse = (adresse or "").strip()
        if not adresse or adresse.lower() in gesehen:
            continue
        gesehen.add(adresse.lower())
        db.ausfuehren("INSERT INTO mails (an, betreff, text) VALUES (?, ?, ?)", (adresse, betreff, text))


def senden(e: dict, an: str, betreff: str, text: str) -> None:
    """Eine Mail sofort verschicken. Wirft bei Fehlern."""
    nachricht = EmailMessage()
    nachricht["From"] = formataddr((APP_NAME, e["absender"]))
    nachricht["To"] = an
    nachricht["Subject"] = betreff
    nachricht["Message-ID"] = make_msgid(domain=e["absender"].split("@")[-1] or None)
    nachricht.set_content(text)
    port = int(e.get("port") or 0) or (465 if e["verschluesselung"] == "ssl" else 587)
    if e["verschluesselung"] == "ssl":
        server = smtplib.SMTP_SSL(e["server"], port, timeout=20, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(e["server"], port, timeout=20)
    try:
        if e["verschluesselung"] == "starttls":
            server.starttls(context=ssl.create_default_context())
        if e.get("benutzer"):
            server.login(e["benutzer"], e.get("passwort", ""))
        server.send_message(nachricht)
    finally:
        try:
            server.quit()
        except Exception:
            pass


class Versand:
    """Hintergrund-Thread, der wartende Mails verschickt."""

    def __init__(self, db, sender=None):
        self.db = db
        self.sender = sender or senden  # Tests setzen eine Ersatzfunktion
        self._stopp = threading.Event()
        self._wecken = threading.Event()
        self._thread: threading.Thread | None = None

    def starten(self) -> None:
        self._thread = threading.Thread(target=self._schleife, name="mailversand", daemon=True)
        self._thread.start()

    def stoppen(self) -> None:
        self._stopp.set()
        self._wecken.set()
        if self._thread:
            self._thread.join(timeout=5)

    def wecken(self) -> None:
        self._wecken.set()

    def _schleife(self) -> None:
        while not self._stopp.is_set():
            try:
                self.abarbeiten()
            except Exception:
                log.exception("Mailversand")
            self._wecken.wait(60)
            self._wecken.clear()

    def abarbeiten(self) -> int:
        """Verschickt alle fälligen Mails. Gibt die Zahl der verschickten zurück."""
        if not eingerichtet(self.db):
            return 0
        e = einstellungen(self.db)
        # nach einem Fehler steigt die Wartezeit: 1, 2, 4, 8 … Minuten
        faellig = self.db.alle(
            """SELECT * FROM mails WHERE status = 'wartet'
                AND (versuche = 0 OR datetime(erstellt, '+' || (1 << versuche) || ' minutes') <= datetime('now'))
              ORDER BY id LIMIT 50""")
        gesendet = 0
        for m in faellig:
            try:
                self.sender(e, m["an"], m["betreff"], m["text"])
            except Exception as ex:
                versuche = m["versuche"] + 1
                status = "fehler" if versuche >= MAX_VERSUCHE else "wartet"
                log.warning("Mail an %s fehlgeschlagen (%s/%s): %s", m["an"], versuche, MAX_VERSUCHE, ex)
                self.db.ausfuehren("UPDATE mails SET versuche = ?, status = ?, fehler = ? WHERE id = ?",
                                   (versuche, status, str(ex)[:500], m["id"]))
                continue
            self.db.ausfuehren("UPDATE mails SET status = 'gesendet', gesendet = datetime('now'), fehler = '' WHERE id = ?", (m["id"],))
            gesendet += 1
        # verschickte Mails nach 90 Tagen löschen
        self.db.ausfuehren("DELETE FROM mails WHERE status = 'gesendet' AND gesendet < datetime('now', '-90 days')")
        return gesendet
