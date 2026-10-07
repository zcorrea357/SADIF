import pytest

pytestmark = pytest.mark.e2e

from pathlib import Path  # noqa: E402

import yara  # noqa: E402

from sadif.clientmanager.client_data_manager import ClientManager  # noqa: E402
from sadif.config.sadif_config import SadifConfiguration  # noqa: E402
from sadif.frameworks_drivers.gitmanager import GitManager  # noqa: E402
from sadif.frameworks_drivers.sadif_yara.yara_compiler import SadifYaraCompiler  # noqa: E402
from sadif.frameworks_drivers.sadif_yara.yara_crud import YaraCrud  # noqa: E402
from sadif.frameworks_drivers.sadif_yara.yara_import import YaraRulesImporter  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "infra" / "fixtures" / "yara_rules"
CLIENTS = ("Internal", "Acme")
TYPES = tuple(SadifConfiguration().get_configuration("YARA_TYPE_RULES"))
PREFIX = SadifConfiguration().get_configuration("MONGODB_CLIENT_PREFIX")

# Texto de exemplo que deve casar com exatamente uma regra (cliente, tipo).
SAMPLES = {
    ("Internal", "Vips"): "Dossie com CPF e endereco de mariana albuquerque publicado no forum",
    (
        "Internal",
        "POC",
    ): "ambiente de teste aberto em https://intranet-poc.internal-corp.example/login",
    ("Internal", "Leak"): "combo list: joao.silva@internal-corp.example password: Hunter2!",
    (
        "Internal",
        "Domino",
    ): "Lotus Domino Server em http://mail.internal-corp.example/names.nsf?Open",
    ("Internal", "Incidente"): "Atualizacao do ticket INC-INTERNAL-2024-0042 sobre vazamento",
    ("Internal", "StringMatch"): "Documento: PROJETO AURORA CONFIDENCIAL - nao distribuir",
    ("Acme", "Vips"): "Telefone pessoal de Beatriz Montenegro vendido em canal do Telegram",
    ("Acme", "POC"): "subdominio staging-poc.acme-bank.example sem autenticacao",
    ("Acme", "Leak"): "dump: carla@acme-bank.example senha= acme@2024",
    ("Acme", "Domino"): "indice exposto https://webmail.acme-bank.example/names.nsf",
    ("Acme", "Incidente"): "Relatorio do incidente INC-ACME-2023-1234 anexado",
    ("Acme", "StringMatch"): "Planilha da Operacao Falcao Acme vazada",
}
NEUTRAL_TEXT = "Noticia comum sobre o clima de hoje, sem nenhuma referencia a clientes."
VALID_FILES = sorted(f"{c}Monitoramento{t}01.yar" for c in CLIENTS for t in TYPES)
NEGATIVE_FILES = {
    "no_client": "UnknownCorpMonitoramentoVips01.yar",
    "no_type": "AcmeMonitoramentoGenerico01.yar",
    "no_name": "no_rule_name.yar",
    "syntax": "AcmeMonitoramentoLeak99.yar",
    "duplicate": "AcmeMonitoramentoVips01_duplicate.yar",
}
DUPLICATE_CONTENT = (FIXTURES / "Invalid" / NEGATIVE_FILES["duplicate"]).read_text()


def rule_name(client: str, rule_type: str) -> str:
    return f"{client}Monitoramento{rule_type}01"


def fixture_content(client: str, rule_type: str) -> str:
    return (FIXTURES / client / f"{rule_name(client, rule_type)}.yar").read_text()


def all_fixture_files() -> dict[str, str]:
    return {
        str(path.relative_to(FIXTURES)): path.read_text()
        for path in sorted(FIXTURES.rglob("*.yar"))
    }


def yara_db(mongo_client, sadif_databases):
    return mongo_client[sadif_databases["MONGODB_DATABASE_YARA"]]


def create_clients(mongo_client, *clients: str) -> ClientManager:
    manager = ClientManager(db_client=mongo_client)
    for index, client in enumerate(clients):
        message = manager.create_client_collection(client, f"{client} S.A.", f"CIID-{index:04d}")
        assert message == f"Coleção criada para o cliente: {client}."
    assert manager.list_all_clients() == sorted(clients)
    return manager


