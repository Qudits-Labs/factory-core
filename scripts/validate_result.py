#!/usr/bin/env python3
"""Validiert .factory/result.json gegen result.schema.json.

Zweck:
    Prueft, ob die vom Agenten erzeugte Ergebnisdatei dem Schema entspricht.
    result.schema.json verweist relativ auf finding.schema.json; dieser Verweis
    wird ueber eine referencing.Registry aufgeloest und nicht ueber das Netz,
    damit die Pruefung nicht von der Erreichbarkeit einer Adresse abhaengt.

    Das Muster fuer die Registry stammt aus validate_schemas.py::lade_registry
    und wird dort importiert, um keine zweite Kopie zu halten.

Aufruf:
    python3 scripts/validate_result.py <pfad-zu-result.json>
    python3 scripts/validate_result.py <verzeichnis>

    Wird ein Verzeichnis uebergeben, liest das Skript dort result.json.

Ausgaben:
    Schreibt `schema_valid=true|false` nach GITHUB_OUTPUT, wenn die Variable
    gesetzt ist.

Exit-Codes:
    0 - Datei vorhanden, gueltiges JSON und dem Schema entsprechend
    1 - Datei fehlt, kein gueltiges JSON oder Schema-Verletzung
    2 - Technischer Fehler (Abhaengigkeit fehlt, Schema fehlt)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Skript-Verzeichnis dem Suchpfad hinzufuegen, damit factory_phasen und
# validate_schemas unabhaengig vom Aufrufverzeichnis importierbar sind.
_SKRIPT_DIR = Path(__file__).resolve().parent
if str(_SKRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SKRIPT_DIR))

try:
    from validate_schemas import lade_registry  # type: ignore[import]
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError as _fehler:
    print(
        f"FEHLER: Abhaengigkeit fehlt ({_fehler})."
        " Installation: pip install jsonschema referencing",
        file=sys.stderr,
    )
    raise SystemExit(2)

_WURZEL = Path(__file__).resolve().parent.parent
_SCHEMAS = _WURZEL / "schemas"


def schreibe_ausgabe(schluessel: str, wert: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{schluessel}={wert}\n")


def main(argv: list[str]) -> int:
    if not argv:
        print(
            "FEHLER: Kein Pfad uebergeben."
            " Aufruf: python3 scripts/validate_result.py <pfad-oder-verzeichnis>",
            file=sys.stderr,
        )
        return 2

    ziel = Path(argv[0])
    if ziel.is_dir():
        ergebnis_datei = ziel / "result.json"
    else:
        ergebnis_datei = ziel

    schema_datei = _SCHEMAS / "result.schema.json"
    if not schema_datei.exists():
        print(
            f"FEHLER: Schema {schema_datei} nicht gefunden.",
            file=sys.stderr,
        )
        schreibe_ausgabe("schema_valid", "false")
        return 2

    if not ergebnis_datei.exists():
        print(
            f"FEHLER: {ergebnis_datei} fehlt.",
            file=sys.stderr,
        )
        schreibe_ausgabe("schema_valid", "false")
        return 1

    try:
        inhalt = json.loads(ergebnis_datei.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(
            f"FEHLER: {ergebnis_datei} ist kein gueltiges JSON: {e}",
            file=sys.stderr,
        )
        schreibe_ausgabe("schema_valid", "false")
        return 1

    try:
        registry = lade_registry()
        schema = json.loads(schema_datei.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, registry=registry)
        validator.validate(inhalt)
    except ValidationError as e:
        print(
            f"FEHLER: {ergebnis_datei} entspricht nicht dem Schema: {e.message}",
            file=sys.stderr,
        )
        schreibe_ausgabe("schema_valid", "false")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"FEHLER: Technischer Fehler bei der Validierung: {e}", file=sys.stderr)
        schreibe_ausgabe("schema_valid", "false")
        return 2

    schreibe_ausgabe("schema_valid", "true")
    print(f"{ergebnis_datei} entspricht dem Schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
