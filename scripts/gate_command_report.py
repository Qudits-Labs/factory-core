#!/usr/bin/env python3
"""Validiert einen Befehl gegen erlaubte Praefixe und schreibt einen Bericht.

Zweck:
    Prueft, ob ein Befehl mit einem der erlaubten Praefixe beginnt, bevor er
    im gate-command.yml-Workflow ausgefuehrt wird. Die eigentliche
    Ausfuehrungs-Absicherung liegt im Schreibschutz auf der
    Konfigurationsdatei im Produktrepo -- dieses Gate macht die Luecke
    sichtbar, wenn keine Beschraenkung aktiv ist.

    Ist `allowed_command_prefixes` leer, laeuft der Befehl, und der Workflow
    schreibt eine sichtbare Warnung in die Job-Zusammenfassung.

    Sicherheitsauflage: Der Befehl wird nie als Shell-String interpoliert.
    Er kommt ausschliesslich ueber eine Umgebungsvariable.

Aufruf (Fixture-Modus fuer Tests):
    python3 scripts/gate_command_report.py <fixture-verzeichnis>

    Das Verzeichnis muss enthalten:
      command.txt    - der zu pruefende Befehl (eine Zeile)
      prefixes.txt   - zeilenweise erlaubte Praefixe (leer = keine Einschraenkung)

Aufruf (Produktiv via GitHub Actions):
    Liest aus Umgebungsvariablen:
      GATE_COMMAND                   - der Befehl (erforderlich)
      GATE_ALLOWED_COMMAND_PREFIXES  - komma-getrennte Praefixe (optional)
    Schreibt Outputs in GITHUB_OUTPUT.

Exit-Codes:
    0 - Befehl ist erlaubt (oder keine Einschraenkung aktiv)
    1 - Befehl entspricht keinem erlaubten Praefix
    2 - Technischer Fehler
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def schreibe_ausgabe(schluessel: str, wert: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{schluessel}={wert}\n")
    else:
        print(f"  {schluessel}: {wert}")


def pruefe_praefixe(befehl: str, praefixe: list[str]) -> tuple[bool, str, str]:
    """Gibt (erlaubt, meldung, warnung) zurueck."""
    if not praefixe:
        warnung = (
            "Keine Befehlsbeschraenkung aktiv. Der Befehl laeuft ohne"
            " Praefix-Filter. Die eigentliche Absicherung ist der"
            " Schreibschutz auf der Konfigurationsdatei im Produktrepo"
            " -- dieses Gate macht die Luecke sichtbar."
        )
        return True, "Befehl zugelassen (keine Praefixe konfiguriert)", warnung

    for praefix in praefixe:
        if befehl.startswith(praefix):
            return True, f"Befehl entspricht erlaubtem Praefix: {praefix!r}", ""

    meldung = (
        f"Befehl entspricht keinem erlaubten Praefix."
        f" Befehl beginnt mit: {befehl.split()[0]!r}"
        f" -- erlaubt: {', '.join(repr(p) for p in praefixe)}"
    )
    return False, meldung, ""


def lade_fixture(verzeichnis: Path) -> tuple[str, list[str]]:
    cmd_datei = verzeichnis / "command.txt"
    praefixe_datei = verzeichnis / "prefixes.txt"

    if not cmd_datei.exists():
        print(f"FEHLER: {cmd_datei} fehlt", file=sys.stderr)
        raise SystemExit(2)

    befehl = cmd_datei.read_text(encoding="utf-8").strip()
    praefixe: list[str] = []
    if praefixe_datei.exists():
        praefixe = [
            z.strip()
            for z in praefixe_datei.read_text(encoding="utf-8").splitlines()
            if z.strip()
        ]

    return befehl, praefixe


def main(argv: list[str]) -> int:
    if argv and Path(argv[0]).is_dir():
        try:
            befehl, praefixe = lade_fixture(Path(argv[0]))
        except SystemExit:
            raise
    else:
        befehl = os.environ.get("GATE_COMMAND", "")
        praefixe_roh = os.environ.get("GATE_ALLOWED_COMMAND_PREFIXES", "")
        praefixe = [p.strip() for p in praefixe_roh.split(",") if p.strip()]

        if not befehl:
            print("FEHLER: GATE_COMMAND nicht gesetzt", file=sys.stderr)
            return 2

    erlaubt, meldung, warnung = pruefe_praefixe(befehl, praefixe)

    schreibe_ausgabe("allowed", "true" if erlaubt else "false")
    if warnung:
        schreibe_ausgabe("warning", warnung)
        # Warnung in die Job-Zusammenfassung
        github_step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if github_step_summary:
            with open(github_step_summary, "a", encoding="utf-8") as f:
                f.write(f"## Warnung: Befehlsbeschraenkung\n\n{warnung}\n")
        print(f"WARNUNG: {warnung}")

    print(meldung)

    if not erlaubt:
        print(meldung, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