def docs_by_client(db) -> dict[str, dict[str, dict]]:
    return {
        name[len(PREFIX) :]: {doc["rule_name"]: doc for doc in db[name].find({}, {"_id": 0})}
        for name in db.list_collection_names()
        if name.startswith(PREFIX)
    }


def assert_fixture_documents(db, acme_vips_content: str) -> None:
    stored = docs_by_client(db)
    assert set(stored) == set(CLIENTS)
    for client in CLIENTS:
        assert set(stored[client]) == {rule_name(client, t) for t in TYPES}
        for rule_type in TYPES:
            doc = stored[client][rule_name(client, rule_type)]
            expected_content = (
                acme_vips_content
                if (client, rule_type) == ("Acme", "Vips")
                else fixture_content(client, rule_type)
            )
            assert doc == {
                "rule_name": rule_name(client, rule_type),
                "rule_content": expected_content,
                "rule_type": rule_type,
                "client": client,
            }


@pytest.fixture()
def git_managers():
    created: list[GitManager] = []

    def make(url: str) -> GitManager:
        manager = GitManager(url)
        created.append(manager)
        return manager

    yield make
    for manager in created:
        manager.cleanup()


@pytest.fixture()
def imported_fixtures(mongo_client, sadif_databases):
    """Clientes criados e todas as fixtures importadas do diretório (overwrite=False)."""
    create_clients(mongo_client, *CLIENTS)
    importer = YaraRulesImporter(str(FIXTURES), list(CLIENTS), db_client=mongo_client)
    summary = importer.import_rules()
    assert summary["imported"] == len(VALID_FILES)
    return yara_db(mongo_client, sadif_databases)


# --------------------------------------------------------------------------- fixtures


def test_fixtures_cover_every_type_for_every_client():
    for client in CLIENTS:
        files = sorted(p.name for p in (FIXTURES / client).glob("*.yar"))
        assert files == sorted(f"{rule_name(client, t)}.yar" for t in TYPES)
        for rule_type in TYPES:
            rules = yara.compile(source=fixture_content(client, rule_type))
            matches = rules.match(data=SAMPLES[(client, rule_type)])
            assert [m.rule for m in matches] == [rule_name(client, rule_type)]
    negatives = sorted(p.name for p in (FIXTURES / "Invalid").glob("*.yar"))
    assert negatives == sorted(NEGATIVE_FILES.values())
    with pytest.raises(yara.SyntaxError):
        yara.compile(filepath=str(FIXTURES / "Invalid" / NEGATIVE_FILES["syntax"]))


# --------------------------------------------------------------------------- importer


def test_import_directory_without_overwrite(mongo_client, sadif_databases):
    create_clients(mongo_client, *CLIENTS)
    importer = YaraRulesImporter(str(FIXTURES), list(CLIENTS), db_client=mongo_client)
    summary = importer.import_rules()

    assert summary == {
        "imported": 12,
        "overwritten": 0,
        "ignored": 4,
        # ordem determinística: diretórios e arquivos ordenados
        "ignored_rules": [
            NEGATIVE_FILES["no_type"],
            NEGATIVE_FILES["syntax"],
            NEGATIVE_FILES["no_client"],
            NEGATIVE_FILES["no_name"],
        ],
        "duplicated_rules": ["AcmeMonitoramentoVips01"],
        "invalid_rules": [NEGATIVE_FILES["syntax"]],
    }
    assert importer.imported_count == 12
    assert importer.ignored_count == 4
    db = yara_db(mongo_client, sadif_databases)
    # O duplicado não sobrescreve a regra original; regras inválidas não entram no banco.
    assert_fixture_documents(db, fixture_content("Acme", "Vips"))
    assert f"{PREFIX}UnknownCorp" not in db.list_collection_names()
    assert db[f"{PREFIX}Acme"].find_one({"rule_name": "AcmeMonitoramentoGenerico01"}) is None
    assert db[f"{PREFIX}Acme"].find_one({"rule_name": "AcmeMonitoramentoLeak99"}) is None


