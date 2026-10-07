import pytest

pytestmark = pytest.mark.e2e

import io  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import sentry_sdk  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from sadif import cli  # noqa: E402
from sadif.config.sadif_config import ENV_PREFIX, SadifConfiguration  # noqa: E402
from sadif.dataconfig import config_variables_file  # noqa: E402
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager  # noqa: E402
from sadif.utils.generete_string.markdown_string_generator import (  # noqa: E402
    MarkdownStringGenerator,
)
from sadif.utils.generete_string.random_string_generator import (  # noqa: E402
    RandomStringGenerator,
)

SRC = Path(__file__).resolve().parents[2] / "src" / "sadif"


@pytest.fixture(autouse=True)
def _no_airflow_no_sentry(monkeypatch):
    """Sem Airflow e sem Sentry real (o DSN padrão aponta para a internet)."""
    monkeypatch.delenv("AIRFLOW_HOME", raising=False)
    monkeypatch.setenv("SADIF_SENTRYDSN", "")
    monkeypatch.delenv("SADIF_MONGODB_URL", raising=False)  # vem do .env; os testes usam o JSON
    yield
    monkeypatch.setenv("SADIF_SENTRYDSN", "")
    LogManager()  # desliga o cliente Sentry que algum teste tenha apontado ao servidor local


@pytest.fixture()
def sentry_server(http_server, monkeypatch):
    """Servidor local que recebe os eventos do Sentry (DSN apontado para ele)."""
    http_server.add("/api/1/store/", "{}", content_type="application/json")
    http_server.add("/api/1/envelope/", "{}", content_type="application/json")
    host = http_server.url.split("//", 1)[1]
    monkeypatch.setenv("SADIF_SENTRYDSN", f"http://e2epublickey@{host}/1")
    return http_server


def _sentry_events(server) -> list[dict]:
    sentry_sdk.flush(timeout=5)
    return [r for r in server.requests if r["path"].startswith("/api/1/store/")]


# --------------------------------------------------------------------------------------
# SadifConfiguration
# --------------------------------------------------------------------------------------


def _keys_referenced_in_code() -> set[str]:
    pattern = re.compile(r"get_configuration\(\s*[\"']([A-Z][A-Z0-9_]+)[\"']", re.MULTILINE)
    keys = set()
    for path in SRC.rglob("*.py"):
        keys.update(pattern.findall(path.read_text(encoding="utf-8")))
    return keys


def test_default_file_has_every_key_referenced_in_code():
    config = SadifConfiguration()
    keys = _keys_referenced_in_code()
    assert "MONGODB_URL" in json.loads(Path(str(config_variables_file)).read_text())
    assert len(keys) > 10
    missing = [key for key in keys if key not in config._configurations]
    assert missing == []


def test_default_file_values_and_types():
    config = SadifConfiguration()
    assert Path(str(config.json_file_path)) == Path(str(config_variables_file))
    assert config.running_in_airflow is False
    assert config.get_configuration("MONGODB_CLIENT_PREFIX") == "Client_"
    assert isinstance(config.get_configuration("YARA_TYPE_RULES"), list)
    assert isinstance(config.get_configuration("CLIENTS_MODULES"), list)
    schema = config.get_configuration("MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_JSON_SCHEMA")
    assert schema["required"] == ["url"]
    assert config.get_configuration("KEY_THAT_DOES_NOT_EXIST") is None


def test_custom_file_str_and_pathlike(tmp_path, e2e_id):
    config_file = tmp_path / "custom.json"
    config_file.write_text(json.dumps({"MY_KEY": e2e_id, "NESTED": {"a": [1, 2]}}))
    for source in (str(config_file), config_file):
        config = SadifConfiguration(source)
        assert config.get_configuration("MY_KEY") == e2e_id
        assert config.get_configuration("NESTED") == {"a": [1, 2]}
        # O arquivo customizado substitui o padrão por completo
        assert config.get_configuration("MONGODB_URL") is None


def test_missing_file_logs_warning_and_returns_none(tmp_path, caplog):
    missing = tmp_path / "nope.json"
    with caplog.at_level(logging.WARNING):
        config = SadifConfiguration(str(missing))
    assert "JSON file not found" in caplog.text
    assert config.get_configuration("MONGODB_URL") is None


