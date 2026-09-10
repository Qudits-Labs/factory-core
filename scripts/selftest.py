#!/usr/bin/env python3
"""Fuehrt die Pruefskripte gegen bekannte Fixtures aus.

Eine Pruefung, die nie an einem Verstoss gemessen wurde, ist eine Vermutung.
Dieses Skript stellt fest, dass jedes Pruefskript den sauberen Fall durchlaesst
und den verletzenden Fall abweist.

Aufruf:
    python3 scripts/selftest.py

Exit 0 heisst, alle Erwartungen sind eingetreten.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
SAUBER = WURZEL / "tests" / "fixtures" / "sauber"
VERSTOSS = WURZEL / "tests" / "fixtures" / "verstoss"

# (Pruefskript, Fixture-Verzeichnis, erwarteter Exit-Code, Beschreibung)
FAELLE = [
    (
        "check_workflow_triggers.py",
        SAUBER,
        0,
        "erlaubte Ausloeser werden durchgelassen",
    ),
    (
        "check_workflow_triggers.py",
        VERSTOSS,
        1,
        "pull_request_target wird abgewiesen, in beiden Schreibweisen",
    ),
    (
        "check_no_secrets.py",
        SAUBER,
        0,
        "ein im workflow_call deklariertes Secret ist zulaessig",
    ),
    (
        "check_no_secrets.py",
        VERSTOSS,
        1,
        "ein Secret in einem selbst ausgeloesten Workflow wird abgewiesen",
    ),
    # --- Gate-Skripte ---
    (
        "gate_story_lint.py",
        SAUBER / "story-lint",
        0,
        "vollstaendige Story besteht den Lint",
    ),
    (
        "gate_story_lint.py",
        VERSTOSS / "story-lint",
        1,
        "Story ohne Pflichtabschnitt und ohne Checkbox wird abgewiesen",
    ),
    (
        "gate_adr_check.py",
        SAUBER / "adr-check",
        0,
        "ADR mit allen Abschnitten und genuegend Alternativen besteht",
    ),
    (
        "gate_adr_check.py",
        VERSTOSS / "adr-check",
        1,
        "ADR mit zu wenigen Alternativen wird abgewiesen",
    ),
    (
        "gate_test_integrity.py",
        SAUBER / "test-integrity",
        0,
        "keine geschuetzte Datei geaendert -- Integritaet gewahrt",
    ),
    (
        "gate_test_integrity.py",
        VERSTOSS / "test-integrity",
        1,
        "geschuetzte Testdatei im Diff -- Integritaetsverstoss",
    ),
    (
        "gate_doc_check.py",
        SAUBER / "doc-check",
        0,
        "neuer Bezeichner steht in der zugeordneten Doku",
    ),
    (
        "gate_doc_check.py",
        VERSTOSS / "doc-check",
        1,
        "neuer Bezeichner fehlt in der Doku",
    ),
    (
        "gate_command_report.py",
        SAUBER / "command-check",
        0,
        "Befehl entspricht einem erlaubten Praefix",
    ),
    (
        "gate_command_report.py",
        VERSTOSS / "command-check",
        1,
        "Befehl ohne erlaubtes Praefix wird abgewiesen",
    ),
    (
        "gate_health_check.py",
        SAUBER / "health-check",
        0,
        "Lebendpruefung antwortet wie erwartet",
    ),
    (
        "gate_health_check.py",
        VERSTOSS / "health-check",
        1,
        "Lebendpruefung antwortet abweichend",
    ),
    (
        "check_workflow_struktur.py",
        SAUBER,
        0,
        "strukturell saubere Workflows -- kein Ausdruck in uses:, kein Reusable-als-Step",
    ),
    (
        "check_workflow_struktur.py",
        VERSTOSS,
        1,
        "Ausdruck in uses: und Reusable-Workflow-als-Step werden abgewiesen",
    ),
    (
        "check_durchgriff.py",
        SAUBER / "durchgriff",
        0,
        "der Aufrufer reicht jede gemeinsame und jede pflichtige Eingabe weiter",
    ),
    (
        "check_durchgriff.py",
        VERSTOSS / "durchgriff",
        1,
        "ein angebotener Regler ohne Durchgriff und ein nicht gefuehrtes"
        " Pflicht-Secret werden abgewiesen",
    ),
    (
        "transition_check.py",
        SAUBER / "transition-check",
        0,
        "berechtigte Uebergabe-Identitaet innerhalb der Versuchsgrenze",
    ),
    (
        "transition_check.py",
        VERSTOSS / "transition-check",
        1,
        "unbekannte Identitaet wird abgewiesen",
    ),
    (
        "transition_check.py",
        SAUBER / "transition-check-standard",
        0,
        "ohne uebergebene Tabelle gilt die Standardfolge des Kerns",
    ),
    (
        "transition_check.py",
        SAUBER / "transition-check-code-review",
        0,
        "Standardtabelle: status:code-review laesst den Adversary arbeiten",
    ),
    (
        "folgezustand.py",
        SAUBER / "folgezustand",
        0,
        "Standardfolge: auf status:spec folgt status:spec-review",
    ),
    (
        "folgezustand.py",
        SAUBER / "folgezustand-vor-code-review",
        0,
        "Standardfolge: auf status:ready-for-dev folgt status:code-review",
    ),
    (
        "folgezustand.py",
        SAUBER / "folgezustand-kettenende",
        0,
        "nach status:code-review kommt der Merge -- kein Folgezustand",
    ),
    (
        "folgezustand.py",
        SAUBER / "folgezustand-ersetzt",
        0,
        "eine uebergebene Tabelle ersetzt die Standardfolge",
    ),
    (
        "folgezustand.py",
        VERSTOSS / "folgezustand",
        1,
        "ein Zustand, der auf sich selbst zeigt, wird abgewiesen",
    ),
    (
        "pruefe_zugangsart.py",
        SAUBER / "zugangsart",
        0,
        "genau eine Zugangsart zum Modell gesetzt",
    ),
    (
        "pruefe_zugangsart.py",
        VERSTOSS / "zugangsart",
        1,
        "API-Schluessel und OAuth-Token gleichzeitig werden abgewiesen",
    ),
    (
        "pruefe_zugangsart.py",
        VERSTOSS / "zugangsart-keine",
        1,
        "gar keine Zugangsart wird abgewiesen",
    ),
]


def main() -> int:
    if not SAUBER.is_dir() or not VERSTOSS.is_dir():
        print("FEHLER: Fixture-Verzeichnisse fehlen.", file=sys.stderr)
        return 2

    fehler = 0
    for skript, verzeichnis, erwartet, beschreibung in FAELLE:
        lauf = subprocess.run(
            [sys.executable, str(WURZEL / "scripts" / skript), str(verzeichnis)],
            capture_output=True,
            text=True,
        )
        if lauf.returncode == erwartet:
            print(f"OK    {skript} auf {verzeichnis.name}: {beschreibung}")
        else:
            fehler += 1
            print(
                f"FEHLER {skript} auf {verzeichnis.name}: erwartet Exit "
                f"{erwartet}, erhalten {lauf.returncode}. {beschreibung}",
                file=sys.stderr,
            )
            if lauf.stdout:
                print(lauf.stdout, file=sys.stderr)
            if lauf.stderr:
                print(lauf.stderr, file=sys.stderr)

    if fehler:
        print(f"\n{fehler} von {len(FAELLE)} Faellen nicht wie erwartet.", file=sys.stderr)
        return 1

    print(f"\n{len(FAELLE)} Faelle geprueft, alle wie erwartet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
