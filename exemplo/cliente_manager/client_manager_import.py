from pymongo import MongoClient

from sadif.clientmanager.client_data_import import ClientManagerImport
from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.gitmanager import GitManager

if __name__ == "__main__":
    config = SadifConfiguration()

    git_repo_url = config.get_configuration("GIT_REPO_CLIENT_MONITORING_URL")
    access_token = config.get_configuration("GIT_REPO_TOKEN")
    db_url = config.get_configuration("MONGODB_URL")
    git_manager = GitManager(git_repo_url, access_token)

    db_real = MongoClient(db_url)
    manager = ClientManagerImport(db_client=db_real, git_manager=git_manager)
    print(manager.import_from_json(meta_update=True))