def test_directory_instead_of_file_is_not_found(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        config = SadifConfiguration(str(tmp_path))
    assert "JSON file not found" in caplog.text
    assert config._configurations == {}


@pytest.mark.parametrize("content", [b"{invalid json", b"", b"\xff\xfe{ not utf-8"])
def test_invalid_json_file_logs_error(tmp_path, caplog, content):
    config_file = tmp_path / "broken.json"
    config_file.write_bytes(content)
    with caplog.at_level(logging.ERROR):
        config = SadifConfiguration(str(config_file))
    assert "Error reading JSON file" in caplog.text
    assert config.get_configuration("ANY") is None


def test_json_file_that_is_not_an_object(tmp_path, caplog):
    config_file = tmp_path / "list.json"
    config_file.write_text("[1, 2, 3]")
    with caplog.at_level(logging.ERROR):
        config = SadifConfiguration(str(config_file))
    assert "must contain an object" in caplog.text
    assert config.get_configuration("ANY") is None


def test_env_overrides_with_json_values(tmp_path, monkeypatch, e2e_id):
    config_file = tmp_path / "vars.json"
    config_file.write_text(
        json.dumps({"PLAIN": "file", "LIST": ["a"], "OBJ": {}, "NUM": 1, "FLAG": False, "N": "x"})
    )
    monkeypatch.setenv(f"{ENV_PREFIX}PLAIN", e2e_id)
    monkeypatch.setenv(f"{ENV_PREFIX}LIST", '["Leak", "POC"]')
    monkeypatch.setenv(f"{ENV_PREFIX}OBJ", '{"k": {"v": 1}}')
    monkeypatch.setenv(f"{ENV_PREFIX}NUM", "42")
    monkeypatch.setenv(f"{ENV_PREFIX}FLAG", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}N", "null")  # JSON null -> volta ao valor do arquivo
    monkeypatch.setenv(f"{ENV_PREFIX}ONLY_ENV", "mongodb://host:1/{db}")
    config = SadifConfiguration(str(config_file))
    assert config.get_configuration("PLAIN") == e2e_id
    assert config.get_configuration("LIST") == ["Leak", "POC"]
    assert config.get_configuration("OBJ") == {"k": {"v": 1}}
    assert config.get_configuration("NUM") == 42
    assert config.get_configuration("FLAG") is True
    assert config.get_configuration("N") == "x"
    assert config.get_configuration("ONLY_ENV") == "mongodb://host:1/{db}"
    # Variável sem o prefixo não sobrescreve
    monkeypatch.setenv("PLAIN", "ignored")
    assert config.get_configuration("PLAIN") == e2e_id
    # Removida a variável, volta o valor do arquivo (lido a cada chamada)
    monkeypatch.delenv(f"{ENV_PREFIX}PLAIN")
    assert config.get_configuration("PLAIN") == "file"


def test_env_overrides_drive_real_mongodb(sadif_databases, mongo_client, e2e_id):
    config = SadifConfiguration()
    for key, name in sadif_databases.items():
        assert config.get_configuration(key) == name
    db_name = config.get_configuration("MONGODB_DATABASE_YARA")
    mongo_client[db_name]["config_check"].insert_one({"_id": e2e_id})
    assert mongo_client[db_name]["config_check"].find_one({"_id": e2e_id}) == {"_id": e2e_id}
    assert db_name in mongo_client.list_database_names()


def test_airflow_branch_without_airflow_falls_back_to_json(tmp_path, monkeypatch, caplog):
    config_file = tmp_path / "vars.json"
    config_file.write_text(json.dumps({"MONGODB_URL": "mongodb://file:27017", "L": [1]}))
    monkeypatch.setenv("AIRFLOW_HOME", str(tmp_path))
    config = SadifConfiguration(str(config_file))
    assert config.running_in_airflow is True
    with caplog.at_level(logging.WARNING):
        assert config.get_configuration("MONGODB_URL") == "mongodb://file:27017"
    assert "Airflow is not installed" in caplog.text
    assert config.get_configuration("L") == [1]
    monkeypatch.setenv("SADIF_MONGODB_URL", "mongodb://env:27017")
    assert config.get_configuration("MONGODB_URL") == "mongodb://env:27017"


def test_update_airflow_variables_outside_airflow_warns(caplog):
    config = SadifConfiguration()
    with caplog.at_level(logging.WARNING):
        config.update_airflow_variables()
    assert "Not running in Airflow environment" in caplog.text


def test_update_airflow_variables_without_airflow_installed(tmp_path, monkeypatch, caplog):
    config_file = tmp_path / "vars.json"
    config_file.write_text(json.dumps({"A": "1"}))
    monkeypatch.setenv("AIRFLOW_HOME", str(tmp_path))
    config = SadifConfiguration(str(config_file))
    config_file.write_text(json.dumps({"A": "2"}))
    with caplog.at_level(logging.ERROR):
        config.update_airflow_variables()  # não deve levantar
    assert "Error updating Airflow variables" in caplog.text
    # O JSON foi recarregado antes da tentativa de atualização
    assert config._configurations == {"A": "2"}


# --------------------------------------------------------------------------------------
# LogManager
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("level", LogManager.LOG_LEVELS)
def test_log_every_level(level, caplog, e2e_id):
    manager = LogManager()
    with caplog.at_level(logging.DEBUG):
        manager.log(level, f"msg {e2e_id}", category="git", task_state="success")
    records = [r for r in caplog.records if e2e_id in r.getMessage()]
    assert len(records) == 1
    assert records[0].name == "git"
    assert records[0].levelname == level.upper()
    assert records[0].getMessage() == f"[SUCCESS] - msg {e2e_id}"


def test_log_defaults_and_uppercase_level(caplog, e2e_id):
    manager = LogManager()
    with caplog.at_level(logging.DEBUG):
        manager.log("INFO", e2e_id)
    (record,) = (r for r in caplog.records if e2e_id in r.getMessage())
    assert record.name == "general"
    assert record.getMessage() == f"[NONE] - {e2e_id}"


def test_every_allowed_category_and_task_state_is_accepted(caplog, e2e_id):
    manager = LogManager()
    categories = LogManager.ALLOWED_CATEGORIES + LogManager.ALLOWED_CATEGORIES_BRANDING
    assert "module_ransomwhat" in LogManager.ALLOWED_CATEGORIES
    with caplog.at_level(logging.DEBUG):
        for category in categories:
            manager.log("debug", e2e_id, category=category)
        for state in LogManager.TASK_STATES:
            manager.log("debug", e2e_id, task_state=state)
    assert len([r for r in caplog.records if e2e_id in r.getMessage()]) == len(categories) + len(
        LogManager.TASK_STATES
    )


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"level": "info", "category": "not_a_category"}, "Invalid category"),
        ({"level": "info", "task_state": "exploded"}, "Invalid task state"),
        ({"level": "verbose"}, "Invalid log level"),
        ({"level": "exception"}, "Invalid log level"),
    ],
)
def test_log_validation_errors(kwargs, error, caplog, e2e_id):
    manager = LogManager()
    with caplog.at_level(logging.DEBUG), pytest.raises(ValueError, match=error):
        manager.log(message=e2e_id, **kwargs)
    assert e2e_id not in caplog.text


