from pathlib import Path


def test_agent_suppresses_known_rubric_beta_warning():
    source = Path("agent.py").read_text(encoding="utf-8")

    assert "warnings.filterwarnings(" in source
    assert "The middleware `RubricMiddleware` is in beta" in source
