from contextlib import contextmanager
from typing import Any

from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class ModuleDatabaseManager:
    """
    Database manager for modules, responsible for creating, inserting, updating,
    deleting, and querying documents in specific module collections in MongoDB.

    This class uses `MongoClient` for database connection and manages specific
    collection operations for individual modules within a database named 'Modules'.
    Database operations are logged using `LogManager`.

    Attributes
    ----------
    client : MongoClient
        MongoDB connection client.
    db_name : str
        Name of the database used for module operations.
    db : Database
        MongoDB database instance.
    log_manager: LogManager to log events and errors.
    category : str
        Category used for logging.

    Parameters
    ----------
    db_client : MongoClient, optional
        MongoDB connection client. If not provided, a new client is created with
        a default connection to localhost on port 27017.

    """

    def __init__(self, db_client=None):
        """
        Initializes the ModuleDatabaseManager instance, setting up the MongoDB client,
        database, log manager, and logging category.
        """

        self.client = db_client if db_client else MongoClient("localhost", 27017)
        self.log_manager = LogManager()
        self.sadif_internal_config = SadifConfiguration()
        self.db_name = self.sadif_internal_config.get_configuration(
            "MONGODB_DATABASE_MODULES_MANAGER"
        )
        self.db = self.client[self.db_name]
        self.category = "module_manager"

    @contextmanager
    def get_connection(self):
        """
        Context manager to obtain a database connection.

        Yields
        ------
        db : Database
            MongoDB database instance.

        Raises
        ------
        Exception
            Captures and logs any exception that occurs during the database connection,
            then re-raises the exception.

        Examples
        --------
        with module_db_manager.get_connection() as db:
            # Operations with db
        """
        try:
            self.log_manager.log("info", "Connecting to the database.", self.category, "running")
            yield self.db
            self.log_manager.log(
                "info",
                "Database connection closed successfully.",
                self.category,
                "success",
            )
        except Exception as e:
            self.log_manager.capture_exception(
                e, "Failed to connect to the database.", self.category
            )

    def create_module_collection(self, module_name: str, validation_schema: dict[str, Any]):
        """
        Creates a new collection for a module with a specific validation schema.

        Parameters
        ----------
        module_name : str
            Name of the module for which the collection is being created.
        validation_schema : dict[str, Any]
            JSON Schema validation schema for documents in the collection.

        Raises
        ------
        Exception
            Captures and logs exceptions that occur during the collection creation.
        """
        with self.get_connection() as db:
            collection_name = f"module_{module_name}"
            try:
                if collection_name not in db.list_collection_names():
                    db.command(
                        "create",
                        collection_name,
                        validator={"$jsonSchema": validation_schema},
                        validationLevel="strict",
                    )
                    if "required" in validation_schema:
                        for field in validation_schema["required"]:
                            db[collection_name].create_index([(field, 1)], unique=True)
                    self.log_manager.log(
                        "info",
                        f"Collection '{collection_name}' created successfully.",
                        self.category,
                    )
                else:
                    self.log_manager.log(
                        "warning", f"Collection '{collection_name}' already exists.", self.category
                    )
            except Exception as e:
                self.log_manager.capture_exception(
                    e, f"Error creating collection '{collection_name}'.", self.category
                )

    def insert_document(self, module_name: str, document: dict[str, Any]):
        """
        Inserts a new document into the specified module's collection.

        Parameters
        ----------
        module_name : str
            Name of the module associated with the collection where the document will be inserted.
        document : dict[str, Any]
            Document to be inserted into the collection.

        Returns
        -------
        inserted_id : ObjectId
            ID of the inserted document.

        Raises
        ------
        Exception
            Captures and logs exceptions during document insertion.
        """
        collection_name = f"module_{module_name}"
        with self.get_connection():
            try:
                if self.db[collection_name].find_one(document) is None:
                    inserted_id = self.db[collection_name].insert_one(document).inserted_id
                    self.log_manager.log(
                        "info",
                        f"Document inserted successfully. ID: {inserted_id}",
                        self.category,
                        "success",
                    )
                    return inserted_id
                else:
                    self.log_manager.log(
                        "warning",
                        "Document already exists and was ignored.",
                        self.category,
                        "skipped",
                    )
            except Exception as e:
                self.log_manager.capture_exception(e, "Error inserting document.", self.category)

    def find_documents(self, module_name: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Retrieves documents matching the given query from the specified module's collection.

        Parameters
        ----------
        module_name : str
            Name of the module whose collection is being queried.
        query : dict[str, Any]
            Query criteria to filter documents in the collection.

        Returns
        -------
        list[dict[str, Any]]
            A list of documents matching the query. Each document is represented as a dictionary.

        Raises
        ------
        Exception
            Captures and logs exceptions that occur during the document retrieval process.
        """
        collection_name = f"module_{module_name}"
        with self.get_connection():
            try:
                documents = list(self.db[collection_name].find(query))
                self.log_manager.log(
                    "info", f"Documents found: {len(documents)}", self.category, "success"
                )
                return documents
            except Exception as e:
                self.log_manager.capture_exception(e, "Error fetching documents.", self.category)

    def update_document(self, module_name: str, query: dict[str, Any], new_values: dict[str, Any]):
        """
        Updates a document in the specified module's collection based on the given query and new values.

        Parameters
        ----------
        module_name : str
            Name of the module whose collection contains the document to be updated.
        query : dict[str, Any]
            Query criteria to identify the document to be updated.
        new_values : dict[str, Any]
            Dictionary containing the new values for the document. This should follow the
            MongoDB update document structure (e.g., using "$set" for updating specific fields).

        Returns
        -------
        None

        Raises
        ------
        Exception
            Captures and logs exceptions that occur during the document update process.
        """
        collection_name = f"module_{module_name}"
        with self.get_connection():
            try:
                result = self.db[collection_name].update_one(query, {"$set": new_values})
                if result.modified_count > 0:
                    self.log_manager.log(
                        "info", "Document updated successfully.", self.category, "success"
                    )
                else:
                    self.log_manager.log(
                        "warning", "No document was updated.", self.category, "skipped"
                    )
            except Exception as e:
                self.log_manager.capture_exception(e, "Error updating document.", self.category)

    def delete_document(self, module_name: str, query: dict[str, Any]):
        """
        Deletes a document from the specified module's collection based on the given query.

        Parameters
        ----------
        module_name : str
            Name of the module whose collection contains the document to be deleted.
        query : dict[str, Any]
            Query criteria to identify the document to be deleted.

        Returns
        -------
        None

        Raises
        ------
        Exception
            Captures and logs exceptions that occur during the document deletion process.
        """
        collection_name = f"module_{module_name}"
        with self.get_connection():
            try:
                result = self.db[collection_name].delete_one(query)
                if result.deleted_count > 0:
                    self.log_manager.log(
                        "info", "Document deleted successfully.", self.category, "success"
                    )
                else:
                    self.log_manager.log(
                        "warning", "No document was deleted.", self.category, "skipped"
                    )
            except Exception as e:
                self.log_manager.capture_exception(e, "Error deleting document.", self.category)

    def list_module_data(self, module_name: str) -> list[dict[str, Any]]:
        """
        Lists all documents in the specified module's collection.

        Parameters
        ----------
        module_name : str
            Name of the module whose collection is being listed.

        Returns
        -------
        list[dict[str, Any]]
            A list of all documents in the collection. Each document is represented as a dictionary.

        Raises
        ------
        Exception
            Captures and logs exceptions that occur during the document listing process.
        """
        collection_name = f"module_{module_name}"
        with self.get_connection():
            try:
                documents = list(self.db[collection_name].find({}, {"_id": 0}))
                self.log_manager.log(
                    "info",
                    f"Total documents listed: {len(documents)}",
                    self.category,
                    "success",
                )
                return documents
            except Exception as e:
                self.log_manager.capture_exception(e, "Error listing module data.", self.category)
