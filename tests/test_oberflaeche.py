"""Alle Texte der Oberfläche stehen in de.json, alle Fehlercodes des Servers haben einen Text."""

from __future__ import annotations

import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "anforderungstool" / "static"
TEXTE = json.loads((STATIC / "i18n" / "de.json").read_text(encoding="utf-8"))


def _hat(schluessel: str) -> bool:
    knoten = TEXTE
    for teil in schluessel.split("."):
        if not isinstance(knoten, dict) or teil not in knoten:
            return False
        knoten = knoten[teil]
    return True


def test_alle_schluessel_vorhanden():
    fehlt = []
    for datei in (STATIC / "js").glob("*.js"):
        for m in re.finditer(r"""\bt\(\s*["']([a-z0-9_.]+)["']""", datei.read_text(encoding="utf-8")):
            if not _hat(m.group(1)):
                fehlt.append(f"{datei.name}: {m.group(1)}")
        # Schlüssel mit Platzhalter: t(`status.${x}`) → Präfix muss es geben
        for m in re.finditer(r"""\bt\(\s*`([a-z0-9_.]+)\.\$\{""", datei.read_text(encoding="utf-8")):
            if not _hat(m.group(1)):
                fehlt.append(f"{datei.name}: {m.group(1)}.*")
    for d in ("index.html",):
        for m in re.finditer(r'data-i18n="([a-z0-9_.]+)"', (STATIC / d).read_text(encoding="utf-8")):
            if not _hat(m.group(1)):
                fehlt.append(f"{d}: {m.group(1)}")
    assert not fehlt, fehlt


def test_fehlercodes_haben_text():
    paket = Path(__file__).resolve().parent.parent / "anforderungstool"
    codes = set()
    for datei in paket.glob("*.py"):
        text = datei.read_text(encoding="utf-8")
        codes |= set(re.findall(r'fehler\(\d+, "([a-z_]+)"', text))
        codes |= set(re.findall(r'AblaufFehler\(\d+, "([a-z_]+)"', text))
        codes |= set(re.findall(r'VerzeichnisFehler\("([a-z_]+)"\)', text))
    fehlt = sorted(c for c in codes if c not in TEXTE["fehler"])
    assert not fehlt, fehlt


def test_status_und_verlauf_vollstaendig():
    from anforderungstool import ablauf

    assert set(ablauf.STATUS) <= set(TEXTE["status"])
    aktionen = set()
    for rest in re.findall(r'_verlauf\(db, anforderung_id, [^,]+, ([^\n]*)', Path(ablauf.__file__).read_text(encoding="utf-8")):
        aktionen |= set(re.findall(r'"([a-z_]+)"', rest.split(", notiz")[0]))
    assert aktionen and aktionen <= set(TEXTE["verlauf"]), aktionen - set(TEXTE["verlauf"])


def test_ausnahme_status_und_verlauf_vollstaendig():
    from anforderungstool import ausnahme

    assert set(ausnahme.STATUS) <= set(TEXTE["status"])
    quelltext = Path(ausnahme.__file__).read_text(encoding="utf-8")
    aktionen = set(re.findall(r'_verlauf\(db, [^,]+, [^,]+, "([a-z_]+)"', quelltext))
    aktionen |= set(ausnahme.AUSFUEHRUNG[1:])  # bestellt, geliefert, erledigt kommen als Variable
    assert aktionen and aktionen <= set(TEXTE["ausnahme"]["verlauf"]), aktionen - set(TEXTE["ausnahme"]["verlauf"])
