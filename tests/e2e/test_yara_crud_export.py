import pytest

pytestmark = pytest.mark.e2e

import os  # noqa: E402
import zipfile  # noqa: E402
from pathlib import Path  # noqa: E402

from bson import ObjectId  # noqa: E402

from sadif.clientmanager.client_data_manager import ClientManager  # noqa: E402
from sadif.frameworks_drivers.sadif_yara.yara_crud import YaraCrud  # noqa: E402
from sadif.frameworks_drivers.sadif_yara.yara_export import YaraRulesExporter  # noqa: E402

PREFIX = "Client_"


def rule_text(name: str, string: str = "abc") -> str:
    return (
        f'rule {name}\n{{\n    strings:\n        $a = "{string}"\n    condition:\n        $a\n}}\n'
    )


@pytest.fixture()
def clients(sadif_databases, mongo_client, e2e_id):
    manager = ClientManager(db_client=mongo_client)
    names = [f"Acme{e2e_id}", f"Globex{e2e_id}"]
    for index, name in enumerate(names):
        assert "criada" in manager.create_client_collection(name, f"Co{index}", f"ciid{index}")
    return names


@pytest.fixture()
def crud(sadif_databases, mongo_client):
    return YaraCrud(db_client=mongo_client)


def yara_db(mongo_client, sadif_databases):
    return mongo_client[sadif_databases["MONGODB_DATABASE_YARA"]]


# ---------------------------------------------------------------- YaraCrud


def test_init_uses_configured_databases(sadif_databases, mongo_client):
    crud = YaraCrud(db_client=mongo_client)
    assert crud.db.name == sadif_databases["MONGODB_DATABASE_YARA"]
    assert crud.mongo_client_prefix == PREFIX
    assert crud.list_all_clients.db.name == sadif_databases["MONGODB_DATABASE_CLIENTS"]


def test_init_without_client_uses_configured_url(sadif_databases, monkeypatch):
    monkeypatch.setenv("SADIF_MONGODB_URL", "mongodb://127.0.0.1:27017")
    crud = YaraCrud()
    try:
        assert crud.list_all_rule_names() == []
        crud.client.admin.command("ping")  # address só existe após conectar
        assert crud.client.address == ("127.0.0.1", 27017)
        assert crud.list_all_clients.client is crud.client
    finally:
        crud.client.close()


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (rule_text("ExampleRule"), "ExampleRule"),
        ("private rule  Second_1 : tag { condition: true }", "Second_1"),
        ("no yara here", None),
        ("", None),
    ],
)
def test_parse_rule(crud, content, expected):
    assert crud.parse_rule(content) == (expected, content)


def test_insert_and_find_rule(crud, clients, mongo_client, sadif_databases, e2e_id):
    content = rule_text(f"R{e2e_id}")
    inserted_id = crud.insert_rule(clients[0], f"R{e2e_id}", content)
    assert isinstance(inserted_id, ObjectId)

    docs = list(yara_db(mongo_client, sadif_databases)[f"{PREFIX}{clients[0]}"].find())
    assert docs == [{"_id": inserted_id, "rule_name": f"R{e2e_id}", "rule_content": content}]
    assert (
        f"{PREFIX}{clients[1]}"
        not in yara_db(mongo_client, sadif_databases).list_collection_names()
    )

    found = crud.find_rule(f"R{e2e_id}")
    assert found["rule_content"] == content
    assert found["_id"] == inserted_id


def test_insert_duplicate_raises_and_keeps_original(crud, clients, mongo_client, sadif_databases):
    crud.insert_rule(clients[0], "Dup", rule_text("Dup", "one"))
    with pytest.raises(ValueError, match="já existe"):
        crud.insert_rule(clients[0], "Dup", rule_text("Dup", "two"))
    collection = yara_db(mongo_client, sadif_databases)[f"{PREFIX}{clients[0]}"]
    assert collection.count_documents({}) == 1
    assert collection.find_one()["rule_content"] == rule_text("Dup", "one")


