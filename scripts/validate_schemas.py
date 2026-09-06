#!/usr/bin/env python3
"""Prüft die Schemas selbst und die Beispieldateien gegen sie.

Drei Fragen werden beantwortet:

1. Ist jedes Schema gültiges JSON und ein gültiges JSON Schema?
2. Bestehen die Beispieldateien unter `example/` das Schema, das für sie gilt?
3. Greifen die Bedingungen in `result.schema.json` tatsächlich? Ein Schema, das
   einen widersprüchlichen Fall durchlässt, sieht aus wie eine Zusicherung und
   ist keine. Deshalb wird es an vier Fällen gemessen, von denen drei
   durchfallen müssen.

Der Verweis von `result.schema.json` auf `finding.schema.json` ist relativ. Er
wird hier aus dem Dateisystem aufgelöst und nicht über das Netz, damit die
Prüfung nicht von der Erreichbarkeit einer Adresse abhängt.

Aufruf:
    python3 scripts/validate_schemas.py

Exit 0 sauber, 1 Befund, 2 technischer Fehler.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError as fehler:  # pragma: no cover
    print(
        f"FEHLER: Abhängigkeit fehlt ({fehler}). "
        "Installation: pip install jsonschema pyyaml referencing",
        file=sys.stderr,
    )
    raise SystemExit(2)

WURZEL = Path(__file__).resolve().parent.parent
SCHEMAS = WURZEL / "schemas"

# Beispieldatei zu dem Schema, das für sie gilt.
BEISPIELE = [
    ("example/.factory/gate-config.example.yml", "gate-config.schema.json"),
    ("example/.factory/doc-map.example.yml", "doc-map.schema.json"),
]


def lade_registry() -> Registry:
    """Macht alle Schemas unter ihrem Dateinamen auflösbar."""
    registry = Registry()
    for datei in sorted(SCHEMAS.glob("*.json")):
        inhalt = json.loads(datei.read_text(encoding="utf-8"))
        ressource = Resource.from_contents(inhalt)
        registry = registry.with_resource(uri=datei.name, resource=ressource)
        if "$id" in inhalt:
            registry = registry.with_resource(uri=inhalt["$id"], resource=ressource)
    return registry


def validator_fuer(name: str, registry: Registry) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=registry)


def basis_ergebnis() -> dict:
    """Ein gültiges Ergebnis, das die Grundlage der Gegenproben bildet."""
    return {
        "schema_version": "1.0",
        "role": "adversary",
        "attempt": 2,
        "run_id": "1234567890",
        "commit_sha": None,
        "timestamp_utc": "2026-01-01T12:00:00Z",
        "status": "failed",
        "verdict": "FAIL",
        "artefakte": [{"typ": "review", "pfad": "docs/specs/SPEC-001.md"}],
        "findings": [
            {
                "id": "F-001",
                "severity": "BLOCK",
                "title": "Kriterium ohne messbare Bedingung",
                "spec_ref": {
                    "document": "docs/specs/SPEC-001.md",
                    "section": "Akzeptanzkriterien",
                    "criterion_id": "AK-03",
                },
                "location": {
                    "file": None,
                    "line": None,
                    "note": "Betrifft das Dokument, nicht den Code",
                },
                "reproduction": (
                    "Das Kriterium nennt keinen Schwellwert. Kein Testfall kann "
                    "die Bedingung ohne zusätzliche Annahme prüfen."
                ),
            }
        ],
        "begruendung": "Ein Kriterium ohne messbare Bedingung.",
    }


def gegenproben() -> list[tuple[str, dict, bool]]:
    gueltig = basis_ergebnis()

    zustimmung_mit_block = basis_ergebnis()
    zustimmung_mit_block["verdict"] = "PASS"

    block_ohne_beleg = basis_ergebnis()
    block_ohne_beleg["findings"] = [
        {"id": "F-001", "severity": "BLOCK", "title": "Befund ohne Beleg"}
    ]

    urteil_falsche_rolle = basis_ergebnis()
    urteil_falsche_rolle["role"] = "implementer"

    return [
        ("belegter blockierender Befund mit ablehnendem Urteil", gueltig, True),
        ("zustimmendes Urteil trotz offenem BLOCK", zustimmung_mit_block, False),
        ("BLOCK ohne die drei Belegangaben", block_ohne_beleg, False),
        ("Urteil von einer nicht prüfenden Rolle", urteil_falsche_rolle, False),
    ]


def main() -> int:
    if not SCHEMAS.is_dir():
        print("FEHLER: Verzeichnis schemas/ fehlt.", file=sys.stderr)
        return 2

    fehler = 0
    registry = lade_registry()

    # 1. Sind die Schemas selbst gültig?
    for datei in sorted(SCHEMAS.glob("*.json")):
        try:
            schema = json.loads(datei.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            print(f"OK    {datei.name} ist ein gültiges Schema")
        except Exception as e:  # noqa: BLE001
            fehler += 1
            print(f"FEHLER {datei.name}: {e}", file=sys.stderr)

    # 2. Bestehen die Beispiele ihr Schema?
    for beispielpfad, schemaname in BEISPIELE:
        pfad = WURZEL / beispielpfad
        if not pfad.is_file():
            fehler += 1
            print(f"FEHLER {beispielpfad} fehlt", file=sys.stderr)
            continue
        dokument = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        probleme = list(validator_fuer(schemaname, registry).iter_errors(dokument))
        if probleme:
            fehler += 1
            print(f"FEHLER {beispielpfad} gegen {schemaname}", file=sys.stderr)
            for p in probleme:
                print(f"    {list(p.absolute_path)}: {p.message}", file=sys.stderr)
        else:
            print(f"OK    {beispielpfad} besteht {schemaname}")

    # 3. Greifen die Bedingungen des Ergebnis-Schemas?
    ergebnis_validator = validator_fuer("result.schema.json", registry)
    for name, dokument, soll_gueltig in gegenproben():
        ist_gueltig = ergebnis_validator.is_valid(dokument)
        if ist_gueltig == soll_gueltig:
            erwartung = "wird angenommen" if soll_gueltig else "faellt durch"
            print(f"OK    {name} {erwartung}")
        else:
            fehler += 1
            print(
                f"FEHLER {name}: gültig={ist_gueltig}, erwartet={soll_gueltig}",
                file=sys.stderr,
            )

    if fehler:
        print(f"\n{fehler} Befund(e).", file=sys.stderr)
        return 1

    print("\nSchemas, Beispiele und Gegenproben ohne Befund.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
