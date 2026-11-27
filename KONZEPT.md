# Anforderungstool – Konzept

Stand: 27.11.2026, Entwurf nach Besprechung. Noch nichts programmiert.

## Zweck

Mitarbeiter fordern Waren oder Leistungen aus hausinternen Katalogen an,
zum Beispiel Brötchen aus der Cafeteria für eine Feier oder Büromaterial.
Die Anforderung läuft durch eine Genehmigungskette nach festen Regeln.
Nach der Genehmigung bekommt der Ausführende sie und meldet sie als erledigt.
Jeder Beteiligte sieht jederzeit, wo die Anforderung steht.

## Technik

- Web-Anwendung im selben Aufbau wie die Logistik Map: Python mit FastAPI und SQLite.
- Läuft als Windows-Dienst mit Installer, Port-Wahl, Sicherung und Updates.
- E-Mail-Versand über SMTP. Server, Port, Absender und Verschlüsselung werden in den Einstellungen eingetragen.
- Die Oberfläche ist auf Deutsch, die Texte liegen getrennt im Sprachpaket.

## Anmeldung und Rollen

- Eigene Benutzerkonten sind der Normalfall. Die AD-Anmeldung ist zusätzlich möglich und je Benutzer wählbar.
- **Admin:** verwaltet alle Benutzer, die Hierarchie, Kataloge, Einstellungen und E-Mail.
- **Katalogpfleger:** pflegt die Produkte und Preise der Kataloge, die ihm zugewiesen sind.
- **Ausführender:** sieht die genehmigten Anforderungen seiner Kataloge und meldet sie als erledigt.
- **Statistik:** darf die Auswertung sehen.
- Jeder Benutzer kann Anforderungen stellen.
- Die Rollen sind Rechte und lassen sich kombinieren.

## Kataloge

- Ein Katalog hat einen Namen, Produkte, einen oder mehrere Ausführende und eine E-Mail-Adresse für Benachrichtigungen.
- Ein Produkt hat Name, Beschreibung, Einheit und Preis. Es kann aktiv oder inaktiv sein.
- **Jedem Benutzer werden Kataloge zugewiesen.** Er sieht nur diese und kann nur daraus bestellen.
- Der Preis wird beim Übermitteln in der Anforderung festgehalten. Spätere Preisänderungen ändern alte Anforderungen nicht.

## Anforderung

- Der Antragsteller wählt Katalog, Produkte und Mengen. Die Summe wird angezeigt.
- Dazu kommen Anlass, Datum und Uhrzeit, Ort und eine optionale Bemerkung.
- Er kann sie als Entwurf speichern oder übermitteln.

## Hierarchie

- Personenbezogen und unabhängig von Abteilungen: Jeder Benutzer hat genau **einen Vorgesetzten**.
  Beispiel: Ich → Chef Y → Chef XXX.
- Jeder Benutzer hat eine **Freigabegrenze pro Anforderung** in Euro. Die Grenze kann 0 oder unbegrenzt sein.
- Der Admin pflegt beides.

## Genehmigungsregeln

1. Liegt die Summe innerhalb der eigenen Freigabegrenze des Antragstellers, ist die Anforderung **sofort genehmigt**. Das ist die Selbstgenehmigung.
2. Sonst geht sie an seinen Vorgesetzten.
3. Der Genehmiger hat drei Möglichkeiten:
   - **Ablehnen**, mit Begründung. Damit ist der Vorgang beendet.
   - **Rückfrage**, mit Text. Die Anforderung geht zurück an den Antragsteller. Er kann sie ändern, eine Antwort schreiben und sie erneut übermitteln.
   - **Genehmigen**, mit optionaler Notiz. Liegt die Summe innerhalb seiner Grenze, ist die Anforderung endgültig genehmigt. Liegt sie darüber, gilt sein Ja als **Befürwortung**, und die Anforderung geht automatisch an seinen Vorgesetzten. Das wiederholt sich, bis jemand mit ausreichender Grenze entscheidet.
4. Hat jemand keinen Vorgesetzten und reicht seine Grenze nicht aus, kann die Kette nicht enden.
   Das System warnt beim Einrichten davor: Die oberste Person braucht eine ausreichende oder unbegrenzte Grenze.

## Vertretung

