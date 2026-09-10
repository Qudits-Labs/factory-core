#!/usr/bin/env python3
"""Die Phasen der Pipeline: welche Rolle arbeitet, und was danach kommt.

Dieses Modul hat keine Befehlszeile. Es wird von `transition_check.py` und
`folgezustand.py` eingebunden und haelt die beiden Abbildungen, die eine Kette
von Agentenlaeufen ueberhaupt erst weiterlaufen lassen:

    Statuslabel -> Rolle          welcher Agent bei diesem Zustand arbeitet
    Statuslabel -> Folgezustand   welches Label den naechsten Schritt ausloest

Beide sind hier vorbelegt und beide sind vom Aufrufer ersetzbar.

## Warum die Abbildung hier liegt und nicht im Produktrepositorium

Die Phasenfolge ist die Form des Verfahrens, nicht die Konfiguration eines
Produkts. Sie besteht aus denselben Rollennamen, die dieses Repositorium
ohnehin fest fuehrt, und aus den Zustaenden, die zwischen ihnen vermitteln. Wer
sie in jedes Produktrepositorium kopiert, hat dieselbe Tabelle mehrfach; Kopien
derselben Definition laufen auseinander, ohne dass jemand es merkt. Genau das
zu vermeiden ist der Zweck dieses Repositoriums.

Produktspezifisch ist nicht die Folge, sondern die Abweichung: eine Abkuerzung,
eine zusaetzliche Phase, eine andere Labelkonvention. Dafuer gibt es die
Ersetzung. Ein Produktrepositorium, das der Standardfolge folgt, uebergibt
nichts und bekommt sie; eines, das abweicht, uebergibt seine eigene Tabelle und
traegt sie selbst.

## Was hier bewusst nicht steht

Kein Pfad, kein Schwellwert, kein Wortlaut eines Pruefauftrags. Auch nicht, wer
ein menschliches Gate bedient -- das sind Logins, die als Eingabe kommen. Hier
stehen nur Labelnamen und Rollennamen.
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Die sechs Rollen. Ein Label darf auf keinen anderen Wert zeigen.
#
# Sicherheitsauflage: die Abbildung nennt Rollennamen, keine Workflow-Pfade.
# Ein freier Pfad als Wert wuerde die Zustandsmaschine umleitbar machen.
# ---------------------------------------------------------------------------
ERLAUBTE_ROLLENNAMEN: frozenset[str] = frozenset(
    {
        "intake-coordinator",
        "solution-architect",
        "test-designer",
        "implementer",
        "adversary",
        "deployer",
    }
)

# ---------------------------------------------------------------------------
# Welches Statuslabel welche Rolle arbeiten laesst.
#
# Diese Tabelle ist keine Neuerfindung: sie ist die Abbildung, die dieses
# Repositorium in `example/.factory/gate-config.example.yml` bereits als
# Muster fuehrt -- Zeichen fuer Zeichen. Vorher musste jedes
# Produktrepositorium sie abschreiben. Jetzt steht sie an einer Stelle, und
# das Beispiel zeigt, wie man sie ersetzt, nicht mehr, wie man sie kopiert.
#
# Nur diese Label loesen einen Agentenlauf aus. Alles andere an einem Vorgang
# -- Profil, Modul, Prioritaet, die Label eines menschlichen Gates -- laesst
# die Zustandsmaschine still liegen.
# ---------------------------------------------------------------------------
STANDARD_ROLLE_JE_LABEL: dict[str, str] = {
    "status:spec": "solution-architect",
    "status:spec-review": "adversary",
    "status:test-design": "test-designer",
    "status:ready-for-dev": "implementer",
    "status:code-review": "adversary",
}

# ---------------------------------------------------------------------------
# Was nach einem erfolgreichen Lauf als naechstes gilt.
#
# Fuer diese Richtung gab es im Kern bisher gar nichts, und deshalb setzte die
# Zustandsmaschine nach einem Lauf dasselbe Label erneut: die Kette lief einen
# Schritt und blieb stehen.
#
# Zwei Zustaende fehlen hier absichtlich:
#
# `status:spec-review` endet auf `status:approved-spec`. Dieses Label steht in
# keiner Rollentabelle, also loest es keinen Lauf aus -- dort sitzt ein
# menschliches Gate, und die Kette haelt an. Ein Gate, ueber das die Maschine
# hinweggeht, ist keines. `status:approved-spec` ist der einzige Labelname, den
# der Kern von sich aus einfuehrt; wer anders benennt, ersetzt die Tabelle.
#
# `status:code-review` hat keinen Eintrag. Was danach kommt, ist der Merge, und
# der haengt an einem Pull-Request-Ereignis und an einem Menschen mit
# Schreibrecht -- nicht an einem Label, das diese Maschine setzen koennte. Ein
# fehlender Eintrag ist kein Fehler: er heisst, die Kette haelt hier an.
# ---------------------------------------------------------------------------
STANDARD_FOLGE_JE_LABEL: dict[str, str] = {
    "status:spec": "status:spec-review",
    "status:spec-review": "status:approved-spec",
    "status:test-design": "status:ready-for-dev",
    "status:ready-for-dev": "status:code-review",
}


def validiere_rollen_map(rollen_map: dict[str, str]) -> list[str]:
    """Gibt Fehlermeldungen fuer ungueltige Rollenwerte zurueck."""
    fehler: list[str] = []
    for label, rollenname in rollen_map.items():
        if rollenname not in ERLAUBTE_ROLLENNAMEN:
            fehler.append(
                f"Label {label!r} -> ungueltige Rolle {rollenname!r}."
                f" Erlaubt: {', '.join(sorted(ERLAUBTE_ROLLENNAMEN))}"
            )
    return fehler


def validiere_folge_map(folge_map: dict[str, str]) -> list[str]:
    """Gibt Fehlermeldungen fuer eine unbrauchbare Folgetabelle zurueck.

    Ein Zustand, der auf sich selbst zeigt, ist genau der Defekt, den diese
    Tabelle beheben soll: die Kette liefe einen Schritt und bliebe stehen.
    """
    fehler: list[str] = []
    for label, folge in folge_map.items():
        if not isinstance(folge, str) or not folge.strip():
            fehler.append(f"Label {label!r} -> leerer Folgezustand.")
            continue
        if folge == label:
            fehler.append(
                f"Label {label!r} zeigt auf sich selbst. Ein Zustand, der sich"
                " selbst folgt, laesst die Kette nach einem Schritt stehen."
            )
    return fehler


def lade_map(roh: str, standard: dict[str, str]) -> tuple[dict[str, str], str]:
    """Liest eine uebergebene Tabelle oder gibt die Standardtabelle zurueck.

    Gibt (Tabelle, Herkunft) zurueck. Herkunft ist 'Standard' oder 'Aufrufer'
    und gehoert ins Protokoll -- wer eine Kette debuggt, muss sehen, welche
    Tabelle gegolten hat.

    Wirft json.JSONDecodeError bei unlesbarer Eingabe und ValueError, wenn die
    Eingabe kein JSON-Objekt aus Zeichenketten ist.
    """
    roh = (roh or "").strip()
    if not roh or roh == "{}":
        return dict(standard), "Standard"

    geladen = json.loads(roh)
    if not isinstance(geladen, dict):
        raise ValueError("Die Tabelle muss ein JSON-Objekt sein.")
    for schluessel, wert in geladen.items():
        if not isinstance(schluessel, str) or not isinstance(wert, str):
            raise ValueError(
                "Die Tabelle darf nur Zeichenketten auf Zeichenketten abbilden."
            )
    return geladen, "Aufrufer"
