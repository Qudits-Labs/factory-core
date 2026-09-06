#!/usr/bin/env python3
"""Prueft strukturelle Reife einer User Story oder eines Issues.

Zweck:
    Verifiziert rein mechanisch, ob ein Issue-Body die Pflichtabschnitte
    enthaelt, mindestens eine Akzeptanzkriterien-Checkbox aufweist, einen
    Nutzenmarker besitzt und die verlangten Label-Praefixe abdeckt.
    Keine semantische Bewertung.

Aufruf (Fixture-Modus fuer Tests):
    python3 scripts/gate_story_lint.py <fixture-verzeichnis>

    Das Verzeichnis muss enthalten:
      issue_body.txt   - Inhalt des Issue-Body
      labels.txt       - Komma-getrennte Labels (eine Zeile)
      config.txt       - optional, Schluessel=Wert-Paare:
                           required_label_prefixes=profile:,status:
                           nutzen_marker_required=true

Aufruf (Produktiv via GitHub Actions):
    Liest aus Umgebungsvariablen:
      GATE_ISSUE_BODY
      GATE_ISSUE_LABELS               (komma-getrennt)
      GATE_REQUIRED_LABEL_PREFIXES    (komma-getrennt, optional)
      GATE_NUTZEN_REQUIRED            (true/false, Default: true)
    Schreibt Outputs in die Datei, auf die GITHUB_OUTPUT zeigt.

Exit-Codes:
    0 - Alle Pruefungen bestanden
    1 - Mindestens ein Befund (FAIL)
    2 - Technischer Fehler
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PFLICHTABSCHNITTE = [
    "## Kontext",
    "## Ziel",
    "## Akzeptanzkriterien",
]
CHECKBOX_MUSTER = re.compile(r"^- \[[ xX]\]", re.MULTILINE)
NUTZEN_MUSTER = re.compile(r"<!--\s*nutzen:\s*(.+?)\s*-->", re.DOTALL)


def schreibe_ausgabe(schluessel: str, wert: str) -> None:
    """Schreibt key=value in GITHUB_OUTPUT wenn gesetzt, sonst nach stdout."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{schluessel}={wert}\n")
    else:
        print(f"  {schluessel}: {wert}")


def pruefe_body(
    body: str,
    labels: list[str],
    required_label_prefixes: list[str],
    nutzen_required: bool,
) -> list[str]:
    """Gibt eine Liste von Befund-Strings zurueck. Leer bedeutet bestanden."""
    befunde: list[str] = []

    for abschnitt in PFLICHTABSCHNITTE:
        idx = body.lower().find(abschnitt.lower())
        if idx == -1:
            befunde.append(f"Pflichtabschnitt fehlt: {abschnitt}")
            continue
        rest = body[idx + len(abschnitt):]
        naechster = re.search(r"\n##", rest)
        inhalt = rest[: naechster.start()] if naechster else rest
        if not inhalt.strip():
            befunde.append(f"Pflichtabschnitt ist leer: {abschnitt}")

    if not CHECKBOX_MUSTER.search(body):
        befunde.append(
            "Keine Akzeptanzkriterien-Checkbox gefunden (- [ ] oder - [x])"
        )

    if nutzen_required:
        treffer = NUTZEN_MUSTER.search(body)
        if not treffer:
            befunde.append("Nutzenmarker fehlt (<!-- nutzen: ... -->)")
        elif not treffer.group(1).strip():
            befunde.append(
                "Nutzenmarker ist leer (<!-- nutzen: ... --> ohne Inhalt)"
            )

    for praefix in required_label_prefixes:
        if not any(lbl.startswith(praefix) for lbl in labels):
            befunde.append(f"Kein Label mit Praefix '{praefix}' gefunden")

    return befunde


def lade_fixture(
    verzeichnis: Path,
) -> tuple[str, list[str], list[str], bool]:
    body_datei = verzeichnis / "issue_body.txt"
    labels_datei = verzeichnis / "labels.txt"
    config_datei = verzeichnis / "config.txt"

    if not body_datei.exists():
        print(f"FEHLER: {body_datei} fehlt", file=sys.stderr)
        raise SystemExit(2)

    body = body_datei.read_text(encoding="utf-8")
    labels: list[str] = []
    if labels_datei.exists():
        labels = [
            lbl.strip()
            for lbl in labels_datei.read_text(encoding="utf-8").split(",")
            if lbl.strip()
        ]

    required_label_prefixes: list[str] = []
    nutzen_required = True
    if config_datei.exists():
        for zeile in config_datei.read_text(encoding="utf-8").splitlines():
            if "=" in zeile:
                schluessel, wert = zeile.split("=", 1)
                k = schluessel.strip()
                v = wert.strip()
                if k == "required_label_prefixes":
                    required_label_prefixes = [
                        p.strip() for p in v.split(",") if p.strip()
                    ]
                elif k == "nutzen_marker_required":
                    nutzen_required = v.lower() not in ("false", "0", "no")

    return body, labels, required_label_prefixes, nutzen_required


def main(argv: list[str]) -> int:
    if argv and Path(argv[0]).is_dir():
        try:
            body, labels, required_label_prefixes, nutzen_required = (
                lade_fixture(Path(argv[0]))
            )
        except SystemExit:
            raise
    else:
        body = os.environ.get("GATE_ISSUE_BODY", "")
        labels_roh = os.environ.get("GATE_ISSUE_LABELS", "")
        labels = [lbl.strip() for lbl in labels_roh.split(",") if lbl.strip()]
        praefixe_roh = os.environ.get("GATE_REQUIRED_LABEL_PREFIXES", "")
        required_label_prefixes = [
            p.strip() for p in praefixe_roh.split(",") if p.strip()
        ]
        nutzen_required = (
            os.environ.get("GATE_NUTZEN_REQUIRED", "true").lower()
            not in ("false", "0", "no")
        )

        if not body:
            print("FEHLER: GATE_ISSUE_BODY nicht gesetzt", file=sys.stderr)
            return 2

    befunde = pruefe_body(body, labels, required_label_prefixes, nutzen_required)
    bestanden = len(befunde) == 0

    schreibe_ausgabe("pass", "true" if bestanden else "false")
    schreibe_ausgabe("findings_json", json.dumps(befunde))

    if not bestanden:
        for b in befunde:
            print(f"  BEFUND: {b}", file=sys.stderr)
        print(
            f"\n{len(befunde)} Befund(e). Story nicht bereit.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Story-Lint bestanden: {len(PFLICHTABSCHNITTE)} Abschnitte,"
        " Checkboxen, Nutzenmarker."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
