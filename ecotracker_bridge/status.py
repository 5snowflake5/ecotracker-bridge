"""HTML status dashboard and /api/status JSON."""

from __future__ import annotations

from datetime import datetime
from typing import Any

def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M:%S")


def api_status(hub: Any) -> dict[str, Any]:
    sources_out = []
    for sid, src in hub.sources.items():
        stats = src.stats()
        snap = src.snapshot()
        power = snap.power_w if snap else None
        sources_out.append(
            {
                "id": sid,
                "type": getattr(src, "type", stats.get("type", "")),
                "label": stats.get("label", sid),
                "power_w": power,
                "last_ok": stats.get("last_ok").isoformat() if stats.get("last_ok") else None,
                "last_error": stats.get("last_error"),
                "polls_ok": stats.get("polls_ok", 0),
                "polls_fail": stats.get("polls_fail", 0),
            }
        )
    emulators_out = []
    for emu in hub.emulators:
        emulators_out.append(
            {
                "id": getattr(emu, "id", ""),
                "type": getattr(emu, "type", ""),
                "source": getattr(emu, "source_id", ""),
                "hostnames": list(getattr(emu, "hostnames", []) or []),
            }
        )
    return {
        "version": hub.meta.get("version"),
        "announce_ip": hub.meta.get("announce_ip"),
        "port": hub.meta.get("port"),
        "idle_fetch_seconds": hub.meta.get("idle_fetch_seconds"),
        "log_level": hub.meta.get("log_level"),
        "sources": sources_out,
        "emulators": emulators_out,
    }


def html_status(hub: Any) -> bytes:
    version = hub.meta.get("version", "")
    idle = float(hub.meta.get("idle_fetch_seconds") or 0)
    idle_txt = "aus" if not idle else f"nach {idle:.0f} s ohne Live-Trigger"
    announce = hub.meta.get("announce_ip", "")
    port = hub.meta.get("port", 80)

    src_rows = ""
    for sid, src in hub.sources.items():
        stats = src.stats()
        snap = src.snapshot()
        power = snap.power_w if snap else "—"
        err = stats.get("last_error") or "—"
        src_rows += (
            f"<tr><td>{sid}</td><td>{getattr(src, 'type', '')}</td>"
            f"<td>{power}</td><td>{_fmt_dt(stats.get('last_ok'))}</td>"
            f"<td>{err}</td><td>{stats.get('polls_ok', 0)} / {stats.get('polls_fail', 0)}</td></tr>"
        )
    if not src_rows:
        src_rows = "<tr><td colspan=6>Keine Quellen konfiguriert</td></tr>"

    emu_rows = ""
    has_ecotracker = False
    has_shelly = False
    has_sparky = False
    has_em1 = False
    for emu in hub.emulators:
        et = getattr(emu, "type", "")
        if et == "ecotracker":
            has_ecotracker = True
        if et in ("shelly_pro3em", "shellypro3em", "shelly_emg3", "shelly_proem50"):
            has_shelly = True
        if et == "shelly_proem50":
            has_em1 = True
        if et == "chargee_sparky":
            has_sparky = True
        hosts = ", ".join(f"<code>{h}</code>" for h in (getattr(emu, "hostnames", []) or []))
        emu_rows += (
            f"<tr><td>{getattr(emu, 'id', '')}</td><td>{et}</td>"
            f"<td>{getattr(emu, 'source_id', '')}</td><td>{hosts or '—'}</td></tr>"
        )
    if not emu_rows:
        emu_rows = "<tr><td colspan=4>Keine Emulatoren aktiv</td></tr>"

    links = ""
    if has_ecotracker:
        links += (
            '<tr><th>JSON live (NOAH)</th><td><a href="/v1/json"><code>/v1/json</code></a></td></tr>'
            '<tr><th>JSON Cache (HA)</th><td><a href="/v1/cache"><code>/v1/cache</code></a></td></tr>'
        )
    if has_shelly:
        rpc_method = "EM1.GetStatus" if has_em1 and not any(
            getattr(e, "type", "") in ("shelly_pro3em", "shelly_emg3") for e in hub.emulators
        ) else "EM.GetStatus"
        links += (
            f'<tr><th>Shelly RPC</th><td><a href="/rpc/{rpc_method}?id=0">'
            f"<code>/rpc/{rpc_method}</code></a></td></tr>"
        )
    if has_sparky:
        links += (
            '<tr><th>Sparky P1</th><td><a href="/api/v1/data">'
            "<code>/api/v1/data</code></a></td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="5">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Meter Bridge</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; color: #1a1a1a; }}
    h1 {{ font-size: 1.25rem; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 48rem; margin-bottom: 1.5rem; }}
    td, th {{ border-bottom: 1px solid #ddd; padding: 0.35rem 0.5rem; text-align: left; }}
    .muted {{ color: #555; }}
    code {{ background: #f4f4f4; padding: 0.1rem 0.3rem; }}
  </style>
</head>
<body>
  <h1>Meter Bridge {version}</h1>
  <p class="muted">Hub: mehrere Quellen und Emulatoren. Live-Fetch nur bei Client-Abrufen oder Idle-Watchdog.</p>
  <h2>Quellen</h2>
  <table>
    <tr><th>ID</th><th>Typ</th><th>Leistung (W)</th><th>Letzter OK</th><th>Fehler</th><th>Abrufe ok/fehl</th></tr>
    {src_rows}
  </table>
  <h2>Emulatoren</h2>
  <table>
    <tr><th>ID</th><th>Typ</th><th>Quelle</th><th>Hostnames</th></tr>
    {emu_rows}
  </table>
  <h2>Betrieb</h2>
  <table>
    <tr><th>Idle-Fetch</th><td>{idle_txt}</td></tr>
    <tr><th>Log-Level</th><td>{hub.meta.get("log_level", "info")}</td></tr>
    <tr><th>Angekündigte IP</th><td>{announce}:{port}</td></tr>
    {links}
    <tr><th>API</th><td><a href="/api/status"><code>/api/status</code></a></td></tr>
  </table>
</body>
</html>
"""
    return html.encode("utf-8")
