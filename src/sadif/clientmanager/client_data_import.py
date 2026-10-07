import json
from pathlib import Path

from pymongo import MongoClient
from pymongo.collection import Collection

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class ClientManagerImport:
    def __init__(self, db_client=None, git_manager=None):
        """
        Manages the import of client data into a MongoDB database from JSON files.

        Parameters
        ----------
        db_client : MongoClient, optional
            A MongoDB client instance. If not provided, a default local client will be created.
        git_manager : GitManager, optional
            An instance of GitManager for cloning repositories.

        Attributes
        ----------
        git_manager : GitManager
            Manager for Git operations.

        """
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
        self.git_manager = git_manager

    def import_from_json(
        self,
        import_path: str | None = None,
        overwrite: bool = False,
        meta_update: bool = False,
    ) -> str:
        """
        Imports data from JSON files into corresponding collections in the MongoDB database.

        Parameters
        ----------
        import_path : str, optional
            The path to the directory containing JSON files. If not provided, cloning is attempted via GitManager.
        overwrite : bool, default False
            If True, existing collections will be overwritten with the imported data.
        meta_update: bool, default False
            If True, drop collection end recreated if it exists
        Returns
        -------
        str
            A message indicating the result of the import operation.

        Raises
        ------
        Exception
            If any error occurs during the import process.

        Args:
            meta_update:

        """
        try:
            directory = Path(import_path) if import_path else None
            if not directory and self.git_manager:
                cloned_directory = self.git_manager.clone_repo()
                if not cloned_directory:
                    self.log_manager.log(
                        "error",
                        "Failed to clone the Git repository.",
                        category="Database",
                        task_state="failed",
                    )
                    return "Failed to clone the Git repository."
                directory = Path(cloned_directory)

            if not directory:
                return "Import directory not provided and GitManager not configured."

            if not directory.is_dir():
                self.log_manager.log(
                    "error",
                    f"Import directory {directory} does not exist.",
                    category="Database",
                    task_state="failed",
                )
                return f"Error importing JSON data to MongoDB: directory {directory} not found."

            json_files = sorted(
                file_path
                for file_path in directory.rglob("*.json")
                if ".git" not in file_path.relative_to(directory).parts
            )
            # Lê e valida todos os arquivos antes de qualquer alteração, para não perder
            # coleções existentes quando algum JSON for inválido
            parsed_files = []
            for file_path in json_files:
                with file_path.open(encoding="utf-8") as file:
                    data = json.load(file)
                if isinstance(data, dict):
                    data = [data]
                if not isinstance(data, list) or not all(isinstance(d, dict) for d in data):
                    msg = f"{file_path.name} must contain a JSON object or a list of objects"
                    raise ValueError(msg)
                parsed_files.append((file_path, data))

            for file_path, data in parsed_files:
                collection_name = file_path.stem

                if meta_update:
                    # Para a meta atualização, deletamos e recriamos a coleção
                    self.db[collection_name].drop()
                    self.db.create_collection(collection_name)
                    self.log_manager.log(
                        "info",
                        f"Collection {collection_name} re-created for meta update.",
                        category="Database",
                        task_state="success",
                    )
                elif overwrite and collection_name in self.db.list_collection_names():
                    self.db[collection_name].drop()
                    self.db.create_collection(collection_name)
                    self.log_manager.log(
                        "info",
                        f"Existing collection {collection_name} overwritten.",
                        category="Database",
                        task_state="success",
                    )

                collection = self.db[collection_name]
                # Os índices únicos são criados antes da inserção para que dados
                # duplicados sejam rejeitados em vez de impedirem a criação do índice
                self._create_indexes(collection)

                if data:
                    if meta_update:
                        # Inserir todos os dados de uma vez para meta atualização
                        collection.insert_many([dict(document) for document in data])
                    else:
                        for document in data:
                            unique_id = document.get("client_name")
                            if unique_id is not None:
                                fields = {k: v for k, v in document.items() if k != "_id"}
                                collection.update_one(
                                    {"client_name": unique_id}, {"$set": fields}, upsert=True
                                )

            self.log_manager.log(
                "info",
                f"JSON data import to MongoDB completed ({len(json_files)} files).",
                category="Database",
                task_state="success",
            )
            return "JSON data import to MongoDB completed successfully."
        except Exception as e:
            self.log_manager.log(
                "error", str(e), category="Database", exc_info=e, task_state="failed"
            )
            return f"Error importing JSON data to MongoDB: {e}"

    def _generate_collection_name(self, client_name: str) -> str:
        """
        Generates a collection name using the MongoDB client prefix and the provided client name.

        Parameters
        ----------
        client_name : str
            The name of the client for whom the collection is to be named.

        Returns
        -------
        str
            The generated collection name.

        """
        return f"{self.mongodb_client_prefix}{client_name}"

    def _create_indexes(self, collection: Collection) -> None:
        """
        Creates indexes in the specified MongoDB collection.

        Parameters
        ----------
        collection : Collection
            The MongoDB collection in which indexes will be created.

        """
        collection.create_index("client_name", unique=True)
        collection.create_index("company", unique=True)
        collection.create_index("ciid", unique=True)
