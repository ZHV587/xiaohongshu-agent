from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet


@contextmanager
def _file_lock(path: Path):
    """对 <path>.lock 取跨进程独占锁(Linux fcntl / Windows msvcrt)。

    生产是 Linux(fcntl.flock,进程退出/崩溃自动释放,无死锁残留)。锁原语不可用的平台
    (或导入失败)优雅降级为无锁——行为与加锁前一致,不阻断功能。
    """
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except ImportError:
            try:
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            except Exception:
                pass  # 无可用锁原语:降级无锁
        except Exception:
            pass
        yield
    finally:
        fh.close()

EDITABLE_KEYS = {
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_QUALITY_MODELS",
    "LLM_THINKING",
    "LLM_GATEWAY_2_BASE_URL",
    "LLM_GATEWAY_2_API_KEY",
    "LLM_GATEWAY_3_BASE_URL",
    "LLM_GATEWAY_3_API_KEY",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_BITABLE_APP_TOKEN",
    "FEISHU_BITABLE_TABLE_ID",
    "FEISHU_WIKI_SPACE_ID",
    "XHS_BITABLE_FIELD_TITLE",
    "XHS_BITABLE_FIELD_BODY",
    "XHS_BITABLE_FIELD_TAGS",
    "XHS_BITABLE_FIELD_AUTHOR",
    "XHS_BITABLE_FIELD_STATUS",
    "XHS_EMBEDDING_BASE_URL",
    "XHS_EMBEDDING_API_KEY",
    "XHS_EMBEDDING_MODEL",
    "XHS_EMBEDDING_DIMENSIONS",
    "XHS_EMBEDDING_BATCH_SIZE",
    "XHS_EMBEDDING_TIMEOUT_SECONDS",
    "XHS_EMBEDDING_QUERY_INSTRUCTION",
    "XHS_EMBEDDING_RELEVANCE_FLOOR",
}

SECRET_KEYS = {
    "LLM_API_KEY",
    "LLM_GATEWAY_2_API_KEY",
    "LLM_GATEWAY_3_API_KEY",
    "FEISHU_APP_SECRET",
    "XHS_EMBEDDING_API_KEY",
    "XHS_MEILI_KEY",
}

DEPLOY_ONLY_KEYS = {
    "XHS_ADMIN_OPEN_IDS",
    "XHS_JWT_SECRET",
    "XHS_UAT_ENCRYPTION_KEY",
    "XHS_INTERNAL_SECRET",
    "XHS_INTERNAL_BASE_URL",
    "XHS_CONFIG_ENCRYPTION_KEY",
    "XHS_CONFIG_CENTER_PATH",
    "XHS_MEILI_URL",
    "XHS_MEILI_KEY",
    "XHS_FALKOR_URL",
    "XHS_FALKOR_GRAPH",
    "PATH",
    "NODE_OPTIONS",
}


class ConfigValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ConfigSnapshot:
    version: str
    values: dict[str, str]
    actor_open_id: str
    changed_keys: list[str]
    created_at: float


def _make_version(values: dict[str, str], created_at: float) -> str:
    digest = sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"{int(created_at)}-{digest}"


