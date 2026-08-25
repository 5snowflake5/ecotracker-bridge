# EcoTracker Bridge

Schlanker Ersatz für uni-meter: liest einen **physischen everHome EcoTracker** und gibt ihn als virtuellen EcoTracker aus, damit der **Growatt NOAH** ihn lokal koppeln kann.

Zusätzlich: **HA-Integration „EcoTracker Local“** für Sensoren / History / Energy Dashboard.

## App (Growatt-Emulation)

1. Einstellungen → **Apps** → App installieren → ⋮ → **Repositories**
2. `https://github.com/5snowflake5/ecotracker-bridge`
3. **EcoTracker Bridge** installieren, uni-meter stoppen, starten
4. `source_url` = `http://192.168.55.140`
5. ShinePhone: Zähler → `ecotracker-b43a45a1b2c3`

## Integration (Sensoren zum Auswerten)

Pollt den **physischen** EcoTracker direkt (`/v1/json`), unabhängig vom NOAH.

### HACS

1. HACS → ⋮ → Custom repositories  
2. URL: `https://github.com/5snowflake5/ecotracker-bridge`, Kategorie **Integration**
3. **EcoTracker Local** installieren, Home Assistant neu starten
4. Einstellungen → Geräte & Dienste → Integration hinzufügen → **EcoTracker Local**
5. Host: `192.168.55.140`, Intervall z. B. `5` Sekunden

### Manuell

`custom_components/ecotracker_local/` nach `/config/custom_components/ecotracker_local/` kopieren, HA neu starten, Integration hinzufügen.

### Sensoren

| Sensor | JSON | Hinweis |
|--------|------|---------|
| Leistung | `power` | negativ = Einspeisung |
| Leistung Mittelwert | `powerAvg` | letzte Minute |
| Phase 1–3 | `powerPhase*` | falls vorhanden |
| Energie Bezug / Einspeisung | `energyCounterIn/Out` | Wh, Energy Dashboard |

Für Energy Dashboard: Bezug = `energy_in`, Einspeisung = `energy_out` (Grid).

## Hinweise

- Pi, EcoTracker und NOAH im selben LAN (mDNS).
- MAC der Bridge nach dem Koppeln nicht ändern.
- Hintergrund-Poll der Bridge Default `0` (NOAH pollt selbst ~alle 3 s).
