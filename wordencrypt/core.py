"""
wordencrypt/core.py

Core library for protecting Markdown manuscripts from clean scraping/
tokenization by LLM training pipelines, while preserving formatting and
human legibility.

Four perturbation strategies:
  zero_width  - insert invisible chars after eligible letters
  homoglyph   - swap eligible Latin letters with Cyrillic/Greek lookalikes
  combining   - append combining diacritical marks after eligible letters
  combined    - all three at once in a single left-to-right pass

Zero-width insertion is always applied as a base layer for every strategy
(controlled via the ``zero_width_density`` parameter, default 0.15).
For ``strategy="zero_width"`` the base layer is suppressed to avoid
double-insertion; the main ``density`` parameter drives zero-width
intensity for that specific strategy.

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

# ---------------------------------------------------------------------------
# Expanded homoglyph pools
# ---------------------------------------------------------------------------
# HOMOGLYPH_POOLS maps each eligible *lowercase* Latin letter to a list of
# visually-similar single-codepoint alternatives drawn from three sources:
#   1. Cyrillic / Greek block (same characters as HOMOGLYPHS above)
#   2. Mathematical Alphanumeric Symbols block (U+1D400–U+1D7FF):
#      bold, italic, bold-italic, sans-serif, sans-serif bold,
#      sans-serif italic, sans-serif bold-italic, monospace, and Fraktur
#      variants.  Several code points in the italic/fraktur/script ranges
#      are unassigned and redirect to legacy characters; those edge cases
#      are handled explicitly (e.g. italic 'h' → U+210E PLANCK CONSTANT).
#   3. Fullwidth Latin Forms (U+FF01–U+FF5E):
#      fullwidth small letters a–z at U+FF41 + offset.
#
# HOMOGLYPH_POOLS_UPPER is the parallel structure for uppercase letters.
# Keys are always the ASCII base letter (lowercase in POOLS, uppercase in
# POOLS_UPPER).  insert_homoglyphs picks uniformly at random from the pool.
#
# All entries are standalone single codepoints with no combining/zero-width
# properties — safe to paste on any plain-text platform (Reddit, blogs, etc.)
# without requiring HTML support.

import unicodedata as _unicodedata

# Fraktur lowercase has holes at h → U+210C, i → U+2111
_FRAKTUR_LOWER_EX = {"h": "\u210c", "i": "\u2111"}
_ITALIC_LOWER_EX = {"h": "\u210e"}

# Fraktur uppercase has holes: C→U+212D, H→U+210C, I→U+2111, R→U+211C, Z→U+2128
_FRAKTUR_UPPER_EX = {
    "C": "\u212d",
    "H": "\u210c",
    "I": "\u2111",
    "R": "\u211c",
    "Z": "\u2128",
}

_MATH_LOWER_BASES = [
    (0x1D41A, None),               # bold
    (0x1D44E, _ITALIC_LOWER_EX),   # italic (h exception)
    (0x1D482, None),               # bold italic
    (0x1D5BA, None),               # sans-serif
    (0x1D5EE, None),               # sans-serif bold
    (0x1D622, None),               # sans-serif italic
    (0x1D656, None),               # sans-serif bold italic
    (0x1D68A, None),               # monospace
]

_MATH_UPPER_BASES = [
    0x1D400,  # bold
    0x1D434,  # italic
    0x1D468,  # bold italic
    0x1D5A0,  # sans-serif
    0x1D5D4,  # sans-serif bold
    0x1D608,  # sans-serif italic
    0x1D63C,  # sans-serif bold italic
    0x1D670,  # monospace
]


def _build_lower_pool(letter: str, cyrillic_greek: str) -> list:
    """Return all visually-similar alternatives for a lowercase Latin letter."""
    idx = ord(letter) - ord("a")
    pool = [cyrillic_greek]
    for base, exc in _MATH_LOWER_BASES:
        if exc and letter in exc:
            pool.append(exc[letter])
        else:
            c = chr(base + idx)
            if _unicodedata.name(c, ""):
                pool.append(c)
    # Fraktur
    if letter in _FRAKTUR_LOWER_EX:
        pool.append(_FRAKTUR_LOWER_EX[letter])
    else:
        c = chr(0x1D51E + idx)
        if _unicodedata.name(c, ""):
            pool.append(c)
    # Fullwidth
    pool.append(chr(0xFF41 + idx))
    return pool


def _build_upper_pool(letter: str, cyrillic_greek: str) -> list:
    """Return all visually-similar alternatives for an uppercase Latin letter."""
    idx = ord(letter) - ord("A")
    pool = [cyrillic_greek]
    for base in _MATH_UPPER_BASES:
        c = chr(base + idx)
        if _unicodedata.name(c, ""):
            pool.append(c)
    # Fraktur
    if letter in _FRAKTUR_UPPER_EX:
        pool.append(_FRAKTUR_UPPER_EX[letter])
    else:
        c = chr(0x1D504 + idx)
        if _unicodedata.name(c, ""):
            pool.append(c)
    # Fullwidth
    pool.append(chr(0xFF21 + idx))
    return pool


HOMOGLYPH_POOLS: dict = {
    lc: _build_lower_pool(lc, cg)
    for lc, cg in HOMOGLYPHS.items()
}

HOMOGLYPH_POOLS_UPPER: dict = {
    uc: _build_upper_pool(uc, cg)
    for uc, cg in HOMOGLYPHS_UPPER.items()
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


def _perturb_line_with_base_zw(
    line: str,
    perturb_fn,
    density: float,
    zw_density: float,
) -> str:
    """Apply zero-width base layer + strategy in a single left-to-right pass.

    For each alphabetic character:
      1. Possibly insert a zero-width char (base layer, probability=zw_density).
      2. Apply the strategy transformation (homoglyph swap or combining marks).
    Protected leading markdown markers are preserved unchanged.
    """
    m = _LEADING_MARKER_RE.match(line)
    marker = m.group(0) if m else ""
    rest = line[m.end():] if m else line

    # Single left-to-right pass over the prose text
    out = []
    for ch in rest:
        # Base-layer zero-width insertion
        if ch.isalpha() and random.random() < zw_density:
            out.append(random.choice(ZERO_WIDTH_CHARS))
        # Strategy transformation: for homoglyph the char itself changes;
        # for combining we append marks after; fall back to identity.
        transformed = perturb_fn(ch, density=density)
        out.append(transformed)

    return marker + "".join(out)


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


def _zero_width_char(ch: str, density: float) -> str:
    """Per-character version: return ch, possibly followed by a zero-width char."""
    result = ch
    if ch.isalpha() and random.random() < density:
        result += random.choice(ZERO_WIDTH_CHARS)
    return result


def insert_homoglyphs(text: str, density: float = 0.3) -> str:
    """Replace eligible Latin letters with visually-identical lookalikes.

    Picks uniformly at random from HOMOGLYPH_POOLS / HOMOGLYPH_POOLS_UPPER
    so repeated letters in the same document show varied lookalikes across
    the Cyrillic/Greek, Mathematical Alphanumeric, and Fullwidth pools.
    """
    out = []
    for ch in text:
        if ch.isupper() and ch in HOMOGLYPH_POOLS_UPPER and random.random() < density:
            out.append(random.choice(HOMOGLYPH_POOLS_UPPER[ch]))
        elif ch.islower() and ch in HOMOGLYPH_POOLS and random.random() < density:
            out.append(random.choice(HOMOGLYPH_POOLS[ch]))
        else:
            out.append(ch)
    return "".join(out)


def _homoglyph_char(ch: str, density: float) -> str:
    """Per-character version: return homoglyph replacement or original char."""
    if ch.isupper() and ch in HOMOGLYPH_POOLS_UPPER and random.random() < density:
        return random.choice(HOMOGLYPH_POOLS_UPPER[ch])
    if ch.islower() and ch in HOMOGLYPH_POOLS and random.random() < density:
        return random.choice(HOMOGLYPH_POOLS[ch])
    return ch


def insert_combining_marks(text: str, density: float = 0.3) -> str:
    """Append 1-2 combining diacritical marks after eligible alphabetic chars."""
    out = []
    for ch in text:
        out.append(ch)
        if ch.isalpha() and random.random() < density:
            n = random.randint(1, 2)
            out.extend(random.choice(COMBINING_MARKS) for _ in range(n))
    return "".join(out)


def _combining_char(ch: str, density: float) -> str:
    """Per-character version: return ch with possible combining marks appended."""
    result = ch
    if ch.isalpha() and random.random() < density:
        n = random.randint(1, 2)
        result += "".join(random.choice(COMBINING_MARKS) for _ in range(n))
    return result


# Per-character strategy dispatch (used by single-pass helpers)
_CHAR_FN = {
    "zero_width": _zero_width_char,
    "homoglyph": _homoglyph_char,
    "combining": _combining_char,
}

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
    zero_width_density: float = 0.15,
) -> str:
    """Apply zero_width -> homoglyph -> combining in a single left-to-right pass.

    The ``zero_width_density`` parameter controls the base-layer zero-width
    insertion probability.  It is distinct from the per-strategy densities
    derived from ``density``/``weights`` so callers can tune them independently.
    """
    density = max(0.0, min(1.0, density))
    zero_width_density = max(0.0, min(1.0, zero_width_density))
    strategy_weights = _normalize_combined_weights(density, weights)

    def _combined_perturb_line(line: str) -> str:
        m = _LEADING_MARKER_RE.match(line)
        marker = m.group(0) if m else ""
        rest = line[m.end():] if m else line

        # Use zero_width_density as the shared base-layer zero-width density.
        # strategy_weights["homoglyph"] and ["combining"] control their own layers.
        hg_d = strategy_weights["homoglyph"]
        cm_d = strategy_weights["combining"]

        out = []
        for ch in rest:
            # Single left-to-right pass: base zero-width -> homoglyph -> combining
            if ch.isalpha() and random.random() < zero_width_density:
                out.append(random.choice(ZERO_WIDTH_CHARS))
            ch = _homoglyph_char(ch, hg_d)
            out.append(ch)
            if ch.isalpha() and random.random() < cm_d:
                n = random.randint(1, 2)
                out.extend(random.choice(COMBINING_MARKS) for _ in range(n))
        return marker + "".join(out)

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
    zero_width_density: float = 0.15,
) -> str:
    """Perturb only the prose portions of a Markdown document.

    Code fences, inline code, links/images, autolinks, raw HTML, and
    leading line markers (#, >, -, 1.) are left completely untouched.

    Zero-width character insertion is always applied as a base layer for
    every strategy (controlled by ``zero_width_density``, default 0.15).

    **Special case — ``strategy="zero_width"``**: the base-layer zero-width
    insertion is suppressed to avoid double-insertion.  The main ``density``
    parameter exclusively controls zero-width intensity for this strategy;
    ``zero_width_density`` is ignored when ``strategy="zero_width"``.

    Args:
        text:               The Markdown source to protect.
        strategy:           One of "zero_width", "homoglyph", "combining",
                            "combined".
        density:            Fraction of eligible characters to perturb by the
                            *selected* strategy (0.0–1.0).
        zero_width_density: Fraction of eligible characters that receive the
                            always-on base-layer zero-width insertion (0.0–1.0).
                            Ignored when ``strategy="zero_width"`` to avoid
                            double-insertion.  Default 0.15.

    Returns:
        The protected Markdown string.
    """
    if strategy not in STRATEGIES:
        raise ValueError(
            f"Unknown strategy {strategy!r}. Choose from {list(STRATEGIES)}"
        )
    density = max(0.0, min(1.0, density))
    zero_width_density = max(0.0, min(1.0, zero_width_density))

    if strategy == "combined":
        return protect_markdown_combined(
            text,
            density=density,
            weights=weights,
            watermark=watermark,
            zero_width_density=zero_width_density,
        )

    if strategy == "zero_width":
        # For zero_width strategy, only the main density drives insertion.
        # The base layer is suppressed to avoid double-application.
        perturb_fn = CHAR_STRATEGIES["zero_width"]
        spans = _split_protected_spans(text)
        parts = []
        for is_protected, chunk in spans:
            if is_protected:
                parts.append(chunk)
            else:
                lines = chunk.split("\n")
                parts.append(
                    "\n".join(
                        _perturb_line(line, perturb_fn, density) for line in lines
                    )
                )
        protected = "".join(parts)
        if watermark is not None:
            protected = _append_watermark_comment(protected, watermark)
        return protected

    # For homoglyph/combining: single left-to-right pass applying both
    # the base-layer zero-width insertion and the selected strategy.
    char_fn = _CHAR_FN[strategy]

    spans = _split_protected_spans(text)
    parts = []
    for is_protected, chunk in spans:
        if is_protected:
            parts.append(chunk)
        else:
            lines = chunk.split("\n")
            parts.append(
                "\n".join(
                    _perturb_line_with_base_zw(
                        line, char_fn, density, zero_width_density
                    )
                    for line in lines
                )
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
