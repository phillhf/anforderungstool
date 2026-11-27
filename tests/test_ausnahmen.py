"""Ausnahmeanträge: Weg über Vorgesetzten und Fachstellen, Rückfrage, Hinzuziehen, Bestellung, Anhänge, Sichtbarkeit."""

from __future__ import annotations

from datetime import date

import pytest
from conftest import anmelden

from anforderungstool import ausnahme, wartung


@pytest.fixture
def stellen(app, admin, haus):
    """Reihenfolge: Medizintechnik* → IT* → ISM* → Einkauf (führt aus) → Geschäftsführung (* = bei Bedarf).

    Mitglieder: koch in Medizintechnik, vertreter in IT und ISM, boss in Einkauf und Geschäftsführung.
    """
    def neu(name, art, rf, mitglieder, ausfuehrend=False):
        r = admin.post("/api/fachstellen", json={"name": name, "art": art, "reihenfolge": rf, "mitglieder": mitglieder,
                                                 "ausfuehrend": ausfuehrend, "hinweis": f"Hinweis {name}"})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    return {
        "mt": neu("Medizintechnik", "bedarf", 10, [haus["koch"]]),
        "it": neu("IT", "bedarf", 20, [haus["vertreter"]]),
        "ism": neu("ISM", "bedarf", 30, [haus["vertreter"]]),
        "einkauf": neu("Einkauf", "immer", 40, [haus["boss"]], ausfuehrend=True),
        "gf": neu("Geschäftsführung", "immer", 50, [haus["boss"]]),
    }


def antrag(c, haus, fachstellen=(), **mehr):
    r = c.post("/api/ausnahmen", json={"titel": "10 Bürostühle", "bereich": "Station 3", "kostenstelle_id": haus["ks"],
                                       "begruendung": "Die alten sind kaputt.", "menge": 10, "einzelpreis": 250,
                                       "fachstellen": list(fachstellen), **mehr})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def weg(a):
    return [(s["name"], s["status"]) for s in a["stationen"]]


def test_buerostuhl_ohne_bedarfsstellen(app, haus, stellen):
    ich, chef, boss = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "boss")
    aid = antrag(ich, haus)
    a = ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={}).json()
    assert a["status"] == "pruefung" and a["summe"] == 2500
    assert weg(a) == [("Chef", "offen"), ("Einkauf", "offen"), ("Geschäftsführung", "offen")]
    assert [z["id"] for z in chef.get("/api/ausnahmen?ansicht=pruefen").json()] == [aid]
    assert boss.get("/api/ausnahmen?ansicht=pruefen").json() == []  # noch nicht dran
    assert boss.get(f"/api/ausnahmen/{aid}").status_code == 200  # aber beteiligt, darf sehen
    chef.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "freigeben"})
    boss.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "freigeben", "notiz": "Einkauf ok"})
    a = boss.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "freigeben"}).json()
    assert a["status"] == "freigegeben" and all(s["status"] == "freigegeben" for s in a["stationen"])
    assert a["verlauf"][-1]["aktion"] == "endgueltig_freigegeben"
    # Einkauf bestellt, liefert, erledigt
    assert "status" in a["aktionen"]
    assert boss.post(f"/api/ausnahmen/{aid}/status", json={"status": "freigegeben"}).status_code == 409
    boss.post(f"/api/ausnahmen/{aid}/status", json={"status": "bestellt", "notiz": "Bestellnr. 4711"})
    a = boss.post(f"/api/ausnahmen/{aid}/status", json={"status": "erledigt"}).json()
    assert a["status"] == "erledigt" and a["abgeschlossen"]
    assert ich.post(f"/api/ausnahmen/{aid}/status", json={"status": "erledigt"}).status_code == 403


def test_medizingeraet_mit_bedarfsstellen_und_reihenfolge(app, haus, stellen):
    ich = anmelden(app, "ich")
    aid = antrag(ich, haus, [stellen["ism"], stellen["mt"]])
    a = ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={}).json()
    assert [s for s, _ in weg(a)] == ["Chef", "Medizintechnik", "ISM", "Einkauf", "Geschäftsführung"]


def test_rueckfrage_geht_bei_fragender_stelle_weiter(app, haus, stellen):
    ich, chef, boss = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "boss")
    aid = antrag(ich, haus)
    ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={})
    chef.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "freigeben"})
    assert boss.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "rueckfrage"}).status_code == 400  # Text fehlt
    boss.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "rueckfrage", "notiz": "Gibt es ein Angebot?"})
    assert ich.get("/api/aufgaben").json()["ausnahmen"]["rueckfragen"][0]["notiz"] == "Gibt es ein Angebot?"
    # Antragsteller ändert und kreuzt dabei die IT an
    a = ich.get(f"/api/ausnahmen/{aid}").json()
    ich.put(f"/api/ausnahmen/{aid}", json={**{k: a[k] for k in ausnahme.FELDER}, "einzelpreis": 200, "fachstellen": [stellen["it"]]})
    a = ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={"notiz": "Angebot hängt an"}).json()
    # Chef bleibt freigegeben, IT kommt vor den Einkauf (der hatte noch nicht freigegeben)
    assert weg(a) == [("Chef", "freigegeben"), ("IT", "offen"), ("Einkauf", "offen"), ("Geschäftsführung", "offen")]
    assert a["verlauf"][-1]["aktion"] == "erneut_uebermittelt" and a["verlauf"][-1]["weiter_an"] == "IT"


