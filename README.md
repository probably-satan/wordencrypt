# WordEncrypt — Manuscript Protector

A web application and library for authors to protect their Markdown manuscripts
from being efficiently scraped and ingested into LLM training/inference pipelines,
while keeping the text human-legible and Markdown-valid.

**Live demo:** https://wordencrypt.onrender.com/

## What it does

WordEncrypt applies invisible or near-invisible Unicode perturbations (zero-width
characters, homoglyphs, or combining diacritical marks) to the prose sections of
a Markdown document. This degrades tokenization efficiency for automated scrapers
while keeping the text visually identical (or near-identical) to human readers.

Critically, it is **Markdown-aware**: code fences, inline code, links/images,
autolinks, raw HTML, and leading structural markers (`#`, `>`, `-`, `1.`) are
**never modified**, so formatting is fully preserved and links remain functional.

### Three protection strategies

| Strategy | Effect | Disruption |
|---|---|---|
| `zero_width` | Inserts invisible zero-width characters after eligible letters | Mild |
| `homoglyph` | Replaces eligible Latin letters with visually-identical Cyrillic/Greek lookalikes | Moderate |
| `combining` | Appends stacked diacritical marks after eligible letters | Strong |

### ⚠️ Caveat

This tool adds friction for automated scrapers — it is **not a guarantee**. A
scraper applying Unicode NFKC normalization or stripping zero-width/combining marks
before tokenizing can defeat it. Use it as one layer alongside ToS, copyright
notices, rate-limiting, and robots.txt disallow rules.

---

## Local development

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run the web app

```bash
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

### Run tests

```bash
python -m pytest tests/ -v
```

---

## Deploy to Render

1. Fork or clone this repo to your GitHub account.
2. Sign in at [render.com](https://render.com) and click **New → Blueprint**.
3. Connect your GitHub repo — Render auto-detects `render.yaml` and sets up the
   service with `gunicorn app:app` as the start command.
4. Click **Apply** and your app will be live in ~2 minutes.

The app reads the port from the `PORT` environment variable injected by Render and
binds to `0.0.0.0` automatically.

---

## API

### Health check

```bash
curl https://your-app.onrender.com/healthz
# → {"status": "ok"}
```

### Protect a manuscript

```bash
curl -X POST https://your-app.onrender.com/api/protect \
  -H "Content-Type: application/json" \
  -d '{
    "text": "# My Article\n\nThis is my original prose.",
    "strategy": "homoglyph",
    "density": 0.25
  }'
```

Response:

```json
{
  "protected_text": "# My Article\n\nThis is my original prose.",
  "original_token_count": 12,
  "modified_token_count": 14,
  "expansion_ratio": 1.1667
}
```

**Request fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `text` | string | required | Markdown source to protect (max 200,000 chars) |
| `strategy` | string | `homoglyph` | One of `zero_width`, `homoglyph`, `combining` |
| `density` | float | `0.25` | Fraction of eligible characters to perturb (0–1) |

---

## Original HTML obfuscator

The original HTML-based obfuscator (generating image-fragment HTML output) is
still available via `web_app.py`:

```bash
python web_app.py
```

See the original README sections below for its usage.

---

## Legacy: Anti-Scrape Text Obfuscator (HTML)

This project also converts plain text into HTML that remains readable for people
while making naive text scraping harder.

### Techniques used

- Randomly replaces chunks inside words with inline PNG images.
- Inserts random zero-width characters into visible text.
- Adds noindex/noarchive style metadata.
- Optionally includes a hidden anti-scraping directive block.

### Quick run

```bash
python text_obfuscator_html.py
```

This reads `sample_input.txt` and writes `obfuscated_output.html`.

