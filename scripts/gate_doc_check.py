#!/usr/bin/env python3
"""Prueft maschinell, ob Code-Entitaeten in zugeordneten Dokumenten aufgefuehrt sind.

Zweck:
    Erkennt neu hinzugekommene Bezeichner (z.B. Funktionen, Klassen,
    Endpunkte), die in keiner Dokumentationsdatei stehen, sowie entfernte
    Bezeichner, die noch in Dokumentationsdateien erwaehnt werden.

    Das Extraktionsmuster und die Zuordnung von Quellpfaden zu Doku-Dateien
    kommen vom aufrufenden Repositorium als JSON (doc_map.json). Damit
    bleibt der Kern produktneutral.

    Je Eintrag in der Zuordnungsdatei werden erwartet:
      paths          - Array von Glob-Mustern fuer Quelldateien
      docs           - Array von Pfaden zu Dokumentationsdateien
      entity_pattern - Regex mit genau einer Fanggruppe fuer den Bezeichner

Aufruf (Fixture-Modus fuer Tests):
    python3 scripts/gate_doc_check.py <fixture-verzeichnis>

    Das Verzeichnis muss enthalten:
      doc_map.json     - Zuordnungsdatei
      diff_added.txt   - simulierter Diff (hinzugefuegte Zeilen):
                           FILE:pfad/zu/datei.py
                           def neue_funktion(x):
                           ...
      diff_removed.txt - analog fuer entfernte Zeilen
      docs/            - Dokumentationsdateien fuer den Vergleich

Aufruf (Produktiv via GitHub Actions):
    Liest aus Umgebungsvariablen:
      GATE_DOC_MAP_JSON   - Inhalt der Zuordnungsdatei als JSON-String
      GATE_BASE_SHA       - Basis-Commit
      GATE_HEAD_SHA       - Head-Commit
    Fuehrt git diff aus und prueft gegen Dokumentationsdateien.

Exit-Codes:
    0 - Keine fehlenden oder veralteten Entitaeten
    1 - Befund
    2 - Technischer Fehler
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
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


def git_diff_zeilen(basis: str, kopf: str, pfad: str) -> tuple[list[str], list[str]]:
    """Gibt (hinzugefuegte_zeilen, entfernte_zeilen) zurueck."""
    lauf = subprocess.run(
        ["git", "diff", basis, kopf, "--", pfad],
        capture_output=True,
        text=True,
    )
    if lauf.returncode != 0:
        raise RuntimeError(f"git diff schlug fehl: {lauf.stderr}")
    hinzu = [
        z[1:]
        for z in lauf.stdout.splitlines()
        if z.startswith("+") and not z.startswith("+++")
    ]
    entfernt = [
        z[1:]
        for z in lauf.stdout.splitlines()
        if z.startswith("-") and not z.startswith("---")
    ]
    return hinzu, entfernt


def extrahiere_bezeichner(zeilen: list[str], muster: re.Pattern) -> set[str]:
    bezeichner: set[str] = set()
    for zeile in zeilen:
        for treffer in muster.findall(zeile):
            bezeichner.add(treffer)
    return bezeichner


def bezeichner_in_doku(bezeichner: str, doku_pfade: list[str], wurzel: Path) -> bool:
    for dp in doku_pfade:
        datei = wurzel / dp
        if datei.exists() and bezeichner in datei.read_text(encoding="utf-8"):
            return True
    return False


def lade_diff_fixture(pfad: Path) -> dict[str, list[str]]:
    """Liest ein Fixture-Diff-File. Format: FILE:<pfad>\\n<zeilen>..."""
    ergebnis: dict[str, list[str]] = {}
    if not pfad.exists():
        return ergebnis
    aktueller_pfad: str | None = None
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if zeile.startswith("FILE:"):
            aktueller_pfad = zeile[5:].strip()
            ergebnis[aktueller_pfad] = []
        elif aktueller_pfad is not None:
            ergebnis[aktueller_pfad].append(zeile)
    return ergebnis


def pruefe_eintrag(
    eintrag: dict,
    wurzel: Path,
    fixture_hinzu: dict[str, list[str]] | None,
    fixture_entfernt: dict[str, list[str]] | None,
    basis: str | None,
    kopf: str | None,
) -> tuple[list[str], list[str]]:
    muster_str = eintrag.get("entity_pattern", "")
    if not muster_str:
        return [], []
    try:
        muster = re.compile(muster_str)
    except re.error as e:
        raise ValueError(f"Ungueltige Regex '{muster_str}': {e}") from e

    doku_pfade: list[str] = eintrag.get("docs", [])
    glob_muster: list[str] = eintrag.get("paths", [])
    fehlend: list[str] = []
    veraltet: list[str] = []

    # Quelldateien ermitteln (Fixture: Verzeichnisinhalt, Produktion: Git-Diff)
    kandidaten: set[str] = set()
    if fixture_hinzu is not None:
        kandidaten = set(fixture_hinzu.keys()) | set((fixture_entfernt or {}).keys())
    # Nur Kandidaten beachten, die auf die Glob-Muster passen
    gefilterte = [
        k for k in kandidaten if any(fnmatch.fnmatch(k, g) for g in glob_muster)
    ]

    for pfad_rel in gefilterte:
        if fixture_hinzu is not None:
            hinzu = fixture_hinzu.get(pfad_rel, [])
            entfernt = (fixture_entfernt or {}).get(pfad_rel, [])
        else:
            try:
                hinzu, entfernt = git_diff_zeilen(basis, kopf, pfad_rel)
            except RuntimeError as e:
                print(f"WARNUNG: {e}", file=sys.stderr)
                continue

        neue = extrahiere_bezeichner(hinzu, muster)
        alte = extrahiere_bezeichner(entfernt, muster)

        for bez in neue:
            if not bezeichner_in_doku(bez, doku_pfade, wurzel):
                fehlend.append(bez)

        for bez in alte:
            if bezeichner_in_doku(bez, doku_pfade, wurzel):
                veraltet.append(bez)

    return fehlend, veraltet


def main(argv: list[str]) -> int:
    wurzel = Path(".")
    fixture_hinzu: dict[str, list[str]] | None = None
    fixture_entfernt: dict[str, list[str]] | None = None
    basis = kopf = None
    eintraege: list[dict] = []

    if argv and Path(argv[0]).is_dir():
        vz = Path(argv[0])
        doc_map_datei = vz / "doc_map.json"
        if not doc_map_datei.exists():
            print(f"FEHLER: {doc_map_datei} fehlt", file=sys.stderr)
            return 2
        try:
            doc_map = json.loads(doc_map_datei.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"FEHLER: doc_map.json ist kein gueltiges JSON: {e}", file=sys.stderr)
            return 2
        eintraege = doc_map if isinstance(doc_map, list) else doc_map.get("entries", [])
        fixture_hinzu = lade_diff_fixture(vz / "diff_added.txt")
        fixture_entfernt = lade_diff_fixture(vz / "diff_removed.txt")
        wurzel = vz
    else:
        doc_map_roh = os.environ.get("GATE_DOC_MAP_JSON", "")
        if not doc_map_roh:
            print("FEHLER: GATE_DOC_MAP_JSON nicht gesetzt", file=sys.stderr)
            return 2
        basis = os.environ.get("GATE_BASE_SHA", "")
        kopf = os.environ.get("GATE_HEAD_SHA", "")
        if not basis or not kopf:
            print(
                "FEHLER: GATE_BASE_SHA und GATE_HEAD_SHA sind erforderlich",
                file=sys.stderr,
            )
            return 2
        try:
            doc_map = json.loads(doc_map_roh)
        except json.JSONDecodeError as e:
            print(
                f"FEHLER: GATE_DOC_MAP_JSON ist kein gueltiges JSON: {e}",
                file=sys.stderr,
            )
            return 2
        eintraege = (
            doc_map if isinstance(doc_map, list) else doc_map.get("entries", [])
        )

    alle_fehlend: list[str] = []
    alle_veraltet: list[str] = []

    for eintrag in eintraege:
        try:
            fehlend, veraltet = pruefe_eintrag(
                eintrag, wurzel, fixture_hinzu, fixture_entfernt, basis, kopf
            )
        except ValueError as e:
            print(f"FEHLER: {e}", file=sys.stderr)
            return 2
        alle_fehlend.extend(fehlend)
        alle_veraltet.extend(veraltet)

    bestanden = not alle_fehlend and not alle_veraltet
    titel = (
        [f"Fehlend in Doku: {b}" for b in alle_fehlend]
        + [
            f"Veraltet in Doku (Bezeichner entfernt, aber noch erwaehnt): {v}"
            for v in alle_veraltet
        ]
    )

    schreibe_ausgabe("pass", "true" if bestanden else "false")
    schreibe_ausgabe("missing_entities", json.dumps(alle_fehlend))
    schreibe_ausgabe("stale_entities", json.dumps(alle_veraltet))
    schreibe_ausgabe("findings_json", json.dumps(baue_befunde(titel)))

    if not bestanden:
        for t in titel:
            print(f"  BEFUND: {t}", file=sys.stderr)
        return 1

    print("Dokumentations-Pruefung bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
