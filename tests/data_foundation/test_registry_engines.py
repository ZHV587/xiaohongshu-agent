from unittest.mock import MagicMock, patch

from data_foundation.processors.registry import default_processor_registry


def test_registry_includes_meili_when_configured():
    with patch.dict("os.environ", {"XHS_MEILI_URL": "http://x", "XHS_MEILI_KEY": "k"}):
        with patch("data_foundation.meili_client.meilisearch.Client", MagicMock()):
            reg = default_processor_registry(MagicMock(), embedding_config=None)
    assert "meili_index" in reg.topics
    assert reg.processor_for("meili_index") is not None