def test_import_directory_with_overwrite(mongo_client, sadif_databases):
    create_clients(mongo_client, *CLIENTS)
    importer = YaraRulesImporter(
        str(FIXTURES), list(CLIENTS), db_client=mongo_client, overwrite=True
    )
    summary = importer.import_rules()

    assert summary["imported"] == 12
    assert summary["overwritten"] == 1  # o duplicado substitui a regra AcmeMonitoramentoVips01
    assert summary["duplicated_rules"] == []
    db = yara_db(mongo_client, sadif_databases)
    assert_fixture_documents(db, DUPLICATE_CONTENT)


def test_reimport_flags_duplicates_or_overwrites(mongo_client, sadif_databases):
    create_clients(mongo_client, *CLIENTS)
    db = yara_db(mongo_client, sadif_databases)
    YaraRulesImporter(str(FIXTURES), list(CLIENTS), db_client=mongo_client).import_rules()
    db[f"{PREFIX}Internal"].update_one(
        {"rule_name": "InternalMonitoramentoPOC01"}, {"$set": {"rule_content": "stale"}}
    )

    again = YaraRulesImporter(str(FIXTURES), list(CLIENTS), db_client=mongo_client).import_rules()
    assert again["imported"] == 0
    assert again["overwritten"] == 0
    assert len(again["duplicated_rules"]) == 13  # 12 regras + o arquivo duplicado
    stale = db[f"{PREFIX}Internal"].find_one({"rule_name": "InternalMonitoramentoPOC01"})
    assert stale["rule_content"] == "stale"
    assert db[f"{PREFIX}Internal"].count_documents({}) == 6

    overwrite = YaraRulesImporter(
        str(FIXTURES), list(CLIENTS), db_client=mongo_client, overwrite=True
    ).import_rules()
    assert overwrite["imported"] == 0
    assert overwrite["overwritten"] == 13
    assert_fixture_documents(db, DUPLICATE_CONTENT)
    assert db[f"{PREFIX}Acme"].count_documents({}) == 6


def test_meta_update_recreates_only_the_given_clients(mongo_client, sadif_databases):
    create_clients(mongo_client, *CLIENTS, "Other")
    db = yara_db(mongo_client, sadif_databases)
    db[f"{PREFIX}Acme"].insert_one(
        {"rule_name": "AcmeMonitoramentoVips77", "rule_content": "old", "client": "Acme"}
    )
    db[f"{PREFIX}Other"].insert_one({"rule_name": "OtherMonitoramentoPOC01", "rule_content": "x"})

    summary = YaraRulesImporter(str(FIXTURES), list(CLIENTS), db_client=mongo_client).import_rules(
        meta_update=True
    )

    assert summary["imported"] == 12
    assert db[f"{PREFIX}Acme"].find_one({"rule_name": "AcmeMonitoramentoVips77"}) is None
    assert db[f"{PREFIX}Other"].count_documents({}) == 1  # cliente fora da lista intocado
    stored = docs_by_client(db)
    del stored["Other"]
    assert {c: set(r) for c, r in stored.items()} == {
        c: {rule_name(c, t) for t in TYPES} for c in CLIENTS
    }


def test_import_from_git_repository(mongo_client, sadif_databases, local_git_repo, git_managers):
    create_clients(mongo_client, *CLIENTS)
    repo = local_git_repo({f"rules/{k}": v for k, v in all_fixture_files().items()})
    manager = git_managers(repo)
    importer = YaraRulesImporter(None, list(CLIENTS), db_client=mongo_client, git_manager=manager)
    assert importer.directory == manager.repo_dir
    assert (Path(manager.repo_dir) / "rules" / "Acme" / "AcmeMonitoramentoPOC01.yar").is_file()

    summary = importer.import_rules()
    assert summary["imported"] == 12
    assert summary["duplicated_rules"] == ["AcmeMonitoramentoVips01"]
    assert summary["invalid_rules"] == [NEGATIVE_FILES["syntax"]]
    assert_fixture_documents(
        yara_db(mongo_client, sadif_databases), fixture_content("Acme", "Vips")
    )


