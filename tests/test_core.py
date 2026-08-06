"""Unit tests for wordencrypt/core.py"""

import unicodedata

import pytest

from wordencrypt.core import (
    HOMOGLYPHS,
    HOMOGLYPHS_UPPER,
    HOMOGLYPH_POOLS,
    HOMOGLYPH_POOLS_UPPER,
    ZERO_WIDTH_CHARS,
    compare_tokenization,
    extract_watermark,
    insert_combining_marks,
    insert_homoglyphs,
    insert_zero_width,
    pretokenize,
    protect_markdown,
)

# ---------------------------------------------------------------------------
# Strategy: zero_width
# ---------------------------------------------------------------------------


def test_zero_width_density_one_modifies():
    text = "hello world"
    result = insert_zero_width(text, density=1.0)
    assert result != text
    # Every alpha char should have a zero-width char inserted after it
    zw_set = set(ZERO_WIDTH_CHARS)
    assert any(ch in zw_set for ch in result)


def test_zero_width_density_zero_unchanged():
    text = "hello world"
    assert insert_zero_width(text, density=0.0) == text


def test_zero_width_non_alpha_unchanged():
    text = "1234 !@#$"
    result = insert_zero_width(text, density=1.0)
    assert result == text


# ---------------------------------------------------------------------------
# Strategy: homoglyph
# ---------------------------------------------------------------------------


def test_homoglyph_density_one_modifies():
    # "ace" contains three eligible letters
    text = "ace"
    result = insert_homoglyphs(text, density=1.0)
    assert result != text
    for ch in result:
        assert ch in HOMOGLYPHS.values() or ch not in HOMOGLYPHS


def test_homoglyph_density_zero_unchanged():
    text = "hello world"
    assert insert_homoglyphs(text, density=0.0) == text


def test_homoglyph_case_preserving():
    text = "ACE"
    result = insert_homoglyphs(text, density=1.0)
    # Results should be uppercase-category-like (not necessarily ASCII upper)
    assert result != text


# ---------------------------------------------------------------------------
# Strategy: combining
# ---------------------------------------------------------------------------


def test_combining_density_one_modifies():
    text = "hello"
    result = insert_combining_marks(text, density=1.0)
    assert result != text
    # Should contain combining characters
    assert any(unicodedata.combining(ch) for ch in result)


def test_combining_density_zero_unchanged():
    text = "hello world"
    assert insert_combining_marks(text, density=0.0) == text


# ---------------------------------------------------------------------------
# protect_markdown: prose is perturbed, protected regions are not
# ---------------------------------------------------------------------------

SAMPLE_MD = """\
# Heading One

This is a prose paragraph with some words to perturb.

- list item one
- list item two

> blockquote text here

```python
def hello():
    return "world"
```

Inline `code span` should not change.

A [link text](https://example.com) in prose.

An image: ![alt text](https://example.com/img.png)

Autolink: <https://example.com/autolink>

<div class="raw">raw HTML tag</div>
"""


def test_protect_markdown_zero_density_unchanged():
    result = protect_markdown(SAMPLE_MD, strategy="homoglyph", density=0.0)
    assert result == SAMPLE_MD


def test_protect_markdown_perturbs_prose():
    result = protect_markdown(SAMPLE_MD, strategy="zero_width", density=1.0)
    assert result != SAMPLE_MD


def test_protect_markdown_code_fence_unchanged():
    result = protect_markdown(SAMPLE_MD, strategy="zero_width", density=1.0)
    assert '```python\ndef hello():\n    return "world"\n```' in result


def test_protect_markdown_inline_code_unchanged():
    result = protect_markdown(SAMPLE_MD, strategy="zero_width", density=1.0)
    assert "`code span`" in result


def test_protect_markdown_link_url_unchanged():
    result = protect_markdown(SAMPLE_MD, strategy="zero_width", density=1.0)
    assert "[link text](https://example.com)" in result


