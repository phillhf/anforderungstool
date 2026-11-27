"""Legt in einer frischen Installation Beispieldaten an (nur zum Ausprobieren und Testen).

  python werkzeuge/beispieldaten.py [http://localhost:8481]

Konten (alle mit dem Passwort aus PASSWORT):
  admin      Verwaltung, unbegrenzte Grenze
  boss       Geschäftsführung, unbegrenzt
  chef       Stationsleitung, Grenze 100 €, Vorgesetzter boss
  anna       Pflegekraft, Grenze 0 €, Vorgesetzte chef, darf aus „Cafeteria“ und „Büromaterial“ anfordern
  vertreter  stellv. Stationsleitung, Grenze 0 €, Vorgesetzter boss
  kueche     Cafeteria, führt den Katalog „Cafeteria“ aus und pflegt ihn
  einkauf    Fachstelle Einkauf (bestellt freigegebene Ausnahmeanträge)
  it         Fachstellen IT und Team ISM

Fachstellen für Ausnahmeanträge: Medizintechnik (vertreter), IT, Team ISM (bei Bedarf), Einkauf, Geschäftsführung (boss, immer).
"""

from __future__ import annotations

import sys

import httpx

PASSWORT = "beispiel123"


def main(adresse: str) -> None:
    c = httpx.Client(base_url=adresse.rstrip("/") + "/api/")
    r = c.post("ersteinrichtung", json={"benutzername": "admin", "anzeigename": "Verwaltung", "email": "admin@beispiel.test", "passwort": PASSWORT})
    if r.status_code == 409:
        c.post("anmelden", json={"benutzername": "admin", "passwort": PASSWORT}).raise_for_status()
    else:
        r.raise_for_status()

    def post(pfad, daten):
        r = c.post(pfad, json=daten)
        r.raise_for_status()
        return r.json().get("id")

    ks1 = post("kostenstellen", {"nummer": "4100", "bezeichnung": "Station 3 Innere"})
    post("kostenstellen", {"nummer": "4200", "bezeichnung": "Station 5 Chirurgie"})
    post("kostenstellen", {"nummer": "9000", "bezeichnung": "Verwaltung"})
    caf = post("kataloge", {"name": "Cafeteria", "email": "cafeteria@beispiel.test",
                            "beschreibung": "Bitte mindestens 3 Werktage vorher anfordern. Lieferung in Räume im Haupthaus."})
    for i, (name, preis, einheit, beschreibung) in enumerate([
        ("Brötchen belegt", 2.40, "Stück", "Käse, Schinken oder vegetarisch gemischt"),
        ("Mini-Hamburger", 3.20, "Stück", ""),
        ("Würstchen mit Brötchen", 2.90, "Portion", "Wiener Würstchen, Senf"),
        ("Kaffee", 9.50, "Kanne", "1 Liter, mit Milch und Zucker"),
        ("Mineralwasser", 1.20, "Flasche", "0,75 l"),
        ("Kuchenplatte", 24.00, "Platte", "12 Stück, gemischt"),
    ]):
        post(f"kataloge/{caf}/produkte", {"name": name, "preis": preis, "einheit": einheit, "beschreibung": beschreibung, "reihenfolge": i})
    buero = post("kataloge", {"name": "Büromaterial", "email": "einkauf@beispiel.test"})
    for name, preis, einheit in [("Kopierpapier A4", 4.90, "Pack (500 Blatt)"), ("Kugelschreiber", 0.60, "Stück"), ("Ordner breit", 2.10, "Stück")]:
        post(f"kataloge/{buero}/produkte", {"name": name, "preis": preis, "einheit": einheit})

    def person(name, anzeigename, grenze, vorgesetzter=None, kataloge=()):
        return post("benutzer", {"benutzername": name, "anzeigename": anzeigename, "email": f"{name}@beispiel.test", "passwort": PASSWORT,
                                 "grenze": grenze, "vorgesetzter_id": vorgesetzter, "kostenstelle_id": ks1, "kataloge": list(kataloge)})

    boss = person("boss", "Dr. Berta Boss", None)
    chef = person("chef", "Carl Chef", 100, boss)
    anna = person("anna", "Anna Antrag", 0, chef, [caf, buero])
    vertreter = person("vertreter", "Vera Vertreter", 0, boss)
    kueche = person("kueche", "Kurt Küche", 0)
    einkauf = person("einkauf", "Erik Einkauf", 0, boss)
    it = person("it", "Ida IT", 0, boss)
    c.put(f"kataloge/{caf}/zuordnung", json={"nutzer": [anna], "pfleger": [kueche], "ausfuehrender": [kueche]}).raise_for_status()
    c.put(f"kataloge/{buero}/zuordnung", json={"nutzer": [anna]}).raise_for_status()
    fachstellen(post, {"boss": boss, "vertreter": vertreter, "einkauf": einkauf, "it": it})
    print("Beispieldaten angelegt.")


def fachstellen(post, p: dict) -> None:
    """Fachstellen für Ausnahmeanträge: Medizintechnik*, IT*, Team ISM*, Einkauf, Geschäftsführung (* = bei Bedarf)."""
    for i, (name, art, hinweis, mitglieder, ausfuehrend) in enumerate([
        ("Medizintechnik", "bedarf", "Ankreuzen bei medizinischen Geräten und Zubehör.", [p["vertreter"]], False),
        ("IT", "bedarf", "Ankreuzen, wenn etwas ans Netzwerk oder an einen PC angeschlossen wird oder Software dazugehört.", [p["it"]], False),
        ("Team ISM (Datenschutz)", "bedarf", "Ankreuzen, wenn Patienten- oder Mitarbeiterdaten verarbeitet oder gespeichert werden.", [p["it"]], False),
        ("Einkauf", "immer", "", [p["einkauf"]], True),
        ("Geschäftsführung", "immer", "", [p["boss"]], False),
    ], start=1):
        post("fachstellen", {"name": name, "art": art, "hinweis": hinweis, "mitglieder": mitglieder, "ausfuehrend": ausfuehrend, "reihenfolge": i * 10})


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8481")
