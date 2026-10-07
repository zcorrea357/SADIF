import pytest

pytestmark = pytest.mark.e2e

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from bson import ObjectId  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402

from sadif.frameworks_drivers.crawler.crawler_data_export import (  # noqa: E402
    CrawlerManagerExport,
    export_filename,
)
from sadif.frameworks_drivers.crawler.crawler_data_import import (  # noqa: E402
    CrawlerManagerImporter,
)
from sadif.frameworks_drivers.crawler.crawler_manager import CrawlerManager  # noqa: E402
from sadif.frameworks_drivers.gitmanager import GitManager  # noqa: E402

COLLECTIONS = (
    "crawler_with_credential_web",
    "crawler_without_credential_web",
    "crawler_with_credential_onion",
    "crawler_without_credential_onion",
)


@pytest.fixture(autouse=True)
def _no_sentry(monkeypatch: pytest.MonkeyPatch) -> None:
    # Os testes não devem enviar eventos para o Sentry (internet)
    monkeypatch.setenv("SADIF_SENTRYDSN", "")


def _monitoring_repo_files(e2e_id: str) -> dict[str, str]:
    """Arquivos no formato de github.com/florestleaks/crawler_monitoring."""
    docs = {
        "crawler_with_credential_web/portal.json": {
            "url": f"https://portal-{e2e_id}.example.com/login",
            "auth_type": "basic",
            "credentials": {"username": "analyst", "password": "s3cret"},
            "client": "ClienteA",
        },
        "crawler_without_credential_web/blog.json": {
            "url": f"https://www.blog-{e2e_id}.example.com/posts",
            "client": "ClienteA",
        },
        "crawler_with_credential_onion/forum.json": {
            "url": f"http://forum{e2e_id}.onion/board",
            "auth_type": "form",
            "credentials": {"username": "ghost", "password": "hunter2"},
        },
        "crawler_without_credential_onion/leaks.json": {
            "url": f"http://leaks{e2e_id}.onion/",
            "client": "ClienteB",
        },
    }
    files = {path: json.dumps(doc) for path, doc in docs.items()}
    # Entradas que devem ser ignoradas pela importação
    files["README.md"] = "# crawler monitoring"
    files["crawler_without_credential_web/notes.txt"] = "not a json document"
    files["crawler_without_credential_web/no_url.json"] = json.dumps({"client": "ClienteA"})
    files["crawler_without_credential_web/broken.json"] = "{not valid json"
    files["other_folder/ignored.json"] = json.dumps({"url": f"https://ignored-{e2e_id}.example"})
    return files


@pytest.fixture()
def monitoring_repo(local_git_repo, e2e_id, monkeypatch) -> str:
    repo = local_git_repo(_monitoring_repo_files(e2e_id))
    monkeypatch.setenv("SADIF_GIT_REPO_CLIENT_CRAWLER_MONITORING", repo)
    monkeypatch.setenv("SADIF_GIT_REPO_TOKEN", "")
    return repo


@pytest.fixture()
def crawler_db(sadif_databases, mongo_client):
    return mongo_client[sadif_databases["MONGODB_DATABASE_CRAWLER"]]


@pytest.fixture()
def manager(monitoring_repo, crawler_db, mongo_client) -> CrawlerManager:
    return CrawlerManager(db_client=mongo_client)


def _urls(collection) -> set[str]:
    return {doc["url"] for doc in collection.find({}, {"url": 1})}


def _assert_unique_url_index(collection) -> None:
    indexes = collection.index_information()
    assert any(
        info["key"] == [("url", 1)] and info.get("unique") for info in indexes.values()
    ), indexes


# --------------------------------------------------------------------------- CrawlerManager