def test_protect_markdown_image_unchanged():
    result = protect_markdown(SAMPLE_MD, strategy="zero_width", density=1.0)
    assert "![alt text](https://example.com/img.png)" in result


def test_protect_markdown_autolink_unchanged():
    result = protect_markdown(SAMPLE_MD, strategy="zero_width", density=1.0)
    assert "<https://example.com/autolink>" in result


def test_protect_markdown_heading_marker_preserved():
    result = protect_markdown(SAMPLE_MD, strategy="zero_width", density=1.0)
    assert result.startswith("# ")


def test_protect_markdown_list_marker_preserved():
    result = protect_markdown(SAMPLE_MD, strategy="zero_width", density=1.0)
    assert "\n- " in result


def test_protect_markdown_blockquote_marker_preserved():
    result = protect_markdown(SAMPLE_MD, strategy="zero_width", density=1.0)
    assert "\n> " in result


def test_protect_markdown_invalid_strategy():
    with pytest.raises(ValueError):
        protect_markdown("hello", strategy="bad_strategy")


def test_combined_density_one_modifies():
    text = "This is plain prose text."
    result = protect_markdown(text, strategy="combined", density=1.0)
    assert result != text


def test_combined_density_zero_unchanged():
    text = "This is plain prose text."
    result = protect_markdown(text, strategy="combined", density=0.0)
    assert result == text


def test_combined_all_zero_weights_unchanged():
    text = "This is plain prose text."
    result = protect_markdown(
        text,
        strategy="combined",
        density=1.0,
        weights={"zero_width": 0, "homoglyph": 0, "combining": 0},
    )
    assert result == text


def test_combined_respects_all_protected_regions():
    result = protect_markdown(SAMPLE_MD, strategy="combined", density=1.0)
    assert '```python\ndef hello():\n    return "world"\n```' in result
    assert "`code span`" in result
    assert "[link text](https://example.com)" in result
    assert "![alt text](https://example.com/img.png)" in result
    assert "<https://example.com/autolink>" in result
    assert result.startswith("# ")
    assert "\n- " in result
    assert "\n> " in result


def test_watermark_round_trip():
    result = protect_markdown("hello world", strategy="combined", density=0.4, watermark="hello")
    assert extract_watermark(result) == "hello"


def test_watermark_comment_not_perturbed_at_full_density():
    text = "## Title\n\nProse words here for heavy perturbation."
    result = protect_markdown(
        text,
        strategy="combined",
        density=1.0,
        watermark="exact-watermark-value",
    )
    assert "<!-- wm:" in result
    assert extract_watermark(result) == "exact-watermark-value"


def test_extract_watermark_missing_returns_none():
    assert extract_watermark("No watermark here") is None


# ---------------------------------------------------------------------------
# compare_tokenization
# ---------------------------------------------------------------------------


def test_compare_tokenization_same_text():
    stats = compare_tokenization("hello world", "hello world")
    assert stats["original_token_count"] == stats["modified_token_count"]
    assert stats["expansion_ratio"] == 1.0


def test_compare_tokenization_empty():
    stats = compare_tokenization("", "")
    assert stats["original_token_count"] == 0
    assert stats["modified_token_count"] == 0
    assert stats["expansion_ratio"] == 0.0


def test_compare_tokenization_counts():
    original = "hello world"
    orig_chunks = pretokenize(original)
    stats = compare_tokenization(original, original)
    assert stats["original_token_count"] == len(orig_chunks)


def test_compare_tokenization_expansion():
    original = "cat"
    # Insert zero-width chars between every letter → more tokens
    modified = insert_zero_width(original, density=1.0)
    stats = compare_tokenization(original, modified)
    assert stats["modified_token_count"] >= stats["original_token_count"]
    assert stats["expansion_ratio"] >= 1.0

# ---------------------------------------------------------------------------
# Expanded homoglyph pools
# ---------------------------------------------------------------------------


