"""
End-to-end tests for all web authentication strategies.

Each test starts a local HTTP server that validates the auth mechanism,
uses the corresponding AuthStrategy to authenticate a requests.Session,
and verifies the authenticated session can access a protected resource.
"""

import base64
import json
import threading
from unittest.mock import MagicMock
from urllib.parse import parse_qs

import pytest
import requests

import sadif.frameworks_drivers.crawler.base_crawler as crawler_mod
from sadif.frameworks_drivers.web.authenticator.api_key_auth_strategy import ApiKeyAuthStrategy
from sadif.frameworks_drivers.web.authenticator.basic_auth_strategy import BasicAuthStrategy
from sadif.frameworks_drivers.web.authenticator.bearer_auth_strategy import BearerAuthStrategy
from sadif.frameworks_drivers.web.authenticator.cookie_auth_strategy import CookieAuthStrategy
from sadif.frameworks_drivers.web.authenticator.digest_auth_strategy import DigestAuthStrategy
from sadif.frameworks_drivers.web.authenticator.form_auth_strategy import FormAuthStrategy
from sadif.frameworks_drivers.web.authenticator.oauth2_client_credentials_strategy import (
    OAuth2ClientCredentialsStrategy,
)

# ---------------------------------------------------------------------------
# Strategy-level tests (each strategy against a local HTTP server)
# ---------------------------------------------------------------------------


class TestBasicAuthStrategyE2E:
    def test_basic_auth_accepted(self, http_server):
        def handler(req):
            auth = req["headers"].get("Authorization", "")
            expected = base64.b64encode(b"admin:secret123").decode()
            if auth == f"Basic {expected}":
                return 200, "application/json", '{"status": "authenticated"}'
            return 401, "text/plain", "Unauthorized"

        url = http_server.add_handler("/protected", handler)
        session = requests.Session()
        strategy = BasicAuthStrategy("admin", "secret123")
        session = strategy.authenticate(session)
        resp = session.get(url)
        assert resp.status_code == 200
        assert resp.json()["status"] == "authenticated"

    def test_basic_auth_wrong_password(self, http_server):
        def handler(req):
            auth = req["headers"].get("Authorization", "")
            expected = base64.b64encode(b"admin:secret123").decode()
            if auth == f"Basic {expected}":
                return 200, "application/json", '{"status": "authenticated"}'
            return 401, "text/plain", "Unauthorized"

        url = http_server.add_handler("/protected", handler)
        session = requests.Session()
        strategy = BasicAuthStrategy("admin", "wrong")
        session = strategy.authenticate(session)
        resp = session.get(url)
        assert resp.status_code == 401


class TestBearerAuthStrategyE2E:
    def test_bearer_token_accepted(self, http_server):
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"  # noqa: S105

        def handler(req):
            auth = req["headers"].get("Authorization", "")
            if auth == f"Bearer {token}":
                return 200, "application/json", '{"status": "authenticated"}'
            return 401, "text/plain", "Unauthorized"

        url = http_server.add_handler("/api/data", handler)
        session = requests.Session()
        strategy = BearerAuthStrategy(token)
        session = strategy.authenticate(session)
        resp = session.get(url)
        assert resp.status_code == 200
        assert resp.json()["status"] == "authenticated"

    def test_bearer_missing_token(self, http_server):
        def handler(req):
            if "Authorization" in req["headers"]:
                return 200, "application/json", '{"status": "ok"}'
            return 401, "text/plain", "No token"

        url = http_server.add_handler("/api/data", handler)
        session = requests.Session()
        resp = session.get(url)
        assert resp.status_code == 401


class TestDigestAuthStrategyE2E:
    def test_digest_sets_auth(self):
        session = requests.Session()
        strategy = DigestAuthStrategy("user", "pass")
        session = strategy.authenticate(session)
        assert session.auth is not None
        assert session.auth.username == "user"
        assert session.auth.password == "pass"  # noqa: S105


