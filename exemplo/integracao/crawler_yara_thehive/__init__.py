import datetime

from pymongo import MongoClient

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.crawler.base_crawler import BaseCrawler
from sadif.frameworks_drivers.crawler.crawler_manager import CrawlerManager
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


def current_unix_timestamp():
    # Obtendo a data e hora atual no fuso horário UTC
    data = datetime.datetime.now(datetime.timezone.utc)
    timestamp_convertido = int(
        datetime.datetime.timestamp(data) * 1000
    )  # Multiplicando por 1000 para obter milissegundos

    return timestamp_convertido


# Testando a função
if __name__ == "__main__":
    # Initialize the MongoDB client
    config = SadifConfiguration()
    db_url = config.get_configuration("MONGODB_URL")
    db_real = MongoClient(db_url)
    crawler_manager = CrawlerManager(db_real)
    crawler_without_credential_web = crawler_manager.get_all_documents_by_collection()[
        "crawler_without_credential_web"
    ]
    # Initialize TheHive session with API key
    thehive_url = config.get_configuration("THEHIVE")
    thehive_api_key = config.get_configuration("THEHIVE_API_SERVICE")
    session = SessionThehive(base_url=thehive_url)
    session.set_api_key(thehive_api_key)
    case_creator = CreateCase(session)

    for crawler_run in crawler_without_credential_web:
        crawler = BaseCrawler(
            base_url=crawler_run["url"],
            depth=crawler_run["depth"],
            timeout=crawler_run["timeout"],
            db_client=db_real,
        )
        crawler.crawl(crawler.base_url)
        all_matches = crawler.get_yara_matches()
        print(f"{crawler_run['url']}: {len(all_matches)} match(es)")

        for chamados in all_matches:
            # Create an instance of the TemplateRenderer with the CASE_MONITORING_DNS_ALERT_YARA template
            dns_alert_yara_renderer = TemplateRenderer(
                CaseCommentTemplate.CASE_MONITORING_DNS_ALERT_YARA,
                dominio_suspeito=chamados["link_match"],
                regra_deteccao=chamados["rule_name"],
                cliente=chamados["client_match"],
            )
            # Render the template
            dns_alert_yara_comment = dns_alert_yara_renderer.render()
            # Create Case Data
            case_data = CaseDataType(
                title=f"Nome da Regra: {chamados['rule_name']} | Condição YARA: {chamados['yara_match_condition']} | Correspondência de Link: {chamados['link_match']} | Cliente: {chamados['client_match']} | Tipo de Regra: {chamados['rule_type']}"[
                    :512
                ],  # o TheHive aceita no máximo 512 caracteres no título
                description=dns_alert_yara_comment,
                severity=3,
                tags=[chamados["client_match"], chamados["rule_type"]],
                createdAt=current_unix_timestamp(),
                startDate=current_unix_timestamp(),
            )

            # Create a case using TheHive API
            print(case_creator.create(case_data))
