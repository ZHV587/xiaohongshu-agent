from data_foundation.engine_config import meili_config, falkor_config


def test_meili_config_enabled_when_url_and_key_present():
    cfg = meili_config({"XHS_MEILI_URL": "http://127.0.0.1:7700", "XHS_MEILI_KEY": "k"})
    assert cfg.state == "enabled"
    assert cfg.url == "http://127.0.0.1:7700"
    assert cfg.api_key == "k"


def test_meili_config_disabled_when_missing():
    assert meili_config({"XHS_MEILI_URL": "", "XHS_MEILI_KEY": ""}).state == "disabled"
    assert meili_config({"XHS_MEILI_URL": "http://x", "XHS_MEILI_KEY": ""}).state == "disabled"


def test_falkor_config_enabled_when_url_present():
    cfg = falkor_config({"XHS_FALKOR_URL": "redis://127.0.0.1:6379", "XHS_FALKOR_GRAPH": "xhs"})
    assert cfg.state == "enabled"
    assert cfg.url == "redis://127.0.0.1:6379"
    assert cfg.graph_name == "xhs"


def test_falkor_config_defaults_graph_name():
    cfg = falkor_config({"XHS_FALKOR_URL": "redis://127.0.0.1:6379", "XHS_FALKOR_GRAPH": ""})
    assert cfg.state == "enabled"
    assert cfg.graph_name == "xhs"


def test_falkor_config_disabled_when_missing_url():
    assert falkor_config({"XHS_FALKOR_URL": "", "XHS_FALKOR_GRAPH": "xhs"}).state == "disabled"