def test_log_with_exc_info_records_traceback(caplog, e2e_id):
    manager = LogManager()
    try:
        raise RuntimeError(e2e_id)
    except RuntimeError as error:
        exc = error
        with caplog.at_level(logging.DEBUG):
            manager.log("error", "failed", category="Database", task_state="failed", exc_info=exc)
            manager.log("warning", "warned", category="Database", exc_info=exc)
    errors = [r for r in caplog.records if r.name == "Database"]
    assert [r.levelname for r in errors] == ["ERROR", "WARNING"]
    assert all(r.exc_info and r.exc_info[1] is exc for r in errors)
    assert e2e_id in caplog.text


def test_sentry_dsn_empty_disables_sentry(caplog):
    manager = LogManager()
    assert manager.sadif_config.get_configuration("SENTRYDSN") == ""
    client = sentry_sdk.Hub.current.client
    assert client is None or (not client.dsn and client.transport is None)
    try:
        raise ValueError("no sentry")  # noqa: TRY003, EM101
    except ValueError as exc:
        with caplog.at_level(logging.ERROR):
            manager.capture_exception(exc, "captured without sentry", category="network")
    assert "captured without sentry" in caplog.text
    manager.add_breadcrumb("network", "crumb")  # não levanta sem Sentry


def test_capture_exception_reaches_sentry_once(sentry_server, caplog, e2e_id):
    manager = LogManager()
    assert sentry_sdk.Hub.current.client.dsn.endswith("/1")
    try:
        raise KeyError(e2e_id)
    except KeyError as error:
        exc = error
        with caplog.at_level(logging.ERROR):
            manager.capture_exception(exc, f"captured {e2e_id}", category="security")
    events = _sentry_events(sentry_server)
    assert len(events) == 1  # log + capture deduplicados num único evento
    assert "sentry_key=e2epublickey" in events[0]["headers"]["X-Sentry-Auth"]
    assert sentry_sdk.last_event_id() is not None
    (record,) = (r for r in caplog.records if e2e_id in r.getMessage())
    assert record.name == "security"
    assert record.exc_info[1] is exc


