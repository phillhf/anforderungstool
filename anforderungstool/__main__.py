"""Befehlszeile.

  python -m anforderungstool                       Server starten (Port aus config.json)
  python -m anforderungstool serve [--port N]      dasselbe
  python -m anforderungstool config --port N       Port in config.json speichern
  python -m anforderungstool config --zertifikat C --schluessel K   HTTPS einschalten (PEM-Dateien), leer = aus
  python -m anforderungstool passwort BENUTZER [--passwort P]       Passwort neu setzen (Notfall)
  python -m anforderungstool sicherung             Sicherung der Datenbank anlegen
  python -m anforderungstool --version

Überall gilt: --data ORDNER wählt einen anderen Datenordner.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import logging.handlers
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .config import Pfade, lade_konfiguration, speichere_konfiguration, standard_datenordner


def _logging(pfade: Pfade) -> None:
    pfade.logs.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    datei = logging.handlers.RotatingFileHandler(pfade.logs / "anforderungstool.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    datei.setFormatter(fmt)
    konsole = logging.StreamHandler()
    konsole.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(datei)
    root.addHandler(konsole)


def befehl_serve(pfade: Pfade, port: int | None) -> int:
    import uvicorn

    from .server import erstelle_app

    _logging(pfade)
    k = lade_konfiguration(pfade)
    if port:
        k.port = port
    logging.getLogger(__name__).info("%s %s startet auf %s:%s, Daten in %s", APP_NAME, __version__, k.host, k.port, pfade.daten)
    app = erstelle_app(pfade)
    ssl = {"ssl_certfile": k.zertifikat, "ssl_keyfile": k.schluessel} if k.https else {}
    uvicorn.run(app, host=k.host, port=k.port, log_config=None, access_log=False, **ssl)
    return 0


def befehl_config(pfade: Pfade, port: int | None, zertifikat: str | None, schluessel: str | None) -> int:
    k = lade_konfiguration(pfade)
    if zertifikat is not None:
        k.zertifikat = zertifikat
    if schluessel is not None:
        k.schluessel = schluessel
    if port is not None:
        if not 1 <= port <= 65535:
            print("Port muss zwischen 1 und 65535 liegen.", file=sys.stderr)
            return 2
        k.port = port
    pfade.anlegen()
    speichere_konfiguration(pfade, k)
    from .db import Datenbank

    Datenbank(pfade.datenbank).schliessen()
    print(f"Konfiguration gespeichert: {pfade.config} (Port {k.port})")
    return 0


def befehl_passwort(pfade: Pfade, benutzer: str, passwort: str | None) -> int:
    from . import auth
    from .db import Datenbank

    db = Datenbank(pfade.datenbank)
    try:
        b = db.eins("SELECT id, quelle FROM benutzer WHERE benutzername = ?", (benutzer,))
        if b is None:
            print(f"Benutzer „{benutzer}“ gibt es nicht.", file=sys.stderr)
            return 1
        if passwort is None:
            passwort = getpass.getpass("Neues Passwort: ")
        if len(passwort) < auth.MIN_PASSWORT:
            print(f"Das Passwort braucht mindestens {auth.MIN_PASSWORT} Zeichen.", file=sys.stderr)
            return 2
        db.ausfuehren("UPDATE benutzer SET passwort_hash = ?, quelle = 'lokal', aktiv = 1 WHERE id = ?", (auth.passwort_hash(passwort), b["id"]))
        db.ausfuehren("DELETE FROM sitzungen WHERE benutzer_id = ?", (b["id"],))
        print("Passwort gesetzt.")
        return 0
    finally:
        db.schliessen()


def befehl_sicherung(pfade: Pfade) -> int:
    from . import wartung
    from .db import Datenbank

    db = Datenbank(pfade.datenbank)
    try:
        print(f"Sicherung angelegt: {wartung.sicherung_anlegen(db, pfade)}")
        return 0
    finally:
        db.schliessen()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="anforderungstool", description=APP_NAME)
    p.add_argument("--data", type=Path, default=None, help="Datenordner")
    p.add_argument("--version", action="store_true")
    unter = p.add_subparsers(dest="befehl")
    s = unter.add_parser("serve")
    s.add_argument("--port", type=int)
    c = unter.add_parser("config")
    c.add_argument("--port", type=int)
    c.add_argument("--zertifikat")
    c.add_argument("--schluessel")
    pw = unter.add_parser("passwort")
    pw.add_argument("benutzer")
    pw.add_argument("--passwort")
    unter.add_parser("sicherung")
    a = p.parse_args(argv)
    if a.version:
        print(f"{APP_NAME} {__version__}")
        return 0
    pfade = Pfade(a.data or standard_datenordner())
    if a.befehl == "config":
        return befehl_config(pfade, a.port, a.zertifikat, a.schluessel)
    if a.befehl == "passwort":
        return befehl_passwort(pfade, a.benutzer, a.passwort)
    if a.befehl == "sicherung":
        return befehl_sicherung(pfade)
    return befehl_serve(pfade, getattr(a, "port", None))


if __name__ == "__main__":
    sys.exit(main())
