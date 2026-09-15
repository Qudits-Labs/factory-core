#!/usr/bin/env python3
"""Prueft zwei Fehler, die erst beim Anschluss eines Produktrepositoriums
sichtbar wurden.

FEHLER 1 -- Rechtekette (Regel A)
GitHub hat einen Aufruf von transition.yml mit startup_failure abgewiesen:
«run-agent.yml ... is requesting 'contents: write, pull-requests: write',
but is only allowed 'contents: read, pull-requests: none'».
GitHub-Dokumentation: «The GITHUB_TOKEN permissions passed from the caller
workflow can be only downgraded (not elevated) by the called workflow.»
Die wirksamen Rechte des aufrufenden Jobs setzen damit die Obergrenze; ein
aufgerufener Workflow, der mehr anfordert, wird von GitHub abgelehnt.
Der Fehler war nicht im Kern-Repository sichtbar, weil dort keine echten
Laeufe stattfinden -- er zeigte sich erst beim ersten Produktrepo.

FEHLER 2 -- Falscher Checkout (Regel B)
GitHub-Dokumentation: «If the called workflow uses actions/checkout, the
action checks out the contents of the repository that hosts the caller
workflow, not the called workflow.»
Alle workflow_call-Workflows des Kerns riefen actions/checkout ohne
repository: auf und starteten danach python3 scripts/...py, lasen
role-frameworks/ oder schemas/ -- Dateien, die im Produktrepo nicht liegen.
Auch das zeigte sich erst beim Anschluss.

Regeln:

REGEL A -- Rechtekette
Fuer jeden Job mit uses:, dessen Ziel in der geprueften Menge liegt:
wirksame Rechte des aufrufenden Jobs = Job-permissions falls vorhanden,
sonst Workflow-permissions. Hat der Aufrufer weder Job- noch Workflow-Block,
ist das ein Befund (Rechte nicht deklariert). Angeforderte Rechte des
aufgerufenen Workflows = je Scope das Maximum aus dessen Workflow-permissions
und allen Job-permissions (Rangfolge none < read < write; die Kurzformen
read-all/write-all gelten fuer jeden Scope). Ein Scope, den der Aufrufer
nicht nennt, gilt als none (GitHub-Doku: «If you specify the access for any
of these permissions, all of those that are not specified are set to none»).
Befund je Scope, bei dem angefordert > erlaubt.

REGEL B -- Der Kern checkt sich selbst aus
Nur fuer Workflows mit workflow_call (die anderen laufen im Kern selbst;
dort gehoert der github-Kontext dem Kern). Fuer jeden Job mit steps:: hat ein
run:-Text einen Verweis auf scripts/, role-frameworks/ oder schemas/, muss
derselbe Job einen Schritt haben, dessen uses: mit actions/checkout@ beginnt
und dessen with: sowohl repository als auch ref mit nicht leerem Wert setzt.
Zusaetzlich: hat der Workflow workflow_call, aber keinen Input core_ref, und
braucht ein Job Kern-Dateien, ist das ein eigener Befund (der Aufrufer kann
den Kern dann nicht pinnen).

Aufruf:
    python3 scripts/check_anschluss.py <verzeichnis-oder-datei> ...

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

# OWNER/REPO/.github/workflows/DATEI@REF
_VOLLFORM = re.compile(
    r"^[^/]+/[^/]+/\.github/workflows/(?P<datei>[^/@]+\.ya?ml)@.+$"
)
# ./.github/workflows/DATEI
_KURZFORM = re.compile(r"^\./(?:.*/)?(?P<datei>[^/]+\.ya?ml)$")

# Kern-Pfade, auf die ein run:-Text verweisen kann
_KERN_PFADE = re.compile(r"scripts/|role-frameworks/|schemas/")

# Bekannte GitHub-Permission-Scopes
_ALLE_SCOPES: frozenset[str] = frozenset({
    "actions",
    "attestations",
    "checks",
    "contents",
    "deployments",
    "discussions",
    "id-token",
    "issues",
    "packages",
    "pages",
    "pull-requests",
    "repository-projects",
    "security-events",
    "statuses",
    "workflows",
})

# Rangfolge: none=0, read=1, write=2
_RANG: dict[str, int] = {"none": 0, "read": 1, "write": 2}


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


def _parse_permissions(block: object) -> dict[str, str]:
    """Liest einen permissions-Block und gibt je Scope 'none'/'read'/'write' zurueck."""
    if block is None:
        return {s: "none" for s in _ALLE_SCOPES}
    if block == "read-all":
        return {s: "read" for s in _ALLE_SCOPES}
    if block == "write-all":
        return {s: "write" for s in _ALLE_SCOPES}
    if not isinstance(block, dict):
        return {s: "none" for s in _ALLE_SCOPES}
    ergebnis = {s: "none" for s in _ALLE_SCOPES}
    for scope, stufe in block.items():
        if isinstance(scope, str) and scope in _ALLE_SCOPES and stufe in _RANG:
            ergebnis[scope] = stufe
    return ergebnis


def _max_perms(bloecke: list[object]) -> dict[str, str]:
    """Maximum mehrerer permissions-Bloecke."""
    ergebnis = {s: "none" for s in _ALLE_SCOPES}
    for block in bloecke:
        parsed = _parse_permissions(block)
        for scope in _ALLE_SCOPES:
            if _RANG[parsed[scope]] > _RANG[ergebnis[scope]]:
                ergebnis[scope] = parsed[scope]
    return ergebnis


def _aufgerufen_max(dokument: dict) -> dict[str, str]:
    """Maximale Rechte, die der aufgerufene Workflow anfordert.

    Das Maximum aus Workflow-permissions und allen Job-permissions, weil
    der Workflow-Level die Obergrenze fuer alle Jobs setzt -- und GitHub
    diesen Wert gegen die Caller-Permissions prueft.
    """
    bloecke: list[object] = [dokument.get("permissions")]
    jobs = dokument.get("jobs") or {}
    for job in jobs.values():
        if isinstance(job, dict) and "permissions" in job:
            bloecke.append(job["permissions"])
    return _max_perms(bloecke)


def _job_wirksame_perms(job: dict, dokument: dict) -> dict[str, str] | None:
    """Wirksame Rechte des aufrufenden Jobs. None = nicht deklariert.

    Job-permissions haben Vorrang vor Workflow-permissions. Hat der Job
    keinen eigenen Block, gilt der Workflow-Block. Fehlen beide, ist das
    ein Befund -- der Canary verlangt die Deklaration ohnehin.
    """
    if "permissions" in job:
        return _parse_permissions(job["permissions"])
    if "permissions" in dokument:
        return _parse_permissions(dokument["permissions"])
    return None


def _zielname(wert: str) -> str | None:
    treffer = _VOLLFORM.match(wert) or _KURZFORM.match(wert)
    return treffer.group("datei") if treffer else None


def _job_braucht_kern_dateien(job: dict) -> bool:
    """True wenn ein run:-Schritt auf scripts/, role-frameworks/ oder schemas/ verweist."""
    steps = job.get("steps") or []
    for schritt in steps:
        if not isinstance(schritt, dict):
            continue
        run = schritt.get("run", "")
        if isinstance(run, str) and _KERN_PFADE.search(run):
            return True
    return False


def _job_hat_kern_checkout(job: dict) -> bool:
    """True wenn der Job einen Checkout mit nicht leerem repository: und ref: hat."""
    steps = job.get("steps") or []
    for schritt in steps:
        if not isinstance(schritt, dict):
            continue
        uses = schritt.get("uses", "")
        if not isinstance(uses, str):
            continue
        if not uses.startswith("actions/checkout@"):
            continue
        mitm = schritt.get("with") or {}
        if not isinstance(mitm, dict):
            continue
        repo = mitm.get("repository", "")
        ref = mitm.get("ref", "")
        if repo and ref:
            return True
    return False


def _sammle(pfade: list[str]) -> list[Path]:
    gefunden: list[Path] = []
    for eintrag in pfade:
        p = Path(eintrag)
        if p.is_dir():
            gefunden.extend(sorted(k for k in p.rglob("*") if k.suffix in ENDUNGEN))
        elif p.suffix in ENDUNGEN:
            gefunden.append(p)
    return gefunden


def main(argv: list[str]) -> int:
    if not argv:
        print("Aufruf: check_anschluss.py <verzeichnis-oder-datei> ...", file=sys.stderr)
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

    for datei in dateien:
        dokument = dokumente[datei.name]
        if not isinstance(dokument, dict):
            continue
        jobs = dokument.get("jobs")
        if not isinstance(jobs, dict):
            continue

        wf_perms = dokument.get("permissions") if "permissions" in dokument else None

        # -----------------------------------------------------------------------
        # Regel A -- Rechtekette
        # -----------------------------------------------------------------------
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            wert = job.get("uses")
            if not isinstance(wert, str):
                continue
            ziel = _zielname(wert)
            if ziel is None or ziel not in dokumente or ziel == datei.name:
                continue
            aufgerufen = dokumente[ziel]
            if not isinstance(aufgerufen, dict):
                continue

            angefordert = _aufgerufen_max(aufgerufen)
            erlaubt = _job_wirksame_perms(job, dokument)

            if erlaubt is None:
                befunde.append(
                    f"{datei.name}: Job '{job_id}' ruft {ziel} auf, hat aber "
                    "weder Job- noch Workflow-permissions deklariert. Ohne "
                    "Deklaration sind die Rechte nicht steuerbar"
                )
                continue

            verletzte = sorted(
                s for s in _ALLE_SCOPES
                if _RANG[angefordert[s]] > _RANG[erlaubt[s]]
            )
            if verletzte:
                anf_str = ", ".join(f"{s}: {angefordert[s]}" for s in verletzte)
                erl_str = ", ".join(f"{s}: {erlaubt[s]}" for s in verletzte)
                befunde.append(
                    f"{datei.name}: Job '{job_id}' ruft {ziel} auf, das "
                    f"'{anf_str}' anfordert, der Job erlaubt aber nur "
                    f"'{erl_str}'. Ein aufgerufener Workflow bekommt nie "
                    "mehr als der Aufrufer"
                )

        # -----------------------------------------------------------------------
        # Regel B -- Der Kern checkt sich selbst aus (nur workflow_call)
        # -----------------------------------------------------------------------
        wc = _workflow_call(dokument)
        if wc is None:
            continue  # kein workflow_call -- Regel B nicht anwendbar

        wc_inputs = wc.get("inputs") or {}
        hat_core_ref = "core_ref" in wc_inputs

        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            if "uses" in job:
                continue  # wiederverwendbarer Workflow, keine steps
            if "steps" not in job:
                continue
            if not _job_braucht_kern_dateien(job):
                continue

            if not hat_core_ref:
                befunde.append(
                    f"{datei.name}: Job '{job_id}' verwendet Kern-Dateien "
                    "(scripts/, role-frameworks/ oder schemas/), aber der "
                    "Workflow hat keinen Input 'core_ref'. Der Aufrufer kann "
                    "den Kern-Stand damit nicht pinnen"
                )

            if not _job_hat_kern_checkout(job):
                befunde.append(
                    f"{datei.name}: Job '{job_id}' verwendet Kern-Dateien "
                    "(scripts/, role-frameworks/ oder schemas/), checkt aber "
                    "nur das Repositorium des Aufrufers aus "
                    "(actions/checkout ohne repository:/ref:). Der "
                    "github-Kontext gehoert dem Aufrufer; der Kern muss sich "
                    "selbst unter core_ref auschecken"
                )

    if befunde:
        for meldung in befunde:
            print(f"BEFUND: {meldung}", file=sys.stderr)
        print(f"\n{len(befunde)} Befund(e) gefunden.", file=sys.stderr)
        return 1

    print(f"{len(dateien)} Workflow-Datei(en) geprueft, kein Anschluss-Defekt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
