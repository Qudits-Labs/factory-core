#!/usr/bin/env python3
"""Prueft, dass dieses Repository keine eigenen Secrets braucht.

Der Kern hat keine Laufzeit, kein Deployment und keinen Dienst, an dem er sich
anmelden muesste. Ein Workflow, der hier ausgefuehrt wird, soll deshalb nichts
im Kontext haben, das sich zu stehlen lohnt.

Die Regel unterscheidet zwei Faelle:

* Ein `workflow_call`-Workflow wird von einem fremden Repository aufgerufen.
  Er darf Secrets in seinem `secrets:`-Block deklarieren und verwenden; die
  Werte stammen vom Aufrufer und liegen nie hier.
* Ein Workflow, den dieses Repository selbst ausloest (`push`, `pull_request`,
  `schedule` und alles Weitere), darf ausser `GITHUB_TOKEN` kein Secret
  verwenden. Sonst muesste hier eines hinterlegt sein.

Aufruf:
    python3 scripts/check_no_secrets.py [pfad ...]

Exit 0 sauber, Exit 1 Fund, Exit 2 Datei nicht lesbar.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FEHLER: PyYAML fehlt. Installation: pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)

ENDUNGEN = {".yml", ".yaml"}
ERLAUBT_IMMER = {"GITHUB_TOKEN"}

# Ein Secret wirkt nur innerhalb eines GitHub-Ausdrucks. Die Suche laeuft
# deshalb zweistufig: erst die Ausdruecke herausloesen, dann darin nach dem
# Zugriff suchen. Eine Suche allein nach `secrets.` im ganzen Text trifft auch
# Dateinamen und Fliesstext -- dieser Falschtreffer hat den ersten CI-Lauf
# scheitern lassen, an einem Skript, das `check_no_secrets.py` heisst.
AUSDRUCK_MUSTER = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
SECRET_MUSTER = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_-]*)")


def workflow_dateien(pfade: list[str]) -> list[Path]:
    if not pfade:
        pfade = [".github/workflows"]
    gefunden: list[Path] = []
    for eintrag in pfade:
        p = Path(eintrag)
        if p.is_dir():
            gefunden.extend(sorted(k for k in p.rglob("*") if k.suffix in ENDUNGEN))
        elif p.is_file():
            gefunden.append(p)
    return gefunden


def on_block(dokument: object) -> dict | list | str | None:
    """`on` wird von PyYAML nach YAML 1.1 als True gelesen, wenn es nackt steht."""
    if not isinstance(dokument, dict):
        return None
    if "on" in dokument:
        return dokument["on"]
    return dokument.get(True)


def deklarierte_secrets(block: object) -> set[str]:
    if not isinstance(block, dict):
        return set()
    aufruf = block.get("workflow_call")
    if not isinstance(aufruf, dict):
        return set()
    secrets = aufruf.get("secrets")
    if isinstance(secrets, dict):
        return set(secrets.keys())
    if isinstance(secrets, list):
        return {s for s in secrets if isinstance(s, str)}
    return set()


def main(argv: list[str]) -> int:
    dateien = workflow_dateien(argv)
    if not dateien:
        print("Keine Workflow-Datei gefunden. Nichts zu pruefen.")
        return 0

    funde: list[str] = []
    for datei in dateien:
        try:
            roh = datei.read_text(encoding="utf-8")
            inhalt = yaml.safe_load(roh)
        except (OSError, yaml.YAMLError) as fehler:
            print(f"FEHLER: {datei} nicht lesbar: {fehler}", file=sys.stderr)
            return 2

        block = on_block(inhalt)
        erlaubt = ERLAUBT_IMMER | deklarierte_secrets(block)
        verwendet: set[str] = set()
        for ausdruck in AUSDRUCK_MUSTER.findall(roh):
            verwendet.update(SECRET_MUSTER.findall(ausdruck))
        for name in sorted(verwendet - erlaubt):
            funde.append(
                f"{datei}: verwendet `secrets.{name}`, ohne es im "
                "`workflow_call`-Block zu deklarieren"
            )

    for zeile in funde:
        print(zeile, file=sys.stderr)

    if funde:
        print(
            f"\n{len(funde)} Verstoss/Verstoesse in {len(dateien)} geprueften "
            "Dateien.\nDieses Repository haelt keine Secrets. Ein Wert, der von "
            "aussen kommt, gehoert in den `workflow_call`-Block und wird vom "
            "aufrufenden Repository gesetzt.",
            file=sys.stderr,
        )
        return 1

    print(f"{len(dateien)} Workflow-Datei(en) geprueft, keine offene Secret-Referenz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
