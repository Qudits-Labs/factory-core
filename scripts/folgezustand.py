#!/usr/bin/env python3
"""Bestimmt, welcher Zustand auf einen erledigten folgt.

Zweck:
    Nach einem erfolgreichen Agentenlauf muss ein anderes Label gelten als
    das, welches den Lauf ausgeloest hat. Ohne diesen Schritt setzt die
    Zustandsmaschine dasselbe Label erneut: die Kette liefe genau einen
    Schritt und bliebe stehen.

    Die Standardtabelle steht in `factory_phasen.py`. Ein Produktrepositorium
    mit abweichender Phasenfolge uebergibt seine eigene; wer nichts uebergibt,
    bekommt die Standardfolge.

Was dieses Skript nicht tut:
    Es setzt kein Label. Ein Label, das mit dem Standardtoken gesetzt wird,
    loest keinen weiteren Workflow aus -- die Kette bliebe trotz richtigem
    Folgezustand stehen. Das Setzen gehoert deshalb an die Stelle, an der
    eine App-Identitaet zur Verfuegung steht, und die liegt im aufrufenden
    Repositorium. Dieses Skript sagt nur, welches Label das waere.

Aufruf (Fixture-Modus fuer Tests):
    python3 scripts/folgezustand.py <fixture-verzeichnis>

    Das Verzeichnis muss enthalten:
      config.txt            - Schluessel=Wert-Paare:
                                label=status:spec
                                erwartete_folge=status:spec-review   (optional)
      folge_label_map.json  - optional; ohne diese Datei gilt der Standard

    Steht `erwartete_folge` in der Datei, prueft das Skript das Ergebnis
    dagegen und gibt bei Abweichung Exit 1. So laesst sich die Tabelle selbst
    messen und nicht nur ihre Lesbarkeit.

    Massgeblich ist, ob der Schluessel dasteht, nicht ob er einen Wert hat.
    `erwartete_folge=` ohne Wert ist deshalb eine echte Erwartung: fuer dieses
    Label darf es keinen Folgezustand geben. Das Ende der Kette ist ein
    Verhalten des Kerns und gehoert gemessen, nicht angenommen.

Aufruf (Produktiv via GitHub Actions):
    Liest aus Umgebungsvariablen:
      GATE_NEW_LABEL              das Label, das den erledigten Lauf ausloeste
      GATE_FOLGE_LABEL_MAP_JSON   optionale Ersetzung der Standardtabelle
    Schreibt `next_label` nach GITHUB_OUTPUT. Ein leerer Wert heisst: fuer
    diesen Zustand ist kein Folgezustand hinterlegt, die Kette haelt hier an.

Exit-Codes:
    0 - Folgezustand bestimmt (auch wenn es keinen gibt -- das ist kein Fehler)
    1 - Tabelle unbrauchbar oder erwarteter Wert nicht eingetreten
    2 - technischer Fehler
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from factory_phasen import (
    STANDARD_FOLGE_JE_LABEL,
    lade_map,
    validiere_folge_map,
)


def schreibe_ausgabe(schluessel: str, wert: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{schluessel}={wert}\n")
    else:
        print(f"  {schluessel}: {wert}")


def _lade_fixture(verzeichnis: Path) -> tuple[str, str, str | None]:
    """Gibt (label, roh_map, erwartete_folge) zurueck.

    `erwartete_folge` ist None, wenn der Schluessel fehlt -- dann wird nichts
    geprueft. Eine leere Zeichenkette heisst: es darf keinen Folgezustand
    geben.
    """
    config: dict[str, str] = {}
    config_datei = verzeichnis / "config.txt"
    if config_datei.exists():
        for zeile in config_datei.read_text(encoding="utf-8").splitlines():
            if "=" in zeile:
                k, v = zeile.split("=", 1)
                config[k.strip()] = v.strip()

    map_datei = verzeichnis / "folge_label_map.json"
    roh_map = map_datei.read_text(encoding="utf-8") if map_datei.exists() else ""

    return config.get("label", ""), roh_map, config.get("erwartete_folge")


def main(argv: list[str]) -> int:
    erwartete_folge: str | None = None

    if argv and Path(argv[0]).is_dir():
        try:
            label, roh_map, erwartete_folge = _lade_fixture(Path(argv[0]))
        except OSError as fehler:
            print(f"FEHLER: Fixture nicht lesbar: {fehler}", file=sys.stderr)
            return 2
    else:
        label = os.environ.get("GATE_NEW_LABEL", "").strip()
        roh_map = os.environ.get("GATE_FOLGE_LABEL_MAP_JSON", "")

    if not label:
        print("FEHLER: Es wurde kein Label uebergeben.", file=sys.stderr)
        return 2

    try:
        folge_map, herkunft = lade_map(roh_map, STANDARD_FOLGE_JE_LABEL)
    except json.JSONDecodeError as fehler:
        print(
            f"FEHLER: Die Folgetabelle ist kein gueltiges JSON: {fehler}",
            file=sys.stderr,
        )
        return 2
    except ValueError as fehler:
        print(f"FEHLER: {fehler}", file=sys.stderr)
        return 2

    tabellen_fehler = validiere_folge_map(folge_map)
    if tabellen_fehler:
        for meldung in tabellen_fehler:
            print(f"FEHLER: {meldung}", file=sys.stderr)
        return 1

    folge = folge_map.get(label, "")
    schreibe_ausgabe("next_label", folge)

    print(f"Folgetabelle: {herkunft}")
    if folge:
        print(f"Auf {label} folgt {folge}.")
    else:
        print(
            f"Fuer {label} ist kein Folgezustand hinterlegt."
            " Die Kette haelt hier an -- das ist der Regelfall an einem"
            " menschlichen Gate und am Ende der Kette."
        )

    if erwartete_folge is not None and folge != erwartete_folge:
        print(
            f"FEHLER: Erwartet war {erwartete_folge!r}, bestimmt wurde {folge!r}.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
