# EcoTracker Bridge

Schlanker Ersatz für uni-meter: Emulation für **Growatt NOAH** (EcoTracker + optional Shelly Pro 3EM) + **HA-Sensoren aus dem Cache** (ohne Extra-Last auf dem physischen EcoTracker).

Cloud-Anbindung Noah/Nexa/WR (Open API, ein Token): separates Repo
[growatt-cloud](https://github.com/5snowflake5/growatt-cloud).

## Datenfluss

```text
physischer EcoTracker  ←live─  Bridge /v1/json  ←alle ~3s─  Growatt NOAH (EcoTracker)
         ↑                 │     Bridge /rpc/…  ←optional─  Growatt/andere (Shelly)
         │                 │
         └── idle nach 5 s ┤
                           └─Cache─  /v1/cache  ←poll─  HA-Sensoren
```

Nur `/v1/json`, Shelly-Status-RPC oder der Idle-Watchdog (>5 s ohne Trigger) rufen die Hardware.
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

1. Bridge auf **1.2.0+** updaten
2. In der Bridge-Config: `mqtt_enabled: true`, Host `core-mosquitto`
3. User/Pass nur setzen, wenn dein Mosquitto das verlangt
4. Bridge starten → im Log: `MQTT verbunden` und `MQTT HA-Discovery veröffentlicht`
5. Unter **Einstellungen → Geräte & Dienste** erscheint Gerät **Ecotracker** mit Sensoren

Die Werte kommen aus denselben Abrufen wie NOAH (kein Extra-Poll auf die Hardware).

## Shelly Pro 3EM (ab 1.3.0)

Parallel zum EcoTracker, gleiche Live-Werte, anderes Wire-Format:

| | EcoTracker | Shelly Pro 3EM |
|---|---|---|
| mDNS | `_everhome._tcp` | `_shelly._tcp` |
| HTTP | `/v1/json` | `/rpc/EM.GetStatus?id=0` |
| Hostname | `ecotracker-<mac>` | `shellypro3em-<mac>` |

Optionen: `shelly_enabled` (Default an), `shelly_mac` (nicht ändern nach dem Koppeln).  
NOAH koppelt in der Regel **einen** Zähler – Dual-Emulation ist für Wechsel oder unterschiedliche Clients gedacht, nicht für doppelte Kopplung desselben Speichers.

## Integration (optional, ohne MQTT)

HACS **EcoTracker Local** gegen Bridge-`/v1/cache` – nur nötig, wenn du kein MQTT willst.

## Endpunkte

| URL | Wirkung |
|-----|---------|
| `/v1/json` | live vom physischen Tracker (EcoTracker / NOAH) |
| `/v1/cache` | letzter Stand, **kein** Hardware-Call (für HA) |
| `/rpc/EM.GetStatus` | Shelly live (gleiche Quelle) |
| `/rpc/Shelly.GetDeviceInfo` | Shelly-Identität |
| `/shelly` | Alias DeviceInfo |
| `/` | Statusseite aus Cache |
