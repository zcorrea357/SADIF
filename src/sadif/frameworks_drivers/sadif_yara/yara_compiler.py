import threading

import yara
from pymongo import MongoClient

from sadif.clientmanager.client_data_manager import ClientManager
from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class SadifYaraCompiler:
    """
    Compiles the YARA rules stored in the client collections of ``MONGODB_DATABASE_YARA``
    and matches texts/files against them.

    Every stored rule is compiled in its own namespace (``<collection>:<rule_name>``), so
    the same rule name in two client collections does not collide. A rule that does not
    compile (e.g. inserted directly in the database) is skipped and logged: matching keeps
    working with all the other rules. A match is reported only when its client is a client
    registered in ``ClientManager`` and its type is one of ``YARA_TYPE_RULES``; client and
    type come from the stored document and, when absent, from the rule name.
    """

    def __init__(self, db_client=None):
        self.sadif_internal_config = SadifConfiguration()
        self.client = (
            db_client
            if db_client is not None
            else MongoClient(self.sadif_internal_config.get_configuration("MONGODB_URL"))
        )
        self.list_all_clients = ClientManager(self.client)
        self.yara_type_rules = self.sadif_internal_config.get_configuration("YARA_TYPE_RULES")

        self.db = self.client[self.sadif_internal_config.get_configuration("MONGODB_DATABASE_YARA")]
        self.mongo_client_prefix = self.sadif_internal_config.get_configuration(
            "MONGODB_CLIENT_PREFIX"
        )
        self.logger = LogManager()
        self.rules_metadata = {}
        self.invalid_rules = []
        # compile_rules recria rules_metadata a cada chamada; o BaseCrawler compartilha a mesma
        # instância entre threads, então compilar + ler os metadados precisa ser atômico
        self._match_lock = threading.Lock()

    def _load_rules(self):
        """Returns ``{namespace: rule_content}`` and fills ``rules_metadata``."""
        rules = {}
        self.rules_metadata = {}
        for collection_name in sorted(self.db.list_collection_names()):
            if not collection_name.startswith(self.mongo_client_prefix):
                continue
            collection = self.db[collection_name]
            for rule in collection.find(
                {}, {"rule_name": 1, "rule_content": 1, "rule_type": 1, "client": 1, "_id": 0}
            ):
                rule_name = rule.get("rule_name")
                rule_content = rule.get("rule_content")
                if not rule_name or not isinstance(rule_content, str):
                    continue
                try:
                    rule_content.encode("utf-8")
                except UnicodeEncodeError:
                    # Lidar com possíveis erros de codificação
                    self.logger.log(
                        "error",
                        f"Erro de codificação na regra: {rule_name}",
                        category="yara",
                        task_state="failed",
                    )
                    continue
                namespace = f"{collection_name}:{rule_name}"
                rules[namespace] = rule_content
                self.rules_metadata[namespace] = {
                    "rule_name": rule_name,
                    "client": rule.get("client")
                    or collection_name[len(self.mongo_client_prefix) :],
                    "rule_type": rule.get("rule_type"),
                }
        return rules

    def compile_rules(self):
        """
        Compiles all the stored rules, skipping (and logging) the ones that do not compile.

        Returns
        -------
        yara.Rules or None
            The compiled rules, or None only if no valid set could be compiled.
        """
        rules = self._load_rules()
        self.invalid_rules = []
        try:
            return yara.compile(sources=rules)
        except yara.Error as e:
            self.logger.log(
                "warning",
                f"Erro ao compilar regras, compilando individualmente: {e}",
                category="yara",
                task_state="running",
            )

        valid_rules = {}
        for namespace, rule_content in rules.items():
            try:
                yara.compile(source=rule_content)
            except yara.Error as e:
                self.invalid_rules.append(self.rules_metadata[namespace]["rule_name"])
                self.logger.log(
                    "error",
                    f"Regra {namespace} ignorada - erro de sintaxe: {e}",
                    category="yara",
                    task_state="skipped",
                )
                continue
            valid_rules[namespace] = rule_content
        try:
            return yara.compile(sources=valid_rules)
        except yara.Error as e:
            self.logger.log(
                "error",
                f"Erro de sintaxe ao compilar regras: {e}",
                category="yara",
                task_state="failed",
            )
            return None

    def _find_in_name(self, rule_name, candidates):
        """Returns the longest candidate contained in ``rule_name`` (prefix first)."""
        found = sorted(
            (candidate for candidate in candidates if candidate and candidate in rule_name),
            key=lambda candidate: (not rule_name.startswith(candidate), -len(candidate)),
        )
        return found[0] if found else None

    def extract_match_details(self, matches):
        resultados = []
        registered_clients = self.list_all_clients.list_all_clients()
        for match in matches:
            metadata = self.rules_metadata.get(getattr(match, "namespace", None), {})
            client_name = None
            yara_rule_type = None
            if metadata:
                # The rule belongs to the client of its document/collection: when that
                # client is not registered the match is not reported (it must not be
                # attributed to another client whose name is contained in the rule name).
                if metadata.get("client") in registered_clients:
                    client_name = metadata["client"]
                if (
                    metadata.get("rule_name") == match.rule
                    and metadata.get("rule_type") in self.yara_type_rules
                ):
                    yara_rule_type = metadata["rule_type"]
            else:
                client_name = self._find_in_name(match.rule, registered_clients)
            if yara_rule_type is None:
                remainder = match.rule.replace(client_name, " ", 1) if client_name else match.rule
                for potential_rule_type in self.yara_type_rules:
                    if potential_rule_type in remainder:
                        yara_rule_type = potential_rule_type
                        break

            # Se o nome do cliente e o tipo de regra YARA forem encontrados, processar o match
            if client_name and yara_rule_type:
                for string_match in match.strings:
                    resultado = {
                        "rule_name": match.rule,
                        "yara_match": string_match,
                        "client_name": client_name,
                        "yara_rule_type": yara_rule_type,
                    }
                    resultados.append(resultado)
        return resultados

    def match_text(self, text):
        with self._match_lock:
            compiled_rules = self.compile_rules()
            if compiled_rules is None:  # erro de sintaxe ao compilar as regras
                return []
            matches = compiled_rules.match(data=text)
            return self.extract_match_details(matches)

    def match_file(self, file_path):
        with self._match_lock:
            compiled_rules = self.compile_rules()
            if compiled_rules is None:  # erro de sintaxe ao compilar as regras
                return []
            try:
                matches = compiled_rules.match(filepath=str(file_path))
            except yara.Error as e:
                self.logger.log(
                    "error",
                    f"Erro ao analisar o arquivo {file_path}: {e}",
                    category="yara",
                    task_state="failed",
                )
                return []
            return self.extract_match_details(matches)