def test_init_clones_repo_and_creates_unique_indexes(manager, crawler_db, monitoring_repo):
    assert manager.db.name == crawler_db.name
    assert Path(manager.directory, "crawler_with_credential_web", "portal.json").is_file()
    for name in COLLECTIONS:
        _assert_unique_url_index(crawler_db[name])
    # O índice único é aplicado pelo MongoDB
    crawler_db["crawler_without_credential_web"].insert_one({"url": "https://dup.example"})
    with pytest.raises(DuplicateKeyError):
        crawler_db["crawler_without_credential_web"].insert_one({"url": "https://dup.example"})


def test_init_with_unreachable_repo_keeps_working_with_mongodb(
    crawler_db, mongo_client, monkeypatch, tmp_path
):
    monkeypatch.setenv("SADIF_GIT_REPO_CLIENT_CRAWLER_MONITORING", str(tmp_path / "missing"))
    manager = CrawlerManager(db_client=mongo_client)
    assert manager.directory is None
    assert isinstance(manager.process_document({"url": "https://ok.example"}), ObjectId)
    assert _urls(crawler_db["crawler_without_credential_web"]) == {"https://ok.example"}
    # Sem repositório, a importação falha sem apagar os dados (nem com meta_update)
    assert manager.import_collections(meta_update=True) is None
    assert _urls(crawler_db["crawler_without_credential_web"]) == {"https://ok.example"}


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        (
            {"url": "https://bank.example.com/login", "auth_type": "basic", "credentials": {}},
            "crawler_with_credential_web",
        ),
        ({"url": "https://news.example.com/"}, "crawler_without_credential_web"),
        (
            {"url": "http://abcdefxyz.onion/login", "auth_type": "form", "credentials": {}},
            "crawler_with_credential_onion",
        ),
        ({"url": "http://abcdefxyz.onion/"}, "crawler_without_credential_onion"),
        ({"url": "http://UPPER.ONION/x"}, "crawler_without_credential_onion"),
        ({"url": "abcdefxyz.onion/no-scheme"}, "crawler_without_credential_onion"),
        ({"url": "https://news.example.com/a", "auth_type": ""}, "crawler_without_credential_web"),
        (
            {"url": "https://news.example.com/b", "auth_type": None},
            "crawler_without_credential_web",
        ),
        ({"url": "https://onion.example.com/"}, "crawler_without_credential_web"),
    ],
)
def test_process_document_routes_to_the_right_collection(manager, crawler_db, document, expected):
    original = dict(document)
    inserted_id = manager.process_document(document)
    assert isinstance(inserted_id, ObjectId)
    assert document == original  # o documento recebido não é alterado
    stored = crawler_db[expected].find_one({"url": document["url"]})
    assert stored["_id"] == inserted_id
    assert {k: v for k, v in stored.items() if k != "_id"} == original
    for name in COLLECTIONS:
        if name != expected:
            assert crawler_db[name].count_documents({"url": document["url"]}) == 0


def test_process_document_duplicate_without_overwrite_is_ignored(manager, crawler_db):
    collection = crawler_db["crawler_with_credential_web"]
    first = {"url": "https://dup.example/login", "auth_type": "basic", "client": "A"}
    assert isinstance(manager.process_document(first), ObjectId)
    second = {"url": "https://dup.example/login", "auth_type": "basic", "client": "B"}
    assert manager.process_document(second, overwrite=False) is None
    assert collection.count_documents({"url": "https://dup.example/login"}) == 1
    assert collection.find_one({"url": "https://dup.example/login"})["client"] == "A"


def test_process_document_overwrite_updates_and_upserts(manager, crawler_db):
    collection = crawler_db["crawler_without_credential_onion"]
    url = "http://overwrite123.onion/"
    upserted = manager.process_document({"url": url, "client": "A"}, overwrite=True)
    assert isinstance(upserted, ObjectId)
    assert collection.find_one({"url": url})["_id"] == upserted

    matched = manager.process_document({"url": url, "client": "B", "tag": "x"}, overwrite=True)
    assert matched == 1
    stored = collection.find_one({"url": url})
    assert stored["_id"] == upserted
    assert (stored["client"], stored["tag"]) == ("B", "x")
    assert collection.count_documents({}) == 1

    # Reprocessar o documento lido do banco (com _id) também funciona
    stored["client"] = "C"
    assert manager.process_document(stored, overwrite=True) == 1
    assert collection.find_one({"url": url})["client"] == "C"

    # Um documento com _id diferente não altera o _id existente
    assert manager.process_document({"_id": ObjectId(), "url": url}, overwrite=True) == 1
    assert collection.find_one({"url": url})["_id"] == upserted


