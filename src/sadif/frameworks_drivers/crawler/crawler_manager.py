import json
import re
from pathlib import Path
from urllib.parse import urlparse

from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.gitmanager import GitManager
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class CrawlerManager:
    def __init__(self, db_client=None) -> None:
        self.log_manager = LogManager()
        init_msg = "Initializing CrawlerManager"
        self.log_manager.log("info", init_msg, category="crawler_manager", task_state="running")

        try:
            self.sadif_internal_config = SadifConfiguration()
            self.git_url = self.sadif_internal_config.get_configuration(
                "GIT_REPO_CLIENT_CRAWLER_MONITORING"
            )
            self.git_token = self.sadif_internal_config.get_configuration("GIT_REPO_TOKEN")
            self.git_manager = GitManager(self.git_url, self.git_token)  # Initialize GitManager
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
            self._create_unique_indexes()
            init_success_msg = "CrawlerManager initialized successfully"
            self.log_manager.log(
                "info", init_success_msg, category="crawler_manager", task_state="success"
            )
        except Exception as e:
            init_fail_msg = "Failed to initialize CrawlerManager"
            self.log_manager.capture_exception(e, init_fail_msg, category="crawler_manager")

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
                "info", indexes_msg, category="crawler_manager", task_state="success"
            )
        except Exception as e:
            index_fail_msg = "Failed to create unique indexes"
            self.log_manager.capture_exception(e, index_fail_msg, category="crawler_manager")

    def process_document(self, document: dict, overwrite: bool = False) -> ObjectId | int | None:
        task_state = "running"
        process_msg = "Processing document"
        self.log_manager.log("info", process_msg, category="crawler_manager", task_state=task_state)
        try:
            url = document.get("url")
            if not url:
                msg = "URL is missing from the document"
                raise ValueError(msg)

            collection = self._determine_collection(url, document)

            if overwrite:
                result = collection.update_one({"url": url}, {"$set": document}, upsert=True)
                action = "inserted" if result.upserted_id is not None else "updated"
                doc_msg = f"Document with URL '{url}' {action}."
                self.log_manager.log(
                    "info", doc_msg, category="crawler_manager", task_state="success"
                )
                return result.upserted_id or result.matched_count
            else:
                try:
                    inserted_id = collection.insert_one(document).inserted_id
                    insert_msg = f"Document with URL '{url}' inserted."
                    self.log_manager.log(
                        "info", insert_msg, category="crawler_manager", task_state="success"
                    )
                    return inserted_id
                except DuplicateKeyError:
                    dup_msg = f"Document ignored: Document with URL '{url}' already exists."
                    self.log_manager.log(
                        "warning", dup_msg, category="crawler_manager", task_state="skipped"
                    )
                    return None
        except Exception as e:
            fail_msg = "Failed to process document"
            self.log_manager.capture_exception(e, fail_msg, category="crawler_manager")

    def _determine_collection(self, url: str, document: dict) -> Collection:
        task_state = "running"
        determ_msg = "Determining collection for URL"
        self.log_manager.log("info", determ_msg, category="crawler_manager", task_state=task_state)
        parsed_url = urlparse(url)
        has_credentials = "auth_type" in document and bool(document["auth_type"])

        if parsed_url.hostname.endswith(".onion"):
            return (
                self.collection_with_credential_onion
                if has_credentials
                else self.collection_without_credential_onion
            )
        else:
            return (
                self.collection_with_credential_web
                if has_credentials
                else self.collection_without_credential_web
            )

    def get_all_documents_by_collection(self, collection_name: str = None) -> dict:
        try:
            self.log_manager.log(
                "info",
                "Fetching documents from collections",
                category="crawler_manager",
                task_state="running",
            )
            collections = {
                "crawler_with_credential_web": self.collection_with_credential_web,
                "crawler_without_credential_web": self.collection_without_credential_web,
                "crawler_with_credential_onion": self.collection_with_credential_onion,
                "crawler_without_credential_onion": self.collection_without_credential_onion,
            }

            # Verifica se um nome de coleção específico foi fornecido
            if collection_name and collection_name in collections:
                # Retorna documentos apenas da coleção especificada
                documents = list(collections[collection_name].find({}, {"_id": 0}))
                self.log_manager.log(
                    "info",
                    f"Documents fetched from {collection_name}",
                    category="crawler_manager",
                    task_state="running",
                )
                return {collection_name: documents}
            else:
                # Caso nenhum nome específico seja fornecido, retorna todos os documentos
                all_documents = {}
                for collection_name, collection in collections.items():
                    documents = list(collection.find({}, {"_id": 0}))
                    all_documents[collection_name] = documents
                    self.log_manager.log(
                        "info",
                        f"Documents fetched from {collection_name}",
                        category="crawler_manager",
                        task_state="running",
                    )

                self.log_manager.log(
                    "info",
                    "Successfully fetched all documents",
                    category="crawler_manager",
                    task_state="success",
                )
                return all_documents
        except Exception as e:
            self.log_manager.capture_exception(
                e, "Failed to fetch documents", category="crawler_manager"
            )

    def export_collections(self, export_dir: str):
        task_state = "running"
        try:
            self.log_manager.log(
                "info",
                "Starting export of collections",
                category="crawler_manager",
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
                    # Removendo protocolos e 'www' da URL
                    simplified_url = re.sub(r"https?://", "", url)
                    simplified_url = re.sub(r"www\.", "", simplified_url)
                    # Substituindo caracteres não permitidos em nomes de arquivos
                    filename = (
                        simplified_url.replace(".", "_").replace("/", "_").replace(":", "_")
                        + ".json"
                    )
                    with (collection_dir / filename).open("w") as file:
                        json.dump(document, file)

                self.log_manager.log(
                    "info",
                    f"Documents exported for collection {collection_name}",
                    category="crawler_manager",
                    task_state="running",
                )

            self.log_manager.log(
                "info",
                "Export completed successfully",
                category="crawler_manager",
                task_state="success",
            )
        except Exception as e:
            self.log_manager.capture_exception(
                e, "Failed to export collections", category="crawler_manager"
            )

    def import_collections(self, meta_update: bool = False):
        imported_urls = []
        ignored_urls = []  # Esta lista agora conterá tuplas de (nome do arquivo, motivo)

        try:
            if meta_update:
                self.db_client.drop_database(self.db.name)
                self.log_manager.log(
                    level="info",
                    message=f"Database '{self.db.name}' dropped for meta update.",
                    category="crawler_manager",
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
                        category="crawler_manager",
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
                                    category="crawler_manager",
                                    task_state="success",
                                )
                            except Exception as e:
                                ignored_urls.append((file_path.name, str(e)))
                                self.log_manager.log(
                                    level="error",
                                    message=f"Error inserting url {url} in {collection_name}: {e}",
                                    category="crawler_manager",
                                    task_state="failed",
                                    exc_info=e,
                                )

            self.log_manager.log(
                level="info",
                message="Import completed successfully",
                category="crawler_manager",
                task_state="success",
            )
            if ignored_urls:
                for ignored_url in ignored_urls:
                    self.log_manager.log(
                        level="warning",
                        message=f"Ignored URL from file '{ignored_url[0]}': {ignored_url[1]}",
                        category="crawler_manager",
                        task_state="skipped",
                    )
            self.log_manager.log(
                level="info",
                message=f"Imported URLs: {len(imported_urls)}. Ignored URLs: {len(ignored_urls)}.",
                category="crawler_manager",
                task_state="skipped",
            )
        except FileNotFoundError as e:
            self.log_manager.log(
                level="error",
                message="Cloned repository directory not found: " + str(e),
                category="crawler_manager",
                task_state="failed",
                exc_info=e,
            )
        except Exception as e:
            self.log_manager.log(
                level="error",
                message="Failed to import collections: " + str(e),
                category="crawler_manager",
                task_state="failed",
                exc_info=e,
            )
