import json
import os
import re
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from pathlib import Path

import requests
from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.gitmanager import GitManager
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager
from sadif.frameworks_drivers.modules_manager import ModuleDatabaseManager
from sadif.interfaces.base_modules import IBaseModule


class RansomwhatImport(IBaseModule):
    """
    A class to import, update, and manage data from a specified Git repository to a MongoDB collection
    for the Ransomwhat module. It handles operations like initializing module collections, executing
    data imports, listing data, updating the Git repository with new data, and importing data from
    the Git repository to MongoDB.

    Attributes:
        client (MongoClient): A MongoClient object for database interaction.
        sadif_internal_config (SadifConfiguration): Configuration object for internal settings.
        ransomwhat_url (str): URL to fetch Ransomwhat data.
        ransomwhat_collection (str): Name of the MongoDB collection for Ransomwhat data.
        ransomwhat_module_name (str): Name of the Ransomwhat module.
        ransomwhat_json_schema (dict): JSON schema for Ransomwhat data validation.
        git_password (str): Password or token for Git repository access.
        git_url (str): URL of the Git repository for data modules.
        modules_manager (ModuleDatabaseManager): Manager for database module operations.
        sadif_user (str): User identifier for SADIF internal operations.
        log_manager (LogManager): LogManager instance for logging.
        git_manager (GitManager): GitManager instance for Git operations.
    """

    def __init__(self, db_client: MongoClient | None = None) -> None:
        """
        Initializes the RansomwhatImport class with MongoDB connection and configurations.

        Parameters:
            db_client (Optional[MongoClient]): The MongoDB client instance. Defaults to a new client if None.
        """
        self.client = db_client if db_client else MongoClient("localhost", 27017)
        self.sadif_internal_config = SadifConfiguration()
        self.ransomwhat_url: str = self.sadif_internal_config.get_configuration(
            "MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_URL"
        )
        self.ransomwhat_collection: str = self.sadif_internal_config.get_configuration(
            "MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_COLLECTION"
        )
        self.ransomwhat_module_name: str = self.sadif_internal_config.get_configuration(
            "MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_NAME"
        )
        self.ransomwhat_json_schema: dict = self.sadif_internal_config.get_configuration(
            "MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_JSON_SCHEMA"
        )
        self.git_password: str = self.sadif_internal_config.get_configuration("GIT_REPO_TOKEN")
        self.git_url: str = self.sadif_internal_config.get_configuration("SADIF_DATA_MODULES_URL")
        self.modules_manager = ModuleDatabaseManager(self.client)
        self.sadif_user = self.sadif_internal_config.get_configuration("SADIF_INTERNAL_USER")

        # Inicialização correta do LogManager
        self.log_manager = LogManager()

        self.initialize_module_collection()
        self.git_manager = GitManager(repo_url=self.git_url, token=self.git_password)

    def initialize_module_collection(self) -> None:
        """
        Initializes the MongoDB collection for the Ransomwhat module with a specific JSON schema.
        Logs the outcome of the operation.
        """
        try:
            self.modules_manager.create_module_collection(
                module_name=self.ransomwhat_module_name,
                validation_schema=self.ransomwhat_json_schema,
            )
            self.log_manager.log(
                "info",
                "Module collection initialized successfully.",
                category="module_manager",
                task_state="running",
            )
        except Exception as e:
            self.log_manager.log(
                "error",
                f"Failed to initialize module collection: {e}",
                category="module_manager",
                exc_info=e,
                task_state="failed",
            )

    def execute(self) -> None:
        """
        Executes the main routine to extract URLs and insert them into the MongoDB collection.
        Handles and logs exceptions during the process.
        """
        urls = self.extract_v3_urls()
        for url in urls:
            document = {"url": url}
            try:
                self.modules_manager.insert_document(self.ransomwhat_module_name, document)
                self.log_manager.log(
                    "info",
                    f"Inserted URL: {url}",
                    category=f"module_{self.ransomwhat_module_name}",
                    task_state="running",
                )
            except Exception as e:
                self.log_manager.log(
                    "error",
                    f"Failed to insert document: {e}",
                    category="database",
                    exc_info=e,
                    task_state="failed",
                )

    def list_data(self) -> list[dict]:
        """
        Lists all data entries from the Ransomwhat module's MongoDB collection.
        Handles and logs exceptions, returning an empty list on failure.

        Returns:
            List[dict]: A list of dictionaries representing the data entries.
        """
        try:
            data = self.modules_manager.list_module_data(self.ransomwhat_module_name)
            self.log_manager.log(
                "info",
                "Data listed successfully.",
                category="data_processing",
                task_state="success",
            )
            return data
        except Exception as e:
            self.log_manager.log(
                "error",
                f"Failed to list data: {e}",
                category="database",
                exc_info=e,
                task_state="failed",
            )
            return []

    def update_git_repository(self) -> None:
        """
        Updates the Git repository with the latest data from the MongoDB collection.
        Handles directory creation, file updates, and Git operations including commit and push.
        Logs all steps and exceptions.
        """
        try:
            # Cloning the Git repository
            repo_dir = Path(self.git_manager.clone_repo())
            self.log_manager.log(
                "info", f"Repository cloned to: {repo_dir}", category="git", task_state="success"
            )

            directory_path = repo_dir / self.ransomwhat_module_name
            directory_path.mkdir(parents=True, exist_ok=True)
            self.log_manager.log(
                "info",
                f"Directory '{directory_path}' ensured.",
                category="git",
                task_state="success",
            )

            updated_files_count = 0
            update_urls = self.list_data()
            if isinstance(update_urls, list):
                with self.temporary_directory_change(repo_dir):
                    for data in update_urls:
                        url = data.get("url")
                        if url:
                            file_name = Path(url).stem + ".json"
                            json_file_path = directory_path / file_name
                            with json_file_path.open("w") as json_file:
                                json.dump(data, json_file, indent=4)
                                self.log_manager.log(
                                    "info",
                                    f"JSON file created: {json_file_path}",
                                    category="git",
                                    task_state="running",
                                )
                            updated_files_count += 1
                    self.log_manager.log(
                        "info",
                        f"{updated_files_count} files updated.",
                        category="git",
                        task_state="success",
                    )
            else:
                self.log_manager.log(
                    "error",
                    "update_urls is not a list of dictionaries.",
                    category="git",
                    task_state="failed",
                )

            # Building and logging the commit message
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005
            commit_message = (
                f"Automated update: {updated_files_count} URLs at {now} by {self.sadif_user}"
            )
            self.log_manager.log(
                "info", f"Commit message: {commit_message}", category="git", task_state="success"
            )

            self.git_manager.commit_changes(commit_message)
            self.git_manager.push_changes("main")
            self.log_manager.log(
                "info",
                "Changes committed and pushed successfully.",
                category="git",
                task_state="success",
            )
        except Exception as e:
            self.log_manager.log(
                "error",
                f"Failed to update Git repository: {e}",
                category="git",
                exc_info=e,
                task_state="failed",
            )

    def import_git_repository(self) -> None:
        """
        Imports data from the Git repository to the MongoDB collection.
        Handles Git clone, file reading, and document insertion, with logging for each step.
        """
        try:
            # Start of import
            self.log_manager.log(
                "info", "Starting Git repository import.", category="git", task_state="running"
            )

            # Clone the Git repository temporarily to a local directory
            repo_dir = Path(self.git_manager.clone_repo())
            self.log_manager.log(
                "info", f"Repository cloned to: {repo_dir}", category="git", task_state="success"
            )

            # Set the path to the specific modules directory within the cloned repository
            modules_dir = repo_dir / self.ransomwhat_module_name

            if not modules_dir.exists():
                self.log_manager.log(
                    "warning",
                    f"Directory not found: {modules_dir}",
                    category="git",
                    task_state="failed",
                )
                return

            # Counter for successfully imported files
            imported_files_count = 0

            # Read all JSON files in the directory and import the data into MongoDB
            for json_file in modules_dir.glob("*.json"):
                try:
                    with json_file.open() as file:
                        data = json.load(file)
                        self.modules_manager.insert_document(self.ransomwhat_module_name, data)
                        imported_files_count += 1
                        self.log_manager.log(
                            "info",
                            f"File imported successfully: {json_file}",
                            category="data_processing",
                            task_state="success",
                        )

                except Exception as e:
                    self.log_manager.log(
                        "error",
                        f"Error importing file {json_file}: {e}",
                        category="data_processing",
                        exc_info=e,
                        task_state="failed",
                    )

            self.log_manager.log(
                "info",
                f"Total files imported: {imported_files_count}",
                category="data_processing",
                task_state="success",
            )

        except Exception as e:
            self.log_manager.log(
                "error",
                f"Error during Git repository import: {e}",
                category="git",
                exc_info=e,
                task_state="failed",
            )

    @contextmanager
    def temporary_directory_change(self, directory: Path) -> AbstractContextManager:
        """
        A context manager to temporarily change the current working directory.

        Parameters:
            directory (Path): The target directory to change to.

        Yields:
            None
        """
        original_directory = Path.cwd()
        try:
            os.chdir(directory)
            yield
        finally:
            os.chdir(original_directory)
            self.log_manager.log(
                "debug",
                f"Changed directory back to {original_directory}",
                category="file",
                task_state="running",
            )

    def _fetch_groups_text(self) -> str:
        """
        Fetches the raw text from the Ransomwhat URL.

        Returns:
            str: The raw text data as a string.
        """
        response = requests.get(self.ransomwhat_url, timeout=10, verify=False)  # noqa: S501
        groups_raw = response.json()
        return str(groups_raw)

    def extract_v3_urls(self) -> list[str]:
        """
        Extracts V3 Onion URLs from the fetched text data.

        Returns:
            List[str]: A list of V3 Onion URLs.
        """

        groups_text = self._fetch_groups_text()

        v3_pattern = r"[a-z2-7]{56}\.onion"
        all_urls = re.findall(v3_pattern, groups_text)

        v3_urls: set[str] = set()

        for raw_url in all_urls:
            # Use a different variable for the potentially modified URL
            modified_url = raw_url
            if not raw_url.startswith(("http://", "https://")):
                modified_url = f"http://{raw_url}"
            v3_urls.add(modified_url)

        return list(v3_urls)


if __name__ == "__main__":
    db_real = MongoClient("")
    a = RansomwhatImport(db_real)
    a.import_git_repository()
