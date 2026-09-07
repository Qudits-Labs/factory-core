#!/usr/bin/env python3
"""Prueft die strukturelle Substanz eines Architecture Decision Records (ADR).

Zweck:
    Verifiziert, dass ein ADR die Pflichtabschnitte enthaelt und mindestens N
    Alternativen mit erkennbarem Ausschlussgrund aufweist.

    Ausschlussgrund-Heuristik: Ein Listenpunkt gilt als begruendet, wenn er
    einen Doppelpunkt enthaelt ODER auf den Hauptsatz ein zweiter Satz mit
    Grossbuchstabe folgt. Diese Regel ist konfigurierbar ueber den Input
    `required_sections` und pruefbar in Fixtures.

Aufruf (Fixture-Modus fuer Tests):
    python3 scripts/gate_adr_check.py <fixture-verzeichnis>

    Das Verzeichnis muss enthalten:
      adr.md          - der zu pruefende ADR als Markdown
      config.txt      - optional, Schluessel=Wert-Paare:
                          required_sections=Kontext,Entscheidung,Alternativen,Betriebsfolgen,Status
                          min_alternatives=2

Aufruf (Produktiv via GitHub Actions):
    Liest aus Umgebungsvariablen:
      GATE_ADR_PATH            - Pfad zur ADR-Datei (bevorzugt)
      GATE_ADR_CONTENT         - Inhalt der ADR-Datei (Fallback)
      GATE_REQUIRED_SECTIONS   - komma-getrennt (optional)
      GATE_MIN_ALTERNATIVES    - ganzzahlig (optional, Default: 2)
    Schreibt Outputs in GITHUB_OUTPUT.

Exit-Codes:
    0 - Bestanden
    1 - Befund
    2 - Technischer Fehler
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

STANDARD_ABSCHNITTE = [
    "Kontext",
    "Entscheidung",
    "Alternativen",
    "Betriebsfolgen",
    "Status",
]
STANDARD_MIN_ALTERNATIVEN = 2

# Ausschlussgrund erkennbar durch Doppelpunkt oder zweiten Satz (Punkt + Grossbuchstabe).
AUSSCHLUSS_MUSTER = re.compile(r":|\.\s+[A-Z\xc4\xd6\xdc]")


def schreibe_ausgabe(schluessel: str, wert: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{schluessel}={wert}\n")
    else:
        print(f"  {schluessel}: {wert}")


def baue_befunde(titel: list[str]) -> list[dict]:
    """Formt Titelzeilen zu Befunden nach schemas/finding.schema.json.

    Ein maschinelles Gate traegt WARN, nie BLOCK. BLOCK verlangt spec_ref,
    location und reproduction; keine davon liegt hier vor, und erfundene
    Belege waeren schlimmer als der niedrigere Grad. Ueber den Halt
    entscheidet `pass`, nicht der Schweregrad des einzelnen Befunds.
    """
    befunde: list[dict] = []
    for nummer, text in enumerate(titel, start=1):
        gekuerzt = text if len(text) <= 200 else text[:197] + "..."
        befunde.append(
            {"id": f"F-{nummer:03d}", "severity": "WARN", "title": gekuerzt}
        )
    return befunde


def finde_abschnitt_inhalt(text: str, titel: str) -> str | None:
    """Gibt den Text eines Markdown-Abschnitts zurueck oder None."""
    muster = re.compile(
        rf"^#+\s+{re.escape(titel)}\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    treffer = muster.search(text)
    if not treffer:
        return None
    start = treffer.end()
    naechster = re.search(r"^#+\s", text[start:], re.MULTILINE)
    ende = start + naechster.start() if naechster else len(text)
    return text[start:ende].strip()


def zaehle_alternativen(inhalt: str) -> int:
    """Zaehlt Listenpunkte im Alternativen-Abschnitt mit Ausschlussgrund."""
    if not inhalt:
        return 0
    zaehler = 0
    for zeile in inhalt.splitlines():
        bereinigt = zeile.strip()
        if re.match(r"^[-*+]\s+|^\d+\.\s+", bereinigt):
            if AUSSCHLUSS_MUSTER.search(bereinigt):
                zaehler += 1
    return zaehler


def pruefe_adr(
    text: str,
    required_sections: list[str],
    min_alternatives: int,
) -> tuple[list[str], list[str], int]:
    """Gibt (befund_titel, fehlende_abschnitte, alternativen_anzahl) zurueck."""
    befunde: list[str] = []
    fehlende: list[str] = []

    for titel in required_sections:
        inhalt = finde_abschnitt_inhalt(text, titel)
        if inhalt is None:
            fehlende.append(titel)
            befunde.append(f"Pflichtabschnitt fehlt: {titel}")
        elif not inhalt:
            fehlende.append(titel)
            befunde.append(f"Pflichtabschnitt ist leer: {titel}")

    alt_inhalt = finde_abschnitt_inhalt(text, "Alternativen")
    alternativen_anzahl = 0
    if alt_inhalt is not None:
        alternativen_anzahl = zaehle_alternativen(alt_inhalt)
        if alternativen_anzahl < min_alternatives:
            befunde.append(
                f"Zu wenige Alternativen mit Ausschlussgrund: "
                f"{alternativen_anzahl} < {min_alternatives}"
            )

    return befunde, fehlende, alternativen_anzahl


def lade_fixture(verzeichnis: Path) -> tuple[str, list[str], int]:
    adr_datei = verzeichnis / "adr.md"
    config_datei = verzeichnis / "config.txt"

    if not adr_datei.exists():
        print(f"FEHLER: {adr_datei} fehlt", file=sys.stderr)
        raise SystemExit(2)

    text = adr_datei.read_text(encoding="utf-8")
    required_sections = list(STANDARD_ABSCHNITTE)
    min_alternatives = STANDARD_MIN_ALTERNATIVEN

    if config_datei.exists():
        for zeile in config_datei.read_text(encoding="utf-8").splitlines():
            if "=" in zeile:
                k, v = zeile.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "required_sections":
                    required_sections = [s.strip() for s in v.split(",") if s.strip()]
                elif k == "min_alternatives":
                    min_alternatives = int(v)

    return text, required_sections, min_alternatives


def main(argv: list[str]) -> int:
    if argv and Path(argv[0]).is_dir():
        try:
            text, required_sections, min_alternatives = lade_fixture(Path(argv[0]))
        except SystemExit:
            raise
        except ValueError as e:
            print(f"FEHLER: Ungueltige Fixture-Konfiguration: {e}", file=sys.stderr)
            return 2
    else:
        adr_pfad = os.environ.get("GATE_ADR_PATH", "")
        adr_inhalt = os.environ.get("GATE_ADR_CONTENT", "")
        if adr_pfad:
            try:
                text = Path(adr_pfad).read_text(encoding="utf-8")
            except OSError as e:
                print(f"FEHLER: {adr_pfad} nicht lesbar: {e}", file=sys.stderr)
                return 2
        elif adr_inhalt:
            text = adr_inhalt
        else:
            print(
                "FEHLER: Weder GATE_ADR_PATH noch GATE_ADR_CONTENT gesetzt",
                file=sys.stderr,
            )
            return 2

        sektionen_roh = os.environ.get("GATE_REQUIRED_SECTIONS", "")
        required_sections = (
            [s.strip() for s in sektionen_roh.split(",") if s.strip()]
            if sektionen_roh
            else list(STANDARD_ABSCHNITTE)
        )
        try:
            min_alternatives = int(
                os.environ.get("GATE_MIN_ALTERNATIVES", str(STANDARD_MIN_ALTERNATIVEN))
            )
        except ValueError:
            print(
                "FEHLER: GATE_MIN_ALTERNATIVES muss eine ganze Zahl sein",
                file=sys.stderr,
            )
            return 2

    titel, fehlende, alt_anzahl = pruefe_adr(text, required_sections, min_alternatives)
    bestanden = len(titel) == 0

    schreibe_ausgabe("pass", "true" if bestanden else "false")
    schreibe_ausgabe("missing_sections", json.dumps(fehlende))
    schreibe_ausgabe("alternatives_count", str(alt_anzahl))
    schreibe_ausgabe("findings_json", json.dumps(baue_befunde(titel)))

    if not bestanden:
        for t in titel:
            print(f"  BEFUND: {t}", file=sys.stderr)
        return 1

    print(
        f"ADR-Pruefung bestanden: {len(required_sections)} Abschnitte,"
        f" {alt_anzahl} Alternativen mit Ausschlussgrund."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
