# EcoTracker Bridge

Schlanker Ersatz für uni-meter: Emulation für **Growatt NOAH** + **HA-Sensoren aus dem Cache** (ohne Extra-Last auf dem physischen EcoTracker).

## Datenfluss

```text
physischer EcoTracker  ←live─  Bridge /v1/json  ←alle ~3s─  Growatt NOAH
         ↑                      │
         └── idle nach 5 s ─────┤
                                └─Cache─  /v1/cache  ←poll─  HA-Sensoren
```

Nur `/v1/json` (NOAH) oder der Idle-Watchdog (>5 s ohne Trigger) rufen die Hardware.
`/v1/cache` und die Statusseite lesen nur den Speicher.

## Installation über GitHub

1. Einstellungen → Apps → App installieren → ⋮ → Repositories  
2. `https://github.com/5snowflake5/ecotracker-bridge`  
3. **EcoTracker Bridge** installieren  

Ab **1.2.1** kommen vorgebaute Images von GHCR (kein Docker-Build auf dem Pi).  
Das verhindert Supervisor-Crashes / OOM auf Raspberry Pi 3.

Wenn der Store hängt: App deinstallieren, Store einmal neu laden, neu installieren.  
Währenddessen HA/Supervisor nicht neu starten.

## Sensoren über die App (MQTT)

Kein HACS nötig. Voraussetzung: **Mosquitto**-App + MQTT-Integration in HA.

1. Bridge auf **1.2.0** updaten
2. In der Bridge-Config: `mqtt_enabled: true`, Host `core-mosquitto`
3. User/Pass nur setzen, wenn dein Mosquitto das verlangt
4. Bridge starten → im Log: `MQTT verbunden` und `MQTT HA-Discovery veröffentlicht`
5. Unter **Einstellungen → Geräte & Dienste** erscheint Gerät **EcoTracker Bridge** mit Sensoren

Die Werte kommen aus denselben Abrufen wie NOAH (kein Extra-Poll auf die Hardware).

## Integration (optional, ohne MQTT)

HACS **EcoTracker Local** gegen Bridge-`/v1/cache` – nur nötig, wenn du kein MQTT willst.

## Endpunkte

| URL | Wirkung |
|-----|---------|
| `/v1/json` | live vom physischen Tracker (für NOAH) |
| `/v1/cache` | letzter Stand, **kein** Hardware-Call (für HA) |
| `/` | Statusseite aus Cache |
