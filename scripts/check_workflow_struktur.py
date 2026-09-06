#!/usr/bin/env python3
"""Prueft Workflow-Dateien auf strukturelle Defekte.

GitHub wertet in `uses:`-Werten keine Ausdrücke aus und lädt eine
Workflow-Datei deshalb gar nicht erst, wenn dort `${{...}}` steht.
Außerdem ist ein wiederverwendbarer Workflow nur auf Job-Ebene einbindbar,
nicht als Step innerhalb eines Jobs.

Geprüft wird je Workflow-Datei:

* kein `uses:`-Wert enthält `${{`
* kein Step führt den Schlüssel `secrets:`
* kein Step-`uses:` zeigt auf einen lokalen Workflow-Pfad
  (`./.github/workflows/*.yml` oder `.yaml`)
* ein Job mit `uses:` hat weder `steps:` noch `runs-on:`
* ein Job ohne `uses:` hat `runs-on:`

Aufruf:
    python3 scripts/check_workflow_struktur.py [pfad ...]

Ohne Argument wird `.github/workflows` geprueft. Exit 0 sauber,
Exit 1 Fund, Exit 2 technischer Fehler (Datei nicht lesbar).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FEHLER: PyYAML fehlt. Installation: pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)

ENDUNGEN = {".yml", ".yaml"}

# Passt auf `./.github/workflows/<dateiname>.yml` bzw. `.yaml`.
# Tiefer verschachtelte Pfade (Unterordner) sind in GitHub-Workflows nicht
# üblich; das Muster bleibt bewusst flach, um Falschtreffer zu vermeiden.
_LOKALER_WORKFLOW = re.compile(r"^\./\.github/workflows/[^/]+\.ya?ml$")


def workflow_dateien(pfade: list[str]) -> list[Path]:
    if not pfade:
        pfade = [".github/workflows"]
    gefunden: list[Path] = []
    for eintrag in pfade:
        p = Path(eintrag)
        if p.is_dir():
            gefunden.extend(sorted(k for k in p.rglob("*") if k.suffix in ENDUNGEN))
        elif p.is_file():
            gefunden.append(p)
    return gefunden


def _prüfe_datei(datei: Path, dokument: object) -> list[str]:
    """Gibt Verstossbeschreibungen für eine Workflow-Datei zurück."""
    funde: list[str] = []

    if not isinstance(dokument, dict):
        return funde

    jobs = dokument.get("jobs")
    if not isinstance(jobs, dict):
        return funde

    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue

        hat_uses = "uses" in job
        hat_steps = "steps" in job
        hat_runs_on = "runs-on" in job
        job_uses_wert = job.get("uses")

        # Ausdruck in Job-uses
        if isinstance(job_uses_wert, str) and "${{" in job_uses_wert:
            funde.append(
                f"{datei}: Job '{job_id}': uses: enthält einen Ausdruck "
                "('${{...}}') — GitHub wertet dort keine Ausdrücke aus"
            )

        # Ein Job mit uses: darf weder steps: noch runs-on: haben
        if hat_uses and hat_steps:
            funde.append(
                f"{datei}: Job '{job_id}': hat 'uses:' und 'steps:' "
                "— ein wiederverwendbarer Workflow ist nur auf Job-Ebene "
                "aufrufbar, nicht als Step innerhalb eines Jobs"
            )
        if hat_uses and hat_runs_on:
            funde.append(
                f"{datei}: Job '{job_id}': hat 'uses:' und 'runs-on:' "
                "— ein Job mit 'uses:' braucht kein 'runs-on:'"
            )

        # Ein Job ohne uses: braucht runs-on:
        if not hat_uses and not hat_runs_on:
            funde.append(
                f"{datei}: Job '{job_id}': hat weder 'uses:' noch 'runs-on:'"
            )

        # Steps prüfen
        schritte = job.get("steps")
        if not isinstance(schritte, list):
            continue

        for idx, schritt in enumerate(schritte):
            if not isinstance(schritt, dict):
                continue

            schritt_name = schritt.get("name") or f"Schritt {idx + 1}"
            step_uses = schritt.get("uses")

            # Ausdruck in Step-uses
            if isinstance(step_uses, str) and "${{" in step_uses:
                funde.append(
                    f"{datei}: Job '{job_id}', '{schritt_name}': "
                    "uses: enthält einen Ausdruck ('${{...}}') "
                    "— GitHub wertet dort keine Ausdrücke aus"
                )

            # Step-uses zeigt auf einen lokalen Workflow-Pfad
            if isinstance(step_uses, str) and _LOKALER_WORKFLOW.match(step_uses):
                funde.append(
                    f"{datei}: Job '{job_id}', '{schritt_name}': "
                    f"uses: '{step_uses}' — wiederverwendbare Workflows "
                    "sind nur auf Job-Ebene einbindbar, nicht als Step"
                )

            # Step hat secrets: (Schlüssel ist nur auf Job-Ebene gültig)
            if "secrets" in schritt:
                funde.append(
                    f"{datei}: Job '{job_id}', '{schritt_name}': "
                    "Step enthält 'secrets:' — dieser Schlüssel ist "
                    "nur auf Job-Ebene gültig"
                )

    return funde


def main(argv: list[str]) -> int:
    dateien = workflow_dateien(argv)
    if not dateien:
        print("Keine Workflow-Datei gefunden. Nichts zu prüfen.")
        return 0

    funde: list[str] = []
    for datei in dateien:
        try:
            inhalt = yaml.safe_load(datei.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as fehler:
            print(f"FEHLER: {datei} nicht lesbar: {fehler}", file=sys.stderr)
            return 2
        funde.extend(_prüfe_datei(datei, inhalt))

    for zeile in funde:
        print(zeile, file=sys.stderr)

    if funde:
        print(
            f"\n{len(funde)} Verstoss/Verstoesse in {len(dateien)} geprueften Dateien.\n"
            "GitHub lehnt Workflows mit Ausdrücken in 'uses:' stillschweigend ab. "
            "Wiederverwendbare Workflows gehören auf Job-Ebene (jobs.<id>.uses), "
            "nicht in steps.",
            file=sys.stderr,
        )
        return 1

    print(f"{len(dateien)} Workflow-Datei(en) geprueft, keine strukturellen Defekte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