class TestFormAuthStrategyE2E:
    def test_form_login_sets_session_cookie(self, http_server):
        def login_handler(req):
            if req["method"] != "POST":
                return 405, "text/plain", "Method Not Allowed"
            body = parse_qs(req["body"])
            if body.get("username") == ["admin"] and body.get("password") == ["secret"]:
                return 200, "application/json", '{"login": "ok"}'
            return 403, "text/plain", "Invalid credentials"

        def protected_handler(req):
            return 200, "application/json", '{"data": "secret_content"}'

        login_url = http_server.add_handler("/login", login_handler)
        protected_url = http_server.add_handler("/dashboard", protected_handler)

        session = requests.Session()
        strategy = FormAuthStrategy(login_url, {"username": "admin", "password": "secret"})
        session = strategy.authenticate(session)

        resp = session.get(protected_url)
        assert resp.status_code == 200
        assert resp.json()["data"] == "secret_content"

        login_reqs = [r for r in http_server.requests if r["path"] == "/login"]
        assert len(login_reqs) == 1
        assert login_reqs[0]["method"] == "POST"

    def test_form_login_bad_credentials_raises(self, http_server):
        def login_handler(req):
            return 403, "text/plain", "Forbidden"

        login_url = http_server.add_handler("/login", login_handler)
        session = requests.Session()
        strategy = FormAuthStrategy(login_url, {"username": "bad", "password": "bad"})
        with pytest.raises(requests.HTTPError):
            strategy.authenticate(session)


class TestApiKeyAuthStrategyE2E:
    def test_api_key_in_header(self, http_server):
        def handler(req):
            if req["headers"].get("X-Api-Key") == "my-secret-key-123":
                return 200, "application/json", '{"status": "ok"}'
            return 403, "text/plain", "Invalid API key"

        url = http_server.add_handler("/api/resource", handler)
        session = requests.Session()
        strategy = ApiKeyAuthStrategy("X-Api-Key", "my-secret-key-123", "header")
        session = strategy.authenticate(session)
        resp = session.get(url)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_api_key_in_query(self, http_server):
        def handler(req):
            if "api_key=my-secret-key" in req["path"]:
                return 200, "application/json", '{"status": "ok"}'
            return 403, "text/plain", "No API key in query"

        url = http_server.add_handler("/api/resource", handler)
        session = requests.Session()
        strategy = ApiKeyAuthStrategy("api_key", "my-secret-key", "query")
        session = strategy.authenticate(session)
        resp = session.get(url)
        assert resp.status_code == 200

    def test_api_key_wrong_value(self, http_server):
        def handler(req):
            if req["headers"].get("X-Api-Key") == "correct-key":
                return 200, "application/json", '{"status": "ok"}'
            return 403, "text/plain", "Invalid"

        url = http_server.add_handler("/api/resource", handler)
        session = requests.Session()
        strategy = ApiKeyAuthStrategy("X-Api-Key", "wrong-key", "header")
        session = strategy.authenticate(session)
        resp = session.get(url)
        assert resp.status_code == 403


class TestCookieAuthStrategyE2E:
    def test_cookie_auth_accepted(self, http_server):
        def handler(req):
            cookies = req["headers"].get("Cookie", "")
            if "session_id=abc123" in cookies:
                return 200, "application/json", '{"status": "authenticated"}'
            return 401, "text/plain", "No session"

        url = http_server.add_handler("/protected", handler)
        session = requests.Session()
        strategy = CookieAuthStrategy({"session_id": "abc123"})
        session = strategy.authenticate(session)
        resp = session.get(url)
        assert resp.status_code == 200
        assert resp.json()["status"] == "authenticated"

    def test_multiple_cookies(self, http_server):
        def handler(req):
            cookies = req["headers"].get("Cookie", "")
            if "token=xyz" in cookies and "user=admin" in cookies:
                return 200, "application/json", '{"status": "ok"}'
            return 401, "text/plain", "Missing cookies"

        url = http_server.add_handler("/multi", handler)
        session = requests.Session()
        strategy = CookieAuthStrategy({"token": "xyz", "user": "admin"})
        session = strategy.authenticate(session)
        resp = session.get(url)
        assert resp.status_code == 200


