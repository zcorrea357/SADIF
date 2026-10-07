import json
import logging
import os
from pathlib import Path
from typing import Any

from sadif.dataconfig import config_variables_file

ENV_PREFIX = "SADIF_"


class SadifConfiguration:
    def __init__(self, config_file: str | os.PathLike | None = None):
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
        # O JSON é sempre carregado: no Airflow ele serve de fallback quando a Variable
        # não existe ou quando o Airflow não pode ser importado.
        self._load_from_json_file()

    def _load_from_json_file(self):
        if not self.json_file_path.is_file():
            logging.warning(f"JSON file not found: {self.json_file_path}")
            return

        try:
            with self.json_file_path.open(encoding="utf-8") as file:
                configurations = json.load(file)
        except (OSError, ValueError) as e:
            logging.exception(f"Error reading JSON file: {self.json_file_path}: {e}")
            return
        if not isinstance(configurations, dict):
            logging.error(f"JSON file must contain an object: {self.json_file_path}")
            return
        self._configurations = configurations

    @staticmethod
    def _parse_value(value: str) -> Any:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def _get_from_environment(self, key: str) -> Any:
        # Variáveis SADIF_<CHAVE> sobrescrevem o JSON (ex.: SADIF_MONGODB_URL)
        value = os.environ.get(f"{ENV_PREFIX}{key}")
        if value is None:
            return None
        return self._parse_value(value)

    def get_configuration(self, key: str) -> Any:
        env_value = self._get_from_environment(key)
        if env_value is not None:
            return env_value
        if self.running_in_airflow:
            try:
                from airflow.models import Variable

                airflow_value = Variable.get(key, default_var=None)
                if airflow_value is not None:
                    return (
                        self._parse_value(airflow_value)
                        if isinstance(airflow_value, str)
                        else airflow_value
                    )
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
                # Listas/objetos são gravados como JSON para que get_configuration os restaure
                Variable.set(key, value, serialize_json=not isinstance(value, str))
            logging.info("Airflow variables successfully updated.")
        except Exception as e:
            logging.exception(f"Error updating Airflow variables: {e}")
