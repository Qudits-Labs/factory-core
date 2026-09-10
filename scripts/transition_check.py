#!/usr/bin/env python3
"""Prueft Zustandsuebergaenge in der agentischen Factory-Pipeline.

Zweck:
    Verifiziert Akteur-Berechtigung, Versuchszaehlung und Rollenabbildung
    fuer Zustandsuebergaenge. Wird von transition.yml aufgerufen.

    Sicherheitsauflage: `role_label_map_json` bildet Labels auf Rollennamen
    ab, nicht auf Workflow-Pfade. Nur die sechs definierten Rollennamen sind
    als Werte erlaubt. Ein freier Pfad als Wert wuerde die Zustandsmaschine
    umleitbar machen.

    Wird keine Tabelle uebergeben, gilt die Standardfolge aus
    `factory_phasen.py`. Ein Produktrepositorium, das ihr folgt, muss die
    Abbildung nicht mitbringen; eines, das abweicht, uebergibt seine eigene
    und ersetzt die Standardtabelle damit vollstaendig.

    Akteur-Logik:
      - Transition-Identitaet: regulaerer Uebergang
      - Login aus human_gate_logins: erlaubt, wird als menschlicher Eingriff
        protokolliert (im Workflow via Kommentar ins Issue)
      - Jeder andere Login: verweigert, Workflow setzt flag:unauthorized-transition

Aufruf (Fixture-Modus fuer Tests):
    python3 scripts/transition_check.py <fixture-verzeichnis>

    Das Verzeichnis muss enthalten:
      config.txt           - Schluessel=Wert-Paare:
                               actor_login=bot-account
                               transition_identity_login=bot-account
                               human_gate_logins=alice,bob
                               new_label=status:in-review
                               max_attempts=3
                               current_attempts=0
                               erwartete_rolle=solution-architect   (optional)
      role_label_map.json  - optional; JSON-Objekt label -> rollenname.
                             Fehlt die Datei, gilt die Standardtabelle.

    Steht `erwartete_rolle` in der config.txt, prueft das Skript die
    bestimmte Rolle dagegen. Ein leerer Wert ist eine echte Erwartung: dieses
    Label darf keine Rolle haben. Damit ist die Standardtabelle selbst
    gemessen und nicht nur ihre Lesbarkeit.

Aufruf (Produktiv via GitHub Actions):
    Liest aus Umgebungsvariablen:
      GATE_ACTOR_LOGIN
      GATE_TRANSITION_IDENTITY_LOGIN
      GATE_HUMAN_GATE_LOGINS       (komma-getrennt)
      GATE_NEW_LABEL
      GATE_MAX_ATTEMPTS            (Default: 3)
      GATE_ROLE_LABEL_MAP_JSON     (leer: Standardtabelle)
      GATE_CURRENT_ATTEMPTS        (Default: 0)
    Schreibt Outputs in GITHUB_OUTPUT.

Exit-Codes:
    0 - Uebergang erlaubt, Vorbedingungen erfuellt
    1 - Uebergang verweigert oder Vorbedingung nicht erfuellt
    2 - Technischer Fehler
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Die Rollenliste und die Standardtabelle stehen in factory_phasen.py, damit
# es sie nur einmal gibt. Zwei Kopien derselben Liste laufen auseinander.
from factory_phasen import (
    ERLAUBTE_ROLLENNAMEN,
    STANDARD_ROLLE_JE_LABEL,
    lade_map,
    validiere_rollen_map,
)

__all__ = ["ERLAUBTE_ROLLENNAMEN"]


def schreibe_ausgabe(schluessel: str, wert: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{schluessel}={wert}\n")
    else:
        print(f"  {schluessel}: {wert}")


def pruefe_akteur(
    actor: str,
    transition_identity: str,
    human_gate_logins: list[str],
) -> tuple[bool, bool, str]:
    """Gibt (erlaubt, ist_mensch, meldung) zurueck."""
    if actor == transition_identity:
        return True, False, f"Transition-Identitaet {actor!r} erkannt"
    if actor in human_gate_logins:
        return True, True, f"Menschlicher Eingriff durch {actor!r} (wird protokolliert)"
    return (
        False,
        False,
        f"Unbekannter Akteur {actor!r} -- nicht in transition_identity_login"
        f" oder human_gate_logins",
    )


def pruefe_versuche(aktuell: int, maximum: int) -> tuple[bool, str]:
    if aktuell >= maximum:
        return False, f"Maximale Versuche erreicht: {aktuell}/{maximum}"
    return True, f"Versuch {aktuell + 1}/{maximum}"


def lade_fixture(verzeichnis: Path) -> tuple[dict[str, str], str]:
    """Gibt (config, unveraenderte Rollentabelle als Text) zurueck.

    Fehlt `role_label_map.json`, bleibt der Text leer und die Standardtabelle
    aus factory_phasen.py gilt.
    """
    config_datei = verzeichnis / "config.txt"
    map_datei = verzeichnis / "role_label_map.json"

    config: dict[str, str] = {}
    if config_datei.exists():
        for zeile in config_datei.read_text(encoding="utf-8").splitlines():
            if "=" in zeile:
                k, v = zeile.split("=", 1)
                config[k.strip()] = v.strip()

    map_roh = map_datei.read_text(encoding="utf-8") if map_datei.exists() else ""

    return config, map_roh


def main(argv: list[str]) -> int:
    erwartete_rolle: str | None = None

    if argv and Path(argv[0]).is_dir():
        try:
            config, map_roh = lade_fixture(Path(argv[0]))
        except OSError as e:
            print(f"FEHLER: Fixture konnte nicht geladen werden: {e}", file=sys.stderr)
            return 2

        erwartete_rolle = config.get("erwartete_rolle")
        actor = config.get("actor_login", "")
        transition_identity = config.get("transition_identity_login", "")
        human_gate_logins = [
            lbl.strip()
            for lbl in config.get("human_gate_logins", "").split(",")
            if lbl.strip()
        ]
        new_label = config.get("new_label", "")
        try:
            max_attempts = int(config.get("max_attempts", "3"))
            current_attempts = int(config.get("current_attempts", "0"))
        except ValueError as e:
            print(f"FEHLER: Ungueltige Zahl in config.txt: {e}", file=sys.stderr)
            return 2
    else:
        actor = os.environ.get("GATE_ACTOR_LOGIN", "")
        transition_identity = os.environ.get("GATE_TRANSITION_IDENTITY_LOGIN", "")
        human_gate_logins = [
            lbl.strip()
            for lbl in os.environ.get("GATE_HUMAN_GATE_LOGINS", "").split(",")
            if lbl.strip()
        ]
        new_label = os.environ.get("GATE_NEW_LABEL", "")
        map_roh = os.environ.get("GATE_ROLE_LABEL_MAP_JSON", "")
        try:
            max_attempts = int(os.environ.get("GATE_MAX_ATTEMPTS", "3"))
            current_attempts = int(os.environ.get("GATE_CURRENT_ATTEMPTS", "0"))
        except ValueError as e:
            print(f"FEHLER: Ungueltige numerische Eingabe: {e}", file=sys.stderr)
            return 2

    if not actor or not transition_identity or not new_label:
        print(
            "FEHLER: actor_login, transition_identity_login und new_label"
            " sind erforderlich",
            file=sys.stderr,
        )
        return 2

    # Rollenabbildung laden. Ohne Uebergabe gilt die Standardfolge aus
    # factory_phasen.py -- ein Produktrepositorium, das ihr folgt, muss die
    # Tabelle nicht mitbringen.
    try:
        role_label_map, map_herkunft = lade_map(map_roh, STANDARD_ROLLE_JE_LABEL)
    except json.JSONDecodeError as e:
        print(
            f"FEHLER: Die Rollentabelle ist kein gueltiges JSON: {e}",
            file=sys.stderr,
        )
        return 2
    except ValueError as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 2

    map_fehler = validiere_rollen_map(role_label_map)
    if map_fehler:
        for f in map_fehler:
            print(f"FEHLER: {f}", file=sys.stderr)
        return 2

    rollenname = role_label_map.get(new_label, "")
    akteur_erlaubt, ist_mensch, akteur_meldung = pruefe_akteur(
        actor, transition_identity, human_gate_logins
    )
    versuche_ok, versuche_meldung = pruefe_versuche(current_attempts, max_attempts)

    bestanden = akteur_erlaubt and versuche_ok

    schreibe_ausgabe("allowed", "true" if akteur_erlaubt else "false")
    schreibe_ausgabe("human_intervention", "true" if ist_mensch else "false")
    schreibe_ausgabe("role_name", rollenname)
    schreibe_ausgabe("attempts_ok", "true" if versuche_ok else "false")
    schreibe_ausgabe("attempts_current", str(current_attempts))
    schreibe_ausgabe("attempts_max", str(max_attempts))

    for meldung in [akteur_meldung, versuche_meldung]:
        if bestanden:
            print(meldung)
        else:
            print(f"  BEFUND: {meldung}", file=sys.stderr)

    print(f"  Rollentabelle: {map_herkunft}")
    if rollenname:
        print(f"  Rolle: {rollenname}")

    # Erwartungspruefung im Fixture-Modus. Ohne sie misst kein Test, was in der
    # Standardtabelle tatsaechlich steht -- ein stillschweigend entfernter
    # Eintrag bliebe unbemerkt, weil ein unbekanntes Label nur eine leere Rolle
    # ergibt und keinen Fehler. Massgeblich ist, ob der Schluessel dasteht:
    # `erwartete_rolle=` ohne Wert heisst, dieses Label darf keine Rolle haben.
    if erwartete_rolle is not None and rollenname != erwartete_rolle:
        print(
            f"FEHLER: Erwartet war Rolle {erwartete_rolle!r}, bestimmt wurde"
            f" {rollenname!r}.",
            file=sys.stderr,
        )
        return 1

    return 0 if bestanden else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