class TestOAuth2ClientCredentialsStrategyE2E:
    def test_oauth2_token_exchange(self, http_server):
        def token_handler(req):
            if req["method"] != "POST":
                return 405, "text/plain", "Method Not Allowed"
            body = parse_qs(req["body"])
            if (
                body.get("grant_type") == ["client_credentials"]
                and body.get("client_id") == ["my-client"]
                and body.get("client_secret") == ["my-secret"]
            ):
                return (
                    200,
                    "application/json",
                    json.dumps({"access_token": "oauth-token-xyz", "token_type": "bearer"}),
                )
            return 400, "application/json", '{"error": "invalid_client"}'

        def protected_handler(req):
            if req["headers"].get("Authorization") == "Bearer oauth-token-xyz":
                return 200, "application/json", '{"data": "protected_resource"}'
            return 401, "text/plain", "Unauthorized"

        token_url = http_server.add_handler("/oauth/token", token_handler)
        protected_url = http_server.add_handler("/api/resource", protected_handler)

        session = requests.Session()
        strategy = OAuth2ClientCredentialsStrategy(token_url, "my-client", "my-secret")
        session = strategy.authenticate(session)
        resp = session.get(protected_url)
        assert resp.status_code == 200
        assert resp.json()["data"] == "protected_resource"

    def test_oauth2_with_scope(self, http_server):
        def token_handler(req):
            body = parse_qs(req["body"])
            if body.get("scope") == ["read write"]:
                return (
                    200,
                    "application/json",
                    json.dumps({"access_token": "scoped-token", "token_type": "bearer"}),
                )
            return 400, "application/json", '{"error": "invalid_scope"}'

        token_url = http_server.add_handler("/oauth/token", token_handler)
        session = requests.Session()
        strategy = OAuth2ClientCredentialsStrategy(
            token_url, "client", "secret", scope="read write"
        )
        session = strategy.authenticate(session)
        assert session.headers["Authorization"] == "Bearer scoped-token"

    def test_oauth2_bad_credentials(self, http_server):
        def token_handler(req):
            return 401, "application/json", '{"error": "invalid_client"}'

        token_url = http_server.add_handler("/oauth/token", token_handler)
        session = requests.Session()
        strategy = OAuth2ClientCredentialsStrategy(token_url, "bad", "bad")
        with pytest.raises(requests.HTTPError):
            strategy.authenticate(session)


# ---------------------------------------------------------------------------
# BaseCrawler.authenticate() integration tests
# ---------------------------------------------------------------------------


