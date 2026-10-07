from sadif.config.soar_config import SadifConfiguration
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_datatype import (
    CaseDataType,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.create_case import (
    CreateCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_observable import (
    Observable,
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

    observable_instance = Observable(session)
    data_type = ["domain", "fqdn", "hostname", "ip", "url"]
    observable_ids = []
    for i in data_type:
        data = (
            "93.184.215.14" if i == "ip" else "https://example.com" if i == "url" else "example.com"
        )
        response, status = observable_instance.add_to_case(case_id=case_id, data_type=i, data=data)
        print(status, response)
        observable_ids.extend(observable["_id"] for observable in response)

    response = observable_instance.update_observable(
        observable_id=observable_ids[0], data_type="domain", add_tags=["newTag1"]
    )
    print(response)
