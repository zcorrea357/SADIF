from pymongo import MongoClient

from sadif.config.soar_config import SadifConfiguration
from sadif.frameworks_drivers.soar_yara.yara_compiler import SoarYaraCompiler

if __name__ == "__main__":
    config = SadifConfiguration()
    db_url = config.get_configuration("MONGODB_URL")
    db_real = MongoClient(db_url)
    compiler = SoarYaraCompiler(db_real)
    # Texto que casa com a regra InternalMonitoramentoLeak04 (chave da API do Shodan)
    matches = compiler.match_text("config: shodan_api_key: abc123XYZ")
    print(matches)
