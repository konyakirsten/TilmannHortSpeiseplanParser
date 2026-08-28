#!/usr/bin/env python3
"""
Ruft die wöchentlichen Tilemann-Hort Speiseplan-PDFs ab und baut daraus
eine öffentlich abonnierbare ICS-Kalenderdatei.

Läuft als eigenständiges Skript (z.B. per GitHub Actions Cron), keine
Home-Assistant/pyscript-Abhängigkeiten.
"""

from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timedelta, timezone

import requests

from speiseplan_parser import DayMenu, parse_allergen_legend, parse_pdf_bytes

URL_TEMPLATE = "https://stiftung-eilbeker-gemeindehaus.de/_data/{year}-{week:02d}_Kw_Speiseplan.pdf"
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "speiseplan.ics")

# Wie viele Wochen vor/nach der aktuellen Woche geprüft werden.
WEEKS_BEHIND = int(os.environ.get("WEEKS_BEHIND", "1"))
WEEKS_AHEAD = int(os.environ.get("WEEKS_AHEAD", "8"))

WEEKDAY_ISO = {
    "Montag": 1,
    "Dienstag": 2,
    "Mittwoch": 3,
    "Donnerstag": 4,
    "Freitag": 5,
}

CALNAME = "Tilemann-Hort Speiseplan"
UID_DOMAIN = "tilemann-hort-speiseplan.local"


def iter_candidate_weeks() -> list[tuple[int, int]]:
    """Liefert eine deduplizierte, aufsteigend sortierte Liste von
    (iso_jahr, iso_woche)-Paaren rund um die aktuelle Woche."""
    start = date.today() - timedelta(weeks=WEEKS_BEHIND)
    end_days = (WEEKS_BEHIND + WEEKS_AHEAD) * 7
    seen: dict[tuple[int, int], None] = {}
    for offset in range(0, end_days + 1, 7):
        d = start + timedelta(days=offset)
        iso_year, iso_week, _ = d.isocalendar()
        seen[(iso_year, iso_week)] = None
    return sorted(seen.keys())


def fetch_pdf(year: int, week: int) -> bytes | None:
    url = URL_TEMPLATE.format(year=year, week=week)
    try:
        resp = requests.get(url, timeout=20)
    except requests.RequestException as exc:
        print(f"  Warnung: Abruf von {url} fehlgeschlagen: {exc}")
        return None
    if resp.status_code != 200 or not resp.content:
        print(f"  {url} -> HTTP {resp.status_code} (noch nicht veröffentlicht)")
        return None
    if not resp.content.startswith(b"%PDF"):
        print(f"  {url} -> kein gültiges PDF, überspringe")
        return None
    print(f"  {url} -> OK ({len(resp.content)} Bytes)")
    return resp.content


def escape_ics_text(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace(",", "\\,")
    text = text.replace(";", "\\;")
    text = text.replace("\n", "\\n")
    return text


def fold_ics_line(line: str) -> str:
    if len(line.encode("utf-8")) <= 75:
        return line
    result = []
    while len(line.encode("utf-8")) > 75:
        # einfache (nicht multibyte-exakte) Faltung reicht für unsere Texte
        result.append(line[:70])
        line = " " + line[70:]
    result.append(line)
    return "\r\n".join(result)


def event_uid(day: date) -> str:
    base = f"speiseplan-{day.isoformat()}"
    return f"{base}@{UID_DOMAIN}"


def build_event(day: date, menu: DayMenu, legend: dict[str, str]) -> list[str]:
    lines = []
    lines.append("BEGIN:VEVENT")
    lines.append(f"UID:{event_uid(day)}")
    next_day = day + timedelta(days=1)
    lines.append(f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}")
    lines.append(f"DTEND;VALUE=DATE:{next_day.strftime('%Y%m%d')}")

    summary = " / ".join(menu.lines) if menu.lines else "Speiseplan"
    lines.append(f"SUMMARY:{escape_ics_text(summary)}")

    desc_parts = list(menu.lines)
    if menu.allergen_codes:
        allergen_text = ", ".join(
            f"{code} ({legend[code]})" if code in legend else code
            for code in menu.allergen_codes
        )
        desc_parts.append(f"Enthält: {allergen_text}")
    description = "\\n".join(escape_ics_text(p) for p in desc_parts)
    lines.append(f"DESCRIPTION:{description}")

    lines.append("CATEGORIES:Speiseplan")
    lines.append(f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    lines.append("END:VEVENT")
    return lines


def build_ics(events: list[list[str]]) -> str:
    lines = []
    lines.append("BEGIN:VCALENDAR")
    lines.append("VERSION:2.0")
    lines.append("PRODID:-//Tilemann-Hort//Speiseplan//DE")
    lines.append("CALSCALE:GREGORIAN")
    lines.append("METHOD:PUBLISH")
    lines.append(f"X-WR-CALNAME:{escape_ics_text(CALNAME)}")
    lines.append("X-WR-TIMEZONE:Europe/Berlin")
    for ev in events:
        lines.extend(ev)
    lines.append("END:VCALENDAR")

    folded = [fold_ics_line(line) for line in lines]
    return "\r\n".join(folded) + "\r\n"


def main() -> None:
    weeks = iter_candidate_weeks()
    print(f"Prüfe {len(weeks)} Kalenderwochen: {weeks[0]} bis {weeks[-1]}")

    events: list[list[str]] = []
    legend_cache: dict[str, str] = {}
    found_weeks = 0

    for iso_year, iso_week in weeks:
        print(f"KW {iso_week}/{iso_year}:")
        pdf_bytes = fetch_pdf(iso_year, iso_week)
        if pdf_bytes is None:
            continue

        menus = parse_pdf_bytes(pdf_bytes)
        if not menus:
            print("  Warnung: Konnte keine Wochentage aus PDF extrahieren")
            continue

        legend = parse_allergen_legend(pdf_bytes)
        legend_cache.update(legend)
        found_weeks += 1

        for weekday_name, menu in menus.items():
            if menu.is_empty:
                continue
            iso_weekday = WEEKDAY_ISO[weekday_name]
            day = date.fromisocalendar(iso_year, iso_week, iso_weekday)
            events.append(build_event(day, menu, legend_cache))

    print(f"\n{found_weeks} Wochen mit Daten, {len(events)} Termine insgesamt")

    ics_content = build_ics(events)
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(ics_content)
    print(f"Geschrieben: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
