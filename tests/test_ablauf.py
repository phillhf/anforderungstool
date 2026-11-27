from __future__ import annotations

from datetime import date, timedelta

from conftest import anforderung, anmelden


def mails(app):
    return app.state.db.alle("SELECT an, betreff FROM mails ORDER BY id")


def test_unter_grenze_entscheidet_chef(app, haus):
    ich, chef, koch = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "koch")
    aid = anforderung(ich, haus, 50)  # 55 €
    a = ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={}).json()
    assert a["status"] == "genehmigung" and a["bearbeiter"] == "Chef" and a["summe"] == 55.0
    assert [z["id"] for z in chef.get("/api/anforderungen?ansicht=genehmigen").json()] == [aid]
    assert chef.get("/api/offen").json()["genehmigen"] == 1
    # koch sieht sie noch nicht
    assert koch.get(f"/api/anforderungen/{aid}").status_code == 404
    a = chef.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen", "notiz": "passt"}).json()
    assert a["status"] == "genehmigt"
    assert [v["aktion"] for v in a["verlauf"]] == ["uebermittelt", "genehmigt"]
    an = [m["an"] for m in mails(app)]
    assert "chef@example.org" in an and "cafeteria@example.org" in an and "koch@example.org" in an and "ich@example.org" in an
    # Ausführender meldet erledigt
    assert koch.get("/api/offen").json()["ausfuehren"] == 1
    a = koch.post(f"/api/anforderungen/{aid}/erledigt", json={"notiz": "geliefert"}).json()
    assert a["status"] == "erledigt" and a["verlauf"][-1]["benutzer"] == "Koch"


def test_ueber_grenze_befuerwortet_und_weiter(app, haus):
    ich, chef, boss = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "boss")
    aid = anforderung(ich, haus, 100)  # 110 €
    ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    a = chef.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen", "notiz": "aus meiner Sicht ok"}).json()
    assert a["status"] == "genehmigung" and a["bearbeiter"] == "Boss"
    assert a["verlauf"][-1]["aktion"] == "befuerwortet" and a["verlauf"][-1]["weiter_an"] == "Boss"
    # chef kann nicht mehr entscheiden, sieht sie aber weiter
    assert chef.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen"}).status_code == 403
    assert chef.get(f"/api/anforderungen/{aid}").status_code == 200
    a = boss.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen"}).json()
    assert a["status"] == "genehmigt"


def test_selbstgenehmigung_innerhalb_eigener_grenze(app, admin, haus):
    admin_daten = next(b for b in admin.get("/api/benutzer").json() if b["benutzername"] == "chef")
    admin.put(f"/api/benutzer/{haus['chef']}", json={**admin_daten, "kataloge": [haus["kat"]]})
    chef = anmelden(app, "chef")
    aid = anforderung(chef, haus, 10)
    a = chef.post(f"/api/anforderungen/{aid}/uebermitteln", json={}).json()
    assert a["status"] == "genehmigt"
    assert [v["aktion"] for v in a["verlauf"]] == ["uebermittelt", "selbst_genehmigt"]


def test_ablehnen_braucht_begruendung(app, haus):
    ich, chef = anmelden(app, "ich"), anmelden(app, "chef")
    aid = anforderung(ich, haus, 5)
    ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    r = chef.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "ablehnen"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "notiz_fehlt"
    a = chef.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "ablehnen", "notiz": "zu teuer"}).json()
    assert a["status"] == "abgelehnt" and a["aktionen"] == []


def test_rueckfrage_und_neustart_der_kette(app, haus):
    ich, chef, boss = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "boss")
    aid = anforderung(ich, haus, 100)
    ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    chef.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen"})
    a = boss.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "rueckfrage", "notiz": "Bitte weniger Brötchen"}).json()
    assert a["status"] == "rueckfrage"
    assert ich.get("/api/offen").json()["rueckfragen"] == 1
    assert "bearbeiten" in ich.get(f"/api/anforderungen/{aid}").json()["aktionen"]
    # ändern und erneut übermitteln → beginnt wieder beim Chef
    r = ich.put(f"/api/anforderungen/{aid}", json={
        "katalog_id": haus["kat"], "kostenstelle_id": haus["ks"], "anlass": "Sommerfest", "datum": "2026-12-10", "ort": "Raum 2",
        "positionen": [{"produkt_id": haus["broetchen"], "menge": 60}]})
    assert r.status_code == 200, r.text
    a = ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={"notiz": "auf 60 reduziert"}).json()
    assert a["status"] == "genehmigung" and a["bearbeiter"] == "Chef" and a["summe"] == 66.0
    assert a["verlauf"][-1]["aktion"] == "erneut_uebermittelt" and a["verlauf"][-1]["notiz"] == "auf 60 reduziert"
    a = chef.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen"}).json()
    assert a["status"] == "genehmigt"


