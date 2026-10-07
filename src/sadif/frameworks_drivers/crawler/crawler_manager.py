from pathlib import Path
from urllib.parse import urlparse

from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.crawler.crawler_data_export import export_documents, export_filename
from sadif.frameworks_drivers.crawler.crawler_data_import import (
    create_unique_url_indexes,
    import_crawler_directory,
)
from sadif.frameworks_drivers.gitmanager import GitManager
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class CrawlerManager:
    def __init__(self, db_client=None) -> None:
        self.directory: str | None = None
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
                self.log_manager.log(
                    "error",
                    "Error in cloning the Git repository",
                    category="crawler_manager",
                    task_state="failed",
                )
            self.db_client = (
                db_client
                if db_client is not None
                else MongoClient(self.sadif_internal_config.get_configuration("MONGODB_URL"))
            )
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

            create_unique_url_indexes(collections)

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
                # O _id é imutável no MongoDB: não pode fazer parte do $set
                fields = {key: value for key, value in document.items() if key != "_id"}
                result = collection.update_one({"url": url}, {"$set": fields}, upsert=True)
                action = "inserted" if result.upserted_id is not None else "updated"
                doc_msg = f"Document with URL '{url}' {action}."
                self.log_manager.log(
                    "info", doc_msg, category="crawler_manager", task_state="success"
                )
                return result.upserted_id or result.matched_count
            else:
                try:
                    # Insere uma cópia para não alterar (adicionar _id) o documento recebido
                    inserted_id = collection.insert_one(dict(document)).inserted_id
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
            return None

    def _determine_collection(self, url: str, document: dict) -> Collection:
        task_state = "running"
        determ_msg = "Determining collection for URL"
        self.log_manager.log("info", determ_msg, category="crawler_manager", task_state=task_state)
        if not isinstance(url, str):
            msg = f"URL must be a string, got {type(url).__name__}"
            raise TypeError(msg)
        parsed_url = urlparse(url.strip())
        if not parsed_url.hostname and "://" not in url:
            # URLs sem esquema (ex.: 'exemplo.onion/path') não têm hostname no urlparse
            parsed_url = urlparse(f"//{url.strip()}")
        if not parsed_url.hostname:
            msg = f"Invalid URL '{url}': hostname not found"
            raise ValueError(msg)
        has_credentials = "auth_type" in document and bool(document["auth_type"])

        if parsed_url.hostname.rstrip(".").endswith(".onion"):
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

    def _collections_by_name(self) -> dict[str, Collection]:
        return {
            "crawler_with_credential_web": self.collection_with_credential_web,
            "crawler_without_credential_web": self.collection_without_credential_web,
            "crawler_with_credential_onion": self.collection_with_credential_onion,
            "crawler_without_credential_onion": self.collection_without_credential_onion,
        }

    def get_all_documents_by_collection(self, collection_name: str | None = None) -> dict | None:
        try:
            self.log_manager.log(
                "info",
                "Fetching documents from collections",
                category="crawler_manager",
                task_state="running",
            )
            collections = self._collections_by_name()

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
            return None

    @staticmethod
    def _export_filename(url: str) -> str:
        return export_filename(url)

    def export_collections(self, export_dir: str | Path) -> dict[str, int] | None:
        return export_documents(
            self.get_all_documents_by_collection(), export_dir, self.log_manager, "crawler_manager"
        )

    def import_collections(self, meta_update: bool = False) -> dict[str, list] | None:
        if getattr(self, "db", None) is None:
            self.log_manager.log(
                "error",
                "Cannot import collections: CrawlerManager is not initialized",
                category="crawler_manager",
                task_state="failed",
            )
            return None
        return import_crawler_directory(
            self.directory,
            self.db_client,
            self.db,
            self._collections_by_name(),
            self.log_manager,
            "crawler_manager",
            meta_update=meta_update,
        )
