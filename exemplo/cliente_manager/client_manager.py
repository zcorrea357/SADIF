from pymongo import MongoClient

from sadif.clientmanager.client_data_manager import ClientManager
from sadif.config.soar_config import SadifConfiguration
from sadif.utils.generete_string.random_string_generator import RandomStringGenerator

if __name__ == "__main__":
    randstr = RandomStringGenerator()
    config = SadifConfiguration()
    db_real = MongoClient(config.get_configuration("MONGODB_URL"))
    manager = ClientManager(db_client=db_real)
    for i in range(10):
        print(
            manager.create_client_collection(
                f"{randstr.generate_string_title('caju').split()[4]}",
                "TODO",
                "TODO",
                overwrite=True,
            )
        )
