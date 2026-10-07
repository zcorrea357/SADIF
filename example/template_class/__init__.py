# mongo_connection.py
from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration


class MongoDBConnection:
    def __init__(self):
        self.mongo_config = SadifConfiguration()
        self.client = None

    def connect(self):
        print(self.mongo_config.get_configuration("MONGODB_URL"))
        if self.client is None:
            self.client = MongoClient(self.mongo_config.get_configuration("MONGODB_URL"))
        return self.client

    def get_database(self, db_name):
        if self.client is None:
            self.connect()
        return self.client[db_name]


if __name__ == "__main__":
    connection = MongoDBConnection()
    database = connection.get_database(
        connection.mongo_config.get_configuration("MONGODB_DATABASE_CLIENTS")
    )
    print(database.list_collection_names())
