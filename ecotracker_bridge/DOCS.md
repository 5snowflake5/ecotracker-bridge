# Konfiguration

| Option | Bedeutung |
|--------|-----------|
| `source_url` | Physischer EcoTracker, z. B. `http://192.168.55.140` |
| `idle_fetch_seconds` | Selbst holen, wenn so lange kein Live-Trigger (`/v1/json` oder Shelly-Status-RPC). **5** Default. `0` = aus. |
| `log_level` | `info` (ruhig) oder `debug` (jeder GET inkl. Δ und Latenz) |
| `port` | HTTP-Port, Growatt erwartet **80** |
| `mac` | Feste Hex-MAC für `ecotracker-<mac>` |
| `serial` / `productid` | mDNS-TXT (`productid=1137`) |
| `announce_ip` | Leer = Auto |
| `shelly_enabled` | Parallel Shelly Pro 3EM emulieren (Default an) |
| `shelly_mac` | Feste Hex-MAC für `shellypro3em-<mac>` |

## Endpunkte

- `/v1/json` — live EcoTracker (NOAH)
- `/v1/cache` — Cache für HA-Sensoren, ohne Hardware-Call
- `/rpc/EM.GetStatus` — live Shelly (gleiche Quelle)
- `/rpc/Shelly.GetDeviceInfo` / `/shelly` — Shelly-Identität
- `/` — Statusseite (Cache)
