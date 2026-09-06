# ADR-020: Konfigurationsformat für Gate-Schwellwerte

## Kontext

Produktrepositorien müssen Schwellwerte und Befehle an den Kern übergeben.
Bisher gibt es dafür keine einheitliche Lösung.

## Entscheidung

Konfigurationswerte stehen in einer YAML-Datei unter `.factory/gate-config.yml`.

## Alternativen

- JSON-Datei: Kein nativer Kommentar-Support; Konfiguration ohne Erläuterungen
  ist schwer wartbar.
- Umgebungsvariablen: Für einfache Werte geeignet. Bei zusammengesetzten
  Strukturen mit Verschachtelung wird das Mapping unlesbar.
- TOML: Deutlich seltener in GitHub-Ökosystemen anzutreffen. Kein Standardparser
  in der Python-Bibliothek enthalten.

## Betriebsfolgen

Jedes Produktrepositorium legt `.factory/gate-config.yml` an. Ein fehlender
Abschnitt bedeutet, dass der betreffende Gate-Schritt nicht aufgerufen wird.

## Status

Akzeptiert