@pytest.mark.parametrize(
    "document",
    [{"client": "no url"}, {"url": ""}, {"url": None}, {"url": "http://"}, {"url": 123}],
)
def test_process_document_invalid_url_is_rejected(manager, crawler_db, document):
    assert manager.process_document(document) is None
    assert manager.process_document(document, overwrite=True) is None
    for name in COLLECTIONS:
        assert crawler_db[name].count_documents({}) == 0


def test_get_all_documents_by_collection(manager):
    manager.process_document({"url": "https://a.example/", "auth_type": "basic"})
    manager.process_document({"url": "https://b.example/"})
    manager.process_document({"url": "http://c.onion/", "auth_type": "form"})
    manager.process_document({"url": "http://d.onion/"})
    manager.process_document({"url": "http://e.onion/"})

    everything = manager.get_all_documents_by_collection()
    assert set(everything) == set(COLLECTIONS)
    assert everything["crawler_with_credential_web"] == [
        {"url": "https://a.example/", "auth_type": "basic"}
    ]
    assert everything["crawler_without_credential_web"] == [{"url": "https://b.example/"}]
    assert everything["crawler_with_credential_onion"] == [
        {"url": "http://c.onion/", "auth_type": "form"}
    ]
    assert sorted(d["url"] for d in everything["crawler_without_credential_onion"]) == [
        "http://d.onion/",
        "http://e.onion/",
    ]
    assert all("_id" not in doc for docs in everything.values() for doc in docs)

    one = manager.get_all_documents_by_collection("crawler_with_credential_onion")
    assert one == {
        "crawler_with_credential_onion": [{"url": "http://c.onion/", "auth_type": "form"}]
    }
    # Nome desconhecido retorna todas as coleções
    assert manager.get_all_documents_by_collection("unknown") == everything


def test_get_all_documents_empty(manager):
    assert manager.get_all_documents_by_collection() == {name: [] for name in COLLECTIONS}


def test_export_collections_writes_files(manager, tmp_path):
    docs = [
        {"url": "https://www.portal.example.com/login", "auth_type": "basic", "credentials": {}},
        {"url": "https://shop.example.com/a?b=c", "nome": "Ação"},
        {"url": "http://secret.onion:8080/x", "auth_type": "form"},
        {"url": "http://leak.onion/"},
    ]
    for doc in docs:
        manager.process_document(doc)

    export_dir = tmp_path / "nested" / "export"
    assert manager.export_collections(str(export_dir)) == {
        "crawler_with_credential_web": 1,
        "crawler_without_credential_web": 1,
        "crawler_with_credential_onion": 1,
        "crawler_without_credential_onion": 1,
    }
    expected_files = {
        "crawler_with_credential_web/portal_example_com_login.json": docs[0],
        "crawler_without_credential_web/shop_example_com_a_b_c.json": docs[1],
        "crawler_with_credential_onion/secret_onion_8080_x.json": docs[2],
        "crawler_without_credential_onion/leak_onion_.json": docs[3],
    }
    written = {p.relative_to(export_dir).as_posix() for p in export_dir.rglob("*.json")}
    assert written == set(expected_files)
    for relative, doc in expected_files.items():
        content = json.loads((export_dir / relative).read_text(encoding="utf-8"))
        assert content == {k: v for k, v in doc.items() if k != "_id"}


def test_export_collections_empty_creates_collection_dirs(manager, tmp_path):
    assert manager.export_collections(tmp_path / "out") == {name: 0 for name in COLLECTIONS}
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == sorted(COLLECTIONS)