class TestBaseCrawlerAuthenticate:
    """Tests BaseCrawler.authenticate() with a real HTTP server but mocked MongoDB."""

    @pytest.fixture()
    def crawler_factory(self, monkeypatch):
        """Returns a factory that creates a BaseCrawler without a real MongoDB."""

        def patched_init(self, base_url, depth, proxy=None, timeout=10, db_client=None):
            self.base_url = base_url
            self.depth = depth
            self.session = requests.Session()
            self.proxy = proxy
            self.timeout = timeout
            self.client = MagicMock()
            self.yara_compiler = MagicMock()
            self.visited_urls = set()
            self.error_urls = set()
            self._visited_lock = threading.Lock()
            self._yara_lock = threading.Lock()
            self.log_manager = MagicMock()
            self.module_name = "BaseCrawler"
            self.log_message = ""
            self.yara_matches = []

        monkeypatch.setattr(crawler_mod.BaseCrawler, "__init__", patched_init)

        def make(url, depth=0):
            return crawler_mod.BaseCrawler(url, depth)

        return make

    def test_authenticate_basic(self, http_server, crawler_factory):
        def handler(req):
            expected = base64.b64encode(b"user:pass").decode()
            if req["headers"].get("Authorization") == f"Basic {expected}":
                return 200, "text/html", "<html>OK</html>"
            return 401, "text/plain", "Unauthorized"

        url = http_server.add_handler("/", handler)
        crawler = crawler_factory(url)
        crawler.authenticate({"type": "basic", "username": "user", "password": "pass"})
        resp = crawler.session.get(url)
        assert resp.status_code == 200

    def test_authenticate_bearer(self, http_server, crawler_factory):
        def handler(req):
            if req["headers"].get("Authorization") == "Bearer mytoken":
                return 200, "text/html", "<html>OK</html>"
            return 401, "text/plain", "Unauthorized"

        url = http_server.add_handler("/", handler)
        crawler = crawler_factory(url)
        crawler.authenticate({"type": "bearer", "token": "mytoken"})
        resp = crawler.session.get(url)
        assert resp.status_code == 200

    def test_authenticate_form(self, http_server, crawler_factory):
        def login_handler(req):
            body = parse_qs(req["body"])
            if body.get("user") == ["admin"] and body.get("pw") == ["secret"]:
                return 200, "application/json", '{"ok": true}'
            return 403, "text/plain", "Forbidden"

        login_url = http_server.add_handler("/login", login_handler)
        http_server.add("/", "<html>Home</html>")
        crawler = crawler_factory(http_server.url)
        crawler.authenticate(
            {
                "type": "form",
                "login_url": login_url,
                "user": "admin",
                "pw": "secret",
            }
        )
        login_reqs = [r for r in http_server.requests if r["path"] == "/login"]
        assert len(login_reqs) == 1

    def test_authenticate_api_key(self, http_server, crawler_factory):
        def handler(req):
            if req["headers"].get("X-Api-Key") == "key123":
                return 200, "text/html", "<html>OK</html>"
            return 403, "text/plain", "Forbidden"

        url = http_server.add_handler("/", handler)
        crawler = crawler_factory(url)
        crawler.authenticate({"type": "api_key", "key": "X-Api-Key", "value": "key123"})
        resp = crawler.session.get(url)
        assert resp.status_code == 200

    def test_authenticate_cookie(self, http_server, crawler_factory):
        def handler(req):
            cookies = req["headers"].get("Cookie", "")
            if "sid=abc" in cookies:
                return 200, "text/html", "<html>OK</html>"
            return 401, "text/plain", "Unauthorized"

        url = http_server.add_handler("/", handler)
        crawler = crawler_factory(url)
        crawler.authenticate({"type": "cookie", "cookies": '{"sid": "abc"}'})
        resp = crawler.session.get(url)
        assert resp.status_code == 200

    def test_authenticate_oauth2(self, http_server, crawler_factory):
        def token_handler(req):
            body = parse_qs(req["body"])
            if body.get("client_id") == ["cid"] and body.get("client_secret") == ["csec"]:
                return (
                    200,
                    "application/json",
                    json.dumps({"access_token": "tok", "token_type": "bearer"}),
                )
            return 400, "application/json", '{"error": "invalid_client"}'

        def page_handler(req):
            if req["headers"].get("Authorization") == "Bearer tok":
                return 200, "text/html", "<html>Protected</html>"
            return 401, "text/plain", "No"

        token_url = http_server.add_handler("/oauth/token", token_handler)
        http_server.add_handler("/", page_handler)
        crawler = crawler_factory(http_server.url)
        crawler.authenticate(
            {
                "type": "oauth2_client_credentials",
                "token_url": token_url,
                "client_id": "cid",
                "client_secret": "csec",
            }
        )
        resp = crawler.session.get(http_server.url)
        assert resp.status_code == 200

    def test_authenticate_unsupported_type(self, crawler_factory):
        crawler = crawler_factory("http://example.com")
        with pytest.raises(ValueError, match="Unsupported auth type"):
            crawler.authenticate({"type": "kerberos"})

    def test_authenticate_infers_bearer(self, http_server, crawler_factory):
        def handler(req):
            if req["headers"].get("Authorization") == "Bearer auto":
                return 200, "text/html", "<html>OK</html>"
            return 401, "text/plain", "No"

        url = http_server.add_handler("/", handler)
        crawler = crawler_factory(url)
        crawler.authenticate({"token": "auto"})
        resp = crawler.session.get(url)
        assert resp.status_code == 200
