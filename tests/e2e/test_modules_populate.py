import pytest

pytestmark = pytest.mark.e2e

import base64  # noqa: E402
import hashlib  # noqa: E402
import http.server  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402
import ssl  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from pymongo.errors import WriteError  # noqa: E402

from sadif.config.sadif_config import SadifConfiguration  # noqa: E402
from sadif.frameworks_drivers.modules_manager import ModuleDatabaseManager  # noqa: E402
from sadif.modules.populate.url_to_dbs.ransomwhatimport import (  # noqa: E402
    RansomwhatImport,
    is_valid_v3_onion,
)

GIT_IDENTITY = ["-c", "user.name=e2e", "-c", "user.email=e2e@localhost"]
URL_SCHEMA = {
    "bsonType": "object",
    "required": ["url"],
    "properties": {"url": {"bsonType": "string", "description": "obrigatório"}},
}
GROUPS_PATH = "/ransomwatch/groups.json"


# --------------------------------------------------------------------------- helpers


def _git(*args: str, cwd: str | Path | None = None) -> str:
    cmd = ["git", *GIT_IDENTITY]
    if cwd is not None:
        cmd += ["-C", str(cwd)]
    result = subprocess.run([*cmd, *args], check=True, capture_output=True, text=True)  # noqa: S603
    return result.stdout.strip()


def make_v3_address(seed: str, *, version: int = 3, bad_checksum: bool = False) -> str:
    """Builds a deterministic v3 onion address (valid unless told otherwise)."""
    pubkey = hashlib.sha256(seed.encode()).digest()
    checksum = hashlib.sha3_256(b".onion checksum" + pubkey + bytes([version])).digest()[:2]
    if bad_checksum:
        checksum = bytes([checksum[0] ^ 0xFF, checksum[1]])
    label = base64.b32encode(pubkey + checksum + bytes([version])).decode().lower()
    return f"{label}.onion"