- Ein Benutzer trägt eine Vertretung mit Zeitraum ein, zum Beispiel für den Urlaub.
- Im Zeitraum kann die Vertretung **im Namen** des Vertretenen entscheiden, mit dessen Freigabegrenze.
- Im Verlauf steht deutlich, wer entschieden hat: „Entschieden von A in Vertretung für B“.

## Nach der Genehmigung

- Eine E-Mail geht an den Katalog beziehungsweise an die Ausführenden.
- Der Ausführende meldet im System „erledigt“, auf Wunsch mit Notiz. Damit ist der Vorgang abgeschlossen.

## Status und Verlauf

- Statusstufen: Entwurf → In Genehmigung (bei Person X) → Rückfrage → Genehmigt → Erledigt. Daneben gibt es „Abgelehnt“.
- Jede Anforderung hat einen vollständigen Verlauf: wer, wann, was, mit Notiz, gegebenenfalls in Vertretung.
- Der Antragsteller sieht seine Anforderungen mit aktuellem Status.
- Genehmiger und Ausführende haben jeweils eine Liste „Meine offenen Aufgaben“.

## E-Mails

Im Admin-Bereich lässt sich einzeln ein- und ausschalten, welche E-Mails rausgehen:

- an den Genehmiger, wenn eine neue Aufgabe für ihn da ist
- an den Antragsteller bei Genehmigung, Ablehnung oder Rückfrage
- an den Katalog oder die Ausführenden bei Genehmigung
- an den Antragsteller, wenn die Anforderung erledigt ist

## Statistik

- Zeigt, wer wie viel angefordert hat.
- Filter: Zeitraum, Person und Katalog.
- Spalten: Anzahl und Summe, jeweils für alle, genehmigte und abgelehnte Anforderungen.

## Entschieden

- **Eine Anforderung enthält Produkte aus genau einem Katalog.**
- **Nach einer Rückfrage** und dem erneuten Übermitteln startet die Kette wieder von vorn. Frühere Entscheidungen bleiben im Verlauf sichtbar.
- **Kostenstelle:** Sie ist an jeder Anforderung ein Pflichtfeld.
  - Der Admin pflegt eine Liste mit Nummer und Bezeichnung.
  - Jeder Benutzer hat eine Standard-Kostenstelle, die beim Anlegen vorbelegt ist. Er kann aus der ganzen Liste eine andere wählen.
  - Die Statistik lässt sich auch nach Kostenstelle filtern.
- **Repo:** öffentlich auf GitHub.
- **Lizenz:** eigener Lizenztext. Nur Privatpersonen dürfen das Tool kostenlos und privat nutzen. Jede Organisation braucht eine kostenpflichtige Lizenz, auch Krankenhäuser, Behörden und gemeinnützige Einrichtungen. Der Text ist nicht anwaltlich geprüft.

---

# Teil 2: Ausnahmeanträge (ab 0.3.0)

Für Dinge, die in keinem Katalog stehen: zum Beispiel 10 Bürostühle, Glasabfallbehälter oder ein medizinisches Gerät. Bisher läuft das in Pegasos und ist dort undurchsichtig. Niemand sieht, wo ein Antrag gerade liegt. Das ist das Hauptziel: **Jeder sieht jederzeit die ganze Strecke und wo der Antrag gerade steht.**

## Einordnung

- Eine zweite Antragsart im bestehenden Tool, neben der Katalog-Anforderung. Benutzer, Anmeldung, Hierarchie, Vertretung, E-Mails, Übersicht und Erinnerungen werden mitbenutzt.
- Jeder angemeldete Benutzer darf einen Ausnahmeantrag stellen.
- Die Nummern laufen getrennt: **AA-0001**.

## Formular

- **Was:** Titel (z. B. „10 Bürostühle“) und Beschreibung
- **Wofür und wo:** Bereich bzw. Station, Kostenstelle (Pflicht), Begründung (Pflicht)
- **Kosten** in festen Feldern:
  - Menge und Preis je Stück; die Summe rechnet das Tool
  - laufende Kosten pro Jahr (optional)
  - Lieferant oder Angebot (optional)
- **Wirtschaftlichkeit:** Freitext. Die eigentliche Rechnung macht der Antragsteller selbst, zum Beispiel als Anhang.
- **Anhänge:** Angebote, Berechnungen (Excel, PDF), Fotos
- **Beteiligte Fachstellen:** Häkchen für die Stellen, die nur bei Bedarf beteiligt sind (siehe unten), mit dem Hinweis des Admins, wann eine Stelle dazugehört
- Schon beim Ausfüllen zeigt das Tool den Weg, der sich daraus ergibt.

