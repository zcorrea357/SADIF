from sadif.config.soar_config import SadifConfiguration
from sadif.frameworks_drivers.notification.webhook import WebhookSender
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.caso_de_uso.caselist import (
    CaseLister,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_datatype import (
    CaseDataType,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.create_case import (
    CreateCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.save_case import (
    MongoDBSaver,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.update_case import (
    UpdateCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)
from sadif.utils.generete_string.random_string_generator import RandomStringGenerator


class CaseUpdater:
    def __init__(self, thehive_session: SessionThehive):
        self.thehive_session = thehive_session

    def update_case_tag(self, case_id: str, new_tag: str):
        update_case = UpdateCase(self.thehive_session)
        update_data = {"tags": [new_tag]}
        _response, status = update_case.update_case(case_id, update_data)
        if status != 200:
            msg = f"Erro ao atualizar caso {case_id}: {status}"
            raise Exception(msg)


class CaseProcessor:
    def __init__(
        self, lister: CaseLister, saver: MongoDBSaver, sender: WebhookSender, updater: CaseUpdater
    ):
        self.lister = lister
        self.saver = saver
        self.sender = sender
        self.updater = updater

    def process_cases(self, original_tag: str, new_tag: str):
        cases_with_tag = self.lister.list_cases_by_tag(original_tag)
        self.saver.save_cases(cases_with_tag)

        for case in cases_with_tag:
            self.sender.send(case)
            self.updater.update_case_tag(case["id"], new_tag)

        print("Processamento de casos concluído.")


if __name__ == "__main__":
    config = SadifConfiguration()
    session = SessionThehive(base_url=config.get_configuration("THEHIVE"))
    session.set_api_key(config.get_configuration("THEHIVE_API_SERVICE"))

    # Cria um caso com a tag "caju" para ser processado
    generator = RandomStringGenerator()
    CreateCase(session).create(
        CaseDataType(
            title=generator.generate_string_title("ServiceNow"),
            description="Caso de exemplo para envio ao ServiceNow",
            tags=["caju"],
        )
    )

    case_lister = CaseLister(session)
    mongo_saver = MongoDBSaver(config.get_configuration("MONGODB_URL"), "ServiceNow", "cases")
    webhook_sender = WebhookSender("https://httpbin.org/post")
    case_updater = CaseUpdater(session)

    case_processor = CaseProcessor(case_lister, mongo_saver, webhook_sender, case_updater)
    case_processor.process_cases("caju", "service_now_processed")
