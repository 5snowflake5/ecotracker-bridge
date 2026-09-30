# Meter Bridge

Schlanker Ersatz für uni-meter: **Quellen** (EcoTracker, Shelly, Tasmota, HomeWizard, SMA, Fronius, Tibber Pulse, …) lesen echte Zähler; **Emulatoren** geben Identitäten aus, die Speicher koppeln (EcoTracker, Shelly Pro 3EM / EM Gen3 / Pro EM-50, Chargee Sparky). Growatt NOAH und HA-Sensoren aus dem Cache bleiben das Default-Verhalten.

Cloud-Anbindung Noah/Nexa/WR (Open API, ein Token): separates Repo
[growatt-cloud](https://github.com/fromWaterToWind/growatt-cloud).

## Datenfluss (Hub)

```text
                    ┌─ EcoTracker ── /v1/json ──────── Growatt NOAH
Quelle(n) ── Hub ───┼─ Shelly RPC ── /rpc + UDP ────── Growatt / Marstek
  (grid, …)         ├─ Sparky P1 ─── /api/v1/data ──── Chargee
                    └─ MQTT (pro Quelle) ───────────── HA-Sensoren
       ↑
       └── Live nur bei Client-Abruf oder Idle-Watchdog
```

**Legacy-Config** (`source_url`, `mac`, `shelly_*`): eine Quelle `grid`, Emulatoren `ecotracker` + optional `shelly`.

**Hub-Config** (`sources` / `emulators`): mehrere Quellen und mehrere virtuelle Zähler, verbunden über `source`-ID.

Nur `/v1/json`, Shelly-Status-RPC oder der Idle-Watchdog rufen die Quelle live ab.
`/v1/cache`, `/` und `/api/status` lesen nur Cache/Snapshots.

## Installation über GitHub

1. Einstellungen → Apps → App installieren → ⋮ → Repositories  
2. `https://github.com/fromWaterToWind/ecotracker-bridge`  
3. **Meter Bridge** installieren  

Ab **1.2.1** kommen vorgebaute Images von GHCR (kein Docker-Build auf dem Pi).  
Das verhindert Supervisor-Crashes / OOM auf Raspberry Pi 3.

## Releases (wichtig)

Home Assistant liest die Version aus `config.yaml` im Git-Repo. Damit kein Update erscheint, bevor das Image da ist:

1. Code nach `master` pushen → baut nur Preview-Tags `edge` / `sha-…`  
2. **GitHub → Actions → „Release add-on“ → Run workflow** mit Version z. B. `1.3.2`  
3. Workflow: Image pushen → **erst danach** Versionsbump committen  
4. Dann in HA updaten  

Version in `config.yaml` nicht von Hand hochsetzen.

Wenn der Store hängt: App deinstallieren, Store einmal neu laden, neu installieren.  
Währenddessen HA/Supervisor nicht neu starten.

## Sensoren über die App (MQTT)

Kein HACS nötig. Voraussetzung: **Mosquitto**-App + MQTT-Integration in HA.

1. Bridge auf **1.2.0+** updaten
2. In der Bridge-Config: `mqtt_enabled: true`, Host `core-mosquitto`
3. User/Pass nur setzen, wenn dein Mosquitto das verlangt
4. Bridge starten → im Log: `MQTT verbunden` und `MQTT HA-Discovery veröffentlicht`
5. Unter **Einstellungen → Geräte & Dienste** erscheint Gerät **Meter Bridge** mit Sensoren

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

## Mehrere Zähler (Hub)

AstraMeter-Idee, ohne INI: **Quellen** lesen echte Meter, **Emulatoren** geben virtuelle Meter aus. Verknüpfung über die `source`-ID. Mehrere Quellen und mehrere Emulatoren gleichzeitig.

Beispiel: EcoTracker als Quelle, parallel als EcoTracker *und* Shelly ausgeben – das ist der Legacy-Default. Oder: Home-Assistant-Sensor als Quelle, Shelly-Emulator für den Speicher.

In der Add-on-UI: EcoTracker-Adresse oben lassen, oder eine Karte füllen (Tibber, HomeWizard, SMA, …) und unter **Ausgaben** ein oder mehrere virtuelle Zähler anlegen. Die Quellen-ID der Karte (leer = Typname, z. B. `tibber_pulse`) muss bei der Ausgabe als Quelle stehen. Karten leer = bisheriges Verhalten mit `source_url`. **Experten-Quellen** nur, wenn ein Feld fehlt — die ersetzt die Karten.

| Quellentyp | Liest |
|---|---|
| `ecotracker` | everHome `/v1/json` |
| `http_json` | beliebiges HTTP-JSON, Felder per Punkt-Pfad (`emeters.0.power`) |
| `mqtt` | MQTT-Topic (Zahl oder JSON) |
| `homeassistant` | HA-Entität (Add-on nutzt Supervisor-Token) |
| `tasmota` | Tasmota `status 10` / ENERGY-JSON |
| `homewizard` | HomeWizard P1 lokal (`/api/v1/data`, optional v2 Bearer `/api/measurement`) |
| `fronius` | Fronius Solar API `GetMeterRealtimeData` |
| `tibber_pulse` | Tibber Pulse lokal (Binary-SML `/data.json`, Basic-Auth) |
| `shelly` | physisches Shelly EM / 3EM / Pro 3EM |
| `sma` | SMA Energy Meter / SHM2 Speedwire (UDP-Multicast, `host_network`) |
| `amis_reader` | AMIS Reader `/rest` |
| `vzlogger` | VZLogger UUID |
| `esphome` | ESPHome REST-Sensor |
| `refoss` | Refoss/Meross EM |
| `iobroker` | ioBroker `getPlainValue` |
| `envoy` | Enphase Envoy `production.json` |
| `shrdzm` | SHRDZM LastData |

| Emulator | Bietet | Typische Clients |
|---|---|---|
| `ecotracker` | `/v1/json` + mDNS `_everhome._tcp` | Growatt NOAH |
| `shelly_pro3em` | HTTP `/rpc` + mDNS `_shelly._tcp`, Hostname `shellypro3em-…` | Growatt |
| `shelly_emg3` | wie Pro 3EM, Hostname `shellyemg3-…`, UDP 1010/2220 | Marstek |
| `shelly_proem50` | 1-phasig `EM1.GetStatus`, Hostname `shellyproem50-…`, UDP 2223 | Marstek |
| `chargee_sparky` | `/api` + `/api/v1/data` + mDNS `_chargee_p1._tcp` | Chargee |

Nicht emuliert (nur als Quelle lesbar, wo es Sinn ergibt): SMA Speedwire, Fronius, Tibber, Tasmota, HomeWizard, USB-SML, Modbus, ESPHome-native. Batterien koppeln an die Whitelist-Identitäten oben, nicht an jedes physische SKU.

Zwei gleiche Emulatoren: Routing über HTTP-`Host` / mDNS-Hostname. Ein einzelner EcoTracker/Shelly akzeptiert weiter Aufrufe per IP (Growatt).

## Integration (optional, ohne MQTT)

HACS **EcoTracker Local** gegen Bridge-`/v1/cache` – nur nötig, wenn du kein MQTT willst.

## Endpunkte

| URL | Wirkung |
|-----|---------|
| `/v1/json` | live vom physischen Tracker (EcoTracker / NOAH) |
| `/v1/cache` | letzter Stand, **kein** Hardware-Call (für HA) |
| `/rpc/EM.GetStatus` | Shelly live (gleiche Quelle) |
| `/rpc/EM1.GetStatus` | Shelly Pro EM-50 (1-phasig) |
| `/rpc/Shelly.GetDeviceInfo` | Shelly-Identität |
| `/shelly` | Alias DeviceInfo |
| `/api` / `/api/v1/data` | Chargee Sparky (wenn konfiguriert) |
| `/` | Statusseite aus Cache |
| `/api/status` | JSON-Übersicht Quellen/Emulatoren |