def test_import_from_git_updates_with_overwrite_and_meta_update(
    mongo_client, sadif_databases, local_git_repo, git_managers
):
    create_clients(mongo_client, *CLIENTS)
    db = yara_db(mongo_client, sadif_databases)
    first = local_git_repo({k: v for k, v in all_fixture_files().items() if "Invalid" not in k})
    YaraRulesImporter(
        None, list(CLIENTS), db_client=mongo_client, git_manager=git_managers(first)
    ).import_rules()
    assert db[f"{PREFIX}Internal"].count_documents({}) == 6

    new_content = fixture_content("Internal", "StringMatch").replace(
        "Projeto Aurora Confidencial", "Projeto Boreal Confidencial"
    )
    second = local_git_repo({"Internal/InternalMonitoramentoStringMatch01.yar": new_content})

    kept = YaraRulesImporter(
        None, list(CLIENTS), db_client=mongo_client, git_manager=git_managers(second)
    ).import_rules()
    assert kept["duplicated_rules"] == ["InternalMonitoramentoStringMatch01"]
    doc = db[f"{PREFIX}Internal"].find_one({"rule_name": "InternalMonitoramentoStringMatch01"})
    assert doc["rule_content"] == fixture_content("Internal", "StringMatch")

    updated = YaraRulesImporter(
        None,
        list(CLIENTS),
        db_client=mongo_client,
        git_manager=git_managers(second),
        overwrite=True,
    ).import_rules()
    assert updated["overwritten"] == 1
    doc = db[f"{PREFIX}Internal"].find_one({"rule_name": "InternalMonitoramentoStringMatch01"})
    assert doc["rule_content"] == new_content
    assert db[f"{PREFIX}Internal"].count_documents({}) == 6

    meta = YaraRulesImporter(
        None, list(CLIENTS), db_client=mongo_client, git_manager=git_managers(second)
    ).import_rules(meta_update=True)
    assert meta["imported"] == 1
    assert [d["rule_name"] for d in db[f"{PREFIX}Internal"].find()] == [
        "InternalMonitoramentoStringMatch01"
    ]
    assert f"{PREFIX}Acme" not in db.list_collection_names()


def test_import_from_unreachable_git_repository(
    mongo_client, sadif_databases, tmp_path, git_managers
):
    create_clients(mongo_client, *CLIENTS)
    manager = git_managers(str(tmp_path / "does-not-exist"))
    importer = YaraRulesImporter(None, list(CLIENTS), db_client=mongo_client, git_manager=manager)
    assert importer.directory is None
    summary = importer.import_rules(meta_update=True)
    assert summary["imported"] == 0
    assert summary["ignored"] == 0
    assert docs_by_client(yara_db(mongo_client, sadif_databases)) == {}


def test_import_missing_directory_and_empty_clients(mongo_client, sadif_databases, tmp_path):
    db = yara_db(mongo_client, sadif_databases)
    missing = YaraRulesImporter(str(tmp_path / "missing"), list(CLIENTS), db_client=mongo_client)
    assert missing.import_rules()["imported"] == 0

    no_clients = YaraRulesImporter(str(FIXTURES), [], db_client=mongo_client).import_rules()
    assert no_clients["imported"] == 0
    assert no_clients["ignored"] == 17  # sem clientes, todos os arquivos são ignorados
    assert db.list_collection_names() == []


def test_import_relative_directory_and_extensions(
    mongo_client, sadif_databases, tmp_path, monkeypatch
):
    rules_dir = tmp_path / "relative" / "nested" / "deep"
    rules_dir.mkdir(parents=True)
    (rules_dir / "AcmeMonitoramentoPOC01.yara").write_text(fixture_content("Acme", "POC"))
    (rules_dir / "notes.txt").write_text("rule AcmeMonitoramentoVips09 { condition: true }")
    (rules_dir / ".hidden").mkdir()
    (rules_dir / ".hidden" / "AcmeMonitoramentoLeak01.yar").write_text(
        fixture_content("Acme", "Leak")
    )
    monkeypatch.chdir(tmp_path)

    summary = YaraRulesImporter("relative", ["Acme"], db_client=mongo_client).import_rules()
    assert summary["imported"] == 1
    assert set(docs_by_client(yara_db(mongo_client, sadif_databases))["Acme"]) == {
        "AcmeMonitoramentoPOC01"
    }


