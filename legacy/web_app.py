import os
from html import escape
from flask import Flask, Response, render_template, request

from text_obfuscator_html import (
    ObfuscationConfig,
    build_html_document,
    build_reddit_text,
    css_color_to_rgba,
    guess_font_path_from_family,
    parse_css_size_to_px,
)


app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
)


PROTECTION_PRESETS = {
    "readable": {
        "noise_strength": 0.04,
        "gradient_strength": 0.03,
        "frequency_strength": 0.03,
        "texture_strength": 0.03,
        "protection_ensemble": False,
    },
    "balanced": {
        "noise_strength": 0.08,
        "gradient_strength": 0.07,
        "frequency_strength": 0.06,
        "texture_strength": 0.07,
        "protection_ensemble": True,
    },
    "aggressive": {
        "noise_strength": 0.16,
        "gradient_strength": 0.13,
        "frequency_strength": 0.12,
        "texture_strength": 0.14,
        "protection_ensemble": True,
    },
}


def parse_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int(value: str, default: int):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_config_from_form(form_data) -> ObfuscationConfig:
    size_css = (form_data.get("font_size") or "12pt").strip()
    family_css = (form_data.get("font_family") or "Arial, Helvetica, sans-serif").strip()
    color_css = (form_data.get("text_color") or "#141414").strip()

    image_prob = parse_float(form_data.get("image_prob"), 0.35)
    zero_prob = parse_float(form_data.get("zero_prob"), 0.22)
    confusable_prob = parse_float(form_data.get("confusable_prob"), 0.05)
    protection_preset = (form_data.get("protection_preset") or "balanced").strip().lower()
    noise_strength = parse_float(form_data.get("noise_strength"), 0.08)
    gradient_strength = parse_float(form_data.get("gradient_strength"), 0.07)
    frequency_strength = parse_float(form_data.get("frequency_strength"), 0.06)
    texture_strength = parse_float(form_data.get("texture_strength"), 0.07)
    baseline_em = parse_float(form_data.get("baseline_em"), -0.26)
    image_height_em = parse_float(form_data.get("image_height_em"), 1.18)
    seed_value = parse_int(form_data.get("seed"), 42)

    font_px = parse_css_size_to_px(size_css, 18)
    font_path = guess_font_path_from_family(family_css)

    protection_ensemble = form_data.get("protection_ensemble") == "on"

    if protection_preset in PROTECTION_PRESETS:
        preset = PROTECTION_PRESETS[protection_preset]
        noise_strength = preset["noise_strength"]
        gradient_strength = preset["gradient_strength"]
        frequency_strength = preset["frequency_strength"]
        texture_strength = preset["texture_strength"]
        protection_ensemble = preset["protection_ensemble"]

    cfg = ObfuscationConfig(
        image_fragment_probability=max(0.0, min(1.0, image_prob)),
        zero_width_probability=max(0.0, min(1.0, zero_prob)),
        enable_confusables=form_data.get("enable_confusables") == "on",
        confusable_probability=max(0.0, min(1.0, confusable_prob)),
        enable_image_protection=form_data.get("enable_image_protection") == "on",
        protection_ensemble=protection_ensemble,
        protection_noise_strength=max(0.0, min(0.35, noise_strength)),
        protection_gradient_strength=max(0.0, min(0.25, gradient_strength)),
        protection_frequency_strength=max(0.0, min(0.22, frequency_strength)),
        protection_texture_strength=max(0.0, min(0.25, texture_strength)),
        seed=seed_value,
        include_hidden_directive=form_data.get("include_hidden") == "on",
        font_size=font_px,
        font_path=font_path,
        css_font_size=size_css,
        css_font_family=family_css,
        css_text_color=color_css,
        image_vertical_align_em=max(-0.6, min(0.4, baseline_em)),
        image_height_em=max(0.6, min(1.6, image_height_em)),
    )

    cfg.text_color = css_color_to_rgba(color_css, cfg.text_color)
    return cfg


