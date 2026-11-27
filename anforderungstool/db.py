"""SQLite-Datenbank mit fortlaufenden Migrationen.

Neue Tabellen oder Spalten immer als neuen Eintrag in MIGRATIONEN anhängen,
bestehende Einträge nie ändern – installierte Datenbanken haben sie schon.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

# Rechte, die ein Benutzer zusätzlich haben kann. Anfordern darf jeder.
# Wer genehmigt, ergibt sich aus der Hierarchie; wer einen Katalog pflegt oder ausführt, aus der Zuordnung am Katalog.
RECHTE = ("verwalten", "statistik")

# Rollen eines Benutzers an einem Katalog
KATALOG_ROLLEN = ("nutzer", "pfleger", "ausfuehrender")

MIGRATIONEN: list[str] = [
    # 1 – Grundgerüst
    """
    CREATE TABLE einstellungen (
        schluessel TEXT PRIMARY KEY,
        wert       TEXT NOT NULL
    );
    CREATE TABLE kostenstellen (
        id          INTEGER PRIMARY KEY,
        nummer      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        bezeichnung TEXT NOT NULL DEFAULT '',
        aktiv       INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE benutzer (
        id              INTEGER PRIMARY KEY,
        benutzername    TEXT NOT NULL UNIQUE COLLATE NOCASE,
        anzeigename     TEXT NOT NULL,
        email           TEXT NOT NULL DEFAULT '',
        passwort_hash   TEXT NOT NULL DEFAULT '',
        quelle          TEXT NOT NULL DEFAULT 'lokal',
        aktiv           INTEGER NOT NULL DEFAULT 1,
        rechte          TEXT NOT NULL DEFAULT '[]',
        vorgesetzter_id INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
        grenze          REAL DEFAULT 0,
        kostenstelle_id INTEGER REFERENCES kostenstellen(id) ON DELETE SET NULL,
        erstellt        TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE sitzungen (
        token_hash  TEXT PRIMARY KEY,
        benutzer_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
        erstellt    TEXT NOT NULL DEFAULT (datetime('now')),
        zuletzt     TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE kataloge (
        id           INTEGER PRIMARY KEY,
        name         TEXT NOT NULL,
        beschreibung TEXT NOT NULL DEFAULT '',
        email        TEXT NOT NULL DEFAULT '',
        aktiv        INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE katalog_zuordnung (
        katalog_id  INTEGER NOT NULL REFERENCES kataloge(id) ON DELETE CASCADE,
        benutzer_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
        rolle       TEXT NOT NULL,
        PRIMARY KEY (katalog_id, benutzer_id, rolle)
    );
    CREATE TABLE produkte (
        id           INTEGER PRIMARY KEY,
        katalog_id   INTEGER NOT NULL REFERENCES kataloge(id) ON DELETE CASCADE,
        name         TEXT NOT NULL,
        beschreibung TEXT NOT NULL DEFAULT '',
        einheit      TEXT NOT NULL DEFAULT 'Stück',
        preis        REAL NOT NULL DEFAULT 0,
        aktiv        INTEGER NOT NULL DEFAULT 1,
        reihenfolge  INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE vertretungen (
        id          INTEGER PRIMARY KEY,
        benutzer_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
        vertreter_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
        von         TEXT NOT NULL,
        bis         TEXT NOT NULL
    );
    CREATE TABLE anforderungen (
        id               INTEGER PRIMARY KEY,
        antragsteller_id INTEGER NOT NULL REFERENCES benutzer(id),
        katalog_id       INTEGER NOT NULL REFERENCES kataloge(id),
        kostenstelle_id  INTEGER REFERENCES kostenstellen(id),
        anlass           TEXT NOT NULL DEFAULT '',
        datum            TEXT,
        uhrzeit          TEXT NOT NULL DEFAULT '',
        ort              TEXT NOT NULL DEFAULT '',
        bemerkung        TEXT NOT NULL DEFAULT '',
        summe            REAL NOT NULL DEFAULT 0,
        status           TEXT NOT NULL DEFAULT 'entwurf',
        bearbeiter_id    INTEGER REFERENCES benutzer(id),
        erstellt         TEXT NOT NULL DEFAULT (datetime('now')),
        uebermittelt     TEXT,
        abgeschlossen    TEXT
    );
    CREATE TABLE positionen (
        id             INTEGER PRIMARY KEY,
        anforderung_id INTEGER NOT NULL REFERENCES anforderungen(id) ON DELETE CASCADE,
        produkt_id     INTEGER REFERENCES produkte(id) ON DELETE SET NULL,
        name           TEXT NOT NULL,
        einheit        TEXT NOT NULL DEFAULT '',
        preis          REAL NOT NULL,
        menge          REAL NOT NULL
    );
    CREATE TABLE verlauf (
        id             INTEGER PRIMARY KEY,
        anforderung_id INTEGER NOT NULL REFERENCES anforderungen(id) ON DELETE CASCADE,
        zeit           TEXT NOT NULL DEFAULT (datetime('now')),
        benutzer_id    INTEGER REFERENCES benutzer(id),
        im_namen_von   INTEGER REFERENCES benutzer(id),
        aktion         TEXT NOT NULL,
        notiz          TEXT NOT NULL DEFAULT '',
        weiter_an      INTEGER REFERENCES benutzer(id),
        summe          REAL
    );
    CREATE TABLE mails (
        id        INTEGER PRIMARY KEY,
        an        TEXT NOT NULL,
        betreff   TEXT NOT NULL,
        text      TEXT NOT NULL,
        status    TEXT NOT NULL DEFAULT 'wartet',
        versuche  INTEGER NOT NULL DEFAULT 0,
        fehler    TEXT NOT NULL DEFAULT '',
        erstellt  TEXT NOT NULL DEFAULT (datetime('now')),
        gesendet  TEXT
    );
    CREATE INDEX anforderungen_antragsteller ON anforderungen(antragsteller_id);
    CREATE INDEX anforderungen_bearbeiter ON anforderungen(bearbeiter_id);
    CREATE INDEX anforderungen_status ON anforderungen(status);
    CREATE INDEX positionen_anforderung ON positionen(anforderung_id);
    CREATE INDEX verlauf_anforderung ON verlauf(anforderung_id);
    CREATE INDEX vertretungen_benutzer ON vertretungen(benutzer_id)
    """,
    # 2 – Erinnerungen: wann zuletzt an diese Anforderung erinnert wurde
    """
    ALTER TABLE anforderungen ADD COLUMN erinnert TEXT
    """,
]

STANDARD_EINSTELLUNGEN = {
    "adresse": "",
    "mail_ereignisse": {"neue_aufgabe": True, "entscheidung": True, "genehmigt": True, "erledigt": True},
}


class Datenbank:
    """Eine Verbindung für den ganzen Prozess, Zugriffe über eine Sperre serialisiert."""

    def __init__(self, pfad: Path):
        self.pfad = Path(pfad)
        self._sperre = threading.RLock()
        self._verbinden()

    def _verbinden(self) -> None:
        self._con = sqlite3.connect(self.pfad, check_same_thread=False, isolation_level=None)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA foreign_keys = ON")
        self._con.execute("PRAGMA journal_mode = WAL")
        self._migrieren()

    def sichern_nach(self, ziel: Path) -> None:
        """Konsistente Kopie der laufenden Datenbank (SQLite-Backup-API)."""
        with self._sperre:
            ziel_con = sqlite3.connect(ziel)
            try:
                self._con.backup(ziel_con)
            finally:
                ziel_con.close()

    def _migrieren(self) -> None:
        with self._sperre:
            self._con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self._con.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                self._con.execute("INSERT INTO schema_version VALUES (0)")
                version = 0
            else:
                version = row[0]
            for nr, sql in enumerate(MIGRATIONEN, start=1):
                if nr <= version:
                    continue
                self._con.execute("BEGIN")
                try:
                    for befehl in [b.strip() for b in sql.split(";") if b.strip()]:
                        self._con.execute(befehl)
                    self._con.execute("UPDATE schema_version SET version = ?", (nr,))
                    self._con.execute("COMMIT")
                except Exception:
                    self._con.execute("ROLLBACK")
                    raise
            for k, v in STANDARD_EINSTELLUNGEN.items():
                self._con.execute("INSERT OR IGNORE INTO einstellungen (schluessel, wert) VALUES (?, ?)", (k, json.dumps(v)))

    # -- Zugriff -------------------------------------------------------------
    def eins(self, sql: str, params: tuple = ()) -> dict | None:
        with self._sperre:
            row = self._con.execute(sql, params).fetchone()
        return dict(row) if row else None

    def alle(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._sperre:
            return [dict(r) for r in self._con.execute(sql, params).fetchall()]

    def ausfuehren(self, sql: str, params: tuple = ()) -> int:
        """Führt einen Schreibbefehl aus und gibt lastrowid zurück."""
        with self._sperre:
            cur = self._con.execute(sql, params)
            return cur.lastrowid or 0

    def transaktion(self):
        return _Transaktion(self)

    # -- Einstellungen ---------------------------------------------------------
    def einstellung(self, schluessel: str, standard=None):
        row = self.eins("SELECT wert FROM einstellungen WHERE schluessel = ?", (schluessel,))
        return json.loads(row["wert"]) if row else standard

    def setze_einstellung(self, schluessel: str, wert) -> None:
        self.ausfuehren(
            "INSERT INTO einstellungen (schluessel, wert) VALUES (?, ?) "
            "ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
            (schluessel, json.dumps(wert)),
        )

    def schliessen(self) -> None:
        with self._sperre:
            self._con.close()


class _Transaktion:
    """Mehrere Schreibbefehle als Einheit. Innerhalb darf über db.* weitergearbeitet werden (RLock)."""

    def __init__(self, db: Datenbank):
        self.db = db

    def __enter__(self) -> Datenbank:
        self.db._sperre.acquire()
        self.db._con.execute("BEGIN")
        return self.db

    def __exit__(self, typ, wert, tb) -> None:
        try:
            self.db._con.execute("ROLLBACK" if typ else "COMMIT")
        finally:
            self.db._sperre.release()