def test_same_rule_name_allowed_for_different_clients(crud, clients, mongo_client, sadif_databases):
    crud.insert_rule(clients[0], "Shared", rule_text("Shared", "a"))
    crud.insert_rule(clients[1], "Shared", rule_text("Shared", "b"))
    db = yara_db(mongo_client, sadif_databases)
    assert db[f"{PREFIX}{clients[0]}"].find_one()["rule_content"] == rule_text("Shared", "a")
    assert db[f"{PREFIX}{clients[1]}"].find_one()["rule_content"] == rule_text("Shared", "b")
    assert sorted(crud.list_all_rule_names()) == ["Shared", "Shared"]


def test_insert_overwrite_existing_and_new(crud, clients, mongo_client, sadif_databases):
    collection = yara_db(mongo_client, sadif_databases)[f"{PREFIX}{clients[0]}"]
    crud.insert_rule(clients[0], "Over", rule_text("Over", "old"))

    assert crud.insert_rule(clients[0], "Over", rule_text("Over", "new"), overwrite=True) == 1
    assert collection.count_documents({"rule_name": "Over"}) == 1
    assert collection.find_one({"rule_name": "Over"})["rule_content"] == rule_text("Over", "new")

    # overwrite com o mesmo conteúdo: nada modificado
    assert crud.insert_rule(clients[0], "Over", rule_text("Over", "new"), overwrite=True) == 0

    # overwrite de regra inexistente faz upsert
    upserted = crud.insert_rule(clients[0], "Fresh", rule_text("Fresh"), overwrite=True)
    assert isinstance(upserted, ObjectId)
    assert collection.find_one({"_id": upserted})["rule_content"] == rule_text("Fresh")


def test_insert_for_unknown_client_returns_none(crud, clients, mongo_client, sadif_databases):
    assert crud.insert_rule("Unknown", "X", rule_text("X")) is None
    assert crud.insert_rule("Unknown", "X", rule_text("X"), overwrite=True) is None
    assert yara_db(mongo_client, sadif_databases).list_collection_names() == []


def test_insert_without_any_client(crud, mongo_client, sadif_databases):
    assert crud.insert_rule("Nobody", "X", rule_text("X")) is None
    assert crud.list_all_rule_names() == []


def test_find_rule_not_found_and_ignores_foreign_collections(
    crud, clients, mongo_client, sadif_databases
):
    yara_db(mongo_client, sadif_databases)["Other"].insert_one(
        {"rule_name": "Hidden", "rule_content": "rule Hidden {condition: true}"}
    )
    assert crud.find_rule("Missing") is None
    assert crud.find_rule("Hidden") is None
    assert crud.list_all_rule_names() == []


def test_update_rule(crud, clients, mongo_client, sadif_databases):
    crud.insert_rule(clients[1], "Upd", rule_text("Upd", "v1"))
    result = crud.update_rule("Upd", rule_text("Upd", "v2"))
    assert result.matched_count == 1
    assert result.modified_count == 1
    doc = yara_db(mongo_client, sadif_databases)[f"{PREFIX}{clients[1]}"].find_one()
    assert doc["rule_content"] == rule_text("Upd", "v2")
    assert crud.find_rule("Upd")["rule_content"] == rule_text("Upd", "v2")


def test_update_rule_not_found(crud, clients, mongo_client, sadif_databases):
    crud.insert_rule(clients[0], "Keep", rule_text("Keep"))
    assert crud.update_rule("Missing", "rule Missing {condition: true}") is None
    db = yara_db(mongo_client, sadif_databases)
    assert db[f"{PREFIX}{clients[0]}"].count_documents({}) == 1
    assert db[f"{PREFIX}{clients[0]}"].find_one()["rule_content"] == rule_text("Keep")


