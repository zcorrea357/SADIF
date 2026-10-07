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
        self.client = db_client if db_client else MongoClient("localhost", 27017)
        self.sadif_internal_config = SadifConfiguration()
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
                directory = Path(self.git_manager.clone_repo())
                if not directory:
                    return "Failed to clone the Git repository."

            if not directory:
                return "Import directory not provided and GitManager not configured."

            for file_path in directory.rglob("*.json"):
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

                with file_path.open() as file:
                    data = json.load(file)

                if data:
                    if meta_update:
                        collection.insert_many(
                            data
                        )  # Inserir todos os dados de uma vez para meta atualização
                    else:
                        for document in data:
                            unique_id = document.get("client_name")
                            if unique_id is not None:
                                collection.update_one(
                                    {"client_name": unique_id}, {"$set": document}, upsert=True
                                )

                self._create_indexes(collection)

            return "JSON data import to MongoDB completed successfully."
        except Exception as e:
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
