from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.crawler.crawler_manager import CrawlerManager

if __name__ == "__main__":
    config = SadifConfiguration()
    db_url = config.get_configuration("MONGODB_URL")
    db_real = MongoClient(db_url)
    crawler_manager = CrawlerManager(db_real)
    crawler_manager.import_collections(meta_update=True)
