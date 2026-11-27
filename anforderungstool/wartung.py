"""Sicherungen der Datenbank: täglich automatisch, auf Knopfdruck und von der Befehlszeile."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

STANDARD_ANZAHL = 14


def sicherung_anlegen(db, pfade, praefix: str = "sicherung") -> Path:
    pfade.sicherungen.mkdir(parents=True, exist_ok=True)
    ziel = pfade.sicherungen / f"{praefix}-{datetime.now():%Y-%m-%d_%H%M%S}.db"
    db.sichern_nach(ziel)
    return ziel


def sicherungen(pfade) -> list[dict]:
    if not pfade.sicherungen.exists():
        return []
    return [{"name": p.name, "groesse": p.stat().st_size, "zeit": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in sorted(pfade.sicherungen.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)]


def aufraeumen(db, pfade) -> None:
    anzahl = int(db.einstellung("sicherung_anzahl", STANDARD_ANZAHL) or STANDARD_ANZAHL)
    autos = sorted(pfade.sicherungen.glob("auto-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for alt in autos[anzahl:]:
        alt.unlink(missing_ok=True)


class AutoSicherung:
    """Legt einmal am Tag eine Sicherung an (beim Start und danach stündlich geprüft)."""

    def __init__(self, db, pfade):
        self.db = db
        self.pfade = pfade
        self._stopp = threading.Event()
        self._thread: threading.Thread | None = None

    def starten(self) -> None:
        self._thread = threading.Thread(target=self._schleife, name="sicherung", daemon=True)
        self._thread.start()

    def stoppen(self) -> None:
        self._stopp.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _schleife(self) -> None:
        while not self._stopp.is_set():
            try:
                heute = f"auto-{datetime.now():%Y-%m-%d}"
                if not any(self.pfade.sicherungen.glob(f"{heute}*.db")):
                    sicherung_anlegen(self.db, self.pfade, "auto")
                    aufraeumen(self.db, self.pfade)
            except Exception:
                log.exception("Automatische Sicherung")
            self._stopp.wait(3600)
