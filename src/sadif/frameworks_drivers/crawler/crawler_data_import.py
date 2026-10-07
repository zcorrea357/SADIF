import json
from pathlib import Path

from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.gitmanager import GitManager
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class CrawlerManagerImporter:
    def __init__(self, db_client=None, git_manager: GitManager = None) -> None:
        self.git_manager = git_manager
        self.log_manager = LogManager()
        init_msg = "Initializing ImportManager"
        self.log_manager.log("info", init_msg, category="import_manager", task_state="running")

        try:
            self.sadif_internal_config = SadifConfiguration()
            cloned_dir = self.git_manager.clone_repo()
            if cloned_dir:
                self.directory = cloned_dir
            else:
                self.log_manager.log("error", "Error in cloning the Git repository")
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
            init_success_msg = "ImportManager initialized successfully"
            self.log_manager.log(
                "info", init_success_msg, category="import_manager", task_state="success"
            )
        except Exception as e:
            init_fail_msg = "Failed to initialize ImportManager"
            self.log_manager.capture_exception(e, init_fail_msg, category="import_manager")

    def import_collections(self, meta_update: bool = False):
        imported_urls = []
        ignored_urls = []  # Esta lista agora conterá tuplas de (nome do arquivo, motivo)

        try:
            if meta_update:
                self.db_client.drop_database(self.db.name)
                self.log_manager.log(
                    level="info",
                    message=f"Database '{self.db.name}' dropped for meta update.",
                    category="import_manager",
                    task_state="running",
                )

            import_dir_path = Path(self.directory)

            for collection_dir in import_dir_path.iterdir():
                if not collection_dir.is_dir() or not collection_dir.name.startswith("crawler_"):
                    continue

                collection_name = collection_dir.name
                collection = self.db[collection_name]

                if meta_update:
                    self.log_manager.log(
                        level="info",
                        message=f"Collection '{collection_name}' deleted for meta update.",
                        category="import_manager",
                        task_state="running",
                    )

                for file_path in collection_dir.iterdir():
                    if file_path.is_file():
                        with file_path.open() as file:
                            document = json.load(file)
                            url = document.get("url", None)
                            if not url:
                                ignored_urls.append(
                                    (file_path.name, "URL is needed to import file.")
                                )
                                continue

                            try:
                                collection.replace_one({"url": url}, document, upsert=True)
                                imported_urls.append(url)
                                self.log_manager.log(
                                    level="info",
                                    message=f"Monitoring url {url} inserted in {collection_name}.",
                                    category="import_manager",
                                    task_state="success",
                                )
                            except Exception as e:
                                ignored_urls.append((file_path.name, str(e)))
                                self.log_manager.log(
                                    level="error",
                                    message=f"Error inserting url {url} in {collection_name}: {e}",
                                    category="import_manager",
                                    task_state="failed",
                                    exc_info=e,
                                )

            self.log_manager.log(
                level="info",
                message="Import completed successfully",
                category="import_manager",
                task_state="success",
            )
            if ignored_urls:
                for ignored_url in ignored_urls:
                    self.log_manager.log(
                        level="warning",
                        message=f"Ignored URL from file '{ignored_url[0]}': {ignored_url[1]}",
                        category="import_manager",
                        task_state="skipped",
                    )
            self.log_manager.log(
                level="info",
                message=f"Imported URLs: {len(imported_urls)}. Ignored URLs: {len(ignored_urls)}.",
                category="import_manager",
                task_state="skipped",
            )
        except FileNotFoundError as e:
            self.log_manager.log(
                level="error",
                message="Cloned repository directory not found: " + str(e),
                category="import_manager",
                task_state="failed",
                exc_info=e,
            )
        except Exception as e:
            self.log_manager.log(
                level="error",
                message="Failed to import collections: " + str(e),
                category="import_manager",
                task_state="failed",
                exc_info=e,
            )
