from pathlib import Path


def test_agent_does_not_hide_beta_warnings():
    source = Path("agent.py").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "warnings.filterwarnings(" not in source
    assert "LangChainBetaWarning" not in source
    assert "filterwarnings" not in pyproject


def test_agent_runtime_does_not_wire_beta_rubric_middleware():
    source = Path("agent.py").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "RubricMiddleware" not in source
    assert "ContentRubricActivator" not in source
    assert "RegistryRoutedChatModel" not in source
    assert "content_rubric" not in pyproject
    assert "rubric_model" not in pyproject


def test_data_foundation_tests_do_not_use_deprecated_starlette_testclient():
    for path in Path("tests/data_foundation").glob("test_*.py"):
        source = path.read_text(encoding="utf-8")
        assert "starlette.testclient" not in source, path