def test_delete_rule(crud, clients, mongo_client, sadif_databases):
    crud.insert_rule(clients[0], "Del", rule_text("Del"))
    crud.insert_rule(clients[0], "Stay", rule_text("Stay"))
    result = crud.delete_rule("Del")
    assert result.deleted_count == 1
    collection = yara_db(mongo_client, sadif_databases)[f"{PREFIX}{clients[0]}"]
    assert [d["rule_name"] for d in collection.find()] == ["Stay"]
    assert crud.find_rule("Del") is None
    # segunda deleção: não encontrada
    assert crud.delete_rule("Del") is None
    assert crud.list_all_rule_names() == ["Stay"]


def test_list_all_rule_names(crud, clients):
    assert crud.list_all_rule_names() == []
    crud.insert_rule(clients[0], "A1", rule_text("A1"))
    crud.insert_rule(clients[0], "A2", rule_text("A2"))
    crud.insert_rule(clients[1], "B1", rule_text("B1"))
    assert sorted(crud.list_all_rule_names()) == ["A1", "A2", "B1"]


def test_full_crud_cycle(crud, clients):
    name, content = crud.parse_rule(rule_text("Cycle"))
    crud.insert_rule(clients[0], name, content)
    assert crud.find_rule(name)["rule_content"] == content
    crud.update_rule(name, rule_text("Cycle", "zzz"))
    assert "zzz" in crud.find_rule(name)["rule_content"]
    crud.delete_rule(name)
    assert crud.find_rule(name) is None
    assert crud.list_all_rule_names() == []


# ---------------------------------------------------------------- YaraRulesExporter


def populate(crud, clients):
    expected = {
        clients[0]: {"A1": rule_text("A1", "á-ç"), "A2": rule_text("A2")},
        clients[1]: {"B1": rule_text("B1", "xyz")},
    }
    for client, rules in expected.items():
        for name, content in rules.items():
            crud.insert_rule(client, name, content)
    return expected


def zip_contents(zip_path: Path) -> dict[str, str]:
    with zipfile.ZipFile(zip_path) as zipf:
        return {info.filename: zipf.read(info).decode("utf-8") for info in zipf.infolist()}


def expected_entries(expected: dict[str, dict[str, str]]) -> dict[str, str]:
    return {
        f"{client}/{name}.yar": content
        for client, rules in expected.items()
        for name, content in rules.items()
    }


def make_exporter(sadif_databases, export_dir, **kwargs):
    # sadif_databases exporta SADIF_MONGODB_URL apontando para o MongoDB de teste
    return YaraRulesExporter(
        os.environ["SADIF_MONGODB_URL"],
        sadif_databases["MONGODB_DATABASE_YARA"],
        str(export_dir),
        **kwargs,
    )


def test_exporter_creates_export_dir(sadif_databases, tmp_path):
    export_dir = tmp_path / "nested" / "out"
    exporter = make_exporter(sadif_databases, export_dir)
    assert export_dir.is_dir()
    assert exporter.auto_extract is False
    exporter.client.close()


def test_export_zip_only(crud, clients, sadif_databases, tmp_path):
    expected = populate(crud, clients)
    export_dir = tmp_path / "out"
    exporter = make_exporter(sadif_databases, export_dir)
    zip_path = exporter.export_rules()
    exporter.client.close()

    assert zip_path == export_dir / "YaraRulesExport.zip"
    assert zip_contents(zip_path) == expected_entries(expected)
    # sem auto_extract nada além do zip é escrito em disco
    assert [p.name for p in export_dir.iterdir()] == ["YaraRulesExport.zip"]


def test_export_with_auto_extract(crud, clients, sadif_databases, tmp_path):
    expected = populate(crud, clients)
    export_dir = tmp_path / "out"
    exporter = make_exporter(sadif_databases, export_dir, auto_extract=True)
    zip_path = exporter.export_rules()
    exporter.client.close()

    assert zip_contents(zip_path) == expected_entries(expected)
    for client, rules in expected.items():
        client_dir = export_dir / client
        assert sorted(p.name for p in client_dir.iterdir()) == sorted(f"{n}.yar" for n in rules)
        for name, content in rules.items():
            assert (client_dir / f"{name}.yar").read_text(encoding="utf-8") == content


