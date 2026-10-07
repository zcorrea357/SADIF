import pytest

pytestmark = pytest.mark.e2e

import base64  # noqa: E402
import http.server  # noqa: E402
import threading  # noqa: E402
from collections.abc import Iterator  # noqa: E402

import requests  # noqa: E402

from sadif.clientmanager.client_data_manager import ClientManager  # noqa: E402
from sadif.frameworks_drivers.crawler.base_crawler import BaseCrawler  # noqa: E402
from sadif.frameworks_drivers.sadif_yara.yara_crud import YaraCrud  # noqa: E402
from sadif.frameworks_drivers.web.authenticator.basic_auth_strategy import (  # noqa: E402
    BasicAuthStrategy,
)
from sadif.frameworks_drivers.web.authenticator.bearer_auth_strategy import (  # noqa: E402
    BearerAuthStrategy,
)
from sadif.frameworks_drivers.web.session_manager import SessionManager  # noqa: E402
from sadif.modules.crawler.generic import GenericCrawler  # noqa: E402
from sadif.modules.crawler.targeted_crawler import PastebinPLCrawler  # noqa: E402

USERNAME = "analyst"
PASSWORD = "s3cr3t"  # noqa: S105
TOKEN = "tok-e2e-123"  # noqa: S105


def html(*links: str, body: str = "") -> str:
    anchors = "".join(f'<a href="{link}">{link}</a>' for link in links)
    return f"<html><body>{body}{anchors}</body></html>"


def get_paths(server) -> list[str]:
    return [request["path"] for request in server.requests if request["method"] == "GET"]


@pytest.fixture()
def leak_rule(sadif_databases, mongo_client, e2e_id):
    """Registers a client and a Leak YARA rule for it in the isolated YaraRules DB."""
    client_name = f"Acme{e2e_id}"
    assert "criada" in ClientManager(db_client=mongo_client).create_client_collection(
        client_name, "Acme Corp", f"ciid{e2e_id}"
    )
    secret = f"ACME-SECRET-{e2e_id}"
    rule_name = f"{client_name}_Leak_{e2e_id}"
    content = f'rule {rule_name}\n{{\n    strings:\n        $a = "{secret}"\n    condition:\n        $a\n}}\n'
    assert YaraCrud(db_client=mongo_client).insert_rule(client_name, rule_name, content)
    return {"client": client_name, "rule": rule_name, "secret": secret}


@pytest.fixture()
def site(http_server, leak_rule):
    """
    index (0) -> a (1, relative), b (1, absolute), 404 (1), mailto, #fragment
    a (1) -> index (loop), deep (2), leak (2)
    deep (2) -> beyond (3)  -- beyond max depth 2
    """
    url = http_server.url
    http_server.add(
        "/index.html",
        html(
            "a.html",
            f"{url}/b.html",
            "/missing.html",
            "mailto:sec@example.invalid",
            "#top",
            "a.html#section",
        ),
    )
    http_server.add("/a.html", html("index.html", "/deep/deep.html", "leak.html"))
    http_server.add("/b.html", html(f"{url}/index.html", body="<p>nothing here</p>"))
    http_server.add("/missing.html", html("/never.html"), status=404)
    http_server.add("/deep/deep.html", html("../beyond.html"))
    http_server.add("/beyond.html", html(), status=200)
    http_server.add("/never.html", html())
    http_server.add("/leak.html", html(body=f"<pre>password dump {leak_rule['secret']} end</pre>"))
    return url


# ---------------------------------------------------------------- crawl