def _validate_updates(updates: dict[str, Any]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in updates.items():
        if key in DEPLOY_ONLY_KEYS or key not in EDITABLE_KEYS:
            raise ConfigValidationError(f"Config key is not editable: {key}")
        # 只把 None 归一成空串;保留 0/0.0/False 的字面值,让下面的数值/边界校验正常命中
        # (此前 str(value or "") 会把 XHS_EMBEDDING_RELEVANCE_FLOOR=0 等合法 falsy 吞成空串、跳过校验)。
        sanitized_value = "" if value is None else str(value)
        if key == "XHS_EMBEDDING_DIMENSIONS" and sanitized_value.strip():
            try:
                dimensions = int(sanitized_value)
            except ValueError as exc:
                raise ConfigValidationError(
                    "XHS_EMBEDDING_DIMENSIONS only supports 1536 with the current vector schema"
                ) from exc
            if dimensions != 1536:
                raise ConfigValidationError(
                    "XHS_EMBEDDING_DIMENSIONS only supports 1536 with the current vector schema"
                )
        if key == "XHS_EMBEDDING_QUERY_INSTRUCTION" and sanitized_value.strip():
            if "{query}" not in sanitized_value:
                raise ConfigValidationError(
                    "XHS_EMBEDDING_QUERY_INSTRUCTION must contain the {query} placeholder"
                )
        if key == "XHS_EMBEDDING_RELEVANCE_FLOOR" and sanitized_value.strip():
            try:
                floor = float(sanitized_value)
            except ValueError as exc:
                raise ConfigValidationError(
                    "XHS_EMBEDDING_RELEVANCE_FLOOR must be a number in [0, 1]"
                ) from exc
            if not (0.0 <= floor <= 1.0):
                raise ConfigValidationError(
                    "XHS_EMBEDDING_RELEVANCE_FLOOR must be a number in [0, 1]"
                )
        sanitized[key] = sanitized_value
    return sanitized


class ConfigCenter:
    def __init__(self, path: Path | str, encryption_key: str) -> None:
        self.path = Path(path)
        self.fernet = Fernet(encryption_key.encode("utf-8"))

    def _read_document(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"current": {}, "history": []}
        decrypted = self.fernet.decrypt(self.path.read_bytes())
        return json.loads(decrypted.decode("utf-8"))

    def _write_document(self, document: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ciphertext = self.fernet.encrypt(payload)
        # 原子写:先写同目录临时文件 + fsync 落盘,再 os.replace 原子 rename 覆盖目标。
        # 直接 write_bytes 覆写非原子 —— 写到一半进程被杀(OOM/容器重启)会把目标文件
        # 截断成残片,下次 _read_document 的 fernet.decrypt 抛 InvalidToken,整个配置中心
        # (含 history)永久不可读。os.replace 在同一文件系统上是原子的:任一时刻读到的
        # 要么是完整旧文件、要么是完整新文件,绝无截断中间态。临时文件必须与目标同目录,
        # 否则跨设备 rename 会退化为非原子的拷贝+删除。
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=self.path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(ciphertext)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            # 写临时文件或 rename 失败:清理临时文件,目标文件保持原样(未被触碰)。
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def save(self, actor_open_id: str, updates: dict[str, Any]) -> ConfigSnapshot:
        sanitized = _validate_updates(updates)
        # 跨进程独占锁包住整个 read-modify-write:三个写入方(langgraph admin save、
        # web_bridge_runner 恢复子进程、embedding bootstrap)并发 save 时,无锁会各自读到同一
        # current+history、各 append 一条、后写的 os.replace 覆盖前者 → 丢一次配置变更+一条历史。
        # 锁文件用目标旁的 .lock,fcntl/msvcrt 不可用的平台优雅降级为无锁(行为同改前)。
        with _file_lock(self.path):
            document = self._read_document()
            current = {str(k): str(v) for k, v in document.get("current", {}).items()}
            next_values = {**current, **sanitized}
            created_at = time.time()
            snapshot = ConfigSnapshot(
                version=_make_version(next_values, created_at),
                values=next_values,
                actor_open_id=actor_open_id,
                changed_keys=sorted(sanitized),
                created_at=created_at,
            )
            history = list(document.get("history", []))
            history.append(
                {
                    "version": snapshot.version,
                    "values": snapshot.values,
                    "actor_open_id": snapshot.actor_open_id,
                    "changed_keys": snapshot.changed_keys,
                    "created_at": snapshot.created_at,
                }
            )
            self._write_document({"current": next_values, "history": history})
        return snapshot

    def get_plain(self) -> dict[str, str]:
        return {str(k): str(v) for k, v in self._read_document().get("current", {}).items()}

    def get_redacted(self) -> dict[str, str]:
        plain = self.get_plain()
        return {key: ("********" if key in SECRET_KEYS and value else value) for key, value in plain.items()}

    def history(self) -> list[ConfigSnapshot]:
        items = self._read_document().get("history", [])
        return [
            ConfigSnapshot(
                version=item["version"],
                values={str(k): str(v) for k, v in item["values"].items()},
                actor_open_id=item["actor_open_id"],
                changed_keys=list(item["changed_keys"]),
                created_at=float(item["created_at"]),
            )
            for item in items
        ]

    def get_version(self, version: str) -> ConfigSnapshot:
        for snapshot in self.history():
            if snapshot.version == version:
                return snapshot
        raise KeyError(version)


def bootstrap_snapshot_from_env(actor_open_id: str) -> ConfigSnapshot:
    values = {key: os.environ[key] for key in EDITABLE_KEYS if os.environ.get(key)}
    created_at = time.time()
    return ConfigSnapshot(
        version=_make_version(values, created_at),
        values=values,
        actor_open_id=actor_open_id,
        changed_keys=sorted(values),
        created_at=created_at,
    )


def default_config_center() -> ConfigCenter:
    key = os.environ["XHS_CONFIG_ENCRYPTION_KEY"]
    path = os.environ.get("XHS_CONFIG_CENTER_PATH", ".xhs-config/config-center.enc")
    return ConfigCenter(path=path, encryption_key=key)


def project_config_to_env(values: dict[str, Any]) -> list[str]:
    """把 config-center 可编辑配置投影进当前进程 os.environ,使所有 env-reading 消费方
    (飞书工具 lark_cli/feishu_bitable/feishu_actions、uat_store 等)遵从 config-center 为
    唯一权威源。

    语义(对齐 README"config-center 是唯一权威源"):config-center 管理的 key **覆盖** .env;
    未被 config-center 管理的 key 保留 .env(填补)。只投影 EDITABLE_KEYS —— DEPLOY_ONLY
    (JWT/内部密钥/引擎 URL 等)与未知 key 一律不动。返回被投影的 key 列表(不含值,供日志)。

    调用点:① http_app lifespan 启动(冷启动对齐);② internal_config_post 保存成功后
    (热生效,N_WORKERS=1 同进程,下次工具调用即读到新值)。
    """
    projected: list[str] = []
    for key, value in values.items():
        if key in EDITABLE_KEYS:
            os.environ[key] = str(value if value is not None else "")
            projected.append(key)
    return sorted(projected)


def latest_config_snapshot() -> ConfigSnapshot | None:
    """读 config-center 当前生效快照(history 末条),供进程启动时按权威配置构建模型池。

    返回 None 的两种情形(调用方应退回 env 冷启动,不报错):
    - 未配置 XHS_CONFIG_ENCRYPTION_KEY / 路径(无配置中心,纯 env 部署)
    - 配置中心存在但 history 为空(全新部署,尚无任何写入)

    只读,不在此处 bootstrap 写盘——写盘是 web 配置保存路径与 embedding 运行时快照
    的既有职责,避免多入口竞争写同一加密文件。
    """
    if not (os.environ.get("XHS_CONFIG_ENCRYPTION_KEY") and os.environ.get("XHS_CONFIG_CENTER_PATH")):
        return None
    history = default_config_center().history()
    return history[-1] if history else None
