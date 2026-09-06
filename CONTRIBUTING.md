# Beitragen

Dieses Repository ist oeffentlich lesbar. Schreibrecht haben nur Mitglieder der
Organisation `Qudits-Labs`. Ein Beitrag von aussen kommt als Pull Request herein
und wird wirksam, wenn ihn jemand mit Schreibrecht merged.

## Was hier hineingehoert

Der generische Kern der Fabrik. Ein Beitrag gehoert hierher, wenn er ohne
Kenntnis eines bestimmten Produkts vollstaendig ist:

- wiederverwendbare Workflows und ihre Schritte
- Schemas der Ergebnisdateien
- Gate-Schnittstellen: welche Eingaben ein Gate bekommt, welche Rueckgabewerte
  es kennt, wie ein Befund aufgebaut ist
- neutrale Rollenrahmen: welche Art von Auftrag eine Rolle erhaelt, welche
  Belege sie liefern muss, was sie nicht darf
- Canary-Tests
- Issue- und PR-Vorlagen ohne Produktbezug

## Was hier nie hineingehoert

- ausformulierte Rollenprompts mit den Konventionen eines Repositoriums
- Schwellwerte von Gates und die Kriterien, an denen ein Review misst
- Pfadlisten, geschuetzte Pfadklassen, Zuordnungsdateien fuer Dokumentation
- Sicherheitsregeln, die aus einem konkreten Datenbestand folgen
- Anwendungscode jeder Art, auch Ausschnitte
- Secrets, Token, Verbindungszeichenfolgen, auch abgelaufene
- Personendaten, Kundennamen, Vertragsinhalte
- interne Hostnamen, Produktions-URLs, Netzplaene, Datenbankschemata

Diese Dinge liegen im Verzeichnis `.factory/` des jeweiligen Produktrepositoriums
und werden von dort als Eingabe an einen Workflow uebergeben.

Die Probe fuer einen Zweifelsfall: Funktioniert der Beitrag nur, wenn man ein
bestimmtes Produkt kennt? Dann gehoert nicht der Beitrag hierher, sondern die
Schnittstelle, ueber die das Produktrepositorium ihn beisteuert.

## Regeln fuer Workflow-Dateien

- Kein `pull_request_target`. Dieser Ausloeser fuehrt fremden Code mit den
  Rechten dieses Repositoriums aus. Ein CI-Schritt weist ihn zurueck.
- Jeder Workflow deklariert `permissions:` ausdruecklich. Geerbte Rechte gelten
  als Fehler.
- Werte aus dem `github`-Kontext gehen ueber `env:` in einen Schritt, nie direkt
  in eine Kommandozeile. Titel, Rumpf, Labels und Branch-Namen sind Eingaben,
  keine Anweisungen.
- Ein `workflow_call`-Workflow darf Secrets deklarieren; ihre Werte kommen vom
  aufrufenden Repositorium. Ein Workflow, den dieses Repositorium selbst
  ausloest, verwendet ausser `GITHUB_TOKEN` kein Secret. Ein CI-Schritt prueft
  das.
- Fremde Actions werden auf einen Commit-SHA gepinnt, nicht auf einen Tag.

## Ablauf

1. Fork anlegen und einen Branch erstellen.
2. Aenderung committen. Die Selbstpruefung laeuft im Pull Request; ein Lauf aus
   einem Fork wird erst nach Freigabe gestartet.
3. Pull Request eroeffnen und beschreiben, welchen Teil des Kerns die Aenderung
   betrifft und warum sie ohne Produktkenntnis vollstaendig ist.

Eine Aenderung an diesem Repositorium wirkt erst dann in einem Produktrepositorium,
wenn dort der referenzierte Commit-SHA hochgezogen wird. Das ist ein eigener Pull
Request im Produktrepositorium und braucht einen Menschen.