def test_fachstelle_hinzuziehen(app, haus, stellen):
    ich, chef, boss = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "boss")
    aid = antrag(ich, haus)
    ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={})
    chef.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "freigeben"})
    # Einkauf merkt: muss ins Netz → IT (steht eigentlich vor dem Einkauf) kommt direkt als Nächstes
    a = boss.post(f"/api/ausnahmen/{aid}/hinzuziehen", json={"fachstelle_id": stellen["it"], "notiz": "Gerät ins Netz"}).json()
    assert [s for s, _ in weg(a)] == ["Chef", "Einkauf", "IT", "Geschäftsführung"]
    assert next(s for s in a["stationen"] if s["name"] == "IT")["hinzugefuegt_von"] == "Boss"
    assert boss.post(f"/api/ausnahmen/{aid}/hinzuziehen", json={"fachstelle_id": stellen["it"]}).status_code == 409
    boss.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "freigeben"})
    vertreter = anmelden(app, "vertreter")  # Mitglied der IT
    assert [z["id"] for z in vertreter.get("/api/ausnahmen?ansicht=pruefen").json()] == [aid]


def test_vertretung_entscheidet_fuer_fachstelle(app, haus, stellen):
    ich, chef, boss = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "boss")
    heute = date.today().isoformat()
    boss.post("/api/vertretungen", json={"vertreter_id": haus["chef"], "von": heute, "bis": heute})
    aid = antrag(ich, haus)
    ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={})
    chef.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "freigeben"})
    zeile = chef.get("/api/ausnahmen?ansicht=pruefen").json()[0]
    assert zeile["station"] == "Einkauf" and zeile["vertretung_fuer"] == "Boss"
    a = chef.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "freigeben"}).json()
    einkauf = next(s for s in a["stationen"] if s["name"] == "Einkauf")
    assert einkauf["entschieden_von"] == "Chef" and einkauf["im_namen_von"] == "Boss"


def test_ablehnen_und_sichtbarkeit(app, haus, stellen):
    ich, chef, koch = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "koch")
    aid = antrag(ich, haus)
    assert chef.get(f"/api/ausnahmen/{aid}").status_code == 404  # Entwurf: nur der Antragsteller
    ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={})
    assert koch.get(f"/api/ausnahmen/{aid}").status_code == 404  # Medizintechnik ist nicht beteiligt
    a = chef.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "ablehnen", "notiz": "Kein Budget"}).json()
    assert a["status"] == "abgelehnt"
    assert chef.post(f"/api/ausnahmen/{aid}/entscheidung", json={"aktion": "freigeben"}).status_code == 403


def test_pflichtangaben(app, haus, stellen):
    ich = anmelden(app, "ich")
    aid = antrag(ich, haus, begruendung="", einzelpreis=0)
    r = ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={})
    assert r.status_code == 400 and set(r.json()["detail"]["felder"]) == {"begruendung", "kosten"}


def test_anhaenge(app, haus, stellen):
    ich, chef = anmelden(app, "ich"), anmelden(app, "chef")
    aid = antrag(ich, haus)
    r = ich.post(f"/api/ausnahmen/{aid}/anhaenge?name=Angebot.pdf", content=b"%PDF-1.4 test")
    assert r.status_code == 200, r.text
    hid = r.json()["id"]
    assert ich.post(f"/api/ausnahmen/{aid}/anhaenge?name=boese.exe", content=b"MZ").status_code == 400
    assert chef.post(f"/api/ausnahmen/{aid}/anhaenge?name=x.pdf", content=b"x").status_code == 404
    ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={})
    r = chef.get(f"/api/anhaenge/{hid}")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 test" and "Angebot.pdf" in r.headers["content-disposition"]
    # Nach dem Übermitteln kann der Antragsteller seinen Anhang nicht mehr löschen (nur bei Rückfrage)
    assert ich.delete(f"/api/anhaenge/{hid}").status_code == 409
    # Anhänge kommen in die Sicherung
    assert wartung.anhaenge_sichern(app.state.pfade) == 1
    assert wartung.anhaenge_sichern(app.state.pfade) == 0


def test_uebersicht_und_zahlen(app, haus, stellen):
    ich, chef = anmelden(app, "ich"), anmelden(app, "chef")
    aid = antrag(ich, haus)
    ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={})
    assert chef.get("/api/ich").json()["offen_ausnahmen"]["pruefen"] == 1
    a = chef.get("/api/aufgaben").json()["ausnahmen"]
    assert a["pruefen"][0]["id"] == aid and a["pruefen"][0]["station"] == "Chef"
    laufend = ich.get("/api/aufgaben").json()["ausnahmen"]["laufend"]
    assert laufend[0]["station"] == "Chef" and laufend[0]["status"] == "pruefung"


def test_erinnerung(app, haus, stellen):
    db = app.state.db
    ich = anmelden(app, "ich")
    aid = antrag(ich, haus)
    ich.post(f"/api/ausnahmen/{aid}/uebermitteln", json={})
    db.ausfuehren("UPDATE ausnahme_verlauf SET zeit = '2026-11-20 08:00:00' WHERE ausnahme_id = ?", (aid,))
    assert ausnahme.erinnern(db, date(2026, 11, 25)) == 1
    assert db.alle("SELECT an, betreff FROM mails ORDER BY id DESC LIMIT 1")[0]["betreff"].startswith("Erinnerung: Ausnahmeantrag")
