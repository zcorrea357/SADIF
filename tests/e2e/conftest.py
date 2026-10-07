"""
Fixtures dos testes end-to-end (tests/e2e).

Os testes e2e usam a infraestrutura local real (make infra-up / infra-up-all e
make examples-bootstrap) e são pulados automaticamente quando ela não está no ar.
Cada teste usa bancos MongoDB próprios (prefixo único via variáveis SADIF_*), então
os testes podem rodar em paralelo sem interferir uns nos outros nem nos exemplos.
"""

import functools
import http.server
import os
import subprocess
import threading
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient
from pymongo.errors import PyMongoError

ROOT = Path(__file__).resolve().parents[2]
DATABASE_KEYS = (
    "MONGODB_DATABASE_CLIENTS",
    "MONGODB_DATABASE_YARA",
    "MONGODB_DATABASE_CRAWLER",
    "MONGODB_DATABASE_MODULES_MANAGER",
)


def _load_dotenv() -> None:
    """Carrega o .env da raiz sem sobrescrever variáveis já definidas."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()
for _host in ("localhost", "127.0.0.1"):
    if _host not in os.environ.get("NO_PROXY", ""):
        os.environ["NO_PROXY"] = ",".join(filter(None, [os.environ.get("NO_PROXY"), _host]))
os.environ["no_proxy"] = os.environ["NO_PROXY"]

MONGODB_URL = os.environ.get("SADIF_MONGODB_URL", "mongodb://localhost:27017")
THEHIVE_URL = os.environ.get("SADIF_THEHIVE", "http://localhost:9000/api")


@functools.cache
def _mongo_available() -> bool:
    try:
        MongoClient(MONGODB_URL, serverSelectionTimeoutMS=2000).admin.command("ping")
        return True
    except PyMongoError:
        return False


@functools.cache
def _thehive_available() -> bool:
    if not os.environ.get("SADIF_THEHIVE_API_SERVICE"):
        return False
    try:
        return requests.get(f"{THEHIVE_URL}/status", timeout=5).ok
    except requests.RequestException:
        return False


@pytest.fixture()
def e2e_id() -> str:
    """Identificador único do teste, para nomes de bancos, casos, URLs etc."""
    return f"e2e{uuid.uuid4().hex[:10]}"


@pytest.fixture()
def mongo_client() -> Iterator[MongoClient]:
    """MongoClient real (pula o teste se o MongoDB local não estiver no ar)."""
    if not _mongo_available():
        pytest.skip(f"MongoDB indisponível em {MONGODB_URL} (rode 'make infra-up')")
    client = MongoClient(MONGODB_URL)
    yield client
    client.close()


@pytest.fixture()
def sadif_databases(
    mongo_client: MongoClient, e2e_id: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[dict[str, str]]:
    """
    Isola o teste em bancos MongoDB próprios (SADIF_MONGODB_DATABASE_* = <e2e_id>_<nome>)
    e os apaga ao final. Retorna {chave_de_config: nome_do_banco}.
    """
    databases = {key: f"{e2e_id}_{key.rsplit('_', 1)[-1].title()}" for key in DATABASE_KEYS}
    for key, name in databases.items():
        monkeypatch.setenv(f"SADIF_{key}", name)
    monkeypatch.setenv("SADIF_MONGODB_URL", MONGODB_URL)
    yield databases
    for name in databases.values():
        mongo_client.drop_database(name)


@pytest.fixture()
def requires_thehive():
    """Pula o teste quando o TheHive local não está acessível."""
    if not _thehive_available():
        pytest.skip(
            f"TheHive indisponível em {THEHIVE_URL} ou sem SADIF_THEHIVE_API_SERVICE "
            "(rode 'make infra-up-all' e 'make examples-bootstrap')"
        )


@pytest.fixture()
def thehive_session():
    """Sessão autenticada no TheHive local (pula se indisponível ou sem API key)."""
    # Import tardio: importar o sadif ao carregar o conftest desligaria o typeguard
    # (o plugin precisa instrumentar o pacote antes do primeiro import)
    from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
        SessionThehive,
    )

    if not _thehive_available():
        pytest.skip(
            f"TheHive indisponível em {THEHIVE_URL} ou sem SADIF_THEHIVE_API_SERVICE "
            "(rode 'make infra-up-all' e 'make examples-bootstrap')"
        )
    session = SessionThehive(base_url=THEHIVE_URL)
    session.set_api_key(os.environ["SADIF_THEHIVE_API_SERVICE"])
    return session


@pytest.fixture()
def local_git_repo(tmp_path: Path) -> Callable[[dict[str, str]], str]:
    """
    Fábrica de repositórios git locais: local_git_repo({"caminho/arquivo": "conteúdo"})
    cria e commita os arquivos e retorna o caminho, utilizável como URL pelo GitManager.
    """
    counter = iter(range(1_000_000))

    def make(files: dict[str, str]) -> str:
        repo = tmp_path / f"repo{next(counter)}"
        for relative_path, content in files.items():
            file_path = repo / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        git = ["git", "-c", "user.name=e2e", "-c", "user.email=e2e@localhost", "-C", str(repo)]
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run([*git, "init", "-q", "-b", "main"], check=True)  # noqa: S603
        subprocess.run([*git, "add", "-A"], check=True)  # noqa: S603
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "fixture"], check=True)  # noqa: S603
        return str(repo)

    return make


class _Handler(http.server.BaseHTTPRequestHandler):
    routes: dict[str, tuple[int, str, str]]
    dynamic_routes: dict[str, Callable]
    requests_log: list[dict]

    def _respond(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body_bytes = self.rfile.read(length) if length else b""
        req = {
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers),
            "body": body_bytes.decode("utf-8", "replace") if body_bytes else "",
        }
        self.requests_log.append(req)
        clean_path = self.path.split("?", 1)[0]

        if clean_path in self.dynamic_routes:
            status, content_type, body = self.dynamic_routes[clean_path](req)
        else:
            status, content_type, body = self.routes.get(
                clean_path, (404, "text/plain", "not found")
            )
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _respond

    def log_message(self, *args) -> None:  # silencia o log padrão no stderr
        pass


class LocalHTTPServer:
    """Servidor HTTP local para os testes: rotas configuráveis e registro das requisições."""

    def __init__(self) -> None:
        self.routes: dict[str, tuple[int, str, str]] = {}
        self.dynamic_routes: dict[str, Callable] = {}
        self.requests: list[dict] = []
        handler = type(
            "Handler",
            (_Handler,),
            {
                "routes": self.routes,
                "dynamic_routes": self.dynamic_routes,
                "requests_log": self.requests,
            },
        )
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def add(self, path: str, body: str, status: int = 200, content_type: str = "text/html") -> str:
        """Registra uma rota e retorna a URL completa dela."""
        self.routes[path] = (status, content_type, body)
        return f"{self.url}{path}"

    def add_handler(self, path: str, handler: Callable) -> str:
        """Registra uma rota dinâmica (handler recebe o request dict e retorna (status, content_type, body))."""
        self.dynamic_routes[path] = handler
        return f"{self.url}{path}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture()
def http_server() -> Iterator[LocalHTTPServer]:
    """Servidor HTTP local (sem internet): http_server.add('/p', '<html>...</html>')."""
    server = LocalHTTPServer()
    yield server
    server.close()