def test_sentry_event_carries_category_tag_without_leaking(sentry_server, e2e_id):
    """A tag 'category' vai no próprio evento e não vaza para eventos posteriores."""
    manager = LogManager()
    seen: list[dict] = []

    def record(event, _hint):
        seen.append(event)
        return event  # o evento segue para o transporte real (servidor local)

    with sentry_sdk.push_scope() as scope:
        scope.add_event_processor(record)
        try:
            raise LookupError(e2e_id)
        except LookupError as exc:
            manager.capture_exception(exc, f"tagged {e2e_id}", category="security")
        sentry_sdk.capture_message(f"after {e2e_id}")
    assert len(_sentry_events(sentry_server)) == 2
    assert [e.get("tags", {}).get("category") for e in seen] == ["security", None]
    assert seen[0]["exception"]["values"][-1]["type"] == "LookupError"
    assert seen[0]["exception"]["values"][-1]["value"] == e2e_id


def test_capture_exception_invalid_category_sends_nothing(sentry_server):
    manager = LogManager()
    with pytest.raises(ValueError, match="Invalid category"):
        manager.capture_exception(RuntimeError("x"), category="bogus")
    assert _sentry_events(sentry_server) == []


def test_add_breadcrumb_is_attached_to_next_event(sentry_server, e2e_id):
    manager = LogManager()
    for level in ["debug", "info", "warning", "error", "critical", "fatal"]:
        manager.add_breadcrumb("crawler", f"{level} {e2e_id}", level=level)
    with sentry_sdk.push_scope() as scope:
        crumbs = [c for c in scope._breadcrumbs if e2e_id in (c.get("message") or "")]
    assert [c["message"] for c in crumbs] == [
        f"{lvl} {e2e_id}" for lvl in ["debug", "info", "warning", "error", "critical", "fatal"]
    ]
    assert all(c["category"] == "crawler" for c in crumbs)
    assert [c["level"] for c in crumbs][:3] == ["debug", "info", "warning"]
    with pytest.raises(ValueError, match="Invalid category"):
        manager.add_breadcrumb("bogus", "x")
    with pytest.raises(ValueError, match="Invalid breadcrumb level"):
        manager.add_breadcrumb("crawler", "x", level="loud")
    try:
        raise OSError(e2e_id)
    except OSError as exc:
        manager.capture_exception(exc, category="crawler")
    assert len(_sentry_events(sentry_server)) == 1


def test_sentry_client_reused_until_dsn_changes(sentry_server, monkeypatch):
    LogManager()
    client = sentry_sdk.Hub.current.client
    LogManager()
    assert sentry_sdk.Hub.current.client is client
    monkeypatch.setenv("SADIF_SENTRYDSN", "")
    LogManager()
    assert sentry_sdk.Hub.current.client is not client


# --------------------------------------------------------------------------------------
# Geradores de string
# --------------------------------------------------------------------------------------


def test_markdown_document_written_to_disk(tmp_path):
    generator = MarkdownStringGenerator(string_length=8)
    document = generator.generate_markdown_document("Relatório", 3, 4, 5, language="yaml")
    path = tmp_path / "doc.md"
    path.write_text(document, encoding="utf-8")
    lines = path.read_text(encoding="utf-8").split("\n")
    assert lines[0] == "## Relatório"
    assert lines[1] == ""
    assert all(re.fullmatch(r"- [A-Za-z0-9]{8}", line) for line in lines[2:5])
    assert lines[6] == "```yaml"
    assert all(re.fullmatch(r"[A-Za-z0-9]{10,20}", line) for line in lines[7:11])
    assert lines[11] == "```"
    assert len(lines[13].split(" ")) == 5
    assert len(lines) == 14


def test_markdown_elements_and_errors():
    generator = MarkdownStringGenerator()
    for level in range(1, 7):
        assert generator.generate_title(level, "T") == f"{'#' * level} T"
    assert re.fullmatch(r"### [A-Za-z0-9]{10}", generator.generate_title(3))
    ordered = generator.generate_list(2, ordered=True).split("\n")
    assert all(item.startswith("1. ") for item in ordered)
    assert len(ordered) == 2
    assert generator.generate_code_block(1).startswith("```\n")
    for bad in (0, 7):
        with pytest.raises(ValueError, match="entre 1 e 6"):
            generator.generate_title(bad)
    with pytest.raises(ValueError, match="inteiro positivo"):
        generator.generate_list(0)
    with pytest.raises(ValueError, match="inteiro positivo"):
        generator.generate_code_block(-1)
    with pytest.raises(ValueError, match="positive integer"):
        generator.generate_paragraph(0)
    with pytest.raises(ValueError, match="inteiro positivo"):
        MarkdownStringGenerator(string_length=0)


