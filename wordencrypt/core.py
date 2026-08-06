"""
wordencrypt/core.py

Core library for protecting Markdown manuscripts from clean scraping/
tokenization by LLM training pipelines, while preserving formatting and
human legibility.

Three perturbation strategies:
  zero_width  - insert invisible chars after eligible letters
  homoglyph   - swap eligible Latin letters with Cyrillic/Greek lookalikes
  combining   - append combining diacritical marks after eligible letters

Markdown-aware segmentation: code fences, inline code, links/images,
autolinks, raw HTML, and leading structural markers are never perturbed.
"""

import base64
import random
import re

# ---------------------------------------------------------------------------
# Perturbation constants
# ---------------------------------------------------------------------------

ZERO_WIDTH_CHARS = [
    "\u200b",  # zero width space
    "\u200c",  # zero width non-joiner
    "\u200d",  # zero width joiner
    "\ufeff",  # zero width no-break space
]

# Latin -> Cyrillic/Greek visually-identical homoglyphs (case-preserving)
HOMOGLYPHS = {
    "a": "\u0430",  # Cyrillic а
    "e": "\u0435",  # Cyrillic е
    "o": "\u043e",  # Cyrillic о
    "p": "\u0440",  # Cyrillic р
    "c": "\u0441",  # Cyrillic с
    "x": "\u0445",  # Cyrillic х
    "i": "\u0456",  # Cyrillic Ukrainian і
    "j": "\u0458",  # Cyrillic ј
    "s": "\u0455",  # Cyrillic ѕ
    "y": "\u0443",  # Cyrillic у
}

# Explicit uppercase mappings (most Cyrillic homoglyphs lack a distinct upper)
HOMOGLYPHS_UPPER = {
    "A": "\u0410",  # Cyrillic А
    "E": "\u0415",  # Cyrillic Е
    "O": "\u041e",  # Cyrillic О
    "P": "\u0420",  # Cyrillic Р
    "C": "\u0421",  # Cyrillic С
    "X": "\u0425",  # Cyrillic Х
    "I": "\u0406",  # Cyrillic Ukrainian І
    "J": "\u0408",  # Cyrillic Ј
    "S": "\u0405",  # Cyrillic Ѕ
    "Y": "\u0423",  # Cyrillic У
}

COMBINING_MARKS = [
    "\u0301",  # combining acute accent
    "\u0300",  # combining grave accent
    "\u0308",  # combining diaeresis
    "\u0303",  # combining tilde
    "\u0304",  # combining macron
    "\u0306",  # combining breve
    "\u0307",  # combining dot above
    "\u030c",  # combining caron
    "\u0327",  # combining cedilla
    "\u0328",  # combining ogonek
]

# ---------------------------------------------------------------------------
# Markdown segmentation
# ---------------------------------------------------------------------------

# Patterns for regions that must never be modified
_FENCE_RE = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_LINK_OR_IMAGE_RE = re.compile(r"!?\[[^\]]*\]\([^)]*\)")
_AUTOLINK_RE = re.compile(r"<https?://[^>]+>")
_HTML_TAG_RE = re.compile(r"<[^>\n]+>")
_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")

_PROTECTED_PATTERNS = [
    _FENCE_RE,
    _INLINE_CODE_RE,
    _LINK_OR_IMAGE_RE,
    _AUTOLINK_RE,
    _HTML_COMMENT_RE,
    _HTML_TAG_RE,
]

# Leading markers to preserve on each line (headings, lists, blockquotes)
_LEADING_MARKER_RE = re.compile(
    r"^(\s{0,3}(#{1,6}\s+|>+\s*|[-*+]\s+|\d+\.\s+))"
)


def _split_protected_spans(text: str):
    """Return list of (protected: bool, chunk: str) covering the whole text.

    Protected spans are code fences, inline code, links/images, autolinks,
    and raw HTML tags — they must pass through unchanged.
    """
    spans = []
    for pat in _PROTECTED_PATTERNS:
        for m in pat.finditer(text):
            spans.append((m.start(), m.end()))
    spans.sort()

    # Merge overlapping/adjacent spans
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    out = []
    pos = 0
    for start, end in merged:
        if start > pos:
            out.append((False, text[pos:start]))
        out.append((True, text[start:end]))
        pos = end
    if pos < len(text):
        out.append((False, text[pos:]))
    return out


def _perturb_line(line: str, perturb_fn, density: float) -> str:
    """Perturb a single prose line, preserving any leading markdown marker."""
    m = _LEADING_MARKER_RE.match(line)
    if m:
        marker = m.group(0)
        rest = line[m.end():]
        return marker + perturb_fn(rest, density=density)
    return perturb_fn(line, density=density)


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------


def insert_zero_width(text: str, density: float = 0.3) -> str:
    """Insert invisible zero-width chars after eligible alphabetic chars."""
    out = []
    for ch in text:
        out.append(ch)
        if ch.isalpha() and random.random() < density:
            out.append(random.choice(ZERO_WIDTH_CHARS))
    return "".join(out)


def insert_homoglyphs(text: str, density: float = 0.3) -> str:
    """Replace eligible Latin letters with visually-identical lookalikes."""
    out = []
    for ch in text:
        if ch.isupper() and ch in HOMOGLYPHS_UPPER and random.random() < density:
            out.append(HOMOGLYPHS_UPPER[ch])
        elif ch.islower() and ch in HOMOGLYPHS and random.random() < density:
            out.append(HOMOGLYPHS[ch])
        else:
            out.append(ch)
    return "".join(out)


