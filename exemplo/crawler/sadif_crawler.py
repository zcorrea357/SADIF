from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.crawler.base_crawler import BaseCrawler
from sadif.frameworks_drivers.web.authenticator.basic_auth_strategy import BasicAuthStrategy
from sadif.frameworks_drivers.web.session_manager import SessionManager

if __name__ == "__main__":
    config = SadifConfiguration()
    db_url = config.get_configuration("MONGODB_URL")
    db_real = MongoClient(db_url)

    # Credenciais de exemplo: o httpbin aceita exatamente este usuário/senha na URL abaixo
    username = "your_username"
    password = "your_password"  # noqa: S105
    url = f"https://httpbin.org/basic-auth/{username}/{password}"

    session_manager = SessionManager()

    # Criar uma sessão com autenticação básica
    session_with_basic_auth = session_manager.create_session(BasicAuthStrategy(username, password))

    # Inicializa o crawler e usa a sessão autenticada nas requisições
    crawler = BaseCrawler(base_url=url, depth=1, timeout=50, db_client=db_real)
    crawler.session = session_with_basic_auth
    print("Status com autenticação:", crawler.session.get(url, timeout=crawler.timeout).status_code)

    crawler.crawl(crawler.base_url)
    session_manager.close_all_sessions()

    print(crawler.visited_urls)
    print("Quantidade de match found:", len(crawler.get_yara_matches()))
    print(crawler.get_yara_matches())