def test_vertretung_entscheidet_im_namen(app, haus):
    ich, chef, vertreter = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "vertreter")
    heute = date.today()
    r = chef.post("/api/vertretungen", json={"vertreter_id": haus["vertreter"], "von": heute.isoformat(),
                                             "bis": (heute + timedelta(days=7)).isoformat()})
    assert r.status_code == 200, r.text
    aid = anforderung(ich, haus, 50)
    ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    assert "vertreter@example.org" in [m["an"] for m in mails(app)]
    liste = vertreter.get("/api/anforderungen?ansicht=genehmigen").json()
    assert liste[0]["id"] == aid and liste[0]["vertretung"] is True
    a = vertreter.get(f"/api/anforderungen/{aid}").json()
    assert a["vertretung_fuer"] == "Chef" and "genehmigen" in a["aktionen"]
    a = vertreter.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen"}).json()
    assert a["status"] == "genehmigt"  # mit der Grenze des Chefs (100 €)
    assert a["verlauf"][-1]["benutzer"] == "Vertreter" and a["verlauf"][-1]["im_namen_von"] == "Chef"


def test_vertretung_abgelaufen(app, haus):
    ich, chef, vertreter = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "vertreter")
    gestern = date.today() - timedelta(days=1)
    chef.post("/api/vertretungen", json={"vertreter_id": haus["vertreter"], "von": (gestern - timedelta(days=5)).isoformat(),
                                         "bis": gestern.isoformat()})
    aid = anforderung(ich, haus, 5)
    ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    assert vertreter.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen"}).status_code == 403


def test_kette_endet_ohne_vorgesetzten(app, admin, haus):
    # boss bekommt eine Grenze → Anforderung über 100 € kann nicht enden
    b = next(x for x in admin.get("/api/benutzer").json() if x["benutzername"] == "boss")
    admin.put(f"/api/benutzer/{haus['boss']}", json={**b, "grenze": 50, "kataloge": []})
    hinweise = admin.get("/api/hierarchie/hinweise").json()
    assert any(h["code"] == "spitze_begrenzt" and h["name"] == "Boss" for h in hinweise)
    # koch darf nichts anfordern und ist niemandes Vorgesetzter → kein Hinweis
    assert not any(h["name"] == "Koch" for h in hinweise)
    ich, chef, boss = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "boss")
    aid = anforderung(ich, haus, 200)
    ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    chef.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen"})
    r = boss.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "kein_vorgesetzter"
    # Zustand unverändert, ablehnen geht weiter
    assert boss.get(f"/api/anforderungen/{aid}").json()["bearbeiter"] == "Boss"
    assert boss.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "ablehnen", "notiz": "x"}).status_code == 200


def test_hierarchie_ohne_kreis(admin, haus):
    b = next(x for x in admin.get("/api/benutzer").json() if x["benutzername"] == "boss")
    r = admin.put(f"/api/benutzer/{haus['boss']}", json={**b, "vorgesetzter_id": haus["ich"], "kataloge": []})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "hierarchie_kreis"


def test_nur_zugewiesene_kataloge(app, admin, haus):
    andere = admin.post("/api/kataloge", json={"name": "Büromaterial"}).json()["id"]
    ich = anmelden(app, "ich")
    assert [k["name"] for k in ich.get("/api/ich").json()["kataloge"]] == ["Cafeteria"]
    assert ich.get(f"/api/kataloge/{andere}").status_code == 404
    r = ich.post("/api/anforderungen", json={"katalog_id": andere, "positionen": []})
    assert r.status_code == 403
    # Produkt aus fremdem Katalog
    r = ich.post("/api/anforderungen", json={"katalog_id": haus["kat"], "positionen": [{"produkt_id": 999, "menge": 1}]})
    assert r.status_code == 400


