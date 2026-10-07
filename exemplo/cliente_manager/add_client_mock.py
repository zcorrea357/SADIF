from sadif.clientmanager.client_data_manager import ClientManager

if __name__ == "__main__":
    import mongomock

    # Criar uma instância mock do MongoClient
    mock_client = mongomock.MongoClient()

    # Criar uma instância de ClientManager usando o mock_client
    manager = ClientManager(db_client=mock_client)
    print(manager.create_client_collection("Empresa XYZ", "dsadsa", "12345"))

    module_info = {
        "ativação": "2024-01-01",
        "versão": "1.0",
        "configurações": {"opção1": True, "opção2": "algum valor"},
    }
    print(manager.update_module_info("Empresa XYZ", "ModuloB", module_info))
    # Buscar todas as informações dos módulos do cliente
    modules_info = manager.find_client_modules("Empresa XYZ")
    print("Todas as informações dos módulos:", modules_info)

    # Acessar informações de um módulo específico, por exemplo, "ModuloA"
    modulo_a_info = modules_info.get("ModuloA")
    print("Informações do ModuloA:", modulo_a_info)
    # Atualizando um módulo permitido
    print(
        manager.update_module_info("Empresa XYZ", "ModuloA", {"configuração": "valor"})
    )  # Deve funcionar

    # Tentando atualizar um módulo não permitido
    print(
        manager.update_module_info("Empresa XYZ", "ModuloNaoPermitido", {"configuração": "valor"})
    )  # Deve retornar erro
    print(manager.delete_client_collection("Empresa XYZ"))
