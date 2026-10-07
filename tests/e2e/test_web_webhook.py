import pytest

pytestmark = pytest.mark.e2e

import base64  # noqa: E402
import hashlib  # noqa: E402
import http.server  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from collections.abc import Iterator  # noqa: E402

import requests  # noqa: E402
from requests import Session  # noqa: E402
from requests.auth import HTTPDigestAuth  # noqa: E402
from requests.exceptions import (  # noqa: E402
    ConnectionError as RequestsConnectionError,
)
from requests.exceptions import (  # noqa: E402
    HTTPError,
    InvalidURL,
    RequestException,
    Timeout,
)

from sadif.frameworks_drivers.notification.webhook import WebhookSender  # noqa: E402
from sadif.frameworks_drivers.web.authenticator import Authenticator  # noqa: E402
from sadif.frameworks_drivers.web.authenticator.basic_auth_strategy import (  # noqa: E402
    BasicAuthStrategy,
)
from sadif.frameworks_drivers.web.authenticator.bearer_auth_strategy import (  # noqa: E402
    BearerAuthStrategy,
)
from sadif.frameworks_drivers.web.authenticator.digest_auth_strategy import (  # noqa: E402
    DigestAuthStrategy,
)
from sadif.frameworks_drivers.web.session_manager import SessionManager  # noqa: E402
from sadif.interfaces.base_modules import IBaseModule  # noqa: E402
from sadif.interfaces.web.authenticator import AuthStrategy  # noqa: E402

# ---------------------------------------------------------------------------
# Servidor HTTP próprio: verifica Basic/Bearer/Digest de verdade, rotas que
# falham N vezes antes de responder 200 e rotas lentas (timeouts).
# ---------------------------------------------------------------------------

REALM = "sadif-e2e"
_PARAM_RE = re.compile(r'(\w+)=(?:"([^"]*)"|([^\s,]*))')


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()  # noqa: S324


class _AuthHandler(http.server.BaseHTTPRequestHandler):
    server: "AuthHTTPServer"

    def _reply(self, status: int, body: dict, extra_headers: dict | None = None) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _check_digest(self, header: str) -> bool:
        if not header.startswith("Digest "):
            return False
        params = {k: (q if q else u) for k, q, u in _PARAM_RE.findall(header[7:])}
        nonce = params.get("nonce", "")
        if nonce not in self.server.nonces or params.get("username") != self.server.user:
            return False
        ha1 = _md5(f"{self.server.user}:{REALM}:{self.server.password}")
        ha2 = _md5(f"{self.command}:{params.get('uri', '')}")
        expected = _md5(
            f"{ha1}:{nonce}:{params.get('nc')}:{params.get('cnonce')}:{params.get('qop')}:{ha2}"
        )
        return params.get("response") == expected and params.get("uri") == self.path

    def _handle(self) -> None:  # noqa: PLR0911
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        auth = self.headers.get("Authorization", "")
        path = self.path.split("?", 1)[0]
        with self.server.lock:
            self.server.log.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": body,
                }
            )
            count = sum(1 for r in self.server.log if r["path"].split("?", 1)[0] == path)
        user, password = self.server.user, self.server.password
        if path == "/basic":
            expected = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
            if auth == expected:
                return self._reply(200, {"auth": "basic", "user": user})
            return self._reply(
                401, {"error": "bad basic"}, {"WWW-Authenticate": f'Basic realm="{REALM}"'}
            )
        if path == "/bearer":
            if auth == f"Bearer {self.server.token}":
                return self._reply(200, {"auth": "bearer"})
            return self._reply(401, {"error": "bad bearer"})
        if path == "/digest":
            if self._check_digest(auth):
                return self._reply(200, {"auth": "digest", "user": user})
            nonce = uuid.uuid4().hex
            with self.server.lock:
                self.server.nonces.add(nonce)
            challenge = f'Digest realm="{REALM}", qop="auth", nonce="{nonce}", opaque="{uuid.uuid4().hex}", algorithm=MD5'
            return self._reply(401, {"error": "digest required"}, {"WWW-Authenticate": challenge})
        if path.startswith("/flaky/"):
            # /flaky/<n>: responde 500 nas n primeiras chamadas e 200 depois
            failures = int(path.rsplit("/", 1)[1])
            if count <= failures:
                return self._reply(500, {"error": f"failure {count}"})
            return self._reply(200, {"ok": True, "attempt": count})
        if path.startswith("/slow/"):
            # /slow/<segundos>: dorme antes de responder
            time.sleep(float(path.rsplit("/", 1)[1]))
            return self._reply(200, {"ok": True})
        if path == "/echo":
            return self._reply(200, {"method": self.command, "body": body})
        return self._reply(404, {"error": "not found"})

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

    def log_message(self, *args) -> None:
        pass


class AuthHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, user: str, password: str, token: str) -> None:
        super().__init__(("127.0.0.1", 0), _AuthHandler)
        self.user, self.password, self.token = user, password, token
        self.log: list[dict] = []
        self.nonces: set[str] = set()
        self.lock = threading.Lock()
        self.url = f"http://127.0.0.1:{self.server_address[1]}"

    def requests_to(self, path: str) -> list[dict]:
        with self.lock:
            return [r for r in self.log if r["path"].split("?", 1)[0] == path]


@pytest.fixture()
def auth_server(e2e_id: str) -> Iterator[AuthHTTPServer]:
    server = AuthHTTPServer(user=f"user-{e2e_id}", password=f"pw-{e2e_id}", token=f"tok-{e2e_id}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


class Recorder:
    def __init__(self) -> None:
        self.calls: list = []

    def __call__(self, arg) -> None:
        self.calls.append(arg)


# ---------------------------------------------------------------------------
# Estratégias de autenticação + SessionManager
# ---------------------------------------------------------------------------


def test_basic_strategy_authenticates_real_request(auth_server: AuthHTTPServer) -> None:
    manager = SessionManager()
    session = manager.create_session(BasicAuthStrategy(auth_server.user, auth_server.password))
    assert isinstance(session, Session)
    assert session in manager.sessions

    response = session.get(f"{auth_server.url}/basic", timeout=5)
    assert response.status_code == 200
    assert response.json() == {"auth": "basic", "user": auth_server.user}
    sent = auth_server.requests_to("/basic")[-1]["headers"]["Authorization"]
    assert (
        base64.b64decode(sent.split(" ", 1)[1]).decode()
        == f"{auth_server.user}:{auth_server.password}"
    )


def test_basic_strategy_wrong_password_is_rejected(auth_server: AuthHTTPServer) -> None:
    manager = SessionManager()
    session = manager.create_session(BasicAuthStrategy(auth_server.user, "wrong"))
    response = session.get(f"{auth_server.url}/basic", timeout=5)
    assert response.status_code == 401
    with pytest.raises(HTTPError):
        response.raise_for_status()


def test_bearer_strategy_sets_header_on_every_request(auth_server: AuthHTTPServer) -> None:
    manager = SessionManager()
    session = manager.create_session(BearerAuthStrategy(auth_server.token))
    assert session.headers["Authorization"] == f"Bearer {auth_server.token}"

    for _ in range(3):
        assert session.get(f"{auth_server.url}/bearer", timeout=5).status_code == 200
    received = auth_server.requests_to("/bearer")
    assert len(received) == 3
    assert {r["headers"]["Authorization"] for r in received} == {f"Bearer {auth_server.token}"}


def test_bearer_strategy_wrong_token_and_isolated_sessions(auth_server: AuthHTTPServer) -> None:
    manager = SessionManager()
    bad = manager.create_session(BearerAuthStrategy("invalid-token"))
    anonymous = manager.create_session()
    assert bad.get(f"{auth_server.url}/bearer", timeout=5).status_code == 401
    assert anonymous.get(f"{auth_server.url}/bearer", timeout=5).status_code == 401
    assert "Authorization" not in auth_server.requests_to("/bearer")[-1]["headers"]
    assert anonymous.auth is None
    assert len(manager.sessions) == 2


def test_digest_strategy_answers_401_challenge(auth_server: AuthHTTPServer) -> None:
    manager = SessionManager()
    session = manager.create_session(DigestAuthStrategy(auth_server.user, auth_server.password))
    assert isinstance(session.auth, HTTPDigestAuth)

    response = session.get(f"{auth_server.url}/digest", timeout=5)
    assert response.status_code == 200
    assert response.json() == {"auth": "digest", "user": auth_server.user}

    received = auth_server.requests_to("/digest")
    assert len(received) == 2  # desafio 401 + requisição autenticada
    assert "Authorization" not in received[0]["headers"]
    digest_header = received[1]["headers"]["Authorization"]
    assert digest_header.startswith("Digest ")
    assert f'username="{auth_server.user}"' in digest_header
    assert auth_server.password not in digest_header


def test_digest_strategy_wrong_password_is_rejected(auth_server: AuthHTTPServer) -> None:
    session = SessionManager().create_session(DigestAuthStrategy(auth_server.user, "wrong"))
    response = session.get(f"{auth_server.url}/digest", timeout=5)
    assert response.status_code == 401
    # requests tenta responder ao desafio apenas uma vez (sem loop infinito)
    assert len(auth_server.requests_to("/digest")) == 2


@pytest.mark.parametrize("kind", ["basic", "bearer", "digest"])
def test_authenticator_wrapper_with_session_manager(auth_server: AuthHTTPServer, kind: str) -> None:
    strategies: dict[str, AuthStrategy] = {
        "basic": BasicAuthStrategy(auth_server.user, auth_server.password),
        "bearer": BearerAuthStrategy(auth_server.token),
        "digest": DigestAuthStrategy(auth_server.user, auth_server.password),
    }
    authenticator = Authenticator(strategies[kind])
    assert isinstance(authenticator, AuthStrategy)
    assert authenticator.strategy is strategies[kind]

    # uso direto do wrapper sobre uma sessão existente
    plain = Session()
    assert authenticator.authenticate(plain) is plain
    assert plain.get(f"{auth_server.url}/{kind}", timeout=5).status_code == 200
    plain.close()

    # uso do wrapper como estratégia do SessionManager
    manager = SessionManager()
    session = manager.create_session(authenticator)
    assert session.get(f"{auth_server.url}/{kind}", timeout=5).status_code == 200
    manager.close_all_sessions()


def test_auth_strategy_is_abstract() -> None:
    with pytest.raises(TypeError):
        AuthStrategy()  # type: ignore[abstract]

    class Custom(AuthStrategy):
        def authenticate(self, session: Session) -> Session:
            session.headers["X-Custom-Auth"] = "yes"
            return session

    session = SessionManager().create_session(Custom())
    assert session.headers["X-Custom-Auth"] == "yes"


def test_ibase_module_is_abstract() -> None:
    with pytest.raises(TypeError):
        IBaseModule()  # type: ignore[abstract]

    class Module(IBaseModule):
        def execute(self):
            return "exec"

        def initialize_module_collection(self):
            return "init"

        def list_data(self):
            return []

        def update_git_repository(self):
            return "update"

        def import_git_repository(self):
            return "import"

    module = Module()
    assert module.execute() == "exec"
    assert module.list_data() == []


def test_session_manager_close_session_and_close_all(http_server, e2e_id: str) -> None:
    url = http_server.add(f"/{e2e_id}/ping", "pong")
    manager = SessionManager()
    s1 = manager.create_session(BearerAuthStrategy("t1"))
    s2 = manager.create_session(BasicAuthStrategy("u", "p"))
    s3 = manager.create_session()
    for s in (s1, s2, s3):
        assert s.get(url, timeout=5).text == "pong"
    assert len(http_server.requests) == 3
    assert http_server.requests[0]["headers"]["Authorization"] == "Bearer t1"
    assert http_server.requests[1]["headers"]["Authorization"].startswith("Basic ")
    assert "Authorization" not in http_server.requests[2]["headers"]
    assert all(s.adapters for s in (s1, s2, s3))

    manager.close_session(s1)
    assert manager.sessions == [s2, s3]
    # sessão fechada perde os adapters de conexão ativos
    assert all(not a.poolmanager.pools for a in s1.adapters.values())

    # fechar uma sessão que não pertence (mais) ao manager é um erro explícito
    with pytest.raises(ValueError):
        manager.close_session(s1)
    with pytest.raises(ValueError):
        manager.close_session(Session())

    manager.close_all_sessions()
    assert manager.sessions == []
    manager.close_all_sessions()  # idempotente
    assert manager.sessions == []


# ---------------------------------------------------------------------------
# WebhookSender
# ---------------------------------------------------------------------------


def test_webhook_send_success_and_callbacks(http_server, e2e_id: str) -> None:
    url = http_server.add(f"/{e2e_id}/hook", '{"received": true}', content_type="application/json")
    ok, fail = Recorder(), Recorder()
    sender = WebhookSender(url, success_callback=ok, failure_callback=fail)
    assert sender.validate_url() is True

    payload = {"event": "case_created", "id": e2e_id, "tags": ["a", "b"]}
    response = sender.send(payload)
    assert response is not None
    assert response.status_code == 200
    assert response.json() == {"received": True}

    assert len(http_server.requests) == 1
    req = http_server.requests[0]
    assert req["method"] == "POST"
    assert req["path"] == f"/{e2e_id}/hook"
    assert req["headers"]["Content-Type"] == "application/json"
    assert json.loads(req["body"]) == payload
    assert ok.calls == [response]
    assert fail.calls == []


def test_webhook_custom_headers_and_methods(http_server, e2e_id: str) -> None:
    url = http_server.add(f"/{e2e_id}/hook", "ok")
    sender = WebhookSender(url)
    sender.send({"a": 1}, headers={"X-Sadif-Signature": e2e_id}, method="PUT")
    sender.send([1, 2, 3], method="PATCH")
    sender.send("raw=text", headers={"Content-Type": "text/plain"}, method="POST")

    put, patch, post = http_server.requests
    assert put["method"] == "PUT"
    assert put["headers"]["X-Sadif-Signature"] == e2e_id
    # cabeçalhos customizados não removem o Content-Type JSON padrão
    assert put["headers"]["Content-Type"] == "application/json"
    assert json.loads(put["body"]) == {"a": 1}
    assert patch["method"] == "PATCH"
    assert json.loads(patch["body"]) == [1, 2, 3]
    assert post["headers"]["Content-Type"] == "text/plain"
    assert post["body"] == "raw=text"


def test_webhook_retries_until_success(auth_server: AuthHTTPServer) -> None:
    ok, fail = Recorder(), Recorder()
    sender = WebhookSender(
        f"{auth_server.url}/flaky/2", max_retries=3, success_callback=ok, failure_callback=fail
    )
    response = sender.send({"x": 1})
    assert response is not None
    assert response.json() == {"ok": True, "attempt": 3}
    assert len(auth_server.requests_to("/flaky/2")) == 3
    assert len(fail.calls) == 2
    assert all(isinstance(e, HTTPError) for e in fail.calls)
    assert ok.calls == [response]


def test_webhook_all_retries_fail(http_server, e2e_id: str) -> None:
    url = http_server.add(f"/{e2e_id}/down", "boom", status=503)
    ok, fail = Recorder(), Recorder()
    sender = WebhookSender(url, max_retries=4, success_callback=ok, failure_callback=fail)
    with pytest.raises(HTTPError) as excinfo:
        sender.send({"x": 1})
    assert excinfo.value.response.status_code == 503
    assert len(http_server.requests) == 4
    assert len(fail.calls) == 4
    assert ok.calls == []


def test_webhook_not_found_route_is_failure(http_server, e2e_id: str) -> None:
    http_server.add(f"/{e2e_id}/other", "x")
    sender = WebhookSender(f"{http_server.url}/{e2e_id}/missing", max_retries=2)
    with pytest.raises(HTTPError):
        sender.send({})
    assert [r["path"] for r in http_server.requests] == [f"/{e2e_id}/missing"] * 2


def test_webhook_zero_retries_still_sends_once(http_server, e2e_id: str) -> None:
    url = http_server.add(f"/{e2e_id}/hook", "ok")
    response = WebhookSender(url, max_retries=0).send({"once": True})
    assert response is not None and response.status_code == 200
    assert len(http_server.requests) == 1


@pytest.mark.parametrize("bad_url", ["not a url", "/relative/path", "http://", ""])
def test_webhook_invalid_url(bad_url: str) -> None:
    fail = Recorder()
    sender = WebhookSender(bad_url, failure_callback=fail)
    assert sender.validate_url() is False
    start = time.monotonic()
    with pytest.raises(InvalidURL):
        sender.send({"x": 1})
    # InvalidURL também é RequestException e ValueError (compatível com quem já tratava)
    assert issubclass(InvalidURL, RequestException) and issubclass(InvalidURL, ValueError)
    assert fail.calls == []  # nenhuma tentativa de rede
    assert time.monotonic() - start < 1


def test_webhook_connection_refused(http_server) -> None:
    # porta que acabou de ser liberada: conexão recusada, sem internet
    url = http_server.add("/gone", "x")
    http_server.close()
    fail = Recorder()
    sender = WebhookSender(url, timeout=1, max_retries=2, failure_callback=fail)
    with pytest.raises(RequestsConnectionError):
        sender.send({})
    assert len(fail.calls) == 2


def test_webhook_timeout_then_doubling_succeeds(auth_server: AuthHTTPServer) -> None:
    fail, ok = Recorder(), Recorder()
    # 1ª tentativa: timeout 1s < 1.5s de atraso -> Timeout; 2ª: timeout 2s -> sucesso
    # (margem de 0.5s para não ficar instável com a máquina carregada)
    sender = WebhookSender(
        f"{auth_server.url}/slow/1.5",
        timeout=1,
        max_retries=2,
        failure_callback=fail,
        success_callback=ok,
    )
    response = sender.send({"slow": True})
    assert response is not None and response.status_code == 200
    assert len(fail.calls) == 1 and isinstance(fail.calls[0], Timeout)
    assert len(ok.calls) == 1
    assert len(auth_server.requests_to("/slow/1.5")) == 2


def test_webhook_timeout_all_attempts(auth_server: AuthHTTPServer) -> None:
    fail = Recorder()
    sender = WebhookSender(
        f"{auth_server.url}/slow/1.5", timeout=0.2, max_retries=2, failure_callback=fail
    )
    with pytest.raises(Timeout):
        sender.send({})
    assert len(fail.calls) == 2
    assert all(isinstance(e, Timeout) for e in fail.calls)


def test_webhook_proxies_are_used(auth_server: AuthHTTPServer, e2e_id: str) -> None:
    # o servidor local faz papel de proxy HTTP: recebe a URL absoluta de destino
    target = f"http://webhook-target.invalid/{e2e_id}"
    sender = WebhookSender(target, max_retries=1, proxies={"http": auth_server.url})
    with pytest.raises(HTTPError):  # o "proxy" responde 404 para a rota desconhecida
        sender.send({"via": "proxy"})
    assert auth_server.log[-1]["path"] == target
    assert json.loads(auth_server.log[-1]["body"]) == {"via": "proxy"}


def test_webhook_echo_body_roundtrip(auth_server: AuthHTTPServer, e2e_id: str) -> None:
    sender = WebhookSender(f"{auth_server.url}/echo")
    payload = {"id": e2e_id, "nested": {"ok": True}, "acentuação": "ç"}
    response = sender.send(payload, method="DELETE")
    assert response is not None
    echoed = response.json()
    assert echoed["method"] == "DELETE"
    assert json.loads(echoed["body"]) == payload
    assert requests.codes.ok == response.status_code
