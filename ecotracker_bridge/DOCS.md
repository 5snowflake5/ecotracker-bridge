# EcoTracker Bridge

Liest einen physischen everHome EcoTracker und gibt ihn als virtuellen EcoTracker aus, damit der Growatt NOAH ihn lokal koppeln kann.

## Konfiguration

| Option | Bedeutung |
|--------|-----------|
| `source_url` | IP/URL des physischen EcoTrackers, z. B. `http://192.168.55.140` |
| `poll_seconds` | Hintergrund-Poll. **0 = aus** (empfohlen). Growatt holt live über `GET /v1/json`. |
| `log_level` | `info` (ruhig) oder `debug` (jeder GET inkl. Δ-Intervall) |
| `port` | HTTP-Port, Growatt erwartet **80** |
| `mac` | Feste 12-stellige Hex-MAC für den Hostnamen `ecotracker-<mac>` |
| `serial` / `productid` | mDNS-TXT (Default wie uni-meter, `productid=1137`) |
| `announce_ip` | Leer lassen für Auto-Erkennung |

## Nach dem Start

1. uni-meter **stoppen** (Port 80 und mDNS kollidieren sonst).
2. Status: `http://<pi-ip>/`
3. JSON: `http://<pi-ip>/v1/json`
4. ShinePhone: NOAH → Zähler suchen → `ecotracker-b43a45a1b2c3`

Pi, EcoTracker und NOAH müssen im selben Layer-2-Netz sein.