def test_parse_rule_ignores_comments_and_supports_modifiers(tmp_path):
    importer_cls = YaraRulesImporter.__new__(YaraRulesImporter)
    cases = {
        "comment.yar": "// rule Fake\n/* rule Fake2 */\nrule AcmeMonitoramentoPOC02 { condition: true }",
        "private.yar": 'import "math"\n\nprivate global rule AcmeMonitoramentoLeak02 : tag\n{ condition: true }',
        "meta.yar": 'rule AcmeMonitoramentoVips02 { meta: d = "rule Other" condition: true }',
    }
    expected = {
        "comment.yar": "AcmeMonitoramentoPOC02",
        "private.yar": "AcmeMonitoramentoLeak02",
        "meta.yar": "AcmeMonitoramentoVips02",
    }
    for filename, content in cases.items():
        path = tmp_path / filename
        path.write_text(content)
        name, data = importer_cls.parse_rule(path)
        assert (name, data) == (expected[filename], content)

    name, content = importer_cls.parse_rule(FIXTURES / "Invalid" / NEGATIVE_FILES["no_name"])
    assert name is None
    assert "rule nao" in content


def test_client_resolution_prefers_longest_prefix(mongo_client, sadif_databases, tmp_path):
    for client in ("Acme", "AcmeBank"):
        content = fixture_content("Acme", "Vips").replace(
            "AcmeMonitoramentoVips01", f"{client}MonitoramentoVips01"
        )
        (tmp_path / f"{client}MonitoramentoVips01.yar").write_text(content)

    importer = YaraRulesImporter(str(tmp_path), ["Acme", "AcmeBank"], db_client=mongo_client)
    assert importer.resolve_client_and_type("AcmeBankMonitoramentoVips01") == ("AcmeBank", "Vips")
    assert importer.resolve_client_and_type("AcmeMonitoramentoDomino03") == ("Acme", "Domino")
    assert importer.resolve_client_and_type("AcmeMonitoramentoOutro01") == (None, None)
    assert importer.import_rules()["imported"] == 2
    stored = docs_by_client(yara_db(mongo_client, sadif_databases))
    assert set(stored["Acme"]) == {"AcmeMonitoramentoVips01"}
    assert set(stored["AcmeBank"]) == {"AcmeBankMonitoramentoVips01"}
    assert stored["AcmeBank"]["AcmeBankMonitoramentoVips01"]["client"] == "AcmeBank"


# --------------------------------------------------------------------------- compiler


@pytest.mark.parametrize(("client", "rule_type"), sorted(SAMPLES))
def test_match_text_each_rule_type_and_client(mongo_client, imported_fixtures, client, rule_type):
    compiler = SadifYaraCompiler(db_client=mongo_client)
    results = compiler.match_text(SAMPLES[(client, rule_type)])

    assert results
    assert {(r["rule_name"], r["client_name"], r["yara_rule_type"]) for r in results} == {
        (rule_name(client, rule_type), client, rule_type)
    }
    for result in results:
        assert set(result) == {"rule_name", "yara_match", "client_name", "yara_rule_type"}
        assert result["yara_match"].identifier.startswith("$")
        assert result["yara_match"].instances


@pytest.mark.parametrize(("client", "rule_type"), sorted(SAMPLES))
def test_match_file_each_rule_type_and_client(
    mongo_client, imported_fixtures, tmp_path, client, rule_type
):
    sample = tmp_path / f"{client}_{rule_type}.txt"
    sample.write_text(f"cabecalho\n{SAMPLES[(client, rule_type)]}\nrodape\n")
    results = SadifYaraCompiler(db_client=mongo_client).match_file(str(sample))
    assert {(r["rule_name"], r["client_name"], r["yara_rule_type"]) for r in results} == {
        (rule_name(client, rule_type), client, rule_type)
    }


def test_match_text_details_and_multiple_rules(mongo_client, imported_fixtures):
    compiler = SadifYaraCompiler(db_client=mongo_client)
    vips = compiler.match_text("Mariana Albuquerque e Rodrigo Tavares no mesmo vazamento")
    assert sorted(r["yara_match"].identifier for r in vips) == ["$vip1", "$vip2"]
    assert vips[0]["yara_match"].instances[0].matched_data in (
        b"Mariana Albuquerque",
        b"Rodrigo Tavares",
    )

    combined = " | ".join(SAMPLES.values())
    results = compiler.match_text(combined)
    assert {(r["rule_name"], r["client_name"], r["yara_rule_type"]) for r in results} == {
        (rule_name(c, t), c, t) for c, t in SAMPLES
    }
    from_bytes = compiler.match_text(combined.encode())
    assert sorted(r["rule_name"] for r in from_bytes) == sorted(r["rule_name"] for r in results)


