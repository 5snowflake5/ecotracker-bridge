# Konfiguration

## Legacy (Add-on-UI)

Die flachen Felder bleiben unverändert nutzbar. Intern entsteht daraus automatisch:

| Legacy | Hub-Objekt |
|--------|------------|
| `source_url` | Quelle `grid` (Typ `ecotracker`, URL wie angegeben) |
| `mac`, `serial`, `productid` | Emulator `ecotracker` → Quelle `grid` |
| `shelly_enabled` / `shelly_mac` | optional Emulator `shelly` (Typ `shelly_pro3em`) |

| Option | Bedeutung |
|--------|-----------|
| `source_url` | Physischer EcoTracker, z. B. `http://192.168.55.140` |
| `idle_fetch_seconds` | Selbst holen, wenn so lange kein Live-Trigger. **5** Default. `0` = aus. |
| `log_level` | `info` oder `debug` |
| `port` | HTTP-Port, Growatt erwartet **80** |
| `mac` | Feste Hex-MAC für `ecotracker-<mac>` |
| `serial` / `productid` | mDNS-TXT (`productid=1137`) |
| `announce_ip` | Leer = Auto |
| `shelly_enabled` | Parallel Shelly Pro 3EM (Default an) |
| `shelly_mac` | Feste Hex-MAC für `shellypro3em-<mac>` |
| MQTT-* | HA Discovery pro Quelle (Legacy-Quelle `grid` behält alte Topics) |

## Hub (Add-on-Formular)

Jede Zählerart hat eine eigene Karte. Nur die passende Karte füllen. **Ausgaben** kann mehrere Zeilen haben (EcoTracker und Shelly gleichzeitig).

Leere Karten und leere Ausgaben = Legacy (`source_url`, `mac`, `shelly_*`).

Quellen-ID leer lassen → sie wird der Typ (`tibber_pulse`, `homewizard`, `sma`, …). Dieselbe ID bei der Ausgabe unter Quelle eintragen. Eine Ausgabe ohne Quelle nimmt die einzige (oder erste) Quelle.

**Experten-Quellen** / **Experten-Ausgaben** ersetzen die Karten, sobald dort eine Zeile steht. Für YAML, wenn ein seltenes Feld fehlt.

Sprachen der UI: `en`, `de`, `fr`, `es`.

Beispiel Tibber → Growatt und Marstek (Formular oder YAML):

```yaml
tibber:
  - host: 192.168.1.50
    password: "bridge-print"
outputs:
  - id: noah
    type: ecotracker
    mac: B43A45A1B2C3
  - id: marstek
    type: shelly_emg3
    source: tibber_pulse
    mac: AABBCCDDEEFF
```

Zwei Ausgaben desselben Typs: HTTP-`Host` / mDNS-Hostname entscheidet. Eine einzelne akzeptiert weiter IP-Aufrufe.

Marstek koppelt per Hostname-Prefix (`shellypro3em-` / `shellyemg3-` / `shellyproem50-`) plus UDP-RPC. Growatt nutzt HTTP EcoTracker und/oder Shelly Pro 3EM. UDP-Ports nur unter Experten-Ausgaben (`udp_ports`, oder `off`).

## Endpunkte

- `/v1/json`, `/v1/cache` — EcoTracker-Emulator (wenn konfiguriert)
- `/rpc/...`, `/shelly` — Shelly-Emulator (wenn konfiguriert)
- `/api`, `/api/v1/data` — Chargee Sparky (wenn konfiguriert; `/api/status` bleibt Hub-Status)
- `/` — Statusseite (nur Cache, kein Hardware-Call)
- `/api/status` — JSON-Übersicht aller Quellen/Emulatoren
