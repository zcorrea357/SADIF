from pymongo import MongoClient

from sadif.config.soar_config import SadifConfiguration
from sadif.frameworks_drivers.crawler.base_crawler import BaseCrawler

config = SadifConfiguration()
db_url = config.get_configuration("MONGODB_URL")
db_real = MongoClient(db_url)
crawler = BaseCrawler(base_url="https://example.com", depth=1, timeout=5, db_client=db_real)
crawler.crawl(crawler.base_url)
yara_matches = crawler.get_yara_matches()
print(yara_matches)  # Imprime as correspondências Yara acumuladas
