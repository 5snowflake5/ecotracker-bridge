# Konfiguration

| Option | Bedeutung |
|--------|-----------|
| `source_url` | Physischer EcoTracker, z. B. `http://192.168.55.140` |
| `idle_fetch_seconds` | Selbst holen, wenn so lange kein `/v1/json`-Trigger (NOAH). **5** Default. `0` = aus. Bei NOAH alle ~3 s praktisch nie nötig. |
| `log_level` | `info` (ruhig) oder `debug` (jeder GET inkl. Δ und Latenz) |
| `port` | HTTP-Port, Growatt erwartet **80** |
| `mac` | Feste Hex-MAC für `ecotracker-<mac>` |
| `serial` / `productid` | mDNS-TXT (`productid=1137`) |
| `announce_ip` | Leer = Auto |

## Endpunkte

- `/v1/json` — live (NOAH)
- `/v1/cache` — Cache für HA-Sensoren, ohne Hardware-Call
- `/` — Statusseite (Cache)
