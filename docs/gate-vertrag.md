# Der Gate-Vertrag

Jeder Prüfschritt dieses Kerns hält denselben Vertrag ein. Das ist der Grund,
warum die Übergabe zwischen zwei Schritten ohne Fallunterscheidung auskommt: sie
liest immer dasselbe Feld.

## Eingaben

Ein Prüfschritt liest **nie selbst** eine Datei aus dem aufrufenden
Repositorium. Alles, was er braucht, kommt als `inputs`. Der Grund ist nicht
Reinheit, sondern Prüfbarkeit: ein Schritt, dessen Verhalten von einer Datei
abhängt, die er selbst sucht, lässt sich nicht gegen ein Fixture messen.

Daraus folgt die Aufgabenteilung. Der aufrufende Workflow im Produktrepositorium
liest `.factory/gate-config.yml`, wählt die Werte für diesen Schritt aus und
übergibt sie. Der Prüfschritt wendet sie an.

Jeder Schritt bekommt mindestens die Kennung des Vorgangs, auf den er sich
bezieht: eine Issue-Nummer oder eine Pull-Request-Nummer.

## Rückgaben

Jeder Prüfschritt gibt zwei Werte zurück:

| Ausgabe | Typ | Bedeutung |
|---|---|---|
| `pass` | boolean | Die einzige Grösse, an der die Übergabe entscheidet |
| `findings_json` | string | JSON-Array von Befunden nach `schemas/finding.schema.json` |

Alles Weitere ist schrittspezifisch und für die Fehlersuche da, nicht für die
Entscheidung. Ein Schritt, dessen Ergebnis sich nur aus einem Zusatzfeld
ablesen lässt, hat den Vertrag verletzt.

## Schweregrade

| Grad | Wirkung | Wer setzt ihn |
|---|---|---|
| `BLOCK` | `pass` wird falsch, der Vorgang bleibt stehen | eine prüfende Rolle, aber nur mit vollständigem Beleg |
| `WARN` | `pass` bleibt wahr, der Befund erscheint im Vorgang | prüfende Rolle oder maschinelle Prüfung |
| `INFO` | `pass` bleibt wahr, der Befund erscheint nur in der Ergebnisdatei | maschinelle Prüfung |

Ein `BLOCK` ohne die drei Belegangaben aus `finding.schema.json` wird auf `WARN`
herabgestuft, und zwar von der Übergabe, nicht vom Prüfschritt. Der
herabgestufte Befund trägt danach das Feld `downgraded_from`, damit der Vorgang
nachvollziehbar bleibt.

## Wie ein Produktrepositorium einen Schwellwert beisteuert

Der Kern kennt keine Schwellwerte. Er kennt die Stelle, an der einer steht.

Ein Beispiel für die Abdeckungsprüfung: der Kern legt fest, dass die Prüfung
einen maschinellen und einen bewertenden Teil hat und dass der bewertende Teil
abschaltbar ist. Ob er in einem bestimmten Repositorium läuft, steht dort in
`.factory/gate-config.yml`. Der aufrufende Workflow liest den Wert und übergibt
ihn als `run_adversarial`.

Dasselbe Muster gilt für die Mindestzahl der Alternativen in einer
Architekturentscheidung, für die Zahl der Versuche, für die geschützten Pfade
und für jeden auszuführenden Befehl.

Die Regel dahinter: **der Kern definiert die Bedeutung eines Werts, das
Produktrepositorium setzt ihn.**

## Versuchszählung

`max_attempts` ist einer dieser Schwellwerte: das Produktrepositorium setzt
ihn, der Kern definiert, was gezählt wird.

**Quelle:** Vor jedem Agentenlauf schreibt `transition.yml` einen Kommentar
mit der Markierung `<!-- factory:attempt run=<id> -->` und einer Tabelle mit
Rolle, Akteur, Zeitstempel und Run-ID ins Issue. Diese Kommentare sind die
einzige Quelle der Zählung; es gibt keinen zweiten Zähler in einem Label,
einer Datei oder einem Cache. `scripts/count_attempts.py` liest sie über die
Issue-API, bevor `transition_check.py` prüft.

**Zählweise:** pro Rolle. Gezählt wird jeder Kommentar mit Markierung, dessen
Zeile `| Rolle |` dieselbe Rolle nennt wie der anstehende Übergang. Läufe
anderer Rollen am selben Issue zählen nicht: drei gescheiterte Läufe des
Solution Architect verbrauchen nicht das Kontingent des Implementers.
Kommentare ohne Markierung zählen nie, auch wenn sie eine Rollenzeile
enthalten. Ein Kommentar mit Markierung, aber ohne Rollenzeile ist ein Befund
und hält den Übergang an; ein stilles 0 an dieser Stelle würde die Grenze
genauso lautlos ausser Kraft setzen wie eine fest verdrahtete 0.

