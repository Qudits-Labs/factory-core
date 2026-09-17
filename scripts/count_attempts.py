#!/usr/bin/env python3
"""Zaehlt die bisherigen Agentenlaeufe eines Issues fuer eine Rolle.

Zweck:
    transition_check.py vergleicht GATE_CURRENT_ATTEMPTS mit GATE_MAX_ATTEMPTS.
    Bis zu diesem Skript stand dort fest '0': die Abbruchbedingung griff nie,
    ein Agent, der wiederholt scheiterte, wurde endlos neu gestartet. Die
    Quelle der Wahrheit gab es laengst -- der Schritt «Attempt-Eintrag
    schreiben» in transition.yml legt vor jedem Lauf einen Kommentar mit der
    Markierung `<!-- factory:attempt run=<id> -->` und einer Tabelle
    (Rolle, Akteur, Zeitstempel, Run-ID) ins Issue. Dieses Skript liest sie.

Zaehlweise:
    Pro Rolle. Gezaehlt wird jeder Kommentar, der die Markierung traegt und
    in dessen Tabellenzeile `| Rolle |` dieselbe Rolle steht wie beim
    anstehenden Uebergang. Laeufe anderer Rollen am selben Issue zaehlen
    nicht: ein Solution Architect, der dreimal gescheitert ist, verbraucht
    nicht das Kontingent des Implementers. Kommentare ohne Markierung werden
    ignoriert.

    Ein Kommentar mit Markierung, aber ohne Rollenzeile ist ein Befund
    (Exit 1), kein stilles 0: sonst wuerde eine Aenderung am Kommentarformat
    die Abbruchbedingung genauso lautlos ausser Kraft setzen wie die feste 0.

Rolle:
    Kommt aus GATE_ROLE. Fehlt die Variable, wird die Rolle wie in
    transition_check.py aus GATE_NEW_LABEL und GATE_ROLE_LABEL_MAP_JSON
    abgeleitet (Standardtabelle aus factory_phasen.py, wenn die Tabelle leer
    ist). Das ist noetig, weil dieser Schritt VOR transition_check.py laeuft
    und dessen Ausgabe `role_name` noch nicht existiert. Ein Label ohne Rolle
    ist kein Zustandslabel; dann gibt es nichts zu zaehlen, das Ergebnis ist
    0 und gh wird nicht aufgerufen.

Repositorium:
    Der gh-Aufruf traegt Owner und Name aus GITHUB_REPOSITORY ausdruecklich im
    Pfad (`repos/<owner>/<repo>/issues/<n>/comments`). `gh api` kennt kein
    `--repo`; die Platzhalter `{owner}/{repo}` wuerden an GH_REPO oder am
    Arbeitsverzeichnis haengen -- und das ist im Kern-Checkout der Kern, nicht
    das Produkt (siehe docs/gate-vertrag.md, Abschnitt "gh-Aufrufe").

Aufruf (Fixture-Modus fuer Tests, ohne Netz):
    python3 scripts/count_attempts.py <fixture-verzeichnis>

    Das Verzeichnis enthaelt:
      comments.json  - JSON-Array von Kommentaren, wie die GitHub-API sie
                       liefert; gelesen wird nur das Feld `body`.
      config.txt     - Schluessel=Wert-Paare:
                         rolle=implementer
                         erwartet=2          (optional; weicht die Zaehlung
                                              ab, endet das Skript mit 1)

Aufruf (Produktiv via GitHub Actions):
    Liest aus Umgebungsvariablen:
      GITHUB_REPOSITORY         owner/repo des aufrufenden Repositoriums
      GATE_ISSUE                Issue-Nummer
      GATE_ROLE                 Rollenname (optional, siehe oben)
      GATE_NEW_LABEL            Ziel-Label (wenn GATE_ROLE fehlt)
      GATE_ROLE_LABEL_MAP_JSON  Rollentabelle (leer: Standardtabelle)
      GH_TOKEN                  Token fuer gh
      GATE_COMMENTS_FILE        optional: Pfad zu einer JSON-Datei, die statt
                                `gh api` gelesen wird
    Schreibt `attempts=<n>` nach GITHUB_OUTPUT und die Zahl auf stdout.
    Alles andere geht auf stderr, damit stdout nur die Zahl traegt.

Exit-Codes:
    0 - gezaehlt (und, im Fixture-Modus, Erwartung erfuellt)
    1 - Befund: Erwartung verfehlt oder Attempt-Eintrag ohne Rollenzeile
    2 - Technischer Fehler (gh, JSON, fehlende Eingaben)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from factory_phasen import STANDARD_ROLLE_JE_LABEL, lade_map

MARKIERUNG = "<!-- factory:attempt run="

# Tabellenzeile `| Rolle | `implementer` |` -- die Backticks sind optional,
# damit ein Kommentar ohne Code-Formatierung ebenfalls zaehlt.
_ROLLENZEILE = re.compile(
    r"^\|\s*Rolle\s*\|\s*`?\s*([^|`]*?)\s*`?\s*\|", re.MULTILINE
)


def _meldung(text: str) -> None:
    print(text, file=sys.stderr)


def schreibe_ausgabe(schluessel: str, wert: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{schluessel}={wert}\n")


def rolle_aus_kommentar(body: str) -> str | None:
    """Gibt die Rolle aus der Tabellenzeile zurueck, oder None ohne Zeile."""
    treffer = _ROLLENZEILE.search(body)
    if not treffer:
        return None
    return treffer.group(1).strip()


def zaehle(kommentare: list[dict], rolle: str) -> tuple[int, list[str]]:
    """Gibt (Anzahl fuer die Rolle, Befunde) zurueck."""
    anzahl = 0
    befunde: list[str] = []
    for kommentar in kommentare:
        if not isinstance(kommentar, dict):
            continue
        body = kommentar.get("body")
        if not isinstance(body, str) or MARKIERUNG not in body:
            continue
        gefunden = rolle_aus_kommentar(body)
        if gefunden is None:
            kennung = kommentar.get("id", "?")
            befunde.append(
                f"Attempt-Eintrag (Kommentar {kennung}) traegt die Markierung,"
                " aber keine Zeile `| Rolle |` -- Zaehlung nicht moeglich."
            )
            continue
        if gefunden == rolle:
            anzahl += 1
    return anzahl, befunde


def _flach(wert: object) -> list[dict]:
    """Macht aus einem Array, einem Array von Arrays (`--slurp`) oder einer
    Folge aneinandergereihter Arrays eine flache Liste von Kommentaren."""
    ergebnis: list[dict] = []
    if isinstance(wert, list):
        for element in wert:
            if isinstance(element, list):
                ergebnis.extend(_flach(element))
            elif isinstance(element, dict):
                ergebnis.append(element)
    elif isinstance(wert, dict):
        ergebnis.append(wert)
    return ergebnis


def parse_kommentare(text: str) -> list[dict]:
    """Liest ein oder mehrere aneinandergereihte JSON-Dokumente."""
    decoder = json.JSONDecoder()
    position = 0
    ergebnis: list[dict] = []
    laenge = len(text)
    while position < laenge:
        while position < laenge and text[position].isspace():
            position += 1
        if position >= laenge:
            break
        wert, position = decoder.raw_decode(text, position)
        ergebnis.extend(_flach(wert))
    return ergebnis


def lade_kommentare_aus_datei(pfad: Path) -> list[dict]:
    return parse_kommentare(pfad.read_text(encoding="utf-8"))


def lade_kommentare_via_gh(repository: str, issue: str) -> list[dict]:
    endpunkt = f"repos/{repository}/issues/{issue}/comments"
    lauf = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpunkt],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ,
    )
    if lauf.returncode != 0:
        raise RuntimeError(
            f"gh api {endpunkt} endete mit Exit {lauf.returncode}: "
            f"{lauf.stderr.strip()[:400]}"
        )
    return parse_kommentare(lauf.stdout)


def lade_fixture(verzeichnis: Path) -> tuple[dict[str, str], list[dict]]:
    config: dict[str, str] = {}
    config_datei = verzeichnis / "config.txt"
    if config_datei.exists():
        for zeile in config_datei.read_text(encoding="utf-8").splitlines():
            if "=" in zeile:
                k, v = zeile.split("=", 1)
                config[k.strip()] = v.strip()
    kommentare_datei = verzeichnis / "comments.json"
    kommentare = (
        lade_kommentare_aus_datei(kommentare_datei)
        if kommentare_datei.exists()
        else []
    )
    return config, kommentare


def bestimme_rolle() -> tuple[str, str]:
    """Gibt (Rolle, Herkunft) fuer den Produktivmodus zurueck."""
    rolle = os.environ.get("GATE_ROLE", "").strip()
    if rolle:
        return rolle, "GATE_ROLE"
    label = os.environ.get("GATE_NEW_LABEL", "").strip()
    if not label:
        raise ValueError("GATE_ROLE oder GATE_NEW_LABEL ist erforderlich")
    tabelle, herkunft = lade_map(
        os.environ.get("GATE_ROLE_LABEL_MAP_JSON", ""), STANDARD_ROLLE_JE_LABEL
    )
    return tabelle.get(label, ""), f"Rollentabelle ({herkunft}) fuer {label!r}"


def main(argv: list[str]) -> int:
    erwartet: int | None = None

    if argv and Path(argv[0]).is_dir():
        try:
            config, kommentare = lade_fixture(Path(argv[0]))
        except (OSError, json.JSONDecodeError) as e:
            _meldung(f"FEHLER: Fixture konnte nicht geladen werden: {e}")
            return 2
        rolle = config.get("rolle", "").strip()
        if not rolle:
            _meldung("FEHLER: config.txt braucht `rolle=`")
            return 2
        if "erwartet" in config:
            try:
                erwartet = int(config["erwartet"])
            except ValueError as e:
                _meldung(f"FEHLER: Ungueltige Zahl in config.txt: {e}")
                return 2
        herkunft = "Fixture"
    else:
        try:
            rolle, herkunft = bestimme_rolle()
        except (ValueError, json.JSONDecodeError) as e:
            _meldung(f"FEHLER: {e}")
            return 2

        if not rolle:
            _meldung(f"Keine Rolle ({herkunft}) -- kein Zustandslabel, nichts zu zaehlen.")
            schreibe_ausgabe("attempts", "0")
            print(0)
            return 0

        datei = os.environ.get("GATE_COMMENTS_FILE", "").strip()
        try:
            if datei:
                kommentare = lade_kommentare_aus_datei(Path(datei))
            else:
                repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
                issue = os.environ.get("GATE_ISSUE", "").strip()
                if not repository or not issue:
                    _meldung("FEHLER: GITHUB_REPOSITORY und GATE_ISSUE sind erforderlich")
                    return 2
                kommentare = lade_kommentare_via_gh(repository, issue)
        except (OSError, json.JSONDecodeError, RuntimeError) as e:
            _meldung(f"FEHLER: Kommentare konnten nicht gelesen werden: {e}")
            return 2

    anzahl, befunde = zaehle(kommentare, rolle)

    for befund in befunde:
        _meldung(f"  BEFUND: {befund}")
    _meldung(f"  Rolle: {rolle} ({herkunft})")
    _meldung(f"  Kommentare gelesen: {len(kommentare)}")
    _meldung(f"  Versuche fuer diese Rolle: {anzahl}")

    if befunde:
        return 1

    if erwartet is not None and anzahl != erwartet:
        _meldung(f"FEHLER: Erwartet waren {erwartet} Versuche, gezaehlt wurden {anzahl}.")
        return 1

    schreibe_ausgabe("attempts", str(anzahl))
    print(anzahl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
