"""Übersicht, Genehmigungsweg, Tagesliste, Erinnerungen und Update-Prüfung."""

from __future__ import annotations

from datetime import date, timedelta

from conftest import anforderung, anmelden

from anforderungstool import __version__, ablauf


def test_uebersicht_zeigt_nur_eigene_aufgaben(app, haus):
    ich, chef, koch = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "koch")
    entwurf = anforderung(ich, haus, 1)
    offen = anforderung(ich, haus, 50)
    ich.post(f"/api/anforderungen/{offen}/uebermitteln", json={})

    a = ich.get("/api/aufgaben").json()
    assert [z["id"] for z in a["entwuerfe"]] == [entwurf]
    assert [z["id"] for z in a["laufend"]] == [offen] and a["laufend"][0]["bearbeiter"] == "Chef"
    assert a["genehmigen"] == [] and a["rueckfragen"] == [] and "verwaltung" not in a

    c = chef.get("/api/aufgaben").json()
    assert [z["id"] for z in c["genehmigen"]] == [offen]
    assert c["genehmigen"][0]["endgueltig"] is True and c["genehmigen"][0]["seit"]

    chef.post(f"/api/anforderungen/{offen}/entscheidung", json={"aktion": "rueckfrage", "notiz": "Reichen 30 Stück?"})
    r = ich.get("/api/aufgaben").json()["rueckfragen"]
    assert r[0]["id"] == offen and r[0]["notiz"] == "Reichen 30 Stück?" and r[0]["von"] == "Chef"
    assert koch.get("/api/aufgaben").json()["ausfuehren"] == []


def test_uebersicht_fuer_verwaltung(admin, haus):
    v = admin.get("/api/aufgaben").json()["verwaltung"]
    assert v["mail_fehlt"] is True and v["adresse_fehlt"] is True and v["mail_fehler"] == 0


def test_genehmigungsweg_und_kette(app, haus):
    ich, chef = anmelden(app, "ich"), anmelden(app, "chef")
    i = ich.get("/api/ich").json()
    assert [(p["name"], p["grenze"]) for p in i["kette"]] == [("Chef", 100), ("Boss", None)]
    aid = anforderung(ich, haus, 100)  # 110 € – über der Grenze des Chefs
    ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    a = chef.get(f"/api/anforderungen/{aid}").json()
    assert [p["name"] for p in a["kette"]] == ["Chef", "Boss"]
    zeile = chef.get("/api/anforderungen?ansicht=genehmigen").json()[0]
    assert zeile["endgueltig"] is False  # Chef kann nur befürworten


def test_vertretung_in_hinweisleiste(app, haus):
    chef, vertreter = anmelden(app, "chef"), anmelden(app, "vertreter")
    heute = date.today().isoformat()
    r = chef.post("/api/vertretungen", json={"vertreter_id": haus["vertreter"], "von": heute, "bis": heute})
    assert r.status_code == 200, r.text
    assert chef.get("/api/ich").json()["vertreten_durch"] == [{"name": "Vertreter", "bis": heute}]
    assert vertreter.get("/api/ich").json()["ich_vertrete"] == [{"name": "Chef", "bis": heute}]


def test_tagesliste(app, haus):
    ich, chef, koch = anmelden(app, "ich"), anmelden(app, "chef"), anmelden(app, "koch")
    ids = [anforderung(ich, haus, n, 2) for n in (10, 20)]
    for aid in ids:
        ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
        chef.post(f"/api/anforderungen/{aid}/entscheidung", json={"aktion": "genehmigen"})
    d = koch.get("/api/tagesliste?datum=2026-12-10").json()
    assert [a["id"] for a in d["anforderungen"]] == ids
    summen = {s["name"]: s["menge"] for s in d["summen"]}
    assert summen == {"Brötchen": 30, "Würstchen": 4}
    assert koch.get("/api/tagesliste?datum=2026-12-11").json()["anforderungen"] == []
    assert ich.get("/api/tagesliste?datum=2026-12-10").status_code == 403
    # Ausführen-Liste nach Termin
    assert [z["id"] for z in koch.get("/api/anforderungen?ansicht=ausfuehren&status=genehmigt").json()] == ids


def test_werktage():
    freitag = date(2026, 11, 27)
    assert ablauf.werktage_zwischen(freitag, freitag + timedelta(days=3)) == 1  # Montag
    assert ablauf.werktage_zwischen(freitag, freitag + timedelta(days=5)) == 3  # bis Mittwoch


def test_erinnerung(app, admin, haus):
    db = app.state.db
    ich = anmelden(app, "ich")
    aid = anforderung(ich, haus, 50)
    ich.post(f"/api/anforderungen/{aid}/uebermitteln", json={})
    db.ausfuehren("UPDATE verlauf SET zeit = '2026-11-20 08:00:00' WHERE anforderung_id = ?", (aid,))  # Freitag
    vorher = db.eins("SELECT COUNT(*) AS n FROM mails")["n"]

    assert ablauf.erinnern(db, date(2026, 11, 24)) == 0  # Dienstag: erst 2 Werktage
    assert ablauf.erinnern(db, date(2026, 11, 25)) == 1  # Mittwoch: 3 Werktage
    neu = db.alle("SELECT an, betreff FROM mails WHERE id > (SELECT MAX(id) - 1 FROM mails)")
    assert neu[0]["an"] == "chef@example.org" and neu[0]["betreff"].startswith("Erinnerung")
    assert db.eins("SELECT COUNT(*) AS n FROM mails")["n"] == vorher + 1
    # nicht gleich noch einmal; am Wochenende nie
    db.ausfuehren("UPDATE anforderungen SET erinnert = '2026-11-25 07:00:00' WHERE id = ?", (aid,))
    assert ablauf.erinnern(db, date(2026, 11, 26)) == 0
    assert ablauf.erinnern(db, date(2026, 11, 28)) == 0
    # ausgeschaltet
    admin.put("/api/einstellungen", json={"erinnerung_tage": 0})
    assert ablauf.erinnern(db, date(2026, 12, 9)) == 0


def test_update_pruefung(app, admin):
    def github(url):
        return {"tag_name": "v99.0.0", "body": "## Neu\n- alles besser\n<!-- ende-der-neuerungen -->\nfester Teil", "html_url": "https://example.org/r",
                "assets": [{"name": "Anforderungstool-Setup-99.0.0.exe", "browser_download_url": "https://example.org/s.exe"},
                           {"name": "Anforderungstool-Setup-99.0.0.exe.sha256", "browser_download_url": "https://example.org/s.sha256"}]}

    app.state.github = github
    u = admin.get("/api/update").json()
    assert u["aktuell"] == __version__ and u["neueste"] == "99.0.0" and u["verfuegbar"] is True
    assert u["notizen"] == "## Neu\n- alles besser"
    assert u["installierbar"] is False  # nur in der installierten Windows-Fassung

    app.state.github = lambda url: (_ for _ in ()).throw(OSError("offline"))
    assert admin.get("/api/update").json()["fehler"] == "keine_verbindung"