def test_export_auto_extract_existing_dir_and_overwrite(crud, clients, sadif_databases, tmp_path):
    export_dir = tmp_path / "out"
    (export_dir / clients[0]).mkdir(parents=True)
    (export_dir / clients[0] / "A1.yar").write_text("stale", encoding="utf-8")
    expected = populate(crud, clients)
    exporter = make_exporter(sadif_databases, export_dir, auto_extract=True)
    exporter.export_rules()
    assert (export_dir / clients[0] / "A1.yar").read_text(encoding="utf-8") == expected[clients[0]][
        "A1"
    ]

    # a reexportação reflete o estado atual do banco (regra removida some do zip)
    crud.delete_rule("A2")
    del expected[clients[0]]["A2"]
    zip_path = exporter.export_rules()
    exporter.client.close()
    assert zip_contents(zip_path) == expected_entries(expected)


def test_export_empty_database(sadif_databases, tmp_path):
    exporter = make_exporter(sadif_databases, tmp_path / "out", auto_extract=True)
    zip_path = exporter.export_rules()
    exporter.client.close()
    assert zip_contents(zip_path) == {}


def test_export_ignores_foreign_and_invalid_documents(
    crud, clients, mongo_client, sadif_databases, tmp_path
):
    expected = populate(crud, clients)
    db = yara_db(mongo_client, sadif_databases)
    db["Other_collection"].insert_one({"rule_name": "Foreign", "rule_content": "rule Foreign {}"})
    db[f"{PREFIX}{clients[1]}"].insert_one({"note": "not a rule"})
    exporter = make_exporter(sadif_databases, tmp_path / "out")
    zip_path = exporter.export_rules()
    exporter.client.close()
    assert zip_contents(zip_path) == expected_entries(expected)


def test_export_client_name_with_underscore(sadif_databases, mongo_client, tmp_path, e2e_id):
    client = f"My_Client_{e2e_id}"
    assert "criada" in ClientManager(db_client=mongo_client).create_client_collection(
        client, "Co", "ciid"
    )
    crud = YaraCrud(db_client=mongo_client)
    crud.insert_rule(client, "U1", rule_text("U1"))
    exporter = make_exporter(sadif_databases, tmp_path / "out", auto_extract=True)
    zip_path = exporter.export_rules()
    exporter.client.close()
    assert zip_contents(zip_path) == {f"{client}/U1.yar": rule_text("U1")}
    assert (tmp_path / "out" / client / "U1.yar").read_text(encoding="utf-8") == rule_text("U1")


def test_export_custom_prefix(sadif_databases, mongo_client, tmp_path, monkeypatch, e2e_id):
    monkeypatch.setenv("SADIF_MONGODB_CLIENT_PREFIX", "Cli-")
    client = f"Pref{e2e_id}"
    ClientManager(db_client=mongo_client).create_client_collection(client, "Co", "ciid")
    crud = YaraCrud(db_client=mongo_client)
    crud.insert_rule(client, "P1", rule_text("P1"))
    assert f"Cli-{client}" in yara_db(mongo_client, sadif_databases).list_collection_names()
    exporter = make_exporter(sadif_databases, tmp_path / "out")
    zip_path = exporter.export_rules()
    exporter.client.close()
    assert zip_contents(zip_path) == {f"{client}/P1.yar": rule_text("P1")}


def test_parse_rule_ignores_rule_word_in_comments(mongo_client, sadif_databases):
    from sadif.frameworks_drivers.sadif_yara.yara_crud import YaraCrud

    content = (
        "// this rule detects leaked keys\n"
        "/* rule Fake { condition: true } */\n"
        'private rule InternalMonitoramentoLeak99 { strings: $a = "k" condition: $a }\n'
    )
    name, parsed = YaraCrud(db_client=mongo_client).parse_rule(content)
    assert name == "InternalMonitoramentoLeak99"
    assert parsed == content
