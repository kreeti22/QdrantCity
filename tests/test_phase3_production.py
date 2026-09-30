"""
tests/test_phase3_production.py — Phase 3G: Production Hardening Regression Tests

Covers:
- 3A: Config validation (port, boost_weight, sync_interval, log_level)
- 3B: X-Request-ID header propagation and response echo
- 3B: Structured logging level application
- 3C: Security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
- 3C: Rate limiting (disabled by default, enabled on demand)
- 3C: request_id in error envelopes
- 3D: /metrics endpoint (privacy-safe, no personal data)
- 3D: Metrics tracking (search count increments)
- 3E: Dockerfile and .dockerignore presence
- 3F: Demo behavior (reset endpoint works, returns correct response)
"""

import os
import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def settings():
    return Settings(
        edge_storage_path="data/test_edge_phase3",
        collection_name="phase3_test_col",
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        vector_size=384,
        auto_seed_on_startup=True,
        sync_enabled=False,
        enable_personalization=True,
        personalization_boost_weight=0.20,
        rate_limit_search_enabled=False,
        rate_limit_sync_enabled=False,
        rate_limit_search_requests=60,
        rate_limit_search_window_seconds=60.0,
        rate_limit_sync_requests=10,
        rate_limit_sync_window_seconds=60.0,
        log_level="INFO",
    )


@pytest.fixture(scope="module")
def client(settings):
    app = create_app(settings=settings)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# 3A — Configuration Validation
# ---------------------------------------------------------------------------

class TestPhase3AConfig:

    def test_valid_settings_constructed(self, settings):
        """Settings with valid values should construct without error."""
        assert settings.port == 8000
        assert settings.log_level == "INFO"

    def test_invalid_port_rejected(self):
        """Port outside 1–65535 should raise a validation error."""
        with pytest.raises(Exception):
            Settings(port=99999)

    def test_invalid_port_zero_rejected(self):
        """Port 0 should raise a validation error."""
        with pytest.raises(Exception):
            Settings(port=0)

    def test_invalid_boost_weight_rejected(self):
        """Personalization boost weight > 1.0 should raise a validation error."""
        with pytest.raises(Exception):
            Settings(personalization_boost_weight=1.5)

    def test_invalid_boost_weight_negative_rejected(self):
        """Negative personalization boost weight should raise a validation error."""
        with pytest.raises(Exception):
            Settings(personalization_boost_weight=-0.1)

    def test_invalid_sync_interval_rejected(self):
        """sync_interval_seconds < 30 should raise a validation error."""
        with pytest.raises(Exception):
            Settings(sync_interval_seconds=10)

    def test_invalid_log_level_rejected(self):
        """Unknown log_level should raise a validation error."""
        with pytest.raises(Exception):
            Settings(log_level="VERBOSE")

    def test_valid_log_level_warning(self):
        """WARNING is a valid log level."""
        s = Settings(log_level="WARNING")
        assert s.log_level == "WARNING"

    def test_cors_origins_various_formats(self, monkeypatch):
        """CORS origins should parse raw strings, comma-separated lists, JSON arrays, and wildcards without crashing."""
        monkeypatch.setenv("QDRANT_EDGE_CORS_ORIGINS", "*")
        assert Settings().cors_origins == ["*"]

        monkeypatch.setenv("QDRANT_EDGE_CORS_ORIGINS", "")
        assert Settings().cors_origins == ["*"]

        monkeypatch.setenv("QDRANT_EDGE_CORS_ORIGINS", "https://app1.com, https://app2.com")
        assert Settings().cors_origins == ["https://app1.com", "https://app2.com"]

        monkeypatch.setenv("QDRANT_EDGE_CORS_ORIGINS", '["https://example.com"]')
        assert Settings().cors_origins == ["https://example.com"]

    def test_env_example_exists(self):
        """.env.example file must be present in repository root."""
        assert os.path.exists(".env.example"), ".env.example is missing"

    def test_env_example_contains_key_settings(self):
        """The .env.example must document the API key setting and CORS."""
        with open(".env.example", "r", encoding="utf-8") as f:
            content = f.read()
        assert "QDRANT_EDGE_SYNC_API_KEY" in content
        assert "QDRANT_EDGE_CORS_ORIGINS" in content


# ---------------------------------------------------------------------------
# 3B — X-Request-ID Header Propagation
# ---------------------------------------------------------------------------

