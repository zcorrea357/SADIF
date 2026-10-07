import json
from pathlib import Path

from pymongo import MongoClient
from pymongo.mongo_client import MongoClient as MongoClientType

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class ClientManagerExport:
    """
    Manages the export of MongoDB client data to JSON files.

    Parameters
    ----------
    db_client : MongoClientType, optional
        MongoDB client to be used for export. If None, a new one is created with default values.

    Attributes
    ----------
    client : MongoClientType
        MongoDB client used for database connection.
    sadif_internal_config : SadifConfiguration
        SADIF internal configuration.
    mongodb_client_prefix : str
        MongoDB client prefix, obtained from SADIF configuration.
    db : Database
        MongoDB database for clients.
    log_manager : LogManager
        Log manager to record actions and events.
    temp_dir : Optional[Path]
        Temporary directory for storing files, None by default.

    """

    def __init__(self, db_client: MongoClientType | None = None):
        self.client = db_client if db_client else MongoClient("localhost", 27017)
        self.sadif_internal_config = SadifConfiguration()
        self.mongodb_client_prefix = self.sadif_internal_config.get_configuration(
            "MONGODB_CLIENT_PREFIX"
        )
        self.db = self.client[
            self.sadif_internal_config.get_configuration("MONGODB_DATABASE_CLIENTS")
        ]
        self.log_manager = LogManager()
        self.temp_dir = None

    def export_to_json(self, export_path: str | Path) -> str:
        """
        Exports all database collections to JSON files in the specified path.

        Parameters
        ----------
        export_path : str or Path
            The path to the directory where the JSON files will be saved.

        Returns
        -------
        str
            Message indicating the success or failure of the export operation.

        Raises
        ------
        Exception
            Any exception that occurs during the export is logged and re-raised.
        """
        try:
            collection_names = self.db.list_collection_names()
            for collection_name in collection_names:
                collection = self.db[collection_name]
                documents = list(
                    collection.find({}, {"_id": 0})  # Excludes the '_id' field from documents
                )

                # Converts documents to JSON format
                json_data = json.dumps(
                    documents,
                    default=str,  # default=str to handle non-serializable types
                )

                # Creates a Path object for the JSON file
                json_file_path = Path(export_path) / f"{collection_name}.json"

                # Writes the data to a JSON file using Path.open()
                with json_file_path.open("w") as file:
                    file.write(json_data)

            self.log_manager.log(
                "info",
                "Collection export to JSON completed successfully.",
                category="Database",
                task_state="success",
            )
            return "Collection export to JSON completed successfully."
        except Exception as e:
            self.log_manager.log(
                "error", str(e), category="Database", exc_info=e, task_state="failed"
            )
            return f"Error exporting collections to JSON: {e}"
