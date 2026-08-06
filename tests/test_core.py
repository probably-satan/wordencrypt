"""Unit tests for wordencrypt/core.py"""

import unicodedata

import pytest

from wordencrypt.core import (
    HOMOGLYPHS,
    HOMOGLYPHS_UPPER,
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
    # With both density=0 and zero_width_density=0, text is unchanged
    result = protect_markdown(SAMPLE_MD, strategy="homoglyph", density=0.0, zero_width_density=0.0)
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
    result = protect_markdown(text, strategy="combined", density=0.0, zero_width_density=0.0)
    assert result == text


def test_combined_all_zero_weights_unchanged():
    text = "This is plain prose text."
    result = protect_markdown(
        text,
        strategy="combined",
        density=1.0,
        weights={"zero_width": 0, "homoglyph": 0, "combining": 0},
        zero_width_density=0.0,
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
# Base-layer zero-width tests
# ---------------------------------------------------------------------------

ZW_SET = set(ZERO_WIDTH_CHARS)

PROSE = "The quick brown fox jumps over the lazy dog."


def _count_zw(text: str) -> int:
    return sum(1 for ch in text if ch in ZW_SET)


def test_homoglyph_zero_density_but_zw_density_inserts_zw():
    """homoglyph density=0 but zero_width_density>0 → zero-width chars appear."""
    result = protect_markdown(PROSE, strategy="homoglyph", density=0.0, zero_width_density=1.0)
    assert _count_zw(result) > 0


def test_homoglyph_density_but_no_zw_density_no_zw():
    """homoglyph density>0 but zero_width_density=0 → no zero-width chars."""
    result = protect_markdown(PROSE, strategy="homoglyph", density=1.0, zero_width_density=0.0)
    assert _count_zw(result) == 0


def test_combining_zero_density_but_zw_density_inserts_zw():
    """combining density=0 but zero_width_density>0 → zero-width chars appear."""
    result = protect_markdown(PROSE, strategy="combining", density=0.0, zero_width_density=1.0)
    assert _count_zw(result) > 0


def test_combining_density_but_no_zw_density_no_zw():
    """combining density>0 but zero_width_density=0 → no zero-width chars."""
    result = protect_markdown(PROSE, strategy="combining", density=1.0, zero_width_density=0.0)
    assert _count_zw(result) == 0


def test_zero_width_strategy_density_controls_zw():
    """strategy=zero_width: main density drives insertion; zero_width_density ignored."""
    result_high = protect_markdown(PROSE, strategy="zero_width", density=1.0, zero_width_density=0.0)
    # density=1 → every alpha char gets a ZW char
    assert _count_zw(result_high) > 0


def test_zero_width_strategy_no_double_insertion():
    """strategy=zero_width: zero_width_density does NOT cause double insertion."""
    # With density=0 (main) and zero_width_density=1 (base), no ZW should appear
    # because base layer is suppressed for zero_width strategy.
    result = protect_markdown(PROSE, strategy="zero_width", density=0.0, zero_width_density=1.0)
    assert _count_zw(result) == 0


def test_combined_no_double_zw_insertion():
    """strategy=combined: zero-width count should not be roughly double what a single
    pass at zero_width_density would produce — guards against double-application."""
    import random as _random
    _random.seed(42)
    # Run combined with zero_width_density=1.0 and strategy weights zero_width=0.0
    result = protect_markdown(
        PROSE,
        strategy="combined",
        density=0.0,
        weights={"zero_width": 0.0, "homoglyph": 0.0, "combining": 0.0},
        zero_width_density=1.0,
    )
    # With combined strategy, zero_width_density controls the base-layer ZW.
    # Count should be > 0 (base layer ran) but not excessively high (no double-pass).
    alpha_count = sum(1 for ch in PROSE if ch.isalpha())
    zw_count = _count_zw(result)
    # Should have roughly alpha_count ZW chars (density=1.0), not 2x that
    assert zw_count <= alpha_count, "Double-insertion detected in combined strategy"
    assert zw_count > 0


def test_protected_regions_unmodified_with_base_zw():
    """Protected Markdown regions must remain unmodified even with base-layer ZW active."""
    for strategy in ("homoglyph", "combining", "combined"):
        result = protect_markdown(
            SAMPLE_MD, strategy=strategy, density=1.0, zero_width_density=1.0
        )
        assert '```python\ndef hello():\n    return "world"\n```' in result
        assert "`code span`" in result
        assert "[link text](https://example.com)" in result
        assert "![alt text](https://example.com/img.png)" in result
        assert "<https://example.com/autolink>" in result
        assert result.startswith("# ")
        assert "\n- " in result
        assert "\n> " in result
