import pytest

pytestmark = pytest.mark.e2e

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from pymongo import MongoClient  # noqa: E402

from sadif.clientmanager.client_data_export import ClientManagerExport  # noqa: E402
from sadif.clientmanager.client_data_import import ClientManagerImport  # noqa: E402
from sadif.clientmanager.client_data_manager import ClientManager  # noqa: E402
from sadif.config.sadif_config import SadifConfiguration  # noqa: E402
from sadif.frameworks_drivers.gitmanager import GitManager  # noqa: E402

PREFIX = "Client_"
UNIQUE_FIELDS = {"client_name", "company", "ciid"}


def _clients_db(mongo_client: MongoClient, sadif_databases: dict[str, str]):
    return mongo_client[sadif_databases["MONGODB_DATABASE_CLIENTS"]]


def _unique_index_fields(collection) -> set[str]:
    return {
        next(iter(index["key"]))
        for index in collection.list_indexes()
        if index.get("unique") and index["name"] != "_id_"
    }


def _snapshot(db) -> dict:
    """Estado comparável do banco: documentos (sem _id) e índices únicos por coleção."""
    return {
        name: (
            sorted(db[name].find({}, {"_id": 0}), key=lambda d: d.get("client_name", "")),
            _unique_index_fields(db[name]),
        )
        for name in sorted(db.list_collection_names())
    }


@pytest.fixture()
def manager(sadif_databases, mongo_client) -> ClientManager:
    return ClientManager(db_client=mongo_client)


@pytest.fixture()
def populated(manager: ClientManager, e2e_id: str) -> list[str]:
    names = [f"{e2e_id}_alpha", f"{e2e_id}_beta"]
    for i, name in enumerate(names):
        assert manager.create_client_collection(name, f"Company{i}", f"CIID-{i}") == (
            f"Coleção criada para o cliente: {name}."
        )
    manager.update_module_info(names[0], "ModuloA", {"enabled": True, "keywords": ["acme"]})
    manager.update_module_info(names[1], "ModuloB", {"level": 3})
    return names


# --------------------------------------------------------------------------- ClientManager


def test_uses_isolated_database_and_config_prefix(manager, sadif_databases):
    assert manager.db.name == sadif_databases["MONGODB_DATABASE_CLIENTS"]
    assert manager.mongodb_client_prefix == PREFIX


def test_default_client_uses_configured_mongodb_url(
    sadif_databases, mongo_client, monkeypatch, e2e_id, tmp_path
):
    monkeypatch.setenv("SADIF_MONGODB_URL", "mongodb://127.0.0.1:27017")
    manager = ClientManager()
    exporter = ClientManagerExport()
    importer = ClientManagerImport()
    try:
        for instance in (manager, exporter, importer):
            seeds = instance.client.topology_description.server_descriptions()
            assert ("127.0.0.1", 27017) in seeds
        name = f"{e2e_id}_default"
        assert manager.create_client_collection(name, "C", "I").startswith("Coleção criada")
        db = _clients_db(mongo_client, sadif_databases)
        assert db[PREFIX + name].count_documents({"client_name": name}) == 1
        assert exporter.export_to_json(tmp_path).endswith("successfully.")
        db[PREFIX + name].drop()
        assert importer.import_from_json(str(tmp_path)).endswith("successfully.")
        assert db[PREFIX + name].count_documents({"client_name": name}) == 1
    finally:
        for instance in (manager, exporter, importer):
            instance.client.close()


def test_create_client_persists_document_and_unique_indexes(
    manager, mongo_client, sadif_databases, e2e_id
):
    name = f"{e2e_id}_acme"
    result = manager.create_client_collection(name, "ACME", "CIID-1")
    assert result == f"Coleção criada para o cliente: {name}."

    collection = _clients_db(mongo_client, sadif_databases)[PREFIX + name]
    docs = list(collection.find({}, {"_id": 0}))
    assert docs == [{"client_name": name, "company": "ACME", "ciid": "CIID-1", "Modules": {}}]
    assert _unique_index_fields(collection) == UNIQUE_FIELDS


