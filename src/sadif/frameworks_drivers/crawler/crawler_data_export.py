import json
import re
from pathlib import Path

from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class CrawlerManagerExport:
    def __init__(self, db_client=None) -> None:
        self.log_manager = LogManager()
        init_msg = "Initializing ExportManager"
        self.log_manager.log("info", init_msg, category="export_manager", task_state="running")

        try:
            self.sadif_internal_config = SadifConfiguration()
            self.db_client = db_client or MongoClient()
            self.db = self.db_client[
                self.sadif_internal_config.get_configuration("MONGODB_DATABASE_CRAWLER")
            ]
            self.collection_with_credential_web = self.db[
                self.sadif_internal_config.get_configuration(
                    "MONGODB_COLLECTION_CRAWLER_WEB_WITH_CREDENTIAL"
                )
            ]
            self.collection_without_credential_web = self.db[
                self.sadif_internal_config.get_configuration(
                    "MONGODB_COLLECTION_CRAWLER_WEB_WITHOUT_CREDENTIAL"
                )
            ]
            self.collection_with_credential_onion = self.db[
                self.sadif_internal_config.get_configuration(
                    "MONGODB_COLLECTION_CRAWLER_ONION_WITH_CREDENTIAL"
                )
            ]
            self.collection_without_credential_onion = self.db[
                self.sadif_internal_config.get_configuration(
                    "MONGODB_COLLECTION_CRAWLER_ONION_WITHOUT_CREDENTIAL"
                )
            ]
            self._create_unique_indexes()
            init_success_msg = "ExportManager initialized successfully"
            self.log_manager.log(
                "info", init_success_msg, category="export_manager", task_state="success"
            )
        except Exception as e:
            init_fail_msg = "Failed to initialize ExportManager"
            self.log_manager.capture_exception(e, init_fail_msg, category="export_manager")

    def _create_unique_indexes(self):
        try:
            collections = [
                self.collection_with_credential_web,
                self.collection_without_credential_web,
                self.collection_with_credential_onion,
                self.collection_without_credential_onion,
            ]

            for collection in collections:
                collection.create_index("url", unique=True)

            indexes_msg = "Unique indexes created for all collections"
            self.log_manager.log(
                "info", indexes_msg, category="export_manager", task_state="success"
            )
        except Exception as e:
            index_fail_msg = "Failed to create unique indexes"
            self.log_manager.capture_exception(e, index_fail_msg, category="export_manager")

    def export_collections(self, export_dir: str):
        task_state = "running"
        try:
            self.log_manager.log(
                "info",
                "Starting export of collections",
                category="export_manager",
                task_state=task_state,
            )
            all_documents = self.get_all_documents_by_collection()

            export_dir_path = Path(export_dir)
            export_dir_path.mkdir(parents=True, exist_ok=True)

            for collection_name, documents in all_documents.items():
                collection_dir = export_dir_path / collection_name
                collection_dir.mkdir(parents=True, exist_ok=True)

                for document in documents:
                    url = document.get("url", "unknown")
                    simplified_url = re.sub(r"https?://", "", url)
                    simplified_url = re.sub(r"www\.", "", simplified_url)
                    filename = (
                        simplified_url.replace(".", "_").replace("/", "_").replace(":", "_")
                        + ".json"
                    )
                    with (collection_dir / filename).open("w") as file:
                        json.dump(document, file)

                self.log_manager.log(
                    "info",
                    f"Documents exported for collection {collection_name}",
                    category="export_manager",
                    task_state="running",
                )

            self.log_manager.log(
                "info",
                "Export completed successfully",
                category="export_manager",
                task_state="success",
            )
        except Exception as e:
            self.log_manager.capture_exception(
                e, "Failed to export collections", category="export_manager"
            )

    def get_all_documents_by_collection(self, collection_name: str = None) -> dict:
        try:
            self.log_manager.log(
                "info",
                "Fetching documents from collections",
                category="export_manager",
                task_state="running",
            )
            collections = {
                "crawler_with_credential_web": self.collection_with_credential_web,
                "crawler_without_credential_web": self.collection_without_credential_web,
                "crawler_with_credential_onion": self.collection_with_credential_onion,
                "crawler_without_credential_onion": self.collection_without_credential_onion,
            }

            if collection_name and collection_name in collections:
                documents = list(collections[collection_name].find({}, {"_id": 0}))
                self.log_manager.log(
                    "info",
                    f"Documents fetched from {collection_name}",
                    category="export_manager",
                    task_state="running",
                )
                return {collection_name: documents}
            else:
                all_documents = {}
                for collection_name, collection in collections.items():
                    documents = list(collection.find({}, {"_id": 0}))
                    all_documents[collection_name] = documents
                    self.log_manager.log(
                        "info",
                        f"Documents fetched from {collection_name}",
                        category="export_manager",
                        task_state="running",
                    )

                self.log_manager.log(
                    "info",
                    "Successfully fetched all documents",
                    category="export_manager",
                    task_state="success",
                )
                return all_documents
        except Exception as e:
            self.log_manager.capture_exception(
                e, "Failed to fetch documents", category="export_manager"
            )
