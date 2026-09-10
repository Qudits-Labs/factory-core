# factory-core

Der generische Kern einer Fabrik, die Änderungen an Software als Pull Requests
durch eine Kette von Prüfschritten führt. Hier liegen die wiederverwendbaren
Abläufe, die Schemas der Ergebnisdateien, der Vertrag der Prüfschritte, die
Rollenrahmen und die Selbsttests.

Was hier **nicht** liegt: Anwendungscode, Prüfaufträge im Wortlaut,
Schwellwerte, Pfadlisten und Sicherheitsregeln, die aus einem bestimmten
Datenbestand folgen. Das gehört in `.factory/` des jeweiligen
Produktrepositoriums. Der Grund steht weiter unten unter
[Warum die Grenze eng ist](#warum-die-grenze-eng-ist).

Dieses Repositorium ist öffentlich lesbar, damit auch Projekte ausserhalb der
besitzenden Organisation seine Abläufe einbinden können. Schreibrecht haben
weiterhin nur deren Mitglieder.

## Einbinden

Über einen unveränderlichen Commit-SHA, nicht über einen Tag oder einen Zweig.
Ein Tag lässt sich verschieben, und mit ihm ändert sich unbemerkt, was in jedem
Produktrepositorium läuft. Ein SHA lässt sich nicht verschieben.

```yaml
# .github/workflows/pr.yml im Produktrepositorium
name: Pull Request

on:
  pull_request:

permissions:
  contents: read

jobs:
  tests:
    uses: Qudits-Labs/factory-core/.github/workflows/gate-command.yml@7e151870000000000000000000000000000000ab
    with:
      command: ${{ vars.FACTORY_TEST_COMMAND }}
      allowed_command_prefixes: 'npm run '
      setup: node
      runtime_version: '20'
      tc_id_pattern: 'TC-[0-9]+'
```

Der SHA im Beispiel ist ein Platzhalter. Den aktuellen holt man sich so:

```
gh api repos/Qudits-Labs/factory-core/commits/main --jq .sha
```

**Den SHA aktuell halten** übernimmt Dependabot. Damit wird jede neue Fassung des
Kerns zu einem sichtbaren Pull Request im Produktrepositorium statt zu einem
stillen Ereignis:

```yaml
# .github/dependabot.yml im Produktrepositorium
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

Zwei Türen liegen damit hintereinander. Ein Commit hier ändert nichts an einem
Produktrepositorium; erst wenn dort jemand mit Schreibrecht den Pull Request
merged, der den SHA hochzieht, wandert die neue Fassung weiter.

## Was hier liegt

```
schemas/           Verträge als JSON Schema
role-frameworks/   Was eine Rolle bekommt, liefert, belegen muss und nicht darf
templates/         Vorlagen für Vorgänge und Pull Requests, ohne Produktbezug
example/.factory/  Muster der Konfiguration, ausschliesslich mit Platzhaltern
docs/              Der Vertrag der Prüfschritte
scripts/           Prüfprogramme, gegen Fixtures gemessen
tests/fixtures/    Ein sauberer und ein verletzender Fall je Prüfung
.github/workflows/ Die wiederverwendbaren Abläufe und die Selbstprüfung
```

Die Schemas im Einzelnen:

| Datei | Beschreibt |
|---|---|
| `result.schema.json` | Das Ergebnis eines Agentenlaufs unter `.factory/result.json` |
| `finding.schema.json` | Einen einzelnen Befund samt Belegpflicht |
| `test-report.schema.json` | Den Bericht eines Testlaufs |
| `ac-map.schema.json` | Die Zuordnung Akzeptanzkriterium zu Testfall |
| `doc-map.schema.json` | Die Zuordnung Codepfad zu Dokumentationsdatei |
| `gate-config.schema.json` | Die Konfiguration der Prüfschritte im Produktrepositorium |

Die letzten drei beschreiben Dateien, die **nicht hier** liegen. Der Kern legt
ihren Aufbau fest, weil die Prüfschritte sie lesen; ihre Inhalte kommen aus dem
Produktrepositorium.

## Der Vertrag

Jeder Prüfschritt gibt `pass` und `findings_json` zurück, und nichts anderes
entscheidet über den Fortgang. Jeder Prüfschritt bekommt seine Konfiguration als
Eingabe und liest keine Datei des aufrufenden Repositoriums selbst. Die
Einzelheiten stehen in [`docs/gate-vertrag.md`](docs/gate-vertrag.md).

Der Kern kennt keine Schwellwerte. Er kennt die Stelle, an der einer steht, und
was er bedeutet. Gesetzt wird er im Produktrepositorium.

## Was ein Produktrepositorium mitbringen muss

Der Kern läuft nicht allein. Was er nicht wissen kann und deshalb von aussen
bekommt:

**Eine Identität, die Folgeereignisse auslöst.** In aller Regel eine GitHub App.
Das Standardtoken taugt dafür nicht: was damit gesetzt wird, löst keinen
weiteren Workflow aus, und die Kette bliebe nach einem Schritt stehen.

**Den Job, der das nächste Label setzt.** Der Kern gibt den Folgezustand als
`next_label` zurück und setzt ihn nicht selbst. Der Grund ist eine Eigenschaft
des Runners: ein App-Token entsteht zur Laufzeit, und ein maskierter Wert
überlebt keinen Job-Output — er kommt als leere Zeichenkette an. Das Token muss
deshalb in dem Job entstehen, in dem es gebraucht wird, und dieser Job liegt
hier:

```yaml
# .github/workflows/uebergang.yml im Produktrepositorium
jobs:
  uebergang:
    uses: Qudits-Labs/factory-core/.github/workflows/transition.yml@<SHA>
    with:
      issue_number: ${{ github.event.issue.number }}
      new_label: ${{ github.event.label.name }}
      actor_login: ${{ github.actor }}
      human_gate_logins: ${{ vars.FACTORY_HUMAN_GATE_LOGINS }}
      transition_identity_login: ${{ vars.FACTORY_BOT_LOGIN }}
      allowed_bots: ${{ vars.FACTORY_ALLOWED_BOTS }}
      core_ref: <SHA>
    secrets:
      transition_token: ${{ secrets.GITHUB_TOKEN }}
      claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}

  weiterschalten:
    needs: uebergang
    if: needs.uebergang.outputs.next_label != ''
    runs-on: ubuntu-latest
    steps:
      # Token erzeugen und verwenden im selben Job -- ein Job-Output dazwischen
      # würde den maskierten Wert leeren.
      - id: app_token
        uses: actions/create-github-app-token@<SHA>
        with:
          app-id: ${{ vars.FACTORY_APP_ID }}
          private-key: ${{ secrets.FACTORY_APP_PRIVATE_KEY }}
      - env:
          GH_TOKEN: ${{ steps.app_token.outputs.token }}
        run: |
          gh issue edit "${{ github.event.issue.number }}" \
            --remove-label "${{ github.event.label.name }}" \
            --add-label "${{ needs.uebergang.outputs.next_label }}"
