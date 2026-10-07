import yara
from pymongo import MongoClient

from sadif.clientmanager.client_data_manager import ClientManager
from sadif.config.sadif_config import SadifConfiguration


class SadifYaraCompiler:
    def __init__(self, db_client=None):
        self.client = db_client if db_client else MongoClient("localhost", 27017)
        self.sadif_internal_config = SadifConfiguration()
        self.list_all_clients = ClientManager(db_client)
        self.sadif_internal_config.get_configuration("MONGODB_DATABASE_YARA")
        self.yara_type_rules = self.sadif_internal_config.get_configuration("YARA_TYPE_RULES")

        self.db = self.client[self.sadif_internal_config.get_configuration("MONGODB_DATABASE_YARA")]
        self.mongo_client_prefix = self.sadif_internal_config.get_configuration(
            "MONGODB_CLIENT_PREFIX"
        )

    def compile_rules(self):
        # Compilar todas as regras de todas as coleções
        rules = {}
        for collection_name in self.db.list_collection_names():
            if collection_name.startswith(self.mongo_client_prefix):
                collection = self.db[collection_name]
                for rule in collection.find(
                    {}, {"rule_name": 1, "rule_content": 1, "rule_type": 1, "client": 1, "_id": 0}
                ):
                    try:
                        encoded_rule_content = rule["rule_content"].encode("utf-8").decode("utf-8")
                        rules[rule["rule_name"]] = encoded_rule_content
                    except UnicodeEncodeError:
                        # Lidar com possíveis erros de codificação
                        print(f"Erro de codificação na regra: {rule['rule_name']}")
                        continue
        try:
            return yara.compile(sources=rules)
        except yara.SyntaxError as e:
            print(f"Erro de sintaxe ao compilar regras: {e}")
            return None

    def extract_match_details(self, matches):
        resultados = []
        for match in matches:
            client_name = None
            yara_rule_type = None
            for potential_client in self.list_all_clients.list_all_clients():
                if potential_client in match.rule:
                    client_name = potential_client
                    break
            for potential_rule_type in self.yara_type_rules:
                if potential_rule_type in match.rule:
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
        compiled_rules = self.compile_rules()
        if compiled_rules is None:  # erro de sintaxe ao compilar as regras
            return []
        matches = compiled_rules.match(data=text)
        return self.extract_match_details(matches)

    def match_file(self, file_path):
        compiled_rules = self.compile_rules()
        if compiled_rules is None:  # erro de sintaxe ao compilar as regras
            return []
        matches = compiled_rules.match(filepath=file_path)
        return self.extract_match_details(matches)
