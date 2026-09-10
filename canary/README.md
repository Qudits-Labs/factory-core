# Canary

Aufruf: `python3 canary/run_canary.py`

Der Canary misst den Kern gegen sich selbst, ohne Kenntnis eines konkreten
Produkts. Er legt keine Dateien an und schreibt in kein Produktrepositorium.

---

## Was der Canary prüft

**Schemas**
- Alle Schemas unter `schemas/` sind gültiges JSON und gültiges JSON Schema
  (Draft 2020-12).
- Die Beispieldateien unter `example/` bestehen das für sie geltende Schema.
- `result.schema.json` lehnt ein zustimmendes Urteil mit offenem
  blockierendem Befund ab.
- `result.schema.json` lehnt einen blockierenden Befund ohne die drei
  Belegangaben ab (spec_ref, location, reproduction).
- Der relative Verweis von `result.schema.json` auf `finding.schema.json`
  löst vom Dateisystem auf, ohne einen Netzzugriff auszulösen. Das ist die
  einzige Bedingung, für die es keinen anderen Test gibt.

**Gate-Skripte**
- Jedes Skript unter `scripts/gate_*.py` und `scripts/transition_check.py`
  gibt Exit 0 bei einem sauberen Fixture und Exit 1 bei einem verletzenden
  zurück. Dafür sind zwei Sätze von Fixtures vorhanden: die bestehenden unter
  `tests/fixtures/` (geprüft durch `scripts/selftest.py`) und die Canary-
  eigenen unter `canary/fixtures/` mit anderen Szenarien.

**AC-Map**
- Ein vollständiges AC-Map-Dokument besteht `ac-map.schema.json`.
- Ein lückenhaftes AC-Map-Dokument (fehlende Pflichtfelder) fällt durch.

**Ergebnis-Dokumente**
- Ein gültiges Ergebnisdokument besteht `result.schema.json`.
- Ein Dokument mit PASS-Urteil und offenem BLOCK-Befund fällt durch.
- Ein Dokument mit BLOCK-Befund ohne spec_ref, location und reproduction
  fällt durch.

**Workflows**
- Jeder Workflow unter `.github/workflows/` deklariert `permissions:`
  ausdrücklich. Fehlt die Zeile, erbt der Workflow Rechte.
- Jeder `workflow_call`-Workflow unter `.github/workflows/gate-*.yml`
  deklariert `pass` und `findings_json` als Ausgaben. Das ist die
  Vertragstreue-Prüfung nach `docs/gate-vertrag.md`.
- Jeder Ablauf, der einen anderen aufruft, reicht die Eingaben weiter, die
  beide führen, und dazu alles, was der aufgerufene als
  `[durchgriff-pflicht]` markiert. Sonst bietet er einen Regler an, der
  nichts bewirkt.
- Jeder Verweis auf einen Workflow dieses Repositoriums steht in der Vollform
  mit Commit-SHA, und der SHA trägt dieselbe Fassung der Zieldatei wie der
  Arbeitsstand. Damit fällt auf, wenn nach einer Änderung an einem
  aufgerufenen Ablauf der zweite Commit vergessen wurde, der den Zeiger
  nachzieht. Lässt sich der SHA lokal nicht auflösen — flache Kopie —, wird
  dieser zweite Teil sichtbar übersprungen; deshalb holt `canary.yml` die
  volle Historie.

---

## Was der Canary nicht prüfen kann

**Inhaltliche Korrektheit**
- Ob ein Prüfbefund inhaltlich richtig ist. Der Canary kann prüfen, ob ein
  Befund die drei Belegfelder hat — nicht, ob die Fundstelle stimmt oder die
  Reproduktionsschritte zum beschriebenen Fehler führen.
- Ob die Schwellwerte eines Produkts sinnvoll sind. `min_alternatives: 2`
  wird erzwungen, aber ob zwei Alternativen für eine bestimmte Entscheidung
  genug oder zu wenig sind, weiß der Kern nicht.

**Ausführung und Laufzeit**
- Ob ein Auslieferungsbefehl funktioniert. Der Canary überprüft, dass ein
  Befehl einen erlaubten Präfix hat und der Health-Check die erwartete
  Antwort zurückgibt — beides an synthetischen Fixtures, nicht an einer
  laufenden Umgebung.
- Was ein Lauf kostet. Laufzeit, Tokens und Cloud-Rechnung entstehen erst
  im Produktrepositorium.

**Gleichzeitigkeit und Skalierung**
- Wie sich die Kette bei mehreren gleichzeitigen Vorgängen verhält. Gate-
  Skripte laufen isoliert; Race Conditions zwischen zwei Issues, die
  gleichzeitig durch dieselbe Rolle laufen, sind im Canary nicht sichtbar.

**Semantische Prüfungen**
- Ob ein Testfall das genannte Akzeptanzkriterium wirklich abdeckt. Die
  AC-Map-Prüfung bestätigt nur die Struktur der Datei, nicht ob TC-001
  tatsächlich AK-01 trifft.
- Ob ein ADR die richtige Entscheidung beschreibt. Der Canary zählt
  Abschnitte und begründete Alternativen — er bewertet keinen Inhalt.

**Infrastruktur und Berechtigungen**
- Ob Branch-Schutzregeln greifen. Der Canary liest Workflow-Dateien, aber
  er sieht nicht, ob der Merge in den Hauptzweig tatsächlich durch eine
  menschliche Freigabe gesperrt ist.
- Ob die Kennungen in `human_gate_logins` noch aktiven Konten gehören.
  Abgelaufene oder deaktivierte Konten werden nicht erkannt.

**Externe Abhängigkeiten**
- Ob externe Actions (gepinnt auf SHA) inhaltlich sicher sind. Der Canary
  bestätigt nur, dass ein SHA vorhanden ist — nicht, was der Code an diesem
  SHA tut.
