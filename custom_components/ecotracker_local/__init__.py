"""EcoTracker Local — liest den Bridge-Cache (`/v1/cache`), kein Extra-Poll auf Hardware."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


def cache_url(host: str) -> str:
    """Bridge-Cache. Niemals /v1/json — das würde den physischen EcoTracker triggern."""
    host = host.strip()
    if host.startswith("http://") or host.startswith("https://"):
        base = host.rstrip("/")
    else:
        base = f"http://{host}"
    for suffix in ("/v1/cache", "/v1/json"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base}/v1/cache"


# Backwards-compatible name used by config_flow
source_url = cache_url


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    scan = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    url = cache_url(host)
    session = async_get_clientsession(hass)

    async def async_update() -> dict[str, Any]:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 503:
                    raise UpdateFailed(
                        "Bridge-Cache leer – warte bis Growatt einmal /v1/json geholt hat"
                    )
                if resp.status != 200:
                    raise UpdateFailed(f"HTTP {resp.status} von {url}")
                data = await resp.json(content_type=None)
        except UpdateFailed:
            raise
        except Exception as exc:
            raise UpdateFailed(f"Bridge-Cache nicht erreichbar ({url}): {exc}") from exc
        if not isinstance(data, dict):
            raise UpdateFailed("Antwort ist kein JSON-Objekt")
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"ecotracker_local:{host}",
        update_method=async_update,
        update_interval=timedelta(seconds=int(scan)),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
