# Growatt Cloud

## Warum

`noah-mqtt` + HA **Growatt Server** = zwei Logins / viele Requests → Account-Sperre.

Diese App: **ein Open-API-Token**, offizielle **v4**-Endpunkte, MQTT → Home Assistant.

## Noah und Nexa

Beide laufen in der Open API unter `deviceType=noah` (v1 hat weder Noah noch Nexa).

- Auto-Erkennung über Antwortfelder / `storage_family: auto`
- Oder fest: `storage_family: noah` bzw. `nexa` (nur Anzeigename/Modell in HA)

Ein Nexa-2000 erscheint in der Geräteliste wie ein Noah – die Live-Daten kommen über denselben v4-Endpunkt `queryLastData`.

## Token holen

1. [openapi.growatt.com](https://openapi.growatt.com) einloggen  
2. Account → **API Token** erzeugen/kopieren  
3. In der App-Config unter `api_token` eintragen  

Kein Benutzername/Passwort in der App.

## Intervalle (Growatt-Limits)

| Gerät | Minimum |
|-------|---------|
| Noah / Nexa | 60 s |
| MIN-WR / andere | 300 s |
| Geräteliste | stündlich (Default) |

Kürzer bringt Rate-Limits (code 102 / 10012), keine frischeren Daten.

## Sensoren (Beispiele)

Nach Serial, z. B. `0PVP…` / `BZP4…`:

**Speicher:** SoC, Solar Power, Charging/Discharge/Output Power, Generation Today/Total  

**WR:** Energy Today, Energy Today Input 1/2, AC Power, PV Power  

Entity-IDs weichen von noah-mqtt ab (`growatt_cloud_…`). Lovelace ggf. anpassen oder alte Integrationen deaktivieren, damit nichts doppelt zählt.

## Empfohlen nach Sperre

1. Growatt-Account entsperren / Token neu  
2. **noah-mqtt** und **Growatt Server**-Integration in HA **aus**  
3. Diese App starten, Log prüfen (`Gerät: sn=… type=noah`)  
4. MQTT-Gerät unter Einstellungen → Geräte  

Optional: `storage_sn` / `inverter_sn` fest setzen, sonst Auto-Detect aus der Geräteliste.
