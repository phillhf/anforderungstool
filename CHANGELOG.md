# Änderungen

## [0.3.0] – 27.11.2026

Neu: **Ausnahmeanträge** für alles, was in keinem Katalog steht, zum Beispiel Bürostühle, Glasabfallbehälter oder ein medizinisches Gerät. Jeder sieht jederzeit den ganzen Weg und wo der Antrag gerade liegt.

- **Antrag stellen:** Was, Beschreibung, Bereich, Kostenstelle, Menge und Preis (die Summe rechnet das Tool), laufende Kosten, Lieferant, Begründung, Wirtschaftlichkeit und Anhänge (PDF, Office, Bilder, E-Mails, bis 20 MB je Datei). Jeder darf einen Antrag stellen.
- **Fachstellen** wie Einkauf, IT, Team ISM oder Medizintechnik legt der Admin selbst an, mit Mitgliedern und einer festen Reihenfolge. Eine Fachstelle ist *immer* beteiligt oder *bei Bedarf*. Fachstellen „bei Bedarf“ kreuzt der Antragsteller an, mit einem Hinweis, wann sie dazugehören.
- **Weg:** Zuerst prüft der eigene Vorgesetzte, danach die Fachstellen nacheinander. Der Betrag spielt keine Rolle. Den Weg sieht man schon beim Ausfüllen.
- **Jede Station** kann freigeben, eine Rückfrage stellen, ablehnen oder eine weitere Fachstelle dazuholen. Nach einer Rückfrage geht es bei der Stelle weiter, die gefragt hat. Die bisherigen Freigaben bleiben bestehen.
- **Nach der Freigabe** meldet der Einkauf (oder die festgelegte Fachstelle) *bestellt*, *geliefert* und *erledigt*, jeweils mit Notiz, zum Beispiel der Bestellnummer.
- **Weg des Antrags** in der Ansicht: erledigte Stationen mit Person und Zeitpunkt, die aktuelle markiert, die kommenden grau, bis „erledigt“. Auf dem Handy steht der Weg ganz oben.
- Ausnahmeanträge erscheinen in der Übersicht (Rückfragen, zu prüfen, zu bestellen, Entwürfe, laufend), mit E-Mails, Erinnerungen, Vertretung und Zahl im Browser-Tab.
- Sichtbar ist ein Antrag nur für die Beteiligten: Antragsteller, Vorgesetzter, Mitglieder der beteiligten Fachstellen samt Vertretung, Einkauf ab der Freigabe und Admins.
- Die tägliche Sicherung nimmt die Anhänge mit (Ordner `sicherungennhaenge`).

## [0.2.0] – 27.11.2026

Jeder sieht sofort, was er tun kann und tun muss.

- **Übersicht als Startseite:** Kacheln nur für das, was die Person betrifft: Rückfragen an sie (mit der Frage im Wortlaut), zu genehmigen, auszuführen, nicht übermittelte Entwürfe und die eigenen laufenden Anforderungen. Ist nichts zu tun, steht das dort.
- **Vorher sehen, was ein Klick bewirkt:** Beim Genehmigen steht, ob endgültig genehmigt wird oder an wen die Anforderung weitergeht. Beim Anfordern zeigt das Tool schon während der Eingabe den Genehmigungsweg, zum Beispiel „Carl Chef → Dr. Berta Boss“.
- **Verlauf mit Ausblick:** Unter dem aktuellen Schritt stehen die noch folgenden Stellen bis zur Ausführung.
- **Wartet bei / seit:** In allen Listen steht, bei wem eine Anforderung liegt und seit wann. Ab drei Tagen ist das hervorgehoben.
- **Hinweise statt leerer Seiten,** zum Beispiel wenn kein Vorgesetzter eingetragen ist oder E-Mails nicht verschickt werden konnten.
- **Vertretung als Leiste oben:** „Du vertrittst gerade …“ beziehungsweise „Du wirst gerade vertreten von …“.
- **Erinnerungs-E-Mails** nach einstellbar vielen Werktagen (Standard 3), wahlweise mit Kopie an den Vorgesetzten des Genehmigers.
- **Zahl offener Aufgaben im Browser-Tab,** zum Beispiel „(3) Anforderungstool“.
- **Tagesliste zum Drucken** für die Ausführenden: alle Anforderungen eines Tages mit Produkten und einer Gesamtmenge je Produkt. Die Liste „Ausführen“ ist nach Termin sortiert und markiert „heute“, „morgen“ und „Termin vorbei“.
- **Update aus dem Tool:** Unter *Einstellungen → Update* wird die neue Version geladen, geprüft und installiert. Vorher legt das Tool eine Sicherung an. Admins sehen eine neue Version auch im Menü.

## [0.1.0] – 27.11.2026

Erste Fassung.

- Anforderungen aus Katalogen mit Preisen, Anlass, Termin, Ort, Kostenstelle und Bemerkung. Ein Entwurf lässt sich speichern.
- Genehmigungskette über Vorgesetzte und Freigabegrenzen, mit Befürwortung, Ablehnung, Rückfrage und Selbstgenehmigung.
- Vertretung mit Zeitraum, im Verlauf sichtbar.
- Ausführende melden genehmigte Anforderungen als erledigt.
- Kataloge mit Zuordnung: anfordern, pflegen, ausführen.
- Kostenstellen, Benutzer mit Hierarchie-Ansicht und Hinweisen auf Lücken.
- E-Mail-Versand über SMTP mit Warteschlange, Wiederholung und Ereignis-Schaltern.
- Anmeldung über eigene Konten oder Active Directory.
- Statistik, tägliche Sicherung, Einrichtungsliste für Admins.
