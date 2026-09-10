#!/usr/bin/env python3
"""Stellt fest, ob genau eine Zugangsart zum Modell gesetzt ist.

Die Claude-Code-Action fuehrt zwei getrennte Eingaben fuer den Zugang:
einen Anthropic-API-Schluessel und ein OAuth-Token eines Claude-Abos. Ein
OAuth-Token im Feld fuer den API-Schluessel wird abgewiesen. Der Aufrufer
waehlt, welchen Weg er geht; genau einer muss es sein.

GitHub kennt in `workflow_call.secrets` kein "genau eines von beiden".
`required: true` bei beiden wuerde jeden Aufrufer zwingen, beide zu setzen.
Beide sind deshalb optional deklariert, und diese Pruefung stellt die
Bedingung her, bevor die Action startet.

Dieses Skript sieht die Geheimnisse nie. Der aufrufende Workflow wertet im
Ausdruck aus, ob ein Wert leer ist, und uebergibt nur das Ergebnis. Ein
Geheimnis, das durch ein Skript laeuft, kann in eine Ausgabe geraten; ein
Wahrheitswert nicht.

Aufruf (Fixture-Modus fuer Tests):
    python3 scripts/pruefe_zugangsart.py <fixture-verzeichnis>

    Das Verzeichnis muss `config.txt` enthalten:
      hat_api_key=true
      hat_oauth_token=false

Aufruf (Produktiv via GitHub Actions):
    Liest aus Umgebungsvariablen. Ein nicht leerer Wert bedeutet gesetzt:
      GATE_HAT_API_KEY
      GATE_HAT_OAUTH_TOKEN

Exit-Codes:
    0 - genau eine Zugangsart gesetzt
    1 - keine oder beide gesetzt
    2 - technischer Fehler
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

API_KEY = "anthropic_api_key"
OAUTH_TOKEN = "claude_code_oauth_token"

_WAHR = {"true", "1", "ja", "yes"}
_FALSCH = {"false", "0", "nein", "no", ""}


def _lies_fixture(verzeichnis: Path) -> tuple[bool, bool]:
    config_datei = verzeichnis / "config.txt"
    if not config_datei.exists():
        raise FileNotFoundError(f"{config_datei} fehlt")

    config: dict[str, str] = {}
    for zeile in config_datei.read_text(encoding="utf-8").splitlines():
        if "=" in zeile:
            schluessel, wert = zeile.split("=", 1)
            config[schluessel.strip()] = wert.strip().lower()

    def als_wahrheitswert(schluessel: str) -> bool:
        wert = config.get(schluessel, "")
        if wert in _WAHR:
            return True
        if wert in _FALSCH:
            return False
        raise ValueError(f"{schluessel}={wert!r} ist weder wahr noch falsch")

    return als_wahrheitswert("hat_api_key"), als_wahrheitswert("hat_oauth_token")


def main(argv: list[str]) -> int:
    if argv and Path(argv[0]).is_dir():
        try:
            hat_api_key, hat_oauth_token = _lies_fixture(Path(argv[0]))
        except (OSError, ValueError) as fehler:
            print(f"FEHLER: Fixture nicht lesbar: {fehler}", file=sys.stderr)
            return 2
    else:
        hat_api_key = bool(os.environ.get("GATE_HAT_API_KEY", "").strip())
        hat_oauth_token = bool(os.environ.get("GATE_HAT_OAUTH_TOKEN", "").strip())

    if hat_api_key and hat_oauth_token:
        print(
            f"FEHLER: {API_KEY} und {OAUTH_TOKEN} sind beide gesetzt."
            " Genau eine Zugangsart waehlen -- sonst entscheidet die Action,"
            " welche gilt, und der Aufrufer weiss nicht, wofuer er zahlt.",
            file=sys.stderr,
        )
        return 1

    if not hat_api_key and not hat_oauth_token:
        print(
            f"FEHLER: Weder {API_KEY} noch {OAUTH_TOKEN} ist gesetzt."
            " Der Agentenlauf braucht einen Zugang zum Modell.",
            file=sys.stderr,
        )
        return 1

    gewaehlt = API_KEY if hat_api_key else OAUTH_TOKEN
    print(f"Zugangsart: {gewaehlt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
