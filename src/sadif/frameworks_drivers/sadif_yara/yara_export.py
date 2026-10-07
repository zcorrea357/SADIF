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

    def export_rules(self) -> Path:
        """
        Exports Yara rules from the database to files in the specified directory.
        """
        zip_filename = Path(self.export_dir) / "YaraRulesExport.zip"
        prefix_length = len(self.mongo_client_prefix)
        with zipfile.ZipFile(str(zip_filename), "w") as zipf:
            for collection in self.db.list_collection_names():
                if (
                    collection.startswith(self.mongo_client_prefix)
                    and len(collection) > prefix_length
                ):
                    client_name = collection[prefix_length:]
                    client_dir = Path(self.export_dir) / client_name
                    if self.auto_extract and not client_dir.exists():
                        client_dir.mkdir(parents=True)

                    for rule in self.db[collection].find():
                        rule_name = rule.get("rule_name")
                        rule_content = rule.get("rule_content")
                        if not rule_name or rule_content is None:
                            self.logger.log(
                                "warning",
                                f"Invalid rule document ignored in {collection}",
                                category="yara",
                            )
                            continue
                        arcname = f"{client_name}/{rule_name}.yar"
                        if self.auto_extract:
                            rule_file_path = client_dir / f"{rule_name}.yar"
                            rule_file_path.write_text(rule_content, encoding="utf-8")
                        zipf.writestr(arcname, rule_content)
                        self.logger.log(
                            "info", f"Rule {rule_name} exported to {client_name}", category="yara"
                        )

        self.logger.log("info", f"Rules exported to {zip_filename}", category="yara")
        print(f"Rules exported to {zip_filename}")
        return zip_filename
