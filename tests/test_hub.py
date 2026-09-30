from __future__ import annotations

from hub import Hub
from config import HubConfig
from status import api_status, html_status


class DummyMqtt:
    def set_hub(self, hub, source_ids):
        self.hub = hub
        self.source_ids = source_ids

    def publish_state(self, source_id, payload):
        return None

    def configure(self, opts):
        return None


def test_hub_legacy_shape():
    cfg = HubConfig(
        log_level="info",
        port=80,
        announce_ip="192.168.1.2",
        idle_fetch_seconds=5,
        mqtt_enabled=False,
        mqtt_host="core-mosquitto",
        mqtt_port=1883,
        mqtt_user="",
        mqtt_password="",
        mqtt_discovery_prefix="homeassistant",
        sources=[{"id": "grid", "type": "ecotracker", "url": "http://192.168.1.10"}],
        emulators=[
            {"id": "ecotracker", "type": "ecotracker", "source": "grid", "mac": "B43A45A1B2C3"},
            {"id": "shelly", "type": "shelly_pro3em", "source": "grid", "mac": "C8C9A3B43A45"},
        ],
        raw={},
    )
    hub = Hub(cfg, DummyMqtt())
    try:
        assert list(hub.sources) == ["grid"]
        assert [e.type for e in hub.emulators] == ["ecotracker", "shelly_pro3em"]
        assert hub.emulators_of_type("ecotracker")[0].hostnames[0].startswith("ecotracker-")
        status = api_status(hub)
        assert status["sources"][0]["id"] == "grid"
        html = html_status(hub)
        assert b"Meter Bridge" in html
        assert b"/v1/json" in html
        assert b"/rpc/EM.GetStatus" in html
    finally:
        hub.stop()