def test_non_matching_text_and_file(mongo_client, imported_fixtures, tmp_path):
    compiler = SadifYaraCompiler(db_client=mongo_client)
    assert compiler.match_text(NEUTRAL_TEXT) == []
    assert compiler.match_text("") == []
    # Leak exige domínio E senha: só o domínio não basta.
    assert compiler.match_text("contato: carla@acme-bank.example") == []
    # Fixtures negativas nunca foram importadas, então não casam.
    assert compiler.match_text("Fernando Unknowncorp acme-generico-token acme-broken-token") == []
    neutral = tmp_path / "neutral.txt"
    neutral.write_text(NEUTRAL_TEXT)
    assert compiler.match_file(str(neutral)) == []
    assert compiler.match_file(str(tmp_path / "missing.txt")) == []


def test_match_with_empty_database(mongo_client, sadif_databases):
    create_clients(mongo_client, *CLIENTS)
    compiler = SadifYaraCompiler(db_client=mongo_client)
    assert compiler.match_text(SAMPLES[("Acme", "POC")]) == []


def test_broken_rule_in_database_does_not_break_other_rules(mongo_client, imported_fixtures):
    imported_fixtures[f"{PREFIX}Acme"].insert_one(
        {
            "rule_name": "AcmeMonitoramentoLeak99",
            "rule_content": (FIXTURES / "Invalid" / NEGATIVE_FILES["syntax"]).read_text(),
            "rule_type": "Leak",
            "client": "Acme",
        }
    )
    compiler = SadifYaraCompiler(db_client=mongo_client)
    compiled = compiler.compile_rules()
    assert compiled is not None
    assert compiler.invalid_rules == ["AcmeMonitoramentoLeak99"]

    for (client, rule_type), text in SAMPLES.items():
        results = compiler.match_text(text)
        assert {(r["rule_name"], r["client_name"], r["yara_rule_type"]) for r in results} == {
            (rule_name(client, rule_type), client, rule_type)
        }
    assert compiler.match_text("acme-broken-token") == []


def test_rules_of_unregistered_clients_are_not_reported(mongo_client, sadif_databases):
    create_clients(mongo_client, "Internal")  # Acme não é cliente cadastrado
    YaraRulesImporter(str(FIXTURES), list(CLIENTS), db_client=mongo_client).import_rules()
    compiler = SadifYaraCompiler(db_client=mongo_client)
    assert compiler.match_text(SAMPLES[("Acme", "Vips")]) == []
    assert {r["client_name"] for r in compiler.match_text(SAMPLES[("Internal", "Vips")])} == {
        "Internal"
    }


def test_same_rule_name_in_two_clients_does_not_collide(mongo_client, sadif_databases):
    create_clients(mongo_client, *CLIENTS)
    db = yara_db(mongo_client, sadif_databases)
    content = 'rule SharedMonitoramentoStringMatch01 { strings: $s = "token compartilhado" condition: $s }'
    for client in CLIENTS:
        db[f"{PREFIX}{client}"].insert_one(
            {
                "rule_name": "SharedMonitoramentoStringMatch01",
                "rule_content": content,
                "rule_type": "StringMatch",
                "client": client,
            }
        )
    results = SadifYaraCompiler(db_client=mongo_client).match_text("um token compartilhado aqui")
    assert sorted((r["client_name"], r["yara_rule_type"]) for r in results) == [
        ("Acme", "StringMatch"),
        ("Internal", "StringMatch"),
    ]


def test_rule_inserted_by_yara_crud_is_matched_by_name(mongo_client, sadif_databases):
    create_clients(mongo_client, *CLIENTS)
    crud = YaraCrud(db_client=mongo_client)
    name, content = crud.parse_rule(fixture_content("Acme", "Domino"))
    assert crud.insert_rule("Acme", name, content) is not None
    stored = yara_db(mongo_client, sadif_databases)[f"{PREFIX}Acme"].find_one({"rule_name": name})
    assert "rule_type" not in stored  # YaraCrud não grava tipo/cliente

    results = SadifYaraCompiler(db_client=mongo_client).match_text(SAMPLES[("Acme", "Domino")])
    assert {(r["rule_name"], r["client_name"], r["yara_rule_type"]) for r in results} == {
        ("AcmeMonitoramentoDomino01", "Acme", "Domino")
    }


