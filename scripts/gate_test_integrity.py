#!/usr/bin/env python3
"""Prueft, ob geschuetzte Testpfade zwischen zwei Commits unveraendert blieben.

Zweck:
    Schuetzt Testdateien vor stillschweigender Anpassung. Sobald eine Datei
    unter einem der geschuetzten Glob-Muster im Diff erscheint, schlaegt
    dieses Gate an.

    Wichtig: Fehlt die Baseline oder ist sie unbekannt, endet der Workflow
    mit Fehler -- nie mit einem stillen PASS. Zwei Quellen fuer denselben
    Zustand laufen auseinander; der Issue-Kommentar bleibt die einzige Quelle.

Aufruf (Fixture-Modus fuer Tests):
    python3 scripts/gate_test_integrity.py <fixture-verzeichnis>

    Das Verzeichnis muss enthalten:
      baseline.txt      - Baseline-SHA (beliebiger String im Test)
      head.txt          - Head-SHA
      protected.txt     - zeilenweise Glob-Muster
      changed_files.txt - zeilenweise simulierter Git-Diff (geaenderte Pfade)

Aufruf (Produktiv via GitHub Actions):
    Liest aus Umgebungsvariablen:
      GATE_BASELINE_SHA      - erforderlich
      GATE_HEAD_SHA          - erforderlich
      GATE_PROTECTED_PATHS   - komma-getrennte Glob-Muster
    Fuehrt `git diff --name-only <baseline> <head>` aus.

Exit-Codes:
    0 - Keine geschuetzten Dateien geaendert
    1 - Mindestens eine geschuetzte Datei geaendert
    2 - Technischer Fehler (fehlende Eingaben, Git-Fehler)
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path


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


def passt_auf_muster(dateipfad: str, muster_liste: list[str]) -> bool:
    return any(fnmatch.fnmatch(dateipfad, m) for m in muster_liste)


def hole_geaenderte_dateien(baseline: str, head: str) -> list[str]:
    lauf = subprocess.run(
        ["git", "diff", "--name-only", baseline, head],
        capture_output=True,
        text=True,
    )
    if lauf.returncode != 0:
        print(f"FEHLER: git diff schlug fehl: {lauf.stderr}", file=sys.stderr)
        raise SystemExit(2)
    return [z.strip() for z in lauf.stdout.splitlines() if z.strip()]


def lade_fixture(verzeichnis: Path) -> tuple[str, str, list[str], list[str]]:
    erforderlich = ["baseline.txt", "head.txt", "protected.txt", "changed_files.txt"]
    inhalte: dict[str, str] = {}
    for name in erforderlich:
        pfad = verzeichnis / name
        if not pfad.exists():
            print(f"FEHLER: {pfad} fehlt", file=sys.stderr)
            raise SystemExit(2)
        inhalte[name] = pfad.read_text(encoding="utf-8").strip()

    baseline = inhalte["baseline.txt"]
    head = inhalte["head.txt"]
    protected = [
        z.strip() for z in inhalte["protected.txt"].splitlines() if z.strip()
    ]
    changed = [
        z.strip() for z in inhalte["changed_files.txt"].splitlines() if z.strip()
    ]
    return baseline, head, protected, changed


def main(argv: list[str]) -> int:
    if argv and Path(argv[0]).is_dir():
        try:
            baseline, head, protected, changed = lade_fixture(Path(argv[0]))
        except SystemExit:
            raise
    else:
        baseline = os.environ.get("GATE_BASELINE_SHA", "")
        head = os.environ.get("GATE_HEAD_SHA", "")
        protected_roh = os.environ.get("GATE_PROTECTED_PATHS", "")
        protected = [p.strip() for p in protected_roh.split(",") if p.strip()]

        if not baseline:
            print(
                "FEHLER: GATE_BASELINE_SHA fehlt. Eine unbekannte Baseline"
                " ist ein Fehler, kein PASS -- zwei Quellen fuer denselben"
                " Zustand laufen auseinander.",
                file=sys.stderr,
            )
            return 2
        if not head:
            print("FEHLER: GATE_HEAD_SHA fehlt", file=sys.stderr)
            return 2
        if not protected:
            print("FEHLER: GATE_PROTECTED_PATHS fehlt oder leer", file=sys.stderr)
            return 2

        try:
            changed = hole_geaenderte_dateien(baseline, head)
        except SystemExit:
            raise

    verletzungen = [f for f in changed if passt_auf_muster(f, protected)]
    titel = [f"Geschuetzte Datei geaendert: {v}" for v in verletzungen]

    schreibe_ausgabe("pass", "true" if not verletzungen else "false")
    schreibe_ausgabe("changed_files", json.dumps(changed))
    schreibe_ausgabe("findings_json", json.dumps(baue_befunde(titel)))

    if verletzungen:
        for t in titel:
            print(f"  BEFUND: {t}", file=sys.stderr)
        return 1

    print(
        f"Integritaetspruefung bestanden. {len(changed)} Datei(en)"
        " geaendert, keine unter geschuetzten Mustern."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
