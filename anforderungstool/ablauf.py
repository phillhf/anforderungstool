"""Anforderungen und Genehmigungskette.

Regeln (siehe KONZEPT.md):
- Deckt die eigene Freigabegrenze des Antragstellers die Summe, ist die Anforderung sofort genehmigt.
- Sonst geht sie an seinen Vorgesetzten. Ein Ja innerhalb der Grenze des Genehmigers genehmigt endgültig,
  darüber gilt es als Befürwortung, und die Anforderung geht automatisch an dessen Vorgesetzten.
- Ablehnen beendet den Vorgang. Rückfrage schickt sie an den Antragsteller zurück; nach dem erneuten
  Übermitteln beginnt die Kette von vorn.
- Eine Vertretung entscheidet im Namen des Vertretenen mit dessen Grenze; der Verlauf zeigt beides.
- Nach der Genehmigung meldet ein Ausführender des Katalogs „erledigt“.

Grenze NULL = unbegrenzt.
"""

from __future__ import annotations

from datetime import date

from . import mail

STATUS = ("entwurf", "genehmigung", "rueckfrage", "genehmigt", "erledigt", "abgelehnt")
BEARBEITBAR = ("entwurf", "rueckfrage")


class AblaufFehler(Exception):
    def __init__(self, status: int, code: str, **extra):
        super().__init__(code)
        self.status = status
        self.code = code
        self.extra = extra


def heute() -> str:
    return date.today().isoformat()


def grenze_deckt(grenze: float | None, summe: float) -> bool:
    return grenze is None or summe <= grenze + 1e-9


def betrag(wert: float) -> str:
    return f"{wert:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


# --------------------------------------------------------------------------- Personen
def benutzer(db, benutzer_id: int | None) -> dict | None:
    if benutzer_id is None:
        return None
    return db.eins("SELECT id, benutzername, anzeigename, email, aktiv, vorgesetzter_id, grenze, kostenstelle_id "
                   "FROM benutzer WHERE id = ?", (benutzer_id,))


def vertreter_von(db, benutzer_id: int, tag: str | None = None) -> list[dict]:
    """Wer vertritt diese Person heute?"""
    tag = tag or heute()
    return db.alle("""SELECT b.id, b.anzeigename, b.email FROM vertretungen v JOIN benutzer b ON b.id = v.vertreter_id
                       WHERE v.benutzer_id = ? AND v.von <= ? AND v.bis >= ? AND b.aktiv = 1""", (benutzer_id, tag, tag))


def vertretene(db, vertreter_id: int, tag: str | None = None) -> list[int]:
    """Für wen darf diese Person heute entscheiden?"""
    tag = tag or heute()
    return [r["benutzer_id"] for r in db.alle(
        "SELECT benutzer_id FROM vertretungen WHERE vertreter_id = ? AND von <= ? AND bis >= ?", (vertreter_id, tag, tag))]


def kette_pruefen(db, benutzer_id: int, vorgesetzter_id: int | None) -> None:
    """Verhindert Kreise in der Hierarchie (A über B über A)."""
    if vorgesetzter_id is None:
        return
    gesehen = set()
    aktuell = vorgesetzter_id
    while aktuell is not None:
        if aktuell == benutzer_id:
            raise AblaufFehler(400, "hierarchie_kreis")
        if aktuell in gesehen:
            break
        gesehen.add(aktuell)
        row = db.eins("SELECT vorgesetzter_id FROM benutzer WHERE id = ?", (aktuell,))
        if row is None:
            raise AblaufFehler(400, "benutzer_unbekannt")
        aktuell = row["vorgesetzter_id"]


