#!/usr/bin/env python3
"""Prueft, ob ein aufrufender Workflow seine Eingaben auch weiterreicht.

Der Defekt, den dieses Skript sucht, sieht harmlos aus: ein Workflow fuehrt
eine Eingabe in seinem eigenen `workflow_call`-Block, ruft einen anderen
Workflow dieses Repositoriums auf, der dieselbe Eingabe kennt -- und uebergibt
sie dort nicht. Der Aufrufer bietet damit einen Regler an, der nichts bewirkt.
Wer ihn setzt, bekommt still den Standardwert des aufgerufenen Ablaufs.

Genau daran scheitert eine Kette, in der ein Agent den naechsten anstoesst.
Der Ausloeser ist dann ein Bot, und die Claude-Code-Action weist einen
Bot-Ausloeser ab, solange sein Login nicht in `allowed_bots` steht. Die
Eingabe war vorhanden, der Durchgriff fehlte, und der Fehler zeigte sich erst
im Lauf.

Die Regel ist deshalb eng gefasst und nicht zu bevormundend:

    Fuehrt der aufrufende Workflow eine Eingabe (oder ein Secret), die der
    aufgerufene ebenfalls fuehrt, muss sie im Aufruf uebergeben werden.

Eine Eingabe, die nur der aufgerufene Ablauf kennt, bleibt unberuehrt -- sie
wird im Aufrufer berechnet oder hat einen Standardwert, und beides ist
zulaessig. Erst wenn der Aufrufer denselben Regler nach aussen anbietet, ist
das Nichtweiterreichen ein Widerspruch.

Diese Regel allein reicht nicht. Sie greift erst, wenn der Aufrufer den Regler
ueberhaupt anbietet -- ein Aufrufer, der ihn gar nicht erst fuehrt, faellt
durch. Genau so lag der Fall bei `allowed_bots`. Deshalb die zweite Regel:

    Traegt die Beschreibung einer Eingabe oder eines Secrets im aufgerufenen
    Ablauf die Markierung [durchgriff-pflicht], muss jeder Aufrufer sie selbst
    als Eingabe fuehren und weiterreichen.

Was durchgriffspflichtig ist, entscheidet damit der aufgerufene Ablauf und
steht dort, wo es gilt. Der Kern kennt zwei Faelle: die Zugangsart zum Modell
und die Liste erlaubter Bot-Ausloeser. In beiden bedeutet ein Standardwert
nicht "sinnvolle Voreinstellung", sondern "laeuft nicht".

Aufruf:
    python3 scripts/check_durchgriff.py .github/workflows
    python3 scripts/check_durchgriff.py tests/fixtures/sauber

Exit-Codes:
    0 - kein Befund
    1 - mindestens ein Durchgriff fehlt
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

# OWNER/REPO/.github/workflows/DATEI@REF
_VOLLFORM = re.compile(
    r"^[^/]+/[^/]+/\.github/workflows/(?P<datei>[^/@]+\.ya?ml)@.+$"
)
# ./.github/workflows/DATEI
_KURZFORM = re.compile(r"^\./(?:.*/)?(?P<datei>[^/]+\.ya?ml)$")


def _workflow_call(dokument: object) -> dict | None:
    """Gibt den workflow_call-Block zurueck, falls vorhanden.

    `on:` liest PyYAML als booleschen Schluessel True -- beide Schreibweisen
    werden geprueft.
    """
    if not isinstance(dokument, dict):
        return None
    ausloeser = dokument.get("on", dokument.get(True))
    if not isinstance(ausloeser, dict):
        return None
    block = ausloeser.get("workflow_call")
    return block if isinstance(block, dict) else None


MARKIERUNG = "[durchgriff-pflicht]"


def _schluessel(block: dict | None, name: str) -> set[str]:
    if not block:
        return set()
    abschnitt = block.get(name)
    return set(abschnitt) if isinstance(abschnitt, dict) else set()


def _pflichtig(block: dict | None, name: str) -> set[str]:
    """Namen, deren Beschreibung die Durchgriff-Markierung traegt."""
    if not block:
        return set()
    abschnitt = block.get(name)
    if not isinstance(abschnitt, dict):
        return set()
    treffer = set()
    for schluessel, eigenschaften in abschnitt.items():
        if not isinstance(eigenschaften, dict):
            continue
        if MARKIERUNG in str(eigenschaften.get("description", "")):
            treffer.add(schluessel)
    return treffer


def _sammle(pfade: list[str]) -> list[Path]:
    gefunden: list[Path] = []
    for eintrag in pfade:
        p = Path(eintrag)
        if p.is_dir():
            gefunden.extend(sorted(k for k in p.rglob("*") if k.suffix in ENDUNGEN))
        elif p.suffix in ENDUNGEN:
            gefunden.append(p)
    return gefunden


def _zielname(wert: str) -> str | None:
    treffer = _VOLLFORM.match(wert) or _KURZFORM.match(wert)
    return treffer.group("datei") if treffer else None


def main(argv: list[str]) -> int:
    if not argv:
        print("Aufruf: check_durchgriff.py <verzeichnis-oder-datei> ...", file=sys.stderr)
        return 2

    dateien = _sammle(argv)
    if not dateien:
        print("FEHLER: Keine Workflow-Dateien gefunden.", file=sys.stderr)
        return 2

    dokumente: dict[str, object] = {}
    for datei in dateien:
        try:
            dokumente[datei.name] = yaml.safe_load(datei.read_text(encoding="utf-8"))
        except yaml.YAMLError as fehler:
            print(f"FEHLER: {datei} ist kein gueltiges YAML: {fehler}", file=sys.stderr)
            return 2

    befunde: list[str] = []
    geprueft = 0

    for datei in dateien:
        dokument = dokumente[datei.name]
        if not isinstance(dokument, dict):
            continue
        jobs = dokument.get("jobs")
        if not isinstance(jobs, dict):
            continue

        aufrufer = _workflow_call(dokument)
        aufrufer_eingaben = _schluessel(aufrufer, "inputs")
        aufrufer_secrets = _schluessel(aufrufer, "secrets")

        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            wert = job.get("uses")
            if not isinstance(wert, str):
                continue
            ziel = _zielname(wert)
            if ziel is None or ziel not in dokumente or ziel == datei.name:
                continue

            aufgerufen = _workflow_call(dokumente[ziel])
            if aufgerufen is None:
                continue

            geprueft += 1

            uebergeben = job.get("with")
            uebergeben = set(uebergeben) if isinstance(uebergeben, dict) else set()

            fehlend = sorted(
                (aufrufer_eingaben & _schluessel(aufgerufen, "inputs")) - uebergeben
            )
            for name in fehlend:
                befunde.append(
                    f"{datei.name}: Job '{job_id}' ruft {ziel} auf und fuehrt "
                    f"selbst die Eingabe '{name}', reicht sie aber nicht weiter. "
                    "Wer sie setzt, bekommt still den Standardwert"
                )

            # Zweite Regel: was der aufgerufene Ablauf als durchgriffspflichtig
            # markiert, muss der Aufrufer anbieten und weiterreichen.
            for name in sorted(_pflichtig(aufgerufen, "inputs")):
                if name not in aufrufer_eingaben:
                    befunde.append(
                        f"{datei.name}: Job '{job_id}' ruft {ziel} auf, dessen "
                        f"Eingabe '{name}' als durchgriffspflichtig markiert "
                        "ist. Der Aufrufer fuehrt sie nicht -- ein "
                        "Produktrepositorium kann sie damit nicht setzen"
                    )
                elif name not in uebergeben:
                    befunde.append(
                        f"{datei.name}: Job '{job_id}' fuehrt die "
                        f"durchgriffspflichtige Eingabe '{name}', reicht sie "
                        "aber nicht an " + ziel + " weiter"
                    )

            secrets_block = job.get("secrets")
            if secrets_block == "inherit":
                continue
            gesetzt = set(secrets_block) if isinstance(secrets_block, dict) else set()
            fehlend_secrets = sorted(
                (aufrufer_secrets & _schluessel(aufgerufen, "secrets")) - gesetzt
            )
            for name in fehlend_secrets:
                befunde.append(
                    f"{datei.name}: Job '{job_id}' ruft {ziel} auf und fuehrt "
                    f"selbst das Secret '{name}', reicht es aber nicht weiter"
                )

            for name in sorted(_pflichtig(aufgerufen, "secrets")):
                if name not in aufrufer_secrets:
                    befunde.append(
                        f"{datei.name}: Job '{job_id}' ruft {ziel} auf, dessen "
                        f"Secret '{name}' als durchgriffspflichtig markiert "
                        "ist. Der Aufrufer fuehrt es nicht"
                    )
                elif name not in gesetzt:
                    befunde.append(
                        f"{datei.name}: Job '{job_id}' fuehrt das "
                        f"durchgriffspflichtige Secret '{name}', reicht es "
                        "aber nicht an " + ziel + " weiter"
                    )

    if befunde:
        for meldung in befunde:
            print(f"BEFUND: {meldung}", file=sys.stderr)
        print(f"\n{len(befunde)} fehlende(r) Durchgriff(e).", file=sys.stderr)
        return 1

    if not geprueft:
        print("Kein Aufruf eines Workflows aus derselben Menge -- nichts zu pruefen.")
        return 0

    print(f"{geprueft} Aufruf(e) geprueft, jede gemeinsame Eingabe wird weitergereicht.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
