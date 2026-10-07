from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_datatype import (
    CaseDataType,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.create_case import (
    CreateCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.delete_case import (
    DeleteCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.get_case import (
    GetCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.list_case import (
    ListCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)
from sadif.utils.generete_string.markdown_string_generator import MarkdownStringGenerator
from sadif.utils.generete_string.random_string_generator import RandomStringGenerator

if __name__ == "__main__":
    md_generator = MarkdownStringGenerator()
    markdown_document = md_generator.generate_markdown_document("Exemplo de Evento", 3, 5, 10)

    generator = RandomStringGenerator()
    config = SadifConfiguration()

    thehive_url = config.get_configuration("THEHIVE")
    thehive_api_key = config.get_configuration("THEHIVE_API_SERVICE")
    session = SessionThehive(base_url=thehive_url)
    session.set_api_key(thehive_api_key)

    # Step 2: Initialize CreateCase with the session
    case_creator = CreateCase(session)
    # Step 3: Create a new case
    # Create a CaseDataType instance with desired case details
    case_data = CaseDataType(
        title=generator.generate_string_title("Case Creator"),
        description=markdown_document,
        severity=3,
        tags=["dsa", "DSA"],
    )

    print("criar")
    status_code = case_creator.create(case_data)
    print(status_code)

    # Step 4: Initialize GetCase with the session
    get_case = GetCase(session)
    print("pegar")
    # Fetch a specific case
    case_id = status_code[0]["_id"]
    fetched_case = get_case.fetch_case(case_id)
    print(fetched_case)
    print("listar")

    # Step 5: Initialize ListCase with the session
    list_case = ListCase(session)

    # List all cases
    response, status = list_case.list_cases()
    print(response)

    case_delete = DeleteCase(session)
    result = case_delete.delete_case(status_code[0]["_id"])
    print(result)
