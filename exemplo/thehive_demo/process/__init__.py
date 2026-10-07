import random
from collections.abc import Callable
from typing import Any

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.list_case import (
    ListCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class JsonProcessor:
    def __init__(self, clientes: list, categorias: list, servico_constante: str):
        self.clientes = clientes
        self.categorias = categorias
        self.servico_constante = servico_constante
        self.tag_action_dict = self._generate_action_dict()
        self.total_carregados = 0
        self.total_enviados = 0
        self.total_ignorados = 0

    def _generate_action_dict(self) -> dict[tuple[str, str, str], Callable[..., None]]:
        combinacoes = [
            (cliente, categoria, self.servico_constante)
            for cliente in self.clientes
            for categoria in self.categorias
        ]
        return {comb: self._executar_acao for comb in combinacoes}

    def _executar_acao(self, cliente: str, categoria: str, servico: str):
        self.total_enviados += 1
        if servico == "ServiceNow" == cliente == categoria:
            print(f"Enviando chamado via webpost para {cliente}, {categoria}, {servico}")
        else:
            print(f"Ação executada para {cliente}, {categoria}, {servico}")

    def process_json(self, json_data: dict[str, Any]):
        self.total_carregados += 1
        tags = set(json_data.get("tags", []))
        action_executed = False
        for tag_combination, action in self.tag_action_dict.items():
            if tags.issuperset(tag_combination):
                cliente, categoria, servico = tag_combination
                action(cliente, categoria, servico)
                action_executed = True
                break
        if not action_executed:
            self.total_ignorados += 1


def generate_random_json_calls(clientes, categorias, servico_constante, n=10):
    """
    Generate a list of random JSON calls.

    :param clientes: List of clients.
    :param categorias: List of categories.
    :param servico_constante: The constant service.
    :param n: Number of JSON calls to generate.
    :return: List of randomly generated JSON calls.
    """
    json_calls = []

    for _ in range(n):
        # Escolher aleatoriamente se o serviço constante será incluído ou não
        tags = [
            random.choice(clientes),
            random.choice(categorias),
            servico_constante if random.choice([True, False]) else "OutroServico",
        ]

        # Remover aleatoriamente um ou mais tags para criar algumas entradas inválidas
        for _ in range(random.randint(0, len(tags) - 1)):
            tags.remove(random.choice(tags))

        json_calls.append({"tags": tags})

    return json_calls


if __name__ == "__main__":
    config = SadifConfiguration()
    thehive_url = config.get_configuration("THEHIVE")
    thehive_api_key = config.get_configuration("THEHIVE_API_SERVICE")
    session = SessionThehive(base_url=thehive_url)
    session.set_api_key(thehive_api_key)
    list_case = ListCase(session)

    # List all cases
    response, status = list_case.list_cases()
    print(response)

    # Inicialização
    clientes = ["cliente 1", "cliente 2", "cliente 3", "cliente 4", "cliente 5", "cliente 6"]
    categorias = ["domaindect", "vipDesct", "Investigation"]
    servico_constante = "ServiceNow"

    processor = JsonProcessor(clientes, categorias, servico_constante)

    # Gerar chamadas JSON aleatórias
    random_json_calls = response
    print(random_json_calls)
    # Processar cada chamada JSON
    for json_call in random_json_calls:
        processor.process_json(json_call)

    # Verificar os resultados
    print(f"Total Carregados: {processor.total_carregados}")
    print(f"Total Enviados: {processor.total_enviados}")
    print(f"Total Ignorados: {processor.total_ignorados}")
