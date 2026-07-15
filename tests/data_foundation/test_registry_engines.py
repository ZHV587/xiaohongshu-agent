from unittest.mock import MagicMock, patch

from data_foundation.processors.registry import default_processor_registry


def test_registry_includes_meili_when_configured():
    with patch.dict(
        "os.environ",
        {
            "XHS_MEILI_URL": "http://x",
            "XHS_MEILI_KEY": "k",
            # Keep this unit test hermetic when the developer/production .env
            # enables FalkorDB. Registry construction eagerly opens FalkorDB.
            "XHS_FALKOR_URL": "",
            "XHS_FALKOR_GRAPH": "",
        },
    ):
        with patch("data_foundation.meili_client.meilisearch.Client", MagicMock()):
            reg = default_processor_registry(MagicMock(), embedding_config=None)
    assert "meili_index" in reg.topics
    assert reg.processor_for("meili_index") is not None


def test_registry_includes_graph_when_configured():
    with patch.dict("os.environ", {"XHS_FALKOR_URL": "redis://x:6379", "XHS_FALKOR_GRAPH": "xhs"}):
        with patch("data_foundation.falkor_client.falkordb.FalkorDB", MagicMock()):
            reg = default_processor_registry(MagicMock(), embedding_config=None)
    assert "graph_ingest" in reg.topics
    assert reg.processor_for("graph_ingest") is not None
