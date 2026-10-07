import time

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_datatype import (
    CaseDataType,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.create_case import (
    CreateCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case_comment_template import (
    CaseCommentTemplate,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case_comment_template.template_render import (
    TemplateRenderer,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)
from sadif.utils.generete_string.markdown_string_generator import MarkdownStringGenerator
from sadif.utils.generete_string.random_string_generator import RandomStringGenerator


class CreateYaraMatchCaseTheHiveSecurityTicket:
    def __init__(
        self,
        session: SessionThehive,
        dominio_suspeito,
        ip_associado,
        regra_deteccao,
        cliente,
        title,
    ):
        """
        Initialize the DeleteCase object.

        Parameters
        ----------
        session : SessionThehive
            An active session to interact with TheHive's API.
        """
        self.session = session
        self.dominio_suspeito = dominio_suspeito
        self.ip_associado = ip_associado
        self.regra_deteccao = regra_deteccao
        self.cliente = cliente
        self.title = title

    def create_security_ticket(self):
        """Cria um CreateYaraMatchCaseHiveSecurityTicket."""
        return CaseCommentTemplate.MALICIOUS_DNS_ALERT(
            dominio_suspeito=self.dominio_suspeito,
            ip_associado=self.ip_associado,
            data_registro=self.regra_deteccao,
            data_atualizacao=1,
            cliente=self.cliente,
        )

    def create_case(self, ticket):
        """Cria um caso no Thehive."""
        template_instance = CaseCommentTemplate.CASE_MONITORING_DNS_ALERT_YARA
        renderer = TemplateRenderer(template_instance, **ticket.to_dict())

        case_data = CaseDataType(
            title=self.title,
            description=renderer.render(),
            severity=3,
            startDate=time.mktime(ticket.data_registro.timetuple()),
            tags=[ticket.cliente, ticket.regra_deteccao, "MonitoramentoDns"],
        )
        case_creator = CreateCase(self.session)
        status_code = case_creator.create(case_data)
        return status_code

    def main(self):
        """Função principal."""
        ticket = self.create_security_ticket()
        status_code = self.create_case(ticket)
        print(status_code)


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
