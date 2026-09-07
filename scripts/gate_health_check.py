#!/usr/bin/env python3
"""Fuehrt den Health-Check nach einem Deployment aus und entscheidet ueber Rollback.

Zweck:
    Prueft eine URL wiederholt auf HTTP-Status und optionalen Text. Schlaegt
    der Check fehl und ein Rollback-Befehl ist gesetzt, wird der Rollback
    ausgefuehrt. Der Workflow endet trotzdem als fehlgeschlagen.

    Keine Annahme ueber das Deployment-Ziel: Der Workflow fuehrt einen Befehl
    aus und prueft danach eine URL.

Aufruf (Fixture-Modus fuer Tests):
    python3 scripts/gate_health_check.py <fixture-verzeichnis>

    Das Verzeichnis muss enthalten:
      config.txt     - Schluessel=Wert-Paare:
                         url=http://example.invalid/health
                         expected_status=200
                         expected_text=ok         (optional)
                         retries=1
                         retry_delay=0
                         rollback=false           (optional)
      response.txt   - simulierte Antwort:
                         erste Zeile = HTTP-Statuscode (z.B. 200)
                         restliche Zeilen = Body

Aufruf (Produktiv via GitHub Actions):
    Liest aus Umgebungsvariablen:
      GATE_HEALTH_URL              - erforderlich
      GATE_EXPECTED_STATUS         - Default: 200
      GATE_EXPECTED_TEXT           - optional
      GATE_RETRIES                 - Default: 5
      GATE_RETRY_DELAY_SECONDS     - Default: 10
      GATE_ROLLBACK_COMMAND        - optional
    Schreibt Outputs in GITHUB_OUTPUT.

Exit-Codes:
    0 - Health-Check bestanden
    1 - Health-Check fehlgeschlagen
    2 - Technischer Fehler
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
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


def http_get(url: str) -> tuple[int, str]:
    """Fuehrt einen HTTP-GET aus. Gibt (statuscode, body) zurueck."""
    try:
        with urllib.request.urlopen(url, timeout=10) as antwort:
            return antwort.status, antwort.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        raise RuntimeError(f"HTTP-Anfrage schlug fehl: {e}") from e


def fuehre_health_check_aus(
    url: str,
    expected_status: int,
    expected_text: str | None,
    retries: int,
    retry_delay: int,
    http_fn=None,
) -> tuple[bool, str]:
    """Gibt (bestanden, ergebnis_beschreibung) zurueck."""
    if http_fn is None:
        http_fn = http_get
    letzter_fehler = "kein Versuch ausgefuehrt"
    for versuch in range(1, retries + 1):
        try:
            status, body = http_fn(url)
        except RuntimeError as e:
            letzter_fehler = str(e)
            if versuch < retries:
                time.sleep(retry_delay)
            continue

        if status != expected_status:
            letzter_fehler = f"HTTP {status} statt {expected_status}"
        elif expected_text and expected_text not in body:
            letzter_fehler = f"Text '{expected_text}' nicht im Body"
        else:
            return True, f"HTTP {status} nach {versuch} Versuch(en)"

        if versuch < retries:
            time.sleep(retry_delay)

    return False, letzter_fehler


def lade_fixture(
    verzeichnis: Path,
) -> tuple[str, int, str | None, int, int, str | None, tuple[int, str] | None]:
    config_datei = verzeichnis / "config.txt"
    response_datei = verzeichnis / "response.txt"

    config: dict[str, str] = {}
    if config_datei.exists():
        for zeile in config_datei.read_text(encoding="utf-8").splitlines():
            if "=" in zeile:
                k, v = zeile.split("=", 1)
                config[k.strip()] = v.strip()

    url = config.get("url", "http://example.invalid/health")
    expected_status = int(config.get("expected_status", "200"))
    expected_text = config.get("expected_text") or None
    retries = int(config.get("retries", "1"))
    retry_delay = int(config.get("retry_delay", "0"))
    rollback = config.get("rollback") or None

    mock_response: tuple[int, str] | None = None
    if response_datei.exists():
        zeilen = response_datei.read_text(encoding="utf-8").splitlines()
        mock_status = int(zeilen[0].strip()) if zeilen else 200
        mock_body = "\n".join(zeilen[1:]) if len(zeilen) > 1 else ""
        mock_response = (mock_status, mock_body)

    return url, expected_status, expected_text, retries, retry_delay, rollback, mock_response


def main(argv: list[str]) -> int:
    rollback_befehl: str | None = None
    http_fn = None

    if argv and Path(argv[0]).is_dir():
        try:
            (
                url,
                expected_status,
                expected_text,
                retries,
                retry_delay,
                rollback_befehl,
                mock_response,
            ) = lade_fixture(Path(argv[0]))
        except (ValueError, SystemExit) as e:
            if isinstance(e, SystemExit):
                raise
            print(f"FEHLER: Ungueltige Fixture: {e}", file=sys.stderr)
            return 2

        if mock_response is not None:
            gespeichert = mock_response

            def http_fn(u: str) -> tuple[int, str]:  # type: ignore[misc]
                return gespeichert

    else:
        url = os.environ.get("GATE_HEALTH_URL", "")
        if not url:
            print("FEHLER: GATE_HEALTH_URL nicht gesetzt", file=sys.stderr)
            return 2
        try:
            expected_status = int(os.environ.get("GATE_EXPECTED_STATUS", "200"))
            retries = int(os.environ.get("GATE_RETRIES", "5"))
            retry_delay = int(os.environ.get("GATE_RETRY_DELAY_SECONDS", "10"))
        except ValueError as e:
            print(f"FEHLER: Ungueltige numerische Eingabe: {e}", file=sys.stderr)
            return 2
        expected_text = os.environ.get("GATE_EXPECTED_TEXT") or None
        rollback_befehl = os.environ.get("GATE_ROLLBACK_COMMAND") or None

    bestanden, ergebnis = fuehre_health_check_aus(
        url, expected_status, expected_text, retries, retry_delay, http_fn
    )

    rollback_ausgefuehrt = False
    if not bestanden and rollback_befehl:
        print(
            f"Health-Check fehlgeschlagen. Fuehre Rollback aus: {rollback_befehl}",
            file=sys.stderr,
        )
        lauf = subprocess.run(
            rollback_befehl, shell=True, capture_output=True, text=True
        )
        rollback_ausgefuehrt = True
        if lauf.returncode != 0:
            print(
                f"WARNUNG: Rollback schlug fehl (Exit {lauf.returncode}):"
                f" {lauf.stderr}",
                file=sys.stderr,
            )

    # Befunde nach dem Gate-Vertrag: leer bei bestanden, sonst der Grund des
    # fehlgeschlagenen Health-Checks und, falls erfolgt, der Rollback.
    titel: list[str] = []
    if not bestanden:
        titel.append(f"Health-Check auf {url} fehlgeschlagen: {ergebnis}")
        if rollback_ausgefuehrt:
            titel.append("Rollback wurde ausgefuehrt.")

    schreibe_ausgabe("pass", "true" if bestanden else "false")
    schreibe_ausgabe("health_check_result", ergebnis)
    schreibe_ausgabe("rollback_executed", "true" if rollback_ausgefuehrt else "false")
    schreibe_ausgabe("findings_json", json.dumps(baue_befunde(titel)))

    if not bestanden:
        print(
            f"FEHLER: Health-Check fehlgeschlagen: {ergebnis}", file=sys.stderr
        )
        return 1

    print(f"Health-Check bestanden: {ergebnis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
