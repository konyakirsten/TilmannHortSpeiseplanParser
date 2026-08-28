"""
Parser für die Tilemann-Hort Speiseplan-PDFs.

Das PDF-Layout ist zweispaltig (Wochentag links, Gerichte/Allergene rechts
daneben, plus eine separate Zusatzstoff-/Allergenlegende ganz rechts).
Normale Textextraktion (Lesereihenfolge des PDF-Content-Streams) zerstört
diese Zuordnung komplett - deshalb wird hier positionsbasiert (x/y-Koordinaten
der Wörter) gearbeitet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pdfplumber

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]

# Spaltengrenzen (kalibriert an den vorliegenden Speiseplan-PDFs).
# x0 < DAY_LABEL_MAX_X   -> Wochentags-Label (linke Randspalte)
# DAY_LABEL_MAX_X..LEGEND_MIN_X -> Gerichte-/enthält-Spalte
# x0 >= LEGEND_MIN_X     -> Zusatzstoffe-/Allergene-Legende (ignorieren)
DAY_LABEL_MAX_X = 120
LEGEND_MIN_X = 370
HEADER_MIN_TOP = 180  # alles oberhalb ist Kopfzeile (Titel, "vom ...")

LINE_TOLERANCE = 3.0  # Wörter mit fast gleichem "top" gelten als eine Zeile

ENTHAELT_RE = re.compile(r"enthält:?\s*(?P<codes>[a-zA-Z,]*)", re.IGNORECASE)


@dataclass
class DayMenu:
    weekday: str
    lines: list[str] = field(default_factory=list)
    allergen_codes: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.lines


def _group_into_lines(words: list[dict]) -> list[tuple[float, str]]:
    """Gruppiert Wörter mit fast identischem 'top' zu Zeilen und sortiert
    sie innerhalb der Zeile nach x-Position. Gibt (top, text) zurück."""
    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict]] = []
    for w in words:
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= LINE_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [
        (line[0]["top"], " ".join(w["text"] for w in line))
        for line in lines
    ]


def parse_pdf_bytes(pdf_bytes: bytes) -> dict[str, DayMenu]:
    """Parst ein Speiseplan-PDF und liefert ein Mapping Wochentag -> DayMenu.
    Wochentage ohne Eintrag im PDF fehlen im Ergebnis-Dict."""
    import io

    result: dict[str, DayMenu] = {}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        words = [w for w in words if w["top"] >= HEADER_MIN_TOP]

        day_labels = sorted(
            (w for w in words if w["x0"] < DAY_LABEL_MAX_X and w["text"] in WEEKDAYS),
            key=lambda w: w["top"],
        )
        if not day_labels:
            return result

        content_words = [
            w for w in words if DAY_LABEL_MAX_X <= w["x0"] < LEGEND_MIN_X
        ]

        for i, label in enumerate(day_labels):
            band_top = label["top"]
            band_bottom = (
                day_labels[i + 1]["top"] if i + 1 < len(day_labels) else float("inf")
            )
            band_words = [
                w for w in content_words if band_top - 1 <= w["top"] < band_bottom - 1
            ]
            lines = _group_into_lines(band_words)

            menu = DayMenu(weekday=label["text"])
            for _, text in lines:
                m = ENTHAELT_RE.match(text)
                if m:
                    codes = m.group("codes")
                    menu.allergen_codes = [c.strip() for c in codes.split(",") if c.strip()]
                elif text.strip():
                    menu.lines.append(text.strip())

            result[menu.weekday] = menu

    return result


def parse_allergen_legend(pdf_bytes: bytes) -> dict[str, str]:
    """Extrahiert die Allergen-Codes -> Klartext-Legende (rechte Spalte,
    Abschnitt 'ALLERGENE'). Zusatzstoffe (1-22) werden ignoriert, da die
    'enthält'-Angaben im Speiseplan nur Buchstaben-Allergene referenzieren."""
    import io

    legend: dict[str, str] = {}
    code_re = re.compile(r"^[a-z]:$", re.IGNORECASE)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        legend_words = [w for w in words if w["x0"] >= LEGEND_MIN_X and w["top"] >= HEADER_MIN_TOP]
        lines = _group_into_lines(legend_words)

        started = False
        for _, text in lines:
            if text.strip().upper() == "ALLERGENE":
                started = True
                continue
            if not started:
                continue
            m = re.match(r"^([a-zA-Z]):\s*(.+)$", text.strip())
            if m:
                legend[m.group(1).lower()] = m.group(2).strip()

    return legend
