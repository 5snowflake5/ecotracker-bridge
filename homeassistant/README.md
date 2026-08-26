# Energy-Dashboard für NOAH-Topologie

## Dein echter Fluss

```text
PV ──┬──► Speicher (nur aus PV, nie aus dem Netz)
     │         │
     │         ▼ entladen
     └──────► WR-Abgabe ──► Hausnetz (EcoTracker)
```

HA zeichnet **kein** WR-Zwischenglied. Modell ist nur: Solar / Batterie / Netz / Haus.
Das sieht anders aus als die Physik, die Zahlen können trotzdem stimmen – wenn die Sensoren passen.

## Richtige Zuordnung

**Einstellungen → Dashboards → Energie**

| Slot | Sensor | Nicht nehmen |
|------|--------|----------------|
| Netz Bezug | `sensor.ecotracker_total_grid_import` | Growatt Import (oft 0/falsch) |
| Netz Einspeisung | `sensor.ecotracker_total_grid_export` | Growatt Export |
| Solar | NOAH **Generation Total** (`…_generation_total`) | Generation Today, WR Energy today, wechselrichter Total Energy today |
| Batterie laden | Integral aus **Charging Power** (`…_charging_power`) | Growatt „batteries charged today“, PV−AC-Differenz |
| Batterie entladen | Integral aus **Discharge Power** (`…_discharge_power`) | dasselbe Charging-Power nochmal (häufiger Copy-Paste-Fehler!) |

Solar und WR-Energy-today **nicht beide** als Solar → Doppelzählung, kaputter Flow.

## Integral-Helfer (Batterie)

Zwei getrennte Helfer:

1. Input = Charging Power → „NOAH geladen“ (Präfix k, Stunden, left)
2. Input = Discharge Power → „NOAH entladen“ (Präfix k, Stunden, left)

Dann diese beiden im Energy-Dashboard unter Heimspeicher eintragen.

**Wichtig:** Growatt pollt oft nur alle 5 min. Integral unterschätzt dann die kWh (z. B. „nur 1,3 kWh“). Besser noah-mqtt (~30 s) als Quelle für Charging/Discharge Power.

## Warum der Flow „falsch“ aussieht

- HA zeigt keine Kette „PV → Speicher → WR → Haus“, sondern Bilanzknoten.
- „Aus dem Netz geladen“ erscheint, wenn Laden + Solar + Netz rechnerisch nicht aufgehen (falsche/zu niedrige Sensoren) – nicht weil der NOAH wirklich aus dem Netz lädt.
- 1,3 kWh Laden heute: meist zu grobes Integral oder falscher Sensor, nicht die Physik.

## Pragmatischer Check

1. Batterie im Energy-Dashboard **kurz entfernen** → nur Netz + Solar (Generation Total). Flow sollte ruhiger werden.
2. Integrale prüfen: Input wirklich `…_charging_power` bzw. `…_discharge_power`?
3. Batterie erst wieder rein, wenn die Integrale über den Tag plausibel steigen.
