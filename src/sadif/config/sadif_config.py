import json
import logging
import os
from pathlib import Path
from typing import Any

from sadif.dataconfig import config_variables_file

ENV_PREFIX = "SADIF_"


class SadifConfiguration:
    def __init__(self, config_file: str | None = None):
        self.current_directory = Path(__file__).parent
        # Configura o caminho do arquivo JSON usando o parâmetro config_file, se fornecido
        self.json_file_path = Path(config_file) if config_file else config_variables_file
        self._configurations = {}
        self.running_in_airflow = False
        self._detect_environment()
        self._load_configurations()

    def _detect_environment(self):
        self.running_in_airflow = "AIRFLOW_HOME" in os.environ

    def _load_configurations(self):
        if not self.running_in_airflow:
            self._load_from_json_file()

    def _load_from_json_file(self):
        if not self.json_file_path.exists():
            logging.warning(f"JSON file not found: {self.json_file_path}")
            return

        try:
            with self.json_file_path.open() as file:
                self._configurations = json.load(file)
        except json.JSONDecodeError as e:
            logging.exception(f"Error reading JSON file: {self.json_file_path}: {e}")

    def _get_from_environment(self, key: str) -> Any:
        # Variáveis SADIF_<CHAVE> sobrescrevem o JSON (ex.: SADIF_MONGODB_URL)
        value = os.environ.get(f"{ENV_PREFIX}{key}")
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def get_configuration(self, key: str) -> Any:
        env_value = self._get_from_environment(key)
        if env_value is not None:
            return env_value
        if self.running_in_airflow:
            try:
                from airflow.models import Variable

                return Variable.get(key)
            except ImportError:
                logging.warning("Airflow is not installed or cannot be found.")
            except Exception as e:
                logging.exception(f"Failed to access Airflow Variable: {e}")
        return self._configurations.get(key)

    def update_airflow_variables(self):
        """
        Update Airflow variables with the configurations loaded from the JSON file, if running in an Airflow environment.
        This method now ensures to reload configurations from the JSON file before updating Airflow variables.
        """
        if not self.running_in_airflow:
            logging.warning(
                "Not running in Airflow environment. Airflow variables will not be updated."
            )
            return

        # Recarrega as configurações do arquivo JSON para garantir que as últimas configurações sejam usadas.
        self._load_from_json_file()

        try:
            from airflow.models import Variable

            for key, value in self._configurations.items():
                Variable.set(key, value)
            logging.info("Airflow variables successfully updated.")
        except Exception as e:
            logging.exception(f"Error updating Airflow variables: {e}")
