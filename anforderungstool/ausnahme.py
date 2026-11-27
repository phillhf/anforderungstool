"""Ausnahmeanträge: Anträge für Dinge, die in keinem Katalog stehen.

Regeln (siehe KONZEPT.md, Teil 2):
- Weg: zuerst der direkte Vorgesetzte des Antragstellers, danach die Fachstellen in fester Reihenfolge.
  Fachstellen sind „immer“ beteiligt oder „bei Bedarf“ (vom Antragsteller angekreuzt). Der Betrag spielt keine Rolle.
- Die Stationen prüfen nacheinander. Jede kann freigeben, eine Rückfrage stellen, ablehnen oder eine weitere
  „bei Bedarf“-Stelle hinzuziehen. Nach einer Rückfrage geht es bei der fragenden Station weiter.
- Für eine Fachstelle entscheidet jedes Mitglied. Eine eingetragene Vertretung entscheidet im Namen des Vertretenen.
- Nach der letzten Freigabe führt die ausführende Fachstelle (meist der Einkauf) weiter: bestellt → geliefert → erledigt.
  Gibt es keine ausführende Fachstelle, übernehmen das die Admins.
- Sehen dürfen einen Antrag nur Beteiligte: Antragsteller, Stationen (samt Vertretung), Ausführende, Admins.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path

from . import mail
from .ablauf import AblaufFehler, benutzer, betrag, vertreter_von, vertretene, werktage_zwischen

STATUS = ("entwurf", "pruefung", "rueckfrage", "freigegeben", "bestellt", "geliefert", "erledigt", "abgelehnt")
BEARBEITBAR = ("entwurf", "rueckfrage")
AUSFUEHRUNG = ("freigegeben", "bestellt", "geliefert", "erledigt")  # in dieser Reihenfolge
ART = ("immer", "bedarf")

MAX_ANHANG = 20 * 1024 * 1024
ENDUNGEN = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".odt", ".ods", ".txt", ".csv",
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".msg", ".eml", ".zip"}


def nummer(aid: int) -> str:
    return f"AA-{aid:04d}"


def menge_text(menge: float) -> str:
    return f"{menge:g}".replace(".", ",")


# --------------------------------------------------------------------------- Fachstellen
def fachstellen(db, nur_aktive: bool = False) -> list[dict]:
    zeilen = db.alle(f"SELECT * FROM fachstellen {'WHERE aktiv = 1' if nur_aktive else ''} ORDER BY reihenfolge, id")
    mitglieder: dict[int, list[int]] = {}
    for r in db.alle("SELECT fachstelle_id, benutzer_id FROM fachstelle_mitglieder"):
        mitglieder.setdefault(r["fachstelle_id"], []).append(r["benutzer_id"])
    for z in zeilen:
        z["aktiv"] = bool(z["aktiv"])
        z["ausfuehrend"] = bool(z["ausfuehrend"])
        z["mitglieder"] = mitglieder.get(z["id"], [])
    return zeilen


def stellen_fuer(db, benutzer_id: int) -> dict[int, int | None]:
    """Für welche Fachstellen darf diese Person heute entscheiden? → {fachstelle_id: im_namen_von (None = selbst Mitglied)}"""
    ergebnis: dict[int, int | None] = {}
    for vertretener in vertretene(db, benutzer_id):
        for r in db.alle("SELECT fachstelle_id FROM fachstelle_mitglieder WHERE benutzer_id = ?", (vertretener,)):
            ergebnis.setdefault(r["fachstelle_id"], vertretener)
    for r in db.alle("SELECT fachstelle_id FROM fachstelle_mitglieder WHERE benutzer_id = ?", (benutzer_id,)):
        ergebnis[r["fachstelle_id"]] = None  # eigene Mitgliedschaft geht vor
    return ergebnis


def darf_ausfuehren(db, ich: dict) -> bool:
    ausfuehrende = [r["id"] for r in db.alle("SELECT id FROM fachstellen WHERE ausfuehrend = 1 AND aktiv = 1")]
    if not ausfuehrende:
        return "verwalten" in ich["rechte"]
    return any(f in ausfuehrende for f in stellen_fuer(db, ich["id"]))


def _stationsname(st: dict) -> str:
    return st["fachstelle"] if st["art"] == "fachstelle" else st["person"]


# --------------------------------------------------------------------------- Lesen
def stationen(db, aid: int) -> list[dict]:
    zeilen = db.alle("""
        SELECT s.id, s.pos, s.art, s.benutzer_id, s.fachstelle_id, s.status, s.entschieden_am,
               f.name AS fachstelle, b.anzeigename AS person, e.anzeigename AS entschieden_von,
               n.anzeigename AS im_namen_von, h.anzeigename AS hinzugefuegt_von
          FROM ausnahme_stationen s
          LEFT JOIN fachstellen f ON f.id = s.fachstelle_id
          LEFT JOIN benutzer b ON b.id = s.benutzer_id
          LEFT JOIN benutzer e ON e.id = s.entschieden_von
          LEFT JOIN benutzer n ON n.id = s.im_namen_von
          LEFT JOIN benutzer h ON h.id = s.hinzugefuegt_von
         WHERE s.ausnahme_id = ? ORDER BY s.pos, s.id""", (aid,))
    for z in zeilen:
        z["name"] = _stationsname(z)
    return zeilen


def aktuelle_station(db, aid: int) -> dict | None:
    return next((s for s in stationen(db, aid) if s["status"] == "offen"), None)


def laden(db, aid: int) -> dict:
    a = db.eins("""SELECT a.*, s.anzeigename AS antragsteller, ks.nummer AS kostenstelle_nummer, ks.bezeichnung AS kostenstelle_bezeichnung
                     FROM ausnahmen a JOIN benutzer s ON s.id = a.antragsteller_id
                     LEFT JOIN kostenstellen ks ON ks.id = a.kostenstelle_id WHERE a.id = ?""", (aid,))
    if a is None:
        raise AblaufFehler(404, "nicht_gefunden")
    a["auswahl"] = [r["fachstelle_id"] for r in db.alle("SELECT fachstelle_id FROM ausnahme_auswahl WHERE ausnahme_id = ?", (aid,))]
    a["stationen"] = stationen(db, aid)
    a["verlauf"] = db.alle("""SELECT v.id, v.zeit, v.aktion, v.notiz, v.station, v.weiter_an,
                                     b.anzeigename AS benutzer, n.anzeigename AS im_namen_von
                                FROM ausnahme_verlauf v
                                LEFT JOIN benutzer b ON b.id = v.benutzer_id
                                LEFT JOIN benutzer n ON n.id = v.im_namen_von
                               WHERE v.ausnahme_id = ? ORDER BY v.id""", (aid,))
    a["anhaenge"] = db.alle("""SELECT h.id, h.name, h.groesse, h.erstellt, h.benutzer_id, b.anzeigename AS benutzer
                                 FROM anhaenge h LEFT JOIN benutzer b ON b.id = h.benutzer_id
                                WHERE h.ausnahme_id = ? ORDER BY h.id""", (aid,))
    return a


def zustaendig(db, a: dict, ich: dict) -> dict | None:
    """Darf ich an der aktuellen Station entscheiden? → {"im_namen_von": id | None, "station": …} oder None."""
    if a["status"] != "pruefung":
        return None
    st = aktuelle_station(db, a["id"])
    if st is None:
        return None
    if st["art"] == "vorgesetzter":
        if st["benutzer_id"] == ich["id"]:
            return {"im_namen_von": None, "station": st}
        if st["benutzer_id"] in vertretene(db, ich["id"]):
            return {"im_namen_von": st["benutzer_id"], "station": st}
        return None
    stellen = stellen_fuer(db, ich["id"])
    if st["fachstelle_id"] in stellen:
        return {"im_namen_von": stellen[st["fachstelle_id"]], "station": st}
    return None


def darf_sehen(db, a: dict, ich: dict) -> bool:
    if "verwalten" in ich["rechte"] or a["antragsteller_id"] == ich["id"]:
        return True
    if a["status"] == "entwurf":
        return False
    ich_und_vertretene = {ich["id"], *vertretene(db, ich["id"])}
    stellen = stellen_fuer(db, ich["id"])
    for st in db.alle("SELECT art, benutzer_id, fachstelle_id FROM ausnahme_stationen WHERE ausnahme_id = ?", (a["id"],)):
        if st["art"] == "vorgesetzter" and st["benutzer_id"] in ich_und_vertretene:
            return True
        if st["art"] == "fachstelle" and st["fachstelle_id"] in stellen:
            return True
    if db.eins("SELECT 1 FROM ausnahme_verlauf WHERE ausnahme_id = ? AND (benutzer_id = ? OR im_namen_von = ?)", (a["id"], ich["id"], ich["id"])):
        return True
    return a["status"] in AUSFUEHRUNG and darf_ausfuehren(db, ich)


def moegliche_aktionen(db, a: dict, ich: dict) -> list[str]:
    aktionen = []
    eigen = a["antragsteller_id"] == ich["id"]
    if eigen and a["status"] in BEARBEITBAR:
        aktionen += ["bearbeiten", "uebermitteln"]
        if a["status"] == "entwurf":
            aktionen.append("loeschen")
    if zustaendig(db, a, ich):
        aktionen += ["freigeben", "rueckfrage", "ablehnen", "hinzuziehen"]
    if a["status"] in AUSFUEHRUNG[:-1] and darf_ausfuehren(db, ich):
        aktionen.append("status")
    if a["status"] != "entwurf":
        aktionen.append("notiz")
    if a["status"] not in ("erledigt", "abgelehnt") and (eigen and a["status"] in BEARBEITBAR or "freigeben" in aktionen or "status" in aktionen):
        aktionen.append("anhang")
    return aktionen


# --------------------------------------------------------------------------- Anlegen und Bearbeiten
FELDER = ("titel", "beschreibung", "bereich", "kostenstelle_id", "begruendung", "menge", "einzelpreis", "laufende_kosten",
          "lieferant", "wirtschaftlichkeit")


def speichern(db, ich: dict, daten: dict, aid: int | None = None) -> int:
    ks = daten.get("kostenstelle_id")
    if ks is not None and not db.eins("SELECT 1 FROM kostenstellen WHERE id = ? AND aktiv = 1", (ks,)):
        raise AblaufFehler(400, "kostenstelle_unbekannt")
    bedarf = {r["id"] for r in db.alle("SELECT id FROM fachstellen WHERE art = 'bedarf' AND aktiv = 1")}
    auswahl = sorted(set(daten.get("fachstellen", [])))
    if any(f not in bedarf for f in auswahl):
        raise AblaufFehler(400, "fachstelle_unbekannt")
    werte = {k: daten.get(k) for k in FELDER}
    werte["summe"] = round((werte["menge"] or 0) * (werte["einzelpreis"] or 0), 2)
    spalten = list(werte)
    with db.transaktion():
        if aid is None:
            aid = db.ausfuehren(f"INSERT INTO ausnahmen ({', '.join(spalten)}, antragsteller_id) VALUES ({', '.join('?' * (len(spalten) + 1))})",
                                (*werte.values(), ich["id"]))
        else:
            a = db.eins("SELECT antragsteller_id, status FROM ausnahmen WHERE id = ?", (aid,))
            if a is None or a["antragsteller_id"] != ich["id"]:
                raise AblaufFehler(404, "nicht_gefunden")
            if a["status"] not in BEARBEITBAR:
                raise AblaufFehler(409, "nicht_bearbeitbar")
            db.ausfuehren(f"UPDATE ausnahmen SET {', '.join(f'{k} = ?' for k in spalten)} WHERE id = ?", (*werte.values(), aid))
            db.ausfuehren("DELETE FROM ausnahme_auswahl WHERE ausnahme_id = ?", (aid,))
        for f in auswahl:
            db.ausfuehren("INSERT INTO ausnahme_auswahl (ausnahme_id, fachstelle_id) VALUES (?, ?)", (aid, f))
    return aid


def loeschen(db, pfade, ich: dict, aid: int) -> None:
    a = db.eins("SELECT antragsteller_id, status FROM ausnahmen WHERE id = ?", (aid,))
    if a is None or a["antragsteller_id"] != ich["id"]:
        raise AblaufFehler(404, "nicht_gefunden")
    if a["status"] != "entwurf":
        raise AblaufFehler(409, "nicht_bearbeitbar")
    dateien = [r["datei"] for r in db.alle("SELECT datei FROM anhaenge WHERE ausnahme_id = ?", (aid,))]
    db.ausfuehren("DELETE FROM ausnahmen WHERE id = ?", (aid,))
    for d in dateien:
        (pfade.anhaenge / d).unlink(missing_ok=True)


def _verlauf(db, aid: int, benutzer_id: int | None, aktion: str, notiz: str = "", im_namen_von: int | None = None,
             station: str = "", weiter_an: str = "") -> None:
    db.ausfuehren("""INSERT INTO ausnahme_verlauf (ausnahme_id, benutzer_id, im_namen_von, aktion, notiz, station, weiter_an)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""", (aid, benutzer_id, im_namen_von, aktion, notiz, station, weiter_an))


def _neu_nummerieren(db, ids: list[int]) -> None:
    for pos, sid in enumerate(ids, start=1):
        db.ausfuehren("UPDATE ausnahme_stationen SET pos = ? WHERE id = ?", (pos, sid))


def _einfuegen(db, aid: int, fachstelle_id: int, mindestens: int, von: int | None) -> None:
    """Fügt eine Fachstelle an ihrer Stelle in der Reihenfolge ein – aber nicht vor Index „mindestens“ (schon geprüft)."""
    rf = {r["id"]: r["reihenfolge"] for r in db.alle("SELECT id, reihenfolge FROM fachstellen")}
    liste = stationen(db, aid)
    natuerlich = sum(1 for s in liste if s["art"] == "vorgesetzter" or rf.get(s["fachstelle_id"], 0) <= rf[fachstelle_id])
    index = max(natuerlich, mindestens)
    neu = db.ausfuehren("INSERT INTO ausnahme_stationen (ausnahme_id, pos, art, fachstelle_id, hinzugefuegt_von) VALUES (?, 0, 'fachstelle', ?, ?)",
                        (aid, fachstelle_id, von))
    ids = [s["id"] for s in liste]
    ids.insert(index, neu)
    _neu_nummerieren(db, ids)


def weg_planen(db, antragsteller_id: int, auswahl: list[int]) -> list[dict]:
    """Die Stationen eines neuen Antrags: Vorgesetzter, dann alle „immer“-Stellen und die angekreuzten „bei Bedarf“-Stellen."""
    weg = []
    person = benutzer(db, antragsteller_id)
    if person["vorgesetzter_id"] is not None:
        v = benutzer(db, person["vorgesetzter_id"])
        if v is None or not v["aktiv"]:
            raise AblaufFehler(409, "vorgesetzter_inaktiv", name=person["anzeigename"])
        weg.append({"art": "vorgesetzter", "benutzer_id": v["id"], "fachstelle_id": None})
    for f in fachstellen(db, nur_aktive=True):
        if f["art"] == "immer" or f["id"] in auswahl:
            weg.append({"art": "fachstelle", "benutzer_id": None, "fachstelle_id": f["id"]})
    return weg


def uebermitteln(db, ich: dict, aid: int, notiz: str = "") -> dict:
    a = db.eins("SELECT * FROM ausnahmen WHERE id = ?", (aid,))
    if a is None or a["antragsteller_id"] != ich["id"]:
        raise AblaufFehler(404, "nicht_gefunden")
    if a["status"] not in BEARBEITBAR:
        raise AblaufFehler(409, "nicht_bearbeitbar")
    fehlt = [f for f in ("titel", "begruendung") if not (a[f] or "").strip()]
    if a["kostenstelle_id"] is None:
        fehlt.append("kostenstelle")
    if not a["menge"] or a["menge"] <= 0 or not a["einzelpreis"] or a["einzelpreis"] <= 0:
        fehlt.append("kosten")
    if fehlt:
        raise AblaufFehler(400, "ausnahme_angaben_fehlen", felder=fehlt)
    auswahl = [r["fachstelle_id"] for r in db.alle("SELECT fachstelle_id FROM ausnahme_auswahl WHERE ausnahme_id = ?", (aid,))]
    with db.transaktion():
        if a["status"] == "entwurf":
            weg = weg_planen(db, ich["id"], auswahl)
            if not weg:
                raise AblaufFehler(409, "kein_weg")
            for pos, st in enumerate(weg, start=1):
                db.ausfuehren("INSERT INTO ausnahme_stationen (ausnahme_id, pos, art, benutzer_id, fachstelle_id) VALUES (?, ?, ?, ?, ?)",
                              (aid, pos, st["art"], st["benutzer_id"], st["fachstelle_id"]))
            aktion = "uebermittelt"
        else:
            # nach einer Rückfrage: geänderte Häkchen übernehmen, es geht bei der fragenden Station weiter
            liste = stationen(db, aid)
            aktuell = next(i for i, s in enumerate(liste) if s["status"] == "offen")
            bedarf = {r["id"] for r in db.alle("SELECT id FROM fachstellen WHERE art = 'bedarf'")}
            for s in liste:
                if (s["status"] == "offen" and s["art"] == "fachstelle" and s["fachstelle_id"] in bedarf
                        and s["fachstelle_id"] not in auswahl and s["hinzugefuegt_von"] is None):
                    db.ausfuehren("DELETE FROM ausnahme_stationen WHERE id = ?", (s["id"],))
            vorhanden = {s["fachstelle_id"] for s in stationen(db, aid)}
            for f in auswahl:
                if f not in vorhanden and db.eins("SELECT 1 FROM fachstellen WHERE id = ? AND aktiv = 1", (f,)):
                    _einfuegen(db, aid, f, aktuell, None)
            _neu_nummerieren(db, [s["id"] for s in stationen(db, aid)])
            if aktuelle_station(db, aid) is None:
                raise AblaufFehler(409, "kein_weg")
            aktion = "erneut_uebermittelt"
        db.ausfuehren("UPDATE ausnahmen SET status = 'pruefung', uebermittelt = COALESCE(uebermittelt, datetime('now')) WHERE id = ?", (aid,))
        st = aktuelle_station(db, aid)
        _verlauf(db, aid, ich["id"], aktion, (notiz or "").strip(), weiter_an=st["name"])
    _benachrichtigen_station(db, aid)
    return laden(db, aid)


# --------------------------------------------------------------------------- Entscheiden
def entscheiden(db, ich: dict, aid: int, aktion: str, notiz: str = "") -> dict:
    a = db.eins("SELECT * FROM ausnahmen WHERE id = ?", (aid,))
    if a is None:
        raise AblaufFehler(404, "nicht_gefunden")
    recht = zustaendig(db, a, ich)
    if recht is None:
        raise AblaufFehler(403, "nicht_zustaendig")
    notiz = (notiz or "").strip()
    if aktion in ("ablehnen", "rueckfrage") and not notiz:
        raise AblaufFehler(400, "notiz_fehlt")
    st, im_namen = recht["station"], recht["im_namen_von"]
    naechste = None
    with db.transaktion():
        if aktion == "freigeben":
            db.ausfuehren("""UPDATE ausnahme_stationen SET status = 'freigegeben', entschieden_von = ?, im_namen_von = ?,
                             entschieden_am = datetime('now') WHERE id = ?""", (ich["id"], im_namen, st["id"]))
            naechste = aktuelle_station(db, aid)
            if naechste is None:
                db.ausfuehren("UPDATE ausnahmen SET status = 'freigegeben' WHERE id = ?", (aid,))
            _verlauf(db, aid, ich["id"], "freigegeben", notiz, im_namen, st["name"], naechste["name"] if naechste else "")
            if naechste is None:
                _verlauf(db, aid, None, "endgueltig_freigegeben")
        elif aktion == "rueckfrage":
            db.ausfuehren("UPDATE ausnahmen SET status = 'rueckfrage' WHERE id = ?", (aid,))
            _verlauf(db, aid, ich["id"], "rueckfrage", notiz, im_namen, st["name"])
        elif aktion == "ablehnen":
            db.ausfuehren("UPDATE ausnahmen SET status = 'abgelehnt', abgeschlossen = datetime('now') WHERE id = ?", (aid,))
            _verlauf(db, aid, ich["id"], "abgelehnt", notiz, im_namen, st["name"])
        else:
            raise AblaufFehler(400, "aktion_unbekannt")
    if aktion == "freigeben" and naechste is not None:
        _benachrichtigen_station(db, aid)
    elif aktion == "freigeben":
        _benachrichtigen_antragsteller(db, aid, "freigegeben", notiz)
        _benachrichtigen_ausfuehrende(db, aid)
    else:
        _benachrichtigen_antragsteller(db, aid, "abgelehnt" if aktion == "ablehnen" else "rueckfrage", notiz)
    return laden(db, aid)


def hinzuziehen(db, ich: dict, aid: int, fachstelle_id: int, notiz: str = "") -> dict:
    a = db.eins("SELECT * FROM ausnahmen WHERE id = ?", (aid,))
    if a is None:
        raise AblaufFehler(404, "nicht_gefunden")
    recht = zustaendig(db, a, ich)
    if recht is None:
        raise AblaufFehler(403, "nicht_zustaendig")
    f = db.eins("SELECT * FROM fachstellen WHERE id = ? AND aktiv = 1", (fachstelle_id,))
    if f is None:
        raise AblaufFehler(400, "fachstelle_unbekannt")
    liste = stationen(db, aid)
    if any(s["fachstelle_id"] == fachstelle_id for s in liste):
        raise AblaufFehler(409, "fachstelle_schon_dabei")
    aktuell = next(i for i, s in enumerate(liste) if s["status"] == "offen")
    with db.transaktion():
        _einfuegen(db, aid, fachstelle_id, aktuell + 1, ich["id"])  # frühestens direkt nach der jetzigen Station
        _verlauf(db, aid, ich["id"], "hinzugezogen", (notiz or "").strip(), recht["im_namen_von"], recht["station"]["name"], f["name"])
    return laden(db, aid)


def status_setzen(db, ich: dict, aid: int, neu: str, notiz: str = "") -> dict:
    a = db.eins("SELECT * FROM ausnahmen WHERE id = ?", (aid,))
    if a is None:
        raise AblaufFehler(404, "nicht_gefunden")
    if not darf_ausfuehren(db, ich):
        raise AblaufFehler(403, "nicht_zustaendig")
    if a["status"] not in AUSFUEHRUNG or neu not in AUSFUEHRUNG or AUSFUEHRUNG.index(neu) <= AUSFUEHRUNG.index(a["status"]):
        raise AblaufFehler(409, "status_nicht_moeglich")
    with db.transaktion():
        db.ausfuehren(f"UPDATE ausnahmen SET status = ?{', abgeschlossen = datetime(?)' if neu == 'erledigt' else ''} WHERE id = ?",
                      (neu, "now", aid) if neu == "erledigt" else (neu, aid))
        _verlauf(db, aid, ich["id"], neu, (notiz or "").strip())
    _benachrichtigen_antragsteller(db, aid, neu, notiz)
    return laden(db, aid)


def notiz_hinzufuegen(db, ich: dict, aid: int, notiz: str) -> dict:
    notiz = (notiz or "").strip()
    if not notiz:
        raise AblaufFehler(400, "notiz_fehlt")
    _verlauf(db, aid, ich["id"], "notiz", notiz)
    return laden(db, aid)


# --------------------------------------------------------------------------- Anhänge
def anhang_speichern(db, pfade, ich: dict, a: dict, name: str, inhalt: bytes) -> dict:
    if "anhang" not in moegliche_aktionen(db, a, ich):
        raise AblaufFehler(403, "keine_berechtigung")
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", Path(name or "").name).strip()[:150]
    endung = Path(name).suffix.lower()
    if not name or endung not in ENDUNGEN:
        raise AblaufFehler(400, "anhang_typ", erlaubt=", ".join(sorted(e.lstrip(".") for e in ENDUNGEN)))
    if not inhalt:
        raise AblaufFehler(400, "anhang_leer")
    if len(inhalt) > MAX_ANHANG:
        raise AblaufFehler(413, "anhang_zu_gross", mb=MAX_ANHANG // (1024 * 1024))
    datei = f"{a['id']}/{uuid.uuid4().hex}{endung}"
    ziel = pfade.anhaenge / datei
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(inhalt)
    hid = db.ausfuehren("INSERT INTO anhaenge (ausnahme_id, name, datei, groesse, benutzer_id) VALUES (?, ?, ?, ?, ?)",
                        (a["id"], name, datei, len(inhalt), ich["id"]))
    if a["status"] != "entwurf":
        _verlauf(db, a["id"], ich["id"], "anhang", name)
    return {"id": hid, "name": name}


def anhang(db, anhang_id: int) -> dict:
    h = db.eins("SELECT * FROM anhaenge WHERE id = ?", (anhang_id,))
    if h is None:
        raise AblaufFehler(404, "nicht_gefunden")
    return h


def anhang_loeschen(db, pfade, ich: dict, h: dict) -> None:
    a = db.eins("SELECT * FROM ausnahmen WHERE id = ?", (h["ausnahme_id"],))
    eigener = h["benutzer_id"] == ich["id"] and a["status"] not in ("erledigt", "abgelehnt")
    if not eigener and "verwalten" not in ich["rechte"]:
        raise AblaufFehler(403, "keine_berechtigung")
    # Nach dem Übermitteln bleiben Anhänge des Antragstellers stehen (andere haben sie womöglich schon geprüft) – außer bei Rückfrage
    if h["benutzer_id"] == a["antragsteller_id"] and a["status"] not in BEARBEITBAR and "verwalten" not in ich["rechte"]:
        raise AblaufFehler(409, "nicht_bearbeitbar")
    db.ausfuehren("DELETE FROM anhaenge WHERE id = ?", (h["id"],))
    (pfade.anhaenge / h["datei"]).unlink(missing_ok=True)
    if a["status"] != "entwurf":
        _verlauf(db, a["id"], ich["id"], "anhang_entfernt", h["name"])


# --------------------------------------------------------------------------- Listen
_BASIS = """SELECT a.id, a.titel, a.status, a.summe, a.bereich, a.erstellt, a.uebermittelt, a.antragsteller_id,
                   s.anzeigename AS antragsteller, ks.nummer AS kostenstelle_nummer,
                   COALESCE((SELECT MAX(v.zeit) FROM ausnahme_verlauf v WHERE v.ausnahme_id = a.id), a.erstellt) AS seit,
                   st.art AS station_art, st.benutzer_id AS station_benutzer, st.fachstelle_id AS station_fachstelle,
                   COALESCE(f.name, sb.anzeigename) AS station
              FROM ausnahmen a
              JOIN benutzer s ON s.id = a.antragsteller_id
              LEFT JOIN kostenstellen ks ON ks.id = a.kostenstelle_id
              LEFT JOIN ausnahme_stationen st ON st.id = (SELECT x.id FROM ausnahme_stationen x WHERE x.ausnahme_id = a.id
                                                           AND x.status = 'offen' ORDER BY x.pos LIMIT 1)
              LEFT JOIN fachstellen f ON f.id = st.fachstelle_id
              LEFT JOIN benutzer sb ON sb.id = st.benutzer_id"""


def _in(werte) -> str:
    return ",".join("?" * len(werte)) or "NULL"


def liste(db, ich: dict, ansicht: str, status: str | None = None) -> list[dict]:
    bed, werte = [], []
    stellen: dict[int, int | None] = {}
    vertreten: list[int] = []
    if ansicht == "meine":
        bed.append("a.antragsteller_id = ?")
        werte.append(ich["id"])
    elif ansicht == "pruefen":
        vertreten = vertretene(db, ich["id"])
        personen = [ich["id"], *vertreten]
        stellen = stellen_fuer(db, ich["id"])
        bed.append(f"""a.status = 'pruefung' AND ((st.art = 'vorgesetzter' AND st.benutzer_id IN ({_in(personen)}))
                       OR (st.art = 'fachstelle' AND st.fachstelle_id IN ({_in(stellen)})))""")
        werte += [*personen, *stellen]
    elif ansicht == "ausfuehren":
        if not darf_ausfuehren(db, ich):
            return []
        bed.append("a.status IN ('freigegeben', 'bestellt', 'geliefert', 'erledigt')")
        if not status:
            bed.append("a.status != 'erledigt'")
    elif ansicht == "entschieden":
        bed.append("""a.id IN (SELECT ausnahme_id FROM ausnahme_verlauf WHERE (benutzer_id = ? OR im_namen_von = ?)
                       AND aktion IN ('freigegeben', 'rueckfrage', 'abgelehnt', 'hinzugezogen'))""")
        werte += [ich["id"], ich["id"]]
    elif ansicht == "alle":
        if "verwalten" not in ich["rechte"]:
            raise AblaufFehler(403, "keine_berechtigung")
        bed.append("a.status != 'entwurf'")
    else:
        raise AblaufFehler(400, "ansicht_unbekannt")
    if status:
        if status not in STATUS:
            raise AblaufFehler(400, "status_unbekannt")
        bed.append("a.status = ?")
        werte.append(status)
    reihenfolge = "seit, a.id" if ansicht in ("pruefen", "ausfuehren") else "COALESCE(a.uebermittelt, a.erstellt) DESC, a.id DESC"
    zeilen = db.alle(f"{_BASIS} WHERE {' AND '.join(bed)} ORDER BY {reihenfolge} LIMIT 500", tuple(werte))
    if ansicht == "pruefen":
        namen = {}
        for z in zeilen:
            fuer = z["station_benutzer"] if z["station_art"] == "vorgesetzter" and z["station_benutzer"] != ich["id"] else \
                stellen.get(z["station_fachstelle"]) if z["station_art"] == "fachstelle" else None
            if fuer and fuer not in namen:
                namen[fuer] = benutzer(db, fuer)["anzeigename"]
            z["vertretung_fuer"] = namen.get(fuer) if fuer else None
    return zeilen


def offene_zahlen(db, ich: dict) -> dict:
    return {
        "pruefen": len(liste(db, ich, "pruefen")),
        "rueckfragen": db.eins("SELECT COUNT(*) AS n FROM ausnahmen WHERE status = 'rueckfrage' AND antragsteller_id = ?", (ich["id"],))["n"],
        "bestellen": db.eins("SELECT COUNT(*) AS n FROM ausnahmen WHERE status = 'freigegeben'")["n"] if darf_ausfuehren(db, ich) else 0,
    }


def aufgaben(db, ich: dict) -> dict:
    rueckfragen = db.alle("""
        SELECT a.id, a.titel, a.summe, v.notiz, v.station, b.anzeigename AS von, n.anzeigename AS im_namen_von, v.zeit AS seit
          FROM ausnahmen a
          LEFT JOIN ausnahme_verlauf v ON v.id = (SELECT MAX(id) FROM ausnahme_verlauf WHERE ausnahme_id = a.id AND aktion = 'rueckfrage')
          LEFT JOIN benutzer b ON b.id = v.benutzer_id
          LEFT JOIN benutzer n ON n.id = v.im_namen_von
         WHERE a.status = 'rueckfrage' AND a.antragsteller_id = ? ORDER BY v.zeit""", (ich["id"],))
    eigene = liste(db, ich, "meine")
    return {
        "rueckfragen": rueckfragen,
        "pruefen": liste(db, ich, "pruefen"),
        "bestellen": [z for z in liste(db, ich, "ausfuehren") if z["status"] == "freigegeben"],
        "entwuerfe": [z for z in eigene if z["status"] == "entwurf"],
        "laufend": [z for z in eigene if z["status"] in ("pruefung", "freigegeben", "bestellt", "geliefert")],
    }


# --------------------------------------------------------------------------- E-Mails
def _ereignis_an(db, name: str) -> bool:
    return bool((db.einstellung("mail_ereignisse", {}) or {}).get(name, True))


def _text(db, a: dict, einleitung: str, notiz: str = "") -> str:
    teile = [einleitung, ""]
    if notiz:
        teile += [f"Notiz: {notiz}", ""]
    teile += [
        f"Ausnahmeantrag {nummer(a['id'])}: {a['titel']}",
        f"Antragsteller: {a['antragsteller']}",
        f"Bereich: {a['bereich'] or '–'}",
        f"Kostenstelle: {a['kostenstelle_nummer'] or '–'} {a['kostenstelle_bezeichnung'] or ''}".rstrip(),
        f"Kosten: {menge_text(a['menge'])} × {betrag(a['einzelpreis'])} = {betrag(a['summe'])}",
    ]
    if a["laufende_kosten"]:
        teile.append(f"Laufende Kosten pro Jahr: {betrag(a['laufende_kosten'])}")
    teile += ["", "Begründung:", a["begruendung"] or "–"]
    weg = " → ".join(("✓ " if s["status"] == "freigegeben" else "") + s["name"] for s in a["stationen"])
    if weg:
        teile += ["", f"Weg: {weg}"]
    adresse = (db.einstellung("adresse", "") or "").rstrip("/")
    if adresse:
        teile += ["", f"Zum Antrag: {adresse}/#/ausnahme/{a['id']}"]
    return "\n".join(teile)


def _station_empfaenger(db, st: dict) -> list[tuple[str, str]]:
    """(E-Mail, Name) aller, die an dieser Station entscheiden dürfen, samt heutiger Vertretung."""
    personen = [st["benutzer_id"]] if st["art"] == "vorgesetzter" else \
        [r["benutzer_id"] for r in db.alle("SELECT benutzer_id FROM fachstelle_mitglieder WHERE fachstelle_id = ?", (st["fachstelle_id"],))]
    empfaenger = []
    for pid in personen:
        p = benutzer(db, pid)
        if p and p["aktiv"]:
            empfaenger.append((p["email"], p["anzeigename"]))
        empfaenger += [(v["email"], v["anzeigename"]) for v in vertreter_von(db, pid)]
    if st["art"] == "fachstelle":
        f = db.eins("SELECT email FROM fachstellen WHERE id = ?", (st["fachstelle_id"],))
        if f and f["email"]:
            empfaenger.append((f["email"], ""))
    return empfaenger


def _benachrichtigen_station(db, aid: int, erinnerung_tage: int | None = None) -> None:
    if not _ereignis_an(db, "neue_aufgabe") and erinnerung_tage is None:
        return
    a = laden(db, aid)
    st = next((s for s in a["stationen"] if s["status"] == "offen"), None)
    if st is None:
        return
    an = [e for e, _ in _station_empfaenger(db, st)]
    if erinnerung_tage is None:
        betreff = f"Bitte prüfen: Ausnahmeantrag {nummer(aid)} – {a['titel']}"
        einleitung = f"Guten Tag,\n\nein Ausnahmeantrag wartet auf die Prüfung durch: {st['name']}."
    else:
        betreff = f"Erinnerung: Ausnahmeantrag {nummer(aid)} wartet auf Prüfung – {a['titel']}"
        einleitung = f"Guten Tag,\n\ndieser Ausnahmeantrag wartet seit {erinnerung_tage} Werktagen auf die Prüfung durch: {st['name']}."
    mail.einreihen(db, an, betreff, _text(db, a, einleitung))


def _benachrichtigen_antragsteller(db, aid: int, was: str, notiz: str = "") -> None:
    if not _ereignis_an(db, "erledigt" if was in ("bestellt", "geliefert", "erledigt") else "entscheidung"):
        return
    a = laden(db, aid)
    person = benutzer(db, a["antragsteller_id"])
    einleitung = {
        "freigegeben": "Ihr Ausnahmeantrag ist von allen Stellen freigegeben.",
        "abgelehnt": "Ihr Ausnahmeantrag wurde abgelehnt.",
        "rueckfrage": "Zu Ihrem Ausnahmeantrag gibt es eine Rückfrage. Bitte ändern oder ergänzen Sie ihn und übermitteln Sie ihn erneut.",
        "bestellt": "Ihr Ausnahmeantrag wurde bestellt.",
        "geliefert": "Ihr Ausnahmeantrag wurde geliefert.",
        "erledigt": "Ihr Ausnahmeantrag ist erledigt.",
    }[was]
    titel = {"freigegeben": "freigegeben", "abgelehnt": "abgelehnt", "rueckfrage": "Rückfrage", "bestellt": "bestellt",
             "geliefert": "geliefert", "erledigt": "erledigt"}[was]
    mail.einreihen(db, person["email"], f"Ausnahmeantrag {nummer(aid)} {titel}: {a['titel']}",
                   _text(db, a, f"Hallo {person['anzeigename']},\n\n{einleitung}", (notiz or "").strip()))


def _benachrichtigen_ausfuehrende(db, aid: int) -> None:
    if not _ereignis_an(db, "genehmigt"):
        return
    a = laden(db, aid)
    an = []
    for f in db.alle("SELECT id, email FROM fachstellen WHERE ausfuehrend = 1 AND aktiv = 1"):
        an.append(f["email"])
        an += [b["email"] for b in db.alle("""SELECT b.email FROM fachstelle_mitglieder m JOIN benutzer b ON b.id = m.benutzer_id
                                              WHERE m.fachstelle_id = ? AND b.aktiv = 1""", (f["id"],))]
    mail.einreihen(db, an, f"Freigegebener Ausnahmeantrag {nummer(aid)}: {a['titel']}",
                   _text(db, a, "Guten Tag,\n\ndieser Ausnahmeantrag ist von allen Stellen freigegeben und kann bestellt werden. "
                                "Bitte melden Sie im Anforderungstool „bestellt“, „geliefert“ und „erledigt“."))


def erinnern(db, heute_: date | None = None) -> int:
    """Erinnerungen wie bei den Katalog-Anforderungen (Einstellung erinnerung_tage, nur werktags)."""
    from .ablauf import STANDARD_ERINNERUNG_TAGE

    tage = int(db.einstellung("erinnerung_tage", STANDARD_ERINNERUNG_TAGE) or 0)
    heute_ = heute_ or date.today()
    if tage <= 0 or heute_.weekday() >= 5:
        return 0
    anzahl = 0
    for r in db.alle("""SELECT a.id, a.status, a.antragsteller_id, a.erinnert,
                               (SELECT MAX(zeit) FROM ausnahme_verlauf v WHERE v.ausnahme_id = a.id) AS seit
                          FROM ausnahmen a WHERE a.status IN ('pruefung', 'rueckfrage')"""):
        if not r["seit"]:
            continue
        bezug = max(r["seit"], r["erinnert"] or "")
        if werktage_zwischen(date.fromisoformat(bezug[:10]), heute_) < tage:
            continue
        seit_tagen = werktage_zwischen(date.fromisoformat(r["seit"][:10]), heute_)
        if r["status"] == "pruefung":
            _benachrichtigen_station(db, r["id"], seit_tagen)
        else:
            a = laden(db, r["id"])
            person = benutzer(db, r["antragsteller_id"])
            mail.einreihen(db, person["email"], f"Erinnerung: Rückfrage zu Ihrem Ausnahmeantrag {nummer(r['id'])} – {a['titel']}", _text(
                db, a, f"Hallo {person['anzeigename']},\n\nzu Ihrem Ausnahmeantrag gibt es seit {seit_tagen} Werktagen eine Rückfrage. "
                       "Bitte ändern oder ergänzen Sie ihn und übermitteln Sie ihn erneut."))
        db.ausfuehren("UPDATE ausnahmen SET erinnert = datetime('now') WHERE id = ?", (r["id"],))
        anzahl += 1
    return anzahl
