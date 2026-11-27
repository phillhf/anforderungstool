"""Sicherungen, stündliche Hintergrundaufgaben und Updates.

Sicherungen: täglich automatisch, auf Knopfdruck und von der Befehlszeile.

Updates: Prüft die GitHub-Releases. Das Setup wird geladen, per SHA-256 geprüft und über eine
einmalige geplante Aufgabe als SYSTEM gestartet. So läuft es unabhängig vom Dienst weiter,
den es während der Installation beendet und danach wieder startet.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from . import __version__

log = logging.getLogger(__name__)

STANDARD_ANZAHL = 14
REPO = "phillhf/anforderungstool"
SETUP_MUSTER = re.compile(r"^Anforderungstool-Setup-(\d+\.\d+\.\d+)\.exe$")
UPDATE_AUFGABE = "Anforderungstool Update"
# Im Release-Text steht unter dieser Zeile der feste Teil (Installation, technische Eckdaten).
# Im Update-Fenster zeigen wir nur, was darüber steht: die Neuerungen.
NOTIZEN_ENDE = "<!-- ende-der-neuerungen -->"


class WartungsFehler(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# --------------------------------------------------------------------------- Sicherungen
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


def tages_sicherung(db, pfade) -> None:
    """Legt die Sicherung des Tages an, falls es sie noch nicht gibt."""
    heute = f"auto-{datetime.now():%Y-%m-%d}"
    if not any(pfade.sicherungen.glob(f"{heute}*.db")):
        sicherung_anlegen(db, pfade, "auto")
        aufraeumen(db, pfade)


def anhaenge_sichern(pfade) -> int:
    """Spiegelt neue Anhänge nach sicherungen/anhaenge. Anhänge ändern sich nie, deshalb reicht es, fehlende zu kopieren.

    Gelöschte Anhänge bleiben in der Sicherung erhalten.
    """
    if not pfade.anhaenge.exists():
        return 0
    ziel_basis = pfade.sicherungen / "anhaenge"
    neu = 0
    for quelle in pfade.anhaenge.rglob("*"):
        if not quelle.is_file():
            continue
        ziel = ziel_basis / quelle.relative_to(pfade.anhaenge)
        if ziel.exists() and ziel.stat().st_size == quelle.stat().st_size:
            continue
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(quelle, ziel)
        neu += 1
    return neu


class Stuendlich:
    """Führt Aufgaben beim Start und danach stündlich aus (Sicherung, Erinnerungen)."""

    def __init__(self, aufgaben: list):
        self.aufgaben = aufgaben
        self._stopp = threading.Event()
        self._thread: threading.Thread | None = None

    def starten(self) -> None:
        self._thread = threading.Thread(target=self._schleife, name="stuendlich", daemon=True)
        self._thread.start()

    def stoppen(self) -> None:
        self._stopp.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _schleife(self) -> None:
        while not self._stopp.is_set():
            for aufgabe in self.aufgaben:
                try:
                    aufgabe()
                except Exception:
                    log.exception("Stündliche Aufgabe %s", getattr(aufgabe, "__name__", aufgabe))
            self._stopp.wait(3600)


# --------------------------------------------------------------------------- Updates
def version_tupel(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


_update_cache: dict = {"zeit": 0.0, "daten": None}


def update_pruefen(neu: bool = False, abrufen=None) -> dict:
    """Fragt das neueste Release bei GitHub ab (10 Minuten zwischengespeichert)."""
    if not neu and abrufen is None and _update_cache["daten"] and time.time() - _update_cache["zeit"] < 600:
        return _update_cache["daten"]
    try:
        rel = (abrufen or _github_json)(f"https://api.github.com/repos/{REPO}/releases/latest")
    except Exception as e:
        log.info("Update-Prüfung fehlgeschlagen: %s", e)
        return {"aktuell": __version__, "fehler": "keine_verbindung"}
    neueste = rel.get("tag_name", "").lstrip("v")
    setup = next((a for a in rel.get("assets", []) if SETUP_MUSTER.match(a["name"])), None)
    pruefsumme = next((a for a in rel.get("assets", []) if setup and a["name"] == setup["name"] + ".sha256"), None)
    daten = {
        "aktuell": __version__,
        "neueste": neueste,
        "verfuegbar": bool(neueste) and version_tupel(neueste) > version_tupel(__version__),
        "notizen": (rel.get("body") or "").split(NOTIZEN_ENDE)[0].strip(),
        "url": rel.get("html_url", ""),
        "setup_url": setup["browser_download_url"] if setup else None,
        "sha256_url": pruefsumme["browser_download_url"] if pruefsumme else None,
        "installierbar": bool(setup and pruefsumme) and sys.platform == "win32" and getattr(sys, "frozen", False),
    }
    if abrufen is None:
        _update_cache.update(zeit=time.time(), daten=daten)
    return daten


def _github_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "anforderungstool-updater"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _laden(url: str, ziel: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "anforderungstool-updater"})
    with urllib.request.urlopen(req, timeout=60) as r, ziel.open("wb") as f:
        shutil.copyfileobj(r, f)


def update_installieren(pfade, info: dict) -> str:
    if not info.get("installierbar"):
        raise WartungsFehler("update_nicht_moeglich")
    pfade.updates.mkdir(parents=True, exist_ok=True)
    name = info["setup_url"].rsplit("/", 1)[-1]
    if not SETUP_MUSTER.match(name):
        raise WartungsFehler("update_nicht_moeglich")
    setup = pfade.updates / name
    pruef = pfade.updates / (name + ".sha256")
    _laden(info["sha256_url"], pruef)
    _laden(info["setup_url"], setup)
    erwartet = pruef.read_text(encoding="ascii").split()[0].lower()
    h = hashlib.sha256()
    with setup.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    if h.hexdigest() != erwartet:
        setup.unlink(missing_ok=True)
        raise WartungsFehler("update_pruefsumme")
    xml = pfade.updates / "aufgabe.xml"
    # UTF-16 mit BOM, wie schtasks es erwartet
    xml.write_text(aufgabe_xml(setup, pfade.logs / "update.log"), encoding="utf-16")
    schtasks = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "schtasks.exe"
    subprocess.run([str(schtasks), "/Create", "/F", "/TN", UPDATE_AUFGABE, "/XML", str(xml)], check=True, capture_output=True)
    subprocess.run([str(schtasks), "/Run", "/TN", UPDATE_AUFGABE], check=True, capture_output=True)
    log.info("Update auf %s gestartet", info.get("neueste"))
    return info.get("neueste", "")


def aufgabe_xml(setup: Path, logdatei: Path) -> str:
    """Einmalige geplante Aufgabe, die das Setup als SYSTEM startet (nur per /Run ausgelöst)."""
    from xml.sax.saxutils import escape

    argumente = f'/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="{logdatei}"'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Anforderungstool: Update installieren</Description></RegistrationInfo>
  <Triggers><TimeTrigger><StartBoundary>2099-01-01T00:00:00</StartBoundary><Enabled>false</Enabled></TimeTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(str(setup))}</Command><Arguments>{escape(argumente)}</Arguments></Exec></Actions>
</Task>
"""