def test_create_duplicate_client_is_ignored(manager, mongo_client, sadif_databases, e2e_id):
    name = f"{e2e_id}_dup"
    manager.create_client_collection(name, "ACME", "CIID-1")
    manager.update_module_info(name, "ModuloA", {"x": 1})

    result = manager.create_client_collection(name, "Other", "CIID-2")
    assert result == f"Coleção {PREFIX}{name} já existe. Operação ignorada."

    collection = _clients_db(mongo_client, sadif_databases)[PREFIX + name]
    assert list(collection.find({}, {"_id": 0})) == [
        {"client_name": name, "company": "ACME", "ciid": "CIID-1", "Modules": {"ModuloA": {"x": 1}}}
    ]


def test_create_with_overwrite_replaces_collection(manager, mongo_client, sadif_databases, e2e_id):
    name = f"{e2e_id}_ow"
    manager.create_client_collection(name, "ACME", "CIID-1")
    manager.update_module_info(name, "ModuloA", {"x": 1})

    result = manager.create_client_collection(name, "NewCo", "CIID-9", overwrite=True)
    assert result == f"Coleção criada para o cliente: {name}."

    collection = _clients_db(mongo_client, sadif_databases)[PREFIX + name]
    assert list(collection.find({}, {"_id": 0})) == [
        {"client_name": name, "company": "NewCo", "ciid": "CIID-9", "Modules": {}}
    ]
    assert _unique_index_fields(collection) == UNIQUE_FIELDS


def test_create_overwrite_on_new_client_just_creates(
    manager, mongo_client, sadif_databases, e2e_id
):
    name = f"{e2e_id}_fresh"
    assert manager.create_client_collection(name, "C", "I", overwrite=True) == (
        f"Coleção criada para o cliente: {name}."
    )
    assert PREFIX + name in _clients_db(mongo_client, sadif_databases).list_collection_names()


@pytest.mark.parametrize(
    ("client_name", "company", "ciid"),
    [("", "ACME", "C1"), ("x", "", "C1"), ("x", "ACME", ""), (None, None, None)],
)
def test_create_missing_fields_creates_nothing(
    manager, mongo_client, sadif_databases, client_name, company, ciid
):
    result = manager.create_client_collection(client_name, company, ciid)
    assert result == "Erro: 'client_name', 'company' e 'ciid' são necessários."
    assert _clients_db(mongo_client, sadif_databases).list_collection_names() == []


@pytest.mark.parametrize("module_name", SadifConfiguration().get_configuration("CLIENTS_MODULES"))
def test_update_every_allowed_module(manager, mongo_client, sadif_databases, e2e_id, module_name):
    name = f"{e2e_id}_mod"
    manager.create_client_collection(name, "ACME", "CIID-1")
    info = {"enabled": True, "targets": ["a.example", "b.example"], "threshold": 0.5}

    result = manager.update_module_info(name, module_name, info)
    assert result == f"Informações do módulo '{module_name}' atualizadas com sucesso."

    doc = _clients_db(mongo_client, sadif_databases)[PREFIX + name].find_one()
    assert doc["Modules"] == {module_name: info}
    assert manager.find_client_modules(name) == {module_name: info}

    # Segunda atualização substitui só esse módulo
    manager.update_module_info(name, module_name, {"enabled": False})
    assert manager.find_client_modules(name) == {module_name: {"enabled": False}}


def test_update_all_modules_accumulate(manager, e2e_id):
    name = f"{e2e_id}_all"
    manager.create_client_collection(name, "ACME", "CIID-1")
    modules = SadifConfiguration().get_configuration("CLIENTS_MODULES")
    for i, module_name in enumerate(modules):
        manager.update_module_info(name, module_name, {"i": i})
    assert manager.find_client_modules(name) == {m: {"i": i} for i, m in enumerate(modules)}


def test_update_forbidden_module_is_rejected(manager, mongo_client, sadif_databases, e2e_id):
    name = f"{e2e_id}_forbidden"
    manager.create_client_collection(name, "ACME", "CIID-1")
    result = manager.update_module_info(name, "ModuloProibido", {"x": 1})
    assert result == "Erro: Módulo 'ModuloProibido' não é permitido."
    doc = _clients_db(mongo_client, sadif_databases)[PREFIX + name].find_one()
    assert doc["Modules"] == {}


