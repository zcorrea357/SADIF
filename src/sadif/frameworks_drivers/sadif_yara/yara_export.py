import zipfile
from pathlib import Path  # Import Path from pathlib for file operations

from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class YaraRulesExporter:
    def __init__(
        self, mongo_uri: str, db_name: str, export_dir: str, *, auto_extract: bool = False
    ):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.export_dir = export_dir
        self.auto_extract = auto_extract
        self.logger = LogManager()
        self.sadif_internal_config = SadifConfiguration()
        self.mongo_client_prefix = self.sadif_internal_config.get_configuration(
            "MONGODB_CLIENT_PREFIX"
        )
        if not Path(export_dir).exists():
            Path(export_dir).mkdir(parents=True)

    def export_rules(self):
        """
        Exports Yara rules from the database to files in the specified directory.
        """
        zip_filename = Path(self.export_dir) / "YaraRulesExport.zip"
        with zipfile.ZipFile(str(zip_filename), "w") as zipf:
            for collection in self.db.list_collection_names():
                if collection.startswith(self.mongo_client_prefix):
                    client_name = collection.split("_", 1)[1]
                    client_dir = Path(self.export_dir) / client_name
                    if self.auto_extract and not client_dir.exists():
                        client_dir.mkdir(parents=True)

                    for rule in self.db[collection].find():
                        rule_name = rule.get("rule_name")
                        rule_content = rule.get("rule_content")
                        rule_file_path = (
                            client_dir / f"{rule_name}.yar"
                            if self.auto_extract
                            else Path(f"{client_name}/{rule_name}.yar")
                        )

                        if self.auto_extract:
                            with rule_file_path.open("w") as file:
                                file.write(rule_content)
                        zipf.write(str(rule_file_path), str(rule_file_path))
                        self.logger.log(
                            "info", f"Rule {rule_name} exported to {client_name}", category="yara"
                        )

        self.logger.log("info", f"Rules exported to {zip_filename}", category="yara")
        print(f"Rules exported to {zip_filename}")
