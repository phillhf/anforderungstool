# Anforderungstool

Web-Anwendung für hausinterne Anforderungen mit Genehmigung. Ein Beispiel: Brötchen aus der Cafeteria für eine Feier, Büromaterial oder andere Leistungen aus einem Katalog.

## So läuft eine Anforderung

1. **Anfordern:** Die Person wählt Produkte mit Preis und Menge aus einem ihrer Kataloge. Dazu gibt sie Anlass, Datum, Uhrzeit, Ort und Kostenstelle an und übermittelt.
2. **Genehmigen:** Die Anforderung geht an den Vorgesetzten.
   - Liegt die Summe innerhalb seiner **Freigabegrenze**, entscheidet er endgültig.
   - Liegt sie darüber, kann er nur **befürworten**. Dann geht die Anforderung automatisch eine Stufe höher.
   - Er kann auch ablehnen oder eine **Rückfrage** stellen. Nach einer Rückfrage ändert die Person die Anforderung und übermittelt sie erneut. Die Kette beginnt dann von vorn.
3. **Ausführen:** Nach der Genehmigung bekommt der Katalog (zum Beispiel die Cafeteria) eine E-Mail. Die Ausführenden melden die Anforderung im Tool als **erledigt**.

Wer anfordert, sieht jederzeit, wo die Anforderung steht und wer was entschieden hat.

## Funktionen

- **Benutzer:** eigene Konten mit Passwort, wahlweise auch Anmeldung über Active Directory.
- **Hierarchie:** Jede Person hat einen Vorgesetzten und eine Freigabegrenze pro Anforderung (0 €, ein Betrag oder unbegrenzt). Wer innerhalb der eigenen Grenze liegt, genehmigt sich selbst.
- **Vertretung:** Für einen Zeitraum entscheidet eine andere Person im eigenen Namen. Im Verlauf steht „… in Vertretung für …“.
- **Kataloge:** Produkte mit Preis und Einheit. Pro Katalog legt man fest, wer anfordern, wer Produkte pflegen und wer ausführen darf.
- **Kostenstellen:** eine Liste, dazu eine Standard-Kostenstelle je Person.
- **E-Mails** über SMTP. Pro Ereignis lässt sich ein- und ausschalten, ob eine E-Mail rausgeht.
- **Statistik:** wer wie viel angefordert hat, nach Zeitraum, Person, Katalog und Kostenstelle.
- **Sicherung:** einmal täglich automatisch.

## Installation

1. Unter [Releases](https://github.com/phillhf/anforderungstool/releases) die neueste `Anforderungstool-Setup-x.y.z.exe` herunterladen.
2. Als Administrator ausführen und den Port wählen (Standard 8480).
3. Im Browser `http://<Server>:<Port>` öffnen und das erste Konto anlegen. Unter *Einstellungen* zeigt eine Liste, was noch einzurichten ist.

Das Tool läuft als Windows-Dienst `Anforderungstool`. Die Daten liegen in `C:\ProgramData\Anforderungstool` und bleiben bei Updates und bei der Deinstallation erhalten. Ein Update ist einfach das neue Setup.

Notfall-Passwort für ein Konto (als Administrator im Programmordner):

```powershell
.\Anforderungstool.exe passwort admin
```

## Starten (Entwicklung)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m anforderungstool --data data serve --port 8480
```

Danach im Browser `http://localhost:8480` öffnen und das erste Konto anlegen. Beispieldaten für einen leeren Server legt `werkzeuge/beispieldaten.py` an.

Tests:

```powershell
.venv\Scripts\python -m pytest
```

## Lizenz

Privatpersonen dürfen das Tool privat kostenlos nutzen. Jede Nutzung durch Organisationen braucht eine kostenpflichtige Lizenz. Das gilt auch für Unternehmen, Krankenhäuser, Behörden und Vereine. Einzelheiten stehen in [LICENSE](LICENSE).
