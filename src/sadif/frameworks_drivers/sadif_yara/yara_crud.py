from pymongo import MongoClient

from sadif.clientmanager.client_data_manager import ClientManager
from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.sadif_yara.yara_import import (
    _BLOCK_COMMENT,
    _LINE_COMMENT,
    _RULE_DECLARATION,
)


class YaraCrud:
    def __init__(self, db_client=None):
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
        self.list_all_clients = ClientManager(self.client)

    def parse_rule(self, content):
        # Ignora comentários (ex.: "// esta rule detecta...") ao procurar a declaração da regra
        code = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", content))
        match = _RULE_DECLARATION.search(code)
        if match:
            return match.group(1), content
        return None, content

    def insert_rule(self, client_name, rule_name, rule_content, overwrite=False):
        if client_name in self.list_all_clients.list_all_clients():
            collection_name = f"{self.mongo_client_prefix}{client_name}"
            collection = self.db[collection_name]

            if overwrite:
                # Substituir uma regra existente
                result = collection.update_one(
                    {"rule_name": rule_name}, {"$set": {"rule_content": rule_content}}, upsert=True
                )
                return result.upserted_id or result.modified_count
            else:
                # Verificar se a regra já existe
                if collection.find_one({"rule_name": rule_name}):
                    msg = f"Regra '{rule_name}' já existe em '{collection_name}'. Use 'overwrite=True' para substituir."
                    raise ValueError(msg)
                # Inserir a nova regra
                new_rule = {"rule_name": rule_name, "rule_content": rule_content}
                return collection.insert_one(new_rule).inserted_id
        else:
            return None  # Add a return statement to cover this code path

    def find_rule(self, rule_name):
        # Encontrar uma regra pelo nome em todas as coleções
        for collection_name in self.db.list_collection_names():
            if collection_name.startswith(f"{self.mongo_client_prefix}"):
                collection = self.db[collection_name]
                rule = collection.find_one({"rule_name": rule_name})
                if rule:
                    return rule
        return None

    def update_rule(self, rule_name, new_rule_content):
        # Atualizar o conteúdo de uma regra em todas as coleções
        for collection_name in self.db.list_collection_names():
            if collection_name.startswith(f"{self.mongo_client_prefix}"):
                collection = self.db[collection_name]
                result = collection.update_one(
                    {"rule_name": rule_name}, {"$set": {"rule_content": new_rule_content}}
                )
                if result.matched_count:
                    return result
        return None

    def delete_rule(self, rule_name):
        # Deletar uma regra pelo nome em todas as coleções
        for collection_name in self.db.list_collection_names():
            if collection_name.startswith(f"{self.mongo_client_prefix}"):
                collection = self.db[collection_name]
                result = collection.delete_one({"rule_name": rule_name})
                if result.deleted_count:
                    return result
        return None

    def list_all_rule_names(self):
        rule_names = [
            rule["rule_name"]
            for collection_name in self.db.list_collection_names()
            if collection_name.startswith(f"{self.mongo_client_prefix}")
            for rule in self.db[collection_name].find({}, {"rule_name": 1, "_id": 0})
        ]
        return rule_names
