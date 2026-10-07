import json

from sadif.config.sadif_config import SadifConfiguration


def test_reads_value_from_json_file(tmp_path, monkeypatch):
    monkeypatch.delenv("AIRFLOW_HOME", raising=False)
    config_file = tmp_path / "variables.json"
    config_file.write_text(json.dumps({"MONGODB_URL": "mongodb://localhost:27017"}))

    config = SadifConfiguration(str(config_file))

    assert config.get_configuration("MONGODB_URL") == "mongodb://localhost:27017"


def test_environment_overrides_json_file(tmp_path, monkeypatch):
    monkeypatch.delenv("AIRFLOW_HOME", raising=False)
    config_file = tmp_path / "variables.json"
    config_file.write_text(json.dumps({"MONGODB_URL": "mongodb://localhost:27017"}))
    monkeypatch.setenv("SADIF_MONGODB_URL", "mongodb://mongodb:27017")

    config = SadifConfiguration(str(config_file))

    assert config.get_configuration("MONGODB_URL") == "mongodb://mongodb:27017"


def test_environment_value_is_parsed_as_json(monkeypatch):
    monkeypatch.delenv("AIRFLOW_HOME", raising=False)
    monkeypatch.setenv("SADIF_YARA_TYPE_RULES", '["Leak", "POC"]')

    config = SadifConfiguration()

    assert config.get_configuration("YARA_TYPE_RULES") == ["Leak", "POC"]
