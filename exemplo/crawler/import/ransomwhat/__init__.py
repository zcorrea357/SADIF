from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.crawler.crawler_manager import CrawlerManager
from sadif.modules.populate.url_to_dbs.ransomwhatimport import RansomwhatImport

if __name__ == "__main__":
    config = SadifConfiguration()
    onion_extractor = RansomwhatImport()
    v3_urls = onion_extractor.extract_v3_urls()
    db_url = config.get_configuration("MONGODB_URL")
    db_real = MongoClient(db_url)
    crawler_manager = CrawlerManager(db_real)
    print(v3_urls)
    for onion_url in v3_urls:
        no_auth_document = {
            "url": f"{onion_url}",
            "timeout": 100,
            "max_threads": 10,
            "depth": 3,
        }
        crawler_manager.process_document(document=no_auth_document, overwrite=True)
