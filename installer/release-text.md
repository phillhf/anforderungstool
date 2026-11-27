<!-- ende-der-neuerungen -->

---

## Installation

1. **`Anforderungstool-Setup-{VERSION}.exe`** unten unter *Assets* herunterladen.
2. Als Administrator ausführen und den Port wählen (Standard 8480).
3. Im Browser das erste Konto anlegen. Unter *Einstellungen* zeigt eine Liste, was noch einzurichten ist.

Ein Update geht unter *Einstellungen → Update* direkt im Tool oder durch Ausführen dieses Setups. Daten und Einstellungen bleiben erhalten.

**Prüfsumme kontrollieren** (PowerShell, beide Werte müssen gleich sein):

```powershell
(Get-FileHash .\Anforderungstool-Setup-{VERSION}.exe -Algorithm SHA256).Hash
Get-Content .\Anforderungstool-Setup-{VERSION}.exe.sha256
```

## Technische Eckdaten

| | |
|---|---|
| System | Windows Server 2016+ bzw. Windows 10/11, 64 Bit, ohne weitere Laufzeitumgebungen |
| Betrieb | Windows-Dienst `Anforderungstool`, Zugriff per Browser über einen TCP-Port (HTTP oder HTTPS) |
| Daten | lokal in `C:\ProgramData\Anforderungstool`, tägliche Sicherung, keine Telemetrie |
| Internet | nur für die Update-Prüfung (api.github.com, github.com); ohne Internet läuft alles andere, Updates dann per Setup. E-Mails gehen über den eingetragenen Mailserver |
| Unbeaufsichtigt | `Anforderungstool-Setup-{VERSION}.exe /VERYSILENT /PORT=8480 /TASKS="firewall"` |
| Herkunft | von GitHub Actions aus dem Tag `v{VERSION}` gebaut, alle Tests vor dem Bau |

Lizenz: Privatpersonen dürfen das Tool privat kostenlos nutzen. Jede Organisation braucht eine kostenpflichtige Lizenz (siehe [LICENSE](https://github.com/phillhf/anforderungstool/blob/main/LICENSE)).
