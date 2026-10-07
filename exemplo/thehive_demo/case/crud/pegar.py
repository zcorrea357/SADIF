from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_datatype import (
    CaseDataType,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.create_case import (
    CreateCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.get_case import (
    GetCase,
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

    get_case = GetCase(session)
    print(get_case.fetch_case(id_or_name=case_id))