def test_random_string_generator():
    generator = RandomStringGenerator(string_length=12)
    titles = {generator.generate_string_title("case") for _ in range(20)}
    assert len(titles) == 20
    assert all(re.fullmatch(r"test de case - [A-Za-z0-9]{12}", t) for t in titles)
    words = generator.generate_string_paragraph(7).split(" ")
    assert len(words) == 7
    assert all(re.fullmatch(r"[A-Za-z]{5,10}", w) for w in words)
    with pytest.raises(ValueError, match="inteiro positivo"):
        generator.generate_string_paragraph(0)
    with pytest.raises(ValueError, match="inteiro positivo"):
        RandomStringGenerator(string_length=-1)


def test_generated_strings_create_real_thehive_case(thehive_session, e2e_id):
    title = RandomStringGenerator().generate_string_title(e2e_id)
    description = MarkdownStringGenerator().generate_markdown_document(e2e_id, 2, 2, 3)
    body, status = thehive_session.request(
        "v1/case", method="POST", json_data={"title": title, "description": description}
    )
    assert status == 201, body
    try:
        fetched, status = thehive_session.request(f"v1/case/{body['_id']}")
        assert status == 200
        assert fetched["title"] == title
        assert fetched["description"] == description
    finally:
        thehive_session.request(f"v1/case/{body['_id']}", method="DELETE")
    _, status = thehive_session.request(f"v1/case/{body['_id']}")
    assert status == 404


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def _run_cli(*args, stdin=""):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-m", "sadif.cli", *args],  # noqa: S603
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )


def test_cli_interactive_session_subprocess(e2e_id):
    stdin = f"create\n{e2e_id}\ncreate\n{e2e_id}\nnotify\n{e2e_id}\nnotify\nghost\nfoo\nexit\n"
    result = _run_cli(stdin=stdin)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert f"User created: {e2e_id}" in out
    assert "The user already exists" in out
    assert f"Notification sent for user: {e2e_id}" in out
    assert "User not found" in out
    assert "Invalid command" in out
    assert out.rstrip().endswith("Exiting...")


def test_cli_interactive_eof_exits_cleanly():
    result = _run_cli(stdin="create\n")
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout.rstrip().endswith("Exiting...")


def test_cli_subcommands_subprocess():
    result = _run_cli("create", "rick")
    assert result.returncode == 0, result.stderr
    assert "The user already exists" in result.stdout
    result = _run_cli("notify", "morty")
    assert "Notification sent for user: morty" in result.stdout
    result = _run_cli("--help")
    assert result.returncode == 0
    assert "create" in result.stdout
    assert "notify" in result.stdout
    result = _run_cli("delete", "rick")
    assert result.returncode != 0
    result = _run_cli("create")  # argumento obrigatório ausente
    assert result.returncode != 0


def test_cli_typer_app_in_process(e2e_id):
    runner = CliRunner()
    result = runner.invoke(cli.app, ["notify", e2e_id])
    assert result.exit_code == 0
    assert "User not found" in result.stdout
    result = runner.invoke(cli.app, ["create", e2e_id])
    assert result.exit_code == 0
    assert f"User created: {e2e_id}" in result.stdout
    assert e2e_id in cli.existing_usernames
    result = runner.invoke(cli.app, ["notify", e2e_id])
    assert f"Notification sent for user: {e2e_id}" in result.stdout
    cli.existing_usernames.remove(e2e_id)


def test_cli_functions_and_main_in_process(monkeypatch, capsys, e2e_id):
    stdin = f"notify\n{e2e_id}\ncreate\n{e2e_id}\nnotify\n{e2e_id}\n\nexit\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    cli.main()
    prompt = re.compile(r"^(Enter [^:]+: )+")
    out = [prompt.sub("", line) for line in capsys.readouterr().out.splitlines()]
    assert out == [
        "User not found",
        f"User created: {e2e_id}",
        f"Notification sent for user: {e2e_id}",
        "Invalid command",
        "Exiting...",
    ]
    cli.existing_usernames.remove(e2e_id)
