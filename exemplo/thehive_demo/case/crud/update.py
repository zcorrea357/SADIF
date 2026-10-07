from sadif.config.soar_config import SadifConfiguration
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_datatype import (
    CaseDataType,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.create_case import (
    CreateCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.update_case import (
    UpdateCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)
from sadif.utils.generete_string.random_string_generator import RandomStringGenerator

if __name__ == "__main__":
    config = SadifConfiguration()
    thehive_url = config.get_configuration("THEHIVE")
    thehive_api_key = config.get_configuration("THEHIVE_API_SERVICE")
    session = SessionThehive(base_url=thehive_url)
    session.set_api_key(thehive_api_key)

    # Cria um caso para o exemplo (ou troque case_id pelo ID de um caso existente)
    generator = RandomStringGenerator()
    created, _ = CreateCase(session).create(
        CaseDataType(title=generator.generate_string_title("Case Example"), description="Exemplo")
    )
    case_id = created["_id"]

    update_case = UpdateCase(session)
    update_data = {"tags": ["new_tag"]}
    response, status = update_case.update_case(case_id, update_data)
    if status != 200:
        msg = f"Erro ao atualizar caso {case_id}: {status}"
        raise Exception(msg)
    print(response["tags"])