def hierarchie_hinweise(db) -> list[dict]:
    """Warnungen für den Admin: Wo kann eine Anforderung nicht enden?"""
    hinweise = []
    # nur Personen, bei denen eine Anforderung landen kann: wer selbst anfordern darf oder Vorgesetzter ist
    for b in db.alle("""SELECT id, anzeigename, grenze, email, vorgesetzter_id FROM benutzer b WHERE aktiv = 1
                         AND (EXISTS (SELECT 1 FROM katalog_zuordnung z WHERE z.benutzer_id = b.id AND z.rolle = 'nutzer')
                              OR EXISTS (SELECT 1 FROM benutzer u WHERE u.vorgesetzter_id = b.id AND u.aktiv = 1))
                       ORDER BY anzeigename"""):
        if b["vorgesetzter_id"] is None and b["grenze"] is not None:
            hinweise.append({"code": "spitze_begrenzt", "benutzer_id": b["id"], "name": b["anzeigename"], "grenze": b["grenze"]})
    vorgesetzte = db.alle("""SELECT DISTINCT v.id, v.anzeigename, v.aktiv, v.email FROM benutzer b
                              JOIN benutzer v ON v.id = b.vorgesetzter_id WHERE b.aktiv = 1""")
    for v in vorgesetzte:
        if not v["aktiv"]:
            hinweise.append({"code": "vorgesetzter_inaktiv", "benutzer_id": v["id"], "name": v["anzeigename"]})
        elif not v["email"]:
            hinweise.append({"code": "vorgesetzter_ohne_email", "benutzer_id": v["id"], "name": v["anzeigename"]})
    return hinweise


# --------------------------------------------------------------------------- Kataloge
def kataloge_fuer(db, benutzer_id: int, rolle: str) -> list[int]:
    return [r["katalog_id"] for r in db.alle(
        "SELECT z.katalog_id FROM katalog_zuordnung z JOIN kataloge k ON k.id = z.katalog_id "
        "WHERE z.benutzer_id = ? AND z.rolle = ? AND k.aktiv = 1", (benutzer_id, rolle))]


def ausfuehrende(db, katalog_id: int) -> list[dict]:
    return db.alle("""SELECT b.id, b.anzeigename, b.email FROM katalog_zuordnung z JOIN benutzer b ON b.id = z.benutzer_id
                       WHERE z.katalog_id = ? AND z.rolle = 'ausfuehrender' AND b.aktiv = 1""", (katalog_id,))


# --------------------------------------------------------------------------- Lesen
def laden(db, anforderung_id: int) -> dict:
    a = db.eins("""SELECT a.*, k.name AS katalog, ks.nummer AS kostenstelle_nummer, ks.bezeichnung AS kostenstelle_bezeichnung,
                          s.anzeigename AS antragsteller, g.anzeigename AS bearbeiter
                     FROM anforderungen a
                     JOIN kataloge k ON k.id = a.katalog_id
                     JOIN benutzer s ON s.id = a.antragsteller_id
                     LEFT JOIN kostenstellen ks ON ks.id = a.kostenstelle_id
                     LEFT JOIN benutzer g ON g.id = a.bearbeiter_id
                    WHERE a.id = ?""", (anforderung_id,))
    if a is None:
        raise AblaufFehler(404, "nicht_gefunden")
    a["positionen"] = db.alle("SELECT id, produkt_id, name, einheit, preis, menge FROM positionen WHERE anforderung_id = ? ORDER BY id",
                              (anforderung_id,))
    a["verlauf"] = db.alle("""SELECT v.id, v.zeit, v.aktion, v.notiz, v.summe,
                                     b.anzeigename AS benutzer, n.anzeigename AS im_namen_von, w.anzeigename AS weiter_an
                                FROM verlauf v
                                LEFT JOIN benutzer b ON b.id = v.benutzer_id
                                LEFT JOIN benutzer n ON n.id = v.im_namen_von
                                LEFT JOIN benutzer w ON w.id = v.weiter_an
                               WHERE v.anforderung_id = ? ORDER BY v.id""", (anforderung_id,))
    return a