def test_crawl_respects_depth_loops_errors_and_finds_leak(
    site, http_server, mongo_client, leak_rule
):
    crawler = BaseCrawler(base_url=f"{site}/index.html", depth=2, timeout=5, db_client=mongo_client)
    crawler.crawl(crawler.base_url)

    assert crawler.visited_urls == {
        f"{site}/index.html",
        f"{site}/a.html",
        f"{site}/b.html",
        f"{site}/missing.html",
        f"{site}/deep/deep.html",
        f"{site}/leak.html",
    }
    paths = get_paths(http_server)
    # no revisits (loop index <-> a <-> b, fragment variants)
    assert sorted(paths) == sorted(set(paths))
    # beyond max depth is never requested, nor the links of the 404 page
    assert "/beyond.html" not in paths
    assert "/never.html" not in paths
    assert crawler.error_urls == {f"{site}/missing.html"}

    matches = crawler.get_yara_matches()
    assert len(matches) == 1
    match = matches[0]
    assert match["rule_name"] == leak_rule["rule"]
    assert match["client_match"] == leak_rule["client"]
    assert match["rule_type"] == "Leak"
    assert match["link_match"] == f"{site}/leak.html"
    assert match["yara_match_condition"].identifier == "$a"
    assert match["yara_match_condition"].instances[0].matched_data == leak_rule["secret"].encode()


def test_crawl_depth_zero_only_visits_start(site, http_server, mongo_client):
    crawler = BaseCrawler(base_url=f"{site}/a.html", depth=0, db_client=mongo_client)
    crawler.crawl(crawler.base_url)
    assert crawler.visited_urls == {f"{site}/a.html"}
    assert get_paths(http_server) == ["/a.html"]
    assert crawler.get_yara_matches() == []


def test_crawl_same_url_twice_is_noop(site, http_server, mongo_client):
    crawler = BaseCrawler(base_url=f"{site}/b.html", depth=0, db_client=mongo_client)
    crawler.crawl(crawler.base_url)
    crawler.crawl(crawler.base_url)
    crawler.crawl(f"{site}/b.html#x", current_depth=0)
    assert get_paths(http_server) == ["/b.html"]


def test_crawl_beyond_depth_is_not_requested(site, http_server, mongo_client):
    crawler = BaseCrawler(base_url=f"{site}/a.html", depth=1, db_client=mongo_client)
    crawler.crawl(crawler.base_url, current_depth=2)
    assert crawler.visited_urls == set()
    assert http_server.requests == []


def test_crawl_error_page_is_skipped(site, http_server, mongo_client):
    crawler = BaseCrawler(base_url=f"{site}/missing.html", depth=3, db_client=mongo_client)
    crawler.crawl(crawler.base_url)
    assert crawler.error_urls == {f"{site}/missing.html"}
    assert get_paths(http_server) == ["/missing.html"]


def test_crawl_unreachable_host_is_skipped(sadif_databases, mongo_client):
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/"
    crawler = BaseCrawler(base_url=url, depth=1, timeout=2, db_client=mongo_client)
    crawler.crawl(url)
    assert crawler.visited_urls == {url}
    assert crawler.error_urls == {url}
    assert crawler.get_yara_matches() == []


def test_crawl_non_html_content_is_analyzed_but_not_followed(http_server, mongo_client, leak_rule):
    url = http_server.add(
        "/dump.txt", f'<a href="/x.html">x</a> {leak_rule["secret"]}', content_type="text/plain"
    )
    http_server.add("/x.html", html())
    crawler = BaseCrawler(base_url=url, depth=2, db_client=mongo_client)
    crawler.crawl(url)
    assert get_paths(http_server) == ["/dump.txt"]
    assert [m["link_match"] for m in crawler.get_yara_matches()] == [url]


def test_init_uses_configured_mongodb(sadif_databases, monkeypatch):
    monkeypatch.setenv("SADIF_MONGODB_URL", "mongodb://127.0.0.1:27017")
    crawler = BaseCrawler(base_url="http://127.0.0.1/", depth=1)
    try:
        crawler.client.admin.command("ping")  # address só existe após conectar
        assert crawler.client.address == ("127.0.0.1", 27017)
        assert crawler.yara_compiler.client is crawler.client
        assert crawler.yara_compiler.db.name == sadif_databases["MONGODB_DATABASE_YARA"]
        assert crawler.module_name == "BaseCrawler"
        assert crawler.get_yara_matches() == []
    finally:
        crawler.client.close()


def test_generic_crawler_alias(sadif_databases, mongo_client):
    assert GenericCrawler is BaseCrawler


