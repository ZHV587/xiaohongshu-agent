from __future__ import annotations

import hashlib
import unicodedata


# ZWJ is deliberately preserved: removing it corrupts multi-codepoint emoji such as
# family/profession glyphs.  The remaining characters are invisible separators or
# byte-order markers that frequently create false non-duplicates.
_REMOVED_ZERO_WIDTH = {"\u200b", "\u200c", "\u2060", "\ufeff"}
_PRESERVED_FORMAT_CONTROLS = {"\u200d"}  # emoji ZWJ


def normalize_knowledge_text(text: str | None) -> str:
    """Normalize text for matching without flattening paragraphs or emoji."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", str(text).replace("\r\n", "\n").replace("\r", "\n"))
    cleaned: list[str] = []
    for char in normalized:
        if char in _REMOVED_ZERO_WIDTH:
            continue
        category = unicodedata.category(char)
        if category == "Cc" and char not in {"\n", "\t"}:
            continue
        # Bidi marks/isolates and other invisible formatting controls are matching
        # noise.  Keep ZWJ and emoji tag code points so normalization never breaks a
        # valid multi-codepoint emoji sequence.
        if category == "Cf" and char not in _PRESERVED_FORMAT_CONTROLS:
            if not ("\U000e0020" <= char <= "\U000e007f"):
                continue
        cleaned.append(char)
    # Strip only the document boundary.  Internal blank lines/tabs remain evidence of
    # the author's structure and are therefore kept intact.
    return "".join(cleaned).strip()


def normalized_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