def test_clients_modules_can_be_overridden_by_env(manager, monkeypatch, e2e_id):
    name = f"{e2e_id}_envmod"
    manager.create_client_collection(name, "ACME", "CIID-1")
    monkeypatch.setenv("SADIF_CLIENTS_MODULES", json.dumps(["ModuloX"]))
    assert manager.update_module_info(name, "ModuloA", {}) == (
        "Erro: Módulo 'ModuloA' não é permitido."
    )
    assert manager.update_module_info(name, "ModuloX", {"y": 2}).endswith("sucesso.")
    assert manager.find_client_modules(name) == {"ModuloX": {"y": 2}}


def test_update_unknown_client_creates_nothing(manager, mongo_client, sadif_databases, e2e_id):
    result = manager.update_module_info(f"{e2e_id}_ghost", "ModuloA", {"x": 1})
    assert result == "Erro: Cliente não encontrado."
    assert _clients_db(mongo_client, sadif_databases).list_collection_names() == []


def test_find_client_modules_not_found_and_missing_document(
    manager, mongo_client, sadif_databases, e2e_id
):
    assert manager.find_client_modules(f"{e2e_id}_ghost") == "Cliente não encontrado."

    # Coleção existe mas sem o documento do cliente
    _clients_db(mongo_client, sadif_databases).create_collection(f"{PREFIX}{e2e_id}_empty")
    assert manager.find_client_modules(f"{e2e_id}_empty") == (
        "Informações do cliente não encontradas."
    )


def test_find_client_modules_fresh_client_is_empty(manager, e2e_id):
    manager.create_client_collection(f"{e2e_id}_new", "ACME", "CIID-1")
    assert manager.find_client_modules(f"{e2e_id}_new") == {}


def test_list_all_clients(manager, mongo_client, sadif_databases, e2e_id):
    assert manager.list_all_clients() == []
    names = [f"{e2e_id}_b", f"{e2e_id}_a", f"{PREFIX}{e2e_id}_nested"]
    for i, name in enumerate(names):
        manager.create_client_collection(name, f"Co{i}", f"CIID-{i}")
    # Coleções sem o prefixo de cliente não são listadas
    _clients_db(mongo_client, sadif_databases).create_collection("not_a_client")

    assert manager.list_all_clients() == sorted(names)


def test_delete_client(manager, mongo_client, sadif_databases, populated):
    keep, delete = populated
    assert manager.delete_client_collection(delete) == (
        f"Coleção do cliente {delete} deletada com sucesso."
    )
    assert _clients_db(mongo_client, sadif_databases).list_collection_names() == [PREFIX + keep]
    assert manager.list_all_clients() == [keep]
    assert manager.find_client_modules(delete) == "Cliente não encontrado."

    assert manager.delete_client_collection(delete) == "Cliente não encontrado."


def test_full_lifecycle_recreate_after_delete(manager, e2e_id):
    name = f"{e2e_id}_life"
    manager.create_client_collection(name, "ACME", "CIID-1")
    manager.update_module_info(name, "ModuloC", {"v": 1})
    manager.delete_client_collection(name)
    assert manager.create_client_collection(name, "ACME", "CIID-1").startswith("Coleção criada")
    assert manager.find_client_modules(name) == {}


# --------------------------------------------------------------------------- Export


def test_export_writes_one_json_file_per_collection(
    manager, mongo_client, sadif_databases, populated, tmp_path
):
    export_dir = tmp_path / "nested" / "export"  # diretório ainda inexistente
    exporter = ClientManagerExport(db_client=mongo_client)
    assert exporter.export_to_json(export_dir) == (
        "Collection export to JSON completed successfully."
    )

    files = sorted(p.name for p in export_dir.iterdir())
    assert files == sorted(f"{PREFIX}{name}.json" for name in populated)
    data = json.loads((export_dir / f"{PREFIX}{populated[0]}.json").read_text(encoding="utf-8"))
    assert data == [
        {
            "client_name": populated[0],
            "company": "Company0",
            "ciid": "CIID-0",
            "Modules": {"ModuloA": {"enabled": True, "keywords": ["acme"]}},
        }
    ]


def test_export_accepts_str_path_and_empty_database(sadif_databases, mongo_client, tmp_path):
    exporter = ClientManagerExport(db_client=mongo_client)
    assert exporter.export_to_json(str(tmp_path)).endswith("successfully.")
    assert list(tmp_path.iterdir()) == []


