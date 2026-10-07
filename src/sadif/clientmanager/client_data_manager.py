from typing import Any

from pymongo import MongoClient, errors
from pymongo.collection import Collection

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class ClientManager:
    """
    Manages client collections within a MongoDB database, including creation,
    deletion, and updates to client-specific collections and modules.

    Parameters
    ----------
    db_client : MongoClient, optional
        An instance of a MongoDB client to connect to a database. If not provided,
        a new client will be created to connect to a local MongoDB instance.

    Attributes
    ----------
    client : MongoClient
        The MongoDB client used to interact with the database.
    sadif_internal_config : SadifConfiguration
        Configuration object to access SADIF platform settings.
    mongodb_client_prefix : str
        Prefix for MongoDB client collections derived from the SADIF configuration.
    db : Database
        The MongoDB database instance where client collections are managed.
    log_manager : LogManager
        Log manager instance for logging operations within the class.

    """

    def __init__(self, db_client=None):
        self.sadif_internal_config = SadifConfiguration()
        self.client = (
            db_client
            if db_client is not None
            else MongoClient(self.sadif_internal_config.get_configuration("MONGODB_URL"))
        )
        self.mongodb_client_prefix = self.sadif_internal_config.get_configuration(
            "MONGODB_CLIENT_PREFIX"
        )
        self.db = self.client[
            self.sadif_internal_config.get_configuration("MONGODB_DATABASE_CLIENTS")
        ]
        self.log_manager = LogManager()

    def create_client_collection(
        self,
        client_name: str | None,
        company: str | None,
        ciid: str | None,
        overwrite: bool = False,
    ) -> str:
        """
        Creates a new collection for a client in the MongoDB database. If the collection
        already exists, it can be overwritten based on the `overwrite` flag.

        Parameters
        ----------
        client_name : str
            The name of the client for which the collection is to be created.
        company : str
            The company name associated with the client.
        ciid : str
            The unique CIID (Client Identification ID) for the client.
        overwrite : bool, optional
            If True, an existing collection with the same name will be dropped before
            creating a new one. The default is False.

        Returns
        -------
        str
            A message indicating the outcome of the operation.

        """
        if not client_name or not company or not ciid:
            self.log_manager.log(
                "error",
                "Falha na criação da coleção: 'client_name', 'company' e 'ciid' são necessários.",
                category="Database",
                task_state="failed",
            )
            return "Erro: 'client_name', 'company' e 'ciid' são necessários."

        collection_name = self._generate_collection_name(client_name)

        if collection_name in self.db.list_collection_names():
            if overwrite:
                self.db[collection_name].drop()
                self.log_manager.log(
                    "info",
                    f"Coleção existente {collection_name} sobrescrita.",
                    category="Database",
                    task_state="success",
                )
            else:
                self.log_manager.log(
                    "info",
                    f"Coleção {collection_name} já existe. Operação ignorada.",
                    category="Database",
                    task_state="success",
                )
                return f"Coleção {collection_name} já existe. Operação ignorada."

        try:
            self.db.create_collection(collection_name)
            new_collection = self.db[collection_name]
            new_collection.insert_one(
                {"client_name": client_name, "company": company, "ciid": ciid, "Modules": {}}
            )
            self._create_indexes(new_collection)
            self.log_manager.log(
                "info",
                f"Coleção criada para o cliente: {client_name}.",
                category="Database",
                task_state="success",
            )
            return f"Coleção criada para o cliente: {client_name}."
        except errors.DuplicateKeyError as e:
            self.log_manager.log(
                "error", str(e), category="Database", exc_info=e, task_state="failed"
            )
            return "Erro: Valor duplicado para 'client_name', 'company' ou 'ciid'."

    def update_module_info(
        self, client_name: str, module_name: str, module_info: dict[str, Any]
    ) -> str:
        """
        Updates information for a specific module within a client's collection.

        Parameters
        ----------
        client_name : str
            The name of the client whose module information is to be updated.
        module_name : str
            The name of the module to update.
        module_info : dict
            A dictionary containing the new information for the module.

        Returns
        -------
        str
            A message indicating the outcome of the update operation.

        """
        if module_name not in self.sadif_internal_config.get_configuration("CLIENTS_MODULES"):
            self.log_manager.log(
                "error",
                f"Módulo '{module_name}' não é permitido.",
                category="Database",
                task_state="failed",
            )
            return f"Erro: Módulo '{module_name}' não é permitido."

        collection_name = self._generate_collection_name(client_name)
        if collection_name not in self.db.list_collection_names():
            self.log_manager.log(
                "error", "Cliente não encontrado.", category="Database", task_state="failed"
            )
            return "Erro: Cliente não encontrado."

        try:
            update_query = {"$set": {f"Modules.{module_name}": module_info}}
            self.db[collection_name].update_one(
                {"client_name": client_name}, update_query, upsert=True
            )
            self.log_manager.log(
                "info",
                f"Informações do módulo '{module_name}' atualizadas com sucesso.",
                category="Database",
                task_state="success",
            )
            return f"Informações do módulo '{module_name}' atualizadas com sucesso."
        except errors.PyMongoError as e:
            self.log_manager.log(
                "error", str(e), category="Database", exc_info=e, task_state="failed"
            )
            return f"Erro ao atualizar informações do módulo: {e}"

    def find_client_modules(self, client_name: str) -> str | dict[Any, Any] | Any:
        """
        Retrieves module information for a specified client.

        Parameters
        ----------
        client_name : str
            The name of the client whose module information is to be retrieved.

        Returns
        -------
        dict
            A dictionary containing the client's module information, or an empty
            dictionary if no information is found.

        """
        collection_name = self._generate_collection_name(client_name)
        if collection_name not in self.db.list_collection_names():
            self.log_manager.log(
                "error",
                "Cliente não encontrado ao buscar módulos.",
                category="Database",
                task_state="failed",
            )
            return "Cliente não encontrado."

        try:
            client_data = self.db[collection_name].find_one({"client_name": client_name})
            if client_data:
                self.log_manager.log(
                    "info",
                    f"Encontradas informações dos módulos para o cliente {client_name}.",
                    category="Database",
                    task_state="success",
                )
                return client_data.get("Modules", {})
            else:
                self.log_manager.log(
                    "error",
                    "Informações do cliente não encontradas ao buscar módulos.",
                    category="Database",
                    task_state="failed",
                )
                return "Informações do cliente não encontradas."
        except errors.PyMongoError as e:
            self.log_manager.log(
                "error", str(e), category="Database", exc_info=e, task_state="failed"
            )
            return "Erro ao buscar informações dos módulos."

    def delete_client_collection(self, client_name: str) -> str:
        """
        Deletes a client's collection from the database.

        Parameters
        ----------
        client_name : str
            The name of the client whose collection is to be deleted.

        Returns
        -------
        str
            A message indicating the outcome of the deletion operation.

        """
        collection_name = self._generate_collection_name(client_name)
        if collection_name not in self.db.list_collection_names():
            self.log_manager.log(
                "error",
                "Cliente não encontrado ao deletar coleção.",
                category="Database",
                task_state="failed",
            )
            return "Cliente não encontrado."

        try:
            self.db.drop_collection(collection_name)
            self.log_manager.log(
                "info",
                f"Coleção do cliente {client_name} deletada com sucesso.",
                category="Database",
                task_state="success",
            )
            return f"Coleção do cliente {client_name} deletada com sucesso."
        except errors.PyMongoError as e:
            self.log_manager.log(
                "error", str(e), category="Database", exc_info=e, task_state="failed"
            )
            return "Erro ao deletar coleção do cliente."

    def list_all_clients(self) -> list:
        """
        Lists all client names that have collections in the database.

        Returns
        -------
        list
            A list of all client names.

        """
        prefix_length = len(self.mongodb_client_prefix)
        return sorted(
            collection_name[prefix_length:]
            for collection_name in self.db.list_collection_names()
            if collection_name.startswith(self.mongodb_client_prefix)
            and len(collection_name) > prefix_length
        )

    def _generate_collection_name(self, client_name: str) -> str:
        """
        Generates a collection name for a client based on the configured prefix.

        Parameters
        ----------
        client_name : str
            The name of the client.

        Returns
        -------
        str
            The generated collection name.

        """
        return f"{self.mongodb_client_prefix}{client_name}"

    def _create_indexes(self, collection: Collection) -> None:
        """
        Creates unique indexes for a collection on specified fields.

        Parameters
        ----------
        collection : Collection
            The MongoDB collection object on which indexes are to be created.

        """
        collection.create_index("client_name", unique=True)
        collection.create_index("company", unique=True)
        collection.create_index("ciid", unique=True)
