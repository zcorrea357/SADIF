from pymongo import MongoClient

from sadif.clientmanager.client_data_manager import ClientManager
from sadif.config.soar_config import SadifConfiguration

if __name__ == "__main__":
    config = SadifConfiguration()
    db_real = MongoClient(config.get_configuration("MONGODB_URL"))
    manager = ClientManager(db_client=db_real)

    # O nome do cliente precisa aparecer no nome das regras YARA dele
    # (ex.: "InternalMonitoramentoLeak01" pertence ao cliente "Internal")
    print(manager.create_client_collection("Internal", "Internal", "CIID-INTERNAL", overwrite=True))
    print(manager.list_all_clients())

    module_info = {
        "ativação": "2024-01-01",
        "versão": "1.0",
        "configurações": {"opção1": True, "opção2": "algum valor"},
    }
    print(manager.update_module_info("Internal", "ModuloB", module_info))
    print("Todas as informações dos módulos:", manager.find_client_modules("Internal"))

    # Tentando atualizar um módulo não permitido
    print(manager.update_module_info("Internal", "ModuloNaoPermitido", {"configuração": "valor"}))
