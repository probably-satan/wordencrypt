"""Integration tests for the Flask app in app.py."""

import json

import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


SAMPLE_MD = """\
# Title

This is some prose text for testing.

```python
x = 1
```

A [link](https://example.com) here.
"""

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# /api/protect — valid payloads
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", ["zero_width", "homoglyph", "combining"])
def test_api_protect_valid(client, strategy):
    payload = {"text": SAMPLE_MD, "strategy": strategy, "density": 0.5}
    resp = client.post(
        "/api/protect",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "protected_text" in data
    assert "original_token_count" in data
    assert "modified_token_count" in data
    assert "expansion_ratio" in data
    assert isinstance(data["protected_text"], str)
    assert len(data["protected_text"]) >= len(SAMPLE_MD)


def test_api_protect_default_density(client):
    payload = {"text": SAMPLE_MD, "strategy": "homoglyph"}
    resp = client.post(
        "/api/protect",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200


def test_api_protect_density_clamped(client):
    # density > 1 should be clamped, not error
    payload = {"text": SAMPLE_MD, "strategy": "homoglyph", "density": 5.0}
    resp = client.post(
        "/api/protect",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/protect — invalid payloads → 4xx
# ---------------------------------------------------------------------------


def test_api_protect_empty_text(client):
    payload = {"text": "", "strategy": "homoglyph", "density": 0.25}
    resp = client.post(
        "/api/protect",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_protect_whitespace_only_text(client):
    payload = {"text": "   \n\t  ", "strategy": "homoglyph", "density": 0.25}
    resp = client.post(
        "/api/protect",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_protect_invalid_strategy(client):
    payload = {"text": SAMPLE_MD, "strategy": "bad_strategy", "density": 0.25}
    resp = client.post(
        "/api/protect",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_protect_oversized_text(client):
    big_text = "a" * 200_001
    payload = {"text": big_text, "strategy": "homoglyph", "density": 0.25}
    resp = client.post(
        "/api/protect",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 413


def test_api_protect_missing_text(client):
    payload = {"strategy": "homoglyph", "density": 0.25}
    resp = client.post(
        "/api/protect",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# UI endpoint
# ---------------------------------------------------------------------------


def test_index_get(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"WordEncrypt" in resp.data


def test_index_post_valid(client):
    resp = client.post(
        "/",
        data={"text": SAMPLE_MD, "strategy": "homoglyph", "density": "0.25"},
    )
    assert resp.status_code == 200
    assert b"protected" in resp.data.lower()
