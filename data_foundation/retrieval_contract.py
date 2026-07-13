from __future__ import annotations

from typing import Any


RETRIEVAL_ERROR_CODES = frozenset(
    {
        "INVALID_RETRIEVAL_REQUEST",
        "POSTGRES_KNOWLEDGE_GATE_FAILED",
        "KNOWLEDGE_RETRIEVAL_FAILED",
    }
)


def retrieval_error(code: str) -> dict[str, str]:
    if code not in RETRIEVAL_ERROR_CODES:
        raise ValueError("invalid retrieval error code")
    return {"error": code}


def is_retrieval_error_result(result: Any) -> bool:
    error = result.get("error") if isinstance(result, dict) else None
    return (
        isinstance(result, dict)
        and set(result) == {"error"}
        and isinstance(error, str)
        and error in RETRIEVAL_ERROR_CODES
    )


__all__ = [
    "RETRIEVAL_ERROR_CODES",
    "is_retrieval_error_result",
    "retrieval_error",
]
