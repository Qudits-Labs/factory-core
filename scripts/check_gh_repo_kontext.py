#!/usr/bin/env python3
"""Prueft, dass jeder gh-Aufruf in einem Workflow gegen ein ausdrueckliches
Repositorium laeuft.

Hintergrund
Die Jobs eines wiederverwendbaren Ablaufs checken den Kern aus, nicht das
Produkt (siehe check_anschluss.py, Regel B). gh leitet das Repositorium ohne
weitere Angabe aus dem Arbeitsverzeichnis ab -- also aus dem Kern. Beim ersten
echten Durchlauf scheiterte `gh issue comment 18` mit «Could not resolve to an
issue», weil das Issue nur im Produktrepositorium existiert. Der Fehler war im
Kern nicht sichtbar: dort laufen keine echten Uebergaenge.

Regel
Fuer jeden run:-Text eines Jobs werden gh-Aufrufe gesucht, in zwei Formen:

  1. Python-Listenliteral  ["gh", ...]   (subprocess.run und Verwandte)
  2. Shell-Zeile           gh <befehl> ...

Jeder gefundene Aufruf muss eine der beiden Bedingungen erfuellen:

  a) `--repo` (oder `-R`) steht im Aufruf selbst, oder
  b) `GH_REPO` ist in der env: des Workflows, des Jobs oder des Schritts
     gesetzt. gh liest die Variable und wertet sie fuer jeden Aufruf aus.

Zusatz fuer Form 1: reicht der Aufruf eine eigene Umgebung (`env=`) an
subprocess, muss diese `os.environ` einschliessen -- sonst kommt GH_REPO aus
der Job-Umgebung nicht bei gh an.

Grenzen
Die Pruefung ist statisch und textbasiert. Sie sieht gh-Aufrufe, die aus
Variablen zusammengesetzt werden (z. B. `cmd = ["gh"]; cmd.append(...)`),
nicht. Kommentarzeilen werden uebersprungen.

Aufruf:
    python3 scripts/check_gh_repo_kontext.py <verzeichnis-oder-datei> ...

Exit-Codes:
    0 - kein Befund
    1 - mindestens ein Befund
    2 - technischer Fehler
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FEHLER: PyYAML fehlt (pip install pyyaml).", file=sys.stderr)
    raise SystemExit(2)

ENDUNGEN = {".yml", ".yaml"}

# Form 1: Python-Listenliteral, das mit "gh" beginnt
_PY_LISTE = re.compile(r"\[\s*[\"']gh[\"']\s*,")

# Form 2: Shell-Zeile, in der gh als Befehl steht. Vor gh darf nur
# Zeilenanfang, Leerraum oder ein Shell-Trenner stehen -- nicht ein
# Anfuehrungszeichen (das waere ein String) und kein Wortzeichen.
_SH_AUFRUF = re.compile(r"(?:^|[\s;&|(`])gh\s+[a-z]")

# Repositoriumsangabe im Aufruf: --repo, --repo=..., -R
_REPO_FLAG = re.compile(r"(?:^|[\s\"'])(?:--repo|-R)(?:[\s\"'=]|$)")

# Eigene Umgebung fuer subprocess
_ENV_ARG = re.compile(r"\benv\s*=")
# Formen, die die Prozessumgebung uebernehmen: env=os.environ,
# env={**os.environ, ...}, env=dict(os.environ, ...)
_ENV_UEBERNIMMT = re.compile(
    r"\benv\s*=\s*(?:os\.environ\b|\{\s*\*\*os\.environ\b|dict\(\s*os\.environ\b)"
)


def _hat_gh_repo(block: object) -> bool:
    return isinstance(block, dict) and "GH_REPO" in block


def _zeile_von(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _py_aufrufe(text: str) -> list[tuple[int, str, bool]]:
    """Gibt (Zeile, Aufruftext, umgebung_ohne_os_environ) je Listenliteral.

    Der Aufruftext reicht vom `[` bis zur schliessenden Klammer des
    umgebenden Funktionsaufrufs, damit `--repo` in der Liste und `env=` in den
    Schluesselwortargumenten gleichermassen sichtbar sind.
    """
    ergebnis: list[tuple[int, str, bool]] = []
    for treffer in _PY_LISTE.finditer(text):
        start = treffer.start()
        ende_liste = text.find("]", start)
        if ende_liste < 0:
            ende_liste = len(text)
        # Bis zur schliessenden runden Klammer des Funktionsaufrufs lesen;
        # geschweifte und eckige Klammern dazwischen ueberspringen.
        tiefe = 0
        ende = ende_liste
        for i in range(ende_liste, len(text)):
            z = text[i]
            if z in "{[(":
                tiefe += 1
            elif z in "}]":
                tiefe -= 1
            elif z == ")":
                if tiefe <= 0:
                    ende = i
                    break
                tiefe -= 1
        aufruf = text[start : ende + 1]
        env_ohne_environ = bool(_ENV_ARG.search(aufruf)) and not _ENV_UEBERNIMMT.search(aufruf)
        ergebnis.append((_zeile_von(text, start), aufruf, env_ohne_environ))
    return ergebnis


def _sh_aufrufe(text: str) -> list[tuple[int, str]]:
    """Gibt (Zeile, Aufruftext) je Shell-Aufruf von gh.

    Fortsetzungszeilen (Backslash am Ende) werden zum Aufruf gezaehlt.
    """
    ergebnis: list[tuple[int, str]] = []
    zeilen = text.split("\n")
    i = 0
    while i < len(zeilen):
        zeile = zeilen[i]
        if zeile.strip().startswith("#"):
            i += 1
            continue
        if _SH_AUFRUF.search(zeile):
            block = [zeile]
            j = i
            while zeilen[j].rstrip().endswith("\\") and j + 1 < len(zeilen):
                j += 1
                block.append(zeilen[j])
            ergebnis.append((i + 1, "\n".join(block)))
            i = j + 1
            continue
        i += 1
    return ergebnis


def _pruefe_datei(pfad: Path) -> tuple[list[str], int]:
    """Gibt (Befunde, Anzahl gefundener gh-Aufrufe) fuer eine Datei zurueck."""
    befunde: list[str] = []
    try:
        dokument = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    except Exception as ausnahme:
        return [f"{pfad.name}: nicht lesbar: {ausnahme}"], 0
    if not isinstance(dokument, dict):
        return [], 0

    workflow_env = _hat_gh_repo(dokument.get("env"))
    jobs = dokument.get("jobs")
    if not isinstance(jobs, dict):
        return [], 0

    anzahl = 0
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        job_env = workflow_env or _hat_gh_repo(job.get("env"))
        schritte = job.get("steps")
        if not isinstance(schritte, list):
            continue
        for index, schritt in enumerate(schritte, start=1):
            if not isinstance(schritt, dict):
                continue
            run = schritt.get("run")
            if not isinstance(run, str):
                continue
            kontext = job_env or _hat_gh_repo(schritt.get("env"))
            name = schritt.get("name") or schritt.get("id") or f"Schritt {index}"
            ort = f"{pfad.name}: Job `{job_name}`, Schritt {index} ({name})"

            for zeile, aufruf, env_ohne_environ in _py_aufrufe(run):
                anzahl += 1
                hat_flag = bool(_REPO_FLAG.search(aufruf))
                if not hat_flag and not kontext:
                    befunde.append(
                        f"{ort}, run-Zeile {zeile}: gh-Aufruf ohne "
                        "Repositoriumskontext (kein --repo, kein GH_REPO in env)"
                    )
                elif not hat_flag and env_ohne_environ:
                    befunde.append(
                        f"{ort}, run-Zeile {zeile}: gh-Aufruf uebergibt eine "
                        "eigene Umgebung ohne os.environ -- GH_REPO aus der "
                        "Job-Umgebung erreicht gh nicht"
                    )

            for zeile, aufruf in _sh_aufrufe(run):
                anzahl += 1
                if not _REPO_FLAG.search(aufruf) and not kontext:
                    befunde.append(
                        f"{ort}, run-Zeile {zeile}: gh-Aufruf ohne "
                        "Repositoriumskontext (kein --repo, kein GH_REPO in env)"
                    )

    return befunde, anzahl


def _sammle(pfade: list[str]) -> list[Path]:
    dateien: list[Path] = []
    for eintrag in pfade:
        p = Path(eintrag)
        if p.is_dir():
            dateien.extend(
                sorted(d for d in p.iterdir() if d.suffix in ENDUNGEN and d.is_file())
            )
        elif p.is_file():
            dateien.append(p)
        else:
            print(f"FEHLER: {eintrag} existiert nicht.", file=sys.stderr)
            raise SystemExit(2)
    return dateien


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    dateien = _sammle(argv)
    alle_befunde: list[str] = []
    aufrufe = 0
    for datei in dateien:
        befunde, anzahl = _pruefe_datei(datei)
        aufrufe += anzahl
        alle_befunde.extend(befunde)

    for befund in alle_befunde:
        print(f"FEHLER {befund}")
    if alle_befunde:
        print(
            f"{len(dateien)} Workflow-Datei(en) geprueft, {aufrufe} gh-Aufruf(e) "
            f"gefunden, {len(alle_befunde)} Befund(e)."
        )
        return 1
    print(
        f"{len(dateien)} Workflow-Datei(en) geprueft, {aufrufe} gh-Aufruf(e) "
        "gefunden, jeder mit Repositoriumskontext."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