# ---------------------------------------------------------------- links


def test_extract_and_normalize_links(sadif_databases, mongo_client):
    crawler = BaseCrawler(base_url="http://h.test/dir/page.html", depth=1, db_client=mongo_client)
    content = html(
        "other.html",
        "../up.html",
        "/root.html",
        "https://abs.test/x?q=1",
        "other.html#frag",
        "#only",
        "mailto:a@b.c",
        "javascript:void(0)",
        "  spaced.html ",
    ).encode()
    links = crawler.extract_links(content, "http://h.test/dir/page.html")
    assert links == {
        "http://h.test/dir/other.html",
        "http://h.test/up.html",
        "http://h.test/root.html",
        "https://abs.test/x?q=1",
        "http://h.test/dir/spaced.html",
    }
    assert crawler.extract_links("<html>no links</html>", "http://h.test/") == set()
    assert crawler.normalize_link("https://abs.test/a#b", "http://h.test/") == "https://abs.test/a"
    assert crawler.normalize_link("a", "http://h.test/d/") == "http://h.test/d/a"


# ---------------------------------------------------------------- analyze_content


def test_analyze_content_matches_registered_client_rule(mongo_client, leak_rule):
    crawler = BaseCrawler(base_url="http://h.test/", depth=0, db_client=mongo_client)
    results = crawler.analyze_content(f"xx {leak_rule['secret']} yy", "http://h.test/p")
    assert len(results) == 1
    assert results[0]["client_match"] == leak_rule["client"]
    assert results[0]["rule_type"] == "Leak"
    assert results[0]["link_match"] == "http://h.test/p"
    assert crawler.get_yara_matches() == results
    # no match / empty text
    assert crawler.analyze_content("nothing", "http://h.test/q") == []
    assert crawler.analyze_content("", "http://h.test/r") == []
    assert len(crawler.get_yara_matches()) == 1


def test_analyze_content_ignores_unregistered_client(
    sadif_databases, mongo_client, leak_rule, e2e_id
):
    # rule stored for a client that is not registered in ClientManager
    db = mongo_client[sadif_databases["MONGODB_DATABASE_YARA"]]
    db[f"Client_Ghost{e2e_id}"].insert_one(
        {
            "rule_name": f"Ghost{e2e_id}_Leak",
            "rule_content": f'rule Ghost{e2e_id}_Leak {{ strings: $a = "GHOST{e2e_id}" condition: $a }}',
        }
    )
    crawler = BaseCrawler(base_url="http://h.test/", depth=0, db_client=mongo_client)
    assert crawler.analyze_content(f"GHOST{e2e_id}", "http://h.test/") == []


def test_analyze_content_without_rules(sadif_databases, mongo_client):
    crawler = BaseCrawler(base_url="http://h.test/", depth=0, db_client=mongo_client)
    assert crawler.analyze_content("anything", "http://h.test/") == []


# ---------------------------------------------------------------- authentication