```

**`.factory/gate-config.yml`.** Profil, Schwellwerte, geschützte Pfade,
Prüfaufträge im Wortlaut und die Pfade der Ergebnisdateien. Aufbau in
`schemas/gate-config.schema.json`, Muster in `example/.factory/`.

**Einen Zugang zum Modell.** Genau eines von `anthropic_api_key` und
`claude_code_oauth_token`. Beide gesetzt wird abgewiesen, keines auch.

**Den Login der App in `allowed_bots`.** In einer Kette, in der ein Lauf den
nächsten anstösst, ist der Auslöser ein Bot. Ohne Eintrag weist die Action ihn
ab, und zwar jeden.

**Die Kennungen der Menschen mit Freigaberecht** als Repository-Variable, nicht
in einer versionierten Datei.

Was ein Produktrepositorium **nicht** mehr mitbringen muss: die Zuordnung von
Statuslabel zu Rolle und die Folge der Zustände. Beide stehen als Standard im
Kern. Wer davon abweicht, übergibt seine eigene Tabelle und ersetzt die
Standardtabelle damit vollständig.

## Warum die Grenze eng ist

Der Kern ist öffentlich, damit ein Repositorium ausserhalb der besitzenden
Organisation seine Abläufe einbinden kann. Die Alternative wäre eine zweite
Kopie gewesen, und zwei Kopien derselben Prüfdefinitionen laufen auseinander,
ohne dass jemand es merkt.

Öffentlich heisst aber auch: alles hier ist lesbar, auch was einmal in einem
Commit stand und später entfernt wurde. Ein Prüfauftrag im Wortlaut, der die
Schwellwerte und die geschützten Pfade eines privaten Produkts nennt, wäre keine
Beschreibung eines Verfahrens mehr, sondern eine Anleitung, wie man daran
vorbeikommt.

Der Preis dieser Trennung gehört genannt: die Wiederverwendung wird flacher. Ein
zweites Repositorium bekommt die Abläufe und muss seine Prüfaufträge und
Schwellwerte selbst schreiben. Das ist mehr Arbeit als einbinden und laufen
lassen, und es ist die richtige Menge Arbeit, weil ein Prüfauftrag aus einem
Produkt für ein anderes ohnehin falsch wäre.

Was öffentlich bleibt, ist die Form des Verfahrens. Sie trägt nicht durch
Geheimhaltung. Ein Prüfschritt, dessen Wirkung davon abhängt, dass niemand ihn
kennt, wäre keiner.

## Regeln, die hier durchgesetzt werden

- **Kein `pull_request_target`.** Dieser Auslöser führt den Ablauf im Kontext
  des Basis-Repositoriums aus, also mit dessen Schreibtoken und Geheimnissen,
  wertet dabei aber den Code aus einem fremden Pull Request aus. Ein CI-Schritt
  weist ihn zurück.
- **Keine Geheimnisse.** Der Kern hat keine Laufzeit und keinen Dienst, an dem
  er sich anmelden müsste. Ein wiederverwendbarer Ablauf darf ein Geheimnis
  deklarieren, dessen Wert vom Aufrufer kommt; ein Ablauf, den dieses
  Repositorium selbst auslöst, verwendet ausser dem Standardtoken keines. Ein
  CI-Schritt prüft das.
- **Läufe fremder Beiträger brauchen eine Freigabe.** Ohne diese Einstellung
  wird jeder Vorbeikommende zum Auslöser von Läufen.
- **Der Merge bleibt bei Menschen mit Schreibrecht.** Ein Regelwerk auf dem
  Hauptzweig verlangt einen Pull Request.
- **Fremde Actions sind auf einen Commit-SHA gepinnt.**
- **Ein Regler, den ein Ablauf anbietet, muss auch ankommen.** Führt ein
  aufrufender Ablauf eine Eingabe, die der aufgerufene ebenfalls führt, und
  reicht sie nicht weiter, bekommt der Aufrufer still den Standardwert. Was ein
  aufgerufener Ablauf als `[durchgriff-pflicht]` markiert, muss jeder Aufrufer
  zusätzlich selbst anbieten. Ein CI-Schritt prüft beides.

## Selbst prüfen

```
python3 scripts/selftest.py
python3 scripts/check_workflow_triggers.py .github/workflows
python3 scripts/check_no_secrets.py .github/workflows
python3 scripts/check_durchgriff.py .github/workflows
```

Jede Prüfung wird an einem sauberen und an einem verletzenden Fall gemessen. Die
verletzenden Fixtures liegen ausserhalb von `.github/workflows`, damit sie nicht
ausgeführt werden.

## Beitragen

Siehe [`CONTRIBUTING.md`](CONTRIBUTING.md). Die Probe für einen Zweifelsfall
steht dort: funktioniert der Beitrag nur, wenn man ein bestimmtes Produkt kennt,
gehört nicht der Beitrag hierher, sondern die Schnittstelle, über die das
Produktrepositorium ihn beisteuert.
