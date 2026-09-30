"""Legacy option migration into sources/emulators lists."""

from __future__ import annotations

from config import load_config


def test_legacy_default_two_emulators(monkeypatch, tmp_path):
    opts = {
        "source_url": "http://192.168.1.10",
        "idle_fetch_seconds": 5,
        "shelly_enabled": True,
        "mac": "B43A45A1B2C3",
        "serial": "293d45273261",
        "productid": "1137",
        "shelly_mac": "C8C9A3B43A45",
    }
    path = tmp_path / "options.json"
    path.write_text(__import__("json").dumps(opts), encoding="utf-8")
    monkeypatch.setattr("config.OPTIONS_PATHS", (str(path),))
    monkeypatch.setattr("util.OPTIONS_PATHS", (str(path),))

    cfg = load_config()
    assert len(cfg.sources) == 1
    assert cfg.sources[0]["id"] == "grid"
    assert cfg.sources[0]["type"] == "ecotracker"
    assert cfg.sources[0]["url"] == "http://192.168.1.10"
    assert cfg.sources[0]["idle_fetch_seconds"] == 5

    assert len(cfg.emulators) == 2
    assert cfg.emulators[0]["type"] == "ecotracker"
    assert cfg.emulators[0]["source"] == "grid"
    assert cfg.emulators[1]["type"] == "shelly_pro3em"
    assert cfg.emulators[1]["source"] == "grid"


def test_legacy_shelly_disabled(monkeypatch, tmp_path):
    opts = {
        "source_url": "http://meter.local",
        "shelly_enabled": False,
    }
    path = tmp_path / "options.json"
    path.write_text(__import__("json").dumps(opts), encoding="utf-8")
    monkeypatch.setattr("config.OPTIONS_PATHS", (str(path),))
    monkeypatch.setattr("util.OPTIONS_PATHS", (str(path),))

    cfg = load_config()
    assert len(cfg.emulators) == 1
    assert cfg.emulators[0]["type"] == "ecotracker"


def test_explicit_lists_not_migrated(monkeypatch, tmp_path):
    opts = {
        "source_url": "http://ignored",
        "shelly_enabled": True,
        "sources": [
            {"id": "pv", "type": "http_json", "url": "http://inverter/api"},
        ],
        "emulators": [
            {"id": "emu1", "type": "ecotracker", "source": "pv", "mac": "AABBCCDDEEFF"},
        ],
    }
    path = tmp_path / "options.json"
    path.write_text(__import__("json").dumps(opts), encoding="utf-8")
    monkeypatch.setattr("config.OPTIONS_PATHS", (str(path),))
    monkeypatch.setattr("util.OPTIONS_PATHS", (str(path),))

    cfg = load_config()
    assert len(cfg.sources) == 1
    assert cfg.sources[0]["id"] == "pv"
    assert len(cfg.emulators) == 1
    assert cfg.emulators[0]["id"] == "emu1"
    assert cfg.emulators[0]["source"] == "pv"


def test_form_cards_tibber_and_two_outputs(monkeypatch, tmp_path):
    opts = {
        "source_url": "http://ignored",
        "shelly_enabled": True,
        "tibber": [
            {"host": "192.168.1.50", "password": "printed", "user": "admin"},
        ],
        "outputs": [
            {"id": "noah", "type": "ecotracker", "mac": "B43A45A1B2C3"},
            {"type": "shelly_emg3", "source": "tibber_pulse", "mac": "AABBCCDDEEFF"},
        ],
        "announce_ip": "127.0.0.1",
    }
    path = tmp_path / "options.json"
    path.write_text(__import__("json").dumps(opts), encoding="utf-8")
    monkeypatch.setattr("config.OPTIONS_PATHS", (str(path),))

    cfg = load_config()
    assert cfg.sources == [
        {
            "id": "tibber_pulse",
            "host": "192.168.1.50",
            "password": "printed",
            "user": "admin",
            "type": "tibber_pulse",
        }
    ]
    assert cfg.emulators[0]["type"] == "ecotracker"
    assert cfg.emulators[0]["id"] == "noah"
    assert "source" not in cfg.emulators[0]
    assert cfg.emulators[1]["id"] == "shelly_emg3"
    assert cfg.emulators[1]["source"] == "tibber_pulse"


def test_expert_sources_ignore_form_cards(monkeypatch, tmp_path):
    opts = {
        "tibber": [{"host": "1.2.3.4", "password": "x"}],
        "sources": [{"id": "pv", "type": "http_json", "url": "http://inverter/api"}],
        "emulators": [{"id": "emu1", "type": "ecotracker", "source": "pv"}],
        "announce_ip": "127.0.0.1",
    }
    path = tmp_path / "options.json"
    path.write_text(__import__("json").dumps(opts), encoding="utf-8")
    monkeypatch.setattr("config.OPTIONS_PATHS", (str(path),))

    cfg = load_config()
    assert [s["id"] for s in cfg.sources] == ["pv"]
    assert cfg.emulators[0]["id"] == "emu1"


def test_sources_without_emulators_uses_first_source_id(monkeypatch, tmp_path):
    opts = {
        "source_url": "http://ignored",
        "sources": [
            {"id": "pv", "type": "http_json", "url": "http://inverter/api"},
        ],
        "emulators": [],
        "announce_ip": "127.0.0.1",
    }
    path = tmp_path / "options.json"
    path.write_text(__import__("json").dumps(opts), encoding="utf-8")
    monkeypatch.setattr("config.OPTIONS_PATHS", (str(path),))

    cfg = load_config()
    assert cfg.emulators[0]["source"] == "pv"
    assert cfg.emulators[0]["type"] == "ecotracker"
