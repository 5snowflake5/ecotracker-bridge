# EcoTracker Bridge

Schlanker Ersatz für uni-meter: Emulation für **Growatt NOAH** + **HA-Sensoren aus dem Cache** (ohne Extra-Last auf dem physischen EcoTracker).

## Datenfluss

```text
physischer EcoTracker  ←live─  Bridge /v1/json  ←alle ~3s─  Growatt NOAH
                                      │
                                      └─Cache─  /v1/cache  ←poll─  HA-Sensoren
```

Nur `/v1/json` (NOAH) ruft die Hardware. `/v1/cache` und die Statusseite lesen nur den Speicher.

## App (Growatt)

1. Apps → Repository `https://github.com/5snowflake5/ecotracker-bridge`
2. **EcoTracker Bridge** installieren, uni-meter stoppen
3. `source_url` = `http://192.168.55.140`
4. ShinePhone → `ecotracker-b43a45a1b2c3`

## Integration (Sensoren)

1. HACS → Custom repo (Integration): dieselbe GitHub-URL  
2. **EcoTracker Local** installieren, HA neu starten  
3. Integration hinzufügen, Host = **Bridge/Pi** `192.168.55.151` (nicht `.140`)  
4. Intervall z. B. 5 s (trifft nur `/v1/cache`)

Sensoren: Leistung, Mittelwert, Phasen, Energie Bezug/Einspeisung.

## Endpunkte

| URL | Wirkung |
|-----|---------|
| `/v1/json` | live vom physischen Tracker (für NOAH) |
| `/v1/cache` | letzter Stand, **kein** Hardware-Call (für HA) |
| `/` | Statusseite aus Cache |