def darf_sehen(db, a: dict, ich: dict) -> bool:
    if "verwalten" in ich["rechte"] or a["antragsteller_id"] == ich["id"]:
        return True
    if a["bearbeiter_id"] is not None and (a["bearbeiter_id"] == ich["id"] or a["bearbeiter_id"] in vertretene(db, ich["id"])):
        return True
    if db.eins("SELECT 1 FROM verlauf WHERE anforderung_id = ? AND (benutzer_id = ? OR im_namen_von = ?)", (a["id"], ich["id"], ich["id"])):
        return True
    if a["status"] in ("genehmigt", "erledigt") and a["katalog_id"] in kataloge_fuer(db, ich["id"], "ausfuehrender"):
        return True
    return False


def moegliche_aktionen(db, a: dict, ich: dict) -> list[str]:
    aktionen = []
    if a["antragsteller_id"] == ich["id"] and a["status"] in BEARBEITBAR:
        aktionen += ["bearbeiten", "uebermitteln"]
        if a["status"] == "entwurf":
            aktionen.append("loeschen")
    if a["status"] == "genehmigung" and entscheider(db, a, ich) is not None:
        aktionen += ["genehmigen", "ablehnen", "rueckfrage"]
    if a["status"] == "genehmigt" and a["katalog_id"] in kataloge_fuer(db, ich["id"], "ausfuehrender"):
        aktionen.append("erledigen")
    return aktionen


def entscheider(db, a: dict, ich: dict) -> dict | None:
    """Darf ich bei dieser Anforderung entscheiden? → {"im_namen_von": id | None} oder None."""
    if a["status"] != "genehmigung" or a["bearbeiter_id"] is None:
        return None
    if a["bearbeiter_id"] == ich["id"]:
        return {"im_namen_von": None}
    if a["bearbeiter_id"] in vertretene(db, ich["id"]):
        return {"im_namen_von": a["bearbeiter_id"]}
    return None