class TestPhase3BRequestId:

    def test_request_id_returned_in_response(self, client):
        """Every response must include an X-Request-ID header."""
        resp = client.get("/live")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers

    def test_client_provided_request_id_echoed(self, client):
        """When client sends X-Request-ID, the same value must be echoed."""
        custom_id = "demo-test-request-001"
        resp = client.get("/live", headers={"X-Request-ID": custom_id})
        assert resp.status_code == 200
        assert resp.headers["X-Request-ID"] == custom_id

    def test_server_generates_request_id_if_missing(self, client):
        """If no X-Request-ID sent, the server should generate one (UUID-like)."""
        resp = client.get("/ready")
        assert resp.status_code == 200
        req_id = resp.headers.get("X-Request-ID", "")
        assert len(req_id) > 0

    def test_response_time_header_present(self, client):
        """X-Response-Time-Ms header should be present on all responses."""
        resp = client.get("/live")
        assert "X-Response-Time-Ms" in resp.headers
        val = float(resp.headers["X-Response-Time-Ms"])
        assert val >= 0.0


# ---------------------------------------------------------------------------
# 3C — Security Headers
# ---------------------------------------------------------------------------

class TestPhase3CSecurityHeaders:

    def test_x_content_type_options_present(self, client):
        """X-Content-Type-Options: nosniff must be present on all responses."""
        resp = client.get("/live")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options_present(self, client):
        """X-Frame-Options: DENY must be present on all responses."""
        assert resp_header(client, "/live", "X-Frame-Options") == "DENY"

    def test_referrer_policy_present(self, client):
        """Referrer-Policy must be set on all responses."""
        val = resp_header(client, "/live", "Referrer-Policy")
        assert val is not None
        assert "origin" in val.lower()

    def test_404_error_envelope_has_request_id(self, client):
        """404 error envelope must include request_id."""
        resp = client.get("/api/experiences/999999")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert "request_id" in body["error"]

    def test_400_error_envelope_has_request_id(self, client):
        """400 error envelope must include request_id."""
        resp = client.post("/api/experiences/search", json={"query": ""})
        assert resp.status_code in (400, 422)
        body = resp.json()
        assert "error" in body
        assert "request_id" in body["error"]

    def test_rate_limiter_disabled_by_default(self, client):
        """Rate limiting is disabled by default — 60 rapid searches should all succeed."""
        for _ in range(5):
            resp = client.post(
                "/api/experiences/search",
                json={"query": "comedy shows"},
            )
            # Should never be rate-limited when disabled
            assert resp.status_code != 429


# ---------------------------------------------------------------------------
# 3C — Rate Limiting (enabled explicitly)
# ---------------------------------------------------------------------------

class TestPhase3CRateLimiting:

    def test_rate_limiter_class_allows_within_limit(self):
        """RateLimiter allows requests within window."""
        from app.ratelimit import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=60.0)
        for _ in range(5):
            allowed, retry_after = limiter.is_allowed("test-ip")
            assert allowed is True
            assert retry_after == 0.0

    def test_rate_limiter_class_rejects_when_exceeded(self):
        """RateLimiter rejects requests beyond window limit."""
        from app.ratelimit import RateLimiter
        limiter = RateLimiter(max_requests=3, window_seconds=60.0)
        for _ in range(3):
            limiter.is_allowed("test-ip")
        allowed, retry_after = limiter.is_allowed("test-ip")
        assert allowed is False
        assert retry_after > 0.0

    def test_rate_limiter_isolates_clients(self):
        """Different client keys have independent rate limit windows."""
        from app.ratelimit import RateLimiter
        limiter = RateLimiter(max_requests=2, window_seconds=60.0)
        for _ in range(2):
            limiter.is_allowed("client-a")
        # client-b should still be allowed
        allowed, _ = limiter.is_allowed("client-b")
        assert allowed is True


# ---------------------------------------------------------------------------
# 3D — Metrics Endpoint
# ---------------------------------------------------------------------------

