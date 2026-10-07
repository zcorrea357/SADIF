import json
from pathlib import Path

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.gitmanager import GitManager
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


def create_unique_url_indexes(collections: list[Collection]) -> None:
    """Cria o índice único por 'url' em cada coleção informada."""
    for collection in collections:
        collection.create_index("url", unique=True)


def import_crawler_directory(
    directory: str | Path | None,
    db_client: MongoClient,
    db: Database,
    collections_by_name: dict[str, Collection],
    log_manager: LogManager,
    category: str,
    meta_update: bool = False,
) -> dict[str, list] | None:
    """
    Importa os documentos JSON das pastas 'crawler_*' de ``directory`` para o MongoDB.

    Cada pasta corresponde a uma coleção; as pastas conhecidas (``collections_by_name``) são
    gravadas nas coleções configuradas. Cada documento precisa ter 'url' (chave única) e é
    inserido ou substituído pela URL. Com ``meta_update`` o banco é apagado antes da importação
    (somente depois de validar o diretório) e os índices únicos são recriados.

    Retorna {"imported": [urls], "ignored": [(arquivo, motivo)]} ou None se a importação falhar.
    """
    imported_urls = []
    ignored_urls = []  # Esta lista contém tuplas de (nome do arquivo, motivo)

    try:
        if not directory or not Path(directory).is_dir():
            msg = f"Import directory not found: {directory}"
            raise FileNotFoundError(msg)
        import_dir_path = Path(directory)

        if meta_update:
            db_client.drop_database(db.name)
            log_manager.log(
                level="info",
                message=f"Database '{db.name}' dropped for meta update.",
                category=category,
                task_state="running",
            )
        # Os índices únicos são (re)criados antes da importação, inclusive após o drop
        create_unique_url_indexes(list(collections_by_name.values()))

        for collection_dir in sorted(import_dir_path.iterdir()):
            if not collection_dir.is_dir() or not collection_dir.name.startswith("crawler_"):
                continue

            collection_name = collection_dir.name
            collection = collections_by_name.get(collection_name)
            if collection is None:
                collection = db[collection_name]
                create_unique_url_indexes([collection])

            for file_path in sorted(collection_dir.iterdir()):
                if not file_path.is_file() or file_path.suffix.lower() != ".json":
                    continue
                try:
                    with file_path.open(encoding="utf-8") as file:
                        data = json.load(file)
                except (OSError, ValueError) as e:
                    ignored_urls.append((file_path.name, f"Invalid JSON file: {e}"))
                    continue

                documents = data if isinstance(data, list) else [data]
                for document in documents:
                    if not isinstance(document, dict):
                        ignored_urls.append((file_path.name, "Document must be a JSON object."))
                        continue
                    url = document.get("url", None)
                    if not url or not isinstance(url, str):
                        ignored_urls.append((file_path.name, "URL is needed to import file."))
                        continue

                    try:
                        collection.replace_one({"url": url}, document, upsert=True)
                        imported_urls.append(url)
                        log_manager.log(
                            level="info",
                            message=f"Monitoring url {url} inserted in {collection_name}.",
                            category=category,
                            task_state="success",
                        )
                    except Exception as e:
                        ignored_urls.append((file_path.name, str(e)))
                        log_manager.log(
                            level="error",
                            message=f"Error inserting url {url} in {collection_name}: {e}",
                            category=category,
                            task_state="failed",
                            exc_info=e,
                        )

        log_manager.log(
            level="info",
            message="Import completed successfully",
            category=category,
            task_state="success",
        )
        for ignored_url in ignored_urls:
            log_manager.log(
                level="warning",
                message=f"Ignored URL from file '{ignored_url[0]}': {ignored_url[1]}",
                category=category,
                task_state="skipped",
            )
        log_manager.log(
            level="info",
            message=f"Imported URLs: {len(imported_urls)}. Ignored URLs: {len(ignored_urls)}.",
            category=category,
            task_state="success",
        )
        return {"imported": imported_urls, "ignored": ignored_urls}
    except FileNotFoundError as e:
        log_manager.log(
            level="error",
            message="Cloned repository directory not found: " + str(e),
            category=category,
            task_state="failed",
            exc_info=e,
        )
    except Exception as e:
        log_manager.log(
            level="error",
            message="Failed to import collections: " + str(e),
            category=category,
            task_state="failed",
            exc_info=e,
        )
    return None


class CrawlerManagerImporter:
    def __init__(self, db_client=None, git_manager: GitManager | None = None) -> None:
        self.git_manager = git_manager
        self.directory: str | None = None
        self.log_manager = LogManager()
        init_msg = "Initializing ImportManager"
        self.log_manager.log("info", init_msg, category="import_manager", task_state="running")

        try:
            self.sadif_internal_config = SadifConfiguration()
            if self.git_manager is None:
                # Sem GitManager explícito, usa o repositório configurado
                self.git_manager = GitManager(
                    self.sadif_internal_config.get_configuration(
                        "GIT_REPO_CLIENT_CRAWLER_MONITORING"
                    ),
                    self.sadif_internal_config.get_configuration("GIT_REPO_TOKEN"),
                )
            cloned_dir = self.git_manager.clone_repo()
            if cloned_dir:
                self.directory = cloned_dir
            else:
                self.log_manager.log(
                    "error",
                    "Error in cloning the Git repository",
                    category="import_manager",
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
            init_success_msg = "ImportManager initialized successfully"
            self.log_manager.log(
                "info", init_success_msg, category="import_manager", task_state="success"
            )
        except Exception as e:
            init_fail_msg = "Failed to initialize ImportManager"
            self.log_manager.capture_exception(e, init_fail_msg, category="import_manager")

    def _collections_by_name(self) -> dict[str, Collection]:
        return {
            "crawler_with_credential_web": self.collection_with_credential_web,
            "crawler_without_credential_web": self.collection_without_credential_web,
            "crawler_with_credential_onion": self.collection_with_credential_onion,
            "crawler_without_credential_onion": self.collection_without_credential_onion,
        }

    def import_collections(self, meta_update: bool = False) -> dict[str, list] | None:
        if getattr(self, "db", None) is None:
            self.log_manager.log(
                "error",
                "Cannot import collections: ImportManager is not initialized",
                category="import_manager",
                task_state="failed",
            )
            return None
        return import_crawler_directory(
            self.directory,
            self.db_client,
            self.db,
            self._collections_by_name(),
            self.log_manager,
            "import_manager",
            meta_update=meta_update,
        )
