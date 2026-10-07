import hashlib
import json
import re
from pathlib import Path

from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.crawler.crawler_data_import import create_unique_url_indexes
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


def export_filename(url: str) -> str:
    """Gera o nome do arquivo JSON exportado a partir da URL do documento."""
    # Removendo protocolos e 'www' da URL
    simplified_url = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", url)
    simplified_url = re.sub(r"^www\.", "", simplified_url)
    # Substituindo caracteres não permitidos em nomes de arquivos
    return re.sub(r"[^A-Za-z0-9_-]", "_", simplified_url) + ".json"


def export_documents(
    all_documents: dict[str, list] | None,
    export_dir: str | Path,
    log_manager: LogManager,
    category: str,
) -> dict[str, int] | None:
    """
    Grava cada documento em <export_dir>/<coleção>/<url simplificada>.json.

    Retorna {coleção: quantidade de arquivos gravados} ou None se a exportação falhar.
    """
    try:
        log_manager.log(
            "info", "Starting export of collections", category=category, task_state="running"
        )
        if all_documents is None:
            msg = "Could not fetch the documents to export"
            raise RuntimeError(msg)

        export_dir_path = Path(export_dir)
        export_dir_path.mkdir(parents=True, exist_ok=True)
        exported: dict[str, int] = {}

        for collection_name, documents in all_documents.items():
            collection_dir = export_dir_path / collection_name
            collection_dir.mkdir(parents=True, exist_ok=True)
            written: set[str] = set()

            for document in documents:
                url = document.get("url")
                if not url or not isinstance(url, str):
                    log_manager.log(
                        "warning",
                        f"Document without URL skipped in {collection_name}",
                        category=category,
                        task_state="skipped",
                    )
                    continue
                filename = export_filename(url)
                if filename in written:
                    # URLs diferentes podem gerar o mesmo nome (ex.: http/https, 'www.'):
                    # um sufixo determinístico evita sobrescrever o arquivo de outro documento
                    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]  # noqa: S324
                    filename = f"{filename[: -len('.json')]}_{digest}.json"
                with (collection_dir / filename).open("w", encoding="utf-8") as file:
                    json.dump(document, file, ensure_ascii=False, default=str)
                written.add(filename)
            exported[collection_name] = len(written)

            log_manager.log(
                "info",
                f"Documents exported for collection {collection_name}",
                category=category,
                task_state="running",
            )

        log_manager.log(
            "info", "Export completed successfully", category=category, task_state="success"
        )
        return exported
    except Exception as e:
        log_manager.capture_exception(e, "Failed to export collections", category=category)
        return None


class CrawlerManagerExport:
    def __init__(self, db_client=None) -> None:
        self.log_manager = LogManager()
        init_msg = "Initializing ExportManager"
        self.log_manager.log("info", init_msg, category="export_manager", task_state="running")

        try:
            self.sadif_internal_config = SadifConfiguration()
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

            create_unique_url_indexes(collections)

            indexes_msg = "Unique indexes created for all collections"
            self.log_manager.log(
                "info", indexes_msg, category="export_manager", task_state="success"
            )
        except Exception as e:
            index_fail_msg = "Failed to create unique indexes"
            self.log_manager.capture_exception(e, index_fail_msg, category="export_manager")

    def export_collections(self, export_dir: str | Path) -> dict[str, int] | None:
        return export_documents(
            self.get_all_documents_by_collection(), export_dir, self.log_manager, "export_manager"
        )

    def get_all_documents_by_collection(self, collection_name: str | None = None) -> dict | None:
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
            return None
