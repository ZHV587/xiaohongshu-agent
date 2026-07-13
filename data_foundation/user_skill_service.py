from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping


DEFINITION_FIELDS = frozenset(
    {
        "displayName",
        "description",
        "instructions",
        "triggerExamples",
        "nonTriggerExamples",
        "tags",
    }
)
FORBIDDEN_CAPABILITY_FIELDS = frozenset(
    {
        "tool",
        "tools",
        "permission",
        "permissions",
        "script",
        "scripts",
        "path",
        "paths",
        "command",
        "commands",
        "file",
        "files",
        "network",
        "mcp",
        "subagent",
        "allowedtools",
        "filesystempath",
        "toolpermissions",
        "allowedcommands",
    }
)


class SkillDefinitionError(ValueError):
    def __init__(self, code: str, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.field = field


@dataclass(frozen=True)
class SkillDefinition:
    display_name: str
    description: str
    instructions: str
    trigger_examples: tuple[str, ...]
    non_trigger_examples: tuple[str, ...]
    tags: tuple[str, ...]

    def storage_kwargs(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "description": self.description,
            "instructions_markdown": self.instructions,
            "trigger_examples": list(self.trigger_examples),
            "non_trigger_examples": list(self.non_trigger_examples),
            "tags": list(self.tags),
        }


class UserSkillCompiler:
    MAX_DISPLAY_NAME = 80
    MAX_DESCRIPTION = 500
    MAX_INSTRUCTIONS = 32 * 1024
    MAX_EXAMPLES = 20
    MAX_EXAMPLE_LENGTH = 200
    MAX_TAGS = 20
    MAX_TAG_LENGTH = 50
    # deepagents 0.6.10 的 Skill metadata description 上限是 1024。
    MAX_ROUTING_DESCRIPTION = 1024

    @classmethod
    def validate(cls, payload: Mapping[str, Any]) -> SkillDefinition:
        if not isinstance(payload, Mapping):
            raise SkillDefinitionError("SKILL_INVALID_INPUT", "Skill definition must be an object")
        unknown = sorted(set(payload) - DEFINITION_FIELDS)
        if unknown:
            lowered = {re.sub(r"[_\-.]", "", str(field).casefold()) for field in unknown}
            code = (
                "SKILL_FIELD_NOT_ALLOWED"
                if lowered & FORBIDDEN_CAPABILITY_FIELDS
                else "SKILL_UNKNOWN_FIELD"
            )
            raise SkillDefinitionError(code, f"Field is not allowed: {unknown[0]}", field=unknown[0])

        display_name = cls._text(payload.get("displayName"), "displayName", cls.MAX_DISPLAY_NAME)
        description = cls._text(payload.get("description"), "description", cls.MAX_DESCRIPTION)
        instructions = cls._text(payload.get("instructions"), "instructions", cls.MAX_INSTRUCTIONS)
        if "\n" in display_name or "\r" in display_name:
            raise SkillDefinitionError(
                "SKILL_INVALID_INPUT", "displayName must be a single line", field="displayName"
            )
        if "\n" in description or "\r" in description:
            raise SkillDefinitionError(
                "SKILL_INVALID_INPUT", "description must be a single line", field="description"
            )

        trigger_examples = cls._string_list(
            payload.get("triggerExamples", []),
            field="triggerExamples",
            max_items=cls.MAX_EXAMPLES,
            max_length=cls.MAX_EXAMPLE_LENGTH,
        )
        non_trigger_examples = cls._string_list(
            payload.get("nonTriggerExamples", []),
            field="nonTriggerExamples",
            max_items=cls.MAX_EXAMPLES,
            max_length=cls.MAX_EXAMPLE_LENGTH,
        )
        tags = cls._string_list(
            payload.get("tags", []),
            field="tags",
            max_items=cls.MAX_TAGS,
            max_length=cls.MAX_TAG_LENGTH,
        )
        definition = SkillDefinition(
            display_name=display_name,
            description=description,
            instructions=instructions,
            trigger_examples=trigger_examples,
            non_trigger_examples=non_trigger_examples,
            tags=tags,
        )
        cls.routing_description(definition)
        return definition

    @classmethod
    def compile(cls, runtime_name: str, definition: SkillDefinition) -> str:
        if not re.fullmatch(r"usr-[a-z0-9-]+", runtime_name or ""):
            raise SkillDefinitionError("SKILL_INVALID_RUNTIME_NAME", "Invalid runtime Skill name")
        routing_description = cls.routing_description(definition)
        sections = [
            "---",
            f"name: {json.dumps(runtime_name, ensure_ascii=False)}",
            f"description: {json.dumps(routing_description, ensure_ascii=False)}",
            "---",
            "",
            f"# {definition.display_name}",
            "",
            definition.instructions,
        ]
        if definition.trigger_examples:
            sections.extend(["", "## 适用示例", *[f"- {item}" for item in definition.trigger_examples]])
        if definition.non_trigger_examples:
            sections.extend(
                ["", "## 不适用示例", *[f"- {item}" for item in definition.non_trigger_examples]]
            )
        if definition.tags:
            sections.extend(["", "## 标签", "、".join(definition.tags)])
        return "\n".join(sections).rstrip() + "\n"

    @classmethod
    def routing_description(cls, definition: SkillDefinition) -> str:
        parts = [definition.description]
        if definition.trigger_examples:
            parts.append("适用场景：" + "；".join(definition.trigger_examples))
        if definition.non_trigger_examples:
            parts.append("不适用：" + "；".join(definition.non_trigger_examples))
        if definition.tags:
            parts.append("标签：" + "、".join(definition.tags))
        rendered = " ".join(parts)
        if len(rendered) > cls.MAX_ROUTING_DESCRIPTION:
            raise SkillDefinitionError(
                "SKILL_INVALID_INPUT",
                f"Compiled description exceeds {cls.MAX_ROUTING_DESCRIPTION} characters",
                field="description",
            )
        return rendered

    @staticmethod
    def _text(value: Any, field: str, max_length: int) -> str:
        if not isinstance(value, str):
            raise SkillDefinitionError("SKILL_INVALID_INPUT", f"{field} must be text", field=field)
        normalized = unicodedata.normalize(
            "NFC", value.replace("\r\n", "\n").replace("\r", "\n")
        ).strip()
        for char in normalized:
            if unicodedata.category(char) == "Cc" and char not in {"\n", "\t"}:
                raise SkillDefinitionError(
                    "SKILL_INVALID_INPUT", f"{field} contains an invalid control character", field=field
                )
        if not normalized:
            raise SkillDefinitionError("SKILL_INVALID_INPUT", f"{field} is required", field=field)
        if len(normalized) > max_length:
            raise SkillDefinitionError(
                "SKILL_INVALID_INPUT", f"{field} exceeds {max_length} characters", field=field
            )
        return normalized

    @classmethod
    def _string_list(
        cls, value: Any, *, field: str, max_items: int, max_length: int
    ) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise SkillDefinitionError("SKILL_INVALID_INPUT", f"{field} must be an array", field=field)
        if len(value) > max_items:
            raise SkillDefinitionError(
                "SKILL_INVALID_INPUT", f"{field} exceeds {max_items} items", field=field
            )
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = cls._text(item, field, max_length)
            normalized = re.sub(r"\s+", " ", normalized)
            key = normalized.casefold()
            if key not in seen:
                result.append(normalized)
                seen.add(key)
        return tuple(result)


def definition_from_version(version: Any) -> SkillDefinition:
    return SkillDefinition(
        display_name=version.display_name,
        description=version.description,
        instructions=version.instructions_markdown,
        trigger_examples=tuple(version.trigger_examples),
        non_trigger_examples=tuple(version.non_trigger_examples),
        tags=tuple(version.tags),
    )