class _AuthHandler(http.server.BaseHTTPRequestHandler):
    expected: dict[str, str]
    log: list[dict]

    def do_GET(self) -> None:  # noqa: N802
        auth = self.headers.get("Authorization")
        self.log.append({"path": self.path, "auth": auth})
        expected = self.expected.get(self.path.split("/")[1])
        if auth != expected:
            body, status = b"denied", 401
        elif self.path.endswith("/start"):
            body, status = b'<html><a href="next">n</a></html>', 200
        else:
            body, status = self.server.secret.encode(), 200  # type: ignore[attr-defined]
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture()
def auth_server(leak_rule) -> Iterator[tuple[str, list[dict]]]:
    basic = "Basic " + base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
    handler = type(
        "H", (_AuthHandler,), {"expected": {"basic": basic, "bearer": f"Bearer {TOKEN}"}, "log": []}
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.secret = f"leaked {leak_rule['secret']}"  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", handler.log
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize(
    ("kind", "strategy"),
    [("basic", BasicAuthStrategy(USERNAME, PASSWORD)), ("bearer", BearerAuthStrategy(TOKEN))],
)
def test_crawl_with_session_manager_session(auth_server, mongo_client, leak_rule, kind, strategy):
    url, log = auth_server
    start = f"{url}/{kind}/start"

    anonymous = BaseCrawler(base_url=start, depth=1, db_client=mongo_client)
    anonymous.crawl(start)
    assert anonymous.error_urls == {start}
    assert anonymous.get_yara_matches() == []

    manager = SessionManager()
    crawler = BaseCrawler(base_url=start, depth=1, db_client=mongo_client)
    crawler.session = manager.create_session(strategy)
    crawler.crawl(start)
    manager.close_all_sessions()

    assert crawler.visited_urls == {start, f"{url}/{kind}/next"}
    assert crawler.error_urls == set()
    assert [m["link_match"] for m in crawler.get_yara_matches()] == [f"{url}/{kind}/next"]
    authorized = [entry for entry in log if entry["auth"]]
    assert {entry["path"] for entry in authorized} == {f"/{kind}/start", f"/{kind}/next"}


@pytest.mark.parametrize(
    ("kind", "details"),
    [
        ("basic", {"username": USERNAME, "password": PASSWORD}),
        ("basic", {"type": "basic", "username": USERNAME, "password": PASSWORD}),
        ("bearer", {"token": TOKEN}),
        ("bearer", {"type": "Bearer", "token": TOKEN}),
    ],
)
def test_authenticate_configures_session(auth_server, mongo_client, kind, details):
    url, _log = auth_server
    crawler = BaseCrawler(base_url=f"{url}/{kind}/start", depth=1, db_client=mongo_client)
    crawler.authenticate(details)
    crawler.crawl(crawler.base_url)
    assert crawler.error_urls == set()
    assert len(crawler.visited_urls) == 2


def test_authenticate_digest_sets_digest_auth(sadif_databases, mongo_client):
    crawler = BaseCrawler(base_url="http://h.test/", depth=1, db_client=mongo_client)
    crawler.authenticate({"type": "digest", "username": USERNAME, "password": PASSWORD})
    assert isinstance(crawler.session.auth, requests.auth.HTTPDigestAuth)


@pytest.mark.parametrize(
    "details",
    [{}, {"username": USERNAME}, {"type": "bearer"}, {"type": "ntlm", "token": TOKEN}],
)
def test_authenticate_invalid_details(sadif_databases, mongo_client, details):
    crawler = BaseCrawler(base_url="http://h.test/", depth=1, db_client=mongo_client)
    with pytest.raises(ValueError, match="auth_details"):
        crawler.authenticate(details)
    assert crawler.session.auth is None
    assert "Authorization" not in crawler.session.headers


# ---------------------------------------------------------------- PastebinPLCrawler


@pytest.fixture()
def pastebin(http_server, leak_rule):
    http_server.add(
        "/lists",
        html(
            "/view/aaa",
            "/view/aaa",
            "/view/bbb",
            "/view/gone",
            "/lists?page=2",
            "/about",
            body="<h1>Recent pastes</h1>",
        ),
    )
    http_server.add("/view/aaa", f"<html><pre>creds {leak_rule['secret']}</pre></html>")
    http_server.add("/view/bbb", "<html><pre>hello world</pre></html>")
    http_server.add("/view/gone", "removed", status=404)
    http_server.add("/about", html())
    return f"{http_server.url}/lists"


def test_pastebin_crawl_analyzes_pastes(pastebin, http_server, mongo_client, leak_rule):
    crawler = PastebinPLCrawler(base_url=pastebin, depth=0, db_client=mongo_client)
    crawler.crawl(crawler.base_url)

    host = http_server.url
    assert [p["url"] for p in crawler.found_pastes] == [
        f"{host}/view/aaa",
        f"{host}/view/bbb",
        f"{host}/view/gone",
    ]
    assert crawler.found_pastes[0]["title"] == "/view/aaa"
    paths = get_paths(http_server)
    assert sorted(paths) == ["/lists", "/view/aaa", "/view/bbb", "/view/gone"]
    assert crawler.error_urls == {f"{host}/view/gone"}
    matches = crawler.get_yara_matches()
    assert len(matches) == 1
    assert matches[0]["link_match"] == f"{host}/view/aaa"
    assert matches[0]["client_match"] == leak_rule["client"]
    assert matches[0]["rule_type"] == "Leak"
    assert list(crawler.paste_analysis) == [f"{host}/view/aaa"]


def test_pastebin_follows_pagination_within_depth(pastebin, http_server, mongo_client):
    http_server.routes["/lists"] = (
        200,
        "text/html",
        html("/view/aaa", "/lists?page=2", "/about"),
    )
    crawler = PastebinPLCrawler(base_url=pastebin, depth=1, db_client=mongo_client)
    crawler.crawl(crawler.base_url)
    paths = get_paths(http_server)
    # page 2 serves the same list: its pastes are not analyzed twice
    assert sorted(paths) == ["/lists", "/lists?page=2", "/view/aaa"]
    assert "/about" not in paths
    assert len(crawler.found_pastes) == 1
    assert len(crawler.get_yara_matches()) == 1


def test_pastebin_extract_pastes_and_errors(pastebin, http_server, mongo_client):
    crawler = PastebinPLCrawler(base_url=pastebin, depth=1, db_client=mongo_client)
    assert crawler.extract_pastes(b"<html></html>", pastebin) == []
    assert crawler.analyze_paste(f"{http_server.url}/view/gone") is None
    assert crawler.analyze_paste(f"{http_server.url}/view/bbb") == []

    http_server.routes["/lists"] = (500, "text/html", html("/view/aaa"))
    crawler.crawl(crawler.base_url)
    assert crawler.error_urls == {f"{http_server.url}/view/gone", pastebin}
    assert crawler.found_pastes == []
    assert "/view/aaa" not in get_paths(http_server)


def test_pastebin_defaults(sadif_databases, mongo_client):
    crawler = PastebinPLCrawler(db_client=mongo_client)
    assert crawler.base_url == "https://pastebin.pl/lists"
    assert crawler.depth == 1
    assert crawler.timeout == 10
    assert crawler.found_pastes == []


def test_pastebin_extract_list_pages_same_host_and_path(pastebin, http_server, mongo_client):
    crawler = PastebinPLCrawler(base_url=pastebin, depth=1, db_client=mongo_client)
    host = http_server.url
    content = html(
        "/lists?page=2",
        "/lists/?page=3",
        "/lists#top",
        "/view/aaa",
        "/about",
        "http://other.test/lists?page=2",
        "mailto:a@b.c",
    ).encode()
    assert crawler.extract_list_pages(content, pastebin) == {
        f"{host}/lists?page=2",
        f"{host}/lists/?page=3",
        f"{host}/lists",
    }


def test_pastebin_unreachable_list_and_paste(sadif_databases, mongo_client):
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/lists"
    crawler = PastebinPLCrawler(base_url=url, depth=1, timeout=2, db_client=mongo_client)
    crawler.crawl(url)
    assert crawler.visited_urls == {url}
    assert crawler.error_urls == {url}
    assert crawler.found_pastes == []
    paste = f"http://127.0.0.1:{port}/view/zzz"
    assert crawler.analyze_paste(paste) is None
    assert crawler.error_urls == {url, paste}
    assert crawler.get_yara_matches() == []


def test_pastebin_recrawl_and_depth_exceeded_are_noops(pastebin, http_server, mongo_client):
    crawler = PastebinPLCrawler(base_url=pastebin, depth=0, db_client=mongo_client)
    crawler.crawl(pastebin, current_depth=1)
    assert http_server.requests == []
    crawler.crawl(pastebin)
    first = sorted(get_paths(http_server))
    crawler.crawl(pastebin)
    crawler.crawl(f"{pastebin}#again")
    assert sorted(get_paths(http_server)) == first
    assert len(crawler.found_pastes) == 3
    assert len(crawler.get_yara_matches()) == 1
