"""Packaging metadata regression tests."""

from pathlib import Path
import tomllib


def test_pyproject_packages_imported_root_modules():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    py_modules = set(pyproject["tool"]["setuptools"]["py-modules"])

    assert {
        "agent",
        "auth",
        "backends",
        "config_center",
        "middlewares",
        "model_health",
        "model_registry",
        "models",
        "prompts",
        "subagents_executor",
    } <= py_modules
    assert "content_rubric" not in py_modules
    assert "rubric_model" not in py_modules
