from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from anforderungstool.config import Pfade
from anforderungstool.server import erstelle_app

PW = "geheim123"


@pytest.fixture
def app(tmp_path):
    a = erstelle_app(Pfade(tmp_path / "daten"), hintergrund=False)
    yield a
    a.state.db.schliessen()


@pytest.fixture
def admin(app):
    c = TestClient(app)
    r = c.post("/api/ersteinrichtung", json={"benutzername": "admin", "anzeigename": "Admin", "email": "admin@example.org", "passwort": PW})
    assert r.status_code == 200, r.text
    return c


def anmelden(app, name: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/anmelden", json={"benutzername": name, "passwort": PW})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def haus(app, admin):
    """Kostenstelle, Cafeteria-Katalog und eine Kette: ich (0 €) → chef (100 €) → boss (unbegrenzt).

    koch führt den Katalog aus, vertreter kann chef vertreten.
    """
    ks = admin.post("/api/kostenstellen", json={"nummer": "4711", "bezeichnung": "Station 3"}).json()["id"]
    kat = admin.post("/api/kataloge", json={"name": "Cafeteria", "email": "cafeteria@example.org"}).json()["id"]
    p_broetchen = admin.post(f"/api/kataloge/{kat}/produkte", json={"name": "Brötchen", "preis": 1.10}).json()["id"]
    p_wurst = admin.post(f"/api/kataloge/{kat}/produkte", json={"name": "Würstchen", "preis": 2.50, "einheit": "Paar"}).json()["id"]

    def neu(name, grenze, vorgesetzter=None, kataloge=()):
        r = admin.post("/api/benutzer", json={"benutzername": name, "anzeigename": name.capitalize(), "email": f"{name}@example.org",
                                              "passwort": PW, "grenze": grenze, "vorgesetzter_id": vorgesetzter,
                                              "kostenstelle_id": ks, "kataloge": list(kataloge)})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    boss = neu("boss", None)
    chef = neu("chef", 100, boss)
    ich = neu("ich", 0, chef, [kat])
    vertreter = neu("vertreter", 0, boss)
    koch = neu("koch", 0)
    admin.put(f"/api/kataloge/{kat}/zuordnung", json={"nutzer": [ich], "ausfuehrender": [koch]})
    return {"ks": ks, "kat": kat, "broetchen": p_broetchen, "wurst": p_wurst,
            "boss": boss, "chef": chef, "ich": ich, "vertreter": vertreter, "koch": koch}


def anforderung(c: TestClient, haus: dict, broetchen: float, wurst: float = 0) -> int:
    r = c.post("/api/anforderungen", json={
        "katalog_id": haus["kat"], "kostenstelle_id": haus["ks"], "anlass": "Sommerfest", "datum": "2026-12-10",
        "uhrzeit": "14:00", "ort": "Konferenzraum 2",
        "positionen": [{"produkt_id": haus["broetchen"], "menge": broetchen}, {"produkt_id": haus["wurst"], "menge": wurst}]})
    assert r.status_code == 200, r.text
    return r.json()["id"]
