from pymongo import MongoClient

from sadif.clientmanager.client_data_export import ClientManagerExport
from sadif.config.soar_config import SadifConfiguration

if __name__ == "__main__":
    config = SadifConfiguration()

    git_repo_url = config.get_configuration("GIT_REPO_CLIENT_MONITORING_URL")
    access_token = config.get_configuration("GIT_REPO_TOKEN")
    db_url = config.get_configuration("MONGODB_URL")

    db_real = MongoClient(db_url)
    manager = ClientManagerExport(db_client=db_real)
    print(manager.export_to_json("."))