def insert_combining_marks(text: str, density: float = 0.3) -> str:
    """Append 1-2 combining diacritical marks after eligible alphabetic chars."""
    out = []
    for ch in text:
        out.append(ch)
        if ch.isalpha() and random.random() < density:
            n = random.randint(1, 2)
            out.extend(random.choice(COMBINING_MARKS) for _ in range(n))
    return "".join(out)


CHAR_STRATEGIES = {
    "zero_width": insert_zero_width,
    "homoglyph": insert_homoglyphs,
    "combining": insert_combining_marks,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _append_watermark_comment(text: str, watermark: str) -> str:
    encoded = base64.b64encode(watermark.encode("utf-8")).decode("ascii")
    comment = f"<!-- wm:{encoded} -->"
    if not text:
        return comment
    return f"{text}\n\n{comment}"


def extract_watermark(text: str) -> str | None:
    """Return decoded watermark from `<!-- wm:<base64> -->`, if present/valid."""
    m = re.search(r"<!--\s*wm:([A-Za-z0-9+/=]+)\s*-->", text)
    if not m:
        return None
    encoded = m.group(1)
    try:
        decoded = base64.b64decode(encoded, validate=True)
        return decoded.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def _normalize_combined_weights(
    density: float, weights: dict[str, float] | None
) -> dict[str, float]:
    if weights is not None:
        normalized = {}
        for name in ("zero_width", "homoglyph", "combining"):
            try:
                value = float(weights.get(name, 0.0))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid weight for {name!r}") from exc
            normalized[name] = max(0.0, min(1.0, value))
        return normalized

    # Defaults intentionally reduce homoglyph/combining intensity because
    # stacking all three strategies at full density can become too noisy.
    return {
        "zero_width": density,
        "homoglyph": density * 0.6,
        "combining": density * 0.5,
    }


def protect_markdown_combined(
    text: str,
    density: float = 0.15,
    weights: dict[str, float] | None = None,
    watermark: str | None = None,
) -> str:
    """Apply zero_width -> homoglyph -> combining across prose spans."""
    density = max(0.0, min(1.0, density))
    strategy_weights = _normalize_combined_weights(density, weights)

    def _combined_perturb_line(line: str) -> str:
        m = _LEADING_MARKER_RE.match(line)
        marker = m.group(0) if m else ""
        rest = line[m.end() :] if m else line
        rest = insert_zero_width(rest, density=strategy_weights["zero_width"])
        rest = insert_homoglyphs(rest, density=strategy_weights["homoglyph"])
        rest = insert_combining_marks(rest, density=strategy_weights["combining"])
        return marker + rest

    spans = _split_protected_spans(text)
    parts = []
    for is_protected, chunk in spans:
        if is_protected:
            parts.append(chunk)
        else:
            lines = chunk.split("\n")
            parts.append("\n".join(_combined_perturb_line(line) for line in lines))
    protected = "".join(parts)
    if watermark is not None:
        protected = _append_watermark_comment(protected, watermark)
    return protected


def protect_markdown(
    text: str,
    strategy: str = "homoglyph",
    density: float = 0.25,
    weights: dict[str, float] | None = None,
    watermark: str | None = None,
) -> str:
    """Perturb only the prose portions of a Markdown document.

    Code fences, inline code, links/images, autolinks, raw HTML, and
    leading line markers (#, >, -, 1.) are left completely untouched.

    Args:
        text:     The Markdown source to protect.
        strategy: One of "zero_width", "homoglyph", "combining", "combined".
        density:  Fraction of eligible characters to perturb (0.0–1.0).

    Returns:
        The protected Markdown string.
    """
    if strategy not in STRATEGIES:
        raise ValueError(
            f"Unknown strategy {strategy!r}. Choose from {list(STRATEGIES)}"
        )
    density = max(0.0, min(1.0, density))

    if strategy == "combined":
        return protect_markdown_combined(
            text,
            density=density,
            weights=weights,
            watermark=watermark,
        )

    perturb_fn = STRATEGIES[strategy]

    spans = _split_protected_spans(text)
    parts = []
    for is_protected, chunk in spans:
        if is_protected:
            parts.append(chunk)
        else:
            lines = chunk.split("\n")
            parts.append(
                "\n".join(_perturb_line(line, perturb_fn, density) for line in lines)
            )
    protected = "".join(parts)
    if watermark is not None:
        protected = _append_watermark_comment(protected, watermark)
    return protected


STRATEGIES = {
    **CHAR_STRATEGIES,
    "combined": protect_markdown_combined,
}


# ---------------------------------------------------------------------------
# Tokenization measurement helpers
# ---------------------------------------------------------------------------

# Approximate GPT-2/GPT-4 BPE pretokenization pattern
# Note: whitespace is simplified to \s+ (avoiding polynomial backtracking)
_PRETOKEN_PATTERN = re.compile(
    r"'s|'t|'re|'ve|'m|'ll|'d| ?[^\W\d_]+| ?\d+| ?[^\s\w]+|\s+",
    re.UNICODE,
)


def pretokenize(text: str) -> list:
    """Approximate GPT-style BPE pretokenization chunks."""
    return _PRETOKEN_PATTERN.findall(text)


def compare_tokenization(original: str, modified: str) -> dict:
    """Return token counts and expansion ratio for original vs. modified text."""
    orig_chunks = pretokenize(original)
    mod_chunks = pretokenize(modified)
    orig_count = len(orig_chunks)
    mod_count = len(mod_chunks)
    return {
        "original_token_count": orig_count,
        "modified_token_count": mod_count,
        "expansion_ratio": round(mod_count / max(orig_count, 1), 4),
    }