## Fachstellen

- Der Admin legt beliebig viele Fachstellen an, zum Beispiel Einkauf, IT, Team ISM (Datenschutz), Medizintechnik, Controlling, Geschäftsführung.
- Jede Fachstelle hat ein oder mehrere **Mitglieder**. Jedes Mitglied darf für die Stelle entscheiden. Die persönliche Vertretung gilt zusätzlich.
- Jede Fachstelle ist entweder
  - **immer beteiligt**: Sie prüft jeden Antrag, oder
  - **bei Bedarf beteiligt**: Der Antragsteller kreuzt sie an. Dazu gibt es einen Hinweistext, z. B. bei ISM „Ankreuzen, wenn Patienten- oder Mitarbeiterdaten verarbeitet werden“.
- Der Admin legt **eine feste Reihenfolge** über alle Fachstellen fest. Der Betrag spielt keine Rolle.

## Weg eines Antrags

1. **Eigener Vorgesetzter** (nur die direkte Stelle, nicht die ganze Kette): Will der Bereich das überhaupt?
2. **Fachstellen nacheinander** in der festen Reihenfolge. Nicht angekreuzte Stellen fallen weg.

Beispiel mit der Reihenfolge Medizintechnik* → IT* → ISM* → Einkauf → Geschäftsführung (* = bei Bedarf):
- Bürostuhl: Vorgesetzter → Einkauf → Geschäftsführung
- Medizinisches Gerät mit Patientendaten: Vorgesetzter → Medizintechnik → IT → ISM → Einkauf → Geschäftsführung

Jede Station kann:
- **Freigeben:** weiter zur nächsten Station
- **Rückfrage:** mit Text zurück an den Antragsteller. Nach dem erneuten Übermitteln geht es **bei der fragenden Station weiter**. Frühere Freigaben bleiben gültig und im Verlauf sichtbar.
- **Ablehnen:** mit Pflicht-Begründung, damit ist der Antrag beendet
- **Weitere Fachstelle hinzuziehen:** Jede prüfende Station kann eine „bei Bedarf“-Stelle dazunehmen. Ein Beispiel: Der Einkauf merkt, dass das Gerät ins Netzwerk muss, und holt die IT dazu. Die Stelle wird an ihrer Position in der Reihenfolge eingefügt. Liegt diese Position schon hinter dem Antrag, kommt die Stelle als Nächstes dran. Im Verlauf steht, wer sie dazugenommen hat.
- Notizen und eigene Anhänge dazulegen

## Nach der Freigabe

- Eine vom Admin festgelegte Fachstelle (meist der Einkauf) führt den Antrag weiter: **bestellt → geliefert → erledigt**, jeweils mit optionaler Notiz, zum Beispiel Bestellnummer oder Liefertermin.
- Der Antragsteller bekommt bei jeder Entscheidung und jedem dieser Schritte eine E-Mail.

## Transparenz

- Der Verlauf zeigt **die ganze Strecke**: erledigte Stationen mit Person und Zeitpunkt, die aktuelle markiert, die kommenden grau.
- In allen Listen steht „wartet bei IT · seit 4 Tagen“.
- Ausnahmeanträge erscheinen in den Kacheln der Übersicht. Für Mitglieder einer Fachstelle gibt es die Kachel „Für meine Fachstelle zu prüfen“. Erinnerungs-Mails und die Zahl im Browser-Tab gelten auch hier.

## Wer sieht einen Antrag?

Nur die Beteiligten: der Antragsteller, sein Vorgesetzter, die Mitglieder der beteiligten Fachstellen, deren Vertretungen und die Admins.

## Entschieden (Teil 2)

- Fachstellen sind frei anlegbar, entweder immer beteiligt oder bei Bedarf, in fester Reihenfolge, unabhängig vom Betrag.
- Die Stationen prüfen nacheinander, nie parallel.
- Zuerst prüft der direkte Vorgesetzte, danach die Fachstellen.
- Jede Station darf eine „bei Bedarf“-Stelle nachträglich hinzuziehen.
- Nach einer Rückfrage geht es bei der fragenden Station weiter.
- Kosten in festen Feldern, die Wirtschaftlichkeitsrechnung als Freitext oder Anhang.
- Nach der Freigabe: bestellt → geliefert → erledigt, meist durch den Einkauf.
- Sichtbar nur für die Beteiligten.
