import pytest
from cryptography.fernet import Fernet

from config_center import (
    ConfigCenter,
    ConfigValidationError,
    bootstrap_snapshot_from_env,
)


def test_config_center_encrypts_secret_values(tmp_path):
    key = Fernet.generate_key().decode()
    path = tmp_path / "config-center.enc"
    center = ConfigCenter(path=path, encryption_key=key)

    saved = center.save(
        actor_open_id="ou_admin",
        updates={
            "LLM_PROVIDER": "openai",
            "LLM_BASE_URL": "https://gateway.example/v1",
            "LLM_API_KEY": "sk-secret",
            "LLM_QUALITY_MODELS": "gpt-4o,claude-sonnet-4-6",
        },
    )

    raw = path.read_bytes()
    assert b"sk-secret" not in raw
    assert saved.version
    assert center.get_plain()["LLM_API_KEY"] == "sk-secret"
    assert center.get_redacted()["LLM_API_KEY"] == "********"


def test_config_center_rejects_deploy_only_keys(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    with pytest.raises(ConfigValidationError, match="XHS_JWT_SECRET"):
        center.save(actor_open_id="ou_admin", updates={"XHS_JWT_SECRET": "do-not-edit"})


def test_config_center_rejects_internal_base_url(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    with pytest.raises(ConfigValidationError, match="XHS_INTERNAL_BASE_URL"):
        center.save(actor_open_id="ou_admin", updates={"XHS_INTERNAL_BASE_URL": "http://127.0.0.1:2024"})


def test_config_center_rejects_unsupported_embedding_dimensions(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    with pytest.raises(ConfigValidationError, match="XHS_EMBEDDING_DIMENSIONS"):
        center.save(actor_open_id="ou_admin", updates={"XHS_EMBEDDING_DIMENSIONS": "3072"})


def test_config_center_records_audit_history(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    first = center.save(actor_open_id="ou_admin", updates={"LLM_PROVIDER": "openai"})
    second = center.save(actor_open_id="ou_admin", updates={"LLM_QUALITY_MODELS": "gpt-4o"})

    history = center.history()
    assert [item.version for item in history] == [first.version, second.version]
    assert history[0].actor_open_id == "ou_admin"
    assert history[1].changed_keys == ["LLM_QUALITY_MODELS"]


def test_config_center_gets_historical_profile(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    first = center.save(
        actor_open_id="ou_admin",
        updates={
            "XHS_EMBEDDING_BASE_URL": "https://embedding.example/v1",
            "XHS_EMBEDDING_API_KEY": "embedding-key",
            "XHS_EMBEDDING_MODEL": "model-a",
            "XHS_EMBEDDING_DIMENSIONS": "1536",
            "XHS_EMBEDDING_BATCH_SIZE": "64",
            "XHS_EMBEDDING_TIMEOUT_SECONDS": "30",
        },
    )
    center.save(actor_open_id="ou_admin", updates={"XHS_EMBEDDING_MODEL": "model-b"})

    assert center.get_version(first.version).values["XHS_EMBEDDING_MODEL"] == "model-a"
    with pytest.raises(KeyError):
        center.get_version("missing-version")


def test_config_center_redacts_embedding_api_key(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    center.save(
        actor_open_id="ou_admin",
        updates={
            "XHS_EMBEDDING_BASE_URL": "https://embedding.example/v1",
            "XHS_EMBEDDING_API_KEY": "embedding-secret",
            "XHS_EMBEDDING_MODEL": "text-embedding-3-small",
        },
    )

    redacted = center.get_redacted()

    assert redacted["XHS_EMBEDDING_API_KEY"] == "********"
    assert redacted["XHS_EMBEDDING_BASE_URL"] == "https://embedding.example/v1"


def test_bootstrap_snapshot_from_env_imports_allowed_keys(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-bootstrap")
    monkeypatch.setenv("LLM_QUALITY_MODELS", "gpt-4o")
    monkeypatch.setenv("XHS_JWT_SECRET", "not-imported")

    snapshot = bootstrap_snapshot_from_env(actor_open_id="system-bootstrap")

    assert snapshot.values["LLM_API_KEY"] == "sk-bootstrap"
    assert "XHS_JWT_SECRET" not in snapshot.values


def test_engine_keys_are_deploy_only():
    from config_center import DEPLOY_ONLY_KEYS, SECRET_KEYS
    assert "XHS_MEILI_URL" in DEPLOY_ONLY_KEYS
    assert "XHS_MEILI_KEY" in DEPLOY_ONLY_KEYS
    assert "XHS_FALKOR_URL" in DEPLOY_ONLY_KEYS
    assert "XHS_FALKOR_GRAPH" in DEPLOY_ONLY_KEYS
    assert "XHS_MEILI_KEY" in SECRET_KEYS


def test_config_center_atomic_write_survives_mid_write_crash(tmp_path, monkeypatch):
    """写到一半进程被杀(OOM/容器重启),目标文件必须保持上一份完好,不被截断损坏。

    根因:原 _write_document 用 path.write_bytes 直接覆写,非原子 —— 写一半中断会把
    .enc 截断成残片,下次 decrypt 抛 InvalidToken,整个配置中心(含 history)永久不可读。
    修复后用临时文件 + os.replace 原子 rename,任一时刻只读到完整旧/新文件。
    """
    import os
    path = tmp_path / "config.enc"
    center = ConfigCenter(path=path, encryption_key=Fernet.generate_key().decode())
    center.save(actor_open_id="ou_admin", updates={"LLM_BASE_URL": "https://gw1/v1"})

    # 模拟"临时文件已写、os.replace 前"进程被杀:让 fsync 抛异常。
    real_fsync = os.fsync

    def boom(fd):
        real_fsync(fd)
        raise KeyboardInterrupt("simulated kill mid-write")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(KeyboardInterrupt):
        center.save(actor_open_id="ou_admin", updates={"LLM_API_KEY": "k2"})
    monkeypatch.undo()

    # 目标文件保持第一次保存的完好内容(不损坏、未被部分写污染)。
    assert center.get_plain() == {"LLM_BASE_URL": "https://gw1/v1"}
    # 临时文件被清理,无泄漏。
    assert [f for f in os.listdir(tmp_path) if f.endswith(".tmp")] == []
    # 后续正常保存仍工作,history 正确累积。
    center.save(actor_open_id="ou_admin", updates={"LLM_API_KEY": "k3"})
    assert center.get_plain()["LLM_API_KEY"] == "k3"
    assert len(center.history()) == 2


def _center(tmp_path):
    return ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())


def test_config_center_rejects_query_instruction_without_placeholder(tmp_path):
    center = _center(tmp_path)
    with pytest.raises(ConfigValidationError, match="{query}"):
        center.save(actor_open_id="ou_admin", updates={"XHS_EMBEDDING_QUERY_INSTRUCTION": "no placeholder"})


def test_config_center_accepts_valid_query_instruction(tmp_path):
    center = _center(tmp_path)
    saved = center.save(
        actor_open_id="ou_admin",
        updates={"XHS_EMBEDDING_QUERY_INSTRUCTION": "Instruct: x\nQuery: {query}"},
    )
    assert center.get_plain()["XHS_EMBEDDING_QUERY_INSTRUCTION"] == "Instruct: x\nQuery: {query}"
    assert saved.version


def test_config_center_rejects_out_of_range_relevance_floor(tmp_path):
    center = _center(tmp_path)
    for bad in ("1.5", "-0.1", "abc"):
        with pytest.raises(ConfigValidationError, match=r"\[0, 1\]"):
            center.save(actor_open_id="ou_admin", updates={"XHS_EMBEDDING_RELEVANCE_FLOOR": bad})


def test_config_center_accepts_valid_relevance_floor(tmp_path):
    center = _center(tmp_path)
    center.save(actor_open_id="ou_admin", updates={"XHS_EMBEDDING_RELEVANCE_FLOOR": "0.55"})
    assert center.get_plain()["XHS_EMBEDDING_RELEVANCE_FLOOR"] == "0.55"


def test_project_config_to_env_projects_editable_and_overrides(monkeypatch):
    from config_center import project_config_to_env

    # .env 已有旧值,config-center 管理的 key 应覆盖;预先 setenv 全部待投影 key 以便 teardown 回滚
    monkeypatch.setenv("FEISHU_APP_ID", "old-app-id")
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "old-token")
    monkeypatch.setenv("XHS_BITABLE_FIELD_TITLE", "旧标题列")
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    projected = project_config_to_env(
        {
            "FEISHU_APP_ID": "cli_new",
            "FEISHU_BITABLE_APP_TOKEN": "bascn_new",
            "XHS_BITABLE_FIELD_TITLE": "标题",
        }
    )

    import os

    assert os.environ["FEISHU_APP_ID"] == "cli_new"  # 覆盖 .env
    assert os.environ["FEISHU_BITABLE_APP_TOKEN"] == "bascn_new"
    assert os.environ["XHS_BITABLE_FIELD_TITLE"] == "标题"
    # 未被 config-center 管理的 key 保留 .env(未投影)
    assert os.environ["LLM_PROVIDER"] == "openai"
    assert projected == sorted(["FEISHU_APP_ID", "FEISHU_BITABLE_APP_TOKEN", "XHS_BITABLE_FIELD_TITLE"])


def test_project_config_to_env_skips_deploy_only_and_unknown(monkeypatch):
    from config_center import project_config_to_env

    monkeypatch.delenv("XHS_JWT_SECRET", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "seed")  # 预先 setenv 待投影 key,teardown 回滚防泄漏
    projected = project_config_to_env(
        {
            "XHS_JWT_SECRET": "should-not-project",   # DEPLOY_ONLY
            "XHS_INTERNAL_SECRET": "nope",            # DEPLOY_ONLY
            "TOTALLY_UNKNOWN_KEY": "x",               # 未知
            "LLM_API_KEY": "sk-ok",                   # EDITABLE
        }
    )

    import os

    assert "XHS_JWT_SECRET" not in os.environ
    assert os.environ.get("TOTALLY_UNKNOWN_KEY") is None
    assert os.environ["LLM_API_KEY"] == "sk-ok"
    assert projected == ["LLM_API_KEY"]


def test_project_config_to_env_empty_value_clears(monkeypatch):
    # config-center 把某 key 改空 → 覆盖为空串(消费方按"未配置"处理),不残留 .env 旧值
    from config_center import project_config_to_env

    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl_old")
    project_config_to_env({"FEISHU_BITABLE_TABLE_ID": ""})

    import os

    assert os.environ["FEISHU_BITABLE_TABLE_ID"] == ""


def test_llm_thinking_is_editable_not_secret():
    from config_center import EDITABLE_KEYS, SECRET_KEYS, DEPLOY_ONLY_KEYS
    assert "LLM_THINKING" in EDITABLE_KEYS
    assert "LLM_THINKING" not in SECRET_KEYS
    assert "LLM_THINKING" not in DEPLOY_ONLY_KEYS


def test_llm_thinking_triggers_pool_rebuild():
    from data_foundation.internal_api import _MODEL_POOL_KEYS
    assert "LLM_THINKING" in _MODEL_POOL_KEYS
