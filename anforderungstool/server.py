"""Webserver: Oberfläche und JSON-Schnittstelle.

Fehler gibt die Schnittstelle als {"detail": {"code": "...", ...}} zurück; die Oberfläche
übersetzt den Code (fehler.<code> in static/i18n/de.json).
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from . import APP_NAME, __version__, ablauf, auth, mail, verzeichnis, wartung
from .config import Pfade, static_ordner
from .db import KATALOG_ROLLEN, RECHTE, Datenbank

log = logging.getLogger(__name__)


def fehler(status: int, code: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, **extra})


# --------------------------------------------------------------------------- Modelle
class Ersteinrichtung(BaseModel):
    benutzername: str = Field(min_length=1, max_length=64)
    anzeigename: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=200)
    passwort: str


class Anmeldung(BaseModel):
    benutzername: str
    passwort: str


class PasswortAendern(BaseModel):
    altes_passwort: str
    neues_passwort: str


class BenutzerDaten(BaseModel):
    benutzername: str = Field(min_length=1, max_length=64)
    anzeigename: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=200)
    quelle: str = "lokal"
    passwort: str | None = None  # nur lokale Konten; leer = unverändert
    aktiv: bool = True
    rechte: list[str] = []
    vorgesetzter_id: int | None = None
    grenze: float | None = Field(default=0, ge=0)  # None = unbegrenzt
    kostenstelle_id: int | None = None
    kataloge: list[int] = []  # Kataloge, aus denen die Person anfordern darf


class Position(BaseModel):
    produkt_id: int
    menge: float = Field(ge=0, le=1_000_000)


class AnforderungDaten(BaseModel):
    katalog_id: int
    kostenstelle_id: int | None = None
    anlass: str = Field(default="", max_length=200)
    datum: date | None = None
    uhrzeit: str = Field(default="", max_length=20)
    ort: str = Field(default="", max_length=200)
    bemerkung: str = Field(default="", max_length=2000)
    positionen: list[Position] = []


class Notiz(BaseModel):
    notiz: str = Field(default="", max_length=2000)


class Entscheidung(BaseModel):
    aktion: str
    notiz: str = Field(default="", max_length=2000)


class KatalogDaten(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    beschreibung: str = Field(default="", max_length=1000)
    email: str = Field(default="", max_length=500)
    aktiv: bool = True


class Zuordnung(BaseModel):
    nutzer: list[int] = []
    pfleger: list[int] = []
    ausfuehrender: list[int] = []


class ProduktDaten(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    beschreibung: str = Field(default="", max_length=1000)
    einheit: str = Field(default="Stück", max_length=40)
    preis: float = Field(ge=0, le=1_000_000)
    aktiv: bool = True
    reihenfolge: int = 0


class KostenstelleDaten(BaseModel):
    nummer: str = Field(min_length=1, max_length=40)
    bezeichnung: str = Field(default="", max_length=200)
    aktiv: bool = True


class VertretungDaten(BaseModel):
    benutzer_id: int | None = None  # None = ich selbst; für andere nur Admins
    vertreter_id: int
    von: date
    bis: date


class EinstellungenDaten(BaseModel):
    adresse: str | None = Field(default=None, max_length=300)
    mail_ereignisse: dict[str, bool] | None = None
    sicherung_anzahl: int | None = Field(default=None, ge=1, le=365)
    sitzung_inaktiv_stunden: float | None = Field(default=None, ge=0.25, le=24 * 14)
    sitzung_ad_stunden: float | None = Field(default=None, ge=1, le=24 * 14)
    erinnerung_tage: int | None = Field(default=None, ge=0, le=30)  # 0 = keine Erinnerungen
    erinnerung_vorgesetzter: bool | None = None


class SmtpDaten(BaseModel):
    server: str = Field(default="", max_length=200)
    port: int = Field(default=587, ge=1, le=65535)
    verschluesselung: str = "starttls"
    benutzer: str = Field(default="", max_length=200)
    passwort: str | None = None  # None = unverändert
    absender: str = Field(default="", max_length=200)


class MailTest(BaseModel):
    an: str = Field(min_length=3, max_length=200)


class LdapGruppe(BaseModel):
    gruppe: str = Field(max_length=500)
    recht: str


class LdapDaten(BaseModel):
    aktiv: bool = False
    server: str = Field(default="", max_length=500)
    domaene: str = Field(default="", max_length=200)
    basis_dn: str = Field(default="", max_length=500)
    zugang_gruppe: str = Field(default="", max_length=500)
    gruppen: list[LdapGruppe] = []


class LdapTest(BaseModel):
    benutzername: str
    passwort: str


_BENUTZERNAME = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _benutzername_pruefen(name: str) -> str:
    name = name.strip()
    if not _BENUTZERNAME.match(name):
        raise fehler(400, "benutzername_ungueltig")
    return name


def _email_pruefen(adresse: str, mehrere: bool = False) -> str:
    adresse = (adresse or "").strip()
    teile = [t.strip() for t in re.split(r"[;,]", adresse) if t.strip()] if mehrere else ([adresse] if adresse else [])
    for t in teile:
        if not _EMAIL.match(t):
            raise fehler(400, "email_ungueltig", adresse=t)
    return ", ".join(teile)


def _passwort_pruefen(pw: str) -> None:
    if len(pw) < auth.MIN_PASSWORT:
        raise fehler(400, "passwort_zu_kurz", min=auth.MIN_PASSWORT)


# --------------------------------------------------------------------------- App
def erstelle_app(pfade: Pfade, hintergrund: bool = True) -> FastAPI:
    pfade.anlegen()
    db = Datenbank(pfade.datenbank)
    versand = mail.Versand(db)

    def erinnerungen() -> None:
        if ablauf.erinnern(db):
            versand.wecken()

    stuendlich = wartung.Stuendlich([lambda: wartung.tages_sicherung(db, pfade), erinnerungen])
    bremse = auth.Anmeldebremse()

    @asynccontextmanager
    async def lebenszyklus(app: FastAPI):
        auth.alte_sitzungen_loeschen(db)
        if hintergrund:
            versand.starten()
            stuendlich.starten()
        yield
        stuendlich.stoppen()
        versand.stoppen()
        db.schliessen()

    app = FastAPI(title=APP_NAME, version=__version__, lifespan=lebenszyklus, docs_url=None, redoc_url=None)
    app.state.db = db
    app.state.pfade = pfade
    app.state.versand = versand
    app.state.ldap_verbindung = None  # Tests setzen hier eine Ersatzverbindung
    app.state.github = None  # Tests setzen hier eine Ersatzabfrage für die Update-Prüfung

    @app.exception_handler(ablauf.AblaufFehler)
    async def _ablauf_fehler(request: Request, ex: ablauf.AblaufFehler):
        return JSONResponse({"detail": {"code": ex.code, **ex.extra}}, status_code=ex.status, headers={"Cache-Control": "private, no-store"})

    @app.middleware("http")
    async def kopfzeilen(request: Request, call_next):
        antwort = await call_next(request)
        if request.url.path.startswith("/api/") and "cache-control" not in antwort.headers:
            antwort.headers["Cache-Control"] = "private, no-store"
        if request.method != "GET" and request.url.path.startswith("/api/"):
            versand.wecken()
        antwort.headers.setdefault("X-Content-Type-Options", "nosniff")
        antwort.headers.setdefault("Referrer-Policy", "same-origin")
        return antwort

    # ---------------------------------------------------------------- Abhängigkeiten
    def aktueller_benutzer(request: Request) -> dict | None:
        b = auth.benutzer_zur_sitzung(db, request.cookies.get(auth.SITZUNG_COOKIE))
        if b is not None:
            b["rechte"] = b["rechte"] if isinstance(b["rechte"], list) else json.loads(b["rechte"])
        return b

    def angemeldet(benutzer: dict | None = Depends(aktueller_benutzer)) -> dict:
        if benutzer is None:
            raise fehler(401, "nicht_angemeldet")
        return benutzer

    def recht(*namen: str):
        def pruefen(benutzer: dict = Depends(angemeldet)) -> dict:
            if not any(n in benutzer["rechte"] for n in namen):
                raise fehler(403, "keine_berechtigung")
            return benutzer

        return pruefen

    verwalten = recht("verwalten")
    statistik_recht = recht("statistik", "verwalten")

    def darf_katalog_pflegen(ich: dict, katalog_id: int) -> None:
        if "verwalten" in ich["rechte"]:
            return
        if katalog_id not in ablauf.kataloge_fuer(db, ich["id"], "pfleger"):
            raise fehler(403, "keine_berechtigung")

    def sitzung_setzen(response: Response, request: Request, benutzer_id: int) -> None:
        token = auth.sitzung_anlegen(db, benutzer_id)
        response.set_cookie(auth.SITZUNG_COOKIE, token, httponly=True, samesite="lax", max_age=auth.SITZUNG_TAGE * 86400,
                            secure=request.url.scheme == "https")

    # ---------------------------------------------------------------- Status und Anmeldung
    @app.get("/api/status")
    def status(benutzer: dict | None = Depends(aktueller_benutzer)):
        leer = db.eins("SELECT COUNT(*) AS n FROM benutzer")["n"] == 0
        return {"name": APP_NAME, "version": __version__, "ersteinrichtung": leer, "benutzer": benutzer}

    @app.post("/api/ersteinrichtung")
    def ersteinrichtung(daten: Ersteinrichtung, request: Request, response: Response):
        if db.eins("SELECT COUNT(*) AS n FROM benutzer")["n"]:
            raise fehler(409, "schon_eingerichtet")
        name = _benutzername_pruefen(daten.benutzername)
        _passwort_pruefen(daten.passwort)
        bid = db.ausfuehren(
            "INSERT INTO benutzer (benutzername, anzeigename, email, passwort_hash, rechte, grenze) VALUES (?, ?, ?, ?, ?, NULL)",
            (name, daten.anzeigename.strip() or name, _email_pruefen(daten.email), auth.passwort_hash(daten.passwort),
             json.dumps(list(RECHTE))))
        sitzung_setzen(response, request, bid)
        return {"ok": True}

    @app.post("/api/anmelden")
    def anmelden(daten: Anmeldung, request: Request, response: Response):
        name = daten.benutzername.strip()
        adresse = f"a:{request.client.host if request.client else '-'}"
        if bremse.gesperrt(f"n:{name.lower()}", adresse):
            raise fehler(429, "zu_viele_versuche")
        b = db.eins("SELECT * FROM benutzer WHERE benutzername = ?", (name,))
        e = verzeichnis.einstellungen(db)
        if b is not None and b["quelle"] == "lokal":
            if not auth.passwort_pruefen(daten.passwort, b["passwort_hash"]):
                bremse.fehlschlag(f"n:{name.lower()}", adresse)
                raise fehler(401, "anmeldung_falsch")
        elif e["aktiv"]:
            try:
                info = verzeichnis.anmelden(e, name, daten.passwort, app.state.ldap_verbindung)
            except verzeichnis.VerzeichnisFehler as ex:
                if ex.code == "anmeldung_falsch":
                    bremse.fehlschlag(f"n:{name.lower()}", adresse)
                raise fehler(401 if ex.code == "anmeldung_falsch" else 503, ex.code)
            if not verzeichnis.zugang(e, info["gruppen"]):
                raise fehler(403, "kein_zugang")
            gruppenrechte = verzeichnis.rechte_fuer(e, info["gruppen"]) & set(RECHTE)
            if b is None:
                bid = db.ausfuehren("INSERT INTO benutzer (benutzername, anzeigename, email, quelle, rechte) VALUES (?, ?, ?, 'ldap', ?)",
                                    (name, info["anzeigename"], info["email"], json.dumps(sorted(gruppenrechte))))
                b = db.eins("SELECT * FROM benutzer WHERE id = ?", (bid,))
            else:
                rechte = sorted(set(json.loads(b["rechte"])) | gruppenrechte)
                db.ausfuehren("UPDATE benutzer SET anzeigename = ?, email = CASE WHEN ? != '' THEN ? ELSE email END, rechte = ? WHERE id = ?",
                              (info["anzeigename"], info["email"], info["email"], json.dumps(rechte), b["id"]))
        else:
            bremse.fehlschlag(f"n:{name.lower()}", adresse)
            raise fehler(401, "anmeldung_falsch")
        if not b["aktiv"]:
            raise fehler(403, "konto_gesperrt")
        bremse.erfolg(f"n:{name.lower()}")
        sitzung_setzen(response, request, b["id"])
        return {"ok": True}

    @app.post("/api/abmelden")
    def abmelden(request: Request, response: Response):
        token = request.cookies.get(auth.SITZUNG_COOKIE)
        if token:
            auth.sitzung_beenden(db, token)
        response.delete_cookie(auth.SITZUNG_COOKIE)
        return {"ok": True}

    @app.post("/api/ich/passwort")
    def passwort_aendern(daten: PasswortAendern, ich: dict = Depends(angemeldet)):
        b = db.eins("SELECT passwort_hash, quelle FROM benutzer WHERE id = ?", (ich["id"],))
        if b["quelle"] != "lokal":
            raise fehler(400, "passwort_im_verzeichnis")
        if not auth.passwort_pruefen(daten.altes_passwort, b["passwort_hash"]):
            raise fehler(400, "passwort_falsch")
        _passwort_pruefen(daten.neues_passwort)
        db.ausfuehren("UPDATE benutzer SET passwort_hash = ? WHERE id = ?", (auth.passwort_hash(daten.neues_passwort), ich["id"]))
        return {"ok": True}

    @app.get("/api/ich")
    def ich_lesen(ich: dict = Depends(angemeldet)):
        b = ablauf.benutzer(db, ich["id"])
        v = ablauf.benutzer(db, b["vorgesetzter_id"])
        k = ablauf.kataloge_fuer(db, ich["id"], "nutzer")
        return {
            **ich,
            "grenze": b["grenze"],
            "kostenstelle_id": b["kostenstelle_id"],
            "vorgesetzter": v["anzeigename"] if v else None,
            "kataloge": db.alle(f"SELECT id, name, beschreibung FROM kataloge WHERE id IN ({','.join('?' * len(k)) or 'NULL'}) ORDER BY name",
                                tuple(k)),
            "pfleger": bool(ablauf.kataloge_fuer(db, ich["id"], "pfleger")),
            "ausfuehrender": bool(ablauf.kataloge_fuer(db, ich["id"], "ausfuehrender")),
            "genehmiger": bool(db.eins("SELECT 1 FROM benutzer WHERE vorgesetzter_id = ? AND aktiv = 1", (ich["id"],))
                               or ablauf.vertretene(db, ich["id"])),
            "offen": ablauf.offene_zahlen(db, ich),
            "kette": ablauf.kette_nach_oben(db, ich["id"]),
            **ablauf.vertretungen_heute(db, ich["id"]),
        }

    @app.get("/api/offen")
    def offen(ich: dict = Depends(angemeldet)):
        return ablauf.offene_zahlen(db, ich)

    @app.get("/api/aufgaben")
    def aufgaben(ich: dict = Depends(angemeldet)):
        daten = ablauf.aufgaben(db, ich)
        if "verwalten" in ich["rechte"]:
            daten["verwaltung"] = {
                "mail_fehlt": not mail.eingerichtet(db),
                "adresse_fehlt": not db.einstellung("adresse", ""),
                "mail_fehler": db.eins("SELECT COUNT(*) AS n FROM mails WHERE status = 'fehler'")["n"],
                "hierarchie": len(ablauf.hierarchie_hinweise(db)),
            }
        return daten

    @app.get("/api/tagesliste")
    def tagesliste(datum: date, ich: dict = Depends(angemeldet)):
        return ablauf.tagesliste(db, ich, datum.isoformat())

    # ---------------------------------------------------------------- Anforderungen
    def _sichtbar(anforderung_id: int, ich: dict) -> dict:
        a = ablauf.laden(db, anforderung_id)
        if not ablauf.darf_sehen(db, a, ich):
            raise fehler(404, "nicht_gefunden")
        return a

    def _mit_aktionen(a: dict, ich: dict) -> dict:
        a["aktionen"] = ablauf.moegliche_aktionen(db, a, ich)
        e = ablauf.entscheider(db, a, ich)
        if e and e["im_namen_von"]:
            a["vertretung_fuer"] = ablauf.benutzer(db, e["im_namen_von"])["anzeigename"]
        if a["status"] == "genehmigung" and a["bearbeiter_id"]:
            g = ablauf.benutzer(db, a["bearbeiter_id"])
            a["bearbeiter_grenze"] = g["grenze"]
            a["bearbeiter_vertretung"] = [v["anzeigename"] for v in ablauf.vertreter_von(db, g["id"])]
            # Genehmigungsweg ab der zuständigen Person, damit jeder sieht, wie es weitergeht
            a["kette"] = [{"id": g["id"], "name": g["anzeigename"], "grenze": g["grenze"], "aktiv": bool(g["aktiv"])},
                          *ablauf.kette_nach_oben(db, g["id"])]
        return a

    @app.get("/api/anforderungen")
    def anforderungen(ansicht: str = "meine", status: str | None = None, ich: dict = Depends(angemeldet)):
        if status and status not in ablauf.STATUS:
            raise fehler(400, "status_unbekannt")
        return ablauf.liste(db, ich, ansicht, status)

    @app.post("/api/anforderungen")
    def anforderung_neu(daten: AnforderungDaten, ich: dict = Depends(angemeldet)):
        d = daten.model_dump()
        d["datum"] = daten.datum.isoformat() if daten.datum else None
        return {"id": ablauf.speichern(db, ich, d)}

    @app.get("/api/anforderungen/{anforderung_id}")
    def anforderung_lesen(anforderung_id: int, ich: dict = Depends(angemeldet)):
        return _mit_aktionen(_sichtbar(anforderung_id, ich), ich)

    @app.put("/api/anforderungen/{anforderung_id}")
    def anforderung_aendern(anforderung_id: int, daten: AnforderungDaten, ich: dict = Depends(angemeldet)):
        d = daten.model_dump()
        d["datum"] = daten.datum.isoformat() if daten.datum else None
        ablauf.speichern(db, ich, d, anforderung_id)
        return _mit_aktionen(ablauf.laden(db, anforderung_id), ich)

    @app.delete("/api/anforderungen/{anforderung_id}")
    def anforderung_loeschen(anforderung_id: int, ich: dict = Depends(angemeldet)):
        ablauf.loeschen(db, ich, anforderung_id)
        return {"ok": True}

    @app.post("/api/anforderungen/{anforderung_id}/uebermitteln")
    def anforderung_uebermitteln(anforderung_id: int, daten: Notiz, ich: dict = Depends(angemeldet)):
        return _mit_aktionen(ablauf.uebermitteln(db, ich, anforderung_id, daten.notiz.strip()), ich)

    @app.post("/api/anforderungen/{anforderung_id}/entscheidung")
    def anforderung_entscheiden(anforderung_id: int, daten: Entscheidung, ich: dict = Depends(angemeldet)):
        return _mit_aktionen(ablauf.entscheiden(db, ich, anforderung_id, daten.aktion, daten.notiz), ich)

    @app.post("/api/anforderungen/{anforderung_id}/erledigt")
    def anforderung_erledigt(anforderung_id: int, daten: Notiz, ich: dict = Depends(angemeldet)):
        return _mit_aktionen(ablauf.erledigen(db, ich, anforderung_id, daten.notiz), ich)

    # ---------------------------------------------------------------- Kataloge und Produkte
    def _katalog(katalog_id: int) -> dict:
        k = db.eins("SELECT * FROM kataloge WHERE id = ?", (katalog_id,))
        if k is None:
            raise fehler(404, "nicht_gefunden")
        return k

    @app.get("/api/kataloge")
    def kataloge(ich: dict = Depends(angemeldet)):
        zeilen = db.alle("""SELECT k.*, (SELECT COUNT(*) FROM produkte p WHERE p.katalog_id = k.id) AS produkte,
                                   (SELECT COUNT(*) FROM katalog_zuordnung z WHERE z.katalog_id = k.id AND z.rolle = 'nutzer') AS nutzer
                              FROM kataloge k ORDER BY k.name""")
        rollen = {}
        for r in db.alle("SELECT katalog_id, rolle FROM katalog_zuordnung WHERE benutzer_id = ?", (ich["id"],)):
            rollen.setdefault(r["katalog_id"], []).append(r["rolle"])
        if "verwalten" not in ich["rechte"]:
            zeilen = [z for z in zeilen if z["id"] in rollen]
        for z in zeilen:
            z["meine_rollen"] = rollen.get(z["id"], [])
        return zeilen

    @app.get("/api/kataloge/{katalog_id}")
    def katalog_lesen(katalog_id: int, ich: dict = Depends(angemeldet)):
        k = _katalog(katalog_id)
        rollen = {r["rolle"] for r in db.alle("SELECT rolle FROM katalog_zuordnung WHERE katalog_id = ? AND benutzer_id = ?",
                                              (katalog_id, ich["id"]))}
        admin = "verwalten" in ich["rechte"]
        if not admin and not rollen:
            raise fehler(404, "nicht_gefunden")
        pflege = admin or "pfleger" in rollen
        k["produkte"] = db.alle(f"SELECT * FROM produkte WHERE katalog_id = ? {'' if pflege else 'AND aktiv = 1'} ORDER BY reihenfolge, name",
                                (katalog_id,))
        k["darf_pflegen"] = pflege
        if admin:
            k["zuordnung"] = {rolle: [r["benutzer_id"] for r in db.alle(
                "SELECT benutzer_id FROM katalog_zuordnung WHERE katalog_id = ? AND rolle = ?", (katalog_id, rolle))] for rolle in KATALOG_ROLLEN}
        return k

    @app.post("/api/kataloge")
    def katalog_neu(daten: KatalogDaten, ich: dict = Depends(verwalten)):
        kid = db.ausfuehren("INSERT INTO kataloge (name, beschreibung, email, aktiv) VALUES (?, ?, ?, ?)",
                            (daten.name.strip(), daten.beschreibung, _email_pruefen(daten.email, True), int(daten.aktiv)))
        return {"id": kid}

    @app.put("/api/kataloge/{katalog_id}")
    def katalog_aendern(katalog_id: int, daten: KatalogDaten, ich: dict = Depends(verwalten)):
        _katalog(katalog_id)
        db.ausfuehren("UPDATE kataloge SET name = ?, beschreibung = ?, email = ?, aktiv = ? WHERE id = ?",
                      (daten.name.strip(), daten.beschreibung, _email_pruefen(daten.email, True), int(daten.aktiv), katalog_id))
        return {"ok": True}

    @app.delete("/api/kataloge/{katalog_id}")
    def katalog_loeschen(katalog_id: int, ich: dict = Depends(verwalten)):
        _katalog(katalog_id)
        if db.eins("SELECT 1 FROM anforderungen WHERE katalog_id = ?", (katalog_id,)):
            raise fehler(409, "katalog_benutzt")
        db.ausfuehren("DELETE FROM kataloge WHERE id = ?", (katalog_id,))
        return {"ok": True}

    @app.put("/api/kataloge/{katalog_id}/zuordnung")
    def katalog_zuordnung(katalog_id: int, daten: Zuordnung, ich: dict = Depends(verwalten)):
        _katalog(katalog_id)
        with db.transaktion():
            db.ausfuehren("DELETE FROM katalog_zuordnung WHERE katalog_id = ?", (katalog_id,))
            for rolle in KATALOG_ROLLEN:
                for bid in set(getattr(daten, rolle)):
                    if not db.eins("SELECT 1 FROM benutzer WHERE id = ?", (bid,)):
                        raise fehler(400, "benutzer_unbekannt")
                    db.ausfuehren("INSERT INTO katalog_zuordnung (katalog_id, benutzer_id, rolle) VALUES (?, ?, ?)", (katalog_id, bid, rolle))
        return {"ok": True}

    @app.post("/api/kataloge/{katalog_id}/produkte")
    def produkt_neu(katalog_id: int, daten: ProduktDaten, ich: dict = Depends(angemeldet)):
        _katalog(katalog_id)
        darf_katalog_pflegen(ich, katalog_id)
        pid = db.ausfuehren("INSERT INTO produkte (katalog_id, name, beschreibung, einheit, preis, aktiv, reihenfolge) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (katalog_id, daten.name.strip(), daten.beschreibung, daten.einheit.strip(), round(daten.preis, 2),
                             int(daten.aktiv), daten.reihenfolge))
        return {"id": pid}

    def _produkt(produkt_id: int, ich: dict) -> dict:
        p = db.eins("SELECT * FROM produkte WHERE id = ?", (produkt_id,))
        if p is None:
            raise fehler(404, "nicht_gefunden")
        darf_katalog_pflegen(ich, p["katalog_id"])
        return p

    @app.put("/api/produkte/{produkt_id}")
    def produkt_aendern(produkt_id: int, daten: ProduktDaten, ich: dict = Depends(angemeldet)):
        _produkt(produkt_id, ich)
        db.ausfuehren("UPDATE produkte SET name = ?, beschreibung = ?, einheit = ?, preis = ?, aktiv = ?, reihenfolge = ? WHERE id = ?",
                      (daten.name.strip(), daten.beschreibung, daten.einheit.strip(), round(daten.preis, 2), int(daten.aktiv),
                       daten.reihenfolge, produkt_id))
        return {"ok": True}

    @app.delete("/api/produkte/{produkt_id}")
    def produkt_loeschen(produkt_id: int, ich: dict = Depends(angemeldet)):
        _produkt(produkt_id, ich)
        db.ausfuehren("DELETE FROM produkte WHERE id = ?", (produkt_id,))
        return {"ok": True}

    # ---------------------------------------------------------------- Benutzer und Hierarchie
    @app.get("/api/benutzer")
    def benutzer_liste(ich: dict = Depends(verwalten)):
        zeilen = db.alle("""SELECT b.id, b.benutzername, b.anzeigename, b.email, b.quelle, b.aktiv, b.rechte, b.vorgesetzter_id,
                                   b.grenze, b.kostenstelle_id, v.anzeigename AS vorgesetzter, ks.nummer AS kostenstelle
                              FROM benutzer b
                              LEFT JOIN benutzer v ON v.id = b.vorgesetzter_id
                              LEFT JOIN kostenstellen ks ON ks.id = b.kostenstelle_id
                             ORDER BY b.aktiv DESC, b.anzeigename""")
        zuordnung = {}
        for r in db.alle("SELECT z.benutzer_id, z.rolle, k.id, k.name FROM katalog_zuordnung z JOIN kataloge k ON k.id = z.katalog_id ORDER BY k.name"):
            zuordnung.setdefault(r["benutzer_id"], {}).setdefault(r["rolle"], []).append({"id": r["id"], "name": r["name"]})
        for z in zeilen:
            z["rechte"] = json.loads(z["rechte"])
            z["kataloge"] = zuordnung.get(z["id"], {})
        return zeilen

    @app.get("/api/benutzer/auswahl")
    def benutzer_auswahl(ich: dict = Depends(angemeldet)):
        return db.alle("SELECT id, anzeigename, benutzername FROM benutzer WHERE aktiv = 1 ORDER BY anzeigename")

    @app.get("/api/hierarchie/hinweise")
    def hinweise(ich: dict = Depends(verwalten)):
        return ablauf.hierarchie_hinweise(db)

    def _benutzer_werte(daten: BenutzerDaten, benutzer_id: int | None) -> dict:
        if daten.quelle not in ("lokal", "ldap"):
            raise fehler(400, "quelle_unbekannt")
        if any(r not in RECHTE for r in daten.rechte):
            raise fehler(400, "recht_unbekannt")
        if daten.kostenstelle_id is not None and not db.eins("SELECT 1 FROM kostenstellen WHERE id = ?", (daten.kostenstelle_id,)):
            raise fehler(400, "kostenstelle_unbekannt")
        for kid in daten.kataloge:
            _katalog(kid)
        if benutzer_id is not None:
            if daten.vorgesetzter_id == benutzer_id:
                raise fehler(400, "hierarchie_kreis")
            ablauf.kette_pruefen(db, benutzer_id, daten.vorgesetzter_id)
        elif daten.vorgesetzter_id is not None and not db.eins("SELECT 1 FROM benutzer WHERE id = ?", (daten.vorgesetzter_id,)):
            raise fehler(400, "benutzer_unbekannt")
        if daten.passwort:
            _passwort_pruefen(daten.passwort)
        return {
            "benutzername": _benutzername_pruefen(daten.benutzername),
            "anzeigename": daten.anzeigename.strip() or daten.benutzername.strip(),
            "email": _email_pruefen(daten.email),
        }

    def _nutzer_kataloge_setzen(benutzer_id: int, kataloge: list[int]) -> None:
        db.ausfuehren("DELETE FROM katalog_zuordnung WHERE benutzer_id = ? AND rolle = 'nutzer'", (benutzer_id,))
        for kid in set(kataloge):
            db.ausfuehren("INSERT INTO katalog_zuordnung (katalog_id, benutzer_id, rolle) VALUES (?, ?, 'nutzer')", (kid, benutzer_id))

    @app.post("/api/benutzer")
    def benutzer_neu(daten: BenutzerDaten, ich: dict = Depends(verwalten)):
        w = _benutzer_werte(daten, None)
        if db.eins("SELECT 1 FROM benutzer WHERE benutzername = ?", (w["benutzername"],)):
            raise fehler(409, "benutzername_vergeben")
        if daten.quelle == "lokal" and not daten.passwort:
            raise fehler(400, "passwort_zu_kurz", min=auth.MIN_PASSWORT)
        with db.transaktion():
            bid = db.ausfuehren(
                """INSERT INTO benutzer (benutzername, anzeigename, email, quelle, passwort_hash, aktiv, rechte, vorgesetzter_id, grenze, kostenstelle_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (w["benutzername"], w["anzeigename"], w["email"], daten.quelle,
                 auth.passwort_hash(daten.passwort) if daten.quelle == "lokal" else "", int(daten.aktiv),
                 json.dumps(sorted(set(daten.rechte))), daten.vorgesetzter_id, daten.grenze, daten.kostenstelle_id))
            _nutzer_kataloge_setzen(bid, daten.kataloge)
        return {"id": bid}

    @app.put("/api/benutzer/{benutzer_id}")
    def benutzer_aendern(benutzer_id: int, daten: BenutzerDaten, ich: dict = Depends(verwalten)):
        alt = db.eins("SELECT * FROM benutzer WHERE id = ?", (benutzer_id,))
        if alt is None:
            raise fehler(404, "nicht_gefunden")
        w = _benutzer_werte(daten, benutzer_id)
        if db.eins("SELECT 1 FROM benutzer WHERE benutzername = ? AND id != ?", (w["benutzername"], benutzer_id)):
            raise fehler(409, "benutzername_vergeben")
        if benutzer_id == ich["id"] and ("verwalten" not in daten.rechte or not daten.aktiv):
            raise fehler(400, "eigene_rechte")
        if daten.quelle == "lokal" and alt["quelle"] != "lokal" and not daten.passwort:
            raise fehler(400, "passwort_zu_kurz", min=auth.MIN_PASSWORT)
        with db.transaktion():
            db.ausfuehren("""UPDATE benutzer SET benutzername = ?, anzeigename = ?, email = ?, quelle = ?, aktiv = ?, rechte = ?,
                             vorgesetzter_id = ?, grenze = ?, kostenstelle_id = ? WHERE id = ?""",
                          (w["benutzername"], w["anzeigename"], w["email"], daten.quelle, int(daten.aktiv), json.dumps(sorted(set(daten.rechte))),
                           daten.vorgesetzter_id, daten.grenze, daten.kostenstelle_id, benutzer_id))
            if daten.quelle == "lokal" and daten.passwort:
                db.ausfuehren("UPDATE benutzer SET passwort_hash = ? WHERE id = ?", (auth.passwort_hash(daten.passwort), benutzer_id))
            if daten.quelle == "ldap":
                db.ausfuehren("UPDATE benutzer SET passwort_hash = '' WHERE id = ?", (benutzer_id,))
            if not daten.aktiv:
                db.ausfuehren("DELETE FROM sitzungen WHERE benutzer_id = ?", (benutzer_id,))
            _nutzer_kataloge_setzen(benutzer_id, daten.kataloge)
        return {"ok": True}

    @app.delete("/api/benutzer/{benutzer_id}")
    def benutzer_loeschen(benutzer_id: int, ich: dict = Depends(verwalten)):
        if benutzer_id == ich["id"]:
            raise fehler(400, "eigene_rechte")
        if db.eins("SELECT 1 FROM anforderungen WHERE antragsteller_id = ? OR bearbeiter_id = ?", (benutzer_id, benutzer_id)) or \
                db.eins("SELECT 1 FROM verlauf WHERE benutzer_id = ? OR im_namen_von = ? OR weiter_an = ?", (benutzer_id,) * 3):
            raise fehler(409, "benutzer_benutzt")
        db.ausfuehren("DELETE FROM benutzer WHERE id = ?", (benutzer_id,))
        return {"ok": True}

    # ---------------------------------------------------------------- Kostenstellen
    @app.get("/api/kostenstellen")
    def kostenstellen(ich: dict = Depends(angemeldet)):
        nur_aktiv = "" if "verwalten" in ich["rechte"] else "WHERE aktiv = 1"
        return db.alle(f"SELECT * FROM kostenstellen {nur_aktiv} ORDER BY nummer")

    @app.post("/api/kostenstellen")
    def kostenstelle_neu(daten: KostenstelleDaten, ich: dict = Depends(verwalten)):
        if db.eins("SELECT 1 FROM kostenstellen WHERE nummer = ?", (daten.nummer.strip(),)):
            raise fehler(409, "kostenstelle_vergeben")
        return {"id": db.ausfuehren("INSERT INTO kostenstellen (nummer, bezeichnung, aktiv) VALUES (?, ?, ?)",
                                    (daten.nummer.strip(), daten.bezeichnung.strip(), int(daten.aktiv)))}

    @app.put("/api/kostenstellen/{ks_id}")
    def kostenstelle_aendern(ks_id: int, daten: KostenstelleDaten, ich: dict = Depends(verwalten)):
        if db.eins("SELECT 1 FROM kostenstellen WHERE nummer = ? AND id != ?", (daten.nummer.strip(), ks_id)):
            raise fehler(409, "kostenstelle_vergeben")
        db.ausfuehren("UPDATE kostenstellen SET nummer = ?, bezeichnung = ?, aktiv = ? WHERE id = ?",
                      (daten.nummer.strip(), daten.bezeichnung.strip(), int(daten.aktiv), ks_id))
        return {"ok": True}

    @app.delete("/api/kostenstellen/{ks_id}")
    def kostenstelle_loeschen(ks_id: int, ich: dict = Depends(verwalten)):
        if db.eins("SELECT 1 FROM anforderungen WHERE kostenstelle_id = ?", (ks_id,)):
            raise fehler(409, "kostenstelle_benutzt")
        db.ausfuehren("DELETE FROM kostenstellen WHERE id = ?", (ks_id,))
        return {"ok": True}

    # ---------------------------------------------------------------- Vertretungen
    @app.get("/api/vertretungen")
    def vertretungen(alle: bool = False, ich: dict = Depends(angemeldet)):
        sql = """SELECT v.*, b.anzeigename AS benutzer, r.anzeigename AS vertreter,
                        (v.von <= date('now', 'localtime') AND v.bis >= date('now', 'localtime')) AS aktiv
                   FROM vertretungen v JOIN benutzer b ON b.id = v.benutzer_id JOIN benutzer r ON r.id = v.vertreter_id"""
        if alle:
            if "verwalten" not in ich["rechte"]:
                raise fehler(403, "keine_berechtigung")
            return db.alle(sql + " WHERE v.bis >= date('now', 'localtime', '-30 days') ORDER BY v.von")
        return db.alle(sql + " WHERE (v.benutzer_id = ? OR v.vertreter_id = ?) AND v.bis >= date('now', 'localtime', '-30 days') ORDER BY v.von",
                       (ich["id"], ich["id"]))

    @app.post("/api/vertretungen")
    def vertretung_neu(daten: VertretungDaten, ich: dict = Depends(angemeldet)):
        fuer = daten.benutzer_id or ich["id"]
        if fuer != ich["id"] and "verwalten" not in ich["rechte"]:
            raise fehler(403, "keine_berechtigung")
        if daten.vertreter_id == fuer:
            raise fehler(400, "vertretung_selbst")
        if daten.bis < daten.von:
            raise fehler(400, "zeitraum_ungueltig")
        if not db.eins("SELECT 1 FROM benutzer WHERE id = ? AND aktiv = 1", (daten.vertreter_id,)):
            raise fehler(400, "benutzer_unbekannt")
        vid = db.ausfuehren("INSERT INTO vertretungen (benutzer_id, vertreter_id, von, bis) VALUES (?, ?, ?, ?)",
                            (fuer, daten.vertreter_id, daten.von.isoformat(), daten.bis.isoformat()))
        return {"id": vid}

    @app.delete("/api/vertretungen/{vertretung_id}")
    def vertretung_loeschen(vertretung_id: int, ich: dict = Depends(angemeldet)):
        v = db.eins("SELECT * FROM vertretungen WHERE id = ?", (vertretung_id,))
        if v is None:
            raise fehler(404, "nicht_gefunden")
        if v["benutzer_id"] != ich["id"] and "verwalten" not in ich["rechte"]:
            raise fehler(403, "keine_berechtigung")
        db.ausfuehren("DELETE FROM vertretungen WHERE id = ?", (vertretung_id,))
        return {"ok": True}

    # ---------------------------------------------------------------- Statistik
    @app.get("/api/statistik")
    def statistik(von: date | None = None, bis: date | None = None, benutzer_id: int | None = None, katalog_id: int | None = None,
                  kostenstelle_id: int | None = None, ich: dict = Depends(statistik_recht)):
        return ablauf.statistik(db, von.isoformat() if von else None, bis.isoformat() if bis else None, benutzer_id, katalog_id, kostenstelle_id)

    @app.get("/api/statistik/filter")
    def statistik_filter(ich: dict = Depends(statistik_recht)):
        return {
            "benutzer": db.alle("SELECT id, anzeigename FROM benutzer ORDER BY anzeigename"),
            "kataloge": db.alle("SELECT id, name FROM kataloge ORDER BY name"),
            "kostenstellen": db.alle("SELECT id, nummer, bezeichnung FROM kostenstellen ORDER BY nummer"),
        }

    # ---------------------------------------------------------------- Einstellungen
    @app.get("/api/einstellungen")
    def einstellungen(ich: dict = Depends(verwalten)):
        smtp = mail.einstellungen(db)
        smtp["passwort_gesetzt"] = bool(smtp.pop("passwort", ""))
        inaktiv, ad = auth.sitzungsdauer(db)
        return {
            "adresse": db.einstellung("adresse", ""),
            "mail_ereignisse": {**{"neue_aufgabe": True, "entscheidung": True, "genehmigt": True, "erledigt": True},
                                **(db.einstellung("mail_ereignisse", {}) or {})},
            "sicherung_anzahl": db.einstellung("sicherung_anzahl", wartung.STANDARD_ANZAHL),
            "sitzung_inaktiv_stunden": inaktiv,
            "sitzung_ad_stunden": ad,
            "erinnerung_tage": db.einstellung("erinnerung_tage", ablauf.STANDARD_ERINNERUNG_TAGE),
            "erinnerung_vorgesetzter": bool(db.einstellung("erinnerung_vorgesetzter", False)),
            "smtp": smtp,
            "ldap": verzeichnis.einstellungen(db),
            "rechte": list(RECHTE),
        }

    @app.put("/api/einstellungen")
    def einstellungen_aendern(daten: EinstellungenDaten, ich: dict = Depends(verwalten)):
        if daten.adresse is not None:
            adresse = daten.adresse.strip().rstrip("/")
            if adresse and not re.match(r"^https?://", adresse):
                raise fehler(400, "adresse_ungueltig")
            db.setze_einstellung("adresse", adresse)
        if daten.mail_ereignisse is not None:
            erlaubt = {"neue_aufgabe", "entscheidung", "genehmigt", "erledigt"}
            db.setze_einstellung("mail_ereignisse", {k: v for k, v in daten.mail_ereignisse.items() if k in erlaubt})
        for feld in ("sicherung_anzahl", "sitzung_inaktiv_stunden", "sitzung_ad_stunden", "erinnerung_tage", "erinnerung_vorgesetzter"):
            wert = getattr(daten, feld)
            if wert is not None:
                db.setze_einstellung(feld, wert)
        return {"ok": True}

    @app.put("/api/einstellungen/smtp")
    def smtp_aendern(daten: SmtpDaten, ich: dict = Depends(verwalten)):
        if daten.verschluesselung not in ("keine", "starttls", "ssl"):
            raise fehler(400, "verschluesselung_unbekannt")
        alt = mail.einstellungen(db)
        neu = daten.model_dump()
        neu["absender"] = _email_pruefen(daten.absender)
        if daten.passwort is None:
            neu["passwort"] = alt.get("passwort", "")
        db.setze_einstellung("smtp", neu)
        return {"ok": True}

    @app.post("/api/einstellungen/smtp/test")
    def smtp_test(daten: MailTest, ich: dict = Depends(verwalten)):
        if not mail.eingerichtet(db):
            raise fehler(400, "mail_nicht_eingerichtet")
        an = _email_pruefen(daten.an)
        try:
            versand.sender(mail.einstellungen(db), an, f"{APP_NAME}: Test-E-Mail",
                           "Diese E-Mail bestätigt, dass der Versand aus dem Anforderungstool funktioniert.")
        except Exception as ex:
            log.warning("Test-Mail fehlgeschlagen: %s", ex)
            raise fehler(502, "mail_fehler", text=str(ex)[:300])
        return {"ok": True}

    @app.get("/api/mails")
    def mails(ich: dict = Depends(verwalten)):
        return db.alle("SELECT id, an, betreff, status, versuche, fehler, erstellt, gesendet FROM mails ORDER BY id DESC LIMIT 100")

    @app.post("/api/mails/{mail_id}/wiederholen")
    def mail_wiederholen(mail_id: int, ich: dict = Depends(verwalten)):
        db.ausfuehren("UPDATE mails SET status = 'wartet', versuche = 0, erstellt = datetime('now') WHERE id = ? AND status = 'fehler'", (mail_id,))
        return {"ok": True}

    @app.put("/api/einstellungen/ldap")
    def ldap_aendern(daten: LdapDaten, ich: dict = Depends(verwalten)):
        if any(g.recht not in RECHTE for g in daten.gruppen):
            raise fehler(400, "recht_unbekannt")
        if daten.aktiv and not daten.server.strip():
            raise fehler(400, "ldap_server_fehlt")
        db.setze_einstellung("ldap", daten.model_dump())
        return {"ok": True}

    @app.post("/api/einstellungen/ldap/test")
    def ldap_test(daten: LdapTest, ich: dict = Depends(verwalten)):
        e = verzeichnis.einstellungen(db)
        try:
            info = verzeichnis.anmelden(e, daten.benutzername.strip(), daten.passwort, app.state.ldap_verbindung)
        except verzeichnis.VerzeichnisFehler as ex:
            raise fehler(400, ex.code)
        return {**info, "zugang": verzeichnis.zugang(e, info["gruppen"]), "rechte": sorted(verzeichnis.rechte_fuer(e, info["gruppen"]))}

    @app.get("/api/sicherungen")
    def sicherungen(ich: dict = Depends(verwalten)):
        return wartung.sicherungen(pfade)

    @app.post("/api/sicherungen")
    def sicherung_neu(ich: dict = Depends(verwalten)):
        return {"name": wartung.sicherung_anlegen(db, pfade).name}

    # ---------------------------------------------------------------- Update
    @app.get("/api/update")
    def update(neu: bool = False, ich: dict = Depends(verwalten)):
        return wartung.update_pruefen(neu, app.state.github)

    @app.post("/api/update")
    def update_starten(ich: dict = Depends(verwalten)):
        info = wartung.update_pruefen(True, app.state.github)
        if not info.get("verfuegbar"):
            raise fehler(400, "kein_update")
        try:
            wartung.sicherung_anlegen(db, pfade, "vor-update")
            version = wartung.update_installieren(pfade, info)
        except wartung.WartungsFehler as ex:
            raise fehler(400, ex.code)
        except Exception as ex:
            log.exception("Update fehlgeschlagen")
            raise fehler(500, "update_fehlgeschlagen", grund=str(ex)[:200])
        return {"ok": True, "version": version}

    # ---------------------------------------------------------------- Oberfläche
    static = static_ordner()

    def _index() -> HTMLResponse:
        # Skripte und Stile unter v/<version>/…, damit Browser und Zwischenspeicher nach einem Update die neuen Dateien holen
        text = (static / "index.html").read_text(encoding="utf-8")
        text = text.replace('href="style.css"', f'href="v/{__version__}/style.css"').replace('src="js/', f'src="v/{__version__}/js/')
        return HTMLResponse(text, headers={"Cache-Control": "no-cache"})

    @app.get("/", include_in_schema=False)
    def startseite():
        return _index()

    @app.get("/{pfad:path}", include_in_schema=False)
    def statische_datei(pfad: str):
        if pfad.startswith("api/"):
            raise fehler(404, "nicht_gefunden")
        m = re.match(r"^v/[^/]+/(.+)$", pfad)
        versioniert = bool(m)
        if m:
            pfad = m.group(1)
        ziel = (static / pfad).resolve()
        if not ziel.is_file() or static.resolve() not in ziel.parents:
            return _index() if "." not in pfad.rsplit("/", 1)[-1] else Response(status_code=404)
        # Dauerhaft zwischenspeichern nur in der installierten Fassung; beim Entwickeln ändern sich Dateien ohne neue Version
        dauerhaft = versioniert and getattr(sys, "frozen", False)
        kopf = {"Cache-Control": "public, max-age=31536000, immutable" if dauerhaft else "no-cache"}
        return FileResponse(ziel, headers=kopf)

    return app
