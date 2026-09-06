# ADR-001: Datenhaltung fuer Konfigurationswerte

## Kontext

Die Anwendung benoetigt persistente Konfigurationswerte, die zur Laufzeit
lesbar sein muessen. Bisher wurden diese als Umgebungsvariablen verwaltet,
was bei vielen Werten unuebersichtlich wird.

## Entscheidung

Konfigurationswerte werden in einer YAML-Datei abgelegt, die beim Start
eingelesen wird.

## Alternativen

- Umgebungsvariablen beibehalten: Gut fuer einfache Deployments, aber bei
  mehr als zehn Werten schwer zu warten. Kein Typsystem vorhanden.
- Datenbanktabelle: Ermoeglicht Aenderungen zur Laufzeit. Erfordert
  jedoch eine Datenbankverbindung fuer reine Konfigurationszwecke, was
  eine unnoetige Abhaengigkeit eintraegt.
- Externe Config-Map (z.B. Kubernetes): Passt zur geplanten
  Container-Infrastruktur, bringt aber erhebliche Komplexitaet fuer eine
  Anwendung, die heute noch lokal laeuft.

## Betriebsfolgen

Die YAML-Datei muss beim Deployment mitgeliefert werden. Ein fehlender
Schluessel fuehrt zu einem Startfehler mit klar lesbarer Meldung.

## Status

Akzeptiert