def test_export_to_invalid_path_returns_error(populated, mongo_client, tmp_path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    result = ClientManagerExport(db_client=mongo_client).export_to_json(blocker)
    assert result.startswith("Error exporting collections to JSON:")


# --------------------------------------------------------------------------- Import


def _write_client_file(directory: Path, docs: list[dict] | dict, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{PREFIX}{name}.json"
    path.write_text(json.dumps(docs), encoding="utf-8")
    return path


def test_round_trip_export_import_directory(
    manager, mongo_client, sadif_databases, populated, tmp_path
):
    db = _clients_db(mongo_client, sadif_databases)
    before = _snapshot(db)
    ClientManagerExport(db_client=mongo_client).export_to_json(tmp_path)

    for name in populated:
        manager.delete_client_collection(name)
    assert db.list_collection_names() == []

    importer = ClientManagerImport(db_client=mongo_client)
    assert importer.import_from_json(str(tmp_path)) == (
        "JSON data import to MongoDB completed successfully."
    )
    assert _snapshot(db) == before
    assert manager.list_all_clients() == sorted(populated)
    assert manager.find_client_modules(populated[1]) == {"ModuloB": {"level": 3}}

    # Reimportar sem overwrite é idempotente
    importer.import_from_json(str(tmp_path))
    assert _snapshot(db) == before


def test_import_without_overwrite_merges_with_existing(
    manager, mongo_client, sadif_databases, e2e_id, tmp_path
):
    name = f"{e2e_id}_merge"
    manager.create_client_collection(name, "ACME", "CIID-1")
    coll = _clients_db(mongo_client, sadif_databases)[PREFIX + name]
    coll.update_one({"client_name": name}, {"$set": {"local_only": "keep"}})

    _write_client_file(
        tmp_path,
        [{"client_name": name, "company": "ACME", "ciid": "CIID-1", "Modules": {"ModuloA": {}}}],
        name,
    )
    result = ClientManagerImport(db_client=mongo_client).import_from_json(str(tmp_path))
    assert result.endswith("successfully.")
    docs = list(coll.find({}, {"_id": 0}))
    assert docs == [
        {
            "client_name": name,
            "company": "ACME",
            "ciid": "CIID-1",
            "Modules": {"ModuloA": {}},
            "local_only": "keep",
        }
    ]


def test_import_with_overwrite_replaces_existing(
    manager, mongo_client, sadif_databases, e2e_id, tmp_path
):
    name = f"{e2e_id}_replace"
    manager.create_client_collection(name, "ACME", "CIID-1")
    coll = _clients_db(mongo_client, sadif_databases)[PREFIX + name]
    coll.update_one({"client_name": name}, {"$set": {"local_only": "drop"}})

    imported = {"client_name": name, "company": "ACME2", "ciid": "CIID-2", "Modules": {}}
    _write_client_file(tmp_path, [imported], name)
    result = ClientManagerImport(db_client=mongo_client).import_from_json(
        str(tmp_path), overwrite=True
    )
    assert result.endswith("successfully.")
    assert list(coll.find({}, {"_id": 0})) == [imported]
    assert _unique_index_fields(coll) == UNIQUE_FIELDS


def test_import_meta_update_recreates_collection(
    manager, mongo_client, sadif_databases, e2e_id, tmp_path
):
    name = f"{e2e_id}_meta"
    manager.create_client_collection(name, "OldCo", "CIID-OLD")
    coll = _clients_db(mongo_client, sadif_databases)[PREFIX + name]
    # Documento extra que não está no JSON deve desaparecer
    coll.insert_one({"client_name": "stale", "company": "S", "ciid": "S"})

    imported = {"client_name": name, "company": "NewCo", "ciid": "CIID-NEW", "Modules": {}}
    _write_client_file(tmp_path, [imported], name)
    result = ClientManagerImport(db_client=mongo_client).import_from_json(
        str(tmp_path), meta_update=True
    )
    assert result.endswith("successfully.")
    assert list(coll.find({}, {"_id": 0})) == [imported]
    assert _unique_index_fields(coll) == UNIQUE_FIELDS


def test_import_single_object_file_and_document_with_id(
    mongo_client, sadif_databases, e2e_id, tmp_path
):
    name = f"{e2e_id}_obj"
    doc = {"_id": "legacy", "client_name": name, "company": "C", "ciid": "I", "Modules": {}}
    _write_client_file(tmp_path, doc, name)
    importer = ClientManagerImport(db_client=mongo_client)
    assert importer.import_from_json(str(tmp_path)).endswith("successfully.")
    # Reimportar documento com _id não falha (campo imutável é ignorado no $set)
    assert importer.import_from_json(str(tmp_path)).endswith("successfully.")
    coll = _clients_db(mongo_client, sadif_databases)[PREFIX + name]
    assert list(coll.find({}, {"_id": 0})) == [
        {"client_name": name, "company": "C", "ciid": "I", "Modules": {}}
    ]


def test_import_skips_documents_without_client_name_and_empty_files(
    mongo_client, sadif_databases, e2e_id, tmp_path
):
    name = f"{e2e_id}_partial"
    _write_client_file(
        tmp_path,
        [{"company": "nameless", "ciid": "X"}, {"client_name": name, "company": "C", "ciid": "I"}],
        name,
    )
    _write_client_file(tmp_path, [], f"{e2e_id}_empty")
    result = ClientManagerImport(db_client=mongo_client).import_from_json(str(tmp_path))
    assert result.endswith("successfully.")
    db = _clients_db(mongo_client, sadif_databases)
    assert list(db[PREFIX + name].find({}, {"_id": 0})) == [
        {"client_name": name, "company": "C", "ciid": "I"}
    ]
    # Arquivo vazio cria a coleção com os índices únicos
    assert _unique_index_fields(db[f"{PREFIX}{e2e_id}_empty"]) == UNIQUE_FIELDS


def test_import_duplicate_unique_values_fails(mongo_client, sadif_databases, e2e_id, tmp_path):
    name = f"{e2e_id}_dupidx"
    _write_client_file(
        tmp_path,
        [
            {"client_name": f"{name}_1", "company": "SAME", "ciid": "1"},
            {"client_name": f"{name}_2", "company": "SAME", "ciid": "2"},
        ],
        name,
    )
    result = ClientManagerImport(db_client=mongo_client).import_from_json(str(tmp_path))
    assert result.startswith("Error importing JSON data to MongoDB:")
    assert "duplicate key" in result.lower()
    coll = _clients_db(mongo_client, sadif_databases)[PREFIX + name]
    assert coll.count_documents({}) == 1
    assert _unique_index_fields(coll) == UNIQUE_FIELDS


def test_import_invalid_json_keeps_existing_collection_on_meta_update(
    manager, mongo_client, sadif_databases, e2e_id, tmp_path
):
    name = f"{e2e_id}_broken"
    manager.create_client_collection(name, "ACME", "CIID-1")
    tmp_path.joinpath(f"{PREFIX}{name}.json").write_text("{not json", encoding="utf-8")

    result = ClientManagerImport(db_client=mongo_client).import_from_json(
        str(tmp_path), meta_update=True
    )
    assert result.startswith("Error importing JSON data to MongoDB:")
    coll = _clients_db(mongo_client, sadif_databases)[PREFIX + name]
    assert coll.count_documents({"client_name": name}) == 1


def test_import_non_object_json_is_rejected(mongo_client, sadif_databases, e2e_id, tmp_path):
    _write_client_file(tmp_path, [1, 2, 3], f"{e2e_id}_nums")
    result = ClientManagerImport(db_client=mongo_client).import_from_json(str(tmp_path))
    assert result.startswith("Error importing JSON data to MongoDB:")
    assert _clients_db(mongo_client, sadif_databases).list_collection_names() == []


def test_import_missing_directory_and_no_source(mongo_client, sadif_databases, tmp_path):
    importer = ClientManagerImport(db_client=mongo_client)
    result = importer.import_from_json(str(tmp_path / "missing"))
    assert result.startswith("Error importing JSON data to MongoDB:")
    assert "not found" in result
    assert importer.import_from_json() == (
        "Import directory not provided and GitManager not configured."
    )
    assert _clients_db(mongo_client, sadif_databases).list_collection_names() == []


def test_round_trip_through_local_git_repo(
    manager, mongo_client, sadif_databases, populated, tmp_path, local_git_repo
):
    db = _clients_db(mongo_client, sadif_databases)
    before = _snapshot(db)
    export_dir = tmp_path / "export"
    ClientManagerExport(db_client=mongo_client).export_to_json(export_dir)
    files = {
        f"clients/{p.name}": p.read_text(encoding="utf-8") for p in sorted(export_dir.iterdir())
    }
    repo_url = local_git_repo(files)

    for name in populated:
        manager.delete_client_collection(name)
    # Altera um cliente localmente para verificar overwrite/meta_update
    manager.create_client_collection(populated[0], "Changed", "CIID-X")

    git_manager = GitManager(repo_url)
    try:
        importer = ClientManagerImport(db_client=mongo_client, git_manager=git_manager)
        assert importer.import_from_json(overwrite=True).endswith("successfully.")
        assert _snapshot(db) == before
        assert git_manager.repo is not None

        db[PREFIX + populated[1]].insert_one({"client_name": "stale", "company": "s", "ciid": "s"})
        assert importer.import_from_json(meta_update=True).endswith("successfully.")
        assert _snapshot(db) == before
        assert manager.list_all_clients() == sorted(populated)
    finally:
        git_manager.cleanup()


def test_import_from_git_without_overwrite(mongo_client, sadif_databases, e2e_id, local_git_repo):
    name = f"{e2e_id}_git"
    doc = {"client_name": name, "company": "G", "ciid": "G1", "Modules": {"ModuloA": {"a": 1}}}
    repo_url = local_git_repo({f"{PREFIX}{name}.json": json.dumps([doc]), "README.md": "x"})
    git_manager = GitManager(repo_url)
    try:
        importer = ClientManagerImport(db_client=mongo_client, git_manager=git_manager)
        assert importer.import_from_json().endswith("successfully.")
        db = _clients_db(mongo_client, sadif_databases)
        assert db.list_collection_names() == [PREFIX + name]
        assert list(db[PREFIX + name].find({}, {"_id": 0})) == [doc]
        assert ClientManager(db_client=mongo_client).find_client_modules(name) == {
            "ModuloA": {"a": 1}
        }
    finally:
        git_manager.cleanup()


def test_import_from_unreachable_git_repo(mongo_client, sadif_databases, tmp_path):
    git_manager = GitManager(str(tmp_path / "does-not-exist"))
    try:
        importer = ClientManagerImport(db_client=mongo_client, git_manager=git_manager)
        assert importer.import_from_json() == "Failed to clone the Git repository."
        assert _clients_db(mongo_client, sadif_databases).list_collection_names() == []
    finally:
        git_manager.cleanup()


def test_explicit_path_takes_precedence_over_git(
    mongo_client, sadif_databases, e2e_id, tmp_path, local_git_repo
):
    git_name, dir_name = f"{e2e_id}_fromgit", f"{e2e_id}_fromdir"
    repo_url = local_git_repo(
        {
            f"{PREFIX}{git_name}.json": json.dumps(
                [{"client_name": git_name, "company": "a", "ciid": "a"}]
            )
        }
    )
    _write_client_file(
        tmp_path / "dir", [{"client_name": dir_name, "company": "b", "ciid": "b"}], dir_name
    )
    git_manager = GitManager(repo_url)
    try:
        importer = ClientManagerImport(db_client=mongo_client, git_manager=git_manager)
        assert importer.import_from_json(str(tmp_path / "dir")).endswith("successfully.")
        assert git_manager.repo is None  # não clonou
        assert _clients_db(mongo_client, sadif_databases).list_collection_names() == [
            PREFIX + dir_name
        ]
    finally:
        git_manager.cleanup()


def test_import_invalid_second_file_leaves_all_collections_untouched(
    manager, mongo_client, sadif_databases, e2e_id, tmp_path
):
    good, bad = f"{e2e_id}_a_good", f"{e2e_id}_b_bad"
    manager.create_client_collection(good, "OldCo", "OLD-1")
    manager.update_module_info(good, "ModuloA", {"keep": True})
    manager.create_client_collection(bad, "BadCo", "BAD-1")
    _write_client_file(tmp_path, [{"client_name": good, "company": "New", "ciid": "N"}], good)
    tmp_path.joinpath(f"{PREFIX}{bad}.json").write_text("[{broken", encoding="utf-8")

    db = _clients_db(mongo_client, sadif_databases)
    before = _snapshot(db)
    result = ClientManagerImport(db_client=mongo_client).import_from_json(
        str(tmp_path), meta_update=True
    )
    assert result.startswith("Error importing JSON data to MongoDB:")
    assert _snapshot(db) == before
    assert manager.find_client_modules(good) == {"ModuloA": {"keep": True}}
