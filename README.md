# Anti-Scrape Text Obfuscator (HTML)

Try it here: https://anti-scrape-text-obfuscator.onrender.com/

This project converts plain text into HTML that remains readable for people while making naive text scraping harder.

## Techniques used

- Randomly replaces chunks inside words with inline PNG images.
- Inserts random zero-width characters into visible text.
- Adds noindex/noarchive style metadata.
- Optionally includes a hidden anti-scraping directive block.

## Setup

```bash
pip install -r requirements.txt
```

## Quick run

```bash
python text_obfuscator_html.py
```

This reads `sample_input.txt` and writes `obfuscated_output.html`.

## Use your own file

```bash
python text_obfuscator_html.py --input your_input.txt --output protected.html --title "Protected Text"
```

## Useful options

- `--seed 42` for deterministic output.
- `--image-prob 0.35` controls how often chunks become images.
- `--zero-width-prob 0.22` controls zero-width insertion rate.
- `--enable-confusables` enables low-rate Cyrillic/Unicode lookalike substitutions.
- `--confusable-prob 0.05` controls confusable substitution rate.
- `--enable-image-protection` enables image hardening on base64 syllable PNGs.
- `--disable-protection-ensemble` disables random ensemble stacking and applies all layers deterministically.
- `--noise-strength 0.08` controls random pixel noise.
- `--gradient-strength 0.07` controls gradient perturbation.
- `--frequency-strength 0.06` controls sinusoidal frequency perturbation.
- `--texture-strength 0.07` controls texture overlays.
- `--no-hidden-directive` disables the hidden directive block.

## Reddit / plain-text mode

To generate obfuscated text safe for Reddit messages, posts, and DMs (no HTML or image fragments — only zero-width characters and Unicode lookalikes):

```bash
python text_obfuscator_html.py --reddit --input your_input.txt --output reddit_obfuscated.txt
```

When `--output` is not changed from the default, the file is written to `reddit_obfuscated.txt`.

The `--reddit` flag can be combined with `--enable-confusables`, `--confusable-prob`, `--zero-width-prob`, and `--seed`. Image-related options are ignored in Reddit mode.

In the web app, click **Generate Reddit Text** below the main form to fetch Reddit-safe output. The result can be copied or downloaded from the Reddit Output panel that appears in the output column.



Run the local web app:

```bash
python web_app.py
```

Then open:

```text
http://127.0.0.1:5000
```

In the UI, users can:

- Paste input text.
- Set display typography (for example `12pt` and a font family).
- Optionally enable Cyrillic/Unicode lookalike substitutions.
- Optionally enable image protection layers (ensemble, frequency, gradient, texture, noise).
- Generate obfuscated HTML output.
- Copy or download the generated HTML file.
