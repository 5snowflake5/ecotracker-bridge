# EcoTracker Bridge

Schlanker Ersatz für uni-meter: liest einen **physischen everHome EcoTracker** und gibt ihn als virtuellen EcoTracker aus, damit der **Growatt NOAH** ihn lokal koppeln kann.

- HTTP `GET /v1/json` auf **Port 80**
- mDNS `_everhome._tcp` mit TXT `ip`, `serial`, `productid=1137`
- Statusseite unter `http://<pi-ip>/`
- Deutlich weniger RAM als die JVM von uni-meter

## Installation über GitHub (empfohlen)

1. In Home Assistant: **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
2. Repository hinzufügen:

   ```text
   https://github.com/5snowflake5/ecotracker-bridge
   ```

3. Store neu laden, **EcoTracker Bridge** installieren.
4. **uni-meter stoppen**, bevor du startest (Port 80).
5. Konfiguration: `source_url` = `http://192.168.55.140` (bereits Default).
6. Starten. Prüfen: `http://<pi-ip>/v1/json`
7. ShinePhone: Zähler neu suchen → `ecotracker-b43a45a1b2c3`

## Manuell (lokales Add-on)

Ordner `ecotracker_bridge/` nach `/addons/ecotracker_bridge/` kopieren, Store neu laden, installieren.

## Hinweise

- Pi, EcoTracker und NOAH im **selben WLAN/LAN** (mDNS geht nicht über Router/VLAN).
- MAC nach dem Koppeln nicht ändern, sonst muss der NOAH neu koppeln.
- Falls mDNS auf HaOS fehlschlägt: HTTP läuft trotzdem; dann ggf. Pyscript-Fallback wie bei uni-meter.
