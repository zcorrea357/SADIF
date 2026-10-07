from pymongo import MongoClient

from sadif.clientmanager.client_data_manager import ClientManager
from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.gitmanager import GitManager
from sadif.frameworks_drivers.sadif_yara.yara_import import YaraRulesImporter

if __name__ == "__main__":
    config = SadifConfiguration()

    git_repo_url = config.get_configuration("GIT_REPO_CLIENT_YARA_RULES_URL")
    access_token = config.get_configuration("GIT_REPO_TOKEN")
    git_manager = GitManager(git_repo_url, access_token)

    db_url = config.get_configuration("MONGODB_URL")
    yara_db = config.get_configuration("MONGODB_DATABASE_YARA")

    client = MongoClient(db_url)
    client_manager = ClientManager(client)
    print(client_manager.list_all_clients())
    # Exemplo de como usar a classe com um repositório Git
    importer = YaraRulesImporter(
        directory=None,
        clients=client_manager.list_all_clients(),
        db_client=client,
        overwrite=True,
        git_manager=git_manager,
    )
    importer.import_rules(meta_update=True)
