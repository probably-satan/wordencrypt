"""
app.py — Manuscript Protection Web App

A simple Flask app wrapping wordencrypt/core.py so authors can protect
their Markdown manuscripts before publishing online.

Routes:
  GET  /              — single-page UI
  POST /api/protect   — JSON API endpoint
  GET  /healthz       — health check for hosting platforms
"""

import os

from flask import Flask, jsonify, render_template, request

from wordencrypt.core import STRATEGIES, compare_tokenization, protect_markdown

app = Flask(__name__, template_folder="templates")

MAX_INPUT_SIZE = 200_000  # characters


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------


@app.post("/api/protect")
def api_protect():
    data = request.get_json(silent=True) or {}

    text = data.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "text is required and must be a non-empty string"}), 400

    if len(text) > MAX_INPUT_SIZE:
        return (
            jsonify(
                {
                    "error": (
                        f"Input too large: {len(text)} characters "
                        f"(max {MAX_INPUT_SIZE})"
                    )
                }
            ),
            413,
        )

    strategy = data.get("strategy", "homoglyph")
    if strategy not in STRATEGIES:
        return (
            jsonify(
                {
                    "error": (
                        f"Invalid strategy {strategy!r}. "
                        f"Choose from {list(STRATEGIES)}"
                    )
                }
            ),
            400,
        )

    try:
        density = float(data.get("density", 0.25))
    except (TypeError, ValueError):
        return jsonify({"error": "density must be a number between 0 and 1"}), 400
    density = max(0.0, min(1.0, density))
    watermark = data.get("watermark")
    if watermark is not None and not isinstance(watermark, str):
        return jsonify({"error": "watermark must be a string when provided"}), 400

    protected = protect_markdown(
        text,
        strategy=strategy,
        density=density,
        watermark=watermark,
    )
    stats = compare_tokenization(text, protected)

    return (
        jsonify(
            {
                "protected_text": protected,
                "original_token_count": stats["original_token_count"],
                "modified_token_count": stats["modified_token_count"],
                "expansion_ratio": stats["expansion_ratio"],
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# Single-page UI
# ---------------------------------------------------------------------------


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None
    form_values = {
        "text": "",
        "strategy": "homoglyph",
        "density": "0.25",
        "watermark": "",
    }

    if request.method == "POST":
        # Handle file upload or pasted text
        uploaded = request.files.get("md_file")
        if uploaded and uploaded.filename:
            try:
                text = uploaded.read().decode("utf-8")
            except UnicodeDecodeError:
                error = "Could not decode the uploaded file as UTF-8."
                text = ""
        else:
            text = request.form.get("text", "")

        strategy = request.form.get("strategy", "homoglyph")
        density_raw = request.form.get("density", "0.25")
        watermark = request.form.get("watermark", "")

        form_values["text"] = text
        form_values["strategy"] = strategy
        form_values["density"] = density_raw
        form_values["watermark"] = watermark

        if not error:
            if not text.strip():
                error = "Please paste some Markdown text or upload a .md file."
            elif len(text) > MAX_INPUT_SIZE:
                error = (
                    f"Input is too large ({len(text):,} characters). "
                    f"Maximum is {MAX_INPUT_SIZE:,} characters."
                )
            elif strategy not in STRATEGIES:
                error = (
                    f"Invalid strategy {strategy!r}. "
                    f"Choose from {list(STRATEGIES)}."
                )
            else:
                try:
                    density = float(density_raw)
                except (TypeError, ValueError):
                    density = 0.25
                density = max(0.0, min(1.0, density))

                protected = protect_markdown(
                    text,
                    strategy=strategy,
                    density=density,
                    watermark=watermark or None,
                )
                stats = compare_tokenization(text, protected)
                result = {
                    "protected_text": protected,
                    "original_token_count": stats["original_token_count"],
                    "modified_token_count": stats["modified_token_count"],
                    "expansion_ratio": stats["expansion_ratio"],
                }

    return render_template(
        "manuscript.html",
        form_values=form_values,
        strategies=list(STRATEGIES.keys()),
        result=result,
        error=error,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
