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

## Menschliche Gates

Die Freigabe zum Bauen, der Merge in den Hauptzweig und die Freigabe zur
Auslieferung sind keine Workflows. Es sind Zustandsprüfungen innerhalb der
Übergabe: sie erkennt an der Kennung dessen, der ein Label gesetzt hat, ob ein
Mensch mit Freigaberecht gehandelt hat.

Ein eigener Workflow dafür wäre eine Einladung. Was ein Workflow tun kann, kann
ein Workflow auch ohne Menschen tun.

## Auflösung der Schema-Verweise

`result.schema.json` verweist auf `finding.schema.json` über einen relativen
Verweis. Ein Prüfprogramm muss beide Dateien laden und dem Validierer bekannt
machen; ein Verweis, der über das Netz aufgelöst wird, macht die Prüfung von der
Erreichbarkeit einer Adresse abhängig. Der Canary misst genau diesen Fall.
