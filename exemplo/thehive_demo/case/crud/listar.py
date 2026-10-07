from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.list_case import (
    ListCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)
from sadif.utils.generete_string.random_string_generator import RandomStringGenerator

if __name__ == "__main__":
    generator = RandomStringGenerator()
    config = SadifConfiguration()

    thehive_url = config.get_configuration("THEHIVE")
    thehive_api_key = config.get_configuration("THEHIVE_API_SERVICE")
    session = SessionThehive(base_url=thehive_url)
    session.set_api_key(thehive_api_key)
    list_case = ListCase(session)

    # List all cases
    response, status = list_case.list_cases()
    print(response)