def test_export_collections_to_invalid_path_fails(manager, tmp_path):
    manager.process_document({"url": "https://a.example/"})
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert manager.export_collections(blocker / "sub") is None


def test_export_filename():
    assert export_filename("https://www.site.com/a/b") == "site_com_a_b.json"
    assert export_filename("http://x.onion:80/") == "x_onion_80_.json"


def test_import_collections_from_repo(manager, crawler_db, e2e_id):
    summary = manager.import_collections()
    assert sorted(summary["imported"]) == sorted(
        [
            f"https://portal-{e2e_id}.example.com/login",
            f"https://www.blog-{e2e_id}.example.com/posts",
            f"http://forum{e2e_id}.onion/board",
            f"http://leaks{e2e_id}.onion/",
        ]
    )
    assert sorted(name for name, _ in summary["ignored"]) == ["broken.json", "no_url.json"]

    portal = crawler_db["crawler_with_credential_web"].find_one({}, {"_id": 0})
    assert portal["credentials"] == {"username": "analyst", "password": "s3cret"}
    assert portal["auth_type"] == "basic"
    assert _urls(crawler_db["crawler_without_credential_web"]) == {
        f"https://www.blog-{e2e_id}.example.com/posts"
    }
    assert _urls(crawler_db["crawler_with_credential_onion"]) == {
        f"http://forum{e2e_id}.onion/board"
    }
    assert _urls(crawler_db["crawler_without_credential_onion"]) == {f"http://leaks{e2e_id}.onion/"}
    assert "other_folder" not in crawler_db.list_collection_names()

    # Importar de novo não duplica (upsert pela URL)
    manager.import_collections()
    for name in COLLECTIONS:
        assert crawler_db[name].count_documents({}) == 1


def test_import_without_meta_update_keeps_existing_and_replaces_same_url(
    manager, crawler_db, e2e_id
):
    url = f"http://leaks{e2e_id}.onion/"
    manager.process_document({"url": url, "client": "old", "stale_field": True})
    manager.process_document({"url": "https://kept.example/"})
    manager.import_collections(meta_update=False)

    leaks = crawler_db["crawler_without_credential_onion"].find_one({"url": url}, {"_id": 0})
    assert leaks == {"url": url, "client": "ClienteB"}  # documento substituído
    assert "https://kept.example/" in _urls(crawler_db["crawler_without_credential_web"])


def test_import_with_meta_update_replaces_database_and_keeps_indexes(manager, crawler_db):
    manager.process_document({"url": "https://removed.example/"})
    crawler_db["unrelated"].insert_one({"x": 1})
    manager.import_collections(meta_update=True)

    assert "https://removed.example/" not in _urls(crawler_db["crawler_without_credential_web"])
    assert "unrelated" not in crawler_db.list_collection_names()
    for name in COLLECTIONS:
        assert crawler_db[name].count_documents({}) == 1
        _assert_unique_url_index(crawler_db[name])
    # Após o meta update o process_document continua respeitando a unicidade
    existing = crawler_db["crawler_without_credential_web"].find_one()
    assert manager.process_document({"url": existing["url"]}) is None


def test_import_routes_folders_to_configured_collection_names(
    monitoring_repo, crawler_db, mongo_client, monkeypatch, e2e_id
):
    monkeypatch.setenv("SADIF_MONGODB_COLLECTION_CRAWLER_WEB_WITH_CREDENTIAL", "custom_web_cred")
    manager = CrawlerManager(db_client=mongo_client)
    manager.import_collections()
    assert _urls(crawler_db["custom_web_cred"]) == {f"https://portal-{e2e_id}.example.com/login"}
    assert "crawler_with_credential_web" not in crawler_db.list_collection_names()
    _assert_unique_url_index(crawler_db["custom_web_cred"])
    assert manager.get_all_documents_by_collection("crawler_with_credential_web") == {
        "crawler_with_credential_web": [crawler_db["custom_web_cred"].find_one({}, {"_id": 0})]
    }


