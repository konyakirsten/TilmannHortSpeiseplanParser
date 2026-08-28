# Tilemann-Hort Speiseplan-Kalender

Lädt automatisch die wöchentlichen Speiseplan-PDFs von
stiftung-eilbeker-gemeindehaus.de und veröffentlicht sie als
abonnierbaren ICS-Kalender.

## Einrichtung (einmalig)

1. **Neues öffentliches GitHub-Repo** anlegen (öffentlich, damit die
   `.ics`-Datei ohne Login abrufbar ist).
2. Diese Dateien in das Repo pushen (inkl. `.github/workflows/`).
3. Unter **Settings → Actions → General → Workflow permissions**
   „Read and write permissions" aktivieren – sonst darf der Workflow
   die aktualisierte `speiseplan.ics` nicht zurück ins Repo committen.
4. Einmal manuell anstoßen: **Actions → Speiseplan-Kalender
   aktualisieren → Run workflow**, um sofort eine erste
   `speiseplan.ics` zu erzeugen.

## Abonnement-Link für Eltern

Nach dem ersten Lauf liegt die Datei unter:

```
https://raw.githubusercontent.com/<user>/<repo>/main/speiseplan.ics
```

Diese URL kann in Google Kalender, Apple Kalender, Outlook usw. als
„Kalender abonnieren" / „per URL hinzufügen" eingetragen werden
(einige Apps erwarten das `webcal://`-Präfix statt `https://` –
funktioniert identisch).

## Konfiguration

Über Umgebungsvariablen im Workflow (`.github/workflows/update-calendar.yml`)
anpassbar:

- `WEEKS_BEHIND` (Standard `1`) – wie viele Wochen rückwirkend geprüft werden
- `WEEKS_AHEAD` (Standard `8`) – wie viele Wochen im Voraus geprüft werden
- Cron-Zeitplan (Standard: montags 05:30 UTC) – Zeile `cron:` anpassen

## Hinweis zur PDF-Struktur

Der Parser (`speiseplan_parser.py`) nutzt die x/y-Koordinaten der
Textwörter im PDF, nicht die reine Textreihenfolge – eine normale
Textextraktion würde Wochentage und Gerichte durcheinanderbringen,
da das PDF-Layout zweispaltig ist. Ändert die Einrichtung ihr
PDF-Layout grundlegend, muss ggf. `DAY_LABEL_MAX_X` / `LEGEND_MIN_X`
in `speiseplan_parser.py` neu kalibriert werden.