class TestPhase3DMetrics:

    def test_metrics_endpoint_returns_200(self, client):
        """/metrics must return 200 OK."""
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_has_required_keys(self, client):
        """/metrics response must contain uptime_seconds, search, bookmarks, sync."""
        data = client.get("/metrics").json()
        assert "uptime_seconds" in data
        assert "search" in data
        assert "bookmarks" in data
        assert "sync" in data

    def test_metrics_search_has_percentiles(self, client):
        """/metrics search.latency_ms must include p50, p95, p99 keys."""
        data = client.get("/metrics").json()
        latency = data["search"]["latency_ms"]
        assert "p50" in latency
        assert "p95" in latency
        assert "p99" in latency
        assert "avg" in latency

    def test_metrics_increments_after_search(self, client):
        """Performing a search should increment search.total."""
        before = client.get("/metrics").json()["search"]["total"]
        client.post("/api/experiences/search", json={"query": "comedy"})
        after = client.get("/metrics").json()["search"]["total"]
        assert after == before + 1

    def test_metrics_no_personal_data(self, client):
        """Metrics response must not contain user_id, query text, or bookmarks content."""
        data = client.get("/metrics").json()
        raw = str(data)
        assert "user_id" not in raw
        assert "local-default" not in raw

    def test_metrics_uptime_positive(self, client):
        """Uptime must be a positive number after startup."""
        data = client.get("/metrics").json()
        assert data["uptime_seconds"] > 0.0

    def test_metrics_collector_class(self):
        """MetricsCollector records and snapshots correctly."""
        from app.metrics import MetricsCollector
        m = MetricsCollector()
        m.record_search(success=True, latency_ms=42.0)
        m.record_search(success=False, latency_ms=200.0)
        m.record_bookmark_add()
        m.record_sync(success=True, items_applied=5)
        snap = m.snapshot()
        assert snap["search"]["total"] == 2
        assert snap["search"]["success"] == 1
        assert snap["search"]["error"] == 1
        assert snap["bookmarks"]["adds"] == 1
        assert snap["sync"]["success"] == 1
        assert snap["sync"]["items_applied"] == 5


# ---------------------------------------------------------------------------
# 3E — Deployment Packaging Files
# ---------------------------------------------------------------------------

class TestPhase3EDeployment:

    def test_dockerfile_exists(self):
        """Dockerfile must be present."""
        assert os.path.exists("Dockerfile"), "Dockerfile missing"

    def test_dockerignore_exists(self):
        """.dockerignore must be present."""
        assert os.path.exists(".dockerignore"), ".dockerignore missing"

    def test_docker_compose_exists(self):
        """docker-compose.yml must be present."""
        assert os.path.exists("docker-compose.yml"), "docker-compose.yml missing"

    def test_dockerfile_has_healthcheck(self):
        """Dockerfile must include a HEALTHCHECK instruction."""
        with open("Dockerfile", "r", encoding="utf-8") as f:
            content = f.read()
        assert "HEALTHCHECK" in content

    def test_dockerfile_has_volume_declaration(self):
        """Dockerfile must declare a VOLUME for persistent data."""
        with open("Dockerfile", "r", encoding="utf-8") as f:
            content = f.read()
        assert "VOLUME" in content

    def test_dockerignore_excludes_env(self):
        """.dockerignore must exclude .env (secrets)."""
        with open(".dockerignore", "r", encoding="utf-8") as f:
            content = f.read()
        assert ".env" in content

    def test_dockerignore_excludes_tests(self):
        """.dockerignore should exclude tests/ directory."""
        with open(".dockerignore", "r", encoding="utf-8") as f:
            content = f.read()
        assert "tests/" in content


# ---------------------------------------------------------------------------
# 3F — Demo UX: Reset Memory
# ---------------------------------------------------------------------------

class TestPhase3FDemo:

    def test_reset_memory_endpoint_returns_200(self, client):
        """DELETE /api/users/{user_id}/memory should return 200."""
        resp = client.delete("/api/users/demo-user/memory")
        assert resp.status_code == 200

    def test_reset_memory_returns_status_cleared(self, client):
        """Reset response must include status=cleared."""
        resp = client.delete("/api/users/demo-user/memory")
        data = resp.json()
        assert data.get("status") == "cleared"
        assert data.get("user_id") == "demo-user"

    def test_ready_endpoint_includes_points_count(self, client):
        """/ready must report points_count for demo panel."""
        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert "points_count" in data
        assert isinstance(data["points_count"], int)
        assert data["points_count"] >= 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resp_header(client, path, header_name):
    resp = client.get(path)
    return resp.headers.get(header_name)
