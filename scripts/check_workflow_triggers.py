#!/usr/bin/env python3
"""Prueft Workflow-Dateien auf verbotene Ausloeser.

Verboten ist `pull_request_target`. Dieser Ausloeser fuehrt den Workflow im
Kontext des Basis-Repositoriums aus, also mit dessen Schreibtoken und dessen
Secrets, wertet dabei aber den Code aus dem fremden Pull Request aus. In einem
oeffentlichen Repository ist das der Weg, ueber den fremder Code mit eigenen
Rechten laeuft.

Aufruf:
    python3 scripts/check_workflow_triggers.py [pfad ...]

Ohne Argument wird `.github/workflows` geprueft. Exit 0 heisst sauber,
Exit 1 heisst Fund, Exit 2 heisst, dass eine Datei nicht lesbar war.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FEHLER: PyYAML fehlt. Installation: pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)

VERBOTENE_AUSLOESER = {"pull_request_target"}
ENDUNGEN = {".yml", ".yaml"}


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


def ausloeser_von(dokument: object) -> set[str]:
    """Liest die Ausloeser aus dem `on`-Block.

    PyYAML liest das unquotierte `on` nach YAML 1.1 als booleschen Wert True.
    Beide Schluessel werden deshalb geprueft.
    """
    if not isinstance(dokument, dict):
        return set()
    block = dokument.get("on", dokument.get(True))
    if isinstance(block, str):
        return {block}
    if isinstance(block, list):
        return {e for e in block if isinstance(e, str)}
    if isinstance(block, dict):
        return {k for k in block if isinstance(k, str)}
    return set()


def main(argv: list[str]) -> int:
    dateien = workflow_dateien(argv)
    if not dateien:
        print("Keine Workflow-Datei gefunden. Nichts zu pruefen.")
        return 0

    funde: list[str] = []
    for datei in dateien:
        try:
            inhalt = yaml.safe_load(datei.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as fehler:
            print(f"FEHLER: {datei} nicht lesbar: {fehler}", file=sys.stderr)
            return 2
        treffer = ausloeser_von(inhalt) & VERBOTENE_AUSLOESER
        for t in sorted(treffer):
            funde.append(f"{datei}: verbotener Ausloeser `{t}`")

    for zeile in funde:
        print(zeile, file=sys.stderr)

    if funde:
        print(
            f"\n{len(funde)} Verstoss/Verstoesse in {len(dateien)} geprueften Dateien.\n"
            "`pull_request_target` fuehrt fremden Code mit den Rechten des "
            "Basis-Repositoriums aus. Verwende `pull_request`.",
            file=sys.stderr,
        )
        return 1

    print(f"{len(dateien)} Workflow-Datei(en) geprueft, kein verbotener Ausloeser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
