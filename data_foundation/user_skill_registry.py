from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable

from data_foundation.models import UserSkillRegistryEntry


logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SYSTEM_SKILLS_ROOT = _PROJECT_ROOT / ".agents" / "skills"
_MAX_SKILL_FILE_BYTES = 64 * 1024
_VALID_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DEPRECATED_MARKERS = ("已废弃", "deprecated")


def _plain_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace(r'\"', '"').replace(r"\n", "\n")
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _frontmatter(text: str) -> dict[str, Any] | None:
    """解析受限 frontmatter，只识别顶层 name/description，不执行 YAML 类型构造。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return None
    frontmatter = lines[1:end]
    parsed: dict[str, str] = {}
    index = 0
    while index < len(frontmatter):
        line = frontmatter[index]
        if line.startswith((" ", "\t")) or ":" not in line:
            index += 1
            continue
        key, raw_value = line.split(":", 1)
        if key not in {"name", "description"}:
            index += 1
            continue
        value = raw_value.strip()
        if value in {"|", "|-", "|+", ">", ">-", ">+"}:
            block: list[str] = []
            index += 1
            while index < len(frontmatter):
                nested = frontmatter[index]
                if nested and not nested.startswith((" ", "\t")):
                    break
                block.append(nested.lstrip())
                index += 1
            parsed[key] = (" " if value.startswith(">") else "\n").join(block).strip()
            continue
        parsed[key] = _plain_scalar(value)
        index += 1
    return parsed


def load_system_skill_items(skills_root: Path | None = None) -> list[dict[str, Any]]:
    """安全读取系统 Skill frontmatter；无效、越界和废弃条目直接跳过。"""
    root = (skills_root or _SYSTEM_SKILLS_ROOT).resolve()
    try:
        directories = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        logger.warning("system_skill_registry_root_unavailable")
        return []

    items: list[dict[str, Any]] = []
    for directory in directories:
        skill_file = directory / "SKILL.md"
        try:
            resolved = skill_file.resolve(strict=True)
            if root not in resolved.parents or not resolved.is_file():
                continue
            if resolved.stat().st_size > _MAX_SKILL_FILE_BYTES:
                continue
            parsed = _frontmatter(resolved.read_text(encoding="utf-8"))
            if parsed is None:
                continue
            name = parsed.get("name")
            description = parsed.get("description")
            if (
                not isinstance(name, str)
                or not isinstance(description, str)
                or name != directory.name
                or not _VALID_SKILL_NAME.fullmatch(name)
            ):
                continue
            description = description.strip()
            if not description or len(description) > 4096:
                continue
            lowered = description.casefold()
            if any(marker.casefold() in lowered for marker in _DEPRECATED_MARKERS):
                continue
            items.append(
                {
                    "name": name,
                    "displayName": name,
                    "description": description,
                    "source": "system",
                    "readonly": True,
                }
            )
        except (OSError, UnicodeError, ValueError):
            logger.warning("system_skill_registry_entry_skipped name=%s", directory.name)
    return items


def user_skill_items(entries: Iterable[UserSkillRegistryEntry]) -> list[dict[str, Any]]:
    """把数据库最小投影转换为前端注册表契约，不携带正文或内容哈希。"""
    return [
        {
            "skillId": entry.skill_id,
            "versionId": entry.version_id,
            "runtimeName": entry.runtime_name,
            "displayName": entry.display_name,
            "description": entry.description,
            "tags": list(entry.tags),
            "source": "user",
            "readonly": False,
        }
        for entry in entries
    ]


def build_skill_registry(
    user_entries: Iterable[UserSkillRegistryEntry],
    *,
    skills_root: Path | None = None,
) -> list[dict[str, Any]]:
    return [*load_system_skill_items(skills_root), *user_skill_items(user_entries)]


__all__ = ["build_skill_registry", "load_system_skill_items", "user_skill_items"]
