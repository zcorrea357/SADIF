import os
import re
from pathlib import Path

import yara
from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager

# Extensões aceitas para arquivos de regras YARA.
YARA_RULE_EXTENSIONS = (".yar", ".yara")
# Declaração de regra no início de uma linha (com modificadores opcionais), ignorando
# ocorrências da palavra "rule" em comentários, metadados ou strings.
_RULE_DECLARATION = re.compile(r"^\s*(?:(?:private|global)\s+)*rule\s+([A-Za-z_]\w*)", re.MULTILINE)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")


class YaraRulesImporter:
    """
    Class for importing YARA rules.

    Each ``.yar``/``.yara`` file found (recursively, in sorted order) in ``directory`` (or
    in the repository cloned by ``git_manager``) is imported into the collection
    ``<MONGODB_CLIENT_PREFIX><client>`` of the ``MONGODB_DATABASE_YARA`` database as
    ``{"rule_name", "rule_content", "rule_type", "client"}``. The client and the rule type
    are taken from the rule name (``<Client>Monitoramento<Type>NN``): the client is the
    longest name of ``clients`` contained in the rule name (preferring a prefix) and the
    type is the first entry of ``YARA_TYPE_RULES`` found in the rest of the name.

    Files are ignored (``ignored_rules``) when they have no rule declaration, when no
    client/type can be found in the rule name, or when they are not valid YARA (these are
    also listed in ``invalid_rules``), so a broken rule never reaches the database. A rule
    whose name already exists in the client collection is updated when ``overwrite`` is
    True, otherwise it is kept as is and listed in ``duplicated_rules``.
    """

    def __init__(self, directory, clients, db_client=None, git_manager=None, overwrite=False):
        """
        Initializes the YaraRulesImporter class.
        """
        self.sadif_internal_config = SadifConfiguration()
        self.client = (
            db_client
            if db_client is not None
            else MongoClient(self.sadif_internal_config.get_configuration("MONGODB_URL"))
        )
        self.db = self.client[self.sadif_internal_config.get_configuration("MONGODB_DATABASE_YARA")]
        self.mongo_client_prefix = self.sadif_internal_config.get_configuration(
            "MONGODB_CLIENT_PREFIX"
        )
        self.yara_type_rules = self.sadif_internal_config.get_configuration("YARA_TYPE_RULES")
        self.git_manager = git_manager
        self.directory = directory
        self.clients = list(clients or [])
        self.overwrite = overwrite
        self.logger = LogManager()
        self.imported_count = 0
        self.ignored_count = 0
        self.ignored_rules = []
        self.invalid_rules = []
        self.temp_dir = None

        self.duplicated_rules = []
        self.overwrite_count = 0

        if self.git_manager:
            cloned_dir = self.git_manager.clone_repo()
            if cloned_dir:
                self.directory = cloned_dir
            else:
                self.logger.log(
                    "error",
                    "Error in cloning the Git repository",
                    category="yara",
                    task_state="failed",
                )

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

    def _iter_rule_files(self, directory_path):
        """Yields the YARA rule files below ``directory_path`` in a deterministic order."""
        for root, dirs, files in os.walk(directory_path):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for filename in sorted(files):
                if filename.lower().endswith(YARA_RULE_EXTENSIONS):
                    yield Path(root) / filename

    def _ignore(self, filename, message, task_state="skipped"):
        self.ignored_rules.append(filename)
        self.ignored_count += 1
        self.logger.log("warning", message, category="yara", task_state=task_state)

    def import_rules(self, meta_update=False):
        """
        Importa regras do diretório especificado com suporte a meta atualização.

        Returns
        -------
        dict
            Summary of the import (imported, overwritten, ignored, duplicated and invalid).
        """
        if self.directory is None or not Path(self.directory).is_dir():
            self.logger.log(
                "error",
                f"YARA rules directory not found: {self.directory}",
                category="yara",
                task_state="failed",
            )
            return self.summary()

        if meta_update:
            self.perform_meta_update()

        for rule_path in self._iter_rule_files(Path(self.directory)):
            filename = rule_path.name
            try:
                rule_name, rule_data = self.parse_rule(rule_path)
            except (OSError, UnicodeDecodeError) as e:
                self._ignore(filename, f"Rule {filename} ignored - unreadable file: {e}", "failed")
                continue
            if not rule_name:
                self._ignore(filename, f"Rule {filename} ignored - couldn't find rule name")
                continue
            try:
                yara.compile(source=rule_data)
            except yara.Error as e:
                self.invalid_rules.append(filename)
                self._ignore(filename, f"Rule {filename} ignored - invalid YARA: {e}", "failed")
                continue
            self.insert_rule(rule_name, rule_data, filename)

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
        return self.summary()

    def summary(self):
        """Returns the counters and lists of the import process."""
        return {
            "imported": self.imported_count,
            "overwritten": self.overwrite_count,
            "ignored": self.ignored_count,
            "ignored_rules": list(self.ignored_rules),
            "duplicated_rules": list(self.duplicated_rules),
            "invalid_rules": list(self.invalid_rules),
        }

    def parse_rule(self, filepath):
        """
        Analisa uma regra Yara em um arquivo.

        Returns the name of the first rule declared in the file (``None`` when there is
        none; comments are not considered) and the full content of the file.
        """
        path = Path(filepath)
        content = path.read_text(encoding="utf-8")
        code = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", content))
        match = _RULE_DECLARATION.search(code)
        if match:
            return match.group(1), content  # Rule name and rule content
        return None, content

    def resolve_client_and_type(self, rule_name):
        """
        Returns ``(client, rule_type)`` for ``rule_name`` or ``(None, None)``.

        Clients that prefix the rule name are preferred, then longer names, so that
        e.g. ``AcmeBankMonitoramentoVips01`` belongs to ``AcmeBank`` and not to ``Acme``.
        """
        candidates = sorted(
            (client for client in self.clients if client and client in rule_name),
            key=lambda client: (not rule_name.startswith(client), -len(client)),
        )
        for client in candidates:
            if rule_name.startswith(client):
                remainder = rule_name[len(client) :]
            else:
                remainder = rule_name.replace(client, " ", 1)
            for rule_type in self.yara_type_rules:
                if rule_type in remainder:
                    return client, rule_type
        return None, None

    def insert_rule(self, rule_name, rule_data, filename):
        """
        Insere uma regra no banco de dados.
        """
        client, rule_type = self.resolve_client_and_type(rule_name)
        if not client:
            self._ignore(
                filename,
                f"Rule {filename} ignored - client or rule type not found",
                "upstream_failed",
            )
            return

        collection_name = f"{self.mongo_client_prefix}{client}"
        collection = self.db[collection_name]
        if collection.find_one({"rule_name": rule_name}):
            if self.overwrite:
                collection.update_one(
                    {"rule_name": rule_name},
                    {"$set": {"rule_content": rule_data, "rule_type": rule_type, "client": client}},
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

    def __del__(self):
        # getattr: __del__ also runs on partially initialized instances
        temp_dir = getattr(self, "temp_dir", None)
        if temp_dir:
            temp_dir.cleanup()
