from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_alert import (
    Alert,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)
from sadif.utils.generete_string.markdown_string_generator import MarkdownStringGenerator
from sadif.utils.generete_string.random_string_generator import RandomStringGenerator

# funcionando
if __name__ == "__main__":
    md_generator = MarkdownStringGenerator()
    markdown_document = md_generator.generate_markdown_document("Exemplo de Evento", 3, 5, 10)

    generator = RandomStringGenerator()
    config = SadifConfiguration()

    thehive_url = config.get_configuration("THEHIVE")
    thehive_api_key = config.get_configuration("THEHIVE_API_SERVICE")
    session = SessionThehive(base_url=thehive_url)
    session.set_api_key(thehive_api_key)

    alert = Alert(session)
    response = alert.create(
        alert_type="someType",
        source="someSource",
        sourceRef=generator.generate_string_title("Event"),
        title=generator.generate_string_title("Event"),
        description=markdown_document,
        tags=["fdsa", "fdsa"],
    )
    print(response)