**Bei Erreichen von `max_attempts`:** `transition_check.py` verweigert den
Übergang und gibt `attempts_ok=false` zurück, der Job `pruefung` endet mit
Befund, es wird kein weiterer Attempt-Eintrag geschrieben und kein Agent
gestartet. Die Grenze gilt für jeden Akteur, auch für Logins aus
`human_gate_logins`: ein Mensch, der das Label erneut setzt, löst keinen
weiteren Lauf aus. Die Zählung sinkt nie, weil die Kommentare bleiben. Wer
die Rolle an diesem Issue noch einmal arbeiten lassen will, hebt
`max_attempts` im Produktrepositorium an; sonst übernimmt ein Mensch die
Arbeit.

Der Fall wird im Issue als das gemeldet, was er ist, nicht als
Agentenfehler. Der Job `nachbereitung` schreibt einen Kommentar mit der
Markierung `<!-- factory:attempts-exhausted run=<id> -->`, der Rolle, Stand
der Zählung und `max_attempts` nennt, und setzt das Label
`flag:attempts-exhausted`. Die Ausgabe `agent_status` trägt dann den Wert
`attempts_exhausted`. Die Markierung `factory:attempts-exhausted` zählt
nicht als Versuch; gezählt werden ausschliesslich Kommentare mit
`factory:attempt`. Das Zustandslabel selbst bleibt stehen; entfernt wird
es nur bei unberechtigtem Akteur.

## Menschliche Gates

Die Freigabe zum Bauen, der Merge in den Hauptzweig und die Freigabe zur
Auslieferung sind keine Workflows. Es sind Zustandsprüfungen innerhalb der
Übergabe: sie erkennt an der Kennung dessen, der ein Label gesetzt hat, ob ein
Mensch mit Freigaberecht gehandelt hat.

Ein eigener Workflow dafür wäre eine Einladung. Was ein Workflow tun kann, kann
ein Workflow auch ohne Menschen tun.

## Rechte und Checkout

**Rechte:** Rechte können in einer Kette aus Abläufen nur sinken. Ein Ablauf,
der `run-agent.yml` aufruft -- direkt oder über `transition.yml` --, muss dem
aufrufenden Job mindestens `contents: write`, `pull-requests: write` und
`issues: write` erteilen. Weniger bricht den Lauf vor dem ersten Schritt ab.
Der Workflow-Kopf reicht nicht; die Rechte müssen am **Job** stehen, der den
wiederverwendbaren Ablauf aufruft.

**Checkout:** Der `github`-Kontext in einem wiederverwendbaren Ablauf zeigt auf
das Produktrepositorium. Jeder Job, der Dateien aus diesem Kern braucht, muss
`actions/checkout` deshalb mit `repository: Qudits-Labs/factory-core` und
`ref: ${{ inputs.core_ref }}` aufrufen. Ohne diese Angabe checkt der Runner
das Produkt aus, und `scripts/`, `role-frameworks/` sowie `schemas/` fehlen.

## gh-Aufrufe

Jeder `gh`-Aufruf im Kern läuft ausdrücklich gegen das aufrufende
Repositorium. Das folgt aus dem Checkout-Muster oben: ein Job, der den Kern
ausgecheckt hat, steht in einem Arbeitsverzeichnis, dessen Git-Remote auf
`Qudits-Labs/factory-core` zeigt. Ohne weitere Angabe leitet `gh` das
Repositorium genau daraus ab und sucht Issues, Labels und Pull Requests im
Kern statt im Produkt. Beim ersten echten Durchlauf scheiterte
`gh issue comment 18` so mit «Could not resolve to an issue»; das Issue lag
im Produktrepositorium.

Die Regel: der Job, der `gh` aufruft, setzt `GH_REPO: ${{ github.repository }}`
in seiner `env:`. `github.repository` zeigt in einem wiederverwendbaren Ablauf
auf das Produkt, und `gh` wertet `GH_REPO` bei jedem Aufruf aus. Wer die
Umgebung an `subprocess` selbst zusammenstellt, übernimmt `os.environ`; sonst
kommt die Variable nicht an. `--repo` je Aufruf ist die gleichwertige zweite
Form. Der Canary misst beides (`scripts/check_gh_repo_kontext.py`).

## Auflösung der Schema-Verweise

`result.schema.json` verweist auf `finding.schema.json` über einen relativen
Verweis. Ein Prüfprogramm muss beide Dateien laden und dem Validierer bekannt
machen; ein Verweis, der über das Netz aufgelöst wird, macht die Prüfung von der
Erreichbarkeit einer Adresse abhängig. Der Canary misst genau diesen Fall.