def groups_json(locations: list[list[str]]) -> str:
    """groups.json in the joshhighet/ransomwatch shape (one group per list of fqdns)."""
    groups = []
    for index, fqdns in enumerate(locations):
        groups.append(
            {
                "name": f"group{index}",
                "captcha": False,
                "parser": True,
                "javascript_render": False,
                "meta": None,
                "locations": [
                    {
                        "fqdn": fqdn,
                        "title": f"Group {index}",
                        "version": 3 if len(fqdn) == 62 else 2,
                        "slug": f"http://{fqdn}/blog",
                        "available": True,
                        "delay": None,
                        "updated": "2024-03-01 10:00:00.000000",
                        "lastscrape": "2024-03-01 10:00:00.000000",
                        "enabled": True,
                    }
                    for fqdn in fqdns
                ],
                "profile": [],
            }
        )
    return json.dumps(groups, indent=2)


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic identity for the commits made by GitManager."""
    for var, value in {
        "GIT_AUTHOR_NAME": "sadif-e2e",
        "GIT_AUTHOR_EMAIL": "sadif-e2e@localhost",
        "GIT_COMMITTER_NAME": "sadif-e2e",
        "GIT_COMMITTER_EMAIL": "sadif-e2e@localhost",
    }.items():
        monkeypatch.setenv(var, value)


@pytest.fixture()
def bare_repo(tmp_path: Path, e2e_id: str) -> Callable[[dict[str, str] | None], Path]:
    """Seeded bare repository (branch main): usable as SADIF_DATA_MODULES_URL and pushable."""
    counter = iter(range(1_000_000))

    def make(files: dict[str, str] | None = None) -> Path:
        files = files if files is not None else {"README.md": f"modules data {e2e_id}"}
        number = next(counter)
        bare = tmp_path / f"{e2e_id}_{number}.git"
        _git("init", "-q", "--bare", "-b", "main", str(bare))
        seed = tmp_path / f"seed_{number}"
        _git("clone", "-q", str(bare), str(seed))
        _git("checkout", "-q", "-B", "main", cwd=seed)
        for rel, content in files.items():
            path = seed / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        _git("add", "-A", cwd=seed)
        _git("commit", "-q", "--allow-empty", "-m", "seed", cwd=seed)
        _git("push", "-q", "origin", "main", cwd=seed)
        return bare

    return make


def read_repo(bare: Path, tmp_path: Path) -> Path:
    """Fresh clone of ``bare`` to inspect what was pushed."""
    target = tmp_path / f"inspect_{len(list(tmp_path.glob('inspect_*')))}"
    _git("clone", "-q", str(bare), str(target))
    return target


@pytest.fixture()
def importers() -> Iterator[Callable[[MongoClient], RansomwhatImport]]:
    created: list[RansomwhatImport] = []

    def make(client: MongoClient) -> RansomwhatImport:
        importer = RansomwhatImport(db_client=client)
        created.append(importer)
        return importer

    yield make
    for importer in created:
        importer.git_manager.cleanup()


@pytest.fixture()
def ransomwhat_env(
    sadif_databases: dict[str, str],
    http_server,
    bare_repo,
    monkeypatch: pytest.MonkeyPatch,
    e2e_id: str,
) -> dict:
    """Points the Ransomwhat URL to the local HTTP server and the data repo to a bare repo."""
    v3_a = make_v3_address(f"{e2e_id}-a")
    v3_b = make_v3_address(f"{e2e_id}-b")
    v3_c = make_v3_address(f"{e2e_id}-c")
    body = groups_json(
        [
            [v3_a, "lockbitapt2yfbt7.onion"],  # v3 + v2
            [v3_b, v3_a],  # duplicate across groups
            [v3_c.upper()],  # upper-case address is normalized
            [make_v3_address(f"{e2e_id}-x", bad_checksum=True)],  # invalid checksum
            [make_v3_address(f"{e2e_id}-y", version=2)],  # wrong version byte
            ["a" * 60 + ".onion"],  # too long: must not yield a 56-char suffix
            ["example.com"],
        ]
    )
    url = http_server.add(GROUPS_PATH, body, content_type="application/json")
    bare = bare_repo()
    monkeypatch.setenv("SADIF_MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_URL", url)
    monkeypatch.setenv("SADIF_SADIF_DATA_MODULES_URL", str(bare))
    monkeypatch.setenv("SADIF_GIT_REPO_TOKEN", "")
    expected = sorted(f"http://{address}" for address in (v3_a, v3_b, v3_c))
    return {
        "db": sadif_databases["MONGODB_DATABASE_MODULES_MANAGER"],
        "url": url,
        "bare": bare,
        "expected": expected,
    }


def _closed_port_url() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}/groups.json"


# --------------------------------------------------------- ModuleDatabaseManager


def test_manager_uses_isolated_database_and_configured_url(
    sadif_databases, mongo_client, monkeypatch: pytest.MonkeyPatch
):
    manager = ModuleDatabaseManager(db_client=mongo_client)
    assert manager.db_name == sadif_databases["MONGODB_DATABASE_MODULES_MANAGER"]
    assert manager.db.name == manager.db_name
    assert manager.client is mongo_client

    # without a client, the configured SADIF_MONGODB_URL is used (not a hard-coded localhost)
    monkeypatch.setenv("SADIF_MONGODB_URL", "mongodb://127.0.0.1:27017/")
    default = ModuleDatabaseManager()
    try:
        assert default.client.admin.command("ping")["ok"] == 1
        default.client.admin.command("ping")  # address só existe após conectar
        assert default.client.address == ("127.0.0.1", 27017)
    finally:
        default.client.close()


def test_create_module_collection_enforces_schema_and_unique_index(sadif_databases, mongo_client):
    manager = ModuleDatabaseManager(db_client=mongo_client)
    manager.create_module_collection("leaks", URL_SCHEMA)

    db = mongo_client[sadif_databases["MONGODB_DATABASE_MODULES_MANAGER"]]
    assert "module_leaks" in db.list_collection_names()
    options = db["module_leaks"].options()
    assert options["validator"] == {"$jsonSchema": URL_SCHEMA}
    assert options["validationLevel"] == "strict"
    indexes = db["module_leaks"].index_information()
    assert any(info["key"] == [("url", 1)] and info.get("unique") for info in indexes.values())

    # documents rejected by the MongoDB validator itself
    with pytest.raises(WriteError):
        db["module_leaks"].insert_one({"url": 42})

    inserted_id = manager.insert_document("leaks", {"url": "http://a.example"})
    assert inserted_id is not None
    assert manager.insert_document("leaks", {"url": 42}) is None
    assert manager.insert_document("leaks", {"name": "missing url"}) is None
    stored = list(db["module_leaks"].find({}, {"_id": 0}))
    assert stored == [{"url": "http://a.example"}]
    assert db["module_leaks"].find_one({"_id": inserted_id})["url"] == "http://a.example"


def test_create_module_collection_without_required_creates_no_index(sadif_databases, mongo_client):
    manager = ModuleDatabaseManager(db_client=mongo_client)
    manager.create_module_collection("free", {"bsonType": "object"})
    db = mongo_client[sadif_databases["MONGODB_DATABASE_MODULES_MANAGER"]]
    assert list(db["module_free"].index_information()) == ["_id_"]
    assert manager.insert_document("free", {"anything": 1}) is not None
    assert manager.insert_document("free", {"anything": 2}) is not None
    assert db["module_free"].count_documents({}) == 2


def test_create_module_collection_existing_collection_is_kept(sadif_databases, mongo_client):
    manager = ModuleDatabaseManager(db_client=mongo_client)
    manager.create_module_collection("leaks", URL_SCHEMA)
    manager.insert_document("leaks", {"url": "http://keep.example"})

    other_schema = {"bsonType": "object", "required": ["name"]}
    manager.create_module_collection("leaks", other_schema)

    db = mongo_client[sadif_databases["MONGODB_DATABASE_MODULES_MANAGER"]]
    assert db["module_leaks"].options()["validator"] == {"$jsonSchema": URL_SCHEMA}
    assert "name_1" not in db["module_leaks"].index_information()
    assert list(db["module_leaks"].find({}, {"_id": 0})) == [{"url": "http://keep.example"}]


def test_create_module_collection_invalid_schema_is_reported_not_created(
    sadif_databases, mongo_client
):
    manager = ModuleDatabaseManager(db_client=mongo_client)
    manager.create_module_collection("broken", {"bsonType": "not-a-bson-type"})
    db = mongo_client[sadif_databases["MONGODB_DATABASE_MODULES_MANAGER"]]
    assert "module_broken" not in db.list_collection_names()


def test_insert_document_duplicates(sadif_databases, mongo_client):
    manager = ModuleDatabaseManager(db_client=mongo_client)
    manager.create_module_collection("leaks", URL_SCHEMA)
    db = mongo_client[sadif_databases["MONGODB_DATABASE_MODULES_MANAGER"]]

    first = manager.insert_document("leaks", {"url": "http://dup.example", "group": "x"})
    assert first is not None
    # identical document: skipped by the lookup before inserting
    assert manager.insert_document("leaks", {"url": "http://dup.example", "group": "x"}) is None
    # same unique key with other fields: rejected by the unique index (DuplicateKeyError)
    assert manager.insert_document("leaks", {"url": "http://dup.example", "group": "y"}) is None
    assert list(db["module_leaks"].find({}, {"_id": 0})) == [
        {"url": "http://dup.example", "group": "x"}
    ]


def test_find_update_delete_list(sadif_databases, mongo_client):
    manager = ModuleDatabaseManager(db_client=mongo_client)
    manager.create_module_collection("leaks", URL_SCHEMA)
    db = mongo_client[sadif_databases["MONGODB_DATABASE_MODULES_MANAGER"]]
    for index in range(3):
        manager.insert_document(
            "leaks", {"url": f"http://site{index}.example", "group": "even" if index % 2 else "odd"}
        )

    found = manager.find_documents("leaks", {"group": "odd"})
    assert sorted(doc["url"] for doc in found) == ["http://site0.example", "http://site2.example"]
    assert all("_id" in doc for doc in found)
    assert manager.find_documents("leaks", {"group": "none"}) == []
    assert manager.find_documents("missing_module", {}) == []
    # invalid query operator: error is logged and an empty list is returned
    assert manager.find_documents("leaks", {"$invalid": 1}) == []

    # plain field values are wrapped in $set
    assert manager.update_document("leaks", {"url": "http://site0.example"}, {"status": "up"}) == 1
    assert db["module_leaks"].find_one({"url": "http://site0.example"})["status"] == "up"
    # unchanged value: nothing modified
    assert manager.update_document("leaks", {"url": "http://site0.example"}, {"status": "up"}) == 0
    # full update document (as described in the docstring)
    assert (
        manager.update_document(
            "leaks", {"url": "http://site0.example"}, {"$unset": {"status": ""}, "$set": {"n": 1}}
        )
        == 1
    )
    updated = db["module_leaks"].find_one({"url": "http://site0.example"}, {"_id": 0})
    assert updated == {"url": "http://site0.example", "group": "odd", "n": 1}
    # not found
    assert manager.update_document("leaks", {"url": "http://nope.example"}, {"n": 2}) == 0
    # update violating the schema is rejected by MongoDB and the document is unchanged
    assert manager.update_document("leaks", {"url": "http://site1.example"}, {"url": 5}) is None
    assert db["module_leaks"].count_documents({"url": "http://site1.example"}) == 1
    # update violating the unique index is rejected
    assert (
        manager.update_document(
            "leaks", {"url": "http://site1.example"}, {"url": "http://site2.example"}
        )
        is None
    )
    assert db["module_leaks"].count_documents({"url": "http://site2.example"}) == 1

    assert manager.delete_document("leaks", {"url": "http://site1.example"}) == 1
    assert db["module_leaks"].count_documents({"url": "http://site1.example"}) == 0
    assert manager.delete_document("leaks", {"url": "http://site1.example"}) == 0

    listed = manager.list_module_data("leaks")
    assert sorted(listed, key=lambda doc: doc["url"]) == [
        {"url": "http://site0.example", "group": "odd", "n": 1},
        {"url": "http://site2.example", "group": "odd"},
    ]
    assert manager.list_module_data("missing_module") == []


def test_get_connection_reraises_errors(sadif_databases, mongo_client):
    manager = ModuleDatabaseManager(db_client=mongo_client)
    with manager.get_connection() as db:
        assert db.name == sadif_databases["MONGODB_DATABASE_MODULES_MANAGER"]
    with pytest.raises(RuntimeError, match="boom"), manager.get_connection():
        raise RuntimeError("boom")  # noqa: EM101


# ------------------------------------------------------------- RansomwhatImport


def test_is_valid_v3_onion():
    assert is_valid_v3_onion(make_v3_address("ok"))
    assert is_valid_v3_onion(make_v3_address("ok").upper())
    assert not is_valid_v3_onion(make_v3_address("ok", bad_checksum=True))
    assert not is_valid_v3_onion(make_v3_address("ok", version=2))
    assert not is_valid_v3_onion("lockbitapt2yfbt7.onion")
    assert not is_valid_v3_onion("1" * 56 + ".onion")


def test_init_creates_ransomwhat_collection(ransomwhat_env, mongo_client, importers):
    importer = importers(mongo_client)
    db = mongo_client[ransomwhat_env["db"]]
    collection = f"module_{importer.ransomwhat_module_name}"
    assert collection in db.list_collection_names()
    assert db[collection].options()["validator"] == {
        "$jsonSchema": SadifConfiguration().get_configuration(
            "MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_JSON_SCHEMA"
        )
    }
    assert importer.ransomwhat_url == ransomwhat_env["url"]
    assert importer.git_url == str(ransomwhat_env["bare"])
    # second instance on the same database: collection already exists, nothing breaks
    importers(mongo_client)
    assert db.list_collection_names().count(collection) == 1


def test_extract_v3_urls_filters_and_deduplicates(
    ransomwhat_env, mongo_client, importers, http_server
):
    importer = importers(mongo_client)
    urls = importer.extract_v3_urls()
    assert urls == ransomwhat_env["expected"]
    assert [r["path"] for r in http_server.requests] == [GROUPS_PATH]
    assert http_server.requests[0]["method"] == "GET"


def test_execute_stores_urls_without_duplicates(ransomwhat_env, mongo_client, importers):
    importer = importers(mongo_client)
    importer.execute()
    collection = mongo_client[ransomwhat_env["db"]][f"module_{importer.ransomwhat_module_name}"]
    stored = sorted(doc["url"] for doc in collection.find())
    assert stored == ransomwhat_env["expected"]

    importer.execute()
    assert collection.count_documents({}) == len(ransomwhat_env["expected"])
    assert sorted(d["url"] for d in importer.list_data()) == ransomwhat_env["expected"]
    assert all(set(doc) == {"url"} for doc in importer.list_data())


@pytest.mark.parametrize(
    ("status", "body"),
    [(500, '{"error": "boom"}'), (404, "not found"), (200, "<html>not json</html>")],
)
def test_execute_handles_bad_responses(
    ransomwhat_env, mongo_client, importers, http_server, status, body
):
    http_server.add(GROUPS_PATH, body, status=status)
    importer = importers(mongo_client)
    with pytest.raises((requests.RequestException, ValueError)):
        importer.extract_v3_urls()
    importer.execute()  # logged, not raised
    assert importer.list_data() == []


def test_execute_handles_unreachable_url(
    ransomwhat_env, mongo_client, importers, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SADIF_MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_URL", _closed_port_url())
    importer = importers(mongo_client)
    importer.execute()
    assert importer.list_data() == []


def test_execute_with_empty_groups(ransomwhat_env, mongo_client, importers, http_server):
    http_server.add(GROUPS_PATH, "[]", content_type="application/json")
    importer = importers(mongo_client)
    assert importer.extract_v3_urls() == []
    importer.execute()
    assert importer.list_data() == []


def test_update_git_repository_pushes_one_file_per_url(
    ransomwhat_env, mongo_client, importers, tmp_path
):
    importer = importers(mongo_client)
    importer.execute()
    cwd = Path.cwd()
    importer.update_git_repository()
    assert Path.cwd() == cwd

    clone = read_repo(ransomwhat_env["bare"], tmp_path)
    folder = clone / importer.ransomwhat_module_name
    files = sorted(path.name for path in folder.glob("*.json"))
    expected = ransomwhat_env["expected"]
    assert files == sorted(
        url.removeprefix("http://").removesuffix(".onion") + ".json" for url in expected
    )
    contents = sorted(json.loads(path.read_text())["url"] for path in folder.glob("*.json"))
    assert contents == expected
    message = _git("log", "-1", "--format=%s", cwd=clone)
    assert message.startswith(f"Automated update: {len(expected)} URLs at ")
    assert message.endswith(f"by {importer.sadif_user}")
    assert (clone / "README.md").exists()

    # nothing changed: no new commit is pushed
    commits = _git("rev-list", "--count", "main", cwd=ransomwhat_env["bare"])
    importer.update_git_repository()
    assert _git("rev-list", "--count", "main", cwd=ransomwhat_env["bare"]) == commits


def test_update_git_repository_follows_remote_default_branch(
    ransomwhat_env, mongo_client, importers, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    bare = ransomwhat_env["bare"]
    _git("branch", "-m", "main", "data", cwd=bare)
    _git("symbolic-ref", "HEAD", "refs/heads/data", cwd=bare)
    importer = importers(mongo_client)
    importer.execute()
    importer.update_git_repository()
    assert _git("branch", "--list", "main", cwd=bare) == ""
    clone = read_repo(bare, tmp_path)
    assert len(list((clone / importer.ransomwhat_module_name).glob("*.json"))) == len(
        ransomwhat_env["expected"]
    )


def test_update_git_repository_with_invalid_repo(
    ransomwhat_env, mongo_client, importers, tmp_path, monkeypatch: pytest.MonkeyPatch, caplog
):
    monkeypatch.setenv("SADIF_SADIF_DATA_MODULES_URL", str(tmp_path / "does-not-exist.git"))
    importer = importers(mongo_client)
    importer.execute()
    caplog.clear()
    with caplog.at_level("DEBUG"):
        importer.update_git_repository()  # logged, not raised
        importer.import_git_repository()  # logged, not raised
    assert importer.git_manager.repo is None
    git_errors = [
        r.getMessage() for r in caplog.records if r.name == "git" and r.levelname == "ERROR"
    ]
    assert any("Failed to update Git repository: clone failed." in m for m in git_errors)
    assert any("Error during Git repository import: clone failed." in m for m in git_errors)
    messages = [r.getMessage() for r in caplog.records]
    assert not any("pushed successfully" in m or "Total files imported" in m for m in messages)


def test_update_git_repository_push_rejected(
    ransomwhat_env, mongo_client, importers, tmp_path, local_git_repo, monkeypatch, caplog
):
    # non-bare repo with main checked out: the push is refused by git
    repo = local_git_repo({"README.md": "checked out"})
    monkeypatch.setenv("SADIF_SADIF_DATA_MODULES_URL", repo)
    importer = importers(mongo_client)
    importer.execute()
    caplog.clear()
    with caplog.at_level("DEBUG"):
        importer.update_git_repository()
    messages = [(r.levelname, r.getMessage()) for r in caplog.records if r.name == "git"]
    assert any(level == "ERROR" and "Failed to push changes" in msg for level, msg in messages)
    assert not any("pushed successfully" in msg for _, msg in messages)
    assert not (Path(repo) / importer.ransomwhat_module_name).exists()
    assert _git("rev-list", "--count", "main", cwd=repo) == "1"


def test_import_git_repository(
    sadif_databases, mongo_client, importers, bare_repo, http_server, monkeypatch, e2e_id, caplog
):
    valid_a = f"http://{make_v3_address(e2e_id + 'ia')}"
    valid_b = f"http://{make_v3_address(e2e_id + 'ib')}"
    bare = bare_repo(
        {
            "ransomwhat/a.json": json.dumps({"url": valid_a}),
            "ransomwhat/b.json": json.dumps({"url": valid_b, "group": "b"}),
            "ransomwhat/invalid_schema.json": json.dumps({"url": 123}),
            "ransomwhat/missing_url.json": json.dumps({"name": "x"}),
            "ransomwhat/list.json": json.dumps([{"url": "http://list.onion"}]),
            "ransomwhat/broken.json": "{not json",
            "ransomwhat/ignored.txt": json.dumps({"url": "http://txt.onion"}),
            "other/c.json": json.dumps({"url": "http://other.onion"}),
        }
    )
    monkeypatch.setenv("SADIF_SADIF_DATA_MODULES_URL", str(bare))
    monkeypatch.setenv(
        "SADIF_MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_URL",
        http_server.add(GROUPS_PATH, "[]", content_type="application/json"),
    )
    importer = importers(mongo_client)
    with caplog.at_level("INFO"):
        importer.import_git_repository()
    assert "[SUCCESS] - Total files imported: 2" in caplog.messages
    collection = mongo_client[sadif_databases["MONGODB_DATABASE_MODULES_MANAGER"]][
        f"module_{importer.ransomwhat_module_name}"
    ]
    assert sorted(collection.find({}, {"_id": 0}), key=lambda d: d["url"]) == sorted(
        [{"url": valid_a}, {"url": valid_b, "group": "b"}], key=lambda d: d["url"]
    )
    caplog.clear()
    with caplog.at_level("INFO"):
        importer.import_git_repository()  # re-import: no duplicates
    assert "[SUCCESS] - Total files imported: 0" in caplog.messages
    assert collection.count_documents({}) == 2
    assert http_server.requests == []  # import never touches the groups URL


def test_temporary_directory_change_restores_cwd(ransomwhat_env, mongo_client, importers, tmp_path):
    importer = importers(mongo_client)
    original = Path.cwd()
    target = tmp_path / "workdir"
    target.mkdir()
    with importer.temporary_directory_change(target):
        assert Path.cwd() == target.resolve()
    assert Path.cwd() == original
    with pytest.raises(RuntimeError), importer.temporary_directory_change(target):
        assert Path.cwd() == target.resolve()
        raise RuntimeError("boom")  # noqa: EM101
    assert Path.cwd() == original
    with (
        pytest.raises(FileNotFoundError),
        importer.temporary_directory_change(tmp_path / "missing"),
    ):
        pass
    assert Path.cwd() == original


def test_import_git_repository_without_module_folder(ransomwhat_env, mongo_client, importers):
    importer = importers(mongo_client)
    importer.import_git_repository()
    assert importer.list_data() == []


def test_round_trip_update_then_import_into_fresh_database(ransomwhat_env, mongo_client, importers):
    exporter = importers(mongo_client)
    exporter.execute()
    exporter.update_git_repository()

    collection = mongo_client[ransomwhat_env["db"]][f"module_{exporter.ransomwhat_module_name}"]
    collection.delete_many({})
    importer = importers(mongo_client)  # fresh clone of the updated repository
    importer.import_git_repository()
    assert sorted(doc["url"] for doc in collection.find()) == ransomwhat_env["expected"]


# --------------------------------------------------------- TLS certificate checking


@pytest.fixture()
def https_server(tmp_path: Path) -> Iterator[dict]:
    """Local HTTPS server with a self-signed certificate for 127.0.0.1."""
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    command = [
        *("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1"),
        *("-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"),
        *("-keyout", str(key), "-out", str(cert)),
    ]
    subprocess.run(command, check=True, capture_output=True)  # noqa: S603
    routes: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            payload = routes.get(self.path, "").encode()
            self.send_response(200 if self.path in routes else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {"url": f"https://127.0.0.1:{server.server_address[1]}", "routes": routes, "cert": cert}
    server.shutdown()
    server.server_close()


def test_tls_certificates_are_verified(
    sadif_databases, mongo_client, importers, https_server, monkeypatch, e2e_id
):
    address = make_v3_address(e2e_id + "tls")
    https_server["routes"][GROUPS_PATH] = groups_json([[address]])
    monkeypatch.setenv(
        "SADIF_MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_URL",
        https_server["url"] + GROUPS_PATH,
    )
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    importer = importers(mongo_client)
    importer.execute()  # self-signed certificate is not trusted: nothing stored
    assert importer.list_data() == []

    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(https_server["cert"]))
    assert os.environ["REQUESTS_CA_BUNDLE"]
    importer.execute()  # trusted CA bundle: certificate verified and data stored
    assert importer.list_data() == [{"url": f"http://{address}"}]