# --------------------------------------------------------------------------- Bearbeiten
def speichern(db, ich: dict, daten: dict, anforderung_id: int | None = None) -> int:
    """Legt einen Entwurf an oder ändert einen Entwurf / eine Anforderung in Rückfrage."""
    katalog_id = daten["katalog_id"]
    if katalog_id not in kataloge_fuer(db, ich["id"], "nutzer"):
        raise AblaufFehler(403, "katalog_nicht_erlaubt")
    ks = daten.get("kostenstelle_id")
    if ks is not None and not db.eins("SELECT 1 FROM kostenstellen WHERE id = ? AND aktiv = 1", (ks,)):
        raise AblaufFehler(400, "kostenstelle_unbekannt")
    positionen = []
    for p in daten.get("positionen", []):
        if p["menge"] <= 0:
            continue
        produkt = db.eins("SELECT * FROM produkte WHERE id = ? AND katalog_id = ?", (p["produkt_id"], katalog_id))
        if produkt is None or not produkt["aktiv"]:
            raise AblaufFehler(400, "produkt_nicht_verfuegbar", produkt_id=p["produkt_id"])
        positionen.append((produkt, p["menge"]))
    summe = round(sum(pr["preis"] * m for pr, m in positionen), 2)
    felder = (katalog_id, ks, daten.get("anlass", ""), daten.get("datum"), daten.get("uhrzeit", ""),
              daten.get("ort", ""), daten.get("bemerkung", ""), summe)
    with db.transaktion():
        if anforderung_id is None:
            anforderung_id = db.ausfuehren(
                """INSERT INTO anforderungen (katalog_id, kostenstelle_id, anlass, datum, uhrzeit, ort, bemerkung, summe, antragsteller_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (*felder, ich["id"]))
        else:
            a = db.eins("SELECT antragsteller_id, status FROM anforderungen WHERE id = ?", (anforderung_id,))
            if a is None or a["antragsteller_id"] != ich["id"]:
                raise AblaufFehler(404, "nicht_gefunden")
            if a["status"] not in BEARBEITBAR:
                raise AblaufFehler(409, "nicht_bearbeitbar")
            db.ausfuehren("""UPDATE anforderungen SET katalog_id = ?, kostenstelle_id = ?, anlass = ?, datum = ?, uhrzeit = ?,
                             ort = ?, bemerkung = ?, summe = ? WHERE id = ?""", (*felder, anforderung_id))
            db.ausfuehren("DELETE FROM positionen WHERE anforderung_id = ?", (anforderung_id,))
        for produkt, menge in positionen:
            db.ausfuehren("INSERT INTO positionen (anforderung_id, produkt_id, name, einheit, preis, menge) VALUES (?, ?, ?, ?, ?, ?)",
                          (anforderung_id, produkt["id"], produkt["name"], produkt["einheit"], produkt["preis"], menge))
    return anforderung_id


def loeschen(db, ich: dict, anforderung_id: int) -> None:
    a = db.eins("SELECT antragsteller_id, status FROM anforderungen WHERE id = ?", (anforderung_id,))
    if a is None or a["antragsteller_id"] != ich["id"]:
        raise AblaufFehler(404, "nicht_gefunden")
    if a["status"] != "entwurf":
        raise AblaufFehler(409, "nicht_bearbeitbar")
    db.ausfuehren("DELETE FROM anforderungen WHERE id = ?", (anforderung_id,))


def _verlauf(db, anforderung_id: int, benutzer_id: int | None, aktion: str, notiz: str = "",
             im_namen_von: int | None = None, weiter_an: int | None = None, summe: float | None = None) -> None:
    db.ausfuehren("""INSERT INTO verlauf (anforderung_id, benutzer_id, im_namen_von, aktion, notiz, weiter_an, summe)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""", (anforderung_id, benutzer_id, im_namen_von, aktion, notiz, weiter_an, summe))


def uebermitteln(db, ich: dict, anforderung_id: int, notiz: str = "") -> dict:
    """Übermittelt einen Entwurf oder eine Anforderung nach Rückfrage. Die Kette beginnt von vorn."""
    a = db.eins("SELECT * FROM anforderungen WHERE id = ?", (anforderung_id,))
    if a is None or a["antragsteller_id"] != ich["id"]:
        raise AblaufFehler(404, "nicht_gefunden")
    if a["status"] not in BEARBEITBAR:
        raise AblaufFehler(409, "nicht_bearbeitbar")
    if a["katalog_id"] not in kataloge_fuer(db, ich["id"], "nutzer"):
        raise AblaufFehler(403, "katalog_nicht_erlaubt")
    fehlt = [f for f in ("anlass", "datum", "ort") if not (a[f] or "").strip()]
    if a["kostenstelle_id"] is None:
        fehlt.append("kostenstelle")
    if fehlt:
        raise AblaufFehler(400, "angaben_fehlen", felder=fehlt)
    with db.transaktion():
        # Preise beim Übermitteln festhalten
        summe = 0.0
        positionen = db.alle("SELECT * FROM positionen WHERE anforderung_id = ?", (anforderung_id,))
        if not positionen:
            raise AblaufFehler(400, "keine_positionen")
        for p in positionen:
            produkt = db.eins("SELECT * FROM produkte WHERE id = ? AND katalog_id = ?", (p["produkt_id"], a["katalog_id"]))
            if produkt is None or not produkt["aktiv"]:
                raise AblaufFehler(400, "produkt_nicht_verfuegbar", produkt_id=p["produkt_id"], name=p["name"])
            db.ausfuehren("UPDATE positionen SET name = ?, einheit = ?, preis = ? WHERE id = ?",
                          (produkt["name"], produkt["einheit"], produkt["preis"], p["id"]))
            summe += produkt["preis"] * p["menge"]
        summe = round(summe, 2)
        antragsteller = benutzer(db, ich["id"])
        erneut = a["status"] == "rueckfrage"
        if grenze_deckt(antragsteller["grenze"], summe):
            db.ausfuehren("""UPDATE anforderungen SET summe = ?, status = 'genehmigt', bearbeiter_id = NULL,
                             uebermittelt = datetime('now') WHERE id = ?""", (summe, anforderung_id))
            _verlauf(db, anforderung_id, ich["id"], "erneut_uebermittelt" if erneut else "uebermittelt", notiz, summe=summe)
            _verlauf(db, anforderung_id, ich["id"], "selbst_genehmigt")
            naechster = None
        else:
            naechster = _naechster(db, antragsteller)
            db.ausfuehren("""UPDATE anforderungen SET summe = ?, status = 'genehmigung', bearbeiter_id = ?,
                             uebermittelt = datetime('now') WHERE id = ?""", (summe, naechster["id"], anforderung_id))
            _verlauf(db, anforderung_id, ich["id"], "erneut_uebermittelt" if erneut else "uebermittelt", notiz,
                     weiter_an=naechster["id"], summe=summe)
    if naechster is None:
        _benachrichtigen_genehmigt(db, anforderung_id)
    else:
        _benachrichtigen_aufgabe(db, anforderung_id, naechster)
    return laden(db, anforderung_id)


def _naechster(db, person: dict) -> dict:
    """Vorgesetzter einer Person – mit Fehler, wenn die Kette hier endet."""
    if person["vorgesetzter_id"] is None:
        raise AblaufFehler(409, "kein_vorgesetzter", name=person["anzeigename"])
    v = benutzer(db, person["vorgesetzter_id"])
    if v is None or not v["aktiv"]:
        raise AblaufFehler(409, "vorgesetzter_inaktiv", name=person["anzeigename"])
    return v


def entscheiden(db, ich: dict, anforderung_id: int, aktion: str, notiz: str = "") -> dict:
    a = db.eins("SELECT * FROM anforderungen WHERE id = ?", (anforderung_id,))
    if a is None:
        raise AblaufFehler(404, "nicht_gefunden")
    recht = entscheider(db, a, ich)
    if recht is None:
        raise AblaufFehler(403, "nicht_zustaendig")
    notiz = (notiz or "").strip()
    if aktion in ("ablehnen", "rueckfrage") and not notiz:
        raise AblaufFehler(400, "notiz_fehlt")
    zustaendig = benutzer(db, a["bearbeiter_id"])  # in dessen Namen wird entschieden (bei Vertretung nicht ich)
    im_namen = recht["im_namen_von"]
    naechster = None
    with db.transaktion():
        if aktion == "ablehnen":
            db.ausfuehren("UPDATE anforderungen SET status = 'abgelehnt', bearbeiter_id = NULL, abgeschlossen = datetime('now') WHERE id = ?",
                          (anforderung_id,))
            _verlauf(db, anforderung_id, ich["id"], "abgelehnt", notiz, im_namen_von=im_namen)
        elif aktion == "rueckfrage":
            db.ausfuehren("UPDATE anforderungen SET status = 'rueckfrage', bearbeiter_id = NULL WHERE id = ?", (anforderung_id,))
            _verlauf(db, anforderung_id, ich["id"], "rueckfrage", notiz, im_namen_von=im_namen)
        elif aktion == "genehmigen":
            if grenze_deckt(zustaendig["grenze"], a["summe"]):
                db.ausfuehren("UPDATE anforderungen SET status = 'genehmigt', bearbeiter_id = NULL WHERE id = ?", (anforderung_id,))
                _verlauf(db, anforderung_id, ich["id"], "genehmigt", notiz, im_namen_von=im_namen)
            else:
                naechster = _naechster(db, zustaendig)
                db.ausfuehren("UPDATE anforderungen SET bearbeiter_id = ? WHERE id = ?", (naechster["id"], anforderung_id))
                _verlauf(db, anforderung_id, ich["id"], "befuerwortet", notiz, im_namen_von=im_namen, weiter_an=naechster["id"])
        else:
            raise AblaufFehler(400, "aktion_unbekannt")
    if aktion == "genehmigen" and naechster is not None:
        _benachrichtigen_aufgabe(db, anforderung_id, naechster)
    elif aktion == "genehmigen":
        _benachrichtigen_antragsteller(db, anforderung_id, "genehmigt", notiz)
        _benachrichtigen_genehmigt(db, anforderung_id)
    else:
        _benachrichtigen_antragsteller(db, anforderung_id, "abgelehnt" if aktion == "ablehnen" else "rueckfrage", notiz)
    return laden(db, anforderung_id)


def erledigen(db, ich: dict, anforderung_id: int, notiz: str = "") -> dict:
    a = db.eins("SELECT * FROM anforderungen WHERE id = ?", (anforderung_id,))
    if a is None:
        raise AblaufFehler(404, "nicht_gefunden")
    if a["katalog_id"] not in kataloge_fuer(db, ich["id"], "ausfuehrender"):
        raise AblaufFehler(403, "nicht_zustaendig")
    if a["status"] != "genehmigt":
        raise AblaufFehler(409, "nicht_genehmigt")
    with db.transaktion():
        db.ausfuehren("UPDATE anforderungen SET status = 'erledigt', abgeschlossen = datetime('now') WHERE id = ?", (anforderung_id,))
        _verlauf(db, anforderung_id, ich["id"], "erledigt", (notiz or "").strip())
    _benachrichtigen_antragsteller(db, anforderung_id, "erledigt", notiz)
    return laden(db, anforderung_id)


# --------------------------------------------------------------------------- Listen
def liste(db, ich: dict, ansicht: str, status: str | None = None) -> list[dict]:
    basis = """SELECT a.id, a.status, a.summe, a.anlass, a.datum, a.uhrzeit, a.ort, a.erstellt, a.uebermittelt,
                      k.name AS katalog, s.anzeigename AS antragsteller, g.anzeigename AS bearbeiter,
                      ks.nummer AS kostenstelle_nummer
                 FROM anforderungen a
                 JOIN kataloge k ON k.id = a.katalog_id
                 JOIN benutzer s ON s.id = a.antragsteller_id
                 LEFT JOIN kostenstellen ks ON ks.id = a.kostenstelle_id
                 LEFT JOIN benutzer g ON g.id = a.bearbeiter_id"""
    bedingungen, werte = [], []
    if ansicht == "meine":
        bedingungen.append("a.antragsteller_id = ?")
        werte.append(ich["id"])
    elif ansicht == "genehmigen":
        ids = [ich["id"], *vertretene(db, ich["id"])]
        bedingungen.append(f"a.status = 'genehmigung' AND a.bearbeiter_id IN ({','.join('?' * len(ids))})")
        werte += ids
    elif ansicht == "ausfuehren":
        kat = kataloge_fuer(db, ich["id"], "ausfuehrender")
        if not kat:
            return []
        bedingungen.append(f"a.katalog_id IN ({','.join('?' * len(kat))}) AND a.status IN ('genehmigt', 'erledigt')")
        werte += kat
    elif ansicht == "entschieden":
        bedingungen.append("a.id IN (SELECT anforderung_id FROM verlauf WHERE (benutzer_id = ? OR im_namen_von = ?) "
                           "AND aktion IN ('genehmigt', 'befuerwortet', 'abgelehnt', 'rueckfrage'))")
        werte += [ich["id"], ich["id"]]
    elif ansicht == "alle":
        if "verwalten" not in ich["rechte"]:
            raise AblaufFehler(403, "keine_berechtigung")
        bedingungen.append("a.status != 'entwurf'")
    else:
        raise AblaufFehler(400, "ansicht_unbekannt")
    if status:
        bedingungen.append("a.status = ?")
        werte.append(status)
    sql = basis + " WHERE " + " AND ".join(bedingungen) + " ORDER BY COALESCE(a.uebermittelt, a.erstellt) DESC, a.id DESC LIMIT 500"
    zeilen = db.alle(sql, tuple(werte))
    if ansicht == "genehmigen":
        for z in zeilen:
            z["vertretung"] = False
        vertreten = set(vertretene(db, ich["id"]))
        if vertreten:
            bearbeiter = {r["id"]: r["bearbeiter_id"] for r in db.alle(
                f"SELECT id, bearbeiter_id FROM anforderungen WHERE id IN ({','.join(str(z['id']) for z in zeilen) or '0'})")}
            for z in zeilen:
                z["vertretung"] = bearbeiter.get(z["id"]) in vertreten
    return zeilen


def offene_zahlen(db, ich: dict) -> dict:
    ids = [ich["id"], *vertretene(db, ich["id"])]
    genehmigen = db.eins(f"SELECT COUNT(*) AS n FROM anforderungen WHERE status = 'genehmigung' AND bearbeiter_id IN ({','.join('?' * len(ids))})",
                         tuple(ids))["n"]
    kat = kataloge_fuer(db, ich["id"], "ausfuehrender")
    ausfuehren = 0
    if kat:
        ausfuehren = db.eins(f"SELECT COUNT(*) AS n FROM anforderungen WHERE status = 'genehmigt' AND katalog_id IN ({','.join('?' * len(kat))})",
                             tuple(kat))["n"]
    rueckfragen = db.eins("SELECT COUNT(*) AS n FROM anforderungen WHERE status = 'rueckfrage' AND antragsteller_id = ?", (ich["id"],))["n"]
    return {"genehmigen": genehmigen, "ausfuehren": ausfuehren, "rueckfragen": rueckfragen}


# --------------------------------------------------------------------------- Statistik
def statistik(db, von: str | None, bis: str | None, benutzer_id: int | None, katalog_id: int | None,
              kostenstelle_id: int | None) -> dict:
    """Wer hat wie viel angefordert? Gezählt wird ab dem Übermitteln (Entwürfe nicht)."""
    bed, werte = ["a.uebermittelt IS NOT NULL", "a.status != 'entwurf'"], []
    if von:
        bed.append("date(a.uebermittelt) >= ?")
        werte.append(von)
    if bis:
        bed.append("date(a.uebermittelt) <= ?")
        werte.append(bis)
    for spalte, wert in (("antragsteller_id", benutzer_id), ("katalog_id", katalog_id), ("kostenstelle_id", kostenstelle_id)):
        if wert is not None:
            bed.append(f"a.{spalte} = ?")
            werte.append(wert)
    zeilen = db.alle(f"""
        SELECT s.id AS benutzer_id, s.anzeigename AS name,
               COUNT(*) AS anzahl, ROUND(SUM(a.summe), 2) AS summe,
               SUM(a.status IN ('genehmigt', 'erledigt')) AS anzahl_genehmigt,
               ROUND(SUM(CASE WHEN a.status IN ('genehmigt', 'erledigt') THEN a.summe ELSE 0 END), 2) AS summe_genehmigt,
               SUM(a.status = 'abgelehnt') AS anzahl_abgelehnt,
               ROUND(SUM(CASE WHEN a.status = 'abgelehnt' THEN a.summe ELSE 0 END), 2) AS summe_abgelehnt,
               SUM(a.status IN ('genehmigung', 'rueckfrage')) AS anzahl_offen,
               ROUND(SUM(CASE WHEN a.status IN ('genehmigung', 'rueckfrage') THEN a.summe ELSE 0 END), 2) AS summe_offen
          FROM anforderungen a JOIN benutzer s ON s.id = a.antragsteller_id
         WHERE {' AND '.join(bed)}
         GROUP BY s.id ORDER BY summe DESC, s.anzeigename""", tuple(werte))
    gesamt = {k: round(sum(z[k] or 0 for z in zeilen), 2) for k in
              ("anzahl", "summe", "anzahl_genehmigt", "summe_genehmigt", "anzahl_abgelehnt", "summe_abgelehnt", "anzahl_offen", "summe_offen")}
    return {"zeilen": zeilen, "gesamt": gesamt}


# --------------------------------------------------------------------------- E-Mails
def _ereignis_an(db, name: str) -> bool:
    return bool((db.einstellung("mail_ereignisse", {}) or {}).get(name, True))


def _link(db, anforderung_id: int) -> str:
    adresse = (db.einstellung("adresse", "") or "").rstrip("/")
    return f"{adresse}/#/anforderung/{anforderung_id}" if adresse else ""


def _zusammenfassung(a: dict) -> str:
    zeilen = [
        f"Anforderung Nr. {a['id']}: {a['anlass']}",
        f"Katalog: {a['katalog']}",
        f"Antragsteller: {a['antragsteller']}",
        f"Wann: {a['datum'] or '–'} {a['uhrzeit'] or ''}".rstrip(),
        f"Wo: {a['ort'] or '–'}",
        f"Kostenstelle: {a['kostenstelle_nummer'] or '–'} {a['kostenstelle_bezeichnung'] or ''}".rstrip(),
        "",
    ]
    for p in a["positionen"]:
        menge = f"{p['menge']:g}".replace(".", ",")
        zeilen.append(f"  {menge} {p['einheit']} {p['name']} à {betrag(p['preis'])} = {betrag(p['preis'] * p['menge'])}")
    zeilen.append(f"Summe: {betrag(a['summe'])}")
    if a["bemerkung"]:
        zeilen += ["", f"Bemerkung: {a['bemerkung']}"]
    return "\n".join(zeilen)


def _text(db, a: dict, einleitung: str, notiz: str = "") -> str:
    teile = [einleitung, ""]
    if notiz:
        teile += [f"Notiz: {notiz}", ""]
    teile.append(_zusammenfassung(a))
    link = _link(db, a["id"])
    if link:
        teile += ["", f"Zur Anforderung: {link}"]
    return "\n".join(teile)


def _benachrichtigen_aufgabe(db, anforderung_id: int, person: dict) -> None:
    if not _ereignis_an(db, "neue_aufgabe"):
        return
    a = laden(db, anforderung_id)
    betreff = f"Bitte genehmigen: Anforderung Nr. {a['id']} – {a['anlass']} ({betrag(a['summe'])})"
    mail.einreihen(db, person["email"], betreff, _text(db, a, f"Hallo {person['anzeigename']},\n\neine Anforderung wartet auf Ihre Entscheidung."))
    for v in vertreter_von(db, person["id"]):
        mail.einreihen(db, v["email"], betreff, _text(
            db, a, f"Hallo {v['anzeigename']},\n\neine Anforderung wartet auf die Entscheidung von {person['anzeigename']}. "
                   "Sie sind derzeit als Vertretung eingetragen."))


def _benachrichtigen_antragsteller(db, anforderung_id: int, was: str, notiz: str = "") -> None:
    if not _ereignis_an(db, "erledigt" if was == "erledigt" else "entscheidung"):
        return
    a = laden(db, anforderung_id)
    person = benutzer(db, a["antragsteller_id"])
    titel = {"genehmigt": "genehmigt", "abgelehnt": "abgelehnt", "rueckfrage": "Rückfrage", "erledigt": "erledigt"}[was]
    einleitung = {
        "genehmigt": "Ihre Anforderung wurde genehmigt.",
        "abgelehnt": "Ihre Anforderung wurde abgelehnt.",
        "rueckfrage": "Zu Ihrer Anforderung gibt es eine Rückfrage. Bitte ergänzen oder ändern Sie sie und übermitteln Sie sie erneut.",
        "erledigt": "Ihre Anforderung wurde ausgeführt und als erledigt gemeldet.",
    }[was]
    mail.einreihen(db, person["email"], f"Anforderung Nr. {a['id']} {titel}: {a['anlass']}",
                   _text(db, a, f"Hallo {person['anzeigename']},\n\n{einleitung}", (notiz or "").strip()))


def _benachrichtigen_genehmigt(db, anforderung_id: int) -> None:
    if not _ereignis_an(db, "genehmigt"):
        return
    a = laden(db, anforderung_id)
    katalog = db.eins("SELECT email FROM kataloge WHERE id = ?", (a["katalog_id"],))
    an = [katalog["email"], *[p["email"] for p in ausfuehrende(db, a["katalog_id"])]]
    mail.einreihen(db, an, f"Genehmigte Anforderung Nr. {a['id']}: {a['anlass']} am {a['datum'] or '–'}",
                   _text(db, a, "Guten Tag,\n\ndiese Anforderung ist genehmigt und kann ausgeführt werden. "
                                "Bitte melden Sie sie nach der Ausführung im Anforderungstool als erledigt."))