@app.route("/", methods=["GET", "POST"])
def index():
    defaults = {
        "title": "Protected Text",
        "font_size": "12pt",
        "font_family": "Arial, Helvetica, sans-serif",
        "text_color": "#141414",
        "image_prob": "0.35",
        "zero_prob": "0.22",
        "confusable_prob": "0.05",
        "enable_confusables": False,
        "enable_image_protection": False,
        "protection_preset": "balanced",
        "protection_ensemble": True,
        "noise_strength": "0.08",
        "gradient_strength": "0.07",
        "frequency_strength": "0.06",
        "texture_strength": "0.07",
        "baseline_em": "-0.26",
        "image_height_em": "1.18",
        "seed": "42",
        "include_hidden": True,
    }

    result_html = None
    debug_info = None

    if request.method == "POST":
        form_values = {
            "title": request.form.get("title", defaults["title"]),
            "font_size": request.form.get("font_size", defaults["font_size"]),
            "font_family": request.form.get("font_family", defaults["font_family"]),
            "text_color": request.form.get("text_color", defaults["text_color"]),
            "image_prob": request.form.get("image_prob", defaults["image_prob"]),
            "zero_prob": request.form.get("zero_prob", defaults["zero_prob"]),
            "confusable_prob": request.form.get("confusable_prob", defaults["confusable_prob"]),
            "enable_confusables": request.form.get("enable_confusables"),
            "enable_image_protection": request.form.get("enable_image_protection"),
            "protection_preset": request.form.get("protection_preset", defaults["protection_preset"]),
            "protection_ensemble": request.form.get("protection_ensemble"),
            "noise_strength": request.form.get("noise_strength", defaults["noise_strength"]),
            "gradient_strength": request.form.get("gradient_strength", defaults["gradient_strength"]),
            "frequency_strength": request.form.get("frequency_strength", defaults["frequency_strength"]),
            "texture_strength": request.form.get("texture_strength", defaults["texture_strength"]),
            "baseline_em": request.form.get("baseline_em", defaults["baseline_em"]),
            "image_height_em": request.form.get("image_height_em", defaults["image_height_em"]),
            "seed": request.form.get("seed", defaults["seed"]),
            "include_hidden": request.form.get("include_hidden"),
        }

        user_text = request.form.get("input_text", "")
        config = build_config_from_form(form_values)
        result_html = build_html_document(form_values["title"], user_text, config)

        debug_info = (
            f"Detected render size: {config.css_font_size} -> {config.font_size}px | "
            f"Font family: {config.css_font_family} | "
            f"Image baseline offset: {config.image_vertical_align_em}em | "
            f"Image height: {config.image_height_em}em | "
            f"Confusables: {'on' if config.enable_confusables else 'off'} @ {config.confusable_probability} | "
            f"Image protection: {'on' if config.enable_image_protection else 'off'} "
            f"({form_values['protection_preset']}, {'ensemble' if config.protection_ensemble else 'all'})"
        )

        defaults.update(form_values)
        defaults["enable_confusables"] = form_values["enable_confusables"] == "on"
        defaults["enable_image_protection"] = form_values["enable_image_protection"] == "on"
        defaults["protection_ensemble"] = config.protection_ensemble
        if form_values["protection_preset"] in PROTECTION_PRESETS:
            defaults["noise_strength"] = f"{config.protection_noise_strength:.2f}"
            defaults["gradient_strength"] = f"{config.protection_gradient_strength:.2f}"
            defaults["frequency_strength"] = f"{config.protection_frequency_strength:.2f}"
            defaults["texture_strength"] = f"{config.protection_texture_strength:.2f}"
        defaults["include_hidden"] = form_values["include_hidden"] == "on"
        defaults["input_text"] = user_text

    else:
        defaults["input_text"] = "Paste text here to generate obfuscated output."

    return render_template(
        "index.html",
        values=defaults,
        result_html=result_html,
        debug_info=debug_info,
    )


@app.post("/download")
def download_output():
    output_html = escape(request.form.get("output_html", ""))
    title = request.form.get("title", "protected_text").strip() or "protected_text"
    safe_title = "".join(ch for ch in title if ch.isalnum() or ch in ("-", "_"))
    if not safe_title:
        safe_title = "protected_text"

    filename = f"{safe_title}.html"
    return Response(
        output_html,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/reddit")
def reddit_output():
    user_text = request.form.get("input_text", "")
    form_values = {
        "zero_prob": request.form.get("zero_prob", "0.22"),
        "confusable_prob": request.form.get("confusable_prob", "0.05"),
        "enable_confusables": request.form.get("enable_confusables"),
        "seed": request.form.get("seed", "42"),
        # Unused by reddit mode but required by build_config_from_form
        "font_size": "12pt",
        "font_family": "Arial, Helvetica, sans-serif",
        "text_color": "#141414",
        "image_prob": "0.35",
        "protection_preset": "balanced",
        "protection_ensemble": None,
        "noise_strength": "0.08",
        "gradient_strength": "0.07",
        "frequency_strength": "0.06",
        "texture_strength": "0.07",
        "baseline_em": "-0.26",
        "image_height_em": "1.18",
        "enable_image_protection": None,
        "include_hidden": None,
    }
    config = build_config_from_form(form_values)
    result = build_reddit_text(user_text, config)
    return Response(result, mimetype="text/plain; charset=utf-8")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
