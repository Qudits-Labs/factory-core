#!/usr/bin/env python3
"""Canary-Selbsttest der Software-Fabrik.

Misst die Prüfschritte des Kerns gegen synthetische Fixtures und gibt je Fall
eine Zeile aus. Er ruft scripts/validate_schemas.py und scripts/selftest.py
auf, statt deren Logik nachzubauen. Zusätzlich prüft er Dinge, die diese
Skripte nicht abdecken: Schema-Verweis ohne Netz, Workflow-Permissions und den
Gate-Vertrag für workflow_call-Workflows.

Ausgabe je Fall:
  OK            <name>
  FEHLER        <name>: <grund>
  UEBERSPRUNGEN <name>: <grund>

Bilanz am Ende: X von Y OK, Z Fehler, W uebersprungen.

Exit-Codes:
  0  alle ausgefuehrten Faelle bestanden
  1  mindestens ein Befund
  2  technischer Fehler (fehlende Abhaengigkeit oder unlesbare Datei)

Aufruf:
  python3 canary/run_canary.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError as fehler:
    print(
        f"FEHLER: Abhaengigkeit fehlt ({fehler}). "
        "Installation: pip install jsonschema pyyaml referencing",
        file=sys.stderr,
    )
    raise SystemExit(2)

WURZEL = Path(__file__).resolve().parent.parent
CANARY = Path(__file__).resolve().parent
FIXTURES = CANARY / "fixtures"
SCRIPTS = WURZEL / "scripts"
SCHEMAS = WURZEL / "schemas"
WORKFLOWS = WURZEL / ".github" / "workflows"

_ok: list[str] = []
_fehler: list[str] = []
_uebersprungen: list[str] = []


def _ok_(name: str) -> None:
    _ok.append(name)
    print(f"OK            {name}")


def _fehler_(name: str, grund: str) -> None:
    _fehler.append(name)
    print(f"FEHLER        {name}: {grund}")


def _uebersprungen_(name: str, grund: str) -> None:
    _uebersprungen.append(name)
    print(f"UEBERSPRUNGEN {name}: {grund}")


def _lauf(skript: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(skript), *args],
        capture_output=True,
        text=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema-Validierung und Gegenproben via validate_schemas.py
#    Deckt ab: Schemas sind gültig, Beispieldateien bestehen, und die vier
#    Gegenproben greifen (darunter PASS+BLOCK und BLOCK-ohne-Beleg).
# ─────────────────────────────────────────────────────────────────────────────
def pruefe_schema_validierung() -> None:
    skript = SCRIPTS / "validate_schemas.py"
    if not skript.exists():
        _uebersprungen_("schema-validierung", f"{skript.name} fehlt")
        return
    lauf = _lauf(skript)
    if lauf.returncode == 0:
        _ok_(
            "schema-validierung — Schemas, Beispiele und Gegenproben "
            "(inkl. PASS+BLOCK und BLOCK-ohne-Beleg) ohne Befund"
        )
    else:
        _fehler_("schema-validierung", lauf.stderr.strip()[:300] or lauf.stdout.strip()[:300])


# ─────────────────────────────────────────────────────────────────────────────
# 2. Gate-Skripte gegen bestehende tests/fixtures/ via selftest.py
#    Deckt ab: alle gate_*.py und transition_check.py gegen sauber/verstoss.
# ─────────────────────────────────────────────────────────────────────────────
def pruefe_selftest() -> None:
    skript = SCRIPTS / "selftest.py"
    if not skript.exists():
        _uebersprungen_("selftest", f"{skript.name} fehlt")
        return
    lauf = _lauf(skript)
    if lauf.returncode == 0:
        zeilen = [z for z in lauf.stdout.splitlines() if z.startswith("OK")]
        _ok_(f"selftest — {len(zeilen)} Gate-Faelle gegen tests/fixtures/ bestanden")
    else:
        _fehler_("selftest", lauf.stderr.strip()[:300] or lauf.stdout.strip()[:300])


# ─────────────────────────────────────────────────────────────────────────────
# 3. Schema-Verweis ohne Netzzugriff
#    result.schema.json verweist relativ auf finding.schema.json. Loesung
#    ausschliesslich aus dem Dateisystem — nicht ueber das Netz. Schlaegt die
#    Validierung hier fehl, bedeutet das, dass der Kern von einer externen
#    Adresse abhaengt, die nicht verfuegbar sein muss.
# ─────────────────────────────────────────────────────────────────────────────
def pruefe_schema_verweis_offline() -> None:
    result_datei = SCHEMAS / "result.schema.json"
    finding_datei = SCHEMAS / "finding.schema.json"
    if not result_datei.exists() or not finding_datei.exists():
        _uebersprungen_(
            "schema-verweis-offline",
            "result.schema.json oder finding.schema.json fehlt",
        )
        return
    try:
        registry = Registry()
        for datei in sorted(SCHEMAS.glob("*.json")):
            inhalt = json.loads(datei.read_text(encoding="utf-8"))
            ressource = Resource.from_contents(inhalt)
            registry = registry.with_resource(uri=datei.name, resource=ressource)
            if "$id" in inhalt:
                registry = registry.with_resource(
                    uri=inhalt["$id"], resource=ressource
                )

        result_schema = json.loads(result_datei.read_text(encoding="utf-8"))
        validator = Draft202012Validator(result_schema, registry=registry)

        # Minimal-gueltiges Dokument: kein Netzaufruf darf entstehen
        testdok = {
            "schema_version": "1.0",
            "role": "adversary",
            "attempt": 1,
            "run_id": "canary-offline-001",
            "commit_sha": None,
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "status": "failed",
            "verdict": "FAIL",
            "artefakte": [],
            "findings": [],
            "begruendung": "Offline-Prüfung des Schema-Verweises.",
        }
        schema_fehler = list(validator.iter_errors(testdok))
        if schema_fehler:
            _fehler_(
                "schema-verweis-offline",
                f"{len(schema_fehler)} Validierungsfehler beim Offline-Testdokument",
            )
        else:
            _ok_(
                "schema-verweis-offline — finding.schema.json vom Dateisystem "
                "aufgeloest, kein Netzzugriff"
            )
    except Exception as ausnahme:
        _fehler_("schema-verweis-offline", str(ausnahme))


# ─────────────────────────────────────────────────────────────────────────────
# 4. Canary-eigene Gate-Fixtures
#    Jedes Gate-Skript laeuft gegen ein sauberes und ein verletzendes Fixture
#    aus canary/fixtures/. Diese Fixtures testen andere Szenarien als die
#    Fixtures unter tests/.
# ─────────────────────────────────────────────────────────────────────────────
# (skriptname, sauber-fixture-verzeichnis, verstoss-fixture-verzeichnis)
_CANARY_GATE_FAELLE: list[tuple[str, str, str]] = [
    (
        "gate_story_lint",
        "story-lint-vollstaendig",
        "story-lint-unvollstaendig",
    ),
    (
        "gate_adr_check",
        "adr-vollstaendig",
        "adr-unvollstaendig",
    ),
    (
        "gate_test_integrity",
        "test-integrity-sauber",
        "test-integrity-verstoss",
    ),
    (
        "gate_doc_check",
        "doc-check-sauber",
        "doc-check-neu-ohne-doku",    # synthetischer Diff: neuer Bezeichner fehlt in Doku
    ),
]


def pruefe_canary_gate_fixtures() -> None:
    for skriptname, sauber_name, verstoss_name in _CANARY_GATE_FAELLE:
        skript = SCRIPTS / f"{skriptname}.py"
        if not skript.exists():
            _uebersprungen_(
                f"canary/{skriptname}",
                f"{skript.name} noch nicht angelegt",
            )
            continue

        sauber_vz = FIXTURES / sauber_name
        verstoss_vz = FIXTURES / verstoss_name

        # Sauber-Fall: Exit 0 erwartet
        if not sauber_vz.is_dir():
            _uebersprungen_(f"canary/{skriptname}/sauber", f"Fixture {sauber_name} fehlt")
        else:
            lauf = _lauf(skript, str(sauber_vz))
            if lauf.returncode == 0:
                _ok_(f"canary/{skriptname}/sauber — {sauber_name} → Exit 0")
            else:
                _fehler_(
                    f"canary/{skriptname}/sauber",
                    f"Exit {lauf.returncode} statt 0. "
                    + (lauf.stderr.strip()[:200] or lauf.stdout.strip()[:200]),
                )

        # Verstoss-Fall: Exit 1 erwartet
        if not verstoss_vz.is_dir():
            _uebersprungen_(f"canary/{skriptname}/verstoss", f"Fixture {verstoss_name} fehlt")
        else:
            lauf = _lauf(skript, str(verstoss_vz))
            if lauf.returncode == 1:
                _ok_(f"canary/{skriptname}/verstoss — {verstoss_name} → Exit 1")
            else:
                _fehler_(
                    f"canary/{skriptname}/verstoss",
                    f"Exit {lauf.returncode} statt 1. "
                    + (lauf.stderr.strip()[:200] or lauf.stdout.strip()[:200]),
                )


# ─────────────────────────────────────────────────────────────────────────────
# 5. AC-Map-Schema-Validierung gegen Canary-Fixtures
#    Vollstaendige AC-Map besteht das Schema, lueckenhafte faellt durch.
# ─────────────────────────────────────────────────────────────────────────────
def pruefe_ac_map_schema() -> None:
    schema_datei = SCHEMAS / "ac-map.schema.json"
    if not schema_datei.exists():
        _uebersprungen_("ac-map-schema", "ac-map.schema.json fehlt")
        return

    try:
        registry = Registry()
        for datei in sorted(SCHEMAS.glob("*.json")):
            inhalt = json.loads(datei.read_text(encoding="utf-8"))
            ressource = Resource.from_contents(inhalt)
            registry = registry.with_resource(uri=datei.name, resource=ressource)
            if "$id" in inhalt:
                registry = registry.with_resource(uri=inhalt["$id"], resource=ressource)

        schema = json.loads(schema_datei.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, registry=registry)
    except Exception as ausnahme:
        _fehler_("ac-map-schema", f"Schema konnte nicht geladen werden: {ausnahme}")
        return

    vollstaendig = FIXTURES / "ac-map-vollstaendig.json"
    lueckenhaft = FIXTURES / "ac-map-lueckenhaft.json"

    if vollstaendig.exists():
        dok = json.loads(vollstaendig.read_text(encoding="utf-8"))
        fehler = list(validator.iter_errors(dok))
        if fehler:
            _fehler_(
                "ac-map-schema/vollstaendig",
                f"{len(fehler)} Validierungsfehler — erwartet: bestanden",
            )
        else:
            _ok_("ac-map-schema/vollstaendig — vollstaendige AC-Map besteht das Schema")
    else:
        _uebersprungen_("ac-map-schema/vollstaendig", "Fixture fehlt")

    if lueckenhaft.exists():
        dok = json.loads(lueckenhaft.read_text(encoding="utf-8"))
        fehler = list(validator.iter_errors(dok))
        if fehler:
            _ok_("ac-map-schema/lueckenhaft — lueckenhafte AC-Map faellt durch das Schema")
        else:
            _fehler_(
                "ac-map-schema/lueckenhaft",
                "lueckenhafte AC-Map besteht faelschlich — erwartet: abgelehnt",
            )
    else:
        _uebersprungen_("ac-map-schema/lueckenhaft", "Fixture fehlt")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Ergebnis-Schema-Validierung gegen Canary-Fixtures
#    Gueltiges Dokument besteht, widersprüchliche fallen durch.
# ─────────────────────────────────────────────────────────────────────────────
_RESULT_FIXTURES: list[tuple[str, bool, str]] = [
    (
        "result-gueltig.json",
        True,
        "vollstaendiges Ergebnisdokument besteht result.schema.json",
    ),
    (
        "result-zustimmung-mit-block.json",
        False,
        "PASS-Urteil mit offenem BLOCK wird abgelehnt",
    ),
    (
        "result-block-ohne-beleg.json",
        False,
        "BLOCK-Befund ohne spec_ref/location/reproduction wird abgelehnt",
    ),
]


def pruefe_result_schema_fixtures() -> None:
    schema_datei = SCHEMAS / "result.schema.json"
    finding_datei = SCHEMAS / "finding.schema.json"
    if not schema_datei.exists() or not finding_datei.exists():
        _uebersprungen_("result-schema-fixtures", "result.schema.json oder finding.schema.json fehlt")
        return

    try:
        registry = Registry()
        for datei in sorted(SCHEMAS.glob("*.json")):
            inhalt = json.loads(datei.read_text(encoding="utf-8"))
            ressource = Resource.from_contents(inhalt)
            registry = registry.with_resource(uri=datei.name, resource=ressource)
            if "$id" in inhalt:
                registry = registry.with_resource(uri=inhalt["$id"], resource=ressource)
        schema = json.loads(schema_datei.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, registry=registry)
    except Exception as ausnahme:
        _fehler_("result-schema-fixtures", f"Schema konnte nicht geladen werden: {ausnahme}")
        return

    for dateiname, soll_gueltig, beschreibung in _RESULT_FIXTURES:
        fixture_pfad = FIXTURES / dateiname
        if not fixture_pfad.exists():
            _uebersprungen_(f"result-schema/{dateiname}", "Fixture fehlt")
            continue
        try:
            dok = json.loads(fixture_pfad.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            _fehler_(f"result-schema/{dateiname}", f"Kein gueltiges JSON: {e}")
            continue
        ist_gueltig = validator.is_valid(dok)
        if ist_gueltig == soll_gueltig:
            _ok_(f"result-schema/{dateiname} — {beschreibung}")
        else:
            erwartet = "besteht" if soll_gueltig else "faellt durch"
            tatsaechlich = "besteht" if ist_gueltig else "faellt durch"
            _fehler_(
                f"result-schema/{dateiname}",
                f"Erwartet: {erwartet}, tatsaechlich: {tatsaechlich}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Workflow-Permissions
#    Jeder Workflow unter .github/workflows/ muss permissions: ausdrücklich
#    deklarieren. Ein Workflow ohne diese Zeile erbt Rechte.
# ─────────────────────────────────────────────────────────────────────────────
def pruefe_workflow_permissions() -> None:
    if not WORKFLOWS.is_dir():
        _uebersprungen_("workflow-permissions", ".github/workflows/ fehlt")
        return
    dateien = sorted(WORKFLOWS.glob("*.yml"))
    if not dateien:
        _uebersprungen_("workflow-permissions", "keine Workflow-Dateien gefunden")
        return
    ohne: list[str] = []
    for datei in dateien:
        try:
            inhalt = yaml.safe_load(datei.read_text(encoding="utf-8"))
        except Exception as ausnahme:
            _fehler_(f"workflow-permissions/{datei.name}", f"nicht lesbar: {ausnahme}")
            continue
        if not isinstance(inhalt, dict):
            continue
        if "permissions" not in inhalt:
            ohne.append(datei.name)
    if ohne:
        _fehler_(
            "workflow-permissions",
            f"{len(ohne)} Workflow(s) ohne `permissions:` deklariert: {', '.join(ohne)}",
        )
    else:
        _ok_(
            f"workflow-permissions — alle {len(dateien)} Workflow(s) deklarieren "
            "`permissions:` ausdruecklich"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 8. Workflow-Call-Vertrag
#    Jeder gate-*.yml-Workflow, der per workflow_call aufgerufen wird, muss
#    `pass` und `findings_json` als Ausgaben deklarieren. Das ist die
#    Vertragstreue-Pruefung — der wertvollste Teil.
#    Fehlen gate-*.yml-Dateien, ist der Schritt noch nicht angelegt und wird
#    uebersprungen (sichtbar, nicht still).
# ─────────────────────────────────────────────────────────────────────────────
def pruefe_workflow_call_vertrag() -> None:
    if not WORKFLOWS.is_dir():
        _uebersprungen_("workflow-call-vertrag", ".github/workflows/ fehlt")
        return
    gate_dateien = sorted(WORKFLOWS.glob("gate-*.yml"))
    if not gate_dateien:
        _uebersprungen_(
            "workflow-call-vertrag",
            "keine gate-*.yml-Workflows gefunden — noch nicht angelegt",
        )
        return

    verstossdateien: list[str] = []
    geprueft = 0
    for datei in gate_dateien:
        try:
            inhalt = yaml.safe_load(datei.read_text(encoding="utf-8"))
        except Exception as ausnahme:
            _fehler_(f"workflow-call-vertrag/{datei.name}", f"nicht lesbar: {ausnahme}")
            continue
        if not isinstance(inhalt, dict):
            continue

        # Ist es ein workflow_call-Workflow?
        on_block = inhalt.get("on", inhalt.get(True))
        if not isinstance(on_block, dict) or "workflow_call" not in on_block:
            continue

        geprueft += 1
        wc = on_block.get("workflow_call") or {}
        wc_ausgaben: set[str] = set()
        if isinstance(wc, dict):
            for schluessel in (wc.get("outputs") or {}):
                wc_ausgaben.add(schluessel)

        fehlend = [p for p in ("pass", "findings_json") if p not in wc_ausgaben]
        if fehlend:
            verstossdateien.append(
                f"{datei.name} (Ausgaben fehlen: {', '.join(fehlend)})"
            )

    if not geprueft:
        _uebersprungen_(
            "workflow-call-vertrag",
            f"{len(gate_dateien)} gate-*.yml gefunden, aber keiner davon hat workflow_call",
        )
        return

    if verstossdateien:
        _fehler_(
            "workflow-call-vertrag",
            "Vertrag verletzt in: " + "; ".join(verstossdateien),
        )
    else:
        _ok_(
            f"workflow-call-vertrag — {geprueft} gate-Workflow(s) geben "
            "`pass` und `findings_json` zurueck"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Hauptprogramm
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("── Canary-Selbsttest ────────────────────────────────────────────────")
    print()

    print("Schritt 1: Schema-Validierung (validate_schemas.py)")
    pruefe_schema_validierung()
    print()

    print("Schritt 2: Gate-Skripte gegen tests/fixtures/ (selftest.py)")
    pruefe_selftest()
    print()

    print("Schritt 3: Schema-Verweis ohne Netzzugriff")
    pruefe_schema_verweis_offline()
    print()

    print("Schritt 4: Canary-eigene Gate-Fixtures")
    pruefe_canary_gate_fixtures()
    print()

    print("Schritt 5: AC-Map-Schema gegen Canary-Fixtures")
    pruefe_ac_map_schema()
    print()

    print("Schritt 6: Ergebnis-Schema gegen Canary-Fixtures")
    pruefe_result_schema_fixtures()
    print()

    print("Schritt 7: Workflow-Permissions")
    pruefe_workflow_permissions()
    print()

    print("Schritt 8: Workflow-Call-Vertrag (gate-*.yml)")
    pruefe_workflow_call_vertrag()
    print()

    gesamt = len(_ok) + len(_fehler) + len(_uebersprungen)
    print("── Bilanz ───────────────────────────────────────────────────────────")
    print(f"  OK:            {len(_ok):3d}")
    print(f"  FEHLER:        {len(_fehler):3d}")
    print(f"  UEBERSPRUNGEN: {len(_uebersprungen):3d}")
    print(f"  Gesamt:        {gesamt:3d}")
    print()

    if _fehler:
        print("Fehlgeschlagene Faelle:")
        for name in _fehler:
            print(f"  - {name}")
        print()

    if _uebersprungen:
        print("Uebersprungene Faelle (kein Fehler, aber Abdeckungsluecke):")
        for name in _uebersprungen:
            print(f"  - {name}")
        print()

    if _fehler:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