def test_preis_wird_beim_uebermitteln_festgehalten(app, admin, haus):
    ich = anmelden(app, "ich")
    aid = anforderung(ich, haus, 10)
    admin.put(f"/api/produkte/{haus['broetchen']}", json={"name": "Brötchen", "preis": 1.50})
    a = ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={}).json()
    assert a["summe"] == 15.0
    admin.put(f"/api/produkte/{haus['broetchen']}", json={"name": "Brötchen", "preis": 9.99})
    assert ich.get(f"/api/anforderungen/{aid}").json()["positionen"][0]["preis"] == 1.5


def test_pflichtangaben(app, haus):
    ich = anmelden(app, "ich")
    r = ich.post("/api/anforderungen", json={"katalog_id": haus["kat"], "positionen": [{"produkt_id": haus["broetchen"], "menge": 1}]})
    aid = r.json()["id"]
    r = ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    assert r.status_code == 400 and set(r.json()["detail"]["felder"]) == {"anlass", "datum", "ort", "kostenstelle"}


def test_statistik(app, admin, haus):
    ich, chef = anmelden(app, "ich"), anmelden(app, "chef")
    a1 = anforderung(ich, haus, 10)
    a2 = anforderung(ich, haus, 20)
    anforderung(ich, haus, 30)  # Entwurf zählt nicht
    for aid in (a1, a2):
        ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    chef.post(f"/api/anforderungen/{a1}/entscheidung", json={"aktion": "genehmigen"})
    chef.post(f"/api/anforderungen/{a2}/entscheidung", json={"aktion": "ablehnen", "notiz": "nein"})
    s = admin.get("/api/statistik").json()
    z = s["zeilen"][0]
    assert z["name"] == "Ich" and z["anzahl"] == 2 and z["summe"] == 33.0
    assert z["summe_genehmigt"] == 11.0 and z["summe_abgelehnt"] == 22.0
    assert ich.get("/api/statistik").status_code == 403
    assert admin.get(f"/api/statistik?kostenstelle_id={haus['ks']}").json()["gesamt"]["anzahl"] == 2


def test_mailversand_mit_ersatz(app, admin, haus):
    gesendet = []
    app.state.versand.sender = lambda e, an, betreff, text: gesendet.append(an)
    admin.put("/api/einstellungen/smtp", json={"server": "smtp.example.org", "absender": "tool@example.org"})
    admin.put("/api/einstellungen", json={"adresse": "https://anforderung.example.org"})
    ich = anmelden(app, "ich")
    aid = anforderung(ich, haus, 5)
    ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    assert app.state.versand.abarbeiten() == 1
    assert gesendet == ["chef@example.org"]
    text = app.state.db.eins("SELECT text FROM mails")["text"]
    assert f"https://anforderung.example.org/#/anforderung/{aid}" in text
    # Ereignis abschalten
    admin.put("/api/einstellungen", json={"mail_ereignisse": {"neue_aufgabe": False}})
    aid = anforderung(ich, haus, 5)
    ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    assert app.state.versand.abarbeiten() == 0


def test_ldap_anmeldung(app, admin):
    class Eintrag:
        def __init__(self):
            self.displayName = type("W", (), {"value": "Maria Muster"})()
            self.mail = type("W", (), {"value": "maria@example.org"})()
            self.memberOf = type("W", (), {"values": ["CN=Anforderung-Statistik,OU=G,DC=x"], "value": None})()

        def __contains__(self, k):
            return True

    class Verbindung:
        entries = [Eintrag()]

        def search(self, *a, **k):
            pass

        def unbind(self):
            pass

    app.state.ldap_verbindung = lambda server, upn, pw: Verbindung()
    admin.put("/api/einstellungen/ldap", json={"aktiv": True, "server": "ldaps://dc", "domaene": "x.local", "basis_dn": "DC=x",
                                               "gruppen": [{"gruppe": "Anforderung-Statistik", "recht": "statistik"}]})
    from fastapi.testclient import TestClient

    c = TestClient(app)
    assert c.post("/api/anmelden", json={"benutzername": "maria", "passwort": "egal"}).status_code == 200
    ich = c.get("/api/ich").json()
    assert ich["anzeigename"] == "Maria Muster" and ich["email"] == "maria@example.org" and ich["rechte"] == ["statistik"]


def test_oberflaeche_versioniert(admin):
    r = admin.get("/")
    assert r.status_code == 200 and "/js/app.js" in r.text and "v/" in r.text
    assert admin.get("/api/status").headers["cache-control"] == "private, no-store"