# ------------------------------------------------------- CrawlerManagerExport / Importer


def test_export_import_round_trip(
    monitoring_repo, crawler_db, mongo_client, local_git_repo, tmp_path
):
    seed = [
        {"url": "https://www.rt.example/login", "auth_type": "basic", "credentials": {"u": "p"}},
        {"url": "https://rt.example/public", "tags": ["a", "b"]},
        {"url": "http://rt1.onion/", "auth_type": "cookie", "credentials": {"c": "1"}},
        {"url": "http://rt2.onion/page"},
    ]
    manager = CrawlerManager(db_client=mongo_client)
    for doc in seed:
        manager.process_document(doc)

    exporter = CrawlerManagerExport(db_client=mongo_client)
    for name in COLLECTIONS:
        _assert_unique_url_index(crawler_db[name])
    assert exporter.get_all_documents_by_collection("crawler_without_credential_onion") == {
        "crawler_without_credential_onion": [{"url": "http://rt2.onion/page"}]
    }
    before = exporter.get_all_documents_by_collection()
    export_dir = tmp_path / "export"
    assert exporter.export_collections(str(export_dir)) == {name: 1 for name in COLLECTIONS}

    files = {
        p.relative_to(export_dir).as_posix(): p.read_text(encoding="utf-8")
        for p in export_dir.rglob("*.json")
    }
    assert len(files) == 4
    repo = local_git_repo(files)

    mongo_client.drop_database(crawler_db.name)
    importer = CrawlerManagerImporter(mongo_client, GitManager(repo))
    summary = importer.import_collections(meta_update=True)
    assert len(summary["imported"]) == 4
    assert summary["ignored"] == []
    assert exporter.get_all_documents_by_collection() == before
    for name in COLLECTIONS:
        _assert_unique_url_index(crawler_db[name])

    # meta_update=False: documentos extras permanecem
    crawler_db["crawler_without_credential_web"].insert_one({"url": "https://extra.example/"})
    importer.import_collections(meta_update=False)
    assert "https://extra.example/" in _urls(crawler_db["crawler_without_credential_web"])
    # meta_update=True: o banco volta a refletir exatamente o repositório
    importer.import_collections(meta_update=True)
    assert exporter.get_all_documents_by_collection() == before


def test_importer_uses_configured_repo_by_default(
    monitoring_repo, crawler_db, mongo_client, e2e_id
):
    importer = CrawlerManagerImporter(db_client=mongo_client)
    assert importer.directory is not None
    summary = importer.import_collections()
    assert len(summary["imported"]) == 4
    assert _urls(crawler_db["crawler_with_credential_onion"]) == {
        f"http://forum{e2e_id}.onion/board"
    }
    _assert_unique_url_index(crawler_db["crawler_with_credential_onion"])


def test_importer_with_failed_clone_does_not_drop_data(crawler_db, mongo_client, tmp_path):
    crawler_db["crawler_without_credential_web"].insert_one({"url": "https://keep.example/"})
    importer = CrawlerManagerImporter(mongo_client, GitManager(str(tmp_path / "missing")))
    assert importer.directory is None
    assert importer.import_collections(meta_update=True) is None
    assert _urls(crawler_db["crawler_without_credential_web"]) == {"https://keep.example/"}


def test_exporter_on_empty_database(crawler_db, mongo_client, tmp_path):
    exporter = CrawlerManagerExport(db_client=mongo_client)
    assert exporter.get_all_documents_by_collection() == {name: [] for name in COLLECTIONS}
    assert exporter.export_collections(tmp_path / "empty") == {name: 0 for name in COLLECTIONS}
    assert list((tmp_path / "empty").rglob("*.json")) == []


# ------------------------------------------------------------- verificação adicional


def test_process_document_scheme_less_onion_with_port(manager, crawler_db):
    assert isinstance(manager.process_document({"url": "portxyz.onion:8080/p"}), ObjectId)
    assert _urls(crawler_db["crawler_without_credential_onion"]) == {"portxyz.onion:8080/p"}