def test_rule_of_unregistered_client_is_not_attributed_to_a_prefix_client(
    mongo_client, sadif_databases, tmp_path
):
    # Só "Acme" é cliente cadastrado; a regra pertence à coleção de "AcmeBank" (não cadastrado).
    create_clients(mongo_client, "Acme")
    content = fixture_content("Acme", "Vips").replace(
        "AcmeMonitoramentoVips01", "AcmeBankMonitoramentoVips01"
    )
    (tmp_path / "AcmeBankMonitoramentoVips01.yar").write_text(content)
    summary = YaraRulesImporter(
        str(tmp_path), ["Acme", "AcmeBank"], db_client=mongo_client
    ).import_rules()
    assert summary["imported"] == 1
    db = yara_db(mongo_client, sadif_databases)
    assert db[f"{PREFIX}AcmeBank"].count_documents({"client": "AcmeBank"}) == 1

    # Não pode ser reportada como do cliente "Acme" só porque o nome começa com "Acme".
    assert SadifYaraCompiler(db_client=mongo_client).match_text(SAMPLES[("Acme", "Vips")]) == []


def test_file_with_several_rules_reports_each_rule_with_its_own_type(
    mongo_client, sadif_databases, tmp_path
):
    create_clients(mongo_client, "Acme")
    content = (
        'rule AcmeMonitoramentoPOC05 { strings: $a = "poc-cinco" condition: $a }\n'
        'rule AcmeMonitoramentoLeak05 { strings: $b = "leak-cinco" condition: $b }\n'
    )
    (tmp_path / "AcmeMultiplas.yar").write_text(content)
    summary = YaraRulesImporter(str(tmp_path), ["Acme"], db_client=mongo_client).import_rules()
    assert summary["imported"] == 1
    doc = yara_db(mongo_client, sadif_databases)[f"{PREFIX}Acme"].find_one({}, {"_id": 0})
    assert doc == {
        "rule_name": "AcmeMonitoramentoPOC05",
        "rule_content": content,
        "rule_type": "POC",
        "client": "Acme",
    }

    results = SadifYaraCompiler(db_client=mongo_client).match_text("poc-cinco e leak-cinco")
    assert sorted((r["rule_name"], r["client_name"], r["yara_rule_type"]) for r in results) == [
        ("AcmeMonitoramentoLeak05", "Acme", "Leak"),
        ("AcmeMonitoramentoPOC05", "Acme", "POC"),
    ]


def test_import_ignores_non_utf8_file(mongo_client, sadif_databases, tmp_path):
    (tmp_path / "AcmeMonitoramentoPOC01.yar").write_text(fixture_content("Acme", "POC"))
    (tmp_path / "AcmeMonitoramentoVips03.yar").write_bytes(
        b'rule AcmeMonitoramentoVips03 { strings: $a = "Jos\xe9" condition: $a }'
    )
    summary = YaraRulesImporter(str(tmp_path), ["Acme"], db_client=mongo_client).import_rules()
    assert summary["imported"] == 1
    assert summary["ignored_rules"] == ["AcmeMonitoramentoVips03.yar"]
    assert set(docs_by_client(yara_db(mongo_client, sadif_databases))["Acme"]) == {
        "AcmeMonitoramentoPOC01"
    }


def test_shared_compiler_is_thread_safe(mongo_client, imported_fixtures):
    # O BaseCrawler compartilha um único SadifYaraCompiler entre as threads do crawl
    from concurrent.futures import ThreadPoolExecutor

    compiler = SadifYaraCompiler(db_client=mongo_client)
    cases = sorted(SAMPLES) * 5

    def match(case):
        client, rule_type = case
        results = compiler.match_text(SAMPLES[case])
        return case, {(r["rule_name"], r["client_name"], r["yara_rule_type"]) for r in results}

    with ThreadPoolExecutor(max_workers=10) as executor:
        for (client, rule_type), found in executor.map(match, cases):
            assert found == {(rule_name(client, rule_type), client, rule_type)}
