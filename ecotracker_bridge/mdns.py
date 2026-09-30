"""Register mDNS services for all emulators on one Zeroconf instance."""

from __future__ import annotations

import logging
from typing import Any

from zeroconf import IPVersion, Zeroconf

LOG = logging.getLogger("ecotracker-bridge")


def register_emulators(hub: Any) -> tuple[Zeroconf | None, list[Any]]:
    ip = str(hub.meta.get("announce_ip") or "")
    port = int(hub.meta.get("port") or 80)
    if not ip:
        LOG.error("mDNS: keine announce_ip")
        return None, []

    zc = Zeroconf(ip_version=IPVersion.V4Only)
    infos: list[Any] = []
    for emu in hub.emulators:
        try:
            services = emu.mdns_services(ip, port)
        except Exception as exc:
            LOG.error("mDNS für Emulator %s fehlgeschlagen: %s", getattr(emu, "id", "?"), exc)
            continue
        for info in services:
            try:
                zc.register_service(info, cooperating_responders=True)
                infos.append(info)
                LOG.info(
                    "mDNS %s: %s:%s",
                    getattr(emu, "id", "?"),
                    ip,
                    port,
                )
            except Exception as exc:
                LOG.error("mDNS register fehlgeschlagen (%s): %s", getattr(emu, "id", "?"), exc)
    return zc, infos


def unregister_all(zc: Zeroconf | None) -> None:
    if zc is None:
        return
    try:
        zc.unregister_all_services()
        zc.close()
    except Exception as exc:
        LOG.debug("mDNS cleanup: %s", exc)
