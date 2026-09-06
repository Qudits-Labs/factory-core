# Die Zusätze zu den Rollenrahmen

Dieses Verzeichnis gehört in das Produktrepositorium unter
`.factory/prompts/`. Hier liegt nur die Erklärung, was hineingehört — keine
Inhalte, weil Inhalte ohne Kenntnis eines bestimmten Repositoriums nicht
schreibbar sind.

## Was der Zusatz ist

Ein Agentenlauf bekommt seinen Auftrag aus zwei Teilen. Der Rollenrahmen aus
diesem Kern beschreibt die Rolle in einer Form, die überall gilt: welche
Eingaben sie bekommt, welches Lieferobjekt sie schuldet, welche Belege sie
liefern muss, was sie nicht darf. Der Zusatz aus dem Produktrepositorium sagt,
worauf in genau diesem Repositorium zu achten ist.

Die Trennung hat einen Grund, der nichts mit Ordnung zu tun hat. Der Kern ist
öffentlich lesbar. Ein Prüfauftrag, der die Schwellwerte und die geschützten
Pfade eines privaten Produkts nennt, wäre keine Beschreibung eines Verfahrens
mehr, sondern eine Anleitung, wie man daran vorbeikommt.

## Die Probe

Lässt sich der Satz wortwörtlich in ein anderes Repositorium übernehmen, ohne
dort falsch zu sein? Dann gehört er in den Rahmen und nicht hierher.

Beispiele, die in den **Rahmen** gehören und dort bereits stehen:

- «Ein blockierender Befund braucht drei Angaben: verletzte Stelle, Fundstelle,
  Reproduktion.»
- «Du erhältst keinen Gesprächsverlauf aus der Erstellung.»
- «Du schreibst nie in den Code.»

Beispiele, die in den **Zusatz** gehören, also hierher:

- welche Bereiche dieses Repositoriums besonders heikel sind und warum
- ab welcher Abweichung ein Befund blockiert
- welche Namens- und Ablagekonventionen gelten
- welche Datenbestände mit besonderer Sorgfalt zu behandeln sind
- welche Pfade nicht angefasst werden dürfen

## Dateinamen

Ein Zusatz je Rolle und Anlass. Der Pfad wird in `gate-config.yml` benannt,
nicht erraten:

```
.factory/prompts/adversary-spec.md
.factory/prompts/adversary-code.md
.factory/prompts/adversary-coverage.md
.factory/prompts/adversary-doc.md
.factory/prompts/implementer.md
.factory/prompts/solution-architect.md
.factory/prompts/test-designer.md
```

## Wenn ein Zusatz fehlt

Der Lauf startet trotzdem, mit dem Rahmen allein. Das Ergebnis wird schwächer,
aber es bleibt strukturell richtig: die Belegpflicht gilt, das Urteil hat
dieselbe Form, die Ergebnisdatei besteht dasselbe Schema. Ein fehlender Zusatz
ist ein Qualitätsverlust, kein Ausfall.
