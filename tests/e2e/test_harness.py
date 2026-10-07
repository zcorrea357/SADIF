import requests


def test_isolated_databases(sadif_databases, mongo_client):
    from sadif.config.sadif_config import SadifConfiguration

    config = SadifConfiguration()
    name = config.get_configuration("MONGODB_DATABASE_CLIENTS")
    assert name == sadif_databases["MONGODB_DATABASE_CLIENTS"]
    mongo_client[name]["c"].insert_one({"ok": True})
    assert mongo_client[name]["c"].count_documents({}) == 1


def test_http_server(http_server):
    url = http_server.add("/hello", "world")
    assert requests.get(url, timeout=5).text == "world"
    assert http_server.requests[0]["path"] == "/hello"


def test_local_git_repo(local_git_repo):
    from sadif.frameworks_drivers.gitmanager import GitManager

    repo = local_git_repo({"a/b.json": "[]"})
    cloned = GitManager(repo).clone_repo()
    assert (__import__("pathlib").Path(cloned) / "a" / "b.json").read_text() == "[]"


def test_thehive_status(thehive_session):
    response, status = thehive_session.get_status()
    assert status == 200
    assert "TheHive" in response["versions"]