def test_export_colliding_filenames_keep_every_document(
    monitoring_repo, crawler_db, mongo_client, local_git_repo, tmp_path
):
    # URLs distintas que geram o mesmo nome de arquivo simplificado
    urls = [
        "https://collide.example/x",
        "http://collide.example/x",
        "https://www.collide.example/x",
    ]
    manager = CrawlerManager(db_client=mongo_client)
    for url in urls:
        assert isinstance(manager.process_document({"url": url}), ObjectId)

    export_dir = tmp_path / "export"
    result = manager.export_collections(export_dir)
    assert result["crawler_without_credential_web"] == 3
    files = list((export_dir / "crawler_without_credential_web").glob("*.json"))
    assert len(files) == 3
    assert {json.loads(f.read_text(encoding="utf-8"))["url"] for f in files} == set(urls)
    # Exportar de novo gera exatamente os mesmos nomes (determinístico)
    manager.export_collections(export_dir)
    assert len(list((export_dir / "crawler_without_credential_web").glob("*.json"))) == 3

    repo = local_git_repo(
        {p.relative_to(export_dir).as_posix(): p.read_text() for p in export_dir.rglob("*.json")}
    )
    importer = CrawlerManagerImporter(mongo_client, GitManager(repo))
    summary = importer.import_collections(meta_update=True)
    assert sorted(summary["imported"]) == sorted(urls)
    assert _urls(crawler_db["crawler_without_credential_web"]) == set(urls)


def test_import_json_arrays_non_objects_and_extra_crawler_folder(
    local_git_repo, crawler_db, mongo_client
):
    repo = local_git_repo(
        {
            "crawler_without_credential_web/many.json": json.dumps(
                [{"url": "https://arr1.example/"}, {"url": "https://arr2.example/"}, "oops"]
            ),
            "crawler_without_credential_web/scalar.json": json.dumps(42),
            "crawler_without_credential_web/bad_url.json": json.dumps({"url": 7}),
            "crawler_extra/extra.json": json.dumps({"url": "https://extra.example/"}),
        }
    )
    importer = CrawlerManagerImporter(mongo_client, GitManager(repo))
    summary = importer.import_collections()
    assert sorted(summary["imported"]) == [
        "https://arr1.example/",
        "https://arr2.example/",
        "https://extra.example/",
    ]
    assert sorted(name for name, _ in summary["ignored"]) == [
        "bad_url.json",
        "many.json",
        "scalar.json",
    ]
    assert _urls(crawler_db["crawler_without_credential_web"]) == {
        "https://arr1.example/",
        "https://arr2.example/",
    }
    assert _urls(crawler_db["crawler_extra"]) == {"https://extra.example/"}
    _assert_unique_url_index(crawler_db["crawler_extra"])
    with pytest.raises(DuplicateKeyError):
        crawler_db["crawler_extra"].insert_one({"url": "https://extra.example/"})


def test_exporter_uses_configured_collection_names_and_reports_failure(
    crawler_db, mongo_client, monkeypatch, tmp_path
):
    monkeypatch.setenv("SADIF_MONGODB_COLLECTION_CRAWLER_ONION_WITHOUT_CREDENTIAL", "custom_onion")
    crawler_db["custom_onion"].insert_one({"url": "http://cfg.onion/", "client": "Z"})
    exporter = CrawlerManagerExport(db_client=mongo_client)
    _assert_unique_url_index(crawler_db["custom_onion"])
    assert exporter.export_collections(tmp_path / "out")["crawler_without_credential_onion"] == 1
    exported = tmp_path / "out" / "crawler_without_credential_onion" / "cfg_onion_.json"
    assert json.loads(exported.read_text(encoding="utf-8")) == {
        "url": "http://cfg.onion/",
        "client": "Z",
    }

    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert exporter.export_collections(blocker / "sub") is None
    assert not (blocker.parent / "sub").exists()
