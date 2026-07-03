from pathlib import Path


def test_agent_suppresses_known_rubric_beta_warning():
    source = Path("agent.py").read_text(encoding="utf-8")

    assert "from langchain_core._api import LangChainBetaWarning" in source
    assert "warnings.filterwarnings(" in source
    assert "category=LangChainBetaWarning" in source
