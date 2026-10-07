import os
import re
from pathlib import Path

from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class YaraRulesImporter:
    """
    Class for importing YARA rules.
    """

    def __init__(self, directory, clients, db_client=None, git_manager=None, overwrite=False):
        """
        Initializes the YaraRulesImporter class.
        """
        self.sadif_internal_config = SadifConfiguration()
        self.client = db_client if db_client else MongoClient("localhost", 27017)
        self.db = self.client[self.sadif_internal_config.get_configuration("MONGODB_DATABASE_YARA")]
        self.mongo_client_prefix = self.sadif_internal_config.get_configuration(
            "MONGODB_CLIENT_PREFIX"
        )
        self.yara_type_rules = self.sadif_internal_config.get_configuration("YARA_TYPE_RULES")
        self.git_manager = git_manager
        self.directory = directory
        self.clients = clients
        self.overwrite = overwrite
        self.logger = LogManager()
        self.imported_count = 0
        self.ignored_count = 0
        self.ignored_rules = []
        self.temp_dir = None

        self.duplicated_rules = []
        self.overwrite_count = 0

        if self.git_manager:
            cloned_dir = self.git_manager.clone_repo()
            if cloned_dir:
                self.directory = cloned_dir
            else:
                self.logger.log("error", "Error in cloning the Git repository")

    def perform_meta_update(self):
        """
        Realiza a meta atualização, deletando e recriando as coleções de regras YARA.
        """
        for client in self.clients:
            collection_name = f"{self.mongo_client_prefix}{client}"
            self.db.drop_collection(collection_name)
            self.logger.log(
                "info",
                f"Collection {collection_name} deleted for meta update",
                category="yara",
                task_state="running",
            )

    def import_rules(self, meta_update=False):
        """
        Importa regras do diretório especificado com suporte a meta atualização.
        """
        if meta_update:
            self.perform_meta_update()

        directory_path = Path(self.directory)
        for root, dirs, files in os.walk(directory_path):
            for filename in files:
                if filename.endswith(".yar"):
                    rule_path = directory_path / root / filename
                    rule_name, rule_data = self.parse_rule(rule_path)
                    if rule_name:
                        self.insert_rule(rule_name, rule_data, filename)
                    else:
                        self.ignored_rules.append(filename)
                        self.ignored_count += 1
                        self.logger.log(
                            "warning",
                            f"Rule {filename} ignored - couldn't find rule name",
                            category="yara",
                            task_state="skipped",
                        )

        # Logging the summary of import process
        self.logger.log(
            "info", f"Imported Rules: {self.imported_count}", category="yara", task_state="success"
        )
        self.logger.log(
            "info",
            f"Rules overwritten: {self.overwrite_count}",
            category="yara",
            task_state="success",
        )  # Log overwrite count
        self.logger.log(
            "info", f"Ignored Rules: {self.ignored_count}", category="yara", task_state="skipped"
        )

        if self.ignored_count > 0:
            self.logger.log(
                "info",
                f"Ignored Rules (names): {self.ignored_rules}",
                category="yara",
                task_state="skipped",
            )
        if self.duplicated_rules:
            self.logger.log(
                "info",
                f"Duplicated Rules (names): {self.duplicated_rules}",
                category="yara",
                task_state="skipped",
            )

    def parse_rule(self, filepath):
        """
        Analisa uma regra Yara em um arquivo.
        """
        path = Path(filepath)
        with path.open() as file:
            content = file.read()
            match = re.search(r"rule\s+(\w+)", content)
            if match:
                return match.group(1), content  # Rule name and rule content
            return None, content

    def insert_rule(self, rule_name, rule_data, filename):
        """
        Insere uma regra no banco de dados.
        """
        rule_inserted = False
        for client in self.clients:
            if client in rule_name:
                for rule_type in self.yara_type_rules:
                    if rule_type in rule_name:
                        collection_name = f"{self.mongo_client_prefix}{client}"
                        collection = self.db[collection_name]
                        existing_rule = collection.find_one({"rule_name": rule_name})
                        if existing_rule:
                            if self.overwrite:
                                collection.update_one(
                                    {"rule_name": rule_name}, {"$set": {"rule_content": rule_data}}
                                )
                                self.overwrite_count += 1  # Increment overwrite counter
                                self.logger.log(
                                    "info",
                                    f"Rule {rule_name} updated in {collection_name}",
                                    category="yara",
                                    task_state="running",
                                )
                            else:
                                self.duplicated_rules.append(rule_name)
                                self.logger.log(
                                    "warning",
                                    f"Duplicated rule {rule_name} ignored in {collection_name}",
                                    category="yara",
                                    task_state="skipped",
                                )
                            return
                        else:
                            collection.insert_one(
                                {
                                    "rule_name": rule_name,
                                    "rule_content": rule_data,
                                    "rule_type": rule_type,
                                    "client": client,
                                }
                            )
                            self.imported_count += 1
                            self.logger.log(
                                "info",
                                f"Rule {rule_name} inserted in {collection_name}",
                                category="yara",
                                task_state="running",
                            )
                            rule_inserted = True
                            break
                if rule_inserted:
                    break

        if not rule_inserted:
            self.ignored_rules.append(filename)
            self.ignored_count += 1
            self.logger.log(
                "warning",
                f"Rule {filename} ignored - client or rule type not found",
                category="yara",
                task_state="upstream_failed",
            )

    def __del__(self):
        if self.temp_dir:
            self.temp_dir.cleanup()
