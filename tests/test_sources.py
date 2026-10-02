import json
from unittest.mock import MagicMock, patch

from model import Reading, reading_from_ecotracker
from sources.ecotracker import EcoTrackerSource, normalize_ecotracker_url
from sources.http_json import HttpJsonSource
from sources.base import PollingSource


class _SlowSource(PollingSource):
    type = "slow"

    def __init__(self) -> None:
        super().__init__({"id": "slow"})
        self.calls = 0
        self._enter = __import__("threading").Event()
        self._release = __import__("threading").Event()

    def fetch(self):
        self.calls += 1
        self._enter.set()
        self._release.wait(timeout=2)
        return Reading(power_w=1.0, source_id=self.id)


def test_error_backoff_skips_retry():
    class Boom(PollingSource):
        type = "boom"

        def fetch(self):
            raise TimeoutError("timed out")

    src = Boom({"id": "boom", "error_retry_s": 30})
    src._last = Reading(power_w=4.0, source_id="boom")
    first = src.read(reason="fail")
    assert first is not None and first.power_w == 4.0
    assert src._polls_fail == 1
    second = src.read(reason="too-soon")
    assert second is not None and second.power_w == 4.0
    assert src._polls_fail == 1


def test_read_single_flight_returns_cache():
    src = _SlowSource()
    src._last = Reading(power_w=9.0, source_id="slow")
    src._last_fetch_mono = 0.0
    t = __import__("threading").Thread(target=lambda: src.read(reason="first"))
    t.start()
    assert src._enter.wait(timeout=1)
    cached = src.read(reason="second")
    assert cached is not None
    assert cached.power_w == 9.0
    src._release.set()
    t.join(timeout=2)
    assert src.calls == 1



def test_reading_from_ecotracker_roundtrip():
    payload = {
        "power": 1500.0,
        "powerPhase1": 500.0,
        "powerPhase2": 600.0,
        "powerPhase3": 400.0,
        "energyCounterIn": 12345.0,
    }
    reading = reading_from_ecotracker(payload, source_id="meter-1")
    out = reading.to_ecotracker()
    assert out["power"] == 1500.0
    assert out["powerPhase1"] == 500.0
    assert out["powerPhase2"] == 600.0
    assert out["powerPhase3"] == 400.0
    assert out["energyCounterIn"] == 12345.0


def test_ecotracker_source_appends_v1_json():
    src = EcoTrackerSource({"id": "et1", "url": "http://192.168.1.10/"})
    assert src.url == "http://192.168.1.10/v1/json"
    assert normalize_ecotracker_url("http://x/v1/json") == "http://x/v1/json"
    assert normalize_ecotracker_url("http://x/v1/json/") == "http://x/v1/json"


def test_http_json_fetch_nested_emeters():
    body = json.dumps({"emeters": [{"power": 42.5}], "meta": {"ok": True}}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    src = HttpJsonSource(
        {
            "id": "hj1",
            "url": "http://meter.local/json",
            "json_power": "emeters.0.power",
        }
    )

    with patch("sources.http_json.urlopen", return_value=mock_resp):
        reading = src.fetch()

    assert reading.power_w == 42.5
    assert reading.extra["meta"]["ok"] is True
    assert reading.fetched_at is not None
    assert reading.raw is not None
    synthesized = reading.to_ecotracker()
    assert synthesized["power"] == 42.5
    assert "emeters" not in synthesized


def test_to_ecotracker_keeps_native_payload():
    reading = reading_from_ecotracker({"power": 9, "foo": "bar"})
    out = reading.to_ecotracker()
    assert out["power"] == 9
    assert out["foo"] == "bar"


def test_generic_reading_does_not_leak_nested_extra():
    reading = Reading(power_w=3.5, extra={"emeters": [{"power": 3.5}]})
    out = reading.to_ecotracker()
    assert out["power"] == 3.5
    assert "emeters" not in out
