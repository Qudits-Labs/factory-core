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
