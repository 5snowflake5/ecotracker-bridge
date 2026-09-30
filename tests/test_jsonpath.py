from jsonpath import extract, extract_float


def test_extract_nested_and_index():
    data = {"emeters": [{"power": 12.5}, {"power": -3}], "total": {"power": 9.5}}
    assert extract(data, "total.power") == 9.5
    assert extract(data, "emeters.0.power") == 12.5
    assert extract(data, "emeters[1].power") == -3
    assert extract(data, "$.total.power") == 9.5
    assert extract(data, "missing.path") is None
    assert extract_float(data, "emeters.0.power") == 12.5