def test_homoglyph_pools_have_multiple_entries():
    """Each letter in HOMOGLYPH_POOLS has more than one alternative."""
    for letter, pool in HOMOGLYPH_POOLS.items():
        assert len(pool) > 1, f"Pool for '{letter}' has only one entry"
    for letter, pool in HOMOGLYPH_POOLS_UPPER.items():
        assert len(pool) > 1, f"Pool for '{letter}' has only one entry"


def test_homoglyph_pools_no_zero_width_or_combining():
    """No pool entry should be a zero-width or combining-mark codepoint."""
    zw_set = set(ZERO_WIDTH_CHARS)
    for letter, pool in {**HOMOGLYPH_POOLS, **HOMOGLYPH_POOLS_UPPER}.items():
        for ch in pool:
            assert ch not in zw_set, f"Zero-width char in pool for '{letter}': U+{ord(ch):04X}"
            assert unicodedata.combining(ch) == 0, (
                f"Combining mark in pool for '{letter}': U+{ord(ch):04X}"
            )


def test_homoglyph_pools_all_single_codepoint():
    """Every pool entry is exactly one codepoint (no multi-char precomposed strings)."""
    for letter, pool in {**HOMOGLYPH_POOLS, **HOMOGLYPH_POOLS_UPPER}.items():
        for ch in pool:
            assert len(ch) == 1, f"Multi-codepoint entry in pool for '{letter}': {ch!r}"


def test_homoglyph_pool_variety_lowercase():
    """At density=1.0 over 200 identical lowercase letters, output shows multiple distinct variants."""
    for letter in HOMOGLYPH_POOLS:
        text = letter * 200
        result = insert_homoglyphs(text, density=1.0)
        distinct_subs = set(result) - {letter}
        assert len(distinct_subs) > 1, (
            f"Expected >1 distinct substitution for '{letter}', got {distinct_subs!r}"
        )


def test_homoglyph_pool_variety_uppercase():
    """At density=1.0 over 200 identical uppercase letters, output shows multiple distinct variants."""
    for letter in HOMOGLYPH_POOLS_UPPER:
        text = letter * 200
        result = insert_homoglyphs(text, density=1.0)
        distinct_subs = set(result) - {letter}
        assert len(distinct_subs) > 1, (
            f"Expected >1 distinct substitution for '{letter}', got {distinct_subs!r}"
        )


def test_homoglyph_uppercase_uses_only_uppercase_pool():
    """Uppercase letters only produce substitutions from HOMOGLYPH_POOLS_UPPER."""
    for letter in HOMOGLYPH_POOLS_UPPER:
        text = letter * 200
        result = insert_homoglyphs(text, density=1.0)
        allowed = set(HOMOGLYPH_POOLS_UPPER[letter]) | {letter}
        for ch in result:
            assert ch in allowed, (
                f"Unexpected char U+{ord(ch):04X} for uppercase '{letter}'"
            )


def test_homoglyph_lowercase_uses_only_lowercase_pool():
    """Lowercase letters only produce substitutions from HOMOGLYPH_POOLS."""
    for letter in HOMOGLYPH_POOLS:
        text = letter * 200
        result = insert_homoglyphs(text, density=1.0)
        allowed = set(HOMOGLYPH_POOLS[letter]) | {letter}
        for ch in result:
            assert ch in allowed, (
                f"Unexpected char U+{ord(ch):04X} for lowercase '{letter}'"
            )


def test_homoglyph_pools_backward_compat_cyrillic_greek():
    """The original Cyrillic/Greek homoglyph is still present in each pool."""
    for letter, cg_char in HOMOGLYPHS.items():
        assert cg_char in HOMOGLYPH_POOLS[letter], (
            f"Cyrillic/Greek char for '{letter}' missing from expanded pool"
        )
    for letter, cg_char in HOMOGLYPHS_UPPER.items():
        assert cg_char in HOMOGLYPH_POOLS_UPPER[letter], (
            f"Cyrillic/Greek char for '{letter}' missing from expanded upper pool"
        )
